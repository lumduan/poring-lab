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
- ROUND 3 (Amendment 5): when another picture is within ICON_MARGIN of the best (the magic
  scrolls: one shape, a 5 x 6 seal of another colour), the hotbar reader's PAIR LEAD decides on the
  pixels where the two pictures differ (slot_items' DIFF_PX / DISCRIM_MIN / PAIR_LEAD, on the whole
  square: the popup has no count box over its icon). Pictures with fewer than DISCRIM_MIN such
  pixels are one picture to the eye: their ids join the read (one group, Amendment 4).

- AMENDMENT 6 (section 4's 1080 run-time check): at 1920 x 1080 the client draws the popup 1:1 at
  the 720 place moved right by (w - 1280) / 2 on the SAME rows (measured 2026-11-22 19:43 on dev).
  `item_popup.py watch` grabs only that band of the REAL frame (BAND, band_box), puts it back at
  the 720 coordinates (place_band) and feeds the Tracker unchanged; events.jsonl, no input.

PURE (numpy only) but for the pictures' loader and the `watch` command's grabs (ro_agent, imported
lazily in main); no input.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from collections.abc import Callable, Mapping, Sequence
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
    # round 3: each picture as the popup shows it, its key pixels the box's white (slot_items'
    # composite, whose face is the same white)
    comp: np.ndarray = field(init=False, repr=False)

    def __post_init__(self) -> None:
        rgb = np.asarray(self.rgb, np.float32)[..., :3]
        self.comp = np.where(np.asarray(self.own, bool)[..., None], rgb, np.float32(WHITE))

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
            return self.close_read(sq, d, icon_max, margin, dm)
        return ItemRead(tuple(ids), float(d[best]), dm, "ok")

    def lead(self, sq: np.ndarray, p: int, q: int) -> tuple[int, float]:
        """PURE (round 3): slot_items.SlotRefs.pair's rival test of pictures ``p`` and ``q`` on the
        whole square: (the pixels that tell them apart -- where their composited pictures differ
        by more than DIFF_PX --, the read's LEAD of ``p`` over ``q`` there, in [-1, 1]: (its mean
        difference from ``q`` - from ``p``) / the pictures' own mean difference there)."""
        import slot_items as si

        a, b = self.comp[p].reshape(-1, 3), self.comp[q].reshape(-1, 3)
        apart = np.abs(a - b).mean(axis=1) > si.DIFF_PX
        n = int(apart.sum())
        if n == 0:
            return 0, 0.0
        o = np.asarray(sq, np.float32)[..., :3].reshape(-1, 3)[apart]
        e_p, e_q = float(np.abs(o - a[apart]).mean()), float(np.abs(o - b[apart]).mean())
        return n, (e_q - e_p) / float(np.abs(a[apart] - b[apart]).mean())

    def close_read(self, sq: np.ndarray, d: np.ndarray, icon_max: float, margin: float,
                   dm: float) -> ItemRead:  # fmt: skip
        """Round 3 (Amendment 5): the close set is the best picture and every picture within
        ``margin`` of it. The read names the nearest member (at most ``icon_max`` away) whose lead
        is >= PAIR_LEAD over every other member it differs from on >= DISCRIM_MIN pixels; members
        with fewer such pixels are the same picture to the eye and their ids join the read.
        why: "lead" (a lead was needed) or "same" (only same-looking members); else "ambiguous"."""
        import slot_items as si

        order = [int(i) for i in np.argsort(d)]
        top = float(d[order[0]])
        close = [i for i in order if float(d[i]) < top + margin]
        for c in close:
            if float(d[c]) > icon_max:
                break
            ids, led, beaten = set(self.ids[c]), False, True
            for m in close:
                if m == c:
                    continue
                n, lead = self.lead(sq, c, m)
                if n < si.DISCRIM_MIN:
                    ids |= set(self.ids[m])
                elif lead >= si.PAIR_LEAD:
                    led = True
                else:
                    beaten = False
                    break
            if beaten:
                return ItemRead(tuple(sorted(ids)), float(d[c]), dm, "lead" if led else "same")
        return ItemRead(None, top, dm, "ambiguous")


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


# --- Amendment 6: the run-time reader at 1080 (item_popup.py watch) -------------------------------
# The band of the 720 coordinates the watcher grabs: the popup's place with a margin (x 533-1068,
# rows 72-109; the box is at most POPUP_MAX_W wide from POPUP_LEFT, the count's crop is rows
# POPUP_TOP - 2 .. POPUP_BOTTOM + 1). On the real frame it sits (w - 1280) / 2 to the right.
BAND = (
    bs.POPUP_LEFT - 8,
    bs.POPUP_TOP - 4,
    bs.POPUP_MAX_W + 16,
    bs.POPUP_BOTTOM - bs.POPUP_TOP + 9,
)
VIRTUAL_W = 1280
WATCH_PERIOD_S = 0.25  # 4 grabs a second (the popup stays ~4-5 s)
SLOW_GRAB_S = 0.25  # a grab slower than this is logged


def band_box(region: Sequence[int]) -> tuple[int, int, int, int]:
    """PURE: the band's desktop box for a client REGION (x, y, w, h): the 720 place moved right by
    (w - 1280) / 2 (none at 1280 or less), the same rows (Amendment 6, measured at 1920 x 1080)."""
    rx, ry, rw, _rh = (int(v) for v in region)
    dx = max(0, (rw - VIRTUAL_W) // 2)
    bx, by, bw, bh = BAND
    return rx + bx + dx, ry + by, bw, bh


def place_band(band_rgb: np.ndarray) -> np.ndarray:
    """PURE: a grabbed band (RGB) put back at the 720 coordinates: a frame of rows 0 .. the band's
    last, VIRTUAL_W wide, black outside the band -- what box_of / the Tracker read."""
    bx, by, bw, bh = BAND
    out = np.zeros((by + bh, VIRTUAL_W, 3), np.uint8)
    h, w = min(int(band_rgb.shape[0]), bh), min(int(band_rgb.shape[1]), bw)
    out[by : by + h, bx : bx + w] = np.asarray(band_rgb)[:h, :w, :3]
    return out


def tick_stats(ms: Sequence[float]) -> dict[str, Any]:
    """PURE: a list of tick times (ms) as n / p50 / p95 / max (nearest rank)."""
    if not ms:
        return {"n": 0, "p50": None, "p95": None, "max": None}
    v = sorted(ms)

    def rank(q: float) -> float:
        return round(float(v[min(len(v) - 1, max(0, int(np.ceil(q * len(v))) - 1))]), 2)

    return {"n": len(v), "p50": rank(0.50), "p95": rank(0.95), "max": round(float(v[-1]), 2)}


def watch(out_dir: Path, grab: Callable[[], tuple[int, np.ndarray]], tracker: Tracker,
          stop: Callable[[], bool], period_s: float = WATCH_PERIOD_S, crops: bool = False,
          sleep: Callable[[float], None] = time.sleep,
          clock: Callable[[], float] = time.perf_counter) -> dict[str, Any]:  # fmt: skip
    """The watcher's loop: grab the band (t_mono_ns, BGRA), put it at the 720 place, feed the
    Tracker, append each CLOSED event to events.jsonl (flushed), until ``stop()``; then the open
    one. ``crops``: the band of each event's first frame as crop-<t>.png (dev only). A failed grab
    is counted and the loop goes on. Writes and returns summary.json's dict."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ticks: list[float] = []
    slow = errors = events = 0
    first: dict[int, np.ndarray] = {}
    with open(out_dir / "events.jsonl", "a", encoding="utf-8") as fh:

        def write(e: Event) -> None:
            nonlocal events
            fh.write(json.dumps(e.doc()) + "\n")
            fh.flush()
            events += 1
            band = first.pop(e.t, None)
            if crops and band is not None:
                from PIL import Image

                Image.fromarray(band).save(out_dir / f"crop-{e.t}.png")

        while not stop():
            t0 = clock()
            try:
                t, bgra = grab()
            except Exception:  # noqa: BLE001 -- a grab that failed: counted, the loop goes on
                errors += 1
                sleep(period_s)
                continue
            g = clock() - t0
            rgb = np.ascontiguousarray(np.asarray(bgra)[..., 2::-1])
            closed = tracker.feed(int(t), place_band(rgb))
            if crops and tracker.open is not None and tracker.open.t == int(t):
                first[int(t)] = rgb
            for e in closed:
                write(e)
            dt = clock() - t0
            ticks.append(dt * 1000.0)
            slow += g > SLOW_GRAB_S
            sleep(max(0.0, period_s - dt))
        for e in tracker.flush():
            write(e)
    summary = {"ticks": tick_stats(ticks), "slow_grabs": slow, "grab_errors": errors,
               "events": events, "t_end_mono_ns": time.monotonic_ns()}  # fmt: skip
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="The item popup reader (item-popup-reader.md).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("watch", help="Amendment 6: read the real frame's popup beside a Run")
    w.add_argument("--out", type=Path, required=True, help="a folder: events.jsonl, meta, summary")
    w.add_argument("--refs", help="slot_items' pictures (default: this checkout's data/)")
    w.add_argument("--count", type=Path, required=True, help="the count font (.npz)")
    w.add_argument("--seconds", type=float, help="stop after this long (default: SIGTERM/SIGINT)")
    w.add_argument("--period", type=float, default=WATCH_PERIOD_S)
    w.add_argument("--crops", action="store_true", help="save each event's band (dev only)")
    a = ap.parse_args(argv)
    import ro_agent as r  # the grabs: its own Screen (one pipe), never another process's

    os.environ.pop("PORING_PAUSE_AWAY", None)  # a Run's pause gate is the runner's, not ours
    tracker = Tracker(Icons.load(a.refs), load_count(a.count))
    region = r.real_game_region()
    box = band_box(region)
    screen = r.Screen()
    stopping = [False]

    def on_signal(_sig: int, _frm: Any) -> None:
        stopping[0] = True

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    end = None if a.seconds is None else time.monotonic() + a.seconds
    a.out.mkdir(parents=True, exist_ok=True)
    meta = {"region": list(region), "band_box": list(box), "period_s": a.period,
            "refs": a.refs, "count": str(a.count), "pid": os.getpid(),
            "t_start_mono_ns": time.monotonic_ns()}  # fmt: skip
    (a.out / "meta.json").write_text(json.dumps(meta, indent=1))
    summary = watch(a.out, lambda: screen.grab(*box), tracker,
                    lambda: stopping[0] or (end is not None and time.monotonic() >= end),
                    a.period, a.crops)  # fmt: skip
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
