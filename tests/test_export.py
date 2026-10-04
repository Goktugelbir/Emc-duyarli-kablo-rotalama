"""Tests for harness_demo/export.py: wirelist CSV and routes JSON exports."""

from __future__ import annotations

import csv
import json

from harness_demo.export import export_routes_json, export_wirelist_csv, generate_wirelist_records


def test_generate_wirelist_records(graph, cables, results):
    integrated = results["integrated"]
    records = generate_wirelist_records(graph, cables, integrated.routes)

    assert len(records) == len(cables)
    names = [r["cable_name"] for r in records]
    assert names == [c.name for c in cables]

    for r in records:
        assert r["length_m"] > 0
        assert r["waypoint_count"] >= 2
        assert 0.0 <= r["sharing_ratio"] <= 1.0
        assert r["from_node"] in range(graph.n_nodes)
        assert r["to_node"] in range(graph.n_nodes)


def test_export_wirelist_csv(tmp_path, graph, cables, results):
    csv_file = tmp_path / "wirelist.csv"
    integrated = results["integrated"]
    records = generate_wirelist_records(graph, cables, integrated.routes)
    export_wirelist_csv(records, csv_file)

    assert csv_file.is_file()
    with open(csv_file, mode="r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
    assert len(reader) == len(cables)
    assert set(reader[0].keys()) == {
        "cable_name", "emc_class", "from_node", "from_x_m", "from_y_m", "from_z_m",
        "to_node", "to_x_m", "to_y_m", "to_z_m", "length_m", "waypoint_count",
        "bundled_with", "shared_length_m", "sharing_ratio",
    }


def test_export_routes_json(tmp_path, graph, cables, results):
    json_file = tmp_path / "routes.json"
    integrated = results["integrated"]
    export_routes_json(graph, cables, integrated, json_file)

    assert json_file.is_file()
    with open(json_file, mode="r", encoding="utf-8") as f:
        data = json.load(f)

    assert "methods" in data
    assert "integrated" in data["methods"]
    method_data = data["methods"]["integrated"]
    assert len(method_data["cables"]) == len(cables)

    first_cable = method_data["cables"][0]
    assert "waypoints_xyz" in first_cable
    assert len(first_cable["waypoints_xyz"]) == first_cable["waypoint_count"]
    assert len(first_cable["waypoints_xyz"][0]) == 3
