"""poring_env.panelfind (teaching-prerun.md 4f, Batt 2026-11-19): RO's hotbar and Basic Info found
by their SHAPE anywhere on the client -- synthetic frames drawn by the rules the module states
(no client pixels in the repo)."""

from __future__ import annotations

import numpy as np
import pytest

from poring_env import panelfind as pf


def world(h: int = 720, w: int = 1280, seed: int = 0) -> np.ndarray:
    """A busy scene: no uniform line or row anywhere."""
    return np.random.default_rng(seed).uniform(0, 255, (h, w)).astype(np.float32)


def draw_hotbar(lum: np.ndarray, at: tuple[int, int], lines: int = 9, rows: bool = True,
                seed: int = 1) -> np.ndarray:  # fmt: skip
    """The shortcut bar as the module describes it: the top frame rows, 9 slot lines on the
    pitch, an icon (noise) in every slot."""
    rng = np.random.default_rng(seed)
    ox, oy = at
    x0, y0 = ox + pf.HOTBAR_LINE_DX, oy + pf.HOTBAR_LINE_DY
    if rows:
        for depth, (lo, hi) in pf.HOTBAR_ROWS:
            lum[oy + depth, x0 : x0 + pf.HOTBAR_SPAN] = (lo + hi) / 2
    for i in range(pf.HOTBAR_SLOTS):
        x = x0 + pf.HOTBAR_PITCH * i
        lum[y0 : y0 + pf.HOTBAR_BAND, x + 1 : x + 26] = rng.uniform(0, 255, (pf.HOTBAR_BAND, 25))
        if i < lines:
            lum[y0 : y0 + pf.HOTBAR_BAND, x] = 195.0
    return lum


def draw_basic(lum: np.ndarray, at: tuple[int, int], crossed: int = 0, seed: int = 2) -> np.ndarray:
    """Basic Info: its frame rows at their depths, text (noise) between them; ``crossed`` rows
    broken by something over them (the pointer)."""
    rng = np.random.default_rng(seed)
    ox, oy = at
    lum[oy : oy + pf.BASIC_H, ox : ox + pf.BASIC_W] = rng.uniform(0, 255, (pf.BASIC_H, pf.BASIC_W))
    for k, (depth, (lo, hi)) in enumerate(pf.BASIC_ROWS):
        lum[oy + depth, ox : ox + pf.BASIC_W] = (lo + hi) / 2
        if k < crossed:
            lum[oy + depth, ox + 100 : ox + 130] = 0 if lo > 100 else 255
    return lum


@pytest.mark.parametrize("at", [(230, 0), (0, 0), (517, 333), (1280 - 300, 720 - 40)])
def test_the_hotbar_is_found_wherever_it_was_dragged(at: tuple[int, int]) -> None:
    got = pf.find_hotbar(draw_hotbar(world(), at))
    assert got is not None and got.origin == at and (got.score, got.of) == (13, 13)


def test_one_covered_slot_is_still_a_hotbar_two_are_not() -> None:
    assert pf.find_hotbar(draw_hotbar(world(), (400, 200), lines=8)) is not None
    assert pf.find_hotbar(draw_hotbar(world(), (400, 200), lines=7)) is None


def test_a_comb_of_lines_without_the_frame_rows_is_no_hotbar() -> None:
    """The login screen's list drew 8 lines on the pitch (2026-11-19, the lab's frames)."""
    assert pf.find_hotbar(draw_hotbar(world(), (143, 523), rows=False)) is None
    assert pf.find_hotbar(world()) is None


def test_the_recheck_pins_the_hotbar_to_its_row() -> None:
    lum = draw_hotbar(world(), (300, 120))
    assert pf.hotbar_at(lum, (300, 120)) == 13 >= pf.HOTBAR_MIN_AT
    assert pf.hotbar_at(lum, (300, 121)) < pf.HOTBAR_MIN_AT  # one row off: its top rows fail
    assert pf.hotbar_at(lum, (5000, 0)) == 0  # off the frame


@pytest.mark.parametrize("at", [(0, 0), (412, 300), (1280 - 220, 720 - pf.BASIC_H)])
def test_basic_info_is_found_wherever_it_was_dragged(at: tuple[int, int]) -> None:
    got = pf.find_basic_info(draw_basic(world(), at))
    assert got is not None and got.origin == at and got.score == len(pf.BASIC_ROWS)


def test_basic_info_with_one_row_crossed_is_found_with_two_it_is_not() -> None:
    one = pf.find_basic_info(draw_basic(world(), (300, 100), crossed=1))
    assert one is not None and one.score == len(pf.BASIC_ROWS) - 1
    assert pf.find_basic_info(draw_basic(world(), (300, 100), crossed=2)) is None
    assert pf.find_basic_info(world()) is None


def test_both_windows_on_one_frame_and_the_cheap_rechecks() -> None:
    lum = draw_basic(draw_hotbar(world(1080, 1920), (900, 600)), (40, 700))
    h, b = pf.find_hotbar(lum), pf.find_basic_info(lum)
    assert h is not None and h.origin == (900, 600) and b is not None and b.origin == (40, 700)
    assert pf.basic_info_at(lum, (40, 700)) == len(pf.BASIC_ROWS)
    assert pf.basic_info_at(lum, (41, 700)) < pf.BASIC_MIN_ROWS


def test_luma_uses_the_readers_weights() -> None:
    px = np.array([[[10, 20, 30]]], np.uint8)  # B, G, R
    assert abs(float(pf.luma(px)[0, 0]) - (0.114 * 10 + 0.587 * 20 + 0.299 * 30)) < 1e-4
