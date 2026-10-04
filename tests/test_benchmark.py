"""Scenario perturbation and the robustness benchmark."""

from __future__ import annotations

import itertools

import numpy as np

import main
from harness_demo.benchmark import CheckSettings, format_robustness_markdown, run_robustness
from harness_demo.geometry import surface_point
from harness_demo.routing import route_baseline
from harness_demo.scenarios import SCENARIO_SPECS, perturb_specs, separation


def _terminals(specs):
    pts = []
    for s in specs:
        pts += [(s.emc_class, surface_point(*s.start_xt, main.PARAMS.radius)),
                (s.emc_class, surface_point(*s.end_xt, main.PARAMS.radius))]
    return pts


def test_perturbation_keeps_terminals_separable():
    rng = np.random.default_rng(0)
    for _ in range(50):
        pts = _terminals(perturb_specs(SCENARIO_SPECS, rng))
        for (ca, pa), (cb, pb) in itertools.combinations(pts, 2):
            if ca != cb:
                assert np.linalg.norm(pa - pb) > separation(ca, cb)


def test_robustness_rows(graph, volumes):
    settings = CheckSettings(volumes, separation, main.MIN_BEND_RADIUS_M, main.CAPACITY_K, main.CLEARANCE_M)
    rows = run_robustness(graph, SCENARIO_SPECS, main.PARAMS.radius,
                          {"a": lambda cs: route_baseline(graph, cs)}, settings, n_trials=2)
    assert [r["family"] for r in rows] == ["Rastgele sıra", "Rastgele sıra + uç nokta sapması"]
    for r in rows:
        assert r["trials"] == 2 and 0 <= r["emc_zero"] <= 2 and 0 <= r["all_clean"] <= 2
    assert format_robustness_markdown(rows).count("\n") == 1 + len(rows)
