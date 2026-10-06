"""Method d: Lagrangian relaxation of the edge-capacity constraint (subgradient, Polyak step)."""

from __future__ import annotations

import time

import numpy as np

from ..graph import RoutingGraph
from ..scenarios import Cable
from .core import NoPathError, RoutingResult, shortest_path


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
