"""Bend-aware routing: the line graph of the routing graph with only the allowed turns."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.sparse import csr_matrix

from ..graph import RoutingGraph
from .core import circumradii, shortest_path

_SINK_EPS = 1e-12  # tiny weight for arcs into the virtual sink (explicit zeros would be dropped)


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
    ok &= circumradii(a, b, c) >= min_radius * (1.0 + 1e-9)
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
