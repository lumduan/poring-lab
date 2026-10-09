"""poring_env.dialog_variant (labels-v2-plan.md 7.4a): the delivery-dialog classifier on a
SYNTHETIC bitmap font and INVENTED pages. No client pixels, no script text, no serial number: the
destinations are map keys, every line and number below is made up. The font keeps the client's
measured spacing (1 blank column inside a word, 5 at a space, ink from the 4th column) and the
dialog's measured layout (16-row bands on a 21-px pitch, word wrap at the measured pixel width)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from poring_env import dialog_variant as dv
from poring_env import menu_text as mt

CHARS = "ABCDEFGHIJKLMNOPRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,'?[]"  # no "Q"
PLAIN = (247, 247, 247)
BLUE = "3355FF"
X0 = 3
SPACE_ADV = 4  # + the glyph's own blank column = a 5-column gap
ORIGIN = (40, 30)
SCENE_BGR = (40, 90, 60)


def make_font(seed: int = 11) -> dict[str, np.ndarray]:
    """Random glyphs, 2-7 columns (1 for a few), ink on rows 2-13, every column inked."""
    rng = np.random.default_rng(seed)
    font: dict[str, np.ndarray] = {}
    seen: set[bytes] = set()
    for c in CHARS + "Q":
        while True:
            w = 1 if c in "il.,'" else int(rng.integers(3, 8))
            g = np.zeros((mt.BAND_H, w), bool)
            g[2:12] = rng.random((10, w)) < 0.45
            for x in range(w):
                g[2 + int(rng.integers(0, 10)), x] = True
            if c in "gjpqy,":
                g[13, w // 2] = True
            key = g.tobytes() + bytes([w])
            if key not in seen:
                seen.add(key)
                font[c] = g
                break
    return font


FONT = make_font()


def bgr(code: str) -> tuple[int, int, int]:
    r, g, b = dv.render_rgb(code)
    return (b, g, r)


def width(tokens: list[tuple[str, str | None]]) -> int:
    """Columns from a line's first ink to its last."""
    x = 0
    for c, _ in tokens:
        x += SPACE_ADV if c == " " else FONT[c].shape[1] + 1
    return x - 1 if tokens else 0


def wrap(line: str, wrap_end: int) -> list[list[tuple[str, str | None]]]:
    """The client's word wrap: a word goes on the line while the line's ink ends <= wrap_end."""
    toks = dv.styled(line)
    words: list[list[tuple[str, str | None]]] = [[]]
    for t in toks:
        if t == dv.SPACE:
            words.append([])
        else:
            words[-1].append(t)
    out: list[list[tuple[str, str | None]]] = [[]]
    for w in words:
        trial = [*out[-1], dv.SPACE, *w] if out[-1] else list(w)
        if out[-1] and X0 + width(trial) > wrap_end:
            out.append(list(w))
        else:
            out[-1] = trial
    return out


def render_page(lines: list[str], wrap_end: int = dv.TEXT.wrap_end, recolour: dict[int, str]
                | None = None) -> np.ndarray:  # fmt: skip
    """A 360x260 frame with the dialog's text area at ORIGIN showing ``lines``; ``recolour``:
    the ink of the n-th drawn glyph replaced (to fake text in another colour)."""
    frame = np.empty((260, 360, 3), np.uint8)
    frame[:] = SCENE_BGR
    ox, oy = ORIGIN
    frame[oy : oy + 178, ox : ox + 278] = 255
    ax, ay, aw, ah = dv.TEXT.area
    frame[oy + ay : oy + ay + ah, ox + ax : ox + ax + aw] = PLAIN
    phys = [p for line in lines for p in wrap(line, wrap_end)]
    n = 0
    for k, toks in enumerate(phys):
        top = oy + ay + dv.TEXT.band_rows(k)[0]
        if top + mt.BAND_H > frame.shape[0]:
            break
        x = ox + ax + X0
        for c, ink in toks:
            if c == " ":
                x += SPACE_ADV
                continue
            g = FONT[c]
            code = (recolour or {}).get(n, ink or dv.BLACK)
            region = frame[top : top + mt.BAND_H, x : x + g.shape[1]]
            region[g[: region.shape[0]]] = bgr(code)
            x += g.shape[1] + 1
            n += 1
    return frame


TRAIN = ["ABCDEFG HIJKLMN", "OPRST UVWXYZ", "abcdefg hijklm", "nopqrst uvwxyz",
         "0123 4567 89", "Mix it.[up] now,", "Why's this? Okay", "Zebra jumps 42 over",
         "Pack 10 boxes", "the Key 7 is [here]."]  # fmt: skip


def menu_row(text: str) -> np.ndarray:
    row = np.empty((mt.BAND_H, 243, 3), np.uint8)
    row[:] = PLAIN
    x = X0
    for c in text:
        if c == " ":
            x += SPACE_ADV
            continue
        row[:, x : x + FONT[c].shape[1]][FONT[c]] = 0
        x += FONT[c].shape[1] + 1
    return row


GLYPHS, FIT = mt.fit_menu_glyphs([menu_row(t) for t in TRAIN], TRAIN)


@pytest.fixture
def glyphs() -> mt.MenuGlyphs:
    return GLYPHS


def test_the_synthetic_font_fits_like_the_clients() -> None:
    assert FIT["skipped"] == {} and set(GLYPHS.chars) == set(CHARS)
    assert GLYPHS.gaps0 == (1,) and GLYPHS.gaps1 == (5,) and GLYPHS.lead_range == (X0, X0)


def _same_width_digits() -> tuple[str, str]:
    """Two digits of one width (pigeonhole: 10 digits, 5 widths), so a serial that differs only
    there has a finite distance to the read."""
    by_w: dict[int, list[str]] = {}
    for d in "0123456789":
        by_w.setdefault(FONT[d].shape[1], []).append(d)
    pair = next(v for v in by_w.values() if len(v) >= 2)
    return pair[0], pair[1]


D1, D2 = _same_width_digits()


# Invented pages, in the shapes the job changer uses (7.4a): a destination page (plain text names
# it), the assignment's serial page (the same plain text for every destination: only the coloured
# serial differs) and the reminder's serial page (one long line, wrapped, serial inside).
NAME = "[Clerk Bob]"
DEST_LINES = {"prontera": "Take the crate to the old mill by the north gate.",
              "geffen_in": "Take the crate to the tower of the west wizards.",
              "morocc_in": "Take the crate to the dyer in the desert town.",
              "izlu2dun": "Take the crate to the clerk on the far island."}  # fmt: skip
SERIALS = {"prontera/1": D1 * 7, "prontera/2": D1 * 6 + D2, "geffen_in/1": "2468024",
           "geffen_in/2": "1357913", "morocc_in/1": "9081726", "morocc_in/2": "5544332",
           "izlu2dun/1": "1122334", "izlu2dun/2": "9988776"}  # fmt: skip


def code(v: str) -> str:
    return f"^{BLUE}{SERIALS[v]}^000000."


def pages() -> list[dv.ExpectedPage]:
    out = [dv.ExpectedPage(f"dest-{d}", frozenset({f"{d}/1", f"{d}/2"}), (NAME, line))
           for d, line in DEST_LINES.items()]  # fmt: skip
    for v in SERIALS:
        out.append(dv.ExpectedPage(f"give-{v}", frozenset({v}),
                                   (NAME, "Recall this.", "The code is", code(v))))  # fmt: skip
        d = dv.destination_of(v)
        town = d.split("_")[0].capitalize()
        out.append(dv.ExpectedPage(
            f"remind-{v}", frozenset({v}),
            (NAME, f"Bring the crate to {town} and say the code of the box, it is {code(v)}"),
        ))  # fmt: skip
    out.append(dv.ExpectedPage("generic", frozenset(SERIALS), (NAME, "All set now?")))
    return out


PAGES = pages()


def page(pid: str) -> dv.ExpectedPage:
    return next(p for p in PAGES if p.page_id == pid)


def run(pid: str, ctx: set[str] | None = None, **kw: object) -> dv.VariantRead:
    frame = render_page(list(page(pid).lines), **kw)  # type: ignore[arg-type]
    return run_frame(frame, ctx)


def run_frame(frame: np.ndarray, ctx: set[str] | None = None, pages_: list[dv.ExpectedPage]
              | None = None, p: dv.Params = dv.PARAMS) -> dv.VariantRead:  # fmt: skip
    r, _ = dv.classify_frame(frame, ORIGIN, GLYPHS, pages_ or PAGES, ctx, p=p)
    return r


def test_colour_model_and_styled_text() -> None:
    assert dv.render_rgb("6666CC") == (99, 99, 206)  # measured on banked frames, 2026-10-09
    assert dv.render_rgb("000000") == (0, 0, 0)
    toks = dv.styled("ab ^3355FF12^000000. ")
    assert toks == [("a", "000000"), ("b", "000000"), (" ", None), ("1", "3355FF"),
                    ("2", "3355FF"), (".", "000000")]  # fmt: skip
    assert set(dv.page_inks(PAGES)) == {"000000", BLUE}


def test_a_destination_page_names_its_destination_only() -> None:
    r = run("dest-morocc_in")
    assert (r.variant, r.destination, r.reason) == (None, "morocc_in", "destination_only")
    assert len(r.line_margins) >= 2 and all(m > 0 for m in r.line_margins)


def test_the_serial_page_needs_the_destination_read_before_it() -> None:
    assert run("give-prontera/2").reason == "destination_unknown"
    r = run("give-prontera/2", {"prontera"})
    assert (r.variant, r.reason) == ("prontera/2", "ok")
    assert 0 < r.variant_margin < math.inf  # the other prontera serial, at the same boxes


def test_a_serial_of_another_destination_is_never_matched() -> None:
    frame = render_page(list(page("give-geffen_in/1").lines))
    assert run_frame(frame, {"prontera"}).reason == "serial_not_candidate"
    assert run_frame(frame, {"geffen_in"}).variant == "geffen_in/1"


def test_a_wrapped_reminder_reads_as_its_variant_without_context() -> None:
    lines = list(page("remind-morocc_in/1").lines)
    assert len(wrap(lines[1], dv.TEXT.wrap_end)) >= 2  # the long line really wraps
    read = dv.read_page(render_page(lines), ORIGIN, GLYPHS, dv.page_inks(PAGES))
    assert read.reason == "ok" and len(read.lines) >= 3 and read.coloured
    r = run("remind-morocc_in/1")
    assert (r.variant, r.destination, r.reason) == ("morocc_in/1", "morocc_in", "ok")


def test_a_wrap_the_client_would_not_make_is_refused() -> None:
    assert run("remind-prontera/1", wrap_end=150).reason == "wrap_inconsistent"


def test_one_wrong_glyph_is_no_page() -> None:
    lines = list(page("dest-prontera").lines)
    lines[1] = lines[1].replace("mill", "mall")
    assert run_frame(render_page(lines)).reason == "no_page_matches"


def test_a_missing_glyph_refuses_before_reading() -> None:
    extra = [*PAGES, dv.ExpectedPage("q", frozenset({"prontera/1"}), (NAME, "Quick"))]
    r, read = dv.classify_frame(render_page([NAME]), ORIGIN, GLYPHS, extra)
    assert (r.variant, r.reason, read) == (None, "glyph_missing:Q", None)


def test_identical_pages_and_near_variants_are_ambiguous() -> None:
    same = [dv.ExpectedPage("a", frozenset({"prontera/1"}), (NAME, "All set now?")),
            dv.ExpectedPage("b", frozenset({"geffen_in/1"}), (NAME, "All set now?"))]  # fmt: skip
    r = run_frame(render_page([NAME, "All set now?"]), pages_=same)
    assert (r.variant, r.reason) == (None, "no_variant_info")
    strict = dv.Params(variant_margin=1e9)  # any other candidate is "within the margin"
    r = run_frame(render_page(list(page("give-prontera/1").lines)), {"prontera"}, p=strict)
    assert (r.variant, r.reason) == (None, "ambiguous_variant")


def test_a_generic_page_carries_no_variant() -> None:
    r = run("generic")
    assert (r.variant, r.destination, r.reason) == (None, None, "no_variant_info")


def test_a_destination_other_than_the_one_read_is_a_conflict() -> None:
    assert run("dest-geffen_in", {"prontera"}).reason == "destination_conflict"


def test_coloured_text_where_black_is_expected_is_refused() -> None:
    lines = list(page("dest-prontera").lines)
    r = run_frame(render_page(lines, recolour={12: BLUE, 13: BLUE}))  # our blue, wrong place
    assert r.reason == "no_page_matches"
    r = run_frame(render_page(lines, recolour={12: "CC2222", 13: "CC2222"}))  # an unknown colour
    assert r.variant is None and r.reason.endswith("coloured_text")


def test_overflow_scrollbar_and_foreign_pixels_are_refused() -> None:
    seven = [NAME, *(f"Line {k}" for k in range(6))]
    pages7 = [dv.ExpectedPage("seven", frozenset({"prontera/1"}), tuple(seven))]
    assert run_frame(render_page(seven), pages_=pages7).reason == "overflow"
    frame = render_page(list(page("dest-prontera").lines))
    ox, oy = ORIGIN
    frame[oy + 20 : oy + 120, ox + 252 : ox + 262] = (230, 150, 100)  # a scrollbar's place
    assert run_frame(frame).reason == "beyond_wrap"
    frame = render_page(list(page("dest-prontera").lines))
    frame[oy + 9 + 27 : oy + 9 + 33, ox + 60 : ox + 66] = (140, 140, 200)  # an occluder
    assert run_frame(frame).reason.endswith("foreign_pixels")


def test_the_conversation_and_the_decision() -> None:
    conv = dv.Conversation()
    conv = conv.add(run("generic"))
    assert conv.context is None
    conv = conv.add(run("dest-prontera"))
    assert (conv.destination, conv.reason, conv.context) == ("prontera", "destination_only",
                                                             frozenset({"prontera"}))  # fmt: skip
    conv = conv.add(run("give-prontera/1", set(conv.context or ())))
    assert (conv.variant, conv.reason) == ("prontera/1", "ok")
    assert conv.add(run("dest-geffen_in")).reason == "conflict_destination"
    assert [dv.decide(v) for v in ("prontera/2", "morocc_in/1", "geffen_in/1", "izlu2dun/2",
                                   None, "alberta/1")] == ["act", "act", "hand_over", "hand_over",
                                                           "stop", "stop"]  # fmt: skip


def test_coverage_counts_classes(glyphs: mt.MenuGlyphs) -> None:
    extra = [*PAGES, dv.ExpectedPage("q", frozenset({"prontera/1"}), ("Quick ~ Fox",))]
    assert dv.missing_chars(extra, glyphs) == "Q~"
    cov = dv.coverage(extra, glyphs)
    assert cov["upper"]["missing"] == 1 and cov["punct"]["missing"] == 1
    assert cov["digit"] == {"needed": 10, "have": 10, "missing": 0}
