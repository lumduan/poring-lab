---
doc_type: measurement
hypothesis: "The bot's two biggest IDLE losses against Batt on gef_fild10 -- idle inside search and the loot pause -- are not 'thinking time' in general but a few concrete runner mechanisms (named waits, bounds and timers in dungeon_hunt.py) that can be measured second by second from the runner's own events joined to the time budget's packet labels, and the largest of them can be cut without touching any safety bar."
status: "MEASURED (offline): scripts/idle_study.py on c5b, c6, c7 (the brief's pool) and on c8, read after the proposal's rule was committed (section 3e). Nothing is pre-registered; no runner changed."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [gef10-time-budget.md, gef10-cursor-unknown.md, gef10-miss-cue.md, rogue-gef10.md, ../../scripts/idle_study.py, ../../scripts/time_budget.py, ../../scripts/dungeon_hunt.py, ../../services/backend/tests/test_idle_study.py]
next_action: "The parent: pre-register the LOOT TRIM (section 5: `--loot trim`, OFF by default -- loot v1's own order, at most 9 hovers per loot step, no sweep) as one arm against today's P2 + 9.1b, and build it behind that option; Batt: accept or refuse its one cost (about 5 % of floor pickups left on the ground: 4 of 84 here). Next in line: longer walk legs through the waypoint (section 6.1) and the patrol dead end (6.2, a correctness bug)."
title: "gef_fild10: what the runner does in its idle seconds (the idle study), and the one change to make first"
date: 2026-10-26
owner: Batt
---

# gef_fild10: what the runner does in its idle seconds

**Why.** [gef10-time-budget.md](gef10-time-budget.md) ranks the bot's losses against Batt by
seconds per kill. On today's P2 runs (c5b, c6, c7; 91.0 kills / h against his 232.7) the two
biggest are both IDLE: **idle inside search** (6.70 s per kill; Batt 0.46) and the **loot pause**
(6.33; Batt 1.24). Idle after a fight comes fifth (4.03; Batt 0.19). The time budget's labels come
from the packets, so they say *that* the Rogue stood still, not *why*. This study joins every
idle second to what the runner was doing at that moment, from its own events, and names the code
that made it wait.

**What this is NOT.** It changes no runner and no default, and it decides nothing. Every number
is **measured** offline from the runs' events and packets, unless it says **estimate**. Packets
are used only as offline truth (ADR-0007); the proposal uses pixels and the runner's own state
only.

## 0. The answer in brief

1. **Idle inside search (6.70 s per kill) is the walk's stop-and-go: 82 % of it.**
   - Each walk click sends a path of 5-6 cells (0.90-0.96 s of walking, median), but clicks come
     every 1.25 s (WALK_EVERY_S = 1.2 s, counted from the START of the previous decision). So the
     Rogue stops for about 0.3-0.4 s after almost every click: 1,679 stops of under 2.5 s,
     848.1 s in all (5.2 s per kill).
   - During that stop the runner is busy with the NEXT walk decision (4.80 s per kill): about
     0.4 s of cursor read and 0.5 s of paced click (`click_at`), ~0.9 s per decision.
   - 52-56 % of the walk clicks target the patrol waypoint itself, so the path ends there
     (WP_TOL = 2) however long WALK_AHEAD is.
   - The rest: a **patrol dead end** (0.39 s per kill, all in c7: 62.8 s, 1.40 s per kill there),
     the stall scan (0.21), empty defend scans (0.28), Fly Wing settling (0.15), the UI watch
     (0.32, a lower bound).
2. **The loot pause (6.33 s per kill) is the loot step's hover list: 72 % of it.**
   - Loot v1 hovers the 5 x 5 around our cell at every kill (25 cells per kill, up to 30), then
     sweeps up to 10 "changed" cells, ~0.37 s per hover: a one-kill step is 35 hovers, ~14-15 s.
   - **80 of its 84 pickups came within its first 9 hovers** (our own cell and ring 1); 83 of 84
     came from the list, 1 from the sweep. The seconds after a step's last pickup add up to
     1,180 s of its 1,379 s.
   - The list hovers are 3.36 s per kill, the sweep 1.17, the pickup waits 0.24. The rest:
     "other" 0.53 (76 % of it in c6: its 9.1 re-engage loop), empty defend scans 0.49, walk
     decisions 0.26, a patrol dead end 0.19 (c6).
3. **Idle after a fight (4.03 s per kill) is mostly the same loot step (2.51 s per kill)** when it
   found nothing to pick (no loot label follows), plus Fly Wing settling (0.38), empty scans
   after a kill or a phantom fight (0.43) and c6's loop.
4. **The ONE change: the LOOT TRIM** (section 5). Keep loot v1's order, stop each loot step after
   9 hovers, and drop the sweep.
   - **Estimate: +14.1 kills / h** on the same three runs (91.0 -> 105.1): 863.2 s of the
     6,446.5 s are cut, 843.3 s of them from idle labels (+13.7 if only those convert).
   - **Cost:** 4 of 84 pickups lost (4.8 %); 14 SWORDs the loot hover found late are left to the
     other triggers.
   - **c8, read after the rule was committed** (section 3e): it would have kept all 29 of its
     pickups and saved 308.7 s (81.7 -> 95.3 kills / h, +13.6). With c8 the pool gives +14.0
     (88.7 -> 102.7) and 4 of 113 pickups lost (3.5 %).
   - **Risk:** it only removes pointer hovers. It adds no click and no new click path, and it
     touches no safety bar.
5. **Runner-ups** (section 6): longer walk legs through the waypoint (+11.1 to +12.5 kills / h,
   estimate); the patrol dead end, a correctness bug (<= +1.4); the empty defend scans
   (<= +1.7 and <= +1.1).

## 1. What was read

- **Runs:** c5b (`20261026T150619`, P2), c6 (`20261026T162920`, P2 + the 9.1 cue, with its
  loop), c7 (`20261026T170913`, P2): the brief's pool, 6,446.5 s, 163 kills, **91.0 kills / h**,
  the same windows and labels as `time_budget.py compare` (run_start .. run_end). c8 (P2 + 9.1b)
  is added in section 3e.
- **Batt's demo** (`20261026T095021-demo-human-demo-gef10`, `--live 898`) only for the walk
  comparison (section 4a); it has no runner events.
- **Events:** each run's `events.jsonl` (t_ns on the host CLOCK_MONOTONIC, the packets' clock).
  The runner logs a scan and a loot step at their END with `ms`, a strike with t_end_ns, every
  walk decision, every loot click, and one `hp_read` per tick; a guard_tick read inside a long
  action is marked `quick` (one after every hover).
- **Packets:** `packets.jsonl.gz`, only through `time_budget.analyse` (the labels) and our
  self_move paths (the walk cadence). Offline truth only.
- **Code:** `scripts/dungeon_hunt.py` at 020eeac (dungeon@8.3 with 9.0b / 9.1b's options), and
  `scripts/ro_agent.py` / `scripts/cursor_sword.py` for the input timing.

## 2. Method: the join

1. `time_budget.analyse` labels every instant of the window (its docstring is the definition of
   record) and `seg_causes` names each idle stretch by its context.
2. `idle_study.mech_spans` builds the runner's own activity spans from its events. Each instant of
   an idle stretch takes the FIRST mechanism of this list that covers it, else "other":

   | # | mechanism | span (from the events) | the code that makes it (dungeon_hunt.py) |
   |---|---|---|---|
   | 1 | loot_pick_wait | loot_click .. + 0.45 + 0.2 d s | `loot_step_v1.visit`: `time.sleep(0.45 + 0.2 * d_)` (l. 1851) |
   | 2 | strike | strike t_ns .. t_end_ns | `strike()`: the burst until the lock arrow / our damage / 3 s |
   | 3 | fly_settle | a Fly Wing press .. the next position read | the loop's `time.sleep(1.0)` and FLY_SETTLE_S = 2.5 (l. 214, 2107) |
   | 4 | loot_list_hover | loot step start .. its list_hovered-th guard read | `loot_step_v1`'s list loop (l. 1856): LOOT_MAX_HOVERS = 30, LOOT_MAX_S = 25 (l. 194) |
   | 5 | loot_sweep_hover | .. the step's end | the sweep: `changed_cells` + up to SWEEP_MAX = 10 hovers (l. 1870-1872) |
   | 6 | stall_scan | a scan right after a `stall` | the stall branch's `scan("defend", ring(1))` (l. 2622) |
   | 7 | scan_found | a defend scan that found a SWORD | the fight loop's scan (l. 2361-2363) |
   | 8 | scan_empty_after_kill | an empty scan after a kill in its fight | the same, after a kill cleared the lock |
   | 9 | scan_empty_no_kill | an empty scan, no kill yet in its fight | the same, in a fight with no kill (box, hit, Miss, HP drop) |
   | 10 | patrol_dead_end | route-less `goal` events <= 1.5 s apart | `patrol_goal` + `skip_waypoint` (l. 2553-2555) until IDLE_MAX_S = 45 (l. 2512) |
   | 11 | walk_decision | the tick's hp_read .. its walk event (<= 2.5 s) | the walk block (l. 2561-2630): `route`, `walk_target`, `hover`, `trust_why`, `click_at` |
   | 12 | ui_watch | a tick > 0.6 s that logged nothing else | the UI watch every UI_EVERY_S = 10 s (l. 2271): `f0.client_state` + the weight read |
   | 13 | fight_other | engage .. fight_end / Fly Wing, the rest | the fight loop's lock waits and 5 Hz ticks |
   | 14 | walk_timer | a walk event .. the next decision (<= 3 s) | WALK_EVERY_S = 1.2 (l. 209, 2561) |

3. Per cause and mechanism: seconds per kill and the count of that mechanism's spans that took
   any of it. Every second of a studied stretch lands in exactly one mechanism (tested).
4. Two side analyses: the **walk cadence** from our self_move packets (path cells, moving
   seconds, the stops between moves) and the runner's walk events; and the **loot steps** (the
   hover rank of each pickup: the guard reads since the step began).

**Approximations** (stated, not hidden):
- The list / sweep boundary is the list_hovered-th guard read; one read follows every hover
  (129 of the 132 steps have exactly one read per hover before any strike; the 38 steps with
  1-6 extra reads all held a strike, whose burst reads HP, and the rank counts only the reads
  before it; 3 steps had 1, 3 and 5 reads fewer than hovers, a hover decided in under 0.25 s).
- A walk decision is timed from its tick's hp_read. When the 10-s UI watch falls in that tick, the
  decision span carries it (43-56 trusted decisions per run took over 1.5 s); "ui_watch" is
  therefore a lower bound.

## 3. The decomposition (seconds per kill; in brackets the number of spans)

The time budget's own per-kill totals for the pool (`time_budget.py compare`, 163 kills): idle
inside search **6.70**, loot pause **6.33**, after fight **4.03** (Batt: 0.46, 1.24, 0.19).

### 3a. Idle inside search

| mechanism | c5b | c6 | c7 | **pooled** |
|---|---|---|---|---|
| walk_decision | 5.16 (634) | 3.29 (447) | 6.34 (670) | **4.80** (1,751) |
| patrol_dead_end | 0.01 (3) | 0.01 (5) | 1.40 (6) | **0.39** (14) |
| walk_timer | 0.50 (99) | 0.22 (55) | 0.42 (78) | **0.38** (232) |
| ui_watch | 0.25 (38) | 0.20 (27) | 0.55 (54) | **0.32** (119) |
| stall_scan | 0.33 (6) | 0.21 (4) | 0.08 (1) | 0.21 (11) |
| scan_empty_no_kill | 0.10 (2) | 0 | 0.60 (10) | 0.20 (12) |
| fly_settle | 0 | 0 | 0.55 (4) | 0.15 (4) |
| loot hovers (a loot step between two search stretches, e.g. the sweep after a phantom fight) | 0.32 (3) | 0 | 0.10 (1) | 0.14 (4) |
| scan_empty_after_kill | 0.22 (2) | 0 | 0 | 0.08 (2) |
| other, fight_other, strike, scan_found | 0.03 | 0.01 | 0.05 | 0.02 |
| **total** | **6.93** | **3.94** | **10.09** | **6.70** |

### 3b. The loot pause

| mechanism | c5b | c6 | c7 | **pooled** |
|---|---|---|---|---|
| loot_list_hover | 1.98 (11) | 3.78 (22) | 4.57 (20) | **3.36** (53) |
| loot_sweep_hover | 0.56 (8) | 1.54 (22) | 1.48 (16) | **1.17** (46) |
| other | 0.15 (10) | 1.10 (414) | 0.27 (21) | 0.53 (445) |
| scan_empty_no_kill | 0 | 0.83 (14) | 0 | 0.30 (14) |
| walk_decision | 0.13 (11) | 0.36 (29) | 0.30 (19) | 0.26 (59) |
| loot_pick_wait | 0.11 (11) | 0.29 (29) | 0.34 (26) | 0.24 (66) |
| patrol_dead_end | 0 | 0.52 (2) | 0.00 (1) | 0.19 (3) |
| scan_empty_after_kill | 0 | 0.51 (6) | 0 | 0.19 (6) |
| stall_scan, walk_timer, fly_settle, fight_other, strike | 0.00 | 0.22 | 0.01 | 0.09 |
| **total** | **2.93** | **9.13** | **6.98** | **6.33** |

- c6's "other" (66 s, 414 pieces) and its 401 tiny "fights" are the 9.1 cue's re-engage loop
  (rogue-gef10.md Amendment W): engage / fight_end pairs on every tick after a kill, which held
  the loot step back. 9.1b removed the loop.

### 3c. Idle after a fight

| mechanism | c5b | c6 | c7 | **pooled** |
|---|---|---|---|---|
| loot_list_hover | 2.82 (18) | 1.47 (10) | 1.10 (6) | **1.85** (34) |
| loot_sweep_hover | 0.90 (13) | 0.58 (9) | 0.46 (5) | **0.66** (27) |
| other | 0.23 (19) | 0.73 (300) | 0.13 (8) | 0.38 (327) |
| fly_settle | 0.44 (6) | 0.29 (3) | 0.43 (5) | 0.38 (14) |
| scan_empty_no_kill | 0 | 0.39 (8) | 0.31 (3) | 0.23 (11) |
| scan_empty_after_kill | 0 | 0.20 (2) | 0.47 (5) | 0.20 (7) |
| walk_decision | 0.21 (18) | 0.16 (12) | 0.18 (11) | 0.18 (41) |
| stall_scan, fight_other, walk_timer, scan_found, strike, dead end | 0.15 | 0.15 | 0.12 | 0.14 |
| **total** | **4.75** | **3.96** | **3.20** | **4.03** |

- An after-fight stretch is the same loot step when it picked nothing: with no pickup there is no
  loot label, so the stretch runs from the fight's end into the next search.

### 3d. The loot steps and the walk (side analyses)

| loot steps (loot v1) | c5b | c6 | c7 | **pooled** |
|---|---|---|---|---|
| steps / seconds | 59 / 490.1 | 34 / 476.3 | 39 / 412.4 | **132 / 1,378.8 (8.46 s per kill)** |
| pickups (loot clicks) | 18 | 34 | 32 | **84** |
| steps with a pickup | 17 | 23 | 22 | 62 |
| ended by a SWORD under a hover ("fight") / done | 30 / 29 | 3 / 31 | 14 / 25 | 47 / 85 |
| hover, median (guard read to guard read) | 0.369 s | 0.376 s | 0.372 s | |
| pickups at a hover rank <= 9 / > 9 | 18 / 0 | 33 / 1 | 29 / 3 | **80 / 4** |
| pickups by the item's distance from us: 0 / 1 / 2 / 3 cells | 10 / 8 / 0 / 0 | 12 / 21 / 1 / 0 | 11 / 18 / 1 / 2 | 33 / 47 / 2 / 2 |
| pickups from the list / the sweep | 18 / 0 | 34 / 0 | 31 / 1 | **83 / 1** |
| seconds after a step's last pickup wait (or the whole step without one) | 457.2 | 399.4 | 323.6 | **1,180.2** |

| walk (packets: our self_move; events: walk clicks) | c5b | c6 | c7 | Batt |
|---|---|---|---|---|
| walk clicks | 803 | 564 | 842 | (28.1 requests / min) |
| click to click, median | 1.251 s | 1.238 s | 1.249 s | |
| our path per move, median | 5 cells | 5 cells | 6 cells | 6 cells |
| moving per move, median | 0.93 s | 0.90 s | 0.96 s | **0.72 s** (cut short by his next click) |
| clicks whose target IS the patrol waypoint | 52.1 % | 54.8 % | 55.9 % | |
| stops inside search under 2.5 s: n / seconds / median | 599 / 323.4 / 0.43 | 435 / 210.0 / 0.42 | 645 / 314.7 / 0.38 | 79 / 26.9 / **0.13** (14.95 min) |

### 3e. c8 (P2 + the 9.1b cue), read after the rule was fixed

c8 (`20261026T174709`, 36.0 min, time box, 49 kills, **81.7 kills / h**) ended at 18:24, after the
TRIM rule (9 hovers, no sweep: `PROPOSAL = "9"` in `idle_study.py`) was committed in 760f439 at
18:20:57 on c5b-c7 alone. It is therefore a first out-of-sample check of the rule, not a source
of it.

| | c8 | pooled with c5b, c6, c7 (4 runs, 212 kills, 8,606.7 s, 88.7 kills / h) |
|---|---|---|
| idle inside search / loot pause / after fight (s per kill) | 8.07 / 6.47 / 5.00 | 7.02 / 6.36 / 4.25 |
| inside search: walk_decision + walk_timer + ui_watch | 5.98 (74 %) | 5.62 (80 %) |
| inside search: empty defend scans in a fight with no kill | 1.20 (13: 12 after a Battle Log hit, 55.8 s) | 0.43 (25) |
| loot pause: list + sweep hovers | 4.90 (76 %) | 4.61 (72 %) |
| after fight: list + sweep hovers | 2.83 (57 %) | 2.58 (61 %) |
| loot steps / seconds / pickups | 56 / 506.1 / 29 (13 steps after a fight with no kill) | 188 / 1,884.9 / 113 |
| pickups at a hover rank <= 9 | **29 of 29** (distance 0: 15, 1: 14) | 109 of 113 |
| TRIM 9: saved / pickups lost / late SWORDs | **308.7 s / 0 / 9** | 1,171.9 s / 4 / 23 |
| TRIM 9: kills / h (estimate) | **81.7 -> 95.3 (+13.6)** | **88.7 -> 102.7 (+14.0)**; idle seconds only +13.6 |
| walk legs +5 / +7 cells (estimate) | +9.6 / +10.9 | +10.7 / +12.1 |
| walk: clicks, click gap, path, moving, target = waypoint | 728, 1.242 s, 6 cells, 0.96 s, 53.6 % | |
| stops inside search under 2.5 s | 583, 276.5 s, median 0.35 s | 2,262, 1,124.6 s |

- c8 tells the same story: the stop-and-go and the loot hovers dominate, and the trimmed step
  would have kept every one of its 29 pickups.
- c8 adds one thing: 1.20 s per kill of empty defend scans inside search. 12 of the 13 followed a
  Battle Log hit on us (55.8 s) whose rings 1-2 showed no SWORD: the unanswered attacker of
  gef10-time-budget.md section 5 (section 6.3). None followed a Miss-cue engage.

## 4. The mechanisms, with their code

### 4a. The walk's stop-and-go (idle inside search: walk_decision + walk_timer + ui_watch, 5.50 of 6.70 s per kill)

1. **The decision is slow, and the timer counts from its START.** The SEARCH walk
   (dungeon_hunt.py l. 2560-2630) runs when `tick - last_walk >= WALK_EVERY_S` (1.2 s), with
   `last_walk = tick`, the decision's start. One decision:
   - `route(okr, carved, here, goal_path[-1])` when the minimap cell is not on the planned path;
   - `walk_target` (7 cells ahead, in view, the zones' segment check);
   - `hover()`: `cursor_sword.check` with CURSOR_WAIT_S = 0.35 s. On a moving camera it ends
     UNKNOWN almost always (gef10-cursor-unknown.md): 761 / 529 / 807 of the 803 / 564 / 842
     clicks were `--walk-trust` clicks of an UNKNOWN read;
   - `walk_trust.trust_why`, then `click_at`: a move, 0.02 s, a move, 0.05 s, then
     `ro_agent.click` (a move, HOLD_S 0.05, down, 0.05, up, 0.05): five acknowledged sends.
   - **Measured** (tick's hp_read to walk event, medians): a trusted click **0.90 s** in all three
     runs; a refused read with no click (hover + red crop + trust_why) **0.38-0.41 s**. So
     `click_at` takes ~0.5 s, the read ~0.4 s. The walk request packet leaves 0.14 s before the
     walk event (c7, median).
2. **The path is shorter than the cadence.** The click aims WALK_AHEAD = 7 cells ahead of the
   minimap cell, which lags the server by ~0.5 s; the server path is a median 5-6 cells, walked in
   0.90-0.96 s. Clicks come every 1.25 s. The Rogue therefore arrives ~0.3 s before the next
   click and stands: a stop after nearly every click (1,679 stops under 2.5 s, 848.1 s, median
   0.38-0.43 s), during which the runner is inside its next decision (hence "walk_decision").
3. **The waypoint caps the leg.** 52-56 % of the clicks target the patrol waypoint itself
   (`patrol_goal` advances only within WP_TOL = 2 cells, l. 1397), so near a waypoint the path is
   shorter still, whatever WALK_AHEAD is.
4. **Batt does the opposite.** His moves are as long (6 cells) but last 0.72 s: his next click
   supersedes the walk before it ends. His stops inside search: 79 in 14.95 min, median 0.13 s.
5. The UI watch (UI_EVERY_S = 10 s, `f0.client_state` + the weight read, ~1.0-1.1 s each) adds a
   1-s block every 10 s outside fights: 0.32 s per kill where it fell outside a walk tick.

### 4b. The loot step (loot pause 4.77 and after fight 2.51 s per kill, with its pickup waits)

1. **What runs** (`loot_step_v1`, l. 1806-1880; every run used `--loot v1`, the default): the
   LOOT LIST is the 5 x 5 around our cell at EVERY kill of the fight (<= 55 s old), walkable and
   outside the zones, nearest first; then the SWEEP, up to SWEEP_MAX = 10 cells whose 24 x 20
   patch changed by SWEEP_DIFF since the fight began. Bounds: LOOT_MAX_HOVERS = 30 list hovers,
   LOOT_MAX_PICKS = 10, LOOT_MAX_S = 25 s. Every hover is a 0.35-s cursor read plus the red crop
   (0.37 s per hover, median).
2. **What it finds.** 80 of the 84 pickups came within the first 9 hovers (our own cell, then
   ring 1); 80 of 84 lay 0-1 cells from us (2 at 2 cells, 2 at 3). 83 came from the list, 1 from
   the sweep. The sweep's "changed" test flags a median 145-150 cells per step on gef_fild10
   (6-201) and hovers 10 of them.
3. **So most of a step is a fruitless tail.** A one-kill step that picks its drop at hover 1 still
   hovers 34 more cells (c7 at 595 s: 15.2 s for one pickup at rank 1; it would have stopped 10.7 s
   earlier at 9 hovers). Pooled, 1,180 of the steps' 1,379 s came after their last pickup.
4. **A fight with no kill still sweeps.** `if mode == "after" and (loot_list or fight_ref is not
   None)` (l. 2383): a phantom fight (a box or a hit with nobody found) leaves fight_ref set, so
   an empty list is followed by a 10-hover sweep (~4 s).

### 4c. The patrol dead end (idle inside search 0.39 s per kill; c7 1.40)

- c7 at 1,312 s: the Rogue stood at 152,309 and every waypoint came back with no route. The patrol
  skipped one waypoint per tick (`skip_waypoint`, l. 2555), round the 80-waypoint loop about five
  times (412 route-less goal events), until the IDLE_MAX_S = 45 s watchdog pressed a Fly Wing
  (45.8 s). The same cell had held it 16.3 s at 319 s, ended there by a fight.
- **Why** (offline, the run's own grids: `stand_grid` + the zones): 152,309 lies in a pocket of the
  route grid whose only exit runs west along row 306. The read before the stop was "cursor
  unknown + red" (94 red px) at 146,306, and that carved a 5 x 5 (CARVE_R = 2) across the exit.
  `route()` restores the base grid only within CARVE_R of OUR cell, so from inside the pocket
  nothing is routable; with no carve, the route exists. The carve stays for the whole run
  (Amendment C), so when a walk took the Rogue into the same pocket at 1,312 s, it was stuck
  again.

### 4d. The rest

- **Empty defend scans** (1.20 s per kill over the three causes: 0.73 in fights with no kill yet,
  0.47 after a kill): ring 1 (8 hovers, ~3 s) and, while hits came within 2.5 s, ring 2
  (16 hovers, ~6 s), l. 2361-2363. After a kill the lock is
  cleared (`lock = None` on the Base EXP line), and the quiet-kill exit needs no hit for 2.5 s AND
  the kill < 3 s old (l. 2305). A first scan of ~3 s therefore misses that window, and the fight
  ends only after another empty scan (c7 at 676 s: 12.2 s of empty scans after one kill, then a
  13.9-s loot step with no pickup).
- **Fly Wing settling** (0.55 s per kill): `time.sleep(1.0)` and FLY_SETTLE_S = 2.5 s without a
  position read (Amendment H). It is a safety rule against a stale minimap read.
- **The stall scan** (0.31 s per kill): two clicks from one cell without moving start a ring-1
  scan (l. 2622).

## 5. THE PROPOSAL: the LOOT TRIM (`--loot trim`)

**The change** (one, behind an option that is OFF by default): a new loot mode that is loot v1
with two bounds changed, nothing else:
- `LOOT_MAX_HOVERS` 30 -> **9** for the list (our cell, then ring 1: v1's own nearest-first order);
- **no sweep** (the `changed_cells` sweep after the list is skipped).

Everything else is v1's code path, unchanged: the PICKUP-hand read before every loot click, the
pickup's coded wait, the SWORD -> `strike()` path, `npc_guard_blocks` on loot clicks, guard_tick's
HP reads and escapes, the hit abort (`last_taken < 1.0`), LOOT_MAX_PICKS and LOOT_MAX_S.

**Estimate: +14.1 kills / h** (91.0 -> 105.1) on the brief's pool. How:
1. For every banked loot step, the hovers are timed by its guard reads (one per hover, section 2).
   The trimmed step keeps the first 9 hovers as measured (the order does not change) and any
   pickup made within them with its wait; it drops the rest. A step that never reached 9 hovers
   is unchanged; a step whose fight logged no kill (empty list) makes no hover at all.
2. Pooled: **863.2 s** of the 6,446.5 s are not spent (99 of 132 steps are cut).
   - Where those seconds lay: 528.5 s loot pause, 295.6 s after fight, 19.2 s inside search,
     18.3 s approach-react, 1.5 s loot. **843.3 s (98 %) are idle**: nothing else waited on them.
3. The kills / h follow time_budget's convention (`losses`, `idle_study.gain`): every other second
   per kill held, 3600 / (39.55 - 863.2 / 163) = 105.1. With the idle seconds only: 104.7
   (+13.7).
   - **c8, read after the rule was committed (18:20:57, 760f439):** 308.7 s saved, 0 of 29
     pickups lost, 9 late SWORDs: 81.7 -> 95.3 kills / h (+13.6). All four runs: 1,171.9 s,
     4 of 113 pickups, 23 late SWORDs, 88.7 -> 102.7 (+14.0).
4. The trade-off curve (the same method):

   | hovers kept (no sweep) | saved | pickups lost (of 84) | late SWORDs | kills / h |
   |---|---|---|---|---|
   | 5 | 1,029.0 s | 22 | 26 | 108.3 |
   | **9** | **863.2 s** | **4** | **14** | **105.1** |
   | 12 | 764.6 s | 4 | 13 | 103.3 |
   | 16 | 633.9 s | 4 | 12 | 101.0 |
   | 30 (today's list, no sweep) | 326.0 s | 1 | 11 | 95.9 |
   | 9 per kill of the fight | 632.6 s | 1 | 14 | 100.9 |

   Nine is the knee: below it the losses jump (22 at 5); above it they do not fall.

**What it costs.**
- **4 of 84 pickups (4.8 %)**, all in steps after 2-4 kills, where the drop lay 2-3 cells away
  (ranks 21, 21 and 26 in the list, and one sweep pickup at rank 30). The floor-loot completeness
  falls by about that share (c5b's 90.5 % would read ~86 %, estimate). More kills per hour bring
  more drops and more Snatcher procs (30 of c5b's 49 items, 29 of c6's 65), so items / h should
  not fall; that is a measure for the run, not a claim.
- **14 SWORDs** that the loot hover found after its 9th hover (or in the sweep). Those monsters
  are left to the other triggers (the Battle Log, the HP drop, the Miss cue, the walk's own
  SWORD read). The saved seconds above do not count their strikes.

**Risk to the safety bars: none found.**
- It REMOVES pointer hovers and adds nothing. No new click, no new click path: the loot click still
  needs the PICKUP hand under the pointer, and a strike still needs a SWORD read (the same
  `strike()`).
- The NPC guard (`--npc-guard`) still refuses a loot or strike click within 8 cells of an NPC; the
  zones still keep the list's cells out of the no-enter areas.
- The UI gate types nothing here. The UI watch and the hard bars (NPC contact, map change,
  unknown UI state) are untouched, and the time saved goes back to the same loop that checks them.
- Fewer hovers mean fewer pointer moves over the world, so if anything fewer chances of a stray
  press.
- 4.02's lesson (demonstrations.md): Batt's "rhythm" on orcsdun01 bounded the step at 2.5 s but
  hovered the CHANGED cells first. Its completeness collapsed (18 % against v1's 60 %). TRIM keeps
  v1's distance order, which is where 80 of 84 pickups came from here.

**Pre-registration sketch** (for the parent; nothing is registered here):
- **Arms:** A = today's arm (P2, `--search patrol --walk-trust --npc-guard`, with or without
  `--miss-cue` 9.1b as c8 is judged), `--loot v1`; B = the same + `--loot trim`. Paired,
  alternating order, 36 min each, consecutive seeds, Amendment E's cycle; at least 2 pairs.
- **Primary measure:** kills / h from the packets (time_budget's window and kills). **Bar:**
  B - A >= **+8 kills / h** pooled (about 60 % of the estimate: the convention assumes the freed
  seconds convert like the rest of the cycle).
- **Secondary:** loot-step seconds per kill (prediction: from 8.5 to <= 3.5); the loot pause +
  after-fight idle per kill (prediction: -4 s or more); floor-loot completeness (judge, packets:
  B within 8 points of A); items / h and value / h at OC (not lower); damage per kill and potions
  + Fly Wings per hour (not more than 10 % higher: the late SWORDs).
- **Hard bars, absolute:** NPC contact 0, map change 0, attacks on non-targets 0, deaths reported;
  the click census and the loot / strike safety tests green before the first run.

## 6. Runner-up changes (estimates; each its own decision)

1. **Longer walk legs, through the waypoint** (the stop-and-go, 4a). The next click must land
   before the path ends, as Batt's does. Route the goal path through the NEXT waypoint (so the
   target is not capped at the current one) and aim 10-14 cells ahead instead of 7. Estimate from
   the 1,679 stops: each shrinks by up to the extra cells x 0.15 s, so **+3 cells -> +8.1,
   +5 -> +11.1, +7 -> +12.5 kills / h**. Risk: longer straight walks; the zone segment check and
   walk-trust's landing cells already cover the line. With TRIM: ~122 kills / h together
   (estimate, the two assumed independent).
2. **The patrol dead end** (4c, a correctness bug): when no waypoint routes from our cell, route
   once without the carves (or un-carve the pocket's exit) before skipping, and fly at once after
   one full lap of skips instead of waiting IDLE_MAX_S. <= +1.4 kills / h pooled (c7 alone:
   62.8 s).
3. **The empty defend scans** (4d): after a kill, skip ring 2 unless a hit came within ~1 s, and
   measure the quiet-kill window from the scan's end, not the kill. <= +1.1 (after a kill)
   and <= +1.7 (fights with no kill) kills / h; with c8, whose Battle-Log engages that found
   nobody add 1.20 s per kill inside search, <= +1.3 and <= +2.1. Those empty scans are partly
   the unanswered attacker (a hit, and nobody on rings 1-2), so the fix there is the defend scan's,
   not a shorter scan.
4. **The UI watch** (>= 0.32 s per kill inside search): read it every 20-30 s, or only when the
   pixels change state. <= +0.8 visible here (a lower bound).
5. Not proposed: Fly Wing settling (<= +1.3) is Amendment H's safety rule against stale minimap
   reads.

## 7. Limits

- **Four runs, one map, one day,** with three variants of the same arm (c6 carries the 9.1 loop).
  The pool is the brief's three; c8 is shown apart (3e) as a check read after the rule was
  committed.
- **Every "kills / h" is an estimate** under time_budget's convention: the removed seconds are taken
  out and every other second per kill is held. Aggressive orcs come to a standing Rogue, so some of
  a long loot step also "waited" for the next monster. The +8 bar in section 5 allows for that.
- **A hover's timing comes from the guard reads,** not from a logged hover time (the runner does
  not log one); 3 of 132 steps had fewer reads than hovers.
- **The walk-decision span starts at the tick's hp_read,** so it includes a UI watch that fell in
  that tick; the split between the two is not exact.
- **Packets are offline truth only.** The proposal reads nothing from them.

## 8. Reproduce

    export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts
    python3 scripts/idle_study.py 20261026T150619-demo-dungeon-rogue-gef_fild10-patrol-P2-c5b \
        20261026T162920-demo-dungeon-rogue-gef_fild10-patrol-P2-c6 \
        20261026T170913-demo-dungeon-rogue-gef_fild10-patrol-P2-c7 \
        [20261026T174709-demo-dungeon-rogue-gef_fild10-patrol-P2-c8] [--json]
    python3 -m pytest -p no:cacheprovider services/backend/tests/test_idle_study.py
