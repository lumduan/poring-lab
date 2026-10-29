#!/usr/bin/env python3
"""FLOOR ITEMS on gef_fild10: the FIT measurement of the items' drawn ANCHOR and fit floor
T_item (docs/planning/gef10-detector.md section 8, PROPOSED 2026-10-25 20:51:49 ICT, 3e31b01,
before this was built).

    gef10_items.py sprites --out JSON                 the item sprites' native extents (1e)
    gef10_items.py measure PART... --offset-ms MS --out JSON
                                                      8's anchor and T_item, FIT parts only
    ROUND 3 (docs/planning/gef10-round3.md, one pooled `item` class):
    gef10_items.py freeze --measure JSON --rows JSON --out PARAMS     the anchor + T_item frozen
    gef10_items.py label PART... --params PARAMS --offset-ms MS --out JSON   TRAIN labels
    gef10_items.py g2 PART... --params PARAMS --offset-ms MS --out JSON      G2 on TEST3 only
    gef10_items.py pack PART... --rows LABEL_ROWS --offset-ms MS --out JSON  the blind pack

The rule (8): an item is LABELLED on a frame at t when its floor_item_appear + 2.2 s <= t < its
vanish (item-class.md 8a's frozen D_APPEAR / D_GONE), on the monsters' candidate frames (our
character still: map_labels.RecSession). Its cell = (x + OX[sub_x], y + OY[sub_y]) (item-class.md
8a's frozen sub-cell table), projected like a monster's anchor; its BOX = its own client sprite
(one ACT frame) drawn by the monsters' billboard rule (render.predict_sprite) at that point, plus
the ANCHOR measured here. A SAMPLE (8's measurement): aged >= 2.5 s and >= 1.0 s before its
vanish, its predicted box clear of our self box (+ 4 px), our HP / SP bar (target-items.md 10.3),
every unit's generic box (60 px wide, 100 px up to 6 px down at tw and tw - 0.5 s; target-items.md
3d), every other present item's box and every model's projected box, and >= 30 px inside the
frame and from every UI window. Each sample's best masked-NCC offset within +-10 px of the
unanchored prediction: the ANCHOR = the pooled median (dx, dy) (>= 12 samples, else STOP),
T_item = the pooled 5th percentile of the samples' NCC whose fit is not at the search edge.

OFFLINE ONLY (ADR-0007): packets, the recorder's PNG shards (read-only), the client's item sprites
and name table decoded into /dev/shm (client-derived, never committed). No GPU, no client. TEST is
refused (map_labels' GEF10 spec: watch cells 11-14, s7, s8).
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import item_labels as il  # noqa: E402
import label_check  # noqa: E402
import map_labels as ml  # noqa: E402
import orc_camera_check as occ  # noqa: E402
import orc_labels_fix as olf  # noqa: E402
import qa_export  # noqa: E402

from poring_dataset.render import (  # noqa: E402
    Actor,
    SpritePrediction,
    SpriteSheet,
    anchor_and_depth,
    predict_sprite,
)
from poring_dataset.sprites import parse_act, parse_spr  # noqa: E402

Box = tuple[float, float, float, float]
ITEM_DIR = ml.G10 / "items" / "data" / "sprite" / "아이템"
RESNAME = ml.G10 / "grf" / "data" / "idnum2itemresnametable.txt"
OX = {3: -0.189, 6: 0.0, 9: 0.185, 12: 0.376}  # item-class.md 8a (frozen 2026-10-23)
OY = {3: -0.210, 6: 0.0, 9: 0.173, 12: 0.329}
NS = 1_000_000_000
D_APPEAR_NS, D_GONE_NS = int(2.2 * NS), int(0.6 * NS)  # item-class.md 8a
AGE_MIN_NS, BEFORE_VANISH_NS = int(2.5 * NS), int(1.0 * NS)  # 8: a sample's margins
SELF_W, SELF_H, SELF_PAD = 34.0, 74.0, 4.0  # labels v2's self box + 4 px
BAR = (-36.0, 0.0, 36.0, 24.0)  # target-items.md 10.3: our HP / SP bar around our feet
UNIT_BOX = (-30.0, -100.0, 30.0, 6.0)  # target-items.md 3d: any unit's generic box
UNIT_BACK_NS = 500_000_000  # ... at tw and tw - 0.5 s (frames lag; the unit may have moved)
MARGIN_PX = 30.0  # inside the frame and from every UI window
R_MEASURE = 10  # the anchor's search (+-px)
MIN_SAMPLES = 12
T_ITEM_PERCENTILE = 5.0


# --- pure parts --------------------------------------------------------------------------------


def parse_resnames(raw: bytes) -> dict[int, str]:
    """The client's ``idnum2itemresnametable.txt`` (CP949): ``id#resname#`` lines."""
    out: dict[int, str] = {}
    for line in raw.decode("cp949", errors="replace").splitlines():
        parts = line.split("#")
        if len(parts) >= 2 and parts[0].strip().isdigit() and parts[1].strip():
            out[int(parts[0].strip())] = parts[1].strip()
    return out


def overlaps(a: Box, b: Box) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def at(anchor: tuple[float, float], rel: Box) -> Box:
    """A box given relative to an anchor (x0, y0, x1, y1 offsets), placed at ``anchor``."""
    return (anchor[0] + rel[0], anchor[1] + rel[1], anchor[0] + rel[2], anchor[1] + rel[3])


def self_box(me: tuple[float, float], pad: float = SELF_PAD) -> Box:
    return (me[0] - SELF_W / 2 - pad, me[1] - SELF_H - pad, me[0] + SELF_W / 2 + pad, me[1] + pad)


def inside(box: Box, size: tuple[int, int], rects: Sequence[tuple[int, int, int, int]],
           margin: float = MARGIN_PX) -> bool:  # fmt: skip
    """``box`` lies >= ``margin`` px inside the frame and >= ``margin`` px from every UI window
    (x, y, w, h)."""
    w, h = size
    if box[0] < margin or box[1] < margin or box[2] > w - margin or box[3] > h - margin:
        return False
    grown = (box[0] - margin, box[1] - margin, box[2] + margin, box[3] + margin)
    return not any(overlaps(grown, (x, y, x + rw, y + rh)) for x, y, rw, rh in rects)


def sample_reason(item_box: Box, me: tuple[float, float], units: Sequence[tuple[float, float]],
                  others: Sequence[Box], size: tuple[int, int],
                  rects: Sequence[tuple[int, int, int, int]], under_model: bool,
                  age_ns: int, left_ns: int | None) -> str | None:  # fmt: skip
    """PURE (8): None when the labelled item is a clean SAMPLE, else the first reason it is not."""
    if age_ns < AGE_MIN_NS:
        return "young"
    if left_ns is not None and left_ns < BEFORE_VANISH_NS:
        return "vanishing_soon"
    if overlaps(item_box, self_box(me)):
        return "under_self"
    if overlaps(item_box, at(me, BAR)):
        return "under_self_bar"
    if any(overlaps(item_box, at(u, UNIT_BOX)) for u in units):
        return "under_unit"
    if any(overlaps(item_box, o) for o in others):
        return "near_item"
    if not inside(item_box, size, rects):
        return "ui_or_edge"
    if under_model:
        return "under_model"
    return None


def summarize(samples: Sequence[Mapping[str, Any]], r: int = R_MEASURE) -> dict[str, Any]:
    """PURE (8): the pooled ANCHOR (median dx, dy of the best fits) and T_item (the p5 of the
    NCC of the fits NOT at the search edge); STOP below MIN_SAMPLES."""
    fits = [s for s in samples if s.get("ncc") is not None]
    good = [s for s in fits if not olf.at_edge(int(s["dx"]), int(s["dy"]), r)]
    out: dict[str, Any] = {"samples": len(samples), "fitted": len(fits), "not_at_edge": len(good)}
    if len(good) < MIN_SAMPLES:
        return {**out, "STOP": f"{len(good)} samples < {MIN_SAMPLES}", "anchor_px": None,
                "t_item": None}  # fmt: skip
    dx = statistics.median(float(s["dx"]) for s in good)
    dy = statistics.median(float(s["dy"]) for s in good)
    return {**out, "anchor_px": [dx, dy],
            "t_item": ml.percentile([float(s["ncc"]) for s in good], T_ITEM_PERCENTILE),
            "ncc_median": round(statistics.median(float(s["ncc"]) for s in good), 3),
            "mad_px": [statistics.median(abs(float(s["dx"]) - dx) for s in good),
                       statistics.median(abs(float(s["dy"]) - dy) for s in good)]}  # fmt: skip


# --- the client's item sprites ------------------------------------------------------------------


class ItemSheets:
    """item id -> its SpriteSheet (the decoded SPR / ACT under ITEM_DIR, named by the client's
    resname table); None when either is missing (recorded in ``missing``)."""

    def __init__(self, directory: Path = ITEM_DIR, resnames: Path = RESNAME) -> None:
        self.directory = directory
        self.names = parse_resnames(resnames.read_bytes()) if resnames.exists() else {}
        self.cache: dict[int, SpriteSheet | None] = {}
        self.missing: dict[int, str] = {}

    def __call__(self, item_id: int) -> SpriteSheet | None:
        if item_id not in self.cache:
            name = self.names.get(item_id)
            sheet = None
            if name is None:
                self.missing[item_id] = "no_resname"
            else:
                act, spr = self.directory / f"{name}.act", self.directory / f"{name}.spr"
                if act.exists() and spr.exists():
                    sheet = SpriteSheet(parse_act(act.read_bytes()), parse_spr(spr.read_bytes()))
                else:
                    self.missing[item_id] = "no_files"
            self.cache[item_id] = sheet
        return self.cache[item_id]


def cmd_sprites(_a: argparse.Namespace) -> dict[str, Any]:
    sheets = ItemSheets()
    out = {}
    for item_id in sorted(sheets.names):
        name = sheets.names[item_id]
        if not (ITEM_DIR / f"{name}.act").exists():
            continue
        sh = sheets(item_id)
        assert sh is not None
        ext = sh.extent(0, 0)
        out[str(item_id)] = {"actions": len(sh.act.actions), "motions": sh.motions(0),
                             "extent": ext, "w": None if ext is None else ext[2] - ext[0],
                             "h": None if ext is None else ext[3] - ext[1]}  # fmt: skip
    return {"what": "8: the decoded item sprites' native extents (ACT action 0, frame 0)",
            "dir": str(ITEM_DIR), "items": out, "missing": sheets.missing}  # fmt: skip


# --- the FIT measurement ------------------------------------------------------------------------


def _frame(ref: qa_export.JpegRef) -> tuple[list[dict[str, Any]], str]:
    sess: ml.RecSession = olf._JOB["sess"]
    floors: list[il.Floor] = olf._JOB["floors"]
    sheets: ItemSheets = olf._JOB["sheets"]
    occl: olf.Occluders = olf._JOB["occluders"]
    off_ns: int = olf._JOB["offset_ns"]
    t = ref.t_mono_ns
    live = [f for f in floors if il.phase(f, t, D_APPEAR_NS, D_GONE_NS) == "on"]
    if not live:
        return [], "no_item"
    tw = t - off_ns
    world = sess.lab.timeline.frame_world(tw)
    scene = sess.scene(world)
    if scene is None:
        return [], "no_scene"
    bgr = ml.read_png(ref)
    if not sess.layout_ok(bgr):
        return [], "ui_layout_mismatch"
    me = anchor_and_depth(scene, scene.player)[0]
    units = []
    for when in (tw, tw - UNIT_BACK_NS):
        fw = world if when == tw else sess.lab.timeline.frame_world(when)
        for e in fw.entities:
            if e.objtype in occ.UNIT_OBJTYPES and not e.hidden:
                units.append(anchor_and_depth(scene, (e.x, e.y))[0])
    preds = {}
    for f in live:
        sheet = sheets(f.item_id)
        if sheet is None:
            continue
        p = predict_sprite(Actor(il.item_cell(f, OX, OY), 0, 0), sheet, scene, olf.K)
        if p is not None:
            preds[f.floor_id] = (f, sheet, p)
    grey = bgr[:, :, :3].astype(float) @ label_check.GREY
    valid = olf.valid_map(sess.lab.size, sess.lab.ui_rects)
    rows = []
    for fid, (f, sheet, p) in preds.items():
        others = [q.box for g, (_f, _s, q) in preds.items() if g != fid]
        why = sample_reason(p.box, me, units, others, sess.lab.size, sess.lab.ui_rects,
                            occl.hit(scene, p.box) is not None, t - f.t_a,
                            (f.t_v - t) if f.vanished else None)  # fmt: skip
        row: dict[str, Any] = {"frame_id": ref.frame_id, "floor_id": f.floor_id,
                               "item_id": f.item_id, "reason": why, "scale": round(p.scale, 4),
                               "w": round(p.box[2] - p.box[0], 1),
                               "h": round(p.box[3] - p.box[1], 1)}  # fmt: skip
        if why is None:
            best = olf.best_fit(olf.fit_label_all(grey, valid, sheet, p, R_MEASURE))
            if best is not None:
                row.update({"ncc": round(best[0], 4), "dx": best[1], "dy": best[2]})
        rows.append(row)
    return rows, "items"


def cmd_measure(a: argparse.Namespace) -> dict[str, Any]:
    spec = ml.GEF10
    occl = ml.occluders(spec)
    sheets = ItemSheets()
    rows: list[dict[str, Any]] = []
    per_part: dict[str, Any] = {}
    for part in a.parts:
        sess = ml.RecSession.open(part, spec, a.layout_templates)
        ml.refuse(sess, "fit")
        refs = sess.candidates_at(float(a.offset_ms))
        floors = il.floor_items(sess.lab.timeline.events)
        olf._JOB.update(sess=sess, floors=floors, sheets=sheets, occluders=occl,
                        offset_ns=int(float(a.offset_ms) * 1e6))  # fmt: skip
        why: Counter[str] = Counter()
        n0 = len(rows)
        for r, w in olf.run_parallel(_frame, refs, a.workers):
            why[w] += 1
            rows += [{**x, "part": sess.name} for x in r]
        per_part[sess.name] = {"frames": len(sess.refs), "candidates": len(refs),
                               "floor_items": len(floors),
                               "floor_items_by_id": dict(Counter(str(f.item_id) for f in floors)),
                               "frames_by_outcome": dict(why),
                               "labelled_item_views": len(rows) - n0}  # fmt: skip
    clean = [r for r in rows if r["reason"] is None]
    per_item: dict[str, Any] = {}
    by: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by[int(r["item_id"])].append(r)
    for item_id, rs in sorted(by.items()):
        cs = [r for r in rs if r["reason"] is None and r.get("ncc") is not None]
        per_item[str(item_id)] = {
            "labelled_views": len(rs), "floor_items": len({r["floor_id"] for r in rs}),
            "reasons": dict(Counter(str(r["reason"]) for r in rs)),
            "samples_fitted": len(cs),
            "median_dx_dy": [statistics.median(r["dx"] for r in cs),
                             statistics.median(r["dy"] for r in cs)] if cs else None,
            "ncc_median": round(statistics.median(r["ncc"] for r in cs), 3) if cs else None,
            "drawn_box_px": [statistics.median(r["w"] for r in rs),
                             statistics.median(r["h"] for r in rs)],
            "scale_median": statistics.median(r["scale"] for r in rs),
        }  # fmt: skip
    if a.rows is not None:
        a.rows.write_text(json.dumps(rows) + "\n")
    return {
        "what": "8: the floor items' drawn ANCHOR and T_item on FIT (sprite boxes, +-10 px fit)",
        "map": spec.name, "parts": a.parts, "measured_at": olf.now_ict(), "commit": olf.git_head(),
        "offset_ms": float(a.offset_ms), "offset_source": a.offset_source,
        "sub_table": {"OX": OX, "OY": OY}, "d_appear_s": 2.2, "d_gone_s": 0.6,
        "pooled": summarize(clean), "per_item": per_item, "per_part": per_part,
        "sprites_missing": {str(k): v for k, v in sheets.missing.items()},
        "occluders": occl.provenance()["rsw_sha256"],
    }  # fmt: skip


# --- ROUND 3 (gef10-round3.md): freeze, labels, G2 ----------------------------------------------
LAYOUT_TEMPLATES = Path("/home/batt/docker/poring-lab/data/ui_anchors/layout")
R_LABEL = 6  # 8: a label's fit, +-px around the ANCHORED prediction
G2_BAR_PX = 3.0  # 8 / round3 4.3: the median |dx|, |dy| at the frozen anchor, on TEST3
MIN_FIT_FLOOR_ITEMS = 4  # round3 4.1: the clean samples come from >= 4 floor items


def anchored(p: SpritePrediction, anchor: Sequence[float]) -> SpritePrediction:
    """PURE: the prediction moved by the item ANCHOR (its box = the fit's window, its anchor_px =
    where the sprite is rendered)."""
    dx, dy = float(anchor[0]), float(anchor[1])
    b = p.box
    return dataclasses.replace(p, box=(b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy),
                               anchor_px=(p.anchor_px[0] + dx, p.anchor_px[1] + dy),
                               mask=None, mask_origin=None)  # fmt: skip


def label_reasons(boxes: Mapping[int, Box], phases: Sequence[str], me: tuple[float, float],
                  units: Sequence[tuple[float, float]], size: tuple[int, int],
                  rects: Sequence[tuple[int, int, int, int]]
                  ) -> tuple[list[str], list[int]]:  # fmt: skip
    """PURE (8's item exclusions; round3 1): the frame's exclusion reasons and the floor ids to
    fit. ``boxes``: floor id -> the ANCHORED box of every item ON the floor (phase "on");
    ``phases``: every nearby item's phase; ``rects``: UI windows (x, y, w, h). Wholly behind the UI
    or off the region: not drawn, no label. ``under_unit`` uses the generic unit box at tw and
    tw - 0.5 s (a superset of a unit's predicted box; round3 1)."""
    why: list[str] = []
    if "settling" in phases:
        why.append("item_settling")
    if "vanishing" in phases:
        why.append("item_vanishing")
    xyxy = [(float(x), float(y), float(x + w), float(y + h)) for x, y, w, h in rects]
    vis: list[int] = []
    for fid, b in boxes.items():
        st = il.ui_status(b, xyxy, size)
        if st == "hidden":
            continue
        if st != "clear":
            why.append(st)
            continue
        vis.append(fid)
    vb = [boxes[f] for f in vis]
    if il.stacked(vb):
        why.append("stacked")
    if any(overlaps(b, self_box(me)) for b in vb):
        why.append("under_self")
    if any(overlaps(b, at(me, BAR)) for b in vb):
        why.append("under_self_bar")
    if any(overlaps(b, at(u, UNIT_BOX)) for b in vb for u in units):
        why.append("under_unit")
    return list(dict.fromkeys(why)), vis


def freeze_params(measure: Mapping[str, Any], rows: Sequence[Mapping[str, Any]],
                  r: int = R_MEASURE) -> dict[str, Any]:  # fmt: skip
    """PURE (round3 4.1): the frozen anchor and T_item from a FIT measurement, or a STOP: >= 12
    clean samples not at the search edge (8) from >= MIN_FIT_FLOOR_ITEMS floor items."""
    pooled = measure.get("pooled") or {}
    good = [x for x in rows if x.get("reason") is None and x.get("ncc") is not None
            and not olf.at_edge(int(x["dx"]), int(x["dy"]), r)]  # fmt: skip
    floor_ids = {(str(x.get("part")), int(x["floor_id"])) for x in good}
    out = {"samples": len(good), "floor_items": len(floor_ids)}
    if pooled.get("STOP") or pooled.get("anchor_px") is None:
        return {**out, "STOP": pooled.get("STOP") or "no anchor"}
    if len(floor_ids) < MIN_FIT_FLOOR_ITEMS:
        return {**out, "STOP": f"{len(floor_ids)} floor items < {MIN_FIT_FLOOR_ITEMS}"}
    return {**out, "anchor_px": list(pooled["anchor_px"]), "t_item": float(pooled["t_item"]),
            "r_label": R_LABEL, "d_appear_s": 2.2, "d_gone_s": 0.6,
            "sub_table": {"OX": OX, "OY": OY},
            "class": "item (one pooled class, Batt C)"}  # fmt: skip


def g2_summary(rows: Sequence[Mapping[str, Any]], bar: float = G2_BAR_PX) -> dict[str, Any]:
    """PURE (round3 4.3): G2 = the median |dx|, |dy| of the TEST3 fits at the frozen anchor."""
    fits = [x for x in rows if x.get("dx") is not None]
    if not fits:
        return {"n": 0, "verdict": "NO_DATA"}
    mdx = statistics.median(abs(float(x["dx"])) for x in fits)
    mdy = statistics.median(abs(float(x["dy"])) for x in fits)
    return {"n": len(fits), "floor_items": len({(x.get("part"), x["floor_id"]) for x in fits}),
            "median_abs_dx": mdx, "median_abs_dy": mdy,
            "verdict": "PASS" if mdx <= bar and mdy <= bar else "STOP"}  # fmt: skip


def check_role(spec: ml.MapSpec, sid: str, spots: frozenset[int] | None, role: str) -> None:
    """PURE (round3 2): ``train`` refuses every TEST (round 1's, TEST2, TEST3); ``test3`` (G2)
    reads TEST3 and nothing else."""
    if role == "train" and spec.is_test(sid, spots):
        raise SystemExit(f"{sid}: shares frames with a TEST: refused (gef10-round3.md 2)")
    if role == "test3" and not any(sid.endswith(x) for x in spec.test3_suffixes):
        raise SystemExit(f"{sid}: g2 reads TEST3 only (gef10-round3.md 2)")


def load_params(path: Path) -> dict[str, Any]:
    d = json.loads(path.read_text())
    if d.get("STOP") or d.get("anchor_px") is None:
        raise SystemExit(f"{path}: not frozen ({d.get('STOP')})")
    return d


def _setup(ref: qa_export.JpegRef) -> tuple[Any, str]:
    """The frame's shared state for round 3, or (None, reason)."""
    sess: ml.RecSession = olf._JOB["sess"]
    floors: list[il.Floor] = olf._JOB["floors"]
    t = ref.t_mono_ns
    near = [(f, il.phase(f, t, D_APPEAR_NS, D_GONE_NS)) for f in floors
            if f.t_a <= t < f.t_v + D_GONE_NS]  # fmt: skip
    if not any(ph == "on" for _f, ph in near):
        return None, "no_item"
    tw = t - olf._JOB["offset_ns"]
    world = sess.lab.timeline.frame_world(tw)
    scene = sess.scene(world)
    if scene is None:
        return None, "no_scene"
    bgr = ml.read_png(ref)
    if not sess.layout_ok(bgr):
        return None, "ui_layout_mismatch"
    me = anchor_and_depth(scene, scene.player)[0]
    units = []
    for when in (tw, tw - UNIT_BACK_NS):
        fw = world if when == tw else sess.lab.timeline.frame_world(when)
        for e in fw.entities:
            if e.objtype in occ.UNIT_OBJTYPES and not e.hidden:
                units.append(anchor_and_depth(scene, (e.x, e.y))[0])
    return (t, near, scene, bgr, me, units), "ok"


def _preds(near: Sequence[tuple[il.Floor, str]], scene: Any, anchor: Sequence[float]
           ) -> dict[int, tuple[il.Floor, SpriteSheet, SpritePrediction]]:  # fmt: skip
    sheets: ItemSheets = olf._JOB["sheets"]
    out = {}
    for f, ph in near:
        if ph != "on":
            continue
        sheet = sheets(f.item_id)
        if sheet is None:
            continue
        p = predict_sprite(Actor(il.item_cell(f, OX, OY), 0, 0), sheet, scene, olf.K)
        if p is not None:
            out[f.floor_id] = (f, sheet, anchored(p, anchor))
    return out


def _label_frame(ref: qa_export.JpegRef) -> tuple[list[dict[str, Any]], str]:
    st, why = _setup(ref)
    if st is None:
        return [], why
    t, near, scene, bgr, me, units = st
    sess: ml.RecSession = olf._JOB["sess"]
    prm = olf._JOB["params"]
    preds = _preds(near, scene, prm["anchor_px"])
    if any(ph == "on" and f.floor_id not in preds for f, ph in near):
        return [{"frame_id": ref.frame_id, "t": t, "status": "exclude",
                 "reasons": ["item_untemplated"], "items": []}], "frame"  # fmt: skip
    reasons, vis = label_reasons({k: v[2].box for k, v in preds.items()},
                                 [ph for _f, ph in near], me, units, sess.lab.size,
                                 sess.lab.ui_rects)  # fmt: skip
    grey = bgr[:, :, :3].astype(float) @ label_check.GREY
    valid = olf.valid_map(sess.lab.size, sess.lab.ui_rects)
    occl: olf.Occluders = olf._JOB["occluders"]
    items = []
    for fid in vis:
        f, sheet, p = preds[fid]
        best = olf.best_fit(olf.fit_label_all(grey, valid, sheet, p, R_LABEL))
        if best is None:
            reasons.append("edge_partial")
            continue
        ncc, dx, dy = best[0], best[1], best[2]
        unfit = ncc < float(prm["t_item"]) or olf.at_edge(dx, dy, R_LABEL)
        b = p.box
        items.append({"floor_id": f.floor_id, "item_id": f.item_id, "kind": f.kind,
                      "box": [round(b[0] + dx, 2), round(b[1] + dy, 2), round(b[2] + dx, 2),
                              round(b[3] + dy, 2)],
                      "pred_box": [round(x, 2) for x in b], "ncc": round(ncc, 4), "dx": dx,
                      "dy": dy, "unfit": unfit, "under_model": occl.hit(scene, b) is not None,
                      "age_s": round((t - f.t_a) / NS, 2)})  # fmt: skip
        if unfit:
            reasons.append("item_unfit")
    reasons = list(dict.fromkeys(reasons))
    return [{"frame_id": ref.frame_id, "t": t, "status": "exclude" if reasons else "keep",
             "reasons": reasons, "items": items, "me": [round(me[0], 1), round(me[1], 1)]}], \
        "frame"  # fmt: skip


def _g2_frame(ref: qa_export.JpegRef) -> tuple[list[dict[str, Any]], str]:
    st, why = _setup(ref)
    if st is None:
        return [], why
    t, near, scene, bgr, me, units = st
    sess: ml.RecSession = olf._JOB["sess"]
    occl: olf.Occluders = olf._JOB["occluders"]
    preds = _preds(near, scene, olf._JOB["params"]["anchor_px"])
    grey = bgr[:, :, :3].astype(float) @ label_check.GREY
    valid = olf.valid_map(sess.lab.size, sess.lab.ui_rects)
    rows = []
    for fid, (f, sheet, p) in preds.items():
        others = [q.box for g, (_f, _s, q) in preds.items() if g != fid]
        why_s = sample_reason(p.box, me, units, others, sess.lab.size, sess.lab.ui_rects,
                              occl.hit(scene, p.box) is not None, t - f.t_a,
                              (f.t_v - t) if f.vanished else None)  # fmt: skip
        row: dict[str, Any] = {"frame_id": ref.frame_id, "floor_id": f.floor_id,
                               "item_id": f.item_id, "reason": why_s}  # fmt: skip
        if why_s is None:
            best = olf.best_fit(olf.fit_label_all(grey, valid, sheet, p, R_MEASURE))
            if best is not None:
                row.update({"ncc": round(best[0], 4), "dx": best[1], "dy": best[2]})
        rows.append(row)
    return rows, "items"


def _run(a: argparse.Namespace, worker: Any, role: str) -> tuple[list[dict[str, Any]], dict]:
    spec = ml.GEF10
    prm = load_params(a.params)
    occl = ml.occluders(spec)
    sheets = ItemSheets()
    rows: list[dict[str, Any]] = []
    per_part: dict[str, Any] = {}
    for part in a.parts:
        sess = ml.RecSession.open(part, spec, a.layout_templates)
        check_role(spec, sess.sid, sess.spots, role)
        refs = sess.candidates_at(float(a.offset_ms))
        floors = il.floor_items(sess.lab.timeline.events)
        olf._JOB.update(sess=sess, floors=floors, sheets=sheets, occluders=occl, params=prm,
                        offset_ns=int(float(a.offset_ms) * 1e6))  # fmt: skip
        why: Counter[str] = Counter()
        n0 = len(rows)
        for r, w in olf.run_parallel(worker, refs, a.workers):
            why[w] += 1
            rows += [{**x, "part": sess.name} for x in r]
        per_part[sess.name] = {"frames": len(sess.refs), "candidates": len(refs),
                               "dropped": dict(sess.dropped), "floor_items": len(floors),
                               "outcomes": dict(why), "rows": len(rows) - n0}  # fmt: skip
    return rows, per_part


R3 = Path("/dev/shm/poring-lab-tmp/gef10-r3")  # client-derived crops: RAM, small (rule 7)
BLIND_SEED = 33  # round3 4.4
INSTRUCTIONS_SHA256 = "7d0a97041201f3d622f663115de9cb4d128afe4859706f388d1b35b3076e125c"
NEG_ITEM_CELLS, NEG_UNIT_CELLS, NEG_SPAN = 3, 2, 8


def empty_cell(me: tuple[float, float], items: Sequence[tuple[float, float]],
               units: Sequence[tuple[float, float]], rng: random.Random,
               span: int = NEG_SPAN) -> tuple[float, float] | None:  # fmt: skip
    """PURE (item-class.md amendment A 1, as item_labels.empty_point): a random cell within
    +-``span`` of ours, not ours or next to it, >= 3 cells (Chebyshev) from every floor item and
    >= 2 from every unit; None after 200 tries."""

    def cheb(a: tuple[float, float], b: tuple[float, float]) -> float:
        return max(abs(a[0] - b[0]), abs(a[1] - b[1]))

    for _ in range(200):
        c = (me[0] + rng.randint(-span, span), me[1] + rng.randint(-span, span))
        if cheb(c, me) <= 1 or any(cheb(c, x) < NEG_ITEM_CELLS for x in items):
            continue
        if any(cheb(c, u) < NEG_UNIT_CELLS for u in units):
            continue
        return c
    return None


def cmd_pack(a: argparse.Namespace) -> dict[str, Any]:
    """round3 4.4: the blind pack -- 40 crops of KEPT TRAIN labels (<= 3 per floor item, by the
    seed) + 20 empty-floor negatives in kept frames; item_labels' crop and instructions."""
    from PIL import Image

    if hashlib.sha256(il.INSTRUCTIONS.encode()).hexdigest() != INSTRUCTIONS_SHA256:
        raise SystemExit("item_labels.INSTRUCTIONS changed: the blind round needs them as frozen")
    spec = ml.GEF10
    rows = [json.loads(x) for x in a.rows.read_text().splitlines() if x.strip()]
    keep = [r for r in rows if r["status"] == "keep" and r["items"]]
    cands = [{"sid": r["part"], "frame_id": r["frame_id"], "t": r["t"], **it}
             for r in keep for it in r["items"]]  # fmt: skip
    picks = il.draw_items(cands, il.BLIND_ITEMS, a.seed)
    sessions = {}
    for part in a.parts:
        sess = ml.RecSession.open(part, spec, a.layout_templates)
        check_role(spec, sess.sid, sess.spots, "train")
        sessions[sess.name] = sess
    off_ns = int(float(a.offset_ms) * 1e6)
    sizes = [(c["box"][2] - c["box"][0], c["box"][3] - c["box"][1]) for c in cands]
    mw = statistics.median(w for w, _h in sizes) if sizes else 16.0
    mh = statistics.median(h for _w, h in sizes) if sizes else 16.0
    rng = random.Random(a.seed * 1000 + 7)
    order = list(keep)
    rng.shuffle(order)
    negs: list[dict[str, Any]] = []
    for r in order:
        if len(negs) >= il.BLIND_NEG:
            break
        sess = sessions[r["part"]]
        t = int(r["t"])
        world = sess.lab.timeline.frame_world(t - off_ns)
        scene = sess.scene(world)
        if scene is None or world.self_pos is None:
            continue
        floors = [il.item_cell(f, OX, OY) for f in il.floor_items(sess.lab.timeline.events)
                  if f.t_a <= t < f.t_v]  # fmt: skip
        units = [(float(e.x), float(e.y)) for e in world.entities
                 if e.objtype in occ.UNIT_OBJTYPES and not e.hidden]  # fmt: skip
        c = empty_cell(tuple(world.self_pos), floors, units, rng)
        if c is None:
            continue
        u, v = anchor_and_depth(scene, c)[0]
        box = (u - mw / 2, v - mh / 2, u + mw / 2, v + mh / 2)
        me = anchor_and_depth(scene, scene.player)[0]
        why, vis = label_reasons({0: box}, [], me, [], sess.lab.size, sess.lab.ui_rects)
        if why or not vis:
            continue
        negs.append({"sid": r["part"], "frame_id": r["frame_id"], "t": t, "floor_id": None,
                     "item_id": None, "box": [round(x, 2) for x in box]})  # fmt: skip
    entries = [{"truth": "item", **x} for x in picks] + [{"truth": "none", **x} for x in negs]
    random.Random(a.seed).shuffle(entries)
    root, keyd = R3 / f"blind-pack-seed{a.seed}", R3 / f"answer-key-seed{a.seed}"
    root.mkdir(parents=True, exist_ok=True)
    keyd.mkdir(parents=True, exist_ok=True)
    key: dict[str, Any] = {"seed": a.seed, "rows": str(a.rows), "crops": {}}
    for i, e in enumerate(entries, 1):
        cid = f"{i:03d}"
        sess = sessions[e["sid"]]
        ref = next(x for x in sess.refs if x.frame_id == e["frame_id"])
        rgb = np.ascontiguousarray(ml.read_png(ref)[:, :, 2::-1])
        Image.fromarray(il.crop_pair(rgb, e["box"])).save(root / f"crop-{cid}.png")
        key["crops"][cid] = {k: v for k, v in e.items() if k != "pred_box"}
    (root / "instructions.txt").write_text(il.INSTRUCTIONS)
    (keyd / "answer_key.json").write_text(json.dumps(key, indent=1))
    return {"what": "round3 4.4: the blind pack", "pack": str(root),
            "key": str(keyd / "answer_key.json"), "kept_labels": len(cands),
            "items": len(picks), "negatives": len(negs), "built_at": olf.now_ict(),
            "commit": olf.git_head()}  # fmt: skip


def cmd_freeze(a: argparse.Namespace) -> dict[str, Any]:
    raw = a.measure.read_bytes()
    out = freeze_params(json.loads(raw), json.loads(a.rows.read_text()))
    return {**out, "what": "round3 4.1: the frozen item anchor and T_item",
            "measure": str(a.measure), "measure_sha256": hashlib.sha256(raw).hexdigest(),
            "frozen_at": olf.now_ict(), "commit": olf.git_head()}  # fmt: skip


def cmd_label(a: argparse.Namespace) -> dict[str, Any]:
    rows, per_part = _run(a, _label_frame, "train")
    if a.rows is not None:
        a.rows.write_text("".join(json.dumps(r) + "\n" for r in rows))
    keep = [r for r in rows if r["status"] == "keep"]
    labels = [(r["part"], it) for r in keep for it in r["items"]]
    return {"what": "round3: TRAIN item labels (one pooled class)", "params": str(a.params),
            "params_sha256": hashlib.sha256(a.params.read_bytes()).hexdigest(),
            "labelled_at": olf.now_ict(), "commit": olf.git_head(),
            "frames": len(rows), "kept_frames": len(keep), "kept_labels": len(labels),
            "kept_floor_items": len({(p, it["floor_id"]) for p, it in labels}),
            "kept_by_item_id": dict(Counter(str(it["item_id"]) for _p, it in labels)),
            "reasons": dict(Counter(x for r in rows for x in r["reasons"])),
            "per_part": per_part}  # fmt: skip


def cmd_g2(a: argparse.Namespace) -> dict[str, Any]:
    rows, per_part = _run(a, _g2_frame, "test3")
    if a.rows is not None:
        a.rows.write_text(json.dumps(rows) + "\n")
    clean = [r for r in rows if r["reason"] is None]
    return {"what": "round3 4.3: G2 on TEST3 at the frozen anchor", "params": str(a.params),
            "checked_at": olf.now_ict(), "commit": olf.git_head(), "g2": g2_summary(clean),
            "reasons": dict(Counter(str(r["reason"]) for r in rows)),
            "per_part": per_part}  # fmt: skip


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("sprites")
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("measure")
    p.add_argument("parts", nargs="+")
    p.add_argument("--offset-ms", type=float, required=True)
    p.add_argument("--offset-source", required=True)
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--layout-templates", type=Path,
                   default=Path("/home/batt/docker/poring-lab/data/ui_anchors/layout"))  # fmt: skip
    p.add_argument("--rows", type=Path, default=None)
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("freeze")
    p.add_argument("--measure", type=Path, required=True)
    p.add_argument("--rows", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    for name in ("label", "g2"):
        p = sub.add_parser(name)
        p.add_argument("parts", nargs="+")
        p.add_argument("--params", type=Path, required=True)
        p.add_argument("--offset-ms", type=float, required=True)
        p.add_argument("--workers", type=int, default=1)
        p.add_argument("--layout-templates", type=Path, default=LAYOUT_TEMPLATES)
        p.add_argument("--rows", type=Path, default=None)
        p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("pack")
    p.add_argument("parts", nargs="+")
    p.add_argument("--rows", type=Path, required=True, help="label's --rows (TRAIN)")
    p.add_argument("--offset-ms", type=float, required=True)
    p.add_argument("--seed", type=int, default=BLIND_SEED)
    p.add_argument("--layout-templates", type=Path, default=LAYOUT_TEMPLATES)
    p.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    out = {"sprites": cmd_sprites, "measure": cmd_measure, "freeze": cmd_freeze,
           "label": cmd_label, "g2": cmd_g2, "pack": cmd_pack}[a.cmd](a)  # fmt: skip
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1)[:6000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
