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

- 7 x 6 slots on a 32 px pitch; slot (0, 0)'s icon is the 24 x 24 square at the window's origin +
  ICON0. An EMPTY slot shows an oval (OVAL's colour; its box OVAL_BOX in the square). The oval is
  drawn behind an item too, so the pictures are composited over THIS client's own empty slot, cut
  at run time from an empty slot of the open bag (any skin, no stored client pixels).
- The count: PURE BLACK digits (max channel <= COUNT_INK; an icon's darkest outline is 8),
  left-aligned from the icon's x + 14, rows +18 .. +26, in the hotbar's glyphs (hotbar_count).
- Four tabs on the left (TABS, from the window's origin): Use, Eqp, Etc, Fav.

The window is FOUND by the lattice of empty-slot ovals (a rule: no template, no text, any
language): the 7 x 6 placement with the most ovals, and NO oval one pitch outside it on any side
(a placement shifted by a column would see the real last column's ovals there).

Never guessed: a slot is "item" (its ids -- a shared icon is a group -- and its count), "empty", or
"unread" with the reason. Items fill a tab in reading order, so an item after an empty slot is an
anomaly (a pointer, a tooltip): unread. A tab whose 42 slots are all items may hold more ("full").
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
COLS, ROWS = 7, 6
SLOTS = COLS * ROWS
ICON0 = (44, 21)  # slot (0, 0)'s icon square, from the window's origin (its title bar's top-left)
OVAL = (206, 214, 231)  # an empty slot's oval (RGB)
OVAL_TOL = 30  # a pixel within this (sum of |RGB - OVAL|) is oval-coloured
# the oval's BOUNDING BOX in the icon square (dx, dy, w, h): its OVAL_TOL pixels span rows 11-20
# and columns 1-22 (measured on 35 empty cells); the box is tight, so "the oval touches all four
# edges" holds only at its exact place
OVAL_BOX = (1, 11, 22, 10)
OVAL_SHARE = 0.6  # an empty cell's box is at least this oval-coloured (an ellipse fills ~0.78)
LATTICE_MIN = 2  # the bag is found by at least this many empty-slot ovals
TABS: dict[str, tuple[int, int]] = {"use": (10, 45), "eqp": (10, 100), "etc": (10, 154),
                                    "fav": (10, 205)}  # fmt: skip
COUNT_DY, COUNT_ROWS = 18, 9  # the digits' rows from the icon's top
# the count's place (measured 2026-11-20 on 1 / 2 / 4-digit stacks): it starts at the icon's x + 14
# (+ 15 for a leading '1', drawn a column in) unless it would pass x + 26: then it ENDS at x + 26
# ("8" 14-19, "46" 14-26, "1001" 1-26). The band stops before the next slot (its count can start
# at its own x + 0 = our x + 32)
COUNT_X0, COUNT_X1 = 0, 28
COUNT_FIRST = (14, 15)  # a 1- or 2-digit count's first glyph column
COUNT_END = 26  # a 2+ digit count's last ink column
COUNT_INK = 3  # a count pixel is pure black: max channel <= this
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
    """PURE: the icon square's compared pixels: not the count's rows and columns."""
    keep = np.ones((SIZE, SIZE), bool)
    keep[COUNT_DY - 1 :, COUNT_X0:] = False
    return keep


COMPARE = _compare_mask()


# --- where the bag is ---------------------------------------------------------------------------
def rgb_of(frame_bgr: Any) -> np.ndarray:
    return np.ascontiguousarray(np.asarray(frame_bgr)[..., 2::-1]).astype(np.int16)


def oval_mask(frame_bgr: Any) -> np.ndarray:
    """PURE: the frame's oval-coloured pixels."""
    rgb = rgb_of(frame_bgr)
    return np.asarray(np.abs(rgb - np.asarray(OVAL, np.int16)).sum(axis=2) <= OVAL_TOL)


def oval_cells(frame_bgr: Any) -> tuple[np.ndarray, np.ndarray]:
    """PURE: for an oval box (OVAL_BOX's size) with its top-left at (y, x): (empty, tight).
    ``empty``: at least OVAL_SHARE of it is oval-coloured. ``tight``: the oval touches all four
    of the box's edges -- only at the oval's exact place (the box is the oval's bounding box), so
    the share, which holds over +-2 px, does not pick the place alone."""
    m = oval_mask(frame_bgr).astype(np.int32)
    w, h = OVAL_BOX[2], OVAL_BOX[3]
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


def find_window(frame_bgr: Any, min_ovals: int = LATTICE_MIN) -> tuple[int, int] | None:
    """PURE: the bag's window origin on a real-client frame, by its oval lattice, or None.

    A 7 x 6 placement is a bag when its EMPTY cells are the TAIL of its cells in reading order
    (items fill a tab from its first slot: a placement a row or a column off sees non-oval cells
    after its ovals, or ovals in the ring one pitch outside it), at least ``min_ovals`` of them,
    and the ring is clear. Among those: the most empty cells, then the most TIGHT ones (the exact
    pixel). Another as good more than half a pitch away = two bags alike: None."""
    empty, tight = oval_cells(frame_bgr)
    dx0, dy0 = ICON0[0] + OVAL_BOX[0], ICON0[1] + OVAL_BOX[1]  # a cell's oval box from the origin
    H, W = empty.shape
    # a ring cell beyond the frame shows no oval (a bag pushed to a screen edge): pad with False
    P = PITCH * 2
    empty = np.pad(empty, P)
    tight = np.pad(tight, P)
    # the tail rule makes the LAST cell empty: only origins whose last cell sits on an oval box
    # are candidates (a few hundred, not every pixel)
    ly, lx = dy0 + PITCH * (ROWS - 1), dx0 + PITCH * (COLS - 1)
    ys, xs = np.nonzero(empty[P : P + H, P : P + W])
    oy, ox = ys - ly, xs - lx
    keep = (ox + dx0 >= 0) & (oy + dy0 >= 0)  # the lattice's own cells inside the frame
    oy, ox = oy[keep] + P, ox[keep] + P  # in the padded arrays
    if len(oy) == 0:
        return None
    cells = [(c, r) for r in range(ROWS) for c in range(COLS)]
    ring = [(c, r) for r in range(-1, ROWS + 1) for c in range(-1, COLS + 1)
            if not (0 <= r < ROWS and 0 <= c < COLS)]  # fmt: skip
    cy = np.array([dy0 + PITCH * r for _c, r in cells])
    cx = np.array([dx0 + PITCH * c for c, _r in cells])
    e = empty[oy[:, None] + cy[None], ox[:, None] + cx[None]]  # (N, 42) in reading order
    t = tight[oy[:, None] + cy[None], ox[:, None] + cx[None]]
    ry = np.array([dy0 + PITCH * r for _c, r in ring])
    rx = np.array([dx0 + PITCH * c for c, _r in ring])
    outside = empty[oy[:, None] + ry[None], ox[:, None] + rx[None]].any(axis=1)
    count = e.sum(axis=1)
    trail = np.cumprod(e[:, ::-1], axis=1).sum(axis=1)  # the trailing run of empty cells
    ok = (count >= min_ovals) & (trail == count) & ~outside
    if not ok.any():
        return None
    best = int(count[ok].max())
    snug = np.where(ok & (count == best), (e & t).sum(axis=1), -1)
    k = int(np.argmax(snug))
    same = snug == snug[k]
    if np.any((np.abs(oy[same] - oy[k]) > PITCH // 2) | (np.abs(ox[same] - ox[k]) > PITCH // 2)):
        return None
    return int(ox[k]) - P, int(oy[k]) - P


def window_at(frame_bgr: Any, origin: tuple[int, int]) -> bool:
    """PURE: the bag is still at ``origin`` (cheap: its own cells only): at least one empty cell,
    the empty cells a tail of its cells, the ring clear -- the same rule as find_window."""
    sh = np.asarray(frame_bgr).shape
    flags = []
    for r in range(-1, ROWS + 1):
        for c in range(-1, COLS + 1):
            x = origin[0] + ICON0[0] + OVAL_BOX[0] + PITCH * c
            y = origin[1] + ICON0[1] + OVAL_BOX[1] + PITCH * r
            w, h = OVAL_BOX[2], OVAL_BOX[3]
            if x < 0 or y < 0 or y + h > sh[0] or x + w > sh[1]:
                e = False
            else:
                box = rgb_of(np.asarray(frame_bgr)[y : y + h, x : x + w])
                d = np.abs(box - np.asarray(OVAL, np.int16)).sum(axis=2)
                e = bool((d <= OVAL_TOL).mean() >= OVAL_SHARE)
            flags.append(((c, r), e))
    inside = [e for (c, r), e in flags if 0 <= r < ROWS and 0 <= c < COLS]
    ring = [e for (c, r), e in flags if not (0 <= r < ROWS and 0 <= c < COLS)]
    n = sum(inside)
    tail = 0
    for e in reversed(inside):
        if not e:
            break
        tail += 1
    return n >= 1 and tail == n and not any(ring)


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


def empty_picture(frame_bgr: Any, origin: tuple[int, int]) -> np.ndarray | None:
    """PURE: THIS client's empty slot (RGB float32), from the tab's last cell when it shows the
    oval (items fill a tab in reading order, so the last cell is the likeliest empty one)."""
    for slot in range(SLOTS - 1, -1, -1):
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
              | ((o[:, 0] >= 220) & (o[:, 2] >= 220) & (o[:, 1] <= 215))
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


def read_count(frame_bgr: Any, origin: tuple[int, int], slot: int,
               templates: Mapping[str, Any]) -> int | None:  # fmt: skip
    """PURE: the stack's count, or None. The band's pure-black glyphs, every one a digit, at most
    DIGIT_GAP apart, in the count's place: ONE digit from COUNT_FIRST, or 2+ digits whose last
    ink column is COUNT_END; no leading zero. Anything else (an icon's black pixel, a covered
    digit) is unread, never a shorter number."""
    import hotbar_count as hb

    x, y = icon_xy(origin, slot)
    img = np.asarray(frame_bgr)
    band = img[y + COUNT_DY : y + COUNT_DY + COUNT_ROWS, x + COUNT_X0 : x + COUNT_X1, :3]
    if band.shape[0] != COUNT_ROWS or band.shape[1] != COUNT_X1 - COUNT_X0:
        return None
    runs = hb.glyph_runs(band.max(axis=2) <= COUNT_INK)
    if not runs:
        return None
    digits = []
    for col, g in runs:
        d = hb.match(g, templates)
        if d is None:
            return None
        digits.append((col + COUNT_X0, col + COUNT_X0 + g.shape[1] - 1, d))
    for (_a0, a1, _da), (b0, _b1, _db) in zip(digits, digits[1:], strict=False):
        if b0 - a1 - 1 > DIGIT_GAP:
            return None
    text = "".join(d for _x0, _x1, d in digits)
    if len(digits) == 1:
        if digits[0][0] not in COUNT_FIRST:
            return None
    elif digits[-1][1] != COUNT_END:
        return None
    if len(text) > 1 and text[0] == "0":
        return None
    return int(text)


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
             templates: Mapping[str, Any]) -> list[BagSlot]:  # fmt: skip
    """PURE: every slot of the open tab; after the first empty slot every later slot must be
    empty (items fill a tab in reading order), else that slot is unread."""
    out, seen_empty = [], False
    for s in range(SLOTS):
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


def _grab(r: Any, screen: Any) -> np.ndarray:
    x, y, w, h = _real_client(r)
    _, img = screen.grab(x, y, w, h)
    return np.ascontiguousarray(np.asarray(img)[..., :3])


def _save_box(frame_bgr: Any, origin: tuple[int, int], path: Path) -> None:
    """The bag's window only (a lab trial's evidence: our own character; never in a Run)."""
    from PIL import Image

    x, y = origin
    box = np.asarray(frame_bgr)[max(0, y) : y + 260, max(0, x) : x + 290, 2::-1]
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
    time.sleep(0.9)


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
    was_open = find_window(_grab(r, screen)) is not None  # left as it was found (B3)
    if not was_open:
        agent.chord(*keys)
        time.sleep(1.2)
    out: dict[str, Any] = {"tabs": [], "origin": None, "was_open": was_open}
    opened = not was_open
    try:
        f = _grab(r, screen)
        origin = find_window(f)
        if origin is None:
            raise r.Stop("bag_count: Alt+E showed no bag (no oval lattice found)")
        out["origin"] = list(origin)
        empty = empty_picture(f, origin)
        pics = None if empty is None else Pictures.over(refs, empty)
        tabs = []
        for name, (tx, ty) in TABS.items():
            _click(agent, r, origin[0] + tx, origin[1] + ty)
            _park(agent, r)
            reads = []
            for _ in range(2):
                f = _grab(r, screen)
                # cheap first (its own cells); the whole-frame search only when that fails (a
                # full tab shows no oval): a lattice elsewhere = the bag moved
                if not window_at(f, origin) and find_window(f) not in (origin, None):
                    raise r.Stop("bag_count: the bag moved while it was read")
                if empty is None:  # no empty slot seen yet: this tab may show one
                    empty = empty_picture(f, origin)
                    pics = None if empty is None else Pictures.over(refs, empty)
                if frames_dir is not None:  # the lab's trials only: the bag's own box, per read
                    _save_box(f, origin, frames_dir / f"{name}-{len(reads)}.png")
                if pics is None or empty is None:
                    reads.append(None)
                else:
                    reads.append(read_tab(f, origin, pics, empty, templates))
                time.sleep(0.3)
            tab = TabRead(name)
            if reads[0] is None or reads[1] is None:
                tab.slots = [BagSlot(s, "unread", why="no empty slot seen to compare with")
                             for s in range(SLOTS)]  # fmt: skip
            else:
                for a, b in zip(reads[0], reads[1], strict=True):
                    same = (a.kind, a.ids, a.count) == (b.kind, b.ids, b.count)
                    why = "two reads disagree"
                    tab.slots.append(a if same else BagSlot(a.slot, "unread", a.ids, None, a.d1,
                                                            a.d2, why))  # fmt: skip
            tabs.append(tab)
        out["tabs"] = [t.record() for t in tabs]
        out["totals"] = bag_totals(tabs)
        out["unread"] = sum(len(t.unread()) for t in tabs)
        out["full_tabs"] = [t.tab for t in tabs if t.full]
    finally:
        if opened:
            agent.chord(*keys)
            time.sleep(1.0)
            _park(agent, r)
        out["closed"] = find_window(_grab(r, screen)) is None
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
        origin = find_window(f)
        if origin is None:
            print(json.dumps({"origin": None, "why": "no bag lattice"}))
            return 2
        empty = empty_picture(f, origin)
        if empty is None:
            print(json.dumps({"origin": list(origin), "why": "no empty slot to compare with"}))
            return 2
        pics = Pictures.over(refs or si.SlotRefs.load(), empty)
        tab = TabRead("shown", read_tab(f, origin, pics, empty, hb.load()))
        print(json.dumps({"origin": list(origin), **tab.record(),
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
