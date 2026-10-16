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
GM_SPRITE_BOX = (620.0, 285.0, 660.0, 375.0)  # v11: the GM's drawn sprite (x0, y0, x1, y1)
GUARD_EXCLUDE = (605.0, 270.0, 675.0, 390.0)  # v16's walk guard: the GM sprite + hair
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
    11: "OPPORTUNISTIC STRIKE (Batt 19:0x: Porings around the GM while it walked to a far one): "
    "any tracked target within 4 cells PRE-EMPTS the plan at once (nearest first); the hunting "
    "risk rule: overlap is risky only with a NON-target box, the GM check is occlusion only (its "
    "sprite hides >= 50 % of the box); the stand wait only on the read path; the walk-click "
    "clearance (12 px) only around non-target boxes (the Creamy hits)",
    12: "BURST STRIKE (Batt 19:4x / 20:0x: he clicks until the client draws the ARROW on the "
    "monster): after a direct attack click, the client's arrow is watched on raw frames; with "
    "none after 0.6 s (Batt's re-click interval) the next click goes to the FRESHEST box's body "
    "centre with a jitter scaled to that sprite (tighter on a Lunatic); stop on the arrow, at 4 "
    "clicks or 3 s, when the box is gone, or when the risk gate turns; logged per burst",
    13: "PRE-EMPTION HYSTERESIS (Batt 20:5x; v11: 1,085 pre-emptions in 242 engagements, landing "
    "within 5 s 44 %): a nearer target replaces the current one only if it is >= 2 cells closer "
    "(or the current one left the 4-cell zone) AND stays so for >= 0.5 s; never during a burst",
    14: "NAME-TAG CHECK (Batt 19:5x; the size gate let a Creamy -- pink, 39 x 36 px like a Poring "
    "-- pass as a target, v11 +527 s): before a direct attack click the pointer rests on the "
    "target until the client's own name tag under it reads (<= 1.2 s); only Poring / Lunatic / "
    "Pupa / Drops are clicked; another name bans the target; no tag = no click",
    15: "LATENCY BUDGET on the miss path (Batt B1; v13: 4 of 262 engagements ever re-clicked, the "
    "bot's 'dead' p50 0.38 s BEFORE the server's kill, bursts ended 'gone' 57 %): re-click 2.0 -> "
    "1.0 s; a burst whose box vanished keeps clicking the track's last box (<= 1.2 s old, "
    "tag-confirmed only); 'dead' needs >= 1.4 s after the last click and 0.8 s unseen",
    16: "FOCUS TRACKING (Batt B2 / B4): the chosen target's sprite crop, cut from the very frame "
    "of its detector box, is tracked by NCC on every frame-bus frame (~10-20 Hz); the attack "
    "click and every burst re-click aim at its fresh centre (<= 0.35 s old) led by its velocity "
    "x (age + 0.15 s), instead of the detector box (p50 0.57 s old)",
    17: "LOOT EVERYTHING (Batt 20:3x): after each kill, sweep the drop area (the death cell, the "
    "server's drop pattern SE / W / N, then the 3 x 3) with one park per sweep and one cursor read "
    "per cell; on the HAND (PICKUP read twice) and a clear unit check, click, confirm by the "
    "weight or the chat cue, and sweep again until a sweep shows no hand (<= 6 s, <= 8 clicks); a "
    "monster in the area skips the loot (the risk rule)",
    18: "MOVEMENT (Batt 21:31 + 18:2x): a remembered SEARCH HEADING -- keep it while its ray runs "
    ">= 8 cells (a <= 20 deg drift on 30 % of re-plans), turn +-45 deg first, then +-90, then "
    "+-135, reverse only at a real dead end, and RESUME it after every engagement; the minimap "
    "arrow is logged beside it. Plus the ENGAGEMENT ZONE: one path into the attack range, "
    "re-planned only when the target leaves the zone",
    19: "RE-TARGET WHILE STEERING (Batt's change 2: detection -> dispatch, v7 p50 2.85 s, was the "
    "bot steering to ANOTHER target that then failed, 19 / 32): after >= 1 s on a target, the "
    "planner's queue[0] replaces it when it is valid and cheaper by >= 2 cells (Chebyshev to the "
    "predicted cell, +2 for a walking one)",
    20: "TAG FOLLOW (the top loser after v14: 59 of 138 tag reads timed out, and only 7 / 66 of "
    "the refused reads show a matchable tag anywhere in the recorded frames -- the pointer was OFF "
    "the sprite, so the client drew no tag): during the read the pointer follows the focused "
    "target's fresh centre when it is > 10 px away, the tag is searched under the box AND under "
    "the pointer, and the click goes where the tag was read",
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
              # attempt 2 (2026-10-16 18:15, 0a515f7, before its run): the gate's box may be
              # <= 1.0 s old (attempt 1: 15 / 15 calls "stale_box" at 0.4 s; the CPU detector's
              # boxes arrive 0.3-0.65 s after their frame; v9's stand gate holds it still 1.2 s)
              "gate_fresh_s": 1.0}  # fmt: skip
# v11 = Batt's ENGAGEMENT ZONE (18:2x); the re-target build waits (it re-aims, the zone commits)
PARAMS[11] = {**PARAMS[10], "opportunistic": True, "opp_cells": 4, "risk_targets_ok": True,
              "still_read_only": True, "box_clear_px": 12.0,
              "box_clear_nontarget_only": True}  # fmt: skip
PARAMS[12] = {**PARAMS[11], "burst": True, "burst_interval_s": 0.6, "burst_max_clicks": 4,
              "burst_max_s": 3.0}  # fmt: skip
PARAMS[13] = {**PARAMS[12], "preempt_hyst": True, "preempt_margin": 2.0, "preempt_hold_s": 0.5}
PARAMS[14] = {**PARAMS[13], "name_tag": True, "tag_wait_s": 1.2, "tag_harvest": True,
              "walk_clear_unconfirmed": True}  # fmt: skip
PARAMS[15] = {**PARAMS[14], "reclick_s": 1.0, "dead_min_s": 1.4, "dead_gone_s": 0.8,
              "burst_hold": True, "burst_hold_s": 1.2, "tag_cache_s": 10.0,
              "burst_same_track": True, "unstall_s": 8.0}  # fmt: skip
# 16 also carries the WALK GUARD, a safety layer (not a play change) for every later version: v14's
# six Creamy hits were walk clicks on a sprite the detector cannot see (3.56)
PARAMS[16] = {**PARAMS[15], "focus": True, "focus_lead_s": 0.15, "focus_max_age_s": 0.35,
              "walk_guard": True, "guard_gm_px": 120.0, "guard_pink_r": 80,
              "guard_pink_max": 0.001}  # fmt: skip
PARAMS[17] = {**PARAMS[16], "loot": True, "loot_sweep": True, "loot_max_s": 6.0,
              "loot_max_clicks": 8}  # fmt: skip
# 18 = movement (Batt's heading method + the zone)
PARAMS[18] = {**PARAMS[17], "zone": True, "zone_radius": 7, "zone_radius_walking": 4,
              "heading_search": True, "heading_min_run": 8, "heading_drift_p": 0.3}  # fmt: skip
PARAMS[19] = {**PARAMS[18], "retarget": True, "retarget_margin": 2.0, "retarget_commit_s": 1.0}
PARAMS[20] = {**PARAMS[19], "tag_follow": True, "tag_follow_px": 10.0}


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
               ban_s: float = 15.0, moving_penalty: float = 2.0,
               heading: Sequence[float] | None = None,
               rev_penalty: float = 0.0) -> list[Track]:  # fmt: skip
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
    first = True
    while left and len(out) < depth:
        i = min(
            range(len(left)),
            key=lambda j: (
                cheb(at, left[j][1])
                + left[j][2]
                + (reversal_penalty(at, left[j][1], heading, rev_penalty) if first else 0.0)
            ),
        )
        first = False
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


def unstall_cells(grid: Any, here: Cell, rng: Any, min_steps: int = 6, max_steps: int = 14,
                  k: int = 4) -> list[Cell]:  # fmt: skip
    """PURE (the stall breaker, v15 attempt 2: the GM stood 53 s in a cliff pocket at the map's
    west edge, every walk candidate refused): up to ``k`` cells reachable on ``grid`` from
    ``here`` in ``min_steps``..``max_steps`` 8-connected steps, drawn at random (``rng``), the
    deepest band first -- somewhere clearly away from the pocket."""
    h, w = grid.shape
    depth: dict[Cell, int] = {here: 0}
    level = [here]
    for d in range(1, max_steps + 1):
        nxt: list[Cell] = []
        for x, y in level:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    c = (x + dx, y + dy)
                    if (0 <= c[0] < w and 0 <= c[1] < h and grid[c[1], c[0]]
                            and c not in depth):  # fmt: skip
                        depth[c] = d
                        nxt.append(c)
        level = nxt
    band = [c for c, d in depth.items() if d >= min_steps]
    rng.shuffle(band)
    band.sort(key=lambda c: -depth[c] // 4)  # stable: the deepest quarter-band first
    return band[:k]


def zone_path(grid: Any, here: Cell, center: Sequence[float], radius: int, reach: int = 45
              ) -> list[Cell] | None:  # fmt: skip
    """PURE (Batt 18:2x, the ENGAGEMENT ZONE): the shortest 8-connected path on ``grid`` from
    ``here`` to a cell within ``radius`` (Chebyshev) of ``center``; among the zone cells first
    reached at the same depth, the one nearest the centre (a straight approach, no diagonal
    detour). [here] when already inside; None when no zone cell is reachable within ``reach``."""
    cx, cy = float(center[0]), float(center[1])

    def inside(c: Cell) -> bool:
        return max(abs(c[0] - cx), abs(c[1] - cy)) <= radius

    if inside(here):
        return [here]
    h, w = grid.shape
    prev: dict[Cell, Cell | None] = {here: None}
    level = [here]
    while level:
        nxt: list[Cell] = []
        for c in level:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    n = (c[0] + dx, c[1] + dy)
                    if (n in prev or not (0 <= n[0] < w and 0 <= n[1] < h)
                            or not grid[n[1], n[0]]
                            or max(abs(n[0] - here[0]), abs(n[1] - here[1])) > reach):  # fmt: skip
                        continue
                    prev[n] = c
                    nxt.append(n)
        hits = [n for n in nxt if inside(n)]
        if hits:
            end = min(hits, key=lambda n: (math.hypot(n[0] - cx, n[1] - cy), n))
            out = [end]
            while prev[out[-1]] is not None:
                out.append(prev[out[-1]])  # type: ignore[arg-type]
            return out[::-1]
        level = nxt
    return None


def ray_run(area: Any, start: Cell, d: Cell, max_len: int) -> int:
    """PURE (v12): how many cells along direction ``d`` from ``start`` stay inside ``area``."""
    h, w = area.shape
    n = 0
    x, y = start
    while n < max_len:
        x, y = x + d[0], y + d[1]
        if not (0 <= x < w and 0 <= y < h) or not area[y, x]:
            break
        n += 1
    return n


def sweep_goal(area: Any, here: Cell, st: dict[str, Any], lane_w: int = 12, max_len: int = 40,
               min_run: int = 6) -> Cell | None:  # fmt: skip
    """PURE (v12, Batt 18:2x: "long sweeps, lawnmower-like lanes; keep the heading until a dead
    end, the area edge, or a target"): the next search goal, updating ``st`` (h = the lane heading,
    +-x; side = the shift direction, +-y; phase lane / shift). A lane runs to the area's edge or a
    dead end; then a shift of ``lane_w`` sideways (the same side until it can't, then the other);
    then the next lane back the other way. No shift and no lane -> None (the caller falls back)."""
    st.setdefault("h", (1, 0))
    st.setdefault("side", (0, 1))
    st.setdefault("phase", "lane")
    if st["phase"] == "lane":
        run = ray_run(area, here, st["h"], max_len)
        if run >= min_run:
            return (here[0] + st["h"][0] * run, here[1] + st["h"][1] * run)
        for side in (st["side"], (-st["side"][0], -st["side"][1])):
            sr = ray_run(area, here, side, lane_w)
            if sr >= max(2, lane_w // 2):
                st.update(side=side, phase="shift", h=(-st["h"][0], -st["h"][1]))
                return (here[0] + side[0] * sr, here[1] + side[1] * sr)
        st["h"] = (-st["h"][0], -st["h"][1])  # a dead end with no shift: the lane back
        run = ray_run(area, here, st["h"], max_len)
        return (here[0] + st["h"][0] * run, here[1] + st["h"][1] * run) if run >= min_run else None
    st["phase"] = "lane"  # the shift is done: the next lane
    return sweep_goal(area, here, st, lane_w, max_len, min_run)


def ray_run_angle(area: Any, start: Cell, ang: float, max_len: int) -> tuple[int, Cell]:
    """PURE (v18): how far a ray at angle ``ang`` (radians, x right / y down) runs inside
    ``area`` from ``start`` (in Chebyshev cells) and the last cell it reaches."""
    h, w = area.shape
    dx, dy = math.cos(ang), math.sin(ang)
    k = max(abs(dx), abs(dy))
    dx, dy = dx / k, dy / k  # one Chebyshev cell per step
    last = start
    n = 0
    for i in range(1, max_len + 1):
        c = (int(round(start[0] + dx * i)), int(round(start[1] + dy * i)))
        if not (0 <= c[0] < w and 0 <= c[1] < h) or not area[c[1], c[0]]:
            break
        last, n = c, i
    return n, last


def heading_goal(area: Any, here: Cell, st: dict[str, Any], rng: Any, max_len: int = 40,
                 min_run: int = 8, drift_deg: float = 20.0, drift_p: float = 0.3
                 ) -> Cell | None:  # fmt: skip
    """PURE (v18, Batt 21:31): the next search goal along the remembered SEARCH HEADING
    (st["ang"]): keep it while its ray runs >= ``min_run`` cells (sometimes drifting <= +-20 deg);
    when blocked, turn +-45 deg first, then +-90, then +-135 -- the side with the longer run --
    and reverse only at a real dead end. Updates st["ang"] and st["turn"] (the turn taken)."""
    ang = float(st.setdefault("ang", 0.0))
    if rng is not None and rng.random() < drift_p:
        a2 = ang + math.radians(rng.uniform(-drift_deg, drift_deg))
        n2, c2 = ray_run_angle(area, here, a2, max_len)
        if n2 >= min_run:
            st.update(ang=a2, turn=round(math.degrees(a2 - ang), 1))
            return c2
    n, c = ray_run_angle(area, here, ang, max_len)
    if n >= min_run:
        st["turn"] = 0.0
        return c
    for deg in (45, 90, 135):
        best = None
        for sgn in (1, -1):
            a2 = ang + sgn * math.radians(deg)
            n2, c2 = ray_run_angle(area, here, a2, max_len)
            if n2 >= min_run and (best is None or n2 > best[0]):
                best = (n2, c2, a2, sgn * deg)
        if best is not None:
            st.update(ang=best[2], turn=float(best[3]))
            return best[1]
    a2 = ang + math.pi  # a real dead end: the only reversal
    n2, c2 = ray_run_angle(area, here, a2, max_len)
    st.update(ang=a2, turn=180.0)
    return c2 if n2 >= 2 else None


def start_heading(area: Any, here: Cell, max_len: int = 40) -> float:
    """PURE (v18): the first search heading -- the longest of the 8 compass rays from ``here``."""
    angs = [k * math.pi / 4 for k in range(8)]
    return max(angs, key=lambda a: ray_run_angle(area, here, a, max_len)[0])


def minimap_heading(img: Any) -> float | None:
    """PURE (v18, Batt: "the heading from the game"): the player ARROW on the minimap picture (the
    only white pixels on it, 4-60 of them: an arrowhead with two prongs and a notch at the back)
    -> its mirror-symmetry axis through the centroid (36 axes, the most pixels mapped onto the
    set), pointing to the NARROW end (the tip; the back is the prongs' spread). The angle in
    radians (x right / y down), or None. On v14's frames it agrees within 45 deg with the arrow's
    own motion over 2.4 s in 69 % of straight stretches (that ground truth is coarse: ~0.3 px a
    cell)."""
    a = np.asarray(img)[..., :3].astype(np.int16)
    ys, xs = np.nonzero(a.min(-1) >= 215)
    if not 4 <= len(xs) <= 60:
        return None
    cx, cy = float(xs.mean()), float(ys.mean())
    dx, dy = xs - cx, ys - cy
    have = set(zip(xs.tolist(), ys.tolist(), strict=True))
    best = (-1, 0.0)
    for k in range(36):
        t = k * math.pi / 36
        c, s_ = math.cos(t), math.sin(t)
        p, q = dx * c + dy * s_, -dx * s_ + dy * c
        rx = np.rint(cx + p * c + q * s_).astype(int)  # the mirror image: q -> -q
        ry = np.rint(cy + p * s_ - q * c).astype(int)
        sc = sum((u, v) in have for u, v in zip(rx.tolist(), ry.tolist(), strict=True))
        if sc > best[0]:
            best = (sc, t)
    t = best[1]
    p = dx * math.cos(t) + dy * math.sin(t)
    q = -dx * math.sin(t) + dy * math.cos(t)
    hi, lo = p >= np.percentile(p, 80), p <= np.percentile(p, 20)
    return t if float(np.ptp(q[hi])) < float(np.ptp(q[lo])) else t + math.pi


def reversal_penalty(here: Sequence[float], target: Sequence[float],
                     heading: Sequence[float] | None, penalty: float,
                     angle_deg: float = 120.0) -> float:  # fmt: skip
    """PURE (v12): ``penalty`` cells when going to ``target`` turns the GM by more than
    ``angle_deg`` from its current ``heading`` (a unit-ish vector; None = no heading yet)."""
    if heading is None or (heading[0] == 0 and heading[1] == 0):
        return 0.0
    dx, dy = target[0] - here[0], target[1] - here[1]
    if dx == 0 and dy == 0:
        return 0.0
    cosv = (dx * heading[0] + dy * heading[1]) / (math.hypot(dx, dy) * math.hypot(*heading))
    return penalty if cosv < math.cos(math.radians(angle_deg)) else 0.0


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


def gate_reasons_hunt(
    b: Any,
    nontargets: Sequence[Any],
    gm_box: Sequence[float],
    min_conf: float,
    npc_near: bool,
    ignore_near: bool,
    hide_frac: float = 0.5,
) -> list[str]:
    """PURE (v11, Batt 19:0x, the HUNTING risk rule): overlap is risky only with a NON-target box
    (a Creamy-sized one); a cluster of targets is not (a misclick still hits a target). The GM
    check is OCCLUSION only: the GM's sprite box hides >= ``hide_frac`` of the target's box.
    Low confidence, an L3 NPC near, a non-target species near stay risky."""
    why: list[str] = []
    if any(not (o.x1 < b.x0 or o.x0 > b.x1 or o.y1 < b.y0 or o.y0 > b.y1) for o in nontargets):
        why.append("intersect_nontarget")
    ix = max(0.0, min(b.x1, gm_box[2]) - max(b.x0, gm_box[0]))
    iy = max(0.0, min(b.y1, gm_box[3]) - max(b.y0, gm_box[1]))
    area = max(1e-9, (b.x1 - b.x0) * (b.y1 - b.y0))
    if ix * iy / area >= hide_frac:
        why.append("gm_hides")
    if float(b.score) < min_conf:
        why.append("low_conf")
    if npc_near:
        why.append("npc_near")
    if ignore_near:
        why.append("ignore_species")
    return why


def nearest_close(tracks: Sequence[Track], here: Sequence[float], t_ns: int, cells: float,
                  fresh_s: float, exclude: Sequence[int] = (),
                  banned: Sequence[tuple[float, Cell]] = (), now_s: float = 0.0,
                  ban_s: float = 15.0) -> Track | None:  # fmt: skip
    """PURE (v11, the OPPORTUNISTIC strike): the nearest tracked target within ``cells``
    (Chebyshev, predicted) whose newest box is <= ``fresh_s`` old; None if there is none. It skips
    the cells a DROPPED target left within ``ban_s``, as ``choose`` does (v15 run 1: a target
    dropped after three refused tag reads was pre-empted again at once, 60 s, the stuck stop)."""
    best = None
    for tr in tracks:
        if tr.tid in exclude or (t_ns - tr.box_t) / 1e9 > fresh_s:
            continue
        p = tr.predict(t_ns)
        if any(now_s - tb < ban_s and cheb(p, cb) <= 2 for tb, cb in banned):
            continue
        d = cheb(here, p)
        if d <= cells and (best is None or d < best[0]):
            best = (d, tr)
    return None if best is None else best[1]


def arrow_blobs(region: Any) -> list[tuple[float, float]]:
    """PURE (v12, the ARROW marker): small white down-pointing blobs (every channel >= 215; 6-45
    px; 5-15 x 2-9; the top row wider than the bottom) in ``region``: (x, y) centres. On v10's
    recordings, after a strike click: P(arrow | our attack registered) 0.71, P(arrow | not) 0.08,
    first seen p50 0.44 s after the click."""
    from collections import deque

    w = np.asarray(region)[..., :3].astype(np.int16).min(-1) >= 215
    h_, w_ = w.shape
    lab = np.zeros(w.shape, np.int32)
    out: list[tuple[float, float]] = []
    n = 0
    for y0, x0 in zip(*np.nonzero(w), strict=True):
        if lab[y0, x0]:
            continue
        n += 1
        q = deque([(int(y0), int(x0))])
        lab[y0, x0] = n
        pts: list[tuple[int, int]] = []
        while q:
            y, x = q.popleft()
            pts.append((y, x))
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                yy, xx = y + dy, x + dx
                if 0 <= yy < h_ and 0 <= xx < w_ and w[yy, xx] and not lab[yy, xx]:
                    lab[yy, xx] = n
                    q.append((yy, xx))
        ys = [p[0] for p in pts]
        xs = [p[1] for p in pts]
        bw, bh = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
        if 6 <= len(pts) <= 45 and 5 <= bw <= 15 and 2 <= bh <= 9 and bw >= bh:
            top = sum(1 for y in ys if y == min(ys))
            bot = sum(1 for y in ys if y == max(ys))
            if top > bot:
                out.append((min(xs) + bw / 2, min(ys) + bh / 2))
    return out


def arrow_new(ref: Any, cur: Any, near_px: float = 4.0) -> bool:
    """PURE (v12): an arrow blob in ``cur`` that was not in ``ref`` (the same region before the
    first click): a scenery blob that was already there never counts."""
    old = arrow_blobs(ref)
    return any(all(math.hypot(x - a, y - b) > near_px for a, b in old)
               for x, y in arrow_blobs(cur))  # fmt: skip


BURST_JITTER = ((0.0, 0.0), (0.0, 0.18), (-0.18, 0.0), (0.18, 0.0), (0.0, -0.15))


def burst_aim(box: Any, k: int) -> tuple[float, float]:
    """PURE (v12): the k-th burst click on ``box`` (x0, y0, x1, y1): its centre (the drawn body)
    plus a jitter of a fraction of ITS size, so a small Lunatic gets a tighter pattern."""
    jx, jy = BURST_JITTER[k % len(BURST_JITTER)]
    w, h = box.x1 - box.x0, box.y1 - box.y0
    return (box.x0 + box.x1) / 2 + jx * w, (box.y0 + box.y1) / 2 + jy * h


def preempt_better(d_new: float, d_cur: float | None, zone_cells: float, margin: float) -> bool:
    """PURE (v13, Batt 20:5x): a pre-emption candidate is CLEARLY better -- there is no current
    target, the current one left the zone (> ``zone_cells``), or the new one is >= ``margin``
    cells closer."""
    return d_cur is None or d_cur > zone_cells or d_new + margin <= d_cur


def ncc_search(window: Any, tpl: Any) -> tuple[int, int, float]:
    """PURE (v16, FOCUS TRACKING): the template's best match in ``window`` (both grey, 2-D) by
    normalised cross-correlation -- the FFT for the correlation, integral images for the local
    means / norms (Lewis' fast NCC). Returns (x, y) of the template's top-left, and the score
    (-1..1); (0, 0, -1.0) when the window is smaller than the template."""
    w = np.asarray(window, np.float64)
    t = np.asarray(tpl, np.float64)
    H, W = w.shape
    h, w_ = t.shape
    if h > H or w_ > W:
        return 0, 0, -1.0
    t0 = t - t.mean()
    tn = float(np.sqrt((t0 * t0).sum()))
    if tn < 1e-6:
        return 0, 0, -1.0
    sh = (H + h - 1, W + w_ - 1)
    num_full = np.fft.irfft2(np.fft.rfft2(w, sh) * np.conj(np.fft.rfft2(t0, sh)), sh)
    num = num_full[: H - h + 1, : W - w_ + 1]
    ii = np.pad(w, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    ii2 = np.pad(w * w, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    s1 = ii[h:, w_:] - ii[:-h, w_:] - ii[h:, :-w_] + ii[:-h, :-w_]
    s2 = ii2[h:, w_:] - ii2[:-h, w_:] - ii2[h:, :-w_] + ii2[:-h, :-w_]
    var = np.maximum(s2 - s1 * s1 / (h * w_), 1e-9)
    score = num / (np.sqrt(var) * tn)
    y, x = np.unravel_index(int(np.argmax(score)), score.shape)
    return int(x), int(y), float(score[y, x])


def grey(img: Any) -> Any:
    a = np.asarray(img)[..., :3].astype(np.float32)
    return 0.114 * a[..., 0] + 0.587 * a[..., 1] + 0.299 * a[..., 2]


class Focus:
    """v16 (Batt B2, FOCUS TRACKING like an FPS aimbot): once a target is chosen, its sprite crop
    (cut from the very frame its detector box came from) is tracked by NCC on EVERY frame-bus
    frame, so the aim is ~0.1 s old instead of the detector's ~0.57 s. Thread-safe."""

    def __init__(self, search_px: int = 70, min_score: float = 0.45) -> None:
        import threading

        self.lock = threading.Lock()
        self.search_px, self.min_score = search_px, min_score
        self.tid: int | None = None
        self.tpl: Any = None
        self.pos: tuple[float, float] | None = None  # the crop's CENTRE (client px)
        self.vel = (0.0, 0.0)  # px / s
        self.t = 0
        self.score = 0.0
        self.misses = 0

    def start(self, tid: int, box: Any, img_t: int, img: Any) -> None:
        g = grey(img)
        x0, y0 = max(0, int(box.x0)), max(0, int(box.y0))
        x1, y1 = min(g.shape[1], int(box.x1)), min(g.shape[0], int(box.y1))
        if x1 - x0 < 8 or y1 - y0 < 8:
            return
        with self.lock:
            self.tid, self.tpl = tid, g[y0:y1, x0:x1].copy()
            self.pos, self.vel, self.t, self.score, self.misses = (
                ((x0 + x1) / 2, (y0 + y1) / 2),
                (0.0, 0.0),
                int(img_t),
                1.0,
                0,
            )

    def stop(self) -> None:
        with self.lock:
            self.tid = None

    def update(self, t: int, img: Any) -> None:
        with self.lock:
            if self.tid is None or self.pos is None:
                return
            tpl, pos, vel, t0 = self.tpl, self.pos, self.vel, self.t
        dt = max(0.0, (t - t0) / 1e9)
        px, py = pos[0] + vel[0] * dt, pos[1] + vel[1] * dt
        h, w = tpl.shape
        X0 = int(max(0, px - w / 2 - self.search_px))
        Y0 = int(max(0, py - h / 2 - self.search_px))
        a = np.asarray(img)
        win = grey(a[Y0 : int(py + h / 2 + self.search_px), X0 : int(px + w / 2 + self.search_px)])
        x, y, sc = ncc_search(win, tpl)
        with self.lock:
            if self.tid is None:
                return
            if sc < self.min_score:
                self.misses += 1
                if self.misses >= 6:
                    self.tid = None  # lost: the detector's boxes take over
                return
            npos = (X0 + x + w / 2, Y0 + y + h / 2)
            if sc >= 0.6:  # follow the sprite's animation (a Poring bounces): blend the match in
                cur = win[y : y + h, x : x + w]
                if cur.shape == self.tpl.shape:
                    self.tpl = 0.8 * self.tpl + 0.2 * cur
            if dt > 0:
                nv = ((npos[0] - pos[0]) / dt, (npos[1] - pos[1]) / dt)
                self.vel = (0.5 * vel[0] + 0.5 * nv[0], 0.5 * vel[1] + 0.5 * nv[1])
            self.pos, self.t, self.score, self.misses = npos, int(t), sc, 0

    def aim(self, tid: int, now_ns: int, lead_s: float, max_age_s: float
            ) -> tuple[float, float, float] | None:  # fmt: skip
        """(u, v, age_s): the tracked centre led by the velocity over the frame's age + lead_s;
        None if this track is not focused or the fix is too old."""
        with self.lock:
            if self.tid != tid or self.pos is None:
                return None
            age = (now_ns - self.t) / 1e9
            if age > max_age_s:
                return None
            k = age + lead_s
            return self.pos[0] + self.vel[0] * k, self.pos[1] + self.vel[1] * k, age


def pink_share(crop: Any, origin: tuple[int, int], u: float, v: float, radius: int,
               exclude: tuple[float, float, float, float]) -> float:  # fmt: skip
    """PURE (the walk guard, from v16): the share of PINK pixels -- R over G by > 51, B not under
    G by > 10, not dark: a Poring's or a Creamy's colours, never the ground's yellow-brown or
    green -- within ``radius`` px of the click pixel (u, v), outside ``exclude`` (the GM's own
    sprite: its red hair). ``crop`` is the frame region whose top-left is ``origin`` (client px),
    BGR(A) as Screen.grab returns it."""
    a = np.asarray(crop)[..., :3].astype(np.int16)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[origin[1] : origin[1] + h, origin[0] : origin[0] + w]
    m = (xx - u) ** 2 + (yy - v) ** 2 <= radius * radius
    m &= ~((xx >= exclude[0]) & (xx <= exclude[2]) & (yy >= exclude[1]) & (yy <= exclude[3]))
    b_, g_, r_ = a[..., 0], a[..., 1], a[..., 2]
    pk = (r_ - g_ > 51) & (b_ - g_ >= -10) & (a.max(-1) > 89)
    n = int(m.sum())
    return float((pk & m).sum() / n) if n else 0.0


def walk_guard_why(u: float, v: float, share: float, gm_px: float, pink_max: float) -> str | None:
    """PURE (the walk guard, from v16): why a WALK click at (u, v) is refused, or None. The client
    turns a walk click into an attack when it lands on a sprite; on v10-v14's recordings the walk
    clicks it turned into attacks sat near the GM (5-8 % of clicks within 100 px, 0.5 % beyond 150)
    or near pink pixels, and "within 120 px or any pink within 80 px" covered 14 of 17 Creamy hits
    (the detector sees none of them) at 25 % of the normal clicks."""
    if math.hypot(u - GM_SPRITE_PX[0], v - GM_SPRITE_PX[1]) < gm_px:
        return "near_gm"
    if share > pink_max:
        return "pink"
    return None


def tag_boxes(b: Any, ptr: tuple[float, float], around_ptr: bool) -> list[Any]:
    """PURE (v20): the boxes whose bands may hold the name tag -- the detector box, and with
    ``around_ptr`` a sprite-sized box centred on the pointer: the client draws the tag only under
    the HOVERED sprite, so a tag in either band names what the pointer is on."""
    from types import SimpleNamespace

    out = [b]
    if around_ptr:
        out.append(SimpleNamespace(x0=ptr[0] - 20, y0=ptr[1] - 18, x1=ptr[0] + 20, y1=ptr[1] + 18))
    return out


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
    guard_n: Counter[str] = Counter()  # v16+: the walk guard's verdicts (in the summary)
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
                        if prm.get("loot_sweep"):
                            loot_sweep(eng_, here2, dead_.cell)
                        else:
                            loot1.loot(rig, here2, dead_, eng_)
                finally:
                    split.to(prev_, time.monotonic())

            def loot_sweep(eng_: dict[str, Any], here2: Cell, dcell: Cell) -> None:
                """v17 (Batt 20:3x, LOOT EVERYTHING): sweep the drop area -- the death cell, then
                the server's drop pattern (SE, W, N), then the rest of the 3 x 3 -- with ONE park
                per sweep and one cursor read per cell; on the HAND (PICKUP, read twice) and a
                clear unit check, click it, confirm (weight / chat cue), and sweep again; done
                when a whole sweep shows no hand, or at loot_max_s / loot_max_clicks."""
                from poring_dataset import deathcell as dcm_

                t_l0 = time.monotonic()
                out: dict[str, Any] = {"cell": list(dcell), "sweeps": 0, "clicks": 0, "picked": 0}
                w_l = w5.World(camera, gat, here2)
                fr_l = sampler.since(max(0, len(sampler.frames) - 1))
                risky_l = [x for x, c in (sightings_in(fr_l[-1][1], here2) if fr_l else [])
                           if cheb(c, dcell) <= 1.5]  # fmt: skip
                if risky_l:
                    out["skip"] = "monster_in_area"  # the risk rule: a click could attack it
                    eng_["loot"] = out
                    ev({"kind": "loot", **out})
                    return
                while (time.monotonic() - t_l0 < prm["loot_max_s"]
                       and out["clicks"] < prm["loot_max_clicks"]):  # fmt: skip
                    if not pr.park():
                        out["end"] = "stale_park"
                        break
                    out["sweeps"] += 1
                    found = False
                    for cell in dcm_.scan_order(dcell, 1):
                        if time.monotonic() - t_l0 >= prm["loot_max_s"]:
                            break
                        if not w_l.walkable[cell[1], cell[0]]:
                            continue
                        u_l, v_l = (float(c_) for c_ in w_l.project([cell])[0])
                        if loot1.in_ui(u_l, v_l) or not in_view(u_l, v_l):
                            continue
                        pr.hover(u_l, v_l)
                        if pr.read(u_l, v_l)["shape"] != "pickup":
                            continue
                        if pr.read(u_l, v_l)["shape"] != "pickup":
                            continue
                        ok_u, _env = w11.unit_check(pr, w_l, u_l, v_l)
                        if not ok_u:
                            continue
                        before_l = loot1.frame_bgr(rig)
                        before_w = loot1.weight_now(rig)
                        t_lc = r.ns()
                        agent.click(gx0 + round(u_l), gy0 + round(v_l))  # the LOOT click
                        out["clicks"] += 1
                        trial_l: dict[str, Any] = {}
                        loot1.check(rig, before_l, before_w, t_lc, trial_l)
                        if (trial_l.get("runtime") or {}).get("obtained"):
                            out["picked"] += 1
                        click_log({"t": t_lc, "u": round(u_l, 1), "v": round(v_l, 1),
                                   "kind": "loot", "cell": list(cell)})  # fmt: skip
                        found = True
                        break  # the GM walked: the background is stale -> park, sweep again
                    if not found:
                        out["end"] = "no_hand"
                        break
                out["s"] = round(time.monotonic() - t_l0, 2)
                eng_["loot"] = out
                ev({"kind": "loot", **out})

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
                nontargets = []
                if prm.get("risk_targets_ok"):  # v11: only non-target boxes make overlap risky
                    for o in others:
                        c_o, sc_o = cell_of(o, here)
                        if c_o is None or f1.native_size(o, sc_o) > f1.MAX_NATIVE_PX:
                            nontargets.append(o)
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
                if prm.get("risk_targets_ok"):
                    return gate_reasons_hunt(b0, nontargets, GM_SPRITE_BOX, prm["gate_min_conf"],
                                             npc_near, ignore_near)  # fmt: skip
                return gate_reasons(b0, others, GM_SPRITE_PX, prm["gate_near_gm_px"],
                                    prm["gate_min_conf"], npc_near, ignore_near)  # fmt: skip

            import nametag

            tag_templates = nametag.load_templates() if prm.get("name_tag") else {}
            confirmed: dict[int, tuple[str, float]] = {}  # v14: track -> (its tag, when)
            if prm.get("name_tag") and not tag_templates:
                raise f0.FarmStop("hunt-flow refused: no name-tag templates (nametag.py build)")

            def read_tag(u: float, v: float, b: Any, tid: int | None = None
                         ) -> tuple[str | None, int, tuple[float, float]]:  # fmt: skip
                """v12: rest the pointer on (u, v) and read the name tag under ``b`` until one
                matches (<= tag_wait_s); the pointer is left on the target for the click. v20
                (tag_follow): the pointer follows the focused target, the tag is also searched
                under the pointer, and the returned point is where the pointer ended."""
                t_a = time.monotonic()
                agent.move(gx0 + round(u) - 12, gy0 + round(v) - 12)  # two motions: drawn
                time.sleep(0.06)
                agent.move(gx0 + round(u), gy0 + round(v))
                ptr[0] = (u, v)
                name_: str | None = None
                follow_ = bool(prm.get("tag_follow") and tid is not None)
                while time.monotonic() - t_a < prm["tag_wait_s"]:
                    time.sleep(0.1)
                    if follow_ and tid is not None:
                        fa_ = focus.aim(tid, r.ns(), 0.0, prm["focus_max_age_s"])
                        if (fa_ is not None and not loot1.in_ui(fa_[0], fa_[1])
                                and math.hypot(fa_[0] - u, fa_[1] - v)
                                > prm["tag_follow_px"]):  # fmt: skip
                            u, v = fa_[0], fa_[1]
                            agent.move(gx0 + round(u), gy0 + round(v))
                            ptr[0] = (u, v)
                    img_ = screen.grab(gx0, gy0, gw, gh)[1]
                    for bb_ in tag_boxes(b, (u, v), follow_):
                        name_, _iou = nametag.match(nametag.letter_mask(nametag.band(img_, bb_)),
                                                    tag_templates)  # fmt: skip
                        if name_ is not None:
                            break
                    if name_ is not None:
                        break
                return name_, round((time.monotonic() - t_a) * 1000), (u, v)

            def above(img_: Any, u_: float, v_: float) -> Any:
                """v12: the region where the client draws the attack arrow above a target."""
                a_ = np.asarray(img_)
                return a_[max(0, int(v_) - 80) : max(0, int(v_) - 15),
                          max(0, int(u_) - 45) : max(0, int(u_) + 45), :3]  # fmt: skip

            harvest_n = [0]

            def harvest_tag(img_: Any, ua: float, va: float) -> None:
                """v14+: the raw tag band under the struck target (the client shows its name
                after the click), saved for nametag.py build (labelled by the packets later)."""
                fr_h = sampler.since(max(0, len(sampler.frames) - 1))
                near_h = [
                    x
                    for x in (fr_h[-1][1] if fr_h else [])
                    if x.cls == "monster"
                    and float(np.hypot(*(np.array(f1.centre(x)) - (ua, va)))) <= 60
                ]
                if not near_h:
                    return
                bh = min(near_h, key=lambda x: float(np.hypot(*(np.array(f1.centre(x))
                                                                 - (ua, va)))))  # fmt: skip
                d_h = r.ROOT / "data" / "nametags" / "cuts"
                d_h.mkdir(parents=True, exist_ok=True)
                harvest_n[0] += 1
                name_h = f"live-{sid}-{harvest_n[0]:04d}"
                np.save(d_h / f"{name_h}.npy", np.asarray(nametag.band(img_, bh)))
                with (d_h / f"cuts-live-{sid}.jsonl").open("a") as fh_:
                    fh_.write(
                        json.dumps(
                            {
                                "name": name_h,
                                "t": r.ns(),
                                "u": round(ua, 1),
                                "v": round(va, 1),
                                "box": [bh.x0, bh.y0, bh.x1, bh.y1],
                            }
                        )
                        + "\n"
                    )

            focus = Focus()

            def focus_loop() -> None:
                """v16: the focused target updated on every frame-bus frame (its own grab)."""
                scr_f = r.Screen()
                last_t = 0
                try:
                    while not halt.is_set():
                        if focus.tid is None:
                            time.sleep(0.03)
                            continue
                        t_f, img_f = scr_f.grab(gx0, gy0, gw, gh)
                        if int(t_f) != last_t:
                            last_t = int(t_f)
                            focus.update(int(t_f), img_f)
                        else:
                            time.sleep(0.01)
                finally:
                    scr_f.close()

            def run_burst(
                tr: Track, here: Cell, u: float, v: float, ref_img: Any
            ) -> dict[str, Any]:
                """v12 (Batt 19:4x): after the first attack click, click again on the FRESHEST box
                every burst_interval_s (a jitter within the sprite's own size) until the arrow
                appears above it; bounded; every click re-checks the risk gate."""
                t_c0 = time.monotonic()
                t_last = t_c0
                ua, va = u, v
                out: dict[str, Any] = {"clicks": 1, "arrow_s": None, "end": None}
                while True:
                    time.sleep(0.07)
                    img_b = screen.grab(gx0, gy0, gw, gh)[1]
                    if arrow_new(above(ref_img, ua, va), above(img_b, ua, va)):
                        out.update(arrow_s=round(time.monotonic() - t_c0, 2), end="arrow")
                        if prm.get("tag_harvest"):
                            harvest_tag(img_b, ua, va)
                        break
                    if (time.monotonic() - t_c0 > prm["burst_max_s"]
                            or out["clicks"] >= prm["burst_max_clicks"]):  # fmt: skip
                        out["end"] = "bound"
                        break
                    if time.monotonic() - t_last < prm["burst_interval_s"]:
                        continue
                    fr_b = sampler.since(max(0, len(sampler.frames) - 1))
                    # v15 (burst_same_track): the SAME track's box only, <= 35 px of its newest
                    # box -- a neighbour within 60 px of the aim may be an unconfirmed Creamy
                    same_ = bool(prm.get("burst_same_track") and tr.box is not None)
                    ref_c = f1.centre(tr.box) if same_ else (ua, va)
                    lim_ = 35.0 if same_ else 60.0
                    near_b = [
                        x
                        for x in (fr_b[-1][1] if fr_b else [])
                        if x.cls == "monster"
                        and float(np.hypot(*(np.array(f1.centre(x)) - ref_c))) <= lim_
                    ]
                    if not near_b and prm.get("burst_hold") and tr.box is not None and (
                            r.ns() - tr.box_t) / 1e9 <= prm["burst_hold_s"] and (
                            not prm.get("name_tag") or tr.tid in confirmed):  # fmt: skip
                        # v15: the box is gone from the freshest frame (the cursor over a small
                        # sprite hides it; v13: 57 % of bursts ended "gone"): keep clicking the
                        # track's last box -- a tag-confirmed target only
                        near_b = [tr.box]
                        out["held"] = out.get("held", 0) + 1
                    if not near_b:
                        out["end"] = "gone"
                        break
                    if prm.get("risk_gate") and gate_risks(tr, here):
                        out["end"] = "risky"  # no more direct clicks
                        break
                    b_b = min(near_b, key=lambda x: float(np.hypot(*(np.array(f1.centre(x))
                                                                      - (ua, va)))))  # fmt: skip
                    ua, va = burst_aim(b_b, out["clicks"])
                    if prm.get("focus"):
                        fa_b = focus.aim(tr.tid, r.ns(), prm["focus_lead_s"],
                                         prm["focus_max_age_s"])  # fmt: skip
                        if fa_b is not None:  # v16: the fresh tracked centre + the same jitter
                            ua += fa_b[0] - (b_b.x0 + b_b.x1) / 2
                            va += fa_b[1] - (b_b.y0 + b_b.y1) / 2
                            out["focus"] = out.get("focus", 0) + 1
                    if loot1.in_ui(ua, va):
                        out["end"] = "ui"
                        break
                    tb_ = r.ns()
                    agent.click(gx0 + round(ua), gy0 + round(va))
                    t_last = time.monotonic()
                    out["clicks"] += 1
                    click_log({"t": tb_, "u": round(ua, 1), "v": round(va, 1),
                               "kind": "strike_burst", "track": tr.tid,
                               "n": out["clicks"]})  # fmt: skip
                out["dur_s"] = round(time.monotonic() - t_c0, 2)
                ev({"kind": "burst", "track": tr.tid, **out})
                return out

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
                aim_src = "box"
                if prm.get("focus") and direct_:
                    fa_ = focus.aim(tr.tid, r.ns(), prm["focus_lead_s"], prm["focus_max_age_s"])
                    if fa_ is not None and not loot1.in_ui(fa_[0], fa_[1]):
                        # v16: the target tracked on every frame, led by its velocity
                        u, v, aim_src = fa_[0], fa_[1], f"focus:{round(fa_[2] * 1000)}"
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
                tag_ = None
                cached_ = confirmed.get(tr.tid)
                if (direct_ and prm.get("name_tag") and prm.get("tag_cache_s") and cached_
                        and time.monotonic() - cached_[1] <= prm["tag_cache_s"]):  # fmt: skip
                    tag_ = cached_[0]  # v15: this track's tag read a target <= 10 s ago
                elif direct_ and prm.get("name_tag"):
                    # v12: the client's own species label must read a TARGET before a direct click
                    # (the size gate let a Creamy, a non-target, pass as a Poring: v11 +527 s)
                    tag_, tag_ms, (u, v) = read_tag(u, v, b, tr.tid)
                    if tag_ in nametag.TARGET_NAMES:
                        confirmed[tr.tid] = (tag_, time.monotonic())
                    if tag_ not in nametag.TARGET_NAMES:
                        reads += 1 if tag_ is None else prm["max_reads"]
                        ev({"kind": "tag_refused", "track": tr.tid, "tag": tag_, "ms": tag_ms})
                        note(f"tag {tag_}: no click")
                        split.to(prev, time.monotonic())
                        return False
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
                burst_ = bool(prm.get("burst") and direct_)
                ref_img = screen.grab(gx0, gy0, gw, gh)[1] if burst_ else None  # v12: the arrow's
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
                if burst_:  # v12: BURST until the client draws the arrow (after the aim error:
                    # v12 run 1 measured the aim after the burst, an artifact)
                    hov["burst"] = run_burst(tr, here, u, v, ref_img)
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
                           "risk": gate_why, "tag": tag_, "aim_src": aim_src})  # fmt: skip
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
                    if prm.get("heading_search"):  # v18: RESUME the search heading from here
                        plan["goal_path"] = None
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
            sweep_st: dict[str, Any] = {}  # v12: the lawnmower's heading / side / phase
            import random as random_

            heading_st: dict[str, Any] = {"ang": start_heading(area, start)}  # v18
            arrow_last: list[float | None] = [None]  # v18: the minimap arrow (deg), logged only
            heading_rng = random_.Random(seed)
            trail: list[tuple[float, Cell]] = []  # v8 attempt 2: (mono s, cell) we stood on

            def planner() -> None:
                """The queue (chained, standing first) every plan_every_s, and the next exploration
                waypoint (the coverage plan's stalest tile) always held."""
                while not halt.is_set():
                    now_, t_ = time.monotonic(), r.ns()
                    here_ = posm.at(now_)
                    head_ = None
                    if prm.get("sweep"):  # v12: our heading over the last ~2 s (the trail)
                        with plock:
                            tr2_ = [c_ for t_c, c_ in trail if now_ - t_c <= 2.0]
                        if tr2_ and cheb(tr2_[0], here_) >= 2:
                            head_ = (here_[0] - tr2_[0][0], here_[1] - tr2_[0][1])
                    q = plan_queue(tracks_now(), here_, t_, prm["queue_depth"], list(banned),
                                   now_, prm["drop_target_s"], prm["moving_penalty"], head_,
                                   prm.get("rev_penalty", 0.0))  # fmt: skip
                    gp = plan["goal_path"]
                    left_ = 999
                    if gp and prm.get("replan_left"):  # v5: never walk off the route's end
                        ci_ = min(range(len(gp)), key=lambda i_: cheb(gp[i_], here_))
                        left_ = len(gp) - 1 - ci_
                    stale_ = (not prm.get("sweep")  # v12: no time-based re-pick (hysteresis)
                              and now_ - plan["t_goal"] > prm["waypoint_every_s"])  # fmt: skip
                    if (gp is None or stale_
                            or cheb(here_, gp[-1]) <= 2
                            or (left_ < prm.get("replan_left", -1)
                                and not (prm.get("sweep")
                                         and sweep_st.get("phase") == "shift"))):  # fmt: skip
                        p_ = None
                        goal = None
                        if prm.get("heading_search") and area[here_[1], here_[0]]:
                            # v18 (Batt 21:31): along the remembered SEARCH HEADING; small turns
                            goal = heading_goal(area, here_, heading_st, heading_rng,
                                                min_run=prm["heading_min_run"],
                                                drift_p=prm["heading_drift_p"])  # fmt: skip
                            if goal is not None:
                                p_ = hc.astar(area, here_, goal)
                                if p_ is not None and len(p_) >= 2:
                                    ev({"kind": "heading_goal", "goal": list(goal),
                                        "ang": round(math.degrees(heading_st["ang"]) % 360, 1),
                                        "turn": heading_st.get("turn"),
                                        "arrow": arrow_last[0]})  # fmt: skip
                                else:
                                    goal = None
                        elif prm.get("sweep") and area[here_[1], here_[0]]:
                            goal = sweep_goal(area, here_, sweep_st, prm["lane_w"])
                            if goal is not None:
                                p_ = hc.astar(area, here_, goal)
                                if p_ is not None and len(p_) >= 2:
                                    ev({"kind": "sweep_goal", "goal": list(goal),
                                        "phase": sweep_st.get("phase")})  # fmt: skip
                                else:
                                    goal = None
                        if goal is not None:
                            pass  # v12: the lane / shift path is p_
                        elif area[here_[1], here_[0]]:
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
                if prm.get("focus"):
                    ths += [_start_thread(focus_loop, "focus")]
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
                pre_cand: dict[str, Any] = {}  # v13: the pre-emption candidate and since when
                last_unstall = [time.monotonic()]  # the stall breaker's last firing (mono s)
                busy_t = [time.monotonic()]  # the last moment with a target or an engagement
                stuck_cell: list[Cell | None] = [None]  # attempt 4: the cell we have stood on ...
                stuck_t = [time.monotonic()]  # ... since (walk clicks the client refuses)
                unstall_rng = random_.Random(seed + 7)
                zone_st: dict[str, Any] = {}  # v11: the engagement zone (tid, center, radius, path)
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
                    if not fr_:
                        return True
                    boxes_ = [b for b in fr_[-1][1] if b.cls == "monster"]
                    if prm.get("walk_clear_unconfirmed"):
                        # v14: only a box whose track's tag READ a target is clickable around;
                        # an unconfirmed box may be a Creamy (v10: a walk click turned attack)
                        ok_ids = {id(t_.box) for t_ in tracks_now() if t_.tid in confirmed}
                        boxes_ = [b for b in boxes_ if id(b) not in ok_ids]
                    elif prm.get("box_clear_nontarget_only"):  # v11: targets are fine to click
                        boxes_ = [b for b in boxes_ if (lambda cs: cs[0] is None or f1.native_size(
                            b, cs[1]) > f1.MAX_NATIVE_PX)(cell_of(b, pos))]  # fmt: skip
                    return all(
                        not (b.x0 - px_ <= u <= b.x1 + px_ and b.y0 - px_ <= v <= b.y1 + px_)
                        for b in boxes_)  # fmt: skip

                def guard_ok(u: float, v: float) -> bool:
                    """v16+ (a safety layer): no walk click near the GM's sprite or near pink
                    pixels on a FRESH grab (the client picks what its display shows there)."""
                    if not prm.get("walk_guard"):
                        return True
                    rg_ = int(prm["guard_pink_r"])
                    x0_, y0_ = max(0, int(u) - rg_), max(0, int(v) - rg_)
                    x1_, y1_ = min(gw, int(u) + rg_ + 1), min(gh, int(v) + rg_ + 1)
                    share_ = 0.0
                    if x1_ > x0_ and y1_ > y0_:
                        crop_ = screen.grab(gx0 + x0_, gy0 + y0_, x1_ - x0_, y1_ - y0_)[1]
                        share_ = pink_share(crop_, (x0_, y0_), u, v, rg_, GUARD_EXCLUDE)
                    why_ = walk_guard_why(u, v, share_, prm["guard_gm_px"],
                                          prm["guard_pink_max"])  # fmt: skip
                    guard_n[why_ or "ok"] += 1
                    if sum(guard_n.values()) % 200 == 0:
                        ev({"kind": "walk_guard", **guard_n})
                    return why_ is None

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
                                and (not cont or walk_ok(c_)) and guard_ok(uu, vv)):  # fmt: skip
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
                        if target is not None or eng is not None:
                            busy_t[0] = now  # the stall breaker counts idle SEARCH time only
                        ch_t = mstate.get("changed_t")
                        if (prm.get("freeze_guard") and ch_t is not None
                                and now - ch_t > FREEZE_S and last_walk > ch_t + 0.5):  # fmt: skip
                            # v10 safety (v9 attempt 2, 17:59: the client stopped redrawing while
                            # it still took input; the bot clicked blind 60 s): no input on a
                            # stale picture. v15 attempt 4: a STILL scene (the GM on a ledge, its
                            # walk clicks refused, nothing in view) looked the same -> first a
                            # LIVENESS probe: the pointer moves (two motions, no click); a live
                            # client redraws its own cursor, which changes the picture
                            t_pr = time.monotonic()
                            pu_, pv_ = ptr[0]
                            qu_ = pu_ + (70.0 if pu_ < gw / 2 else -70.0)
                            agent.move(gx0 + round(qu_) - 12, gy0 + round(pv_) - 12)
                            time.sleep(0.06)
                            agent.move(gx0 + round(qu_), gy0 + round(pv_))
                            ptr[0] = (qu_, pv_)
                            alive_ = False
                            while time.monotonic() - t_pr < 1.5:
                                time.sleep(0.05)
                                if (mstate.get("changed_t") or 0.0) > t_pr:
                                    alive_ = True
                                    break
                            if not alive_:
                                raise f0.FarmStop(
                                    f"the picture froze ({now - ch_t:.1f} s identical "
                                    f"after a walk click, and a pointer probe drew nothing): "
                                    f"a frozen client display"
                                )
                            ev({"kind": "freeze_probe", "alive": True,
                                "still_s": round(now - ch_t, 1)})  # fmt: skip
                            stuck_t[0] = 0.0  # a still scene after walk clicks: break the stall
                            continue
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
                                if prm.get("heading_search"):  # v18: the arrow, logged only
                                    ah_ = minimap_heading(mm_crop())
                                    arrow_last[0] = (
                                        None if ah_ is None else round(math.degrees(ah_) % 360, 1)
                                    )
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
                            busy_t[0] = time.monotonic()  # the loot sweep was busy time too
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
                        if prm.get("opportunistic") and eng is None:
                            # v11: a target within strike range PRE-EMPTS the plan at once (Batt
                            # 19:0x: Porings around the GM while it walked to a far one)
                            nc_ = nearest_close(
                                live, pos, t_now, prm["opp_cells"], prm["gate_fresh_s"],
                                list(done_ids), list(banned), now, prm["drop_target_s"],
                            )  # fmt: skip
                            do_ = nc_ is not None and (target is None or nc_.tid != target.tid)
                            if do_ and prm.get("preempt_hyst") and nc_ is not None:
                                # v13: only a CLEARLY better one, and only once it has stayed
                                # better for preempt_hold_s (v11: 1,085 flips in 242 engagements)
                                d_n = cheb(pos, nc_.predict(t_now))
                                d_c = None if target is None else cheb(pos, target.predict(t_now))
                                if preempt_better(d_n, d_c, prm["opp_cells"],
                                                  prm["preempt_margin"]):  # fmt: skip
                                    if pre_cand.get("tid") != nc_.tid:
                                        pre_cand.update(tid=nc_.tid, since=now)
                                    do_ = (
                                        target is None
                                        or now - pre_cand["since"] >= prm["preempt_hold_s"]
                                    )
                                else:
                                    pre_cand.clear()
                                    do_ = False
                            if do_ and nc_ is not None:
                                ev({"kind": "preempt", "to": nc_.tid,
                                    "from": None if target is None else target.tid,
                                    "d": round(cheb(pos, nc_.predict(t_now)), 1)})  # fmt: skip
                                target, reads = nc_, 0
                                t_target[0] = now
                                pre_cand.clear()
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
                        if prm.get("focus"):
                            if target is None and eng is None:
                                focus.stop()
                            elif target is not None and focus.tid != target.tid:
                                li_ = sampler.last_img
                                same_fr = li_ is not None and int(li_[0]) == int(target.box_t)
                                if same_fr and li_ is not None and target.box is not None:
                                    focus.start(target.tid, target.box, li_[0], li_[1])
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
                            # v11: inside the ENGAGEMENT ZONE counts as in range (the zone keeps
                            # its centre while the target stays in it: no re-aim at small hops)
                            in_zone = bool(prm.get("zone") and zone_st.get("tid") == target.tid
                                           and cheb(pos, zone_st["center"]) <= zone_st["radius"]
                                           and cheb(tcell, zone_st["center"])
                                           <= zone_st["radius"])  # fmt: skip
                            in_rng = cheb(pos, tcell) <= s_range or in_zone
                            if in_rng:
                                in_range_since.setdefault(target.tid, time.monotonic())
                            if not moving and in_rng:
                                need_still = bool(prm.get("still_gate")) and (
                                    not prm.get("still_read_only")
                                    or bool(gate_risks(target, pos)))  # fmt: skip
                                if need_still and not box_still(
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
                            if in_rng:
                                time.sleep(0.02)  # walking, about to arrive: the strike is next
                                continue
                            if cont:  # v5: steer continuously, no standstill gate
                                set_mode("steer")
                                due = now - last_walk >= (prm["walk_every_s"] if moving else 0.3)
                                if due and prm.get("zone"):
                                    # v11: ONE path into the zone; re-planned only when the
                                    # target leaves it (or a new target)
                                    if (zone_st.get("tid") != target.tid
                                            or cheb(tcell, zone_st["center"])
                                            > zone_st["radius"]):  # fmt: skip
                                        rz_ = (prm["zone_radius_walking"] if strike_range(
                                            target, prm) < prm["zone_radius"]
                                            else prm["zone_radius"])  # fmt: skip
                                        same_ = zone_st.get("tid") == target.tid
                                        pz_ = zone_path(ok, pos, tcell, rz_)
                                        zone_st.clear()
                                        zone_st.update(tid=target.tid, center=tuple(tcell),
                                                       radius=rz_, path=pz_)  # fmt: skip
                                        ev({"kind": "zone_plan", "track": target.tid,
                                            "replan": same_, "radius": rz_,
                                            "len": None if pz_ is None else len(pz_)})  # fmt: skip
                                    ap = zone_st.get("path")
                                elif due:
                                    ap = approach_path(ok, pos, tcell, prm["short"])
                                if due and ap is not None and len(ap) <= 1:
                                    pass  # v11: inside the zone already: the strike comes next
                                elif due:
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
                        if pos != stuck_cell[0]:
                            stuck_cell[0], stuck_t[0] = pos, now
                        if (cont and prm.get("unstall_s") and not moving
                                and now - max(min(last_walk, stuck_t[0]), busy_t[0],
                                              last_unstall[0]) > prm["unstall_s"]):  # fmt: skip
                            # the STALL BREAKER (v15 attempt 2): no walk click for unstall_s while
                            # standing with NO target (attempt 3: engagements had counted, so it
                            # fired after every long strike) -> settle our cell, walk to a
                            # reachable cell 6-14 away
                            last_unstall[0] = now
                            pos = settle(timeout=1.5) or pos
                            for c_ in unstall_cells(ok, pos, unstall_rng):
                                p_ = hc.astar(ok, pos, c_)
                                if p_ is not None and len(p_) >= 2:
                                    with plock:
                                        plan.update(goal_path=p_, escape=True, t_goal=now)
                                    gp = p_
                                    ev({"kind": "unstall", "at": list(pos), "to": list(c_)})
                                    break
                            else:
                                ev({"kind": "unstall", "at": list(pos), "to": None})
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
               else round(len(sampler.frames) / run_s, 2), "walk_guard": dict(guard_n)}  # fmt: skip
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
