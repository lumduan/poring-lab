"""Pick an EMPTY walkable cell to click (Post-S2 round B5, 2026-10-04): the activity driver must
never open an NPC dialog or attack a monster by walking onto it.

Two checks, neither reads packets at decision time:
  1. static map data: the cell is walkable in the map's GAT (client data in /dev/shm, never
     committed) -- the rule an indoor map needs most (walls, pews, the altar);
  2. pixels: hover the mouse there, wait for a frame decoded after the move, and compare the cursor
     crop with the calibrated WALK cursor. Over an NPC or a monster the client draws another
     cursor (a speech bubble, a sword), so anything that is not the walk cursor means "pick another
     cell".

The walk-cursor template is calibrated in the scene (``calibrate``): hover a few cells, grab each
crop WITH the cursor and again with the cursor moved away, keep the pixels the cursor changes
(the mask) and their median (the reference). Outliers -- a hover that landed on an entity -- are
dropped by their distance to the median. The template is client-drawn pixels: it lives under
data/ (gitignored), never in the repository.

Pure functions here; dataset_activity.py does the I/O.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

Img = npt.NDArray[np.uint8]
# hotspot-relative crop: the client draws its cursor down-right of the hotspot
CROP = (-6, -6, 44, 44)  # dx, dy, w, h
DIFF_MIN = 24.0  # grey levels: a pixel the cursor changes
MASK_SHARE = 0.5  # ... in at least this share of the calibration samples
MIN_MASK_PX = 40  # fewer: no cursor seen (the calibration failed)
OUTLIER_FACTOR = 2.5  # a calibration sample this far above the median distance is dropped
THRESHOLD_MARGIN = 1.5  # the check's threshold = worst kept sample x this (+ THRESHOLD_FLOOR)
THRESHOLD_FLOOR = 6.0
# where a walk click may land (client-area pixels): clear of the hotbar (y <= 131), the chat
# window (y >= 531) and the screen edges -- dataset_activity's old fixed band, now per pixel
CLICK_BAND = (40, 150, 1240, 520)  # x0, y0, x1, y1


def grey(img: Img) -> npt.NDArray[np.float64]:
    """BGRA/BGR -> grey (float)."""
    b, g, r = (img[..., i].astype(float) for i in range(3))
    return np.asarray(0.114 * b + 0.587 * g + 0.299 * r, dtype=float)


def crop_region(x: int, y: int) -> tuple[int, int, int, int]:
    """The screen region (x, y, w, h) holding the cursor drawn at the hotspot (x, y)."""
    dx, dy, w, h = CROP
    return x + dx, y + dy, w, h


@dataclass(frozen=True)
class CursorTemplate:
    mask: npt.NDArray[np.bool_]
    ref: npt.NDArray[np.float64]
    threshold: float
    samples: int

    def distance(self, crop: Img) -> float:
        """Mean absolute grey difference on the cursor's own pixels."""
        return float(np.abs(grey(crop)[self.mask] - self.ref[self.mask]).mean())

    def is_walk_cursor(self, crop: Img) -> bool:
        return self.distance(crop) <= self.threshold

    def save(self, path: Path, meta: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp.npz")
        np.savez_compressed(tmp, mask=self.mask, ref=self.ref, threshold=self.threshold,
                            samples=self.samples, meta=json.dumps(meta))  # fmt: skip
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> CursorTemplate:
        with np.load(path) as z:
            return cls(z["mask"].astype(bool), z["ref"].astype(float), float(z["threshold"]),
                       int(z["samples"]))  # fmt: skip


class CalibrationFailed(RuntimeError):
    pass


def build_template(with_cursor: Sequence[Img], without: Sequence[Img]) -> CursorTemplate:
    """From paired crops (the same region with the cursor on it, then with the cursor away)."""
    if len(with_cursor) != len(without) or len(with_cursor) < 3:
        raise CalibrationFailed("need >= 3 paired crops")
    on = np.stack([grey(c) for c in with_cursor])
    off = np.stack([grey(c) for c in without])
    changed = np.abs(on - off) > DIFF_MIN
    mask = changed.mean(axis=0) >= MASK_SHARE
    if int(mask.sum()) < MIN_MASK_PX:
        raise CalibrationFailed(f"no cursor seen ({int(mask.sum())} px changed)")
    ref = np.median(on, axis=0)
    dist = np.abs(on[:, mask] - ref[mask]).mean(axis=1)
    keep = dist <= max(np.median(dist) * OUTLIER_FACTOR, THRESHOLD_FLOOR)
    if int(keep.sum()) < 3:
        raise CalibrationFailed("the samples disagree (hovers over entities?)")
    ref = np.median(on[keep], axis=0)
    dist = np.abs(on[keep][:, mask] - ref[mask]).mean(axis=1)
    threshold = float(dist.max()) * THRESHOLD_MARGIN + THRESHOLD_FLOOR
    return CursorTemplate(mask, ref, threshold, int(keep.sum()))


Projector = Callable[[npt.NDArray[np.float64], tuple[int, int]], npt.NDArray[np.float64]]


def pick_cell(
    rng: object,
    pos: tuple[int, int],
    walkable: npt.NDArray[np.bool_] | None,
    projector: Projector,
    *,
    dx_range: tuple[int, int] = (2, 6),
    dy_range: tuple[int, int] = (2, 4),
    band: tuple[int, int, int, int] = CLICK_BAND,
    reject: Callable[[int, int], bool] | None = None,
    tries: int = 30,
) -> tuple[int, int, float, float] | None:
    """(dx, dy, u, v): a cell 2-6 across and 2-4 up/down from ``pos`` (cells; seeded ``rng`` with
    choice/randint, like random.Random), walkable in the GAT (when known), whose click pixel (the
    map's projector, client area) is inside ``band`` and that ``reject`` does not refuse."""
    x0, y0, x1, y1 = band
    for _ in range(tries):
        dx = rng.choice([-1, 1]) * rng.randint(*dx_range)  # type: ignore[attr-defined]
        dy = rng.choice([-1, 1]) * rng.randint(*dy_range)  # type: ignore[attr-defined]
        cx, cy = pos[0] + dx, pos[1] + dy
        if walkable is not None:
            h, w = walkable.shape
            if not (0 <= cx < w and 0 <= cy < h) or not walkable[cy, cx]:
                continue
        ((u, v),) = projector(np.array([[float(dx), float(dy)]]), pos)
        if not (x0 <= u <= x1 and y0 <= v <= y1):
            continue
        if reject is not None and reject(int(round(u)), int(round(v))):
            continue
        return dx, dy, float(u), float(v)
    return None
