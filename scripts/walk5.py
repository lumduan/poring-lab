#!/usr/bin/env python3
"""walk@5 (docs/demonstrations.md 3.8; Batt's design, 2026-10-07 ~15:30): walk like the monsters.

    walk5.py --scene indoor|outdoor [--n 50] [--seed 20261013] [--label walk5-alone]

Batt's diagnosis of the indoor failures: long clicks across pews and walls fail (the server's
path limit is 32 steps, MAX_WALKPATH; an unwalkable target does not move the character), and the
client turns the cursor into a red NO-ENTRY sign over an unwalkable cell. So:
1. PLAN with A* on the GAT (poring_dataset.walk.walk_path), then split the path into straight or
   diagonal runs of at most SEG_MAX cells, each ending inside the click band.
2. HOVER-PROBE every segment end before clicking:
   - green chevrons that name the target cell (rule_run.identify_cell, the corner anchors) -> click;
   - chevrons naming a neighbour -> one correction (move by the projected difference);
   - the no-entry sign (NOENTRY_MIN of the calibrated ring mask) -> never click;
   - nothing (a plain arrow: occluded, an NPC, a wall top) -> the in-cell alternates.
3. A no-entry sign on a cell the GAT calls walkable means OUR POSITION BELIEF is wrong: stop,
   RE-LOCALISE, re-plan, continue. Re-localisation v1 (this file) uses the map's own structure as
   the landmark: the camera follows the TRUE player, so hovering a screen offset o reports
   walkable(true + o). Candidates near the belief predict those outcomes from the GAT; probes that
   split them, on flat cells, eliminate all but one. (The static-NPC landmark fix is v2: it needs
   NPC placements and NPC sprites, which are not built yet.)
4. Arrival per segment: dead reckoning live (the minimap outdoors); packets offline for scoring.
Pixels in, input out: the rule never reads packets. Client pixels stay in /dev/shm.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import record_session  # noqa: E402
import ro_agent as r  # noqa: E402
import rule_run as rr  # noqa: E402

from poring_env.demo import Action, DemoLog, DemoRecord, Intended, new_session_id  # noqa: E402

WALK5_RULE = "walk@5"
SEG_MAX = 5  # cells per click: a straight run, far under the server's 32 (path.hpp MAX_WALKPATH)
PLAN_MAX = 48  # the A* plan's own step limit (it is split into clicks)
NOENTRY_MIN = 0.4  # fraction of the calibrated ring mask that is red (RDP: walkable <= 0.07,
#                    no-entry 0.66-1.0; walk5 cursor calibration 2026-10-07, 40 + 16 hovers)
# client pixels: data/ (gitignored) survives a reboot; the design-time copy stays in /dev/shm
_MASK_DATA = Path(__file__).resolve().parents[1] / "data/walk6/noentry_mask_rdp.npy"
_MASK_SHM = Path("/dev/shm/poring-lab-tmp/walk5-cal/noentry_mask_rdp.npy")
NOENTRY_MASK = _MASK_DATA if _MASK_DATA.exists() else _MASK_SHM
RELOC_RADIUS = 2  # candidate cells: the belief +-2
RELOC_PROBES = 8
STEP_S, ARRIVE_S = 0.21, 0.8  # wait per cell (diagonal-safe at speed 150) + margin


class GatGrid:
    """poring_dataset.walk.Grid over a GAT walkable array."""

    def __init__(self, walkable: Any) -> None:
        self.w = np.asarray(walkable, dtype=bool)
        self.ys, self.xs = self.w.shape

    def nopass(self, x: int, y: int) -> bool:
        return not (0 <= x < self.xs and 0 <= y < self.ys and bool(self.w[y, x]))


def split_segments(
    start: tuple[int, int], path: Sequence[tuple[int, int]], seg_max: int = SEG_MAX
) -> list[tuple[int, int]]:
    """The segment ENDS: the path cut wherever the step direction changes, and every seg_max
    cells within a run. Each segment is a straight or diagonal run from the previous end."""
    ends: list[tuple[int, int]] = []
    prev, run_dir, run_len = start, None, 0
    for cell in path:
        d = (cell[0] - prev[0], cell[1] - prev[1])
        if run_dir is not None and (d != run_dir or run_len >= seg_max):
            ends.append(prev)
            run_len = 0
        run_dir = d
        run_len += 1
        prev = cell
    if path:
        ends.append(path[-1])
    return ends


def noentry_score(crop_bgr: Any, mask: Any) -> float:
    """The fraction of the ring mask that is red in a 64x64 BGR crop centred on the hotspot."""
    c = np.asarray(crop_bgr)[..., :3].astype(int)
    b, g, red = c[..., 0], c[..., 1], c[..., 2]
    hit = (red > 170) & (g < 90) & (b < 90)
    m = np.asarray(mask, dtype=bool)
    return float(hit[m].mean()) if m.any() else 0.0


def best_probe(
    candidates: Sequence[tuple[int, int]],
    walkable: Any,
    altitude: Any,
    offsets: Sequence[tuple[int, int]],
) -> tuple[int, int] | None:  # fmt: skip
    """The screen offset whose walkability best splits the candidates (max of the minority), on
    cells FLAT for every candidate (relative altitude 0), so one pixel serves all of them."""
    best: tuple[int, tuple[int, int]] | None = None
    for o in offsets:
        outs, flat = [], True
        for cx, cy in candidates:
            x, y = cx + o[0], cy + o[1]
            if not (0 <= y < walkable.shape[0] and 0 <= x < walkable.shape[1]):
                flat = False
                break
            if abs(float(altitude[y, x]) - float(altitude[cy, cx])) > 1e-6:
                flat = False
                break
            outs.append(bool(walkable[y, x]))
        if not flat or not outs:
            continue
        minority = min(sum(outs), len(outs) - sum(outs))
        if minority and (best is None or minority > best[0]):
            best = (minority, o)
    return None if best is None else best[1]


def eliminate(
    candidates: Sequence[tuple[int, int]], walkable: Any, o: tuple[int, int], walk: bool
) -> list[tuple[int, int]]:
    """The candidates whose GAT agrees with the probe's outcome at offset o."""
    return [(x, y) for x, y in candidates if bool(walkable[y + o[1], x + o[0]]) == walk]


def probe(agent: r.Agent, screen: r.Screen, u: float, v: float, mask: Any) -> dict[str, Any]:
    """Hover client pixel (u, v) with two motions; report chevrons and the no-entry score."""
    gx, gy, _, _ = r.game_region()
    px, py = gx + round(u), gy + round(v)
    agent.move(px - rr.HOVER_APPROACH_PX, py - rr.HOVER_APPROACH_PX)
    time.sleep(rr.HOVER_APPROACH_S)
    agent.move(px, py)
    time.sleep(rr.HOVER_S)
    big = screen.grab(px - 60, py - 60, 120, 120)[1]
    comps = rr.green_components(big)
    small = big[28:92, 28:92]
    pts = [(x + px - 60 - gx, y + py - 60 - gy) for x, y, _ in comps]
    total = sum(n for *_, n in comps)
    return {"comps": pts, "marker_px": total, "noentry": noentry_score(small, mask)}


def classify(p: dict[str, Any]) -> str:
    """chevrons | noentry | nothing."""
    if p["noentry"] >= NOENTRY_MIN:
        return "noentry"
    if p["marker_px"] >= rr.MIN_MARKER_PX and len(p["comps"]) >= rr.MIN_CHEVRONS:
        return "chevrons"
    return "nothing"


class World:
    """What the rule knows: the camera, the GAT (walkability + altitude) and its BELIEVED cell."""

    def __init__(self, camera: Any, gat: Any, position: tuple[int, int]) -> None:
        self.camera, self.gat = camera, gat
        self.walkable = gat.walkable()
        self.altitude = gat.altitude
        self.grid = GatGrid(self.walkable)
        self.position = position

    def project(self, cells: Any) -> Any:
        """Screen pixels of ABSOLUTE cells, relative to the believed position (GAT altitude)."""
        c = np.asarray(cells, dtype=float) - np.asarray(self.position, dtype=float)
        return self.camera.project(c, self.gat.relative_altitude(self.position, c))


def segment_step(agent: r.Agent, screen: r.Screen, w: World, end: tuple[int, int], mask: Any,
                 band: tuple[int, int, int, int]) -> dict[str, Any]:  # fmt: skip
    """Probe and (maybe) click ONE segment end. Returns {"clicked": bool, "outcome", "hovers"}."""
    rel = (end[0] - w.position[0], end[1] - w.position[1])
    cells = np.array([(end[0] + dx, end[1] + dy) for dx, dy in rr.NB9], dtype=float)
    proj = w.project(cells)
    queue = rr.in_cell_points(proj)
    hovers: list[dict[str, Any]] = []
    corrected = False
    while queue and len(hovers) < rr.MAX_HOVERS:
        u, v = queue.pop(0)
        p = probe(agent, screen, u, v, mask)
        kind = classify(p)
        k = None
        if kind == "chevrons":
            k, _ = rr.identify_cell(w.camera, w.gat, w.position, rel, p["comps"])
        hovers.append({"at": [round(u, 1), round(v, 1)], "kind": kind, "cell": k,
                       "noentry": round(p["noentry"], 2), "marker_px": p["marker_px"]})  # fmt: skip
        if kind == "noentry":
            return {"clicked": False, "outcome": "noentry", "hovers": hovers}
        if kind == "chevrons" and k == (0, 0):
            gx, gy, _, _ = r.game_region()
            agent.click(gx + round(u), gy + round(v))
            return {"clicked": True, "outcome": "confirmed", "hovers": hovers, "at": (u, v)}
        if kind == "chevrons" and k is not None and not corrected:
            i = rr.NB9.index(k)
            queue.insert(
                0, (u + float(proj[4][0] - proj[i][0]), v + float(proj[4][1] - proj[i][1]))
            )
            corrected = True
        elif kind == "chevrons" and k is not None:
            return {"clicked": False, "outcome": "neighbour", "hovers": hovers}
    return {"clicked": False, "outcome": "unconfirmed", "hovers": hovers}


def relocalise(agent: r.Agent, screen: r.Screen, w: World, mask: Any,
               band: tuple[int, int, int, int]) -> dict[str, Any]:  # fmt: skip
    """Re-localisation v1: the structure as the landmark (see the module docstring)."""
    bx, by = w.position
    cands = [(bx + dx, by + dy) for dy in range(-RELOC_RADIUS, RELOC_RADIUS + 1)
             for dx in range(-RELOC_RADIUS, RELOC_RADIUS + 1)
             if w.walkable[by + dy, bx + dx]]  # fmt: skip
    x0, y0, x1, y1 = band
    offsets = []
    for dy in range(-5, 6):
        for dx in range(-6, 7):
            if max(abs(dx), abs(dy)) < 2:
                continue
            u, v = w.camera.project(np.array([(dx, dy)], dtype=float), None)[0]
            if x0 <= u <= x1 and y0 <= v <= y1:
                offsets.append((dx, dy))
    probes: list[dict[str, Any]] = []
    tried: set[tuple[int, int]] = set()
    while len(cands) > 1 and len(probes) < RELOC_PROBES:
        o = best_probe(cands, w.walkable, w.altitude, [x for x in offsets if x not in tried])
        if o is None:
            break
        tried.add(o)
        u, v = w.camera.project(np.array([o], dtype=float), None)[0]  # flat: same for all
        kind = classify(probe(agent, screen, float(u), float(v), mask))
        probes.append({"offset": list(o), "kind": kind, "candidates": len(cands)})
        if kind == "nothing":
            continue
        cands = eliminate(cands, w.walkable, o, kind == "chevrons")
    if len(cands) == 1:
        old, w.position = w.position, cands[0]
        return {"ok": True, "from": list(old), "to": list(cands[0]), "probes": probes}
    return {"ok": False, "left": len(cands), "probes": probes}


def walk_route(agent: r.Agent, screen: r.Screen, w: World, goal: tuple[int, int], mask: Any,
               band: tuple[int, int, int, int], log_seg: Any,
               read_position: Any = None) -> dict[str, Any]:  # fmt: skip
    """walk@5, ALONE: plan, then walk segment by segment with the probe gate; a no-entry on a
    GAT-walkable cell (or a neighbour confirmed twice) re-localises and re-plans."""
    events: list[dict[str, Any]] = []
    relocs = 0
    for _ in range(12):  # at most 12 segment attempts per route
        if read_position is not None:
            pos = read_position()
            if pos is not None:
                w.position = pos
        if w.position == goal:
            return {"arrived_belief": True, "events": events, "relocs": relocs}
        path = rr_walk_path(w, goal)
        if path is None:
            return {"decline": "no_plan", "events": events, "relocs": relocs}
        ends = split_segments(w.position, path)
        end = ends[0]
        x0, y0, x1, y1 = band
        while True:  # shorten until the end is inside the click band
            u, v = w.project([end])[0]
            if x0 <= u <= x1 and y0 <= v <= y1:
                break
            k = path.index(end)
            if k == 0:
                return {"decline": "out_of_band", "events": events, "relocs": relocs}
            end = path[k - 1]
        t0 = r.ns()
        step = segment_step(agent, screen, w, end, mask, band)
        ev = {"from": list(w.position), "end": list(end), **{k: v for k, v in step.items()
                                                                if k != "at"}}  # fmt: skip
        log_seg(t0, w.position, end, step)
        events.append(ev)
        if step["clicked"]:
            n = max(abs(end[0] - w.position[0]), abs(end[1] - w.position[1]))
            w.position = end  # dead reckoning
            time.sleep(n * STEP_S + ARRIVE_S)
            continue
        if step["outcome"] in ("noentry", "neighbour") and w.walkable[end[1], end[0]]:
            if relocs >= 2:
                return {"decline": "relocalise_limit", "events": events, "relocs": relocs}
            rl = relocalise(agent, screen, w, mask, band)
            relocs += 1
            events.append({"relocalise": rl})
            if not rl["ok"]:
                return {"decline": "relocalise_failed", "events": events, "relocs": relocs}
            continue
        return {"decline": f"segment_{step['outcome']}", "events": events, "relocs": relocs}
    return {"decline": "segment_limit", "events": events, "relocs": relocs}


def rr_walk_path(w: World, goal: tuple[int, int]) -> list[tuple[int, int]] | None:
    from poring_dataset.walk import walk_path

    return walk_path(w.grid, w.position[0], w.position[1], goal[0], goal[1], max_len=PLAN_MAX)


def run(scene: str, n: int, seed: int, label: str) -> int:
    import random

    import bench

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod
    from poring_env import selfpos

    mask = np.load(NOENTRY_MASK)
    mapname, sx0, sy0 = rr.SCENES[scene]
    gat = gatmod.parse((cam.GAT_DIR / f"{mapname}.gat").read_bytes())
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    base = cam.camera_from_json(cj["camera"])
    indoor = scene == "indoor"
    camera = (cam.camera_for_map(base, True, cj["indoor"]["yaw_deg"], cj["indoor"]["distance"])
              if indoor else base)  # fmt: skip
    w = World(camera, gat, (sx0, sy0))
    templates = None if indoor else selfpos.load_digit_templates()
    band = rr.ec_band()
    rng = random.Random(seed)
    sid = new_session_id(f"{label}-{scene}")
    log = DemoLog(sid)
    lock = record_session.read_lock(r.ROOT / "state")
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena", rule=WALK5_RULE,
              n=n, scene=scene, seed=seed, account="gm", seg_max=SEG_MAX)  # fmt: skip
    print(json.dumps({"session": sid, "rule": WALK5_RULE, "scene": scene}), flush=True)
    t_first = r.ns()
    with r.session(f"rule:{WALK5_RULE}") as (agent, screen):
        r.gm(agent, screen, f"@warp {mapname} {sx0} {sy0}")  # the harness enters the scene once
        time.sleep(rr.SCENE_ENTRY_S)
        bench.close_chat(agent, screen)

        def read_position() -> tuple[int, int] | None:
            if indoor:
                return None
            xy = selfpos.read_minimap_xy(screen.grab(*r.game_region())[1][:, :, :3], templates)
            return None if xy is None else (int(xy[0]), int(xy[1]))

        for i in range(n):
            if i % rr.DR_WARP_EVERY == 0:  # the HARNESS: a seeded warp, the rule's known start
                if i % 10 == 0 and not indoor:
                    r.gm(agent, screen, "@killmonster2")
                for _ in range(200):
                    sx, sy = sx0 + rng.randint(-8, 8), sy0 + rng.randint(-8, 8)
                    if w.walkable[sy, sx]:
                        break
                r.gm(agent, screen, f"@warp {mapname} {sx} {sy}")
                time.sleep(rr.WARP_SETTLE_S)
                bench.close_chat(agent, screen)
                w.position = (sx, sy)
            r.activate_client(agent, screen)
            if not indoor:
                pos = read_position()
                if pos is not None:
                    w.position = pos
            # the HARNESS: a seeded goal 8-20 A* steps from the BELIEVED position
            goal = None
            for _ in range(400):
                g = (w.position[0] + rng.randint(-12, 12), w.position[1] + rng.randint(-12, 12))
                if not (0 <= g[1] < w.walkable.shape[0] and 0 <= g[0] < w.walkable.shape[1]):
                    continue
                if not w.walkable[g[1], g[0]]:
                    continue
                path = rr_walk_path(w, g)
                if path is not None and 8 <= len(path) <= 20:
                    goal = g
                    break
            start, t_route = w.position, r.ns()
            pre = rr.snap(log, screen, f"{i:03d}-route-before")

            def log_seg(t0: int, frm: tuple[int, int], end: tuple[int, int],
                        step: dict[str, Any], i: int = i) -> None:  # fmt: skip
                if not step["clicked"]:
                    return  # a refused probe is route evidence, not a walk attempt
                log.append(DemoRecord(
                    session=sid, actor=f"rule:{WALK5_RULE}", t_mono_ns=t0, t_done_ns=r.ns(),
                    rule=f"{WALK5_RULE}/segment", scene=f"{scene}:{mapname}",
                    cue="walk@5 segment: A* run <= 5 cells; clicked after the probe confirmed it",
                    action=Action(type="walk", points=[step["at"]],
                                  intended=Intended(kind="cell", cell=end, relative=False,
                                                    note=f"route {i} believed {frm[0]},{frm[1]}")),
                    outcome={"status": "pending", "evidence": {  # type: ignore[arg-type]
                        "hovers": step["hovers"], "believed_position": list(frm)}},
                ))  # fmt: skip

            if goal is None:
                did: dict[str, Any] = {"decline": "no_goal", "events": [], "relocs": 0}
            else:
                did = walk_route(agent, screen, w, goal, mask, band, log_seg,
                                 read_position if not indoor else None)  # fmt: skip
            log.append(DemoRecord(
                session=sid, actor=f"rule:{WALK5_RULE}", t_mono_ns=t_route, t_done_ns=r.ns(),
                frame=pre, rule=WALK5_RULE, scene=f"{scene}:{mapname}",
                cue="walk@5 route: A* plan, straight segments, probe gate, re-localise on mismatch",
                action=Action(type="walk", intended=Intended(
                    kind="route", cell=goal or start, relative=False,
                    note=f"route {i} from believed {start[0]},{start[1]}")),
                outcome={"status": "pending", "evidence": {  # type: ignore[arg-type]
                    "start_believed": list(start), "goal": list(goal) if goal else None,
                    "end_believed": list(w.position), **did}},
            ))  # fmt: skip
            print(json.dumps({"route": i, "start": list(start), "goal": goal,
                              "end_believed": list(w.position), "decline": did.get("decline"),
                              "segments": sum(1 for e in did["events"] if e.get("clicked")),
                              "probes_refused": sum(1 for e in did["events"]
                                                    if "clicked" in e and not e["clicked"]),
                              "relocs": did["relocs"]}), flush=True)  # fmt: skip
            time.sleep(0.5)
    events, anchor = record_session.write_packets(log.dir, t_first, r.ns())
    log.finish(packet_events=len(events), packet_anchor=anchor, routes=n)
    print(json.dumps({"session": sid, "packet_events": len(events), "routes": n}), flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--scene", choices=sorted(rr.SCENES), required=True)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=20261013)
    ap.add_argument("--label", default="walk5-alone")
    a = ap.parse_args()
    if not NOENTRY_MASK.exists():
        raise SystemExit(f"{NOENTRY_MASK} missing: run the walk5 cursor calibration (design time)")
    return run(a.scene, a.n, a.seed, a.label)


if __name__ == "__main__":
    sys.exit(main())
