"""loot_sight.py (Batt 2026-10-20 ~19:5x, option C measured offline): the pure parts. The
real-session case is 3.91 run 1 (20261020T183131, 44 kills with the GM still): every cell that
held an item changed by >= 0.079 of its patch; THR 0.04 leaves 8.7 cells a kill "empty", none of
them holding an item (training run; runs 2-4 held out)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

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


def test_line_anchor_is_the_first_exp_line_after_the_kill() -> None:
    """Live timing: the runner knows of a kill at the EXP line's first frame (p50 0.33 s later)."""
    s = ls.NS
    lines = [int(1.2 * s), int(5.3 * s), int(9.9 * s)]
    assert ls.line_anchor(1 * s, lines) == int(1.2 * s)
    assert ls.line_anchor(5 * s, lines) == int(5.3 * s)
    assert ls.line_anchor(6 * s, lines) is None  # 3.9 s later: not this kill's line
    assert ls.line_anchor(10 * s, lines) is None


# --- the SHARED classifier (v54, the fast scan: hunt_flow calls the same ``classify``) ----------


def _scene(seed: int = 7) -> np.ndarray:
    """A textured 720 x 1280 ground (smooth blobs: phase correlation registers it)."""
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 256, size=(90, 160, 3)).astype(np.uint8)
    return np.ascontiguousarray(np.repeat(np.repeat(small, 8, axis=0), 8, axis=1))


def _grid(own: tuple[int, int]) -> tuple[list[tuple[int, int]], list[tuple[float, float]]]:
    """The 25 cells around ``own`` and synthetic centres: 40 px a column, 30 px a row, the GM's
    own cell at (640, 340) -- only it and the cells right above / below it fall in the GM's box."""
    cells = ls.five_by_five(own)
    uv = [(640.0 + 40 * (c[0] - own[0]), 340.0 + 30 * (c[1] - own[1])) for c in cells]
    return cells, uv


def test_five_by_five_is_row_major_with_the_own_cell_at_12() -> None:
    cells = ls.five_by_five((10, 20))
    assert len(cells) == 25 and len(set(cells)) == 25 and cells[12] == (10, 20)
    assert cells[0] == (8, 18) and cells[1] == (9, 18) and cells[24] == (12, 22)


def test_classify_a_changed_patch_is_unsure_an_unchanged_one_empty() -> None:
    own = (100, 100)
    cells, uv = _grid(own)
    before = _scene()
    after = before.copy()
    u, v = uv[cells.index((102, 100))]  # the east edge cell: an item drawn there
    after[int(v) - 8 : int(v) + 8, int(u) - 10 : int(u) + 10] = (250, 30, 200)
    got = ls.classify(before, after, cells, uv, own, ground=[])
    ver = got["verdicts"]
    assert ver[(102, 100)] == "unsure" and got["changed"][(102, 100)] > ls.THR
    covered = {own, (100, 99), (100, 101)}  # the GM's own cell + the centres inside its sprite
    assert got["covered"] == covered and all(ver[c] == "unsure" for c in covered)
    others = [c for c in cells if c not in covered and c != (102, 100)]
    assert others and all(ver[c] == "empty" for c in others)
    # the matcher's ground point on a cell -> "seen" (hovered first), even with no change there
    got2 = ls.classify(before, after, cells, uv, own, ground=[uv[cells.index((98, 98))]])
    assert got2["verdicts"][(98, 98)] == "seen"


def test_classify_registers_the_camera_jitter_and_a_big_shift_is_unsure() -> None:
    own = (5, 5)
    cells, uv = _grid(own)
    before = _scene(11)
    after = np.ascontiguousarray(np.roll(before, (3, -2), axis=(0, 1)))  # 1-3 px of jitter
    got = ls.classify(before, after, cells, uv, own, ground=[])
    assert got["shift"] != (0, 0)
    assert sum(v == "empty" for v in got["verdicts"].values()) == 22  # all but the 3 covered
    # --max-shift (loot_sight's study option): a shift above it makes every cell changed
    got3 = ls.classify(before, after, cells, uv, own, ground=[], max_shift_px=1)
    assert set(got3["verdicts"].values()) == {"unsure"}


def test_classify_is_channel_order_agnostic() -> None:
    """The runner hands BGR grabs; the recordings are RGB: the diff ignores the order."""
    own = (40, 40)
    cells, uv = _grid(own)
    before = _scene(3)
    after = before.copy()
    after[330:350, 715:725] = (10, 240, 10)
    a = ls.classify(before, after, cells, uv, own, ground=[])
    b = ls.classify(before[..., ::-1].copy(), after[..., ::-1].copy(), cells, uv, own, ground=[])
    assert a["verdicts"] == b["verdicts"]


# A REAL session (v52 run 1, 3.93): loot_sight's records for its first 12 kills (--from-line,
# before 0.45 s, stand 0.5 s, THR 0.04, --all-kills), taken from the run BEFORE the classifier was
# moved into ``classify`` (2026-10-21): (kill t, seen / unsure / empty cells, the verdicts of the
# floor items on the 25 cells -- "*" not ours --, the matcher's hits, the registration shift). The
# whole session's records (92 kills) were byte-identical before / after the refactor.
REAL_SID = "20261021T092850-demo-hunt-flow52"
REAL_12 = [
    (1291648282772284, 0, 14, 11, (), 0, (-1, 0)),
    (1291687251608188, 3, 11, 11, ("seen*", "unsure"), 1, (0, 0)),
    (1291734130565996, 0, 14, 11, ("unsure",), 0, (-6, 0)),
    (1291815453243229, 2, 13, 10, (), 1, (0, 0)),
    (1291828131217939, 0, 24, 1, ("unsure",), 0, (0, 0)),
    (1291843220610309, 0, 15, 10, (), 0, (0, 0)),
    (1291901771987115, 0, 14, 11, (), 0, (0, 0)),
    (1291909561217290, 0, 11, 14, ("unsure", "unsure"), 0, (4, -7)),
    (1291943542726067, 0, 13, 12, (), 0, (0, 0)),
    (1291968780451532, 3, 4, 18, ("seen", "unsure"), 1, (0, 0)),
    (1291981122255331, 0, 18, 7, (), 1, (0, 0)),
    (1292000243774411, 0, 10, 15, ("unsure",), 0, (0, -6)),
]


def test_the_shared_classifier_reproduces_loot_sight_on_a_real_session() -> None:
    """POSITIVE CASE (real frames, NAS + the session's packets): the shared ``classify`` gives
    loot_sight's pre-refactor numbers, and the same on the frames in the runner's BGR order."""
    import drop_blobs as db
    import item_icons as ii

    if not ((db.DEMO_ROOT / REAL_SID / "packets.jsonl.gz").exists()
            and (db.REC_ROOT / REAL_SID / "frames").is_dir()
            and (ii.ICONS_DIR / "index.json").exists()):  # fmt: skip
        pytest.skip("the real session's packets / frames / item templates are not here")
    for bgr in (False, True):
        recs = ls.session(REAL_SID, 0.5, 0.45, ls.THR, from_line=True, still_only=False,
                          limit=len(REAL_12), bgr=bgr)  # fmt: skip
        got = [(int(r["t"]), r["cells"].get("seen", 0), r["cells"].get("unsure", 0),
                r["cells"].get("empty", 0),
                tuple(sorted(i["verdict"] + ("" if i["ours"] else "*") for i in r["items"])),
                int(r["hits"]), tuple(r["shift"])) for r in recs]  # fmt: skip
        assert got == REAL_12, f"bgr={bgr}"
        # a positive case: our items lay on these cells, and none on an "empty" one
        assert sum(len(r["items"]) for r in recs) == 9  # 8 ours, 1 not ours
        assert not any(i["verdict"] == "empty" for r in recs for i in r["items"])


def test_the_runners_fast_verdicts_give_the_same_classes_on_real_frames() -> None:
    """POSITIVE CASE for the RUNNER's path (hunt_flow.fast_verdicts: BGR grabs, the matcher told
    so, the cells projected by a callable, then the shared ``classify``) on the same real kills:
    the same seen / unsure / empty counts, matcher hits and registration as loot_sight's."""
    from collections import Counter

    import drop_blobs as db
    import hunt_flow as hf
    import item_icons as ii

    if not ((db.DEMO_ROOT / REAL_SID / "packets.jsonl.gz").exists()
            and (db.REC_ROOT / REAL_SID / "frames").is_dir()
            and (ii.ICONS_DIR / "index.json").exists()):  # fmt: skip
        pytest.skip("the real session's packets / frames / item templates are not here")
    import json

    ev = db.load_events(REAL_SID)
    bev = (db.DEMO_ROOT / REAL_SID / "events.jsonl").read_text().splitlines()
    lines = sorted(int(e["line_t_ns"]) for e in map(json.loads, filter(None, bev))
                   if e.get("kind") == "exp_dead" and e.get("line_t_ns"))  # fmt: skip
    pos, proj, frames = db.Positions(ev), db.Projector(), db.load_frames(REAL_SID)
    tpls = ii.load_templates()
    want = {r[0]: r for r in REAL_12[:6]}
    n = 0
    for k in db.kills_with_drops(ev, pos):
        if k.t not in want:
            continue
        la = ls.line_anchor(k.t, lines)
        assert la is not None
        fa = db.frame_at(frames, la + int(0.5 * ls.NS))
        fb = db.frame_before(frames, la - int(0.45 * ls.NS))
        assert fa is not None and fb is not None
        o_a = pos.gm_at(fa[0] - int(0.5 * ls.NS))
        assert o_a is not None
        r0 = (round(o_a[0]), round(o_a[1]))
        before = np.ascontiguousarray(db.read_rgb(fb[1])[..., ::-1])
        stand = np.ascontiguousarray(db.read_rgb(fa[1])[..., ::-1])
        ver, info = hf.fast_verdicts(before, stand, lambda cs, o=o_a: proj.project(o, cs), r0,
                                     tpls, ls.THR)  # fmt: skip
        c = Counter(ver.values())
        w = want[k.t]
        assert (c["seen"], c["unsure"], c["empty"]) == w[1:4], k.t
        assert info["hits"] == w[5] and tuple(info["shift"]) == w[6]
        n += 1
    assert n == 6
