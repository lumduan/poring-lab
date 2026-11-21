#!/usr/bin/env python3
"""THE ITEM POPUP READER (docs/planning/item-popup-reader.md; Batt 2026-11-21: "every item gained,
by a pickup or a Steal, shows its icon at the same place every time: make the list of each Run").

The client shows a white rounded box for every item that lands in the bag: the item's icon, its
name, the count ("<name> - 1 obtained."; Batt's Thai client "Scell 1 ชิ้น"). At a FIXED place
with a left-aligned width (bare_steal.popup_box, measured on the 720 recordings), drawn 1:1 on the
real client frame at every size (the 1080 recordings' virtual view shrinks it: never read there).

Read by shape, colour and digits only (Batt 10-26 / 11-11: no word is read):
- the box: bare_steal.popup_box; a NEW popup when it appears or its contents change;
- which item: the icon square at ICON_OFF in the box against the GRF's item pictures
  (slot_items.SlotRefs, the bag count's), composited over the box's white -- the nearest picture's
  ids (a shared icon is a group) under ICON_MAX, ahead of the next other picture by ICON_MARGIN;
- how many: the LAST group of digit runs in the text (glyphs learned from popups whose amounts the
  packets give; hp_percent's run method), on the box's OWN columns (text_box: its right border is
  the crop's last columns, which text_runs drops);
- ROUND 2 (item-popup-reader.md, Amendment 2): one event per popup SHOWN (Tracker). A new event
  needs the box to have left the screen, or another item, or another width read with its text's
  tail; while the same box stays, an unread item or amount is read again (the first read wins).

PURE (numpy only) but for the pictures' loader; no input, no grabs.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bare_steal as bs  # noqa: E402 -- the popup's box (pure, numpy only)

ICON = 24
# CALIBRATED 2026-11-21 on fiT1-fiT20 (1,071 popups of a known item; item-popup-reader.md 4):
# at (12, 4) the true picture was the nearest of the occurring items' on 1,069; its distance
# p50 7.4 / p95 8.9; the nearest WRONG picture (of all 2,381) at least 29.0 further at p05 (35.4)
ICON_OFF = (12, 4)  # the icon square's top-left from the box's (left, POPUP_TOP)
ICON_MAX = 15.0  # the best picture's mean |RGB| over its own pixels: above the true p95, far under
ICON_MARGIN = 10.0  # ... and the next other picture at least this much further
WHITE = 255.0


@dataclass(frozen=True, slots=True)
class Popup:
    left: int
    right: int
    sig: bytes  # the contents' signature (a coarse picture of the box), for "a new popup"


@dataclass(frozen=True, slots=True)
class ItemRead:
    ids: tuple[int, ...] | None  # the picture's ids (a shared icon: several), None: unread
    dist: float | None
    margin: float | None
    why: str  # "ok", or why not


def box_of(frame_rgb: np.ndarray) -> Popup | None:
    """The popup on a 1:1 RGB frame of the client region (rows from 0), or None."""
    got = bs.popup_box(frame_rgb)
    if got is None:
        return None
    x0, x1 = got
    crop = np.asarray(frame_rgb[bs.POPUP_TOP : bs.POPUP_BOTTOM + 1, x0 : x1 + 1, :3], np.float32)
    lum = crop.mean(axis=2)
    coarse = lum[::3, ::3] < 200  # ink, coarsely: the same text and icon give the same picture
    return Popup(int(x0), int(x1), np.packbits(coarse).tobytes())


def is_new(prev: Popup | None, cur: Popup | None, change: float = 0.08) -> bool:
    """PURE: a popup that was not on the previous frame, or whose width or ink changed."""
    if cur is None:
        return False
    if prev is None or abs((cur.right - cur.left) - (prev.right - prev.left)) > bs.POPUP_WIDTH_TOL:
        return True
    a = np.unpackbits(np.frombuffer(prev.sig, np.uint8))
    b = np.unpackbits(np.frombuffer(cur.sig, np.uint8))
    n = min(len(a), len(b))
    return bool(n and float((a[:n] != b[:n]).mean()) > change)


def text_box(frame_rgb: np.ndarray, p: Popup) -> np.ndarray:
    """The box's crop for the count: rows POPUP_TOP - 2 .. POPUP_BOTTOM + 1, the box's OWN columns
    (left .. right), so its right border is the crop's last columns (round 2: a 260-px white pad
    put the border inside the text, and a long name past 260 px lost its tail)."""
    return np.asarray(frame_rgb[bs.POPUP_TOP - 2 : bs.POPUP_BOTTOM + 2, p.left : p.right + 1, :3])


def icon_square(frame_rgb: np.ndarray, p: Popup, off: tuple[int, int] = ICON_OFF) -> np.ndarray:
    x, y = p.left + off[0], bs.POPUP_TOP + off[1]
    return np.asarray(frame_rgb[y : y + ICON, x : x + ICON, :3])


@dataclass
class Icons:
    """The item pictures over white, compared on each picture's own pixels."""

    rgb: np.ndarray  # (P, 24, 24, 3) float32
    own: np.ndarray  # (P, 24, 24) bool: the picture's own (non-key) pixels
    ids: tuple[tuple[int, ...], ...]
    names: Mapping[int, str] = field(default_factory=dict)

    @classmethod
    def from_refs(cls, refs: Any) -> Icons:
        import slot_items as si

        raw = np.asarray(refs.rgb)
        key = np.stack([si.transparent(p) for p in raw])
        return cls(raw[..., :3].astype(np.float32), ~key, tuple(refs.ids), dict(refs.names))

    @classmethod
    def load(cls, path: str | None = None) -> Icons:
        import slot_items as si

        return cls.from_refs(si.SlotRefs.load(path) if path else si.SlotRefs.load())

    def distances(self, sq: np.ndarray) -> np.ndarray:
        o = np.asarray(sq, np.float32)[None, ..., :3]
        diff = np.abs(self.rgb - o).mean(axis=3)  # (P, 24, 24)
        n = np.maximum(self.own.sum(axis=(1, 2)), 1)
        return np.asarray((diff * self.own).sum(axis=(1, 2)) / n)

    def read(self, sq: np.ndarray, icon_max: float = ICON_MAX,
             margin: float = ICON_MARGIN) -> ItemRead:  # fmt: skip
        """The nearest picture's ids, or unread: too far, or a different picture too close."""
        if sq.shape[:2] != (ICON, ICON):
            return ItemRead(None, None, None, "off_frame")
        d = self.distances(sq)
        order = np.argsort(d)
        best = int(order[0])
        ids = self.ids[best]
        rival = next((int(i) for i in order[1:] if set(self.ids[int(i)]) != set(ids)), None)
        dm = None if rival is None else float(d[rival] - d[best])
        if float(d[best]) > icon_max:
            return ItemRead(None, float(d[best]), dm, "far")
        if dm is not None and dm < margin:
            return ItemRead(None, float(d[best]), dm, "ambiguous")
        return ItemRead(tuple(ids), float(d[best]), dm, "ok")


def digit_groups(ink: np.ndarray, font: Mapping[str, np.ndarray], max_dist: float = 0.12,
                 gap: int = 3) -> list[str]:  # fmt: skip
    """PURE: the text band's runs (ink columns split by a blank column) named by ``font``'s digits
    (the same shape, <= max_dist of the pixels differing); consecutive digit runs at most ``gap``
    blank columns apart form a group. Returns the groups, left to right."""
    cols = ink.any(axis=0)
    runs: list[tuple[int, int]] = []
    i = 0
    while i < len(cols):
        if not cols[i]:
            i += 1
            continue
        j = i
        while j < len(cols) and cols[j]:
            j += 1
        runs.append((i, j))
        i = j
    groups: list[str] = []
    cur, last_end = "", -10
    for a, b in runs:
        run = ink[:, a:b]
        sc = sorted(
            (float((run != g).mean()), ch) for ch, g in font.items() if g.shape == run.shape
        )
        ch = sc[0][1] if sc and sc[0][0] <= max_dist else None
        if ch is not None and ch.isdigit() and (not cur or a - last_end <= gap):
            cur += ch
        else:
            if cur:
                groups.append(cur)
            cur = ch if ch is not None and ch.isdigit() else ""
        last_end = b
    if cur:
        groups.append(cur)
    return groups


def amount_of(groups: Sequence[str]) -> int | None:
    """PURE: the count is the LAST digit group; None when there is none or it starts with 0."""
    if not groups:
        return None
    g = groups[-1]
    return None if (len(g) > 1 and g[0] == "0") or len(g) > 5 else int(g)


# --- the count, by the text's constant tail (learned per client, 2026-11-21) ---------------------
# The text after the icon ends with the SAME words on every popup ("... - N obtained." on the lab's
# client, "... N ชิ้น" on Batt's): that tail is learned as its runs' shapes, never read as words;
# the count is the group of runs just left of it (each run at most COUNT_GAP blank columns from the
# next), each run named by a digit learned from popups whose amounts the packets give.
TEXT_X = 12 + ICON + 4  # the text's first column from the box's left
TEXT_ROWS = (6, 22)  # its rows from the crop's top (POPUP_TOP - 2): a 16-row band
TEXT_INK = 150.0  # a pixel darker than this (mean RGB) is ink
COUNT_GAP = 3
SAME = 0.12  # two runs are the same glyph when at most this share of their pixels differ


def text_runs(box: np.ndarray) -> list[np.ndarray]:
    """PURE: the ink runs (bitmaps) of a box crop's text, left to right (``box``: rows POPUP_TOP - 2
    .. POPUP_BOTTOM + 2, columns from the box's left)."""
    band = np.asarray(box[TEXT_ROWS[0] : TEXT_ROWS[1], TEXT_X:, :3], np.float32).mean(axis=2)
    ink = band < TEXT_INK
    ink[:, -4:] = False  # the box's right border
    cols = ink.any(axis=0)
    out: list[np.ndarray] = []
    i = 0
    while i < len(cols):
        if not cols[i]:
            i += 1
            continue
        j = i
        while j < len(cols) and cols[j]:
            j += 1
        out.append(ink[:, i:j])
        i = j
    return out


def run_spans(box: np.ndarray) -> list[tuple[int, int]]:
    band = np.asarray(box[TEXT_ROWS[0] : TEXT_ROWS[1], TEXT_X:, :3], np.float32).mean(axis=2)
    ink = band < TEXT_INK
    ink[:, -4:] = False
    cols = ink.any(axis=0)
    spans, i = [], 0
    while i < len(cols):
        if not cols[i]:
            i += 1
            continue
        j = i
        while j < len(cols) and cols[j]:
            j += 1
        spans.append((i, j))
        i = j
    return spans


def same(a: np.ndarray, b: np.ndarray) -> bool:
    return a.shape == b.shape and float((a != b).mean()) <= SAME


@dataclass
class CountFont:
    tail: list[np.ndarray]  # the text's constant last runs
    digits: dict[str, np.ndarray]  # a digit -> its run


def suffix_of(texts: Sequence[Sequence[np.ndarray]], share: float) -> list[np.ndarray]:
    """PURE: the longest run suffix the same on >= ``share`` of the texts (from the commonest)."""
    texts = [t for t in texts if t]
    if not texts:
        return []
    ref = max(texts, key=lambda t: sum(1 for u in texts if len(u) == len(t)))
    out: list[np.ndarray] = []
    for k in range(1, len(ref) + 1):
        if sum(1 for t in texts if len(t) >= k and same(t[-k], ref[-k])) < share * len(texts):
            break
        out.insert(0, ref[-k])
    return out


def learn_count(boxes: Sequence[np.ndarray], amounts: Sequence[int],
                share: float = 0.9) -> CountFont:  # fmt: skip
    """PURE: the tail -- the run suffix every AMOUNT's boxes share (a digit differs between two
    amounts, so it never joins the tail; one amount alone cannot tell its digits from the words:
    no tail, nothing read) -- and the digits, from each box's count group."""
    texts = [text_runs(b) for b in boxes]
    by_amount: dict[int, list[list[np.ndarray]]] = {}
    for t, amt in zip(texts, amounts, strict=True):
        by_amount.setdefault(int(amt), []).append(t)
    sufs = [suffix_of(v, share) for v in by_amount.values()]
    tail: list[np.ndarray] = []
    if len(sufs) >= 2:
        for k in range(1, min(len(x) for x in sufs) + 1):
            if not all(same(x[-k], sufs[0][-k]) for x in sufs[1:]):
                break
            tail.insert(0, sufs[0][-k])
    digits: dict[str, list[np.ndarray]] = {}
    for b, t, amt in zip(boxes, texts, amounts, strict=True):
        grp = count_group(b, t, tail)
        s = str(amt)
        if grp is not None and len(grp) == len(s):
            for ch, run in zip(s, grp, strict=True):
                digits.setdefault(ch, []).append(run)
    out: dict[str, np.ndarray] = {}
    for ch, runs in digits.items():
        shapes: dict[tuple[int, int], list[np.ndarray]] = {}
        for r in runs:
            shapes.setdefault(r.shape, []).append(r)
        best = max(shapes.values(), key=len)  # the commonest shape; its majority pixels
        out[ch] = np.mean(np.stack(best), axis=0) >= 0.5
    return CountFont(tail, out)


def count_group(box: np.ndarray, runs: Sequence[np.ndarray],
                tail: Sequence[np.ndarray]) -> list[np.ndarray] | None:  # fmt: skip
    """PURE: the runs just left of the tail, each <= COUNT_GAP blank columns from the next; None
    when the text does not end with the tail."""
    k = len(tail)
    if not k or len(runs) <= k or not all(same(runs[-k + i], tail[i]) for i in range(k)):
        return None
    spans = run_spans(box)
    if len(spans) != len(runs):
        return None
    j = len(runs) - k - 1
    grp = [j]
    while grp[0] > 0 and spans[grp[0]][0] - spans[grp[0] - 1][1] <= COUNT_GAP:
        grp.insert(0, grp[0] - 1)
    return [runs[i] for i in grp]


def read_count(box: np.ndarray, font: CountFont) -> int | None:
    """PURE: the count, or None: no tail, an unknown run, a leading zero."""
    runs = text_runs(box)
    grp = count_group(box, runs, font.tail)
    if grp is None:
        return None
    s = ""
    for r in grp:
        ch = next((c for c, g in font.digits.items() if same(r, g)), None)
        if ch is None:
            return None
        s += ch
    return amount_of([s])


def save_count(font: CountFont, path: Path) -> None:
    """The learned tail and digits (client pixels: under data/, never committed)."""
    arrays = {f"tail_{i}": t for i, t in enumerate(font.tail)}
    arrays.update({f"digit_{c}": g for c, g in font.digits.items()})
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **arrays)


def load_count(path: Path) -> CountFont:
    with np.load(path, allow_pickle=False) as z:
        tail = [
            np.asarray(z[f"tail_{i}"], bool)
            for i in range(sum(k.startswith("tail_") for k in z.files))
        ]
        digits = {k[6:]: np.asarray(z[k], bool) for k in z.files if k.startswith("digit_")}
    return CountFont(tail, digits)


# --- round 2: one event per popup shown -----------------------------------------------------------
@dataclass
class Event:
    t: int  # the first frame's t_mono_ns
    ids: tuple[int, ...] | None
    why: str
    dist: float | None
    amount: int | None
    width: int
    t_last: int = 0  # the last frame that showed it
    frames: int = 1
    filled: list[str] = field(default_factory=list)  # "item" / "amount": read on a later frame

    def doc(self) -> dict[str, Any]:
        return {"t": self.t, "ids": list(self.ids) if self.ids else None, "why": self.why,
                "dist": self.dist, "amount": self.amount, "width": self.width,
                "t_last": self.t_last, "frames": self.frames,
                "filled": list(self.filled)}  # fmt: skip


@dataclass(frozen=True, slots=True)
class FrameRead:
    item: ItemRead
    amount: int | None
    width: int


def same_popup(ev: Event, rd: FrameRead, width_tol: int = bs.POPUP_WIDTH_TOL) -> bool:
    """PURE (round 2): is this frame's box the popup of the open event?
    - another item: both reads name pictures and they share no id -> no;
    - another width: only when BOTH widths are true ones (each read its text's tail, so no cover cut
      the box's top or bottom edge short) -> no;
    - anything else (a cover over the icon, the text or an edge) -> the same popup."""
    if ev.ids and rd.item.ids and not set(ev.ids) & set(rd.item.ids):
        return False
    return not (
        ev.amount is not None and rd.amount is not None and abs(rd.width - ev.width) > width_tol
    )


class Tracker:
    """Round 2: the reader over a frame stream, one Event per popup shown. ``feed`` returns the
    events this frame CLOSED (the box left, or another popup replaced it); ``flush`` the open
    one."""

    def __init__(self, icons: Icons, count: CountFont) -> None:
        self.icons, self.count = icons, count
        self.open: Event | None = None

    def read(self, frame_rgb: np.ndarray, p: Popup) -> FrameRead:
        item = self.icons.read(icon_square(frame_rgb, p))
        return FrameRead(item, read_count(text_box(frame_rgb, p), self.count), p.right - p.left)

    def _start(self, t: int, rd: FrameRead) -> None:
        it = rd.item
        self.open = Event(t, it.ids, it.why, it.dist, rd.amount, rd.width, t_last=t)

    def feed(self, t: int, frame_rgb: np.ndarray) -> list[Event]:
        p = box_of(frame_rgb)
        if p is None:
            return self.flush()  # the box left the screen
        rd = self.read(frame_rgb, p)
        ev = self.open
        if ev is None:
            self._start(t, rd)
            return []
        if not same_popup(ev, rd):
            out = self.flush()
            self._start(t, rd)
            return out
        ev.frames += 1
        ev.t_last = t
        if ev.ids is None and rd.item.ids:
            ev.ids, ev.why, ev.dist = rd.item.ids, rd.item.why, rd.item.dist
            ev.filled.append("item")
        if ev.amount is None and rd.amount is not None:
            ev.amount, ev.width = rd.amount, rd.width
            ev.filled.append("amount")
        return []

    def flush(self) -> list[Event]:
        out = [self.open] if self.open is not None else []
        self.open = None
        return out
