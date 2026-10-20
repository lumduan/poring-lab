"""deathcell_cues.py (Batt 2026-10-20, step 2's offline study): the pure parts. The 8-run read
(v42 + v44) is in docs/competition.md's loot block."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import deathcell_cues as dc  # noqa: E402


def test_follow_keeps_the_nearest_box_frame_to_frame() -> None:
    far = [500.0, 500.0, 540.0, 540.0, 0.9, "monster"]
    frames = [(1, [[100.0, 100.0, 140.0, 144.0, 0.9, "monster"], far]),
              (2, [[110.0, 104.0, 150.0, 148.0, 0.9, "monster"]]),
              (3, []),  # a missed frame: skipped, the track may come back
              (4, [[118.0, 106.0, 158.0, 150.0, 0.9, "monster"], far]),
              (9, [[120.0, 106.0, 160.0, 150.0, 0.9, "monster"]])]  # fmt: skip
    trk = dc.follow(frames, 1, 121.0, 140.0, 5)
    assert [t for t, _f in trk] == [1, 2, 4]  # stops at t_end; never jumps to the far box
    assert trk[0][1] == (120.0, 140.0)  # the foot: centre x, bottom - FOOT_LIFT


def test_paired_compares_the_same_kills_only() -> None:
    rows = [{"a": (0, 2, 2), "b": (1, 1, 2)}, {"a": (2, 0, 1)}, {"a": (1, 1, 1), "b": (0, 1, 1)}]
    p = dc.paired(rows, "a", "b")
    assert p["kills"] == 2 and p["items"] == 3
    assert p["a"]["exact"] == 0.5 and p["b"]["exact"] == 0.5 and p["a"]["drops_in_3x3"] == 1.0
    assert (
        dc.at_or_before([(1, "x"), (5, "y")], 4) == "x" and dc.at_or_before([(1, "x")], 0) is None
    )
