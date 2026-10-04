"""Routing algorithms.

a) baseline        : independent Dijkstra per cable
b) bundled         : sequential routing; reused edges get a cost discount
c) emc_aware       : (b) + penalty on edges close to earlier routes of other EMC classes
d) lagrangian      : edge capacity (<= K cables) relaxed with Lagrange multipliers,
                     subgradient updates, lower/upper bounds tracked per iteration
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

from .graph import RoutingGraph
from .scenarios import EMC_CLASSES, Cable


class NoPathError(RuntimeError):
    """Raised when a cable cannot be routed."""


@dataclass
class RoutingResult:
    """Routes produced by one method plus bookkeeping."""

    method: str
    label: str
    routes: dict[str, list[int]]
    runtime_s: float
    history: list[dict[str, float]] = field(default_factory=list)


def shortest_path(adj: csr_matrix, source: int, target: int) -> list[int]:
    """Dijkstra shortest node path from source to target on a CSR adjacency."""
    dist, pred = dijkstra(adj, directed=True, indices=source, return_predecessors=True)
    if not np.isfinite(dist[target]):
        raise NoPathError(f"no path {source} -> {target}")
    path = [target]
    while path[-1] != source:
        path.append(int(pred[path[-1]]))
    return path[::-1]


def _densify(points: np.ndarray, step: float) -> np.ndarray:
    """Insert points along a polyline so consecutive samples are <= step apart."""
    out = [points[0]]
    for a, b in zip(points[:-1], points[1:]):
        n = max(1, int(np.ceil(np.linalg.norm(b - a) / step)))
        out.extend(a + (b - a) * t for t in np.linspace(0, 1, n + 1)[1:])
    return np.asarray(out)


def route_baseline(graph: RoutingGraph, cables: list[Cable]) -> RoutingResult:
    """Each cable takes its own geometric shortest path."""
    t0 = time.perf_counter()
    adj = graph.csr(graph.lengths)
    routes = {c.name: shortest_path(adj, c.start, c.end) for c in cables}
    return RoutingResult("baseline", "a) Baseline (bağımsız Dijkstra)", routes, time.perf_counter() - t0)


def _route_sequential(
    graph: RoutingGraph,
    cables: list[Cable],
    reuse_factor: float,
    separation_fn: Callable[[str, str], float] | None,
    emc_penalty: float,
    emc_margin: float,
) -> dict[str, list[int]]:
    """Route cables one by one with bundling discount and optional EMC penalty.

    Bundling: an edge already used by any earlier cable costs `reuse_factor * length`.
    EMC: after a cable of class c is routed, nodes within sep(c, c') + margin of it
    are marked "tainted" for every other class c'. A KD-tree query limits this to the
    neighbourhood of the route. A later cable of class c' pays
    `emc_penalty * length` extra on every edge touching a tainted node.
    """
    used = np.zeros(graph.n_edges, dtype=bool)
    tainted = {c: np.zeros(graph.n_nodes, dtype=bool) for c in EMC_CLASSES}
    tree = cKDTree(graph.positions) if separation_fn else None
    routes: dict[str, list[int]] = {}

    for cable in cables:
        cost = graph.lengths * np.where(used, reuse_factor, 1.0)
        if separation_fn is not None:
            t = tainted[cable.emc_class]
            near = t[graph.edges[:, 0]] | t[graph.edges[:, 1]]
            cost = cost + emc_penalty * graph.lengths * near
        path = shortest_path(graph.csr(cost), cable.start, cable.end)
        routes[cable.name] = path
        used[graph.path_edge_ids(path)] = True

        if separation_fn is not None:
            pts = _densify(graph.positions[path], step=0.05)
            for other in EMC_CLASSES:
                sep = separation_fn(cable.emc_class, other)
                if sep <= 0.0:
                    continue
                hits = tree.query_ball_point(pts, r=sep + emc_margin)
                idx = np.unique(np.concatenate([np.asarray(h, dtype=int) for h in hits]))
                tainted[other][idx] = True
    return routes


def route_bundled(graph: RoutingGraph, cables: list[Cable], reuse_factor: float = 0.4) -> RoutingResult:
    """Sequential routing that rewards reusing edges of earlier cables."""
    t0 = time.perf_counter()
    routes = _route_sequential(graph, cables, reuse_factor, None, 0.0, 0.0)
    return RoutingResult("bundled", "b) Demetleme", routes, time.perf_counter() - t0)


def route_emc_aware(
    graph: RoutingGraph,
    cables: list[Cable],
    separation_fn: Callable[[str, str], float],
    reuse_factor: float = 0.4,
    emc_penalty: float = 20.0,
    emc_margin: float = 0.03,
) -> RoutingResult:
    """Bundling plus a soft penalty near routes of other EMC classes."""
    t0 = time.perf_counter()
    routes = _route_sequential(graph, cables, reuse_factor, separation_fn, emc_penalty, emc_margin)
    return RoutingResult("emc_aware", "c) EMC duyarlı demetleme", routes, time.perf_counter() - t0)


def _repair_feasible(
    graph: RoutingGraph, cables: list[Cable], cost: np.ndarray, capacity: int
) -> dict[str, list[int]] | None:
    """Primal heuristic: route sequentially on `cost`, closing edges that reach capacity."""
    load = np.zeros(graph.n_edges, dtype=int)
    routes: dict[str, list[int]] = {}
    for cable in cables:
        c = np.where(load >= capacity, np.inf, cost)
        try:
            path = shortest_path(graph.csr(c), cable.start, cable.end)
        except NoPathError:
            return None
        routes[cable.name] = path
        load[graph.path_edge_ids(path)] += 1
    return routes


def route_lagrangian(
    graph: RoutingGraph,
    cables: list[Cable],
    capacity: int = 3,
    iterations: int = 60,
    step_scale: float = 1.0,
    patience: int = 5,
) -> RoutingResult:
    """Lagrangian relaxation of  min sum_k len(P_k)  s.t.  load_e <= K  for every edge.

    Relaxing the capacity constraint with multipliers lambda_e >= 0 gives
        L(lambda) = sum_k SP_k(w + lambda) - K * sum_e lambda_e ,
    a lower bound on the optimum that decomposes into one shortest-path problem per
    cable. lambda is updated by projected subgradient with a Polyak step; an upper
    bound comes from a capacity-respecting repair heuristic guided by w + lambda.
    """
    t0 = time.perf_counter()
    w = graph.lengths
    lam = np.zeros(graph.n_edges)
    best_lb, best_ub = -np.inf, np.inf
    best_routes: dict[str, list[int]] | None = None
    theta, stall = step_scale, 0
    history: list[dict[str, float]] = []

    for it in range(iterations):
        cost = w + lam
        adj = graph.csr(cost)
        load = np.zeros(graph.n_edges, dtype=int)
        sp_total = 0.0
        for cable in cables:
            path = shortest_path(adj, cable.start, cable.end)
            eids = graph.path_edge_ids(path)
            sp_total += float(cost[eids].sum())
            load[eids] += 1
        dual = sp_total - capacity * float(lam.sum())

        if dual > best_lb + 1e-9:
            best_lb, stall = dual, 0
        else:
            stall += 1
            if stall >= patience:
                theta, stall = theta / 2.0, 0

        routes = _repair_feasible(graph, cables, cost, capacity)
        if routes is not None:
            total = sum(graph.path_length(p) for p in routes.values())
            if total < best_ub:
                best_ub, best_routes = total, routes

        history.append(
            {"iteration": it, "dual": dual, "lower_bound": best_lb, "upper_bound": best_ub, "theta": theta}
        )

        g = (load - capacity).astype(float)
        g[(lam <= 0.0) & (g < 0.0)] = 0.0  # projected subgradient
        norm2 = float(g @ g)
        if norm2 == 0.0 or best_ub - best_lb < 1e-6:
            break
        lam = np.maximum(0.0, lam + theta * (best_ub - dual) / norm2 * g)

    if best_routes is None:
        raise NoPathError("Lagrangian heuristic found no capacity-feasible solution")
    return RoutingResult(
        "lagrangian", f"d) Lagrange gevşetmesi (K={capacity})", best_routes, time.perf_counter() - t0, history
    )
