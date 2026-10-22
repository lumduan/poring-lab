#!/usr/bin/env python3
"""OFFLINE (Batt 2026-10-22 13:4x, MELEE-RING): "Verify first (packets): moving the pointer to scan
while a melee attack is in progress does NOT cancel or retarget the attack; if it does, scan only
between swings or after the lock, and report." And the hand-off numbers.

    melee_ring_check.py SID [SID ...]

Per `queue_scan` event of dungeon_hunt.py --engage melee_ring (the hovers while LOCKED; moves only,
never a click), from the PACKETS (the truth; nothing here reaches a runner):
- the target X = our last damaging-or-miss act's target before the scan began;
- `requests` = our attack requests inside the scan (must be 0: hovers never click);
- `kept` = X still alive at the scan's start and our next act after the scan's start is on X
  (the swing went on); `stopped` = X alive, yet no act of ours from the scan's start until
  ACT_GAP_S after its end; `retargeted` = our next act is on another unit while X still lives;
- `x_dead` = X died before the scan began (nothing to keep).
Per `handoff` event: the runner's ms from the kill, and from the packets the time from X's death
vanish to our first act on the next target. Rates per kill from the packets' kills.
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

NS = 1_000_000_000
AID = 2000002
ACT_GAP_S = 1.5  # an attack every 730 ms (ASPD 163): 2 missed swings = stopped


def our_acts(packets: Sequence[Mapping[str, Any]], aid: int = AID) -> list[tuple[int, int]]:
    """PURE: [(t, target)] of our attack acts (any damage, misses included), in time order."""
    return sorted((int(e["t_mono_ns"]), int(e.get("target_gid") or -1)) for e in packets
                  if e.get("type") == "act" and int(e.get("src_gid") or -1) == aid
                  and e.get("kind") in ("normal", "critical", "multi", "endure", "lucky")
                  and int(e.get("target_gid") or -1) != aid)  # fmt: skip


def deaths(packets: Sequence[Mapping[str, Any]]) -> dict[int, int]:
    """PURE: gid -> its death vanish time (reason 1)."""
    return {int(e["gid"]): int(e["t_mono_ns"]) for e in packets
            if e.get("type") == "entity_vanish" and int(e.get("reason", -1)) == 1}  # fmt: skip


def requests(packets: Sequence[Mapping[str, Any]], aid: int = AID) -> list[int]:
    """PURE: our attack request times (sit / stand excluded)."""
    return sorted(int(e["t_mono_ns"]) for e in packets if e.get("type") == "attack_request"
                  and e.get("kind") not in ("sit", "stand")
                  and int(e.get("target_gid") or -1) != aid)  # fmt: skip


def scan_verdict(t0: int, t1: int, acts: Sequence[tuple[int, int]], dead: Mapping[int, int],
                 reqs: Sequence[int]) -> dict[str, Any]:  # fmt: skip
    """PURE: one hover window [t0, t1] while locked -> its verdict (the module's definitions)."""
    ts = [a[0] for a in acts]
    i = bisect.bisect_left(ts, t0) - 1
    n_req = bisect.bisect_right(reqs, t1) - bisect.bisect_left(reqs, t0)
    if i < 0:
        return {"verdict": "no_target", "requests": n_req}
    x = acts[i][1]
    if dead.get(x, 1 << 62) <= t0:
        return {"verdict": "x_dead", "requests": n_req, "x": x}
    j = bisect.bisect_left(ts, t0)
    if j >= len(acts) or acts[j][0] > t1 + int(ACT_GAP_S * NS):
        return {"verdict": "stopped", "requests": n_req, "x": x}
    if acts[j][1] != x and dead.get(x, 1 << 62) > acts[j][0]:
        return {"verdict": "retargeted", "requests": n_req, "x": x, "to": acts[j][1]}
    return {"verdict": "kept", "requests": n_req, "x": x,
            "acts_on_x": sum(1 for t, g in acts[j:] if t <= t1 and g == x)}  # fmt: skip


def judge(events: Sequence[Mapping[str, Any]], packets: Sequence[Mapping[str, Any]]
          ) -> dict[str, Any]:  # fmt: skip
    acts = our_acts(packets)
    dead = deaths(packets)
    reqs = requests(packets)
    scans = []
    for e in events:
        if e.get("kind") != "queue_scan" or not e.get("hovers"):
            continue
        t1 = int(e["t_ns"])
        t0 = t1 - int(float(e.get("ms") or 0) * 1e6)
        scans.append(scan_verdict(t0, t1, acts, dead, reqs))
    hand = []
    for e in events:
        if e.get("kind") != "handoff":
            continue
        t = int(e["t_ns"])
        ts = [a[0] for a in acts]
        k = bisect.bisect_left(ts, t)
        prev = acts[k - 1][1] if k > 0 else None
        first_new = next((a for a in acts[k:] if a[1] != prev), None)
        hand.append(
            {
                "runner_from_kill_ms": e.get("from_kill_ms"),
                "packets_death_to_next_act_s": None
                if prev is None or first_new is None or prev not in dead
                else round((first_new[0] - dead[prev]) / NS, 2),
            }
        )
    verdicts: dict[str, int] = {}
    for s in scans:
        verdicts[s["verdict"]] = verdicts.get(s["verdict"], 0) + 1
    return {"queue_scans": len(scans), "verdicts": verdicts,
            "requests_during_scans": sum(s["requests"] for s in scans),
            "handoffs": len(hand), "handoff_rows": hand}  # fmt: skip


def load(sid: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    for root in (Path("/dev/shm/poring-lab-demo"), Path("/mnt/poring-lab-datasets")):
        d = root / sid
        if (d / "packets.jsonl.gz").exists():
            ev = [json.loads(x) for x in (d / "events.jsonl").read_text().splitlines() if x]
            with gzip.open(d / "packets.jsonl.gz", "rt") as fh:
                return ev, [json.loads(x) for x in fh]
    raise SystemExit(f"no session {sid}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("sids", nargs="+")
    a = ap.parse_args()
    for sid in a.sids:
        print(sid, json.dumps(judge(*load(sid))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
