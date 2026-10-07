"""Pick an EMPTY walkable cell to click (Post-S2 round B5, 2026-10-04): the activity driver must
never open an NPC dialog or attack a monster by walking onto it.

Two checks, neither reads packets at decision time:
  1. static map data: the cell is walkable in the map's GAT (client data in /dev/shm, never
     committed) -- the rule an indoor map needs most (walls, pews, the altar);
  2. pixels: hover the mouse there and look at a frame decoded after the move. On a walkable,
     empty cell the client draws its GROUND MARKER -- four mint-green chevrons around the hovered
     cell. Over a monster or an NPC it draws another cursor (a sword, a speech bubble), the
     entity's name, and NO ground marker. So: enough marker pixels around the hotspot = an empty
     walkable cell; otherwise pick another cell.

Found live 2026-10-04 (S2 session): the walk cursor itself is ANIMATED (the arrow spins), so a
template of the arrow failed (empty cells 33-70 vs a 16 threshold); the marker separates cleanly
(chevron crops 70-311 px indoors and over grass, Poring hovers 0). No calibration is needed. The
first colour rule (church only) missed the marker over grass, where it is blended: 4 walks in a
3-min outdoor run (C3's first attempt, discarded); the rule now holds in both scenes.

Pure functions here; dataset_activity.py does the I/O.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import numpy.typing as npt

Img = npt.NDArray[np.uint8]
# hotspot-centred crop: the ground marker's chevrons sit ~25-35 px around the hovered cell
CROP = (-45, -45, 90, 90)  # dx, dy, w, h
MIN_MARKER_PX = 40  # measured 2026-10-04: chevrons 70-116 px over grass, 169-311 on the church
#                    floor (90x90 crop); Poring hovers, walls and plain floor 0
# where a walk click may land (client-area pixels): clear of the hotbar (y <= 131), the chat
# window (y >= 531) and the screen edges -- dataset_activity's old fixed band, now per pixel
CLICK_BAND = (40, 150, 1240, 520)  # x0, y0, x1, y1


def crop_region(x: int, y: int) -> tuple[int, int, int, int]:
    """The screen region (x, y, w, h) around the hotspot (x, y) that holds the ground marker."""
    dx, dy, w, h = CROP
    return x + dx, y + dy, w, h


def marker_px(crop: Img) -> int:
    """Pixels of the client's mint ground marker in a BGR(A) crop. Measured live (RGB): ~(125-135,
    205-217, 155-173) on the church floor, ~(47-76, 149-178, 85-97) blended over grass (the marker
    is semi-transparent). A monster's HP bar is a purer green with little blue (~16, 236, 34) and
    is excluded by the blue floor; grass itself fails G - R."""
    b, g, r = (crop[..., i].astype(int) for i in range(3))
    mint = (g - r > 40) & (b - r > 10) & (g > 110) & (g - b > 10) & (b > 70)
    return int(mint.sum())


# walk@2 (docs/demonstrations.md §3.4, 2026-10-07): over RDP the marker renders ~RGB (105-112,
# 196-203, 112-120) -- blue barely above red -- so the mint filter above counts 2-12 px of it. This
# filter was calibrated on RDP hovers (scripts/walk_marker_calibrate.py): a drawn marker gives
# 129-403 px, no marker ~0; the HP bar's pure green fails r > 60.
MIN_MARKER_PX_V2 = 60


def marker_px_v2(crop: Img) -> int:
    b, g, r = (crop[..., i].astype(int) for i in range(3))
    return int(((g - r > 50) & (g - b > 35) & (r > 60) & (b > 60) & (g > 150)).sum())


def is_empty_walk_cell(crop: Img) -> bool:
    return marker_px(crop) >= MIN_MARKER_PX


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
