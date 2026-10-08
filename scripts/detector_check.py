#!/usr/bin/env python3
"""Can walk@11's unit detector SEE the units on RDP frames? (Batt 2026-10-08: a safety sensor must
prove a positive case.) Design-time, the TUNING maps; packets are offline ground truth only.

    detector_check.py record [--frames 40] [--porings 6]      then
    detector_check.py score SESSION_DIR [--conf 0.25]

record: for each scene (prt_fild08 outdoor, prt_church indoor), @killmonster2, spawn Porings,
then grab --frames frames ~1 s apart (the capture time kept) and run the detector on each, saving
frames and boxes to /dev/shm (client pixels: never committed). No click, no hover.
score: the packet-derived boxes at each frame's time (qa_export.Labeler, the same ground truth
demo_verify uses) vs the detections, inside the click band; recall per class, false detections,
and the foot offset (detected box bottom - ground-truth box bottom).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import record_session  # noqa: E402
import ro_agent as r  # noqa: E402
import rule_run as rr  # noqa: E402

from poring_env.demo import DemoLog, new_session_id  # noqa: E402

SCENES = (("prt_fild08", 268, 107), ("prt_church", 100, 114))
BAND = (200, 140, 1080, 560)  # client px: where walk clicks land (walk@9's MOVE_BAND)
FRAMES_DIR = Path("/dev/shm/poring-lab-tmp/detector-check")
MATCH_PX = 30.0  # a detection matches a ground-truth unit when their feet are this close


def record(frames: int, porings: int) -> int:
    import bench
    import unit_detector

    det = unit_detector.UnitDetector()
    sid = new_session_id("detector-check")
    log = DemoLog(sid)
    lock = record_session.read_lock(r.ROOT / "state")
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena",
              rule="detector-check", account="gm", model=str(det.model))  # fmt: skip
    out_dir = FRAMES_DIR / sid
    out_dir.mkdir(parents=True, exist_ok=True)
    t_first = r.ns()
    rows: list[dict[str, Any]] = []
    with r.session("rule:detector-check") as (agent, screen):
        for mapname, x, y in SCENES:
            r.gm(agent, screen, "@killmonster2")
            r.gm(agent, screen, f"@warp {mapname} {x} {y}")
            time.sleep(rr.SCENE_ENTRY_S)  # a warp ONTO a map: its load takes longer than 2.5 s
            r.gm(agent, screen, f"@monster poring {porings}")
            time.sleep(1.5)
            bench.close_chat(agent, screen)
            r.activate_client(agent, screen)
            gx, gy, _, _ = r.game_region()
            agent.move(gx + 1270, gy + 700)  # the cursor parked in a corner, off the scene
            time.sleep(0.5)
            for k in range(frames):
                t = r.ns()
                frame = screen.grab(*r.game_region())[1][..., :3].copy()
                boxes = det.detect(frame)
                name = f"{mapname}-{k:03d}.npy"
                np.save(out_dir / name, frame)
                found = [[b.x0, b.y0, b.x1, b.y1, b.score, b.cls] for b in boxes]
                rows.append({"map": mapname, "t": t, "frame": name, "ms": det.last_ms,
                             "boxes": found})  # fmt: skip
                time.sleep(1.0)
        r.gm(agent, screen, "@killmonster2")
        bench.close_chat(agent, screen)
    det.close()
    (log.dir / "detections.json").write_text(json.dumps(rows))
    events, anchor = record_session.write_packets(log.dir, t_first, r.ns())
    log.finish(packet_events=len(events), packet_anchor=anchor, frames=len(rows),
               frames_dir=str(out_dir))  # fmt: skip
    print(json.dumps({"session": sid, "frames": len(rows), "dir": str(log.dir)}), flush=True)
    return 0


def in_band(u: float, v: float) -> bool:
    return BAND[0] <= u <= BAND[2] and BAND[1] <= v <= BAND[3]


def score(session: Path, conf: float, match_px: float = MATCH_PX) -> dict[str, Any]:
    import demo_verify

    rows = json.loads((session / "detections.json").read_text())
    labeler, offset_ms, _run = demo_verify.click_targets(session, None)
    gm_gid = 2000002
    per: dict[str, dict[str, int]] = {}
    offsets: list[float] = []
    false_det = 0
    skipped = 0
    for row in rows:
        gt = labeler.boxes(int(row["t"]))
        if gt is None:
            skipped += 1
            continue
        gt = [b for b in gt if b.get("gid") != gm_gid]
        dets = [d for d in row["boxes"] if d[4] >= conf]
        used: set[int] = set()
        for b in gt:
            fu, fv = (b["x1"] + b["x2"]) / 2, b["y2"]
            if not in_band(fu, fv):
                continue
            c = per.setdefault(f"{row['map']}:{b['cls']}", {"units": 0, "seen": 0})
            c["units"] += 1
            best, bj = None, None
            for j, d in enumerate(dets):
                if j in used:
                    continue
                du, dv = (d[0] + d[2]) / 2, d[3]
                dist = float(np.hypot(du - fu, dv - fv))
                if dist <= match_px and (best is None or dist < best):
                    best, bj = dist, j
            if bj is not None:
                used.add(bj)
                c["seen"] += 1
                offsets.append(float(dets[bj][3] - fv))
        false_det += sum(1 for j, d in enumerate(dets)
                         if j not in used and in_band((d[0] + d[2]) / 2, d[3]))  # fmt: skip
    recall = {k: {**v, "recall": round(v["seen"] / v["units"], 3) if v["units"] else None}
              for k, v in per.items()}  # fmt: skip
    return {"session": session.name, "conf": conf, "match_px": match_px, "offset_ms": offset_ms,
            "frames": len(rows),
            "frames_in_gm_window": skipped, "recall": recall, "unmatched_detections": false_det,
            "foot_offset_px": _quantiles(offsets)}  # fmt: skip


def _quantiles(xs: list[float]) -> dict[str, float | None]:
    if not xs:
        return {"median": None, "p10": None, "p90": None}
    q = np.percentile(xs, [50, 10, 90])
    return {"median": round(float(q[0]), 1), "p10": round(float(q[1]), 1),
            "p90": round(float(q[2]), 1)}  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("record")
    a1.add_argument("--frames", type=int, default=40)
    a1.add_argument("--porings", type=int, default=6)
    a2 = sub.add_parser("score")
    a2.add_argument("session", type=Path)
    a2.add_argument("--conf", type=float, default=0.25)
    a2.add_argument("--match-px", type=float, default=MATCH_PX)
    a = ap.parse_args()
    if a.cmd == "record":
        return record(a.frames, a.porings)
    print(json.dumps(score(a.session, a.conf, a.match_px), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
