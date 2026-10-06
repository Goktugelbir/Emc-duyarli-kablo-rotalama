"""Routing algorithms.

a) baseline        : independent Dijkstra per cable                              (core.py)
b) bundled         : sequential routing; reused edges get a cost discount        (sequential.py)
c) emc_aware       : (b) + penalty on edges close to routes of other EMC classes,
                     followed by rip-up-and-reroute of cables that still conflict (sequential.py)
d) lagrangian      : edge capacity (<= K cables) relaxed with Lagrange multipliers,
                     subgradient updates, lower/upper bounds tracked per iteration (lagrangian.py)
e) integrated      : (c) on a turn-aware graph (no turn sharper than the minimum bend
                     radius can be taken) with a capacity penalty on full edges   (sequential.py, turn_graph.py)
"""

from .core import SAMPLE_STEP_M, NoPathError, RoutingResult, circumradii, densify, route_baseline, shortest_path
from .lagrangian import route_lagrangian
from .sequential import (
    ORDER_STRATEGIES,
    order_cables,
    route_bundled,
    route_conflicts,
    route_emc_aware,
    route_integrated,
)
from .turn_graph import TurnGraph, build_turn_graph, turn_aware_path

__all__ = [
    "ORDER_STRATEGIES",
    "SAMPLE_STEP_M",
    "NoPathError",
    "RoutingResult",
    "TurnGraph",
    "build_turn_graph",
    "circumradii",
    "densify",
    "order_cables",
    "route_baseline",
    "route_bundled",
    "route_conflicts",
    "route_emc_aware",
    "route_integrated",
    "route_lagrangian",
    "shortest_path",
    "turn_aware_path",
]
