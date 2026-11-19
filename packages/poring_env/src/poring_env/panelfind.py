"""Find RO's interface windows by their SHAPE, anywhere on the client (teaching-prerun.md 4f,
docs/planning/fullscreen-client.md milestone 3; Batt 2026-11-19: "make it work with every client;
we cannot ask to see every user's client, but we know what RO's main UI looks like: start from
that").

A player drags RO's windows where they like and RO restores them there; another client's layout
is not the lab's. Everything the bot reads (the weight, the hotbar counts, the Battle Log) was built
at the lab's places. So each window is FOUND on the real client and moved, in the virtual 1280x720
client (poring_env.clientview), to the lab's place: the readers and the byte-pinned runner stay
unchanged.

The finders use the standard RO windows' STRUCTURE, written here as rules -- no template cut from
a client, no text (any language), so every install can use them without a calibration step:

- the HOTBAR (the shortcut bar): 9 slots on a 29 px pitch; each slot's left frame line is a
  vertical line, uniform over the slot's 25 rows, of a mid grey, whatever icon the slot holds
  (measured on the lab's client: x = 245 + 29 i, rows 4-28 of the window, luma 180-210);
- BASIC INFO: a 220 px wide window whose frame draws uniform rows at fixed depths and a right
  border line, measured only where no text, EXP bar or badge can reach (the title rows right of
  x 130, the gaps between the bars, the level panel's edges, the line over the weight), whatever
  the character's name, level or language (measured on the lab's client, 1280x720 and
  1920x1080).

Pure: numpy only, no X, no I/O. Inputs are LUMA frames of the real client (client pixels).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

Luma = NDArray[np.float32]

# --- the hotbar --------------------------------------------------------------------------------
HOTBAR_SLOTS = 9
HOTBAR_PITCH = 29
HOTBAR_BAND = 25  # rows of a slot's left line (window rows 4-28)
HOTBAR_LINE_DX = 15  # the first slot's left line, from the window's origin
HOTBAR_LINE_DY = 4
HOTBAR_LINE_STD = 12.0  # a line: its column varies at most this much over the band
HOTBAR_LINE_LUMA = (165.0, 225.0)  # and its mean is a mid grey (the lab: 180-210)
HOTBAR_MIN_LINES = 8  # of 9: one slot may be covered (the pointer, a tooltip)
# its top frame rows, over the slots' span: uniform, at these lumas (the lab's client: 204, 245,
# 254, 254 on four frames of 1280x720 and 1920x1080, whatever the slots held). They pin the row
# exactly and refuse other combs of lines (the login screen's list drew 8 of 9).
HOTBAR_ROWS: tuple[tuple[int, tuple[float, float]], ...] = (
    (0, (180.0, 228.0)),
    (1, (230.0, 256.0)),
    (2, (240.0, 256.0)),
    (3, (240.0, 256.0)),
)
HOTBAR_ROW_STD = 8.0
HOTBAR_SPAN = HOTBAR_PITCH * (HOTBAR_SLOTS - 1) + 26  # the slots' width, from the first line
HOTBAR_CANDIDATES = 400  # the best comb positions checked for the rows

HOTBAR_MIN_AT = HOTBAR_MIN_LINES + 4  # hotbar_at: 8 of 9 lines and all four top rows

# --- Basic Info ------------------------------------------------------------------------------
BASIC_W = 220
BASIC_ROW_STD = 8.0  # a frame row: uniform across its span
# (depth from the window's top, luma band, (x0, x1) of the span). Only rows no TEXT, EXP BAR or
# BADGE can reach (2026-11-19 ~11:0x, after the first test on a Thai-UI client: a Thai title's
# tails reach the line under it, the "N" notice badge sits at the bottom). The title rows are read
# only right of x 130 (a title is left-aligned, ~105 px in English and in Thai); the level panel
# only by its top and bottom edges (its EXP bars live inside; live 11:40, Valcd8bd6 Base 70 / Job 1:
# they missed the first rules' rows too). Measured on the lab's 1280x720 and 1920x1080 frames.
BASIC_ROWS: tuple[tuple[int, tuple[float, float], tuple[int, int]], ...] = (
    (2, (150.0, 225.0), (130, 200)),  # the title bar (lab 187)
    (16, (0.0, 60.0), (130, 200)),  # the line under it (lab 0)
    (64, (240.0, 256.0), (0, BASIC_W)),  # white, between the HP and SP bars
    (66, (240.0, 256.0), (0, BASIC_W)),
    (78, (240.0, 256.0), (0, BASIC_W)),  # white, under the SP bar
    (82, (240.0, 256.0), (0, BASIC_W)),
    (85, (205.0, 248.0), (0, BASIC_W)),  # the level panel's top edge (lab 231-233)
    (109, (205.0, 248.0), (0, BASIC_W)),  # its bottom edge (its EXP bars are inside)
    (111, (240.0, 256.0), (0, BASIC_W)),  # white, under the panel
    (114, (170.0, 225.0), (0, BASIC_W)),  # the line over the weight (lab 197)
)
# the window's right border: column 219, rows 20-130 (lab 197, std 2-6)
BASIC_COL: tuple[int, tuple[float, float], tuple[int, int]] = (219, (175.0, 220.0), (20, 131))
BASIC_COL_STD = 10.0
BASIC_CUES = len(BASIC_ROWS) + 1
BASIC_MIN_ROWS = BASIC_CUES - 1  # one cue may be crossed (the pointer)
BASIC_H = max(max(r for r, _, _ in BASIC_ROWS) + 1, BASIC_COL[2][1])


@dataclass(frozen=True)
class Found:
    """A window found at ``origin`` (client px, its top-left) with ``score`` of ``of`` cues."""

    name: str
    origin: tuple[int, int]
    score: int
    of: int


def luma(frame_bgr: NDArray[np.uint8]) -> Luma:
    """BGR(A) -> luma (the weights chat_window and the readers use)."""
    f = frame_bgr[..., :3].astype(np.float32)
    return np.asarray(0.114 * f[..., 0] + 0.587 * f[..., 1] + 0.299 * f[..., 2], np.float32)


def _running(a: Luma, n: int, axis: int) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Mean and std of every run of ``n`` along ``axis`` (valid positions only)."""
    x = a.astype(np.float64)
    c1 = np.cumsum(x, axis=axis)
    c2 = np.cumsum(x * x, axis=axis)
    zero = np.zeros_like(np.take(c1, [0], axis=axis))
    c1 = np.concatenate([zero, c1], axis=axis)
    c2 = np.concatenate([zero, c2], axis=axis)
    m = a.shape[axis]
    s1 = np.take(c1, range(n, m + 1), axis=axis) - np.take(c1, range(0, m - n + 1), axis=axis)
    s2 = np.take(c2, range(n, m + 1), axis=axis) - np.take(c2, range(0, m - n + 1), axis=axis)
    mean = s1 / n
    var = np.maximum(s2 / n - mean * mean, 0.0)
    return mean, np.sqrt(var)


def hotbar_lines(lum: Luma) -> NDArray[np.bool_]:
    """PURE: line[y, x] -- column x is a slot frame line over rows y .. y + HOTBAR_BAND - 1."""
    if lum.shape[0] < HOTBAR_BAND:
        return np.zeros((0, lum.shape[1]), bool)
    mean, std = _running(lum, HOTBAR_BAND, axis=0)
    lo, hi = HOTBAR_LINE_LUMA
    return (std <= HOTBAR_LINE_STD) & (mean >= lo) & (mean <= hi)


def _hotbar_comb(line: NDArray[np.bool_]) -> NDArray[np.int64]:
    span = HOTBAR_PITCH * (HOTBAR_SLOTS - 1)
    h, w = line.shape
    if w <= span:
        return np.zeros((h, 0), np.int64)
    comb = np.zeros((h, w - span), np.int64)
    for i in range(HOTBAR_SLOTS):
        comb += line[:, HOTBAR_PITCH * i : HOTBAR_PITCH * i + w - span]
    return comb


def hotbar_rows_at(lum: Luma, origin: tuple[int, int]) -> int:
    """PURE: how many of the hotbar's top frame rows hold at ``origin``."""
    ox, oy = origin
    x0 = ox + HOTBAR_LINE_DX
    if oy < 0 or x0 < 0 or oy + len(HOTBAR_ROWS) > lum.shape[0] or x0 + HOTBAR_SPAN > lum.shape[1]:
        return 0
    n = 0
    for depth, (lo, hi) in HOTBAR_ROWS:
        row = lum[oy + depth, x0 : x0 + HOTBAR_SPAN].astype(np.float64)
        n += int(float(row.std()) <= HOTBAR_ROW_STD and lo <= float(row.mean()) <= hi)
    return n


def find_hotbar(lum: Luma) -> Found | None:
    """PURE: the hotbar's row 1 -- a comb of at least HOTBAR_MIN_LINES slot lines on the pitch
    under all of its top frame rows; the most lines, then the topmost, then the leftmost -- or
    None. Its origin is where the lab's registry puts the window's (the first line at origin +
    (15, 4), the top frame row at origin)."""
    comb = _hotbar_comb(hotbar_lines(lum))
    if comb.size == 0 or int(comb.max()) < HOTBAR_MIN_LINES:
        return None
    ys, xs = np.nonzero(comb >= HOTBAR_MIN_LINES)
    order = np.lexsort((xs, ys, -comb[ys, xs]))[:HOTBAR_CANDIDATES]
    for k in order.tolist():
        y, x = int(ys[k]), int(xs[k])
        origin = (x - HOTBAR_LINE_DX, y - HOTBAR_LINE_DY)
        if hotbar_rows_at(lum, origin) == len(HOTBAR_ROWS):
            return Found("hotbar", origin, int(comb[y, x]) + len(HOTBAR_ROWS),
                         HOTBAR_SLOTS + len(HOTBAR_ROWS))  # fmt: skip
    return None


def hotbar_at(lum: Luma, origin: tuple[int, int]) -> int:
    """PURE: how many of the hotbar's cues (9 slot lines + its top frame rows) hold at
    ``origin`` (a cheap re-check: HOTBAR_MIN_AT or more = still there)."""
    ox, oy = origin
    y0, x0 = oy + HOTBAR_LINE_DY, ox + HOTBAR_LINE_DX
    x1 = x0 + HOTBAR_PITCH * (HOTBAR_SLOTS - 1) + 1
    if y0 < 0 or x0 < 0 or y0 + HOTBAR_BAND > lum.shape[0] or x1 > lum.shape[1]:
        return 0
    band = lum[y0 : y0 + HOTBAR_BAND, x0:x1].astype(np.float64)
    cols = band[:, ::HOTBAR_PITCH]
    lo, hi = HOTBAR_LINE_LUMA
    mean, std = cols.mean(axis=0), cols.std(axis=0)
    lines = int(((std <= HOTBAR_LINE_STD) & (mean >= lo) & (mean <= hi)).sum())
    return lines + hotbar_rows_at(lum, origin)


def _basic_rows(lum: Luma) -> NDArray[np.int64]:
    """score[y, x]: how many of Basic Info's cues hold for a window whose top-left is (x, y)."""
    h, w = lum.shape
    if w < BASIC_W or h < BASIC_H:
        return np.zeros((0, 0), np.int64)
    ny, nx = h - BASIC_H + 1, w - BASIC_W + 1
    score = np.zeros((ny, nx), np.int64)
    stats: dict[int, tuple[NDArray[np.float64], NDArray[np.float64]]] = {}
    for depth, (lo, hi), (x0, x1) in BASIC_ROWS:
        n = x1 - x0
        if n not in stats:
            stats[n] = _running(lum, n, axis=1)  # (h, w - n + 1)
        mean, std = stats[n]
        m = mean[depth : depth + ny, x0 : x0 + nx]
        sd = std[depth : depth + ny, x0 : x0 + nx]
        score += (sd <= BASIC_ROW_STD) & (m >= lo) & (m <= hi)
    col, (lo, hi), (y0, y1) = BASIC_COL
    cmean, cstd = _running(lum, y1 - y0, axis=0)  # (h - n + 1, w)
    m = cmean[y0 : y0 + ny, col : col + nx]
    sd = cstd[y0 : y0 + ny, col : col + nx]
    score += (sd <= BASIC_COL_STD) & (m >= lo) & (m <= hi)
    return score


def find_basic_info(lum: Luma) -> Found | None:
    """PURE: Basic Info's top-left, or None (closed, collapsed to its title bar, or covered)."""
    score = _basic_rows(lum)
    if score.size == 0:
        return None
    best = int(score.max())
    if best < BASIC_MIN_ROWS:
        return None
    ys, xs = np.nonzero(score == best)
    k = int(np.lexsort((xs, ys))[0])
    return Found("basic_info", (int(xs[k]), int(ys[k])), best, BASIC_CUES)


def basic_info_at(lum: Luma, origin: tuple[int, int]) -> int:
    """PURE: how many of Basic Info's cues hold at ``origin`` (a cheap re-check)."""
    ox, oy = origin
    if ox < 0 or oy < 0 or ox + BASIC_W > lum.shape[1] or oy + BASIC_H > lum.shape[0]:
        return 0
    n = 0
    for depth, (lo, hi), (x0, x1) in BASIC_ROWS:
        row = lum[oy + depth, ox + x0 : ox + x1].astype(np.float64)
        n += int(float(row.std()) <= BASIC_ROW_STD and lo <= float(row.mean()) <= hi)
    col, (lo, hi), (y0, y1) = BASIC_COL
    c = lum[oy + y0 : oy + y1, ox + col].astype(np.float64)
    n += int(float(c.std()) <= BASIC_COL_STD and lo <= float(c.mean()) <= hi)
    return n
