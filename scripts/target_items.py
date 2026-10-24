#!/usr/bin/env python3
"""TARGET floor items from pixels: Batt's four (757, 756, 604, 518), staged on pay_fild07 and
learnt by masked colour template matching (docs/planning/target-items.md, PRE-REGISTERED; Batt
2026-10-24 ~16:0x: "try training the target drop items ... for pickup accuracy").

    target_items.py index SID                      the frame index of a recording (timestamps only)
    target_items.py inventory                      packet labels per split (counts; no pixel)
    target_items.py fit                            FIT: templates, anchors, the detector threshold
    target_items.py freeze                         params.json + templates.npz sha256
    target_items.py scan --set test|neg|pilot      frozen detector on TEST / negatives / pilot
    target_items.py score                          the pre-registered bars

Packets are OFFLINE ground truth only (ADR-0007): they label where each floor item lies; the
DETECTOR reads pixels only (the frame, the hunt layout's fixed UI rectangles and our own sprite's
fixed screen box at the camera target). Nothing here is an input of a live decision.

Everything client-derived (frames, crops, templates, candidates, labels) goes to
/dev/shm/poring-lab-tmp/target-items/ only, never the repo. Item NAMES are never written: ids.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import math
import os
import sys
import tarfile
import time
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
DATASETS = Path("/mnt/poring-lab-datasets")
OUT = Path("/dev/shm/poring-lab-tmp/target-items")
NS = 10**9

# --- the data (fixed by the pre-registration) ----------------------------------------------------
MAP = "pay_fild07"
STAGED = "20261024T170356-rdp-stage-items-b"
STAGE_EVENTS = Path(
    "/dev/shm/poring-lab-demo/20261024T170401-stage-items-pay_fild07-b/events.jsonl"
)
NEGATIVES = ("20261024T123622-rdp-thief-t1b", "20261024T131838-rdp-thief-t2")
PILOT = "20261024T164555-rdp-thief-s-pilot"
TARGETS = (757, 756, 604, 518)
FIT_SPOTS = tuple(range(0, 8))
TEST_SPOTS = tuple(range(8, 12))

# --- the label rule (target-items.md section 3) --------------------------------------------------
D_APPEAR_S = 2.2  # item-class.md 8a, frozen 2026-10-23 (the client's display rule)
D_GONE_S = 0.6
# the sub-cell table measured in item-class.md 8a (cells; keyed by the packet's sub value)
OX = {3: -0.189, 6: 0.0, 9: 0.185, 12: 0.376}
OY = {3: -0.210, 6: 0.0, 9: 0.173, 12: 0.329}
STILL_LEAD_S = 0.5  # a still window's frames: [still + 0.5 s, the next map change), <= 8 s
STILL_MAX_S = 8.0
STILL_S = 0.8  # our position unchanged at every 0.1-s step of [t_f - 0.8 s, t_f] (item_labels)
STEP_S = 0.1
ITEM_BOX = 28.0  # px, square, centred on the predicted sprite centre (exclusion geometry)
SAMPLE_BOX = 36.0  # the same before the anchors exist (FIT sampling: centred on the ground point)
UNIT_HALF_W, UNIT_UP, UNIT_DOWN = 30.0, 100.0, 6.0  # a unit's generic box around its anchor
UNIT_LAG_S = 1.0  # unit boxes over [t_f - 1.0 s, t_f] (frames lag the server ~0.5 s)
SELF_PAD = 4.0
STACK_IOU = 0.5
GAME = (1280, 720)

# --- templates (FIT) ------------------------------------------------------------------------------
CROP_HALF = 44
HALF = 14
SEED = (2, -5)  # (dy, dx) px: the first guess of sprite centre - ground point (item-class anchors)
REFINE = 6
ITERS = 4
KEEP_SHARE = 0.8
MIN_SAMPLES = 12
TPL_MIN_AGE_S = 2.5
TPL_BEFORE_VANISH_S = 1.0
ITEM_GAP_PX = 24.0
REGION_MARGIN_PX = 44.0
UI_MARGIN_PX = 30.0
ALIGN_STOP_PX = 3.0  # FIT: median |offset| of the best match vs the prediction above it -> STOP

# --- the detector -------------------------------------------------------------------------------
CAND_NCC = 0.45
LOCAL_R = 2
NMS_PX = 10.0
INLIER_PX = 32  # item_icons.INLIER_PX
GRID_NCC = tuple(round(0.45 + 0.01 * i, 2) for i in range(54))  # 0.45 .. 0.98
GRID_RMS = (*range(15, 85, 5), math.inf)
GRID_INL = tuple(round(0.1 * i, 1) for i in range(10))  # 0.0 .. 0.9
FIT_FALSE_MAX = 0.5  # false detections per 100 FIT negative frames
MATCH_PX = 6.0  # Chebyshev
PILOT_GUARD_S = 60.0
MAP_SETTLE_S = 5.0

# --- the bars (target-items.md section 5) ---------------------------------------------------
RECALL_MIN = 0.80
FALSE_MAX = 1.0  # per 100 negative frames
PRECISION_MIN = 0.90
N_MIN = 20

Rect = tuple[float, float, float, float]


# --- the staging events (PURE) -------------------------------------------------------------------


@dataclass(frozen=True)
class Window:
    spot: int
    at: tuple[int, int]
    t0: int  # first frame time admitted
    t1: int  # end (exclusive)


def still_windows(events: Sequence[Mapping[str, Any]], changes: Sequence[int]) -> list[Window]:
    """PURE: the still windows of the staging tool's events.jsonl: [still + STILL_LEAD_S, the
    first map change after the still event), at most STILL_MAX_S after it (``changes``: the
    packets' map_change times; the next @warp ends the view)."""
    ch = sorted(int(c) for c in changes)
    out = []
    for e in events:
        if e.get("kind") == "still":
            t = int(e["t_ns"])
            nxt = [c for c in ch if c > t]
            end = min(nxt[0] if nxt else t + int(STILL_MAX_S * NS), t + int(STILL_MAX_S * NS))
            out.append(
                Window(
                    int(e["spot"]),
                    (int(e["at"][0]), int(e["at"][1])),
                    t + int(STILL_LEAD_S * NS),
                    end,
                )
            )
    return out


def window_of(windows: Sequence[Window], t_f: int) -> Window | None:
    for w in windows:
        if w.t0 <= t_f < w.t1:
            return w
    return None


def split_of_spot(spot: int) -> str:
    if spot in FIT_SPOTS:
        return "fit"
    if spot in TEST_SPOTS:
        return "test"
    raise ValueError(f"spot {spot} is in no split")


# --- boxes (PURE) --------------------------------------------------------------------------------


def square(c: tuple[float, float], side: float) -> Rect:
    h = side / 2.0
    return (c[0] - h, c[1] - h, c[0] + h, c[1] + h)


def area(b: Rect) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def inter(a: Rect, b: Rect) -> float:
    return area((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])))


def iou(a: Rect, b: Rect) -> float:
    i = inter(a, b)
    u = area(a) + area(b) - i
    return i / u if u > 0 else 0.0


def unit_box(u: float, v: float) -> Rect:
    return (u - UNIT_HALF_W, v - UNIT_UP, u + UNIT_HALF_W, v + UNIT_DOWN)


def view_status(box: Rect, rects: Sequence[Rect], size: tuple[int, int] = GAME) -> str:
    """'clear', 'hidden' (wholly under a UI window / off the region: not drawn), 'ui_partial' or
    'edge_partial' (item_labels.ui_status's rule)."""
    a = area(box)
    region = (0.0, 0.0, float(size[0]), float(size[1]))
    inside = inter(box, region)
    if inside <= 0:
        return "hidden"
    if inside < a - 1e-9:
        return "edge_partial"
    for r in rects:
        s = inter(box, r)
        if s >= a - 1e-9:
            return "hidden"
        if s > 0:
            return "ui_partial"
    return "clear"


@dataclass
class ItemView:
    floor_id: int
    item_id: int
    phase: str  # on | settling | vanishing
    ground: tuple[float, float]
    centre: tuple[float, float]
    box: Rect
    excl: list[str] = field(default_factory=list)

    @property
    def labelled(self) -> bool:
        """Labelled AND fully in view: in the recall denominator."""
        return self.phase == "on" and not self.excl


def exclusions(
    views: list[ItemView],
    self_box: Rect | None,
    unit_boxes: Sequence[Rect],
    rects: Sequence[Rect],
) -> list[ItemView]:
    """PURE: each item's exclusions (an excluded item stays PRESENT: a detection on it is not
    false). 'hidden' items are dropped (not drawn)."""
    out = []
    for iv in views:
        st = view_status(iv.box, rects)
        if st == "hidden":
            continue
        if st != "clear":
            iv.excl.append(st)
        if self_box is not None and inter(iv.box, self_box) > 0:
            iv.excl.append("under_self")
        if any(inter(iv.box, ub) > 0 for ub in unit_boxes):
            iv.excl.append("under_unit")
        out.append(iv)
    for i in range(len(out)):
        for j in range(i + 1, len(out)):
            if iou(out[i].box, out[j].box) >= STACK_IOU:
                for k in (i, j):
                    if "stacked" not in out[k].excl:
                        out[k].excl.append("stacked")
    return out


# --- detection maths (PURE) ----------------------------------------------------------------------


def local_maxima(s: Any, r: int = LOCAL_R) -> Any:
    """True where ``s`` is the maximum of its (2 r + 1)^2 neighbourhood (item_icons._local_max)."""
    import item_icons

    return item_icons._local_max(s, r)


def nms(xy: Any, score: Any, r: float = NMS_PX) -> Any:
    """Greedy NMS (best score first, Euclidean ``r``): the kept indices."""
    order = np.argsort(-np.asarray(score), kind="stable")
    kept: list[int] = []
    for i in order:
        if all(math.hypot(xy[i][0] - xy[k][0], xy[i][1] - xy[k][1]) > r for k in kept):
            kept.append(int(i))
    return np.asarray(kept, int)


def inside_any(u: Any, v: Any, rects: Sequence[Rect]) -> Any:
    m = np.zeros(np.shape(u), bool)
    for r in rects:
        m |= (u >= r[0]) & (u <= r[2]) & (v >= r[1]) & (v <= r[3])
    return m


def near(a: Any, b: Any, r: float = MATCH_PX) -> Any:
    """PURE: len(a) x len(b) bool, Chebyshev distance <= r (a, b: n x 2)."""
    a = np.asarray(a, float).reshape(-1, 2)
    b = np.asarray(b, float).reshape(-1, 2)
    if not len(a) or not len(b):
        return np.zeros((len(a), len(b)), bool)
    d = np.abs(a[:, None, :] - b[None, :, :]).max(-1)
    return d <= r


def passes(c: Any, tn: float, tr: float, ti: float) -> Any:
    """Candidates (n x 5: u, v, ncc, rms, inl) passing a threshold triple."""
    c = np.asarray(c, float).reshape(-1, 5)
    return (c[:, 2] >= tn) & (c[:, 3] <= tr) & (c[:, 4] >= ti)


def grid_stats(
    pos: Sequence[Any], neg: Any, n_neg_frames: int
) -> dict[tuple[float, float], dict[str, Any]]:
    """PURE: per (rms, inl) pair of the grid, recall (over ``pos``: per label, the n x 3 array of
    nearby candidates' ncc, rms, inl) and false detections per 100 frames (``neg``: m x 3 of the
    false candidates) for every ncc of GRID_NCC."""
    neg = np.asarray(neg, float).reshape(-1, 3)
    tn = np.asarray(GRID_NCC)
    out = {}
    for tr in GRID_RMS:
        for ti in GRID_INL:
            sel = neg[(neg[:, 1] <= tr) & (neg[:, 2] >= ti), 0]
            sel.sort()
            fp = len(sel) - np.searchsorted(sel, tn - 1e-12, side="left")
            best = np.full(len(pos), -np.inf)
            for j, p in enumerate(pos):
                p = np.asarray(p, float).reshape(-1, 3)
                ok = p[(p[:, 1] <= tr) & (p[:, 2] >= ti), 0]
                if len(ok):
                    best[j] = ok.max()
            rec = (best[None, :] >= tn[:, None] - 1e-12).mean(1) if len(pos) else tn * 0
            out[(float(tr), float(ti))] = {
                "recall": rec,
                "fp100": 100.0 * fp / max(1, n_neg_frames),
                "fp": fp,
            }
    return out


def choose(stats: Mapping[tuple[float, float], Mapping[str, Any]], fmax: float) -> dict[str, Any]:
    """PURE: the threshold triple with the highest recall among those with fp100 <= ``fmax``;
    ties: fewer false, then the higher ncc, the lower rms, the higher inlier share."""
    best: tuple[Any, ...] | None = None
    for (tr, ti), s in stats.items():
        for k, tn in enumerate(GRID_NCC):
            if s["fp100"][k] > fmax + 1e-12:
                continue
            key = (float(s["recall"][k]), -float(s["fp100"][k]), tn, -tr, ti)
            if best is None or key > best[0]:
                best = (key, tn, tr, ti, float(s["recall"][k]), float(s["fp100"][k]))
    if best is None:
        return {"ncc": None}
    return {
        "ncc": best[1],
        "rms": best[2],
        "inl": best[3],
        "fit_recall": round(best[4], 4),
        "fit_fp100": round(best[5], 4),
    }


# --- templates (PURE on arrays) ------------------------------------------------------------------


@dataclass
class Tpl:
    item_id: int
    rgb: Any  # h x w x 3 float32 RGB
    mask: Any  # h x w bool
    anchor: tuple[float, float]  # (du, dv): sprite centre - projected ground point, px
    samples: int = 0
    instances: int = 0

    @property
    def size(self) -> tuple[int, int]:
        return int(self.rgb.shape[0]), int(self.rgb.shape[1])

    def as_icon(self) -> Any:
        import item_icons

        return item_icons.IconTemplate(self.item_id, self.rgb, self.mask)


def _win(crop: Any, sy: int, sx: int, half: int) -> Any:
    c0 = crop.shape[0] // 2
    return crop[c0 + sy - half : c0 + sy + half + 1, c0 + sx - half : c0 + sx + half + 1]


def build_seeded(
    crops: Any,
    item_id: int,
    instances: Sequence[int],
    seed: tuple[int, int] = SEED,
    half: int = HALF,
    iters: int = ITERS,
    refine: int = REFINE,
    keep_share: float = KEEP_SHARE,
    fg_thr: float = 38.0,
    fg_share: float = 0.6,
    mad_max: float = 40.0,
) -> Tpl | None:
    """One item's template from crops centred on its PROJECTED ground point (N x S x S x 3, S =
    2 CROP_HALF + 1). Each crop's shift (dy, dx) = its sprite centre relative to the crop centre,
    starting at ``seed`` for all. A round: the windows at the shifts, item_icons' foreground mask
    (pixels off their crop's ground in >= 60 % of the crops, the largest components), the windows
    re-centred on the mask's centroid, the median, the consistency mask; then each crop
    re-aligned by masked NCC within +-``refine`` and the best ``keep_share`` kept. The anchor =
    the median shift of the kept crops (sprite centre = the mask's tight box centre)."""
    import item_icons as ii

    crops = np.asarray(crops, np.float32)
    n = len(crops)
    if n < MIN_SAMPLES:
        return None
    lim = crops.shape[1] // 2 - half - refine
    sh = np.tile(np.asarray(seed, int), (n, 1))
    use = np.ones(n, bool)
    tpl: Tpl | None = None
    off = (0.0, 0.0)
    for it in range(iters + 1):
        for _ in range(3):  # re-centre on the mask
            sh = np.clip(sh, -lim, lim)
            stack = np.stack([_win(crops[i], sh[i][0], sh[i][1], half) for i in np.nonzero(use)[0]])
            m = ii._fg_mask(stack, fg_thr, fg_share)
            if m.sum() < 6:
                return None
            yy, xx = np.nonzero(m)
            cy, cx = int(round(yy.mean())) - half, int(round(xx.mean())) - half
            if not (cy or cx):
                break
            sh = sh + np.array([cy, cx])
        med = np.median(stack, 0)
        mad = np.median(np.abs(stack - med[None]).max(-1), 0)
        mc = m & (mad <= mad_max)
        mm = mc if mc.sum() >= 0.5 * m.sum() else m
        yy, xx = np.nonzero(mm)
        ya, yb, xa, xb = int(yy.min()), int(yy.max()) + 1, int(xx.min()), int(xx.max()) + 1
        off = ((ya + yb - 1) / 2.0 - half, (xa + xb - 1) / 2.0 - half)  # tight centre - window's
        tpl = Tpl(item_id, med[ya:yb, xa:xb].astype(np.float32), mm[ya:yb, xa:xb].copy(), (0, 0))
        if it == iters:
            break
        icon = tpl.as_icon()
        h, w = tpl.size
        c0 = crops.shape[1] // 2
        best = np.full(n, -1.0)
        for i in range(n):
            # the tight template's top-left at the current shift (+ the tight offset)
            ty = c0 + sh[i][0] + int(round(off[0] - (h - 1) / 2)) - refine
            tx = c0 + sh[i][1] + int(round(off[1] - (w - 1) / 2)) - refine
            if ty < 0 or tx < 0 or ty + h + 2 * refine > crops.shape[1]:
                continue
            if tx + w + 2 * refine > crops.shape[2]:
                continue
            sub = crops[i, ty : ty + h + 2 * refine, tx : tx + w + 2 * refine]
            ncc = ii.match_maps(sub, [icon])[0][0][: 2 * refine + 1, : 2 * refine + 1]
            ncc = np.where(np.isfinite(ncc), ncc, -1.0)
            iy, ix = np.unravel_index(int(np.argmax(ncc)), ncc.shape)
            sh[i] = (sh[i][0] + iy - refine, sh[i][1] + ix - refine)
            best[i] = ncc[iy, ix]
        use = best >= np.quantile(best, 1.0 - keep_share)
    assert tpl is not None
    s = np.median(sh[use], 0)
    tpl.anchor = (round(float(s[1] + off[1]), 3), round(float(s[0] + off[0]), 3))
    tpl.samples = int(use.sum())
    tpl.instances = len({int(instances[i]) for i in np.nonzero(use)[0]})
    return tpl


def scan(
    img: Any, tpls: Sequence[Tpl], drop: Sequence[Rect], cand_ncc: float = CAND_NCC
) -> dict[int, Any]:
    """PURE (pixels only): per template, its candidates over the whole image as an n x 5 float32
    array (u, v = the sprite centre, masked colour NCC, masked RMS colour distance, inlier
    share): local maxima (+-LOCAL_R) of the NCC with NCC >= ``cand_ncc``, centres outside every
    ``drop`` rectangle (the UI windows, our own sprite), greedy NMS within NMS_PX by NCC."""
    import item_icons as ii

    a = np.asarray(img)[..., :3]
    icons = [t.as_icon() for t in tpls]
    maps = ii.match_maps(a, icons)
    rf = a.astype(np.int16)
    out: dict[int, Any] = {}
    for t, (ncc, rms) in zip(tpls, maps, strict=True):
        h, w = t.size
        ok = np.isfinite(ncc) & (ncc >= cand_ncc)
        if not ok.any():
            out[t.item_id] = np.zeros((0, 5), np.float32)
            continue
        ys, xs = np.nonzero(ok & local_maxima(np.where(np.isfinite(ncc), ncc, -np.inf)))
        u = xs + (w - 1) / 2.0
        v = ys + (h - 1) / 2.0
        keep = ~inside_any(u, v, drop)
        ys, xs, u, v = ys[keep], xs[keep], u[keep], v[keep]
        sc = ncc[ys, xs]
        k = nms(np.stack([u, v], 1), sc) if len(ys) else np.zeros(0, int)
        ys, xs, u, v, sc = ys[k], xs[k], u[k], v[k], sc[k]
        my, mx = np.nonzero(np.asarray(t.mask, bool))
        tp = np.asarray(t.rgb, np.float32)[my, mx].round().astype(np.int16)
        inl = np.zeros(len(ys), np.float32)
        for s0 in range(0, len(ys), 2048):
            yb, xb = ys[s0 : s0 + 2048], xs[s0 : s0 + 2048]
            patch = rf[yb[:, None] + my[None, :], xb[:, None] + mx[None, :]]
            inl[s0 : s0 + 2048] = (np.abs(patch - tp[None]).max(-1) <= INLIER_PX).mean(1)
        out[t.item_id] = np.stack([u, v, sc, rms[ys, xs], inl], 1).astype(np.float32)
    return out


# --- recordings: the frame index, frames, packets ------------------------------------------------


def index_path(sid: str) -> Path:
    return OUT / "index" / f"{sid}.json"


def build_index(sid: str) -> list[dict[str, Any]]:
    """(frame_id, t_mono_ns, shard, png offset, png size) per frame, from the tar headers and the
    per-frame JSON only (no pixel read)."""
    d = DATASETS / sid
    man = json.loads((d / "manifest.json").read_text())
    rows: dict[str, dict[str, Any]] = {}
    for shard in man["shards"]:
        with tarfile.open(d / shard) as tar:
            for mem in tar:
                key, _, ext = mem.name.partition(".")
                r = rows.setdefault(key, {"shard": shard})
                if ext == "png":
                    r["off"], r["size"] = mem.offset_data, mem.size
                elif ext == "json":
                    fh = tar.extractfile(mem)
                    assert fh is not None
                    meta = json.loads(fh.read())
                    r["frame_id"], r["t"] = int(meta["frame_id"]), int(meta["t_mono_ns"])
    out = [r for r in rows.values() if "off" in r and "t" in r]
    out.sort(key=lambda r: r["t"])
    p = index_path(sid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out))
    return out


def load_index(sid: str) -> list[dict[str, Any]]:
    p = index_path(sid)
    return json.loads(p.read_text()) if p.exists() else build_index(sid)


def read_frame(sid: str, row: Mapping[str, Any]) -> Any:
    """The frame's RGB pixels (1280 x 720 game region)."""
    from PIL import Image

    with open(DATASETS / sid / row["shard"], "rb") as fh:
        fh.seek(int(row["off"]))
        data = fh.read(int(row["size"]))
    return np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))


def load_events(sid: str) -> list[dict[str, Any]]:
    with gzip.open(DATASETS / sid / "packets.jsonl.gz", "rt") as fh:
        return sorted((json.loads(x) for x in fh), key=lambda e: int(e["t_mono_ns"]))


def map_spans(events: Sequence[Mapping[str, Any]], map_name: str = MAP) -> list[tuple[int, int]]:
    """PURE: [t_change + MAP_SETTLE_S, next change) spans while on ``map_name``."""
    ch = [(int(e["t_mono_ns"]), str(e.get("map", ""))) for e in events if e["type"] == "map_change"]
    end = int(events[-1]["t_mono_ns"]) if events else 0
    out = []
    for i, (t, m) in enumerate(ch):
        if m.removesuffix(".gat") != map_name:
            continue
        t1 = ch[i + 1][0] if i + 1 < len(ch) else end
        a = t + int(MAP_SETTLE_S * NS)
        if a < t1:
            out.append((a, t1))
    # merge consecutive same-map spans (a same-map @warp is a map change too)
    merged: list[tuple[int, int]] = []
    for a, b in out:
        if merged and a <= merged[-1][1] + int(MAP_SETTLE_S * NS):
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


# --- the packet labels (OFFLINE ground truth) ---------------------------------------------------


class Truth:
    """One session's floor items, our position and the units, by the packets (item_labels.World /
    Geo: the Timeline and labels_v2's projection with our still cell as the camera target)."""

    def __init__(self, sid: str) -> None:
        import item_labels as il

        self.sid = sid
        self.events = load_events(sid)
        sess = il.Session(sid, MAP, {}, self.events, [])
        self.world = il.World(sess)
        self.geo = il.Geo(MAP)
        self.floors = il.floor_items(self.events)
        self.mc = il.first_map_change(self.events)

    def present(self, t_f: int) -> list[Any]:
        d = int(D_GONE_S * NS)
        return [f for f in self.floors if f.t_a <= t_f < f.t_v + (d if f.vanished else 0)]

    def frame(
        self, t_f: int, anchors: Mapping[int, tuple[float, float]] | None, rects: Sequence[Rect]
    ) -> dict[str, Any]:
        """The frame's status ('ok' or its frame exclusion) and its target items' views."""
        import item_labels as il

        from poring_dataset.labels_v2 import self_label

        if self.mc is None or t_f < self.mc:
            return {"status": "item_truth_unknown", "items": []}
        fws = self.world.steps(t_f)
        if not il.World.still(fws):
            return {"status": "self_moving", "items": []}
        if self.world.is_dead(t_f):
            return {"status": "self_dead", "items": []}
        gm = fws[-1].self_pos
        sc = self.geo.scene(gm)
        sl = self_label(fws[-1], sc)
        sbox = None
        if sl is not None:
            b = sl.box
            sbox = (b[0] - SELF_PAD, b[1] - SELF_PAD, b[2] + SELF_PAD, b[3] + SELF_PAD)
        ubs = []
        n = int(round(UNIT_LAG_S / STEP_S))
        for i in range(n + 1):
            fw = self.world.tl.frame_world(t_f - int((n - i) * STEP_S * NS))
            for e in fw.entities:
                if e.gid == self.world.aid:
                    continue
                u, v = self.geo.project(sc, (e.x, e.y))
                ubs.append(unit_box(u, v))
        d_app, d_gone = int(D_APPEAR_S * NS), int(D_GONE_S * NS)
        views = []
        for f in self.present(t_f):
            g = self.geo.project(sc, il.item_cell(f, OX, OY))
            if anchors is None:
                c, side = g, SAMPLE_BOX
            else:
                a = anchors.get(f.item_id, (0.0, 0.0))
                c, side = (g[0] + a[0], g[1] + a[1]), ITEM_BOX
            views.append(
                ItemView(
                    f.floor_id,
                    f.item_id,
                    il.phase(f, t_f, d_app, d_gone),
                    (round(g[0], 2), round(g[1], 2)),
                    (round(c[0], 2), round(c[1], 2)),
                    square(c, side),
                )
            )
        views = exclusions([v for v in views if v.phase != "none"], sbox, ubs, rects)
        return {
            "status": "ok",
            "gm": gm,
            "self_box": sbox,
            "items": views,
            "floors": {f.floor_id: f for f in self.present(t_f)},
        }


def ui_rects() -> list[Rect]:
    import client_layout

    return [tuple(map(float, r)) for r in client_layout.RECTS["hunt"]]  # type: ignore[misc]


def self_screen_box() -> Rect:
    """Our own sprite's FIXED screen box (the camera target: our feet), pixel-legal for the
    detector: labels_v2's player box (34 x 74) at the projection of our own cell, + SELF_PAD."""
    import item_labels as il

    geo = il.Geo(MAP)
    sc = geo.scene((150.0, 150.0))
    u, v = geo.project(sc, (150.0, 150.0))
    return (u - 17 - SELF_PAD, v - 74 - SELF_PAD, u + 17 + SELF_PAD, v + SELF_PAD)


def staged_frames(split: str) -> list[tuple[Window, dict[str, Any]]]:
    """The staged session's frames inside the split's still windows (index rows only)."""
    changes = [int(e["t_mono_ns"]) for e in load_events(STAGED) if e["type"] == "map_change"]
    wins = still_windows([json.loads(x) for x in STAGE_EVENTS.read_text().splitlines()], changes)
    out = []
    for r in load_index(STAGED):
        w = window_of(wins, int(r["t"]))
        if w is not None and split_of_spot(w.spot) == split:
            out.append((w, r))
    return out


# --- commands ------------------------------------------------------------------------------------


def cmd_index(a: argparse.Namespace) -> int:
    for sid in a.sid:
        t0 = time.time()
        rows = build_index(sid)
        print(f"{sid}: {len(rows)} frames indexed ({time.time() - t0:.0f} s)", flush=True)
    return 0


def cmd_inventory(_a: argparse.Namespace) -> int:
    """Packet-only: per split, frames in still windows, frame statuses, labelled items per id and
    the exclusions (the provisional SAMPLE_BOX geometry: anchors are FIT's)."""
    tr = Truth(STAGED)
    rects = ui_rects()
    res: dict[str, Any] = {}
    for split in ("fit", "test"):
        st: Counter[str] = Counter()
        lab: Counter[str] = Counter()
        exc: Counter[str] = Counter()
        inst: dict[str, set[int]] = {}
        frames = staged_frames(split)
        for _w, r in frames:
            fr = tr.frame(int(r["t"]), None, rects)
            st[fr["status"]] += 1
            for iv in fr["items"]:
                if iv.item_id not in TARGETS:
                    exc["non_target"] += 1
                    continue
                if iv.labelled:
                    lab[str(iv.item_id)] += 1
                    inst.setdefault(str(iv.item_id), set()).add(iv.floor_id)
                for x in iv.excl or ([iv.phase] if iv.phase != "on" else []):
                    exc[x] += 1
        res[split] = {
            "frames": len(frames),
            "status": dict(st),
            "labelled": dict(lab),
            "instances": {k: len(v) for k, v in inst.items()},
            "exclusions": dict(exc),
        }
    print(json.dumps(res, indent=1))
    (OUT / "inventory.json").write_text(json.dumps(res, indent=1))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("index")
    p.add_argument("sid", nargs="+")
    sub.add_parser("inventory")
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    return {"index": cmd_index, "inventory": cmd_inventory}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())


__all__: Iterable[str] = ()
_ = (hashlib, os)
