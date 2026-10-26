---
doc_type: measurement
hypothesis: "On gef_fild10 the walk gate's UNKNOWN refusals come from the TIMING of the cursor read (the client draws its rotating WALK arrow at a new pointer point late, above all while the camera scrolls), not from unsafe cells; a walk target the map knowledge already trusts can be clicked on an UNKNOWN read without reopening the NPC, warp or UI risks the gate was built for."
status: "MEASURED (offline) and IMPLEMENTED behind dungeon_hunt --walk-trust, OFF by default. Nothing is pre-registered and nothing ran live."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [gef10-time-budget.md, rogue-gef10.md, gef10-prep.md, ../../scripts/dungeon_hunt.py, ../../scripts/walk_trust.py, ../../scripts/cursor_unknown.py, ../../scripts/cursor_sword.py, ../../config/map_zones/gef_fild10.yaml, ../../config/routes/gef_fild10-batt-loop.json]
next_action: "The parent: pre-register --walk-trust (section 6) as an arm against today's gate and switch it on in that commit; Batt: accept or refuse its one new risk (an UNKNOWN that hid a monster becomes an attack request: 23 of 2,249 targets, about 3 per 36-min run, all on target species). Separately: map_zones.segment_violates passes axis-aligned walks (section 8); waypoint 0 of Batt's loop sits inside the Kafra's no-enter zone (section 7)."
title: "gef_fild10: why the walk cursor reads 'unknown', and the trusted walk cell (--walk-trust)"
date: 2026-10-26
owner: Batt
---

# gef_fild10: why the walk cursor reads "unknown", and the trusted walk cell

**Why.** [gef10-time-budget.md](gef10-time-budget.md) ranks the stop-and-go walk second among the
bot's losses against Batt (22 % of the gap, 14.85 s per kill). The bot walks 8.7 % of its time,
Batt 35.6 %. Most of its walk decisions send no click because the cursor read says "unknown".
This document says **what that read is, why it fails on gef_fild10, what the gate protects, and
what to change**, with numbers. It ends with one fix implemented behind an option that is OFF.

**What this is NOT.** It changes no default behaviour and decides nothing. Every number is
**measured** offline from the runs' events, packets and recordings, unless it says **estimate**.

## 0. The answer in brief

1. **An UNKNOWN read is a timing failure.**
   - The read gives up 0.35 s after the pointer's first motion.
   - 93 % of the unknown reads came while the GM walked (42 %) or within 2 s of the server's
     stop (51 %). Standing for 2 s or more, only 14.7 % of reads are unknown.
   - 92.6 % of the decisions that follow a click read unknown: the next decision comes 1.2 s
     later, while the 7-cell walk is still on screen.
   - So 71 % of all clicks (895 of 1,258) came after the GM had stood for 2 s or more. That is the
     stop-and-go.
2. **What the cursor looked like during those reads** (the recordings' frames at the hover
   point; section 3b):
   - inside the 0.35-s window: **no arrow at the point yet** in 75 % of the frames; an arrow drawn
     but matched by no WALK reference in 22 % (the arrow ROTATES, and its narrow images miss);
   - after the window, the arrow shows up: 0.7 s or more after the first motion, 59 % of the
     frames read CLEAR to the live reader and 68 % to the full WALK set.
3. **The cell itself was rarely the problem.**
   - Every walk target is already on the route grid: the client GAT AND the server map cache,
     minus the warp spans, minus the delegated zones (NPCs and warps grown by 4 cells).
   - No walk target came within 9 cells of an NPC.
   - 23 of the 2,249 unknown targets (1.0 %) had a monster on (3), beside (10) or 2-3 cells in
     front of (10) the cell, by the packets.
   - 61 decisions (1.7 %) showed the no-entry ring's red.
4. **The options** (section 5):

   | option | unknowns turned into clicks (of 2,249) | cost | new risk |
   |---|---|---|---|
   | A. read longer (up to ~1.0 s) | ~1,330-1,760 (59-78 %, estimate) | +0.35-0.65 s per such decision; the loop stops polling HP while it waits | none |
   | B. better WALK references | at most ~495 (22 %, estimate) | a new cut of references and their own validation; the full set is 14x slower | a thinner SWORD margin |
   | **C. trust the cell (implemented)** | **2,190 (97.4 %)**; 58 more become no-entry carves | none (the read stays 0.35 s) | up to 23 attack requests on monsters (1.0 %) |
5. **Implemented: `dungeon_hunt.py run --walk-trust`**, OFF by default. Section 6 lists exactly
   what it does and how it is switched on.
6. **Batt's loop** (82 waypoints): waypoint 0 (76,337) is **3 cells from the Kafra** and inside
   its no-enter zone. Its two legs (81 -> 0 and 0 -> 1) are the only ones within 3 cells of an NPC
   or touching a zone; no A* route reaches waypoint 0 on the route grid. No other waypoint or leg
   comes within 3 cells of an NPC or touches a zone. The orc village's NPCs are 38-40 cells away.

## 1. What was read

- **Runs:** a2, a3, a4, a5b, a6, a7, a8 and b1: the gef_fild10 Rogue runs the brief allows, each a
  36-min time box (a6 rested most of its run: 86 walk decisions).
  - That is 3,510 walk decisions, 1,258 clicked, 2,249 "cursor unknown", 3 "cursor noentry".
  - The time budget's 3,807 / 2,437 counted a different set of 8 (with a9 and a11, without a6
    and b1). The share is the same: 64.1 % here, 64 % there.
- **Not read:** a9, a10, a11 and any w3. They are the detector's TEST2 (gef10-eval.md amendment
  R2). `cursor_unknown.py` refuses them by name, events and recordings alike.
- **Events:** each run's `events.jsonl`. A walk event logs only from, to, clicked, why, and the red
  pixel count; it does NOT log the read's recalls or its read count.
- **Packets:** each run's `packets.jsonl.gz`, for our walk (self_move) and the monsters' cells.
  Offline ground truth only.
- **Recordings:** the 1-fps PNG shards of a2-a8 on the NAS and of b1 in /dev/shm/poring-lab-rec.
  - b1's recording covers only its first 10 minutes.
  - Up to 300 decisions per run were sampled (seed 7). Every frame inside a decision's pointer
    rest was read at the hover point.
  - Nothing of these frames was written outside /dev/shm.

## 2. What "cursor unknown" means exactly

The walk decision (`dungeon_hunt.run`, the SEARCH walk):

1. **When.** Every `WALK_EVERY_S` = 1.2 s while there is a goal path. The target is the path cell
   `WALK_AHEAD` = 7 cells ahead that is in view and whose straight segment passes the zones.
2. **Where.** The target cell is projected with the RDP camera and the GAT altitude, from `here`,
   the minimap readout. `here` lags the server by ~0.45-0.5 s.
3. **The read** (`hover` -> `cursor_sword.check`, `wait_s` = `CURSOR_WAIT_S` = 0.35 s):
   - the pointer moves to (u - 3, v - 2), 20 ms, then to (u, v): the two motions the client needs
     before it redraws its cursor;
   - it reads a 64 x 64 crop at (u, v) about every 38 ms (an 8-ms read plus a 30-ms gap) until a
     verdict or 0.35 s after the FIRST motion: about 9 reads;
   - each read is the colour recall against the v3 references: 26 SWORD, 9 PICKUP and a subset
     of 31 WALK prototypes (every 16th of 491; `WALK_SUBSET`), each at +-2 px;
   - verdict per read: SWORD if sword >= 0.75; CLEAR if pickup >= 0.90, or walk >= 0.85 with
     sword < 0.60; else UNKNOWN;
   - over the series: any SWORD wins; else CLEAR once one read is clear; else UNKNOWN.
4. **After the read**, one more crop counts the no-entry ring's red pixels. A CLEAR with red >= 25
   becomes "noentry", is carved off the route grid, and the heading turns.
5. **The decision:** CLEAR -> walk click. SWORD -> strike ("walk_sword"). NOENTRY -> carve.
   UNKNOWN -> no click, the event `why: "cursor unknown"`; the next decision comes 1.2 s later.

The 0.35 s comes from hunt_flow v37 (2026-10-18). There, 3.78 measured the redraw: about
0.2-0.3 s with the GM standing, and **0.35-0.4 s while the camera scrolls**. With the 0.35-s
wait, 75-78 % of moving walk checks ended UNKNOWN. v38 (Batt's decision 2, option a) then kept
the SWORD check on LOOT clicks only, with a 0.6-s wait, and left walk clicks without it.
dungeon@1 (2026-10-22) gated every walk click on a CLEAR read again, with the 0.35-s wait.

## 3. Why the reads are unknown on gef_fild10

### 3a. The events and packets: the GM's motion at the read (all 3,510 decisions)

The read start is the event time minus 0.37 s for an unknown read, or minus 0.15 s for a clicked
one. The motion state at that time comes from our self_move packets (150 ms a cell).

| motion state at the read | decisions | unknown | unknown share | share of all unknowns |
|---|---|---|---|---|
| moving (the server walk under way) | 1,146 | 950 | 82.9 % | 42.2 % |
| stopped < 1 s ago | 770 | 754 | **97.9 %** | 33.5 % |
| stopped 1-2 s ago | 532 | 389 | 73.1 % | 17.3 % |
| stood >= 2 s | 1,051 | 154 | 14.7 % | 6.8 % |
| before any walk | 11 | 2 | | 0.1 % |

| seconds since the server stop (not moving) | 0 | 1 | 2 | 3 | 4 | 5 | 6+ |
|---|---|---|---|---|---|---|---|
| unknown share | 97.9 % | 73.1 % | 17.1 % | 7.3 % | 6.9 % | 0 % | 25.0 % |

- The frames show the GM ~0.45 s behind the server, so "stopped < 1 s" is mostly still scrolling
  on screen.
- **The rhythm locks the bot into it.** After a click, the next decision comes 1.2 s later; a
  7-cell walk lasts 1.05-1.5 s. So 1,159 of the 1,251 decisions after a click (92.6 %) read
  unknown. After an unknown, 1,089 of 2,248 (48.4 %) read unknown again.
- Hence 895 of the 1,258 clicks (71 %) came after the GM had stood for 2 s or more.
- The 6+ s bucket (42 of 168) holds the decisions right after fights and rests.

### 3b. The frames: what the cursor looked like at the hover point

`cursor_unknown.py frames`: 1,453 frames of UNKNOWN decisions (up to 300 decisions a run; seed 7).
Each frame lies between the read's start and the pointer's next action, so the pointer rests at
the hover point in it. The cause per frame is the module's definition.

| frames after the read start | n | no arrow at the point | partial (< 0.85, full set too) | narrow (full set only) | wide (live: CLEAR) | no-entry ring | other |
|---|---|---|---|---|---|---|---|
| 0-0.37 s (inside the live read) | 393 | **75.6 %** | **21.1 %** | 0.5 % | 1.0 % | 1.3 % | 0.5 % (arrow off the point) |
| 0.37-0.70 s | 318 | 52.5 % | 16.7 % | 3.8 % | 23.9 % | 2.5 % | 0.6 % |
| 0.70 s and later | 742 | 16.2 % | 10.4 % | 9.0 % | **59.0 %** | 5.0 % | 0.4 % (SWORD) |

Inside the read, by motion state: moving 61.8 % no arrow / 37.0 % partial (n = 165); stopped
< 1 s 89.8 % / 7.1 % (127); stopped 1-2 s 88.9 % / 7.9 % (63); stood >= 2 s 64.9 % / 21.6 %
(37), where 8.1 % were already wide.

The CLEAR share of single frames, by time since the read start:

| s after the read start | 0-0.2 | 0.2-0.37 | 0.37-0.5 | 0.5-0.7 | 0.7-0.9 | 0.9-1.2 | 1.2+ |
|---|---|---|---|---|---|---|---|
| frames | 217 | 176 | 119 | 199 | 207 | 289 | 246 |
| live reader CLEAR | 1 % | 1 % | 8 % | 33 % | 57 % | 61 % | 59 % |
| full WALK set CLEAR | 2 % | 1 % | 11 % | 38 % | 66 % | 74 % | 63 % |

How to read it:
- **no arrow:** the cursor is not drawn at the point. On a contact sheet of the window's frames
  (in /dev/shm only, 12 frames) the arrow was still drawn where the pointer had been before (up to
  ~45 px away inside the 96-px crop, or outside it), and a few were drawn at the point in a thin
  rotation image. This is the redraw lag.
- **partial / narrow arrow:** the arrow is drawn at the point, in one of its ROTATION images
  (cursors.act action 0 cycles six images, one edge-on). The live reader's 31 WALK prototypes
  match only the wide images. The full set (491) adds the "narrow" ones; "partial" stays below
  0.85 even for the full set.
- **wide arrow:** what the live reader reads CLEAR.
- **noentry ring:** red >= 25 in the crop. After the window it rises to 11 % of the frames while
  the GM moves: the pointer stays put while the world scrolls under it, so it ends up over other
  cells (trees, cliffs). It says little about the target cell itself.
- Monsters (a SWORD) appear in 3 of the 742 late frames.

**The split of the 2,249 unknowns by cause:**

| cause | evidence | share |
|---|---|---|
| the read ended before the client drew the arrow at the point (redraw lag, mostly in motion) | 75 % of the window's frames show no arrow at the point; 93 % of the unknowns within 2 s of a move | **~75 %** |
| the arrow drawn in a rotation image the reader does not match | 22 % of the window's frames: partial or narrow | **~22 %** |
| the no-entry ring (the client says the cell is not walkable) | 58 unknown reads with red >= 25 in the crop (2.6 %); 1 % of the window's frames | ~2.6 % |
| a monster under the pointer | 23 targets with a monster on, beside or in front (1.0 %, packets) | ~1 % |
| UI or an NPC under the pointer | none: in_view keeps the point off the UI windows, and no target came within 9 cells of an NPC | 0 |
| grass or tree texture | not separable: the arrow is drawn ON TOP, and the colour recall reads only the cursor's own pixels; the wide arrow read 0.93-0.99 over grass, dirt and canopy alike | not a cause found |

The window's frames are a sample of 1-fps frames that happened to fall inside the 0.35-s reads,
so the first two shares are estimates with a few-points margin, not counts. The rows mix that
frame sample with event and packet counts and overlap; they do not add up to 100 %.

## 4. What the walk gate protects against, and which of those risks exist here

**Where it came from.**
- Batt's decision 6 (2026-10-08): every non-rule world click passes a cursor gate. where@2's
  blind harness click had attacked field monsters and contacted NPCs.
- hunt_flow v37 (3.76-3.77): on prt_fild06, 5 of 29 non-target attack requests came from walk
  clicks. The cursor's SWORD was added at walk and loot points; 75-78 % of the moving walk checks
  then ended UNKNOWN (3.78). v38 (Batt's decision 2, option a) kept it at loot points only.
- dungeon@1 (cb3ab8f): every walk click needs a CLEAR read. Pilot 3 (dc85d4c) added the ring's
  red after 4 clicks on a cliff sent no request.

**The risks, against gef_fild10's walking:**

| risk | what already guards it on gef_fild10 | left for the cursor |
|---|---|---|
| an NPC contact (a hard bar) | 5 dialog NPCs, no touch area; each inside a no-enter zone grown by 4; the route grid and every walk segment avoid the zones; no target came within 9 cells of an NPC | nothing measured |
| a warp (a map change, a hard bar) | 9 spans grown by 4 in the zones; stand_grid removes spans and touch areas; the search area keeps 10 cells off | nothing measured |
| a UI click | in_view refuses points over the static UI windows | nothing |
| a non-walkable cell | the route grid is the client GAT AND the server map cache | the no-entry ring: 61 decisions (1.7 %); its click would only stall |
| attacking a monster | none but the cursor | 23 of 2,249 unknown targets (1.0 %). Every normal species here is a target; the Orc Lord is kept off scored runs by the @killmonster2 schedule (rogue-gef10.md Amendment E), and a SWORD read on it is engaged today anyway |

So on gef_fild10 the cursor read on a walk click guards two things: the no-entry ring (now a
stall) and an unplanned attack on a target-species monster. Only 5 walk decisions in the 8 runs
read SWORD and engaged ("walk_sword").

## 5. The options, with numbers

**A. Read longer.** Keep failing closed, but let the walk read run up to W s (early stop at the
first CLEAR).
- From the frames (estimate): the single-frame CLEAR share is a LOWER bound for a read series,
  and the share with an arrow at the point (wide + narrow + partial) is an UPPER bound.
  - W = 0.7 s: 24-44 % of the unknowns (540-1,000);
  - W = 1.0 s: 59-78 % (1,330-1,760).
- Cost: +0.35-0.65 s per converted decision. The loop does not read HP or the battle log while
  the pointer waits, so the reaction to a hit (already 5.5 s per kill of the gap) gets slower.
- Risk: none new.

**B. Better WALK references.** The rotation images that miss.
- The full WALK set adds the "narrow" frames: 0.5 % in the window, 4-9 % later. The "partial"
  21 % in the window would need new references cut on gef_fild10 (client pixels in data/, never
  committed).
- At most ~495 of the unknowns (22 %), and only those already drawn at the point within 0.35 s.
- Cost: the full set takes 105 ms a read (the subset 7 ms), so a 0.35-s window gets 3 reads. A
  curated set would need its own leave-one-out. SWORD_MIN's margin is only ~0.04 each side, so
  more WALK prototypes risk a thinner SWORD separation.

**C. Trust the cell (implemented, section 6).** On an UNKNOWN read, click when the map knowledge
trusts the cell.
- Offline, on the 2,249 unknowns (`cursor_unknown.py events`):
  - **2,190 clicked (97.4 %)**;
  - 58 carved as no-entry, because the ring's red was in the crop (2.6 %);
  - 1 refused: a landing cell within 6 of an NPC.
  - Carving is not replayed and the box watcher is not known offline. Both make the live trust
    stricter than this.
- Cost: none. The read stays 0.35 s.
- Risk:
  - **attack requests on monsters:** at most 23 over the 8 runs (3 on the cell, 10 beside it,
    10 in front of it), about 3 per 36-min run. All are on target species. A fresh detector box
    near the point refuses the trust, which can only lower the count;
  - **wasted clicks on no-entry cells** the ring did not show in time: the stall rule (2 clicks
    without moving: turn, carve, scan ring 1) handles them, as now;
  - NPCs and warps: no new risk (section 4, plus the landing cells and the NPC distance).
- **The walk rhythm (estimate).** Every decision would click. The clicks would come every
  ~1.2-1.6 s instead of 3.9 s (median), against a 7-cell walk of 1.05-1.5 s, so the search walk
  becomes nearly continuous. Batt clicks every 2.1 s. The time it can win back is the "idle inside
  search": 14.85 s per kill of the gap, 3,246 s over the time budget's 8 runs. How much of it turns
  into kills is NOT estimated here: walking more meets more monsters, but the time budget's causes
  are not independent. That is a run's job.

**D. No read at all on a trusted cell.** It saves the 0.35 s, but it loses the SWORD engagement
(5 in the 8 runs) and the ring's red (61 decisions). Not recommended.

**Why C.** It converts nearly all the refusals at no time cost. It keeps every decision the
reader can make within its window (SWORD engages, the ring carves). Its one new risk is small and
falls on target species. A and B keep the failure-closed rule, but they convert fewer clicks,
and A slows the loop.

## 6. The implemented option: `--walk-trust`

**Code:** `scripts/walk_trust.py` holds the pure functions; `scripts/dungeon_hunt.py` wires them.

- **Off by default:** `dungeon_hunt.py run ... --walk-trust` switches it on, and
  `--no-walk-trust` is the default. run_start's and the manifest's `fixes` record `walk_trust`.
  With it off, `walk_trust.decide` returns exactly the old gate for every verdict; a test pins
  this.
- **What changes when it is on:** only a read that ends UNKNOWN.
  1. When the crop holds the ring's red (red >= `NOENTRY_RED` = 25), it is a no-entry: carve, no
     click (`why: "cursor unknown + red"`).
  2. Otherwise `walk_trust.trust_why(here, target, ...)` decides. It refuses, in this order:
     - `box`: a fresh detector box's foot within 60 px of the point (when the box watcher runs);
     - `off_grid`: the target is off the map, off the route grid, or carved. The route grid is
       the client GAT AND the server map cache, minus warp spans and touch areas, minus the zones;
     - `no_enter`: a straight walk from `here` to the target or to one of the up to 4 LANDING
       cells beyond it (a click sent while the GM moves lands up to ~3 cells further along) meets
       a no-cross line or enters a no-enter area. The landing cells stop at the first wall;
     - `npc`: a landing cell within 6 cells (Chebyshev) of any L3 script NPC.
  3. A trusted UNKNOWN is clicked through the same `click_at`. Its walk event gets
     `"gate": "trusted"`, and `counts.walk_trusted` counts it.
  4. Refusals log `"trust": <why>`.
- **Fail closed:** `--walk-trust` refuses to start unless `data/kb/npc_cells.json` lists the map
  as complete.
- **Unchanged:** SWORD -> strike; a CLEAR with red -> carve; the stall rule; the hover itself
  (0.35 s, two motions); every other click.
- **Tests:**
  - `services/backend/tests/test_walk_trust.py`: synthetic grids and zones, the landing cells, the
    decision table with the option off and on, the runner's flag defaulting to False;
  - `services/backend/tests/test_cursor_unknown.py`: the measurement's pure parts;
  - the click census: the count is unchanged, its reason now names the option;
  - the dungeon_hunt, map_zones, cursor_sword and time_budget tests still pass.
- **How the parent switches it on:** pre-register the arm (for example `--walk-trust` against
  today's gate, interleaved by run), then add `--walk-trust` to the run lines in that commit.
  - Primary counts: walk clicks per minute, the share of time walking, kills per hour.
  - Safety counts from the packets: attack requests not preceded by a strike, NPC contacts, map
    changes.
  - Each run's `fixes.walk_trust` (run_start and the manifest) names its arm. The judges do not
    read `fixes` yet, and trusted clicks are marked `"gate": "trusted"` in the events.

## 7. Batt's loop against the NPCs and the delegated zones

`cursor_unknown.py loop`: config/routes/gef_fild10-batt-loop.json (82 waypoints) against L3's 5
NPCs and config/map_zones/gef_fild10.yaml.

| check | result |
|---|---|
| waypoints within 3 cells of an NPC | **1: waypoint 0 (76,337)**, 3 cells from the Kafra (73,340), 7 from the board (69,340) |
| waypoints inside a no-enter zone | **1: waypoint 0**, inside npc-kafra-73-340 (x 69-77, y 336-344); off the route grid |
| waypoints off the search area | 2: waypoint 0, and waypoint 81 (71,327), which is on the route grid |
| legs within 3 cells of an NPC (straight or A*) | **2: 81 -> 0 and 0 -> 1** (the Kafra, 3 cells) |
| legs touching a no-enter zone | the same 2 (npc-kafra-73-340); no A* route reaches waypoint 0 on the route grid |
| legs with non-walkable cells on the straight line | 7 (1-5 cells each); A* on the route grid goes round them |
| closest approach to the other NPCs | board (69,340): 6 cells; Orc's Memory (238/242,202): 38-40 cells; board (109,23): 55 cells |
| closest approach to the door and warp zones | 4 cells outside door-in_orcs01-136-331 and door-in_orcs01-63-337; 2 cells outside npc-board-69-340 |

- **So:** one waypoint needs moving before a runner may walk the loop. Waypoint 0 is where Batt
  started, beside the Kafra.
  - A runner joining or closing the loop there would aim inside the Kafra's zone; dungeon_hunt
    refuses such a waypoint today ("not on the route grid").
  - Moving it out of the zone fixes both legs. For example (80,333): on the route grid, outside
    every zone, 7 cells from the Kafra, with A* routes from waypoint 81 (10 cells) and to
    waypoint 1 (9 cells). That is Batt's review (the routes README), not done here.

## 8. A finding outside the brief: `map_zones.segment_violates` and axis-aligned walks

- `segment_violates(a, b, zones)` checks the cells whose OPEN interior the straight walk crosses
  (`supercover(closed=False)`).
- For a horizontal or vertical segment that list is EMPTY. `_box_hit`'s strict interval test
  fails on the degenerate axis.
- So **a straight east-west or north-south walk through a no-enter area is not refused.**
  Checked: (20,30) -> (40,30) across a 9 x 9 area returns None. A diagonal through it returns
  "no_enter".
- **Impact today (estimate): none found for dungeon_hunt's walk.**
  - Its targets lie on the zoned route grid, 7 path cells ahead.
  - The smallest no-enter area is 9 cells across, so an axis-aligned line from outside to outside
    through it needs 10+ cells.
  - Other callers (hunt_flow, longer straight walks) were not audited.
- `walk_trust.trust_why` does not rely on it: it also checks the CLOSED supercover's cells.
- **Not fixed here.** A fix changes the default behaviour of every zone check, so it needs its own
  commit and its own tests.

## 9. Limits

- **The read's own recalls are not logged.** The split joins the events (every decision) to
  1-fps frames (a sample). The frames show the cursor near, not at, the read's instants.
- **The read start is reconstructed** from the event time (0.37 s / 0.15 s back). A clicked read
  that decided early is placed up to ~0.2 s too late.
- **The monster check uses packet cells.** A monster's drawn body can cover a point it does not
  stand on. The "front" class (2-3 cells south) approximates that; large sprites may reach
  further.
- **C's gain in kills is not estimated.** The time budget's causes interact; only a run shows it.
- **The no-entry share** of a trusted click's cell after the 0.35-s window is not known for the
  cell itself. The late frames' 5 % mixes in cells the scrolling world brought under the pointer.

## 10. Reproduce

    export PYTHONPATH=scripts:packages/poring_dataset/src:packages/poring_env/src:packages/poring_packets/src
    python3 scripts/cursor_unknown.py events a2 a3 a4 a5b a6 a7 a8 b1
    python3 scripts/cursor_unknown.py frames a2 a3 a4 a5b a6 a7 a8 b1 --per-run 300   # ~15 min, NAS reads
    python3 scripts/cursor_unknown.py loop
    # from a worktree: add --data-root /home/batt/docker/poring-lab before the command
