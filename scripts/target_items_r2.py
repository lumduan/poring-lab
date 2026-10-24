#!/usr/bin/env python3
"""ROUND 2 of the target-item study (docs/planning/target-items.md section 10, PRE-REGISTERED):
Batt's four target items (757, 756, 604, 518) staged on OPEN ground (stage-c), MULTI-templates per
item (one sprite mask, colour variants per floor item), colour gates chosen on FIT, FIT-NEG from a
hunting session, the SAME bars as round 1. Round 1 (target_items.py) is unchanged; its pure parts
and its packet labels (``Truth``) are reused.

    target_items_r2.py index                         frame indexes (timestamps only, no pixel)
    target_items_r2.py inventory                     packet labels per split (counts; no pixel)
    target_items_r2.py fit                           FIT: templates, variants, anchors, thresholds
    target_items_r2.py freeze                        params.json + templates.npz sha256
    target_items_r2.py scan --set test|neg|natural   the frozen detector
    target_items_r2.py score                         the pre-registered bars

Packets are OFFLINE ground truth only (ADR-0007): they label where each floor item lies; the
DETECTOR reads pixels only (the frame, the hunt layout's fixed UI rectangles, our own sprite's and
our own HP / SP bar's fixed screen boxes at the camera target). Nothing here is a live input.

Client-derived outputs (crops, templates, candidates, labels) go to
/dev/shm/poring-lab-tmp/target-items-r2/ only, never the repo. Item names are never written: ids.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import sys
import time
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):  # one BLAS thread per
    os.environ.setdefault(_v, "1")  # worker: a shared host (WORKERS processes, no oversubscription)

import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

import target_items as ti  # noqa: E402

OUT = Path("/dev/shm/poring-lab-tmp/target-items-r2")
PDIR = OUT / "params"
NS = 10**9
TARGETS = ti.TARGETS

# --- the data and the split (target-items.md 10.1-10.2, fixed by the pre-registration) ----------
STAGED_B = ti.STAGED  # round 1's staging (read in round 1)
EVENTS_B = ti.STAGE_EVENTS
STAGED_C = "20261024T222352-rdp-stage-items-c"  # stage@2 --open, seed 8 (never read before 10)
EVENTS_C = Path("/dev/shm/poring-lab-demo/20261024T222356-stage-items-pay_fild07-c/events.jsonl")
EVENTS = {STAGED_B: EVENTS_B, STAGED_C: EVENTS_C}
# FIT: stage-c spots 0-7 + round 1's OPEN-ground spots of stage-b (by eye in round 1: amendment A
# and 9b: spots 0, 3, 5 of its FIT, 9, 10 of its TEST); TEST: stage-c spots 8-11
FIT_SPOTS: dict[str, tuple[int, ...]] = {STAGED_C: tuple(range(0, 8)), STAGED_B: (0, 3, 5, 9, 10)}
TEST_SPOTS: dict[str, tuple[int, ...]] = {STAGED_C: (8, 9, 10, 11)}
FIT_NEG = ("20261024T123622-rdp-thief-t1b",)
TEST_NEG = ("20261024T193810-rdp-thief-s4", "20261024T201949-rdp-thief-s5")
NATURAL = ("20261024T164555-rdp-thief-s-pilot", "20261024T210115-rdp-thief-s6")

# --- the label rule's one change: our own HP / SP bar (10.3) ------------------------------------
BAR = (-36.0, 0.0, 36.0, 24.0)  # (du0, dv0, du1, dv1) px from our feet (10.3: round 1 saw a 756
# centred (-32, +19) from our feet under the bar); not measured: a generous box

# --- the multi-template detector (10.4) -----------------------------------------------------------
GEN_NCC = 0.35  # the pooled template's NCC local maxima that are re-scored by every variant
MIN_PLACE_SAMPLES = 5  # a floor item's kept samples for its own colour variant
WORKERS = 10
CHUNK = 48  # frames read sequentially (one session at a time) per batch: paced NAS reads


# --- frames and labels -------------------------------------------------------------------------


def load_index(sid: str) -> list[dict[str, Any]]:
    return ti.load_index(sid, OUT)


def stage_events(sid: str) -> list[dict[str, Any]]:
    return [json.loads(x) for x in EVENTS[sid].read_text().splitlines() if x.strip()]


def spot_frames(
    windows: Sequence[ti.Window], rows: Sequence[Mapping[str, Any]], spots: Sequence[int]
) -> list[tuple[ti.Window, Mapping[str, Any]]]:
    """PURE: the index rows inside a still window of one of ``spots``."""
    out = []
    for r in rows:
        w = ti.window_of(windows, int(r["t"]))
        if w is not None and w.spot in spots:
            out.append((w, r))
    return out


def staged_frames(sid: str, spots: Sequence[int]) -> list[tuple[ti.Window, Mapping[str, Any]]]:
    changes = [int(e["t_mono_ns"]) for e in ti.load_events(sid) if e["type"] == "map_change"]
    wins = ti.still_windows(stage_events(sid), changes)
    return spot_frames(wins, load_index(sid), spots)


def bar_box(self_box: ti.Rect) -> ti.Rect:
    """PURE: our HP / SP bar's box from our own (padded) box: around our feet."""
    u = (self_box[0] + self_box[2]) / 2.0
    v = self_box[3] - ti.SELF_PAD
    return (u + BAR[0], v + BAR[1], u + BAR[2], v + BAR[3])


def add_bar(fr: dict[str, Any]) -> dict[str, Any]:
    """PURE: 'under_self_bar' on every item whose box touches our bar's box (an item already
    under_self keeps that one only)."""
    if fr.get("status") != "ok" or fr.get("self_box") is None:
        return fr
    bb = bar_box(fr["self_box"])
    for iv in fr["items"]:
        if "under_self" not in iv.excl and ti.inter(iv.box, bb) > 0:
            iv.excl.append("under_self_bar")
    return fr


def frame_truth(
    tr: ti.Truth, t: int, anchors: Mapping[int, tuple[float, float]] | None, rects: Any
) -> dict[str, Any]:
    return add_bar(tr.frame(t, anchors, rects))


def drop_rects() -> list[ti.Rect]:
    """The detector's fixed no-go boxes: the hunt layout's UI windows, our sprite, our bar."""
    sb = ti.self_screen_box()
    return [*ti.ui_rects(), sb, bar_box(sb)]


# --- the multi-template (PURE on arrays) -------------------------------------------------------


@dataclass
class MultiTpl:
    item_id: int
    pooled: ti.Tpl  # the pooled template: the mask, the anchor, variant 0's colours
    variants: Any  # K x h x w x 3 float32 (variant 0 = the pooled median)
    keys: list[str]  # "pooled", then "<session>:<floor id>" per floor-item variant

    @property
    def size(self) -> tuple[int, int]:
        return self.pooled.size


def place_variants(
    built: ti.Built, inst: Sequence[int], min_n: int = MIN_PLACE_SAMPLES
) -> tuple[list[int], Any]:
    """PURE: per floor item ("place") with >= ``min_n`` kept samples, the median of its kept
    samples' tight windows (aligned by the pooled build): (place keys, P x h x w x 3)."""
    keys = [int(inst[int(i)]) for i in built.kept]
    out_k: list[int] = []
    out: list[Any] = []
    for p in sorted(set(keys)):
        rows = [j for j, k in enumerate(keys) if k == p]
        if len(rows) >= min_n:
            out_k.append(p)
            out.append(np.median(np.asarray(built.windows)[rows], 0))
    h, w = built.tpl.size
    return out_k, (np.stack(out).astype(np.float32) if out else np.zeros((0, h, w, 3), np.float32))


def ncc_rms_at(img: Any, mask: Any, variants: Any, ys: Any, xs: Any) -> tuple[Any, Any]:
    """PURE: masked colour NCC and RMS colour distance (item_icons' maths: one mean over the three
    channels) of each variant with its top-left at (xs, ys): two K x N arrays."""
    a = np.asarray(img)[..., :3]
    my, mx = np.nonzero(np.asarray(mask, bool))
    tv = np.asarray(variants, np.float64)[:, my, mx].reshape(len(variants), -1)  # K x 3P
    n = tv.shape[1]
    mu = tv.mean(1)
    tp = tv - mu[:, None]
    tvar = np.maximum((tp**2).sum(1), 1e-6)
    tsq = (tv**2).sum(1)
    ys = np.asarray(ys, int)
    xs = np.asarray(xs, int)
    ncc = np.zeros((len(tv), len(ys)))
    rms = np.zeros((len(tv), len(ys)))
    for s0 in range(0, len(ys), 1024):
        yb, xb = ys[s0 : s0 + 1024], xs[s0 : s0 + 1024]
        patch = a[yb[:, None] + my[None, :], xb[:, None] + mx[None, :]]
        patch = patch.reshape(len(yb), -1).astype(np.float64)  # N x 3P
        s1 = patch.sum(1)
        s2 = (patch**2).sum(1)
        var_i = np.maximum(s2 - s1 * s1 / n, 1e-6)
        num = patch @ tp.T  # N x K
        ncc[:, s0 : s0 + 1024] = (num / np.sqrt(var_i[:, None] * tvar[None, :])).T
        ssd = s2[:, None] - 2.0 * (num + mu[None, :] * s1[:, None]) + tsq[None, :]
        rms[:, s0 : s0 + 1024] = np.sqrt(np.maximum(ssd, 0.0) / n).T
    return ncc, rms


def inlier_at(img: Any, mask: Any, variants: Any, ys: Any, xs: Any, ks: Any) -> Any:
    """PURE: the inlier share (every channel within INLIER_PX of the rounded template) of variant
    ``ks[i]`` with its top-left at (xs[i], ys[i])."""
    a = np.asarray(img)[..., :3]
    my, mx = np.nonzero(np.asarray(mask, bool))
    tr = np.asarray(variants, np.float32)[:, my, mx].round().astype(np.int16)  # K x P x 3
    ys = np.asarray(ys, int)
    xs = np.asarray(xs, int)
    ks = np.asarray(ks, int)
    out = np.zeros(len(ys))
    for s0 in range(0, len(ys), 1024):
        yb, xb, kb = ys[s0 : s0 + 1024], xs[s0 : s0 + 1024], ks[s0 : s0 + 1024]
        patch = a[yb[:, None] + my[None, :], xb[:, None] + mx[None, :]].astype(np.int16)
        out[s0 : s0 + 1024] = (np.abs(patch - tr[kb]).max(-1) <= ti.INLIER_PX).mean(1)
    return out


def score_at(img: Any, mask: Any, variants: Any, ys: Any, xs: Any) -> tuple[Any, Any, Any]:
    """PURE: NCC, RMS and inlier share of EVERY variant at every position (three K x N arrays;
    the scan computes the inlier share only for the chosen variant: the same numbers)."""
    ncc, rms = ncc_rms_at(img, mask, variants, ys, xs)
    inl = np.stack([inlier_at(img, mask, variants, ys, xs, np.full(len(ys), k))
                    for k in range(len(variants))])  # fmt: skip
    return ncc, rms, inl


def scan_multi(
    img: Any, mtpls: Sequence[MultiTpl], drop: Sequence[ti.Rect], gen_ncc: float = GEN_NCC
) -> dict[int, Any]:
    """PURE (pixels only): per item, its candidates over the whole image as an n x 6 float32 array
    (u, v = the sprite centre, NCC, RMS, inlier share of the best variant there, its index): the
    pooled template's NCC local maxima (+-LOCAL_R) >= ``gen_ncc`` outside every ``drop`` box,
    each re-scored by EVERY variant at every offset within +-LOCAL_R and moved to its best
    (variant, offset) by NCC; kept with NCC >= CAND_NCC, centres outside ``drop``, greedy NMS
    within NMS_PX by NCC."""
    import item_icons as ii

    a = np.asarray(img)[..., :3]
    hh, ww = a.shape[:2]
    maps = ii.match_maps(a, [m.pooled.as_icon() for m in mtpls])
    r = ti.LOCAL_R
    dyx = np.array([(dy, dx) for dy in range(-r, r + 1) for dx in range(-r, r + 1)])
    out: dict[int, Any] = {}
    for m, (ncc, _rms) in zip(mtpls, maps, strict=True):
        h, w = m.size
        empty = np.zeros((0, 6), np.float32)
        fin = np.where(np.isfinite(ncc), ncc, -np.inf)
        ys, xs = np.nonzero((fin >= gen_ncc) & ti.local_maxima(fin))
        keep = ~ti.inside_any(xs + (w - 1) / 2.0, ys + (h - 1) / 2.0, drop)
        ys, xs = ys[keep], xs[keep]
        if not len(ys):
            out[m.item_id] = empty
            continue
        py = (ys[:, None] + dyx[None, :, 0]).ravel()
        px = (xs[:, None] + dyx[None, :, 1]).ravel()
        ok = (py >= 0) & (px >= 0) & (py + h <= hh) & (px + w <= ww)
        nc, rm = ncc_rms_at(a, m.pooled.mask, m.variants, py[ok], px[ok])
        kb = np.argmax(nc, 0)
        col = np.arange(nc.shape[1])
        best = np.full(len(py), -np.inf)
        best[ok] = nc[kb, col]
        feats = np.zeros((len(py), 2))
        feats[ok] = np.stack([rm[kb, col], kb], 1)
        best = best.reshape(len(ys), len(dyx))
        j = np.argmax(best, 1)
        sc = best[np.arange(len(ys)), j]
        sel = np.arange(len(ys)) * len(dyx) + j
        u = px[sel] + (w - 1) / 2.0
        v = py[sel] + (h - 1) / 2.0
        f = feats[sel]
        keep = (sc >= ti.CAND_NCC) & ~ti.inside_any(u, v, drop)
        sel, u, v, sc, f = sel[keep], u[keep], v[keep], sc[keep], f[keep]
        if not len(u):
            out[m.item_id] = empty
            continue
        k = ti.nms(np.stack([u, v], 1), sc)
        inl = inlier_at(a, m.pooled.mask, m.variants, py[sel[k]], px[sel[k]], f[k, 1])
        out[m.item_id] = np.stack([u[k], v[k], sc[k], f[k, 0], inl, f[k, 1]], 1).astype(np.float32)
    return out


# --- the scanner: sequential reads, a worker pool ------------------------------------------------

_POOL: dict[str, Any] = {}


def read_bytes(sid: str, row: Mapping[str, Any]) -> bytes:
    with open(ti.DATASETS / sid / row["shard"], "rb") as fh:
        fh.seek(int(row["off"]))
        return fh.read(int(row["size"]))


def _job(job: tuple[str, int, bytes]) -> tuple[str, int, bool, dict[int, Any]]:
    import io

    from PIL import Image

    sid, t, data = job
    img = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))
    ok = bool(_POOL["layout"].ok(img))
    return sid, t, ok, scan_multi(img, _POOL["mtpls"], _POOL["drop"])


def chunks(seq: Sequence[Any], n: int) -> Iterator[Sequence[Any]]:
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def scan_jobs(
    jobs: Sequence[tuple[str, Mapping[str, Any]]], mtpls: Sequence[MultiTpl]
) -> dict[tuple[str, int], tuple[bool, dict[int, Any]]]:
    """{(sid, t): (layout ok, candidates)}: the PNG bytes read by THIS process, sequentially, one
    session after the other, CHUNK frames at a time; decode + scan in WORKERS processes."""
    import multiprocessing as mp

    import item_labels as il

    _POOL.update(mtpls=list(mtpls), drop=drop_rects(), layout=il.Layout())
    out: dict[tuple[str, int], tuple[bool, dict[int, Any]]] = {}
    t0 = time.time()
    done = 0
    with mp.get_context("fork").Pool(WORKERS) as pool:
        for ch in chunks(list(jobs), CHUNK):
            blobs = [(sid, int(r["t"]), read_bytes(sid, r)) for sid, r in ch]
            for sid, t, ok, c in pool.imap(_job, blobs, chunksize=1):
                out[(sid, t)] = (ok, c)
            done += len(ch)
            if done % (CHUNK * 5) == 0 or done == len(jobs):
                print(f"  {done}/{len(jobs)} frames ({time.time() - t0:.0f} s)", flush=True)
    return out


def neg_frames(sids: Sequence[str]) -> list[tuple[str, Mapping[str, Any]]]:
    out: list[tuple[str, Mapping[str, Any]]] = []
    for sid in sids:
        ev = ti.load_events(sid)
        if any(e["type"] == "floor_item_appear" and e.get("item_id") in TARGETS for e in ev):
            raise SystemExit(f"{sid}: a target item is on the floor: not a negative session")
        spans = ti.map_spans(ev)
        out += [(sid, r) for r in load_index(sid) if ti.in_spans(spans, int(r["t"]))]
    return out


def natural_frames() -> list[tuple[str, Mapping[str, Any], int]]:
    """Every NATURAL session's frames in [a target's fall + D_APPEAR, its vanish): (sid, row,
    floor id)."""
    import item_labels as il

    out = []
    for sid in NATURAL:
        fl = [f for f in il.floor_items(ti.load_events(sid)) if f.item_id in TARGETS]
        for r in load_index(sid):
            t = int(r["t"])
            for f in fl:
                if f.t_a + int(ti.D_APPEAR_S * NS) <= t < f.t_v:
                    out.append((sid, r, f.floor_id))
    return out


# --- params ---------------------------------------------------------------------------------------


def save_multi(mt: Mapping[int, MultiTpl], path: Path) -> None:
    arrs = {}
    for it, m in mt.items():
        arrs[f"rgb_{it}"] = np.asarray(m.pooled.rgb, np.float32)
        arrs[f"mask_{it}"] = np.asarray(m.pooled.mask, bool)
        arrs[f"variants_{it}"] = np.asarray(m.variants, np.float32)
    with open(path, "wb") as fh:
        np.savez(fh, **arrs)


def load_frozen() -> tuple[dict[str, Any], dict[int, MultiTpl]]:
    fz = PDIR / "frozen.json"
    if not fz.exists():
        raise SystemExit("not frozen: run fit, then freeze (target-items.md 10.4)")
    f = json.loads(fz.read_text())
    for name in ("params.json", "templates.npz"):
        if ti.sha256(PDIR / name) != f[name]:
            raise SystemExit(f"{name}: sha256 differs from the frozen one")
    p = json.loads((PDIR / "params.json").read_text())
    z = np.load(PDIR / "templates.npz")
    out = {}
    for it in TARGETS:
        if f"rgb_{it}" in z.files:
            q = p["items"][str(it)]
            a = q["anchor"]
            tp = ti.Tpl(it, z[f"rgb_{it}"], z[f"mask_{it}"], (float(a[0]), float(a[1])))
            out[it] = MultiTpl(it, tp, z[f"variants_{it}"], list(q["variant_keys"]))
    return p, out


def _short(sid: str) -> str:
    return sid.rsplit("-", 1)[-1]


# --- commands ------------------------------------------------------------------------------------


def cmd_index(_a: argparse.Namespace) -> int:
    for sid in [*FIT_SPOTS, *FIT_NEG, *TEST_NEG, *NATURAL]:
        t0 = time.time()
        rows = ti.build_index(sid, OUT)
        print(f"{sid}: {len(rows)} frames indexed ({time.time() - t0:.0f} s)", flush=True)
    return 0


def cmd_inventory(_a: argparse.Namespace) -> int:
    """Packet-only: per split, frames in the still windows, statuses, labelled items per id (the
    provisional SAMPLE_BOX geometry), floor items, exclusions."""
    rects = ti.ui_rects()
    res: dict[str, Any] = {}
    for split, spots in (("fit", FIT_SPOTS), ("test", TEST_SPOTS)):
        st: Counter[str] = Counter()
        lab: Counter[str] = Counter()
        exc: Counter[str] = Counter()
        inst: dict[str, set[str]] = {}
        nfr = 0
        for sid, sp in spots.items():
            tr = ti.Truth(sid)
            frames = staged_frames(sid, sp)
            nfr += len(frames)
            for _w, r in frames:
                fr = frame_truth(tr, int(r["t"]), None, rects)
                st[fr["status"]] += 1
                for iv in fr["items"]:
                    if iv.labelled:
                        lab[str(iv.item_id)] += 1
                        inst.setdefault(str(iv.item_id), set()).add(f"{_short(sid)}:{iv.floor_id}")
                    for x in iv.excl or ([iv.phase] if iv.phase != "on" else []):
                        exc[x] += 1
        res[split] = {
            "frames": nfr,
            "status": dict(st),
            "labelled": dict(lab),
            "floor_items": {k: len(v) for k, v in inst.items()},
            "exclusions": dict(exc),
        }
    print(json.dumps(res, indent=1))
    (OUT / "inventory.json").write_text(json.dumps(res, indent=1))
    return 0


def cmd_fit(_a: argparse.Namespace) -> int:
    import item_labels as il

    rects = ti.ui_rects()
    PDIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    layout = il.Layout()
    crops: dict[int, list[Any]] = {it: [] for it in TARGETS}
    inst: dict[int, list[int]] = {it: [] for it in TARGETS}
    place_name: dict[int, str] = {}
    layout_bad = 0
    eval_frames: list[tuple[str, Mapping[str, Any]]] = []
    truths: dict[str, ti.Truth] = {}
    for si, (sid, spots) in enumerate(FIT_SPOTS.items()):
        tr = truths[sid] = ti.Truth(sid)
        frames = staged_frames(sid, spots)
        eval_frames += [(sid, r) for _w, r in frames]
        by_frame: dict[int, list[ti.ItemView]] = {}
        rows: dict[int, Mapping[str, Any]] = {}
        for _w, r in frames:
            t = int(r["t"])
            fr = frame_truth(tr, t, None, rects)
            if fr["status"] != "ok":
                continue
            for iv in fr["items"]:
                if iv.item_id in TARGETS and ti._sample_ok(iv, fr["present"], rects, t):
                    by_frame.setdefault(t, []).append(iv)
                    rows[t] = r
        for t, ivs in sorted(by_frame.items()):  # FIT pixels: sequential reads
            img = ti.read_frame(sid, rows[t])
            if not layout.ok(img):
                layout_bad += 1
                continue
            for iv in ivs:
                cu, cv = int(round(iv.ground[0])), int(round(iv.ground[1]))
                h = ti.CROP_HALF
                c = img[cv - h : cv + h + 1, cu - h : cu + h + 1]
                key = (si + 1) * 100000 + iv.floor_id
                place_name[key] = f"{_short(sid)}:{iv.floor_id}"
                crops[iv.item_id].append(np.ascontiguousarray(c))
                inst[iv.item_id].append(key)
    print(f"samples: { {k: len(v) for k, v in crops.items()} } ({time.time() - t0:.0f} s)")
    with open(PDIR / "fit_samples.npz", "wb") as fh:  # client pixels: /dev/shm only
        np.savez(fh, **{f"crops_{it}": np.stack(v) for it, v in crops.items() if v},
                 **{f"inst_{it}": np.asarray(inst[it]) for it in TARGETS if inst[it]})  # fmt: skip
    mt: dict[int, MultiTpl] = {}
    rep: dict[str, Any] = {"layout_bad_sample_frames": layout_bad, "items": {}}
    for it in TARGETS:
        b = ti.build_seeded_core(np.stack(crops[it]), it, inst[it]) if crops[it] else None
        if b is None:
            rep["items"][str(it)] = {"samples": len(crops[it]), "template": None}
            print(it, "NO TEMPLATE", flush=True)
            continue
        pk, pv = place_variants(b, inst[it])
        variants = np.concatenate([np.asarray(b.tpl.rgb, np.float32)[None], pv])
        keys = ["pooled", *[place_name[k] for k in pk]]
        mt[it] = MultiTpl(it, b.tpl, variants, keys)
        offs = []
        for c in crops[it]:
            m = ti.best_offset(c, b.tpl, (ti.CROP_HALF + b.tpl.anchor[0],
                                          ti.CROP_HALF + b.tpl.anchor[1]), 8)  # fmt: skip
            if m is not None:
                offs.append((m["dx"], m["dy"], m["ncc"]))
        o = np.asarray(offs, float)
        per_place = Counter(place_name[int(inst[it][int(i)])] for i in b.kept)
        rep["items"][str(it)] = {
            "samples": len(crops[it]),
            "floor_items": len(set(inst[it])),
            "kept": b.tpl.samples,
            "kept_floor_items": b.tpl.instances,
            "kept_per_floor_item": dict(per_place),
            "variants": keys,
            "size_hw": list(b.tpl.size),
            "mask_px": int(np.asarray(b.tpl.mask).sum()),
            "anchor": list(b.tpl.anchor),
            "align_median_abs_dx": float(np.median(np.abs(o[:, 0]))),
            "align_median_abs_dy": float(np.median(np.abs(o[:, 1]))),
            "align_ncc_median": round(float(np.median(o[:, 2])), 4),
            "align_ncc_p10": round(float(np.quantile(o[:, 2], 0.1)), 4),
        }
        print(json.dumps({it: rep["items"][str(it)]}), flush=True)
    save_multi(mt, PDIR / "templates.npz")
    al = {it: rep["items"][str(it)] for it in mt}
    lim = ti.ALIGN_STOP_PX
    stop = [
        it for it, q in al.items() if max(q["align_median_abs_dx"], q["align_median_abs_dy"]) > lim
    ]
    if stop:
        rep["STOP"] = f"alignment: median |offset| > {ti.ALIGN_STOP_PX} px for {stop}"
        (PDIR / "fit_report.json").write_text(json.dumps(rep, indent=1))
        print(rep["STOP"])
        return 2
    anchors = {it: m.pooled.anchor for it, m in mt.items()}
    negs = neg_frames(FIT_NEG)
    print(f"FIT scan: {len(eval_frames)} staged + {len(negs)} FIT-NEG frames", flush=True)
    res = scan_jobs(eval_frames + negs, list(mt.values()))
    pos: dict[int, list[Any]] = {it: [] for it in mt}
    false: dict[int, list[Any]] = {it: [] for it in mt}
    n_cand: Counter[int] = Counter()
    labelled_n: Counter[int] = Counter()
    st: Counter[str] = Counter()
    n_staged = 0
    for sid, r in eval_frames:
        t = int(r["t"])
        ok, cands = res[(sid, t)]
        fr = frame_truth(truths[sid], t, anchors, rects)
        status = fr["status"] if ok or fr["status"] != "ok" else "ui_layout_mismatch"
        st[status] += 1
        if status != "ok":
            continue
        n_staged += 1
        labs = [iv for iv in fr["items"] if iv.labelled and iv.item_id in mt]
        mf = ti.match_frame({k: v[:, :5] for k, v in cands.items()}, labs, fr["present"])
        for it in mt:
            pos[it] += mf[it]["pos"]
            false[it].append(mf[it]["false"])
            n_cand[it] += len(mf[it]["cands"])
            labelled_n[it] += len(mf[it]["labs"])
    n_neg = 0
    neg_layout_bad = 0
    for sid, r in negs:
        ok, cands = res[(sid, int(r["t"]))]
        n_neg += 1
        neg_layout_bad += int(not ok)
        for it in mt:
            c = np.asarray(cands.get(it, np.zeros((0, 6))), float).reshape(-1, 6)
            false[it].append(c[:, 2:5])
            n_cand[it] += len(c)
    nf = n_staged + n_neg
    params: dict[str, Any] = {
        "pre_registration": "docs/planning/target-items.md section 10 (round 2)",
        "constants": {
            **{
                k: getattr(ti, k)
                for k in (
                    "D_APPEAR_S",
                    "D_GONE_S",
                    "OX",
                    "OY",
                    "STILL_LEAD_S",
                    "STILL_MAX_S",
                    "STILL_S",
                    "ITEM_BOX",
                    "SAMPLE_BOX",
                    "UNIT_HALF_W",
                    "UNIT_UP",
                    "UNIT_DOWN",
                    "UNIT_LAG_S",
                    "SELF_PAD",
                    "STACK_IOU",
                    "CROP_HALF",
                    "HALF",
                    "SEED",
                    "REFINE",
                    "ITERS",
                    "KEEP_SHARE",
                    "MIN_SAMPLES",
                    "CAND_NCC",
                    "LOCAL_R",
                    "NMS_PX",
                    "INLIER_PX",
                    "FIT_FALSE_MAX",
                    "MATCH_PX",
                    "RECALL_MIN",
                    "FALSE_MAX",
                    "PRECISION_MIN",
                    "N_MIN",
                )
            },
            "BAR": BAR,
            "GEN_NCC": GEN_NCC,
            "MIN_PLACE_SAMPLES": MIN_PLACE_SAMPLES,
            "FIT_SPOTS": FIT_SPOTS,
            "TEST_SPOTS": TEST_SPOTS,
            "FIT_NEG": FIT_NEG,
            "TEST_NEG": TEST_NEG,
            "NATURAL": NATURAL,
        },  # fmt: skip
        "drop_rects": drop_rects(),
        "fit_frames": {
            "staged_eval": n_staged,
            "fit_neg": n_neg,
            "fit_neg_layout_mismatch": neg_layout_bad,
            "status": dict(st),
        },  # fmt: skip
        "items": {},
    }
    for it, m in mt.items():
        gs = ti.grid_stats(pos[it], np.concatenate(false[it]) if false[it] else [], nf)
        ch = ti.choose(gs, ti.FIT_FALSE_MAX)
        params["items"][str(it)] = {
            "anchor": list(m.pooled.anchor),
            "size_hw": list(m.size),
            "mask_px": int(np.asarray(m.pooled.mask).sum()),
            "variant_keys": m.keys,
            "threshold": ch,
            "fit_labelled": labelled_n[it],
            "fit_candidates_per_frame": round(n_cand[it] / max(1, nf), 1),
        }
        print(json.dumps({it: params["items"][str(it)]}), flush=True)
    (PDIR / "params.json").write_text(json.dumps(params, indent=1, default=str))
    (PDIR / "fit_report.json").write_text(json.dumps(rep, indent=1))
    with open(PDIR / "fit_cands.pkl", "wb") as fh:
        pickle.dump({"pos": pos, "false": false, "n_frames": nf}, fh)
    print(f"fit done ({time.time() - t0:.0f} s); freeze next")
    return 0


def cmd_freeze(_a: argparse.Namespace) -> int:
    f = {
        "params.json": ti.sha256(PDIR / "params.json"),
        "templates.npz": ti.sha256(PDIR / "templates.npz"),
        "frozen_at": time.strftime("%Y-%m-%d %H:%M:%S %z"),
    }
    (PDIR / "frozen.json").write_text(json.dumps(f, indent=1))
    print(json.dumps(f, indent=1))
    return 0


def cmd_scan(a: argparse.Namespace) -> int:
    p, mt = load_frozen()
    if a.set == "test":
        jobs: list[tuple[str, Mapping[str, Any]]] = [
            (sid, r) for sid, sp in TEST_SPOTS.items() for _w, r in staged_frames(sid, sp)
        ]
    elif a.set == "neg":
        jobs = neg_frames(TEST_NEG)
    else:
        seen: set[tuple[str, int]] = set()
        jobs = []
        for sid, r, _fid in natural_frames():
            if (sid, int(r["t"])) not in seen:
                seen.add((sid, int(r["t"])))
                jobs.append((sid, r))
    print(f"scan {a.set}: {len(jobs)} frames ({time.strftime('%H:%M:%S')})", flush=True)
    t0 = time.time()
    res = scan_jobs(jobs, [mt[it] for it in TARGETS if it in mt])
    if a.set == "neg":  # keep what the curves can use (NCC >= the frozen one - 0.10)
        lo = {it: float(p["items"][str(it)]["threshold"]["ncc"]) - 0.10 for it in mt}
        res = {k: (ok, {it: c[c[:, 2] >= lo[it]] for it, c in cs.items()})
               for k, (ok, cs) in res.items()}  # fmt: skip
    sdir = OUT / "scan"
    sdir.mkdir(parents=True, exist_ok=True)
    with open(sdir / f"{a.set}.pkl", "wb") as fh:
        pickle.dump({"jobs": list(jobs), "res": res}, fh)
    print(f"scan {a.set} done ({time.time() - t0:.0f} s, {time.strftime('%H:%M:%S')})")
    return 0


def _det(c: Any, th: Mapping[str, Any]) -> Any:
    c = np.asarray(c, float).reshape(-1, 6)
    return c[ti.passes(c[:, :5], float(th["ncc"]), float(th["rms"]), float(th["inl"]))]


def cmd_score(_a: argparse.Namespace) -> int:
    import item_labels as il
    import stage_items as si

    p, mt = load_frozen()
    anchors = {it: m.pooled.anchor for it, m in mt.items()}
    th = {it: p["items"][str(it)]["threshold"] for it in mt if p["items"][str(it)]["threshold"]
          .get("ncc") is not None}  # fmt: skip
    rects = ti.ui_rects()
    canopy = Path("/dev/shm/poring-lab-tmp/payf07/canopy.npy")
    open_ = si.open_area(np.ones((400, 400), bool), np.load(canopy)) if canopy.exists() else None
    out: dict[str, Any] = {"items": {}}
    test = pickle.loads((OUT / "scan" / "test.pkl").read_bytes())
    truths = {sid: ti.Truth(sid) for sid in TEST_SPOTS}
    floors = {(sid, f.floor_id): f for sid in TEST_SPOTS
              for f in il.floor_items(truths[sid].events)}  # fmt: skip
    wins = {(sid, int(r["t"])): w for sid, sp in TEST_SPOTS.items()
            for w, r in staged_frames(sid, sp)}  # fmt: skip
    st: Counter[str] = Counter()
    rec: dict[int, list[dict[str, Any]]] = {it: [] for it in th}
    prec: dict[int, list[bool]] = {it: [] for it in th}
    excl: Counter[str] = Counter()
    for sid, r in test["jobs"]:
        t = int(r["t"])
        ok, cands = test["res"][(sid, t)]
        fr = frame_truth(truths[sid], t, anchors, rects)
        status = fr["status"] if ok or fr["status"] != "ok" else "ui_layout_mismatch"
        st[status] += 1
        if status != "ok":
            continue
        for iv in fr["items"]:
            for x in iv.excl:
                excl[x] += 1
        for it in th:
            d = _det(cands.get(it, np.zeros((0, 6))), th[it])
            pc = [c for iid, c in fr["present"] if iid == it]
            hit = ti.near(d[:, :2], pc).any(1) if pc else np.zeros(len(d), bool)
            prec[it] += [bool(x) for x in hit]
            for iv in fr["items"]:
                bar_only = iv.phase == "on" and iv.excl == ["under_self_bar"]  # round 1's rule
                if iv.item_id != it or not (iv.labelled or bar_only):
                    continue
                nb = ti.near([iv.centre], d[:, :2])[0]
                best = None
                if nb.any():
                    dd = d[nb]
                    k = int(np.argmax(dd[:, 2]))
                    best = [round(float(dd[k, 0] - iv.centre[0]), 1),
                            round(float(dd[k, 1] - iv.centre[1]), 1),
                            round(float(dd[k, 2]), 3), mt[it].keys[int(dd[k, 5])]]  # fmt: skip
                cand = np.asarray(cands.get(it, np.zeros((0, 6))), float).reshape(-1, 6)
                cn = ti.near([iv.centre], cand[:, :2])[0]
                bc = cand[cn][np.argmax(cand[cn][:, 2])][2:5] if cn.any() else None
                fl = floors[(sid, iv.floor_id)]
                w = wins[(sid, t)]
                rec[it].append({
                    "frame": f"{r['frame_id']:09d}", "t": t, "spot": w.spot, "view": list(w.at),
                    "floor_id": iv.floor_id, "centre": list(iv.centre), "found": bool(nb.any()),
                    "best": best,
                    "best_cand": None if bc is None else [round(float(x), 3) for x in bc],
                    "open_cell": None if open_ is None else bool(open_[fl.y, fl.x]),
                    "bar_only": bar_only,
                })  # fmt: skip
    npath = OUT / "scan" / "neg.pkl"  # not scanned yet: no TEST-NEG frames, every item fails
    neg = pickle.loads(npath.read_bytes()) if npath.exists() else {"jobs": [], "res": {}}
    n_neg = len(neg["jobs"])
    fneg: Counter[int] = Counter()
    fneg_bad: Counter[int] = Counter()
    fneg_sid: dict[str, Counter[int]] = {}
    for (sid, _t), (ok, cands) in neg["res"].items():
        for it in th:
            n = len(_det(cands.get(it, np.zeros((0, 6))), th[it]))
            fneg[it] += n
            fneg_sid.setdefault(_short(sid), Counter())[it] += n
            if not ok:
                fneg_bad[it] += n
    neg_layout_bad = sum(1 for ok, _c in neg["res"].values() if not ok)
    for it in th:
        rs = [x for x in rec[it] if not x["bar_only"]]
        r1 = rec[it]  # round 1's label rule: the bar exclusion off (reported, not the verdict)
        n = len(rs)
        found = sum(bool(x["found"]) for x in rs)
        per_inst: dict[str, list[int]] = {}
        for x in rs:
            per_inst.setdefault(str(x["floor_id"]), [0, 0])
            per_inst[str(x["floor_id"])][0] += int(x["found"])
            per_inst[str(x["floor_id"])][1] += 1
        pr = prec[it]
        recall = found / n if n else None
        precision = sum(pr) / len(pr) if pr else None
        f100 = 100.0 * fneg[it] / n_neg if n_neg else math.inf
        verdict = "NO VERDICT" if n < ti.N_MIN else (
            "PASS" if recall is not None and recall >= ti.RECALL_MIN and precision is not None
            and precision >= ti.PRECISION_MIN and f100 <= ti.FALSE_MAX else "FAIL")  # fmt: skip
        out["items"][str(it)] = {
            "threshold": th[it],
            "test_labelled": n,
            "test_found": found,
            "recall": None if recall is None else round(recall, 4),
            "per_floor_item": per_inst,
            "test_detections": len(pr),
            "test_true": int(sum(pr)),
            "precision": None if precision is None else round(precision, 4),
            "neg_frames": n_neg,
            "neg_false": fneg[it],
            "neg_false_by_session": {k: v[it] for k, v in fneg_sid.items()},
            "neg_false_on_non_hunt_layout": fneg_bad[it],
            "neg_false_per_100": round(f100, 3),
            "verdict": verdict,
            "variant_of_hits": dict(Counter(x["best"][3] for x in rs if x["found"])),
            "round1_rule_labelled": len(r1),
            "round1_rule_recall": round(sum(bool(x["found"]) for x in r1) / len(r1), 4)
            if r1
            else None,
            "bar_only_misses": [x for x in r1 if x["bar_only"] and not x["found"]],
            "misses": [x for x in rs if not x["found"]],
        }
    out["test_status"] = dict(st)
    out["test_exclusions"] = dict(excl)
    out["neg_layout_mismatch_frames"] = neg_layout_bad
    nat_path = OUT / "scan" / "natural.pkl"
    nat: list[dict[str, Any]] = []
    if nat_path.exists():
        natp = pickle.loads(nat_path.read_bytes())
        ntr = {sid: ti.Truth(sid) for sid in NATURAL}
        for sid, r, fid in natural_frames():
            t = int(r["t"])
            ok, cands = natp["res"][(sid, t)]
            fr = frame_truth(ntr[sid], t, anchors, rects)
            ivs = [iv for iv in fr.get("items", []) if iv.floor_id == fid]
            row: dict[str, Any] = {"session": _short(sid), "floor_id": fid,
                                   "frame": f"{r['frame_id']:09d}", "status": fr["status"],
                                   "layout_ok": ok}  # fmt: skip
            if ivs:
                iv = ivs[0]
                it = iv.item_id
                d = _det(cands.get(it, np.zeros((0, 6))), th[it]) if it in th else np.zeros((0, 6))
                row.update(item_id=it, centre=list(iv.centre), excl=iv.excl, phase=iv.phase,
                           n_det=len(d))  # fmt: skip
                if len(d):
                    dist = np.abs(d[:, :2] - np.asarray(iv.centre)).max(1)
                    row["nearest_px"] = round(float(dist.min()), 1)
                    row["found"] = bool(dist.min() <= ti.MATCH_PX)
                cand = np.asarray(cands.get(it, np.zeros((0, 6))), float).reshape(-1, 6)
                cn = ti.near([iv.centre], cand[:, :2])[0]
                row["best_cand_ncc_near"] = (round(float(cand[cn][:, 2].max()), 3)
                                             if cn.any() else None)  # fmt: skip
            nat.append(row)
    out["natural"] = nat
    (OUT / "score.json").write_text(json.dumps(out, indent=1, default=str))
    for it in th:
        x = {k: v for k, v in out["items"][str(it)].items() if k not in ("misses",)}
        print(it, json.dumps(x))
    print(json.dumps({"status": out["test_status"], "excl": out["test_exclusions"],
                      "neg_layout_mismatch_frames": neg_layout_bad}))  # fmt: skip
    for row in nat:
        print(json.dumps(row))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("index")
    sub.add_parser("inventory")
    sub.add_parser("fit")
    sub.add_parser("freeze")
    p = sub.add_parser("scan")
    p.add_argument("--set", choices=("test", "neg", "natural"), required=True)
    sub.add_parser("score")
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    cmds = {"index": cmd_index, "inventory": cmd_inventory, "fit": cmd_fit,
            "freeze": cmd_freeze, "scan": cmd_scan, "score": cmd_score}  # fmt: skip
    return cmds[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
