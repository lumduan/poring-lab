"""The weight readout from pixels (loot@1 P1): the Basic Information window's weight line -> (N, M).

The client draws, at the bottom of the Basic Information window, a label, then the weight as
"N / M", then the zeny. In the frozen 1280x720 layout (RDP) the text is a crisp bitmap font,
black on the window's opaque white, every digit on a 7 px pitch (6 ink columns + 1 blank), glyph
rows 118-129 when the window sits at (0, 0). The line is NOT laid out from a fixed left edge
(measured 2026-10-08): '/' and M stay put, N ends at the same column, and the LABEL moves with N's
digit count (its first column was 53 at "90", 50 at "205"). So no column is assumed: the label is
searched along the whole line and the parse starts right of wherever it is.

This module reads that line from the game region (1280x720, BGR) and nothing else: pixels in,
two integers out -- or None. It never guesses: an absent window, a covered or partly hidden line,
an unexplained mark or an unknown glyph is None, with a reason.

Where: the ``weight_line`` element of the UI anchor map (``poring_env.ui_anchors``, inside
``basic_info``): by default at the window's measured origin; a caller that LOCATED the window
passes the origin.

How (numpy only):
  1. The rect's grey is mapped to an ink probability: 0 at THIS frame's paper (the rect's median:
     the window's white), 1 at the calibrated stroke grey. A rect whose median is not white
     (``MIN_PAPER``) shows no window: None.
  2. The label is found by its template (cut locally from banked frames: client pixels, never
     committed) at any column of the line, within ``LABEL_SEARCH`` rows of its calibrated row; it
     fixes the glyph row and where the numbers may start.
  3. Every symbol template (0-9 and '/', the mean ink probability of many instances, cut by
     scripts/weight_calibrate.py into data/ui_anchors/weight_glyphs.npz, gitignored) is scored at
     every column right of the label: the sum of squared differences, roughly how many pixels
     disagree. The glyphs are the best non-overlapping positions under ``max_score``.
  4. They must read: digits on the pitch (N), '/', digits on the pitch (M); then
     ``AFTER_BLANK`` blank columns, and the zeny text's first ink exactly ``tail_gap`` px after
     M's last cell (calibrated: 12) -- so a digit hidden at M's end cannot leave a shorter
     number. Every MARK (a pixel ``MARK_PROB`` or more toward the stroke grey: a grey occluder,
     not just black ink; the background of the span stays under 0.06 on the banked frames) from
     the label to there must lie inside a read glyph, each glyph must beat the runner-up symbol at
     its place by ``min_margin``, and no number may have a leading zero.
  5. By default the reader refuses templates that lack any symbol ("incomplete_templates"): an
     unseen digit could otherwise pass for a similar seen one (8 for 9 or 0). Only tests and the
     calibration report pass ``allow_incomplete=True``.

The value's confidence (0..1) is the weakest glyph's: min(1 - score / max_score, margin /
(2 * min_margin) capped at 1). A runtime check should also require the SAME value on two fresh
frames (``stable_value``): the RDP codec refines a changed region over a few frames.

The readout's unit is the client's (rAthena weight / 10): what one step of the number means in
rAthena units is MEASURED, not assumed (scripts/weight_resolution.py).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from poring_env.ui_anchors import CAPTURE_ORIGINS, ELEMENTS

Gray = npt.NDArray[np.float32]

ELEMENT = "weight_line"
DEFAULT_TEMPLATES = Path("data/ui_anchors/weight_glyphs.npz")
FORMAT_VERSION = 1
SYMBOLS = "0123456789/"
SLASH = SYMBOLS.index("/")
MIN_PAPER = 180.0  # the rect's median grey must be the window's white, or nothing is read
INK_PROB = 0.5  # a pixel at least this inked is a stroke (ink columns, calibration runs)
LABEL_SEARCH = 2  # rows the label may sit off its calibrated row (columns: the whole line)
AFTER_BLANK = 3  # blank columns required right after the last digit's cell
MARK_PROB = 0.15  # any pixel this inked inside the parsed span must belong to a read glyph
TAIL_SLACK = 1  # px the zeny text's first ink may sit off tail_gap
FULL_INK_W = 6  # ink columns of a full-width digit: it starts at its cell's left column
SCORE_FLOOR = 0.5  # a crisp font's true scores can be ~0: thresholds never go below this


@dataclass(frozen=True, slots=True)
class Geometry:
    """Where things sit in the ``weight_line`` rect (measured 2026-10-08 on RDP frames)."""

    label: tuple[int, int, int, int] = (52, 3, 49, 14)  # x (nominal: at "90"), y, w, h
    cell: tuple[int, int] = (14, 7)  # (h, w) of a glyph cell; its top row is the label's
    pitch: int = 7
    tail_gap: int = 12  # from M's last cell to the zeny text's first ink


GEOMETRY = Geometry()


def _box() -> tuple[int, int, int, int]:
    box = ELEMENTS[ELEMENT].box
    if box is None:
        raise ValueError(f"{ELEMENT} has no fixed box")
    return box


def rect_at(origin: tuple[int, int] | None = None) -> tuple[int, int, int, int]:
    """The line's rect (x, y, w, h) in game-region pixels when ``basic_info`` sits at ``origin``
    (default: its measured origin)."""
    ox, oy = CAPTURE_ORIGINS[ELEMENTS[ELEMENT].window] if origin is None else origin
    dx, dy, w, h = _box()
    return ox + dx, oy + dy, w, h


def to_gray(bgr: npt.NDArray[np.uint8]) -> Gray:
    f = bgr[..., :3].astype(np.float32)
    return np.asarray(0.114 * f[..., 0] + 0.587 * f[..., 1] + 0.299 * f[..., 2], np.float32)


def ink_probability(gray: Gray, ink: float) -> tuple[Gray, float]:
    """(probability map, paper grey): 0 at this rect's paper, 1 at the stroke grey. An all-zero
    map when the rect is not the window's white (the caller refuses on the paper value)."""
    paper = float(np.median(gray))
    if paper < MIN_PAPER or paper - ink < 40:
        return np.zeros(gray.shape, np.float32), paper
    return np.asarray(np.clip((paper - gray) / (paper - ink), 0, 1), np.float32), paper


@dataclass(frozen=True, slots=True)
class WeightGlyphs:
    """Symbol and label templates (ink probability) and the acceptance rules."""

    mean: Gray  # (11, h, w): 0-9 then '/'
    counts: npt.NDArray[np.int64]  # (11,): training instances; 0 = never seen
    label: Gray  # (h, w): the label
    ink: float  # grey of a typical stroke: probability 1
    max_score: float  # a glyph scores at most this ...
    min_margin: float  # ... and beats the runner-up symbol at its place by this much
    label_max: float  # the label scores at most this at its best place
    geometry: Geometry = GEOMETRY
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def missing(self) -> str:
        """The symbols no calibration frame showed."""
        return "".join(s for s, c in zip(SYMBOLS, self.counts, strict=True) if c == 0)

    @property
    def complete(self) -> bool:
        return not self.missing

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        g = self.geometry
        params = [self.ink, self.max_score, self.min_margin, self.label_max, *g.label, *g.cell,
                  g.pitch, g.tail_gap]  # fmt: skip
        np.savez_compressed(
            path,
            version=np.int64(FORMAT_VERSION),
            mean=self.mean.astype(np.float32),
            counts=self.counts.astype(np.int64),
            label=self.label.astype(np.float32),
            params=np.array(params, np.float64),
            meta=np.array(json.dumps(self.meta, sort_keys=True)),
        )


def load_weight_glyphs(path: Path = DEFAULT_TEMPLATES) -> WeightGlyphs:
    """The calibrated templates (scripts/weight_calibrate.py). Plain arrays only: never
    unpickled."""
    with np.load(path, allow_pickle=False) as z:
        version = int(z["version"])
        if version != FORMAT_VERSION:
            raise ValueError(f"{path}: format {version}, this reader needs {FORMAT_VERSION}")
        mean = np.asarray(z["mean"], np.float32)
        counts = np.asarray(z["counts"], np.int64)
        label = np.asarray(z["label"], np.float32)
        p = [float(v) for v in z["params"]]
        meta = json.loads(str(z["meta"]))
    if mean.ndim != 3 or mean.shape[0] != len(SYMBOLS) or counts.shape != (len(SYMBOLS),):
        raise ValueError(f"{path}: expected ({len(SYMBOLS)}, h, w) templates and counts")
    if len(p) != 12:
        raise ValueError(f"{path}: expected 12 parameters, got {len(p)}")
    lx, ly, lw, lh, ch, cw, pitch, tail = (int(v) for v in p[4:12])
    geometry = Geometry(label=(lx, ly, lw, lh), cell=(ch, cw), pitch=pitch, tail_gap=tail)
    if label.shape != (lh, lw) or mean.shape[1:] != (ch, cw):
        raise ValueError(f"{path}: template shapes disagree with the stored geometry")
    return WeightGlyphs(mean, counts, label, ink=p[0], max_score=p[1], min_margin=p[2],
                        label_max=p[3], geometry=geometry, meta=meta)  # fmt: skip


@dataclass(frozen=True, slots=True)
class Glyph:
    x: int  # the cell's left column, in band pixels (the first column right of the label)
    symbol: str
    score: float
    margin: float  # the runner-up symbol's score minus this one's


@dataclass(frozen=True, slots=True)
class WeightReading:
    value: tuple[int, int] | None  # (N, M) as shown, or None
    reason: str  # "ok", or why the line was not read
    confidence: float = 0.0
    glyphs: tuple[Glyph, ...] = ()
    label_at: tuple[int, int] | None = None  # the label's top-left in rect pixels


def find_label(prob: Gray, glyphs: WeightGlyphs) -> tuple[tuple[int, int], float] | None:
    """The label's best place (any column; within ``LABEL_SEARCH`` rows of its calibrated row)
    and its score; None when the rect cannot hold it."""
    _, ly, lw, lh = glyphs.geometry.label
    best: tuple[tuple[int, int], float] | None = None
    for y in range(max(0, ly - LABEL_SEARCH), min(ly + LABEL_SEARCH, prob.shape[0] - lh) + 1):
        if prob.shape[1] < lw:
            break
        windows = np.lib.stride_tricks.sliding_window_view(prob[y : y + lh], (lh, lw))[0]
        scores = ((windows - glyphs.label) ** 2).sum(axis=(1, 2))
        x = int(np.argmin(scores))
        if best is None or float(scores[x]) < best[1]:
            best = ((x, y), float(scores[x]))
    return best


def label_left(prob: Gray, geometry: Geometry = GEOMETRY) -> int | None:
    """Calibration only: the label template's column in a rect known to show the line -- one
    column left of the first ink on the label's rows (nothing is drawn left of the label)."""
    _, ly, lw, lh = geometry.label
    cols = np.flatnonzero((prob[ly : ly + lh] >= INK_PROB).any(axis=0))
    if not cols.size or cols[0] < 1 or cols[0] - 1 + lw > prob.shape[1]:
        return None
    return int(cols[0]) - 1


def band_scores(band: Gray, glyphs: WeightGlyphs) -> npt.NDArray[np.float64]:
    """(11, cols): each symbol's score at every cell position along the band (inf: a symbol never
    seen in calibration, or a band narrower than a cell)."""
    h, w = glyphs.geometry.cell
    if band.shape[0] != h or band.shape[1] < w:
        return np.full((len(SYMBOLS), 0), np.inf)
    windows = np.lib.stride_tricks.sliding_window_view(band.astype(np.float64), (h, w))[0]
    out = np.full((len(SYMBOLS), windows.shape[0]), np.inf)
    for i in range(len(SYMBOLS)):
        if glyphs.counts[i] > 0:
            out[i] = ((windows - glyphs.mean[i]) ** 2).sum(axis=(1, 2))
    return out


def _accept(scores: npt.NDArray[np.float64], glyphs: WeightGlyphs) -> list[Glyph]:
    """The best non-overlapping positions under max_score, left to right."""
    order = np.argsort(scores, axis=0, kind="stable")
    s1 = np.take_along_axis(scores, order[:1], axis=0)[0]
    s2 = np.take_along_axis(scores, order[1:2], axis=0)[0]
    pitch = glyphs.geometry.pitch
    accepted: list[Glyph] = []
    for x in np.argsort(s1, kind="stable"):
        if not s1[x] <= glyphs.max_score:
            break
        if any(abs(int(x) - g.x) < pitch for g in accepted):
            continue
        sym = SYMBOLS[int(order[0, x])]
        accepted.append(Glyph(int(x), sym, float(s1[x]), float(s2[x] - s1[x])))
    return sorted(accepted, key=lambda g: g.x)


def _numbers(tokens: Sequence[Glyph], pitch: int) -> tuple[list[Glyph], Glyph, list[Glyph]] | None:
    """digits on the pitch, '/', digits on the pitch -- from the first token; None otherwise."""
    n: list[Glyph] = []
    i = 0
    while i < len(tokens) and tokens[i].symbol != "/":
        if n and tokens[i].x - n[-1].x != pitch:
            return None
        n.append(tokens[i])
        i += 1
    if not n or i >= len(tokens) - 1:
        return None
    slash = tokens[i]
    m = [tokens[i + 1]]
    if m[0].symbol == "/":
        return None
    for g in tokens[i + 2 :]:
        if g.symbol == "/" or g.x - m[-1].x != pitch:
            break
        m.append(g)
    return n, slash, m


def read_rect(gray: Gray, glyphs: WeightGlyphs, *, allow_incomplete: bool = False) -> WeightReading:  # noqa: PLR0911
    """Parse the line from its rect (grey, rect pixels). See the module docstring."""
    if not allow_incomplete and not glyphs.complete:
        return WeightReading(None, "incomplete_templates")
    prob, paper = ink_probability(gray, glyphs.ink)
    if paper < MIN_PAPER or not prob.any():
        return WeightReading(None, "no_window")
    found = find_label(prob, glyphs)
    if found is None:
        return WeightReading(None, "rect_too_small")
    (lx, ly), label_score = found
    if label_score > glyphs.label_max:
        return WeightReading(None, "no_label", label_at=(lx, ly))
    h, w = glyphs.geometry.cell
    pitch = glyphs.geometry.pitch
    band = prob[ly : ly + h, lx + glyphs.geometry.label[2] :]
    scores = band_scores(band, glyphs)
    if scores.shape[1] == 0:
        return WeightReading(None, "rect_too_small", label_at=(lx, ly))
    tokens = _accept(scores, glyphs)
    parsed = _numbers(tokens, pitch)
    if parsed is None:
        return WeightReading(None, "layout", glyphs=tuple(tokens), label_at=(lx, ly))
    n, slash, m = parsed
    used = (*n, slash, *m)
    end = m[-1].x + w + AFTER_BLANK
    if end > band.shape[1]:
        return WeightReading(None, "cut_off", glyphs=used, label_at=(lx, ly))
    ink_cols = np.flatnonzero((band[:, :end] >= MARK_PROB).any(axis=0))
    covered = np.zeros(end, bool)
    for g in used:
        covered[g.x : g.x + w] = True
    if ink_cols.size and not covered[ink_cols].all():
        return WeightReading(None, "unexplained_ink", glyphs=used, label_at=(lx, ly))
    tail = tail_column(band, m[-1].x + w)
    if tail is None or abs(tail - m[-1].x - glyphs.geometry.tail_gap) > TAIL_SLACK:
        return WeightReading(None, "tail_mismatch", glyphs=used, label_at=(lx, ly))
    if any(g.margin < glyphs.min_margin for g in used):
        return WeightReading(None, "ambiguous", glyphs=used, label_at=(lx, ly))
    if any(len(num) > 1 and num[0].symbol == "0" for num in (n, m)):
        return WeightReading(None, "leading_zero", glyphs=used, label_at=(lx, ly))
    value = (int("".join(g.symbol for g in n)), int("".join(g.symbol for g in m)))
    conf = min(
        min(1.0, max(0.0, 1 - g.score / glyphs.max_score),
            g.margin / (2 * glyphs.min_margin) if glyphs.min_margin > 0 else 1.0)
        for g in used
    )  # fmt: skip
    return WeightReading(value, "ok", float(conf), used, (lx, ly))


BADGE_RED = 60  # R - max(G, B) of the client's red notice badge (the window and the text: < 20)


def unbadge(region_bgr: npt.NDArray[np.uint8]) -> npt.NDArray[np.uint8]:
    """PURE (2026-10-19): the client's red NOTICE BADGE ("N") repainted white. With the menu icon
    panel collapsed (the hunting layout) the client draws it on Basic Info's bottom edge, under the
    weight digits (v43 run 2's start: "unexplained_ink"). Its red box's bounding box (its white
    "N" inside) becomes the window's white; the dark text is never red. No red: unchanged."""
    px = region_bgr[..., :3].astype(np.int16)
    red = (px[..., 2] - np.maximum(px[..., 0], px[..., 1])) >= BADGE_RED
    if not red.any():
        return region_bgr
    ys, xs = np.nonzero(red)
    out = region_bgr.copy()
    out[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1, :3] = 255
    return out


def read_weight(
    game_region_bgr: npt.NDArray[np.uint8],
    glyphs: WeightGlyphs,
    origin: tuple[int, int] | None = None,
    *,
    allow_incomplete: bool = False,
) -> WeightReading:
    """The readout with its reason and confidence. ``origin``: where ``basic_info`` sits (game
    region pixels); default its measured origin. The notice badge is repainted first (unbadge)."""
    x, y, w, h = rect_at(origin)
    region = game_region_bgr[y : y + h, x : x + w]
    if region.shape[0] != h or region.shape[1] != w:
        return WeightReading(None, "rect_outside_frame")
    return read_rect(to_gray(unbadge(region)), glyphs, allow_incomplete=allow_incomplete)


def tail_column(band: Gray, start: int) -> int | None:
    """The first column at or after ``start`` holding a mark (the zeny text); None if none."""
    cols = np.flatnonzero((band[:, start:] >= MARK_PROB).any(axis=0))
    return int(cols[0]) + start if cols.size else None


def stable_value(readings: Sequence[WeightReading], n: int = 2) -> tuple[int, int] | None:
    """The value when the last ``n`` readings (fresh frames, oldest first) all read it; else
    None."""
    last = list(readings)[-n:]
    if len(last) < n or any(r.value is None for r in last):
        return None
    first = last[0].value
    return first if all(r.value == first for r in last) else None


# --- fitting (host side: scripts/weight_calibrate.py, and the tests) ----------------------------


def ink_runs(band: Gray) -> list[tuple[int, int]]:
    """[start, end) of every run of ink columns in a band (one blank column separates glyphs in
    this font)."""
    cols = (band >= INK_PROB).any(axis=0)
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for i, c in enumerate(cols):
        if c and start is None:
            start = i
        elif not c and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(cols)))
    return runs


def label_cells(band: Gray, value: tuple[int, int], pitch: int = 7) -> list[tuple[str, int]] | str:
    """(symbol, cell left) of every glyph of a band known to show ``value`` -- or why not. The
    numbers' cells are placed on the pitch from their full-width digits (ink starts at the cell's
    left); '/' is cut one column left of its ink."""
    n, m = (str(v) for v in value)
    runs = ink_runs(band)
    need = len(n) + 1 + len(m)
    if len(runs) < need:
        return "too_few_runs"
    out: list[tuple[str, int]] = []
    k = 0
    for i, text in enumerate((n, m)):
        part = runs[k : k + len(text)]
        starts = {a - pitch * j for j, (a, b) in enumerate(part) if b - a == FULL_INK_W}
        if len(starts) != 1:
            return "misaligned" if starts else "no_full_width_digit"
        x0 = starts.pop()
        for j, (a, b) in enumerate(part):
            left = x0 + pitch * j
            if a < left or b > left + FULL_INK_W:
                return "misaligned"
        out += [(ch, x0 + pitch * j) for j, ch in enumerate(text)]
        k += len(text)
        if i == 0:
            out.append(("/", runs[k][0] - 1))
            k += 1
    return out


def fit_weight_glyphs(
    grays: Sequence[Gray],
    values: Sequence[tuple[int, int]],
    *,
    geometry: Geometry = GEOMETRY,
    tail: float = 0.1,
) -> tuple[WeightGlyphs, dict[str, Any]]:
    """Templates and thresholds from line rects (grey) labelled with the shown value. Fixed rules,
    set before any held-out frame is read:
      * ink: the median grey of the label's stroke pixels (darker than half the paper);
      * per symbol the template is the mean cell (label_cells places them); an instance another
        symbol's template fits at least as well is dropped once, then everything is re-fitted;
      * worst true glyph = the (100 - tail)th percentile of the true scores; best wrong = the
        tail-th percentile of the best score at every OTHER position of the parsed span (spaces,
        straddled glyphs: >= 2 px from a true cell); smallest margin = the tail-th percentile of
        the true glyphs' margins over the runner-up symbol;
      * max_score = the geometric middle of max(worst true, SCORE_FLOOR) and best wrong, at most
        3x that; min_margin = half the smallest margin;
      * label_max = the geometric middle of max(worst true label, SCORE_FLOOR) and the label's
        own ink mass (what an empty place scores).
    Frames whose paper is not white, or whose glyphs cannot be placed, are skipped (counted).
    Returns (templates, stats)."""
    if len(grays) != len(values) or not grays:
        raise ValueError("one value per rect, at least one rect")
    _, ly, lw, lh = geometry.label
    h, w = geometry.cell
    papers = [float(np.median(g)) for g in grays]
    strokes = np.concatenate([
        g[ly : ly + lh][g[ly : ly + lh] < p / 2]
        for g, p in zip(grays, papers, strict=True) if p >= MIN_PAPER
    ] or [np.zeros(0, np.float32)])  # fmt: skip
    if strokes.size == 0:
        raise ValueError("no rect shows the window's white paper")
    ink = float(np.median(strokes))
    skipped: dict[str, int] = {}
    labels: list[Gray] = []
    cells: dict[int, list[Gray]] = {i: [] for i in range(len(SYMBOLS))}
    placed: list[tuple[Gray, list[tuple[str, int]]]] = []
    tails: dict[int, int] = {}
    for g, value in zip(grays, values, strict=True):
        prob, paper = ink_probability(g, ink)
        if paper < MIN_PAPER:
            skipped["no_window"] = skipped.get("no_window", 0) + 1
            continue
        lx = label_left(prob, geometry)
        if lx is None:
            skipped["no_label"] = skipped.get("no_label", 0) + 1
            continue
        band = prob[ly : ly + h, lx + lw :]
        where = label_cells(band, value, geometry.pitch)
        if isinstance(where, str):
            skipped[where] = skipped.get(where, 0) + 1
            continue
        labels.append(prob[ly : ly + lh, lx : lx + lw])
        for sym, left in where:
            cells[SYMBOLS.index(sym)].append(band[:, left : left + w])
        placed.append((band, where))
        last = max(left for sym, left in where if sym != "/")
        tail_x = tail_column(band, last + w)
        if tail_x is not None:
            tails[tail_x - last] = tails.get(tail_x - last, 0) + 1
    if not placed:
        raise ValueError(f"no rect could be placed: {skipped}")
    if tails:  # the zeny text's offset after M, as seen (the most common one)
        geometry = replace(geometry, tail_gap=max(tails, key=lambda k: tails[k]))

    def fit(instances: dict[int, list[Gray]], label_max: float = np.inf) -> WeightGlyphs:
        mean = np.zeros((len(SYMBOLS), h, w), np.float32)
        counts = np.zeros(len(SYMBOLS), np.int64)
        for i, inst in instances.items():
            if inst:
                mean[i] = np.stack(inst).mean(axis=0)
                counts[i] = len(inst)
        return WeightGlyphs(mean, counts, np.stack(labels).mean(axis=0).astype(np.float32), ink,
                            max_score=np.inf, min_margin=0.0, label_max=label_max,
                            geometry=geometry)  # fmt: skip

    def cell_scores(inst: Sequence[Gray], t: WeightGlyphs) -> npt.NDArray[np.float64]:
        return np.stack([band_scores(c, t)[:, 0] for c in inst]) if inst else np.zeros((0, 11))

    first = fit(cells)
    dropped: dict[str, int] = {}
    for i in range(len(SYMBOLS)):
        if cells[i]:
            s = cell_scores(cells[i], first)
            keep = s[:, i] < np.delete(s, i, axis=1).min(axis=1)
            dropped[SYMBOLS[i]] = int((~keep).sum())
            cells[i] = [c for c, k in zip(cells[i], keep, strict=True) if k]
    t = fit(cells)
    true_s, margins = [], []
    for i in range(len(SYMBOLS)):
        if cells[i]:
            s = cell_scores(cells[i], t)
            true_s.append(s[:, i])
            margins.append(np.delete(s, i, axis=1).min(axis=1) - s[:, i])
    true_all, margin_all = np.concatenate(true_s), np.concatenate(margins)
    wrong: list[float] = []
    for band, where in placed:
        scores = band_scores(band, t).min(axis=0)
        lefts = np.array([left for _, left in where])
        span = min(scores.shape[0], max(lefts) + w + AFTER_BLANK)
        for x in range(span):
            if np.abs(lefts - x).min() >= 2:
                wrong.append(float(scores[x]))
    worst_true = max(float(np.percentile(true_all, 100 - tail)), SCORE_FLOOR)
    best_wrong = float(np.percentile(wrong, tail)) if wrong else np.inf
    smallest_margin = float(np.percentile(margin_all, tail))
    label_scores = np.array([float(((lab - t.label) ** 2).sum()) for lab in labels])
    worst_label = max(float(np.percentile(label_scores, 100 - tail)), SCORE_FLOOR)
    label_mass = float((t.label**2).sum())
    max_score = min(float(np.sqrt(worst_true * best_wrong)), 3.0 * worst_true)
    templates = replace(
        t, max_score=max_score, min_margin=0.5 * smallest_margin,
        label_max=float(np.sqrt(worst_label * label_mass)),
    )  # fmt: skip
    stats = {
        "frames": len(grays), "placed": len(placed), "skipped": skipped,
        "counts": dict(zip(SYMBOLS, (int(c) for c in t.counts), strict=True)),
        "missing": templates.missing, "dropped_mislabelled": dropped, "ink": ink,
        "worst_true": worst_true, "best_wrong": best_wrong, "smallest_margin": smallest_margin,
        "true_score_p50_p99_max": [float(np.percentile(true_all, q)) for q in (50, 99, 100)],
        "worst_label": worst_label, "label_mass": label_mass,
        "max_score": templates.max_score, "min_margin": templates.min_margin,
        "label_max": templates.label_max, "tail_gaps_seen": tails,
        "tail_gap": templates.geometry.tail_gap,
    }  # fmt: skip
    return templates, stats
