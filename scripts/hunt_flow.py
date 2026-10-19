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
MAP = "prt_fild08"  # `run --map` replaces it (the HELD-OUT map test, Batt 2026-10-17 21:5x)
# Per map: does the field hold species the detector was never trained on? (Batt 2026-10-18,
# decision 2 option a: the cursor's SWORD check at LOOT clicks only, and ONLY on such maps; 3.78:
# on prt_fild06 the untrained Thief Bugs were 21 of 29 non-target attacks, from loot clicks.) A map
# missing here refuses a run whose params ask for the check by map (fail closed: someone decides).
UNTRAINED_SPECIES = {"prt_fild08": False, "prt_fild06": True}
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
# v26: where the pointer RESTS after a walk click / a loot step -- over the Basic Information
# window's HP bar (route_preview.UI_WINDOWS[0]): no monster can come under it there. v24's 15 walk
# clicks that became attacks came 0.35-1.45 s after the click, with no box near the click point
# then (the Creamy hard bar: it flew under the resting pointer and the client attacked it)
REST_PX = (110.0, 66.0)
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
    20: "TAG FOLLOW, on v18 (not v19) (the top loser after v14: 59 of 138 tag reads timed out, "
    "and only 7 / 66 of "
    "the refused reads show a matchable tag anywhere in the recorded frames -- the pointer was OFF "
    "the sprite, so the client drew no tag): during the read the pointer follows the focused "
    "target's fresh centre when it is > 10 px away, the tag is searched under the box AND under "
    "the pointer, and the click goes where the tag was read",
    21: "LOOT BY FRAME DIFFERENCE, on v20 (Batt 2026-10-17, the competition's order item 1): "
    "after a kill, drop_blobs compares the death spot ~1.8 s before the 'dead' decision with now "
    "and +0.4 s; each new small blob becomes a floor cell (+ its sub-cell pixel residual), "
    "re-projected as the GM moves, hovered, and clicked on the HAND read twice + walk@11's unit "
    "check; the v17 sweep only when no blob was clicked; plus the walk guard leaving our own "
    "cursor out",
    22: "SEARCH GEOMETRY, on v21 (Batt's competition order item 2; the search-gap study: the bot "
    "swept 0.63x Batt's ground per 10 min -- overlap, turning back, short net legs): the heading "
    "search remembers the ground in our own view (+-12 cells, 3 min) and scores keep / +-45 / "
    "+-90 / +-135 by run x (0.25 + the fresh share at the ray's end), keeping the heading while it "
    "scores >= 0.8x the best",
    23: "BATT'S FIXED LOOT WORKFLOW, on v22 (Batt 2026-10-17 11:0x; it replaces the blob / icon "
    "analysis, whose item-sprite version stays built and unrun): after every kill, burst-click the "
    "death cell (2), then click through the 3 x 3 in the drop pattern's order (1 each), 0.3 s "
    "apart, each click re-projected from where the GM is; no item detection, no cursor read; "
    "skipped only near a monster / NPC box, an NPC, a Creamy's NEW pink (> 100 px within 40 px: "
    "an Apple holds 64), the UI or off the frame; plus the pixel species check logged in SHADOW "
    "beside each tag read",
    24: "THE FIXED LOOT'S DEATH CELL, on v23 (offline on v21 / v22 / v23: v23's death cell put the "
    "first loot click 50 px from the nearest drop, p50; the last strike click 10-16 px): the cell "
    "under the last strike click when it is within 1 cell of the GM, else the GM's neighbour in "
    "its direction; and the cadence v23 registered (0.05 s sleep: ~0.4 s a click, 0.66 s as built)",
    25: "THE NAME TAG ONLY WHEN AMBIGUOUS, on v24 (Batt's work order item 3): no tag read when the "
    "pixel species check is sure of a target and no other monster box is within 50 px (v23's "
    "shadow: sure on 37 %, 37 of 38 agreed, the one miss crowded), and then the strike already "
    "while walking in (in range, no risk) instead of waiting for the GM to stop",
    26: "RE-TARGET WHILE STEERING, on v25 (Batt's work order item 4; v19's change, built and never "
    "run): after >= 1 s on a target, the planner's queue[0] replaces it when it is valid and "
    "cheaper by >= 2 cells",
    27: "BATTLESHIP, on v26 (Batt 2026-10-17): the belief map of HIDDEN monsters (tracks on the "
    "walkable grid, a fitted random-walk kernel, negative evidence from the cells in view, a "
    "walk-on lead); a monster unseen 1-10 s that the map still believes in becomes the search "
    "goal, at its most probable cell",
    28: "THE POINTER REST THE CLIENT DRAWS, on v27: two motions to the HP bar after every walk "
    "click and loot step (one jump never moved the client's own cursor: v26 / v27's rest was "
    "inert, and v27's Creamy flew under the cursor left on the world); + each belief ghost is "
    "chased once",
    29: "BATT'S A / B / C STRIKE TEST, interleaved per engagement on v28: A = pointer on the "
    "target, the name tag (or its cache) confirms, then the click; B = click at once and burst "
    "until the lock arrow; C = B after a second small motion (1-2 px); B / C only for a confident "
    "target (species check or tag cache) with no pink other than the target within 60 px",
    30: "v29 WITH THE BELIEF MAP OFF (Batt 18:3x, decision 2): the A / B / C strike test "
    "continues, pooled with v29's runs",
    31: "THE DEATH CELL WHERE THE HIT LANDED, on v30 (Batt 18:3x): the fixed loot's 3 x 3 centres "
    "on the target's own last box (the hit / death animation), turned into a cell with our "
    "measured position at that frame (offline vs packets: 86-90 % of drops inside its 3 x 3; "
    "the last strike click 54 %); the A / B / C strike test keeps running",
    32: "FAST DEAD, interleaved per engagement, with arm C the default strike (Batt), on v31: once "
    "the burst ended on the client's attack arrow or the target vanished, 0.35 s unseen (one "
    "detector frame) and 0.5 s after the click is the death, and the loot starts with no 0.4 s "
    "wait (odd engagements; even ones keep v15's rule)",
    33: "LOOT IS A RACE (Batt, decision 3), on v32: the floor items the matcher sees (item_icons) "
    "are clicked FIRST at their own pixels, nearest first, then the fixed 3 x 3; a target that "
    "steps onto our pile is killed first (one a kill) and our cells looted with its own; "
    "interleaved per kill (odd loot steps: the race; even: v32's plain 3 x 3)",
    34: "PACED INPUT, on v33: ro_agent drained 50 ms before EVERY send (a click's three sends "
    "waited 150 ms of ~0.3 s); paced sends read the queued status without blocking and keep "
    "only the old minimum gap (50 ms) since the previous send; 10-min blocks alternate paced / "
    "default within each run",
    35: "THE SPECIES CHECK ON THE BOX'S OWN FRAME (the stale-box study), gated by re-centring the "
    "sprite in a fresh grab: arm C's 'species unsure' fallbacks came from a ~0.6 s old box "
    "cropped on a newer frame",
    36: "THE LOOT RETRY: a loot cell skipped for a unit near is queued once more at the end of "
    "the step (>= 0.6 s later, the same checks); interleaved per kill",
    37: "THE CURSOR'S SWORD at every loot click and every moving walk click: the pointer there in "
    "two motions, the client's own cursor read; SWORD or unknown = no click (cursor_sword); "
    "interleaved per engagement",
    38: "THE AGE-WEIGHTED SEARCH HEADING: each heading scored by the ground it brings into our own "
    "view, weighted by how long since we last saw it, per walking second (the search study); "
    "10-min blocks. Base: the cursor's SWORD at loot clicks on untrained-species maps only",
    39: "THE CONTINUOUS APPROACH: the steer's walk click may take the route's tail when nothing "
    "lies >= 3 cells ahead, and the route's end when even that is empty (Batt 16:2x: the steer "
    "always finds a point on the route; only the gates refuse), and the standstill fallback steps "
    "from the route point nearest the GM (the conversion study: the GM stood while closing in); "
    "interleaved per engagement (odd k)",
    40: "THE FALSE-DEAD FIX: after a RISKY last burst the dead call stands only when the "
    "death-cell fix says ok; otherwise the engagement ends skipped_risky (no loot step, the "
    "track stays selectable: the normal selection re-engages it), never dead; interleaved per "
    "engagement (odd k). Base: v38's (v39 not adopted, 3.80)",
    41: "WALKING TARGETS STRUCK FROM FURTHER: a walking target's strike range (and the steer's "
    "zone) from strike_cells_walking (7) on odd k, as a standing one's; the client walks up "
    "after the attack click. Base: v40 adopted (3.81), the false-dead fix on every engagement",
    43: "THE HUNTING UI LAYOUT (Batt's three spots): the hotkey bar on one row, the menu icon "
    "panel collapsed, the chat window's Battle Log tab shown; applied by the runner through the "
    "client's own controls, the UI masks follow it; with the dead-end ping-pong fix "
    "(dead_end_hyst_s). Base: v40's, the false-dead fix on every engagement (v41 not adopted)",
    42: "THE STEER'S WALK GUARD FROM THE GM'S BOX: on odd k the steer's walk clicks are refused "
    "only within the GM's drawn box + 20 px (not the 120-px circle) and its picker may take the "
    "route's tail; search and loot clicks keep the circle; interleaved per engagement. With the "
    "pocket escape (stuck by displacement: a 60-s spread <= 18 cells over >= 80 walked -> walk "
    "out >= 26 cells, the pocket blacklisted 5 min) as a bug fix in both arms. Base: v43 adopted",
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
# six Creamy hits were walk clicks on a sprite the detector cannot see (3.56); and from its
# attempt 3 the tag on EVERY attack click, the read path too, and the cache only near its point
PARAMS[16] = {**PARAMS[15], "focus": True, "focus_lead_s": 0.15, "focus_max_age_s": 0.35,
              "walk_guard": True, "guard_gm_px": 120.0, "guard_pink_r": 80,
              "guard_pink_max": 0.001, "tag_every_click": True, "tag_cache_s": 3.0,
              "tag_cache_px": 60.0}  # fmt: skip
PARAMS[17] = {**PARAMS[16], "loot": True, "loot_sweep": True, "loot_max_s": 6.0,
              "loot_max_clicks": 8, "guard_ui_mask": True}  # fmt: skip
# 18 = movement (Batt's heading method + the zone)
PARAMS[18] = {**PARAMS[17], "zone": True, "zone_radius": 7, "zone_radius_walking": 4,
              "heading_search": True, "heading_min_run": 8, "heading_drift_p": 0.3}  # fmt: skip
PARAMS[19] = {**PARAMS[18], "retarget": True, "retarget_margin": 2.0, "retarget_commit_s": 1.0}
# 20 builds on 18, NOT 19 (2026-10-17 02:3x): the night's last slot goes to the top loser (the tag
# reads: 40-58 % refused in v15-v16), one change against the last version run; v19 is built, unrun
PARAMS[20] = {**PARAMS[18], "tag_follow": True, "tag_follow_px": 10.0}
PARAMS[21] = {**PARAMS[20], "loot_blobs": True, "loot_before_s": 1.8, "guard_ptr_mask": True}
PARAMS[22] = {**PARAMS[21], "heading_cov": True, "cov_recent_s": 180.0, "cov_half": 12,
              "cov_keep": 0.8}  # fmt: skip
# 23 = Batt's FIXED loot workflow (2026-10-17 11:0x); the item-sprite loot (loot_icons, b1289b2)
# stays built and UNRUN: Batt replaced it before its run
PARAMS[23] = {**PARAMS[22], "loot_fixed": True, "loot_center_clicks": 2, "loot_ring_clicks": 1,
              "loot_interval_s": 0.3, "loot_fixed_max_s": 4.0,
              "loot_pink_r": 40, "loot_pink_max_px": 100, "species_shadow": True,
              "icon_radius": 110, "blob_gm_px": 70.0}  # fmt: skip
# 24 = v23's fixed loot at the RIGHT death cell (the last strike click's cell, else the GM's
# neighbour toward it) and at the cadence v23 registered (0.3 s was 0.66 s as built)
PARAMS[24] = {**PARAMS[23], "loot_death": "hybrid", "loot_interval_s": 0.05,
              "loot_fixed_max_s": 4.5}  # fmt: skip
# 25 = Batt's item 3, the NAME TAG: the tag only when the pixel species check is unsure or crowded,
# and the strike already while walking in when it is sure
# (+ two loot safety fixes from v24's run: the GM's sprite out of the pink count, and a monster box
# within 70 px skips a loot cell -- v24's 10 loot clicks that became attacks had the nearest box
# edge 19-81 px away, p50 42, on boxes 0.1-0.4 s old)
PARAMS[25] = {**PARAMS[24], "species_skip": True, "strike_moving": True,
              "loot_pink_gm_exclude": True, "loot_unit_px": 70.0}  # fmt: skip
# 26 = Batt's item 4: v19's RE-TARGET (built 2026-10-17 02:2x, never run), on v25
PARAMS[26] = {**PARAMS[25], "retarget": True, "retarget_margin": 2.0, "retarget_commit_s": 1.0,
              "ptr_rest_ui": True}  # fmt: skip
# 27 = Batt's "Battleship": the belief map's most probable cell of a HIDDEN monster as the search
# goal (belief_map, merged 8268666: ne + lead, the offline eval's best variant), on v26
PARAMS[27] = {**PARAMS[26], "belief": True, "belief_pd": 0.2, "belief_lead": 0.5,
              "belief_unseen": (1.0, 10.0), "belief_min_mass": 0.3,
              "steer_stuck_s": 10.0}  # fmt: skip
# 28 = FAST DEAD (the top loser after loot: server kill -> the bot's "dead" + loot start), staged;
# its base is decided by v26 / v27's results and pre-registered then
# 28 = the pointer rest the client ACTUALLY draws (two motions; v26 / v27's one jump never moved
# the client's cursor, and v27's walk-click Creamy hit came from it), + each belief ghost once
PARAMS[28] = {**PARAMS[27], "ptr_rest_two": True, "belief_probe_once": True}
# 29 = Batt's INTERLEAVED A / B / C strike test (2026-10-17 17:3x), on v28
PARAMS[29] = {**PARAMS[28], "abc": True}
# 30 = v29 with the Battleship belief map OFF (Batt 18:3x, decision 2: as a search goal it does
# not pay -- ~11 % of goals led to a kill; the code stays, inert). The A / B / C test continues in
# v30's runs, pooled with v29's (its arms are interleaved within each run)
PARAMS[30] = {**PARAMS[29], "belief": False}
# 31 = the fixed loot's death cell from the target's own LAST box (Batt 18:3x, decision 1), on v30
# (the A / B / C test keeps running inside it)
PARAMS[31] = {**PARAMS[30], "loot_death": "anim"}
# 32 = arm C the DEFAULT strike (Batt, after the A/B/C test; A the fallback) + FAST DEAD, the main
# change, interleaved per engagement (odd k: fast; even k: v15's rule), on v31
PARAMS[32] = {**PARAMS[31], "abc_arm": "C", "fast_dead": True, "fast_dead_ab": True,
              "fast_dead_min_s": 0.5, "fast_dead_gone_s": 0.35}  # fmt: skip
# 33 = LOOT IS A RACE (Batt, after the 21:33 report, decision 3), on v32: items first (the
# matcher's floor items at their own pixels, then the 3 x 3) + the LOOTER CHAIN (a confident target
# whose box stands within looter_cells of the death cell stops the loot, is engaged at once, and its
# own loot step covers the cells still to click; at most one a kill). Interleaved per loot step
# fast_dead_ab is OFF: the dead rule is ONE rule for the whole run, set by 3.72's verdict before
# v33's first run (fast for all if it passed, v15's for all if not) -- loot steps follow
# engagements, so two parity-interleaved arms would be confounded
# 3.72's verdict (23:2x): the fast arm's kill -> loot start p50 1.23 s missed its pre-registered
# <= 1.2 s (bootstrap 95 % 1.10-1.49) -> by 3.73's rule v15's dead rule for ALL (fast_dead off)
PARAMS[33] = {**PARAMS[32], "fast_dead": False, "fast_dead_ab": False,
              "loot_icons": True, "loot_race": True, "loot_race_ab": True,
              "looter_chain": True, "looter_cells": 2, "looter_pending_s": 12.0,
              "looter_match_px": 40.0,
              # a BASE fix in both arms (not the change under test): the loot step's position
              # from the minimap readout whenever the odometry is > 1.5 cells off it
              "loot_refix": True, "loot_refix_cells": 1.5}  # fmt: skip
# 34 = PACED INPUT (the agent link's dead 50 ms wait before every send), interleaved in 10-min
# blocks within each run (the input path is global, so not per engagement): odd seeds start
# paced. Its base (v33 as is, or with its loot arm decided) is set at its pre-registration
# + a BASE fix (amended before v34's first run): the loot's unit check ignores the target's own
# dying sprite for 2.5 s (the speed fix made loot start 0.63 s after the kill, under the corpse)
# 3.73's verdict (01:3x): the race failed both primary predictions -> the plain 3 x 3 for all
PARAMS[34] = {**PARAMS[33], "loot_race": False, "loot_icons": False, "looter_chain": False,
              "send_gap_s": 0.05, "send_gap_ab": True, "send_gap_ab_min": 10.0,
              "loot_corpse": True, "loot_corpse_s": 2.5, "loot_corpse_px": 30.0}  # fmt: skip
# 35 = the species check on the box's OWN frame, gated by finding the sprite again in a fresh grab
# (the species-crop study, species_check.py THE STALE BOX: coverage 0.34 -> 0.65 at a 0.6 s old
# box, wrong species 11 -> 0, Creamy accepted 1/85 -> 0/85, offline on hunt-flow28..31): to cut
# arm C's "species unsure" fallbacks (Batt's decision 1). Ported from 69a1293 (proposed there as
# "v33"). Base: v34 PACED for the whole run (3.74's verdict 2026-10-18 03:46, fef68d9: the loot step
# 1.02 s faster, the input still registered)
PARAMS[35] = {**PARAMS[34], "send_gap_ab": False, "species_own": True, "species_own_ab": True}
# 36 = the LOOT RETRY: a loot cell skipped for "a unit near" is queued once more at the end of
# the step, not before 0.6 s, under the same checks. v34 run 1: 40 of 143 steps skipped >= 6 of
# their clicks; in 15 no live monster stood within 6 cells (packets) -- the target's own dying
# sprite beside the GM (the corpse match missed: its last tracked box was > 30 px off) or our own
# hand pointer. Base: v35 with the STALE-box species check for all (3.75's verdict 2026-10-18
# 06:08, 6c95acf: the own frame cut "unsure" 27 -> 16 % but landing fell 80.5 -> 63.6 %)
PARAMS[36] = {**PARAMS[35], "species_own": False, "species_own_ab": False, "loot_retry": True,
              "loot_retry_ab": True, "loot_retry_wait_s": 0.6}  # fmt: skip
# 37 = THE CURSOR'S SWORD at loot and moving-walk click points (Batt 2026-10-18, decision 2,
# option b; cursor_sword): on prt_fild06 (3.76) the detector had no box for the species it never
# learned, so 21 of the 29 non-target attack requests came from loot clicks and 5 from walk clicks.
# Interleaved per engagement. Base: v36's adopted base -- the loot retry is NOT in it (3.77: run
# 1's primary failed; adoption is Batt's)
PARAMS[37] = {**PARAMS[36], "loot_retry": False, "loot_retry_ab": False, "cursor_sword": True,
              "cursor_sword_ab": True, "cursor_sword_wait_s": 0.35}  # fmt: skip
# 38 = THE AGE-WEIGHTED SEARCH HEADING (the search study's proposal, competition.md "Search study";
# STAGED, not pre-registered: it needs >= 4 run-hours and Batt's go). Interleaved in 10-min blocks
# within each run (the field drifts between runs). Its base is set at its pre-registration
# + Batt's decision 2, option a (2026-10-18), in the base of every version from here: the cursor's
# SWORD check at LOOT clicks only (walk clicks unchanged), with a 0.6 s wait (3.78: the client
# redraws its cursor ~0.35-0.4 s in while the camera scrolls), on every engagement, ONLY on a map
# UNTRAINED_SPECIES flags (prt_fild06 yes, prt_fild08 no: inert there). Loot retry staged, not in
# (Batt's decision 1: the loot gain is not shown and each step costs +0.39 s)
PARAMS[38] = {**PARAMS[36], "loot_retry": False, "loot_retry_ab": False, "heading_age": True,
              "heading_age_ab": True, "heading_age_block_min": 10.0,
              "cursor_sword": True, "cursor_sword_ab": False, "cursor_sword_where": ("loot",),
              "cursor_sword_maps": "untrained", "cursor_sword_wait_s": 0.6}  # fmt: skip
# 39 = THE CONTINUOUS APPROACH (the conversion study, competition.md "Conversion study": the
# approach is the largest loss, +3.22 s / kill; in steer mode the GM moves 37-38 % of the time):
# the steer's continuous walk click may take the route's TAIL when nothing lies >= 3 cells ahead
# of the lead (cont_fail, 3.79: "none" in most failed steer calls, routes <= 3 cells), and the
# standstill fallback steps from the route point NEAREST the GM, not the route's start. Every walk
# gate unchanged. Batt's go 2026-10-18 16:2x ("the steer must always find a click point on the
# route ... fix the point picker, not the gates"): also the route's END when nothing else is
# left. Pre-registered as 3.80; interleaved per engagement (odd k). Its base: the coverage heading
# (v38's age heading only if v38 is adopted by its rule, switched in a commit before run 1)
PARAMS[39] = {**PARAMS[38], "heading_age": False, "heading_age_ab": False, "steer_tail": True,
              "steer_tail_ab": True, "dead_probe": True}  # fmt: skip
# 40 = THE FALSE-DEAD FIX (Batt 16:2x: "a burst ending risky must not let the dead rule abandon a
# target that is still visible/alive ... mark it skipped: risky explicitly, never dead"), on the
# death-cell verdict (3.81: after a risky last burst "ok" = 93 real / 2 alive, other = 93 / 71 on 6
# banked runs; held out on v39 runs 2-3: 20 / 2 vs 24 / 21). Pre-registered as 3.81 (b871eff);
# interleaved per engagement (odd k). Its base (3.81): v39 NOT adopted (3.80, 7dd9524) -> v38's
# base, the steer's old picker (no tail); the log-only dead_probe stays on
PARAMS[40] = {**PARAMS[39], "steer_tail": False, "steer_tail_ab": False, "false_dead_fix": True,
              "false_dead_ab": True}  # fmt: skip
# 41 = WALKING TARGETS STRUCK FROM FURTHER (3.82, pre-registered 61cf81d; Batt's GO 2026-10-19
# 07:0x): a WALKING target's strike range from strike_cells_walking (7) on odd k, as a standing
# one's (the conversion study: never-attacked walkers +1.96 s / kill; v39: the walk guard blocks
# the steer's last cells). The zone radius follows the same strike_range call. Its base: v40
# ADOPTED (3.81, aed0fb4) -> the false-dead fix on every engagement (false_dead_ab False)
PARAMS[41] = {**PARAMS[40], "false_dead_ab": False, "strike_cells_walking": 7,
              "strike_walking_ab": True}  # fmt: skip
# 43 = THE HUNTING UI LAYOUT (3.84, pre-registered 23d41f5; Batt's order 2026-10-19 ~08:4x):
# the client's layout reached at the run's start through its own controls (client_layout.ensure),
# the run's UI rectangles follow it; the dead-end ping-pong FIX (Batt: a bug, fixed with this
# version). Its base: v41 NOT adopted (3.82) -> v40's, the false-dead fix on every engagement
PARAMS[43] = {**PARAMS[40], "false_dead_ab": False, "ui_layout": "hunt",
              "dead_end_hyst_s": 10.0}  # fmt: skip
# 42 = THE STEER'S WALK GUARD FROM THE GM'S BOX, with the route tail (3.83, pre-registered e3fc195;
# Batt's decision 1, 2026-10-19 ~07:00; "keep the tail in v42, go ahead"): on odd k the steer's walk
# clicks use the GM's drawn box + 20 px instead of the 120-px circle, and its picker may take the
# route's tail. Search and loot clicks keep the circle. With the POCKET ESCAPE as a bug fix in both
# arms (3.83 amendment 2, 4d937b4; Batt approved the 60-s spread ~19:5x). Its base: v43 ADOPTED
# (3.84) -> the hunting UI layout + the ping-pong fix, the false-dead fix on every engagement
PARAMS[42] = {**PARAMS[43], "steer_tail": True, "steer_tail_ab": True, "steer_guard_box_px": 20,
              "steer_guard_ab": True, "stuck_window_s": 60.0, "stuck_extent": 18.0,
              "stuck_walked": 80.0, "stuck_escape_min": 26.0, "stuck_zone_r": 22.0,
              "stuck_zone_s": 300.0}  # fmt: skip


# --- pure parts (tested) --------------------------------------------------------------------------


def untrained_map(map_name: str) -> bool:
    """UNTRAINED_SPECIES for ``map_name``; a map it does not list raises (fail closed)."""
    if map_name not in UNTRAINED_SPECIES:
        raise ValueError(f"{map_name}: not in UNTRAINED_SPECIES (does it hold species the "
                         "detector never learned? decide and add it)")  # fmt: skip
    return UNTRAINED_SPECIES[map_name]


def sword_active(prm: dict[str, Any], map_name: str) -> bool:
    """PURE: is the cursor's SWORD check used at all in this run? v37: on any map. From v38
    (``cursor_sword_maps`` "untrained"): only on a map UNTRAINED_SPECIES flags."""
    if not prm.get("cursor_sword"):
        return False
    return prm.get("cursor_sword_maps") != "untrained" or untrained_map(map_name)


def sword_check_wanted(prm: dict[str, Any], map_name: str, where: str, k: int) -> bool:
    """PURE: does the ``where`` click ("loot" | "walk", the latter only while moving) of
    engagement ``k`` get the SWORD check? v37: both kinds, odd k when A/B. From v38 (Batt's
    decision 2, option a): loot only, every engagement, on flagged maps only."""
    if not sword_active(prm, map_name):
        return False
    if where not in prm.get("cursor_sword_where", ("loot", "walk")):
        return False
    return not prm.get("cursor_sword_ab") or k % 2 == 1


# 3.79 amendment (log-only): the continuous walk click's gates, in the order cont_click checks them
CONT_GATES = ("view", "grid", "units", "boxes", "refused", "guard")


def cheb(a: Sequence[float], b: Sequence[float]) -> float:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


class FrameGuard:
    """(v24) Every hunt-flow pointer input passes here (Batt: never a click outside the game
    frame). A MOVE is clamped into the game region: read_tag's pre-motion, 12 px up-left of a
    target at the top edge, gave y < 0, which the backend drops unanswered, and the run stopped on
    the missing ack (v23 attempt 2, 25.7 min). A CLICK outside the region is refused. Both are
    counted in ``n`` ("clamped" / "refused"); everything else passes through to the agent."""

    def __init__(self, agent: Any, region: tuple[int, int, int, int], n: Counter[str]) -> None:
        self._a, self._r, self.n = agent, region, n

    def inside(self, x: float, y: float) -> bool:
        x0, y0, w, h = self._r
        return x0 <= x < x0 + w and y0 <= y < y0 + h

    def move(self, x: int, y: int) -> None:
        x0, y0, w, h = self._r
        cx, cy = min(max(x, x0), x0 + w - 1), min(max(y, y0), y0 + h - 1)
        if (cx, cy) != (x, y):
            self.n["clamped"] += 1
        self._a.move(cx, cy)

    def click(self, x: int, y: int, button: str = "left") -> None:
        if not self.inside(x, y):
            self.n["refused"] += 1
            return
        self._a.click(x, y, button)  # the pass-through: every hunt-flow click comes here

    def __getattr__(self, k: str) -> Any:
        return getattr(self._a, k)

    def __setattr__(self, k: str, v: Any) -> None:
        if k in ("_a", "_r", "n"):
            object.__setattr__(self, k, v)
        else:  # e.g. farm0.stop_on_takeover's hook must land on the real agent
            setattr(self._a, k, v)


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


def strike_range(tr: Track, prm: dict[str, Any], k: int | None = None) -> int:
    """PURE (v4): STANDING targets from ``strike_cells_standing`` (Batt's p90, 7), WALKING ones
    from ``strike_cells`` (3); before v4 always ``strike_cells``. v41 candidate (STAGED): WALKING
    ones from ``strike_cells_walking`` too (the client walks up by itself after an attack click,
    as Batt plays; v39 run 1: the 120-px walk guard refuses the steer's clicks inside ~3 cells, so
    a walker's 3-cell range left the GM standing), on odd ``k`` when ``strike_walking_ab``."""
    vx, vy = tr.velocity()
    if prm.get("strike_cells_standing") and not (vx or vy):
        return int(prm["strike_cells_standing"])
    if prm.get("strike_cells_walking") and (
            not prm.get("strike_walking_ab") or (k is not None and k % 2 == 1)):  # fmt: skip
        return int(prm["strike_cells_walking"])
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


def risky_unproven(last_burst: str | None, death_reason: str | None) -> bool:
    """PURE (v40 candidate, Batt 2026-10-18 16:2x: "a burst ending 'risky' must not let the dead
    rule abandon a target that is still visible / alive; re-engage it, or mark it 'skipped:
    risky' explicitly, never 'dead'"). After a RISKY last burst the dead call stands only when the
    death-cell fix (loot1.death_of on the track's own sightings) says "ok": a clean
    disappearance. Measured before (6 banked runs, v36-v39): after a risky burst "ok" was a real
    death 93 times and a target still alive twice; any other reason 93 real vs 71 not. Any other
    last burst: the dead rule stands (False)."""
    return last_burst == "risky" and death_reason != "ok"


def exp_dead_on(prm: dict[str, Any], k: int) -> bool:
    """PURE (3.87, hunt-flow@44): does engagement ``k`` take its dead call from the Battle Log's
    base EXP line? ``exp_dead`` on; with ``exp_dead_ab`` only odd k (the fix arm)."""
    return bool(prm.get("exp_dead")) and (not prm.get("exp_dead_ab") or k % 2 == 1)


def exp_line_for(lines: Sequence[dict[str, Any]], t_from: int, used: set[int]
                 ) -> dict[str, Any] | None:  # fmt: skip
    """PURE (3.87): the first BASE EXP record (battle_log.Reader's) that first showed AFTER
    ``t_from`` (the engagement's first attack click, the same CLOCK_MONOTONIC ns) and is not in
    ``used`` (its ``t_ns``: each line confirms one death only). A job EXP line never counts."""
    for rec in sorted(lines, key=lambda x: int(x["t_ns"])):
        t_ = int(rec["t_ns"])
        if rec.get("type") == "base_exp" and t_ > t_from and t_ not in used:
            return rec
    return None


def checked_fallback(death_reason: str | None) -> str:
    """PURE (3.87, approved by Batt ~19:5x): the pixel dead call with no EXP line within
    ``exp_wait_s`` stands only on the death-cell verdict "ok" (v40's signal, here after every
    burst); otherwise the engagement ends ``skipped_unconfirmed`` (no loot step, the track stays
    selectable, as v40's skipped_risky)."""
    return "dead" if death_reason == "ok" else "skipped_unconfirmed"


SKIPPED_SELECTABLE = ("skipped_risky", "skipped_unconfirmed")  # the track stays selectable


class BattleLogTail:
    """3.87: the Battle Log reader for the runner -- battle_log.py's validated LIVE reader in its
    OWN process (nice 10; its numpy/Python work never holds the runner's GIL), writing the
    session's ``battle_log_live.jsonl`` as the log-only runs did; a thread here tails that file
    and keeps the records. Pixels only: the reader reads the client's chat window from frames."""

    def __init__(self, out: Path, owner_pid: int, hz: float = 10.0) -> None:
        import subprocess
        import threading

        self.out, self.owner_pid, self.hz = out, owner_pid, hz
        self.lines: list[dict[str, Any]] = []
        self.used: set[int] = set()
        self.lock = threading.Lock()
        self.halt = threading.Event()
        self.restarts = 0
        self._sp = subprocess
        self.proc = self._spawn()
        self.th = threading.Thread(target=self._tail, name="battle-log-tail", daemon=True)
        self.th.start()

    def _spawn(self) -> Any:
        log_ = (self.out.parent / "battle_log_live.out").open("a")
        return self._sp.Popen(["nice", "-n", "10", sys.executable,
                               str(Path(__file__).with_name("battle_log.py")), "live",
                               "--out", str(self.out), "--hz", str(self.hz),
                               "--until-pid", str(self.owner_pid)],
                              stdout=log_, stderr=self._sp.STDOUT)  # fmt: skip

    def _tail(self) -> None:
        while not self.out.exists() and not self.halt.is_set():
            time.sleep(0.05)
        with contextlib.suppress(FileNotFoundError), self.out.open() as fh:
            buf = ""
            while not self.halt.is_set():
                chunk = fh.readline()
                if not chunk:
                    time.sleep(0.03)
                    continue
                buf += chunk
                if not buf.endswith("\n"):
                    continue
                with contextlib.suppress(ValueError):
                    rec = json.loads(buf)
                    with self.lock:
                        self.lines.append(rec)
                buf = ""

    def alive(self) -> bool:
        """The reader process runs; restarted ONCE if it exited (False after a second exit)."""
        if self.proc.poll() is None:
            return True
        if self.restarts >= 1:
            return False
        self.restarts += 1
        self.proc = self._spawn()
        return True

    def take_base_exp(self, t_from: int) -> dict[str, Any] | None:
        with self.lock:
            rec = exp_line_for(self.lines, t_from, self.used)
            if rec is not None:
                self.used.add(int(rec["t_ns"]))
            return rec

    def stop(self) -> None:
        self.halt.set()
        with contextlib.suppress(Exception):
            self.proc.terminate()
            self.proc.wait(timeout=10)
        self.th.join(timeout=3)


def ahead_candidates(path: Sequence[Cell], here: Sequence[float], order: Sequence[int],
                     tail: bool = False) -> list[int]:  # fmt: skip
    """PURE (v5): path indices to try for the next walk click, ``order`` cells ahead of the path
    cell nearest to where we ARE (measured), the first in range first. ``tail`` (v39, the
    continuous approach): then the route's remaining cells beyond that nearest one, its END
    first -- near the end of a short route ``order`` (>= 3 ahead) has none, and the GM stood.
    And when even that is empty (the nearest cell IS the end), the end itself unless ``here``
    lies on it (Batt 2026-10-18 16:2x: the steer always finds a point on the route; only the
    gates may refuse it). So with ``tail`` the list is empty only for a one-cell route or when
    ``here`` is the route's last cell: the walk already ends there."""
    if not path:
        return []
    ci = min(range(len(path)), key=lambda i: cheb(path[i], here))
    out = [ci + k for k in order if 0 < ci + k < len(path)]
    if tail:
        out += [j for j in range(len(path) - 1, ci, -1) if j > 0 and j not in out]
        end = len(path) - 1
        at_ = (int(round(here[0])), int(round(here[1])))
        if not out and end > 0 and at_ != tuple(path[end]):
            out.append(end)
    return out


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


def area_centre(area: Any) -> Cell:
    """PURE (the held-out map test): the area cell nearest the area's centroid -- a start anchor
    derived from the map alone (prt_fild08 keeps hunt.START, its tuned open field)."""
    ys, xs = np.nonzero(np.asarray(area, dtype=bool))
    if not len(xs):
        raise SystemExit("an empty search area")
    i = int(np.argmin((xs - xs.mean()) ** 2 + (ys - ys.mean()) ** 2))
    return int(xs[i]), int(ys[i])


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


def fresh_share(swept: Any, now: float, cell: Sequence[int], half: int, recent_s: float) -> float:
    """PURE (v22): the share of cells within ``half`` (Chebyshev) of ``cell`` NOT swept in the last
    ``recent_s`` (``swept`` = the last time each cell was in our view; very negative = never)."""
    h, w = swept.shape
    x0, x1 = max(0, int(cell[0]) - half), min(w, int(cell[0]) + half + 1)
    y0, y1 = max(0, int(cell[1]) - half), min(h, int(cell[1]) + half + 1)
    win = swept[y0:y1, x0:x1]
    return float((win < now - recent_s).mean()) if win.size else 0.0


def heading_goal_cov(area: Any, here: Cell, st: dict[str, Any], swept: Any, now: float,
                     recent_s: float = 180.0, half: int = 12, keep: float = 0.8,
                     max_len: int = 40, min_run: int = 8,
                     hyst_s: float = 0.0, no135: bool = False) -> Cell | None:  # fmt: skip
    """PURE (v22, the SEARCH GAP: the bot swept 0.63x Batt's ground per 10 min -- overlap, turning
    back, short net legs): v18's heading search with a memory of the bot's OWN swept ground.
    The current heading and the +-45 / +-90 / +-135 deg turns that run >= ``min_run`` cells each
    score run x (0.25 + the FRESH share around the ray's end: ground not in our view for
    ``recent_s``). The heading is KEPT while it scores >= ``keep`` x the best; otherwise the
    smallest turn scoring that much wins. A reversal only at a real dead end, as v18."""
    ang = float(st.setdefault("ang", 0.0))
    cands = []
    for deg, sgn in ((0, 1), (45, 1), (45, -1), (90, 1), (90, -1), (135, 1), (135, -1)):
        a2 = ang + sgn * math.radians(deg)
        n2, c2 = ray_run_angle(area, here, a2, max_len)
        if n2 < min_run:
            continue
        f2 = fresh_share(swept, now, c2, half, recent_s)
        cands.append((n2 * (0.25 + f2), deg, sgn, a2, c2, f2))
    if no135 and any(c[1] <= 90 for c in cands):
        # P4 (Batt 2026-10-19, "reverse only when 0/45/90 are all blocked; matches my rule"):
        # the +-135 turns (a reversal by the 120-deg rule) only when nothing within +-90 runs
        cands = [c for c in cands if c[1] <= 90]
    if not cands:
        if hyst_s and now - float(st.get("rev_t", -math.inf)) < hyst_s:
            # the dead-end PING-PONG fix (Batt 2026-10-19, a bug: v39 run 2 flipped between two
            # dead-end goals 52 times in ~110 s): a second dead end within ``hyst_s`` of the last
            # reversal does not reverse again; the best of the 8 COMPASS headings by run x
            # (0.25 + fresh), any run >= 2 -- an absolute choice, so repeated calls agree
            best: tuple[float, float, Cell] | None = None
            for k8 in range(8):
                a8 = k8 * math.pi / 4
                n8, c8 = ray_run_angle(area, here, a8, max_len)
                if n8 < 2:
                    continue
                sc8 = n8 * (0.25 + fresh_share(swept, now, c8, half, recent_s))
                if best is None or sc8 > best[0]:
                    best = (sc8, a8, c8)
            if best is None:
                return None
            d8 = (best[1] - ang + math.pi) % (2 * math.pi) - math.pi
            st.update(ang=best[1], turn=round(math.degrees(d8), 1), fresh=None,
                      dead_end_escape=True)  # fmt: skip
            return best[2]
        a2 = ang + math.pi  # a real dead end: the only reversal
        n2, c2 = ray_run_angle(area, here, a2, max_len)
        st.update(ang=a2, turn=180.0, fresh=None, rev_t=now, dead_end_escape=False)
        return c2 if n2 >= 2 else None
    top = max(c[0] for c in cands)
    ok_ = [c for c in cands if c[0] >= keep * top]
    pick = min(ok_, key=lambda c: (c[1], -c[0]))  # the smallest turn among the good ones
    st.update(ang=pick[3], turn=float(pick[2] * pick[1]), fresh=round(pick[5], 2),
              dead_end_escape=False)  # fmt: skip
    return pick[4]


def stuck_pocket(samples: Sequence[tuple[float, Cell, bool]], now: float, window_s: float,
                 extent: float, walked_min: float,
                 search_share: float = 0.8) -> tuple[float, float] | None:  # fmt: skip
    """PURE (Batt 2026-10-19, a BUG: v43 run 2 spent 53 min in a cliff / pond pocket, its search
    turning +-90 / +-135 -- never the 180 the ping-pong fix watches): over the last ``window_s``
    (2-s samples of (time, our cell, searching)), mostly searching, every cell within ``extent``
    (Chebyshev) of their centre while >= ``walked_min`` cells were walked -> the pocket's centre;
    else None. Sized on the run: 60 s / 18 cells / 80 cells fired at the stall's start (minute
    9:00) and never on 4 normal runs (v43 run 1, v41 runs 1, 2, 4)."""
    win = [x for x in samples if now - x[0] <= window_s]
    if not win or now - win[0][0] < window_s - 2.5 or len(win) < 3:
        return None
    if sum(1 for x in win if x[2]) < search_share * len(win):
        return None
    cx = sum(c[0] for _t, c, _s in win) / len(win)
    cy = sum(c[1] for _t, c, _s in win) / len(win)
    if max(max(abs(c[0] - cx), abs(c[1] - cy)) for _t, c, _s in win) > extent:
        return None
    walked = sum(cheb(a[1], b[1]) for a, b in zip(win, win[1:], strict=False))
    return (cx, cy) if walked >= walked_min else None


def escape_goal(area: Any, here: Cell, centre: tuple[float, float], min_dist: float,
                max_nodes: int = 40_000) -> Cell | None:  # fmt: skip
    """PURE: the NEAREST cell reachable from ``here`` on the walkable grid (8-connected, breadth
    first: real paths, not ray headings) that lies >= ``min_dist`` (Chebyshev) from ``centre``;
    None when none is reachable within ``max_nodes``."""
    from collections import deque

    a = np.asarray(area, dtype=bool)
    h, w = a.shape
    start = (int(here[0]), int(here[1]))
    if not (0 <= start[0] < w and 0 <= start[1] < h):
        return None
    seen = {start}
    dq = deque([start])
    while dq and len(seen) < max_nodes:
        c = dq.popleft()
        if max(abs(c[0] - centre[0]), abs(c[1] - centre[1])) >= min_dist:
            return c
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                n_ = (c[0] + dx, c[1] + dy)
                if n_ not in seen and 0 <= n_[0] < w and 0 <= n_[1] < h and a[n_[1], n_[0]]:
                    seen.add(n_)
                    dq.append(n_)
    return None


# v38 candidate (the SEARCH study, 2026-10-18, scripts/search_study.py): the yield of ground by how
# long since WE last saw it, relative to ground never seen this run. The bot's own kills deplete the
# ground it covers; a killed mob respawns anywhere on the map (prt_fild08: all spawns whole-map).
# Measured over v32-v36 (6 h): <= 10 min 0.40-0.47 of never-seen, 10-20 min 0.63, > 20 min 1.02.
AGE_REL = ((600.0, 0.32), (1200.0, 0.5), (math.inf, 0.82))
NEVER_REL = 1.0
SEEN_NEVER = -1e8  # a last-seen grid value below this = never seen this run


def rel_yield(age_s: Any) -> Any:
    """PURE (v38): the relative yield of ground last seen ``age_s`` ago (inf = never): AGE_REL;
    the same as search_study.rel_yield (a test pins it)."""
    a = np.asarray(age_s, dtype=float)
    out = np.full(a.shape, NEVER_REL)
    fin = np.isfinite(a)
    lo = 0.0
    for hi, v in AGE_REL:
        out[fin & (a > lo) & (a <= hi)] = v
        lo = hi
    out[fin & (a <= 0)] = AGE_REL[0][1]
    return out


def band_score_age(area: Any, here: Cell, ang: float, last_seen: Any, now: float,
                   offsets: Sequence[Cell], max_len: int = 40, min_run: int = 8,
                   ms_cell: float = MS_CELL) -> tuple[float, int, Cell] | None:  # fmt: skip
    """PURE (v38): a heading's expected yield per walking second -- the cells our on-screen
    ``offsets`` would bring into view along the ray (and do not cover from ``here``), each
    weighted by rel_yield of its age (``last_seen``: monotonic s, < SEEN_NEVER = never), over the
    ray's walk time (a diagonal step 1.4x). None when the ray runs < ``min_run`` cells. Returns
    (score, cells, the ray's last cell). search_study.band_score with the bot's own clock."""
    h, w = np.asarray(area).shape
    dx, dy = math.cos(ang), math.sin(ang)
    k = max(abs(dx), abs(dy))
    dx, dy = dx / k, dy / k
    cells = [here]
    for i in range(1, max_len + 1):
        c = (int(round(here[0] + dx * i)), int(round(here[1] + dy * i)))
        if not (0 <= c[0] < w and 0 <= c[1] < h) or not area[c[1], c[0]]:
            break
        cells.append(c)
    if len(cells) - 1 < min_run:
        return None
    offs = np.asarray(offsets, dtype=int).reshape(-1, 2)
    pad = int(np.abs(offs).max()) + 1
    xs, ys = [c[0] for c in cells], [c[1] for c in cells]
    gx0, gy0 = max(0, min(xs) - pad), max(0, min(ys) - pad)
    gx1, gy1 = min(w, max(xs) + pad + 1), min(h, max(ys) + pad + 1)
    band = np.zeros((gy1 - gy0, gx1 - gx0), dtype=bool)
    now_view = np.zeros_like(band)
    for i, c in enumerate(cells):
        px, py = offs[:, 0] + c[0] - gx0, offs[:, 1] + c[1] - gy0
        ok = (px >= 0) & (px < band.shape[1]) & (py >= 0) & (py < band.shape[0])
        (now_view if i == 0 else band)[py[ok], px[ok]] = True
    band &= ~now_view & np.asarray(area, dtype=bool)[gy0:gy1, gx0:gx1]
    ls = np.asarray(last_seen, dtype=float)[gy0:gy1, gx0:gx1][band]
    ages = np.where(ls < SEEN_NEVER, np.inf, now - ls)
    walk_s = sum((1.4 if (a[0] != b[0] and a[1] != b[1]) else 1.0)
                 for a, b in zip(cells, cells[1:], strict=False)) * ms_cell / 1000  # fmt: skip
    return float(rel_yield(ages).sum()) / walk_s, int(band.sum()), cells[-1]


def heading_goal_age(area: Any, here: Cell, st: dict[str, Any], last_seen: Any, now: float,
                     offsets: Sequence[Cell], keep: float = 0.8, max_len: int = 40,
                     min_run: int = 8) -> Cell | None:  # fmt: skip
    """PURE (v38 candidate, the search study's proposal): v22's heading rule (keep the heading
    while it scores >= ``keep`` x the best, else the smallest turn that does; a reversal only at a
    real dead end) with the AGE-WEIGHTED score per walking second (band_score_age) in place of
    run x fresh share."""
    ang = float(st.setdefault("ang", 0.0))
    cands = []
    for deg, sgn in ((0, 1), (45, 1), (45, -1), (90, 1), (90, -1), (135, 1), (135, -1)):
        a2 = ang + sgn * math.radians(deg)
        got = band_score_age(area, here, a2, last_seen, now, offsets, max_len, min_run)
        if got is not None:
            cands.append((got[0], deg, sgn, a2, got[2]))
    if not cands:
        a2 = ang + math.pi  # a real dead end: the only reversal
        n2, c2 = ray_run_angle(area, here, a2, max_len)
        st.update(ang=a2, turn=180.0, fresh=None)
        return c2 if n2 >= 2 else None
    top = max(c[0] for c in cands)
    ok_ = [c for c in cands if c[0] >= keep * top]
    pick = min(ok_, key=lambda c: (c[1], -c[0]))
    st.update(ang=pick[3], turn=float(pick[2] * pick[1]),
              fresh=round(pick[0] / top, 2) if top else None)  # fmt: skip
    return pick[4]


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
               exclude: tuple[float, float, float, float],
               ui_rects: Sequence[tuple[float, float, float, float]] = (),
               pointer: tuple[float, float] | None = None) -> float:  # fmt: skip
    """PURE (the walk guard, from v16): the share of PINK pixels -- R over G by > 51, B not under
    G by > 10, not dark: a Poring's or a Creamy's colours, never the ground's yellow-brown or
    green -- within ``radius`` px of the click pixel (u, v), outside ``exclude`` (the GM's own
    sprite: its red hair). ``crop`` is the frame region whose top-left is ``origin`` (client px),
    BGR(A) as Screen.grab returns it. From v17, ``ui_rects`` (the client's static windows) are
    left out too: their red icons are not sprites (v16 run 1: 30 % of the first 200 candidates
    refused as pink, many beside the chat window and the skill bar). From v21, ``pointer`` (where
    our pointer rests) leaves out the client's own drawn CURSOR: its red no-entry ring read as pink
    (the agent's round 1, 2026-10-17: walks refused beside a ring the last click left)."""
    a = np.asarray(crop)[..., :3].astype(np.int16)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[origin[1] : origin[1] + h, origin[0] : origin[0] + w]
    m = (xx - u) ** 2 + (yy - v) ** 2 <= radius * radius
    m &= ~((xx >= exclude[0]) & (xx <= exclude[2]) & (yy >= exclude[1]) & (yy <= exclude[3]))
    for x0, y0, x1, y1 in ui_rects:
        m &= ~((xx >= x0) & (xx <= x1) & (yy >= y0) & (yy <= y1))
    if pointer is not None:
        pu, pv = pointer
        m &= ~((xx >= pu - 26) & (xx <= pu + 40) & (yy >= pv - 26) & (yy <= pv + 40))
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


def box_dist(u: float, v: float, box: Sequence[float]) -> float:
    """PURE: px from (u, v) to the box (x0, y0, x1, y1); 0 inside it."""
    dx = max(box[0] - u, 0.0, u - box[2])
    dy = max(box[1] - v, 0.0, v - box[3])
    return math.hypot(dx, dy)


def walk_guard_box_why(u: float, v: float, share: float, box: Sequence[float], margin: float,
                       pink_max: float) -> str | None:  # fmt: skip
    """PURE (v42 candidate, STAGED; Batt 2026-10-19 decision 1): the walk guard for STEER clicks
    only -- refused within ``margin`` px of the GM's drawn sprite box (GM_SPRITE_BOX) instead of
    the 120-px circle; the pink rule unchanged. Sized on hunt-flow1-15's pre-guard walk clicks:
    the client turned 5 / 1,397 clicks within 60 px of the box into a Creamy attack (0.36 %),
    11 / 18,869 beyond 100 px (0.06 %); box + 20 px refuses every 1-cell step and the cells behind
    the sprite and frees 13 / 16 cells at 2 and 21 / 24 at 3 that the circle refuses."""
    if box_dist(u, v, box) < margin:
        return "near_gm_box"
    if share > pink_max:
        return "pink"
    return None


LOOT_JITTER = ((-6.0, 3.0), (6.0, -4.0), (0.0, 0.0))  # v23: px around a cell's click point


def loot_plan(
    dcell: Cell, center_clicks: int, ring_clicks: int
) -> list[tuple[Cell, tuple[float, float]]]:
    """PURE (v23, Batt 2026-10-17, his looting as a FIXED workflow): the death cell first (a
    short burst of ``center_clicks``), then the 8 cells of the 3 x 3 in the server's drop
    pattern order (SE, W, N, then the rest: deathcell.scan_order), ``ring_clicks`` each; every
    click a (cell, pixel jitter) -- the jitter (the item sprites' measured bias, -6 / +3 px, then
    the other side) covers the sub-cell offsets an item lands at."""
    from poring_dataset.deathcell import scan_order

    plan: list[tuple[Cell, tuple[float, float]]] = []
    for i, c in enumerate(scan_order(dcell, 1)):
        for k in range(center_clicks if i == 0 else ring_clicks):
            plan.append((c, LOOT_JITTER[k % len(LOOT_JITTER)]))
    return plan


def loot_union_plan(
    dcell: Cell, extra: Sequence[Sequence[int]], center_clicks: int, ring_clicks: int
) -> list[tuple[Cell, tuple[float, float]]]:
    """PURE (v33, the looter chain): ``loot_plan`` around ``dcell`` (the looter's own death cell),
    then each ``extra`` cell (the first kill's cells still unclicked when the looter came) outside
    that 3 x 3, once, in the given order; no cell twice."""
    plan = loot_plan(dcell, center_clicks, ring_clicks)
    seen = {c for c, _j in plan}
    for e in extra:
        c = (int(e[0]), int(e[1]))
        if c not in seen:
            seen.add(c)
            plan.append((c, LOOT_JITTER[0]))
    return plan


def items_first(
    plan: Sequence[tuple[Cell, tuple[float, float]]],
    icons: Sequence[tuple[Cell, tuple[float, float]]],
    gm_px: Sequence[float] = GM_SPRITE_PX,
) -> list[tuple[Cell, tuple[float, float], tuple[float, float] | None]]:
    """PURE (v33, LOOT IS A RACE): the matcher's floor items (cell, sprite pixel) FIRST, nearest
    the GM first (within pickup reach the client picks at once), each clicked at its own pixel;
    then the whole fixed plan (the matcher's recall is ~0.4: the 3 x 3 still catches the rest)."""
    first = sorted(icons, key=lambda i: math.hypot(i[1][0] - gm_px[0], i[1][1] - gm_px[1]))
    return [(c, (0.0, 0.0), px) for c, px in first] + [(c, j, None) for c, j in plan]


def loot_retry_of(
    step: Sequence[Any], why: str, retry_on: bool, now: float, wait_s: float
) -> tuple[Any, ...] | None:
    """PURE (v36, the LOOT RETRY): the retry entry for a loot step just skipped -- only for a
    "unit" skip (never pink / npc / view), only in the retry arm, and never for a retry itself (a
    4-tuple carries its not-before time): ``(cell, jitter, pixel, now + wait_s)``."""
    if why != "unit" or not retry_on or len(step) > 3:
        return None
    return (step[0], step[1], step[2], now + wait_s)


def new_pink_px(after: Any, before: Any | None, u: float, v: float, radius: int, grow: int = 6,
                shift: tuple[float, float] = (0.0, 0.0),
                exclude: tuple[float, float, float, float] | None = None) -> int:  # fmt: skip
    """PURE (v23): how many PINK pixels (the walk guard's rule) within ``radius`` of (u, v) in
    ``after`` were NOT pink (within ``grow`` px) in ``before`` -- both full game-region frames, BGR.
    ``shift`` = how far the ground moved on screen since ``before`` (the camera follows the GM): the
    pixel (u, v) now was (u - shift) then. A Poring's pink corpse, there before the death, does not
    count; a Creamy flying in does. The count, not a share: one Apple's sprite holds 64 pink
    pixels and a Red Herb's 33 (item_icons' templates), a Creamy's wings far more. No ``before``:
    every pink pixel counts."""
    a = np.asarray(after)[..., :3].astype(np.int16)
    h, w = a.shape[:2]
    y0, y1 = max(0, int(v) - radius), min(h, int(v) + radius + 1)
    x0, x1 = max(0, int(u) - radius), min(w, int(u) + radius + 1)
    if y1 <= y0 or x1 <= x0:
        return 0

    def pinkm(c: Any) -> Any:
        b_, g_, r_ = c[..., 0], c[..., 1], c[..., 2]
        return (r_ - g_ > 51) & (b_ - g_ >= -10) & (c.max(-1) > 89)

    pk = pinkm(a[y0:y1, x0:x1])
    if before is not None:
        bf = np.asarray(before)[..., :3].astype(np.int16)
        dx, dy = int(round(shift[0])), int(round(shift[1]))
        old = np.zeros_like(pk)
        by0, by1, bx0, bx1 = y0 - dy, y1 - dy, x0 - dx, x1 - dx
        cy0, cy1, cx0, cx1 = max(0, by0), min(bf.shape[0], by1), max(0, bx0), min(bf.shape[1], bx1)
        if cy1 > cy0 and cx1 > cx0:
            old[cy0 - by0 : cy1 - by0, cx0 - bx0 : cx1 - bx0] = pinkm(bf[cy0:cy1, cx0:cx1])
        for _ in range(grow):  # a small dilation: the shift is measured, not exact
            o2 = old.copy()
            o2[1:, :] |= old[:-1, :]
            o2[:-1, :] |= old[1:, :]
            o2[:, 1:] |= old[:, :-1]
            o2[:, :-1] |= old[:, 1:]
            old = o2
        pk &= ~old
    yy, xx = np.mgrid[y0:y1, x0:x1]
    m = (xx - u) ** 2 + (yy - v) ** 2 <= radius * radius
    if exclude is not None:  # v25: the GM's own sprite (its red hair stays at the screen centre
        # while BEFORE is shifted by the ground: v24 skipped 1-3 loot cells a kill as "pink")
        m &= ~((xx >= exclude[0]) & (xx <= exclude[2]) & (yy >= exclude[1]) & (yy <= exclude[3]))
    return int((pk & m).sum())


LOOT_FOOT_PX = (3.0, 9.0)  # v24: a strike click aims at the body; the drops lie ~9 px lower


def death_cell_hybrid(click_cell: Cell, gm_cell: Cell) -> Cell:
    """PURE (v24): the fixed loot's death cell. A melee kill dies next to the GM: the cell under
    the last strike click when it is within 1 cell of the GM, else the GM's neighbour in that
    click's direction (offline on v21 / v22 / v23, 340 drops: 63 % in its 3 x 3, 87 % within 2
    cells, against 61 % / 79 % for the click's cell alone)."""
    if max(abs(click_cell[0] - gm_cell[0]), abs(click_cell[1] - gm_cell[1])) <= 1:
        return click_cell

    def sgn(a: int) -> int:
        return (a > 0) - (a < 0)

    return (gm_cell[0] + sgn(click_cell[0] - gm_cell[0]),
            gm_cell[1] + sgn(click_cell[1] - gm_cell[1]))  # fmt: skip


def nearest_cell(project: Any, origin: Cell, u: float, v: float, radius: int = 9) -> Cell:
    """PURE (v24): the cell within ``radius`` of ``origin`` whose projection (``project(cell)`` ->
    (u, v)) lies nearest the pixel (u, v)."""
    best: tuple[float, Cell] | None = None
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            c = (origin[0] + dx, origin[1] + dy)
            pu, pv = project(c)
            d = (pu - u) ** 2 + (pv - v) ** 2
            if best is None or d < best[0]:
                best = (d, c)
    assert best is not None
    return best[1]


def belief_ghost(bel: Any, t_ns: int, dead: Sequence[tuple[float, Cell]], now_s: float,
                 variant: str, unseen_s: tuple[float, float] = (1.0, 10.0),
                 min_mass: float = 0.3, min_n: int = 2, dead_cells: float = 2.0,
                 dead_s: float = 30.0,
                 skip: Sequence[int] | set[int] = ()) -> dict[str, Any] | None:  # fmt: skip
    """PURE on a belief_map.BeliefMap (v27, Batt's "Battleship"): the HIDDEN track worth a probe
    -- seen >= ``min_n`` times, unseen for ``unseen_s`` (the offline eval: within 1 cell 66 / 54 /
    26 % at 1-2 / 2-5 / 5-10 s), its existence mass after negative evidence >= ``min_mass``, and
    not within ``dead_cells`` of one of our kills in the last ``dead_s`` (a dead monster's track
    lingers). The best by mass, then recency: {tid, probes (top-3 spaced cells), mass, unseen_s,
    last}; None when there is none."""
    best: tuple[float, float, Any] | None = None
    skip_ = set(skip)
    for tr in bel.tracks.values():
        if tr.tid in skip_:
            continue  # v28: its probe was reached already
        u_s = (t_ns - tr.t) / 1e9
        if tr.n < min_n or not (unseen_s[0] <= u_s <= unseen_s[1]):
            continue
        if any(now_s - td <= dead_s and cheb(tr.cell, dc) <= dead_cells for td, dc in dead):
            continue
        _p, m = bel.posterior(tr, t_ns, variant)
        if m < min_mass:
            continue
        key = (m, -u_s, tr)
        if best is None or key[:2] > best[:2]:
            best = key
    if best is None:
        return None
    tr = best[2]
    return {"tid": tr.tid, "probes": bel.probes(tr, t_ns, variant, 3, True), "mass": best[0],
            "unseen_s": -best[1], "last": tr.cell}  # fmt: skip


def shifted_crop(img: Any, x0: int, y0: int, w: int, h: int) -> Any:
    """PURE (v23): the w x h region of ``img`` whose top-left is (x0, y0), zero where it falls
    outside ``img``."""
    a = np.asarray(img)[..., :3]
    out = np.zeros((h, w, 3), a.dtype)
    cx0, cy0, cx1, cy1 = max(0, x0), max(0, y0), min(a.shape[1], x0 + w), min(a.shape[0], y0 + h)
    if cx1 > cx0 and cy1 > cy0:
        out[cy0 - y0 : cy1 - y0, cx0 - x0 : cx1 - x0] = a[cy0:cy1, cx0:cx1]
    return out


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


def nearest_cell_frac(world: Any, origin: Sequence[float], center: Cell, u: float, v: float,
                      radius: int = 9) -> Cell:  # fmt: skip
    """``nearest_cell`` over ``frac_project`` (the camera on the FRACTIONAL ``origin``) in ONE
    projection call -- the same cell, the same tie order (v33 speed fix, 2026-10-17 23:3x: one
    frac_project costs ~3 ms, so the per-cell loop took ~1 s at radius 9 on EVERY kill's death
    cell and ~0.3 s per matched item at radius 4)."""
    r0 = (int(round(origin[0])), int(round(origin[1])))
    fx, fy = origin[0] - r0[0], origin[1] - r0[1]
    cells = [(center[0] + dx, center[1] + dy)
             for dx in range(-radius, radius + 1) for dy in range(-radius, radius + 1)]  # fmt: skip
    world.position = r0
    p = np.asarray(world.project([(c[0] - fx, c[1] - fy) for c in cells]), dtype=float)
    d = (p[:, 0] - u) ** 2 + (p[:, 1] - v) ** 2
    return cells[int(np.argmin(d))]


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

    import client_layout as cl

    # v43 (Batt 2026-10-19): the run's UI rectangles follow its client layout -- selected BEFORE
    # any mask module (route_preview / ui_mask / work_zone / loot1) is imported below
    cl.select(PARAMS[version].get("ui_layout") or "standard")

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
    try:
        sword_active(prm, MAP)  # an unlisted map refuses before any input (UNTRAINED_SPECIES)
    except ValueError as e:
        raise f0.FarmStop(f"hunt-flow refused: {e}") from None
    ok_imm, why_imm = f0.immunity_confirmed()
    if not ok_imm:
        raise f0.FarmStop(f"hunt-flow refused: the GM is not confirmed immune ({why_imm})")
    lock = record_session.read_lock(r.ROOT / "state")
    if str(lock.backend) != "rdp":
        raise f0.FarmStop(f"hunt-flow refused: RDP-only cursor references (lock {lock.backend})")
    gat = gatmod.parse((cam.GAT_DIR / f"{MAP}.gat").read_bytes())
    ok = stand_grid(MAP, gat)
    ok0 = ok.copy()  # the walkable grid before any refusal carves it (the stall breaker's)
    kb = r.ROOT / "data" / "kb"
    warps = json.loads((kb / "warps.json").read_text()).get(MAP, [])
    npcs = json.loads((kb / "npc_cells.json").read_text())["maps"].get(MAP, {}).get("npcs", [])
    keep = [(w["x"], w["y"], w["span_x"], w["span_y"]) for w in warps]
    keep += [(n["x"], n["y"], 1, 1) for n in npcs]
    area = hc.search_area(ok, keep, margin=10)
    if MAP == "prt_fild08":
        start = hunt.start_cell(area, seed)
    else:  # a held-out map: an anchor from the map alone, nothing tuned there
        start = hunt.start_cell(area, seed, near=area_centre(main_component(area)))
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

    last_strike: dict[int, tuple[int, float, float]] = {}  # v24: track -> (t_ns, u, v)

    def click_log(rec: dict[str, Any]) -> None:
        if rec.get("kind") in ("strike", "strike_burst") and rec.get("track") is not None:
            last_strike[int(rec["track"])] = (int(rec["t"]), float(rec["u"]), float(rec["v"]))
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
    bl_tail: BattleLogTail | None = None  # 3.87: the Battle Log reader (exp_dead only)
    guard_n: Counter[str] = Counter()  # v16+: the walk guard's verdicts (in the summary)
    fg_n: Counter[str] = Counter()
    with r.session(f"rule:{RULE}@{version}") as (agent_raw, screen):
        f0.stop_on_takeover(agent_raw)  # on the REAL agent: its send() calls the hook
        agent = FrameGuard(agent_raw, r.game_region(), fg_n)  # v24: no input off the frame
        pace: dict[str, Any] = {"block": None, "on": False, "t0": None}

        @contextlib.contextmanager
        def typing_pace() -> Any:
            """v34: a helper that TYPES (/where, the weight clear) keeps the default pacing (the
            50 ms drain before every send); only the hunt's own pointer input is paced."""
            old_ = agent_raw.min_send_gap_s
            agent_raw.min_send_gap_s = None
            try:
                yield
            finally:
                agent_raw.min_send_gap_s = old_

        def pace_tick(now_: float) -> None:
            """v34: the paced / default block at ``now_`` (10-min blocks; odd seeds start
            paced); logged at each change."""
            if not prm.get("send_gap_s"):
                return
            if pace["t0"] is None:
                pace["t0"] = now_
            blk_ = int((now_ - pace["t0"]) / (60.0 * prm["send_gap_ab_min"]))
            if blk_ == pace["block"]:
                return
            on_ = not prm.get("send_gap_ab") or (blk_ + seed) % 2 == 1  # off: paced all run
            pace.update(block=blk_, on=on_)
            agent_raw.min_send_gap_s = float(prm["send_gap_s"]) if on_ else None
            ev({"kind": "send_gap", "block": blk_, "on": on_})

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

            mm_rect = selfpos.default_rect()

            def read_position_quick() -> Cell | None:
                """v33: the same readout from a grab of ITS rect only (the loot step's check
                before each click: the main loop's 0.3 s re-anchor waits behind the step)."""
                x_, y_, w_, h_ = mm_rect
                img_ = np.ascontiguousarray(
                    np.asarray(screen.grab(gx0 + x_, gy0 + y_, w_, h_)[1])[..., :3]
                )
                xy = selfpos.read_rect(selfpos.to_gray(img_), digits).xy
                return None if xy is None else (int(xy[0]), int(xy[1]))

            def refix_now() -> str | None:
                """v33 (the loot TREADMILL fix): re-anchor on the readout when the odometry is >
                loot_refix_cells off it -> "refix"; "jump" when > JUMP_CELLS (the main loop's
                guard decides); None when they agree or nothing reads. v28-v32: 29-48 % of loot
                steps sent the GM >= 4 cells off the death cell (by the loot clicks' own
                destinations; first stated 62-77 %, a judge window that overstated) -- a stale
                odometry re-projects
                every click to the same screen pixels and the GM walks a treadmill (v32 run 1:
                13 cells, a jump stop)."""
                mp_r = measured_pos()
                if mp_r is None:
                    return None
                t_rf = r.ns()
                mm_l = read_position_quick()
                if mm_l is None:
                    return None
                if cheb(mm_l, mp_r) > JUMP_CELLS:
                    return "jump"
                if cheb(mm_l, mp_r) > prm["loot_refix_cells"]:
                    mstate["anchor"] = (mm_l, odo_at(hist_now(), t_rf))
                    return "refix"
                return None

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
                hunt_tabs = prm.get("ui_layout") == "hunt"
                if hunt_tabs:  # v43: /where's reply lands on Regular Chat, not on Battle Log
                    cl.select_tab(agent_raw, screen, "regular")
                try:
                    with typing_pace():  # v34: /where is TYPED
                        got = relocalise(agent, screen, world, noentry, band)
                        bench.close_chat(agent_raw, screen)
                finally:
                    if hunt_tabs:
                        cl.select_tab(agent_raw, screen, "battle")
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
            # Batt 2026-10-18: the runner REBUILDS the hunting state itself when it is not there
            # (Base Lv 70, STR 99 by the status window; gm_state.ensure_hunting), and keeps it
            if prm.get("ui_layout"):
                # v43: the client's layout reached through its own controls (F12 / the Basic
                # Info arrow / a chat tab), each step verified; unreadable -> stop (never blind)
                # an open chat input draws the chat window as active and hides the tab templates
                # (v43 run 2's start, after run 1's restore typed lines): closed first, by the UI
                # gate's known step
                bench.close_chat(agent_raw, screen)
                try:
                    lay_ = cl.ensure(agent_raw, screen, prm["ui_layout"])
                except cl.LayoutError as exc:
                    raise f0.FarmStop(f"client layout: {exc}") from exc
                ev({"kind": "client_layout", "layout": lay_["layout"], "steps": lay_["steps"],
                    "dist": lay_["state"].get("dist")})  # fmt: skip
            before = gm_state.ensure_hunting(agent_raw, screen, why=f"hunt-flow@{version}:before",
                                             out_dir=log.dir / "gm_state", loot=True)  # fmt: skip
            ev({"kind": "gm_state_before", **f0._brief(before)})
            r.gm(agent_raw, screen, f"@warp {MAP} {start[0]} {start[1]}")
            time.sleep(rr.SCENE_ENTRY_S)
            bench.close_chat(agent_raw, screen)
            r.activate_client(agent_raw, screen)
            sampler = loot1.Sampler(det)
            sampler.start()
            if prm.get("exp_dead"):
                # 3.87: the reader needs the Battle Log tab shown (the hunting layout)
                if prm.get("ui_layout") != "hunt":
                    raise f0.FarmStop("exp_dead needs ui_layout 'hunt' (the Battle Log tab)")
                import os

                bl_tail = BattleLogTail(log.dir / "battle_log_live.jsonl", os.getpid())
                ev({"kind": "battle_log_reader", "pid": bl_tail.proc.pid})
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
            # v37 (Batt 2026-10-18, decision 2 option b): the client's own SWORD cursor checked at
            # every loot click and every walk click made while the GM moves -- a unit check that
            # does not need the detector to know the species (cursor_sword)
            # From v38 (Batt's decision 2, option a): loot clicks only, on flagged maps only
            sword_refs: Any = None
            if sword_active(prm, MAP):
                import cursor_sword as csw_

                sword_refs = csw_.SwordRefs.load()

            def steer_tail_on(k_: int) -> bool:
                """v39 (the continuous approach): the steer's walk click may take the route's
                tail, and its standstill fallback steps from the nearest route point; odd k when
                A/B (interleaved per engagement)."""
                return bool(prm.get("steer_tail")) and (
                    not prm.get("steer_tail_ab") or k_ % 2 == 1
                )  # fmt: skip

            def steer_box_on(k_: int) -> bool:
                """v42 candidate (STAGED; Batt 2026-10-19 decision 1): the STEER's walk clicks
                use the GM-box guard (``steer_guard_box_px``) instead of the 120-px circle; odd k
                when A/B. Search walk clicks and loot clicks keep the current guard."""
                return prm.get("steer_guard_box_px") is not None and (
                    not prm.get("steer_guard_ab") or k_ % 2 == 1
                )  # fmt: skip

            def sword_on(k_: int, where: str) -> bool:
                """The cursor check for a ``where`` click of engagement ``k_``
                (sword_check_wanted)."""
                return sword_refs is not None and sword_check_wanted(prm, MAP, where, k_)

            def sword_verdict(u_: float, v_: float, where: str) -> str:
                """v37: the pointer to (u_, v_) in two motions, the cursor read there: "clear"
                (click), "sword" or "unknown" (no click). Moves only."""
                res_ = csw_.check(agent, screen, sword_refs, gx0, gy0, u_, v_,
                                  wait_s=float(prm["cursor_sword_wait_s"]))  # fmt: skip
                ptr[0] = (u_, v_)
                ev({"kind": "cursor_sword", "where": where, "u": round(u_, 1),
                    "v": round(v_, 1), "verdict": res_["verdict"], "ms": res_["ms"],
                    "reads": len(res_["reads"]), "rec": res_["rec"]})  # fmt: skip
                return str(res_["verdict"])

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

            def rest_ptr() -> None:
                """v26 / v28: the pointer to REST_PX. From v28 in TWO motions: the client draws
                its own cursor (and resolves what is under it) only where a second motion leaves
                it -- one jump left the drawn cursor on the world spot (checked live 2026-10-17
                16:5x), and v27's Creamy flew under that cursor and was attacked."""
                if prm.get("ptr_rest_two"):
                    agent.move(gx0 + round(REST_PX[0]) + 12, gy0 + round(REST_PX[1]) + 12)
                    time.sleep(0.06)
                agent.move(gx0 + round(REST_PX[0]), gy0 + round(REST_PX[1]))
                ptr[0] = REST_PX

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
                    sw_ = sword_on(k, "walk")
                    if sw_:  # v37: no walk click where the client draws the SWORD
                        vd_ = sword_verdict(u, v, "walk")
                        if vd_ != "clear":
                            ev({"kind": "walk_click", "gate": gate, "to": list(to),
                                "clicked": False, "why": f"cursor_{vd_}"})  # fmt: skip
                            return False
                        t_c = r.ns()
                    agent.click(gx0 + round(u), gy0 + round(v))
                ptr[0] = (u, v)
                if prm.get("ptr_rest_ui"):  # v26: the pointer never rests on the world
                    rest_ptr()
                sw_log = {"sw": sword_on(k, "walk")} if sword_refs is not None else {}
                click_log({"t": t_c, "u": round(u, 1), "v": round(v, 1), "kind": "walk",
                           "gate": gate, "to": list(to), "why": why, **sw_log,
                           **(extra or {})})  # fmt: skip
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

                extra_: list[Any] = []
                if prm.get("loot_race"):
                    # v33: the arm per loot step; the looter's own step carries our cells
                    if (
                        looter_pend.get("tid") == int(eng_["track"])
                        and time.monotonic() - looter_pend["t"] <= prm["looter_pending_s"]
                    ):
                        eng_["loot_arm"] = "race_chain"
                        eng_["looter_of"] = looter_pend["k"]
                        extra_ = list(looter_pend["cells"])
                    else:
                        if looter_pend:
                            ev({"kind": "looter_pending_dropped", **looter_pend})
                        race_n = not prm.get("loot_race_ab") or loot_n[0] % 2 == 1
                        eng_["loot_arm"] = "race" if race_n else "plain"
                        loot_n[0] += 1
                    looter_pend.clear()
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
                    if prm.get("loot_fixed"):
                        # v23 attempt 2: Batt's rule is EVERY confirmed kill, at the target's
                        # last tracked cell -- death_of's cell when it has one, else the
                        # track's last cell (attempt 1: death_of's gate looted 5 of 11 kills)
                        dc_ = dead_.cell
                        ls_ = last_strike.get(int(eng_["track"]))
                        corpse_: tuple[float, float, tuple[float, float], int] | None = None
                        if prm.get("loot_refix"):  # v33: the death cell from a fresh anchor too
                            rf_ = refix_now()
                            eng_["death"]["refix"] = rf_
                            if rf_ == "jump":
                                return  # no loot: the main loop's jump guard decides
                        if prm.get("loot_death") == "anim" and tr_.boxes:
                            # v31 (Batt 18:3x, decision 1): where the target WAS when our hit
                            # landed -- its own LAST box (the hit / the death animation; every kill
                            # is one hit at STR 99), turned into a cell with OUR measured position
                            # at THAT frame (offline vs packets: 86-90 % of drops in its 3 x 3, the
                            # last strike click 54 %)
                            bt_, bb_ = tr_.boxes[-1]
                            mp_a = pos_at_frame(int(bt_)) or measured_pos()
                            if mp_a is not None:
                                g_a = (int(round(mp_a[0])), int(round(mp_a[1])))
                                w_a = w5.World(camera, gat, g_a)
                                dc_ = nearest_cell_frac(w_a, mp_a, g_a,
                                                   (bb_.x0 + bb_.x1) / 2,
                                                   bb_.y1 - loot1.FOOT_LIFT)  # fmt: skip
                                eng_["death"]["fixed_from"] = "anim"
                                eng_["death"]["box_age_s"] = round((r.ns() - int(bt_)) / 1e9, 2)
                                corpse_ = ((bb_.x0 + bb_.x1) / 2, (bb_.y0 + bb_.y1) / 2,
                                           (float(mp_a[0]), float(mp_a[1])), int(bt_))  # fmt: skip
                        elif prm.get("loot_death") == "hybrid" and ls_ is not None:
                            # v24: the cell under the LAST strike click (found in the frame the
                            # click was aimed in), then the hybrid rule against where we stand now
                            mp_c = pos_at_frame(ls_[0]) or measured_pos()
                            mp_n = measured_pos()
                            if mp_c is not None and mp_n is not None:
                                w_c = w5.World(camera, gat, here2)
                                o_c = (int(round(mp_c[0])), int(round(mp_c[1])))
                                ck_ = nearest_cell_frac(w_c, mp_c, o_c,
                                                   ls_[1] + LOOT_FOOT_PX[0],
                                                   ls_[2] + LOOT_FOOT_PX[1])  # fmt: skip
                                g_n = (int(round(mp_n[0])), int(round(mp_n[1])))
                                dc_ = death_cell_hybrid(ck_, g_n)
                                eng_["death"]["fixed_from"] = (
                                    "click" if dc_ == ck_ else "adjacent")  # fmt: skip
                                eng_["death"]["click_cell"] = list(ck_)
                                eng_["death"]["gm_cell"] = list(g_n)
                        if dc_ is None and tr_.seen:
                            c_t = tr_.seen[-1][1]
                            dc_ = (int(round(c_t[0])), int(round(c_t[1])))
                            eng_["death"]["fixed_from"] = "track"
                        if dc_ is not None:
                            dead_cells_.append((time.monotonic(), dc_))  # v27: not a ghost
                            del dead_cells_[:-40]
                            loot_fixed_run(eng_, here2, dc_, extra_, corpse_)
                    elif dead_.cell is not None and dead_.gone_ns is not None:
                        if prm.get("loot_blobs"):
                            loot_blobs_run(eng_, here2, dead_.cell, tr_)
                        elif prm.get("loot_sweep"):
                            loot_sweep(eng_, here2, dead_.cell)
                        else:
                            loot1.loot(rig, here2, dead_, eng_)
                finally:
                    split.to(prev_, time.monotonic())

            def loot_fixed_run(eng_: dict[str, Any], here2: Cell, dcell: Cell,
                               extra: Sequence[Any] = (),
                               corpse: tuple[float, float, tuple[float, float], int] | None = None,
                               ) -> None:  # fmt: skip
                """v23 (Batt 2026-10-17): his looting as a FIXED workflow after every kill -- no
                item detection, no cursor read: burst-click the death cell, then click through
                the 3 x 3 (loot_plan), each click re-projected from where the GM is now (each one
                steps the GM or picks an item up). SAFETY only: a click is skipped near any
                monster box, within 2 cells of an NPC, on NEW pink pixels (a Creamy; the corpse
                was there before), on the UI or off the frame. Then hunting resumes at once.
                v33 (LOOT IS A RACE, the "race" arms): the matcher's floor items first, each at
                its own pixel (items_first), and a confident target standing within looter_cells
                of the death cell STOPS the step (eng_["loot"]["looter"]: the main loop kills it
                and its own step covers the cells still unclicked, ``extra``)."""
                t_l0 = time.monotonic()
                out: dict[str, Any] = {"cell": list(dcell), "clicks": 0, "skipped": {}}
                race_ = eng_.get("loot_arm") in ("race", "race_chain")
                if eng_.get("loot_arm"):
                    out["arm"] = eng_["loot_arm"]
                w_l = w5.World(camera, gat, here2)
                with plock:
                    ring_ = list(ring_frames)
                old_ = [f for f in ring_ if f[0] <= t_l0 - prm["loot_before_s"]]
                before_ = old_[-1][1] if old_ else None
                mp_b = pos_at_frame(int(old_[-1][0] * 1e9)) if old_ else None
                npc_c = [(int(n_["x"]), int(n_["y"])) for n_ in npcs]
                plan_l = loot_union_plan(dcell, extra, prm["loot_center_clicks"],
                                         prm["loot_ring_clicks"])  # fmt: skip
                icons_l: list[tuple[Cell, tuple[float, float]]] = []

                def pos_l() -> tuple[float, float] | None:
                    """Our position for a loot click, re-anchored first (v33, ``refix_now``);
                    None = a jump."""
                    if prm.get("loot_refix"):
                        st_ = refix_now()
                        if st_ == "jump":
                            return None
                        if st_ == "refix":
                            out["refix"] = out.get("refix", 0) + 1
                    return measured_pos() or (float(here2[0]), float(here2[1]))

                mp_g0 = pos_l()  # the item pixels' reference: the SAME estimator as each click
                mp_g = mp_g0 or (float(here2[0]), float(here2[1]))
                if mp_g0 is None:
                    out["stop"] = "jump"
                if race_ and icon_templates and mp_g0 is not None:
                    # v33: ONE fresh grab around the death cell, the matcher on it (~60 ms);
                    # only our own drawn pointer is excluded (the evaluated configuration)
                    import item_icons as ii_

                    ud_, vd_ = frac_project(w_l, mp_g, dcell)
                    r_i = int(prm["icon_radius"]) + 24
                    x0_, y0_ = max(0, int(ud_) - r_i), max(0, int(vd_) - r_i)
                    x1_, y1_ = min(gw, int(ud_) + r_i + 1), min(gh, int(vd_) + r_i + 1)
                    if x1_ - x0_ >= 48 and y1_ - y0_ >= 48:
                        img_i = screen.grab(gx0 + x0_, gy0 + y0_, x1_ - x0_, y1_ - y0_)[1]
                        img_i = np.ascontiguousarray(img_i[..., :3])
                        pu_, pv_ = ptr[0]
                        found_ = ii_.find_items(
                            img_i, (ud_ - x0_, vd_ - y0_), int(prm["icon_radius"]),
                            icon_templates, order="BGR",
                            exclude=[(pu_ - 26 - x0_, pv_ - 26 - y0_,
                                      pu_ + 40 - x0_, pv_ + 40 - y0_)],
                        )  # fmt: skip
                        for iu_, iv_, _id, _sc in found_:
                            pi_ = (float(iu_) + x0_, float(iv_) + y0_)
                            ci_ = nearest_cell_frac(w_l, mp_g, dcell,
                                               pi_[0], pi_[1], radius=4)  # fmt: skip
                            icons_l.append((ci_, pi_))
                    out["icons"] = len(icons_l)
                    out["icon_ms"] = round((time.monotonic() - t_l0) * 1e3)
                steps_: list[Any] = (items_first(plan_l, icons_l) if mp_g0 is not None
                                     else [])  # fmt: skip
                # v36 (the LOOT RETRY): a cell skipped for a unit near is queued ONCE more at the
                # end of the step, not before loot_retry_wait_s (the dying sprite fades, a
                # passer-by walks on); the same checks decide it again. Odd kills, A/B.
                retry_on = bool(prm.get("loot_retry")) and (
                    not prm.get("loot_retry_ab") or int(eng_.get("k", 0)) % 2 == 1
                )
                if prm.get("loot_retry"):
                    out["retry_arm"] = retry_on
                for i_s, st_ in enumerate(steps_):  # v36: grows by the retries it queues
                    c_l, (jx_, jy_), px_ = st_[0], st_[1], st_[2]
                    nb_ = st_[3] if len(st_) > 3 else None  # a retry's not-before time
                    if nb_ is not None:
                        if max(time.monotonic(), nb_) - t_l0 >= prm["loot_fixed_max_s"]:
                            break
                        if nb_ > time.monotonic():
                            time.sleep(nb_ - time.monotonic())
                    if time.monotonic() - t_l0 >= prm["loot_fixed_max_s"]:
                        break
                    why_ = None
                    if any(cheb(c_l, nc_) <= 2 for nc_ in npc_c):
                        why_ = "npc"
                    else:
                        mp_n = pos_l()
                        if mp_n is None:
                            out["stop"] = "jump"  # the main loop's guard decides
                            break
                        mp_ = mp_n
                        if px_ is not None:  # v33: the item's own pixel, moved with the ground
                            a_i = frac_project(w_l, mp_g, c_l)
                            b_i = frac_project(w_l, mp_, c_l)
                            u_l, v_l = px_[0] + b_i[0] - a_i[0], px_[1] + b_i[1] - a_i[1]
                        else:
                            u_l, v_l = frac_project(w_l, mp_, c_l)
                            u_l, v_l = u_l + jx_, v_l + jy_
                        if not in_view(u_l, v_l):
                            why_ = "view"
                        else:
                            fr_l = sampler.since(max(0, len(sampler.frames) - 1))
                            mu_ = float(prm.get("loot_unit_px", 30.0))  # v25: 70 (see PARAMS)
                            near_ = [x_ for x_ in (fr_l[-1][1] if fr_l else [])
                                     if x_.cls in ("monster", "npc")  # not the GM's box
                                     and x_.x0 - mu_ <= u_l <= x_.x1 + mu_
                                     and x_.y0 - mu_ <= v_l <= x_.y1 + mu_]  # fmt: skip
                            if (near_ and corpse is not None and prm.get("loot_corpse")
                                    and (fr_l[-1][0] - corpse[3]) / 1e9
                                    <= prm["loot_corpse_s"]):  # fmt: skip
                                # v34 base (2026-10-18 00:3x): the TARGET'S OWN dying sprite is
                                # not a unit -- a box on its last box (moved with the camera)
                                # within loot_corpse_s of that box. v32: a loot starting at
                                # 1.23 s skipped 4.0 clicks a step, at 2.5 s 2.48 (v33 att 2,
                                # 0.63 s: 3.8). Every kill is one hit at STR 99
                                sh0_ = frac_project(w_l, corpse[2], dcell)
                                sh1_ = frac_project(w_l, mp_, dcell)
                                cu_ = corpse[0] + sh1_[0] - sh0_[0]
                                cv_ = corpse[1] + sh1_[1] - sh0_[1]
                                keep_ = [x_ for x_ in near_ if math.hypot(
                                    (x_.x0 + x_.x1) / 2 - cu_, (x_.y0 + x_.y1) / 2 - cv_)
                                    > prm["loot_corpse_px"] or x_.cls != "monster"]  # fmt: skip
                                if len(keep_) < len(near_):
                                    out["corpse"] = out.get("corpse", 0) + 1
                                near_ = keep_
                            blk_ = near_[0] if near_ else None
                            if blk_ is not None:
                                why_ = "unit"
                                if (race_ and prm.get("looter_chain")
                                        and not eng_.get("looter_of") and blk_.cls == "monster"
                                        and species_model is not None):  # fmt: skip
                                    # v33: a looter ON our pile -> kill it first (Batt)
                                    ub_ = (blk_.x0 + blk_.x1) / 2
                                    vb_ = blk_.y1 - loot1.FOOT_LIFT
                                    cb_ = nearest_cell_frac(w_l, mp_,
                                                       dcell, ub_, vb_, radius=4)  # fmt: skip
                                    if cheb(cb_, dcell) <= prm["looter_cells"]:
                                        sp_l, cf_l, cr_l = species_now(blk_)
                                        if sp_l in nametag.TARGET_NAMES and not cr_l:
                                            pend_: list[list[int]] = []
                                            for st2_ in steps_[i_s:]:
                                                c2_ = st2_[0]
                                                if list(c2_) not in pend_:
                                                    pend_.append([int(c2_[0]), int(c2_[1])])
                                            out["looter"] = {
                                                "u": round(ub_, 1), "v": round(vb_, 1),
                                                "cell": list(cb_), "species": sp_l,
                                                "conf": round(cf_l, 3), "pending": pend_,
                                            }  # fmt: skip
                                            break
                                        out["looter_unsure"] = out.get("looter_unsure", 0) + 1
                            else:
                                dx_, dy_ = 0, 0
                                if mp_b is not None:  # the ground's move since BEFORE
                                    p1_ = frac_project(w_l, mp_, c_l)
                                    p0_ = frac_project(w_l, mp_b, c_l)
                                    dx_ = int(round(p1_[0] - p0_[0]))
                                    dy_ = int(round(p1_[1] - p0_[1]))
                                # attempt 2: a FRESH crop around the click point only (attempt
                                # 1 grabbed the whole frame per click: ~0.7 s a click)
                                r_p = int(prm["loot_pink_r"])
                                x0_, y0_ = max(0, int(u_l) - r_p), max(0, int(v_l) - r_p)
                                x1_ = min(gw, int(u_l) + r_p + 1)
                                y1_ = min(gh, int(v_l) + r_p + 1)
                                crop_ = screen.grab(gx0 + x0_, gy0 + y0_, x1_ - x0_, y1_ - y0_)[1]
                                crop_ = np.ascontiguousarray(crop_[..., :3])
                                bcrop_ = None
                                if before_ is not None:
                                    hh_, ww_ = crop_.shape[:2]
                                    bcrop_ = shifted_crop(before_, x0_ - dx_, y0_ - dy_, ww_, hh_)
                                ex_ = None
                                if prm.get("loot_pink_gm_exclude"):
                                    ge_ = GUARD_EXCLUDE
                                    ex_ = (ge_[0] - x0_, ge_[1] - y0_, ge_[2] - x0_, ge_[3] - y0_)
                                n_pk = new_pink_px(crop_, bcrop_, u_l - x0_, v_l - y0_, r_p,
                                                   exclude=ex_)  # fmt: skip
                                if n_pk > prm["loot_pink_max_px"]:
                                    why_ = "pink"
                    if why_ is not None:
                        if nb_ is not None:  # v36: a retry skipped again (counted apart)
                            rs_ = out.setdefault("retry_skipped", {})
                            rs_[why_] = rs_.get(why_, 0) + 1
                            continue
                        out["skipped"][why_] = out["skipped"].get(why_, 0) + 1
                        rt_ = loot_retry_of(st_, why_, retry_on, time.monotonic(),
                                            float(prm.get("loot_retry_wait_s", 0.6)))  # fmt: skip
                        if rt_ is not None:
                            steps_.append(rt_)
                            out["retry_queued"] = out.get("retry_queued", 0) + 1
                        continue
                    sw_l = sword_on(int(eng_.get("k", 0)), "loot")
                    if sw_l:  # v37: no loot click where the client draws the SWORD
                        vd_l = sword_verdict(u_l, v_l, "loot")
                        if vd_l != "clear":
                            out["skipped"][f"cursor_{vd_l}"] = (
                                out["skipped"].get(f"cursor_{vd_l}", 0) + 1)  # fmt: skip
                            continue
                    t_lc = r.ns()
                    agent.click(gx0 + round(u_l), gy0 + round(v_l))  # the LOOT click (fixed)
                    ptr[0] = (u_l, v_l)
                    out["clicks"] += 1
                    if nb_ is not None:
                        out["retry_clicks"] = out.get("retry_clicks", 0) + 1
                    click_log({"t": t_lc, "u": round(u_l, 1), "v": round(v_l, 1),
                               "kind": "loot", "cell": list(c_l),
                               "src": "icon" if px_ is not None else "fixed",
                               **({"retry": True} if nb_ is not None else {}),
                               **({"sw": sw_l} if sword_refs is not None else {})})  # fmt: skip
                    time.sleep(prm["loot_interval_s"])
                if prm.get("ptr_rest_ui") and out["clicks"]:  # v26: off the world after the step
                    rest_ptr()
                out["s"] = round(time.monotonic() - t_l0, 2)
                out["death"] = eng_.get("death")
                eng_["loot"] = out
                ev({"kind": "loot_fixed", **out})

            def loot_blobs_run(eng_: dict[str, Any], here2: Cell, dcell: Cell, tr_: Any) -> None:
                """v21 (Batt 2026-10-17, LOOT by frame difference): the drops as NEW small blobs
                around the death spot -- BEFORE from the frame ring ~loot_before_s before this
                'dead' (v15: 'dead' comes ~0.8 s after the death is drawn), AFTER now, LATER
                +0.4 s (drop_blobs, offline recall@20 ~0.5, ~0.65 false blobs a kill: every blob
                is only a hover candidate). Each blob becomes a floor cell (+ its sub-cell pixel
                residual), re-projected from where the GM is now (it walks onto each item), and is
                clicked only on the HAND read twice + walk@11's unit check, as v17's sweep. The
                v17 sweep only when no blob got a click; bounded by loot_max_s / loot_max_clicks
                as v17."""
                import drop_blobs as db_

                t_l0 = time.monotonic()
                out: dict[str, Any] = {"cell": list(dcell), "blobs": 0, "clicks": 0, "picked": 0,
                                       "no_hand": 0}  # fmt: skip
                w_l = w5.World(camera, gat, here2)
                fr_l = sampler.since(max(0, len(sampler.frames) - 1))
                risky_l = [x for x, c in (sightings_in(fr_l[-1][1], here2) if fr_l else [])
                           if cheb(c, dcell) <= 1.5]  # fmt: skip
                if risky_l:
                    out["skip"] = "monster_in_area"  # the risk rule: a click could attack it
                    eng_["loot"] = out
                    ev({"kind": "loot", **out})
                    return
                with plock:
                    ring_ = list(ring_frames)
                old_ = [f for f in ring_ if f[0] <= t_l0 - prm["loot_before_s"]]
                blobs: list[Any] = []
                if old_ and tr_.box is not None:
                    before_ = old_[-1][1]
                    after_ = np.ascontiguousarray(np.asarray(frame())[..., :3])
                    time.sleep(0.4)
                    later_ = np.ascontiguousarray(np.asarray(frame())[..., :3])
                    pu_, pv_ = ptr[0]  # our own drawn cursor is not a drop
                    ys_ = slice(max(0, int(pv_) - 26), max(0, int(pv_) + 40))
                    xs_ = slice(max(0, int(pu_) - 26), max(0, int(pu_) + 40))
                    after_[ys_, xs_] = before_[ys_, xs_]
                    later_[ys_, xs_] = before_[ys_, xs_]
                    blobs = db_.drop_blobs(before_, after_, f1.centre(tr_.box), later=later_)
                    out["before_age_s"] = round(t_l0 - old_[-1][0], 2)
                else:
                    out["no_before"] = True
                out["blobs"] = len(blobs)
                points: list[tuple[float, float, str]] = []
                cen_ = f1.centre(tr_.box) if tr_.box is not None else GM_SPRITE_PX
                if icon_templates:
                    # v23: the item SPRITES first (few false matches); then only the blobs off
                    # the GM's own animated sprite (v21: 48 of 82 blob hovers read walk there)
                    import item_icons as ii_

                    img_i = np.ascontiguousarray(np.asarray(frame())[..., :3])
                    pu_, pv_ = ptr[0]
                    icons_ = ii_.find_items(img_i, cen_, prm["icon_radius"], icon_templates,
                                            order="BGR",
                                            exclude=[(pu_ - 26, pv_ - 26, pu_ + 40,
                                                      pv_ + 40)])  # fmt: skip
                    out["icons"] = len(icons_)
                    points += [(float(iu), float(iv), "icon") for iu, iv, _id, _sc in icons_]
                    blobs = [bl for bl in blobs
                             if math.hypot(bl.u - GM_SPRITE_PX[0], bl.v - GM_SPRITE_PX[1])
                             > prm["blob_gm_px"]
                             and all(math.hypot(bl.u - pu2_, bl.v - pv2_) > 15
                                     for pu2_, pv2_, _s in points)]  # fmt: skip
                points += [(bl.u, bl.v, "blob") for bl in blobs]
                # each blob keeps ITS OWN pixel, moved only by how far the GM moved since AFTER
                # (attempt 1 re-projected from the fractional position against a residual taken
                # on the integer cell: hovers up to ~30 px off, 26 of 43 read no hand)
                mp0_ = measured_pos() or (float(here2[0]), float(here2[1]))
                targets: list[tuple[Cell, tuple[float, float], str]] = []
                for pu3_, pv3_, src_ in points:
                    off_ = picking.pick_cells(camera, gat, here2, np.array([[pu3_, pv3_]]))[0]
                    if abs(int(off_[0])) > 1000:
                        continue
                    c_b = (here2[0] + int(off_[0]), here2[1] + int(off_[1]))
                    targets.append((c_b, (pu3_, pv3_), src_))
                if not icon_templates:  # v21: nearest the GM first
                    targets.sort(key=lambda t_: math.hypot(t_[1][0] - GM_SPRITE_PX[0],
                                                           t_[1][1] - GM_SPRITE_PX[1]))  # fmt: skip
                for c_b, px_, src_ in targets:
                    if (time.monotonic() - t_l0 >= prm["loot_max_s"]
                            or out["clicks"] >= prm["loot_max_clicks"]):  # fmt: skip
                        break
                    mp_ = measured_pos() or mp0_
                    a_ = frac_project(w_l, mp0_, c_b)
                    b_ = frac_project(w_l, mp_, c_b)
                    u_l, v_l = px_[0] + b_[0] - a_[0], px_[1] + b_[1] - a_[1]
                    if loot1.in_ui(u_l, v_l) or not in_view(u_l, v_l):
                        continue
                    if not pr.park():
                        out["end"] = "stale_park"
                        break
                    pr.hover(u_l, v_l)
                    sh1_ = pr.read(u_l, v_l)["shape"]
                    sh2_ = pr.read(u_l, v_l)["shape"] if sh1_ == "pickup" else None
                    out.setdefault("tried", []).append([round(u_l), round(v_l), sh1_, src_])
                    if sh1_ != "pickup" or sh2_ != "pickup":
                        out["no_hand"] += 1
                        continue
                    w_l.position = (int(round(mp_[0])), int(round(mp_[1])))
                    ok_u, _env = w11.unit_check(pr, w_l, u_l, v_l)
                    if not ok_u:
                        continue
                    before_l = loot1.frame_bgr(rig)
                    before_w = loot1.weight_now(rig)
                    t_lc = r.ns()
                    agent.click(gx0 + round(u_l), gy0 + round(v_l))  # the LOOT click (a blob)
                    out["clicks"] += 1
                    trial_l: dict[str, Any] = {}
                    loot1.check(rig, before_l, before_w, t_lc, trial_l)
                    if (trial_l.get("runtime") or {}).get("obtained"):
                        out["picked"] += 1
                    click_log({"t": t_lc, "u": round(u_l, 1), "v": round(v_l, 1),
                               "kind": "loot", "cell": list(c_b), "src": src_})  # fmt: skip
                out["s"] = round(time.monotonic() - t_l0, 2)
                eng_["loot"] = out
                ev({"kind": "loot_blobs", **out})
                if out["clicks"] == 0 and time.monotonic() - t_l0 < prm["loot_max_s"]:
                    loot_sweep(eng_, here2, dcell)  # the short sweep as the fallback

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
            # v14: track -> (its tag, when, the client px it was read at)
            confirmed: dict[int, tuple[str, float, tuple[float, float]]] = {}
            if prm.get("name_tag") and not tag_templates:
                raise f0.FarmStop("hunt-flow refused: no name-tag templates (nametag.py build)")

            def read_tag(u: float, v: float, b: Any, tid: int | None = None
                         ) -> tuple[str | None, int, tuple[float, float]]:  # fmt: skip
                """v12: rest the pointer on (u, v) and read the name tag under ``b`` until one
                matches (<= tag_wait_s); the pointer is left on the target for the click. v20
                (tag_follow): the pointer follows the focused target, the tag is also searched
                under the pointer, and the returned point is where the pointer ended."""
                t_a = time.monotonic()
                agent.move(gx0 + max(0, round(u) - 12), gy0 + max(0, round(v) - 12))  # 2 motions
                time.sleep(0.06)
                agent.move(gx0 + round(u), gy0 + round(v))
                ptr[0] = (u, v)
                name_: str | None = None
                follow_ = bool(prm.get("tag_follow") and tid is not None)
                while time.monotonic() - t_a < prm["tag_wait_s"]:
                    time.sleep(0.1)
                    if follow_ and tid is not None:
                        fa_ = focus.aim(tid, r.ns(), 0.0, prm["focus_max_age_s"])
                        if (fa_ is not None and in_view(fa_[0], fa_[1])
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
                            ub_ = ua + fa_b[0] - (b_b.x0 + b_b.x1) / 2
                            vb_ = va + fa_b[1] - (b_b.y0 + b_b.y1) / 2
                            if in_view(ub_, vb_):  # v16 run 1: a lead off the top edge (y < 0)
                                ua, va = ub_, vb_
                                out["focus"] = out.get("focus", 0) + 1
                    if not in_view(ua, va):
                        out["end"] = "off_view"
                        break
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

            def species_now(b: Any) -> tuple[str | None, float, bool]:
                """v24/v25: the pixel species check on a FRESH crop around box ``b`` -> (species
                or None when unsure, confidence, crowded = another monster box within 50 px).
                v35 (species_own): ``b`` is ~0.6 s old and the fresh crop at its coordinates
                missed the walking / scrolled sprite -> classify it on ITS OWN frame (the
                sampler's), and only when ``recentre`` finds it again in the fresh grab (NCC >=
                RECENTRE_MIN, within RECENTRE_WIDE px); its frame no longer held: the old way."""
                import species_check as sc_

                # v35: interleaved per engagement (odd k, the engagement about to start: own frame)
                own_on = bool(prm.get("species_own")) and (
                    not prm.get("species_own_ab") or k % 2 == 1)  # fmt: skip
                own_ = sampler.frame_of(b) if own_on else None
                r_s = sc_.RECENTRE_WIDE if own_ is not None else 40
                sx0_, sy0_ = max(0, int(b.x0) - r_s), max(0, int(b.y0) - r_s)
                sx1_, sy1_ = min(gw, int(b.x1) + r_s + 1), min(gh, int(b.y1) + r_s + 1)
                img_s = screen.grab(gx0 + sx0_, gy0 + sy0_, sx1_ - sx0_, sy1_ - sy0_)[1]
                bx_ = (b.x0, b.y0, b.x1, b.y1, b.score)
                if own_ is not None:
                    _bn, s_ = sc_.recentre(own_[1], bx_, img_s, order="bgr",
                                           cur_origin=(sx0_, sy0_), max_shift=r_s,
                                           coarse=sc_.RECENTRE_COARSE)  # fmt: skip
                    sp_, cf_ = (sc_.species_of(own_[1], species_model, bx_, order="bgr")
                                if s_ >= sc_.RECENTRE_MIN else (None, 0.0))  # fmt: skip
                else:
                    sp_, cf_ = sc_.species_of(img_s, species_model,
                                              (b.x0 - sx0_, b.y0 - sy0_, b.x1 - sx0_,
                                               b.y1 - sy0_, b.score), order="bgr")  # fmt: skip
                fr_s = sampler.since(max(0, len(sampler.frames) - 1))
                cb_ = np.array(f1.centre(b))
                crowd_ = any(
                    o.cls == "monster" and 8 < math.hypot(*(np.array(f1.centre(o)) - cb_)) < 50
                    for o in (fr_s[-1][1] if fr_s else []))  # fmt: skip
                return sp_, float(cf_), bool(crowd_)

            def abc_ineligible(tr: Track, b: Any, u: float, v: float) -> str | None:
                """v29: why B / C may NOT skip the confirmation for this target (None = they may):
                the species must be a confident target (the pixel check sure and uncrowded, or
                the track's tag within the cache rule), and no pink other than the target's own
                sprite within 60 px of the click (a Creamy, or another Poring: A then). The risk
                gate (non-target species, NPCs, overlap, near the GM) already chose the direct
                path."""
                c_ = confirmed.get(tr.tid)
                cache_ok = bool(c_ and time.monotonic() - c_[1] <= prm["tag_cache_s"]
                                and math.hypot(u - c_[2][0], v - c_[2][1])
                                <= prm.get("tag_cache_px", 1e9))  # fmt: skip
                if not cache_ok:
                    if species_model is None or b is None:
                        return "no_species_check"
                    sp_, _cf, cr_ = species_now(b)
                    if sp_ not in nametag.TARGET_NAMES:
                        return "species_unsure"
                    if cr_:
                        return "crowded"
                r_p = 60
                x0_, y0_ = max(0, int(u) - r_p), max(0, int(v) - r_p)
                x1_, y1_ = min(gw, int(u) + r_p + 1), min(gh, int(v) + r_p + 1)
                crop_ = np.array(
                    screen.grab(gx0 + x0_, gy0 + y0_, x1_ - x0_, y1_ - y0_)[1][..., :3]
                )
                gx_a, gy_a, gx_b, gy_b = GUARD_EXCLUDE  # the GM's sprite
                crop_[max(0, int(gy_a) - y0_) : max(0, int(gy_b) - y0_),
                      max(0, int(gx_a) - x0_) : max(0, int(gx_b) - x0_)] = 0  # fmt: skip
                ex_ = None if b is None else (b.x0 - 8 - x0_, b.y0 - 8 - y0_, b.x1 + 8 - x0_,
                                              b.y1 + 8 - y0_)  # fmt: skip
                if new_pink_px(crop_, None, u - x0_, v - y0_, r_p, exclude=ex_) > 30:
                    return "pink_near"
                return None

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
                    if fa_ is not None and in_view(fa_[0], fa_[1]):
                        # v16: the target tracked on every frame, led by its velocity
                        # (in the frame: run 1 stopped on a lead above the top edge, y < 0)
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

                def tag_gate(u_: float, v_: float, no_skip: bool = False
                             ) -> tuple[bool, str | None, float, float]:  # fmt: skip
                    """v14: the client's own species label must read a TARGET before an attack
                    click (the size gate let a Creamy, a non-target, pass as a Poring). v15: a
                    track's tag read <= tag_cache_s ago is reused; from v16 attempt 3 only near
                    the point it was read at (tag_cache_px: a track can take over another
                    sprite's box)."""
                    nonlocal reads
                    c_ = confirmed.get(tr.tid)
                    if (prm.get("tag_cache_s") and c_
                            and time.monotonic() - c_[1] <= prm["tag_cache_s"]
                            and math.hypot(u_ - c_[2][0], v_ - c_[2][1])
                            <= prm.get("tag_cache_px", 1e9)):  # fmt: skip
                        return True, c_[0], u_, v_
                    sp_ = cf_ = crowd_ = None
                    if species_model is not None and b is not None:
                        sp_, cf_, crowd_ = species_now(b)
                        if (prm.get("species_skip") and not no_skip
                                and sp_ in nametag.TARGET_NAMES and not crowd_):  # fmt: skip
                            # v25 (Batt's item 3): the pixel check is sure of a TARGET and no
                            # other monster box is within 50 px -> no tag read (v23's shadow:
                            # 37 of 38 agreed; the one miss was crowded)
                            confirmed[tr.tid] = (sp_, time.monotonic(), (u_, v_))
                            ev({"kind": "species_skip", "track": tr.tid, "species": sp_,
                                "conf": round(float(cf_ or 0.0), 4)})  # fmt: skip
                            return True, sp_, u_, v_
                    t_, ms_, (u_, v_) = read_tag(u_, v_, b, tr.tid)
                    if species_model is not None and b is not None:
                        ev({"kind": "species_shadow", "track": tr.tid, "tag": t_,
                            "species": sp_, "conf": round(float(cf_ or 0.0), 4),
                            "crowded": bool(crowd_)})  # fmt: skip
                    if t_ in nametag.TARGET_NAMES:
                        confirmed[tr.tid] = (t_, time.monotonic(), (u_, v_))
                        return True, t_, u_, v_
                    reads += 1 if t_ is None else prm["max_reads"]
                    ev({"kind": "tag_refused", "track": tr.tid, "tag": t_, "ms": ms_,
                        "branch": "direct" if direct_ else "read"})  # fmt: skip
                    note(f"tag {t_}: no click")
                    return False, t_, u_, v_

                # v29 (Batt 2026-10-17 17:3x): the INTERLEAVED A / B / C test, per engagement
                # (k % 3), so spawns, map area and time are matched. A = the pointer on the
                # target, the client's confirmation (the name tag; the tag cache counts), then the
                # click. B = click at once and burst until the lock arrow. C = B after a second
                # small motion (the client draws -- and resolves -- its cursor only where a second
                # motion leaves it). B / C only for a confident target with no risk near: else A.
                arm_: str | None = None
                arm_why: str | None = None
                t_arrive = r.ns()
                if prm.get("abc") and direct_ and prm.get("name_tag") and not again and (
                        eng is None or eng["track"] != tr.tid):  # fmt: skip
                    arm_ = prm.get("abc_arm") or "ABC"[k % 3]  # v32: C (Batt), A the fallback
                    if arm_ != "A":
                        arm_why = abc_ineligible(tr, b, u, v)
                hov_arm = {"arm": arm_, "arm_eff": "A" if arm_why else arm_,
                           "fallback": arm_why}  # fmt: skip
                if direct_ and prm.get("name_tag"):
                    if arm_ in ("B", "C") and arm_why is None:
                        tag_ = f"skip:{arm_}"
                        t_arrive = r.ns()
                        if arm_ == "C":  # the nudge: a second small motion onto the target
                            agent.move(gx0 + round(u) + 2, gy0 + round(v) + 1)
                            time.sleep(0.03)
                    else:
                        t_arrive = r.ns()
                        ok_t, tag_, u, v = tag_gate(u, v, no_skip=arm_ is not None)
                        if not ok_t:
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
                if not direct_ and prm.get("name_tag") and prm.get("tag_every_click"):
                    # v16 attempt 1: the READ path (a risky context) clicked a Creamy -- the
                    # SWORD read says "a monster", not which. The tag, at the click point, now
                    ok_t, tag_, u, v = tag_gate(u, v)
                    if not ok_t:
                        split.to(prev, time.monotonic())
                        return False
                if not in_view(u, v):  # v16 run 1: never a click outside the game frame
                    ev({"kind": "strike_off_view", "track": tr.tid, "u": round(u, 1),
                        "v": round(v, 1)})  # fmt: skip
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
                if prm.get("abc") and hov_arm.get("arm"):
                    hov.update(hov_arm, t_arrive=t_arrive)  # v29: the arm + pointer arrival
                    ev({"kind": "abc", "track": tr.tid, "k": k, **hov_arm,
                        "arrive_to_click_ms": round((tc - t_arrive) / 1e6)})  # fmt: skip
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
                    off_ = fread.blink_point(u, v, cs2, in_view) or (
                        u,
                        v - 90.0 if v >= 90.0 else v + 90.0,
                    )
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
                    if result not in SKIPPED_SELECTABLE:  # v40/3.87: a skipped target stays
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
            swept_grid = np.full(area.shape, -1e9, dtype=np.float64)  # v22: last time in view
            # v38 candidate: the WHOLE run's memory of the cells our own screen showed (the camera
            # footprint at the measured position), for the age-weighted heading; v22's grid stays
            seen_grid = np.full(area.shape, -1e9, dtype=np.float64)
            offs_arr = np.asarray(offsets, dtype=int).reshape(-1, 2)
            head_blk: dict[str, Any] = {"t0": None, "block": None, "on": False}

            def age_on(now_s: float) -> bool:
                """v38: the age-weighted heading's arm -- 10-min blocks (odd seeds start on)."""
                if not prm.get("heading_age"):
                    return False
                if head_blk["t0"] is None:
                    head_blk["t0"] = now_s
                blk_ = int((now_s - head_blk["t0"]) / (60.0 * prm["heading_age_block_min"]))
                if blk_ != head_blk["block"]:
                    on_ = not prm.get("heading_age_ab") or (blk_ + seed) % 2 == 1
                    head_blk.update(block=blk_, on=on_)
                    ev({"kind": "heading_arm", "block": blk_, "on": on_})
                return bool(head_blk["on"])

            arrow_last: list[float | None] = [None]  # v18: the minimap arrow (deg), logged only
            heading_rng = random_.Random(seed)
            trail: list[tuple[float, Cell]] = []  # v8 attempt 2: (mono s, cell) we stood on

            # v27 (Batt's "Battleship"): the belief map, fed from the planner thread only
            bel_: Any = None
            bel_k = [0]  # the sampler frames already fed
            dead_cells_: list[tuple[float, Cell]] = []  # (mono s, death cell) of our kills
            looter_pend: dict[str, Any] = {}  # v33: the looter to kill + our unclicked cells
            loot_n = [0]  # v33: loot steps so far (the race arm on odd ones)
            bel_off: list[int] = []  # non-empty: the belief map failed once and is off
            bel_done: set[int] = set()  # v28: ghosts whose probe was reached
            offs_arr = np.array(offsets, dtype=int).reshape(-1, 2)
            if prm.get("belief"):
                import belief_map as bm_

                bel_ = bm_.BeliefMap(ok, bm_.Kernel.default(),
                                     [bm_.Variant("nl", pd=prm["belief_pd"],
                                                  lead=prm["belief_lead"])])  # fmt: skip
            w_bel = w5.World(camera, gat, start)

            def feed_belief() -> None:
                """v27: the detector's new frames -> the belief map: our sightings' fractional
                cells (sightings_in's gates: no Creamy, no floor item, no UI) and the cells in
                view as negative evidence, each at our measured position at that frame."""
                fr_b = sampler.since(bel_k[0])
                bel_k[0] += len(fr_b)
                h_g, w_g = ok.shape
                for t_f, boxes_f in fr_b[-10:]:
                    mp_f = pos_at_frame(int(t_f))
                    if mp_f is None:
                        continue
                    h_f = (int(round(mp_f[0])), int(round(mp_f[1])))
                    frac_f = (mp_f[0] - h_f[0], mp_f[1] - h_f[1])
                    dets_ = [(float(c_[0]), float(c_[1]))
                             for _b, c_ in sightings_in(boxes_f, h_f, w_bel, frac_f)]  # fmt: skip
                    vis_ = np.zeros(ok.shape, dtype=bool)
                    xs_, ys_ = offs_arr[:, 0] + h_f[0], offs_arr[:, 1] + h_f[1]
                    in_ = (xs_ >= 0) & (xs_ < w_g) & (ys_ >= 0) & (ys_ < h_g)
                    vis_[ys_[in_], xs_[in_]] = True
                    bel_.update(int(t_f), dets_, vis_)

            from collections import deque as deque_

            # the pocket escape (a bug fix with v42): our cell every 2 s and the mode, the
            # pockets left behind (centre, radius, until)
            stuck_st: dict[str, Any] = {"hist": deque_(), "zones": [], "mode": ""}

            def planner() -> None:
                """The queue (chained, standing first) every plan_every_s, and the next exploration
                waypoint (the coverage plan's stalest tile) always held."""
                while not halt.is_set():
                    now_, t_ = time.monotonic(), r.ns()
                    here_ = posm.at(now_)
                    if prm.get("stuck_window_s"):
                        sh_ = stuck_st["hist"]
                        if not sh_ or now_ - sh_[-1][0] >= 2.0:
                            sh_.append((now_, (int(here_[0]), int(here_[1])),
                                        stuck_st["mode"] == "search"))  # fmt: skip
                        while sh_ and now_ - sh_[0][0] > float(prm["stuck_window_s"]) + 4.0:
                            sh_.popleft()
                    if prm.get("heading_cov"):  # v22: the ground in our view now (+-cov_half)
                        hx_, hy_, hc_ = int(here_[0]), int(here_[1]), int(prm["cov_half"])
                        swept_grid[max(0, hy_ - hc_): hy_ + hc_ + 1,
                                   max(0, hx_ - hc_): hx_ + hc_ + 1] = now_  # fmt: skip
                    if prm.get("heading_age"):  # v38: the cells our screen shows now
                        fx_ = offs_arr[:, 0] + int(here_[0])
                        fy_ = offs_arr[:, 1] + int(here_[1])
                        in_ = ((fx_ >= 0) & (fx_ < area.shape[1]) & (fy_ >= 0)
                               & (fy_ < area.shape[0]))  # fmt: skip
                        seen_grid[fy_[in_], fx_[in_]] = now_
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
                    g_bel = None
                    if bel_ is not None and not bel_off:
                        try:
                            feed_belief()
                            if (prm.get("belief_probe_once") and plan.get("bel_goal")
                                    and cheb(here_, plan["bel_goal"][1]) <= 2):  # fmt: skip
                                # v28: the probe was reached -- that ghost is not chased again
                                # (v27 re-planned the same ghost every cycle at the probe)
                                bel_done.add(int(plan["bel_goal"][0]))
                                plan["bel_goal"] = None
                            g_bel = belief_ghost(bel_, t_, list(dead_cells_), now_, "nl",
                                                 tuple(prm["belief_unseen"]),
                                                 prm["belief_min_mass"],
                                                 skip=bel_done)  # fmt: skip
                        except Exception as exc_b:  # noqa: BLE001 -- never kill the planner
                            bel_off.append(1)
                            ev(
                                {
                                    "kind": "belief_error",
                                    "error": f"{type(exc_b).__name__}: {exc_b}",
                                }
                            )
                            g_bel = None
                    left_ = 999
                    if gp and prm.get("replan_left"):  # v5: never walk off the route's end
                        ci_ = min(range(len(gp)), key=lambda i_: cheb(gp[i_], here_))
                        left_ = len(gp) - 1 - ci_
                    stale_ = (not prm.get("sweep")  # v12: no time-based re-pick (hysteresis)
                              and now_ - plan["t_goal"] > prm["waypoint_every_s"])  # fmt: skip
                    new_ghost = g_bel is not None and plan.get("bel_tid") != g_bel["tid"]
                    if (gp is None or stale_ or new_ghost
                            or cheb(here_, gp[-1]) <= 2
                            or (left_ < prm.get("replan_left", -1)
                                and not (prm.get("sweep")
                                         and sweep_st.get("phase") == "shift"))):  # fmt: skip
                        p_ = None
                        goal = None
                        bel_p: list[Cell] | None = None
                        if g_bel is not None:
                            # v27: a HIDDEN monster's most probable cell first (the belief map:
                            # last seen 1-10 s ago, not ruled out by the cells we see empty)
                            hg_, wg_ = ok.shape
                            for pc_ in g_bel["probes"]:
                                inb_ = 0 <= pc_[0] < wg_ and 0 <= pc_[1] < hg_
                                if inb_ and ok[pc_[1], pc_[0]] and cheb(pc_, here_) >= 2:
                                    pb_ = hc.astar(ok, here_, pc_)
                                    if pb_ is not None and len(pb_) >= 2:
                                        bel_p, goal = pb_, pc_
                                        break
                            plan["bel_tid"] = g_bel["tid"]
                            if bel_p is not None and goal is not None:
                                plan["bel_goal"] = (g_bel["tid"], goal)
                                ev({"kind": "belief_goal", "track": g_bel["tid"],
                                    "probe": list(goal),
                                    "probes": [list(c_) for c_ in g_bel["probes"]],
                                    "mass": round(float(g_bel["mass"]), 3),
                                    "unseen_s": round(float(g_bel["unseen_s"]), 2),
                                    "last": [round(float(g_bel["last"][0]), 2),
                                             round(float(g_bel["last"][1]), 2)]})  # fmt: skip
                        if bel_p is not None:
                            p_ = bel_p
                        elif prm.get("heading_search") and area[here_[1], here_[0]]:
                            # v18 (Batt 21:31): along the remembered SEARCH HEADING; small turns;
                            # v22: away from the ground we swept in the last minutes
                            if age_on(now_):  # v38: the age-weighted score per walking second
                                goal = heading_goal_age(area, here_, heading_st, seen_grid, now_,
                                                        offsets, prm["cov_keep"],
                                                        min_run=prm["heading_min_run"])  # fmt: skip
                            elif prm.get("heading_cov"):
                                goal = heading_goal_cov(
                                    area,
                                    here_,
                                    heading_st,
                                    swept_grid,
                                    now_,
                                    prm["cov_recent_s"],
                                    prm["cov_half"],
                                    prm["cov_keep"],
                                    min_run=prm["heading_min_run"],
                                    hyst_s=float(prm.get("dead_end_hyst_s") or 0.0),
                                    no135=bool(prm.get("cov_135_only_blocked")),
                                )
                            else:
                                goal = heading_goal(area, here_, heading_st, heading_rng,
                                                    min_run=prm["heading_min_run"],
                                                    drift_p=prm["heading_drift_p"])  # fmt: skip
                            if goal is not None:
                                p_ = hc.astar(area, here_, goal)
                                if p_ is not None and len(p_) >= 2:
                                    ev({"kind": "heading_goal", "goal": list(goal),
                                        "ang": round(math.degrees(heading_st["ang"]) % 360, 1),
                                        "turn": heading_st.get("turn"),
                                        "fresh": heading_st.get("fresh"),
                                        "dead_end_escape": heading_st.get("dead_end_escape"),
                                        "arrow": arrow_last[0],
                                        **({"age": bool(head_blk["on"])}
                                           if prm.get("heading_age") else {})})  # fmt: skip
                                else:
                                    goal = None
                            if prm.get("stuck_window_s"):
                                # the POCKET escape (a bug fix with v42): stuck by displacement,
                                # or a heading goal inside a pocket left behind -> the nearest
                                # reachable cell well outside it, by the grid's real paths
                                zs_ = [z for z in stuck_st["zones"] if z[2] > now_]
                                stuck_st["zones"] = zs_
                                pk_ = stuck_pocket(list(stuck_st["hist"]), now_,
                                                   float(prm["stuck_window_s"]),
                                                   float(prm["stuck_extent"]),
                                                   float(prm["stuck_walked"]))  # fmt: skip
                                inz_ = next((z for z in zs_ if goal is not None and max(
                                    abs(goal[0] - z[0][0]), abs(goal[1] - z[0][1])) < z[1]),
                                    None)  # fmt: skip
                                if pk_ is not None or inz_ is not None:
                                    ctr_ = pk_ if pk_ is not None else inz_[0]
                                    eg_ = escape_goal(area, here_, ctr_,
                                                      float(prm["stuck_escape_min"]))  # fmt: skip
                                    ep_ = None if eg_ is None else hc.astar(area, here_, eg_)
                                    if eg_ is not None and ep_ is not None and len(ep_) >= 2:
                                        goal, p_ = eg_, ep_
                                        dy_, dx_ = eg_[1] - ctr_[1], eg_[0] - ctr_[0]
                                        heading_st["ang"] = math.atan2(dy_, dx_)
                                        if pk_ is not None:
                                            stuck_st["zones"].append(
                                                (pk_, float(prm["stuck_zone_r"]),
                                                 now_ + float(prm["stuck_zone_s"])))  # fmt: skip
                                            stuck_st["hist"].clear()
                                    ev({"kind": "stuck_escape",
                                        "why": "pocket" if pk_ is not None else "zone",
                                        "centre": [round(ctr_[0], 1), round(ctr_[1], 1)],
                                        "goal": None if eg_ is None else list(eg_),
                                        "path": None if ep_ is None else len(ep_)})  # fmt: skip
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
            from collections import deque as deque_

            ring_frames: Any = deque_(maxlen=24)  # v21: (mono s, BGR frame) at ~5 Hz, ~4.8 s
            species_model: Any = None
            if prm.get("species_shadow") or prm.get("species_skip"):  # v23 shadow, v25 skip
                import species_check as sc_

                species_model = sc_.load_model()
            icon_templates: list[Any] = []
            if prm.get("loot_icons"):  # v23: the floor items' own sprites (data/item_icons)
                import item_icons as ii_

                icon_templates = ii_.load_templates()

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
                        if prm.get("loot_blobs") and (
                            not ring_frames or time.monotonic() - ring_frames[-1][0] >= 0.18
                        ):
                            with plock:  # v21: BEFORE for the drop detector
                                ring_frames.append((time.monotonic(), img3.copy()))
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
                    stuck_st["mode"] = m_  # the pocket escape reads it from the planner
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

                import route_preview as rp_ui

                guard_ui = (
                    [(x0 - 4, y0 - 4, x1 + 4, y1 + 4) for x0, y0, x1, y1 in rp_ui.UI_WINDOWS]
                    if prm.get("guard_ui_mask")
                    else []
                )  # v17+: the client's static windows are not sprites

                def guard_ok(u: float, v: float, near_box: bool = False) -> bool:
                    """v16+ (a safety layer): no walk click near the GM's sprite or near pink
                    pixels on a FRESH grab (the client picks what its display shows there).
                    ``near_box`` (v42 candidate, steer clicks only): the GM's drawn box +
                    ``steer_guard_box_px`` instead of the ``guard_gm_px`` circle."""
                    if not prm.get("walk_guard"):
                        return True
                    rg_ = int(prm["guard_pink_r"])
                    x0_, y0_ = max(0, int(u) - rg_), max(0, int(v) - rg_)
                    x1_, y1_ = min(gw, int(u) + rg_ + 1), min(gh, int(v) + rg_ + 1)
                    share_ = 0.0
                    if x1_ > x0_ and y1_ > y0_:
                        crop_ = screen.grab(gx0 + x0_, gy0 + y0_, x1_ - x0_, y1_ - y0_)[1]
                        share_ = pink_share(crop_, (x0_, y0_), u, v, rg_, GUARD_EXCLUDE,
                                            guard_ui, ptr[0] if prm.get("guard_ptr_mask")
                                            else None)  # fmt: skip
                    if near_box:
                        why_ = walk_guard_box_why(u, v, share_, GM_SPRITE_BOX,
                                                  float(prm["steer_guard_box_px"]),
                                                  prm["guard_pink_max"])  # fmt: skip
                    else:
                        why_ = walk_guard_why(u, v, share_, prm["guard_gm_px"],
                                              prm["guard_pink_max"])  # fmt: skip
                    guard_n[why_ or "ok"] += 1
                    if sum(guard_n.values()) % 200 == 0:
                        ev({"kind": "walk_guard", **guard_n})
                    return why_ is None

                def cont_click(route: list[Cell], grid: Any, why: str,
                               avoid: tuple[float, float] | None = None,
                               tail: bool = False, near_box: bool = False) -> bool:  # fmt: skip
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
                    fails_: Counter[str] = Counter()  # 3.79 amendment: log-only (cont_fail)
                    for j_ in ahead_candidates(route, src_, prm["ahead_order"], tail=tail):
                        c_ = route[j_]
                        if lead_ is not None:
                            uu, vv = frac_project(world, lead_, c_)  # the click
                            gu, gv = frac_project(world, cur, c_)  # the frames' own pixel
                        else:
                            uu, vv = (float(x) for x in world.project([c_])[0])
                            gu, gv = uu, vv
                        if avoid is not None and prm.get("steer_clear_cells") and cheb(
                                c_, avoid) < prm["steer_clear_cells"]:  # fmt: skip
                            fails_["steer_clear"] += 1
                            continue  # v8 plan B: never a steering click onto the target
                        # the gates in their old order (CONT_GATES), short-circuited as the old
                        # `a and b and ...` chain; the first failing one is only counted
                        fail_: str | None = None
                        if not (in_view(uu, vv) and in_view(gu, gv)):
                            fail_ = "view"
                        elif not grid[c_[1], c_[0]]:
                            fail_ = "grid"
                        elif not units_clear(gu, gv):
                            fail_ = "units"
                        elif not boxes_clear(gu, gv):
                            fail_ = "boxes"
                        elif cont and not walk_ok(c_):
                            fail_ = "refused"
                        elif not guard_ok(uu, vv, near_box):
                            fail_ = "guard"
                        if fail_ is not None:
                            fails_[fail_] += 1
                        else:
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
                            fails_["click_refused"] += 1
                            world.position = at_
                    # v39: the tail arm's counts apart ("steer+tail"); v38's keys unchanged
                    cont_fail_note(why + ("+tail" if tail else "") + ("+box" if near_box else ""),
                                   fails_, len(route))  # fmt: skip
                    return False

                cf_acc: dict[str, Any] = {"t": time.monotonic(), "n": Counter()}

                def cont_fail_note(why: str, fails: Counter[str], route_len: int) -> None:
                    """3.79 amendment (log-only, no behaviour change): why a continuous walk
                    click found no candidate -- the first failing gate per candidate cell, or
                    "none" (no candidate ahead on the route) -- by purpose and by whether the GM
                    was measured moving; one ``cont_fail`` event per 10 s with the counts."""
                    st_ = "moving" if moving else "standing"
                    acc_ = cf_acc["n"]
                    acc_[f"{why}:{st_}:calls"] += 1
                    if not fails:
                        acc_[f"{why}:{st_}:none"] += 1
                        acc_[f"{why}:{st_}:none_route_len_le3"] += route_len <= 3
                    for k_, n_ in fails.items():
                        acc_[f"{why}:{st_}:{k_}"] += n_
                    if time.monotonic() - cf_acc["t"] >= 10.0:
                        ev({"kind": "cont_fail", "counts": dict(acc_)})
                        cf_acc.update(t=time.monotonic(), n=Counter())

                def dead_probe(eng_: dict[str, Any], tr_: Track | None, unseen_: float,
                               live_: Sequence[Track], t_now_: int) -> None:  # fmt: skip
                    """3.80 amendment (log-only, no behaviour change): at every dead call, what
                    the false-dead fix (3.81) could see -- the last burst's end, the same monster
                    under a new id (reacquire_target near the engaged track's prediction), and
                    the freshest frame's monster box nearest the predicted cell's pixel (bottom
                    centre, px). One ``dead_probe`` event; judged offline against packets."""
                    tl_ = eng_tracks.get(int(eng_["track"]))
                    ends_ = [(h_.get("burst") or {}).get("end") for h_ in eng_.get("hovers", [])
                             if h_.get("burst")]  # fmt: skip
                    out_: dict[str, Any] = {"kind": "dead_probe", "k": int(eng_["k"]),
                                            "last_burst": ends_[-1] if ends_ else None,
                                            "unseen_s": round(unseen_, 2),
                                            "track_live": tr_ is not None}  # fmt: skip
                    if tl_ is not None:
                        nt_ = reacquire_target(tl_, live_, t_now_, prm["reacquire_cells"],
                                               list(done_ids) + [tl_.tid])  # fmt: skip
                        pc_ = tl_.predict(t_now_)
                        if nt_ is not None:
                            d_r = round(cheb(nt_.predict(t_now_), pc_), 2)
                            a_r = round((t_now_ - nt_.t_last) / 1e9, 2)
                            out_["reacq"] = {"tid": nt_.tid, "d": d_r, "age_s": a_r}
                        cur_ = measured_pos() or (float(pos[0]), float(pos[1]))
                        pu_, pv_ = frac_project(world, cur_, pc_)
                        fr_ = sampler.since(max(0, len(sampler.frames) - 1))
                        if fr_:
                            bx_ = [float(np.hypot((b_.x0 + b_.x1) / 2 - pu_, b_.y1 - pv_))
                                   for b_ in fr_[-1][1] if b_.cls == "monster"]  # fmt: skip
                            out_["pred_px"] = [round(pu_, 1), round(pv_, 1)]
                            out_["box_px"] = round(min(bx_), 1) if bx_ else None
                            out_["frame_age_s"] = round((r.ns() - int(fr_[-1][0])) / 1e9, 2)
                    ev(out_)

                def death_reason_now(eng_: dict[str, Any], here2: Cell) -> str | None:
                    """v40 candidate: loot_after's death-cell verdict (loot1.death_of on the
                    engaged track's sightings since 2 s before the first click), computed before
                    the loot step; the same inputs as loot_after's (kept apart so v39's loot
                    step is untouched)."""
                    from poring_dataset import deathcell as dcm_

                    tr_ = eng_tracks.get(int(eng_["track"]))
                    if tr_ is None or tr_.box is None:
                        return "no_track"
                    bx = dict(tr_.boxes)
                    t_from = int(eng_["t_first_click"]) - int(2e9)
                    sights = [dcm_.Sighting(int(t_), None if (b_ := bx.get(int(t_))) is None
                                            else (b_.x0, b_.y0, b_.x1, b_.y1))
                              for t_, _bs in sampler.since(0) if int(t_) >= t_from]  # fmt: skip
                    lt = loot1.Track(f1.foot(tr_.box))
                    lt.sightings = sights
                    return str(loot1.death_of(rig, lt, here2).reason)

                def walk_ok(c_: Cell) -> bool:
                    return not refusals.get(c_, 0) >= 2

                try:
                    while time.monotonic() < deadline:
                        now = time.monotonic()
                        pace_tick(now)  # v34
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
                            agent.move(gx0 + max(0, round(qu_) - 12), gy0 + max(0, round(pv_) - 12))
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
                                with typing_pace():  # v34: the clear TYPES
                                    gm_state.clear_loot(agent_raw, screen, why="hunt-flow:mid-run",
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
                            # v28 (FAST DEAD): one hit kills at STR 99 -- once the burst ended on
                            # the client's attack arrow (or the target vanished during it), the
                            # first missed detector frame is the death (v24: server kill -> loot
                            # start p50 2.41 s, 360 s an hour; Batt's whole loot takes 1.56 s)
                            # v32: interleaved per engagement -- the fast rule on odd k only
                            fast_arm = bool(prm.get("fast_dead")) and (
                                not prm.get("fast_dead_ab") or int(eng["k"]) % 2 == 1)  # fmt: skip
                            landed_ = fast_arm and any(
                                (h_.get("burst") or {}).get("end") in ("arrow", "gone")
                                for h_ in eng.get("hovers", []))  # fmt: skip
                            fast_ = landed_ and (since_last >= prm["fast_dead_min_s"]
                                                 and unseen >= prm["fast_dead_gone_s"])  # fmt: skip
                            slow_ = since_last >= prm["dead_min_s"] and unseen >= prm["dead_gone_s"]
                            exp_arm = exp_dead_on(prm, int(eng["k"]))  # 3.87: odd k
                            line_ = None
                            if exp_arm:
                                eng["exp_arm"] = True
                                assert bl_tail is not None
                                if not bl_tail.alive():  # a fault, not a result: never blind
                                    raise f0.FarmStop("the Battle Log reader exited twice")
                                line_ = bl_tail.take_base_exp(int(eng["t_first_click"]))
                            if line_ is not None:
                                # 3.87: DEAD = a new base EXP line since our first attack click
                                done = "dead"
                                eng["dead_rule"] = "exp"
                                eng["dead_by"] = ("exp_after_pixel" if eng.get("pix_dead_t")
                                                  else "exp")  # fmt: skip
                                eng["exp_line"] = {"t_ns": int(line_["t_ns"]),
                                                   "t_emit_ns": int(line_.get("t_emit_ns")
                                                                    or line_["t_ns"]),
                                                   "n": line_.get("n")}  # fmt: skip
                                ev({"kind": "exp_dead", "k": int(eng["k"]),
                                    "track": int(eng["track"]), "line_t_ns": int(line_["t_ns"]),
                                    "since_first_s": round((int(line_["t_ns"])
                                                            - int(eng["t_first_click"])) / 1e9, 3),
                                    "lag_s": round((t_now - int(line_["t_ns"])) / 1e9, 3),
                                    "pixel_waited": eng.get("pix_dead_t") is not None})  # fmt: skip
                            elif exp_arm and (fast_ or slow_):
                                # 3.87 the CHECKED fallback: the pixel call waits exp_wait_s for
                                # an EXP line (no re-click meanwhile), then stands only on the
                                # death-cell verdict (below, before the loot step)
                                if eng.get("pix_dead_t") is None:
                                    eng["pix_dead_t"] = t_now
                                    eng["dead_by"] = "fast" if (fast_ and not slow_) else "slow"
                                    ev({"kind": "pix_dead_wait", "k": int(eng["k"]),
                                        "track": int(eng["track"])})  # fmt: skip
                                if (t_now - int(eng["pix_dead_t"])) / 1e9 < prm["exp_wait_s"]:
                                    time.sleep(0.02)
                                    continue
                                done = "dead"
                                eng["dead_rule"] = "pixel_checked"
                            elif fast_ or slow_:
                                done = "dead"
                                eng["dead_rule"] = "fast" if fast_arm else "slow"
                                eng["dead_by"] = "fast" if (fast_ and not slow_) else "slow"
                                if prm.get("dead_probe"):  # 3.80 amendment: log-only
                                    try:  # a log-only probe never stops a run
                                        dead_probe(eng, tr, unseen, live, t_now)
                                    except Exception as e_:  # noqa: BLE001
                                        ev({"kind": "dead_probe_error", "err": repr(e_)[:200]})
                            elif since_first > prm["give_up_s"]:
                                banned.append((now, tuple(int(x) for x in eng["pred_cell"])))
                                done = "gave_up"
                            if done is None:
                                if since_last >= prm["reclick_s"] and tr is not None and not moving:
                                    strike(tr, pos, again=True)
                                time.sleep(0.02)
                                continue
                            looter_ = None
                            if done == "dead" and prm.get("loot"):
                                if eng.get("dead_rule") not in ("fast", "exp", "pixel_checked"):
                                    time.sleep(0.4)  # v28: the hybrid death cell needs no gone
                                    # frames (v32: per arm); 3.87: an EXP line is the death, and
                                    # the checked fallback has waited exp_wait_s already
                                here_l = quick_fix()
                                posm.stop(here_l)
                                ends_ = [(h_.get("burst") or {}).get("end")
                                         for h_ in eng.get("hovers", [])
                                         if h_.get("burst")]  # fmt: skip
                                if eng.get("dead_rule") == "pixel_checked":
                                    # 3.87: no EXP line within exp_wait_s -> the pixel call
                                    # stands only on the death-cell verdict "ok" (every burst)
                                    rs_ = death_reason_now(eng, here_l)
                                    done = checked_fallback(rs_)
                                    eng["death"] = {"reason": rs_,
                                                    "skipped": done != "dead"}  # fmt: skip
                                    ev({"kind": "pix_dead_checked", "k": int(eng["k"]),
                                        "track": int(eng["track"]), "reason": rs_,
                                        "result": done})  # fmt: skip
                                elif eng.get("exp_arm"):
                                    pass  # 3.87: the EXP line confirmed it (v40's check moot)
                                elif prm.get("false_dead_fix") and (
                                        not prm.get("false_dead_ab")
                                        or int(eng["k"]) % 2 == 1):  # fmt: skip
                                    # v40 candidate (Batt 16:2x): a risky burst's dead call
                                    # stands only on a clean death-cell verdict
                                    eng["fd_arm"] = True
                                    rs_ = (death_reason_now(eng, here_l)
                                           if ends_ and ends_[-1] == "risky" else None)  # fmt: skip
                                    if risky_unproven(ends_[-1] if ends_ else None, rs_):
                                        eng["death"] = {"reason": rs_, "skipped": True}
                                        ev({"kind": "fd_skipped", "k": int(eng["k"]),
                                            "track": int(eng["track"]), "reason": rs_})  # fmt: skip
                                        done = "skipped_risky"
                                if done == "dead":
                                    loot_after(eng, here_l)
                                    looter_ = (eng.get("loot") or {}).get("looter")
                            k_done = int(eng["k"])
                            end_engagement(done)
                            ev({"kind": "hand_off", "after": done})
                            busy_t[0] = time.monotonic()  # the loot sweep was busy time too
                            pos = quick_fix()
                            posm.stop(pos)
                            moving, path, pi = False, [], 0
                            live = tracks_now()
                            t_now = r.ns()
                            if looter_ is not None:
                                # v33: the LOOTER on our pile is the next target, at once; its
                                # own loot step covers our cells still unclicked
                                fresh_l = [
                                    x
                                    for x in live
                                    if x.box is not None
                                    and x.tid not in done_ids
                                    and (t_now - x.box_t) / 1e9 <= prm["fresh_s"] + 0.4
                                ]
                                tl_ = min(fresh_l, default=None, key=lambda x: math.hypot(
                                    f1.centre(x.box)[0] - looter_["u"],
                                    x.box.y1 - loot1.FOOT_LIFT - looter_["v"]))  # fmt: skip
                                d_l = None if tl_ is None else math.hypot(
                                    f1.centre(tl_.box)[0] - looter_["u"],
                                    tl_.box.y1 - loot1.FOOT_LIFT - looter_["v"])  # fmt: skip
                                if tl_ is not None and d_l is not None and (
                                        d_l <= prm["looter_match_px"]):  # fmt: skip
                                    looter_pend.update(tid=tl_.tid, cells=looter_["pending"],
                                                       t=time.monotonic(), k=k_done)  # fmt: skip
                                    target, reads = tl_, 0
                                    t_target[0] = time.monotonic()
                                    ev({"kind": "looter_engage", "track": tl_.tid, "k": k_done,
                                        "d_px": round(d_l, 1),
                                        "pending": len(looter_["pending"])})  # fmt: skip
                                else:
                                    ev(
                                        {
                                            "kind": "looter_lost",
                                            "k": k_done,
                                            "d_px": None if d_l is None else round(d_l, 1),
                                        }
                                    )
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
                        if (target is not None and eng is None and prm.get("steer_stuck_s")
                                and now - max(last_progress[0], t_target[0])
                                > prm["steer_stuck_s"]):  # fmt: skip
                            # v27: a steering DEADLOCK (v26 stopped on "no progress for 60 s": the
                            # zone's one path ran into a blocked spot and no click came again) --
                            # drop the target, forget the zone; the planner moves on
                            tc_s = target.predict(t_now)
                            banned.append((now, (int(round(tc_s[0])), int(round(tc_s[1])))))
                            ev({"kind": "target_dropped", "track": target.tid,
                                "why": "steer_stuck"})  # fmt: skip
                            zone_st.clear()
                            target = None
                        if target is not None:
                            split.to("steering", time.monotonic())
                            tcell = target.predict(t_now)
                            s_range = strike_range(target, prm, k)
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
                                if (prm.get("strike_moving") and species_model is not None
                                        and fresh_box and target.box is not None
                                        and not gate_risks(target, pos)):  # fmt: skip
                                    # v25 (Batt's item 3, "start the read while walking in"):
                                    # in range while WALKING -> strike now when the pixel check
                                    # is sure of a target with no other box near (the click
                                    # makes the client walk in and attack, as Batt does)
                                    sp_m, _cf, cr_m = species_now(target.box)
                                    if sp_m in nametag.TARGET_NAMES and not cr_m:
                                        ev({"kind": "strike_moving", "track": target.tid,
                                            "species": sp_m})  # fmt: skip
                                        if (not strike(target, pos, again=False)
                                                and reads >= prm["max_reads"]):  # fmt: skip
                                            tc_m = (int(round(tcell[0])), int(round(tcell[1])))
                                            banned.append((now, tc_m))
                                            target = None
                                        continue
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
                                            target, prm, k) < prm["zone_radius"]
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
                                    elif cont_click(ap, ok, "steer", tcell,
                                                    tail=steer_tail_on(k),
                                                    near_box=steer_box_on(k)):  # fmt: skip
                                        stop_since = None
                                    elif not moving:
                                        stop_since = stop_since or now
                                        if now - stop_since > prm["stop_after_s"]:
                                            # none passed for 1 s: the GM stops; cursor-gated.
                                            # v39: from the route point nearest the GM (the old
                                            # index 0 is a start the GM has walked past)
                                            i0_ = (min(range(len(ap)),
                                                       key=lambda i_: cheb(ap[i_], pos))
                                                   if steer_tail_on(k) else 0)  # fmt: skip
                                            j, (u, v) = step_target(ap, i0_, pos, prm["ahead"],
                                                                    ok)  # fmt: skip
                                            if j is not None:
                                                walk_click(u, v, ap[j], ap[: j + 1], "cursor",
                                                           "steer")  # fmt: skip
                                            else:  # 3.79 amendment: log-only
                                                cf_acc["n"]["steer:fallback_no_step"] += 1
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
                            # v16 attempt 3: refusals had carved `ok` shut around the GM ->
                            # first the cells WE WALKED (the client took them), then random
                            # cells, both on the walkable grid as it was before any refusal
                            g0_ = ok0.copy()
                            g0_[pos[1], pos[0]] = True
                            with plock:
                                tr_u = list(trail)
                            cands_u = [*trail_cells(tr_u, pos, now, near=4, far=25, min_age_s=2.0),
                                       *unstall_cells(g0_, pos, unstall_rng, k=6)]  # fmt: skip
                            for c_ in cands_u:
                                p_ = hc.astar(g0_, pos, c_)
                                if p_ is not None and len(p_) >= 2:
                                    with plock:
                                        plan.update(goal_path=p_, escape="unstall", t_goal=now)
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
                            grid_s = (
                                ok0
                                if plan.get("escape") == "unstall"  # its own grid
                                else ok
                                if plan.get("escape")
                                else area
                            )  # v8 attempt 2
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
                        gm_state.clear_loot(agent_raw, screen, why="hunt-flow:mid-run",
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
            if bl_tail is not None:
                bl_tail.stop()
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
                after = f0._brief(gm_state.ensure_fixed(agent_raw, screen,
                                                        why=f"hunt-flow@{version}:after",
                                                        out_dir=log.dir / "gm_state",
                                                        profile="hunt-flow"))  # fmt: skip
                bench.close_chat(agent_raw, screen)
        ev({"kind": "gm_state_after", **after})
    events_f.close()
    clicks_f.close()
    events, anchor = record_session.write_packets(log.dir, t_first, r.ns())
    (log.dir / "engagements.json").write_text(json.dumps(engagements, default=str))
    summary = {"run_s": round(run_s, 1), "engagements": len(engagements),
               "results": dict(Counter(e["result"] for e in engagements)),
               "split": split.ranked(), "coverage_cells": cov.first_seen,
               "det_fps": None if sampler is None or not run_s
               else round(len(sampler.frames) / run_s, 2), "walk_guard": dict(guard_n),
               "frame_guard": dict(fg_n),
               "battle_log": None if bl_tail is None else {
                   "lines": len(bl_tail.lines), "base_exp_used": len(bl_tail.used),
                   "restarts": bl_tail.restarts}}  # fmt: skip
    log.finish(ended=ended, packet_events=len(events), packet_anchor=anchor, **summary)
    print(json.dumps({"session": sid, "ended": ended, **summary}, default=str), flush=True)
    if crashed is not None:
        raise crashed
    return 0 if ended == "time_box" else 3


def main() -> int:
    global MAP
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    rn = sub.add_parser("run")
    rn.add_argument("--version", type=int, required=True)
    rn.add_argument("--minutes", type=float, default=30.0)
    rn.add_argument("--seed", type=int, default=20261201)
    rn.add_argument("--map", default=MAP, help="a held-out map (its GAT in GAT_DIR, L3, npc_cells)")
    a = ap.parse_args()
    MAP = a.map
    return run(a.version, a.minutes, a.seed)


if __name__ == "__main__":
    sys.exit(main())
