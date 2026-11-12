#!/usr/bin/env python3
"""A WEAPON-SWAP hunt, offline from packets (Batt 2026-11-12: "use my technique; use me as the
bar for training the bot"): how a session's weapon changes line up with its steals and kills.
Packets are ground truth here (ADR-0007); nothing reaches a runner.

    weapon_swap_study.py SESSION [--live S] [--weak INDEX] [--main INDEX] [--start main|weak]

Batt's xmas_dun02 Rogue demo (2026-11-12 21:50, 30.5 min) alternated the Knife (inventory index
10) and his Damascus +8 (index 2) in the weapon slot 208 times. This reads, per kill
(arm_judge.kills_of):
- the weapon on at its first and its last damaging hit of ours (the equip_result packets in force);
- whether it gave a STEAL: an item gain (pickup_result) between our first hit on it and 1 s after
  its death, not <= 2 s after a pickup request of ours (Snatcher procs only on our hits);
- the knife hits before that steal, and the time from the steal to the next swap to the main
  weapon (the "swap back once the steal lands" reflex);
- the kill time (first hit -> death).

``--start``: the weapon on before the first equip_result in the window (default main).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

NS = 1_000_000_000
PICK_S = 2.0  # a gain this soon after our pickup request is the pickup's, not a steal
AFTER_DEATH_S = 1.0


def weapon_at(swaps: Sequence[tuple[int, str]], t: int, start: str) -> str:
    """PURE: the weapon in force at ``t`` (swaps sorted by time)."""
    w = start
    for te, name in swaps:
        if te > t:
            break
        w = name
    return w


def kill_rows(
    packets: Sequence[Mapping[str, Any]],
    kills: Sequence[tuple[int, int]],
    aid: int,
    names: Mapping[int, str],
    start: str,
) -> list[dict[str, Any]]:
    """PURE: one row per kill (the module docstring)."""
    ps = sorted(packets, key=lambda p: int(p["t_mono_ns"]))
    eq = [p for p in ps if p.get("type") == "equip_result" and int(p.get("location") or 0) & 2]
    swaps = [(int(p["t_mono_ns"]), names.get(int(p["index"]), str(p["index"]))) for p in eq]
    hits = [p for p in ps if p.get("type") == "act" and p.get("src_gid") == aid
            and int(p.get("damage") or 0) > 0 and p.get("target_gid") != aid]  # fmt: skip
    gains = [int(p["t_mono_ns"]) for p in ps if p.get("type") == "pickup_result"]
    picks = [int(p["t_mono_ns"]) for p in ps if p.get("type") == "pickup_request"]
    main = names.get(-1, "main")
    rows = []
    for tk, gid in kills:
        hk = [
            h
            for h in hits
            if h.get("target_gid") == gid and tk - 60 * NS <= int(h["t_mono_ns"]) <= tk
        ]
        if not hk:
            continue
        t_first = int(hk[0]["t_mono_ns"])
        ws = [weapon_at(swaps, int(h["t_mono_ns"]), start) for h in hk]
        steals = [x for x in gains if t_first <= x <= tk + AFTER_DEATH_S * NS
                  and not any(0 <= x - pr <= PICK_S * NS for pr in picks)]  # fmt: skip
        s0 = steals[0] if steals else None
        back = None
        if s0 is not None:
            back = next(((te - s0) / NS for te, n in swaps if n == main and s0 <= te <= tk), None)
        rows.append({
            "hits": len(hk), "weak_hits": sum(w != main for w in ws),
            "first": ws[0], "last": ws[-1],
            "steal": s0 is not None,
            "weak_hits_before_steal": None if s0 is None else sum(
                1 for h, w in zip(hk, ws, strict=True) if w != main and int(h["t_mono_ns"]) <= s0),
            "steal_to_main_s": None if back is None else round(back, 3),
            "kill_s": round((tk - t_first) / NS, 3),
        })  # fmt: skip
    return rows


def _q(xs: Sequence[float]) -> dict[str, Any]:
    s = sorted(xs)
    if not s:
        return {"n": 0}
    return {
        "n": len(s),
        "median": round(statistics.median(s), 2),
        "p75": round(s[3 * len(s) // 4], 2),
    }


def summary(rows: Sequence[Mapping[str, Any]], main: str) -> dict[str, Any]:
    """PURE: the per-kill rows summed up."""
    fl = Counter(f"{r['first']}->{r['last']}" for r in rows)
    return {
        "kills": len(rows),
        "with_steal": sum(bool(r["steal"]) for r in rows),
        "first_last": dict(fl),
        "steal_to_main_s": _q(
            [r["steal_to_main_s"] for r in rows if r["steal_to_main_s"] is not None]
        ),
        "weak_hits_before_steal": _q(
            [r["weak_hits_before_steal"] for r in rows if r["steal"] and r["first"] != main]
        ),  # fmt: skip
        "hits_per_kill": _q([r["hits"] for r in rows]),
        "weak_hits_per_kill": _q([r["weak_hits"] for r in rows]),
        "kill_s_with_steal": _q([r["kill_s"] for r in rows if r["steal"]]),
        "kill_s_without_steal": _q([r["kill_s"] for r in rows if not r["steal"]]),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("session")
    ap.add_argument("--live", type=float, default=None, help="a human demo: first input .. + S s")
    ap.add_argument("--weak", type=int, default=10, help="the weak weapon's inventory index")
    ap.add_argument("--main", type=int, default=2, help="the main weapon's inventory index")
    ap.add_argument("--start", choices=("main", "weak"), default="main")
    a = ap.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import arm_judge as aj
    import dungeon_judge as dj

    ev, pk, man = dj.load(a.session)
    if a.live is not None:
        t0, t1 = dj.live_window(man, a.live)
    else:
        t0, t1, _src = dj.window(ev, man, pk)
    packets = [p for p in pk if t0 - 5 * NS <= int(p["t_mono_ns"]) <= t1]
    kills = [(t, g) for t, g in aj.kills_of(packets, dj.AID) if t0 <= t <= t1]
    names = {a.weak: "weak", a.main: "main", -1: "main"}
    rows = kill_rows(packets, kills, dj.AID, names, a.start)
    sid = dj.session_dir(a.session).name
    print(json.dumps({"session": sid, "window_s": round((t1 - t0) / NS, 1),
                      "swaps": sum(1 for p in packets if p.get("type") == "equip_result"
                                   and t0 <= int(p["t_mono_ns"]) <= t1),
                      **summary(rows, "main")}, indent=1))  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
