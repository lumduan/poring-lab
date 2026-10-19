#!/usr/bin/env python3
"""The REVERSALS study (Batt 2026-10-19, decision 3: "Reversals rose back to ~7-8/min (v20 reached
~4). Find out why (engagement turns vs search heading) from banked runs and report; don't change
anything yet"). OFFLINE: packets are ground truth here (ADR-0007) and never a decision input
(rule 1); nothing in this module runs during play, and the bot (hunt_flow.py) never imports it.

    reversals_study.py SID [SID ...]          per session + pooled per version (JSON)
    reversals_study.py --rows SID [SID ...]   ... plus every reversal's attribution row

The ruler is flow_judge.heading_metrics', unchanged (``legs`` replays it leg by leg): from the
server's walk, each self_move is one LEG (its start to where our GM got before the next leg); a
REVERSAL is a heading change > 120 deg between consecutive legs of >= 2 cells (a 1-cell leg is
skipped: the turn is measured against the last leg of >= 2 cells). ``legs`` reconciles exactly
with heading_metrics on the same window (the reversal count and the turn histogram).

Each leg is ATTRIBUTED (``attribute``), and every reversal by its SECOND leg (the one that turned):
- MODE at the leg's start (the runner's ``mode`` events: search / steer / engaged; ``loot`` inside
  a loot step, [its end - its "s", its end] from the loot / loot_blobs / loot_fixed events; ``pre``
  before the first mode event);
- the CLICK behind it: the leg's self_move_request (the client's walk request, ~70-90 ms after
  our click), and the latest click of clicks.jsonl within CLICK_LAG_S before that request (kind
  walk + its why / strike / strike_burst / loot; "none" when no click of ours preceded it: the
  client's own re-request);
- the BOUNDARY: a new target picked within BOUNDARY_S before the click (dispatch / retarget /
  preempt / target_lost / target_reacquired: "new_target"), an engagement or a loot step ended
  within END_S before ("after_end"), a search heading TURN (a heading_goal event with turn != 0
  within HEADING_S before: "heading_turn"), or none;
- the CAUSE, one label per leg (``cause``): loot / strike / steer:new_target / steer:replan
  (a zone re-plan within BOUNDARY_S) / steer:approach / search:resume (the first leg of >= 2
  cells of a search span that follows a non-search span) / search:turn (a heading_goal turn
  within HEADING_S) / search:straight (the heading held: the route bent, stalled, re-planned) /
  walk:other (another walk why) / none:<mode>;
- the DECISION (``decision``): did the place the bot chose to go already point back (> 120 deg
  from the previous leg)? a search leg's heading (heading_goal's ang): heading_back / heading_ok;
  a steer / strike leg's target (the latest valid dispatch's cell): target_behind / target_ahead;
  a loot leg's cell: cell_behind / cell_ok;
- the PACKET phase, the same ruler for Batt's demo (no runner log there): "approach" = an attack
  request of ours follows within APPROACH_S with no kill between, else "post_kill" = a kill of
  ours within POST_KILL_S before, else "search" (time-based: a long bot steer reads as search).

Per session and pooled per version (``summarise`` / ``pool``): minutes per mode, legs / min and
cells walked / min, engagements and kills / min, reversals / min overall, BY CAUSE (also per
engagement), BY MODE (and per minute OF that mode), by the mode pair (first leg -> second leg), by
cause x decision and by the packet phase; the NET reversals of a cause (``reversals_without``:
the count with that cause's legs taken out of the heading chain); ``decompose`` splits a rate
change between two versions per mode into "more time in the mode" vs "more reversals per minute
of it".
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import re
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import flow_judge as fj  # noqa: E402

NS = fj.NS
GM = fj.GM
REV_DEG = 120.0  # heading_metrics' reversal
CLICK_LAG_S = 0.6  # our click -> the client's walk request (measured p50 ~0.08 s)
REQ_LAG_S = 1.0  # a self_move's request (the server answers at once: p50 ~0 ms)
BOUNDARY_S = 1.0  # a target pick this long before the click puts the leg on a boundary
END_S = 2.0  # an engagement / loot step ended this long before
HEADING_S = 2.0  # a search heading turn (heading_goal turn != 0) this long before
APPROACH_S = 4.0  # the packet ruler: an attack request this soon after the leg's request
POST_KILL_S = 5.0  # the packet ruler: a walk this soon after our kill (the loot walk proxy)
TARGET_S = 30.0  # the steer's target = the latest valid dispatch's cell, this recent
NEW_TARGET = ("dispatch", "retarget", "preempt", "target_lost", "target_reacquired")
LOOT_KINDS = ("loot", "loot_blobs", "loot_fixed")
MODES = ("search", "steer", "engaged", "loot", "pre")

Cell = tuple[int, int]


@dataclass
class Leg:
    i: int  # its index among the window's self_moves
    t: int  # the self_move's time
    p0: Cell
    p1: Cell
    n: int  # cells (Chebyshev)
    h_deg: float
    counted: bool  # n >= 2: it enters the turn histogram and sets the heading
    prev: int | None = None  # the leg (i) whose heading this one turned from
    turn_deg: float | None = None
    rev: bool = False
    t_req: int | None = None
    mode: str = ""
    click: dict[str, Any] | None = None
    boundary: str = "none"
    cause: str = ""
    pkt: str = ""
    info: dict[str, Any] = field(default_factory=dict)


# --- the ruler: heading_metrics leg by leg -------------------------------------------------------


def legs(events: Sequence[Mapping[str, Any]], t0: int, w1: int) -> list[Leg]:
    """PURE: flow_judge.heading_metrics' legs on [t0, w1), each with its turn and reversal flag.
    The same track (fj.gm_track), the same cut (where the next self_move starts), the same rule
    (> 120 deg between consecutive legs of >= 2 cells); legs of < 1 cell are dropped as there."""
    track, _mv = fj.gm_track(events)
    times = [p[0] for p in track]
    moves = [e for e in events if e.get("type") == "self_move" and t0 <= int(e["t_mono_ns"]) < w1]
    out: list[Leg] = []
    prev: Leg | None = None
    for i, (a, b) in enumerate(zip(moves, [*moves[1:], None], strict=True)):
        tb = int(b["t_mono_ns"]) if b is not None else w1
        p0 = (int(a["x0"]), int(a["y0"]))
        k = bisect.bisect_right(times, tb - 1)
        p1 = track[k - 1][1] if k > 0 else (int(a["x1"]), int(a["y1"]))
        n = fj.cheb(p0, p1)
        if n < 1:
            continue
        h = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
        leg = Leg(i, int(a["t_mono_ns"]), p0, p1, n, round(math.degrees(h), 2), n >= 2)
        leg.info["h"] = h  # the exact heading (h_deg is rounded for the rows)
        if n >= 2 and prev is not None:
            d = abs((h - float(prev.info["h"]) + math.pi) % (2 * math.pi) - math.pi)
            leg.prev, leg.turn_deg = prev.i, round(math.degrees(d), 6)
            leg.rev = d > math.radians(REV_DEG)
        out.append(leg)
        if n >= 2:
            prev = leg
    return out


def turn_hist(ls: Iterable[Leg]) -> list[int]:
    """PURE: heading_metrics' turn_hist_45 (<= 45 / <= 90 / <= 135 / > 135 deg) from legs."""
    hist = [0, 0, 0, 0]
    for leg in ls:
        if leg.turn_deg is not None:
            hist[min(3, max(0, math.ceil(round(leg.turn_deg, 6) / 45) - 1))] += 1
    return hist


# --- attribution ---------------------------------------------------------------------------------


def mode_track(bot_events: Sequence[Mapping[str, Any]]) -> tuple[list[int], list[str]]:
    """PURE: the runner's mode changes, sorted ([t], [mode])."""
    ms = sorted((int(e["t_ns"]), str(e["mode"])) for e in bot_events if e.get("kind") == "mode")
    return [t for t, _ in ms], [m for _, m in ms]


def loot_spans(bot_events: Sequence[Mapping[str, Any]]) -> list[tuple[int, int]]:
    """PURE: the loot steps [end - s, end] (loot / loot_blobs / loot_fixed events with an "s")."""
    out = []
    for e in bot_events:
        if e.get("kind") in LOOT_KINDS and e.get("s") is not None:
            z = int(e["t_ns"])
            out.append((z - int(float(e["s"]) * NS), z))
    return sorted(out)


def in_spans(spans: Sequence[tuple[int, int]], t: int) -> bool:
    k = bisect.bisect_right([a for a, _ in spans], t)
    return k > 0 and spans[k - 1][0] <= t <= spans[k - 1][1]


def mode_at(mt: tuple[list[int], list[str]], loots: Sequence[tuple[int, int]], t: int) -> str:
    """PURE: the runner's mode at t (``loot`` inside a loot step; ``pre`` before any mode)."""
    if in_spans(loots, t):
        return "loot"
    k = bisect.bisect_right(mt[0], t)
    return mt[1][k - 1] if k > 0 else "pre"


def mode_minutes(mt: tuple[list[int], list[str]], loots: Sequence[tuple[int, int]], t0: int,
                 w1: int) -> dict[str, float]:  # fmt: skip
    """PURE: minutes per mode on [t0, w1), loot steps carved out of the mode they sit in."""
    cuts = sorted({t0, w1, *(t for t in mt[0] if t0 < t < w1),
                   *(x for s in loots for x in s if t0 < x < w1)})  # fmt: skip
    out: Counter[str] = Counter()
    for a, b in zip(cuts, cuts[1:], strict=False):
        out[mode_at(mt, loots, (a + b) // 2)] += (b - a) / NS / 60
    return {m: round(out.get(m, 0.0), 3) for m in MODES}


def _before(ts: Sequence[int], t: int, within: int) -> int | None:
    """The latest of the sorted ts in (t - within, t], or None."""
    k = bisect.bisect_right(ts, t)
    return ts[k - 1] if k > 0 and t - ts[k - 1] < within else None


class Context:
    """The bot's own log and our packets, indexed for the attribution (PURE given its inputs)."""

    def __init__(self, events: Sequence[Mapping[str, Any]],
                 bot_events: Sequence[Mapping[str, Any]] = (),
                 clicks: Sequence[Mapping[str, Any]] = ()) -> None:  # fmt: skip
        self.reqs = sorted(int(e["t_mono_ns"]) for e in events
                           if e.get("type") == "self_move_request")  # fmt: skip
        self.attacks = sorted(int(e["t_mono_ns"]) for e in events
                              if e.get("type") == "attack_request")  # fmt: skip
        self.pickups = sorted(int(e["t_mono_ns"]) for e in events
                              if e.get("type") == "pickup_request")  # fmt: skip
        import arm_judge as aj

        self.kills = sorted(t for t, _g in aj.kills_of(events, GM))
        self.track, _mv = fj.gm_track(events)
        self.track_t = [p[0] for p in self.track]
        self.bot = bool(bot_events)
        self.mt = mode_track(bot_events)
        self.loots = loot_spans(bot_events)
        self.clicks = sorted(clicks, key=lambda c: int(c["t"]))
        self.click_t = [int(c["t"]) for c in self.clicks]
        nt = sorted((int(e["t_ns"]), str(e["kind"])) for e in bot_events
                    if e.get("kind") in NEW_TARGET
                    and (e.get("kind") != "dispatch" or e.get("valid", True)))  # fmt: skip
        self.new_target = [t for t, _k in nt]
        self.new_target_kind = [k for _t, k in nt]
        self.ends = sorted([int(e["t_ns"]) for e in bot_events if e.get("kind") == "engagement"]
                           + [z for _a, z in self.loots])  # fmt: skip
        tu = sorted((int(e["t_ns"]), abs(float(e.get("turn") or 0.0))) for e in bot_events
                    if e.get("kind") == "heading_goal"
                    and abs(float(e.get("turn") or 0.0)) > 0)  # fmt: skip
        self.turns = [t for t, _d in tu]
        self.turn_deg = [d for _t, d in tu]
        self.engagements = sorted(int(e["t_ns"]) for e in bot_events
                                  if e.get("kind") == "engagement")  # fmt: skip
        hd = sorted((int(e["t_ns"]), float(e["ang"])) for e in bot_events
                    if e.get("kind") == "heading_goal" and e.get("ang") is not None)  # fmt: skip
        self.heading_t = [t for t, _a in hd]
        self.heading_ang = [a for _t, a in hd]
        dc = sorted((int(e["t_ns"]), (float(e["cell"][0]), float(e["cell"][1])))
                    for e in bot_events if e.get("kind") == "dispatch"
                    and e.get("valid", True) and e.get("cell"))  # fmt: skip
        self.dispatch_t = [t for t, _c in dc]
        self.dispatch_cell = [c for _t, c in dc]
        self.replans = sorted(int(e["t_ns"]) for e in bot_events if e.get("kind") == "zone_plan"
                              and e.get("replan"))  # fmt: skip


def packet_phase(ctx: Context, t_req: int) -> str:
    """PURE: the leg by our packets only, the same ruler for Batt's demo (no runner log there):
    "approach" = an attack request of ours follows within APPROACH_S with no kill of ours in
    between (the turn went toward a target); else "post_kill" = a kill of ours within POST_KILL_S
    before (the loot / leaving walk); else "search"."""
    k = bisect.bisect_left(ctx.attacks, t_req)
    if k < len(ctx.attacks) and ctx.attacks[k] - t_req <= APPROACH_S * NS:
        j = bisect.bisect_left(ctx.kills, t_req)
        if not (j < len(ctx.kills) and ctx.kills[j] < ctx.attacks[k]):
            return "approach"
    if _before(ctx.kills, t_req, int(POST_KILL_S * NS)) is not None:
        return "post_kill"
    return "search"


def cause(leg: Leg, resume: bool) -> str:
    """PURE: the one-label cause of a leg from its mode, click and boundary (module docstring)."""
    c = leg.click
    kind = c.get("kind") if c else None
    why = c.get("why") if c else None
    if kind == "loot" or (c is None and leg.mode == "loot"):
        return "loot"
    if kind in ("strike", "strike_burst"):
        return "strike"
    if kind == "walk" and why == "steer":
        if leg.boundary == "new_target":
            return "steer:new_target"
        return "steer:replan" if leg.info.get("replan") else "steer:approach"
    if kind == "walk" and why == "search":
        if resume:
            return "search:resume"
        return "search:turn" if leg.boundary == "heading_turn" else "search:straight"
    if kind == "walk":
        return "walk:other"
    return f"none:{leg.mode}"


def attribute(ls: Sequence[Leg], ctx: Context) -> list[Leg]:
    """PURE (given ctx): fills each leg's request, mode, click, boundary, cause and packet phase
    in place, and returns the legs."""
    last_mode_counted: str | None = None  # the mode of the last leg of >= 2 cells
    for leg in ls:
        leg.t_req = _before(ctx.reqs, leg.t, int(REQ_LAG_S * NS))
        anchor = leg.t_req if leg.t_req is not None else leg.t
        leg.pkt = packet_phase(ctx, anchor)
        if not ctx.bot:
            continue
        leg.mode = mode_at(ctx.mt, ctx.loots, anchor)
        tc = _before(ctx.click_t, anchor, int(CLICK_LAG_S * NS))
        if tc is not None:
            c = ctx.clicks[bisect.bisect_right(ctx.click_t, tc) - 1]
            leg.click = {"kind": c.get("kind"), "why": c.get("why"),
                         "dt_ms": round((anchor - tc) / 1e6)}  # fmt: skip
            plan(leg, c, ctx)
            anchor = tc
        tn = _before(ctx.new_target, anchor, int(BOUNDARY_S * NS))
        if tn is not None:
            leg.boundary = "new_target"
            leg.info["nt_kind"] = ctx.new_target_kind[bisect.bisect_right(ctx.new_target, tn) - 1]
        elif _before(ctx.ends, anchor, int(END_S * NS)) is not None:
            leg.boundary = "after_end"
        elif _before(ctx.turns, anchor, int(HEADING_S * NS)) is not None:
            leg.boundary = "heading_turn"
        th = _before(ctx.turns, anchor, int(HEADING_S * NS))
        if th is not None:
            leg.info["heading_turn"] = ctx.turn_deg[bisect.bisect_right(ctx.turns, th) - 1]
        leg.info["replan"] = _before(ctx.replans, anchor, int(BOUNDARY_S * NS)) is not None
        k = bisect.bisect_right(ctx.heading_t, anchor)
        if k > 0:
            leg.info["heading_deg"] = ctx.heading_ang[k - 1]
        td = _before(ctx.dispatch_t, anchor, int(TARGET_S * NS))
        if td is not None:
            leg.info["target_cell"] = list(
                ctx.dispatch_cell[bisect.bisect_right(ctx.dispatch_t, td) - 1]
            )
        leg.info["start"] = last_mode_counted == "search"  # the previous leg was a search leg
        resume = (leg.counted and leg.mode == "search"
                  and last_mode_counted not in (None, "search"))  # fmt: skip
        leg.cause = cause(leg, resume)
        if leg.counted:
            last_mode_counted = leg.mode
    return ls


def _deg(a: Sequence[float], b: Sequence[float]) -> float | None:
    if abs(b[0] - a[0]) < 1e-9 and abs(b[1] - a[1]) < 1e-9:
        return None
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def plan(leg: Leg, c: Mapping[str, Any], ctx: Context) -> None:
    """PURE (given ctx): the click's PLAN beside what the server did. ``target`` = the cell the
    click meant (a walk's "to", a loot's "cell", a strike's "pred_cell"); ``gm`` = our GM's
    server cell at the click; for a walk click with "at" (the runner's measured cell) the plan's
    origin = at + its "lead" (where the runner put the GM when the client resolves the click).
    plan_deg = origin -> target, true_deg = gm -> target, lag_cells = gm - origin (Chebyshev)."""
    tgt = c.get("to") or c.get("cell") or c.get("pred_cell")
    if not tgt:
        return
    k = bisect.bisect_right(ctx.track_t, int(c["t"]))
    gm = ctx.track[k - 1][1] if k > 0 else None
    leg.info["target"] = [float(tgt[0]), float(tgt[1])]
    if gm is not None:
        leg.info["gm"] = list(gm)
        leg.info["true_deg"] = _deg(gm, tgt)
    if c.get("at") is not None:
        lead = c.get("lead") or [0.0, 0.0]
        org = (float(c["at"][0]) + float(lead[0]), float(c["at"][1]) + float(lead[1]))
        leg.info["origin"] = [round(org[0], 2), round(org[1], 2)]
        leg.info["plan_deg"] = _deg(org, tgt)
        if gm is not None:
            leg.info["lag_cells"] = round(max(abs(gm[0] - org[0]), abs(gm[1] - org[1])), 2)


def _dang(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def decision(leg: Leg, prev: Leg | None) -> str:
    """PURE: did the reversal come from WHERE THE BOT DECIDED TO GO, or from how the click got
    there? Against the previous leg's heading (> 120 deg = "back"):
    - a search leg: the SEARCH HEADING (the latest heading_goal's ang) -> "heading_back" (the
      remembered / chosen heading itself points back) or "heading_ok" (the heading did not
      reverse: the route / the click point did);
    - a steer / strike leg: the TARGET (the latest valid dispatch's cell, from the GM's server
      cell at the click) -> "target_behind" or "target_ahead";
    - a loot leg: the loot cell from the GM's cell -> "cell_behind" or "cell_ok";
    - "unknown" when the angle is not available."""
    if prev is None:
        return "unknown"
    c = leg.cause
    if c.startswith("search:"):
        hd = leg.info.get("heading_deg")
        if hd is None:
            return "unknown"
        return "heading_back" if _dang(float(hd), prev.h_deg) > REV_DEG else "heading_ok"
    gm = leg.info.get("gm")
    if c.startswith("steer:") or c == "strike":
        tc = leg.info.get("target_cell")
        d = _deg(gm, tc) if gm is not None and tc is not None else None
        if d is None:
            return "unknown"
        return "target_behind" if _dang(d, prev.h_deg) > REV_DEG else "target_ahead"
    if c == "loot":
        d = leg.info.get("true_deg")
        if d is None:
            return "unknown"
        return "cell_behind" if _dang(float(d), prev.h_deg) > REV_DEG else "cell_ok"
    return "unknown"


def reversals_without(ls: Sequence[Leg], drop: Iterable[str]) -> int:
    """PURE: the reversals heading_metrics would count if the legs whose cause is in ``drop``
    left the heading chain (each other leg then turns from the last KEPT leg of >= 2 cells):
    total - this = the NET reversals those legs add (a loot leg between an approach and a resume
    can turn one reversal into two, or none into one)."""
    drop_ = set(drop)
    rev, prev_h = 0, None
    for leg in ls:
        if not leg.counted or leg.cause in drop_:
            continue
        h = float(leg.info["h"])
        if prev_h is not None:
            d = abs((h - prev_h + math.pi) % (2 * math.pi) - math.pi)
            rev += d > math.radians(REV_DEG)
        prev_h = h
    return rev


# --- tables --------------------------------------------------------------------------------------


def _rate(n: float, mins: float) -> float:
    return round(n / mins, 2) if mins > 0 else 0.0


NET_GROUPS = {
    "loot": ("loot",),
    "strike": ("strike",),
    "steer:new_target": ("steer:new_target",),
    "steer:approach+replan": ("steer:approach", "steer:replan"),
    "search:resume": ("search:resume",),
    "search:turn": ("search:turn",),
    "search:straight": ("search:straight",),
    "engagement(steer+strike+loot)": ("steer:new_target", "steer:approach", "steer:replan",
                                      "strike", "loot"),
}  # fmt: skip


def _turn_bucket(deg: float | None) -> str:
    if deg is None:
        return "none"
    return next((f"<={b}" for b in (44, 45, 90, 135) if deg <= b + 0.5), "180")


def _lag_bucket(x: float | None) -> str:
    if x is None:
        return "none"
    return next((f"<={b}" for b in (1, 2, 3, 5) if x <= b), ">5")


def counts(ls: Sequence[Leg], mins: float, mode_mins: Mapping[str, float] | None = None,
           extra: Mapping[str, Any] | None = None) -> dict[str, Any]:  # fmt: skip
    """PURE: the raw counts of one session (summed over runs by ``pool``)."""
    by_i = {leg.i: leg for leg in ls}
    revs = [leg for leg in ls if leg.rev]
    pair = Counter(f"{by_i[r.prev].mode if r.prev in by_i else '?'}>{r.mode}" for r in revs)
    pcause = Counter(f"{by_i[r.prev].cause if r.prev in by_i else '?'}>{r.cause}" for r in revs)

    def nt(leg: Leg) -> str:
        return f"{'start' if leg.info.get('start') else 'switch'}:{leg.info.get('nt_kind')}"

    steer_nt = [leg for leg in ls if leg.counted and leg.cause == "steer:new_target"]
    return {
        "minutes": mins,
        "mode_minutes": dict(mode_mins or {}),
        **dict(extra or {}),
        "legs": len(ls),
        "legs2": sum(leg.counted for leg in ls),
        "cells": sum(leg.n for leg in ls),
        "reversals": len(revs),
        "rev135": sum(1 for r in revs if (r.turn_deg or 0) > 135),
        "by_cause": dict(Counter(r.cause for r in revs)),
        "by_mode": dict(Counter(r.mode for r in revs)),
        "by_boundary": dict(Counter(r.boundary for r in revs)),
        "by_pkt": dict(Counter(r.pkt for r in revs)),
        "by_pair": dict(pair),
        "by_cause_pair": dict(pcause),
        "legs2_by_cause": dict(Counter(leg.cause for leg in ls if leg.counted)),
        "legs2_by_mode": dict(Counter(leg.mode for leg in ls if leg.counted)),
        "legs2_by_pkt": dict(Counter(leg.pkt for leg in ls if leg.counted)),
        "cells_by_mode": dict(sum((Counter({leg.mode: leg.n}) for leg in ls), Counter())),
        "click_kinds": dict(Counter((leg.click or {}).get("kind") or "none" for leg in ls)),
        "steer_nt_rev": dict(Counter(nt(r) for r in revs if r.cause == "steer:new_target")),
        "steer_nt_legs2": dict(Counter(nt(leg) for leg in steer_nt)),
        "search_turn_rev_by_deg": dict(Counter(_turn_bucket(r.info.get("heading_turn"))
                                               for r in revs if r.cause == "search:turn")),
        "resume_rev_heading_turned": dict(Counter(_turn_bucket(r.info.get("heading_turn"))
                                                  for r in revs if r.cause == "search:resume")),
        "net": {k: len(revs) - reversals_without(ls, v) for k, v in NET_GROUPS.items()},
        "by_cause_decision": dict(Counter(f"{r.cause}|{decision(r, by_i.get(r.prev))}"
                                          for r in revs)),
        "lag_cells_rev": dict(Counter(_lag_bucket(r.info.get("lag_cells")) for r in revs
                                      if r.click and r.click.get("kind") == "walk")),
    }  # fmt: skip


def pool(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """PURE: sums the counts of several sessions (runs of one version)."""
    out: dict[str, Any] = {}
    for r in rows:
        for k, v in r.items():
            if isinstance(v, dict):
                acc = out.setdefault(k, {})
                for kk, vv in v.items():
                    acc[kk] = acc.get(kk, 0) + vv
            elif isinstance(v, int | float):
                out[k] = out.get(k, 0) + v
    return out


def summarise(c: Mapping[str, Any]) -> dict[str, Any]:
    """PURE: rates and shares from (pooled) counts."""
    mins = float(c["minutes"])
    mm = c.get("mode_minutes") or {}
    nrev = int(c["reversals"])
    neng = int(c.get("engagements", 0))

    def table(d: Mapping[str, int]) -> dict[str, dict[str, float]]:
        return {k: {"n": v, "per_min": _rate(v, mins),
                    "share": round(v / nrev, 3) if nrev else 0.0}
                for k, v in sorted(d.items(), key=lambda kv: -kv[1])}  # fmt: skip

    per_mode = {}
    for m, mn in mm.items():
        if mn <= 0:
            continue
        r = int(c["by_mode"].get(m, 0))
        l2 = int(c["legs2_by_mode"].get(m, 0))
        per_mode[m] = {"minutes": round(mn, 2), "time_share": round(mn / mins, 3),
                       "reversals": r, "rev_per_mode_min": _rate(r, mn),
                       "legs2_per_mode_min": _rate(l2, mn),
                       "rev_per_leg2": round(r / l2, 3) if l2 else None,
                       "cells_per_mode_min": _rate(int(c["cells_by_mode"].get(m, 0)),
                                                   mn)}  # fmt: skip
    per_cause_leg = {k: {"legs2": v, "reversals": int(c["by_cause"].get(k, 0)),
                         "rev_per_leg2": round(int(c["by_cause"].get(k, 0)) / v, 3)}
                     for k, v in sorted(c["legs2_by_cause"].items(),
                                        key=lambda kv: -kv[1])}  # fmt: skip
    return {
        "minutes": round(mins, 2),
        "reversals_per_min": _rate(nrev, mins),
        "reversals135_per_min": _rate(int(c["rev135"]), mins),
        "legs_per_min": _rate(int(c["legs"]), mins),
        "legs2_per_min": _rate(int(c["legs2"]), mins),
        "cells_per_min": round(int(c["cells"]) / mins, 1) if mins else 0.0,
        "rev_per_leg2": round(nrev / int(c["legs2"]), 3) if c["legs2"] else None,
        "by_cause": table(c["by_cause"]),
        "by_mode": table(c["by_mode"]),
        "per_mode": per_mode,
        "by_boundary": table(c["by_boundary"]),
        "by_pkt": table(c["by_pkt"]),
        "by_pair": table(c["by_pair"]),
        "by_cause_pair_top": dict(list(table(c["by_cause_pair"]).items())[:12]),
        "cause_leg_rates": per_cause_leg,
        "pkt_leg_rates": {k: {"legs2": v, "reversals": int(c["by_pkt"].get(k, 0)),
                              "rev_per_leg2": round(int(c["by_pkt"].get(k, 0)) / v, 3)}
                          for k, v in sorted(c["legs2_by_pkt"].items(), key=lambda kv: -kv[1])},
        "engagements_per_min": _rate(int(c.get("engagements", 0)), mins),
        "kills_per_min": _rate(int(c.get("kills", 0)), mins),
        "rev_per_engagement": ({k: round(v / neng, 3) for k, v in
                                sorted(c["by_cause"].items(), key=lambda kv: -kv[1])}
                               | {"total": round(nrev / neng, 3)}) if neng else None,
        "net_per_min": {k: _rate(v, mins) for k, v in (c.get("net") or {}).items()},
        "steer_new_target": {k: {"rev": int(c.get("steer_nt_rev", {}).get(k, 0)), "legs2": v,
                                 "rev_per_min": _rate(int(c.get("steer_nt_rev", {}).get(k, 0)),
                                                      mins)}
                             for k, v in sorted((c.get("steer_nt_legs2") or {}).items(),
                                                key=lambda kv: -kv[1])},
        "by_cause_decision": table(c.get("by_cause_decision") or {}),
        "lag_cells_rev": c.get("lag_cells_rev"),
        "search_turn_rev_by_deg": c.get("search_turn_rev_by_deg"),
        "resume_rev_heading_turned": c.get("resume_rev_heading_turned"),
        "heading_turns_per_search_min": {k: _rate(v, float(mm.get("search", 0.0)))
                                         for k, v in sorted((c.get("heading_turns")
                                                             or {}).items())},
    }  # fmt: skip


def decompose(a: Mapping[str, Any], b: Mapping[str, Any]) -> dict[str, Any]:
    """PURE: the change in reversals / min from summary a to summary b, per mode, split
    (midpoint) into TIME (the mode's share of the run changed) and RATE (reversals per minute of
    the mode changed): d = sum_m (s_b r_b - s_a r_a) = sum_m [(s_b - s_a) (r_a + r_b) / 2 +
    (r_b - r_a) (s_a + s_b) / 2]. The two parts sum to the change (up to rounding)."""
    out: dict[str, Any] = {}
    tot_t = tot_r = 0.0
    for m in sorted(set(a["per_mode"]) | set(b["per_mode"])):
        pa = a["per_mode"].get(m, {"time_share": 0.0, "rev_per_mode_min": 0.0})
        pb = b["per_mode"].get(m, {"time_share": 0.0, "rev_per_mode_min": 0.0})
        sa, sb = float(pa["time_share"]), float(pb["time_share"])
        ra, rb = float(pa["rev_per_mode_min"]), float(pb["rev_per_mode_min"])
        dt, dr = (sb - sa) * (ra + rb) / 2, (rb - ra) * (sa + sb) / 2
        out[m] = {"time": round(dt, 2), "rate": round(dr, 2), "total": round(dt + dr, 2)}
        tot_t += dt
        tot_r += dr
    seen = b["reversals_per_min"] - a["reversals_per_min"]
    out["sum"] = {"time": round(tot_t, 2), "rate": round(tot_r, 2),
                  "total": round(tot_t + tot_r, 2), "observed": round(seen, 2)}  # fmt: skip
    cause_d = {}
    for k in sorted(set(a["by_cause"]) | set(b["by_cause"])):
        ra_ = a["by_cause"].get(k, {"per_min": 0.0})["per_min"]
        rb_ = b["by_cause"].get(k, {"per_min": 0.0})["per_min"]
        cause_d[k] = round(rb_ - ra_, 2)
    out["by_cause"] = dict(sorted(cause_d.items(), key=lambda kv: -abs(kv[1])))
    return out


# --- sessions ------------------------------------------------------------------------------------


def version_of(sid: str) -> str:
    m = re.search(r"hunt-flow(\d+)$", sid)
    return f"v{int(m.group(1))}" if m else "human" if sid.endswith("human-demo") else sid


def study(sid: str, root: Path | None = None) -> dict[str, Any]:
    """One banked session on flow_judge's window (search_study.load_session): its legs, their
    attribution and counts."""
    import search_study as ss

    sess = ss.load_session(sid, root)
    d = (root or _demo_root()) / sid
    clicks: list[dict[str, Any]] = []
    if sess.bot and (d / "clicks.jsonl").exists():
        clicks = [json.loads(x) for x in (d / "clicks.jsonl").read_text().splitlines() if x]
    ctx = Context(sess.events, sess.bot_events, clicks)
    ls = attribute(legs(sess.events, sess.t0, sess.w1), ctx)
    mins = (sess.w1 - sess.t0) / NS / 60
    mm = mode_minutes(ctx.mt, ctx.loots, sess.t0, sess.w1) if sess.bot else {}
    return {"sid": sid, "version": version_of(sid), "t0": sess.t0, "w1": sess.w1, "legs": ls,
            "counts": counts(ls, mins, mm, window_extra(ctx, sess.t0, sess.w1)),
            "turn_hist_45": turn_hist(ls)}  # fmt: skip


def window_extra(ctx: Context, t0: int, w1: int) -> dict[str, Any]:
    """PURE: the window's engagements (the runner's ends), our kills (packets) and the search
    heading's turns by size (heading_goal events)."""

    def inw(ts: Sequence[int]) -> int:
        return bisect.bisect_left(ts, w1) - bisect.bisect_left(ts, t0)

    turns = Counter(_turn_bucket(d) for t, d in zip(ctx.turns, ctx.turn_deg, strict=True)
                    if t0 <= t < w1)  # fmt: skip
    return {"engagements": inw(ctx.engagements), "kills": inw(ctx.kills),
            "heading_turns": dict(turns)}  # fmt: skip


def _demo_root() -> Path:
    from poring_env.demo import DEMO_ROOT

    return Path(DEMO_ROOT)


def row(leg: Leg, prev: Leg | None) -> dict[str, Any]:
    o = asdict(leg)
    o.pop("info", None)
    o["prev_mode"] = prev.mode if prev else None
    o["prev_cause"] = prev.cause if prev else None
    o["prev_n"] = prev.n if prev else None
    o["gap_s"] = round((leg.t - prev.t) / NS, 2) if prev else None
    return o


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("sids", nargs="+")
    ap.add_argument("--rows", action="store_true", help="every reversal's attribution row")
    a = ap.parse_args()
    per_v: dict[str, list[dict[str, Any]]] = {}
    sessions = {}
    rows = {}
    skipped = {}
    for sid in a.sids:
        try:
            s = study(sid)
        except SystemExit as e:  # search_study.load_session: nothing to judge
            skipped[sid] = str(e)
            continue
        per_v.setdefault(s["version"], []).append(s["counts"])
        sessions[sid] = {"version": s["version"], **summarise(s["counts"]), "counts": s["counts"]}
        if a.rows:
            by_i = {leg.i: leg for leg in s["legs"]}
            rows[sid] = [row(leg, by_i.get(leg.prev)) for leg in s["legs"] if leg.rev]
    versions = {v: {"runs": len(cs), **summarise(pool(cs))} for v, cs in per_v.items()}
    out: dict[str, Any] = {"sessions": sessions, "versions": versions, "skipped": skipped}
    if rows:
        out["rows"] = rows
    json.dump(out, sys.stdout, indent=1, default=str)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
