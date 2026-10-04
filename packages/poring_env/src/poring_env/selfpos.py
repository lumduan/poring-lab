"""Self-localisation from pixels (Phase 3, T0): our own cell from the minimap's coordinate readout.

The RO client draws, under the minimap, a magnifier icon and the player's cell as "x y" in small
white digits with a black drop shadow on their left, over a translucent strip the scene shows
through. This module reads that readout from the game region (1280x720, BGR) and nothing else:
pixels in, two integers out -- or None. It never guesses: an unreadable, partly hidden or
ambiguous readout is None, and so is a map where the client draws no minimap (indoor maps on the
lab's client).

Where: the ``minimap_xy`` element of the UI anchor map (ADR-0011, ``poring_env.ui_anchors``),
inside the ``minimap`` window: by default at the window's measured origin; a caller that LOCATED
the window passes the rect from ``rect_at(origin)``.

How (numpy only, no OpenCV, no GPU):
  1. Grey is mapped to a stroke probability: 0 at THIS frame's strip background (the median of
     the rect's pixels that are neither stroke nor shadow: the scene shows through, from a dark
     field to prontera's bright paving), 1 at the typical stroke (calibrated). A half-bright
     pixel is half a stroke for every digit alike: a missing stroke and an extra one cost the
     same, so a glyph caught between two digits (a codec frame in mid-change) scores close for
     both instead of reading as whichever has fewer strokes.
  2. Every digit template (the mean probability of many training instances, cut by
     scripts/selfpos_calibrate.py into data/ui_anchors/minimap_digits.npz, gitignored:
     client-derived) is scored at every cell position of the readout rect: the sum of squared
     differences, i.e. roughly how many pixels disagree.
  3. The glyphs are the best non-overlapping positions under ``max_score``, on one baseline.
     Every column where a stroke starts (a bright pixel right of a black shadow pixel) must lie
     inside a read glyph -- nothing on the readout is left unexplained, while a bright scene
     showing through the strip has no shadow -- and each glyph's digit must beat the runner-up
     at the same place by ``min_margin``.
  4. They must form exactly two numbers: ``pitch`` px from digit to digit, 1-3 digits each, no
     leading zero, the first starting at ``text_left`` and the second ``number_gap`` px after the
     first one's last cell (both measured in calibration; None = not pinned).
Any failure is None with a reason (``read_minimap``), for evaluation and logs.

Known blind spot of a single frame: a DARK occluder over the y number's last digit(s) leaves a
shorter, well-formed number (an outlined one, like the cursor, is caught by step 3; a hidden x
digit or the y number's first by step 4). The UI is drawn over the scene, so only another window
could do it; the agent's step check (a cell moves by at most one per step) catches what is left.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from poring_env.ui_anchors import CAPTURE_ORIGINS, ELEMENTS

Gray = npt.NDArray[np.float32]

ELEMENT = "minimap_xy"
DEFAULT_TEMPLATES = Path("data/ui_anchors/minimap_digits.npz")
FORMAT_VERSION = 1
MAX_DIGITS = 3  # RO maps are under 1000 cells a side
NOT_PINNED = -1  # how text_left / number_gap = None is stored
MIN_CONTRAST = 40.0  # strokes must stand this far above the strip, or nothing can be read


def _box() -> tuple[int, int, int, int]:
    box = ELEMENTS[ELEMENT].box
    if box is None:
        raise ValueError(f"{ELEMENT} has no fixed box")
    return box


def default_rect() -> tuple[int, int, int, int]:
    """The readout's rect (x, y, w, h) in game-region pixels at the window's measured origin."""
    return rect_at(CAPTURE_ORIGINS[ELEMENTS[ELEMENT].window])


def rect_at(origin: tuple[int, int]) -> tuple[int, int, int, int]:
    """The readout's rect when the ``minimap`` window sits at ``origin`` (located)."""
    dx, dy, w, h = _box()
    return origin[0] + dx, origin[1] + dy, w, h


def to_gray(bgr: npt.NDArray[np.uint8]) -> Gray:
    f = bgr[..., :3].astype(np.float32)
    return np.asarray(0.114 * f[..., 0] + 0.587 * f[..., 1] + 0.299 * f[..., 2], np.float32)


@dataclass(frozen=True, slots=True)
class DigitTemplates:
    """Per-digit stroke-probability templates of one glyph cell and the acceptance rules."""

    mean: Gray  # (10, h, w): digit d's mean stroke probability per pixel
    counts: npt.NDArray[np.int64]  # (10,): training instances per digit; 0 = never seen
    bright: float  # grey of a typical stroke: probability 1
    max_score: float  # a glyph scores at most this (sum of squared differences)
    min_margin: float  # the runner-up digit at the same place scores at least this much more
    ink_level: float  # a stroke pixel is at least this bright ...
    shadow_level: float  # ... and where a stroke starts, its left neighbour is this dark or more
    stroke_rows: tuple[int, int]  # [first, last) template rows that hold strokes
    pitch: int = 7  # px from one digit to the next within a number
    min_gap: int = 3  # extra px between the two numbers at least (when number_gap is None)
    text_left: int | None = None  # rect column of the first digit cell (left-aligned text)
    number_gap: int | None = None  # px from the x number's last cell to the y number's first
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def shape(self) -> tuple[int, int]:
        return int(self.mean.shape[1]), int(self.mean.shape[2])

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        pins = [NOT_PINNED if v is None else v for v in (self.text_left, self.number_gap)]
        params = [self.bright, self.max_score, self.min_margin, self.ink_level, self.shadow_level,
                  *self.stroke_rows, self.pitch, self.min_gap, *pins]  # fmt: skip
        np.savez_compressed(
            path,
            version=np.int64(FORMAT_VERSION),
            mean=self.mean.astype(np.float32),
            counts=self.counts.astype(np.int64),
            params=np.array(params, np.float64),
            meta=np.array(json.dumps(self.meta, sort_keys=True)),
        )


def load_digit_templates(path: Path = DEFAULT_TEMPLATES) -> DigitTemplates:
    """The calibrated digit templates (scripts/selfpos_calibrate.py). Plain arrays only: the file
    is never unpickled."""
    with np.load(path, allow_pickle=False) as z:
        version = int(z["version"])
        if version != FORMAT_VERSION:
            raise ValueError(f"{path}: format {version}, this reader needs {FORMAT_VERSION}")
        mean = np.asarray(z["mean"], np.float32)
        counts = np.asarray(z["counts"], np.int64)
        p = [float(v) for v in z["params"]]
        meta = json.loads(str(z["meta"]))
    if mean.ndim != 3 or mean.shape[0] != 10 or counts.shape != (10,) or len(p) != 11:
        raise ValueError(f"{path}: expected (10, h, w) templates, 10 counts and 11 parameters")
    left, gap = (None if v == NOT_PINNED else int(v) for v in p[9:11])
    return DigitTemplates(
        mean, counts, bright=p[0], max_score=p[1], min_margin=p[2], ink_level=p[3],
        shadow_level=p[4], stroke_rows=(int(p[5]), int(p[6])), pitch=int(p[7]), min_gap=int(p[8]),
        text_left=left, number_gap=gap, meta=meta,
    )  # fmt: skip


@dataclass(frozen=True, slots=True)
class Glyph:
    x: int  # the cell's left column, rect pixels
    digit: int
    score: float
    margin: float  # the runner-up digit's score minus this one's


@dataclass(frozen=True, slots=True)
class Reading:
    xy: tuple[int, int] | None
    reason: str  # "ok", or why the readout was not read
    glyphs: tuple[Glyph, ...] = ()
    row: int | None = None  # the baseline (template top row) in rect pixels


def strip_background(gray: Gray, ink_level: float, shadow_level: float) -> float:
    """This frame's strip grey: the median of the pixels that are neither stroke nor shadow."""
    scene = gray[(gray < ink_level) & (gray > shadow_level)]
    return float(np.median(scene)) if scene.size else float(np.median(gray))


def stroke_probability(gray: Gray, bright: float, ink_level: float, shadow_level: float) -> Gray:
    """0 at this frame's strip background, 1 at a stroke; all 0 when strokes would not stand out
    (``MIN_CONTRAST``): nothing is then read."""
    bg = strip_background(gray, ink_level, shadow_level)
    if bright - bg < MIN_CONTRAST:
        return np.zeros(gray.shape, np.float32)
    return np.asarray(np.clip((gray - bg) / (bright - bg), 0, 1), np.float32)


def score_maps(prob: Gray, templates: DigitTemplates) -> npt.NDArray[np.float64]:
    """(10, rows, cols): each digit's score at every cell position of a stroke-probability map
    (inf: a digit never seen in calibration)."""
    h, w = templates.shape
    if prob.shape[0] < h or prob.shape[1] < w:
        return np.full((10, 0, 0), np.inf)
    windows = np.lib.stride_tricks.sliding_window_view(prob.astype(np.float64), (h, w))
    out = np.full((10, windows.shape[0], windows.shape[1]), np.inf)
    for d in range(10):
        if templates.counts[d] > 0:
            out[d] = ((windows - templates.mean[d]) ** 2).sum(axis=(2, 3))
    return out


def stroke_starts(gray: Gray, templates: DigitTemplates) -> npt.NDArray[np.bool_]:
    """(rows, cols - 1): where a stroke starts -- a bright pixel right of its black drop shadow.
    Column j is pixel column j + 1. A bright scene showing through the strip (prontera's paving)
    has no black pixel beside it; a glyph, or the cursor, always has."""
    return (gray[:, 1:] >= templates.ink_level) & (gray[:, :-1] <= templates.shadow_level)


def read_rect(gray: Gray, templates: DigitTemplates) -> Reading:  # noqa: PLR0911
    """Parse the readout from its rect (grey, rect pixels). See the module docstring."""
    prob = stroke_probability(gray, templates.bright, templates.ink_level, templates.shadow_level)
    scores = score_maps(prob, templates)
    if scores.shape[1] == 0:
        return Reading(None, "rect_too_small")
    if not np.isfinite(scores).any():
        return Reading(None, "no_templates")
    best = scores.min(axis=0)  # (rows, cols)
    row = int(np.unravel_index(int(np.argmin(best)), best.shape)[0])
    if best[row].min() > templates.max_score:
        return Reading(None, "no_glyph")
    line = scores[:, row, :]  # (10, cols)
    order = np.argsort(line, axis=0, kind="stable")
    s1 = np.take_along_axis(line, order[:1], axis=0)[0]
    s2 = np.take_along_axis(line, order[1:2], axis=0)[0]
    pitch = templates.pitch
    accepted: list[Glyph] = []
    for x in np.argsort(s1, kind="stable"):
        if s1[x] > templates.max_score:
            break
        if any(abs(int(x) - g.x) < pitch for g in accepted):
            continue
        accepted.append(Glyph(int(x), int(order[0, x]), float(s1[x]), float(s2[x] - s1[x])))
    glyphs = tuple(sorted(accepted, key=lambda g: g.x))

    # nothing on the readout that looks like the start of a stroke may be left unexplained
    _, w = templates.shape
    r0, r1 = templates.stroke_rows
    ink_cols = 1 + np.flatnonzero(stroke_starts(gray[row + r0 : row + r1], templates).any(axis=0))
    covered = np.zeros(gray.shape[1], bool)
    for g in glyphs:
        covered[g.x : g.x + w] = True
    if ink_cols.size and not covered[ink_cols].all():
        return Reading(None, "uncovered_ink", glyphs, row)
    if any(g.margin < templates.min_margin for g in glyphs):
        return Reading(None, "ambiguous", glyphs, row)

    numbers: list[list[Glyph]] = [[glyphs[0]]]
    for prev, g in zip(glyphs, glyphs[1:], strict=False):
        step = g.x - prev.x
        if step == pitch:
            numbers[-1].append(g)
        elif step >= pitch + templates.min_gap:
            numbers.append([g])
        else:
            return Reading(None, "layout", glyphs, row)
    if len(numbers) != 2 or any(not 1 <= len(n) <= MAX_DIGITS for n in numbers):
        return Reading(None, "layout", glyphs, row)
    if templates.text_left is not None and numbers[0][0].x != templates.text_left:
        return Reading(None, "layout", glyphs, row)
    gap = numbers[1][0].x - numbers[0][-1].x - pitch
    if templates.number_gap is not None and gap != templates.number_gap:
        return Reading(None, "layout", glyphs, row)
    if any(len(n) > 1 and n[0].digit == 0 for n in numbers):
        return Reading(None, "leading_zero", glyphs, row)
    x, y = (int("".join(str(g.digit) for g in n)) for n in numbers)
    return Reading((x, y), "ok", glyphs, row)


def read_minimap(
    game_region_bgr: npt.NDArray[np.uint8],
    templates: DigitTemplates,
    rect: tuple[int, int, int, int] | None = None,
) -> Reading:
    """The readout with its reason (evaluation, logs). ``rect``: game-region pixels (x, y, w, h);
    default: the ``minimap_xy`` element at the minimap window's measured origin."""
    x, y, w, h = default_rect() if rect is None else rect
    region = game_region_bgr[y : y + h, x : x + w]
    if region.shape[0] != h or region.shape[1] != w:
        return Reading(None, "rect_outside_frame")
    return read_rect(to_gray(region), templates)


def read_minimap_xy(
    game_region_bgr: npt.NDArray[np.uint8],
    templates: DigitTemplates,
    rect: tuple[int, int, int, int] | None = None,
) -> tuple[int, int] | None:
    """Our own cell (x, y) as the client shows it under the minimap, or None when it cannot be
    read with confidence (never a guess)."""
    return read_minimap(game_region_bgr, templates, rect).xy


# --- fitting (host side: scripts/selfpos_calibrate.py, and the tests) ---------------------------

STROKE_GREY = 200.0  # a template pixel this bright on average is a stroke ...
BACKGROUND_GREY = (50.0, 150.0)  # ... one in this range, on a stroke row, is background


@dataclass(frozen=True, slots=True)
class Layout:
    """Where the readout's cells sit in the rect (measured on the client): the first digit cell's
    left column and top row, the digit pitch, the gap between the numbers, the cell size."""

    text_left: int
    top: int
    number_gap: int
    pitch: int = 7
    cell: tuple[int, int] = (11, 7)  # (h, w)

    def cells(self, x: int, y: int, rect_w: int) -> list[tuple[str, int]]:
        """(char, left column) of every cell of the readout "x y": the digits, the cell in the
        gap as a blank (" "), and every empty cell after the y number inside the rect."""
        xs, ys = str(x), str(y)
        out = [(c, self.text_left + self.pitch * i) for i, c in enumerate(xs)]
        gap = self.text_left + self.pitch * len(xs)
        out.append((" ", gap))
        y0 = gap + self.number_gap
        out += [(c, y0 + self.pitch * i) for i, c in enumerate(ys)]
        left = y0 + self.pitch * len(ys)
        while left + self.cell[1] <= rect_w:
            out.append((" ", left))
            left += self.pitch
        return out

    def cut(self, image: npt.NDArray[np.floating[Any]], left: int) -> Gray:
        h, w = self.cell
        return np.asarray(image[self.top : self.top + h, left : left + w], np.float32)


def _levels(cells: Sequence[Gray]) -> dict[str, Any]:
    """Stroke, background and shadow grey over labelled digit cells (any digits, one array per
    digit): strokes are the template's bright pixels, background its mid pixels on stroke rows,
    shadows the pixels just left of where a stroke starts."""
    strokes, background, shadows = [], [], []
    for stack in cells:
        grey_mean = stack.mean(axis=0)
        stroke_px = grey_mean >= STROKE_GREY
        lo, hi = BACKGROUND_GREY
        bg_px = (grey_mean >= lo) & (grey_mean < hi) & stroke_px.any(axis=1)[:, None]
        starts = np.zeros_like(stroke_px)
        starts[:, :-1] = stroke_px[:, 1:] & ~stroke_px[:, :-1]
        strokes.append(stack[:, stroke_px].ravel())
        background.append(stack[:, bg_px].ravel())
        shadows.append(stack[:, starts].ravel())
    s, b, sh = np.concatenate(strokes), np.concatenate(background), np.concatenate(shadows)
    return {
        "bright": float(np.median(s)),
        "background_median": float(np.median(b)),
        "stroke_p1": float(np.percentile(s, 1)),
        "background_p99": float(np.percentile(b, 99)),
        "shadow_p50_p99": [float(np.percentile(sh, 50)), float(np.percentile(sh, 99))],
    }


def cell_scores(cells: Sequence[Gray], templates: DigitTemplates) -> npt.NDArray[np.float64]:
    """(n, 10): every digit's score on each stroke-probability cell, in place."""
    if not cells:
        return np.zeros((0, 10))
    return np.stack([score_maps(c, templates)[:, 0, 0] for c in cells])


def fit_templates(
    rects: Sequence[Gray],
    labels: Sequence[tuple[int, int]],
    layout: Layout,
    *,
    pin_layout: bool = True,
    tail: float = 0.1,
) -> tuple[DigitTemplates, dict[str, Any]]:
    """Templates and thresholds from readout rects (grey) labelled with the true cell. The rules
    are fixed here, before any held-out frame is read:
      * bright: the median stroke grey; ink_level: halfway between the median background and
        bright; shadow_level: halfway between the shadow's p99 and the median background (a
        stroke start needs both, so a bright scene without a black edge never counts as ink);
      * each rect becomes a stroke-probability map against its own strip background, cut into
        cells by ``layout``; per digit the template is the mean cell; an instance that another
        digit's template fits at least as well (a mislabelled cell) is dropped once, then
        everything is re-fitted;
      * the extremes are robust quantiles, so a handful of covered or mislabelled cells cannot
        set them: worst true glyph = the (100 - ``tail``)th percentile of the true scores, best
        blank = the ``tail``th percentile of the blank cells' best scores, smallest margin = the
        ``tail``th percentile of the true glyphs' margins over their runner-up;
      * max_score: the geometric middle between the worst true glyph and the best blank, at most
        3x the worst true glyph; min_margin: half the smallest margin.
    With ``pin_layout`` the reader then also requires the measured text start and number gap.
    Returns (templates, stats)."""
    if len(rects) != len(labels) or not rects:
        raise ValueError("one label per rect, at least one rect")
    grey: dict[int, list[Gray]] = {d: [] for d in range(10)}
    for rect, (x, y) in zip(rects, labels, strict=True):
        for ch, left in layout.cells(x, y, rect.shape[1]):
            if ch != " ":
                grey[int(ch)].append(layout.cut(rect, left))
    levels = _levels([np.stack(c) for c in grey.values() if c])
    ink = (levels["background_median"] + levels["bright"]) / 2
    shadow = (levels["shadow_p50_p99"][1] + levels["background_median"]) / 2

    kept: dict[int, list[Gray]] = {d: [] for d in range(10)}
    blanks: list[Gray] = []
    for rect, (x, y) in zip(rects, labels, strict=True):
        prob = stroke_probability(rect, levels["bright"], ink, shadow)
        for ch, left in layout.cells(x, y, rect.shape[1]):
            (blanks if ch == " " else kept[int(ch)]).append(layout.cut(prob, left))

    h, w = layout.cell
    probe = DigitTemplates(
        np.zeros((10, h, w), np.float32), np.zeros(10, np.int64), levels["bright"],
        max_score=np.inf, min_margin=0.0, ink_level=ink, shadow_level=shadow, stroke_rows=(0, h),
        pitch=layout.pitch,
    )  # fmt: skip

    def fit(cells: Mapping[int, Sequence[Gray]]) -> DigitTemplates:
        mean = np.zeros((10, h, w), np.float32)
        counts = np.zeros(10, np.int64)
        for d in range(10):
            if cells[d]:
                mean[d] = np.stack(cells[d]).mean(axis=0)
                counts[d] = len(cells[d])
        return replace(probe, mean=mean, counts=counts)

    first = fit(kept)
    dropped = {}
    for d in range(10):
        if not kept[d]:
            continue
        s = cell_scores(kept[d], first)
        keep = s[:, d] < np.delete(s, d, axis=1).min(axis=1)  # its own digit fits best
        dropped[d] = int((~keep).sum())
        kept[d] = [c for c, k in zip(kept[d], keep, strict=True) if k]
    t = fit(kept)

    true_s, margins = [], []
    for d in range(10):
        if kept[d]:
            s = cell_scores(kept[d], t)
            true_s.append(s[:, d])
            margins.append(np.delete(s, d, axis=1).min(axis=1) - s[:, d])
    true_all, margin_all = np.concatenate(true_s), np.concatenate(margins)
    blank_best = cell_scores(blanks, t).min(axis=1) if blanks else np.array([np.inf])
    worst_true = float(np.percentile(true_all, 100 - tail))
    best_blank = float(np.percentile(blank_best, tail))
    smallest_margin = float(np.percentile(margin_all, tail))
    rows = np.flatnonzero((t.mean[t.counts > 0] >= 0.5).any(axis=(0, 2)))
    templates = replace(
        t,
        max_score=min(float(np.sqrt(worst_true * best_blank)), 3.0 * worst_true),
        min_margin=0.5 * smallest_margin,
        stroke_rows=(int(rows[0]), int(rows[-1]) + 1),
        text_left=layout.text_left if pin_layout else None,
        number_gap=layout.number_gap if pin_layout else None,
    )
    stats = {
        "counts": [int(c) for c in t.counts],
        "dropped_mislabelled": dropped,
        "blanks": len(blanks),
        "levels": levels,
        "worst_true": worst_true,
        "best_blank": best_blank,
        "smallest_margin": smallest_margin,
        "true_score_p50_p99_max": [float(np.percentile(true_all, q)) for q in (50, 99, 100)],
        "margin_min_p1_p50": [float(margin_all.min()),
                              *(float(np.percentile(margin_all, q)) for q in (1, 50))],
        "blank_best_min_p1": [float(blank_best.min()), float(np.percentile(blank_best, 1))],
    }  # fmt: skip
    return templates, stats
