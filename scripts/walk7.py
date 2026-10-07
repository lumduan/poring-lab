#!/usr/bin/env python3
"""walk@7 (docs/demonstrations.md 3.12; Batt's reading of walk@6, 2026-10-07 ~18:45).

    walk7.py --scene indoor|outdoor --condition clean|crowd [--n 56] [--seed 20261016]
             [--label walk7-alone] [--crowd 4]

walk@6's GATE is right (0 unsafe clicks; 97.9 % of its clicked runs went where it meant), so it is
reused UNCHANGED (walk6.segment_step: every cell the walk cursor, the target's chevrons, the
no-motion re-check). What failed was the ROUTE's decisions under uncertainty. walk@7 changes only
those:
(a) PATIENCE for things that move. A monster's idle pause between random walks is 4.0-5.0 s
    (rAthena e985006: mob.hpp:39 MIN_RANDOMWALKTIME 4000; mob.cpp:1766 next_walktime = tick +
    rnd()%1000 + 4000 + the walk's own time; conf/battle/monster.conf mob_nopc_move_rate 100, so
    a spotted monster always walks again). A cell refused for an entity (sword, unknown) is
    probed again until PATIENCE_S has passed since its first refusal, within WAIT_BUDGET_S per
    route; only then is it routed around. Static shapes (talk = an NPC, warp = a portal) never
    move: they are routed around at once.
(b) A blocked GOAL gets a SUBSTITUTE: the nearest free cell around it (ring 1, then 2; the
    shortest plan first). The route then ends there. Offline, a substitute counts only when the
    packets put another unit within one cell of the goal when the rule substituted it.
(c) Re-localisation is triggered by evidence of a WRONG belief: a no-entry sign or a twice-named
    neighbour on a GAT-walkable cell (as walk@5/6), and now also UNCONFIRMED_STREAK targets in a
    row from one believed cell without the chevrons naming them (walk@6 routes 21-24 stayed stuck
    on that). The method is re-localisation v2 (scripts/reloc2.py, relocalise@2 / 3.11): v1 could
    not even choose a probe among the pews (relocalise@1).
(d) Every segment record's time is the CLICK (walk@6 logged the probe step's start).
Pixels in, input out: the rule never reads packets.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import record_session  # noqa: E402
import reloc2  # noqa: E402
import ro_agent as r  # noqa: E402
import rule_run as rr  # noqa: E402
import walk5 as w5  # noqa: E402
import walk6 as w6  # noqa: E402

from poring_env.demo import Action, DemoLog, DemoRecord, Intended, new_session_id  # noqa: E402

WALK7_RULE = "walk@7"
PATIENCE_S = 6.0  # one monster idle pause (<= 5.0 s, rAthena e985006) + margin
PATIENCE_POLL_S = 0.5
WAIT_BUDGET_S = 24.0  # all patience waits of one route together
STATIC_SHAPES = frozenset({"talk", "warp"})  # never move: route around at once
UNCONFIRMED_STREAK = 2
SUBSTITUTE_RINGS = (1, 2)
SUBSTITUTES = 3
REPLANS = 4
RELOCS = 2
SEGMENT_ATTEMPTS = 24
WALK = w6.WALK


def substitute_goal(w: w5.World, goal: tuple[int, int], blocked: set[tuple[int, int]],
                    tried: set[tuple[int, int]]) -> tuple[int, int] | None:  # fmt: skip
    """The nearest free cell around a blocked goal: ring 1, then ring 2; within a ring the
    shortest plan from the believed cell. None if no cell in the rings has a plan."""
    for ring in SUBSTITUTE_RINGS:
        best: tuple[int, tuple[int, int]] | None = None
        for dy in range(-ring, ring + 1):
            for dx in range(-ring, ring + 1):
                if max(abs(dx), abs(dy)) != ring:
                    continue
                c = (goal[0] + dx, goal[1] + dy)
                if c in blocked or c in tried:
                    continue
                if not (0 <= c[1] < w.walkable.shape[0] and 0 <= c[0] < w.walkable.shape[1]):
                    continue
                if not w.walkable[c[1], c[0]]:
                    continue
                path = w6.plan(w, c, blocked)
                if path is not None and (best is None or len(path) < best[0]):
                    best = (len(path), c)
        if best is not None:
            return best[1]
    return None


def walk_route(pr: w6.Prober, w: w5.World, goal: tuple[int, int], band: tuple[int, int, int, int],
               seg_start: int, log_seg: Any, noentry_mask: Any, read_position: Any = None,
               relocalise: Callable[..., dict[str, Any]] = reloc2.relocalise,
               clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:  # fmt: skip
    """walk@7, ALONE, one route: walk@6's gate per run; the route decisions (a)-(c) above."""
    events: list[dict[str, Any]] = []
    blocked: set[tuple[int, int]] = set()
    first_refused: dict[tuple[int, int], float] = {}
    tried: set[tuple[int, int]] = set()
    relocs = replans = 0
    waited = 0.0
    seg_max = seg_start
    target, substitute = goal, None
    streak, streak_from = 0, None

    def done(**kw: Any) -> dict[str, Any]:
        return {"events": events, "relocs": relocs, "replans": replans,
                "waited_s": round(waited, 1), "seg_max_end": seg_max, "substitute": substitute,
                **kw}  # fmt: skip

    for _ in range(SEGMENT_ATTEMPTS):
        if read_position is not None:
            pos = read_position()
            if pos is not None:
                w.position = pos
        if w.position == target:
            return done(arrived_belief=True)
        path = w6.plan(w, target, blocked)
        if path is None:
            return done(decline="no_plan")
        end = w6.shorten_into_band(w, path, w5.split_segments(w.position, path, seg_max)[0], band)
        if end is None:
            return done(decline="out_of_band")
        step = w6.segment_step(pr, w, end)
        kept = {k: v for k, v in step.items() if k not in ("at", "blocker")}
        events.append({"from": list(w.position), "end": list(end), "seg_max": seg_max,
                       "t": r.ns(), **kept})  # fmt: skip
        log_seg(step.get("t_click", r.ns()), w.position, end, step)
        if step["clicked"]:
            n = max(abs(end[0] - w.position[0]), abs(end[1] - w.position[1]))
            w.position = end  # dead reckoning
            streak, streak_from = 0, None
            time.sleep(n * w5.STEP_S + w5.ARRIVE_S)
            continue
        if step["blocker"] is None:  # the parked frame never went fresh: probe the run again
            continue
        blocker = tuple(step["blocker"])
        shapes = [x["shape"] for x in step["line"] + step["target"]]
        if any(s not in (WALK, "noentry") for s in shapes):
            seg_max = w6.SEG_CROWDED
        # (c) evidence that the BELIEF is wrong -> re-localise
        if step["outcome"] == "unconfirmed":
            streak = streak + 1 if streak_from == w.position else 1
            streak_from = w.position
        noentry = "noentry" in shapes or step["outcome"] == "neighbour"
        if (noentry and w.walkable[blocker[1], blocker[0]]) or streak >= UNCONFIRMED_STREAK:
            if relocs >= RELOCS:
                return done(decline="relocalise_limit")
            rl = relocalise(pr.agent, pr.screen, w, noentry_mask, band)
            relocs += 1
            events.append({"relocalise": rl, "why": "unconfirmed" if streak >= 2 else "noentry",
                           "t": r.ns()})  # fmt: skip
            streak, streak_from = 0, None
            if not rl["ok"]:
                return done(decline="relocalise_failed")
            continue
        # (a) patience for what moves; static shapes and occluded targets are routed around
        moves = (step["outcome"] != "unconfirmed" and not noentry
                 and not any(s in STATIC_SHAPES for s in shapes))  # fmt: skip
        if moves:
            now = clock()
            since = now - first_refused.setdefault(blocker, now)
            if since < PATIENCE_S and waited < WAIT_BUDGET_S:
                time.sleep(PATIENCE_POLL_S)
                waited += clock() - now
                continue
        # (b) a blocked goal -> the nearest free cell around it
        if blocker == target:
            tried.add(target)
            blocked.add(target)
            if len(tried) > SUBSTITUTES:
                return done(decline="goal_occupied")
            sub = substitute_goal(w, goal, blocked, tried)
            if sub is None:
                return done(decline="goal_occupied")
            substitute, target = sub, sub
            events.append({"substitute": list(sub), "for": list(goal), "because": shapes,
                           "t": r.ns()})  # fmt: skip
            continue
        if replans >= REPLANS:
            return done(decline=f"segment_{step['outcome']}")
        blocked.add(blocker)
        replans += 1
    return done(decline="segment_limit")


def run(scene: str, condition: str, n: int, seed: int, label: str, crowd: int) -> int:
    import random

    import bench

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod
    from poring_env import selfpos

    refs = w6.CursorRefs.load()
    noentry_mask = np.load(w5.NOENTRY_MASK)
    mapname, sx0, sy0 = rr.SCENES[scene]
    gat = gatmod.parse((cam.GAT_DIR / f"{mapname}.gat").read_bytes())
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    base = cam.camera_from_json(cj["camera"])
    indoor = scene == "indoor"
    camera = (cam.camera_for_map(base, True, cj["indoor"]["yaw_deg"], cj["indoor"]["distance"])
              if indoor else base)  # fmt: skip
    w = w5.World(camera, gat, (sx0, sy0))
    templates = None if indoor else selfpos.load_digit_templates()
    band = rr.ec_band()
    seg_start = w6.SEG_INDOOR if indoor else w6.SEG_OPEN
    rng = random.Random(seed)
    sid = new_session_id(f"{label}-{condition}-{scene}")
    log = DemoLog(sid)
    lock = record_session.read_lock(r.ROOT / "state")
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena", rule=WALK7_RULE,
              n=n, scene=scene, condition=condition, crowd=crowd if condition == "crowd" else 0,
              seed=seed, account="gm", patience_s=PATIENCE_S,
              wait_budget_s=WAIT_BUDGET_S)  # fmt: skip
    print(json.dumps({"session": sid, "rule": WALK7_RULE, "scene": scene, "condition": condition}),
          flush=True)  # fmt: skip
    t_first = r.ns()
    with r.session(f"rule:{WALK7_RULE}") as (agent, screen):
        pr = w6.Prober(agent, screen, refs)
        r.gm(agent, screen, f"@warp {mapname} {sx0} {sy0}")  # the harness enters the scene once
        time.sleep(rr.SCENE_ENTRY_S)
        bench.close_chat(agent, screen)

        def read_position() -> tuple[int, int] | None:
            if indoor:
                return None
            xy = selfpos.read_minimap_xy(screen.grab(*r.game_region())[1][:, :, :3], templates)
            return None if xy is None else (int(xy[0]), int(xy[1]))

        for i in range(n):
            gm_cmd = False
            if condition == "clean":  # the CLEAN room: no monster before any route
                r.gm(agent, screen, "@killmonster2")
                gm_cmd = True
            if i % rr.DR_WARP_EVERY == 0:  # the HARNESS: a seeded warp, the rule's known start
                if condition == "crowd":
                    r.gm(agent, screen, "@killmonster2")
                for _ in range(200):
                    sx, sy = sx0 + rng.randint(-8, 8), sy0 + rng.randint(-8, 8)
                    if w.walkable[sy, sx]:
                        break
                r.gm(agent, screen, f"@warp {mapname} {sx} {sy}")
                time.sleep(rr.WARP_SETTLE_S)
                if condition == "crowd":  # the SEEDED crowd: a fixed number around us
                    r.gm(agent, screen, f"@monster poring {crowd}")
                    time.sleep(1.0)
                w.position = (sx, sy)
                gm_cmd = True
            if gm_cmd:
                bench.close_chat(agent, screen)
            r.activate_client(agent, screen)
            if not indoor:
                pos = read_position()
                if pos is not None:
                    w.position = pos
            goal = None  # the HARNESS: a seeded goal 8-20 A* steps from the BELIEVED position
            for _ in range(400):
                g = (w.position[0] + rng.randint(-12, 12), w.position[1] + rng.randint(-12, 12))
                if not (0 <= g[1] < w.walkable.shape[0] and 0 <= g[0] < w.walkable.shape[1]):
                    continue
                if not w.walkable[g[1], g[0]]:
                    continue
                path = w6.plan(w, g, set())
                if path is not None and 8 <= len(path) <= 20:
                    goal = g
                    break
            start, t_route = w.position, r.ns()
            pre = rr.snap(log, screen, f"{i:03d}-route-before")

            def log_seg(t_click: int, frm: tuple[int, int], end: tuple[int, int],
                        step: dict[str, Any], i: int = i) -> None:  # fmt: skip
                if not step["clicked"]:
                    return  # a refused probe is route evidence, not a walk attempt
                log.append(DemoRecord(
                    session=sid, actor=f"rule:{WALK7_RULE}", t_mono_ns=t_click, t_done_ns=r.ns(),
                    rule=f"{WALK7_RULE}/segment", scene=f"{scene}:{mapname}",
                    cue="walk@7 segment: walk@6's gate; the record's time is the CLICK",
                    action=Action(type="walk", points=[step["at"]],
                                  intended=Intended(kind="cell", cell=end, relative=False,
                                                    note=f"route {i} believed {frm[0]},{frm[1]}")),
                    outcome={"status": "pending", "evidence": {  # type: ignore[arg-type]
                        "line": step["line"], "target": step["target"],
                        "believed_position": list(frm)}},
                ))  # fmt: skip

            if goal is None:
                did: dict[str, Any] = {"decline": "no_goal", "events": [], "relocs": 0,
                                       "replans": 0, "substitute": None}  # fmt: skip
            else:
                did = walk_route(pr, w, goal, band, seg_start, log_seg, noentry_mask,
                                 read_position if not indoor else None)  # fmt: skip
            log.append(DemoRecord(
                session=sid, actor=f"rule:{WALK7_RULE}", t_mono_ns=t_route, t_done_ns=r.ns(),
                frame=pre, rule=WALK7_RULE, scene=f"{scene}:{mapname}",
                cue="walk@7 route: walk@6's gate; patience, substitute goal, decisive re-localise",
                action=Action(type="walk", intended=Intended(
                    kind="route", cell=goal or start, relative=False,
                    note=f"route {i} from believed {start[0]},{start[1]}")),
                outcome={"status": "pending", "evidence": {  # type: ignore[arg-type]
                    "start_believed": list(start), "goal": list(goal) if goal else None,
                    "end_believed": list(w.position), **did}},
            ))  # fmt: skip
            refused = [e for e in did["events"] if "clicked" in e and not e["clicked"]]
            print(json.dumps({"route": i, "start": list(start), "goal": goal,
                              "end_believed": list(w.position), "decline": did.get("decline"),
                              "substitute": did.get("substitute"),
                              "segments": sum(1 for e in did["events"] if e.get("clicked")),
                              "refused": [e["outcome"] for e in refused],
                              "relocs": did["relocs"], "replans": did["replans"],
                              "waited_s": did.get("waited_s")}), flush=True)  # fmt: skip
            time.sleep(0.5)
        r.gm(agent, screen, "@killmonster2")
        bench.close_chat(agent, screen)
    events, anchor = record_session.write_packets(log.dir, t_first, r.ns())
    log.finish(packet_events=len(events), packet_anchor=anchor, routes=n)
    print(json.dumps({"session": sid, "packet_events": len(events), "routes": n}), flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--scene", choices=sorted(rr.SCENES), required=True)
    ap.add_argument("--condition", choices=("clean", "crowd"), required=True)
    ap.add_argument("--n", type=int, default=56)
    ap.add_argument("--seed", type=int, default=20261016)
    ap.add_argument("--label", default="walk7-alone")
    ap.add_argument("--crowd", type=int, default=4, help="Porings in the seeded crowd")
    a = ap.parse_args()
    for p in (w6.CURSOR_REFS, w5.NOENTRY_MASK):
        if not p.exists():
            raise SystemExit(f"{p} missing: run the walk@6 cursor calibration (design time)")
    return run(a.scene, a.condition, a.n, a.seed, a.label, a.crowd)


if __name__ == "__main__":
    sys.exit(main())
