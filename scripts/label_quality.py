#!/usr/bin/env python3
"""Label quality: the auto-labels (v0, v1) against Batt's hand-checked gold set, gap by gap
(Batt 2026-10-13, decision 11: "fix LABEL QUALITY toward my gold convention ... before labels
v2"; docs/planning/label-quality.md).

    label_quality.py dump SESSION [--out JSON] [--data DIR] [--bundles DIR] [--mapcache DIR]
        The gold frames: Batt's hand boxes, the /qa bundle he edited, the v0 and v1 labels
        (qa_export.Labeler: build_frame_cache's labeller) and every unit's projection facts.
    label_quality.py cache DUMP SHARD
        The reproduced v1 labels against the v1 cache's own YOLO txt (the reproduction proof).
    label_quality.py report DUMP
        Matching (IoU >= 0.5 and position), per-pair geometry, the systematic gaps, the FN / FP
        causes and the ranked single-gap what-ifs -> JSON on stdout.
    label_quality.py peek SESSION SECONDS OUT.png
        One recorded frame with its v1 labels drawn, written under /dev/shm only (to LOOK at a gap).
    label_quality.py models DUMP PRED.json [PRED.json ...]
        A detector's gold-set misses beside the labels' own (its predict_dir output; no model run).
    label_quality.py census CACHE_MANIFEST [--step-s 1]
        How much of a frame cache's sessions each gap touches (packets only).

The dump holds client-derived numbers (the boxes of a recorded session): it goes to /dev/shm, never
into git. Every number in the planning doc comes from ``report`` / ``census`` output.

OFFLINE ONLY: packets are ground truth for LABELS (ADR-0007), never an agent input.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import statistics
import sys
import tarfile
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

NAS = Path("/mnt/poring-lab-datasets")
SCRATCH = Path("/dev/shm/poring-lab-tmp/label-quality")
CLASSES = ("player", "monster", "npc")
SIZE = (1280, 720)
UI_NAMES = ("basic_info", "hotkeys", "top_window", "chat", "notifier", "minimap")  # UI_RECTS order
SELF_LAGS_MS = tuple(range(-100, 301, 25))  # the self-lag what-if grid (ms)

Rect = tuple[float, float, float, float]  # x0, y0, x1, y1


# --- geometry (pure) ------------------------------------------------------------------------------


def rect_of(b: dict[str, Any]) -> Rect:
    return float(b["x1"]), float(b["y1"]), float(b["x2"]), float(b["y2"])


def centre(r: Rect) -> tuple[float, float]:
    return (r[0] + r[2]) / 2.0, (r[1] + r[3]) / 2.0


def iou(a: Rect, b: Rect) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def inside(p: tuple[float, float], r: Rect) -> bool:
    return r[0] <= p[0] <= r[2] and r[1] <= p[1] <= r[3]


# --- dump: the gold frames, every label source, the projection facts (needs the session) ---------


def _box(d: dict[str, Any], **extra: Any) -> dict[str, Any]:
    out = {
        "cls": d["cls"],
        "gid": d.get("gid"),
        "x1": float(d["x1"]),
        "y1": float(d["y1"]),
        "x2": float(d["x2"]),
        "y2": float(d["y2"]),
    }
    for k in ("kind", "state", "phase_known", "facing"):
        if k in d:
            out[k] = d[k]
    out.update(extra)
    return out


def setup(data: Path, mapcache_dir: Path | None = None) -> None:
    """Point qa_export at a checkout's KB (``data``: its gitignored data/) and, when this runs from
    a worktree that has none, at the generated map caches (GPL-derived, never committed)."""
    import qa_export

    from poring_dataset import mapcache

    if mapcache_dir is not None and not getattr(mapcache, "_label_quality", False):
        load = mapcache.load
        mapcache.load = lambda directory=mapcache_dir, **kw: load(directory, **kw)
        mapcache._label_quality = True  # type: ignore[attr-defined]
    qa_export.KB_CLASSES = data / "kb" / "classes.json"
    qa_export.KB_SPRITE_NAMES = data / "kb" / "monster_sprite_names.json"


def frame_facts(v1: Any, t: int, lags: Sequence[int] = SELF_LAGS_MS) -> dict[str, Any]:
    """One frame (capture time ``t``): the v1 labels exactly as qa_export.Labeler gives them
    (build_frame_cache's labels), and every unit's projection facts, so ``relabel`` can re-derive
    the labels with a knob turned. ``v1``: a qa_export.Labeler(labels="v1")."""
    import numpy as np

    from poring_dataset.labels import BOX_PX, OBJTYPE_CLASS, STATE_ACTION, drawn
    from poring_dataset.render import Actor, load_scene, predict_sprite
    from poring_dataset.ui_layout import UI_RECTS, covered_fraction

    tw = t - int(v1.offset_ms * 1e6)
    b1 = v1.boxes(t)
    world = v1.timeline.frame_world(tw)
    row: dict[str, Any] = {
        "t_mono_ns": t,
        "map": world.map,
        "self_pos": world.self_pos,
        "self_heading": world.self_heading,
        "v1": None if b1 is None else [_box(b) for b in b1],
        "entities": {},
    }
    if world.self_pos is None or world.map is None or b1 is None:
        return row
    projector, which, _yaw = v1.projectors[world.map]
    sx, sy = world.self_pos
    scene = load_scene(v1.camera, world.map, world.self_pos, indoor_table=v1.indoor)
    origin = (int(round(sx)), int(round(sy)))

    def project(
        x: float, y: float, o: tuple[int, int] = origin, s: tuple[float, float] = (sx, sy)
    ) -> tuple[float, float]:
        ((u, v),) = projector(np.array([[x - s[0], y - s[1]]]), o)
        return float(u), float(v)

    row["self_px"] = list(project(sx, sy))
    row["projection"] = which
    row["self_moving"] = not (float(sx).is_integer() and float(sy).is_integer())
    # where every unit would be drawn if OUR character were where the packets put it ``lag`` ms
    # earlier (the units themselves unchanged): the per-unit pixel shift
    lag_shift: dict[str, dict[str, list[float]]] = {}
    for lag in lags:
        past = v1.timeline.frame_world(tw - lag * 1_000_000).self_pos
        if past is None or past == world.self_pos:
            continue
        o2 = (int(round(past[0])), int(round(past[1])))
        lag_shift[str(lag)] = {
            str(ent.gid): [
                a - b
                for a, b in zip(project(ent.x, ent.y, o2, past), project(ent.x, ent.y), strict=True)
            ]
            for ent in world.entities
        }
    row["self_lag_shift"] = lag_shift
    seen = {e.gid for e in world.entities}
    for ent in world.entities:
        cls = OBJTYPE_CLASS.get(ent.objtype)
        u, v = project(ent.x, ent.y)
        e: dict[str, Any] = {
            "cls": cls,
            "objtype": ent.objtype,
            "job": ent.job,
            "x": ent.x,
            "y": ent.y,
            "moving": ent.moving,
            "heading": ent.heading,
            "hidden": ent.hidden,
            "drawn": drawn(ent.objtype, ent.job),
            "foot_px": [u, v],
        }
        if cls in BOX_PX:
            w, h = BOX_PX[cls]
            v0_box = (u - w / 2, v - h, u + w / 2, v)
            e["v0_box"] = list(v0_box)
            e["v0_cover_by_rect"] = [covered_fraction(v0_box, (r,)) for r in UI_RECTS]
        st = v1.timeline.state(ent.gid, tw)
        if st is not None:
            e.update(
                state=st.state,
                facing=st.facing,
                elapsed_ms=st.elapsed_ms,
                duration_ms=st.duration_ms,
            )
        sheet = v1.sheets(ent.job) if cls == "monster" else None
        e["sheet"] = sheet is not None
        if sheet is not None and st is not None:  # labels_for_v1's call, verbatim
            action = STATE_ACTION.get(st.state, 0)
            one_shot = action in (2, 3, 4)
            heading = st.facing if st.facing is not None else (ent.heading or 0)
            pred = predict_sprite(
                Actor(
                    (float(ent.x), float(ent.y)),
                    int(heading),
                    action,
                    elapsed_ms=st.elapsed_ms if one_shot else None,
                    duration_ms=st.duration_ms,
                ),
                sheet,
                scene,
                v1.k,
            )
            if pred is not None:
                idle = sheet.act.action_index(0, pred.direction)
                e["v1_pred"] = {
                    "box": list(pred.box),
                    "anchor_px": list(pred.anchor_px),
                    "scale": pred.scale,
                    "depth": pred.depth,
                    "action": pred.action,
                    "direction": pred.direction,
                    "motion": pred.motion,
                    "phase_known": pred.phase_known,
                    "kind": pred.box_kind,
                    "cover_by_rect": [covered_fraction(pred.box, (r,)) for r in UI_RECTS],
                    # sprite px around the anchor: the drawn action's envelope and each of its
                    # frames, and the IDLE envelope (what a still unit shows)
                    "extent": list(sheet.envelope(pred.action_index) or ()),
                    "motion_extents": [
                        list(x) if x is not None else None
                        for x in (
                            sheet.extent(pred.action_index, m)
                            for m in range(sheet.motions(pred.action_index))
                        )
                    ],
                    "idle_extent": list(sheet.envelope(idle) or ()),
                }
        row["entities"][str(ent.gid)] = e
    # units playing their die animation are not in world.entities (labels_for_v1 skips them)
    for st in v1.timeline.states(tw):
        if st.gid in seen or st.gid == world.aid or st.state != "dying":
            continue
        row["entities"][str(st.gid)] = {
            "cls": "monster" if st.job is not None and st.job >= 1000 else None,
            "job": st.job,
            "x": st.x,
            "y": st.y,
            "state": "dying",
            "dying": True,
            "foot_px": list(project(st.x, st.y)),
        }
    return row


def dump(
    session: str,
    datasets: Path,
    data: Path,
    bundle_dir: Path | None,
    k: float,
    mapcache_dir: Path | None = None,
) -> dict[str, Any]:
    """Everything ``report`` needs, per gold frame (no pixels): Batt's hand boxes, the /qa bundle he
    edited, the v0 and v1 labels (qa_export.Labeler, build_frame_cache's labeller), whether our GM
    lay dead (labels_v2.self_dead_spans), and frame_facts."""
    import label_iou
    import qa_export

    from poring_dataset.labels_v2 import self_dead_spans
    from poring_dataset.timeline import infer_self_aid

    setup(data, mapcache_dir)
    hand_path = data / "qa" / "handcheck" / f"{session}.json"
    hand = json.loads(hand_path.read_text())
    path = datasets / session
    v0 = qa_export.Labeler(path, labels="v0")
    v1 = qa_export.Labeler(path, labels="v1", k=k)
    with gzip.open(path / "packets.states.jsonl.gz", "rt") as fh:
        events = [json.loads(line) for line in fh]
    aid = infer_self_aid(events)
    dead = self_dead_spans(events, aid)
    bundle: dict[int, Any] = {}
    if bundle_dir is not None and (bundle_dir / session / "labels.json").exists():
        doc = json.loads((bundle_dir / session / "labels.json").read_text())
        bundle = {int(f["frame_id"]): f for f in doc["frames"]}
    frames = []
    for f in hand["frames"]:
        t, fid = int(f["t_mono_ns"]), int(f["frame_id"])
        tw = t - int(v1.offset_ms * 1e6)
        b0 = v0.boxes(t)
        frames.append(
            {
                "frame_id": fid,
                **frame_facts(v1, t),
                "self_dead": any(a <= tw <= b for a, b in dead),
                "hand": [_box(b) for b in f["boxes"]],
                "v0": None if b0 is None else [_box(b) for b in b0],
                "bundle": [_box(b) for b in bundle[fid]["boxes"]] if fid in bundle else None,
            }
        )
    return {
        "session": session,
        "handcheck_sha256": label_iou.sha256(hand_path),
        "offset_ms": v1.offset_ms,
        "k": k,
        "camera": v1.camera_path.name,
        "self_aid": aid,
        "dead_spans_ns": dead,
        "size": hand.get("size", list(SIZE)),
        "sheets_missing": {str(j): r for j, r in (v1.sheets.missing if v1.sheets else {}).items()},
        "frames": frames,
    }


# --- peek: one recorded frame with its v1 labels drawn (to LOOK at a gap; pixels stay in RAM) ---


def session_frame(path: Path, at_s: float) -> tuple[int, Any]:
    """(capture time, RGB game-region image) of the recorded frame nearest ``at_s`` seconds after
    the recording's t0. H.264: only the bytes from the GOP's IDR to that frame are read (never the
    whole stream); PNG shards: the tar is walked by its headers and one PNG is read."""
    import numpy as np

    manifest = json.loads((path / "manifest.json").read_text())
    want = int(manifest["t0_mono_ns"]) + int(at_s * 1e9)
    if (manifest.get("format") or "png") == "h264":
        import av

        from poring_dataset.h264 import read_index

        units = read_index(path / "stream.idx.csv")
        target = min(range(len(units)), key=lambda i: abs(units[i].t_ns - want))
        start = max(i for i in range(target + 1) if units[i].idr)
        with open(path / "stream.h264", "rb") as fh:
            fh.seek(units[start].offset)
            blob = fh.read(units[target].offset + units[target].length - units[start].offset)
        ctx = av.CodecContext.create("h264", "r")
        img = None
        for i in range(start, target + 1):
            o = units[i].offset - units[start].offset
            for fr in ctx.decode(av.Packet(blob[o : o + units[i].length])):
                if i == target:
                    img = fr.to_ndarray(format="rgb24")
        if img is None:
            raise SystemExit("the frame decoded to nothing")
        x, y, w, h = (int(v) for v in manifest["game_region"])
        return int(units[target].t_ns), img[y : y + h, x : x + w]
    from PIL import Image

    best: tuple[int, str, str] | None = None
    for shard in manifest["shards"]:
        with tarfile.open(path / shard, "r:") as tar:
            for m in tar:
                if m.name.endswith(".json"):
                    meta = tar.extractfile(m)
                    assert meta is not None
                    t = int(json.loads(meta.read())["t_mono_ns"])
                    if best is None or abs(t - want) < abs(best[0] - want):
                        best = (t, shard, m.name.rsplit(".", 1)[0])
    if best is None:
        raise SystemExit("no frames")
    with tarfile.open(path / best[1], "r:") as tar:
        png = tar.extractfile(tar.getmember(best[2] + ".png"))
        assert png is not None
        return best[0], np.asarray(Image.open(png).convert("RGB"))


def peek(session: str, at_s: float, out: Path, datasets: Path, data: Path, k: float,
         mapcache_dir: Path | None = None) -> dict[str, Any]:  # fmt: skip
    """One recorded frame with its v1 labels drawn (monsters yellow, NPCs and players cyan), saved
    to ``out`` -- which must be under /dev/shm: client pixels never land on the disk or in git."""
    if not str(out.resolve()).startswith("/dev/shm/"):
        raise SystemExit(f"{out}: peek writes client pixels to /dev/shm only")
    import qa_export
    from PIL import Image, ImageDraw

    setup(data, mapcache_dir)
    path = datasets / session
    t, img = session_frame(path, at_s)
    v1 = qa_export.Labeler(path, labels="v1", k=k)
    boxes = v1.boxes(t) or []
    world = v1.timeline.frame_world(t - int(v1.offset_ms * 1e6))
    im = Image.fromarray(img)
    draw = ImageDraw.Draw(im)
    for b in boxes:
        colour = (255, 255, 0) if b["cls"] == "monster" else (0, 255, 255)
        draw.rectangle([b["x1"], b["y1"], b["x2"], b["y2"]], outline=colour, width=2)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    t0 = int(json.loads((path / "manifest.json").read_text())["t0_mono_ns"])
    return {"session": session, "t_s": round((t - t0) / 1e9, 3), "map": world.map,
            "self_pos": world.self_pos, "boxes": len(boxes), "out": str(out)}  # fmt: skip


# --- census: how much of a frame cache each gap touches (packets only, no pixels) ----------------

SCENE_MAPS = (
    "prt_fild08",
    "prt_church",
)  # build_frame_cache.SCENE_MAPS (test_label_quality pins it)
CENSUS_LAG_MS = 125
NEAR_MISS_PX = 40.0  # model_misses: a detection this close to a missed hand box is a near miss


def census_frame(f: dict[str, Any], lag_ms: int = CENSUS_LAG_MS) -> dict[str, Any]:
    """One frame's exposure to each gap (monster labels): the labels kept, the units the UI rule
    drops per window, the units dropped as less than half on screen though partly visible, and the
    whole-frame shift our own walk would cause at ``lag_ms`` (median over the units, px)."""
    kept = [b for b in f.get("v1") or [] if b["cls"] == "monster"]
    out: dict[str, Any] = {
        "monsters": len(kept),
        "walking": sum(1 for b in kept if b.get("state") == "walk"),
    }
    have = {str(b.get("gid")) for b in kept}
    for name in ("minimap", "chat", "top_window", "notifier"):
        extra = [
            b
            for b in relabel(f, "v1", ui_off=frozenset({name})) or []
            if b["cls"] == "monster" and str(b["gid"]) not in have
        ]
        out[f"ui_dropped:{name}"] = len(extra)
    edge = 0
    for gid, e in f.get("entities", {}).items():
        p = e.get("v1_pred")
        if gid in have or p is None or e.get("cls") != "monster":
            continue
        r = tuple(p["box"])
        c = _clip(r, SIZE)
        visible = c[2] > c[0] and c[3] > c[1]
        if visible and _kept(r, SIZE, 0.0) is None and _cover_of(r, frozenset()) < MAX_UI_COVER:
            edge += 1
    out["edge_dropped"] = edge
    shift = (f.get("self_lag_shift") or {}).get(str(lag_ms)) or {}
    mags = [
        math.hypot(*shift[str(b.get("gid"))])
        for b in f.get("v1") or []
        if str(b.get("gid")) in shift
    ]
    out["self_shift_px"] = statistics.median(mags) if mags else 0.0
    return out


def dead_span_walks(
    events: Sequence[dict[str, Any]], aid: int | None, spans: Sequence[tuple[int, int]], t0: int
) -> list[dict[str, Any]]:
    """Per dead-GM span: the last walk the server acknowledged for us before the death, and whether
    it came inside the damage motion of a hit on us (``act`` with our gid as target, ``dmotion``
    ms). Such a walk is one the client may never show (2026-10-13: the indoor-b death); if it does
    not, our position in the packets runs ahead of the camera for the whole span. Times are seconds
    from ``t0``; a CANDIDATE signature only -- pixels decide."""
    evs = sorted(events, key=lambda e: int(e["t_mono_ns"]))
    hits = [
        (int(e["t_mono_ns"]), float(e.get("dmotion") or 0))
        for e in evs
        if e.get("type") == "act"
        and aid is not None
        and e.get("target_gid") == aid
        and (e.get("damage") or 0) > 0
    ]
    out = []
    for a, b in spans:
        row: dict[str, Any] = {
            "start_s": round((a - t0) / 1e9, 2),
            "end_s": round((b - t0) / 1e9, 2) if b < 1 << 61 else None,
        }
        walks = [e for e in evs if e.get("type") == "self_move" and int(e["t_mono_ns"]) <= a]
        if walks:
            w = walks[-1]
            tw = int(w["t_mono_ns"])
            before = [h for h in hits if h[0] <= tw]
            row["last_walk"] = {
                "from": [w.get("x0"), w.get("y0")],
                "to": [w.get("x1"), w.get("y1")],
                "ms_before_death": round((a - tw) / 1e6),
                "ms_after_last_hit": round((tw - before[-1][0]) / 1e6) if before else None,
                "in_damage_motion": bool(before) and tw - before[-1][0] <= before[-1][1] * 1e6,
            }
        out.append(row)
    return out


def census(
    sessions: Sequence[tuple[str, str]],
    datasets: Path,
    data: Path,
    k: float,
    step_s: float,
    mapcache_dir: Path | None = None,
) -> dict[str, Any]:
    """Per session (and split): frames on a ``step_s`` grid between the recording's t0 and t1, kept
    by build_frame_cache's own rules (GM-command windows and off-scene maps skipped), and per frame
    census_frame -- plus relabel's reproduction check on every frame."""
    import qa_export

    from poring_dataset.labels_v2 import self_dead_spans
    from poring_dataset.timeline import infer_self_aid

    setup(data, mapcache_dir)
    rows: dict[str, dict[str, Any]] = {}
    for sid, split in sessions:
        path = datasets / sid
        manifest = json.loads((path / "manifest.json").read_text())
        v1 = qa_export.Labeler(path, labels="v1", k=k)
        name = (
            "packets.states.jsonl.gz"
            if (path / "packets.states.jsonl.gz").exists()
            else "packets.jsonl.gz"
        )
        with gzip.open(path / name, "rt") as fh:
            events = [json.loads(line) for line in fh]
        aid = infer_self_aid(events)
        dead = self_dead_spans(events, aid)
        spans = dead_span_walks(events, aid, dead, int(manifest["t0_mono_ns"]))
        tally: Counter[str] = Counter()
        shifts: list[float] = []
        t = int(manifest["t0_mono_ns"])
        while t <= int(manifest["t1_mono_ns"]):
            tw = t - int(v1.offset_ms * 1e6)
            world_map = (v1.timeline.frame_world(tw).map or "").removesuffix(".gat")
            t_next = t + int(step_s * 1e9)
            if world_map not in SCENE_MAPS:
                tally["off_scene"] += 1
                t = t_next
                continue
            f = frame_facts(v1, t, lags=(CENSUS_LAG_MS,))
            if f["v1"] is None:
                tally["gm_window"] += 1
                t = t_next
                continue
            tally["frames"] += 1
            tally["relabel_equal"] += same_boxes(relabel(f, "v1") or [], f["v1"])
            tally["indoor_frames"] += "indoor" in str(f.get("projection"))
            tally["self_moving_frames"] += bool(f.get("self_moving"))
            tally["self_dead_frames"] += any(a <= tw <= b for a, b in dead)
            for (a, b), sp in zip(dead, spans, strict=True):
                if a <= tw <= b:
                    sp["frames"] = sp.get("frames", 0) + 1
                    lw = sp.get("last_walk")
                    if lw and "shift_px_if_not_shown" not in lw and f.get("self_pos"):
                        # labels minus pixels, for a unit at our packet cell, if the camera
                        # stayed where that walk started
                        proj = v1.projectors[f["map"]][0]
                        sx, sy = f["self_pos"]
                        fx, fy = lw["from"]
                        import numpy as np

                        ((u0, v0),) = proj(np.array([[0.0, 0.0]]), (int(sx), int(sy)))
                        ((u1, v1_),) = proj(np.array([[sx - fx, sy - fy]]), (int(fx), int(fy)))
                        lw["shift_px_if_not_shown"] = [round(u0 - u1, 1), round(v0 - v1_, 1)]
            c = census_frame(f)
            shifts.append(c.pop("self_shift_px"))
            tally["frames_self_shift_gt_10px"] += shifts[-1] > 10
            tally["frames_self_shift_gt_20px"] += shifts[-1] > 20
            for key, n in c.items():
                tally[key] += n
            for key in ("ui_dropped:minimap", "ui_dropped:chat", "edge_dropped"):
                tally[f"frames_with_{key}"] += c[key] > 0
            t = t_next
        rows[sid] = {
            "split": split,
            **dict(tally),
            "self_shift_px_when_moving": describe(x for x in shifts if x > 0),
            "dead_spans": spans,
        }
        print(json.dumps({sid: rows[sid]}), file=sys.stderr, flush=True)
    totals: dict[str, Counter[str]] = defaultdict(Counter)
    for r in rows.values():
        for key, n in r.items():
            if isinstance(n, int) and not isinstance(n, bool):
                totals[r["split"]][key] += n
                totals["all"][key] += n
    return {
        "k": k,
        "step_s": step_s,
        "lag_ms": CENSUS_LAG_MS,
        "sessions": rows,
        "totals": {k_: dict(v) for k_, v in totals.items()},
    }


# --- cache: the reproduction proof (the v1 cache's own YOLO txt for the same frames) -------------


def parse_yolo(text: str, size: tuple[int, int] = SIZE) -> list[tuple[str, Rect]]:
    """YOLO lines (class cx cy w h, normalised) -> (class name, pixel rect)."""
    w, h = size
    out = []
    for line in text.splitlines():
        if not line.strip():
            continue
        c, cx, cy, bw, bh = line.split()
        x, y, ww, hh = float(cx) * w, float(cy) * h, float(bw) * w, float(bh) * h
        out.append((CLASSES[int(c)], (x - ww / 2, y - hh / 2, x + ww / 2, y + hh / 2)))
    return out


def compare_boxes(
    ours: Sequence[tuple[str, Rect]], theirs: Sequence[tuple[str, Rect]], tol: float = 0.05
) -> dict[str, Any]:
    """Order-free equality of two box lists within ``tol`` px per edge (YOLO txt keeps 6 decimals:
    ~0.004 px at 1280 x 720). Returns counts and the largest edge difference among the pairs."""
    left = list(theirs)
    worst = 0.0
    unmatched = 0
    for cls, r in ours:
        best, bi = math.inf, -1
        for i, (c2, r2) in enumerate(left):
            if c2 != cls:
                continue
            d = max(abs(a - b) for a, b in zip(r, r2, strict=True))
            if d < best:
                best, bi = d, i
        if bi < 0 or best > tol:
            unmatched += 1
            continue
        worst = max(worst, best)
        left.pop(bi)
    return {
        "ours": len(ours),
        "theirs": len(theirs),
        "equal": unmatched == 0 and not left,
        "unmatched_ours": unmatched,
        "unmatched_theirs": len(left),
        "max_edge_px": worst,
    }


def cache_txt(shard: Path, session: str, frame_ids: Iterable[int]) -> dict[int, str]:
    """The YOLO txt of the wanted frames from one cache shard. The tar is opened seekable, so only
    its headers and the small txt members are read, never the PNGs."""
    want = {f"{session}.{fid:09d}.txt": fid for fid in frame_ids}
    out: dict[int, str] = {}
    with tarfile.open(shard, "r:") as tar:
        for m in tar:
            fid = want.get(m.name)
            if fid is not None:
                fh = tar.extractfile(m)
                assert fh is not None
                out[fid] = fh.read().decode()
    return out


def cache_check(d: dict[str, Any], shard: Path) -> dict[str, Any]:
    frames = {f["frame_id"]: f for f in d["frames"] if f["v1"] is not None}
    txt = cache_txt(shard, d["session"], frames)
    rows = {}
    for fid, f in sorted(frames.items()):
        if fid not in txt:
            rows[fid] = {"in_cache": False}
            continue
        ours = [(b["cls"], rect_of(b)) for b in f["v1"]]
        rows[fid] = {"in_cache": True, **compare_boxes(ours, parse_yolo(txt[fid], d["size"]))}
    present = [r for r in rows.values() if r["in_cache"]]
    return {
        "shard": str(shard),
        "frames": len(frames),
        "in_cache": len(present),
        "equal": sum(1 for r in present if r["equal"]),
        "max_edge_px": max((r["max_edge_px"] for r in present), default=None),
        "per_frame": {str(k): v for k, v in rows.items()},
    }


# --- report: matching, geometry, causes, what-ifs (pure: a dump in, numbers out) -----------------


def greedy_iou(
    truth: Sequence[Rect], pred: Sequence[Rect], threshold: float = 0.5
) -> list[tuple[int, int, float]]:
    """poring_dataset.metrics.match's pairing (highest IoU first, one-to-one, >= threshold), but
    returning the pairs (truth index, predicted index, IoU) so each miss can be explained."""
    cand = sorted(
        ((iou(t, p), i, j) for i, t in enumerate(truth) for j, p in enumerate(pred)), reverse=True
    )
    used_t: set[int] = set()
    used_p: set[int] = set()
    out = []
    for value, i, j in cand:
        if value < threshold:
            break
        if i in used_t or j in used_p:
            continue
        used_t.add(i)
        used_p.add(j)
        out.append((i, j, value))
    return out


def greedy_position(truth: Sequence[Rect], pred: Sequence[Rect]) -> list[tuple[int, int, float]]:
    """label_iou.match_position's pairing (§5f: the predicted CENTRE inside the truth box,
    one-to-one by ascending centre distance), returning (truth index, predicted index, distance)."""
    cand = []
    for i, t in enumerate(truth):
        tx, ty = centre(t)
        for j, p in enumerate(pred):
            cx, cy = centre(p)
            if inside((cx, cy), t):
                cand.append((math.hypot(cx - tx, cy - ty), i, j))
    used_t: set[int] = set()
    used_p: set[int] = set()
    out = []
    for dist, i, j in sorted(cand):
        if i in used_t or j in used_p:
            continue
        used_t.add(i)
        used_p.add(j)
        out.append((i, j, dist))
    return out


def match_pairs(
    metric: str, truth: Sequence[Rect], pred: Sequence[Rect]
) -> list[tuple[int, int, float]]:
    return greedy_position(truth, pred) if metric == "position" else greedy_iou(truth, pred)


def _ratio(a: int, b: int) -> float | None:
    return round(a / b, 3) if b else None


def describe(values: Iterable[float], nd: int = 2) -> dict[str, Any]:
    """n, median, mean, p10, p90 (nearest-rank, like label_iou's p90)."""
    v = sorted(values)
    if not v:
        return {"n": 0}

    def q(p: float) -> float:
        return v[min(len(v) - 1, int(p * len(v)))]

    return {
        "n": len(v),
        "median": round(statistics.median(v), nd),
        "mean": round(statistics.fmean(v), nd),
        "p10": round(q(0.1), nd),
        "p90": round(q(0.9), nd),
    }


AutoOf = Callable[[dict[str, Any]], list[dict[str, Any]] | None]


def score(frames: Sequence[dict[str, Any]], auto_of: AutoOf, metric: str) -> dict[str, Any]:
    """Per class and overall TP / FP / FN, precision, recall and the matched-pair mean IoU (IoU
    metric) or centre distance median / p90 (position metric) -- label_iou's numbers, reproduced
    from the dump so that every what-if is scored by the same code."""
    per: dict[str, dict[str, Any]] = {c: {"tp": 0, "fp": 0, "fn": 0, "v": []} for c in CLASSES}
    n = skipped = 0
    for f in frames:
        auto = auto_of(f)
        if auto is None:
            skipped += 1
            continue
        n += 1
        for c in CLASSES:
            truth = [rect_of(b) for b in f["hand"] if b["cls"] == c]
            pred = [rect_of(b) for b in auto if b["cls"] == c]
            pairs = match_pairs(metric, truth, pred)
            per[c]["tp"] += len(pairs)
            per[c]["fp"] += len(pred) - len(pairs)
            per[c]["fn"] += len(truth) - len(pairs)
            per[c]["v"] += [v for _, _, v in pairs]

    def summary(d: dict[str, Any]) -> dict[str, Any]:
        tp, fp, fn, v = d["tp"], d["fp"], d["fn"], sorted(d["v"])
        out = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": _ratio(tp, tp + fp),
            "recall": _ratio(tp, tp + fn),
        }
        if metric == "position":
            out["centre_px_median"] = round(v[len(v) // 2], 2) if v else None
            out["centre_px_p90"] = round(v[min(len(v) - 1, int(0.9 * len(v)))], 2) if v else None
        else:
            out["mean_iou"] = round(sum(v) / len(v), 3) if v else None
        return out

    total = {"tp": 0, "fp": 0, "fn": 0, "v": []}
    for d in per.values():
        for key in ("tp", "fp", "fn", "v"):
            total[key] += d[key]
    return {
        "frames": n,
        "skipped": skipped,
        "metric": metric,
        "per_class": {c: summary(d) for c, d in per.items()},
        "overall": summary(total),
    }


def pair_geometry(hand: Rect, auto: Rect) -> dict[str, float | bool]:
    """auto minus hand: centre dx, dy, bottom and top edge dy (px, +y = down); size ratios auto /
    hand; IoU; whether the auto centre lies inside the hand box (the position metric's test)."""
    (hx, hy), (ax, ay) = centre(hand), centre(auto)
    return {
        "dx": ax - hx,
        "dy": ay - hy,
        "d_bottom": auto[3] - hand[3],
        "d_top": auto[1] - hand[1],
        "w_ratio": (auto[2] - auto[0]) / (hand[2] - hand[0]),
        "h_ratio": (auto[3] - auto[1]) / (hand[3] - hand[1]),
        "iou": iou(hand, auto),
        "centre_in": inside((ax, ay), hand),
    }


def provenance(
    hand: dict[str, Any], bundle: Sequence[dict[str, Any]] | None, tol: float = 0.05
) -> str:
    """What Batt did to the auto box he was shown (the /qa bundle): accepted (unchanged), moved
    (same size), resized, added (no auto box behind it: no gid), or unknown (no bundle)."""
    if hand.get("gid") is None:
        return "added"
    if bundle is None:
        return "unknown"
    shown = next((b for b in bundle if b.get("gid") == hand["gid"]), None)
    if shown is None:
        return "added"
    h, b = rect_of(hand), rect_of(shown)
    if max(abs(x - y) for x, y in zip(h, b, strict=True)) < tol:
        return "accepted"
    same_size = (
        abs((h[2] - h[0]) - (b[2] - b[0])) < tol and abs((h[3] - h[1]) - (b[3] - b[1])) < tol
    )
    return "moved" if same_size else "resized"


def link_unit(
    hand: dict[str, Any], f: dict[str, Any], max_px: float = 60.0
) -> tuple[str | None, float | None]:
    """The unit behind a hand box: its gid when it has one, else the nearest unit of the same class
    whose v0 box centre (the projected foot point minus half the class box) is within ``max_px``
    of the hand box's centre. Returns (gid, link distance px; 0 for a gid)."""
    if hand.get("gid") is not None:
        return str(hand["gid"]), 0.0
    hx, hy = centre(rect_of(hand))
    best: tuple[float, str] | None = None
    for gid, e in f.get("entities", {}).items():
        if e.get("cls") != hand["cls"] or "v0_box" not in e:
            continue
        d = math.hypot(*(a - b for a, b in zip(centre(tuple(e["v0_box"])), (hx, hy), strict=True)))
        if d <= max_px and (best is None or d < best[0]):
            best = (d, gid)
    return (None, None) if best is None else (best[1], round(best[0], 1))


# The class boxes of v0 (labels.BOX_PX), repeated so ``report`` needs no poring_dataset import.
V0_BOX_PX = {"player": (34.0, 74.0), "monster": (44.0, 40.0), "npc": (34.0, 74.0)}
MAX_UI_COVER = 0.5  # labels.MAX_UI_COVER


def _clip(r: Rect, size: tuple[int, int]) -> Rect:
    return max(r[0], 0.0), max(r[1], 0.0), min(r[2], float(size[0])), min(r[3], float(size[1]))


def _kept(r: Rect, size: tuple[int, int], cover: float) -> Rect | None:
    """labels_for's rules: at least half the box on screen in each dimension, and less than
    MAX_UI_COVER of it under the UI windows. The clipped box, or None."""
    c = _clip(r, size)
    on_screen = c[2] - c[0] >= (r[2] - r[0]) / 2 and c[3] - c[1] >= (r[3] - r[1]) / 2
    return c if on_screen and cover < MAX_UI_COVER else None


def shifted(r: Sequence[float], d: Sequence[float] | None) -> Rect:
    if d is None:
        return r[0], r[1], r[2], r[3]
    return r[0] + d[0], r[1] + d[1], r[2] + d[0], r[3] + d[1]


def relabel(
    f: dict[str, Any],
    source: str,
    *,
    ui_off: frozenset[str] = frozenset(),
    lag_ms: int | None = None,
    monster_box: Callable[[dict[str, Any]], Rect | None] | None = None,
    size: tuple[int, int] = SIZE,
) -> list[dict[str, Any]] | None:
    """The frame's auto-labels re-derived from the dump's unit facts, by labels_for (v0) /
    labels_for_v1 (v1)'s rules, with the what-if knobs: ``ui_off`` (UI windows not applied),
    ``lag_ms`` (our character drawn where the packets put it that long ago: every unit shifted by
    the dump's self_lag_shift), ``monster_box`` (a v1 monster's unclipped box from its facts; None:
    the client draws nothing). With no knob it must give the frame's own labels back (``report``
    checks this on every frame and says so)."""
    if f.get(source) is None:
        return None
    if not f.get("entities"):
        return [dict(b) for b in f[source]]
    shift = (f.get("self_lag_shift") or {}).get(str(lag_ms)) if lag_ms else None
    out: list[dict[str, Any]] = []
    for gid, e in f["entities"].items():
        cls = e.get("cls")
        if cls not in V0_BOX_PX or e.get("dying") or e.get("hidden") or not e.get("drawn", True):
            continue
        d = None if shift is None else shift.get(gid)
        base = shifted(e["v0_box"], d)
        v0_kept = _kept(base, size, _cover_of(base, ui_off))
        if source == "v1" and cls == "monster" and e.get("sheet") and e.get("state") is not None:
            if monster_box is not None:
                r = monster_box(e)
            else:
                r = tuple(e["v1_pred"]["box"]) if "v1_pred" in e else None
            if r is None:
                continue
            r = shifted(r, d)
            kept = _kept(r, size, _cover_of(r, ui_off))
            if kept is not None:
                out.append(
                    {
                        "cls": cls,
                        "gid": int(gid),
                        "x1": kept[0],
                        "y1": kept[1],
                        "x2": kept[2],
                        "y2": kept[3],
                    }
                )
            continue
        if v0_kept is not None:
            out.append(
                {
                    "cls": cls,
                    "gid": int(gid),
                    "x1": v0_kept[0],
                    "y1": v0_kept[1],
                    "x2": v0_kept[2],
                    "y2": v0_kept[3],
                }
            )
    return out


# ui_layout.UI_RECTS, repeated for the same reason (test_label_quality pins the two equal)
UI_RECTS_PX: tuple[tuple[int, int, int, int], ...] = (
    (0, 0, 222, 325),
    (228, 0, 296, 135),
    (655, 0, 90, 40),
    (0, 528, 600, 98),
    (965, 560, 175, 36),
    (1128, 8, 152, 152),
)


def _cover_of(r: Rect, off: frozenset[str]) -> float:
    """ui_layout.covered_fraction over the UI windows not in ``off``."""
    area = max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])
    if area <= 0:
        return 0.0
    covered = 0.0
    for name, (rx, ry, rw, rh) in zip(UI_NAMES, UI_RECTS_PX, strict=True):
        if name in off:
            continue
        ix = max(0.0, min(r[2], rx + rw) - max(r[0], rx))
        iy = max(0.0, min(r[3], ry + rh) - max(r[1], ry))
        covered += ix * iy
    return min(1.0, covered / area)


def _box_key(x: dict[str, Any]) -> tuple[str, int]:
    return str(x["cls"]), int(x.get("gid") or 0)


def same_boxes(a: Sequence[dict[str, Any]], b: Sequence[dict[str, Any]], tol: float = 1e-6) -> bool:
    """The same boxes (class, gid, edges within ``tol`` px), in any order."""
    key = _box_key
    if len(a) != len(b):
        return False
    return all(
        key(x) == key(y)
        and max(abs(p - q) for p, q in zip(rect_of(x), rect_of(y), strict=True)) <= tol
        for x, y in zip(sorted(a, key=key), sorted(b, key=key), strict=True)
    )


def _unit_auto(
    f: dict[str, Any], auto: Sequence[dict[str, Any]], gid: str | None
) -> dict[str, Any] | None:
    if gid is None:
        return None
    return next((b for b in auto if str(b.get("gid")) == gid), None)


def _why_absent(e: dict[str, Any] | None, source: str, size: tuple[int, int]) -> str:
    """Why a unit the packets know has no auto box: the UI windows (named), off screen, or the
    client draws nothing for it (v1: predict_sprite None), or it is filtered (hidden, dying)."""
    if e is None:
        return "no_unit_in_packets"
    if e.get("dying"):
        return "dying_unit"
    if e.get("hidden") or not e.get("drawn", True):
        return "hidden_unit"
    if (
        source == "v1"
        and e.get("cls") == "monster"
        and e.get("sheet")
        and e.get("state") is not None
    ):
        if "v1_pred" not in e:
            return "draws_nothing"
        r = tuple(e["v1_pred"]["box"])
    else:
        r = tuple(e["v0_box"])
    c = _clip(r, size)
    if not (c[2] - c[0] >= (r[2] - r[0]) / 2 and c[3] - c[1] >= (r[3] - r[1]) / 2):
        return "off_screen"
    names = [n for n in UI_NAMES if _cover_of(r, frozenset(UI_NAMES) - {n}) > 0.05]
    return "ui_window:" + "+".join(names) if names else "other"


def causes(
    frames: Sequence[dict[str, Any]],
    source: str,
    metric: str,
    cls: str = "monster",
    size: tuple[int, int] = SIZE,
) -> dict[str, Any]:
    """Every unmatched hand box (FN) and auto box (FP) of ``cls``, with its cause:
    FN: the unit's auto box is absent (why: _why_absent), or present but not paired -- then
    ``self_moving_shift`` when our own character walks in that frame, else ``unit_position`` (the
    unit's own placement or size: ``walk`` / ``idle`` / ...), or ``paired_elsewhere``.
    FP: the twin of such an FN (its unit has a hand box: same split), or ``no_hand_box`` (Batt
    deleted it, or never saw the unit: the unit's state is given)."""
    fn: Counter[str] = Counter()
    fp: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []
    for f in frames:
        auto = f.get(source)
        if auto is None:
            continue
        truth = [b for b in f["hand"] if b["cls"] == cls]
        pred = [b for b in auto if b["cls"] == cls]
        pairs = match_pairs(metric, [rect_of(b) for b in truth], [rect_of(b) for b in pred])
        mt = {i for i, _, _ in pairs}
        mp = {j for _, j, _ in pairs}
        linked = [link_unit(h, f)[0] for h in truth]
        moving = bool(f.get("self_moving"))
        for i, h in enumerate(truth):
            if i in mt:
                continue
            gid = linked[i]
            a = _unit_auto(f, pred, gid)
            e = f.get("entities", {}).get(gid) if gid is not None else None
            if a is None:
                why = _why_absent(e, source, size)
            elif moving:
                why = "self_moving_shift"
            else:
                why = f"unit_position:{(e or {}).get('state')}"
            if a is not None and pred.index(a) in mp:
                why = "paired_elsewhere"
            fn[why] += 1
            rows.append(
                {
                    "frame_id": f["frame_id"],
                    "side": "fn",
                    "hand_index": i,
                    "gid": gid,
                    "cause": why,
                    "provenance": provenance(h, f.get("bundle")),
                    "hand_centre": [round(v, 1) for v in centre(rect_of(h))],
                    "hand_wh": [round(h["x2"] - h["x1"], 1), round(h["y2"] - h["y1"], 1)],
                    "unit_foot_px": [round(v, 1) for v in e["foot_px"]] if e else None,
                }
            )
        for j, a in enumerate(pred):
            if j in mp:
                continue
            gid = str(a.get("gid"))
            has_hand = gid in linked
            e = f.get("entities", {}).get(gid)
            if has_hand:
                why = "self_moving_shift" if moving else f"unit_position:{(e or {}).get('state')}"
            else:
                why = f"no_hand_box:{(e or {}).get('state')}"
            fp[why] += 1
            rows.append(
                {
                    "frame_id": f["frame_id"],
                    "side": "fp",
                    "gid": gid,
                    "cause": why,
                    "auto_centre": [round(v, 1) for v in centre(rect_of(a))],
                }
            )
    return {
        "source": source,
        "metric": metric,
        "cls": cls,
        "fn": dict(fn.most_common()),
        "fp": dict(fp.most_common()),
        "rows": rows,
    }


def gid_pairs(
    frames: Sequence[dict[str, Any]], source: str, cls: str = "monster"
) -> list[dict[str, Any]]:
    """Every hand box whose unit (gid, or link_unit for an added box) has an auto box: the pair's
    geometry plus what explains it (Batt's edit, the unit's state, our own motion, a dead GM)."""
    out = []
    for f in frames:
        auto = f.get(source)
        if auto is None:
            continue
        for h in f["hand"]:
            if h["cls"] != cls:
                continue
            gid, link = link_unit(h, f)
            a = _unit_auto(f, [b for b in auto if b["cls"] == cls], gid)
            if a is None:
                continue
            e = f.get("entities", {}).get(gid, {})
            row = {
                "frame_id": f["frame_id"],
                "gid": gid,
                "link_px": link,
                "provenance": provenance(h, f.get("bundle")),
                "state": e.get("state"),
                "self_moving": bool(f.get("self_moving")),
                "self_dead": bool(f.get("self_dead")),
                "hand_w": h["x2"] - h["x1"],
                "hand_h": h["y2"] - h["y1"],
                "hand_cy": centre(rect_of(h))[1],
                "hand_cx": centre(rect_of(h))[0],
                **pair_geometry(rect_of(h), rect_of(a)),
            }
            p = e.get("v1_pred")
            if p is not None:
                ax, ay = p["anchor_px"]
                hx, hy = centre(rect_of(h))
                row.update(
                    anchor_to_hand_dx=hx - ax,
                    anchor_to_hand_dy=hy - ay,
                    anchor_to_hand_bottom=h["y2"] - ay,
                    scale=p["scale"],
                    auto_clipped=rect_of(a) != tuple(p["box"]),
                )
            out.append(row)
    return out


def group_geometry(rows: Sequence[dict[str, Any]], keys: Sequence[str]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups["|".join(str(r[k]) for k in keys)].append(r)
    out = {}
    for name, g in sorted(groups.items()):
        out[name] = {
            "n": len(g),
            "centre_in": sum(1 for r in g if r["centre_in"]),
            **{
                m: describe(r[m] for r in g)
                for m in ("dx", "dy", "d_bottom", "w_ratio", "h_ratio", "iou")
            },
        }
    return out


def fit_line(xs: Sequence[float], ys: Sequence[float]) -> dict[str, float | int | None]:
    """Ordinary least squares y = a + b x: slope b, intercept a, R^2, n."""
    n = len(xs)
    if n < 3:
        return {"n": n, "slope": None, "intercept": None, "r2": None}
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0:
        return {"n": n, "slope": None, "intercept": None, "r2": None}
    b = sxy / sxx
    a = my - b * mx
    r2 = (sxy * sxy) / (sxx * syy) if syy else 0.0
    return {"n": n, "slope": round(b, 4), "intercept": round(a, 2), "r2": round(r2, 3)}


def frame_shifts(frames: Sequence[dict[str, Any]], source: str) -> list[dict[str, Any]]:
    """Per frame: the median auto-minus-hand centre offset over every unit with both boxes
    (monsters and NPCs, by gid) -- a whole-frame shift is a camera (our own position) error, not a
    per-unit one."""
    out = []
    for f in frames:
        auto = {str(b.get("gid")): b for b in f.get(source) or []}
        d = [
            (
                centre(rect_of(auto[str(h["gid"])]))[0] - centre(rect_of(h))[0],
                centre(rect_of(auto[str(h["gid"])]))[1] - centre(rect_of(h))[1],
            )
            for h in f["hand"]
            if h.get("gid") is not None and str(h["gid"]) in auto
        ]
        if not d:
            continue
        out.append(
            {
                "frame_id": f["frame_id"],
                "self_moving": bool(f.get("self_moving")),
                "self_dead": bool(f.get("self_dead")),
                "n": len(d),
                "median_dx": round(statistics.median(x for x, _ in d), 1),
                "median_dy": round(statistics.median(y for _, y in d), 1),
            }
        )
    return out


def lag_scan(frames: Sequence[dict[str, Any]], source: str) -> list[dict[str, Any]]:
    """On the frames where our character walks: the median centre distance (auto vs hand, by gid,
    monsters and NPCs) if our own position were taken ``lag`` ms earlier (SELF_LAGS_MS)."""
    out = []
    moving = [f for f in frames if f.get("self_moving")]
    for lag in (0, *[x for x in SELF_LAGS_MS if x]):
        dists = []
        for f in moving:
            relab = {str(b["gid"]): b for b in relabel(f, source, lag_ms=lag or None) or []}
            for h in f["hand"]:
                a = relab.get(str(h.get("gid")))
                if a is not None:
                    (hx, hy), (ax, ay) = centre(rect_of(h)), centre(rect_of(a))
                    dists.append(math.hypot(ax - hx, ay - hy))
        out.append(
            {
                "lag_ms": lag,
                "frames": len(moving),
                "pairs": len(dists),
                "median_px": round(statistics.median(dists), 1) if dists else None,
            }
        )
    return out


# --- what-ifs: each gap closed alone, scored by the same code (IN-SAMPLE on the gold set) --------

UI_LAYOUT_OFF = frozenset({"minimap", "top_window", "notifier"})  # not drawn there in this session


def walk_idle_box(e: dict[str, Any]) -> Rect | None:
    """A walking unit's box from its IDLE envelope at the same anchor and scale (the walk envelope
    adds the bounce of every walk frame)."""
    p = e.get("v1_pred")
    if p is None:
        return None
    if e.get("state") != "walk" or not p.get("idle_extent"):
        return p["box"][0], p["box"][1], p["box"][2], p["box"][3]
    (ax, ay), s = p["anchor_px"], p["scale"]
    x0, y0, x1, y1 = p["idle_extent"]
    return ax + s * x0, ay + s * y0, ax + s * x1, ay + s * y1


def resized_box(
    w: float | None = None,
    h: float | None = None,
    rw: float = 1.0,
    rh: float = 1.0,
    dy: float = 0.0,
    dx: float = 0.0,
) -> Callable[[dict[str, Any]], Rect | None]:
    """A v1 monster box with its centre kept (moved by ``dx``, ``dy``) and its size set to w x h,
    or scaled by rw x rh."""

    def box(e: dict[str, Any]) -> Rect | None:
        p = e.get("v1_pred")
        if p is None:
            return None
        cx, cy = centre(tuple(p["box"]))
        bw = w if w is not None else (p["box"][2] - p["box"][0]) * rw
        bh = h if h is not None else (p["box"][3] - p["box"][1]) * rh
        return cx + dx - bw / 2, cy + dy - bh / 2, cx + dx + bw / 2, cy + dy + bh / 2

    return box


@dataclass(frozen=True)
class WhatIf:
    name: str
    gap: str
    fitted_on_gold: bool  # a constant was chosen by looking at the gold set: an upper bound
    auto_of: AutoOf
    keep: Callable[[dict[str, Any]], bool] = lambda f: True


def what_ifs(
    frames: Sequence[dict[str, Any]],
    source: str,
    lag: int,
    batt_ratio: tuple[float, float],
    lofo: dict[str, dict[int, float]],
) -> list[WhatIf]:
    """The single-gap what-ifs for ``source`` (v1 gets the monster-box ones too)."""
    out = [
        WhatIf("as_is", "-", False, lambda f: f[source]),
        WhatIf(
            "exclude_dead_gm_frames",
            "dead GM frames",
            False,
            lambda f: f[source],
            keep=lambda f: not f.get("self_dead"),
        ),
        WhatIf(
            "ui_no_minimap",
            "UI windows",
            False,
            lambda f: relabel(f, source, ui_off=frozenset({"minimap"})),
        ),
        WhatIf(
            "ui_session_layout",
            "UI windows",
            False,
            lambda f: relabel(f, source, ui_off=UI_LAYOUT_OFF),
        ),
        WhatIf(
            "ui_session_layout_chat_translucent",
            "UI windows",
            False,
            lambda f: relabel(f, source, ui_off=UI_LAYOUT_OFF | {"chat"}),
        ),
        WhatIf(f"self_lag_{lag}ms", "our own walk", True, lambda f: relabel(f, source, lag_ms=lag)),
    ]
    if source == "v1":
        out += [
            WhatIf(
                "walk_idle_envelope",
                "walk envelope",
                False,
                lambda f: relabel(f, source, monster_box=walk_idle_box),
            ),
            WhatIf(
                "box_44x40",
                "box size",
                False,
                lambda f: relabel(f, source, monster_box=resized_box(44.0, 40.0)),
            ),
            WhatIf(
                "box_batt_drawn_ratio",
                "box size",
                True,
                lambda f: relabel(
                    f, source, monster_box=resized_box(rw=batt_ratio[0], rh=batt_ratio[1])
                ),
            ),
            WhatIf(
                "centre_dy_lofo",
                "anchor offset",
                True,
                lambda f: relabel(
                    f, source, monster_box=resized_box(dy=lofo["dy"].get(f["frame_id"], 0.0))
                ),
            ),
            WhatIf(
                "centre_dx_lofo",
                "anchor offset",
                True,
                lambda f: relabel(
                    f, source, monster_box=resized_box(dx=lofo["dx"].get(f["frame_id"], 0.0))
                ),
            ),
            WhatIf(
                "combined_no_minimap_self_lag",
                "combined",
                True,
                lambda f: relabel(f, source, ui_off=frozenset({"minimap"}), lag_ms=lag),
            ),
            WhatIf(
                "combined_no_minimap_chat_self_lag",
                "combined",
                True,
                lambda f: relabel(f, source, ui_off=frozenset({"minimap", "chat"}), lag_ms=lag),
            ),
            WhatIf(
                "combined_no_minimap_self_lag_44x40",
                "combined",
                True,
                lambda f: relabel(
                    f,
                    source,
                    ui_off=frozenset({"minimap"}),
                    lag_ms=lag,
                    monster_box=resized_box(44.0, 40.0),
                ),
            ),
        ]
    return out


def _monster(r: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = r["per_class"]["monster"]
    return out


def labels_of(source: str) -> AutoOf:
    """A frame's own labels of ``source`` (v0 / v1), as they are."""
    return lambda f: f[source]


def position_outcome(
    frames: Sequence[dict[str, Any]], auto_of: AutoOf
) -> dict[tuple[int, str], tuple[str, list[float]]]:
    """(frame, gid) -> ("tp" or "fp", the box centre) for every monster auto box, by the position
    metric: what a what-if changes, box by box."""
    out: dict[tuple[int, str], tuple[str, list[float]]] = {}
    for f in frames:
        auto = auto_of(f)
        if auto is None:
            continue
        pred = [b for b in auto if b["cls"] == "monster"]
        truth = [rect_of(b) for b in f["hand"] if b["cls"] == "monster"]
        hit = {j for _, j, _ in greedy_position(truth, [rect_of(b) for b in pred])}
        for j, b in enumerate(pred):
            c = [round(v, 1) for v in centre(rect_of(b))]
            out[(f["frame_id"], str(b.get("gid")))] = ("tp" if j in hit else "fp", c)
    return out


def run_what_ifs(frames: Sequence[dict[str, Any]], ifs: Sequence[WhatIf]) -> list[dict[str, Any]]:
    """Each what-if scored on both metrics (monsters; NPCs beside), with its change against as_is
    (``ifs[0]``), box by box for the position metric. The cost of a gap = the errors (FN + FP) its
    what-if removes: ranked by the position metric's errors removed, then the IoU metric's."""
    rows = []
    base: dict[str, dict[str, Any]] = {}
    for w in ifs:
        fs = [f for f in frames if w.keep(f)]
        sc = {m: score(fs, w.auto_of, m) for m in ("position", "iou")}
        if w.name == "as_is":
            base = sc
        row: dict[str, Any] = {
            "name": w.name,
            "gap": w.gap,
            "fitted_on_gold": w.fitted_on_gold,
            "frames": len(fs),
            "position": _monster(sc["position"]),
            "iou": _monster(sc["iou"]),
            "npc_position": sc["position"]["per_class"]["npc"],
        }
        bp, bi = _monster(base["position"]), _monster(base["iou"])
        bn = base["position"]["per_class"]["npc"]
        p, q = row["position"], row["iou"]

        def dr(a: float | None, b: float | None) -> float | None:
            return None if a is None or b is None else round(a - b, 3)

        row["delta"] = {
            "position_tp": p["tp"] - bp["tp"],
            "position_fp": p["fp"] - bp["fp"],
            "position_fn": p["fn"] - bp["fn"],
            "position_precision": dr(p["precision"], bp["precision"]),
            "position_recall": dr(p["recall"], bp["recall"]),
            "position_errors_removed": (bp["fp"] + bp["fn"]) - (p["fp"] + p["fn"]),
            "iou_tp": q["tp"] - bi["tp"],
            "iou_fp": q["fp"] - bi["fp"],
            "iou_fn": q["fn"] - bi["fn"],
            "iou_errors_removed": (bi["fp"] + bi["fn"]) - (q["fp"] + q["fn"]),
            "mean_iou": dr(q["mean_iou"], bi["mean_iou"]),
            "npc_position_errors_removed": (bn["fp"] + bn["fn"])
            - (row["npc_position"]["fp"] + row["npc_position"]["fn"]),
        }
        before = position_outcome(fs, ifs[0].auto_of)
        after = position_outcome(fs, w.auto_of)
        row["position_changes"] = {
            kind: [
                [fid, gid, *c]
                for (fid, gid), (o, c) in sorted(after.items())
                if o == kind and (before.get((fid, gid)) or ("",))[0] != kind
            ]
            for kind in ("tp", "fp")
        }
        row["position_changes"]["lost_tp"] = [
            [fid, gid, *c]
            for (fid, gid), (o, c) in sorted(before.items())
            if o == "tp" and (after.get((fid, gid)) or ("",))[0] != "tp"
        ]
        rows.append(row)
    ranked = sorted(
        (r for r in rows if r["name"] != "as_is" and r["gap"] != "combined"),
        key=lambda r: (-r["delta"]["position_errors_removed"], -r["delta"]["iou_errors_removed"]),
    )
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    return rows


def lofo_offset(
    pairs: Sequence[dict[str, Any]], axis: str = "dy", states: Sequence[str] = ("idle",)
) -> tuple[dict[int, float], float | None]:
    """A centre offset (hand minus v1, px, ``axis`` dx or dy) from Batt's MOVED boxes of units in
    ``states`` while our character stands: for every frame, the median over the OTHER frames
    (leave-one-frame-out, so no frame is corrected with its own boxes); plus the all-frame median
    (reported only). The moved boxes are the ones Batt found off: selected on their error."""
    use = [
        p
        for p in pairs
        if p["provenance"] == "moved" and p["state"] in states and not p["self_moving"]
    ]
    frames = sorted({p["frame_id"] for p in pairs})
    out = {}
    for fid in frames:
        rest = [-p[axis] for p in use if p["frame_id"] != fid]
        if rest:
            out[fid] = statistics.median(rest)
    return out, (statistics.median(-p[axis] for p in use) if use else None)


def model_misses(
    frames: Sequence[dict[str, Any]], preds: dict[str, list[dict[str, Any]]], source: str = "v1"
) -> dict[str, Any]:
    """A detector's gold-set misses (position metric, monsters; its detections as
    poring_vision.predict_dir writes them) set beside the LABELS' own misses: each hand box the
    model misses is ``label_hit`` (the training label pointed at it) or the cause the label missed
    it by (``causes``); each false detection is counted by whether our character walked in that
    frame and whether its centre lies under a UI window. No model is run here."""
    label_fn = {
        (r["frame_id"], r["hand_index"]): r["cause"]
        for r in causes(frames, source, "position")["rows"]
        if r["side"] == "fn"
    }
    fn: Counter[str] = Counter()
    fn_alive: Counter[str] = Counter()
    fn_rows: list[list[Any]] = []
    fp: Counter[str] = Counter()
    near_miss: list[dict[str, Any]] = []
    no_det: list[str] = []
    by_gm: dict[str, Counter[str]] = {"gm_alive": Counter(), "gm_dead": Counter()}
    dead_fp_offset: list[tuple[float, float]] = []
    tp = 0
    for f in frames:
        truth = [b for b in f["hand"] if b["cls"] == "monster"]
        det = [b for b in preds.get(str(f["frame_id"]), []) if b["cls"] == "monster"]
        pairs = greedy_position([rect_of(b) for b in truth], [rect_of(b) for b in det])
        tp += len(pairs)
        mt, mp = {i for i, _, _ in pairs}, {j for _, j, _ in pairs}
        gm = by_gm["gm_dead" if f.get("self_dead") else "gm_alive"]
        gm["frames"] += 1
        gm["tp"] += len(pairs)
        gm["fn"] += len(truth) - len(pairs)
        gm["fp"] += len(det) - len(pairs)
        if f.get("self_dead"):
            # a false detection under a dead GM: its offset from the nearest hand box
            for j, d in enumerate(det):
                if j in mp or not truth:
                    continue
                c = centre(rect_of(d))
                hc = min((centre(rect_of(h)) for h in truth),
                         key=lambda q: math.hypot(q[0] - c[0], q[1] - c[1]))  # fmt: skip
                dead_fp_offset.append((c[0] - hc[0], c[1] - hc[1]))
        free = [d for j, d in enumerate(det) if j not in mp]
        for i, h in enumerate(truth):
            if i in mt:
                continue
            why = label_fn.get((f["frame_id"], i), "label_hit")
            fn[why] += 1
            fn_rows.append([f["frame_id"], i, why])
            if not f.get("self_dead"):
                fn_alive[why] += 1
            if why != "label_hit":
                continue
            # the model missed a unit its label pointed at: its nearest unpaired detection
            hc = centre(rect_of(h))
            near = sorted(
                (math.hypot(c[0] - hc[0], c[1] - hc[1]), c)
                for c in (centre(rect_of(d)) for d in free)
            )
            gid, _ = link_unit(h, f)
            state = (f.get("entities", {}).get(gid) or {}).get("state") if gid else None
            if near and near[0][0] <= NEAR_MISS_PX:
                c = near[0][1]
                near_miss.append({"dx": c[0] - hc[0], "dy": c[1] - hc[1], "state": state})
            else:
                no_det.append(str(state))
        for j, d in enumerate(det):
            if j in mp:
                continue
            c = centre(rect_of(d))
            under = any(
                inside(c, (rx, ry, rx + rw, ry + rh))
                for name, (rx, ry, rw, rh) in zip(UI_NAMES, UI_RECTS_PX, strict=True)
                if name != "minimap"
            )
            fp[
                ("self_moving_frame" if f.get("self_moving") else "self_still_frame")
                + (":under_ui_window" if under else "")
            ] += 1
    n_fp, n_fn = sum(fp.values()), sum(fn.values())
    return {
        "tp": tp,
        "fp": n_fp,
        "fn": n_fn,
        "precision": _ratio(tp, tp + n_fp),
        "recall": _ratio(tp, tp + n_fn),
        "fn_by_label_cause": dict(fn.most_common()),
        "fn_by_label_cause_gm_alive": dict(fn_alive.most_common()),
        "fn_rows": [r for r in fn_rows if r[2] != "label_hit"],
        "label_hit_near_miss": {
            "n": len(near_miss),
            "dx": describe(m["dx"] for m in near_miss),
            "dy": describe(m["dy"] for m in near_miss),
            "states": dict(Counter(str(m["state"]) for m in near_miss)),
        },
        "label_hit_no_detection": dict(Counter(no_det)),
        "fp_by_frame": dict(fp.most_common()),
        "by_gm": {
            k: {
                **dict(v),
                "precision": _ratio(v["tp"], v["tp"] + v["fp"]),
                "recall": _ratio(v["tp"], v["tp"] + v["fn"]),
            }
            for k, v in by_gm.items()
        },
        "gm_dead_fp_offset_to_nearest_hand": {
            "dx": describe(x for x, _ in dead_fp_offset),
            "dy": describe(y for _, y in dead_fp_offset),
        },
    }


def _envelope(frames: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """How much the phase-unknown ENVELOPE (the union of an action's frames) inflates a v1 box over
    the action's single frames: envelope / median single-frame size, per state (sprite px)."""
    by: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"w": [], "h": []})
    for f in frames:
        for e in f.get("entities", {}).values():
            p = e.get("v1_pred")
            if p is None or p.get("phase_known") or not p.get("extent"):
                continue
            ms = [m for m in p.get("motion_extents") or [] if m]
            if not ms:
                continue
            x0, y0, x1, y1 = p["extent"]
            mw = statistics.median(m[2] - m[0] for m in ms)
            mh = statistics.median(m[3] - m[1] for m in ms)
            by[str(e.get("state"))]["w"].append((x1 - x0) / mw)
            by[str(e.get("state"))]["h"].append((y1 - y0) / mh)
    return {k: {"w": describe(v["w"], 3), "h": describe(v["h"], 3)} for k, v in sorted(by.items())}


def report(d: dict[str, Any]) -> dict[str, Any]:
    frames = d["frames"]
    prov: Counter[str] = Counter()
    deleted: Counter[str] = Counter()
    species: Counter[str] = Counter()
    for f in frames:
        for h in f["hand"]:
            prov[f"{h['cls']}:{provenance(h, f.get('bundle'))}"] += 1
            gid, _ = link_unit(h, f)
            if h["cls"] == "monster":
                species[str((f.get("entities", {}).get(gid) or {}).get("job"))] += 1
        hand_gids = {h.get("gid") for h in f["hand"]}
        for b in f.get("bundle") or []:
            if b.get("gid") not in hand_gids:
                deleted[f"{b['cls']}:deleted"] += 1
    out: dict[str, Any] = {
        "inputs": {
            "session": d["session"],
            "handcheck_sha256": d["handcheck_sha256"],
            "offset_ms": d["offset_ms"],
            "k": d["k"],
            "camera": d["camera"],
            "frames": len(frames),
            "hand_boxes": Counter(h["cls"] for f in frames for h in f["hand"]),
            "self_dead_frames": [f["frame_id"] for f in frames if f.get("self_dead")],
            "self_moving_frames": [f["frame_id"] for f in frames if f.get("self_moving")],
            "monster_species_of_hand_boxes": dict(species),
            "sheets_missing": d.get("sheets_missing"),
        },
        "relabel_check": {
            s: sum(
                1 for f in frames if f.get(s) is not None and same_boxes(relabel(f, s) or [], f[s])
            )
            for s in ("v0", "v1")
        },
        "hand_provenance": dict(sorted((prov + deleted).items())),
    }
    out["matching"] = {
        s: {m: score(frames, labels_of(s), m) for m in ("iou", "position")} for s in ("v0", "v1")
    }
    pairs = {s: gid_pairs(frames, s) for s in ("v0", "v1")}
    out["geometry"] = {
        s: {
            "all": group_geometry(pairs[s], ("self_moving",)),
            "by_self_dead_self_still": group_geometry(
                [p for p in pairs[s] if not p["self_moving"]], ("self_dead",)
            ),
            "by_provenance_state_self_still": group_geometry(
                [p for p in pairs[s] if not p["self_moving"]], ("provenance", "state")
            ),
        }
        for s in ("v0", "v1")
    }
    still_idle = [p for p in pairs["v1"] if not p["self_moving"] and p["state"] == "idle"]
    out["anchor"] = {
        "hand_centre_minus_anchor_dy_by_provenance": {
            k: describe(
                p["anchor_to_hand_dy"]
                for p in still_idle
                if p["provenance"] == k and "anchor_to_hand_dy" in p
            )
            for k in ("accepted", "moved", "resized", "added")
        },
        "hand_bottom_minus_anchor_by_provenance": {
            k: describe(
                p["anchor_to_hand_bottom"]
                for p in still_idle
                if p["provenance"] == k and "anchor_to_hand_bottom" in p
            )
            for k in ("accepted", "moved", "resized", "added")
        },
        "v0_box_centre_minus_anchor_dy": -V0_BOX_PX["monster"][1] / 2,
        "v1_centre_minus_anchor_dy_by_state": {
            st: describe(
                centre(tuple(e["v1_pred"]["box"]))[1] - e["v1_pred"]["anchor_px"][1]
                for f in frames
                for e in f.get("entities", {}).values()
                if e.get("state") == st and "v1_pred" in e
            )
            for st in ("idle", "walk", "attacking")
        },
        "v1_bottom_minus_anchor_by_state": {
            st: describe(
                e["v1_pred"]["box"][3] - e["v1_pred"]["anchor_px"][1]
                for f in frames
                for e in f.get("entities", {}).values()
                if e.get("state") == st and "v1_pred" in e
            )
            for st in ("idle", "walk", "attacking")
        },
    }
    moved_idle = [p for p in still_idle if p["provenance"] == "moved"]
    accepted_idle = [p for p in still_idle if p["provenance"] == "accepted"]
    out["position_dependence"] = {
        "moved_idle_dy_vs_hand_y": fit_line(
            [p["hand_cy"] for p in moved_idle], [p["dy"] for p in moved_idle]
        ),
        "moved_idle_dx_vs_hand_x": fit_line(
            [p["hand_cx"] for p in moved_idle], [p["dx"] for p in moved_idle]
        ),
        "moved_idle_dy_vs_scale": fit_line(
            [p["scale"] for p in moved_idle if "scale" in p],
            [p["dy"] for p in moved_idle if "scale" in p],
        ),
        "accepted_idle_dy_vs_hand_y": fit_line(
            [p["hand_cy"] for p in accepted_idle], [p["dy"] for p in accepted_idle]
        ),
        "accepted_idle_dy_vs_scale": fit_line(
            [p["scale"] for p in accepted_idle if "scale" in p],
            [p["dy"] for p in accepted_idle if "scale" in p],
        ),
    }
    drawn = [p for p in pairs["v1"] if p["provenance"] in ("added", "resized")]
    own = [
        h
        for f in frames
        for h in f["hand"]
        if h["cls"] == "monster" and provenance(h, f.get("bundle")) in ("added", "resized")
    ]
    v1_boxes = [b for f in frames for b in f.get("v1") or [] if b["cls"] == "monster"]
    out["size"] = {
        "batt_drawn_all_n": len(own),
        "batt_drawn_all_w": describe(h["x2"] - h["x1"] for h in own),
        "batt_drawn_all_h": describe(h["y2"] - h["y1"] for h in own),
        "batt_drawn_hand_w": describe(p["hand_w"] for p in drawn),
        "batt_drawn_hand_h": describe(p["hand_h"] for p in drawn),
        "batt_drawn_v1_over_hand_w": describe((p["w_ratio"] for p in drawn), 3),
        "batt_drawn_v1_over_hand_h": describe((p["h_ratio"] for p in drawn), 3),
        "hand_44x40_share": _ratio(
            sum(
                1
                for f in frames
                for h in f["hand"]
                if h["cls"] == "monster"
                and abs(h["x2"] - h["x1"] - 44) < 0.05
                and abs(h["y2"] - h["y1"] - 40) < 0.05
            ),
            sum(1 for f in frames for h in f["hand"] if h["cls"] == "monster"),
        ),
        "v1_box_w": describe(b["x2"] - b["x1"] for b in v1_boxes),
        "v1_box_h": describe(b["y2"] - b["y1"] for b in v1_boxes),
        "v1_box_w_over_44": describe(((b["x2"] - b["x1"]) / 44 for b in v1_boxes), 3),
        "v1_box_h_over_40": describe(((b["y2"] - b["y1"]) / 40 for b in v1_boxes), 3),
        "envelope_over_single_frame": _envelope(frames),
    }
    out["frame_shift"] = {
        s: [
            r
            for r in frame_shifts(frames, s)
            if abs(r["median_dx"]) > 15 or abs(r["median_dy"]) > 15 or r["self_moving"]
        ]
        for s in ("v0", "v1")
    }
    scan = lag_scan(frames, "v1")
    best = min(
        (r for r in scan if r["median_px"] is not None),
        key=lambda r: r["median_px"],
        default={"lag_ms": 0},
    )
    out["self_lag_scan_v1"] = {"scan": scan, "best_lag_ms": best["lag_ms"]}
    out["causes"] = {
        s: {
            m: {k: v for k, v in causes(frames, s, m).items() if k != "rows"}
            for m in ("position", "iou")
        }
        for s in ("v0", "v1")
    }
    out["causes_npc_position"] = {
        s: {k: v for k, v in causes(frames, s, "position", "npc").items() if k != "rows"}
        for s in ("v0", "v1")
    }
    out["causes_rows_v1_position"] = causes(frames, "v1", "position")["rows"]
    r_w = statistics.median(p["w_ratio"] for p in drawn) if drawn else 1.0
    r_h = statistics.median(p["h_ratio"] for p in drawn) if drawn else 1.0
    lofo_y, dy_all = lofo_offset(pairs["v1"], "dy", ("idle",))
    lofo_x, dx_all = lofo_offset(pairs["v1"], "dx", ("idle", "walk"))
    lofo = {"dx": lofo_x, "dy": lofo_y}
    out["what_if_constants"] = {
        "self_lag_ms": best["lag_ms"],
        "batt_drawn_scale": [round(1 / r_w, 3), round(1 / r_h, 3)],
        "centre_dy_all_frames": None if dy_all is None else round(dy_all, 2),
        "centre_dy_lofo": describe(lofo_y.values()),
        "centre_dx_all_frames": None if dx_all is None else round(dx_all, 2),
        "centre_dx_lofo": describe(lofo_x.values()),
    }
    out["what_ifs"] = {
        s: run_what_ifs(frames, what_ifs(frames, s, int(best["lag_ms"]), (1 / r_w, 1 / r_h), lofo))
        for s in ("v1", "v0")
    }
    return out


# --- CLI ----------------------------------------------------------------------------------------


def _json(x: Any) -> str:
    return json.dumps(x, indent=1, default=lambda o: dict(o) if isinstance(o, Counter) else str(o))


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    du = sub.add_parser("dump")
    du.add_argument("session")
    du.add_argument("--out", type=Path, default=None, help=f"default {SCRATCH}/dump-<session>.json")
    du.add_argument("--datasets", type=Path, default=NAS)
    du.add_argument(
        "--data",
        type=Path,
        default=ROOT / "data",
        help="the checkout's data/ (hand-check, KB); a worktree has none",
    )
    du.add_argument(
        "--bundles",
        type=Path,
        default=ROOT / "services" / "frontend" / ".qa-local",
        help="the /qa bundles (what Batt edited)",
    )
    du.add_argument(
        "--mapcache",
        type=Path,
        default=None,
        help="the generated map caches, when this checkout has none",
    )
    du.add_argument("--k", type=float, default=0.140, help="v1's k (the v1 cache: 0.140)")
    ca = sub.add_parser("cache")
    ca.add_argument("dump", type=Path)
    ca.add_argument("shard", type=Path, help="the v1 cache shard holding the session's frames")
    rp = sub.add_parser("report")
    rp.add_argument("dump", type=Path)
    pk = sub.add_parser("peek")
    pk.add_argument("session")
    pk.add_argument("seconds", type=float, help="seconds after the recording's t0")
    pk.add_argument("out", type=Path, help="a PNG path under /dev/shm")
    pk.add_argument("--datasets", type=Path, default=NAS)
    pk.add_argument("--data", type=Path, default=ROOT / "data")
    pk.add_argument("--mapcache", type=Path, default=None)
    pk.add_argument("--k", type=float, default=0.140)
    mo = sub.add_parser("models")
    mo.add_argument("dump", type=Path)
    mo.add_argument("preds", type=Path, nargs="+", help="predict_dir outputs on the gold frames")
    ce = sub.add_parser("census")
    ce.add_argument("cache_manifest", type=Path, help="a frame cache's manifest.json (its split)")
    ce.add_argument("--datasets", type=Path, default=NAS)
    ce.add_argument("--data", type=Path, default=ROOT / "data")
    ce.add_argument("--mapcache", type=Path, default=None)
    ce.add_argument("--step-s", type=float, default=1.0)
    a = ap.parse_args(argv)
    if a.cmd == "peek":
        print(json.dumps(peek(a.session, a.seconds, a.out, a.datasets, a.data, a.k, a.mapcache)))
        return 0
    if a.cmd == "census":
        m = json.loads(a.cache_manifest.read_text())
        sessions = [(sid, part) for part, sids in m["split"].items() for sid in sids]
        print(
            _json(
                census(
                    sessions, a.datasets, a.data, float(m.get("k") or 0.140), a.step_s, a.mapcache
                )
            )
        )
        return 0
    if a.cmd == "dump":
        if a.out is None:
            SCRATCH.mkdir(parents=True, exist_ok=True)
        out = a.out or SCRATCH / f"dump-{a.session}.json"
        doc = dump(a.session, a.datasets, a.data, a.bundles, a.k, a.mapcache)
        out.write_text(_json(doc))
        print(
            json.dumps(
                {
                    "dump": str(out),
                    "frames": len(doc["frames"]),
                    "offset_ms": doc["offset_ms"],
                    "k": doc["k"],
                }
            )
        )
        return 0
    d = json.loads(a.dump.read_text())
    if a.cmd == "models":
        out = {}
        for path in a.preds:
            p = json.loads(path.read_text())
            out[path.name] = {"weights": p.get("weights"), "conf": p.get("conf"),
                              **model_misses(d["frames"], p["frames"])}  # fmt: skip
        print(_json(out))
        return 0
    print(_json(cache_check(d, a.shard) if a.cmd == "cache" else report(d)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
