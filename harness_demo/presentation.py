"""Interactive web page: the three.js viewer with the routing results embedded as JSON.

The viewer source lives in `harness_demo/viewer/` (template.html, viewer.css, viewer.js); it is
assembled here into one self-contained page, so docs/index.html works from GitHub Pages and from
the file system alike. Every number shown on the page is passed in from the pipeline (metrics rows,
check results); nothing is hard-coded. The README's 3D images are rendered from this page (`capture.py`).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import trimesh

from .geometry import ForbiddenVolume, SphereVolume
from .metrics import Row
from .routing import RoutingResult
from .scenarios import Cable, separation
from .visualize import CLASS_COLORS

VIEWER_DIR = Path(__file__).with_name("viewer")
THREE_VERSION = "0.169.0"


def assemble_page(data_json: str) -> str:
    """Viewer template with its stylesheet, script, three.js version and data inlined."""
    parts = {name: (VIEWER_DIR / name).read_text(encoding="utf-8")
             for name in ("template.html", "viewer.css", "viewer.js")}
    return (
        parts["template.html"]
        .replace("__STYLE__", parts["viewer.css"])
        .replace("__SCRIPT__", parts["viewer.js"])
        .replace("__THREE_VERSION__", THREE_VERSION)
        .replace("__DATA_JSON__", data_json)
    )


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
    rows: list[Row],
    violations: dict[str, np.ndarray],
    html_path: Path,
    radius: float,
    length: float,
    clearance: float = 0.0,
    initial: str = "integrated",
    margins: dict[str, dict[str, dict[str, object]]] | None = None,
    min_bend_radius: float = 0.0,
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
            "margins": (margins or {}).get(res.method, {}),
            **{k: row[k] for k in ("total_length_m", "unique_length_m", "bundling_ratio", "emc_points",
                                   "bend_points", "forbidden_points", "clearance_points", "capacity_edges",
                                   "runtime_s")},
        })
    classes = sorted({c.emc_class for c in cables}, key=list(CLASS_COLORS).index)
    data = {
        "radius": radius, "length": length, "clearance": clearance, "minBendRadius": min_bend_radius,
        "mesh": {"v": _flat(pos, 4), "f": np.asarray(mesh.faces, dtype=int).ravel().tolist()},
        "volumes": [_volume_spec(v) for v in volumes],
        "cables": [{"name": c.name, "cls": c.emc_class, "start": c.start, "end": c.end,
                    "from": c.from_location, "to": c.to_location} for c in cables],
        "classColors": CLASS_COLORS,
        "separation": {f"{a}|{b}": separation(a, b) for a in classes for b in classes},
        "methods": methods,
        "initial": initial if any(m["key"] == initial for m in methods) else methods[0]["key"],
    }
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = assemble_page(payload)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(page, encoding="utf-8")
