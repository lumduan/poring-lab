#!/usr/bin/env python3
"""Late strikes: the box target had already walked off when the client resolved the click
(rogue-xmas02.md Study S-LS; Batt 2026-11-10 night: "sometimes the bot has already picked a monster,
but it clicks at the moment the monster has already walked away"). ANALYSIS ONLY.

    late_strike.py score SESSION_DIR [SESSION_DIR ...] [--lag S] [--out OUT.json]
    late_strike.py fit-lag SESSION_DIR [SESSION_DIR ...] [--gat GAT]

OFFLINE ground truth only (packets, ADR-0007): nothing here reaches a runner. One clock: the
runner's ``t_ns``, the sniffer's ``t_mono_ns`` and the server's ticks are all bot-server's
CLOCK_MONOTONIC (ns / ns / ms).

Per BOX strike (a ``strike`` event with ``by`` "box", and the struck ``box_target`` logged just
before it):
- TIMES.
  - ``t_grab``: the box frame's grab -- the detection row (detections.jsonl) holding the struck box,
    its ``t_ns`` minus its ``ms``; without one, the box_target's time minus its
    ``verdict_from_grab_ms``, + GRAB_END_MS.
  - ``t_shown`` = ``t_grab`` - FRAME_LAG_S: the server time the grabbed picture shows (the stream's
    lag for monster sprites, fitted by ``fit-lag``: S-LS, 1,672 walking monsters, p40-p49).
  - ``t_click``: the strike's stamp (taken just before click_at's two motions and the click).
  - ``t_req``: the client's FIRST request after the stamp (a walk, attack or pickup request within
    REQ_WIN_S): the moment the client RESOLVED the click; with none, ``t_click`` + CLIENT_S.
- THE TARGET: among the monsters within TARGET_CELLS (Chebyshev) of the clicked cell at
  ``t_shown`` (our server cell then + the strike's ``rel``), the one an attack request of the click
  named (within OUTCOME_S), else the nearest.
- ITS MOTION: its position (interpolated along rAthena's path: diagonal first, a diagonal step x1.4)
  at ``t_shown`` (``seen``: what the box showed), ``t_grab``, ``t_click`` and ``t_req``; ``moved`` =
  Chebyshev(seen, at ``t_req``), in cells.
- LATE: ``moved`` >= LATE_CELLS (it had left the cell the box showed when the client resolved the
  click). Its KIND, by when the walk that carried it off began:
  - ``walking``: it was already walking at ``t_shown`` (the picture showed a walker);
  - ``unseen``: the walk began after ``t_shown`` but by ``t_grab`` (on the server, not yet drawn);
  - ``latency``: it began after ``t_grab`` (while the runner decided and the click travelled).
  ``move_start_s`` / ``move_start_click_s``: that walk's start, s after ``t_grab`` / ``t_click``.
- OUTCOME of the click (the packets within OUTCOME_S after ``t_click``, the strike's re-clicks
  included, as lock_study's classes): ``target`` (an attack request on the target), ``other`` (on
  another monster), ``walk`` (no attack request; the first request a walk), ``none``.
- LOST TIME (``add_lost``; failed clicks only, outcome ``walk`` / ``none``): from the click to our
  next attack request on ANY monster (capped at LOST_CAP_S), minus the click -> attack request a
  successful on-time strike of the same distance band takes (the run's median: the time it would
  have taken anyway). ``regain_s``: to the next attack request on THE TARGET (before it vanishes).
- STAGES (ms): ``detect`` (the grab -> the hover's first motion: detection + selection), ``hover``
  (-> the SWORD verdict: two motions + the cursor reads), ``pre_click`` (-> the strike's stamp: the
  event, a frame and the tag bank), ``client`` (-> the client's request: click_at's motions, the
  input path and the client), ``grab_to_req`` (the whole).
- PIXEL SIGNAL a runner has at decision time (``prev``): the same sprite's box (centre within
  PREV_MATCH_PX) in the runner's previous detection (at most PREV_MAX_S older); the foot's motion
  (px, px / s); ``scene_still``: our server cell unchanged between the two grabs. A walker flag
  needs a SETTLED camera (``settled_s``: our last walk ended this long before the previous grab;
  the client's camera glides for ~0.5 s after our walk ends).
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import json
import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

NS = 1_000_000_000
OUR_GID = 2000002  # the lab account's Rogue (fight_time.OUR_GID)
MONSTER_OBJTYPE = 5
OUR_SPEED_MS = 150  # the Rogue's ms a cell (no speed packet in these runs)
MOVE_COST, MOVE_DIAGONAL_COST = 10, 14  # rAthena path.hpp (poring_packets.world)
TICK_MOD = 1 << 32
FRAME_LAG_S = 0.16  # the picture shows the server this long before its grab (fit-lag, S-LS)
GRAB_END_MS = 21  # a detection's grab ends ~21 ms after the runner's stamp (S-LS: p50 20.7)
REQ_WIN_S = 1.2  # the client's first request after a click: this soon
CLIENT_S = 0.352  # the stamp -> the client's request, median of p40-p49's box strikes (S-LS)
TARGET_CELLS = 2.5  # the target: within this many cells of the clicked cell at t_shown
LATE_CELLS = 1.0  # moved this far between the picture and the client's resolve = late
OUTCOME_S = 2.0  # lock_study's REQ_S: an attack request this soon after the click is the click's
LOST_CAP_S = 30.0
PREV_MAX_S = 1.5  # the runner's previous detection: at most this much older than the box's own
PREV_MATCH_PX = 60.0  # the same sprite: its box centre within this of the box's
WALKER_PX = 10.0  # S-LS's walker flag: the foot moved this far between two settled detections
SETTLED_S = 0.5  # ... and our own last walk ended at least this long before the earlier one
MOVED_BINS = (0.0, 0.5, 1.0, 1.5, 2.0, 3.0)  # the summary's P(target | moved) bins (cells)
REQUEST_TYPES = ("self_move_request", "attack_request", "pickup_request")
FAILED = ("walk", "none")


def ticks_since(tick: int, start: int) -> int:
    """PURE: ``tick - start`` on the server's 2^32 ms clock, signed."""
    d = (tick - start) % TICK_MOD
    return d - TICK_MOD if d >= TICK_MOD // 2 else d


def path_cells(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    """PURE: rAthena's fallback path (diagonal steps first, then straight): the cells after the
    start (poring_packets.world.path_cells, the same rule)."""
    out: list[tuple[int, int]] = []
    x, y = x0, y0
    while (x, y) != (x1, y1):
        x, y = x + (x1 > x) - (x1 < x), y + (y1 > y) - (y1 < y)
        out.append((x, y))
    return out


@dataclass(frozen=True)
class Seg:
    """One record of a unit's track. From ``t_rx`` (the packet's arrival) on, it stands at (x0, y0)
    (``kind`` "stand"), walks from (x0, y0) to (x1, y1) from ``t_start`` at ``speed`` ms a cell
    ("move"), or is gone ("gone"; ``x1`` = the vanish reason)."""

    t_rx: int
    kind: str
    x0: int
    y0: int
    x1: int = 0
    y1: int = 0
    t_start: int = 0
    speed: float = 0.0
    job: int = 0
    name: str = ""

    def step_ms(self, a: tuple[float, float], b: tuple[int, int]) -> float:
        diag = a[0] != b[0] and a[1] != b[1]
        return self.speed * (MOVE_DIAGONAL_COST if diag else MOVE_COST) / MOVE_COST

    def duration_ns(self) -> int:
        """PURE: a walk's length in ns (0 for a stand)."""
        if self.kind != "move":
            return 0
        total, here = 0.0, (float(self.x0), float(self.y0))
        for c in path_cells(self.x0, self.y0, self.x1, self.y1):
            total += self.step_ms(here, c)
            here = (float(c[0]), float(c[1]))
        return int(total * 1e6)

    def at(self, t: int) -> tuple[float, float, bool]:
        """PURE: (x, y, walking) at ``t`` (ns), interpolated along the path."""
        if self.kind != "move":
            return float(self.x0), float(self.y0), False
        el = (t - self.t_start) / 1e6  # ms
        if el <= 0:
            return float(self.x0), float(self.y0), True
        x, y = float(self.x0), float(self.y0)
        for c in path_cells(self.x0, self.y0, self.x1, self.y1):
            step = self.step_ms((x, y), c)
            if el < step:
                f = el / step
                return x + (c[0] - x) * f, y + (c[1] - y) * f, True
            el -= step
            x, y = float(c[0]), float(c[1])
        return float(self.x1), float(self.y1), False


Track = list[Seg]


def _start_ns(p: dict[str, Any], tick_key: str) -> int:
    """PURE: a walk's start on the ns clock from its server tick (wrap-safe against its arrival)."""
    t = int(p["t_mono_ns"])
    tick = p.get(tick_key)
    if tick is None:
        return t
    return t - ticks_since((t // 1_000_000) % TICK_MOD, int(tick)) * 1_000_000


def tracks(packets: Sequence[dict[str, Any]],
           our_gid: int = OUR_GID) -> tuple[dict[int, Track], Track]:  # fmt: skip
    """PURE: the monsters' tracks (gid -> segments in arrival order) and ours, from the packets in
    time order: entity_appear (stand / move; monsters only), entity_stop, entity_vanish; for us,
    self_move (OUR_SPEED_MS a cell), our own entity_stop and map_change."""
    mobs: dict[int, Track] = defaultdict(list)
    ours: Track = []
    meta: dict[int, tuple[int, str, float]] = {}
    for p in sorted(packets, key=lambda q: int(q.get("t_mono_ns") or 0)):
        typ, t, gid = p.get("type"), p.get("t_mono_ns"), p.get("gid")
        if not isinstance(t, int):
            continue
        if typ == "entity_appear" and p.get("objtype") == MONSTER_OBJTYPE and gid is not None:
            meta[gid] = (int(p.get("job") or 0), str(p.get("name") or ""),
                         float(p.get("speed") or 200))  # fmt: skip
            job, name, sp = meta[gid]
            if p.get("kind") == "move" and p.get("x1") is not None:
                mobs[gid].append(Seg(t, "move", int(p["x"]), int(p["y"]), int(p["x1"]),
                                     int(p["y1"]), _start_ns(p, "move_start_tick"), sp, job,
                                     name))  # fmt: skip
            else:
                mobs[gid].append(Seg(t, "stand", int(p["x"]), int(p["y"]), speed=sp, job=job,
                                     name=name))  # fmt: skip
        elif typ == "entity_stop" and gid == our_gid:
            ours.append(Seg(t, "stand", int(p["x"]), int(p["y"])))
        elif typ == "entity_stop" and gid in mobs:
            job, name, sp = meta[gid]
            mobs[gid].append(Seg(t, "stand", int(p["x"]), int(p["y"]), speed=sp, job=job,
                                 name=name))  # fmt: skip
        elif typ == "entity_vanish" and gid in mobs:
            mobs[gid].append(Seg(t, "gone", 0, 0, x1=int(p.get("reason") or 0)))
        elif typ == "self_move":
            ours.append(Seg(t, "move", int(p["x0"]), int(p["y0"]), int(p["x1"]), int(p["y1"]),
                            _start_ns(p, "server_tick"), float(OUR_SPEED_MS)))  # fmt: skip
        elif typ == "map_change":
            ours.append(Seg(t, "stand", int(p["x"]), int(p["y"])))
    return dict(mobs), ours


def seg_at(track: Track, t: int) -> Seg | None:
    """PURE: the segment in force at ``t`` (the last one that arrived at or before it)."""
    i = bisect.bisect_right([s.t_rx for s in track], t) - 1
    return None if i < 0 else track[i]


def pos_at(track: Track, t: int) -> tuple[float, float, bool] | None:
    """PURE: (x, y, walking) at ``t``; None before the first record or once gone."""
    s = seg_at(track, t)
    if s is None or s.kind == "gone":
        return None
    return s.at(t)


def cheb(a: Sequence[float], b: Sequence[float]) -> float:
    """PURE: the Chebyshev distance (cells)."""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def moves_between(track: Track, t0: int, t1: int) -> list[Seg]:
    """PURE: the walks in force at some instant of (t0, t1]: the one at t0 (if still walking) and
    every move that arrived inside the span, in order."""
    out = []
    s0 = seg_at(track, t0)
    if s0 is not None and s0.kind == "move" and s0.at(t0)[2]:
        out.append(s0)
    out += [s for s in track if s.kind == "move" and t0 < s.t_rx <= t1]
    return out


def last_walk_end(track: Track, t: int) -> int | None:
    """PURE: when our last walk that began by ``t`` ended (its start + its length), or None."""
    mv = [s for s in track if s.kind == "move" and s.t_start <= t]
    return None if not mv else mv[-1].t_start + mv[-1].duration_ns()


def requests(packets: Sequence[dict[str, Any]]) -> list[tuple[int, str, Any]]:
    """PURE: the client's requests (t, type, target: a gid / a cell / a floor id), in time order."""
    out = []
    for p in packets:
        typ = p.get("type")
        if typ in REQUEST_TYPES and isinstance(p.get("t_mono_ns"), int):
            tgt: Any = p.get("floor_id")
            if typ == "attack_request":
                tgt = p.get("target_gid")
            elif typ == "self_move_request":
                tgt = (p.get("x"), p.get("y"))
            out.append((int(p["t_mono_ns"]), str(typ), tgt))
    return sorted(out, key=lambda r: r[0])


def band(dist: int) -> str:
    """PURE: a strike's distance band (lock_study / 4AC's): 0-1, 2-3, 4-6, 7-8, 9+."""
    return "0-1" if dist <= 1 else "2-3" if dist <= 3 else "4-6" if dist <= 6 else \
        "7-8" if dist <= 8 else "9+"  # fmt: skip


def pick_target(mobs: dict[int, Track], cell: Sequence[float], t: int,
                attacked: Sequence[int] = (),
                within: float = TARGET_CELLS) -> tuple[int, float] | None:  # fmt: skip
    """PURE: (gid, distance) of the strike's target among the monsters alive at ``t`` within
    ``within`` cells of ``cell``: one the click attacked (``attacked``, in order) wins, else the
    nearest (the lower gid on a tie)."""
    near: dict[int, float] = {}
    for gid, tr in mobs.items():
        p = pos_at(tr, t)
        if p is not None and cheb(p, cell) <= within:
            near[gid] = cheb(p, cell)
    for g in attacked:
        if g in near:
            return g, near[g]
    if not near:
        return None
    g = min(near, key=lambda k: (near[k], k))
    return g, near[g]


def late_kind(track: Track, t_shown: int, t_grab: int, t_req: int, moved: float,
              late_cells: float = LATE_CELLS) -> tuple[str | None, int | None]:  # fmt: skip
    """PURE: (kind, the start ns of the first walk in force over (t_shown, t_req]) for a target that
    moved ``moved`` cells: kind None when not late; "walking" when it walked at ``t_shown``;
    "unseen" when that walk began by ``t_grab``; "latency" when after."""
    mv = moves_between(track, t_shown, t_req)
    start = mv[0].t_start if mv else None
    if moved < late_cells:
        return None, start
    s0 = seg_at(track, t_shown)
    if s0 is not None and s0.kind == "move" and s0.at(t_shown)[2]:
        return "walking", start
    if start is None:
        return "latency", None  # it moved with no walk record in the span (not seen in S-LS)
    return ("unseen" if start <= t_grab else "latency"), start


def prev_box(dets: Sequence[dict[str, Any]], box: Sequence[float], t_grab: int,
             max_s: float = PREV_MAX_S,
             match_px: float = PREV_MATCH_PX) -> dict[str, Any] | None:  # fmt: skip
    """PURE: the runner's latest detection grabbed 30 ms .. ``max_s`` before ``t_grab``, and in it
    the monster box whose centre is nearest the box's (within ``match_px``): {"dt_s", "t_prev",
    "match", "foot_dx", "foot_dy", "px" (the foot's motion), "px_s", "c_px", "c_px_s" (the
    centre's), "dsize"}; None without such a detection."""
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    prev = [d for d in dets
            if t_grab - max_s * NS <= int(d["t_ns"]) - float(d.get("ms") or 0) * 1e6
            < t_grab - 30_000_000]  # fmt: skip
    if not prev:
        return None
    d = prev[-1]
    tp = int(d["t_ns"] - float(d.get("ms") or 0) * 1e6)
    dt = (t_grab - tp) / NS
    best = None
    for b in d.get("boxes") or []:
        if len(b) > 5 and b[5] != "monster":
            continue
        dd = math.hypot((b[0] + b[2]) / 2 - cx, (b[1] + b[3]) / 2 - cy)
        if dd <= match_px and (best is None or dd < best[0]):
            best = (dd, b)
    if best is None:
        return {"dt_s": round(dt, 3), "t_prev": tp, "match": False}
    b = best[1]
    dx, dy = cx - (b[0] + b[2]) / 2, box[3] - b[3]
    px = math.hypot(dx, dy)
    return {"dt_s": round(dt, 3), "t_prev": tp, "match": True, "foot_dx": round(dx, 1),
            "foot_dy": round(dy, 1), "px": round(px, 1), "px_s": round(px / dt, 1),
            "c_px": round(best[0], 1), "c_px_s": round(best[0] / dt, 1),
            "dsize": round(abs((box[2] - box[0]) - (b[2] - b[0]))
                           + abs((box[3] - box[1]) - (b[3] - b[1])), 1)}  # fmt: skip


def walker_flag(prev: dict[str, Any] | None, min_px: float = WALKER_PX,
                settled_s: float = SETTLED_S) -> bool | None:  # fmt: skip
    """PURE: S-LS's pixel walker flag: the matched box's foot moved >= ``min_px`` between two
    detections on a settled camera; None when it cannot be judged (no match, the scene scrolled,
    or our walk ended < ``settled_s`` before the earlier grab)."""
    if not prev or not prev.get("match") or not prev.get("scene_still"):
        return None
    if prev.get("settled_s") is not None and prev["settled_s"] < settled_s:
        return None
    return float(prev["px"]) >= min_px


def det_grab(dets: Sequence[dict[str, Any]], box: Sequence[float], before: int,
             within_s: float = 3.0) -> int | None:  # fmt: skip
    """PURE: the grab (``t_ns`` - ``ms``) of the latest detection logged before ``before`` (within
    ``within_s``) that holds ``box`` (to 0.1 px), or None."""
    key = tuple(round(float(x), 1) for x in box[:4])
    for d in reversed(dets):
        t = int(d["t_ns"])
        if t >= before:
            continue
        if before - t > within_s * NS:
            return None
        if any(tuple(round(float(x), 1) for x in b[:4]) == key for b in d.get("boxes") or []):
            return int(t - float(d.get("ms") or 0) * 1e6)
    return None


def strike_grab(bt: Mapping[str, Any], dets: Sequence[dict[str, Any]], t_click: int
                ) -> tuple[int, str, str | None]:  # fmt: skip
    """PURE: the grab a box strike's click is judged from, its source and the hold's end. Today's
    strike: the struck box's detection (else the runner's stamp + GRAB_END_MS). A strike HELD by
    --still-target (dungeon@9.23, LS-2; rogue-xmas02.md 4BO) clicked the hold's LAST matched box
    (``press.box_end``), so its grab is that box's detection before the click, else D1's grab +
    ``press.end_gap_ms``."""
    t_stamp = int(bt["t_ns"] - float(bt["verdict_from_grab_ms"]) * 1e6)  # the runner's grab
    press = bt.get("press") or {}
    end = press.get("end")
    t_grab = det_grab(dets, bt["box"], int(bt["t_ns"])) if bt.get("box") else None
    src = "runner" if t_grab is None else "detection"
    if t_grab is None:
        t_grab = t_stamp + GRAB_END_MS * 1_000_000
    if end == "still" and press.get("box_end"):
        t_end = det_grab(dets, press["box_end"], t_click)
        if t_end is not None:
            return t_end, "hold_detection", end
        if press.get("end_gap_ms") is not None:
            return t_grab + int(float(press["end_gap_ms"]) * 1e6), "hold_gap", end
    return t_grab, src, end


def _xy(p: tuple[float, float, bool] | None) -> list[float] | None:
    return None if p is None else [round(p[0], 2), round(p[1], 2)]


def strike_rows(events: Sequence[dict[str, Any]], packets: Sequence[dict[str, Any]],
                dets: Sequence[dict[str, Any]] = (), lag_s: float = FRAME_LAG_S,
                our_gid: int = OUR_GID) -> list[dict[str, Any]]:  # fmt: skip
    """PURE: one record per box strike (the module's docstring), in time order; ``lost_s`` comes
    from ``add_lost``."""
    mobs, ours = tracks(packets, our_gid)
    reqs = requests(packets)
    req_t = [r[0] for r in reqs]
    attacks = [r for r in reqs if r[1] == "attack_request"]
    t0 = next((int(e["t_ns"]) for e in events if e.get("kind") == "run_start"), None)
    rows: list[dict[str, Any]] = []
    for i, st in enumerate(events):
        if st.get("kind") != "strike" or st.get("by") != "box":
            continue
        t_click = int(st["t_ns"])
        bt = next((b for b in reversed(events[:i]) if b.get("kind") == "box_target"
                   and b.get("struck") and t_click - int(b["t_ns"]) <= 2 * NS), None)  # fmt: skip
        if bt is None or bt.get("verdict_from_grab_ms") is None:
            continue
        t_stamp = int(bt["t_ns"] - float(bt["verdict_from_grab_ms"]) * 1e6)  # the runner's grab
        t_grab, grab_src, press_end = strike_grab(bt, dets, t_click)
        t_shown = t_grab - int(lag_s * NS)
        j = bisect.bisect_right(req_t, t_click)
        first = reqs[j] if j < len(reqs) and reqs[j][0] - t_click <= REQ_WIN_S * NS else None
        t_req = first[0] if first is not None else t_click + int(CLIENT_S * NS)
        rel = [int(v) for v in st.get("rel") or (0, 0)]
        dist = max(abs(rel[0]), abs(rel[1]))
        hfg = bt.get("hover_from_grab_ms")
        rec: dict[str, Any] = {
            "t_s": None if t0 is None else round((t_click - t0) / NS, 2), "t_ns": t_click,
            "rel": rel, "dist": dist, "band": band(dist), "end": st.get("end"),
            "clicks": st.get("clicks"), "grab_src": grab_src, "press_end": press_end,
            "first_req": None if first is None else first[1],
            "first_req_to": None if first is None or first[1] != "self_move_request"
            else list(first[2]),
            "stages_ms": {
                "detect": hfg,
                "hover": None if hfg is None else round(float(bt["verdict_from_grab_ms"]) - hfg),
                "pre_click": round((t_click - int(bt["t_ns"])) / 1e6),
                "client": None if first is None else round((first[0] - t_click) / 1e6),
                "grab_to_req": round((t_req - t_stamp) / 1e6)},
            "still": bt.get("still"), "settle_ms": bt.get("settle_ms"),
            "still_wait_ms": bt.get("still_wait_ms"), "target": None, "outcome": None,
            "late": None, "late_kind": None, "moved": None}  # fmt: skip
        me = pos_at(ours, t_shown)
        if me is None:
            rows.append(rec)
            continue
        cell = (round(me[0]) + rel[0], round(me[1]) + rel[1])
        att = [r for r in attacks if t_click <= r[0] <= t_click + OUTCOME_S * NS]
        rec.update(me=_xy(me), me_walking=me[2])
        tgt = pick_target(mobs, cell, t_shown, [r[2] for r in att])
        if tgt is None:
            rec["outcome"] = "other" if att else "none" if first is None else \
                "walk" if first[1] == "self_move_request" else str(first[1])  # fmt: skip
            rows.append(rec)
            continue
        gid, dcell = tgt
        tr = mobs[gid]
        seen, at_req = pos_at(tr, t_shown), pos_at(tr, t_req)
        seg = seg_at(tr, t_shown)
        moved = None if seen is None or at_req is None else round(cheb(seen, at_req), 2)
        kind, start = late_kind(tr, t_shown, t_grab, t_req, 99.0 if moved is None else moved)
        on_t = [r for r in att if r[2] == gid]
        outcome = "target" if on_t else "other" if att else "none" if first is None else \
            "walk" if first[1] == "self_move_request" else str(first[1])  # fmt: skip
        nxt_any = next((r[0] for r in attacks if r[0] > t_click), None)
        gone = next((s.t_rx for s in tr if s.kind == "gone" and s.t_rx > t_click), None)
        nxt_tgt = next((r[0] for r in attacks if r[0] > t_click and r[2] == gid
                        and (gone is None or r[0] <= gone)), None)  # fmt: skip
        rec.update(
            target=gid, species=None if seg is None else seg.name,
            job=None if seg is None else seg.job, target_d=round(dcell, 2),
            seen=_xy(seen), at_grab=_xy(pos_at(tr, t_grab)), at_click=_xy(pos_at(tr, t_click)),
            at_req=_xy(at_req), walking_shown=None if seen is None else seen[2],
            walking_req=None if at_req is None else at_req[2], moved=moved,
            late=moved is not None and kind is not None, late_kind=kind,
            move_start_s=None if start is None else round((start - t_grab) / NS, 3),
            move_start_click_s=None if start is None else round((start - t_click) / NS, 3),
            outcome=outcome,
            attack_s=None if not on_t else round((on_t[0][0] - t_click) / NS, 2),
            next_attack_s=None if nxt_any is None else round((nxt_any - t_click) / NS, 2),
            regain_s=None if nxt_tgt is None or on_t else round((nxt_tgt - t_click) / NS, 2),
            req_to_target=None if first is None or first[1] != "self_move_request"
            or at_req is None else round(cheb(first[2], at_req), 2))  # fmt: skip
        pv = prev_box(dets, bt["box"], t_grab) if dets and bt.get("box") else None
        if pv is not None and pv.get("match"):
            a_, b_ = pos_at(ours, pv["t_prev"]), pos_at(ours, t_grab)
            pv["scene_still"] = (a_ is not None and b_ is not None and not a_[2] and not b_[2]
                                 and cheb(a_, b_) < 0.5)  # fmt: skip
            end_ = last_walk_end(ours, pv["t_prev"])
            pv["settled_s"] = None if end_ is None else round((pv["t_prev"] - end_) / NS, 2)
        rec["prev"] = pv
        rec["walker_flag"] = walker_flag(pv)
        rows.append(rec)
    return rows


def add_lost(rows: list[dict[str, Any]],
             baseline: dict[str, float] | None = None) -> dict[str, float]:  # fmt: skip
    """PURE (in place): each row's ``lost_s`` -- a failed click (outcome walk / none, with a
    target) loses the time to our next attack request on any monster (capped at LOST_CAP_S) minus
    the baseline of its band; any other row 0. ``baseline``: band -> s; default the rows' own median
    ``attack_s`` of successful on-time strikes per band. Returns the baseline used."""
    if baseline is None:
        by: dict[str, list[float]] = defaultdict(list)
        for r in rows:
            if r.get("outcome") == "target" and r.get("late") is False \
                    and r.get("attack_s") is not None:  # fmt: skip
                by[r["band"]].append(float(r["attack_s"]))
        baseline = {k: round(statistics.median(v), 2) for k, v in by.items()}
    for r in rows:
        if r.get("outcome") in FAILED and r.get("target") is not None:
            dead = LOST_CAP_S if r.get("next_attack_s") is None else \
                min(LOST_CAP_S, float(r["next_attack_s"]))  # fmt: skip
            r["lost_s"] = round(max(0.0, dead - baseline.get(r["band"], 0.0)), 2)
        else:
            r["lost_s"] = 0.0
    return baseline


def _p50(v: Sequence[float]) -> float | None:
    return None if not v else round(float(statistics.median(v)), 2)


def summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """PURE: one run's (or a pool's) counts: outcomes, the late strikes by kind and outcome, their
    lost time, P(target | moved), the stage medians late vs on time, by species, the walker flag."""
    tg = [r for r in rows if r.get("target") is not None and r.get("moved") is not None]
    late = [r for r in tg if r.get("late")]
    ontime = [r for r in tg if r.get("late") is False]
    lf = [r for r in late if r["outcome"] in FAILED]
    of = [r for r in ontime if r["outcome"] in FAILED]
    hit_by_moved = {}
    edges = (*MOVED_BINS, math.inf)
    for lo, hi in zip(edges, edges[1:], strict=False):
        sel = [r for r in tg if lo <= float(r["moved"]) < hi]
        hit_by_moved[f"{lo}-{hi}"] = [len(sel), sum(1 for r in sel if r["outcome"] == "target")]
    stages = {}
    keys = ("detect", "hover", "pre_click", "client", "grab_to_req")
    for name, sel in (("late", late), ("ontime", ontime)):
        stages[name] = {k: _p50([r["stages_ms"][k] for r in sel
                                 if r["stages_ms"].get(k) is not None]) for k in keys}  # fmt: skip
    species: dict[str, list[int]] = {}
    for r in tg:
        s = species.setdefault(str(r.get("species")), [0, 0, 0])
        s[0] += 1
        s[1] += bool(r.get("late"))
        s[2] += bool(r.get("late")) and r["outcome"] in FAILED
    flags: Counter[str] = Counter()
    lf_ids = {id(r) for r in lf}
    for r in tg:
        f = r.get("walker_flag")
        if f is not None:
            key = "flag" if f else "noflag"
            flags[f"{key}:{'walking' if r['walking_shown'] else 'standing'}"] += 1
            flags[f"{key}:{'late_failed' if id(r) in lf_ids else 'other'}"] += 1
    return {
        "box_strikes": len(rows), "targeted": len(tg),
        "no_target": sum(1 for r in rows if r.get("target") is None),
        "outcomes": dict(Counter(str(r.get("outcome")) for r in rows)),
        "late": len(late), "late_share": round(len(late) / len(tg), 3) if tg else None,
        "late_kinds": dict(Counter(str(r["late_kind"]) for r in late)),
        "late_outcomes": dict(Counter(r["outcome"] for r in late)),
        "late_failed": len(lf), "late_lost_s": round(sum(r.get("lost_s", 0.0) for r in lf), 1),
        "late_lost_p50_s": _p50([r.get("lost_s", 0.0) for r in lf]),
        "ontime_failed": len(of),
        "ontime_lost_s": round(sum(r.get("lost_s", 0.0) for r in of), 1),
        "walking_at_frame": sum(1 for r in tg if r.get("walking_shown")),
        "hit_by_moved": hit_by_moved, "stages_ms_p50": stages, "species": species,
        "move_start_s_p50": {k: _p50([r["move_start_s"] for r in late if r["late_kind"] == k
                                      and r.get("move_start_s") is not None])
                             for k in ("walking", "unseen", "latency")},  # fmt: skip
        "walker_flag": dict(sorted(flags.items())),
    }  # fmt: skip


def lag_profile(dets: Sequence[dict[str, Any]], mobs: dict[int, Track], ours: Track,
                project: Callable[[Sequence[float], tuple[int, int]], tuple[float, float]],
                lags: Sequence[float], still_s: float = 1.5, moved_min: float = 1.0,
                window_s: float = 1.0,
                max_px: float = 40.0) -> dict[float, list[float]]:  # fmt: skip
    """PURE: for ``fit-lag``. Every detection on a standing camera (our server cell unchanged and
    no walk of ours over the ``still_s`` before its grab), every monster within view that moved >=
    ``moved_min`` cells over the ``window_s`` before the grab: for each lag L, the pixel distance
    from its projected foot at grab - L (``project(offset cells, our cell)``) to the nearest
    monster box's foot. Pairs whose best distance exceeds ``max_px`` are left out (no box)."""
    out: dict[float, list[float]] = {float(lag): [] for lag in lags}
    for d in dets:
        tg = int(d["t_ns"] - float(d.get("ms") or 0) * 1e6)
        feet = [((b[0] + b[2]) / 2, b[3]) for b in d.get("boxes") or []
                if len(b) <= 5 or b[5] == "monster"]  # fmt: skip
        a, b = pos_at(ours, tg - int(still_s * NS)), pos_at(ours, tg)
        if not feet or a is None or b is None or a[2] or b[2] or cheb(a, b) > 0:
            continue
        if moves_between(ours, tg - int(still_s * NS), tg):
            continue
        me = (int(b[0]), int(b[1]))
        for tr in mobs.values():
            p0, p1 = pos_at(tr, tg), pos_at(tr, tg - int(window_s * NS))
            if p0 is None or p1 is None or abs(p0[0] - me[0]) > 12 or abs(p0[1] - me[1]) > 10:
                continue
            if cheb(p0, p1) < moved_min:
                continue
            row = []
            for lag in lags:
                q = pos_at(tr, tg - int(lag * NS))
                if q is None:
                    break
                u, v = project((q[0] - me[0], q[1] - me[1]), me)
                row.append(min(math.hypot(fx - u, fy - v) for fx, fy in feet))
            if len(row) == len(lags) and min(row) <= max_px:
                for lag, e in zip(lags, row, strict=True):
                    out[float(lag)].append(e)
    return out


def load(session: Path) -> tuple[list[Any], list[Any], list[Any]]:
    def jl(name: str) -> list[dict[str, Any]]:
        p = session / name
        return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() \
            else []  # fmt: skip

    with gzip.open(session / "packets.jsonl.gz", "rt") as fh:
        packets = sorted((json.loads(x) for x in fh if x.strip()), key=lambda p: p["t_mono_ns"])
    return jl("events.jsonl"), packets, jl("detections.jsonl")


def fit_lag(sessions: Sequence[Path], gat_path: Path) -> dict[str, Any]:
    """The lag fit over ``sessions`` with the runner's own camera (camera_rdp.json) and the map's
    GAT altitudes (client-derived run-time data in /dev/shm, never committed)."""
    import numpy as np

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    root = Path(__file__).resolve().parents[1]
    cj = json.loads((root / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    camera = cam.camera_from_json(cj["camera"])
    gat = gatmod.parse(gat_path.read_bytes())

    def project(off: Sequence[float], me: tuple[int, int]) -> tuple[float, float]:
        rel = np.asarray([off], dtype=float)
        uv = camera.project(rel, gat.relative_altitude(me, rel))[0]
        return float(uv[0]), float(uv[1])

    lags = [round(0.025 * i, 3) for i in range(17)]
    pooled: dict[float, list[float]] = {lag: [] for lag in lags}
    for s in sessions:
        ev, pk, det = load(s)
        mobs, ours = tracks(pk)
        for lag, v in lag_profile(det, mobs, ours, project, lags).items():
            pooled[lag] += v
    prof = {str(lag): {"n": len(v), "median_px": _p50(v)} for lag, v in pooled.items()}
    best = min((lag for lag in lags if pooled[lag]), key=lambda lag: statistics.median(pooled[lag]))
    return {"sessions": [s.name for s in sessions], "profile": prof, "best_lag_s": best}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("score", help="the late-strike records and summary of each session")
    sc.add_argument("sessions", type=Path, nargs="+")
    sc.add_argument("--lag", type=float, default=FRAME_LAG_S)
    sc.add_argument("--out", type=Path, default=None, help="every row of every session (JSON)")
    fl = sub.add_parser("fit-lag", help="fit FRAME_LAG_S (needs the map's GAT, run-time data)")
    fl.add_argument("sessions", type=Path, nargs="+")
    fl.add_argument(
        "--gat", type=Path, default=Path("/dev/shm/poring-lab-tmp/gat/data/xmas_dun02.gat")
    )
    a = ap.parse_args(argv)
    if a.cmd == "fit-lag":
        print(json.dumps(fit_lag(a.sessions, a.gat)))
        return 0
    allrows: dict[str, list[dict[str, Any]]] = {}
    pooled: list[dict[str, Any]] = []
    for s in a.sessions:
        ev, pk, det = load(s)
        rows = strike_rows(ev, pk, det, lag_s=a.lag)
        base = add_lost(rows)
        allrows[s.name] = rows
        pooled += rows
        print(json.dumps({"session": s.name, "baseline_attack_s": base, **summary(rows)}))
    if len(a.sessions) > 1:
        print(json.dumps({"pooled": len(a.sessions), **summary(pooled)}))
    if a.out is not None:
        a.out.write_text(json.dumps(allrows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
