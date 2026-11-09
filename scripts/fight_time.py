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
- L1 / L2 (rogue-xmas02.md 4AQ, Batt 2026-11-09: "pick up what the scan finds; scan for drops only
  after a kill"): floor items that appeared (``floor_item_appear``), our ``pickup_request``s and
  their share; the loot steps that hovered (``hovered`` > 0) and how many of them came with NO death
  of ours in the 10 s before (a loot scan without a kill). Base runs p28-p36: 0-2 pickups for 21-46
  floor items (the loot list was empty: no exp line at Base 99).
- K3 (--kill-gap): each ``kill`` event by ``hit_gap`` is MATCHED when a death of ours (above) came
  0-3 s before it; the matched share.
- L3 / L4 (--loot-first, rogue-xmas02.md 4AT; committed before p39 was scored): the runner's
  ``kill`` events followed by a ``loot_step`` with a list (``list_kills`` > 0) within 5 s, and
  their share (L3; p38: 17 / 53); the ``engage`` events ended by a ``fight_end`` "quiet kill" in
  under 50 ms, and their share of all engages (L4; p38: 1,057 / 1,144); the loot clicks by why
  (``list`` / ``sweep`` / ``scan_hand``).
- Q1 / S1 (--quiet-scan, rogue-xmas02.md 4AW; committed before p42 was scored): the ``scan``
  events of purpose ``defend`` whose START (the event time minus its ``ms``) had NO ``act`` on us
  (target OUR_GID) in the 5 s before -- Q1 counts them (p38 / p39 / p40: 39 / 28 / 34) and how
  many found a sword; S1 = our damaging hits taken (``act`` on us with damage > 0) per 10 min of
  the run (p38 / p39 / p40: 11.2 / 10.8 / 11.2).
- B1 / B2 (--boss-walk, rogue-xmas02.md 4AZ; committed before its trial was scored): each
  ``boss_walk`` event BROKE CONTACT when no ``act`` on us (a hit OR a miss: the Rogue's FLEE makes
  most of them misses, p40: 24 of 24) came from a summon (a gid whose ``entity_appear`` job is in
  SUMMON_JOBS: Garm Baby 1515, Christmas Goblin 1607) in the 2.5 .. 10 s after it; the boss guard's
  Fly Wings (``press`` fly, why ``boss``); the summons' acts on us and the damaging ones.
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
SUMMON_JOBS = (1515, 1607)  # xmas_dun02's Stormy Knight summons (Garm Baby, Christmas Goblin)
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
    """PURE: the death times of monsters we hit before they died, sorted. Time-ordered and per LIFE
    of a gid: the server REUSES monster gids for later spawns, so a death counts when one of our
    acts on that gid came after its previous death (or the start) and before this one.
    (2026-11-09 fix: a gid -> last-death dict let a later spawn's death overwrite the real one --
    p37 lost 17 real kills to it; K3, K1 and L2 were mis-scored.)"""
    out: list[int] = []
    hit_since: set[Any] = set()  # gids with an act of ours since their last death
    for p in sorted(packets, key=lambda q: int(q.get("t_mono_ns") or 0)):
        typ = p.get("type")
        if typ == "act" and p.get("src_gid") == our_gid and p.get("target_gid") is not None:
            hit_since.add(p.get("target_gid"))
        elif typ == "entity_vanish" and p.get("reason") == DIED:
            g = p.get("gid")
            if g in hit_since:
                out.append(int(p["t_mono_ns"]))
            hit_since.discard(g)
    return sorted(out)


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


def loot_summary(events: Sequence[dict[str, Any]], packets: Sequence[dict[str, Any]],
                 kills: Sequence[int], window_s: float = 10.0) -> dict[str, Any]:  # fmt: skip
    """PURE: L1 (pickups / floor items) and L2 (hovering loot steps with no kill of ours before)."""
    floor = sum(1 for p in packets if p.get("type") == "floor_item_appear")
    picks = sum(1 for p in packets if p.get("type") == "pickup_request")
    steps = [int(e["t_ns"]) for e in events
             if e.get("kind") == "loot_step" and int(e.get("hovered") or 0) > 0]  # fmt: skip
    no_kill = sum(1 for t in steps if not any(0 <= t - k <= window_s * 1e9 for k in kills))
    return {"floor_items": floor, "pickups": picks,
            "pickup_share": round(picks / floor, 3) if floor else None,
            "loot_steps_hovering": len(steps), "loot_steps_without_kill": no_kill}  # fmt: skip


def loot_order(events: Sequence[dict[str, Any]], within_s: float = 5.0,
               instant_s: float = 0.05) -> dict[str, Any]:  # fmt: skip
    """PURE: L3 (kills looted within ``within_s``) and L4 (engages ended at once by quiet-kill)."""
    kills = [int(e["t_ns"]) for e in events if e.get("kind") == "kill"]
    steps = [int(e["t_ns"]) for e in events
             if e.get("kind") == "loot_step" and int(e.get("list_kills") or 0) > 0]  # fmt: skip
    looted = sum(any(0 <= t - k <= within_s * 1e9 for t in steps) for k in kills)
    engages = sum(1 for e in events if e.get("kind") == "engage")
    instant = sum(1 for e0, e1 in zip(events, events[1:], strict=False)
                  if e0.get("kind") == "engage" and e1.get("kind") == "fight_end"
                  and e1.get("why") == "quiet kill"
                  and int(e1["t_ns"]) - int(e0["t_ns"]) < instant_s * 1e9)  # fmt: skip
    why: dict[str, int] = {}
    for e in events:
        if e.get("kind") == "loot_click":
            why[str(e.get("why"))] = why.get(str(e.get("why")), 0) + 1
    return {"kills_looted_5s": looted, "kills_events": len(kills),
            "looted_share": round(looted / len(kills), 3) if kills else None,
            "engages": engages, "instant_ends": instant,
            "instant_share": round(instant / engages, 3) if engages else None,
            "loot_clicks_by": dict(sorted(why.items()))}  # fmt: skip


def quiet_scans(events: Sequence[dict[str, Any]], packets: Sequence[dict[str, Any]],
                our_gid: int = OUR_GID, window_s: float = 5.0) -> dict[str, Any]:  # fmt: skip
    """PURE: Q1 (defend scans with no act on us in the ``window_s`` before their start) and S1
    (damaging acts on us per 10 min of the run)."""
    on_us = sorted(int(p["t_mono_ns"]) for p in packets
                   if p.get("type") == "act" and p.get("target_gid") == our_gid)  # fmt: skip
    quiet = found = 0
    for e in events:
        if e.get("kind") != "scan" or e.get("purpose") != "defend":
            continue
        start = int(e["t_ns"]) - int(float(e.get("ms") or 0) * 1e6)
        if not any(start - window_s * 1e9 <= t <= start for t in on_us):
            quiet += 1
            found += e.get("found") is not None
    t0 = next((int(e["t_ns"]) for e in events if e.get("kind") == "run_start"), None)
    t1 = next((int(e["t_ns"]) for e in reversed(events) if e.get("kind") == "run_end"), None)
    per10 = None
    if t0 is not None and t1 is not None and t1 > t0:
        n = sum(1 for p in packets if p.get("type") == "act" and p.get("target_gid") == our_gid
                and int(p.get("damage") or 0) > 0 and t0 <= int(p["t_mono_ns"]) <= t1)  # fmt: skip
        per10 = round(n / ((t1 - t0) / 6e10) * 10, 1)
    return {"quiet_defend_scans": quiet, "quiet_defend_found": found, "hits_taken_per10": per10}


def boss_walks(events: Sequence[dict[str, Any]], packets: Sequence[dict[str, Any]],
               our_gid: int = OUR_GID, jobs: Sequence[int] = SUMMON_JOBS,
               after_s: tuple[float, float] = (2.5, 10.0)) -> dict[str, Any]:  # fmt: skip
    """PURE: B1 (walk-aways that broke contact with the summons) and B2 (the guard's Fly Wings)."""
    job = {int(p["gid"]): int(p.get("job") or 0) for p in packets
           if p.get("type") == "entity_appear" and p.get("gid") is not None}  # fmt: skip
    acts = [p for p in packets if p.get("type") == "act" and p.get("target_gid") == our_gid
            and job.get(int(p.get("src_gid") or 0)) in jobs]  # fmt: skip
    hits = sorted(int(p["t_mono_ns"]) for p in acts)
    walks = [int(e["t_ns"]) for e in events if e.get("kind") == "boss_walk"]
    broke = sum(not any(t + after_s[0] * 1e9 < h <= t + after_s[1] * 1e9 for h in hits)
                for t in walks)  # fmt: skip
    flies = sum(1 for e in events if e.get("kind") == "press"
                and e.get("what") == "fly" and e.get("why") == "boss")  # fmt: skip
    return {"boss_walks": len(walks), "boss_walks_broke": broke, "boss_flies": flies,
            "boss_guards": sum(1 for e in events if e.get("kind") == "boss_guard"),
            "summon_acts": len(hits),
            "summon_damaging": sum(int(p.get("damage") or 0) > 0 for p in acts)}  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("session", type=Path)
    a = ap.parse_args(argv)
    events = [json.loads(x) for x in (a.session / "events.jsonl").read_text().splitlines() if x]
    with gzip.open(a.session / "packets.jsonl.gz", "rt") as fh:
        packets = [json.loads(x) for x in fh if x.strip()]
    kills = our_kills(packets)
    print(json.dumps({"session": a.session.name, **summary(fights(events), kills),
                      **hit_gap_match(events, kills),
                      **loot_summary(events, packets, kills), **loot_order(events),
                      **quiet_scans(events, packets), **boss_walks(events, packets)}))  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
