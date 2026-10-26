#!/usr/bin/env python3
"""THE TIME BUDGET (2026-10-26, docs/planning/rogue-gef10.md Amendment L, work item (b)): WHERE a
hunt's time goes -- Batt's gef_fild10 demo against the bot's runs, with the SAME definitions for
both, from the PACKETS (the server's truth, ADR-0007). Offline only: nothing here reaches a
runner, and it reads only banked session files.

    time_budget.py session SID [--live S] [--map gef_fild10]     one session's budget (JSON)
    time_budget.py compare --target SID --live S SID [SID ...] [--json]
                                                 the target (Batt) vs the bot pooled, ranked
    time_budget.py route SID --live S [--out PATH]               the target's loop (waypoints)

THE WINDOW is dungeon_judge's: run_start..run_end for a runner session; ``--live S`` for a human
demo (his first input .. + S s, capped at the recording's end; only for a session whose manifest
has t0_live_ns).

DEFINITIONS (written 2026-10-26 ~10:35 ICT, before any number was read). Changed after a first
look, each recorded: the LOOT span per pile, not per request (~10:4x, after Batt's first row: per
request, 44 pickups gave 1 s in all); the APPROACH split into react / close and the IDLE split by
context (~10:5x, after the first comparison, to locate the losses: no label's boundary moved);
the ROUTE from the first lap, despiked (~10:5x, after seeing that he walked the loop twice).
Every instant of the window gets exactly ONE label; where spans overlap, the first of this list
wins:

1. REST: our sitting (act kind sit -> stand, packets) UNION the runner's rest spans (rest_go ->
   rest_end: the walk to the spot and the sit; the bot only) UNION the time on another map than
   the hunt map (map_change packets: Batt walked into in_orcs01 to sit);
2. FIGHT: per engagement, our first act on the monster (any attack act, a miss included) until it
   dies (arm_judge.kills_of: its death vanish <= 1.5 s after our damaging act) or, when it does not
   die, our last act on it + FIGHT_TAIL_S (we disengaged). Our acts on one monster more than
   ENGAGE_GAP_S apart (or across its death: ids are reused) are separate engagements;
3. LOOT: per PILE (one kill's drops: items that fell <= PILE_S / PILE_CELLS apart), from the start
   of the walk that ends at its first picked item (our self_moves whose destination is within
   LOOT_NEAR cells of the item, chained back while each one ends there, not before the item fell
   nor LOOT_WALK_MAX_S before the request) until the pickup_result answering its last pickup
   request (<= PICK_S after it; else the request + PICK_NONE_S). A pile's pickups more than
   LOOT_GAP_S apart are separate spans;
4. APPROACH (walking toward a target): per engagement, from the EARLIEST of (a) our first attack
   request on it, (b) the walk that ends at it (our self_moves whose destination is within
   WALK_NEAR cells of the monster's cell at that time, chained back), (c) its first act on us (it
   engaged us first) -- each at most APPROACH_MAX_S before our first act on it and after our
   previous engagement on it -- until that first act. Split in two: REACT = from its first act on
   us until our first request / walk toward it (only when it acted first); CLOSE = the rest;
5. SEARCH: our walking (flow_judge.gm_track's moving spans) with none of the above;
6. IDLE: everything else (no movement and none of the above), split by what surrounds each idle
   stretch: inside a search (search on both sides: stop-and-go walking), the loot pause (after a
   fight before a loot, or beside a loot), after a fight, before an engagement (waiting for the
   monster), beside a rest, other. For the bot it is also split by the runner's own activity spans
   (scan, loot hover, strike clicks, Steal); for a human demo the CLI counts his input events in
   each label (aggregate counts only).

PER KILL: the kill-to-kill time (consecutive kills in the window) split by the labels; the time
to kill (our first act -> the death); the ENGAGE DISTANCE (Chebyshev cells from our cell to the
monster's at our first attack request on it); the hits taken (monster acts on us with damage > 0,
counted once each: per kill-to-kill cycle, and by the label in force when each landed); a SECOND
MONSTER JOINED (another monster acted on us, or we acted on another, inside that kill's approach +
fight).

THE ROUTE: the target's SEARCH walking cells (the ring, without the detours to monsters and items),
in time order, on the hunt map only; its FIRST LAP (until it comes back within LAP_BACK cells of
its start after going >= LAP_AWAY away), simplified (Ramer-Douglas-Peucker, WP_EPS), spaced
WP_MIN..WP_MAX cells of path apart, spikes (a turn sharper than SPIKE_DEG) removed, a waypoint off
the map's walkable grid (the client GAT in /dev/shm, when there) moved to a walked cell <= 3 cells
from it; the kills' Chebyshev distance to its polyline, and the later lap's distance to it. The
waypoints are coordinates only: nothing of the GAT is written out.
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

NS = 1_000_000_000
AID = 2000002
HUNT_MAP = "gef_fild10"
POTION, FLY = 504, 601
NOT_A_HIT = ("pickup", "sit", "stand")
MOB = 5  # entity_appear objtype of a monster
ENGAGE_GAP_S = 5.0
FIGHT_TAIL_S = 1.0
APPROACH_MAX_S = 15.0
WALK_NEAR, LOOT_NEAR = 2, 1
LOOT_WALK_MAX_S = 10.0
LOOT_GAP_S = 5.0
PILE_S, PILE_CELLS = 1.0, 3  # one kill's drops: fallen this close in time and space
PICK_S, PICK_NONE_S = 2.0, 0.3
KILL_S = 1.5  # arm_judge.kills_of: a death this soon after our damaging act is our kill
POTION_S = 1.0  # an HP rise this soon after our potion's use_item_result is the potion's
WP_EPS, WP_MIN, WP_MAX, WP_STEP = 3.0, 8, 15, 12
SPIKE_DEG = 120.0
LAP_AWAY, LAP_BACK = 60, 10
# the timeline's labels, in priority order (idle = none of them); react / close = the approach
PRIORITY = ("rest", "fight", "loot", "react", "close", "search")
MAIN = {"react": "approach", "close": "approach"}
CATS = ("fight", "approach", "loot", "rest", "search", "idle")  # the brief's (a)-(f) order
IDLE_CTX = ("inside_search", "loot_pause", "after_fight", "before_engage", "around_rest",
            "other")  # fmt: skip
CAUSES = ("fight", "approach_react", "approach_close", "loot", "rest", "search_walk",
          *(f"idle_{k}" for k in IDLE_CTX))  # fmt: skip
RUNNER_ACTS = ("scan", "loot_hover", "strike", "steal")  # the bot's own activity spans
Cell = tuple[int, int]
Span = tuple[int, int]
Seg = tuple[int, int, str]


def _t(e: Mapping[str, Any]) -> int:
    return int(e["t_mono_ns"])


def cheb(a: Sequence[int], b: Sequence[int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _q(xs: Sequence[float], q: float) -> float | None:
    """PURE: the q-quantile (linear between ranks; None when empty)."""
    if not xs:
        return None
    s = sorted(xs)
    k = q * (len(s) - 1)
    i = int(k)
    return round(s[i] + (s[min(i + 1, len(s) - 1)] - s[i]) * (k - i), 2)


def _stats(xs: Sequence[float]) -> dict[str, Any]:
    return {"n": len(xs), "median": _q(xs, 0.5), "p75": _q(xs, 0.75),
            "mean": round(statistics.fmean(xs), 2) if xs else None}  # fmt: skip


# --- spans ---------------------------------------------------------------------------------------


def merge(spans: Iterable[Span]) -> list[Span]:
    """PURE: the union of ``spans`` as sorted, disjoint spans (empty ones dropped)."""
    out: list[Span] = []
    for a, b in sorted(s for s in spans if s[1] > s[0]):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def clip(spans: Iterable[Span], t0: int, t1: int) -> list[Span]:
    """PURE: ``spans`` cut to [t0, t1]."""
    return [(max(a, t0), min(b, t1)) for a, b in spans if b > t0 and a < t1]


def overlap(spans: Sequence[Span], a: int, b: int) -> int:
    """PURE: the ns of ``spans`` inside [a, b]."""
    return sum(max(0, min(y, b) - max(x, a)) for x, y in spans)


def minus(s: Span, cut: Sequence[Span]) -> list[Span]:
    """PURE: span ``s`` minus the (sorted, disjoint) spans ``cut``."""
    out, cur = [], s[0]
    for x, y in cut:
        if y <= cur or x >= s[1]:
            continue
        if x > cur:
            out.append((cur, x))
        cur = max(cur, y)
    if cur < s[1]:
        out.append((cur, s[1]))
    return out


def label(t0: int, t1: int, spans: Mapping[str, Iterable[Span]],
          order: Sequence[str] = PRIORITY, default: str = "idle") -> list[Seg]:  # fmt: skip
    """PURE: [t0, t1] cut into (a, b, label) segments: each instant takes the FIRST label of
    ``order`` whose spans cover it, else ``default``; neighbours with one label are joined."""
    ms = {c: merge(clip(spans.get(c, ()), t0, t1)) for c in order}
    cuts = sorted({t0, t1, *(x for v in ms.values() for s in v for x in s)})
    ptr = dict.fromkeys(order, 0)
    out: list[Seg] = []
    for a, b in zip(cuts, cuts[1:], strict=False):
        cat = default
        for c in order:
            lst, i = ms[c], ptr[c]
            while i < len(lst) and lst[i][1] <= a:
                i += 1
            ptr[c] = i
            if i < len(lst) and lst[i][0] <= a:
                cat = c
                break
        if out and out[-1][2] == cat and out[-1][1] == a:
            out[-1] = (out[-1][0], b, cat)
        else:
            out.append((a, b, cat))
    return out


def seconds_by(segs: Sequence[Seg], a: int | None = None, b: int | None = None
               ) -> dict[str, float]:  # fmt: skip
    """PURE: the seconds of each MAIN label (CATS) inside [a, b] (all of it when not given)."""
    out = dict.fromkeys(CATS, 0.0)
    for s0, s1, c in segs:
        lo, hi = s0 if a is None else max(s0, a), s1 if b is None else min(s1, b)
        if hi > lo:
            out[MAIN.get(c, c)] += (hi - lo) / NS
    return out


def idle_kind(prv: str | None, nxt: str | None) -> str:
    """PURE: an idle stretch's context from the labels on either side (definition 6)."""
    if prv == "fight":
        return "loot_pause" if nxt == "loot" else "after_fight"
    if "loot" in (prv, nxt):
        return "loot_pause"
    if "rest" in (prv, nxt):
        return "around_rest"
    if nxt in ("react", "close", "fight"):
        return "before_engage"
    if prv == nxt == "search":
        return "inside_search"
    return "other"


def causes_by(segs: Sequence[Seg]) -> dict[str, float]:
    """PURE: the seconds of each refined CAUSE: the labels, the approach's two parts, and the idle
    stretches by their context."""
    out = dict.fromkeys(CAUSES, 0.0)
    for (a, b, _c), k in zip(segs, seg_causes(segs), strict=True):
        out[k] += (b - a) / NS
    return out


def label_at(segs: Sequence[Seg], t: int) -> str | None:
    """PURE: the MAIN label in force at ``t`` (None outside the timeline)."""
    i = bisect.bisect_right([s[0] for s in segs], t) - 1
    if i < 0 or t > segs[-1][1]:
        return None
    return MAIN.get(segs[i][2], segs[i][2])


def seg_causes(segs: Sequence[Seg]) -> list[str]:
    """PURE: each segment's refined CAUSE (an idle one by its neighbours, definition 6)."""
    name = {"react": "approach_react", "close": "approach_close", "search": "search_walk"}
    out = []
    for i, (_a, _b, c) in enumerate(segs):
        if c == "idle":
            out.append(
                "idle_"
                + idle_kind(
                    segs[i - 1][2] if i else None, segs[i + 1][2] if i + 1 < len(segs) else None
                )
            )
        else:
            out.append(name.get(c, c))
    return out


def at(segs: Sequence[Seg], starts: Sequence[int], t: int) -> int | None:
    """PURE: the index of the segment in force at ``t`` (``starts``: the segments' starts)."""
    i = bisect.bisect_right(starts, t) - 1
    return None if i < 0 or t > segs[-1][1] else i


# --- the facts from the packets ------------------------------------------------------------------


def monsters(packets: Sequence[Mapping[str, Any]]) -> dict[int, int]:
    """PURE: gid -> job of every monster seen (its latest entity_appear)."""
    return {int(e["gid"]): int(e.get("job", -1)) for e in packets
            if e.get("type") == "entity_appear" and e.get("objtype") == MOB
            and e.get("gid") is not None}  # fmt: skip


def acts(packets: Sequence[Mapping[str, Any]], mobs: Mapping[int, int], aid: int = AID
         ) -> tuple[list[tuple[int, int, int]], list[tuple[int, int, int]]]:  # fmt: skip
    """PURE: ([(t, monster, damage)] of OUR attack acts on a monster, [(t, monster, damage)] of a
    monster's attack acts on US) -- misses and lucky dodges included, pickups / sits not."""
    ours, theirs = [], []
    for e in packets:
        if e.get("type") != "act" or e.get("kind") in NOT_A_HIT:
            continue
        s, g = int(e.get("src_gid") or -1), int(e.get("target_gid") or -1)
        d = int(e.get("damage") or 0)
        if s == aid and g in mobs:
            ours.append((_t(e), g, d))
        elif g == aid and s in mobs:
            theirs.append((_t(e), s, d))
    return sorted(ours), sorted(theirs)


def map_spans(packets: Sequence[Mapping[str, Any]], t0: int, t1: int,
              hunt_map: str = HUNT_MAP) -> list[Span]:  # fmt: skip
    """PURE: the spans inside [t0, t1] spent on ANOTHER map than ``hunt_map`` (map_change; the map
    at t0 is the last change before it, else the hunt map)."""
    cur, out, since = hunt_map, [], t0
    for e in packets:
        if e.get("type") != "map_change":
            continue
        t, m = _t(e), str(e.get("map") or "").removesuffix(".gat")
        if t <= t0:
            cur = m
            continue
        if t >= t1:
            break
        if cur != hunt_map and m == hunt_map:
            out.append((since, t))
        elif cur == hunt_map and m != hunt_map:
            since = t
        cur = m
    if cur != hunt_map:
        out.append((since, t1))
    return [(a, b) for a, b in out if b > a]


def first_off_map(packets: Sequence[Mapping[str, Any]], t0: int, t1: int,
                  hunt_map: str = HUNT_MAP) -> int:  # fmt: skip
    """PURE: the first time in [t0, t1] we are on another map (t1 when never)."""
    sp = map_spans(packets, t0, t1, hunt_map)
    return sp[0][0] if sp else t1


def runner_rest_spans(events: Sequence[Mapping[str, Any]], t0: int, t1: int) -> list[Span]:
    """PURE: the runner's rests, rest_go (else rest_start) -> rest_end; an open one ends at t1."""
    out: list[Span] = []
    start: int | None = None
    for e in events:
        k, t = e.get("kind"), int(e.get("t_ns") or 0)
        if k in ("rest_go", "rest_start") and start is None:
            start = t
        elif k == "rest_end" and start is not None:
            out.append((start, t))
            start = None
    if start is not None:
        out.append((start, t1))
    return clip(out, t0, t1)


def runner_activity(events: Sequence[Mapping[str, Any]]) -> dict[str, list[Span]]:
    """PURE: the bot's own activity spans from its events: scan / loot_step (logged at their END
    with ``ms``), strike (t_ns .. t_end_ns), Steal (its press .. its steal event)."""
    out: dict[str, list[Span]] = defaultdict(list)
    steal_press: int | None = None
    for e in events:
        k, t = e.get("kind"), int(e.get("t_ns") or 0)
        if k == "scan" and e.get("ms") is not None:
            out["scan"].append((t - int(e["ms"]) * 1_000_000, t))
        elif k == "loot_step" and e.get("ms") is not None:
            out["loot_hover"].append((t - int(e["ms"]) * 1_000_000, t))
        elif k == "strike" and e.get("t_end_ns"):
            out["strike"].append((t, int(e["t_end_ns"])))
        elif k == "press" and e.get("what") == "steal":
            steal_press = t
        elif k == "steal" and steal_press is not None:
            out["steal"].append((steal_press, t))
            steal_press = None
    return {k: merge(v) for k, v in out.items()}


def runner_walk(events: Sequence[Mapping[str, Any]], t0: int, t1: int) -> dict[str, Any]:
    """PURE: the bot's walk decisions in [t0, t1] from its events: walk events (clicked or not,
    and why not), stalls, new goals, and the gaps between consecutive walk clicks."""
    ev = [e for e in events if t0 <= int(e.get("t_ns") or 0) <= t1]
    walks = [e for e in ev if e.get("kind") == "walk"]
    clicks = [int(e["t_ns"]) for e in walks if e.get("clicked")]
    gaps = [(b - a) / NS for a, b in zip(clicks, clicks[1:], strict=False) if b - a <= 10 * NS]
    return {"walk_events": len(walks), "clicked": len(clicks),
            "not_clicked_why": dict(Counter(str(e.get("why")) for e in walks
                                            if not e.get("clicked"))),
            "stalls": sum(1 for e in ev if e.get("kind") == "stall"),
            "goals": sum(1 for e in ev if e.get("kind") == "goal"),
            "click_gap_s_within_10s": _stats(gaps)}  # fmt: skip


class Track:
    """Our cell over time (flow_judge.gm_track) and a monster's (hunt_core.walk_positions)."""

    def __init__(self, packets: Sequence[Mapping[str, Any]]) -> None:
        import flow_judge as fj
        import hunt_core as hc

        self.points, self.moving = fj.gm_track(packets)
        self.tt = [p[0] for p in self.points]
        self.pos = hc.walk_positions(packets)
        self.ptt = {g: [q[0] for q in v] for g, v in self.pos.items()}

    def us(self, t: int) -> Cell | None:
        i = bisect.bisect_right(self.tt, t) - 1
        return self.points[i][1] if i >= 0 else None

    def mob(self, g: int, t: int) -> Cell | None:
        i = bisect.bisect_right(self.ptt.get(g, []), t) - 1
        return self.pos[g][i][1] if i >= 0 else None


def our_moves(packets: Sequence[Mapping[str, Any]]) -> list[tuple[int, Cell]]:
    """PURE: [(t, destination)] of our self_move packets."""
    return [(_t(e), (int(e["x1"]), int(e["y1"]))) for e in packets if e.get("type") == "self_move"]


def walk_back(moves: Sequence[tuple[int, Cell]], t_end: int, lo: int,
              near: Callable[[int, Cell], bool]) -> int | None:  # fmt: skip
    """PURE: the start of the chain of our moves at or before ``t_end`` (back to ``lo``) whose
    every destination is ``near`` (a predicate on (t, cell)): the earliest one's time, or None."""
    i = bisect.bisect_right([m[0] for m in moves], t_end) - 1
    out = None
    while i >= 0 and moves[i][0] >= lo and near(moves[i][0], moves[i][1]):
        out = moves[i][0]
        i -= 1
    return out


def engagements(packets: Sequence[Mapping[str, Any]], t0: int, t1: int, track: Track,
                aid: int = AID) -> list[dict[str, Any]]:  # fmt: skip
    """PURE (given the track): every engagement whose first act of ours lies in [t0, t1]
    (definitions 2 and 4), in time order."""
    import arm_judge as aj
    import dungeon_judge as dj

    mobs = monsters(packets)
    ours, theirs = acts(packets, mobs, aid)
    kills = aj.kills_of(packets, aid)
    deaths: dict[int, list[int]] = defaultdict(list)
    for e in packets:
        if e.get("type") == "entity_vanish" and int(e.get("reason", -1)) == 1:
            deaths[int(e["gid"])].append(_t(e))
    reqs: dict[int, list[int]] = defaultdict(list)
    for e in packets:
        if dj.is_attack_request(e, aid):
            reqs[int(e.get("target_gid") or -1)].append(_t(e))
    by: dict[int, list[int]] = defaultdict(list)
    for t, g, _d in ours:
        by[g].append(t)
    moves = our_moves(packets)
    segs: list[tuple[int, int, int]] = []  # (first, last, gid)
    for g, ts in by.items():
        start = last = ts[0]
        for t in ts[1:]:
            if t - last > ENGAGE_GAP_S * NS or any(last < x < t for x in deaths.get(g, ())):
                segs.append((start, last, g))
                start = t
            last = t
        segs.append((start, last, g))
    segs.sort()
    prev_end: dict[int, int] = {}
    out = []
    for tf, tl, g in segs:
        kill = next((tk for tk, gk in kills if gk == g and tf <= tk <= tl + KILL_S * NS), None)
        end = kill if kill is not None else tl + int(FIGHT_TAIL_S * NS)
        lo = max(tf - int(APPROACH_MAX_S * NS), prev_end.get(g, -(10**18)))
        prev_end[g] = end
        if not t0 <= tf <= t1:
            continue
        t_req = next((t for t in reqs.get(g, ()) if lo <= t <= tf), None)
        t_att = next((t for t, s, _d in theirs if s == g and lo <= t <= tf), None)

        def near(tm: int, c: Cell, g: int = g) -> bool:
            m = track.mob(g, tm)
            return m is not None and cheb(c, m) <= WALK_NEAR

        t_walk = walk_back(moves, tf, lo, near)
        cand = {k: v for k, v in (("request", t_req), ("walk", t_walk), ("attacked", t_att))
                if v is not None}  # fmt: skip
        how = min(cand, key=lambda k: cand[k]) if cand else "none"
        t_app = cand[how] if cand else tf
        # REACT: it acted on us first; until our first request / walk toward it (else the hit)
        t_resp = t_app
        if how == "attacked":
            t_resp = min([t for t in (t_req, t_walk) if t is not None and t >= t_app] or [tf])
        me, it = (track.us(t_req), track.mob(g, t_req)) if t_req is not None else (None, None)
        on_us = [(t, s, d) for t, s, d in theirs if t_app <= t <= end]
        out.append({
            "gid": g, "job": mobs.get(g, -1), "t_approach": t_app, "approach_by": how,
            "t_respond": t_resp, "t_first": tf, "t_last": tl, "t_end": end,
            "killed": kill is not None, "t_kill": kill,
            "ttk_s": round((kill - tf) / NS, 3) if kill is not None else None,
            "approach_s": round((tf - t_app) / NS, 3), "react_s": round((t_resp - t_app) / NS, 3),
            "engage_dist": cheb(me, it) if me is not None and it is not None else None,
            "hits_before_first": sum(1 for t, _s, d in on_us if d > 0 and t < tf),
            "joined": any(s != g for _t_, s, _d in on_us)
            or any(t_app <= t <= end and x != g for t, x, _d in ours),
            "cell": track.us(kill if kill is not None else tf),
        })  # fmt: skip
    return out


def piles(packets: Sequence[Mapping[str, Any]]) -> dict[int, int]:
    """PURE: floor id -> its PILE (one kill's drops): floor_item_appear entries that fell <= PILE_S
    after a pile's first item and <= PILE_CELLS (Chebyshev) from it; an item seen again (back in
    sight) keeps its pile."""
    out: dict[int, int] = {}
    heads: list[tuple[int, Cell, int]] = []  # (t, cell, pile) of each pile's first item
    for e in sorted((e for e in packets if e.get("type") == "floor_item_appear"
                     and e.get("floor_id") is not None), key=_t):  # fmt: skip
        fid, t, c = int(e["floor_id"]), _t(e), (int(e["x"]), int(e["y"]))
        if fid in out:
            continue
        hit = next((p for t_, c_, p in reversed(heads)
                    if t - t_ <= PILE_S * NS and cheb(c, c_) <= PILE_CELLS), None)  # fmt: skip
        if hit is None:
            hit = len(heads)
            heads.append((t, c, hit))
        out[fid] = hit
    return out


def pickups(packets: Sequence[Mapping[str, Any]], t0: int, t1: int) -> list[dict[str, Any]]:
    """PURE: per pickup request of ours in [t0, t1]: the start of the walk that ends at its item
    (else the request), the pickup_result answering it (<= PICK_S; else request + PICK_NONE_S),
    its pile and its item's fall."""
    falls: dict[int, tuple[int, Cell]] = {}
    for e in packets:
        if e.get("type") == "floor_item_appear" and e.get("floor_id") is not None:
            falls.setdefault(int(e["floor_id"]), (_t(e), (int(e["x"]), int(e["y"]))))
    pile = piles(packets)
    res = sorted((_t(e), bool(e.get("ok"))) for e in packets if e.get("type") == "pickup_result")
    rt = [r[0] for r in res]
    moves = our_moves(packets)
    out = []
    for e in packets:
        if e.get("type") != "pickup_request" or not t0 <= _t(e) <= t1:
            continue
        t, fid = _t(e), int(e.get("floor_id") or -1)
        j = bisect.bisect_right(rt, t)
        ok = j < len(res) and res[j][0] - t <= PICK_S * NS
        end = res[j][0] if ok else t + int(PICK_NONE_S * NS)
        start = t
        if fid in falls:
            tf, cell = falls[fid]

            def near(_tm: int, c: Cell, cell: Cell = cell) -> bool:
                return cheb(c, cell) <= LOOT_NEAR

            w = walk_back(moves, t, max(tf, t - int(LOOT_WALK_MAX_S * NS)), near)
            start = w if w is not None else t
        out.append({"t_request": t, "t_start": start, "t_end": end, "floor_id": fid,
                    "pile": pile.get(fid), "t_fall": falls[fid][0] if fid in falls else None,
                    "answered": ok, "ok": ok and res[j][1]})  # fmt: skip
    return out


def loot_spans(picks: Sequence[Mapping[str, Any]]) -> list[Span]:
    """PURE (definition 3): per pile, its first pickup's start .. its last pickup's answer; a
    pile's pickups more than LOOT_GAP_S apart are separate spans; an item with no known pile is a
    span of its own."""
    by: dict[Any, list[Mapping[str, Any]]] = defaultdict(list)
    for i, p in enumerate(picks):
        by[p["pile"] if p["pile"] is not None else ("solo", i)].append(p)
    out: list[Span] = []
    for ps in by.values():
        ps = sorted(ps, key=lambda p: p["t_request"])
        a, b = ps[0]["t_start"], ps[0]["t_end"]
        for p in ps[1:]:
            if p["t_start"] - b > LOOT_GAP_S * NS:
                out.append((a, b))
                a = p["t_start"]
            b = max(b, p["t_end"])
        out.append((a, b))
    return merge(out)


def fall_to_pick(picks: Sequence[Mapping[str, Any]]) -> list[float]:
    """PURE: per pile, its first item's fall to our first pickup request on it (seconds)."""
    first: dict[Any, tuple[int, int]] = {}
    for p in picks:
        if p["pile"] is None or p["t_fall"] is None:
            continue
        if p["pile"] not in first or p["t_request"] < first[p["pile"]][1]:
            first[p["pile"]] = (p["t_fall"], p["t_request"])
    return [round((b - a) / NS, 2) for a, b in first.values()]


def hp_economy(packets: Sequence[Mapping[str, Any]], t0: int, t1: int, sitting: Sequence[Span],
               aid: int = AID) -> dict[str, Any]:  # fmt: skip
    """PURE: our HP in [t0, t1] from the hp series: start / end / min, the damage taken (the sum
    of its falls), the potions' HP (rises <= POTION_S after our potion's use_item_result) and the
    natural regen (every other rise), split sitting / not sitting, with their rates."""
    import dungeon_judge as dj

    hp = dj.clip(dj.series(packets, "hp"), t0, t1)
    pots = sorted(_t(e) for e in packets if e.get("type") == "use_item_result" and e.get("ok")
                  and int(e.get("item_id") or 0) == POTION
                  and int(e.get("aid") or aid) == aid)  # fmt: skip
    sit = merge(sitting)
    dmg = potion = regen_sit = regen_other = 0
    for (_a, v0), (t, v) in zip(hp, hp[1:], strict=False):
        if v < v0:
            dmg += v0 - v
        elif v > v0:
            k = bisect.bisect_right(pots, t) - 1
            if k >= 0 and t - pots[k] <= POTION_S * NS:
                potion += v - v0
            elif any(a <= t <= b for a, b in sit):
                regen_sit += v - v0
            else:
                regen_other += v - v0
    sit_s = sum(b - a for a, b in clip(sit, t0, t1)) / NS
    other_s = (t1 - t0) / NS - sit_s
    return {"start": hp[0][1] if hp else None, "end": hp[-1][1] if hp else None,
            "min": min((v for _t_, v in hp), default=None), "damage": dmg, "potion_hp": potion,
            "potions": sum(1 for t in pots if t0 <= t <= t1),
            "regen_sitting": regen_sit, "regen_not_sitting": regen_other,
            "sitting_s": round(sit_s, 1), "not_sitting_s": round(other_s, 1),
            "regen_sitting_hp_s": round(regen_sit / sit_s, 3) if sit_s > 0 else None,
            "regen_not_sitting_hp_s": (round(regen_other / other_s, 3) if other_s > 0
                                       else None)}  # fmt: skip


def walked(track: Track, t0: int, t1: int) -> int:
    """PURE (given the track): the cells we stepped in [t0, t1] (one-cell steps only: a teleport
    or a map change is not walking)."""
    pts = [c for t, c in track.points if t0 <= t <= t1]
    return sum(1 for a, b in zip(pts, pts[1:], strict=False) if cheb(a, b) == 1)


# --- one session ---------------------------------------------------------------------------------


def analyse(packets: Sequence[Mapping[str, Any]], events: Sequence[Mapping[str, Any]], t0: int,
            t1: int, hunt_map: str = HUNT_MAP, aid: int = AID) -> dict[str, Any]:  # fmt: skip
    """PURE: one window's time budget, per-kill cycle, damage and HP economy (the module's
    definitions). The underscore keys are for the CLI and the pooling, not for output."""
    import dungeon_judge as dj

    tr = Track(packets)
    eng = engagements(packets, t0, t1, tr, aid)
    picks = pickups(packets, t0, t1)
    sits = dj.sit_spans(packets, t1, aid)
    off = map_spans(packets, t0, t1, hunt_map)
    spans = {
        "rest": merge([*sits, *runner_rest_spans(events, t0, t1), *off]),
        "fight": [(e["t_first"], e["t_end"]) for e in eng],
        "loot": loot_spans(picks),
        "react": [(e["t_approach"], e["t_respond"]) for e in eng],
        "close": [(e["t_respond"], e["t_first"]) for e in eng],
        "search": tr.moving,
    }
    segs = label(t0, t1, spans)
    secs = (t1 - t0) / NS
    by = seconds_by(segs)
    killed = [e for e in eng if e["killed"] and t0 <= e["t_kill"] <= t1]
    kills = sorted(e["t_kill"] for e in killed)
    nk = len(kills)
    mobs = monsters(packets)
    _ours, theirs = acts(packets, mobs, aid)
    hits = [(t, d) for t, _s, d in theirs if t0 <= t <= t1 and d > 0]
    cyc = []
    for a, b in zip(kills, kills[1:], strict=False):
        c = seconds_by(segs, a, b)
        c["_hits"] = sum(1 for t, _d in hits if a < t <= b)
        c["_damage"] = sum(d for t, d in hits if a < t <= b)
        cyc.append(c)
    dmg_by: dict[str, list[int]] = {c: [0, 0] for c in CATS}
    for t, d in hits:
        lab = label_at(segs, t) or "idle"
        dmg_by[lab][0] += 1
        dmg_by[lab][1] += d
    # every attack act on us (misses too: the exposure) and the hits, by refined cause; and the
    # attackers we never acted on in the window (unanswered)
    on_us = [(t, g, d) for t, g, d in theirs if t0 <= t <= t1]
    ours_g = {g for t, g, _d in _ours if t0 <= t <= t1}
    sc, starts = seg_causes(segs), [x[0] for x in segs]
    by_cause = {k: [0, 0, 0] for k in CAUSES}  # attempts, hits, damage
    for t, _g, d in on_us:
        i_ = at(segs, starts, t)
        k = sc[i_] if i_ is not None else "idle_other"
        by_cause[k][0] += 1
        by_cause[k][1] += d > 0
        by_cause[k][2] += d
    unanswered = [(t, g, d) for t, g, d in on_us if g not in ours_g]
    act = runner_activity(events)
    by_act = {c: dict.fromkeys((*RUNNER_ACTS, "none"), 0.0) for c in CAUSES}
    for (a, b, _c), k_ in zip(segs, sc, strict=True):
        rem = [(a, b)]
        for k in RUNNER_ACTS:
            sp = act.get(k, [])
            by_act[k_][k] += sum(overlap(sp, x, y) for x, y in rem) / NS
            rem = [p for x, y in rem for p in minus((x, y), sp)]
        by_act[k_]["none"] += sum(y - x for x, y in rem) / NS
    ev_rest, _why = dj.rest_spans(events, t0, t1)
    moving_s = overlap(merge(tr.moving), t0, t1) / NS
    cells = walked(tr, t0, t1)
    cau = causes_by(segs)
    n_walk_req = sum(1 for e in packets if e.get("type") == "self_move_request"
                     and t0 <= _t(e) <= t1)  # fmt: skip
    return {
        "seconds": round(secs, 1), "minutes": round(secs / 60, 2), "kills": nk,
        "kills_h": round(nk * 3600 / secs, 1) if secs else None,
        "budget": {c: {"s": round(by[c], 1), "share": round(by[c] / secs, 4) if secs else None}
                   for c in CATS},
        "per_kill_s": {c: round(by[c] / nk, 2) if nk else None for c in CATS},
        "causes_s": {k: round(v, 1) for k, v in cau.items()},
        "causes_per_kill_s": {k: round(v / nk, 2) if nk else None for k, v in cau.items()},
        "cycle": cycle_stats(cyc),
        "time_to_kill_s": _stats([e["ttk_s"] for e in killed]),
        "approach_s": _stats([e["approach_s"] for e in killed]),
        "react_s_when_attacked_first": _stats([e["react_s"] for e in killed
                                               if e["approach_by"] == "attacked"]),
        "engage_dist": _stats([e["engage_dist"] for e in killed if e["engage_dist"] is not None]),
        "engage_dist_hist": dict(sorted(Counter(min(e["engage_dist"], 10) for e in killed
                                                if e["engage_dist"] is not None).items())),
        "approach_by": dict(Counter(e["approach_by"] for e in killed)),
        "hits_taken": len(hits), "damage_taken": sum(d for _t_, d in hits),
        "hits_per_kill": round(len(hits) / nk, 2) if nk else None,
        "damage_per_kill": round(sum(d for _t_, d in hits) / nk, 1) if nk else None,
        "hits_before_our_first_hit_per_kill": round(sum(e["hits_before_first"] for e in killed)
                                                    / nk, 2) if nk else None,
        "damage_by_label": {c: {"hits": v[0], "damage": v[1]} for c, v in dmg_by.items()},
        "on_us_by_cause": {k: {"attempts": v[0], "hits": v[1], "damage": v[2]}
                           for k, v in by_cause.items()},
        "attempts_on_us": len(on_us),
        "attempts_per_kill": round(len(on_us) / nk, 2) if nk else None,
        "unanswered_attackers": {"monsters": len({g for _t_, g, _d in unanswered}),
                                 "attempts": len(unanswered),
                                 "hits": sum(1 for *_x, d in unanswered if d > 0),
                                 "damage": sum(d for *_x, d in unanswered),
                                 "seconds": round(sum(b - a for a, b in merge(
                                     _first_last(unanswered))) / NS, 1)},
        "joined_share": round(sum(e["joined"] for e in killed) / nk, 3) if nk else None,
        "engagements": len(eng), "engagements_not_killed": sum(1 for e in eng if not e["killed"]),
        "loot": {"requests": len(picks), "ok": sum(x["ok"] for x in picks),
                 "unanswered": sum(not x["answered"] for x in picks),
                 "fall_to_first_pick_s": _stats(fall_to_pick(picks))},
        "hp": hp_economy(packets, t0, t1, sits, aid),
        "runner_activity_by_cause_s": ({c: {k: round(v, 1) for k, v in d.items()}
                                        for c, d in by_act.items()} if events else None),
        "rest_check_s": {"sitting_packets": round(sum(b - a for a, b in clip(merge(sits), t0, t1))
                                                  / NS, 1),
                         "runner_rest_start_to_end": round(sum(b - a for a, b in ev_rest) / NS, 1),
                         "off_map": round(sum(b - a for a, b in off) / NS, 1)},
        "walking": {"cells": cells, "moving_s": round(moving_s, 1),
                    "cells_per_walking_min": round(cells / moving_s * 60, 1) if moving_s else None,
                    "cells_per_min": round(cells / secs * 60, 1) if secs else None,
                    "walk_requests_per_min": round(n_walk_req / secs * 60, 1) if secs else None},
        "fly_wings": sum(1 for e in packets if e.get("type") == "use_item_result" and e.get("ok")
                         and int(e.get("item_id") or 0) == FLY and t0 <= _t(e) <= t1),
        "runner_walk": runner_walk(events, t0, t1) if events else None,
        "_segments": segs, "_killed": killed, "_cycles": cyc,
    }  # fmt: skip


def _first_last(hits: Sequence[tuple[int, int, int]]) -> list[Span]:
    """PURE: per monster, the span from its first to its last act in ``hits``."""
    by: dict[int, list[int]] = defaultdict(list)
    for t, g, _d in hits:
        by[g].append(t)
    return [(min(v), max(v)) for v in by.values()]


def cycle_stats(cyc: Sequence[Mapping[str, float]]) -> dict[str, Any]:
    """PURE: the kill-to-kill cycles' distributions: the total, each label, hits and damage."""
    return {"n": len(cyc), "total": _stats([sum(c[k] for k in CATS) for c in cyc]),
            **{c: _stats([x[c] for x in cyc]) for c in CATS},
            "hits": _stats([x["_hits"] for x in cyc]),
            "damage": _stats([x["_damage"] for x in cyc])}  # fmt: skip


def public(row: Mapping[str, Any]) -> dict[str, Any]:
    """PURE: the row without its CLI-only (underscore) keys."""
    return {k: v for k, v in row.items() if not k.startswith("_")}


def pool(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """PURE: the runs pooled: seconds, kills, hits and HP summed, every share and rate from the
    sums; the per-kill distributions over all runs' kills / cycles together."""
    secs = sum(r["seconds"] for r in rows)
    nk = sum(r["kills"] for r in rows)
    by = {c: sum(r["budget"][c]["s"] for r in rows) for c in CATS}
    cau = {k: sum(r["causes_s"][k] for r in rows) for k in CAUSES}
    killed = [e for r in rows for e in r["_killed"]]
    cyc = [c for r in rows for c in r["_cycles"]]
    hp_keys = ("damage", "potion_hp", "potions", "regen_sitting", "regen_not_sitting",
               "sitting_s", "not_sitting_s")  # fmt: skip
    hp: dict[str, Any] = {k: round(sum(r["hp"][k] for r in rows), 1) for k in hp_keys}
    hp["regen_sitting_hp_s"] = (round(hp["regen_sitting"] / hp["sitting_s"], 3)
                                if hp["sitting_s"] else None)  # fmt: skip
    hp["regen_not_sitting_hp_s"] = (round(hp["regen_not_sitting"] / hp["not_sitting_s"], 3)
                                    if hp["not_sitting_s"] else None)  # fmt: skip
    hits, dmg = sum(r["hits_taken"] for r in rows), sum(r["damage_taken"] for r in rows)
    acts_: dict[str, Counter[str]] = defaultdict(Counter)
    for r in rows:
        for c, d in (r.get("runner_activity_by_cause_s") or {}).items():
            acts_[c].update(d)
    cells = sum(r["walking"]["cells"] for r in rows)
    mv = sum(r["walking"]["moving_s"] for r in rows)
    return {
        "runs": len(rows), "seconds": round(secs, 1), "minutes": round(secs / 60, 2),
        "kills": nk, "kills_h": round(nk * 3600 / secs, 1) if secs else None,
        "budget": {c: {"s": round(by[c], 1), "share": round(by[c] / secs, 4)} for c in CATS},
        "per_kill_s": {c: round(by[c] / nk, 2) if nk else None for c in CATS},
        "causes_s": {k: round(v, 1) for k, v in cau.items()},
        "causes_per_kill_s": {k: round(v / nk, 2) if nk else None for k, v in cau.items()},
        "cycle": cycle_stats(cyc),
        "time_to_kill_s": _stats([e["ttk_s"] for e in killed]),
        "approach_s": _stats([e["approach_s"] for e in killed]),
        "react_s_when_attacked_first": _stats([e["react_s"] for e in killed
                                               if e["approach_by"] == "attacked"]),
        "engage_dist": _stats([e["engage_dist"] for e in killed if e["engage_dist"] is not None]),
        "engage_dist_hist": dict(sorted(Counter(min(e["engage_dist"], 10) for e in killed
                                                if e["engage_dist"] is not None).items())),
        "approach_by": dict(Counter(e["approach_by"] for e in killed)),
        "hits_taken": hits, "damage_taken": dmg,
        "hits_per_kill": round(hits / nk, 2) if nk else None,
        "damage_per_kill": round(dmg / nk, 1) if nk else None,
        "hits_before_our_first_hit_per_kill": round(sum(e["hits_before_first"] for e in killed)
                                                    / nk, 2) if nk else None,
        "damage_by_label": {c: {k: sum(r["damage_by_label"][c][k] for r in rows)
                                for k in ("hits", "damage")} for c in CATS},
        "on_us_by_cause": {c: {k: sum(r["on_us_by_cause"][c][k] for r in rows)
                               for k in ("attempts", "hits", "damage")} for c in CAUSES},
        "attempts_on_us": sum(r["attempts_on_us"] for r in rows),
        "attempts_per_kill": round(sum(r["attempts_on_us"] for r in rows) / nk, 2) if nk else None,
        "unanswered_attackers": {k: round(sum(r["unanswered_attackers"][k] for r in rows), 1)
                                 for k in ("monsters", "attempts", "hits", "damage", "seconds")},
        "joined_share": round(sum(e["joined"] for e in killed) / nk, 3) if nk else None,
        "engagements": sum(r["engagements"] for r in rows),
        "engagements_not_killed": sum(r["engagements_not_killed"] for r in rows),
        "loot": {k: sum(r["loot"][k] for r in rows) for k in ("requests", "ok", "unanswered")},
        "hp": hp,
        "runner_activity_by_cause_s": {c: {k: round(v, 1) for k, v in d.items()}
                                       for c, d in acts_.items()},
        "rest_check_s": {k: round(sum(r["rest_check_s"][k] for r in rows), 1)
                         for k in ("sitting_packets", "runner_rest_start_to_end", "off_map")},
        "walking": {"cells": cells, "moving_s": round(mv, 1),
                    "cells_per_walking_min": round(cells / mv * 60, 1) if mv else None,
                    "cells_per_min": round(cells / secs * 60, 1) if secs else None},
        "fly_wings": sum(r["fly_wings"] for r in rows),
    }  # fmt: skip


# --- the losses ----------------------------------------------------------------------------------


def losses(target: Mapping[str, Any], bot: Mapping[str, Any], key: str = "causes_per_kill_s"
           ) -> list[dict[str, Any]]:  # fmt: skip
    """PURE: per cause (``key``: the refined causes, or ``per_kill_s`` for the six labels), the
    bot's seconds per kill against the target's -- MEASURED, and additive: the gaps sum to the
    whole per-kill gap -- and the kills / h the bot would reach if ONLY that cause matched the
    target's, then cumulatively in rank order (ESTIMATES: everything else held at the bot's own
    seconds per kill). The largest loss first."""
    tb, tt = bot[key], target[key]
    total = sum(tb.values())
    gap = total - sum(tt.values())
    rows = [{"cause": c, "bot_s_per_kill": tb[c], "target_s_per_kill": tt[c],
             "lost_s_per_kill": round(tb[c] - tt[c], 2)} for c in tb]  # fmt: skip
    rows.sort(key=lambda r: -r["lost_s_per_kill"])
    cum = total
    for r in rows:
        alone = total - r["lost_s_per_kill"]
        cum -= r["lost_s_per_kill"]
        r["share_of_gap"] = round(r["lost_s_per_kill"] / gap, 3) if gap else None
        r["kills_h_if_only_this_matched"] = round(3600 / alone, 1) if alone > 0 else None
        r["gain_kills_h_alone"] = round(3600 / alone - 3600 / total, 1) if alone > 0 else None
        r["kills_h_cumulative"] = round(3600 / cum, 1) if cum > 0 else None
    return rows


def sustain(row: Mapping[str, Any], sit_hp_s: float, potion_hp: float | None = None
            ) -> dict[str, Any]:  # fmt: skip
    """PURE (an ESTIMATE): what holding HP steady would cost per kill. The net HP lost per kill
    (damage minus the regen while not sitting) is bought back either by sitting at ``sit_hp_s``
    -- the kills / h with that sitting added to the per-kill time without the session's own rest
    -- or by potions of ``potion_hp`` each (potions / h at the session's own kill rate)."""
    hp, nk = row["hp"], row["kills"]
    if not nk or not sit_hp_s:
        return {"why": "no kills or no sitting rate"}
    net = (hp["damage"] - hp["regen_not_sitting"]) / nk
    need = max(0.0, net / sit_hp_s)
    base = sum(row["per_kill_s"][c] for c in CATS if c != "rest")
    return {"net_hp_per_kill": round(net, 1), "sit_hp_s": round(sit_hp_s, 3),
            "rest_needed_s_per_kill": round(need, 2),
            "rest_had_s_per_kill": row["per_kill_s"]["rest"],
            "kills_h_sustained_by_sitting": round(3600 / (base + need), 1),
            "potions_h_at_own_rate": (round(max(0.0, net) * row["kills_h"] / potion_hp, 1)
                                      if potion_hp else None)}  # fmt: skip


# --- the route -----------------------------------------------------------------------------------


def rdp_idx(points: Sequence[Cell], eps: float, lo: int = 0, hi: int | None = None) -> list[int]:
    """PURE: Ramer-Douglas-Peucker on a cell polyline, as the kept INDICES (ends included)."""
    hi = len(points) - 1 if hi is None else hi
    if hi - lo < 2:
        return [lo, hi] if hi > lo else [lo]
    (x0, y0), (x1, y1) = points[lo], points[hi]
    dx, dy = x1 - x0, y1 - y0
    norm = math.hypot(dx, dy)
    best, idx = -1.0, lo
    for i in range(lo + 1, hi):
        px, py = points[i]
        d = (abs(dy * px - dx * py + x1 * y0 - y1 * x0) / norm if norm
             else math.hypot(px - x0, py - y0))  # fmt: skip
        if d > best:
            best, idx = d, i
    if best <= eps:
        return [lo, hi]
    return rdp_idx(points, eps, lo, idx)[:-1] + rdp_idx(points, eps, idx, hi)


def route_cells(track: Sequence[tuple[int, Cell]], keep: Sequence[Span]) -> list[tuple[int, Cell]]:
    """PURE: the track's (t, cell) points inside the ``keep`` spans (start included, end not),
    consecutive repeats dropped."""
    ks = merge(keep)
    st = [k[0] for k in ks]
    out: list[tuple[int, Cell]] = []
    for t, c in track:
        i = bisect.bisect_right(st, t) - 1
        if i >= 0 and t < ks[i][1] and (not out or out[-1][1] != c):
            out.append((t, c))
    return out


def lap_end(cells: Sequence[Cell], away: int = LAP_AWAY, back: int = LAP_BACK) -> int | None:
    """PURE: the index where the walk first comes back within ``back`` cells of its start after
    having been ``away`` cells or more from it (None: no lap closed)."""
    far = False
    for i, c in enumerate(cells):
        d = cheb(c, cells[0])
        far = far or d >= away
        if far and d <= back:
            return i
    return None


def waypoints(cells: Sequence[Cell], eps: float = WP_EPS, lo: int = WP_MIN, hi: int = WP_MAX,
              step: int = WP_STEP) -> list[int]:  # fmt: skip
    """PURE: indices into ``cells`` for the waypoints: the RDP corners (``eps``); every leg longer
    than ``hi`` cells of PATH (Chebyshev steps summed) split evenly, about ``step`` a piece; then,
    while two neighbours are closer than ``lo``, the one of them that bends the route less is
    dropped (never the first or the last, nor one whose removal leaves a leg over ``hi``)."""
    if not cells:
        return []
    arc = [0]
    for a, b in zip(cells, cells[1:], strict=False):
        arc.append(arc[-1] + cheb(a, b))
    corners = rdp_idx(cells, eps)
    out = [corners[0]]
    for i, j in zip(corners, corners[1:], strict=False):
        n = arc[j] - arc[i]
        if n > hi:
            k = math.ceil(n / step)
            out += [bisect.bisect_left(arc, arc[i] + n * m / k, i, j) for m in range(1, k)]
        out.append(j)
    out = sorted(set(out))

    def bend(m: int) -> float:
        (x0, y0), (x1, y1), (px, py) = cells[out[m - 1]], cells[out[m + 1]], cells[out[m]]
        norm = math.hypot(x1 - x0, y1 - y0)
        return (abs((y1 - y0) * px - (x1 - x0) * py + x1 * y0 - y1 * x0) / norm if norm
                else math.hypot(px - x0, py - y0))  # fmt: skip

    changed = True
    while changed and len(out) > 2:
        changed = False
        for n in range(1, len(out)):
            if arc[out[n]] - arc[out[n - 1]] >= lo:
                continue
            cand = [m for m in (n - 1, n) if 0 < m < len(out) - 1
                    and arc[out[m + 1]] - arc[out[m - 1]] <= hi]  # fmt: skip
            if cand:
                del out[min(cand, key=bend)]
                changed = True
                break
    return out


def turn_deg(a: Cell, b: Cell, c: Cell) -> float:
    """PURE: the heading change at ``b`` going a -> b -> c, in degrees (0 straight, 180 back)."""
    u, v = (b[0] - a[0], b[1] - a[1]), (c[0] - b[0], c[1] - b[1])
    nu, nv = math.hypot(*u), math.hypot(*v)
    if not nu or not nv:
        return 0.0
    cos = max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / (nu * nv)))
    return math.degrees(math.acos(cos))


def despike(wps: Sequence[Cell], max_deg: float = SPIKE_DEG, loop: bool = False) -> list[Cell]:
    """PURE: drop every waypoint where the route turns sharper than ``max_deg`` (it went out and
    came back: a detour, not the ring), and a waypoint equal to its predecessor, until none."""
    out = [c for i, c in enumerate(wps) if i == 0 or c != wps[i - 1]]
    changed = True
    while changed and len(out) > 3:
        changed = False
        n = len(out)
        for i in range(n) if loop else range(1, n - 1):
            a, b, c = out[i - 1], out[i], out[(i + 1) % n]
            if turn_deg(a, b, c) > max_deg:
                del out[i]
                changed = True
                break
    return out


def densify(wps: Sequence[Cell], loop: bool) -> list[Cell]:
    """PURE: every cell along the waypoint polyline (Chebyshev steps, diagonal first)."""
    import flow_judge as fj

    if not wps:
        return []
    ends = [*wps[1:], wps[0]] if loop else list(wps[1:])
    out: list[Cell] = [(wps[0][0], wps[0][1])]
    for a, b in zip(wps, ends, strict=False):
        out += fj.steps((a[0], a[1]), (b[0], b[1]))
    return out


def route_dist(cell: Cell, dense: Sequence[Cell]) -> int:
    """PURE: the Chebyshev distance from ``cell`` to the nearest cell of the densified route."""
    return min(cheb(cell, d) for d in dense)


def signed_area(poly: Sequence[Cell]) -> float:
    """PURE: shoelace; > 0 counter-clockwise with x east and y north, < 0 clockwise."""
    return 0.5 * sum(a[0] * b[1] - b[0] * a[1]
                     for a, b in zip(poly, [*poly[1:], poly[0]], strict=True))  # fmt: skip


def dist_summary(ds: Sequence[int]) -> dict[str, Any]:
    n = len(ds)
    return {"n": n, "median": _q(ds, 0.5), "p75": _q(ds, 0.75), "p90": _q(ds, 0.9),
            "within_5": round(sum(d <= 5 for d in ds) / n, 3) if n else None,
            "within_10": round(sum(d <= 10 for d in ds) / n, 3) if n else None}  # fmt: skip


def snap(wps: Sequence[Cell], walkable: Any, cells: Sequence[Cell], r: int = 3
         ) -> tuple[list[Cell], list[list[list[int]]]]:  # fmt: skip
    """PURE: each waypoint that is not walkable (walkable[y, x]) moved to the nearest walkable
    cell of ``cells`` (the walked cells) within ``r``; returns the waypoints and the moves made
    ([from, to]; a waypoint with no such cell stays and is listed with to = None)."""

    def ok(c: Sequence[int]) -> bool:
        x, y = int(c[0]), int(c[1])
        return 0 <= y < walkable.shape[0] and 0 <= x < walkable.shape[1] and bool(walkable[y, x])

    out, moved = [], []
    for w in wps:
        if ok(w):
            out.append(w)
            continue
        near = sorted((cheb(w, c), c) for c in set(cells) if ok(c) and cheb(w, c) <= r)
        out.append(near[0][1] if near else w)
        moved.append([list(w), list(near[0][1]) if near else None])
    return out, moved  # type: ignore[return-value]


def route(row: Mapping[str, Any], packets: Sequence[Mapping[str, Any]], t0: int, t1: int,
          hunt_map: str = HUNT_MAP, walkable: Any = None) -> dict[str, Any]:  # fmt: skip
    """PURE (given the analysed row and the map's walkability, when there): the target's loop
    from its FIRST LAP of search walking on the hunt map, a waypoint off the walkable grid
    snapped to a walked cell near it; the later lap(s) and the kills measured against it."""
    tr = Track(packets)
    t_off = first_off_map(packets, t0, t1, hunt_map)
    keep = [(a, min(b, t_off)) for a, b, c in row["_segments"] if c == "search" and a < t_off]
    rc = route_cells(tr.points, keep)
    cells = [c for _t_, c in rc]
    end = lap_end(cells)
    lap = cells[: end + 1] if end is not None else cells
    raw = [lap[i] for i in waypoints(lap)]
    loop = end is not None
    wps = despike(raw, loop=loop)
    if loop and len(wps) > 3 and cheb(wps[0], wps[-1]) < WP_MIN:
        wps = wps[:-1]  # the lap's last cell is its start again: the loop closes itself
    snapped: list[list[list[int]]] = []
    if walkable is not None:
        wps, snapped = snap(wps, walkable, lap)
    dense = densify(wps, loop)
    legs = [cheb(a, b) for a, b in zip(wps, [*wps[1:], wps[0]] if loop else wps[1:],
                                         strict=False)]  # fmt: skip
    t_lap0, t_lap1 = rc[0][0], rc[end][0] if end is not None else rc[-1][0]
    rest_cells = cells[end + 1 :] if end is not None else []
    end2 = lap_end(rest_cells) if rest_cells else None
    t_lap2 = rc[end + 1 + end2][0] if end is not None and end2 is not None else None
    return {
        "waypoints": [list(c) for c in wps], "kind": "loop" if loop else "path",
        "waypoints_before_despike": len(raw), "snapped": snapped,
        "direction": ("counter-clockwise" if signed_area(wps) > 0 else "clockwise")
        + " (x east, y north)",
        "legs": {"n": len(legs), "min": min(legs, default=None), "max": max(legs, default=None),
                 "median": _q(legs, 0.5)},
        "length_cells": sum(legs),
        "lap1": {"cells_walked": len(lap), "s": round((t_lap1 - t_lap0) / NS, 1),
                 "walking_s": round(overlap(merge(tr.moving), t_lap0, t_lap1) / NS, 1),
                 "kills": sum(1 for e in row["_killed"] if t_lap0 <= e["t_kill"] <= t_lap1),
                 "track_deviation": dist_summary([route_dist(c, dense) for c in lap])},
        "after_lap1": {"cells_walked": len(rest_cells),
                       "s": round((rc[-1][0] - t_lap1) / NS, 1) if rest_cells else 0.0,
                       "second_lap_closed_s": round((t_lap2 - t_lap1) / NS, 1) if t_lap2 else None,
                       "deviation_from_lap1_loop": dist_summary([route_dist(c, dense)
                                                                 for c in rest_cells])},
        "kill_dist": dist_summary([route_dist(e["cell"], dense) for e in row["_killed"]
                                   if e["cell"] is not None and e["t_kill"] < t_off]),
        "_dense": dense,
    }  # fmt: skip


def route_json(doc: Mapping[str, Any], per_line: int = 8) -> str:
    """PURE: the route file's text: one key per line, the waypoints ``per_line`` to a line."""
    wps = [json.dumps(w) for w in doc["waypoints"]]
    rows = [", ".join(wps[i : i + per_line]) for i in range(0, len(wps), per_line)]
    head = [f" {json.dumps(k)}: {json.dumps(v)}," for k, v in doc.items() if k != "waypoints"]
    body = ",\n".join(f"  {r}" for r in rows)
    return "{\n" + "\n".join(head) + '\n "waypoints": [\n' + body + "\n ]\n}\n"


def gat_check(wps: Sequence[Sequence[int]], dense: Sequence[Cell], walkable: Any
              ) -> dict[str, Any]:  # fmt: skip
    """PURE: the waypoints and the straight legs between them against a walkability grid
    (walkable[y, x]): the waypoints that are not walkable, the share of leg cells that are."""

    def ok(c: Sequence[int]) -> bool:
        x, y = int(c[0]), int(c[1])
        return 0 <= y < walkable.shape[0] and 0 <= x < walkable.shape[1] and bool(walkable[y, x])

    bad = [list(c) for c in wps if not ok(c)]
    return {
        "waypoints_not_walkable": bad,
        "leg_cells_walkable_share": round(sum(ok(c) for c in dense) / max(1, len(dense)), 3),
    }


# --- loading and the CLI (not pure) --------------------------------------------------------------


Loaded = tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], int, int]


def load_window(sid: str, live_s: float | None) -> Loaded:
    import dungeon_judge as dj

    ev, pk, man = dj.load(sid)
    if live_s is not None and man.get("t0_live_ns"):
        t0, t1 = dj.live_window(man, live_s)
    else:
        t0, t1, _src = dj.window(ev, man, pk)
    return ev, pk, man, t0, t1


def input_counts(sid: str, segs: Sequence[Seg]) -> dict[str, dict[str, int]]:
    """A human demo's input events per MAIN label (AGGREGATE COUNTS ONLY: move / button / key; the
    log itself is never copied, printed or stored). Timed by the backend's t_mono_ns (the
    event's own t_mono_ns is the browser's clock)."""
    import dungeon_judge as dj

    p = dj.session_dir(sid) / "input_human.jsonl"
    if not p.exists():
        return {}
    out: dict[str, Counter[str]] = defaultdict(Counter)
    with p.open() as fh:
        for line in fh:
            e = json.loads(line)
            ev = e.get("event") or {}
            lab = label_at(segs, int(e.get("t_mono_ns") or 0))
            if lab is not None:
                out[lab]["button" if "button" in ev else "key" if "code" in ev else "move"] += 1
    return {k: dict(v) for k, v in out.items()}


def load_walkable(hunt_map: str) -> Any:
    """The hunt map's client GAT walkability (client data in /dev/shm; None when absent)."""
    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    p = cam.GAT_DIR / f"{hunt_map}.gat"
    return gatmod.parse(p.read_bytes()).walkable() if p.exists() else None


def compare(target_sid: str, sids: Sequence[str], live_s: float, hunt_map: str) -> dict[str, Any]:
    ev, pk, _man, t0, t1 = load_window(target_sid, live_s)
    tgt = analyse(pk, ev, t0, t1, hunt_map)
    t_off = first_off_map(pk, t0, t1, hunt_map)
    field = analyse(pk, ev, t0, t_off, hunt_map) if t_off < t1 else None
    walk = load_walkable(hunt_map)
    rt = route(tgt, pk, t0, t1, hunt_map, walk)
    rows = []
    for s in sids:
        e2, p2, _m2, a, b = load_window(s, None)
        r = analyse(p2, e2, a, b, hunt_map)
        r["session"] = s
        r["steal"] = next((x.get("steal") for x in e2 if x.get("kind") == "run_start"), None)
        r["kill_dist_to_loop"] = dist_summary(
            [route_dist(k["cell"], rt["_dense"]) for k in r["_killed"] if k["cell"] is not None]
        )
        rows.append(r)
    arm_n = [r for r in rows if not r["steal"]]
    pooled, pooled_n = pool(rows), pool(arm_n)
    for p_, rs in ((pooled, rows), (pooled_n, arm_n)):
        p_["kill_dist_to_loop"] = dist_summary(
            [
                route_dist(k["cell"], rt["_dense"])
                for r in rs
                for k in r["_killed"]
                if k["cell"] is not None
            ]
        )
    sit_rate = pooled["hp"]["regen_sitting_hp_s"] or tgt["hp"]["regen_sitting_hp_s"]
    pot = (tgt["hp"]["potion_hp"] / tgt["hp"]["potions"]) if tgt["hp"]["potions"] else None
    rtp = {k: v for k, v in rt.items() if not k.startswith("_")}
    if walk is not None:
        rtp["gat"] = gat_check(rt["waypoints"], rt["_dense"], walk)
    return {
        "target": {"session": target_sid, **public(tgt),
                   "inputs_by_label": input_counts(target_sid, tgt["_segments"])},
        "target_field": public(field) if field else None,
        "route": rtp,
        "runs": [public(r) for r in rows], "pooled": public(pooled),
        "pooled_arm_n": public(pooled_n),
        "losses_labels": losses(tgt, pooled, "per_kill_s"),
        "losses": losses(tgt, pooled), "losses_arm_n": losses(tgt, pooled_n),
        "losses_vs_target_field": losses(field, pooled) if field else None,
        "sustain": {"target": sustain(tgt, sit_rate, pot),
                    "target_field": sustain(field, sit_rate, pot) if field else None,
                    "bot_pooled": sustain(pooled, sit_rate, pot)},
    }  # fmt: skip


def box(head: Sequence[str], rows: Sequence[Sequence[str]], title: str) -> str:
    """An ASCII box table."""
    w = [max(len(str(x)) for x in col) for col in zip(head, *rows, strict=False)]

    def line(cells: Sequence[str]) -> str:
        return "| " + " | ".join(str(c).ljust(n) for c, n in zip(cells, w, strict=True)) + " |"

    sep = "+-" + "-+-".join("-" * n for n in w) + "-+"
    return "\n".join([title, sep, line(head), sep, *(line(r) for r in rows), sep])


def text(out: Mapping[str, Any]) -> str:
    cols = [("Batt", out["target"])]
    if out.get("target_field"):
        cols.append(("Batt field", out["target_field"]))
    cols += [(str(r["session"]).rsplit("-", 1)[-1], r) for r in out["runs"]]
    cols += [("bot pooled", out["pooled"]), ("bot arm N", out["pooled_arm_n"])]
    head = ["label", *[c for c, _r in cols]]
    rows = [[c, *[f"{r['budget'][c]['s']:.0f} s {100 * r['budget'][c]['share']:.1f} %"
                  for _n, r in cols]] for c in CATS]  # fmt: skip
    rows.append(["kills / h", *[str(r["kills_h"]) for _n, r in cols]])
    t1 = box(head, rows, "TIME BUDGET (seconds, share of the window)")
    lr = [[x["cause"], str(x["bot_s_per_kill"]), str(x["target_s_per_kill"]),
           str(x["lost_s_per_kill"]), str(x["gain_kills_h_alone"]), str(x["kills_h_cumulative"])]
          for x in out["losses"]]  # fmt: skip
    t2 = box(["cause", "bot s/kill", "Batt s/kill", "lost s/kill", "+kills/h alone",
              "kills/h cumul."], lr, "RANKED LOSSES (bot pooled vs Batt)")  # fmt: skip
    return t1 + "\n\n" + t2


def main() -> int:
    global APPROACH_MAX_S
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("session", "compare", "route"):
        p = sub.add_parser(name)
        p.add_argument("sids", nargs="+" if name == "compare" else 1)
        p.add_argument("--live", type=float, default=None, metavar="S")
        p.add_argument("--map", default=HUNT_MAP)
        p.add_argument(
            "--approach-max",
            type=float,
            default=APPROACH_MAX_S,
            metavar="S",
            help="the approach's look-back bound (a sensitivity check)",
        )
        if name == "compare":
            p.add_argument("--target", required=True)
            p.add_argument("--json", action="store_true")
        if name == "route":
            p.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    APPROACH_MAX_S = a.approach_max
    if a.cmd == "session":
        ev, pk, _man, t0, t1 = load_window(a.sids[0], a.live)
        print(json.dumps(public(analyse(pk, ev, t0, t1, a.map)), indent=1, default=str))
        return 0
    if a.cmd == "route":
        ev, pk, _man, t0, t1 = load_window(a.sids[0], a.live)
        walk = load_walkable(a.map)
        rt = route(analyse(pk, ev, t0, t1, a.map), pk, t0, t1, a.map, walk)
        if a.out:
            doc = {"source": f"{a.sids[0]} (Batt's demo, packets, --live {a.live:g}): his first "
                   "lap of search walking, scripts/time_budget.py route", "map": a.map,
                   "kind": rt["kind"], "waypoints": rt["waypoints"]}  # fmt: skip
            a.out.write_text(route_json(doc))
        info = {k: v for k, v in rt.items() if not k.startswith("_")}
        if walk is not None:
            info["gat"] = gat_check(rt["waypoints"], rt["_dense"], walk)
        print(json.dumps(info, indent=1))
        return 0
    if a.live is None:
        ap.error("compare needs --live S for the target's window")
    out = compare(a.target, a.sids, a.live, a.map)
    print(json.dumps(out, indent=1, default=str) if a.json else text(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
