#!/usr/bin/env python3
"""WHY ITEMS ARE LEFT BEHIND (Batt 2026-10-20, the loot block's step 3: "find out first why items
are left behind today -- loot step ending early vs the next engagement pulling the GM away").
OFFLINE, packets as ground truth (ADR-0007); nothing here runs during play.

Every item dropped by a kill of ours (loot_complete.py's base) that was NOT picked gets ONE cause,
the first that holds:
1. ``no_loot_step``      its kill's engagement ran no loot step (skipped, given up, none owned it);
2. ``fell_after_step``   it fell after its kill's loot step had ended;
3. ``pickup_refused``    a loot click became a pickup request for it and the server said no;
4. ``clicked_walked``    a loot click aimed at its cell and became a WALK there (no pickup): the
                         click's pixel hit the ground, not the item;
5. ``in_plan_unclicked`` its cell lies in the step's 3 x 3 (around the step's loot cell) but no
                         click went to it (skipped: a unit, pink, the view; or the step's cap);
6. ``outside_plan``      its cell lies outside that 3 x 3 (``near_death_cell``: within 1 cell of
                         the server's death cell, i.e. the bot's death cell was off).
For each such item: its fate (left behind = out of our sight; looter; expired), and, for the left
behind, what took the GM away -- the first non-loot click after the step (``why`` of
clicks.jsonl: search, steer / strike = the next engagement) -- and how long after the step's end
it left our view.

A loot click's result: the first of our self_move_request / pickup_request within 0.6 s after it.

    left_behind.py SID [SID ...]        per run + pooled (JSON); ``causes_by_arm`` splits the causes
                                        by the owning engagement's arm (odd k "fix", even k "base",
                                        no engagement "none"), for interleaved versions
    left_behind.py --aim SID [SID ...]  where the LOOT CLICKS land: each click that became a walk,
                                        its walk request's cell against the cell the runner aimed
                                        at (clicks.jsonl "cell"), split by the step's first click /
                                        later ones and by our GM moving (packets) at the click
"""

from __future__ import annotations

import argparse
import bisect
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

NS = 1_000_000_000
CLICK_RESULT_S = 0.6
CAUSES = ("no_loot_step", "fell_after_step", "pickup_refused", "clicked_walked",
          "in_plan_unclicked", "outside_plan")  # fmt: skip


def cheb(a: Sequence[int], b: Sequence[int]) -> int:
    return max(abs(int(a[0]) - int(b[0])), abs(int(a[1]) - int(b[1])))


def click_results(clicks: Sequence[Mapping[str, Any]], packets: Sequence[Mapping[str, Any]]
                  ) -> list[dict[str, Any]]:  # fmt: skip
    """PURE: each LOOT click with what it became: ("walk", cell) / ("pickup", floor_id, ok) /
    ("none",) -- the first of our move / pickup requests within CLICK_RESULT_S after it."""
    reqs = [e for e in packets if e.get("type") in ("self_move_request", "pickup_request",
                                                    "pickup_result")]  # fmt: skip
    ts = [int(e["t_mono_ns"]) for e in reqs]
    out = []
    for c in clicks:
        if c.get("kind") != "loot":
            continue
        t = int(c["t"])
        i = bisect.bisect_right(ts, t)
        res: dict[str, Any] = {"t": t, "cell": tuple(c.get("cell") or ()), "what": "none"}
        while i < len(reqs) and ts[i] <= t + int(CLICK_RESULT_S * NS):
            e = reqs[i]
            if e["type"] == "self_move_request":
                res.update(what="walk", to=(int(e["x"]), int(e["y"])))
                break
            if e["type"] == "pickup_request":
                ok = next((bool(r.get("ok")) for r in reqs[i + 1 : i + 4]
                           if r["type"] == "pickup_result"), False)  # fmt: skip
                res.update(what="pickup", floor_id=int(e["floor_id"]), ok=ok)
                break
            i += 1
        out.append(res)
    return out


def arm_of(eng: Mapping[str, Any] | None) -> str:
    """PURE: the interleaved arm of the engagement that owned a kill -- odd k "fix", even k
    "base", no owner "none"."""
    if eng is None:
        return "none"
    return "fix" if int(eng["k"]) % 2 == 1 else "base"


def cause_of(item: Mapping[str, Any], fid: int, looted: bool, step: tuple[int, int] | None,
             step_cell: Sequence[int] | None, death_cell: Sequence[int] | None,
             results: Sequence[Mapping[str, Any]]) -> str:  # fmt: skip
    """PURE: the first cause that holds (module docstring), for an item that was not picked.
    ``step`` = the loot step's (start, end) ns; ``results`` = click_results inside it."""
    if not looted or step is None or step_cell is None:
        return "no_loot_step"
    if int(item["t_fall"]) > step[1]:
        return "fell_after_step"
    cell = tuple(item["cell"])
    if any(r["what"] == "pickup" and r.get("floor_id") == fid and not r.get("ok")
           for r in results):  # fmt: skip
        return "pickup_refused"
    if any(r["what"] == "walk" and tuple(r.get("to") or ()) == cell for r in results):
        return "clicked_walked"
    if cheb(cell, step_cell) <= 1:
        return "in_plan_unclicked"
    return "outside_plan" + ("_near_death_cell" if death_cell is not None
                             and cheb(cell, death_cell) <= 1 else "")  # fmt: skip


def session(sid: str) -> dict[str, Any]:
    import arm_judge as aj
    import flow_judge as fj
    import hunt_core as hc
    import loot_complete as lc
    import search_study as ss

    sess = ss.load_session(sid)
    d = aj.DEMO / sid
    engs = json.loads((d / "engagements.json").read_text())
    rows = json.loads((d / "flow_judge.json").read_text())["engagements_w"]["rows"]
    gid_by_k = {int(r["k"]): r.get("gid") for r in rows}
    clicks = sorted((json.loads(x) for x in (d / "clicks.jsonl").read_text().splitlines() if x),
                    key=lambda c: int(c["t"]))  # fmt: skip
    pk = sess.events
    pos = hc.walk_positions(pk)
    items = aj.item_fates(pk, pos, fj.mob_at)
    results = click_results(clicks, pk)
    rts = [r["t"] for r in results]
    cts = [int(c["t"]) for c in clicks]
    causes: Counter[str] = Counter()
    by_arm: Counter[str] = Counter()
    by_fate: Counter[str] = Counter()
    away: Counter[str] = Counter()
    out_after: list[float] = []
    picked = n_items = 0
    for t_k, g in aj.kills_of(pk):
        if not sess.t0 <= t_k <= sess.w1:
            continue
        e = lc.owner_of(g, t_k, engs, gid_by_k)
        looted = lc.looted(e)
        lo = (e or {}).get("loot") or {}
        step = None
        if looted and e is not None and e.get("t_end") and lo.get("s") is not None:
            t_end = int(e["t_end"])
            step = (t_end - int(float(lo["s"]) * NS), t_end)
        dcell = fj.mob_at(pos, g, t_k - 1)
        for f in aj.drops_of_kill(items, t_k, dcell):
            it = items[f]
            n_items += 1
            if it["fate"] == "picked":
                picked += 1
                continue
            res = [] if step is None else results[bisect.bisect_left(rts, step[0]):
                                                  bisect.bisect_right(rts, step[1])]  # fmt: skip
            c = cause_of(it, f, looted, step, lo.get("cell"), dcell, res)
            causes[c] += 1
            by_arm[f"{arm_of(e)}|{c}"] += 1
            by_fate[f"{c}|{it['fate']}"] += 1
            if it["fate"] == "out_of_sight" and step is not None and it.get("t_out"):
                out_after.append((int(it["t_out"]) - step[1]) / NS)
                j = bisect.bisect_right(cts, step[1])
                nxt = next((cc for cc in clicks[j:] if cc.get("kind") != "loot"
                            and int(cc["t"]) <= int(it["t_out"])), None)  # fmt: skip
                away[str((nxt or {}).get("why") or "no click before it left our view")] += 1
    s_ = sorted(out_after)
    return {"items": n_items, "picked": picked, "not_picked": sum(causes.values()),
            "causes": dict(causes.most_common()), "causes_by_arm": dict(sorted(by_arm.items())),
            "cause_by_fate": dict(by_fate.most_common()),
            "left_behind_what_took_the_gm_away": dict(away.most_common()),
            "left_our_view_after_step_end_s": {
                "n": len(s_), "p25": s_[len(s_) // 4] if s_ else None,
                "p50": s_[len(s_) // 2] if s_ else None,
                "p75": s_[3 * len(s_) // 4] if s_ else None}}  # fmt: skip


def pooled(per: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """PURE: the runs' counts summed (the time quantiles are not pooled)."""
    out: dict[str, Any] = {"items": 0, "picked": 0, "not_picked": 0}
    for k in ("causes", "causes_by_arm", "cause_by_fate", "left_behind_what_took_the_gm_away"):
        c: Counter[str] = Counter()
        for v in per.values():
            c.update(v[k])
        out[k] = dict(c.most_common())
    for v in per.values():
        for k in ("items", "picked", "not_picked"):
            out[k] += v[k]
    return out


def aim(sids: Sequence[str]) -> dict[str, Any]:
    """Loot clicks that became walks: exact / <= 1 cell from the aimed cell, by group."""
    import gzip

    import arm_judge as aj
    import flow_judge as fj

    agg: dict[str, Counter[str]] = {}
    for sid in sids:
        d = aj.DEMO / sid
        clicks = sorted((json.loads(x) for x in (d / "clicks.jsonl").read_text().splitlines()
                         if x), key=lambda c: int(c["t"]))  # fmt: skip
        with gzip.open(d / "packets.jsonl.gz", "rt") as fh:
            pk = sorted((json.loads(x) for x in fh), key=lambda e: int(e["t_mono_ns"]))
        moving = fj.gm_track(pk)[1]
        mv0 = [a_ for a_, _b in moving]
        res = click_results(clicks, pk)
        prev = None
        for r in res:
            first = prev is None or r["t"] - prev > int(1.5 * NS)  # the step's first click
            prev = r["t"]
            if r["what"] != "walk" or not r["cell"]:
                continue
            i = bisect.bisect_right(mv0, r["t"]) - 1
            mv = i >= 0 and moving[i][0] <= r["t"] <= moving[i][1]
            e = cheb(r["to"], r["cell"])
            for g in ("all", "first click of a step" if first else "later clicks",
                      "GM moving" if mv else "GM standing"):  # fmt: skip
                c = agg.setdefault(g, Counter())
                c["n"] += 1
                c["exact"] += e == 0
                c["within1"] += e <= 1
    return {g: {"n": c["n"], "exact": round(c["exact"] / c["n"], 3),
                "within1": round(c["within1"] / c["n"], 3)} for g, c in agg.items()}  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--aim", action="store_true")
    ap.add_argument("sids", nargs="+")
    a = ap.parse_args()
    if a.aim:
        print(json.dumps(aim(a.sids), indent=1))
        return 0
    per = {s: session(s) for s in a.sids}
    print(json.dumps({**per, "pooled": pooled(per)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
