#!/usr/bin/env python3
"""SEARCH GAP (Batt 2026-10-17): flow_judge's "monsters in sight / 10 min" is 44 for Batt's human
demo and 13-19 for the hunt-flow runs on the same map. Why -- from data, OFFLINE (packets are
ground truth here only, never a decision input).

    search_gap.py analyse SID [SID ...] [--json OUT]

Per session, on the SAME basis: back-to-back 10-min windows from the first move (flow_judge's t0;
Batt's demo is one window), and per window:

  SIGHT       flow_judge.sight_per_10min's own definition (distinct mob gids with an
              entity_appear in the window), the AOI census (distinct gids alive inside the
              server's area of interest at any time in it) and, on the detector frames: IN VIEW
              (the feet projected into the 1280 x 720 game region, the body not under a static UI
              window) and DETECTED (a monster box matched within MATCH_PX of it on >= 1 frame).
  DETECTOR    per-frame recall of in-view mobs by ring (Chebyshev cells from our GM), species,
              GM moving / standing, screen band; per VISIT (one stay in view): detected at all,
              and the first-detection delay after it came into view.
  SEARCH      cells walked / min; WALKABLE cells SWEPT / min by the AOI square (fresh within the
              window: the sight basis) and new to the whole session; per cell walked; reversals /
              min (flow_judge.heading_metrics); net cells moved per 60 s; the standing share;
              entries per 1000 swept walkable cells (the density met); how each counted gid got
              in (a standing mob our walk brought in, a walking one, GM moving / standing); the
              time split from packets for any actor (FIGHT / LOOT / walk / stand, AOI empty or
              not) and, for a bot, its own mode log.

HOW (the drop_blobs.py conventions): positions from packets -- our GM from self_move /
entity_stop / map_change at 150 ms a cell, every monster from entity_appear (rAthena re-sends the
walking spawn 0x09FD to the whole area at EVERY walk start, so in-view wandering is in the
packets; a walk that started before it came into view starts at move_start_tick). The screen
shows the server LAG_S late: a frame at t is matched to positions at t - LAG_S, the camera centred
on our GM's fractional cell (drop_blobs.Projector). A box's feet = (centre u, bottom v) minus the
session's median offset to the projection (measured, printed). Matching is greedy nearest-first.

MEASURED 2026-10-17 (Batt's demo 20261016T093835, one window; hunt-flow17 / 18 / 20 / 20, 22
windows; bot = the median window unless said):
  - The headline 13-19 is flow_judge.bot() counting DISTINCT gids over the WHOLE 45-60 min run,
    / 6: rAthena keeps a spawn slot's block id across respawns, so the count saturates at the
    population met (82-103 gids per run). Per 10-min window the bots meet 24-30.5 (median per
    run; 27.5 pooled; best windows 40-46) vs Batt 44.
  - The remaining 0.62 is AREA SWEPT: 2535 vs 3995 walkable AOI cells / min (0.63) = moving share
    0.85 x swept per cell walked 0.78 (reversals 5.0 vs 3.6 / min, net 59 vs 91 cells / 60 s).
    The density met is about equal (0.93 vs 1.10 per 1000 swept walkable cells); it drives the
    bot's window-to-window spread, not its gap to Batt.
  - The detector is NOT in the sight number (packets only). Of the mobs in view, 91 % are boxed
    at least once per window (Batt's session 98 %); frame recall 69 % (Batt's 66 %), flat by ring
    (66-74 %); Creamy 11 %; GM moving 52 % (70 % within 80 px: mostly our lag model) vs standing
    76 %; visits < 1 s 53 %; first box on the first in-view frame (p50 0 s, p90 1.0-1.6 s).
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import json
import math
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

DEMO_ROOT = Path("/dev/shm/poring-lab-demo")
NS = 10**9
GM = 2000002
GM_MS_CELL = 150.0
DIAG = 1.4
LAG_S = 0.5  # the frames show the server ~0.45-0.6 s late (hunt_flow v7, drop_blobs)
AOI = 14  # rAthena area_size: the server sends units within this many cells (Chebyshev)
WINDOW_S = 600.0
MATCH_PX = 40.0
CALIB_PX = 60.0  # pairs nearer than this calibrate the box-feet offset
VISIT_GAP_S = 1.0  # in-view frames further apart than this start a new visit
BODY_UP_PX = 20.0  # the sprite's body centre above its feet (the UI test uses the body)
SCREEN = (1280, 720)
EDGE = (8.0, 24.0, 8.0, 4.0)  # left, top, right, bottom margins for the feet to count as drawn
RINGS = ((0, 3), (4, 6), (7, 9), (10, 14))
SPECIES = {1002: "Poring", 1063: "Lunatic", 1008: "Pupa", 1113: "Drops", 1018: "Creamy"}
# prt_fild08's spawn table (the local KB, data/kb/spawns.json, read 2026-10-17): 70 Poring, 40
# Lunatic, 20 Pupa, 10 Drops, every one map-wide (0,0,0,0) with delay 0 -- a uniform density
POPULATION = 140
Cell = tuple[int, int]
Pt = tuple[float, float]


# --- pure helpers ---------------------------------------------------------------------------------


def cheb_path(a: Cell, b: Cell) -> list[Cell]:
    """Chebyshev steps a -> b, diagonal first (flow_judge.steps)."""
    out, (x, y) = [], a
    while (x, y) != b:
        x += (b[0] > x) - (b[0] < x)
        y += (b[1] > y) - (b[1] < y)
        out.append((x, y))
    return out


def walk_at(a: Cell, b: Cell, t0: int, ms_cell: float, t: int) -> Pt:
    """Fractional position at ``t`` along a walk a -> b started at ``t0`` (diagonals x DIAG)."""
    prev, tt = (float(a[0]), float(a[1])), float(t0)
    for c in cheb_path(a, b):
        dt = ms_cell * (DIAG if c[0] != prev[0] and c[1] != prev[1] else 1.0) * 1e6
        if t < tt + dt:
            f = max(0.0, (t - tt) / dt)
            return prev[0] + f * (c[0] - prev[0]), prev[1] + f * (c[1] - prev[1])
        prev, tt = (float(c[0]), float(c[1])), tt + dt
    return prev


def walk_end(a: Cell, b: Cell, t0: int, ms_cell: float) -> int:
    tt, prev = float(t0), a
    for c in cheb_path(a, b):
        tt += ms_cell * (DIAG if c[0] != prev[0] and c[1] != prev[1] else 1.0) * 1e6
        prev = c
    return int(tt)


@dataclass
class Walker:
    """One unit's position over time: walks (t0, a, b, ms/cell) and pins (a == b); the newest
    segment that started at or before t wins."""

    segs: list[tuple[int, Cell, Cell, float]] = field(default_factory=list)
    _ts: list[int] = field(default_factory=list)

    def add(self, t0: int, a: Cell, b: Cell, ms_cell: float) -> None:
        i = bisect.bisect_right(self._ts, t0)
        self.segs.insert(i, (t0, a, b, ms_cell))
        self._ts.insert(i, t0)

    def at(self, t: int) -> Pt | None:
        i = bisect.bisect_right(self._ts, t) - 1
        if i < 0:
            return None
        t0, a, b, ms = self.segs[i]
        return walk_at(a, b, t0, ms, t)

    def moving(self, t: int) -> bool:
        i = bisect.bisect_right(self._ts, t) - 1
        if i < 0:
            return False
        t0, a, b, ms = self.segs[i]
        return a != b and t < walk_end(a, b, t0, ms)


def greedy_match(pts: Sequence[Pt], feet: Sequence[Pt], r: float) -> dict[int, tuple[int, float]]:
    """Nearest-first one-to-one matching of projected points to box feet within ``r`` px:
    {point index: (box index, distance)}."""
    pairs = sorted((math.dist(p, f), i, j) for i, p in enumerate(pts)
                   for j, f in enumerate(feet))  # fmt: skip
    out: dict[int, tuple[int, float]] = {}
    used: set[int] = set()
    for d, i, j in pairs:
        if d > r:
            break
        if i in out or j in used:
            continue
        out[i] = (j, d)
        used.add(j)
    return out


def on_screen(u: float, v: float, size: tuple[int, int] = SCREEN,
              edge: tuple[float, float, float, float] = EDGE) -> bool:  # fmt: skip
    return edge[0] <= u <= size[0] - edge[2] and edge[1] <= v <= size[1] - edge[3]


def under_ui(u: float, v: float, windows: Iterable[tuple[float, float, float, float]]) -> bool:
    """The body (BODY_UP_PX above the feet) inside a static UI window."""
    vb = v - BODY_UP_PX
    return any(x0 <= u <= x1 and y0 <= vb <= y1 for x0, y0, x1, y1 in windows)


def ring_of(d: int) -> str:
    for a, b in RINGS:
        if a <= d <= b:
            return f"{a}-{b}"
    return f">{RINGS[-1][1]}"


def visits(times: Sequence[int], gap_s: float = VISIT_GAP_S) -> list[tuple[int, int]]:
    """Index ranges [i, j) of sorted ``times`` with no gap over ``gap_s``."""
    out, i = [], 0
    for k in range(1, len(times) + 1):
        if k == len(times) or times[k] - times[k - 1] > gap_s * NS:
            out.append((i, k))
            i = k
    return out


def footprint_offsets(project: Any, reach: int = 30) -> list[Cell]:
    """Cell offsets whose (flat-ground) feet land drawn on screen with the GM at the origin."""
    offs = [(dx, dy) for dx in range(-reach, reach + 1) for dy in range(-reach, reach + 1)]
    px = project(offs)
    return [o for o, (u, v) in zip(offs, px, strict=True) if on_screen(float(u), float(v))]


def sweep(cells: Sequence[Cell], offsets: Sequence[Cell], seen: set[Cell],
          ok: Any = None) -> int:  # fmt: skip
    """Add ``cells`` + every offset to ``seen`` (only cells ``ok(cell)`` accepts, when given);
    the count of cells that were new."""
    n0 = len(seen)
    for c in cells:
        for dx, dy in offsets:
            q = (c[0] + dx, c[1] + dy)
            if q not in seen and (ok is None or ok(q)):
                seen.add(q)
    return len(seen) - n0


def merge_iv(iv: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for a, b in sorted(iv):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def in_iv(iv: Sequence[tuple[int, int]], starts: Sequence[int], t: int) -> bool:
    i = bisect.bisect_right(starts, t) - 1
    return i >= 0 and iv[i][0] <= t < iv[i][1]


def net_displacement(pos: Sequence[Pt | None], lag: int) -> list[float]:
    """Chebyshev cells between each sample and the one ``lag`` samples earlier."""
    return [max(abs(a[0] - b[0]), abs(a[1] - b[1])) for a, b in zip(pos[lag:], pos, strict=False)
            if a is not None and b is not None]  # fmt: skip


def pct(xs: Sequence[float], q: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return round(s[min(len(s) - 1, int(q * (len(s) - 1) + 0.5))], 2)


def rate(k: int, n: int) -> str:
    return f"{k}/{n} = {100 * k / n:.0f} %" if n else "-"


# --- packets --------------------------------------------------------------------------------------


@dataclass
class World:
    gm: Walker
    mobs: dict[int, Walker]
    lives: dict[int, list[tuple[int, int | None, int]]]  # gid -> [(appear, vanish | None, reason)]
    job: dict[int, int]
    gm_moving: list[tuple[int, int]]

    def alive_at(self, g: int, t: int) -> bool:
        return any(a <= t and (b is None or t < b) for a, b, _ in self.lives.get(g, ()))


def tick_offset_ns(events: Sequence[Mapping[str, Any]]) -> int:
    """t_mono_ns - server_tick * 1e6 (rAthena's gettick() is the shared CLOCK_MONOTONIC in ms),
    the median over the packets that carry a server tick."""
    xs = sorted(
        int(e["t_mono_ns"]) - int(e["server_tick"]) * 10**6
        for e in events
        if e.get("server_tick") is not None and e.get("type") in ("self_move", "act")
    )
    return xs[len(xs) // 2] if xs else 0


def build_world(events: Sequence[Mapping[str, Any]]) -> World:
    off = tick_offset_ns(events)
    gm, mobs = Walker(), {}
    lives: dict[int, list[tuple[int, int | None, int]]] = {}
    job: dict[int, int] = {}
    moving: list[tuple[int, int]] = []
    for e in events:
        t, typ = int(e["t_mono_ns"]), e.get("type")
        g = -1 if e.get("gid") is None else int(e["gid"])
        if typ == "self_move":
            a, b = (int(e["x0"]), int(e["y0"])), (int(e["x1"]), int(e["y1"]))
            gm.add(t, a, b, GM_MS_CELL)
            if moving and moving[-1][1] > t:
                moving[-1] = (moving[-1][0], t)
            moving.append((t, walk_end(a, b, t, GM_MS_CELL)))
        elif typ == "map_change" or (typ == "entity_stop" and g == GM):
            c = (int(e["x"]), int(e["y"]))
            gm.add(t, c, c, GM_MS_CELL)
            if moving and moving[-1][1] > t:
                moving[-1] = (moving[-1][0], t)
        elif typ == "entity_appear" and e.get("objtype") == 5:
            ls = lives.setdefault(g, [])
            if not ls or ls[-1][1] is not None:
                ls.append((t, None, -1))
            job.setdefault(g, int(e.get("job") or -1))
            a = (int(e["x"]), int(e["y"]))
            ms = float(e.get("speed") or 200)
            if e.get("x1") is not None:
                b = (int(e["x1"]), int(e["y1"]))
                t0 = t
                if e.get("move_start_tick") is not None:
                    ts = int(e["move_start_tick"]) * 10**6 + off
                    t0 = ts if 0 <= t - ts <= 30 * NS else t
                mobs.setdefault(g, Walker()).add(t0, a, b, ms)
            else:
                mobs.setdefault(g, Walker()).add(t, a, a, ms)
        elif typ == "entity_stop" and g in mobs:
            c = (int(e["x"]), int(e["y"]))
            mobs[g].add(t, c, c, 200.0)
        elif typ == "entity_vanish" and lives.get(g) and lives[g][-1][1] is None:
            lives[g][-1] = (lives[g][-1][0], t, int(e.get("reason", -1)))
    return World(gm, mobs, lives, job, moving)


def busy_intervals(
    events: Sequence[Mapping[str, Any]],
    gap_s: float = 3.0,
    tail_s: float = 1.0,
    loot_s: float = 10.0,
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """From packets, for ANY actor: FIGHT = our attack requests / damaging acts on one unit, runs
    with gaps <= gap_s, + tail_s (cut at its vanish); LOOT = from one of our kills to our last
    pickup request within loot_s of it."""
    per: dict[int, list[int]] = defaultdict(list)
    vanish: dict[int, list[int]] = defaultdict(list)
    kills: list[int] = []
    for e in events:
        t, typ = int(e["t_mono_ns"]), e.get("type")
        ours = typ == "attack_request" or (typ == "act" and e.get("src_gid") == GM)
        if ours and e.get("target_gid") is not None:
            per[int(e["target_gid"])].append(t)
        elif typ == "entity_vanish" and e.get("gid") is not None:
            vanish[int(e["gid"])].append(t)
            if int(e.get("reason", -1)) == 1 and int(e["gid"]) in per \
                    and 0 <= t - per[int(e["gid"])][-1] <= 30 * NS:  # fmt: skip
                kills.append(t)
    fight = []
    for g, ts in per.items():
        ts.sort()
        a = b = ts[0]
        for t in [*ts[1:], None]:
            if t is not None and t - b <= gap_s * NS:
                b = t
                continue
            end = b + int(tail_s * NS)
            k = bisect.bisect_left(vanish[g], b)
            if k < len(vanish[g]):
                end = min(end, vanish[g][k])
            fight.append((a, max(a + 1, end)))
            if t is not None:
                a = b = t
    picks = sorted(int(e["t_mono_ns"]) for e in events if e.get("type") == "pickup_request")
    loot = []
    for tk in kills:
        last = [t for t in picks[bisect.bisect_left(picks, tk) :] if t - tk <= loot_s * NS]
        if last:
            loot.append((tk, last[-1] + 1))
    return merge_iv(fight), merge_iv(loot)


def kills_in(events: Sequence[Mapping[str, Any]], w0: int, w1: int) -> int:
    hit: dict[int, int] = {}
    n = 0
    for e in events:
        t, typ = int(e["t_mono_ns"]), e.get("type")
        if typ == "act" and e.get("src_gid") == GM and int(e.get("damage") or 0) > 0 \
                and e.get("target_gid") is not None:  # fmt: skip
            hit[int(e["target_gid"])] = t
        elif typ == "entity_vanish" and int(e.get("reason", -1)) == 1 and w0 <= t < w1:
            g = int(e["gid"])
            n += g in hit and 0 <= t - hit[g] <= 30 * NS
    return n


# --- one session ----------------------------------------------------------------------------------


def load(
    sid: str,
) -> tuple[Path, dict[str, Any], list[dict[str, Any]], list[tuple[int, list[Any]]]]:
    d = DEMO_ROOT / sid
    man = json.loads((d / "manifest.json").read_text())
    with gzip.open(d / "packets.jsonl.gz", "rt") as fh:
        events = sorted((json.loads(x) for x in fh), key=lambda e: int(e["t_mono_ns"]))
    frames = []
    for line in (d / "boxes.jsonl").open():
        x = json.loads(line)
        frames.append((int(x["t"]), [b for b in x["boxes"] if b[5] == "monster"]))
    frames.sort(key=lambda f: f[0])
    return d, man, events, frames


def session_windows(d: Path, man: Mapping[str, Any], events: Sequence[Mapping[str, Any]]
                    ) -> tuple[str, list[tuple[int, int]]]:  # fmt: skip
    """flow_judge's t0 (the first move after arming / the loop start) and back-to-back full
    WINDOW_S windows from it (Batt's demo: one)."""
    from flow_judge import t0_of

    if (d / "events.jsonl").exists():
        loop0 = next((int(x["t_ns"]) for x in map(json.loads, (d / "events.jsonl").read_text()
                                                  .splitlines()) if x.get("kind") == "loop_start"),
                     int(man["t0_mono_ns"]))  # fmt: skip
        actor = "bot"
    else:
        loop0, actor = int(man["t_armed_ns"]), "human"
    t0 = t0_of(events, loop0)
    if t0 is None:
        raise SystemExit(f"{d.name}: no movement after the start")
    t_end = int(man.get("t1_mono_ns") or events[-1]["t_mono_ns"])
    n = max(1, int((t_end - t0) // int(WINDOW_S * NS)))
    return actor, [(t0 + k * int(WINDOW_S * NS), t0 + (k + 1) * int(WINDOW_S * NS))
                   for k in range(n)]  # fmt: skip


def mode_split(d: Path, w0: int, w1: int) -> dict[str, float] | None:
    """The bot's own mode log: share of the window in each mode; loot sweeps (their ``s``)."""
    p = d / "events.jsonl"
    if not p.exists():
        return None
    evs = [x for x in map(json.loads, p.read_text().splitlines())]
    modes = sorted((int(x["t_ns"]), str(x["mode"])) for x in evs if x.get("kind") == "mode")
    tot: Counter[str] = Counter()
    for k, (t, m) in enumerate(modes):
        t_next = modes[k + 1][0] if k + 1 < len(modes) else w1
        tot[m] += max(0, min(t_next, w1) - max(t, w0))
    loot = sum(min(int(x["t_ns"]), w1) - max(int(x["t_ns"] - float(x["s"]) * NS), w0)
               for x in evs if x.get("kind") == "loot" and x.get("s") is not None
               and w0 <= int(x["t_ns"]) < w1)  # fmt: skip
    out = {m: round(v / (w1 - w0), 3) for m, v in sorted(tot.items())}
    out["loot_sweeps"] = round(loot / (w1 - w0), 3)
    return out


def analyse(sid: str) -> dict[str, Any]:
    import numpy as np
    from drop_blobs import Projector
    from flow_judge import sight_per_10min
    from route_preview import UI_WINDOWS

    d, man, events, frames = load(sid)
    actor, wins = session_windows(d, man, events)
    world = build_world(events)
    proj = Projector(man.get("map", "prt_fild08"))
    lag = int(LAG_S * NS)
    ft = [f[0] for f in frames]

    # 1) every detector frame: in-view mobs (projected) and the box feet
    rows: list[dict[str, Any]] = []  # one per (frame, in-view mob)
    frame_boxes: list[tuple[int, list[Pt], list[list[Any]]]] = []
    w_all0, w_all1 = wins[0][0], wins[-1][1]
    i0, i1 = bisect.bisect_left(ft, w_all0), bisect.bisect_left(ft, w_all1)
    for tf, boxes in frames[i0:i1]:
        td = tf - lag
        here = world.gm.at(td)
        if here is None:
            continue
        gids = [g for g in world.mobs if world.alive_at(g, td)]
        pos = [world.mobs[g].at(td) for g in gids]
        keep = [(g, p) for g, p in zip(gids, pos, strict=True) if p is not None
                and max(abs(p[0] - here[0]), abs(p[1] - here[1])) <= AOI + 0.5]  # fmt: skip
        feet = [((b[0] + b[2]) / 2, b[3]) for b in boxes]
        frame_boxes.append((tf, feet, boxes))
        if not keep:
            continue
        px = proj.project(here, [p for _g, p in keep])
        for (g, p), (u, v) in zip(keep, px, strict=True):
            u, v = float(u), float(v)
            ring = max(abs(p[0] - here[0]), abs(p[1] - here[1]))
            rows.append({"t": tf, "g": g, "u": u, "v": v, "d": int(round(ring)),
                         "view": on_screen(u, v) and not under_ui(u, v, UI_WINDOWS),
                         "mob_moving": world.mobs[g].moving(td), "gm_moving": False})  # fmt: skip

    # 2) the box-feet offset: nearest box to each in-view mob, pairs under CALIB_PX
    by_t: dict[int, list[int]] = defaultdict(list)
    for k, r_ in enumerate(rows):
        by_t[r_["t"]].append(k)
    fb = {tf: (feet, boxes) for tf, feet, boxes in frame_boxes}
    du, dv = [], []
    for tf, ks in by_t.items():
        feet = fb[tf][0]
        pts = [(rows[k]["u"], rows[k]["v"]) for k in ks if rows[k]["view"]]
        for i, (j, _dd) in greedy_match(pts, feet, CALIB_PX).items():
            du.append(feet[j][0] - pts[i][0])
            dv.append(feet[j][1] - pts[i][1])
    off = (float(np.median(du)) if du else 0.0, float(np.median(dv)) if dv else 0.0)

    # 3) match with the offset; the GM's moving flag; box heights of matches
    mv_iv = world.gm_moving
    mv_t0 = [a for a, _b in mv_iv]
    dists: list[float] = []
    box_h: dict[str, list[float]] = defaultdict(list)
    for tf, ks in by_t.items():
        feet, boxes = fb[tf]
        ks = [k for k in ks if rows[k]["view"]]
        pts = [(rows[k]["u"] + off[0], rows[k]["v"] + off[1]) for k in ks]
        m = greedy_match(pts, feet, MATCH_PX)
        m2 = greedy_match(pts, feet, 2 * MATCH_PX)
        td = tf - lag
        i = bisect.bisect_right(mv_t0, td) - 1
        gm_mv = i >= 0 and mv_iv[i][0] <= td < mv_iv[i][1]
        for idx, k in enumerate(ks):
            rows[k]["gm_moving"] = gm_mv
            rows[k]["hit"] = idx in m
            rows[k]["hit2"] = idx in m2
            if idx in m:
                j, dd = m[idx]
                dists.append(dd)
                b = boxes[j]
                box_h[SPECIES.get(world.job.get(rows[k]["g"], -1), "?")].append(b[3] - b[1])
    unmatched_boxes = sum(len(fb[tf][0]) for tf in fb) - len(dists)

    # 4) per window
    from flow_judge import heading_metrics

    out_w = []
    seen_aoi: set[Cell] = set()  # session-cumulative (a 60-min run re-crosses its own ground)
    seen_own: set[Cell] = set()
    scr_off = footprint_offsets(lambda o: proj.camera.project(np.asarray(o, dtype=float)))
    aoi_off = [(dx, dy) for dx in range(-AOI, AOI + 1) for dy in range(-AOI, AOI + 1)]
    appears = [e for e in events if e.get("type") == "entity_appear" and e.get("objtype") == 5]
    wk = proj.gat.walkable()

    def walkable(q: Cell) -> bool:
        return 0 <= q[0] < wk.shape[1] and 0 <= q[1] < wk.shape[0] and bool(wk[q[1], q[0]])

    fight, loot = busy_intervals(events)
    f_t0, l_t0 = [a for a, _b in fight], [a for a, _b in loot]
    for w0, w1 in wins:
        wr = [r_ for r_ in rows if w0 <= r_["t"] < w1 and r_["view"]]
        in_view = {r_["g"] for r_ in wr}
        detected = {r_["g"] for r_ in wr if r_.get("hit")}
        aoi_census = {g for g, ls in world.lives.items()
                      if any(a < w1 and (b is None or b > w0) for a, b, _ in ls)}  # fmt: skip
        # the GM's path, sampled every 0.1 s
        cells: list[Cell] = []
        for t in range(w0, w1, NS // 10):
            p = world.gm.at(t)
            if p is not None:
                c = (int(round(p[0])), int(round(p[1])))
                if not cells or cells[-1] != c:
                    cells.append(c)
        walked = sum(
            max(abs(a[0] - b[0]), abs(a[1] - b[1])) for a, b in zip(cells, cells[1:], strict=False)
        )
        own_new = len(set(cells) - seen_own)
        seen_own |= set(cells)
        aoi_cum = sweep(cells, aoi_off, seen_aoi, walkable)
        aoi_win = sweep(cells, aoi_off, set(), walkable)  # fresh in THIS window (sight's basis)
        scr_win = sweep(cells, scr_off, set(), walkable)
        # time split from packets (any actor), sampled every 0.1 s
        split: Counter[str] = Counter()
        samples: list[Pt | None] = []
        for t in range(w0, w1, NS // 10):
            p = world.gm.at(t)
            samples.append(p)
            if in_iv(fight, f_t0, t):
                split["fight"] += 1
            elif in_iv(loot, l_t0, t):
                split["loot"] += 1
            else:
                mv = in_iv(world.gm_moving, mv_t0, t)
                empty = p is None or not any(
                    world.alive_at(g, t) and (q := world.mobs[g].at(t)) is not None
                    and max(abs(q[0] - p[0]), abs(q[1] - p[1])) <= AOI
                    for g in world.mobs)  # fmt: skip
                split[
                    ("walk" if mv else "stand") + (" / AOI empty" if empty else " / mob in AOI")
                ] += 1
        n_s = max(1, sum(split.values()))
        disp = net_displacement(samples, 600)  # 60 s
        mins = (w1 - w0) / NS / 60
        # how each gid counted by flow_judge got in: its first appear in the window
        first: dict[int, Mapping[str, Any]] = {}
        for e in appears:
            if w0 <= int(e["t_mono_ns"]) < w1:
                first.setdefault(int(e["gid"]), e)
        how: Counter[str] = Counter()
        for g, e in first.items():
            t = int(e["t_mono_ns"])
            if world.alive_at(g, t - 1):
                how["in AOI before (walk re-sent)"] += 1
                continue
            i = bisect.bisect_right(mv_t0, t) - 1
            gm_mv = i >= 0 and mv_iv[i][0] <= t < mv_iv[i][1]
            how[f"{e.get('kind')} / GM {'moving' if gm_mv else 'standing'}"] += 1
        mv_share = sum(max(0, min(b, w1) - max(a, w0)) for a, b in world.gm_moving) / (w1 - w0)
        # density met: mobs alive inside the AOI / drawn on screen per detector frame
        nf = [f for f in frame_boxes if w0 <= f[0] < w1]
        aoi_per = sum(len(by_t.get(tf, ())) for tf, _f, _b in nf) / max(1, len(nf))
        scr_per = sum(1 for tf, _f, _b in nf for k in by_t.get(tf, ()) if rows[k]["view"]) \
            / max(1, len(nf))  # fmt: skip
        sight = sight_per_10min(events, w0, w1)
        out_w.append({
            "from_min": round((w0 - wins[0][0]) / NS / 60, 1),
            "sight_flow_judge": sight, "aoi_census": len(aoi_census),
            "in_view": len(in_view), "detected": len(detected), "kills": kills_in(events, w0, w1),
            "walked_cells_per_min": round(walked / mins, 1),
            "own_cells_new_to_session_per_min": round(own_new / mins, 1),
            "aoi_cells_swept_per_min": round(aoi_win / mins, 1),
            "aoi_cells_new_to_session_per_min": round(aoi_cum / mins, 1),
            "screen_cells_swept_per_min": round(scr_win / mins, 1),
            "aoi_cells_swept_per_cell_walked": round(aoi_win / max(1, walked), 1),
            "standing_share": round(1 - mv_share, 3),
            "reversals_per_min": heading_metrics(events, w0, w1)["reversals_per_min"],
            "mobs_in_aoi_per_frame": round(aoi_per, 2),
            "mobs_on_screen_per_frame": round(scr_per, 2),
            "entries_per_1000_swept_walkable": round(1000 * sight / 10 * mins / max(1, aoi_win),
                                                     2),
            "net_cells_per_60s_p50": pct(disp, 0.5),
            "time_split": {k: round(v / n_s, 3) for k, v in sorted(split.items())},
            "entered_how": dict(sorted(how.items())),
            "modes": mode_split(d, w0, w1),
        })  # fmt: skip

    # 5) detector recall, all windows pooled
    vw = [r_ for r_ in rows if r_["view"]]

    def rec(sel: Iterable[dict[str, Any]]) -> str:
        xs = list(sel)
        return rate(sum(1 for r_ in xs if r_.get("hit")), len(xs))

    by_ring = {ring_of(a): rec(r_ for r_ in vw if a <= r_["d"] <= b) for a, b in RINGS}
    by_species = {sp: rec(r_ for r_ in vw if SPECIES.get(world.job.get(r_["g"], -1)) == sp)
                  for sp in SPECIES.values()}  # fmt: skip
    by_gm = {"GM moving": rec(r_ for r_ in vw if r_["gm_moving"]),
             "GM standing": rec(r_ for r_ in vw if not r_["gm_moving"])}  # fmt: skip
    # the same within 2 x MATCH_PX: how much of the moving loss is our projection, not the boxes
    by_gm_2r = {k: rate(sum(1 for r_ in vw if r_["gm_moving"] == mv and r_.get("hit2")),
                        sum(1 for r_ in vw if r_["gm_moving"] == mv))
                for k, mv in (("GM moving", True), ("GM standing", False))}  # fmt: skip
    by_mob = {"mob walking": rec(r_ for r_ in vw if r_["mob_moving"]),
              "mob still": rec(r_ for r_ in vw if not r_["mob_moving"])}  # fmt: skip
    bands = ((0, 240), (240, 480), (480, 720))
    by_band = {f"v {a}-{b}": rec(r_ for r_ in vw if a <= r_["v"] < b) for a, b in bands}
    # visits: per gid, sorted in-view frames
    per_g: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r_ in vw:
        per_g[r_["g"]].append(r_)
    delays, n_vis, n_det, short = [], 0, 0, 0
    vis_by_len: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for xs in per_g.values():
        xs.sort(key=lambda r_: r_["t"])
        for i, j in visits([r_["t"] for r_ in xs]):
            seg = xs[i:j]
            n_vis += 1
            dur = (seg[-1]["t"] - seg[0]["t"]) / NS
            key = "<1 s" if dur < 1 else "1-3 s" if dur < 3 else "3-10 s" if dur < 10 else ">=10 s"
            vis_by_len[key][1] += 1
            first = next((r_ for r_ in seg if r_.get("hit")), None)
            if first is not None:
                n_det += 1
                vis_by_len[key][0] += 1
                delays.append((first["t"] - seg[0]["t"]) / NS)
            short += dur < 1
    det = {
        "frames_in_view": len(vw), "frame_recall": rec(vw), "by_ring": by_ring,
        "by_species": by_species, "by_gm": by_gm, "by_gm_within_2x_px": by_gm_2r, "by_mob": by_mob,
        "by_screen_band": by_band,
        "visits": rate(n_det, n_vis),
        "visits_by_length": {k: rate(*v) for k, v in sorted(vis_by_len.items())},
        "first_detection_delay_s": {"p50": pct(delays, 0.5), "p90": pct(delays, 0.9),
                                    "within_1s": rate(sum(x <= 1 for x in delays), n_vis)},
        "box_h_px_p50": {k: pct(v, 0.5) for k, v in sorted(box_h.items())},
        "match_px": {"p50": pct(dists, 0.5), "p90": pct(dists, 0.9)},
        "feet_offset_px": [round(off[0], 1), round(off[1], 1)],
        "boxes_unmatched": rate(unmatched_boxes, sum(len(fb[tf][0]) for tf in fb)),
    }  # fmt: skip
    fp = {"cells": len(scr_off), "dx": [min(o[0] for o in scr_off), max(o[0] for o in scr_off)],
          "dy": [min(o[1] for o in scr_off), max(o[1] for o in scr_off)],
          "beyond_aoi": sum(1 for o in scr_off if max(abs(o[0]), abs(o[1])) > AOI)}  # fmt: skip
    pop = len(world.lives)
    return {
        "session": sid,
        "actor": actor,
        "rule": man.get("rule"),
        "windows": out_w,
        "detector": det,
        "screen_footprint": fp,
        "map": {
            "mob_gids_in_session": pop,
            "walkable_cells": int(wk.sum()),
            "spawn_table_mobs": POPULATION,
            "spawn_table_per_1000_walkable": round(1000 * POPULATION / max(1, int(wk.sum())), 2),
        },
    }


# --- report ---------------------------------------------------------------------------------------


def _median(xs: Sequence[float]) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def report(res: Sequence[Mapping[str, Any]]) -> str:
    keys = ("sight_flow_judge", "aoi_census", "in_view", "detected", "kills",
            "walked_cells_per_min", "own_cells_new_to_session_per_min",
            "aoi_cells_swept_per_min", "aoi_cells_new_to_session_per_min",
            "screen_cells_swept_per_min", "aoi_cells_swept_per_cell_walked", "standing_share",
            "reversals_per_min", "mobs_in_aoi_per_frame", "mobs_on_screen_per_frame",
            "entries_per_1000_swept_walkable", "net_cells_per_60s_p50")  # fmt: skip
    lines = []
    for r_ in res:
        lines.append(f"== {r_['session']} ({r_['actor']}, {r_['rule']}), "
                     f"{len(r_['windows'])} x 10 min")  # fmt: skip
        lines.append("  window   " + " ".join(f"{w['from_min']:>6}" for w in r_["windows"])
                     + "  median")  # fmt: skip
        for k in keys:
            xs = [float(w[k]) for w in r_["windows"]]
            lines.append(f"  {k:<34}" + " ".join(f"{x:>6g}" for x in xs)
                         + f"  {_median(xs):>6g}")  # fmt: skip
        hows: Counter[str] = Counter()
        for w in r_["windows"]:
            hows.update(w["entered_how"])
        lines.append(
            "  entered how (all windows): "
            + ", ".join(f"{k} {v}" for k, v in sorted(hows.items(), key=lambda kv: -kv[1]))
        )
        names_ = sorted({k for w in r_["windows"] for k in w["time_split"]})
        lines.append("  time split from packets (median share): " + ", ".join(
            f"{n} {_median([w['time_split'].get(n, 0.0) for w in r_['windows']]):.2f}"
            for n in names_))  # fmt: skip
        modes = [w["modes"] for w in r_["windows"] if w["modes"]]
        if modes:
            names = sorted({k for m in modes for k in m})
            lines.append(
                "  modes (share of window, median): "
                + ", ".join(f"{n} {_median([m.get(n, 0.0) for m in modes]):.2f}" for n in names)
            )
        for k, v in r_["detector"].items():
            lines.append(f"  {k}: {v}")
        lines.append(f"  screen footprint: {r_['screen_footprint']}; map: {r_['map']}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    a_ = sub.add_parser("analyse")
    a_.add_argument("sessions", nargs="+")
    a_.add_argument("--json", type=Path)
    a = ap.parse_args()
    res = [analyse(s) for s in a.sessions]
    print(report(res))
    if a.json:
        a.json.write_text(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
