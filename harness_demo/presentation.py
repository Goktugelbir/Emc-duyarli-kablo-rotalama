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
from plotly.offline import get_plotlyjs_version
from plotly.subplots import make_subplots
from PIL import Image

from .geometry import ForbiddenVolume
from .routing import RoutingResult
from .scenarios import Cable
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
    title = "Aynı senaryo, aynı kamera: EMC ayrımını gözeten rotalama ihlalleri ortadan kaldırıyor"
    figs = [_legend_strip(title, include_violation=True)]
    for routes, caption, violations in panels:
        fig = _scene_figure(mesh, volumes, cables, routes, [_violation_trace(violations)])
        fig.update_layout(margin={"b": 60})
        fig.add_annotation(text=f"<b>{caption}</b>", x=0.5, y=0.0, xref="paper", yref="paper", yanchor="top",
                           yshift=-12, showarrow=False, font={"size": 24, "color": "#0b0b0b"})
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
    """Two bar panels: bundling ratio and EMC violation points per method."""
    labels = [SHORT_LABELS.get(str(r["method"]), str(r["label"])) for r in rows]
    ratio = [float(r["bundling_ratio"]) for r in rows]
    emc = [int(r["emc_points"]) for r in rows]
    fig = make_subplots(
        rows=1, cols=2, horizontal_spacing=0.14,
        subplot_titles=("Demetlenme oranı  (yüksek = daha çok ortak güzergâh)",
                        "EMC ihlali [nokta]  (düşük = daha iyi)"),
    )
    common = {"orientation": "h", "marker": {"color": BAR_COLOR, "cornerradius": 4},
              "textposition": "outside", "cliponaxis": False, "showlegend": False,
              "textfont": {"color": "#0b0b0b", "size": 15}}
    fig.add_trace(go.Bar(y=labels, x=ratio, text=[f"{v:.3f}" for v in ratio], **common), row=1, col=1)
    fig.add_trace(go.Bar(y=labels, x=emc, text=[f"{v}" for v in emc], **common), row=1, col=2)
    fig.update_yaxes(autorange="reversed", tickfont={"size": 15, "color": "#0b0b0b"}, ticklabelstandoff=12)
    fig.update_xaxes(gridcolor=GRID, zeroline=True, zerolinecolor="#c3c2b7",
                     tickfont={"color": TEXT_SECONDARY, "size": 13})
    fig.update_xaxes(range=[0, 1.0], row=1, col=1)
    fig.update_xaxes(range=[0, max(emc) * 1.15 if max(emc) else 1], row=1, col=2)
    fig.update_layout(
        title={"text": "Yöntemlerin karşılaştırması (aynı senaryo, 11 kablo)", "x": 0.02, "font": {"size": 20, "color": "#0b0b0b"}},
        bargap=0.35, plot_bgcolor=SURFACE, paper_bgcolor=SURFACE,
        margin={"l": 20, "r": 40, "t": 90, "b": 40},
    )
    fig.update_annotations(font={"size": 16, "color": TEXT_SECONDARY})
    fig.write_image(png_path, width=1600, height=520, scale=1)


_PAGE_TEMPLATE = """<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kablo Rotalama 3B</title>
<script src="https://cdn.plot.ly/plotly-__PLOTLYJS_VERSION__.min.js" charset="utf-8"></script>
<style>
  :root {
    color-scheme: light;
    --surface: #fcfcfb; --surface-2: #f1f0ec; --border: #dcdbd5;
    --text: #0b0b0b; --text-2: #52514e; --accent: #2a78d6;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--surface); color: var(--text);
         font: 15px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  main { max-width: 1200px; margin: 0 auto; padding: 24px 16px 40px; }
  h1 { font-size: 1.5rem; margin: 0 0 4px; }
  p.lead { margin: 0 0 20px; color: var(--text-2); }
  .tabs { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }
  .tabs button { font: inherit; padding: 8px 14px; border-radius: 8px; cursor: pointer;
                 border: 1px solid var(--border); background: var(--surface); color: var(--text); }
  .tabs button[aria-selected="true"] { background: var(--accent); border-color: var(--accent); color: #fff; }
  .tabs button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px; margin-bottom: 14px; }
  .stat { background: var(--surface-2); border-radius: 8px; padding: 10px 12px; }
  .stat .k { font-size: .8rem; color: var(--text-2); }
  .stat .v { font-size: 1.25rem; font-weight: 600; font-variant-numeric: tabular-nums; }
  #plot { width: 100%; height: min(72vh, 720px); border: 1px solid var(--border); border-radius: 8px; }
  footer { margin-top: 16px; font-size: .85rem; color: var(--text-2); }
</style>
</head>
<body>
<main>
  <h1>Kablo demeti rotalama — etkileşimli 3B görünüm</h1>
  <p class="lead">Yarım silindir gövde kesiti üzerinde 11 kablonun dört yöntemle rotalanması.
     Sürükleyerek döndürün, tekerlekle yakınlaşın, renklere göre EMC sınıfını izleyin.</p>
  <div class="tabs" role="tablist" id="tabs"></div>
  <div class="stats" id="stats" aria-live="polite"></div>
  <div id="plot"></div>
  <footer>Tüm değerler temsilîdir ve <code>python main.py</code> çıktısından üretilmiştir.
    Gerçek uçak verisi kullanılmamıştır. Kırmızı yarı saydam hacimler yasak bölgelerdir.</footer>
</main>
<script>
const FIG = __FIGURE_JSON__;
const METHODS = __METHODS_JSON__;
const N_CONTEXT = __N_CONTEXT__;
const N_TRACES = FIG.data.length;

function visibility(active) {
  const vis = new Array(N_TRACES).fill(false);
  for (let i = 0; i < N_CONTEXT; i++) vis[i] = true;
  const m = METHODS.find(x => x.key === active);
  for (let i = m.first; i < m.last; i++) vis[i] = true;
  return vis;
}
function renderStats(m) {
  const items = [
    ["Toplam uzunluk", m.total_length_m.toFixed(2) + " m"],
    ["Benzersiz uzunluk", m.unique_length_m.toFixed(2) + " m"],
    ["Demetlenme oranı", m.bundling_ratio.toFixed(3)],
    ["EMC ihlali", m.emc_points + " nokta"],
    ["Bükülme ihlali", String(m.bend_points)],
    ["Kapasite ihlali", m.capacity_edges + " ayrıt"],
  ];
  document.getElementById("stats").innerHTML = items
    .map(([k, v]) => `<div class="stat"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");
}
function select(key) {
  document.querySelectorAll("#tabs button").forEach(b =>
    b.setAttribute("aria-selected", String(b.dataset.key === key)));
  Plotly.restyle("plot", { visible: visibility(key) });
  renderStats(METHODS.find(x => x.key === key));
}
const tabs = document.getElementById("tabs");
METHODS.forEach(m => {
  const b = document.createElement("button");
  b.type = "button"; b.setAttribute("role", "tab"); b.dataset.key = m.key; b.textContent = m.label;
  b.addEventListener("click", () => select(m.key));
  tabs.appendChild(b);
});
FIG.data.forEach((t, i) => { t.visible = i < N_CONTEXT; });
Plotly.newPlot("plot", FIG.data, FIG.layout, { responsive: true, displaylogo: false })
  .then(() => select(METHODS[__INITIAL__].key));
</script>
</body>
</html>
"""


def write_interactive_page(
    mesh: trimesh.Trimesh,
    volumes: list[ForbiddenVolume],
    cables: list[Cable],
    results: list[RoutingResult],
    rows: list[dict[str, object]],
    html_path: Path,
    initial: str = "emc_aware",
) -> None:
    """Single self-contained page (plotly.js from CDN) with one tab per routing method."""
    context = context_traces(mesh, volumes)
    fig = go.Figure(context)
    methods = []
    for res, row in zip(results, rows):
        first = len(fig.data)
        for t in route_traces(mesh, cables, res.routes):
            fig.add_trace(t)
        methods.append({
            "key": res.method, "label": res.label, "first": first, "last": len(fig.data),
            **{k: row[k] for k in ("total_length_m", "unique_length_m", "bundling_ratio",
                                   "emc_points", "bend_points", "capacity_edges")},
        })
    fig.update_layout(
        scene={"aspectmode": "data", "camera": CAMERA, **SCENE_AXES},
        legend={"x": 0.99, "y": 0.97, "xanchor": "right", "bgcolor": "rgba(252,252,251,0.85)"},
        margin={"l": 0, "r": 0, "t": 0, "b": 0}, paper_bgcolor=SURFACE,
    )
    page = (
        _PAGE_TEMPLATE.replace("__PLOTLYJS_VERSION__", get_plotlyjs_version())
        .replace("__FIGURE_JSON__", fig.to_json())
        .replace("__METHODS_JSON__", json.dumps(methods, ensure_ascii=False))
        .replace("__N_CONTEXT__", str(len(context)))
        .replace("__INITIAL__", str(next(i for i, m in enumerate(methods) if m["key"] == initial)))
    )
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(page, encoding="utf-8")
