#!/usr/bin/env python3
"""Run ONE rule ALONE and log every attempt (docs/demonstrations.md §3, pre-registered).

    rule_run.py login [--n 50] [--label login-alone]
    rule_run.py walk --scene outdoor|indoor [--n 50] [--seed 20261009] [--label walk-alone]
    rule_run.py open_window --scene outdoor|indoor [--n 50] [--seed 20261010]

Batt, 2026-10-07: a rule is adopted only if it passes its bar ALONE.
- No agent reasoning and no manual help: this script runs the rule's code only.
- Every attempt is logged as a DemoRecord, actor rule:<name>@<ver>, outcome PENDING.
- The verdicts come later, offline, from packets (scripts/demo_verify.py SESSION).
- The harness's own actions (closing the client between attempts) are logged as
  actor rule:harness@1. They are never part of the rule.

The demo session is written to /dev/shm/poring-lab-demo/<session>/ with its packet window
(packets.jsonl.gz: the sniffer's events, pseudonymised, record_session.write_packets). It ships to
the NAS with the rest; nothing here is committed.

login@1 = `ro_agent login gm` exactly as it stands: dialogs found by their anchors (the calibrated
signatures at their fixed boxes), elements clicked at their offsets, and the demonstrated 0.8 s
server pick. An attempt starts with no client running and launches it.
- A guard's Stop is recorded as evidence. It never decides the verdict.
- Two consecutive Stops end the run: never retry fast on login (lockout, CLAUDE.md rule 2).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import record_session  # noqa: E402
import ro_agent as r  # noqa: E402

from poring_dataset.shards import encode_png  # noqa: E402
from poring_env.demo import (  # noqa: E402
    Action,
    DemoLog,
    DemoRecord,
    FrameRef,
    Intended,
    new_session_id,
)

LOGIN_RULE = "login@1"
LOGIN_CUE = (
    "login@1: dialogs by anchor (signature at its box), elements at offsets, 0.8 s server pick"
)
BETWEEN_S = 5.0  # the harness's pause between attempts


def snap(log: DemoLog, screen: r.Screen, name: str, after_ns: int | None = None) -> FrameRef:
    """The game region, as a snapshot in the demo session (a frame decoded after ``after_ns``)."""
    region = r.game_region()
    if after_ns is None:
        t, img, frame_id, source = screen.grab_meta(*region)
    else:
        img = r.grab_after(screen, region, after_ns)
        t, frame_id, source = r.ns(), -1, "x11"
    ref = log.snapshot(name, encode_png(img[:, :, :3]))
    return FrameRef(frame_id=frame_id, source=source, t_capture_ns=t, ref=ref)  # type: ignore[arg-type]


def harness_close(log: DemoLog, i: int) -> None:
    """No client running before an attempt: close it (paced Alt+F4) and wait until it is gone."""
    with r.session("rule-harness") as (agent, screen):
        if r.client_absent(screen):
            return
        t0 = r.ns()
        pre = snap(log, screen, f"{i:03d}-harness-close-before")
        r.close_client(agent, screen)
        end = time.monotonic() + 20
        while not r.client_absent(screen) and time.monotonic() < end:
            time.sleep(1)
        gone = r.client_absent(screen)
        log.append(DemoRecord(
            session=log.session, actor="rule:harness@1", t_mono_ns=t0, t_done_ns=r.ns(), frame=pre,
            action=Action(type="logout", keys=["AltLeft+F4"],
                          intended=Intended(kind="window", note="close the client")),
            cue="harness: close the client between login attempts", scene="login",
        ))  # fmt: skip
        if not gone:
            raise SystemExit(f"attempt {i}: the client did not close; the run stops here")


def run_login(n: int, label: str) -> int:
    sid = new_session_id(label)
    log = DemoLog(sid)
    lock = record_session.read_lock(r.ROOT / "state")
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena",
              rule=LOGIN_RULE, n=n, account="gm")  # fmt: skip
    print(json.dumps({"session": sid, "dir": str(log.dir), "rule": LOGIN_RULE, "n": n}), flush=True)
    t_first = r.ns()
    stops = 0
    for i in range(n):
        harness_close(log, i)
        time.sleep(BETWEEN_S)
        t0 = r.ns()
        err = None
        with r.session(f"rule:{LOGIN_RULE}") as (agent, screen):
            pre = snap(log, screen, f"{i:03d}-login-before")
            try:
                r.launch_client(agent, screen)
                r.login(agent, screen, "gm")
            except r.Stop as exc:
                err = str(exc)
            post = snap(log, screen, f"{i:03d}-login-after", after_ns=t0)
        log.append(DemoRecord(
            session=sid, actor=f"rule:{LOGIN_RULE}", t_mono_ns=t0, t_done_ns=r.ns(), frame=pre,
            frame_after=post, rule=LOGIN_RULE, scene="login", cue=LOGIN_CUE,
            action=Action(type="login", intended=Intended(kind="login", note="gm")),
            **({"outcome": {"status": "pending", "evidence": {"rule_stop": err[:180]}}}
               if err else {}),
        ))  # fmt: skip
        print(json.dumps({"attempt": i, "seconds": round((r.ns() - t0) / 1e9, 1),
                          "rule_stop": err}), flush=True)  # fmt: skip
        stops = stops + 1 if err else 0
        if stops >= 2:
            print("two consecutive rule stops: the run ends here (never retry fast on login)",
                  flush=True)  # fmt: skip
            break
    events, anchor = record_session.write_packets(log.dir, t_first, r.ns())
    log.finish(packet_events=len(events), packet_anchor=anchor, attempts=i + 1)
    print(json.dumps({"session": sid, "packet_events": len(events), "attempts": i + 1}), flush=True)
    return 0


WALK_RULE = "walk@3"  # docs/demonstrations.md 3.5 (walk@1 and walk@2: §Results, failed)
SCENES = {"outdoor": ("prt_fild08", 268, 107), "indoor": ("prt_church", 104, 122)}  # GM spots
SPOT_RADIUS = 8
WARP_SETTLE_S = 2.5  # a warp WITHIN the scene's map (probe 2026-10-07: the minimap read 18/18)
SCENE_ENTRY_S = 7.0  # the first warp ONTO the map: its minimap is not drawn after 2.5 s (walk@2 #0)
# The hover (walk@3). The client draws the walk marker only on a SECOND motion event at the spot:
# one jump to the cell drew it 0/18 times, a second 1-px move 18/18 (probe, 2026-10-07; walk@1 and
# walk@2 hovered with one jump). So the rule approaches from 3 px off, then moves onto the cell,
# exactly as walk_marker_calibrate.py did for its 30/30. Mirrored in L2 cue.walk_marker.hover.
HOVER_APPROACH_PX = 3
HOVER_APPROACH_S = 0.05
HOVER_S = 0.4
SYSTEMATIC_K = 10  # the same decline 10 times in a row stops the run (pre-registered, 3.5)


def walk_projector(scene: str) -> tuple[object, bool]:
    """(projector, outdoor): the RDP camera; GAT altitude outdoors, a FLAT floor indoors (the
    pre-registered simplification: no minimap indoors, so no origin to take altitude from)."""
    from poring_dataset import camera as cam

    camera_json = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/"
                              "camera_rdp.json").read_text())  # fmt: skip
    table = cam.load_indoor_table(cam.GAT_DIR)
    mapname = SCENES[scene][0]
    if scene == "outdoor":
        proj, which = cam.projector_for(camera_json, mapname, indoor_table=table)
    else:
        proj, which = cam.projector_for(camera_json, mapname, gat_dir=Path("/nonexistent-flat"),
                                        indoor_table=table)  # fmt: skip
    print(json.dumps({"projector": which}), flush=True)
    return proj, scene == "outdoor"


def hover_marker(agent: r.Agent, screen: r.Screen, x: int, y: int) -> int:
    """Hover the screen pixel (x, y) with TWO motion events (3 px off, then onto it) and count the
    walk marker's pixels (empty_cell.marker_px_v2) in the hover crop."""
    import empty_cell as ec

    agent.move(x - HOVER_APPROACH_PX, y - HOVER_APPROACH_PX)
    time.sleep(HOVER_APPROACH_S)
    agent.move(x, y)
    time.sleep(HOVER_S)
    return ec.marker_px_v2(screen.grab(*ec.crop_region(x, y))[1])


def systematic_decline(declines: list[str | None], k: int = SYSTEMATIC_K) -> str | None:
    """The decline cause when the last ``k`` attempts all declined with it, else None."""
    tail = declines[-k:]
    if len(tail) == k and tail[0] is not None and all(d == tail[0] for d in tail):
        return tail[0]
    return None


def walk_rule(agent: r.Agent, screen: r.Screen, proj: object, outdoor: bool,
              offset: tuple[int, int], templates: object) -> dict[str, object]:  # fmt: skip
    """walk@3, ALONE: our cell from the minimap (outdoors), the offset's pixel, the hover marker
    (two motion events), the click. Returns what it did (points / decline) -- never a verdict."""
    import empty_cell as ec

    from poring_dataset.camera import click_for_cell
    from poring_env import selfpos

    gx, gy, _, _ = r.game_region()
    origin = (0, 0)
    if outdoor:
        frame = screen.grab(*r.game_region())[1][:, :, :3]
        xy = selfpos.read_minimap_xy(frame, templates)  # type: ignore[arg-type]
        if xy is None:
            return {"decline": "no_selfpos"}
        origin = xy
    u, v = click_for_cell(proj, offset, origin)  # type: ignore[arg-type]
    marker = hover_marker(agent, screen, gx + round(u), gy + round(v))
    if marker < ec.MIN_MARKER_PX_V2:
        return {"decline": "no_marker", "points": [(u, v)], "marker_px": marker, "origin": origin}
    agent.click(gx + round(u), gy + round(v))
    return {"points": [(u, v)], "marker_px": marker, "origin": origin}


def run_walk(scene: str, n: int, seed: int, label: str) -> int:
    import random

    import bench
    import empty_cell as ec

    from poring_dataset import gat as gatmod
    from poring_dataset.camera import GAT_DIR
    from poring_env import selfpos

    mapname, sx0, sy0 = SCENES[scene]
    walkable = gatmod.parse((GAT_DIR / f"{mapname}.gat").read_bytes()).walkable()
    proj, outdoor = walk_projector(scene)
    harness_proj = walk_projector("outdoor")[0] if outdoor else proj  # the harness's band check
    templates = selfpos.load_digit_templates() if outdoor else None
    rng = random.Random(seed)
    sid = new_session_id(f"{label}-{scene}")
    log = DemoLog(sid)
    lock = record_session.read_lock(r.ROOT / "state")
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena", rule=WALK_RULE,
              n=n, scene=scene, seed=seed, account="gm")  # fmt: skip
    print(json.dumps({"session": sid, "dir": str(log.dir), "rule": WALK_RULE, "scene": scene}),
          flush=True)  # fmt: skip
    t_first = r.ns()
    declines: list[str | None] = []
    with r.session(f"rule:{WALK_RULE}") as (agent, screen):
        # the HARNESS enters the scene once: the first warp onto its map needs the map loaded
        r.gm(agent, screen, f"@warp {mapname} {sx0} {sy0}")
        time.sleep(SCENE_ENTRY_S)
        bench.close_chat(agent, screen)
        i = 0
        while i < n:
            if i % 10 == 0:
                r.gm(agent, screen, "@killmonster2")
                bench.close_chat(agent, screen)
            # the HARNESS: a seeded walkable spot near the scene's GM spot, then a seeded target
            r8 = SPOT_RADIUS
            spots = [(sx0 + rng.randint(-r8, r8), sy0 + rng.randint(-r8, r8)) for _ in range(200)]
            sx, sy = next(((x, y) for x, y in spots if walkable[y, x]), (sx0, sy0))
            pick = ec.pick_cell(rng, (sx, sy), walkable, harness_proj)  # type: ignore[arg-type]
            if pick is None:
                continue
            dx, dy, _, _ = pick
            r.gm(agent, screen, f"@warp {mapname} {sx} {sy}")
            time.sleep(WARP_SETTLE_S)
            # the calibration's UI state. (An open chat does NOT suppress the marker: probe
            # 2026-10-07, 6/6 drawn with it open. walk@1's attribution to it was wrong.)
            bench.close_chat(agent, screen)
            r.activate_client(agent, screen)
            t0 = r.ns()
            pre = snap(log, screen, f"{i:03d}-walk-before")
            did = walk_rule(agent, screen, proj, outdoor, (dx, dy), templates)
            post = snap(log, screen, f"{i:03d}-walk-after", after_ns=t0)
            pts = [tuple(p) for p in did.get("points", [])]  # type: ignore[attr-defined]
            evidence = {k: v for k, v in did.items() if k != "points"}
            log.append(DemoRecord(
                session=sid, actor=f"rule:{WALK_RULE}", t_mono_ns=t0, t_done_ns=r.ns(), frame=pre,
                frame_after=post, rule=WALK_RULE, scene=f"{scene}:{mapname}",
                cue="walk@3: minimap origin (outdoor) or flat floor (indoor) -> click_for_cell -> "
                    "hover 3 px off then on the cell; walk marker green_v2 >= 60 px -> click",
                action=Action(type="walk", points=pts,  # type: ignore[arg-type]
                              intended=Intended(kind="cell", cell=(dx, dy), relative=True,
                                                note=f"harness spot {sx},{sy}")),
                outcome={"status": "pending", "evidence": evidence},  # type: ignore[arg-type]
            ))  # fmt: skip
            print(json.dumps({"attempt": i, "spot": [sx, sy], "offset": [dx, dy], **evidence}),
                  flush=True)  # fmt: skip
            time.sleep(max(abs(dx), abs(dy)) * 0.2 + 1.0)
            i += 1
            declines.append(str(did["decline"]) if "decline" in did else None)
            cause = systematic_decline(declines)
            if cause is not None:
                print(json.dumps({"stop": f"systematic: {SYSTEMATIC_K} x {cause} in a row"}),
                      flush=True)  # fmt: skip
                break
    events, anchor = record_session.write_packets(log.dir, t_first, r.ns())
    log.finish(packet_events=len(events), packet_anchor=anchor, attempts=i)
    print(json.dumps({"session": sid, "packet_events": len(events), "attempts": i}), flush=True)
    return 0


WINDOW_RULE = "open_window@1"  # docs/demonstrations.md 3.6
WINDOW_CLIENT = "kro-20211103-prere"  # the lab client's L2 build
WINDOWS4 = ("status", "skills", "inventory", "equipment")  # the windows with cut anchors
AFTER_S = 1.0  # the menu verifier's window (§2): the after-frame is decoded 1 s after the chord
CLOSE_SETTLE_S = 0.6


def window_keys(window: str) -> list[str]:
    """The window's chord from the L2 binding (never a literal here)."""
    from poring_skills.resolve import load_l2

    return list(load_l2(WINDOW_CLIENT)["shortcut"]["window"][window]["keys"])


def window_order(n: int, seed: int) -> list[str]:
    """A seeded shuffle of the four windows, repeated: 12 or 13 attempts each for n = 50."""
    import random

    rng = random.Random(seed)
    out: list[str] = []
    while len(out) < n:
        block = list(WINDOWS4)
        rng.shuffle(block)
        out += block
    return out[:n]


def window_rule(agent: r.Agent, keys: list[str]) -> dict[str, object]:
    """open_window@1, ALONE: the L2 chord, paced. It never looks at the screen."""
    try:
        agent.chord(*keys)
    except r.Stop as exc:  # a foreground-gate refusal or a guard: a decline (= FAIL)
        return {"rule_decline": f"refused: {str(exc)[:120]}"}
    return {}


def run_window(scene: str, n: int, seed: int, label: str) -> int:
    import bench

    from poring_env import ui_anchors as ua

    reg = ua.default_registry(r.ROOT / "data" / "ui_anchors")
    missing = [w for w in WINDOWS4 if w not in reg.templates]
    if missing:
        raise SystemExit(f"no cut anchor for {missing} (data/ui_anchors): the verifier needs them")
    region = r.game_region()
    mapname, sx, sy = SCENES[scene]
    sid = new_session_id(f"{label}-{scene}")
    log = DemoLog(sid)
    lock = record_session.read_lock(r.ROOT / "state")
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena", rule=WINDOW_RULE,
              n=n, scene=scene, seed=seed, account="gm")  # fmt: skip
    print(json.dumps({"session": sid, "dir": str(log.dir), "rule": WINDOW_RULE, "scene": scene}),
          flush=True)  # fmt: skip
    t_first = r.ns()
    order = window_order(n, seed)

    def open_now(screen: r.Screen) -> set[str]:
        frame = r.grab_after(screen, region, r.ns())[:, :, :3]
        return set(reg.locate(frame)) & set(WINDOWS4)

    def harness_close(agent: r.Agent, screen: r.Screen, which: set[str]) -> None:
        for w in sorted(which):
            t = r.ns()
            agent.chord(*window_keys(w))
            log.append(DemoRecord(
                session=sid, actor="rule:harness@1", t_mono_ns=t, t_done_ns=r.ns(),
                cue="harness: close an open window with its own chord",
                action=Action(type="menu_shortcut", keys=["+".join(window_keys(w))],
                              intended=Intended(kind="window", window=w)),
            ))  # fmt: skip
            time.sleep(CLOSE_SETTLE_S)

    unseen: list[str | None] = []
    with r.session(f"rule:{WINDOW_RULE}") as (agent, screen):
        r.gm(agent, screen, f"@warp {mapname} {sx} {sy}")  # the harness enters the scene once
        time.sleep(SCENE_ENTRY_S)
        bench.close_chat(agent, screen)
        for i, w in enumerate(order):
            r.activate_client(agent, screen)
            harness_close(agent, screen, open_now(screen))
            keys = window_keys(w)
            pre = snap(log, screen, f"{i:03d}-{w}-before", after_ns=r.ns())
            t0 = r.ns()
            did = window_rule(agent, keys)
            t_done = r.ns()
            time.sleep(AFTER_S)
            post = snap(log, screen, f"{i:03d}-{w}-after", after_ns=t_done + int(AFTER_S * 1e9))
            log.append(DemoRecord(
                session=sid, actor=f"rule:{WINDOW_RULE}", t_mono_ns=t0, t_done_ns=t_done,
                frame=pre, frame_after=post, rule=WINDOW_RULE, scene=f"{scene}:{mapname}",
                cue="open_window@1: the window's L2 chord, paced; the screen is not consulted",
                action=Action(type="menu_shortcut", keys=["+".join(keys)],
                              intended=Intended(kind="window", window=w)),
                outcome={"status": "pending", "evidence": did},  # type: ignore[arg-type]
            ))  # fmt: skip
            # the HARNESS (not the rule): what is open now, for its closing and the systematic stop
            now_open = open_now(screen)
            unseen.append(str(did.get("rule_decline", "not_open")) if w not in now_open else None)
            print(json.dumps({"attempt": i, "window": w, "open_after": sorted(now_open), **did}),
                  flush=True)  # fmt: skip
            harness_close(agent, screen, now_open)
            cause = systematic_decline(unseen)
            if cause is not None:
                print(json.dumps({"stop": f"systematic: {SYSTEMATIC_K} x {cause} in a row"}),
                      flush=True)  # fmt: skip
                break
    attempts = len(unseen)
    events, anchor = record_session.write_packets(log.dir, t_first, r.ns())
    log.finish(packet_events=len(events), packet_anchor=anchor, attempts=attempts)
    print(json.dumps({"session": sid, "packet_events": len(events), "attempts": attempts}),
          flush=True)  # fmt: skip
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="rule", required=True)
    lg = sub.add_parser("login")
    lg.add_argument("--n", type=int, default=50)
    lg.add_argument("--label", default="login-alone")
    wk = sub.add_parser("walk")
    wk.add_argument("--scene", choices=sorted(SCENES), required=True)
    wk.add_argument("--n", type=int, default=50)
    wk.add_argument("--seed", type=int, default=20261009)
    wk.add_argument("--label", default="walk-alone")
    ow = sub.add_parser("open_window")
    ow.add_argument("--scene", choices=sorted(SCENES), required=True)
    ow.add_argument("--n", type=int, default=50)
    ow.add_argument("--seed", type=int, default=20261010)
    ow.add_argument("--label", default="window-alone")
    a = ap.parse_args()
    if a.rule == "login":
        return run_login(a.n, a.label)
    if a.rule == "walk":
        return run_walk(a.scene, a.n, a.seed, a.label)
    if a.rule == "open_window":
        return run_window(a.scene, a.n, a.seed, a.label)
    return 2


if __name__ == "__main__":
    sys.exit(main())
