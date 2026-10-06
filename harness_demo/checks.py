"""Independent constraint checks.

These functions deliberately do NOT use the routing code or the routing graph:
they take plain node paths plus vertex coordinates and recompute everything
from geometry, so they can catch mistakes in the routing logic.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from itertools import pairwise
from typing import Protocol, runtime_checkable

import numpy as np
from scipy.spatial import cKDTree

SAMPLE_STEP_M = 0.05  # resampling step for distance-based checks


@runtime_checkable
class SphereLike(Protocol):
    """Any sphere-shaped keep-out volume (only its raw parameters are used)."""

    @property
    def center(self) -> tuple[float, float, float]: ...

    @property
    def radius(self) -> float: ...


@runtime_checkable
class BoxLike(Protocol):
    """Any axis-aligned box keep-out volume (only its raw parameters are used)."""

    @property
    def lo(self) -> tuple[float, float, float]: ...

    @property
    def hi(self) -> tuple[float, float, float]: ...


VolumeLike = SphereLike | BoxLike


@dataclass(frozen=True)
class CheckSettings:
    """Parameters of the independent checks (shared by the metrics, the benchmark and the exports)."""

    volumes: Sequence[VolumeLike]
    separation_fn: Callable[[str, str], float]
    min_bend_radius: float
    capacity: int
    clearance: float = 0.0


@dataclass
class CheckReport:
    """Violation counts for one routing solution."""

    emc_points: int  # sampled route points closer than the required separation
    bend_points: int  # route vertices whose local bend radius is below the limit
    forbidden_points: int  # sampled route points inside a forbidden volume
    clearance_points: int  # sampled route points outside a volume but closer than the clearance
    capacity_edges: int  # edges carrying more than K cables

    def as_dict(self) -> dict[str, int]:
        """Plain dict view."""
        return asdict(self)


def resample_polyline(points: np.ndarray, step: float = SAMPLE_STEP_M) -> np.ndarray:
    """Return points along the polyline with spacing <= step (vertices included).

    Segment k is split into n_k = ceil(length / step) parts at t = i / n_k, i = 1..n_k
    (vectorised over all segments).

    Deliberately not shared with the router's `routing.densify`: the checks must stay
    independent of the code they verify, so they carry their own copy of this primitive.
    """
    points = np.asarray(points, dtype=float)
    a, d = points[:-1], points[1:] - points[:-1]
    n = np.maximum(1, np.ceil(np.linalg.norm(d, axis=1) / step).astype(int))
    seg = np.repeat(np.arange(len(n)), n)
    i = np.arange(len(seg)) - np.repeat(np.cumsum(n) - n, n) + 1
    t = i / n[seg]
    return np.vstack([points[:1], a[seg] + d[seg] * t[:, None]])


def emc_violation_points(
    polylines: Sequence[np.ndarray],
    classes: Sequence[str],
    separation_fn: Callable[[str, str], float],
    step: float = SAMPLE_STEP_M,
) -> np.ndarray:
    """Sampled points closer to a route of another class than the required separation.

    A point is listed once per offending route (a point near two foreign routes appears twice).
    Returns an (M, 3) array.
    """
    samples = [resample_polyline(p, step) for p in polylines]
    trees = [cKDTree(s) for s in samples]
    hits = [np.empty((0, 3))]
    for i, si in enumerate(samples):
        for j, tj in enumerate(trees):
            if i == j:
                continue
            sep = separation_fn(classes[i], classes[j])
            if sep <= 0.0:
                continue
            d, _ = tj.query(si)
            hits.append(si[d < sep])
    return np.vstack(hits)


def count_emc_violations(
    polylines: Sequence[np.ndarray],
    classes: Sequence[str],
    separation_fn: Callable[[str, str], float],
    step: float = SAMPLE_STEP_M,
) -> int:
    """Number of EMC violation points (see `emc_violation_points`)."""
    return len(emc_violation_points(polylines, classes, separation_fn, step))


def circumradius(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """Radius of the circle through three points (inf if collinear)."""
    ab, bc, ca = np.linalg.norm(b - a), np.linalg.norm(c - b), np.linalg.norm(a - c)
    area2 = np.linalg.norm(np.cross(b - a, c - a))  # = 2 * triangle area
    if area2 < 1e-12:
        return float("inf")
    return float(ab * bc * ca / (2.0 * area2))


def circumradii(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Row-wise `circumradius` for (M, 3) arrays (inf where the three points are collinear)."""
    ab = np.linalg.norm(b - a, axis=1)
    bc = np.linalg.norm(c - b, axis=1)
    ca = np.linalg.norm(a - c, axis=1)
    area2 = np.linalg.norm(np.cross(b - a, c - a), axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = ab * bc * ca / (2.0 * area2)
    return np.where(area2 < 1e-12, np.inf, r)


def count_bend_violations(polylines: Sequence[np.ndarray], min_radius: float) -> int:
    """Count interior vertices whose three-point circumradius is below min_radius."""
    return sum(int(np.count_nonzero(circumradii(p[:-2], p[1:-1], p[2:]) < min_radius))
               for p in polylines if len(p) >= 3)


def _inside_volume(points: np.ndarray, volume: VolumeLike) -> np.ndarray:
    """Point-in-volume test recomputed from the volume's raw parameters."""
    if isinstance(volume, SphereLike):
        return np.linalg.norm(points - np.asarray(volume.center), axis=1) < volume.radius
    lo, hi = np.asarray(volume.lo), np.asarray(volume.hi)
    return np.all((points > lo) & (points < hi), axis=1)


def distance_to_volume(points: np.ndarray, volume: VolumeLike) -> np.ndarray:
    """Euclidean distance from each point to the volume (0 inside), from raw parameters."""
    if isinstance(volume, SphereLike):
        return np.maximum(np.linalg.norm(points - np.asarray(volume.center), axis=1) - volume.radius, 0.0)
    lo, hi = np.asarray(volume.lo), np.asarray(volume.hi)
    return np.linalg.norm(np.maximum(np.maximum(lo - points, points - hi), 0.0), axis=1)


def count_forbidden_violations(
    polylines: Sequence[np.ndarray], volumes: Sequence[VolumeLike], step: float = SAMPLE_STEP_M
) -> int:
    """Count sampled route points inside any forbidden volume."""
    count = 0
    for p in polylines:
        s = resample_polyline(p, step)
        inside = np.zeros(len(s), dtype=bool)
        for vol in volumes:
            inside |= _inside_volume(s, vol)
        count += int(inside.sum())
    return count


def count_clearance_violations(
    polylines: Sequence[np.ndarray], volumes: Sequence[VolumeLike], clearance: float, step: float = SAMPLE_STEP_M
) -> int:
    """Count sampled route points outside every volume but closer than `clearance` to one of them."""
    if clearance <= 0.0:
        return 0
    count = 0
    for p in polylines:
        s = resample_polyline(p, step)
        inside = np.zeros(len(s), dtype=bool)
        near = np.zeros(len(s), dtype=bool)
        for vol in volumes:
            inside |= _inside_volume(s, vol)
            near |= distance_to_volume(s, vol) < clearance
        count += int((near & ~inside).sum())
    return count


def count_capacity_violations(node_paths: Sequence[Sequence[int]], capacity: int) -> int:
    """Count undirected edges used by more than `capacity` cables."""
    load: Counter[tuple[int, int]] = Counter()
    for path in node_paths:
        for e in {(min(a, b), max(a, b)) for a, b in pairwise(path)}:
            load[e] += 1
    return sum(1 for n in load.values() if n > capacity)


def run_all_checks(
    node_paths: Sequence[Sequence[int]],
    classes: Sequence[str],
    positions: np.ndarray,
    volumes: Sequence[VolumeLike],
    separation_fn: Callable[[str, str], float],
    min_bend_radius: float,
    capacity: int,
    clearance: float = 0.0,
) -> CheckReport:
    """Run all five checks on a set of node paths."""
    polylines = [positions[np.asarray(p)] for p in node_paths]
    return CheckReport(
        emc_points=count_emc_violations(polylines, classes, separation_fn),
        bend_points=count_bend_violations(polylines, min_bend_radius),
        forbidden_points=count_forbidden_violations(polylines, volumes),
        clearance_points=count_clearance_violations(polylines, volumes, clearance),
        capacity_edges=count_capacity_violations(node_paths, capacity),
    )
