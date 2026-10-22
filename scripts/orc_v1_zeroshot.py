#!/usr/bin/env python3
"""v1 ZERO-SHOT on orcsdun01: the live CPU detector (unit_detector.UnitDetector, v1, as hunt_flow
runs it) against the packet truth of the warp-and-watch blocks
(docs/planning/orcsdun01-dungeon-prep.md section 1). Nothing is trained or tuned on these frames;
the detector never saw this map.

    orc_v1_zeroshot.py run SESSION_DIR [...] [--every 20] [--threads 8] [--out-dir DIR]
    orc_v1_zeroshot.py table ROWS_JSON [...] [--tol 40]

OFFLINE ONLY (ADR-0007): packets are ground truth for a measurement, never an agent input. The
frames are the sessions' JPEG shards (NAS, read-only); the sprites, GAT and RSW models are the
local run-time copies (/dev/shm, never committed). No GPU, no client.

``run`` reads every --every-th recorded frame inside a DWELL (events.jsonl dwell_start..dwell_end,
the GM settled at its stand), outside the GM-command windows, and writes one row per frame:
- the detector's boxes (x0, y0, x1, y1, score, class) and its time (worker ms, wall ms, CPU ms);
- the TRUTH: every monster the packets place in the GM's view at the frame's time (the packet ->
  frame offset 120 ms, measured on col3 in orcsdun01-detector.md 3c), its predicted sprite box
  (render.predict_sprite: species, Timeline action and facing, k 0.140, flyers drawn above their
  cell), the v1 visibility rule (labels_for_v1: >= half on screen, < half under the UI), the
  RSW-model overlap of 3c's 1c (``under_model``), and its Chebyshev distance to the GM's cell;
- the GM's projected anchor (the camera centres on it).

``table`` matches boxes to truth units ONE-TO-ONE, greedily by the distance between the box
centre and the predicted box centre, at a tolerance ``--tol`` px (generous: the facing errors of
3a/3c shift a predicted box sideways by up to ~half its width, and C2 measured the position itself
at 1 / 1 px), and prints the per-species recall, the precision, boxes per frame, the same within
3 cells (Chebyshev) of the GM, and the false boxes near the GM.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

MAP = "orcsdun01"
K = 0.140  # the v1 labels' k (M4); orc_camera_check.K_V1
OFFSET_MS = 120.0  # packet -> frame on this grab path (orcsdun01-detector.md 3c, 1d, from col3)
NEAR_CELLS = 3  # the defend-scan range (Chebyshev, cells)
GM_RADIUS_PX = 100.0  # "near the GM sprite": box centre within this of the GM's anchor
TOLERANCES = (24.0, 40.0, 64.0)
DEFAULT_TOL = 40.0
CELL_GRID = 20  # foot -> cell: the projected cells within this many of the GM
SPECIES = (1153, 1005, 1042, 1152, 1084, 1111, 1082)  # orcsdun01's 7 (orcsdun01-detector.md 1)
AGGRESSIVE = (1153, 1005, 1152, 1111)
NAS_RSM = Path(
    "/mnt/poring-lab-datasets/scratch-archive/2026-10-21/poring-lab-tmp/orc-labels-fix/grf/data/model"
)

Rect = tuple[float, float, float, float]


# --- pure parts ------------------------------------------------------------------------------


def centre(b: Sequence[float]) -> tuple[float, float]:
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def foot(b: Sequence[float]) -> tuple[float, float]:
    """The box's bottom centre (unit_detector.Box.foot)."""
    return ((b[0] + b[2]) / 2.0, float(b[3]))


def cheb(a: Sequence[float], b: Sequence[float]) -> int:
    return int(max(abs(round(a[0]) - round(b[0])), abs(round(a[1]) - round(b[1]))))


def greedy_match(truth: Sequence[Sequence[float]], boxes: Sequence[Sequence[float]],
                 tol: float) -> list[tuple[int, int, float]]:  # fmt: skip
    """One-to-one (truth index, box index, distance): the closest box-centre / truth-box-centre
    pairs first, each pair within ``tol`` px. Ties break by index (deterministic)."""
    pairs = []
    for ti, t in enumerate(truth):
        ct = centre(t)
        for bi, b in enumerate(boxes):
            cb = centre(b)
            d = math.hypot(ct[0] - cb[0], ct[1] - cb[1])
            if d <= tol:
                pairs.append((d, ti, bi))
    pairs.sort()
    used_t: set[int] = set()
    used_b: set[int] = set()
    out = []
    for d, ti, bi in pairs:
        if ti in used_t or bi in used_b:
            continue
        used_t.add(ti)
        used_b.add(bi)
        out.append((ti, bi, d))
    return out


def nearest_cell(pt: Sequence[float], cells: Sequence[Sequence[float]],
                 uv: Sequence[Sequence[float]]) -> tuple[int, int] | None:  # fmt: skip
    """The cell whose projected anchor ``uv[i]`` lies closest to the screen point ``pt``."""
    if not len(cells):
        return None
    a = np.asarray(uv, dtype=float)
    i = int(np.argmin(np.hypot(a[:, 0] - pt[0], a[:, 1] - pt[1])))
    return (int(cells[i][0]), int(cells[i][1]))


@dataclass
class FrameScore:
    """One frame's matching at one tolerance."""

    truth_vis: list[tuple[int, bool, bool, bool]]  # (species, matched, matched_any_class, near)
    under_model: list[bool]  # parallel to truth_vis
    boxes: int  # monster-class boxes
    box_matched: int  # matched to a visible truth unit or (2nd pass) any other monster
    box_near: int  # monster boxes whose cell is within NEAR_CELLS of the GM
    box_near_matched: int
    false_near_gm: int  # unmatched monster boxes with their centre within GM_RADIUS_PX
    duplicates: int  # unmatched monster boxes within tol of an already-matched unit


def score_frame(row: dict[str, Any], tol: float) -> FrameScore:
    """Match one frame's row (``run``'s output) at ``tol`` px.

    Pass 1: monster-class boxes vs the VISIBLE truth units (v1's rule) -> recall. Pass 2: the
    boxes left vs every other monster the packets place (not visible by v1's rule, partly off
    screen or under the UI) -> those boxes are not false. Recall "any class" also lets a player /
    npc box match. A box's cell is its matched unit's cell, else the projected cell nearest its
    foot (``foot_cell``, from ``run``)."""
    truth = row["truth"]
    vis = [t for t in truth if t["visible"]]
    rest = [t for t in truth if not t["visible"]]
    mon = [b for b in row["boxes"] if b["cls"] == "monster"]
    other = [b for b in row["boxes"] if b["cls"] != "monster"]
    m1 = greedy_match([t["box"] for t in vis], [b["box"] for b in mon], tol)
    hit_t = {ti: bi for ti, bi, _ in m1}
    left = [i for i in range(len(mon)) if i not in {bi for _, bi, _ in m1}]
    m2 = greedy_match([t["box"] for t in rest], [mon[i]["box"] for i in left], tol)
    matched_b = {bi for _, bi, _ in m1} | {left[bi] for _, bi, _ in m2}
    # any class: the visible units pass 1 left, against the non-monster boxes
    miss = [i for i in range(len(vis)) if i not in hit_t]
    m3 = greedy_match([vis[i]["box"] for i in miss], [b["box"] for b in other], tol)
    any_t = set(hit_t) | {miss[ti] for ti, _, _ in m3}
    truth_vis = [(int(t["mob"]), i in hit_t, i in any_t, t["cheb"] <= NEAR_CELLS)
                 for i, t in enumerate(vis)]  # fmt: skip
    unit_of: dict[int, dict[str, Any]] = {bi: vis[ti] for ti, bi, _ in m1}
    unit_of.update({left[bi]: rest[ti] for ti, bi, _ in m2})
    near = near_m = false_gm = dup = 0
    gm = row["gm_anchor"]
    matched_centres = [centre(t["box"]) for t in unit_of.values()]
    for i, b in enumerate(mon):
        u = unit_of.get(i)
        cell_d = u["cheb"] if u is not None else b.get("foot_cheb")
        if cell_d is not None and cell_d <= NEAR_CELLS:
            near += 1
            near_m += i in matched_b
        if i in matched_b:
            continue
        c = centre(b["box"])
        if gm is not None and math.hypot(c[0] - gm[0], c[1] - gm[1]) <= GM_RADIUS_PX:
            false_gm += 1
        if any(math.hypot(c[0] - m[0], c[1] - m[1]) <= tol for m in matched_centres):
            dup += 1
    return FrameScore(truth_vis, [bool(t.get("under_model")) for t in vis], len(mon),
                      len(matched_b), near, near_m, false_gm, dup)  # fmt: skip


def ratio(a: int, b: int) -> float | None:
    return None if b == 0 else a / b


def summarize(rows: Sequence[dict[str, Any]], tol: float) -> dict[str, Any]:
    """Per species and pooled: recall (all visible / within NEAR_CELLS / not under a model),
    the precision of the monster boxes (all / within NEAR_CELLS), boxes per frame, false boxes
    near the GM."""
    sp: dict[int, Counter[str]] = defaultdict(Counter)
    tot: Counter[str] = Counter()
    for row in rows:
        fs = score_frame(row, tol)
        tot["frames"] += 1
        tot["boxes"] += fs.boxes
        tot["box_matched"] += fs.box_matched
        tot["box_near"] += fs.box_near
        tot["box_near_matched"] += fs.box_near_matched
        tot["false_near_gm"] += fs.false_near_gm
        tot["frames_false_near_gm"] += fs.false_near_gm > 0
        tot["duplicates"] += fs.duplicates
        for (mob, hit, hit_any, near), um in zip(fs.truth_vis, fs.under_model, strict=True):
            for c in (sp[mob], tot):
                c["vis"] += 1
                c["hit"] += hit
                c["hit_any"] += hit_any
                c["near"] += near
                c["near_hit"] += hit and near
                c["clear"] += not um
                c["clear_hit"] += hit and not um

    def pack(c: Counter[str]) -> dict[str, Any]:  # fmt: skip
        return {
            "visible": c["vis"],
            "recall": ratio(c["hit"], c["vis"]),
            "recall_any_class": ratio(c["hit_any"], c["vis"]),
            "near": c["near"],
            "recall_near": ratio(c["near_hit"], c["near"]),
            "clear_of_models": c["clear"],
            "recall_clear": ratio(c["clear_hit"], c["clear"]),
        }

    n = max(tot["frames"], 1)
    return {
        "tol_px": tol, "frames": tot["frames"],
        "species": {str(m): pack(sp[m]) for m in sorted(sp)},
        "pooled": pack(tot),
        "aggressive": pack(sum((sp[m] for m in AGGRESSIVE if m in sp), Counter())),
        "boxes": tot["boxes"], "boxes_per_frame": tot["boxes"] / n,
        "precision": ratio(tot["box_matched"], tot["boxes"]),
        "boxes_near": tot["box_near"], "precision_near": ratio(tot["box_near_matched"],
                                                              tot["box_near"]),
        "false_boxes": tot["boxes"] - tot["box_matched"], "duplicates": tot["duplicates"],
        "false_near_gm": tot["false_near_gm"], "false_near_gm_per_frame": tot["false_near_gm"] / n,
        "frames_with_false_near_gm": tot["frames_false_near_gm"],
    }  # fmt: skip


def timing(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    def q(vals: list[float]) -> dict[str, float] | None:
        if not vals:
            return None
        s = sorted(vals)
        return {"p50": statistics.median(s), "p90": s[int(0.9 * (len(s) - 1))], "max": s[-1]}

    return {"worker_ms": q([r["det_ms"] for r in rows]), "wall_ms": q([r["wall_ms"] for r in rows]),
            "cpu_ms": q([r["cpu_ms"] for r in rows if r.get("cpu_ms") is not None])}  # fmt: skip


# --- the run (needs the detector env, the sprites, the GAT, the map cache) --------------------


def proc_cpu_s(pid: int) -> float | None:
    """utime + stime of a process (its threads included), seconds."""
    try:
        f = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return (int(f[11]) + int(f[12])) / os.sysconf("SC_CLK_TCK")
    except (OSError, IndexError, ValueError):
        return None


def project_cells(scene: Any, cells: np.ndarray) -> np.ndarray:
    """Cells -> game-region px (orc_labels_fix.unit_anchors' projection, altitude included)."""
    px, py = scene.player
    off = cells - np.array([px, py])
    alt = np.zeros(len(cells))
    if scene.gat is not None:
        origin = (int(math.floor(px)), int(math.floor(py)))
        rel = scene.gat.relative_altitude(origin, cells - np.array(origin, dtype=float))
        p0 = scene.gat.relative_altitude(origin, np.array([[px - origin[0], py - origin[1]]]))
        alt = rel - p0[0]
    uv: np.ndarray = scene.camera.project(off, alt)
    return uv


def run_session(session: Path, a: argparse.Namespace, det: Any) -> dict[str, Any]:
    import orc_camera_check as occ
    import qa_export

    from poring_dataset.camera import map_key, projector_for
    from poring_dataset.labels import ONE_SHOT, STATE_ACTION, in_windows, labels_for_v1
    from poring_dataset.render import Actor, MonsterAction, predict_sprite
    from poring_dataset.ui_layout import covered_fraction

    qa_export.KB_CLASSES = a.kb / "classes.json"
    qa_export.KB_SPRITE_NAMES = a.kb / "monster_sprite_names.json"
    manifest = json.loads((session / "manifest.json").read_text())
    if not qa_export.is_warp_watch(manifest) or manifest.get("map") != MAP:
        raise SystemExit(f"{session}: not an orcsdun01 warp_watch session")
    lab = qa_export.Labeler(session, str(OFFSET_MS), labels="v1", k=K)
    assert lab.sheets is not None
    occ.cache_compose()
    occluders = None
    if a.rsm_dir is not None:
        import orc_labels_fix as olf

        occluders = olf.Occluders(model_dir=a.rsm_dir)
    off = int(OFFSET_MS * 1e6)
    dwells = occ.dwell_spans(
        json.loads(x) for x in (session / "events.jsonl").read_text().splitlines() if x
    )
    refs = qa_export.jpeg_index(session, manifest)
    _proj, which = projector_for(lab.camera, MAP, indoor_table=lab.indoor)
    pid = det.proc.pid
    rows: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    grid = np.array([[dx, dy] for dx in range(-CELL_GRID, CELL_GRID + 1)
                     for dy in range(-CELL_GRID, CELL_GRID + 1)], dtype=float)  # fmt: skip
    for ref in refs[:: a.every][: a.max_frames or None]:
        t = ref.t_mono_ns
        if not in_windows(t, dwells):
            skipped["outside_dwell"] += 1
            continue
        if in_windows(t, lab.windows):
            skipped["gm_window"] += 1
            continue
        tw = t - off
        world = lab.timeline.frame_world(tw)
        if world.self_pos is None or not world.map or map_key(world.map) != MAP:
            skipped["no_world"] += 1
            continue
        scene = occ.scene_for(lab, world.map, world.self_pos)
        gm_cell = (round(world.self_pos[0]), round(world.self_pos[1]))
        gm_uv = project_cells(scene, np.array([[world.self_pos[0], world.self_pos[1]]]))[0]
        vis_gids = {lb.gid for lb in labels_for_v1(
            world, _proj, lab.size, scene=scene, state=lambda g, tw=tw: lab.timeline.state(g, tw),
            sheet=lab.sheets, k=K, ui_rects=lab.ui_rects) if lb.cls == "monster"}  # fmt: skip
        truth = []
        for e in world.entities:
            if e.objtype != 5 or e.hidden:
                continue
            sh = lab.sheets(e.job)
            st = lab.timeline.state(e.gid, tw)
            pred = None
            if sh is not None and st is not None:
                action = STATE_ACTION.get(st.state, MonsterAction.IDLE)
                heading = st.facing if st.facing is not None else (e.heading or 0)
                pred = predict_sprite(Actor((float(e.x), float(e.y)), int(heading), action,
                                            elapsed_ms=st.elapsed_ms if action in ONE_SHOT
                                            else None, duration_ms=st.duration_ms),
                                      sh, scene, K)  # fmt: skip
            if pred is None:
                uv = project_cells(scene, np.array([[e.x, e.y]], dtype=float))[0]
                box: Rect = (uv[0] - 12, uv[1] - 40, uv[0] + 12, uv[1])  # undrawn: anchor only
            else:
                box = tuple(float(v) for v in pred.box)  # type: ignore[assignment]
            truth.append({
                "gid": e.gid, "mob": e.job, "cell": [round(e.x, 2), round(e.y, 2)],
                "state": None if st is None else st.state, "drawn": pred is not None,
                "box": [round(v, 1) for v in box], "visible": e.gid in vis_gids,
                "ui_cover": round(covered_fraction(box, lab.ui_rects), 3),
                "under_model": None if occluders is None or pred is None
                else occluders.hit(scene, pred.box) is not None,
                "cheb": cheb((e.x, e.y), world.self_pos),
            })  # fmt: skip
        bgr = qa_export.read_jpeg(ref)
        c0 = proc_cpu_s(pid)
        w0 = time.perf_counter()
        boxes = det.detect(bgr)
        wall = (time.perf_counter() - w0) * 1e3
        c1 = proc_cpu_s(pid)
        cells = grid + np.array(gm_cell, dtype=float)
        uv_grid = project_cells(scene, cells)
        out_boxes = []
        for b in boxes:
            bb = (b.x0, b.y0, b.x1, b.y1)
            fc = nearest_cell(foot(bb), cells.tolist(), uv_grid.tolist())
            out_boxes.append({"box": [round(v, 1) for v in bb], "score": round(b.score, 3),
                              "cls": b.cls, "foot_cell": fc,
                              "foot_cheb": None if fc is None else cheb(fc, gm_cell)})  # fmt: skip
        rows.append({
            "frame_id": ref.frame_id, "t_ns": t, "gm_cell": list(gm_cell),
            "gm_anchor": [round(float(gm_uv[0]), 1), round(float(gm_uv[1]), 1)],
            "truth": truth, "boxes": out_boxes, "det_ms": round(det.last_ms, 1),
            "wall_ms": round(wall, 1),
            "cpu_ms": None if c0 is None or c1 is None else round((c1 - c0) * 1e3, 1),
        })  # fmt: skip
        if len(rows) % 100 == 0:
            print(f"{session.name}: {len(rows)} frames", file=sys.stderr, flush=True)
    return {
        "session": session.name, "map": MAP, "projection": which, "offset_ms": OFFSET_MS,
        "k": K, "every": a.every, "model": str(det.model), "threads": a.threads,
        "occluders": None if occluders is None else str(a.rsm_dir),
        "frames_recorded": len(refs), "skipped": dict(skipped), "rows": rows,
    }  # fmt: skip


def cmd_run(a: argparse.Namespace) -> int:
    import unit_detector

    a.out_dir.mkdir(parents=True, exist_ok=True)
    with unit_detector.UnitDetector(threads=a.threads) as det:
        for s in a.sessions:
            t0 = time.time()
            res = run_session(Path(s), a, det)
            res["elapsed_s"] = round(time.time() - t0, 1)
            path = a.out_dir / f"{Path(s).name}.rows.json"
            path.write_text(json.dumps(res))
            print(f"{path}: {len(res['rows'])} frames, {res['elapsed_s']} s", file=sys.stderr)
    return 0


def fmt(v: float | None) -> str:
    return "--" if v is None else f"{100 * v:.1f} %"


def cmd_table(a: argparse.Namespace) -> int:
    out = {}
    for p in a.rows:
        res = json.loads(Path(p).read_text())
        rows = res["rows"]
        s = {str(t): summarize(rows, t) for t in TOLERANCES}
        out[res["session"]] = {"summary": s, "timing": timing(rows), "frames": len(rows),
                               "skipped": res["skipped"], "threads": res["threads"]}  # fmt: skip
        m = s[str(a.tol)]
        print(f"\n{res['session']}  ({len(rows)} frames, tol {a.tol} px)")
        print(
            "species | visible | recall | recall any class | <=3 cells n | recall <=3 | "
            "clear of models n | recall clear"
        )
        for mob, r in [*m["species"].items(), ("pooled", m["pooled"]),
                       ("aggressive", m["aggressive"])]:  # fmt: skip
            print(
                f"{mob} | {r['visible']} | {fmt(r['recall'])} | {fmt(r['recall_any_class'])} |"
                f" {r['near']} | {fmt(r['recall_near'])} | {r['clear_of_models']} |"
                f" {fmt(r['recall_clear'])}"
            )
        print(
            f"boxes {m['boxes']} ({m['boxes_per_frame']:.2f}/frame), precision "
            f"{fmt(m['precision'])}; <=3 cells: {m['boxes_near']} boxes, precision "
            f"{fmt(m['precision_near'])}; false {m['false_boxes']} (duplicates "
            f"{m['duplicates']}); false within {GM_RADIUS_PX:.0f} px of the GM "
            f"{m['false_near_gm']} in {m['frames_with_false_near_gm']} frames"
        )
        for t in TOLERANCES:
            mt = s[str(t)]
            print(
                f"  tol {t:.0f}: recall {fmt(mt['pooled']['recall'])}, <=3 "
                f"{fmt(mt['pooled']['recall_near'])}, precision {fmt(mt['precision'])}, <=3 "
                f"{fmt(mt['precision_near'])}"
            )
        print(f"timing: {out[res['session']]['timing']}")
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=1))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("sessions", nargs="+")
    r.add_argument("--every", type=int, default=20)
    r.add_argument("--max-frames", type=int, default=0, help="recorded frames considered")
    r.add_argument("--threads", type=int, default=8, help="the detector's (hunt_flow: 8)")
    r.add_argument("--kb", type=Path, default=ROOT / "data" / "kb")
    r.add_argument(
        "--rsm-dir",
        type=Path,
        default=NAS_RSM,
        help="the RSW's extracted models (1c occlusion flag); 'none' = no flag",
    )
    r.add_argument(
        "--out-dir", type=Path, default=Path("/dev/shm/poring-lab-tmp/orc-offline/zeroshot")
    )
    t = sub.add_parser("table")
    t.add_argument("rows", nargs="+")
    t.add_argument("--tol", type=float, default=DEFAULT_TOL)
    t.add_argument("--out")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        if str(a.rsm_dir) == "none":
            a.rsm_dir = None
        return cmd_run(a)
    return cmd_table(a)


if __name__ == "__main__":
    raise SystemExit(main())
