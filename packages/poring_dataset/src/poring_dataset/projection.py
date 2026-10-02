"""Cell -> screen projection for the default camera (B4, docs/phase2-plan.md).

RO draws a 3-D scene through a perspective camera; with a FIXED camera (the default after a map
change: docs/benchmarks/SPEC.md) and the player at the screen centre, the ground plane maps to the
screen by a homography. Cell offsets from the player (dx, dy) -> pixels (u, v) in GAME_REGION.

Fitted from correspondences by the normalised DLT (Hartley): the click grid (click pixel <-> the
cell the client itself asked to walk to, `self_move_request`) and GM-spawned monsters (their cell
from packets <-> their sprite's detected foot point). Residuals are reported in pixels.

What breaks it -- and how a session detects it:
  * camera rotation (right-drag) or zoom (wheel): every such input is in the input log; frames after
    one are `camera_dirty` until the next camera reset (a map change);
  * terrain height: the homography models a flat ground; residuals are reported per height class.
"""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

Array = npt.NDArray[np.float64]


def _normaliser(points: Array) -> Array:
    centre = points.mean(axis=0)
    scale = np.sqrt(2) / max(float(np.mean(np.linalg.norm(points - centre, axis=1))), 1e-9)
    return np.array(
        [[scale, 0, -scale * centre[0]], [0, scale, -scale * centre[1]], [0, 0, 1]], dtype=float
    )


def fit_homography(src: Array, dst: Array) -> Array:
    """3x3 H with dst ~ H @ [src, 1]; needs >= 4 non-collinear correspondences."""
    src, dst = np.asarray(src, dtype=float), np.asarray(dst, dtype=float)
    if src.shape != dst.shape or src.shape[0] < 4 or src.shape[1] != 2:
        raise ValueError("need N>=4 correspondences of shape (N, 2)")
    t_src, t_dst = _normaliser(src), _normaliser(dst)
    s = (t_src @ np.c_[src, np.ones(len(src))].T).T
    d = (t_dst @ np.c_[dst, np.ones(len(dst))].T).T
    rows = []
    for (x, y, _), (u, v, _) in zip(s, d, strict=True):
        rows.append([-x, -y, -1, 0, 0, 0, u * x, u * y, u])
        rows.append([0, 0, 0, -x, -y, -1, v * x, v * y, v])
    _, _, vt = np.linalg.svd(np.asarray(rows))
    h = vt[-1].reshape(3, 3)
    h = np.linalg.inv(t_dst) @ h @ t_src
    return np.asarray(h / h[2, 2], dtype=float)


def project(h: Array, points: Array) -> Array:
    pts = np.c_[np.asarray(points, dtype=float), np.ones(len(points))]
    out = (h @ pts.T).T
    return np.asarray(out[:, :2] / out[:, 2:3], dtype=float)


@dataclass(frozen=True)
class Fit:
    h: Array
    residuals_px: Array  # per correspondence, Euclidean

    @property
    def median_px(self) -> float:
        return float(np.median(self.residuals_px))

    @property
    def p95_px(self) -> float:
        return float(np.percentile(self.residuals_px, 95))


def fit(src: Array, dst: Array) -> Fit:
    h = fit_homography(src, dst)
    residuals = np.linalg.norm(project(h, src) - np.asarray(dst, dtype=float), axis=1)
    return Fit(h, residuals)
