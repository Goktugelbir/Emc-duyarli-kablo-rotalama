"""Sequential routing (methods b, c, e): bundling discount, EMC penalty, capacity penalty,
optional turn-aware graph, and rip-up-and-reroute of the cables that still conflict."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from ..graph import RoutingGraph
from ..scenarios import Cable
from .core import SAMPLE_STEP_M, RoutingResult, densify, shortest_path
from .turn_graph import TurnGraph, turn_aware_path

ORDER_STRATEGIES: tuple[str, ...] = ("input", "critical-first", "longest-first", "shortest-first")


def order_cables(
    cables: Sequence[Cable],
    strategy: str = "input",
    positions: np.ndarray | None = None,
) -> list[Cable]:
    """Sort cables according to a designated initial routing priority heuristic.

    Supported strategies:
    - "input": Original list order (default).
    - "critical-first": Highest-EMC-separation classes first (power -> data -> signal),
      and longest cables within the same class first.
    - "longest-first": Longest direct terminal-to-terminal Euclidean distance first,
      establishing trunk corridors early.
    - "shortest-first": Shortest terminal-to-terminal distance first.
    """
    if strategy not in ORDER_STRATEGIES:
        raise ValueError(f"Unknown ordering strategy: {strategy!r}. Expected one of: {', '.join(ORDER_STRATEGIES)}.")
    if strategy == "input":
        return list(cables)
    if positions is None:
        raise ValueError(f"ordering strategy {strategy!r} needs the node positions")

    def dist(c: Cable) -> float:
        return float(np.linalg.norm(positions[c.start] - positions[c.end]))

    if strategy == "longest-first":
        return sorted(cables, key=dist, reverse=True)
    elif strategy == "shortest-first":
        return sorted(cables, key=dist)
    class_priority = {"power": 0, "data": 1, "signal": 2}  # critical-first
    return sorted(cables, key=lambda c: (class_priority.get(c.emc_class, 99), -dist(c)))


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
    order_strategy: str = "input"


class _RouteGeometry:
    """Per-route derived data (unique edges, dense samples, sample KD-tree, nearby nodes).

    Sequential routing re-evaluates the same placed routes for every cable and every reroute
    round; caching by the route itself (an immutable tuple of node ids) turns those repeated
    computations into lookups without changing any result.
    """

    def __init__(self, graph: RoutingGraph) -> None:
        self.graph = graph
        self.node_tree = cKDTree(graph.positions)
        self._edges: dict[tuple[int, ...], np.ndarray] = {}
        self._samples: dict[tuple[int, ...], np.ndarray] = {}
        self._trees: dict[tuple[int, ...], cKDTree] = {}
        self._near: dict[tuple[tuple[int, ...], float], np.ndarray] = {}

    def edges(self, path: list[int]) -> np.ndarray:
        key = tuple(path)
        if key not in self._edges:
            self._edges[key] = np.unique(self.graph.path_edge_ids(path))
        return self._edges[key]

    def samples(self, path: list[int]) -> np.ndarray:
        key = tuple(path)
        if key not in self._samples:
            self._samples[key] = densify(self.graph.positions[path], SAMPLE_STEP_M)
        return self._samples[key]

    def sample_tree(self, path: list[int]) -> cKDTree:
        key = tuple(path)
        if key not in self._trees:
            self._trees[key] = cKDTree(self.samples(path))
        return self._trees[key]

    def nodes_near(self, path: list[int], radius: float) -> np.ndarray:
        """Graph nodes within `radius` of the route (KD-tree query around its samples only)."""
        key = (tuple(path), radius)
        if key not in self._near:
            hits = self.node_tree.query_ball_point(self.samples(path), r=radius)
            self._near[key] = np.unique(np.concatenate([np.asarray(h, dtype=int) for h in hits]))
        return self._near[key]


def _cable_cost(
    graph: RoutingGraph,
    geo: _RouteGeometry,
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
        eids = geo.edges(path)
        used[eids] = True
        load[eids] += 1
        if cfg.separation_fn is not None and emc_penalty > 0.0:
            sep = cfg.separation_fn(cable.emc_class, classes[name])
            if sep > 0.0:
                tainted[geo.nodes_near(path, sep + cfg.emc_margin)] = True

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
    geo: _RouteGeometry | None = None,
) -> dict[str, float]:
    """Router-side conflict score per cable (EMC samples too close + overloaded edges).

    This is the router's own estimate used to decide what to reroute; the reported metrics
    come from the independent checks in `checks.py`.
    """
    geo = geo or _RouteGeometry(graph)
    score = {name: 0.0 for name in routes}
    if separation_fn is not None:
        samples = {n: geo.samples(p) for n, p in routes.items()}
        trees = {n: geo.sample_tree(p) for n, p in routes.items()}
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
        edge_sets = {n: geo.edges(p) for n, p in routes.items()}
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
    geo = _RouteGeometry(graph)
    classes = {c.name: c.emc_class for c in cables}
    by_name = {c.name: c for c in cables}
    routes: dict[str, list[int]] = {}
    order: list[str] = []
    initial_cables = order_cables(cables, cfg.order_strategy, graph.positions)
    for cable in initial_cables:
        cost = _cable_cost(graph, geo, cable, routes, classes, cfg, cfg.emc_penalty)
        routes[cable.name] = _route_one(graph, cost, cable, cfg)
        order.append(cable.name)

    def conflicts(r: dict[str, list[int]]) -> dict[str, float]:
        return route_conflicts(graph, r, classes, cfg.separation_fn, cfg.capacity, geo)

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
            cost = _cable_cost(graph, geo, by_name[name], placed, classes, cfg, penalty)
            routes[name] = _route_one(graph, cost, by_name[name], cfg)
            order.remove(name)
            order.append(name)
        score = conflicts(routes)
        if sum(score.values()) < best[0]:
            best = (sum(score.values()), dict(routes), list(order))
    _, routes, order = best
    return {c.name: routes[c.name] for c in cables}, order


def route_bundled(
    graph: RoutingGraph,
    cables: list[Cable],
    reuse_factor: float = 0.4,
    order_strategy: str = "input",
) -> RoutingResult:
    """Sequential routing that rewards reusing edges of earlier cables."""
    t0 = time.perf_counter()
    cfg = _SequentialConfig(reuse_factor=reuse_factor, order_strategy=order_strategy)
    routes, order = _route_sequential(graph, cables, cfg)
    return RoutingResult("bundled", "b) Demetleme", routes, time.perf_counter() - t0, order=order)


def route_emc_aware(
    graph: RoutingGraph,
    cables: list[Cable],
    separation_fn: Callable[[str, str], float],
    reuse_factor: float = 0.4,
    emc_penalty: float = 20.0,
    emc_margin: float = 0.03,
    reroute_rounds: int = 5,
    order_strategy: str = "input",
) -> RoutingResult:
    """Bundling plus a soft penalty near routes of other EMC classes, with rip-up-and-reroute."""
    t0 = time.perf_counter()
    cfg = _SequentialConfig(reuse_factor=reuse_factor, separation_fn=separation_fn, emc_penalty=emc_penalty,
                            emc_margin=emc_margin, reroute_rounds=reroute_rounds, order_strategy=order_strategy)
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
    order_strategy: str = "input",
) -> RoutingResult:
    """EMC-aware bundling on the turn-aware graph with a (near-hard) capacity penalty.

    Bend radius is a hard constraint (forbidden turns do not exist in `turns`), capacity and EMC
    separation are penalties strong enough to be respected whenever the geometry allows it.
    """
    t0 = time.perf_counter()
    cfg = _SequentialConfig(reuse_factor=reuse_factor, separation_fn=separation_fn, emc_penalty=emc_penalty,
                            emc_margin=emc_margin, capacity=capacity, capacity_penalty=capacity_penalty,
                            turns=turns, reroute_rounds=reroute_rounds, order_strategy=order_strategy)
    routes, order = _route_sequential(graph, cables, cfg)
    return RoutingResult("integrated", "e) Bütünleşik (EMC + kapasite + bükülme)", routes,
                         time.perf_counter() - t0, order=order)
