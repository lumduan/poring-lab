#!/usr/bin/env python3
"""Fit the default camera's cell -> pixel projection (Phase 2, B4; docs/phase2-plan.md).

    calibrate_projection.py --backend rdp [--validate N]

1. Camera reset (a map change), GM at the benchmark's outdoor spot prt_fild08 170,375.
2. Click grid: for each pixel offset around the character, the GM is warped back to the spot (same
   map: the camera stays), the agent clicks, and the client's OWN pick -- its `self_move_request`
   target cell -- pairs the click pixel with a cell offset. No sprite detection involved.
3. Fit: normalised-DLT homography (poring_dataset.projection), cell offset -> client-area pixel.
   Clicks land anywhere inside a cell while the cell's centre projects to one point, so the
   residual floor is about a quarter cell; the median is reported with that caveat.
4. Validation (--validate N): GM @monster poring N; their packet cells (Timeline, walk paths)
   projected vs the bottom of each nearby pink blob in the frame -> residual px.
   Then @killmonster2 removes them (no drops).

Writes data/bench/calibration/<stamp>.json (evidence) and, with --save, the fitted camera to
packages/poring_dataset/src/poring_dataset/camera_default.json (committed: a lab constant).
Input only through /internal/agent in ASSIST (ro_agent rules); lock must say --backend.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench  # noqa: E402
import record_session  # noqa: E402
import ro_agent as r  # noqa: E402

from poring_backend.capture_lock import read_lock  # noqa: E402
from poring_dataset import mapcache, projection  # noqa: E402
from poring_dataset.timeline import Timeline  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
# Calibration spot: the most open ground on prt_fild08 by the map cache (walkable 37 cells in every
# direction, >100 cells from every edge, so far from the field's edge portals). The bench's 170,375
# has 2 open cells and lies 24 cells from the Prontera gate warp: a wide click grid walked the
# GM into it (2026-10-02).
SPOT = (268, 107)
CAMERA = ROOT / "packages" / "poring_dataset" / "src" / "poring_dataset" / "camera_default.json"
# Client-area rectangles that are UI, not world (x, y, w, h): never click there. Measured on the
# frozen 1280x720 layout (2026-10-02): Basic Information (expanded), the 4-row hotkey bar, the small
# top window, the chat window, the right-anchored notifier and minimap (outdoor maps).
UI = [
    (0, 0, 222, 325), (228, 0, 296, 135), (655, 0, 90, 40), (0, 528, 600, 98), (965, 560, 175, 36),
    (1128, 8, 152, 152),
]  # fmt: skip


def grid(gw: int, gh: int) -> list[tuple[int, int]]:
    """Client-area click points around the character's feet (the screen centre), spread wide across
    the 1280x720 view so the homography is constrained out to the edges."""
    cx, cy = gw // 2, int(gh * 0.53)
    points = []
    for dy in (-200, -130, -60, 60, 130):
        for dx in (-400, -300, -200, -100, 0, 100, 200, 300, 400):
            x, y = cx + dx, cy + dy
            if dx == 0 and dy < 0:
                continue  # on the character (its body rises ~120 px above the feet)
            if any(ux <= x < ux + uw and uy <= y < uy + uh for ux, uy, uw, uh in UI):
                continue
            points.append((x, y))
    return points


def first_after(
    events: list[dict[str, Any]], kind: str, t: int, within_ns: int
) -> dict[str, Any] | None:
    for e in events:
        if e["type"] == kind and t <= int(e["t_mono_ns"]) <= t + within_ns:
            return e
    return None


def pink_feet(img: np.ndarray, u: float, v: float, radius: int = 70) -> tuple[float, float] | None:
    """Bottom-centre of the Poring-pink pixels near (u, v) in a BGR client-area frame."""
    h, w = img.shape[:2]
    x0, x1 = max(0, int(u) - radius), min(w, int(u) + radius)
    y0, y1 = max(0, int(v) - radius), min(h, int(v) + radius)
    b, g, rch = (img[y0:y1, x0:x1, k].astype(int) for k in range(3))
    mask = (rch > 200) & (g > 90) & (g < 190) & (b > 140) & (rch - g > 50)
    ys, xs = np.nonzero(mask)
    if len(xs) < 30:
        return None
    bottom = ys.max()
    row = xs[ys >= bottom - 3]
    return float(x0 + row.mean()), float(y0 + bottom)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--backend", required=True, choices=["rdp", "console"])
    ap.add_argument("--validate", type=int, default=3)
    ap.add_argument("--save", action="store_true")
    a = ap.parse_args()
    lock = read_lock(ROOT / "state")
    if lock.backend != a.backend or lock.phase != "steady":
        raise r.Stop(f"the lock says {lock.backend}/{lock.phase}, not {a.backend}/steady")
    gx, gy, gw, gh = r.game_region()
    points = grid(gw, gh)
    clicks: list[tuple[int, tuple[int, int]]] = []
    validation: list[dict[str, Any]] = []
    with r.session("calibrate") as (agent, screen):
        r.minimize_consoles(agent, screen)
        bench.enter_scene(agent, screen, "outdoor")
        t_start = r.ns()
        for x, y in points:
            r.gm(agent, screen, f"@warp prt_fild08 {SPOT[0]} {SPOT[1]}")
            time.sleep(2.5)
            bench.close_chat(agent, screen)
            t = r.ns()
            agent.click(gx + x, gy + y)
            clicks.append((t, (x, y)))
            time.sleep(1.2)
        frames: list[tuple[int, np.ndarray]] = []
        if a.validate:
            r.gm(agent, screen, f"@warp prt_fild08 {SPOT[0]} {SPOT[1]}")
            time.sleep(2.5)
            r.gm(agent, screen, f"@monster poring {a.validate}")
            bench.close_chat(agent, screen)
            time.sleep(3)
            for _ in range(10):
                t_cap, img = screen.grab(gx, gy, gw, gh)
                frames.append((t_cap, img[:, :, :3].copy()))
                time.sleep(0.5)
            r.gm(agent, screen, "@killmonster2")
            bench.close_chat(agent, screen)
        t_end = r.ns()
    events = sorted(record_session.packets_for(t_start, t_end), key=lambda e: e["t_mono_ns"])
    src, dst = [], []
    for t, (x, y) in clicks:
        req = first_after(events, "self_move_request", t, 1_000_000_000)
        if req is not None:
            src.append((req["x"] - SPOT[0], req["y"] - SPOT[1]))
            dst.append((x, y))
    if len(src) < 6:
        raise r.Stop(f"only {len(src)} clicks produced a walk request: not enough to fit")
    fit = projection.fit(np.array(src, float), np.array(dst, float))
    offset_ms = 0.0  # the frames were grabbed with the scene static except the Porings' walks
    if frames:
        maps = mapcache.load(prere=True)
        timeline = Timeline(events, maps)
        for t_cap, img in frames:
            world = timeline.frame_world(t_cap - int(offset_ms * 1e6))
            if world.self_pos is None:
                continue
            sx, sy = world.self_pos
            for ent in world.entities:
                if ent.job != 1002:  # Poring
                    continue
                ((u, v),) = projection.project(fit.h, np.array([[ent.x - sx, ent.y - sy]]))
                seen = pink_feet(img, u, v)
                if seen is not None:
                    err = float(np.hypot(seen[0] - u, seen[1] - v))
                    validation.append({
                        "gid": ent.gid, "projected": [round(u, 1), round(v, 1)],
                        "seen": [round(seen[0], 1), round(seen[1], 1)],
                        "err_px": round(err, 1), "moving": ent.moving,
                    })  # fmt: skip
    errs = [v["err_px"] for v in validation]
    med = round(float(np.median(errs)), 1) if errs else None
    p95 = round(float(np.percentile(errs, 95)), 1) if errs else None
    result = {
        "stamp": time.strftime("%FT%T%z"), "backend": a.backend, "spot": ["prt_fild08", *SPOT],
        "game_region": [gx, gy, gw, gh], "clicks": len(clicks), "pairs": len(src),
        "h": fit.h.tolist(),
        "click_residual_px": {"median": round(fit.median_px, 1), "p95": round(fit.p95_px, 1)},
        "validation": {"n": len(errs), "median_px": med, "p95_px": p95,
                       "samples": validation[:40]},
        "pairs_detail": [{"cell": list(s), "px": list(d)} for s, d in zip(src, dst, strict=True)],
    }  # fmt: skip
    out = ROOT / "data" / "bench" / "calibration"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{time.strftime('%Y%m%dT%H%M%S')}.json").write_text(json.dumps(result, indent=1))
    if a.save:
        CAMERA.write_text(json.dumps({k: result[k] for k in (
            "stamp", "backend", "spot", "game_region", "h", "click_residual_px", "validation"
        )} | {"pairs": result["pairs"]}, indent=1) + "\n")  # fmt: skip
    print(
        json.dumps(
            {k: result[k] for k in ("pairs", "click_residual_px", "validation")}, default=str
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
