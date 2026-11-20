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

- the HOTBAR (the shortcut bar; Batt 2026-11-19: "9 slots in a row = the hotbar"): 9 square slot
  boxes on one row at one pitch (26-36 px; the lab's 29), each by its left line and its top edge,
  uniform and standing out from a neighbour, whatever their colour or the icon inside;
- BASIC INFO: a 220 px wide window whose frame draws uniform rows at fixed depths and a right
  border line, measured only where no text, EXP bar or badge can reach (the title rows right of
  x 130, the gaps between the bars, the level panel's edges, the line over the weight), whatever
  the character's name, level or language (measured on the lab's client, 1280x720 and
  1920x1080).

Pure: numpy only, no X, no I/O. Inputs are LUMA frames of the real client (client pixels).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

Luma = NDArray[np.float32]

# --- the hotbar --------------------------------------------------------------------------------
# Batt 2026-11-19 ~12:3x: "really not hard: just look for the UI with 9 slots in a row ... RO's
# hotbar is fixed like that: 9 horizontal slots = the hotbar." Each slot is a square BOX with a
# thin frame (the lab's: 26 x 26 on a 29 px pitch, grey 195 on white); another client's frame may
# be another colour (Batt's: dark) and its counts sit elsewhere, so a slot is its LEFT line and its
# TOP edge -- each uniform and standing out from a neighbour, whatever their colour -- and the bar
# is 9 such boxes on one row at one pitch. The right line and the bottom edge are not used: the
# counts are drawn over them.
HOTBAR_SLOTS = 9
# RO's shortcut bar is fixed (Batt): the lab's 29, Batt's other client's 29 too (his screenshot);
# a little either side for another skin
HOTBAR_PITCHES = (28, 29, 30)
HOTBAR_GAP = 3  # a slot box is its pitch minus this (the lab: 26 of 29)
HOTBAR_LINE_STD = 12.0  # a frame line varies at most this much along itself
HOTBAR_EDGE = 20.0  # and stands out from a neighbour (outside or inside) by at least this
HOTBAR_MIN_LINES = 9  # a search wants all 9 boxes (Batt: "9 slots complete = the hotbar")
HOTBAR_LINE_DX = 15  # the first slot's left line, from the window's origin (the lab's registry)
HOTBAR_LINE_DY = 4  # its top edge, from the window's origin
HOTBAR_MIN_AT = 8  # a re-check at its place: one slot may be covered (the pointer, a tooltip)
# 2026-11-20 (the live PC's client): a slot's stack count ("592", "570", "11") is drawn over the
# BOTTOM of its left frame line, so that line was not uniform there and 3 of the 9 slots failed
# (the search wants 9): the left line is checked only above the count's rows. The lab's frames pass
# on any part of their lines.
HOTBAR_COUNT_ROWS = 5


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
    """A window found at ``origin`` (client px, its top-left) with ``score`` of ``of`` cues
    (the hotbar: its slots' ``pitch``)."""

    name: str
    origin: tuple[int, int]
    score: int
    of: int
    pitch: int | None = None


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


def _frame_line(m: NDArray[np.float64], sd: NDArray[np.float64], axis: int) -> NDArray[np.bool_]:
    """A box's frame line, from each line's run mean ``m`` and std ``sd`` along ``axis`` (the
    line before = outside the box, the line after = inside): uniform; standing out from the
    OUTSIDE; and from the inside too -- or the inside is no flat colour (an icon)."""
    out = np.zeros(m.shape, bool)
    sl = [slice(None)] * m.ndim
    cur, prev, nxt = list(sl), list(sl), list(sl)
    cur[axis], prev[axis], nxt[axis] = slice(1, -1), slice(None, -2), slice(2, None)
    c, p, n = tuple(cur), tuple(prev), tuple(nxt)
    outside = np.abs(m[c] - m[p]) >= HOTBAR_EDGE
    inside = (np.abs(m[c] - m[n]) >= HOTBAR_EDGE) | (sd[n] > HOTBAR_LINE_STD)
    out[c] = (sd[c] <= HOTBAR_LINE_STD) & outside & inside
    return out


def _slots(lum: Luma, pitch: int) -> NDArray[np.bool_]:
    """ok[y, x]: a slot box of this pitch has its top-left corner at (x, y) -- its left line
    (rows y + 1 .. y + size - 2) and its top edge (columns x + 1 .. x + size - 2) uniform and
    each standing out from a neighbour."""
    size = pitch - HOTBAR_GAP
    n = size - 2
    h, w = lum.shape
    if h < size or w < size:
        return np.zeros((0, 0), bool)
    # the left line above the stack count's rows (HOTBAR_COUNT_ROWS)
    cm, cs = _running(lum, n - HOTBAR_COUNT_ROWS, axis=0)  # column runs, row r = from row r
    left = _frame_line(cm, cs, axis=1)
    rm, rs = _running(lum, n, axis=1)  # row runs: (h, w - n + 1), column c = from column c
    top = _frame_line(rm, rs, axis=0)
    ny, nx = h - size + 1, w - size + 1
    return np.asarray(left[1 : 1 + ny, :nx] & top[:ny, 1 : 1 + nx])


def _comb(ok: NDArray[np.bool_], pitch: int) -> NDArray[np.int64]:
    span = pitch * (HOTBAR_SLOTS - 1)
    h, w = ok.shape
    if w <= span:
        return np.zeros((h, 0), np.int64)
    comb = np.zeros((h, w - span), np.int64)
    for i in range(HOTBAR_SLOTS):
        comb += ok[:, pitch * i : pitch * i + w - span]
    return comb


def find_hotbar(lum: Luma, pitches: Sequence[int] = HOTBAR_PITCHES) -> Found | None:
    """PURE: the hotbar's row 1 -- the most slots (at least HOTBAR_MIN_LINES of 9) on one row at
    one pitch, then the topmost, then the leftmost -- or None. Its origin is where the lab's
    registry puts the window's (slot 1's box at origin + (15, 4)); ``pitch`` says its pitch."""
    best: tuple[int, int, int, int] | None = None  # (-score, y, x, pitch)
    for pitch in pitches:
        comb = _comb(_slots(lum, pitch), pitch)
        if comb.size == 0:
            continue
        top = int(comb.max())
        if top < HOTBAR_MIN_LINES:
            continue
        ys, xs = np.nonzero(comb == top)
        k = int(np.lexsort((xs, ys))[0])
        cand = (-top, int(ys[k]), int(xs[k]), pitch)
        if best is None or cand < best:
            best = cand
    if best is None:
        return None
    score, y, x, pitch = -best[0], best[1], best[2], best[3]
    return Found("hotbar", (x - HOTBAR_LINE_DX, y - HOTBAR_LINE_DY), score, HOTBAR_SLOTS, pitch)


def hotbar_at(lum: Luma, origin: tuple[int, int], pitch: int = 29) -> int:
    """PURE: how many of the 9 slot boxes the hotbar shows at ``origin`` (a cheap re-check:
    HOTBAR_MIN_AT or more = still there)."""
    ox, oy = origin
    x0, y0 = ox + HOTBAR_LINE_DX, oy + HOTBAR_LINE_DY
    size = pitch - HOTBAR_GAP
    x1, y1 = x0 + pitch * (HOTBAR_SLOTS - 1) + size + 1, y0 + size + 1
    if x0 < 1 or y0 < 1 or x1 > lum.shape[1] or y1 > lum.shape[0]:
        return 0
    sub = lum[y0 - 1 : y1, x0 - 1 : x1]
    ok = _slots(sub, pitch)
    return int(sum(bool(ok[1, 1 + pitch * i]) for i in range(HOTBAR_SLOTS)))


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
