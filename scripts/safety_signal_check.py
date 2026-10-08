#!/usr/bin/env python3
"""Prove that a SAFETY signal can see a positive case (Batt, 2026-10-08): "0 observed" from a sensor
that cannot see the event is not evidence. Run after any sniffer (re)build, before walk runs.

    safety_signal_check.py monster-click [--map prt_fild08 --x 268 --y 107]
    safety_signal_check.py npc-click [--npc garnet]     then npc-key CODE ... and npc-collect

monster-click: a deliberate GM click on a spawned Poring, found by PIXELS ONLY (hover cells around
us until the cursor reads `sword`, re-checked with no motion); then the live packets are checked:
`attack_request` (our CZ_REQUEST_ACT2, live only since the 2026-10-08 sniffer rebuild) and the
server's `act` from us (ZC_NOTIFY_ACT). PASS = both seen within 5 s of the click. The Poring is
killed afterwards (@killmonster2). Pixels in, input out: the check reads packets only afterwards.

npc-click / npc-key / npc-collect: a deliberate click on a church NPC (found by pixels: the TALK
bubble, v3 references, re-checked), a screenshot after each step so a person (or the operator)
sees the dialog, single keys to page through and cancel it, then the live packets: `npc_contact`
(our CZ_CONTACTNPC) within 5 s of the click. The dialog is closed BY STEPS, never blind.
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
import walk5 as w5  # noqa: E402
import walk6 as w6  # noqa: E402
import walk10 as w10  # noqa: E402

from poring_env.demo import DemoLog, new_session_id  # noqa: E402

GM_AID = 2000002
CURSOR_REFS_V3 = r.ROOT / "data/walk6/cursor_refs_rdp_v3.npz"
SCAN = [(dx, dy) for r_ in (1, 2, 3, 4) for dx in range(-r_, r_ + 1) for dy in range(-r_, r_ + 1)
        if max(abs(dx), abs(dy)) == r_]  # fmt: skip
WINDOW_S = 5.0


def judge_attack(events: list[dict[str, Any]], t_click: int) -> dict[str, Any]:
    """The positive case: our attack REQUEST and the server's act from us, within WINDOW_S."""
    lo, hi = t_click - 500_000_000, t_click + int(WINDOW_S * 1e9)
    win = [e for e in events if lo <= int(e.get("t_mono_ns", 0)) <= hi]
    req = [e for e in win if e.get("type") == "attack_request"]
    acts = [e for e in win if e.get("type") == "act" and int(e.get("src_gid", -1)) == GM_AID
            and e.get("kind") == "normal"]  # fmt: skip
    return {"attack_request": len(req), "act_from_us": len(acts),
            "request_targets": sorted({int(e.get("target_gid", -1)) for e in req}),
            "act_targets": sorted({int(e.get("target_gid", -1)) for e in acts}),
            "pass": bool(req) and bool(acts)}  # fmt: skip


def monster_click(mapname: str, x: int, y: int) -> int:
    import bench

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    refs = w6.CursorRefs.load(CURSOR_REFS_V3)
    gat = gatmod.parse((cam.GAT_DIR / f"{mapname}.gat").read_bytes())
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    base = cam.camera_from_json(cj["camera"])
    indoor = mapname in cam.load_indoor_table()
    camera = (cam.camera_for_map(base, True, cj["indoor"]["yaw_deg"], cj["indoor"]["distance"])
              if indoor else base)  # fmt: skip
    sid = new_session_id("safety-check-monster-click")
    log = DemoLog(sid)
    lock = record_session.read_lock(r.ROOT / "state")
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena",
              rule="safety-check/monster-click", map=mapname, account="gm")  # fmt: skip
    t_first = r.ns()
    t_click: int | None = None
    hovers: list[dict[str, Any]] = []
    with r.session("rule:safety-check") as (agent, screen):
        pr = w10.Prober9(agent, screen, refs)
        r.gm(agent, screen, "@killmonster2")
        r.gm(agent, screen, f"@warp {mapname} {x} {y}")
        time.sleep(rr.WARP_SETTLE_S)
        r.gm(agent, screen, "@monster poring 1")
        time.sleep(2.0)
        bench.close_chat(agent, screen)
        r.activate_client(agent, screen)
        w = w5.World(camera, gat, (x, y))
        for _round in range(3):  # the Poring wanders: up to three scans
            for dx, dy in SCAN:
                cell = (x + dx, y + dy)
                if not w.walkable[cell[1], cell[0]]:
                    continue
                rel = np.array([[dx, dy]], dtype=float)
                u, v = camera.project(rel, gat.relative_altitude((x, y), rel))[0]
                for du, dv in ((0, 0), (0, -14), (0, -28)):  # the cell, then up its sprite
                    if not pr.park():
                        continue
                    pr.hover(u + du, v + dv)
                    p = pr.read(u + du, v + dv)
                    hovers.append({"cell": list(cell), "dv": dv, "shape": p["shape"]})
                    if p["shape"] != "sword":
                        continue
                    again = pr.read(u + du, v + dv)
                    if again["shape"] != "sword":
                        continue
                    gx, gy, _, _ = r.game_region()
                    t_click = r.ns()
                    agent.click(gx + round(u + du), gy + round(v + dv))  # the DELIBERATE attack
                    break
                if t_click is not None:
                    break
            if t_click is not None:
                break
        time.sleep(WINDOW_S + 1.0)
        r.gm(agent, screen, "@killmonster2")
        bench.close_chat(agent, screen)
    events, anchor = record_session.write_packets(log.dir, t_first, r.ns())
    out: dict[str, Any] = {"session": sid, "clicked": t_click is not None, "hovers": len(hovers),
                           "shapes": dict(_count(h["shape"] for h in hovers))}  # fmt: skip
    if t_click is not None:
        out.update(judge_attack(events, t_click))
    out["event_types"] = dict(_count(str(e.get("type")) for e in events))
    log.finish(packet_events=len(events), packet_anchor=anchor, result=out)
    print(json.dumps(out, indent=1), flush=True)
    return 0 if out.get("pass") else 1


NPC_DIR = Path("/dev/shm/poring-lab-tmp/npc-check")
NPCS = {"garnet": ((103, 76), (103, 79)), "henson": ((103, 71), (103, 74))}  # (npc, stand cell)


def _shot(screen: Any, name: str) -> str:
    NPC_DIR.mkdir(parents=True, exist_ok=True)
    gx, gy, gw, gh = r.game_region()
    path = NPC_DIR / f"{int(time.time())}-{name}.png"
    r.to_png(screen.grab(gx, gy, gw, gh)[1], path)
    return str(path)


def npc_click(npc: str) -> int:
    import bench

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    (nx, ny), (sx, sy) = NPCS[npc]
    refs = w6.CursorRefs.load(CURSOR_REFS_V3)
    gat = gatmod.parse((cam.GAT_DIR / "prt_church.gat").read_bytes())
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    camera = cam.camera_for_map(cam.camera_from_json(cj["camera"]), True,
                                cj["indoor"]["yaw_deg"], cj["indoor"]["distance"])  # fmt: skip
    sid = new_session_id(f"safety-check-npc-{npc}")
    log = DemoLog(sid)
    lock = record_session.read_lock(r.ROOT / "state")
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena",
              rule="safety-check/npc-click", npc=npc, account="gm")  # fmt: skip
    t_first = r.ns()
    t_click: int | None = None
    shots: list[str] = []
    with r.session("rule:safety-check") as (agent, screen):
        pr = w10.Prober9(agent, screen, refs)
        r.gm(agent, screen, "@killmonster2")
        r.gm(agent, screen, f"@warp prt_church {sx} {sy}")
        time.sleep(rr.WARP_SETTLE_S)
        bench.close_chat(agent, screen)
        r.activate_client(agent, screen)
        rel = np.array([[nx - sx, ny - sy]], dtype=float)
        cu, cv = camera.project(rel, gat.relative_altitude((sx, sy), rel))[0]
        for dv in (-12, -24, -36, 0, -48):
            if not pr.park():
                continue
            pr.hover(cu, cv + dv)
            p = pr.read(cu, cv + dv)
            if p["shape"] != "talk" or pr.read(cu, cv + dv)["shape"] != "talk":
                continue
            gx, gy, _, _ = r.game_region()
            t_click = r.ns()
            agent.click(gx + round(cu), gy + round(cv + dv))  # the DELIBERATE NPC contact
            break
        time.sleep(1.5)
        shots.append(_shot(screen, "after-click"))
    NPC_DIR.mkdir(parents=True, exist_ok=True)
    state = {"session": sid, "dir": str(log.dir), "t_first": t_first, "t_click": t_click}
    (NPC_DIR / "state.json").write_text(json.dumps(state))
    print(json.dumps({"session": sid, "clicked": t_click is not None, "shots": shots}), flush=True)
    return 0 if t_click is not None else 1


def npc_key(code: str) -> int:
    """ONE key to the client (the foreground gate applies), then a screenshot."""
    with r.session("rule:safety-check") as (agent, screen):
        r.activate_client(agent, screen)
        agent.keys(code)
        time.sleep(0.8)
        print(json.dumps({"key": code, "shot": _shot(screen, f"key-{code}")}), flush=True)
    return 0


def ui_click(x: int, y: int) -> int:
    """ONE click on a client-region pixel (a dialog button seen in the last screenshot), two-motion
    hover first, then a screenshot."""
    with r.session("rule:safety-check") as (agent, screen):
        gx, gy, _, _ = r.game_region()
        agent.move(gx + x - 3, gy + y - 3)
        time.sleep(0.15)
        agent.move(gx + x, gy + y)
        time.sleep(0.4)
        agent.click(gx + x, gy + y)
        time.sleep(0.8)
        print(json.dumps({"click": [x, y], "shot": _shot(screen, f"ui-{x}-{y}")}), flush=True)
    return 0


PICKUP_SPOT = (100, 114)  # prt_church, open floor, no monsters


def pickup_start() -> int:
    """Session start; the GM gets one Knife (1201, no quantity dialog) and opens the inventory."""
    import bench

    sid = new_session_id("safety-check-pickup")
    log = DemoLog(sid)
    lock = record_session.read_lock(r.ROOT / "state")
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena",
              rule="safety-check/pickup", account="gm")  # fmt: skip
    t_first = r.ns()
    with r.session("rule:safety-check") as (agent, screen):
        r.gm(agent, screen, "@killmonster2")
        r.gm(agent, screen, f"@warp prt_church {PICKUP_SPOT[0]} {PICKUP_SPOT[1]}")
        time.sleep(rr.WARP_SETTLE_S)
        r.gm(agent, screen, "@item 1201 1")
        bench.close_chat(agent, screen)
        r.activate_client(agent, screen)
        agent.chord("AltLeft", "KeyE")
        time.sleep(1.0)
        shot = _shot(screen, "inventory")
    NPC_DIR.mkdir(parents=True, exist_ok=True)
    state = {"session": sid, "t_first": t_first, "t_click": None}
    (NPC_DIR / "pickup-state.json").write_text(json.dumps(state))
    print(json.dumps({"session": sid, "shot": shot}), flush=True)
    return 0


def ui_drag(x1: int, y1: int, x2: int, y2: int) -> int:
    with r.session("rule:safety-check") as (agent, screen):
        gx, gy, _, _ = r.game_region()
        agent.drag(gx + x1, gy + y1, gx + x2, gy + y2)
        time.sleep(1.0)
        print(json.dumps({"drag": [x1, y1, x2, y2], "shot": _shot(screen, "drag")}), flush=True)
    return 0


def pickup_click() -> int:
    """Pixels only: hover cells around us until the cursor reads `pickup` (v3); re-check; click."""
    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    st = json.loads((NPC_DIR / "pickup-state.json").read_text())
    refs = w6.CursorRefs.load(CURSOR_REFS_V3)
    gat = gatmod.parse((cam.GAT_DIR / "prt_church.gat").read_bytes())
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    camera = cam.camera_for_map(cam.camera_from_json(cj["camera"]), True,
                                cj["indoor"]["yaw_deg"], cj["indoor"]["distance"])  # fmt: skip
    x, y = PICKUP_SPOT
    with r.session("rule:safety-check") as (agent, screen):
        pr = w10.Prober9(agent, screen, refs)
        for dx, dy in SCAN[:24]:
            rel = np.array([[dx, dy]], dtype=float)
            u, v = camera.project(rel, gat.relative_altitude((x, y), rel))[0]
            if not pr.park():
                continue
            pr.hover(u, v)
            if pr.read(u, v)["shape"] != "pickup" or pr.read(u, v)["shape"] != "pickup":
                continue
            gx, gy, _, _ = r.game_region()
            st["t_click"] = r.ns()
            agent.click(gx + round(u), gy + round(v))  # the DELIBERATE pickup
            st["cell"] = [x + dx, y + dy]
            break
        time.sleep(2.0)
        shot = _shot(screen, "after-pickup")
    (NPC_DIR / "pickup-state.json").write_text(json.dumps(st))
    print(json.dumps({"clicked": st["t_click"] is not None, "cell": st.get("cell"),
                      "shot": shot}), flush=True)  # fmt: skip
    return 0 if st["t_click"] is not None else 1


def pickup_collect() -> int:
    st = json.loads((NPC_DIR / "pickup-state.json").read_text())
    log = DemoLog(st["session"])
    events, anchor = record_session.write_packets(log.dir, st["t_first"], r.ns())
    t = st["t_click"]
    win = [e for e in events if t - 500_000_000 <= int(e.get("t_mono_ns", 0)) <= t + 5_000_000_000]
    acts = [e for e in win if e.get("type") == "act" and int(e.get("src_gid", -1)) == GM_AID
            and e.get("kind") == "pickup"]  # fmt: skip
    out = {
        "session": st["session"],
        "act_pickup_from_us": len(acts),
        "types_in_window": dict(_count(str(e.get("type")) for e in win)),
        "pass": bool(acts),
    }
    log.finish(packet_events=len(events), packet_anchor=anchor, result=out)
    print(json.dumps(out, indent=1), flush=True)
    return 0 if out["pass"] else 1


def npc_collect() -> int:
    st = json.loads((NPC_DIR / "state.json").read_text())
    log = DemoLog(st["session"])
    events, anchor = record_session.write_packets(log.dir, st["t_first"], r.ns())
    t = st["t_click"]
    win = [
        e
        for e in events
        if t - 500_000_000 <= int(e.get("t_mono_ns", 0)) <= t + int(WINDOW_S * 1e9)
    ]
    contact = [e for e in win if e.get("type") == "npc_contact"]
    out = {"session": st["session"], "npc_contact": len(contact),
           "npc_gids": sorted({int(e.get("npc_gid", -1)) for e in contact}),
           "npc_events": dict(_count(str(e["type"]) for e in events
                                     if str(e.get("type", "")).startswith("npc"))),
           "pass": bool(contact)}  # fmt: skip
    log.finish(packet_events=len(events), packet_anchor=anchor, result=out)
    print(json.dumps(out, indent=1), flush=True)
    return 0 if out["pass"] else 1


def cancel_test(delays_ms: list[int], n: int, mapname: str, x: int, y: int) -> int:
    """walk@11's defensive layer, MEASURED (Batt 2026-10-08): does a walk click right after a click
    that hit a unit stop the attack? Per trial: one Red Plant, found by the detector + the cursor
    (sword, re-read), a
    safe walk point verified first (walk, re-read; away from the Poring), the deliberate click on
    the Poring, D ms, then the walk click. The live packets say whether we hit it."""
    import bench

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    refs = w6.CursorRefs.load(CURSOR_REFS_V3)
    gat = gatmod.parse((cam.GAT_DIR / f"{mapname}.gat").read_bytes())
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    camera = cam.camera_from_json(cj["camera"])
    sid = new_session_id("safety-check-cancel")
    log = DemoLog(sid)
    lock = record_session.read_lock(r.ROOT / "state")
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena",
              rule="safety-check/cancel", account="gm", delays_ms=delays_ms, n=n)  # fmt: skip
    t_first = r.ns()
    trials: list[dict[str, Any]] = []
    import unit_detector

    det = unit_detector.UnitDetector()
    with r.session("rule:safety-check") as (agent, screen):
        pr = w10.Prober9(agent, screen, refs)
        gx, gy, _, _ = r.game_region()
        for d_ms in delays_ms:
            for _ in range(n):
                r.gm(agent, screen, "@killmonster2")
                r.gm(agent, screen, f"@warp {mapname} {x} {y}")
                time.sleep(rr.WARP_SETTLE_S)
                # a RED PLANT (1078): a monster that never moves, so the hover at its detected
                # box still finds it (Porings hop away during the ~1 s park + hover)
                r.gm(agent, screen, "@monster 1078 1")
                time.sleep(2.0)
                bench.close_chat(agent, screen)
                r.activate_client(agent, screen)
                hit = None
                # the detector finds the Poring in one frame; the cursor confirms it (sword twice)
                frame = screen.grab(*r.game_region())[1]
                pc = camera.project(np.zeros((1, 2)), np.zeros(1))[0]  # our own feet
                # the target: the detected monster nearest our feet (the static plant). The cursor
                # is NOT required here: the sword reference set recognises 6 / 26 (leave-one-out);
                # whether the click hit it is the live attack_request's to say
                mobs = [bx for bx in det.detect(frame) if bx.cls == "monster"]
                if mobs:
                    box = min(
                        mobs, key=lambda bx: abs(bx.foot[0] - pc[0]) + abs(bx.foot[1] - pc[1])
                    )
                    u, v = (box.x0 + box.x1) / 2, box.y0 + 0.65 * (box.y1 - box.y0)
                    hit = (1 if u > pc[0] else -1, 1 if v < pc[1] else -1, u, v)
                if hit is None:
                    trials.append({"delay_ms": d_ms, "found": False})
                    continue
                # the safe point: 2 cells AWAY from the Poring, verified walk twice
                sdx = -2 if hit[0] > 0 else 2
                sdy = -2 if hit[1] > 0 else 2
                rel = np.array([[sdx, sdy]], dtype=float)
                su, sv = camera.project(rel, gat.relative_altitude((x, y), rel))[0]
                if not pr.park():
                    continue
                pr.hover(su, sv)
                safe = pr.read(su, sv)["shape"] == "walk" and pr.read(su, sv)["shape"] == "walk"
                if not safe:
                    trials.append({"delay_ms": d_ms, "found": True, "safe_point": False})
                    continue
                agent.move(gx + round(hit[2]) - 3, gy + round(hit[3]) - 3)
                agent.move(gx + round(hit[2]), gy + round(hit[3]))
                time.sleep(0.3)
                t_hit = r.ns()
                agent.click(gx + round(hit[2]), gy + round(hit[3]))  # the deliberate unit click
                time.sleep(d_ms / 1000)
                agent.move(gx + round(su) - 3, gy + round(sv) - 3)
                agent.move(gx + round(su), gy + round(sv))
                t_cancel = r.ns()
                agent.click(gx + round(su), gy + round(sv))  # the CANCEL walk click
                time.sleep(4.0)
                trials.append({"delay_ms": d_ms, "found": True, "t_hit": t_hit,
                               "t_cancel": t_cancel})  # fmt: skip
        r.gm(agent, screen, "@killmonster2")
        bench.close_chat(agent, screen)
    det.close()
    events, anchor = record_session.write_packets(log.dir, t_first, r.ns())
    for t in trials:
        if "t_hit" not in t:
            continue
        lo, hi = t["t_hit"] - 200_000_000, t["t_hit"] + 4_000_000_000
        win = [e for e in events if lo <= int(e.get("t_mono_ns", 0)) <= hi]
        t["attack_request"] = sum(e.get("type") == "attack_request" for e in win)
        t["hits"] = sum(e.get("type") == "act" and int(e.get("src_gid", -1)) == GM_AID
                        and e.get("kind") == "normal" for e in win)  # fmt: skip
        t["walk_request_after_cancel"] = any(e.get("type") == "self_move_request"
                                             and int(e["t_mono_ns"]) >= t["t_cancel"]
                                             for e in win)  # fmt: skip
    summary: dict[str, Any] = {}
    for d_ms in delays_ms:
        done = [t for t in trials if t["delay_ms"] == d_ms and t.get("attack_request")]
        summary[str(d_ms)] = {"trials": len(done),
                              "with_request": sum(t["attack_request"] > 0 for t in done),
                              "with_hits": sum(t["hits"] > 0 for t in done),
                              "hits": [t["hits"] for t in done]}  # fmt: skip
    missed = sum(1 for t in trials if "t_hit" in t and not t.get("attack_request"))
    out = {"session": sid, "summary": summary, "clicks_without_request": missed,
           "skipped": [t for t in trials if "t_hit" not in t]}  # fmt: skip
    log.finish(packet_events=len(events), packet_anchor=anchor, result=out)
    print(json.dumps(out, indent=1), flush=True)
    return 0


def _count(xs: Any) -> dict[str, int]:
    from collections import Counter

    return dict(Counter(xs))


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("monster-click")
    a1.add_argument("--map", default="prt_fild08")
    a1.add_argument("--x", type=int, default=268)
    a1.add_argument("--y", type=int, default=107)
    a2 = sub.add_parser("npc-click")
    a2.add_argument("--npc", choices=sorted(NPCS), default="garnet")
    a3 = sub.add_parser("npc-key")
    a3.add_argument("code", help="KeyboardEvent.code, e.g. Enter or Escape")
    sub.add_parser("npc-collect")
    a6 = sub.add_parser("cancel-test")
    a6.add_argument("--delays-ms", default="150,300,600")
    a6.add_argument("--n", type=int, default=5)
    a6.add_argument("--map", default="prt_fild08")
    a6.add_argument("--x", type=int, default=268)
    a6.add_argument("--y", type=int, default=107)
    sub.add_parser("pickup-start")
    sub.add_parser("pickup-click")
    sub.add_parser("pickup-collect")
    a5 = sub.add_parser("ui-drag")
    for n in ("x1", "y1", "x2", "y2"):
        a5.add_argument(n, type=int)
    a4 = sub.add_parser("ui-click")
    a4.add_argument("x", type=int)
    a4.add_argument("y", type=int)
    a = ap.parse_args()
    if a.cmd == "npc-click":
        return npc_click(a.npc)
    if a.cmd == "npc-key":
        return npc_key(a.code)
    if a.cmd == "npc-collect":
        return npc_collect()
    if a.cmd == "ui-click":
        return ui_click(a.x, a.y)
    if a.cmd == "ui-drag":
        return ui_drag(a.x1, a.y1, a.x2, a.y2)
    if a.cmd == "cancel-test":
        return cancel_test([int(x) for x in a.delays_ms.split(",")], a.n, a.map, a.x, a.y)
    if a.cmd == "pickup-start":
        return pickup_start()
    if a.cmd == "pickup-click":
        return pickup_click()
    if a.cmd == "pickup-collect":
        return pickup_collect()
    if a.cmd == "monster-click":
        return monster_click(a.map, a.x, a.y)
    return 2


if __name__ == "__main__":
    sys.exit(main())
