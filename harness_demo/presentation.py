"""Interactive web page: the routing results embedded as JSON in the three.js viewer template.

Every number shown on the page is passed in from the pipeline (metrics rows / check results);
nothing is hard-coded. The README's 3D images are rendered from this page, see `capture.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import trimesh

from .geometry import ForbiddenVolume, SphereVolume
from .routing import RoutingResult
from .scenarios import Cable, separation
from .visualize import CLASS_COLORS

VIEWER_TEMPLATE = Path(__file__).with_name("viewer_template.html")
THREE_VERSION = "0.169.0"


def _volume_spec(vol: ForbiddenVolume) -> dict[str, object]:
    """Plain-JSON description of a keep-out volume for the viewer."""
    if isinstance(vol, SphereVolume):
        return {"name": vol.name, "kind": "sphere", "center": list(vol.center), "radius": vol.radius, "prop": vol.prop}
    return {"name": vol.name, "kind": "box", "lo": list(vol.lo), "hi": list(vol.hi), "prop": vol.prop}


def _flat(a: np.ndarray, decimals: int) -> list[float]:
    """Rounded, flattened float list (keeps the embedded JSON small)."""
    return np.round(np.asarray(a, dtype=float), decimals).ravel().tolist()


def write_interactive_page(
    mesh: trimesh.Trimesh,
    volumes: list[ForbiddenVolume],
    cables: list[Cable],
    results: list[RoutingResult],
    rows: list[dict[str, object]],
    violations: dict[str, np.ndarray],
    html_path: Path,
    radius: float,
    length: float,
    clearance: float = 0.0,
    initial: str = "integrated",
) -> None:
    """Self-contained three.js page (library from CDN) with one tab per routing method.

    Only geometry, node paths, check results and metric rows are embedded; all realism
    (structure, clamps, connectors, smoothing, lighting) is added in the viewer and is visual-only.
    """
    pos = np.asarray(mesh.vertices)
    methods = []
    for res, row in zip(results, rows):
        routes = {c.name: [int(n) for n in res.routes[c.name]] for c in cables}
        lengths = {
            name: float(np.linalg.norm(np.diff(pos[path], axis=0), axis=1).sum()) for name, path in routes.items()
        }
        methods.append({
            "key": res.method, "label": res.label, "routes": routes, "lengths": lengths,
            "order": res.order or [c.name for c in cables],
            "violations": _flat(violations.get(res.method, np.empty((0, 3))), 3),
            **{k: row[k] for k in ("total_length_m", "unique_length_m", "bundling_ratio", "emc_points",
                                   "bend_points", "forbidden_points", "clearance_points", "capacity_edges",
                                   "runtime_s")},
        })
    classes = sorted({c.emc_class for c in cables}, key=list(CLASS_COLORS).index)
    data = {
        "radius": radius, "length": length, "clearance": clearance,
        "mesh": {"v": _flat(pos, 4), "f": np.asarray(mesh.faces, dtype=int).ravel().tolist()},
        "volumes": [_volume_spec(v) for v in volumes],
        "cables": [{"name": c.name, "cls": c.emc_class, "start": c.start, "end": c.end} for c in cables],
        "classColors": CLASS_COLORS,
        "separation": {f"{a}|{b}": separation(a, b) for a in classes for b in classes},
        "methods": methods,
        "initial": initial if any(m["key"] == initial for m in methods) else methods[0]["key"],
    }
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = (
        VIEWER_TEMPLATE.read_text(encoding="utf-8")
        .replace("__THREE_VERSION__", THREE_VERSION)
        .replace("__DATA_JSON__", payload)
    )
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(page, encoding="utf-8")
