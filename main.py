"""End-to-end demo: geometry -> graph -> scenario -> 4 routing methods -> checks -> metrics -> plots."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import kaleido
import trimesh

from harness_demo.checks import emc_violation_points, run_all_checks
from harness_demo.geometry import ForbiddenVolume, FuselageParams, build_fuselage, default_forbidden_volumes
from harness_demo.graph import RoutingGraph, build_routing_graph
from harness_demo.metrics import compute_metrics, format_console_table, format_markdown_table
from harness_demo.routing import RoutingResult, route_baseline, route_bundled, route_emc_aware, route_lagrangian
from harness_demo.scenarios import Cable, build_scenario, separation
from harness_demo.presentation import (
    plot_comparison,
    plot_metrics_chart,
    render_rotation_gif,
    write_interactive_page,
)
from harness_demo.visualize import plot_convergence, plot_routes

OUT_DIR = Path(__file__).parent / "outputs"
DOCS_DIR = Path(__file__).parent / "docs"

# Representative parameters (see README).
PARAMS = FuselageParams()  # R = 2 m, L = 6 m, seed = 42
CAPACITY_K = 2  # max cables per edge (deliberately tight so the constraint is active)
MIN_BEND_RADIUS_M = 0.10
REUSE_FACTOR = 0.4  # cost multiplier on already used edges
EMC_PENALTY = 20.0  # extra cost (x edge length) near routes of other EMC classes
LAGRANGE_ITERATIONS = 60


def main() -> None:
    """Run the full pipeline and write all outputs."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    t_start = time.perf_counter()
    OUT_DIR.mkdir(exist_ok=True)
    kaleido.start_sync_server(n=4, silence_warnings=True)  # one headless browser (4 tabs) for all exports

    mesh = build_fuselage(PARAMS)
    volumes = default_forbidden_volumes(PARAMS.radius)
    graph = build_routing_graph(mesh, volumes)
    cables = build_scenario(graph, PARAMS.radius)
    print(
        f"Mesh: {len(mesh.vertices)} köşe, {len(mesh.faces)} üçgen | "
        f"Çizge: {graph.nx_graph.number_of_nodes()} düğüm, {graph.n_edges} ayrıt | "
        f"{len(mesh.vertices) - graph.nx_graph.number_of_nodes()} düğüm yasak hacimler nedeniyle çıkarıldı | "
        f"{len(cables)} kablo"
    )

    results = [
        route_baseline(graph, cables),
        route_bundled(graph, cables, reuse_factor=REUSE_FACTOR),
        route_emc_aware(graph, cables, separation, reuse_factor=REUSE_FACTOR, emc_penalty=EMC_PENALTY),
        route_lagrangian(graph, cables, capacity=CAPACITY_K, iterations=LAGRANGE_ITERATIONS),
    ]

    rows = []
    for res in results:
        paths = [res.routes[c.name] for c in cables]
        report = run_all_checks(
            paths, [c.emc_class for c in cables], graph.positions, volumes, separation, MIN_BEND_RADIUS_M, CAPACITY_K
        )
        rows.append(compute_metrics(res, graph, report))
        plot_routes(
            mesh, volumes, cables, res.routes, res.label,
            OUT_DIR / f"routes_{res.method}.html", OUT_DIR / f"routes_{res.method}.png",
        )

    lagr = results[-1]
    plot_convergence(lagr.history, OUT_DIR / "lagrangian_convergence.png", OUT_DIR / "lagrangian_convergence.html")
    write_presentation(mesh, volumes, cables, graph, results, rows)
    last = lagr.history[-1]

    print()
    print(format_console_table(rows))
    print(
        f"\nLagrange: {len(lagr.history)} iterasyon, alt sınır {last['lower_bound']:.2f} m, "
        f"üst sınır {last['upper_bound']:.2f} m, fark %{(last['upper_bound'] - last['lower_bound']) / last['upper_bound'] * 100:.2f}"
    )

    md = [
        "# Metrikler",
        "",
        format_markdown_table(rows),
        "",
        f"- Kapasite K = {CAPACITY_K} kablo/ayrıt, minimum bükülme yarıçapı = {MIN_BEND_RADIUS_M} m, "
        f"EMC ve yasak hacim denetimleri {0.05} m örnekleme ile.",
        f"- Lagrange: {len(lagr.history)} iterasyon, alt sınır {last['lower_bound']:.2f} m, "
        f"üst sınır {last['upper_bound']:.2f} m.",
        "",
    ]
    (OUT_DIR / "metrics.md").write_text("\n".join(md), encoding="utf-8")
    (OUT_DIR / "lagrangian_history.json").write_text(json.dumps(lagr.history, indent=1), encoding="utf-8")
    print(f"\nÇıktılar: {OUT_DIR}  (toplam süre {time.perf_counter() - t_start:.1f} s)")


def write_presentation(
    mesh: trimesh.Trimesh,
    volumes: list[ForbiddenVolume],
    cables: list[Cable],
    graph: RoutingGraph,
    results: list[RoutingResult],
    rows: list[dict[str, object]],
) -> None:
    """Comparison image, rotating GIF, metric chart and the interactive GitHub Pages page."""
    by_method = {r.method: (r, row) for r, row in zip(results, rows)}
    classes = [c.emc_class for c in cables]

    panels = []
    for method, name in (("bundled", "Demetleme"), ("emc_aware", "EMC duyarlı")):
        res, row = by_method[method]
        pts = emc_violation_points([graph.positions[res.routes[c.name]] for c in cables], classes, separation)
        assert len(pts) == row["emc_points"], "violation points must match the reported metric"
        n = int(row["emc_points"])
        panels.append((res.routes, f"{name} — EMC ihlali: {n} nokta" if n else f"{name} — EMC ihlali: 0", pts))
    plot_comparison(mesh, volumes, cables, panels, OUT_DIR / "comparison.png")

    plot_metrics_chart(rows, OUT_DIR / "metrics_chart.png")

    emc_res = by_method["emc_aware"][0]
    render_rotation_gif(mesh, volumes, cables, emc_res.routes, emc_res.label, OUT_DIR / "demo.gif")

    write_interactive_page(mesh, volumes, cables, results, rows, DOCS_DIR / "index.html")


if __name__ == "__main__":
    try:
        main()
    finally:
        kaleido.stop_sync_server(silence_warnings=True)
