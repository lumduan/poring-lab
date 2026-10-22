---
doc_type: design
hypothesis: "Warp-and-watch collection plus packet labels give a per-species detector for orcsdun01 that does not forget prt_fild08 (v1's gold set and held-out sessions no worse)."
status: PROPOSED (collection done 2026-10-21; the 15 classes decided (3b); label fix 2 + exclusions and the two tiers PRE-REGISTERED 2026-10-22 in 3f; the evaluation is pre-registered in ../benchmarks/v2orc-vs-v1.md BEFORE training, its P1 amended by 3f)
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [labels-v2-plan.md, training-cost.md, ../benchmarks/v1-vs-v0png.md, ../phase3-plan.md, ../operations/vision-long-lived.md]
next_action: "3h: the TRAINING TIER FAILS -- T1 passes (C1 2.69 % on col1), T2 (blind round 3) fails on ONE species, the Familiar (labeller E 86.7 % good < 90 %: wing tips cut). By 3f nothing of orcsdun01 trains; Batt's call: a wing-reach box for the bats, the Familiar's labels left out, or accept it. The cache tooling (build_frame_cache --fix, per-session label modes) is built anyway for the next attempt."
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
    ➡️ 3e (DRAFT) finds this count inflated by TIES: the ACT draws its directions in identical
    pairs, so a best-of-8 that keeps the first of equal scores never names W, S or E. Read by image
    in 3e.
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

  ➡️ **SUPERSEDED by 3e (a DRAFT, measured on col3 only):** the axis row above is mostly a TIE of
  the best-of-8 (the ACT draws S = SW, W = NW, N = NE, E = SE). Read by image, the rule was right on
  154 of the 259 axis-move labels. On col3 the client draws a unit that walked NORTH with NW's image
  and one that walked EAST with NE's image; south and west match the rule. The 37.7 % and the
  per-species agreement above count the same ties.

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

### 3d. RESULT: the blind check, round 2, on the FITTED labels (col1, seed 1, 2026-10-21 18:1x-18:26)

- **The pack:** the label fix's (3c), `orc-labels-fix/blind-pack-seed1`.
  - 30 crops per orcsdun01 species, drawn from every KEPT fitted label (3c's deviation: whole
    frames alone would give Drainliar 6, White Plant 4, Black Mushroom 0), plus 15 Poring
    controls.
  - Two NEW blind labeller agents (C, D), each seeing only the pack.
- **Scored by `scripts/blind_score.py`** (0a14c67, committed today; it reproduces round 1 exactly).
  Bars (section 5): >= 90 % good from EACH labeller and the species right >= 95 %.

| species | C good / species (off, loose) | D good / species (off, loose) | blind check |
|---|---|---|---|
| Orc Zombie 1153 | 93.3 / 100 (2, 0) | 90.0 / 100 (2, 1) | PASS |
| Orc Skeleton 1152 | 90.0 / 100 (2, 1) | **86.7** / 100 (2, 2) | **FAIL** (D) |
| White Plant 1082 | 100 / 100 | 100 / 100 | PASS |
| Black Mushroom 1084 | 100 / 100 | 100 / 100 | PASS (56 kept labels only; no C1 verdict, 3c) |
| Familiar 1005 | 96.7 / 100 (1, 0) | 96.7 / 100 (1, 0) | PASS |
| Steel Chonchon 1042 | 90.0 / 100 (3, 0) | 90.0 / 100 (3, 0) | PASS |
| Drainliar 1111 | 93.3 / 100 (2, 0) | 93.3 / 100 (2, 0) | PASS |
| (Poring 1002, control) | 93.3 / 100 (0, 1) | 100 / 100 | PASS |

- **Agreement C-D:** q1 225 / 225, q2 222 / 225, q3 225 / 225. Crops good with the right species
  for both: 211 / 225 (round 1: 157).
- **What the labellers flagged:**
  - the "off" boxes cut a weapon (orc cleavers) or a wing (bats), or sit too high on a Steel
    Chonchon;
  - stacked orcs: the box fits the rear one;
  - two-tone bats (one wing tinted), called Familiar by both.
- **Against round 1 (5a, on the PREDICTED boxes):** every species FAILED there; now 7 of 8 pass.
  The fit (3b item 0) is what changed the boxes.
- **THE VERDICT UNDER 3b's RULE IS UNCHANGED: NOTHING TRAINS.** 3b: "If C1 fails pooled, nothing
  trains, and the result goes to Batt". C1 failed pooled (15.6 %, 3c).
  - C1 judges the PREDICTION (the camera, facing and anchor model).
  - This check judges the fitted LABELS. They are what a model would train on, and they now pass
    for 6 of 7 orcsdun01 species.
  - Whether the fitted labels may train despite C1 is a new decision. It is Batt's: a new
    pre-registration, not a reading of this one.

### 3e. DRAFT for Batt -- NOT pre-registered, NOT run: fix 2 (the drawn view), and options for the occlusion and the Orc Skeleton

➡️ **SUPERSEDED as a draft: fix 2 is now PRE-REGISTERED in 3f** (Batt 2026-10-22 ~19:4x: "fix 2 +
exclusions", read as (i)-(iii) with 2b AND 2c, the exclude variant). O1-O4 and S2-S4 were NOT
adopted (3b's 1c stays). This section is kept unchanged below as the evidence 3f rests on.

**Status: a DRAFT.** It is evidence for Batt's next hypothesis, written by an offline study on the
FITTING block col3 only (2026-10-21, 21:4x-22:3x ICT). Nothing here is pre-registered, nothing
re-runs on col1 until Batt approves, and col2 is not read (the tool refuses col1 and col2 by name).
3b's rules, bars and parameters are unchanged.

**The study** (`scripts/orc_facing_study.py`; 72cb479, its test 41ba6cf):
- **Data:** col3 `20261021T142100-orcsdun01-col3`, every 2nd frame inside a dwell, outside the GM
  windows, at 3c's frozen 1d offset (120 ms) and 1b anchors.
- **Halves by time:** half 1 = the first 32 dwells, half 2 = the last 32.
  - The rules were explored on half 1 only.
  - The rule `fix2` and the confirmation test were committed at 22:04:51 (72cb479), BEFORE half 2's
    rows were made (22:05-22:10).
- **The samples:** every orcsdun01 monster STANDING (section 3's rule: idle >= 1 s) or WALKING,
  isolated by 120 px, clear of the UI and the edges. Half 1: 4,377 samples; half 2: 4,282.
- **The drawn view:**
  - each view CLASS is scored by label_check's masked NCC (the best over the action's frames and
    +-3 px standing / +-4 px walking);
  - the drawn class is the best one;
  - a sample counts when it is DECISIVE: best >= tau 0.092 and >= 0.05 above the second (96 % of
    the samples).
  - The decisive samples are also reported per EPISODE (one unit's one walk, or one standing spell:
    its majority class).
  - The picture is the same on all samples (fix2 90.1 / 91.5 %, 1a 78.1 / 77.3 %) and on the
    samples clear of the model boxes (93.6 / 94.4 %, 1a 81.7 / 78.5 %; `score.json`).
- **Nothing is ported from rAthena (GPL).** The diagonal-first path is our own code from its idea;
  the A* is the Timeline's.
- **Checked by eye:** col3 frame 1938, an Orc Zombie standing after an EAST move.
  - It shows its BACK: NCC 0.69 for the N / NE image against 0.10 for the E / SE image, the cleaver
    side the frozen 1a rule draws.
  - That frame is the test's real positive case.

**Finding 0. 3c's "diagonal after an axis move" is mostly a TIE, not the client.**
- Every orcsdun01 ACT draws its 8 directions in identical PAIRS, in every frame of idle and walk:
  - S = SW, W = NW, N = NE, E = SE for the walkers and the bats (4 distinct images);
  - the two plants have 2 images, mirrored.
- Under our mapping (camera.displayed_direction, yaw 0) an axis heading shares its image with its
  CLOCKWISE diagonal. 3c's best-of-8 kept the first of equal scores, so it could never name W, S or
  E.
- Its "best view -45° on 153 of 259 axis moves" is that tie: the rule's own image.
  - Read by image, the rule was right on 154 of col1's 259 axis-move labels and wrong on 103: 57
    "+45°" and 46 "+90°".
  - On col3 the wrong ones are the north and east moves (below). col1's split by direction is
    not known here: col1 is not read.
- 3a's "the Timeline facing differs from the best view on 78 %" carries the same tie.

**Finding 1. What the client draws (by image).** The share of decisive samples where the rule's
image is the drawn one, % (samples).

Half 1 (explore):

| rule | appeared standing | stand / axis | stand / diagonal | stand / mixed | walk / axis | walk / diagonal | walk / mixed | all |
|---|---|---|---|---|---|---|---|---|
| **fix2 (PROPOSED)** | 99.2 (240) | **98.2** (550) | 99.3 (421) | **86.8** (1,707) | **98.3** (176) | 96.2 (131) | **92.4** (930) | **92.3** (4,155) |
| 1a as frozen (whole vector, map_calc_dir; our mapping) | 99.2 | 56.5 | 99.3 | 77.9 | 59.1 | 96.2 | 85.9 | 80.0 |
| the Timeline facing (A* last step / appear) | 99.2 | 56.9 | 97.4 | 50.9 | 59.7 | 94.7 | 76.6 | 66.7 |
| whole vector, 22.5° sectors | 99.2 | 56.5 | 99.3 | 74.1 | 59.1 | 96.2 | 80.8 | 77.3 |
| last step of the Timeline's A* (rAthena's path_search on 2,534 of 2,540 walks) | 99.2 | 56.9 | 97.4 | 50.9 | 59.7 | 89.3 | 53.7 | 61.4 |
| last step, diagonal-first path | 99.2 | 56.5 | 99.3 | 50.3 | 59.1 | 96.2 | 54.0 | 61.5 |
| last step, straight-first path | 99.2 | 56.5 | 99.3 | 82.9 | 59.1 | 96.2 | 92.4 | 83.5 |
| the step being walked | -- | -- | -- | -- | 59.7 | 94.7 | 76.6 | 76.1 (1,237) |
| the appear packet's heading | 99.2 (240) | -- | -- | -- | -- | -- | -- | 99.2 |
| eye -> unit azimuth (the camera angle), floored, on the A* last step (+ / -) | 39.6 / 60.4 | 48.4 / 50.4 | 97.4 / 99.3 | 53.4 / 47.1 | 55.1 / 44.3 | 89.3 / 90.8 | 47.1 / 52.6 | 56.2 / 56.1 |
| approach: the diagonal turned from (the previous step / facing) | -- | 52.4 (252) | 99.3 | 83.5 | 44.7 (103) | 94.7 | 92.3 | 84.7 |
| every axis heading takes its counter-clockwise image | 0.8 | 41.8 | 99.3 | 78.1 | 39.8 | 96.2 | 81.9 | 70.8 |

Half 2 (CONFIRM; the same rules):

| rule | appeared standing | stand / axis | stand / diagonal | stand / mixed | walk / axis | walk / diagonal | walk / mixed | all |
|---|---|---|---|---|---|---|---|---|
| **fix2 (PROPOSED)** | 97.7 (394) | **97.1** (477) | 98.6 (359) | **90.8** (1,626) | **98.2** (165) | 95.4 (152) | **92.8** (895) | **93.8** (4,068) |
| 1a as frozen | 97.7 | 49.9 | 98.6 | 79.1 | 42.4 | 95.4 | 81.8 | 78.9 |
| the Timeline facing | 97.7 | 49.9 | 98.6 | 49.3 | 42.4 | 93.4 | 73.5 | 65.1 |
| whole vector, 22.5° sectors | 97.7 | 49.9 | 98.6 | 76.8 | 42.4 | 95.4 | 76.3 | 76.8 |
| last step of the Timeline's A* | 97.7 | 49.9 | 98.6 | 49.3 | 42.4 | 93.4 | 46.4 | 59.1 |
| last step, diagonal-first path | 97.7 | 49.9 | 98.6 | 47.4 | 42.4 | 95.4 | 47.0 | 58.6 |
| last step, straight-first path | 97.7 | 49.9 | 98.6 | 84.3 | 42.4 | 95.4 | 92.8 | 83.4 |
| the step being walked | -- | -- | -- | -- | 42.4 | 93.4 | 73.5 | 71.8 (1,212) |
| the appear packet's heading | 97.7 (394) | -- | -- | -- | -- | -- | -- | 97.7 |
| eye -> unit azimuth, floored, on the A* last step (+ / -) | 35.3 / 65.5 | 45.9 / 51.4 | 96.4 / 93.0 | 53.4 / 45.9 | 47.3 / 49.7 | 91.5 / 88.8 | 48.0 / 51.1 | 54.6 / 55.5 |
| approach | 100 (5) | 40.0 (165) | 98.6 | 83.8 | 29.5 (61) | 94.7 | 91.8 | 84.9 |
| every axis heading takes its counter-clockwise image | 3.0 | 47.4 | 98.6 | 79.2 | 55.8 | 95.4 | 84.4 | 70.6 |

- **"Turning in place": no sample.** col3 has no entity_turn and no act packet: the GM is immune and
  nothing fights.
- **The confirmation test** (fixed in 72cb479, before half 2):
  - fix2 pooled >= 0.85, and >= the frozen 1a rule in every state x move shape with >= 20 samples.
  - **Half 2: 93.8 % pooled, and >= 1a in all 7 cells (equal in 3, higher in 4). CONFIRMED** (on
    col3).
  - Per episode: 93.9 % (883) against 77.0 % for 1a.
  - Clear of the model boxes: 94.4 % (1,961) against 78.5 %.

**The axis moves, by direction** (4-image species, decisive samples; fix2 / 1a as frozen):

| last move | half 1 | half 2 |
|---|---|---|
| north | 99.3 / **0.0** % (139 samples, 37 episodes) | 98.8 / **0.6** % (165, 44) |
| east | 98.2 / **1.2** % (165, 37) | 98.1 / **0.0** % (158, 37) |
| south | 98.0 / 98.0 % (249, 51) | 93.2 / 93.2 % (146, 35) |
| west | 97.7 / 97.7 % (173, 37) | 98.8 / 98.8 % (173, 39) |

A unit that WALKED north shows the NW image (its back-left), not N / NE's. One that walked east
shows the NE image (its back), not E / SE's (its front, the cleaver side). South and west are drawn
as we draw them.

**Per species** (all states; fix2 / 1a / the Timeline facing, % of decisive samples):

| species | half 1 | half 2 |
|---|---|---|
| Orc Zombie 1153 | 92.4 / 79.8 / 66.7 (2,454) | 94.1 / 75.9 / 62.9 (2,356) |
| Orc Skeleton 1152 | 94.9 / 81.4 / 62.7 (177) | 93.8 / 74.1 / 57.5 (386) |
| Familiar 1005 | 88.7 / 74.6 / 55.8 (701) | 91.9 / 72.7 / 54.9 (370) |
| Steel Chonchon 1042 | 91.5 / 73.4 / 64.7 (402) | 93.0 / 87.7 / 65.5 (357) |
| Drainliar 1111 | 94.4 / 92.9 / 75.0 (196) | 89.9 / 85.0 / 66.0 (247) |
| White Plant 1082 | 100 / 100 / 100 (225; 5 units) | 95.8 / 95.8 / 95.8 (166; 4 units) |
| Black Mushroom 1084 | -- (none decisive) | 100 / 100 / 100 (186; 3 units) |

**What the rule says, and what it rests on:**
- **A unit that APPEARED standing** (a stand packet, no move since): its packet heading, our mapping.
  - 97.7-99.2 %, but mostly the two plants (heading 0).
  - The 4-image species give only a few units with an axis packet heading:
    - north: 9 of 11 samples (about 5 units) drawn as N / NE;
    - east: 15 of 15 (6 units) drawn as E / SE.
  - A walk-set north or east is drawn otherwise, so the client treats the two sources
    differently. That rests on few units.
- **A WALKING unit:** the quadrant diagonal of its move vector (x1 - x0, y1 - y0), an axis vector
  taken as dx = 0 -> west, dy = 0 -> north. So north -> NW, east -> NE, south -> SW, west -> NW.
- **A unit STANDING after its move:**
  - rAthena's map_calc_dir heading of the whole vector (3b's frozen 1a heading, 1:3 slopes);
  - an axis heading takes the diagonal by the same zero convention; a diagonal stays.
  - On mixed moves this beats the plain quadrant (86.8 / 90.8 against 82.9 / 84.3). While walking
    the plain quadrant is better (92.4 / 92.8 against 84.5 / 87.0): the image switches to the
    axis's late in the walk, or at arrival.
- **Rejected by the data:**
  - the last step of any path (A*, diagonal-first) -- the image is not the last step's;
  - the eye -> unit azimuth (a perspective side rule): about chance on axis moves;
  - "the side it turned from" -- chance on pure axis moves;
  - 22.5° sectors (worse than the 1:3 rule);
  - every axis heading taking its counter-clockwise image (right for N and E, wrong for S, W and
    the packet headings).

**Finding 2. What fix 2 would do to C1: an ESTIMATE on col3, not the check.**
- **The measure:** standing samples clear of the model boxes; the rule's image scored at the
  projected place, no shift (C1's own measure); the share below tau.
- **Calibration:** the frozen 1a rule gives 14.7 % (half 1) and 15.1 % (half 2) here, close to
  col1's real C1 of 15.6 % (3c).
- **The best of the 4 images would give 0.4 / 0.2 %.** So what is left after fix2 is the facing,
  not the position.

| on col3 (standing, clear of models) | half 1 | half 2 |
|---|---|---|
| 1a as frozen | 14.7 % (267 / 1,815) | 15.1 % (203 / 1,346) |
| **fix2** | **4.2 %** (77 / 1,815) | **4.2 %** (57 / 1,346) |
| fix2, without the 150 ms before a unit's next move packet (2b) | 3.3 % | 3.0 % |
| fix2, without the ambiguous mixed moves (2c) | 3.7 % | 3.1 % |
| fix2 with 2b and 2c | 2.7 % (43 / 1,574) | 1.9 % (23 / 1,191) |

- **Per species, fix2:**
  - half 1: Orc Zombie 5.1, Orc Skeleton 2.9, Familiar 2.7, Steel Chonchon 6.3, Drainliar 6.6,
    White Plant 0.0 %;
  - half 2: 5.4, 1.0, 0.0, 10.4, 4.0, 0.0 %, Black Mushroom 0.0 %.
- **⇒ fix 2 alone is projected to FAIL C1 again** (about 4 % against < 2 %), at about a quarter of
  today's failure.
- **The two residual mechanisms, found on half 1 and looked at again on half 2 after its one
  reading** (so NOT confirmed):
  - **2b, the next move:** in the 150 ms (timeline time) before a unit's next move packet, fix2
    holds on only 40 / 64 (half 1) and 36 / 58 (half 2) standing samples. Of the wrong ones, 19 / 24
    and 14 / 22 already show the NEXT move's image. The client turns at the packet, before the
    visible step (the 120 ms offset was fitted on positions).
  - **2c, the ambiguous mixed moves:** on a mixed move the image switches from the vector's
    quadrant to the axis's late in the walk, and the switch slope is fuzzy:
    - long / short ratio about 2-3.5 against map_calc_dir's sharp 3;
    - "ambiguous" here = the vector's quadrant and map_calc_dir's quadrant name different images
      (176 + 100 standing samples).
- With both, the estimate is at the bar, 1.9-2.7 %. Without a confirmation it is not a basis for
  a pre-registered expectation.

**DRAFT TEXT for a pre-registration (Batt edits, approves or drops; NOT in force):**

> **3e fix 2 (labels v2orc-fix2):** 3b unchanged except the facing (1a) and its mapping to the
> sprite's image:
> - (i) a monster that appeared standing and has not moved since: its appear heading, mapped as
>   today;
> - (ii) a walking monster: the image of the quadrant diagonal of its move vector (x1 - x0, y1 - y0)
>   (dx = 0 counts as west, dy = 0 as north);
> - (iii) a monster standing after its move: map_calc_dir's heading of that vector; an axis heading
>   draws the image of the diagonal by the same convention (north -> NW, east -> NE, south -> SW,
>   west -> NW).
>
> [Optional, Batt's choice:]
> - (2b) a monster within 150 ms (timeline time) of its next move packet is EXCLUDED (as `unfit`);
> - (2c) a standing label after a mixed move whose two candidate images differ is EXCLUDED, or
>   fitted with both images and the better kept (labels only: C1 judges the prediction).
>
> 1b, 1c, 1d, tau, k and the fit radius are 3c's frozen values. C1 / C2 and the blind check re-run
> on col1 with section 3 / 5's bars and 3b's decision rule. Expected from col3, not a bar: C1 about
> 4 % without 2b / 2c, about 2-3 % with them.

**The occlusion (3c: the literal 1c rule keeps 283 of 4,343 col1 frames whole).** Measured on col3:
- **Most standing monsters under a model's 2-D box are drawn whole:** 2,888 of 2,897 have a best
  image NCC >= tau.
- **The orcs score about as well under a box as clear of one:** Orc Zombie (half 1) median 0.66
  under a box, 0.70 clear.
- **Only the White Plants under canopy are really hidden:** median 0.23 (half 1), 0.26 (both
  halves), against 0.76-0.78 clear.
- **What each rule keeps** on col3: 3b's label fit with either facing, every 6th dwell frame, 1,543
  frames (scratch `occl_options.py`, 22:19-22:29). Monster labels only: v2's other frame rules (NPC,
  warp, ...) are not applied here.

  | col3 | the frozen 1a facing | fix2 |
  |---|---|---|
  | labels fitted and kept (not under a box) | 4,501 | 5,088 |
  | excluded under a model box (1c) | 5,285 | 5,266 |
  | excluded unfit / crowd / UI | 815 | **248** |
  | under a box, the fit passes (O3 would keep) | 4,337 (82 %) | 4,760 (90 %) |
  | frames whole: the literal 1c | 87 (5.6 %; col1's 3c: 6.5 %) | 144 (9.3 %) |
  | frames whole: O3 | 543 (35.2 %) | **980 (63.5 %)** |
  | frames whole: no model test at all (the upper bound) | 936 (60.7 %) | 1,321 (85.6 %) |
  | kept labels stacked (IoU >= 0.3 with another kept label; S3) | 85 | 109 |
  | frames whole: O3 + S3 | 529 | 954 |

  - With fix2 the fit itself fails 70 % less often (815 -> 248 labels).
  - O3 with fix2 keeps 980 of the 1,543 frames whole, against 87 today.

| option | what | cost | risk |
|---|---|---|---|
| O1 per-label ignore regions | an excluded monster's box is masked in the image (YOLO has no ignore input), the frame kept | ~0.5 day (build_frame_cache writes masked frames) + a cache rebuild; col2 scoring needs a matching don't-care list | the mask is a visual cue the model can learn; it also hides neighbours |
| O2 a depth test | the 162 placed RSM models' triangles rasterised into a depth buffer per dwell (the GM stands still: ~64-80 renders a block), the sprite's depth from render.anchor_and_depth; a label is hidden where a model surface is IN FRONT of most of its mask | ~1 day (the RSM reader exists) + ~0.5 day for alpha-textured leaves (GRF textures, /dev/shm only); a positive case on col3 (the canopy plants hidden, the boxed orcs visible) | leaves without alpha read as solid; node animation ignored |
| O3 the fit's evidence instead of the 2-D box | a label under a model box is KEPT when its fit passes (>= tau, not at the edge); only a failed fit under a box excludes the frame | a few lines in FixLabeler + tests; minutes to re-label | tau 0.092 is low (a fit can pass on clutter); a hidden monster still excludes its frame; the blind check judges the boxes |
| O4 = O2 + O3 | O2 decides hidden (no label, frame kept), O3 the box | O2's cost | O2's |

**The Orc Skeleton's blind failure (3d: labeller D 86.7 % good; "off" boxes cut weapons; stacked
orcs fitted to the rear one):**
- **S1 fix 2 itself:**
  - The frozen 1a rule drew the wrong image for 19-26 % of col3's Orc Skeleton samples (1a 81.4 /
    74.1 % against fix2 94.9 / 93.8 %).
  - A fit that starts from the mirrored or back image puts the cleaver on the wrong side. That is a
    plausible source of "cuts the weapon", not shown here.
  - Cost: none beyond fix 2. The next blind round measures it.
- **S2 weapon reach:** the box = the fitted frame's box joined with the action's envelope for the
  orcs.
  - Cost: trivial.
  - Risk: looser boxes (the labellers' "loose").
- **S3 stacked orcs:** a label whose fitted box overlaps another kept label's by IoU >= 0.3
  excludes its frame even when its fit passes. Today `crowd` counts only when the fit fails.
  - Cost: trivial code.
  - On col3: 85 (frozen facing) / 109 (fix2) stacked labels of 4,501 / 5,088, so O3 + S3 keeps 529
    / 954 frames whole against O3's 543 / 980. Not split per species here.
- **S4 sample size:** at 30 crops one crop is 3.3 points, and D's 86.7 % is 26 / 30. A larger
  Orc Skeleton sample (e.g. 60) is only valid if fixed BEFORE the round.

**Open questions for Batt:**
1. Pre-register fix 2 as drafted? With 2b and / or 2c, or without?
2. C1 is projected at about 4 % with fix 2 alone. Is a second C1 failure worth running to learn
   from, or is C1 (the PREDICTION, no fit) still the right gate, now that the fitted labels pass the
   blind check for 6 of 7 species (3d)?
3. The occlusion: O1, O2, O3 or O4?
4. The Orc Skeleton: S1 only, or also S2 / S3? And a larger blind sample for it?
5. The packet-heading evidence for the 4-image species rests on about 6 units. Is that enough, or
   should a dwell block record more appearances (any block will, at no extra cost)?

**Where the evidence lives** (client-derived, never committed):
- `/mnt/poring-lab-datasets/scratch-archive/2026-10-22/orc-facing/`:
  - `rows-half1.json`, `rows-half2.json` (every sample);
  - `score.json` (every rule, both halves, the three sample sets, the C1 estimate);
  - `classes.json` (the view classes);
  - `occl_options_{frozen,fix2}.json` (the occlusion options);
  - `viz_axis.png` (the by-eye check);
  - `scratch/` (the exploration scripts).

### 3f. PRE-REGISTERED: label fix 2 with the exclusions 2b and 2c, and the two tiers (Batt 2026-10-22 ~19:4x; pre-registered at the commit time of 3f's first commit, BEFORE fix 2 is built and BEFORE anything runs on col1 or on today's sessions)

**Batt (verbatim), the overnight brief, item C:** "C. GPU: TRAIN THE DETECTOR FOR THIS MAP (accuracy
of engagement). Pre-register label fix 2 + exclusions with the two tiers: TRAINING data passes at
C1 <= 5 % with every species passing the blind check; EVALUATION only on crops both blind labellers
judged good (col2 stays TEST). Add today's orcsdun01 sessions (the bot's runs and my demo, packets
as truth, never col2) as extra training data. If the training tier passes: build the cache (IO
rules), train on the GPU (long-lived worker, MID_CKPT, R3, VRAM cap) with v1's prt_fild08 data (v1
rules + species split) and the 15 classes. Score against v2orc-vs-v1.md only after training ends.
If it doesn't pass: report why."

**Batt, earlier today (verbatim):** "orcsdun01 labels: pre-register fix 2 + exclusions; two tiers:
TRAINING at C1 <= 5 % with every species passing the blind check; EVALUATION only on crops both
blind labellers judged good. Train if the training tier passes."

**The parent's interpretation (stated here, before anything runs; NOT Batt's words):**
- "fix 2 + exclusions" = 3e's DRAFT TEXT (i)-(iii) WITH BOTH optional exclusions, 2b AND 2c, and
  2c is the EXCLUDE variant (not "fit both images and keep the better").
- **The occlusion:** Batt decided none of O1-O4, so 3b's literal 1c rule stays (a label whose
  predicted sprite box overlaps a model's projected box is EXCLUDED; a frame with an excluded
  monster is excluded from the cache).
- **The Orc Skeleton:** S1 is fix 2 itself. S2 (weapon reach) and S3 (stacked orcs) are not
  adopted (no decision); S4 is not adopted (30 crops per species, as 3b).

**The fix, "labels v2orc-fix2": 3b unchanged except the facing (1a) and its mapping to the sprite's
image.** The heading is `orc_facing_study.fix2_heading` (72cb479, confirmed on col3's half 2 in 3e),
reused, never re-derived:
- (i) a monster that appeared standing and has not moved since: its appear heading, mapped as today
  (the Timeline's facing; any unit no rule below covers keeps the Timeline's facing, as in 3b);
- (ii) a WALKING monster (the Timeline state `walk`): the heading of the quadrant diagonal of its
  current move's vector (x1 - x0, y1 - y0), with dx = 0 counted as west and dy = 0 as north
  (north -> NW, east -> NE, south -> SW, west -> NW);
- (iii) a monster NOT walking whose last move has ended (3b's walk rule applies: arrived or cut
  short, no newer turn or attack): map_calc_dir's heading of that move's vector (3b's frozen 1a
  heading); an axis heading takes the diagonal by the same convention, a diagonal stays;
- the heading is drawn with today's mapping (`camera.displayed_direction`).

**The exclusions (each handled as `unfit`: the label is not kept, and its frame is excluded from the
cache; each is counted under its own name):**
- **2b `next_move`:** a monster whose NEXT move packet (an `entity_appear` of kind `move`, 0x09FD,
  for its id) arrives within 150 ms AFTER the label's timeline time (the frame time minus 1d's
  120 ms). Every monster label (standing or walking).
  - 3e's estimate also counted vanish packets. On col3's rows that changes nothing: 2.7 % (half 1)
    and 1.9 % (half 2) either way (measured on col3 only, 19:3x today, before this section was
    committed).
- **2c `ambiguous_view`:** a monster under (iii) whose move was MIXED (dx and dy both non-zero,
  |dx| != |dy|) and whose two candidate images DIFFER: the image of the move vector's quadrant
  diagonal (ii's rule) and the image (iii) names. "Image" = the view class of the action drawn
  (`orc_facing_study.view_classes`: the ACT's directions that draw identical images).

**Frozen, never re-measured:** 1b, 1c, 1d, tau 0.092, k 0.140 and the fit radius (±6 px ground /
±10 px flyers) are 3c's values: `params.json`, sha256 `fe1fb9b3…f6d5af`, frozen 2026-10-21 17:27:20
ICT on col3. col2 is not read by any of it.

**The checks on col1** (the pre-registered fitting / check block): `orc_labels_fix.py check`, the
same tool, parameters and frames as 3c (every 5th frame inside a dwell, outside the GM windows).
C1 and C2 judge the PREDICTION (fix 2's facing, 1b, 1d; no fit), after the 1c, 2b and 2c
exclusions:
- **C1 pooled** = `bad_label` / standing labels scored, over the 7 orcsdun01 species pooled
  (`orc_camera_check.summarize`, as in 3a and 3c). **This is the one number that gates (T1 below).**
- Reported: C1 per species; C2 per species against section 3's bars; the exclusions per reason;
  the facing agreement.

**THE TWO TIERS (operational):**
- **TRAINING tier.** Batt: "TRAINING data passes at C1 <= 5 % with every species passing the blind
  check". orcsdun01 labels train only if BOTH hold:
  - **T1:** C1 pooled on col1 <= 0.050 (the unrounded ratio). For the training decision this
    replaces section 3's < 2 %.
  - **T2:** EVERY orcsdun01 species passes the blind check, round 3:
    - two NEW blind labeller agents;
    - seed 2 (rounds 1 and 2 used 0 and 1);
    - 30 crops per species, drawn from every KEPT fix-2 label of col1 (`--blind-from
      kept_labels`, as round 2), plus col1's Poring controls;
    - the bars of section 5: >= 90 % "good" from EACH labeller AND the species right >= 95 %;
    - scored by `scripts/blind_score.py`;
    - the instructions are round 2's, word for word.
  - **"Every species" (the parent's reading):**
    - one failing orcsdun01 species fails the tier: NOTHING of orcsdun01 trains, and the result
      goes to Batt (3b's per-species exclusion is not applied);
    - a species with fewer than 30 kept labels is sampled whole;
    - a species with none fails T2;
    - the Poring controls are reported and decide nothing.
  - **Reported, NOT gating:** C1 per species, and C1 on today's added sessions (but see "an added
    session" below).
  - **C2 is not one of Batt's tiers.** It is reported against section 3's bars. If it fails for a
    species, the parent tells Batt before any cache is built: a stop, not a verdict.
- **EVALUATION tier.** Batt: "EVALUATION only on crops both blind labellers judged good (col2 stays
  TEST)".
  - col2 stays the TEST block: never read for training, fitting or any parameter, and not read
    before training ends.
  - **The parent's reading, fixed now (it amends v2orc-vs-v1.md's P1 before training; see its
    Amendment A):**
    - after training ends, col2 is labelled with fix 2 (these tools, these frozen parameters,
      every 3rd frame as the cache);
    - an evaluation pack is drawn from col2's KEPT labels: seed 3, up to 60 crops per species (so
      a species can reach P1's 50-label bar);
    - two NEW blind labellers judge it, with the same instructions;
    - a crop is EVALUATED when BOTH answer q1 yes, q2 good, and q3 = the label's species.
  - **P1 per species s, on the frames of the evaluated crops (the position metric):**
    - recall = the evaluated s crops whose box contains the centre of a class-s detection
      (one-to-one per frame) / the evaluated s crops;
    - precision = those matches / the class-s detections whose centre falls inside ANY evaluated
      crop's box;
    - detections elsewhere in the frame are not scored: their truth is not verified.
  - **The bar is P1's own:** recall and precision >= 0.80 for a species with >= 50 evaluated crops;
    fewer: reported, no bar.

**The extra training data: today's orcsdun01 sessions** (Batt: "the bot's runs and my demo,
packets as truth, never col2").

| session | what | frames | packets | labelled? |
|---|---|---|---|---|
| `20261022T114129-demo-dungeon-A-pilot1` | 3.98 pilot 1 (A) | none | yes | no: no frames |
| `20261022T115210-demo-dungeon-B-pilot2` | 3.98 pilot 2 (B) | none | none | no: neither |
| `20261022T115747-demo-dungeon-B-pilot3` | 3.98 pilot 3 (B) | 5 strike shots | yes | no (below) |
| `20261022T120309-demo-dungeon-C-pilot4` | 3.98 pilot 4 (C) | 9 strike shots | yes | no (below) |
| `20261022T120918-demo-dungeon-A-r1-attempt1-stopped` | 3.98 run 1, attempt 1 | none | none | no: neither |
| `20261022T121416-demo-dungeon-A-r1` | 3.98 run 1 (A) | 40 strike shots | yes | no (below) |
| `20261022T124204-demo-dungeon-B-r2` | 3.98 run 2 (B) | 23 strike shots | yes | no (below) |
| `20261022T131504-demo-dungeon-B-r3-attempt1-stopped` | 3.98 run 3, attempt 1 | 17 strike shots | none | no: no packets |
| `20261022T132000-demo-dungeon-B-r3` | 3.98 run 3, attempt 2 | 40 strike shots | yes | no (below) |
| `20261022T133358-demo-dungeon-B-r3` | 3.98 run 3 (B) | 40 strike shots | yes | no (below) |
| `20261022T142105-demo-dungeon-mr-B-mrpilot` | 3.99 pilot (MR) | 4 strike shots | yes | no (below) |
| `20261022T142950-demo-dungeon-mr-B-mr1` | 3.99 run 1 (MR) | 40 strike shots | yes | no (below) |
| `20261022T151124-demo-dungeon-C-r4` | 3.98 r4 (C) | 40 strike shots | yes | no (below) |
| `20261022T155122-demo-dungeon-B-r5` | 3.98 r5 (B) | 40 strike shots | yes | no (below) |
| `20261022T163311-demo-dungeon-A-r6` | 3.98 r6 (A) | 40 strike shots | yes | no (below) |
| `20261022T171500-demo-dungeon-mr-B-mr2` | 3.99 run 2 (MR) | 40 strike shots | yes | no (below) |
| `20261022T184536-demo-human-demo-orcsdun01-crusader` | Batt's Crusader demo | **4,880** (5 Hz, JPEG q80, `human-demos/<sid>/frames`) | yes (5,283 events) | **yes, with the adapter below** |

- **The bot's runs (3.98 / 3.99) recorded NO continuous frames.** `dungeon_hunt.py` keeps at most
  40 `strike-NNN.jpg` per run: evidence frames for the judge's eye.
  - **The capture time is not stored.** The grab happens between the strike event's `t_ns` (the
    first click) and `t_end_ns` (after the JPEG save). A label needs the frame's time to within
    1d's scale (120 ms), or every moving monster is misplaced.
  - **Every shot shows the Crusader in contact with its target** (the crowd rule).
  - So they are NOT labelled, and not forced. Recording frames in the runner is a separate
    change, not made here.
- **Batt's demo is labelled by the SAME rules, with an adapter in the label tools (built after this
  commit):**
  - **Frames:** the JPEG files, each named `<k>-<t_mono_ns>.jpg`, the capture time. The recorder
    grabs through the same `ro_agent.Screen` path at 5 Hz q80 as `warp_watch`, so 1d's 120 ms
    applies.
  - **The moving camera:** the label stack places the camera at the Timeline's own position at each
    frame's timeline time (our `self_move`s, walked), as for any frame. No change.
  - **The UI:** the demo records no layout. Its frames show Batt's hunting layout. The rectangles
    are `client_layout.RECTS["hunt"]`.
    - A frame is labelled only if `client_layout.read` (pixels) says it IS the hunt layout; any
      other frame is EXCLUDED (`ui_layout_mismatch`).
    - Other windows Batt may open (inventory, skills, item notices) are NOT detected. That is a
      known limit, reported.
  - **The candidate frames:** every frame on orcsdun01, outside the GM windows (there are no
    dwells). C1 uses every 5th frame, as on col1; the labels use every 3rd frame, as the cache.
  - **An added session trains only if:**
    - the training tier passes (on col1, above); AND
    - its OWN C1 pooled is <= 0.050 on >= 50 standing labels scored (Batt: "TRAINING data passes
      at C1 <= 5 %"); with fewer it is not added (no measure).
  - **It is NOT blind-checked separately.** The blind check is col1's round 3, as Batt said. The
    demo's own conditions (fights, a moving camera, the Crusader's v0-size `player` box) are
    reported as limits.
- **Not added:** the 2026-10-21 demo (`20261021T175710-demo-human-demo-orcsdun01-crusader`).
  Batt's words are "today's".

**What follows if the training tier passes** (the parent's steps, under the IO rules and R1-R3):
- **The combined cache:**
  - orcsdun01's TRAIN blocks (col1, col3) plus the added sessions that qualify;
  - fix 2's fitted monster boxes, v2's frame rules, the literal 1c rule, the 15 classes;
  - v1's prt_fild08 sessions with v1's rules and the species split (3b item 2), split by session
    as v1's cache.
- Then training and the v2orc-vs-v1.md score, ONCE, after training ends.
- **If the tier fails, nothing trains,** and the report says which condition failed and by how
  much.

**Expected, from col3 (an estimate, not a bar):** C1 about 1.9-2.7 % with fix 2 + 2b + 2c (3e),
under T1's 5 %. T2 is the open question: round 2's Orc Skeleton failed at 86.7 % for one labeller.

### 3g. RESULT of fix 2 (3f) on col1 and on Batt's demo: T1 PASSES (C1 2.7 %); T2 waits for the blind round 3

**The order of events** (times from `date` and the tools' own stamps, 2026-10-22 ICT):
- 3f was pre-registered at **19:33:52** (8b7d629). Read before it:
  - col3's archived rows, for the 2b estimate;
  - the file lists and manifests of today's sessions;
  - the demo's frame 1000, viewed by eye for its UI layout.

  Nothing was labelled or checked on col1 or on today's sessions before that commit.
- Fix 2 was built at 19:41:51 (11434a8), and the check ran at 19:42-19:43 at that commit.
- col2 was not read.

**The tool first reproduced 3c (a positive control):** the same check with `--rule 1a` at 11434a8
gives 3c's numbers exactly: 1,366 standing labels scored, 213 `bad_label`, 15.59 %.

**THE CHECK on col1** (`orc_labels_fix.py check --rule fix2`, 3c's frozen parameters, params sha256
`fe1fb9b3…f6d5af`; every 5th frame inside a dwell, outside the GM windows: 2,325 frames read).
C1 / C2 judge the PREDICTION, after the 1c, 2b and 2c exclusions:

| species | standing scored | 1c excluded | 2b `next_move` | 2c `ambiguous_view` | C1 `bad_label` (3c, 1a) | C2 median \|dx\| / \|dy\| px |
|---|---|---|---|---|---|---|
| Orc Zombie 1153 | 610 | 874 | 31 | 46 | 4.1 % (17.5) | 1 / 1 PASS |
| Orc Skeleton 1152 | 113 | 91 | 6 | 12 | **0.0 %** (29.8) | 1 / 1 PASS |
| White Plant 1082 | 125 | 107 | 0 | 0 | 0.0 % (0.0) | 1 / 1 PASS |
| Black Mushroom 1084 | 0 | 132 (every one) | 0 | 0 | -- (none left after 1c) | -- |
| Familiar 1005 | 169 | 256 | 7 | 15 | 1.2 % (12.0) | 1 / 1 PASS |
| Steel Chonchon 1042 | 160 | 116 | 7 | 11 | 3.1 % (15.7) | 1 / 1 PASS |
| Drainliar 1111 | 50 | 37 | 3 | 7 | 2.0 % (5.4) | 1 / 1 PASS |
| **pooled** | **1,227** | 1,613 | 54 | 91 | **2.69 %** (33; 3c 15.6) | |

- **T1 PASSES:** C1 pooled 0.0269 <= 0.050.
  - The tool's own `verdict` field still says FAIL. It judges against section 3's < 2 %, which is no
    longer the training gate (3f).
  - The 3e estimate on col3 was 1.9-2.7 %.
- **C2 passes for every species with >= 20 standing labels.** All are at 1 / 1 px.
- **The other drops** are unchanged from 3c: not standing 6,297; crowded 5,463; under the UI or at
  an edge 1,275.
- **Reported, not deciding: the facing, by IMAGE** (3e's finding 0: the heading ties are counted
  as the same view).
  - fix 2's view equals the best of the 8 on 94.1 % of the labels; 1a's on 76.1 %.
  - Per species, fix 2: Orc Zombie 94.1, Orc Skeleton 91.2, White Plant 100, Familiar 93.5, Steel
    Chonchon 98.8, Drainliar 72.0 %.

**THE LABELS on col1** (`orc_label_sheets.py --fix PARAMS --rule fix2`, every 3rd frame as rounds 1
and 2: 5,010 frames; v2's own frame rules keep 4,343):

| species | kept (fitted) | 1c | 2b | 2c | unfit | crowd | UI | (3c kept) |
|---|---|---|---|---|---|---|---|---|
| Orc Zombie 1153 | 7,305 | 8,866 | 172 | 376 | 175 | 95 | 44 | (6,942) |
| Orc Skeleton 1152 | 753 | 893 | 24 | 58 | 20 | 3 | 5 | (710) |
| White Plant 1082 | 722 | 623 | 0 | 0 | 0 | 9 | 0 | (722) |
| Black Mushroom 1084 | 56 | 1,719 | 0 | 0 | 0 | 0 | 0 | (56) |
| Familiar 1005 | 1,384 | 1,823 | 45 | 81 | 17 | 9 | 10 | (1,294) |
| Steel Chonchon 1042 | 1,215 | 970 | 39 | 99 | 20 | 1 | 10 | (1,198) |
| Drainliar 1111 | 381 | 318 | 11 | 13 | 8 | 1 | 0 | (390) |
| all | 11,816 | 15,212 | 291 | 627 | 240 | 118 | 69 | (11,312) |

- **The fit fails far less often:** unfit + crowd + UI = 427 labels, against 3c's 1,847.
- **Frames labelled whole:** 356 of the 4,343 (3c: 283). The literal 1c rule still decides that
  (3,851 frames have a monster under a model box). O1-O4 remain Batt's call.

**THE BLIND PACK, round 3 (T2), built, NOT run** (the parent launches two NEW blind labeller agents):
- seed 2; 30 crops per orcsdun01 species, drawn from every KEPT fix-2 label of col1. Every species
  has >= 30 (Black Mushroom 56).
- Plus col1's 15 Poring controls: 225 crops, 12 numbered grids, the reference sheet A-L.
- **The pack:** `/mnt/poring-lab-datasets/scratch-archive/2026-10-22/orc-fix2/blind-pack-seed2/`,
  with `instructions.txt` = round 2's word for word (byte-identical).
- **The answer key, in its own directory:** `.../orc-fix2/answer-key-seed2/answer_key.json`.
- **The score:** `scripts/blind_score.py --key <key> <answers A> <answers B>`, with section 5's
  bars.

**Batt's demo (`20261022T184536-demo-human-demo-orcsdun01-crusader`), labelled by the same rules
through the adapter (a625def). Under 3f it is NOT added: its own C1 is 14.8 %.**
- **C1:** 22 `bad_label` of 149 standing labels (every 5th frame: 976 frames read). That is over
  5 %, and >= 50 labels were scored, so 3f's rule leaves it out.
  - Per species: Orc Zombie 11 / 65 (16.9 %), Steel Chonchon 8 / 54 (14.8 %), White Plant 3 / 14,
    Familiar 0 / 16.
  - C2: Orc Zombie 2 / 1 px, Steel Chonchon 2 / 1 px.
- **Split by our own motion (reported, not deciding):**
  - the Crusader moving: 5 / 12 (41.7 %), C2 median 13 / 9.5 px. The camera is misplaced during
    our own walks: frame 1000's minimap reads "88 123", which the Timeline gives at ~376 ms, not
    at 120 ms;
  - the Crusader still: 17 / 137 (12.4 %), C2 1 / 1 px.
- **By eye, on the 22 low crops:**
  - orcs ENGAGED with the Crusader are drawn facing another way than any rule says. Fix 2 was
    measured on col3, where the GM was immune and nothing fought;
  - boxes are shifted while the Crusader walks;
  - three White Plants.
- **What it would have added** (every 3rd frame, 1,627 candidates):
  - 261 whole frames and 1,747 kept monster labels;
  - the hunt-layout check excluded 2 frames.
- **The bot's 3.98 / 3.99 runs add nothing:** they recorded no frames (3f).

**v1's prt_fild08 data, "v1 rules + species split": BUILDABLE.**
- **The tool:** 347db05, `build_frame_cache.py --labels v1 --classes species --kb DIR`. It keeps
  v1's frames and boxes and gives each its class id per species. Batt's 3b item 2 and 3f.
- **The dry run** (packets and indexes only, 19:51-19:59, v1png's arguments: `--every 15
  --every-png 1`, its split):
  - every one of v1's 10 sessions keeps EXACTLY v1png-20261008's frames and boxes (kept, GM
    window, off scene, boxes all equal), with 0 species exclusions;
  - train 8,193 frames: 14,658 npc, 20,558 Poring, 738 Lunatic, 164 Pupa, 779 Drops;
  - val 3,242 frames; test 2,511 frames;
  - Creamy: 0 boxes; `player`: 0 (v1 never labels our own GM).
- Section 6's labels-v2 route kept 3.3 % of the frames. This one keeps all of v1's.

**Where the outputs live (client-derived, never committed):**
`/mnt/poring-lab-datasets/scratch-archive/2026-10-22/orc-fix2/`:
- `col1/` (`check_fix2.json`, `check_rows_fix2.json`, `check_1a_repro.json`, the labels'
  `labels_summary.json` and `sheets/`);
- `blind-pack-seed2/` and `answer-key-seed2/`;
- `demo/` (the check and its rows, the labels' summary);
- `v1-dry-run/dry.json`;
- `params.json` (the frozen 3c file, the same sha256).

**NEXT (the parent's):**
1. Run blind round 3 (T2).
2. If every orcsdun01 species passes, the training tier passes. Before training, the cache needs
   two changes that do not exist yet:
   - **`--fix PARAMS --rule fix2` in `build_frame_cache.py`'s v2 path.** Today the fitted fix-2
     boxes come only from `orc_label_sheets.py`. A cache built now would carry v2's PREDICTED
     orcsdun01 boxes instead.
   - **Two label modes in ONE cache:** `train.py` reads one `--cache`. v1's sessions need
     `--labels v1 --classes species`, the orcsdun01 blocks `--labels v2 --classes species --fix`,
     and one build takes one `--labels`.
3. If a species fails, nothing of orcsdun01 trains, and the result goes to Batt.

### 3h. RESULT: blind round 3 (T2) -- FAILS on ONE species, Familiar; by 3f NOTHING of orcsdun01 trains (scored 2026-10-22 ~20:1x ICT)

- **The round:** two NEW blind labeller agents, E and F, each seeing only `blind-pack-seed2/`
  (seed 2; 30 crops per orcsdun01 species from the KEPT fix-2 labels + 15 Poring controls = 225;
  round 2's instructions, byte-identical). Scored by `scripts/blind_score.py` against
  `answer-key-seed2/answer_key.json`; `answers-round3/score.json` and `both-good.json` on the NAS
  (`scratch-archive/2026-10-22/orc-fix2/`).
- **Bars (section 5, unchanged):** >= 90 % good from EACH labeller AND species right >= 95 %.

| species | E good / species (off) | F good / species (off) | T2 |
|---|---|---|---|
| Orc Zombie 1153 | 96.7 / 96.7 (1) | 96.7 / 96.7 (1) | PASS |
| Orc Skeleton 1152 | 96.7 / 100 (1) | 96.7 / 100 (1) | PASS (round 2: 86.7 % FAIL) |
| White Plant 1082 | 100 / 100 | 100 / 100 | PASS |
| Black Mushroom 1084 | 100 / 100 | 100 / 100 | PASS |
| **Familiar 1005** | **86.7** / 96.7 (**4**) | 93.3 / 96.7 (2) | **FAIL (E)** |
| Steel Chonchon 1042 | 96.7 / 100 (1) | 96.7 / 96.7 (1) | PASS |
| Drainliar 1111 | 96.7 / 100 (1) | 96.7 / 100 (1) | PASS |
| (Poring 1002, control) | 100 / 100 | 100 / 100 | PASS |

- **Agreement E-F:** q1 225 / 225, q2 223 / 225, q3 224 / 225; good with the right species for
  both: 216 / 225 (round 2: 211).
- **What failed (crops checked against the key):** the Familiar's not-good boxes are E 032 / 056 /
  108 / 109 and F 032 / 108. Three cut a raised WING tip (056, 108, 109), as round 2's labellers
  said of the bats; 032 is a Familiar STACKED on an Orc Skeleton (the box held the skeleton's
  helmet; 3e's S3 case). One crop is 3.3 points at n = 30: E's 26 / 30 against the 27 / 30 the bar
  needs.
- **THE TRAINING TIER (3f): T1 PASS (C1 2.69 %), T2 FAIL -> NOTHING of orcsdun01 trains tonight,
  and the result goes to Batt** ("every species" is read literally, 3f). The GPU stays idle.
- **For Batt (new decisions, not taken here):** (1) a wing-reach box for the bats (3e's S2 idea,
  the action's envelope joined to the fit, for the Familiar and the Drainliar); (2) train without
  the Familiar class's orcsdun01 labels (its frames kept, the box ignored -- O1's mask problem); (3)
  accept the Familiar on F's 93.3 % with E's at 86.7 % (a single crop short). The cache tooling for
  the next attempt (`build_frame_cache --fix`, per-session label modes) is being built anyway
  (feat/orc-cache). ➡️ MERGED 2026-10-22 20:38 (c507a9b): `--fix PARAMS --rule fix2 --fix-sha256`,
  `--v1-species-sessions`, `--collection orcsdun01`, col2 refused; the exact `cache@` step and the
  dry run are on the NAS (`orc-fix2/cache-dry-run/`).
- **The dry run's finding (for the occlusion decision):** under 3b's literal 1c rule the combined
  TRAIN would hold <= 8,850 frames, of which orcsdun01 <= 657 (~7.4 %; col1 <= 397, col3 <= 260;
  1c excludes 3,851 + 3,234 frames). Boxes per orcsdun01 class (upper bounds): Orc Zombie 1,275,
  Orc Skeleton 241, Steel Chonchon 198, Familiar 155, Drainliar 64, White Plant 16, Black Mushroom
  0. Batt's O1-O4 occlusion choice (3e) is what would change that.

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

➡️ Round 2 (the label fix's fitted boxes, seed 1) ran in 3d. Round 3 (fix 2, seed 2) is
pre-registered in 3f.

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
    ➡️ **DECIDED and BUILT:** Batt's 3b item 2 / 3f say "v1 rules + species split".
    `build_frame_cache.py --labels v1 --classes species` (347db05) keeps ALL of v1png's frames and
    boxes in its dry run (3g).
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
