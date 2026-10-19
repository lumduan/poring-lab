#!/usr/bin/env python3
"""The client's BATTLE LOG chat tab, read from PIXELS (Batt 2026-10-19: the hunting layout has it).

    battle_log.py replay SID [--frames DIR] [--out FILE] [--lang L]
                        a banked session's frames -> /dev/shm/poring-lab-demo/SID/battle_log.jsonl
    battle_log.py live --out FILE [--hz 5] [--until-pid PID] [--lang L]
                        the LIVE frames, read-only
    battle_log.py formats-init en [--force]          write <anchors>/en/formats.json
    battle_log.py clusters [SID] [--every 2] [--images IMG ...] [--lang L] [--out DIR]
                                                     design time: the glyph runs, clustered
    battle_log.py cut CLUSTERS.npz LABELS.json [--lang L]   design time: <lang>/glyphs.npz
    battle_log.py cut-names SID [--lang L]           design time: <lang>/names.npz, labelled by
                                                     the session's packets

LANGUAGE-INDEPENDENT (Batt 2026-10-19 ~19:50): the EVENTS are fixed -- damage {n, name},
base_exp {n}, job_exp {n}, item {count}, other -- and each client language is DATA, in the
gitignored data/ui_anchors/battle_log/<lang>/: formats.json (the line formats: fixed words around
the stable anchors, a [bracketed name] and 'quoted' / (parenthesised) / bare numbers; the
rendering: band rows above / below the x-height for stacked marks, glyph min width; the schema is
documented at "events and per-language line formats" below), glyphs.npz (that client's glyph
templates: a script's own font, clusters of a base glyph and its marks for Thai), names.npz. The
language is --lang, else data/ui_anchors/battle_log/lang.json {"lang": ...}, else "en"; --lang
auto picks, on the first frames, the language whose words type the most lines (not used live
yet). English is the live, validated path (v43 runs 1-2; its glyph / name files may also sit
directly in data/ui_anchors/battle_log/, as before languages). Thai: formats.json and a parser
fixture from Batt's screenshot (text); its glyphs need the screenshot's PIXELS (th/README.txt).
No client text is committed: `formats-init en` builds the English file from words in code.

THIS MODULE NEVER SENDS INPUT. ``live`` holds no Agent and opens no ro_agent.session: it reads
frames (ro_agent.Screen().grab of the chat window's rows of the game region, as human_demo's
recorder does) and nothing else (test_battle_log.py checks the source).

The chat window of the hunting layout (measured on 20261019T152849-demo-hunt-flow43's frames,
client px): the tab strip at y 529..545, THREE message lines on a 14 px pitch, line k's band at
rows 551 + 14 k .. 564 + 14 k (x-height rows 555..561 of line 0, ascenders from 552, descenders
to 563), the text from x 8 (the damage line starts with a space: x 12) to at most x 580; the
scrollbar is right of x 584 and the input box below y 596. The newest line is the BOTTOM one; a
new line scrolls the others up by one band. Battle Log is the SELECTED tab when the window's top
border (row 545, opaque) runs under Regular Chat and not under Battle Log; both tabs are
translucent, so a template of their fill fails over dark grass, the border does not.

Reading (pure functions):
- a line's ink = LUMA > LUMA_MIN in its band, minus PINK (a Poring behind the translucent window
  passes the luma bar), then only the pixels of the line's colour: the client's flat bitmap font
  is bright on the darkened window (background under ~110 luma; yellow text ~235, cyan ~180).
  Luma, not a colour mask: the recorded frames are JPEG q80, the chroma is subsampled and a cyan
  mask lost whole strokes; the luma plane is full resolution;
- glyph runs = column runs of ink split on empty columns; a gap of >= SPACE_COLS columns is a
  space. Each run is matched to the nearest glyph template (Hamming over the full band height, so
  a quote and a comma differ by row; width +-1), within a tolerance and a margin over the next
  other character; a run that matches nothing is tried as two touching glyphs (a JPEG speck
  bridges a gap), else it reads '?'. Thai item names read as '?'s, never as text;
- the line's colour = its ink's mean RGB (yellow / cyan / teal / white / red / green);
- the type by the decoded text's SHAPE with fuzzy fixed words (classify): DAMAGE
  `[<name>] receives '<N>' damage points.`, BASE / JOB EXP `'<N>' Base|Job Experience
  acquired.`, ITEM `You got <...> (<count>).`, else OTHER (drops, broadcasts). A spoiled glyph
  in a fixed word does not change the type; a number is read only when every digit matched,
  else its field is None (the line is not "clean");
- the monster NAME = the bracketed text, mapped to the species vocabulary (exact, or the one
  name the read letters fit, '?' = 1-2 letters); species name templates (`cut-names`, labelled
  by packets) answer when that fails.

NEW lines (lines carry no timestamps): the visible lines of a frame are compared with the last
frame's (frames with another tab are skipped; the comparison resumes against the last Battle
Log frame). The smallest shift s (0..3) with this frame's first 3 - s lines EQUAL to the last
frame's lines s.. is taken; the bottom s lines are new. Equal (same_line) = the same colour
group and the glyph runs aligned column by column: read glyphs must agree, an unread glyph
matches anything (one spoiled glyph does not make a line new), an extra unread run (a sprite's
highlight) is ignored, an extra read run or a different digit is a difference. Identical
consecutive lines (two kills with the same EXP) are therefore counted right whenever the scroll
is SEEN: [dmg, base 2, job 1] -> [base 2, job 1, dmg'] is s = 1 even though the old and the new
lines repeat. What cannot be seen is a scroll that brings back exactly the lines it pushed out
(all three, or a period of the pattern) within one frame interval: the smallest shift is taken
(an undercount) and the frame counts as ``ambiguous``. s = 3 is no overlap: >= 3 new lines, any
beyond 3 never visible (``overflow``). Reader (below) adds a one-frame hold for a no-overlap
jump that looks like a misread, and the refinement of a line read unclean on its first frame.

Templates and formats are client data: data/ui_anchors/battle_log/ (gitignored), never committed.
"""

from __future__ import annotations

import argparse
import dataclasses
import difflib
import json
import os
import re
import signal
import sys
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEMO = Path("/dev/shm/poring-lab-demo")
RECORDINGS = Path("/mnt/poring-lab-datasets/hunt-recordings")
ANCHORS = ROOT / "data/ui_anchors/battle_log"
GLYPHS = ANCHORS / "glyphs.npz"
NAMES = ANCHORS / "names.npz"

# --- geometry (client px of the 1280 x 720 game region) -------------------------------------------
CROP = (0, 528, 600, 600)  # x0, y0, x1, y1: what a live grab takes (the tabs + the 3 lines)
# the window's top border row, under the Battle Log tab and under the Regular Chat tab
TAB_EDGE_Y, BATTLE_SPAN, REGULAR_SPAN, TAB_EDGE_LUMA = 545, (6, 76), (86, 156), 180
LINE_Y0, LINE_PITCH, N_LINES = 551, 14, 3
TEXT_X0, TEXT_X1 = 4, 580
LUMA_MIN = 140
LUMA_REL, LUMA_FLOOR = 0.68, 120  # the colour pass: 0.68 x the line's median ink luma, >= 120
SPACE_COLS = 3
MIN_INK = 2  # a run of fewer ink pixels is a speck
# glyph match: the nearest template within max(MATCH_MIN, MATCH_FRAC x its ink) pixels and at
# least MATCH_MARGIN closer than the nearest template of another character
MATCH_MIN, MATCH_FRAC, MATCH_MARGIN = 2, 0.15, 2
REFINE_FRAMES = 3  # a new line not read in full waits this many frames for a clean read
LIKE_MIN = 0.6  # a decoded word reads as a fixed word at this SequenceMatcher ratio

SPECIES = ("Poring", "Lunatic", "Fabre", "Pupa", "Creamy", "Rocker", "Chonchon", "Willow",
           "Condor", "Drops", "Picky", "Roda Frog", "Thief Bug", "Hornet")  # fmt: skip
TYPES = ("damage", "base_exp", "job_exp", "item", "other")
LANG_FILE = ANCHORS / "lang.json"  # {"lang": "<code>"}: this host's default language
AUTO_LINES = 6  # --lang auto: decide on the first frames holding this many lines (or AUTO_FRAMES)
AUTO_FRAMES = 300


@dataclass(frozen=True)
class Render:
    """How a language's client draws the chat lines (formats.json "render"; the defaults are the
    English lab client's, measured on v43 run 1). A line's band is its pitch plus band_above /
    band_below rows (a script with stacked marks above and below the x-height -- Thai -- needs
    them; the bands of neighbouring lines then overlap). Runs narrower than min_glyph_w closer
    than space_cols to a neighbour join it (a mark drawn beside its base glyph)."""

    line_y0: int = LINE_Y0
    line_pitch: int = LINE_PITCH
    n_lines: int = N_LINES
    band_above: int = 0
    band_below: int = 0
    text_x0: int = TEXT_X0
    text_x1: int = TEXT_X1
    luma_min: float = LUMA_MIN
    space_cols: int = SPACE_COLS
    min_ink: int = MIN_INK
    min_glyph_w: int = 1
    colour_check: bool = False  # True: an event's "colour" must match the line's colour group

    @property
    def band_h(self) -> int:
        return self.line_pitch + self.band_above + self.band_below

    @property
    def crop(self) -> tuple[int, int, int, int]:
        """The grab: the tab strip and every band."""
        last = self.line_y0 + self.line_pitch * self.n_lines + self.band_below
        top = min(CROP[1], self.line_y0 - self.band_above)
        return (0, top, max(CROP[2], self.text_x1), max(CROP[3], last))


EN_RENDER = Render()


# --- pixels -> ink --------------------------------------------------------------------------------


def luma(rgb: np.ndarray) -> np.ndarray:
    a = np.asarray(rgb)[..., :3].astype(np.float32)
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


def band_rows(k: int, render: Render = EN_RENDER) -> tuple[int, int]:
    y0 = render.line_y0 + render.line_pitch * k
    return y0 - render.band_above, y0 + render.line_pitch + render.band_below


def chat_crop(frame_rgb: np.ndarray, render: Render = EN_RENDER) -> np.ndarray:
    """The crop of a full game-region RGB frame (a live grab is already this crop)."""
    x0, y0, x1, y1 = render.crop
    return np.asarray(frame_rgb)[y0:y1, x0:x1, :3]


def band_of(crop_rgb: np.ndarray, k: int, render: Render = EN_RENDER) -> np.ndarray:
    """Line k's RGB band (band_h x text width) out of a crop."""
    y0, y1 = band_rows(k, render)
    cx, cy = render.crop[0], render.crop[1]
    return np.asarray(crop_rgb)[y0 - cy : y1 - cy, render.text_x0 - cx : render.text_x1 - cx]


def ink_of(band_rgb: np.ndarray, colour: str | None = None, luma_min: float = LUMA_MIN
           ) -> np.ndarray:  # fmt: skip
    """Bright pixels that are not a SPRITE behind the translucent window: a Poring's highlights
    pass the luma bar at about (172, 142, 132) -- r - g +20..+40, b - g -20..0 -- while yellow
    text sits at r - g ~ +4, b - g ~ -113 and cyan at r - g ~ -90 (20261019T152849 frames
    370-383). With ``colour`` known, only pixels of that colour are kept (yellow: b - g < -45;
    cyan: r - g < -20; teal: r - g < 0)."""
    a = np.asarray(band_rgb)[..., :3].astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    m = luma(band_rgb) > luma_min
    pink = (r - g > 15) & (r - g < 70) & (b - g > -45)
    m &= ~pink
    if colour == "yellow":
        m &= b - g < -45
    elif colour == "cyan":
        m &= r - g < -20
    elif colour == "teal":  # broadcasts: r - g -55..-14 (10th..90th percentile)
        m &= r - g < 0
    return m


def runs(mask: np.ndarray, min_ink: int = MIN_INK, min_w: int = 1, join_gap: int = SPACE_COLS
         ) -> list[tuple[int, int]]:  # fmt: skip
    """(start, end) column runs of ink, specks (< min_ink pixels) dropped; a run narrower than
    min_w joins a neighbour closer than join_gap (a mark beside its base glyph; min_w 1 = never)."""
    cols = mask.any(0)
    out: list[tuple[int, int]] = []
    start = None
    for x, on in enumerate([*cols.tolist(), False]):
        if on and start is None:
            start = x
        elif not on and start is not None:
            if int(mask[:, start:x].sum()) >= min_ink:
                out.append((start, x))
            start = None
    if min_w > 1:
        joined: list[tuple[int, int]] = []
        for a, b in out:
            if joined and (b - a < min_w or joined[-1][1] - joined[-1][0] < min_w) \
                    and a - joined[-1][1] < join_gap:  # fmt: skip
                joined[-1] = (joined[-1][0], b)
            else:
                joined.append((a, b))
        out = joined
    return out


COLOURS = ("yellow", "cyan", "teal", "red", "green", "white")


def colour_of(band_rgb: np.ndarray, mask: np.ndarray) -> str:
    """The text colour class by the MAJORITY of the ink's pixels (a white cursor over a teal
    line shifted a mean colour to white: Batt's setup session, frames 845-879). JPEG blurs the
    chroma towards the darkened background, so the classes are coarse."""
    if int(mask.sum()) < 4:
        return "none"
    px = np.asarray(band_rgb)[mask][:, :3].astype(np.float32)
    r, g, b = px[:, 0], px[:, 1], px[:, 2]
    cls = np.full(len(px), len(COLOURS), np.int8)  # unclassified
    rules = [
        (r > 150) & (g > 150) & (b < 0.75 * np.minimum(r, g)),  # yellow
        (g > 150) & (b > 150) & (r < 0.7 * np.minimum(g, b)),  # cyan
        (g > 150) & (b > 120) & (r < 0.85 * g),  # teal
        (r > 150) & (g < 0.6 * r) & (b < 0.6 * r),  # red
        (g > 150) & (r < 0.75 * g) & (b < 0.75 * g),  # green
        np.minimum(np.minimum(r, g), b) > 150,  # white
    ]
    for k in range(len(rules) - 1, -1, -1):  # the earlier rule wins where several hold
        cls[rules[k]] = k
    counts = np.bincount(cls, minlength=len(COLOURS) + 1)[: len(COLOURS)]
    if int(counts.sum()) == 0:
        return "other"
    # a line has ONE colour; white pixels are mostly a cursor or a highlight on top of it: a
    # coloured class with >= 20 % of the classified ink wins over white
    coloured = counts[:-1]
    if int(coloured.max()) >= 0.2 * int(counts.sum()):
        return COLOURS[int(np.argmax(coloured))]
    return COLOURS[int(np.argmax(counts))]


# --- glyphs -------------------------------------------------------------------------------------


@dataclass
class Glyphs:
    """Glyph templates: chars[i] is the character of bitmaps[i] (LINE_PITCH x w, bool). '~' marks
    a non-Latin (Thai) glyph: it reads as '?' but no Latin template claims it."""

    chars: list[str]
    bitmaps: list[np.ndarray]
    by_width: dict[int, tuple[np.ndarray, list[int]]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        widths: dict[int, list[int]] = {}
        for i, b in enumerate(self.bitmaps):
            widths.setdefault(int(b.shape[1]), []).append(i)
        self.by_width = {w: (np.stack([self.bitmaps[i] for i in ix]), ix)
                         for w, ix in widths.items()}  # fmt: skip
        self.ink = [int(b.sum()) for b in self.bitmaps]


def load_glyphs(path: Path = GLYPHS) -> Glyphs:
    with np.load(path) as z:
        chars = [str(c) for c in z["chars"]]
        return Glyphs(chars, [z[f"g{i}"].astype(bool) for i in range(len(chars))])


def _dists(g: np.ndarray, gl: Glyphs) -> list[tuple[int, int]]:
    """[(distance, template index)] for every template of width w-1 .. w+1, the narrower one
    placed at its best column offset (a JPEG speck can widen a run by a column)."""
    w = g.shape[1]
    out: list[tuple[int, int]] = []
    for tw in (w - 1, w, w + 1):
        if tw not in gl.by_width:
            continue
        stack, ix = gl.by_width[tw]
        if tw == w:
            d = (stack != g[None]).sum((1, 2))
        elif tw < w:  # template narrower: try it at offset 0 and 1 (the extra column counts)
            d = np.minimum(
                (stack != g[None, :, :tw]).sum((1, 2)) + int(g[:, tw:].sum()),
                (stack != g[None, :, 1:]).sum((1, 2)) + int(g[:, :1].sum()),
            )
        else:  # template wider by one
            d = np.minimum(
                (stack[:, :, :w] != g[None]).sum((1, 2)) + stack[:, :, w:].sum((1, 2)),
                (stack[:, :, 1:] != g[None]).sum((1, 2)) + stack[:, :, :1].sum((1, 2)),
            )
        out += [(int(v), i) for v, i in zip(d.tolist(), ix, strict=True)]
    return sorted(out)


def match_glyph(g: np.ndarray, gl: Glyphs) -> tuple[str | None, int]:
    """(the character, its distance) of one run, or (None, best distance)."""
    ds = _dists(g, gl)
    if not ds:
        return None, 10**6
    d0, i0 = ds[0]
    c0 = gl.chars[i0]
    tol = max(MATCH_MIN, int(MATCH_FRAC * gl.ink[i0]))
    other = next((d for d, i in ds[1:] if gl.chars[i] != c0), None)
    if d0 <= tol and (other is None or other - d0 >= MATCH_MARGIN):
        return c0, d0
    return None, d0


def _trim(g: np.ndarray) -> np.ndarray | None:
    cols = np.nonzero(g.any(0))[0]
    if len(cols) == 0 or int(g.sum()) < MIN_INK:
        return None
    return g[:, cols[0] : cols[-1] + 1]


def read_run(g: np.ndarray, gl: Glyphs, depth: int = 2) -> list[str]:
    """One run's characters: a single glyph, else two (or three) touching ones split at a weak
    column (<= 1 ink pixel, or a column boundary), else ['?']."""
    ch, _ = match_glyph(g, gl)
    if ch is not None:
        return [ch]
    w = g.shape[1]
    if depth > 0 and w >= 4:
        best: tuple[int, list[str]] | None = None
        col_ink = g.sum(0)
        for c in range(2, w - 1):
            for left, right in ((g[:, :c], g[:, c:]), (g[:, :c], g[:, c + 1 :]))[
                    : 2 if col_ink[c] <= 1 else 1]:  # fmt: skip
                lt, rt = _trim(left), _trim(right)
                if lt is None or rt is None:
                    continue
                lc, ld = match_glyph(lt, gl)
                if lc is None:
                    continue
                rcs = read_run(rt, gl, depth - 1)
                if "?" in rcs:
                    continue
                cost = ld + (0 if len(rcs) > 1 else match_glyph(rt, gl)[1])
                if best is None or cost < best[0]:
                    best = (cost, [lc, *rcs])
        if best is not None:
            return best[1]
    return ["?"]


def decode(mask: np.ndarray, gl: Glyphs, render: Render = EN_RENDER
           ) -> tuple[str, list[tuple[int, int, str]]]:  # fmt: skip
    """A line's text ('?' per unreadable run, '~' runs read as '?', a space per gap of >=
    space_cols columns) and its runs [(x0, x1, chars)]."""
    rs = runs(mask, render.min_ink, render.min_glyph_w, render.space_cols)
    text: list[str] = []
    parts: list[tuple[int, int, str]] = []
    prev_end: int | None = None
    for a, b in rs:
        if prev_end is not None and a - prev_end >= render.space_cols:
            text.append(" ")
        chars = "".join("?" if c == "~" else c for c in read_run(mask[:, a:b], gl))
        text.append(chars)
        parts.append((a, b, chars))
        prev_end = b
    return "".join(text), parts


# --- lines --------------------------------------------------------------------------------------


@dataclass
class Line:
    text: str
    colour: str
    mask: np.ndarray  # the band's ink (band_h x text width)
    parts: list[tuple[int, int, str]]  # the glyph runs: (x0, x1, chars) in band columns
    x_base: int = TEXT_X0  # the band's first column (client px)

    @property
    def ink(self) -> int:
        return int(self.mask.sum())

    @property
    def x0(self) -> int:
        """The first ink column (client px)."""
        return self.x_base + (self.parts[0][0] if self.parts else 0)


def read_line(band_rgb: np.ndarray, gl: Glyphs,
              cache: dict[bytes, tuple[str, list[tuple[int, int, str]]]] | None = None,
              render: Render = EN_RENDER) -> Line | None:  # fmt: skip
    """One band's line (None = empty): the colour from the sprite-free ink, then the ink of that
    colour only, decoded. ``cache`` maps a mask's bytes to its decode."""
    m0 = ink_of(band_rgb, None, render.luma_min)
    if int(m0.sum()) < 4:
        return None
    colour = colour_of(band_rgb, m0)
    # a dimmer text colour (teal / cyan, ~180-190 luma) loses its JPEG-softened stroke edges
    # under LUMA_MIN: its bar follows the line's own brightness (frames 280-292: a broadcast
    # read as '?'s); the colour test keeps the background out
    bar = float(
        np.clip(LUMA_REL * float(np.median(luma(band_rgb)[m0])), LUMA_FLOOR, render.luma_min)
    )
    m = ink_of(band_rgb, colour, bar)
    if int(m.sum()) < 4:
        return None
    key = m.tobytes()
    if cache is not None and key in cache:
        text, parts = cache[key]
    else:
        text, parts = decode(m, gl, render)
        if cache is not None:
            if len(cache) > 20000:
                cache.clear()
            cache[key] = (text, parts)
    return Line(text, colour, m, parts, render.text_x0)


def read_lines(crop_rgb: np.ndarray, gl: Glyphs,
               cache: dict[bytes, tuple[str, list[tuple[int, int, str]]]] | None = None,
               render: Render = EN_RENDER) -> list[Line | None]:  # fmt: skip
    """The n_lines visible lines of a crop, top to bottom (None = an empty band)."""
    return [read_line(band_of(crop_rgb, k, render), gl, cache, render)
            for k in range(render.n_lines)]  # fmt: skip


COLOUR_GROUP = {"cyan": "blue", "teal": "blue"}
SAME_MIN_SHARE = 0.7  # of the shorter line's runs that must sit at the same columns
MAX_SOFT = 1  # letters (never digits) that may read differently in the same line
# two unread runs at the same columns are the same glyphs when at most this much ink of either
# lies more than a pixel from the other's ink (_far)
QMARK_TOL_MIN, QMARK_TOL_FRAC = 3, 0.15
# an unpaired read run this small (a period, a quote) is not a difference: the RDP progressive
# codec draws a new line coarse first, and its smallest glyphs come a frame later (frame 1048)
SMALL_INK = 4


def _dilate(m: np.ndarray) -> np.ndarray:
    """3 x 3 dilation of a bool mask."""
    p = np.pad(m, 1)
    out = np.zeros_like(m)
    h, w = m.shape
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            out |= p[dy : dy + h, dx : dx + w]
    return out


def _far(a: np.ndarray, b: np.ndarray) -> int:
    """Ink of either mask more than one pixel from the other's ink: a JPEG-softened edge moves
    a stroke by a pixel, a different glyph puts ink where the other has none."""
    return int((a & ~_dilate(b)).sum() + (b & ~_dilate(a)).sum())


def _groups(a: Sequence[tuple[int, int, str]], b: Sequence[tuple[int, int, str]]
            ) -> list[tuple[list[int], list[int]]]:  # fmt: skip
    """The runs of two lines grouped by column overlap (transitively): [(a indices, b
    indices)], left to right."""
    ev = sorted([(x0, x1, 0, i) for i, (x0, x1, _) in enumerate(a)]
                + [(x0, x1, 1, i) for i, (x0, x1, _) in enumerate(b)])  # fmt: skip
    out: list[tuple[list[int], list[int]]] = []
    end = -1
    for x0, x1, side, i in ev:
        if not out or x0 >= end:
            out.append(([], []))
        out[-1][side].append(i)
        end = max(end, x1) if x0 < end else x1
    return out


def same_line(a: Line | None, b: Line | None) -> bool:
    """The same line (symmetric): the same colour group, and their glyph runs ALIGNED -- a line
    is drawn at fixed columns, so the same text puts its runs at the same columns (+-1). The
    runs of both lines are grouped by column overlap; in each group:
    - one run a side: read characters must be equal; a read and an unread run pass (a speck or a
      sprite can spoil one glyph in one frame); two unread runs (a Thai name) must agree within
      QMARK_TOL over the columns both cover, edge pixels forgiven (_far);
    - a split / merge (more runs on one side): passes when any run in it is unread, else the
      characters must be equal;
    - runs on one side only: an unread one is ignored (a sprite's highlights beside the text),
      so is a read one of <= SMALL_INK pixels (a period or a quote drawn a frame late); a larger
      read one is real text the other line lacks: a difference.
    At least SAME_MIN_SHARE of the shorter line's runs must sit in two-sided groups. Up to
    MAX_SOFT glyphs may differ -- a LETTER read as another (a damaged 'r' reads as 'i':
    20261019T152849 frame 3208) or two unread runs out of tolerance (a spoiled Thai glyph); a
    differing DIGIT never passes, and different words / names differ in many glyphs."""
    if a is None or b is None:
        return a is b
    if COLOUR_GROUP.get(a.colour, a.colour) != COLOUR_GROUP.get(b.colour, b.colour):
        return False
    if a.text == b.text and "?" not in a.text:
        return True
    paired = soft = 0
    for ia, ib in _groups(a.parts, b.parts):
        ra, rb = [a.parts[i] for i in ia], [b.parts[i] for i in ib]
        if not ra or not rb:
            line, runs_ = (a, ra) if ra else (b, rb)
            for x0, x1, c in runs_:
                if "?" not in c and int(line.mask[:, x0:x1].sum()) > SMALL_INK:
                    return False
            continue
        paired += min(len(ra), len(rb))
        ca, cb = "".join(r[2] for r in ra), "".join(r[2] for r in rb)
        if len(ra) == 1 and len(rb) == 1 and "?" in ca and "?" in cb:
            # over the columns BOTH runs cover: a run that grew into its neighbour (a Thai
            # glyph merged with the '(' after it by a speck) is compared on its own glyph (v43
            # run 2 frames 12191 / 17864: two fake [base, job, item] triples)
            u0, u1 = max(ra[0][0], rb[0][0]), min(ra[0][1], rb[0][1])
            ga, gb = a.mask[:, u0:u1], b.mask[:, u0:u1]
            tol = max(QMARK_TOL_MIN, int(QMARK_TOL_FRAC * max(int(ga.sum()), int(gb.sum()))))
            if _far(ga, gb) > tol:
                soft += 1  # one spoiled glyph, as for letters (frame 12191: 4 px off of 24)
                if soft > MAX_SOFT:
                    return False
        elif "?" not in ca and "?" not in cb and ca != cb:
            if any(ch.isdigit() for ch in ca + cb):
                return False  # a number differs: never the same line
            soft += 1  # a letter read as another (an 'r' that lost its hook reads 'i')
            if soft > MAX_SOFT:
                return False
    shorter = min(len(a.parts), len(b.parts))
    return shorter == 0 or paired >= SAME_MIN_SHARE * shorter


def new_lines(prev: Sequence[Line | None], cur: Sequence[Line | None]
              ) -> tuple[list[int], int, bool]:  # fmt: skip
    """PURE: (indices of the NEW lines in ``cur``, the shift, ambiguous). Lines are compared as
    lists of the non-empty ones, top to bottom (the window fills either way): the smallest shift
    s with cur[:m] == prev[s:] (m = len(prev) - s) wins; s = len(prev) (no overlap: every line is
    new) always fits; ambiguous = another shift WITH overlap fitted as well."""
    p = [x for x in prev if x is not None]
    c_idx = [i for i, x in enumerate(cur) if x is not None]
    c = [cur[i] for i in c_idx]
    fits = []
    for s in range(len(p) + 1):
        m = len(p) - s
        if m > len(c):
            continue
        if all(same_line(c[i], p[s + i]) for i in range(m)):
            fits.append((s, m))
    s, m = fits[0]
    return c_idx[m:], s, sum(1 for _, mm in fits if mm > 0) > 1


def clean(ln: Line, lang: Lang | None = None) -> bool:
    """A line read in full: a typed line with its number, or another line with no unread glyph
    (an item line's name is never read: its count must be)."""
    k = classify(ln.text, ln.colour, lang)
    if k["type"] == "damage":
        return k.get("n") is not None and "?" not in str(k.get("name_read", "?"))
    if k["type"] in ("base_exp", "job_exp"):
        return k.get("n") is not None
    if k["type"] == "item":
        return k.get("count") is not None
    return "?" not in ln.text


# --- events and per-language line formats ------------------------------------------------------
#
# The EVENT model is fixed: damage {n, name}, base_exp {n}, job_exp {n}, item {count} (the item's
# name is never read), other. HOW a client language writes each event is DATA, one file per
# language: data/ui_anchors/battle_log/<lang>/formats.json (gitignored: client text is never
# committed; `formats-init en` writes the English one). Its schema:
#
#   {"lang": "en",
#    "render": {Render's fields; any left out keep the English lab client's values},
#    "species": ["Poring", ...],            the bracketed names this client shows (optional)
#    "events": {"<type>": {"colour": "yellow", "pattern": [ELEMENT, ...]}, ...}}
#
# A pattern is the line from its start to its end, in order (whitespace between elements is
# free; a period or unread specks may follow the last one, anything may follow once only
# optional words are left -- as the validated English reader never checked them). Each ELEMENT:
#   {"lit": "<word>"}                       a fixed word, matched FUZZILY (SequenceMatcher ratio
#                                           >= LIKE_MIN with spaces ignored: one spoiled glyph
#                                           passes); {"lit": ..., "opt": true} may be missing
#   {"name": "name", "anchor": "bracket"}   [NAME] -> name_read, name (the species it fits)
#   {"num": "<field>", "anchor": "quoted"}  'N'   (the leading quote may be lost)
#   {"num": "<field>", "anchor": "paren"}   (N)
#   {"num": "<field>", "anchor": "bare"}    N
#   {"item": "item"}                        an item name: any text, never read
# The quoted numbers and the bracketed name are the stable ANCHORS across languages; the fixed
# words are what differs. A line is the event whose pattern fits with the best mean word ratio
# (one word per "lit" keeps "Base" and "Job" apart). "colour" is checked only with
# render.colour_check (the English path does not: as validated).

ANCHOR_RX = {
    ("name", "bracket"): re.compile(r"\s*\[\s*(?P<v>[^\]]*?)\s*\]"),
    ("num", "quoted"): re.compile(r"\s*'?\s*(?P<v>[0-9?]+)\s*'"),
    ("num", "paren"): re.compile(r"\s*\(\s*(?P<v>[0-9?]+)\s*\)"),
    ("num", "bare"): re.compile(r"\s*(?P<v>[0-9?]+)(?![0-9?])"),
}
TAIL_RX = re.compile(r"[\s.?]*")  # what may follow the last element
WORD_END = " '[(."  # a fixed word may end before one of these, or at the line's end
WORD_STRETCH = 1.4  # a fixed word's text may read up to 1.4 x + 1.5 its length (split glyphs)


@dataclass(frozen=True)
class Elem:
    kind: str  # lit / name / num / item
    text: str = ""  # lit: the word
    field: str = ""  # name / num / item: the record field
    anchor: str = ""  # name: bracket; num: quoted / paren / bare
    opt: bool = False


def parse_pattern(pattern: Sequence[Mapping[str, Any]]) -> tuple[Elem, ...]:
    out = []
    for e in pattern:
        if "lit" in e:
            out.append(Elem("lit", text=str(e["lit"]), opt=bool(e.get("opt"))))
        elif "name" in e:
            out.append(Elem("name", field=str(e["name"]), anchor=str(e.get("anchor", "bracket"))))
        elif "num" in e:
            out.append(Elem("num", field=str(e["num"]), anchor=str(e.get("anchor", "quoted"))))
        elif "item" in e:
            out.append(Elem("item", field=str(e["item"])))
        else:
            raise ValueError(f"unknown pattern element {e!r}")
        if out[-1].kind in ("name", "num") and (out[-1].kind, out[-1].anchor) not in ANCHOR_RX:
            raise ValueError(f"unknown anchor {e!r}")
    return tuple(out)


@dataclass
class Lang:
    """A client language: its line formats and rendering, and its glyph / name templates."""

    code: str
    events: dict[str, tuple[Elem, ...]]
    colours: dict[str, str] = field(default_factory=dict)
    render: Render = EN_RENDER
    species: tuple[str, ...] = SPECIES
    glyphs: Glyphs | None = None
    names: dict[str, np.ndarray] | None = None
    _cache: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict, repr=False)


def lang_from_formats(fm: Mapping[str, Any], glyphs: Glyphs | None = None,
                      names: dict[str, np.ndarray] | None = None) -> Lang:  # fmt: skip
    """PURE: a Lang from a formats.json document."""
    ev = fm.get("events") or {}
    unknown = set(ev) - set(TYPES)
    if unknown:
        raise ValueError(f"unknown event types {sorted(unknown)}")
    render = Render(**{k: v for k, v in (fm.get("render") or {}).items()
                       if k in Render.__dataclass_fields__})  # fmt: skip
    return Lang(code=str(fm.get("lang", "?")),
                events={t: parse_pattern(e["pattern"]) for t, e in ev.items()},
                colours={t: str(e["colour"]) for t, e in ev.items() if e.get("colour")},
                render=render, species=tuple(fm.get("species") or SPECIES), glyphs=glyphs,
                names=names)  # fmt: skip


def _num(s: str | None) -> int | None:
    return int(s) if s is not None and s.isdigit() else None


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.replace(" ", ""), b.replace(" ", "")).ratio()


def _like(token: str, word: str, min_ratio: float = LIKE_MIN) -> bool:
    """A decoded token reads as ``word``: SequenceMatcher ratio >= min_ratio (a '?' or a split
    glyph costs a little; 'acquii ed' still reads as acquired)."""
    return _ratio(token, word) >= min_ratio


def match_pattern(text: str, elems: Sequence[Elem]) -> tuple[float, dict[str, str]] | None:
    """PURE: (mean fixed-word ratio, the anchors' raw values) of the best way ``elems`` spell the
    whole of ``text``, or None. Fixed words end at a word end (WORD_END) and are fuzzy; anchors
    are exact apart from an optional leading quote."""
    best: list[Any] = [None]

    def keep(vals: dict[str, str], ratios: list[float]) -> None:
        score = sum(ratios) / len(ratios)
        if best[0] is None or score > best[0][0]:
            best[0] = (score, dict(vals))

    def rec(k: int, i: int, vals: dict[str, str], ratios: list[float]) -> None:
        if k == len(elems):
            if ratios and TAIL_RX.fullmatch(text, i):  # a period or unread specks may follow
                keep(vals, ratios)
            return
        if ratios and all(e.opt for e in elems[k:]):
            keep(vals, ratios)  # only optional words left: anything may follow, unchecked
        e = elems[k]
        if e.opt:
            rec(k + 1, i, vals, ratios)
        if e.kind in ("name", "num"):
            m = ANCHOR_RX[(e.kind, e.anchor)].match(text, i)
            if m:
                rec(k + 1, m.end(), {**vals, e.field: m["v"]}, ratios)
            return
        if e.kind == "item":
            for j in range(i, len(text) + 1):
                rec(k + 1, j, vals, ratios)
            return
        want = len(e.text.replace(" ", ""))
        for j in range(i + 1, len(text) + 1):
            if j < len(text) and text[j] not in WORD_END:
                continue
            seg = text[i:j].strip()
            n = len(seg.replace(" ", ""))
            if n == 0 or n * 2 < want:
                continue
            if n > WORD_STRETCH * want + 1.5:  # a word plus the next ("Job EXP" is not "EXP")
                break
            r = _ratio(seg, e.text)
            if r >= LIKE_MIN:
                rec(k + 1, j, vals, [*ratios, r])

    rec(0, 0, {}, [])
    return best[0]


def species_of(name: str, vocab: Sequence[str] = SPECIES) -> str | None:
    """The species a bracketed name reads as: exact, else the ONE vocabulary name that the read
    letters fit, each '?' standing for 1-2 letters (an unknown glyph, or two touching ones read
    as one run: "Crea?" fits Creamy); None otherwise."""
    if "?" not in name:
        return name if name in vocab else None
    rx = re.compile("".join(".{1,2}" if ch == "?" else re.escape(ch) for ch in name))
    fit = [v for v in vocab if rx.fullmatch(v)]
    return fit[0] if len(fit) == 1 and sum(ch != "?" for ch in name) >= 2 else None


def classify(text: str, colour: str = "", lang: Lang | None = None) -> dict[str, Any]:
    """{"type", fields} of one decoded line in ``lang`` (default: this host's language, see
    default_lang): the event whose pattern fits best (match_pattern), else other. Fields: n /
    count (None when a digit is unread), and for a damage line name_read and name (the
    species). Cached per language."""
    lang = lang or default_lang()
    key = (text, colour if lang.render.colour_check else "")
    hit = lang._cache.get(key)
    if hit is not None:
        return dict(hit)
    t = text.strip()
    best: tuple[float, str, dict[str, str]] | None = None
    for typ, elems in lang.events.items():
        want = lang.colours.get(typ)
        if lang.render.colour_check and want and colour not in ("", "none") and \
                COLOUR_GROUP.get(want, want) != COLOUR_GROUP.get(colour, colour):  # fmt: skip
            continue
        m = match_pattern(t, elems)
        if m and (best is None or m[0] > best[0]):
            best = (m[0], typ, m[1])
    out: dict[str, Any] = {"type": "other"}
    if best is not None:
        _, typ, vals = best
        out = {"type": typ}
        for e in lang.events[typ]:
            if e.kind == "num":
                out[e.field] = _num(vals.get(e.field))
            elif e.kind == "name":
                raw = vals.get(e.field, "").strip()
                out["name_read"] = raw
                out[e.field] = species_of(raw, lang.species)
    if len(lang._cache) > 50000:
        lang._cache.clear()
    lang._cache[key] = out
    return dict(out)


# --- the language files ---------------------------------------------------------------------


def lang_dir(code: str) -> Path:
    return ANCHORS / code


def _first(*paths: Path) -> Path | None:
    return next((x for x in paths if x.exists()), None)


def load_lang(code: str | None = None, glyphs: Glyphs | None = None) -> Lang:
    """A language from data/ui_anchors/battle_log/<code>/ (formats.json, glyphs.npz,
    names.npz); ``code`` None = this host's default (lang.json, else "en"). English falls back
    to the pre-language files beside the folder (glyphs.npz / names.npz) when en/ lacks them."""
    code = code or default_code()
    d = lang_dir(code)
    fpath = d / "formats.json"
    if not fpath.exists():
        hint = " (battle_log.py formats-init en)" if code == "en" else ""
        raise SystemExit(f"no line formats for language {code!r}: {fpath}{hint}")
    legacy = code == "en"
    gpath = _first(d / "glyphs.npz", *([GLYPHS] if legacy else []))
    npath = _first(d / "names.npz", *([NAMES] if legacy else []))
    return lang_from_formats(json.loads(fpath.read_text()),
                             glyphs if glyphs is not None else
                             (load_glyphs(gpath) if gpath else None),
                             load_names(npath) if npath else None)  # fmt: skip


def default_code() -> str:
    try:
        return str(json.loads(LANG_FILE.read_text()).get("lang") or "en")
    except (OSError, ValueError):
        return "en"


_DEFAULT: dict[str, Lang] = {}


def default_lang() -> Lang:
    code = default_code()
    if code not in _DEFAULT:
        _DEFAULT[code] = load_lang(code)
    return _DEFAULT[code]


def languages() -> list[str]:
    """The languages with a formats.json on this host."""
    return sorted(p.parent.name for p in ANCHORS.glob("*/formats.json"))


def en_formats() -> dict[str, Any]:
    """The English lab client's formats (the words built at run time, never one client
    string)."""
    w = {"rec": "receives", "dmg": "damage", "pts": "points", "base": "Base", "job": "Job",
         "exp": "Experience", "acq": "acquired", "you": "You", "got": "got"}  # fmt: skip

    def lit(k: str, opt: bool = False) -> dict[str, Any]:
        return {"lit": w[k], "opt": True} if opt else {"lit": w[k]}

    def exp(kind: str) -> dict[str, Any]:
        return {"colour": "yellow", "pattern": [{"num": "n", "anchor": "quoted"}, lit(kind),
                                                lit("exp"), lit("acq", opt=True)]}  # fmt: skip

    return {"lang": "en", "render": dataclasses.asdict(EN_RENDER), "species": list(SPECIES),
            "events": {
                "damage": {"colour": "yellow", "pattern": [
                    {"name": "name", "anchor": "bracket"}, lit("rec"),
                    {"num": "n", "anchor": "quoted"}, lit("dmg"), lit("pts", opt=True)]},
                "base_exp": exp("base"), "job_exp": exp("job"),
                "item": {"colour": "cyan", "pattern": [
                    lit("you"), lit("got"), {"item": "item"},
                    {"num": "count", "anchor": "paren"}]}}}  # fmt: skip


def formats_init(code: str, force: bool = False) -> dict[str, Any]:
    """Write a language's formats.json (only English is generated; another language's file is
    written by a person from the client's own lines -- see the schema above)."""
    if code != "en":
        raise SystemExit(f"only 'en' is generated; write {lang_dir(code)}/formats.json by hand")
    out = lang_dir(code) / "formats.json"
    if out.exists() and not force:
        raise SystemExit(f"{out} exists (--force to overwrite)")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(en_formats(), indent=1, ensure_ascii=False) + "\n")
    return {"out": str(out)}


def detect_lang(imgs: Iterable[np.ndarray], langs: Sequence[Lang],
                box: Sequence[int] | None = None) -> tuple[str, dict[str, Any]]:  # fmt: skip
    """--lang auto: the language whose formats type the most of the first lines seen (each read
    with that language's own glyphs and rendering, from ``imgs`` grabbed at ``box``; None = the
    images are already every language's crop), the mean word ratio breaking ties; the first
    language when none types a line. Not used live yet."""
    imgs = list(imgs)
    score: dict[str, tuple[int, float]] = {}
    for lg in langs:
        if lg.glyphs is None:
            continue
        typed, ratio_sum = 0, 0.0
        for img in imgs:
            c = img if box is None else sub_crop(img, box, lg.render.crop)
            for ln in read_lines(c, lg.glyphs, None, lg.render):
                if ln is None:
                    continue
                k = classify(ln.text, ln.colour, lg)
                if k["type"] != "other":
                    typed += 1
                    ratio_sum += max((m[0] for e in lg.events.values()
                                      if (m := match_pattern(ln.text.strip(), e))),
                                     default=0.0)  # fmt: skip
        score[lg.code] = (typed, ratio_sum)
    if not score:
        return langs[0].code, {}
    code = max(score, key=lambda c: score[c])
    return code, {c: {"typed": v[0], "ratio": round(v[1], 2)} for c, v in score.items()}


# --- the stream reader -------------------------------------------------------------------------


def tab_is_battle(crop_rgb: np.ndarray, render: Render = EN_RENDER) -> bool | None:
    """The Battle Log tab is the selected one: the chat window's top border (row TAB_EDGE_Y, an
    opaque light line) is drawn under the UNSELECTED tab only. True / False, or None when the
    border reads neither way (a sprite or the cursor on it). Both tabs are translucent, so
    their fill tracks the scene behind them (dark grass: a template distance of 50 against the
    Battle Log template and 86 against Regular Chat); the border does not."""
    cx, cy = render.crop[0], render.crop[1]
    row = luma(np.asarray(crop_rgb)[TAB_EDGE_Y - cy : TAB_EDGE_Y - cy + 1, :, :3])[0]
    edge = row > TAB_EDGE_LUMA
    fb = float(edge[BATTLE_SPAN[0] - cx : BATTLE_SPAN[1] - cx].mean())
    fr = float(edge[REGULAR_SPAN[0] - cx : REGULAR_SPAN[1] - cx].mean())
    if fr >= 0.8 and fb <= 0.3:
        return True
    if fb >= 0.8 and fr <= 0.3:
        return False
    return None


class Reader:
    """Feed frames in time order; get the records of the lines that are new in each.

    - A frame showing another tab is skipped (the lines are compared again with the last Battle
      Log frame when it is back).
    - A frame whose lines do not overlap the last ones (every line new) is HELD for one frame
      when a new line is not read in full or sits at its slot unchanged (the signature of a
      misread, not of a scroll): the next frame confirms it (it overlaps the held one: its lines
      count from the held frame's time) or rejects it (``garbage``). A clean jump -- a kill's
      damage + EXP lines in one frame interval -- counts at once.
    - A new line not read in full is REFINED while it stays visible: the first clean read of the
      same line (up to REFINE_FRAMES frames) fills its fields. A record is returned once it is
      clean, refined out of time, or scrolled away -- always with ``t_ns`` = the frame it first
      showed in (``t_emit_ns`` = when it was returned)."""

    def __init__(self, gl: Glyphs | Lang, names: Mapping[str, np.ndarray] | None = None,
                 trace: list[dict[str, Any]] | None = None) -> None:  # fmt: skip
        """``gl``: a Lang (its glyphs, names, formats and rendering), or -- as before languages
        -- a Glyphs set read with this host's default language's formats."""
        if isinstance(gl, Lang):
            self.lang = gl
        else:
            base = default_lang()
            self.lang = dataclasses.replace(base, glyphs=gl, names=names, _cache={})
        if self.lang.glyphs is None:
            raise SystemExit(f"no glyph templates for language {self.lang.code!r}")
        self.gl, self.names, self.trace = self.lang.glyphs, self.lang.names, trace
        self.render = self.lang.render
        self.prev: list[Line | None] | None = None
        self.vis: list[dict[str, Any] | None] = []  # the records of prev's non-empty lines
        self.pending: tuple[int, Any, list[Line | None]] | None = None
        self.cache: dict[bytes, tuple[str, list[tuple[int, int, str]]]] = {}
        self.stats: dict[str, int] = {"frames": 0, "other_tab": 0, "tab_unknown": 0, "held": 0,
                                      "garbage": 0, "ambiguous": 0, "overflow": 0,
                                      "refined": 0}  # fmt: skip

    def feed(self, t_ns: int, crop_rgb: np.ndarray, frame: Any = None) -> list[dict[str, Any]]:
        before = dict(self.stats)
        out = self._feed(t_ns, crop_rgb, frame)
        if self.trace is not None:  # one row per frame: what the reader made of it
            self.trace.append({"t": int(t_ns), "frame": frame, "out": len(out),
                               **{k: v - before.get(k, 0) for k, v in self.stats.items()
                                  if v != before.get(k, 0) and k != "frames"}})  # fmt: skip
        return out

    def _feed(self, t_ns: int, crop_rgb: np.ndarray, frame: Any) -> list[dict[str, Any]]:
        self.stats["frames"] += 1
        tab = tab_is_battle(crop_rgb, self.render)
        if tab is False:
            self.stats["other_tab"] += 1
            return []
        self.stats["tab_unknown"] += int(tab is None)
        cur = read_lines(crop_rgb, self.gl, self.cache, self.render)
        if self.prev is None:  # the first frame: what is visible is history, not new
            self.prev = cur
            self.vis = [None] * _count(cur)
            return []
        out: list[dict[str, Any]] = []
        if self.pending is not None:
            pt, pf, pcur = self.pending
            self.pending = None
            _, s2, _ = new_lines(pcur, cur)
            if s2 < _count(pcur):  # this frame overlaps the held one: it was real
                out += self._commit(pt, pf, pcur, *new_lines(self.prev, pcur), t_now=int(t_ns))
            else:
                self.stats["garbage"] += 1
        idx, shift, ambiguous = new_lines(self.prev, cur)
        n_prev = _count(self.prev)
        if idx and n_prev and shift >= n_prev and self._suspicious(cur, idx):
            self.stats["held"] += 1
            self.pending = (int(t_ns), frame, cur)
            return out
        out += self._commit(int(t_ns), frame, cur, idx, shift, ambiguous, t_now=int(t_ns))
        if idx:
            self.stats[f"shift{shift}"] = self.stats.get(f"shift{shift}", 0) + 1
        return out

    def flush(self) -> list[dict[str, Any]]:
        """The records still waiting for a clean read (at the end of a replay)."""
        out = [r for r in self.vis if r is not None and not r["_out"]]
        for r in out:
            r["_out"] = True
        return [_public(r) for r in out]

    def _suspicious(self, cur: Sequence[Line | None], idx: Sequence[int]) -> bool:
        assert self.prev is not None
        for i in idx:
            ln = cur[i]
            assert ln is not None
            if not clean(ln, self.lang):
                return True
            if i < len(self.prev) and same_line(ln, self.prev[i]):
                return True
        return False

    def _record(self, t_ns: int, frame: Any, slot: int, ln: Line, shift: int, ambiguous: bool,
                overflow: bool) -> dict[str, Any]:  # fmt: skip
        rec: dict[str, Any] = {"t_ns": t_ns, "frame": frame, "slot": slot, "shift": shift}
        self._fill(rec, ln)
        if ambiguous:
            rec["ambiguous"] = True
        if overflow:
            rec["overflow"] = True
        rec["_age"], rec["_out"] = 0, False
        return rec

    def _fill(self, rec: dict[str, Any], ln: Line) -> None:
        for k in ("n", "name", "name_read", "name_by", "count"):
            rec.pop(k, None)
        rec.update(classify(ln.text, ln.colour, self.lang))
        rec.update(colour=ln.colour, text=ln.text, x0=ln.x0, clean=clean(ln, self.lang))
        if rec["type"] == "damage" and rec.get("name") is None and self.names:
            rec["name"] = name_by_template(ln, self.names)
            rec["name_by"] = "template"

    def _commit(self, t_ns: int, frame: Any, cur: list[Line | None], idx: Sequence[int],
                shift: int, ambiguous: bool, t_now: int) -> list[dict[str, Any]]:  # fmt: skip
        n_vis = _count(cur)
        overflow = bool(idx) and len(idx) == n_vis and n_vis == self.render.n_lines
        self.stats["ambiguous"] += int(ambiguous)  # frames where a hidden scroll could hide
        self.stats["overflow"] += int(overflow)
        gone, kept = self.vis[:shift], self.vis[shift:]
        lines = [x for x in cur if x is not None]
        for rec, ln in zip(kept, lines, strict=False):  # the lines still visible: refine
            if rec is not None and not rec["_out"] and not rec["clean"] and clean(ln, self.lang):
                self._fill(rec, ln)
                rec["refined"] = True
                self.stats["refined"] += 1
        new = []
        for i in idx:
            ln = cur[i]
            assert ln is not None
            new.append(self._record(t_ns, frame, i, ln, shift, ambiguous, overflow))
        self.vis = [*kept, *new]
        # the reference for the next frame: per line still visible, the CLEANER of its two reads
        # (fewer unread runs) -- a noisy frame is then compared with a clean read, not with the
        # last noisy one (frames 5563-5583: a Thai name and a ')' that vary frame to frame)
        old = [x for x in (self.prev or []) if x is not None]
        merged = list(cur)
        c_idx = [i for i, x in enumerate(cur) if x is not None]
        for k, i in enumerate(c_idx[: max(0, len(old) - shift)]):
            o, c = old[shift + k], cur[i]
            if c is not None and o.text.count("?") < c.text.count("?"):
                merged[i] = o
        self.prev = merged
        out = [r for r in gone if r is not None and not r["_out"]]  # scrolled away unread
        for r in self.vis:
            if r is None or r["_out"]:
                continue
            r["_age"] += 1
            if r["clean"] or r["_age"] > REFINE_FRAMES:
                out.append(r)
        for r in out:
            r["_out"] = True
            r["t_emit_ns"] = t_now
        return [_public(r) for r in out]


def _public(rec: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in rec.items() if not k.startswith("_")}


def _count(lines: Sequence[Line | None]) -> int:
    return sum(1 for x in lines if x is not None)


# --- species name templates (fallback when a letter is unknown) -----------------------------------


def bracket_word(ln: Line) -> np.ndarray | None:
    """The ink between a damage line's first run ('[') and the run that closes the name (the
    last run before the first space)."""
    rs = runs(ln.mask)
    if len(rs) < 3:
        return None
    end = next((k for k in range(1, len(rs)) if rs[k][0] - rs[k - 1][1] >= SPACE_COLS), None)
    if end is None or end < 3:
        return None
    return _trim(ln.mask[:, rs[1][0] : rs[end - 2][1]])


def name_by_template(ln: Line, names: Mapping[str, np.ndarray]) -> str | None:
    g = bracket_word(ln)
    if g is None:
        return None
    best: list[tuple[int, str]] = []
    for name, t in names.items():
        if abs(t.shape[1] - g.shape[1]) > 1:
            continue
        w = max(t.shape[1], g.shape[1])
        a = np.zeros((LINE_PITCH, w), bool)
        b = np.zeros((LINE_PITCH, w), bool)
        a[:, : g.shape[1]] = g
        b[:, : t.shape[1]] = t
        best.append((int((a != b).sum()), name))
    best.sort()
    if best and best[0][0] <= max(4, int(0.1 * int(g.sum()))) and (
            len(best) < 2 or best[1][0] - best[0][0] >= 4):  # fmt: skip
        return best[0][1]
    return None


def load_names(path: Path = NAMES) -> dict[str, np.ndarray] | None:
    try:
        with np.load(path) as z:
            return {k: z[k].astype(bool) for k in z.files}
    except OSError:
        return None


# --- frames -----------------------------------------------------------------------------------


def frame_files(frames_dir: Path) -> list[tuple[int, int, Path]]:
    """[(index, t_mono_ns, path)] of a recording's `<index>-<t_mono_ns>.jpg` files, in order."""
    out = []
    for name in os.listdir(frames_dir):
        stem, ext = os.path.splitext(name)
        if ext != ".jpg" or "-" not in stem:
            continue
        i, t = stem.split("-", 1)
        if i.isdigit() and t.isdigit():
            out.append((int(i), int(t), frames_dir / name))
    return sorted(out)


def read_crop(path: Path, render: Render = EN_RENDER) -> np.ndarray:
    from PIL import Image

    with Image.open(path) as im:  # crop first: no full-frame copy
        return np.asarray(im.crop(render.crop).convert("RGB"))


def sub_crop(img: np.ndarray, box: Sequence[int], inner: Sequence[int]) -> np.ndarray:
    """PURE: the part of an image grabbed at ``box`` (x0, y0, x1, y1) that covers ``inner``."""
    return np.asarray(img)[inner[1] - box[1] : inner[3] - box[1], inner[0] - box[0] :
                           inner[2] - box[0]]  # fmt: skip


def union_box(langs: Sequence[Lang]) -> tuple[int, int, int, int]:
    bs = [lg.render.crop for lg in langs]
    return (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs),
            max(b[3] for b in bs))  # fmt: skip


def pick_lang(spec: str | None, sample: Callable[[tuple[int, int, int, int]], list[np.ndarray]]
              ) -> tuple[Lang, dict[str, Any]]:  # fmt: skip
    """The language to read with: ``spec`` a code, None (this host's default: lang.json, else
    "en") or "auto" -- every language on this host with glyphs, scored by detect_lang on the
    images ``sample(box)`` returns for their union box."""
    if spec != "auto":
        return load_lang(spec), {}
    langs = [lg for lg in (load_lang(c) for c in languages()) if lg.glyphs is not None]
    if not langs:
        raise SystemExit("--lang auto: no language with glyph templates on this host")
    box = union_box(langs)
    imgs = sample(box)
    code, score = detect_lang(imgs, langs, box)
    return next(lg for lg in langs if lg.code == code), {"auto": score, "picked": code}


def replay(sid: str, frames_dir: Path | None = None, out: Path | None = None,
           gl: Glyphs | None = None, lang: str | None = None) -> dict[str, Any]:  # fmt: skip
    frames_dir = frames_dir or RECORDINGS / sid / "frames"
    out = out or DEMO / sid / "battle_log.jsonl"
    files = frame_files(frames_dir)

    def sample(box: tuple[int, int, int, int]) -> list[np.ndarray]:
        from PIL import Image

        out_: list[np.ndarray] = []
        for _, _, p in files[: AUTO_FRAMES * 5 : 5]:
            with Image.open(p) as im:
                out_.append(np.asarray(im.crop(box).convert("RGB")))
        return out_

    lg, auto = pick_lang(lang, sample)
    if gl is not None:
        lg = dataclasses.replace(lg, glyphs=gl, _cache={})
    trace: list[dict[str, Any]] = []
    reader = Reader(lg, trace=trace)
    counts: dict[str, int] = {}
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as fh:
        for i, t, p in files:
            for rec in reader.feed(t, read_crop(p, lg.render), frame=i):
                counts[rec["type"]] = counts.get(rec["type"], 0) + 1
                fh.write(json.dumps(rec) + "\n")
        for rec in reader.flush():
            counts[rec["type"]] = counts.get(rec["type"], 0) + 1
            fh.write(json.dumps(rec) + "\n")
    with out.with_name(out.stem + "_frames.jsonl").open("w") as fh:
        fh.writelines(json.dumps(x) + "\n" for x in trace)
    return {"sid": sid, "lang": lg.code, **auto, "out": str(out), "frames": len(files),
            "lines": counts, **reader.stats}  # fmt: skip


def live(out: Path, hz: float = 5.0, until_pid: int | None = None,
         grab: Callable[[tuple[int, int, int, int]], tuple[int, np.ndarray]] | None = None,
         max_frames: int | None = None, lang: str | None = None) -> dict[str, Any]:  # fmt: skip
    """Read the LIVE frames (read-only) at ``hz`` and append the new lines' records to ``out``
    until SIGINT / SIGTERM, the exit of ``until_pid``, or ``max_frames``. ``grab(box)`` (a test
    seam) returns (t_mono_ns, that box of the game region as RGB); by default ro_agent.Screen's
    grab. ``lang`` "auto" first grabs AUTO_FRAMES / 5 frames of every language's box to pick
    one (documented, not used live yet)."""
    stop = {"v": False}

    def _stop(*_: Any) -> None:
        stop["v"] = True

    old_int = signal.signal(signal.SIGINT, _stop)
    old_term = signal.signal(signal.SIGTERM, _stop)
    screen = None
    if grab is None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import ro_agent as r

        screen = r.Screen()
        gx, gy, _, _ = r.game_region()

        def grab(box: tuple[int, int, int, int]) -> tuple[int, np.ndarray]:
            assert screen is not None
            x0, y0, x1, y1 = box
            t, img = screen.grab(gx + x0, gy + y0, x1 - x0, y1 - y0)
            return int(t), np.asarray(img)[..., :3][..., ::-1]  # BGRA -> RGB

    period = 1.0 / hz

    def sample(box: tuple[int, int, int, int]) -> list[np.ndarray]:
        imgs = []
        for _ in range(AUTO_FRAMES // 5):
            imgs.append(grab(box)[1])
            time.sleep(period)
        return imgs

    try:
        lg, auto = pick_lang(lang, sample)
        reader = Reader(lg)
        n = 0
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("a") as fh:
            nxt = time.monotonic()
            while not stop["v"]:
                if until_pid is not None and not _alive(until_pid):
                    break
                if max_frames is not None and n >= max_frames:
                    break
                t, crop = grab(lg.render.crop)
                for rec in reader.feed(t, crop, frame=n):
                    fh.write(json.dumps(rec) + "\n")
                fh.flush()
                n += 1
                nxt = max(nxt + period, time.monotonic() - period)  # late: no catch-up burst
                time.sleep(max(0.0, nxt - time.monotonic()))
        for rec in reader.flush():
            with out.open("a") as fh:
                fh.write(json.dumps(rec) + "\n")
    finally:
        signal.signal(signal.SIGINT, old_int)
        signal.signal(signal.SIGTERM, old_term)
        if screen is not None:
            screen.close()
    return {"out": str(out), "lang": lg.code, **auto, "frames_read": n, **reader.stats}


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# --- design time: glyph clusters and templates ------------------------------------------------


def collect_runs(crops: Iterable[np.ndarray], render: Render = EN_RENDER) -> list[list[Any]]:
    """[[count, bitmap]] of distinct glyph runs (exact), merged when the same width and <= 2 px
    apart, most frequent first. A language with stacked marks (render.band_above / below,
    min_glyph_w) gets its clusters -- a base glyph with its marks -- as one run each."""
    exact: dict[tuple[int, bytes], list[Any]] = {}
    for crop in crops:
        for k in range(render.n_lines):
            m = ink_of(band_of(crop, k, render), None, render.luma_min)
            for a, b in runs(m, render.min_ink, render.min_glyph_w, render.space_cols):
                g = m[:, a:b]
                c = exact.setdefault((g.shape[1], g.tobytes()), [0, g])
                c[0] += 1
    reps: list[list[Any]] = []
    for cnt, g in sorted(exact.values(), key=lambda c: -c[0]):
        for rep in reps:
            if rep[1].shape == g.shape and int((rep[1] != g).sum()) <= 2:
                rep[0] += cnt
                break
        else:
            reps.append([cnt, g])
    return reps


def ascii_grid(reps: Sequence[Sequence[Any]], min_count: int = 5, per: int = 10) -> str:
    """The clusters seen at least ``min_count`` times, labelled by their index in ``reps``."""
    idx = [i for i, (c, _) in enumerate(reps) if c >= min_count]
    lines = []
    for b in range(0, len(idx), per):
        grp = idx[b : b + per]
        lines.append("  ".join(f"{i:<4d}{reps[i][0]:<6d}".ljust(max(10, reps[i][1].shape[1]))
                               for i in grp))  # fmt: skip
        for row in range(reps[grp[0]][1].shape[0]):
            lines.append("  ".join("".join("#" if v else "." for v in reps[i][1][row]).ljust(10)
                                   for i in grp))  # fmt: skip
        lines.append("")
    return "\n".join(lines)


def cut(clusters: Path, labels: Path, out: Path) -> dict[str, Any]:
    """labels.json = {"<cluster index>": "<char>", ...} ('~' = a Thai glyph; unlisted = not a
    template)."""
    with np.load(clusters) as z:
        bms = [z[f"g{i}"].astype(bool) for i in range(int(z["n"]))]
    lab = {int(k): v for k, v in json.loads(labels.read_text()).items()}
    chars = [lab[i] for i in sorted(lab)]
    out.parent.mkdir(parents=True, exist_ok=True)
    arrays = {f"g{j}": bms[i].astype(np.uint8) for j, i in enumerate(sorted(lab))}
    np.savez_compressed(out, chars=np.array(chars), **arrays)
    return {"out": str(out), "templates": len(chars), "chars": "".join(sorted(set(chars)))}


def cut_names(sid: str, lang: Lang, out: Path) -> dict[str, Any]:
    """Design time: per-species NAME templates from a session's DAMAGE lines, labelled by PACKETS
    (battle_log_judge.match of each line to our hit; the species of the hit's target): the
    per-pixel majority of each species' bracketed word. Needs `replay SID` first."""
    import battle_log_judge as bj

    assert lang.glyphs is not None
    render = lang.render
    packets, lines, _ = bj.load(sid)
    hits = bj.hits_of(packets)
    dl = [x for x in lines if x["type"] == "damage"]
    files = {i: p for i, _, p in frame_files(RECORDINGS / sid / "frames")}
    gl = lang.glyphs
    inst: dict[str, list[np.ndarray]] = {}
    for i, j in bj.match(dl, hits, "n", "damage"):
        if j is None or hits[j]["species"] is None or dl[i].get("frame") not in files:
            continue
        crop = read_crop(files[dl[i]["frame"]], render)
        ln = read_line(band_of(crop, int(dl[i]["slot"]), render), gl, None, render)
        g = bracket_word(ln) if ln is not None else None
        if g is not None:
            inst.setdefault(str(hits[j]["species"]), []).append(g)
    tmpl = {}
    for name, gs in inst.items():
        w = max(g.shape[1] for g in gs)
        stack = np.zeros((len(gs), render.band_h, w), bool)
        for k, g in enumerate(gs):
            stack[k, :, : g.shape[1]] = g
        maj = _trim(stack.mean(0) >= 0.5)
        if maj is not None:
            tmpl[name] = maj.astype(np.uint8)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, **tmpl)
    return {"out": str(out), "instances": {k: len(v) for k, v in inst.items()}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    lang_help = "a language code, 'auto', or (default) lang.json's, else en"
    rp = sub.add_parser("replay")
    rp.add_argument("sid")
    rp.add_argument("--frames", type=Path, default=None)
    rp.add_argument("--out", type=Path, default=None)
    rp.add_argument("--lang", default=None, help=lang_help)
    lv = sub.add_parser("live")
    lv.add_argument("--out", type=Path, required=True)
    lv.add_argument("--hz", type=float, default=5.0)
    lv.add_argument("--until-pid", type=int, default=None)
    lv.add_argument("--lang", default=None, help=lang_help)
    cl = sub.add_parser("clusters")
    cl.add_argument("sid", nargs="?", default="")
    cl.add_argument("--every", type=int, default=2)
    cl.add_argument("--out", type=Path, default=Path("/dev/shm/poring-lab-tmp/battle_log"))
    cl.add_argument("--lang", default=None)
    cl.add_argument("--frames", type=Path, default=None)
    cl.add_argument("--images", type=Path, nargs="*", default=None,
                    help="game-region images (a screenshot) instead of a recording")  # fmt: skip
    ct = sub.add_parser("cut")
    ct.add_argument("clusters", type=Path)
    ct.add_argument("labels", type=Path)
    ct.add_argument("--lang", default=None)
    cn = sub.add_parser("cut-names")
    cn.add_argument("sid")
    cn.add_argument("--lang", default=None)
    fi = sub.add_parser("formats-init")
    fi.add_argument("lang", choices=["en"])
    fi.add_argument("--force", action="store_true")
    a = ap.parse_args()
    os.nice(19 if a.cmd in ("replay", "clusters", "cut-names") else 10)
    if a.cmd == "replay":
        print(json.dumps(replay(a.sid, a.frames, a.out, lang=a.lang)))
    elif a.cmd == "live":
        print(json.dumps(live(a.out, a.hz, a.until_pid, lang=a.lang)))
    elif a.cmd == "formats-init":
        print(json.dumps(formats_init(a.lang, a.force)))
    elif a.cmd == "clusters":
        code = a.lang or default_code()
        fm = lang_dir(code) / "formats.json"
        render = lang_from_formats(json.loads(fm.read_text())).render if fm.exists() \
            else EN_RENDER  # fmt: skip
        paths = a.images or [
            p for _, _, p in frame_files(a.frames or RECORDINGS / a.sid / "frames")[:: a.every]
        ]
        reps = collect_runs((read_crop(p, render) for p in paths), render)  # fmt: skip
        a.out.mkdir(parents=True, exist_ok=True)
        arrays = {f"g{i}": g.astype(np.uint8) for i, (_, g) in enumerate(reps)}
        np.savez_compressed(a.out / "clusters.npz", n=len(reps),
                            counts=np.array([c for c, _ in reps]), **arrays)  # fmt: skip
        print(ascii_grid(reps))
    elif a.cmd == "cut-names":
        lg = load_lang(a.lang)
        print(json.dumps(cut_names(a.sid, lg, lang_dir(lg.code) / "names.npz")))
    else:
        out = lang_dir(a.lang or default_code()) / "glyphs.npz"
        print(json.dumps(cut(a.clusters, a.labels, out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
