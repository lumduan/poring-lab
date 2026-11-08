#!/usr/bin/env python3
"""Where a run's fight time goes (rogue-xmas02.md 4AF, p24's K1 / K2; committed before p24).

    fight_time.py SESSION_DIR

OFFLINE ground truth only (packets, ADR-0007): nothing here reaches a runner.
- Fights: each ``engage`` event to the next ``fight_end`` (events.jsonl).
- Kills: ``entity_vanish`` with reason 1 (died) of a monster we hit (an ``act`` of ours, src_gid
  OUR_GID, on it), at or before its death.
- A fight is a KILL fight when such a death falls inside it (to fight_end + 1 s); per kill fight
  the time from the first death to fight_end (``after_kill_s``: K1 is its median); the NO-KILL
  fights' count and total time (K2's context).
- K3 (--kill-gap): each ``kill`` event by ``hit_gap`` is MATCHED when a death of ours (above) came
  0-3 s before it; the matched share.
By this definition (2026-11-09): p21 92 fights, 42 kill fights, after the kill p50 6.46 s (total
276.8 s), no-kill fights 50 (434.1 s); p16 6.50 s (296.3 s), p19 6.53 s, p22 6.47 s.
"""

from __future__ import annotations

import argparse
import gzip
import json
import statistics
from collections.abc import Sequence
from pathlib import Path
from typing import Any

OUR_GID = 2000002  # the lab account's character id on the lab server (every pilot's Rogue)
DIED = 1  # entity_vanish reason: died


def fights(events: Sequence[dict[str, Any]]) -> list[tuple[int, int]]:
    """PURE: (engage t_ns, fight_end t_ns) pairs, in order."""
    out, start = [], None
    for e in events:
        if e.get("kind") == "engage" and start is None:
            start = int(e["t_ns"])
        elif e.get("kind") == "fight_end" and start is not None:
            out.append((start, int(e["t_ns"])))
            start = None
    return out


def our_kills(packets: Sequence[dict[str, Any]], our_gid: int = OUR_GID) -> list[int]:
    """PURE: the death times of monsters we hit before they died, sorted."""
    died = {p["gid"]: int(p["t_mono_ns"]) for p in packets
            if p.get("type") == "entity_vanish" and p.get("reason") == DIED}  # fmt: skip
    hit = {p.get("target_gid") for p in packets if p.get("type") == "act"
           and p.get("src_gid") == our_gid and p.get("target_gid") in died
           and int(p["t_mono_ns"]) <= died[p.get("target_gid")]}  # fmt: skip
    return sorted(t for g, t in died.items() if g in hit)


def summary(fs: Sequence[tuple[int, int]], kills: Sequence[int]) -> dict[str, Any]:
    """PURE: kill fights' after-kill time (p50, total) and the no-kill fights' count and time."""
    after, nokill = [], []
    for s, f in fs:
        k = [t for t in kills if s <= t <= f + 1_000_000_000]
        if k:
            after.append(max(0.0, (f - k[0]) / 1e9))
        else:
            nokill.append((f - s) / 1e9)
    return {"fights": len(fs), "kill_fights": len(after),
            "after_kill_p50_s": round(statistics.median(after), 2) if after else None,
            "after_kill_total_s": round(sum(after), 1),
            "nokill_fights": len(nokill), "nokill_total_s": round(sum(nokill), 1)}  # fmt: skip


def hit_gap_match(events: Sequence[dict[str, Any]], kills: Sequence[int],
                  window_s: float = 3.0) -> dict[str, Any]:  # fmt: skip
    """PURE: --kill-gap's inferred kills, matched to a death of ours 0..window_s before each."""
    inferred = [int(e["t_ns"]) for e in events
                if e.get("kind") == "kill" and e.get("by") == "hit_gap"]  # fmt: skip
    m = sum(any(0 <= t - k <= window_s * 1e9 for k in kills) for t in inferred)
    return {"hit_gap_kills": len(inferred), "hit_gap_matched": m,
            "hit_gap_share": round(m / len(inferred), 3) if inferred else None}  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("session", type=Path)
    a = ap.parse_args(argv)
    events = [json.loads(x) for x in (a.session / "events.jsonl").read_text().splitlines() if x]
    with gzip.open(a.session / "packets.jsonl.gz", "rt") as fh:
        packets = [json.loads(x) for x in fh if x.strip()]
    kills = our_kills(packets)
    print(json.dumps({"session": a.session.name, **summary(fights(events), kills),
                      **hit_gap_match(events, kills)}))  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
