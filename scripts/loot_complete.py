#!/usr/bin/env python3
"""LOOT COMPLETENESS (Batt 2026-10-20, the block's primary): items picked / items dropped by OUR
kills, with the fates split. OFFLINE, packets as ground truth (ADR-0007); nothing here runs during
play.

THE BASE: every kill of ours in the run's window (arm_judge.kills_of: a mob's death vanish <= 1.5 s
after a damaging act of our GM), whatever the bot's engagement made of it -- dead, skipped, given
up, or no engagement at all -- and all its drops (arm_judge.drops_of_kill). The run_row column
"loot picked / dropped" counts only the engagements that ended "dead"; this one does not leave a
real kill out, so a kill the bot walked away from counts as dropped and not picked.

THE FATES (arm_judge.item_fates): picked; left behind (out of our sight: the GM walked > 14 cells
away while the item lay there; the server's 60-s floor lifetime then ends it); looter (a monster
within 1 cell at the vanish); expired (on the floor >= 55 s, in sight); left (still on the floor at
the capture's end); gone (vanished in sight, no monster near).

ABANDONED: a kill of ours whose engagement ended without a loot step (skipped, given up), or that
no engagement owned.

    loot_complete.py runs SID [SID ...]         per run + pooled (JSON)
    loot_complete.py arms SID [SID ...]         per arm (odd k = the fix arm), pooled
    loot_complete.py null SID1 ... SID4n        the arm-difference spread with no change between
                                                the arms: pools of 4 (in the order given) x 5 k
                                                splits (parity + 4 balanced)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

FATES = ("picked", "out_of_sight", "looter", "expired", "left", "gone")
NS = 1_000_000_000
SPLITS: dict[str, Callable[[int], bool]] = {
    "parity": lambda k: k % 2 == 1,
    "mod4 12|30": lambda k: k % 4 in (1, 2),
    "mod4 01|23": lambda k: k % 4 in (0, 1),
    "mod8": lambda k: k % 8 < 4,
    "mod6": lambda k: k % 6 < 3,
}


def owner_of(kill_gid: int, t_kill: int, engs: Sequence[Mapping[str, Any]],
             gid_by_k: Mapping[int, Any]) -> Mapping[str, Any] | None:  # fmt: skip
    """PURE: the engagement whose target was ``kill_gid`` (flow_judge's gid) and whose first click
    came before the kill -- the LAST such one (a target re-engaged after a skip) -- or None."""
    best = None
    for x in engs:
        t_ = int(x["t_first_click"])
        if (gid_by_k.get(int(x["k"])) == kill_gid and t_ <= t_kill
                and (best is None or t_ > int(best["t_first_click"]))):  # fmt: skip
            best = x
    return best


def looted(eng: Mapping[str, Any] | None) -> bool:
    """PURE: did this engagement run a loot step (ended "dead" with a loot record)?"""
    return eng is not None and eng.get("result") == "dead" and bool(eng.get("loot"))


def kill_rows(kills: Sequence[tuple[int, int]], items: Mapping[int, Mapping[str, Any]],
              cell_of: Callable[[int, int], Any], engs: Sequence[Mapping[str, Any]],
              gid_by_k: Mapping[int, Any], t0: int, w1: int) -> list[dict[str, Any]]:  # fmt: skip
    """PURE: one row per kill of ours inside [t0, w1]: its engagement (k, result), whether it was
    looted, and its items' fates."""
    import arm_judge as aj

    out = []
    for t, g in kills:
        if not t0 <= t <= w1:
            continue
        e = owner_of(g, t, engs, gid_by_k)
        fs = [str(items[f]["fate"]) for f in aj.drops_of_kill(items, t, cell_of(g, t - 1))]
        out.append({"t": t, "gid": g, "k": None if e is None else int(e["k"]),
                    "result": None if e is None else e.get("result"),
                    "looted": looted(e), "fates": fs})  # fmt: skip
    return out


def summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """PURE: completeness = picked / dropped, the fates' shares, kills, abandoned kills (and their
    items)."""
    c: Counter[str] = Counter()
    kills = abandoned = ab_items = 0
    for r in rows:
        kills += 1
        c.update(r["fates"])
        if not r["looted"]:
            abandoned += 1
            ab_items += len(r["fates"])
    n = sum(c.values())
    out: dict[str, Any] = {"kills": kills, "items": n, **{f: c[f] for f in FATES}}
    out["completeness"] = round(c["picked"] / n, 4) if n else None
    for f in FATES[1:]:
        out[f"{f}_share"] = round(c[f] / n, 4) if n else None
    out["abandoned_kills"] = abandoned
    out["abandoned_share"] = round(abandoned / kills, 4) if kills else None
    out["abandoned_items"] = ab_items
    return out


def cells(s: Mapping[str, Any]) -> tuple[str, str]:
    """PURE: run_row's two standard cells -- "picked/dropped = C %" and the fates "left behind /
    looters / expired %" with their counts (pooled by summing the counts)."""
    n = max(1, int(s["items"]))
    return (f"{s['picked']}/{s['items']} = {100 * s['picked'] / n:.1f} %",
            f"{100 * s['out_of_sight'] / n:.0f} / {100 * s['looter'] / n:.0f} / "
            f"{100 * s['expired'] / n:.0f} % ({s['out_of_sight']} / {s['looter']} / "
            f"{s['expired']})")  # fmt: skip


def column(s: Mapping[str, Any]) -> str:
    """PURE: the standard column's text: picked/dropped = C % | left behind | looters | expired."""
    n = max(1, int(s["items"]))
    return (f"{s['picked']}/{s['items']} = {100 * s['picked'] / n:.1f} % | left behind "
            f"{100 * s['out_of_sight'] / n:.0f} % | looters {100 * s['looter'] / n:.0f} % | "
            f"expired {100 * s['expired'] / n:.0f} %")  # fmt: skip


def session_rows(sid: str, sess: Any = None) -> list[dict[str, Any]]:
    """The kill rows of one banked session (packets + the bot's events); ``sess`` =
    search_study.load_session(sid) when the caller has it."""
    import arm_judge as aj
    import flow_judge as fj
    import hunt_core as hc
    import search_study as ss

    if sess is None:
        sess = ss.load_session(sid)
    d = aj.DEMO / sid
    try:  # a human demo has no engagements: its kills are all "no engagement"
        engs = json.loads((d / "engagements.json").read_text())
        rows = json.loads((d / "flow_judge.json").read_text())["engagements_w"]["rows"]
    except (OSError, ValueError, KeyError):
        engs, rows = [], []
    pos = hc.walk_positions(sess.events)
    items = aj.item_fates(sess.events, pos, fj.mob_at)
    kills = aj.kills_of(sess.events)
    return kill_rows(kills, items, lambda g, t: fj.mob_at(pos, g, t), engs,
                     {int(r["k"]): r.get("gid") for r in rows}, sess.t0, sess.w1)  # fmt: skip


def arms(rows: Sequence[Mapping[str, Any]], split: Callable[[int], bool] = SPLITS["parity"]
         ) -> dict[str, dict[str, Any]]:  # fmt: skip
    """PURE: per arm ("fix" = split(k) true, "base" = false; kills no engagement owned apart)."""
    return {
        "fix": summary(r for r in rows if r["k"] is not None and split(int(r["k"]))),
        "base": summary(r for r in rows if r["k"] is not None and not split(int(r["k"]))),
        "no_engagement": summary(r for r in rows if r["k"] is None),
    }


def null(by_sid: Mapping[str, Sequence[Mapping[str, Any]]], sids: Sequence[str]
         ) -> dict[str, Any]:  # fmt: skip
    """The fix - base difference with no change between the arms, per 4-run pool and split:
    completeness (points) and abandoned kills (points)."""
    d_c: list[float] = []
    d_a: list[float] = []
    for i in range(0, len(sids) - 3, 4):
        pool = [r for s in sids[i : i + 4] for r in by_sid[s]]
        for f in SPLITS.values():
            a = arms(pool, f)
            if a["fix"]["completeness"] is None or a["base"]["completeness"] is None:
                continue
            d_c.append(100 * (a["fix"]["completeness"] - a["base"]["completeness"]))
            d_a.append(100 * ((a["fix"]["abandoned_share"] or 0)
                              - (a["base"]["abandoned_share"] or 0)))  # fmt: skip
    return {"pools": len(sids) // 4, "n": len(d_c),
            "completeness_points": [round(min(d_c), 1), round(max(d_c), 1)] if d_c else None,
            "abandoned_points": [round(min(d_a), 1), round(max(d_a), 1)] if d_a else None,
            "completeness_all": [round(x, 1) for x in d_c]}  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=("runs", "arms", "null"))
    ap.add_argument("sids", nargs="+")
    a = ap.parse_args()
    by_sid = {s: session_rows(s) for s in a.sids}
    if a.cmd == "runs":
        out: dict[str, Any] = {s: {**summary(r), "column": column(summary(r))}
                               for s, r in by_sid.items()}  # fmt: skip
        allr = [x for r in by_sid.values() for x in r]
        out["pooled"] = {**summary(allr), "column": column(summary(allr))}
    elif a.cmd == "arms":
        out = arms([x for r in by_sid.values() for x in r])
    else:
        out = null(by_sid, a.sids)
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
