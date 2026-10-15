"""hp_bar: the monster HP bar finder (a measured cue, not yet a decision input)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import hp_bar  # noqa: E402

SAND = (190, 172, 100)


def _bar(img: np.ndarray, x0: int, y: int, w: int = 60, fill: float = 0.25) -> None:
    img[y, x0 : x0 + w] = (37, 29, 40)  # the border rows
    img[y + 4, x0 : x0 + w] = (31, 35, 44)
    n = int(w * fill)
    for r in (1, 2, 3):
        img[y + r, x0] = img[y + r, x0 + w - 1] = (40, 32, 20)  # the inner edges
        img[y + r, x0 + 1 : x0 + w - 1] = (63, 60, 77)  # navy
        img[y + r, x0 + 1 : x0 + 1 + n] = (243, 253, 94)  # the fill, from the left


def test_find_bars_finds_a_bar_and_its_fill() -> None:
    img = np.full((200, 300, 3), SAND, dtype=np.uint8)
    _bar(img, 100, 80, fill=0.25)
    bars = hp_bar.find_bars(img)
    assert len(bars) == 1
    x0, x1, y, frac = bars[0]
    assert (x0, x1, y) == (100, 159, 80) and 0.2 < frac < 0.3
    assert hp_bar.find_bars(img, (50, 50, 250, 150)) == bars  # frame coordinates with a roi


def test_find_bars_ignores_dark_blocks_and_green_shade() -> None:
    img = np.full((200, 300, 3), SAND, dtype=np.uint8)
    img[50:90, 20:120] = (30, 30, 34)  # a dark block: taller than a bar
    img[120:125, 150:250] = (30, 60, 25)  # green shade, bar-shaped
    assert hp_bar.find_bars(img) == []


def test_near_gm_uses_cells_around_the_gm() -> None:
    u, v = hp_bar.GM_FEET
    w = 60
    assert hp_bar.near_gm((int(u + 34 - w / 2), int(u + 34 + w / 2), int(v + 8), 0.5))
    assert not hp_bar.near_gm((int(u + 5 * 34 - w / 2), int(u + 5 * 34 + w / 2), int(v + 8), 0.5))
