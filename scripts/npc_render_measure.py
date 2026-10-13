#!/usr/bin/env python3
"""The NPC render path's DESIGN measurements (docs/planning/npc-render.md section 3; Batt
2026-10-13). OFFLINE: banked sessions (NAS copies, named by exact path; never a walk of /mnt),
packets as ground truth, nothing live, no GPU.

    npc_render_measure.py align SESSION [SESSION ...] --names JSON [--sprites DIR] [--kb DIR]
                                [--k K ...] [--radius 24] [--per-session 15] [--every-png 10]
                                [--out JSON]
        (a) positions / masks vs the observed pixels: on banked frames where the packets put our
        GM standing still on a known cell, every on-screen drawn L3 NPC is rendered from that
        cell (npc_render.render) and its rendered sprite is template-matched against the frame
        within +-radius px: the best offset (dx, dy), its masked NCC and the NCC at (0, 0). The
        L3 data (cell, sprite, facing) is also checked against the packets' NPC objects.
    npc_render_measure.py click PROBE_SESSION [...] --items JSON --labels JSON --names JSON
                                [--sprites DIR] [--kb DIR] [--k K] [--out JSON]
        (b) the rendered mask vs the CLICKABLE area: every npc-click probe (hover only) of the
        sessions, rendered from our GM's packet cell; its point inside a rendered NPC mask / box
        or not, crossed with the agreed label of its grab 0 (talk / walk / noentry ...).

    npc_render_measure.py camera SESSION [...] [--input-log DIR] [--out JSON]
        The OFFLINE camera guard on the design sessions: the rotation / zoom inputs the backend's
        input log holds in each session's window (byte ranges only) and the state it leaves.

Every number printed is ids, cells, pixels and counts: no names, no pixels leave the machine.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import npc_render as nr  # noqa: E402

from poring_dataset.camera import is_indoor, load_indoor_table, map_key  # noqa: E402
from poring_dataset.labels import BOX_PX  # noqa: E402
from poring_dataset.render import K_NOSTALRO  # noqa: E402
from poring_dataset.ui_layout import covered_fraction  # noqa: E402

PROBE_RULE = "npc-click@1/probe"
STAND_MS = 500  # our GM counts as standing when its packet cell is the same this long before
CONFIDENT = 0.5  # a match counts at or above this NCC (0.4 / 0.6 reported beside it)
CENTRE = (640.0, 360.0)
Box = tuple[float, float, float, float]


# --- shared helpers -------------------------------------------------------------------------------


def session_args(kb: Path) -> argparse.Namespace:
    """labels_v2.Session's options: packets, the backend's offset and camera only."""
    return argparse.Namespace(
        kb=kb,
        offset_ms=None,
        npc_extents=None,
        npc_sprites=None,
        npc_sprite_names=None,
        cutin_rect=None,
        warp_visibility=None,
        k=None,
    )


def camera_path(backend: str) -> str:
    return "s2" if backend == "console" else "rdp"


def standing_cell(sess: Any, t: int) -> tuple[str, tuple[int, int]] | None:
    """(map, cell) when the packets put our GM on the same whole cell at t and STAND_MS before."""
    w = sess.world(t)
    if not w.map or w.self_pos is None:
        return None
    before = sess.world(t - STAND_MS * 1_000_000)
    x, y = w.self_pos
    if before.self_pos != w.self_pos or before.map != w.map or x != int(x) or y != int(y):
        return None
    return map_key(w.map), (int(x), int(y))


def overlaps(a: Box, b: Box) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def grow(b: Box, r: float) -> Box:
    return (b[0] - r, b[1] - r, b[2] + r, b[3] + r)


def unit_boxes(world: Any, res: nr.RenderResult, scene: Any) -> list[Box]:
    """Rough boxes of every non-NPC unit the packets show (our GM included): v0's sizes at the
    projected feet. A rendered NPC overlapping one is not matched (an occluder, not a miss)."""
    from poring_dataset.render import anchor_and_depth

    out = []
    pts: list[tuple[tuple[float, float], str]] = []
    if world.self_pos is not None:
        pts.append((world.self_pos, "player"))
    for e in world.entities:
        if getattr(e, "hidden", False) or e.objtype == 6:
            continue
        pts.append(((float(e.x), float(e.y)), "monster" if e.objtype == 5 else "player"))
    for cell, cls in pts:
        (u, v), z = anchor_and_depth(scene, cell)
        if z <= 0:
            continue
        w, h = BOX_PX[cls]
        out.append((u - w / 2, v - h, u + w / 2, v + 4))
    return out


def unsupported_box(anchor: tuple[float, float]) -> Box:
    """A generous box around an unsupported NPC's anchor (its sprite is unknown): wider and taller
    than any NPC sprite rendered so far, so nothing it draws is taken for a matched sprite."""
    u, v = anchor
    return (u - 70.0, v - 170.0, u + 70.0, v + 20.0)


def q(values: Sequence[float], p: float) -> float | None:
    return round(float(np.percentile(values, p)), 2) if values else None


def dist_stats(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    dx = [r["dx"] for r in rows]
    dy = [r["dy"] for r in rows]
    d = [math.hypot(r["dx"], r["dy"]) for r in rows]
    return {
        "n": len(rows),
        "dx_median": q(dx, 50),
        "dx_p10_p90": [q(dx, 10), q(dx, 90)],
        "dy_median": q(dy, 50),
        "dy_p10_p90": [q(dy, 10), q(dy, 90)],
        "d_median": q(d, 50),
        "d_p90": q(d, 90),
        "within_3px": round(sum(1 for v in d if v <= 3) / len(d), 3) if d else None,
        "within_6px": round(sum(1 for v in d if v <= 6) / len(d), 3) if d else None,
        "within_12px": round(sum(1 for v in d if v <= 12) / len(d), 3) if d else None,
    }


def linear_fit(rows: Sequence[dict[str, Any]], key: str) -> dict[str, Any] | None:
    """key ~ a + b * (u - 640) + c * (v - 360), least squares: does the offset grow away from the
    screen centre (a camera mis-fit) or stay constant (a shift)?"""
    if len(rows) < 8:
        return None
    x = np.array([[1.0, r["u"] - CENTRE[0], r["v"] - CENTRE[1]] for r in rows])
    y = np.array([float(r[key]) for r in rows])
    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ coef
    return {
        "a_px": round(float(coef[0]), 2),
        "b_per_100px_u": round(float(coef[1]) * 100, 2),
        "c_per_100px_v": round(float(coef[2]) * 100, 2),
        "residual_sd": round(float(resid.std()), 2),
        "n": len(rows),
    }


# --- (a) align ------------------------------------------------------------------------------------


def frames_of(path: Path, every_png: int) -> list[tuple[int, str]]:
    import labels_v2 as tool

    out = [(t, str(i)) for t, i in tool.banked_frames(path) if i is not None]
    return out or tool.shard_frames(path, every_png)


def packet_npcs(world: Any) -> dict[tuple[int, int], tuple[int, int | None]]:
    return {(int(e.x), int(e.y)): (int(e.job), e.heading) for e in world.entities if e.objtype == 6}


def cmd_align(a: argparse.Namespace) -> int:
    import labels_v2 as tool

    sheets = nr.sheets_from_files(a.sprites, a.names)
    table = load_indoor_table()
    rows: list[dict[str, Any]] = []
    l3check: Counter[str] = Counter()
    skipped: Counter[str] = Counter()
    per_session: dict[str, dict[str, int]] = {}
    camera_check: Counter[str] = Counter()  # the pixel guard's verdict per frame (default camera)
    for p in a.sessions:
        if not (p / "packets.jsonl.gz").exists():
            skipped["no_packets"] += 1
            continue
        frames = frames_of(p, a.every_png)
        if not frames:
            skipped["no_frames"] += 1
            continue
        try:
            sess = tool.Session(p, session_args(a.kb))
        except Exception as exc:  # noqa: BLE001  (a session the labeller cannot read: reported)
            skipped[f"session_error:{type(exc).__name__}"] += 1
            continue
        path_ = camera_path(sess.backend)
        renders: dict[tuple[str, tuple[int, int], float], nr.RenderResult | str] = {}
        cands: list[tuple[int, str, str, tuple[int, int], list[nr.RenderedNpc], Any]] = []
        for t, ref in frames:
            if sess.labeler.boxes(t) is None:
                skipped["gm_window"] += 1
                continue
            got = standing_cell(sess, t)
            if got is None:
                skipped["not_standing"] += 1
                continue
            map_name, cell = got
            key = (map_name, cell, a.k[0])
            if key not in renders:
                try:
                    renders[key] = nr.render(
                        map_name, cell, path_, k=a.k[0], kb_dir=a.kb, sheets=sheets
                    )
                except nr.Unsupported as exc:
                    renders[key] = exc.reason
            res = renders[key]
            if isinstance(res, str):
                skipped[f"refused:{res}"] += 1
                continue
            world = sess.world(t)
            scene = nr.cached_scene(sess.labeler.camera, map_name, cell, nr.GAT_DIR, table)
            units = unit_boxes(world, res, scene)
            pk = packet_npcs(world)
            clean = []
            for r in res.rendered:
                # L3 against the packets (the server's own NPC objects at that moment)
                got_p = pk.get(r.npc.cell)
                if got_p is None:
                    l3check["no_packet_npc_at_cell"] += 1
                elif got_p[0] != r.npc.sprite:
                    l3check["packet_job_differs"] += 1
                else:
                    l3check["cell_and_sprite_agree"] += 1
                    l3check["facing_agrees" if got_p[1] == r.npc.dir else "facing_differs"] += 1
                b = r.box
                if b[0] < 0 or b[1] < 0 or b[2] > nr.SCREEN[0] or b[3] > nr.SCREEN[1]:
                    skipped["npc_partly_off_screen"] += 1
                    continue
                if covered_fraction(grow(b, a.radius)) > 0:
                    skipped["npc_near_ui"] += 1
                    continue
                if any(overlaps(grow(b, 4), u) for u in units):
                    skipped["npc_overlaps_a_unit"] += 1
                    continue
                if any(o is not r and overlaps(b, o.box) for o in res.rendered):
                    skipped["npc_overlaps_an_npc"] += 1
                    continue
                if any(
                    overlaps(grow(b, a.radius), unsupported_box(o[2]))
                    for o in res.unsupported_near()
                    if o[2] is not None
                ):
                    skipped["npc_near_an_unsupported_npc"] += 1
                    continue
                clean.append(r)
            if clean:
                cands.append((t, ref, map_name, cell, clean, scene))
        chosen = pick(cands, a.per_session)
        per_session[p.name] = {
            "frames": len(frames),
            "candidate_frames": len(cands),
            "read": len(chosen),
        }
        for t, ref, map_name, cell, clean, scene in chosen:
            img = np.asarray(tool.open_frame(ref).convert("RGB"))
            if img.shape[:2] != (nr.SCREEN[1], nr.SCREEN[0]):
                skipped["frame_size"] += 1
                continue
            frame_matches: list[nr.Match | None] = []
            for r in clean:
                got_s = sheets(r.npc.sprite)
                assert got_s is not None
                _stem, sheet = got_s
                row: dict[str, Any] = {
                    "session": p.name,
                    "t_ns": t,
                    "map": map_name,
                    "cell": list(cell),
                    "indoor": is_indoor(map_name, table),
                    "sprite": r.npc.sprite,
                    "npc_cell": list(r.npc.cell),
                    "frames": r.motions,
                    "u": round(r.pred.anchor_px[0], 1),
                    "v": round(r.pred.anchor_px[1], 1),
                    "box_h": round(r.box[3] - r.box[1], 1),
                    "path": path_,
                }
                for k in a.k:
                    pred = r.pred
                    if k != a.k[0]:
                        alt = nr.render_scene([r.npc], scene, sheets, k)
                        if not alt.rendered:
                            continue
                        pred = alt.rendered[0].pred
                    m = nr.match_offset(img, sheet, pred, a.radius)
                    if k == a.k[0]:
                        frame_matches.append(m)
                    if m is None:
                        continue
                    tag = "" if k == a.k[0] else f"_k{k:.4f}"
                    row.update(
                        {
                            f"dx{tag}": m.dx,
                            f"dy{tag}": m.dy,
                            f"score{tag}": round(m.score, 3),
                            f"score0{tag}": None
                            if m.score_at_zero is None
                            else round(m.score_at_zero, 3),
                            f"edge{tag}": m.edge,
                        }
                    )
                if "dx" in row:
                    rows.append(row)
            verdict, _counts = nr.pixel_camera_check(frame_matches)
            camera_check[f"{'indoor' if is_indoor(map_name, table) else 'outdoor'}:{verdict}"] += 1
    summary = align_summary(rows, a.k)
    out = {
        "k": a.k,
        "radius": a.radius,
        "confident": CONFIDENT,
        "sessions": per_session,
        "skipped": dict(skipped),
        "l3_vs_packets": dict(l3check),
        "pixel_camera_check_per_frame": dict(camera_check),
        "summary": summary,
        "rows": rows,
    }
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1))
    return 0


def pick(items: Sequence[Any], n: int) -> list[Any]:
    """Up to n items spread evenly over the list (first and last included)."""
    if len(items) <= n:
        return list(items)
    step = (len(items) - 1) / (n - 1) if n > 1 else 0
    return [items[round(i * step)] for i in range(n)]


def align_summary(rows: Sequence[dict[str, Any]], ks: Sequence[float]) -> dict[str, Any]:
    good = [r for r in rows if r["score"] >= CONFIDENT and not r["edge"]]
    out: dict[str, Any] = {
        "sightings": len(rows),
        "confident": {
            thr: sum(1 for r in rows if r["score"] >= thr and not r["edge"])
            for thr in (0.4, 0.5, 0.6)
        },
        "edge_of_search": sum(1 for r in rows if r["edge"]),
        "all_confident": dist_stats(good),
    }
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in good:
        groups[f"{'indoor' if r['indoor'] else 'outdoor'}"].append(r)
        groups[f"map:{r['map']}"].append(r)
        groups[f"sprite:{r['map']}:{r['sprite']}"].append(r)
        groups[f"path:{r['path']}"].append(r)
        dist = math.hypot(r["u"] - CENTRE[0], r["v"] - CENTRE[1])
        band = (
            "0-150"
            if dist < 150
            else "150-300"
            if dist < 300
            else "300-450"
            if dist < 450
            else "450+"
        )
        groups[f"{'indoor' if r['indoor'] else 'outdoor'}:from_centre:{band}"].append(r)
        side = (
            "left"
            if r["u"] < CENTRE[0] - 150
            else "right"
            if r["u"] > CENTRE[0] + 150
            else "middle"
        )
        groups[f"{'indoor' if r['indoor'] else 'outdoor'}:u_side:{side}"].append(r)
    out["groups"] = {k: dist_stats(v) for k, v in sorted(groups.items())}
    out["fits"] = {
        f"{place}:{key}": linear_fit([r for r in good if r["indoor"] == (place == "indoor")], key)
        for place in ("indoor", "outdoor")
        for key in ("dx", "dy")
    }
    if len(ks) > 1:
        tag = f"_k{ks[1]:.4f}"
        paired = [r for r in good if f"score{tag}" in r]
        out["k_compare"] = {
            "other_k": ks[1],
            "pairs": len(paired),
            "first_k_scores_higher": sum(1 for r in paired if r["score"] > r[f"score{tag}"]),
            "other_k_scores_higher": sum(1 for r in paired if r[f"score{tag}"] > r["score"]),
            "median_score_first": q([r["score"] for r in paired], 50),
            "median_score_other": q([r[f"score{tag}"] for r in paired], 50),
        }
    return out


# --- (b) click ------------------------------------------------------------------------------------


def grab0_labels(items: Path, labels: Path) -> dict[tuple[str, str, int], str]:
    """(session, crop, grab) -> the agreed label (cursor2_truth's items.json, a labeller's
    labels.json: A and B agree on every image)."""
    it = json.loads(items.read_text())
    lab = json.loads(labels.read_text())
    return {
        (str(s), str(c), int(g)): str(lab[str(i)])
        for i, (s, c, g) in enumerate(it)
        if str(i) in lab
    }


def probes(session: Path) -> Iterable[dict[str, Any]]:
    for line in (session / "demo.jsonl").read_text().splitlines():
        rec = json.loads(line)
        ev = (rec.get("outcome") or {}).get("evidence") or {}
        if rec.get("rule") == PROBE_RULE and "crop" in ev and "at" in ev:
            yield {
                "t_ns": int((ev.get("reads") or [{}])[0].get("t_ns") or rec["t_mono_ns"]),
                "at": ev["at"],
                "kind": ev.get("kind"),
                "stand": ev.get("stand"),
                "npc_cell": ev.get("npc_cell"),
                "crop": ev["crop"],
            }


# --- the offline camera check over the design sessions ------------------------------------------

INPUT_LOG = Path("/home/batt/docker/poring-lab/data/input_log")


def session_days(session_id: str) -> list[str]:
    """The UTC days a session can touch: its id is the local (ICT, UTC+7) start time."""
    from datetime import datetime, timedelta, timezone

    start = datetime.strptime(session_id[:15], "%Y%m%dT%H%M%S").replace(
        tzinfo=timezone(timedelta(hours=7))
    )
    utc = start.astimezone(UTC)
    return sorted({(utc + timedelta(days=d)).strftime("%Y-%m-%d") for d in (0, 1)})


def cmd_camera(a: argparse.Namespace) -> int:
    """Per session: the camera inputs (rotation / zoom) the input log holds inside its window, and
    the state the offline guard gives at its end (map changes from the packets reset a rotation)."""
    import labels_v2 as tool

    out: dict[str, Any] = {}
    for p in a.sessions:
        manifest = json.loads((p / "manifest.json").read_text())
        t0, t1 = manifest.get("t0_mono_ns"), manifest.get("t1_mono_ns")
        if not t0 or not t1:
            out[p.name] = {"why": "no_window"}
            continue
        recs: list[dict[str, Any]] = []
        logs = [a.input_log / f"{d}.jsonl" for d in session_days(p.name)]
        present = [x for x in logs if x.exists()]
        if not present:
            out[p.name] = {"why": "no_input_log"}
            continue
        for x in present:
            recs += nr.read_input_window(x, int(t0) - a.before_s * 1_000_000_000, int(t1))
        events = nr.camera_events(recs)
        changes = []
        if (p / "packets.jsonl.gz").exists():
            changes = [
                int(e["t_mono_ns"]) for e in tool.load_events(p) if e.get("type") == "map_change"
            ]
        log = nr.CameraLog(events, changes)
        inside = [e for e in events if int(t0) <= e.t_ns <= int(t1)]
        out[p.name] = {
            "logs": [x.name for x in present],
            "records": len(recs),
            "camera_inputs_in_window": dict(Counter(f"{e.kind}:{e.source}" for e in inside)),
            "state_at_start": log.state_at(int(t0))[0],
            "state_at_end": log.state_at(int(t1))[0],
        }
    flagged = sorted(
        k
        for k, v in out.items()
        if v.get("camera_inputs_in_window") or v.get("state_at_start", "default") != "default"
    )
    print(json.dumps({"sessions": out, "flagged": flagged}, indent=1))
    if a.out:
        a.out.write_text(json.dumps({"sessions": out, "flagged": flagged}, indent=1) + "\n")
    return 0


def cmd_click(a: argparse.Namespace) -> int:
    import labels_v2 as tool

    sheets = nr.sheets_from_files(a.sprites, a.names)
    truth = grab0_labels(a.items, a.labels)
    rows: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    for p in a.sessions:
        sess = tool.Session(p, session_args(a.kb))
        manifest = json.loads((p / "manifest.json").read_text())
        map_name = map_key(str(manifest.get("map")))
        path_ = camera_path(sess.backend)
        renders: dict[tuple[int, int], nr.RenderResult] = {}
        for pr in probes(p):
            label = truth.get((p.name, pr["crop"], 0))
            if label is None:
                skipped["no_label"] += 1
                continue
            w = sess.world(pr["t_ns"])
            if w.self_pos is None or map_key(w.map or "") != map_name:
                skipped["no_world"] += 1
                continue
            cell = (int(round(w.self_pos[0])), int(round(w.self_pos[1])))
            moving = w.self_pos != (float(cell[0]), float(cell[1]))
            if cell not in renders:
                renders[cell] = nr.render(map_name, cell, path_, k=a.k, kb_dir=a.kb, sheets=sheets)
            res = renders[cell]
            u, v = float(pr["at"][0]), float(pr["at"][1])
            hits = res.hits(u, v)
            boxes = [r for r in res.rendered if r.in_box(u, v)]
            near = min(res.rendered, key=lambda r: r.distance(u, v), default=None)
            near_box = min(res.rendered, key=lambda r: box_distance(r.box, u, v), default=None)
            target = next(
                (
                    r
                    for r in res.rendered
                    if pr["npc_cell"] is not None and list(r.npc.cell) == list(pr["npc_cell"])
                ),
                None,
            )
            unsupported_target = any(
                list(n.cell) == list(pr["npc_cell"] or []) for n, _w, _a in res.unsupported
            )
            rows.append(
                {
                    "session": p.name,
                    "map": map_name,
                    "kind": pr["kind"],
                    "label": label,
                    "at": [u, v],
                    "stand": pr["stand"],
                    "gm_cell": list(cell),
                    "moving": moving,
                    "stand_agrees": list(cell) == list(pr["stand"] or []),
                    "npc_cell": pr["npc_cell"],
                    "target_sprite": None if target is None else target.npc.sprite,
                    "target_unsupported": unsupported_target,
                    "in_mask": bool(hits),
                    "mask_sprite": hits[0].npc.sprite if hits else None,
                    "in_box": bool(boxes),
                    "nearest_sprite": None if near is None else near.npc.sprite,
                    "mask_distance": None if near is None else round(near.distance(u, v), 1),
                    "box_distance": None
                    if near_box is None
                    else round(box_distance(near_box.box, u, v), 1),
                    "rel_target": None if target is None else rel(target, u, v),
                    "complete": res.complete,
                }
            )
    summary = click_summary(rows)
    out = {"k": a.k, "skipped": dict(skipped), "summary": summary, "rows": rows}
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1))
    return 0


def box_distance(b: Box, u: float, v: float) -> float:
    """px from (u, v) to the box (0 inside)."""
    du = max(b[0] - u, 0.0, u - b[2])
    dv = max(b[1] - v, 0.0, v - b[3])
    return math.hypot(du, dv)


def rel(r: nr.RenderedNpc, u: float, v: float) -> dict[str, float]:
    """The point against the target's render: px from its feet (anchor), the same in native
    sprite px (/ scale), and its envelope box in sprite px."""
    au, av = r.pred.anchor_px
    s = r.pred.scale
    b = r.box
    return {
        "du_px": round(u - au, 1),
        "dv_px": round(v - av, 1),
        "du_sprite": round((u - au) / s, 1),
        "dv_sprite": round((v - av) / s, 1),
        "box_sprite": [
            round((b[0] - au) / s, 1),
            round((b[1] - av) / s, 1),
            round((b[2] - au) / s, 1),
            round((b[3] - av) / s, 1),
        ],
        "scale": round(s, 4),
    }


DILATIONS = (0, 4, 8, 12, 16, 20, 24, 32)


def dilation_curve(rows: Sequence[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    """For a no-click region = the rendered mask (or box) grown by d px: the share of TALK points
    inside it (coverage) and of non-TALK points inside it (over-coverage), per d."""
    talk = [r for r in rows if r["label"] == "talk" and r[key] is not None]
    other = [
        r
        for r in rows
        if r["label"] in ("walk", "noentry", "sword", "pickup", "warp") and r[key] is not None
    ]
    out = []
    for d in DILATIONS:
        t = sum(1 for r in talk if r[key] <= d)
        o = sum(1 for r in other if r[key] <= d)
        out.append(
            {
                "d_px": d,
                "talk_covered": t,
                "talk_n": len(talk),
                "talk_share": round(t / len(talk), 3) if talk else None,
                "other_inside": o,
                "other_n": len(other),
                "other_share": round(o / len(other), 3) if other else None,
            }
        )
    return out


def share(rows: Sequence[dict[str, Any]], key: str) -> dict[str, Any]:
    n = len(rows)
    k = sum(1 for r in rows if r[key])
    return {"n": n, "yes": k, "share": round(k / n, 3) if n else None}


def click_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """TALK coverage (TALK points inside the mask / box), over-coverage (non-TALK points inside),
    and where TALK answers beyond the drawn pixels."""
    usable = [r for r in rows if not r["target_unsupported"] and not r["moving"]]

    def block(rs: Sequence[dict[str, Any]]) -> dict[str, Any]:
        talk = [r for r in rs if r["label"] == "talk"]
        other = [r for r in rs if r["label"] in ("walk", "noentry", "sword", "pickup", "warp")]
        outside = [r for r in talk if not r["in_mask"]]
        d = [r["mask_distance"] for r in outside if r["mask_distance"] is not None]
        return {
            "mask_dilation": dilation_curve(rs, "mask_distance"),
            "box_dilation": dilation_curve(rs, "box_distance"),
            "talk_in_mask": share(talk, "in_mask"),
            "talk_in_box": share(talk, "in_box"),
            "other_in_mask": share(other, "in_mask"),
            "other_in_box": share(other, "in_box"),
            "other_in_mask_by_label": dict(Counter(r["label"] for r in other if r["in_mask"])),
            "talk_outside_mask": len(outside),
            "talk_outside_mask_but_in_box": sum(1 for r in outside if r["in_box"]),
            "talk_outside_distance_px": {
                "median": q(d, 50),
                "p90": q(d, 90),
                "max": max(d) if d else None,
                "within_4": sum(1 for x in d if x <= 4),
                "within_8": sum(1 for x in d if x <= 8),
            },
        }

    out: dict[str, Any] = {
        "probes": len(rows),
        "usable": len(usable),
        "excluded_target_unsupported": sum(1 for r in rows if r["target_unsupported"]),
        "excluded_gm_moving": sum(1 for r in rows if r["moving"]),
        "stand_agrees_with_packets": sum(1 for r in rows if r["stand_agrees"]),
        "all": block(usable),
    }
    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in usable:
        by[f"map:{r['map']}"].append(r)
        by[f"kind:{r['kind']}"].append(r)
        if r["target_sprite"] is not None:
            by[f"target:{r['map']}:{r['target_sprite']}"].append(r)
    out["groups"] = {k: block(v) for k, v in sorted(by.items())}
    return out


# --- main -----------------------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("sessions", nargs="+", type=Path)
        p.add_argument("--names", type=Path, required=True)
        p.add_argument("--sprites", type=Path, default=nr.SPRITES)
        p.add_argument("--kb", type=Path, default=nr.KB)
        p.add_argument("--out", type=Path, default=None)

    p = sub.add_parser("align")
    common(p)
    p.add_argument("--k", type=float, nargs="+", default=[nr.DEFAULT_K, K_NOSTALRO])
    p.add_argument("--radius", type=int, default=24)
    p.add_argument("--per-session", type=int, default=15)
    p.add_argument("--every-png", type=int, default=10)
    p = sub.add_parser("camera")
    p.add_argument("sessions", nargs="+", type=Path)
    p.add_argument("--input-log", type=Path, default=INPUT_LOG)
    p.add_argument("--before-s", type=int, default=600, help="look back before the session")
    p.add_argument("--out", type=Path, default=None)
    p = sub.add_parser("click")
    common(p)
    p.add_argument("--items", type=Path, required=True)
    p.add_argument("--labels", type=Path, required=True)
    p.add_argument("--k", type=float, default=nr.DEFAULT_K)
    a = ap.parse_args(argv)
    return {"align": cmd_align, "click": cmd_click, "camera": cmd_camera}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
