"""scripts/stage_items.py (Batt 2026-10-24 ~16:0x: learn the target drops from pixels): the spot
picker on a synthetic area, and the tool's fixed facts."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import stage_items as si  # noqa: E402


def test_spots_keep_every_offset_inside_and_are_spread() -> None:
    area = np.zeros((100, 120), dtype=bool)
    area[10:90, 10:110] = True
    area[40:60, 50:70] = False  # a hole: no spot whose offsets reach into it
    spots = si.pick_spots(area, n=50, seed=3, sep=20)
    assert 4 <= len(spots) <= 50
    for x, y in spots:
        for dx, dy in si.OFFSETS:
            assert area[y + dy, x + dx], (x, y, dx, dy)
    for i, a in enumerate(spots):
        for b in spots[i + 1 :]:
            assert max(abs(a[0] - b[0]), abs(a[1] - b[1])) >= 20
    assert si.pick_spots(area, n=5, seed=3, sep=20) == spots[:5]  # seeded
    assert si.pick_spots(np.zeros((10, 10), dtype=bool), n=3, seed=0) == []


def test_the_four_targets_and_offsets() -> None:
    """Batt's four target items (pinned pre-re ids); the camera sees them from 5 places."""
    assert si.TARGETS == {757: "rough_elunium", 756: "rough_oridecon", 604: "dead_branch",
                          518: "honey"}  # fmt: skip
    assert si.OFFSETS[0] == (0, 0) and len(set(si.OFFSETS)) == 5
    assert "data" in si.ICON_DIR.parts  # client pixels: gitignored data/
