#!/usr/bin/env python3
"""Run ONE rule ALONE and log every attempt (docs/demonstrations.md §3, pre-registered).

    rule_run.py login [--n 50] [--label login-alone]
    rule_run.py walk --scene outdoor|indoor [--n 50] [--seed 20261007] [--label walk-alone]

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


WALK_RULE = "walk@1"
SCENES = {"outdoor": ("prt_fild08", 268, 107), "indoor": ("prt_church", 104, 122)}  # GM spots
SPOT_RADIUS = 8
WARP_SETTLE_S = 2.5
HOVER_S = 0.35  # empty_cell's settle: the client draws the walk marker under a hovered cell


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


def walk_rule(agent: r.Agent, screen: r.Screen, proj: object, outdoor: bool,
              offset: tuple[int, int], templates: object) -> dict[str, object]:  # fmt: skip
    """walk@1, ALONE: our cell from the minimap (outdoors), the offset's pixel, the hover marker,
    the click. Returns what it did (points / decline) -- never a verdict."""
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
    agent.move(gx + round(u), gy + round(v))
    time.sleep(HOVER_S)
    crop = screen.grab(*ec.crop_region(gx + round(u), gy + round(v)))[1]
    marker = ec.marker_px(crop)
    if marker < ec.MIN_MARKER_PX:
        return {"decline": "no_marker", "points": [(u, v)], "marker_px": marker, "origin": origin}
    agent.click(gx + round(u), gy + round(v))
    return {"points": [(u, v)], "marker_px": marker, "origin": origin}


def run_walk(scene: str, n: int, seed: int, label: str) -> int:
    import random

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
    with r.session(f"rule:{WALK_RULE}") as (agent, screen):
        i = 0
        while i < n:
            if i % 10 == 0:
                r.gm(agent, screen, "@killmonster2")
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
            t0 = r.ns()
            pre = snap(log, screen, f"{i:03d}-walk-before")
            did = walk_rule(agent, screen, proj, outdoor, (dx, dy), templates)
            post = snap(log, screen, f"{i:03d}-walk-after", after_ns=t0)
            pts = [tuple(p) for p in did.get("points", [])]  # type: ignore[attr-defined]
            evidence = {k: v for k, v in did.items() if k != "points"}
            log.append(DemoRecord(
                session=sid, actor=f"rule:{WALK_RULE}", t_mono_ns=t0, t_done_ns=r.ns(), frame=pre,
                frame_after=post, rule=WALK_RULE, scene=f"{scene}:{mapname}",
                cue="walk@1: minimap origin (outdoor) or flat floor (indoor) -> click_for_cell -> "
                    "hover walk marker -> click",
                action=Action(type="walk", points=pts,  # type: ignore[arg-type]
                              intended=Intended(kind="cell", cell=(dx, dy), relative=True,
                                                note=f"harness spot {sx},{sy}")),
                outcome={"status": "pending", "evidence": evidence},  # type: ignore[arg-type]
            ))  # fmt: skip
            print(json.dumps({"attempt": i, "spot": [sx, sy], "offset": [dx, dy], **evidence}),
                  flush=True)  # fmt: skip
            time.sleep(max(abs(dx), abs(dy)) * 0.2 + 1.0)
            i += 1
    events, anchor = record_session.write_packets(log.dir, t_first, r.ns())
    log.finish(packet_events=len(events), packet_anchor=anchor, attempts=n)
    print(json.dumps({"session": sid, "packet_events": len(events), "attempts": n}), flush=True)
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
    wk.add_argument("--seed", type=int, default=20261007)
    wk.add_argument("--label", default="walk-alone")
    a = ap.parse_args()
    if a.rule == "login":
        return run_login(a.n, a.label)
    if a.rule == "walk":
        return run_walk(a.scene, a.n, a.seed, a.label)
    return 2


if __name__ == "__main__":
    sys.exit(main())
