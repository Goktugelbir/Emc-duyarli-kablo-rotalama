"""Presentation outputs: side-by-side comparison, rotating GIF, metric chart, interactive web page.

Every number shown here is passed in from the pipeline (metrics rows / check results);
nothing is hard-coded.
"""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import plotly.io as pio
import trimesh
from plotly.subplots import make_subplots
from PIL import Image

from .geometry import ForbiddenVolume, SphereVolume
from .routing import RoutingResult
from .scenarios import Cable, separation
from .visualize import (
    CAMERA,
    CLASS_COLORS,
    DISPLAY_OFFSET_BASE_M,
    FORBIDDEN_COLOR,
    HULL_COLOR,
    SCENE_AXES,
    context_traces,
    offset_inward,
    route_traces,
)

VIOLATION_COLOR = "#b5001f"  # deep red, darker than the translucent keep-out volumes
BAR_COLOR = "#2a78d6"
SURFACE = "#fcfcfb"
GRID = "#e6e5e0"
TEXT_SECONDARY = "#52514e"

SHORT_LABELS: dict[str, str] = {
    "baseline": "a) Baseline",
    "bundled": "b) Demetleme",
    "emc_aware": "c) EMC duyarlı",
    "lagrangian": "d) Lagrange",
    "integrated": "e) Bütünleşik",
}


# Exporting several 3D scenes in one figure is unreliable in headless WebGL (only the first scene
# renders correctly), so every 3D view below is exported as its own single-scene figure; the
# finished PNGs are then only placed side by side / appended as GIF frames with Pillow.


def _violation_trace(points: np.ndarray) -> go.Scatter3d:
    """Marker trace for EMC violation points (duplicates removed, lifted like the cable lines)."""
    pts = np.unique(np.round(points, 6), axis=0) if len(points) else np.empty((0, 3))
    pts = offset_inward(pts, DISPLAY_OFFSET_BASE_M) if len(pts) else pts
    return go.Scatter3d(
        x=pts[:, 0], y=pts[:, 1], z=pts[:, 2], mode="markers",
        marker={"size": 2.5, "color": VIOLATION_COLOR, "symbol": "x"},
        name="EMC ihlali noktası", showlegend=False, hoverinfo="skip",
    )


def _scene_figure(
    mesh: trimesh.Trimesh,
    volumes: list[ForbiddenVolume],
    cables: list[Cable],
    routes: dict[str, list[int]],
    extra: list[go.Scatter3d] | None = None,
) -> go.Figure:
    """Single 3D scene without legend, used for comparison panels and GIF frames."""
    fig = go.Figure(context_traces(mesh, volumes, showlegend=False)
                    + route_traces(mesh, cables, routes, showlegend=False) + (extra or []))
    fig.update_layout(
        scene={"aspectmode": "data", "camera": CAMERA, **SCENE_AXES},
        showlegend=False, margin={"l": 0, "r": 0, "t": 0, "b": 0}, paper_bgcolor=SURFACE,
    )
    return fig


def _legend_strip(title: str, include_violation: bool) -> go.Figure:
    """2D-only header figure carrying the title and the colour key (no WebGL involved)."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", name="Gövde",
                             marker={"symbol": "square", "size": 14, "color": HULL_COLOR, "opacity": 0.5}))
    fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", name="Yasak hacim",
                             marker={"symbol": "square", "size": 14, "color": FORBIDDEN_COLOR, "opacity": 0.6}))
    for name, color in CLASS_COLORS.items():
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="lines", name=name, line={"color": color, "width": 4}))
    if include_violation:
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", name="EMC ihlali noktası",
                                 marker={"symbol": "x", "size": 11, "color": VIOLATION_COLOR}))
    fig.update_layout(
        title={"text": title, "x": 0.5, "y": 0.82, "yanchor": "top", "font": {"size": 22, "color": "#0b0b0b"}},
        legend={"orientation": "h", "x": 0.5, "xanchor": "center", "y": 0.05, "yanchor": "bottom",
                "font": {"size": 16, "color": "#0b0b0b"}},
        xaxis={"visible": False}, yaxis={"visible": False},
        plot_bgcolor=SURFACE, paper_bgcolor=SURFACE, margin={"l": 0, "r": 0, "t": 0, "b": 0},
    )
    return fig


def plot_comparison(
    mesh: trimesh.Trimesh,
    volumes: list[ForbiddenVolume],
    cables: list[Cable],
    panels: list[tuple[dict[str, list[int]], str, np.ndarray]],
    png_path: Path,
    panel_size: tuple[int, int] = (900, 680),
    scale: float = 1.5,
) -> None:
    """Side-by-side 3D panels (same camera, same colours) with EMC violation markers.

    `panels` holds (routes, caption, violation_points) per panel; the caption is drawn
    under each panel and a shared title/legend strip on top.
    """
    pw, ph = panel_size
    title = "Aynı senaryo, aynı kamera: bütünleşik rotalama EMC, kapasite ve bükülme ihlallerini ortadan kaldırıyor"
    figs = [_legend_strip(title, include_violation=True)]
    for routes, caption, violations in panels:
        fig = _scene_figure(mesh, volumes, cables, routes, [_violation_trace(violations)])
        fig.update_layout(margin={"b": 60})
        fig.add_annotation(text=f"<b>{caption}</b>", x=0.5, y=0.0, xref="paper", yref="paper", yanchor="top",
                           yshift=-12, showarrow=False, font={"size": 20, "color": "#0b0b0b"})
        figs.append(fig)

    sizes = [(pw * len(panels), 130)] + [(pw, ph)] * len(panels)
    with tempfile.TemporaryDirectory() as tmp:
        paths = [Path(tmp) / f"part_{i}.png" for i in range(len(figs))]
        pio.write_images(figs, paths, width=[w for w, _ in sizes], height=[h for _, h in sizes], scale=scale)
        parts = [Image.open(p).convert("RGB") for p in paths]

    header, tiles = parts[0], parts[1:]
    sheet = Image.new("RGB", (sum(t.width for t in tiles), header.height + max(t.height for t in tiles)), SURFACE)
    sheet.paste(header, (0, 0))
    x = 0
    for t in tiles:
        sheet.paste(t, (x, header.height))
        x += t.width
    sheet.save(png_path, optimize=True)


def render_rotation_gif(
    mesh: trimesh.Trimesh,
    volumes: list[ForbiddenVolume],
    cables: list[Cable],
    routes: dict[str, list[int]],
    title: str,
    gif_path: Path,
    n_frames: int = 36,
    fps: int = 6,
    size: tuple[int, int] = (640, 440),
) -> None:
    """Looping 360° turntable GIF of one routing solution.

    The camera circles the vertical axis below the open floor, so it always looks up into
    the arch and the cables are never hidden behind the hull.
    """
    radius = math.hypot(CAMERA["eye"]["x"], CAMERA["eye"]["y"])
    height = CAMERA["eye"]["z"]
    a0 = math.atan2(CAMERA["eye"]["y"], CAMERA["eye"]["x"])
    hidden = {"visible": False}
    key = "   ".join(f'<span style="color:{c}">■</span> {name}' for name, c in CLASS_COLORS.items())
    key += f'   <span style="color:{FORBIDDEN_COLOR}">■</span> yasak hacim'

    base = _scene_figure(mesh, volumes, cables, routes)
    base.update_layout(scene={"xaxis": hidden, "yaxis": hidden, "zaxis": hidden})
    base.add_annotation(text=f"<b>{title}</b>", x=0.01, y=0.99, xref="paper", yref="paper", xanchor="left",
                        yanchor="top", showarrow=False, font={"size": 17, "color": "#0b0b0b"})
    base.add_annotation(text=key, x=0.01, y=0.01, xref="paper", yref="paper", xanchor="left", yanchor="bottom",
                        showarrow=False, font={"size": 14, "color": TEXT_SECONDARY})

    frames = []
    for i in range(n_frames):
        a = a0 + 2 * math.pi * i / n_frames
        f = go.Figure(base)
        f.update_layout(scene_camera={"eye": {"x": radius * math.cos(a), "y": radius * math.sin(a), "z": height},
                                      "up": CAMERA["up"]})
        frames.append(f)

    with tempfile.TemporaryDirectory() as tmp:
        paths = [Path(tmp) / f"frame_{i:03d}.png" for i in range(n_frames)]
        pio.write_images(frames, paths, width=size[0], height=size[1], scale=1)
        images = [Image.open(p).convert("RGB") for p in paths]

    # One shared palette for all frames avoids colour flicker between frames.
    palette = images[0].quantize(colors=96, method=Image.Quantize.MEDIANCUT)
    gif = [im.quantize(palette=palette, dither=Image.Dither.NONE) for im in images]
    gif[0].save(gif_path, save_all=True, append_images=gif[1:], duration=int(1000 / fps), loop=0, optimize=True)


def plot_metrics_chart(rows: list[dict[str, object]], png_path: Path) -> None:
    """Three bar panels: bundling ratio, EMC violation points and capacity violations per method."""
    labels = [SHORT_LABELS.get(str(r["method"]), str(r["label"])) for r in rows]
    ratio = [float(r["bundling_ratio"]) for r in rows]
    emc = [int(r["emc_points"]) for r in rows]
    cap = [int(r["capacity_edges"]) for r in rows]
    fig = make_subplots(
        rows=1, cols=3, horizontal_spacing=0.1,
        subplot_titles=("Demetlenme oranı  (yüksek = daha çok ortak yol)",
                        "EMC ihlali [nokta]  (düşük = iyi)",
                        "Kapasite ihlali [ayrıt]  (düşük = iyi)"),
    )
    common = {"orientation": "h", "marker": {"color": BAR_COLOR, "cornerradius": 4},
              "textposition": "outside", "cliponaxis": False, "showlegend": False,
              "textfont": {"color": "#0b0b0b", "size": 15}}
    fig.add_trace(go.Bar(y=labels, x=ratio, text=[f"{v:.3f}" for v in ratio], **common), row=1, col=1)
    fig.add_trace(go.Bar(y=labels, x=emc, text=[f"{v}" for v in emc], **common), row=1, col=2)
    fig.add_trace(go.Bar(y=labels, x=cap, text=[f"{v}" for v in cap], **common), row=1, col=3)
    fig.update_yaxes(autorange="reversed", tickfont={"size": 15, "color": "#0b0b0b"}, ticklabelstandoff=12)
    fig.update_xaxes(gridcolor=GRID, zeroline=True, zerolinecolor="#c3c2b7",
                     tickfont={"color": TEXT_SECONDARY, "size": 13})
    fig.update_xaxes(range=[0, 1.0], row=1, col=1)
    fig.update_xaxes(range=[0, max(emc) * 1.2 if max(emc) else 1], row=1, col=2)
    fig.update_xaxes(range=[0, max(cap) * 1.2 if max(cap) else 1], row=1, col=3)
    fig.update_layout(
        title={"text": f"Yöntemlerin karşılaştırması (aynı senaryo, {len(rows)} yöntem)", "x": 0.02, "font": {"size": 20, "color": "#0b0b0b"}},
        bargap=0.35, plot_bgcolor=SURFACE, paper_bgcolor=SURFACE,
        margin={"l": 20, "r": 40, "t": 90, "b": 40},
    )
    fig.update_annotations(font={"size": 16, "color": TEXT_SECONDARY})
    fig.write_image(png_path, width=1800, height=560, scale=1)


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
