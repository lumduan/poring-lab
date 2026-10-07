#!/usr/bin/env python3
"""relocalise@1 (docs/demonstrations.md 3.10): the indoor landmark v1 ALONE -- the structure probes.

    reloc_run.py [--n 56] [--seed 20261015] [--label reloc-alone]

walk@5/6 re-localise when a no-entry sign appears on a cell the GAT calls walkable, but that path
fires rarely, so the method has never been measured on its own. Here the HARNESS makes the belief
wrong on purpose and the rule must find the truth:
1. a seeded `@warp prt_church X Y` puts the GM on a known walkable cell (the packets confirm it);
2. the belief handed to the rule is that cell + a seeded offset in the +-2 square, never (0, 0),
   always GAT-walkable (a real belief error of up to 2 cells, as dead reckoning makes);
3. the rule runs `walk5.relocalise` UNCHANGED: candidates = the belief +-2; each probe hovers the
   screen offset whose walkability best splits them, on cells flat for all; a unique survivor is
   the new belief; at most RELOC_PROBES probes.
Scoring (offline, packets): correct = the survivor is where the packets put us; WRONG = a survivor
elsewhere (the dangerous outcome: confidently wrong); undecided = no unique survivor.
Pixels in, input out; the rule never reads packets. Client pixels stay in /dev/shm.
"""

from __future__ import annotations

import argparse
import json
import random
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

from poring_env.demo import Action, DemoLog, DemoRecord, Intended, new_session_id  # noqa: E402

RELOC_RULE = "relocalise@1"
HOVER_S = 0.55
OFFSETS = [(dx, dy) for dy in range(-2, 3) for dx in range(-2, 3) if (dx, dy) != (0, 0)]


def score(session: Path) -> dict[str, Any]:
    """correct / wrong / undecided per attempt, against where the packets put us."""
    import gzip

    from poring_dataset import verify as V

    recs = [json.loads(x) for x in (session / "demo.jsonl").read_text().splitlines()]
    with gzip.open(session / "packets.jsonl.gz", "rt") as fh:
        events = [json.loads(x) for x in fh]
    aid = next((int(e["aid"]) for e in events if e.get("type") == "login_accepted"), None)
    if aid is None:
        from poring_dataset.timeline import infer_self_aid

        aid = infer_self_aid(events)
    rows = []
    for rec in recs:
        if rec.get("rule") != RELOC_RULE:
            continue
        ev = rec["outcome"]["evidence"]
        true = V.position_before(events, rec["t_mono_ns"], aid) if aid is not None else None
        got = ev.get("to")
        if true is None:
            status = "ambiguous"
        elif not ev.get("ok"):
            status = "undecided"
        else:
            status = "correct" if tuple(got) == tuple(true) else "wrong"
        rows.append({"i": ev["attempt"], "status": status, "true": true, "belief": ev["belief"],
                     "to": got, "probes": len(ev.get("probes", [])),
                     "harness_cell": ev["warp_cell"]})  # fmt: skip
    from collections import Counter

    return {"attempts": len(rows), "by_status": dict(Counter(r["status"] for r in rows)),
            "rows": rows}  # fmt: skip


def run(n: int, seed: int, label: str) -> int:
    import bench

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    mask = np.load(w5.NOENTRY_MASK)
    # the probe's settle: walk@6's measured 0.55 s, not walk@4/5's 0.4 (the client draws its
    # cursor and marker ~0.41-0.82 s after the second motion, 2026-10-07 17:46); 3.10 says so
    rr.HOVER_S = HOVER_S
    mapname, sx0, sy0 = rr.SCENES["indoor"]
    gat = gatmod.parse((cam.GAT_DIR / f"{mapname}.gat").read_bytes())
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    base = cam.camera_from_json(cj["camera"])
    camera = cam.camera_for_map(base, True, cj["indoor"]["yaw_deg"], cj["indoor"]["distance"])
    w = w5.World(camera, gat, (sx0, sy0))
    band = rr.ec_band()
    rng = random.Random(seed)
    sid = new_session_id(f"{label}-indoor")
    log = DemoLog(sid)
    lock = record_session.read_lock(r.ROOT / "state")
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena", rule=RELOC_RULE,
              n=n, scene="indoor", seed=seed, account="gm",
              reloc_radius=w5.RELOC_RADIUS, reloc_probes=w5.RELOC_PROBES)  # fmt: skip
    print(json.dumps({"session": sid, "rule": RELOC_RULE}), flush=True)
    t_first = r.ns()
    with r.session(f"rule:{RELOC_RULE}") as (agent, screen):
        r.gm(agent, screen, "@killmonster2")
        for i in range(n):
            for _ in range(200):  # the HARNESS: a seeded known cell, and a seeded wrong belief
                sx, sy = sx0 + rng.randint(-8, 8), sy0 + rng.randint(-8, 8)
                if not w.walkable[sy, sx]:
                    continue
                dx, dy = OFFSETS[rng.randrange(len(OFFSETS))]
                if w.walkable[sy + dy, sx + dx]:
                    break
            r.gm(agent, screen, f"@warp {mapname} {sx} {sy}")
            time.sleep(rr.WARP_SETTLE_S)
            bench.close_chat(agent, screen)
            r.activate_client(agent, screen)
            belief = (sx + dx, sy + dy)
            w.position = belief
            t0 = r.ns()
            pre = rr.snap(log, screen, f"{i:03d}-before")
            rl = w5.relocalise(agent, screen, w, mask, band)
            log.append(DemoRecord(
                session=sid, actor=f"rule:{RELOC_RULE}", t_mono_ns=t0, t_done_ns=r.ns(),
                frame=pre, rule=RELOC_RULE, scene=f"indoor:{mapname}",
                cue="relocalise v1: the structure probes (walk5.relocalise, unchanged)",
                action=Action(type="other", intended=Intended(
                    kind="cell", cell=belief, relative=False,
                    note=f"attempt {i}: the belief handed to the rule")),
                outcome={"status": "pending", "evidence": {  # type: ignore[arg-type]
                    "attempt": i, "warp_cell": [sx, sy], "belief": list(belief), **rl}},
            ))  # fmt: skip
            print(json.dumps({"attempt": i, "warp": [sx, sy], "belief": list(belief),
                              "ok": rl["ok"], "to": rl.get("to"),
                              "probes": len(rl["probes"])}), flush=True)  # fmt: skip
            time.sleep(0.3)
    events, anchor = record_session.write_packets(log.dir, t_first, r.ns())
    log.finish(packet_events=len(events), packet_anchor=anchor, attempts=n)
    print(json.dumps({"session": sid, "packet_events": len(events), "attempts": n}), flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--n", type=int, default=56)
    ap.add_argument("--seed", type=int, default=20261015)
    ap.add_argument("--label", default="reloc-alone")
    ap.add_argument("--score", type=Path, help="score a finished session instead of running")
    a = ap.parse_args()
    if a.score is not None:
        print(json.dumps(score(a.score), indent=1))
        return 0
    if not w5.NOENTRY_MASK.exists():
        raise SystemExit(f"{w5.NOENTRY_MASK} missing: run the walk5 cursor calibration")
    return run(a.n, a.seed, a.label)


if __name__ == "__main__":
    sys.exit(main())
