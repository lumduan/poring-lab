#!/usr/bin/env python3
"""The Orc Lord FLEE proof's scorer (orclord-recognizer.md section 12; committed BEFORE fp1c is
scored, while it runs). Packets are ground truth OFFLINE only; nothing here reaches the bot.

Per trial k of the proof's events.jsonl (`orclord_flee_proof.py`):
- the WINDOW: from the trial's verified immunity OFF to its `trial_end` (or the run's end);
- the PARTY: every Orc Lord (1190) / Orc Archer (1189) gid the packets show appearing in it;
- SEEN: the first frame of the per-frame truth (`mvp_watch_study.py truth --map prt_fild08`) in
  the window with a party unit `in_view` (the round-2 definition: its predicted box inside the
  game frame, off the UI rects);
- HIT: the first `act` with target = our AID, source = a party gid and damage > 0 (the first
  attack of any damage, a miss included, is reported beside it);
- FLEE: the trial's `flee` event (`why` aura / hp) and the next non-GM `map_change` (the Fly
  Wing's same-map teleport);
- HP: the lowest `stat_change` hp in the window and the hp at the window's start.

A trial is COUNTED when SEEN exists ("a trial with no party unit in view at all is reported and
not counted"). It PASSES when counted, FLEE's why is "aura", and FLEE precedes HIT (or there is
no HIT).

Bar 1, "in >= 5 of 6 trials" with c counted trials: PASS when c >= 4 and passes >= ceil(5 c / 6)
(all six counted: 5); NO_VERDICT when c < 4. Bar 2: no death (an hp `stat_change` of 0, or a
`dead` stop in the events).

    orclord_flee_score.py --events EVENTS.jsonl --truth TRUTH.json --session REC_DIR --out JSON
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

PARTY = (1190, 1189)
MIN_COUNTED = 4


def _first(ts: Sequence[int]) -> int | None:
    return min(ts) if ts else None


def trial_windows(events: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """PURE: per spawned trial, (k, off_t, end_t, flee) from the proof's events."""
    run_end = max((int(e["t_ns"]) for e in events), default=0)
    spawns = [e for e in events if e.get("kind") == "spawn"]
    out = []
    for sp in spawns:
        k, t_sp = int(sp["i"]), int(sp["t_ns"])
        ends = [int(e["t_ns"]) for e in events
                if e.get("kind") == "trial_end" and int(e["i"]) == k]  # fmt: skip
        end_t = ends[0] if ends else run_end
        offs = [int(e["t_ns"]) for e in events if e.get("kind") == "immune"
                and e.get("want") == "off" and e.get("got") == "off"
                and t_sp <= int(e["t_ns"]) <= end_t]  # fmt: skip
        flees = [e for e in events if e.get("kind") == "flee" and int(e["i"]) == k]
        out.append({"i": k, "spawn_t": t_sp, "off_t": _first(offs), "end_t": end_t,
                    "flee": flees[0] if flees else None})  # fmt: skip
    return out


def score_trial(w: dict[str, Any], truth_rows: Sequence[dict[str, Any]],
                packets: Sequence[dict[str, Any]], aid: int) -> dict[str, Any]:  # fmt: skip
    """PURE: one trial's SEEN / HIT / FLEE / HP and its verdict (the module docstring)."""
    t0, t1 = w["off_t"], w["end_t"]
    res: dict[str, Any] = {"i": w["i"], "off_t": t0, "end_t": t1}
    if t0 is None:
        return {**res, "counted": False, "passed": False, "note": "no verified immunity OFF"}
    inwin = [p for p in packets if t0 <= int(p["t_mono_ns"]) <= t1]
    from_t = w["spawn_t"] - 2_000_000_000
    party = {int(p["gid"]) for p in packets if p.get("type") == "entity_appear"
             and p.get("job") in PARTY and from_t <= int(p["t_mono_ns"]) <= t1}  # fmt: skip
    seen = _first([int(r["t"]) for r in truth_rows if t0 <= int(r["t"]) <= t1
                   and any(u["in_view"] and u["job"] in PARTY for u in r["units"])])  # fmt: skip
    acts = [p for p in inwin if p.get("type") == "act" and int(p.get("target_gid", -1)) == aid
            and int(p.get("src_gid", -1)) in party]  # fmt: skip
    hit = _first([int(p["t_mono_ns"]) for p in acts if int(p.get("damage", 0)) > 0])
    attack = _first([int(p["t_mono_ns"]) for p in acts])
    hp = [(int(p["t_mono_ns"]), int(p["value"])) for p in packets if p.get("type") == "stat_change"
          and p.get("name") == "hp"]  # fmt: skip
    hp_before = [v for t, v in hp if t <= t0]
    hp_in = [v for t, v in hp if t0 <= t <= t1]
    flee = w["flee"]
    flee_t = int(flee["t_ns"]) if flee else None
    tele = None
    if flee_t is not None:
        tele = _first([int(p["t_mono_ns"]) for p in packets if p.get("type") == "map_change"
                       and not p.get("gm_command") and int(p["t_mono_ns"]) >= flee_t])  # fmt: skip
    counted = seen is not None
    why = flee.get("why") if flee else None
    passed = counted and why == "aura" and flee_t is not None and (hit is None or flee_t < hit)
    ms = lambda a, b: None if a is None or b is None else round((b - a) / 1e6, 1)  # noqa: E731
    return {**res, "party_gids": sorted(party), "seen_t": seen, "hit_t": hit,
            "first_attack_t": attack, "flee_t": flee_t, "why": why, "teleport_t": tele,
            "seen_to_f2_ms": ms(seen, flee_t), "f2_to_teleport_ms": ms(flee_t, tele),
            "f2_minus_hit_ms": ms(hit, flee_t),
            "hp_start": hp_before[-1] if hp_before else None,
            "hp_min": min(hp_in) if hp_in else None,
            "died": any(v == 0 for v in hp_in), "counted": counted,
            "passed": passed}  # fmt: skip


def verdict(trials: Sequence[dict[str, Any]], stopped_dead: bool = False) -> dict[str, Any]:
    """PURE: bar 1 (the module docstring's counting rule) and bar 2 (no death)."""
    c = sum(1 for t in trials if t["counted"])
    p = sum(1 for t in trials if t["passed"])
    need = math.ceil(5 * c / 6)
    bar1 = "NO_VERDICT" if c < MIN_COUNTED else ("PASS" if p >= need else "FAIL")
    died = stopped_dead or any(t.get("died") for t in trials)
    return {"trials": len(trials), "counted": c, "passed": p, "needed": need,
            "bar1": bar1, "bar2": "FAIL" if died else "PASS"}  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("--events", type=Path, required=True)
    ap.add_argument("--truth", type=Path, required=True)
    ap.add_argument("--session", type=Path, required=True, help="the recorder session's dir")
    ap.add_argument("--aid", type=int, default=None, help="our AID (default: inferred)")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/poring_dataset/src"))
    from poring_dataset.timeline import infer_self_aid

    events = [json.loads(x) for x in a.events.read_text().splitlines() if x.strip()]
    with gzip.open(a.session / "packets.jsonl.gz", "rt") as f:
        packets = [json.loads(x) for x in f]
    aid = a.aid if a.aid is not None else infer_self_aid(packets)
    if aid is None:
        raise SystemExit("our AID could not be inferred: pass --aid")
    truth_rows = json.loads(a.truth.read_text())["frames"]
    trials = [score_trial(w, truth_rows, packets, aid) for w in trial_windows(events)]
    stopped_dead = any(e.get("kind") == "run_end" and "dead" in str(e.get("reason"))
                       for e in events)  # fmt: skip
    doc = {"aid": aid, "trials": trials, "verdict": verdict(trials, stopped_dead)}
    a.out.write_text(json.dumps(doc, indent=1))
    print(json.dumps(doc["verdict"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
