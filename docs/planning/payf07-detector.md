---
doc_type: design
hypothesis: "Packet labels with the orcsdun01 o3h rule (fix 2 facing, 2b / 2c, the map's RSW models with a fit-evidence gate), re-measured on pay_fild07's own FIT data, give per-species monster boxes for pay_fild07 (Elder Willow, Willow, Eggyra, Bigfoot, Poporing, Green Plant) that pass the training tier (T1: C1 <= 5 % on the held-out TEST data; T2: every species passes a blind check), so ONE detector can be trained on v2orc's classes plus this map's species."
status: "STOPPED 2026-10-25 12:40 ICT by Batt's target change (gef_fild10 instead; 13g), after epoch 1 of 10 (val mAP50 0.800). The run: payf07-20261024 on the cache v2orc-payf07-20261024 (16,793 TRAIN frames), launched 02:56:41 (13f), 7 attempts (2 IO trips, 4 R3-HARD camera-drop aborts). Training tier PASSED 2026-10-24 19:52 ICT (T1 under Amendment C, 10k; T2 round 2, 11a). payf07-eval.md is NOT scored."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [orcsdun01-detector.md, thief-payon.md, payf07-prep.md, labels-v2-plan.md, training-cost.md, ../benchmarks/v2orc-vs-v1.md, ../benchmarks/payf07-eval.md]
next_action: "None here. The parent archives data/train/payf07-20261024 to the NAS (13g); its epoch-1 last.pt is a candidate init for gef_fild10's detector (rogue-gef10.md 6), where ENGAGED units are part of the label pre-registration."
title: "A detector for pay_fild07's monsters: the facts, the split, the label rule, the two tiers and the class scheme (pre-registered)"
date: 2026-10-24
owner: Batt
---

# A detector for pay_fild07's monsters (pre-registered)

**Batt, 2026-10-24 ~18:0x ICT (as relayed by the parent):** "I think you should train YOLO for the
monsters in this map too." His clip showed the Thief standing next to an Elder Willow, taking hits
for ~50 s: the engagement hovers ring cells for the client's SWORD cursor, and the cursor read
failed over the swaying Elder Willow sprite (12 scans, "clear" / "unknown"). A detector that sees
the map's monsters directly lets the bot strike the box.

**This document covers the LABEL side up to the training tier.** The GPU training (R1-R3, the
long-lived vision worker) is the parent's, and only if the tier passes. The evaluation of a trained
model is pre-registered separately, before training (section 8 proposes it).

**The rule of this document:** everything below is fixed at the commit time of its first commit.
A change after that is a clock-labelled AMENDMENT, written and committed BEFORE the step it
changes. A failed tier is reported, never re-run under the same bars.

## 1. The facts (read before this commit)

### 1a. What was read before this commit (and nothing else)

- The four sessions' `manifest.json` and their packet logs' event-type counts, species appearance
  counts (name, job) and the `map_change` / `drop_request` / GM-chat times. No monster POSITION was
  used for anything.
- Two frames of the staged session's spot 0 (a FIT spot, 3a), by eye: frame 57 (the inventory
  window open during the drops) and frame 76 (the hunting layout, the inventory closed).
- The client data, extracted to /dev/shm (client-derived, never committed):
  - `pay_fild07.rsw` (MIXCRYPT, decoded with `grf_read.py --decode-mixcrypt`, Batt 2026-10-05
    option (a), study only) and its 9 RSM models: `/dev/shm/poring-lab-tmp/payf07/grf/`;
  - the six species' SPR / ACT (`sprite_catalog.py --decode-mixcrypt`):
    `/dev/shm/poring-lab-tmp/payf07/sprites/`; their client stems
    (`npc_sprites.py mob-names`) and catalog: `/dev/shm/poring-lab-tmp/payf07/kb/`.
- No TEST frame, no label, no check.

### 1b. The species (pinned rAthena e985006, pre-renewal, `data/kb`)

| species (mob id) | spawns on pay_fild07 | walk (ms / cell) | idle sprite box (native px) | flies? | sprite |
|---|---|---|---|---|---|
| Elder Willow (1033) | 70 | 200 | -33 -60 33 15 | no | `elder_wilow` |
| Eggyra (1116) | 40 | 200 | -16 -50 16 10 | no | `eggyra` |
| Bigfoot (1060) | 30 | 300 | -42 -94 36 15 | no | `bigfoot` |
| Poporing (1031) | 20 | 300 | -18 -30 18 6 | no | `poporing` |
| Willow (1010) | 20 | 200 | -33 -60 33 15 | no | `wilow` |
| Green Plant (1080) | 8 | immobile | -20 -15 20 15 | no | `green_plant` |

- **No species flies:** every idle box reaches the ground (y1 > 0). orcsdun01's flyer rules (1b's
  anchor, the ±10 px fit, W) therefore do not apply (section 4).
- **Three look-alike pairs differ mainly in COLOUR** (the rendered idle sprite's mean hue /
  saturation, `orc_camera_check.reference_hue`):
  - Elder Willow 358° / 0.54 vs Willow 350° / 0.30: the SAME ACT geometry, a recoloured SPR (the
    same size); they differ in SATURATION only;
  - Poporing 74° / 0.30 vs Poring (v2orc class 3) 2° / 0.40: the same box; hue differs;
  - Green Plant 83° / 0.42 vs White Plant (v2orc class 10) 36° / 0.06: the same box; saturation
    and hue differ.
  - The blind check's reference therefore shows both members of each pair (section 6), and the
    class scheme flags the training's saturation augmentation (section 7).
- **The map:** 400 x 400 cells, a forest. Client and server agree on every walkable cell
  (payf07-prep.md 2). Not indoor: the fitted OUTDOOR camera plus the GAT altitude, as orcsdun01.
- **The RSW:** version 2.1, **1,212 models from 9 RSM files**, all trees and plants (the file
  names, translated): leaves (549 placed), two bushes (322, 20), a tree (79), the Payon willow
  (73), two trunks (61, 55), two vines (43, 10). The leaf planes float
  ~30-43 altitude units up: a projected 2-D model box covers much of the screen, so most labels
  will be "under a model box" and the fit's evidence decides (o3h, section 4).

### 1c. The sessions (NAS, recorder v5, RDP via the frame bus, 1 fps lossless PNG, 1280 x 720)

| session | what | frames | packets | role (section 3) |
|---|---|---|---|---|
| `20261024T170356-rdp-stage-items-b` | the Thief IMMUNE, still at 12 spots x (centre + 4 offsets), @warp only; 48 staged floor items; 17:04-17:31 | 1,538 | 1,617 events | spots 0-7: FIT + TRAIN; spots 8-11: TEST |
| `20261024T123622-rdp-thief-t1b` | 4.03 hunting run (walk-and-hit, fights, sitting) | 2,271 | 3,064 | FIT + TRAIN |
| `20261024T131838-rdp-thief-t2` | 4.03 hunting run | 2,292 | (not opened) | TEST |
| `20261024T164555-rdp-thief-s-pilot` | 4.04 pilot | 523 | (not opened) | TRAIN |
| `20261024T173322-rdp-thief-s1` | 4.04 run s1 (shipped during this work; the parent's message) | 1,950 | (not opened) | TRAIN |
| `*-rdp-thief-s2` ... `s6` and later | 4.04 runs to come | ~2,400 each | | TRAIN, by the join rule (3c) |

- **The staged session's structure** (from its `map_change` and `drop_request` times): each spot
  starts with a `@warp` to its centre; the @item lines and the four drops follow (the inventory
  window is OPEN during the drops: frame 57); then four offsets (+-3 cells, same-map @warp)
  ~16.7 s apart. The spots are >= 25 cells apart (thief-payon.md 4e).
- t1b starts and ends on prt_fild08 (its first and last minutes; Porings there). Only frames on
  pay_fild07 are ever labelled.

## 2. What is reused from orcsdun01, unchanged

From `orcsdun01-detector.md` (3b, 3f, 3i, 3l; o3h won in 3m) and its tools:
- **fix 2's facing** (3f (i)-(iii), `orc_facing_study.fix2_heading`) and its exclusions **2b**
  (`next_move`, 150 ms timeline time) and **2c** (`ambiguous_view`);
- **boxes from the sprites:** the expected sprite (species, the Timeline state's action, fix 2's
  facing, the one-shot frame from its elapsed time or a looping action's best frame) at the
  projected position at the 1d time; the LABEL box = the best masked-NCC fit within ±r px; a fit
  below tau 0.092, at the search edge or unscorable is EXCLUDED (`crowd` / `ui` / `unfit`);
- **k 0.140, tau 0.092, the search ±16 px for C2;**
- **the standing rule for C1 / C2** (idle >= 1 s, isolated 120 px from every unit incl. our own
  character, the box grown by 16 px clear of the UI and the frame edge);
- **o3h:** a label whose predicted box overlaps a model's projected box is KEPT when its fit passes
  AND its fit NCC >= T_h, else EXCLUDED (`occluded_model`). No S3, no W.
- **A frame with any excluded monster label is not labelled whole** (it is excluded from the
  cache; section 5 of the orcsdun01 plan).
- **The crowd box of our own character:** the v0-size box, as in orcsdun01's labeller.

## 3. The split (FIT / TRAIN / TEST)

### 3a. The staged session, by spot

- Spot k = the time from its centre `@warp` (the k-th `map_change` that is followed by
  `drop_request`s before the next `map_change`) up to the next spot's centre `map_change` (the last
  spot: to the end of the session). Spots are numbered 0-11 in time order.
- **Spots 0-7 are FIT (and TRAIN); spots 8-11 are TEST.** This is the same split by spot as the
  target-items study's (thief-payon.md 4e: "0-7 fit, 8-11 test"), so the TEST places of both
  studies are the same frames.

### 3b. The sessions

- **FIT** (every parameter is measured here and only here): staged spots 0-7 + `t1b`.
- **TEST** (never read for fitting or training; read only by T1, after the parameters are frozen,
  and later by the model evaluation): staged spots 8-11 + `t2` (the whole session).
- **TRAIN:** staged spots 0-7, `t1b`, `s-pilot`, `s1`, and every later session admitted by 3c.
- **T2's pool** (the blind check judges the labels that train): the kept labels of staged spots
  0-7, `t1b`, `s-pilot` and `s1` (the TRAIN sessions shipped when this was written).

### 3c. The join rule for later sessions (no re-registration needed)

A session recorded AFTER this commit joins TRAIN (never TEST) when ALL hold:
- the same recording path: manifest `backend` rdp, `recorder_version` 5, `format` png,
  `game_region` [80, 77, 1280, 720], `server` lab-rathena, `packets.jsonl.gz` present;
- the hunting layout, read from pixels per frame (section 4f);
- labelled by the frozen parameters with the frozen tool, unchanged;
- **its OWN C1 pooled (T1's measure on that session) <= 0.050 on >= 50 standing labels scored**
  (orcsdun01 3f's added-session rule); with fewer, it is not added (no measure).
- It is not blind-checked separately.

The same own-C1 rule applies to `t1b`, `s-pilot` and `s1` (TRAIN sessions that are not staged
FIT spots). The staged FIT spots train when the tier passes (as orcsdun01's col3 did).

## 4. The label rule, "labels payf07-o3h" (what changes for pay_fild07, and why)

### 4a. Map and models
pay_fild07, 400 x 400; its RSW and 9 RSMs from the client GRF (1b); their sha256 are frozen with
the parameters. The occlusion test is orcsdun01's 1c (each model's projected vertex box).

### 4b. 1d: the packet -> frame offset, RE-MEASURED on FIT
- **Why:** this is another grab path (the 1-fps recorder via the RDP frame bus, PNG) than
  orcsdun01's warp_watch (5 Hz JPEG shards, 120 ms), and the hunt path showed ~0.4-0.6 s.
- **How:** orcsdun01 1d's method unchanged: moving walkers walking ONE move through the whole
  sweep, isolated 120 px, clear of the UI / edges by 16 px and of every model box at every offset;
  the error = |best-NCC offset| within ±16 px of the rendered walk sprite at the packet position;
  the smallest MEDIAN error wins (coarse 50 ms 0..1000, then 10 ms ±50).
- **The walkers:** every mobile species (1033, 1116, 1060, 1031, 1010; none flies).
- **The frames:** FIT's candidate frames (4e, 4f), every frame.
- **Stop:** fewer than 50 walker samples, or the best coarse offset at the sweep's edge (0 or
  1,000 ms): nothing is frozen; the result goes to Batt with a proposal.

### 4c. 1b: no anchor
No species flies (1b), so no anchor is applied. The per-species median best-NCC offset of FIT's
standing labels is REPORTED (reference only).

### 4d. The fit radius
±6 px for every species (orcsdun01's ground value).

### 4e. o3h's threshold T_h, RE-MEASURED on FIT
- **Why:** orcsdun01's 0.48 was col3's (a dark dungeon, JPEG q80). This map is a forest in daylight
  and shadow, on lossless frames.
- **How:** orcsdun01 3i's definition: the pooled 5th percentile of the fit NCC of FIT's kept labels
  that lie CLEAR of every model box (every frame of FIT's candidates; the fit, tau and edge rules of
  section 2). Frozen to 3 decimals.
- Reported with it: the fit NCC distribution of FIT's under-box labels.

### 4f. The frames a label may come from (the candidate frames)
A recorded frame (capture time t; timeline time tw = t - 1d) is a candidate only when ALL hold:
- the map at tw and at t is pay_fild07, and no `map_change` lies in [t - 5 s, t] (the loading
  screen and the settle after a @warp or a Fly Wing);
- **our character stands still:** its Timeline position is the same at every 100 ms step from
  tw - 1,000 ms to t (the camera does not move; the 3g demo showed C1 41.7 % while our character
  walked);
- outside the GM-command windows (as ever);
- **staged session only:** outside its spot's inventory span, [the spot's first `drop_request`
  - 20 s, its last `drop_result` + 5 s] (the inventory window is open, frame 57, and is not one of
  the layout's rectangles);
- **the hunting layout, read from pixels** (`client_layout.read` = `hunt`, as the 3f demo adapter);
  else excluded (`ui_layout_mismatch`). The UI rectangles are `client_layout.RECTS["hunt"]`. Other
  windows are not detected: a known limit, reported.

### 4g. Frame-level exclusions (a frame is not labelled whole)
On top of section 2's "any excluded monster label":
- a visible warp portal or NPC (objtype 6; pay_fild07 has only its 4 edge warps): `warp_in_view`
  (the warp class's own rule is not built for this map);
- another player (objtype 0 other than us): `other_player`;
- a visible monster of a species without a class or without its own T2 pass (e.g. Green Plant
  under 7's rule): `unchecked_species`.

### 4h. Frozen with the parameters
1d, T_h, tau, k, the fit radius, the RSW / RSM sha256, the tool's commit; the file
`/dev/shm/poring-lab-tmp/payf07/params.json` and its sha256, recorded in the RESULT section. TEST is
refused by the measuring commands (by session name and by spot).

## 5. T1: the geometric check (C1), on TEST

- **Data:** TEST (staged spots 8-11 + `t2`), every candidate frame (4f).
- **C1** = `bad_label` / standing labels scored (`label_check.classify`), pooled over the six
  pay_fild07 species: the PREDICTION (fix 2's facing, the 1d time, no anchor, NO fit) at the
  projected position, after o3h's under-box rule (an under-box standing label counts only when its
  fit passes and its NCC >= T_h), 2b and 2c.
- **T1 PASSES when C1 pooled <= 0.050** (the unrounded ratio; Batt's training-tier bar, 3f).
- **Reported, not gating:** C1 per species and per TEST part (staged / t2); C2 per species (median
  |dx|, |dy| of the best-NCC offset within ±16 px; bar <= 4 px, every species is ground, for a
  species with >= 20 standing labels); the exclusions by reason; the facing agreement by image;
  C1 split by our own motion (should be empty: 4f).
- **C2 failing for a species is a STOP** (as 3f): the parent tells Batt before any cache.

## 6. T2: the blind check (the parent runs the labellers)

- **The labellers:** two NEW blind labeller agents, launched by the parent. Each sees ONLY the pack
  directory and `instructions.txt` = `docs/planning/payf07-blind-instructions.txt` (sha256
  `dc3ee728ba5637c2416fcd34775e3ed7b5bc22afeae6096bdec8eb378d1c19f9`). The answer key lives in
  another directory.
- **Why new instructions:** orcsdun01's (sha256 `1253e64b…fae13`) say "the game scene is dark (a
  dungeon); sprites may be lit by torches". This map is a forest field, and three look-alike pairs
  differ in colour (1b). The questions, the answer format and the box drawing are unchanged.
- **The seed:** 21.
- **The sample:** per species, the T2 pool's KEPT labels (3b; every candidate frame, o3h) sorted by
  (session, frame, gid), shuffled with `random.Random(f"payf07:21:{mob}")`; the first 30. Fewer
  than 30: all of them. None: that species fails T2. No controls (the look-alike classes are in the
  reference instead).
- **The reference** (`reference.png`): 12 species under letters A-L in a seeded order, MULTI-VIEW
  (orcsdun01 3l: the idle action in directions 0, 2, 4, 6, each at frame 0 and its middle frame,
  identical images once): the six pay_fild07 species + Poring, White Plant (the look-alikes) +
  Lunatic, Pupa, Drops, Creamy (prt_fild08, as orcsdun01's sheet).
- **The bars (unchanged):** for EACH species, >= 90 % "good" from EACH labeller AND the species
  right on >= 95 %. Scored by `scripts/blind_score.py --key KEY A.json B.json`.
- **T2 passes when every species in the tier passes** (Green Plant per section 7's rule).

## 7. The class scheme (PROPOSED; Batt's default if he does not answer by the time the labels pass)

**ONE model:** v2orc's 15 classes, ids 0-14 UNCHANGED (`config/detector/classes-v2orc.json`), plus
this map's species appended:

| id | class | mob id |
|---|---|---|
| 0-2 | player, npc, warp | (v2orc) |
| 3-14 | Poring, Lunatic, Pupa, Drops, Creamy, Familiar, Steel Chonchon, White Plant, Black Mushroom, Drainliar, Orc Skeleton, Orc Zombie | (v2orc) |
| 15 | Elder Willow | 1033 |
| 16 | Willow | 1010 |
| 17 | Eggyra | 1116 |
| 18 | Bigfoot | 1060 |
| 19 | Poporing | 1031 |
| 20 | Green Plant | 1080 (conditional, below) |

- **No pay_fild07 species is already a class** (v2orc lists 1002, 1063, 1008, 1113, 1018, 1005,
  1042, 1082, 1084, 1111, 1152, 1153). Poporing is NOT Poring and Green Plant is NOT White Plant:
  other species, other drops, other colours.
- **Green Plant** (8 alive, immobile, a field plant the bot does not hunt): its own class 20 IF the
  T2 pool holds >= 30 kept Green Plant labels (counted before the round is scored) and it passes
  T2 like any species. Otherwise it is NOT a class: it is left out of T2, and every frame with a
  visible Green Plant is excluded from the cache (`unchecked_species`), so it is never learned as
  background. Thin classes train and are reported apart, with no bar of their own until they reach
  50 held-out labels (orcsdun01 section 4).
- **The data:** v1's prt_fild08 sessions (v1 rules + species split, as v2orc), orcsdun01's TRAIN
  blocks (o3h + W, the v2orc-fix2-w-o3h labels), and pay_fild07's TRAIN (this rule). Evaluated per
  map, without forgetting prt_fild08 / orcsdun01 (section 8).
- **Flag for the training (not a label tier, Batt's / the parent's call):** v2orc trained with
  `hsv_s 0.7` (a saturation gain of 0.3-1.7). Elder Willow and Willow differ in saturation only
  (0.54 vs 0.30, 1b): the augmentation can turn one into the other. Proposed: `hsv_s <= 0.2` for
  this model (hsv_h 0.015 cannot cross Poring / Poporing: 72° apart). The evaluation reports the
  Elder Willow <-> Willow confusion either way.

## 8. What passes the TRAINING TIER, and what follows

- **The training tier passes** when T1 passes (5), T2 passes for every species in the tier (6, 7),
  and no C2 STOP (5). Then pay_fild07's TRAIN labels may train.
- **If it fails,** nothing of pay_fild07 trains, and the report says which condition failed and by
  how much.
- **What the parent needs before a cache** (not built here):
  - `build_frame_cache.py` reading these labels for recorder sessions on pay_fild07 (the frozen
    params, the candidate-frame rule 4f, the frame exclusions 4g), as `--fix` did for orcsdun01;
  - the classes file `classes-v2orc-payf07.json` (7);
  - the evaluation pre-registered BEFORE training (proposed: P1 per species on TEST's blind-judged
    crops, a NEW seed and two NEW labellers, recall and precision >= 0.80 for a species with >= 50
    evaluated crops; v1's gold set and held-out prt_fild08 sessions no worse than v1; orcsdun01's
    col2 per v2orc-vs-v1.md).

## 9. RESULT: 4b, the 1d measurement on FIT, attempt 1 -- STOPPED (17 walker samples < 50)

- **Run** 2026-10-24 18:32:12-18:33:22 ICT at c8812fd (`map_labels.py offset`, FIT = staged spots
  0-7 + t1b; local `/dev/shm/poring-lab-tmp/payf07/fit/offset.json`). Nothing was frozen.
- **The candidates:** staged spots 0-7: 507 frames (dropped: other spots 474, inventory 320, GM
  windows 138, map changes 86, before spot 0 13); t1b: 1,450 (our character moving 738, off the
  map 62, map changes 11, GM windows 10).
- **The samples: 17, all from t1b; the staged spots gave 0.** 4b's stop (< 50) applies.
- **The coarse curve (n = 17, median px):** 0 ms 13.6; 50 ms 9.4; **100 ms 4.5; 150 ms 4.2**;
  200 ms 10.8; every offset from 250 to 1,000 ms 13.0-18.9.
- **Why so few (a scratch diagnostic on FIT only, `payf07/scratch/diag_1d.py`):** in the staged
  FIT frames ~175 walker-instances walk at any one offset. Only 15-26 of them are isolated, clear
  of the UI and clear of every model box; 72-79 more are isolated and clear but under a model box
  (the forest). And 1d's sample must walk ONE move through the whole 1-s sweep: at 1 fps and
  5 cells/s (Elder Willow, Willow, Eggyra walk 200 ms / cell) such moves are rare. orcsdun01's
  col3 had 5 Hz frames and Orc Zombies at 400 ms / cell.

### 9a. AMENDMENT A (2026-10-24 18:35:20 ICT, from `date`; written after attempt 1's STOP and BEFORE any 1d is frozen, before T_h and before any TEST frame is read)

- **What changes (4b only):** the 1d sweep is narrowed from 0..1,000 ms to **0..500 ms** (coarse
  50 ms steps, then 10 ms within ±50 of the coarse best, clipped to 0..500). A sample must then walk
  one move through 0.5 s instead of 1 s. For the sweep, a candidate frame's character must stand
  still from t - 1.5 s (the sweep's edge + 4f's 1 s) to t.
- **What stays:** everything else in 4b (the walkers, isolation, UI / edge / model-box clearance at
  every offset, the error, the median), the stop at < 50 samples, and **the stop when the best
  coarse offset lies at the sweep's edge** (0 or 500 ms). If the true offset were >= 500 ms (the
  brief's "~0.4-0.6 s on the hunt path"), attempt 2 stops at the edge instead of freezing it.
- **Why this is not tuning to TEST:** it is a FIT-only instrument change; T1's and T2's bars and
  data are untouched. It is informed by attempt 1's FIT curve (the minimum at 100-150 ms, every
  offset >= 250 ms at >= 13 px), and by orcsdun01's 1d on the SAME RDP frame bus (warp_watch's
  frames also come from the bus: 120 ms, 260 samples).
- **If attempt 2 also stops:** nothing is frozen, T1 does not run, and the report proposes
  orcsdun01's 120 ms (the same bus) for Batt's decision.

## 10. RESULT: 4b attempt 2 (Amendment A) -- STOPPED again (47 walker samples < 50); 1d is NOT frozen and T1 does NOT run

- **Run** 2026-10-24 18:36:22-18:37:09 ICT at c6ac191 (sweep 0..500 ms; local
  `payf07/fit/offset.json`, attempt 1 kept as `offset-attempt1.json`).
- **The samples: 47** (staged spots 0-7: 6 from 512 candidate frames; t1b: 41 from 1,560). Under
  50, so Amendment A's rule holds: **nothing is frozen, T1 does not run, no TEST frame is read.**
- **The coarse curve (n = 47, median px):** 0 ms 13.6; 50 ms 9.2; **100 ms 3.2**; 150 ms 5.0;
  200 ms 10.1; 250-500 ms 15.1-17.5. The fine sweep did not run (the stop comes first). Both attempts
  put the minimum at 100-150 ms, where orcsdun01 froze 120 ms on the same RDP frame bus.

### 10a. THE PROPOSAL for the decision (the parent's / Batt's; NOT adopted here)

| option | what | for | against |
|---|---|---|---|
| **P1 (recommended)** | 1d = **120 ms**, orcsdun01's frozen value (col3, 260 samples, 2.24 px median) | the same RDP frame bus and timestamps (warp_watch and the 1-fps recorder both read the bus); both FIT attempts here put the minimum at 100-150 ms (3.2 / 5.0 px at n = 47) | a value measured on another map's frames |
| P2 | 1d measured with the 50-sample floor on a larger FIT: + s-pilot and s1 (TRAIN sessions, never TEST) | keeps 4b's measurement on this path | changes FIT after two stops; adds a third attempt |
| P3 | accept attempt 2's 47 samples and run its fine sweep | the measurement as designed, 3 samples short | lowers a pre-registered floor after the fact |

### 10b. What is done meanwhile (PROVISIONAL under P1; no TEST read, nothing frozen)

So that P1, if chosen, can proceed at once:
- T_h is measured on FIT at 120 ms (4e's method, unchanged);
- the parameters are written as `params-P1-proposed.json` with `status: PROPOSED_NOT_FROZEN`. The
  tool REFUSES T1 on them (c.f. `map_labels.py check`);
- the TRAIN sessions are labelled under them (staged spots 0-7, t1b, s-pilot, s1): the counts;
- the T2 pack is built from them (seed 21, as section 6), marked provisional in its key. It may be
  run only if the decision is P1 and T1 then runs on the frozen P1 parameters; under P2 / P3 the
  labels and the pack are rebuilt with the frozen values.
- A DIAGNOSTIC (not a measurement under the rule) for P2: 1d's sweep on staged 0-7 + t1b +
  s-pilot + s1, reported, never frozen.

### 10c. FIT finding under P1 (provisional): T_h came out 0.111, driven by ENGAGED Elder Willows

- **The provisional T_h run** (P1's 120 ms, FIT = staged spots 0-7 + t1b, 4e's method; 18:39:18-
  18:41:31 at 67f0bc6; `payf07/fit/threshold-P1.json`): **T_h = 0.111** (orcsdun01: 0.48). The
  clear kept fits: n 737, p5 0.111, p25 0.695, median 0.761.
- **The cause** (scratch diagnostics on FIT only, `payf07/scratch/diag_th.py`, `diag_engaged.py`):
  - Elder Willow's clear kept fits: staged median 0.751 (49), t1b median 0.133 (123);
  - in t1b, split by ENGAGEMENT (an `act` between the unit and our character, either way, or our
    `attack_request` on it, within [tw - 3 s, tw + 1 s]): **engaged 87, median 0.127, 80 of them
    under 0.3; not engaged 36, median 0.784.** Every engaged unit in t1b was an Elder Willow (the
    bot's Steal / fight target);
  - every other species, not engaged: median 0.73-0.91.
- So the rule, built on immune-GM data where nothing fought (orcsdun01 3g saw the same on Batt's
  demo), keeps fights' units on spurious fits barely above tau, and they drag T_h down.

### 10d. AMENDMENT B (2026-10-24 18:54:50 ICT, from `date`; written after 10c's FIT diagnostics and BEFORE any parameter is frozen, before T_h is re-measured and before any TEST frame is read)

- **New exclusion `engaged`** (handled as 2b / 2c: the label is not kept, its frame is not whole;
  counted under its own name): a monster with an `act` packet between it and our character (either
  direction) or an `attack_request` of ours targeting it, at a time within **[tw - 3 s, tw + 1 s]**
  (tw = the label's timeline time). It applies to the labels, to 4e's T_h and to C1 (where 5's
  standing rule already isolates almost every such unit).
- **Why these numbers:** 3 s back spans a fight's ongoing attack and hurt animations (attack
  delays ~1-2 s, our hits every ~0.5-0.7 s); 1 s forward covers a fight starting just after the
  frame (2b's idea, wider for a fight's approach).
- **What stays:** everything else, including Amendment A, the stops, T1's and T2's bars and data.
- The provisional P1 work of 10b is redone under B (T_h, the parameters, the TRAIN labels, the
  pack). The decision on 1d (10a) is still open: T1 does not run.

### 10e. RESULT of the provisional work (P1 + Amendment B; no TEST read, nothing frozen)

**The order of events** (2026-10-24 ICT, from `date` and the commits): pre-registered 18:25:24
(7ed0422) -> tool c8812fd 18:32:03 -> 4b attempt 1 18:32-18:33 STOP -> Amendment A 18:35:38
(f7dbd42) -> attempt 2 18:36-18:37 STOP -> 10a / 10b 18:38:53 (67f0bc6) -> the P2 diagnostic and the
first P1 T_h 18:39-18:41 -> 10c / Amendment B 18:55:06 (adda47a; code fe8047f, efa7739) -> T_h
under P1 + B 18:56-18:58 -> the proposed parameters 18:58:08 -> the TRAIN labels 18:58-19:00 -> the
T2 pack 19:01. **No TEST frame and no TEST packet has been read by any of it** (TEST = staged spots
8-11 + t2: the tools refuse them; t2's packets were never opened).

- **The P2 DIAGNOSTIC** (`offset --diagnostic` on staged spots 0-7 + t1b + s-pilot + s1; never
  frozen; `payf07/fit/offset-diag-P2.json`): **89 walker samples (35 units; Willow 22, Bigfoot 22,
  Poporing 21, Eggyra 17, Elder Willow 7), the best coarse 100 ms, the fine sweep's best 120 ms**
  (median 2.83 px, p25-p75 1.41-6.08; 130 ms ties at 2.83, the tie keeps the smaller). So P2, run
  as 4b's rule with the floor met, lands on **exactly P1's 120 ms**.
- **T_h under P1 + B** (`payf07/fit/threshold-P1.json`, sha256 `f477de49…`): **0.479** (orcsdun01:
  0.4775). The clear kept fits: n 650, p5 0.479, median 0.769. The fits of under-box labels that
  pass: n 834, median 0.676; 306 of them fall under T_h (o3h excludes them).
  - Per species, the clear kept median: Elder Willow 0.767 (85), Willow 0.750 (148), Eggyra 0.903
    (62), Bigfoot 0.754 (111), Poporing 0.734 (128), Green Plant 0.810 (116). The Green Plants
    under a model box all fit at <= 0.443 (46): o3h drops every one.
  - **Amendment B's positive case, on real data:** `engaged` excluded 404 Elder Willow, 22 Bigfoot,
    13 Eggyra and 2 Poporing fates in t1b; T_h moved from 0.111 to 0.479.
  - The reported anchors (4c): every species' clear kept median fit offset is within 1 px
    ((0..1, -1..0) px): no anchor is needed, as 1b expected.
- **The proposed parameters:** `payf07/params-P1-proposed.json` (sha256 `798508ee…`), `status:
  PROPOSED_NOT_FROZEN` (its `frozen_at` field is only the write time). `map_labels.py check`
  refuses it.

### 10f. The TRAIN labels under P1 + B (provisional): counts per species and session

Every candidate frame (1 fps). "kept" = the kept fitted labels in any candidate frame (T2's pool);
"whole" = the labels in frames labelled whole (what a cache would hold).

| species | staged spots 0-7 (kept / whole) | t1b | s-pilot | s1 | ALL kept | ALL in whole frames |
|---|---|---|---|---|---|---|
| Elder Willow 1033 | 130 / 57 | 41 / 30 | 8 / 7 | 27 / 6 | **206** | **100** |
| Willow 1010 | 88 / 64 | 185 / 137 | 41 / 27 | 289 / 222 | 603 | 450 |
| Eggyra 1116 | 99 / 54 | 85 / 52 | 49 / 38 | 280 / 182 | 513 | 326 |
| Bigfoot 1060 | 61 / 15 | 131 / 52 | 90 / 79 | 149 / 92 | 431 | 238 |
| Poporing 1031 | 58 / 52 | 184 / 129 | 0 / 0 | 29 / 12 | 271 | 193 |
| Green Plant 1080 | 116 / 0 | 0 | 0 | 0 | 116 | **0** |
| **all** | 552 / 242 | 626 / 400 | 188 / 151 | 774 / 514 | **2,140** | **1,307** |
| frames: recorded / candidates / whole | 1,538 (spots 0-7 of it) / 513 / 281 | 2,271 / 1,645 / 975 | 523 / 423 / 267 | 1,950 / 1,675 / 1,137 | | **2,660 whole** |

- **The exclusions, by reason** (labels, all four parts; recounted from the label files):
  `engaged` 1,089 (Elder Willow 1,007 of them); `occluded_model` 933 (o3h); `ambiguous_view` 173;
  `next_move` 116; `unfit` 88; `ui` 9; `crowd` 6. Frames: `warp_in_view` 3 (t1b); no other player,
  no unchecked species.
- **The candidate-frame drops:** our character moving 872 (t1b 543, s-pilot 73, s1 256); the
  staged session's other spots 474 (TEST and before spot 0: 13 more), its inventory spans 314; GM
  windows 164; map changes 113; off pay_fild07 76.
- **Green Plant:** 116 kept labels (>= 30), so it is a class and in the tier (section 7), but 0 of
  them lie in a whole frame (its neighbours under canopy are excluded), so a cache would hold no
  Green Plant box today.
- **s2 (`20261024T181454-rdp-thief-s2`, shipped 19:0x; the parent's message), labelled the same
  way at 19:05-19:06 with paced reads (3 workers):** 1,266 frames (its recorder stopped at ~21 min
  on a host IO-guard trip), 1,082 candidates, 542 whole; kept / in whole frames: Elder Willow
  34 / 16 (155 `engaged`), Willow 26 / 16, Eggyra 207 / 81, Bigfoot 38 / 12, Poporing 87 / 57,
  Green Plant 0; all 392 / 182. It is NOT in T2's pool (fixed in 3b) and joins TRAIN only by 3c,
  whose own-C1 check needs the FROZEN parameters (not run).
- 🔴 **Elder Willow, the species Batt asked about, is the THINNEST: 100 boxes in whole frames.** The
  hunting runs fight it (Steal first): 1,007 of its hunting sightings are `engaged`, the very
  situation of Batt's clip, and Amendment B removes them because their fits are spurious (10c).
  A detector trained on these labels learns Elder Willow from stills and wanderers, not from a
  fight next to our character. See 10i.

### 10g. The T2 blind pack (PROVISIONAL: built from the P1 + B labels; seed 21)

- **Where (local, client-derived, never committed):** the pack
  `/dev/shm/poring-lab-tmp/payf07/t2-seed21/pack/` (180 crops in `crops/`, 9 grids, the multi-view
  `reference.png` with 12 letters, `pack.json`, `instructions.txt`); the answer key, apart:
  `/dev/shm/poring-lab-tmp/payf07/t2-seed21-key/answer_key.json` (sha256 `3c4748bc…`).
- **The sample:** 30 per species from the T2 pool (pool sizes: Elder Willow 206, Willow 603, Eggyra
  513, Bigfoot 431, Poporing 271, Green Plant 116), section 6's seeded order. 61 of the 180 lie
  under a model box (kept by o3h). By session: staged 72, s1 48, t1b 47, s-pilot 13. No controls.
- **The reference letters** (in the key only): 12 species, the six of pay_fild07 + Poring, White
  Plant, Lunatic, Pupa, Drops, Creamy, each in its idle views side by side.
- **The labeller instructions:** `docs/planning/payf07-blind-instructions.txt`, copied verbatim as
  the pack's `instructions.txt` (sha256 `dc3ee728…19f9`, checked by the tool). Each of two NEW
  blind labeller agents gets ONLY the pack directory and this text, plus an answers path outside
  the pack; never the key directory, never this document.
- **The score:**

      python3 scripts/blind_score.py --key /dev/shm/poring-lab-tmp/payf07/t2-seed21-key/answer_key.json \
          ANSWERS_A.json ANSWERS_B.json --both-good /dev/shm/poring-lab-tmp/payf07/t2-seed21-both-good.json

  The bars (section 6): per species, >= 90 % good from EACH labeller AND the species right >= 95 %.
- **When it may be run:** only after the 1d decision is recorded and the parameters are FROZEN.
  Under P1 the frozen labels are the provisional ones exactly (the same 120 ms and T_h; only the
  parameter file's status differs), so the pack is rebuilt from the frozen labels and its key
  compared crop by crop (mob, session, frame, gid, box) before the labellers start. Under P2 the
  result is the same 120 ms (10e). Under P3 the labels and the pack are rebuilt.
- **A sanity look, by eye, at the RENDERING only** (`grid_01.png`, crops 001-020, before any
  labeller): the crops, boxes and reference draw correctly. Crop 007 (an Eggyra in s1, clear of
  the models, fit 0.152) shows grass and no monster. Nothing was changed for it: it is the blind
  round's to judge. 5 of the 180 crops have a fit under 0.3 (3 Elder Willow, 1 Bigfoot, 1 Eggyra).

### 10h. What the parent runs next (after recording the decision as Amendment C)

Under **P1** (recommended; the same as P2's outcome), from this worktree, the PYTHONPATH and venv
of the subagent brief:

    cd /dev/shm/poring-lab-tmp/payf07
    # 1. freeze: the proposal's T_h file + the decision, cited
    python $W/scripts/map_labels.py freeze --threshold fit/threshold-P1.json \
        --decision "Amendment C (<time>): 1d = 120 ms (P1)" --out params.json
    # 2. T1 on TEST (the first TEST read)
    python $W/scripts/map_labels.py check \
        /mnt/poring-lab-datasets/20261024T170356-rdp-stage-items-b:spots=8-11 \
        /mnt/poring-lab-datasets/20261024T131838-rdp-thief-t2 \
        --params params.json --workers 8 --rows t1/rows.json --out t1/check.json
    # 3. the TRAIN labels with the frozen file, then the pack (compare the key with 10g's)
    mkdir -p labels-frozen && PARAMS=params.json OUTDIR=labels-frozen scratch/run_labels.sh \
        /mnt/poring-lab-datasets/20261024T170356-rdp-stage-items-b:spots=0-7 \
        /mnt/poring-lab-datasets/20261024T123622-rdp-thief-t1b \
        /mnt/poring-lab-datasets/20261024T164555-rdp-thief-s-pilot \
        /mnt/poring-lab-datasets/20261024T173322-rdp-thief-s1
    python $W/scripts/map_labels.py pack labels-frozen/*.json --seed 21 --pack-dir t2/pack \
        --key-dir t2-key --instructions $W/docs/planning/payf07-blind-instructions.txt \
        --instructions-sha256 dc3ee728ba5637c2416fcd34775e3ed7b5bc22afeae6096bdec8eb378d1c19f9 --out t2-build.json
    # 4. each TRAIN hunting session's own C1 (3c): check --allow-fit for t1b; check s-pilot, s1

T1's numbers come from `t1/check.json`: `T1` (PASS / FAIL against <= 0.050), `c1.ratio`,
`c1.per_species`, `c2.per_species` and `c2_stop`, `per_part` (staged / t2).

### 10j. AMENDMENT C (the parent's decision, 2026-10-24 19:08:31 ICT from `date`; written BEFORE any parameter is frozen and BEFORE any TEST frame is read): **P1, 1d = 120 ms**

- **Adopted: P1.** The packet -> frame offset 1d is orcsdun01's frozen 120 ms.
- **Why:**
  - The 1-fps recorder and warp_watch read the same RDP frame bus and the same timestamps.
    orcsdun01 froze 120 ms on 260 samples (col3, 2.24 px median).
  - Both FIT attempts here put the minimum at 100-150 ms (3.2 / 5.0 px at n = 47).
  - 10e's P2 diagnostic, on TRAIN sessions only (s-pilot + s1, never TEST), found 120 ms exactly
    on 89 samples (2.83 px median).
  - P3 (lowering the 50-sample floor after the fact) is rejected.
- Nothing else changes. Amendment B (engaged), T_h measured on FIT under P1 + B (0.479), the
  split, T1's bar (C1 <= 0.050) and T2's bars stay as written.
- Next: 10h's steps 1-4, in order (freeze, then T1 on TEST, then the frozen TRAIN labels and
  the pack). The decision is reported to Batt.

- **FROZEN 2026-10-24 19:08:56 ICT** (from `date`; BEFORE the first TEST read):
  - `/dev/shm/poring-lab-tmp/payf07/params.json`, sha256
    `e93367fe7d333a4ce74289a76915d48ded8631a77a042e62f68d83dc0dc2de14`;
  - its T_h file `fit/threshold-P1.json`, sha256
    `f477de49852e656e7e8ac025af151d3fd86e5e6ed9abc4683dea4635d8138247`;
  - decision "Amendment C (2026-10-24 19:08:32, c508f3d): 1d = 120 ms (P1)".

### 10k. RESULT: T1 on TEST under Amendment C -- **PASS** (run 2026-10-24 19:09:06-19:10:33 ICT; `t1/check.json`, commit 4b8d61e, params sha256 e93367fe...)

- **C1 (the bar: bad labels / scored <= 0.050, pooled): 2 / 463 = 0.0043. PASS.** The NCC
  median is 0.731, p10 0.477.
- **C2 (median |dx|, |dy| <= 4.0 px, species with >= 20): PASS for every species scored.**

| species | C1 scored | bad | NCC median | C2 n | median abs dx / dy (px) | C2 |
|---|---|---|---|---|---|---|
| Eggyra (1116) | 313 | 2 | 0.787 | 313 | 0 / 1 | PASS |
| Willow (1010) | 52 | 0 | 0.554 | 52 | 0 / 1 | PASS |
| Bigfoot (1060) | 39 | 0 | 0.610 | 39 | 1 / 1 | PASS |
| Poporing (1031) | 34 | 0 | 0.482 | 34 | 1 / 2 | PASS |
| Elder Willow (1033) | 25 | 0 | 0.595 | 25 | 1 / 1 | PASS |
| Green Plant (1080) | 0 | -- | -- | -- | -- | not in TEST |

- **By part:**
  - staged spots 8-11: 1,538 frames, 219 candidates, 25 scored, 0 bad;
  - t2: 2,292 frames, 1,665 candidates, 438 scored, 2 bad.
- **Excluded as occluded by a model:** Eggyra 151, Poporing 29, Bigfoot 17, Willow 16, Elder
  Willow 4.
- Next: 10h step 3 (the TRAIN labels with the frozen file, then the pack, its key compared with
  10g's), then T2 by two new blind labellers.

### 10l. The T2 pack from the FROZEN labels (10h step 3; 2026-10-24 19:17 ICT)

- The TRAIN labels were rebuilt with the frozen `params.json` (19:11-19:16), then the pack
  (seed 21): `/dev/shm/poring-lab-tmp/payf07/t2/pack/`, key `t2-key/answer_key.json`, sha256
  `48818815fd4b66bb8cf61288794ca7e5f90bec28fb19714107c94e0266fafb7e`.
- **The crop-by-crop comparison with 10g's provisional key: 180 of 180 identical** (mob, session,
  frame, gid, box, NCC, under, state, spot). Only the provenance differs (params FROZEN, the
  frozen label files).
- Two NEW blind labellers (A, B) started ~19:18-19:19 ICT. Each was given ONLY the pack, its
  instructions (sha256 dc3ee728...) and an answers path outside it
  (`/dev/shm/poring-lab-tmp/payf07/t2-answers/A.json`, `B.json`). The key stays apart.

### 10m. RESULT: T2, blind round 1 (seed 21), scored 2026-10-24 19:30:15 ICT -- **FAILS on ONE species, Elder Willow**; by section 8 the TRAINING TIER FAILS and nothing of pay_fild07 trains on this round

- Labellers A and B, each alone, 180 / 180 crops answered. The answers are in
  `/dev/shm/poring-lab-tmp/payf07/t2-answers/`, the score in `t2-score.json`.
- Agreement A vs B: q1 179, q2 178, q3 178 of 180.

| species | A good / species right | B good / species right | bar: >= 90 % good EACH and species >= 95 % | verdict |
|---|---|---|---|---|
| Eggyra (1116) | 96.7 % / 96.7 % | 96.7 % / 96.7 % | | PASS |
| Willow (1010) | 100 / 100 | 100 / 100 | | PASS |
| Bigfoot (1060) | 100 / 100 | 100 / 100 | | PASS |
| Poporing (1031) | 100 / 100 | 96.7 / 100 | | PASS |
| Green Plant (1080) | 100 / 100 | 100 / 100 | (>= 30 kept labels in the pool: 116) | PASS |
| **Elder Willow (1033)** | 93.3 / **93.3** | 93.3 / **93.3** | species below 95 % | **FAIL** |

- **The Elder Willow misses:**
  - **079** (s1, fit 0.123, not under a model): both labellers saw empty grass, with an Elder Willow
    just OUTSIDE the box's corner. A: no; B: off.
  - **176** (s1, fit 0.170, not under a model): both saw the box on grass, with an EGG (Eggyra) just
    outside it. Both: off, species H.
  - **048** (s-pilot, fit 0.734, under a model, in deep shadow): A said Elder Willow, B said Willow
    by colour.
- **Eggyra's one miss:** 007 (s1, fit 0.152), empty grass for both. This is the crop 10g flagged
  by eye.
- **What the misses share:** three of the four have a fit under 0.2 and are not under a model. 10g
  had counted 5 of the 180 crops under 0.3.
- **The procedure note (labeller A):** once, while checking that the answers directory existed, it
  ran `ls` on `/dev/shm/poring-lab-tmp/payf07/`, which printed directory NAMES, including the key
  directories. It opened nothing there. Labeller B used only PACK files and also read pixel colours
  from them, which its instructions allow.
- **Next (a NEW pre-registration, not an amendment of this round):** a fit floor for labels not
  under a model, a new seed and two NEW labellers. More Elder Willow labels may come from a still
  collection (warp and watch, the immune GM).

### 10i. Estimates: the cache and the training (by analogy with v2orc)

- **v2orc's cache** (`v2orc-fix2-w-o3h-20261024`): 16,169 frames in 54 shards, 25.9 GB on the NAS
  (1.60 MB a frame, ~300 frames a shard), built in 11,274 s (0.70 s a frame).
- **Adding pay_fild07's TRAIN as labelled today** (2,660 whole frames, 1,307 monster boxes + one
  player box a frame): ~18,800 frames, **~63 shards, ~30 GB**, a build of ~3.7 h.
- **With s2-s6 joining by 3c** (s1's yield: 58 % of its frames whole, ~0.26 monster box a frame):
  ~+7,000 whole frames and ~+3,200 boxes: ~25,800 frames, **~86 shards, ~41 GB**, ~5 h to build.
- **Training** (training-cost.md: k = 0.146 s per frame per epoch, 30 epochs, the long-lived
  worker; R1-R3 and the IO guard add their stops):
  - TRAIN 10,416 (v2orc) + 2,660 = 13,076 frames: **~15.9 compute-h**; ~25 h wall at night
    availability (0.63), ~31 h around the clock (0.505);
  - with s2-s6: ~20,100 frames: ~24.4 compute-h; ~39 h / ~48 h wall.
  - v2orc's own run reached 3 epochs in 04:31-11:35 with ~1.5 h of stops and the duty cycle at its
    slow levels: a wall pace far slower than k suggests. Plan for the slower figure by day.
- **Per-species budget** (training-cost.md 2: B = 1,500 frames per species): every pay_fild07
  species is far below it in whole frames; Elder Willow worst (100 boxes), Green Plant at 0.
  **Proposal (not decided here):** an immune-Thief warp-and-watch block on pay_fild07 (the staged
  session's stills gave Elder Willow 130 kept labels in ~1/3 of their frames), dwelling at Elder
  Willow and Green Plant areas, before training; and, as a separate hypothesis, a label rule for
  ENGAGED units (drawn facing our character, in their attack / hurt actions) so the fight that
  Batt's clip shows can be labelled at all.

## 11. PRE-REGISTERED: round 2 -- the fit floor on EVERY label, a new blind round (the parent, 2026-10-24 19:40:44 ICT from `date`; written BEFORE any round-2 code, label filter or crop exists)

**Why.** Round 1 (10m) failed on Elder Willow alone: species 93.3 % < 95 %.
- Two of its three misses (079 fit 0.123, 176 fit 0.170) and Eggyra's one miss (007, 0.152) are
  labels NOT under a model whose best fit is far below the evidence threshold T_h.
- o3h applies T_h only to labels under a model box. A clear label with a weak fit is kept on the
  prediction alone: exactly the kind both labellers judged "box beside the monster" or "empty".

**The rule change ("payf07-o3h-all"), the only one:**
- the FROZEN T_h = 0.479 (`fit/threshold-P1.json`, sha256 f477de49...) applies to EVERY kept
  label, under a model or not;
- a label NOT under a model with best NCC < T_h is excluded as `weak_fit`. A frame holding one is
  not whole (3f / 4g: a frame is labelled completely or excluded);
- nothing else changes: params.json (sha256 e93367fe...), 1d = 120 ms (Amendment C), Amendment B
  (engaged), the split, T1's and T2's bars.
- **Its cost, counted BEFORE this commit** on the frozen TRAIN label files only (label fields,
  no pixel, no TEST): clear labels below 0.479:
  - Bigfoot 21 of 274;
  - Elder Willow 15 of 109;
  - Poporing 8 of 150;
  - Eggyra 8 of 232;
  - Willow 10 of 359;
  - Green Plant 0 of 116.
  - Below 0.30 the counts are 14 / 14 / 5 / 8 / 10 / 0. No Elder Willow clear label lies between
    0.20 and 0.40.

**T1 stands.** C1 / C2 judge the PREDICTION before any fit (10k: "on the payf07-o3h PREDICTION
... no fit"). The floor only removes fitted labels, so T1 is not re-run.

**T2, round 2:**
- the pool is the frozen TRAIN labels with the floor applied;
- every crop judged in round 1 (by session, frame, gid in `t2-key/answer_key.json`) is REMOVED
  from the pool, so round 2 is a fresh sample;
- seed **22**; 30 per species; the same multi-view reference rule and the same instructions
  (sha256 dc3ee728...);
- two NEW labellers (C, D), each given ONLY the pack, its instructions and an answers path outside
  it;
- the SAME bars: per species >= 90 % good from EACH labeller AND species right >= 95 %, every
  species of the tier (Green Plant by section 7).

**The training tier** is section 8's, on round 2's T2 (with T1 from 10k). If Elder Willow fails
again on SPECIES in shadow (round 1's 048), the next step is data (a still warp-and-watch
collection), not a further rule. That would be its own pre-registration.

**Not changed by a passing round:** the cache and the evaluation still need their own
pre-registration (section 8) before any GPU step.

### 11a. RESULT: round 2 (seed 22), scored 2026-10-24 19:52:28 ICT -- **T2 PASSES for every species -> the TRAINING TIER PASSES** (T1 from 10k)

- **The pack** (`t2r2/pack`, key `t2r2-key/answer_key.json`; built 19:4x from the frozen labels
  with `--min-fit 0.479 --exclude-key t2-key/answer_key.json`). The pool removals, per species:

  | species | weak_fit | judged in round 1 | pool left |
  |---|---|---|---|
  | Elder Willow | 12 | 30 | 164 |
  | Willow | 10 | 30 | 563 |
  | Eggyra | 7 | 30 | 476 |
  | Bigfoot | 20 | 30 | 381 |
  | Poporing | 8 | 30 | 233 |
  | Green Plant | 0 | 30 | 86 |

- **Labellers C and D** (new, each alone, only the pack): 180 / 180 answered each.
- **Agreement:** q1 180, q2 180, q3 180 of 180. Both good with the species right: 179.

| species | C good / species right | D good / species right | verdict |
|---|---|---|---|
| Elder Willow (1033) | 100 % / 96.7 % | 100 % / 96.7 % | PASS |
| Willow (1010) | 100 / 100 | 100 / 100 | PASS |
| Eggyra (1116) | 100 / 100 | 100 / 100 | PASS |
| Bigfoot (1060) | 100 / 100 | 100 / 100 | PASS |
| Poporing (1031) | 100 / 100 | 100 / 100 | PASS |
| Green Plant (1080) | 100 / 100 | 100 / 100 | PASS |

- **The one species miss:** an Elder Willow in deep shade (crop 127). Both labellers read it as a
  Willow by colour (C: G/R 0.69; D: R/G 1.45, the highest of their "Willow" group). It is the same
  kind of miss as round 1's 048.
- **Procedure:** both read only PACK files. C made and at once removed an empty directory outside
  the pack and wrote nothing into it. Both used read-only pixel-colour reads of PACK images (as
  allowed).
- **What the pass allows (section 8):** pay_fild07's TRAIN labels may train, under
  `payf07-o3h-all` (frozen params + the weak_fit floor).
- **Still needed BEFORE any GPU step (section 8):**
  - the cache built with this rule;
  - the classes file `classes-v2orc-payf07.json` (section 7's scheme, Batt's default unless he
    answers);
  - the evaluation pre-registered BEFORE training.
- **Known gap:** ENGAGED monsters (fighting our character) are excluded (Amendment B), and that
  is Batt's clip's situation. Labelling them is a separate hypothesis.

## 12. PROPOSED: the cache and the training run (2026-10-24 20:23 ICT from `date`; section 8's "what the parent needs before a cache"; nothing here is built or trained)

**What this section adds:** the class list (7), the cache tooling for these labels and its dry run,
3c's own-C1 checks of the hunting TRAIN sessions, the real build's command, and a training
proposal. The evaluation is pre-registered apart, BEFORE any of it runs:
`../benchmarks/payf07-eval.md` (ad5e3be, 2026-10-24 20:20:01 ICT).

### 12a. The class list: `config/detector/classes-v2orc-payf07.json` (4e6b574)

- Section 7's scheme exactly: v2orc's ids 0-14 unchanged, then Elder Willow 15 (1033), Willow 16
  (1010), Eggyra 17 (1116), Bigfoot 18 (1060), Poporing 19 (1031), Green Plant 20 (1080). sha256
  `aa78912d03315c35ecda7dbf9b2765f0f41f45d3be4ecf3ff3cc1394b8da9a80`.
- **Green Plant's condition (7) holds:** 116 kept labels in T2's pool (>= 30) and T2 passed (10m,
  11a). So it is class 20, not `unchecked_species`.
- Ids only, as `classes-v2orc.json`: the names come from a KB at build time. **The lab KB
  (`data/kb`) cannot name 1033, 1116, 1060, 1031 or 1080**, so the build reads the pay_fild07 KB
  (`/dev/shm/poring-lab-tmp/payf07/kb`, 1a). Its names for ids 0-14 equal v2orc's manifest names
  exactly (checked by `--link-cache`, 12b). Ids 15-20: `elder_wilow`, `wilow`, `eggyra`, `bigfoot`,
  `poporing`, `green_plant` (the KB's aegis names, lower case).

### 12b. The cache tooling (fcb5620, 104ef54; tests on synthetic data)

**`build_frame_cache.py --labels map`** reads `map_labels.py labels` files (one per part; the kept
FITTED boxes per candidate frame; no pixel). Per frame:
- **written only WHOLE** under `payf07-o3h-all`:
  - no excluded monster label (2b, 2c, `engaged`, o3h's `occluded_model`, `unfit`, `crowd`, `ui`);
  - no frame exclusion (4g: `warp_in_view`, `other_player`, `unchecked_species`; the label pass's
    `ui_layout_mismatch` / `no_scene`);
  - no kept label NOT under a model whose fit is below the frozen T_h 0.479 (11's `weak_fit`);
  - no species outside the class list;
  - our own character alive (labels v2's `self_dead`) and placed (`self_unknown`).
- **Its YOLO lines:** our own character as `player`, plus every kept monster box at its species' id.
  - The player box is labels v2's self box (`labels_v2.self_label`: v0's 34 x 74 at the camera
    target), the box v2 / v2orc gave their own character (the Crusader in 3f's demo), from the same
    camera as the labels' scene.
  - Checked by eye on 4 frames (s1 110 and 555, staged 78 and 601; crops in
    `/dev/shm/poring-lab-tmp/payf07-cache/selfbox/`, client-derived, listed for removal): it
    holds the red-haired Thief, whose feet reach ~4 px below the box. Under a leaf plane the box
    labels a partly covered Thief: the self box is not subject to o3h, as in v2 / v2orc.
- **The image:** the recorded PNG (one seek), decoded, re-encoded as `--image` says.
- **Fail closed, before any frame:**
  - the PARAMS file's sha256 must equal `--map-params-sha256`, and its status must be FROZEN;
  - every label file must carry the same params sha256 and the FROZEN status;
  - no part may share a frame with TEST (3b), and the staged session trains on FIT spots only;
  - **3c's join rule:** a session other than the staged one needs its own C1 = ADDED under the same
    params (`--own-c1`, `map_labels.py check` outputs). A real build refuses it otherwise; a dry
    run reports it (`join_rule_3c`, `would_refuse_3c`);
  - TRAIN only: a labelled session in `--val` / `--test` is refused.
- **`--dry-run`:** label files and packets only (no image, no directory). Per session it prints the
  frames considered and written, the exclusions by reason, the boxes per class id, and the
  estimated shards and bytes. With no fit at cache time, its counts are the build's exactly.

**`--link-cache ID`:** every session of a FINISHED cache joins the new one BY REFERENCE, in its own
split. The new manifest holds its rows with shard paths `../ID/<shard>`; nothing is copied or
re-labelled.
- **Why:**
  - v2orc's part needs no rebuild (11,274 s, 10i);
  - its orcsdun01 fit inputs (RSW / RSMs, orcsdun01-detector.md 3j) are no longer in /dev/shm;
  - 25.9 GB are not duplicated on the NAS;
  - `poring_vision.shards.load_split` reads `<cache>/<shard path>`, so the trainer reads the
    linked frames UNCHANGED (tested end to end with the vision reader).
- **Refused when:** the linked cache's class names differ from the list's for any of its ids, or a
  recorded shard's size differs on the NAS.
- **Valid here because:**
  - the list only APPENDS classes, so v2orc's YOLO ids 0-14 mean the same;
  - v2orc's v1 sessions excluded no frame for an unlisted species (`excluded_species` is empty in
    its manifest), so no pay_fild07 species hides unlabelled in a linked frame.
- **The linked cache must stay where it is** while the model is trained or evaluated.

**The guarded `cache:` step** now admits absolute paths below `/dev/shm/poring-lab-tmp/` only (the
label files, the frozen params, the KB: rule 7), never another absolute path or a `..` (104ef54).

Existing builds are unchanged: v0 / v1 / v2 / `--fix` / items; their tests stay green.
`map_labels.session_labeler` is RecSession's own label stack, moved, not changed.

### 12c. RESULT: 3c's own C1 for the hunting TRAIN sessions (the parent's 10h step 4; frozen params sha256 e93367fe...; `map_labels.py check`, the main checkout's tool at 989b11b; run 20:04:50-20:08:29, 20:17:00-20:17:58 and 20:24:53-20:26:22 ICT; one session at a time, 2 workers)

| session | frames | candidates | standing labels scored | bad | own C1 | 3c |
|---|---|---|---|---|---|---|
| t1b (`--allow-fit`: a FIT part) | 2,271 | 1,645 | 271 | 8 | 2.95 % | **ADDED** |
| s-pilot | 523 | 423 | 65 | 0 | 0.00 % | **ADDED** |
| s1 | 1,950 | 1,675 | 339 | 7 | 2.06 % | **ADDED** |
| s2 (`20261024T181454-rdp-thief-s2`) | 1,266 | 1,082 | 156 | 11 | **7.05 %** | **NOT ADDED** |
| s3 (`20261024T185649-rdp-thief-s3`) | 56 | 22 | 17 | 0 | 0.00 % | **NOT ADDED** (< 50 scored) |
| s4 (`20261024T193810-rdp-thief-s4`, shipped 20:2x; the parent's message) | 2,351 | 1,562 | 293 | 9 | 3.07 % | **ADDED** |

- **s2 does NOT join TRAIN (3c: C1 > 0.050).** Willow has 8 of its 19 scored labels bad; Bigfoot 2 of
  17; Elder Willow 1 of 10. s2's recorder stopped at ~21 min on a host IO-guard trip (10f); no cause
  of the failure is established here.
  - **It is a real negative case of the builder's gate:** a build with s2 refused with "3c's join
    rule: no own C1 ADDED for {s2: NOT_ADDED_C1}" and created nothing.
  - **For the record, s2's frozen labels:** `/dev/shm/poring-lab-tmp/payf07-cache/s2/`. Under the
    rule they would have written 539 frames: Elder Willow 16, Willow 15, Eggyra 81, Bigfoot 12,
    Poporing 55.
- **s3 is too short to measure** (17 standing labels scored < 50): not added (3c), whatever its C1.
- **s4 joins TRAIN by 3c** (Willow 9 of 111 bad; every other species 0). Its frozen labels:
  `/dev/shm/poring-lab-tmp/payf07-cache/candidates/` (s3's too).
- C2 per session is reported in the check files, and it does not gate 3c.
- **The check files:** `/dev/shm/poring-lab-tmp/payf07-cache/own-c1/<session>.json`. sha256: t1b
  `6a650302…`, s-pilot `9db5192b…`, s1 `0af8f625…`, s2 `808aa779…`, s3 `f27d02e3…`, s4
  `cbb8449b…`. The candidates' label files: s2 `49e682ad…`, s3 `2f735074…`, s4 `fb9cc322…`.

### 12d. RESULT: the dry run (fcb5620; 20:15:47-20:15:57 ICT; the four TRAIN label files of 10l, 3c's checks of 12c, `--link-cache v2orc-fix2-w-o3h-20261024`)

Boxes written per class; frames = candidates considered / frames written (whole, the floor, our
own box).

| part | frames | player 0 | Elder Willow 15 | Willow 16 | Eggyra 17 | Bigfoot 18 | Poporing 19 | Green Plant 20 | est. GB / shards |
|---|---|---|---|---|---|---|---|---|---|
| staged spots 0-7 | 513 / 281 | 281 | 57 | 64 | 54 | 15 | 52 | 0 | 0.64 / 2 |
| t1b | 1,645 / 953 | 953 | 23 | 133 | 49 | 43 | 127 | 0 | 2.13 / 4 |
| s-pilot | 423 / 261 | 261 | 6 | 27 | 38 | 74 | 0 | 0 | 0.58 / 2 |
| s1 | 1,675 / 1,131 | 1,131 | 6 | 219 | 178 | 87 | 11 | 0 | 2.56 / 5 |
| **pay_fild07 TRAIN** | **4,256 / 2,626** | **2,626** | **92** | **443** | **319** | **219** | **190** | **0** | **5.91 / 13** |

- **Frames holding each species:** Elder Willow 80, Willow 403, Eggyra 310, Bigfoot 207, Poporing
  190.
- **The exclusions** (frames; a frame counts under each reason it has): `occluded_model` 821,
  `engaged` 667 (Elder Willow in 626 of them), `ambiguous_view` 170, `next_move` 116, `unfit` 85,
  `weak_fit` 61, `ui` 9, `crowd` 5, `warp_in_view` 3. `self_dead` and `self_unknown`: 0.
- **Against 10f's provisional whole frames** (2,660):
  - the floor removes 34 frames (t1b 22, s-pilot 6, s1 6, staged 0);
  - per species: Elder Willow 100 -> 92, Willow 450 -> 443, Eggyra 326 -> 319, Bigfoot 238 -> 219,
    Poporing 193 -> 190.
- **The estimate is the recorded PNG sizes:**
  - on 3 s1 frames, the re-encoded PNG (`encode_png`, level 1) came out exactly as large as the
    recorded one (2,282,362 / 2,242,658 / 2,254,256 B);
  - read and decode took 0.06-0.15 s a frame, the encode 0.15-0.19 s.
- **The linked cache `v2orc-fix2-w-o3h-20261024`:** 16,169 frames (TRAIN 10,416, VAL 3,242, TEST
  2,511), 54 shards, 25.9 GB, manifest sha256 `11bf2814…`. Names 0-14 equal.
- **The combined TRAIN: 13,042 frames.** Boxes per class (ids):

| class | boxes | class | boxes | class | boxes |
|---|---|---|---|---|---|
| player 0 | 4,849 | Familiar 8 | 1,134 | Elder Willow 15 | 92 |
| npc 1 | 14,658 | Steel Chonchon 9 | 754 | Willow 16 | 443 |
| warp 2 | 0 | White Plant 10 | 195 | Eggyra 17 | 319 |
| Poring 3 | 20,573 | Black Mushroom 11 | 56 | Bigfoot 18 | 219 |
| Lunatic 4 | 738 | Drainliar 12 | 339 | Poporing 19 | 190 |
| Pupa 5 | 164 | Orc Skeleton 13 | 763 | Green Plant 20 | 0 |
| Drops 6 | 779 | Orc Zombie 14 | 6,145 | | |
| Creamy 7 | 0 | | | | |

- 🔴 **Elder Willow, the species Batt asked about, is the thinnest class:** 92 boxes in 80 frames,
  against training-cost.md 2's B = 1,500 frames per species.
- 🔴 **Green Plant is a class with 0 training boxes.** All 116 of its kept labels lie in frames
  that are not whole: their neighbours under the canopy are excluded (10f).
- 10i's proposals stand:
  - a still warp-and-watch collection at Elder Willow and Green Plant areas;
  - a separate label hypothesis for ENGAGED units.

### 12d-2. RESULT: the dry run of the CANDIDATES after 3c, reported apart (20:28:55-20:29:02 ICT, the same code; the parent's instruction: "include them only as candidates after 3c, apart from the four frozen TRAIN files")

| session | 3c | frames | player 0 | Elder Willow 15 | Willow 16 | Eggyra 17 | Bigfoot 18 | Poporing 19 | est. GB / shards |
|---|---|---|---|---|---|---|---|---|---|
| s2 | NOT ADDED (C1 7.05 %) | 1,082 / 539 | 539 | 16 | 15 | 81 | 12 | 55 | 1.22 / 3 |
| s3 | NOT ADDED (too few) | 22 / 9 | 9 | 0 | 8 | 0 | 0 | 0 | 0.02 / 1 |
| **s4** | **ADDED** | **1,562 / 979** | **979** | **6** | **170** | **166** | **70** | **68** | **2.19 / 5** |

- The dry run lists s2 and s3 in `would_refuse_3c`: a real build with them refuses.
- s4's exclusions (frames): `engaged` 303, `occluded_model` 223, `ambiguous_view` 68, `unfit` 39,
  `next_move` 18, `weak_fit` 15, `ui` 5. 757 of its frames were dropped as `self_moving` (4f).
- **With s4, the pay_fild07 TRAIN would be 3,605 frames** (Elder Willow 98, Willow 613, Eggyra
  485, Bigfoot 289, Poporing 258; ~8.1 GB, 18 shards), and the combined TRAIN 14,021 frames.
  - s4 adds only 6 Elder Willow boxes: the hunting runs fight it (`engaged`).
  - The time estimate of 12f grows by 7.5 % (E = 10: 5.7 compute-h; ~25 h running at v2orc's
    pace).
- s5 / s6 follow tonight (the parent): each one the same way (its own C1, frozen labels), BEFORE the
  build. A session that comes after the build waits for the next cache.

### 12e. The real build (the parent's, after this branch is merged; NOT run here)

The guarded step (ONE line in practice, wrapped here; `L=/dev/shm/poring-lab-tmp/payf07/labels-frozen`,
`C=/dev/shm/poring-lab-tmp/payf07-cache/own-c1`, both written out in full):

    python3 scripts/guarded_build.py --sustain 30 --spike 25 'cache@3600=--labels map
      --classes species --class-list config/detector/classes-v2orc-payf07.json
      --kb /dev/shm/poring-lab-tmp/payf07/kb --map-params /dev/shm/poring-lab-tmp/payf07/params.json
      --map-params-sha256 e93367fe7d333a4ce74289a76915d48ded8631a77a042e62f68d83dc0dc2de14
      --map-labels L/20261024T170356-rdp-stage-items-b-fitspots.json L/20261024T123622-rdp-thief-t1b.json
        L/20261024T164555-rdp-thief-s-pilot.json L/20261024T173322-rdp-thief-s1.json
      --own-c1 C/20261024T123622-rdp-thief-t1b.json C/20261024T164555-rdp-thief-s-pilot.json
        C/20261024T173322-rdp-thief-s1.json
      --link-cache v2orc-fix2-w-o3h-20261024 --image png --cache-id v2orc-payf07-20261024
      --train 20261024T170356-rdp-stage-items-b 20261024T123622-rdp-thief-t1b
        20261024T164555-rdp-thief-s-pilot 20261024T173322-rdp-thief-s1'

- **To include s4** (12d-2, ADDED by 3c), add
  `/dev/shm/poring-lab-tmp/payf07-cache/candidates/20261024T193810-rdp-thief-s4.json` to
  `--map-labels`, `C/20261024T193810-rdp-thief-s4.json` to `--own-c1`, and
  `20261024T193810-rdp-thief-s4` to `--train`. The eval's TRAIN definition covers it ("any later
  session that passes 3c before the build"). Then the expected counts are 12d + 12d-2's s4 row.
- **The exact line** without s4 (paths written out) is in
  `/dev/shm/poring-lab-tmp/payf07-cache/cache-step.txt`.
  `guarded_build.parse_step` accepts it (checked: 32 builder arguments). The same arguments plus
  `--dry-run` reproduced 12d byte for byte.
- **The shards go to** `/mnt/poring-lab-datasets/.framecache/v2orc-payf07-20261024/`:
  - 13 new shards, ~5.9 GB, plus `manifest.json`, `split.json` and `progress.json`;
  - v2orc's 54 shards stay in their own directory, referenced, not copied.
- **Expected time:** ~2,626 frames x ~0.3-0.4 s (a 2.25 MB NAS read, decode, encode, write, the
  read-back hash) ≈ 15-20 min. The step's timeout is 3600 s; resume with `--resume` and the same
  arguments.
- **Before it runs:**
  1. this branch is merged (the step runs the main checkout's builder);
  2. the /dev/shm inputs are in place: params.json (sha256 above), the four label files (10l), the
     three check files (12c), the pay_fild07 KB, and the GAT `/dev/shm/poring-lab-tmp/gat/data/
     pay_fild07.gat`; a host reboot wipes them (after-host-reboot);
  3. the same line with `--dry-run` matches 12d;
  4. on a weekday, it starts outside 09:30-10:15 and 14:00-14:45.
- **After it runs:** the manifest's per-session `kept` and `boxes_by_class_id` must equal 12d's.
  Then a vision-side read (the trainer's `--smoke`, or `load_split` on train) before the real run.

### 12f. PROPOSED: the training run (not run; Batt's / the parent's decision, recorded here BEFORE the launch)

| setting | proposal | why |
|---|---|---|
| start weights | **v2orc's epoch-3 `last.pt`**: `/datasets/archive/train/v2orc-20261024/weights/last.pt` in the container (val mAP50 0.805, 3n) | Its backbone, neck and box branch are already fitted to RO at imgsz 1280. Ultralytics transfers every tensor of the same shape; the class branch's last layers (15 -> 21 classes) start fresh. The alternative, COCO YOLO11n (v2orc-vs-v1.md's start), took 3 epochs to reach 0.805 on v2orc and was planned for 30 |
| data | **the 12e cache**: TRAIN 13,042 frames (v1's prt_fild08 8,193, orcsdun01 2,223, pay_fild07 2,626); VAL v1's 3,242 | all of v2orc's data is replayed, so nothing is forgotten by design (G1, G2, O1 of the evaluation) |
| epochs | **10**, `close_mosaic` 3 (v2orc's one third without mosaic) | the faster alternative: **6** epochs, `close_mosaic` 2. That is training-cost.md 1's incremental compute: 2 x the new frames x E/2 = 78,780 frame-epochs ≈ 6 epochs of 13,042 |
| `hsv_s` | **0.2** (section 7's flag) | Elder Willow and Willow differ by saturation only (0.54 vs 0.30); 0.7 can turn one into the other. hsv_h 0.015 and the rest stay ultralytics' defaults, as v2orc |
| the rest | YOLO11n, seed 20261004, imgsz 1280, batch 2, workers 1, WORKER=1, MID_CKPT=1, R1-R3, the IO guard, the 25 % VRAM cap | v2orc's |

**The launch** (443944f adds `HSV_S` / `CLOSE_MOSAIC` to train-day.sh and `--hsv-s` to train.py;
both opt-in, and unset means the defaults as before):

    WORKER=1 MID_CKPT=1 INIT_WEIGHTS=/datasets/archive/train/v2orc-20261024/weights/last.pt \
      HSV_S=0.2 CLOSE_MOSAIC=3 scripts/runbooks/train-day.sh payf07-20261024 \
      v2orc-payf07-20261024 10 /dev/shm/poring-lab-tmp/train-payf07 2 1

**The time estimate** (6,521 batches an epoch):

| | E = 10 | E = 6 |
|---|---|---|
| compute (training-cost.md's k = 0.146 s per frame-epoch: 0.53 compute-h an epoch) | 5.3 compute-h | 3.2 compute-h |
| wall at the measured night availability 0.63 / around the clock 0.505 | ~8.4 h / ~10.5 h | ~5.0 h / ~6.3 h |
| **wall at v2orc's real pace** (3 epochs of 10,416 frames in 04:31-11:35 with ~1.5 h of stops: ~0.63 s per frame-epoch running, ~2.3 h an epoch here) | **~23 h running, ~29 h with v2orc's share of stops** | **~14 h running, ~17.5 h** |

- Plan for the slower figure: v2orc's duty cycle ran at its slow levels (10i).
- Sunday has no market-open windows (train-day.sh: weekdays only).
- **Scoring:** `../benchmarks/payf07-eval.md`, once. It scores `last.pt` of the LAST COMPLETED
  epoch. A run Batt stops early is scored at the epoch it reached, and the report says so.

### 12g. Open (Batt / the parent)

1. Decide 12f (start weights, E, `hsv_s`) and record it here BEFORE the launch.
2. Build the cache (12e) and compare it with 12d.
3. Later sessions (s3: 56 frames; s4-s6) join TRAIN only by 3c: labelled with the frozen params,
   their own C1 ADDED, then a new `--labels map` cache. `--link-cache` takes one finished cache, so
   that build lists every map session again with the v2orc link.
4. Elder Willow's budget (92 boxes) and Green Plant's 0 boxes: 10i's still collection, before or
   after this run.
5. Engaged units: a separate label hypothesis (10i). The evaluation reports them as E1.

## 13. The parent's decisions before the build and the training (2026-10-24 20:45:11 ICT from `date`; BEFORE any cache shard, worker start or training)

**13a. More Elder Willow first, on the SAME recording path (no rule change).** Section 12's dry run
gives Elder Willow 92 boxes (98 with s4), and payf07-eval.md requires Elder Willow's bar to EXIST
(>= 50 evaluated crops) and to pass. So before the cache is built, after 4.04's s6, the immune Thief
runs `stage_items.py watch`:
- 30-s dwells on the seeded lattice of three-check stand cells
  (`/dev/shm/poring-lab-tmp/payf07-ww/lattice.json`: 779 cells ~11 apart + 45 in the Green Plant
  box; `npc_click_test.check_warps` PASS);
- ~40 min, beside the 1-fps recorder (PNG, the same path as the staged session);
- typed `@warp` lines only, with immunity read on a frame first and a relog after.
Its session, s5 and s6 join TRAIN only by 3c (own C1 <= 0.050 on >= 50 standing labels), labelled
with the frozen params; s2 stays out (own C1 7.05 %). The open-ground item re-staging
(`stage_items.py run --open`) is recorded too. Its monster frames join TRAIN by 3c like any later
session, and its item frames serve the item study only.

**13b. The training settings (12f), decided:**
- warm start from v2orc's epoch-3 `last.pt` (`/datasets/archive/train/v2orc-20261024/weights/last.pt`);
  the class head goes 15 -> 21;
- **E = 10, close_mosaic 3, hsv_s 0.2.** Elder Willow and Willow differ by saturation only. All
  else is v2orc's (YOLO11n, seed 20261004, imgsz 1280, batch 2, workers 1);
- `WORKER=1 MID_CKPT=1 INIT_WEIGHTS=... HSV_S=0.2 CLOSE_MOSAIC=3 scripts/runbooks/train-day.sh`
  with the cache built in 13a; R1-R3 throughout (the adaptive duty cycle; R2: Ollama's `/api/ps`
  empty at the start);
- scored only per `docs/benchmarks/payf07-eval.md` (ad5e3be): `last.pt` of the last completed
  epoch.

**13c. Launch conditions:**
- the cache's manifest per session equals its `--dry-run`;
- the guarded `worker:vision` is up;
- no market-open window (Sunday: none);
- the hunt keeps its CPU detector, and training must not slow it (the loader niced; v2orc ran the
  same way).

**13d. The cache's composition, fixed by its dry run BEFORE the build (2026-10-24 22:32:20 ICT).** Sessions
joined by 3c, each by its own C1 (bad / scored):
- s4 9 / 293 (3.07 %);
- s5 11 / 676 (1.63 %);
- s6 1 / 383 (0.26 %);
- the Elder Willow watch `20261024T214323-rdp-watch-w1` 2 / 699 (0.29 %). It ran 21:43-22:23:
  the immune Thief, 30-s dwells, 1,944 frames;
- s2 stays out (7.05 %), and s3 has too few labels.

| session | frames seen / written | EW 15 | Willow 16 | Eggyra 17 | Bigfoot 18 | Poporing 19 | Green Plant 20 | shards |
|---|---|---|---|---|---|---|---|---|
| staged spots 0-7 (FIT) | 513 / 281 | 57 | 64 | 54 | 15 | 52 | 0 | 2 |
| t1b | 1,645 / 953 | 23 | 133 | 49 | 43 | 127 | 0 | 4 |
| s-pilot | 423 / 261 | 6 | 27 | 38 | 74 | 0 | 0 | 2 |
| s1 | 1,675 / 1,131 | 6 | 219 | 178 | 87 | 11 | 0 | 5 |
| s4 | 1,562 / 979 | 6 | 170 | 166 | 70 | 68 | 0 | 5 |
| s5 | 1,752 / 881 | 36 | 151 | 388 | 264 | 76 | 0 | 4 |
| s6 | 1,523 / 839 | 2 | 54 | 330 | 105 | 86 | 0 | 4 |
| watch-w1 | 1,660 / 1,052 | **273** | 34 | 252 | 152 | 225 | **80** | 5 |
| **pay_fild07 total** | **6,377 written** | **409** | 852 | 1,455 | 810 | 645 | 80 | **31 (14.4 GB)** |

- Every written frame carries our own `player` box: 6,377.
- With v2orc linked by reference: **16,793 TRAIN frames**.
- The cache id is `v2orc-payf07-20261024`, built by the guarded `cache:` step; the full argument
  list is `/dev/shm/poring-lab-tmp/payf07-cache/cache-args-final.txt`.

**13e. The cache BUILT (guarded `cache:` step, 2026-10-24 22:32:32-23:01:30 ICT, ALL STEPS OK).**
- `/mnt/poring-lab-datasets/.framecache/v2orc-payf07-20261024`: 6,377 frames written, 31 shards.
  The manifest lists 22,546 frames with v2orc's linked.
- **Per session, the kept frames and the boxes per class EQUAL the dry run (13d), 8 of 8.**
- The IO guard's worst capture stall was 18.1 % on quant-postgres (62 s above 10 %), under the
  tolerant guard's 25 % spike: no abort.
- Next (13b / 13c): the vision worker through `quiet_start`, then `train-day.sh` with 13b's
  settings.

**13f. The training LAUNCHED (2026-10-25, times from the logs).**
- The vision worker: `quiet_start` was requested 2026-10-24 23:02:09. IO bursts kept restarting its
  10 quiet minutes (quant-postgres 28.4 %, Frigate 29.5 % at 00:14-00:15, among others), so it
  started only at 02:53:06. It was UP and idle at 02:55:10 (ALL STEPS OK; worst capture stall
  10.8 % on quant-postgres, 4 s above 10 %).
- R2: Ollama's `/api/ps` returned `{"models":[]}` just before the launch.
- `train-day.sh` with 13b's settings (the command in 12f): attempt 0 at **02:56:41**, the guarded
  `execdev:vision@43200` at 02:56:43, duty start level 4 (2,000 ms).
- `data/train/payf07-20261024/args.yaml` confirms the decided settings:
  - model = v2orc's `last.pt`, epochs 10, close_mosaic 3, hsv_s 0.2;
  - batch 2, imgsz 1280, seed 20261004.
- The cache loaded from the NAS in ~3 min; the first `weights/mid.pt` was written at 03:04.
- The duty cycle went from level 4 to level 0 (100 ms) by 03:01:09 at a fleet load of 0.7-2.1
  detections/s. The R3 paired windows began at 03:01:44.
- **The 12 h step cap:** each attempt is `execdev:vision@43200`, and section 12f puts this run at
  ~23 h running. So attempt 0 ends at ~14:57 ICT, with an exit that `train-day.sh` logs as
  `TRAIN STOPPED: not a guard trip`. That is expected, not a fault.
  - Resume in the warm worker at once (vision-long-lived.md 5c), with no quiet window:

        WORKER=1 MID_CKPT=1 RESUME=1 scripts/runbooks/train-day.sh payf07-20261024 \
          v2orc-payf07-20261024 10 /dev/shm/poring-lab-tmp/train-payf07 2 1

  - The resume carries no INIT_WEIGHTS / HSV_S / CLOSE_MOSAIC: the run keeps its checkpoint's own,
    and train-day.sh drops them with `--resume`.
  - Sunday has no market-open windows.
- The hunt stays on its CPU detector. No hunt runs while it trains: the next block waits for
  Batt's weight decision (thief-payon.md).
- ➡️ **SUPERSEDED: the run was STOPPED on 2026-10-25 at 12:40 ICT, before its 12 h cap (13g).**

**13g. The training STOPPED by the target change (Batt 2026-10-25 ~12:3x: "train on gef_fild10
instead"; [rogue-gef10.md](rogue-gef10.md) section 0). Times from train.log.**
- **Epoch 1 completed** (results.csv: 3,242 s of training; val precision 0.852, recall 0.834,
  mAP50 0.800, mAP50-95 0.568). Its `weights/last.pt` and `best.pt` were written at 05:17. The last
  mid-epoch checkpoint (epoch 2 in progress) is `weights/mid.pt`, 12:09.
- **The attempts after 13f:**

  | attempt | ran (ICT) | ended by |
  |---|---|---|
  | 0 | 02:56:41-04:05:17 | IO guard: quant-postgres 31.2 % (spike over 25 %) |
  | 1 | 04:20:20-08:19:16 | R3-HARD: cam-1-01-font-s dropping frames 31 s (skipped_fps 0.1, camera_fps 5.0; fleet 79.8 detections/s) |
  | 2 | 09:51:39-09:52:28 | IO guard: quant-postgres 11.6 % (over 10 % for 31 s) |
  | 3 | 10:07:31-10:08:43 | R3-HARD: the same camera, 32 s (fleet 88.9) |
  | 4 | 10:27:34-10:44:06 | R3-HARD: the same camera, 31 s (fleet 86.6) |
  | 5 | 11:19:01-12:12:24 | R3-HARD: the same camera, 31 s (fleet 75.1) |
  | 6 | 12:37:12-12:40:25 | SIGINT by the parent at 12:40:19 (the target change); "TRAIN STOPPED: not a guard trip" |

  - No abort ever made 3 within 2 h, so the duty cap and NOTIFY never fired.
  - The guard verified the stop: the worker "up and idle (no CUDA context), nothing of ours on the
    GPU" (12:40:25). The worker stays up for the gef_fild10 training (rogue-gef10.md 6).
- **An observation for Batt (suggestion only, nothing done):** after each R3-HARD abort,
  train-day.sh waits for 15 minutes without a camera dropping frames. Those waits took 92, 19, 35
  and 25 min. So drops kept appearing for up to ~77, 4, 20 and 10 min after our stop, while
  NOTHING of ours ran (the gate re-arms on any camera's drop; train.log names cam-1-01-font-s in
  every abort). The drops on that camera are, at least mostly, its own.
- **What is kept:** `data/train/payf07-20261024` (args.yaml, results.csv, the weights) goes to the
  NAS archive with a guarded `archive:` step. Its epoch-1 `last.pt` is a candidate init for
  gef_fild10's detector, decided in that pre-registration. payf07-eval.md is NOT scored: no run of
  this pre-registration reached its last epoch.
