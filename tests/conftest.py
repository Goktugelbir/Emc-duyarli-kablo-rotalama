"""Shared fixtures: the demo's mesh, graph, scenario and routing results, built once per session."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main  # noqa: E402  (parameters of the published run)
from harness_demo.checks import run_all_checks  # noqa: E402
from harness_demo.geometry import build_fuselage, default_forbidden_volumes  # noqa: E402
from harness_demo.graph import build_routing_graph  # noqa: E402
from harness_demo.metrics import compute_metrics  # noqa: E402
from harness_demo.routing import (  # noqa: E402
    build_turn_graph,
    route_baseline,
    route_bundled,
    route_emc_aware,
    route_integrated,
    route_lagrangian,
)
from harness_demo.scenarios import build_scenario, separation  # noqa: E402


@pytest.fixture(scope="session")
def mesh():
    return build_fuselage(main.PARAMS)


@pytest.fixture(scope="session")
def volumes():
    return default_forbidden_volumes(main.PARAMS.radius)


@pytest.fixture(scope="session")
def graph(mesh, volumes):
    return build_routing_graph(mesh, volumes, clearance=main.CLEARANCE_M)


@pytest.fixture(scope="session")
def cables(graph):
    return build_scenario(graph, main.PARAMS.radius)


@pytest.fixture(scope="session")
def turns(graph):
    return build_turn_graph(graph, main.MIN_BEND_RADIUS_M)


@pytest.fixture(scope="session")
def results(graph, cables, turns):
    """The five methods exactly as main.py runs them, keyed by method name."""
    out = [
        route_baseline(graph, cables),
        route_bundled(graph, cables, reuse_factor=main.REUSE_FACTOR),
        route_emc_aware(graph, cables, separation, reuse_factor=main.REUSE_FACTOR, emc_penalty=main.EMC_PENALTY),
        route_lagrangian(graph, cables, capacity=main.CAPACITY_K, iterations=main.LAGRANGE_ITERATIONS),
        route_integrated(graph, cables, separation, turns, main.CAPACITY_K, reuse_factor=main.REUSE_FACTOR,
                         emc_penalty=main.EMC_PENALTY),
    ]
    return {r.method: r for r in out}


@pytest.fixture(scope="session")
def metrics(results, graph, cables, volumes):
    """Metric rows (independent checks included) keyed by method name."""
    rows = {}
    for name, res in results.items():
        report = run_all_checks(
            [res.routes[c.name] for c in cables], [c.emc_class for c in cables], graph.positions, volumes,
            separation, main.MIN_BEND_RADIUS_M, main.CAPACITY_K, main.CLEARANCE_M,
        )
        rows[name] = compute_metrics(res, graph, report)
    return rows
