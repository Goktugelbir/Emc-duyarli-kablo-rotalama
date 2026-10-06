"""Shared routing building blocks: result type, Dijkstra, route sampling and the baseline method."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

from ..graph import RoutingGraph
from ..scenarios import Cable

SAMPLE_STEP_M = 0.05  # spacing used when measuring distances between routes inside the router


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


def densify(points: np.ndarray, step: float) -> np.ndarray:
    """Insert points along a polyline so consecutive samples are <= step apart.

    Vectorised; the sample parameters reproduce `np.linspace(0, 1, n + 1)[1:]` per segment
    exactly (i * (1 / n), the last one exactly 1), so the result is bit-identical to a loop.

    Note: `checks.resample_polyline` is a deliberate near-duplicate. The independent checks must
    not import any routing code, so they keep their own copy (which uses t = i / n); the router
    uses this one only to *decide* what to penalise or reroute, never to report results.
    """
    a, d = points[:-1], points[1:] - points[:-1]
    n = np.maximum(1, np.ceil(np.linalg.norm(d, axis=1) / step).astype(int))
    seg = np.repeat(np.arange(len(n)), n)
    i = np.arange(len(seg)) - np.repeat(np.cumsum(n) - n, n) + 1
    t = i * (1.0 / n[seg])
    t[np.cumsum(n) - 1] = 1.0
    return np.vstack([points[:1], a[seg] + d[seg] * t[:, None]])


def circumradii(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Vectorised radius of the circle through rows of a, b, c (inf where collinear)."""
    ab = np.linalg.norm(b - a, axis=1)
    bc = np.linalg.norm(c - b, axis=1)
    ca = np.linalg.norm(a - c, axis=1)
    area2 = np.linalg.norm(np.cross(b - a, c - a), axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = ab * bc * ca / (2.0 * area2)
    return np.where(area2 < 1e-12, np.inf, r)


def route_baseline(graph: RoutingGraph, cables: list[Cable]) -> RoutingResult:
    """Each cable takes its own geometric shortest path."""
    t0 = time.perf_counter()
    adj = graph.csr(graph.lengths)
    routes = {c.name: shortest_path(adj, c.start, c.end) for c in cables}
    return RoutingResult("baseline", "a) Baseline (bağımsız Dijkstra)", routes, time.perf_counter() - t0,
                         order=[c.name for c in cables])
