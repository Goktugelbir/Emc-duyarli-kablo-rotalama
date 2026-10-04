"""Synthetic cable scenario and EMC separation table.

All numbers are representative values chosen for the demo; they are not taken
from any standard or real aircraft.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from .geometry import surface_point
from .graph import RoutingGraph

EMC_CLASSES: tuple[str, ...] = ("power", "signal", "data")

# Minimum separation [m] between routes of two EMC classes (representative).
SEPARATION_M: dict[frozenset[str], float] = {
    frozenset(("power", "signal")): 0.15,
    frozenset(("power", "data")): 0.20,
    frozenset(("signal", "data")): 0.10,
}


def separation(class_a: str, class_b: str) -> float:
    """Required separation between two EMC classes (0 for the same class)."""
    if class_a == class_b:
        return 0.0
    return SEPARATION_M[frozenset((class_a, class_b))]


@dataclass(frozen=True)
class CableSpec:
    """Cable definition in surface coordinates: (x [m], theta [deg])."""

    name: str
    emc_class: str
    start_xt: tuple[float, float]
    end_xt: tuple[float, float]


@dataclass(frozen=True)
class Cable:
    """Cable snapped to routing-graph nodes."""

    name: str
    emc_class: str
    start: int
    end: int


# Two equipment clusters per side; neighbouring terminals of different classes
# are close (so bundling is attractive) but at least the required separation
# apart (so an EMC-clean solution exists away from crossings).
SCENARIO_SPECS: list[CableSpec] = [
    # Right side: aft rack (x~0.3) -> forward panel (x~5.7); blocked by the actuator envelope.
    CableSpec("P1", "power", (0.3, 48.0), (5.7, 50.0)),
    CableSpec("P2", "power", (0.4, 51.0), (5.6, 53.0)),
    CableSpec("S1", "signal", (0.3, 59.0), (5.7, 61.0)),
    CableSpec("S2", "signal", (0.4, 62.0), (5.6, 64.0)),
    CableSpec("D1", "data", (0.3, 69.0), (5.7, 71.0)),
    # Left side: aft rack -> forward panel; blocked by the access panel.
    CableSpec("D2", "data", (0.3, 112.0), (5.7, 114.0)),
    CableSpec("S3", "signal", (0.3, 121.0), (5.7, 123.0)),
    CableSpec("P3", "power", (0.3, 132.0), (5.7, 134.0)),
    CableSpec("P4", "power", (0.4, 135.0), (5.6, 137.0)),
    # Cross-links between the two sides (must cross the other bundles).
    CableSpec("D3", "data", (0.4, 72.0), (5.6, 110.0)),
    CableSpec("S4", "signal", (0.8, 125.0), (5.2, 58.0)),
]


def build_scenario(graph: RoutingGraph, radius: float, specs: list[CableSpec] = SCENARIO_SPECS) -> list[Cable]:
    """Snap each cable terminal to the nearest routable node."""
    cables = []
    for s in specs:
        start = graph.nearest_node(surface_point(*s.start_xt, radius))
        end = graph.nearest_node(surface_point(*s.end_xt, radius))
        cables.append(Cable(s.name, s.emc_class, start, end))
    return cables


def perturb_specs(
    specs: list[CableSpec], rng: np.random.Generator, dx: float = 0.05, dtheta: float = 1.5
) -> list[CableSpec]:
    """Shift every terminal by up to +-dx [m] axially and +-dtheta [deg] around the arc.

    The bounds are small enough that neighbouring terminals of different classes stay further
    apart than their required separation, so EMC violations remain avoidable.
    """
    def move(xt: tuple[float, float]) -> tuple[float, float]:
        return (float(xt[0] + rng.uniform(-dx, dx)), float(xt[1] + rng.uniform(-dtheta, dtheta)))

    return [replace(s, start_xt=move(s.start_xt), end_xt=move(s.end_xt)) for s in specs]
