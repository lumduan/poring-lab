"""poring_env.weight (loot@1 P1): the weight readout from pixels.

Synthetic tests draw the line with OUR OWN toy bitmap font and label (no client pixels); the
banked-frame tests read frames recorded on 2026-10-08 (the readout then showed 90 / 2030) and are
skipped when those RAM-only frames are absent."""

from __future__ import annotations

import glob
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest

from poring_env import weight as wt

PAPER, INK = 250.0, 10.0
# A toy 6x9 font (rows top to bottom), ours: NOT the client's glyphs.
TOY = {
    "0": ["######", "#....#", "#....#", "#....#", "#....#", "#....#", "#....#", "#....#", "######"],
    "1": ["..##..", ".###..", "..##..", "..##..", "..##..", "..##..", "..##..", "..##..", ".####."],
    "2": ["######", ".....#", ".....#", ".....#", "######", "#.....", "#.....", "#.....", "######"],
    "3": ["######", ".....#", ".....#", "..####", ".....#", ".....#", ".....#", ".....#", "######"],
    "4": ["#....#", "#....#", "#....#", "######", ".....#", ".....#", ".....#", ".....#", ".....#"],
    "5": ["######", "#.....", "#.....", "######", ".....#", ".....#", ".....#", ".....#", "######"],
    "6": ["######", "#.....", "#.....", "######", "#....#", "#....#", "#....#", "#....#", "######"],
    "7": ["######", ".....#", "....#.", "...#..", "..#...", "..#...", "..#...", "..#...", "..#..."],
    "8": ["######", "#....#", "#....#", "######", "#....#", "#....#", "#....#", "#....#", "######"],
    "9": ["######", "#....#", "#....#", "######", ".....#", ".....#", ".....#", ".....#", "######"],
}  # fmt: skip
SLASH = ["...#", "...#", "..#.", "..#.", "..#.", ".#..", ".#..", ".#..", "#...", "#...",
         "#...", "#..."]  # fmt: skip
TAIL = ["#####", "...#.", "..#..", ".#...", "#####"]  # a letter-like mark after the numbers


def _stamp(img: npt.NDArray[np.float32], rows: list[str], x: int, y: int) -> None:
    for dy, row in enumerate(rows):
        for dx, ch in enumerate(row):
            if ch == "#":
                img[y + dy, x + dx] = INK


def toy_label() -> list[str]:
    rng = np.random.default_rng(7)
    grid = rng.random((10, 44)) < 0.35
    return ["".join("#" if v else "." for v in row) for row in grid]


N_LAST, SLASH_AT, M_FIRST = 116, 127, 136  # rect columns, as measured on the client's line


def render(n: str, m: str, *, gap_after_m: int = 12) -> npt.NDArray[np.float32]:
    """A weight_line rect (20 x 220) laid out like the client's: N right-aligned to a fixed
    column, '/' and M fixed, our toy label ending 10 px before N (so it MOVES with N's digit
    count), a tail mark after M; digit rows 5-13."""
    img = np.full((20, 220), PAPER, np.float32)
    _, ly, _, _ = wt.GEOMETRY.label
    first = N_LAST - 7 * (len(n) - 1)
    _stamp(img, toy_label(), first - 10 - 44, 4)
    for i, ch in enumerate(n):
        _stamp(img, TOY[ch], first + 7 * i, ly + 2)
    _stamp(img, SLASH, SLASH_AT, ly + 1)
    for i, ch in enumerate(m):
        _stamp(img, TOY[ch], M_FIRST + 7 * i, ly + 2)
    tail_x = M_FIRST + 7 * (len(m) - 1) + gap_after_m
    if tail_x + 5 <= img.shape[1]:
        _stamp(img, TAIL, tail_x, ly + 5)
    return img


TRAIN = [("90", "2030"), ("1234", "5678"), ("567", "890"), ("12", "3456"), ("78", "9012")]


@pytest.fixture(scope="module")
def glyphs() -> wt.WeightGlyphs:
    rects = [render(n, m) for n, m in TRAIN]
    t, stats = wt.fit_weight_glyphs(rects, [(int(n), int(m)) for n, m in TRAIN])
    assert stats["skipped"] == {} and t.complete and stats["missing"] == ""
    return t


@pytest.mark.parametrize("value", [(0, 2030), (91, 2030), (100, 2030), (1987, 2030), (5, 7),
                                   (2030, 2030), (4561, 99999)])  # fmt: skip
def test_reads_any_value_the_toy_font_can_show(
    glyphs: wt.WeightGlyphs, value: tuple[int, int]
) -> None:
    r = wt.read_rect(render(str(value[0]), str(value[1])), glyphs)
    assert (r.value, r.reason) == (value, "ok")
    assert 0.9 < r.confidence <= 1.0


def test_no_window_no_label(glyphs: wt.WeightGlyphs) -> None:
    dark = np.full((20, 220), 60.0, np.float32)
    assert wt.read_rect(dark, glyphs).reason == "no_window"
    blank_label = render("90", "2030")
    blank_label[:, :105] = PAPER
    assert wt.read_rect(blank_label, glyphs).reason == "no_label"


def test_the_label_moves_with_the_digit_count(glyphs: wt.WeightGlyphs) -> None:
    """As on the client ("90" -> label at 53, "205" -> 50): no column is assumed."""
    one, four = (
        wt.read_rect(render("7", "2030"), glyphs),
        wt.read_rect(render("1234", "2030"), glyphs),
    )
    assert (one.value, four.value) == ((7, 2030), (1234, 2030))
    assert one.label_at is not None and four.label_at is not None
    assert one.label_at[0] - four.label_at[0] == 21


def test_the_label_may_sit_a_pixel_or_two_off(glyphs: wt.WeightGlyphs) -> None:
    img = render("90", "2030")
    shifted = np.full_like(img, PAPER)
    shifted[1:, 2:] = img[:-1, :-2]  # the whole line 2 px right, 1 px down
    r = wt.read_rect(shifted, glyphs)
    base = wt.read_rect(img, glyphs).label_at
    assert base is not None and r.value == (90, 2030) and r.label_at == (base[0] + 2, base[1] + 1)


def test_an_unexplained_mark_or_a_covered_digit_is_refused(glyphs: wt.WeightGlyphs) -> None:
    img = render("90", "2030")
    img[8, 124] = INK  # a speck between the first number and the slash
    assert wt.read_rect(img, glyphs).value is None
    covered = render("90", "2030")
    covered[4:16, 143:149] = 120.0  # something grey over a digit of M
    assert wt.read_rect(covered, glyphs).value is None


def test_a_glyph_right_after_the_last_digit_is_never_cut_off(glyphs: wt.WeightGlyphs) -> None:
    """A mark where a further digit would start (an unknown glyph) refuses the reading instead of
    returning the shorter number."""
    img = render("90", "2030", gap_after_m=1)
    r = wt.read_rect(img, glyphs)
    assert r.value is None and r.reason in ("unexplained_ink", "layout")


def test_leading_zero_and_missing_slash(glyphs: wt.WeightGlyphs) -> None:
    assert wt.read_rect(render("090", "2030"), glyphs).reason == "leading_zero"
    img = render("90", "2030")
    img[3:18, 126:133] = PAPER  # erase the slash
    assert wt.read_rect(img, glyphs).value is None


def test_ambiguous_symbols_are_refused(glyphs: wt.WeightGlyphs) -> None:
    mean = glyphs.mean.copy()
    mean[8] = mean[0]  # 8 now looks exactly like 0: nothing with a 0 can be read with margin
    tampered = wt.WeightGlyphs(mean, glyphs.counts, glyphs.label, glyphs.ink, glyphs.max_score,
                               glyphs.min_margin, glyphs.label_max)  # fmt: skip
    assert wt.read_rect(render("90", "2030"), tampered).reason == "ambiguous"


def test_incomplete_templates_are_refused_unless_explicitly_allowed() -> None:
    rects = [render("90", "2030") for _ in range(3)]
    t, stats = wt.fit_weight_glyphs(rects, [(90, 2030)] * 3)
    assert stats["missing"] == "145678" and not t.complete
    assert wt.read_rect(render("90", "2030"), t).reason == "incomplete_templates"
    assert wt.read_rect(render("90", "2030"), t, allow_incomplete=True).value == (90, 2030)
    # an unseen digit is refused, never read as a seen one
    assert wt.read_rect(render("98", "2030"), t, allow_incomplete=True).value is None


def test_save_load_round_trip(glyphs: wt.WeightGlyphs, tmp_path: Path) -> None:
    path = tmp_path / "weight_glyphs.npz"
    glyphs.save(path)
    back = wt.load_weight_glyphs(path)
    assert back.geometry == glyphs.geometry and back.missing == ""
    assert np.allclose(back.mean, glyphs.mean) and back.max_score == glyphs.max_score
    assert wt.read_rect(render("123", "4567"), back).value == (123, 4567)


def test_read_weight_follows_the_window(glyphs: wt.WeightGlyphs) -> None:
    frame = np.full((720, 1280, 3), 30, np.uint8)
    origin = (300, 200)
    x, y, w, h = wt.rect_at(origin)
    rect = render("345", "2030").astype(np.uint8)
    frame[y : y + h, x : x + w] = rect[..., None]
    assert wt.read_weight(frame, glyphs, origin).value == (345, 2030)
    assert wt.read_weight(frame, glyphs).reason == "no_window"  # nothing at the default place
    assert wt.read_weight(frame[:100, :100], glyphs, origin).reason == "rect_outside_frame"


def test_stable_value_needs_the_same_reading_twice() -> None:
    ok = wt.WeightReading((90, 2030), "ok", 1.0)
    other = wt.WeightReading((91, 2030), "ok", 1.0)
    none = wt.WeightReading(None, "no_label")
    assert wt.stable_value([ok, ok]) == (90, 2030)
    assert wt.stable_value([other, ok]) is None
    assert wt.stable_value([ok, none]) is None
    assert wt.stable_value([ok]) is None


def test_the_element_sits_inside_basic_info() -> None:
    from poring_env.ui_anchors import ELEMENTS, WINDOWS

    dx, dy, w, h = ELEMENTS["weight_line"].box or (0, 0, 0, 0)
    ww, wh = WINDOWS["basic_info"].size
    assert dx + w <= ww and dy + h <= wh
    assert wt.rect_at() == (0, 114, 220, 20)


# --- banked frames (2026-10-08); RAM-only, skipped when absent ------------------------------------
# The five route-demo recordings of 12:33-13:58 showed 90 / 2030 throughout (Batt's reading, and
# the server's weight 900 / 20300 in their packets); walk12's first snapshot (14:52) shows 205 /
# 2030 -- a "5", which those frames never showed.
ROUTE = [
    f"/dev/shm/poring-lab-tmp/route-demo/{s}/frames/*.jpg"
    for s in (
        "20261008T123356",
        "20261008T124909",
        "20261008T133137",
        "20261008T134452",
        "20261008T135639",
    )
]
FRAMES = sorted(p for g in ROUTE for p in glob.glob(g))
SNAPSHOTS = sorted(glob.glob("/dev/shm/poring-lab-demo/20261008T1[23]*route-demo*/snapshots/*.png"))
WITH_A_FIVE = Path(
    "/dev/shm/poring-lab-demo/20261008T145202-demo-walk12-alone-clean-indoor/snapshots/"
    "000-route-before.png"
)


def _rect(path: str) -> npt.NDArray[np.float32]:
    from PIL import Image

    img = np.asarray(Image.open(path).convert("RGB"))[..., ::-1]
    x, y, w, h = wt.rect_at()
    return wt.to_gray(np.ascontiguousarray(img[y : y + h, x : x + w]))


@pytest.mark.skipif(len(FRAMES) < 100, reason="banked frames absent (RAM-only)")
def test_banked_frames_fit_on_some_and_read_the_others() -> None:
    train, test = FRAMES[::50], FRAMES[13::31] + SNAPSHOTS[::4]
    t, stats = wt.fit_weight_glyphs([_rect(p) for p in train], [(90, 2030)] * len(train))
    assert stats["placed"] == len(train) and stats["missing"] == "145678"
    reads = [wt.read_rect(_rect(p), t, allow_incomplete=True) for p in test]
    assert all(r.value == (90, 2030) for r in reads), {r.reason for r in reads}
    assert min(r.confidence for r in reads) > 0.9
    assert wt.read_rect(_rect(test[0]), t).reason == "incomplete_templates"
    # a real frame with the "3" of 2030 painted over by a scene-like grey is refused
    g = _rect(test[0]).copy()
    g[4:17, 150:157] = 140.0
    assert wt.read_rect(g, t, allow_incomplete=True).value is None
    if WITH_A_FIVE.exists():  # a REAL unseen digit: refused, never read as a shorter number
        r = wt.read_rect(_rect(str(WITH_A_FIVE)), t, allow_incomplete=True)
        assert r.value is None and r.label_at is not None and r.label_at[0] < 52, r
