"""hand_truth.py (3.90): the HAND scan's reads against the server's floor items -- pure parts.
The real-session positive case (v49's stopped run 1, 20261020T135303): all 8 "hand" reads had a
floor item within 1 cell of the hovered cell (and each became a pickup of it)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import hand_truth as ht  # noqa: E402

S = 1_000_000_000


def test_floor_spans_close_on_vanish_and_stay_open_at_the_end() -> None:
    pk = [
        {"type": "floor_item_appear", "floor_id": 1, "x": 10, "y": 20, "t_mono_ns": 1 * S},
        {"type": "floor_item_appear", "floor_id": 2, "x": 11, "y": 20, "t_mono_ns": 2 * S},
        {"type": "floor_item_vanish", "floor_id": 1, "t_mono_ns": 5 * S},
    ]
    sp = ht.floor_spans(pk)
    assert (10, 20, 1 * S, 5 * S) in sp
    assert any(x == 11 and t1 > 100 * S for x, _y, _t0, t1 in sp)


def test_reads_on_the_cell_near_it_and_after_the_pickup() -> None:
    sp = [(10, 20, 1 * S, 5 * S)]
    hovers = [
        {"t_ns": 2 * S, "cell": [10, 20], "seen": "hand"},  # on the cell
        {"t_ns": 2 * S, "cell": [10, 19], "seen": "hand"},  # one cell off (the belief)
        {"t_ns": 2 * S, "cell": [13, 20], "seen": "empty"},  # nothing near
        {"t_ns": 6 * S, "cell": [10, 20], "seen": "empty"},  # picked up already
    ]
    c = ht.truth(hovers, sp)
    assert c["hand"] == 2 and c["hand|item_on_cell"] == 1 and c["hand|item_within_1"] == 2
    assert c["empty"] == 2 and c["empty|item_on_cell"] == 0 and c["empty|item_within_1"] == 0
