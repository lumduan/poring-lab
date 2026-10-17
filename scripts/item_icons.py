#!/usr/bin/env python3
"""LOOT by RECOGNISING the floor item sprites (Batt 2026-10-17, the third approach): a floor item
is drawn as its item sprite (~10-30 px) at a fixed spot on the ground until it is picked, so a
small set of per-item templates (the prt_fild08 drop table) finds it from ONE frame, wherever it
lies -- also at the GM's feet, where frame differencing (drop_blobs.py) fails.

    item_icons.py build SID [SID ...] [--out DIR]   OFFLINE: labelled crops -> templates (DIR)
    item_icons.py eval SID [SID ...] [--icons DIR]  OFFLINE: recall / false per kill (held out)
    item_icons.py sheet --icons DIR --out PNG       OFFLINE: the templates, enlarged (debug)
    item_icons.py bench --icons DIR                 the matcher's cost on a 200 x 200 region

THE MATCHER (pure, ``find_items``): masked colour template matching over a square around a death
spot. Per template (an RGB patch + a mask of the item's own pixels, the ground left out) and per
position, the masked zero-mean colour NCC (the three channels as one vector: colour-sensitive,
invariant to a joint gain / offset) and the masked RMS colour distance, both FFT correlations
(numpy only: per call 5 forward transforms of the region, per template 3 inverse ones). Local NCC
maxima passing the template's ``ncc_min`` / ``rms_max`` are CANDIDATES; a candidate is a MATCH
when its INLIER share (the share of the sprite's own pixels within INLIER_PX of the template, every
channel) >= ``inl_min`` -- robust to a partly covered sprite (the Poring's pink corpse splat, the
cursor, the GM's feet). The best match wins a position; matches within ``nms_px`` are merged.
Channel order: an explicit ``order`` ('RGB' recordings, 'BGR' live mss grabs; alpha ignored)
flips the templates, never the frame.

THE TEMPLATES (offline, ``build``; client-derived, NEVER committed: data/ is gitignored): for every
floor item (floor_item_appear .. floor_item_vanish, packets as OFFLINE ground truth) on a frame
sampled every 0.4 s, the crop around its projected pixel (drop_blobs.Projector, the item's sub12
cell, the camera on the GM 0.5 s earlier), when it is clear: inside the game area off the UI
windows, outside the GM's sprite box + 12 px, outside the live detector's monster boxes (the
session's boxes.jsonl) + 10 px, no live monster within 1 cell, no other floor item within 22 px.
Per item_id at most PER_INSTANCE crops per floor item (spread in time: one long-lived item must
not dominate). Each crop is SEEDED on its most likely salient blob (saliency = distance to the
15 x 15 mean colour; the blob nearest the projected point, weighted by its contrast), the median
of the seeded windows gives a first template + mask, then each crop is re-aligned by masked NCC
(+-REFINE px) and the worst 20 % dropped, 4 rounds. The MASK = pixels differing from each crop's
own ground (its border ring's median colour) in >= 60 % of the crops, AND agreeing across crops
(MAD <= 40) when that keeps >= half of it. The ANCHOR = the median offset of the sprite centre from
the projected ground point (the eval's truth = projection + anchor). The thresholds are TUNED per
template on training kills (``tune``: true - 2 x false); a template that cannot beat zero is
switched off (ncc_min = OFF).

THE EVALUATION (offline, ``eval``): drop_blobs' kills (our kills and their 'fall' drops); on the
first frame ``delay`` s after the death, the matcher searches a 200 x 200 square around the dead
monster's projected last cell. recall@R = this kill's drops still on the floor (not yet vanished
at the frame's server time) with a match within R px of the truth; a FALSE match has no floor item
at all (any kill's, any age) within R. "feet" = drops whose truth lies within FEET_PX of the GM's
sprite centre; "still" = the GM moved < 0.05 cells in the 0.6 s before (the projection, i.e. the
truth itself, is off by up to ~30 px while the GM walks).

MEASURED 2026-10-17 (templates built and tuned on hunt-flow17 / flow18 / flow20 04:42; HELD OUT:
flow20 05:55, 82 kills; 8 templates: 909 Jellopy 617 crops / 118 floor items, 705 Clover 452 / 80
-- switched off by the tuning, it matches grass --, 512 Apple 313 / 57, 713 Empty Bottle 145 / 30,
949 Feather 85 / 18, 507 Red Herb 85 / 16, 515 Carrot 48 / 9, 938 Sticky Mucus 45 / 9; 619 Unripe
Apple, 1202 Knife, 620 too rare):
  delay 1.0 s  recall@15 0.35 (GM still 0.40, feet 0.32 of 71)  false/kill 0.15   @25 0.39
  delay 1.5 s  recall@15 0.39 (GM still 0.42, feet 0.33 of 55)  false/kill 0.12   @25 0.44
  delay 2.5 s  recall@15 0.39 (GM still 0.52, feet 0.42 of 43)  false/kill 0.16   @25 0.47
  delay 4.0 s  recall@15 0.39 (GM still 0.41, feet 0.24 of 33)  false/kill 0.15   @25 0.44
Per item at 2.5 s: Jellopy 29 / 56, Apple 8 / 17, Carrot 3 / 4, Feather 3 / 6, Mucus 2 / 2,
Bottle 1 / 6, Herb 0 / 3, Clover 1 / 24 (off), Knife 0 / 2 (no template). Most "false" matches lie
15-28 px from a real item while the GM walks (the truth's error, not the matcher's). Cost: ~60 ms
per call on a 200 x 200 square, 7 templates on (numpy FFT, one core at nice 15, host load ~26).
Misses: a sprite under the GM's body or a dying Lunatic's white puff, the Jellopy inside the
Poring's pink corpse splat (inlier share < 0.4), the bot's own sword / hand cursor over it, Clover
on grass, and truth errors while the GM walks.
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import sys
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
ICONS_DIR = ROOT / "data" / "item_icons"
SCRATCH = Path("/dev/shm/poring-lab-tmp/item-icons")
NS = 10**9
GM_CENTRE = (640.0, 340.0)  # the GM's drawn sprite centre (client px; drop_blobs.GM_BOX)
FEET_PX = 60.0  # "at the GM's feet": within this distance of GM_CENTRE

# Build parameters
SEARCH = 24  # alignment search, +- px around the projected point
HALF = 10  # template window half side before the mask's tight crop (21 x 21; items ~8-16 px)
CROP_HALF = 44  # the stored crop's half side (>= SEARCH + HALF + the refine step)
SAL_THR = 45.0  # saliency: max-channel distance to the 15 x 15 box mean
MAD_KEEP = 0.5  # the consistency mask is used when it keeps at least this share of the item mask
REFINE = 6  # +- px of each masked-NCC re-alignment around the current shift
PER_INSTANCE = 8
MIN_SAMPLES = 12
INLIER_PX = 32  # a sprite pixel matches when every channel is within this of the template's
OFF = 2.0  # an ncc_min no position reaches: the template is switched off


# --- the matcher (PURE) --------------------------------------------------------------------------


@dataclass
class IconTemplate:
    item_id: int
    rgb: Any  # h x w x 3 float32, RGB order
    mask: Any  # h x w bool: the item's own pixels
    anchor: tuple[float, float] = (0.0, 0.0)  # sprite centre - projected ground point (px)
    ncc_min: float = 0.6
    rms_max: float = 40.0
    inl_min: float = 0.5
    samples: int = 0
    instances: int = 0
    _fft: dict[tuple[Any, ...], Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def size(self) -> tuple[int, int]:
        return int(self.rgb.shape[0]), int(self.rgb.shape[1])

    def spectra(self, shape: tuple[int, int], order: str) -> tuple[Any, Any, float, float, int,
                                                                   float]:  # fmt: skip
        """Cached per (padded shape, order): F(M (T_c - mu)) per channel, F(M), the masked mean
        mu, sum M (T - mu)^2, the masked pixel count x 3 and sum M T^2."""
        key = (shape, order)
        if key not in self._fft:
            t = np.asarray(self.rgb, np.float64)
            if order.upper() == "BGR":
                t = t[..., ::-1]
            m = np.asarray(self.mask, bool)
            n = int(m.sum()) * 3
            mu = float(t[m].sum() / max(1, n))
            tp = np.where(m[..., None], t - mu, 0.0)
            ft = np.stack([_rfft_flip(tp[..., c], shape) for c in range(3)])
            fm = _rfft_flip(m.astype(np.float64), shape)
            self._fft[key] = (ft, fm, mu, float((tp**2).sum()), n,
                              float((np.where(m[..., None], t, 0.0) ** 2).sum()))  # fmt: skip
        return self._fft[key]  # type: ignore[no-any-return]


def _rfft_flip(a: Any, shape: tuple[int, int]) -> Any:
    """F of the template flipped and zero-padded to ``shape``: then irfft(F(I) * this) is the
    correlation sum_q a(q) I(p + q) with the template's (0, 0) at p - (h - 1, w - 1)."""
    return np.fft.rfft2(np.asarray(a)[::-1, ::-1], s=shape)


def _fast_len(n: int) -> int:
    """The next length with only 2, 3, 5 as factors (pocketfft is fastest there)."""
    while True:
        m = n
        for p in (2, 3, 5):
            while m % p == 0:
                m //= p
        if m == 1:
            return n
        n += 1


def _local_max(s: Any, r: int) -> Any:
    """True where ``s`` is the maximum of its (2 r + 1)^2 neighbourhood (separable max)."""
    h, w = s.shape
    p = np.pad(s, ((0, 0), (r, r)), constant_values=-np.inf)
    row = p[:, :w].copy()
    for dx in range(1, 2 * r + 1):
        np.maximum(row, p[:, dx : dx + w], out=row)
    p = np.pad(row, ((r, r), (0, 0)), constant_values=-np.inf)
    best = p[:h].copy()
    for dy in range(1, 2 * r + 1):
        np.maximum(best, p[dy : dy + h], out=best)
    return s >= best


def match_maps(region: Any, templates: Sequence[IconTemplate], order: str = "RGB"
               ) -> list[tuple[Any, Any]]:  # fmt: skip
    """PURE: per template, its (ncc, rms) maps over ``region`` (H x W x 3|4), indexed by the
    template's TOP-LEFT corner: maps[i][0][y, x] is the score with the template's (0, 0) at
    (x, y). Positions where the template leaves the region are -inf / inf."""
    r = np.asarray(region)[..., :3].astype(np.float64)
    hh, ww = r.shape[:2]
    th = max(t.size[0] for t in templates)
    tw = max(t.size[1] for t in templates)
    shape = (_fast_len(hh + th), _fast_len(ww + tw))
    fi = [np.fft.rfft2(r[..., c], s=shape) for c in range(3)]
    s_i = np.fft.rfft2(r.sum(-1), s=shape)
    s_i2 = np.fft.rfft2((r**2).sum(-1), s=shape)
    out = []
    for t in templates:
        ft, fm, mu, tvar, n, tsq = t.spectra(shape, order)
        h, w = t.size
        num = np.fft.irfft2(fi[0] * ft[0] + fi[1] * ft[1] + fi[2] * ft[2], s=shape)
        s1 = np.fft.irfft2(s_i * fm, s=shape)
        s2 = np.fft.irfft2(s_i2 * fm, s=shape)
        # full correlation index p corresponds to the top-left at p - (h - 1, w - 1)
        sl = (slice(h - 1, hh), slice(w - 1, ww))
        num, s1, s2 = num[sl], s1[sl], s2[sl]
        var_i = np.maximum(s2 - s1 * s1 / n, 1e-6)
        ncc = num / np.sqrt(var_i * max(tvar, 1e-6))
        ssd = s2 - 2.0 * (num + mu * s1) + tsq
        rms = np.sqrt(np.maximum(ssd, 0.0) / n)
        full_n = np.full((hh, ww), -np.inf)
        full_r = np.full((hh, ww), np.inf)
        full_n[: ncc.shape[0], : ncc.shape[1]] = ncc
        full_r[: rms.shape[0], : rms.shape[1]] = rms
        out.append((full_n, full_r))
    return out


def find_items(  # noqa: PLR0913
    img: Any,
    centre_uv: tuple[float, float],
    radius_px: int,
    templates: Sequence[IconTemplate],
    *,
    order: str = "RGB",
    nms_px: float = 10.0,
    ncc_min: float | None = None,
    rms_max: float | None = None,
    inl_min: float | None = None,
    exclude: Iterable[tuple[float, float, float, float]] = (),
    details: bool = False,
) -> list[tuple[float, float, int, float]]:
    """PURE: the floor items around ``centre_uv`` (full-frame pixels): every sprite CENTRE within
    the square of half side ``radius_px`` where a template matches, as (u, v, item_id, score)
    sorted by score: the INLIER share, the share of the sprite's own (mask) pixels within
    INLIER_PX (max channel) of the template -- robust to a partly covered sprite (a corpse splat,
    the cursor, the GM's feet). ``img`` is H x W x 3|4 uint8 in ``order`` ('RGB' or 'BGR'; alpha
    ignored). A position is a candidate at a local maximum of the masked colour NCC with NCC >=
    the template's ``ncc_min`` and masked RMS colour distance <= its ``rms_max``, and a match when
    its inlier share >= its ``inl_min`` (the arguments, when given, override every template's
    own). The best-scoring template wins a position; hits within ``nms_px`` of a better one are
    dropped (``nms_px`` <= 0: none). Centres inside an ``exclude`` box (x0, y0, x1, y1) are
    dropped. ``details`` returns (u, v, item_id, ncc, rms, inlier share) instead."""
    a = np.asarray(img)
    if a.ndim != 3 or a.shape[2] not in (3, 4):
        raise ValueError(f"expected an H x W x 3|4 image, got {a.shape}")
    templates = [t for t in templates if (t.ncc_min if ncc_min is None else ncc_min) <= 1.0]
    if not templates:  # none, or every one switched off
        return []
    th = max(t.size[0] for t in templates)
    tw = max(t.size[1] for t in templates)
    H, W = a.shape[:2]
    cu, cv = int(round(centre_uv[0])), int(round(centre_uv[1]))
    x0 = max(0, cu - radius_px - tw // 2 - 1)
    y0 = max(0, cv - radius_px - th // 2 - 1)
    x1 = min(W, cu + radius_px + tw // 2 + 2)
    y1 = min(H, cv + radius_px + th // 2 + 2)
    if x1 - x0 < tw or y1 - y0 < th:
        return []
    region = a[y0:y1, x0:x1, :3]
    maps = match_maps(region, templates, order)
    rf = region.astype(np.int16)
    cands: list[tuple[float, float, float, int, float, float]] = []
    boxes = list(exclude)
    for t, (ncc, rms) in zip(templates, maps, strict=True):
        h, w = t.size
        nmin = t.ncc_min if ncc_min is None else ncc_min
        rmax = t.rms_max if rms_max is None else rms_max
        imin = t.inl_min if inl_min is None else inl_min
        ok = (ncc >= nmin) & (rms <= rmax)
        if not ok.any():
            continue
        ys, xs = np.nonzero(ok & _local_max(np.where(ok, ncc, -np.inf), 2))
        u = x0 + xs + (w - 1) / 2.0
        v = y0 + ys + (h - 1) / 2.0
        keep = (np.abs(u - centre_uv[0]) <= radius_px) & (np.abs(v - centre_uv[1]) <= radius_px)
        for b in boxes:
            keep &= ~((u >= b[0]) & (u <= b[2]) & (v >= b[1]) & (v <= b[3]))
        ys, xs, u, v = ys[keep], xs[keep], u[keep], v[keep]
        if not len(ys):
            continue
        my, mx = np.nonzero(np.asarray(t.mask, bool))
        tpl = np.asarray(t.rgb, np.float32)
        if order.upper() == "BGR":
            tpl = tpl[..., ::-1]
        patch = rf[ys[:, None] + my[None, :], xs[:, None] + mx[None, :]]  # n x m x 3
        dist = np.abs(patch - tpl[my, mx].round().astype(np.int16)[None]).max(-1)
        inl = (dist <= INLIER_PX).mean(1)
        for i in np.nonzero(inl >= imin)[0]:
            y, x = int(ys[i]), int(xs[i])
            cands.append((float(inl[i]), float(u[i]), float(v[i]), t.item_id, float(ncc[y, x]),
                          float(rms[y, x])))  # fmt: skip
    cands.sort(key=lambda c: (-c[0], -c[4]))
    kept = _nms(cands, nms_px, 1, 2)
    if details:
        return [(k[1], k[2], k[3], k[4], k[5], k[0]) for k in kept]  # type: ignore[misc]
    return [(k[1], k[2], k[3], k[0]) for k in kept]


def _nms(cands: list[Any], nms_px: float, iu: int, iv: int) -> list[Any]:
    """Greedy: ``cands`` (sorted best first) without those within ``nms_px`` of a kept one."""
    if nms_px <= 0 or len(cands) < 2:
        return list(cands)
    kept: list[Any] = []
    ku = np.empty(len(cands))
    kv = np.empty(len(cands))
    r2 = nms_px * nms_px
    for c in cands:
        n = len(kept)
        if n and (((ku[:n] - c[iu]) ** 2 + (kv[:n] - c[iv]) ** 2) <= r2).any():
            continue
        ku[n], kv[n] = c[iu], c[iv]
        kept.append(c)
    return kept


# --- template storage ---------------------------------------------------------------------------


def save_templates(templates: Sequence[IconTemplate], out: Path, meta: dict[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    index = []
    for t in templates:
        np.savez_compressed(out / f"{t.item_id}.npz", rgb=np.asarray(t.rgb, np.float32),
                            mask=np.asarray(t.mask, bool))  # fmt: skip
        index.append({"item_id": t.item_id, "anchor": list(t.anchor), "ncc_min": t.ncc_min,
                      "rms_max": t.rms_max, "inl_min": t.inl_min, "samples": t.samples,
                      "instances": t.instances, "size": list(t.size),
                      "mask_px": int(np.asarray(t.mask).sum())})  # fmt: skip
    (out / "index.json").write_text(json.dumps({"meta": meta, "templates": index}, indent=1))


def load_templates(src: Path = ICONS_DIR) -> list[IconTemplate]:
    idx = json.loads((src / "index.json").read_text())
    out = []
    for e in idx["templates"]:
        z = np.load(src / f"{e['item_id']}.npz")
        out.append(IconTemplate(int(e["item_id"]), z["rgb"], z["mask"],
                                (float(e["anchor"][0]), float(e["anchor"][1])),
                                float(e["ncc_min"]), float(e["rms_max"]), float(e["inl_min"]),
                                int(e["samples"]), int(e["instances"])))  # fmt: skip
    return out


# --- offline: sessions, floor items, clear samples ------------------------------------------------


@dataclass
class Floor:
    floor_id: int
    item_id: int
    cell: tuple[float, float]  # sub12 fractional cell
    t0: int  # floor_item_appear
    t1: int  # floor_item_vanish (or the session's end)
    kind: str


def floor_items(events: Sequence[dict[str, Any]]) -> list[Floor]:
    import drop_blobs as db

    live: dict[int, Floor] = {}
    out: list[Floor] = []
    end = int(events[-1]["t_mono_ns"]) if events else 0
    for e in events:
        typ = e.get("type")
        if typ == "floor_item_appear":
            d = db.Drop(int(e["floor_id"]), int(e.get("item_id") or -1), int(e["x"]),
                        int(e["y"]), int(e["sub_x"]), int(e["sub_y"]),
                        int(e["t_mono_ns"]))  # fmt: skip
            f = Floor(d.floor_id, d.item_id, db.item_cell(d, "sub12"), d.t, end,
                      str(e.get("kind")))  # fmt: skip
            live[d.floor_id] = f
            out.append(f)
        elif typ == "floor_item_vanish":
            f0 = live.pop(int(e["floor_id"]), None)
            if f0 is not None:
                f0.t1 = int(e["t_mono_ns"])
        elif typ == "map_change":
            for f0 in live.values():
                f0.t1 = min(f0.t1, int(e["t_mono_ns"]))
            live.clear()
    return out


class Mobs:
    """Live monsters (objtype 5) per time: appear .. vanish, positions from drop_blobs.Positions."""

    def __init__(self, events: Sequence[dict[str, Any]], pos: Any) -> None:
        self.pos = pos
        self.spans: list[tuple[int, int, int]] = []
        start: dict[int, int] = {}
        for e in events:
            typ = e.get("type")
            if typ == "entity_appear" and e.get("objtype") == 5:
                start.setdefault(int(e["gid"]), int(e["t_mono_ns"]))
            elif typ == "entity_vanish" and e.get("gid") is not None and int(e["gid"]) in start:
                g = int(e["gid"])
                self.spans.append((start.pop(g), int(e["t_mono_ns"]), g))
        end = int(events[-1]["t_mono_ns"]) if events else 0
        self.spans += [(t0, end, g) for g, t0 in start.items()]

    def near(self, t: int, cell: tuple[float, float], r: float) -> bool:
        for t0, t1, g in self.spans:
            if t0 <= t <= t1 + NS // 2:
                p = self.pos.mob_at(g, t)
                if p is not None and max(abs(p[0] - cell[0]), abs(p[1] - cell[1])) <= r:
                    return True
        return False


class Boxes:
    """The live detector's monster boxes (the session's boxes.jsonl), nearest in time."""

    def __init__(self, path: Path) -> None:
        self.t: list[int] = []
        self.b: list[list[tuple[float, float, float, float]]] = []
        if path.exists():
            for line in path.read_text().splitlines():
                e = json.loads(line)
                self.t.append(int(e["t"]))
                self.b.append([tuple(map(float, x[:4])) for x in e.get("boxes", [])])  # type: ignore[misc]

    def at(self, t: int, tol_s: float = 0.3) -> list[tuple[float, float, float, float]]:
        i = bisect.bisect_left(self.t, t)
        best = None
        for j in (i - 1, i):
            if (
                0 <= j < len(self.t)
                and abs(self.t[j] - t) <= tol_s * NS
                and (best is None or abs(self.t[j] - t) < abs(self.t[best] - t))
            ):
                best = j
        return [] if best is None else self.b[best]


def _in_box(u: float, v: float, b: Sequence[float], m: float) -> bool:
    return b[0] - m <= u <= b[2] + m and b[1] - m <= v <= b[3] + m


def _ui_clear(u: float, v: float, m: float = 30.0) -> bool:
    from route_preview import UI_WINDOWS

    if not (m <= u <= 1280 - m and m <= v <= 720 - m):
        return False
    return not any(_in_box(u, v, b, m) for b in UI_WINDOWS)


@dataclass
class Sample:
    floor_id: int
    item_id: int
    frame: str
    t: int
    uv: tuple[float, float]  # projected ground point
    still: bool
    crop: Any = None  # (2 CROP_HALF + 1)^2 x 3 uint8 around round(uv)


FALL_SETTLE_S = 1.1  # 0.5 s display lag + the falling animation
SIGHT_SETTLE_S = 0.6


def collect(sid: str, every_s: float = 1.0, lag_s: float = 0.5, clear_only: bool = True,
            limit_frames: int | None = None) -> list[Sample]:  # fmt: skip
    """Clear samples of every floor item on frames every ``every_s`` (see the module doc)."""
    import drop_blobs as db

    events = db.load_events(sid)
    frames = db.load_frames(sid)
    pos = db.Positions(events)
    mobs = Mobs(events, pos)
    boxes = Boxes(db.DEMO_ROOT / sid / "boxes.jsonl")
    items = floor_items(events)
    proj = db.Projector()
    out: list[Sample] = []
    last = -10 * NS
    n_read = 0
    for tf, path in frames:
        if tf - last < every_s * NS:
            continue
        ts = tf - int(lag_s * NS)  # the server time this frame shows
        alive = [
            f for f in items
            if f.t0 + int((FALL_SETTLE_S if f.kind == "fall" else SIGHT_SETTLE_S) * NS) - int(
                lag_s * NS) <= ts < f.t1 - int(0.2 * NS)
        ]  # fmt: skip
        if not alive:
            continue
        o = pos.gm_at(ts)
        o0 = pos.gm_at(ts - int(0.6 * NS))
        if o is None or o0 is None:
            continue
        still = math.hypot(o[0] - o0[0], o[1] - o0[1]) < 0.05
        pts = proj.project(o, [f.cell for f in alive])
        bx = boxes.at(tf)
        picked: list[tuple[Floor, tuple[float, float]]] = []
        for i, f in enumerate(alive):
            u, v = float(pts[i][0]), float(pts[i][1])
            if clear_only:
                if not _ui_clear(u, v, CROP_HALF):
                    continue
                if _in_box(u, v, db.GM_BOX, 12):
                    continue
                if any(_in_box(u, v, b, 10) for b in bx):
                    continue
                if mobs.near(ts, f.cell, 1.0):
                    continue
                if any(g is not f and math.hypot(pts[j][0] - u, pts[j][1] - v) <= 22
                       for j, g in enumerate(alive)):  # fmt: skip
                    continue
            picked.append((f, (u, v)))
        if not picked:
            continue
        img = db.read_rgb(path)
        n_read += 1
        last = tf
        for f, (u, v) in picked:
            crop, _, _ = db._crop(img, u, v, CROP_HALF)
            out.append(Sample(f.floor_id, f.item_id, path.name, tf, (u, v), still,
                              np.ascontiguousarray(crop)))  # fmt: skip
        if limit_frames is not None and n_read >= limit_frames:
            break
    print(f"{sid}: {n_read} frames read, {len(out)} samples, "
          f"{len({s.floor_id for s in out})} floor items", flush=True)  # fmt: skip
    return out


# --- offline: alignment, templates ---------------------------------------------------------------


def _window(crop: Any, dy: int, dx: int, half: int) -> Any:
    c0 = crop.shape[0] // 2
    return crop[c0 + dy - half : c0 + dy + half + 1, c0 + dx - half : c0 + dx + half + 1]


def saliency(crop: Any, box: int = 15) -> Any:
    """Max-channel distance of each pixel to its ``box`` x ``box`` mean colour (integral image)."""
    c = np.asarray(crop, np.float64)
    r = box // 2
    p = np.pad(c, ((r + 1, r), (r + 1, r), (0, 0)), mode="edge")
    ii_ = p.cumsum(0).cumsum(1)
    h, w = c.shape[:2]
    s = (
        ii_[box : box + h, box : box + w]
        - ii_[:h, box : box + w]
        - ii_[box : box + h, :w]
        + ii_[:h, :w]
    )
    return np.abs(c - s / (box * box)).max(-1)


def seed_shift(crop: Any, search: int = SEARCH, thr: float = SAL_THR,
               sigma: float = 12.0) -> tuple[int, int] | None:  # fmt: skip
    """The salient blob most likely to be THE item: components of saliency > ``thr`` within
    +-``search`` of the crop centre, 6-250 px, <= 24 px a side, scored by their summed saliency
    x a Gaussian of the distance to the centre; (dy, dx) of its centroid, None without one."""
    import drop_blobs as db

    d = saliency(crop)
    c0 = crop.shape[0] // 2
    m = np.zeros(d.shape, bool)
    m[c0 - search : c0 + search + 1, c0 - search : c0 + search + 1] = True
    m &= d > thr
    best, best_s = None, 0.0
    for ys, xs in db._components(m):
        if not 6 <= len(ys) <= 250 or np.ptp(ys) > 23 or np.ptp(xs) > 23:
            continue
        cy, cx = ys.mean() - c0, xs.mean() - c0
        sc = float(d[ys, xs].sum()) * math.exp(-(cy * cy + cx * cx) / (2 * sigma * sigma))
        if sc > best_s:
            best, best_s = (int(round(cy)), int(round(cx))), sc
    return best


def _refine(tpl: IconTemplate, crops: Any, shifts: Any, step: int) -> tuple[Any, Any]:
    """Each crop's shift re-aligned by masked colour NCC within +-``step`` of its current one."""
    h, w = tpl.size
    c0 = crops.shape[1] // 2
    out = shifts.copy()
    best = np.full(len(crops), -1.0)
    for i, c in enumerate(crops):
        dy, dx = int(shifts[i][0]), int(shifts[i][1])
        y0 = c0 + dy - h // 2 - step
        x0 = c0 + dx - w // 2 - step
        if y0 < 0 or x0 < 0 or y0 + h + 2 * step > c.shape[0] or x0 + w + 2 * step > c.shape[1]:
            continue
        sub = c[y0 : y0 + h + 2 * step, x0 : x0 + w + 2 * step]
        ncc, _ = match_maps(sub, [tpl])[0]
        win = ncc[: 2 * step + 1, : 2 * step + 1]
        iy, ix = np.unravel_index(int(np.argmax(win)), win.shape)
        out[i] = (dy + iy - step, dx + ix - step)
        best[i] = win[iy, ix]
    return out, best


def build_template(samples: Sequence[Sample], iters: int = 4, fg_thr: float = 38.0,
                   fg_share: float = 0.6, keep_share: float = 0.8, mad_max: float = 40.0
                   ) -> IconTemplate | None:  # fmt: skip
    """One item_id's template from its clear samples (see the module doc): seed each crop on its
    most likely salient blob, take the median and the mask, then re-align by masked NCC."""
    seeds = [(s, seed_shift(s.crop)) for s in samples]
    seeds = [(s, sh) for s, sh in seeds if sh is not None]
    if len(seeds) < MIN_SAMPLES:
        return None
    crops = np.stack([s.crop for s, _ in seeds]).astype(np.float32)
    shifts = np.array([sh for _, sh in seeds], int)
    use = np.ones(len(crops), bool)
    tpl: IconTemplate | None = None
    lim = CROP_HALF - HALF
    for it in range(iters + 1):
        shifts = np.clip(shifts, -lim, lim)
        stack = np.stack([_window(crops[i], shifts[i][0], shifts[i][1], HALF)
                          for i in range(len(crops)) if use[i]])  # fmt: skip
        m = _fg_mask(stack, fg_thr, fg_share)
        if m.sum() < 6:
            return None
        yy, xx = np.nonzero(m)
        cy, cx = int(round(yy.mean())) - HALF, int(round(xx.mean())) - HALF
        if (cy or cx) and it < iters:  # keep the item centred in the window
            shifts = shifts + np.array([cy, cx])
            continue
        med = np.median(stack, 0)
        mad = np.median(np.abs(stack - med[None]).max(-1), 0)
        # the item's own pixels agree across crops, the ground (a corpse splat) does not; a
        # translucent sprite (the bottle) fails it inside: then the plain mask is kept
        mc = m & (mad <= mad_max)
        tpl = _tight(med, mc if mc.sum() >= MAD_KEEP * m.sum() else m, samples[0].item_id)
        if it == iters:
            break
        shifts, best = _refine(tpl, crops, shifts, REFINE)
        use = best >= np.quantile(best, 1.0 - keep_share)
    assert tpl is not None
    # sprite centre (the tight box's centre) - projected ground point
    sh = np.median(shifts[use], 0)
    tpl.anchor = (float(sh[1] + tpl._off[1]), float(sh[0] + tpl._off[0]))  # type: ignore[attr-defined]
    tpl.samples = int(use.sum())
    tpl.instances = len({s.floor_id for (s, _), u in zip(seeds, use, strict=True) if u})
    return tpl


def _tight(med: Any, m: Any, item_id: int) -> IconTemplate:
    yy, xx = np.nonzero(m)
    ya, yb, xa, xb = yy.min(), yy.max() + 1, xx.min(), xx.max() + 1
    t = IconTemplate(item_id, med[ya:yb, xa:xb].astype(np.float32), m[ya:yb, xa:xb].copy())
    t._off = ((ya + yb - 1) / 2.0 - HALF, (xa + xb - 1) / 2.0 - HALF)  # type: ignore[attr-defined]
    return t


def _fg_mask(stack: Any, fg_thr: float, fg_share: float) -> Any:
    """Pixels that differ (max channel) from their crop's own ground -- the median colour of the
    crop's 3-px border ring -- by more than ``fg_thr`` in at least ``fg_share`` of the crops."""
    n, h, w, _ = stack.shape
    ring = np.zeros((h, w), bool)
    ring[:3], ring[-3:], ring[:, :3], ring[:, -3:] = True, True, True, True
    g = np.median(stack[:, ring], 1)  # N x 3
    d = np.abs(stack - g[:, None, None, :]).max(-1)
    share = (d > fg_thr).mean(0)
    m = share >= fg_share
    m &= ~ring
    return _largest_component(m)


def _largest_component(m: Any) -> Any:
    import drop_blobs as db

    comps = db._components(m)
    if not comps:
        return m
    big = max(comps, key=lambda c: len(c[0]))
    out = np.zeros_like(m)
    # keep every component of >= 1/4 of the largest's size (an item may have 2 coloured parts)
    for ys, xs in comps:
        if len(ys) * 4 >= len(big[0]):
            out[ys, xs] = True
    return out


def thin_samples(samples: Sequence[Sample], per_instance: int = PER_INSTANCE) -> list[Sample]:
    """At most ``per_instance`` samples per floor item, spread evenly in time."""
    by: dict[int, list[Sample]] = {}
    for s in samples:
        by.setdefault(s.floor_id, []).append(s)
    out = []
    for ss in by.values():
        ss.sort(key=lambda s: s.t)
        if len(ss) > per_instance:
            idx = np.linspace(0, len(ss) - 1, per_instance).round().astype(int)
            ss = [ss[i] for i in sorted(set(idx.tolist()))]
        out += ss
    return out


# --- offline: evaluation on kills ----------------------------------------------------------------


@dataclass
class KillCase:
    sid: str
    gid: int
    t: int
    delay: float
    frame: str
    centre: tuple[float, float]  # the dead monster's last cell, projected (the search centre)
    drops: list[tuple[float, float, int]]  # this kill's drops still on the floor: truth, item_id
    present: list[tuple[float, float, int]]  # every floor item alive on the frame (truth)
    gm_moved: float  # cells the GM moved in the 0.6 s before the frame (server time)
    hits: list[tuple[float, float, int, float, float, float]]  # find_items' details, no NMS
    ms: float = 0.0  # the matcher's time on this case


def eval_session(sid: str, templates: Sequence[IconTemplate], delays: Sequence[float],
                 radius_px: int = 100, lag_s: float = 0.5, floor_ncc: float = 0.3,
                 ceil_rms: float = 90.0) -> list[KillCase]:  # fmt: skip
    """Per kill and delay: the matcher's candidates on the first frame ``delay`` s after the
    death, searched around the dead monster's projected last cell (drop_blobs' kills)."""
    import drop_blobs as db

    events = db.load_events(sid)
    frames = db.load_frames(sid)
    pos = db.Positions(events)
    kills = db.kills_with_drops(events, pos)
    items = floor_items(events)
    proj = db.Projector()
    anchors = {t.item_id: t.anchor for t in templates}
    a0 = (float(np.median([a[0] for a in anchors.values()])),
          float(np.median([a[1] for a in anchors.values()])))  # fmt: skip
    out: list[KillCase] = []
    for k in kills:
        if k.cell is None:
            continue
        for delay in delays:
            fa = db.frame_at(frames, k.t + int(delay * NS))
            if fa is None:
                continue
            ts = fa[0] - int(lag_s * NS)
            o = pos.gm_at(ts)
            o0 = pos.gm_at(ts - int(0.6 * NS))
            if o is None or o0 is None:
                continue
            c = proj.project(o, [k.cell])[0]
            centre = (float(c[0]) + a0[0], float(c[1]) + a0[1])

            def truth(fs: Sequence[Any], o: Any = o) -> list[tuple[float, float, int]]:
                if not fs:
                    return []
                pts = proj.project(o, [f.cell for f in fs])
                res = []
                for f, p in zip(fs, pts, strict=True):
                    an = anchors.get(f.item_id, a0)
                    res.append((float(p[0]) + an[0], float(p[1]) + an[1], f.item_id))
                return res

            mine = {(d.floor_id, d.t) for d in k.drops}
            drops = truth([f for f in items if (f.floor_id, f.t0) in mine and ts <= f.t1])
            present = truth([f for f in items if f.t0 <= ts <= f.t1 + NS // 2])
            img = db.read_rgb(fa[1])
            t0 = time.perf_counter()
            hits = find_items(img, centre, radius_px, templates, nms_px=0, ncc_min=floor_ncc,
                              rms_max=ceil_rms, inl_min=0.0, details=True)  # fmt: skip
            ms = (time.perf_counter() - t0) * 1e3
            out.append(
                KillCase(
                    sid,
                    k.gid,
                    k.t,
                    delay,
                    fa[1].name,
                    centre,
                    drops,
                    present,
                    math.hypot(o[0] - o0[0], o[1] - o0[1]),
                    [tuple(h) for h in hits],
                    ms,
                )
            )  # type: ignore[misc]
    return out


def select(hits: Sequence[Sequence[Any]], templates: Sequence[IconTemplate] | None = None,
           ncc_min: float | None = None, rms_max: float | None = None,
           inl_min: float | None = None, nms_px: float = 10.0
           ) -> list[tuple[float, float, int, float]]:  # fmt: skip
    """The thresholds + NMS of ``find_items`` applied to its ``details`` candidates taken with
    loose thresholds and no NMS: (u, v, id, ncc, rms, inl) -> (u, v, id, inl)."""
    th = {t.item_id: t for t in templates or ()}
    ok = []
    for u, v, iid, ncc, rms, inl in hits:
        t = th.get(iid)
        nmin = ncc_min if ncc_min is not None else (t.ncc_min if t else OFF)
        rmax = rms_max if rms_max is not None else (t.rms_max if t else 0.0)
        imin = inl_min if inl_min is not None else (t.inl_min if t else 1.0)
        if ncc >= nmin and rms <= rmax and inl >= imin:
            ok.append((u, v, iid, inl, ncc))
    ok.sort(key=lambda h: (-h[3], -h[4]))
    return [h[:4] for h in _nms(ok, nms_px, 0, 1)]


def score(cases: Sequence[KillCase], sel: Any, r: float = 15.0) -> dict[str, Any]:
    """recall@r over this kill's drops (any id / the right id), false detections per kill (no
    floor item at all within r), overall, at the GM's feet (truth within FEET_PX of GM_CENTRE)
    and with the GM still."""
    n = hit = hit_id = 0
    nf = hf = 0
    ns = hs = 0
    false = 0
    for c in cases:
        dets = sel(c)
        for u, v, iid in c.drops:
            dd = [(math.hypot(d[0] - u, d[1] - v), d[2]) for d in dets]
            ok = any(x <= r for x, _ in dd)
            ok_id = any(x <= r and i == iid for x, i in dd)
            n += 1
            hit += ok
            hit_id += ok_id
            if math.hypot(u - GM_CENTRE[0], v - GM_CENTRE[1]) <= FEET_PX:
                nf += 1
                hf += ok
            if c.gm_moved < 0.05:
                ns += 1
                hs += ok
        for d in dets:
            if all(math.hypot(d[0] - p[0], d[1] - p[1]) > r for p in c.present):
                false += 1
    return {"kills": len(cases), "drops": n, "recall": round(hit / max(1, n), 3),
            "recall_id": round(hit_id / max(1, n), 3), "false_per_kill":
            round(false / max(1, len(cases)), 2), "feet_n": nf,
            "recall_feet": round(hf / max(1, nf), 3), "still_n": ns,
            "recall_still": round(hs / max(1, ns), 3)}  # fmt: skip


# --- CLI ------------------------------------------------------------------------------------------


def _samples(sid: str, every_s: float, refresh: bool) -> list[Sample]:
    """``collect`` cached in RAM scratch (/dev/shm): the NAS is read once per session."""
    import pickle

    SCRATCH.mkdir(parents=True, exist_ok=True)
    p = SCRATCH / f"samples-{sid}-{every_s}.pkl"
    if p.exists() and not refresh:
        with p.open("rb") as fh:
            return pickle.load(fh)  # type: ignore[no-any-return]
    ss = collect(sid, every_s=every_s)
    with p.open("wb") as fh:
        pickle.dump(ss, fh)
    return ss


def tune(templates: Sequence[IconTemplate], cases: Sequence[KillCase], r: float = 15.0,
         ncc_grid: Sequence[float] = (0.3, 0.5, 0.6, 0.7, 0.8),
         rms_grid: Sequence[float] = (35, 45, 60, 90),
         inl_grid: Sequence[float] = (0.4, 0.5, 0.6, 0.7, 0.8, 0.9),
         false_cost: float = 2.0) -> None:  # fmt: skip
    """Per template, the (ncc_min, rms_max, inl_min) maximising its true detections -
    ``false_cost`` x its false ones on ``cases`` (training kills): a detection is true when a
    floor item of the same id lies within ``r``, false when no floor item at all does. A template
    that cannot beat 0 is switched off (ncc_min = OFF)."""
    for t in templates:
        per = [[h for h in c.hits if h[2] == t.item_id] for c in cases]
        best, best_v = (OFF, t.rms_max, t.inl_min), 0.0
        for nmin in ncc_grid:
            for rmax in rms_grid:
                for imin in inl_grid:
                    tp = fp = 0
                    for c, hs in zip(cases, per, strict=True):
                        sel = [(h[0], h[1], h[2], h[5], h[3]) for h in hs
                               if h[3] >= nmin and h[4] <= rmax and h[5] >= imin]  # fmt: skip
                        sel.sort(key=lambda h: (-h[3], -h[4]))
                        for d in _nms(sel, 10.0, 0, 1):
                            near = [p for p in c.present
                                    if math.hypot(d[0] - p[0], d[1] - p[1]) <= r]  # fmt: skip
                            if any(p[2] == t.item_id for p in near):
                                tp += 1
                            elif not near:
                                fp += 1
                    v = tp - false_cost * fp
                    if v > best_v:
                        best, best_v = (nmin, rmax, imin), v
        t.ncc_min, t.rms_max, t.inl_min = (float(x) for x in best)
        print(f"  tune {t.item_id}: ncc >= {t.ncc_min}, rms <= {t.rms_max}, inliers >= "
              f"{t.inl_min} (value {best_v:.1f})", flush=True)  # fmt: skip


def cmd_build(a: argparse.Namespace) -> int:
    ss: list[Sample] = []
    for sid in a.sids:
        ss += _samples(sid, a.every, a.refresh)
    ss = thin_samples(ss, a.per_instance)
    by: dict[int, list[Sample]] = {}
    for s in ss:
        by.setdefault(s.item_id, []).append(s)
    tpls = []
    for iid, g in sorted(by.items(), key=lambda x: -len(x[1])):
        t = build_template(g)
        print(f"{iid}: {len(g)} samples -> " + ("none" if t is None else
              f"{t.size} mask {int(t.mask.sum())} px, anchor {t.anchor}, "
              f"used {t.samples} / {t.instances} floor items"), flush=True)  # fmt: skip
        if t is not None:
            tpls.append(t)
    if a.tune:
        cases: list[KillCase] = []
        for sid in a.tune:
            cases += [c for c in eval_session(sid, tpls, [a.delay]) if c.delay == a.delay]
        tune(tpls, cases)
    save_templates(tpls, Path(a.out), {"sessions": a.sids, "tuned_on": a.tune,
                                       "every_s": a.every, "per_instance": a.per_instance,
                                       "built": time.strftime("%Y-%m-%dT%H:%M:%S%z")})  # fmt: skip
    print(Path(a.out))
    return 0


def cmd_eval(a: argparse.Namespace) -> int:
    tpls = load_templates(Path(a.icons))
    delays = [float(x) for x in a.delays.split(",")]
    report: dict[str, Any] = {}
    allc: list[KillCase] = []
    for sid in a.sids:
        cs = eval_session(sid, tpls, delays, radius_px=a.radius)
        allc += cs
        for d in delays:
            sc = [c for c in cs if c.delay == d]
            row = {f"R{r}": score(sc, lambda c: select(c.hits, tpls), r) for r in (15, 25)}
            report[f"{sid}@{d}"] = row
            print(sid, d, json.dumps(row), flush=True)
    if a.json:
        Path(a.json).write_text(json.dumps({"report": report,
                                            "cases": [c.__dict__ for c in allc]}))  # fmt: skip
    return 0


def cmd_bench(a: argparse.Namespace) -> int:
    tpls = load_templates(Path(a.icons))
    rng = np.random.default_rng(0)
    img = rng.integers(0, 255, (720, 1280, 3), dtype=np.uint8)
    if a.frame:
        import drop_blobs as db

        img = db.read_rgb(Path(a.frame))
    find_items(img, (640.0, 340.0), 100, tpls)
    ts = []
    for _ in range(a.n):
        t0 = time.perf_counter()
        find_items(img, (640.0, 340.0), 100, tpls)
        ts.append((time.perf_counter() - t0) * 1e3)
    on = sum(1 for t in tpls if t.ncc_min <= 1.0)
    print(f"{on} of {len(tpls)} templates on, 200 x 200 region: {np.median(ts):.1f} ms median, "
          f"{np.percentile(ts, 90):.1f} p90 over {a.n}")  # fmt: skip
    return 0


def cmd_sheet(a: argparse.Namespace) -> int:
    from PIL import Image

    tpls = load_templates(Path(a.icons))
    cell = 24
    sheet = np.zeros((cell * len(tpls), cell * 2, 3), np.uint8)
    for i, t in enumerate(tpls):
        h, w = t.size
        sheet[i * cell : i * cell + h, :w] = np.asarray(t.rgb).clip(0, 255).astype(np.uint8)
        m = np.where(np.asarray(t.mask)[..., None], t.rgb, 0)
        sheet[i * cell : i * cell + h, cell : cell + w] = m.clip(0, 255).astype(np.uint8)
    Image.fromarray(sheet).resize((sheet.shape[1] * 6, sheet.shape[0] * 6),
                                  Image.Resampling.NEAREST).save(a.out)  # fmt: skip
    print(a.out, [t.item_id for t in tpls])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("sids", nargs="+")
    b.add_argument("--out", default=str(ICONS_DIR))
    b.add_argument("--every", type=float, default=0.4, help="frame sampling (s)")
    b.add_argument("--per-instance", type=int, default=PER_INSTANCE)
    b.add_argument("--tune", nargs="*", default=[], help="sessions to tune the thresholds on")
    b.add_argument("--delay", type=float, default=1.5)
    b.add_argument("--refresh", action="store_true", help="re-read the NAS (ignore the cache)")
    e = sub.add_parser("eval")
    e.add_argument("sids", nargs="+")
    e.add_argument("--icons", default=str(ICONS_DIR))
    e.add_argument("--delays", default="1.0,1.5,2.5")
    e.add_argument("--radius", type=int, default=100)
    e.add_argument("--json", default="")
    s = sub.add_parser("sheet")
    s.add_argument("--icons", default=str(ICONS_DIR))
    s.add_argument("--out", default=str(SCRATCH / "templates.png"))
    n = sub.add_parser("bench")
    n.add_argument("--icons", default=str(ICONS_DIR))
    n.add_argument("--frame", default="")
    n.add_argument("--n", type=int, default=50)
    a = ap.parse_args()
    return {"build": cmd_build, "eval": cmd_eval, "sheet": cmd_sheet, "bench": cmd_bench}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
