"""Robustness benchmark: how much do the sequential methods depend on cable order and terminals?

Sequential routing is order dependent, so a single "0 violations" result can be luck. Two
families of trials are run with a fixed seed:

- order    : the original scenario, cables routed in a random order,
- perturbed: every terminal shifted slightly (see `perturb_specs`) and a random order.

Every trial is evaluated with the independent checks, exactly like the main results. The trials
are independent, so they can run in parallel worker processes; the trials themselves are drawn
in the parent process, so the result does not depend on the number of workers.
"""

from __future__ import annotations

import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .checks import CheckReport, CheckSettings, run_all_checks
from .graph import RoutingGraph
from .metrics import Row
from .routing import RoutingResult, TurnGraph, route_baseline, route_bundled, route_emc_aware, route_integrated
from .scenarios import Cable, CableSpec, build_scenario, perturb_specs

FAMILIES: tuple[tuple[str, bool], ...] = (("Rastgele sıra", False), ("Rastgele sıra + uç nokta sapması", True))


@dataclass(frozen=True)
class RouterSpec:
    """A routing method by name plus its keyword arguments (picklable, unlike a lambda)."""

    method: str  # "baseline" | "bundled" | "emc_aware" | "integrated"
    kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BenchmarkContext:
    """Everything a trial needs besides its cables; sent once to every worker process."""

    graph: RoutingGraph
    settings: CheckSettings
    turns: TurnGraph | None = None  # required by the integrated method


def route_with(spec: RouterSpec, ctx: BenchmarkContext, cables: list[Cable]) -> RoutingResult:
    """Run the routing method described by `spec`."""
    s = ctx.settings
    if spec.method == "baseline":
        return route_baseline(ctx.graph, cables)
    if spec.method == "bundled":
        return route_bundled(ctx.graph, cables, **spec.kwargs)
    if spec.method == "emc_aware":
        return route_emc_aware(ctx.graph, cables, s.separation_fn, **spec.kwargs)
    if spec.method == "integrated":
        if ctx.turns is None:
            raise ValueError("the integrated method needs the turn graph in the benchmark context")
        return route_integrated(ctx.graph, cables, s.separation_fn, ctx.turns, s.capacity,
                                **spec.kwargs)
    raise ValueError(f"unknown routing method {spec.method!r}")


def _evaluate(spec: RouterSpec, ctx: BenchmarkContext, cables: list[Cable]) -> CheckReport:
    """Route one trial and measure it with the independent checks."""
    res, s = route_with(spec, ctx, cables), ctx.settings
    return run_all_checks(
        [res.routes[c.name] for c in cables], [c.emc_class for c in cables], ctx.graph.positions,
        s.volumes, s.separation_fn, s.min_bend_radius, s.capacity, s.clearance,
    )


_WORKER_CTX: BenchmarkContext | None = None


def _init_worker(ctx: BenchmarkContext) -> None:
    global _WORKER_CTX
    _WORKER_CTX = ctx


def _evaluate_in_worker(job: tuple[RouterSpec, list[Cable]]) -> CheckReport:
    assert _WORKER_CTX is not None, "worker not initialised"
    return _evaluate(job[0], _WORKER_CTX, job[1])


def default_workers() -> int:
    """Worker processes used by default: up to 4 where processes fork cheaply (Linux), otherwise 1.

    With the "spawn" start method (Windows, macOS) every worker re-imports numpy, scipy, networkx
    and trimesh (~1.5-2 s each), which costs about as much as the ~10 s benchmark can save;
    pass `workers` explicitly for larger trial counts there.
    """
    if multiprocessing.get_start_method() != "fork":
        return 1
    return max(1, min(4, os.cpu_count() or 1))


def _trial_cables(
    graph: RoutingGraph, specs: list[CableSpec], radius: float, rng: np.random.Generator, perturb: bool
) -> list[Cable]:
    """Cables of one trial: optionally perturbed terminals, always a random routing order."""
    cables = build_scenario(graph, radius, perturb_specs(specs, rng) if perturb else specs)
    return [cables[i] for i in rng.permutation(len(cables))]


def _summary(family: str, label: str, reports: list[CheckReport]) -> Row:
    emc = np.array([r.emc_points for r in reports])
    cap = np.array([r.capacity_edges for r in reports])
    bend = np.array([r.bend_points for r in reports])
    clean = sum(
        r.emc_points == 0 and r.capacity_edges == 0 and r.bend_points == 0
        and r.forbidden_points == 0 and r.clearance_points == 0
        for r in reports
    )
    return {
        "family": family, "method": label, "trials": len(reports),
        "emc_zero": int((emc == 0).sum()), "emc_mean": float(emc.mean()), "emc_max": int(emc.max()),
        "capacity_mean": float(cap.mean()), "capacity_max": int(cap.max()),
        "bend_max": int(bend.max()), "all_clean": int(clean),
    }


def run_robustness(
    ctx: BenchmarkContext,
    specs: list[CableSpec],
    radius: float,
    routers: dict[str, RouterSpec],
    n_trials: int,
    seed: int = 7,
    workers: int = 1,
) -> list[Row]:
    """Run `n_trials` trials per family and summarise each router's check results.

    With `workers > 1` the (router, trial) jobs run in that many processes; the summary is
    identical for any number of workers.
    """
    trials = {}
    for family, perturb in FAMILIES:
        rng = np.random.default_rng(seed)
        trials[family] = [_trial_cables(ctx.graph, specs, radius, rng, perturb) for _ in range(n_trials)]
    jobs = [(family, label, spec, cables)
            for family, _ in FAMILIES for label, spec in routers.items() for cables in trials[family]]

    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker, initargs=(ctx,)) as pool:
            reports = list(pool.map(_evaluate_in_worker, [(spec, cables) for _, _, spec, cables in jobs],
                                    chunksize=max(1, len(jobs) // (4 * workers))))
    else:
        reports = [_evaluate(spec, ctx, cables) for _, _, spec, cables in jobs]

    rows = []
    for family, _ in FAMILIES:
        for label in routers:
            mine = [r for (f, lab, _, _), r in zip(jobs, reports) if f == family and lab == label]
            rows.append(_summary(family, label, mine))
    return rows


def format_robustness_markdown(rows: list[Row]) -> str:
    """Markdown table of the robustness summary."""
    head = ("| Deney | Yöntem | EMC ihlali 0 olan | EMC ort. / en çok [nokta] | Kapasite ort. / en çok [ayrıt] "
            "| Bükülme en çok | Tüm denetimler temiz |")
    out = [head, "|:---|:---|---:|---:|---:|---:|---:|"]
    for r in rows:
        n = r["trials"]
        out.append(
            f"| {r['family']} | {r['method']} | {r['emc_zero']}/{n} | {r['emc_mean']:.1f} / {r['emc_max']} "
            f"| {r['capacity_mean']:.1f} / {r['capacity_max']} | {r['bend_max']} | {r['all_clean']}/{n} |"
        )
    return "\n".join(out)
