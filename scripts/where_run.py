#!/usr/bin/env python3
"""where@1 (docs/demonstrations.md 3.13): the /where position fix ALONE, against the packets.

    where_run.py [--n 56] [--seed 20261020] [--label where-alone]
    where_run.py --version 2 --scene indoor|outdoor --seed S [--n 56]     (where@2, 3.15)
    where_run.py --score SESSION_DIR

Per attempt (prt_church, the indoor map every re-localisation test used):
1. the HARNESS: a seeded @warp to a walkable cell near the GM spot, then a seeded click on a cell
   3-8 cells away, THROUGH THE CURSOR GATE (cursor_gate.py, Batt 2026-10-08: no blind clicks) --
   the character walks somewhere (where exactly, only the packets know) and stops; this is the
   "belief in doubt" situation the fix is for;
2. the RULE: type /where (the chat path: the foreground gate applies), read the STABLE newest
   chat line (where_fix: the chat-font templates), (X, Y) or nothing.
Scoring (offline): correct = the packets' position at the read time; WRONG = another cell (a
misread absolute fix is the dangerous outcome); no fix = nothing parsed. Compared with
relocalise@2 (3.11). Pixels in, input out.
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cursor_gate  # noqa: E402
import record_session  # noqa: E402
import ro_agent as r  # noqa: E402
import rule_run as rr  # noqa: E402
import where_fix as wf  # noqa: E402

from poring_env.demo import Action, DemoLog, DemoRecord, Intended, new_session_id  # noqa: E402

WHERE_RULE = "where@1"
RULES = {1: "where@1", 2: "where@2"}
SCENES = {"indoor": ("prt_church", 104, 122, True), "outdoor": ("prt_fild08", 268, 107, False)}
GM_AID = 2000002
WALK_WAIT_S = 3.0
SAFE = (300, 200, 980, 520)  # client px (x0, y0, x1, y1): the harness's walk click
HARNESS_TRIES = 6  # seeded candidates the cursor gate may refuse before the attempt goes clickless


def score(session: Path) -> dict[str, Any]:
    from poring_dataset import verify as V

    recs = [json.loads(x) for x in (session / "demo.jsonl").read_text().splitlines()]
    with gzip.open(session / "packets.jsonl.gz", "rt") as fh:
        events = [json.loads(x) for x in fh]
    marks_path = session / "interrupted.json"
    marks = json.loads(marks_path.read_text()) if marks_path.exists() else {}
    rows = []
    for rec in recs:
        if rec.get("rule") not in RULES.values():
            continue
        ev = rec["outcome"]["evidence"]
        true = V.position_before(events, ev["t_read"], GM_AID)
        got = ev.get("xy")
        if rec.get("record_id") in marks:
            status = "interrupted"
        elif true is None:
            status = "ambiguous"
        elif got is None:
            status = "no_fix"
        else:
            status = "correct" if tuple(got) == tuple(true) else "wrong"
        rows.append({"i": ev["attempt"], "status": status, "true": true, "read": got,
                     "warp": ev["warp_cell"], "rejects": ev.get("rejects", [])})  # fmt: skip
    scored = [x for x in rows if x["status"] != "interrupted"][:50]
    gates = Counter(g.split(":")[0] for x in scored for g in x["rejects"])
    return {"attempts": len(rows), "scored": dict(Counter(x["status"] for x in scored)),
            "interrupted": sum(x["status"] == "interrupted" for x in rows),
            "gate_rejections": dict(gates),
            "wrong": [x for x in scored if x["status"] == "wrong"], "rows": rows}  # fmt: skip


def run(n: int, seed: int, label: str, version: int = 1, scene: str = "indoor") -> int:
    import bench

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    rule = RULES[version]
    templates = wf.load_templates(wf.TEMPLATES if version == 1 else wf.TEMPLATES_V2)
    mapname, sx0, sy0, indoor = SCENES[scene]
    gat = gatmod.parse((cam.GAT_DIR / f"{mapname}.gat").read_bytes())
    walk = gat.walkable()
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    base = cam.camera_from_json(cj["camera"])
    camera = (cam.camera_for_map(base, True, cj["indoor"]["yaw_deg"], cj["indoor"]["distance"])
              if indoor else base)  # fmt: skip
    rng = random.Random(seed)
    sid = new_session_id(f"{label}-{scene}")
    log = DemoLog(sid)
    lock = record_session.read_lock(r.ROOT / "state")
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena", rule=rule,
              n=n, scene=scene, seed=seed, account="gm", version=version)  # fmt: skip
    print(json.dumps({"session": sid, "rule": rule}), flush=True)
    t_first = r.ns()
    with r.session(f"rule:{rule}") as (agent, screen):
        pr = cursor_gate.prober(agent, screen)  # fails closed: no click without the gate
        r.gm(agent, screen, "@killmonster2")
        for i in range(n):
            if version == 2:
                r.gm(agent, screen, "@killmonster2")  # the field's own monsters, every attempt
            for _ in range(200):  # the HARNESS: a seeded known cell ...
                sx, sy = sx0 + rng.randint(-8, 8), sy0 + rng.randint(-8, 8)
                if walk[sy, sx]:
                    break
            r.gm(agent, screen, f"@warp {mapname} {sx} {sy}")
            time.sleep(rr.WARP_SETTLE_S)
            bench.close_chat(agent, screen)
            r.activate_client(agent, screen)
            gate: list[str] = []
            d = (0, 0)
            for _ in range(400):  # ... then a seeded click 3-8 cells away: where we stop is unknown
                d = (rng.randint(-8, 8), rng.randint(-8, 8))
                if not 3 <= max(abs(d[0]), abs(d[1])) <= 8:
                    continue
                if not walk[sy + d[1], sx + d[0]]:
                    continue
                rel = np.array([d], dtype=float)
                u, v = camera.project(rel, gat.relative_altitude((sx, sy), rel))[0]
                # a SAFE box clear of every UI panel: the first run's blind click hit the left menu
                # icons and opened the shortcut help (22:02, amended in 3.13 before scoring)
                if not (SAFE[0] <= u <= SAFE[2] and SAFE[1] <= v <= SAFE[3]):
                    continue
                # the CURSOR GATE (Batt 2026-10-08): where@2's blind click attacked monsters and
                # contacted NPCs; a harness click needs the walk cursor, twice, or no click
                g = cursor_gate.gated_click(pr, u, v)
                gate.append(g["why"])
                if g["clicked"] or len(gate) >= HARNESS_TRIES:
                    break
            if gate and gate[-1] == "ok":
                time.sleep(WALK_WAIT_S)
            else:
                d = (0, 0)  # no harness click: the character stays on the warp cell
            t0 = r.ns()
            belief = (sx + d[0], sy + d[1])  # the rule's own dead reckoning: where it clicked to go
            got = (wf.fix(agent, screen, templates) if version == 1
                   else wf.fix_v2(agent, screen, templates, belief, walk))  # the RULE  # fmt: skip
            log.append(DemoRecord(
                session=sid, actor=f"rule:{rule}", t_mono_ns=t0, t_done_ns=r.ns(),
                rule=rule, scene=f"{scene}:{mapname}",
                cue=f"{rule}: /where, the stable newest chat line, the chat-font templates",
                action=Action(type="other", intended=Intended(
                    kind="cell", cell=got["xy"] or (sx, sy), relative=False,
                    note=f"attempt {i}: the fix read")),
                outcome={"status": "pending", "evidence": {  # type: ignore[arg-type]
                    "attempt": i, "warp_cell": [sx, sy], "click_rel": list(d),
                    "xy": list(got["xy"]) if got["xy"] else None, "why": got.get("why"),
                    "rejects": got.get("rejects", []), "belief": list(belief),
                    "harness_gate": gate, "t_read": got["t"]}},
            ))  # fmt: skip
            print(json.dumps({"attempt": i, "warp": [sx, sy], "click_rel": list(d),
                              "read": got["xy"]}), flush=True)  # fmt: skip
            bench.close_chat(agent, screen)
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
    ap.add_argument("--seed", type=int, default=20261020)
    ap.add_argument("--label", default="where-alone")
    ap.add_argument("--score", type=Path)
    ap.add_argument("--version", type=int, choices=(1, 2), default=1)
    ap.add_argument("--scene", choices=sorted(SCENES), default="indoor")
    a = ap.parse_args()
    if a.score is not None:
        print(json.dumps(score(a.score), indent=1))
        return 0
    need = wf.TEMPLATES if a.version == 1 else wf.TEMPLATES_V2
    if not need.exists():
        raise SystemExit(f"{need} missing: where_fix.py cut / cut-v2 (design time)")
    return run(a.n, a.seed, a.label, a.version, a.scene)


if __name__ == "__main__":
    sys.exit(main())
