"""Client signboards from pixels (Batt, 2026-10-08): the floating board the client draws over some
NPCs, a small ICON SQUARE with a TITLE BAR attached to its right.

Both parts are drawn by the client's UI layer, not the world renderer, so each has a crisp 1-px
BLACK outline with a 1-px WHITE halo outside it. Floors, wood, robes and pianos have warm colours
like a sign's, but never that outline. A sign is found by its SHAPE:
- a rectangle is a top edge (black, white directly above) and a bottom edge (black, white directly
  below) spanning the same columns, with black left and right outlines between them;
- the icon is a near-square of a sign's size; its 3-px frame is mostly orange;
- the bar is attached to the icon's right edge, vertically inside the icon's span, and its inside
  is filled with the bar's dark brown (and the title's white text);
- nothing larger than a sign can be is ever returned;
- optionally (``npcs``), the sign must float just above an NPC detection.

A union of every warm pixel in view (the first finder) put one giant false box over half the church
in 194 of 224 banked walk@12 frames; this one is the replacement for every user.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

# pixel classes (RGB); the outline is drawn, so it is pure in a lossless grab
BLACK_MAX = 50  # every channel at most this
WHITE_MIN = 200  # every channel at least this
MIN_EDGE = 18  # px: the shortest outline run that can be a sign part
EDGE_SLACK = 3  # px: a top and a bottom run of one rectangle may differ by this at either end
# the fraction of a rectangle's side outline column that is black (our own HP/SP bar crossing a
# sign's icon covers 9 of its 29 outline rows: 0.69)
SIDE_FILL = 0.6

# the icon square (outline to outline, client px; measured 31 x 32 on the wedding NPC's sign)
ICON_SIDE = (24, 40)
ICON_ASPECT = (0.8, 1.25)  # width / height
ICON_FRAME_ORANGE = 0.6  # its 3-px frame inside the outline

# the title bar (measured 130 x 24 on the same sign); its length follows the title
BAR_HEIGHT = (0.55, 0.95)  # x the icon's height
BAR_WIDTH = (30, 360)
BAR_ATTACH = 4  # px: the bar's left outline within this of the icon's right outline
BAR_FILL = 0.75  # its inside (inset 4 px) that is the bar's brown or the title's white

# the whole sign can never be larger than this (Batt: "reject anything larger than a sign can be")
SIGN_MAX = (400, 44)  # w, h

# a sign with more than this fraction of its box inside a UI window is the window's, not the world's
EXCLUDE_OVERLAP = 0.25

# the NPC under its sign (measured on the wedding NPC's sign, 45 banked frames: the NPC box's top
# 93-102 px below the sign's bottom, its centre -8..+10 px from the sign's centre). The windows are
# wider than that, because a sign's height over its NPC is set per sign by the client.
NPC_GAP = (40, 160)  # px from the sign's bottom down to the NPC box's top
NPC_X = 40  # px: the NPC box's centre within this of the sign's centre
# where the NPC must be is OBSERVABLE only when that whole zone (NPC_GAP, plus this much of the NPC
# under its top) is in the image and at most NPC_COVERED of it under a UI window; otherwise the
# shape alone decides (the NPC cannot be seen there)
NPC_SEEN = (36, 60)  # w, h px
NPC_COVERED = 0.25


@dataclass(frozen=True)
class Rect:
    x0: int
    y0: int
    x1: int  # inclusive: the outline's own column / row
    y1: int

    @property
    def w(self) -> int:
        return self.x1 - self.x0 + 1

    @property
    def h(self) -> int:
        return self.y1 - self.y0 + 1


@dataclass(frozen=True)
class Sign:
    icon: Rect
    bar: Rect

    @property
    def box(self) -> Rect:
        return Rect(
            self.icon.x0,
            min(self.icon.y0, self.bar.y0),
            self.bar.x1,
            max(self.icon.y1, self.bar.y1),
        )


Bool2 = npt.NDArray[np.bool_]


def _runs(mask: Bool2) -> list[tuple[int, int, int]]:
    """Horizontal runs of True as (y, x_start, x_end inclusive), row-major."""
    pad = np.zeros((mask.shape[0], mask.shape[1] + 2), np.int8)
    pad[:, 1:-1] = mask
    d = np.diff(pad, axis=1)
    sy, sx = np.nonzero(d == 1)
    ey, ex = np.nonzero(d == -1)
    return [(int(y), int(a), int(b) - 1) for y, a, b in zip(sy, sx, ex, strict=True)]


def _rects(black: Bool2, white: Bool2) -> list[tuple[Rect, float, float]]:
    """Every outlined rectangle of a sign part's possible size, with the black fill of its left and
    right outline columns (at least one of them a side)."""
    top = np.zeros_like(black)
    bot = np.zeros_like(black)
    top[1:] = black[1:] & white[:-1]
    bot[:-1] = black[:-1] & white[1:]
    tops = [r for r in _runs(top) if r[2] - r[1] + 1 >= MIN_EDGE]
    bots = [r for r in _runs(bot) if r[2] - r[1] + 1 >= MIN_EDGE]
    out: list[tuple[Rect, float, float]] = []
    for ty, ta, tb in tops:
        for by, ba, bb in bots:
            h = by - ty + 1
            if not (ICON_SIDE[0] * BAR_HEIGHT[0] <= h <= SIGN_MAX[1]):
                continue
            if abs(ta - ba) > EDGE_SLACK or abs(tb - bb) > EDGE_SLACK:
                continue
            x0, x1 = min(ta, ba), max(tb, bb)
            if x1 - x0 + 1 > SIGN_MAX[0]:
                continue
            # the side outlines: the most-black column within EDGE_SLACK of each end (the corners
            # are cut, so a side sits up to 2 px outside its top and bottom runs)
            inner = black[ty + 2 : by - 1]
            lo, hi = max(0, x0 - EDGE_SLACK), min(black.shape[1], x0 + EDGE_SLACK + 1)
            fill = inner[:, lo:hi].mean(axis=0)
            left, lx = float(fill.max()), lo + int(fill.argmax())
            lo, hi = max(0, x1 - EDGE_SLACK), min(black.shape[1], x1 + EDGE_SLACK + 1)
            fill = inner[:, lo:hi].mean(axis=0)
            right, rx = float(fill.max()), lo + int(fill.argmax())
            if max(left, right) >= SIDE_FILL:
                out.append((Rect(lx, ty, rx, by), left, right))
    return out


def _orange(rgb: npt.NDArray[np.int32]) -> Bool2:
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return (r > 140) & (r - b > 80) & (g > 70) & (g < 230)


def _bar_inside(rgb: npt.NDArray[np.int32]) -> Bool2:
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    brown = (r > 70) & (r < 140) & (g > 45) & (g < 105) & (b < 70) & (r > b + 30)
    text = rgb.min(axis=-1) > WHITE_MIN
    return brown | text


def _is_icon(rgb: npt.NDArray[np.int32], r: Rect) -> bool:
    if not (ICON_SIDE[0] <= r.h <= ICON_SIDE[1] and ICON_SIDE[0] <= r.w <= ICON_SIDE[1]):
        return False
    if not (ICON_ASPECT[0] <= r.w / r.h <= ICON_ASPECT[1]):
        return False
    inner = rgb[r.y0 + 1 : r.y1, r.x0 + 1 : r.x1]
    ring = np.ones(inner.shape[:2], bool)
    ring[3:-3, 3:-3] = False  # the 3-px frame
    return float(_orange(inner)[ring].mean()) >= ICON_FRAME_ORANGE


def _is_bar(rgb: npt.NDArray[np.int32], r: Rect, icon: Rect) -> bool:
    if not (BAR_HEIGHT[0] * icon.h <= r.h <= BAR_HEIGHT[1] * icon.h):
        return False
    if not (BAR_WIDTH[0] <= r.w <= BAR_WIDTH[1]):
        return False
    if abs(r.x0 - icon.x1) > BAR_ATTACH or r.y0 < icon.y0 or r.y1 > icon.y1:
        return False
    inner = rgb[r.y0 + 4 : r.y1 - 3, r.x0 + 4 : r.x1 - 3]
    return inner.size > 0 and float(_bar_inside(inner).mean()) >= BAR_FILL


def _overlap(r: Rect, e: Sequence[int]) -> int:
    w = min(r.x1 + 1, e[2]) - max(r.x0, e[0])
    h = min(r.y1 + 1, e[3]) - max(r.y0, e[1])
    return max(0, w) * max(0, h)


def _npc_observable(sign: Rect, shape: tuple[int, int], exclude: Sequence[Sequence[int]]) -> bool:
    cx = (sign.x0 + sign.x1) // 2
    w, h = NPC_SEEN
    need = Rect(cx - w // 2, sign.y1 + NPC_GAP[0], cx + w // 2, sign.y1 + NPC_GAP[1] + h)
    if need.x0 < 0 or need.y0 < 0 or need.x1 >= shape[1] or need.y1 >= shape[0]:
        return False
    return not any(_overlap(need, e) > NPC_COVERED * need.w * need.h for e in exclude)


def _over_npc(sign: Rect, npcs: Sequence[Sequence[float]]) -> bool:
    cx = (sign.x0 + sign.x1) / 2
    for x0, y0, x1, _y1 in npcs:
        if abs((x0 + x1) / 2 - cx) <= NPC_X and NPC_GAP[0] <= y0 - sign.y1 <= NPC_GAP[1]:
            return True
    return False


def find_signs(
    img: npt.NDArray[np.uint8],
    search: tuple[int, int, int, int] | None = None,
    npcs: Sequence[Sequence[float]] | None = None,
    exclude: Sequence[Sequence[int]] = (),
) -> list[Sign]:
    """Every signboard in ``img`` (BGR or BGRA, client px), in that image's coordinates.

    ``search`` (x0, y0, x1, y1) limits the look to part of the image. ``exclude`` (the same form,
    image px) are the UI windows, where the client draws its own outlined boxes and icons: a sign
    with more than ``EXCLUDE_OVERLAP`` of its box inside one is dropped (one that only touches a
    window is kept). ``npcs`` (boxes x0, y0, x1, y1, image px) keeps a sign only with an NPC
    detected under it, wherever that NPC could be seen (in the image, not under a UI window); a
    sign whose NPC would be off-screen or covered is kept on its shape. None: the shape alone."""
    rgb = img[..., 2::-1].astype(np.int32)
    ox = oy = 0
    if search is not None:
        sx0, sy0, sx1, sy1 = search
        rgb, ox, oy = rgb[sy0:sy1, sx0:sx1], sx0, sy0
    black = rgb.max(axis=-1) <= BLACK_MAX
    white = rgb.min(axis=-1) >= WHITE_MIN
    rects = _rects(black, white)
    icons = [r for r, lf, rf in rects if min(lf, rf) >= SIDE_FILL and _is_icon(rgb, r)]
    out: list[Sign] = []
    for icon in icons:
        # a bar's left outline IS the icon's right one (proved with the icon), so only its right
        # side is asked for: our own HP/SP bar can cross both where they meet
        bars = [r for r, _lf, rf in rects
                if r != icon and rf >= SIDE_FILL and _is_bar(rgb, r, icon)]  # fmt: skip
        if not bars:
            continue
        bar = max(bars, key=lambda r: r.w)
        s = Sign(
            Rect(icon.x0 + ox, icon.y0 + oy, icon.x1 + ox, icon.y1 + oy),
            Rect(bar.x0 + ox, bar.y0 + oy, bar.x1 + ox, bar.y1 + oy),
        )
        b = s.box
        if b.w > SIGN_MAX[0] or b.h > SIGN_MAX[1]:
            continue
        if any(_overlap(b, e) > EXCLUDE_OVERLAP * b.w * b.h for e in exclude):
            continue
        seen = _npc_observable(b, img.shape[:2], exclude)
        if npcs is not None and seen and not _over_npc(b, npcs):
            continue
        out.append(s)
    return out
