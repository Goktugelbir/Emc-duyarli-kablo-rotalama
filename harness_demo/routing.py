"""Routing algorithms.

a) baseline        : independent Dijkstra per cable
b) bundled         : sequential routing; reused edges get a cost discount
c) emc_aware       : (b) + penalty on edges close to routes of other EMC classes,
                     followed by rip-up-and-reroute of cables that still conflict
d) lagrangian      : edge capacity (<= K cables) relaxed with Lagrange multipliers,
                     subgradient updates, lower/upper bounds tracked per iteration
e) integrated      : (c) on a turn-aware graph (no turn sharper than the minimum bend
                     radius can be taken) with a capacity penalty on full edges
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
from .scenarios import Cable

SAMPLE_STEP_M = 0.05  # spacing used when measuring distances between routes inside the router
_SINK_EPS = 1e-12  # tiny weight for arcs into the virtual sink (explicit zeros would be dropped)


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
    order: list[str] = field(default_factory=list)  # order in which cables were (last) routed


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


def _circumradius(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Vectorised radius of the circle through rows of a, b, c (inf where collinear)."""
    ab = np.linalg.norm(b - a, axis=1)
    bc = np.linalg.norm(c - b, axis=1)
    ca = np.linalg.norm(a - c, axis=1)
    area2 = np.linalg.norm(np.cross(b - a, c - a), axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = ab * bc * ca / (2.0 * area2)
    return np.where(area2 < 1e-12, np.inf, r)


# --------------------------------------------------------------------------- turn-aware graph


@dataclass
class TurnGraph:
    """Line graph of the routing graph: one state per directed edge, arcs = allowed turns.

    A route u -> v -> w is only possible if w != u and the circle through u, v, w has a
    radius of at least `min_radius`, i.e. exactly the condition the bend check tests.
    """

    de_from: np.ndarray  # (2E,) tail node of each directed edge
    de_to: np.ndarray  # (2E,) head node
    de_edge: np.ndarray  # (2E,) undirected edge id
    arc_src: np.ndarray  # allowed transitions de_src -> de_dst
    arc_dst: np.ndarray
    min_radius: float

    @property
    def n_states(self) -> int:
        """Number of directed edges."""
        return len(self.de_from)


def build_turn_graph(graph: RoutingGraph, min_radius: float) -> TurnGraph:
    """Enumerate every (u->v, v->w) transition and keep the ones with a large enough bend radius."""
    e = graph.edges
    de_from = np.concatenate([e[:, 0], e[:, 1]])
    de_to = np.concatenate([e[:, 1], e[:, 0]])
    de_edge = np.concatenate([np.arange(len(e)), np.arange(len(e))])

    # Out-going directed edges grouped by tail node -> contiguous ranges.
    order = np.argsort(de_from, kind="stable")
    counts_by_node = np.bincount(de_from, minlength=graph.n_nodes)
    start_by_node = np.concatenate([[0], np.cumsum(counts_by_node)[:-1]])

    counts = counts_by_node[de_to]  # successors of each directed edge
    arc_src = np.repeat(np.arange(len(de_from)), counts)
    within = np.arange(counts.sum()) - np.repeat(np.cumsum(counts) - counts, counts)
    arc_dst = order[np.repeat(start_by_node[de_to], counts) + within]

    pos = graph.positions
    a, b, c = pos[de_from[arc_src]], pos[de_to[arc_src]], pos[de_to[arc_dst]]
    ok = de_to[arc_dst] != de_from[arc_src]  # no U-turns
    ok &= _circumradius(a, b, c) >= min_radius * (1.0 + 1e-9)
    return TurnGraph(de_from, de_to, de_edge, arc_src[ok], arc_dst[ok], min_radius)


def turn_aware_path(turns: TurnGraph, cost: np.ndarray, source: int, target: int) -> list[int]:
    """Cheapest node path from source to target that only uses allowed turns.

    The cost of a state (directed edge) is paid when it is entered; a virtual source enters
    every edge leaving `source` and every edge reaching `target` leads to a virtual sink.
    """
    n = turns.n_states
    src, snk = n, n + 1
    start = np.flatnonzero(turns.de_from == source)
    end = np.flatnonzero(turns.de_to == target)
    w_arc = cost[turns.de_edge[turns.arc_dst]]
    keep = np.isfinite(w_arc)
    rows = np.concatenate([turns.arc_src[keep], np.full(len(start), src), end])
    cols = np.concatenate([turns.arc_dst[keep], start, np.full(len(end), snk)])
    data = np.concatenate([w_arc[keep], cost[turns.de_edge[start]], np.full(len(end), _SINK_EPS)])
    adj = csr_matrix((data, (rows, cols)), shape=(n + 2, n + 2))
    states = shortest_path(adj, src, snk)[1:-1]
    return [int(turns.de_from[states[0]])] + [int(turns.de_to[s]) for s in states]


# --------------------------------------------------------------------------- sequential routing


@dataclass
class _SequentialConfig:
    """Cost model of the sequential methods (b, c, e)."""

    reuse_factor: float = 0.4
    separation_fn: Callable[[str, str], float] | None = None
    emc_penalty: float = 0.0
    emc_margin: float = 0.03
    capacity: int | None = None
    capacity_penalty: float = 1000.0
    turns: TurnGraph | None = None
    reroute_rounds: int = 0
    penalty_growth: float = 2.0  # EMC penalty multiplier per rip-up-and-reroute round


def _cable_cost(
    graph: RoutingGraph,
    tree: cKDTree,
    cable: Cable,
    placed: dict[str, list[int]],
    classes: dict[str, str],
    cfg: _SequentialConfig,
    emc_penalty: float,
) -> np.ndarray:
    """Edge costs for `cable` given the routes already placed (excluding the cable itself).

    Bundling: an edge used by any other cable costs `reuse_factor * length`.
    EMC: nodes within sep(c, c') + margin of a route of class c' are "tainted" for class c;
    edges touching a tainted node pay `emc_penalty * length` extra. The KD-tree query keeps
    this local to each route's neighbourhood.
    Capacity: an edge already carrying `capacity` other cables pays `capacity_penalty * length`.
    """
    w = graph.lengths
    used = np.zeros(graph.n_edges, dtype=bool)
    load = np.zeros(graph.n_edges, dtype=int)
    tainted = np.zeros(graph.n_nodes, dtype=bool)
    for name, path in placed.items():
        if name == cable.name:
            continue
        eids = np.unique(graph.path_edge_ids(path))
        used[eids] = True
        load[eids] += 1
        if cfg.separation_fn is not None and emc_penalty > 0.0:
            sep = cfg.separation_fn(cable.emc_class, classes[name])
            if sep > 0.0:
                hits = tree.query_ball_point(_densify(graph.positions[path], SAMPLE_STEP_M), r=sep + cfg.emc_margin)
                tainted[np.unique(np.concatenate([np.asarray(h, dtype=int) for h in hits]))] = True

    cost = w * np.where(used, cfg.reuse_factor, 1.0)
    if cfg.separation_fn is not None and emc_penalty > 0.0:
        cost = cost + emc_penalty * w * (tainted[graph.edges[:, 0]] | tainted[graph.edges[:, 1]])
    if cfg.capacity is not None:
        cost = cost + cfg.capacity_penalty * w * (load >= cfg.capacity)
    return cost


def _route_one(graph: RoutingGraph, cost: np.ndarray, cable: Cable, cfg: _SequentialConfig) -> list[int]:
    """Shortest path for one cable on the plain or the turn-aware graph."""
    if cfg.turns is not None:
        return turn_aware_path(cfg.turns, cost, cable.start, cable.end)
    return shortest_path(graph.csr(cost), cable.start, cable.end)


def route_conflicts(
    graph: RoutingGraph,
    routes: dict[str, list[int]],
    classes: dict[str, str],
    separation_fn: Callable[[str, str], float] | None,
    capacity: int | None,
) -> dict[str, float]:
    """Router-side conflict score per cable (EMC samples too close + overloaded edges).

    This is the router's own estimate used to decide what to reroute; the reported metrics
    come from the independent checks in `checks.py`.
    """
    score = {name: 0.0 for name in routes}
    if separation_fn is not None:
        samples = {n: _densify(graph.positions[p], SAMPLE_STEP_M) for n, p in routes.items()}
        trees = {n: cKDTree(s) for n, s in samples.items()}
        for a in routes:
            for b in routes:
                if a == b:
                    continue
                sep = separation_fn(classes[a], classes[b])
                if sep <= 0.0:
                    continue
                d, _ = trees[b].query(samples[a])
                score[a] += float(np.count_nonzero(d < sep))
    if capacity is not None:
        load = np.zeros(graph.n_edges, dtype=int)
        edge_sets = {n: np.unique(graph.path_edge_ids(p)) for n, p in routes.items()}
        for eids in edge_sets.values():
            load[eids] += 1
        for n, eids in edge_sets.items():
            score[n] += float(np.count_nonzero(load[eids] > capacity))
    return score


def _route_sequential(
    graph: RoutingGraph, cables: list[Cable], cfg: _SequentialConfig
) -> tuple[dict[str, list[int]], list[str]]:
    """Route cables one by one, then rip up and reroute the ones that still conflict.

    In every reroute round the conflicting cables are removed and routed again, most
    conflicting first, now seeing *all* other routes (not only earlier ones) and with the
    EMC penalty multiplied by `penalty_growth`. The best solution (lowest total conflict
    score) seen over all rounds is returned, so rerouting never makes the result worse.
    """
    tree = cKDTree(graph.positions)
    classes = {c.name: c.emc_class for c in cables}
    by_name = {c.name: c for c in cables}
    routes: dict[str, list[int]] = {}
    order: list[str] = []
    for cable in cables:
        cost = _cable_cost(graph, tree, cable, routes, classes, cfg, cfg.emc_penalty)
        routes[cable.name] = _route_one(graph, cost, cable, cfg)
        order.append(cable.name)

    def conflicts(r: dict[str, list[int]]) -> dict[str, float]:
        return route_conflicts(graph, r, classes, cfg.separation_fn, cfg.capacity)

    score = conflicts(routes)
    best = (sum(score.values()), dict(routes), list(order))
    penalty = cfg.emc_penalty
    for _ in range(cfg.reroute_rounds):
        bad = sorted((n for n, s in score.items() if s > 0), key=lambda n: -score[n])
        if not bad:
            break
        penalty *= cfg.penalty_growth
        for name in bad:
            placed = {n: p for n, p in routes.items() if n != name}
            cost = _cable_cost(graph, tree, by_name[name], placed, classes, cfg, penalty)
            routes[name] = _route_one(graph, cost, by_name[name], cfg)
            order.remove(name)
            order.append(name)
        score = conflicts(routes)
        if sum(score.values()) < best[0]:
            best = (sum(score.values()), dict(routes), list(order))
    _, routes, order = best
    return {c.name: routes[c.name] for c in cables}, order


def route_baseline(graph: RoutingGraph, cables: list[Cable]) -> RoutingResult:
    """Each cable takes its own geometric shortest path."""
    t0 = time.perf_counter()
    adj = graph.csr(graph.lengths)
    routes = {c.name: shortest_path(adj, c.start, c.end) for c in cables}
    return RoutingResult("baseline", "a) Baseline (bağımsız Dijkstra)", routes, time.perf_counter() - t0,
                         order=[c.name for c in cables])


def route_bundled(graph: RoutingGraph, cables: list[Cable], reuse_factor: float = 0.4) -> RoutingResult:
    """Sequential routing that rewards reusing edges of earlier cables."""
    t0 = time.perf_counter()
    routes, order = _route_sequential(graph, cables, _SequentialConfig(reuse_factor=reuse_factor))
    return RoutingResult("bundled", "b) Demetleme", routes, time.perf_counter() - t0, order=order)


def route_emc_aware(
    graph: RoutingGraph,
    cables: list[Cable],
    separation_fn: Callable[[str, str], float],
    reuse_factor: float = 0.4,
    emc_penalty: float = 20.0,
    emc_margin: float = 0.03,
    reroute_rounds: int = 5,
) -> RoutingResult:
    """Bundling plus a soft penalty near routes of other EMC classes, with rip-up-and-reroute."""
    t0 = time.perf_counter()
    cfg = _SequentialConfig(reuse_factor=reuse_factor, separation_fn=separation_fn, emc_penalty=emc_penalty,
                            emc_margin=emc_margin, reroute_rounds=reroute_rounds)
    routes, order = _route_sequential(graph, cables, cfg)
    return RoutingResult("emc_aware", "c) EMC duyarlı demetleme", routes, time.perf_counter() - t0, order=order)


def route_integrated(
    graph: RoutingGraph,
    cables: list[Cable],
    separation_fn: Callable[[str, str], float],
    turns: TurnGraph,
    capacity: int,
    reuse_factor: float = 0.4,
    emc_penalty: float = 20.0,
    emc_margin: float = 0.03,
    capacity_penalty: float = 1000.0,
    reroute_rounds: int = 10,
) -> RoutingResult:
    """EMC-aware bundling on the turn-aware graph with a (near-hard) capacity penalty.

    Bend radius is a hard constraint (forbidden turns do not exist in `turns`), capacity and EMC
    separation are penalties strong enough to be respected whenever the geometry allows it.
    """
    t0 = time.perf_counter()
    cfg = _SequentialConfig(reuse_factor=reuse_factor, separation_fn=separation_fn, emc_penalty=emc_penalty,
                            emc_margin=emc_margin, capacity=capacity, capacity_penalty=capacity_penalty,
                            turns=turns, reroute_rounds=reroute_rounds)
    routes, order = _route_sequential(graph, cables, cfg)
    return RoutingResult("integrated", "e) Bütünleşik (EMC + kapasite + bükülme)", routes,
                         time.perf_counter() - t0, order=order)


# --------------------------------------------------------------------------- Lagrangian relaxation


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
    target_gap: float = 0.05,
) -> RoutingResult:
    """Lagrangian relaxation of  min sum_k len(P_k)  s.t.  load_e <= K  for every edge.

    Relaxing the capacity constraint with multipliers lambda_e >= 0 gives
        L(lambda) = sum_k SP_k(w + lambda) - K * sum_e lambda_e ,
    a lower bound on the optimum that decomposes into one shortest-path problem per
    cable. lambda is updated by projected subgradient with a Polyak step; an upper
    bound comes from a capacity-respecting repair heuristic guided by w + lambda.
    While no feasible solution is known, the Polyak target is the best lower bound
    raised by `target_gap` (so the step stays finite).
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
        target = best_ub if np.isfinite(best_ub) else best_lb + target_gap * max(abs(best_lb), 1.0)
        lam = np.maximum(0.0, lam + theta * max(target - dual, 0.0) / norm2 * g)

    if best_routes is None:
        raise NoPathError("Lagrangian heuristic found no capacity-feasible solution")
    return RoutingResult(
        "lagrangian", f"d) Lagrange gevşetmesi (K={capacity})", best_routes, time.perf_counter() - t0, history,
        order=[c.name for c in cables],
    )
