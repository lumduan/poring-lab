#!/usr/bin/env python3
"""Validate the INDOOR camera rule on a live indoor map (Post-S2 round B2, 2026-10-04).

    camera_validate.py --backend console [--map prt_church --spot 99 112] [--clicks 12]
                       [--spawns 5] [--save]

The rule (camera.py, ported from nostalro): an indoor map is drawn with the fitted outdoor camera
rotated by 45 degrees. This measures, on the SAME points, three models -- the outdoor fit as is
(yaw 0), and the fit rotated by -45 and by +45 degrees (the sign in our convention is what is
being measured) -- each with the map's GAT altitude when the GAT is extracted:

1. Clicks (no sprite detection): the GM is warped back to the spot (same map: the camera stays),
   the agent clicks a grid pixel, and the client's OWN pick -- its self_move_request cell -- pairs
   the pixel with a cell. Residual = |model(cell) - click|. A click lands anywhere inside its cell,
   so the floor is about a quarter cell. Grid pixels without the client's ground marker under the
   hovered cursor (an NPC or a wall there; empty_cell.py) are skipped: no dialog is ever opened.
2. Single-Poring spawns, ONE at a time (so the detector cannot take a neighbour's feet): a frame
   before the spawn is the background; the pink pixels that appear (outside the UI windows) are the
   Poring; their bottom centre vs model(its packet cell). @killmonster2 after each.
3. A fourth model, `indoor_fit`: yaw AND distance fitted on THIS run's clicks (the first run,
   2026-10-04, showed the indoor camera is also closer). The spawns are its HELD-OUT check.

PRE-REGISTERED (docs/s2-plan.md, before the run): the better rotated model is within ~2x the
outdoor in-sample residual (~10-20 px median); the yaw-0 model is far worse.

Writes data/bench/calibration/<stamp>-indoor-validate.json; --save records the winning offset and
its residuals in camera_<backend>.json ("indoor"). Input only through /internal/agent in ASSIST
(ro_agent's rules); the lock must say --backend.
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
import calibrate_projection as cp  # noqa: E402
import cursor_gate  # noqa: E402
import empty_cell as ec  # noqa: E402
import record_session  # noqa: E402
import ro_agent as r  # noqa: E402

from poring_backend.capture_lock import read_lock  # noqa: E402
from poring_dataset import camera as cm  # noqa: E402
from poring_dataset import gat as gatmod  # noqa: E402
from poring_dataset import mapcache  # noqa: E402
from poring_dataset.projection import camera_file  # noqa: E402
from poring_dataset.timeline import Timeline  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MODELS = {"outdoor_yaw0": None, "indoor_minus45": -45.0, "indoor_plus45": 45.0}
PINK_GROWTH_MIN = 30  # new pink pixels that make "a Poring appeared"
FIELD_BOTTOM = 520  # client-area y: the game field ends above the chat window (cp.UI)


def models(camera_json: dict[str, Any]) -> dict[str, cm.Camera]:
    block = camera_json["camera"]
    fitted = cm.camera_from_json(block, int(block.get("height", 720)))
    return {name: fitted if off is None else cm.camera_for_map(fitted, True, off)
            for name, off in MODELS.items()}  # fmt: skip


def predict(
    cam: cm.Camera, grid: "gatmod.Gat | None", origin: tuple[int, int], cell: tuple[float, float]
) -> tuple[float, float]:
    offsets = np.array([[cell[0] - origin[0], cell[1] - origin[1]]], dtype=float)
    alt = None if grid is None else grid.relative_altitude(origin, offsets)
    ((u, v),) = cam.project(offsets, alt)
    return float(u), float(v)


def pink_mask(img: np.ndarray) -> np.ndarray:
    b, g, rch = (img[:, :, k].astype(int) for k in range(3))
    return np.asarray((rch > 200) & (g > 90) & (g < 190) & (b > 140) & (rch - g > 50))


def new_pink_feet(before: np.ndarray, after: np.ndarray) -> tuple[float, float] | None:
    """Bottom centre of the pink pixels present in ``after`` but not in ``before`` (BGR frames),
    outside the client's UI windows (the chat window's GM text showed up as "new pink" at
    y ~715 on the first run, 2026-10-04)."""
    mask = pink_mask(after) & ~pink_mask(before)
    for ux, uy, uw, uh in cp.UI:
        mask[uy : uy + uh, ux : ux + uw] = False
    mask[FIELD_BOTTOM:, :] = False  # below the chat window: more UI (a pink line at y ~715)
    ys, xs = np.nonzero(mask)
    if len(xs) < PINK_GROWTH_MIN:
        return None
    bottom = ys.max()
    row = xs[ys >= bottom - 3]
    return float(row.mean()), float(bottom)


def summarise(errs: list[float]) -> dict[str, Any]:
    if not errs:
        return {"n": 0, "median_px": None, "p95_px": None}
    return {"n": len(errs), "median_px": round(float(np.median(errs)), 1),
            "p95_px": round(float(np.percentile(errs, 95)), 1)}  # fmt: skip


def main() -> int:  # noqa: PLR0915 -- one linear procedure, like calibrate_projection
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--backend", required=True, choices=["rdp", "console"])
    ap.add_argument("--map", default=bench.SCENES["indoor"][0])
    ap.add_argument("--spot", type=int, nargs=2, default=list(bench.SCENES["indoor"][1:]))
    ap.add_argument("--clicks", type=int, default=12)
    ap.add_argument("--spawns", type=int, default=5)
    ap.add_argument("--save", action="store_true")
    a = ap.parse_args()
    lock = read_lock(ROOT / "state")
    if lock.backend != a.backend or lock.phase != "steady":
        raise r.Stop(f"the lock says {lock.backend}/{lock.phase}, not {a.backend}/steady")
    table = cm.load_indoor_table()
    if not cm.is_indoor(a.map, table):
        raise r.Stop(f"{a.map} is not in the client's indoor table: nothing to validate")
    camera_json = cm.load_camera_json(camera_file(a.backend))
    cams = models(camera_json)
    gat_path = cm.GAT_DIR / f"{a.map}.gat"
    grid = gatmod.parse(gat_path.read_bytes()) if gat_path.exists() else None
    spot = (a.spot[0], a.spot[1])
    gx, gy, gw, gh = r.game_region()
    points = cp.grid(gw, gh)
    points = points[:: max(1, len(points) // max(1, a.clicks))][: a.clicks]
    clicks: list[tuple[int, tuple[int, int]]] = []
    skipped_hover = 0
    spawn_frames: list[tuple[int, np.ndarray, np.ndarray]] = []  # (t, before, after) BGR
    warp = f"@warp {a.map} {spot[0]} {spot[1]}"
    with r.session("camera-validate") as (agent, screen):
        gate = cursor_gate.prober(agent, screen)  # fails closed off RDP
        r.minimize_consoles(agent, screen)
        bench.enter_scene(agent, screen, "indoor")  # a map change: the client's default camera
        t_start = r.ns()
        for x, y in points:
            r.gm(agent, screen, warp)
            time.sleep(2.5)
            bench.close_chat(agent, screen)
            agent.move(gx + x, gy + y)
            t = r.ns()
            time.sleep(0.35)
            crop = r.grab_after(screen, ec.crop_region(gx + x, gy + y), t + 350_000_000)
            if not ec.is_empty_walk_cell(crop):
                skipped_hover += 1  # an NPC, the GM itself or a wall under the cursor
                continue
            g = cursor_gate.gated_click(gate, x, y)  # the cursor gate (Batt 2026-10-08)
            if not g["clicked"]:
                skipped_hover += 1
                continue
            clicks.append((g["t_click"], (x, y)))
            time.sleep(1.2)
        for _ in range(a.spawns):
            r.gm(agent, screen, warp)
            time.sleep(2.5)
            bench.close_chat(agent, screen)
            _, before = screen.grab(gx, gy, gw, gh)
            r.gm(agent, screen, "@monster poring 1")
            bench.close_chat(agent, screen)
            time.sleep(2.0)
            for _ in range(4):
                t_cap, img = screen.grab(gx, gy, gw, gh)
                spawn_frames.append((t_cap, before[:, :, :3].copy(), img[:, :, :3].copy()))
                time.sleep(0.5)
            r.gm(agent, screen, "@killmonster2")
            bench.close_chat(agent, screen)
            time.sleep(1.0)
        t_end = r.ns()
    events = sorted(record_session.packets_for(t_start, t_end), key=lambda e: e["t_mono_ns"])
    found = []
    for t, (x, y) in clicks:
        req = cp.first_after(events, "self_move_request", t, 1_000_000_000)
        if req is not None:
            found.append(((float(req["x"]), float(req["y"])), (x, y)))
    if len(found) >= 4:
        offsets = np.array([[c[0] - spot[0], c[1] - spot[1]] for c, _ in found])
        px = np.array([p for _, p in found], dtype=float)
        alt = None if grid is None else grid.relative_altitude(spot, offsets)
        fit = cm.fit_camera(offsets, px, altitude=alt, start=cams["indoor_plus45"],
                            free=("yaw", "distance"))  # fmt: skip
        cams["indoor_fit"] = fit.camera
    click_errs: dict[str, list[float]] = {m: [] for m in cams}
    pairs = []
    for cell, (x, y) in found:
        row: dict[str, Any] = {"cell": [int(cell[0]), int(cell[1])], "px": [x, y]}
        for name, cam in cams.items():
            u, v = predict(cam, grid, spot, cell)
            click_errs[name].append(float(np.hypot(u - x, v - y)))
            row[name] = [round(u, 1), round(v, 1)]
        pairs.append(row)
    timeline = Timeline(events, mapcache.load(prere=True))
    spawn_errs: dict[str, list[float]] = {m: [] for m in cams}
    static_errs: dict[str, list[float]] = {m: [] for m in cams}
    samples = []
    for t_cap, before, after in spawn_frames:
        world = timeline.frame_world(t_cap)
        porings = [e for e in world.entities if e.job == 1002]
        if world.self_pos is None or len(porings) != 1:
            continue  # one at a time, or the pairing is ambiguous
        seen = new_pink_feet(before, after)
        if seen is None:
            continue
        ent = porings[0]
        origin = (int(round(world.self_pos[0])), int(round(world.self_pos[1])))
        sample: dict[str, Any] = {"cell": [ent.x, ent.y], "seen": [round(seen[0], 1),
                                  round(seen[1], 1)], "moving": ent.moving}  # fmt: skip
        for name, cam in cams.items():
            u, v = predict(cam, grid, origin, (ent.x, ent.y))
            err = float(np.hypot(u - seen[0], v - seen[1]))
            spawn_errs[name].append(err)
            if not ent.moving:
                static_errs[name].append(err)
            sample[name] = round(err, 1)
        samples.append(sample)
    table_out = {
        name: {"clicks": summarise(click_errs[name]), "spawns_all": summarise(spawn_errs[name]),
               "spawns_static": summarise(static_errs[name])}
        for name in cams
    }  # fmt: skip
    # the winner is judged on the HELD-OUT spawns (indoor_fit saw the clicks)
    scored = {n: np.median(static_errs[n]) for n in cams if static_errs[n]}
    winner = min(scored, key=lambda n: scored[n]) if scored else None
    fitted = cams.get("indoor_fit")
    outdoor = cams["outdoor_yaw0"]
    result = {
        "stamp": time.strftime("%FT%T%z"), "backend": a.backend, "map": a.map, "spot": list(spot),
        "gat": grid is not None, "clicks": len(clicks), "skipped_hover": skipped_hover,
        "hover_check": "ground-marker", "pairs": len(pairs), "spawn_frames": len(spawn_frames),
        "residuals": table_out, "winner": winner,
        "indoor_fit": None if fitted is None else {
            "yaw_offset_deg": round(float(np.degrees(fitted.yaw - outdoor.yaw)), 2),
            "distance": round(float(fitted.distance), 1)},
        "outdoor_in_sample_median_px": (camera_json["camera"].get("leave_one_out", {})
                                        .get("camera_altitude", {}).get("median_px")),
        "pairs_detail": pairs, "spawn_samples": samples,
    }  # fmt: skip
    out = ROOT / "data" / "bench" / "calibration"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{time.strftime('%Y%m%dT%H%M%S')}-indoor-validate.json"
    path.write_text(json.dumps(result, indent=1))
    if a.save and winner in ("indoor_minus45", "indoor_plus45", "indoor_fit"):
        cam_path = camera_file(a.backend)
        current = json.loads(cam_path.read_text())
        if winner == "indoor_fit" and fitted is not None:
            yaw_deg = round(float(np.degrees(fitted.yaw - outdoor.yaw)), 2)
            block = {"yaw_deg": yaw_deg, "distance": round(float(fitted.distance), 1)}
        else:
            block = {"yaw_deg": MODELS[winner]}
        current["indoor"] = block | {
            "source": cm.INDOOR_SOURCE,
            "validated": {"evidence": path.name, "map": a.map, "winner": winner,
                          "residuals": table_out},
        }  # fmt: skip
        cam_path.write_text(json.dumps(current, indent=1) + "\n")
        if json.loads(cam_path.read_text())["indoor"]["yaw_deg"] != block["yaw_deg"]:
            raise r.Stop(f"{cam_path.name}: the indoor block did not read back")
    print(json.dumps({"evidence": str(path), "winner": winner, "residuals": table_out,
                      "pairs": len(pairs), "skipped_hover": skipped_hover}))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
