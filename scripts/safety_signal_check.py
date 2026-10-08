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
        time.sleep(rr.SCENE_ENTRY_S)  # may be a warp onto another map
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
        time.sleep(rr.SCENE_ENTRY_S)  # may be a warp onto another map
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
        time.sleep(rr.SCENE_ENTRY_S)  # may be a warp onto another map
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
        # close the inventory pickup-start opened (2026-10-08 21:22: left open, it covered the
        # weight readout and part of the world outside the walk work zone): restore the UI
        r.activate_client(agent, screen)
        agent.chord("AltLeft", "KeyE")
        time.sleep(1.0)
        st["closed_shot"] = _shot(screen, "inventory-closed")
    (NPC_DIR / "pickup-state.json").write_text(json.dumps(st))
    print(json.dumps({"clicked": st["t_click"] is not None, "cell": st.get("cell"),
                      "shot": shot}), flush=True)  # fmt: skip
    return 0 if st["t_click"] is not None else 1


def walk_click() -> int:
    """loot@1 P5's NEGATIVE case: a click that picks nothing up. Pixels only, as every harness
    click: hover cells around us until the cursor reads `walk` (v3) twice, click there; a screenshot
    before and 2 s after, so `chat_cue.py check BEFORE AFTER` can show no "got" line appeared."""
    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    refs = w6.CursorRefs.load(CURSOR_REFS_V3)
    gat = gatmod.parse((cam.GAT_DIR / "prt_church.gat").read_bytes())
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    camera = cam.camera_for_map(cam.camera_from_json(cj["camera"]), True,
                                cj["indoor"]["yaw_deg"], cj["indoor"]["distance"])  # fmt: skip
    x, y = PICKUP_SPOT
    out: dict[str, Any] = {"clicked": False}
    with r.session("rule:safety-check") as (agent, screen):
        pr = w10.Prober9(agent, screen, refs)
        out["before"] = _shot(screen, "walk-before")
        for dx, dy in [(0, 3), (3, 0), (0, -3), (-3, 0), (2, 2), (-2, -2)]:
            rel = np.array([[dx, dy]], dtype=float)
            u, v = camera.project(rel, gat.relative_altitude((x, y), rel))[0]
            if not pr.park():
                continue
            pr.hover(u, v)
            if pr.read(u, v)["shape"] != "walk" or pr.read(u, v)["shape"] != "walk":
                continue
            gx, gy, _, _ = r.game_region()
            agent.click(gx + round(u), gy + round(v))  # the deliberate NON-pickup click
            out.update(clicked=True, cell=[x + dx, y + dy])
            break
        time.sleep(2.0)
        out["after"] = _shot(screen, "walk-after")
    print(json.dumps(out), flush=True)
    return 0 if out["clicked"] else 1


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
                time.sleep(rr.SCENE_ENTRY_S)  # may be a warp onto another map
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


REC0_CONDITIONS = ("C0", "C1", "C2", "C3", "C4")
REC0_CANCEL_S = 0.4  # the cancel comes this long after the attack click (the attack is under way)
REC0_AFTER_S = 0.3  # one swing already in flight is allowed
REC0_WINDOW_S = 5.0
REC0_SEED = 20261063
REC0_WALK_CELLS = {"C1": 2, "C2": 6}  # the walk-away distances (the plant's reach is 1)
REC0_SIT_KEY = "Insert"  # L2 `sit` (kro-20211103-prere.yaml, demonstrated)
REC0_WING_KEY = "F1"  # hotbar row 1 slot 1: the Fly Wing, placed 2026-10-08 14:24 (verified)


def judge_rec0(trials: list[dict[str, Any]], events: list[dict[str, Any]],
               gm: int = GM_AID) -> dict[str, Any]:  # fmt: skip
    """§3.19's bar from the packets: a trial SUCCEEDS when, after its cancel, the GM's act hits
    (kind normal) in [t_cancel + 0.3 s, t_cancel + 5 s] AND its attack_requests after t_cancel are
    both zero. C0 (no cancel) is the positive control: the attack must continue (>= 2 hits)."""
    per: dict[str, dict[str, Any]] = {c: {"trials": 0, "success": 0, "continued": 0, "hits": []}
                                      for c in REC0_CONDITIONS}  # fmt: skip
    for t in trials:
        if "t_cancel" not in t:
            continue
        tc = int(t["t_cancel"])
        lo, hi = tc + int(REC0_AFTER_S * 1e9), tc + int(REC0_WINDOW_S * 1e9)
        hits = sum(1 for e in events if e.get("type") == "act" and int(e.get("src_gid", -1)) == gm
                   and e.get("kind") == "normal" and lo <= int(e["t_mono_ns"]) <= hi)  # fmt: skip
        reqs = sum(1 for e in events if e.get("type") == "attack_request"
                   and tc <= int(e["t_mono_ns"]) <= hi)  # fmt: skip
        t["hits_after"], t["requests_after"] = hits, reqs
        t["success"] = hits == 0 and reqs == 0
        c = per[t["condition"]]
        c["trials"] += 1
        c["success"] += int(t["success"])
        c["continued"] += int(hits >= 2)
        c["hits"].append(hits)
    control_ok = per["C0"]["trials"] > 0 and per["C0"]["continued"] >= 0.9 * per["C0"]["trials"]
    stops = {c: control_ok and 0 < per[c]["trials"] <= per[c]["success"] / 0.9
             for c in REC0_CONDITIONS[1:]}  # fmt: skip
    return {"per_condition": per, "control_proven": control_ok, "stops_an_attack": stops}


def rec0(n: int, mapname: str, x: int, y: int, seed: int) -> int:
    """rec@0 (docs/demonstrations.md §3.19, pre-registered): what really STOPS an attack on our
    client. Per trial: a fresh Red Plant (static, never fights back), the DELIBERATE attack click on
    it, REC0_CANCEL_S later the condition's cancel, then REC0_WINDOW_S of watching. Conditions in a
    seeded interleaved order; the live packets judge (judge_rec0)."""
    import random

    import bench

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    refs = w6.CursorRefs.load(CURSOR_REFS_V3)
    gat = gatmod.parse((cam.GAT_DIR / f"{mapname}.gat").read_bytes())
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    camera = cam.camera_from_json(cj["camera"])
    order = [c for c in REC0_CONDITIONS for _ in range(n)]
    random.Random(seed).shuffle(order)
    sid = new_session_id("rec0")
    log = DemoLog(sid)
    lock = record_session.read_lock(r.ROOT / "state")
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena", rule="rec@0",
              account="gm", n=n, seed=seed, order=order, map=mapname, spot=[x, y],
              cancel_s=REC0_CANCEL_S)  # fmt: skip
    t_first = r.ns()
    trials: list[dict[str, Any]] = []
    import unit_detector

    det = unit_detector.UnitDetector()
    with r.session("rule:rec0") as (agent, screen):
        pr = w10.Prober9(agent, screen, refs)
        gx, gy, _, _ = r.game_region()
        for k, cond in enumerate(order):
            trial: dict[str, Any] = {"k": k, "condition": cond}
            trials.append(trial)
            r.gm(agent, screen, "@killmonster2")
            r.gm(agent, screen, f"@warp {mapname} {x} {y}")
            time.sleep(rr.SCENE_ENTRY_S)
            r.gm(agent, screen, "@monster 1078 1")
            time.sleep(2.0)
            bench.close_chat(agent, screen)
            r.activate_client(agent, screen)
            frame = screen.grab(*r.game_region())[1]
            pc = camera.project(np.zeros((1, 2)), np.zeros(1))[0]  # our own feet
            mobs = [bx for bx in det.detect(frame) if bx.cls == "monster"]
            if not mobs:
                trial["found"] = False
                continue
            box = min(mobs, key=lambda bx: abs(bx.foot[0] - pc[0]) + abs(bx.foot[1] - pc[1]))
            u, v = (box.x0 + box.x1) / 2, box.y0 + 0.65 * (box.y1 - box.y0)
            trial["found"] = True
            su = sv = None
            if cond in REC0_WALK_CELLS:  # the cancel's walk point, AWAY from the plant
                kc = REC0_WALK_CELLS[cond]
                rel = np.array([[-kc if u > pc[0] else kc, -kc if v < pc[1] else kc]], dtype=float)
                su, sv = camera.project(rel, gat.relative_altitude((x, y), rel))[0]
                if not pr.park():
                    trial["safe_point"] = False
                    continue
                pr.hover(su, sv)
                ok = pr.read(su, sv)["shape"] == "walk" and pr.read(su, sv)["shape"] == "walk"
                trial["safe_point"] = bool(ok)
                if not ok:
                    continue
            agent.move(gx + round(u) - 3, gy + round(v) - 3)
            agent.move(gx + round(u), gy + round(v))
            time.sleep(0.3)
            trial["t_hit"] = r.ns()
            agent.click(gx + round(u), gy + round(v))  # the DELIBERATE attack click
            time.sleep(REC0_CANCEL_S)
            trial["t_cancel"] = r.ns()
            if cond in REC0_WALK_CELLS:
                assert su is not None and sv is not None
                agent.move(gx + round(su) - 3, gy + round(sv) - 3)
                agent.move(gx + round(su), gy + round(sv))
                agent.click(gx + round(su), gy + round(sv))
            elif cond == "C3":
                agent.keys(REC0_SIT_KEY)  # sit
                time.sleep(1.0)
                agent.keys(REC0_SIT_KEY)  # stand
            elif cond == "C4":
                agent.keys(REC0_WING_KEY)  # the Fly Wing
            time.sleep(REC0_WINDOW_S)
        r.gm(agent, screen, "@killmonster2")
        bench.close_chat(agent, screen)
    det.close()
    events, anchor = record_session.write_packets(log.dir, t_first, r.ns())
    verdict = judge_rec0(trials, events)
    skipped = [{"k": t["k"], "condition": t["condition"], "found": t.get("found"),
                "safe_point": t.get("safe_point")}
               for t in trials if "t_cancel" not in t]  # fmt: skip
    out = {"session": sid, **verdict, "skipped": skipped}
    log.finish(packet_events=len(events), packet_anchor=anchor, result=out, trials=trials)
    print(json.dumps(out, indent=1, default=str), flush=True)
    return 0


REC0B_CANCEL_S = 0.8  # 3.22: after the attack click; adjacent, the first hit lands before it
REC0B_SEED, REC0B_TOPUP_SEED = 20261064, 20261065
REC0B_ATTEMPTS, REC0B_TOPUP = 25, 15
REC0B_INCLUDED_MIN = 10
REC0B_SETTLE_S = 1.5  # after the walk to the plant's neighbour


def judge_rec0b(trials: list[dict[str, Any]], events: list[dict[str, Any]],
                gm: int = GM_AID) -> dict[str, Any]:  # fmt: skip
    """§3.22: a trial is INCLUDED only if an attack_request AND the GM's first hit (act, normal)
    both fall between its attack click and its cancel time -- the same rule for every condition,
    C0 included. Then 3.19's success and continued measures, on included trials only."""

    def n(pred: Any, lo: int, hi: int) -> int:
        return sum(1 for e in events if lo <= int(e["t_mono_ns"]) <= hi and pred(e))

    def is_req(e: dict[str, Any]) -> bool:
        return e.get("type") == "attack_request"

    def is_hit(e: dict[str, Any]) -> bool:
        return (
            e.get("type") == "act" and int(e.get("src_gid", -1)) == gm and e.get("kind") == "normal"
        )

    per: dict[str, dict[str, Any]] = {c: {"attempts": 0, "included": 0, "success": 0,
                                          "continued": 0, "hits": []}
                                      for c in REC0_CONDITIONS}  # fmt: skip
    for t in trials:
        c = per[t["condition"]]
        c["attempts"] += 1
        if "t_cancel" not in t:
            t["included"] = False
            continue
        th, tc = int(t["t_hit"]), int(t["t_cancel"])
        t["included"] = n(is_req, th, tc) > 0 and n(is_hit, th, tc) > 0
        if not t["included"]:
            continue
        lo, hi = tc + int(REC0_AFTER_S * 1e9), tc + int(REC0_WINDOW_S * 1e9)
        hits, reqs = n(is_hit, lo, hi), n(is_req, tc + 1, hi)
        t["hits_after"], t["requests_after"] = hits, reqs
        t["success"] = hits == 0 and reqs == 0
        c["included"] += 1
        c["success"] += int(t["success"])
        c["continued"] += int(hits >= 2)
        c["hits"].append(hits)
    c0 = per["C0"]
    control_ok = c0["included"] >= REC0B_INCLUDED_MIN and c0["continued"] >= 0.9 * c0["included"]
    stops = {c: control_ok and per[c]["included"] >= REC0B_INCLUDED_MIN
             and per[c]["success"] >= 0.9 * per[c]["included"]
             for c in REC0_CONDITIONS[1:]}  # fmt: skip
    short = [c for c in REC0_CONDITIONS if per[c]["included"] < REC0B_INCLUDED_MIN]
    return {"per_condition": per, "control_proven": control_ok, "stops_an_attack": stops,
            "not_enough_engaged": short}  # fmt: skip


def rec0b(attempts: int, conditions: tuple[str, ...], mapname: str, x: int, y: int,
          seed: int) -> int:  # fmt: skip
    """rec@0b (docs/demonstrations.md §3.22, pre-registered): rec@0 with the attack starting AT
    ONCE. The GM walks to the plant's neighbouring cell first (the plant's cell from pixels: the
    detector's foot point + the picking model), then attacks the re-detected box centre; the cancel
    comes REC0B_CANCEL_S later. Inclusion and outcome are judged offline (judge_rec0b)."""
    import random

    import bench
    import cursor_gate

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod
    from poring_dataset import picking

    refs = w6.CursorRefs.load(CURSOR_REFS_V3)
    gat = gatmod.parse((cam.GAT_DIR / f"{mapname}.gat").read_bytes())
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    camera = cam.camera_from_json(cj["camera"])
    order = [c for c in conditions for _ in range(attempts)]
    random.Random(seed).shuffle(order)
    sid = new_session_id("rec0b")
    log = DemoLog(sid)
    lock = record_session.read_lock(r.ROOT / "state")
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena", rule="rec@0b",
              account="gm", attempts=attempts, conditions=list(conditions), seed=seed,
              order=order, map=mapname, spot=[x, y], cancel_s=REC0B_CANCEL_S)  # fmt: skip
    t_first = r.ns()
    trials: list[dict[str, Any]] = []
    import unit_detector

    det = unit_detector.UnitDetector()
    feet = camera.project(np.zeros((1, 2)), np.zeros(1))[0]

    def nearest_plant(frame: Any) -> Any:
        mobs = [bx for bx in det.detect(frame) if bx.cls == "monster"]
        return min(mobs, key=lambda b: abs(b.foot[0] - feet[0]) + abs(b.foot[1] - feet[1]),
                   default=None)  # fmt: skip

    with r.session("rule:rec0b") as (agent, screen):
        pr = w10.Prober9(agent, screen, refs)
        gx, gy, _, _ = r.game_region()
        for k, cond in enumerate(order):
            trial: dict[str, Any] = {"k": k, "condition": cond}
            trials.append(trial)
            r.gm(agent, screen, "@killmonster2")
            r.gm(agent, screen, f"@warp {mapname} {x} {y}")
            time.sleep(rr.SCENE_ENTRY_S)
            r.gm(agent, screen, "@monster 1078 1")
            time.sleep(2.0)
            bench.close_chat(agent, screen)
            r.activate_client(agent, screen)
            box = nearest_plant(screen.grab(*r.game_region())[1])
            if box is None:
                time.sleep(0.5)
                box = nearest_plant(screen.grab(*r.game_region())[1])
            if box is None:
                trial["found"] = False
                continue
            trial["found"] = True
            off = picking.pick_cells(
                camera, gat, (x, y), np.array([[box.foot[0], box.foot[1] - 4]])
            )[0]
            dx, dy = int(off[0]), int(off[1])
            if abs(dx) > 1000:  # nothing picked under the plant's feet
                trial["plant_cell"] = None
                continue
            trial["plant_rel"] = [dx, dy]
            here = (x, y)
            if max(abs(dx), abs(dy)) > 1:  # walk to the plant's neighbour on our side first
                a = (dx - int(np.sign(dx)), dy - int(np.sign(dy)))
                pts = picking.safe_points(camera, gat, (x, y), a, margin=6.0)
                if not pts:
                    trial["adjacent_walk"] = "no_point"
                    continue
                walked = cursor_gate.gated_click(pr, *pts[0])
                trial["adjacent_walk"] = walked.get("why")
                if not walked.get("clicked"):
                    continue
                time.sleep(REC0B_SETTLE_S)
                here = (x + a[0], y + a[1])
                dx, dy = dx - a[0], dy - a[1]
            trial["here"] = list(here)
            box = nearest_plant(screen.grab(*r.game_region())[1])
            if box is None:
                trial["refound"] = False
                continue
            u, v = (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2  # the box CENTRE
            su = sv = None
            if cond in REC0_WALK_CELLS:  # the cancel's walk point, AWAY from the plant
                kc = REC0_WALK_CELLS[cond]
                away = (-int(np.sign(dx)) * kc or kc, -int(np.sign(dy)) * kc or kc)
                pts = picking.safe_points(camera, gat, here, away, margin=6.0)
                if not pts or not pr.park():
                    trial["safe_point"] = False
                    continue
                su, sv = pts[0]
                pr.hover(su, sv)
                ok = pr.read(su, sv)["shape"] == "walk" and pr.read(su, sv)["shape"] == "walk"
                trial["safe_point"] = bool(ok)
                if not ok:
                    continue
            agent.move(gx + round(u) - 3, gy + round(v) - 3)
            agent.move(gx + round(u), gy + round(v))
            time.sleep(0.3)
            trial["t_hit"] = r.ns()
            agent.click(gx + round(u), gy + round(v))  # the DELIBERATE attack click
            time.sleep(REC0B_CANCEL_S)
            trial["t_cancel"] = r.ns()
            if cond in REC0_WALK_CELLS:
                assert su is not None and sv is not None
                agent.move(gx + round(su) - 3, gy + round(sv) - 3)
                agent.move(gx + round(su), gy + round(sv))
                agent.click(gx + round(su), gy + round(sv))
            elif cond == "C3":
                agent.keys(REC0_SIT_KEY)
                time.sleep(1.0)
                agent.keys(REC0_SIT_KEY)
            elif cond == "C4":
                agent.keys(REC0_WING_KEY)
            time.sleep(REC0_WINDOW_S)
        r.gm(agent, screen, "@killmonster2")
        bench.close_chat(agent, screen)
    det.close()
    events, anchor = record_session.write_packets(log.dir, t_first, r.ns())
    out = {"session": sid, **judge_rec0b(trials, events)}
    log.finish(packet_events=len(events), packet_anchor=anchor, result=out, trials=trials)
    print(json.dumps(out, indent=1, default=str), flush=True)
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
    a7 = sub.add_parser("rec0")
    a7.add_argument("--n", type=int, default=10)
    a7.add_argument("--map", default="prt_fild08")
    a7.add_argument("--x", type=int, default=268)
    a7.add_argument("--y", type=int, default=107)
    a7.add_argument("--seed", type=int, default=REC0_SEED)
    a8 = sub.add_parser("rec0b")
    a8.add_argument("--attempts", type=int, default=REC0B_ATTEMPTS)
    a8.add_argument(
        "--conditions",
        default=",".join(REC0_CONDITIONS),
        help="a top-up names its conditions (3.22: once, 15 attempts, seed 20261065)",
    )
    a8.add_argument("--map", default="prt_fild08")
    a8.add_argument("--x", type=int, default=268)
    a8.add_argument("--y", type=int, default=107)
    a8.add_argument("--seed", type=int, default=REC0B_SEED)
    sub.add_parser("pickup-start")
    sub.add_parser("pickup-click")
    sub.add_parser("pickup-collect")
    sub.add_parser("walk-click")
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
    if a.cmd == "rec0b":
        conds = tuple(c for c in a.conditions.split(",") if c in REC0_CONDITIONS)
        return rec0b(a.attempts, conds, a.map, a.x, a.y, a.seed)
    if a.cmd == "rec0":
        return rec0(a.n, a.map, a.x, a.y, a.seed)
    if a.cmd == "cancel-test":
        return cancel_test([int(x) for x in a.delays_ms.split(",")], a.n, a.map, a.x, a.y)
    if a.cmd == "pickup-start":
        return pickup_start()
    if a.cmd == "pickup-click":
        return pickup_click()
    if a.cmd == "pickup-collect":
        return pickup_collect()
    if a.cmd == "walk-click":
        return walk_click()
    if a.cmd == "monster-click":
        return monster_click(a.map, a.x, a.y)
    return 2


if __name__ == "__main__":
    sys.exit(main())
