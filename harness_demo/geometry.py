"""Parametric fuselage section and forbidden volumes.

The fuselage is a half cylinder (an arch over the x axis) triangulated as a
structured grid. A small, seeded jitter is applied to interior vertices so the
mesh is not perfectly regular (closer to a real CAD tessellation) and so that
shortest-path ties are broken deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import trimesh


@dataclass(frozen=True)
class FuselageParams:
    """Geometric and meshing parameters of the half-cylinder section."""

    radius: float = 2.0
    length: float = 6.0
    n_axial: int = 61  # vertices along x  -> ~0.10 m spacing
    n_circ: int = 64  # vertices along the arc -> ~0.10 m spacing
    jitter: float = 0.15  # fraction of the grid spacing
    seed: int = 42


def surface_point(x: float, theta_deg: float, radius: float) -> np.ndarray:
    """Return the 3D point on the cylinder at axial position x and angle theta."""
    t = np.deg2rad(theta_deg)
    return np.array([x, radius * np.cos(t), radius * np.sin(t)])


def build_fuselage(params: FuselageParams = FuselageParams()) -> trimesh.Trimesh:
    """Build the triangulated half-cylinder surface (theta in [0, pi])."""
    xs = np.linspace(0.0, params.length, params.n_axial)
    ts = np.linspace(0.0, np.pi, params.n_circ)
    grid_x, grid_t = np.meshgrid(xs, ts, indexing="ij")

    rng = np.random.default_rng(params.seed)
    jx = rng.uniform(-1, 1, grid_x.shape) * params.jitter * (xs[1] - xs[0])
    jt = rng.uniform(-1, 1, grid_t.shape) * params.jitter * (ts[1] - ts[0])
    jx[[0, -1], :] = 0.0  # keep the open ends planar
    jt[:, [0, -1]] = 0.0  # keep the lower edges on z = 0
    grid_x = grid_x + jx
    grid_t = grid_t + jt

    vertices = np.column_stack(
        [
            grid_x.ravel(),
            params.radius * np.cos(grid_t.ravel()),
            params.radius * np.sin(grid_t.ravel()),
        ]
    )

    nc = params.n_circ
    i, j = np.meshgrid(np.arange(params.n_axial - 1), np.arange(nc - 1), indexing="ij")
    i, j = i.ravel(), j.ravel()
    v00, v10 = i * nc + j, (i + 1) * nc + j
    v01, v11 = v00 + 1, v10 + 1
    # Alternate the quad diagonal (checkerboard) so both diagonal directions exist.
    flip = (i + j) % 2 == 1
    faces_a = np.where(flip[:, None], np.column_stack([v00, v10, v01]), np.column_stack([v00, v10, v11]))
    faces_b = np.where(flip[:, None], np.column_stack([v10, v11, v01]), np.column_stack([v00, v11, v01]))
    faces = np.vstack([faces_a, faces_b])
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)


@dataclass(frozen=True)
class BoxVolume:
    """Axis-aligned box keep-out volume."""

    name: str
    lo: tuple[float, float, float]
    hi: tuple[float, float, float]

    def contains(self, points: np.ndarray) -> np.ndarray:
        """Boolean mask of points strictly inside the box."""
        p = np.atleast_2d(points)
        return np.all((p > np.asarray(self.lo)) & (p < np.asarray(self.hi)), axis=1)

    def to_mesh(self) -> trimesh.Trimesh:
        """Triangle mesh of the box, for visualisation."""
        lo, hi = np.asarray(self.lo), np.asarray(self.hi)
        return trimesh.creation.box(bounds=np.vstack([lo, hi]))


@dataclass(frozen=True)
class SphereVolume:
    """Spherical keep-out volume."""

    name: str
    center: tuple[float, float, float]
    radius: float

    def contains(self, points: np.ndarray) -> np.ndarray:
        """Boolean mask of points strictly inside the sphere."""
        p = np.atleast_2d(points)
        return np.linalg.norm(p - np.asarray(self.center), axis=1) < self.radius

    def to_mesh(self) -> trimesh.Trimesh:
        """Triangle mesh of the sphere, for visualisation."""
        m = trimesh.creation.icosphere(subdivisions=3, radius=self.radius)
        m.apply_translation(self.center)
        return m


ForbiddenVolume = BoxVolume | SphereVolume


def default_forbidden_volumes(radius: float = 2.0) -> list[ForbiddenVolume]:
    """Three representative keep-out volumes placed across typical cable paths."""
    sphere_c = surface_point(3.0, 50.0, radius)
    return [
        # Fuel line running along the crown of the section.
        BoxVolume("Yakıt hattı", lo=(1.8, -0.45, 1.6), hi=(4.2, 0.45, 2.3)),
        # Swept envelope of a moving-surface actuator.
        SphereVolume("Hareketli yüzey zarfı", center=tuple(sphere_c), radius=0.5),
        # Maintenance access panel (no cables may cross it).
        BoxVolume("Bakım kapağı", lo=(4.2, -1.65, 1.0), hi=(5.0, -1.10, 1.8)),
    ]


def mark_forbidden_vertices(vertices: np.ndarray, volumes: list[ForbiddenVolume]) -> np.ndarray:
    """Boolean mask of mesh vertices lying inside any forbidden volume."""
    mask = np.zeros(len(vertices), dtype=bool)
    for vol in volumes:
        mask |= vol.contains(vertices)
    return mask
