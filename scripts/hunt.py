#!/usr/bin/env python3
"""hunt@N (Batt 2026-10-15 overnight): SEARCH and ENGAGE like a player on prt_fild08, natural
spawns, the GM immune. Engagement success >= 95 % is the bar (docs/demonstrations.md 3.39).

    hunt.py run --version N [--minutes 35] [--seed S]    LIVE (RDP, the GM, ASSIST)
    hunt.py judge SESSION                                 OFFLINE: the 3.39 numbers from the packets

THE LOOP
- SEARCH (scripts/hunt_core.py): a coverage plan over the search area (stand cells: client GAT AND
  the server's map cache, outside warp spans and touch areas; 6 cells clear of warps and NPCs; a
  20-cell border), goals by staleness per 16 x 16 tile plus the sightings memory (stationary targets
  kept), A* routes, a waypoint every 8 cells.
  - The FIRST click of a route, from a standstill, is cursor-gated (robust2's WALK series).
  - Every LATER click goes out BEFORE the character stops (<= 3 cells left by dead reckoning at the
    map's speed), gated by the map and the detector instead of the cursor (Batt's continuous
    walking; design section 6, option B): the cell in the search area, the point clear of the UI,
    no detector unit box within 40 px on a frame <= 0.35 s old. A refused gate waits for the stop.
  - The minimap corrects the reckoning (two reads > 3 cells off: stop, settle, re-plan).
  - Detection runs all the time (the frame bus, ~3-4 Hz): a target in view INTERRUPTS the route.
- ENGAGE: the selected target is tracked frame by frame (farm@1's Focus). The hover waits for a
  still target (0.5 s), or after 8 s takes the latest fresh box. ONE robust2 SWORD read -> click
  at once on the latest box's centre. While it lives, it is re-clicked the same way every
  RECLICK_S, bounded by ENGAGE_MAX_S and MAX_CLICKS, then dropped with its reason. Death from
  pixels (loot@1's rule, 1.5 s). Then loot@1's PICKUP scan.
- Stops (none retried): any UI state but clear (the gate's pixel check every 30 s and at each
  engagement), HP < 75 %, Batt's takeover, the mux leaving ASSIST, an unknown own cell.
Packets are never read here (rule 1): `judge` reads them afterwards.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import farm0 as f0  # noqa: E402
import farm1 as f1  # noqa: E402
import hunt_core as hc  # noqa: E402
import ro_agent as r  # noqa: E402

RULE = "hunt"
MAP = "prt_fild08"
START = (268, 107)
OUT = Path("/dev/shm/poring-lab-tmp/hunt")
REC_HZ = 5.0
CHECK_EVERY_S = 30.0
FRESH_S = 0.35
UNIT_CLEAR_PX = 40.0
MINIMAP_EVERY_S = 0.3
DRIFT_CELLS = 3
RECLICK_S = 5.0
ENGAGE_MAX_S = 60.0
MAX_CLICKS = 10
MOVING_AFTER_S = 8.0
LOST_S = 3.0
REACQ_PX = 140.0
WIDE_PX = 200.0
RETRY_S = 0.5
DROP_S = 30.0
Cell = tuple[int, int]

# what each version changes (pre-registered in demonstrations.md 3.39.N before its run)
VERSIONS = {1: "search (coverage plan, look while walking, memory, continuous walking) + "
               "persistent engagement (re-click every 5 s, bounded)"}  # fmt: skip


def run(version: int, minutes: float, seed: int) -> int:
    import multiprocessing as mp

    import bench
    import cursor_gate
    import gm_state
    import gm_vitals
    import loot1
    import operator_hud
    import record_session
    import route_demo
    import route_plan
    import rule_run as rr
    import unit_detector
    import walk5 as w5
    import walk15 as w15
    import where_fix as wf
    from anim_region import stand_grid

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod
    from poring_dataset import picking
    from poring_env import selfpos
    from poring_env import weight as wt
    from poring_env.demo import DemoLog, new_session_id

    if version not in VERSIONS:
        raise SystemExit(f"unknown version {version}")
    ok_imm, why_imm = f0.immunity_confirmed()
    if not ok_imm:
        raise f0.FarmStop(f"hunt refused: the GM is not confirmed immune ({why_imm})")
    lock = record_session.read_lock(r.ROOT / "state")
    if str(lock.backend) != "rdp":
        raise f0.FarmStop(f"hunt refused: RDP-only cursor references (lock {lock.backend})")
    gat = gatmod.parse((cam.GAT_DIR / f"{MAP}.gat").read_bytes())
    ok = stand_grid(MAP, gat)
    kb = r.ROOT / "data" / "kb"
    warps = json.loads((kb / "warps.json").read_text()).get(MAP, [])
    npcs = json.loads((kb / "npc_cells.json").read_text())["maps"].get(MAP, {}).get("npcs", [])
    keep = [(w["x"], w["y"], w["span_x"], w["span_y"]) for w in warps]
    keep += [(n["x"], n["y"], 1, 1) for n in npcs]
    area = hc.search_area(ok, keep)
    if not area[START[1], START[0]]:
        raise f0.FarmStop(f"the start cell {START} is outside the search area")
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    camera = cam.camera_from_json(cj["camera"])
    gx0, gy0, gw, gh = r.game_region()

    def in_view(u: float, v: float) -> bool:
        return 0 <= u < gw and 0 <= v < gh and not loot1.in_ui(u, v)

    offsets = hc.footprint(lambda o: camera.project(o, np.zeros(len(o))), in_view)
    ms_cell = 200.0  # walk11.map_ms_per_cell(prt_fild08); the GM's speed
    sid = new_session_id(f"hunt{version}")
    log = DemoLog(sid)
    out = OUT / sid
    (out / "frames").mkdir(parents=True, exist_ok=True)
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena",
              rule=f"{RULE}@{version}", account="gm", map=MAP, minutes=minutes, seed=seed,
              change=VERSIONS[version], area_cells=int(area.sum()), footprint=len(offsets),
              scored=True, immunity=why_imm, rec_dir=str(out))  # fmt: skip
    print(json.dumps({"session": sid, "version": version, "start": time.strftime("%H:%M:%S")}),
          flush=True)  # fmt: skip
    events_f = (log.dir / "events.jsonl").open("a")

    def ev(rec: dict[str, Any]) -> None:
        events_f.write(json.dumps({"t_ns": r.ns(), **rec}, default=str) + "\n")
        events_f.flush()

    split = f0.Split(dict.fromkeys(("searching", "stopping", "engaging", "fighting", "looting",
                                    "checks"), 0.0))  # fmt: skip
    engagements: list[dict[str, Any]] = []
    cov = hc.Coverage(area)
    mem = hc.Memory()
    ended, run_s, t_run0 = "time_box", 0.0, time.monotonic()
    t_first = r.ns()
    ctx = mp.get_context("spawn")
    stop_rec = ctx.Event()
    region = (gx0, gy0, gw, gh)
    rec = ctx.Process(target=route_demo._record, args=(str(out / "frames"), region, stop_rec,
                                                       REC_HZ), daemon=True)  # fmt: skip
    plan_tok = route_plan.enable(f"hunt{version}-{sid}", MAP, log_path=str(out / "live.jsonl"))
    with r.session(f"rule:{RULE}@{version}") as (agent, screen):
        f0.stop_on_takeover(agent)
        hud_tok = operator_hud.enable(f"hunt@{version}", agent=agent,
                                      log_path=str(out / "hud.jsonl"))  # fmt: skip
        det = unit_detector.UnitDetector()
        sampler = None
        rec.start()
        try:
            import walk11 as w11

            w11.UNITS["detector"] = det
            w11.UNITS["ms_per_cell"] = ms_cell
            w11.UNITS["memory"] = w15.NpcClearMemory()
            pr = cursor_gate.prober(agent, screen)  # robust2
            digits = selfpos.load_digit_templates()
            relocalise = w15.where_relocalise(wf.load_templates(wf.TEMPLATES_V2))
            band, noentry = rr.ec_band(), np.load(w5.NOENTRY_MASK)
            world = w5.World(camera, gat, START)
            rig = loot1.Rig(agent, screen, pr, det, camera, gat, gat.walkable(), digits,
                            wt.load_weight_glyphs(r.ROOT / wt.DEFAULT_TEMPLATES),
                            loot1.chat_cue.load_cues(), operator_hud.sender())  # fmt: skip

            def note(line: str, boxes: Any = ()) -> None:
                loot1.hud(rig, line, boxes)

            def frame() -> Any:
                return screen.grab(gx0, gy0, gw, gh)[1]

            def read_position() -> Cell | None:
                xy = selfpos.read_minimap_xy(frame()[:, :, :3], digits)
                return None if xy is None else (int(xy[0]), int(xy[1]))

            def settle(timeout: float = 5.0) -> Cell | None:
                """Our cell once the GM stands: two minimap reads 0.3 s apart agree. Failing
                that, /where ONCE (minimap first, /where only when needed); else stop."""
                end = time.monotonic() + timeout
                while time.monotonic() < end:
                    a = read_position()
                    time.sleep(0.3)
                    b = read_position()
                    if a is not None and a == b and ok[a[1], a[0]]:
                        return a
                world.position = pos_box[0]
                got = relocalise(agent, screen, world, noentry, band)
                bench.close_chat(agent, screen)
                ev({"kind": "where_fix", "ok": bool(got.get("ok")), "to": list(world.position)})
                if got.get("ok"):
                    return tuple(world.position)  # type: ignore[return-value]
                raise f0.FarmStop("our cell is unknown (minimap and /where both failed)")

            last_check = [0.0]

            def check(where: str) -> None:
                prev = split._cat
                split.to("checks", time.monotonic())
                st = f0.client_state(agent, screen)
                last_check[0] = time.monotonic()
                if st["decision"]["do"] != "clear":
                    shot = r.to_png(st["frame"], log.dir / f"stop-{len(engagements)}.png")
                    raise f0.FarmStop(f"client state at {where}: {st['decision']} (frame {shot})")
                hp = gm_vitals.hp_fraction(frame()[..., :3])
                if hp < f0.HP_STOP:
                    raise f0.FarmStop(f"HP {hp:.2f} at {where}: an immune GM lost HP")
                split.to(prev, time.monotonic())

            def cell_of(b: Any, here: Cell) -> tuple[Cell | None, float]:
                fu, fv = f1.foot(b)
                off = picking.pick_cells(camera, gat, here,
                                         np.array([[fu, fv - loot1.FOOT_LIFT]]))[0]  # fmt: skip
                if abs(int(off[0])) > 1000:
                    return None, 1.0
                c = (here[0] + int(off[0]), here[1] + int(off[1]))
                world.position = here
                p = world.project([c, (c[0] + 1, c[1])])
                p0 = world.project([here, (here[0] + 1, here[1])])
                px0 = float(np.hypot(*(p0[1] - p0[0])))
                return c, (float(np.hypot(*(p[1] - p[0]))) / px0 if px0 > 0 else 1.0)

            dropped: list[tuple[float, Cell]] = []

            def rp(cmd: str, *a: Any) -> None:
                """The route preview (display only, never raises)."""
                pub = route_plan.publisher()
                if pub is None:
                    return
                with contextlib.suppress(Exception):
                    if cmd == "route":
                        world.position = a[0]
                        route_plan.preview(agent, world, a[0], a[1], None, f"hunt@{version}")
                    elif cmd == "walk":
                        pub.walk(a[0], a[1], ms_cell, a[2])
                    elif cmd == "snap":
                        pub.snap(a[0])
                    else:
                        pub.clear()

            pos_box: list[Cell] = [START]  # the last believed cell, for /where's search

            def targets_in(boxes: Any, here: Cell, t_mono: float) -> list[tuple[Any, Cell]]:
                out_ = []
                for b in boxes:
                    c, scale = cell_of(b, here)
                    if c is None or not (0 <= c[0] < area.shape[1] and 0 <= c[1] < area.shape[0]):
                        continue
                    if f1.native_size(b, scale) > f1.MAX_NATIVE_PX:
                        continue
                    if loot1.in_ui(*f1.centre(b)):
                        continue
                    if any(t_mono - td < DROP_S and max(abs(dc[0] - c[0]), abs(dc[1] - c[1])) <= 2
                           for td, dc in dropped):  # fmt: skip
                        continue
                    if not area[c[1], c[0]]:  # targets stay inside the search area (warps far)
                        continue
                    out_.append((b, c))
                return out_

            # --- start ------------------------------------------------------------------------
            r.gm(agent, screen, f"@warp {MAP} {START[0]} {START[1]}")
            time.sleep(rr.SCENE_ENTRY_S)
            bench.close_chat(agent, screen)
            r.activate_client(agent, screen)
            before = gm_state.ensure_fixed(agent, screen, why=f"hunt@{version}:before",
                                           out_dir=log.dir / "gm_state")  # fmt: skip
            bench.close_chat(agent, screen)
            ev({"kind": "gm_state_before", **f0._brief(before)})
            sampler = loot1.Sampler(det)
            sampler.start()
            pos = settle() or START
            reck = hc.Reckoner(ms_cell)
            deadline = time.monotonic() + minutes * 60
            t_run0 = time.monotonic()
            ev({"kind": "loop_start"})
            wp: list[Cell] = []
            wi = 0
            moving = False
            bad_tiles: list[Cell] = []
            last_mm, mm_off = 0.0, 0
            k = 0
            split.to("searching", time.monotonic())
            while time.monotonic() < deadline:
                now = time.monotonic()
                if now - last_check[0] > CHECK_EVERY_S:
                    check("searching")
                # position: reckoned while moving, corrected by the minimap
                est = reck.where(now) if moving else pos
                if est is not None:
                    pos = est
                if now - last_mm > MINIMAP_EVERY_S:
                    last_mm = now
                    mm = read_position()
                    if mm is not None and ok[mm[1], mm[0]]:
                        if max(abs(mm[0] - pos[0]), abs(mm[1] - pos[1])) <= DRIFT_CELLS:
                            mm_off = 0
                            if not moving:
                                pos = mm
                        else:
                            mm_off += 1
                            if mm_off >= 2:  # the reckoning drifted: stop, settle, re-plan
                                ev({"kind": "drift", "reck": list(pos), "minimap": list(mm)})
                                split.to("stopping", time.monotonic())
                                pos = settle() or mm
                                moving, wp, wi = False, [], 0
                                mm_off = 0
                                split.to("searching", time.monotonic())
                pos_box[0] = pos
                cov.mark(pos, now, offsets)
                # look while walking: a target in view interrupts the route
                fr = sampler.since(max(0, len(sampler.frames) - 1))
                tg: list[tuple[Any, Cell]] = []
                if fr and (r.ns() - fr[-1][0]) / 1e9 <= FRESH_S * 2:
                    t_fr = fr[-1][0]
                    here_fr = (reck.where(now - (r.ns() - t_fr) / 1e9) if moving else pos) or pos
                    tg = targets_in(fr[-1][1], here_fr, now)
                    for _b, c in tg:
                        mem.add(now, c)
                if tg:
                    box, tcell = min(
                        tg, key=lambda bc: max(abs(bc[1][0] - pos[0]), abs(bc[1][1] - pos[1]))
                    )
                    rp("clear")
                    if moving:  # let the current click finish: no click until it stops
                        split.to("stopping", time.monotonic())
                        note(f"target at {tcell[0]},{tcell[1]}: stopping to engage", [box])
                        pos = settle(timeout=4.0) or pos
                        moving, wp, wi = False, [], 0
                    check(f"engagement {k}")
                    eng = engage(k, tcell, pos, version, sampler, pr, rig, world, split, note,
                                 frame, cell_of, settle, ev)  # fmt: skip
                    k += 1
                    engagements.append(eng)
                    if eng["result"] != "dead":
                        dropped.append((time.monotonic(), tcell))
                    mem.forget(tcell)
                    pos = settle() or pos
                    split.to("searching", time.monotonic())
                    continue
                # search: plan, first click from a standstill, then continuous clicks
                if not moving:
                    if wi >= len(wp):
                        goal = hc.choose_goal(cov, pos, now, mem.bonus(now), bad_tiles)
                        path = None if goal is None else hc.astar(area, pos, goal)
                        if path is None:
                            if goal is not None:
                                bad_tiles.append((goal[0] - goal[0] % hc.TILE,
                                                  goal[1] - goal[1] % hc.TILE))  # fmt: skip
                            pos = settle(timeout=2.0) or pos
                            if goal is None or len(bad_tiles) > 40:
                                bad_tiles = []
                            continue
                        wp, wi = hc.waypoints(path), 0
                        rp("route", pos, wp)
                        ev({"kind": "route", "from": list(pos), "goal": list(goal),
                            "cells": len(path)})  # fmt: skip
                        note(f"search: route to {goal[0]},{goal[1]} ({len(path)} cells)")
                    world.position = pos
                    u, v = (float(c) for c in world.project([wp[wi]])[0])
                    if not in_view(u, v):
                        wp, wi = [], 0
                        continue
                    got = cursor_gate.gated_click(pr, u, v, allow=("walk",))
                    ev({"kind": "walk_click", "gate": "cursor", "to": list(wp[wi]),
                        "clicked": got["clicked"], "why": got["why"]})  # fmt: skip
                    if not got["clicked"]:
                        wi += 1  # try the next waypoint from here
                        if wi >= len(wp):
                            wp, wi = [], 0
                        continue
                    seg = hc.astar(ok, pos, wp[wi]) or [pos, wp[wi]]
                    reck.go(seg, time.monotonic())
                    rp("walk", pos, seg, int(got["t_click"]))
                    moving = True
                elif reck.remaining(now) == 0:  # stopped: the next click is cursor-gated again
                    moving = False
                    pos = settle(timeout=3.0) or pos
                    rp("snap", pos)
                    wi += 1
                    if wi >= len(wp):
                        rp("clear")
                        wp, wi = [], 0
                elif reck.remaining(now) <= hc.LEAD_CELLS:
                    if wi + 1 < len(wp):
                        cur = reck.where(now + 0.15) or pos
                        world.position = cur
                        nxt = wp[wi + 1]
                        u, v = (float(c) for c in world.project([nxt])[0])
                        clear = (in_view(u, v) and area[nxt[1], nxt[0]] and fr
                                 and (r.ns() - fr[-1][0]) / 1e9 <= FRESH_S
                                 and all(np.hypot(*(np.array(f1.centre(b)) - (u, v)))
                                         > UNIT_CLEAR_PX for b in fr[-1][1]))  # fmt: skip
                        if clear:
                            t_c = r.ns()
                            agent.click(gx0 + round(u), gy0 + round(v))
                            wi += 1
                            seg = hc.astar(ok, cur, nxt) or [cur, nxt]
                            reck.go(seg, time.monotonic())
                            rp("walk", cur, seg, t_c)
                            ev({"kind": "walk_click", "gate": "map+units", "to": list(nxt),
                                "from": list(cur)})  # fmt: skip
                time.sleep(0.03)
            split.to(None, time.monotonic())
            run_s = time.monotonic() - t_run0
        except BaseException as exc:
            split.to(None, time.monotonic())
            ended = f"stopped:{type(exc).__name__}: {str(exc)[:200]}"
            run_s = time.monotonic() - t_run0
            if not isinstance(exc, (r.Stop, KeyboardInterrupt)):
                raise
        finally:
            stop_rec.set()
            if rec.is_alive():
                rec.join(timeout=5)
            if sampler is not None:
                sampler.stop()
            with contextlib.suppress(Exception):
                det.close()
            route_plan.disable(plan_tok)
            operator_hud.disable(hud_tok)
        after: dict[str, Any] = {"skipped": ended}
        if ended == "time_box":
            with contextlib.suppress(r.Stop):
                after = f0._brief(gm_state.ensure_fixed(agent, screen, why=f"hunt@{version}:after",
                                                        out_dir=log.dir / "gm_state"))  # fmt: skip
                bench.close_chat(agent, screen)
        ev({"kind": "gm_state_after", **after})
    events_f.close()
    events, anchor = record_session.write_packets(log.dir, t_first, r.ns())
    (log.dir / "engagements.json").write_text(json.dumps(engagements, default=str))
    np.save(log.dir / "coverage_seen.npy", cov.seen)
    summary = {"run_s": round(run_s, 1), "engagements": len(engagements),
               "dead_pixels": sum(e["result"] == "dead" for e in engagements),
               "results": dict(Counter(e["result"] for e in engagements)),
               "split": split.ranked(), "coverage_cells": cov.first_seen,
               "stationary_remembered": len(mem.stationary)}  # fmt: skip
    log.finish(ended=ended, packet_events=len(events), packet_anchor=anchor, **summary)
    print(json.dumps({"session": sid, "ended": ended, **summary}, default=str), flush=True)
    return 0 if ended == "time_box" else 3


def engage(k: int, tcell: Cell, here: Cell, version: int, sampler: Any, pr: Any, rig: Any,
           world: Any, split: Any, note: Any, frame: Any, cell_of: Any, settle: Any,
           ev: Any) -> dict[str, Any]:  # fmt: skip
    """ONE engagement, from the selection to the death (pixels) or a bounded give-up.
    The target is followed frame by frame: acquired within REACQ_PX of its projected cell, then
    within FOCUS_PX per frame, widened to WIDE_PX once attacked (the camera scrolls while the client
    walks up and chases). It counts as DEAD only when no box is within WIDE_PX of its last feet for
    3 frames and 1.5 s after an attack click (a hop is not a death)."""
    import loot1

    from poring_dataset import deathcell as dcm

    split.to("engaging", time.monotonic())
    t_sel = r.ns()
    eng: dict[str, Any] = {"k": k, "t_select": t_sel, "target_cell": list(tcell),
                           "here": list(here), "hovers": []}  # fmt: skip
    world.position = here
    u0, v0 = (float(c) for c in world.project([tcell])[0])
    fo = f1.Focus((u0, v0))
    fo.gate = REACQ_PX
    sightings: list[Any] = []
    kf = max(0, len(sampler.frames) - 2)
    t_first: int | None = None
    t_last: int | None = None
    t_try: int | None = None
    clicks = 0
    gx, gy, _, _ = r.game_region()
    result = "timeout"
    while True:
        new = sampler.since(kf)
        kf += len(new)
        for t, boxes in new:
            n0 = len(fo.seen)
            fo.update(t, boxes)
            got = len(fo.seen) > n0
            b = fo.seen[-1][2] if got else None
            sightings.append(dcm.Sighting(t, None if b is None else (b.x0, b.y0, b.x1, b.y1)))
            if got:
                fo.gate = WIDE_PX if t_first is not None else f1.FOCUS_PX
            elif fo.seen and (t - fo.seen[-1][0]) / 1e9 > 1.0:
                fo.gate = WIDE_PX  # unseen 1 s: look wider before calling it lost
        now = r.ns()
        if (
            t_first is not None
            and f1._gone(sightings, now)
            and fo.seen
            and fo.seen[-1][0] > t_first
        ):
            result = "dead"
            break
        if (now - t_sel) / 1e9 > ENGAGE_MAX_S:
            result = "timeout"
            break
        unseen = fo.unseen_s(now)
        if t_first is None and ((not fo.seen and (now - t_sel) / 1e9 > LOST_S)
                                or (unseen is not None and unseen > LOST_S)):  # fmt: skip
            result = "lost"
            break
        if t_first is None:
            due = t_try is None or (now - t_try) / 1e9 > RETRY_S
        else:
            due = (now - (t_last or 0)) / 1e9 > RECLICK_S and (now - (t_try or 0)) / 1e9 > 1.5
        if due and clicks < MAX_CLICKS and fo.seen:
            b = fo.still(now)
            if b is None and (now - fo.seen[-1][0]) / 1e9 <= FRESH_S and (
                    t_first is not None or (now - t_sel) / 1e9 > MOVING_AFTER_S):  # fmt: skip
                b = fo.seen[-1][2]  # a re-click, or a target that will not rest: its latest box
            if b is not None:
                u, v = f1.centre(b)
                t_try = r.ns()
                if not loot1.in_ui(u, v) and pr.park():
                    pr.hover(u, v)
                    shape = pr.read(u, v)["shape"]
                    age = round((r.ns() - fo.seen[-1][0]) / 1e6)
                    hov: dict[str, Any] = {"t": r.ns(), "at": [round(u, 1), round(v, 1)],
                                           "read": shape, "age_ms": age}  # fmt: skip
                    eng["hovers"].append(hov)
                    if shape == "sword":
                        tc = r.ns()
                        rig.agent.click(gx + round(u), gy + round(v))
                        hov["clicked"] = tc
                        clicks += 1
                        t_first = t_first or tc
                        t_last = tc
                        fo.gate = WIDE_PX
                        pr.park()
                        split.to("fighting", time.monotonic())
                        note(f"SWORD -> attack click {clicks}", [b])
                    else:
                        note(f"read {shape}: no click")
                        if t_first is None:
                            fo.seen = fo.seen[-1:]  # stillness is measured afresh
        time.sleep(0.03)
    eng.update(result=result, clicks=clicks, t_end=r.ns(), t_first_click=t_first)
    if result == "dead":
        split.to("looting", time.monotonic())
        here2 = settle() or here
        track = loot1.Track(fo.last)
        track.sightings = sightings
        dead = loot1.death_of(rig, track, here2)
        eng["death"] = {"cell": None if dead.cell is None else list(dead.cell),
                        "reason": dead.reason}  # fmt: skip
        if dead.cell is not None and dead.gone_ns is not None:
            loot1.loot(rig, here2, dead, eng)
        eng["t_loot_end"] = r.ns()
    ev({"kind": "engagement", **{k_: eng.get(k_) for k_ in ("k", "result", "clicks",
                                                             "target_cell")}})  # fmt: skip
    print(json.dumps({k_: eng.get(k_) for k_ in ("k", "result", "clicks", "target_cell")}),
          flush=True)  # fmt: skip
    return eng


def judge(sid: str) -> dict[str, Any]:
    """The 3.39 numbers from the packets (definitions fixed in 3.39 before any data)."""
    import gzip

    import replay_safety

    from poring_env.demo import DEMO_ROOT

    d = DEMO_ROOT / sid
    man = json.loads((d / "manifest.json").read_text())
    evs = [json.loads(x) for x in (d / "events.jsonl").read_text().splitlines() if x]
    engs = json.loads((d / "engagements.json").read_text())
    with gzip.open(d / "packets.jsonl.gz", "rt") as fh:
        pk = [json.loads(x) for x in fh]
    t0 = next((e["t_ns"] for e in evs if e.get("kind") == "loop_start"), man["t0_mono_ns"])
    t1 = next((e["t_ns"] for e in evs if e.get("kind") == "gm_state_after"),
              max(int(e.get("t_mono_ns", 0)) for e in pk))  # fmt: skip
    win = [e for e in pk if t0 <= int(e.get("t_mono_ns", 0)) <= t1]
    rows = []
    for e in engs:
        j = hc.judge_engagement({**e, "t_end": e.get("t_loot_end") or e["t_end"]}, win)
        rows.append({"k": e["k"], "bot": e["result"], "clicks": e.get("clicks"), **j})
    counted = [x for x in rows if not x["excluded"]]
    ok_n = sum(x["success"] for x in counted)
    lo, hi = hc.wilson(ok_n, len(counted))
    run_s = float(man.get("run_s") or 0)
    k = f0.kills_from_packets(win)
    stats = [e for e in win if e.get("type") == "stat_change"]
    first_sel = min((e["t_select"] for e in engs), default=None)
    kill_times = [x["t_death"] for x in counted if x["success"]]
    walk_clicks = [e for e in evs if e.get("kind") == "walk_click"]
    # unintended attacks: attack requests not within an engagement window
    wins = [(e["t_select"], e.get("t_loot_end") or e["t_end"]) for e in engs]
    grace = 3 * 10**9
    unintended = [e for e in win if e.get("type") == "attack_request"
                  and not any(a <= int(e["t_mono_ns"]) <= b + grace for a, b in wins)]  # fmt: skip
    path_cells = sum(e.get("cells", 0) for e in evs if e.get("kind") == "route")
    return {
        "session": sid, "version": man.get("rule"), "ended": man.get("ended"), "run_s": run_s,
        "engagements": len(rows), "excluded": len(rows) - len(counted),
        "success": ok_n, "success_rate": round(ok_n / len(counted), 4) if counted else None,
        "wilson95": [round(lo, 4), round(hi, 4)],
        "why": dict(Counter(x["why"] for x in rows)),
        "kills_packets": k, "kills_per_hour": f0.per_hour(k["kills"], run_s),
        "time_to_first_target_s": None if first_sel is None else round((first_sel - t0) / 1e9, 1),
        "targets_per_10min": round(len(rows) / (run_s / 600), 2) if run_s else None,
        "seconds_per_kill": round(run_s / k["kills"], 1) if k["kills"] else None,
        "planned_path_cells_per_kill": round(path_cells / k["kills"], 1) if k["kills"] else None,
        "coverage_cells": man.get("coverage_cells"),
        "exp": {"base": f0.exp_gained(stats, "base", needs=f0.BASE_NEED_PRE_RE),
                "job": f0.exp_gained(stats, "job", needs=f0.JOB_NEED_NOVICE)},
        "split": man.get("split"), "walk_clicks": Counter(e.get("gate") for e in walk_clicks),
        "safety": {**replay_safety.judge(pk, int(t0), int(t1)),
                   "npc_dialog_events": sum(e.get("type") in ("npc_say", "npc_wait", "npc_menu")
                                            for e in win),
                   "map_changes": [(e.get("map"), e.get("x"), e.get("y")) for e in win
                                   if e.get("type") == "map_change"],
                   "non_target_jobs_hit": k["non_target_jobs_hit"],
                   "unintended_attack_requests": len(unintended)},
        "rows": rows,
        "kill_times": kill_times,
    }  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("--version", type=int, required=True)
    p.add_argument("--minutes", type=float, default=35.0)
    p.add_argument("--seed", type=int, required=True)
    q = sub.add_parser("judge")
    q.add_argument("session")
    a = ap.parse_args()
    if a.cmd == "run":
        return run(a.version, a.minutes, a.seed)
    out = judge(a.session)
    print(json.dumps({k: v for k, v in out.items() if k not in ("rows", "kill_times")},
                     indent=1, default=str))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
