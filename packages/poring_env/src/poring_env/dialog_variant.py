"""The Merchant job change's delivery-dialog classifier (labels-v2-plan.md 7.4a; Batt 2026-10-09).

Batt: "build it as a CLASSIFIER over the KNOWN set from L3 (4 destinations x 2 serials = 8
variants), like the T3 menu reader; never free OCR. Verify on the live dialog before relying on it."

The job changer picks one of 4 destinations and one of 2 serial numbers per destination (8
variants) and shows them on its dialog pages: the ASSIGNMENT (the application) and the REMINDER
(every later talk). The expected pages are built at run time from the local L3 extract
(scripts/dialog_variants.py ``extract``: GPL script text, never committed). This module holds no
script text and no serial number; its tests use a synthetic font and invented strings.

READING one page (``read_page``), on a glyph set in T3's format (``menu_text.MenuGlyphs``: one
bitmap per character, client pixels loaded at run time, never committed), fails CLOSED like T3.
The dialog's font IS the menu's (32 shared characters, identical bitmaps, on banked frames), but its
gaps are not: in-word 1-3 columns (an ellipsis: 3) and spaces 4-6, where the menus showed 1-2 and 5.
So the set is cut from DIALOG lines (scripts/dialog_variants.py ``cut``); T3's menu_glyphs.npz as it
stands refuses most dialog lines (``unexplained_gap``). The rules:
  * the text area is cut into fixed 16-row BANDS on the dialog's 21-px line pitch (``DialogText``);
    the rows between bands and below the last full band must be background (a 7th line, which the
    client shows cut off with a scrollbar, is ``overflow``); nothing may be drawn right of the
    wrap width (``beyond_wrap``: the scrollbar sits there);
  * every pixel of a band is background, or a blend of the background with ONE of the page's ink
    colours (black, and each ^RRGGBB code the candidate pages use, drawn as ``render_rgb``), else
    ``foreign_pixels`` / ``coloured_text`` (a chromatic ink no candidate page uses);
  * glyphs are matched exactly as T3 does (one template of the run's width under max_score,
    beating every other by min_margin; touching glyphs split one unique way; gaps are in-word gaps
    or spaces); each glyph takes the colour of >= 90 % of its ink (``mixed_colour`` otherwise).

CLASSIFYING the read against the closed set (``classify``):
  1. every character the candidate pages need must have a template, else
     ``glyph_missing:<chars>`` before anything is read;
  2. PLAIN match: the read lines must equal a candidate page's mes lines glyph for glyph and colour
     for colour, with coloured characters (the serial) as wildcards; physical lines are mapped onto
     mes lines by WORD WRAP (below);
  3. the DESTINATION is fixed by the plain text, narrowed by ``destinations`` (what earlier pages
     of the same conversation said: a disagreement is ``destination_conflict``);
  4. a page that shows coloured text needs ONE destination by then (``destination_unknown``
     otherwise: the serial-only page of the assignment needs the page before it); its coloured
     glyphs are then compared with the serials of THAT destination's variants only (a closed set
     of <= 2, never free digits): none equal -> ``serial_not_candidate``;
  5. any other eligible candidate whose glyphs, at the read glyphs' boxes, lie within
     ``variant_margin`` of the read -> ``ambiguous_variant``.
The result names a variant (``ok``), only a destination (``destination_only``: the page restates
the destination, not the serial), or nothing (``no_variant_info``: a page every variant shows).

WRAPPING (measured 2026-10-10, offline, on the banked RDP dialog frames of the 7 talk@1
calibration sessions of 2026-10-09, packet-labelled by npc_say; scripts/dialog_variants.py
``measure-wrap``: 28 pages, 126 lines, 59 wraps): the client WORD-wraps a long mes line by PIXEL
width, not by character count (a 41-character line fitted where a 35-character one wrapped). Every
line that fit ended its ink at text-area column <= 213; every wrap happened where the next word
would have ended at >= 214. The classifier therefore accepts a mapping of physical lines onto mes
lines only when
(a) the physical lines of one mes line, joined with ONE space, are that mes line, and (b) the wrap
is the one this rule makes: each line ends <= ``wrap_end`` + slack, and each wrapped line's next
word (its measured width, after one space gap) would end > ``wrap_end`` - slack. ``wrap_end`` is a
parameter; the merchant dialog's own lines re-check it live.

COLOUR: the client draws ^RRGGBB in 15-bit colour (5 bits a channel, top bits repeated):
^6666CC showed as exactly (99, 99, 206) on the same frames. The serial's code is read from the L3
lines, never hard-coded here.
"""

from __future__ import annotations

import math
import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import numpy.typing as npt

from poring_env import menu_text as mt
from poring_env.npc_dialog import GEOMETRY as T2_GEOMETRY

Gray = npt.NDArray[np.float32]
RGB = tuple[int, int, int]
Box = tuple[int, int, int, int]
Tok = tuple[str, str | None]  # (character, ink code); a space is (" ", None)
Decision = Literal["act", "hand_over", "stop"]

BLACK = "000000"
PLAIN_RGB: RGB = mt.PLAIN_RGB  # the text area's background (measured: exactly 247 grey)
COLOUR_CODE = re.compile(r"\^([0-9A-Fa-f]{6})")
SPACE: Tok = (" ", None)

# Batt's c (2026-10-09): only the two easiest destinations are acted on; the other two are
# classified so the hand-over can say which, then the workflow stops. Batt 2026-10-15 (decision 4):
# morocc_in is DROPPED (morocc's client GAT and server map cache disagree on 4,482 cells); its
# replacement by the same criteria (Kafra hops, map agreement) is geffen_in: 4 Kafra hops, and
# prontera / geffen / geffen_in agree except 8 geffen cells 14+ cells off the delivery walk
# (izlu2dun's routes all cross izlude, whose client map is another size). labels-v2-plan 7.7.
ACT_DESTINATIONS = frozenset({"prontera", "geffen_in"})
HAND_OVER_DESTINATIONS = frozenset({"morocc_in", "izlu2dun"})


def render_rgb(code: str) -> RGB:
    """The colour the client draws a ^RRGGBB code in: 15-bit, 5 bits a channel with the top bits
    repeated below (^6666CC -> (99, 99, 206), as measured)."""
    v = int(code, 16)
    out = []
    for shift in (16, 8, 0):
        c5 = ((v >> shift) & 0xFF) >> 3
        out.append((c5 << 3) | (c5 >> 2))
    return (out[0], out[1], out[2])


def destination_of(variant: str) -> str:
    """A variant id is ``<destination map>/<serial slot>`` (e.g. ``prontera/1``)."""
    return variant.rsplit("/", 1)[0]


def char_class(c: str) -> str:
    if c.isdigit():
        return "digit"
    if c.isupper():
        return "upper"
    if c.islower():
        return "lower"
    return "punct"


# --- the expected pages --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExpectedPage:
    """One page the job changer can show: its mes lines (raw, ^RRGGBB codes kept) and the
    variants that show it. Built at run time from the local L3 extract; never committed."""

    page_id: str
    variants: frozenset[str]
    lines: tuple[str, ...]

    @property
    def destinations(self) -> frozenset[str]:
        return frozenset(destination_of(v) for v in self.variants)


def styled(line: str) -> list[Tok]:
    """(character, ink code) of what the client draws for one mes line: colour codes switch the
    ink (black first) and take no room; trailing spaces are invisible."""
    out: list[Tok] = []
    ink = BLACK
    pos = 0
    for m in COLOUR_CODE.finditer(line):
        out += [SPACE if c == " " else (c, ink) for c in line[pos : m.start()]]
        ink = m.group(1).upper()
        pos = m.end()
    out += [SPACE if c == " " else (c, ink) for c in line[pos:]]
    while out and out[-1] == SPACE:
        out.pop()
    return out


def page_inks(pages: Iterable[ExpectedPage]) -> dict[str, RGB]:
    """Every ink the pages draw in (black always), as the client renders it."""
    codes = {BLACK}
    for p in pages:
        for line in p.lines:
            codes |= {ink for c, ink in styled(line) if ink is not None}
    return {c: render_rgb(c) for c in sorted(codes)}


def needed_chars(pages: Iterable[ExpectedPage]) -> set[str]:
    return {c for p in pages for line in p.lines for c, ink in styled(line) if ink is not None}


def missing_chars(pages: Iterable[ExpectedPage], g: mt.MenuGlyphs) -> str:
    """The characters the pages need that the glyph set has no template for (sorted)."""
    return "".join(sorted(needed_chars(pages) - set(g.chars)))


def coverage(pages: Sequence[ExpectedPage], g: mt.MenuGlyphs) -> dict[str, dict[str, int]]:
    """Per character class: how many distinct characters the pages need, have, and miss."""
    need = needed_chars(pages)
    have = set(g.chars)
    out: dict[str, dict[str, int]] = {}
    for c in need:
        row = out.setdefault(char_class(c), {"needed": 0, "have": 0, "missing": 0})
        row["needed"] += 1
        row["have" if c in have else "missing"] += 1
    return dict(sorted(out.items()))


# --- the geometry --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DialogText:
    """Where the dialog draws its lines, as offsets in the npc_dialog window (measured 2026-10-10
    on 414 banked RDP dialog frames of 2026-10-09: ink of a line on rows 6-17 (+21 per line) of the
    text area, its first column 3 or 4, black exactly (0,0,0) on (247,247,247))."""

    area: Box = T2_GEOMETRY.dialog_text  # (9, 9, 260, 140): the grey text area
    band_top: int = 4  # line k's 16-row band starts at area row band_top + k * pitch
    pitch: int = 21
    wrap_end: int = 213  # a line's ink ends at area column <= this (exclusive end); see module
    wrap_slack: int = 1

    @property
    def bands(self) -> int:
        """Full bands that fit in the area (6)."""
        return (self.area[3] - self.band_top - mt.BAND_H) // self.pitch + 1

    def band_rows(self, k: int) -> tuple[int, int]:
        top = self.band_top + k * self.pitch
        return top, top + mt.BAND_H


TEXT = DialogText()


@dataclass(frozen=True, slots=True)
class Params:
    """Acceptance rules on top of the glyph set's own (max_score, min_margin)."""

    ink_tol: float = 32.0  # a pixel this far from every background-to-ink blend is foreign
    bg_tol: int = 16  # within this of the background (each channel): background
    foreign_max: int = 1  # foreign pixels a band tolerates (one codec speck)
    chroma: int = 80  # a foreign pixel this chromatic is coloured text
    colour_share: float = 0.9  # a glyph's ink must be this much one colour
    variant_margin: float | None = None  # None: the glyph set's min_margin


PARAMS = Params()


# --- reading -------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CGlyph:
    """One glyph: its columns [x, x + w) in the band, character, ink, score, margin to the next
    best template of its width, and every same-width template's score (for variant margins)."""

    x: int
    w: int
    char: str
    ink: str
    score: float
    margin: float
    alts: tuple[tuple[str, float], ...] = ()

    def score_of(self, c: str) -> float:
        for k, s in self.alts:
            if k == c:
                return s
        return math.inf


@dataclass(frozen=True, slots=True)
class LineRead:
    """One band: ``reason`` "ok" (glyphs read), "empty", or why it could not be read."""

    reason: str
    glyphs: tuple[CGlyph, ...] = ()
    spaces: tuple[int, ...] = ()  # spaces before each glyph (0 before the first)

    @property
    def tokens(self) -> list[Tok]:
        out: list[Tok] = []
        for gl, n in zip(self.glyphs, self.spaces, strict=True):
            out += [SPACE] * n
            out.append((gl.char, gl.ink))
        return out

    @property
    def text(self) -> str:
        return "".join(c for c, _ in self.tokens)

    @property
    def end(self) -> int:
        """The column after the last ink (0 for an empty band)."""
        return self.glyphs[-1].x + self.glyphs[-1].w if self.glyphs else 0

    @property
    def first_word_width(self) -> int:
        """Columns from the first glyph's start to the end of the first word."""
        if not self.glyphs:
            return 0
        end = self.glyphs[0].x + self.glyphs[0].w
        for gl, n in zip(self.glyphs[1:], self.spaces[1:], strict=True):
            if n:
                break
            end = gl.x + gl.w
        return end - self.glyphs[0].x

    @property
    def margin(self) -> float:
        return min((gl.margin for gl in self.glyphs), default=math.inf)


@dataclass(frozen=True, slots=True)
class PageRead:
    """The page's lines top to bottom (trailing empty bands dropped); ``reason`` "ok" or why the
    page could not be read (``lineK:<why>`` for band K, 1-based)."""

    lines: tuple[LineRead, ...]
    reason: str

    @property
    def coloured(self) -> bool:
        return any(gl.ink != BLACK for ln in self.lines for gl in ln.glyphs)


def ink_layers(band_bgr: npt.NDArray[np.uint8], inks: Mapping[str, RGB], p: Params = PARAMS
               ) -> tuple[Gray, npt.NDArray[np.int64], npt.NDArray[np.bool_]]:  # fmt: skip
    """(ink probability, index of the ink into ``inks`` or -1, foreign) per pixel: each pixel is
    explained as background * (1 - a) + ink * a for the ink that leaves the least residual."""
    rgb = band_bgr[..., 2::-1].astype(np.float32)
    bg = np.array(PLAIN_RGB, np.float32)
    background = (np.abs(rgb - bg) <= p.bg_tol).all(axis=-1)
    best_a = np.zeros(rgb.shape[:2], np.float32)
    best_k = np.full(rgb.shape[:2], -1, np.int64)
    best_r = np.full(rgb.shape[:2], np.inf, np.float32)
    for k, ink in enumerate(inks.values()):
        d = np.array(ink, np.float32) - bg
        dd = float(d @ d)
        if dd == 0:
            continue
        a = np.clip(((rgb - bg) @ d) / dd, 0.0, 1.0).astype(np.float32)
        r = np.abs(rgb - (bg + a[..., None] * d)).max(axis=-1)
        better = r < best_r
        best_a = np.where(better, a, best_a)
        best_k = np.where(better, k, best_k)
        best_r = np.where(better, r, best_r)
    foreign = ~background & (best_r > p.ink_tol)
    prob = np.where(background | foreign, 0.0, best_a).astype(np.float32)
    kind = np.where(background | foreign, -1, best_k)
    return prob, kind, foreign


def _foreign_kind(band_bgr: npt.NDArray[np.uint8], foreign: npt.NDArray[np.bool_],
                  p: Params) -> str | None:  # fmt: skip
    if int(foreign.sum()) <= p.foreign_max:
        return None
    rgb = band_bgr[..., :3].astype(np.int16)[foreign]
    chroma = rgb.max(axis=-1) - rgb.min(axis=-1)
    return "coloured_text" if float((chroma >= p.chroma).mean()) >= 0.5 else "foreign_pixels"


def _match(prob: Gray, a: int, b: int, g: mt.MenuGlyphs) -> CGlyph | None:
    """menu_text.span_match, keeping every same-width template's score."""
    idx = np.flatnonzero(g.widths == b - a)
    if idx.size == 0:
        return None
    span = prob[:, a:b]
    scores = sorted((float(((span - g.bitmap(int(i))) ** 2).sum()), g.chars[int(i)]) for i in idx)
    s1, c1 = scores[0]
    margin = scores[1][0] - s1 if len(scores) > 1 else math.inf
    if s1 > g.max_score or margin < g.min_margin:
        return None
    return CGlyph(a, b - a, c1, "", s1, margin, tuple((c, s) for s, c in scores))


def _split(prob: Gray, a: int, b: int, g: mt.MenuGlyphs) -> list[list[CGlyph]]:
    """menu_text.split_run with ``_match``: every way to read [a, b) as 2..MAX_SPLIT glyphs."""
    out: list[list[CGlyph]] = []

    def walk(x: int, acc: list[CGlyph]) -> None:
        if x == b:
            if len(acc) >= 2:
                out.append(list(acc))
            return
        if len(acc) == mt.MAX_SPLIT or len(out) > 1:
            return
        for w in sorted({int(v) for v in g.widths}):
            if x + w > b:
                break
            got = _match(prob, x, x + w, g)
            if got is not None:
                walk(x + w, [*acc, got])

    walk(a, [])
    return out


def read_band(band_bgr: npt.NDArray[np.uint8], g: mt.MenuGlyphs, inks: Mapping[str, RGB],
              p: Params = PARAMS) -> LineRead:  # fmt: skip  # noqa: PLR0911
    """One dialog line from its band (BAND_H rows from the text area's left edge; BGR). The token
    loop mirrors menu_text.read_row (the proven T3 rules), on the multi-ink map."""
    if band_bgr.shape[0] != mt.BAND_H or band_bgr.shape[1] < 8:
        return LineRead("bad_band")
    prob, kind, foreign = ink_layers(band_bgr, inks, p)
    why = _foreign_kind(band_bgr, foreign, p)
    if why is not None:
        return LineRead(why)
    ink = prob >= mt.INK_P
    if not ink.any():
        return LineRead("empty")
    runs = mt.ink_runs(ink)
    tokens: list[tuple[list[CGlyph], int]] = []
    i = 0
    while i < len(runs):
        a, b = runs[i]
        single = _match(prob, a, b, g)
        alone = [[single]] if single is not None else _split(prob, a, b, g)
        merged = None
        if i + 1 < len(runs) and runs[i + 1][0] - b <= mt.MERGE_GAP:
            merged = _match(prob, a, runs[i + 1][1], g)
        if merged is not None and alone:
            return LineRead("ambiguous_glyph")
        if merged is not None:
            tokens.append(([merged], runs[i + 1][1]))
            i += 2
            continue
        if len(alone) != 1:
            return LineRead("unknown_glyph" if not alone else "ambiguous_glyph")
        tokens.append((alone[0], b))
        i += 1
    names = list(inks)
    glyphs: list[CGlyph] = []
    spaces: list[int] = []
    for k, (gls, _end) in enumerate(tokens):
        n = 0
        if k:
            got = g.spaces(gls[0].x - tokens[k - 1][1])
            if got is None:
                return LineRead("unexplained_gap")
            n = got
        for j, gl in enumerate(gls):
            box = kind[:, gl.x : gl.x + gl.w][ink[:, gl.x : gl.x + gl.w]]
            counts = np.bincount(box[box >= 0], minlength=len(names))
            if counts.sum() == 0 or counts.max() < p.colour_share * counts.sum():
                return LineRead("mixed_colour")
            glyphs.append(CGlyph(gl.x, gl.w, gl.char, names[int(counts.argmax())], gl.score,
                                 gl.margin, gl.alts))  # fmt: skip
            spaces.append(n if j == 0 else 0)
    first = glyphs[0]
    want = g.lead.get(first.char)
    lo, hi = (want, want) if want is not None else g.lead_range
    if not lo - 1 <= first.x <= hi + 1:
        return LineRead("leading_blank")
    return LineRead("ok", tuple(glyphs), tuple(spaces))


def read_page(frame_bgr: npt.NDArray[np.uint8], origin: tuple[int, int], g: mt.MenuGlyphs,
              inks: Mapping[str, RGB], t: DialogText = TEXT, p: Params = PARAMS
              ) -> PageRead:  # fmt: skip
    """Every line of the dialog at ``origin`` (its window's top-left, from T2) on one frame (the
    1280x720 client area, BGR or BGRA)."""
    ax, ay, aw, ah = t.area
    x0, y0 = origin[0] + ax, origin[1] + ay
    if x0 < 0 or y0 < 0 or y0 + ah > frame_bgr.shape[0] or x0 + aw > frame_bgr.shape[1]:
        return PageRead((), "outside_frame")
    area = np.ascontiguousarray(frame_bgr[y0 : y0 + ah, x0 : x0 + aw, :3])
    bg = (np.abs(area.astype(np.int16) - np.array(PLAIN_RGB[::-1], np.int16)) <= p.bg_tol
          ).all(axis=-1)  # fmt: skip
    right = t.wrap_end + t.wrap_slack + 1
    if int((~bg[:, right:]).sum()) > p.foreign_max:
        return PageRead((), "beyond_wrap")
    in_band = np.zeros(ah, bool)
    for k in range(t.bands):
        top, bottom = t.band_rows(k)
        in_band[top:bottom] = True
    below = t.band_rows(t.bands)[0]
    if int((~bg[below:]).sum()) > p.foreign_max:
        return PageRead((), "overflow")
    if int((~bg[~in_band]).sum()) > p.foreign_max:
        return PageRead((), "foreign_pixels")
    lines: list[LineRead] = []
    for k in range(t.bands):
        top, bottom = t.band_rows(k)
        r = read_band(area[top:bottom, :right], g, inks, p)
        if r.reason not in ("ok", "empty"):
            return PageRead(tuple(lines), f"line{k + 1}:{r.reason}")
        lines.append(r)
    while lines and lines[-1].reason == "empty":
        lines.pop()
    return PageRead(tuple(lines), "ok" if lines else "no_text")


# --- classifying ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class VariantRead:
    """``variant``: the one variant the page shows, else None; ``destination``: the one
    destination it shows (also without a serial); ``reason``: "ok", "destination_only",
    "no_variant_info" or why nothing could be decided."""

    variant: str | None
    reason: str
    destination: str | None = None
    page_id: str | None = None
    line_margins: tuple[float, ...] = ()
    variant_margin: float = math.inf

    def summary(self) -> dict[str, object]:
        def num(v: float) -> float | None:
            return None if math.isinf(v) else round(v, 3)

        return {"variant": self.variant, "destination": self.destination, "reason": self.reason,
                "page_id": self.page_id, "line_margins": [num(m) for m in self.line_margins],
                "variant_margin": num(self.variant_margin)}  # fmt: skip


def _same(r: Tok, e: Tok, plain: bool) -> bool:
    if r == SPACE or e == SPACE:
        return r == e
    if r[1] != e[1]:
        return False
    return (plain and e[1] != BLACK) or r[0] == e[0]


def fit_lines(phys: Sequence[Sequence[Tok]], mes: Sequence[Sequence[Tok]],
              plain: bool = False) -> list[tuple[int, int]] | None:  # fmt: skip
    """[a, b) of the physical lines each mes line was drawn on, when the physical lines, in order,
    are the mes lines word-wrapped (the lines of one mes line joined by one space equal it); with
    ``plain`` coloured characters match any character of their colour. None when no such map."""
    memo: dict[tuple[int, int], list[tuple[int, int]] | None] = {}

    def go(i: int, k: int) -> list[tuple[int, int]] | None:
        if i == len(mes):
            return [] if k == len(phys) else None
        if k == len(phys) or (i, k) in memo:
            return memo.get((i, k))
        want = mes[i]
        out: list[tuple[int, int]] | None = None
        joined: list[Tok] = []
        for b in range(k + 1, len(phys) + 1):
            if b > k + 1:
                if not phys[b - 1]:
                    break  # an empty line never continues a wrapped one
                joined = [*joined, SPACE]
            joined = [*joined, *phys[b - 1]]
            if len(joined) > len(want):
                break
            if len(joined) == len(want) and all(
                _same(r, e, plain) for r, e in zip(joined, want, strict=True)
            ):
                rest = go(i + 1, b)
                if rest is not None:
                    out = [(k, b), *rest]
                    break
        memo[(i, k)] = out
        return out

    return go(0, 0)


def wrap_ok(lines: Sequence[LineRead], spans: Sequence[tuple[int, int]], g: mt.MenuGlyphs,
            t: DialogText = TEXT) -> bool:  # fmt: skip
    """Every line fits the wrap width, and every wrap is where the next word would not fit."""
    gap = int(round(float(np.median(g.gaps1))))
    if any(ln.end > t.wrap_end + t.wrap_slack for ln in lines):
        return False
    for a, b in spans:
        for j in range(a, b - 1):
            nxt = lines[j + 1]
            if lines[j].end + gap + nxt.first_word_width <= t.wrap_end - t.wrap_slack:
                return False
    return True


def _distance(read: PageRead, page: ExpectedPage) -> float:
    """How far the page's text is from the read, scored at the read glyphs' boxes: 0 when equal;
    the sum of (score of the page's character - score of the read one) where they differ; inf
    when the glyph count, a colour, or a width differs."""
    got = [gl for ln in read.lines for gl in ln.glyphs]
    want = [tok for line in page.lines for tok in styled(line) if tok != SPACE]
    if len(got) != len(want):
        return math.inf
    total = 0.0
    for gl, (c, ink) in zip(got, want, strict=True):
        if gl.ink != ink:
            return math.inf
        if gl.char != c:
            total += gl.score_of(c) - gl.score
    return total


def classify(read: PageRead, pages: Sequence[ExpectedPage], g: mt.MenuGlyphs,
             destinations: Collection[str] | None = None, t: DialogText = TEXT,
             p: Params = PARAMS) -> VariantRead:  # fmt: skip  # noqa: PLR0911
    """The read page against the closed set (see the module docstring for the rules)."""
    lacking = missing_chars(pages, g)
    if lacking:
        return VariantRead(None, f"glyph_missing:{lacking}")
    if read.reason != "ok":
        return VariantRead(None, read.reason)
    margins = tuple(ln.margin for ln in read.lines)
    phys = [ln.tokens for ln in read.lines]
    plain: list[tuple[ExpectedPage, list[tuple[int, int]]]] = []
    for page in pages:
        spans = fit_lines(phys, [styled(x) for x in page.lines], plain=True)
        if spans is not None:
            plain.append((page, spans))
    if not plain:
        return VariantRead(None, "no_page_matches", line_margins=margins)
    if destinations is not None:
        allowed = set(destinations)
        plain = [
            (ExpectedPage(pg.page_id, frozenset(v for v in pg.variants
                                                if destination_of(v) in allowed), pg.lines), s)
            for pg, s in plain
        ]  # fmt: skip
        plain = [(pg, s) for pg, s in plain if pg.variants]
        if not plain:
            return VariantRead(None, "destination_conflict", line_margins=margins)
    if read.coloured:
        dests = {d for pg, _ in plain for d in pg.destinations}
        if len(dests) != 1:
            return VariantRead(None, "destination_unknown", line_margins=margins)
    exact = [(pg, s) for pg, s in plain
             if fit_lines(phys, [styled(x) for x in pg.lines]) is not None]  # fmt: skip
    if not exact:
        why = "serial_not_candidate" if read.coloured else "no_page_matches"
        return VariantRead(None, why, line_margins=margins)
    exact = [(pg, s) for pg, s in exact if wrap_ok(read.lines, s, g, t)]
    if not exact:
        return VariantRead(None, "wrap_inconsistent", line_margins=margins)
    variants = frozenset(v for pg, _ in exact for v in pg.variants)
    page_id = exact[0][0].page_id if len(exact) == 1 else None
    others = [pg for pg, _ in plain if not pg.variants <= variants]
    margin = min((_distance(read, pg) for pg in others), default=math.inf)
    need = g.min_margin if p.variant_margin is None else p.variant_margin
    if margin < need:
        return VariantRead(None, "ambiguous_variant", line_margins=margins,
                           variant_margin=margin)  # fmt: skip
    dests = {destination_of(v) for v in variants}
    if len(variants) == 1:
        (v,) = variants
        return VariantRead(v, "ok", destination_of(v), page_id, margins, margin)
    if len(dests) == 1:
        (d,) = dests
        return VariantRead(None, "destination_only", d, page_id, margins, margin)
    return VariantRead(None, "no_variant_info", None, page_id, margins, margin)


def classify_frame(frame_bgr: npt.NDArray[np.uint8], origin: tuple[int, int],
                   g: mt.MenuGlyphs, pages: Sequence[ExpectedPage],
                   destinations: Collection[str] | None = None, t: DialogText = TEXT,
                   p: Params = PARAMS) -> tuple[VariantRead, PageRead | None]:  # fmt: skip
    """``read_page`` (inks: black and every colour the pages use) then ``classify``; nothing is
    read while a needed glyph is missing."""
    lacking = missing_chars(pages, g)
    if lacking:
        return VariantRead(None, f"glyph_missing:{lacking}"), None
    read = read_page(frame_bgr, origin, g, page_inks(pages), t, p)
    return classify(read, pages, g, destinations, t, p), read


# --- the conversation and the decision ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Conversation:
    """What the pages of ONE conversation said so far: a destination (from any page naming one)
    and the variant (from the serial page). Pages that disagree end it (``conflict``)."""

    destination: str | None = None
    variant: str | None = None
    reason: str = "empty"
    reads: tuple[str, ...] = field(default=())

    @property
    def context(self) -> frozenset[str] | None:
        """The ``destinations`` to classify the next page with."""
        return None if self.destination is None else frozenset({self.destination})

    def add(self, r: VariantRead) -> Conversation:
        log = (*self.reads, r.reason)
        if self.reason.startswith("conflict"):
            return Conversation(self.destination, None, self.reason, log)
        if r.destination is None:
            return Conversation(self.destination, self.variant, self.reason, log)
        if self.destination is not None and r.destination != self.destination:
            return Conversation(None, None, "conflict_destination", log)
        if r.variant is not None and self.variant not in (None, r.variant):
            return Conversation(None, None, "conflict_variant", log)
        variant = r.variant or self.variant
        return Conversation(r.destination, variant, "ok" if variant else "destination_only", log)


def decide(variant: str | None) -> Decision:
    """Batt's c, as amended 2026-10-15 (decision 4): act on the prontera and geffen_in variants;
    hand the morocc_in and izlu2dun ones over to a person (the hand-over names the variant); stop on
    anything else."""
    if variant is None:
        return "stop"
    d = destination_of(variant)
    if d in ACT_DESTINATIONS:
        return "act"
    if d in HAND_OVER_DESTINATIONS:
        return "hand_over"
    return "stop"
