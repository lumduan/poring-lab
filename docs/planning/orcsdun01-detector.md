---
doc_type: design
hypothesis: "Warp-and-watch collection plus packet labels give a per-species detector for orcsdun01 that does not forget prt_fild08 (v1's gold set and held-out sessions no worse)."
status: PROPOSED (collection running from 2026-10-21; the class scheme is Batt's default unless he answers; the evaluation is pre-registered in ../benchmarks/v2orc-vs-v1.md BEFORE training)
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [labels-v2-plan.md, training-cost.md, ../benchmarks/v1-vs-v0png.md, ../phase3-plan.md, ../operations/vision-long-lived.md]
next_action: "The label fix (3b) re-run on col1 FAILED C1 pooled (3c: 15.6 % bad_label against < 2 %; 3a was 34.7 %), so per 3b nothing trains and the result goes to Batt. C2 passes (1 / 1 px everywhere). The facing is what is left: after a straight (axis) move the client draws a DIAGONAL view (walk rule 0.4 % on axis moves). The literal 1c rule keeps 283 of 4,343 frames whole. The round-2 blind pack is built, not run (3c)."
title: "orcsdun01 (Orc Dungeon F1): the facts, the collection, the camera check, the class scheme, the labels and the evaluation (plan)"
date: 2026-10-21
owner: Batt
---

# A detector for orcsdun01 (Orc Dungeon F1)

**Batt, 2026-10-21 ~09:1x (verbatim, abridged):** "GPU FREEZE LIFTED (Batt, now). Next big step:
train the detector for a NEW map, ORC DUNGEON F1 (orcsdun01) ... 1. FACTS FIRST (offline) ...
2. COLLECTION WITHOUT WORLD CLICKS ... "warp and watch" ... 3. LABELS from packets offline
(ADR-0007) ... a contact sheet per species checked by two blind labeller agents on a sample before
training, plus a small gold set for this map. 4. CLASS SCHEME (propose; default if I don't answer
by the time labels are ready): PER-SPECIES monster classes ... 5. TRAINING on the GPU ... train on
the combined data (v1's data + the new map) so prt_fild08 isn't forgotten ... 6. EVALUATION,
pre-registered before training ... 7. Then (separate decisions, not today): the GPU detector for
live hunting, and what hunting in a dungeon of AGGRESSIVE monsters needs."

**Batt ~09:3x:** the orcsdun01 work runs IN PARALLEL with the hunting work. The client alternates
blocks: a hunt run, then a ~45-60 min collection block, and so on, never splitting a hunt run.

## 1. The facts (offline, from the pinned rAthena e985006 and the client GRF)

The full record is local only, because it is GPL- and client-derived: `/dev/shm/poring-lab-tmp/orc/FACTS.md`
and its JSON. The summary:

| species (mob id) | Batt's list | the lab server (pinned rAthena) | aggressive | looter | moves |
|---|---|---|---|---|---|
| Orc Zombie (1153) | 10, 3-8 s | **80**: 10 at 3 s + 30 at 60 s + 40 at 120 s | yes | no | 2.5 cells/s |
| Familiar (1005) | 15 | 15, 5 s | yes | no | flies, 6.7 cells/s |
| Steel Chonchon (1042) | 10 | 10, 5 s | **no** | **yes** (+ assist, detector) | flies, 6.7 cells/s |
| Orc Skeleton (1152) | 10, 3-4 min | 10, fixed 180 s | yes | no | 5 cells/s |
| Black Mushroom (1084) | 10, 15-23 min | 10, fixed 900 s, in 2 small areas | no | no | immobile |
| Drainliar (1111) | 5 | 5, 5 s | yes | no | flies, 4 cells/s |
| White Plant (1082) | 5, 3-5 min | 5, fixed 180 s, in 2 small areas | no | no | immobile |

- **Differences from Batt's list:**
  - 135 monsters, not 65: two Orc Zombie spawn lines are missing from the list.
  - The respawns are FIXED on our server (`mob_spawn_variance: 1`). The list's ranges are the
    official variance.
  - Steel Chonchon is a looter, not aggressive.
- **The map:**
  - 200 x 200 cells, 9,356 walkable;
  - client and server agree on every cell, in one connected part;
  - 2 warps and 0 script NPCs;
  - `@warp` is allowed (only `nomemo`);
  - `dynamic_mobs`: the whole population spawns when a player arrives and is removed 300 s after
    the last one leaves.
- **Not indoor:** orcsdun01 is not in the client's indoor table, so the code uses the fitted
  OUTDOOR camera plus the GAT altitude. That is UNMEASURED on this map (section 3).
- **Dark:** the RSW diffuse light is 0.2 / 0.3 / 0.3 (prt_fild08: 1 / 1 / 1), with a dark-green
  fog entry.
- **Familiar and Drainliar share one SPR.** Drainliar differs only by an ACT tint (250, 69, 96).
  Hue augmentation must not cross them, and the light / fog may flatten the tint (the label check
  measures it).
- Three species FLY: Familiar, Drainliar and Steel Chonchon are drawn 38-88 native px above their
  cell. Creamy, the species the old detector missed, flies too.

## 2. The collection: warp and watch (`scripts/warp_watch.py`, 686a4e7)

- **No world click.** Per stand cell: `@warp orcsdun01 x y`, a 2.5-s settle, a 30-s dwell.
  - collect_v2's natural-dwell driver; no `@monster` spawn and no `@killmonster2` (it would also
    kill the slow-respawning natural mobs: 15 min for the Black Mushrooms).
  - Every line goes through ro_agent.gm: the UI gate, the foreground gate and the typing guard
    (each warp line is distinct).
  - The GM is immune (@monsterignore, confirmed for this login).
- **The stands:** a 97-cell lattice, about 11 cells apart (local `lattice.json`).
  - Each stand is a three-check cell: client ∩ server walkable, ≥ 3 cells from a warp area, and
    a fully walkable 5 x 5 around it.
  - 98.7 % of the walkable cells lie within 7 of a stand.
  - Each block takes a new seeded order and fits ~92 dwells in 50 min.
- **The recording:**
  - the game region at 5 Hz, JPEG q80, in 256-MB tar shards straight on the NAS
    (`/mnt/poring-lab-datasets/detector-collection/orcsdun01/<session>/frames/`), never the local
    disk;
  - the sniffer's packets for the window, pseudonymised, beside them.
- **Thin species get their own dwells:** the plants and the mushrooms live in 4 small fixed areas,
  so a later block dwells on the stands that see them (7-17 stands each). Black Mushrooms respawn
  in 15 min, so a killed one is not the issue; their only 10 sprites are.
- **The state at each switch:**
  - for collection: the hunt's state as the runner leaves it (immune, the hunting UI layout), on a
    judged screenshot;
  - for hunting: the runner restores its own (layout, Lv 70 / STR 99, weight).

### 2a. The collection log

| block | session | time (ICT) | dwells | frames (GB) | safety (packets, `warp_watch.py judge`) | units seen on screen / unit-seconds (1 Hz, within 15 x 11 cells of the GM) |
|---|---|---|---|---|---|---|
| col1 | 20261021T103231-orcsdun01-col1 | 10:32-11:22 (seed 1, 30-s dwells) | 80 (all 80 warps landed as typed) | 15,028 (1.77) | no request, no GM act, 0 acts on the GM (3,627 monster moves); 81 / 81 GM lines seen at the server | Orc Zombie 80 / 10,223; Familiar 15 / 2,068; Steel Chonchon 10 / 1,484; Black Mushroom 10 / 1,157 (from 8 stands); Orc Skeleton 10 / 1,074; White Plant 5 / 789 (14 stands); Drainliar 5 / 449 (23 stands) |
| col2 (the pre-registered TEST block) | 20261021T122650-orcsdun01-col2 | 12:26-13:16 (seed 2, 30-s dwells) | 80 (80 / 80 landed) | 15,038 (1.76) | no request, no GM act, 0 acts on the GM (3,498 monster moves); 81 / 81 lines; the chat closed by warp_watch at its end | Orc Zombie 80 / 9,707; Familiar 15 / 1,570; Steel Chonchon 10 / 1,376; Orc Skeleton 10 / 1,365; Black Mushroom 10 / 1,279 (13 stands); Drainliar 5 / 643 (31 stands); White Plant 5 / 635 (9 stands) |
| col3 | 20261021T142100-orcsdun01-col3 | 14:21-15:01 (seed 3, 30-s dwells, a 40-min block) | 64 (64 / 64 landed) | 12,030 (1.41) | no request, no GM act, 0 acts on the GM (3,049 monster moves); 65 / 65 lines; the chat closed by warp_watch | Orc Zombie 80 / 8,356; Familiar 15 / 1,770; Orc Skeleton 10 / 1,140; Steel Chonchon 10 / 996; Black Mushroom 10 / 940 (6 stands); Drainliar 5 / 610 (24 stands); White Plant 5 / 565 (9 stands) |

- **The live server matches the pinned list exactly:** 135 units of the 7 species.
- **The TRAIN blocks (col1 + col3), unit-seconds per species:**
  - Orc Zombie 18,579; Familiar 3,838; Steel Chonchon 2,480; Orc Skeleton 2,214;
  - Black Mushroom 2,097; White Plant 1,354; Drainliar 1,059.
  - At 1 labelled frame a second that is >= 1,000 candidate labels per species before
    exclusions.
  - The thinnest are Drainliar (5 alive, a fast flyer) and White Plant (5 alive, two small
    areas). Black Mushroom is seen from only 6-13 stands a block, and is often under canopy.
- **More for the thin species, if Batt wants it (not run):** dwells weighted to the stands that
  see their spawn areas:
  - White Plant (83,50) / (58,67);
  - Black Mushroom (167,133) / (67,34);
  - Drainliar has no area (whole map), so only longer blocks help.
  - The label gates (3a, 5a) come first: more frames do not fix the boxes.
- **A dwell takes ~40 s, not the planned 32.5 s:** typing a GM line costs ~7 s. So ~73 dwells fit
  in a 50-min block, not 92.
- **The chat input stayed OPEN after the GM lines** (`chat_open` True). It is the chat window's own
  input line, so it shows in col1's frames.
  - It was closed by its known step before the next hunt run.
  - Since 90a15bf, warp_watch closes it after its last line.

## 3. The camera check on the first block (bars fixed HERE, before its frames are read)

The model was fitted on prt_fild08 / prt_church, and orcsdun01 uses the outdoor camera without a
measurement. The check:
- **Data:** the first block's frames, with the packets' STANDING monsters: idle >= 1 s, no other
  unit within 120 px, not under a UI window.
- **C1:** `label_check.py`'s masked NCC of the rendered sprite (k 0.140, the v1 labels' k) at the
  projected anchor.
  - The fixed tau is 0.092 (M4, phase3-plan 5b).
  - **Pass: < 2 % `bad_label` pooled** (the M5 gate), reported per species.
- **C2:** the best-NCC offset within ±16 px of the projected anchor.
  - **Pass: median |dx| and |dy| <= 4 px for the ground species** (Orc Zombie, Orc Skeleton, White
    Plant, Black Mushroom) **and <= 6 px for the three flyers**, per species with >= 20 standing
    labels.
- **Reported:** the Familiar-vs-Drainliar colour gap as drawn here (the mean hue of their pixels).
- **If C1 or C2 fails,** no orcsdun01 label trains. The camera / k is re-measured first, M4-style,
  and the result goes to Batt.

### 3a. RESULT on the first block, col1 (`scripts/orc_camera_check.py`, run 2026-10-21 11:55 ICT): FAIL

➡️ The fix this led to is pre-registered in 3b; its re-run on col1 is 3c (C1 15.6 %, still FAIL).

Session `20261021T103231-orcsdun01-col1` (80 dwells, 15,028 frames; every 5th frame inside a dwell,
outside GM windows; 2,985 standing labels scored). The output is local:
`/dev/shm/poring-lab-tmp/orc-labels/<session>/camera_check.json`.

- **C1 FAILS:** `bad_label` 34.7 % pooled (bar < 2 %). Per species: Orc Zombie 36.1 %, Orc Skeleton
  49.6 %, White Plant 12.0 %, Black Mushroom 69.2 %, Familiar 22.0 %, Steel Chonchon 43.9 %,
  Drainliar 19.8 %.
- **C2 FAILS on Black Mushroom only** (median |dx| 7.5, |dy| 9 px; bar 4). It passes for Orc Zombie
  (2 / 2), Orc Skeleton (4 / 2), White Plant (1 / 1), Familiar (2 / 5), Steel Chonchon (4 / 3) and
  Drainliar (1 / 3). Every species had >= 20 standing labels (101-1,573).
- **Colour (reported):** the drawn Familiar is a dull grey-brown and the drawn Drainliar a saturated
  red. On well-found bats: hue 53° (saturation 0.26) against 5° (0.69), a 48° gap; 84° in the
  rendered sprites.
- **Diagnostic, NOT a bar:** the sprite's VIEW, not the camera.
  - With the best of the 8 headings, the low share falls from 34.7 % to 5.0 % pooled. The max over 8
    is biased upward, so read it as an upper bound.
  - The Timeline facing differs from the best view on 78 % of the labels, mostly by 45° (±1
    heading), then 90°. 85 % of those facings were set by a walk.
  - This is the outdoor facing that phase3-plan 5d-ii left OPEN: "a wrong view lowers the NCC".
    The symmetric prt_fild08 sprites hid it; the asymmetric orc sprites show it, and their boxes
    shift sideways with the view.
  - The positive cases score 0.6-0.9 at offset (0, 0). Re-measuring decides what to change; this
    diagnostic does not.
  - **Per species** (`facing_diagnostic` in the same JSON, read 15:0x; low share with the
    Timeline facing -> with the best of 8 headings; where the facing came from):

    | species | n | Timeline facing | best of 8 | facing differs | facing set by |
    |---|---|---|---|---|---|
    | Orc Zombie | 1,573 | 36.1 % | 5.5 % | 1,337 | walk 1,532 |
    | Orc Skeleton | 222 | 49.5 % | 2.2 % | 191 | walk 213 |
    | Steel Chonchon | 280 | 43.9 % | 3.6 % | 232 | walk 273 |
    | Familiar | 445 | 22.0 % | 0.9 % | 390 | walk 431 |
    | Drainliar | 101 | 19.8 % | 0.0 % | 86 | walk 90 |
    | Black Mushroom | 130 | 69.2 % | 12.3 % | 83 | appear 130 |
    | White Plant | 234 | 12.0 % | 12.0 % | 0 | appear 234 |

  - So the FACING explains nearly all of the walkers' failures (<= 5.5 % with the best view).
  - For the two immobile plants, two different things:
    - Black Mushroom's facing at appearance is wrong for 83 of 130. Its 12 % residual is LIKELY
      the canopy and model occlusion that 5a saw (not measured: the RSW models were not read);
    - White Plant's 12 % is NOT the facing (0 differ). Something else, unmeasured.
  - Even the best view, pooled at 5.0 %, misses the 2 % bar. So a facing fix alone would not
    pass C1; occlusion (and White Plant's cause) must come with it.

### 3b. THE LABEL FIX (pre-registered 2026-10-21 16:52 ICT, the commit time of 3b's first commit, BEFORE it is built or any check re-runs; Batt's decisions on the day report)

**Batt (verbatim, abridged):** "ORC DUNGEON labels (pre-register the fix, then re-run BOTH checks
on col1 before any training): 0. Use the monster SPRITES (decoded client sprites, local only) as
the primary source for boxes wherever possible: render the expected sprite (species, action,
facing, frame) at the projected position, and fit the box to it. 1a. Facing: derive each
monster's view from its WALK DIRECTION (85 % of the wrong facings come from walks); keep the
best-of-8 drawn view as the cross-check. 1b. Flyers: measure the drawn anchor offset per species
(Familiar, Drainliar, Steel Chonchon). 1c. Occlusion: read the map's RSW models and exclude labels
under canopy/models. 1d. Measure the packet -> frame offset on this grab path. 2. v1's prt_fild08
sessions keep v1's rules with the species split only. 3. Class scheme: the proposed 15 classes.
4. More collection after the labels pass, stand-weighted at White Plant / Black Mushroom spawn
areas."

**The changes (one set, "labels v2orc-fix"):**
- **1a. The facing from the walk direction.**
  - A monster whose last move (packets: its move's from -> to) ended within the frame's past is
    drawn facing that move's 8-way direction, kept after it stops, until a new move, an attack
    or a turn packet changes it.
  - Otherwise: the Timeline's facing, as before.
  - The best-of-8 drawn view is REPORTED as the cross-check (agreement per species), never used
    to choose.
- **1b. The flyers' drawn anchor:** Familiar, Drainliar, Steel Chonchon. A per-species
  (dx, dy) offset of the drawn sprite from the projected cell: the median best-NCC offset of
  STANDING units. Measured on **col3** only.
- **1c. Occlusion:**
  - orcsdun01.rsw's models are read from the client GRF (local only, never committed) and
    projected with the same camera.
  - A label whose sprite box overlaps a model's projected box (canopy, rocks, pillars) is
    EXCLUDED, never kept.
  - The count is reported per species.
- **1d. The packet -> frame offset on this grab path** (RDP, the frame bus, 5 Hz shards):
  - measured on **col3**: moving units' packet positions against the best-NCC drawn positions
    over a sweep of offsets, keeping the offset with the smallest median error;
  - it replaces 375.9 ms (the 2026-10-02 RDP v2 baseline p50, a different path).
- **0. Boxes from the sprites:**
  - the expected sprite (species, action, facing from 1a, frame) is rendered at the projected
    position (+ the 1b anchor, at the 1d time);
  - the LABEL box is the rendered sprite's box, fitted to the frame by the best masked-NCC offset
    within +/- 6 px (ground) / +/- 10 px (flyers);
  - a fit below tau 0.092 or at the search edge = EXCLUDED.
- All parameters (1b, 1d) are frozen from col3 BEFORE col1 is read. col2 (the pre-registered TEST
  block) is not read at all.

**The checks re-run on col1 (the SAME bars as sections 3 and 5):**
- **C1 / C2 judge the PREDICTION, not the fitted box** (a fitted box would pass C1 by
  construction):
  - C1 = the masked NCC of the rendered sprite (facing from 1a, anchor from 1b, time from 1d) AT
    the projected position, no fit; **< 2 % `bad_label` pooled**, tau 0.092;
  - C2 = the best-NCC offset of the same: **median |dx|, |dy| <= 4 px ground, <= 6 px flyers**,
    per species with >= 20 standing labels.
  - Both are computed after the 1c exclusion. The excluded count is reported.
- **The blind check judges the LABELS (the fitted boxes, after 1c):**
  - two NEW blind labeller agents, a NEW seed, 30 crops per species;
  - **>= 90 % "good" from each agent, the species right >= 95 %**.
- **Reported, not deciding:**
  - the facing agreement walk-rule vs best-of-8, per species;
  - the measured 1b offsets and the 1d offset;
  - the exclusions per reason (unfit, occluded, UI, crowd);
  - the labels kept per species.

**Decision rule:**
- A species trains only if it passes C1, C2 (where it has >= 20 standing labels) and the blind
  check.
- A failing species is excluded and reported; the others may train under v2orc-vs-v1.md's
  unchanged pre-registration.
- If C1 fails pooled, nothing trains, and the result goes to Batt.

**Also decided (Batt):**
- 2. v1's prt_fild08 sessions keep v1's rules, with the species split only (no labels-v2
  exclusions on them).
- 3. The class scheme: the 15 classes of section 4 (no longer "proposed").
- 4. More collection only AFTER the labels pass: stand-weighted dwells at White Plant (83,50) /
  (58,67) and Black Mushroom (167,133) / (67,34).

### 3c. RESULT of the label fix on col1 (`scripts/orc_labels_fix.py`, a4d2493)

**The parameters, measured on col3 and FROZEN at 17:27:20 ICT, before any col1 frame or packet was
read** (`orc_labels_fix.py freeze`; params sha256 `fe1fb9b3…f6d5af`, local
`/dev/shm/poring-lab-tmp/orc-labels-fix/params.json`). col2 is not read (the tools refuse it by
name).

| parameter | value | measured how (col3 `20261021T142100-orcsdun01-col3`, every 2nd frame in a dwell) |
|---|---|---|
| 1d packet -> frame offset | **120 ms** (replaces 375.9) | 260 samples (56 units; Orc Zombie 257, Orc Skeleton 3) that walk ONE move through the whole sweep, isolated, clear of the UI, edges and models; median error 2.24 px at 120 ms, 3.16 at 150, 16.3-17.8 at 350-400 (the old value's neighbourhood); coarse 50 ms 0..1000, then 10 ms ±50 |
| 1b anchor, Familiar 1005 | (dx, dy) = **(1, -1) px** | 455 standing labels, MAD 1 / 1 |
| 1b anchor, Steel Chonchon 1042 | **(0, -2) px** | 317 standing labels, MAD 1 / 1 |
| 1b anchor, Drainliar 1111 | **(1, -1) px** | 271 standing labels, MAD 1 / 1 |
| (reference only) ground species | Orc Zombie (1, -1), Orc Skeleton (1, -1), White Plant (0, 0), Black Mushroom (0, -1) | not applied: 1b is the flyers' |
| fit radius, tau, k | ±6 px ground / ±10 px flyers, 0.092, 0.140 | 3b, section 3 |
| 1c models | 162 RSW models (23 RSM 1.4 files), the client GRF, local | each model's projected vertex box; checked by eye on col3 frames |


**THE CHECK on col1** (`orc_labels_fix.py check`, run 17:28 ICT at 13a5ae4, 49 s; every 5th
frame inside a dwell, outside the GM windows: 2,325 frames read, 1,010 with standing labels).
C1 / C2 judge the PREDICTION (facing 1a, anchor 1b, time 1d, no fit), after 1c.

| species | standing scored | 1c: under a model, excluded | C1 `bad_label` (3a) | C2 median \|dx\| / \|dy\| px (bar) | C2 |
|---|---|---|---|---|---|
| Orc Zombie 1153 | 685 | 874 | 17.5 % (36.1) | 1 / 1 (4) | PASS |
| Orc Skeleton 1152 | 131 | 91 | 29.8 % (49.6) | 1 / 1 (4) | PASS |
| White Plant 1082 | 125 | 107 | **0.0 %** (12.0) | 1 / 1 (4) | PASS |
| Black Mushroom 1084 | **0** | 132 (every one) | -- (69.2) | -- | NO VERDICT (0 labels) |
| Familiar 1005 | 191 | 256 | 12.0 % (22.0) | 1 / 1 (6) | PASS |
| Steel Chonchon 1042 | 178 | 116 | 15.7 % (43.9) | 1 / 1 (6) | PASS |
| Drainliar 1111 | 56 | 37 | 5.4 % (19.8) | 1 / 1 (6) | PASS |
| **pooled** | **1,366** | 1,613 | **15.6 %** (213; bar < 2 %; 3a 34.7) | | |

- The other exclusions of the check: not standing 6,297; crowded 5,463; under the UI or at an edge
  1,281. The C1 failures are all `bad_label` (0 `occluded` / `ui_covered`: the standing rule
  isolates them). The 3a column is a different label set (1c removes labels, 1d moves the
  standing window): an indication, not a like-for-like.
- **VERDICT (3b's decision rule): C1 FAILS pooled (15.6 % against < 2 %), so NOTHING TRAINS and the
  result goes to Batt.** C2 passes for every species with >= 20 labels (all at 1 / 1 px: the
  position, anchor and offset are right). White Plant is the only species under 2 % on its own.
  Black Mushroom has no standing label left after 1c: every one is under a model box.
- **Reported, not deciding: the facing.** The walk rule's heading equals the best of the 8 drawn
  views on 456 of its 1,208 labels (37.7 %). Per species, over all its scored labels (the rule set
  the heading of 1,208 of the 1,366): Orc Zombie 37.7 %, Orc Skeleton 38.9 %, Familiar 36.1 %,
  Steel Chonchon 35.4 %, Drainliar 44.6 %, White Plant 100 % (never moves: its appear heading). With the best of the 8 views the low share would be 0.44 % pooled (a max over
  8, biased upward). Split by the shape of the move the rule used (a scratch diagnostic on the
  same rows, `/dev/shm/poring-lab-tmp/orc-labels-fix/scratch/facing_diag.py`):

  | move (from -> to) | labels | rule = best view | low (C1 < tau) | the Timeline's last step = best view |
  |---|---|---|---|---|
  | along an axis (dx or dy = 0) | 259 | **0.4 %** (best view: -45° 153, +45° 57, +90° 46) | 30.1 % | 0.4 % |
  | exact diagonal | 160 | 68.8 % | 1.9 % | 65.6 % |
  | mixed | 789 | 43.7 % | 15.8 % | 11.4 % |
  | all | 1,208 | 37.7 % | 17.1 % | 16.2 % |

  After a straight (axis) move the client draws a DIAGONAL view, never the axis one. The walk rule
  beats the last step on mixed moves but leaves the axis moves wrong. That is material for the next
  hypothesis (Batt's call), not tuned here.

**THE LABELS on col1** (`orc_label_sheets.py --fix`, ab61cdf, every 3rd frame as round 1: 5,010
frames; v2's own frame rules keep 4,343, as in round 1). Each visible orcsdun01 monster label:

| species | kept (fitted) | under a model (1c) | unfit | crowd | UI | kept share |
|---|---|---|---|---|---|---|
| Orc Zombie 1153 | 6,942 | 8,869 | 722 | 323 | 178 | 40.8 % |
| Orc Skeleton 1152 | 710 | 894 | 114 | 31 | 7 | 40.4 % |
| White Plant 1082 | 722 | 623 | 0 | 9 | 0 | 53.3 % |
| Black Mushroom 1084 | 56 | 1,719 | 0 | 0 | 0 | 3.2 % |
| Familiar 1005 | 1,294 | 1,822 | 168 | 51 | 34 | 38.4 % |
| Steel Chonchon 1042 | 1,198 | 971 | 129 | 39 | 18 | 50.9 % |
| Drainliar 1111 | 390 | 318 | 14 | 10 | 0 | 53.3 % |
| all | 11,312 | 15,216 | 1,147 | 463 | 237 | 39.9 % |

- 1,551 more monsters fail v1's visibility rule (under half on screen, or half behind the UI) and
  get no label, as in v1.
- **The literal 1c rule empties the cache:** a frame with any excluded monster is excluded
  (section 5: labelled completely or excluded), so only **283 of the 4,343 frames** stay whole
  (6.5 %); 3,850 have a monster under a model box. A projected 2-D model box covers much of the
  screen in this dungeon of trees, braziers and fences, in front of the sprite or behind it.
  What a training cache does about it (per-label ignore regions, a depth-aware occlusion test) is
  a new decision for Batt, not made here.
- The fit fails (unfit / crowd / UI) on 1,847 of the 13,159 labels that are not under a model
  (14.0 %).

**THE BLIND PACK (round 2), built, NOT run** (the parent launches two new blind agents):
- seed 1 (round 1: seed 0); 30 crops per orcsdun01 species, drawn from EVERY kept fitted label
  (`--blind-from kept_labels`: the blind check judges the labels; whole frames alone would give
  Drainliar 6, White Plant 4 and Black Mushroom 0 crops), plus col1's 15 Poring crops (prt_fild08
  frames, v1's labels, as in round 1) = 225 crops, 12 numbered grids, the reference sheet A-L;
- the pack: `/dev/shm/poring-lab-tmp/orc-labels-fix/blind-pack-seed1/` (with `instructions.txt`);
  the answer key, in its own directory: `/dev/shm/poring-lab-tmp/orc-labels-fix/answer-key-seed1/`;
- **under 3b's decision rule the blind round cannot make a species train while C1 fails pooled.**
  It still measures the fitted boxes.

**Where the outputs live (local, client-derived, never committed):**
`/dev/shm/poring-lab-tmp/orc-labels-fix/` -- `col3/{offset,anchor}.json` (1d, 1b),
`params.json`, `col1/camera_check_fix.json` + `col1/check_rows.json` (the check),
`20261021T103231-orcsdun01-col1/{labels_summary.json,sheets/}` (the labels, the contact sheets),
`grf/data/model/` (the 23 RSMs), `scratch/overlay_*.png` (the 1c geometry check on col3).

## 4. The class scheme (PROPOSED; Batt's default if he does not answer by the time the labels are ready)

| id | class | from |
|---|---|---|
| 0 | `player` | packets objtype 0; our GM labelled `player` (labels v2, Batt 2026-10-09) |
| 1 | `npc` | packets objtype 6 (labels v2) |
| 2 | `warp` | labels v2's warp rule (L3 cell + drawn portal + visible). A frame whose warp cannot be labelled completely is EXCLUDED (labels v2's rule) |
| 3.. | one class per monster species with data | packets objtype 5, by mob id |

- **The monster classes:**
  - the prt_fild08 species: Poring 1002, Lunatic 1063, Pupa 1008, Drops 1113, Creamy 1018 (the
    metamorphosis), plus any other species the labeller finds in v1's sessions;
  - orcsdun01's seven: 1005, 1042, 1082, 1084, 1111, 1152, 1153.
  - That makes about 15 classes.
- **The hunt code maps species to `monster` plus its target / ignore lists.** The species check
  then comes from the detector. Creamy becomes its own class instead of a monster the bot strikes
  by mistake.
- **The live CPU detector stays v1** until Batt decides on the new one (his item 7).
- Two open questions for Batt:
  - **Warp:** if labels v2's warp inputs are not ready for these maps, `warp` is left out of this
    model rather than half-labelled.
  - **Thin classes:** White Plant (5 alive) and Drainliar (5) may stay thin. They train and are
    reported apart, with no bar of their own until they reach 50 held-out labels.

## 5. The labels and the label check

- **The labels** come from packets, offline (ADR-0007):
  - positions -> screen through the camera model (`projector_for`);
  - boxes from the sprite catalog per species (`predict_sprite`; local decoded sprites, never
    committed);
  - occlusion and UI cover handled as labels v1 / v2 do;
  - every frame is labelled completely or EXCLUDED.
- **The contact sheets:** one per species, each crop with its box (the NAS / /dev/shm only).
- **The blind check:** two labeller agents, independently, on a sample of 30 crops per species.
  - They see no predicted class name. They answer: a monster there? the box good / loose / off?
    which species (from a sheet of rendered references)?
  - **The bar for a species to train: >= 90 % "good" from each agent, and the agents' species
    agreeing with the label on >= 95 %.**
  - A species that fails is excluded and reported.
- **The gold set for orcsdun01:**
  - 20 frames from a held-out block on which both agents accept every box;
  - any disagreement is resolved by the parent, recorded, and shown to Batt.

### 5a. RESULT: the blind label check on col1 (2026-10-21 ~12:10 ICT): FAIL for every orcsdun01 species

➡️ Round 2 (the label fix's fitted boxes, seed 1) is built but not run: 3c.

- **The pack** (`scripts/orc_label_sheets.py`, seed 0):
  - 30 crops per orcsdun01 species + col1's 15 Poring boxes = 225 crops;
  - shown to the labellers as 12 numbered grids, with a reference sheet of 12 rendered sprites
    (A-L);
  - the answer key sat in a separate directory the labellers never opened.
- **The labellers:** two blind agents, A and B, independent; B worked in reverse order. Their
  agreement: Q1 (a monster in the box) 218 / 225, Q2 (the box) 201 / 225, Q3 (the species)
  213 / 225.
- **The bars** (section 5, fixed before): >= 90 % "good" from EACH labeller, and the species right
  on >= 95 %.

| species | crops | A: good / species right | B: good / species right | passes |
|---|---|---|---|---|
| Orc Zombie 1153 | 30 | 86.7 / 96.7 % | 83.3 / 96.7 % | no (good) |
| Orc Skeleton 1152 | 30 | 86.7 / 100 % | 76.7 / 100 % | no (good) |
| White Plant 1082 | 30 | 93.3 / 96.7 % | 86.7 / 93.3 % | no (B) |
| Steel Chonchon 1042 | 30 | 76.7 / 76.7 % | 76.7 / 80.0 % | no |
| Familiar 1005 | 30 | 60.0 / 83.3 % | 53.3 / 70.0 % | no |
| Drainliar 1111 | 30 | 56.7 / 93.3 % | 50.0 / 96.7 % | no |
| Black Mushroom 1084 | 30 | 70.0 / 60.0 % | 60.0 / 60.0 % | no |
| (Poring 1002, prt_fild08 frames) | 15 | 100 / 100 % | 100 / 100 % | yes |

- **When a monster is in the box, its species is right.** The wrong-species answers are mostly
  "none / unsure": nothing visible in the box. Black Mushroom accounts for 12-13 of them, Steel
  Chonchon 6-7. Real confusions are few: Familiar read as White Plant (B) or Lunatic (G) in 3-4 crops.
- **The failures are in WHERE the box is, and in occlusion:**
  1. The bats' boxes sit next to the bat: both labellers called Drainliar and Familiar "off" in 5-8
     crops each. The flyers' anchor (drawn 38-88 native px above the cell) and the facing (3a)
     shift them.
  2. The orcs are cut along one side: the facing model's asymmetric idle box (3a's diagnostic).
  3. Black Mushrooms under tree canopy or map models: the packets place one there, and the client
     draws nothing visible (FACTS 9.4: the RSW models were not read). Those labels need an
     occlusion exclusion.
- **=> No orcsdun01 label trains** (section 3's gate and this one). The fix is a labelling
  hypothesis, pre-registered (the facing, the flyers' anchor, model occlusion), then both checks
  re-run. That is Batt's call.
- 157 of the 225 crops were "good" for both labellers with the right species. They are the
  candidates for this map's small gold set once the labels are fixed.
- The answers are local only (`/dev/shm/poring-lab-tmp/blind-A|B/answers.json`, client-derived).

## 6. Training and evaluation

- **Training** runs on the combined cache: v1's sessions re-labelled per species + the orcsdun01
  blocks (split by block).
  - ⚠️ **Measured 2026-10-21 (a dry run, packets only):** `build_frame_cache.py --labels v2
    --classes species` on v1's 10 sessions KEEPS 566 of 16,995 candidate frames (3.3 %). The rest
    are excluded by labels v2's own rules:
    - `npc_unchecked`, 15,560 frames: no person's N3 verdicts yet (prt_fild08's NPCs 51 and 909,
      prt_church's);
    - `warp_visibility_unknown`, 9,914: no warp table (prt_fild08 170,378 alone is 7,143);
    - `self_dead`, 4,130.
  - No species outside the class list appears in v1's data, and Creamy has 0 boxes.
  - So the "not forgotten" half needs those inputs, or a decision on how v1's sessions are
    re-labelled, before the combined cache is built.
  - The setup is v1's: `train-day.sh` in the long-lived vision worker, `MID_CKPT=1`, the adaptive
    duty cycle, the IO guard, VRAM 25 %, batch 2 / workers 1.
  - Cache building stays outside 09:30-10:15 and 14:00-14:45.
  - **CPU contention (Batt ~09:3x):** the hunt's CPU detector fps / latency is measured while
    training runs (the runner's `det_fps`, v51 2.87-3.08). If it drops, the loader's workers or
    nice go down first; the hunt is never slowed.
- **The evaluation** is pre-registered in `docs/benchmarks/v2orc-vs-v1.md` BEFORE training. Its
  outline:
  - per-species recall / precision on the held-out orcsdun01 block;
  - v1's gold set (Batt's 27 frames, the position metric, monsters collapsed) and held-out
    prt_fild08 sessions no worse than v1 (P 0.902 / R 0.830);
  - Creamy recall reported;
  - latency per frame on GPU vs CPU.

## 7. Not today (Batt's item 7)

Two later decisions:
- the GPU detector for live hunting;
- what hunting among AGGRESSIVE monsters needs: HP watch, potions, retreat / death handling.
  Immunity comes off only after those exist.
