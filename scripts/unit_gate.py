"""walk@11's click-instant unit gate (Batt, 2026-10-08, decision 3): PREDICTION, not a later check.

The cursor read and its re-check happen BEFORE the click; a unit can arrive at the click point in
between (the 2026-10-07/08 attacks), and the drawn cursor near an NPC's edge read WALK while the
client contacted the NPC (the replay). So, on the frame used for the click decision:
1. the CPU detector (unit_detector.py) finds every player / monster / npc;
2. each unit's cell = the client's pick under its feet (poring_dataset.picking);
3. WORST-CASE ENVELOPE (Batt's choice, no tracker): within the horizon H (measured: the frame's
   age at the click + the click's latency to the client) a unit can be anywhere within
   ceil(H / its fastest speed) cells, + ONE MORE STEP; static NPCs stay put. Its detected box is
   moved to every one of those cells (the projected displacement);
4. the click point must lie at least MARGIN_PX outside every such box. Otherwise it is refused
   and the rule moves the click along the polyline (a covered point).
Our own character (the box at our feet) is not a unit to avoid.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

MARGIN_PX = 12.0  # beyond a moved box: the detector's box error + the cursor hotspot
LATENCY_S = 0.36  # frame staleness (RDP packet->frame p95 157 ms) + click->server p99 197 ms
PLAYER_MS_PER_CELL = 150  # the default walk speed of a character
SELF_PX = 24.0  # a box whose feet are this close to ours is our own character


@dataclass(frozen=True)
class Envelope:
    cls: str
    cell: tuple[int, int]  # relative to our belief
    radius: int
    boxes: list[tuple[float, float, float, float]] = field(default_factory=list)


def radius_cells(cls: str, horizon_s: float, monster_ms_per_cell: int) -> int:
    """How far a unit can be at the click's arrival, plus one more step (Batt)."""
    if cls == "npc":
        return 0
    ms = PLAYER_MS_PER_CELL if cls == "player" else monster_ms_per_cell
    return math.ceil(horizon_s * 1000 / ms) + 1


def point_box_distance(u: float, v: float, b: tuple[float, float, float, float]) -> float:
    """0 inside the box, else the Euclidean distance to it."""
    dx = max(b[0] - u, 0.0, u - b[2])
    dy = max(b[1] - v, 0.0, v - b[3])
    return math.hypot(dx, dy)


def envelopes(boxes: Sequence[Any], camera: Any, gat: Any, belief: tuple[int, int],
              horizon_s: float, monster_ms_per_cell: int,
              pick: Any = None) -> list[Envelope]:  # fmt: skip
    """Every detected unit's worst-case envelope on screen. `pick(camera, gat, belief, px)` ->
    (N, 2) cell offsets (poring_dataset.picking.pick_cells; injectable for tests)."""
    if pick is None:
        from poring_dataset.picking import pick_cells as pick
    self_px = camera.project(np.zeros((1, 2)), np.zeros(1))[0]
    out: list[Envelope] = []
    for b in boxes:
        fx, fy = b.foot
        if math.hypot(fx - self_px[0], fy - self_px[1]) <= SELF_PX:
            continue  # our own character
        cell = tuple(int(c) for c in pick(camera, gat, belief, np.array([[fx, fy]]))[0])
        if abs(cell[0]) > 10**5:  # nothing picked under its feet: use the nearest flat cell
            cell = _nearest_cell(camera, fx, fy)
        rad = radius_cells(b.cls, horizon_s, monster_ms_per_cell)
        cells = np.array([(cell[0] + dx, cell[1] + dy) for dx in range(-rad, rad + 1)
                          for dy in range(-rad, rad + 1)], dtype=float)  # fmt: skip
        one = np.array([cell], dtype=float)
        alt = None if gat is None else gat.relative_altitude(belief, cells)
        alt1 = None if gat is None else gat.relative_altitude(belief, one)
        moved = camera.project(cells, alt) - camera.project(one, alt1)[0]
        out.append(Envelope(b.cls, cell, rad, [(b.x0 + du, b.y0 + dv, b.x1 + du, b.y1 + dv)
                                               for du, dv in moved]))  # fmt: skip
    return out


def _nearest_cell(camera: Any, u: float, v: float) -> tuple[int, int]:
    grid = np.array([(dx, dy) for dx in range(-15, 16) for dy in range(-15, 16)], dtype=float)
    px = camera.project(grid, None)
    k = int(np.argmin(((px - [u, v]) ** 2).sum(1)))
    return int(grid[k, 0]), int(grid[k, 1])


def click_clear(u: float, v: float, envs: Sequence[Envelope],
                margin: float = MARGIN_PX) -> tuple[bool, float, str | None]:  # fmt: skip
    """(ok, the smallest distance to any moved box, the class nearest)."""
    best, who = math.inf, None
    for e in envs:
        for b in e.boxes:
            d = point_box_distance(u, v, b)
            if d < best:
                best, who = d, e.cls
    return best >= margin, best, who
