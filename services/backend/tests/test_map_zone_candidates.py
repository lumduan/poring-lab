"""map_zone_candidates.py (Batt 2026-10-20 ~21:0x, MAP TRAPS: help him author the zones): the pure
parts on a fixture map. The real case is prt_fild08's south-east pocket (2395 cells behind ONE
2-cell entrance at x 319-320, y 89-91; the bot's time there 310.7 s a run-hour over 18.1 h of
v43+ runs, kills 0.37 / min inside vs 1.89 outside)."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import map_zone_candidates as mz  # noqa: E402


def fixture() -> np.ndarray:
    """A 40 x 30 map ([y, x]): an open field (x 1..18), a wall at x 19..20 with a 2-cell door at
    y 14..15, a room behind it (x 21..38)."""
    ok = np.zeros((30, 40), dtype=bool)
    ok[1:29, 1:19] = True
    ok[1:29, 21:39] = True
    ok[14:16, 19:21] = True
    return ok


def test_chess_distance_is_one_next_to_a_wall() -> None:
    ok = fixture()
    d = mz.chess_distance(ok)
    assert d[0, 0] == 0 and d[1, 1] == 1 and d[10, 10] == 9  # x 19 is the wall
    assert d[14, 19] == 1  # inside the 2-cell door


def test_the_room_behind_the_door_is_a_pocket() -> None:
    ok = fixture()
    reg, _d = mz.regions(ok)
    assert reg[10, 5] != reg[10, 30]  # the field and the room are different regions
    dr = mz.doors(reg, ok)
    sizes = Counter(int(v) for v in reg[reg >= 0].ravel())
    pk = mz.pockets(sizes, dr, max_door=4, min_room=50)
    assert len(pk) == 1
    cut, behind = pk[0]
    assert dr[cut]["width"] <= 2
    assert int(reg[10, 30]) in behind and int(reg[10, 5]) not in behind
    line = mz.door_line(dr[cut], ok)
    assert all(abs(x - 19.5) <= 2 for x, _y in line)  # across the door, at the wall


def test_a_room_with_two_doors_is_no_pocket() -> None:
    ok = fixture()
    ok[3:5, 19:21] = True  # a second door: cutting one leaves the room reachable
    reg, _d = mz.regions(ok)
    dr = mz.doors(reg, ok)
    sizes = Counter(int(v) for v in reg[reg >= 0].ravel())
    assert mz.pockets(sizes, dr, max_door=4, min_room=50) == []
