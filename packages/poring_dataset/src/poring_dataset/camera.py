"""RO's default camera as a physical model: perspective, looking at the player, a few parameters
(Phase 2, B4 follow-up; Batt 2026-10-03: "port the camera model, fit our calibration as a camera,
keep the winner").

PORTED (the model, re-expressed in numpy; no code copied verbatim) from two permissively licensed
clients, read at these exact commits (THIRD_PARTY.md):
  * nmeylan/nostalro-client @ 15b3029 (Apache-2.0), lib/renderer/src/camera.rs: the eye on a
    sphere around the target (yaw, pitch, distance), look-at, a 15 degree vertical FOV, default
    pitch 55 degrees;
  * vE5li/korangar @ e14d320 (MIT), korangar/src/world/cameras/player.rs: the same rig (pitch -55
    degrees, FOV 15.5 degrees, default distance 400).
Both agree on the rig; the numbers here are FITTED to our client, not taken from either.

World frame (ours): X east = cell dx * 5, Z north = cell dy * 5 (5 world units per GAT cell), Y up
= altitude (a GAT height is negative-up, so up = -height). The target is the player's feet. With
yaw 0 the eye is south of and above the target, looking north; screen v grows downwards.

Why it can beat a homography: a homography maps ONE plane. The camera is a 3-D projection, so a
cell's ALTITUDE (from the map's GAT) moves its pixel the way the client draws it -- the flat-ground
assumption is the first suspect for the projection's residual tail (phase2-plan B4).
"""

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import numpy.typing as npt

Array = npt.NDArray[np.float64]
# offsets from the player (N, 2) cells, the player's map cell -> pixels (N, 2)
Projector = Callable[[Array, tuple[int, int]], Array]
GAT_DIR = Path(os.environ.get("PORING_GAT_DIR", "/dev/shm/poring-lab-tmp/gat/data"))
CELL = 5.0  # world units per GAT cell
NAMES = ("yaw", "pitch", "distance", "fov", "cx", "cy")


@dataclass(frozen=True)
class Camera:
    yaw: float  # radians, rotation of the eye around the vertical axis
    pitch: float  # radians above the horizon
    distance: float  # eye <-> target, world units
    fov: float  # vertical field of view, radians
    cx: float  # where the target lands on screen (pixels)
    cy: float
    height: int = 720  # the client area's height in pixels (the FOV spans it)

    def vector(self) -> Array:
        return np.array([getattr(self, n) for n in NAMES], dtype=float)

    @classmethod
    def from_vector(cls, v: Array, height: int = 720) -> "Camera":
        yaw, pitch, distance, fov, cx, cy = (float(x) for x in v)
        return cls(yaw, pitch, distance, fov, cx, cy, height=height)

    def basis(self) -> tuple[Array, Array, Array, Array]:
        """(eye, right, up, forward) in the world frame."""
        cp, sp = np.cos(self.pitch), np.sin(self.pitch)
        offset = np.array([-np.sin(self.yaw) * cp, sp, -np.cos(self.yaw) * cp]) * self.distance
        eye = offset  # the target is the origin
        forward = -offset / np.linalg.norm(offset)
        world_up = np.array([0.0, 1.0, 0.0])
        right = np.cross(world_up, forward)
        right /= np.linalg.norm(right)
        up = np.cross(forward, right)
        return eye, right, up, forward

    def project(self, cells: Array, altitude: Array | None = None) -> Array:
        """Cell offsets from the player (N, 2) [+ altitude relative to the player's cell, world
        units, up positive] -> pixels (N, 2) in the client area."""
        cells = np.asarray(cells, dtype=float)
        alt = np.zeros(len(cells)) if altitude is None else np.asarray(altitude, dtype=float)
        world = np.c_[cells[:, 0] * CELL, alt, cells[:, 1] * CELL]
        eye, right, up, forward = self.basis()
        rel = world - eye
        z = rel @ forward
        f = (self.height / 2) / np.tan(self.fov / 2)
        u = self.cx + f * (rel @ right) / z
        v = self.cy - f * (rel @ up) / z
        return np.asarray(np.c_[u, v], dtype=float)


@dataclass(frozen=True)
class CameraFit:
    camera: Camera
    residuals_px: Array
    free: tuple[str, ...]

    @property
    def median_px(self) -> float:
        return float(np.median(self.residuals_px))

    @property
    def p95_px(self) -> float:
        return float(np.percentile(self.residuals_px, 95))


def _residuals(
    cam: Camera, free: tuple[str, ...], x: Array, cells: Array, px: Array, alt: Array | None
) -> Array:
    values = {n: float(v) for n, v in zip(free, x, strict=True)}
    trial = replace(cam, **values)  # type: ignore[arg-type]  # only float fields are free
    return (trial.project(cells, alt) - px).ravel()


def fit_camera(
    cells: Array,
    px: Array,
    *,
    altitude: Array | None = None,
    start: Camera | None = None,
    free: tuple[str, ...] = ("yaw", "pitch", "distance", "cx", "cy"),
    iterations: int = 200,
) -> CameraFit:
    """Levenberg-Marquardt on the pixel residuals (numeric Jacobian). ``free``: the parameters
    fitted; the rest stay at ``start`` (default: the clients' rig, FOV 15 degrees)."""
    cells, px = np.asarray(cells, dtype=float), np.asarray(px, dtype=float)
    best: CameraFit | None = None
    starts = [start] if start is not None else [
        Camera(np.radians(y), np.radians(55), 400.0, np.radians(15), 640.0, 360.0)
        for y in range(0, 360, 45)
    ]  # fmt: skip
    for cam0 in starts:
        x = np.array([getattr(cam0, n) for n in free], dtype=float)
        lam = 1e-3
        r = _residuals(cam0, free, x, cells, px, altitude)
        cost = float(r @ r)
        for _ in range(iterations):
            jac = np.empty((len(r), len(x)))
            for j in range(len(x)):
                step = 1e-6 * max(1.0, abs(x[j]))
                xp = x.copy()
                xp[j] += step
                jac[:, j] = (_residuals(cam0, free, xp, cells, px, altitude) - r) / step
            jtj, jtr = jac.T @ jac, jac.T @ r
            improved = False
            for _ in range(10):
                try:
                    delta = np.linalg.solve(jtj + lam * np.diag(np.diag(jtj) + 1e-12), -jtr)
                except np.linalg.LinAlgError:
                    lam *= 10
                    continue
                xn = x + delta
                rn = _residuals(cam0, free, xn, cells, px, altitude)
                cn = float(rn @ rn)
                if np.isfinite(cn) and cn < cost:
                    x, r, cost, lam, improved = xn, rn, cn, lam / 3, True
                    break
                lam *= 10
            if not improved or float(np.linalg.norm(delta)) < 1e-10:
                break
        fitted = {n: float(v) for n, v in zip(free, x, strict=True)}
        cam = replace(cam0, **fitted)  # type: ignore[arg-type]  # only float fields are free
        res = np.linalg.norm(cam.project(cells, altitude) - px, axis=1)
        if best is None or float(res @ res) < float(best.residuals_px @ best.residuals_px):
            best = CameraFit(cam, res, free)
    assert best is not None
    return best


def camera_from_json(block: dict[str, float], height: int = 720) -> Camera:
    return Camera.from_vector(np.array([float(block[n]) for n in NAMES]), height)


def projector_for(
    camera_json: dict[str, object], map_name: str | None, gat_dir: Path = GAT_DIR
) -> tuple[Projector, str]:
    """(projector, which): the perspective camera + the map's GAT altitude when both exist (the
    held-out winner, 2026-10-03), else the flat homography ``h``. The GAT is client data that
    lives only in /dev/shm (grf_read.py extract --decode-des), never in the repository."""
    from poring_dataset import gat as gatmod
    from poring_dataset.projection import project

    block = camera_json.get("camera")
    path = gat_dir / f"{map_name}.gat" if map_name else None
    if isinstance(block, dict) and path is not None and path.exists():
        cam = camera_from_json(block, int(block.get("height", 720)))
        grid = gatmod.parse(path.read_bytes())

        def perspective(offsets: Array, origin: tuple[int, int]) -> Array:
            return cam.project(offsets, grid.relative_altitude(origin, offsets))

        return perspective, f"camera+gat:{map_name}"
    h = np.asarray(camera_json["h"], dtype=float)
    return (lambda offsets, _origin: project(h, offsets)), "homography"


def load_camera_json(path: Path) -> dict[str, object]:
    data: dict[str, object] = json.loads(path.read_text())
    return data
