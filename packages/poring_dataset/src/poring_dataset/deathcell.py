"""The death cell: a stand-in for the tracker (loot@1 P3; Phase 3 T1 is not built).

For the ONE deliberate target of a kill: the cell its feet were on, on the last frames before it
vanished after the kill -- where its loot falls (rAthena drops a kill's first item ON the cell the
monster died on and the next ones on fixed neighbours: ``DROP_PATTERN``). Pixels in only: the
boxes come from the unit detector, the foot pixel goes through the picking model
(``poring_dataset.picking``: the first GAT top surface the camera ray comes down through) to a
cell. Packets never reach it (rule 1); they only judge it offline (the target's
``entity_vanish`` with reason "died" and its last position in ``Timeline``, which plays its die
animation where it fell).

The rule, fixed here before any trial:
  1. The target is the matched box per frame (the caller's lock / matching), None when the
     detector did not see it. Frames are in time order.
  2. It VANISHED when its last sighting is followed by at least ``gone_frames`` frames without it.
     A target still seen at the end is "still_visible"; a shorter gap is "gap_too_short".
  3. The feet of the last ``window`` sightings up to the last one (bottom centre of the box, as
     ``scripts/unit_detector.Box.foot``) go through ``cell_of``. The answer is the LAST sighting's
     cell (the most recent valid one when the picking model has none for it).
  4. Every valid cell of that window must lie within ``max_spread`` cells (Chebyshev) of the
     answer, or the target was still moving: "unstable", no cell. None of them valid: "no_cell".
  5. confidence = (the window's cells equal to the answer / window) x min(1, the last
     sighting's detector score / ``full_score``). It ranks; it does not gate.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

Cell = tuple[int, int]
Box = tuple[float, float, float, float]  # x0, y0, x1, y1 in client pixels
CellOf = Callable[[tuple[float, float], int], Cell | None]  # (foot pixel, frame index) -> cell


@dataclass(frozen=True, slots=True)
class Sighting:
    t_ns: int
    box: Box | None  # the target's box on this frame, None when it was not detected
    score: float = 1.0  # the detector's confidence for that box


@dataclass(frozen=True, slots=True)
class DeathCell:
    cell: Cell | None
    confidence: float
    reason: str  # ok | never_seen | still_visible | gap_too_short | no_cell | unstable
    last_seen_ns: int | None = None
    gone_ns: int | None = None  # the first frame without the target after its last sighting
    cells: tuple[Cell | None, ...] = ()  # the window's cells, oldest first


def foot(box: Box) -> tuple[float, float]:
    """The unit's feet: the box's bottom centre (scripts/unit_detector.Box.foot)."""
    x0, _, x1, y1 = box
    return (x0 + x1) / 2, y1


def death_cell(
    sightings: Sequence[Sighting],
    cell_of: CellOf,
    *,
    window: int = 3,
    gone_frames: int = 3,
    max_spread: int = 1,
    full_score: float = 0.5,
) -> DeathCell:
    """The target's last foot cell before it vanished (see the module docstring)."""
    if any(b.t_ns < a.t_ns for a, b in zip(sightings, sightings[1:], strict=False)):
        raise ValueError("sightings must be in time order")
    seen = [i for i, s in enumerate(sightings) if s.box is not None]
    if not seen:
        return DeathCell(None, 0.0, "never_seen")
    last = seen[-1]
    last_ns = sightings[last].t_ns
    after = len(sightings) - 1 - last
    if after == 0:
        return DeathCell(None, 0.0, "still_visible", last_ns)
    gone_ns = sightings[last + 1].t_ns
    if after < gone_frames:
        return DeathCell(None, 0.0, "gap_too_short", last_ns, gone_ns)
    recent = seen[-window:]
    cells: list[Cell | None] = []
    for i in recent:
        box = sightings[i].box
        assert box is not None
        cells.append(cell_of(foot(box), i))
    valid = [c for c in cells if c is not None]
    if not valid:
        return DeathCell(None, 0.0, "no_cell", last_ns, gone_ns, tuple(cells))
    answer = valid[-1]
    spread = max(max(abs(c[0] - answer[0]), abs(c[1] - answer[1])) for c in valid)
    if spread > max_spread:
        return DeathCell(None, 0.0, "unstable", last_ns, gone_ns, tuple(cells))
    agree = sum(1 for c in cells if c == answer) / max(1, window)
    conf = agree * min(1.0, sightings[last].score / full_score)
    return DeathCell(answer, float(conf), "ok", last_ns, gone_ns, tuple(cells))


# Where a kill's drops fall at the pinned rAthena (mob.cpp:2531-2551 mob_process_drop_list): the
# first ON the death cell, then the pattern loops SE -> W -> N -> SE ...; a cell holding a char or
# pet moves that item to a free cell within 1 (map.cpp:2016-2027). RO map coordinates: y grows
# north; rAthena dirx/diry give SE = (+1, -1), W = (-1, 0), N = (0, +1).
DROP_PATTERN: tuple[Cell, ...] = ((0, 0), (1, -1), (-1, 0), (0, 1))


def scan_order(center: Cell, radius: int = 1) -> list[Cell]:
    """The cells to hover-scan around a death cell (loot@1 step 4: the 3 x 3): the server's drop
    pattern first (death cell, SE, W, N), then the other cells within ``radius``, edge neighbours
    before corners."""
    cx, cy = center
    first = [(cx + dx, cy + dy) for dx, dy in DROP_PATTERN
             if max(abs(dx), abs(dy)) <= radius]  # fmt: skip
    rest = [(cx + dx, cy + dy) for dy in range(-radius, radius + 1)
            for dx in range(-radius, radius + 1) if (cx + dx, cy + dy) not in first]  # fmt: skip
    rest.sort(key=lambda c: (abs(c[0] - cx) + abs(c[1] - cy), -c[1], c[0]))
    return [*first, *rest]
