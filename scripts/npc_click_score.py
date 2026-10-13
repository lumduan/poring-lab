#!/usr/bin/env python3
"""walk@17 item 5's OFFLINE judge and analyses (docs/planning/npc-click-test.md). The packets judge
what the pixels did; nothing here is ever fed back into a run (ADR-0007).

    npc_click_score.py score      SESSION   the targeted test (npc_click_test.py's session)
    npc_click_score.py recall     SESSION [--frames DIR --run-detector]
                                            detector recall on NPC sprites vs packet truth
    npc_click_score.py replay-l3  SESSION   the L3 no-click layer on a walk session's reads/clicks
    npc_click_score.py remembered SESSION   walk@12-15's TALK-cell memory vs the packets' NPC cells
    npc_click_score.py shift      NPZ...    cursor crops: does a 1-2 px shift restore the match?

Session contract (npc_click_test.py): manifest.json, demo.jsonl (rule "npc-click@1/probe" or
"npc-click@1/click"; the record's outcome.evidence carries the reads, see below), crops/*.npz
(client pixels, /dev/shm only), detections.jsonl (unit_detector's batch log) and packets.jsonl.gz.
  probe evidence: {"npc": key, "npc_cell", "stand", "kind": sprite|cell, "offset", "at",
                   "reads": [{"shape", "iou", "col", "best": {...}, "t_ns"}...], "verdict",
                   "crop", "det_batch", "l3": refusal-or-None}
  click evidence: {"npc", "npc_cell", "stand", "cell", "at", "gate": cursor_gate's result,
                   "l3": refusal-or-None, "dialog": the after-click policy's record}
Names of NPCs never appear: L3 keys (file:line), cells and job ids only.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/poring_dataset/src"))
import npc_noclick as nc  # noqa: E402
import walk_readiness  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
S = 1_000_000_000
CAMERA_JSON = ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json"
CONTACT_S = 1.5  # a click's npc_contact: within this of the click (contacts came 0.17 s after)
MOVE_S = 1.5  # a click's self_move_request: within this
MATCH_PX = 40.0  # a detector box "sees" an NPC: its foot within this of the projected feet ...
GROW_PX = 20.0  # ... or the projected feet inside the box grown by this (each box: ONE NPC, the
#                nearest by feet; generous on purpose: a miss must not come from the criterion)
SHIFT_R = 2
PROBE, CLICK = "npc-click@1/probe", "npc-click@1/click"
SHAPE_MATCH_IOU = 0.6  # walk6.MIN_IOU: a shape match; unknown above it = the COLOUR check failed


def wilson(k: int, n: int) -> list[float] | None:
    if n <= 0:
        return None
    lo, hi = walk_readiness.wilson(k, n)
    return [round(lo, 4), round(hi, 4)]


def rate(k: int, n: int) -> dict[str, Any]:
    return {"k": k, "n": n, "rate": round(k / n, 4) if n else None, "ci95": wilson(k, n)}


def read_events(session: Path) -> list[dict[str, Any]]:
    p = session / "packets.jsonl.gz"
    if not p.exists():
        return []
    with gzip.open(p, "rt") as f:
        return sorted((json.loads(x) for x in f if x.strip()), key=lambda e: int(e["t_mono_ns"]))


def read_records(session: Path, verified: bool = False) -> list[dict[str, Any]]:
    p = session / ("demo.verified.jsonl" if verified else "demo.jsonl")
    if verified and not p.exists():
        p = session / "demo.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def static_npcs(events: Iterable[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Every drawn NPC the server showed (objtype 6, not a hidden/portal class, no invisibility
    option): gid -> job, cell, the map. DESIGN-TIME TRUTH only: the stand-in for a COMPLETE L3
    list in the analyses."""
    from poring_dataset.labels import drawn
    from poring_dataset.timeline import HIDDEN_OPTIONS

    out: dict[int, dict[str, Any]] = {}
    cur_map = None
    for e in events:
        if e.get("type") == "map_change":
            cur_map = str(e.get("map", "")).removesuffix(".gat")
        npc = e.get("type") == "entity_appear" and int(e.get("objtype", -1)) == 6
        hidden = int(e.get("effect_state") or 0) & HIDDEN_OPTIONS  # sent, drawn as nothing
        if npc and not hidden and drawn(6, int(e["job"])):
            out[int(e["gid"])] = {"job": int(e["job"]), "cell": (int(e["x"]), int(e["y"])),
                                  "map": cur_map}  # fmt: skip
    return out


def world(camera: Any, gat: Any, pos: Sequence[int]) -> Any:
    """What NoClickLayer / picking need of a walk World."""
    return SimpleNamespace(camera=camera, gat=gat, position=(int(pos[0]), int(pos[1])))


def load_map(map_name: str) -> tuple[Any, Any]:
    """(camera, gat) for a map, as the walk rules build them (camera_rdp.json; indoor rotated)."""
    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    cj = json.loads(CAMERA_JSON.read_text())
    base = cam.camera_from_json(cj["camera"])
    indoor = map_name in cam.load_indoor_table()
    camera = (cam.camera_for_map(base, True, cj["indoor"]["yaw_deg"], cj["indoor"]["distance"])
              if indoor else base)  # fmt: skip
    gat = gatmod.parse((cam.GAT_DIR / f"{map_name}.gat").read_bytes())
    return camera, gat


def project_feet(camera: Any, gat: Any, pos: Sequence[int], cells: Sequence[Sequence[int]]) -> Any:
    rel = np.array([(c[0] - pos[0], c[1] - pos[1]) for c in cells], dtype=float).reshape(-1, 2)
    p = (int(pos[0]), int(pos[1]))
    return camera.project(rel, None if gat is None else gat.relative_altitude(p, rel))


# --- detector recall on NPC sprites (Batt ~16:10) -------------------------------------------------


def box_sees(box: Sequence[Any], feet: tuple[float, float]) -> bool:
    x0, y0, x1, y1 = (float(b) for b in box[:4])
    u, v = feet
    foot = ((x0 + x1) / 2, y1)
    inside = x0 - GROW_PX <= u <= x1 + GROW_PX and y0 - GROW_PX <= v <= y1 + GROW_PX
    return inside or bool(np.hypot(foot[0] - u, foot[1] - v) <= MATCH_PX)


def recall(events: list[dict[str, Any]], batches: Sequence[dict[str, Any]],
           projector_for: Any = None) -> dict[str, Any]:  # fmt: skip
    """Per detector batch ({"t_frame", "boxes": [[x0, y0, x1, y1, score, cls], ...], "id"}): the
    NPCs the server showed on screen then (v0 labels: the projected feet at the GM's packet cell,
    on screen, not behind the UI) and whether any box (ANY class) sees each. Recall per job id
    and overall with Wilson CIs, per gid ever-boxed, and the frames worth banking."""
    from poring_dataset import camera as cam
    from poring_dataset.labels import labels_for
    from poring_dataset.timeline import Timeline

    cj = json.loads(CAMERA_JSON.read_text())
    tl = Timeline(events)
    jobs = {g: s["job"] for g, s in static_npcs(events).items()}
    cache: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    for b in batches:
        fw = tl.frame_world(int(b["t_frame"]))
        if fw.self_pos is None or not fw.map:
            continue
        mname = str(fw.map).removesuffix(".gat")
        if mname not in cache:
            cache[mname] = (projector_for or cam.projector_for)(cj, mname)[0]
        labels = [
            lab
            for lab in labels_for(fw, cache[mname], (1280, 720), exclude_gids=[fw.aid or -1])
            if lab.cls == "npc"
        ]
        feet_of = {lab.gid: ((lab.x0 + lab.x1) / 2, lab.y1) for lab in labels}
        owner: dict[int, list[Any]] = defaultdict(list)
        for bx in b[
            "boxes"
        ]:  # each box counts for ONE NPC: the one whose feet are nearest its foot
            foot = ((float(bx[0]) + float(bx[2])) / 2, float(bx[3]))
            near = min(
                feet_of,
                key=lambda g: np.hypot(feet_of[g][0] - foot[0], feet_of[g][1] - foot[1]),
                default=None,
            )
            if near is not None:
                owner[near].append(bx)
        for lab in labels:
            feet = feet_of[lab.gid]
            seen = [bx for bx in owner[lab.gid] if box_sees(bx, feet)]
            best = max(seen, key=lambda bx: float(bx[4]), default=None)
            ent = next(e for e in fw.entities if e.gid == lab.gid)
            rows.append({"batch": b["id"], "gid": lab.gid, "job": jobs.get(lab.gid, ent.job),
                         "cell": [round(ent.x), round(ent.y)], "map": mname,
                         "feet": [round(feet[0], 1), round(feet[1], 1)],
                         "boxed": best is not None,
                         "score": None if best is None else float(best[4]),
                         "cls": None if best is None else str(best[5])})  # fmt: skip
    by_job: dict[int, list[bool]] = defaultdict(list)
    by_gid: dict[int, dict[str, Any]] = {}
    for r in rows:
        by_job[r["job"]].append(r["boxed"])
        g = by_gid.setdefault(r["gid"], {"job": r["job"], "cell": r["cell"], "frames": 0,
                                         "boxed": 0, "max_score": None})  # fmt: skip
        g["frames"] += 1
        g["boxed"] += int(r["boxed"])
        if r["score"] is not None:
            g["max_score"] = max(g["max_score"] or 0.0, r["score"])
    return {
        "batches": len(batches),
        "batches_with_any_box": sum(1 for b in batches if b["boxes"]),
        "boxes": dict(Counter(str(bx[5]) for b in batches for bx in b["boxes"])),
        "npc_sightings": rate(sum(r["boxed"] for r in rows), len(rows)),
        "per_job": {str(j): rate(sum(v), len(v)) for j, v in sorted(by_job.items())},
        "per_gid": {str(g): v for g, v in sorted(by_gid.items())},
        "bank": sorted({r["batch"] for r in rows}),
        "rows": rows,
    }


def batches_from_log(session: Path) -> list[dict[str, Any]]:
    """detections.jsonl: each row is logged AFTER its detection; its frame came ``ms`` earlier."""
    p = session / "detections.jsonl"
    out = []
    for k, line in enumerate(p.read_text().splitlines() if p.exists() else []):
        d = json.loads(line)
        out.append({"id": k, "t_frame": int(d["t_ns"] - float(d.get("ms", 0.0)) * 1e6),
                    "boxes": d["boxes"]})  # fmt: skip
    return out


def frame_files(session: Path, frames: Path | None) -> list[tuple[Path, int]]:
    """(png, capture time): ``frames``' <name>-<t_ns>.png (talk-cal sessions, npc_click_test's
    frames/; the name's LAST field is the frame's time), else the session's route snapshots with
    their records' t_capture_ns (walk runs)."""
    if frames is not None:
        return [(p, int(p.stem.rsplit("-", 1)[1])) for p in sorted(frames.glob("*.png"))]
    out = []
    for r in read_records(session):
        f = r.get("frame") or {}
        if f.get("ref") and f.get("t_capture_ns"):
            out.append((session / f["ref"], int(f["t_capture_ns"])))
    return out


def batches_from_frames(
    files: Sequence[tuple[Path, int]], threads: int = 4
) -> list[dict[str, Any]]:
    """Run the CPU detector (unit_detector, its own env; ``threads`` caps its CPU) on the frames."""
    import unit_detector
    from PIL import Image

    out = []
    with unit_detector.UnitDetector(threads=threads) as det:
        for p, t in files:
            if not p.exists():
                continue
            rgb = np.asarray(Image.open(p).convert("RGB"))
            boxes = det.detect(np.ascontiguousarray(rgb[..., ::-1]))  # BGR, as the grabs are
            out.append({"id": p.name, "t_frame": t, "boxes": [
                [b.x0, b.y0, b.x1, b.y1, round(b.score, 3), b.cls] for b in boxes]})  # fmt: skip
    return out


# --- the L3 no-click layer, replayed on a walk session ------------------------------------------


def contact_clicks(events: list[dict[str, Any]], clicks: Sequence[int]) -> dict[int, int]:
    """t_click -> the npc_gid of an npc_contact within CONTACT_S after it."""
    out = {}
    contacts = [e for e in events if e.get("type") == "npc_contact"]
    for t in clicks:
        hit = [e for e in contacts if 0 <= int(e["t_mono_ns"]) - t <= CONTACT_S * S]
        if hit:
            out[t] = int(hit[0]["npc_gid"])
    return out


def scored_routes(records: list[dict[str, Any]], first: int = 50) -> list[dict[str, Any]]:
    routes = [r for r in records if r.get("rule") and "/" not in r["rule"]]
    return [r for r in routes if r["outcome"]["status"] != "interrupted"][:first]


def replay_l3(session: Path, kb_dir: Path = nc.KB_DIR, layers: dict[str, Any] | None = None,
              camera_gat: tuple[Any, Any] | None = None) -> dict[str, Any]:  # fmt: skip
    """Would the L3 layer alone have refused walk@15's clicks? Two layers: "l3_kb" (the L3 lists
    as they are today) and "l3_complete" (every drawn NPC the server showed: the stand-in for a
    COMPLETE L3, design time only). Every hover read and every click of every route is checked at
    the rule's belief; the contacts are found by the packets."""
    man = json.loads((session / "manifest.json").read_text())
    mname = man["map"]
    events = read_events(session)
    records = read_records(session, verified=True)
    camera, gat = camera_gat or load_map(mname)
    if layers is None:
        kb_npcs, cov = nc.load_l3_npcs(mname, kb_dir)
        full = [nc.StaticNpc(mname, s["cell"], f"gid:{g}", str(s["job"]), "packets")
                for g, s in static_npcs(events).items() if s["map"] in (None, mname)]  # fmt: skip
        layers = {"l3_kb": nc.NoClickLayer(kb_npcs), "l3_complete": nc.NoClickLayer(full)}
    scored = {r["record_id"] for r in scored_routes(records)}
    routes = [r for r in records if r.get("rule") and "/" not in r["rule"]]
    clicks: list[dict[str, Any]] = []
    hovers: list[dict[str, Any]] = []
    subs: list[dict[str, Any]] = []
    for k, rt in enumerate(routes):
        ev = rt["outcome"]["evidence"]
        for e in ev.get("events", []):
            if "npc_substitute" in e and e["npc_substitute"] is not None:
                subs.append({"route": k, "cell": e["npc_substitute"], "for": e["for"]})
            if "from" not in e or not e.get("target"):
                continue
            w = world(camera, gat, e["from"])
            for i, t in enumerate(e["target"]):
                row = {"route": k, "scored": rt["record_id"] in scored, "end": e["end"],
                       "at": t["at"], "shape": t["shape"], "from": e["from"]}  # fmt: skip
                for name, layer in layers.items():
                    row[name] = layer.refuse_point(w, *t["at"]) is not None
                is_click = bool(e.get("clicked")) and i == len(e["target"]) - 1
                if is_click:
                    row["t_click"] = int(e["t_click"])
                    clicks.append(row)
                else:
                    hovers.append(row)
    contacts = contact_clicks(events, [c["t_click"] for c in clicks])
    for c in clicks:
        c["contact_gid"] = contacts.get(c["t_click"])
    near = {n: lay.near_cells() for n, lay in layers.items()}
    out: dict[str, Any] = {"session": session.name, "map": mname,
                           "routes": len(routes), "scored_routes": len(scored),
                           "clicks": len(clicks), "hovers": len(hovers),
                           "contacts": [{k: c[k] for k in ("route", "end", "at", "from",
                                                           "contact_gid", *layers)}
                                        for c in clicks if c["contact_gid"] is not None],
                           }  # fmt: skip
    for name in layers:
        sc = [c for c in clicks if c["scored"]]
        out[name] = {
            "npcs": len(layers[name].npcs),
            "clicks_refused": sum(c[name] for c in clicks),
            "contacts_refused": sum(c[name] for c in clicks if c["contact_gid"] is not None),
            "hovers_refused": sum(h[name] for h in hovers),
            "scored_routes_with_a_refused_click": len({c["route"] for c in sc if c[name]}),
            "scored_clicks_refused": sum(c[name] for c in sc),
            "substitutes_in_near_cells": [s for s in subs if tuple(s["cell"]) in near[name]],
            "goals_in_near_cells": sum(1 for r in routes if r["record_id"] in scored and tuple(
                r["outcome"]["evidence"]["goal"]) in near[name]),
        }  # fmt: skip
    return out


# --- walk@12-15's TALK-cell memory vs the packets -------------------------------------------------


def remembered(session: Path, camera_gat: tuple[Any, Any] | None = None) -> dict[str, Any]:
    """Every TALK read of every click step: the cell walk@12's memory stored (the picking model's
    cell under the pixel, as logged) re-computed offline, and the drawn NPC whose feet are nearest
    the pixel inside the PROVISIONAL footprint (packets), with the offsets."""
    from poring_dataset import picking

    man = json.loads((session / "manifest.json").read_text())
    events = read_events(session)
    camera, gat = camera_gat or load_map(man["map"])
    npcs = static_npcs(events)
    fp = nc.PROVISIONAL
    rows = []
    for rt in read_records(session):
        if not rt.get("rule") or "/" in rt["rule"]:
            continue
        for e in rt["outcome"]["evidence"].get("events", []):
            if "from" not in e:
                continue
            pos = tuple(e["from"])
            for t in e.get("target", []):
                if t["shape"] != "talk":
                    continue
                pc = picking.pick_cells(camera, gat, pos, np.array([t["at"]], dtype=float))[0]
                cell = [pos[0] + int(pc[0]), pos[1] + int(pc[1])]
                cands = []
                for g, s in npcs.items():
                    ((fu, fv),) = project_feet(camera, gat, pos, [s["cell"]])
                    du, dv = t["at"][0] - fu, t["at"][1] - fv
                    if -fp.left <= du <= fp.right and -fp.up <= dv <= fp.down:
                        cands.append((abs(du) + abs(dv) / 3, g, s, du, dv))
                row: dict[str, Any] = {"from": list(pos), "at": t["at"], "computed_cell": cell,
                                       "logged": [list(c) for c in e.get("talk_cells", [])],
                                       "end": e["end"]}  # fmt: skip
                row["reproduced"] = cell in row["logged"]
                if cands:
                    _, g, s, du, dv = min(cands, key=lambda c: c[0])
                    row.update({"npc_gid": g, "npc_job": s["job"], "npc_cell": list(s["cell"]),
                                "offset_cell": [cell[0] - s["cell"][0], cell[1] - s["cell"][1]],
                                "offset_px": [round(du), round(dv)],
                                "candidates": len(cands)})  # fmt: skip
                rows.append(row)
    offs = Counter(tuple(r["offset_cell"]) for r in rows if "offset_cell" in r)
    return {"session": session.name, "talk_reads": len(rows),
            "reproduced": sum(r["reproduced"] for r in rows),
            "remembered_is_npc_cell": sum(1 for r in rows if r.get("offset_cell") == [0, 0]),
            "offset_cells": {f"{k[0]},{k[1]}": v for k, v in sorted(offs.items())},
            "rows": rows}  # fmt: skip


# --- the colour check: a shift that restores the match -------------------------------------------


def best_shift(refs: Any, a: Any, mask: Any, want: str = "talk", r: int = SHIFT_R
               ) -> dict[str, Any] | None:  # fmt: skip
    """The smallest integer shift (|dx| + |dy|, at most ``r`` each) of the observed crop and its
    mask after which walk6's two-sided match reads ``want``; None if none does."""
    order = sorted(((dx, dy) for dx in range(-r, r + 1) for dy in range(-r, r + 1)),
                   key=lambda s: (abs(s[0]) + abs(s[1]), s))  # fmt: skip
    for dx, dy in order:
        sa = np.roll(np.roll(np.asarray(a), dy, 0), dx, 1)
        sm = np.roll(np.roll(np.asarray(mask, dtype=bool), dy, 0), dx, 1)
        got = refs.match(sa, sm)
        if got["shape"] == want:
            return {"shift": [dx, dy], "iou": got["iou"], "col": got["col"]}
    return None


def blurred(refs: Any) -> Any:
    """The references with each crop box-blurred 3x3 (masks unchanged): a match that passes only
    against these says the observed cursor was SOFTENED (a codec pass), not moved."""
    a = np.asarray(refs.a, dtype=float)
    p = np.pad(a, ((0, 0), (1, 1), (1, 1), (0, 0)), mode="edge")
    b = sum(p[:, 1 + dy : p.shape[1] - 1 + dy, 1 + dx : p.shape[2] - 1 + dx]
            for dy in (-1, 0, 1) for dx in (-1, 0, 1)) / 9.0  # fmt: skip
    return type(refs)(np.rint(b).astype(np.uint8), refs.m, refs.cls)


def refs_shift(refs: Any, want: str = "talk", src_prefix: str = "npc/",
               shifts: Sequence[tuple[int, int]] = ((0, 0), (1, 0), (0, 1), (1, 1), (-1, 0),
                                                    (0, -1), (2, 0), (0, 2)),
               src: Sequence[str] | None = None) -> dict[str, Any]:  # fmt: skip
    """Leave-one-out over the references of class ``want`` (source prefix ``src_prefix``): each
    crop and its mask SHIFTED by (dx, dy), matched against all the others. What a 1-2 px
    misregistration does to the two-sided match (analysis c of the planning doc)."""
    names = list(src) if src is not None else [""] * len(refs.cls)
    idx = [i for i, c in enumerate(refs.cls) if c == want and names[i].startswith(src_prefix)]
    out: dict[str, Any] = {"refs": len(idx)}
    for dx, dy in shifts:
        got: Counter[str] = Counter()
        ious, cols = [], []
        for i in idx:
            keep = np.arange(len(refs.cls)) != i
            others = type(refs)(
                refs.a[keep], refs.m[keep], [c for c, k in zip(refs.cls, keep, strict=True) if k]
            )
            a = np.roll(np.roll(refs.a[i], dy, 0), dx, 1)
            m = np.roll(np.roll(refs.m[i], dy, 0), dx, 1)
            ex = explain(others, a, m)
            got[ex["shape"]] += 1
            ious.append(ex["best"]["iou"])
            cols.append(ex["best"]["col"])
        out[f"{dx},{dy}"] = {"read": dict(got), "best_iou_median": round(float(np.median(ious)), 3),
                             "best_col_median": round(float(np.median(cols)), 3)}  # fmt: skip
    return out


def explain(refs: Any, a: Any, mask: Any) -> dict[str, Any]:
    """walk6's verdict plus the best-IoU reference's class and REAL colour agreement (walk6 reports
    col 0.0 for every unknown: a placeholder, not a measurement)."""
    out = dict(refs.match(a, mask))
    m = np.asarray(mask, dtype=bool)
    if m.sum():
        inter = (refs.m & m).reshape(len(refs.cls), -1).sum(1)
        union = (refs.m | m).reshape(len(refs.cls), -1).sum(1)
        iou = inter / np.maximum(union, 1)
        j = int(np.argmax(iou))
        ov = refs.m[j] & m
        d = np.abs(np.asarray(a)[..., :3].astype(np.int16) - refs.a[j]).max(-1)[ov]
        out["best"] = {"cls": refs.cls[j], "iou": round(float(iou[j]), 3),
                       "col": round(float((d < 40).mean()), 3) if ov.any() else 0.0}  # fmt: skip
    return out


def shift_report(paths: Sequence[Path], refs: Any, want: str = "talk") -> dict[str, Any]:
    """Per saved crop: the verdict, the best-IoU reference's real colour, and for a miss whether a
    1-2 px shift (misregistration) or blurred references (a softening codec pass) restore it."""
    soft = blurred(refs)
    rows = []
    for p in paths:
        z = np.load(p)
        a, mask = z["a"], z["mask"]
        ex = explain(refs, a, mask)
        row = {"npz": p.name, "shape": ex["shape"], "best": ex.get("best")}
        if ex["shape"] != want:
            row["shift"] = best_shift(refs, a, mask, want)
            row["blur_restores"] = soft.match(a, mask)["shape"] == want
        rows.append(row)
    fails = [r for r in rows if r["shape"] != want]
    cfail = [r for r in fails if r.get("best") and r["best"]["iou"] >= SHAPE_MATCH_IOU]
    return {"crops": len(rows), "read_" + want: len(rows) - len(fails),
            "colour_fails": len(cfail),
            "colour_fails_restored_by_shift": sum(1 for r in cfail if r.get("shift")),
            "colour_fails_restored_by_blur": sum(1 for r in cfail if r.get("blur_restores")),
            "rows": rows}  # fmt: skip


# --- the targeted test's judge -------------------------------------------------------------------


def verdict(reads: Sequence[dict[str, Any]], grabs: int = 3) -> str:
    """Prober9.read's verdict from a timed series: the first non-unknown shape among the first
    ``grabs`` grabs (walk6.SHAPE_GRABS), else unknown."""
    for rd in reads[:grabs]:
        if rd["shape"] != "unknown":
            return str(rd["shape"])
    return "unknown"


def click_metrics(clicks: Sequence[dict[str, Any]], events: list[dict[str, Any]], camera: Any,
                  gat: Any, layers: dict[str, Any]) -> dict[str, Any]:  # fmt: skip
    """The click arm's metrics over ``clicks``: what the server did, the L3 arms, the dialogs."""

    def table(d: dict[tuple[Any, ...], list[bool]]) -> dict[str, Any]:
        return {"/".join(str(x) for x in k): rate(sum(v), len(v)) for k, v in sorted(
            d.items(), key=lambda kv: tuple(str(x) for x in kv[0]))}  # fmt: skip

    outcome: Counter[str] = Counter()
    walk_contact = defaultdict(list)
    l3_arm: dict[str, Counter[str]] = {n: Counter() for n in layers}
    stops = []
    for rec in clicks:
        ev = rec["outcome"]["evidence"]
        gate = ev.get("gate", {})
        if ev.get("dialog", {}).get("action", "").startswith("stop"):
            stops.append({"cell": ev["cell"], "dialog": ev["dialog"]})
        if not gate.get("clicked"):
            outcome["not_clicked:" + str(gate.get("why"))] += 1
            continue
        t = int(gate["t_click"])
        con = [e for e in events if e.get("type") == "npc_contact"
               and 0 <= int(e["t_mono_ns"]) - t <= CONTACT_S * S]  # fmt: skip
        mv = [e for e in events if e.get("type") == "self_move_request"
              and 0 <= int(e["t_mono_ns"]) - t <= MOVE_S * S]  # fmt: skip
        res = "npc_contact" if con else "self_move_request" if mv else "nothing"
        outcome[res] += 1
        ring = max(abs(ev["cell"][0] - ev["npc_cell"][0]), abs(ev["cell"][1] - ev["npc_cell"][1]))
        for key in (("all",), ("ring", ring), ("npc", ev["npc"])):
            walk_contact[key].append(res == "npc_contact")
        w = world(camera, gat, ev["stand"])
        for n, layer in layers.items():
            refused = layer.refuse_point(w, *ev["at"]) is not None
            l3_arm[n][f"{'refused' if refused else 'allowed'}:{res}"] += 1
    arms = {}
    for n, c in l3_arm.items():
        contacts = c["refused:npc_contact"] + c["allowed:npc_contact"]
        allowed = sum(v for k, v in c.items() if k.startswith("allowed:"))
        arms[n] = {"counts": dict(c),
                   "contacts_refused": rate(c["refused:npc_contact"], contacts),
                   "contacts_left_with_layer": c["allowed:npc_contact"],
                   "contact_rate_among_allowed": rate(c["allowed:npc_contact"], allowed),
                   "moves_refused (cost)": rate(c["refused:self_move_request"],
                                                c["refused:self_move_request"]
                                                + c["allowed:self_move_request"])}  # fmt: skip
    return {
        "click_outcomes": dict(outcome),
        "walk_read_but_contact": table(walk_contact),
        "l3_arms": arms,
        "dialog_stops": stops,
    }


SEGMENT_GAP_S = 600  # a resume after a stop for a person is a new segment (3.32a amendment)


Segment = tuple[dict[str, Any], list[dict[str, Any]]]


def segments(clicks: Sequence[dict[str, Any]], events: list[dict[str, Any]],
             gap_s: float = SEGMENT_GAP_S) -> list[Segment]:  # fmt: skip
    """The click records split where two consecutive records are more than ``gap_s`` apart (each
    run of a resumed session): per segment its span, its gate (robust2 when its clicks carry the
    6-grab series, else v3), and replay_safety's request / act counts over its window."""
    import replay_safety

    recs = sorted(clicks, key=lambda r: int(r["t_mono_ns"]))
    runs: list[list[dict[str, Any]]] = []
    for rec in recs:
        if runs and int(rec["t_mono_ns"]) - int(runs[-1][-1]["t_mono_ns"]) <= gap_s * S:
            runs[-1].append(rec)
        else:
            runs.append([rec])
    out = []
    for k, run in enumerate(runs):
        t0 = int(run[0]["t_mono_ns"])
        t1 = max(int(r.get("t_done_ns") or r["t_mono_ns"]) for r in run) + 5 * S
        gates = set()
        for r in run:
            g = r["outcome"]["evidence"].get("gate", {})
            if "shapes" in g:  # robust2's 6-grab series (cursor_gate.read_series)
                gates.add("robust2")
            elif g.get("shape") is not None:  # a read without the series: the v3 gate
                gates.add("v3")
        seg = {"segment": k, "records": len(run), "t0_mono_ns": t0, "t1_mono_ns": t1,
               "gate": sorted(gates), "safety": replay_safety.judge(events, t0, t1)}  # fmt: skip
        out.append((seg, run))
    return out


def score(
    session: Path,
    layers: dict[str, Any] | None = None,
    camera_gat: tuple[Any, Any] | None = None,
    kb_dir: Path = nc.KB_DIR,
    refs: Any = None,
) -> dict[str, Any]:
    """The targeted test's metrics (docs/planning/npc-click-test.md, 5.5). ``refs``: the cursor
    references, to sort each colour fail by what restores it (C1 shift, C2 blur) from its crop."""
    from poring_dataset import picking
    from poring_dataset.timeline import Timeline

    man = json.loads((session / "manifest.json").read_text())
    mname = man["map"]
    events = read_events(session)
    recs = read_records(session)
    probes = [r for r in recs if r.get("rule") == PROBE]
    clicks = [r for r in recs if r.get("rule") == CLICK]
    tl = Timeline(events) if events else None
    camera, gat = camera_gat or load_map(mname)
    npcs = static_npcs(events)
    by_cell = {s["cell"]: (g, s) for g, s in npcs.items()}
    if layers is None:
        kb_npcs, _ = nc.load_l3_npcs(mname, kb_dir)
        full = [nc.StaticNpc(mname, s["cell"], f"gid:{g}", str(s["job"]), "packets")
                for g, s in npcs.items()]  # fmt: skip
        layers = {"l3_kb": nc.NoClickLayer(kb_npcs), "l3_complete": nc.NoClickLayer(full)}

    def at_stand(rec: dict[str, Any]) -> bool | None:
        if tl is None:
            return None
        fw = tl.frame_world(int(rec["t_mono_ns"]))
        if fw.self_pos is None:
            return None
        ev = rec["outcome"]["evidence"]
        return (round(fw.self_pos[0]), round(fw.self_pos[1])) == tuple(ev["stand"])

    # probes: the TALK read rate, the colour fails, the remembered cell
    talk = defaultdict(list)
    colour = defaultdict(list)
    offsets: Counter[tuple[int, int]] = Counter()
    causes: Counter[str] = Counter()
    soft = None if refs is None else blurred(refs)
    off_stand = 0
    for rec in probes:
        ev = rec["outcome"]["evidence"]
        if at_stand(rec) is False:
            off_stand += 1
            continue
        v = ev.get("verdict") or verdict(ev["reads"])
        npc = by_cell.get(tuple(ev["npc_cell"]))
        job = None if npc is None else npc[1]["job"]
        for key in (("all",), ("job", job), ("kind", ev["kind"]), ("npc", ev["npc"]),
                    ("stand", ev["npc"], tuple(ev["stand"])),
                    ("offset", ev["kind"], tuple(ev["offset"]))):  # fmt: skip
            talk[key].append(v == "talk")
        first = ev["reads"][0] if ev["reads"] else {}
        best = first.get("best") or {}
        cfail = v == "unknown" and float(best.get("iou", 0.0)) >= SHAPE_MATCH_IOU
        for key in (("all",), ("job", job), ("kind", ev["kind"])):
            colour[key].append(cfail)
        if cfail:
            want = "walk" if ev["kind"] == "control" else "talk"
            later = any(rd["shape"] == want for rd in ev["reads"][3:])
            causes["a_later_grab_passed" if later else "no_later_grab_passed"] += 1
            crop = session / str(ev.get("crop", ""))
            if refs is not None and ev.get("crop") and crop.exists():
                z = np.load(crop)
                shifted = best_shift(refs, z["a"], z["mask"], want) is not None
                soft_ok = soft is not None and soft.match(z["a"], z["mask"])["shape"] == want
                causes["C1_restored_by_shift" if shifted else "C1_not_by_shift"] += 1
                causes["C2_restored_by_blur" if soft_ok else "C2_not_by_blur"] += 1
        if v == "talk":
            pos = tuple(ev["stand"])
            pc = picking.pick_cells(camera, gat, pos, np.array([ev["at"]], dtype=float))[0]
            cell = (pos[0] + int(pc[0]), pos[1] + int(pc[1]))
            offsets[(cell[0] - ev["npc_cell"][0], cell[1] - ev["npc_cell"][1])] += 1

    def table(d: dict[tuple[Any, ...], list[bool]]) -> dict[str, Any]:
        return {"/".join(str(x) for x in k): rate(sum(v), len(v)) for k, v in sorted(
            d.items(), key=lambda kv: tuple(str(x) for x in kv[0]))}  # fmt: skip

    clk = click_metrics(clicks, events, camera, gat, layers)
    det = recall(events, batches_from_log(session)) if events else None
    return {
        "session": session.name,
        "map": mname,
        "probes": len(probes),
        "clicks": len(clicks),
        "probes_off_stand": off_stand,
        "talk_read_rate": table(talk),
        "colour_fail_rate": table(colour),
        "colour_fail_causes": dict(causes),
        "remembered_cell_offset": {f"{k[0]},{k[1]}": v for k, v in sorted(offsets.items())},
        **clk,
        "segments": [
            {**seg, **click_metrics(seg_recs, events, camera, gat, layers)}
            for seg, seg_recs in segments(clicks, events)
        ],  # fmt: skip
        "detector": None if det is None else {k: v for k, v in det.items() if k != "rows"},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("score", "replay-l3", "remembered"):
        sp = sub.add_parser(name)
        sp.add_argument("session", type=Path)
        sp.add_argument("--kb", type=Path, default=nc.KB_DIR, help="the L3 KB (data/kb)")
        sp.add_argument("--refs", type=Path, help="cursor references (score: default v3)")
    rc = sub.add_parser("recall")
    rc.add_argument("session", type=Path)
    rc.add_argument("--frames", type=Path, help="NNNN-<t_ns>.png frames instead of the log")
    rc.add_argument(
        "--run-detector",
        action="store_true",
        help="the CPU detector on --frames, or on the session's route snapshots",
    )
    rc.add_argument("--threads", type=int, default=4)
    rc.add_argument("--rows", action="store_true")
    sh = sub.add_parser("shift")
    sh.add_argument("npz", type=Path, nargs="+")
    sh.add_argument("--want", default="talk")
    sh.add_argument("--refs", type=Path, help="cursor references (default: walk@11's v3)")
    rs = sub.add_parser("refs-shift", help="leave-one-out: a shifted reference vs the others")
    rs.add_argument("--refs", type=Path)
    rs.add_argument("--want", default="talk")
    rs.add_argument("--src-prefix", default="npc/")
    a = ap.parse_args()
    if a.cmd == "score":
        import walk6 as w6
        import walk10 as w10

        path = a.refs or w10.CURSOR_REFS_V2
        out = score(a.session, kb_dir=a.kb,
                    refs=w6.CursorRefs.load(path) if Path(path).exists() else None)  # fmt: skip
    elif a.cmd == "replay-l3":
        out = replay_l3(a.session, a.kb)
    elif a.cmd == "remembered":
        out = remembered(a.session)
    elif a.cmd == "recall":
        if a.frames is not None and not a.run_detector:
            raise SystemExit("--frames needs --run-detector (no log for them)")
        batches = (batches_from_frames(frame_files(a.session, a.frames), a.threads)
                   if a.run_detector else batches_from_log(a.session))  # fmt: skip
        out = recall(read_events(a.session), batches)
        if not a.rows:
            out.pop("rows")
        out["session"] = a.session.name
    else:
        import walk6 as w6
        import walk10 as w10

        path = a.refs or w10.CURSOR_REFS_V2
        refs = w6.CursorRefs.load(path)
        if a.cmd == "shift":
            out = shift_report(a.npz, refs, a.want)
        else:
            src = [str(x) for x in np.load(path)["src"]]
            out = refs_shift(refs, a.want, a.src_prefix, src=src)
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
