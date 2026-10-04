"""End-to-end demo: geometry -> graph -> scenario -> 5 routing methods -> checks -> metrics -> plots.

Run `python main.py --help` for the options (e.g. `--no-images` skips PNG/GIF export, which
needs Chrome, and still writes the metrics, the robustness table and the interactive page).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import sys
import time
import warnings
from pathlib import Path

import trimesh

from harness_demo.benchmark import CheckSettings, format_robustness_markdown, run_robustness
from harness_demo.checks import emc_violation_points, run_all_checks
from harness_demo.geometry import ForbiddenVolume, FuselageParams, build_fuselage, default_forbidden_volumes
from harness_demo.graph import RoutingGraph, build_routing_graph
from harness_demo.metrics import compute_metrics, format_console_table, format_markdown_table
from harness_demo.routing import (
    RoutingResult,
    build_turn_graph,
    route_baseline,
    route_bundled,
    route_emc_aware,
    route_integrated,
    route_lagrangian,
)
from harness_demo.scenarios import SCENARIO_SPECS, Cable, build_scenario, separation
from harness_demo.presentation import write_interactive_page

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "outputs"
DOCS_DIR = ROOT / "docs"

# Representative parameters (see README).
PARAMS = FuselageParams()  # R = 2 m, L = 6 m, seed = 42
CAPACITY_K = 2  # max cables per edge (deliberately tight so the constraint is active)
MIN_BEND_RADIUS_M = 0.10
CLEARANCE_M = 0.05  # minimum distance between a route and a keep-out volume
REUSE_FACTOR = 0.4  # cost multiplier on already used edges
EMC_PENALTY = 20.0  # extra cost (x edge length) near routes of other EMC classes
LAGRANGE_ITERATIONS = 60
ROBUSTNESS_TRIALS = 20  # trials per robustness family
ROBUSTNESS_SEED = 7


class _Tee(io.TextIOBase):
    """Writes to the console and keeps a copy for outputs/run_log.txt."""

    def __init__(self, stream: io.TextIOBase) -> None:
        self.stream, self.buffer_text = stream, io.StringIO()

    def write(self, s: str) -> int:
        self.stream.write(s)
        self.buffer_text.write(s)
        return len(s)

    def flush(self) -> None:
        self.stream.flush()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Command-line options."""
    p = argparse.ArgumentParser(description="EMC duyarlı kablo demeti rotalama demosu: tüm çıktıları üretir.")
    p.add_argument("--no-images", action="store_true",
                   help="PNG/GIF üretme (Chrome/kaleido gerekmez); metrikler, sağlamlık tablosu ve sayfa yine yazılır")
    p.add_argument("--out", type=Path, default=OUT_DIR, help="çıktı klasörü (varsayılan: outputs/)")
    p.add_argument("--docs", type=Path, default=DOCS_DIR, help="etkileşimli sayfa klasörü (varsayılan: docs/)")
    p.add_argument("--trials", type=int, default=ROBUSTNESS_TRIALS,
                   help="sağlamlık testinde her deney ailesi için deneme sayısı; 0 = atla")
    p.add_argument("--capacity", type=int, default=CAPACITY_K, help="ayrıt kapasitesi K [kablo]")
    p.add_argument("--clearance", type=float, default=CLEARANCE_M, help="yasak hacim güvenlik payı [m]")
    return p.parse_args(argv)


def _display(path: Path) -> str:
    """Path relative to the repository when possible (keeps local paths out of run_log.txt)."""
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix() + "/"
    except ValueError:
        return path.name + "/"


def _finite(x: object) -> object:
    """JSON has no Infinity: unknown bounds are written as null."""
    return None if isinstance(x, float) and not math.isfinite(x) else x


def main(argv: list[str] | None = None) -> None:
    """Run the full pipeline and write all outputs."""
    args = parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    tee = _Tee(sys.stdout)
    with contextlib.redirect_stdout(tee):
        run(args)
    (args.out / "run_log.txt").write_text(tee.buffer_text.getvalue(), encoding="utf-8")


def run(args: argparse.Namespace) -> None:
    """Pipeline body (its console output is also written to run_log.txt)."""
    t_start = time.perf_counter()
    args.out.mkdir(parents=True, exist_ok=True)
    kaleido = None
    if not args.no_images:
        import kaleido

        # plotly warns that per-call kaleido options are ignored while a shared server runs; that is intended.
        warnings.filterwarnings("ignore", message="The kopts argument is ignored if using a server")
        kaleido.start_sync_server(n=1, silence_warnings=True)  # one headless browser for the 2D charts
    try:
        _run(args, t_start)
    finally:
        if kaleido is not None:
            kaleido.stop_sync_server(silence_warnings=True)


def _run(args: argparse.Namespace, t_start: float) -> None:
    mesh = build_fuselage(PARAMS)
    volumes = default_forbidden_volumes(PARAMS.radius)
    graph = build_routing_graph(mesh, volumes, clearance=args.clearance)
    cables = build_scenario(graph, PARAMS.radius)
    turns = build_turn_graph(graph, MIN_BEND_RADIUS_M)
    print(
        f"Mesh: {len(mesh.vertices)} köşe, {len(mesh.faces)} üçgen | "
        f"Çizge: {graph.nx_graph.number_of_nodes()} düğüm, {graph.n_edges} ayrıt | "
        f"{len(mesh.vertices) - graph.nx_graph.number_of_nodes()} düğüm yasak hacimler ve {args.clearance} m "
        f"güvenlik payı nedeniyle çıkarıldı | {len(cables)} kablo"
    )
    print(f"Dönüş çizgesi: {turns.n_states} yönlü ayrıt, {len(turns.arc_src)} izinli dönüş "
          f"(bükülme yarıçapı >= {MIN_BEND_RADIUS_M} m)")

    results = [
        route_baseline(graph, cables),
        route_bundled(graph, cables, reuse_factor=REUSE_FACTOR),
        route_emc_aware(graph, cables, separation, reuse_factor=REUSE_FACTOR, emc_penalty=EMC_PENALTY),
        route_lagrangian(graph, cables, capacity=args.capacity, iterations=LAGRANGE_ITERATIONS),
        route_integrated(graph, cables, separation, turns, args.capacity, reuse_factor=REUSE_FACTOR,
                         emc_penalty=EMC_PENALTY),
    ]

    def check(res: RoutingResult, cs: list[Cable], g: RoutingGraph = graph):
        return run_all_checks([res.routes[c.name] for c in cs], [c.emc_class for c in cs], g.positions, volumes,
                              separation, MIN_BEND_RADIUS_M, args.capacity, args.clearance)

    rows = [compute_metrics(res, graph, check(res, cables)) for res in results]

    # The clearance check is only meaningful if it fires when the margin is ignored: route the
    # baseline on a graph built without clearance and count how close it gets to the volumes.
    plain = build_routing_graph(mesh, volumes)
    plain_cables = build_scenario(plain, PARAMS.radius)
    no_margin = check(route_baseline(plain, plain_cables), plain_cables, plain).clearance_points

    lagr = next(r for r in results if r.method == "lagrangian")
    last = lagr.history[-1]
    print()
    print(format_console_table(rows))
    gap = last["upper_bound"] - last["lower_bound"]
    lagr_line = (f"Lagrange: {len(lagr.history)} iterasyon, alt sınır {last['lower_bound']:.4f} m, "
                 f"üst sınır {last['upper_bound']:.4f} m, fark {gap:.4f} m (%{gap / last['upper_bound'] * 100:.3f})")
    print("\n" + lagr_line)
    print(f"Güvenlik payı olmadan kurulan çizgede baseline: {no_margin} boşluk payı ihlali noktası.")

    md = [
        "# Metrikler",
        "",
        format_markdown_table(rows),
        "",
        f"- Kapasite K = {args.capacity} kablo/ayrıt, minimum bükülme yarıçapı = {MIN_BEND_RADIUS_M} m, "
        f"yasak hacim güvenlik payı = {args.clearance} m; EMC, yasak hacim ve boşluk denetimleri 0.05 m örnekleme ile.",
        f"- {lagr_line}.",
        f"- Güvenlik payı olmadan kurulan çizgede baseline {no_margin} boşluk payı ihlali noktası üretir "
        "(boşluk denetiminin çalıştığını gösterir).",
        "",
    ]
    (args.out / "metrics.md").write_text("\n".join(md), encoding="utf-8")
    history = [{k: _finite(v) for k, v in h.items()} for h in lagr.history]
    (args.out / "lagrangian_history.json").write_text(json.dumps(history, indent=1), encoding="utf-8")

    if args.trials > 0:
        t0 = time.perf_counter()
        settings = CheckSettings(volumes, separation, MIN_BEND_RADIUS_M, args.capacity, args.clearance)
        routers = {
            "c) tek geçiş": lambda cs: route_emc_aware(graph, cs, separation, REUSE_FACTOR, EMC_PENALTY,
                                                       reroute_rounds=0),
            "c) + söküp yeniden rotalama": lambda cs: route_emc_aware(graph, cs, separation, REUSE_FACTOR,
                                                                     EMC_PENALTY),
            "e) Bütünleşik": lambda cs: route_integrated(graph, cs, separation, turns, args.capacity,
                                                        reuse_factor=REUSE_FACTOR, emc_penalty=EMC_PENALTY),
        }
        bench = run_robustness(graph, SCENARIO_SPECS, PARAMS.radius, routers, settings, args.trials,
                               ROBUSTNESS_SEED)
        table = format_robustness_markdown(bench)
        print(f"\nSağlamlık testi ({args.trials} deneme / deney, {time.perf_counter() - t0:.1f} s):\n{table}")
        (args.out / "robustness.md").write_text(
            "# Sağlamlık testi\n\n"
            f"Her deney {args.trials} denemedir (seed = {ROBUSTNESS_SEED}). \"Rastgele sıra\": özgün senaryo, kablolar "
            "rastgele sırayla rotalanır. \"Uç nokta sapması\": ayrıca her uç nokta ±0,05 m eksenel ve ±1,5° çevresel "
            "kaydırılır. Tüm sonuçlar bağımsız denetimlerle ölçülmüştür.\n\n" + table + "\n",
            encoding="utf-8",
        )

    write_presentation(mesh, volumes, cables, graph, results, rows, args)
    print(f"\nÇıktılar: {_display(args.out)}, {_display(args.docs)}  (toplam süre {time.perf_counter() - t_start:.1f} s)")


def write_presentation(
    mesh: trimesh.Trimesh,
    volumes: list[ForbiddenVolume],
    cables: list[Cable],
    graph: RoutingGraph,
    results: list[RoutingResult],
    rows: list[dict[str, object]],
    args: argparse.Namespace,
) -> None:
    """Interactive page always; unless --no-images also the 2D charts and the 3D images captured from the page."""
    by_method = {r.method: (r, row) for r, row in zip(results, rows)}
    classes = [c.emc_class for c in cables]

    violations = {}
    for res, row in zip(results, rows):
        pts = emc_violation_points([graph.positions[res.routes[c.name]] for c in cables], classes, separation)
        assert len(pts) == row["emc_points"], "violation points must match the reported metric"
        violations[res.method] = pts

    page = args.docs / "index.html"
    write_interactive_page(
        mesh, volumes, cables, results, rows, violations, page, PARAMS.radius, PARAMS.length,
        clearance=args.clearance,
    )
    if args.no_images:
        return

    from harness_demo.capture import capture_readme_images
    from harness_demo.visualize import plot_convergence, plot_metrics_chart

    plot_convergence(by_method["lagrangian"][0].history, args.out / "lagrangian_convergence.png")
    plot_metrics_chart(rows, args.out / "metrics_chart.png")
    t0 = time.perf_counter()
    written = capture_readme_images(page, args.out, [r.method for r in results],
                                    comparison=("bundled", "integrated"), animated="integrated")
    print(f"3B görseller etkileşimli sayfadan yakalandı ({len(written)} dosya, {time.perf_counter() - t0:.1f} s).")


if __name__ == "__main__":
    main()
