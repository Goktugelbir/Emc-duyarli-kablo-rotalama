"""Industrial export functions for cable harness wirelists and 3D route coordinates.

Generates:
- CSV wirelist (production harness schedule: terminals, length, waypoints, bundling)
- JSON routes (complete 3D centerline splines / waypoints per cable for CAD/ECAD ingest)
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Sequence

import numpy as np

from .graph import RoutingGraph
from .routing import RoutingResult
from .scenarios import Cable


def generate_wirelist_records(
    graph: RoutingGraph,
    cables: Sequence[Cable],
    routes: dict[str, list[int]],
) -> list[dict[str, object]]:
    """Compute production wirelist records for each routed cable."""
    # Map each undirected edge to the list of cable names using it
    edge_to_cables: dict[int, list[str]] = {}
    for cable in cables:
        path = routes[cable.name]
        for eid in np.unique(graph.path_edge_ids(path)):
            edge_to_cables.setdefault(int(eid), []).append(cable.name)

    records = []
    pos = graph.positions

    for cable in cables:
        path = routes[cable.name]
        length = float(graph.path_length(path))
        eids = graph.path_edge_ids(path)

        shared_with: set[str] = set()
        shared_length = 0.0

        for eid in eids:
            sharing = edge_to_cables.get(int(eid), [])
            if len(sharing) > 1:
                shared_length += float(graph.lengths[eid])
                for other in sharing:
                    if other != cable.name:
                        shared_with.add(other)

        start_pt = pos[cable.start]
        end_pt = pos[cable.end]

        sharing_ratio = (shared_length / length) if length > 1e-9 else 0.0

        records.append({
            "cable_name": cable.name,
            "emc_class": cable.emc_class,
            "from_node": cable.start,
            "from_x_m": round(float(start_pt[0]), 4),
            "from_y_m": round(float(start_pt[1]), 4),
            "from_z_m": round(float(start_pt[2]), 4),
            "to_node": cable.end,
            "to_x_m": round(float(end_pt[0]), 4),
            "to_y_m": round(float(end_pt[1]), 4),
            "to_z_m": round(float(end_pt[2]), 4),
            "length_m": round(length, 4),
            "waypoint_count": len(path),
            "bundled_with": ";".join(sorted(shared_with)) if shared_with else "none",
            "shared_length_m": round(shared_length, 4),
            "sharing_ratio": round(sharing_ratio, 3),
        })

    return records


def export_wirelist_csv(records: list[dict[str, object]], csv_path: Path) -> None:
    """Write wirelist records to a standard CSV file."""
    if not records:
        return
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(records[0].keys())
    with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def export_routes_json(
    graph: RoutingGraph,
    cables: Sequence[Cable],
    results: Sequence[RoutingResult] | RoutingResult,
    json_path: Path,
) -> None:
    """Export 3D waypoint coordinates and wirelist metadata to JSON."""
    json_path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(results, RoutingResult):
        results_list = [results]
    else:
        results_list = list(results)

    pos = graph.positions
    data: dict[str, object] = {
        "description": "EMC-aware cable harness 3D routing centerline export",
        "units": "meters",
        "methods": {},
    }

    for res in results_list:
        records = generate_wirelist_records(graph, cables, res.routes)
        records_by_name = {r["cable_name"]: r for r in records}

        cables_data = []
        for cable in cables:
            path = res.routes[cable.name]
            rec = records_by_name[cable.name]
            waypoints = np.round(pos[path], 4).tolist()

            cables_data.append({
                "name": cable.name,
                "emc_class": cable.emc_class,
                "length_m": rec["length_m"],
                "waypoint_count": rec["waypoint_count"],
                "start_node": cable.start,
                "end_node": cable.end,
                "bundled_with": rec["bundled_with"].split(";") if rec["bundled_with"] != "none" else [],
                "shared_length_m": rec["shared_length_m"],
                "sharing_ratio": rec["sharing_ratio"],
                "node_ids": [int(n) for n in path],
                "waypoints_xyz": waypoints,
            })

        data["methods"][res.method] = {
            "label": res.label,
            "runtime_s": round(res.runtime_s, 4),
            "cables": cables_data,
        }

    with open(json_path, mode="w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
