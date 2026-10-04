"""Unit tests of the independent checks on small synthetic inputs."""

from __future__ import annotations

import math

import numpy as np
import pytest

from harness_demo.checks import (
    circumradius,
    count_bend_violations,
    count_capacity_violations,
    count_clearance_violations,
    count_emc_violations,
    count_forbidden_violations,
    distance_to_volume,
    resample_polyline,
)
from harness_demo.geometry import BoxVolume, SphereVolume
from harness_demo.scenarios import separation


def line(y: float, length: float = 1.0) -> np.ndarray:
    return np.array([[0.0, y, 0.0], [length, y, 0.0]])


def test_circumradius_right_angle_and_collinear():
    a, b, c = np.zeros(3), np.array([1.0, 0, 0]), np.array([1.0, 1.0, 0])
    assert circumradius(a, b, c) == pytest.approx(math.sqrt(2) / 2)
    assert math.isinf(circumradius(a, b, np.array([2.0, 0, 0])))


def test_resample_keeps_endpoints_and_spacing():
    pts = np.array([[0, 0, 0], [0.33, 0, 0], [0.33, 0.21, 0]], dtype=float)
    s = resample_polyline(pts, 0.05)
    assert np.allclose(s[0], pts[0]) and np.allclose(s[-1], pts[-1])
    assert np.linalg.norm(np.diff(s, axis=0), axis=1).max() <= 0.05 + 1e-12


def test_emc_counts_points_closer_than_separation():
    sep = separation("power", "data")  # 0.20 m
    n = len(resample_polyline(line(0.0)))
    assert count_emc_violations([line(0.0), line(sep / 2)], ["power", "data"], separation) == 2 * n
    assert count_emc_violations([line(0.0), line(sep * 1.5)], ["power", "data"], separation) == 0
    assert count_emc_violations([line(0.0), line(0.01)], ["power", "power"], separation) == 0


def test_bend_check_flags_sharp_turns_only():
    sharp = np.array([[0, 0, 0], [0.1, 0, 0], [0.1, 0.1, 0]], dtype=float)  # 90 deg, R = 0.0707 m
    gentle = np.array([[0, 0, 0], [0.1, 0, 0], [0.2, 0.02, 0]], dtype=float)
    assert count_bend_violations([sharp], 0.10) == 1
    assert count_bend_violations([gentle], 0.10) == 0


def test_capacity_counts_undirected_edges():
    paths = [[0, 1, 2], [2, 1, 0], [1, 0]]
    assert count_capacity_violations(paths, 2) == 1  # edge (0, 1) carries three cables
    assert count_capacity_violations(paths, 3) == 0


def test_distance_to_volume():
    box = BoxVolume("b", (0, 0, 0), (1, 1, 1))
    sphere = SphereVolume("s", (0, 0, 0), 1.0)
    pts = np.array([[0.5, 0.5, 0.5], [2.0, 0.5, 0.5], [2.0, 2.0, 0.5]])
    assert np.allclose(distance_to_volume(pts, box), [0.0, 1.0, math.sqrt(2)])
    assert np.allclose(distance_to_volume(np.array([[0, 0, 0.5], [0, 0, 3.0]]), sphere), [0.0, 2.0])


def test_forbidden_and_clearance_are_separate():
    box = BoxVolume("b", (0.4, -0.1, -0.1), (0.6, 0.1, 0.1))
    through = line(0.0)
    near = line(0.13)  # 3 cm outside the box
    assert count_forbidden_violations([through], [box]) > 0
    assert count_forbidden_violations([near], [box]) == 0
    assert count_clearance_violations([near], [box], clearance=0.05) > 0
    assert count_clearance_violations([near], [box], clearance=0.02) == 0
    # Points inside the volume are forbidden-volume violations, not clearance violations.
    inside_only = np.array([[0.45, 0, 0], [0.55, 0, 0]])
    assert count_clearance_violations([inside_only], [box], clearance=0.05) == 0
