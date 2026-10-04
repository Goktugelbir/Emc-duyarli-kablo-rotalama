"""Mesh, keep-out volumes, clearance inflation and routing graph."""

from __future__ import annotations

import networkx as nx
import numpy as np

import main
from harness_demo.checks import distance_to_volume
from harness_demo.geometry import BoxVolume, SphereVolume, mark_forbidden_vertices
from harness_demo.graph import build_routing_graph


def test_mesh_size(mesh):
    assert len(mesh.vertices) == main.PARAMS.n_axial * main.PARAMS.n_circ == 3904
    assert len(mesh.faces) == 7560


def test_inflated_volume_contains_clearance_neighbourhood():
    rng = np.random.default_rng(0)
    margin = 0.05
    for vol in (BoxVolume("b", (0, 0, 0), (1, 0.5, 0.3)), SphereVolume("s", (0, 0, 0), 0.4)):
        pts = rng.uniform(-1.0, 1.5, size=(50_000, 3))
        near = pts[distance_to_volume(pts, vol) < margin * 0.999]
        assert len(near) > 100
        assert vol.inflated(margin).contains(near).all()


def test_routable_nodes_respect_clearance(graph, volumes):
    allowed = graph.positions[graph.node_allowed]
    for vol in volumes:
        assert distance_to_volume(allowed, vol).min() >= main.CLEARANCE_M


def test_edges_do_not_enter_volumes(graph, volumes):
    p, q = graph.positions[graph.edges[:, 0]], graph.positions[graph.edges[:, 1]]
    for t in np.linspace(0, 1, 11):
        assert not mark_forbidden_vertices(p + t * (q - p), volumes).any()


def test_graph_is_connected_and_csr_symmetric(graph):
    assert nx.is_connected(graph.nx_graph)
    adj = graph.csr(graph.lengths)
    assert abs(adj - adj.T).max() == 0
    u, v = (int(x) for x in graph.edges[0])
    assert graph.edge_id(u, v) == graph.edge_id(v, u) == 0


def test_clearance_removes_more_nodes(mesh, volumes, graph):
    plain = build_routing_graph(mesh, volumes)
    assert plain.node_allowed.sum() > graph.node_allowed.sum()
