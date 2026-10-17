#!/usr/bin/env python3
"""LOOT by frame difference (Batt 2026-10-17): item DROPS from pixels only -- compare the area
around the death spot just before the death and ~1 s after; new small blobs = drops. The bot is to
hover each blob centre and click while the client's cursor is the hand (the parent integrates).

    drop_blobs.py eval SID [SID ...] [--json OUT]   OFFLINE: score the detector on packet drops
    drop_blobs.py sheet SID --n 12 --out PNG        OFFLINE: crops around projected drops (debug)

THE DETECTOR (pure, ``drop_blobs`` = ``candidates`` + ``keep``; colour-order agnostic, see there):
NEW pixels = changed vs the registered BEFORE (max channel > 40, min over a 1-px neighbourhood),
not a GROUND colour (the crop's unchanged colours), not a VANISHED colour (BEFORE's changed,
non-ground colours: the dying monster -- its corpse splat lingers 3-5 s in its own colours --, the
GM's previous pose, HP bars). Components of 10-500 px, <= 34 px a side, not a thin bar, >= 30 %
still there in LATER (+0.4 s), centre outside the GM's sprite box.

THE EVALUATION (packets are ground truth OFFLINE only, never a detector input): our kills
(entity_vanish reason 1 of a monster our GM damaged) and their drops (floor_item_appear 'fall'
-1.5..+0.5 s of the vanish, <= 2 cells from the monster's last cell). BEFORE = the last frame
0.4 s before the vanish; AFTER = the first frame DELAY after it; LATER = AFTER + 0.4 s. Projection:
the camera centred on the GM's fractional cell at the frame time - 0.5 s (the display lag), the
item at cell - 0.5 + sub / 12 (sub_x, sub_y are 3, 6, 9 or 12). Recall@R = items with a blob
within R px; false blobs = blobs with no item within R, per kill (no-drop kills included).

MEASURED 2026-10-17 (hunt-flow17/18/20/20 recordings, 416 kills, 633 drops; centre = the item
cells' centroid | the dead monster's last cell):
  delay 0.3 s  recall@20 0.17 | 0.18   false/kill 0.82 | 0.85
  delay 0.5 s  recall@20 0.25 | 0.25   false/kill 0.82 | 0.88
  delay 0.8 s  recall@20 0.36 | 0.35   false/kill 0.67 | 0.72
  delay 1.0 s  recall@20 0.46 | 0.44   false/kill 0.66 | 0.76   (@15: 0.40 | 0.40; GM still: 0.54)
  delay 1.5 s  recall@20 0.42 | 0.44   false/kill 1.01 | 1.11
A PROTOTYPE, not a gate: about half the drops are found. Misses: items ON the corpse splat or in
the dying monster's colours (white items from a white Lunatic), green items (Clover) on grass, items
at the GM's feet / HP bars, the bot's own hand cursor over the spot, projection error while the GM
walks (nearest blob p50 9-10 px, p90 22-26 px).
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import json
import math
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
REC_ROOT = Path("/mnt/poring-lab-datasets/hunt-recordings")
DEMO_ROOT = Path("/dev/shm/poring-lab-demo")
MAP = "prt_fild08"
GM = 2000002
NS = 10**9
LAG_S = 0.5  # the frames show the server ~0.45-0.6 s late (hunt_flow v7)
MS_CELL = 150.0
Cell = tuple[int, int]


# --- the detector (PURE) -------------------------------------------------------------------------

GM_BOX = (620.0, 285.0, 660.0, 375.0)  # hunt_flow v11: the GM's drawn sprite (client px)


@dataclass(frozen=True)
class Blob:
    u: float  # centre of its NEW pixels, AFTER's full-frame pixels
    v: float
    area: int  # NEW pixels
    w: int  # bounding box of the (1-px grown) component
    h: int
    vanished: float = 0.0  # share of its pixels in the VANISHED colours (the dying monster etc.)
    scene: float = 0.0  # share in BEFORE's non-ground colours anywhere in the region
    persist: float = 1.0  # share still there in LATER (1.0 without LATER)
    contrast: float = 0.0  # median max-channel difference to BEFORE


def _rgb3(img: Any) -> Any:
    a = np.asarray(img)
    if a.ndim != 3 or a.shape[2] not in (3, 4):
        raise ValueError(f"expected an H x W x 3|4 image, got {a.shape}")
    return a[..., :3]


def _crop(img: Any, cu: float, cv: float, half: int) -> tuple[Any, int, int]:
    """A (2 half + 1)^2 crop centred on (cu, cv), edge-padded outside the image; its origin."""
    h, w = img.shape[:2]
    x0, y0 = int(round(cu)) - half, int(round(cv)) - half
    n = 2 * half + 1
    xs = np.clip(np.arange(x0, x0 + n), 0, w - 1)
    ys = np.clip(np.arange(y0, y0 + n), 0, h - 1)
    return img[np.ix_(ys, xs)], x0, y0


def _inside(img: Any, cu: float, cv: float, half: int) -> Any:
    h, w = img.shape[:2]
    x0, y0 = int(round(cu)) - half, int(round(cv)) - half
    n = 2 * half + 1
    xs = np.arange(x0, x0 + n)
    ys = np.arange(y0, y0 + n)
    return ((ys >= 0) & (ys < h))[:, None] & ((xs >= 0) & (xs < w))[None, :]


def phase_shift(ref: Any, mov: Any, max_shift: int) -> tuple[int, int]:
    """(dy, dx) such that mov[y, x] ~ ref[y + dy, x + dx] (integer phase correlation on the grey
    means; Hann-windowed); (0, 0) when the peak is outside ``max_shift``."""
    a = np.asarray(ref, np.float32)
    b = np.asarray(mov, np.float32)
    a, b = a - a.mean(), b - b.mean()
    win = np.outer(np.hanning(a.shape[0]), np.hanning(a.shape[1])).astype(np.float32)
    fa, fb = np.fft.rfft2(a * win), np.fft.rfft2(b * win)
    r = fa * np.conj(fb)
    r /= np.abs(r) + 1e-6
    c = np.fft.irfft2(r, s=a.shape)
    iy, ix = np.unravel_index(int(np.argmax(c)), c.shape)
    dy = iy - c.shape[0] if iy > c.shape[0] // 2 else iy
    dx = ix - c.shape[1] if ix > c.shape[1] // 2 else ix
    if abs(dy) > max_shift or abs(dx) > max_shift:
        return 0, 0
    return int(dy), int(dx)


def _shift(img: Any, dy: int, dx: int) -> Any:
    """out[y, x] = img[y + dy, x + dx], edge-padded."""
    h, w = img.shape[:2]
    ys = np.clip(np.arange(h) + dy, 0, h - 1)
    xs = np.clip(np.arange(w) + dx, 0, w - 1)
    return img[np.ix_(ys, xs)]


def _min_diff(a: Any, b: Any, r: int = 1) -> Any:
    """Per pixel: min over |d| <= r of max_channel |a(p) - b(p + d)| (absorbs a 1-px misregistration
    and JPEG ringing on edges). Channel order does not matter."""
    a16 = a.astype(np.int16)
    best = None
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            d = np.abs(a16 - _shift(b, dy, dx).astype(np.int16)).max(-1)
            best = d if best is None else np.minimum(best, d)
    return best


def _bins(img: Any, q: int) -> Any:
    k = 256 // q
    c = (img.astype(np.int32) // q).clip(0, k - 1)
    return (c[..., 0] * k + c[..., 1]) * k + c[..., 2]


def _colour_set(img: Any, mask: Any, q: int, min_count: int, grow: int = 1) -> Any:
    """Boolean (k^3,) table: the quantised colours of ``img[mask]`` seen >= ``min_count`` times,
    grown by ``grow`` bins along every axis (quantisation edges)."""
    k = 256 // q
    cnt = np.bincount(_bins(img, q)[mask].ravel(), minlength=k**3).reshape(k, k, k)
    on = cnt >= min_count
    for _ in range(grow):  # a 26-neighbour grow, no wrap-around
        p = np.pad(on, 1)
        g = np.zeros_like(on)
        for dz in range(3):
            for dy in range(3):
                for dx in range(3):
                    g |= p[dz : dz + k, dy : dy + k, dx : dx + k]
        on = g
    return on.ravel()


def _components(mask: Any) -> list[Any]:
    """8-connected components of a boolean mask: a list of (ys, xs) index arrays."""
    from collections import deque

    h, w = mask.shape
    lab = np.zeros(mask.shape, np.int32)
    out = []
    n = 0
    for y0, x0 in zip(*np.nonzero(mask), strict=True):
        if lab[y0, x0]:
            continue
        n += 1
        lab[y0, x0] = n
        q = deque([(int(y0), int(x0))])
        ys, xs = [], []
        while q:
            y, x = q.popleft()
            ys.append(y)
            xs.append(x)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < h and 0 <= xx < w and mask[yy, xx] and not lab[yy, xx]:
                        lab[yy, xx] = n
                        q.append((yy, xx))
        out.append((np.array(ys), np.array(xs)))
    return out


def _dilate(mask: Any, r: int) -> Any:
    out = mask.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dy or dx:
                out |= _shift(mask, dy, dx)
    return out


def candidates(  # noqa: PLR0913
    before: Any,
    after: Any,
    centre_uv: tuple[float, float],
    *,
    after_centre_uv: tuple[float, float] | None = None,
    later: Any = None,
    radius_px: int = 70,
    max_shift: int = 12,
    diff_thr: int = 40,
    q: int = 16,
    ground_frac: float = 0.003,
    vanished_min: int = 4,
    vanished_grow: int = 1,
    grow_px: int = 1,
    persist_thr: int = 45,
) -> list[Blob]:
    """PURE: every component of NEW pixels around the death spot, with its features (no size or
    colour gate yet; ``drop_blobs`` applies them). See ``drop_blobs`` for the arguments."""
    b = _rgb3(before)
    a = _rgb3(after)
    au, av = after_centre_uv if after_centre_uv is not None else centre_uv
    big = radius_px + max_shift + 2
    ca, ax0, ay0 = _crop(a, au, av, big)
    cb, _, _ = _crop(b, centre_uv[0], centre_uv[1], big)
    dy, dx = phase_shift(cb.mean(-1), ca.mean(-1), max_shift)
    cbr = _shift(cb, dy, dx)
    if dy or dx:  # keep the registration only if it explains the crop better than no shift
        d0 = np.abs(ca.astype(np.int16) - cb.astype(np.int16)).max(-1)
        d1 = np.abs(ca.astype(np.int16) - cbr.astype(np.int16)).max(-1)
        if np.median(d1) >= np.median(d0):
            cbr = cb
    diff = _min_diff(ca, cbr)
    valid = _inside(a, au, av, big)
    m = big - radius_px
    roi = np.zeros(ca.shape[:2], bool)
    roi[m:-m, m:-m] = True
    roi &= valid
    changed = (diff > diff_thr) & roi
    still = (diff <= diff_thr // 2) & valid
    bins_a, bins_b = _bins(ca, q), _bins(cbr, q)
    ground_min = max(3, int(ground_frac * still.sum()))  # a colour seen this often unchanged
    ground = _colour_set(ca, still, q, ground_min)
    ground_b = _colour_set(cbr, still, q, ground_min)
    vanished = _colour_set(cbr, changed & ~ground_b[bins_b], q, vanished_min, vanished_grow)
    scene = _colour_set(cbr, roi & ~ground_b[bins_b], q, vanished_min, vanished_grow)
    fresh = changed & ~ground[bins_a]  # changed, and not ground
    new = fresh & ~vanished[bins_a]  # ... and not the dying monster's (or the GM's old) colours
    stable = None
    if later is not None:
        lc, _, _ = _crop(_rgb3(later), au, av, big)
        ly, lx = phase_shift(ca.mean(-1), lc.mean(-1), max_shift)
        stable = _min_diff(ca, _shift(lc, ly, lx)) <= persist_thr
    out: list[Blob] = []
    if not new.any():
        return out
    grown = _dilate(new, grow_px) & roi
    for ys, xs in _components(grown):
        core = new[ys, xs]
        cy, cx = ys[core], xs[core]
        if len(cy) == 0:
            continue
        fy, fx = ys[fresh[ys, xs]], xs[fresh[ys, xs]]
        out.append(Blob(
            float(cx.mean()) + ax0, float(cy.mean()) + ay0, len(cy),
            int(cx.max() - cx.min() + 1), int(cy.max() - cy.min() + 1),
            float(vanished[bins_a[fy, fx]].mean()), float(scene[bins_a[cy, cx]].mean()),
            1.0 if stable is None else float(stable[cy, cx].mean()),
            float(np.median(diff[cy, cx]))))  # fmt: skip
    return out


def keep(blob: Blob, *, min_area: int = 10, max_area: int = 500, max_side: int = 34,
         max_vanished: float = 1.0, min_persist: float = 0.3, bar_ratio: float = 2.5,
         exclude: tuple[float, float, float, float] | None = GM_BOX) -> bool:  # fmt: skip
    """The blob gates (``drop_blobs``)."""
    if not min_area <= blob.area <= max_area or blob.w > max_side or blob.h > max_side:
        return False
    if blob.h <= 7 and blob.w >= bar_ratio * blob.h:  # an HP / SP bar
        return False
    if blob.vanished > max_vanished or blob.persist < min_persist:
        return False
    return not (exclude is not None and exclude[0] <= blob.u <= exclude[2]
                and exclude[1] <= blob.v <= exclude[3])  # fmt: skip


KEEP_ARGS = ("min_area", "max_area", "max_side", "max_vanished", "min_persist", "bar_ratio",
             "exclude")  # fmt: skip


def drop_blobs(before: Any, after: Any, centre_uv: tuple[float, float], **kw: Any) -> list[Blob]:
    """PURE: NEW small compact blobs around a death spot, between ``before`` (the monster alive,
    just before the kill) and ``after`` (~0.5-1 s after the death); ``later`` (optional, after
    ``after``) requires each blob to persist.

    Images are H x W x 3 or 4 (alpha ignored), uint8, all in the SAME channel order: every step
    is invariant to the order (max-channel differences, grey = channel mean, colour sets built
    and used on the same image order), so RGB recordings and BGR(A) mss grabs both work.

    ``centre_uv`` is the death spot in BEFORE's pixels; ``after_centre_uv`` the same ground point in
    AFTER's pixels when the camera scrolled (the GM moved; default: unchanged). The remaining
    scroll (<= ``max_shift`` px) is registered away by phase correlation. Only a square of half
    side ``radius_px`` around the spot is searched.

    A pixel is NEW when it differs from every pixel of the registered BEFORE within 1 px by more
    than ``diff_thr`` (max channel) and its colour is unlike the local GROUND (the colours of the
    unchanged pixels). NEW pixels form components (8-connected after a 1-px grow). A component is
    a drop when ``min_area`` <= its NEW pixels <= ``max_area``, both box sides <= ``max_side``, it
    is not a thin bar (an HP / SP bar), at most ``max_vanished`` of its pixels have VANISHED
    colours (BEFORE's changed non-ground colours: the dying monster -- so its corpse splat and
    fading frames are not new --, the GM's previous pose, the HP bars), at least ``min_persist``
    are still there in ``later``, and its centre is outside ``exclude`` (AFTER's pixels: the GM's
    sprite; None keeps them)."""
    gates = {k: kw.pop(k) for k in KEEP_ARGS if k in kw}
    return [b for b in candidates(before, after, centre_uv, **kw) if keep(b, **gates)]


# --- offline evaluation: sessions, kills, drops, projection ---------------------------------------


@dataclass
class Drop:
    floor_id: int
    item_id: int
    x: int
    y: int
    sub_x: int
    sub_y: int
    t: int


@dataclass
class Kill:
    gid: int
    job: int
    t: int  # entity_vanish reason 1
    cell: tuple[float, float] | None  # the monster's last position (packets), fractional
    drops: list[Drop] = field(default_factory=list)


def load_events(sid: str) -> list[dict[str, Any]]:
    with gzip.open(DEMO_ROOT / sid / "packets.jsonl.gz", "rt") as fh:
        return sorted((json.loads(x) for x in fh), key=lambda e: int(e["t_mono_ns"]))


def load_frames(sid: str) -> list[tuple[int, Path]]:
    d = REC_ROOT / sid / "frames"
    out = []
    for name in os.listdir(d):  # one directory (no walk)
        if name.endswith(".jpg"):
            out.append((int(name[:-4].split("-")[1]), d / name))
    out.sort()
    return out


def _gid(e: dict[str, Any], key: str = "gid") -> int:
    v = e.get(key)
    return -1 if v is None else int(v)


def _cheb_path(a: Cell, b: Cell) -> list[Cell]:
    out, (x, y) = [], a
    while (x, y) != b:
        x += (b[0] > x) - (b[0] < x)
        y += (b[1] > y) - (b[1] < y)
        out.append((x, y))
    return out


def _walk_at(a: Cell, b: Cell, t0: int, ms_cell: float, t: int) -> tuple[float, float]:
    """Fractional position at ``t`` along a Chebyshev walk a -> b started at ``t0``."""
    prev, tt = (float(a[0]), float(a[1])), float(t0)
    for c in _cheb_path(a, b):
        diag = c[0] != prev[0] and c[1] != prev[1]
        dt = ms_cell * (1.4 if diag else 1.0) * 1e6
        if t < tt + dt:
            f = max(0.0, (t - tt) / dt)
            return prev[0] + f * (c[0] - prev[0]), prev[1] + f * (c[1] - prev[1])
        prev, tt = (float(c[0]), float(c[1])), tt + dt
    return prev


class Positions:
    """Fractional positions over time from packets: our GM (self_move / entity_stop / map_change)
    and every monster (entity_appear stand|move / entity_stop)."""

    def __init__(self, events: Sequence[dict[str, Any]]) -> None:
        self.gm: list[tuple[int, Cell, Cell, float]] = []  # (t0, from, to, ms/cell)
        self.mob: dict[int, list[tuple[int, Cell, Cell, float]]] = {}
        for e in events:
            t, typ = int(e["t_mono_ns"]), e.get("type")
            if typ == "self_move":
                self.gm.append((t, (int(e["x0"]), int(e["y0"])), (int(e["x1"]), int(e["y1"])),
                                MS_CELL))  # fmt: skip
            elif typ == "map_change" or (typ == "entity_stop" and _gid(e) == GM):
                c = (int(e["x"]), int(e["y"]))
                self.gm.append((t, c, c, MS_CELL))
            elif typ == "entity_appear" and e.get("objtype") == 5:
                a = (int(e["x"]), int(e["y"]))
                b = (int(e["x1"]), int(e["y1"])) if e.get("x1") is not None else a
                self.mob.setdefault(_gid(e), []).append((t, a, b, float(e.get("speed") or 200)))
            elif typ == "entity_stop" and _gid(e) in self.mob:
                c = (int(e["x"]), int(e["y"]))
                self.mob[_gid(e)].append((t, c, c, 200.0))
        self._gm_t = [p[0] for p in self.gm]

    @staticmethod
    def _at(seq: Sequence[tuple[int, Cell, Cell, float]], ts: Sequence[int] | None,
            t: int) -> tuple[float, float] | None:  # fmt: skip
        if ts is None:
            ts = [p[0] for p in seq]
        i = bisect.bisect_right(ts, t) - 1
        if i < 0:
            return None
        t0, a, b, ms = seq[i]
        return _walk_at(a, b, t0, ms, t)

    def gm_at(self, t: int) -> tuple[float, float] | None:
        return self._at(self.gm, self._gm_t, t)

    def mob_at(self, gid: int, t: int) -> tuple[float, float] | None:
        seq = self.mob.get(gid)
        return None if not seq else self._at(seq, None, t)


def kills_with_drops(events: Sequence[dict[str, Any]], pos: Positions,
                     window_s: tuple[float, float] = (-1.5, 0.5), near: int = 2
                     ) -> list[Kill]:  # fmt: skip
    """OUR kills (entity_vanish reason 1 of a monster our GM damaged in the 30 s before) and the
    drops tied to each (floor_item_appear kind 'fall' in ``window_s`` of the vanish and within
    ``near`` cells of the monster's last position; the nearest kill in time wins)."""
    hit: dict[int, int] = {}
    job: dict[int, int] = {}
    kills: list[Kill] = []
    for e in events:
        t, typ = int(e["t_mono_ns"]), e.get("type")
        if typ == "entity_appear" and e.get("objtype") == 5:
            job.setdefault(_gid(e), int(e.get("job", -1)))
        elif (typ == "act" and _gid(e, "src_gid") == GM and int(e.get("damage") or 0) > 0
              and e.get("target_gid") is not None):  # fmt: skip
            hit[_gid(e, "target_gid")] = t
        elif typ == "entity_vanish" and int(e.get("reason", -1)) == 1:
            g = _gid(e)
            if g in hit and 0 <= t - hit[g] <= 30 * NS:
                kills.append(Kill(g, job.get(g, -1), t, pos.mob_at(g, t)))
    for e in events:
        if e.get("type") != "floor_item_appear" or e.get("kind") != "fall":
            continue
        t = int(e["t_mono_ns"])
        d = Drop(int(e["floor_id"]), int(e.get("item_id") or -1), int(e["x"]), int(e["y"]),
                 int(e["sub_x"]), int(e["sub_y"]), t)  # fmt: skip
        best, best_dt = None, None
        for k in kills:
            dt = (t - k.t) / NS
            if not window_s[0] <= dt <= window_s[1] or k.cell is None:
                continue
            if max(abs(d.x - k.cell[0]), abs(d.y - k.cell[1])) > near + 0.5:
                continue
            if best_dt is None or abs(dt) < abs(best_dt):
                best, best_dt = k, dt
        if best is not None:
            best.drops.append(d)
    return kills


class Projector:
    """Screen pixels (game region, 1280 x 720) of fractional cells, the camera centred on our GM's
    fractional cell (hunt_flow.frac_project, walk5.World without the live imports)."""

    def __init__(self, map_name: str = MAP) -> None:
        from poring_dataset import camera as cam
        from poring_dataset import gat as gatmod

        self.gat = gatmod.parse((cam.GAT_DIR / f"{map_name}.gat").read_bytes())
        cj = json.loads((ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                        .read_text())  # fmt: skip
        self.camera = cam.camera_from_json(cj["camera"])

    def project(self, origin: Sequence[float], cells: Any) -> Any:
        r0 = (int(round(origin[0])), int(round(origin[1])))
        frac = np.array([origin[0] - r0[0], origin[1] - r0[1]])
        c = np.atleast_2d(np.asarray(cells, dtype=float)) - frac - np.asarray(r0, dtype=float)
        return self.camera.project(c, self.gat.relative_altitude(r0, c))


def item_cell(d: Drop, mode: str = "sub12") -> tuple[float, float]:
    """The item's fractional cell. RO's sub_x / sub_y are 3, 6, 9 or 12 (rAthena: (r & 3) * 3 + 3).
    sub12: cell - 0.5 + sub / 12 (roBrowser's reading); sub16: cell + (sub - 8) / 16; none."""
    if mode == "sub12":
        return d.x - 0.5 + d.sub_x / 12, d.y - 0.5 + d.sub_y / 12
    if mode == "sub16":
        return d.x + (d.sub_x - 8) / 16, d.y + (d.sub_y - 8) / 16
    return float(d.x), float(d.y)


def read_rgb(path: Path) -> Any:
    try:
        import simplejpeg

        return simplejpeg.decode_jpeg(path.read_bytes(), colorspace="RGB")
    except ImportError:
        from PIL import Image

        with Image.open(path) as im:
            return np.asarray(im.convert("RGB"))


def frame_at(frames: Sequence[tuple[int, Path]], t: int) -> tuple[int, Path] | None:
    """The first frame at or after ``t``."""
    i = bisect.bisect_left(frames, (t, Path("")))
    return frames[i] if i < len(frames) else None


def frame_before(frames: Sequence[tuple[int, Path]], t: int) -> tuple[int, Path] | None:
    i = bisect.bisect_left(frames, (t, Path(""))) - 1
    return frames[i] if i >= 0 else None


# --- CLI ------------------------------------------------------------------------------------------


def cmd_sheet(a: argparse.Namespace) -> int:
    from PIL import Image, ImageDraw

    events = load_events(a.sid)
    frames = load_frames(a.sid)
    pos = Positions(events)
    kills = [k for k in kills_with_drops(events, pos) if k.drops]
    proj = Projector()
    offs = [float(x) for x in a.offsets.split(",")]
    cw, ch = 200, 140
    rows = kills[a.skip : a.skip + a.n]
    sheet = Image.new("RGB", (cw * len(offs), ch * len(rows)), (0, 0, 0))
    dr = ImageDraw.Draw(sheet)
    for ri, k in enumerate(rows):
        for ci, off in enumerate(offs):
            f = frame_at(frames, k.t + int(off * NS))
            if f is None:
                continue
            img = read_rgb(f[1])
            o = pos.gm_at(f[0] - int(a.lag * NS))
            if o is None:
                continue
            pts = proj.project(o, [item_cell(d, a.sub) for d in k.drops])
            cu, cv = pts.mean(0)
            x0, y0 = int(cu) - cw // 2, int(cv) - ch // 2
            pad = np.zeros((ch, cw, 3), np.uint8)
            xs0, ys0 = max(0, x0), max(0, y0)
            xs1, ys1 = min(img.shape[1], x0 + cw), min(img.shape[0], y0 + ch)
            if xs1 > xs0 and ys1 > ys0:
                pad[ys0 - y0 : ys1 - y0, xs0 - x0 : xs1 - x0] = img[ys0:ys1, xs0:xs1]
            sheet.paste(Image.fromarray(pad), (ci * cw, ri * ch))
            for p in pts:
                px, py = ci * cw + p[0] - x0, ri * ch + p[1] - y0
                dr.ellipse((px - 2, py - 2, px + 2, py + 2), outline=(255, 0, 0))
            dr.text((ci * cw + 2, ri * ch + 2), f"{off:+.1f} {f[1].name[:5]}", fill=(255, 255, 0))
        print(ri, k.gid, k.job, len(k.drops), [(d.x, d.y, d.sub_x, d.sub_y) for d in k.drops],
              k.cell)  # fmt: skip
    sheet.save(a.out)
    print(a.out)
    return 0


@dataclass
class Case:
    sid: str
    gid: int
    job: int
    t: int
    delay: float
    variant: str
    before: str
    after: str
    items: list[tuple[float, float]]  # projected, AFTER's pixels
    blobs: list[tuple[float, float, int]]
    cands: list[dict[str, Any]]
    gm_moved: float  # cells between the two frames' origins
    centre: tuple[float, float]  # AFTER's pixels
    centre_before: tuple[float, float]


def _nearest(p: Sequence[float], blobs: Sequence[tuple[float, float, int]]) -> float:
    return min((math.hypot(p[0] - b[0], p[1] - b[1]) for b in blobs), default=math.inf)


def eval_session(sid: str, delays: Sequence[float], variants: Sequence[str], before_s: float,
                 later_s: float | None, lag_s: float, sub: str, prm: dict[str, Any],
                 proj: Projector, dump: bool = False) -> list[Case]:  # fmt: skip
    events = load_events(sid)
    frames = load_frames(sid)
    pos = Positions(events)
    kills = kills_with_drops(events, pos)
    cache: dict[Path, Any] = {}

    def img(p: Path) -> Any:
        if p not in cache:
            if len(cache) > 64:
                cache.clear()
            cache[p] = read_rgb(p)
        return cache[p]

    out: list[Case] = []
    for k in kills:
        if k.cell is None:
            continue
        fb = frame_before(frames, k.t - int(before_s * NS))
        if fb is None:
            continue
        ob = pos.gm_at(fb[0] - int(lag_s * NS))
        cells = [item_cell(d, sub) for d in k.drops]
        for delay in delays:
            fa = frame_at(frames, k.t + int(delay * NS))
            if fa is None:
                continue
            oa = pos.gm_at(fa[0] - int(lag_s * NS))
            if ob is None or oa is None:
                continue
            fl = None if later_s is None else frame_at(frames, fa[0] + int(later_s * NS))
            items = [tuple(map(float, p)) for p in proj.project(oa, cells)] if cells else []
            for var in variants:
                if var == "items" and cells:
                    c = (
                        float(np.mean([x for x, _ in cells])),
                        float(np.mean([y for _, y in cells])),
                    )
                else:
                    c = k.cell
                cb = proj.project(ob, [c])[0]
                ca = proj.project(oa, [c])[0]
                gates = {x: prm[x] for x in KEEP_ARGS if x in prm}
                rest = {x: v for x, v in prm.items() if x not in KEEP_ARGS}
                cand = candidates(img(fb[1]), img(fa[1]), (float(cb[0]), float(cb[1])),
                                  after_centre_uv=(float(ca[0]), float(ca[1])),
                                  later=None if fl is None else img(fl[1]), **rest)  # fmt: skip
                blobs = [x for x in cand if keep(x, **gates)]
                out.append(
                    Case(
                        sid,
                        k.gid,
                        k.job,
                        k.t,
                        delay,
                        var,
                        fb[1].name,
                        fa[1].name,
                        items,
                        [(b.u, b.v, b.area) for b in blobs],
                        [x.__dict__ for x in cand] if dump else [],
                        math.hypot(oa[0] - ob[0], oa[1] - ob[1]),
                        (float(ca[0]), float(ca[1])),
                        (float(cb[0]), float(cb[1])),
                    )
                )
    return out


def summarise(cases: Sequence[Case], radii: Sequence[int]) -> dict[str, Any]:
    """Per (variant, delay): recall@R over items, false blobs per kill (blobs with no item within
    R) over ALL kills and over kills with drops; also the GM-still subset."""
    out: dict[str, Any] = {}
    keys = sorted({(c.variant, c.delay) for c in cases})
    for var, delay in keys:
        cs = [c for c in cases if c.variant == var and c.delay == delay]
        row: dict[str, Any] = {"kills": len(cs), "kills_with_drops": sum(1 for c in cs if c.items),
                               "items": sum(len(c.items) for c in cs),
                               "blobs_per_kill": round(sum(len(c.blobs) for c in cs)
                                                       / max(1, len(cs)), 2)}  # fmt: skip
        for r in radii:
            hit = sum(1 for c in cs for p in c.items if _nearest(p, c.blobs) <= r)
            false = sum(
                1
                for c in cs
                for b in c.blobs
                if all(math.hypot(b[0] - p[0], b[1] - p[1]) > r for p in c.items)
            )
            still = [c for c in cs if c.gm_moved < 0.3]
            hit_s = sum(1 for c in still for p in c.items if _nearest(p, c.blobs) <= r)
            n_s = sum(len(c.items) for c in still)
            row[f"R{r}"] = {
                "recall": round(hit / max(1, row["items"]), 3),
                "false_per_kill": round(false / max(1, len(cs)), 2),
                "recall_gm_still": round(hit_s / max(1, n_s), 3),
                "n_still": n_s,
            }
        out[f"{var}@{delay}"] = row
    return out


def projection_check(cases: Sequence[Case], within: float = 30.0) -> dict[str, Any]:
    """Each projected item -> its nearest blob within ``within`` px: the offset (blob - item)."""
    vec = []
    for c in cases:
        for p in c.items:
            best = min(c.blobs, key=lambda b: math.hypot(b[0] - p[0], b[1] - p[1]), default=None)
            if best is not None and math.hypot(best[0] - p[0], best[1] - p[1]) <= within:
                vec.append((best[0] - p[0], best[1] - p[1], c.gm_moved))
    if not vec:
        return {"n": 0}
    a = np.array(vec)
    still = a[a[:, 2] < 0.3]
    moving = a[a[:, 2] >= 0.3]

    def st(x: Any) -> dict[str, Any]:
        if len(x) == 0:
            return {"n": 0}
        d = np.hypot(x[:, 0], x[:, 1])
        return {"n": len(x), "du_p50": round(float(np.median(x[:, 0])), 1),
                "dv_p50": round(float(np.median(x[:, 1])), 1),
                "dist_p50": round(float(np.median(d)), 1),
                "dist_p90": round(float(np.percentile(d, 90)), 1)}  # fmt: skip

    return {"all": st(a), "gm_still": st(still), "gm_moving": st(moving)}


def cmd_eval(a: argparse.Namespace) -> int:
    proj = Projector()
    delays = [float(x) for x in a.delays.split(",")]
    variants = a.variants.split(",")
    radii = [int(x) for x in a.radii.split(",")]
    prm: dict[str, Any] = json.loads(a.params) if a.params else {}
    if isinstance(prm.get("exclude"), list):
        prm["exclude"] = tuple(prm["exclude"])
    if a.no_exclude:
        prm["exclude"] = None
    later = None if a.later < 0 else a.later
    report: dict[str, Any] = {"params": prm, "before_s": a.before, "later_s": later,
                              "lag_s": a.lag, "sub": a.sub, "sessions": {}}  # fmt: skip
    allc: list[Case] = []
    for sid in a.sids:
        cs = eval_session(sid, delays, variants, a.before, later, a.lag, a.sub, prm, proj,
                          dump=bool(a.json))  # fmt: skip
        allc += cs
        report["sessions"][sid] = summarise(cs, radii)
        report["sessions"][sid]["projection"] = projection_check(
            [c for c in cs if c.variant == variants[0] and c.delay == max(delays)]
        )
        print(sid, json.dumps(report["sessions"][sid]), flush=True)
    report["pooled"] = summarise(allc, radii)
    report["pooled"]["projection"] = projection_check(
        [c for c in allc if c.variant == variants[0] and c.delay == max(delays)]
    )
    print("POOLED", json.dumps(report["pooled"], indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps({"report": report,
                                            "cases": [c.__dict__ for c in allc]}))  # fmt: skip
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sheet")
    s.add_argument("sid")
    s.add_argument("--n", type=int, default=8)
    s.add_argument("--skip", type=int, default=0)
    s.add_argument("--offsets", default="-0.4,0,0.3,0.5,0.8,1.0,1.5")
    s.add_argument("--lag", type=float, default=LAG_S)
    s.add_argument("--sub", default="sub12")
    s.add_argument("--out", default="/dev/shm/poring-lab-tmp/loot-blobs/sheet.png")
    e = sub.add_parser("eval")
    e.add_argument("sids", nargs="+")
    e.add_argument("--delays", default="0.3,0.5,0.8,1.0,1.5")
    e.add_argument("--variants", default="mob,items")
    e.add_argument("--radii", default="10,15,20")
    e.add_argument(
        "--before",
        type=float,
        default=0.4,
        help="BEFORE = the last frame this many s before the death (entity_vanish reason 1)",
    )
    e.add_argument(
        "--later",
        type=float,
        default=0.4,
        help="LATER = this many s after AFTER (persistence; < 0: off)",
    )
    e.add_argument("--lag", type=float, default=LAG_S)
    e.add_argument("--sub", default="sub12")
    e.add_argument("--params", default="", help="JSON: drop_blobs keyword overrides")
    e.add_argument("--no-exclude", action="store_true", help="keep blobs in the GM's sprite box")
    e.add_argument("--json", default="")
    a = ap.parse_args()
    if a.cmd == "sheet":
        return cmd_sheet(a)
    if a.cmd == "eval":
        return cmd_eval(a)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
