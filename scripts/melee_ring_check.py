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


def requests(packets: Sequence[Mapping[str, Any]], aid: int = AID) -> list[tuple[int, int]]:
    """PURE: [(t, target)] of our attack requests (sit / stand excluded), in time order."""
    return sorted((int(e["t_mono_ns"]), int(e.get("target_gid") or -1)) for e in packets
                  if e.get("type") == "attack_request" and e.get("kind") not in ("sit", "stand")
                  and int(e.get("target_gid") or -1) != aid)  # fmt: skip


def scan_verdict(t0: int, t1: int, acts: Sequence[tuple[int, int]], dead: Mapping[int, int],
                 reqs: Sequence[int], req_targets: Sequence[int] | None = None
                 ) -> dict[str, Any]:  # fmt: skip
    """PURE: one hover window [t0, t1] while locked -> its verdict:
    - no_target / not_swinging (our last act on X ended > ACT_GAP_S before t0: nothing to keep);
    - x_dead (X died before t0) / died_inside (X died inside the window: the stop is the kill's);
    - retargeted: an attack request of ours on ANOTHER unit inside the window, or our next act on
      another unit while X lives; stopped: X alive, no act from t0 to t1 + ACT_GAP_S; else kept."""
    ts = [a[0] for a in acts]
    lo, hi = bisect.bisect_left(reqs, t0), bisect.bisect_right(reqs, t1)
    n_req = hi - lo
    i = bisect.bisect_left(ts, t0) - 1
    if i < 0:
        return {"verdict": "no_target", "requests": n_req}
    x = acts[i][1]
    out: dict[str, Any] = {"requests": n_req, "x": x}
    if dead.get(x, 1 << 62) <= t0:
        return {**out, "verdict": "x_dead"}
    if t0 - acts[i][0] > int(ACT_GAP_S * NS):
        return {**out, "verdict": "not_swinging"}
    if dead.get(x, 1 << 62) <= t1:
        return {**out, "verdict": "died_inside"}
    if req_targets is not None and any(g != x for g in req_targets[lo:hi]):
        return {**out, "verdict": "retargeted", "by": "request"}
    j = bisect.bisect_left(ts, t0)
    if j >= len(acts) or acts[j][0] > t1 + int(ACT_GAP_S * NS):
        return {**out, "verdict": "stopped"}
    if acts[j][1] != x:
        return {**out, "verdict": "retargeted", "to": acts[j][1]}
    return {**out, "verdict": "kept",
            "acts_on_x": sum(1 for t, g in acts[j:] if t <= t1 and g == x)}  # fmt: skip


def chain_gaps(packets: Sequence[Mapping[str, Any]], t0: int, t1: int,
               max_s: float = 15.0) -> dict[str, Any]:  # fmt: skip
    """The hand-off for EVERY engagement style (MR vs defend-scan alike): per kill of ours in
    [t0, t1] (arm_judge.kills_of: each death, gids are reused on respawn), the time from the
    death to our next act on ANOTHER unit; "chained" when <= max_s."""
    import statistics

    import arm_judge as aj

    acts = our_acts(packets)
    ts = [a[0] for a in acts]
    kills = [(t, g) for t, g in aj.kills_of(packets) if t0 <= t <= t1]
    gaps = []
    for td, g in kills:
        k = bisect.bisect_left(ts, td)
        nxt = next((a for a in acts[k:] if a[1] != g), None)
        if nxt is not None and nxt[0] - td <= max_s * NS:
            gaps.append((nxt[0] - td) / NS)
    s = sorted(gaps)
    mins = (t1 - t0) / NS / 60
    return {"kills": len(kills), "minutes": round(mins, 1),
            "s_per_kill": round(mins * 60 / len(kills), 1) if kills else None,
            "chained": len(s), "chained_share": round(len(s) / len(kills), 3) if kills else None,
            "gap_median_s": round(statistics.median(s), 2) if s else None,
            "gap_p25_s": round(s[len(s) // 4], 2) if s else None,
            "gap_p75_s": round(s[3 * len(s) // 4], 2) if s else None,
            "gap_le_1s": sum(x <= 1.0 for x in s)}  # fmt: skip


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
        scans.append(scan_verdict(t0, t1, acts, dead, [t for t, _ in reqs],
                                  [g for _, g in reqs]))  # fmt: skip
    hand = []
    ts = [a[0] for a in acts]
    for e in events:
        if e.get("kind") != "handoff":
            continue
        t = int(e["t_ns"])
        # the death just before the hand-off (<= 10 s): the last target we hit that died by then
        k = bisect.bisect_left(ts, t)
        prev = next((g for _, g in reversed(acts[max(0, k - 20):k])
                     if 0 <= t - dead.get(g, 1 << 62) <= 10 * NS), None)  # fmt: skip
        nxt = next((a for a in acts[k:] if a[1] != prev and a[0] - t <= 10 * NS), None)
        lat = None
        if prev is not None and nxt is not None:
            lat = round((nxt[0] - dead[prev]) / NS, 2)
        hand.append({"runner_from_kill_ms": e.get("from_kill_ms"),
                     "packets_death_to_next_act_s": lat})  # fmt: skip
    verdicts: dict[str, int] = {}
    for s in scans:
        verdicts[s["verdict"]] = verdicts.get(s["verdict"], 0) + 1
    t0 = next((int(e["t_ns"]) for e in events if e.get("kind") == "run_start"), 0)
    t1 = next((int(e["t_ns"]) for e in events if e.get("kind") == "run_end"), 1 << 62)
    return {"chain": chain_gaps(packets, t0, t1), "queue_scans": len(scans), "verdicts": verdicts,
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
