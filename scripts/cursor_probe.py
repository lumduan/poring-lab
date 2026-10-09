#!/usr/bin/env python3
"""cursor@probe: the HOVER-ONLY SWORD probe over a Poring, for the cursor classifiers' live
acceptance (docs/planning/cursor-robust.md section 5; a DRAFT for the parent: built offline, NOT
RUN). Nothing is ever clicked; the gate keeps its v3 classifier, and both classifiers are scored
OFFLINE on the saved crops (cursor_eval.py live).

    cursor_probe.py plan  --box X0,Y0,X1,Y1             OFFLINE: the probe points for one box
    cursor_probe.py sword --n 10 --seed S [--per 24]    prt_fild08, loot@1's spots and machinery

One trial (loot@1's machinery, scripts/loot1.py, unchanged): @killmonster2, @alive, @heal, @warp
to a seeded spot, the GM's fixed state, @monster Poring 1 beside the GM; the sampler thread runs
the CPU detector on every frame it can; the spawn is found and tracked. While the box is FRESH and
STILL (loot1.Track.still), the next point of its plan is hovered after a fresh park (two
motions, Prober9) and read as the npc-click probe arm reads (npc_click_test.read_series: 6 grabs
0.1 s apart, the v3 verdict and the best reference's real colour per grab, the crops). The plan:
loot@1's three ATTACK_POINTS, then a 3 x 3 grid on the box (SWORD points), and every third probe
a CONTROL point on the floor beside the box (WALK). Up to ``--per`` probes or PROBE_S per trial.
GM commands only through ro_agent.gm (the typing guard and the UI gate apply); the Poring is
never attacked, so the GM keeps its level. Pixels in, nothing out but hovers: the packets judge
offline where the Poring stood at each probe (rule 1).
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

RULE = "cursor@probe"
PROBE_S = 60.0  # per trial: probing stops after this, whatever is left of the plan
PER_TRIAL = 24
GRID = (
    (0.3, 0.35),
    (0.5, 0.35),
    (0.7, 0.35),
    (0.3, 0.6),
    (0.5, 0.6),
    (0.7, 0.6),
    (0.3, 0.85),
    (0.5, 0.85),
    (0.7, 0.85),
)  # box fractions (x, y): the body, left to right, top down
CONTROL_EVERY = 3  # every third probe is a control point on the floor beside the box
CONTROL_OFF = 1.6  # ... this many box widths left or right of the box centre, at the feet - 10 px
CONTROL_LIFT = 10.0


def sword_points(box: Sequence[float], attack_points: Sequence[tuple[float, float, float]],
                 grid: Sequence[tuple[float, float]] = GRID,
                 every: int = CONTROL_EVERY) -> list[dict[str, Any]]:  # fmt: skip
    """The plan for one box (x0, y0, x1, y1): loot@1's attack points, then the grid (kind
    "sword"); after every ``every``-1 sword points a "control" point beside the box, alternating
    sides. Each point: {"kind", "frac" (or "side"), "at": (u, v)}."""
    x0, y0, x1, y1 = (float(c) for c in box)
    w, h = x1 - x0, y1 - y0
    body = [{"kind": "sword", "frac": [fx, fy], "at": (x0 + fx * w, y0 + fy * h + dv)}
            for fx, fy, dv in attack_points]  # fmt: skip
    body += [{"kind": "sword", "frac": [fx, fy], "at": (x0 + fx * w, y0 + fy * h)}
             for fx, fy in grid]  # fmt: skip
    out: list[dict[str, Any]] = []
    side = 1
    for p in body:
        if (len(out) + 1) % every == 0:
            cx = (x0 + x1) / 2 + side * CONTROL_OFF * w
            out.append({"kind": "control", "side": side, "at": (cx, y1 - CONTROL_LIFT)})
            side = -side
        out.append(p)
    return out


def usable(points: Sequence[dict[str, Any]], in_ui: Any, size: tuple[int, int] = (1280, 720),
           margin: float = 64.0) -> list[dict[str, Any]]:  # fmt: skip
    """The points clear of the client's UI windows and at least ``margin`` px inside the client
    region (the 120 x 120 grab around each must stay inside it)."""
    w, h = size
    return [
        p
        for p in points
        if not in_ui(*p["at"])
        and margin <= p["at"][0] <= w - margin
        and margin <= p["at"][1] <= h - margin
    ]


def plan_cmd(box: Sequence[float]) -> list[dict[str, Any]]:
    """The usable plan for one box, with loot@1's attack points and UI windows."""
    import loot1

    return usable(sword_points(box, loot1.ATTACK_POINTS), loot1.in_ui)


def run_sword(n: int, seed: int, per: int = PER_TRIAL) -> int:  # pragma: no cover - live
    import bench
    import gm_state
    import loot1
    import npc_click_test as nct
    import record_session
    import ro_agent as r
    import rule_run as rr

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod
    from poring_env.demo import Action, DemoLog, DemoRecord, Intended, Outcome, new_session_id

    gat = gatmod.parse((cam.GAT_DIR / f"{loot1.MAP}.gat").read_bytes())
    plan = loot1.spots(gat.walkable(), seed, n)
    if len(plan) < n:
        raise SystemExit(f"only {len(plan)} spots of {n} fit the region")
    sid = new_session_id("cursor-probe-sword")
    log = DemoLog(sid)
    (log.dir / "crops").mkdir(exist_ok=True)
    lock = record_session.read_lock(r.ROOT / "state")
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena", rule=RULE,
              account="gm", mode="sword", n=n, seed=seed, map=loot1.MAP, per=per,
              spots=[list(s) for s in plan], read_grabs=nct.READ_GRABS,
              classifier_live="walk6.CursorRefs v3 (reads only; nothing is clicked)")  # fmt: skip
    print(json.dumps({"session": sid, "rule": RULE, "n": n, "seed": seed}), flush=True)
    t_first = r.ns()
    crops = 0
    trials: list[dict[str, Any]] = []
    with r.session(f"rule:{RULE}") as (agent, screen):
        rig = loot1.rig_up(agent, screen)
        try:
            for k, spot in enumerate(plan):
                trial: dict[str, Any] = {"k": k, "spot": list(spot), "t_start": r.ns(),
                                         "probes": 0}  # fmt: skip
                trials.append(trial)
                for cmd in ("@killmonster2", "@alive", "@heal",
                            f"@warp {loot1.MAP} {spot[0]} {spot[1]}"):  # fmt: skip
                    r.gm(agent, screen, cmd)
                time.sleep(rr.SCENE_ENTRY_S)
                trial["gm_state"] = gm_state.ensure_fixed(agent, screen, why=f"{RULE}:trial{k}",
                                                          out_dir=log.dir / "gm_state")  # fmt: skip
                r.gm(agent, screen, f"@monster {loot1.PORING} 1")
                bench.close_chat(agent, screen)
                r.activate_client(agent, screen)
                sampler = loot1.Sampler(rig.det)
                sampler.start()
                try:
                    time.sleep(loot1.SPAWN_WAIT_S)
                    gm_feet = tuple(rig.camera.project(np.zeros((1, 2)), np.zeros(1))[0])
                    t_find = r.ns()
                    hit = None
                    frames: list[Any] = []
                    while hit is None and (r.ns() - t_find) / 1e9 <= loot1.FIND_S:
                        frames = sampler.since(0)
                        hit = loot1.find_spawn(frames, gm_feet)
                        if hit is None:
                            time.sleep(0.1)
                    trial["found"] = hit is not None
                    if hit is None:
                        continue
                    idx, target = hit
                    track = loot1.Track(loot1.foot_of(target))
                    track.update(frames[idx][0], [target])
                    kk = idx + 1
                    j = 0  # the next entry of the plan, laid on the CURRENT still box
                    t0 = r.ns()
                    while trial["probes"] < per and (r.ns() - t0) / 1e9 <= PROBE_S:
                        new = sampler.since(kk)
                        kk += len(new)
                        for t, boxes in new:
                            track.update(t, boxes)
                        still = track.still(r.ns())
                        if still is None:
                            time.sleep(0.05)
                            continue
                        b = track.last_box
                        full = sword_points((b.x0, b.y0, b.x1, b.y1), loot1.ATTACK_POINTS)
                        p = full[j % len(full)]
                        j += 1
                        if not usable([p], loot1.in_ui):
                            time.sleep(0.02)  # the next entry; never a busy loop
                            continue
                        if not rig.pr.park():
                            continue
                        t_p = r.ns()
                        rig.pr.hover(*p["at"])
                        reads, arrays = nct.read_series(rig.pr, *p["at"])
                        name = f"crops/{crops:05d}.npz"
                        np.savez_compressed(log.dir / name, **arrays)
                        crops += 1
                        trial["probes"] += 1
                        box = [round(float(c), 1) for c in (b.x0, b.y0, b.x1, b.y1)]
                        log.append(DemoRecord(
                            session=sid, actor=f"rule:{RULE}", t_mono_ns=t_p, t_done_ns=r.ns(),
                            rule=f"{RULE}/sword", scene=f"field:{loot1.MAP}",
                            cue="hover only: the cursor over a still Poring box (or the control)",
                            action=Action(type="other", points=[tuple(p["at"])],
                                          intended=Intended(kind="unit", approx_px=tuple(p["at"]),
                                                            note=f"trial {k} {p['kind']}")),
                            outcome=Outcome(evidence={
                                **{kk_: v for kk_, v in p.items() if kk_ != "at"},
                                "at": list(p["at"]), "box": box, "still": still,
                                "reads": reads, "verdict": nct.ncs.verdict(reads),
                                "crop": name, "trial": k}),
                        ))  # fmt: skip
                finally:
                    sampler.stop()
                    trial["sampler"] = {"frames": len(sampler.frames), "error": sampler.error}
                    trial["t_end"] = r.ns()
                print(json.dumps({k_: trial.get(k_) for k_ in ("k", "found", "probes")}),
                      flush=True)  # fmt: skip
        finally:
            r.gm(agent, screen, "@killmonster2")
            bench.close_chat(agent, screen)
            rig.det.close()
    events, anchor = record_session.write_packets(log.dir, t_first, r.ns())
    (log.dir / "trials.json").write_text(json.dumps(trials, default=str))
    log.finish(packet_events=len(events), packet_anchor=anchor, trials=len(trials), crops=crops)
    print(json.dumps({"session": sid, "trials": len(trials), "crops": crops}), flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("mode", choices=("plan", "sword"))
    ap.add_argument("--box", default="")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--per", type=int, default=PER_TRIAL)
    a = ap.parse_args()
    if a.mode == "plan":
        box = [float(x) for x in a.box.split(",")]
        print(json.dumps(plan_cmd(box), default=list))
        return 0
    if a.seed is None:
        raise SystemExit("--seed is required (pre-registered)")
    return run_sword(a.n, a.seed, a.per)


if __name__ == "__main__":
    sys.exit(main())
