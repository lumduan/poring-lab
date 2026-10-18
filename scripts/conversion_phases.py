#!/usr/bin/env python3
"""The CONVERSION study's PHASE TIMELINE (Batt 2026-10-18): for every target that comes into view,
where the time goes between its entry and its death -- Batt's 10-min human demo and the bot's
full-hour hunt-flow runs, OFFLINE, on ONE ruler. Packets are ground truth here (ADR-0007) and never
a decision input (rule 1): nothing in this module runs during play, and the bot never imports it.

    conversion_phases.py compare BATT_SID BOT_SID [BOT_SID ...]   every table below (JSON)

THE COHORT is search_study.turn_toward's: every target VIEW ENTRY (a new life of a Poring, Lunatic,
Pupa or Drops: the server sent it into our view) in [t0, w1 - 10 s), FREE when no other target was
within 14 cells of our GM and we sent no attack request in the 3 s before; else BUSY. ``entries``
reproduces turn_toward's rows exactly (its free_any n and attacked_10s; tested).

THE MILESTONES of an entry (``milestones``; None = not reached before its PRESENCE ends, the
window ends, or HORIZON_S after the entry -- beyond 10 s too, so a target taken late still counts,
with its real wait). A presence (``chain_end``) follows the gid across view-edge flicker: a life
that leaves the view (vanish reason 0) and whose gid is back within FLICKER_S is the same presence,
as turn_toward (which follows the gid, not the life) counts it; with that, the cohort's
attacked-within-10-s share equals turn_toward's exactly:
- t_enter      the entry itself (server time);
- t_onscreen   the first 0.1-s sample whose cell offset mob - GM (packet cells) is inside the
               camera FOOTPRINT, built as hunt_flow builds it: hunt_core.footprint over
               camera_rdp.json's camera (flat ground) inside the 1280 x 720 game region, minus
               loot1.in_ui. What the screen can show (server time; the screen shows it LAG_S later);
- t_detect     the first detector frame (boxes.jsonl, the same detector for both subjects) with a
               monster box whose bottom-centre lies within DETECT_PX of the mob's projected cell.
               Frames show the server's state LAG_S old: the projection uses the GM and the mob
               at t_frame - LAG_S, positions interpolated along their steps. LAG_S = 0.6 s and
               DETECT_PX = 45 px were measured: the box-to-nearest-projected-mob residual is
               smallest at 0.6 s for both subjects (p50 21 px Batt, 19 px bot; 81 / 86 % within
               45 px), with no bias across (du ~0) and the box bottom ~6 px below the foot.
               t_detect is a FRAME time: the earliest a pixel agent could know;
- t_notice     the BOT: its first SELECTION of a track that is this mob (``bot_selections``): a
               valid ``dispatch`` whose cell lies within max(NOTICE_CELLS, NOTICE_PER_CELL x its
               distance from our GM) of the mob's packet cell at t - lag for some lag in
               NOTICE_LAGS_S (the track is predicted from frames ~0.6 s old, and its cell error
               grows with the distance), or any dispatch / preempt / retarget / reacquire of a
               track whose engagement attacked this mob (flow_judge.bot_engagements' join: the
               first attack request within T_REQ of the first click on a unit within 3 cells of
               pred_cell, else the mob nearest pred_cell within 2), or that it re-acquired as /
               from such a track. ``selection_agreement`` checks the cell match against that join
               (the share of dispatches resolved both ways that name the same mob). A retarget
               to a NEW track id of the same monster is not followed back (track churn): the
               notice can then be late (seen on v37: tracks 25 -> 26 -> 27, one Poring).
               BATT: a POINTER proxy (``pointer_times``): his pointer (the
               desktop's 1440 x 900, normalised, minus the game region's origin) first within
               PTR_PX of the mob's projected BODY point (the cell at t - LAG_S, PTR_DV px up).
               Measured on his 59 attack clicks: they land p50 29 px / p90 60 px from that point
               (du +0.3, dv -8.5), so PTR_PX = 60 covers 90 % of his real aims. The proxy's
               quality is reported by ``pointer_quality`` (its lead on his attack clicks and its
               false-positive rate on targets he never attacked);
- t_turn       turn_toward's: the first walk command (self_move_request) within 45 deg of the
               target's bearing (to a cell other than ours), or an attack request on it;
- t_click      the subject's INPUT click that the first attack request answered: the last click
               (bot: clicks.jsonl, any kind; Batt: a left button down) <= T_REQ before it;
- t_attack_req the first attack_request on its gid. NOTE: the client sends it only when the GM is
               (nearly) within reach -- clicked from afar, the client first walks up by itself
               (attack_req -> melee p50 0.08 s, both subjects). So click -> attack_req is the
               client's walk-up plus the input path, and the CLICK is the subject's decision;
- t_inrange3   the first 0.05-s sample with our GM within 3 cells (Chebyshev, packet cells) of it:
               the bot's strike distance (hunt_flow strike_cells; 7 for a standing target since v4);
- t_inrange1   the same within 1 cell (melee reach);
- t_hit        our GM's first act on it with damage > 0;
- t_kill       its vanish with reason 1 (died) after an act of ours (search_study.kill_times).

Batt clicks a target from afar and lets the client walk up; the bot walks to <= 3 cells and THEN
clicks. So the phases are reported both ways: between consecutive milestones of the common chain
enter -> attack_req -> hit -> kill, and between the approach milestones (turn -> in range ->
click -> attack_req -> melee -> hit), each with the share of entries where the order is REVERSED
(e.g. Batt's attack request before he is within 3 cells). ``orders`` counts each subject's actual
milestone orders.

THE DECOMPOSITION (``decompose``): search_study.presence_summary's "target-in-view s per kill"
(every 0.25-s scan sample with an alive target within 14 cells, per kill: Batt 6.8 s, the bot
~12-14 s) split so that it SUMS: each such sample gets ONE label, from the most advanced target in
view (priority FIGHT > CLICKED > LOOT > IN_RANGE > TURNED > NOTICED > UNNOTICED):
- FIGHT       from our first damaging act on it to its death (or our last act + 1 s);
- CLICKED     from the subject's click (t_click; t_attack_req when no click is found) until the
              hit (no hit: until the last attack request on it + CLICK_TAIL_S): split WALK_UP (it
              is > 1 cell away: the client walks up) and REACH;
- LOOT        a kill's pickup chain (pickup requests, the first <= 6 s after the kill, then
              <= 3 s apart): from the kill to the chain's last request;
- IN_RANGE    within 3 cells, not yet clicked;
- TURNED      turned toward (t_turn), not yet in range;
- NOTICED     noticed (t_notice), not yet turned;
- UNNOTICED   in view, not noticed (split: off screen / on screen, not detected / detected).
Each label also carries the target's OUTCOME (killed by us / attacked, not killed / never
attacked), so the time on targets that are never attacked or killed is reported apart and the
whole adds up to the in-view time (``sum_check_s``). Per label, ``label_diagnostics`` gives the
share of samples with our GM moving, the deciding target's mean distance and -- for the bot -- its
own activity then (``bot_activity``: its search / steer / engaged mode and its loot steps), to say
WHY a phase is long; the activity explains a label, it never defines one.

``approach``: per entry the distance (cells) at the turn, the cells closed per second from the turn
to 3 cells, and the GM's moving share over that stretch.

``hit_kill`` gives hits per kill, misses, the interval between our damaging acts, re-requests and
the GM-mob distance between the hit and the kill. ``bot_strikes`` gives the bot's own in range ->
click view (engagements' hovers: in_range_to_click_s, arm_eff, fallback).
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import flow_judge as fj  # noqa: E402
import search_study as ss  # noqa: E402

NS = 10**9
GM = fj.GM
VIEW = ss.VIEW
LAG_S = 0.6  # frames show the server's state this old (measured, both subjects)
DETECT_PX = 45.0  # a box bottom-centre within this of the projected cell = detected
PTR_PX = 60.0  # Batt's pointer within this of the projected body = noticed (p90 of his aims)
PTR_DV = -9.0  # the body point: px above the projected foot (his attack clicks: dv -8.5 .. -12)
PTR_FAR_PX = 120.0  # the final approach starts where the pointer was last this far from it
NOTICE_CELLS = 2.5  # a dispatch's cell within this of the mob (Chebyshev, interpolated cells) ...
NOTICE_PER_CELL = 0.25  # ... or within this x its distance from our GM, when larger
NOTICE_LAGS_S = (0.0, 0.3, 0.6, 0.9, 1.2)
HORIZON_S = 60.0
SAMPLE_S = 0.05  # the in-range sampling step
SCREEN_S = 0.1  # the on-screen sampling step
STRIKE = 3
MELEE = 1
T_REQ = fj.T_REQ  # a click answered by an attack request within this
LOOT_FIRST_S, LOOT_GAP_S = 6.0, 3.0
FIGHT_TAIL_S = 1.0
CLICK_TAIL_S = 2.0  # a click never answered by a hit stays CLICKED until the last request + this
FLICKER_S = 10.0  # a gid back in view within this after leaving it: the same presence
GAME_REGION = (80, 77, 1280, 720)  # camera_rdp.json's game_region (x, y, w, h on the desktop)
DESKTOP = (1440, 900)  # the RDP session Batt played in (human input is normalised by it)
Cell = tuple[int, int]
Pt = tuple[float, float]
MILESTONES = ("t_enter", "t_onscreen", "t_detect", "t_notice", "t_turn", "t_click",
              "t_attack_req", "t_inrange3", "t_inrange1", "t_hit", "t_kill")  # fmt: skip
PHASES = (
    ("enter->attack_req", "t_enter", "t_attack_req"),
    ("attack_req->hit", "t_attack_req", "t_hit"),
    ("hit->kill", "t_hit", "t_kill"),
    ("enter->onscreen", "t_enter", "t_onscreen"),
    ("onscreen->detect", "t_onscreen", "t_detect"),
    ("detect->notice", "t_detect", "t_notice"),
    ("enter->notice", "t_enter", "t_notice"),
    ("notice->turn", "t_notice", "t_turn"),
    ("enter->turn", "t_enter", "t_turn"),
    ("turn->inrange3", "t_turn", "t_inrange3"),
    ("inrange3->click", "t_inrange3", "t_click"),
    ("turn->click", "t_turn", "t_click"),
    ("click->attack_req", "t_click", "t_attack_req"),
    ("attack_req->inrange1", "t_attack_req", "t_inrange1"),
    ("inrange1->hit", "t_inrange1", "t_hit"),
    ("click->hit", "t_click", "t_hit"),
    ("enter->kill", "t_enter", "t_kill"),
)
STATUSES = ("FIGHT", "CLICKED_WALK_UP", "CLICKED_REACH", "LOOT", "IN_RANGE", "TURNED", "NOTICED",
            "UNNOTICED_DETECTED", "UNNOTICED_ONSCREEN", "UNNOTICED_OFFSCREEN")  # fmt: skip
OUTCOMES = ("killed", "attacked_not_killed", "never_attacked")


# --- positions ------------------------------------------------------------------------------------


def interp(ts: Sequence[int], cs: Sequence[Cell], t: int) -> Pt | None:
    """A unit's position at ``t`` from its step points: between two points one cell apart and
    <= 0.6 s apart (a step in progress) linearly, else the last point's cell."""
    i = bisect.bisect_right(ts, t) - 1
    if i < 0:
        return None
    a = cs[i]
    if i + 1 < len(ts):
        b, dt = cs[i + 1], ts[i + 1] - ts[i]
        if fj.cheb(a, b) <= 1 and 0 < dt <= int(0.6 * NS):
            f = (t - ts[i]) / dt
            return (a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1]))
    return (float(a[0]), float(a[1]))


class Paths:
    """Interpolated GM and mob positions over a search_study.Field."""

    def __init__(self, fld: ss.Field) -> None:
        self.fld = fld
        self.gt = [p[0] for p in fld.track]
        self.gc = [p[1] for p in fld.track]
        self.mt = {g: [q[0] for q in v] for g, v in fld.pos.items()}
        self.mc = {g: [q[1] for q in v] for g, v in fld.pos.items()}

    def gm(self, t: int) -> Pt | None:
        return interp(self.gt, self.gc, t)

    def mob(self, g: int, t: int) -> Pt | None:
        if g not in self.mt:
            return None
        return interp(self.mt[g], self.mc[g], t)

    def offset(self, g: int, t: int) -> Pt | None:
        a, b = self.gm(t), self.mob(g, t)
        if a is None or b is None:
            return None
        return (b[0] - a[0], b[1] - a[1])


def camera_projector() -> Callable[[Any], Any]:
    """camera_rdp.json's camera, flat ground: cell offsets (N, 2) -> game-region px (N, 2)."""
    from poring_dataset import camera as cam

    p = Path(__file__).resolve().parents[1] / "packages/poring_dataset/src/poring_dataset"
    cj = json.loads((p / "camera_rdp.json").read_text())
    camera = cam.camera_from_json(cj["camera"])
    return lambda offs: camera.project(np.asarray(offs, dtype=float).reshape(-1, 2),
                                       np.zeros(len(offs)))  # fmt: skip


def footprint_set(
    project: Callable[[Any], Any],
    in_ui: Callable[[float, float], bool] | None = None,
    region: tuple[int, int, int, int] = GAME_REGION,
) -> set[Cell]:
    """hunt_flow's footprint: the cell offsets drawn inside the game region, outside the UI."""
    import hunt_core as hc

    if in_ui is None:
        import loot1

        in_ui = loot1.in_ui
    gw, gh = region[2], region[3]
    ui = in_ui

    def in_view(u: float, v: float) -> bool:
        return 0 <= u < gw and 0 <= v < gh and not ui(u, v)

    return set(hc.footprint(project, in_view))


# --- the cohort -----------------------------------------------------------------------------------


def commands(events: Sequence[Mapping[str, Any]]) -> list[tuple[int, str, Cell | None, int]]:
    """turn_toward's command list: (t, "move", dst, -1) and (t, "atk", None, target gid)."""
    return sorted([(int(e["t_mono_ns"]), "move", (int(e["x"]), int(e["y"])), -1)
                   for e in events if e.get("type") == "self_move_request"]
                  + [(int(e["t_mono_ns"]), "atk", None, fj.gid_of(e, "target_gid"))
                     for e in events if e.get("type") == "attack_request"],
                  key=lambda c: c[0])  # fmt: skip


def entries(fld: ss.Field, t0: int, w1: int, r: int = VIEW, within_s: float = 10.0,
            busy_s: float = 3.0) -> list[dict[str, Any]]:  # fmt: skip
    """turn_toward's rows, one per target view entry in [t0, w1 - within_s) with the GM's and the
    mob's cell known: t, gid, busy, off (deg off our travel, None standing) and the life's end."""
    atk_t = [int(e["t_mono_ns"]) for e in fld.events if e.get("type") == "attack_request"]
    ends = {(g, a): (b, rr) for a, b, g, rr in fld.tlives}
    rows = []
    for a, g in fld.entries(t0, int(w1 - within_s * NS)):
        here, m = fld.gm(a), fld.mob(g, a)
        if here is None or m is None:
            continue
        others = [x for x in fld.targets_at(a) if x[0] != g and fj.cheb(x[1], here) <= r]
        i = bisect.bisect_right(atk_t, a) - 1
        busy = bool(others) or (i >= 0 and a - atk_t[i] <= busy_s * NS)
        h = ss.motion_heading(fld, a)
        off = None if h is None else math.degrees(ss._adiff(h, ss._ang(here, m)))
        b, rr = ends.get((g, a), (None, None))
        rows.append({"t": a, "gid": g, "busy": busy, "off": off, "life_end": b, "reason": rr})
    return rows


def turn_time(
    fld: ss.Field,
    cmds: Sequence[tuple[int, str, Cell | None, int]],
    ct: Sequence[int],
    a: int,
    g: int,
    end: int,
) -> tuple[int | None, int | None]:
    """(t_turn, t_attack_req) by turn_toward's rule, searched in (a, end]."""
    lat = atk = None
    j = bisect.bisect_right(ct, a)
    while j < len(cmds) and cmds[j][0] <= end:
        tc, kind, dst, tg = cmds[j]
        if kind == "atk" and tg == g:
            atk = tc
            lat = tc if lat is None else lat
            break
        if kind == "move" and lat is None and dst is not None:
            h2, m2 = fld.gm(tc), fld.mob(g, tc)
            off_ = None if not (h2 and m2) else ss._adiff(ss._ang(h2, dst), ss._ang(h2, m2))
            if h2 and m2 and dst != h2 and off_ is not None and off_ <= math.radians(45):
                lat = tc
        j += 1
    return lat, atk


# --- milestones -----------------------------------------------------------------------------------


def first_within(fld: ss.Field, g: int, a: int, end: int, cells: int,
                 dt_s: float = SAMPLE_S) -> int | None:  # fmt: skip
    """The first sample in [a, end] with the GM within ``cells`` (Chebyshev, packet cells)."""
    dt = int(dt_s * NS)
    for t in range(a, end + 1, dt):
        h, m = fld.gm(t), fld.mob(g, t)
        if h is not None and m is not None and fj.cheb(h, m) <= cells:
            return t
    return None


def onscreen_time(fld: ss.Field, g: int, a: int, end: int, fp: set[Cell],
                  dt_s: float = SCREEN_S) -> int | None:  # fmt: skip
    """The first sample in [a, end] whose cell offset mob - GM is in the footprint."""
    dt = int(dt_s * NS)
    for t in range(a, end + 1, dt):
        h, m = fld.gm(t), fld.mob(g, t)
        if h is not None and m is not None and (m[0] - h[0], m[1] - h[1]) in fp:
            return t
    return None


def detect_time(frames: Sequence[tuple[int, list[list[Any]]]], ft: Sequence[int], paths: Paths,
                g: int, a: int, end: int, project: Callable[[Any], Any], lag_s: float = LAG_S,
                px: float = DETECT_PX) -> int | None:  # fmt: skip
    """The first frame captured in [a, end + lag] with a monster box whose bottom-centre is within
    ``px`` of the mob's projected cell (GM and mob at t_frame - lag)."""
    lag = int(lag_s * NS)
    for i in range(bisect.bisect_left(ft, a), bisect.bisect_right(ft, end + lag)):
        tf, boxes = frames[i]
        if not boxes:
            continue
        off = paths.offset(g, tf - lag)
        if off is None:
            continue
        u, v = (float(x) for x in project([off])[0])
        for b in boxes:
            if b[5] == "monster" and math.hypot((b[0] + b[2]) / 2 - u, b[3] - v) <= px:
                return tf
    return None


@dataclass
class Pointer:
    """Batt's pointer: mouse_move times and game-region px (sorted)."""

    t: list[int] = field(default_factory=list)
    u: list[float] = field(default_factory=list)
    v: list[float] = field(default_factory=list)
    downs: list[int] = field(default_factory=list)  # left button downs (any position)


def pointer_of(lines: Iterable[str], desktop: tuple[int, int] = DESKTOP,
               region: tuple[int, int, int, int] = GAME_REGION) -> Pointer:  # fmt: skip
    """input_human.jsonl -> the pointer path (accepted human mouse moves and left downs)."""
    p = Pointer()
    rows = []
    for line in lines:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        e = r.get("event") or {}
        if r.get("source") != "human" or not r.get("accepted"):
            continue
        if e.get("type") == "mouse_move" or (e.get("type") == "mouse_button"
                                             and e.get("button") == "left"
                                             and e.get("action") == "down"):  # fmt: skip
            rows.append(
                (
                    int(r["t_mono_ns"]),
                    float(e["x"]) * desktop[0] - region[0],
                    float(e["y"]) * desktop[1] - region[1],
                    e.get("type") != "mouse_move",
                )
            )
    rows.sort()
    for t, u, v, down in rows:
        p.t.append(t)
        p.u.append(u)
        p.v.append(v)
        if down:
            p.downs.append(t)
    return p


def pointer_times(ptr: Pointer, paths: Paths, g: int, a: int, end: int,
                  project: Callable[[Any], Any], lag_s: float = LAG_S, px: float = PTR_PX,
                  dv: float = PTR_DV, far_px: float = PTR_FAR_PX,
                  ) -> tuple[int | None, int | None]:  # fmt: skip
    """(t_reach, t_start): the first pointer sample in [a, end] within ``px`` of the mob's body
    point (its cell at t - lag, ``dv`` px up), and the start of that final approach: the last
    sample before the reach at which the pointer was >= ``far_px`` away (the reach itself when it
    never was since the entry)."""
    lag = int(lag_s * NS)
    i0, i1 = bisect.bisect_left(ptr.t, a), bisect.bisect_right(ptr.t, end)
    last_far = None
    for i in range(i0, i1):
        off = paths.offset(g, ptr.t[i] - lag)
        if off is None:
            continue
        u, v = (float(x) for x in project([off])[0])
        d = math.hypot(ptr.u[i] - u, ptr.v[i] - (v + dv))
        if d <= px:
            return ptr.t[i], (last_far if last_far is not None else ptr.t[i])
        if d >= far_px:
            last_far = ptr.t[i]
    return None, None


def bot_selections(fld: ss.Field, bot_events: Sequence[Mapping[str, Any]],
                   engs: Sequence[Mapping[str, Any]], paths: Paths,
                   tol: float = NOTICE_CELLS, per_cell: float = NOTICE_PER_CELL,
                   lags: Sequence[float] = NOTICE_LAGS_S,
                   ) -> list[tuple[int, int, str, int]]:  # fmt: skip
    """(t, gid, how, tid) for every selection of a track the bot made that resolves to a mob:
    "cell" (a valid dispatch whose cell lies within max(``tol``, ``per_cell`` x its distance from
    our GM) of the mob at t - lag for some lag: the bot's cell error grows with the distance),
    "track" (any selection of a track whose engagement attacked that mob, or of a track it
    re-acquired as / from one), "cell_tid" (a later selection of a track whose dispatch matched)."""
    events = fld.events
    reqs = [(int(e["t_mono_ns"]), fj.gid_of(e, "target_gid")) for e in events
            if e.get("type") == "attack_request"]  # fmt: skip
    rt = [x[0] for x in reqs]
    tid_gid: dict[int, int] = {}
    for e in engs:
        t1 = int(e.get("t_first_click") or 0)
        if not t1 or e.get("pred_cell") is None or e.get("track") is None:
            continue
        pc = (int(round(e["pred_cell"][0])), int(round(e["pred_cell"][1])))
        g = None
        i = bisect.bisect_left(rt, t1)
        if i < len(reqs) and reqs[i][0] <= t1 + int(T_REQ * NS):
            rc = fld.mob(reqs[i][1], reqs[i][0])
            if rc is not None and fj.cheb(rc, pc) <= 3:
                g = reqs[i][1]
        if g is None:
            cands = [(fj.cheb(pc, mc), gg) for gg in fld.pos if fj.present(fld.lives, gg, t1)
                     and (mc := fld.mob(gg, t1)) is not None]  # fmt: skip
            cands = [x for x in cands if x[0] <= fj.NEAR]
            g = min(cands)[1] if cands else None
        if g is not None:
            tid_gid[int(e["track"])] = g
    pairs = [(int(e["track"]), int(e["as"])) for e in bot_events
             if e.get("kind") == "target_reacquired" and e.get("as") is not None]  # fmt: skip
    for _ in range(3):  # "re-acquired as": the same monster under a new id, both ways
        for x, y in pairs:
            if y in tid_gid and x not in tid_gid:
                tid_gid[x] = tid_gid[y]
            elif x in tid_gid and y not in tid_gid:
                tid_gid[y] = tid_gid[x]
    out: list[tuple[int, int, str, int]] = []
    cell_tid: dict[int, int] = {}
    for e in sorted(bot_events, key=lambda x: int(x["t_ns"])):
        k = e.get("kind")
        tid = {"dispatch": e.get("track"), "preempt": e.get("to"), "retarget": e.get("to"),
               "target_reacquired": e.get("as")}.get(str(k))  # fmt: skip
        if tid is None:
            continue
        tid = int(tid)
        if k == "dispatch" and not e.get("valid"):
            continue
        t = int(e["t_ns"])
        if tid in tid_gid:
            out.append((t, tid_gid[tid], "track", tid))
        if tid in cell_tid:
            out.append((t, cell_tid[tid], "cell_tid", tid))
        if k == "dispatch" and e.get("cell") is not None:
            c = (float(e["cell"][0]), float(e["cell"][1]))
            here = paths.gm(t)
            dist = 0.0 if here is None else max(abs(c[0] - here[0]), abs(c[1] - here[1]))
            tol_ = max(tol, per_cell * dist)
            best: tuple[float, int] | None = None
            for a_, _b, g, _r in fld.tlives:
                if a_ > t:
                    break
                for lag in lags:
                    tq = t - int(lag * NS)
                    if not fj.present(fld.lives, g, tq):
                        continue
                    m = paths.mob(g, tq)
                    if m is None:
                        continue
                    d = max(abs(m[0] - c[0]), abs(m[1] - c[1]))
                    if d <= tol_ and (best is None or d < best[0]):
                        best = (d, g)
            if best is not None:
                out.append((t, best[1], "cell", tid))
                cell_tid.setdefault(tid, best[1])
    return sorted(out)


def selection_agreement(sels: Sequence[tuple[int, int, str, int]]) -> dict[str, Any]:
    """The cell match checked against the engagement join: over the dispatches resolved BOTH
    ways, the share naming the same mob."""
    by: dict[tuple[int, int], dict[str, int]] = {}
    for t, g, how, tid in sels:
        by.setdefault((t, tid), {})[how] = g
    both = [v for v in by.values() if "cell" in v and "track" in v]
    agree = sum(1 for v in both if v["cell"] == v["track"])
    return {"both": len(both), "agree": round(agree / len(both), 3) if both else None}


def clicks_of(sess: Any, root: Path, ptr: Pointer | None) -> list[int]:
    """The subject's input click times: the bot's clicks.jsonl (every kind), Batt's left downs."""
    if sess.bot:
        lines = (root / sess.sid / "clicks.jsonl").read_text().splitlines()
        return sorted(int(json.loads(x)["t"]) for x in lines if x)
    return list(ptr.downs) if ptr is not None else []


@dataclass
class Inputs:
    """Everything ``milestones`` reads besides the Field."""

    paths: Paths
    project: Callable[[Any], Any]
    fp: set[Cell]
    frames: list[tuple[int, list[list[Any]]]] = field(default_factory=list)
    selections: list[tuple[int, int, str, int]] = field(default_factory=list)
    pointer: Pointer | None = None
    clicks: list[int] = field(default_factory=list)


def chain_end(fld: ss.Field, g: int, a: int, b: int | None, reason: int | None,
              flicker_s: float = FLICKER_S) -> tuple[int | None, int | None]:  # fmt: skip
    """The end and vanish reason of the gid's PRESENCE from the life starting at ``a``: lives of
    the same gid that leave the view (reason 0) and come back within ``flicker_s`` are one
    presence (a unit on the 14-cell edge flickers; turn_toward follows the gid, not the life)."""
    ls = sorted(fld.lives.get(g, []))
    i = next((k for k, x in enumerate(ls) if x[0] == a), None)
    if i is None:
        return b, reason
    while (ls[i][1] is not None and ls[i][2] == 0 and i + 1 < len(ls)
           and ls[i + 1][0] - ls[i][1] <= flicker_s * NS):  # fmt: skip
        i += 1
    return ls[i][1], ls[i][2]


def milestones(fld: ss.Field, inp: Inputs, g: int, a: int, b: int | None, reason: int | None,
               w1: int, horizon_s: float | None = HORIZON_S) -> dict[str, Any]:  # fmt: skip
    """Every milestone of the life (g, a .. b) -- see the module docstring. ``horizon_s`` None:
    up to the life's end (the decomposition's view)."""
    b_chain, reason = chain_end(fld, g, a, b, reason)
    end = w1 if b_chain is None else min(b_chain, w1)
    if horizon_s is not None:
        end = min(end, a + int(horizon_s * NS))
    cmds = getattr(fld, "_cmds", None)
    if cmds is None:
        cmds = commands(fld.events)
        fld._cmds = cmds  # type: ignore[attr-defined]
        fld._ct = [c[0] for c in cmds]  # type: ignore[attr-defined]
        fld._ours = [e for e in fld.events if e.get("type") == "act"  # type: ignore[attr-defined]
                     and fj.gid_of(e, "src_gid") == GM and e.get("kind") != "pickup"]  # fmt: skip
        fld._ft = [f[0] for f in inp.frames]  # type: ignore[attr-defined]
    ct, ours, ft = fld._ct, fld._ours, fld._ft  # type: ignore[attr-defined]
    m: dict[str, Any] = {k: None for k in MILESTONES}
    m.update(gid=g, t_enter=a, life_end=b, reason=reason)
    m["t_turn"], m["t_attack_req"] = turn_time(fld, cmds, ct, a, g, end)
    reqs = [c[0] for c in cmds[bisect.bisect_right(ct, a):bisect.bisect_right(ct, end)]
            if c[1] == "atk" and c[3] == g]  # fmt: skip
    m["t_last_req"] = reqs[-1] if reqs else None
    if m["t_attack_req"] is not None:
        i = bisect.bisect_right(inp.clicks, m["t_attack_req"]) - 1
        if i >= 0 and m["t_attack_req"] - inp.clicks[i] <= T_REQ * NS:
            m["t_click"] = inp.clicks[i]
    m["t_onscreen"] = onscreen_time(fld, g, a, end, inp.fp)
    if inp.frames:
        m["t_detect"] = detect_time(inp.frames, ft, inp.paths, g, a, end, inp.project)
    if inp.pointer is not None:
        m["t_notice"], m["t_ptr_start"] = pointer_times(inp.pointer, inp.paths, g, a, end,
                                                        inp.project)  # fmt: skip
    else:
        m["t_notice"] = next((t for t, gg, _h, _k in inp.selections if gg == g and a <= t <= end),
                             None)  # fmt: skip
    m["t_inrange3"] = first_within(fld, g, a, end, STRIKE)
    m["t_inrange1"] = first_within(fld, g, a, end, MELEE)
    if m["t_turn"] is not None:
        h, mm = fld.gm(m["t_turn"]), fld.mob(g, m["t_turn"])
        m["dist_turn"] = fj.cheb(h, mm) if h is not None and mm is not None else None
        if m["t_inrange3"] is not None and m["t_inrange3"] > m["t_turn"]:
            ts_ = range(m["t_turn"], m["t_inrange3"], int(0.1 * NS))
            m["moving_turn_inrange3"] = round(sum(fld.is_moving(t) for t in ts_)
                                              / max(1, len(ts_)), 2)  # fmt: skip
    acts = [x for x in ours if fj.gid_of(x, "target_gid") == g and a < int(x["t_mono_ns"]) <= end]
    dmg = [x for x in acts if int(x.get("damage", 0)) + int(x.get("damage2", 0)) > 0]
    m["t_hit"] = int(dmg[0]["t_mono_ns"]) if dmg else None
    m["t_last_act"] = int(acts[-1]["t_mono_ns"]) if acts else None
    if b_chain is not None and reason == 1 and b_chain <= end and acts:
        m["t_kill"] = b_chain
    m["n_hits"], m["n_misses"] = len(dmg), len(acts) - len(dmg)
    m["hit_gaps_s"] = [round((int(q["t_mono_ns"]) - int(p["t_mono_ns"])) / NS, 3)
                       for p, q in zip(dmg, dmg[1:], strict=False)]  # fmt: skip
    if m["t_hit"] is not None:
        tk = m["t_kill"] or m["t_last_act"]
        m["n_rereq"] = sum(1 for c in cmds if c[1] == "atk" and c[3] == g
                           and m["t_hit"] < c[0] <= tk)  # fmt: skip
        dists = [
            fj.cheb(h, mm)
            for t in range(m["t_hit"], tk + 1, int(0.1 * NS))
            if (h := fld.gm(t)) is not None and (mm := fld.mob(g, t)) is not None
        ]
        m["max_dist_hit_kill"] = max(dists) if dists else None
    return m


# --- per-entry tables -----------------------------------------------------------------------------


def _q(xs: Sequence[float]) -> dict[str, Any]:
    if not xs:
        return {"n": 0}
    a = np.asarray(xs, dtype=float)
    return {
        "n": len(xs),
        "p25": round(float(np.percentile(a, 25)), 2),
        "p50": round(float(np.percentile(a, 50)), 2),
        "p75": round(float(np.percentile(a, 75)), 2),
        "mean": round(float(a.mean()), 2),
    }


def phase_table(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Per PHASES pair: the signed time (s) where both milestones are reached, its quantiles and
    the share REVERSED (the later milestone came first); plus n reaching each milestone and the
    share reaching it within 10 s of the entry."""
    n = len(rows)
    reach = {k: sum(1 for r in rows if r.get(k) is not None) for k in MILESTONES}
    within10 = {k: round(sum(1 for r in rows if r.get(k) is not None
                             and r[k] - r["t_enter"] <= 10 * NS) / n, 2) if n else None
                for k in MILESTONES}  # fmt: skip
    out: dict[str, Any] = {"n": n, "reached": reach, "reached_within_10s": within10}
    ap = [r for r in rows if r.get("dist_turn") is not None and r.get("t_inrange3") is not None
          and r["t_inrange3"] > r["t_turn"]]  # fmt: skip
    out["approach"] = {
        "dist_at_turn_cells": _q([float(r["dist_turn"]) for r in rows
                                  if r.get("dist_turn") is not None]),
        "closing_cells_per_s": _q([max(0.0, r["dist_turn"] - STRIKE)
                                   / ((r["t_inrange3"] - r["t_turn"]) / NS) for r in ap]),
        "moving_share_turn_to_inrange3": _q([r["moving_turn_inrange3"] for r in ap
                                             if r.get("moving_turn_inrange3") is not None]),
    }  # fmt: skip
    for name, a, b in PHASES:
        d = [(r[b] - r[a]) / NS for r in rows if r.get(a) is not None and r.get(b) is not None]
        q = _q([x for x in d if x >= 0])
        q["reversed"] = round(sum(1 for x in d if x < 0) / len(d), 2) if d else None
        q["n_both"] = len(d)
        out[name] = q
    return out


def orders(rows: Sequence[Mapping[str, Any]], top: int = 6) -> dict[str, int]:
    """The most common milestone orders (notice / turn / in range 3 / click / attack request /
    melee / hit / kill), as reached."""
    keys = ("t_notice", "t_turn", "t_inrange3", "t_click", "t_attack_req", "t_inrange1", "t_hit",
            "t_kill")  # fmt: skip
    c: Counter[str] = Counter()
    for r in rows:
        seq = sorted((r[k], i, k[2:]) for i, k in enumerate(keys) if r.get(k) is not None)
        c[" > ".join(s[2] for s in seq) or "-"] += 1
    return dict(c.most_common(top))


def pointer_quality(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Batt's pointer proxy: on the entries he attacked, the share with a reach before his click
    and its lead (click - reach, click - approach start); on the entries he never attacked that
    stayed on screen >= 2 s, the share with a reach anyway (the proxy's false-positive rate)."""
    att = [r for r in rows if r.get("t_click") is not None]
    lead = [(r["t_click"] - r["t_notice"]) / NS for r in att
            if r.get("t_notice") is not None and r["t_notice"] <= r["t_click"]]  # fmt: skip
    lead0 = [(r["t_click"] - r["t_ptr_start"]) / NS for r in att
             if r.get("t_ptr_start") is not None and r["t_ptr_start"] <= r["t_click"]]  # fmt: skip
    never = [r for r in rows if r.get("t_attack_req") is None and r.get("t_onscreen") is not None
             and ((r.get("life_end") or 0) - r["t_onscreen"]) >= 2 * NS]  # fmt: skip
    fp = sum(1 for r in never if r.get("t_notice") is not None)
    return {
        "attacked_with_click": len(att),
        "reach_before_click": round(len(lead) / len(att), 2) if att else None,
        "click_minus_reach_s": _q(lead),
        "click_minus_approach_start_s": _q(lead0),
        "never_attacked_onscreen_2s": len(never),
        "never_attacked_but_reached": round(fp / len(never), 2) if never else None,
    }


def notice_quality(rows: Sequence[Mapping[str, Any]], sels: Sequence[tuple[int, int, str, int]]
                   ) -> dict[str, Any]:  # fmt: skip
    """The bot's notice: how its selections resolved, and on the entries it attacked the share
    with a notice before the click and the lead."""
    att = [r for r in rows if r.get("t_click") is not None]
    lead = [(r["t_click"] - r["t_notice"]) / NS for r in att
            if r.get("t_notice") is not None and r["t_notice"] <= r["t_click"]]  # fmt: skip
    return {
        "selections_resolved": dict(Counter(h for _t, _g, h, _k in sels)),
        "cell_vs_engagement_join": selection_agreement(sels),
        "attacked_with_click": len(att),
        "notice_before_click": round(len(lead) / len(att), 2) if att else None,
        "click_minus_notice_s": _q(lead),
    }


def hit_kill(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Over the killed entries (one per kill: flicker re-entries of a gid share its kill): hits per
    kill, misses per kill, the gap between our damaging acts, re-requests after the first hit, the
    GM-mob distance between hit and kill, hit->kill."""
    uniq = {(r["gid"], r["t_kill"]): r for r in rows
            if r.get("t_kill") is not None and r.get("t_hit") is not None}  # fmt: skip
    k = list(uniq.values())
    if not k:
        return {"kills": 0}
    gaps = [g for r in k for g in r.get("hit_gaps_s", [])]
    return {"kills": len(k),
            "hits_per_kill": round(sum(r["n_hits"] for r in k) / len(k), 2),
            "one_hit_share": round(sum(1 for r in k if r["n_hits"] == 1) / len(k), 2),
            "misses_per_kill": round(sum(r["n_misses"] for r in k) / len(k), 2),
            "hit_gap_s": _q(gaps),
            "rereq_per_kill": round(sum(r.get("n_rereq", 0) for r in k) / len(k), 2),
            "max_dist_hit_kill_p50_p90": [fj.pct([float(r["max_dist_hit_kill"]) for r in k
                                                  if r.get("max_dist_hit_kill") is not None], q)
                                          for q in (0.5, 0.9)],
            "hit_to_kill_s": _q([(r["t_kill"] - r["t_hit"]) / NS for r in k])}  # fmt: skip


def bot_strikes(engs: Sequence[Mapping[str, Any]], t0: int, w1: int) -> dict[str, Any]:
    """The bot's own view of in range -> click (engagements' first hover): in_range_to_click_s by
    arm_eff and fallback, and the hovers per engagement."""
    first = [e["hovers"][0] for e in engs if e.get("hovers")
             and t0 <= int(e.get("t_first_click") or 0) < w1]  # fmt: skip
    by: dict[str, list[float]] = {}
    for h in first:
        key = f"{h.get('arm_eff')}/{h.get('fallback')}"
        if h.get("in_range_to_click_s") is not None:
            by.setdefault(key, []).append(float(h["in_range_to_click_s"]))
    allv = [x for v in by.values() for x in v]
    return {"engagements": len(first),
            "in_range_to_click_s": _q(allv),
            "by_arm_fallback": {k: {"share": round(len(v) / max(1, len(allv)), 2), **_q(v)}
                                for k, v in sorted(by.items(), key=lambda kv: -len(kv[1]))},
            "hovers_per_engagement": round(sum(len(e.get("hovers") or []) for e in engs
                                               if t0 <= int(e.get("t_first_click") or 0) < w1)
                                           / max(1, len(first)), 2)}  # fmt: skip


# --- the decomposition ----------------------------------------------------------------------------


def loot_windows(
    events: Sequence[Mapping[str, Any]],
    kills: Sequence[int],
    first_s: float = LOOT_FIRST_S,
    gap_s: float = LOOT_GAP_S,
) -> list[tuple[int, int]]:
    """Per kill: [kill, the last pickup request of the chain that starts <= first_s after it and
    continues <= gap_s apart]; no window when no pickup follows within first_s."""
    pt = sorted(int(e["t_mono_ns"]) for e in events if e.get("type") == "pickup_request")
    out = []
    for k in sorted(kills):
        i = bisect.bisect_left(pt, k)
        if i >= len(pt) or pt[i] - k > first_s * NS:
            continue
        j = i
        while j + 1 < len(pt) and pt[j + 1] - pt[j] <= gap_s * NS:
            j += 1
        out.append((k, pt[j]))
    return out


def status_at(fld: ss.Field, m: Mapping[str, Any], g: int, t: int) -> str:
    """One target's status at ``t`` (the module docstring's decomposition labels, LOOT aside)."""
    th = m.get("t_hit")
    if th is not None and t >= th:
        end = m.get("t_kill") or ((m.get("t_last_act") or th) + int(FIGHT_TAIL_S * NS))
        if t <= end:
            return "FIGHT"
    ta = m.get("t_attack_req")
    tc = m.get("t_click") or ta
    h, mm = fld.gm(t), fld.mob(g, t)
    d = fj.cheb(h, mm) if h is not None and mm is not None else None
    if tc is not None and t >= tc:
        until = th if th is not None else (m.get("t_last_req") or ta) + int(CLICK_TAIL_S * NS)
        if t < until:
            return "CLICKED_WALK_UP" if d is not None and d > MELEE else "CLICKED_REACH"
    if d is not None and d <= STRIKE and (tc is None or t < tc):
        return "IN_RANGE"
    if m.get("t_turn") is not None and t >= m["t_turn"]:
        return "TURNED"
    if m.get("t_notice") is not None and t >= m["t_notice"]:
        return "NOTICED"
    if m.get("t_detect") is not None and t >= m["t_detect"]:
        return "UNNOTICED_DETECTED"
    if m.get("t_onscreen") is not None and t >= m["t_onscreen"]:
        return "UNNOTICED_ONSCREEN"
    return "UNNOTICED_OFFSCREEN"


def outcome(m: Mapping[str, Any]) -> str:
    if m.get("t_kill") is not None:
        return "killed"
    return "attacked_not_killed" if m.get("t_attack_req") is not None else "never_attacked"


def bot_activity(bot_events: Sequence[Mapping[str, Any]], engs: Sequence[Mapping[str, Any]]
                 ) -> list[tuple[int, int, str]]:  # fmt: skip
    """The bot's own activity spans [(t0, t1, what)]: its ``mode`` (search / steer / engaged)
    between mode events, with each engagement's loot step ([t_end - loot.s, t_end]) as
    "loot_step". Read by ``decompose`` only to explain a label (never part of the ruler)."""
    ms = sorted((int(e["t_ns"]), str(e.get("mode"))) for e in bot_events
                if e.get("kind") == "mode")  # fmt: skip
    spans = [(t, (ms[i + 1][0] if i + 1 < len(ms) else 2**62), m) for i, (t, m) in enumerate(ms)]
    loot = sorted((int(e["t_end"]) - int(float(e["loot"]["s"]) * NS), int(e["t_end"]), "loot_step")
                  for e in engs if e.get("t_end") and isinstance(e.get("loot"), dict)
                  and e["loot"].get("s") is not None)  # fmt: skip
    out: list[tuple[int, int, str]] = []
    for a, b, m in spans:  # cut the loot steps out of the mode spans
        cur = a
        for la, lb, _w in loot:
            if lb <= cur or la >= b:
                continue
            if la > cur:
                out.append((cur, la, m))
            out.append((max(la, cur), min(lb, b), "loot_step"))
            cur = min(lb, b)
        if cur < b:
            out.append((cur, b, m))
    return out


def decompose(fld: ss.Field, s: ss.Scan, lives: Mapping[tuple[int, int], Mapping[str, Any]],
              loot: Sequence[tuple[int, int]], r: int = VIEW,
              activity: Sequence[tuple[int, int, str]] = ()) -> dict[str, Any]:  # fmt: skip
    """Every scan sample with an alive target within ``r`` -> ONE (status, outcome) label from the
    most advanced target in view (STATUSES order; LOOT between CLICKED and IN_RANGE, outcome
    "loot"). Returns the sample counts and seconds per label (their sum is the in-view time), and
    per label the share of samples with our GM moving, the deciding target's mean distance
    (cells) and, given the bot's ``activity`` spans, the seconds per activity."""
    lt = [w[0] for w in loot]
    at_ = [x[0] for x in activity]
    rank = {k: i for i, k in enumerate(STATUSES)}
    cnt: Counter[tuple[str, str]] = Counter()
    mov: Counter[tuple[str, str]] = Counter()
    dsum: Counter[tuple[str, str]] = Counter()
    act: dict[tuple[str, str], Counter[str]] = {}
    n_in = 0
    for k in range(len(s.t)):
        if s.n_targets[k] <= 0:
            continue
        n_in += 1
        t = int(s.t[k])
        here = (int(s.x[k]), int(s.y[k]))
        best: tuple[int, str, str, int] | None = None
        for a, b, g, _rr in fld.tlives:
            if a > t:
                break
            if b is not None and t >= b:
                continue
            c = fld.mob(g, t)
            if c is None or fj.cheb(c, here) > r:
                continue
            m = lives.get((g, a))
            if m is None:
                continue
            st = status_at(fld, m, g, t)
            if best is None or rank[st] < best[0]:
                best = (rank[st], st, outcome(m), fj.cheb(c, here))
        i = bisect.bisect_right(lt, t) - 1
        in_loot = i >= 0 and loot[i][0] <= t <= loot[i][1]
        if best is None:
            label = ("UNNOTICED_OFFSCREEN", "never_attacked")
        elif in_loot and best[0] > rank["LOOT"]:
            label = ("LOOT", "loot")
        else:
            label = (best[1], best[2])
        cnt[label] += 1
        mov[label] += int(bool(s.moving[k]))
        dsum[label] += best[3] if best is not None else 0
        if activity:
            j = bisect.bisect_right(at_, t) - 1
            w = activity[j][2] if j >= 0 and t < activity[j][1] else "none"
            act.setdefault(label, Counter())[w] += 1
    dt = s.dt_s

    def key(x: tuple[str, str]) -> str:
        return f"{x[0]}|{x[1]}"

    return {"samples_in_view": n_in, "dt_s": dt,
            "seconds": {key(x): round(v * dt, 2) for x, v in sorted(cnt.items())},
            "counts": {key(x): v for x, v in sorted(cnt.items())},
            "moving": {key(x): mov[x] for x in cnt},
            "dist_sum": {key(x): dsum[x] for x in cnt},
            "activity": {key(x): dict(c) for x, c in act.items()}}  # fmt: skip


def per_kill(dec: Mapping[str, Any], kills: int) -> dict[str, Any]:
    """The decomposition per kill, grouped: the killed targets' phases, loot, attacked-not-killed,
    never attacked; and the sum check against the in-view time."""
    sec = dec["seconds"]

    def tot(pred: Callable[[str, str], bool]) -> float:
        return sum(v for k, v in sec.items() if pred(*k.split("|")))

    groups = {
        "killed:unnoticed(enter->notice)": tot(lambda s_, o: o == "killed"
                                               and s_.startswith("UNNOTICED")),
        "killed:noticed->turn": tot(lambda s_, o: o == "killed" and s_ == "NOTICED"),
        "killed:turn->in_range": tot(lambda s_, o: o == "killed" and s_ == "TURNED"),
        "killed:in_range->click": tot(lambda s_, o: o == "killed" and s_ == "IN_RANGE"),
        "killed:click->hit(walk_up)": tot(lambda s_, o: o == "killed"
                                          and s_ == "CLICKED_WALK_UP"),
        "killed:click->hit(reach)": tot(lambda s_, o: o == "killed" and s_ == "CLICKED_REACH"),
        "killed:hit->kill": tot(lambda s_, o: o == "killed" and s_ == "FIGHT"),
        "loot(after a kill)": tot(lambda s_, o: o == "loot"),
        "attacked_not_killed": tot(lambda s_, o: o == "attacked_not_killed"),
        "never_attacked": tot(lambda s_, o: o == "never_attacked"),
    }  # fmt: skip
    total = dec["samples_in_view"] * dec["dt_s"]
    cnt = dec.get("counts", {})
    diag = {k: {"moving_share": round(dec["moving"][k] / n, 2),
                "mean_dist_cells": round(dec["dist_sum"][k] / n, 1),
                **({"bot_activity_share": {a: round(c / n, 2) for a, c in sorted(
                    dec["activity"][k].items(), key=lambda kv: -kv[1])}}
                   if k in dec.get("activity", {}) else {})}
            for k, n in cnt.items() if n and "moving" in dec}  # fmt: skip
    out = {k: round(v / kills, 2) if kills else None for k, v in groups.items()}
    detail = {k: round(v / kills, 2) for k, v in sec.items()} if kills else {}
    return {"per_kill_s": out, "detail_per_kill_s": detail, "label_diagnostics": diag,
            "in_view_s_per_kill": round(total / kills, 2) if kills else None,
            "sum_check_s": round(sum(groups.values()) - total, 6)}  # fmt: skip


# --- sessions -------------------------------------------------------------------------------------


@dataclass
class Result:
    sid: str
    bot: bool
    rows: list[dict[str, Any]]  # the cohort entries (free and busy) with their milestones
    lives: dict[tuple[int, int], dict[str, Any]]  # every target life (no horizon)
    dec: dict[str, Any]
    kills: int
    some_s_per_kill: float | None
    turn_toward: dict[str, Any]
    extra: dict[str, Any] = field(default_factory=dict)
    sels: list[tuple[int, int, str, int]] = field(default_factory=list)
    engs: list[dict[str, Any]] = field(default_factory=list)  # the bot's, in the window


def analyse(sid: str, root: Path | None = None, project: Callable[[Any], Any] | None = None,
            fp: set[Cell] | None = None) -> Result:  # fmt: skip
    if root is None:
        from poring_env.demo import DEMO_ROOT

        root = DEMO_ROOT
    sess = ss.load_session(sid, root)
    fld = ss.Field(sess.events)
    paths = Paths(fld)
    project = project or camera_projector()
    fp = fp if fp is not None else footprint_set(project)
    d = root / sid
    frames = []
    if (d / "boxes.jsonl").exists():
        for line in (d / "boxes.jsonl").read_text().splitlines():
            if line:
                x = json.loads(line)
                frames.append((int(x["t"]), x["boxes"]))
    frames.sort(key=lambda f: f[0])
    ptr = None
    sels: list[tuple[int, int, str, int]] = []
    if sess.bot:
        sels = bot_selections(fld, sess.bot_events, sess.engagements, paths)
    else:
        ptr = pointer_of((d / "input_human.jsonl").read_text().splitlines())
    inp = Inputs(paths, project, fp, frames, sels, ptr, clicks_of(sess, root, ptr))
    rows = []
    for e in entries(fld, sess.t0, sess.w1):
        m = milestones(fld, inp, e["gid"], e["t"], e["life_end"], e["reason"], sess.w1)
        rows.append({**m, "busy": e["busy"], "off": e["off"]})
    lives = {}
    for a, b, g, rr in fld.tlives:
        if (b is None or b > sess.t0) and a < sess.w1:
            lives[(g, a)] = milestones(fld, inp, g, a, b, rr, sess.w1, horizon_s=None)
    s = ss.scan(fld, sess.t0, sess.w1, None)
    kills = ss.kill_times(sess.events, sess.t0, sess.w1)
    s.kills = len(kills)
    pres = ss.presence_summary([s])
    acty = bot_activity(sess.bot_events, sess.engagements) if sess.bot else []
    dec = decompose(fld, s, lives, loot_windows(sess.events, kills), activity=acty)
    res = Result(sid, sess.bot, rows, lives, dec, len(kills), pres["some_s_per_kill"],
                 ss.turn_toward(fld, sess.t0, sess.w1))  # fmt: skip
    res.extra["window_s"] = round((sess.w1 - sess.t0) / NS, 1)
    res.sels = sels
    res.engs = [e for e in sess.engagements
                if sess.t0 <= int(e.get("t_first_click") or 0) < sess.w1]  # fmt: skip
    if sess.bot:
        res.extra["notice_quality"] = notice_quality([r for r in rows if not r["busy"]], sels)
        res.extra["bot_strikes"] = bot_strikes(sess.engagements, sess.t0, sess.w1)
        res.extra["change"] = json.loads((d / "manifest.json").read_text()).get("change")
    else:
        res.extra["pointer_quality"] = pointer_quality([r for r in rows if not r["busy"]])
        res.extra["pointer_quality_all"] = pointer_quality(rows)
    return res


def summary(results: Sequence[Result]) -> dict[str, Any]:
    """One subject (a session, or the bot runs pooled): the cohort check, the free / busy phase
    tables, orders, hit -> kill and the decomposition per kill."""
    rows = [r for x in results for r in x.rows]
    free = [r for r in rows if not r["busy"]]
    busy = [r for r in rows if r["busy"]]
    kills = sum(x.kills for x in results)
    sec: Counter[str] = Counter()
    cnt: Counter[str] = Counter()
    mov: Counter[str] = Counter()
    dsum: Counter[str] = Counter()
    act: dict[str, Counter[str]] = {}
    n_in = 0
    for x in results:
        n_in += x.dec["samples_in_view"]
        for k, v in x.dec["seconds"].items():
            sec[k] += v
        cnt.update(x.dec["counts"])
        mov.update(x.dec["moving"])
        dsum.update(x.dec["dist_sum"])
        for k, c in x.dec.get("activity", {}).items():
            act.setdefault(k, Counter()).update(c)
    dec = {"samples_in_view": n_in, "dt_s": results[0].dec["dt_s"],
           "seconds": {k: round(v, 2) for k, v in sec.items()}, "counts": dict(cnt),
           "moving": dict(mov), "dist_sum": dict(dsum),
           "activity": {k: dict(c) for k, c in act.items()}}  # fmt: skip
    att10 = (
        round(
            sum(
                1
                for r in free
                if r["t_attack_req"] is not None and r["t_attack_req"] - r["t_enter"] <= 10 * NS
            )
            / len(free),
            2,
        )
        if free
        else None
    )
    tt_n = sum(x.turn_toward["free_any"]["n"] for x in results)
    return {
        "sessions": len(results), "kills": kills,
        "cohort_check": {"free_n": len(free), "turn_toward_free_n": tt_n,
                         "match": len(free) == tt_n, "attacked_10s": att10,
                         "turn_toward_attacked_10s": [x.turn_toward["free_any"]["attacked_10s"]
                                                      for x in results],
                         "busy_n": len(busy)},
        "free": phase_table(free), "busy": phase_table(busy),
        "orders_free": orders(free),
        "hit_kill_free": hit_kill(free), "hit_kill_all_lives": hit_kill(
            [m for x in results for m in x.lives.values()]),
        "decomposition": per_kill(dec, kills),
        "presence_some_s_per_kill": round(n_in * dec["dt_s"] / kills, 2) if kills else None,
    }  # fmt: skip


def compare(batt: str, bots: Sequence[str], root: Path | None = None) -> dict[str, Any]:
    project = camera_projector()
    fp = footprint_set(project)
    rb = analyse(batt, root, project, fp)
    rbots = [analyse(s, root, project, fp) for s in bots]
    out: dict[str, Any] = {
        "constants": {"LAG_S": LAG_S, "DETECT_PX": DETECT_PX, "PTR_PX": PTR_PX, "PTR_DV": PTR_DV,
                      "NOTICE_CELLS": NOTICE_CELLS, "HORIZON_S": HORIZON_S,
                      "footprint_cells": len(fp)},
        "batt": {**summary([rb]), **rb.extra},
        "bot_pooled": {**summary(rbots),
                       "notice_quality": notice_quality(
                           [r for x in rbots for r in x.rows if not r["busy"]],
                           [y for x in rbots for y in x.sels]),
                       "bot_strikes": bot_strikes([e for x in rbots for e in x.engs], 0, 2**62)},
        "bot_sessions": {x.sid: {**summary([x]), **x.extra} for x in rbots},
    }  # fmt: skip
    a = out["batt"]["decomposition"]["per_kill_s"]
    b = out["bot_pooled"]["decomposition"]["per_kill_s"]
    gap = {k: round((b[k] or 0) - (a[k] or 0), 2) for k in a}
    out["gap_per_kill_s"] = dict(sorted(gap.items(), key=lambda kv: -kv[1]))
    out["gap_total_s"] = round(out["bot_pooled"]["decomposition"]["in_view_s_per_kill"]
                               - out["batt"]["decomposition"]["in_view_s_per_kill"], 2)  # fmt: skip
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compare")
    c.add_argument("batt")
    c.add_argument("bots", nargs="+")
    a = ap.parse_args()
    print(json.dumps(compare(a.batt, a.bots), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
