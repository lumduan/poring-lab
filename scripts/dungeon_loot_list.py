#!/usr/bin/env python3
"""OFFLINE (Batt 2026-10-22, the 11:44 clip: "the bot SCANNED but LEFT AN ITEM ... in a mob
fight"): how many items our kills dropped on orcsdun01 were LEFT, and how many his LOOT LIST fix
would have reached, from the runs' PACKETS (the truth; nothing here reaches a runner).

    dungeon_loot_list.py SID [SID ...] [--json]

His fix: (1) a loot list kept across the fight -- every kill adds the 5 x 5 around the GM at that
death; the loot step after the fight covers the union (items do not move and last 60 s); (2) before
leaving, one last hover sweep over every cell that changed since the fight began.

Model, per item our kills dropped (arm_judge.item_fates / drops_of_kill):
- a FIGHT = our kills chained with at most FIGHT_GAP_S between them; it ends LOOT_START_S after
  its last kill (when the loot step starts);
- REACHED BY THE LIST: the item's cell is within 2 cells (Chebyshev) of the GM's cell at any kill
  of its fight, and it is still on the floor when the loot step starts (< 60 s old);
- REACHED BY THE SWEEP: the item fell during the fight (a change since the fight began), is still
  there at the loot step, and lies in view then (|dx| <= VIEW_X, |dy| <= VIEW_Y of the GM);
- "reached" says the hover would SEE it; a pickup still needs the cursor's PICKUP read and the
  walk there. An upper bound of what the fix can pick, not a prediction of picks.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

NS = 1_000_000_000
FIGHT_GAP_S = 8.0
LOOT_START_S = 2.5  # the runner's FIGHT_TAKEN_S: the loot step starts this long after the last hit
LIFE_S = 60.0  # rAthena's flooritem_lifetime (60000 ms)
VIEW_X, VIEW_Y = 8, 6  # the cells the game region shows around the GM (camera_rdp: 34 / 24 px)
Cell = tuple[int, int]


def cheb(a: Sequence[int], b: Sequence[int]) -> int:
    return max(abs(int(a[0]) - int(b[0])), abs(int(a[1]) - int(b[1])))


def at(track: Sequence[tuple[int, Cell]], t: int) -> Cell | None:
    """PURE: the GM's cell at ``t`` (the last track point at or before it)."""
    last = None
    for tm, c in track:
        if tm > t:
            break
        last = c
    return last


def fights(kill_ts: Sequence[int], gap_s: float = FIGHT_GAP_S) -> list[list[int]]:
    """PURE: the kill times grouped into fights (consecutive kills <= gap_s apart)."""
    out: list[list[int]] = []
    for t in sorted(kill_ts):
        if out and t - out[-1][-1] <= gap_s * NS:
            out[-1].append(t)
        else:
            out.append([t])
    return out


def reach(item: Mapping[str, Any], fight: Sequence[int], track: Sequence[tuple[int, Cell]]
          ) -> dict[str, Any]:  # fmt: skip
    """PURE: one item's reach by the loot list and by the final sweep (the module's model)."""
    t_loot = fight[-1] + int(LOOT_START_S * NS)
    end = item.get("t_end")
    on_floor = (end is None or int(end) > t_loot) and t_loot - int(item["t_fall"]) <= LIFE_S * NS
    cell = tuple(item["cell"])
    gms = [at(track, t) for t in fight]
    in_list = any(g is not None and cheb(cell, g) <= 2 for g in gms)
    g_end = at(track, t_loot)
    in_view = g_end is not None and abs(cell[0] - g_end[0]) <= VIEW_X \
        and abs(cell[1] - g_end[1]) <= VIEW_Y  # fmt: skip
    fell_in_fight = fight[0] - int(0.6 * NS) <= int(item["t_fall"]) <= t_loot
    return {"on_floor_at_loot": on_floor, "in_list": in_list, "in_view_at_loot": in_view,
            "list": bool(on_floor and in_list),
            "sweep": bool(on_floor and fell_in_fight and in_view)}  # fmt: skip


def judge(packets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    import arm_judge as aj
    import flow_judge as fj
    import hunt_core as hc

    track = fj.gm_track(packets)[0]
    pos = hc.walk_positions(packets)
    items = aj.item_fates(packets, pos, fj.mob_at, track)
    kills = aj.kills_of(packets)
    ours: dict[int, int] = {}
    for t, g in kills:
        for f in aj.drops_of_kill(items, t, fj.mob_at(pos, g, t)):
            ours.setdefault(f, t)
    groups = fights([t for t, _g in kills])
    rows = []
    for f, t_k in sorted(ours.items(), key=lambda kv: kv[1]):
        it = items[f]
        fight = next(g for g in groups if t_k in g)
        rows.append({"floor_id": f, "cell": list(it["cell"]), "fate": it["fate"],
                     "fight_kills": len(fight), **reach(it, fight, track)})  # fmt: skip
    left = [r for r in rows if r["fate"] != "picked"]
    return {
        "kills": len(kills), "fights": len(groups),
        "fights_with_2plus_kills": sum(len(g) >= 2 for g in groups),
        "items": len(rows), "picked": len(rows) - len(left), "left": len(left),
        "left_by_fate": {k: sum(r["fate"] == k for r in left)
                         for k in sorted({r["fate"] for r in left})},
        "left_reached_by_list": sum(r["list"] for r in left),
        "left_reached_by_sweep": sum(r["sweep"] for r in left),
        "left_reached_by_either": sum(r["list"] or r["sweep"] for r in left),
        "left_in_multi_kill_fights": sum(r["fight_kills"] >= 2 for r in left),
        "rows": rows,
    }  # fmt: skip


def load(sid: str) -> list[dict[str, Any]]:
    for root in (Path("/dev/shm/poring-lab-demo"), Path("/mnt/poring-lab-datasets")):
        p = root / sid / "packets.jsonl.gz"
        if p.exists():
            with gzip.open(p, "rt") as fh:
                return [json.loads(x) for x in fh]
    raise SystemExit(f"no packets for {sid}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("sids", nargs="+")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    tot: dict[str, int] = {}
    for sid in a.sids:
        got = judge(load(sid))
        if a.json:
            print(json.dumps({"sid": sid, **got}, indent=1))
        else:
            print(sid, json.dumps({k: v for k, v in got.items() if k != "rows"}))
        for k, v in got.items():
            if isinstance(v, int):
                tot[k] = tot.get(k, 0) + v
    if len(a.sids) > 1:
        print("TOTAL", json.dumps(tot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
