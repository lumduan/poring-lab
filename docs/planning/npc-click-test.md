---
title: "walk@17 item 5: the NPC-click targeted test (analysis, design, the L3 no-click layer)"
status: PROPOSED
date: 2026-10-09
owner: Batt
extends: docs/demonstrations.md
gate: "Analysis and design only, offline. Nothing here was run live. The DRAFT pre-registration (section 6) is for the parent to review and paste into demonstrations.md 3.32 before any run. The L3 no-click layer is built and tested but NOT integrated: walk17.py is untouched; integrating it is a recorded amendment to 3.32 (section 4). Fixes named in section 5.7 are NOT part of this work."
---

# walk@17 item 5: the NPC-click targeted test

**Batt's decisions (verbatim):**
- (~15:20) "b. walk@17: item 5 (town NPC contacts) gets a targeted test first (dense-NPC town spots,
  deliberate clicks near NPCs, measure cursor + detector + remembered talk cells, find why the
  cells were one column off)"
- (~15:50) "The intermittent 'unknown' cursor reads over Garnet (shape IoU 0.86-0.89 but the colour
  check fails) matter for talk@1: an NPC click requires a TALK read. Include it in item 5's
  targeted test: measure the TALK read rate per NPC/position/background and find why the colour
  check fails, before talk@1's scored trials."
- (~16:10) "The detector does NOT box the town NPCs at all: the city guide right next to the GM, the
  NPCs around the fountain. v0/v1 never trained on town NPC sprites. This likely EXPLAINS walk@15's
  two town NPC contacts ('0 units in the envelope': the detector was blind, not the gate wrong).
  Feed this into item 5: measure detector recall on town NPCs against packet truth (NPC positions
  from the session's packets), per NPC sprite; and per the walk-ready rule, a map is not walk-ready
  while its NPC sprites are outside the detector's training scope. Bank these frames for the next
  training round (NPC class from packets)."
- (~16:15) "Insight from Batt's question ('how does the bot talk to an NPC it can't see?'): talk@1
  finds NPCs from L3 (static NPC cells from the server scripts, allowed by ADR-0015) + the camera
  model, and the client confirms with the TALK cursor; the detector isn't involved. walk@15 avoided
  NPCs with the detector (blind to town NPCs) and remembered TALK cells (one column off). For
  walk@17 item 5: add the L3 NPC cells (and their neighbours, per the clickable footprint) as
  static NO-CLICK cells in the walk gate, independent of the detector. Keep the cursor and detector
  layers for moving/hidden NPCs and units. Measure in the targeted town test whether this alone
  removes the town NPC contacts."

NPCs are named here by job id, cell or L3 key only. Their names and menu texts come from rAthena
(GPL) and stay in the local L3 data.

## 0. At a glance

| question | answer (offline, 2026-10-09) | status |
|---|---|---|
| a. Why were the remembered talk cells "one column off"? | walk@12's memory stores the FLOOR cell under the TALK pixel, which by construction is the click target, never the NPC's cell. A sprite covers floor cells behind it and beside it. In route 55 TWO NPCs answered: the job-722 guild flag at (155,190), whose true cell IS in the remembered column, and the city guide at (154,187) | **cause found** (24 / 24 TALK reads reproduced offline; 2 / 24 remembered cells are an NPC's cell) |
| b. Contact 1: what is job 722, why WALK? | prontera's guild flag (rAthena's guild-flag sprite class), one of 5 in the town centre, from an NPC file the L3 KB does not cover. It is drawn: a ~95 × 150 px banner. The click landed on its right edge. The cursor read WALK and the marker was drawn, so at hover time the CLIENT saw floor there; at click time (0.3-0.6 s later) its hit test found the flag | **what: found. Why WALK: not determined offline** (hypotheses H-a..H-c, separated by the test) |
| c. Why does the colour check fail at IoU 0.86-0.89? | "col 0.0" is a PLACEHOLDER: walk6 reports 0.0 for every unknown, so the real colour is unknown. A ONE-pixel shift of a TALK reference reproduces the live signature exactly (best IoU 0.885-0.91, colour 0.73-0.76, 71-72 / 72 read unknown). A soft codec pass or per-channel noise ~30 also fails the colour at full IoU | **mechanism shown, cause not determined** (needs crops: section 5) |
| d. Detector recall on town NPCs | **1 / 2,195** NPC sightings boxed (Wilson 95 % 0.01-0.26 %); 1 of 13 distinct NPCs ever boxed (the guide, once, as "monster 0.33"). Both contact NPCs: flag 0 / 356, guide 1 / 359 | **Batt's statement confirmed** |
| e. Would the L3 no-click layer alone have refused the two contact clicks? | With the L3 KB as it is today: contact 2 YES, contact 1 NO (the flags are not in L3). With a COMPLETE L3 list: BOTH. Cost on the 50 scored routes: 10 clicks in 6 routes refused (complete) | **built, PROVISIONAL footprint** |

## 1. Analysis a: the remembered talk cells

**The code path (walk@12's click step, unchanged through walk@15 and walk@17):**
1. `zone_points` gives the target cell's tier-A pick-safe pixels: pixels that the picking model
   (`poring_dataset.picking`) puts IN the target cell.
2. Each point is hovered and read. On a TALK read, `picked_cells(w, queue[i:])` runs the picking
   model on the remaining points and `talk_cells.append(picks[i])`.
3. The step logs `talk_cells` as `w.position + pick`. walk@13's route loop adds them to its `talk`
   set; `npc_substitute` then picks a cell 1-2 from the goal "not next to any TALK cell".

So a remembered talk cell is **the floor cell under the TALK pixel**. Since the pixel was chosen to
pick the target cell, the remembered cell is the TARGET cell itself, every time. It is not where the
NPC stands: an NPC's sprite stands on its own cell and covers pixels of cells BEHIND it (up-screen,
+y outdoors) and beside it.

**Reproduced offline** (`npc_click_score.py remembered`, the session's camera + GAT):
- 24 / 24 TALK reads of the town re-run (20261009T140625) give exactly the logged cell. The
  projection and the cell rounding are not the cause.
- Only 2 / 24 remembered cells are an NPC's true cell (packets). The offsets (remembered minus the
  NPC's cell, the NPC whose provisional footprint holds the pixel): (1,0) 4, (0,1) 3, (0,2) 3,
  (1,1) 3, (−1,1) 2, (−1,−1) 2, (0,−1) 2, (0,0) 2, (−1,2) 1, (1,−1) 1, (1,2) 1.

**Route 55, step by step** (from (155,185), then (155,186); goal (155,191)):

| TALK pixel | remembered cell | nearest NPC (packets) | pixel offset from its projected feet |
|---|---|---|---|
| (635.5, 247.8) | (155,190) | job-722 flag at (155,190) | (−5, +1): its feet |
| (635.9, 224.4) | (155,191) | flag (155,190) | (−5, −22): its body |
| (635.1, 269.6) | (155,189) | flag (155,190) / guide (154,187) | (−5, +22) below the flag's feet, or (+28, −45) on the guide |
| (634.8, 291.8) | (155,188) | guide (154,187) | (+28, −23) |
| (634.4, 314.4) | (155,187) | guide (154,187) | (+27, 0) |

- The column x = 155 is the FLAG's column. The flag (job 722, an NPC walk@15 never saw: 0 boxes) has
  its true cell (155,190) inside the remembered set. The "one column off the guide" reading assumed
  every TALK read came from the guide.
- The reads 0-45 px above the guide's feet, 27-28 px right of them, are on the guide (or on a hit
  area wider than its ~40 px drawn sprite).
- The substitute (153,189) is two columns from x = 155, so "not next to any TALK cell" allowed it.
  It is Chebyshev 2 from both NPCs. Its click pixel (568.3, 291.9) was 39 px LEFT of the guide's
  projected feet and 46 px above them. The cursor read WALK there (IoU 0.615) and the server got
  `npc_contact` with the guide 0.16 s after the click.
- Caveat: the camera model's own error is about 10-20 px (outdoor fit). The offsets above carry it.

**Cause:** the memory's semantics. "The floor cell under a TALK pixel" is the cell the click would
have walked to, not the NPC's cell. With two NPCs side by side (flag + guide), the remembered column
belonged to the flag, and the substitute rule measured its distance from the wrong cells.

## 2. Analysis b: contact 1 and job 722

- **What it is:** job 722 is rAthena's guild-flag sprite class. Prontera's centre has five of them
  (cells (143,203), (146,194), (155,190), (165,194), (167,203); the packets of 20261009T140625).
  They come from the guild-castle files (`npc/guild/prtg_cas0*.txt`, the town-flag lines), which
  `kb_route.py` does not read. So **L3 as of 2026-10-09 does not know them**.
- **Is it drawn? Yes.** Snapshot 048-route-before (route 48's start, the GM on (161,192)) shows the
  banner on a stand, about 95 × 150 px, its base at the projected feet (433, 411).
- **The click:** (464.9, 360.9), 32 px right of the projected feet and 50 px above them: the
  banner's right edge / its stand. The cursor read WALK twice (IoU 0.807, re-check WALK), the walk
  marker was drawn (63 px), the envelope held 0 units. The server got `npc_contact` 0.17 s after the click and
  sent `npc_close` 0.35 ms later, with no `npc_say`: no window opened. No `self_move_request`
  followed: the client sent the contact INSTEAD of a move.
- **Why WALK there (not determined offline):**
  - H-a: the client hit-tests the sprite's CURRENT animation frame per pixel. Over the flag at
    (165,194) the reads are patchy, as for an animated banner: WALK at (11,−55), (−5,−51) and
    (3,−51) px from its feet, TALK at (11,−47) and (28,−44). A pixel at the banner's edge can be
    floor at hover time and cloth at click time.
  - H-b: the client re-evaluates its cursor only on mouse motion (the second motion of the hover);
    the click is tested at click time, 0.3-0.6 s later (the re-check read + the unit gate's
    detection).
  - H-c: the click hit area differs from the hover area (e.g. a bounding box for the click, pixels
    for the cursor).
  - The test separates them: the hover TALK map over time (6 grabs + 2 hovers per point) against
    the click contact map at the same points (section 5).
- **Why the detector did not help:** it never boxed any of the five flags (0 / 1,185 sightings).

## 3. Analysis c: the colour check

**What "col 0.0" means.** `walk6.CursorRefs.match` tries the references in IoU order, from the best
down to IoU 0.6. A reference passes when its colour agreement (the share of overlap pixels whose
largest channel difference is < 40) is ≥ 0.85. When none passes it returns `{"shape": "unknown",
"why": "no_match", "iou": <the top IoU>, "col": 0.0}`. **The 0.0 is a constant.** "IoU 0.86-0.89,
col 0.0" means: the shape matched some reference at 0.86-0.89, and every reference with IoU ≥ 0.6
had colour < 0.85. The real colour (0.84 or 0.10) was not measured. `cursor_diag.explain` and
`npc_click_score.explain` report it.

**The margins are thin.** On the 72 filled-bubble references (cut 2026-10-08 over 11 church NPCs,
leave-one-out, `npc_click_score.py refs-shift`):
- 65 / 72 read TALK; the best other reference's colour: median 0.929, minimum among the passes 0.851.
  The gate's floor is 0.85.
- The 7 misses are SHAPE misses (best IoU 0.13-0.585 < 0.6). None is a colour miss.
- 56 / 72 bubbles sit in the same bounding box (14,18)-(43,39) of the 64 × 64 crop: the cut was well
  registered.
- The 15:33 feet read that PASSED had IoU 0.90, colour 0.85: at the edge already.

**A 1-px misregistration reproduces the live signature** (each reference shifted, matched against
all the others):

| shift (dx, dy) px | read TALK | best IoU (median) | its colour (median) |
|---|---|---|---|
| 0, 0 | 65 / 72 | 0.973 | 0.929 |
| 1, 0 | 1 / 72 | 0.909 | 0.756 |
| −1, 0 | 1 / 72 | 0.910 | 0.738 |
| 0, ±1 | 0 / 72 | 0.885 | 0.726 |
| 1, 1 | 0 / 72 | 0.851 | 0.693 |
| 2, 0 | 0 / 72 | 0.839 | 0.702 |

The bubble has a 1-2 px black outline on a white fill with grey dots. A one-pixel offset puts outline
pixels on fill and fill on outline, so the colour fails while the shape still overlaps at about 0.89.

**Competing mechanisms with the same summary numbers** (scratch simulation on the same references):
a 3 × 3 blur of the observed bubble (mask kept) reads 0 / 72 TALK at IoU 0.973, colour 0.65;
per-channel noise of sd 20 still reads 64 / 72, sd 30 reads 0 / 72 (colour 0.63). A real codec pass
also moves the mask edge, so it lowers the IoU too.

**A correlate in the banked runs** (the target reads of every walk session, `demo.jsonl`):

| maps | sessions | TALK IoU median | WALK IoU median | unknown share |
|---|---|---|---|---|
| tuning (prt_church, prt_fild08), 10-08 08:49 - 10-09 11:11 | 27 | 0.969-0.988 | 0.836-0.900 | 2-15 % (20 % and 26 % in two calibration runs) |
| held-out (alberta_in, prontera, iz_dun00), 10-09 12:01-14:38 | 5 | 0.748, 0.809 (prontera) | 0.754-0.812 | 7-44 % |

- Held-out reads are worse on every map, light floor (prontera) and dark (iz_dun00) alike. The 15:33
  Garnet failures are on prt_church, a tuning map, after noon.
- No capture change was found: RDP_GFX = progressive, and the xfreerdp process has run since
  10-07 (no reconnect). The refs were cut BEFORE the RDP frame bus went live (10-08 17:45); the
  tuning-map reads after it stayed good. So the bus alone does not explain it.
- **Not separable offline:** maps and time of day are confounded, and no crop of a failing read
  exists (the 15:33 diagnostic printed numbers only).
- The earlier walk@10 "east/north unknown" note was a different failure: filled bubbles read under
  v2 (no filled references), best-matched the PICKUP hand at IoU ~0.64. v3 fixed it.

**Hypotheses the test separates (each probe saves its crops):**

| | hypothesis | its signature in the saved crops |
|---|---|---|
| C1 | misregistration ≥ 1 px (a bob in the bubble's animation, or the capture path) | an integer shift ≤ 2 px restores TALK (`best_shift`); a bob flips with the dots' phase, a capture offset persists over the 6 grabs and shows on the WALK control too |
| C2 | a soft codec pass (RDP progressive's first pass, worse under scene animation: the flags, the fountain) | blurred references restore TALK (`blur_restores`); later grabs of the series pass; worse where the parked pair shows animation |
| C3 | the mask, not the colour: a light fill on a light floor drops fill pixels | IoU drops but the best colour stays ≥ 0.85 (not the 15:33 signature) |
| C4 | an unseen animation frame (dots / phase) | the dot-pixel count of the failing crops is absent from the references |
| C5 | a hover overlay touching the bubble (the NPC's name label) | extra connected pixels outside the reference mask; only near the feet |

## 4. Analysis d + e: the detector, and the L3 no-click layer

### 4.1 Detector recall on town NPCs (Batt ~16:10)

`npc_click_score.py recall`: per detector batch, the NPCs the server showed on screen then (v0
labels: the projected feet at the GM's packet cell, on screen, not behind the UI) and whether any
box (ANY class) sees each (its foot within 40 px of the feet, or the feet inside the box grown by
20 px; each box counts for one NPC, the nearest).

| source | frames | frames with any box | NPC sightings boxed |
|---|---|---|---|
| town re-run, every detector batch (`detections.jsonl`) | 431 | 1 (a "monster 0.33") | 1 / 1,133 |
| town re-run, the 56 route snapshots (detector re-run on CPU) | 56 | 0 | 0 / 138 |
| talk-cal guide drives 15:38, 15:48, 16:03 (frames, CPU) | 132 | 120 (all one box, "monster" 0.30-0.32 at (984-1032, 599-644): the dialog's cut-in illustration, not an NPC) | 0 / 924 |
| **all** | 619 | | **1 / 2,195** (Wilson 95 % 0.0001-0.0026) |

| job | sightings | boxed | Wilson 95 % upper |
|---|---|---|---|
| 722 (5 guild flags) | 1,185 | 0 | 0.32 % |
| 92 | 365 | 0 | 1.0 % |
| 105 (the city guide) | 359 | 1 | 1.6 % |
| 99 | 192 | 0 | 2.0 % |
| 700 | 83 | 0 | 4.4 % |
| 102, 874, 50 | 6, 4, 1 | 0 | — |

- Sightings of one NPC in consecutive frames are not independent. The honest unit: **13 distinct
  NPCs, 1 ever boxed** (the guide, once, as "monster 0.33").
- The contact NPCs: flag (155,190) 0 / 356; guide (154,187) 1 / 359, never at either contact.
- Under 3.28's per-map walk-readiness, extended by Batt (~16:10) to NPC sprites: **prontera is not
  walk-ready** while jobs 722, 105, 92, 99, 700 (at least) are outside the detector's training
  scope.

### 4.2 The L3 no-click layer (Batt ~16:15): built, PROVISIONAL

`scripts/npc_noclick.py`:
- **The NPCs:** L3's static NPC cells for the map: route.json's NPC groups, the bindings' NPC
  positions, and `npc_cells.json` when a KB extension writes it. Hidden classes (111, 139, 32767)
  and the portal effect (45) are dropped. Deduplicated by cell.
- **Coverage:** a map is COMPLETE only when `npc_cells.json` declares it. `for_map(...,
  require_complete=True)` fails closed. On 2026-10-09 no map is complete: prontera's L3 lists 16
  NPCs, but not the 5 flags, job 92 (157,187), job 99 (163,204) nor job 700 (156,212) of the
  centre; prt_church lists 2 of its 10 drawn NPCs (packets of 20261009T034716).
  ➡️ **2026-10-09 ~21:10: superseded by P1 (5.1).** `npc_cells.json` now declares 33 maps
  complete, prontera and prt_church included, with the flags and every drawn NPC.
- **The footprint (PROVISIONAL):** a screen box hung from the NPC's projected feet (the camera +
  the map's GAT at the rule's belief): 60 px left and right, 165 px above, 36 px below. Sized from
  the largest town sprite in the evidence (the flag, ~95 × 150 px drawn; TALK read up to 23 px
  below its feet) + walk@11's 12 px margin. One box for every NPC until the test measures per-job
  footprints (`footprints={"722": Footprint(...)}`).
- **The answers:** `refuse_point(w, u, v)` (the patch point: None, or `{"refused":
  "l3_npc_noclick", "npc": key, "cell", "box"}`), `filter_points`, `cell_refused(w, cell, points)`
  (the NPC's own cell, or every candidate point refused), `near_cells(radius=1)`.

**Replay on the town re-run** (`npc_click_score.py replay-l3`; every hover and click at the rule's
belief; contacts from the packets). "complete" = every drawn NPC the server showed, the design-time
stand-in for a complete L3:

| | L3 as today (16 NPCs) | complete (the 13 drawn NPCs the server showed) |
|---|---|---|
| contact 1 (route 48, cell (156,192), flag) | **not refused** | refused |
| contact 2 (route 55, substitute (153,189), guide) | refused | refused |
| clicks refused (of 154) | 4 | 14 |
| ... in the 50 scored routes | 2 clicks, 2 routes | 10 clicks, **6 routes** (16, 27, 29, 33, 45, 48) |
| hover reads refused (of 173) | 15 | 37 |
| scored goals inside `near_cells` | 0 | 1 (route 33) |

- What the 6 routes would have done instead (another point, a re-plan, a side cell, a decline)
  cannot be replayed without pixels. They are "changed", not "failed".
- **So the layer can remove both contacts only with a COMPLETE L3** (prerequisite P1).

### 4.3 Integration note (for the parent; walk17.py untouched)

The layer slots in where walk@12/13's `zone_points` already removes work-zone and signboard pixels:
1. Build once per run: `layer = npc_noclick.NoClickLayer.for_map(mapname, require_complete=True)`
   (or `False` with the coverage logged, by Batt's choice).
2. In `zone_points(w, end)`: after the work-zone filter, `inside, refused = layer.filter_points(w,
   inside)`; the refused pixels are logged as `l3_refused`, never hovered, never clicked.
3. A cell left with no point returns `no_safe_point` with `"why": "l3_npc_noclick"`. walk@13-15's
   re-plan, side cell and substitute handle it as today.
4. The goal draw, `npc_substitute` and `side_cell` skip `layer.near_cells()`.
5. The cursor gate, the unit gate and the TALK-cell block stay: they cover moving and hidden NPCs,
   players and monsters.
6. It is a change to walk@17's decision code: a recorded amendment to 3.32 and a new bytecode
   proof, before its tuning runs.

## 5. Design of the targeted test

### 5.1 Prerequisites (each proven before any scored data)
- **P1 · a COMPLETE L3 NPC list per test map:** a KB extension writing `data/kb/npc_cells.json` from
  EVERY NPC file the pinned rAthena loads (`npc/scripts_*.conf`, recursively). The spot choice, the
  L3 arm and the layer all need it. Its check: every drawn NPC in the town re-run's packets (13)
  and in a prt_church session's packets is in the list.
  ➡️ **2026-10-09 ~19:30: the list exists, the file does not yet.** `scripts/kb_first_workflow.py`
  (labels-v2-plan.md section 7.3) extracts every NPC of a map from every file the server loads
  (`npc/pre-re/scripts_main.conf`, 522 files); prontera is in its scope and `--also prt_church`
  adds the church. Its packet check over the 85 banked demo sessions: 49 / 49 NPC objects at
  their cell and sprite, prontera 16 and prt_church 19 among them. ~~It does NOT write
  `npc_cells.json` yet, so `npc_noclick.py` still reports no map complete (a follow-up).~~
  ➡️ **2026-10-09 ~21:10: P1 BUILT and CHECKED** (branch feat/labels-v2-prep; local data, never
  committed).
  - **The file:** `kb_first_workflow.py npc-cells --sessions <banked>` writes
    `data/kb/npc_cells.json` for the KB's 33 maps: the first workflow's 30 plus prt_church,
    prt_fild08 and iz_dun00. Each map is declared complete by the build's rule (every loaded file
    parsed, every line naming the map classified, no run-time placement). Each NPC carries its
    file:line, sprite and a DRAWN mark: True, False, or "conditional" (hidden at start).
  - **Hidden NPCs:** `npc_noclick.StaticNpc.drawn` carries the mark. The no-click layer keeps
    every NPC (the safe side). `npc_click_test.make_plan` probes only `drawn is True`; a hidden
    NPC's cell still keeps stands away.
  - **The check** (`packet_check_per_map`): every NPC object the server showed must be in the list
    at its cell with its sprite. An object sent with an invisibility option must not be marked
    drawn, and one sent without it must not be marked hidden. Over the banked demo sessions (78
    with packets):

    | map | objects (matched) | sent invisible | drawn marks disagreeing |
    |---|---|---|---|
    | prontera | 16 (16) | 0 | 0 |
    | prt_church | 19 (19) | 6 (the wedding row, all marked "conditional") | 0 |
    | alberta_in | 6 (6) | 0 | 0 |
    | alberta | 2 (2) | 0 | 0 |
    | izlu2dun | 2 (2) | 0 | 0 |
    | prt_fild08 | 3 (3) | 0 | 0 |
    | iz_dun00 | 1 (1, its portal) | 0 | 0 |

    - **The two sessions this section names:** the town re-run (20261009T140625) gives prontera
      16 / 16 objects, its 13 drawn NPCs included. The prt_church session (20261009T034716) gives
      19 / 19, its 10 drawn NPCs plus the 6 hidden ones, marked.
    - **`npc_noclick.py cells` now reports COMPLETE** for prontera (94 listed, 88 after the
      undrawn classes; the 5 flags included), prt_church (32 / 31), alberta_in and new_1-2.
    - The training grounds have no banked packets: their check is the first collection's.
- **P2 · T2** (`poring_env.npc_dialog`), proven 168 / 168 (3.30): the dialog policy reads it.
- **P3 · the CPU detector** (`/dev/shm/poring-lab-detector`): every probe logs its boxes.
- **P4 · GAT + indoor table extracted** for the test maps (`/dev/shm/poring-lab-tmp/gat/data`).
  izlude has none today: it is out until extracted.

### 5.2 Spots (mechanical, from L3 at run time)
- `npc_click_test.py plan|probe|click --map M --seed S --near X,Y`: the NPCs within 12 cells of the
  pre-registered spot, the 6 with the most other L3 NPCs within 8 cells (ties by cell). Each gets 2
  stand cells 3-5 away (seeded), never beside another NPC, the NPC's sprite fully in view.
- **prontera, spot (156,191)** (the fountain plaza). With a complete list it picks the guide (105),
  job 92, three flags (722) including (155,190), and job 700: both contact NPCs.
- **prt_church, spot (103,74)**: talk@1's `garnet` (103,76) and `henson` (103,71), where the colour
  check failed at 15:32-15:45. The other church sprites are farther than 12 cells. Six NPCs of the
  church's wedding row are sent with an invisibility option (effect_state 2): the client draws
  nothing, so they are not NPCs to probe. P1's list must mark such NPCs; until then the scorer drops
  them by the packets.
- alberta / izlude: when P1 and P4 cover them (not in this round).
- A CONTROL spot per map: plain floor, every L3 NPC ≥ 8 cells away. It gives the WALK-cursor
  registration / colour baseline of that map and time.

### 5.3 The PROBE arm (hover only, nothing clicked)
Per NPC and stand, the points (client px, from the projected feet):
- **sprite:** the vertical line 0, −14 … −112 px; ±17 / ±34 / ±51 px at −14, −42, −70 px; below the
  feet at +12 / +24 px and ±34 px at +12 px;
- **cell:** the tier-A pick-safe point of every cell 1-2 from the NPC and of the 8 ring-3 cells on
  its axes and diagonals.

Each point is hovered **2 times** (2 reps, seeded order, so the repeats are apart in time) after a
fresh park. Each hover records:
- the gate's own verdict (Prober9: the first non-unknown of 3 grabs) and a **timed series of 6
  grabs** 0.1 s apart (animation, codec refinement);
- per grab: shape, IoU, the best reference's class, IoU and **real** colour; the walk marker's
  pixels and components (the cell it names);
- the crops (`crops/NNNNN.npz`: the 6 cursor crops and masks, the parked crop, the animated mask,
  the 120 × 120 context; client pixels, /dev/shm only, never committed);
- the detector's boxes on the parked frame (`detections.jsonl`), one parked full frame per stand
  (`frames/`, for labels v2);
- the L3 layer's verdict at that pixel (recorded, never applied);
- offline: walk@12's remembered cell for a TALK read (the scorer runs the picking model on it).

### 5.4 The CLICK arm (deliberate, WALK-gated)
- Per NPC: every walkable ring-1 cell from BOTH stands, 8 ring-2 and 8 ring-3 cells (seeded, split
  between the stands). Ring 3 reaches past the provisional footprint: those are the clicks the
  layer would ALLOW.
- Before every click the GM is `@warp`ed to its stand (`ro_agent.gm`; the typing guard applies). The
  stands ALTERNATE, so no @warp line repeats (checked when the plan is built). No /where, no filler.
- The click: `cursor_gate.gated_click` at the cell's tier-A work-zone point, only where the cursor
  reads WALK twice. This is the walk rules' own gate. A refused read is recorded, not clicked.
- **The L3 arm is judged OFFLINE:** each click's pixel gets the layer's verdict for both lists
  (L3 as is, complete). The live click always happens. So "with the layer" is the subset the layer
  allows, and "without" is all clicks. Both come from the same clicks.
- The outcome, from the packets offline: `npc_contact` (which NPC, by position) within 1.5 s, else
  `self_move_request`, else nothing.

**The dialog policy after every click (Batt's item 6):**
1. Wait 1.2 s. Read T2 on two fresh frames with the cursor parked.
2. No window on both: go on.
3. A dialog showing **CLOSE** on both, no menu: press **Enter**. Then the windows must be gone on two
   frames (6 tries), else STOP.
4. **Anything else** (NEXT, a menu, an unreadable or disagreeing frame): **STOP FOR A PERSON**. Exit 7,
   the dialog is left as it is, the session is finished with `ended: stopped_for_person:<why>`.
   After Batt closes it, `--resume <session>` continues the same plan from the next click.
- The run refuses to start unless T2 reads no window on two frames.
- Expected stops: a contact with the city guide opens a NEXT dialog. The flags open none (the server
  closes at once). ~~**Question for Batt:** allow talk1's T2-proven decline path (Cancel on the menu,
  then CLOSE) for the three talk@1 NPCs only, instead of a stop? Not built; default is STOP.~~
  ➡️ **DECIDED (Batt 2026-10-09 ~19:30): "item 5 uses talk@1's decline path."**
  - Built as `talk1.decline_all`: NEXT clicked by image, any menu Cancelled unread, CLOSE clicked.
  - A NEXT or menu state now declines instead of stopping.
  - It still STOPS for a person when the decline does not end with the windows gone on two frames,
    or on any unread or unstable state.

### 5.5 Metrics (`npc_click_score.py score`)
- **TALK read rate** (Wilson 95 %) per NPC, per job, per stand (the background), per probe kind and
  offset. The colour-fail rate (unknown with best IoU ≥ 0.6) by the same keys. Its correlates from
  the crops: `best_shift` restores (C1), blurred references restore (C2), a later grab passes, the
  parked pair's animation, the background's brightness under the bubble, the dot count (C4). The
  control spot's WALK reads give the baseline per map.
- **WALK-read-but-contact:** `npc_contact` / clicked, per ring and per NPC. Also the click
  outcomes: contact / move / nothing / not clicked (why).
- **The L3 arms:** contacts refused by the layer (sensitivity); contacts left among the clicks the
  layer allows (the residual risk, with its Wilson upper bound); moves refused (the cost).
- **Detector recall** at those spots, per job and per NPC (section 4.1's method), and the frames to
  bank.
- **The remembered-cell offset:** walk@12's cell for each TALK read minus the NPC's packet cell.
- **The hover vs click maps per job:** P(TALK) and P(contact | WALK twice) by offset from the feet,
  which give the MEASURED footprint (it replaces PROVISIONAL).
- Probes made while the packets put the GM off its stand are excluded and counted.

### 5.6 n, seeds, time
The plan, dry-run OFFLINE with each map's drawn NPCs from the packets standing in for P1's list
(`npc_click_test.py plan` gives the same from L3 once P1 exists):

| | prontera, spot (156,191) | prt_church, spot (103,74) |
|---|---|---|
| NPCs × stands | 6 × 2 (105, 92, 3 × 722, 700) | 2 × 2 (`garnet`, `henson`) |
| probes (2 reps) | 1,504 + 62 control = 1,566 | 504 + 62 control = 566 |
| clicks (ring 1 / 2 / 3) | 176 (86 / 45 / 45) | 52 (20 / 16 / 16) |
| clicks the PROVISIONAL complete layer would allow | 52 | 39 |
| time, at ~2.3 s a probe and ~8 s a click | ~60 + ~23 min | ~22 + ~7 min |

- Per NPC: 124 sprite reads (a TALK rate near 0.9 has a 95 % CI of about ±5 %). Every ring-1 cell
  is clicked twice (once from each stand).
- 0 contacts in prontera's 86 ring-1 clicks would bound that rate below 4.3 % (Wilson 95 % upper);
  0 among the 52 allowed clicks below 6.9 %. The residual-risk bound is weak by design size; a
  second click run would tighten it, if Batt wants.
- **Seeds (fresh, one per map, both arms: the same NPCs and stands):** prontera **20261160**,
  prt_church **20261161**. Pilot (never scored, `--npcs 1 --reps 1`): **20261162**, **20261163**.
- **Total:** about 2 h live, plus the stops for a person. The probe arm can run first and alone (it
  never clicks).
- When: RDP, ASSIST, the interlock green, the GM; not during S2; crops and frames go to /dev/shm.

### 5.7 What result would justify which fix (no fix is part of this work)

| result | justifies |
|---|---|
| the COMPLETE layer refuses every click-arm contact, and 0 contacts among the clicks it allows | adopt the L3 layer in walk@17 (an amendment to 3.32), after P1, with the provisional or the measured footprint |
| contacts among layer-ALLOWED clicks | the footprint is too small for that job: enlarge it to the measured contact map + margin, and re-test |
| the measured contact maps sit well inside PROVISIONAL | tighten per job (fewer refused moves); the cost metric decides |
| P(contact \| WALK twice) > 0 at points the cursor reads WALK on every grab | the cursor gate cannot protect a click near an NPC (the hover and click hit tests differ, H-a..H-c): the static layer is required, not optional |
| remembered cells ≠ the NPC's cell in most TALK reads | replace walk@12's memory: the NPC is the one whose feet lie below the pixel within its footprint, or L3 itself where it is complete |
| `best_shift` restores ≥ 80 % of the colour fails (C1) | a shift-tolerant match (±1 px) in the reader, re-validated leave-one-out with 0 class confusions (a gate change: Batt) |
| blurred references or a later grab restore them (C2) | read until stable (a later grab), or references cut under that scene load; a gate change |
| neither restores them | more references (C4) or a further diagnostic; no change |
| detector recall < 50 % for a job on a map | the map is not walk-ready (3.28 + Batt ~16:10); bank its frames for labels v2 (section 7) |

## 6. DRAFT pre-registration (for 3.32 item 5; NOT pre-registered until the parent pastes it)

> **DRAFT** — the parent reviews, then pastes into docs/demonstrations.md under 3.32 item 5 with its
> commit time, BEFORE any run.
>
> ### 3.32a npc-click@1 — the NPC-click targeted test (walk@17 item 5; pre-registered <time>, BEFORE any run; Batt 2026-10-09 ~15:20, ~15:50, ~16:10, ~16:15)
> **What it measures** (nothing here is a pass / fail of walk@17):
> - where the client shows TALK around town and church NPCs, and how often the TALK read fails the
>   colour check, per NPC / position / background; why, from the saved crops;
> - how often a click the walk gate allows (WALK read twice) beside an NPC becomes `npc_contact`;
> - whether the L3 no-click layer ALONE (complete L3, PROVISIONAL footprint) refuses those contacts,
>   and at what cost;
> - the detector's recall on the same NPCs, and walk@12's remembered TALK cells against packet truth.
>
> **The harness:** `scripts/npc_click_test.py` at <commit> (`probe`, then `click`), scored by
> `scripts/npc_click_score.py score` at the same commit. Spots, points, clicks, the dialog policy
> and the metrics as in `docs/planning/npc-click-test.md` 5.2-5.5.
> - prontera: `--near 156,191 --seed 20261160` (6 NPCs); prt_church: `--near 103,74 --seed 20261161`
>   (its 2 NPCs within 12 cells).
> - Pilot first, never scored: `--npcs 1 --reps 1`, seeds 20261162 / 20261163. Any harness fix is
>   committed before the scored runs.
>
> **Prerequisites:** P1 (a complete L3 NPC list for both maps, checked against their packets), T2
> (3.30, proven), the CPU detector, the GATs.
>
> **The dialog policy:** after every click, two T2 frames. None: go on. CLOSE on both: Enter, then
> gone on two frames. NEXT or a menu: talk@1's decline (`talk1.decline_all`, Batt ~19:30), then gone
> on two frames. Anything else, or a failed decline: STOP for a person (exit 7); `--resume` after
> Batt closes it.
>
> **Decision rule for the layer** (reported, not a walk@17 bar): "the layer alone removes the town
> contacts" when, in prontera's click arm, every `npc_contact` click is refused by the complete layer
> AND no click the layer allows becomes `npc_contact` (reported with the Wilson upper bound of that
> rate and the share of moves the layer refuses).
>
> **Safety:** contacts are the measurement on the lab server. Every opened dialog is closed by the
> policy above or by a person. An `attack_request` or a GM act of kind normal / pickup is a safety
> event: the harness cannot see packets, so each arm is judged offline before the next one runs,
> and any such event ends the test until Batt decides. The GM stands only on known cells
> (`@warp`).
>
> **Reported:** every metric of 5.5 per map, with Wilson intervals; the stops and their causes; the
> measured footprints per job; which fix (5.7) each result points to.

## 7. Labels v2: NPC sprites from packets (a design note for docs/planning/labels-v2.md)
- **The class:** NPC sprites (objtype 6, drawn classes: not 111 / 139 / 32767 / 45) as class `npc`,
  labelled from the packets: each frame's world state at its capture time (`Timeline`), projected
  at the GM's packet cell (the v1 label path; `poring_dataset.labels.labels_for` already emits
  `npc`).
- **The box:** v0's NPC box (34 × 74) is wrong for big sprites (the flag is ~95 × 150 px). Use a
  per-job size: from the NPC's own sprite (the SPR/ACT reader `poring_dataset.sprites`, its sprite
  read from the GRF into /dev/shm at run time, never committed), or measured on banked frames.
  Until then, train flags and similar big sprites only with measured boxes.
- **What to bank (the parent does it):**
  - the town re-run's 56 route snapshots (`20261009T140625…/snapshots`, 138 NPC sightings,
    t_capture_ns in the records);
  - the three guide drives' 132 frames (`20261009T153815`, `…154802`, `…160329`; 924 sightings).
    Their dialog cut-in is boxed "monster ~0.31" in 120 of 132 frames: a HARD NEGATIVE (labels v2
    section 2) when the cut-in mask (another subagent's work) does not already remove it;
  - the targeted test's parked frames (`frames/stand-*`, `frames/click-*`) and its
    `detections.jsonl`.
- **The detections.jsonl of a walk run has no frames:** the 431 batches of the town re-run can be
  scored but not banked. A frame per detector batch would need a harness change (RAM: ~2 MB per PNG).
- **Scope:** add jobs 722, 105, 92, 99, 700 (prontera's centre) and the church's sprites; per 3.28,
  prontera stays not walk-ready until they are in scope.

## 8. What could not be determined offline
- Why the cursor read WALK where the click contacted (H-a / H-b / H-c): it needs the hover map over
  time against the click map at the same points.
- The NPCs' true clickable footprints: the PROVISIONAL box is a guess from 2 contacts and 24 reads,
  with the camera's ~10-20 px error.
- Why the colour check fails (C1-C5): no crop of a failing read exists; maps and time are confounded
  in the banked reads.
- Whether a complete L3 list exists for each map: P1 is not built. Some NPCs may be server-spawned
  (duplicates, events) and need the packets as a check.
- The effect of the layer on route success: the replay counts refused clicks, not the rule's
  alternatives.

## Tools (this branch)
- `scripts/npc_noclick.py`: the L3 no-click layer (`cells --map M` lists a map's L3 NPC keys and
  coverage).
- `scripts/npc_click_test.py`: `plan` (offline), `probe`, `click` (`--near`, `--resume`).
- `scripts/npc_click_score.py`: `score`, `recall [--run-detector]`, `replay-l3`, `remembered`,
  `shift` (crops), `refs-shift` (the references' leave-one-out under shifts).
- Tests: `services/backend/tests/test_npc_noclick.py`, `test_npc_click_score.py`,
  `test_npc_click_test.py`; `test_click_census.py` registers the gated click (GATED).
