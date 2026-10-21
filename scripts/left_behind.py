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
   ⚠️ Under BATT'S RULE (v50/v51 "gm" steps) the step's ``loot.cell`` is still the believed death
   cell, but the rule scans the 5 x 5 around the DRAWN GM; so for those steps 5 and 6 do NOT say
   whether the rule's plan held the item. ``gm_causes`` (below) does (added 2026-10-21 03:10, after
   competition.md's v51 causes had read 5/6 as the rule's plan).

BATT'S RULE'S OWN PLAN (``gm_causes``, only items of kills whose step was a gm step): the plan is
every cell within GM_PLAN of a hover's ``ref`` (the GM's cell the scan used; the hand_hover log),
and each unpicked item gets the first that holds:
  fell_after_step | pickup_refused | clicked_walked   (as above)
  gone_before_hover     its cell was hovered, but only after the item was gone (its fate's time):
                        the race (looters)
  hovered_read_<X>      hovered while it lay there; the first such read was X (hand, empty,
                        unknown, sword, ...)
  planned_not_hovered   within GM_PLAN of a ref, never hovered (the cap, out of view, the end)
  outside_gm_plan[_near_death_cell]   farther than GM_PLAN from every ref (and, on a v53 union
                        step, not in the believed death cell's 3 x 3 the step planned too)
``gm_causes_5x5_by_arm`` (v53, 3.94's P1) classifies the same items against the GM's 5 x 5 ALONE,
as if no union cell were planned or hovered, so both arms are scored on the same fixed region (the
union's plan grows, so ``outside_gm_plan`` in ``gm_causes`` shrinks by bookkeeping alone).
``gm_extra_picked_by_arm`` counts the items picked on a union step's extra cells.
For each such item: its fate (left behind = out of our sight; looter; expired), and, for the left
behind, what took the GM away -- the first non-loot click after the step (``why`` of
clicks.jsonl: search, steer / strike = the next engagement) -- and how long after the step's end
it left our view.

A loot click's result: the first of our self_move_request / pickup_request within 0.6 s after it.

    left_behind.py SID [SID ...]        per run + pooled (JSON); ``causes_by_arm`` splits the causes
                                        by the owning engagement's arm (odd k "fix", even k "base",
                                        no engagement "none"), for interleaved versions
    left_behind.py --edge SID [SID ...] v54 (Batt 2026-10-21 ~16:4x, "if the 5x5 edge turns out to
                                        hold almost nothing live, say so"): the items PICKED by gm
                                        steps' own loot clicks, by ring around the drawn GM's cell
                                        at the step start (the step's first hover ``ref``): own
                                        cell, 3 x 3, the 5 x 5 EDGE (Chebyshev 2), outside -- by
                                        the item's server cell and by the clicked cell; and what
                                        the edge's hovers cost a step (pass 1, scan hovers)
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
from collections.abc import Collection, Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

NS = 1_000_000_000
CLICK_RESULT_S = 0.6
GM_PLAN = 2  # Batt's rule hovers the GM's cell, the 3 x 3 and the 5 x 5's edge (gm_scan_cells)
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


def gm_cause_of(item: Mapping[str, Any], fid: int, step: tuple[int, int],
                refs: Sequence[Sequence[int]], death_cell: Sequence[int] | None,
                results: Sequence[Mapping[str, Any]], hovers: Sequence[Mapping[str, Any]],
                extra_plan: Collection[Sequence[int]] = ()) -> str:  # fmt: skip
    """PURE: the first cause that holds against BATT'S RULE'S OWN plan (module docstring), for an
    unpicked item of a kill whose step was a gm step. ``hovers`` = that step's hand_hover events
    (time order), ``refs`` = their GM cells. ``extra_plan`` (v53, the union plan): the believed
    death cell's 3 x 3 cells outside the GM's 5 x 5 that the step planned too -- in the plan."""
    if int(item["t_fall"]) > step[1]:
        return "fell_after_step"
    cell = tuple(item["cell"])
    if any(r["what"] == "pickup" and r.get("floor_id") == fid and not r.get("ok")
           for r in results):  # fmt: skip
        return "pickup_refused"
    if any(r["what"] == "walk" and tuple(r.get("to") or ()) == cell for r in results):
        return "clicked_walked"
    on = [h for h in hovers if tuple(h["cell"]) == cell]
    if on:
        t_gone = item.get("t_end") or item.get("t_out")
        first = next((h for h in on if t_gone is None or int(h["t_ns"]) < int(t_gone)), None)
        return "gone_before_hover" if first is None else f"hovered_read_{first['seen']}"
    if any(cheb(cell, r_) <= GM_PLAN for r_ in refs) or cell in {tuple(c) for c in extra_plan}:
        return "planned_not_hovered"
    return "outside_gm_plan" + ("_near_death_cell" if death_cell is not None
                                and cheb(cell, death_cell) <= 1 else "")  # fmt: skip


def gm_cause_5x5(item: Mapping[str, Any], fid: int, step: tuple[int, int],
                 refs: Sequence[Sequence[int]], death_cell: Sequence[int] | None,
                 results: Sequence[Mapping[str, Any]],
                 hovers: Sequence[Mapping[str, Any]]) -> str:  # fmt: skip
    """PURE: ``gm_cause_of`` against the GM's 5 x 5 ALONE: no extra plan, and the union's own
    hovers (``union`` true) ignored. The same fixed region for both arms (3.94's P1)."""
    return gm_cause_of(item, fid, step, refs, death_cell, results,
                       [h for h in hovers if not h.get("union")])  # fmt: skip


def skipped_cells(fast_events: Sequence[Mapping[str, Any]], k: int) -> set[tuple[int, int]]:
    """PURE (v54, 3.95's P2): the edge cells engagement ``k``'s passes SKIPPED (the runner's
    ``fast_scan`` events, ``edge_skipped``; every pass of the step, unioned)."""
    return {(int(c[0]), int(c[1])) for e in fast_events if int(e.get("k", -1)) == k
            for c in e.get("edge_skipped") or ()}  # fmt: skip


def lost_on_skipped(cell: Sequence[int], skipped: set[tuple[int, int]]) -> bool:
    """PURE: an unpicked item of ours lay on a cell the fast scan skipped (its cost)."""
    return (int(cell[0]), int(cell[1])) in skipped


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
    evs = [json.loads(x) for x in filter(None, (d / "events.jsonl").read_text().splitlines())]
    hov = [e for e in evs if e.get("kind") == "hand_hover" and e.get("arm") == "gm"]
    hts = [int(h["t_ns"]) for h in hov]
    fsc = [e for e in evs if e.get("kind") == "fast_scan"]  # v54: each pass's skipped edge cells
    fts = [int(e["t_ns"]) for e in fsc]
    gm_c: Counter[str] = Counter()
    gm_arm: Counter[str] = Counter()
    gm_fate: Counter[str] = Counter()
    gm_dist: Counter[int] = Counter()
    gm5_arm: Counter[str] = Counter()  # v53 P1: against the GM's 5 x 5 alone
    gm_extra_picked: Counter[str] = Counter()  # v53: picked on a union step's extra cells
    gm_items_arm: Counter[str] = Counter()  # v54 (3.95's P2): gm-step items per arm
    gm_lost_skip: Counter[str] = Counter()  # v54: never picked, on a cell the fast scan skipped
    gm_items = gm_picked = 0
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
        gm_step = step is not None and lo.get("arm") == "gm" and e is not None
        hs: list[dict[str, Any]] = []
        if gm_step and step is not None and e is not None:
            hs = [h for h in hov[bisect.bisect_left(hts, step[0] - NS):
                                 bisect.bisect_right(hts, step[1] + NS)]
                  if int(h.get("k", -1)) == int(e["k"])]  # fmt: skip
        refs = {tuple(h["ref"]) for h in hs if h.get("ref")}
        extra: set[tuple[int, int]] = set()  # v53: a union step also planned the believed 3 x 3
        if gm_step and lo.get("union") is not None and lo.get("cell"):
            bc_ = (int(lo["cell"][0]), int(lo["cell"][1]))
            near_ = [(bc_[0] + dx, bc_[1] + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
            extra = {c_ for c_ in near_ if all(cheb(c_, r_) > GM_PLAN for r_ in refs)}
        skipped: set[tuple[int, int]] = set()
        if gm_step and step is not None and e is not None:
            lo_i, hi_i = (
                bisect.bisect_left(fts, step[0] - NS),
                bisect.bisect_right(fts, step[1] + NS),
            )
            skipped = skipped_cells(fsc[lo_i:hi_i], int(e["k"]))
        for f in aj.drops_of_kill(items, t_k, dcell):
            it = items[f]
            n_items += 1
            gm_items += gm_step
            if gm_step:
                gm_items_arm[arm_of(e)] += 1
            if it["fate"] == "picked":
                picked += 1
                gm_picked += gm_step
                if gm_step and tuple(it["cell"]) in extra:
                    gm_extra_picked[arm_of(e)] += 1
                continue
            if gm_step and lost_on_skipped(it["cell"], skipped):
                gm_lost_skip[arm_of(e)] += 1
            if gm_step and step is not None:
                res_g = results[
                    bisect.bisect_left(rts, step[0]) : bisect.bisect_right(rts, step[1])
                ]
                c_g = gm_cause_of(it, f, step, sorted(refs), dcell, res_g, hs, extra)
                gm_c[c_g] += 1
                gm_arm[f"{arm_of(e)}|{c_g}"] += 1
                gm_fate[f"{c_g}|{it['fate']}"] += 1
                c5 = gm_cause_5x5(it, f, step, sorted(refs), dcell, res_g, hs)
                gm5_arm[f"{arm_of(e)}|{c5}"] += 1
                if c_g.startswith("outside_gm_plan") and refs:
                    gm_dist[min(cheb(it["cell"], r_) for r_ in refs)] += 1
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
                "p75": s_[3 * len(s_) // 4] if s_ else None},
            "gm_items": gm_items, "gm_picked": gm_picked,
            "gm_causes": dict(gm_c.most_common()), "gm_causes_by_arm": dict(sorted(gm_arm.items())),
            "gm_cause_by_fate": dict(gm_fate.most_common()),
            "gm_causes_5x5_by_arm": dict(sorted(gm5_arm.items())),
            "gm_extra_picked_by_arm": dict(sorted(gm_extra_picked.items())),
            "gm_items_by_arm": dict(sorted(gm_items_arm.items())),
            "gm_lost_on_skipped_by_arm": dict(sorted(gm_lost_skip.items())),
            "gm_outside_cells_from_the_gm": {str(k): v
                                             for k, v in sorted(gm_dist.items())}}  # fmt: skip


def ring_of(cell: Sequence[int], ref: Sequence[int]) -> str:
    """PURE (v54): a cell's ring around the drawn GM's cell ``ref``: "own", "3x3" (Chebyshev 1),
    "edge" (2: the 5 x 5's edge), "outside"."""
    d = cheb(cell, ref)
    return "own" if d == 0 else "3x3" if d == 1 else "edge" if d == 2 else "outside"


PICK_TAIL_S = 2.0  # a pickup request this long after a step's end still belongs to it (a walk)


def ok_pickups(packets: Sequence[Mapping[str, Any]]) -> list[tuple[int, int]]:
    """PURE: [(t of our pickup request, floor_id)] the server answered ok, in time order."""
    out: list[tuple[int, int]] = []
    pend: tuple[int, int] | None = None
    for e in packets:
        if e.get("type") == "pickup_request":
            pend = (int(e["t_mono_ns"]), int(e["floor_id"]))
        elif e.get("type") == "pickup_result" and pend is not None:
            if e.get("ok"):
                out.append(pend)
            pend = None
    return out


def edge_session(sid: str) -> dict[str, Any]:
    """v54's measurement (module docstring, ``--edge``): one session's gm steps. A pick = our
    pickup request the server answered ok, from the step's start to PICK_TAIL_S after its end;
    the clicked cell = the step's last loot click before it; "ours" = it fell for a kill of ours
    (any, not only the step's own)."""
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
    picks = ok_pickups(pk)
    pts = [t for t, _f in picks]
    lclicks = [c for c in clicks if c.get("kind") == "loot"]
    lts = [int(c["t"]) for c in lclicks]
    hov = [e for e in map(json.loads, filter(None, (d / "events.jsonl").read_text().splitlines()))
           if e.get("kind") == "hand_hover" and e.get("arm") == "gm"]  # fmt: skip
    hts = [int(h["t_ns"]) for h in hov]
    kills = [(t, g) for t, g in aj.kills_of(pk) if sess.t0 <= t <= sess.w1]
    ours_all = {f for t, g in aj.kills_of(pk)
                for f in aj.drops_of_kill(items, t, fj.mob_at(pos, g, t - 1))}  # fmt: skip
    by_item: Counter[str] = Counter()
    by_click: Counter[str] = Counter()
    own_kill: Counter[str] = Counter()
    drops_ring: Counter[str] = Counter()
    edge_n: list[int] = []
    edge_ms: list[float] = []
    all_ms: list[float] = []
    steps = kills_gm = 0
    for t_k, g in kills:
        e = lc.owner_of(g, t_k, engs, gid_by_k)
        lo = (e or {}).get("loot") or {}
        if not (lc.looted(e) and e is not None and e.get("t_end") and lo.get("s") is not None
                and lo.get("arm") == "gm"):  # fmt: skip
            continue
        kills_gm += 1
        t_end = int(e["t_end"])
        step = (t_end - int(float(lo["s"]) * NS), t_end)
        hs = [h for h in hov[bisect.bisect_left(hts, step[0] - NS):
                             bisect.bisect_right(hts, step[1] + NS)]
              if int(h.get("k", -1)) == int(e["k"]) and h.get("ref")]  # fmt: skip
        if not hs:
            continue
        steps += 1
        ref0 = tuple(hs[0]["ref"])
        scan1 = [h for h in hs if int(h.get("burst") or 0) == 0 and int(h.get("pass") or 1) == 1]
        eh = [h for h in scan1 if cheb(h["cell"], ref0) == 2]  # the pass's planned edge
        edge_n.append(len(eh))
        edge_ms += [float(h["ms"]) for h in eh if h.get("ms") is not None]
        all_ms += [float(h["ms"]) for h in scan1 if h.get("ms") is not None]
        mine = set(aj.drops_of_kill(items, t_k, fj.mob_at(pos, g, t_k - 1)))
        for f in mine:  # where the step's own kill's drops lay, whatever became of them
            fate_ = "picked" if items[f]["fate"] == "picked" else "not_picked"
            drops_ring[f"{ring_of(items[f]['cell'], ref0)}|{fate_}"] += 1
        # the step's picks: an ok pickup request from the step's start to PICK_TAIL_S after its
        # end (an item 2 cells away is WALKED to first: its request comes after the walk, so
        # ``click_results`` -- the first request within 0.6 s -- calls that click a walk)
        for t_p, f in picks[bisect.bisect_left(pts, step[0]):
                            bisect.bisect_right(pts, step[1] + int(PICK_TAIL_S * NS))]:  # fmt: skip
            if f not in items:
                continue
            tag = "ours" if f in ours_all else "other"
            by_item[f"{tag}|{ring_of(items[f]['cell'], ref0)}"] += 1
            j = bisect.bisect_right(lts, t_p) - 1  # the step's last loot click before it
            if j >= 0 and lclicks[j]["t"] >= step[0] and lclicks[j].get("cell"):
                by_click[f"{tag}|{ring_of(lclicks[j]['cell'], ref0)}"] += 1
            if f in mine:
                own_kill[ring_of(items[f]["cell"], ref0)] += 1
    se = sorted(edge_ms)
    return {"gm_kills": kills_gm, "gm_steps_with_hovers": steps,
            "picked_by_item_cell": dict(sorted(by_item.items())),
            "picked_by_clicked_cell": dict(sorted(by_click.items())),
            "picked_this_kills_items_by_item_cell": dict(sorted(own_kill.items())),
            "this_kills_drops_by_ring_and_fate": dict(sorted(drops_ring.items())),
            "edge_hovers_pass1": sum(edge_n), "edge_hovers_per_step": round(sum(edge_n) / steps, 2)
            if steps else None,
            "edge_hover_ms_p50": se[len(se) // 2] if se else None,
            "edge_hover_ms_mean": round(sum(se) / len(se), 1) if se else None,
            "edge_ms_sum": round(sum(se), 1), "scan_ms_sum": round(sum(all_ms), 1)}  # fmt: skip


def edge_table(per: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """PURE (v54): per run and pooled -- our picked items on the 5 x 5 EDGE vs the 3 x 3 (own cell
    included), per 100 of our picked items and per gm-step kill; the edge's hover seconds a
    step."""
    rows: dict[str, Any] = {}
    tot: Counter[str] = Counter()
    for sid, v in per.items():
        bi = Counter(v["picked_by_item_cell"])
        bc = Counter(v["picked_by_clicked_cell"])
        dr = Counter(v.get("this_kills_drops_by_ring_and_fate") or {})
        c = Counter({"kills": int(v["gm_kills"]), "steps": int(v["gm_steps_with_hovers"]),
                     "drops": sum(dr.values()),
                     "drops_edge": dr["edge|picked"] + dr["edge|not_picked"],
                     "drops_edge_picked": dr["edge|picked"],
                     "edge": bi["ours|edge"], "in3": bi["ours|own"] + bi["ours|3x3"],
                     "out": bi["ours|outside"], "click_edge": bc["ours|edge"],
                     "edge_hovers": int(v["edge_hovers_pass1"]),
                     "edge_ms": int(round(float(v["edge_ms_sum"])))})  # fmt: skip
        tot.update(c)
        rows[sid] = c
    rows["pooled"] = tot
    out: dict[str, Any] = {}
    for k, c in rows.items():
        n = c["edge"] + c["in3"] + c["out"]
        out[k] = {"gm_kills": c["kills"], "ours_picked": n, "on_3x3": c["in3"],
                  "on_edge": c["edge"], "outside_5x5": c["out"],
                  "edge_per_100_items": round(100 * c["edge"] / n, 1) if n else None,
                  "edge_per_kill": round(c["edge"] / c["kills"], 3) if c["kills"] else None,
                  "picked_by_an_edge_click": c["click_edge"],
                  "step_kills_drops": c["drops"], "of_them_on_edge": c["drops_edge"],
                  "of_them_on_edge_picked": c["drops_edge_picked"],
                  "edge_hovers_per_step": round(c["edge_hovers"] / c["steps"], 2)
                  if c["steps"] else None,
                  "edge_hover_s_per_step": round(c["edge_ms"] / 1000 / c["steps"], 2)
                  if c["steps"] else None}  # fmt: skip
    return out


def pooled(per: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """PURE: the runs' counts summed (the time quantiles are not pooled)."""
    out: dict[str, Any] = {"items": 0, "picked": 0, "not_picked": 0}
    for k in ("causes", "causes_by_arm", "cause_by_fate", "left_behind_what_took_the_gm_away",
              "gm_causes", "gm_causes_by_arm", "gm_cause_by_fate", "gm_causes_5x5_by_arm",
              "gm_extra_picked_by_arm", "gm_outside_cells_from_the_gm", "gm_items_by_arm",
              "gm_lost_on_skipped_by_arm"):  # fmt: skip
        c: Counter[str] = Counter()
        for v in per.values():
            c.update(v.get(k) or {})
        out[k] = dict(c.most_common())
    for v in per.values():
        for k in ("items", "picked", "not_picked", "gm_items", "gm_picked"):
            out[k] = out.get(k, 0) + int(v.get(k) or 0)
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
    ap.add_argument("--edge", action="store_true")
    ap.add_argument("sids", nargs="+")
    a = ap.parse_args()
    if a.edge:
        per_e = {s: edge_session(s) for s in a.sids}
        print(json.dumps({"per_run": per_e, "table": edge_table(per_e)}, indent=1))
        return 0
    if a.aim:
        print(json.dumps(aim(a.sids), indent=1))
        return 0
    per = {s: session(s) for s in a.sids}
    print(json.dumps({**per, "pooled": pooled(per)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
