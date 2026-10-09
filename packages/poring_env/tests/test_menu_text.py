"""poring_env.menu_text (talk@1 T3): the menu line reader on a SYNTHETIC bitmap font (random glyph
bitmaps, the client's measured spacing: 1 blank column inside a word, 5 at a space, ink from the 4th
column). No client pixels and no server strings: the option texts are invented."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from poring_env import menu_text as mt

CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.-"
ROW_W = 243
X0 = 3
SPACE_ADV = 4
PLAIN = (247, 247, 247)  # BGR == RGB for greys
HIGHLIGHT_BGR = (255, 222, 206)


def make_font(seed: int = 7) -> dict[str, np.ndarray]:
    """Random glyphs, 1-7 columns, ink on rows 2-13, every column inked (one run per glyph)."""
    rng = np.random.default_rng(seed)
    font: dict[str, np.ndarray] = {}
    seen: set[bytes] = set()
    for c in CHARS:
        while True:
            w = 1 if c in "il." else int(rng.integers(3, 8))
            g = np.zeros((mt.BAND_H, w), bool)
            g[2:12] = rng.random((10, w)) < 0.45
            for x in range(w):
                g[2 + int(rng.integers(0, 10)), x] = True
            if c in "gjpqy":  # descenders reach row 13
                g[13, w // 2] = True
            key = g.tobytes() + bytes([w])
            if key not in seen:
                seen.add(key)
                font[c] = g
                break
    return font


FONT = make_font()


def render(text: str, bg: tuple[int, int, int] = PLAIN, width: int = ROW_W, x0: int = X0,
           touch: set[int] | None = None, space: int = SPACE_ADV) -> np.ndarray:  # fmt: skip
    """A row (BAND_H x width, BGR) showing ``text`` (clipped at the row's end); ``touch``: glyph
    indices drawn with no gap after them; ``space``: columns a space adds."""
    row = np.empty((mt.BAND_H, width, 3), np.uint8)
    row[:] = bg
    if bg == HIGHLIGHT_BGR:
        row[-1] = PLAIN  # the band covers a row's first 15 rows
    x, k = x0, 0
    for c in text:
        if c == " ":
            x += space
            continue
        g = FONT[c][:, : max(0, width - x)]
        row[:, x : x + g.shape[1]][g] = 0
        g = FONT[c]
        x += g.shape[1] + (0 if touch and k in touch else 1)
        k += 1
    return row


TRAIN = ["About Alpha", "About Beta Gamma", "Clean the Kitchen", "Deliver Quests now",
         "Forge Hammers", "Jump over Lazy dogs", "Paint Your Wagon", "Vex the Zebra",
         "Mix it up. Okay", "Remove marks-now", "Why not quickly", "Expect juicy Ideas",
         "Sun", "No"]  # fmt: skip


@pytest.fixture(scope="module")
def glyphs() -> mt.MenuGlyphs:
    rows = [render(t, HIGHLIGHT_BGR if i % 4 == 0 else PLAIN) for i, t in enumerate(TRAIN)]
    g, stats = mt.fit_menu_glyphs(rows, TRAIN)
    assert stats["skipped"] == {} and stats["used_rows"] == len(TRAIN)
    assert g.gaps0 == (1,) and g.gaps1 == (5,) and g.lead_range == (X0, X0)
    return g


def test_held_out_lines_read_exactly_with_their_highlight(glyphs: mt.MenuGlyphs) -> None:
    for text, bg in (("About Gamma", PLAIN), ("Quick Zebra Jump", HIGHLIGHT_BGR),
                     ("Okay.", PLAIN), ("Mix  two spaces", PLAIN)):  # fmt: skip
        r = mt.read_row(render(text, bg), glyphs)
        assert (r.text, r.reason) == (text, "ok")
        assert r.highlighted == (bg == HIGHLIGHT_BGR) and r.confidence > 0.5


def test_an_empty_row_and_the_trailing_space_rule(glyphs: mt.MenuGlyphs) -> None:
    r = mt.read_row(render(""), glyphs)
    assert (r.text, r.reason, r.key) == ("", "empty", "")
    assert mt.visible_text("About Beta ") == "About Beta"  # a trailing space is invisible
    assert mt.read_row(render("About Beta "), glyphs).text == mt.visible_text("About Beta ")
    assert mt.visible_text("^0000FFBlue^000000") is None  # coloured: never a target


@pytest.mark.parametrize(
    ("make", "why"),
    [
        (lambda: render("About Alpha", (120, 200, 90)), "no_background"),
        (lambda: render("About Alpha", width=60), "cut_off"),
        (lambda: render("About Alpha", x0=X0 + 5), "leading_blank"),
    ],
)
def test_layout_refusals(glyphs: mt.MenuGlyphs, make: object, why: str) -> None:
    r = mt.read_row(make(), glyphs)  # type: ignore[operator]
    assert (r.text, r.reason) == (None, why)


def test_an_unseen_or_damaged_glyph_is_refused_never_guessed(glyphs: mt.MenuGlyphs) -> None:
    unseen = "".join(sorted(set("XUW") - set("".join(TRAIN))))  # never trained
    assert unseen
    r = mt.read_row(render(f"About {unseen}"), glyphs)
    assert r.text is None and r.reason in ("unknown_glyph", "ambiguous_glyph")
    row = render("About Alpha")
    ys, xs = np.nonzero(row[..., 0] == 0)
    row[ys[:2], xs[:2]] = PLAIN  # two ink pixels of the first glyph lost
    r = mt.read_row(row, glyphs)
    assert r.text is None and r.reason in ("unknown_glyph", "ambiguous_glyph")


def test_coloured_text_and_occluders_are_refused(glyphs: mt.MenuGlyphs) -> None:
    row = render("About Alpha")
    row[row[..., 0] == 0] = (255, 0, 0)  # the whole line drawn in blue (an ^0000FF option)
    assert mt.read_row(row, glyphs).reason == "coloured_text"
    row = render("About Alpha")
    row[3:10, 100:108] = (200, 120, 60)  # a foreign, non-ink blob (a cursor's edge)
    assert mt.read_row(row, glyphs).reason in ("foreign_pixels", "coloured_text")
    row = render("About Alpha")
    row[5, 150] = (60, 140, 60)  # one codec speck is tolerated
    assert mt.read_row(row, glyphs).text == "About Alpha"


def test_a_gap_that_is_neither_a_glyph_gap_nor_spaces_is_refused(glyphs: mt.MenuGlyphs) -> None:
    row = render("About")
    tail = render("Alpha", x0=0)[:, :60]
    first_end = int(np.flatnonzero((row[..., 0] == 0).any(axis=0))[-1]) + 1
    row[:, first_end + 3 : first_end + 3 + 60] = tail  # a 3-column gap: not 1, not 5
    assert mt.read_row(row, glyphs).reason == "unexplained_gap"


def test_touching_glyphs_are_split_when_the_split_is_unique(glyphs: mt.MenuGlyphs) -> None:
    r = mt.read_row(render("About Alpha", touch={1}), glyphs)  # "b" touches "o"
    assert r.text == "About Alpha"


def test_templates_round_trip(tmp_path: Path, glyphs: mt.MenuGlyphs) -> None:
    path = tmp_path / "g.npz"
    glyphs.save(path)
    back = mt.load_menu_glyphs(path)
    assert back.chars == glyphs.chars and back.gaps1 == glyphs.gaps1
    assert np.array_equal(back.widths, glyphs.widths) and back.max_score == glyphs.max_score
    assert mt.read_row(render("Paint the Wagon"), back).text == "Paint the Wagon"
    want = "".join(sorted(set("AboutXylophone") - set(back.chars)))
    assert want and back.missing(["About Xylophone "]) == want
    assert back.missing(["^FF0000Red^000000"]) == ""  # coloured options are never read


def test_fitting_refuses_rows_it_cannot_place_and_overlapping_gaps() -> None:
    with pytest.raises(ValueError, match="no row"):
        mt.fit_menu_glyphs([render("")], [""])
    rows = [render("Ab Cd"), render("Ef Gh", space=0)]  # a "space" as narrow as a glyph gap
    with pytest.raises(ValueError, match="overlap"):
        mt.fit_menu_glyphs(rows, ["Ab Cd", "Ef Gh"])
    _, stats = mt.fit_menu_glyphs([render("Ab Cd"), render("Ab"), render("Cd Ab")],
                                  ["Ab Cd", "Ab Cd", "Cd Ab"])  # fmt: skip
    assert stats["skipped"] == {"run_count": 1}  # a mislabelled row is skipped, counted


# --- the whole list ------------------------------------------------------------------------------

OPTIONS = ["About Alpha", "About Beta ", "Forge Hammers", "Paint Your Wagon", "Vex the Zebra",
           "Jump over Lazy dogs", "Clean the Kitchen"]  # fmt: skip


def snap(lines: list[str | None], up: bool, down: bool,
         refuse: str = "unknown_glyph") -> mt.MenuSnapshot:  # fmt: skip
    reads = tuple(mt.RowRead(t, "ok" if t else "empty", 1.0) if t is not None
                  else mt.RowRead(None, refuse) for t in lines)  # fmt: skip
    return mt.MenuSnapshot(reads, up, down)


def windows(opts: list[str], shift: int = 1) -> list[mt.MenuSnapshot]:
    vis = [o.rstrip(" ") for o in opts]
    out = []
    top = 0
    while True:
        lines = vis[top : top + 4] + [""] * max(0, 4 - len(vis[top:]))
        out.append(snap(list(lines), top > 0, top + 4 < len(vis)))
        if top + 4 >= len(vis):
            return out
        top = min(top + shift, len(vis) - 4)


def test_scroll_reads_merge_into_the_whole_list_and_match_l3() -> None:
    full = mt.accumulate(windows(OPTIONS))
    assert full.reason == "ok" and full.tops == (0, 1, 2, 3)
    assert full.keys == [o.rstrip(" ") for o in OPTIONS]
    cc = mt.cross_check(full, OPTIONS)
    assert cc.ok and cc.packet_index == tuple(range(1, 8))
    assert mt.line_of(full, "About Beta ") == 1  # its trailing space is not on screen
    assert mt.align(snap(["Forge Hammers", "Paint Your Wagon", "Vex the Zebra",
                          "Jump over Lazy dogs"], True, True), full) == 2  # fmt: skip
    assert mt.accumulate(windows(OPTIONS, shift=2)).reason == "ok"


def test_a_short_menu_has_empty_rows_and_no_scrolling() -> None:
    short = ["Sun", "No", "Okay."]
    full = mt.accumulate(windows(short))
    assert full.reason == "ok" and full.keys == short and mt.cross_check(full, short).ok
    bad = snap(["Sun", "", "No", ""], False, False)
    assert mt.accumulate([bad]).reason == "empty_row_inside"


def test_a_line_unread_everywhere_is_unread_but_one_read_elsewhere_counts() -> None:
    ws = windows(OPTIONS)
    first = list(ws[0].lines)
    first[3] = mt.RowRead(None, "unknown_glyph")  # unread at the top, read after one scroll
    ws[0] = mt.MenuSnapshot(tuple(first), False, True)
    assert mt.accumulate(ws).reason == "ok"
    first[0] = mt.RowRead(None, "unknown_glyph")  # the first line is seen only there
    ws[0] = mt.MenuSnapshot(tuple(first), False, True)
    full = mt.accumulate(ws)
    assert full.reason == "line_unread" and not mt.cross_check(full, OPTIONS).ok
    assert mt.line_of(full, "About Alpha") is None


def test_the_list_must_run_from_top_to_bottom_and_agree_with_itself() -> None:
    ws = windows(OPTIONS)
    assert mt.accumulate(ws[1:]).reason == "not_at_top"
    assert mt.accumulate(ws[:-1]).reason == "not_at_bottom"
    other = list(ws[1].lines)
    other[0] = mt.RowRead("Something Else", "ok", 1.0)
    ws2 = [ws[0], mt.MenuSnapshot(tuple(other), True, True), *ws[2:]]
    assert mt.accumulate(ws2).reason in ("no_overlap", "conflict")
    same = ["Sun", "Sun", "Sun", "Sun", "Sun"]  # repeated lines: the shift is not unique
    assert mt.accumulate(windows(same)).reason == "ambiguous_shift"


def test_the_cross_check_is_on_the_whole_list() -> None:
    full = mt.accumulate(windows(OPTIONS))
    assert mt.cross_check(full, OPTIONS[:-1]).reason.startswith("count")
    changed = [*OPTIONS[:3], "Forge Anvils", *OPTIONS[4:]]
    assert mt.cross_check(full, changed).reason == "line 4 differs"
    hidden = ["About Alpha", "", "Sun"]  # an empty option is hidden but still counts
    full2 = mt.accumulate([snap(["About Alpha", "Sun", "", ""], False, False)])
    assert mt.cross_check(full2, hidden).packet_index == (1, 3)
    col = ["About Alpha", "^0000FFBlue^000000", "Sun"]
    full3 = mt.accumulate([snap(["About Alpha", None, "Sun", ""], False, False,
                                refuse="coloured_text")])  # fmt: skip
    assert full3.reason == "ok" and mt.cross_check(full3, col).ok
    assert mt.line_of(full3, col[1]) is None  # a coloured option is never a target
