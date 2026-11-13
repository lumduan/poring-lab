"""hotbar_count (dungeon@8.3): the hotbar's stock counts from pixels. Synthetic glyphs only (the
real templates are the client's pixels, never committed). An empty slot (no digit, no icon) is 0;
a slot with an icon but no readable digit is None -- 4.05 a10 started with an EMPTY Fly Wing slot
that the DB called full."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import hotbar_count as hb  # noqa: E402

GLYPHS = {  # 9-row bitmaps cropped to their ink columns, distinct enough for the margin
    "1": [".#.", "##.", ".#.", ".#.", ".#.", ".#.", ".#.", ".#.", "###"],  # tight, as cut()
    "0": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "8": [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", "#...#", "#...#", ".###."],
}


def _t() -> dict[str, np.ndarray]:
    return {d: np.array([[c == "#" for c in row] for row in g]) for d, g in GLYPHS.items()}


def _frame(slot_text: dict[int, str], icon: set[int]) -> np.ndarray:
    g = np.full((60, 400), 235.0)
    t = _t()
    for slot, text in slot_text.items():
        x0, y0, x1, _ = hb.box(slot)
        x = x1 - 1
        for d in reversed(text):  # right-aligned, 1 px apart
            m = t[d]
            x -= m.shape[1]
            g[y0 : y0 + 9, x + 1 : x + 1 + m.shape[1]][m] = 10.0
            x -= 1
    for slot in icon:
        ix0, iy0, ix1, iy1 = hb.ICON
        g[iy0 + 3 : iy1 - 3, ix0 + hb.PITCH * slot + 4 : ix1 + hb.PITCH * slot - 4] = 90.0
    return g


def test_counts_read_right_aligned_digits_per_slot() -> None:
    g = _frame({0: "10", 1: "8"}, icon={0, 1})
    assert hb.read_count(g, 0, _t()) == 10
    assert hb.read_count(g, 1, _t()) == 8


def test_an_empty_slot_is_zero_but_an_icon_without_a_digit_is_unreadable() -> None:
    g = _frame({}, icon={1})
    assert hb.read_count(g, 0, _t()) == 0  # no digit, no icon: the stock is gone
    assert hb.read_count(g, 1, _t()) is None  # an icon with no digit: never guessed


def test_an_unknown_glyph_is_none_not_the_nearest_digit() -> None:
    g = _frame({0: "8"}, icon={0})
    x0, y0, x1, _ = hb.box(0)
    g[y0 + 4, x1 - 6 : x1 - 1] = 10.0  # a bar through the middle: no template within 1 px
    g[y0 + 2, x1 - 6 : x1 - 1] = 10.0
    assert hb.read_count(g, 0, _t()) is None


def test_glyphs_split_at_empty_columns() -> None:
    ink = np.zeros((9, 13), bool)
    ink[:, 1:4] = True
    ink[:, 6:11] = True
    assert [x.shape for x in hb.glyphs(ink)] == [(9, 3), (9, 5)]


def test_an_icons_stray_ink_in_the_tens_place_is_no_digit() -> None:
    """2026-11-13 (the live wing test): the Butterfly Wing's tail on F9 drew a 3-column mark in the
    box's TOP rows before its "5" (the ink as read: rows 0-2 only); the count read None and the
    wing home never pressed. A digit's ink spans the box's height; that mark does not."""
    g = _frame({0: "8"}, icon={0})
    x0, y0, _, _ = hb.box(0)
    for dy, cols in ((0, [2]), (1, [1]), (2, [0])):  # the tail: a short diagonal, top rows only
        for c in cols:
            g[y0 + dy, x0 + c] = 10.0
    assert hb.read_count(g, 0, _t()) == 8
    # ink that spans the height but is no digit still reads None (never guessed)
    g2 = _frame({0: "8"}, icon={0})
    g2[y0 : y0 + 9, x0 + 1] = 10.0
    assert hb.read_count(g2, 0, _t()) is None


def test_every_real_template_spans_the_box_height() -> None:
    """The filter can drop no digit: each committed template touches the top and bottom rows."""
    if not hb.TEMPLATES.exists():  # data/ is local (rule 4); the lab host has it
        return
    for d, m in hb.load().items():
        assert m[0].any() and m[-1].any(), d
