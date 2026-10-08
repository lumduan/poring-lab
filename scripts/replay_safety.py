#!/usr/bin/env python3
"""Per-session SAFETY from a banked-capture REPLAY (guarded_build.py replay:, current decoders).

    replay_safety.py --events E.jsonl [--events E2.jsonl ...] SESSION_DIR [SESSION_DIR ...]

For each session (its manifest's t0_mono_ns .. t1_mono_ns): our REQUESTS (`attack_request`,
`npc_contact` with the NPC's gid) and the server's acts FROM us (normal, pickup). The live sniffer
emitted no request events before its 2026-10-08 07:31 rebuild; the replay re-decodes the raw
packets, so this is the request-side record for the runs before it. Offline only: packets never
reach the agent (ADR-0007). Run it on positive controls too (the safety_signal_check sessions):
a sensor that cannot see a deliberate positive case proves nothing (demonstrations.md §2a).
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

GM_AID = 2000002


def load(paths: list[Path]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for p in paths:
        for line in p.open():
            if line in seen:  # overlapping replays of the same hour
                continue
            seen.add(line)
            out.append(json.loads(line))
    out.sort(key=lambda e: int(e.get("t_mono_ns", 0)))
    return out


def judge(events: list[dict[str, Any]], t0: int, t1: int) -> dict[str, Any]:
    win = [e for e in events if t0 <= int(e.get("t_mono_ns", 0)) <= t1]
    acts = Counter(str(e.get("kind")) for e in win
                   if e.get("type") == "act" and int(e.get("src_gid", -1)) == GM_AID)  # fmt: skip
    contacts = [e for e in win if e.get("type") == "npc_contact"]
    return {"events": len(win),
            "attack_request": sum(e.get("type") == "attack_request" for e in win),
            "npc_contact": len(contacts),
            "npc_contact_gids": sorted({int(e.get("npc_gid", -1)) for e in contacts}),
            "act_normal_from_us": acts["normal"], "act_pickup_from_us": acts["pickup"]}  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--events", type=Path, action="append", required=True)
    ap.add_argument("sessions", type=Path, nargs="+")
    a = ap.parse_args()
    events = load(a.events)
    lo = int(events[0]["t_mono_ns"]) if events else 0
    hi = int(events[-1]["t_mono_ns"]) if events else 0
    rows = {}
    for s in a.sessions:
        man = json.loads((s / "manifest.json").read_text())
        window = "manifest"
        if "t0_mono_ns" in man and "t1_mono_ns" in man:
            t0, t1 = int(man["t0_mono_ns"]), int(man["t1_mono_ns"])
        else:  # an unfinished session: its records' own span, + 5 s
            recs = [json.loads(x) for x in (s / "demo.jsonl").read_text().splitlines() if x]
            if not recs:
                rows[s.name] = {"covered": False, "why": "no records"}
                continue
            t0 = min(int(r["t_mono_ns"]) for r in recs)
            t1 = max(int(r.get("t_done_ns") or r["t_mono_ns"]) for r in recs) + 5_000_000_000
            window = "records"
        row = judge(events, t0, t1)
        row["window"] = window
        row["covered"] = lo <= t0 and t1 <= hi  # the replay spans the whole session
        rows[s.name] = row
    print(json.dumps(rows, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
