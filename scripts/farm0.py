#!/usr/bin/env python3
"""farm@0 (Batt 2026-10-15): the first END-TO-END PLAYABLE DEMO -- supervised, UNSCORED, not a skill
verification (CLAUDE.md "How we work"; docs/demonstrations.md section 6). Batt watches it live.

    farm0.py run [--minutes 30] [--seed S]      LIVE (RDP, the GM, ASSIST; Batt in Watch only)
    farm0.py report SESSION                     OFFLINE: kills, EXP, time split, stops, safety

THE LOOP, proven pieces only, on prt_fild08 (its spawn table is exactly the target list: Poring 70,
Lunatic 40, Pupa 20, Drops 10; data/kb/spawns.json). The detector has no species classes, so the
target set is "a detector MONSTER on prt_fild08"; players and NPCs are never targets. The report
checks every kill's species from the packets.
  1. FIND: the CPU unit detector (v1) on every frame it can (loot@1's sampler); the target is the
     monster whose cell (our minimap cell + the client's picking) is nearest ours, inside the farm
     box (FARM_BOX, an open field away from every warp).
  2. WALK: farther than NEAR_CELLS -> walk@15's own route loop, unchanged (its reader, unit gate and
     NPC clearance), to a stand cell within APPROACH cells of the target. No target for FIND_S ->
     walk@15 to a seeded cell WANDER cells away. Stand cells = client GAT AND the server's map
     cache, outside every warp span and script-NPC touch area (anim_region.stand_grid: the three
     checks).
  3. ATTACK: the live gate's robust2 reader (cursor_gate, Batt 2026-10-13): a click on the target's
     box only where the cursor reads SWORD on a hover read AND a no-motion re-read; again after
     REATTACK_S while it lives (loot@1's points and timing).
  4. DEATH from pixels: the target unseen GONE_FRAMES frames and GONE_S after an attack (loot@1's
     Track); its cell from poring_dataset.deathcell.
  5. LOOT: loot@1's PICKUP hover-scan of the 3 x 3 around the death cell, read by robust2 twice,
     walk@11's unit gate, one click, its runtime check (weight / chat cue).
  6. Repeat until the time box.

SAFETY: the GM is IMMUNE (@monsterignore, confirmed for THIS login through collect_v2's record;
this script never types the toggle) and in its fixed state before and after (gm_state.ensure_fixed
resets the levels the kills gain). Every typed line passes ro_agent.gm (the UI gate, the typing
guard). Every cycle checks the client from pixels (ui_gate.observe twice + decide, nothing
closed) and the HP bar: any dialog, menu, window or unstable read, or HP below HP_STOP, STOPS the
run for a person. Batt's takeover (a human lease) stops it too: stop_on_takeover makes the agent
raise where ro_agent would wait the lease out. Packets are never read here
(rule 1); `report` judges the session from them afterwards.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import random
import sys
import time
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ro_agent as r  # noqa: E402

RULE = "farm@0"
MAP = "prt_fild08"
TARGETS = {1002: "Poring", 1063: "Lunatic", 1008: "Pupa", 1113: "Drops"}  # = the map's spawn table
START = (268, 107)  # the tuning anchor's open field (loot@1's region)
FARM_BOX = (240, 80, 300, 135)  # x0, y0, x1, y1 (inclusive cells): targets and goals stay inside
NEAR_CELLS = 3  # a target this close (Chebyshev) is attacked from where we stand
APPROACH = 2  # else walk to a stand cell this close to it
WANDER = (8, 12)  # no target for FIND_S: walk this many cells away (seeded direction)
FIND_S = 6.0
REACQUIRE_PX = 140.0  # after the walk, the target is the monster box nearest its projected cell
NO_CLICK_S = 30.0  # target chosen, no SWORD-gated click within this: abandoned ("no_sword")
KILL_S = 45.0  # first attack, no death within this: abandoned ("no_kill")
REATTACK_S = 8.0
HP_STOP = 0.75  # an immune GM never loses HP: below this share of the bar, stop for a person
CYCLE_SLEEP_S = 0.05

Cell = tuple[int, int]
CATEGORIES = ("finding", "walking", "cursor_waits", "fighting", "looting", "checks")


# --- pure parts ---------------------------------------------------------------------------------


def cheb(a: Sequence[int], b: Sequence[int]) -> int:
    return max(abs(int(a[0]) - int(b[0])), abs(int(a[1]) - int(b[1])))


def in_box(c: Sequence[int], box: tuple[int, int, int, int] = FARM_BOX) -> bool:
    return box[0] <= c[0] <= box[2] and box[1] <= c[1] <= box[3]


def choose_target(
    cands: Iterable[tuple[Any, Cell | None]], here: Cell, box: tuple[int, int, int, int] = FARM_BOX
) -> tuple[Any, Cell] | None:
    """The (box, cell) nearest ``here`` (Chebyshev, then Euclid), among monsters with a cell inside
    the farm box. None when there is none."""
    best: tuple[Any, Cell] | None = None
    key: tuple[int, float] | None = None
    for b, c in cands:
        if c is None or not in_box(c, box):
            continue
        k = (cheb(c, here), float(np.hypot(c[0] - here[0], c[1] - here[1])))
        if key is None or k < key:
            best, key = (b, c), k
    return best


def approach_goal(target: Cell, here: Cell, ok: Any, approach: int = APPROACH,
                  box: tuple[int, int, int, int] = FARM_BOX) -> Cell | None:  # fmt: skip
    """A stand cell within ``approach`` of the target (never the target's own cell), nearest us."""
    h, w = np.asarray(ok).shape
    best: Cell | None = None
    key: tuple[int, float] | None = None
    tx, ty = target
    for y in range(ty - approach, ty + approach + 1):
        for x in range(tx - approach, tx + approach + 1):
            if (x, y) == (tx, ty) or not (0 <= x < w and 0 <= y < h) or not ok[y, x]:
                continue
            if not in_box((x, y), box):
                continue
            k = (cheb((x, y), here), float(np.hypot(x - here[0], y - here[1])))
            if key is None or k < key:
                best, key = (x, y), k
    return best


def wander_goal(
    here: Cell,
    ok: Any,
    rng: random.Random,
    span: tuple[int, int] = WANDER,
    box: tuple[int, int, int, int] = FARM_BOX,
    tries: int = 64,
) -> Cell | None:
    """A seeded stand cell ``span`` cells away (Chebyshev), inside the farm box."""
    h, w = np.asarray(ok).shape
    for _ in range(tries):
        d = rng.randint(*span)
        ang = rng.uniform(0, 2 * np.pi)
        x, y = round(here[0] + d * np.cos(ang)), round(here[1] + d * np.sin(ang))
        if 0 <= x < w and 0 <= y < h and ok[y, x] and in_box((x, y), box):
            return (int(x), int(y))
    return None


@dataclass
class Split:
    """Where the time went (the report's time split), in seconds per category."""

    s: dict[str, float] = field(default_factory=lambda: dict.fromkeys(CATEGORIES, 0.0))
    _cat: str | None = None
    _t0: float = 0.0

    def to(self, cat: str | None, now: float) -> None:
        if self._cat is not None:
            self.s[self._cat] += now - self._t0
        self._cat, self._t0 = cat, now

    def ranked(self) -> list[tuple[str, float]]:
        return sorted(((k, round(v, 1)) for k, v in self.s.items()), key=lambda kv: -kv[1])


def per_hour(n: int, seconds: float) -> float | None:
    return None if seconds <= 0 else round(n * 3600.0 / seconds, 1)


# --- live -----------------------------------------------------------------------------------------


class FarmStop(r.Stop):
    """A stop for a person: an unknown dialog / state, an HP drop, a refused precondition."""


def client_state(agent: Any, screen: Any) -> dict[str, Any]:
    """The UI gate's pixel check, NOTHING closed: two observations + decide. Anything but
    "clear" stops the run (Batt: stop on any unknown dialog/state)."""
    import ui_gate as ug

    path = ug._require_ready()
    a, _ = ug.observe(agent, screen, None, 0, park=False, path=path)
    b, frame = ug.observe(agent, screen, r.ns(), 0, park=False, path=path)
    d = ug.decide(a, b)
    return {"decision": d, "frame": frame}


def stop_on_takeover(agent: Any) -> None:
    """Batt: STOP on his takeover. ro_agent's Agent WAITS out a human lease (up to 10 min) and then
    resumes; for this run a lease, or the mux leaving ASSIST, raises instead, before any input."""

    def no_wait(max_wait_s: float = 0.0) -> None:
        agent._drain(0.05)
        lease = agent.status.get("lease_until_ns")
        if agent.status.get("mode") != "ASSIST":
            raise FarmStop(f"mux left ASSIST ({agent.status.get('mode')}): stopped")
        if lease and lease >= r.ns():
            raise FarmStop("Batt took over (a human lease is active): stopped, nothing sent")

    agent.wait_for_human = no_wait


def immunity_confirmed() -> tuple[bool, str]:
    import collect_v2 as cv

    return cv.immunity_ok(cv.read_json(cv.IMMUNE), cv.gm_marker())


def run(minutes: float, seed: int) -> int:
    import bench
    import cursor_gate
    import gm_state
    import gm_vitals
    import loot1
    import operator_hud
    import record_session
    import route_plan
    import rule_run as rr
    import unit_detector
    import walk5 as w5
    import walk6 as w6
    import walk11 as w11
    import walk15 as w15
    import where_fix as wf
    from anim_region import stand_grid

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod
    from poring_dataset import picking
    from poring_env import selfpos
    from poring_env import weight as wt
    from poring_env.demo import DemoLog, new_session_id

    ok_imm, why_imm = immunity_confirmed()
    if not ok_imm:
        raise FarmStop(f"farm@0 refused: the GM is not confirmed immune ({why_imm})")
    lock = record_session.read_lock(r.ROOT / "state")
    if str(lock.backend) != "rdp":
        raise FarmStop(f"farm@0 refused: the cursor references are RDP-only (lock {lock.backend})")
    gat = gatmod.parse((cam.GAT_DIR / f"{MAP}.gat").read_bytes())
    ok = stand_grid(MAP, gat)
    if not ok[START[1], START[0]]:
        raise FarmStop(f"farm@0 refused: the start cell {START} fails the stand checks")
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    camera = cam.camera_from_json(cj["camera"])  # prt_fild08 is outdoor
    rng = random.Random(seed)
    sid = new_session_id("farm0")
    log = DemoLog(sid)
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena", rule=RULE,
              account="gm", map=MAP, minutes=minutes, seed=seed, start=list(START),
              farm_box=list(FARM_BOX), targets=TARGETS, scored=False, immunity=why_imm)  # fmt: skip
    print(json.dumps({"session": sid, "rule": RULE, "start": time.strftime("%H:%M:%S")}),
          flush=True)  # fmt: skip
    t_first = r.ns()
    split = Split()
    cycles: list[dict[str, Any]] = []
    stops: list[dict[str, Any]] = []
    ended = "time_box"
    events_f = (log.dir / "events.jsonl").open("a")

    def ev(rec: dict[str, Any]) -> None:
        events_f.write(json.dumps({"t_ns": r.ns(), **rec}, default=str) + "\n")
        events_f.flush()

    plan_tok = route_plan.enable(f"{RULE}-{sid}", MAP)
    with r.session(f"rule:{RULE}") as (agent, screen):
        stop_on_takeover(agent)
        hud_tok = operator_hud.enable(RULE, agent=agent)
        det = unit_detector.UnitDetector()  # fails closed: no detector, no run
        sampler = None
        try:
            w11.UNITS["detector"] = det
            w11.UNITS["ms_per_cell"] = w11.map_ms_per_cell(MAP)
            w11.UNITS["memory"] = w15.NpcClearMemory()
            pr_walk = w11.Prober9(agent, screen, w6.CursorRefs.load(w11.CURSOR_REFS_V2))
            pr = cursor_gate.prober(agent, screen)  # robust2: SWORD and PICKUP
            digits = selfpos.load_digit_templates()
            where_t = wf.load_templates(wf.TEMPLATES_V2)
            relocalise = w15.where_relocalise(where_t)
            band, noentry = rr.ec_band(), np.load(w5.NOENTRY_MASK)
            world = w5.World(camera, gat, START)
            rig = loot1.Rig(agent, screen, pr, det, camera, gat, gat.walkable(), digits,
                            wt.load_weight_glyphs(r.ROOT / wt.DEFAULT_TEMPLATES),
                            loot1.chat_cue.load_cues(), operator_hud.sender())  # fmt: skip

            def note(line: str, boxes: Sequence[Any] = ()) -> None:
                loot1.hud(rig, line, boxes)

            def frame() -> Any:
                return screen.grab(*r.game_region())[1]

            def read_position() -> Cell | None:
                xy = selfpos.read_minimap_xy(frame()[:, :, :3], digits)
                return None if xy is None else (int(xy[0]), int(xy[1]))

            def here_now() -> Cell | None:
                a, b = read_position(), read_position()
                return a if a is not None and a == b and ok[a[1], a[0]] else None

            def check(where: str) -> None:
                split.to("checks", time.monotonic())
                st = client_state(agent, screen)
                if st["decision"]["do"] != "clear":
                    shot = r.to_png(st["frame"], log.dir / f"stop-{len(stops)}.png")
                    raise FarmStop(f"client state at {where}: {st['decision']} (frame {shot})")
                hp = gm_vitals.hp_fraction(frame()[..., :3])
                if hp < HP_STOP:
                    raise FarmStop(f"HP {hp:.2f} < {HP_STOP} at {where}: an immune GM lost HP")

            def segs(t_click: int, frm: Cell, end: Cell, step: dict[str, Any], **_kw: Any) -> None:
                ev({"t_click": t_click, "from": list(frm), "to": list(end),
                                "kind": "walk_segment"})  # fmt: skip

            def walk_to(goal: Cell, why: str, cyc: dict[str, Any]) -> bool:
                split.to("walking", time.monotonic())
                note(f"walk to {goal[0]},{goal[1]} ({why})")
                pos = here_now()
                fixed = pos is not None
                world.position = pos if pos is not None else world.position
                w11.UNITS["memory"].reset()
                did = w15.walk_route(pr_walk, world, goal, band, w11.SEG_OPEN, segs, noentry,
                                     read_position, relocalise=relocalise,
                                     label=f"{RULE} {why}", expect_goal=w15.WALK,
                                     fixed_at_start=fixed)  # fmt: skip
                cyc.setdefault("walks", []).append({
                    "why": why, "goal": list(goal), "arrived": bool(did.get("arrived_belief")),
                    **{k: did.get(k) for k in ("clicks", "relocs", "replans", "decline",
                                               "waited_s")}})  # fmt: skip
                bench.close_chat(agent, screen)  # a /where fix may have left the chat open
                return bool(did.get("arrived_belief"))

            def cell_of_box(b: Any, here: Cell) -> Cell | None:
                fu, fv = loot1.foot_of(b)
                off = picking.pick_cells(camera, gat, here,
                                         np.array([[fu, fv - loot1.FOOT_LIFT]]))[0]  # fmt: skip
                if abs(int(off[0])) > 1000:
                    return None
                return (here[0] + int(off[0]), here[1] + int(off[1]))

            # --- start: the scene, the fixed state (Batt: before and after) ---------------------
            r.gm(agent, screen, f"@warp {MAP} {START[0]} {START[1]}")
            time.sleep(rr.SCENE_ENTRY_S)
            bench.close_chat(agent, screen)
            r.activate_client(agent, screen)
            before = gm_state.ensure_fixed(agent, screen, why=f"{RULE}:before",
                                           out_dir=log.dir / "gm_state")  # fmt: skip
            ev({"kind": "gm_state_before", **_brief(before)})
            sampler = loot1.Sampler(det)
            sampler.start()
            deadline = time.monotonic() + minutes * 60
            t_run0 = time.monotonic()
            k = 0
            while time.monotonic() < deadline:
                cyc: dict[str, Any] = {"k": k, "t_start": r.ns()}
                cycles.append(cyc)
                k += 1
                check(f"cycle {cyc['k']}")
                here = here_now()
                if here is None:
                    got = relocalise(agent, screen, world, noentry, band)
                    bench.close_chat(agent, screen)
                    here = tuple(world.position) if got.get("ok") else None  # type: ignore[assignment]
                if here is None:
                    raise FarmStop("our cell is unknown (minimap and /where both failed)")
                world.position = here
                # 1. FIND
                split.to("finding", time.monotonic())
                t_find, picked = time.monotonic(), None
                while picked is None and time.monotonic() - t_find < FIND_S:
                    frames = sampler.since(max(0, len(sampler.frames) - 1))
                    if frames:
                        t_f, boxes = frames[-1]
                        picked = choose_target(((b, cell_of_box(b, here)) for b in boxes), here)
                    if picked is None:
                        time.sleep(0.1)
                if picked is None:
                    goal = wander_goal(here, ok, rng)
                    cyc["result"] = "wander"
                    if goal is not None:
                        walk_to(goal, "wander", cyc)
                    continue
                box, tcell = picked
                cyc["target_cell"] = list(tcell)
                note(f"target at {tcell[0]},{tcell[1]} ({cheb(tcell, here)} cells)", [box])
                # 2. WALK
                if cheb(tcell, here) > NEAR_CELLS:
                    goal = approach_goal(tcell, here, ok)
                    if goal is None or not walk_to(goal, "approach", cyc):
                        cyc["result"] = "approach_failed"
                        continue
                    here = here_now() or tuple(world.position)  # type: ignore[assignment]
                    world.position = here
                # re-acquire: the monster box nearest the target's cell as drawn from here
                split.to("finding", time.monotonic())
                u0, v0 = (float(c) for c in world.project([tcell])[0])
                n0 = len(sampler.frames)
                time.sleep(0.4)
                recent = sampler.since(max(0, n0 - 2))
                seen = [(t, loot1.nearest(b, (u0, v0), REACQUIRE_PX)) for t, b in recent]
                seen = [(t, b) for t, b in seen if b is not None]
                if not seen:
                    cyc["result"] = "lost_after_walk"
                    continue
                t_seen, first = seen[-1]
                track = loot1.Track(loot1.foot_of(first))
                track.update(t_seen, [first])
                # 3. ATTACK + 4. DEATH
                fight = _fight(rig, pr, sampler, track, split, note, cyc)
                if fight != "dead":
                    cyc["result"] = fight
                    continue
                split.to("looting", time.monotonic())
                here = here_now() or tuple(world.position)  # type: ignore[assignment]
                world.position = here
                dead = loot1.death_of(rig, track, here)
                cyc["death"] = {"cell": None if dead.cell is None else list(dead.cell),
                                "reason": dead.reason}  # fmt: skip
                cyc["result"] = "kill"
                if dead.cell is not None and dead.gone_ns is not None:
                    loot1.loot(rig, here, dead, cyc)  # 5. LOOT (robust2 PICKUP twice)
                cyc["t_end"] = r.ns()
                print(json.dumps({k_: cyc.get(k_) for k_ in ("k", "result", "target_cell",
                                                              "pickup_click", "runtime")},
                                 default=str), flush=True)  # fmt: skip
            split.to(None, time.monotonic())
            run_s = time.monotonic() - t_run0
        except BaseException as exc:  # a stop is reported, never retried
            split.to(None, time.monotonic())
            ended = f"stopped:{type(exc).__name__}: {str(exc)[:200]}"
            stops.append({"t_ns": r.ns(), "why": ended})
            run_s = time.monotonic() - t_run0 if "t_run0" in locals() else 0.0
            if not isinstance(exc, (r.Stop, KeyboardInterrupt)):
                raise
        finally:
            if sampler is not None:
                sampler.stop()
            with contextlib.suppress(Exception):
                det.close()
            route_plan.disable(plan_tok)
            operator_hud.disable(hud_tok)
        # --- end: the fixed state again (the levels the kills gained are reset) -----------------
        # only after a clean end: after a stop nothing more is typed (an unknown state is a
        # person's, a takeover is Batt's); the reset then waits for a judged screen
        after: dict[str, Any] = {"skipped": ended}
        if ended == "time_box":
            with contextlib.suppress(r.Stop):
                after = _brief(gm_state.ensure_fixed(agent, screen, why=f"{RULE}:after",
                                                     out_dir=log.dir / "gm_state"))  # fmt: skip
                bench.close_chat(agent, screen)  # the restore lines leave the chat input open
        ev({"kind": "gm_state_after", **after})
    events_f.close()
    events, anchor = record_session.write_packets(log.dir, t_first, r.ns())
    kills = sum(c.get("result") == "kill" for c in cycles)
    summary = {"run_s": round(run_s, 1), "cycles": len(cycles), "kills": kills,
               "kills_per_hour": per_hour(kills, run_s), "split": split.ranked(),
               "results": dict(Counter(str(c.get("result")) for c in cycles)),
               "stops": stops}  # fmt: skip
    (log.dir / "cycles.json").write_text(json.dumps(cycles, default=str))
    log.finish(ended=ended, packet_events=len(events), packet_anchor=anchor, **summary)
    print(json.dumps({"session": sid, "ended": ended, **summary}, default=str), flush=True)
    return 0 if ended == "time_box" else 3


def _brief(rec: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in rec.items() if isinstance(v, (str, int, float, bool, type(None)))}


def _fight(rig: Any, pr: Any, sampler: Any, track: Any, split: Split, note: Any,
           cyc: dict[str, Any]) -> str:  # fmt: skip
    """loot@1's kill loop on a FOUND target, with the live gate's robust2 SWORD read twice.
    -> "dead" | "no_sword" | "no_kill" | "lost"."""
    import cursor_gate
    import loot1

    k = len(sampler.frames)
    t_found, t_first, last_attack = r.ns(), None, None
    tries: list[dict[str, Any]] = []
    cyc["attacks"] = tries
    while True:
        new = sampler.since(k)
        k += len(new)
        for t, boxes in new:
            track.update(t, boxes)
        now = r.ns()
        if track.gone(now, t_first):
            note("target gone from the pixels: dead")
            return "dead"
        if t_first is None and track.last_seen_ns is not None \
                and (now - track.last_seen_ns) / 1e9 > 3.0:  # fmt: skip
            return "lost"
        if t_first is not None and (now - t_first) / 1e9 > KILL_S:
            return "no_kill"
        if t_first is None and (now - t_found) / 1e9 > NO_CLICK_S:
            return "no_sword"
        again = last_attack is None or (now - last_attack) / 1e9 > REATTACK_S
        if again and track.still(now) is not None:
            split.to("cursor_waits", time.monotonic())
            box = track.last_box
            hit: dict[str, Any] = {"clicked": False}
            for fx, fy, dv in loot1.ATTACK_POINTS:
                u = box.x0 + fx * (box.x1 - box.x0)
                v = box.y0 + fy * (box.y1 - box.y0) + dv
                if loot1.in_ui(u, v):
                    continue
                hit = cursor_gate.gated_click(pr, u, v, allow=("sword",))
                tries.append({"at": [round(u, 1), round(v, 1)], "clicked": hit["clicked"],
                              "why": hit["why"], "t": r.ns()})  # fmt: skip
                if hit["clicked"]:
                    break
            if hit["clicked"]:
                last_attack = int(hit["t_click"])
                t_first = t_first or last_attack
                note("SWORD read twice -> attack click", [box])
                split.to("fighting", time.monotonic())
            else:
                note(f"no SWORD ({tries[-1]['why'] if tries else 'ui'}): wait")
                split.to("cursor_waits" if t_first is None else "fighting", time.monotonic())
        time.sleep(CYCLE_SLEEP_S)


# --- the offline report (packets judge; nothing here acts) ----------------------------------------

GM_AID = 2000002
# the EXP a level needs, ONLY as the packets showed it (var22, 2026-10-15: Lv 1 needs 9 at the
# fixed-state reset, Lv 2 needs 16 after farm@1's level-up). The server sends a level's need only
# AFTER the level-up, so the first level-up's old need is taken from here. No job level-up seen yet.
BASE_NEED_PRE_RE = {1: 9, 2: 16}
JOB_NEED_NOVICE: dict[int, int] = {}
EXP_VARS = {"base": ("base_exp", "var22"), "job": ("job_exp", "var23")}  # value, next-level need


def exp_gained(stats: Sequence[dict[str, Any]], which: str, start: int | None = 0,
               needs: dict[int, int] | None = None) -> int:  # fmt: skip
    """EXP gained from the stat_change stream (time order): positive deltas, and across a level-up
    (the counter drops to the remainder) the rest of the old level's need plus the remainder.
    ``start``: the counter before the first change (0 = the GM began in its fixed state, Lv 1 with
    no EXP; None = count from the first value seen). ``needs``: level -> the EXP that level needs,
    for a level-up whose need was never sent before it (the server sends the NEW need after)."""
    name, need_name = EXP_VARS[which]
    lvl_name = {"base": "base_level", "job": "job_level"}[which]
    cur: int | None = start
    need: int | None = None
    level: int | None = None
    gained = 0
    for e in stats:
        if e.get("name") == need_name:
            need = int(e["value"])
        elif e.get("name") == lvl_name:
            level = int(e["value"])
        elif e.get("name") == name:
            v = int(e["value"])
            if cur is not None:
                if v >= cur:
                    gained += v - cur
                else:
                    old = need if need is not None else (needs or {}).get((level or 2) - 1)
                    gained += max(0, (old or cur) - cur) + v
            cur = v
    return gained


def kills_from_packets(events: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Every unit the GM hit (act src = the GM) that then died (entity_vanish reason 1), with its
    species from its last entity_appear; and every act from a monster onto the GM."""
    job: dict[int, int] = {}
    hit: set[int] = set()
    hit_job: dict[int, int] = {}  # the species WHEN hit (a Pupa can metamorphose into a Creamy)
    died: list[int] = []
    on_gm = 0
    for e in events:
        t = e.get("type")
        if t == "entity_appear":
            job[int(e["gid"])] = int(e.get("job", -1))
        elif (
            t == "act"
            and int(e.get("src_gid", -1)) == GM_AID
            and e.get("target_gid")
            and e.get("kind") != "pickup"
        ):  # a pickup act's target is the FLOOR ITEM's id
            hit.add(int(e["target_gid"]))
            hit_job.setdefault(int(e["target_gid"]), job.get(int(e["target_gid"]), -1))
        elif t == "act" and int(e.get("target_gid", -1)) == GM_AID:
            on_gm += 1
        elif t == "entity_vanish" and int(e.get("reason", -1)) == 1 and int(e["gid"]) in hit:
            died.append(int(e["gid"]))
    species = Counter(TARGETS.get(hit_job.get(g, -1), f"OTHER:{hit_job.get(g)}") for g in died)
    other_hit = sorted({hit_job.get(g, -1) for g in hit if hit_job.get(g, -1) not in TARGETS})
    changed = sorted({(hit_job[g], job[g]) for g in hit if g in job and job[g] != hit_job[g]})
    return {"kills": len(died), "by_species": dict(species), "units_hit": len(hit),
            "non_target_jobs_hit": other_hit, "acts_onto_gm": on_gm,
            "species_changed_after_hit": changed}  # fmt: skip


def report(sid: str) -> dict[str, Any]:
    import gzip

    import replay_safety

    from poring_env.demo import DEMO_ROOT

    d = DEMO_ROOT / sid
    man = json.loads((d / "manifest.json").read_text())
    evs = [json.loads(x) for x in (d / "events.jsonl").read_text().splitlines() if x]
    t0 = next((e["t_ns"] for e in evs if e.get("kind") == "gm_state_before"), man["t0_mono_ns"])
    t1 = next((e["t_ns"] for e in evs if e.get("kind") == "gm_state_after"), None)
    with gzip.open(d / "packets.jsonl.gz", "rt") as fh:
        pk = [json.loads(x) for x in fh]
    t1 = t1 or max(int(e.get("t_mono_ns", 0)) for e in pk)
    win = [e for e in pk if t0 <= int(e.get("t_mono_ns", 0)) <= t1]
    stats = [e for e in win if e.get("type") == "stat_change"]
    k = kills_from_packets(win)
    run_s = float(man.get("run_s") or 0.0)
    return {
        "session": sid, "ended": man.get("ended"), "run_s": run_s,
        "kills_packets": k, "kills_per_hour": per_hour(k["kills"], run_s),
        "kills_pixels": man.get("kills"), "results": man.get("results"),
        "exp": {"base": exp_gained(stats, "base", needs=BASE_NEED_PRE_RE),
                "job": exp_gained(stats, "job", needs=JOB_NEED_NOVICE),
                "assumes": "the GM began at Lv 1 with 0 EXP (its fixed state)"},
        "split_ranked_s": man.get("split"), "stops": man.get("stops"),
        "safety": {**replay_safety.judge(pk, int(t0), int(t1)),
                   "npc_dialog_events": sum(e.get("type") in ("npc_say", "npc_wait", "npc_menu")
                                            for e in win),
                   "map_changes": [(e.get("map"), e.get("x"), e.get("y")) for e in win
                                   if e.get("type") == "map_change"]},
    }  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("--minutes", type=float, default=30.0)
    p.add_argument("--seed", type=int, default=20261015)
    q = sub.add_parser("report")
    q.add_argument("session")
    a = ap.parse_args()
    if a.cmd == "run":
        return run(a.minutes, a.seed)
    print(json.dumps(report(a.session), indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
