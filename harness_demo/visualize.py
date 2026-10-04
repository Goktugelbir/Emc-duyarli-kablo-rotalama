"""2D charts (plotly): Lagrangian convergence and the per-method metrics chart.

The 3D images are rendered from the interactive three.js page, see `capture.py`.
"""

from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Categorical slots 1-3 of a colour-blind-validated palette; red is reserved for keep-out volumes.
CLASS_COLORS: dict[str, str] = {"power": "#eb6834", "signal": "#2a78d6", "data": "#1baf7a"}
BAR_COLOR = "#2a78d6"
SURFACE = "#fcfcfb"
GRID = "#e6e5e0"
TEXT = "#0b0b0b"
TEXT_SECONDARY = "#52514e"

SHORT_LABELS: dict[str, str] = {
    "baseline": "a) Baseline",
    "bundled": "b) Demetleme",
    "emc_aware": "c) EMC duyarlı",
    "lagrangian": "d) Lagrange",
    "integrated": "e) Bütünleşik",
}


def plot_convergence(history: list[dict[str, float]], png_path: Path) -> None:
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
        title={"text": f"Lagrange gevşetmesi yakınsaması — son fark %{gap:.3f}", "x": 0.02},
        xaxis={"title": "İterasyon", "gridcolor": GRID},
        yaxis={"title": "Toplam kablo uzunluğu [m]", "gridcolor": GRID},
        plot_bgcolor=SURFACE, paper_bgcolor=SURFACE,
        legend={"x": 0.98, "y": 0.05, "xanchor": "right", "yanchor": "bottom"},
        hovermode="x unified",
        margin={"l": 70, "r": 20, "t": 50, "b": 60},
    )
    fig.write_image(png_path, width=900, height=500, scale=1)


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
              "textfont": {"color": TEXT, "size": 15}}
    fig.add_trace(go.Bar(y=labels, x=ratio, text=[f"{v:.3f}" for v in ratio], **common), row=1, col=1)
    fig.add_trace(go.Bar(y=labels, x=emc, text=[f"{v}" for v in emc], **common), row=1, col=2)
    fig.add_trace(go.Bar(y=labels, x=cap, text=[f"{v}" for v in cap], **common), row=1, col=3)
    fig.update_yaxes(autorange="reversed", tickfont={"size": 15, "color": TEXT}, ticklabelstandoff=12)
    fig.update_xaxes(gridcolor=GRID, zeroline=True, zerolinecolor="#c3c2b7",
                     tickfont={"color": TEXT_SECONDARY, "size": 13})
    fig.update_xaxes(range=[0, 1.0], row=1, col=1)
    fig.update_xaxes(range=[0, max(emc) * 1.2 if max(emc) else 1], row=1, col=2)
    fig.update_xaxes(range=[0, max(cap) * 1.2 if max(cap) else 1], row=1, col=3)
    fig.update_layout(
        title={"text": f"Yöntemlerin karşılaştırması (aynı senaryo, {len(rows)} yöntem)", "x": 0.02,
               "font": {"size": 20, "color": TEXT}},
        bargap=0.35, plot_bgcolor=SURFACE, paper_bgcolor=SURFACE,
        margin={"l": 20, "r": 40, "t": 90, "b": 40},
    )
    fig.update_annotations(font={"size": 16, "color": TEXT_SECONDARY})
    fig.write_image(png_path, width=1800, height=560, scale=1)
