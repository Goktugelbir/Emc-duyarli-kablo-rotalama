"""Routing graph built from the fuselage mesh.

Nodes are mesh vertices, edges are mesh edges weighted by Euclidean length.
Vertices inside forbidden volumes are removed together with their edges; edges
whose straight segment would clip a volume are removed as well.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx
import numpy as np
import trimesh
from scipy.sparse import csr_matrix
from scipy.spatial import cKDTree

from .geometry import ForbiddenVolume, mark_forbidden_vertices


@dataclass
class RoutingGraph:
    """Routable surface graph with fast edge lookup and CSR export."""

    positions: np.ndarray  # (N, 3) positions of *all* mesh vertices
    edges: np.ndarray  # (E, 2) allowed edges, u < v
    lengths: np.ndarray  # (E,) Euclidean edge lengths [m]
    nx_graph: nx.Graph
    node_allowed: np.ndarray  # (N,) True if the vertex is routable
    _edge_lookup: dict[tuple[int, int], int] = field(default_factory=dict, repr=False)
    _tree: cKDTree | None = field(default=None, repr=False)
    _allowed_ids: np.ndarray | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Build the edge lookup table and the KD-tree of routable nodes."""
        self._edge_lookup = {(int(u), int(v)): k for k, (u, v) in enumerate(self.edges)}
        self._allowed_ids = np.flatnonzero(self.node_allowed)
        self._tree = cKDTree(self.positions[self._allowed_ids])

    @property
    def n_nodes(self) -> int:
        """Number of mesh vertices (including removed ones, which stay isolated)."""
        return len(self.positions)

    @property
    def n_edges(self) -> int:
        """Number of routable edges."""
        return len(self.edges)

    def edge_id(self, u: int, v: int) -> int:
        """Index of the undirected edge (u, v)."""
        return self._edge_lookup[(u, v) if u < v else (v, u)]

    def path_edge_ids(self, path: list[int]) -> np.ndarray:
        """Edge indices traversed by a node path."""
        return np.array([self.edge_id(a, b) for a, b in zip(path[:-1], path[1:])], dtype=int)

    def path_length(self, path: list[int]) -> float:
        """Geometric length of a node path [m]."""
        return float(self.lengths[self.path_edge_ids(path)].sum())

    def csr(self, weights: np.ndarray) -> csr_matrix:
        """Symmetric sparse adjacency matrix; edges with non-finite weight are dropped."""
        keep = np.isfinite(weights)
        u, v, w = self.edges[keep, 0], self.edges[keep, 1], weights[keep]
        rows = np.concatenate([u, v])
        cols = np.concatenate([v, u])
        data = np.concatenate([w, w])
        return csr_matrix((data, (rows, cols)), shape=(self.n_nodes, self.n_nodes))

    def nearest_node(self, point: np.ndarray) -> int:
        """Closest routable node to a 3D point."""
        _, k = self._tree.query(point)
        return int(self._allowed_ids[k])


def _segment_clips_volume(p: np.ndarray, q: np.ndarray, volumes: list[ForbiddenVolume], n: int = 7) -> np.ndarray:
    """For E segments (p[i], q[i]) return True where any interior sample is inside a volume."""
    ts = np.linspace(0.0, 1.0, n)[1:-1]
    hit = np.zeros(len(p), dtype=bool)
    for t in ts:
        hit |= mark_forbidden_vertices(p + t * (q - p), volumes)
    return hit


def build_routing_graph(mesh: trimesh.Trimesh, volumes: list[ForbiddenVolume]) -> RoutingGraph:
    """Create the routing graph, removing forbidden nodes/edges and small islands."""
    pos = np.asarray(mesh.vertices)
    forbidden = mark_forbidden_vertices(pos, volumes)
    edges = np.sort(np.asarray(mesh.edges_unique), axis=1)

    ok = ~forbidden[edges[:, 0]] & ~forbidden[edges[:, 1]]
    ok &= ~_segment_clips_volume(pos[edges[:, 0]], pos[edges[:, 1]], volumes)
    edges = edges[ok]
    lengths = np.linalg.norm(pos[edges[:, 0]] - pos[edges[:, 1]], axis=1)

    g = nx.Graph()
    g.add_weighted_edges_from((int(u), int(v), float(w)) for (u, v), w in zip(edges, lengths))
    # Keep only the largest connected component so every terminal pair is routable.
    main = max(nx.connected_components(g), key=len)
    g = g.subgraph(main).copy()

    node_allowed = np.zeros(len(pos), dtype=bool)
    node_allowed[list(main)] = True
    keep = node_allowed[edges[:, 0]] & node_allowed[edges[:, 1]]
    return RoutingGraph(
        positions=pos,
        edges=edges[keep],
        lengths=lengths[keep],
        nx_graph=g,
        node_allowed=node_allowed,
    )
