#!/usr/bin/env python3
"""THE IDLE STUDY (2026-10-26, docs/planning/gef10-idle-study.md): WHAT the runner was doing in the
idle seconds that scripts/time_budget.py finds in dungeon_hunt's gef_fild10 runs. Offline only:
it reads banked session files, and nothing here reaches a runner. The packets are the server's
truth, used offline only (ADR-0007); the runner's events are its own decisions.

    idle_study.py SID [SID ...] [--json]     per session and pooled: seconds per kill per mechanism

THE JOIN. time_budget.analyse labels every instant of a run's window from the PACKETS (its
docstring is the definition of record); an IDLE stretch carries its context (inside_search,
loot_pause, after_fight, ...). This tool cuts every stretch of the studied causes (FOCUS) by the
runner's own activity spans, built from its events.jsonl (t_ns, the host CLOCK_MONOTONIC: the
packets' clock). Each instant takes the FIRST mechanism of MECHS whose spans cover it, else
"other". The code that makes each span (dungeon_hunt.py, dungeon@8.3 / 9.x):

- loot_pick_wait: a loot click's coded sleep, ``time.sleep(0.45 + 0.2 * d_)`` after
  ``click_at(u, v, "loot")`` (loot_step_v1.visit; d_ = the item's Chebyshev distance), from the
  loot_click event, inside its loot step;
- strike: ``strike()``, t_ns .. t_end_ns (the burst until the lock arrow, our damage, or 3 s);
- fly_settle: a Fly Wing (press "fly") until the next position read: the loop's
  ``time.sleep(1.0)`` and FLY_SETTLE_S (2.5 s: no position read after a Fly Wing, so no walk);
  capped at FLY_MAX_S;
- loot_list_hover / loot_sweep_hover: ``loot_step_v1`` (the run's ``--loot v1``): its LOOT LIST
  (the 5 x 5 around our cell at every kill of the fight, nearest first, up to LOOT_MAX_HOVERS =
  30 hovers or LOOT_MAX_S = 25 s), then its SWEEP (up to SWEEP_MAX = 10 cells that changed since
  the fight began). Each hover is ``cursor_sword.check`` with ``wait_s`` = CURSOR_WAIT_S (0.35 s)
  plus the no-entry crop; the step is logged at its END with ``ms``. The list / sweep boundary is
  the list_hovered-th guard_tick read (one ``hp_read quick`` follows every hover), else a
  proportional split;
- stall_scan: the stall branch's ``scan("defend", ring(1), "sword")`` (two walk clicks from one
  cell without moving);
- scan_found / scan_empty_after_kill / scan_empty_no_kill: the fight loop's
  ``scan("defend", ring(1))`` then ``ring(2)`` while hits still come (8 + 16 hovers), logged at
  its end with ``ms``; split by its verdict, and an empty one by whether its fight (engage ..
  fight_end) had already logged a kill (after a kill the lock is gone, so the loop scans again
  until the quiet-kill exit -- no hit for FIGHT_TAKEN_S = 2.5 s and the kill < 3 s old -- or an
  empty scan with no hit for 2.5 s ends the fight);
- patrol_dead_end: ``goal`` events with no route (len None): the patrol skips every waypoint on
  every tick (``skip_waypoint``) while no route leaves our cell, until the IDLE_MAX_S (45 s)
  watchdog's Fly Wing or a fight;
- walk_decision: the tick that ends in a walk event: from its hp_read (the tick's first record)
  to the walk event (``route()`` from our cell, ``walk_target``, the 0.35-s cursor read,
  ``walk_trust.trust_why``, ``click_at``'s paced moves and click);
- ui_watch: a tick longer than UI_TICK_S that logged nothing but its hp_read (the UI_EVERY_S =
  10 s ``f0.client_state`` + the weight read, outside a fight);
- fight_other: the rest of a fight (engage .. fight_end / Fly Wing): lock waits, the 5 Hz loop;
- walk_timer: from a walk event to the next walk decision, at most WALK_TIMER_S: the loop waits
  for WALK_EVERY_S (1.2 s from the previous decision's START) between clicks;
- other: everything else.

THE WALK CADENCE (packets + events): per clicked walk, our self_move path (cells), its moving span,
and the stop until the next self_move; the share of walk clicks capped at the patrol goal (the
waypoint itself: the leg ends there, WP_TOL = 2).

THE LOOT STEPS (events): per step, its seconds, picks, the hover rank of each pick (guard_tick
reads before its click), and the seconds after its last pick (the fruitless tail); and the
TRIM rule's ESTIMATE: the step stops after TRIM_HOVERS hovers and never sweeps -- the seconds
saved and the picks lost, from the measured hover times.
"""

from __future__ import annotations

import argparse
import bisect
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

NS = 1_000_000_000
MS = 1_000_000
Span = tuple[int, int]
Seg = tuple[int, int, str]

PICK_S, PICK_CELL_S = 0.45, 0.2  # dungeon_hunt loot_step_v1.visit: sleep(0.45 + 0.2 * d_)
FLY_MAX_S = 10.0  # a Fly Wing's settle span is capped at this
DEAD_END_GAP_S = 1.5  # route-less goal events this close together form one dead-end span
TICK_S = 0.2  # 1 / READ_HZ
UI_TICK_S = 0.6  # a tick this long that logged nothing else = the UI watch
WALK_DECISION_MAX_S = 2.5  # a walk decision span is capped at this (a stray tick start)
WALK_TIMER_S = 3.0  # a walk event to the next decision, at most this long = waiting for it
SHORT_STOP_S = 2.5  # a stop after a walk shorter than this = stop-and-go (not a fight, a loot)
TRIM_HOVERS = 9  # the TRIM rule: a loot step's hovers (our cell + ring 1: the first nine)
# the TRIM rules estimated: (hovers, per kill); 30 = the list as now, without the sweep
TRIMS = ((5, False), (9, False), (12, False), (16, False), (30, False),
         (9, True))  # fmt: skip
PROPOSAL = "9"  # the proposal's rule (trim_cut 9 hovers, no sweep)
EXTEND = (3, 5, 7)  # walk legs longer by this many cells: the stop-and-go estimate
WALK_S_CELL = 0.15  # dungeon_hunt WALK_S_PER_CELL: our walk, seconds per cell
FOCUS = ("idle_inside_search", "idle_loot_pause", "idle_after_fight")
MECHS = ("loot_pick_wait", "strike", "fly_settle", "loot_list_hover", "loot_sweep_hover",
         "stall_scan", "scan_found", "scan_empty_after_kill", "scan_empty_no_kill",
         "patrol_dead_end", "walk_decision", "ui_watch", "fight_other",
         "walk_timer")  # fmt: skip
ALL = (*MECHS, "other")


def _t(e: Mapping[str, Any]) -> int:
    return int(e.get("t_ns") or 0)


def _q(xs: Sequence[float], q: float) -> float | None:
    """PURE: the q-quantile (linear between ranks; None when empty)."""
    if not xs:
        return None
    s = sorted(xs)
    k = q * (len(s) - 1)
    i = int(k)
    return round(s[i] + (s[min(i + 1, len(s) - 1)] - s[i]) * (k - i), 3)


def merge(spans: Iterable[Span]) -> list[Span]:
    """PURE: the union of ``spans`` as sorted, disjoint spans (empty ones dropped)."""
    out: list[Span] = []
    for a, b in sorted(s for s in spans if s[1] > s[0]):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


# --- the runner's own timeline -----------------------------------------------------------------


def ticks(events: Sequence[Mapping[str, Any]]) -> list[int]:
    """PURE: the main loop's tick starts: every non-quick hp_read (the tick's first record; a
    guard_tick read inside a long action is ``quick``)."""
    return sorted(_t(e) for e in events if e.get("kind") == "hp_read" and not e.get("quick"))


def quick_reads(events: Sequence[Mapping[str, Any]]) -> list[int]:
    """PURE: the guard_tick reads (``hp_read`` with ``quick``): one after every hover of a scan or
    a loot step (a hover lasts >= QUICK_S)."""
    return sorted(_t(e) for e in events if e.get("kind") == "hp_read" and e.get("quick"))


def fights(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """PURE: the runner's fights: an engage (with its ``by``) until fight_end, a Fly Wing, or the
    next engage; with the kills logged inside."""
    out: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for e in sorted(events, key=_t):
        k, t = e.get("kind"), _t(e)
        if k == "engage":
            if cur is not None:
                cur["t1"] = t
                out.append(cur)
            cur = {"t0": t, "t1": None, "by": e.get("by"), "kills": []}
        elif cur is not None and (k == "fight_end"
                                  or (k == "press" and e.get("what") == "fly")):  # fmt: skip
            cur["t1"] = t
            out.append(cur)
            cur = None
        elif cur is not None and k == "kill":
            cur["kills"].append(t)
    if cur is not None:
        out.append(cur)
    return out


def loot_steps(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """PURE: each loot step (logged at its END with ``ms``): its span, its counts, the first strike
    inside it (a SWORD under a hover: ``end`` "fight"), its HOVER reads (the guard_tick reads
    before that strike: one per hover), its loot clicks (time, distance d, why) with each one's
    hover RANK (the hover reads up to its click, its own hover included) and pick wait, and the
    list / sweep time boundary."""
    q = quick_reads(events)
    clicks = sorted((e for e in events if e.get("kind") == "loot_click"), key=_t)
    ct = [_t(e) for e in clicks]
    strikes = sorted(_t(e) for e in events if e.get("kind") == "strike")
    out = []
    for e in events:
        if e.get("kind") != "loot_step" or e.get("ms") is None:
            continue
        b = _t(e)
        a = b - int(e["ms"]) * MS
        i = bisect.bisect_left(strikes, a)
        ts = strikes[i] if i < len(strikes) and strikes[i] <= b else None
        reads = q[bisect.bisect_left(q, a) : bisect.bisect_right(q, ts if ts is not None else b)]
        picks = []
        for c in clicks[bisect.bisect_left(ct, a) : bisect.bisect_right(ct, b)]:
            rel = c.get("rel") or (0, 0)
            d = max(abs(int(rel[0])), abs(int(rel[1])))
            tc = _t(c)
            w1 = min(b, tc + int((PICK_S + PICK_CELL_S * d) * NS))
            picks.append({"t": tc, "d": d, "why": c.get("why"),
                          "rank": bisect.bisect_right(reads, tc), "wait": (tc, w1)})  # fmt: skip
        n_list = int(e.get("list_hovered") or 0)
        n_sweep = int(e.get("sweep_hovered") or 0)
        if n_sweep <= 0:
            cut = b
        elif len(reads) >= n_list > 0:
            cut = reads[n_list - 1]
        else:
            n = max(1, n_list + n_sweep)
            cut = a + (b - a) * n_list // n
        last = max((p["wait"][1] for p in picks), default=a)
        out.append({"t0": a, "t1": b, "s": (b - a) / NS, "end": e.get("end"), "strike": ts,
                    "hovered": int(e.get("hovered") or 0), "list_hovered": n_list,
                    "sweep_hovered": n_sweep, "picks": picks, "reads": reads, "cut": cut,
                    "tail_s": (b - last) / NS,
                    "kills": int(e.get("list_kills") or 0)})  # fmt: skip
    return out


def trim_cut(step: Mapping[str, Any], trim: int, per_kill: bool = False
             ) -> tuple[Span | None, int, bool]:  # fmt: skip
    """PURE (an ESTIMATE): one loot step under the TRIM rule -- it stops after ``trim`` hovers
    (``trim`` per kill of its list with ``per_kill``), never more than its LIST made (it never
    sweeps: a step whose fight logged no kill, with an empty list, makes none); the hover order is
    unchanged (v1: nearest our cell first), so its first hovers are the measured ones. Returns
    (the span it would NOT spend: from the end of its last kept hover, or of a kept pick's wait,
    to its end -- or to its strike when a SWORD came later than the kept hovers; None when
    unchanged), the picks it would lose, and whether a SWORD it found came only after the kept
    hovers (that monster is left to the other triggers)."""
    reads = step["reads"]
    keep = min(trim * step["kills"] if per_kill else trim, step["list_hovered"])
    if len(reads) <= keep:
        return None, 0, False
    stop = reads[keep - 1] if keep > 0 else step["t0"]
    for p in step["picks"]:
        if p["rank"] <= keep:
            stop = max(stop, p["wait"][1])
    end = step["strike"] if step["strike"] is not None else step["t1"]
    lost = sum(1 for p in step["picks"] if p["rank"] > keep)
    return ((stop, end) if end > stop else None), lost, step["strike"] is not None


def mech_spans(events: Sequence[Mapping[str, Any]], t1: int | None = None
               ) -> dict[str, list[Span]]:  # fmt: skip
    """PURE: each MECHS mechanism's spans from the runner's events (the module docstring says
    which code makes each one); ``t1`` closes a fight still open at the window's end."""
    ev = sorted(events, key=_t)
    end = t1 if t1 is not None else (_t(ev[-1]) if ev else 0)
    tk = ticks(ev)
    out: dict[str, list[Span]] = defaultdict(list)
    for st in loot_steps(ev):
        out["loot_pick_wait"] += [p["wait"] for p in st["picks"]]
        out["loot_list_hover"].append((st["t0"], st["cut"]))
        out["loot_sweep_hover"].append((st["cut"], st["t1"]))
    fts = fights(ev)
    f0 = [f["t0"] for f in fts]
    stall_t = [_t(e) for e in ev if e.get("kind") == "stall"]
    for e in ev:
        k, t = e.get("kind"), _t(e)
        if k == "strike" and e.get("t_end_ns"):
            out["strike"].append((t, int(e["t_end_ns"])))
        elif k == "scan" and e.get("purpose") == "defend" and e.get("ms") is not None:
            a = t - int(e["ms"]) * MS
            i = bisect.bisect_right(stall_t, a + 50 * MS) - 1
            if i >= 0 and a - stall_t[i] <= 0.5 * NS:
                out["stall_scan"].append((a, t))
                continue
            if e.get("found") is not None:
                out["scan_found"].append((a, t))
                continue
            j = bisect.bisect_right(f0, a) - 1
            f = fts[j] if j >= 0 and (fts[j]["t1"] is None or fts[j]["t1"] >= a) else None
            after = f is not None and any(x <= a for x in f["kills"])
            out["scan_empty_after_kill" if after else "scan_empty_no_kill"].append((a, t))
        elif k == "press" and e.get("what") == "fly":
            nxt = next((_t(x) for x in ev if _t(x) > t + 100 * MS and x.get("kind") == "hp_read"
                        and not x.get("quick") and x.get("pos") is not None), None)  # fmt: skip
            out["fly_settle"].append((t, min(nxt or end, t + int(FLY_MAX_S * NS))))
        elif k == "walk":
            i = bisect.bisect_right(tk, t) - 1
            a = tk[i] if i >= 0 else t
            out["walk_decision"].append((max(a, t - int(WALK_DECISION_MAX_S * NS)), t))
    dead = sorted(_t(e) for e in ev if e.get("kind") == "goal" and e.get("len") is None)
    run: list[int] = []
    for t in dead:
        if run and t - run[-1] > DEAD_END_GAP_S * NS:
            out["patrol_dead_end"].append((run[0], run[-1] + int(TICK_S * NS)))
            run = []
        run.append(t)
    if run:
        out["patrol_dead_end"].append((run[0], run[-1] + int(TICK_S * NS)))
    busy = {"hp_read", "weight"}
    et = [(t_, e.get("kind")) for e in ev for t_ in (_t(e),)]
    ets = [x[0] for x in et]
    for a, b in zip(tk, tk[1:], strict=False):
        if b - a <= UI_TICK_S * NS:
            continue
        inside = et[bisect.bisect_right(ets, a) : bisect.bisect_left(ets, b)]
        if all(k in busy for _t_, k in inside):
            out["ui_watch"].append((a, b))
    out["fight_other"] = [(f["t0"], f["t1"] if f["t1"] is not None else end) for f in fts]
    walks = sorted(_t(e) for e in ev if e.get("kind") == "walk")
    starts = sorted(s[0] for s in out["walk_decision"])
    for t in walks:
        j = bisect.bisect_right(starts, t)
        nxt = starts[j] if j < len(starts) else t + int(WALK_TIMER_S * NS)
        out["walk_timer"].append((t, min(nxt, t + int(WALK_TIMER_S * NS))))
    return {m: merge(out.get(m, [])) for m in MECHS}


def attribute(segs: Sequence[Seg], causes: Sequence[str], spans: Mapping[str, Sequence[Span]],
              keep: Iterable[str] | None = None, order: Sequence[str] = MECHS
              ) -> dict[str, dict[str, dict[str, float]]]:  # fmt: skip
    """PURE: per cause (only ``keep``'s, when given), per mechanism: the seconds of its segments
    covered by that mechanism -- the FIRST of ``order`` whose (sorted, disjoint) spans cover the
    instant, else "other" -- and ``n``, the number of that mechanism's spans that took any of it.
    Every second of a kept segment lands in exactly one mechanism."""
    keep_ = None if keep is None else set(keep)
    st = {m: [s[0] for s in spans.get(m, ())] for m in order}
    secs: dict[str, dict[str, float]] = {}
    hits: dict[str, dict[str, set[int]]] = {}
    for (a, b, _c), k in zip(segs, causes, strict=True):
        if keep_ is not None and k not in keep_:
            continue
        s_ = secs.setdefault(k, dict.fromkeys((*order, "other"), 0.0))
        h_ = hits.setdefault(k, {m: set() for m in (*order, "other")})
        rem = [(a, b)]
        for m in order:
            sp = spans.get(m, ())
            nxt: list[Span] = []
            for x, y in rem:
                i = max(0, bisect.bisect_right(st[m], x) - 1)
                cur = x
                while i < len(sp) and sp[i][0] < y:
                    p, r = sp[i]
                    if r > cur and p < y:
                        lo, hi = max(p, cur), min(r, y)
                        if hi > lo:
                            if lo > cur:
                                nxt.append((cur, lo))
                            s_[m] += (hi - lo) / NS
                            h_[m].add(i)
                            cur = hi
                    i += 1
                if cur < y:
                    nxt.append((cur, y))
            rem = nxt
        for x, y in rem:
            s_["other"] += (y - x) / NS
            h_["other"].add(len(h_["other"]))
    return {k: {m: {"s": round(v, 2), "n": len(hits[k][m])} for m, v in d.items()}
            for k, d in secs.items()}  # fmt: skip


# --- the walk cadence and the loot steps --------------------------------------------------------


def walk_cadence(packets: Sequence[Mapping[str, Any]], events: Sequence[Mapping[str, Any]],
                 t0: int, t1: int, segs: Sequence[Seg] = (), causes: Sequence[str] = (),
                 extend: Sequence[int] = EXTEND) -> dict[str, Any]:  # fmt: skip
    """PURE (packets offline): our self_move paths in [t0, t1] (cells, moving seconds), the stops
    between one move's end and the next move (by the cause in force there, when ``segs`` are
    given), the runner's clicked walks (their interval; the share whose target IS the patrol goal,
    so the leg ends at the waypoint), and the ESTIMATE of legs longer by ``extend`` cells: every
    stop-and-go stop inside search (< SHORT_STOP_S) shrinks by up to extend x WALK_S_CELL."""
    import flow_judge as fj

    moves = [((int(e["x0"]), int(e["y0"])), (int(e["x1"]), int(e["y1"])), int(e["t_mono_ns"]))
             for e in packets if e.get("type") == "self_move"
             and t0 <= int(e["t_mono_ns"]) <= t1]  # fmt: skip
    cells = [max(abs(a[0] - b[0]), abs(a[1] - b[1])) for a, b, _t_ in moves]
    _pts, moving = fj.gm_track(packets)
    mv = [(a, b) for a, b in moving if t0 <= a <= t1]
    starts = [s[0] for s in segs]
    stops: dict[str, list[float]] = defaultdict(list)
    for (_a, b), (c, _d) in zip(mv, mv[1:], strict=False):
        if c <= b:
            continue
        i = bisect.bisect_right(starts, b) - 1
        k = causes[i] if segs and 0 <= i < len(causes) else "any"
        stops[k].append((c - b) / NS)
    goal: tuple[int, int] | None = None
    clicked, capped, short = [], 0, 0
    for e in sorted(events, key=_t):
        if _t(e) > t1:
            break
        if e.get("kind") == "goal" and e.get("len") is not None and e.get("to"):
            goal = (int(e["to"][0]), int(e["to"][1]))
        elif e.get("kind") == "walk" and e.get("clicked") and _t(e) >= t0:
            clicked.append(_t(e))
            to = (int(e["to"][0]), int(e["to"][1]))
            fr = (int(e["from"][0]), int(e["from"][1]))
            capped += to == goal
            short += max(abs(to[0] - fr[0]), abs(to[1] - fr[1])) < 7
    gaps = [(b - a) / NS for a, b in zip(clicked, clicked[1:], strict=False) if b - a <= 10 * NS]
    iss = stops.get("idle_inside_search", [])
    sh = [x for x in iss if x < SHORT_STOP_S]
    return {"self_moves": len(moves), "path_cells_median": _q(cells, 0.5),
            "moving_s_median": _q([(b - a) / NS for a, b in mv], 0.5),
            "walk_clicks": len(clicked), "click_gap_s_median": _q(gaps, 0.5),
            "target_is_goal_share": round(capped / len(clicked), 3) if clicked else None,
            "target_under_7_share": round(short / len(clicked), 3) if clicked else None,
            "stops_inside_search": {"n": len(iss), "s": round(sum(iss), 1),
                                    "median_s": _q(iss, 0.5), "short_n": len(sh),
                                    "short_s": round(sum(sh), 1)},
            "extend_saved_s": {str(k): round(sum(min(x, k * WALK_S_CELL) for x in sh), 1)
                               for k in extend},
            "stops_by_cause_s": {k: round(sum(v), 1)
                                 for k, v in sorted(stops.items())}}  # fmt: skip


def by_cause(spans: Sequence[Span], segs: Sequence[Seg], causes: Sequence[str]
             ) -> dict[str, float]:  # fmt: skip
    """PURE: the seconds of ``spans`` (sorted, disjoint) inside each cause's segments."""
    out: dict[str, float] = defaultdict(float)
    st = [s[0] for s in segs]
    for a, b in spans:
        i = max(0, bisect.bisect_right(st, a) - 1)
        while i < len(segs) and segs[i][0] < b:
            lo, hi = max(a, segs[i][0]), min(b, segs[i][1])
            if hi > lo:
                out[causes[i]] += (hi - lo) / NS
            i += 1
    return {k: round(v, 1) for k, v in sorted(out.items())}


def loot_summary(steps: Sequence[Mapping[str, Any]], trims: Sequence[tuple[int, bool]] = TRIMS
                 ) -> dict[str, Any]:  # fmt: skip
    """PURE: the loot steps' seconds, picks (by hover rank, why, distance), hover time, the
    fruitless tails (after a step's last pick wait, or the whole step without a pick), and each
    TRIM rule's ESTIMATE (trim_cut): seconds saved, picks lost, late SWORDs."""
    picks = [p for s in steps for p in s["picks"]]
    hov = [(b - a) / NS for s in steps for a, b in zip(s["reads"], s["reads"][1:], strict=False)]
    rules = {}
    for trim, per_kill in trims:
        cuts = [trim_cut(s, trim, per_kill) for s in steps]
        rules[f"{trim}{'/kill' if per_kill else ''}"] = {
            "saved_s": round(sum((c[0][1] - c[0][0]) / NS for c in cuts if c[0]), 1),
            "picks_lost": sum(c[1] for c in cuts), "late_swords": sum(c[2] for c in cuts),
            "steps_cut": sum(1 for c in cuts if c[0]),
        }  # fmt: skip
    return {"steps": len(steps), "s": round(sum(s["s"] for s in steps), 1),
            "picks": len(picks), "steps_with_pick": sum(1 for s in steps if s["picks"]),
            "ends": dict(Counter(str(s["end"]) for s in steps)),
            "hovers": sum(s["hovered"] for s in steps),
            "hover_s_median": _q(hov, 0.5),
            "kills_per_step": dict(sorted(Counter(s["kills"] for s in steps).items())),
            "picks_by_rank": {"<=9": sum(1 for p in picks if p["rank"] <= 9),
                              ">9": sum(1 for p in picks if p["rank"] > 9)},
            "picks_by_why": dict(Counter(str(p["why"]) for p in picks)),
            "picks_by_distance": dict(sorted(Counter(p["d"] for p in picks).items())),
            "tail_s": round(sum(s["tail_s"] for s in steps), 1), "trim": rules}  # fmt: skip


# --- one session, the pool, the estimate ---------------------------------------------------------


def study(packets: Sequence[Mapping[str, Any]], events: Sequence[Mapping[str, Any]], t0: int,
          t1: int, hunt_map: str = "gef_fild10") -> dict[str, Any]:  # fmt: skip
    """PURE: one run's idle decomposition (time_budget.analyse's labels cut by the runner's
    mechanisms; every cause, FOCUS printed), its walk cadence, its loot steps, and where the
    proposal's (PROPOSAL) trimmed seconds lie by cause."""
    import time_budget as tb

    row = tb.analyse(packets, events, t0, t1, hunt_map)
    segs = row["_segments"]
    causes = tb.seg_causes(segs)
    ev = [e for e in events if t0 - 60 * NS <= _t(e) <= t1]
    spans = mech_spans(ev, t1)
    att = attribute(segs, causes, spans)
    steps = [s for s in loot_steps(ev) if t0 <= s["t1"] <= t1]
    trim, per_kill = next(x for x in TRIMS if f"{x[0]}{'/kill' if x[1] else ''}" == PROPOSAL)
    cuts = merge(c[0] for s in steps for c in [trim_cut(s, trim, per_kill)] if c[0])
    return {"seconds": row["seconds"], "kills": row["kills"], "kills_h": row["kills_h"],
            "causes_s": row["causes_s"], "by_cause": att,
            "walk": walk_cadence(packets, ev, t0, t1, segs, causes),
            "loot": loot_summary(steps), "trim_by_cause_s": by_cause(cuts, segs, causes),
            "_spans": spans}  # fmt: skip


def pool(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """PURE: runs pooled: seconds, kills, every mechanism's seconds and counts, the loot steps,
    the TRIM rules and the walk estimates summed."""
    secs = sum(r["seconds"] for r in rows)
    nk = sum(r["kills"] for r in rows)
    by: dict[str, dict[str, dict[str, float]]] = {}
    for r in rows:
        for k, d in r["by_cause"].items():
            o = by.setdefault(k, {m: {"s": 0.0, "n": 0} for m in ALL})
            for m, v in d.items():
                o[m]["s"] = round(o[m]["s"] + v["s"], 2)
                o[m]["n"] += int(v["n"])
    causes = {k: round(sum(r["causes_s"].get(k, 0.0) for r in rows), 1)
              for k in rows[0]["causes_s"]} if rows else {}  # fmt: skip
    lt = [r["loot"] for r in rows]
    loot: dict[str, Any] = {k: round(sum(x[k] for x in lt), 1)
                            for k in ("steps", "s", "picks", "tail_s")}  # fmt: skip
    loot["trim"] = {k: {f: round(sum(x["trim"][k][f] for x in lt), 1) for f in lt[0]["trim"][k]}
                    for k in lt[0]["trim"]} if lt else {}  # fmt: skip
    wk = [r["walk"] for r in rows]
    ext = list(wk[0]["extend_saved_s"]) if wk else []
    tbc: dict[str, float] = defaultdict(float)
    for r in rows:
        for k, v in r["trim_by_cause_s"].items():
            tbc[k] += v
    return {"runs": len(rows), "seconds": round(secs, 1), "kills": nk,
            "kills_h": round(nk * 3600 / secs, 1) if secs else None, "causes_s": causes,
            "by_cause": by, "loot": loot,
            "trim_by_cause_s": {k: round(v, 1) for k, v in sorted(tbc.items())},
            "walk": {"short_n": sum(w["stops_inside_search"]["short_n"] for w in wk),
                     "short_s": round(sum(w["stops_inside_search"]["short_s"] for w in wk), 1),
                     "extend_saved_s": {k: round(sum(w["extend_saved_s"][k] for w in wk), 1)
                                        for k in ext}}}  # fmt: skip


def per_kill(row: Mapping[str, Any], cause: str) -> list[tuple[str, float, int]]:
    """PURE: (mechanism, seconds per kill, count) of one cause, largest first."""
    d = row["by_cause"].get(cause, {})
    nk = row["kills"] or 1
    out = [(m, round(v["s"] / nk, 2), int(v["n"])) for m, v in d.items() if v["s"] > 0]
    return sorted(out, key=lambda x: -x[1])


def gain(kills: int, seconds: float, saved_s: float) -> dict[str, float | None]:
    """PURE (an ESTIMATE, time_budget.losses' convention): the kills / h if ``saved_s`` seconds of
    the window were removed and every other second kept its share per kill."""
    if not kills or seconds <= 0:
        return {"kills_h": None, "kills_h_new": None, "gain": None}
    per = seconds / kills
    new = per - saved_s / kills
    k0 = round(3600 / per, 1)
    k1 = round(3600 / new, 1) if new > 0 else None
    return {"kills_h": k0, "kills_h_new": k1,
            "gain": round(k1 - k0, 1) if k1 is not None else None}  # fmt: skip


# --- the CLI (not pure) --------------------------------------------------------------------------


def box(head: Sequence[str], rows: Sequence[Sequence[str]], title: str) -> str:
    """An ASCII table."""
    w = [max(len(str(x)) for x in col) for col in zip(head, *rows, strict=False)]

    def line(cells: Sequence[str]) -> str:
        return "| " + " | ".join(str(c).ljust(n) for c, n in zip(cells, w, strict=True)) + " |"

    sep = "+-" + "-+-".join("-" * n for n in w) + "-+"
    return "\n".join([title, sep, line(head), sep, *(line(r) for r in rows), sep])


def estimates(pooled: Mapping[str, Any]) -> list[dict[str, Any]]:
    """PURE (ESTIMATES, ``gain``'s convention): the kills / h each candidate change would give the
    pooled runs: the TRIM rules (all their saved seconds, and only the part that lay in IDLE
    labels), the longer walk legs, and the removal of single mechanisms (every second of the
    mechanism in the FOCUS causes)."""
    nk, secs = pooled["kills"], pooled["seconds"]
    out = []
    for k, v in pooled["loot"].get("trim", {}).items():
        out.append({"change": f"loot TRIM {k} (no sweep)", "saved_s": v["saved_s"],
                    **gain(nk, secs, v["saved_s"]), "note": f"picks lost {v['picks_lost']}, "
                    f"late SWORDs {v['late_swords']}"})  # fmt: skip
    idle = sum(v for k, v in pooled.get("trim_by_cause_s", {}).items() if k.startswith("idle_"))
    out.append({"change": f"loot TRIM {PROPOSAL}: its IDLE seconds only",
                "saved_s": round(idle, 1), **gain(nk, secs, idle),
                "note": "the trimmed seconds inside idle labels"})  # fmt: skip
    for k, v in pooled["walk"]["extend_saved_s"].items():
        out.append({"change": f"walk legs +{k} cells", "saved_s": v, **gain(nk, secs, v),
                    "note": f"of {pooled['walk']['short_s']} s in {pooled['walk']['short_n']} "
                    "stop-and-go stops"})  # fmt: skip
    for m in ("patrol_dead_end", "ui_watch", "scan_empty_after_kill", "scan_empty_no_kill",
              "stall_scan", "fly_settle"):  # fmt: skip
        v = sum(pooled["by_cause"].get(c, {}).get(m, {}).get("s", 0.0) for c in FOCUS)
        note = ("its part outside walk ticks (a lower bound of the watch)" if m == "ui_watch"
                else "upper bound")  # fmt: skip
        out.append({"change": f"no {m} (in {', '.join(c[5:] for c in FOCUS)})",
                    "saved_s": round(v, 1), **gain(nk, secs, v), "note": note})  # fmt: skip
    return out


def text(rows: Sequence[Mapping[str, Any]], pooled: Mapping[str, Any]) -> str:
    cols = [(str(r["session"]).rsplit("-", 1)[-1], r) for r in rows] + [("pooled", pooled)]
    out = []
    for cause in FOCUS:
        mechs = [m for m in ALL if any(c[1]["by_cause"].get(cause, {}).get(m, {}).get("s", 0) > 0
                                       for c in cols)]  # fmt: skip
        body = []
        for m in sorted(mechs, key=lambda m: -pooled["by_cause"].get(cause, {}).get(m, {})
                        .get("s", 0)):  # fmt: skip
            cells = []
            for _n, r in cols:
                v = r["by_cause"].get(cause, {}).get(m, {"s": 0.0, "n": 0})
                cells.append(f"{v['s'] / (r['kills'] or 1):.2f} ({v['n']})")
            body.append([m, *cells])
        tot = [sum(v["s"] for v in r["by_cause"].get(cause, {}).values()) / (r["kills"] or 1)
               for _n, r in cols]  # fmt: skip
        body.append(["TOTAL", *(f"{x:.2f}" for x in tot)])
        out.append(box(["mechanism", *[n for n, _r in cols]], body,
                       f"{cause}: seconds per kill (count)"))  # fmt: skip
    lr = []
    for n, r in cols:
        lo = r["loot"]
        tr = lo["trim"][PROPOSAL]
        lr.append([n, str(lo["steps"]), str(lo["s"]), str(lo["picks"]), str(lo["tail_s"]),
                   str(tr["saved_s"]), str(int(tr["picks_lost"])),
                   str(int(tr["late_swords"]))])  # fmt: skip
    out.append(box(["run", "steps", "s", "picks", "tail s", f"trim {PROPOSAL} saved s",
                    "picks lost", "late SWORDs"], lr,
                   "LOOT STEPS (loot v1; tail = after the last pick)"))  # fmt: skip
    tr_rows = [[k, str(v["saved_s"]), str(int(v["picks_lost"])), str(int(v["late_swords"])),
                str(int(v["steps_cut"]))] for k, v in pooled["loot"]["trim"].items()]  # fmt: skip
    out.append(box(["TRIM hovers", "saved s", "picks lost", "late SWORDs", "steps cut"], tr_rows,
                   f"TRIM RULES, pooled ({pooled['loot']['picks']} picks in "
                   f"{pooled['loot']['steps']} steps)"))  # fmt: skip
    out.append(box(["cause", "s"], [[k, str(v)] for k, v in pooled["trim_by_cause_s"].items()],
                   f"TRIM {PROPOSAL}: where its saved seconds lie (pooled)"))  # fmt: skip
    wr = [[str(r["session"]).rsplit("-", 1)[-1], str(r["walk"]["walk_clicks"]),
           str(r["walk"]["click_gap_s_median"]), str(r["walk"]["path_cells_median"]),
           str(r["walk"]["moving_s_median"]), str(r["walk"]["target_is_goal_share"]),
           str(r["walk"]["stops_inside_search"]["short_n"]),
           str(r["walk"]["stops_inside_search"]["short_s"])] for r in rows]  # fmt: skip
    out.append(box(["run", "walk clicks", "click gap s", "path cells", "moving s",
                    "target = goal", "short stops", "short stops s"], wr,
                   "WALK CADENCE (packets: our self_move paths; stops < 2.5 s inside "
                   "search)"))  # fmt: skip
    er = [[e["change"], str(e["saved_s"]), str(e["kills_h"]), str(e["kills_h_new"]),
           str(e["gain"]), e["note"]] for e in estimates(pooled)]  # fmt: skip
    out.append(box(["change", "saved s", "kills/h", "kills/h new", "gain", "note"], er,
                   "ESTIMATES (pooled; every other second kept per kill)"))  # fmt: skip
    return "\n\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("sids", nargs="+")
    ap.add_argument("--map", default="gef_fild10")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    import time_budget as tb

    rows = []
    for sid in a.sids:
        ev, pk, _man, t0, t1 = tb.load_window(sid, None)
        r = study(pk, ev, t0, t1, a.map)
        r["session"] = sid
        rows.append(r)
    pooled = pool(rows)
    if a.json:
        pub = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
        doc = {"runs": pub, "pooled": pooled, "estimates": estimates(pooled)}
        print(json.dumps(doc, indent=1, default=str))
    else:
        print(text(rows, pooled))
        print(f"\npooled: {pooled['runs']} runs, {pooled['kills']} kills, "
              f"{pooled['seconds']} s, {pooled['kills_h']} kills / h")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
