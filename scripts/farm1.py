#!/usr/bin/env python3
"""farm@1 (Batt 2026-10-15 ~20:25): the playable demo again, ENGAGING LIKE A PLAYER -- supervised,
UNSCORED (CLAUDE.md "How we work"; docs/demonstrations.md 6.2). farm@0 walked to where a Poring HAD
been (the detector lags), the Poring hopped away, and the next look found it elsewhere: 15 of 16
engagements ended "stale target".

    farm1.py run [--minutes 30] [--seed S]     LIVE (RDP, the GM, ASSIST; Batt in Watch only)
    farm1.py report SESSION                    OFFLINE (farm0's packet report + farm@1's own lines)

Batt's five points, as built:
  1. NO WALK FIRST: the monster itself is clicked; the client walks to it and attacks.
  2. FRESH + STILL: while engaging, every detector frame (full frame back to back, ~3-4 Hz: the
     model's input is a fixed 1280 x 736, so a crop costs a full frame) is FOCUSED on the target:
     only boxes within FOCUS_PX of its last feet count. The hover waits until the target's feet
     moved < STILL_PX across detections spanning >= STILL_S, on a frame <= FRESH_S old, and aims at
     the box CENTRE of that latest frame.
  3. ONE SWORD READ -> CLICK AT ONCE, robust2 (the live gate). Every click is judged afterwards
     from the packets: an attack request on a monster, or a walk (a misread there only walks).
  4. RE-ACQUIRE: a target that hops (feet jump > HOP_PX between frames) or is unseen LOST_S is
     DROPPED; the next one is found fresh. A stale box is never chased.
  5. After the click, "attack started" from pixels (new bright pixels above the target: the damage
     numbers), the death from pixels (loot@1's Track), then loot@1's PICKUP scan as farm@0.
Safety as farm@0 (the GM immune and fixed, the UI gate's pixel check every cycle, HP, takeover).
NEW: a SIZE GATE. Pupa metamorphoses into Creamy (1018, NOT a target) by an IDLE skill (farm@0 saw
one); the detector has no species. Creamy flies, 51 x 53 native px; the targets are <= 37: a box
larger than MAX_NATIVE_PX after the camera's scale at its cell is skipped.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import random
import sys
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import farm0 as f0  # noqa: E402
import ro_agent as r  # noqa: E402

RULE = "farm@1"
MAP, START, FARM_BOX = f0.MAP, f0.START, f0.FARM_BOX
FOCUS_PX = 90.0  # a frame's box within this of the target's last feet is the target
HOP_PX = 30.0  # feet jumped more than this between two frames: it hopped -> dropped
STILL_PX, STILL_S, FRESH_S = 6.0, 0.5, 0.35
LOST_S = 1.5  # unseen this long while engaging -> dropped
FIGHT_GATE_PX = 160.0  # after the click: the camera scrolls up to ~70 px per detector frame
ENGAGE_S = 20.0  # no attack click within this of choosing it -> dropped ("no_sword")
MAX_HOVERS = 4  # hovers without SWORD on one target -> dropped
MAX_NATIVE_PX = 45.0  # the size gate (Creamy 51 x 53 native; targets <= 37)
START_S = 4.0  # "attack started" looked for this long after a click
REATTACK_S = 8.0  # no damage cue this long and the target still there: engage it again
KILL_S = 45.0
GONE_FRAMES, GONE_S = 3, 1.5  # death: unseen this many frames AND this long (farm@0: 3 / 1.0)
DAMAGE_PX = 25  # new near-white pixels above the box = the damage numbers
CUE_EVERY_S = 0.15
FIND_S = 6.0
Cell = tuple[int, int]
CATEGORIES = ("finding", "focusing", "cursor", "fighting", "looting", "walking", "checks")


# --- pure parts ---------------------------------------------------------------------------------


def foot(b: Any) -> tuple[float, float]:
    return (b.x0 + b.x1) / 2, float(b.y1)


def centre(b: Any) -> tuple[float, float]:
    return (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2


@dataclass
class Focus:
    """The target over the detector's frames (Batt's points 2 and 4)."""

    last: tuple[float, float]
    seen: list[tuple[int, tuple[float, float], Any]] = field(default_factory=list)
    hopped: bool = False
    gate: float = FOCUS_PX  # widened after the click: the camera scrolls while the GM walks up

    def update(self, t_ns: int, boxes: Sequence[Any]) -> None:
        near = [(float(np.hypot(foot(b)[0] - self.last[0], foot(b)[1] - self.last[1])), b)
                for b in boxes]  # fmt: skip
        near = [(d, b) for d, b in near if d <= self.gate]
        if not near:
            return
        d, b = min(near, key=lambda x: x[0])
        if self.seen and d > HOP_PX:
            self.hopped = True
        self.last = foot(b)
        self.seen.append((t_ns, foot(b), b))

    def unseen_s(self, now_ns: int) -> float | None:
        return None if not self.seen else (now_ns - self.seen[-1][0]) / 1e9

    def still(self, now_ns: int) -> Any | None:
        """The latest box when the feet moved < STILL_PX over sightings spanning >= STILL_S and
        the latest is <= FRESH_S old; else None (wait)."""
        if not self.seen or (now_ns - self.seen[-1][0]) / 1e9 > FRESH_S:
            return None
        t_last, f_last, b_last = self.seen[-1]
        span = [s for s in self.seen if (t_last - s[0]) / 1e9 <= STILL_S + FRESH_S]
        if (t_last - span[0][0]) / 1e9 < STILL_S:
            return None
        if any(np.hypot(f[0] - f_last[0], f[1] - f_last[1]) >= STILL_PX for _, f, _ in span):
            return None
        return b_last


def native_size(b: Any, scale: float) -> float:
    return max(b.x1 - b.x0, b.y1 - b.y0) / max(scale, 1e-6)


def damage_cue(before: Any, after: Any, box: Any, thr: int = 200) -> int:
    """New near-white pixels in the band ABOVE the target's box (the damage numbers rise there):
    pixels white in ``after`` and not in ``before``. A cue only: logged, it gates a re-engage."""
    h, w = after.shape[:2]
    x0, x1 = max(0, int(box.x0) - 20), min(w, int(box.x1) + 20)
    y0, y1 = max(0, int(box.y0) - 60), max(0, min(h, int(box.y0) + 8))
    if x1 <= x0 or y1 <= y0:
        return 0
    a = after[y0:y1, x0:x1, :3].min(axis=2) > thr
    b = before[y0:y1, x0:x1, :3].min(axis=2) > thr
    return int((a & ~b).sum())


# --- live -----------------------------------------------------------------------------------------


def run(minutes: float, seed: int) -> int:
    import bench
    import cursor_gate
    import gm_state
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

    ok_imm, why_imm = f0.immunity_confirmed()
    if not ok_imm:
        raise f0.FarmStop(f"farm@1 refused: the GM is not confirmed immune ({why_imm})")
    lock = record_session.read_lock(r.ROOT / "state")
    if str(lock.backend) != "rdp":
        raise f0.FarmStop(f"farm@1 refused: RDP-only cursor references (lock {lock.backend})")
    gat = gatmod.parse((cam.GAT_DIR / f"{MAP}.gat").read_bytes())
    ok = stand_grid(MAP, gat)
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    camera = cam.camera_from_json(cj["camera"])
    rng = random.Random(seed)
    sid = new_session_id("farm1")
    log = DemoLog(sid)
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena", rule=RULE,
              account="gm", map=MAP, minutes=minutes, seed=seed, start=list(START),
              farm_box=list(FARM_BOX), targets=f0.TARGETS, scored=False, immunity=why_imm,
              max_native_px=MAX_NATIVE_PX, still_s=STILL_S, focus_px=FOCUS_PX)  # fmt: skip
    print(json.dumps({"session": sid, "rule": RULE, "start": time.strftime("%H:%M:%S")}),
          flush=True)  # fmt: skip
    events_f = (log.dir / "events.jsonl").open("a")

    def ev(rec: dict[str, Any]) -> None:
        events_f.write(json.dumps({"t_ns": r.ns(), **rec}, default=str) + "\n")
        events_f.flush()

    t_first = r.ns()
    split = f0.Split(dict.fromkeys(CATEGORIES, 0.0))
    engagements: list[dict[str, Any]] = []
    ended, run_s, t_run0 = "time_box", 0.0, time.monotonic()
    plan_tok = route_plan.enable(f"{RULE}-{sid}", MAP)
    with r.session(f"rule:{RULE}") as (agent, screen):
        f0.stop_on_takeover(agent)
        hud_tok = operator_hud.enable(RULE, agent=agent)
        det = unit_detector.UnitDetector()
        sampler = None
        try:
            w11.UNITS["detector"] = det
            w11.UNITS["ms_per_cell"] = w11.map_ms_per_cell(MAP)
            w11.UNITS["memory"] = w15.NpcClearMemory()
            pr_walk = w11.Prober9(agent, screen, w6.CursorRefs.load(w11.CURSOR_REFS_V2))
            pr = cursor_gate.prober(agent, screen)  # robust2
            digits = selfpos.load_digit_templates()
            relocalise = w15.where_relocalise(wf.load_templates(wf.TEMPLATES_V2))
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

            def settle_here(timeout: float = 5.0) -> Cell | None:
                """Our cell once the GM STANDS: two minimap reads 0.3 s apart agree (farm@0's
                stop: a walk's "arrived" came while the GM still moved)."""
                end = time.monotonic() + timeout
                while time.monotonic() < end:
                    a = read_position()
                    time.sleep(0.3)
                    b = read_position()
                    if a is not None and a == b and ok[a[1], a[0]]:
                        return a
                return None

            def check(where: str) -> None:
                split.to("checks", time.monotonic())
                st = f0.client_state(agent, screen)
                if st["decision"]["do"] != "clear":
                    shot = r.to_png(st["frame"], log.dir / f"stop-{len(engagements)}.png")
                    raise f0.FarmStop(f"client state at {where}: {st['decision']} (frame {shot})")
                import gm_vitals

                hp = gm_vitals.hp_fraction(frame()[..., :3])
                if hp < f0.HP_STOP:
                    raise f0.FarmStop(f"HP {hp:.2f} at {where}: an immune GM lost HP")

            def cell_and_scale(b: Any, here: Cell) -> tuple[Cell | None, float]:
                fu, fv = foot(b)
                off = picking.pick_cells(camera, gat, here,
                                         np.array([[fu, fv - loot1.FOOT_LIFT]]))[0]  # fmt: skip
                if abs(int(off[0])) > 1000:
                    return None, 1.0
                cell = (here[0] + int(off[0]), here[1] + int(off[1]))
                p = world.project([cell, (cell[0] + 1, cell[1])])
                p0 = world.project([here, (here[0] + 1, here[1])])
                px = float(np.hypot(*(p[1] - p[0])))
                px0 = float(np.hypot(*(p0[1] - p0[0])))
                return cell, (px / px0 if px0 > 0 else 1.0)

            def segs(t_click: int, frm: Cell, end: Cell, step: dict[str, Any], **_kw: Any) -> None:
                ev({"kind": "walk_segment", "t_click": t_click, "from": list(frm),
                    "to": list(end)})  # fmt: skip

            # --- start ------------------------------------------------------------------------
            r.gm(agent, screen, f"@warp {MAP} {START[0]} {START[1]}")
            time.sleep(rr.SCENE_ENTRY_S)
            bench.close_chat(agent, screen)
            r.activate_client(agent, screen)
            before = gm_state.ensure_fixed(agent, screen, why=f"{RULE}:before",
                                           out_dir=log.dir / "gm_state")  # fmt: skip
            ev({"kind": "gm_state_before", **f0._brief(before)})
            sampler = loot1.Sampler(det)
            sampler.start()
            deadline = time.monotonic() + minutes * 60
            t_run0 = time.monotonic()
            k = 0
            while time.monotonic() < deadline:
                eng: dict[str, Any] = {"k": k, "t_start": r.ns(), "hovers": []}
                engagements.append(eng)
                k += 1
                check(f"engagement {eng['k']}")
                here = settle_here()
                if here is None:
                    got = relocalise(agent, screen, world, noentry, band)
                    bench.close_chat(agent, screen)
                    here = tuple(world.position) if got.get("ok") else None  # type: ignore[assignment]
                    eng["relocalised"] = bool(got.get("ok"))
                if here is None:
                    raise f0.FarmStop("our cell is unknown (minimap and /where both failed)")
                world.position = here
                # FIND: a fresh frame's monsters, size-gated, nearest by cell, in the farm box
                split.to("finding", time.monotonic())
                t_find, picked, skipped = time.monotonic(), None, []
                while picked is None and time.monotonic() - t_find < FIND_S:
                    fr = sampler.since(max(0, len(sampler.frames) - 1))
                    if fr and (r.ns() - fr[-1][0]) / 1e9 <= FRESH_S * 2:
                        cands = []
                        for b in fr[-1][1]:
                            cell, scale = cell_and_scale(b, here)
                            if cell is not None and native_size(b, scale) > MAX_NATIVE_PX:
                                skipped.append(round(native_size(b, scale), 1))
                                continue
                            cands.append((b, cell))
                        picked = f0.choose_target(cands, here)
                    if picked is None:
                        time.sleep(0.05)
                eng["size_skipped"] = skipped
                if picked is None:
                    goal = f0.wander_goal(here, ok, rng)
                    eng["result"] = "wander"
                    if goal is not None:
                        split.to("walking", time.monotonic())
                        note(f"no target: walk to {goal[0]},{goal[1]}")
                        did = w15.walk_route(pr_walk, world, goal, band, w11.SEG_OPEN, segs,
                                             noentry, read_position, relocalise=relocalise,
                                             label=f"{RULE} wander", expect_goal=w15.WALK,
                                             fixed_at_start=True)  # fmt: skip
                        bench.close_chat(agent, screen)
                        eng["wander"] = {"goal": list(goal), "arrived": did.get("arrived_belief")}
                    continue
                box, tcell = picked
                eng.update(target_cell=list(tcell), box_px=[round(box.x1 - box.x0),
                                                            round(box.y1 - box.y0)])  # fmt: skip
                note(f"target at {tcell[0]},{tcell[1]}: focusing", [box])
                eng["result"] = _engage(rig, pr, sampler, box, split, note, eng, frame)
                if eng["result"] != "dead":
                    continue
                # LOOT as farm@0 (loot@1's scan, robust2 PICKUP twice)
                split.to("looting", time.monotonic())
                here2 = settle_here() or here
                world.position = here2
                track = loot1.Track(eng.pop("_last_foot"))
                track.sightings = eng.pop("_sightings")
                dead = loot1.death_of(rig, track, here2)
                eng["death"] = {"cell": None if dead.cell is None else list(dead.cell),
                                "reason": dead.reason}  # fmt: skip
                if dead.cell is not None and dead.gone_ns is not None:
                    loot1.loot(rig, here2, dead, eng)
                eng["t_end"] = r.ns()
                print(json.dumps({k_: eng.get(k_) for k_ in ("k", "result", "target_cell",
                                                              "pickup_click")}, default=str),
                      flush=True)  # fmt: skip
            split.to(None, time.monotonic())
            run_s = time.monotonic() - t_run0
        except BaseException as exc:
            split.to(None, time.monotonic())
            ended = f"stopped:{type(exc).__name__}: {str(exc)[:200]}"
            run_s = time.monotonic() - t_run0
            if not isinstance(exc, (r.Stop, KeyboardInterrupt)):
                raise
        finally:
            if sampler is not None:
                sampler.stop()
            with contextlib.suppress(Exception):
                det.close()
            route_plan.disable(plan_tok)
            operator_hud.disable(hud_tok)
        after: dict[str, Any] = {"skipped": ended}
        if ended == "time_box":
            with contextlib.suppress(r.Stop):
                after = f0._brief(gm_state.ensure_fixed(agent, screen, why=f"{RULE}:after",
                                                        out_dir=log.dir / "gm_state"))  # fmt: skip
                bench.close_chat(agent, screen)  # the restore lines leave the chat input open
        ev({"kind": "gm_state_after", **after})
    events_f.close()
    events, anchor = record_session.write_packets(log.dir, t_first, r.ns())
    for e in engagements:
        e.pop("_last_foot", None)
        e.pop("_sightings", None)
    (log.dir / "cycles.json").write_text(json.dumps(engagements, default=str))
    kills = sum(e.get("result") == "dead" for e in engagements)
    summary = {"run_s": round(run_s, 1), "cycles": len(engagements), "kills": kills,
               "kills_per_hour": f0.per_hour(kills, run_s), "split": split.ranked(),
               "results": dict(Counter(str(e.get("result")) for e in engagements))}  # fmt: skip
    log.finish(ended=ended, packet_events=len(events), packet_anchor=anchor, **summary)
    print(json.dumps({"session": sid, "ended": ended, **summary}, default=str), flush=True)
    return 0 if ended == "time_box" else 3


def _engage(rig: Any, pr: Any, sampler: Any, box: Any, split: f0.Split, note: Any,
            eng: dict[str, Any], frame: Any) -> str:  # fmt: skip
    """Batt's points 1-5 on ONE target. -> "dead" | "hopped" | "lost" | "no_sword" | "no_kill"."""
    import loot1

    from poring_dataset import deathcell as dcm

    t0 = r.ns()
    split.to("focusing", time.monotonic())
    fo = Focus(foot(box))
    sightings: list[Any] = []
    k = len(sampler.frames) - 1
    t_click: int | None = None
    t_attack: int | None = None
    last_click: int | None = None
    pre_frame: Any = None
    last_cue = 0
    while True:
        new = sampler.since(max(0, k))
        k += len(new)
        for t, boxes in new:
            n0 = len(fo.seen)
            fo.update(t, boxes)
            b = fo.seen[-1][2] if len(fo.seen) > n0 else None
            sightings.append(dcm.Sighting(t, None if b is None else (b.x0, b.y0, b.x1, b.y1)))
        now = r.ns()
        eng["_last_foot"], eng["_sightings"] = fo.last, sightings
        if t_click is None:
            if fo.hopped:
                note("it hopped: dropped, re-detect")
                return "hopped"
            unseen = fo.unseen_s(now)
            if unseen is not None and unseen > LOST_S:
                return "lost"
            if (now - t0) / 1e9 > ENGAGE_S or len(eng["hovers"]) >= MAX_HOVERS:
                return "no_sword"
            b = fo.still(now)
            if b is None:
                time.sleep(0.02)
                continue
            split.to("cursor", time.monotonic())
            u, v = centre(b)
            if loot1.in_ui(u, v) or not pr.park():
                split.to("focusing", time.monotonic())
                time.sleep(0.05)
                continue
            pr.hover(u, v)
            shape = pr.read(u, v)["shape"]
            hov = {"t": r.ns(), "at": [round(u, 1), round(v, 1)], "read": shape,
                   "age_ms": round((r.ns() - fo.seen[-1][0]) / 1e6)}  # fmt: skip
            eng["hovers"].append(hov)
            if shape == "sword":  # point 3: ONE robust2 read, click at once
                gx, gy, _, _ = r.game_region()
                t_click = last_click = r.ns()
                rig.agent.click(gx + round(u), gy + round(v))
                hov["clicked"] = t_click
                fo.gate = FIGHT_GATE_PX
                pr.park()  # off the monster: its hover NAME label would fake the damage cue
                pre_frame = frame()
                note("SWORD -> attack click", [b])
                split.to("fighting", time.monotonic())
            else:
                note(f"read {shape}: no click")
                split.to("focusing", time.monotonic())
                fo.seen = fo.seen[-1:]  # stillness is measured afresh after a hover
            continue
        # fighting: the attack started? the death? (the client walks to it and attacks by itself)
        if (t_attack is None and fo.seen and pre_frame is not None
                and (now - last_cue) / 1e9 >= CUE_EVERY_S):  # fmt: skip
            last_cue = now
            cue = f0_damage(pre_frame, frame(), fo.seen[-1][2])
            if cue >= DAMAGE_PX:
                t_attack = now
                eng["attack_started_s"] = round((now - t_click) / 1e9, 2)
                note("damage numbers: the attack started")
        gone = _gone(sightings, now)
        if gone and fo.seen and fo.seen[-1][0] > t_click:
            eng["fight_s"] = round((now - t_click) / 1e9, 1)
            note("target gone from the pixels: dead")
            return "dead"
        if (now - t_click) / 1e9 > KILL_S:
            return "no_kill"
        if (t_attack is None and last_click is not None and (now - last_click) / 1e9 > START_S
                and fo.still(now) is not None) or (
                last_click is not None and (now - last_click) / 1e9 > REATTACK_S
                and fo.still(now) is not None):  # fmt: skip
            b = fo.still(now)
            u, v = centre(b)
            if not loot1.in_ui(u, v) and pr.park():
                pr.hover(u, v)
                shape = pr.read(u, v)["shape"]
                hov = {"t": r.ns(), "at": [round(u, 1), round(v, 1)], "read": shape,
                       "again": True}  # fmt: skip
                eng["hovers"].append(hov)
                if shape == "sword":
                    gx, gy, _, _ = r.game_region()
                    rig.agent.click(gx + round(u), gy + round(v))
                    hov["clicked"] = r.ns()
                    pr.park()
                    pre_frame = frame()
            last_click = r.ns()  # the next re-engage is spaced from this attempt, clicked or not
        time.sleep(0.03)


def f0_damage(before: Any, after: Any, box: Any) -> int:
    return damage_cue(np.asarray(before)[..., :3], np.asarray(after)[..., :3], box)


def _gone(sightings: Sequence[Any], now_ns: int) -> bool:
    tail = 0
    last_seen = None
    for s in reversed(sightings):
        if s.box is not None:
            last_seen = s.t_ns
            break
        tail += 1
    return last_seen is not None and tail >= GONE_FRAMES and (now_ns - last_seen) / 1e9 >= GONE_S


def report(sid: str) -> dict[str, Any]:
    from poring_env.demo import DEMO_ROOT

    base = f0.report(sid)
    cyc = json.loads((DEMO_ROOT / sid / "cycles.json").read_text())
    hovers = [h for e in cyc for h in e.get("hovers", [])]
    base["engagements"] = Counter(str(e.get("result")) for e in cyc)
    base["hover_reads"] = Counter(h["read"] for h in hovers)
    base["clicks"] = sum("clicked" in h for h in hovers)
    base["attack_started_s"] = [e.get("attack_started_s") for e in cyc if e.get("t_end")]
    base["size_skipped"] = [s for e in cyc for s in e.get("size_skipped", [])]
    return base


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("--minutes", type=float, default=30.0)
    p.add_argument("--seed", type=int, default=20261016)
    q = sub.add_parser("report")
    q.add_argument("session")
    a = ap.parse_args()
    if a.cmd == "run":
        return run(a.minutes, a.seed)
    print(json.dumps(report(a.session), indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
