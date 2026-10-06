"""End-to-end demo: geometry -> graph -> scenario -> 5 routing methods -> checks -> reports -> exports -> plots.

Run `python main.py --help` for the options (e.g. `--no-images` skips PNG/GIF export, which
needs Chrome, and still writes the metrics, the robustness table, the exports and the interactive page).
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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import trimesh

from harness_demo.benchmark import (
    BenchmarkContext,
    RouterSpec,
    default_workers,
    format_robustness_markdown,
    run_robustness,
)
from harness_demo.checks import CheckReport, CheckSettings, emc_violation_points, run_all_checks
from harness_demo.export import export_routes_json, export_wirelist_csv, generate_wirelist_records
from harness_demo.geometry import ForbiddenVolume, FuselageParams, build_fuselage, default_forbidden_volumes
from harness_demo.graph import RoutingGraph, build_routing_graph
from harness_demo.metrics import Row, compute_metrics, format_console_table, format_markdown_table
from harness_demo.presentation import write_interactive_page
from harness_demo.routing import (
    ORDER_STRATEGIES,
    RoutingResult,
    TurnGraph,
    build_turn_graph,
    route_baseline,
    route_bundled,
    route_emc_aware,
    route_integrated,
    route_lagrangian,
)
from harness_demo.scenarios import EMC_CLASSES, SCENARIO_SPECS, Cable, build_scenario, separation

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

# Methods compared in the robustness benchmark (the capacity of `integrated` comes from the check settings).
_COST: dict[str, Any] = {"reuse_factor": REUSE_FACTOR, "emc_penalty": EMC_PENALTY}
BENCHMARK_ROUTERS: dict[str, RouterSpec] = {
    "c) tek geçiş": RouterSpec("emc_aware", {**_COST, "reroute_rounds": 0}),
    "c) + söküp yeniden rotalama": RouterSpec("emc_aware", _COST),
    "e) Bütünleşik": RouterSpec("integrated", _COST),
}


@dataclass(frozen=True)
class Model:
    """The problem instance shared by all pipeline steps."""

    mesh: trimesh.Trimesh
    volumes: list[ForbiddenVolume]
    graph: RoutingGraph
    cables: list[Cable]
    turns: TurnGraph
    settings: CheckSettings

    def check(self, res: RoutingResult, cables: list[Cable] | None = None,
              graph: RoutingGraph | None = None) -> CheckReport:
        """Independent checks of one routing result (by default on this model's graph and cables)."""
        cables, graph, s = cables or self.cables, graph or self.graph, self.settings
        return run_all_checks([res.routes[c.name] for c in cables], [c.emc_class for c in cables], graph.positions,
                              s.volumes, s.separation_fn, s.min_bend_radius, s.capacity, s.clearance)


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
    p.add_argument("--workers", type=int, default=default_workers(),
                   help="sağlamlık testi için paralel işlem sayısı; 1 = sıralı, sonuç değişmez "
                        "(varsayılan: Linux'ta 4, Windows/macOS'ta 1)")
    p.add_argument("--capacity", type=int, default=CAPACITY_K, help="ayrıt kapasitesi K [kablo]")
    p.add_argument("--clearance", type=float, default=CLEARANCE_M, help="yasak hacim güvenlik payı [m]")
    p.add_argument("--order", choices=ORDER_STRATEGIES, default="input",
                   help="kablo önceliklendirme stratejisi (varsayılan: input)")
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
    """Run the full pipeline and write all outputs (console output is also saved to run_log.txt)."""
    args = parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    tee = _Tee(sys.stdout)  # type: ignore[arg-type]
    with contextlib.redirect_stdout(tee):
        run(args)
    (args.out / "run_log.txt").write_text(tee.buffer_text.getvalue(), encoding="utf-8")


def run(args: argparse.Namespace) -> None:
    """The pipeline: build -> route -> check -> report -> export -> benchmark -> present."""
    t_start = time.perf_counter()
    args.out.mkdir(parents=True, exist_ok=True)
    model = build_model(args)
    results = route_all(model, args)
    rows = [compute_metrics(res, model.graph, model.check(res)) for res in results]
    report_metrics(model, results, rows, args)
    write_exports(model, results, rows, args)
    if args.trials > 0:
        run_benchmark(model, args)
    write_presentation(model, results, rows, args)
    print(f"\nÇıktılar: {_display(args.out)}, {_display(args.docs)}  "
          f"(toplam süre {time.perf_counter() - t_start:.1f} s)")


def build_model(args: argparse.Namespace) -> Model:
    """Fuselage mesh, keep-out volumes, routing graph (with clearance), scenario and turn graph."""
    mesh = build_fuselage(PARAMS)
    volumes = default_forbidden_volumes(PARAMS.radius)
    graph = build_routing_graph(mesh, volumes, clearance=args.clearance)
    cables = build_scenario(graph, PARAMS.radius)
    turns = build_turn_graph(graph, MIN_BEND_RADIUS_M)
    settings = CheckSettings(volumes, separation, MIN_BEND_RADIUS_M, args.capacity, args.clearance)
    removed = len(mesh.vertices) - graph.nx_graph.number_of_nodes()
    print(f"Mesh: {len(mesh.vertices)} köşe, {len(mesh.faces)} üçgen | "
          f"Çizge: {graph.nx_graph.number_of_nodes()} düğüm, {graph.n_edges} ayrıt | "
          f"{removed} düğüm yasak hacimler ve {args.clearance} m güvenlik payı nedeniyle çıkarıldı | "
          f"{len(cables)} kablo")
    print(f"Dönüş çizgesi: {turns.n_states} yönlü ayrıt, {len(turns.arc_src)} izinli dönüş "
          f"(bükülme yarıçapı >= {MIN_BEND_RADIUS_M} m)")
    return Model(mesh, volumes, graph, cables, turns, settings)


def route_all(model: Model, args: argparse.Namespace) -> list[RoutingResult]:
    """The five routing methods on the model's scenario."""
    g, cables = model.graph, model.cables
    return [
        route_baseline(g, cables),
        route_bundled(g, cables, reuse_factor=REUSE_FACTOR, order_strategy=args.order),
        route_emc_aware(g, cables, separation, reuse_factor=REUSE_FACTOR, emc_penalty=EMC_PENALTY,
                        order_strategy=args.order),
        route_lagrangian(g, cables, capacity=args.capacity, iterations=LAGRANGE_ITERATIONS),
        route_integrated(g, cables, separation, model.turns, args.capacity, reuse_factor=REUSE_FACTOR,
                         emc_penalty=EMC_PENALTY, order_strategy=args.order),
    ]


def report_metrics(model: Model, results: list[RoutingResult], rows: list[Row],
                   args: argparse.Namespace) -> None:
    """Console table, Lagrangian bounds, clearance sanity check; metrics.md and lagrangian_history.json."""
    # The clearance check is only meaningful if it fires when the margin is ignored: route the
    # baseline on a graph built without clearance and count how close it gets to the volumes.
    plain = build_routing_graph(model.mesh, model.volumes)
    plain_cables = build_scenario(plain, PARAMS.radius)
    no_margin = model.check(route_baseline(plain, plain_cables), plain_cables, plain).clearance_points

    lagr = next(r for r in results if r.method == "lagrangian")
    last = lagr.history[-1]
    gap = last["upper_bound"] - last["lower_bound"]
    lagr_line = (f"Lagrange: {len(lagr.history)} iterasyon, alt sınır {last['lower_bound']:.4f} m, "
                 f"üst sınır {last['upper_bound']:.4f} m, fark {gap:.4f} m (%{gap / last['upper_bound'] * 100:.3f})")
    print()
    print(format_console_table(rows))
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


def write_exports(model: Model, results: list[RoutingResult], rows: list[Row],
                  args: argparse.Namespace) -> None:
    """wirelist.csv (integrated method, with per-cable margins) and routes.json (all methods, 3D polylines)."""
    integrated = next(r for r in results if r.method == "integrated")
    wirelist = generate_wirelist_records(model.graph, model.cables, integrated.routes, model.settings)
    export_wirelist_csv(wirelist, args.out / "wirelist.csv")
    parameters = {
        "capacity_k": args.capacity, "min_bend_radius_m": MIN_BEND_RADIUS_M, "clearance_m": args.clearance,
        "order_strategy": args.order,
        "separation_m": {f"{a}-{b}": separation(a, b) for i, a in enumerate(EMC_CLASSES) for b in EMC_CLASSES[i + 1:]},
    }
    export_routes_json(model.graph, model.cables, results, args.out / "routes.json", rows=rows, parameters=parameters)
    n_ok = sum(r["status"] == "OK" for r in wirelist)
    margins = [m for r in wirelist if isinstance(m := r["min_emc_margin_m"], float)]
    worst = f"{min(margins) * 100:+.1f} cm" if margins else "—"
    print(f"Kablo listesi (e yöntemi): {n_ok}/{len(wirelist)} kablo tüm paylarla OK, "
          f"en küçük EMC payı {worst} -> wirelist.csv, routes.json")


def run_benchmark(model: Model, args: argparse.Namespace) -> None:
    """Robustness benchmark (random order, perturbed terminals) -> robustness.md."""
    t0 = time.perf_counter()
    ctx = BenchmarkContext(model.graph, model.settings, model.turns)
    bench = run_robustness(ctx, SCENARIO_SPECS, PARAMS.radius, BENCHMARK_ROUTERS, args.trials, ROBUSTNESS_SEED,
                           workers=args.workers)
    table = format_robustness_markdown(bench)
    mode = f"{args.workers} paralel işlem" if args.workers > 1 else "sıralı"
    print(f"\nSağlamlık testi ({args.trials} deneme / deney, {mode}, {time.perf_counter() - t0:.1f} s):\n{table}")
    (args.out / "robustness.md").write_text(
        "# Sağlamlık testi\n\n"
        f"Her deney {args.trials} denemedir (seed = {ROBUSTNESS_SEED}). \"Rastgele sıra\": özgün senaryo, kablolar "
        "rastgele sırayla rotalanır. \"Uç nokta sapması\": ayrıca her uç nokta ±0,05 m eksenel ve ±1,5° çevresel "
        "kaydırılır. Tüm sonuçlar bağımsız denetimlerle ölçülmüştür.\n\n" + table + "\n",
        encoding="utf-8",
    )


def write_presentation(model: Model, results: list[RoutingResult], rows: list[Row],
                       args: argparse.Namespace) -> None:
    """Interactive page always; unless --no-images also the 2D charts and the 3D images captured from the page."""
    classes = [c.emc_class for c in model.cables]
    violations = {}
    for res, row in zip(results, rows):
        pts = emc_violation_points([model.graph.positions[res.routes[c.name]] for c in model.cables], classes,
                                   separation)
        assert len(pts) == row["emc_points"], "violation points must match the reported metric"
        violations[res.method] = pts

    # Per-cable verification margins (same computation as the wirelist), shown in the page's tooltips.
    margins = {
        res.method: {str(r["cable_name"]): {"emc": r["min_emc_margin_m"], "bend": r["min_bend_radius_m"],
                                            "keepout": r["min_keepout_distance_m"], "status": r["status"]}
                     for r in generate_wirelist_records(model.graph, model.cables, res.routes, model.settings)}
        for res in results
    }
    page = args.docs / "index.html"
    write_interactive_page(
        model.mesh, model.volumes, model.cables, results, rows, violations, page, PARAMS.radius, PARAMS.length,
        clearance=args.clearance, margins=margins, min_bend_radius=MIN_BEND_RADIUS_M,
    )
    if args.no_images:
        return

    import kaleido

    from harness_demo.capture import capture_readme_images
    from harness_demo.visualize import plot_convergence, plot_metrics_chart

    # The headless browser for the 2D charts starts only now, so it never competes with the timed routing.
    # plotly warns that per-call kaleido options are ignored while a shared server runs; that is intended.
    warnings.filterwarnings("ignore", message="The kopts argument is ignored if using a server")
    kaleido.start_sync_server(n=1, silence_warnings=True)
    try:
        lagr = next(r for r in results if r.method == "lagrangian")
        plot_convergence(lagr.history, args.out / "lagrangian_convergence.png")
        plot_metrics_chart(rows, args.out / "metrics_chart.png")
    finally:
        kaleido.stop_sync_server(silence_warnings=True)
    t0 = time.perf_counter()
    written = capture_readme_images(page, args.out, [r.method for r in results],
                                    comparison=("bundled", "integrated"), animated="integrated")
    print(f"3B görseller etkileşimli sayfadan yakalandı ({len(written)} dosya, {time.perf_counter() - t0:.1f} s).")


if __name__ == "__main__":
    main()
