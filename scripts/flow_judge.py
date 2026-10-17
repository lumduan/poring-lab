#!/usr/bin/env python3
"""hunt-flow's judge (demonstrations.md 3.40, pre-registered 2026-10-16 09:54 BEFORE any analysis):
CLICK -> WALK IN -> HIT LANDS, from packets OFFLINE (never a decision input). The same functions
judge Batt's human demonstration and every hunt-flow version, so the two compare directly.

    flow_judge.py human SESSION        Batt's played demo (human_demo.py): clicks from his input log
    flow_judge.py bot SESSION          a hunt-flow run: clicks from the runner's clicks.jsonl

Per TRIAL (an attack click, or a click on a detector monster box; not a follow-up click on a unit
we acted on in the 3 s before): HIT = a damaging act of ours on its unit G within T_HIT. Also the
reaction (first seen -> click -> hit), the range at the click, idle %, walk-click spacing and
cadence, target choice and switches, kills / h.
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import json
import math
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

Cell = tuple[int, int]
GM = 2000002
GM_MS_CELL = 150.0  # the GM's walk speed (hunt@5's packets)
DIAG = 1.4  # a diagonal step takes 14/10 of a straight one (rAthena)
WINDOW_S = 600.0
T_HIT = 3.0
T_REQ = 1.5
T_WALK = 1.0
BOX_PAD = 6.0
BOX_AGE = 0.5
NEAR = 2
SEEN_NEAR = 1.5
SEEN_GAP = 2.0
SEEN_BACK = 30.0
FOLLOW = 3.0
VIEW = 14
NS = 10**9
W_S = 5.0  # 3.41: the hit must land within W of the FIRST attack click (Batt's re-hit p90 + 0.7 s)
REHIT_NEAR = 6  # the human reference: a failed click's unit, within this of the picked cell


@dataclass
class Click:
    t: int
    u: float  # client px
    v: float
    kind: str = ""  # bot: "strike" | "walk" (what the runner meant); human: ""


@dataclass
class Trial:
    t: int
    u: float
    v: float
    gid: int | None
    # hit | walk_only | request_no_act | miss_only | other_unit | no_unit | no_response
    outcome: str
    t_hit: int | None = None
    t_seen: int | None = None
    range_cells: int | None = None
    rank: int | None = None
    switch: bool = False
    info: dict[str, Any] = field(default_factory=dict)


# --- tracks ---------------------------------------------------------------------------------------


def cheb(a: Cell, b: Cell) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def steps(a: Cell, b: Cell) -> list[Cell]:
    """Chebyshev steps a -> b, diagonal first (as hunt_core.walk_positions)."""
    out, (x, y) = [], a
    while (x, y) != b:
        x += (b[0] > x) - (b[0] < x)
        y += (b[1] > y) - (b[1] < y)
        out.append((x, y))
    return out


def gm_track(events: Sequence[Mapping[str, Any]], ms_cell: float = GM_MS_CELL
             ) -> tuple[list[tuple[int, Cell]], list[tuple[int, int]]]:  # fmt: skip
    """Our GM: (t, cell) points along each self_move (a step per cell, diagonals x1.4) and the
    pins (entity_stop of our gid, map_change), plus its MOVING intervals [(t0, t1)]."""
    pts: list[tuple[int, Cell]] = []
    moving: list[tuple[int, int]] = []
    for e in events:
        t = int(e["t_mono_ns"])
        typ = e.get("type")
        if typ == "self_move":
            pts = [p for p in pts if p[0] <= t]
            if moving and moving[-1][1] > t:
                moving[-1] = (moving[-1][0], t)
            a, b = (int(e["x0"]), int(e["y0"])), (int(e["x1"]), int(e["y1"]))
            pts.append((t, a))
            tt, prev = float(t), a
            for c in steps(a, b):
                diag = c[0] != prev[0] and c[1] != prev[1]
                tt += ms_cell * (DIAG if diag else 1.0) * 1e6
                pts.append((int(tt), c))
                prev = c
            moving.append((t, int(tt)))
        elif (typ == "entity_stop" and gid_of(e) == GM) or typ == "map_change":
            pts = [p for p in pts if p[0] <= t] + [(t, (int(e["x"]), int(e["y"])))]
            if moving and moving[-1][1] > t:
                moving[-1] = (moving[-1][0], t)
    pts.sort(key=lambda p: p[0])
    return pts, moving


def at(track: Sequence[tuple[int, Cell]], t: int) -> Cell | None:
    last = None
    for tm, c in track:
        if tm > t:
            break
        last = c
    return last


def mob_at(pos: Mapping[int, Sequence[tuple[int, Cell, int]]], g: int, t: int) -> Cell | None:
    last = None
    for tm, c, _j in pos.get(g, ()):
        if tm > t:
            break
        last = c
    return last


def alive(events: Sequence[Mapping[str, Any]]
          ) -> dict[int, list[tuple[int, int | None, int | None]]]:  # fmt: skip
    """gid -> EVERY life [(appear t, vanish t or None, vanish reason)] of mobs (objtype 5).
    rAthena reuses a dead mob's block id for a later spawn (found 2026-10-16: 110019414 died at
    Batt's t0+214 s and a new Poring had the id at t0+271 s), so one gid can have several lives."""
    out: dict[int, list[tuple[int, int | None, int | None]]] = {}
    for e in events:
        g = gid_of(e)
        t = int(e["t_mono_ns"])
        if e.get("type") == "entity_appear" and e.get("objtype") == 5:
            lives = out.setdefault(g, [])
            if not lives or lives[-1][1] is not None:
                lives.append((t, None, None))
        elif e.get("type") == "entity_vanish" and out.get(g) and out[g][-1][1] is None:
            out[g][-1] = (out[g][-1][0], t, int(e.get("reason", -1)))
    return out


def gid_of(e: Mapping[str, Any], key: str = "gid") -> int:
    """An event's unit id; -1 when absent or null (pseudonymised players carry none)."""
    v = e.get(key)
    return -1 if v is None else int(v)


def present(life: Mapping[int, Sequence[tuple[int, int | None, int | None]]], g: int,
            t: int) -> bool:  # fmt: skip
    return any(a <= t and (b is None or t < b) for a, b, _ in life.get(g, ()))


def died_before(life: Mapping[int, Sequence[tuple[int, int | None, int | None]]], g: int, t: int,
                within_s: float) -> bool:  # fmt: skip
    """``g`` died (reason 1) in the ``within_s`` before ``t``."""
    return any(b is not None and r_ == 1 and 0 <= t - b <= within_s * NS
               for _a, b, r_ in life.get(g, ()))  # fmt: skip


def moving_share(moving: Sequence[tuple[int, int]], w0: int, w1: int) -> float:
    tot = sum(max(0, min(b, w1) - max(a, w0)) for a, b in moving)
    return tot / max(1, w1 - w0)


def is_moving(moving: Sequence[tuple[int, int]], t: int) -> bool:
    return any(a <= t < b for a, b in moving)


# --- inputs ---------------------------------------------------------------------------------------


def human_clicks(lines: Iterable[str], desktop: tuple[int, int],
                 region: tuple[int, int, int, int]) -> list[Click]:  # fmt: skip
    """Accepted left button downs of source=human inside the game region, in client px (the UI
    test is applied by the judge)."""
    gx, gy, gw, gh = region
    out = []
    for line in lines:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        e = r.get("event", {})
        if (r.get("source") != "human" or not r.get("accepted") or e.get("type") != "mouse_button"
                or e.get("button") != "left" or e.get("action") != "down"):  # fmt: skip
            continue
        u, v = float(e["x"]) * desktop[0] - gx, float(e["y"]) * desktop[1] - gy
        if 0 <= u < gw and 0 <= v < gh:
            out.append(Click(int(r["t_mono_ns"]), u, v))
    return out


def t0_of(events: Sequence[Mapping[str, Any]], t_from: int) -> int | None:
    return next((int(e["t_mono_ns"]) for e in events
                 if e.get("type") == "self_move_request" and int(e["t_mono_ns"]) >= t_from),
                None)  # fmt: skip


def box_at(frames: Sequence[tuple[int, list[list[Any]]]], t: int, u: float, v: float,
           pad: float = BOX_PAD, age_s: float = BOX_AGE) -> list[Any] | None:  # fmt: skip
    """The monster box under (u, v) on the newest detector frame captured <= age_s before t."""
    best = None
    for tf, boxes in frames:
        if tf > t:
            break
        best = (tf, boxes)
    if best is None or t - best[0] > age_s * NS:
        return None
    for b in best[1]:
        if b[5] == "monster" and b[0] - pad <= u <= b[2] + pad and b[1] - pad <= v <= b[3] + pad:
            return b
    return None


# --- the judge ------------------------------------------------------------------------------------


def classify(click_t: int, next_t: int | None, events: Sequence[Mapping[str, Any]]
             ) -> dict[str, Any]:  # fmt: skip
    """What followed a click (packets): the first attack request within T_REQ (and before the
    next click), the first self_move_request within T_WALK, NPC contact / pickup."""
    lim_req = click_t + int(T_REQ * NS)
    if next_t is not None:
        lim_req = min(lim_req, next_t)
    out: dict[str, Any] = {"request": None, "move": None, "npc": False, "pickup": False}
    for e in events:
        t = int(e["t_mono_ns"])
        if t < click_t:
            continue
        if t > click_t + int(T_REQ * NS):
            break
        typ = e.get("type")
        if typ == "attack_request" and t <= lim_req and out["request"] is None:
            out["request"] = (t, int(e["target_gid"]))
        elif typ == "self_move_request" and t <= click_t + int(T_WALK * NS) and out["move"] is None:
            out["move"] = (t, (int(e["x"]), int(e["y"])))
        elif typ == "npc_contact" and t <= lim_req:
            out["npc"] = True
        elif typ == "pickup_request" and t <= lim_req:
            out["pickup"] = True
    return out


def judge(events: Sequence[Mapping[str, Any]], clicks: Sequence[Click],
          frames: Sequence[tuple[int, list[list[Any]]]], t0: int, pick: Any,
          in_ui: Any = lambda u, v: False,
          window_s: float = WINDOW_S) -> dict[str, Any]:  # fmt: skip
    """``pick(origin_cell, (u, v)) -> cell`` maps a client pixel to the cell the client picks;
    ``in_ui(u, v)`` excludes clicks on the fixed UI. Everything within [t0, t0 + window]."""
    import hunt_core as hc

    events = sorted(events, key=lambda e: int(e["t_mono_ns"]))
    w1 = t0 + int(window_s * NS)
    track, moving = gm_track(events)
    pos = hc.walk_positions(events)
    life = alive(events)
    ours = [e for e in events if e.get("type") == "act" and int(e.get("src_gid", -1)) == GM
            and e.get("kind") != "pickup"]  # fmt: skip
    clicks = sorted((c for c in clicks if t0 <= c.t < w1 and not in_ui(c.u, c.v)),
                    key=lambda c: c.t)  # fmt: skip
    trials: list[Trial] = []
    walks: list[dict[str, Any]] = []
    counts = {"clicks": len(clicks), "follow_up": 0, "npc_click": 0, "pickup_click": 0,
              "walk_click": 0, "other_click": 0}  # fmt: skip
    for i, c in enumerate(clicks):
        nxt = clicks[i + 1].t if i + 1 < len(clicks) else None
        f = classify(c.t, nxt, events)
        here = at(track, c.t)
        box = box_at(frames, c.t, c.u, c.v)
        if f["npc"]:
            counts["npc_click"] += 1
            continue
        if f["pickup"] and f["request"] is None:
            counts["pickup_click"] += 1
            continue
        attack = f["request"] is not None or c.kind == "strike" or box is not None
        if not attack:
            if f["move"] is not None and here is not None:
                counts["walk_click"] += 1
                walks.append({"t": c.t, "spacing": cheb(here, f["move"][1]),
                              "while_moving": is_moving(moving, c.t)})  # fmt: skip
            else:
                counts["other_click"] += 1
            continue
        picked = pick(here, (c.u, c.v)) if here is not None else None
        nearest = None
        if picked is not None:
            cands = [(cheb(picked, mc), g) for g in pos
                     if present(life, g, c.t)
                     and (mc := mob_at(pos, g, c.t)) is not None]  # fmt: skip
            cands = [x for x in cands if x[0] <= NEAR]
            nearest = min(cands)[1] if cands else None
        if f["request"] is not None:
            g: int | None = f["request"][1]
        else:
            g = nearest
        if g is not None and any(c.t - FOLLOW * NS <= int(a["t_mono_ns"]) < c.t
                                 and int(a["target_gid"]) == g for a in ours):  # fmt: skip
            counts["follow_up"] += 1
            continue
        tr = Trial(c.t, c.u, c.v, g, "no_response")
        if g is None:
            tr.outcome = "no_unit"
        else:
            hits = [a for a in ours if int(a["target_gid"]) == g
                    and c.t < int(a["t_mono_ns"]) <= c.t + int(T_HIT * NS)]  # fmt: skip
            dmg = [a for a in hits if int(a.get("damage", 0)) + int(a.get("damage2", 0)) > 0]
            if dmg:
                tr.outcome, tr.t_hit = "hit", int(dmg[0]["t_mono_ns"])
            elif hits:
                tr.outcome = "miss_only"
            elif f["request"] is not None:
                tr.outcome = "request_no_act"
            elif f["move"] is not None:
                tr.outcome = "walk_only"
            gc = mob_at(pos, g, c.t)
            if (f["request"] is not None and nearest is not None and nearest != g
                    and picked is not None
                    and (gc is None or cheb(picked, gc) > NEAR)):  # fmt: skip
                tr.outcome = "other_unit"
            if here is not None and gc is not None:
                tr.range_cells = cheb(here, gc)
                vis = sorted(cheb(here, mc) for gg in pos if present(life, gg, c.t)
                             and (mc := mob_at(pos, gg, c.t)) is not None
                             and cheb(here, mc) <= VIEW)  # fmt: skip
                tr.rank = 1 + sum(1 for d in vis if d < tr.range_cells)
            tr.t_seen = first_seen(frames, track, pos, g, c.t, pick)
        tr.info = {"request": f["request"] is not None, "box": box is not None,
                   "moving": is_moving(moving, c.t),
                   "picked": None if picked is None else list(picked)}  # fmt: skip
        recent = [p for p in trials if c.t - FOLLOW * NS <= p.t < c.t and p.gid not in (None, g)
                  and present(life, p.gid, c.t)]  # fmt: skip
        tr.switch = bool(recent)
        trials.append(tr)
    return summarise(trials, walks, counts, events, moving, ours, t0, w1)


def first_seen(frames: Sequence[tuple[int, list[list[Any]]]], track: Sequence[tuple[int, Cell]],
               pos: Mapping[int, Sequence[tuple[int, Cell, int]]], g: int, t_click: int,
               pick: Any) -> int | None:  # fmt: skip
    """Going back from the click (no gap over SEEN_GAP, at most SEEN_BACK): the earliest
    detector frame with a monster box whose picked cell is within SEEN_NEAR of G's cell then."""
    seen, last = None, t_click
    for tf, boxes in reversed([f for f in frames if t_click - SEEN_BACK * NS <= f[0] <= t_click]):
        if last - tf > SEEN_GAP * NS:
            break
        here, gc = at(track, tf), mob_at(pos, g, tf)
        if here is None or gc is None:
            continue
        for b in boxes:
            if b[5] != "monster":
                continue
            pc = pick(here, ((b[0] + b[2]) / 2, b[3]))
            if pc is not None and math.dist(pc, gc) <= SEEN_NEAR:
                seen, last = tf, tf
                break
    return seen


def damaging(ours: Sequence[Mapping[str, Any]], g: int, t0: int, t1: int) -> int | None:
    """The first act of ours on ``g`` with damage > 0 in (t0, t1], or None."""
    for a in ours:
        ta = int(a["t_mono_ns"])
        if (t0 < ta <= t1 and int(a["target_gid"]) == g
                and int(a.get("damage", 0)) + int(a.get("damage2", 0)) > 0):  # fmt: skip
            return ta
    return None


def bot_engagements(events: Sequence[Mapping[str, Any]], engs: Sequence[Mapping[str, Any]],
                    w_s: float = W_S) -> dict[str, Any]:  # fmt: skip
    """3.41's PRIMARY bar per engagement (the bot's first attack click on a track): G = the unit
    of the first attack request (<= T_REQ) when it stood within 3 cells of the predicted cell,
    else the mob nearest that cell within NEAR; SUCCESS = our damaging act on G within w_s;
    EXCLUDED: a species change, a death with no act of ours, a vanish (not 0/1) before our act."""
    import hunt_core as hc

    events = sorted(events, key=lambda e: int(e["t_mono_ns"]))
    pos = hc.walk_positions(events)
    life = alive(events)
    ours = [e for e in events if e.get("type") == "act" and gid_of(e, "src_gid") == GM
            and e.get("kind") != "pickup"]  # fmt: skip
    rows = []
    for e in engs:
        t1 = int(e["t_first_click"])
        pc = (int(round(e["pred_cell"][0])), int(round(e["pred_cell"][1])))
        req = next((x for x in events if x.get("type") == "attack_request"
                    and t1 <= int(x["t_mono_ns"]) <= t1 + int(T_REQ * NS)), None)  # fmt: skip
        g = None
        if req is not None:
            rc = mob_at(pos, int(req["target_gid"]), int(req["t_mono_ns"]))
            if rc is not None and cheb(rc, pc) <= 3:
                g = int(req["target_gid"])
        if g is None:
            cands = [(cheb(pc, mc), gg) for gg in pos if present(life, gg, t1)
                     and (mc := mob_at(pos, gg, t1)) is not None]  # fmt: skip
            cands = [x for x in cands if x[0] <= NEAR]
            g = min(cands)[1] if cands else None
        row: dict[str, Any] = {"k": e.get("k"), "gid": g, "bot": e.get("result"),
                               "clicks": e.get("clicks")}  # fmt: skip
        if g is None:
            row["why"] = "no_unit"
        else:
            th = damaging(ours, g, t1, t1 + int(w_s * NS))
            jobs = {int(x.get("job", -1)) for x in events if x.get("type") == "entity_appear"
                    and gid_of(x) == g and int(x["t_mono_ns"]) >= t1}  # fmt: skip
            first = {int(x.get("job", -1)) for x in events if x.get("type") == "entity_appear"
                     and gid_of(x) == g and int(x["t_mono_ns"]) < t1}  # fmt: skip
            van = next((x for x in events if x.get("type") == "entity_vanish" and gid_of(x) == g
                        and int(x["t_mono_ns"]) >= t1), None)  # fmt: skip
            acted = any(int(a["target_gid"]) == g and int(a["t_mono_ns"]) >= t1 for a in ours)
            if th is not None:
                row.update(why="hit", t_hit_s=round((th - t1) / NS, 2))
            elif first and jobs and not jobs <= first:
                row["why"] = "excluded:species_changed"
            elif van is not None and int(van.get("reason", -1)) == 1 and not acted:
                row["why"] = "excluded:killed_by_other"
            elif (van is not None and int(van.get("reason", -1)) not in (0, 1)
                  and not any(int(a["target_gid"]) == g and int(a["t_mono_ns"]) < int(
                      van["t_mono_ns"]) for a in ours)):  # fmt: skip
                row["why"] = "excluded:vanished"
            else:
                row["why"] = "hit_late" if acted else "never_hit"
        rows.append(row)
    return engagement_summary(rows)


def engagement_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counted = [x for x in rows if not str(x["why"]).startswith("excluded")]
    ok = sum(1 for x in counted if x["why"] == "hit")
    why: dict[str, int] = {}
    for x in rows:
        why[x["why"]] = why.get(x["why"], 0) + 1
    t_hit = [x["t_hit_s"] for x in rows if x.get("t_hit_s") is not None]
    return {"engagements": len(rows), "counted": len(counted), "hit_within_w": ok,
            "rate": round(ok / len(counted), 4) if counted else None,
            "wilson95": wilson(ok, len(counted)), "why": why,
            "first_click_to_hit_p50_p90": [pct(t_hit, 0.5), pct(t_hit, 0.9)],
            "rows": list(rows)}  # fmt: skip


def human_engagements(events: Sequence[Mapping[str, Any]], trials: Sequence[Mapping[str, Any]],
                      t0: int, w_s: float = W_S) -> dict[str, Any]:  # fmt: skip
    """3.41's reference for a HUMAN (no bar): every trial is an engagement. A hit is a success;
    a failed click's unit = the mob nearest its picked cell within REHIT_NEAR (or one that died
    <= 0.5 s before: EXCLUDED, the target was already dead); success if our damaging act on it
    lands within w_s of the click; none -> no_unit."""
    import hunt_core as hc

    events = sorted(events, key=lambda e: int(e["t_mono_ns"]))
    pos = hc.walk_positions(events)
    life = alive(events)
    ours = [e for e in events if e.get("type") == "act" and gid_of(e, "src_gid") == GM
            and e.get("kind") != "pickup"]  # fmt: skip
    rows = []
    for tr in trials:
        t = t0 + int(round(tr["t_s"] * NS))
        if tr["outcome"] == "hit":
            rows.append({"t_s": tr["t_s"], "why": "hit", "t_hit_s": tr["click_to_hit"]})
            continue
        pk = tr.get("picked")
        best = None
        for g in pos:
            dying = died_before(life, g, t, 0.5)
            if not present(life, g, t) and not dying:
                continue
            mc = mob_at(pos, g, t)
            if pk is None or mc is None:
                continue
            d = cheb(tuple(pk), mc)
            if d <= REHIT_NEAR and (best is None or d < best[0]):
                best = (d, g, dying)
        if best is None:
            rows.append({"t_s": tr["t_s"], "why": "no_unit"})
        elif best[2]:
            rows.append({"t_s": tr["t_s"], "why": "excluded:already_dead"})
        else:
            th = damaging(ours, best[1], t, t + int(w_s * NS))
            rows.append({"t_s": tr["t_s"], "why": "hit" if th is not None else "never_hit",
                         "t_hit_s": None if th is None else round((th - t) / NS, 2)})  # fmt: skip
    return engagement_summary(rows)


def idle_between_kills(events: Sequence[Mapping[str, Any]], clicks: Sequence[Click], t0: int,
                       w1: int) -> dict[str, Any]:  # fmt: skip
    """Batt 2026-10-16 ~11:30: the idle time between kills = a death (reason 1) of a unit we
    acted on -> our next click of any kind (human: any left click in the game region)."""
    acted = {gid_of(a, "target_gid") for a in events if a.get("type") == "act"
             and gid_of(a, "src_gid") == GM and a.get("kind") != "pickup"}  # fmt: skip
    deaths = sorted(int(e["t_mono_ns"]) for e in events if e.get("type") == "entity_vanish"
                    and int(e.get("reason", -1)) == 1 and gid_of(e) in acted
                    and t0 <= int(e["t_mono_ns"]) < w1)  # fmt: skip
    ts = sorted(c.t for c in clicks)
    gaps = []
    for td in deaths:
        nxt = next((t for t in ts if t > td), None)
        if nxt is not None and nxt < w1:
            gaps.append(round((nxt - td) / NS, 2))
    return {"n": len(gaps), "p50": pct(gaps, 0.5), "p90": pct(gaps, 0.9)}


def queue_hit_through(lines: Iterable[str]) -> dict[str, Any]:
    """v2: how often the planner's queue[0] was still valid at dispatch (events.jsonl)."""
    n = ok = 0
    for line in lines:
        x = json.loads(line)
        if x.get("kind") == "dispatch" and x.get("rank") == 0:
            n += 1
            ok += bool(x.get("valid"))
    return {"dispatches": n, "valid": ok, "rate": round(ok / n, 4) if n else None}


def unintended_attacks(events: Sequence[Mapping[str, Any]], engs: Sequence[Mapping[str, Any]],
                       t0: int, w1: int) -> int:  # fmt: skip
    """Our attack requests outside every engagement window (first click - 0.2 s .. end + 3 s): the
    client turned a walk click into an attack (no SWORD read). 3.39's count."""
    win = [(int(e["t_first_click"]) - int(0.2 * NS), int(e.get("t_end") or e["t_first_click"])
            + int(3 * NS)) for e in engs]  # fmt: skip
    return sum(1 for e in events if e.get("type") == "attack_request"
               and t0 <= int(e["t_mono_ns"]) < w1
               and not any(a <= int(e["t_mono_ns"]) <= b for a, b in win))  # fmt: skip


def search_moving_share(lines: Iterable[str], moving: Sequence[tuple[int, int]], t0: int,
                        w1: int) -> float | None:  # fmt: skip
    """v5: the share of SEARCH time (the runner's `mode` search windows) the GM moved (packets)."""
    marks = [(int(x["t_ns"]), x["mode"]) for x in map(json.loads, lines)
             if x.get("kind") == "mode"]  # fmt: skip
    wins = []
    for (ta, m), (tb, _m2) in zip(marks, [*marks[1:], (w1, "")], strict=True):
        if m == "search":
            a, b = max(ta, t0), min(tb, w1)
            if b > a:
                wins.append((a, b))
    tot = sum(b - a for a, b in wins)
    if not tot:
        return None
    mv = sum(max(0, min(b, y) - max(a, x)) for a, b in wins for x, y in moving)
    return round(mv / tot, 4)


def engagement_stops(lines: Iterable[str], moving: Sequence[tuple[int, int]], n_engagements: int,
                     t0: int, w1: int) -> dict[str, Any]:  # fmt: skip
    """Batt 15:00: STOPS DURING ENGAGEMENTS -- the GM came to a standstill (a packet moving
    interval ended) inside the runner's steer / engaged windows; per engagement. One stop per
    engagement is the strike itself (a standing GM at the last walk point)."""
    marks = [(int(x["t_ns"]), x["mode"]) for x in map(json.loads, lines)
             if x.get("kind") == "mode"]  # fmt: skip
    wins = []
    for (ta, m), (tb, _m2) in zip(marks, [*marks[1:], (w1, "")], strict=True):
        if m in ("steer", "engaged"):
            a, b = max(ta, t0), min(tb, w1)
            if b > a:
                wins.append((a, b))
    stops = sum(1 for _x, y in moving if any(a <= y < b for a, b in wins))
    return {
        "stops": stops,
        "engagements": n_engagements,
        "per_engagement": round(stops / n_engagements, 2) if n_engagements else None,
    }


def kills_by_origin(events: Sequence[Mapping[str, Any]], engs: Sequence[Mapping[str, Any]],
                    t0: int, w1: int) -> dict[str, int]:  # fmt: skip
    """v6's finding: a kill is ENGAGED when our last attack request on that mob fell inside an
    engagement window (a SWORD-read attack click), else UNINTENDED (a walk click the client turned
    into an attack). A kill = the mob vanished (reason 1) <= 1.5 s after our damaging act."""
    win = [(int(e["t_first_click"]) - int(0.2 * NS), int(e.get("t_end") or e["t_first_click"])
            + int(3 * NS)) for e in engs]  # fmt: skip
    last_req: dict[int, int] = {}
    hit: dict[int, int] = {}
    out = {"engaged": 0, "unintended": 0}
    for e in events:
        t = int(e["t_mono_ns"])
        typ = e.get("type")
        if typ == "attack_request":
            last_req[gid_of(e, "target_gid")] = t
        elif typ == "act" and gid_of(e, "src_gid") == GM and int(e.get("damage") or 0) > 0:
            hit[gid_of(e, "target_gid")] = t
        elif (typ == "entity_vanish" and int(e.get("reason", -1)) == 1 and t0 <= t < w1
              and t - hit.get(gid_of(e), -(10**18)) <= int(1.5 * NS)):  # fmt: skip
            rq = last_req.get(gid_of(e))
            ok = rq is not None and any(a <= rq <= b for a, b in win)
            out["engaged" if ok else "unintended"] += 1
    return out


def loot_metrics(events: Sequence[Mapping[str, Any]], t0: int, w1: int,
                 before_s: float = 0.6, after_s: float = 1.5) -> dict[str, Any]:  # fmt: skip
    """Batt 20:3x (LOOT EVERYTHING), from the packets: the items that FELL around one of our kills
    in [t0, w1) (a mob vanishing, reason 1, <= 1.5 s after our damaging act; the server sends the
    drop ~0.25 s BEFORE the vanish, so an item counts from ``before_s`` before to ``after_s``
    after), how many of them WE picked up (our pickup_request on its floor id, answered ok),
    pickup requests per item picked, and kill -> the LAST pickup of that kill's items (s)."""
    hit: dict[int, int] = {}
    kills: list[int] = []
    falls: list[tuple[int, int]] = []
    picked: dict[int, int] = {}
    pending: int | None = None
    n_req = 0
    for e in events:
        t = int(e["t_mono_ns"])
        typ = e.get("type")
        if typ == "act" and gid_of(e, "src_gid") == GM and int(e.get("damage") or 0) > 0:
            hit[gid_of(e, "target_gid")] = t
        elif (typ == "entity_vanish" and int(e.get("reason", -1)) == 1 and t0 <= t < w1
              and t - hit.get(gid_of(e), -(10**18)) <= int(1.5 * NS)):  # fmt: skip
            kills.append(t)
        elif typ == "floor_item_appear" and e.get("kind") == "fall":
            falls.append((t, int(e["floor_id"])))
        elif typ == "pickup_request" and t0 <= t:
            n_req += 1
            pending = int(e["floor_id"])
        elif typ == "pickup_result" and pending is not None:
            if e.get("ok"):
                picked.setdefault(pending, t)
            pending = None
    item_kill: dict[int, int] = {}
    for tf, fid in falls:
        near = [k for k in kills if -before_s * NS <= tf - k <= after_s * NS]
        if near:
            item_kill[fid] = min(near, key=lambda k: abs(tf - k))
    mine = [f for f in item_kill if f in picked]
    last: dict[int, int] = {}
    for f in mine:
        last[item_kill[f]] = max(last.get(item_kill[f], 0), picked[f] - item_kill[f])
    lag = sorted(v / NS for v in last.values())
    return {"items": len(item_kill), "picked": len(mine),
            "share": round(len(mine) / len(item_kill), 3) if item_kill else None,
            "requests_per_pickup": round(n_req / len(picked), 2) if picked else None,
            "kill_to_last_pickup_p50": round(lag[len(lag) // 2], 2) if lag else None}  # fmt: skip


def heading_metrics(events: Sequence[Mapping[str, Any]], t0: int, w1: int) -> dict[str, Any]:
    """Batt 18:2x (no back-and-forth): from the server's walk, each self_move is one leg (its start
    to where the GM got before the next leg). A REVERSAL is a heading change > 120 deg between
    consecutive legs of >= 2 cells. A straight run merges legs that turn <= 45 deg; its length is
    the cells walked. Batt's demo: 3.6 reversals / min, runs of 16.9 cells (mean). Batt 21:31
    adds the HEADING-CHANGE histogram (<= 45 / <= 90 / <= 135 / > 135 deg between consecutive
    legs of >= 2 cells) and reversals > 135 deg per minute."""
    track, _mv = gm_track(events)
    moves = [e for e in events if e.get("type") == "self_move" and t0 <= int(e["t_mono_ns"]) < w1]
    rev, runs, cur, prev_h, walked = 0, [], 0, None, 0
    hist = [0, 0, 0, 0]
    for a, b in zip(moves, [*moves[1:], None], strict=True):
        tb = int(b["t_mono_ns"]) if b is not None else w1
        p0 = (int(a["x0"]), int(a["y0"]))
        p1 = at(track, tb - 1) or (int(a["x1"]), int(a["y1"]))
        n = cheb(p0, p1)
        if n < 1:
            continue
        walked += n
        h = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
        if n >= 2 and prev_h is not None:
            d = abs((h - prev_h + math.pi) % (2 * math.pi) - math.pi)
            hist[min(3, max(0, math.ceil(round(math.degrees(d), 6) / 45) - 1))] += 1
            if d > math.radians(120):
                rev += 1
            if d > math.radians(45):
                runs.append(cur)
                cur = 0
        cur += n
        if n >= 2:
            prev_h = h
    runs.append(cur)
    mins = max(1e-9, (w1 - t0) / 60 / NS)
    return {"reversals_per_min": round(rev / mins, 2),
            "reversals135_per_min": round(hist[3] / mins, 2),
            "turn_hist_45": hist,
            "mean_straight_run": round(sum(runs) / len(runs), 1) if runs else None,
            "cells_walked_per_min": round(walked / mins, 1)}  # fmt: skip


def selection_metrics(events: Sequence[Mapping[str, Any]], lines: Iterable[str],
                      rows: Sequence[Mapping[str, Any]], engs: Sequence[Mapping[str, Any]],
                      view: tuple[int, int] = (12, 9)) -> dict[str, Any]:  # fmt: skip
    """Batt 19:0x: per engagement, at its SELECTION (the earliest dispatch / pre-emption of the
    engaged track's re-acquire chain), the distance GM -> the engaged mob (packets, cells) and
    whether it was the NEAREST live mob in view. ``rows`` = bot_engagements rows (k, gid)."""
    import hunt_core as hc

    recs = [json.loads(x) for x in lines]
    pred: dict[int, list[int]] = {}
    sel_t: dict[int, list[int]] = {}
    for x in recs:
        if x.get("kind") == "target_reacquired":
            pred.setdefault(int(x["as"]), []).append(int(x["track"]))
        elif (x.get("kind") == "dispatch" and x.get("valid")) or x.get("kind") == "preempt":
            tid = int(x["track"] if x.get("kind") == "dispatch" else x["to"])
            sel_t.setdefault(tid, []).append(int(x["t_ns"]))
    pos = hc.walk_positions(events)
    life = alive(events)
    track, _mv = gm_track(events)
    gid_by_k = {int(r_["k"]): r_.get("gid") for r_ in rows if r_.get("gid") is not None}
    dists, nearest = [], 0
    for e in engs:
        g = gid_by_k.get(int(e["k"]))
        if g is None:
            continue
        chain, todo = set(), [int(e["track"])]
        while todo:
            t_ = todo.pop()
            if t_ not in chain:
                chain.add(t_)
                todo += pred.get(t_, [])
        ts = [t for c in chain for t in sel_t.get(c, []) if t <= int(e["t_first_click"])]
        t_sel = min(ts) if ts else int(e["t_first_click"])
        gm, mc = at(track, t_sel), mob_at(pos, g, t_sel)
        if gm is None or mc is None:
            continue
        d = cheb(gm, mc)
        dists.append(d)
        others = [cheb(gm, c) for g2 in pos if g2 != g and present(life, g2, t_sel)
                  and (c := mob_at(pos, g2, t_sel)) is not None
                  and abs(c[0] - gm[0]) <= view[0] and abs(c[1] - gm[1]) <= view[1]]  # fmt: skip
        nearest += all(d <= o for o in others)
    n = len(dists)
    return {"n": n, "nearest_share": round(nearest / n, 3) if n else None,
            "dist_p50": pct([float(x) for x in dists], 0.5),
            "dist_p90": pct([float(x) for x in dists], 0.9)}  # fmt: skip


SPECIES = {1002: "Poring", 1063: "Lunatic", 1008: "Pupa", 1113: "Drops", 1018: "Creamy"}


def species_landing(events: Sequence[Mapping[str, Any]], rows: Sequence[Mapping[str, Any]],
                    engs: Sequence[Mapping[str, Any]], clicks: Sequence[Mapping[str, Any]]
                    ) -> dict[str, Any]:  # fmt: skip
    """Batt 20:0x, BY SPECIES (packets: the engaged gid's species): the landing rate per engagement
    (hit within W), the attack clicks per landed engagement (first + burst clicks from its first
    click to its end), and the aim error p50 of its first click (px)."""
    job: dict[int, int] = {}
    for e in events:
        if e.get("type") == "entity_appear":
            job.setdefault(gid_of(e), int(e.get("job", -1)))
    eng_by_k = {int(e["k"]): e for e in engs}
    att = [c for c in clicks if c.get("kind") in ("strike", "strike_burst")]
    out: dict[str, dict[str, Any]] = {}
    for r_ in rows:
        e = eng_by_k.get(int(r_["k"]))
        g = r_.get("gid")
        if e is None or g is None or str(r_.get("why", "")).startswith("excluded"):
            continue
        sp = SPECIES.get(job.get(int(g), -1), str(job.get(int(g), -1)))
        d = out.setdefault(sp, {"n": 0, "landed": 0, "clicks_landed": [], "aim_px": []})
        d["n"] += 1
        t0, t1 = int(e["t_first_click"]), int(e.get("t_end") or e["t_first_click"])
        if r_.get("why") == "hit":
            d["landed"] += 1
            d["clicks_landed"].append(sum(1 for c in att if t0 <= int(c["t"]) <= t1))
        h0 = next((h for h in e.get("hovers", []) if h.get("clicked")), {})
        if h0.get("aim_px") is not None:
            d["aim_px"].append(float(h0["aim_px"]))
    return {sp: {"n": d["n"], "landed": d["landed"],
                 "rate": round(d["landed"] / d["n"], 3) if d["n"] else None,
                 "clicks_per_landing": pct([float(x) for x in d["clicks_landed"]], 0.5),
                 "aim_px_p50": pct(d["aim_px"], 0.5)} for sp, d in out.items()}  # fmt: skip


def hard_bars(events: Sequence[Mapping[str, Any]], t0: int, w1: int,
              targets: Mapping[int, str]) -> dict[str, Any]:  # fmt: skip
    """v10's HARD BARS (Batt): NPC contacts, map changes after the start, and units of a non-target
    species our GM hit (its species when hit, farm0's rule), in [t0, w1)."""
    job: dict[int, int] = {}
    hit_job: dict[int, int] = {}
    npc = maps = 0
    for e in events:
        t = int(e["t_mono_ns"])
        typ = e.get("type")
        if typ == "entity_appear":
            job[gid_of(e)] = int(e.get("job", -1))
        if not t0 <= t < w1:
            continue
        if typ == "npc_contact":
            npc += 1
        elif typ == "map_change":
            maps += 1
        elif (typ == "act" and gid_of(e, "src_gid") == GM and e.get("target_gid")
              and e.get("kind") != "pickup" and int(e.get("damage") or 0) > 0):  # fmt: skip
            g = gid_of(e, "target_gid")
            hit_job.setdefault(g, job.get(g, -1))
    other = sorted({j for j in hit_job.values() if j not in targets})
    return {"npc_contacts": npc, "map_changes": maps, "non_target_jobs_hit": other,
            "pass": npc == 0 and maps == 0 and not other}  # fmt: skip


def walk_click_accuracy(events: Sequence[Mapping[str, Any]], walks: Sequence[Mapping[str, Any]],
                        moving: Sequence[tuple[int, int]]) -> dict[str, Any]:  # fmt: skip
    """v7: each walk click's intended cell (clicks.jsonl ``to``) vs the cell the client asked
    the server for (the next self_move_request <= 0.5 s later), split by whether the GM was
    moving at the click: the share within 1 cell, and the error ALONG the GM's motion (cells,
    + = the click landed ahead of the cell meant; v5: +3.0-3.5)."""
    req = [(int(e["t_mono_ns"]), (int(e["x"]), int(e["y"]))) for e in events
           if e.get("type") == "self_move_request"]  # fmt: skip
    rt = [t for t, _ in req]
    track, _mv = gm_track(events)
    out: dict[str, Any] = {}
    rows: dict[bool, list[tuple[int, float | None]]] = {False: [], True: []}
    for w in walks:
        t = int(w["t"])
        i = bisect.bisect_left(rt, t)
        if not (i < len(req) and req[i][0] - t < 0.5 * NS):
            continue
        got, to = req[i][1], (int(w["to"][0]), int(w["to"][1]))
        mv = is_moving(moving, t)
        along = None
        a, b = at(track, t - int(0.3 * NS)), at(track, t)
        if mv and a is not None and b is not None and a != b:
            dx, dy = b[0] - a[0], b[1] - a[1]
            along = ((got[0] - to[0]) * dx + (got[1] - to[1]) * dy) / math.hypot(dx, dy)
        rows[mv].append((cheb(got, to), along))
    for mv, rs in rows.items():
        al = [x for _d, x in rs if x is not None]
        out["moving" if mv else "standing"] = {
            "n": len(rs),
            "within_1": round(sum(d <= 1 for d, _x in rs) / len(rs), 3) if rs else None,
            "along_p50": None if not al else round(pct(al, 0.5) or 0.0, 2),
        }
    return out


def sight_per_10min(events: Sequence[Mapping[str, Any]], t0: int, w1: int) -> float:
    """Distinct mobs that entered sight in [t0, w1), per 10 minutes."""
    g = {gid_of(e) for e in events if e.get("type") == "entity_appear" and e.get("objtype") == 5
         and t0 <= int(e["t_mono_ns"]) < w1}  # fmt: skip
    return round(len(g) * 600 / max(1e-9, (w1 - t0) / NS), 1)


def pct(xs: Sequence[float], q: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return round(s[min(len(s) - 1, int(q * (len(s) - 1) + 0.5))], 2)


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [0.0, 1.0]
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((c - h) / d, 4), round((c + h) / d, 4)]


def summarise(trials: Sequence[Trial], walks: Sequence[Mapping[str, Any]],
              counts: Mapping[str, int], events: Sequence[Mapping[str, Any]],
              moving: Sequence[tuple[int, int]], ours: Sequence[Mapping[str, Any]],
              t0: int, w1: int) -> dict[str, Any]:  # fmt: skip
    hits = [t for t in trials if t.outcome == "hit"]
    why: dict[str, int] = {}
    for t in trials:
        why[t.outcome] = why.get(t.outcome, 0) + 1
    s2c = [(t.t - t.t_seen) / NS for t in hits if t.t_seen is not None]
    c2h = [(t.t_hit - t.t) / NS for t in hits if t.t_hit is not None]
    s2h = [(t.t_hit - t.t_seen) / NS for t in hits if t.t_seen is not None and t.t_hit]
    acted = {int(a["target_gid"]) for a in ours if t0 <= int(a["t_mono_ns"]) < w1}
    kills = sum(1 for e in events if e.get("type") == "entity_vanish"
                and int(e.get("reason", -1)) == 1 and gid_of(e) in acted
                and t0 <= int(e["t_mono_ns"]) < w1)  # fmt: skip
    mv = moving_share(moving, t0, w1)
    after_act = []
    for a in ours:
        ta = int(a["t_mono_ns"])
        if t0 <= ta < w1:
            after_act.append((ta, ta + int(1.5 * NS)))
    idle_att = sum(
        max(0, min(b, w1) - max(a, t0)) - sum(max(0, min(b, y) - max(a, x)) for x, y in moving)
        for a, b in merge(after_act)
    ) / max(1, w1 - t0)  # fmt: skip
    gaps = [(b["t"] - a["t"]) / NS for a, b in zip(walks, walks[1:], strict=False)]
    secs = (w1 - t0) / NS
    return {
        "window_s": round(secs, 1),
        "trials": len(trials), "hits": len(hits),
        "hit_rate": round(len(hits) / len(trials), 4) if trials else None,
        "wilson95": wilson(len(hits), len(trials)), "why": why,
        "reaction_s": {"seen_to_click": [pct(s2c, 0.5), pct(s2c, 0.9)],
                       "click_to_hit": [pct(c2h, 0.5), pct(c2h, 0.9)],
                       "seen_to_hit": [pct(s2h, 0.5), pct(s2h, 0.9)],
                       "n_seen": len(s2c)},
        "range_cells": {"p50": pct([t.range_cells for t in trials if t.range_cells is not None],
                                   0.5),
                        "p90": pct([t.range_cells for t in trials if t.range_cells is not None],
                                   0.9),
                        "hist": hist([t.range_cells for t in trials if t.range_cells is not None])},
        "rank": hist([t.rank for t in trials if t.rank is not None]),
        "switches": sum(t.switch for t in trials),
        "on_moving_gm": sum(1 for t in trials if t.info.get("moving")),
        "idle_pct": round(100 * (1 - mv), 1),
        "idle_attacking_pct": round(100 * idle_att, 1),
        "walk_clicks": {"n": len(walks), "per_min": round(len(walks) / (secs / 60), 1),
                        "spacing_p50_p90": [pct([w["spacing"] for w in walks], 0.5),
                                            pct([w["spacing"] for w in walks], 0.9)],
                        "interval_p50_p90_s": [pct(gaps, 0.5), pct(gaps, 0.9)],
                        "while_moving_pct": round(100 * sum(w["while_moving"] for w in walks)
                                                  / max(1, len(walks)), 1)},
        "clicks": dict(counts),
        "kills": kills, "kills_per_hour": round(kills * 3600 / secs, 1),
        "pickups": sum(1 for e in events if e.get("type") == "pickup_request"
                       and t0 <= int(e["t_mono_ns"]) < w1),
        "trial_rows": [{"t_s": round((t.t - t0) / NS, 2), "gid": t.gid, "outcome": t.outcome,
                        "range": t.range_cells, "rank": t.rank, "switch": t.switch,
                        "seen_to_click": (None if t.t_seen is None
                                          else round((t.t - t.t_seen) / NS, 2)),
                        "click_to_hit": None if t.t_hit is None else round((t.t_hit - t.t) / NS, 2),
                        **t.info} for t in trials],
    }  # fmt: skip


def merge(iv: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for a, b in sorted(iv):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def hist(xs: Iterable[int | None]) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in xs:
        if x is not None:
            out[str(x)] = out.get(str(x), 0) + 1
    return dict(sorted(out.items(), key=lambda kv: int(kv[0])))


# --- sessions -------------------------------------------------------------------------------------


def _session(sid: str) -> tuple[Path, dict[str, Any], list[dict[str, Any]], list[Any]]:
    from poring_env.demo import DEMO_ROOT

    d = DEMO_ROOT / sid
    man = json.loads((d / "manifest.json").read_text())
    with gzip.open(d / "packets.jsonl.gz", "rt") as fh:
        events = sorted((json.loads(x) for x in fh), key=lambda e: int(e["t_mono_ns"]))
    frames = []
    if (d / "boxes.jsonl").exists():
        for line in (d / "boxes.jsonl").open():
            x = json.loads(line)
            frames.append((int(x["t"]), x["boxes"]))
    frames.sort(key=lambda f: f[0])
    return d, man, events, frames


def picker(map_name: str) -> Any:
    import ro_agent as r

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod
    from poring_dataset import picking

    gat = gatmod.parse((cam.GAT_DIR / f"{map_name}.gat").read_bytes())
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    camera = cam.camera_from_json(cj["camera"])

    def pick(origin: Cell, px: tuple[float, float]) -> Cell | None:
        off = picking.pick_cells(camera, gat, origin, [px])[0]
        if off[0] < -1000 or off[1] < -1000:
            return None
        return (origin[0] + int(off[0]), origin[1] + int(off[1]))

    return pick


def human(sid: str) -> dict[str, Any]:
    import loot1
    import ro_agent as r

    d, man, events, frames = _session(sid)
    t0 = t0_of(events, int(man["t_armed_ns"]))
    if t0 is None:
        raise SystemExit("no movement after arming: nothing to judge")
    lines = (d / "input_human.jsonl").read_text().splitlines()
    clicks = human_clicks(lines, r.desktop(), r.game_region())
    out = judge(events, clicks, frames, t0, picker(man.get("map", "prt_fild08")), loot1.in_ui)
    out.update({"session": sid, "actor": "human", "t0_from_armed_s":
                round((t0 - int(man["t_armed_ns"])) / NS, 1)})  # fmt: skip
    out["engagements_w"] = human_engagements(events, out["trial_rows"], t0)
    out["sight_per_10min"] = sight_per_10min(events, t0, t0 + int(WINDOW_S * NS))
    out["idle_between_kills"] = idle_between_kills(events, clicks, t0, t0 + int(WINDOW_S * NS))
    out["heading"] = heading_metrics(events, t0, t0 + int(WINDOW_S * NS))
    out["loot"] = loot_metrics(events, t0, t0 + int(WINDOW_S * NS))
    (d / "flow_judge.json").write_text(json.dumps(out, indent=1))
    return out


def bot(
    sid: str, from_s: float | None = None, length_s: float | None = None, write: bool = True
) -> dict[str, Any]:
    """A hunt-flow run: clicks from the runner's clicks.jsonl, the engagements it logged, the
    sampler's boxes; the window from our first move after the loop start to the run's end. Batt
    2026-10-17 (the competition): ``from_s`` / ``length_s`` judge one window of the run (from that
    offset after the first move, that long) on the same terms as a 10-min human demo."""
    import loot1

    d, man, events, frames = _session(sid)
    clicks = [Click(int(x["t"]), float(x["u"]), float(x["v"]), str(x.get("kind", "")))
              for x in map(json.loads, (d / "clicks.jsonl").read_text().splitlines())]  # fmt: skip
    loop0 = next((int(x["t_ns"]) for x in map(json.loads, (d / "events.jsonl").read_text()
                                              .splitlines()) if x.get("kind") == "loop_start"),
                 int(man["t0_mono_ns"]))  # fmt: skip
    t0 = t0_of(events, loop0)
    if t0 is None:
        raise SystemExit("no movement after the loop start: nothing to judge")
    window = (min(int(man.get("t1_mono_ns", t0)), max(c.t for c in clicks) + 5 * NS) - t0) / NS
    engs = json.loads((d / "engagements.json").read_text())
    if from_s is not None:
        t0 += int(from_s * NS)
        window = max(0.0, min(length_s or window, window - from_s))
        engs = [e for e in engs if t0 <= int(e["t_first_click"]) < t0 + int(window * NS)]
        clicks = [c for c in clicks if t0 <= c.t < t0 + int(window * NS)] or clicks[:0]
    out = judge(events, clicks, frames, t0, picker(man.get("map", "prt_fild08")), loot1.in_ui,
                window_s=window)  # fmt: skip
    out["engagements_w"] = bot_engagements(events, engs)
    out["sight_per_10min"] = sight_per_10min(events, t0, t0 + int(window * NS))
    out["idle_between_kills"] = idle_between_kills(events, clicks, t0, t0 + int(window * NS))
    out["queue_hit_through"] = queue_hit_through((d / "events.jsonl").read_text().splitlines())
    w1 = t0 + int(window * NS)
    out["unintended_attacks"] = unintended_attacks(events, engs, t0, w1)
    # v6: per attack attempt -- the aim error (px), the time from "in range" to the click, the read
    strikes = [x for x in map(json.loads, (d / "clicks.jsonl").read_text().splitlines())
               if x.get("kind") == "strike"]  # fmt: skip
    for key in ("aim_px", "in_range_to_click_s", "read_ms"):
        xs = [float(x[key]) for x in strikes if x.get(key) is not None]
        out[key] = {"n": len(xs), "p50": pct(xs, 0.5), "p90": pct(xs, 0.9)}
    picks = sum(1 for e in events if e.get("type") == "pickup_result" and e.get("ok")
                and t0 <= int(e["t_mono_ns"]) < w1)  # fmt: skip
    out["pickups_ok"] = picks
    out["pickups_per_kill"] = round(picks / out["kills"], 2) if out["kills"] else None
    _track, mv_ = gm_track(events)
    out["search_moving_share"] = search_moving_share(
        (d / "events.jsonl").read_text().splitlines(), mv_, t0, w1)  # fmt: skip
    out["engagement_stops"] = engagement_stops(
        (d / "events.jsonl").read_text().splitlines(), mv_, len(engs), t0, w1)  # fmt: skip
    walks = [x for x in map(json.loads, (d / "clicks.jsonl").read_text().splitlines())
             if x.get("kind") == "walk" and t0 <= int(x["t"]) < w1]  # fmt: skip
    out["walk_click_accuracy"] = walk_click_accuracy(events, walks, mv_)
    out["kills_by_origin"] = kills_by_origin(events, engs, t0, w1)
    import farm0

    out["hard_bars"] = hard_bars(events, t0, w1, farm0.TARGETS)
    out["heading"] = heading_metrics(events, t0, w1)
    out["loot"] = loot_metrics(events, t0, w1)
    all_clicks = [x for x in map(json.loads, (d / "clicks.jsonl").read_text().splitlines())]
    out["species"] = species_landing(events, out["engagements_w"]["rows"], engs, all_clicks)
    evl = [x for x in map(json.loads, (d / "events.jsonl").read_text().splitlines())]
    out["preempts_per_min"] = round(sum(1 for x in evl if x.get("kind") == "preempt")
                                    / max(1e-9, window / 60), 2)  # fmt: skip
    ages = [float(x["age_ms"]) for x in evl if x.get("kind") == "strike_call"
            and x.get("read") in ("sword", "direct") and x.get("age_ms") is not None]  # fmt: skip
    out["box_age_ms"] = {"n": len(ages), "p50": pct(ages, 0.5), "p90": pct(ages, 0.9)}
    bursts = [x for x in evl if x.get("kind") == "burst"]
    if bursts:
        out["bursts"] = {"n": len(bursts),
                         "clicks_p50": pct([float(b["clicks"]) for b in bursts], 0.5),
                         "ends": dict(Counter(b.get("end") for b in bursts)),
                         "arrow_s_p50": pct([float(b["arrow_s"]) for b in bursts
                                             if b.get("arrow_s") is not None], 0.5)}  # fmt: skip
    out["selection"] = selection_metrics(events, (d / "events.jsonl").read_text().splitlines(),
                                         out["engagements_w"]["rows"], engs)  # fmt: skip
    strikes_ = [x for x in map(json.loads, (d / "clicks.jsonl").read_text().splitlines())
                if x.get("kind") == "strike" and t0 <= int(x["t"]) < w1]  # fmt: skip
    out["gate"] = {
        "direct": sum(x.get("branch") == "direct" for x in strikes_),
        "read": sum(x.get("branch") == "read" for x in strikes_),
        "reasons": dict(Counter(r_ for x in strikes_ for r_ in x.get("risk") or [])),
    }
    out.update({"session": sid, "actor": man.get("actor", "bot"), "rule": man.get("rule"),
                "packet_assisted": bool(man.get("packet_assisted"))})  # fmt: skip
    if from_s is not None:
        out["window"] = {"from_s": from_s, "length_s": round(window, 1)}
    if write:
        (d / "flow_judge.json").write_text(json.dumps(out, indent=1))
    return out


def bot_windows(sid: str, length_s: float = 600.0) -> dict[str, Any]:
    """Batt 2026-10-17: a bot run cut into back-to-back ``length_s`` windows from its first move,
    each judged like a 10-min human demo; the MEDIAN window and the BEST by kills / h."""
    full = bot(sid, write=False)
    n = int(full["window_s"] // length_s)
    wins = [bot(sid, k * length_s, length_s, write=False) for k in range(n)]
    order = sorted(range(n), key=lambda k: wins[k]["kills_per_hour"])
    return {"n": n, "median": wins[order[(n - 1) // 2]] if n else None,
            "best": wins[order[-1]] if n else None,
            "kills_per_hour": [w["kills_per_hour"] for w in wins]}  # fmt: skip


def row(o: Mapping[str, Any]) -> dict[str, str]:
    e = o["engagements_w"]
    rx = o["reaction_s"]
    return {
        "hit within 5 s of 1st click": f"{e['hit_within_w']}/{e['counted']} = "
        f"{100 * (e['rate'] or 0):.1f} %",
        "Wilson 95": f"{100 * e['wilson95'][0]:.1f}-{100 * e['wilson95'][1]:.1f} %",
        "1st click lands (not the bar)": f"{o['hits']}/{o['trials']} = "
        f"{100 * (o['hit_rate'] or 0):.1f} %",
        "kills / h": f"{o['kills_per_hour']}",
        "kills / h by engagements (SWORD read)": "-" if not o.get("kills_by_origin")
        else f"{round(o['kills_by_origin']['engaged'] * 3600 / o['window_s'], 1)}"
        f" ({o['kills_by_origin']['unintended']} other kills)",
        "seen -> click p50/p90 s": f"{rx['seen_to_click'][0]} / {rx['seen_to_click'][1]}",
        "click -> hit p50/p90 s": f"{rx['click_to_hit'][0]} / {rx['click_to_hit'][1]}",
        "monsters in sight / 10 min": f"{o['sight_per_10min']}",
        "idle %": f"{o['idle_pct']}",
        "walk clicks / min": f"{o['walk_clicks']['per_min']}",
        "range at click p50/p90": f"{o['range_cells']['p50']} / {o['range_cells']['p90']}",
        "death -> next click p50/p90 s": "{} / {}".format(
            *(o.get("idle_between_kills") or {}).get("p50_p90", [
                (o.get("idle_between_kills") or {}).get("p50"),
                (o.get("idle_between_kills") or {}).get("p90")])),
        "queue[0] valid at dispatch": "-" if not (o.get("queue_hit_through") or {}).get(
            "dispatches") else "{valid}/{dispatches}".format(**o["queue_hit_through"]),
        "engagements (1st clicks)": f"{o['engagements_w']['engagements']}",
        "walk clicks sent while moving": f"{o['walk_clicks']['while_moving_pct']} %",
        "walk click interval p50/p90 s": "{} / {}".format(*o["walk_clicks"]["interval_p50_p90_s"]),
        "moving share of SEARCH time": "-" if o.get("search_moving_share") is None
        else f"{100 * o['search_moving_share']:.0f} %",
        "unintended attack requests": f"{o.get('unintended_attacks', '-')}",
        "aim error px p50/p90": "-" if not (o.get("aim_px") or {}).get("n")
        else "{p50} / {p90}".format(**o["aim_px"]),
        "in range -> click s p50/p90": "-" if not (o.get("in_range_to_click_s") or {}).get("n")
        else "{p50} / {p90}".format(**o["in_range_to_click_s"]),
        "stops / engagement": "-" if not (o.get("engagement_stops") or {}).get("engagements")
        else f"{o['engagement_stops']['per_engagement']}",
        "moving walk clicks within 1 cell": "-" if not ((o.get("walk_click_accuracy") or {})
                                                        .get("moving") or {}).get("n")
        else "{}/{n} = {p:.0f} % (along {a:+})".format(
            round(o["walk_click_accuracy"]["moving"]["within_1"]
                  * o["walk_click_accuracy"]["moving"]["n"]),
            n=o["walk_click_accuracy"]["moving"]["n"],
            p=100 * o["walk_click_accuracy"]["moving"]["within_1"],
            a=o["walk_click_accuracy"]["moving"]["along_p50"] or 0.0),
        "pickups per kill": f"{o.get('pickups_per_kill', '-')}",
        "engaged the nearest (at selection)": "-" if not (o.get("selection") or {}).get("n")
        else f"{100 * o['selection']['nearest_share']:.0f} %",
        "distance at selection p50/p90": "-" if not (o.get("selection") or {}).get("n")
        else f"{o['selection']['dist_p50']} / {o['selection']['dist_p90']}",
        "landing / engagement by species": "-" if not o.get("species")
        else ", ".join(f"{sp} {v['landed']}/{v['n']}" for sp, v in sorted(
            o["species"].items(), key=lambda kv: -kv[1]["n"]) if v["n"]),
        "bursts: clicks p50, ends": "-" if not o.get("bursts")
        else f"{o['bursts']['clicks_p50']} | {o['bursts']['ends']}",
        "pre-emptions / min": "-" if o.get("preempts_per_min") is None
        else f"{o['preempts_per_min']}",
        "box age at click ms p50/p90": "-" if not (o.get("box_age_ms") or {}).get("n")
        else "{p50} / {p90}".format(**o["box_age_ms"]),
        "reversals / min": "-" if not o.get("heading") else f"{o['heading']['reversals_per_min']}",
        "mean straight run (cells)": "-" if not o.get("heading")
        else f"{o['heading']['mean_straight_run']}",
        "reversals > 135 deg / min": "-" if not (o.get("heading") or {}).get("turn_hist_45")
        else f"{o['heading']['reversals135_per_min']}",
        "turns <=45/<=90/<=135/>135": "-" if not (o.get("heading") or {}).get("turn_hist_45")
        else "/".join(str(x) for x in o["heading"]["turn_hist_45"]),
        "loot picked / items": "-" if not (o.get("loot") or {}).get("items")
        else "{picked} / {items}".format(**o["loot"]),
        "loot requests / pickup": "-" if not (o.get("loot") or {}).get("requests_per_pickup")
        else f"{o['loot']['requests_per_pickup']}",
        "kill -> last pickup s p50": "-" if not (o.get("loot") or {}).get("kill_to_last_pickup_p50")
        else f"{o['loot']['kill_to_last_pickup_p50']}",
        "attack clicks direct / read": "-" if not (o.get("gate") or {}).get("direct")
        and not (o.get("gate") or {}).get("read")
        else "{direct} / {read}".format(**o["gate"]),
        "hard bars (NPC / map / non-target)": "-" if not o.get("hard_bars")
        else "{} / {} / {}".format(o["hard_bars"]["npc_contacts"], o["hard_bars"]["map_changes"],
                                   len(o["hard_bars"]["non_target_jobs_hit"])),
        "window min": f"{round(o['window_s'] / 60, 1)}",
    }  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("human")
    h.add_argument("session")
    b = sub.add_parser("bot")
    b.add_argument("session")
    a = ap.parse_args()
    out = human(a.session) if a.cmd == "human" else bot(a.session)
    brief = {k: v for k, v in out.items() if k != "trial_rows"}
    brief["engagements_w"] = {k: v for k, v in out["engagements_w"].items() if k != "rows"}
    print(json.dumps(brief, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
