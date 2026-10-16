#!/usr/bin/env python3
"""hunt-flow@N (Batt 2026-10-16): CLICK -> WALK IN -> HIT LANDS, fast, like Batt played it. Killing
does not matter; reaction does. The bar: a hit within W = 5.0 s of the first attack click, re-clicks
allowed, >= 95 % over >= 60 engagements (docs/demonstrations.md 3.41; the judge is flow_judge.py).

    hunt_flow.py run --version 1 [--minutes 30] [--seed S]   LIVE (RDP, the GM, ASSIST)

THE LOOP (3.41; parameters from Batt's 10-minute demonstration, 3.40.1)
- WALK CONTINUOUSLY: a coverage route (hunt's search area and planner). While the GM walks, a click
  every WALK_EVERY_S to the path cell ~AHEAD cells ahead (gated by the map and the detector: 3.39
  deviation (2) option B). A click from a standstill is cursor-gated (robust2 WALK). The minimap
  corrects the reckoning; hunt@8's unstick routes around clicks the client does not follow.
- TRACK every fresh detector frame (hunt@6's selection gates) into tracks of cells (predicted at
  constant velocity); a track unseen TRACK_DROP_S is dropped.
- QUEUE + STEER: the nearest track; the route is re-aimed toward a cell SHORT cells short of its
  predicted cell, every WALK_EVERY_S.
- STRIKE at the brief moment the walk ends, if the target is <= STRIKE_CELLS away: park, hover the
  target's newest box, ONE robust2 read; SWORD -> the attack click there (as hunt@6). The SWORD read
  is the only separator from an NPC drawn like a monster (the Poring War Recruiter).
- AFTER THE CLICK: dead (pixels: no target box near its last cell for DEAD_GONE_S) -> the next
  target at once; still there after RECLICK_S -> a re-click; give up at GIVE_UP_S. No looting.
- Stops (none retried): any UI state but clear (the gate's pixel check every CHECK_EVERY_S), HP
  below 75 %, Batt's takeover, the mux leaving ASSIST, an unknown own cell, no progress for STUCK_S.
Packets are never read here (rule 1): flow_judge.py reads them afterwards.
"""

from __future__ import annotations

import argparse
import bisect
import contextlib
import json
import math
import sys
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import farm0 as f0  # noqa: E402
import farm1 as f1  # noqa: E402
import hunt_core as hc  # noqa: E402
import ro_agent as r  # noqa: E402

RULE = "hunt-flow"
MAP = "prt_fild08"
START = (268, 107)
OUT = Path("/dev/shm/poring-lab-tmp/hunt-flow")  # logs (small)
REC_ROOT = Path("/mnt/poring-lab-datasets/hunt-recordings")  # the 5 Hz frames (NAS, q80)
REC_QUALITY = 80
REC_HZ = 5.0
CHECK_EVERY_S = 30.0
WEIGHT_EVERY_S = 120.0
MINIMAP_EVERY_S = 0.3
JUMP_CELLS = 12  # v7: a minimap read this far from the measured cell, twice: a map change
MINIMAP_IMG = (1138, 21, 124, 120)  # v9 attempt 2: the minimap's picture (client px)
MAP_SAME_MAX = 20.0  # median summed |diff| of the picture: the same map stays far below
FREEZE_S = 3.0  # v10: identical frames this long after a walk click = a frozen client display
GM_SPRITE_PX = (640.0, 340.0)  # v10: the GM's sprite centre (client px; the camera centres on it)
DRIFT_CELLS = 3
STUCK_S = 60.0
MS_CELL = 150.0  # the GM's measured walk speed (hunt@5's packets)
Cell = tuple[int, int]

VERSIONS = {
    1: "HUNT-FLOW (Batt's play, 3.40.1): walk continuously (a click ~6 cells ahead every ~0.8 s); "
    "track every monster box; the nearest first; steer to 2 cells short of its predicted cell; "
    "at the brief moment the walk ends, <= 3 cells: ONE robust2 SWORD read on its newest box -> "
    "the attack click; dead from pixels -> the next target at once; no looting",
    2: "PIPELINED (Batt 2026-10-16 ~11:30): PERCEPTION (detector + tracker) and the PLANNER (a "
    "2-4 deep queue by the shortest CHAINED path, standing targets first, re-scored every "
    "frame; the next exploration waypoint always held) run in their own threads; the EXECUTOR "
    "only clicks and never waits for them. At a death it takes queue[0] (or the waypoint) at "
    "once, revalidated on the freshest frame, with the SWORD read before every attack click. "
    "A walk click goes to the farthest path point that passes the gates (v1 gave up when the "
    "one point it tried was within 60 px of a unit)",
    3: "CONTINUOUS WALKING THAT HOLDS: the walk gate while moving accepts detector frames <= 1.0 s "
    "old (was the last 2 <= 0.4 s: the detector's ~0.3 s latency made it refuse most clicks, idle "
    "~80 %) AND adds the tracked monsters' predicted positions over the next second (60 px), "
    "also before a cursor-gated walk click; legs 8 cells ahead (was 6)",
    4: "STRIKE A STANDING TARGET FROM <= 7 CELLS (Batt 12:56, from his play: every click that "
    "resolved to a monster landed, p50 4 / p90 7 cells, ~0.15 s walk-in a cell): the client walks "
    "in itself, so most steering walk clicks next to monsters go; a WALKING target keeps <= 3. "
    "Bug fix: a finished target's track and a dropped target's spot are never dispatched again",
    5: "CONTINUOUS MOVEMENT (Batt 13:10): every ~0.6 s WHILE THE GM STILL WALKS, a click ~6 cells "
    "ahead of its MEASURED position (the minimap's cell + route_preview's floor odometry since "
    "that read, no reckoning) along the route; no gate needs a standstill: the candidates "
    "6,5,7,4,8,3 ahead are tried on the freshest frames (map, UI, units of the last second, "
    "tracked monsters' predicted positions); only when none passes for 1 s does the GM stop "
    "(then a cursor-gated click); the planner re-plans before the route runs out; the cursor "
    "shape at each walk click is read in SHADOW (logged, never deciding: not proven)",
    6: "ENGAGE LIKE A PLAYER (Batt 14:40 + 14:39): tracks from the MEASURED position at each "
    "frame's time (fractional cells: identity and velocity hold while the camera scrolls), the "
    "continuity re-acquire on; the POINTER FOLLOWS the target's sprite on every fresh frame; at "
    "the GM's stop within range a SHORT read (park blink, a fast return, robust2) and the click at "
    "once; the attack click is the approach (standing <= 7); after a kill the DROPS are picked up "
    "(loot@1's PICKUP scan) before the next target",
    7: "LEAD-COMPENSATED WALK CLICKS (measured 2026-10-16 15:05 on v5's packets: a walk click sent "
    "while moving landed +3.0-3.5 cells AHEAD of the cell meant, ~0 across; the frames and the "
    "minimap show the GM ~0.45 s behind the server, and the client resolves a click where it "
    "really is): each walk click is projected from the measured position + the measured floor "
    "velocity x 0.50 s (v5's per-click lag p50, 1,074 clicks, IQR 0.40-0.60), fractional, and "
    "the ahead candidates count from there; the unit-clearance gate stays on the frame's own "
    "pixel. No looting (Batt 15:00)",
    8: "LEAN STRIKE (v7: striking was 33 % of the judged run, in range -> click p50 6.74 s): no "
    "park after the attack click (nothing used it), and a STALE park (the drawn cursor never "
    "showed at the park point in 1.5 s) counts as a failed read instead of parking again at "
    "once; every strike call is logged with its park and call time. Bug fixes in: the "
    "stuck-search escape (v7 attempt 2 sat 12.7 min) and a no-progress stop",
    9: "STRIKE A STANDING TARGET ONLY (v8: 19 of 21 strike reads failed, 11 WALK -- a hopping "
    "Poring had left the aimed spot by read time, ~1-1.5 s after the frame): no read until the "
    "target's boxes of the last 1.2 s (>= 3 frames) all sit within 8 px of the newest; the "
    "pointer keeps following meanwhile; a target that never stands in 8 s is dropped "
    "(no_still); after the park, a newest box > 8 px off the aimed one calls the read off "
    "(none counted)",
    10: "RISK-BASED CURSOR GATE (Batt 17:4x, the STRICT rule of 3.51): the SWORD read only when "
    "the target's box intersects another, is <= 45 px from the GM's sprite, has confidence < 0.6, "
    "an L3 NPC is within 12 cells, or a Creamy-sized box (no target) is within 150 px; otherwise "
    "the attack click goes straight to the fresh detection (no park, no read). Every attack "
    "click logs its branch and reasons; hard bars: zero NPC contact, zero non-target hit, zero "
    "map change",
    11: "RE-TARGET WHILE STEERING (Batt's change 2: detection -> dispatch, v7 p50 2.85 s, was the "
    "bot steering to ANOTHER target that then failed, 19 / 32): after >= 1 s on a target, the "
    "planner's queue[0] replaces it when it is valid and cheaper by >= 2 cells (Chebyshev to the "
    "predicted cell, +2 for a walking one)",
}
PARAMS: dict[int, dict[str, Any]] = {
    1: {"walk_every_s": 0.8, "ahead": 6, "strike_cells": 3, "short": 2, "track_near": 2.0,
        "track_drop_s": 2.0, "dead_gone_s": 0.6, "dead_near_cells": 1.5, "reclick_s": 2.0,
        "give_up_s": 8.0, "dead_min_s": 1.0, "max_reads": 3, "fresh_s": 0.4, "min_box_px": 16.0,
        "unit_clear_px": 60.0, "clear_frames": 2, "drop_target_s": 15.0},
    2: {"walk_every_s": 0.8, "ahead": 6, "strike_cells": 3, "short": 2, "track_near": 2.0,
        "track_drop_s": 2.0, "dead_gone_s": 0.6, "give_up_s": 8.0, "dead_min_s": 1.0,
        "max_reads": 3, "fresh_s": 0.4, "min_box_px": 16.0, "unit_clear_px": 60.0,
        "clear_frames": 2, "drop_target_s": 15.0, "reclick_s": 2.0, "pipelined": True,
        "queue_depth": 3, "moving_penalty": 2.0, "plan_every_s": 0.1, "waypoint_every_s": 3.0,
        "dispatch_fresh_s": 1.0},
}  # fmt: skip
PARAMS[3] = {**PARAMS[2], "ahead": 8, "short": 3, "gate_frames_s": 1.0, "track_clear": True,
             "track_clear_s": 1.0, "track_clear_px": 60.0}  # fmt: skip
PARAMS[4] = {**PARAMS[3], "strike_cells_standing": 7, "dispatch_fixes": True,
             "reacquire": False, "reacquire_cells": 3.0}  # fmt: skip
PARAMS[5] = {**PARAMS[4], "continuous": True, "walk_every_s": 0.6, "ahead": 6,
             "ahead_order": (6, 5, 7, 4, 8, 3), "stop_after_s": 1.0, "motion_hz": 10.0,
             "moving_cells": 0.15, "replan_left": 10, "shadow_cursor": True,
             # attempt 2 (bug fixes within v5, 2026-10-16 ~14:30): a STALL guard (clicks going out
             # while the measured cell has not changed for stall_s: those cells are blocked and
             # the route re-planned; run 1 sat 255 s at (75,86)), the UI check in the background
             # (it blocked the executor ~2 s every 30 s), and the route preview published
             "stall_s": 2.0, "bg_check": True, "publish_route": True}  # fmt: skip
PARAMS[6] = {**PARAMS[5], "frame_cells": True, "reacquire": True, "follow_mouse": True,
             "short_read": True, "hover_settle_s": 0.25, "loot": True}  # fmt: skip
PARAMS[7] = {**PARAMS[6], "loot": False, "click_lead_s": 0.50, "lead_window_s": 0.3,
             # attempt 2 (2026-10-16 15:26, 7f13bfb, before its run): attempt 1's velocity lead
             # pointed along the OLD direction (the frames show the motion of 0.5 s ago; the
             # lead along the motion was p50 +0.5 cells vs the lag's +3.8); the lead is now our
             # own walk / attack commands replayed from the measured cell over the last 0.6 s
             "lead_from": "commands", "click_lead_s_commands": 0.6}  # fmt: skip
PARAMS[8] = {**PARAMS[7], "strike_lean": True, "escape_after_s": 3.0}
PARAMS[9] = {**PARAMS[8], "still_gate": True, "still_s": 1.2, "still_px": 8.0,
             "still_wait_s": 8.0}  # fmt: skip
# v9 attempt 2 (2026-10-16 17:35, 8d4a780, before its run): a position jump on the SAME map (the
# minimap picture unchanged) re-anchors on the minimap instead of stopping (run 1: a 14-cell lag)
PARAMS[9]["jump_reanchor"] = True
PARAMS[10] = {**PARAMS[9], "freeze_guard": True, "risk_gate": True, "gate_near_gm_px": 45.0,
              "gate_min_conf": 0.6, "gate_npc_cells": 12, "gate_ignore_px": 150.0,
              # attempt 2 (2026-10-16 ~18:16, before its run): the gate's box may be <= 1.0 s old
              # (attempt 1: 15 / 15 calls "stale_box" at 0.4 s; the CPU detector delivers boxes
              # 0.3-0.65 s after their frame; v9's stand gate holds the target still >= 1.2 s)
              "gate_fresh_s": 1.0}  # fmt: skip
PARAMS[11] = {**PARAMS[10], "retarget": True, "retarget_margin": 2.0, "retarget_commit_s": 1.0}


# --- pure parts (tested) --------------------------------------------------------------------------


def cheb(a: Sequence[float], b: Sequence[float]) -> float:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


@dataclass
class Track:
    """One monster, by its cells over time (constant velocity), and its newest box."""

    tid: int
    seen: list[tuple[int, Cell]] = field(default_factory=list)  # (t_ns, cell)
    box: Any = None  # the newest box (client px)
    box_t: int = 0
    boxes: list[tuple[int, Any]] = field(default_factory=list)  # v6: (t_ns, box) per sighting

    @property
    def t_first(self) -> int:
        return self.seen[0][0]

    @property
    def t_last(self) -> int:
        return self.seen[-1][0]

    def velocity(self) -> tuple[float, float]:
        """Cells / s from the sightings of the last ~1.5 s (0 when it stands or is new)."""
        if len(self.seen) < 2:
            return 0.0, 0.0
        t1, c1 = self.seen[-1]
        old = [s for s in self.seen if 0.4e9 <= t1 - s[0] <= 1.5e9]
        if not old:
            return 0.0, 0.0
        t0, c0 = old[0]  # the oldest in the window: a cell is +-1, so the longest baseline
        if cheb(c0, c1) <= 1:
            return 0.0, 0.0  # within a cell's noise: standing
        dt = (t1 - t0) / 1e9
        vx, vy = (c1[0] - c0[0]) / dt, (c1[1] - c0[1]) / dt
        cap = 1000.0 / 150.0  # nothing on this map walks faster than 150 ms a cell
        n = math.hypot(vx, vy)
        return (vx * cap / n, vy * cap / n) if n > cap else (vx, vy)

    def predict(self, t_ns: int) -> tuple[float, float]:
        t1, c1 = self.seen[-1]
        vx, vy = self.velocity()
        dt = min(1.0, max(0.0, (t_ns - t1) / 1e9))
        return c1[0] + vx * dt, c1[1] + vy * dt


def update_tracks(tracks: list[Track], t_ns: int, sightings: Sequence[tuple[Any, Cell]],
                  next_id: int, near: float, drop_s: float) -> tuple[list[Track], int]:  # fmt: skip
    """PURE: each sighting joins the nearest track whose prediction at ``t_ns`` is within
    ``near`` cells (one sighting per track), else starts a new track; tracks unseen ``drop_s``
    are dropped. Returns (tracks, next_id)."""
    free = list(tracks)
    for box, cell in sorted(sightings, key=lambda s: s[1]):
        best = None
        for tr in free:
            d = cheb(tr.predict(t_ns), cell)
            if d <= near and (best is None or d < best[0]):
                best = (d, tr)
        if best is None:
            tr = Track(next_id)
            next_id += 1
            tracks.append(tr)
        else:
            tr = best[1]
            free.remove(tr)
        tr.seen.append((t_ns, cell))
        tr.box, tr.box_t = box, t_ns
        tr.boxes.append((t_ns, box))
        del tr.boxes[:-60]
    keep = [tr for tr in tracks if (t_ns - tr.t_last) / 1e9 <= drop_s]
    return keep, next_id


def choose(tracks: Sequence[Track], here: Cell, t_ns: int,
           banned: Sequence[tuple[float, Cell]] = (), now_s: float = 0.0,
           ban_s: float = 15.0) -> Track | None:  # fmt: skip
    """PURE: the nearest track by its predicted cell (Batt: the nearest 52 / 54), skipping cells
    a dropped target left within ``ban_s``."""
    best = None
    for tr in tracks:
        p = tr.predict(t_ns)
        if any(now_s - tb < ban_s and cheb(p, cb) <= 2 for tb, cb in banned):
            continue
        d = cheb(p, here)
        if best is None or d < best[0]:
            best = (d, tr)
    return None if best is None else best[1]


def approach_path(grid: Any, here: Cell, target: tuple[float, float], short: int
                  ) -> list[Cell] | None:  # fmt: skip
    """The A* path toward the target's cell, ending ``short`` cells before it (never a walk click
    onto the monster: hunt@5's walk click 2 cells from it became an attack). None: no path or
    already there."""
    goal = (int(round(target[0])), int(round(target[1])))
    if not (0 <= goal[1] < grid.shape[0] and 0 <= goal[0] < grid.shape[1]):
        return None
    g = grid.copy()
    g[goal[1], goal[0]] = True
    g[here[1], here[0]] = True  # a walk-in can leave us on a cell the grid does not hold
    path = hc.astar(g, here, goal)
    if path is None or len(path) <= short + 1:
        return None
    return path[: len(path) - short]


def strike_range(tr: Track, prm: dict[str, Any]) -> int:
    """PURE (v4): STANDING targets from ``strike_cells_standing`` (Batt's p90, 7), WALKING ones
    from ``strike_cells`` (3); before v4 always ``strike_cells``."""
    vx, vy = tr.velocity()
    if prm.get("strike_cells_standing") and not (vx or vy):
        return int(prm["strike_cells_standing"])
    return int(prm["strike_cells"])


def strike_due(moving: bool, here: Cell, target: tuple[float, float], strike_cells: int) -> bool:
    """PURE: Batt's 'attack from a standing GM': the brief moment the walk has ended, the target
    within ``strike_cells``."""
    return not moving and cheb(here, target) <= strike_cells


def plan_queue(tracks: Sequence[Track], start: Sequence[float], t_ns: int, depth: int,
               banned: Sequence[tuple[float, Cell]] = (), now_s: float = 0.0,
               ban_s: float = 15.0, moving_penalty: float = 2.0) -> list[Track]:  # fmt: skip
    """PURE (v2's planner): up to ``depth`` targets by the shortest CHAINED path -- each next one
    nearest to the previous one's predicted cell, starting from ``start`` (our cell) -- with a
    walking monster costing ``moving_penalty`` cells more (standing targets first: Batt's misses
    were on walking ones). Cells a dropped target left within ``ban_s`` are skipped."""
    left = []
    for tr in tracks:
        p = tr.predict(t_ns)
        if any(now_s - tb < ban_s and cheb(p, cb) <= 2 for tb, cb in banned):
            continue
        vx, vy = tr.velocity()
        left.append((tr, p, moving_penalty if (vx or vy) else 0.0))
    out: list[Track] = []
    at = (float(start[0]), float(start[1]))
    while left and len(out) < depth:
        i = min(range(len(left)), key=lambda j: cheb(at, left[j][1]) + left[j][2])
        tr, p, _pen = left.pop(i)
        out.append(tr)
        at = p
    return out


def reacquire_target(target: Track, live: Sequence[Track], t_ns: int, within: float,
                     exclude: Sequence[int] = ()) -> Track | None:  # fmt: skip
    """PURE (v4): the target's track was dropped (the tracker started a new id for the same
    monster: the cell estimate shifts while the GM walks). The live track nearest the target's
    predicted cell within ``within`` cells carries it on, else None (lost)."""
    p = target.predict(t_ns)
    best = None
    for tr in live:
        if tr.tid == target.tid or tr.tid in exclude:
            continue
        d = cheb(tr.predict(t_ns), p)
        if d <= within and (best is None or d < best[0]):
            best = (d, tr)
    return None if best is None else best[1]


def ahead_candidates(path: Sequence[Cell], here: Sequence[float], order: Sequence[int]
                     ) -> list[int]:  # fmt: skip
    """PURE (v5): path indices to try for the next walk click, ``order`` cells ahead of the path
    cell nearest to where we ARE (measured), the first in range first."""
    if not path:
        return []
    ci = min(range(len(path)), key=lambda i: cheb(path[i], here))
    return [ci + k for k in order if 0 < ci + k < len(path)]


def odo_at(hist: Sequence[tuple[int, Any]], t_ns: int) -> Any:
    """PURE (v5): the odometry total at ``t_ns`` (the last sample at or before it)."""
    best = hist[0][1] if hist else None
    for t, v in hist:
        if t > t_ns:
            break
        best = v
    return best


def odo_velocity(hist: Sequence[tuple[int, Any]], window_s: float) -> tuple[float, float]:
    """PURE (v7): the measured floor velocity (cells / s) over the newest ``window_s`` of the
    odometry; 0 with too little history."""
    if len(hist) < 2:
        return 0.0, 0.0
    t1, o1 = hist[-1]
    t0, o0 = hist[0]
    for t, v in hist:  # the last sample at or before t1 - window
        if t > t1 - int(window_s * 1e9):
            break
        t0, o0 = t, v
    if t1 <= t0:
        return 0.0, 0.0
    dt = (t1 - t0) / 1e9
    return float(o1[0] - o0[0]) / dt, float(o1[1] - o0[1]) / dt


def lead_origin(here: Sequence[float], vel: Sequence[float], lead_s: float
                ) -> tuple[float, float]:  # fmt: skip
    """PURE (v7): where the client will resolve a click from: the measured cell + velocity x lead
    (the frames show the GM ~0.5 s behind where the client walks it)."""
    return float(here[0]) + float(vel[0]) * lead_s, float(here[1]) + float(vel[1]) * lead_s


def commanded_lead(at: Sequence[float], cmds: Sequence[tuple[int, Cell]], t_now: int,
                   lead_s: float, ms_cell: float = MS_CELL, step_s: float = 0.01
                   ) -> tuple[float, float]:  # fmt: skip
    """PURE (v7 attempt 2): where the client IS now. The frames (so ``at``, measured from them)
    show it ~``lead_s`` late, and in that time it walked toward the cells we had clicked
    (``cmds``: (t_ns, cell), oldest first): replay those commands from ``at`` over the last
    ``lead_s``, 8 directions, ``ms_cell`` a cell, x1.4 on a diagonal, stopping on arrival.
    Measured on v7 attempt 1's packets: the client at a click's arrival is the server's cell at
    the click time (95 % within 1), the measured cell the server's ~0.6 s earlier."""
    x, y = float(at[0]), float(at[1])
    ts = [t for t, _ in cmds]
    t = t_now - int(lead_s * 1e9)
    while t < t_now:
        i = bisect.bisect_right(ts, t) - 1
        if i >= 0:
            dx, dy = cmds[i][1][0] - x, cmds[i][1][1] - y
            if max(abs(dx), abs(dy)) > 0.5:
                diag = abs(dx) > 0.5 and abs(dy) > 0.5
                sp = step_s / (ms_cell / 1000.0 * (1.4 if diag else 1.0))
                if abs(dx) > 0.5:
                    x += math.copysign(min(sp, abs(dx)), dx)
                if abs(dy) > 0.5:
                    y += math.copysign(min(sp, abs(dy)), dy)
        t += int(step_s * 1e9)
    return x, y


def main_component(area: Any) -> Any:
    """PURE (v8 bug fix): the largest 8-connected component of ``area``. v7 attempt 2 walked onto
    a ledge strip of the area from which no goal had a path, and sat there 12.7 min."""
    from collections import deque

    a = np.asarray(area, dtype=bool)
    h, w = a.shape
    lab = np.zeros((h, w), np.int32)
    n, best = 0, (0, 0)
    for y0, x0 in zip(*np.nonzero(a), strict=True):
        if lab[y0, x0]:
            continue
        n += 1
        lab[y0, x0] = n
        q, size = deque([(int(y0), int(x0))]), 0
        while q:
            y, x = q.popleft()
            size += 1
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < h and 0 <= xx < w and a[yy, xx] and not lab[yy, xx]:
                        lab[yy, xx] = n
                        q.append((yy, xx))
        if size > best[0]:
            best = (size, n)
    return lab == best[1]


def escape_cells(main: Any, here: Cell, reach: int = 30, k: int = 5, near: int = 0
                 ) -> list[Cell]:  # fmt: skip
    """PURE (v8 bug fix): up to ``k`` cells of the main component nearest ``here`` (Chebyshev,
    ``near``..``reach``), nearest first: where to walk when no goal has a path. v8 run 1: the
    nearest (1 step away) read NO-ENTRY, and every other candidate was adjacent too."""
    h, w = main.shape
    x0, y0 = max(0, here[0] - reach), max(0, here[1] - reach)
    ys, xs = np.nonzero(main[y0 : min(h, here[1] + reach + 1), x0 : min(w, here[0] + reach + 1)])
    cells = sorted(((int(x) + x0, int(y) + y0) for y, x in zip(ys, xs, strict=True)),
                   key=lambda c: (cheb(c, here), c))  # fmt: skip
    return [c for c in cells if c != here and cheb(c, here) >= near][:k]


def target_cost(tr: Track, here: Sequence[float], t_ns: int, moving_penalty: float) -> float:
    """PURE (v11): the planner's cost of a target from ``here`` -- Chebyshev cells to its predicted
    cell, plus ``moving_penalty`` when it walks (standing targets first, as plan_queue)."""
    vx, vy = tr.velocity()
    return cheb(here, tr.predict(t_ns)) + (moving_penalty if (vx or vy) else 0.0)


def gate_reasons(b: Any, others: Sequence[Any], gm_px: Sequence[float], near_gm_px: float,
                 min_conf: float, npc_near: bool, ignore_near: bool) -> list[str]:  # fmt: skip
    """PURE (v10, Batt's risk-based gate, the STRICT rule approved 2026-10-16): why this attack
    click still needs the SWORD read; [] = click the fresh detection directly."""
    why: list[str] = []
    if any(not (o.x1 < b.x0 or o.x0 > b.x1 or o.y1 < b.y0 or o.y0 > b.y1) for o in others):
        why.append("intersect")
    cx, cy = (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2
    if math.hypot(cx - gm_px[0], cy - gm_px[1]) <= near_gm_px:
        why.append("near_gm")
    if float(b.score) < min_conf:
        why.append("low_conf")
    if npc_near:
        why.append("npc_near")
    if ignore_near:
        why.append("ignore_species")
    return why


def map_same(ref: Any, cur: Any, max_median: float = MAP_SAME_MAX) -> bool:
    """PURE (v9 attempt 2): the minimap PICTURE is still the run's map -- the median per-pixel
    summed |diff| against the start's crop is small (the GM arrow moves over ~2 % of it). v9 run 1
    stopped as a "map change" on a 14-cell odometry lag on a slope; no map_change in the packets."""
    a = np.asarray(ref)[..., :3].astype(np.int16)
    b = np.asarray(cur)[..., :3].astype(np.int16)
    if a.shape != b.shape:
        return False
    return float(np.median(np.abs(a - b).sum(-1))) <= max_median


def box_still(boxes: Sequence[tuple[int, Any]], t_now: int, window_s: float, px: float,
              min_n: int = 3) -> bool:  # fmt: skip
    """PURE (v9): the target STANDS -- at least ``min_n`` of its boxes from frames of the last
    ``window_s`` (frame time), every centre within ``px`` of the newest. v8: 19 of 21 strike reads
    failed (WALK 11): a hopping Poring had left the aimed spot by read time (~1-1.5 s later)."""
    rec = [(t, b) for t, b in boxes if (t_now - t) / 1e9 <= window_s]
    if len(rec) < min_n:
        return False
    cx, cy = (rec[-1][1].x0 + rec[-1][1].x1) / 2, (rec[-1][1].y0 + rec[-1][1].y1) / 2
    return all(math.hypot((b.x0 + b.x1) / 2 - cx, (b.y0 + b.y1) / 2 - cy) <= px for _t, b in rec)


def trail_cells(trail: Sequence[tuple[float, Cell]], here: Cell, now: float, near: int = 6,
                far: int = 20, min_age_s: float = 3.0, k: int = 5) -> list[Cell]:  # fmt: skip
    """PURE (v8 attempt 2): cells WE WALKED (``trail``: (mono s, cell), oldest first), most recent
    first, ``near``..``far`` cells from ``here`` and at least ``min_age_s`` old: proven reachable,
    unlike a map cell the client may refuse (v8 run 1's escape read NO-ENTRY)."""
    out: list[Cell] = []
    for t, c in reversed(trail):
        if now - t >= min_age_s and near <= cheb(c, here) <= far and c not in out:
            out.append(c)
            if len(out) >= k:
                break
    return out


def frac_project(world: Any, origin: Sequence[float], cell: Sequence[float]) -> tuple[float, float]:
    """(v7) The screen pixel of ``cell`` with the camera centred on the FRACTIONAL ``origin``:
    the World stands on the rounded cell and the cell moves by the fraction instead (the GAT
    altitude is bilinear in fractional offsets)."""
    r0 = (int(round(origin[0])), int(round(origin[1])))
    world.position = r0
    p = world.project([(cell[0] - (origin[0] - r0[0]), cell[1] - (origin[1] - r0[1]))])[0]
    return float(p[0]), float(p[1])


def palette_mask(a: Any) -> Any:
    """v5 SHADOW (not proven): the cursor's own pixels by colour, with no parked background --
    light low-saturation fill, a dark outline, red (BGR). Offline vs robust2 (2026-10-16, 5 Hz
    JPEG): 62 / 200 agree; logged only, never a gate."""
    a = np.asarray(a)[..., :3].astype(np.int16)
    b, g, r_ = a[..., 0], a[..., 1], a[..., 2]
    mx, mn = a.max(-1), a.min(-1)
    red = (r_ >= 150) & (r_ - np.maximum(g, b) >= 60)
    return ((mn >= 165) & (mx - mn <= 55)) | (mx <= 45) | red


def track_clear(u: float, v: float, tracks: Sequence[Track], t_ns: int, horizon_s: float,
                px: float, project: Any) -> bool:  # fmt: skip
    """PURE (v3, the walk-click safety: hunt-flow@1 had 10 walk clicks turned attacks): the click
    point is more than ``px`` from where every TRACKED monster is predicted to be drawn over the
    next ``horizon_s`` (now, half way, the end). ``project(cell) -> (u, v)`` gives a cell's feet
    point; the monster is drawn at its newest box's offset from its feet. Tracks outlive a
    detector miss (a canopy), which the frame gate does not."""
    for tr in tracks:
        b = tr.box
        off = (0.0, 0.0)
        if b is not None:
            cx, cy = (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2
            off = (cx - (b.x0 + b.x1) / 2, cy - b.y1)
        for k in (0.0, 0.5, 1.0):
            pc = tr.predict(t_ns + int(k * horizon_s * 1e9))
            fu, fv = project(pc)
            if math.hypot(u - (fu + off[0]), v - (fv + off[1])) <= px:
                return False
    return True


def valid_at_dispatch(tr: Track, live: Sequence[Track], t_ns: int, fresh_s: float) -> bool:
    """PURE: a planned target is dispatched only if the tracker still holds it and its newest
    box is from a frame <= ``fresh_s`` old (then the SWORD read decides)."""
    return any(x.tid == tr.tid for x in live) and (t_ns - tr.box_t) / 1e9 <= fresh_s


class PositionModel:
    """Our cell, shared by the executor (it writes) and the perception thread (it reads)."""

    def __init__(self, ms_cell: float, pos: Cell) -> None:
        import threading

        self.lock = threading.Lock()
        self.reck = hc.Reckoner(ms_cell)
        self.moving = False
        self.pos = pos

    def go(self, seg: Sequence[Cell], t0: float) -> None:
        with self.lock:
            self.reck.go(seg, t0)
            self.moving = True

    def stop(self, pos: Cell) -> None:
        with self.lock:
            self.moving, self.pos = False, pos

    def at(self, t: float) -> Cell:
        with self.lock:
            if self.moving:
                return self.reck.where(t) or self.pos
            return self.pos


def _start_thread(target: Any, name: str) -> Any:
    import threading

    th = threading.Thread(target=target, name=name, daemon=True)
    th.start()
    return th


# --- the run --------------------------------------------------------------------------------------


def run(version: int, minutes: float, seed: int) -> int:  # noqa: PLR0915
    import multiprocessing as mp

    import bench
    import cursor_gate
    import gm_state
    import gm_vitals
    import hunt
    import loot1
    import operator_hud
    import record_session
    import route_demo
    import route_plan
    import rule_run as rr
    import unit_detector
    import walk5 as w5
    import walk15 as w15
    import where_fix as wf
    from anim_region import stand_grid

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod
    from poring_dataset import picking
    from poring_env import selfpos
    from poring_env.demo import DemoLog, new_session_id

    if version not in VERSIONS:
        raise SystemExit(f"unknown version {version}")
    prm = PARAMS[version]
    ok_imm, why_imm = f0.immunity_confirmed()
    if not ok_imm:
        raise f0.FarmStop(f"hunt-flow refused: the GM is not confirmed immune ({why_imm})")
    lock = record_session.read_lock(r.ROOT / "state")
    if str(lock.backend) != "rdp":
        raise f0.FarmStop(f"hunt-flow refused: RDP-only cursor references (lock {lock.backend})")
    gat = gatmod.parse((cam.GAT_DIR / f"{MAP}.gat").read_bytes())
    ok = stand_grid(MAP, gat)
    kb = r.ROOT / "data" / "kb"
    warps = json.loads((kb / "warps.json").read_text()).get(MAP, [])
    npcs = json.loads((kb / "npc_cells.json").read_text())["maps"].get(MAP, {}).get("npcs", [])
    keep = [(w["x"], w["y"], w["span_x"], w["span_y"]) for w in warps]
    keep += [(n["x"], n["y"], 1, 1) for n in npcs]
    area = hc.search_area(ok, keep, margin=10)
    start = hunt.start_cell(area, seed)
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    camera = cam.camera_from_json(cj["camera"])
    gx0, gy0, gw, gh = r.game_region()

    def in_view(u: float, v: float) -> bool:
        return 0 <= u < gw and 0 <= v < gh and not loot1.in_ui(u, v)

    offsets = hc.footprint(lambda o: camera.project(o, np.zeros(len(o))), in_view)
    sid = new_session_id(f"hunt-flow{version}")
    log = DemoLog(sid)
    out = OUT / sid
    out.mkdir(parents=True, exist_ok=True)
    frames_dir = REC_ROOT / sid / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena",
              rule=f"{RULE}@{version}", account="gm", map=MAP, minutes=minutes, seed=seed,
              start=list(start), change=VERSIONS[version], params=prm,
              area_cells=int(area.sum()), scored=True, immunity=why_imm, rec_dir=str(out),
              frames_dir=str(frames_dir), gm_profile="hunt-flow")  # fmt: skip
    print(json.dumps({"session": sid, "version": version, "start": time.strftime("%H:%M:%S")}),
          flush=True)  # fmt: skip
    events_f = (log.dir / "events.jsonl").open("a")
    clicks_f = (log.dir / "clicks.jsonl").open("a")

    def ev(rec: dict[str, Any]) -> None:
        events_f.write(json.dumps({"t_ns": r.ns(), **rec}, default=str) + "\n")
        events_f.flush()

    def click_log(rec: dict[str, Any]) -> None:
        clicks_f.write(json.dumps(rec, default=str) + "\n")
        clicks_f.flush()

    split = f0.Split(dict.fromkeys(("searching", "steering", "striking", "fighting", "stopping",
                                    "checks", "looting"), 0.0))  # fmt: skip
    engagements: list[dict[str, Any]] = []
    cov = hc.Coverage(area)
    ended, run_s, t_run0 = "time_box", 0.0, time.monotonic()
    crashed: BaseException | None = None
    t_first = r.ns()
    ctx = mp.get_context("spawn")
    stop_rec = ctx.Event()
    rec = ctx.Process(target=route_demo._record, args=(str(frames_dir), (gx0, gy0, gw, gh),
                                                       stop_rec, REC_HZ, REC_QUALITY),
                      daemon=True)  # fmt: skip
    plan_tok = route_plan.enable(f"hunt-flow{version}-{sid}", MAP,
                                 log_path=str(out / "live.jsonl"))  # fmt: skip
    sampler = None
    with r.session(f"rule:{RULE}@{version}") as (agent, screen):
        f0.stop_on_takeover(agent)
        hud_tok = operator_hud.enable(f"hunt-flow@{version}", agent=agent,
                                      log_path=str(out / "hud.jsonl"))  # fmt: skip
        det = unit_detector.UnitDetector()
        rec.start()
        try:
            import walk11 as w11

            w11.UNITS["detector"] = det
            w11.UNITS["ms_per_cell"] = MS_CELL
            w11.UNITS["memory"] = w15.NpcClearMemory()
            pr = cursor_gate.prober(agent, screen)  # robust2
            digits = selfpos.load_digit_templates()
            relocalise = w15.where_relocalise(wf.load_templates(wf.TEMPLATES_V2))
            band, noentry = rr.ec_band(), np.load(w5.NOENTRY_MASK)
            world = w5.World(camera, gat, start)
            from poring_env import weight as wt

            rig = loot1.Rig(agent, screen, pr, det, camera, gat, gat.walkable(), digits,
                            wt.load_weight_glyphs(r.ROOT / wt.DEFAULT_TEMPLATES),
                            loot1.chat_cue.load_cues(), operator_hud.sender())  # fmt: skip

            def note(line: str, boxes: Any = ()) -> None:
                loot1.hud(rig, line, boxes)

            def frame() -> Any:
                return screen.grab(gx0, gy0, gw, gh)[1]

            def read_position() -> Cell | None:
                xy = selfpos.read_minimap_xy(frame()[:, :, :3], digits)
                return None if xy is None else (int(xy[0]), int(xy[1]))

            last_fix = [0.0]
            pos_box: list[Cell] = [start]

            def settle(timeout: float = 5.0) -> Cell | None:
                """Our cell once the GM stands: two minimap reads 0.3 s apart agree; else the
                reckoned cell when a fix is under a minute old; else /where once; else stop."""
                end = time.monotonic() + timeout
                while time.monotonic() < end:
                    a = read_position()
                    time.sleep(0.3)
                    b = read_position()
                    if a is not None and a == b and ok[a[1], a[0]]:
                        last_fix[0] = time.monotonic()
                        return a
                if time.monotonic() - last_fix[0] < 60.0:
                    ev({"kind": "reckoned_fix", "cell": list(pos_box[0])})
                    return pos_box[0]
                world.position = pos_box[0]
                got = relocalise(agent, screen, world, noentry, band)
                bench.close_chat(agent, screen)
                ev({"kind": "where_fix", "ok": bool(got.get("ok")), "to": list(world.position)})
                if got.get("ok"):
                    return tuple(world.position)  # type: ignore[return-value]
                raise f0.FarmStop("our cell is unknown (minimap and /where both failed)")

            last_check = [0.0]

            def check(where: str) -> None:
                prev = split._cat
                split.to("checks", time.monotonic())
                st = f0.client_state(agent, screen)
                last_check[0] = time.monotonic()
                if st["decision"]["do"] != "clear":
                    shot = r.to_png(st["frame"], log.dir / f"stop-{len(engagements)}.png")
                    raise f0.FarmStop(f"client state at {where}: {st['decision']} (frame {shot})")
                hp = gm_vitals.hp_fraction(frame()[..., :3])
                if hp < f0.HP_STOP:
                    raise f0.FarmStop(f"HP {hp:.2f} at {where}: an immune GM lost HP")
                split.to(prev, time.monotonic())

            def cell_of(b: Any, here: Cell, w: Any = None) -> tuple[Cell | None, float]:
                w_ = world if w is None else w  # v2: the perception thread has its own World
                fu, fv = f1.foot(b)
                off = picking.pick_cells(camera, gat, here,
                                         np.array([[fu, fv - loot1.FOOT_LIFT]]))[0]  # fmt: skip
                if abs(int(off[0])) > 1000:
                    return None, 1.0
                c = (here[0] + int(off[0]), here[1] + int(off[1]))
                w_.position = here
                p = w_.project([c, (c[0] + 1, c[1])])
                p0 = w_.project([here, (here[0] + 1, here[1])])
                px0 = float(np.hypot(*(p0[1] - p0[0])))
                return c, (float(np.hypot(*(p[1] - p[0]))) / px0 if px0 > 0 else 1.0)

            def sightings_in(boxes: Any, here: Cell, w: Any = None,
                             frac: tuple[float, float] = (0.0, 0.0)
                             ) -> list[tuple[Any, Any]]:  # fmt: skip
                """hunt@6's selection gates on one frame's boxes; v6: ``frac`` = our measured
                fractional offset from ``here`` at the frame (the camera centres on it), so the
                cells are fractional and hold still while the camera scrolls."""
                got_ = []
                for b in boxes:
                    if b.cls != "monster":
                        continue
                    c, scale = cell_of(b, here, w)
                    if c is None or not (0 <= c[0] < area.shape[1] and 0 <= c[1] < area.shape[0]):
                        continue
                    if f1.native_size(b, scale) > f1.MAX_NATIVE_PX:
                        continue  # Creamy (a metamorphosed Pupa) is no target
                    if min(b.x1 - b.x0, b.y1 - b.y0) < prm["min_box_px"]:
                        continue  # a floor item
                    if loot1.in_ui(*f1.centre(b)) or not area[c[1], c[0]]:
                        continue
                    got_.append((b, c if frac == (0.0, 0.0)
                                 else (c[0] + frac[0], c[1] + frac[1])))  # fmt: skip
                return got_

            def rp(cmd: str, *a: Any) -> None:
                pub = route_plan.publisher()
                if pub is None:
                    return
                with contextlib.suppress(Exception):
                    if cmd == "route":
                        world.position = a[0]
                        route_plan.preview(agent, world, a[0], a[1], None, f"hunt-flow@{version}")
                    elif cmd == "walk":
                        pub.walk(a[0], a[1], MS_CELL, a[2])
                    elif cmd == "snap":
                        pub.snap(a[0])
                    else:
                        pub.clear()

            def step_target(pth: list[Cell], from_i: int, at: Cell, ahead: int,
                            grid: Any = None, need_clear: bool = False
                            ) -> tuple[int | None, tuple[float, float]]:  # fmt: skip
                """The farthest path index in (from_i, from_i + ahead] whose point is in view,
                off the UI and on ``grid`` (the search area by default), seen from ``at``; with
                ``need_clear`` (v2, a click while moving) also clear of units (option B)."""
                g_ = area if grid is None else grid
                world.position = at
                hi = min(len(pth) - 1, from_i + ahead)
                for jj in range(hi, from_i, -1):
                    uu, vv = (float(c) for c in world.project([pth[jj]])[0])
                    if in_view(uu, vv) and g_[pth[jj][1], pth[jj][0]] and (
                            not need_clear or units_clear(uu, vv)):  # fmt: skip
                        return jj, (uu, vv)
                return None, (0.0, 0.0)

            def tracked_clear(u: float, v: float) -> bool:
                """v3: no tracked monster predicted within track_clear_px over track_clear_s."""
                if not prm.get("track_clear"):
                    return True
                here_ = pos_box[0]

                def project(c: Any) -> tuple[float, float]:
                    world.position = here_
                    q = world.project([c])[0]
                    return float(q[0]), float(q[1])

                return track_clear(u, v, tracks_now(), r.ns(), prm["track_clear_s"],
                                   prm["track_clear_px"], project)  # fmt: skip

            def units_clear(u: float, v: float) -> bool:
                """3.39 deviation (2) option B: no detector unit within unit_clear_px of the
                point on the last clear_frames fresh frames; v3: on every frame of the last
                gate_frames_s, and no tracked monster predicted there (tracked_clear)."""
                if prm.get("gate_frames_s"):
                    t_min = r.ns() - int(prm["gate_frames_s"] * 1e9)
                    k_ = len(sampler.frames)
                    rec_ = [f for f in sampler.since(max(0, k_ - 8)) if f[0] >= t_min]
                    return (bool(rec_) and all(
                        np.hypot(*(np.array(f1.centre(b)) - (u, v))) > prm["unit_clear_px"]
                        for _t, bs in rec_ for b in bs) and tracked_clear(u, v))  # fmt: skip
                rec_ = sampler.since(max(0, len(sampler.frames) - prm["clear_frames"]))
                return (len(rec_) >= prm["clear_frames"]
                        and (r.ns() - rec_[-1][0]) / 1e9 <= prm["fresh_s"]
                        and all(np.hypot(*(np.array(f1.centre(b)) - (u, v)))
                                > prm["unit_clear_px"] for _t, bs in rec_ for b in bs))  # fmt: skip

            # --- start --------------------------------------------------------------------------
            import chat_guard

            chat_guard.start_run(f"hunt-flow{version}-{sid}")
            before = gm_state.ensure_fixed(agent, screen, why=f"hunt-flow@{version}:before",
                                           out_dir=log.dir / "gm_state", profile="hunt-flow",
                                           loot=True)  # fmt: skip
            ev({"kind": "gm_state_before", **f0._brief(before)})
            r.gm(agent, screen, f"@warp {MAP} {start[0]} {start[1]}")
            time.sleep(rr.SCENE_ENTRY_S)
            bench.close_chat(agent, screen)
            r.activate_client(agent, screen)
            sampler = loot1.Sampler(det)
            sampler.start()
            pos = settle() or start
            if cheb(pos, start) > 3:
                raise f0.FarmStop(f"the start @warp did not land: at {pos}, not {start}")
            reck = hc.Reckoner(MS_CELL)
            posm = PositionModel(MS_CELL, pos)  # v2: shared with the perception thread
            deadline = time.monotonic() + minutes * 60
            t_run0 = time.monotonic()
            ev({"kind": "loop_start"})
            path: list[Cell] = []
            pi = 0
            moving = False
            refused = 0
            bad_tiles: list[Cell] = []
            click_from: Cell | None = None
            click_cell: Cell | None = None
            unfollowed: dict[Cell, int] = {}
            last_mm, mm_off = 0.0, 0
            last_walk = 0.0
            last_weight = time.monotonic()
            last_progress = [time.monotonic()]
            tracks: list[Track] = []
            next_id = 0
            kf = 0
            target: Track | None = None
            reads = 0
            banned: list[tuple[float, Cell]] = []
            eng: dict[str, Any] | None = None
            k = 0
            split.to("searching", time.monotonic())

            import threading

            plock = threading.Lock()
            plan: dict[str, Any] = {"queue": [], "goal_path": None, "t_goal": 0.0}
            refusals: dict[Cell, int] = {}

            def refuse(to: Cell, why: str) -> None:
                """v2 attempt 2 (Batt 11:46, the GM stuck on a ledge: "if char can't move you
                should click in available field in map"): a NO-ENTRY read blocks that spot at once,
                any other refusal after 2; the blocked cells (radius 1) leave the area and the stand
                grid, and the planner re-plans. v2 attempt 1 retried (194,128) 108 times."""
                n_ = refusals.get(to, 0) + 1
                refusals[to] = n_
                if "noentry" in why or n_ >= 2:
                    x_, y_ = to
                    area[max(0, y_ - 1) : y_ + 2, max(0, x_ - 1) : x_ + 2] = False
                    ok[max(0, y_ - 1) : y_ + 2, max(0, x_ - 1) : x_ + 2] = False
                    ev({"kind": "spot_blocked", "cell": list(to), "why": why, "refusals": n_})
                    if prm.get("pipelined"):
                        with plock:
                            plan["goal_path"] = None

            cmd_hist: list[tuple[int, Cell]] = []  # v7 attempt 2: (t_ns, cell) we clicked
            ptr: list[tuple[float, float]] = [(gw / 2, gh / 2)]  # v8: where the pointer is

            def walk_click(u: float, v: float, to: Cell, seg: list[Cell], gate: str,
                           why: str, extra: dict[str, Any] | None = None) -> bool:  # fmt: skip
                """One walk click: cursor-gated from a standstill, map+units while moving."""
                nonlocal moving, click_from, click_cell, last_walk
                t_c = r.ns()
                if gate == "cursor":
                    if prm.get("track_clear") and not tracked_clear(u, v):
                        ev({"kind": "walk_click", "gate": gate, "to": list(to), "clicked": False,
                            "why": "tracked_monster_near"})  # fmt: skip
                        return False
                    got = cursor_gate.gated_click(pr, u, v, allow=("walk",))
                    if not got["clicked"]:
                        ev({"kind": "walk_click", "gate": gate, "to": list(to), "clicked": False,
                            "why": got["why"]})  # fmt: skip
                        refuse(to, str(got["why"]))
                        return False
                    t_c = int(got["t_click"])
                    click_from, click_cell = seg[0], to
                else:
                    agent.click(gx0 + round(u), gy0 + round(v))
                ptr[0] = (u, v)
                click_log({"t": t_c, "u": round(u, 1), "v": round(v, 1), "kind": "walk",
                           "gate": gate, "to": list(to), "why": why, **(extra or {})})  # fmt: skip
                ev({"kind": "walk_click", "gate": gate, "to": list(to), "why": why,
                    **(extra or {})})  # fmt: skip
                cmd_hist.append((int(t_c), (int(to[0]), int(to[1]))))  # v7: the client's commands
                del cmd_hist[:-40]
                reck.go(seg, time.monotonic())
                posm.go(seg, time.monotonic())
                rp("walk", seg[0], seg, t_c)
                moving = True
                last_walk = time.monotonic()
                last_progress[0] = time.monotonic()
                return True

            in_range_since: dict[int, float] = {}  # v6: track -> when it came in range (mono s)
            eng_tracks: dict[int, Track] = {}

            def loot_after(eng_: dict[str, Any], here2: Cell) -> None:
                """v6 (Batt 14:39: "wait for check item drop before continue next queue"): the death
                cell from the target's boxes on the sampler's frames, then loot@1's PICKUP scan."""
                from poring_dataset import deathcell as dcm_

                tr_ = eng_tracks.get(int(eng_["track"]))
                if tr_ is None or tr_.box is None:
                    eng_["death"] = {"cell": None, "reason": "no_track"}
                    return
                prev_ = split._cat
                split.to("looting", time.monotonic())
                try:
                    bx = dict(tr_.boxes)
                    t_from = int(eng_["t_first_click"]) - int(2e9)
                    sights = [dcm_.Sighting(int(t_), None if (b_ := bx.get(int(t_))) is None
                                            else (b_.x0, b_.y0, b_.x1, b_.y1))
                              for t_, _bs in sampler.since(0) if int(t_) >= t_from]  # fmt: skip
                    lt = loot1.Track(f1.foot(tr_.box))
                    lt.sightings = sights
                    dead_ = loot1.death_of(rig, lt, here2)
                    eng_["death"] = {"cell": None if dead_.cell is None else list(dead_.cell),
                                     "reason": dead_.reason}  # fmt: skip
                    if dead_.cell is not None and dead_.gone_ns is not None:
                        loot1.loot(rig, here2, dead_, eng_)
                finally:
                    split.to(prev_, time.monotonic())

            def gate_risks(tr: Track, here: Cell) -> list[str]:
                """v10: the target's box on the FRESHEST frame and the strict rule's inputs."""
                fr0 = sampler.since(max(0, len(sampler.frames) - 1))
                if (
                    not fr0
                    or tr.box is None
                    or (r.ns() - fr0[-1][0]) / 1e9 > prm.get("gate_fresh_s", prm["fresh_s"])
                ):
                    return ["stale_box"]  # fmt: skip
                near0 = [x for x, c in sightings_in(fr0[-1][1], here)
                         if cheb(c, tr.predict(fr0[-1][0])) <= prm["track_near"]]  # fmt: skip
                if not near0:
                    return ["no_box"]
                b0 = min(near0, key=lambda x: float(np.hypot(*(np.array(f1.foot(x))
                                                                - f1.foot(tr.box)))))  # fmt: skip
                others = [o for o in fr0[-1][1] if o is not b0]
                pc0 = tr.predict(r.ns())
                npc_near = any(cheb(pc0, (int(n_["x"]), int(n_["y"]))) <= prm["gate_npc_cells"]
                               for n_ in npcs)  # fmt: skip
                ignore_near = False
                for o in others:
                    if o.cls != "monster":
                        continue
                    if float(np.hypot(*(np.array(f1.centre(o)) - f1.centre(b0)))) > prm[
                            "gate_ignore_px"]:  # fmt: skip
                        continue
                    c_o, sc_o = cell_of(o, here)
                    if c_o is not None and f1.native_size(o, sc_o) > f1.MAX_NATIVE_PX:
                        ignore_near = True  # a Creamy (no target) next to it
                return gate_reasons(b0, others, GM_SPRITE_PX, prm["gate_near_gm_px"],
                                    prm["gate_min_conf"], npc_near, ignore_near)  # fmt: skip

            def strike(tr: Track, here: Cell, again: bool) -> bool:
                """Park, hover the target's newest box, ONE robust2 read; SWORD -> the attack
                click there. True when it clicked."""
                nonlocal eng, k, reads
                prev = split._cat
                split.to("striking", time.monotonic())
                t_call0 = time.monotonic()
                fast_ = bool(prm.get("fast_read"))
                gate_why: list[str] = []
                direct_ = False
                if prm.get("risk_gate"):  # v10: the read only where there is real risk
                    gate_why = gate_risks(tr, here)
                    direct_ = not gate_why
                ok_park = True if (fast_ or direct_) else pr.park()
                park_ms = round((time.monotonic() - t_call0) * 1000)
                fr = sampler.since(max(0, len(sampler.frames) - 1))
                b = tr.box
                if fr and (r.ns() - fr[-1][0]) / 1e9 <= prm["fresh_s"]:
                    near_ = [x for x, c in sightings_in(fr[-1][1], here)
                             if cheb(c, tr.predict(fr[-1][0])) <= prm["track_near"]]  # fmt: skip
                    if near_:
                        b = min(near_, key=lambda x: np.hypot(*(np.array(f1.foot(x))
                                                                 - f1.foot(tr.box))))  # fmt: skip
                u, v = f1.centre(b)
                if (prm.get("still_gate") and ok_park and tr.box is not None
                        and b is not tr.box and float(np.hypot(*(np.array(f1.centre(b))
                                                               - f1.centre(tr.box))))
                        > prm["still_px"]):  # fmt: skip
                    # v9: it moved during the park -- no read now (none counted); the gate waits
                    ev({"kind": "strike_moved", "track": tr.tid})
                    split.to(prev, time.monotonic())
                    return False
                if not ok_park or loot1.in_ui(u, v):
                    if prm.get("strike_lean") and not ok_park:
                        # v8: a STALE park (the drawn cursor never showed at the park point in
                        # 1.5 s) counts as a failed read; v7 parked again at once, unbounded
                        reads += 1
                        ev({"kind": "park_stale", "track": tr.tid, "park_ms": park_ms})
                    split.to(prev, time.monotonic())
                    return False
                t_read0 = r.ns()
                path_ = "std"
                reads_why: list[list[Any]] = []  # v9: each read's shape / why / best
                if direct_:
                    shape, path_ = "direct", "direct"  # v10: no risk -> the fresh detection
                elif fast_:
                    # v8: the FAST read -- the pointer is on the sprite (it follows), grab, blink
                    # it away, two background grabs, robust2 on |A - B|; unknown -> the proven read
                    import fast_read as fread

                    cs_ = [f1.centre(x) for x in (fr[-1][1] if fr else []) if x is not b]
                    bp_ = fread.blink_point(u, v, cs_, in_view)
                    shape = "unknown"
                    if bp_ is not None:
                        fread.glide(agent, (gx0, gy0), ptr[0], (u, v))
                        time.sleep(fread.SETTLE_S)
                        fres = fread.read(pr, agent, screen, (gx0, gy0), u, v, bp_)
                        shape, path_ = str(fres["shape"]), "fast"
                        ptr[0] = bp_
                    if shape == "unknown" and pr.park():
                        pr.hover(u, v)
                        shape, path_ = pr.read(u, v)["shape"], "fast>std"
                elif prm.get("short_read"):
                    # v6: back from the park in small moves (the client draws its cursor during
                    # continuous travel, ~0.15-0.2 s behind: 13:24's test), a short settle, the
                    # proven read; anything but SWORD -> the standard hover, read once more
                    import walk6 as w6_

                    pu, pv = w6_.PARKS[pr.parked]
                    for i_ in range(1, 7):
                        agent.move(gx0 + round(pu + (u - pu) * i_ / 6),
                                   gy0 + round(pv + (v - pv) * i_ / 6))  # fmt: skip
                        time.sleep(0.012)
                    time.sleep(prm["hover_settle_s"])
                    rd_ = pr.read(u, v)
                    shape = rd_["shape"]
                    reads_why.append([shape, rd_.get("why"), rd_.get("best")])
                    if shape != "sword":
                        pr.hover(u, v)
                        rd_ = pr.read(u, v)
                        shape = rd_["shape"]
                        reads_why.append([shape, rd_.get("why"), rd_.get("best")])
                else:
                    pr.hover(u, v)
                    shape = pr.read(u, v)["shape"]
                pc = tr.predict(r.ns())
                hov = {"t": r.ns(), "at": [round(u, 1), round(v, 1)], "read": shape, "path": path_,
                       "park_ms": park_ms, "call_ms": round((time.monotonic() - t_call0) * 1000),
                       "age_ms": round((r.ns() - tr.box_t) / 1e6),
                       "pred_cell": [round(pc[0], 2), round(pc[1], 2)]}  # fmt: skip
                ev({"kind": "strike_call", "track": tr.tid, "read": shape, "path": path_,
                    "park_ms": park_ms, "call_ms": hov["call_ms"], "again": again,
                    "reads": reads_why, "age_ms": hov["age_ms"],
                    "branch": "direct" if direct_ else "read", "risk": gate_why})  # fmt: skip
                if shape != "sword" and not direct_:
                    reads += 1
                    note(f"read {shape}: no click")
                    if eng is not None:
                        eng["hovers"].append(hov)
                    split.to(prev, time.monotonic())
                    return False
                tc = r.ns()
                agent.click(gx0 + round(u), gy0 + round(v))
                cmd_hist.append((int(tc), (int(round(pc[0])), int(round(pc[1])))))
                del cmd_hist[:-40]
                hov["clicked"] = tc
                hov["read_ms"] = round((tc - t_read0) / 1e6)
                # v6: the AIM ERROR -- the click point to the target's sprite centre on the
                # freshest frame (px), and the time from "in range" to this click
                fr2 = sampler.since(max(0, len(sampler.frames) - 1))
                if fr2:
                    near2 = prm["track_near"] + 1
                    cand_ = [x for x, c in sightings_in(fr2[-1][1], here)
                             if cheb(c, tr.predict(fr2[-1][0])) <= near2]  # fmt: skip
                    if cand_:
                        cx_, cy_ = f1.centre(min(cand_, key=lambda x: float(np.hypot(
                            *(np.array(f1.centre(x)) - (u, v))))))  # fmt: skip
                        hov["aim_px"] = round(float(np.hypot(u - cx_, v - cy_)), 1)
                if in_range_since.get(tr.tid) is not None:
                    hov["in_range_to_click_s"] = round(tc / 1e9 - in_range_since[tr.tid], 2)
                ptr[0] = (u, v)
                if prm.get("strike_lean"):
                    # v8 attempt 2: the pointer OFF the monster at once (no park, no wait). The
                    # park after the click had a hidden job: attempt 1 left the drawn cursor on
                    # the sprite, the detector lost it, and "dead" fired 1.0 s after each click
                    import fast_read as fread

                    cs2 = [f1.centre(x) for x in (fr[-1][1] if fr else []) if x is not b]
                    off_ = fread.blink_point(u, v, cs2, in_view) or (u, v - 90.0)
                    agent.move(gx0 + round(off_[0]), gy0 + round(off_[1]))
                    ptr[0] = off_
                elif not fast_:
                    pr.park()
                click_log({"t": tc, "u": round(u, 1), "v": round(v, 1), "kind": "strike",
                           "track": tr.tid, "pred_cell": hov["pred_cell"], "again": again,
                           "aim_px": hov.get("aim_px"), "read_ms": hov.get("read_ms"),
                           "in_range_to_click_s": hov.get("in_range_to_click_s"),
                           "read_path": path_, "branch": "direct" if direct_ else "read",
                           "risk": gate_why})  # fmt: skip
                eng_tracks[tr.tid] = tr  # v6: the death cell and the loot read its boxes
                if eng is None or eng["track"] != tr.tid:
                    eng = {"k": k, "track": tr.tid, "t_seen": tr.t_first, "t_first_click": tc,
                           "here": list(here), "pred_cell": hov["pred_cell"], "hovers": [],
                           "clicks": 0, "result": None}  # fmt: skip
                    k += 1
                eng["hovers"].append(hov)
                eng["clicks"] += 1
                eng["t_last_click"] = tc
                reads = 0
                note(f"SWORD -> attack click {eng['clicks']} (track {tr.tid})", [b])
                split.to("fighting", time.monotonic())
                last_progress[0] = time.monotonic()
                return True

            done_ids: set[int] = set()  # v4: engaged tracks never dispatched again

            def end_engagement(result: str) -> None:
                nonlocal eng, target
                if eng is not None:
                    done_ids.add(int(eng["track"]))
                    eng.update(result=result, t_end=r.ns())
                    engagements.append(eng)
                    brief = {k_: eng.get(k_) for k_ in ("k", "track", "result", "clicks")}
                    ev({"kind": "engagement", **brief})
                    print(json.dumps(brief), flush=True)
                eng = None
                target = None

            # --- v2: PIPELINED (Batt ~11:30): perception + planner threads, the executor below --
            halt = threading.Event()
            pstate: dict[str, Any] = {"tracks": [], "next_id": 0}
            world_p = w5.World(camera, gat, start)  # the perception thread's own camera model

            def tracks_now() -> list[Track]:
                with plock:
                    return list(pstate["tracks"])

            def perception() -> None:
                """Every detector frame into the tracks, on the frame's own time and our cell
                then (the shared position model)."""
                kf_ = 0
                while not halt.is_set():
                    new_ = sampler.since(kf_)
                    kf_ += len(new_)
                    for t_fr, boxes in new_:
                        age = (r.ns() - t_fr) / 1e9
                        here_fr = posm.at(time.monotonic() - age)
                        frac_ = (0.0, 0.0)
                        if prm.get("frame_cells"):  # v6: MEASURED at the frame's own time
                            fp = pos_at_frame(int(t_fr))
                            if fp is not None:
                                here_fr = (int(round(fp[0])), int(round(fp[1])))
                                frac_ = (fp[0] - here_fr[0], fp[1] - here_fr[1])
                        sts = sightings_in(boxes, here_fr, world_p, frac_)
                        with plock:
                            pstate["tracks"], pstate["next_id"] = update_tracks(
                                pstate["tracks"], t_fr, sts, pstate["next_id"],
                                prm["track_near"], prm["track_drop_s"])  # fmt: skip
                    if not new_:
                        time.sleep(0.02)

            main_area = main_component(area) if prm.get("escape_after_s") else None
            trail: list[tuple[float, Cell]] = []  # v8 attempt 2: (mono s, cell) we stood on

            def planner() -> None:
                """The queue (chained, standing first) every plan_every_s, and the next exploration
                waypoint (the coverage plan's stalest tile) always held."""
                while not halt.is_set():
                    now_, t_ = time.monotonic(), r.ns()
                    here_ = posm.at(now_)
                    q = plan_queue(tracks_now(), here_, t_, prm["queue_depth"], list(banned),
                                   now_, prm["drop_target_s"], prm["moving_penalty"])  # fmt: skip
                    gp = plan["goal_path"]
                    left_ = 999
                    if gp and prm.get("replan_left"):  # v5: never walk off the route's end
                        ci_ = min(range(len(gp)), key=lambda i_: cheb(gp[i_], here_))
                        left_ = len(gp) - 1 - ci_
                    if (gp is None or now_ - plan["t_goal"] > prm["waypoint_every_s"]
                            or cheb(here_, gp[-1]) <= 2
                            or left_ < prm.get("replan_left", -1)):  # fmt: skip
                        p_ = None
                        if area[here_[1], here_[0]]:
                            goal = hc.choose_goal(cov, here_, now_, {}, list(bad_tiles))
                            p_ = None if goal is None else hc.astar(area, here_, goal)
                            if (p_ is None or len(p_) < 2) and goal is not None:
                                bad_tiles.append((goal[0] - goal[0] % hc.TILE,
                                                  goal[1] - goal[1] % hc.TILE))  # fmt: skip
                                if len(bad_tiles) > 40:
                                    bad_tiles.clear()
                        else:
                            back = hc.nearest_in(area, ok, here_)
                            p_ = None if back is None else hc.astar(ok, here_, back)
                        if p_ is not None and len(p_) >= 2:
                            gp = p_
                            plan["t_fail"] = None
                            plan["escape"] = False
                            with plock:
                                plan["t_goal"] = now_
                        elif main_area is not None:
                            # v8 bug fix: no goal has a path from here (a ledge strip) -> after
                            # escape_after_s walk the full walkable grid to the main area
                            plan["t_fail"] = plan.get("t_fail") or now_
                            if now_ - plan["t_fail"] > prm["escape_after_s"]:
                                with plock:
                                    tr_ = list(trail)
                                cands_ = [*trail_cells(tr_, here_, now_),
                                          *escape_cells(main_area, here_, near=6)]  # fmt: skip
                                for c_ in cands_:
                                    p_ = hc.astar(ok, here_, c_)
                                    if p_ is not None and len(p_) >= 2:
                                        gp, plan["t_fail"] = p_, None
                                        plan["escape"] = True  # clicked on the walkable grid
                                        ev({"kind": "escape", "from": list(here_), "to": list(c_)})
                                        with plock:
                                            plan["t_goal"] = now_
                                        break
                    with plock:
                        plan["queue"], plan["goal_path"] = q, gp
                    time.sleep(prm["plan_every_s"])

            def quick_fix() -> Cell:
                """Our cell at a hand-off: one minimap read near where we were (no settle wait),
                else the settle."""
                mm_ = read_position()
                if mm_ is not None and ok[mm_[1], mm_[0]] and cheb(mm_, pos) <= 4:
                    return mm_
                return settle(timeout=1.5) or pos

            # --- v5: MEASURED motion (route_preview's floor odometry) + the shadow cursor read ----
            mstate: dict[str, Any] = {"hist": [], "anchor": None}

            def motion() -> None:
                """~motion_hz frames: the camera's move from the floor patches, summed (cells)."""
                import route_preview as rp_

                core = rp_.PreviewCore(camera, gat, (gx0, gy0, gw, gh), r.desktop())
                scr = r.Screen()
                prev_img = prev_g = None
                odo = np.zeros(2)
                try:
                    while not halt.is_set():
                        t_, img_ = scr.grab(gx0, gy0, gw, gh)
                        img3 = np.ascontiguousarray(np.asarray(img_)[..., :3])
                        g_ = rp_.gray(img3)
                        if prev_g is None or bool(np.any(g_ != prev_g)):
                            mstate["changed_t"] = time.monotonic()  # v10: the picture is live
                        if prev_g is not None:
                            off_ = rp_.scene_shift(prev_img, img3)
                            c_ = np.array(posm.at(time.monotonic()), dtype=float)
                            d_, _n = core.camera_move(prev_g, g_, c_, off_)
                            if d_ is None:
                                d_ = -core.jinv @ np.array(off_)
                            odo = odo + d_
                            with plock:
                                mstate["hist"].append((int(t_), odo.copy()))
                                if len(mstate["hist"]) > 300:
                                    del mstate["hist"][:150]
                        prev_img, prev_g = img3, g_
                        time.sleep(max(0.0, 1.0 / prm["motion_hz"] - 0.03))
                finally:
                    scr.close()

            def hist_now() -> list[tuple[int, Any]]:
                with plock:
                    return list(mstate["hist"])

            def measured_pos() -> tuple[float, float] | None:
                """v5: the minimap's last cell + the floor odometry since that read."""
                a_, h_ = mstate["anchor"], hist_now()
                if a_ is None or not h_ or a_[1] is None:
                    return None
                d_ = h_[-1][1] - a_[1]
                return a_[0][0] + float(d_[0]), a_[0][1] + float(d_[1])

            def pos_at_frame(t_ns: int) -> tuple[float, float] | None:
                """v6: our measured cell at ``t_ns`` (the minimap anchor + odometry then)."""
                a_, h_ = mstate["anchor"], hist_now()
                if a_ is None or not h_ or a_[1] is None:
                    return None
                o_ = odo_at(h_, t_ns)
                if o_ is None:
                    return None
                return a_[0][0] + float(o_[0] - a_[1][0]), a_[0][1] + float(o_[1] - a_[1][1])

            def moving_meas() -> bool:
                h_ = hist_now()
                if len(h_) < 2:
                    return False
                old = odo_at(h_, h_[-1][0] - int(0.3e9))
                return old is not None and float(np.abs(h_[-1][1] - old).max()) > prm[
                    "moving_cells"]  # fmt: skip

            ui_verdict: dict[str, Any] = {}

            def ui_watch() -> None:
                """v5 attempt 2: the UI gate's pixel check + the HP check every CHECK_EVERY_S on
                its own frames (no input: park=False), never blocking the executor."""
                scr = r.Screen()
                try:
                    while not halt.is_set():
                        st = f0.client_state(agent, scr)
                        hp_ = gm_vitals.hp_fraction(
                            np.asarray(scr.grab(gx0, gy0, gw, gh)[1])[..., :3])  # fmt: skip
                        with plock:
                            ui_verdict.update(t=time.monotonic(), decision=st["decision"],
                                              frame=st["frame"], hp=hp_)  # fmt: skip
                        halt.wait(CHECK_EVERY_S)
                finally:
                    scr.close()

            shadow_q: list[tuple[int, float, float]] = []

            def shadow() -> None:
                """v5 SHADOW (never deciding): the cursor shape drawn at each walk click's point
                ~0.2 s later, by colour (palette_mask) and robust2's matcher; logged only."""
                import walk6 as w6_

                scr = r.Screen()
                try:
                    while not halt.is_set():
                        if not shadow_q:
                            time.sleep(0.02)
                            continue
                        t_c, u_, v_ = shadow_q.pop(0)
                        wait_ = 0.2 - (r.ns() - t_c) / 1e9
                        if wait_ > 0:
                            time.sleep(wait_)
                        x_, y_ = int(round(u_)), int(round(v_))
                        _t, crop_ = scr.grab(gx0 + x_ - 32, gy0 + y_ - 32, 64, 64)
                        a_ = np.ascontiguousarray(np.asarray(crop_)[..., :3])
                        if a_.shape[:2] != (64, 64):
                            continue
                        pal = palette_mask(a_)
                        b_ = a_.copy()
                        b_[pal] = 255 - a_[pal]
                        got_ = pr.refs.match(a_, w6_.cursor_mask(a_, b_))
                        ev({"kind": "shadow_read", "t_click": t_c, "shape": got_.get("shape"),
                            "at": [round(u_, 1), round(v_, 1)]})  # fmt: skip
                finally:
                    scr.close()

            def pipelined_loop() -> None:  # noqa: PLR0915
                nonlocal pos, moving, path, pi, target, reads, last_mm, mm_off, last_weight
                nonlocal click_from, click_cell
                ths = [_start_thread(perception, "perception"), _start_thread(planner, "planner")]
                cont = bool(prm.get("continuous"))
                if cont:
                    ths += [_start_thread(motion, "motion")]
                    if prm.get("shadow_cursor"):
                        ths += [_start_thread(shadow, "shadow")]
                if prm.get("bg_check"):
                    ths += [_start_thread(ui_watch, "ui_watch")]
                pos_changed: dict[str, Any] = {"t": time.monotonic(), "cell": pos}
                recent_clicks: list[Cell] = []
                jumps: list[Cell] = []  # v7: minimap reads far from the measured cell

                def mm_crop() -> Any:
                    mx, my, mw, mh = MINIMAP_IMG
                    return np.asarray(frame())[my : my + mh, mx : mx + mw, :3].copy()

                mm_ref = mm_crop() if prm.get("jump_reanchor") else None  # the run's map
                route_shown: list[Any] = [None]
                gp_i = 0
                follow_t = [0]  # v6: the last box time the pointer followed
                still_wait: dict[int, float] = {}  # v9: track -> since when waiting for it to stand
                t_target = [0.0]  # v11: when the current target was set
                dispatched: set[tuple[int, bool]] = set()
                stop_since: float | None = None  # v5: since when standing with no click
                last_click: dict[str, Any] = {}  # v5: the last walk click (unfollowed check)
                mode_ = ""

                def set_mode(m_: str) -> None:
                    nonlocal mode_
                    if m_ != mode_:
                        mode_ = m_
                        ev({"kind": "mode", "mode": m_})

                def boxes_clear(u: float, v: float) -> bool:
                    """v8 plan B: (u, v) is outside every monster box of the NEWEST frame grown by
                    box_clear_px (the sprite is what the client picks, not its centre)."""
                    px_ = prm.get("box_clear_px")
                    if px_ is None:
                        return True
                    fr_ = sampler.since(max(0, len(sampler.frames) - 1))
                    return not fr_ or all(
                        not (b.x0 - px_ <= u <= b.x1 + px_ and b.y0 - px_ <= v <= b.y1 + px_)
                        for b in fr_[-1][1] if b.cls == "monster")  # fmt: skip

                def cont_click(route: list[Cell], grid: Any, why: str,
                               avoid: tuple[float, float] | None = None) -> bool:  # fmt: skip
                    """v5: the first candidate ahead of where we ARE that passes the gates on the
                    freshest frames; no standstill needed."""
                    cur = measured_pos() or (float(pos[0]), float(pos[1]))
                    lead_ = None
                    if prm.get("lead_from") == "commands":  # v7 attempt 2: our own commands
                        lead_ = commanded_lead(cur, list(cmd_hist), r.ns(),
                                               prm["click_lead_s_commands"])  # fmt: skip
                    elif prm.get("click_lead_s"):  # v7 attempt 1: the measured velocity
                        vel_ = odo_velocity(hist_now(), prm["lead_window_s"])
                        lead_ = lead_origin(cur, vel_, prm["click_lead_s"])
                    src_ = lead_ or cur
                    at_ = (int(round(src_[0])), int(round(src_[1])))
                    world.position = at_
                    for j_ in ahead_candidates(route, src_, prm["ahead_order"]):
                        c_ = route[j_]
                        if lead_ is not None:
                            uu, vv = frac_project(world, lead_, c_)  # the click
                            gu, gv = frac_project(world, cur, c_)  # the frames' own pixel
                        else:
                            uu, vv = (float(x) for x in world.project([c_])[0])
                            gu, gv = uu, vv
                        if avoid is not None and prm.get("steer_clear_cells") and cheb(
                                c_, avoid) < prm["steer_clear_cells"]:  # fmt: skip
                            continue  # v8 plan B: never a steering click onto the target
                        if (in_view(uu, vv) and in_view(gu, gv) and grid[c_[1], c_[0]]
                                and units_clear(gu, gv) and boxes_clear(gu, gv)
                                and (not cont or walk_ok(c_))):  # fmt: skip
                            extra_ = None
                            if lead_ is not None:
                                d_ = [round(lead_[0] - cur[0], 2), round(lead_[1] - cur[1], 2)]
                                extra_ = {"at": [round(cur[0], 2), round(cur[1], 2)], "lead": d_}
                            if walk_click(uu, vv, c_, [at_, c_], "map+units", why, extra_):
                                last_click.update(t=time.monotonic(), cell=c_, frm=at_)
                                recent_clicks.append(c_)
                                if prm.get("publish_route") and route_shown[0] is not route:
                                    route_shown[0] = route
                                    rp("route", at_, hc.waypoints(route))
                                if prm.get("shadow_cursor"):
                                    shadow_q.append((r.ns(), uu, vv))
                                return True
                            world.position = at_
                    return False

                def walk_ok(c_: Cell) -> bool:
                    return not refusals.get(c_, 0) >= 2

                try:
                    while time.monotonic() < deadline:
                        now = time.monotonic()
                        ch_t = mstate.get("changed_t")
                        if (prm.get("freeze_guard") and ch_t is not None
                                and now - ch_t > FREEZE_S and last_walk > ch_t + 0.5):  # fmt: skip
                            # v10 safety (v9 attempt 2, 17:59: the client stopped redrawing while
                            # it still took input; the bot clicked blind 60 s): no input on a
                            # stale picture
                            raise f0.FarmStop(
                                f"the picture froze ({now - ch_t:.1f} s identical "
                                f"after a walk click): a frozen client display"
                            )
                        if (prm.get("escape_after_s") and eng is None
                                and now - last_progress[0] > STUCK_S):  # fmt: skip
                            raise f0.FarmStop(f"no progress for {STUCK_S:.0f} s at {pos}: stopped")
                        if prm.get("bg_check"):
                            with plock:
                                vd = dict(ui_verdict)
                            if vd and vd["decision"]["do"] != "clear":
                                stop_png = log.dir / f"stop-{len(engagements)}.png"
                                shot = r.to_png(vd["frame"], stop_png)
                                raise f0.FarmStop(f"client state (background check): "
                                                  f"{vd['decision']} (frame {shot})")  # fmt: skip
                            if vd and vd["hp"] < f0.HP_STOP:
                                raise f0.FarmStop(f"HP {vd['hp']:.2f}: an immune GM lost HP")
                        elif eng is None and now - last_check[0] > CHECK_EVERY_S:
                            check("v2")
                        if eng is None and not moving and now - last_weight > WEIGHT_EVERY_S:
                            last_weight = now
                            wnow = gm_state._weight(gm_state._frames(screen))
                            if gm_state.weight_action(wnow, at_restore=False) == "clear":
                                ev({"kind": "weight_clear", "weight": wnow})
                                gm_state.clear_loot(agent, screen, why="hunt-flow:mid-run",
                                                    out_dir=log.dir / "gm_state")  # fmt: skip
                        if cont:
                            # v5: MEASURED -- the minimap's cell + the floor odometry since it
                            if now - last_mm > MINIMAP_EVERY_S:
                                last_mm = now
                                t_mm = r.ns()
                                mm = read_position()
                                mp0_ = measured_pos()
                                if (prm.get("click_lead_s") and mm is not None and mp0_ is not None
                                        and cheb(mm, mp0_) > JUMP_CELLS):  # fmt: skip
                                    # v7: a position JUMP (a map change, a warp): two reads agree
                                    jumps.append(mm)
                                    if len(jumps) >= 2 and jumps[-1] == jumps[-2]:
                                        same_ = mm_ref is not None and map_same(
                                            mm_ref, mm_crop())  # fmt: skip
                                        if not prm.get("jump_reanchor") or not same_:
                                            raise f0.FarmStop(
                                                f"position jump {mp0_} -> {mm}: a map change or "
                                                f"a warp? (minimap picture same: {same_}) stopped"
                                            )
                                        # v9 attempt 2: the same map -> the odometry lagged;
                                        # the minimap is right: re-anchor on it
                                        ev({"kind": "reanchor", "from": [round(mp0_[0], 1),
                                                                         round(mp0_[1], 1)],
                                            "to": list(mm)})  # fmt: skip
                                        mstate["anchor"] = (mm, odo_at(hist_now(), t_mm))
                                        jumps.clear()
                                    continue
                                jumps.clear()
                                on_ = mm is not None and 0 <= mm[1] < ok.shape[0] and (
                                    0 <= mm[0] < ok.shape[1])  # fmt: skip
                                if on_ and ok[mm[1], mm[0]]:
                                    mstate["anchor"] = (mm, odo_at(hist_now(), t_mm))
                                    last_fix[0] = time.monotonic()
                            moving = moving_meas()
                            mp_ = measured_pos()
                            if mp_ is not None:
                                pos = (int(round(mp_[0])), int(round(mp_[1])))
                            posm.stop(pos)
                            # a walk click the client did not follow (no motion 1.2 s later)
                            if (last_click and not moving and now - last_click["t"] > 1.2
                                    and cheb(pos, last_click["frm"]) <= 1):  # fmt: skip
                                ev({"kind": "unfollowed_click", "from": list(last_click["frm"]),
                                    "to": list(last_click["cell"])})  # fmt: skip
                                refuse(last_click["cell"], "unfollowed")
                                last_click.clear()
                            elif last_click and moving:
                                last_click.clear()
                            if cheb(pos, pos_changed["cell"]) >= 1:
                                pos_changed.update(t=now, cell=pos)
                                recent_clicks.clear()
                                with plock:
                                    trail.append((now, pos))
                                    del trail[:-400]
                            elif (prm.get("stall_s") and eng is None and len(recent_clicks) >= 2
                                    and now - pos_changed["t"] > prm["stall_s"]):  # fmt: skip
                                # attempt 2: clicks went out and the GM did not move: block them
                                ev({"kind": "stall", "at": list(pos),
                                    "cells": [list(c_) for c_ in recent_clicks[-8:]]})  # fmt: skip
                                for c_ in set(recent_clicks):
                                    refuse(c_, "stall_noentry")
                                recent_clicks.clear()
                                pos_changed.update(t=now, cell=pos)
                                with plock:
                                    plan["goal_path"] = None
                        if not cont and moving and reck.remaining(now) == 0:
                            moving = False
                            pos = reck.path[-1] if reck.path else pos
                            posm.stop(pos)
                            rp("snap", pos)
                        est = reck.where(now) if (moving and not cont) else pos
                        if est is not None:
                            pos = est
                        if not cont and now - last_mm > MINIMAP_EVERY_S:
                            last_mm = now
                            mm = read_position()
                            if mm is not None and ok[mm[1], mm[0]]:
                                if cheb(mm, pos) <= DRIFT_CELLS:
                                    mm_off = 0
                                    last_fix[0] = time.monotonic()
                                    if not moving:
                                        pos = mm
                                        posm.stop(pos)
                                else:
                                    mm_off += 1
                                    if mm_off >= 2:
                                        ev({"kind": "drift", "reck": list(pos),
                                            "minimap": list(mm)})  # fmt: skip
                                        if (click_from is not None and click_cell is not None
                                                and cheb(mm, click_from) <= 1
                                                and eng is None):  # fmt: skip
                                            n_u = unfollowed.get(click_from, 0)
                                            unfollowed[click_from] = n_u + 1
                                            rad = 1 + min(2, n_u)
                                            cx, cy = click_cell
                                            blk = np.zeros_like(area)
                                            blk[max(0, cy - rad) : cy + rad + 1,
                                                max(0, cx - rad) : cx + rad + 1] = True  # fmt: skip
                                            fx, fy = click_from
                                            blk[max(0, fy - 1) : fy + 2,
                                                max(0, fx - 1) : fx + 2] = False  # fmt: skip
                                            area[blk] = False
                                            ev({"kind": "unfollowed_click",
                                                "from": list(click_from),
                                                "to": list(click_cell), "radius": rad})  # fmt: skip
                                            click_from = click_cell = None
                                        pos = settle() or mm
                                        posm.stop(pos)
                                        moving, path, pi = False, [], 0
                                        mm_off = 0
                        pos_box[0] = pos
                        cov.mark(pos, now, offsets)
                        t_now = r.ns()
                        live = tracks_now()
                        need_c = moving or bool(prm.get("track_clear"))  # v3: the gate everywhere
                        # the engagement in progress: dead -> HAND-OFF at once; re-click; give up
                        if eng is not None:
                            if cont:
                                set_mode("engaged")
                            tr = next((x for x in live if x.tid == eng["track"]), None)
                            since_first = (t_now - eng["t_first_click"]) / 1e9
                            since_last = (t_now - eng["t_last_click"]) / 1e9
                            unseen = (t_now - tr.t_last) / 1e9 if tr is not None else 99.0
                            done = None
                            if since_last >= prm["dead_min_s"] and unseen >= prm["dead_gone_s"]:
                                done = "dead"
                            elif since_first > prm["give_up_s"]:
                                banned.append((now, tuple(int(x) for x in eng["pred_cell"])))
                                done = "gave_up"
                            if done is None:
                                if since_last >= prm["reclick_s"] and tr is not None and not moving:
                                    strike(tr, pos, again=True)
                                time.sleep(0.02)
                                continue
                            if done == "dead" and prm.get("loot"):
                                time.sleep(0.4)  # the frames after the death (gone frames)
                                here_l = quick_fix()
                                posm.stop(here_l)
                                loot_after(eng, here_l)
                            end_engagement(done)
                            ev({"kind": "hand_off", "after": done})
                            pos = quick_fix()
                            posm.stop(pos)
                            moving, path, pi = False, [], 0
                            live = tracks_now()
                            t_now = r.ns()
                        with plock:
                            q, gp = list(plan["queue"]), plan["goal_path"]
                        # dispatch: queue[0], revalidated on the freshest frame
                        if target is not None and not valid_at_dispatch(
                                target, live, t_now, prm["track_drop_s"]):  # fmt: skip
                            nt = None
                            if prm.get("reacquire"):  # v4: the same monster under a new id
                                nt = reacquire_target(target, live, t_now,
                                                      prm["reacquire_cells"],
                                                      list(done_ids))  # fmt: skip
                            if nt is not None:
                                ev({"kind": "target_reacquired", "track": target.tid,
                                    "as": nt.tid})  # fmt: skip
                                target = nt
                            else:
                                ev({"kind": "target_lost", "track": target.tid})
                                target = None
                        if (prm.get("retarget") and target is not None and eng is None and q
                                and now - t_target[0] >= prm["retarget_commit_s"]):  # fmt: skip
                            # v11: while steering, switch to the planner's better queue[0]
                            # (v7: the unit was in sight p50 2.85 s before its dispatch, in
                            # 19 / 32 while the bot steered to ANOTHER target that then failed)
                            q0 = next((c_ for c_ in q if c_.tid not in done_ids and not any(
                                now - tb < prm["drop_target_s"] and cheb(c_.predict(t_now), cb) <= 2
                                for tb, cb in banned)), None)  # fmt: skip
                            if (
                                q0 is not None
                                and q0.tid != target.tid
                                and valid_at_dispatch(q0, live, t_now, prm["dispatch_fresh_s"])
                                and target_cost(q0, pos, t_now, prm["moving_penalty"])
                                + prm["retarget_margin"]
                                <= target_cost(target, pos, t_now, prm["moving_penalty"])
                            ):
                                ev({"kind": "retarget", "from": target.tid, "to": q0.tid})
                                target, reads = q0, 0
                                t_target[0] = now
                        if target is None and q:
                            for rank, cand in enumerate(q):
                                if prm.get("dispatch_fixes") and (
                                        cand.tid in done_ids or any(
                                            now - tb < prm["drop_target_s"]
                                            and cheb(cand.predict(t_now), cb) <= 2
                                            for tb, cb in banned)):  # fmt: skip
                                    continue  # v4: a finished or dropped target, not again
                                ok_ = valid_at_dispatch(cand, live, t_now, prm["dispatch_fresh_s"])
                                if (cand.tid, ok_) not in dispatched:  # one record per candidate
                                    dispatched.add((cand.tid, ok_))
                                    pc_ = cand.predict(t_now)
                                    ev({"kind": "dispatch", "track": cand.tid, "rank": rank,
                                        "q_len": len(q), "valid": ok_,
                                        "cell": [round(pc_[0], 1), round(pc_[1], 1)]})  # fmt: skip
                                if ok_:
                                    target, reads = cand, 0
                                    t_target[0] = now
                                    break
                        if target is not None:
                            split.to("steering", time.monotonic())
                            tcell = target.predict(t_now)
                            s_range = strike_range(target, prm)
                            fresh_box = (t_now - target.box_t) / 1e9 <= prm["fresh_s"]
                            if (prm.get("follow_mouse") and target.box_t > follow_t[0]
                                    and fresh_box):  # fmt: skip
                                # v6: the POINTER FOLLOWS the sprite on every fresh frame
                                fu_, fv_ = f1.centre(target.box)
                                if not loot1.in_ui(fu_, fv_):
                                    agent.move(gx0 + round(fu_), gy0 + round(fv_))
                                    ptr[0] = (fu_, fv_)
                                follow_t[0] = target.box_t
                            if cheb(pos, tcell) <= s_range:
                                in_range_since.setdefault(target.tid, time.monotonic())
                            if strike_due(moving, pos, tcell, s_range):
                                if prm.get("still_gate") and not box_still(
                                        target.boxes, r.ns(), prm["still_s"],
                                        prm["still_px"]):  # fmt: skip
                                    # v9: no read until the target STANDS (the pointer keeps
                                    # following it); dropped when it never does in still_wait_s
                                    t_w = still_wait.setdefault(target.tid, now)
                                    if now - t_w > prm["still_wait_s"]:
                                        banned.append((now, (int(round(tcell[0])),
                                                             int(round(tcell[1])))))  # fmt: skip
                                        ev({"kind": "target_dropped", "track": target.tid,
                                            "why": "no_still"})  # fmt: skip
                                        target = None
                                    time.sleep(0.02)
                                    continue
                                if (not strike(target, pos, again=False)
                                        and reads >= prm["max_reads"]):  # fmt: skip
                                    banned.append((now, (int(round(tcell[0])),
                                                         int(round(tcell[1])))))  # fmt: skip
                                    ev({"kind": "target_dropped", "track": target.tid,
                                        "why": "no_sword", "reads": reads})  # fmt: skip
                                    target = None
                                continue
                            if cheb(pos, tcell) <= s_range:
                                time.sleep(0.02)  # walking, about to arrive: the strike is next
                                continue
                            if cont:  # v5: steer continuously, no standstill gate
                                set_mode("steer")
                                due = now - last_walk >= (prm["walk_every_s"] if moving else 0.3)
                                if due:
                                    ap = approach_path(ok, pos, tcell, prm["short"])
                                    if ap is None:
                                        ev({"kind": "target_dropped", "track": target.tid,
                                            "why": "no_path"})  # fmt: skip
                                        banned.append((now, (int(round(tcell[0])),
                                                             int(round(tcell[1])))))  # fmt: skip
                                        target = None
                                    elif cont_click(ap, ok, "steer", tcell):
                                        stop_since = None
                                    elif not moving:
                                        stop_since = stop_since or now
                                        if now - stop_since > prm["stop_after_s"]:
                                            # none passed for 1 s: the GM stops; cursor-gated
                                            j, (u, v) = step_target(ap, 0, pos, prm["ahead"], ok)
                                            if j is not None:
                                                walk_click(u, v, ap[j], ap[: j + 1], "cursor",
                                                           "steer")  # fmt: skip
                                            stop_since = None
                                time.sleep(0.02)
                                continue
                            if not moving or now - last_walk >= prm["walk_every_s"]:
                                ap = approach_path(ok, pos, tcell, prm["short"])
                                if ap is None:
                                    ev({"kind": "target_dropped", "track": target.tid,
                                        "why": "no_path"})  # fmt: skip
                                    banned.append((now, (int(round(tcell[0])),
                                                         int(round(tcell[1])))))  # fmt: skip
                                    target = None
                                    continue
                                path, pi = ap, 0
                                j, (u, v) = step_target(path, 0, pos, prm["ahead"], ok,
                                                        need_clear=need_c)  # fmt: skip
                                if j is not None:
                                    gate_ = "map+units" if moving else "cursor"
                                    walk_click(u, v, path[j], path[: j + 1], gate_, "steer")
                                    pi = j
                            time.sleep(0.02)
                            continue
                        # no target: the planner's waypoint, the GM never standing
                        split.to("searching", time.monotonic())
                        if gp is None:
                            time.sleep(0.02)
                            continue
                        if cont:  # v5: the MOVEMENT QUEUE, ~6 ahead of where we are
                            set_mode("search")
                            due = now - last_walk >= (prm["walk_every_s"] if moving else 0.3)
                            grid_s = ok if plan.get("escape") else area  # v8 attempt 2
                            if due:
                                if cont_click(gp, grid_s, "search"):
                                    stop_since = None
                                elif not moving:
                                    stop_since = stop_since or now
                                    if now - stop_since > prm["stop_after_s"]:
                                        ci_ = min(range(len(gp)), key=lambda i_: cheb(gp[i_], pos))
                                        j, (u, v) = step_target(gp, ci_, pos, prm["ahead"],
                                                                grid_s)  # fmt: skip
                                        if j is not None and j > ci_:
                                            walk_click(u, v, gp[j], [pos, gp[j]], "cursor",
                                                       "search")  # fmt: skip
                                        else:
                                            with plock:
                                                plan["goal_path"] = None  # re-plan
                                        stop_since = None
                            time.sleep(0.02)
                            continue
                        if not moving or now - last_walk >= prm["walk_every_s"]:
                            cur = (reck.where(now + 0.15) or pos) if moving else pos
                            ci = gp.index(cur) if cur in gp else (gp_i if gp_i < len(gp) else 0)
                            if not moving and cur not in gp:
                                # the plan was made from another cell: walk to its nearest point
                                ci = min(range(len(gp)), key=lambda i_: cheb(gp[i_], cur))
                            j, (u, v) = step_target(gp, ci, cur, prm["ahead"],
                                                    need_clear=need_c)  # fmt: skip
                            if j is not None and j > ci:
                                seg = gp[ci : j + 1] if cur in gp else [cur, gp[j]]
                                gate_ = "map+units" if moving else "cursor"
                                if walk_click(u, v, gp[j], seg, gate_, "search"):
                                    gp_i = j
                            elif not moving:
                                with plock:
                                    plan["goal_path"] = None  # nothing clickable: re-plan
                        time.sleep(0.02)
                finally:
                    halt.set()
                    for th in ths:
                        th.join(timeout=3)

            while not prm.get("pipelined") and time.monotonic() < deadline:
                now = time.monotonic()
                if eng is None and now - last_check[0] > CHECK_EVERY_S:
                    check("searching")
                if eng is None and now - last_weight > WEIGHT_EVERY_S and not moving:
                    last_weight = now
                    fa, fb = gm_state._frames(screen)
                    wnow = gm_state._weight((fa, fb))
                    if gm_state.weight_action(wnow, at_restore=False) == "clear":
                        ev({"kind": "weight_clear", "weight": wnow})
                        gm_state.clear_loot(agent, screen, why="hunt-flow:mid-run",
                                            out_dir=log.dir / "gm_state")  # fmt: skip
                # where we are: reckoned while moving, corrected by the minimap
                if moving and reck.remaining(now) == 0:
                    moving = False
                    pos = reck.path[-1] if reck.path else pos
                    rp("snap", pos)
                est = reck.where(now) if moving else pos
                if est is not None:
                    pos = est
                if now - last_mm > MINIMAP_EVERY_S:
                    last_mm = now
                    mm = read_position()
                    if mm is not None and ok[mm[1], mm[0]]:
                        if cheb(mm, pos) <= DRIFT_CELLS:
                            mm_off = 0
                            last_fix[0] = time.monotonic()
                            if not moving:
                                pos = mm
                        else:
                            mm_off += 1
                            if mm_off >= 2:  # the reckoning drifted (or a walk-in moved us)
                                ev({"kind": "drift", "reck": list(pos), "minimap": list(mm)})
                                if (click_from is not None and click_cell is not None
                                        and cheb(mm, click_from) <= 1 and eng is None):  # fmt: skip
                                    # hunt@8's unstick: that cursor-gated click was not followed
                                    n_u = unfollowed.get(click_from, 0)
                                    unfollowed[click_from] = n_u + 1
                                    rad = 1 + min(2, n_u)
                                    cx, cy = click_cell
                                    blk = np.zeros_like(area)
                                    blk[max(0, cy - rad) : cy + rad + 1,
                                        max(0, cx - rad) : cx + rad + 1] = True  # fmt: skip
                                    fx, fy = click_from
                                    blk[max(0, fy - 1) : fy + 2, max(0, fx - 1) : fx + 2] = False
                                    area[blk] = False
                                    ev({"kind": "unfollowed_click", "from": list(click_from),
                                        "to": list(click_cell), "radius": rad})  # fmt: skip
                                    click_from = click_cell = None
                                split.to("stopping", time.monotonic())
                                pos = settle() or mm
                                moving, path, pi = False, [], 0
                                mm_off = 0
                                split.to("searching", time.monotonic())
                pos_box[0] = pos
                cov.mark(pos, now, offsets)
                # perception: every new detector frame into the tracks
                new = sampler.since(kf)
                kf += len(new)
                for t_fr, boxes in new:
                    age = (r.ns() - t_fr) / 1e9
                    here_fr = (reck.where(now - age) if moving else pos) or pos
                    tracks, next_id = update_tracks(tracks, t_fr, sightings_in(boxes, here_fr),
                                                    next_id, prm["track_near"],
                                                    prm["track_drop_s"])  # fmt: skip
                t_now = r.ns()
                # the engagement in progress: dead, a re-click, or a give-up
                if eng is not None:
                    tr = next((x for x in tracks if x.tid == eng["track"]), None)
                    since_first = (t_now - eng["t_first_click"]) / 1e9
                    since_last = (t_now - eng["t_last_click"]) / 1e9
                    unseen = (t_now - tr.t_last) / 1e9 if tr is not None else 99.0
                    # a death needs dead_min_s since the click: the client's walk-in scrolls the
                    # camera, and a walk click sent early would cancel the attack
                    if since_last >= prm["dead_min_s"] and unseen >= prm["dead_gone_s"]:
                        end_engagement("dead")
                        note("target gone: next")
                        pos = settle(timeout=1.5) or pos  # the walk-in moved us
                        moving, path, pi = False, [], 0
                        split.to("searching", time.monotonic())
                        continue
                    if since_first > prm["give_up_s"]:
                        banned.append((now, tuple(int(x) for x in eng["pred_cell"])))
                        end_engagement("gave_up")
                        pos = settle(timeout=1.5) or pos
                        moving, path, pi = False, [], 0
                        split.to("searching", time.monotonic())
                        continue
                    if since_last >= prm["reclick_s"] and tr is not None and not moving:
                        strike(tr, pos, again=True)
                    time.sleep(0.03)
                    continue
                # the queue: the nearest track
                if target is not None and target not in tracks:
                    target = None
                if target is None:
                    target = choose(tracks, pos, t_now, banned, now, prm["drop_target_s"])
                    reads = 0
                    if target is not None:
                        ev({"kind": "target", "track": target.tid,
                            "cell": [round(x, 1) for x in target.predict(t_now)]})  # fmt: skip
                if target is not None:
                    tcell = target.predict(t_now)
                    if strike_due(moving, pos, tcell, prm["strike_cells"]):
                        if not strike(target, pos, again=False) and reads >= prm["max_reads"]:
                            banned.append((now, (int(round(tcell[0])), int(round(tcell[1])))))
                            ev({"kind": "target_dropped", "track": target.tid,
                                "why": "no_sword", "reads": reads})  # fmt: skip
                            target = None
                        continue
                    if cheb(pos, tcell) <= prm["strike_cells"]:  # moving, about to arrive
                        time.sleep(0.03)
                        continue
                    if not moving or now - last_walk >= prm["walk_every_s"]:
                        split.to("steering", time.monotonic())
                        ap = approach_path(ok, pos, tcell, prm["short"])
                        if ap is not None:
                            path, pi = ap, 0
                            j, (u, v) = step_target(path, 0, pos, prm["ahead"], ok)
                            if j is not None:
                                if not moving:
                                    walk_click(u, v, path[j], path[: j + 1], "cursor", "steer")
                                elif units_clear(u, v):
                                    walk_click(u, v, path[j], path[: j + 1], "map+units",
                                               "steer")  # fmt: skip
                                pi = j
                        else:
                            ev({"kind": "target_dropped", "track": target.tid, "why": "no_path"})
                            banned.append((now, (int(round(tcell[0])), int(round(tcell[1])))))
                            target = None
                    time.sleep(0.03)
                    continue
                # no target: search, never standing
                split.to("searching", time.monotonic())
                if now - last_progress[0] > STUCK_S:
                    raise f0.FarmStop(f"no progress for {STUCK_S:.0f} s at {pos}: stopped")
                if not moving:
                    if pi >= len(path) - 1:
                        if not area[pos[1], pos[0]]:
                            back = hc.nearest_in(area, ok, pos)
                            got_path = None if back is None else hc.astar(ok, pos, back)
                            if got_path is None or len(got_path) < 2:
                                raise f0.FarmStop(f"outside the search area at {pos}, no way back")
                            path, pi = got_path, 0
                        else:
                            goal = hc.choose_goal(cov, pos, now, {}, bad_tiles)
                            got_path = None if goal is None else hc.astar(area, pos, goal)
                            if got_path is None or len(got_path) < 2:
                                if goal is not None:
                                    bad_tiles.append((goal[0] - goal[0] % hc.TILE,
                                                      goal[1] - goal[1] % hc.TILE))  # fmt: skip
                                if goal is None or len(bad_tiles) > 40:
                                    bad_tiles = []
                                pos = settle(timeout=2.0) or pos
                                continue
                            path, pi = got_path, 0
                            rp("route", pos, hc.waypoints(path))
                            ev({"kind": "route", "from": list(pos), "goal": list(goal),
                                "cells": len(path)})  # fmt: skip
                    j, (u, v) = step_target(path, pi, pos, prm["ahead"])
                    if j is None:
                        path, pi = [], 0
                        continue
                    if walk_click(u, v, path[j], path[pi : j + 1], "cursor", "search"):
                        refused = 0
                        pi = j
                    else:
                        refused += 1
                        if refused >= 3:
                            bad_tiles.append((path[-1][0] - path[-1][0] % hc.TILE,
                                              path[-1][1] - path[-1][1] % hc.TILE))  # fmt: skip
                            path, pi, refused = [], 0, 0
                elif now - last_walk >= prm["walk_every_s"] and pi < len(path) - 1:
                    cur = reck.where(now + 0.15) or pos
                    ci = path.index(cur) if cur in path else pi
                    j, (u, v) = step_target(path, ci, cur, prm["ahead"])
                    if j is not None and j > ci and units_clear(u, v):
                        walk_click(u, v, path[j], path[ci : j + 1], "map+units", "search")
                        pi = j
                time.sleep(0.03)
            if prm.get("pipelined"):
                pipelined_loop()
            if eng is not None:
                end_engagement("time_box")
            split.to(None, time.monotonic())
            run_s = time.monotonic() - t_run0
        except BaseException as exc:
            split.to(None, time.monotonic())
            ended = f"stopped:{type(exc).__name__}: {str(exc)[:200]}"
            run_s = time.monotonic() - t_run0
            if not isinstance(exc, (r.Stop, KeyboardInterrupt)):
                crashed = exc
        finally:
            stop_rec.set()
            if rec.is_alive():
                rec.join(timeout=5)
            if sampler is not None:
                sampler.stop()
                with (log.dir / "boxes.jsonl").open("w") as fh:  # the judge's first-seen
                    for t_b, bs in sampler.frames:
                        fh.write(json.dumps({"t": int(t_b), "boxes": [
                            [round(b.x0, 1), round(b.y0, 1), round(b.x1, 1), round(b.y1, 1),
                             round(b.score, 3), b.cls] for b in bs]}) + "\n")  # fmt: skip
            with contextlib.suppress(Exception):
                det.close()
            route_plan.disable(plan_tok)
            operator_hud.disable(hud_tok)
        after: dict[str, Any] = {"skipped": ended}
        if ended == "time_box":
            with contextlib.suppress(r.Stop):
                after = f0._brief(gm_state.ensure_fixed(agent, screen,
                                                        why=f"hunt-flow@{version}:after",
                                                        out_dir=log.dir / "gm_state",
                                                        profile="hunt-flow"))  # fmt: skip
                bench.close_chat(agent, screen)
        ev({"kind": "gm_state_after", **after})
    events_f.close()
    clicks_f.close()
    events, anchor = record_session.write_packets(log.dir, t_first, r.ns())
    (log.dir / "engagements.json").write_text(json.dumps(engagements, default=str))
    summary = {"run_s": round(run_s, 1), "engagements": len(engagements),
               "results": dict(Counter(e["result"] for e in engagements)),
               "split": split.ranked(), "coverage_cells": cov.first_seen,
               "det_fps": None if sampler is None or not run_s
               else round(len(sampler.frames) / run_s, 2)}  # fmt: skip
    log.finish(ended=ended, packet_events=len(events), packet_anchor=anchor, **summary)
    print(json.dumps({"session": sid, "ended": ended, **summary}, default=str), flush=True)
    if crashed is not None:
        raise crashed
    return 0 if ended == "time_box" else 3


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    rn = sub.add_parser("run")
    rn.add_argument("--version", type=int, required=True)
    rn.add_argument("--minutes", type=float, default=30.0)
    rn.add_argument("--seed", type=int, default=20261201)
    a = ap.parse_args()
    return run(a.version, a.minutes, a.seed)


if __name__ == "__main__":
    sys.exit(main())
