"""poring_env.selfpos: our own cell from the minimap readout -- read, or None, never a guess.

Every glyph here is synthesised by the test (a made-up 6x9 bitmap font with a drop shadow on its
left, like the client's): no client-derived pixels in the repo."""

import dataclasses
from pathlib import Path

import numpy as np
import pytest

from poring_env import selfpos

FONT = {
    0: [".####.", "#....#", "#...##", "#..#.#", "#.#..#", "##...#", "#....#", "#....#", ".####."],
    1: ["..#...", ".##...", "#.#...", "..#...", "..#...", "..#...", "..#...", "..#...", "#####."],
    2: [".####.", "#....#", ".....#", "....#.", "...#..", "..#...", ".#....", "#.....", "######"],
    3: [".####.", "#....#", ".....#", "..###.", ".....#", ".....#", ".....#", "#....#", ".####."],
    4: ["...##.", "..#.#.", ".#..#.", "#...#.", "######", "....#.", "....#.", "....#.", "....#."],
    5: ["######", "#.....", "#.....", "#####.", ".....#", ".....#", ".....#", "#....#", ".####."],
    6: [".####.", "#.....", "#.....", "#####.", "#....#", "#....#", "#....#", "#....#", ".####."],
    7: ["######", ".....#", "....#.", "...#..", "...#..", "..#...", "..#...", "..#...", "..#..."],
    8: [".####.", "#....#", "#....#", ".####.", "#....#", "#....#", "#....#", "#....#", ".####."],
    9: [".####.", "#....#", "#....#", "#....#", ".#####", ".....#", ".....#", "#....#", ".####."],
}
STROKE, SHADOW = 245.0, 8.0
CELL_H, CELL_W, PITCH, SPACE = 11, 7, 7, 8
RECT = selfpos.default_rect()
TEXT_X = RECT[0] + 6  # the first cell's left column (its shadow), as measured on the client
TEXT_Y = RECT[1] + 2  # the cell's top row


def glyph_cell(d: int) -> tuple[np.ndarray, np.ndarray]:
    """(stroke, shadow) masks of one 11x7 cell: a blank row above and below, a shadow column."""
    stroke = np.zeros((CELL_H, CELL_W), bool)
    for r, line in enumerate(FONT[d]):
        for c, ch in enumerate(line):
            stroke[1 + r, 1 + c] = ch == "#"
    shadow = np.zeros_like(stroke)
    shadow[:, :-1] = stroke[:, 1:] & ~stroke[:, :-1]
    return stroke, shadow


def scene(rng: np.random.Generator, paving: bool | None = None) -> np.ndarray:
    """A game region whose readout strip shows a textured, ever-changing scene: a dark field, or
    (a third of the time) bright paving at ~150-200 grey with specks up to 230, like prontera."""
    frame = rng.integers(0, 256, (720, 1280, 3), dtype=np.uint8)
    x, y, w, h = RECT
    if paving is None:
        paving = bool(rng.random() < 1 / 3)
    if paving:
        strip = 150 + 50 * rng.random((h, w))
        strip[rng.random((h, w)) < 0.05] = 230
    else:
        strip = 30 + 110 * rng.random((h, w))
    frame[y : y + h, x : x + w] = strip[..., None].astype(np.uint8)
    return frame


def draw_text(frame: np.ndarray, text: str, rng: np.random.Generator, noise: float = 6.0) -> None:
    left = TEXT_X
    for i, ch in enumerate(text):
        if ch == " ":
            left += SPACE - PITCH  # the space is a whole cell plus one column
        else:
            stroke, shadow = glyph_cell(int(ch))
            region = frame[TEXT_Y : TEXT_Y + CELL_H, left : left + CELL_W].astype(np.float64)
            region[stroke] = STROKE
            region[shadow] = SHADOW
            region += rng.normal(0, noise, region.shape)  # codec softening, roughly
            frame[TEXT_Y : TEXT_Y + CELL_H, left : left + CELL_W] = np.clip(region, 0, 255)
        if i + 1 < len(text):
            left += PITCH


def rect_of(frame: np.ndarray) -> np.ndarray:
    x, y, w, h = RECT
    return selfpos.to_gray(frame[y : y + h, x : x + w])


LAYOUT = selfpos.Layout(text_left=TEXT_X - RECT[0], top=TEXT_Y - RECT[1], number_gap=SPACE)


@pytest.fixture(scope="module")
def templates() -> selfpos.DigitTemplates:
    """Templates fitted the way the calibration does it: many labelled readouts, then the
    shared rules for max_score / min_margin / ink and shadow levels."""
    rng = np.random.default_rng(0)
    rects, labels = [], []
    for _ in range(40):
        for d in range(10):
            frame = scene(rng)
            x = 111 * d if d else 100  # every digit, at every place
            draw_text(frame, f"{x} {d}", rng)
            rects.append(rect_of(frame))
            labels.append((x, d))
    fitted, _ = selfpos.fit_templates(rects, labels, LAYOUT)
    return fitted


@pytest.mark.parametrize("xy", [(170, 369), (155, 25), (99, 112), (7, 300), (0, 0), (204, 18)])
def test_the_readout_round_trips(templates: selfpos.DigitTemplates, xy: tuple[int, int]) -> None:
    rng = np.random.default_rng(xy[0] * 1000 + xy[1])
    frame = scene(rng)
    draw_text(frame, f"{xy[0]} {xy[1]}", rng)
    reading = selfpos.read_minimap(frame, templates)
    assert reading.reason == "ok" and reading.xy == xy
    assert selfpos.read_minimap_xy(frame, templates) == xy


def test_noise_or_an_empty_strip_is_none(templates: selfpos.DigitTemplates) -> None:
    rng = np.random.default_rng(5)
    for _ in range(20):
        frame = scene(rng)  # no readout at all (an indoor map: the client hides the minimap)
        assert selfpos.read_minimap_xy(frame, templates) is None
        frame[RECT[1] : RECT[1] + RECT[3], RECT[0] : RECT[0] + RECT[2]] = rng.integers(
            0, 256, (RECT[3], RECT[2], 3), dtype=np.uint8
        )  # pure noise
        assert selfpos.read_minimap_xy(frame, templates) is None


def test_a_partly_covered_readout_is_none_not_a_shorter_number(
    templates: selfpos.DigitTemplates,
) -> None:
    rng = np.random.default_rng(6)
    frame = scene(rng)
    draw_text(frame, "170 369", rng)
    assert selfpos.read_minimap_xy(frame, templates) == (170, 369)
    left = TEXT_X + 2 * PITCH  # the "0" of 170 ...
    covered = frame.copy()
    covered[TEXT_Y + 1 : TEXT_Y + 10, left + 1 : left + 8] = 5  # ... under the cursor: outlined
    covered[TEXT_Y + 2 : TEXT_Y + 9, left + 2 : left + 7] = 250
    reading = selfpos.read_minimap(covered, templates)
    assert reading.xy is None and reading.reason != "ok"
    cut = frame.copy()
    cut[TEXT_Y : TEXT_Y + CELL_H, left + 1 : left + 7] = 60  # the glyph is gone, its place dark
    assert selfpos.read_minimap_xy(cut, templates) is None  # "17 369" would be a guess


def test_a_bright_scene_through_the_strip_is_not_ink(templates: selfpos.DigitTemplates) -> None:
    """Prontera's paving shows through the strip at ~150-200 grey with specks up to ~230: bright,
    but with no black drop shadow beside it, so it is scenery, not an unexplained glyph. A strip
    nearly as white as the strokes cannot be read at all: None."""
    rng = np.random.default_rng(12)
    x, y, w, h = RECT
    for _ in range(10):
        frame = scene(rng, paving=True)
        draw_text(frame, "155 25", rng)
        assert selfpos.read_minimap_xy(frame, templates) == (155, 25)
    frame = scene(rng)
    frame[y : y + h, x : x + w] = (215 + 30 * rng.random((h, w)))[..., None].astype(np.uint8)
    draw_text(frame, "155 25", rng)
    assert selfpos.read_minimap_xy(frame, templates) is None


def test_a_stroke_start_at_the_rect_edge_where_no_digit_fits_is_scenery(
    templates: selfpos.DigitTemplates,
) -> None:
    """2026-10-25 (4.05 s2): "292 62" over sunlit grass had ONE unexplained stroke start, in the
    rect's last column, where no whole digit can start -- scenery, read. The same speck where a
    third y digit could start is still a refusal (it could be a hidden digit)."""
    rng = np.random.default_rng(25)
    x, y, w, h = RECT
    frame = scene(rng, paving=False)
    draw_text(frame, "292 62", rng, noise=0)
    assert selfpos.read_minimap_xy(frame, templates) == (292, 62)
    assert selfpos.first_stroke_max(templates) <= 2
    edge = frame.copy()
    edge[TEXT_Y + 3 : TEXT_Y + 7, x + w - 2] = 5  # a dark speck, then a bright one: a "start"
    edge[TEXT_Y + 3 : TEXT_Y + 7, x + w - 1] = 250
    assert selfpos.read_minimap_xy(edge, templates) == (292, 62)
    third = frame.copy()  # "62" sits at TEXT_X + 29 and + 36 (draw_text): a third y digit's
    c = TEXT_X + 6 * PITCH + 1  # shadow column would be TEXT_X + 43, its first stroke one right
    third[TEXT_Y + 3 : TEXT_Y + 7, c] = 5
    third[TEXT_Y + 3 : TEXT_Y + 7, c + 1] = 250
    assert selfpos.read_minimap_xy(third, templates) is None


def test_a_glyph_between_two_digits_is_ambiguous(templates: selfpos.DigitTemplates) -> None:
    """Half a 6 and half an 8 in one cell: either would be a guess."""
    base = scene(np.random.default_rng(7))
    six, eight = base.copy(), base.copy()
    draw_text(six, "166 368", np.random.default_rng(1), noise=0)
    draw_text(eight, "168 368", np.random.default_rng(1), noise=0)
    assert selfpos.read_minimap_xy(eight, templates) == (168, 368)
    blend = ((six.astype(np.uint16) + eight) // 2).astype(np.uint8)
    reading = selfpos.read_minimap(blend, templates)
    assert reading.xy is None and reading.reason == "ambiguous"


def test_a_faded_glyph_is_none(templates: selfpos.DigitTemplates) -> None:
    rng = np.random.default_rng(7)
    frame = scene(rng)
    draw_text(frame, "168 368", rng)
    left = TEXT_X + 2 * PITCH
    frame[TEXT_Y + 1 : TEXT_Y + 10, left + 1 : left + 7] //= 2  # under a dark translucent window
    assert selfpos.read_minimap_xy(frame, templates) is None


def test_extra_glyphs_or_three_numbers_are_a_layout_failure(
    templates: selfpos.DigitTemplates,
) -> None:
    rng = np.random.default_rng(8)
    frame = scene(rng)
    draw_text(frame, "1 2 3", rng)
    reading = selfpos.read_minimap(frame, templates)
    assert reading.xy is None and reading.reason == "layout"


def test_leading_zeros_are_refused(templates: selfpos.DigitTemplates) -> None:
    rng = np.random.default_rng(9)
    frame = scene(rng)
    draw_text(frame, "017 369", rng)
    reading = selfpos.read_minimap(frame, templates)
    assert reading.xy is None and reading.reason == "leading_zero"


def test_a_located_window_moves_the_rect() -> None:
    x, y, w, h = selfpos.default_rect()
    assert selfpos.rect_at((1136, 18)) == (x, y, w, h)
    assert selfpos.rect_at((1000, 50))[:2] == (x - 136, y + 32)


def test_templates_round_trip_through_npz(
    templates: selfpos.DigitTemplates, tmp_path: Path
) -> None:
    path = tmp_path / "minimap_digits.npz"
    templates.save(path)
    loaded = selfpos.load_digit_templates(path)
    assert np.array_equal(loaded.mean, templates.mean)
    assert np.array_equal(loaded.counts, templates.counts)
    for name in ("bright", "max_score", "min_margin", "ink_level", "shadow_level",
                 "stroke_rows", "pitch", "min_gap", "text_left", "number_gap"):  # fmt: skip
        assert getattr(loaded, name) == pytest.approx(getattr(templates, name))
    assert loaded.meta == templates.meta
    rng = np.random.default_rng(10)
    frame = scene(rng)
    draw_text(frame, "162 368", rng)
    assert selfpos.read_minimap_xy(frame, loaded) == (162, 368)


def test_the_loader_refuses_other_formats_and_pickles(tmp_path: Path) -> None:
    bad = tmp_path / "old.npz"
    np.savez(bad, version=np.int64(selfpos.FORMAT_VERSION + 1))
    with pytest.raises(ValueError, match="format"):
        selfpos.load_digit_templates(bad)
    pickled = tmp_path / "pickled.npz"
    np.savez(pickled, version=np.array([{"x": 1}], dtype=object))
    with pytest.raises(ValueError):  # object arrays are never unpickled
        selfpos.load_digit_templates(pickled)


def test_a_digit_never_seen_in_training_is_never_read(
    templates: selfpos.DigitTemplates,
) -> None:
    counts = templates.counts.copy()
    counts[7] = 0
    partial = dataclasses.replace(templates, counts=counts)
    rng = np.random.default_rng(11)
    frame = scene(rng)
    draw_text(frame, "170 369", rng)
    assert selfpos.read_minimap_xy(frame, partial) is None
    frame = scene(rng)
    draw_text(frame, "162 368", rng)
    assert selfpos.read_minimap_xy(frame, partial) == (162, 368)


def pale_floor(rng: np.random.Generator, lo: float = 200.0, hi: float = 228.0) -> np.ndarray:
    """A game region whose readout strip shows a PALE floor (xmas_dun02's tiles: ~197-234)."""
    frame = scene(rng, paving=False)
    x, y, w, h = RECT
    frame[y : y + h, x : x + w] = (lo + (hi - lo) * rng.random((h, w)))[..., None].astype(np.uint8)
    return frame


def test_a_pale_floor_is_read_by_the_opaque_glyph_fallback(
    templates: selfpos.DigitTemplates,
) -> None:
    """2026-11-05, rogue-xmas02 X1b: the base reader takes a pale floor for half a stroke and reads
    nothing; the fallback keeps only the opaque glyph pixels and reads it."""
    for seed, text in ((1, "79 93"), (2, "7 230"), (3, "251 156")):
        rng = np.random.default_rng(seed)
        frame = pale_floor(rng)
        draw_text(frame, text, rng, noise=2.0)
        base = selfpos.read_minimap(frame, templates, light=False)
        assert base.xy is None and base.reason in selfpos.OPAQUE_AFTER, (text, base.reason)
        assert selfpos.read_minimap(frame, templates).xy is None  # the fallback is opt-in
        got = selfpos.read_minimap(frame, templates, light=True)
        assert got.xy == tuple(int(v) for v in text.split()) and got.mode == "light", (text, got)


def test_a_digit_changing_over_a_pale_floor_reads_none_or_one_of_its_values(
    templates: selfpos.DigitTemplates,
) -> None:
    """Half a 6 and half an 8 over the pale floor: flattened, their common strokes remain. The
    fallback reads None or one of the TWO true values (here the old one, 166: right for a walk);
    a third digit is possible on other pairs (X1b round 3's synthetic blends: 20 of 1,080), which
    is why a "light" read is only ever used once a second read confirms it (dungeon_hunt)."""
    rng = np.random.default_rng(4)
    floor = pale_floor(rng)
    six, eight = floor.copy(), floor.copy()
    draw_text(six, "166 368", np.random.default_rng(1), noise=0)
    draw_text(eight, "168 368", np.random.default_rng(1), noise=0)
    assert selfpos.read_minimap(eight, templates, light=True).xy == (168, 368)
    blend = ((six.astype(np.uint16) + eight) // 2).astype(np.uint8)
    reading = selfpos.read_minimap(blend, templates, light=True)
    assert reading.xy in (None, (166, 368), (168, 368)), reading


def test_many_half_pairs_in_a_light_cell_refuse_the_read(templates: selfpos.DigitTemplates) -> None:
    """A digit fading out over the floor: its whole stroke half drawn (a pale half stroke beside a
    half shadow on every row) is refused, not read."""
    rng = np.random.default_rng(5)
    frame = pale_floor(rng, 200, 210)
    draw_text(frame, "77 77", rng, noise=0.0)
    x, y, w, h = RECT
    top, left = TEXT_Y + 1, TEXT_X + PITCH  # the x number's 2nd digit: half drawn on 9 rows
    frame[top : top + 9, left + 2] = 120  # half shadows ...
    frame[top : top + 9, left + 3] = 228  # ... before half strokes
    base = selfpos.read_minimap(frame, templates, light=False)
    got = selfpos.read_minimap(frame, templates, light=True)
    assert base.xy is None and got.xy is None and got.mode == "light_failed", (base, got)
    assert got.light_reason == "half_shadow" and got.reason == base.reason  # the base's reason kept


def test_the_fallback_never_runs_after_an_ambiguous_base_read(
    templates: selfpos.DigitTemplates,
) -> None:
    for reason in ("ambiguous", "layout", "leading_zero", "rect_too_small", "no_templates"):
        assert reason not in selfpos.OPAQUE_AFTER


def test_a_dark_floor_band_through_a_pale_floor_is_read(templates: selfpos.DigitTemplates) -> None:
    """X1b round 1's FAIL (xmas_dun02 7,125): a dark floor band (~60-90) runs through light cells;
    the round-1 guard took its pixels for half shadows. A band's edge is not a half pair."""
    for seed, text in ((11, "7 125"), (12, "217 23"), (13, "7 241")):
        rng = np.random.default_rng(seed)
        frame = pale_floor(rng, 195, 215)
        x, y, w, h = RECT
        band = 55 + 40 * rng.random((h, 24))  # its left edge INSIDE the first digit's cell
        frame[y : y + h, x + 11 : x + 35] = band[..., None].astype(np.uint8)
        draw_text(frame, text, rng, noise=2.0)
        got = selfpos.read_minimap(frame, templates, light=True)
        assert got.xy == tuple(int(v) for v in text.split()), (text, got)
