"""loot_sight.py (Batt 2026-10-20 ~19:5x, option C measured offline): the pure parts. The
real-session case is 3.91 run 1 (20261020T183131, 44 kills with the GM still): every cell that
held an item changed by >= 0.079 of its patch; THR 0.04 leaves 8.7 cells a kill "empty", none of
them holding an item (training run; runs 2-4 held out)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import loot_sight as ls  # noqa: E402


def test_a_patch_covers_a_cell_and_clips_to_the_frame() -> None:
    assert ls.patch((100.0, 100.0), (720, 1280)) == (76, 78, 124, 120)
    assert ls.patch((5.0, 5.0), (720, 1280)) == (0, 0, 29, 25)


def test_changed_share_counts_pixels_over_diff_and_off_map_is_unsure() -> None:
    md = np.zeros((40, 60), dtype=np.int16)
    md[10:20, 10:20] = ls.DIFF + 1  # 100 changed pixels
    assert ls.changed_share(md, (0, 0), (0, 0, 60, 40)) == 100 / 2400
    assert ls.changed_share(md, (100, 100), (0, 0, 10, 10)) == 1.0  # outside the map


def test_verdicts_never_call_a_covered_or_changed_cell_empty() -> None:
    cells = [(0, 0), (1, 0), (2, 0), (3, 0)]
    ch = {(0, 0): 0.0, (1, 0): 0.0, (2, 0): 0.5, (3, 0): 0.01}
    v = ls.verdicts(cells, ch, seen=[(1, 0)], covered=[(0, 0)], thr=0.04)
    assert v == {(0, 0): "unsure", (1, 0): "seen", (2, 0): "unsure", (3, 0): "empty"}
    assert ls.verdicts([(9, 9)], {}, [], [], 0.04) == {(9, 9): "unsure"}  # no patch read


def test_no_drop_checks() -> None:
    v = {(0, 0): "unsure", (1, 0): "empty"}
    ch = {(0, 0): 0.9, (1, 0): 0.0, (2, 0): 0.3}
    assert ls.no_drop(v, ch, 0.04, allowed=[(0, 0)]) == (True, False)  # (2, 0) changed
    assert ls.no_drop(v, ch, 0.04, allowed=[(0, 0), (2, 0)]) == (True, True)
    assert ls.no_drop({(0, 0): "seen"}, ch, 0.04, allowed=[(0, 0), (2, 0)]) == (False, False)


def test_server_spans_keep_the_server_cell_and_the_floor_id() -> None:
    ev = [
        {"type": "floor_item_appear", "floor_id": 7, "item_id": 909, "x": 10, "y": 20,
         "sub_x": 12, "sub_y": 3, "t_mono_ns": 1},
        {"type": "floor_item_appear", "floor_id": 8, "item_id": 512, "x": 11, "y": 20,
         "t_mono_ns": 2},
        {"type": "floor_item_vanish", "floor_id": 7, "t_mono_ns": 5},
    ]  # fmt: skip
    sp = ls.server_spans(ev)
    assert (7, 909, 10, 20, 1, 5) in sp
    assert any(f == 8 and t1 > 10**12 for f, _i, _x, _y, _t0, t1 in sp)


def test_summary_counts_the_loss_and_the_no_drop_rates() -> None:
    recs = [
        {"sid": "s", "moved": False, "drops": 1, "cells": {"empty": 10, "unsure": 15},
         "items": [{"ours": True, "verdict": "seen"}, {"ours": True, "verdict": "empty"}],
         "n1": True, "n2": False},
        {"sid": "s", "moved": False, "drops": 0, "cells": {"empty": 6, "unsure": 19},
         "items": [], "n1": True, "n2": True},
        {"sid": "s", "moved": True},
    ]  # fmt: skip
    s = ls.summary(recs)
    assert s["kills"] == 3 and s["gm_still"] == 2 and s["empty_cells_per_kill"] == 8.0
    assert s["LOSS_ours_on_empty"] == 1 and s["ours_items"] == 2 and s["ours_seen_share"] == 0.5
    assert s["N1_FALSE_skip_on_drops"] == 1.0 and s["N2_skip_on_no_drop"] == 1.0
    assert s["N2_FALSE_skip_on_drops"] == 0.0
