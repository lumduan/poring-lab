"""The NPC menu's option lines from pixels (talk@1 T3, docs/demonstrations.md 3.30).

The client draws a menu option as one line of a crisp bitmap font: black ink on the row's
background (light grey, or the light-blue band of the selected row), no anti-aliasing on RDP once
the codec has refined the region. Measured 2026-10-09 on banked RDP frames: glyphs are 1-7 px wide
and one blank column apart inside a word, a space is a 5-column gap, ink sits on rows 2-13 of the
16-row band and the first ink of a line on its 4th column.

This module reads ONE row at a time, and the whole list across scroll positions, and fails CLOSED:
  * every pixel of the row is background, black ink (any blend of the two) -- or the row is
    refused: ``coloured_text`` (an option with ^RRGGBB codes is drawn in colour: never a target),
    ``foreign_pixels`` (a cursor, an occluder, a codec smear);
  * the ink's column runs are glyphs; each must match ONE template of its width under
    ``max_score`` and beat every other character of that width by ``min_margin``; a run that matches
    none may be 2-3 touching glyphs (one unique split) -- otherwise ``unknown_glyph`` /
    ``ambiguous_glyph``;
  * a gap between glyphs is an in-word gap or 1+ spaces as calibrated, else ``unexplained_gap``;
    the first ink must sit where a line starts (``leading_blank``) and the last must not touch the
    row's end (``cut_off``).
A trailing space is invisible: the expected string is compared with its trailing spaces removed
(``visible_text``). The templates are cut LOCALLY by scripts/talk_calibrate.py ``cut`` from
frames labelled by packet truth (the server's ``npc_menu`` option strings), into
``data/ui_anchors/menu_glyphs.npz`` (client pixels, gitignored, never committed). They hold one
bitmap per CHARACTER; no option string is stored here or there.

The list: ``accumulate`` merges the reads of successive scroll positions (each aligned to the
previous by its overlapping lines, a unique shift) into the full list, from the top (no scroll up
possible) to the bottom (no scroll down possible); ``cross_check`` compares it with the L3 option
list as a WHOLE (same count, same order, every line equal). A line read on no position is
``line_unread``: the menu is declined, never guessed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

Gray = npt.NDArray[np.float32]

DEFAULT_GLYPHS = Path("data/ui_anchors/menu_glyphs.npz")
FORMAT_VERSION = 1
BAND_H = 16  # a row's height (the menu's 16 px pitch)
PLAIN_RGB = (247, 247, 247)  # as poring_env.npc_dialog (measured 2026-10-09)
HIGHLIGHT_RGB = (206, 222, 255)
WHITE_RGB = (255, 255, 255)
BG_TOL = 16
BG_SHARE = 0.9  # the row's first 3 columns (always background) must be this much one colour
INK_P = 0.5  # a pixel at least this far from the background toward black is ink
FOREIGN_TOL = 40.0  # a pixel this far from any background-to-black blend is not ink
FOREIGN_MAX = 1  # foreign pixels a row tolerates (a codec speck)
CHROMA = 80  # a foreign pixel this chromatic is coloured text
EDGE_PX = 2  # ink this close to the row's right end: the line may be cut off
MERGE_GAP = 2  # two runs this close may be ONE glyph drawn in two parts
MAX_SPLIT = 3  # a run may be at most this many touching glyphs
SCORE_FLOOR = 0.5  # true scores of a crisp font are ~0: thresholds never go below this
COLOUR_CODE = re.compile(r"\^[0-9A-Fa-f]{6}")
COLOURED = "\x00coloured"  # the key of a line drawn in colour (never a target)


def visible_text(option: str) -> str | None:
    """What the client shows of an option, as this reader can read it: trailing spaces removed;
    None for an option drawn in colour (it carries ^RRGGBB codes)."""
    if COLOUR_CODE.search(option):
        return None
    return option.rstrip(" ")


def visible_options(options: Sequence[str]) -> list[tuple[int, str]]:
    """(1-based packet index, option) of the options the client lists: an empty option is hidden
    but still counts in the index (the server numbers every option)."""
    return [(i + 1, o) for i, o in enumerate(options) if o != ""]


@dataclass(frozen=True, slots=True)
class MenuGlyphs:
    """One bitmap (ink probability) per character, and the acceptance rules."""

    chars: str
    bitmaps: Gray  # (n, BAND_H, max width), zero-padded right of each glyph's width
    widths: npt.NDArray[np.int64]  # (n,)
    counts: npt.NDArray[np.int64]  # (n,) training instances
    gaps0: tuple[int, ...]  # gaps seen inside a word
    gaps1: tuple[int, ...]  # gaps seen for ONE space
    lead: Mapping[str, int]  # first-ink column of a line that starts with this character
    lead_range: tuple[int, int]
    max_score: float
    min_margin: float
    meta: dict[str, Any] = field(default_factory=dict)

    def bitmap(self, i: int) -> Gray:
        return np.asarray(self.bitmaps[i, :, : int(self.widths[i])], np.float32)

    @property
    def space_adv(self) -> int:
        """Columns one more space adds to a gap."""
        return int(round(float(np.median(self.gaps1)) - float(np.median(self.gaps0))))

    def spaces(self, gap: int) -> int | None:
        """How many spaces a gap between two glyphs stands for; None if it is none of them."""
        if gap in self.gaps0:
            return 0
        if gap in self.gaps1:
            return 1
        adv = self.space_adv
        for k in range(2, 6):
            if adv > 0 and any(gap == g + (k - 1) * adv for g in self.gaps1):
                return k
        return None

    def missing(self, texts: Sequence[str]) -> str:
        """The characters of ``texts`` (visible, uncoloured) that have no template."""
        need = {c for t in texts if (v := visible_text(t)) for c in v if c != " "}
        return "".join(sorted(need - set(self.chars)))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        doc = {"chars": self.chars, "gaps0": list(self.gaps0), "gaps1": list(self.gaps1),
               "lead": dict(self.lead), "lead_range": list(self.lead_range),
               "max_score": self.max_score, "min_margin": self.min_margin,
               "meta": self.meta}  # fmt: skip
        np.savez_compressed(
            path, version=np.int64(FORMAT_VERSION), bitmaps=self.bitmaps.astype(np.float32),
            widths=self.widths.astype(np.int64), counts=self.counts.astype(np.int64),
            doc=np.array(json.dumps(doc, sort_keys=True)),
        )  # fmt: skip


def load_menu_glyphs(path: Path = DEFAULT_GLYPHS) -> MenuGlyphs:
    """The calibrated templates (scripts/talk_calibrate.py cut). Plain arrays only."""
    with np.load(path, allow_pickle=False) as z:
        if int(z["version"]) != FORMAT_VERSION:
            raise ValueError(f"{path}: format {int(z['version'])}, need {FORMAT_VERSION}")
        bitmaps = np.asarray(z["bitmaps"], np.float32)
        widths = np.asarray(z["widths"], np.int64)
        counts = np.asarray(z["counts"], np.int64)
        doc = json.loads(str(z["doc"]))
    chars = str(doc["chars"])
    if bitmaps.ndim != 3 or bitmaps.shape[0] != len(chars) or bitmaps.shape[1] != BAND_H:
        raise ValueError(f"{path}: expected ({len(chars)}, {BAND_H}, w) bitmaps")
    if widths.shape != (len(chars),) or counts.shape != (len(chars),):
        raise ValueError(f"{path}: widths / counts disagree with the characters")
    lr = doc["lead_range"]
    return MenuGlyphs(chars, bitmaps, widths, counts, tuple(int(g) for g in doc["gaps0"]),
                      tuple(int(g) for g in doc["gaps1"]),
                      {str(k): int(v) for k, v in doc["lead"].items()}, (int(lr[0]), int(lr[1])),
                      float(doc["max_score"]), float(doc["min_margin"]),
                      dict(doc.get("meta", {})))  # fmt: skip


# --- one row ------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Glyph:
    x: int  # first column
    char: str
    score: float
    margin: float


@dataclass(frozen=True, slots=True)
class RowRead:
    """``text``: the line ("" for an empty row) when ``reason`` is "ok" or "empty"; else None."""

    text: str | None
    reason: str
    confidence: float = 0.0
    highlighted: bool | None = None
    glyphs: tuple[Glyph, ...] = ()

    @property
    def key(self) -> str | None:
        """What two reads of the same line must agree on: the text, COLOURED, or None
        (unread)."""
        if self.reason in ("ok", "empty"):
            return self.text
        return COLOURED if self.reason == "coloured_text" else None


def _luma(rgb: npt.NDArray[np.float32]) -> npt.NDArray[np.float32]:
    return np.asarray(0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2], np.float32)


def _near(rgb: npt.NDArray[np.float32], ref: tuple[int, int, int], tol: float = BG_TOL
          ) -> npt.NDArray[np.bool_]:  # fmt: skip
    out: npt.NDArray[np.bool_] = (np.abs(rgb - np.array(ref, np.float32)) <= tol).all(axis=-1)
    return out


def ink_map(row_bgr: npt.NDArray[np.uint8]) -> tuple[Gray, npt.NDArray[np.bool_], str | None]:
    """(ink probability, foreign pixels, background name) of a row; the background is decided by
    its first 3 columns (always background: a line's ink starts on the 4th)."""
    rgb = row_bgr[..., 2::-1].astype(np.float32)
    head = rgb[: BAND_H - 1, :3]
    bg: str | None = None
    for name, ref in (("plain", PLAIN_RGB), ("highlight", HIGHLIGHT_RGB)):
        if head.size and float(_near(head, ref).mean()) >= BG_SHARE:
            bg = name
    if bg is None:
        return np.zeros(rgb.shape[:2], np.float32), np.zeros(rgb.shape[:2], bool), None
    bg_rgb = np.array(PLAIN_RGB if bg == "plain" else HIGHLIGHT_RGB, np.float32)
    lb = float(_luma(bg_rgb))
    p = np.clip((lb - _luma(rgb)) / lb, 0.0, 1.0).astype(np.float32)
    background = _near(rgb, PLAIN_RGB) | _near(rgb, HIGHLIGHT_RGB) | _near(rgb, WHITE_RGB)
    resid = np.abs(rgb - bg_rgb * (1.0 - p)[..., None]).max(axis=-1)
    foreign = ~background & (resid > FOREIGN_TOL)
    p = np.where(background | foreign, 0.0, p).astype(np.float32)
    return p, foreign, bg


def foreign_kind(row_bgr: npt.NDArray[np.uint8], foreign: npt.NDArray[np.bool_]) -> str | None:
    """None when the row has at most FOREIGN_MAX foreign pixels; else "coloured_text" (mostly
    chromatic: an option drawn in colour) or "foreign_pixels" (a cursor, an occluder)."""
    if int(foreign.sum()) <= FOREIGN_MAX:
        return None
    rgb = row_bgr[..., :3].astype(np.int16)[foreign]
    chroma = rgb.max(axis=-1) - rgb.min(axis=-1)
    return "coloured_text" if float((chroma >= CHROMA).mean()) >= 0.5 else "foreign_pixels"


def ink_runs(ink: npt.NDArray[np.bool_]) -> list[tuple[int, int]]:
    """[start, end) of every run of ink columns."""
    cols = ink.any(axis=0)
    out: list[tuple[int, int]] = []
    start: int | None = None
    for i, c in enumerate(cols):
        if c and start is None:
            start = i
        elif not c and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(cols)))
    return out


def span_match(p: Gray, a: int, b: int, g: MenuGlyphs) -> Glyph | None:
    """The one character whose template fits columns [a, b) under max_score and beats every
    other character of that width by min_margin; None otherwise."""
    width = b - a
    idx = np.flatnonzero(g.widths == width)
    if idx.size == 0:
        return None
    span = p[:, a:b]
    scores = sorted((float(((span - g.bitmap(int(i))) ** 2).sum()), int(i)) for i in idx)
    s1, i1 = scores[0]
    margin = scores[1][0] - s1 if len(scores) > 1 else float("inf")
    if s1 > g.max_score or margin < g.min_margin:
        return None
    return Glyph(a, g.chars[i1], s1, margin)


def split_run(p: Gray, a: int, b: int, g: MenuGlyphs) -> list[list[Glyph]]:
    """Every way to read columns [a, b) as 2..MAX_SPLIT touching glyphs."""
    out: list[list[Glyph]] = []

    def walk(x: int, acc: list[Glyph]) -> None:
        if x == b:
            if len(acc) >= 2:
                out.append(list(acc))
            return
        if len(acc) == MAX_SPLIT or len(out) > 1:
            return
        for w in sorted({int(v) for v in g.widths}):
            if x + w > b:
                break
            got = span_match(p, x, x + w, g)
            if got is not None:
                walk(x + w, [*acc, got])

    walk(a, [])
    return out


def read_row(row_bgr: npt.NDArray[np.uint8], g: MenuGlyphs) -> RowRead:  # noqa: PLR0911
    """One option line from its row (BAND_H rows, the row's text part; BGR)."""
    if row_bgr.shape[0] != BAND_H or row_bgr.shape[1] < 8:
        return RowRead(None, "bad_row")
    p, foreign, bg = ink_map(row_bgr)
    if bg is None:
        return RowRead(None, "no_background")
    lit = bg == "highlight"
    why = foreign_kind(row_bgr, foreign)
    if why is not None:
        return RowRead(None, why, highlighted=lit)
    ink = p >= INK_P
    if not ink.any():
        return RowRead("", "empty", 1.0, lit)
    runs = ink_runs(ink)
    if runs[-1][1] > ink.shape[1] - EDGE_PX:
        return RowRead(None, "cut_off", highlighted=lit)
    tokens: list[tuple[list[Glyph], int]] = []  # (glyphs, end column)
    i = 0
    while i < len(runs):
        a, b = runs[i]
        single = span_match(p, a, b, g)
        alone = [[single]] if single is not None else split_run(p, a, b, g)
        merged = None
        if i + 1 < len(runs) and runs[i + 1][0] - b <= MERGE_GAP:
            merged = span_match(p, a, runs[i + 1][1], g)
        if merged is not None and alone:
            return RowRead(None, "ambiguous_glyph", highlighted=lit)
        if merged is not None:
            tokens.append(([merged], runs[i + 1][1]))
            i += 2
            continue
        if len(alone) != 1:
            why = "unknown_glyph" if not alone else "ambiguous_glyph"
            return RowRead(None, why, highlighted=lit)
        tokens.append((alone[0], b))
        i += 1
    text = ""
    for k, (glyphs, _end) in enumerate(tokens):
        if k:
            n = g.spaces(glyphs[0].x - tokens[k - 1][1])
            if n is None:
                return RowRead(None, "unexplained_gap", highlighted=lit)
            text += " " * n
        text += "".join(gl.char for gl in glyphs)
    first = tokens[0][0][0]
    want = g.lead.get(first.char)
    lo, hi = (want, want) if want is not None else g.lead_range
    if not lo - 1 <= first.x <= hi + 1:
        return RowRead(None, "leading_blank", highlighted=lit)
    used = [gl for glyphs, _ in tokens for gl in glyphs]
    conf = min(
        min(
            1.0,
            max(0.0, 1 - gl.score / g.max_score),
            gl.margin / (2 * g.min_margin) if g.min_margin > 0 else 1.0,
        )
        for gl in used
    )
    return RowRead(text, "ok", float(conf), lit, tuple(used))


# --- the whole list ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MenuSnapshot:
    """The visible rows at one scroll position (top to bottom) and the scrollbar's state."""

    lines: tuple[RowRead, ...]
    can_scroll_up: bool
    can_scroll_down: bool


@dataclass(frozen=True, slots=True)
class FullList:
    """``lines``: one read per listed option, top to bottom (the best read of each), or None when
    the snapshots do not form one list; ``reason`` "ok" only when every line was read."""

    lines: tuple[RowRead, ...] | None
    reason: str
    tops: tuple[int, ...] = ()  # each snapshot's first line, as an index into ``lines``

    @property
    def keys(self) -> list[str | None]:
        return [] if self.lines is None else [ln.key for ln in self.lines]


def _trim(s: MenuSnapshot) -> list[RowRead] | str:
    """The snapshot's option lines: trailing empty rows dropped (only at the list's end)."""
    lines = list(s.lines)
    while lines and lines[-1].reason == "empty":
        lines.pop()
    if len(lines) < len(s.lines) and s.can_scroll_down:
        return "empty_row_before_end"
    if any(ln.reason == "empty" for ln in lines):
        return "empty_row_inside"
    return lines


def _agrees(a: Sequence[RowRead], b: Sequence[RowRead], shift: int) -> bool | None:
    """b placed ``shift`` lines below a's top: True (>= 1 compared line, all equal), False (a
    disagreement), None (nothing comparable)."""
    seen = False
    for j, ln in enumerate(b):
        i = j + shift
        if not 0 <= i < len(a):
            continue
        ka, kb = a[i].key, ln.key
        if ka is None or kb is None:
            continue
        if ka != kb:
            return False
        seen = True
    return True if seen else None


def accumulate(snaps: Sequence[MenuSnapshot]) -> FullList:
    """The full list from snapshots taken top first, each after scrolling DOWN (see module
    docstring)."""
    if not snaps:
        return FullList(None, "no_snapshot")
    if snaps[0].can_scroll_up:
        return FullList(None, "not_at_top")
    first = _trim(snaps[0])
    if isinstance(first, str):
        return FullList(None, first)
    merged: list[list[RowRead]] = [[ln] for ln in first]
    tops = [0]
    prev, prev_top = first, 0
    for s in snaps[1:]:
        cur = _trim(s)
        if isinstance(cur, str):
            return FullList(None, cur)
        fits = [d for d in range(1, len(prev)) if _agrees(prev, cur, d)]
        if len(fits) != 1:
            return FullList(None, "no_overlap" if not fits else "ambiguous_shift")
        top = prev_top + fits[0]
        for j, ln in enumerate(cur):
            if top + j < len(merged):
                merged[top + j].append(ln)
            else:
                merged.append([ln])
        tops.append(top)
        prev, prev_top = cur, top
    if snaps[-1].can_scroll_down:
        return FullList(None, "not_at_bottom", tuple(tops))
    lines: list[RowRead] = []
    for reads in merged:
        keys = {r.key for r in reads if r.key is not None}
        if len(keys) > 1:
            return FullList(None, "conflict", tuple(tops))
        best = [r for r in reads if r.key is not None]
        lines.append(max(best, key=lambda r: r.confidence) if best else reads[0])
    reason = "ok" if all(ln.key is not None for ln in lines) else "line_unread"
    return FullList(tuple(lines), reason, tuple(tops))


@dataclass(frozen=True, slots=True)
class CrossCheck:
    ok: bool
    reason: str
    packet_index: tuple[int, ...] = ()  # 1-based packet / L3 index of each listed line


def cross_check(full: FullList, options: Sequence[str]) -> CrossCheck:
    """The read list against an L3 option list as a WHOLE: same count, same order, every line
    equal (an option drawn in colour must read as coloured)."""
    if full.reason != "ok" or full.lines is None:
        return CrossCheck(False, f"list_{full.reason}")
    vis = visible_options(options)
    if len(vis) != len(full.lines):
        return CrossCheck(False, f"count {len(full.lines)} != {len(vis)}")
    for k, (line, (_, opt)) in enumerate(zip(full.lines, vis, strict=True)):
        want = visible_text(opt)
        got = line.key
        if (want is None and got != COLOURED) or (want is not None and got != want):
            return CrossCheck(False, f"line {k + 1} differs")
    return CrossCheck(True, "ok", tuple(i for i, _ in vis))


def line_of(full: FullList, option: str) -> int | None:
    """The index (into the listed lines) of the ONE line that reads ``option``; None otherwise.
    Coloured options are never found."""
    want = visible_text(option)
    if want is None or full.lines is None:
        return None
    hits = [k for k, ln in enumerate(full.lines) if ln.key == want]
    return hits[0] if len(hits) == 1 else None


def align(snapshot: MenuSnapshot, full: FullList) -> int | None:
    """The ONE top index at which the snapshot's lines fit the full list (every comparable line
    equal, at least one compared); None otherwise."""
    if full.lines is None:
        return None
    cur = _trim(snapshot)
    if isinstance(cur, str):
        return None
    fits = [t for t in range(0, len(full.lines) - len(cur) + 1)
            if _agrees(list(full.lines), cur, t)]  # fmt: skip
    if snapshot.lines and not snapshot.can_scroll_up:
        fits = [t for t in fits if t == 0]
    if not snapshot.can_scroll_down:
        fits = [t for t in fits if t + len(cur) == len(full.lines)]
    return fits[0] if len(fits) == 1 else None


# --- fitting (host side: scripts/talk_calibrate.py, and the tests) ------------------------------


def label_row(p: Gray, text: str) -> list[tuple[str, int, int]] | str:
    """(char, start, end) of every glyph of a row known to show ``text`` (visible, uncoloured),
    when its ink runs are exactly its non-space characters; else why not."""
    chars = [c for c in text if c != " "]
    runs = ink_runs(p >= INK_P)
    if len(runs) != len(chars):
        return "run_count"
    return [(c, a, b) for c, (a, b) in zip(chars, runs, strict=True)]


def word_gaps(text: str, placed: Sequence[tuple[str, int, int]]) -> list[tuple[int, int]]:
    """(gap, spaces) between consecutive placed glyphs of ``text``."""
    spaces: list[int] = []
    n = 0
    for c in text.strip(" "):
        if c == " ":
            n += 1
        else:
            spaces.append(n)
            n = 0
    return [(placed[k][1] - placed[k - 1][2], spaces[k]) for k in range(1, len(placed))]


def fit_menu_glyphs(rows: Sequence[npt.NDArray[np.uint8]], texts: Sequence[str],
                    tail: float = 0.1) -> tuple[MenuGlyphs, dict[str, Any]]:  # fmt: skip
    """Templates and rules from rows labelled with the option they show. Fixed rules, set before
    any held-out row is read:
      * a row is used only when its ink runs are exactly its non-space characters (touching or
        two-part glyphs are skipped, counted) and it has no foreign pixel;
      * per character the template is the mean of its instances of the most common width; an
        instance another character's template fits at least as well is dropped once, then
        everything is re-fitted;
      * worst true = the (100 - tail)th percentile of the true scores (at least SCORE_FLOOR);
        closest pair = the smallest score between two different characters' templates of one
        width; max_score = their geometric middle, at most 3x worst true; min_margin = half the
        tail-th percentile of the true margins;
      * gaps: in-word and one-space gaps as seen; they must not overlap.
    Returns (templates, stats)."""
    if len(rows) != len(texts) or not rows:
        raise ValueError("one text per row, at least one row")
    skipped: dict[str, int] = {}
    inst: dict[str, list[Gray]] = {}
    gaps: dict[int, set[int]] = {0: set(), 1: set()}
    lead: dict[str, list[int]] = {}
    used_rows = 0

    def skip(why: str) -> None:
        skipped[why] = skipped.get(why, 0) + 1

    for row, raw in zip(rows, texts, strict=True):
        text = visible_text(raw)
        if text is None:
            skip("coloured_label")
            continue
        if not text.strip():
            skip("empty_label")
            continue
        p, foreign, bg = ink_map(row)
        if bg is None or int(foreign.sum()) > FOREIGN_MAX:
            skip("no_background" if bg is None else "foreign_pixels")
            continue
        placed = label_row(p, text.lstrip(" "))
        if isinstance(placed, str):
            skip(placed)
            continue
        used_rows += 1
        for c, a, b in placed:
            inst.setdefault(c, []).append(p[:, a:b].copy())
        lead.setdefault(placed[0][0], []).append(placed[0][1])
        for gap, n in word_gaps(text, placed):
            if n in gaps:
                gaps[n].add(gap)
    if not inst:
        raise ValueError(f"no row could be placed: {skipped}")
    width_outliers = 0
    for c, xs in inst.items():
        widths = [x.shape[1] for x in xs]
        mode = max(set(widths), key=widths.count)
        width_outliers += sum(1 for w in widths if w != mode)
        inst[c] = [x for x in xs if x.shape[1] == mode]

    def build(instances: Mapping[str, Sequence[Gray]]) -> MenuGlyphs:
        chars = "".join(sorted(c for c, xs in instances.items() if xs))
        wmax = max(instances[c][0].shape[1] for c in chars)
        bitmaps = np.zeros((len(chars), BAND_H, wmax), np.float32)
        widths = np.zeros(len(chars), np.int64)
        counts = np.zeros(len(chars), np.int64)
        for i, c in enumerate(chars):
            m = np.stack(instances[c]).mean(axis=0)
            bitmaps[i, :, : m.shape[1]] = m
            widths[i], counts[i] = m.shape[1], len(instances[c])
        return MenuGlyphs(chars, bitmaps, widths, counts, (), (), {}, (0, 0), np.inf, 0.0)

    def scores_of(x: Gray, t: MenuGlyphs) -> dict[str, float]:
        out: dict[str, float] = {}
        for i in np.flatnonzero(t.widths == x.shape[1]):
            d = np.asarray(x, np.float32) - t.bitmap(int(i))
            out[t.chars[int(i)]] = float((d * d).sum())
        return out

    first = build(inst)
    dropped: dict[str, int] = {}
    for c, xs in inst.items():
        keep = []
        for x in xs:
            s = scores_of(x, first)
            others = [v for k, v in s.items() if k != c]
            keep.append(not others or s[c] < min(others))
        dropped[c] = keep.count(False)
        inst[c] = [x for x, k in zip(xs, keep, strict=True) if k]
    t = build(inst)
    true_s, margins = [], []
    for c, xs in inst.items():
        for x in xs:
            s = scores_of(x, t)
            true_s.append(s[c])
            others = [v for k, v in s.items() if k != c]
            if others:
                margins.append(min(others) - s[c])
    pair = float("inf")
    for i in range(len(t.chars)):
        for j in range(i + 1, len(t.chars)):
            if t.widths[i] == t.widths[j]:
                pair = min(pair, float(((t.bitmap(i) - t.bitmap(j)) ** 2).sum()))
    worst_true = max(float(np.percentile(true_s, 100 - tail)), SCORE_FLOOR)
    if not np.isfinite(pair):
        pair = 9.0 * worst_true  # no two characters share a width: 3x worst true below
    max_score = min(float(np.sqrt(worst_true * pair)), 3.0 * worst_true)
    min_margin = 0.5 * float(np.percentile(margins, tail)) if margins else 0.5 * pair
    if gaps[0] & gaps[1]:
        raise ValueError(f"in-word gaps {sorted(gaps[0])} overlap space gaps {sorted(gaps[1])}")
    if not gaps[0] or not gaps[1]:
        raise ValueError("the labelled rows show no in-word gap or no space")
    leads = {c: max(set(v), key=v.count) for c, v in lead.items()}
    all_leads = [x for v in lead.values() for x in v]
    glyphs = replace(
        t, gaps0=tuple(sorted(gaps[0])), gaps1=tuple(sorted(gaps[1])), lead=leads,
        lead_range=(min(all_leads), max(all_leads)), max_score=max_score, min_margin=min_margin,
    )  # fmt: skip
    stats = {
        "rows": len(rows), "used_rows": used_rows, "skipped": skipped,
        "chars": glyphs.chars, "counts": dict(zip(glyphs.chars, map(int, glyphs.counts),
                                                  strict=True)),
        "width_outliers": width_outliers, "dropped_mislabelled": dropped,
        "worst_true": worst_true, "closest_pair": pair, "max_score": max_score,
        "min_margin": min_margin, "gaps0": list(glyphs.gaps0), "gaps1": list(glyphs.gaps1),
        "lead_range": list(glyphs.lead_range),
    }  # fmt: skip
    return glyphs, stats
