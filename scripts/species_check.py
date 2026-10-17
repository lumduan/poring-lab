#!/usr/bin/env python3
"""FAST SPECIES CHECK from pixels (Batt 2026-10-17): before an attack click the bot hovers the
target and waits up to 1.2 s for the client's name tag (refused / never shown 34-52 % of the time)
because a CREAMY (job 1018, a non-target) must never be clicked. This classifies the detector's
box crop by its colours and a small shape descriptor in < 5 ms; the tag is read only when the
answer is ambiguous (None).

    species_check.py labels SID [SID ...]          OFFLINE: label detector boxes by packets
    species_check.py crops SID [SID ...]           OFFLINE: cut the labelled crops (NAS frames)
    species_check.py eval [--hold SID] [--json O]  OFFLINE: session-grouped CV + held-out
    species_check.py train [--thr T] [--hold SID]  write data/species/model.npz (gitignored)
    species_check.py sheet OUT --what label|bad    OFFLINE: a montage of chosen crops (debug)

THE CLASSIFIER (PURE, numpy only; ``species_of``): the box crop -> RGB (the colour order is an
explicit argument: live frames are BGR(A), the recordings RGB) -> a SIZE x SIZE block-mean
thumbnail -> ``features`` (joint RGB histograms of the whole box and of three bands, a 4 x 4
colour thumbnail, a saturation-weighted hue histogram, a 2 x 2 gradient-orientation histogram and
the box's width / height / detector score; 250 numbers) -> a softmax classifier with one ReLU
hidden layer of 64 units (``fit``, numpy Adam) over Poring, Lunatic, Drops, Pupa, Creamy and
``other`` (a box with no monster in the packets). The answer is the top class when its
probability is at least the model's threshold AND it is not ``other``; else None (ambiguous: read
the tag as before). A Creamy answer means "do not click" (or read the tag).

LABELS (packets are ground truth OFFLINE only, never a classifier input): the search_gap.py
conventions -- positions from packets, the frame at t shows the server at t - LAG_S, greedy
nearest-first matching of the box's feet (centre u, bottom v) to the projected monsters within
MATCH_PX, but with a PER-SPECIES feet offset (measured per session): a Creamy flies, its box's
bottom is ~31 px ABOVE its projected cell, the walkers' ~8-10 px below. (search_gap.py uses one
offset for every species, so its 40-px match misses most Creamy boxes: its "Creamy 11 %" is at
least partly a matching artefact -- not re-measured here.) A label is CLEAN when the match is
within CLEAN_PX, no other monster (alive, or dead within DEAD_S: the corpse lingers) projects
within UNIQUE_PX, and no box of the frame is "unsure" (a box with a monster 40-100 px away means
the frame's projection is off); a box with no monster within OTHER_PX is ``other``. Crops come
from the 5 Hz recordings: the frame with the detector's own timestamp (``exact``), or for the
rare classes (Creamy, Pupa) the nearest frame within NEAR_MS, the box shifted by the projected
motion between the two times (``near``). Training uses clean labels only, every class and every
(session, gid) individual weighted equally; the evaluation scores every labelled box.

MEASURED 2026-10-17 (34 hunt-flow sessions with detector boxes, 2026-10-16 11:08 .. 2026-10-17
08:58; 9679 crops; 8-fold session-grouped CV on 33 sessions + the held-out flow21 08:58 session,
never used for any choice): labelled detector boxes (clean / individuals) -- Poring 60326 (39710 /
803), Lunatic 37803 (28164 / 512), Drops 9649 (6520 / 128), Creamy 2313 (1533 / 132), Pupa 649
(539 / 8), other 14551; training crops Poring 2269, Lunatic 1759, Drops 449, Pupa 409, Creamy
1207 (286 exact), other 1083. Coverage = clean target crops accepted as a target (species
precision of the accepts 0.998-0.9993 in CV, 1.0 held-out, from 0.95 up). CV (4752 target
crops; 1738 Creamy-labelled, 1141 clean, ~124 individuals) | held-out (134 target crops; 107
Creamy-labelled, 66 clean, 7 individuals):
  thr 0.9    coverage 0.950 | 0.940   Creamy-labelled accepted 26 (clean 3) | 1 (clean 0)
  thr 0.99   coverage 0.897 | 0.888   Creamy-labelled accepted 12 (clean 1) | 1 (clean 0)
  thr 0.995  coverage 0.870 | 0.858   Creamy-labelled accepted  9 (clean 0) | 1 (clean 0)
  thr 0.999  coverage 0.782 | 0.776   Creamy-labelled accepted  7 (clean 0) | 0          <- DEFAULT
  thr 0.9995 coverage 0.737 | 0.739   Creamy-labelled accepted  7 (clean 0) | 0
  (a linear model on the same features: coverage 0.58 | 0.52 at thr 0.99, accepting 7 | 0)
Every Creamy-labelled accept at 0.999 was LOOKED AT: none is a Creamy sprite -- 5 are a target's
box with the Creamy beside it (a label error), 2 are a Creamy's TELEPORT pillar (white-blue
column; the server had already sent entity_vanish reason 3: no unit left to hit, read as
Lunatic). Also accepted at 0.999: boxes labelled "other" (37 | 2; the 22 looked at -- 20 from
the linear model's CV at 0.99, the 2 held-out -- were real monsters the packets placed > 100 px
away, and one teleport pillar), corpses (24 | 1, no unit), a target with a Creamy within 50 px of
its box (47 | 1 -- the click may land on the Creamy: keep the tag read when another box is that
near). The Poring War Recruiter NPC (159,371, looks like a Poring): 4 exact-frame boxes in two
sessions held out of training -> None (top class "other"); keep the NPC guards anyway. HONEST
LIMITS: 0 Creamy sprites accepted in ~131 individuals (CV + held-out) bounds the per-encounter
rate below ~2.3 % (95 %, rule of three), not lower; crops are JPEG q80 recordings, live frames
are raw (colour edges differ slightly); Pupa has 8 individuals (none held out); a call costs
~1.3-1.5 ms p50, 2.4 ms p99 on one core at nice 15 with the bot running (1280 x 720 frame + box,
RGB or BGRA).
Failure cases: flow20 05:55 04920-933939011771891.jpg (a teleport pillar -> Lunatic 1.0), flow21
08:58 06109-945164366734849.jpg (a Poring with a Creamy touching it -> Poring 1.0), flow21 08:32
06372-943670145140183.jpg (a grass box labelled Creamy -> Pupa 0.995: rejected at 0.999).
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import os
import random
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
REC_ROOT = Path("/mnt/poring-lab-datasets/hunt-recordings")
DEMO_ROOT = Path("/dev/shm/poring-lab-demo")
WORK = Path("/dev/shm/poring-lab-species")  # labels and crops: client pixels, RAM only
MODEL_PATH = ROOT / "data" / "species" / "model.npz"  # gitignored (client-derived, rule 4)
NS = 10**9

SPECIES = {1002: "Poring", 1063: "Lunatic", 1113: "Drops", 1008: "Pupa", 1018: "Creamy"}
TARGETS = ("Poring", "Lunatic", "Drops", "Pupa")  # prt_fild08's spawn table (farm0.TARGETS)
CLASSES = ("Poring", "Lunatic", "Drops", "Pupa", "Creamy", "other")
SIZE = 32  # the thumbnail side the features are computed on
DEFAULT_THR = 0.999  # the operating point (see MEASURED)
HIDDEN = 64


# --- the classifier (PURE) ------------------------------------------------------------------------


def to_rgb(img: Any, order: str) -> Any:
    """The first three channels in RGB order. ``order`` is the INPUT's order: "rgb" (the
    recordings, PIL, simplejpeg) or "bgr" (mss / X grabs, BGRA; the alpha is dropped)."""
    a = np.asarray(img)
    if a.ndim != 3 or a.shape[2] < 3:
        raise ValueError(f"expected H x W x 3|4, got {a.shape}")
    if order == "rgb":
        return a[..., :3]
    if order == "bgr":
        return a[..., 2::-1]
    raise ValueError(f"order must be 'rgb' or 'bgr', not {order!r}")


def crop_box(img: Any, box: Sequence[float], order: str) -> Any:
    """The box (x0, y0, x1, y1 in the image's pixels, clipped to it) as RGB."""
    a = np.asarray(img)
    h, w = a.shape[:2]
    x0, y0 = max(0, int(math.floor(box[0]))), max(0, int(math.floor(box[1])))
    x1, y1 = min(w, int(math.ceil(box[2]))), min(h, int(math.ceil(box[3])))
    if x1 - x0 < 2 or y1 - y0 < 2:
        raise ValueError(f"box {tuple(box)} is empty inside a {w} x {h} image")
    return to_rgb(a[y0:y1, x0:x1], order)


def thumbnail(rgb: Any, size: int = SIZE) -> Any:
    """Block-mean resize to size x size (float32, 0..255); a side shorter than ``size`` is first
    repeated (nearest) up to it."""
    a = np.asarray(rgb, dtype=np.float32)
    for ax in (0, 1):
        n = a.shape[ax]
        if n < size:
            a = np.take(a, (np.arange(size) * n) // size, axis=ax)
    for ax in (0, 1):
        n = a.shape[ax]
        edges = (np.arange(size) * n) // size
        cnt = np.diff(np.append(edges, n)).astype(np.float32)
        a = np.add.reduceat(a, edges, axis=ax)
        a = a / (cnt[:, None, None] if ax == 0 else cnt[None, :, None])
    return a


def _hist(q: Any, levels: int) -> Any:
    idx = (q[..., 0] * levels + q[..., 1]) * levels + q[..., 2]
    return np.bincount(idx.ravel(), minlength=levels**3).astype(np.float32) / idx.size


def features(thumb: Any, w: float, h: float, score: float) -> Any:
    """The feature vector of a SIZE x SIZE RGB thumbnail (``thumbnail``) and its box's width,
    height (client px) and detector score."""
    x = np.asarray(thumb, dtype=np.float32) / 255.0
    s = x.shape[0]
    q4 = np.minimum((x * 4).astype(np.int32), 3)
    q3 = np.minimum((x * 3).astype(np.int32), 2)
    b1, b2 = s // 3, (2 * s) // 3
    bands = [_hist(q3[a:b], 3) for a, b in ((0, b1), (b1, b2), (b2, s))]
    k = s // 4
    thumb4 = x.reshape(4, k, 4, k, 3).mean(axis=(1, 3)).ravel()
    mx, mn = x.max(-1), x.min(-1)
    sat = mx - mn
    r, g, b = x[..., 0], x[..., 1], x[..., 2]
    hue = np.arctan2(math.sqrt(3) * (g - b), 2 * r - g - b)  # -pi..pi
    hb = np.minimum(((hue + math.pi) / (2 * math.pi) * 12).astype(np.int32), 11)
    hue_h = np.bincount(hb.ravel(), weights=sat.ravel(), minlength=12) / sat.size
    sv = np.concatenate([
        np.bincount(np.minimum((sat * 4).astype(np.int32), 3).ravel(), minlength=4),
        np.bincount(np.minimum((mx * 4).astype(np.int32), 3).ravel(), minlength=4),
    ]) / sat.size  # fmt: skip
    grey = x.mean(-1)
    gx = np.zeros_like(grey)
    gy = np.zeros_like(grey)
    gx[:, 1:-1] = grey[:, 2:] - grey[:, :-2]
    gy[1:-1] = grey[2:] - grey[:-2]
    mag = np.hypot(gx, gy)
    ob = np.minimum(((np.arctan2(gy, gx) + math.pi) / (2 * math.pi) * 8).astype(np.int32), 7)
    half = s // 2
    hog = []
    for ys in (slice(0, half), slice(half, s)):
        for xs in (slice(0, half), slice(half, s)):
            hog.append(np.bincount(ob[ys, xs].ravel(), weights=mag[ys, xs].ravel(), minlength=8))
    hog_v = np.concatenate(hog)
    hog_v = hog_v / (hog_v.sum() + 1e-6)
    geo = np.array([w / 40.0, h / 40.0, w / max(h, 1.0), score, mag.mean()], dtype=np.float32)
    return np.concatenate([_hist(q4, 4), *bands, thumb4, hue_h, sv, hog_v, geo]).astype(np.float32)


def probabilities(f: Any, model: Mapping[str, Any]) -> Any:
    """Class probabilities (model["classes"] order) of one feature vector or a batch."""
    z = (np.atleast_2d(f) - model["mean"]) / model["std"]
    if "W1" in model:  # the hidden layer
        z = np.maximum(z @ model["W1"] + model["b1"], 0)
    logit = z @ model["W"].T + model["b"]
    logit -= logit.max(axis=1, keepdims=True)
    p = np.exp(logit)
    return p / p.sum(axis=1, keepdims=True)


def decide(p: Any, classes: Sequence[str], thr: float) -> tuple[str | None, float]:
    """The top class and its probability; None when it is ``other`` or below ``thr``."""
    k = int(np.argmax(p))
    conf = float(p[k])
    name = str(classes[k])
    return (None if name == "other" or conf < thr else name), conf


def species_of(img: Any, model: Mapping[str, Any], box: Sequence[float] | None = None, *,
               order: str, score: float = 0.8, thr: float | None = None
               ) -> tuple[str | None, float]:  # fmt: skip
    """PURE: (species, confidence) of a monster box. ``img`` is a whole frame with ``box`` = the
    detector's (x0, y0, x1, y1[, score, ...]) in its pixels, or (box None) the box's crop itself.
    ``order`` ("rgb" | "bgr") is the input's colour order -- no default on purpose. species is a
    name in TARGETS, "Creamy" (a non-target: never click), or None = ambiguous (read the tag).
    ``thr`` defaults to the model's operating point."""
    if box is None:
        rgb = to_rgb(img, order)
        h, w = rgb.shape[:2]
    else:
        rgb = crop_box(img, box, order)
        w, h = float(box[2]) - float(box[0]), float(box[3]) - float(box[1])
        if len(box) > 4 and isinstance(box[4], (int, float)):
            score = float(box[4])
    f = features(thumbnail(rgb), float(w), float(h), score)
    p = probabilities(f, model)[0]
    return decide(p, model["classes"], float(model["thr"] if thr is None else thr))


def load_model(path: Path = MODEL_PATH) -> dict[str, Any]:
    with np.load(path, allow_pickle=False) as z:
        m = {k: z[k] for k in z.files}
    m["classes"] = tuple(str(c) for c in m["classes"])
    m["thr"] = float(m["thr"])
    return m


def save_model(model: Mapping[str, Any], path: Path = MODEL_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.npz")
    np.savez(tmp, **{k: np.asarray(v) for k, v in model.items()})
    tmp.replace(path)


def fit(x: Any, y: Any, n_classes: int, weights: Any | None = None, hidden: int = HIDDEN,
        l2: float = 1e-4, steps: int = 800, lr: float = 0.01, seed: int = 0
        ) -> dict[str, Any]:  # fmt: skip
    """A softmax classifier on standardised features, full-batch Adam with L2: one ReLU hidden
    layer of ``hidden`` units (0 = multinomial logistic regression). ``weights`` per sample."""
    x = np.asarray(x, dtype=np.float32)
    y = np.asarray(y, dtype=np.int64)
    mean = x.mean(0)
    std = x.std(0) + 1e-4
    z = (x - mean) / std
    n, d = z.shape
    wts = np.ones(n, dtype=np.float32) if weights is None else np.asarray(weights, np.float32)
    wts = (wts / wts.sum()).astype(np.float32)
    onehot = np.eye(n_classes, dtype=np.float32)[y]
    rng = np.random.default_rng(seed)
    if hidden:
        prm = {"W1": rng.normal(0, math.sqrt(2 / d), (d, hidden)).astype(np.float32),
               "b1": np.zeros(hidden, np.float32),
               "W": rng.normal(0, math.sqrt(2 / hidden), (n_classes, hidden)).astype(np.float32),
               "b": np.zeros(n_classes, np.float32)}  # fmt: skip
    else:
        prm = {"W": rng.normal(0, 0.01, (n_classes, d)).astype(np.float32),
               "b": np.zeros(n_classes, np.float32)}  # fmt: skip
    mom = {k: np.zeros_like(v) for k, v in prm.items()}
    vel = {k: np.zeros_like(v) for k, v in prm.items()}
    for t in range(1, steps + 1):
        h = np.maximum(z @ prm["W1"] + prm["b1"], 0) if hidden else z
        logit = h @ prm["W"].T + prm["b"]
        logit -= logit.max(1, keepdims=True)
        p = np.exp(logit)
        p /= p.sum(1, keepdims=True)
        g = (p - onehot) * wts[:, None]
        grad = {"W": g.T @ h + l2 * prm["W"], "b": g.sum(0)}
        if hidden:
            gh = (g @ prm["W"]) * (h > 0)
            grad["W1"] = z.T @ gh + l2 * prm["W1"]
            grad["b1"] = gh.sum(0)
        for k, gr in grad.items():
            mom[k] = 0.9 * mom[k] + 0.1 * gr
            vel[k] = 0.999 * vel[k] + 0.001 * gr * gr
            prm[k] -= lr * (mom[k] / (1 - 0.9**t)) / (np.sqrt(vel[k] / (1 - 0.999**t)) + 1e-8)
    return {"mean": mean, "std": std, **prm}


# --- offline: labels from packets -----------------------------------------------------------------

LAG_S = 0.5
MATCH_PX = 40.0
CALIB_PX = 60.0
UNIQUE_PX = 50.0  # no other monster's expected box bottom this near -> a clean label
CLEAN_PX = 20.0  # ... and the match itself this near (median 5-10 px; the tail is wrong boxes)
OTHER_PX = 100.0  # no monster this near -> "other"
DEAD_S = 4.0  # a killed monster's corpse is drawn this long
NEAR_MS = 70.0
DEFAULT_OFF = {1018: (0.5, -31.5)}  # else (0, 9): measured flow12 / flow21
AOI = 14


def _job_timeline(events: Sequence[Mapping[str, Any]]) -> dict[int, tuple[list[int], list[int]]]:
    tl: dict[int, tuple[list[int], list[int]]] = {}
    for e in events:
        if e.get("type") == "entity_appear" and e.get("objtype") == 5:
            ts, js = tl.setdefault(int(e["gid"]), ([], []))
            ts.append(int(e["t_mono_ns"]))
            js.append(int(e.get("job") or -1))
    return tl


def _job_at(tl: Mapping[int, tuple[list[int], list[int]]], g: int, t: int) -> int:
    ts, js = tl.get(g, ([], []))
    if not ts:
        return -1
    i = bisect.bisect_right(ts, t) - 1
    return js[max(i, 0)]


def rec_frames(sid: str) -> list[int]:
    d = REC_ROOT / sid / "frames"
    return sorted(int(n[:-4].split("-")[1]) for n in os.listdir(d) if n.endswith(".jpg"))


def _cached_gat(g: Any) -> Any:
    """The same GAT with its altitude grid computed once (Gat.altitude rebuilds it per call:
    ~4 ms of every projection)."""
    import dataclasses
    import functools

    from poring_dataset.gat import Gat

    class _Cached(Gat):
        @functools.cached_property
        def altitude(self) -> Any:  # type: ignore[override]
            return Gat.altitude.fget(self)  # type: ignore[attr-defined]

    return _Cached(**{f.name: getattr(g, f.name) for f in dataclasses.fields(g)})


def label_session(sid: str) -> list[dict[str, Any]]:
    """Every detector monster box of a session, labelled from packets (see the module doc)."""
    from drop_blobs import Projector
    from search_gap import build_world, greedy_match, load

    d, man, events, frames = load(sid)
    world = build_world(events)
    tl = _job_timeline(events)
    proj = Projector(man.get("map", "prt_fild08"))
    proj.gat = _cached_gat(proj.gat)
    rec = rec_frames(sid)
    lag = int(LAG_S * NS)
    dead_ns = int(DEAD_S * NS)
    spans: dict[int, list[tuple[int, int | None, int]]] = world.lives

    # every life of a monster: alive [a, b), then a corpse [b, b + DEAD_S); bucketed by second
    t_first = int(frames[0][0]) - lag if frames else 0
    t_last = int(frames[-1][0]) if frames else 0
    buckets: dict[int, list[tuple[int, int, int, int]]] = defaultdict(list)
    for g, ls in spans.items():
        if g not in world.mobs:
            continue
        for a, b, reason in ls:
            bb = t_last if b is None else b
            e = bb + dead_ns if b is not None and reason == 1 else bb
            for k in range(max(a, t_first) // NS, min(e, t_last) // NS + 1):
                buckets[k].append((a, bb if b is not None else 2**62, e if b is not None
                                   else 2**62, g))  # fmt: skip

    def pool(td: int, here: tuple[float, float]) -> list[tuple[int, tuple[float, float], bool]]:
        seen: dict[int, bool] = {}
        for a, b, e, g in buckets.get(td // NS, ()):
            if a <= td < b:
                seen[g] = False
            elif b <= td < e and g not in seen:
                seen[g] = True
        out = []
        for g, st in seen.items():
            p = world.mobs[g].at(td)
            if p is None or max(abs(p[0] - here[0]), abs(p[1] - here[1])) > AOI + 0.5:
                continue
            out.append((g, p, st))
        return out

    def expected(here: tuple[float, float], mobs: Sequence[Any], td: int,
                 off: Mapping[int, tuple[float, float]]) -> list[tuple[float, float]]:  # fmt: skip
        if not mobs:
            return []
        px = proj.project(here, [p for _g, p, _d in mobs])
        out = []
        for (g, _p, _dd), (u, v) in zip(mobs, px, strict=True):
            o = off.get(_job_at(tl, g, td), (0.0, 9.0))
            out.append((float(u) + o[0], float(v) + o[1]))
        return out

    # pass 1: the per-species feet offset of this session
    samples = []
    for tf, boxes in frames[:: max(1, len(frames) // 3000)]:
        td = tf - lag
        here = world.gm.at(td)
        if here is None or not boxes:
            continue
        mobs = [m for m in pool(td, here) if not m[2]]
        pts = expected(here, mobs, td, DEFAULT_OFF)
        feet = [((b[0] + b[2]) / 2, b[3]) for b in boxes]
        for i, (j, _dd) in greedy_match(pts, feet, CALIB_PX).items():
            job = _job_at(tl, mobs[i][0], td)
            o = DEFAULT_OFF.get(job, (0.0, 9.0))
            samples.append((job, feet[j][0] - pts[i][0] + o[0], feet[j][1] - pts[i][1] + o[1]))
    off: dict[int, tuple[float, float]] = {}
    for job in {s[0] for s in samples}:
        du = [s[1] for s in samples if s[0] == job]
        dv = [s[2] for s in samples if s[0] == job]
        if len(du) >= 20:
            off[job] = (float(np.median(du)), float(np.median(dv)))
    for job, o in DEFAULT_OFF.items():
        off.setdefault(job, o)

    # pass 2: label every box
    rows: list[dict[str, Any]] = []
    for tf, boxes in frames:
        if not boxes:
            continue
        td = tf - lag
        here = world.gm.at(td)
        if here is None:
            continue
        i_r = bisect.bisect_left(rec, tf)
        cand = [rec[k] for k in (i_r - 1, i_r) if 0 <= k < len(rec)]
        t_rec = min(cand, key=lambda t: abs(t - tf)) if cand else None
        mobs = pool(td, here)
        pts = expected(here, mobs, td, off)
        feet = [((b[0] + b[2]) / 2, b[3]) for b in boxes]
        alive = [k for k, m in enumerate(mobs) if not m[2]]
        m = greedy_match([pts[k] for k in alive], feet, MATCH_PX)
        by_box = {j: (alive[i], dd) for i, (j, dd) in m.items()}
        # a corpse can take a box no live monster took
        dead = [k for k, mm in enumerate(mobs) if mm[2]]
        free = [j for j in range(len(boxes)) if j not in by_box]
        md = greedy_match([pts[k] for k in dead], [feet[j] for j in free], MATCH_PX)
        for i, (jj, dd) in md.items():
            by_box[free[jj]] = (dead[i], dd)
        for j, b in enumerate(boxes):
            dists = [math.dist(p, feet[j]) for p in pts]
            row: dict[str, Any] = {
                "sid": sid, "t": tf, "t_rec": t_rec,
                "dt_ms": None if t_rec is None else round((t_rec - tf) / 1e6, 1),
                "box": [round(float(c), 1) for c in b[:4]], "score": float(b[4]),
            }  # fmt: skip
            if j in by_box:
                k, dd = by_box[j]
                g, pos, is_dead = mobs[k]
                job = _job_at(tl, g, td)
                others = [x for kk, x in enumerate(dists) if kk != k]
                creamy = [x for kk, x in enumerate(dists)
                          if kk != k and _job_at(tl, mobs[kk][0], td) == 1018]  # fmt: skip
                row.update({
                    "label": SPECIES.get(job, f"job{job}"), "job": job, "gid": g,
                    "dead": is_dead, "dist": round(dd, 1),
                    "nn_other": round(min(others), 1) if others else None,
                    "creamy_near": round(min(creamy), 1) if creamy else None,
                    "mob_moving": world.mobs[g].moving(td),
                })  # fmt: skip
                row["clean"] = (not is_dead and dd <= CLEAN_PX
                                and (not others or min(others) > UNIQUE_PX))  # fmt: skip
                if t_rec is not None and t_rec != tf:  # the box moved by the projected motion
                    td2 = t_rec - lag
                    here2, p2 = world.gm.at(td2), world.mobs[g].at(td2)
                    if here2 is not None and p2 is not None:
                        a1 = proj.project(here, [pos])[0]
                        a2 = proj.project(here2, [p2])[0]
                        row["shift"] = [round(float(a2[0] - a1[0]), 1),
                                        round(float(a2[1] - a1[1]), 1)]  # fmt: skip
            else:
                near = min(dists) if dists else None
                row.update({"label": "other" if near is None or near > OTHER_PX else "unsure",
                            "nn_other": None if near is None else round(near, 1),
                            "clean": near is None or near > OTHER_PX})  # fmt: skip
            rows.append(row)
        # a box no monster could be matched to, with one ~45-60 px away, means this frame's
        # projection is off (the GM walking, the lag): no label of the frame is clean
        n_unsure = sum(r_["label"] == "unsure" for r_ in rows[len(rows) - len(boxes) :])
        for r_ in rows[len(rows) - len(boxes) :]:
            r_["frame_unsure"] = n_unsure
            r_["clean"] = bool(r_["clean"]) and n_unsure == 0
    offs = ", ".join(f"{SPECIES.get(k, k)} {v[0]:+.1f},{v[1]:+.1f}" for k, v in sorted(off.items()))
    print(f"{sid}: offsets {offs}", file=sys.stderr)
    return rows


def cmd_labels(a: argparse.Namespace) -> int:
    (WORK / "labels").mkdir(parents=True, exist_ok=True)
    for sid in a.sids:
        out = WORK / "labels" / f"{sid}.jsonl"
        if out.exists() and not a.force:
            continue
        t0 = time.monotonic()
        rows = label_session(sid)
        tmp = out.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(r) + "\n" for r in rows))
        tmp.replace(out)
        c = Counter((r["label"], r.get("clean"), r["dt_ms"] == 0) for r in rows)
        print(f"{sid}: {len(rows)} boxes in {time.monotonic() - t0:.0f} s; "
              + ", ".join(f"{k[0]}{'' if k[1] else '~'}{'=' if k[2] else ''} {v}"
                          for k, v in sorted(c.items(), key=str)), file=sys.stderr)  # fmt: skip
    return 0


# --- offline: crops -------------------------------------------------------------------------------

RARE = ("Creamy", "Pupa")  # also cut from the near frames (Drops has enough exact ones)


def select_rows(rows: Sequence[dict[str, Any]], n_exact: int, seed: int) -> list[dict[str, Any]]:
    """Which labelled boxes to cut: every clean box of a sampled set of EXACT frames, plus every
    clean RARE-class box (exact, or near with its shift), plus the dirty boxes next to a Creamy
    (the eval's risk cases). Corpses (dead) are kept for the eval."""
    by_t: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if r["t_rec"] is not None:
            by_t[r["t"]].append(r)
    exact = [t for t, rs in by_t.items() if rs[0]["dt_ms"] == 0]
    rng = random.Random(seed)
    pick = set(rng.sample(exact, min(n_exact, len(exact))))
    out = []
    for t, rs in by_t.items():
        for r in rs:
            if r["label"] == "unsure":
                continue
            ok_near = r["dt_ms"] == 0 or (abs(r["dt_ms"]) <= NEAR_MS and "shift" in r
                                         and math.hypot(*r["shift"]) <= 25)  # fmt: skip
            sampled = t in pick and r["dt_ms"] == 0
            rare = r["label"] in RARE or (r.get("creamy_near") or 1e9) <= UNIQUE_PX
            if sampled or (ok_near and rare):
                out.append(r)
    return out


def cmd_crops(a: argparse.Namespace) -> int:
    from drop_blobs import read_rgb

    (WORK / "crops").mkdir(parents=True, exist_ok=True)
    for sid in a.sids:
        out = WORK / "crops" / f"{sid}.npz"
        if out.exists() and not a.force:
            continue
        rows = [json.loads(x) for x in (WORK / "labels" / f"{sid}.jsonl").read_text().splitlines()]
        sel = select_rows(rows, a.n_exact, a.seed)
        by_rec: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for r in sel:
            by_rec[int(r["t_rec"])].append(r)
        names = {int(n[:-4].split("-")[1]): n
                 for n in os.listdir(REC_ROOT / sid / "frames") if n.endswith(".jpg")}  # fmt: skip
        thumbs, feats, meta = [], [], []
        t0 = time.monotonic()
        for t_rec in sorted(by_rec):
            img = read_rgb(REC_ROOT / sid / "frames" / names[t_rec])
            for r in by_rec[t_rec]:
                bx = list(r["box"])
                if r["dt_ms"] != 0:
                    du, dv = r["shift"]
                    bx = [bx[0] + du, bx[1] + dv, bx[2] + du, bx[3] + dv]
                try:
                    rgb = crop_box(img, bx, "rgb")
                except ValueError:
                    continue
                th = thumbnail(rgb)
                thumbs.append(th.astype(np.uint8))
                feats.append(features(th, bx[2] - bx[0], bx[3] - bx[1], r["score"]))
                meta.append({**r, "frame": names[t_rec]})
        tmp = out.with_suffix(".tmp.npz")
        np.savez(tmp, thumbs=np.asarray(thumbs, np.uint8), feats=np.asarray(feats, np.float32),
                 meta=np.asarray([json.dumps(m) for m in meta]))  # fmt: skip
        tmp.replace(out)
        c = Counter(m["label"] + ("" if m["clean"] else "~") + ("" if m["dt_ms"] == 0 else ">")
                    for m in meta)  # fmt: skip
        print(f"{sid}: {len(by_rec)} frames, {len(meta)} crops in {time.monotonic() - t0:.0f} s; "
              f"{dict(sorted(c.items()))}", file=sys.stderr)  # fmt: skip
    return 0


# --- offline: train / evaluate -------------------------------------------------------------------


def load_crops(sids: Sequence[str] | None = None) -> tuple[Any, Any, list[dict[str, Any]]]:
    th, fs, meta = [], [], []
    for p in sorted((WORK / "crops").glob("*.npz")):
        if sids is not None and p.stem not in sids:
            continue
        with np.load(p) as z:
            if not len(z["meta"]):
                continue
            th.append(z["thumbs"])
            fs.append(z["feats"])
            ms = [json.loads(str(m)) for m in z["meta"]]
        lab = WORK / "labels" / f"{p.stem}.jsonl"
        if lab.exists():  # the CURRENT labels (a relabel needs no NAS reads)
            cur = {(r["t"], tuple(r["box"])): r for r in map(json.loads, lab.open())}
            ms = [{**m, **cur.get((m["t"], tuple(m["box"])), {})} for m in ms]
        meta += ms
    return np.concatenate(th), np.concatenate(fs), meta


def train_rows(meta: Sequence[Mapping[str, Any]]) -> list[int]:
    """The rows a model learns from: clean labels of the six classes, live monsters only."""
    return [i for i, m in enumerate(meta) if m["clean"] and m["label"] in CLASSES
            and not m.get("dead")]  # fmt: skip


def train_model(feats: Any, meta: Sequence[Mapping[str, Any]], idx: Sequence[int],
                l2: float, thr: float, hidden: int = HIDDEN) -> dict[str, Any]:  # fmt: skip
    """Balanced: every class weighs the same in total, and within a class every (session, gid)
    individual weighs the same (a monster that stood in view for a minute is one sample)."""
    y = np.array([CLASSES.index(meta[i]["label"]) for i in idx])
    ind = [(meta[i]["sid"], meta[i].get("gid", meta[i]["t"])) for i in idx]
    n_ind = Counter(ind)
    w = np.array([1.0 / n_ind[k] for k in ind])
    for c in range(len(CLASSES)):
        s = w[y == c].sum()
        if s > 0:
            w[y == c] /= s
    m = fit(feats[idx], y, len(CLASSES), weights=w, hidden=hidden, l2=l2)
    m["classes"] = np.array(CLASSES)
    m["thr"] = np.float32(thr)
    return m


def eval_rows(meta: Sequence[Mapping[str, Any]]) -> list[int]:
    """What a held-out session is scored on: every labelled box except "unsure" ones (corpses
    and boxes next to another monster included: the live bot meets them)."""
    return [i for i, m in enumerate(meta) if m["label"] != "unsure"]


def sweep(p: Any, meta: Sequence[Mapping[str, Any]], idx: Sequence[int],
          thrs: Sequence[float]) -> list[dict[str, Any]]:  # fmt: skip
    """Per threshold: target coverage / accuracy, and every NON-TARGET accepted as a target."""
    out = []
    for thr in thrs:
        acc: Counter[str] = Counter()
        tot: Counter[str] = Counter()
        bad: list[dict[str, Any]] = []
        for k, i in enumerate(idx):
            m = meta[i]
            name, conf = decide(p[k], CLASSES, thr)
            lab = m["label"] + (" corpse" if m.get("dead") else "")
            if m["label"] in TARGETS and not m.get("dead") and m.get("clean"):
                tot["target"] += 1
                if name in TARGETS:
                    acc["target_accepted"] += 1
                    acc["target_right" if name == m["label"] else "target_wrong_species"] += 1
            if m["label"] in TARGETS and not m.get("dead") and not m.get("clean"):
                tot["target_crowded"] += 1
                acc["target_crowded_accepted"] += name in TARGETS
            if name in TARGETS and (m["label"] not in TARGETS or m.get("dead")
                                    or (m.get("creamy_near") or 1e9) <= UNIQUE_PX):  # fmt: skip
                why = lab if m["label"] not in TARGETS or m.get("dead") else lab + " +Creamy near"
                why += "" if m.get("clean") else "?"  # "?": a doubtful label (look at it)
                acc["nontarget_accept:" + why] += 1
                bad.append({"frame": m["frame"], "sid": m["sid"], "label": why, "as": name,
                            "conf": round(conf, 3), "box": m["box"],
                            "dt_ms": m["dt_ms"], "gid": m.get("gid")})  # fmt: skip
            if m["label"] == "Creamy" and not m.get("dead"):
                tot["creamy"] += 1
                acc["creamy_said_creamy"] += name == "Creamy"
        out.append({"thr": thr, "tot": dict(tot), "acc": dict(acc), "bad": bad,
                    "coverage": round(acc["target_accepted"] / max(1, tot["target"]), 3),
                    "precision_species": round(acc["target_right"]
                                               / max(1, acc["target_accepted"]), 4)})  # fmt: skip
    return out


THRS = (0.5, 0.8, 0.9, 0.95, 0.98, 0.99, 0.995, 0.998, 0.999, 0.9995)


def per_class(p: Any, meta: Sequence[Mapping[str, Any]], idx: Sequence[int]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for c in CLASSES:
        ks = [k for k, i in enumerate(idx) if meta[i]["label"] == c and meta[i]["clean"]
              and not meta[i].get("dead")]  # fmt: skip
        if ks:
            pred = Counter(CLASSES[int(np.argmax(p[k]))] for k in ks)
            out[c] = {"n": len(ks), "top1": round(pred[c] / len(ks), 3),
                      "as": dict(pred.most_common())}  # fmt: skip
    return out


def cmd_eval(a: argparse.Namespace) -> int:
    _th, feats, meta = load_crops()
    sids = sorted({m["sid"] for m in meta})
    tr_all = train_rows(meta)
    rest = [s for s in sids if s != a.hold]
    folds = [set(rest[k :: a.folds]) for k in range(a.folds)]
    res: dict[str, Any] = {"cv": {}, "hold": None}
    # session-grouped cross-validation on every session but the held-out one (picks the
    # threshold): a session's crops are scored by a model that never saw that session
    P = np.zeros((len(meta), len(CLASSES)), dtype=np.float32)
    done = np.zeros(len(meta), dtype=bool)
    for fold in folds:
        tr = [i for i in tr_all if meta[i]["sid"] not in fold and meta[i]["sid"] != a.hold]
        te = [i for i in eval_rows(meta) if meta[i]["sid"] in fold]
        if not te:
            continue
        m = train_model(feats, meta, tr, a.l2, DEFAULT_THR, a.hidden)
        P[te] = probabilities(feats[te], m)
        done[te] = True
    idx = [i for i in eval_rows(meta) if done[i]]
    res["cv"] = {"per_class": per_class(P[idx], meta, idx),
                   "sweep": sweep(P[idx], meta, idx, THRS)}  # fmt: skip
    if a.hold:
        tr = [i for i in tr_all if meta[i]["sid"] != a.hold]
        te = [i for i in eval_rows(meta) if meta[i]["sid"] == a.hold]
        m = train_model(feats, meta, tr, a.l2, DEFAULT_THR, a.hidden)
        ph = probabilities(feats[te], m)
        res["hold"] = {"sid": a.hold, "per_class": per_class(ph, meta, te),
                       "sweep": sweep(ph, meta, te, THRS)}  # fmt: skip
    for k in ("cv", "hold"):
        if not res[k]:
            continue
        print(f"== {k} {res[k].get('sid', '')}")
        for c, v in res[k]["per_class"].items():
            print(f"  {c:8s} n={v['n']:5d} top1={v['top1']:.3f} {v['as']}")
        for row in res[k]["sweep"]:
            na = {kk.split(":", 1)[1]: v for kk, v in row["acc"].items()
                  if kk.startswith("nontarget_accept")}  # fmt: skip
            print(
                f"  thr {row['thr']:.4f} cov {row['coverage']:.3f} "
                f"species-prec {row['precision_species']:.4f} "
                f"doubtful-label targets {row['acc'].get('target_crowded_accepted', 0)}/"
                f"{row['tot'].get('target_crowded', 0)} "
                f"creamy->Creamy {row['acc'].get('creamy_said_creamy', 0)}/"
                f"{row['tot'].get('creamy', 0)} NON-TARGET ACCEPTS {na}"
            )
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1))
        hold_idx = [i for i in eval_rows(meta) if meta[i]["sid"] == a.hold] if a.hold else []
        np.savez(Path(a.json).with_suffix(".npz"), cv_idx=np.asarray(idx), cv_p=P[idx],
                 hold_idx=np.asarray(hold_idx, dtype=np.int64),
                 hold_p=ph if a.hold else np.zeros((0, len(CLASSES))))  # fmt: skip
    return 0


def cmd_train(a: argparse.Namespace) -> int:
    _th, feats, meta = load_crops()
    tr = [i for i in train_rows(meta) if meta[i]["sid"] != a.hold]
    m = train_model(feats, meta, tr, a.l2, a.thr, a.hidden)
    m["trained_on"] = np.array(sorted({meta[i]["sid"] for i in tr}))
    save_model(m, Path(a.model))
    print(
        f"wrote {a.model}: {len(tr)} crops, thr {a.thr}, "
        f"{dict(Counter(meta[i]['label'] for i in tr))}"
    )
    return 0


def cmd_sheet(a: argparse.Namespace) -> int:
    from PIL import Image

    th, _f, meta = load_crops()
    rows = json.loads(Path(a.json).read_text())[a.part]["sweep"] if a.json else []
    want: list[int] = []
    if a.what == "label":
        want = [i for i, m in enumerate(meta) if m["label"] == a.label and m["clean"]]
    elif rows:
        bad = next(r for r in rows if abs(r["thr"] - a.thr) < 1e-9)["bad"]
        keys = {(b["frame"], tuple(b["box"])) for b in bad}
        want = [i for i, m in enumerate(meta) if (m["frame"], tuple(m["box"])) in keys]
    want = want[: a.n]
    cols = 16
    sheet = np.zeros((((len(want) + cols - 1) // cols) * (SIZE * 2 + 2), cols * (SIZE * 2 + 2),
                      3), np.uint8)  # fmt: skip
    for k, i in enumerate(want):
        r_, c_ = divmod(k, cols)
        big = np.repeat(np.repeat(th[i], 2, 0), 2, 1)
        sheet[r_ * (SIZE * 2 + 2): r_ * (SIZE * 2 + 2) + SIZE * 2,
              c_ * (SIZE * 2 + 2): c_ * (SIZE * 2 + 2) + SIZE * 2] = big  # fmt: skip
        print(k, meta[i]["sid"], meta[i]["frame"], meta[i]["label"], meta[i]["box"])
    Image.fromarray(sheet).save(a.out)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("labels")
    p.add_argument("sids", nargs="+")
    p.add_argument("--force", action="store_true")
    p = sp.add_parser("crops")
    p.add_argument("sids", nargs="+")
    p.add_argument("--n-exact", type=int, default=200)
    p.add_argument("--seed", type=int, default=20261017)
    p.add_argument("--force", action="store_true")
    for name in ("eval", "train"):
        p = sp.add_parser(name)
        p.add_argument("--hold", default=None)
        p.add_argument("--l2", type=float, default=1e-4)
        p.add_argument("--hidden", type=int, default=HIDDEN, help="0 = linear")
        if name == "eval":
            p.add_argument("--folds", type=int, default=8)
            p.add_argument("--json", default=None)
        else:
            p.add_argument("--thr", type=float, default=DEFAULT_THR)
            p.add_argument("--model", default=str(MODEL_PATH))
    p = sp.add_parser("sheet")
    p.add_argument("out")
    p.add_argument("--what", choices=("label", "bad"), default="label")
    p.add_argument("--label", default="Creamy")
    p.add_argument("--json", default=None)
    p.add_argument("--part", default="hold")
    p.add_argument("--thr", type=float, default=DEFAULT_THR)
    p.add_argument("--n", type=int, default=128)
    a = ap.parse_args()
    return {"labels": cmd_labels, "crops": cmd_crops, "eval": cmd_eval, "train": cmd_train,
            "sheet": cmd_sheet}[a.cmd](a)  # fmt: skip


if __name__ == "__main__":
    raise SystemExit(main())
