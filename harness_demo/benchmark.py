"""Robustness benchmark: how much do the sequential methods depend on cable order and terminals?

Sequential routing is order dependent, so a single "0 violations" result can be luck. Two
families of trials are run with a fixed seed:

- order    : the original scenario, cables routed in a random order,
- perturbed: every terminal shifted slightly (see `perturb_specs`) and a random order.

Every trial is evaluated with the independent checks, exactly like the main results.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from .checks import CheckReport, run_all_checks
from .geometry import ForbiddenVolume
from .graph import RoutingGraph
from .routing import RoutingResult
from .scenarios import Cable, CableSpec, build_scenario, perturb_specs

Router = Callable[[list[Cable]], RoutingResult]


@dataclass(frozen=True)
class CheckSettings:
    """Parameters of the independent checks used for every trial."""

    volumes: Sequence[ForbiddenVolume]
    separation_fn: Callable[[str, str], float]
    min_bend_radius: float
    capacity: int
    clearance: float


def _trial_cables(
    graph: RoutingGraph, specs: list[CableSpec], radius: float, rng: np.random.Generator, perturb: bool
) -> list[Cable]:
    """Cables of one trial: optionally perturbed terminals, always a random routing order."""
    cables = build_scenario(graph, radius, perturb_specs(specs, rng) if perturb else specs)
    return [cables[i] for i in rng.permutation(len(cables))]


def _check(graph: RoutingGraph, result: RoutingResult, cables: list[Cable], s: CheckSettings) -> CheckReport:
    return run_all_checks(
        [result.routes[c.name] for c in cables], [c.emc_class for c in cables], graph.positions,
        s.volumes, s.separation_fn, s.min_bend_radius, s.capacity, s.clearance,
    )


def run_robustness(
    graph: RoutingGraph,
    specs: list[CableSpec],
    radius: float,
    routers: dict[str, Router],
    settings: CheckSettings,
    n_trials: int,
    seed: int = 7,
) -> list[dict[str, object]]:
    """Run `n_trials` trials per family and summarise each router's check results."""
    rows = []
    for family, perturb in (("Rastgele sıra", False), ("Rastgele sıra + uç nokta sapması", True)):
        rng = np.random.default_rng(seed)
        trials = [_trial_cables(graph, specs, radius, rng, perturb) for _ in range(n_trials)]
        for label, router in routers.items():
            reports = [_check(graph, router(cables), cables, settings) for cables in trials]
            emc = np.array([r.emc_points for r in reports])
            cap = np.array([r.capacity_edges for r in reports])
            bend = np.array([r.bend_points for r in reports])
            clean = sum(
                r.emc_points == 0 and r.capacity_edges == 0 and r.bend_points == 0
                and r.forbidden_points == 0 and r.clearance_points == 0
                for r in reports
            )
            rows.append({
                "family": family, "method": label, "trials": n_trials,
                "emc_zero": int((emc == 0).sum()), "emc_mean": float(emc.mean()), "emc_max": int(emc.max()),
                "capacity_mean": float(cap.mean()), "capacity_max": int(cap.max()),
                "bend_max": int(bend.max()), "all_clean": int(clean),
            })
    return rows


def format_robustness_markdown(rows: list[dict[str, object]]) -> str:
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
