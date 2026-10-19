#!/usr/bin/env python3
"""The client's BATTLE LOG chat tab, read from PIXELS (Batt 2026-10-19: the hunting layout has it).

    battle_log.py replay SID [--frames DIR] [--out FILE]   a banked session's recorded frames ->
                                                           /dev/shm/poring-lab-demo/SID/battle_log.jsonl
    battle_log.py live --out FILE [--hz 5] [--until-pid PID]   the LIVE frames, read-only
    battle_log.py clusters SID [--every 2] [--out DIR]    design time: the glyph runs of a session's
                                                           frames, clustered (ASCII grid printed)
    battle_log.py cut CLUSTERS.npz LABELS.json            design time: the glyph templates
    battle_log.py cut-names SID                           design time: species name templates,
                                                           labelled by the session's packets

THIS MODULE NEVER SENDS INPUT. ``live`` holds no Agent and opens no ro_agent.session: it reads
frames (ro_agent.Screen().grab of the chat window's rows of the game region, as human_demo's
recorder does) and nothing else (test_battle_log.py checks the source).

The chat window of the hunting layout (measured on 20261019T152849-demo-hunt-flow43's frames,
client px): the tab strip at y 530..547 ("Battle Log" selected = client_layout's tabs_battle
template), THREE message lines on a 14 px pitch, line k's band at rows 551 + 14 k .. 564 + 14 k
(x-height rows 555..561 of line 0, ascenders from 552, descenders to 563), the text from x 8
(a line that starts with a space, the damage line, from x 12) to at most x 580; the scrollbar is
right of x 584 and the input box below y 596. The newest line is the BOTTOM one; a new line
scrolls the others up by one band.

Reading (pure functions):
- a line's ink = LUMA > LUMA_MIN in its band: the client's flat bitmap font is bright on the
  darkened, translucent window (the background stays under ~110 luma; yellow text ~235, cyan
  ~180). Luma, not a colour mask: JPEG (the recorded frames are q80) subsamples the chroma, and a
  cyan mask lost whole strokes (2026-10-19 design probe); the luma plane is full resolution;
- glyph runs = column runs of ink split on empty columns; a gap of >= SPACE_COLS columns is a
  space. Each run is matched to the nearest glyph template (Hamming over the full band height, so
  a quote and a comma differ by row; width +-1), within a tolerance and a margin over the next
  other character; a run that matches nothing is tried as two touching glyphs (a JPEG speck
  bridges a gap), else it reads '?'. Thai item names read as '?'s, never as text;
- the line's colour = its ink's mean RGB (yellow / cyan / teal / white / red / green);
- the type by the decoded text: DAMAGE `[<name>] receives '<N>' damage points.`, BASE / JOB EXP
  `'<N>' Base|Job Experience acquired.`, ITEM `You got <...> (<count>).`, else OTHER. A '?' in a
  fixed word still matches it (a speck must not turn a damage line into OTHER); a number is read
  only when every digit matched, else its field is None;
- the monster NAME = the bracketed text, mapped to the species vocabulary (exact, or the one
  name the readable letters fit); species name templates (`cut-names`, labelled by packets)
  answer when a letter of the name is unknown.

NEW lines (lines carry no timestamps): the visible lines of a frame are compared with the last
frame's (the Battle Log shown in both; frames with another tab are skipped and the comparison
resumes against the last Battle Log frame). The smallest shift s (0..3) with this frame's first
3 - s lines EQUAL to the last frame's lines s.. is taken; the bottom s lines are new. Equal =
same colour and the same decoded text, or, when either holds a '?', ink bitmaps within
SAME_TOL. Identical consecutive lines (two kills with the same EXP) are therefore counted right
whenever the scroll is SEEN: [dmg, base 2, job 1] -> [base 2, job 1, dmg'] is s = 1 even though
the old and the new lines repeat; what cannot be seen is a scroll that brings back exactly the
lines it pushed out (all three, or a period of the pattern) within one frame interval -- the
smallest shift is taken (an undercount), and the record says ``ambiguous`` when a larger shift
fitted as well. s = 3 means no overlap: >= 3 new lines, and any beyond 3 were never visible
(``overflow``).

Templates are client pixels: data/ui_anchors/battle_log/ (gitignored), never committed.
"""

from __future__ import annotations

import argparse
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


# --- pixels -> ink --------------------------------------------------------------------------------


def luma(rgb: np.ndarray) -> np.ndarray:
    a = np.asarray(rgb)[..., :3].astype(np.float32)
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


def band_rows(k: int) -> tuple[int, int]:
    y0 = LINE_Y0 + LINE_PITCH * k
    return y0, y0 + LINE_PITCH


def chat_crop(frame_rgb: np.ndarray) -> np.ndarray:
    """The CROP of a full game-region RGB frame (a live grab is already this crop)."""
    x0, y0, x1, y1 = CROP
    return np.asarray(frame_rgb)[y0:y1, x0:x1, :3]


def band_of(crop_rgb: np.ndarray, k: int) -> np.ndarray:
    """Line k's RGB band (LINE_PITCH x text width) out of a CROP."""
    y0, y1 = band_rows(k)
    return np.asarray(crop_rgb)[y0 - CROP[1] : y1 - CROP[1], TEXT_X0 - CROP[0] : TEXT_X1 - CROP[0]]


def ink_of(band_rgb: np.ndarray, colour: str | None = None) -> np.ndarray:
    """Bright pixels that are not a SPRITE behind the translucent window: a Poring's highlights
    pass the luma bar at about (172, 142, 132) -- r - g +20..+40, b - g -20..0 -- while yellow
    text sits at r - g ~ +4, b - g ~ -113 and cyan at r - g ~ -90 (20261019T152849 frames
    370-383). With ``colour`` known, only pixels of that colour are kept (yellow: b - g < -45;
    cyan / teal: r - g < -20)."""
    a = np.asarray(band_rgb)[..., :3].astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    m = luma(band_rgb) > LUMA_MIN
    pink = (r - g > 15) & (r - g < 70) & (b - g > -45)
    m &= ~pink
    if colour == "yellow":
        m &= b - g < -45
    elif colour in ("cyan", "teal"):
        m &= r - g < -20
    return m


def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """(start, end) column runs of ink, specks (< MIN_INK pixels) dropped."""
    cols = mask.any(0)
    out, start = [], None
    for x, on in enumerate([*cols.tolist(), False]):
        if on and start is None:
            start = x
        elif not on and start is not None:
            if int(mask[:, start:x].sum()) >= MIN_INK:
                out.append((start, x))
            start = None
    return out


def colour_of(band_rgb: np.ndarray, mask: np.ndarray) -> str:
    """The text colour class from the ink's mean RGB (JPEG blurs the chroma towards the darkened
    background, so the classes are coarse)."""
    if int(mask.sum()) < 4:
        return "none"
    r, g, b = (float(v) for v in np.asarray(band_rgb)[mask][:, :3].astype(np.float32).mean(0))
    if r > 150 and g > 150 and b < 0.75 * min(r, g):
        return "yellow"
    if g > 150 and b > 150 and r < 0.7 * min(g, b):
        return "cyan"
    if g > 150 and b > 120 and r < 0.85 * g:
        return "teal"
    if r > 150 and g < 0.6 * r and b < 0.6 * r:
        return "red"
    if g > 150 and r < 0.75 * g and b < 0.75 * g:
        return "green"
    return "white" if min(r, g, b) > 150 else "other"


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


def decode(mask: np.ndarray, gl: Glyphs) -> tuple[str, list[tuple[int, int, str]]]:
    """A line's text ('?' per unreadable run, '~' runs read as '?', a space per gap of >=
    SPACE_COLS columns) and its runs [(x0, x1, chars)]."""
    rs = runs(mask)
    text: list[str] = []
    parts: list[tuple[int, int, str]] = []
    prev_end: int | None = None
    for a, b in rs:
        if prev_end is not None and a - prev_end >= SPACE_COLS:
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
    mask: np.ndarray  # the band's ink (LINE_PITCH x text width)
    parts: list[tuple[int, int, str]]  # the glyph runs: (x0, x1, chars) in band columns

    @property
    def ink(self) -> int:
        return int(self.mask.sum())

    @property
    def x0(self) -> int:
        """The first ink column (client px)."""
        return TEXT_X0 + (self.parts[0][0] if self.parts else 0)


def read_line(band_rgb: np.ndarray, gl: Glyphs,
              cache: dict[bytes, tuple[str, list[tuple[int, int, str]]]] | None = None
              ) -> Line | None:  # fmt: skip
    """One band's line (None = empty): the colour from the sprite-free ink, then the ink of that
    colour only, decoded. ``cache`` maps a mask's bytes to its decode."""
    m0 = ink_of(band_rgb)
    if int(m0.sum()) < 4:
        return None
    colour = colour_of(band_rgb, m0)
    m = ink_of(band_rgb, colour)
    if int(m.sum()) < 4:
        return None
    key = m.tobytes()
    if cache is not None and key in cache:
        text, parts = cache[key]
    else:
        text, parts = decode(m, gl)
        if cache is not None:
            if len(cache) > 20000:
                cache.clear()
            cache[key] = (text, parts)
    return Line(text, colour, m, parts)


def read_lines(crop_rgb: np.ndarray, gl: Glyphs,
               cache: dict[bytes, tuple[str, list[tuple[int, int, str]]]] | None = None
               ) -> list[Line | None]:  # fmt: skip
    """The N_LINES visible lines of a CROP, top to bottom (None = an empty band)."""
    return [read_line(band_of(crop_rgb, k), gl, cache) for k in range(N_LINES)]


COLOUR_GROUP = {"cyan": "blue", "teal": "blue"}
SAME_MIN_SHARE = 0.7  # of the shorter line's runs that must sit at the same columns
QMARK_TOL_MIN, QMARK_TOL_FRAC = 3, 0.25  # two unread runs at the same columns: the same glyphs
# an unpaired read run this small (a period, a quote) is not a difference: the RDP progressive
# codec draws a new line coarse first, and its smallest glyphs come a frame later (frame 1048)
SMALL_INK = 4


def _pair(p: tuple[int, int, str], parts: Sequence[tuple[int, int, str]]) -> int | None:
    """The index of the run of ``parts`` at the same columns as ``p``: overlapping by at least
    half the narrower one (a JPEG speck widens a run by a column now and then)."""
    best, best_ov = None, 0
    for j, (x0, x1, _) in enumerate(parts):
        ov = min(x1, p[1]) - max(x0, p[0])
        if ov > best_ov and ov * 2 >= min(x1 - x0, p[1] - p[0]):
            best, best_ov = j, ov
    return best


def same_line(a: Line | None, b: Line | None) -> bool:
    """The same line: the same colour group, and their glyph runs ALIGNED -- a line is drawn at
    fixed columns, so the same text puts its runs at the same columns (+-1). Every run pair at
    the same columns must agree (read characters equal; two unread runs within QMARK_TOL over
    their joint columns; a read and an unread run pass: a speck or a sprite can spoil one glyph
    in one frame), and at least SAME_MIN_SHARE of the shorter line's runs must pair up. A run
    with no partner is ignored when unread (a sprite's highlights beside the text) and is a
    difference when read (real text where the other line has none)."""
    if a is None or b is None:
        return a is b
    if COLOUR_GROUP.get(a.colour, a.colour) != COLOUR_GROUP.get(b.colour, b.colour):
        return False
    if a.text == b.text and "?" not in a.text:
        return True
    paired = 0
    for x0, x1, c in a.parts:
        j = _pair((x0, x1, c), b.parts)
        if j is None:
            if "?" not in c and not _covered((x0, x1, c), b.parts) \
                    and int(a.mask[:, x0:x1].sum()) > SMALL_INK:  # fmt: skip
                return False
            continue
        bx0, bx1, cb = b.parts[j]
        paired += 1
        if "?" in c and "?" in cb:
            u0, u1 = min(x0, bx0), max(x1, bx1)
            ga, gb = a.mask[:, u0:u1], b.mask[:, u0:u1]
            tol = max(QMARK_TOL_MIN, int(QMARK_TOL_FRAC * max(int(ga.sum()), int(gb.sum()))))
            if int((ga ^ gb).sum()) > tol:
                return False
        elif "?" not in c and "?" not in cb and c != cb:
            return False
    for x0, x1, c in b.parts:
        if "?" not in c and _pair((x0, x1, c), a.parts) is None \
                and not _covered((x0, x1, c), a.parts) \
                and int(b.mask[:, x0:x1].sum()) > SMALL_INK:  # fmt: skip
            return False
    shorter = min(len(a.parts), len(b.parts))
    return shorter == 0 or paired >= SAME_MIN_SHARE * shorter


def _covered(p: tuple[int, int, str], parts: Sequence[tuple[int, int, str]]) -> bool:
    """A read run that overlaps an UNREAD run of the other line (a glyph merged with a speck)."""
    return any("?" in c and x0 < p[1] and p[0] < x1 for x0, x1, c in parts)


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


def clean(ln: Line) -> bool:
    """A line read in full: a typed line with its number, or another line with no unread glyph
    (an item line's name is never read: its count must be)."""
    k = classify(ln.text, ln.colour)
    if k["type"] == "damage":
        return k["n"] is not None and "?" not in k["name_read"]
    if k["type"] in ("base_exp", "job_exp"):
        return k["n"] is not None
    if k["type"] == "item":
        return k["count"] is not None
    return "?" not in ln.text


# --- the line types ----------------------------------------------------------------------------


def _num(s: str | None) -> int | None:
    return int(s) if s is not None and s.isdigit() else None


def _like(token: str, word: str, min_ratio: float = LIKE_MIN) -> bool:
    """A decoded token reads as ``word``: SequenceMatcher ratio >= min_ratio (a '?' or a split
    glyph costs a little; 'acquii ed' still reads as acquired)."""
    return difflib.SequenceMatcher(None, token, word).ratio() >= min_ratio


# the fixed words, built at run time (the full client strings are not repeated in the source)
_W = {"rec": "receives", "dmg": "damage", "pts": "points", "base": "Base", "job": "Job",
      "exp": "Experience", "acq": "acquired", "you": "You", "got": "got"}  # fmt: skip
RX_QUOTED = re.compile(r"'?\s*(?P<n>[0-9?]+)\s*'")  # 'N' (a coarse first frame can lose a quote)
RX_COUNT = re.compile(r"\(\s*(?P<n>[0-9?]+)\s*\)\s*\.?\s*$")  # (N). at the end


def species_of(name: str, vocab: Sequence[str] = SPECIES) -> str | None:
    """The species a bracketed name reads as: exact, else the ONE vocabulary name that the read
    letters fit, each '?' standing for 1-2 letters (an unknown glyph, or two touching ones read
    as one run: "Crea?" fits Creamy); None otherwise."""
    if "?" not in name:
        return name if name in vocab else None
    rx = re.compile("".join(".{1,2}" if ch == "?" else re.escape(ch) for ch in name))
    fit = [v for v in vocab if rx.fullmatch(v)]
    return fit[0] if len(fit) == 1 and sum(ch != "?" for ch in name) >= 2 else None


def classify(text: str, colour: str = "") -> dict[str, Any]:
    """PURE: {"type", fields} of one decoded line, by its SHAPE with fuzzy fixed words:
    - damage: '[' first, a ']', then a word like "receives", a quoted number, "damage";
    - base / job EXP: a quoted number first, then a word like "Base" / "Job" and "Experience";
    - item: "You" "got" first and a "(N)" at the end;
    - anything else: other."""
    t = text.strip()
    words = t.replace("'", " ' ").split()
    if t.startswith("[") and "]" in t:
        name, rest = t[1:].split("]", 1)
        q = RX_QUOTED.search(rest)
        rw = rest.split()
        if q and rw and _like(rw[0], _W["rec"]) and any(_like(w, _W["dmg"]) for w in rw):
            name = name.strip()
            return {"type": "damage", "n": _num(q["n"]), "name_read": name,
                    "name": species_of(name)}  # fmt: skip
    q = RX_QUOTED.match(t)
    if q:
        rest = t[q.end() :].split()
        if len(rest) >= 2 and any(_like(w, _W["exp"]) for w in rest[1:3]):
            kb = difflib.SequenceMatcher(None, rest[0], _W["base"]).ratio()
            kj = difflib.SequenceMatcher(None, rest[0], _W["job"]).ratio()
            if max(kb, kj) >= LIKE_MIN and kb != kj:
                return {"type": "base_exp" if kb > kj else "job_exp", "n": _num(q["n"])}
    if len(words) >= 3 and _like(words[0], _W["you"]) and _like(words[1], _W["got"]):
        c = RX_COUNT.search(t)
        if c:
            return {"type": "item", "count": _num(c["n"])}
    return {"type": "other"}


# --- the stream reader -------------------------------------------------------------------------


def tab_is_battle(crop_rgb: np.ndarray) -> bool | None:
    """The Battle Log tab is the selected one: the chat window's top border (row TAB_EDGE_Y, an
    opaque light line) is drawn under the UNSELECTED tab only. True / False, or None when the
    border reads neither way (a sprite or the cursor on it). Both tabs are translucent, so
    their fill tracks the scene behind them (dark grass: a template distance of 50 against the
    Battle Log template and 86 against Regular Chat); the border does not."""
    row = luma(np.asarray(crop_rgb)[TAB_EDGE_Y - CROP[1] : TAB_EDGE_Y - CROP[1] + 1, :, :3])[0]
    edge = row > TAB_EDGE_LUMA
    fb = float(edge[BATTLE_SPAN[0] - CROP[0] : BATTLE_SPAN[1] - CROP[0]].mean())
    fr = float(edge[REGULAR_SPAN[0] - CROP[0] : REGULAR_SPAN[1] - CROP[0]].mean())
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

    def __init__(self, gl: Glyphs, names: Mapping[str, np.ndarray] | None = None,
                 trace: list[dict[str, Any]] | None = None) -> None:  # fmt: skip
        self.gl, self.names, self.trace = gl, names, trace
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
        tab = tab_is_battle(crop_rgb)
        if tab is False:
            self.stats["other_tab"] += 1
            return []
        self.stats["tab_unknown"] += int(tab is None)
        cur = read_lines(crop_rgb, self.gl, self.cache)
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
            if not clean(ln):
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
        rec.update(classify(ln.text, ln.colour))
        rec.update(colour=ln.colour, text=ln.text, x0=ln.x0, clean=clean(ln))
        if rec["type"] == "damage" and rec.get("name") is None and self.names:
            rec["name"] = name_by_template(ln, self.names)
            rec["name_by"] = "template"

    def _commit(self, t_ns: int, frame: Any, cur: list[Line | None], idx: Sequence[int],
                shift: int, ambiguous: bool, t_now: int) -> list[dict[str, Any]]:  # fmt: skip
        n_vis = _count(cur)
        overflow = bool(idx) and len(idx) == n_vis and n_vis == N_LINES
        self.stats["ambiguous"] += int(ambiguous and bool(idx))
        self.stats["overflow"] += int(overflow)
        gone, kept = self.vis[:shift], self.vis[shift:]
        lines = [x for x in cur if x is not None]
        for rec, ln in zip(kept, lines, strict=False):  # the lines still visible: refine
            if rec is not None and not rec["_out"] and not rec["clean"] and clean(ln):
                self._fill(rec, ln)
                rec["refined"] = True
                self.stats["refined"] += 1
        new = []
        for i in idx:
            ln = cur[i]
            assert ln is not None
            new.append(self._record(t_ns, frame, i, ln, shift, ambiguous, overflow))
        self.vis = [*kept, *new]
        self.prev = cur
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


def read_crop(path: Path) -> np.ndarray:
    from PIL import Image

    with Image.open(path) as im:  # crop first: no full-frame copy
        return np.asarray(im.crop(CROP).convert("RGB"))


def replay(sid: str, frames_dir: Path | None = None, out: Path | None = None,
           gl: Glyphs | None = None) -> dict[str, Any]:  # fmt: skip
    frames_dir = frames_dir or RECORDINGS / sid / "frames"
    out = out or DEMO / sid / "battle_log.jsonl"
    trace: list[dict[str, Any]] = []
    reader = Reader(gl or load_glyphs(), load_names(), trace)
    files = frame_files(frames_dir)
    counts: dict[str, int] = {}
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as fh:
        for i, t, p in files:
            for rec in reader.feed(t, read_crop(p), frame=i):
                counts[rec["type"]] = counts.get(rec["type"], 0) + 1
                fh.write(json.dumps(rec) + "\n")
        for rec in reader.flush():
            counts[rec["type"]] = counts.get(rec["type"], 0) + 1
            fh.write(json.dumps(rec) + "\n")
    with out.with_name(out.stem + "_frames.jsonl").open("w") as fh:
        fh.writelines(json.dumps(x) + "\n" for x in trace)
    return {"sid": sid, "out": str(out), "frames": len(files), "lines": counts, **reader.stats}


def live(out: Path, hz: float = 5.0, until_pid: int | None = None,
         grab: Callable[[], tuple[int, np.ndarray]] | None = None,
         max_frames: int | None = None) -> dict[str, Any]:  # fmt: skip
    """Read the LIVE frames (read-only) at ``hz`` and append the new lines' records to ``out``
    until SIGINT / SIGTERM, the exit of ``until_pid``, or ``max_frames``. ``grab`` (a test seam)
    returns (t_mono_ns, the CROP as RGB); by default ro_agent.Screen's grab of the chat rows."""
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
        x0, y0, x1, y1 = CROP

        def grab() -> tuple[int, np.ndarray]:
            assert screen is not None
            t, img = screen.grab(gx + x0, gy + y0, x1 - x0, y1 - y0)
            return int(t), np.asarray(img)[..., :3][..., ::-1]  # BGRA -> RGB

    reader = Reader(load_glyphs(), load_names())
    period = 1.0 / hz
    n = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with out.open("a") as fh:
            nxt = time.monotonic()
            while not stop["v"]:
                if until_pid is not None and not _alive(until_pid):
                    break
                if max_frames is not None and n >= max_frames:
                    break
                t, crop = grab()
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
    return {"out": str(out), "frames_read": n, **reader.stats}


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# --- design time: glyph clusters and templates ------------------------------------------------


def collect_runs(crops: Iterable[np.ndarray]) -> list[list[Any]]:
    """[[count, bitmap]] of distinct glyph runs (exact), merged when the same width and <= 2 px
    apart, most frequent first."""
    exact: dict[tuple[int, bytes], list[Any]] = {}
    for crop in crops:
        for k in range(N_LINES):
            m = ink_of(band_of(crop, k))
            for a, b in runs(m):
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
        for row in range(LINE_PITCH):
            lines.append("  ".join("".join("#" if v else "." for v in reps[i][1][row]).ljust(10)
                                   for i in grp))  # fmt: skip
        lines.append("")
    return "\n".join(lines)


def cut(clusters: Path, labels: Path, out: Path = GLYPHS) -> dict[str, Any]:
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


def cut_names(sid: str, out: Path = NAMES) -> dict[str, Any]:
    """Design time: per-species NAME templates from a session's DAMAGE lines, labelled by PACKETS
    (battle_log_judge.match of each line to our hit; the species of the hit's target): the
    per-pixel majority of each species' bracketed word. Needs `replay SID` first."""
    import battle_log_judge as bj

    packets, lines, _ = bj.load(sid)
    hits = bj.hits_of(packets)
    dl = [x for x in lines if x["type"] == "damage"]
    files = {i: p for i, _, p in frame_files(RECORDINGS / sid / "frames")}
    gl = load_glyphs()
    inst: dict[str, list[np.ndarray]] = {}
    for i, j in bj.match(dl, hits, "n", "damage"):
        if j is None or hits[j]["species"] is None or dl[i].get("frame") not in files:
            continue
        ln = read_line(band_of(read_crop(files[dl[i]["frame"]]), int(dl[i]["slot"])), gl)
        g = bracket_word(ln) if ln is not None else None
        if g is not None:
            inst.setdefault(str(hits[j]["species"]), []).append(g)
    tmpl = {}
    for name, gs in inst.items():
        w = max(g.shape[1] for g in gs)
        stack = np.zeros((len(gs), LINE_PITCH, w), bool)
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
    rp = sub.add_parser("replay")
    rp.add_argument("sid")
    rp.add_argument("--frames", type=Path, default=None)
    rp.add_argument("--out", type=Path, default=None)
    lv = sub.add_parser("live")
    lv.add_argument("--out", type=Path, required=True)
    lv.add_argument("--hz", type=float, default=5.0)
    lv.add_argument("--until-pid", type=int, default=None)
    cl = sub.add_parser("clusters")
    cl.add_argument("sid")
    cl.add_argument("--every", type=int, default=2)
    cl.add_argument("--out", type=Path, default=Path("/dev/shm/poring-lab-tmp/battle_log"))
    ct = sub.add_parser("cut")
    ct.add_argument("clusters", type=Path)
    ct.add_argument("labels", type=Path)
    cn = sub.add_parser("cut-names")
    cn.add_argument("sid")
    a = ap.parse_args()
    os.nice(19 if a.cmd in ("replay", "clusters", "cut-names") else 10)
    if a.cmd == "replay":
        print(json.dumps(replay(a.sid, a.frames, a.out)))
    elif a.cmd == "live":
        print(json.dumps(live(a.out, a.hz, a.until_pid)))
    elif a.cmd == "clusters":
        files = frame_files(RECORDINGS / a.sid / "frames")[:: a.every]
        reps = collect_runs(read_crop(p) for _, _, p in files)
        a.out.mkdir(parents=True, exist_ok=True)
        arrays = {f"g{i}": g.astype(np.uint8) for i, (_, g) in enumerate(reps)}
        np.savez_compressed(a.out / "clusters.npz", n=len(reps),
                            counts=np.array([c for c, _ in reps]), **arrays)  # fmt: skip
        print(ascii_grid(reps))
    elif a.cmd == "cut-names":
        print(json.dumps(cut_names(a.sid)))
    else:
        print(json.dumps(cut(a.clusters, a.labels)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
