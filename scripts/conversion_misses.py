#!/usr/bin/env python3
"""The CONVERSION study, the MISSES half (Batt 2026-10-18): WHY the bot does not attack a FREE
target that comes into its view within 10 s, where Batt attacks 78 % of them and the bot ~40 %;
and what its in range -> click time is spent on. OFFLINE, on banked sessions: the packets are
ground truth here (ADR-0007) and never a decision input (rule 1); nothing in this module runs
during play and the bot (scripts/hunt_flow.py and what it imports) never imports it. It is a judge,
like search_study.py, and reuses search_study's ruler (load_session's windows, Field, the cohort).

    conversion_misses.py compare BATT_SID BOT_SID [BOT_SID ...]   every table below (JSON)

DEFINITIONS
- THE COHORT (``free_entries``) = search_study.turn_toward's FREE target view entries, rebuilt row
  for row: a target (Poring 1002, Lunatic 1063, Pupa 1008, Drops 1113) starts a life in our view
  (entity_appear: the server sent it within 14 cells), with no OTHER alive target within 14 cells
  and no attack request of ours in the 3 s before, in [t0, w1 - 10 s). ATTACKED = an attack
  request on it within 10 s (``free_any.n`` and ``attacked_10s`` reproduce turn_toward's: tested).
- THE WINDOW of an entry W = [entry, min(entry + 10 s, its life's end)).
- ON SCREEN (``Screen``): its packet cell, relative to our GM's packet cell, both LAG_S (0.45 s)
  before a detector frame, is in hunt_flow's camera FOOTPRINT (``hc.footprint``: the flat-ground
  cells drawn in the 1280 x 720 game region outside the static UI, ``loot1.in_ui``). The frames
  lag the server ~0.5 s (frames-lag-server memory); LAG_S is arm_judge.sword_precision's.
- DETECTED on a frame (boxes.jsonl: every processed frame, empty ones too): a detector box whose
  foot point (``f1.foot`` minus ``loot1.FOOT_LIFT``) picks (``picking.pick_cells`` on the GAT,
  from the GM's lagged cell) a cell within MATCH_CELLS (2, Chebyshev) of the mob's lagged cell AND
  the mob is the box's nearest alive mob (any species) -- one box, one mob. Measured on v37: 54 %
  of monster boxes fall on a mob's cell, 85 % within 1, 89 % within 2 (the rest: no mob near).
- GATED (``gate_of``): hunt_flow's ``sightings_in`` gates, in its order, on the matched box: class
  not "monster", the Creamy SIZE gate (native px > f1.MAX_NATIVE_PX, the flat-ground scale at the
  cell), a floor-item box (min side < min_box_px), the box centre in the UI, the cell outside the
  bot's search area (stand cells minus a 20-cell border and 10 cells round warps / NPCs).
- BOT STATE (``BotState``, from engagements.json + events.jsonl + clicks.jsonl + the packets):
  ENGAGED from an engagement's first strike click to its t_end, split into FIGHT (to the engaged
  mob's death packet), DEAD_WAIT (death -> the loot step's start: the dead-confirmation rule) and
  LOOT (t_end - loot.s -> t_end). PURSUIT segments (the executor's ``target``): set by dispatch
  (valid) / preempt / retarget / target_reacquired / looter_engage / zone_plan / strike_call (a
  dispatch is logged ONCE per (track, valid): a re-dispatch shows only in the steps naming the
  target), ended by target_lost / target_dropped / hand_off / the next set. A bot TRACK is joined
  to a packet gid by (a) the attack requests whose last click before them (<= 1.5 s) was a strike
  on that track (apart_why's join), (b) a dispatch's logged cell or a strike click's pred_cell vs
  the targets' lagged cells (<= 5 cells, the nearest, >= 2 cells nearer than the next), then
  target_reacquired hands a gid on, and (c) for tracks still unjoined, the gate-passing boxes on
  the frames of their pursuit: one gid on >= 70 % of those frames joins it; "no mob" on >= 70 %
  makes it a GHOST (a box on no mob: scenery, a corpse, a floor item). Measured on v37: 165 of
  477 dispatch cells had no target within 9 cells, 119 of them no mob at all.
- BUSY_OTHER (``BotState.busy_other``): engaged with another mob, or pursuing a track joined to
  another gid that we attacked by the pursuit's end + 2 s (a productive pursuit).

THE DECISION LIST (``classify``): one PRIMARY cause per not-attacked free entry, the first rule
that holds, in the pipeline's order (each later rule assumes every earlier one passed); every
rule that holds is also kept as a secondary FLAG.
  1. off_screen         never on screen on any frame in W (inside the server's 14-cell view, never
                        drawn outside the UI): out of reach of the pixels.
  2. busy:<phase>       on screen, but for < MIN_FREE_S (1.0 s) of it was the bot not ENGAGED with
                        another mob; <phase> = fight / dead_wait / loot, the phase holding most of
                        that time (an engagement of this target itself is not busy).
  3. undetected         on screen with the bot free >= MIN_FREE_S, no matched box on those frames
                        (flag ``detected_only_busy``: boxes only while it was engaged).
  4. gated:<gate>       matched while free, every matched box failed a sightings_in gate (the
                        gate that removed most of them).
  5. never_attended:<x> a box passed the gates while free, but no pursuit segment or strike of the
                        bot was on a track joined to it in W. <x> = what the bot did on most of
                        those frames: pursuing_target (another target's track), pursuing_nontarget
                        (a track joined to a non-target gid: a Creamy...), pursuing_ghost,
                        pursuing_unjoined (a track nothing joins), none (no target at all: the
                        planner did not dispatch it -- the reason is UNLOGGED: banned cells, done
                        ids, a stale box at dispatch, a cell not yet tracked; flag
                        ``drop_15s_before`` when a drop / give-up came <= 15 s before).
  6. attended:<end>     it was pursued but not attacked within W; <end> = what ended the pursuit
                        (a switch to another track of the SAME gid -- a tracker split -- does not):
                        target_lost:<offscreen|undetected|other> (the 2 s before the loss: its last
                        frame off screen / on screen with no box), dropped:<why>,
                        retarget_away:<target|nontarget|ghost|unjoined> / preempt_away:<...> (what
                        it switched to), hand_off:<after>, strike_no_request (a strike click on its
                        track with no attack request within 1.5 s: the click missed),
                        struck_at_end (a strike in W whose request came just after it), steering
                        (still walking to it at W's end), gone (its life ended while pursued).
  An entry ATTACKED after 10 s (same life) gets primary ``attacked_late`` with ``delay`` = the
  list's cause for its first 10 s, and the lateness.
COST of a cause, two columns, per kill (search_study.kill_times in the same window): ``s_per_kill``
= the in-view seconds of its entries inside W (capped at 10 s, ended by the life's end);
``idle_s_per_kill`` = the part of those seconds the bot was NOT converting another mob
(busy_other): the time the miss really lost. Causes are ranked by idle seconds.

BATT (``classify_packets``, packets + his detector frames only): the same cohort, a packet-only
list applied to Batt AND the bot, side by side: off_screen, busy_attack (an attack request on
another mob in W), busy_loot (a pickup request in W), left_view (the life ended, reason 0, in W),
ignored (none of these).

STRIKES ON WALKERS (``strike_landing``, ``approach_profile``): each first strike click's landing
(an attack request <= 1.5 s after it) by GM / mob walking, the FALSE "dead" calls (the joined gid
did not die), and per cause the GM -> target distance at 0 / 3 / 6 / 10 s and the cells walked.

IN RANGE -> CLICK (``in_range_table``): per engagement, its first CLICKED hover's
in_range_to_click_s, by cause: reread:<read> (an unclicked hover before it: the SWORD read said
no and was read again), risk_read:<read> (the risk gate's read path), fallback:<why> (arm C fell
back to A: the tag read), arm_C (the nudge, no fallback), arm_None (a call outside the A / B / C
test: a re-strike, a moving strike). The excess over arm_C's p50, per kill, is that cause's cost;
plus the strike calls' risk reads, unclicked hovers, burst ends and tag_refused waits.
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import flow_judge as fj  # noqa: E402
import search_study as ss  # noqa: E402

NS = 10**9
VIEW = 14
WITHIN_S = 10.0
BUSY_S = 3.0
LAG_S = 0.45  # the frames lag the server (arm_judge.sword_precision's)
MATCH_CELLS = 2
JOIN_DISPATCH_CELLS = 5
JOIN_UNIQUE = 2  # the second-nearest target must be this many cells farther
JOIN_CLICK_S = 1.5
MIN_FREE_S = 1.0
BAN_S = 15.0  # hunt_flow's drop_target_s
MAX_NATIVE_PX = 45.0  # farm1.MAX_NATIVE_PX
MIN_BOX_PX = 16.0  # hunt_flow PARAMS min_box_px (every version studied)
TARGETS = ss.TARGETS
Cell = tuple[int, int]
PHASES = ("fight", "dead_wait", "loot")


# --- the cohort -----------------------------------------------------------------------------------


def free_entries(fld: ss.Field, t0: int, w1: int, r: int = VIEW, within_s: float = WITHIN_S,
                 busy_s: float = BUSY_S) -> list[dict[str, Any]]:  # fmt: skip
    """search_study.turn_toward's rows (the same order of tests), for the FREE entries only, with
    what this study needs: the entry's gid, job, life end + reason, the first attack request on
    it in this life (``latk_any`` s, any delay), ``latk`` (within ``within_s``), the turn
    latency."""
    cmds = sorted([(int(e["t_mono_ns"]), "move", (int(e["x"]), int(e["y"])), -1)
                   for e in fld.events if e.get("type") == "self_move_request"]
                  + [(int(e["t_mono_ns"]), "atk", None, fj.gid_of(e, "target_gid"))
                     for e in fld.events if e.get("type") == "attack_request"],
                  key=lambda c: c[0])  # fmt: skip
    ct = [c[0] for c in cmds]
    atk = [(c[0], c[3]) for c in cmds if c[1] == "atk"]
    atk_t = [a[0] for a in atk]
    life_of = {(a, g): (b, rr) for a, b, g, rr in fld.tlives}
    rows = []
    for a, g in fld.entries(t0, int(w1 - within_s * NS)):
        here, m = fld.gm(a), fld.mob(g, a)
        if here is None or m is None:
            continue
        others = [x for x in fld.targets_at(a) if x[0] != g and fj.cheb(x[1], here) <= r]
        i = bisect.bisect_right(atk_t, a) - 1
        if others or (i >= 0 and a - atk_t[i] <= busy_s * NS):
            continue
        lat = latk = None
        j = bisect.bisect_right(ct, a)
        while j < len(cmds) and cmds[j][0] <= a + within_s * NS:
            tc, kind, dst, tg = cmds[j]
            if kind == "atk" and tg == g:
                latk = (tc - a) / NS
                lat = latk if lat is None else lat
                break
            if kind == "move" and lat is None and dst is not None:
                h2, m2 = fld.gm(tc), fld.mob(g, tc)
                if (h2 and m2 and dst != h2 and ss._adiff(ss._ang(h2, dst), ss._ang(h2, m2))
                        <= math.radians(45)):  # fmt: skip
                    lat = (tc - a) / NS
            j += 1
        b, reason = life_of.get((a, g), (None, None))
        end = b if b is not None else w1
        k = bisect.bisect_right(atk_t, a)
        latk_any = None
        while k < len(atk) and atk[k][0] < end:
            if atk[k][1] == g:
                latk_any = (atk[k][0] - a) / NS
                break
            k += 1
        rows.append({"t": a, "gid": g, "job": fld.job.get(g), "here": here, "cell": m,
                     "dist": fj.cheb(m, here), "life_end": b, "reason": reason, "lat": lat,
                     "latk": latk, "latk_any": latk_any})  # fmt: skip
    return rows


def window_end(row: Mapping[str, Any], within_s: float = WITHIN_S) -> int:
    end = int(row["t"] + within_s * NS)
    return end if row["life_end"] is None else min(end, int(row["life_end"]))


# --- the screen -----------------------------------------------------------------------------------


@dataclass
class Screen:
    """What the pixels can show: the footprint offsets, a picker (origin, pts (N, 2)) -> cell
    offsets (N, 2) (<-1000: no hit), the flat-ground scale at an offset, the UI test, the bot's
    search area (None: every cell)."""

    offsets: frozenset[Cell]
    pick: Callable[[Cell, Any], Any]
    scale: Callable[[Cell], float] = lambda o: 1.0
    in_ui: Callable[[float, float], bool] = lambda u, v: False
    area: Any = None


def load_screen(map_name: str) -> Screen:
    """hunt_flow.run's camera (camera_rdp.json), footprint, in_view and search area, offline (the
    GAT, the KB and the map cache are client- / GPL-derived: read at run time, never committed)."""
    import hunt_core as hc
    import loot1
    import ro_agent as r
    from anim_region import stand_grid

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod
    from poring_dataset import picking

    gat = gatmod.parse((cam.GAT_DIR / f"{map_name}.gat").read_bytes())
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    camera = cam.camera_from_json(cj["camera"])

    def in_view(u: float, v: float) -> bool:
        return 0 <= u < 1280 and 0 <= v < 720 and not loot1.in_ui(u, v)

    offs = hc.footprint(lambda o: camera.project(o, np.zeros(len(o))), in_view)
    area = None
    try:
        ok = stand_grid(map_name, gat)
        kb = r.ROOT / "data" / "kb"
        warps = json.loads((kb / "warps.json").read_text()).get(map_name, [])
        npcs = (json.loads((kb / "npc_cells.json").read_text())["maps"].get(map_name, {})
                .get("npcs", []))  # fmt: skip
        keep = [(w["x"], w["y"], w["span_x"], w["span_y"]) for w in warps]
        keep += [(n["x"], n["y"], 1, 1) for n in npcs]
        area = hc.search_area(ok, keep, margin=10)
    except (OSError, SystemExit, ValueError, KeyError, Exception):  # noqa: BLE001
        area = None
    p00 = camera.project(np.array([[0.0, 0.0], [1.0, 0.0]]), np.zeros(2))
    px0 = float(np.hypot(*(p00[1] - p00[0])))

    def scale(o: Cell) -> float:
        p = camera.project(np.array([[o[0], o[1]], [o[0] + 1.0, o[1]]], dtype=float), np.zeros(2))
        return float(np.hypot(*(p[1] - p[0]))) / px0 if px0 > 0 else 1.0

    def pick(origin: Cell, pts: Any) -> Any:
        return picking.pick_cells(camera, gat, origin, pts)

    return Screen(frozenset((int(a), int(b)) for a, b in offs), pick, scale,
                  lambda u, v: bool(loot1.in_ui(u, v)), area)  # fmt: skip


def gate_of(box: Sequence[Any], cell: Cell, scale: float, scr: Screen,
            min_box_px: float = MIN_BOX_PX) -> str | None:  # fmt: skip
    """hunt_flow.sightings_in's gates on one box, in its order (None = it passes)."""
    x0, y0, x1, y1 = (float(v) for v in box[:4])
    if len(box) > 5 and box[5] != "monster":
        return "not_monster"
    if max(x1 - x0, y1 - y0) / max(scale, 1e-6) > MAX_NATIVE_PX:
        return "creamy_size"
    if min(x1 - x0, y1 - y0) < min_box_px:
        return "min_box_px"
    if scr.in_ui((x0 + x1) / 2, (y0 + y1) / 2):
        return "in_ui"
    a = scr.area
    if a is not None and not (0 <= cell[1] < a.shape[0] and 0 <= cell[0] < a.shape[1]
                              and a[cell[1], cell[0]]):  # fmt: skip
        return "outside_area"
    return None


@dataclass
class FrameObs:
    """One detector frame: its time, the GM's lagged cell, and per box (gid matched or None,
    the gate or None, the picked cell)."""

    t: int
    gm: Cell | None
    boxes: list[tuple[int | None, str | None, Cell | None]]

    def matched(self, g: int) -> list[str | None]:
        """The gates of the boxes matched to ``g`` on this frame (None = passed)."""
        return [gt for gg, gt, _c in self.boxes if gg == g]


def observe(frames: Sequence[tuple[int, list[list[Any]]]], fld: ss.Field, scr: Screen,
            lag_s: float = LAG_S, match: int = MATCH_CELLS) -> list[FrameObs]:  # fmt: skip
    """Every frame's boxes joined to the packets' mobs (any species): the box's picked cell, the
    nearest alive mob within ``match`` cells at the lagged time (``FrameObs``)."""
    lives = sorted((a, b, g) for g, ls in fld.lives.items() for a, b, _r in ls)
    out: list[FrameObs] = []
    li = 0
    active: list[tuple[int | None, int]] = []
    for t, boxes in sorted(frames, key=lambda f: f[0]):
        tl = int(t - lag_s * NS)
        while li < len(lives) and lives[li][0] <= tl:
            active.append((lives[li][1], lives[li][2]))
            li += 1
        active = [(b, g) for b, g in active if b is None or tl < b]
        gm = fld.gm(tl)
        obs = FrameObs(t, gm, [])
        if gm is None or not boxes:
            out.append(obs)
            continue
        pts = np.array([[(float(b[0]) + float(b[2])) / 2, float(b[3]) - 4.0] for b in boxes])
        offs = scr.pick(gm, pts)
        mobs = [(g, c) for _b, g in active if g != fj.GM and (c := fld.mob(g, tl)) is not None]
        for b, o in zip(boxes, offs, strict=True):
            if int(o[0]) < -1000 or int(o[1]) < -1000:
                obs.boxes.append((None, None, None))
                continue
            c = (gm[0] + int(o[0]), gm[1] + int(o[1]))
            near = min(((fj.cheb(c, m), g) for g, m in mobs), default=None)
            gid = near[1] if near is not None and near[0] <= match else None
            obs.boxes.append((gid, gate_of(b, c, scr.scale((int(o[0]), int(o[1]))), scr), c))
        out.append(obs)
    return out


def on_screen(fld: ss.Field, scr: Screen, g: int, t: int, lag_s: float = LAG_S) -> bool:
    tl = int(t - lag_s * NS)
    gm, m = fld.gm(tl), fld.mob(g, tl)
    return gm is not None and m is not None and (m[0] - gm[0], m[1] - gm[1]) in scr.offsets


# --- the bot's state ------------------------------------------------------------------------------


@dataclass
class BotState:
    """Engaged phases [(t0, t1, phase, gid)], pursuit segments [(t0, t1, tid, end)], the strike
    clicks (t, tid), the drops / give-ups (t, tid), track -> gid."""

    phases: list[tuple[int, int, str, int | None]] = field(default_factory=list)
    pursuit: list[tuple[int, int, int, str]] = field(default_factory=list)
    strikes: list[tuple[int, int]] = field(default_factory=list)
    drops: list[tuple[int, int | None]] = field(default_factory=list)
    gid_of: dict[int, int] = field(default_factory=dict)
    productive: set[tuple[int, int]] = field(default_factory=set)  # (gid, segment start)
    ghosts: set[int] = field(default_factory=set)  # tracks on boxes of no mob (join_by_frames)
    _pt: list[int] = field(default_factory=list)
    _st: list[int] = field(default_factory=list)

    def phase_at(self, t: int, not_gid: int | None = None) -> str | None:
        """The engaged phase at ``t`` (None: not engaged, or engaged with ``not_gid`` itself)."""
        i = bisect.bisect_right(self._pt, t) - 1
        if i >= 0 and self.phases[i][0] <= t < self.phases[i][1]:
            if not_gid is not None and self.phases[i][3] == not_gid:
                return None
            return self.phases[i][2]
        return None

    def busy_other(self, t: int, g: int) -> bool:
        """Converting ANOTHER mob at ``t``: engaged with it, or pursuing a track whose gid we
        attacked by the pursuit's end + 2 s (a productive pursuit)."""
        if self.phase_at(t, g) is not None:
            return True
        s = self.pursuit_at(t)
        if s is None:
            return False
        og = self.gid_of.get(s[2])
        return og is not None and og != g and (og, s[0]) in self.productive

    def pursuit_at(self, t: int) -> tuple[int, int, int, str] | None:
        if len(self._st) != len(self.pursuit):
            self._st = [s[0] for s in self.pursuit]
        i = bisect.bisect_right(self._st, t) - 1
        return self.pursuit[i] if i >= 0 and t < self.pursuit[i][1] else None


# the target set: dispatch is logged ONCE per (track, valid), so a re-dispatch of the same track is
# seen only through the steps that name the current target (zone_plan, strike_call)
SET_KINDS = {"dispatch": "track", "preempt": "to", "retarget": "to", "target_reacquired": "as",
             "looter_engage": "track", "zone_plan": "track", "strike_call": "track"}  # fmt: skip
END_KINDS = ("target_lost", "target_dropped", "hand_off")


def pursuit_segments(bot_events: Sequence[Mapping[str, Any]], t_last: int
                     ) -> list[tuple[int, int, int, str]]:  # fmt: skip
    """PURE: the executor's ``target`` over time, from the events: (t0, t1, tid, how it ended)."""
    segs: list[tuple[int, int, int, str]] = []
    cur: tuple[int, int] | None = None
    for e in sorted(bot_events, key=lambda x: int(x["t_ns"])):
        k, t = e.get("kind"), int(e["t_ns"])
        if k in SET_KINDS and (k != "dispatch" or e.get("valid")):
            tid = e.get(SET_KINDS[k])
            if tid is None:
                continue
            if cur is not None and cur[1] != int(tid):
                end = {"preempt": "preempt_away", "retarget": "retarget_away",
                       "target_reacquired": "reacquired"}.get(str(k), "replaced")  # fmt: skip
                segs.append((cur[0], t, cur[1], end))
            if cur is None or cur[1] != int(tid):
                cur = (t, int(tid))
        elif k in END_KINDS and cur is not None:
            end = "dropped:" + str(e.get("why")) if k == "target_dropped" else str(k)
            if k == "hand_off":
                end = "hand_off:" + str(e.get("after"))
            segs.append((cur[0], t, cur[1], end))
            cur = None
    if cur is not None:
        segs.append((cur[0], t_last, cur[1], "open"))
    return segs


def join_tracks(bot_events: Sequence[Mapping[str, Any]], clicks: Sequence[Mapping[str, Any]],
                fld: ss.Field, lag_s: float = LAG_S, cells: int = JOIN_DISPATCH_CELLS,
                click_s: float = JOIN_CLICK_S) -> dict[int, int]:  # fmt: skip
    """track -> gid by majority vote: (a) every attack request whose last click before it (<=
    ``click_s``) was a strike on a track; (b) every dispatch's logged cell vs the alive TARGETS'
    lagged cells (the nearest within ``cells`` and JOIN_UNIQUE nearer than the next); then
    target_reacquired hands a gid on."""
    votes: dict[int, Counter[int]] = defaultdict(Counter)
    cs = sorted((int(c["t"]), c) for c in clicks)
    ct = [c[0] for c in cs]
    for e in fld.events:
        if e.get("type") != "attack_request":
            continue
        t = int(e["t_mono_ns"])
        i = bisect.bisect_right(ct, t) - 1
        if i < 0 or t - ct[i] > click_s * NS:
            continue
        c = cs[i][1]
        if c.get("kind") in ("strike", "strike_burst") and c.get("track") is not None:
            votes[int(c["track"])][fj.gid_of(e, "target_gid")] += 3  # a request outweighs a cell
    cells_logged = [
        (int(e["t_ns"]), int(e["track"]), e["cell"])
        for e in bot_events
        if e.get("kind") == "dispatch" and e.get("cell") is not None
    ]
    cells_logged += [(int(c["t"]), int(c["track"]), c["pred_cell"]) for c in clicks
                     if c.get("kind") == "strike" and c.get("track") is not None
                     and c.get("pred_cell") is not None]  # fmt: skip
    for t_e, tid, cell in cells_logged:
        tl = int(t_e - lag_s * NS)
        cx, cy = float(cell[0]), float(cell[1])
        ds = sorted((max(abs(m[0] - cx), abs(m[1] - cy)), g) for g, m in fld.targets_at(tl))
        if ds and ds[0][0] <= cells and (len(ds) < 2 or ds[1][0] - ds[0][0] >= JOIN_UNIQUE):
            votes[tid][ds[0][1]] += 1
    out = {tid: v.most_common(1)[0][0] for tid, v in votes.items()}
    for e in sorted(bot_events, key=lambda x: int(x["t_ns"])):
        if e.get("kind") == "target_reacquired":
            a, b = int(e["track"]), int(e["as"])
            if a in out and b not in out:
                out[b] = out[a]
    return out


def join_by_frames(st: BotState, obs: Sequence[FrameObs], share: float = 0.7) -> None:
    """(c), for the tracks (a) and (b) leave unjoined: over the frames of their pursuit segments,
    the gate-passing boxes' gids (None: a box on no mob). When one gid holds >= ``share`` of
    those frames the track joins it; when "no mob" does, the track is a GHOST (``st.ghosts``)."""
    ot = [o.t for o in obs]
    per: dict[int, Counter[int | None]] = defaultdict(Counter)
    for s0, s1, tid, _end in st.pursuit:
        if tid in st.gid_of:
            continue
        for o in obs[bisect.bisect_left(ot, s0) : bisect.bisect_left(ot, s1)]:
            got = {gg for gg, gt, _c in o.boxes if gt is None}
            for gg in got:
                per[tid][gg] += 1
    for tid, cn in per.items():
        n = sum(cn.values())
        top, k = cn.most_common(1)[0]
        if n and k / n >= share:
            if top is None:
                st.ghosts.add(tid)
            else:
                st.gid_of[tid] = top


def bot_state(bot_events: Sequence[Mapping[str, Any]], engagements: Sequence[Mapping[str, Any]],
              clicks: Sequence[Mapping[str, Any]], fld: ss.Field, t_last: int,
              obs: Sequence[FrameObs] = ()) -> BotState:  # fmt: skip
    """The engaged phases (fight -> the engaged gid's death packet -> dead_wait -> loot), the
    pursuit segments, the strikes and drops, and the track -> gid join (``join_tracks``, then
    ``join_by_frames`` when the frames are given)."""
    st = BotState()
    st.gid_of = join_tracks(bot_events, clicks, fld)
    deaths: dict[int, list[int]] = defaultdict(list)
    for e in fld.events:
        if e.get("type") == "entity_vanish" and int(e.get("reason", -1)) == 1:
            deaths[fj.gid_of(e)].append(int(e["t_mono_ns"]))
    for eg in engagements:
        t_a, t_b = eg.get("t_first_click"), eg.get("t_end")
        if not t_a or not t_b:
            continue
        t_a, t_b = int(t_a), int(t_b)
        g = st.gid_of.get(int(eg.get("track", -1)))
        loot_s = float((eg.get("loot") or {}).get("s") or 0.0)
        t_loot = max(t_a, int(t_b - loot_s * NS))
        t_kill = next((d for d in deaths.get(g, []) if t_a <= d <= t_b), None) if g else None
        t_fight_end = t_loot if t_kill is None else min(t_kill, t_loot)
        st.phases.append((t_a, t_fight_end, "fight", g))
        if t_fight_end < t_loot:
            st.phases.append((t_fight_end, t_loot, "dead_wait", g))
        if t_loot < t_b:
            st.phases.append((t_loot, t_b, "loot", g))
    st.phases.sort()
    st._pt = [p[0] for p in st.phases]
    st.pursuit = pursuit_segments(bot_events, t_last)
    if obs:
        join_by_frames(st, obs)
    st.strikes = sorted((int(c["t"]), int(c["track"])) for c in clicks
                        if c.get("kind") in ("strike", "strike_burst")
                        and c.get("track") is not None)  # fmt: skip
    for e in bot_events:
        if e.get("kind") == "target_dropped":
            st.drops.append((int(e["t_ns"]), e.get("track")))
    for eg in engagements:
        if eg.get("result") == "gave_up" and eg.get("t_end"):
            st.drops.append((int(eg["t_end"]), eg.get("track")))
    st.drops.sort()
    atk = sorted((int(e["t_mono_ns"]), fj.gid_of(e, "target_gid")) for e in fld.events
                 if e.get("type") == "attack_request")  # fmt: skip
    at_ = [x[0] for x in atk]
    for s0, s1, tid, _end in st.pursuit:
        og = st.gid_of.get(tid)
        if og is None:
            continue
        for k in range(bisect.bisect_left(at_, s0), bisect.bisect_right(at_, s1 + 2 * NS)):
            if atk[k][1] == og:
                st.productive.add((og, s0))
                break
    return st


def pursuit_summary(st: BotState, fld: ss.Field, kills: int, t0: int, w1: int) -> dict[str, Any]:
    """The bot's pursuit (steering) seconds per kill by what the track joins to: a target that
    was then attacked (productive), a target not attacked, a non-target, no gid (a ghost or a
    tracker split no logged cell joins)."""
    acc: Counter[str] = Counter()
    for s0, s1, tid, _end in st.pursuit:
        a, b = max(s0, t0), min(s1, w1)
        if b <= a:
            continue
        og = st.gid_of.get(tid)
        if og is None:
            k = "ghost" if tid in st.ghosts else "unjoined"
        elif fld.job.get(og) not in TARGETS:
            k = "nontarget"
        else:
            k = "target_attacked" if (og, s0) in st.productive else "target_not_attacked"
        acc[k] += (b - a) / NS
    return {k: {"s": round(v), "s_per_kill": round(v / kills, 2) if kills else None}
            for k, v in acc.most_common()}  # fmt: skip


# --- the decision list ----------------------------------------------------------------------------


def attention_end(segs: Sequence[tuple[int, int, int, str]], gid_of: Mapping[int, int],
                  g: int, e: int) -> tuple[str, int | None]:  # fmt: skip
    """PURE: how the bot's attention on ``g`` ended before ``e``: the end label of the last
    pursuit segment joined to ``g`` that ended before ``e`` (a switch to another track of the SAME
    gid -- a tracker split -- does not end it), with the gid it went to; ("open", None) when it
    was still on ``g`` at ``e``."""
    mine = [k for k, s in enumerate(segs) if gid_of.get(s[2]) == g and s[0] < e]
    if not mine:
        return "none", None
    k = mine[-1]
    s0, s1, _tid, end = segs[k]
    if s1 >= e:
        return "open", None
    nxt = segs[k + 1] if k + 1 < len(segs) and segs[k + 1][0] - s1 <= int(0.05 * NS) else None
    to = None if nxt is None else gid_of.get(nxt[2])
    return end, to


def classify(row: Mapping[str, Any], fld: ss.Field, scr: Screen, obs: Sequence[FrameObs],
             st: BotState, within_s: float = WITHIN_S, min_free_s: float = MIN_FREE_S,
             lag_s: float = LAG_S, drop_s: float = 2.0) -> dict[str, Any]:  # fmt: skip
    """THE DECISION LIST (module docstring) for one free entry: primary, flags and evidence.
    ``idle_s`` = the in-view seconds in W while the bot was NOT converting another mob
    (``BotState.busy_other``): the time this miss really lost."""
    a, g = int(row["t"]), int(row["gid"])
    e = window_end(row, within_s)
    ot = [o.t for o in obs]
    fr = obs[bisect.bisect_left(ot, a) : bisect.bisect_left(ot, e)]
    dt = [(fr[i + 1].t - fr[i].t) / NS if i + 1 < len(fr) else (e - fr[i].t) / NS
          for i in range(len(fr))]  # fmt: skip
    dt = [min(x, 1.5) for x in dt]  # a frame stands for at most 1.5 s
    lead = (fr[0].t - a) / NS if fr else (e - a) / NS  # before the first frame in W
    on = [on_screen(fld, scr, g, f.t, lag_s) for f in fr]
    ph = [st.phase_at(f.t, g) for f in fr]
    bo = [st.busy_other(f.t, g) for f in fr]
    idle_s = sum(d for d, b in zip(dt, bo, strict=True) if not b)
    if fr and not st.busy_other(a, g):
        idle_s += min(lead, 1.5)
    on_s = sum(d for d, o in zip(dt, on, strict=True) if o)
    free_on = [i for i in range(len(fr)) if on[i] and ph[i] is None]
    free_s = sum(dt[i] for i in free_on)
    gates = [fr[i].matched(g) for i in range(len(fr))]
    det_any = any(gates[i] for i in range(len(fr)) if on[i])
    det_free = [i for i in free_on if gates[i]]
    pass_free = [i for i in free_on if any(x is None for x in gates[i])]
    tids = {tid for tid, gg in st.gid_of.items() if gg == g}
    segs = [s for s in st.pursuit if s[2] in tids and s[0] < e and s[1] > a]
    strikes = [s for s in st.strikes if a <= s[0] < e and s[1] in tids]
    first_det = next((fr[i].t for i in range(len(fr)) if on[i] and gates[i]), None)
    first_pass = next((fr[i].t for i in pass_free), None)
    flags: list[str] = []
    if row["life_end"] is not None and int(row["life_end"]) < a + within_s * NS:
        flags.append("left_view" if row["reason"] == 0 else f"life_end_{row['reason']}")
    if any(p is not None for p in ph):
        flags.append("busy_some")
    if any(bo):
        flags.append("converting_other")
    if det_any and not det_free:
        flags.append("detected_only_busy")
    if any(0 <= a - td <= BAN_S * NS for td, _tid in st.drops):
        flags.append("drop_15s_before")
    cause: str
    if not any(on):
        cause = "off_screen"
    elif free_s < min_free_s:
        busy_t: Counter[str] = Counter()
        for i in range(len(fr)):
            if on[i] and ph[i] is not None:
                busy_t[str(ph[i])] += dt[i]
        cause = "busy:" + (busy_t.most_common(1)[0][0] if busy_t else "fight")
    elif not det_free:
        cause = "undetected"
    elif not pass_free:
        gc: Counter[str] = Counter()
        for i in det_free:
            gc.update(str(x) for x in gates[i])
        cause = "gated:" + gc.most_common(1)[0][0]
    elif not segs and not strikes:
        doing: Counter[str] = Counter()
        for i in pass_free:
            s = st.pursuit_at(fr[i].t)
            if s is None:
                doing["none"] += 1
                continue
            og = st.gid_of.get(s[2])
            if og is None:
                doing["pursuing_ghost" if s[2] in st.ghosts else "pursuing_unjoined"] += 1
            elif fld.job.get(og) in TARGETS:
                doing["pursuing_target"] += 1
            else:
                doing["pursuing_nontarget"] += 1
        cause = "never_attended:" + doing.most_common(1)[0][0]
    else:
        atk_g = [int(x["t_mono_ns"]) for x in fld.events if x.get("type") == "attack_request"
                 and fj.gid_of(x, "target_gid") == g and int(x["t_mono_ns"]) >= a]  # fmt: skip
        end, to = attention_end(st.pursuit, st.gid_of, g, e)
        if strikes:
            ts = strikes[-1][0]
            landed = any(ts <= x <= ts + JOIN_CLICK_S * NS for x in atk_g)
            end = "struck_at_end" if landed else "strike_no_request"
        elif end == "target_lost":
            t_l = next(s[1] for s in reversed(segs) if s[3] == "target_lost")
            near = [i for i in range(len(fr)) if t_l - drop_s * NS <= fr[i].t <= t_l]
            if near and not on[near[-1]]:
                end = "target_lost:offscreen"
            elif near and not any(gates[i] for i in near if on[i]):
                end = "target_lost:undetected"
            else:
                end = "target_lost:other"
        elif end in ("retarget_away", "preempt_away", "replaced"):
            nxt_tid = next((s[2] for s in st.pursuit if s[0] >= segs[-1][1]), None)
            kind = (("ghost" if nxt_tid in st.ghosts else "unjoined") if to is None
                    else "target" if fld.job.get(to) in TARGETS else "nontarget")  # fmt: skip
            end = f"{end}:{kind}"
        elif end == "open" and row["life_end"] is not None and int(row["life_end"]) <= e:
            end = "gone"
        elif end == "open":
            end = "steering"
        cause = "attended:" + end
    out = {"t": a, "gid": g, "job": row["job"], "dist": row["dist"], "cause": cause,
           "flags": flags, "inview_s": round((e - a) / NS, 2), "idle_s": round(idle_s, 2),
           "on_s": round(on_s, 2), "free_on_s": round(free_s, 2),
           "first_det_s": None if first_det is None else round((first_det - a) / NS, 2),
           "first_pass_s": None if first_pass is None else round((first_pass - a) / NS, 2),
           "first_pursuit_s": round((segs[0][0] - a) / NS, 2) if segs else None,
           "pursued": bool(segs), "latk_any": row["latk_any"]}  # fmt: skip
    if row["latk_any"] is not None:
        out["delay"] = cause
        out["cause"] = "attacked_late"
        out["late_s"] = round(float(row["latk_any"]) - within_s, 2)
    return out


def cause_table(rows: Sequence[Mapping[str, Any]], kills: int, n_free: int,
                key: str = "cause") -> dict[str, Any]:  # fmt: skip
    """Per cause: n, share of the not-attacked, share of all free entries, in-view s per kill."""
    by: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for r in rows:
        by[str(r[key])].append(r)
    tot = len(rows)
    out = {}
    for c, rs in sorted(
        by.items(), key=lambda kv: -sum(x.get("idle_s", x["inview_s"]) for x in kv[1])
    ):
        s = sum(float(x["inview_s"]) for x in rs)
        idle = sum(float(x.get("idle_s", x["inview_s"])) for x in rs)
        out[c] = {"n": len(rs), "share_missed": round(len(rs) / tot, 3) if tot else None,
                  "share_free": round(len(rs) / n_free, 3) if n_free else None,
                  "inview_s": round(s, 1),
                  "s_per_kill": round(s / kills, 2) if kills else None,
                  "idle_s_per_kill": round(idle / kills, 2) if kills else None}  # fmt: skip
    return out


def classify_packets(row: Mapping[str, Any], fld: ss.Field, scr: Screen,
                     frame_t: Sequence[int], within_s: float = WITHIN_S) -> str:  # fmt: skip
    """The PACKET-ONLY list (Batt and the bot alike): off_screen (on no detector frame's lagged
    view), busy_attack, busy_loot, left_view, ignored."""
    a, g = int(row["t"]), int(row["gid"])
    e = window_end(row, within_s)
    ts = frame_t[bisect.bisect_left(frame_t, a) : bisect.bisect_left(frame_t, e)]
    if not ts:
        ts = list(range(a, e, int(0.3 * NS)))
    if not any(on_screen(fld, scr, g, t) for t in ts):
        return "off_screen"
    evt = getattr(fld, "_evt", None)
    if evt is None:
        evt = [int(x["t_mono_ns"]) for x in fld.events]
        fld._evt = evt  # type: ignore[attr-defined]
    win = fld.events[bisect.bisect_left(evt, a) : bisect.bisect_left(evt, e)]
    if any(x.get("type") == "attack_request" and fj.gid_of(x, "target_gid") != g for x in win):
        return "busy_attack"
    if any(x.get("type") == "pickup_request" for x in win):
        return "busy_loot"
    if row["life_end"] is not None and int(row["life_end"]) <= e and row["reason"] == 0:
        return "left_view"
    return "ignored"


# --- in range -> click ----------------------------------------------------------------------------


def hover_cause(hovers: Sequence[Mapping[str, Any]]) -> tuple[str, Mapping[str, Any]] | None:
    """PURE: the first CLICKED hover of an engagement and the cause of its in range -> click."""
    first = next((i for i, h in enumerate(hovers) if h.get("clicked")), None)
    if first is None:
        return None
    h = hovers[first]
    prior = [x for x in hovers[:first] if not x.get("clicked")]
    if prior:
        return f"reread:{prior[0].get('read')}", h
    if h.get("path") == "std" or h.get("read") not in (None, "direct"):
        return f"risk_read:{h.get('read')}", h
    if h.get("fallback"):
        return f"fallback:{h['fallback']}", h
    if h.get("arm_eff") == "C":
        return "arm_C", h
    return f"arm_{h.get('arm_eff')}", h


def in_range_table(engagements: Sequence[Mapping[str, Any]],
                   bot_events: Sequence[Mapping[str, Any]],
                   kills: int) -> dict[str, Any]:  # fmt: skip
    """The in range -> click distribution by cause (``hover_cause``), each cause's excess over the
    arm_C p50 per kill; the strike calls' risk reads, re-click hovers, burst ends, tag refusals."""
    by: dict[str, list[float]] = defaultdict(list)
    for eg in engagements:
        hc_ = hover_cause(eg.get("hovers") or [])
        if hc_ is None or hc_[1].get("in_range_to_click_s") is None:
            continue
        by[hc_[0]].append(float(hc_[1]["in_range_to_click_s"]))
    allv = [v for vs in by.values() for v in vs]
    base = fj.pct(by.get("arm_C", []), 0.5) or 0.0
    out: dict[str, Any] = {
        "n": len(allv), "p50": fj.pct(allv, 0.5), "p90": fj.pct(allv, 0.9),
        "mean": round(float(np.mean(allv)), 2) if allv else None,
        "s_per_kill_total": round(sum(allv) / kills, 2) if kills else None,
        "arm_C_p50_baseline": base, "causes": {},
    }  # fmt: skip
    for c, vs in sorted(by.items(), key=lambda kv: -sum(kv[1])):
        exc = sum(max(0.0, v - base) for v in vs)
        out["causes"][c] = {
            "n": len(vs),
            "p50": fj.pct(vs, 0.5),
            "p90": fj.pct(vs, 0.9),
            "sum_s": round(sum(vs), 1),
            "excess_s_per_kill": round(exc / kills, 3) if kills else None,
        }
    risk: Counter[str] = Counter()
    for e in bot_events:
        if e.get("kind") == "strike_call" and e.get("risk"):
            risk["+".join(e["risk"])] += 1
    nh = sum(len(eg.get("hovers") or []) for eg in engagements)
    unclicked = sum(1 for eg in engagements for h in eg.get("hovers") or [] if not h.get("clicked"))
    burst = Counter(str(e.get("end")) for e in bot_events if e.get("kind") == "burst")
    tag_ms = [float(e.get("ms") or 0) for e in bot_events if e.get("kind") == "tag_refused"]
    out.update({"strike_call_risk": dict(risk.most_common()), "hovers": nh,
                "hovers_unclicked": unclicked, "burst_end": dict(burst),
                "tag_refused": {"n": len(tag_ms),
                                "s_per_kill": round(sum(tag_ms) / 1000 / kills, 3)
                                if kills else None}})  # fmt: skip
    return out


# --- the strike on a walking target ---------------------------------------------------------------


def strike_landing(clicks: Sequence[Mapping[str, Any]], bot_events: Sequence[Mapping[str, Any]],
                   engagements: Sequence[Mapping[str, Any]], fld: ss.Field, st: BotState,
                   t0: int, w1: int, click_s: float = JOIN_CLICK_S) -> dict[str, Any]:  # fmt: skip
    """Did each FIRST strike click (clicks.jsonl kind "strike", not a re-click) send an attack
    request within ``click_s``? By the GM (a strike_moving call <= 0.6 s before: from a walking
    GM) and the mob (its packet cell changed over the 1 s before the click: walking). And FALSE
    DEATHS: an engagement the bot ended "dead" whose joined gid did not die (reason 1) between its
    first click and t_end + 1 s -- with the loot seconds spent on them."""
    atk = sorted(int(e["t_mono_ns"]) for e in fld.events if e.get("type") == "attack_request")
    sm = sorted(int(e["t_ns"]) for e in bot_events if e.get("kind") == "strike_moving")
    n: Counter[str] = Counter()
    for c in clicks:
        t = int(c["t"])
        if c.get("kind") != "strike" or c.get("again") or not (t0 <= t < w1):
            continue
        i = bisect.bisect_left(atk, t)
        req = i < len(atk) and atk[i] - t <= click_s * NS
        j = bisect.bisect_right(sm, t) - 1
        gm = "gm_walking" if j >= 0 and t - sm[j] <= 0.6 * NS else "gm_standing"
        g = st.gid_of.get(int(c["track"])) if c.get("track") is not None else None
        a, b = (fld.mob(g, t - NS), fld.mob(g, t)) if g is not None else (None, None)
        mob = "mob_?" if a is None or b is None else ("mob_walking" if a != b else "mob_still")
        n[f"{gm}/{mob}"] += 1
        n[f"{gm}/{mob}/landed"] += req
    out: dict[str, Any] = {k: {"n": v, "landed": n[k + "/landed"],
                               "share": round(n[k + "/landed"] / v, 2)}
                           for k, v in sorted(n.items()) if not k.endswith("/landed")}  # fmt: skip
    deaths: dict[int, list[int]] = defaultdict(list)
    for e in fld.events:
        if e.get("type") == "entity_vanish" and int(e.get("reason", -1)) == 1:
            deaths[fj.gid_of(e)].append(int(e["t_mono_ns"]))
    true_ = false_ = 0
    loot_s = 0.0
    for eg in engagements:
        if eg.get("result") != "dead" or not eg.get("t_first_click") or not eg.get("t_end"):
            continue
        g = st.gid_of.get(int(eg.get("track", -1)))
        if g is None:
            continue
        a_, b_ = int(eg["t_first_click"]), int(eg["t_end"]) + NS
        if any(a_ <= x <= b_ for x in deaths.get(g, [])):
            true_ += 1
        else:
            false_ += 1
            loot_s += float((eg.get("loot") or {}).get("s") or 0.0)
    out["dead_calls"] = {"true": true_, "false": false_,
                         "false_share": round(false_ / max(1, true_ + false_), 3),
                         "false_loot_s": round(loot_s, 1)}  # fmt: skip
    return out


def approach_profile(rows: Sequence[Mapping[str, Any]], fld: ss.Field,
                     at_s: Sequence[float] = (0.0, 3.0, 6.0, 9.9)) -> dict[str, Any]:  # fmt: skip
    """Per cause (``cause`` / ``attacked_late`` -> "late/<delay>"; an attacked row has cause
    "attacked<=10s"): the GM -> target distance (packets, Chebyshev) p50 at ``at_s`` after the
    entry, and the cells the target walked in its first 10 s (p50 / p90): is it a WALKER?"""
    by: dict[str, list[tuple[list[int | None], int]]] = defaultdict(list)
    for r in rows:
        t, g = int(r["t"]), int(r["gid"])
        k = str(r["cause"]) if r["cause"] != "attacked_late" else f"late/{r['delay']}"
        ds: list[int | None] = []
        for dt_ in at_s:
            m, h = fld.mob(g, int(t + dt_ * NS)), fld.gm(int(t + dt_ * NS))
            ds.append(fj.cheb(m, h) if m and h else None)
        moved, prev = 0, None
        for tt in range(t, int(t + WITHIN_S * NS), int(0.5 * NS)):
            m = fld.mob(g, tt)
            if prev is not None and m is not None:
                moved += fj.cheb(prev, m)
            prev = m
        by[k].append((ds, moved))
    out = {}
    for k, v in sorted(by.items(), key=lambda kv: -len(kv[1])):
        out[k] = {"n": len(v),
                  "dist_p50": [fj.pct([float(x[0][i]) for x in v if x[0][i] is not None], 0.5)
                               for i in range(len(at_s))],
                  "walked_p50_p90": [fj.pct([float(x[1]) for x in v], 0.5),
                                     fj.pct([float(x[1]) for x in v], 0.9)]}  # fmt: skip
    return out


# --- sessions -------------------------------------------------------------------------------------


def load_frames(sid: str, root: Path) -> list[tuple[int, list[list[Any]]]]:
    p = root / sid / "boxes.jsonl"
    if not p.exists():
        return []
    out = []
    for x in p.read_text().splitlines():
        if x:
            r = json.loads(x)
            out.append((int(r["t"]), list(r.get("boxes") or [])))
    return out


def analyse(sess: ss.Session, scr: Screen, root: Path) -> dict[str, Any]:
    fld = ss.Field(sess.events)
    rows = free_entries(fld, sess.t0, sess.w1)
    kills = len(ss.kill_times(sess.events, sess.t0, sess.w1))
    frames = [f for f in load_frames(sess.sid, root)
              if sess.t0 - 2 * NS <= f[0] < sess.w1 + 12 * NS]  # fmt: skip
    ft = [f[0] for f in frames]
    missed = [r for r in rows if r["latk"] is None]
    pk = [{"cause": classify_packets(r, fld, scr, ft), "inview_s": (window_end(r) - r["t"]) / NS}
          for r in missed]  # fmt: skip
    out: dict[str, Any] = {
        "free_n": len(rows),
        "attacked_10s": round(1 - len(missed) / len(rows), 2) if rows else None,
        "kills": kills, "window_s": round((sess.w1 - sess.t0) / NS),
        "missed_n": len(missed), "packet_causes": cause_table(pk, kills, len(rows)),
    }  # fmt: skip
    if not sess.bot:
        out["approach"] = approach_profile(
            [{"t": r["t"], "gid": r["gid"],
              "cause": "attacked<=10s" if r["latk"] is not None else "missed"} for r in rows],
            fld)  # fmt: skip
    if sess.bot:
        d = root / sess.sid
        clicks = [json.loads(x) for x in (d / "clicks.jsonl").read_text().splitlines() if x]
        obs = observe(frames, fld, scr)
        st = bot_state(sess.bot_events, sess.engagements, clicks, fld, sess.w1, obs)
        cl = [classify(r, fld, scr, obs, st) for r in missed]
        out["causes"] = cause_table(cl, kills, len(rows))
        late = [c for c in cl if c["cause"] == "attacked_late"]
        out["attacked_late"] = {
            "n": len(late),
            "late_s_p50": fj.pct([c["late_s"] for c in late], 0.5),
            "delay": dict(Counter(c["delay"] for c in late).most_common()),
        }
        out["flags"] = dict(Counter(f for c in cl for f in c["flags"]).most_common())
        out["in_range"] = in_range_table(sess.engagements, sess.bot_events, kills)
        out["pursuit"] = pursuit_summary(st, fld, kills, sess.t0, sess.w1)
        out["strike_landing"] = strike_landing(clicks, sess.bot_events, sess.engagements, fld, st,
                                               sess.t0, sess.w1)  # fmt: skip
        hit = [{"t": r["t"], "gid": r["gid"], "cause": "attacked<=10s"} for r in rows
               if r["latk"] is not None]  # fmt: skip
        out["approach"] = approach_profile([*cl, *hit], fld)
        out["join"] = {
            "tracks_joined": len(st.gid_of),
            "pursuit_segments": len(st.pursuit),
            "segments_joined": sum(1 for s in st.pursuit if s[2] in st.gid_of),
        }
        out["rows"] = cl
    return out


def pool(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    kills = sum(r["kills"] for r in results)
    n_free = sum(r["free_n"] for r in results)
    rows = [x for r in results for x in r["rows"]]
    out = {"free_n": n_free, "kills": kills, "missed_n": len(rows),
           "attacked_10s": round(1 - len(rows) / n_free, 2) if n_free else None,
           "causes": cause_table(rows, kills, n_free),
           "flags": dict(Counter(f for x in rows for f in x["flags"]).most_common())}  # fmt: skip
    late = [c for c in rows if c["cause"] == "attacked_late"]
    out["attacked_late"] = {
        "n": len(late),
        "late_s_p50": fj.pct([c["late_s"] for c in late], 0.5),
        "delay": dict(Counter(c["delay"] for c in late).most_common()),
    }
    sl: dict[str, Counter[str]] = defaultdict(Counter)
    for r in results:
        for k, v in r.get("strike_landing", {}).items():
            for kk, vv in v.items():
                if kk not in ("share", "false_share"):
                    sl[k][kk] += vv
    for v in sl.values():
        if "n" in v:
            v["share"] = round(v["landed"] / max(1, v["n"]), 2)  # type: ignore[assignment]
        else:
            v["false_share"] = round(v["false"] / max(1, v["true"] + v["false"]), 3)  # type: ignore[assignment]
    out["strike_landing"] = {k: dict(v) for k, v in sl.items()}
    pk: dict[str, dict[str, float]] = defaultdict(lambda: {"n": 0, "inview_s": 0.0})
    for r in results:
        for c, v in r["packet_causes"].items():
            pk[c]["n"] += v["n"]
            pk[c]["inview_s"] += v["inview_s"]
    out["packet_causes"] = {
        c: {
            "n": int(v["n"]),
            "share_missed": round(v["n"] / len(rows), 3),
            "s_per_kill": round(v["inview_s"] / kills, 2),
        }
        for c, v in sorted(pk.items(), key=lambda kv: -kv[1]["inview_s"])
    }
    return out


def compare(sids: Sequence[str], root: Path | None = None) -> dict[str, Any]:
    if root is None:
        from poring_env.demo import DEMO_ROOT

        root = DEMO_ROOT
    sessions = [ss.load_session(s, root) for s in sids]
    scr = load_screen(sessions[0].map_name)
    res = {s.sid: analyse(s, scr, root) for s in sessions}
    bots = [res[s.sid] for s in sessions if s.bot]
    out: dict[str, Any] = {"lag_s": LAG_S, "match_cells": MATCH_CELLS, "min_free_s": MIN_FREE_S,
                           "area": scr.area is not None, "sessions": res}  # fmt: skip
    if bots:
        out["BOT_POOLED"] = pool(bots)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compare")
    c.add_argument("sessions", nargs="+")
    c.add_argument("--rows", action="store_true", help="keep every entry's row in the JSON")
    a = ap.parse_args()
    out = compare(a.sessions)
    if not a.rows:
        for v in out["sessions"].values():
            v.pop("rows", None)
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
