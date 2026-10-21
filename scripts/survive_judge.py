#!/usr/bin/env python3
"""The judge of the Crusader's survival trials (docs/demonstrations.md 3.96), OFFLINE: each trial's
events (survive.py: hp_read, press, death, trial_end) against its packets (the server's truth).
Nothing here reaches the runner.

    survive_judge.py SID [SID ...] [--offset-s 0.376]

The truth (packets): our `stat_change` hp / max_hp; `use_item_result` 504 (White Potion) / 601 (Fly
Wing) of ours; our `stat_change` sp falling by exactly 30 (Auto Guard 10) or 10 (Endure); hp 0 = a
death. A read at host time t shows the server's HP at t - ``offset`` (the packet -> frame lag; 3.96
names the measured one, else 375.9 ms).

Per 3.96's bars:
- S1: |read - true| <= 5 % of MaxHP on >= 95 % of reads with true HP < 100 % (n >= 200); over-reads
  (read > true + 5 %) on <= 1 %;
- S2: crossings of true HP below 55 % followed by a potion within 1.5 s; potions while true HP
  > 80 %;
- S3: the Fly Wing used before any death, and true HP at the escape;
- S4: Auto Guard casts (sp -30) and uptime (casts x 300 s clipped to the trial) / trial time;
- S6: the runner's stop vs the server's hp 0;
- reported: HP min, potions, escapes, damage taken per minute, regen per minute while no damage.
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

DEMO = Path("/dev/shm/poring-lab-demo")
NS = 1_000_000_000
POTION, FLY = 504, 601
AG_SP, ENDURE_SP = 30, 10
AG_S = 300.0
AID = 2000002  # the GM account's block id: the Crusader is a character on it (crusader.py)


def series(packets: Sequence[Mapping[str, Any]], name: str) -> list[tuple[int, int]]:
    """PURE: [(t_ns, value)] of our ``stat_change`` ``name`` (hp, max_hp, sp), in time order."""
    out = [(int(e["t_mono_ns"]), int(e.get("value") or 0)) for e in packets
           if e.get("type") == "stat_change" and e.get("name") == name]  # fmt: skip
    return sorted(out)


def at(ser: Sequence[tuple[int, int]], t: int) -> int | None:
    """PURE: the series' value at ``t`` (the last change at or before it), or None."""
    i = bisect.bisect_right([x[0] for x in ser], t)
    return ser[i - 1][1] if i else None


def items_used(packets: Sequence[Mapping[str, Any]], item_id: int, aid: int = AID) -> list[int]:
    """PURE: the times OUR ``use_item_result`` succeeded for ``item_id`` (a success goes to the
    area, so other players' uses arrive too: filtered by the user's id)."""
    return sorted(int(e["t_mono_ns"]) for e in packets
                  if e.get("type") == "use_item_result" and int(e.get("item_id") or -1) == item_id
                  and int(e.get("aid") or -1) == aid and e.get("ok", True))  # fmt: skip


def sp_casts(sp: Sequence[tuple[int, int]], cost: int) -> list[int]:
    """PURE: the times our SP fell by exactly ``cost`` (a cast of that skill)."""
    return [t for (t0, v0), (t, v) in zip(sp, sp[1:], strict=False) if v0 - v == cost]


def deaths_of(packets: Sequence[Mapping[str, Any]], aid: int = AID) -> list[int]:
    """PURE: the server's deaths of ours: our own id's vanish with reason "died" (1). The hp
    packet at a death can read 1, not 0 (T-S6 trial 1, 2026-10-21), so hp == 0 is not the cue."""
    return sorted(int(e["t_mono_ns"]) for e in packets
                  if e.get("type") == "entity_vanish" and int(e.get("gid") or -1) == aid
                  and int(e.get("reason") if e.get("reason") is not None else -1) == 1)  # fmt: skip


def judge(events: Sequence[Mapping[str, Any]], packets: Sequence[Mapping[str, Any]],
          offset_s: float = 0.376, max_hp: int | None = None) -> dict[str, Any]:  # fmt: skip
    """PURE: one trial's numbers for 3.96's bars. ``max_hp``: the fallback when no max_hp packet
    is in force at the trial's start (the trial's manifest carries the verified MaxHP)."""
    hp, mx, sp = series(packets, "hp"), series(packets, "max_hp"), series(packets, "sp")
    reads = [e for e in events if e.get("kind") == "hp_read"]
    off = int(offset_s * NS)
    t0 = int(reads[0]["t_ns"]) if reads else 0
    t1 = int(reads[-1]["t_ns"]) if reads else 0
    err: list[float] = []
    over = 0
    for e in reads:
        t = int(e["t_ns"]) - off
        h, m = at(hp, t), (at(mx, t) or max_hp)
        if h is None or not m or h >= m:
            continue
        d = float(e["frac"]) - h / m
        err.append(abs(d))
        over += d > 0.05
    n = len(err)
    s1 = {"n": n, "within_5pct": round(sum(x <= 0.05 for x in err) / n, 4) if n else None,
          "over_read_share": round(over / n, 4) if n else None}  # fmt: skip
    pots, flys = items_used(packets, POTION), items_used(packets, FLY)
    m0 = at(mx, t0) or max_hp or 0
    h0 = at(hp, t0 - off)  # the server's HP in force when the trial's reads begin
    win = ([(t0 - off, h0)] if h0 is not None else []) + [
        (t, v) for t, v in hp if t0 - off < t <= t1
    ]
    crossings = [t for (ta, va), (t, v) in zip(win, win[1:], strict=False)
                 if m0 and va >= 0.55 * m0 > v]  # fmt: skip
    answered = sum(any(t <= p <= t + int(1.5 * NS) for p in pots) for t in crossings)
    high = sum(1 for p in pots if m0 and (at(hp, p) or 0) > 0.80 * m0)
    deaths = [t for t in deaths_of(packets) if t0 - off <= t <= t1 + off]
    ag = [t for t in sp_casts(sp, AG_SP) if t0 - off <= t <= t1]
    span = max(1, t1 - t0)
    up = 0
    for i, t in enumerate(ag):
        end = min(t + int(AG_S * NS), ag[i + 1] if i + 1 < len(ag) else t1, t1)
        up += max(0, end - max(t, t0))
    stop = next((e for e in events if e.get("kind") == "death"), None)
    hp_vals = [v for _t, v in win]
    dmg = sum(max(0, va - v) for (_ta, va), (_t, v) in zip(win, win[1:], strict=False))
    regen = sum(max(0, v - va) for (_ta, va), (_t, v) in zip(win, win[1:], strict=False))
    mins = span / NS / 60.0
    return {
        "S1": s1,
        "S2": {"crossings_below_55": len(crossings), "answered_within_1_5s": answered,
               "potions": len(pots), "potions_above_80": high},
        "S3": {"escapes": len(flys),
               "before_death": bool(flys) and (not deaths or flys[0] < deaths[0]),
               "hp_at_escape": round((at(hp, flys[0]) or 0) / m0, 4) if flys and m0 else None},
        "S4": {"casts": len(ag), "uptime": round(up / span, 4)},
        "S6": {"server_deaths": len(deaths),
               "stop_after_s": round((int(stop["t_ns"]) - deaths[0] - off) / NS, 3)
               if stop and deaths else None},
        "hp_min": min(hp_vals) if hp_vals else None, "max_hp": m0,
        "damage_per_min": round(dmg / mins, 1), "regen_per_min": round(regen / mins, 1),
        "minutes": round(mins, 3),
    }  # fmt: skip


def load(sid: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    d = DEMO / sid
    ev = [json.loads(x) for x in (d / "events.jsonl").read_text().splitlines() if x]
    with gzip.open(d / "packets.jsonl.gz", "rt") as fh:
        pk = sorted((json.loads(x) for x in fh), key=lambda e: int(e["t_mono_ns"]))
    return ev, pk


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("sids", nargs="+")
    ap.add_argument("--offset-s", type=float, default=0.376)
    a = ap.parse_args()
    out = {}
    for sid in a.sids:
        man = json.loads((DEMO / sid / "manifest.json").read_text())
        mx_ = (man.get("thresholds") or {}).get("MAX_HP")
        out[sid] = judge(*load(sid), offset_s=a.offset_s, max_hp=mx_)
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
