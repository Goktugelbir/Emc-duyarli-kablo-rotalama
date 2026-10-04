"""Independent constraint checks.

These functions deliberately do NOT use the routing code or the routing graph:
they take plain node paths plus vertex coordinates and recompute everything
from geometry, so they can catch mistakes in the routing logic.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass

import numpy as np
from scipy.spatial import cKDTree

SAMPLE_STEP_M = 0.05  # resampling step for distance-based checks


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
    """Return points along the polyline with spacing <= step (vertices included)."""
    out = [points[0]]
    for a, b in zip(points[:-1], points[1:]):
        n = max(1, int(np.ceil(np.linalg.norm(b - a) / step)))
        for t in np.arange(1, n + 1) / n:
            out.append(a + (b - a) * t)
    return np.asarray(out)


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


def count_bend_violations(polylines: Sequence[np.ndarray], min_radius: float) -> int:
    """Count interior vertices whose three-point circumradius is below min_radius."""
    count = 0
    for p in polylines:
        for a, b, c in zip(p[:-2], p[1:-1], p[2:]):
            if circumradius(a, b, c) < min_radius:
                count += 1
    return count


def _inside_volume(points: np.ndarray, volume: object) -> np.ndarray:
    """Point-in-volume test recomputed from the volume's raw parameters."""
    if hasattr(volume, "radius"):
        return np.linalg.norm(points - np.asarray(volume.center), axis=1) < volume.radius
    lo, hi = np.asarray(volume.lo), np.asarray(volume.hi)
    return np.all((points > lo) & (points < hi), axis=1)


def distance_to_volume(points: np.ndarray, volume: object) -> np.ndarray:
    """Euclidean distance from each point to the volume (0 inside), from raw parameters."""
    if hasattr(volume, "radius"):
        return np.maximum(np.linalg.norm(points - np.asarray(volume.center), axis=1) - volume.radius, 0.0)
    lo, hi = np.asarray(volume.lo), np.asarray(volume.hi)
    return np.linalg.norm(np.maximum(np.maximum(lo - points, points - hi), 0.0), axis=1)


def count_forbidden_violations(
    polylines: Sequence[np.ndarray], volumes: Sequence[object], step: float = SAMPLE_STEP_M
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
    polylines: Sequence[np.ndarray], volumes: Sequence[object], clearance: float, step: float = SAMPLE_STEP_M
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
        for e in {(min(a, b), max(a, b)) for a, b in zip(path[:-1], path[1:])}:
            load[e] += 1
    return sum(1 for n in load.values() if n > capacity)


def run_all_checks(
    node_paths: Sequence[Sequence[int]],
    classes: Sequence[str],
    positions: np.ndarray,
    volumes: Sequence[object],
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
