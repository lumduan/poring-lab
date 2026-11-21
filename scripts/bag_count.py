#!/usr/bin/env python3
"""COUNT THE BAG from pixels (Economy option b-i; docs/planning/econ-bag-count.md; Batt 2026-11-20:
"count the bag at the Run's start and end -- the way people do it -- and try it offline first").

    bag_count.py read IMAGE [--refs NPZ]          OFFLINE: one real-client frame with the bag open
    bag_count.py census [--refs NPZ] [--out JSON] LIVE: open the bag, read every tab, close it
    bag_count.py truth --char NAME                the lab database's bag of NAME (read only)
    bag_count.py trial --char NAME [--out JSON]   census + truth + the pre-registered bar (B1-B4)

What the screen offers (measured 2026-11-20 on the lab's 1920x1080 client; the plan's section 2):
RO draws the inventory 1:1 on the REAL client (not a pasted panel of the virtual view, which
would shrink it with the world), so everything here reads the real client frame (client pixels).

- 7 columns x ROWS slots on a 32 px pitch: 6 rows on the client's default window, more when the
  player drags it taller (Batt's live bag: 7 x 9, 2026-11-21), so the rows are READ from the
  pixels (ROWS_MIN .. ROWS_MAX), never assumed. Slot (0, 0)'s icon is the 24 x 24 square at the
  window's origin + ICON0. An EMPTY slot shows an oval (OVAL's colour; its box OVAL_BOX in the
  square). The oval is drawn behind an item too, so the pictures are composited over THIS
  client's own empty slot, cut at run time from an empty slot of the open bag (any skin, no stored
  client pixels).
- The count: PURE BLACK digits (max channel <= COUNT_INK; an icon's darkest outline is 8),
  left-aligned from the icon's x + 14, rows +18 .. +26, in the hotbar's glyphs (hotbar_count).
- Four tabs on the left (TABS, from the window's origin): Use, Eqp, Etc, Fav.

The window is FOUND by the lattice of empty-slot ovals (a rule: no template, no text, any
language): the 7 x ROWS placement with the most ovals, and NO oval one pitch outside it on any side
(a placement shifted by a column would see the real last column's ovals there). The ovals fix the
window's columns and its LAST row; its TOP is the first row, going up, that shows no slot at all.
A row shows a slot when one of its cells shows the slot's oval -- whole (empty), or around an
item's icon, or as a NEW item's pink glow -- in at least SLOT_ROWS rows of the oval's box (the
title bar above row 0 shows at most 2: one line of a blue gradient). Without that cue a tab whose
first rows are full of items would fit a window of any height whose rows are all below its title.

Never guessed: a slot is "item" (its ids -- a shared icon is a group -- and its count), "empty", or
"unread" with the reason. Items fill a tab in reading order, so an item after an empty slot is an
anomaly (a pointer, a tooltip): unread. A tab whose slots are all items may hold more ("full").
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
SIZE = 24  # the item bitmap's side, drawn 1:1
PITCH = 32
COLS = 7
# the window's rows: the client's default is 6 (the lab's); a player drags it taller (Batt's live
# bag, 2026-11-21: 9). Read from the pixels (find_bag / rows_at), searched within these bounds.
ROWS_MIN, ROWS_MAX = 6, 12
ICON0 = (44, 21)  # slot (0, 0)'s icon square, from the window's origin (its title bar's top-left)
# the window's size from its origin at ROWS_MIN rows (measured 2026-11-20, ro_agent's 1:1 panel);
# a taller window adds one PITCH per row (its footer stays below its last row)
WINDOW_W, WINDOW_H_MIN = 280, 255
OVAL = (206, 214, 231)  # an empty slot's oval (RGB)
OVAL_TOL = 30  # a pixel within this (sum of |RGB - OVAL|) is oval-coloured
# the oval's BOUNDING BOX in the icon square (dx, dy, w, h): its OVAL_TOL pixels span rows 11-20
# and columns 1-22 (measured on 35 empty cells); the box is tight, so "the oval touches all four
# edges" holds only at its exact place
OVAL_BOX = (1, 11, 22, 10)
OVAL_SHARE = 0.6  # an empty cell's box is at least this oval-coloured (an ellipse fills ~0.78)
LATTICE_MIN = 2  # the bag is found by at least this many empty-slot ovals
# a cell SHOWS A SLOT when at least this many rows of its oval box hold oval-coloured (or NEW-glow
# pink) pixels. Measured 2026-11-22 on the lab's 1080 bag: an empty cell 10, an item row 6-10, the
# title bar above row 0 1-2 per cell (one line of its gradient; the close buttons). Over the 2,381
# icons of slot_items' archive drawn on that bag's empty slot, 3.8 % show fewer than 4 rows (4.5 %
# of weapons and armour), so a row of 7 items that hides every oval is ~1e-9.
SLOT_ROWS = 4
GLOW_RB_MIN, GLOW_G_MAX = 220, 215  # a NEW item's pink glow (255, 131-165, 247): R, B >= / G <=
TABS: dict[str, tuple[int, int]] = {"use": (10, 45), "eqp": (10, 100), "etc": (10, 154),
                                    "fav": (10, 205)}  # fmt: skip
COUNT_DY, COUNT_ROWS = 18, 9  # the digits' rows from the icon's top
# the count's place (measured 2026-11-20 on the trials' 1- to 4-digit stacks, icon-relative x):
#   1 digit  x+14 .. 19 | 2 digits x+14 .. 26 | 3 digits x+14 .. 33 | 4 digits x+0 .. 26
# (a leading '1' is drawn one column in: x+15 / x+1). A slot's band also shows its neighbours'
# digits (the next slot's 4-digit count starts at our x+33), so a count is read only when its runs
# make exactly one of these shapes with clear columns on both sides; anything else is unread.
COUNT_X0, COUNT_X1 = -2, 36  # the band searched, from the icon's x
COUNT_SHAPES = {1: ((14, 15), 19), 2: ((14, 15), 26), 3: ((14, 15), 33), 4: ((0, 1), 26)}
COUNT_INK = 3  # a count pixel is pure black: max channel <= this
# find_bag's EMPTY cell also shows no count ink in these columns of the count's rows (from the
# icon's x): every count starts in them (a 4-digit one at x+0/1, so from x+2 on), and the previous
# slot's 3-digit count ends at its x+33 = our x+1, outside them. A THIN icon (a tooth, a talon, a
# sword: 7.5 % of the archive's icons) leaves >= OVAL_SHARE of the oval showing, but every item
# shows a count (equipment "1"), so its cell is never taken for an empty one.
COUNT_INK_X = (2, 27)
DIGIT_GAP = 2  # at most this many blank columns between two digits of one count
EMPTY_MAX = 4.0  # a square this close (mean |RGB|) to the empty-slot picture is empty
BG_TOL = 40  # a pixel within this (sum of |RGB|) of the empty slot's is its background
UNEXPLAINED_MAX = (
    0.10  # at most this share of the pixels outside the named picture is no background
)
# the naming rule of slot_items (the same pictures and thresholds; another background)
NAME_MAX = 20.0
RIVAL_RANGE = 30.0
DIFF_PX = 30.0
DISCRIM_MIN = 6
PAIR_LEAD = 0.5
TOP_K = 12
PARK = (640, 640)  # the pointer's rest while a tab is read: client px, off any bag place


def _compare_mask() -> np.ndarray:
    """PURE: the icon square's compared pixels: not the count's ROWS (from COUNT_DY - 1 down), all
    columns -- a 4-digit count spans the slot's width (x+0 .. 26)."""
    keep = np.ones((SIZE, SIZE), bool)
    keep[COUNT_DY - 1 :, :] = False
    return keep


COMPARE = _compare_mask()


# --- where the bag is ---------------------------------------------------------------------------
def rgb_of(frame_bgr: Any) -> np.ndarray:
    return np.ascontiguousarray(np.asarray(frame_bgr)[..., 2::-1]).astype(np.int16)


def glow_mask(rgb: np.ndarray) -> np.ndarray:
    """PURE: a NEW item's pink glow (RGB, any shape (..., 3))."""
    return np.asarray((rgb[..., 0] >= GLOW_RB_MIN) & (rgb[..., 2] >= GLOW_RB_MIN)
                      & (rgb[..., 1] <= GLOW_G_MAX))  # fmt: skip


def cell_maps(frame_bgr: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """PURE: for an oval box (OVAL_BOX's size) with its top-left at (y, x): (empty, tight, slot).
    ``empty``: at least OVAL_SHARE of it is oval-coloured. ``tight``: the oval touches all four
    of the box's edges -- only at the oval's exact place (the box is the oval's bounding box), so
    the share, which holds over +-2 px, does not pick the place alone. ``slot``: at least SLOT_ROWS
    of its rows hold an oval-coloured or glow-pink pixel (a slot, empty or not)."""
    rgb = rgb_of(frame_bgr)
    oval = np.abs(rgb - np.asarray(OVAL, np.int16)).sum(axis=2) <= OVAL_TOL
    w, h = OVAL_BOX[2], OVAL_BOX[3]
    if oval.shape[0] < h or oval.shape[1] < w:  # smaller than one box: no cell at all
        none = np.zeros((0, 0), bool)
        return none, none, none
    ev = (oval | glow_mask(rgb)).astype(np.int32)
    es = np.zeros((ev.shape[0], ev.shape[1] + 1), np.int32)  # running sums along each row
    es[:, 1:] = ev.cumsum(1)
    lit = (es[:, w:] - es[:, :-w] > 0).astype(np.int32)  # (rows, cols - w + 1): row y lit from x
    ls = np.zeros((lit.shape[0] + 1, lit.shape[1]), np.int32)
    ls[1:] = lit.cumsum(0)
    slot = np.asarray(ls[h:] - ls[:-h] >= SLOT_ROWS)
    empty, tight = _oval_boxes(oval.astype(np.int32), w, h)
    return empty, tight, slot


def _oval_boxes(m: np.ndarray, w: int, h: int) -> tuple[np.ndarray, np.ndarray]:
    """PURE: cell_maps' (empty, tight) from the oval-coloured mask."""
    ii = np.zeros((m.shape[0] + 1, m.shape[1] + 1), np.int32)
    ii[1:, 1:] = m.cumsum(0).cumsum(1)
    area = ii[h:, w:] - ii[:-h, w:] - ii[h:, :-w] + ii[:-h, :-w]
    H, W = area.shape
    cs = np.zeros((m.shape[0] + 1, m.shape[1]), np.int32)  # running sums down each column
    cs[1:] = m.cumsum(0)
    col = cs[h:] - cs[:-h]  # (rows - h + 1, cols): a column's h pixels from row y
    rs = np.zeros((m.shape[0], m.shape[1] + 1), np.int32)  # running sums along each row
    rs[:, 1:] = m.cumsum(1)
    row = rs[:, w:] - rs[:, :-w]  # (rows, cols - w + 1): a row's w pixels from column x
    left, right = col[:H, :W] > 0, col[:H, w - 1 : w - 1 + W] > 0
    top, bottom = row[:H, :W] > 0, row[h - 1 : h - 1 + H, :W] > 0
    return np.asarray(area >= OVAL_SHARE * h * w), np.asarray(left & right & top & bottom)


@dataclass(frozen=True)
class Bag:
    """A found bag window: its origin (the title bar's top-left, frame px) and its rows."""

    origin: tuple[int, int]
    rows: int


DX0, DY0 = ICON0[0] + OVAL_BOX[0], ICON0[1] + OVAL_BOX[1]  # a cell's oval box from the origin
CHUNK = 4096  # candidates judged at once (bounds the gathers' memory on an oval-rich frame)


def _gather(m: np.ndarray, y: np.ndarray, x: np.ndarray) -> np.ndarray:
    """PURE: m[y, x], False where (y, x) is no box of m: a cell beyond the frame shows nothing (a
    bag pushed to a screen edge: its ring there is clear, its rows there show no slot)."""
    if m.size == 0:
        return np.zeros(np.broadcast_shapes(y.shape, x.shape), bool)
    inside = (y >= 0) & (y < m.shape[0]) & (x >= 0) & (x < m.shape[1])
    got = m[np.clip(y, 0, m.shape[0] - 1), np.clip(x, 0, m.shape[1] - 1)]
    return np.asarray(inside & got)


def _judge(maps: tuple[np.ndarray, np.ndarray, np.ndarray], ox: np.ndarray, oyb: np.ndarray,
           min_ovals: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:  # fmt: skip
    """PURE: each candidate's (rows, empty cells, tight empty cells); rows 0 = no bag. A
    candidate is given by its BOTTOM row: (ox, oyb) is where the window's origin would be if that
    row were its row 0. Its rows: the run of rows, from the bottom up, that show a slot
    (cell_maps), within ROWS_MIN .. ROWS_MAX -- the row above that run (the title bar) shows none.
    Then the 7 x rows placement is a bag when its empty cells are the TAIL of its cells in reading
    order, at least ``min_ovals`` of them, and no empty cell shows in the ring one pitch outside
    it."""
    empty, tight, slot = maps
    k = np.arange(ROWS_MAX + 2)  # grid rows: k = ROWS_MAX is the bottom row, ROWS_MAX + 1 below it
    c = np.arange(COLS + 2)  # grid columns: 0 and COLS + 1 are the ring's sides
    y = (oyb + DY0)[:, None, None] + PITCH * (k - ROWS_MAX)[None, :, None]
    x = (ox + DX0)[:, None, None] + PITCH * (c - 1)[None, None, :]
    e, t, s = (_gather(m, y, x) for m in (empty, tight, slot))  # (N, ROWS_MAX + 2, COLS + 2)
    cells = slice(1, COLS + 1)
    shows = s[:, : ROWS_MAX + 1, cells].any(axis=2)  # a row with a slot in any of its cells
    rows = np.cumprod(shows[:, ::-1], axis=1).sum(axis=1)  # the run from the bottom row up
    rows = np.where((rows >= ROWS_MIN) & (rows <= ROWS_MAX), rows, 0)
    top = (ROWS_MAX + 1 - rows)[:, None, None]  # the top row's k (ROWS_MAX + 1: no bag)
    kk, cc = k[None, :, None], c[None, None, :]
    inside = (kk >= top) & (kk <= ROWS_MAX) & (cc >= 1) & (cc <= COLS)
    ring = (kk >= top - 1) & ~inside
    outside = (e & ring).any(axis=(1, 2))
    count = (e & inside).sum(axis=(1, 2))
    order = e[:, : ROWS_MAX + 1, cells].reshape(len(ox), -1)  # reading order, the bottom row last
    trail = np.cumprod(order[:, ::-1], axis=1).sum(axis=1)  # the trailing run of empty cells
    ok = (rows > 0) & (count >= min_ovals) & (trail == count) & ~outside
    return np.where(ok, rows, 0), count, (e & t & inside).sum(axis=(1, 2))


def find_bag(frame_bgr: Any, min_ovals: int = LATTICE_MIN) -> Bag | None:
    """PURE: the bag's window (origin and rows) on a real-client frame by its oval lattice, or
    None.

    _judge's rule (the window's columns and last row by the ovals and their clear ring, its top by
    the first row above that shows no slot). Among the bags: the most empty cells, then the most
    TIGHT ones (the exact pixel). Another as good more than half a pitch away = two bags alike:
    None. The tail rule makes the LAST cell empty, so only candidates whose bottom-right cell sits
    on an oval box are judged (a few hundred, not every pixel).

    An empty cell here also shows no count ink (COUNT_INK_X): a thin icon's cell is an item, not a
    hole before the tail that moved the bag a few pixels (2026-11-22, the lab's 1080 bag with
    random archive icons and their counts: 95 of 300 tabs found off their place without it, 0
    with it). Every caller looks with the pointer parked off the bag. rows_at keeps the oval rule
    alone: it looks at a known place while the pointer may rest on the bag (ro_agent's drags),
    where the pointer's black outline over an empty cell would read as a count."""
    empty, tight, slot = cell_maps(frame_bgr)
    maps = (empty & ~count_ink(frame_bgr, empty.shape), tight, slot)
    ys, xs = np.nonzero(maps[0])
    ox, oyb = xs - DX0 - PITCH * (COLS - 1), ys - DY0
    keep = ox + DX0 >= 0  # the lattice's first column inside the frame
    ox, oyb = ox[keep], oyb[keep]
    if len(ox) == 0:
        return None
    parts = [_judge(maps, ox[i : i + CHUNK], oyb[i : i + CHUNK], min_ovals)
             for i in range(0, len(ox), CHUNK)]  # fmt: skip
    rows, count, tight = (np.concatenate(p) for p in zip(*parts, strict=True))
    ok = rows > 0
    if not ok.any():
        return None
    oy = oyb - PITCH * (rows - 1)
    best = int(count[ok].max())
    snug = np.where(ok & (count == best), tight, -1)
    k = int(np.argmax(snug))
    same = snug == snug[k]
    if np.any((np.abs(oy[same] - oy[k]) > PITCH // 2) | (np.abs(ox[same] - ox[k]) > PITCH // 2)):
        return None
    return Bag((int(ox[k]), int(oy[k])), int(rows[k]))


def count_ink(frame_bgr: Any, shape: tuple[int, ...]) -> np.ndarray:
    """PURE: for an oval box with its top-left at (y, x) (cell_maps' maps, of ``shape``): its cell
    shows pure-black count ink in the count's rows, columns COUNT_INK_X. Beyond the frame: none."""
    ink = (np.asarray(frame_bgr)[..., :3].max(axis=2) <= COUNT_INK).astype(np.int32)
    H, W = ink.shape
    dy, dx = COUNT_DY - OVAL_BOX[1], COUNT_INK_X[0] - OVAL_BOX[0]  # the band from the oval's box
    bh, bw = COUNT_ROWS, COUNT_INK_X[1] - COUNT_INK_X[0]
    eh, ew = shape[0], shape[1]
    ii = np.zeros((max(H, eh + dy + bh) + 1, max(W, ew + dx + bw) + 1), np.int32)
    ii[1 : H + 1, 1 : W + 1] = ink.cumsum(0).cumsum(1)
    ii[1 : H + 1, W + 1 :] = ii[1 : H + 1, W : W + 1]  # no ink beyond the frame
    ii[H + 1 :, :] = ii[H : H + 1, :]
    ys, xs = np.arange(eh)[:, None] + dy, np.arange(ew)[None, :] + dx
    s = ii[ys + bh, xs + bw] - ii[ys, xs + bw] - ii[ys + bh, xs] + ii[ys, xs]
    return np.asarray(s > 0)


def find_window(frame_bgr: Any, min_ovals: int = LATTICE_MIN) -> tuple[int, int] | None:
    """PURE: find_bag's origin only (is a bag open, and where), or None."""
    bag = find_bag(frame_bgr, min_ovals)
    return None if bag is None else bag.origin


def rows_at(frame_bgr: Any, origin: tuple[int, int]) -> int | None:
    """PURE: the rows of the bag at ``origin`` (cheap: the window's own cells and ring only), or
    None: the same rule as find_bag (_judge) with at least one empty cell, its top row the one at
    ``origin``. At most one row count can pass: its last cell is empty and the row below is not."""
    img = np.asarray(frame_bgr)
    x0 = max(0, origin[0] + DX0 - PITCH)  # the cells -1 .. COLS, rows -1 .. ROWS_MAX: no further
    y0 = max(0, origin[1] + DY0 - PITCH)
    x1 = max(x0, origin[0] + DX0 + PITCH * COLS + OVAL_BOX[2])
    y1 = max(y0, origin[1] + DY0 + PITCH * ROWS_MAX + OVAL_BOX[3])
    maps = cell_maps(img[y0:y1, x0:x1])
    want = np.arange(ROWS_MIN, ROWS_MAX + 1)
    ox = np.full(len(want), origin[0] - x0)
    rows, _count, _tight = _judge(maps, ox, origin[1] - y0 + PITCH * (want - 1), 1)
    hit = want[rows == want]
    return int(hit[0]) if len(hit) else None


def window_at(frame_bgr: Any, origin: tuple[int, int], rows: int | None = None) -> bool:
    """PURE: the bag is (still) at ``origin`` -- with ``rows`` rows, or any rows when None."""
    got = rows_at(frame_bgr, origin)
    return got is not None and (rows is None or got == rows)


def window_size(rows: int) -> tuple[int, int]:
    """PURE: the window's (w, h) from its origin, at ``rows`` rows."""
    return WINDOW_W, WINDOW_H_MIN + PITCH * (rows - ROWS_MIN)


def icon_xy(origin: tuple[int, int], slot: int) -> tuple[int, int]:
    c, r = slot % COLS, slot // COLS
    return origin[0] + ICON0[0] + PITCH * c, origin[1] + ICON0[1] + PITCH * r


def square(frame_bgr: Any, origin: tuple[int, int], slot: int) -> np.ndarray | None:
    """PURE: the slot's icon square (RGB float32), or None outside the frame."""
    x, y = icon_xy(origin, slot)
    img = np.asarray(frame_bgr)
    if x < 0 or y < 0 or y + SIZE > img.shape[0] or x + SIZE > img.shape[1]:
        return None
    return np.ascontiguousarray(img[y : y + SIZE, x : x + SIZE, 2::-1]).astype(np.float32)


def oval_share(sq: np.ndarray) -> float:
    dx, dy, w, h = OVAL_BOX
    box = sq[dy : dy + h, dx : dx + w]
    return float((np.abs(box - np.asarray(OVAL, np.float32)).sum(axis=2) <= OVAL_TOL).mean())


def empty_picture(frame_bgr: Any, origin: tuple[int, int], *, rows: int) -> np.ndarray | None:
    """PURE: THIS client's empty slot (RGB float32), from the tab's last cell when it shows the
    oval (items fill a tab in reading order, so the last cell is the likeliest empty one)."""
    for slot in range(COLS * rows - 1, -1, -1):
        sq = square(frame_bgr, origin, slot)
        if sq is not None and oval_share(sq) >= OVAL_SHARE:
            return sq
    return None


# --- which item, how many -----------------------------------------------------------------------
@dataclass(frozen=True)
class Pictures:
    """slot_items' reference pictures, compared on each picture's OWN pixels (its non-key ones):
    whatever the slot draws behind an icon -- the oval, the pink glow of a NEW item (a gradient,
    measured 255,131-165,247), the white face -- is left out (the lesson of gm_state's 10-29
    masked references). ``empty``: this client's empty slot, for the rival test's composites."""

    raw: np.ndarray  # (P, n, 3) float32: the pictures' colours over COMPARE
    mask: np.ndarray  # (P, n) bool: their own pixels
    comp: np.ndarray  # (P, n * 3) float32: composited over the empty slot (the rival test)
    ids: tuple[tuple[int, ...], ...]
    names: Mapping[int, str]

    @classmethod
    def over(cls, refs: Any, empty: np.ndarray) -> Pictures:
        import slot_items as si

        rgb = np.asarray(refs.rgb)[..., :3].astype(np.float32)
        key = np.stack([si.transparent(p) for p in np.asarray(refs.rgb)])
        comp = np.where(key[..., None], np.asarray(empty, np.float32)[None], rgb)
        return cls(rgb[:, COMPARE, :], ~key[:, COMPARE],
                   comp[:, COMPARE, :].reshape(len(comp), -1), refs.ids, refs.names)  # fmt: skip

    def distances(self, sq: np.ndarray) -> np.ndarray:
        """Each picture's mean |colour difference| over its own pixels."""
        o = np.asarray(sq, np.float32)[COMPARE, :][None]  # (1, n, 3)
        diff = np.abs(self.raw - o).mean(axis=2)  # (P, n)
        n = np.maximum(self.mask.sum(axis=1), 1)
        return np.asarray((diff * self.mask).sum(axis=1) / n)

    def unexplained(self, sq: np.ndarray, p: int, empty: np.ndarray) -> float:
        """The share of the square's pixels OUTSIDE picture ``p`` that are no slot background (not
        the empty slot's own colour, not the glow's pink, not white): an icon bigger than it."""
        o = np.asarray(sq, np.float32)[COMPARE, :]
        e = np.asarray(empty, np.float32)[COMPARE, :]
        bg = ((np.abs(o - e).sum(axis=1) <= BG_TOL)
              | glow_mask(o)
              | (o.min(axis=1) >= 235))  # fmt: skip
        out = ~self.mask[p]
        return float((out & ~bg).sum() / max(1, int(out.sum())))

    def pair(self, sq: np.ndarray, p: int, q: int) -> tuple[int, float]:
        a, b = self.comp[p].reshape(-1, 3), self.comp[q].reshape(-1, 3)
        apart = (np.abs(a - b).mean(axis=1) > DIFF_PX) & (self.mask[p] | self.mask[q])
        n = int(apart.sum())
        if n == 0:
            return 0, 0.0
        o = np.asarray(sq, np.float32)[COMPARE, :].reshape(-1, 3)[apart]
        e_p, e_q = float(np.abs(o - a[apart]).mean()), float(np.abs(o - b[apart]).mean())
        return n, (e_q - e_p) / float(np.abs(a[apart] - b[apart]).mean())

    def name(self, item: int) -> str:
        return self.names.get(item, f"item {item}")


@dataclass(frozen=True)
class BagSlot:
    slot: int
    kind: str  # "item" | "empty" | "unread"
    ids: tuple[int, ...] = ()
    count: int | None = None
    d1: float | None = None
    d2: float | None = None
    why: str = ""

    def record(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, (), "")}


def count_of_runs(runs: Sequence[tuple[int, int, str | None]]) -> int | None:
    """PURE: the count from a band's glyph runs ((first col, last col, the digit or None) in
    icon-relative columns), or None. A 4-digit shape is tried first, then 1-3 digits: the group's
    runs consecutive (at most DIGIT_GAP blank columns apart), every one a digit, its first and last
    columns one of COUNT_SHAPES, and NO ink within DIGIT_GAP + 1 columns before or after it (a
    covered or a neighbour's digit there: unread, never a shorter number); no leading zero."""
    for n in (4, 3, 2, 1):
        starts, last = COUNT_SHAPES[n]
        for i, (c0, _c1, _d) in enumerate(runs):
            if c0 not in starts or i + n > len(runs):
                continue
            grp = runs[i : i + n]
            if any(b[0] - a[1] - 1 > DIGIT_GAP for a, b in zip(grp, grp[1:], strict=False)):
                continue
            if grp[-1][1] != last or any(d is None for _a, _b, d in grp):
                continue
            before = runs[i - 1] if i > 0 else None
            after = runs[i + n] if i + n < len(runs) else None
            if before is not None and grp[0][0] - before[1] - 1 <= DIGIT_GAP:
                return None
            if after is not None and after[0] - grp[-1][1] - 1 <= DIGIT_GAP:
                return None
            text = "".join(str(d) for _a, _b, d in grp)
            return None if len(text) > 1 and text[0] == "0" else int(text)
    return None


def read_count(frame_bgr: Any, origin: tuple[int, int], slot: int,
               templates: Mapping[str, Any]) -> int | None:  # fmt: skip
    """PURE: the stack's count, or None: the band's pure-black glyphs (count_of_runs' shapes)."""
    import hotbar_count as hb

    x, y = icon_xy(origin, slot)
    img = np.asarray(frame_bgr)
    x0, x1 = x + COUNT_X0, x + COUNT_X1
    if x0 < 0 or x1 > img.shape[1] or y + COUNT_DY + COUNT_ROWS > img.shape[0]:
        return None
    band = img[y + COUNT_DY : y + COUNT_DY + COUNT_ROWS, x0:x1, :3]
    runs = [(c + COUNT_X0, c + COUNT_X0 + g.shape[1] - 1, hb.match(g, templates))
            for c, g in hb.glyph_runs(band.max(axis=2) <= COUNT_INK)]  # fmt: skip
    return count_of_runs(runs)


def read_slot(frame_bgr: Any, origin: tuple[int, int], slot: int, pics: Pictures,
              empty: np.ndarray, templates: Mapping[str, Any]) -> BagSlot:  # fmt: skip
    """PURE: what the slot shows."""
    sq = square(frame_bgr, origin, slot)
    if sq is None:
        return BagSlot(slot, "unread", why="the slot is outside the frame")
    if float(np.abs(sq - empty).mean()) <= EMPTY_MAX:
        return BagSlot(slot, "empty")
    d = pics.distances(sq)
    order = [int(i) for i in np.argsort(d)]
    best = order[0]
    d1 = float(d[best])
    group, rivals = [best], []
    for p in order[1:TOP_K]:
        if float(d[p]) > d1 + RIVAL_RANGE:
            break
        n, lead = pics.pair(sq, best, p)
        if n < DISCRIM_MIN:
            group.append(p)
        else:
            rivals.append((p, lead))
    rest = next((p for p in order if p not in group), None)
    d2 = float(d[rest]) if rest is not None else None
    ids = tuple(sorted({i for p in group for i in pics.ids[p]}))
    if d1 > NAME_MAX:
        return BagSlot(slot, "unread", ids, None, d1, d2,
                       f"no known icon (the nearest {pics.name(ids[0])} at {d1:.1f})")  # fmt: skip
    extra = pics.unexplained(sq, best, empty)
    if extra > UNEXPLAINED_MAX:
        return BagSlot(
            slot,
            "unread",
            ids,
            None,
            d1,
            d2,
            f"the icon has pixels {pics.name(ids[0])}'s picture lacks ({extra:.2f})",
        )
    pm = min((m for _p, m in rivals), default=float("inf"))
    if pm < PAIR_LEAD:
        return BagSlot(slot, "unread", ids, None, d1, d2, f"two icons alike (lead {pm:.2f})")
    n = read_count(frame_bgr, origin, slot, templates)
    if n is None:
        return BagSlot(slot, "unread", ids, None, d1, d2, "the count did not read")
    return BagSlot(slot, "item", ids, n, d1, d2)


def read_tab(frame_bgr: Any, origin: tuple[int, int], pics: Pictures, empty: np.ndarray,
             templates: Mapping[str, Any], *, rows: int) -> list[BagSlot]:  # fmt: skip
    """PURE: every slot of the open tab (7 x ``rows``, the found window's); after the first empty
    slot every later slot must be empty (items fill a tab in reading order), else that slot is
    unread."""
    out, seen_empty = [], False
    for s in range(COLS * rows):
        b = read_slot(frame_bgr, origin, s, pics, empty, templates)
        if b.kind == "empty":
            seen_empty = True
        elif seen_empty:
            b = BagSlot(s, "unread", b.ids, b.count, b.d1, b.d2,
                        f"{b.kind} after an empty slot (a pointer or a tooltip?)")  # fmt: skip
        out.append(b)
    return out


@dataclass
class TabRead:
    tab: str
    slots: list[BagSlot] = field(default_factory=list)

    @property
    def full(self) -> bool:
        return all(b.kind != "empty" for b in self.slots)

    def items(self) -> list[BagSlot]:
        return [b for b in self.slots if b.kind == "item"]

    def unread(self) -> list[BagSlot]:
        return [b for b in self.slots if b.kind == "unread"]

    def record(self) -> dict[str, Any]:
        return {"tab": self.tab, "full": self.full,
                "items": [b.record() for b in self.items()],
                "unread": [b.record() for b in self.unread()]}  # fmt: skip


def bag_totals(tabs: Sequence[TabRead]) -> dict[str, int]:
    """PURE: {item key: count}; a shared icon's group is one key ("2401|2402")."""
    out: Counter[str] = Counter()
    for t in tabs:
        for b in t.items():
            out["|".join(str(i) for i in b.ids)] += int(b.count or 0)
    return dict(out)


# --- the census (live) --------------------------------------------------------------------------
def _real_client(r: Any) -> tuple[int, int, int, int]:
    """The real client's rect on the desktop (the virtual view's, else the game region)."""
    if r.virtual_active():
        x, y, w, h = r.client_view().rect
        return int(x), int(y), int(w), int(h)
    x, y, w, h = r.game_region()
    return int(x), int(y), int(w), int(h)


def _grab(r: Any, screen: Any, box: tuple[int, int, int, int] | None = None) -> np.ndarray:
    """The real client (client px), or only ``box`` (x, y, w, h in client px) of it: a whole
    1920x1080 frame through the grab pipe is ~8 MB, the bag's box ~0.4 MB."""
    x, y, w, h = _real_client(r)
    if box is not None:
        bx, by, bw, bh = box
        x0, y0 = max(0, bx), max(0, by)
        x1, y1 = min(w, bx + bw), min(h, by + bh)
        _, img = screen.grab(x + x0, y + y0, x1 - x0, y1 - y0)
        out = np.zeros((bh, bw, 3), np.uint8)  # outside the client: black (no oval there)
        out[y0 - by : y1 - by, x0 - bx : x1 - bx] = np.asarray(img)[..., :3]
        return out
    _, img = screen.grab(x, y, w, h)
    return np.ascontiguousarray(np.asarray(img)[..., :3])


AROUND = 2 * PITCH  # the margin grabbed around the bag (its ring check reaches one pitch out)


def bag_box(origin: tuple[int, int], rows: int) -> tuple[int, int, int, int]:
    """PURE: the client box grabbed once the bag's place is known: the window (7 x ``rows``; a
    look for a bag of unknown rows passes ROWS_MAX) and AROUND."""
    w = ICON0[0] + PITCH * COLS + 2 * AROUND
    h = ICON0[1] + PITCH * rows + 2 * AROUND
    return origin[0] - AROUND, origin[1] - AROUND, w, h


def _save_box(frame_bgr: Any, origin: tuple[int, int], rows: int, path: Path) -> None:
    """The bag's window only (a lab trial's evidence: our own character; never in a Run)."""
    from PIL import Image

    x, y = origin
    w, h = window_size(rows)
    box = np.asarray(frame_bgr)[max(0, y) : y + h + 5, max(0, x) : x + w + 10, 2::-1]
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.ascontiguousarray(box)).save(path)


def _click(agent: Any, r: Any, cx: int, cy: int) -> None:
    """A paced two-motion click at client px (a cold-jump UI click is ignored)."""
    x0, y0, _, _ = _real_client(r)
    x, y = x0 + cx, y0 + cy
    agent.move(x + 3, y + 3)
    time.sleep(0.15)
    agent.move(x, y)
    time.sleep(0.6)
    agent.click(x, y)


def grid_signature(frame_bgr: Any, origin: tuple[int, int], *, rows: int) -> np.ndarray:
    """PURE: each slot square's mean colour (7 x ``rows``, 3): what changes when another tab
    shows."""
    out = np.zeros((COLS * rows, 3), np.float32)
    for s in range(COLS * rows):
        sq = square(frame_bgr, origin, s)
        if sq is not None:
            out[s] = sq.reshape(-1, 3).mean(axis=0)
    return out


TAB_WAIT_S = 0.9  # the longest wait for a clicked tab's slots to change (the old fixed wait)


def shared_items(tabs: Sequence[TabRead]) -> dict[str, set[int]]:
    """PURE: per tab, its item ids that an EARLIER tab holds too. Every item is in one tab only
    (its type's, or Fav), so a shared id means a tab click did not take (the old tab read again)."""
    seen: set[int] = set()
    out: dict[str, set[int]] = {}
    for t in tabs:
        ids = {i for b in t.items() for i in b.ids}
        dup = ids & seen
        if dup:
            out[t.tab] = dup
        seen |= ids
    return out


def _park(agent: Any, r: Any) -> None:
    x0, y0, w, h = _real_client(r)
    agent.move(x0 + min(PARK[0], w - 1), y0 + min(PARK[1], h - 1))
    time.sleep(0.25)


def census(agent: Any, screen: Any, *, refs: Any | None = None,
           templates: Mapping[str, Any] | None = None,
           frames_dir: Path | None = None) -> dict[str, Any]:  # fmt: skip
    """Open the bag (unless it is open), read every tab twice (the reads must agree), and leave it
    as it was found (closed again with Alt+E when the census opened it). r.Stop on anything
    unexpected; the bag is closed first when the census opened it."""
    import hotbar_count as hb
    import ro_agent as r
    import slot_items as si
    import ui_gate

    t0 = time.monotonic()
    refs = refs or si.SlotRefs.load()
    templates = templates if templates is not None else hb.load()
    keys = ui_gate.window_keys("inventory")
    r.activate_client(agent, screen)
    _park(agent, r)
    was_open = find_bag(_grab(r, screen)) is not None  # left as it was found (B3)
    if not was_open:
        agent.chord(*keys)
        time.sleep(1.2)
    out: dict[str, Any] = {"tabs": [], "origin": None, "rows": None, "was_open": was_open}
    opened = not was_open
    try:
        f = _grab(r, screen)
        found = find_bag(f)
        if found is None:
            raise r.Stop(f"bag_count: Alt+E showed no bag (no oval lattice of {COLS} x "
                         f"{ROWS_MIN}..{ROWS_MAX} found)")  # fmt: skip
        origin, rows = found.origin, found.rows  # the window's rows: every tab has the same
        out["origin"], out["rows"] = list(origin), rows
        box = bag_box(origin, rows)
        local = (AROUND, AROUND)  # the origin inside the box
        here = Bag(local, rows)
        empty = empty_picture(f, origin, rows=rows)
        pics = None if empty is None else Pictures.over(refs, empty)
        tabs: list[TabRead] = []
        before = grid_signature(f, origin, rows=rows)

        def read_one(name: str, tx: int, ty: int, before: np.ndarray) -> tuple[TabRead, Any]:
            nonlocal empty, pics
            _click(agent, r, origin[0] + tx, origin[1] + ty)
            _park(agent, r)
            t_end = time.monotonic() + TAB_WAIT_S  # until its slots change, or the old wait
            while time.monotonic() < t_end:
                g = _grab(r, screen, box)
                if np.abs(grid_signature(g, local, rows=rows) - before).max() > 2.0:
                    break
                time.sleep(0.1)
            reads = []
            for _ in range(2):
                f = _grab(r, screen, box)  # the bag's box only (its place is known)
                # its own cells (and rows); a full tab shows no oval: then no lattice ELSEWHERE
                # in the box. Another tab showing other rows is another window: the bag moved
                if not window_at(f, local, rows) and find_bag(f) not in (here, None):
                    raise r.Stop("bag_count: the bag moved while it was read")
                if empty is None:  # no empty slot seen yet: this tab may show one
                    empty = empty_picture(f, local, rows=rows)
                    pics = None if empty is None else Pictures.over(refs, empty)
                if frames_dir is not None:  # the lab's trials only: the bag's own box, per read
                    _save_box(f, local, rows, frames_dir / f"{name}-{len(reads)}.png")
                if pics is None or empty is None:
                    reads.append(None)
                else:
                    reads.append(read_tab(f, local, pics, empty, templates, rows=rows))
                time.sleep(0.2)
            tab = TabRead(name)
            if reads[0] is None or reads[1] is None:
                tab.slots = [BagSlot(s, "unread", why="no empty slot seen to compare with")
                             for s in range(COLS * rows)]  # fmt: skip
            else:
                for a, b in zip(reads[0], reads[1], strict=True):
                    same = (a.kind, a.ids, a.count) == (b.kind, b.ids, b.count)
                    why = "two reads disagree"
                    tab.slots.append(a if same else BagSlot(a.slot, "unread", a.ids, None, a.d1,
                                                            a.d2, why))  # fmt: skip
            return tab, f

        for name, (tx, ty) in TABS.items():
            tab, last = read_one(name, tx, ty, before)
            if shared_items([*tabs, tab]).get(name):  # the click did not take: once more
                tab, last = read_one(name, tx, ty, before)
                dup = shared_items([*tabs, tab]).get(name)
                if dup:
                    why = "an earlier tab's item: the tab click did not take"
                    tab.slots = [
                        b
                        if not set(b.ids) & dup
                        else BagSlot(b.slot, "unread", b.ids, None, b.d1, b.d2, why)
                        for b in tab.slots
                    ]
            tabs.append(tab)
            before = grid_signature(last, local, rows=rows)
        out["tabs"] = [t.record() for t in tabs]
        out["totals"] = bag_totals(tabs)
        out["unread"] = sum(len(t.unread()) for t in tabs)
        out["full_tabs"] = [t.tab for t in tabs if t.full]
    finally:
        if opened:
            agent.chord(*keys)
            time.sleep(1.0)
            _park(agent, r)
        out["closed"] = find_bag(_grab(r, screen)) is None
    out["seconds"] = round(time.monotonic() - t0, 1)
    out["as_found"] = out["closed"] != was_open
    if not out["as_found"]:
        raise r.Stop(
            f"bag_count: the bag is {'open' if not out['closed'] else 'closed'} after "
            f"the census; it was {'open' if was_open else 'closed'}"
        )
    return out


# --- the lab's truth and the pre-registered bar ---------------------------------------------------
def truth(char: str) -> dict[str, int]:
    """The lab database's bag of ``char`` (read only): {item id: amount}, worn equipment left out
    (it is not in the bag's tabs)."""
    import ro_agent as r

    if not char.replace("_", "").isalnum():
        raise SystemExit("--char: letters, digits and _ only")
    rows = r.db_query("SELECT i.nameid, i.amount FROM inventory i JOIN `char` c ON c.char_id = "
                      f"i.char_id WHERE c.name = '{char}' AND i.equip = 0;")  # fmt: skip
    out: Counter[int] = Counter()
    for nameid, amount in rows:
        out[int(nameid)] += int(amount)
    return dict(out)


def judge(read: Mapping[str, Any], true: Mapping[int, int]) -> dict[str, Any]:
    """PURE: the plan's B1 (0 wrong), B2 (>= 98 % read), B3 (closed), B4 (<= 20 s, <= 40
    entries). A group key is right when the true item is in it; a group matched twice (two true
    items alike) is split by its total."""
    left = dict(true)
    wrong, right = [], 0
    for key, n in read.get("totals", {}).items():
        ids = [int(i) for i in key.split("|")]
        have = [i for i in ids if i in left]
        if not have:
            wrong.append({"read": key, "count": n, "why": "no such item in the bag"})
            continue
        total = sum(left[i] for i in have)
        if total != n:
            wrong.append({"read": key, "count": n, "true": {i: left[i] for i in have}})
        else:
            right += len(have)
        for i in have:
            left.pop(i, None)
    entries = len(true)
    read_share = right / entries if entries else 1.0
    b4_applies = entries <= 40
    return {
        "entries": entries,
        "right": right,
        "wrong": wrong,
        "missed": sorted(left),
        "unread_slots": read.get("unread"),
        "B1_no_wrong": not wrong,
        "B2_read_98": read_share >= 0.98,
        "read_share": round(read_share, 4),
        "B3_as_found": bool(read.get("as_found")),
        "B4_20s": (read.get("seconds") or 1e9) <= 20.0 if b4_applies else None,
    }


def _load_frame(path: Path) -> np.ndarray:
    from PIL import Image

    rgb = np.asarray(Image.open(path).convert("RGB"))
    return np.ascontiguousarray(rgb[..., ::-1])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=("read", "census", "truth", "trial"))
    ap.add_argument("image", nargs="?", type=Path)
    ap.add_argument("--refs", type=Path, default=None)
    ap.add_argument("--char", default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument(
        "--frames",
        type=Path,
        default=None,
        help="LAB TRIALS ONLY: save the bag's box per tab read (our own character)",
    )
    a = ap.parse_args(argv)
    import hotbar_count as hb
    import slot_items as si

    refs = si.SlotRefs.load(a.refs) if a.refs else None
    if a.cmd == "truth":
        if not a.char:
            raise SystemExit("truth needs --char")
        print(json.dumps(truth(a.char), sort_keys=True))
        return 0
    if a.cmd == "read":
        if a.image is None:
            raise SystemExit("read needs IMAGE")
        f = _load_frame(a.image)
        found = find_bag(f)
        if found is None:
            print(json.dumps({"origin": None, "why": "no bag lattice"}))
            return 2
        origin, rows = found.origin, found.rows
        empty = empty_picture(f, origin, rows=rows)
        if empty is None:
            print(json.dumps({"origin": list(origin), "rows": rows,
                              "why": "no empty slot to compare with"}))  # fmt: skip
            return 2
        pics = Pictures.over(refs or si.SlotRefs.load(), empty)
        tab = TabRead("shown", read_tab(f, origin, pics, empty, hb.load(), rows=rows))
        print(json.dumps({"origin": list(origin), "rows": rows, **tab.record(),
                          "totals": bag_totals([tab])}))  # fmt: skip
        return 0
    import ro_agent as r

    agent = r.Agent("bag_count")
    screen = r.Screen()
    got = census(agent, screen, refs=refs, frames_dir=a.frames)
    doc: dict[str, Any] = {"census": got}
    if a.cmd == "trial":
        if not a.char:
            raise SystemExit("trial needs --char")
        true = truth(a.char)
        doc.update({"truth": {str(k): v for k, v in sorted(true.items())},
                    "verdict": judge(got, true)})  # fmt: skip
    text = json.dumps(doc, indent=1, sort_keys=True)
    if a.out:
        a.out.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
