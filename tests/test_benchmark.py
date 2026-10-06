"""Scenario perturbation and the robustness benchmark (sequential and parallel)."""

from __future__ import annotations

import itertools

import numpy as np
import pytest

import main
from harness_demo.benchmark import (
    BenchmarkContext,
    RouterSpec,
    format_robustness_markdown,
    route_with,
    run_robustness,
)
from harness_demo.checks import CheckSettings
from harness_demo.geometry import surface_point
from harness_demo.scenarios import SCENARIO_SPECS, perturb_specs, separation


def _terminals(specs):
    pts = []
    for s in specs:
        pts += [(s.emc_class, surface_point(*s.start_xt, main.PARAMS.radius)),
                (s.emc_class, surface_point(*s.end_xt, main.PARAMS.radius))]
    return pts


@pytest.fixture(scope="module")
def ctx(graph, volumes, turns):
    settings = CheckSettings(volumes, separation, main.MIN_BEND_RADIUS_M, main.CAPACITY_K, main.CLEARANCE_M)
    return BenchmarkContext(graph, settings, turns)


def test_perturbation_keeps_terminals_separable():
    rng = np.random.default_rng(0)
    for _ in range(50):
        pts = _terminals(perturb_specs(SCENARIO_SPECS, rng))
        for (ca, pa), (cb, pb) in itertools.combinations(pts, 2):
            if ca != cb:
                assert np.linalg.norm(pa - pb) > separation(ca, cb)


def test_robustness_rows(ctx):
    rows = run_robustness(ctx, SCENARIO_SPECS, main.PARAMS.radius, {"a": RouterSpec("baseline")}, n_trials=2)
    assert [r["family"] for r in rows] == ["Rastgele sıra", "Rastgele sıra + uç nokta sapması"]
    for r in rows:
        assert r["trials"] == 2 and 0 <= r["emc_zero"] <= 2 and 0 <= r["all_clean"] <= 2
    assert format_robustness_markdown(rows).count("\n") == 1 + len(rows)


def test_parallel_benchmark_matches_sequential(ctx):
    """Trials are drawn in the parent process, so the summary does not depend on the worker count."""
    routers = {"a": RouterSpec("baseline"), "e": main.BENCHMARK_ROUTERS["e) Bütünleşik"]}
    seq = run_robustness(ctx, SCENARIO_SPECS, main.PARAMS.radius, routers, n_trials=2, workers=1)
    par = run_robustness(ctx, SCENARIO_SPECS, main.PARAMS.radius, routers, n_trials=2, workers=2)
    assert par == seq


def test_router_specs_cover_every_benchmark_method(ctx, cables):
    for spec in main.BENCHMARK_ROUTERS.values():
        res = route_with(spec, ctx, cables)
        assert set(res.routes) == {c.name for c in cables}
    with pytest.raises(ValueError):
        route_with(RouterSpec("unknown"), ctx, cables)
