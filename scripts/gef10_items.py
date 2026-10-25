#!/usr/bin/env python3
"""FLOOR ITEMS on gef_fild10: the FIT measurement of the items' drawn ANCHOR and fit floor
T_item (docs/planning/gef10-detector.md section 8, PROPOSED 2026-10-25 20:51:49 ICT, 3e31b01,
before this was built).

    gef10_items.py sprites --out JSON                 the item sprites' native extents (1e)
    gef10_items.py measure PART... --offset-ms MS --out JSON
                                                      8's anchor and T_item, FIT parts only

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
import json
import statistics
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import item_labels as il  # noqa: E402
import label_check  # noqa: E402
import map_labels as ml  # noqa: E402
import orc_camera_check as occ  # noqa: E402
import orc_labels_fix as olf  # noqa: E402
import qa_export  # noqa: E402

from poring_dataset.render import Actor, SpriteSheet, anchor_and_depth, predict_sprite  # noqa: E402
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
    a = ap.parse_args(argv)
    out = {"sprites": cmd_sprites, "measure": cmd_measure}[a.cmd](a)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1)[:6000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
