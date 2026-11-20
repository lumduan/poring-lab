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
                seed: int = 1, pitch: int = 29, frame: float = 195.0) -> np.ndarray:  # fmt: skip
    """The shortcut bar as the module describes it: 9 square boxes on one row (each a left line
    and a top edge of ``frame`` on the bar's white), an icon (noise) in every box. ``lines``: how
    many boxes keep their left line; ``rows`` False: no top edges (a comb of lines only)."""
    rng = np.random.default_rng(seed)
    ox, oy = at
    x0, y0 = ox + pf.HOTBAR_LINE_DX, oy + pf.HOTBAR_LINE_DY
    size = pitch - pf.HOTBAR_GAP
    lum[y0 - 2 : y0 + size + 2, x0 - 3 : x0 + pitch * 8 + size + 3] = 250.0  # the bar's white
    for i in range(pf.HOTBAR_SLOTS):
        x = x0 + pitch * i
        lum[y0 + 2 : y0 + size - 2, x + 2 : x + size - 2] = rng.uniform(
            0, 255, (size - 4, size - 4)
        )
        if i < lines:
            lum[y0 : y0 + size, x] = frame  # its left line
        if rows:
            lum[y0, x : x + size] = frame  # its top edge
    return lum


def draw_basic(lum: np.ndarray, at: tuple[int, int], crossed: int = 0, seed: int = 2) -> np.ndarray:
    """Basic Info: its cue rows over their spans and its right border, text (noise) EVERYWHERE
    else -- the title's text, the name, the EXP bars, the weight, the badge; ``crossed`` cue rows
    broken by something over them (the pointer)."""
    rng = np.random.default_rng(seed)
    ox, oy = at
    lum[oy : oy + pf.BASIC_H, ox : ox + pf.BASIC_W] = rng.uniform(0, 255, (pf.BASIC_H, pf.BASIC_W))
    for k, (depth, (lo, hi), (x0, x1)) in enumerate(pf.BASIC_ROWS):
        lum[oy + depth, ox + x0 : ox + x1] = (lo + hi) / 2
        if k < crossed:
            lum[oy + depth, ox + x0 + 10 : ox + x0 + 30] = 0 if lo > 100 else 255
    col, (lo, hi), (y0, y1) = pf.BASIC_COL
    lum[oy + y0 : oy + y1, ox + col] = (lo + hi) / 2
    return lum


@pytest.mark.parametrize("at", [(230, 0), (0, 0), (517, 333), (1280 - 300, 720 - 40)])
def test_the_hotbar_is_found_wherever_it_was_dragged(at: tuple[int, int]) -> None:
    got = pf.find_hotbar(draw_hotbar(world(), at))
    assert got is not None and got.origin == at and (got.score, got.of, got.pitch) == (9, 9, 29)


@pytest.mark.parametrize("pitch", [28, 30])
@pytest.mark.parametrize("frame", [195.0, 40.0])
def test_nine_boxes_in_a_row_whatever_their_colour_and_pitch(pitch: int, frame: float) -> None:
    """Batt 2026-11-19: "9 slots in a row = the hotbar" -- his client draws a dark frame."""
    got = pf.find_hotbar(draw_hotbar(world(), (300, 200), pitch=pitch, frame=frame))
    assert got is not None and got.origin == (300, 200) and got.pitch == pitch


def test_a_search_wants_all_nine_a_recheck_lets_one_be_covered() -> None:
    eight = draw_hotbar(world(), (400, 200), lines=8)
    assert pf.find_hotbar(eight) is None
    assert pf.hotbar_at(eight, (400, 200)) == 8 >= pf.HOTBAR_MIN_AT


def test_a_comb_of_lines_without_the_boxes_tops_is_no_hotbar() -> None:
    """The login screen's list drew lines on the pitch (2026-11-19, the lab's frames)."""
    assert pf.find_hotbar(draw_hotbar(world(), (143, 523), rows=False)) is None
    assert pf.find_hotbar(world()) is None
    flat = np.full((720, 1280), 250.0, np.float32)  # a white window: no line stands out
    assert pf.find_hotbar(flat) is None


def test_the_recheck_pins_the_hotbar_to_its_row() -> None:
    lum = draw_hotbar(world(), (300, 120))
    assert pf.hotbar_at(lum, (300, 120)) == 9
    assert pf.hotbar_at(lum, (300, 126)) < pf.HOTBAR_MIN_AT  # off its row
    assert pf.hotbar_at(lum, (305, 120)) < pf.HOTBAR_MIN_AT  # off its columns
    assert pf.hotbar_at(lum, (5000, 0)) == 0  # off the frame


@pytest.mark.parametrize("at", [(0, 0), (412, 300), (1280 - 220, 720 - pf.BASIC_H)])
def test_basic_info_is_found_wherever_it_was_dragged(at: tuple[int, int]) -> None:
    got = pf.find_basic_info(draw_basic(world(), at))
    assert got is not None and got.origin == at and got.score == pf.BASIC_CUES


def test_basic_info_with_one_row_crossed_is_found_with_two_it_is_not() -> None:
    one = pf.find_basic_info(draw_basic(world(), (300, 100), crossed=1))
    assert one is not None and one.score == pf.BASIC_CUES - 1
    assert pf.find_basic_info(draw_basic(world(), (300, 100), crossed=2)) is None
    assert pf.find_basic_info(world()) is None


def test_both_windows_on_one_frame_and_the_cheap_rechecks() -> None:
    lum = draw_basic(draw_hotbar(world(1080, 1920), (900, 600)), (40, 700))
    h, b = pf.find_hotbar(lum), pf.find_basic_info(lum)
    assert h is not None and h.origin == (900, 600) and b is not None and b.origin == (40, 700)
    assert pf.basic_info_at(lum, (40, 700)) == pf.BASIC_CUES
    assert pf.basic_info_at(lum, (41, 700)) < pf.BASIC_MIN_ROWS


def test_luma_uses_the_readers_weights() -> None:
    px = np.array([[[10, 20, 30]]], np.uint8)  # B, G, R
    assert abs(float(pf.luma(px)[0, 0]) - (0.114 * 10 + 0.587 * 20 + 0.299 * 30)) < 1e-4


def test_basic_info_reads_no_row_a_title_an_exp_bar_or_a_badge_can_reach() -> None:
    """2026-11-19 ~11:0x (a Thai-UI client): a Thai title's tails reach the line under it, a Job
    EXP bar fills the level panel, the "N" badge sits at the bottom. The cues keep clear of them:
    the title rows only right of x 130, the level panel by its edges, nothing under the weight."""
    title = [x0 for d, _, (x0, _x1) in pf.BASIC_ROWS if d <= 16]
    assert title and min(title) >= 130
    depths = {d for d, _, _ in pf.BASIC_ROWS}
    assert not depths & set(range(87, 108))  # inside the level panel (its EXP bars)
    assert max(depths) < 118 and pf.BASIC_COL[2][1] <= 131  # above the weight's text and badge


def test_stack_counts_over_the_left_lines_bottom_keep_all_nine() -> None:
    """2026-11-20, the live PC's client: each slot's stack count ("592", "570", "11") is drawn over
    the BOTTOM of its left frame line (black text on the line); 3 of 9 slots failed the search,
    which wants 9. The left line is checked above the count's rows only."""
    lum = draw_hotbar(world(), (377, 11))
    x0, y0 = 377 + pf.HOTBAR_LINE_DX, 11 + pf.HOTBAR_LINE_DY
    size = 29 - pf.HOTBAR_GAP
    for i in (0, 4, 7, 8):  # the counted slots: black digits across the line's last rows
        x = x0 + 29 * i
        lum[y0 + size - 4 : y0 + size - 1, x - 1 : x + 6] = 0.0
    got = pf.find_hotbar(lum)
    assert got is not None and got.origin == (377, 11) and got.score == 9
    lum[y0 + 6 : y0 + 9, x0 + 29 * 3 - 1 : x0 + 29 * 3 + 4] = 0.0  # ink HIGH on a line: not a frame
    assert pf.find_hotbar(lum) is None
