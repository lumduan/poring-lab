#!/usr/bin/env python3
"""The SEARCH study (Batt 2026-10-18: "next speed work = SEARCH"): Batt's 10-minute human demo vs
the bot's full-hour hunt-flow runs on the same map, from the PACKETS, OFFLINE. Packets are ground
truth here (ADR-0007) and never a decision input (rule 1): nothing in this module runs during play.
The same functions, with the same ruler, measure Batt and the bot.

    search_study.py compare BATT_SID BOT_SID [BOT_SID ...]   every table below (JSON)
    search_study.py kps SID [SID ...]                         kills per sighting only

What it measures (pure functions, tested in services/backend/tests/test_search_study.py):
- KILLS PER SIGHTING = kills / h / monsters seen per 10 min (``flow_judge.sight_windowed``: the
  median of back-to-back 10-min windows, so a 60-min run and a 10-min demo share the ruler).
  Batt 300 / 44 = 6.82. The standard column from now on (``kills_per_sighting``).
- the PATH: cells walked / min, straight runs (cells between turns > 45 deg), reversals (> 120 deg)
  / min, the 20 x 20-cell blocks entered and re-entered per 10 min;
- the VIEW SWEEP (``scan``): every 0.25 s, the cells newly inside the server's view (Chebyshev 14
  of the GM: rAthena's AREA_SIZE) and how long ago each was last inside it -- re-swept within
  5 / 30 / 120 s, fresh ground (not in view for 120 s) / min, new cells per cell walked;
- PRESENCE: the time with NO alive target within 14 cells (the search) vs some (the conversion),
  per kill, and the no-target stretches;
- YIELD BY AGE: target view entries per 1000 newly-viewed walkable cells, by the time since those
  cells were last in view (the hunter's own depletion of the ground it covers);
- TURNING toward a target that enters the view (the first walk command within 45 deg of it, or an
  attack on it), Batt vs bot;
- ENGAGEMENT ENDS: was any alive target within 14 cells; for the "none" ends the wait for the next
  one, a REMEMBERED target (left the view <= 120 s before, not seen since) within 15-25 cells, the
  search heading taken next, the side the next target came from;
- the map-wide DENSITY per block (target entries per 1000 fresh cells, the given sessions pooled)
  and the density of the ground each session chose;
- HEADING REGRET: at each of the bot's search re-plans, its chosen heading vs the best of the 8
  compass headings, both scored by ``band_score`` (the proposal: the expected yield of the ground a
  heading brings into view, by its age, per walking second).
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

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import flow_judge as fj  # noqa: E402
import hunt_core as hc  # noqa: E402

NS = 10**9
GM = fj.GM
VIEW = 14  # rAthena's AREA_SIZE: the server sends a unit within 14 cells (Chebyshev) of the GM
TARGETS = (1002, 1063, 1008, 1113)  # Poring, Lunatic, Pupa, Drops (Creamy 1018 is not one)
MS_CELL = fj.GM_MS_CELL  # 150 ms a straight step; a diagonal one takes 1.4x (rAthena)
DT_S = 0.25  # the scan's sample period
RESWEEP_S = (5.0, 30.0, 120.0)  # re-swept = newly in view again within this long
FRESH_S = 120.0  # fresh ground = not in view for this long
AGE_EDGES_S = (30.0, 120.0, 300.0, 600.0, 1200.0)
AGE_NAMES = ("<=30s", "30s-2min", "2-5min", "5-10min", "10-20min", ">20min", "never")
# The proposal's yield of ground by the time since it was last in view, relative to ground never in
# view in the run: the pooled yield-by-age table of hunt-flow32..36 (6 h, prt_fild08): entries per
# 1000 cells 0.40 / 0.40 / 0.47 at 30 s-10 min, 0.63 at 10-20 min, 1.02 beyond, 1.25 never
AGE_REL = ((600.0, 0.32), (1200.0, 0.5), (math.inf, 0.82))
NEVER_REL = 1.0
# rel_yield per AGE_NAMES class (its edges 600 / 1200 s are AGE_REL's)
CLASS_REL = (0.32, 0.32, 0.32, 0.32, 0.5, 0.82, 1.0)
NEVER = -math.inf
Cell = tuple[int, int]


# --- kills per sighting ---------------------------------------------------------------------------


def kills_per_sighting(kills_per_hour: float, sight_per_10min: float) -> float | None:
    """THE standard column (Batt 2026-10-18): kills / h per monster seen per 10 min (windowed).
    Batt's demo: 300.0 / 44.0 = 6.82."""
    if not sight_per_10min:
        return None
    return round(kills_per_hour / sight_per_10min, 2)


def kill_times(events: Sequence[Mapping[str, Any]], t0: int, w1: int) -> list[int]:
    """Our kills in [t0, w1) by flow_judge's rule: a mob we acted on (any act of our GM in the
    window, not a pickup) vanished with reason 1 (died)."""
    acted = {fj.gid_of(e, "target_gid") for e in events if e.get("type") == "act"
             and fj.gid_of(e, "src_gid") == GM and e.get("kind") != "pickup"
             and t0 <= int(e["t_mono_ns"]) < w1}  # fmt: skip
    return [int(e["t_mono_ns"]) for e in events if e.get("type") == "entity_vanish"
            and int(e.get("reason", -1)) == 1 and fj.gid_of(e) in acted
            and t0 <= int(e["t_mono_ns"]) < w1]  # fmt: skip


def conversion(events: Sequence[Mapping[str, Any]], t0: int, w1: int,
               win_s: float = 600.0) -> dict[str, Any]:  # fmt: skip
    """Kills, kills / h, monsters in sight / 10 min (windowed, and over the whole window) and kills
    per sighting, plus each back-to-back ``win_s`` window's own figures."""
    secs = (w1 - t0) / NS
    kills = len(kill_times(events, t0, w1))
    kph = round(kills * 3600 / max(1e-9, secs), 1)
    sight = fj.sight_windowed(events, t0, w1, win_s)
    wins = []
    for k in range(int(secs // win_s)):
        a, b = t0 + int(k * win_s * NS), t0 + int((k + 1) * win_s * NS)
        kw = len(kill_times(events, a, b)) * 3600 / win_s
        sw = fj.sight_per_10min(events, a, b)
        wins.append({"kills_per_hour": round(kw, 1), "sight_per_10min": sw,
                     "kills_per_sighting": kills_per_sighting(kw, sw)})  # fmt: skip
    return {"window_s": round(secs, 1), "kills": kills, "kills_per_hour": kph,
            "sight_per_10min": sight, "sight_whole_window": fj.sight_per_10min(events, t0, w1),
            "kills_per_sighting": kills_per_sighting(kph, sight), "windows": wins}  # fmt: skip


# --- the field: our GM and the mobs, from the packets ---------------------------------------------


class Field:
    """Our GM's cell timeline (``flow_judge.gm_track``: a step per cell, diagonals x1.4), each mob's
    cell along its walk (``hunt_core.walk_positions``) and its lives (``flow_judge.alive``: a
    respawn reuses the block id)."""

    def __init__(self, events: Sequence[Mapping[str, Any]],
                 targets: Iterable[int] = TARGETS) -> None:  # fmt: skip
        events = sorted(events, key=lambda e: int(e["t_mono_ns"]))
        self.events = events
        self.track, self.moving = fj.gm_track(events)
        self._tt = [p[0] for p in self.track]
        self._ms = [a for a, _b in self.moving]
        self.pos = hc.walk_positions(events)
        self._pt = {g: [q[0] for q in v] for g, v in self.pos.items()}
        self.lives = fj.alive(events)
        self.job: dict[int, int] = {}
        for e in events:
            if e.get("type") == "entity_appear" and e.get("objtype") == 5:
                self.job[int(e["gid"])] = int(e.get("job", -1))
        self.targets = set(targets)
        # every target life (start, end or None, gid, vanish reason), by start
        self.tlives = sorted((a, b, g, r) for g, ls in self.lives.items()
                             if self.job.get(g) in self.targets for a, b, r in ls)  # fmt: skip

    def gm(self, t: int) -> Cell | None:
        i = bisect.bisect_right(self._tt, t) - 1
        return self.track[i][1] if i >= 0 else None

    def mob(self, g: int, t: int) -> Cell | None:
        i = bisect.bisect_right(self._pt.get(g, []), t) - 1
        return self.pos[g][i][1] if i >= 0 else None

    def is_moving(self, t: int) -> bool:
        i = bisect.bisect_right(self._ms, t) - 1
        return i >= 0 and self.moving[i][0] <= t < self.moving[i][1]

    def targets_at(self, t: int) -> list[tuple[int, Cell]]:
        """Alive targets (a life holds ``t``) and their cells."""
        out = []
        for a, b, g, _r in self.tlives:
            if a > t:
                break
            if b is None or t < b:
                c = self.mob(g, t)
                if c is not None:
                    out.append((g, c))
        return out

    def entries(self, t0: int, w1: int) -> list[tuple[int, int]]:
        """(t, gid) of every target VIEW ENTRY (a new life: the server sent it into our view) in
        [t0, w1)."""
        return [(a, g) for a, _b, g, _r in self.tlives if t0 <= a < w1]

    def remembered(self, t: int, horizon_s: float = 120.0) -> list[tuple[int, Cell]]:
        """Targets that LEFT the view (vanish reason 0) <= ``horizon_s`` before ``t`` and have not
        come back by ``t``, at their last cell: what a player could remember."""
        out = []
        for g, ls in self.lives.items():
            if self.job.get(g) not in self.targets:
                continue
            past = [(a, b, r) for a, b, r in ls if a <= t]
            if not past:
                continue
            _a, b, r = past[-1]
            if b is not None and b <= t and r == 0 and t - b <= horizon_s * NS:
                c = self.mob(g, b - 1)
                if c is not None:
                    out.append((g, c))
        return out


# --- the view sweep -------------------------------------------------------------------------------


def age_class(age_s: float) -> int:
    """The AGE_NAMES index of ground last in view ``age_s`` ago (inf = never)."""
    if math.isinf(age_s):
        return len(AGE_NAMES) - 1
    return bisect.bisect_left(AGE_EDGES_S, age_s)


@dataclass
class Scan:
    """Per sample (every ``dt_s``): the GM's cell, moving, the alive targets within ``r``, the
    cells newly in view and how many of them were re-swept within RESWEEP_S; plus the newly-viewed
    cells and the target entries by AGE class, and per ``block`` the fresh cells and the entries
    on fresh ground."""

    t: Any
    x: Any
    y: Any
    moving: Any
    n_targets: Any
    new: Any
    reswept: Any  # (n, len(RESWEEP_S))
    age_cells: Any = field(default_factory=lambda: np.zeros(len(AGE_NAMES)))
    age_entries: Any = field(default_factory=lambda: np.zeros(len(AGE_NAMES)))
    block_fresh: dict[Cell, int] = field(default_factory=dict)
    block_entries: dict[Cell, int] = field(default_factory=dict)
    dt_s: float = DT_S
    kills: int = 0

    @property
    def secs(self) -> float:
        return len(self.t) * self.dt_s

    @property
    def fresh(self) -> Any:
        """Newly in view and not in view in the FRESH_S before."""
        return self.new - self.reswept[:, RESWEEP_S.index(FRESH_S)]


def scan(fld: Field, t0: int, w1: int, walkable: Any = None, dt_s: float = DT_S, r: int = VIEW,
         block: int = 40) -> Scan:  # fmt: skip
    """The one pass every summary reads. ``walkable[y, x]`` (bool) masks the cells counted; None
    counts every cell (synthetic tests)."""
    dt = int(dt_s * NS)
    ts = list(range(t0, w1, dt))
    cells = [fld.gm(t) for t in ts]
    keep = [i for i, c in enumerate(cells) if c is not None]
    ts = [ts[i] for i in keep]
    gm_cells: list[Cell] = [c for c in cells if c is not None]
    if walkable is not None:
        wk = np.asarray(walkable, dtype=bool)
    else:
        hi_x = max([c[0] for c in gm_cells] + [0]) + r + 2
        hi_y = max([c[1] for c in gm_cells] + [0]) + r + 2
        wk = np.ones((hi_y, hi_x), dtype=bool)
    h, w = wk.shape
    last = np.full((h, w), NEVER)
    n = len(ts)
    out = Scan(t=np.array(ts, dtype=np.int64), x=np.array([c[0] for c in gm_cells], dtype=int),
               y=np.array([c[1] for c in gm_cells], dtype=int), moving=np.zeros(n, dtype=bool),
               n_targets=np.zeros(n, dtype=int), new=np.zeros(n, dtype=int),
               reswept=np.zeros((n, len(RESWEEP_S)), dtype=int), dt_s=dt_s)  # fmt: skip
    bf = np.zeros((h // block + 1, w // block + 1), dtype=np.int64)
    be = np.zeros_like(bf)
    ents = fld.entries(t0, w1)
    et = [e[0] for e in ents]
    lives = fld.tlives
    li = 0
    active: list[tuple[int | None, int]] = []
    prev_t = t0 - 1
    for k, (t, c) in enumerate(zip(ts, gm_cells, strict=True)):
        while li < len(lives) and lives[li][0] <= t:
            active.append((lives[li][1], lives[li][2]))
            li += 1
        active = [(b, g) for b, g in active if b is None or t < b]
        near = 0
        for _b, g in active:
            m = fld.mob(g, t)
            if m is not None and fj.cheb(m, c) <= r:
                near += 1
        out.n_targets[k] = near
        out.moving[k] = fld.is_moving(t)
        y0, y1 = max(0, c[1] - r), min(h, c[1] + r + 1)
        x0, x1 = max(0, c[0] - r), min(w, c[0] + r + 1)
        sub = last[y0:y1, x0:x1]
        if k == 0:  # the starting view is not walked into: it only seeds the memory
            sub[:] = t
            prev_t = t
            continue
        newm = (sub < t - dt) & wk[y0:y1, x0:x1]
        ages = (t - sub[newm]) / NS  # inf where never
        out.new[k] = int(newm.sum())
        for q, lim in enumerate(RESWEEP_S):
            out.reswept[k, q] = int((ages <= lim).sum())
        cls = np.searchsorted(np.array(AGE_EDGES_S), ages, side="left")
        cls[np.isinf(ages)] = len(AGE_NAMES) - 1
        out.age_cells += np.bincount(cls, minlength=len(AGE_NAMES))
        fy, fx = np.nonzero(newm & (sub < t - FRESH_S * NS))
        np.add.at(bf, ((fy + y0) // block, (fx + x0) // block), 1)
        # the target entries since the last sample, classed by their cell's age BEFORE this update
        for i in range(bisect.bisect_right(et, prev_t), bisect.bisect_right(et, t)):
            ta, g = ents[i]
            m = fld.mob(g, ta)
            if m is None or not (0 <= m[0] < w and 0 <= m[1] < h):
                continue
            seen = last[m[1], m[0]]
            age = math.inf if seen == NEVER else (t - seen) / NS
            out.age_entries[age_class(age)] += 1
            if age > FRESH_S:
                be[m[1] // block, m[0] // block] += 1
        sub[:] = t
        prev_t = t
    for (by, bx), v in np.ndenumerate(bf):
        if v:
            out.block_fresh[(bx, by)] = int(v)
    for (by, bx), v in np.ndenumerate(be):
        if v:
            out.block_entries[(bx, by)] = int(v)
    return out


def merge_scans(scans: Sequence[Scan]) -> Scan:
    """The pooled sums (stretches stay per scan: ``presence_summary`` takes the list)."""
    out = Scan(t=np.concatenate([s.t for s in scans]), x=np.concatenate([s.x for s in scans]),
               y=np.concatenate([s.y for s in scans]),
               moving=np.concatenate([s.moving for s in scans]),
               n_targets=np.concatenate([s.n_targets for s in scans]),
               new=np.concatenate([s.new for s in scans]),
               reswept=np.concatenate([s.reswept for s in scans]), dt_s=scans[0].dt_s,
               kills=sum(s.kills for s in scans))  # fmt: skip
    for s in scans:
        out.age_cells = out.age_cells + s.age_cells
        out.age_entries = out.age_entries + s.age_entries
        for d_in, d_out in ((s.block_fresh, out.block_fresh), (s.block_entries, out.block_entries)):
            for kk, v in d_in.items():
                d_out[kk] = d_out.get(kk, 0) + v
    return out


def _steps(s: Scan) -> tuple[int, int]:
    """(cells walked, diagonal cells) between consecutive samples (Chebyshev)."""
    dx, dy = np.abs(np.diff(s.x)), np.abs(np.diff(s.y))
    cheb = np.maximum(dx, dy)
    diag = np.minimum(dx, dy)
    ok = cheb <= 4  # a jump (a warp, a re-anchor) is not walking
    return int(cheb[ok].sum()), int(diag[ok].sum())


def sweep_summary(s: Scan) -> dict[str, Any]:
    """fresh ground / min = moving s / min x cells / moving s x new cells / cell x fresh share."""
    mins = max(1e-9, s.secs / 60)
    walked, diag = _steps(s)
    mv_s = float(s.moving.sum()) * s.dt_s
    new = int(s.new.sum())
    return {
        "moving_s_per_min": round(mv_s / mins, 1),
        "cells_per_moving_s": round(walked / max(1e-9, mv_s), 2),
        "new_in_view_per_cell": round(new / max(1, walked), 1),
        "diagonal_share": round(diag / max(1, walked), 2),
        "reswept_share": {
            f"<={int(q)}s": round(float(s.reswept[:, i].sum()) / max(1, new), 2)
            for i, q in enumerate(RESWEEP_S)
        },  # fmt: skip
        "fresh_per_min": round(float(s.fresh.sum()) / mins),
        # the proposal's own currency: newly-viewed cells weighted by rel_yield of their age
        "age_weighted_new_per_min": round(float(np.dot(s.age_cells, CLASS_REL)) / mins),
    }


def presence_summary(scans: Sequence[Scan]) -> dict[str, Any]:
    """NO alive target within the view (the search) vs some (the conversion), per kill; the
    no-target stretches (a stretch cut by the window's end still counts)."""
    runs: list[float] = []
    none_n = some_n = moving_none = 0
    fresh_none = 0.0
    kills = 0
    dt_s = scans[0].dt_s if scans else DT_S
    for s in scans:
        z = s.n_targets == 0
        none_n += int(z.sum())
        some_n += int((~z).sum())
        moving_none += int((z & s.moving).sum())
        fresh_none += float(s.fresh[z].sum())
        kills += s.kills
        cur = 0
        for v in z.tolist():
            if v:
                cur += 1
            elif cur:
                runs.append(cur * dt_s)
                cur = 0
        if cur:
            runs.append(cur * dt_s)
    none_s, some_s = none_n * dt_s, some_n * dt_s
    return {
        "none_share": round(none_s / max(1e-9, none_s + some_s), 2),
        "none_s_per_kill": round(none_s / kills, 1) if kills else None,
        "some_s_per_kill": round(some_s / kills, 1) if kills else None,
        "stretches": len(runs),
        "stretches_per_kill": round(len(runs) / kills, 2) if kills else None,
        "stretch_mean_s": round(float(np.mean(runs)), 1) if runs else None,
        "stretch_p50_p90_s": [fj.pct(runs, 0.5), fj.pct(runs, 0.9)],
        "moving_share_in_none": round(moving_none / max(1, none_n), 2),
        "fresh_per_s_in_none": round(fresh_none / max(1e-9, none_s)),
        "stretch_ends_per_1000_fresh": round(1000 * len(runs) / max(1.0, fresh_none), 2),
        # the search's hazard: a target comes into view, per minute without one (stretches cut by
        # the window's end are counted too: a slight over-estimate on short windows)
        "encounters_per_none_min": round(len(runs) / max(1e-9, none_s / 60), 2),
    }


def yield_by_age(s: Scan) -> dict[str, dict[str, float]]:
    """Target view entries per 1000 newly-viewed cells, by how long ago those cells were in view.
    The "<=30s" class is mostly targets walking into a view that stands or turns."""
    return {name: {"cells_k": round(float(s.age_cells[i]) / 1000, 1),
                   "entries": int(s.age_entries[i]),
                   "per_1000": round(1000 * float(s.age_entries[i]) / max(1.0, s.age_cells[i]), 2)}
            for i, name in enumerate(AGE_NAMES)}  # fmt: skip


def block_density(scans: Sequence[Scan], min_cells: int = 2000) -> dict[Cell, float]:
    """Per block (``scan``'s block size): target entries on fresh ground per 1000 fresh cells, the
    given scans pooled; blocks with fewer than ``min_cells`` fresh cells are left out."""
    pool = merge_scans(scans)
    return {k: round(1000 * pool.block_entries.get(k, 0) / v, 2)
            for k, v in pool.block_fresh.items() if v >= min_cells}  # fmt: skip


def ground_density(s: Scan, dens: Mapping[Cell, float]) -> float | None:
    """The map density of the ground ``s`` chose: its fresh cells weighted by each block's
    pooled density."""
    num = den = 0.0
    for k, v in s.block_fresh.items():
        if k in dens:
            num += v * dens[k]
            den += v
    return round(num / den, 2) if den else None


# --- the path -------------------------------------------------------------------------------------


def straight_runs(fld: Field, t0: int, w1: int) -> tuple[list[int], int, int]:
    """flow_judge.heading_metrics' legs (each self_move cut where the next starts): the straight
    runs (consecutive legs turning <= 45 deg; legs < 2 cells are carried), the reversals (> 120 deg
    between legs of >= 2 cells) and the cells walked."""
    moves = [
        e for e in fld.events if e.get("type") == "self_move" and t0 <= int(e["t_mono_ns"]) < w1
    ]
    rev, runs, cur, prev_h, walked = 0, [], 0, None, 0
    for a, b in zip(moves, [*moves[1:], None], strict=True):
        tb = int(b["t_mono_ns"]) if b is not None else w1
        p0 = (int(a["x0"]), int(a["y0"]))
        p1 = fld.gm(tb - 1) or (int(a["x1"]), int(a["y1"]))
        n = fj.cheb(p0, p1)
        if n < 1:
            continue
        walked += n
        h = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
        if n >= 2 and prev_h is not None:
            d = abs((h - prev_h + math.pi) % (2 * math.pi) - math.pi)
            if d > math.radians(120):
                rev += 1
            if d > math.radians(45):
                runs.append(cur)
                cur = 0
        cur += n
        if n >= 2:
            prev_h = h
    runs.append(cur)
    return runs, rev, walked


def blocks_visited(s: Scan, t0: int, block: int = 20, win_s: float = 600.0) -> dict[str, Any]:
    """Per back-to-back ``win_s`` window (the whole scan when shorter): the distinct ``block`` x
    ``block``-cell blocks our GM stood in, and the block ENTRIES per distinct block (1.0 = never
    back in a block within the window)."""
    n_win = max(1, int(s.secs // win_s))
    dist, ratio = [], []
    for k in range(n_win):
        a, b = t0 + int(k * win_s * NS), t0 + int((k + 1) * win_s * NS)
        sel = (s.t >= a) & (s.t < b) if n_win > 1 else np.ones(len(s.t), dtype=bool)
        bl = list(zip((s.x[sel] // block).tolist(), (s.y[sel] // block).tolist(), strict=True))
        if not bl:
            continue
        ent = 1 + sum(1 for p, q in zip(bl, bl[1:], strict=False) if p != q)
        dist.append(len(set(bl)))
        ratio.append(ent / len(set(bl)))
    return {"blocks_per_window_p50": fj.pct([float(d) for d in dist], 0.5),
            "entries_per_block_p50": fj.pct(ratio, 0.5), "windows": len(dist)}  # fmt: skip


def path_summary(fld: Field, s: Scan, t0: int, w1: int) -> dict[str, Any]:
    runs, rev, walked = straight_runs(fld, t0, w1)
    mins = max(1e-9, (w1 - t0) / NS / 60)
    hm = fj.heading_metrics(fld.events, t0, w1)
    return {"cells_walked_per_min": round(walked / mins, 1),
            "moving_share": round(fj.moving_share(fld.moving, t0, w1), 2),
            "straight_run_mean": round(sum(runs) / len(runs), 1) if runs else None,
            "straight_run_p50_p90": [fj.pct([float(x) for x in runs], 0.5),
                                     fj.pct([float(x) for x in runs], 0.9)],
            "reversals_per_min": round(rev / mins, 2),
            "reversals135_per_min": hm["reversals135_per_min"],
            "turn_hist_45": hm["turn_hist_45"],
            **blocks_visited(s, t0)}  # fmt: skip


# --- turning toward a target that enters the view -------------------------------------------------


def _ang(a: Sequence[float], b: Sequence[float]) -> float:
    return math.atan2(b[1] - a[1], b[0] - a[0])


def _adiff(p: float, q: float) -> float:
    return abs((p - q + math.pi) % (2 * math.pi) - math.pi)


def motion_heading(fld: Field, t: int, back_s: float = 1.5) -> float | None:
    """Our GM's direction of travel over the ``back_s`` before ``t`` (None: < 2 cells)."""
    a, b = fld.gm(int(t - back_s * NS)), fld.gm(t)
    if a is None or b is None or fj.cheb(a, b) < 2:
        return None
    return _ang(a, b)


def turn_toward(fld: Field, t0: int, w1: int, r: int = VIEW, within_s: float = 10.0,
                busy_s: float = 3.0) -> dict[str, Any]:  # fmt: skip
    """For every target view entry: TURNED = the first walk command (self_move_request) within 45
    deg of the target's bearing, or an attack request on it; ATTACKED = an attack request on it,
    both within ``within_s``. FREE = no other target within ``r`` and no attack request in the
    ``busy_s`` before; "off-heading" = it entered > 45 deg off our direction of travel."""
    cmds = sorted([(int(e["t_mono_ns"]), "move", (int(e["x"]), int(e["y"])), -1)
                   for e in fld.events if e.get("type") == "self_move_request"]
                  + [(int(e["t_mono_ns"]), "atk", None, fj.gid_of(e, "target_gid"))
                     for e in fld.events if e.get("type") == "attack_request"],
                  key=lambda c: c[0])  # fmt: skip
    ct = [c[0] for c in cmds]
    atk_t = [c[0] for c in cmds if c[1] == "atk"]
    rows = []
    for a, g in fld.entries(t0, int(w1 - within_s * NS)):
        here, m = fld.gm(a), fld.mob(g, a)
        if here is None or m is None:
            continue
        others = [x for x in fld.targets_at(a) if x[0] != g and fj.cheb(x[1], here) <= r]
        i = bisect.bisect_right(atk_t, a) - 1
        busy = bool(others) or (i >= 0 and a - atk_t[i] <= busy_s * NS)
        h = motion_heading(fld, a)
        off = None if h is None else math.degrees(_adiff(h, _ang(here, m)))
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
                if (h2 and m2 and dst != h2
                        and _adiff(_ang(h2, dst), _ang(h2, m2)) <= math.radians(45)):  # fmt: skip
                    lat = (tc - a) / NS
            j += 1
        rows.append({"busy": busy, "off": off, "lat": lat, "latk": latk})
    groups = {
        "free_off_heading": [
            x for x in rows if not x["busy"] and x["off"] is not None and x["off"] > 45
        ],  # fmt: skip
        "free_ahead": [
            x for x in rows if not x["busy"] and x["off"] is not None and x["off"] <= 45
        ],
        "free_any": [x for x in rows if not x["busy"]],
        "busy": [x for x in rows if x["busy"]],
    }
    out: dict[str, Any] = {}
    for name, xs in groups.items():
        lt = [x["lat"] for x in xs if x["lat"] is not None]
        lk = [x["latk"] for x in xs if x["latk"] is not None]
        out[name] = {"n": len(xs),
                     "turned_2s": round(sum(v <= 2 for v in lt) / len(xs), 2) if xs else None,
                     "turned_4s": round(sum(v <= 4 for v in lt) / len(xs), 2) if xs else None,
                     "turn_lat_p50": fj.pct(lt, 0.5),
                     "attacked_10s": round(len(lk) / len(xs), 2) if xs else None,
                     "attack_lat_p50": fj.pct(lk, 0.5)}  # fmt: skip
    return out


# --- engagement ends ------------------------------------------------------------------------------


def ends_summary(fld: Field, s: Scan, ends: Sequence[int], t0: int, w1: int,
                 bot_events: Sequence[Mapping[str, Any]] = (), r: int = VIEW,
                 mem_s: float = 120.0, block: int = 40) -> dict[str, Any]:  # fmt: skip
    """At each end (an engagement's t_end, or a kill): any alive target within ``r`` (the scan's
    sample at the end)? For the "none" ends: the wait until one is (the scan), a REMEMBERED target
    (``Field.remembered``) within 15-25 cells, the bot's next search heading turn (its
    heading_goal events), and the side the next target entered from (vs our travel then)."""
    ts = s.t.tolist()
    hg = sorted((int(e["t_ns"]), e) for e in bot_events if e.get("kind") == "heading_goal")
    hgt = [h[0] for h in hg]
    ents = fld.entries(t0, w1)
    et = [e[0] for e in ents]
    n_some = n_none = mem_1525 = 0
    waits: list[float] = []
    mem_near: list[float] = []
    turns: Counter[str] = Counter()
    side: Counter[str] = Counter()
    where: dict[Cell, list[float]] = {}
    for te in sorted(ends):
        if not (t0 <= te < w1):
            continue
        k = bisect.bisect_left(ts, te)
        if k >= len(ts):
            continue
        if s.n_targets[k] > 0:
            n_some += 1
            continue
        n_none += 1
        here = (int(s.x[k]), int(s.y[k]))
        nz = np.nonzero(s.n_targets[k:] > 0)[0]
        wait = float(nz[0]) * s.dt_s if len(nz) else None
        if wait is not None:
            waits.append(wait)
            where.setdefault((here[0] // block, here[1] // block), []).append(wait)
        mem = [fj.cheb(c, here) for _g, c in fld.remembered(te, mem_s)]
        if any(15 <= d <= 25 for d in mem):
            mem_1525 += 1
        if mem:
            mem_near.append(float(min(mem)))
        if hgt:
            j = bisect.bisect_right(hgt, te)
            t_stop = te + int((wait if wait is not None else 30.0) * NS)
            if j < len(hg) and hg[j][0] <= t_stop:
                turn = abs(float(hg[j][1].get("turn") or 0.0))
                turns["kept" if turn < 1 else f"<={int(min(180, 45 * math.ceil(turn / 45)))}"] += 1
            else:
                turns["no_heading_goal"] += 1
        if wait is not None:
            i = bisect.bisect_left(et, te)
            if i < len(ents):
                ta, g = ents[i]
                h, m, here2 = motion_heading(fld, ta), fld.mob(g, ta), fld.gm(ta)
                if h is None or m is None or here2 is None:
                    side["standing"] += 1
                else:
                    d = math.degrees(_adiff(h, _ang(here2, m)))
                    side["ahead<=45" if d <= 45 else ("side45-135" if d <= 135 else "behind")] += 1
    n = n_some + n_none
    hot = sorted(where.items(), key=lambda kv: -sum(kv[1]))[:5]
    return {"ends": n, "none_in_view": n_none,
            "none_share": round(n_none / n, 2) if n else None,
            "wait_p50_p75_p90_s": [fj.pct(waits, 0.5), fj.pct(waits, 0.75), fj.pct(waits, 0.9)],
            "wait_mean_s": round(float(np.mean(waits)), 1) if waits else None,
            "wait_total_s_per_hour": round(sum(waits) * 3600 / max(1e-9, (w1 - t0) / NS)),
            "remembered_15_25_share": round(mem_1525 / n_none, 2) if n_none else None,
            "remembered_nearest_p50": fj.pct(mem_near, 0.5),
            "next_heading_turn": dict(turns), "next_target_from": dict(side),
            "top_blocks_by_wait": [{"block_x0y0": [k[0] * block, k[1] * block], "n": len(v),
                                    "wait_total_s": round(sum(v)),
                                    "wait_mean_s": round(sum(v) / len(v), 1)}
                                   for k, v in hot]}  # fmt: skip


# --- the proposal's scorer and the heading regret -------------------------------------------------


def rel_yield(age_s: Any) -> Any:
    """The relative yield of ground last in view ``age_s`` ago (inf = never this run): AGE_REL."""
    a = np.asarray(age_s, dtype=float)
    out = np.full(a.shape, NEVER_REL)
    fin = np.isfinite(a)
    lo = 0.0
    for hi, v in AGE_REL:
        out[fin & (a > lo) & (a <= hi)] = v
        lo = hi
    out[fin & (a <= 0)] = AGE_REL[0][1]
    return out


def ray_cells(area: Any, start: Cell, ang: float, max_len: int = 40) -> list[Cell]:
    """hunt_flow.ray_run_angle's ray (radians, x right / y = the map's y), as its cells from
    ``start`` (included) to the last inside ``area``."""
    h, w = np.asarray(area).shape
    dx, dy = math.cos(ang), math.sin(ang)
    k = max(abs(dx), abs(dy))
    dx, dy = dx / k, dy / k
    out = [start]
    for i in range(1, max_len + 1):
        c = (int(round(start[0] + dx * i)), int(round(start[1] + dy * i)))
        if not (0 <= c[0] < w and 0 <= c[1] < h) or not area[c[1], c[0]]:
            break
        out.append(c)
    return out


def band_score(
    area: Any,
    walkable: Any,
    here: Cell,
    ang: float,
    last_seen: Any,
    now_ns: int,
    footprint: Sequence[Cell] | None = None,
    r: int = VIEW,
    max_len: int = 40,
    min_run: int = 8,
    ms_cell: float = MS_CELL,
) -> tuple[float, int, int] | None:
    """THE PROPOSAL (search_study 2026-10-18): a heading's value = the expected yield of the ground
    it brings into view, per walking second. The cells the ``footprint`` (offsets; default the
    server's Chebyshev-``r`` square -- live, the bot's own on-screen cells) covers along the ray
    and does not cover from ``here``, each weighted by ``rel_yield`` of its age (``last_seen``:
    ns, -inf = never), over the ray's walk time (a diagonal step 1.4x). None when the ray runs
    < ``min_run`` cells. Returns (score, cells, run)."""
    cells = ray_cells(area, here, ang, max_len)
    if len(cells) - 1 < min_run:
        return None
    wk = np.asarray(walkable, dtype=bool)
    h, w = wk.shape
    square = [(dx, dy) for dy in range(-r, r + 1) for dx in range(-r, r + 1)]
    offs = np.array(square if footprint is None else footprint, dtype=int).reshape(-1, 2)
    pad = int(np.abs(offs).max()) + 1
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    gx0, gy0 = max(0, min(xs) - pad), max(0, min(ys) - pad)
    gx1, gy1 = min(w, max(xs) + pad + 1), min(h, max(ys) + pad + 1)
    band = np.zeros((gy1 - gy0, gx1 - gx0), dtype=bool)
    now_view = np.zeros_like(band)
    for i, c in enumerate(cells):
        px, py = offs[:, 0] + c[0] - gx0, offs[:, 1] + c[1] - gy0
        ok = (px >= 0) & (px < band.shape[1]) & (py >= 0) & (py < band.shape[0])
        (now_view if i == 0 else band)[py[ok], px[ok]] = True
    band &= ~now_view & wk[gy0:gy1, gx0:gx1]
    ls = np.asarray(last_seen)[gy0:gy1, gx0:gx1][band]
    ages = np.where(np.isinf(ls), np.inf, (now_ns - ls) / NS)
    walk_s = sum((1.4 if (a[0] != b[0] and a[1] != b[1]) else 1.0)
                 for a, b in zip(cells, cells[1:], strict=False)) * ms_cell / 1000  # fmt: skip
    return float(rel_yield(ages).sum()) / walk_s, int(band.sum()), len(cells) - 1


def heading_regret(fld: Field, bot_events: Sequence[Mapping[str, Any]], t0: int, w1: int,
                   walkable: Any, area: Any, every: int = 3, dt_s: float = 0.5,
                   r: int = VIEW) -> dict[str, Any]:  # fmt: skip
    """At every ``every``-th heading_goal of the bot, from the GM's packet cell then and the view
    history so far (the packets: the server's view), ``band_score`` of the heading it chose
    (event "ang", degrees) vs the best of the 8 compass headings. chosen / best < 1 = the yield /
    s the proposal would have taken instead."""
    wk = np.asarray(walkable, dtype=bool)
    last = np.full(wk.shape, NEVER)
    hg = sorted((int(e["t_ns"]), math.radians(float(e["ang"]))) for e in bot_events
                if e.get("kind") == "heading_goal" and e.get("ang") is not None
                and t0 <= int(e["t_ns"]) < w1)  # fmt: skip
    dt = int(dt_s * NS)
    i = n = 0
    ratios, chosen_sum, best_sum = [], 0.0, 0.0
    best_turn: Counter[int] = Counter()
    for t in range(t0, w1, dt):
        c = fld.gm(t)
        if c is None:
            continue
        last[max(0, c[1] - r) : c[1] + r + 1, max(0, c[0] - r) : c[0] + r + 1] = t
        while i < len(hg) and hg[i][0] <= t:
            th, a = hg[i]
            i += 1
            n += 1
            if n % every:
                continue
            ch = band_score(area, wk, c, a, last, th)
            cands = [(k, band_score(area, wk, c, k * math.pi / 4, last, th)) for k in range(8)]
            ok = [(k, x[0]) for k, x in cands if x is not None]
            if ch is None or not ok:
                continue
            kb, best = max(ok, key=lambda kv: kv[1])
            if best <= 0:
                continue
            ratios.append(ch[0] / best)
            chosen_sum += ch[0]
            best_sum += best
            d = round(math.degrees(_adiff(a, kb * math.pi / 4)) / 45) * 45
            best_turn[int(d)] += 1
    return {"n": len(ratios), "chosen_over_best_p50": fj.pct(ratios, 0.5),
            "chosen_over_best_mean": round(float(np.mean(ratios)), 2) if ratios else None,
            "chosen_over_best_sum": round(chosen_sum / best_sum, 2) if best_sum else None,
            "share_below_0.6": round(sum(x < 0.6 for x in ratios) / len(ratios), 2)
            if ratios else None,
            "best_vs_chosen_deg": dict(sorted(best_turn.items()))}  # fmt: skip


# --- sessions -------------------------------------------------------------------------------------


@dataclass
class Session:
    sid: str
    events: list[dict[str, Any]]
    t0: int
    w1: int
    bot: bool
    bot_events: list[dict[str, Any]] = field(default_factory=list)
    engagements: list[dict[str, Any]] = field(default_factory=list)
    map_name: str = "prt_fild08"


def load_session(sid: str, root: Path | None = None) -> Session:
    """flow_judge's windows: a human demo from the first walk after arming, 600 s; a bot run from
    the first walk after its loop start to min(the run's end, its last click + 5 s)."""
    if root is None:
        from poring_env.demo import DEMO_ROOT

        root = DEMO_ROOT
    d = root / sid
    man = json.loads((d / "manifest.json").read_text())
    with gzip.open(d / "packets.jsonl.gz", "rt") as fh:
        events = sorted((json.loads(x) for x in fh), key=lambda e: int(e["t_mono_ns"]))
    if (d / "events.jsonl").exists():
        bev = [json.loads(x) for x in (d / "events.jsonl").read_text().splitlines() if x]
        clicks = [json.loads(x) for x in (d / "clicks.jsonl").read_text().splitlines() if x]
        loop0 = next((int(x["t_ns"]) for x in bev if x.get("kind") == "loop_start"),
                     int(man["t0_mono_ns"]))  # fmt: skip
        t0 = fj.t0_of(events, loop0)
        if t0 is None:
            raise SystemExit(f"{sid}: no movement after the loop start")
        w1 = min(int(man.get("t1_mono_ns", t0)), max(int(c["t"]) for c in clicks) + 5 * NS)
        engs = json.loads((d / "engagements.json").read_text())
        return Session(sid, events, t0, w1, True, bev, engs, man.get("map", "prt_fild08"))
    t0 = fj.t0_of(events, int(man["t_armed_ns"]))
    if t0 is None:
        raise SystemExit(f"{sid}: no movement after arming")
    return Session(sid, events, t0, t0 + int(fj.WINDOW_S * NS), False,
                   map_name=man.get("map", "prt_fild08"))  # fmt: skip


def load_walkable(map_name: str) -> Any:
    """The client GAT's walkable cells (client-derived: generated locally at run time, never
    committed), or None when the GAT is not extracted (every cell then counts)."""
    try:
        from poring_dataset import camera as cam
        from poring_dataset import gat as gatmod

        g = gatmod.parse((cam.GAT_DIR / f"{map_name}.gat").read_bytes())
    except (ImportError, OSError, ValueError):
        return None
    wk = g.walkable() if callable(getattr(g, "walkable", None)) else g.walkable
    return np.asarray(wk, dtype=bool)


def search_area_of(walkable: Any, border: int = 20) -> Any:
    """hunt_core.search_area's border on the walkable grid (the offline stand-in for the bot's
    area: no warp / NPC margins -- the regret compares headings on the same grid)."""
    return hc.search_area(walkable, [], border=border, margin=0)


def analyse(sess: Session, walkable: Any) -> tuple[dict[str, Any], Scan, Field]:
    fld = Field(sess.events)
    s = scan(fld, sess.t0, sess.w1, walkable)
    kills = kill_times(sess.events, sess.t0, sess.w1)
    s.kills = len(kills)
    out: dict[str, Any] = {
        "conversion": conversion(sess.events, sess.t0, sess.w1),
        "path": path_summary(fld, s, sess.t0, sess.w1),
        "sweep": sweep_summary(s),
        "presence": presence_summary([s]),
        "yield_by_age": yield_by_age(s),
        "turn_toward": turn_toward(fld, sess.t0, sess.w1),
        "at_kills": ends_summary(fld, s, kills, sess.t0, sess.w1),
    }
    if sess.bot:
        ends = [int(e["t_end"]) for e in sess.engagements if e.get("t_end")]
        out["engagement_ends"] = ends_summary(fld, s, ends, sess.t0, sess.w1, sess.bot_events)
        if walkable is not None:
            out["heading_regret"] = heading_regret(fld, sess.bot_events, sess.t0, sess.w1,
                                                   walkable, search_area_of(walkable))  # fmt: skip
    return out, s, fld


TABLE_ROWS = (
    ("kills / h", ("conversion", "kills_per_hour")),
    ("monsters in sight / 10 min (windowed)", ("conversion", "sight_per_10min")),
    ("KILLS PER SIGHTING (Batt 6.82)", ("conversion", "kills_per_sighting")),
    ("cells walked / min", ("path", "cells_walked_per_min")),
    ("moving share", ("path", "moving_share")),
    ("straight run mean (cells)", ("path", "straight_run_mean")),
    ("reversals > 120 deg / min", ("path", "reversals_per_min")),
    ("20-cell blocks / 10 min (p50)", ("path", "blocks_per_window_p50")),
    ("block entries per block / 10 min (p50)", ("path", "entries_per_block_p50")),
    ("new-in-view cells per cell walked", ("sweep", "new_in_view_per_cell")),
    ("diagonal share of steps", ("sweep", "diagonal_share")),
    ("re-swept <= 5 s", ("sweep", "reswept_share", "<=5s")),
    ("re-swept <= 30 s", ("sweep", "reswept_share", "<=30s")),
    ("re-swept <= 120 s", ("sweep", "reswept_share", "<=120s")),
    ("fresh ground cells / min", ("sweep", "fresh_per_min")),
    ("age-weighted new cells / min", ("sweep", "age_weighted_new_per_min")),
    ("no-target share of time", ("presence", "none_share")),
    ("no-target s per kill", ("presence", "none_s_per_kill")),
    ("target-in-view s per kill", ("presence", "some_s_per_kill")),
    ("no-target stretches per kill", ("presence", "stretches_per_kill")),
    ("no-target stretch mean s", ("presence", "stretch_mean_s")),
    ("encounters per no-target min", ("presence", "encounters_per_none_min")),
    ("fresh cells / s in no-target", ("presence", "fresh_per_s_in_none")),
    ("stretch ends per 1000 fresh cells", ("presence", "stretch_ends_per_1000_fresh")),
    ("at kills: no target within 14", ("at_kills", "none_share")),
    ("at kills: wait p50 s", ("at_kills", "wait_p50_p75_p90_s", 0)),
    ("free entry, off-heading: turned <= 2 s", ("turn_toward", "free_off_heading", "turned_2s")),
    ("free entry: turn latency p50 s", ("turn_toward", "free_any", "turn_lat_p50")),
    ("free entry: attacked <= 10 s", ("turn_toward", "free_any", "attacked_10s")),
)


def _dig(o: Any, path: Sequence[Any]) -> Any:
    for k in path:
        if o is None:
            return None
        o = o[k] if isinstance(k, int) else o.get(k)
    return o


def compare(sids: Sequence[str], root: Path | None = None) -> dict[str, Any]:
    """Every session's tables, the bot runs POOLED (sums over the runs; conversion from the summed
    kills and the median window sight), the block density and each session's ground density."""
    sessions = [load_session(s, root) for s in sids]
    walkable = load_walkable(sessions[0].map_name)
    res: dict[str, Any] = {}
    scans: dict[str, Scan] = {}
    for sess in sessions:
        out, s, _fld = analyse(sess, walkable)
        res[sess.sid] = out
        scans[sess.sid] = s
    bots = [x for x in sessions if x.bot]
    if bots:
        pool = merge_scans([scans[b.sid] for b in bots])
        kills = sum(res[b.sid]["conversion"]["kills"] for b in bots)
        secs = sum(res[b.sid]["conversion"]["window_s"] for b in bots)
        sights = sorted(w["sight_per_10min"] for b in bots
                        for w in res[b.sid]["conversion"]["windows"])  # fmt: skip
        kph = round(kills * 3600 / secs, 1)
        sight = fj.pct(sights, 0.5)
        res["BOT_POOLED"] = {
            "conversion": {"kills": kills, "kills_per_hour": kph, "sight_per_10min": sight,
                           "kills_per_sighting": kills_per_sighting(kph, sight or 0.0)},
            "sweep": sweep_summary(pool),
            "presence": presence_summary([scans[b.sid] for b in bots]),
            "yield_by_age": yield_by_age(pool),
        }  # fmt: skip
    dens = block_density(list(scans.values()))
    for sid, s in scans.items():
        res[sid]["ground_density_per_1000_fresh"] = ground_density(s, dens)
    cols = [x.sid for x in sessions] + (["BOT_POOLED"] if bots else [])
    table = [{"metric": name, **{c[-22:]: _dig(res[c], path) for c in cols}}
             for name, path in TABLE_ROWS]  # fmt: skip
    return {"walkable": walkable is not None, "table": table,
            "block_density_per_1000_fresh": {f"{k[0] * 40},{k[1] * 40}": v
                                             for k, v in sorted(dens.items())},
            "sessions": res}  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compare")
    c.add_argument("sessions", nargs="+")
    k = sub.add_parser("kps")
    k.add_argument("sessions", nargs="+")
    a = ap.parse_args()
    if a.cmd == "kps":
        out = {}
        for sid in a.sessions:
            sess = load_session(sid)
            cv = conversion(sess.events, sess.t0, sess.w1)
            out[sid] = {kk: cv[kk] for kk in ("kills_per_hour", "sight_per_10min",
                                              "kills_per_sighting")}  # fmt: skip
        print(json.dumps(out, indent=1))
        return 0
    print(json.dumps(compare(a.sessions), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
