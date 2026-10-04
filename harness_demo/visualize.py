"""3D route visualisation and Lagrangian convergence plot (plotly)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import trimesh

from .geometry import ForbiddenVolume
from .scenarios import Cable

# Categorical slots 1-3 of a colour-blind-validated palette; red is reserved for keep-out volumes.
CLASS_COLORS: dict[str, str] = {"power": "#eb6834", "signal": "#2a78d6", "data": "#1baf7a"}
FORBIDDEN_COLOR = "#e34948"
HULL_COLOR = "#9a9890"
DISPLAY_OFFSET_BASE_M = 0.02  # visual-only lift off the hull, avoids z-fighting with the mesh faces
DISPLAY_OFFSET_STEP_M = 0.004  # extra visual-only offset per cable so bundled cables stay visible

CAMERA = {"eye": {"x": -0.9, "y": -0.8, "z": -1.5}, "up": {"x": 0, "y": 0, "z": 1}}


def _mesh_trace(mesh: trimesh.Trimesh, color: str, opacity: float, name: str) -> go.Mesh3d:
    """Plotly Mesh3d trace for a trimesh object."""
    v, f = mesh.vertices, mesh.faces
    return go.Mesh3d(
        x=v[:, 0], y=v[:, 1], z=v[:, 2], i=f[:, 0], j=f[:, 1], k=f[:, 2],
        color=color, opacity=opacity, name=name, showlegend=True, hoverinfo="name",
        flatshading=True,
    )


def offset_inward(points: np.ndarray, offset: float) -> np.ndarray:
    """Shift points radially towards the cylinder axis (x axis) by `offset`."""
    radial = points.copy()
    radial[:, 0] = 0.0
    norm = np.linalg.norm(radial, axis=1, keepdims=True)
    return points - offset * radial / np.maximum(norm, 1e-9)


SCENE_AXES: dict[str, dict] = {"xaxis": {"title": "x [m]"}, "yaxis": {"title": "y [m]"}, "zaxis": {"title": "z [m]"}}


def context_traces(mesh: trimesh.Trimesh, volumes: list[ForbiddenVolume], scene: str = "scene",
                   showlegend: bool = True) -> list[go.Mesh3d]:
    """Hull and keep-out volume traces shared by every route view."""
    traces = [_mesh_trace(mesh, HULL_COLOR, 0.18, "Gövde")]
    traces += [_mesh_trace(vol.to_mesh(), FORBIDDEN_COLOR, 0.45, f"Yasak: {vol.name}") for vol in volumes]
    for t in traces:
        t.update(scene=scene, showlegend=showlegend)
    return traces


def route_traces(mesh: trimesh.Trimesh, cables: list[Cable], routes: dict[str, list[int]],
                 scene: str = "scene", showlegend: bool = True) -> list[go.Scatter3d]:
    """One line trace plus one terminal-marker trace per cable, coloured by EMC class."""
    pos = np.asarray(mesh.vertices)
    traces: list[go.Scatter3d] = []
    shown: set[str] = set()
    for k, cable in enumerate(cables):
        pts = offset_inward(pos[routes[cable.name]], DISPLAY_OFFSET_BASE_M + DISPLAY_OFFSET_STEP_M * k)
        color = CLASS_COLORS[cable.emc_class]
        traces.append(
            go.Scatter3d(
                x=pts[:, 0], y=pts[:, 1], z=pts[:, 2], mode="lines", scene=scene,
                line={"color": color, "width": 5},
                name=cable.emc_class, legendgroup=cable.emc_class,
                showlegend=showlegend and cable.emc_class not in shown,
                hovertext=f"{cable.name} ({cable.emc_class})", hoverinfo="text",
            )
        )
        shown.add(cable.emc_class)
        ends = pts[[0, -1]]
        traces.append(
            go.Scatter3d(
                x=ends[:, 0], y=ends[:, 1], z=ends[:, 2], mode="markers", scene=scene,
                marker={"size": 4, "color": color, "line": {"color": "#ffffff", "width": 1}},
                legendgroup=cable.emc_class, showlegend=False,
                hovertext=[f"{cable.name} başlangıç", f"{cable.name} bitiş"], hoverinfo="text",
            )
        )
    return traces


def route_figure(mesh: trimesh.Trimesh, volumes: list[ForbiddenVolume], cables: list[Cable],
                 routes: dict[str, list[int]], title: str) -> go.Figure:
    """3D figure of one routing solution (hull, keep-out volumes, cables)."""
    fig = go.Figure(context_traces(mesh, volumes) + route_traces(mesh, cables, routes))
    fig.update_layout(
        title={"text": title, "x": 0.02},
        scene={"aspectmode": "data", "camera": CAMERA, **SCENE_AXES},
        legend={"x": 0.99, "y": 0.95, "xanchor": "right", "bgcolor": "rgba(252,252,251,0.85)"},
        margin={"l": 0, "r": 0, "t": 40, "b": 0},
        paper_bgcolor="#fcfcfb",
    )
    return fig


def plot_routes(
    mesh: trimesh.Trimesh,
    volumes: list[ForbiddenVolume],
    cables: list[Cable],
    routes: dict[str, list[int]],
    title: str,
    html_path: Path,
    png_path: Path,
) -> None:
    """Write an interactive HTML and a static PNG of one routing solution."""
    fig = route_figure(mesh, volumes, cables, routes, title)
    fig.write_html(html_path, include_plotlyjs="cdn")
    fig.write_image(png_path, width=1200, height=800, scale=1)


def plot_convergence(history: list[dict[str, float]], png_path: Path, html_path: Path | None = None) -> None:
    """Lower (dual) and upper (feasible) bound per subgradient iteration."""
    it = [h["iteration"] for h in history]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=it, y=[h["dual"] for h in history], mode="lines", name="L(λ) (iterasyon değeri)",
                             line={"color": "#2a78d6", "width": 1, "dash": "dot"}, opacity=0.6))
    fig.add_trace(go.Scatter(x=it, y=[h["lower_bound"] for h in history], mode="lines",
                             name="Alt sınır (en iyi dual)", line={"color": "#2a78d6", "width": 2}))
    fig.add_trace(go.Scatter(x=it, y=[h["upper_bound"] for h in history], mode="lines",
                             name="Üst sınır (en iyi uygun çözüm)", line={"color": "#eb6834", "width": 2}))
    last = history[-1]
    gap = (last["upper_bound"] - last["lower_bound"]) / last["upper_bound"] * 100
    fig.update_layout(
        title={"text": f"Lagrange gevşetmesi yakınsaması — son fark %{gap:.2f}", "x": 0.02},
        xaxis={"title": "İterasyon", "gridcolor": "#e6e5e0"},
        yaxis={"title": "Toplam kablo uzunluğu [m]", "gridcolor": "#e6e5e0"},
        plot_bgcolor="#fcfcfb", paper_bgcolor="#fcfcfb",
        legend={"x": 0.98, "y": 0.05, "xanchor": "right", "yanchor": "bottom"},
        hovermode="x unified",
        margin={"l": 70, "r": 20, "t": 50, "b": 60},
    )
    if html_path is not None:
        fig.write_html(html_path, include_plotlyjs="cdn")
    fig.write_image(png_path, width=900, height=500, scale=1)
