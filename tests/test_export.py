"""Exports: wirelist CSV (with verification margins) and the compact, deterministic routes JSON."""

from __future__ import annotations

import csv
import json

import pytest

import main
from harness_demo.checks import CheckSettings
from harness_demo.export import (
    WIRELIST_COLUMNS,
    export_routes_json,
    export_wirelist_csv,
    generate_wirelist_records,
)
from harness_demo.scenarios import separation


@pytest.fixture(scope="module")
def settings(volumes):
    return CheckSettings(volumes, separation, main.MIN_BEND_RADIUS_M, main.CAPACITY_K, main.CLEARANCE_M)


def test_wirelist_records(graph, cables, results, settings):
    records = generate_wirelist_records(graph, cables, results["integrated"].routes, settings)
    assert [r["cable_name"] for r in records] == [c.name for c in cables]
    assert [r["wire_id"] for r in records] == [f"W{k:02d}" for k in range(1, len(cables) + 1)]
    for r, c in zip(records, cables):
        assert tuple(r) == WIRELIST_COLUMNS
        assert r["length_m"] > 0 and r["waypoint_count"] >= 2
        assert 0.0 <= r["sharing_ratio"] <= 1.0
        assert (r["from_location"], r["to_location"]) == (c.from_location, c.to_location)
        assert c.name not in r["bundled_with"]


def test_wirelist_margins_agree_with_independent_checks(graph, cables, results, metrics, settings):
    """A cable is flagged exactly when the independent checks find a violation on the route set."""
    clean = generate_wirelist_records(graph, cables, results["integrated"].routes, settings)
    assert all(r["status"] == "OK" for r in clean)
    assert all(r["min_emc_margin_m"] >= 0 and r["min_bend_radius_m"] >= main.MIN_BEND_RADIUS_M
               and r["min_keepout_distance_m"] >= main.CLEARANCE_M for r in clean)

    bundled = generate_wirelist_records(graph, cables, results["bundled"].routes, settings)
    assert metrics["bundled"]["emc_points"] > 0
    assert any(r["min_emc_margin_m"] < 0 for r in bundled)
    assert all((r["status"] == "CHECK") == (r["min_emc_margin_m"] < 0 or r["min_bend_radius_m"] < 0.1)
               for r in bundled)


def test_wirelist_csv(tmp_path, graph, cables, results, settings):
    path = tmp_path / "wirelist.csv"
    export_wirelist_csv(generate_wirelist_records(graph, cables, results["integrated"].routes, settings), path)
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len(cables)
    assert tuple(rows[0]) == WIRELIST_COLUMNS
    assert rows[0]["bundled_with"] == "P2"  # P1 and P2 share their route


def test_routes_json_is_compact_complete_and_deterministic(tmp_path, graph, cables, results, metrics):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    rows = list(metrics.values())
    export_routes_json(graph, cables, list(results.values()), a, rows=rows, parameters={"capacity_k": 2})
    export_routes_json(graph, cables, list(results.values()), b, rows=rows, parameters={"capacity_k": 2})
    assert a.read_bytes() == b.read_bytes()  # no timings or other run-dependent values

    text = a.read_text(encoding="utf-8")
    assert len(text.splitlines()) < 1000  # arrays stay on one line
    data = json.loads(text)
    assert data["units"] == "m" and data["parameters"]["capacity_k"] == 2
    assert set(data["methods"]) == set(results)
    for key, m in data["methods"].items():
        assert m["checks"]["emc_points"] == metrics[key]["emc_points"]
        assert isinstance(m["checks"]["emc_points"], int)
        for c in m["cables"]:
            assert len(c["waypoints_xyz"]) == len(c["node_ids"]) == len(results[key].routes[c["name"]])
            assert all(len(p) == 3 for p in c["waypoints_xyz"])
