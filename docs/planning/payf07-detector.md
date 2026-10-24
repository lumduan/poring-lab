---
doc_type: design
hypothesis: "Packet labels with the orcsdun01 o3h rule (fix 2 facing, 2b / 2c, the map's RSW models with a fit-evidence gate), re-measured on pay_fild07's own FIT data, give per-species monster boxes for pay_fild07 (Elder Willow, Willow, Eggyra, Bigfoot, Poporing, Green Plant) that pass the training tier (T1: C1 <= 5 % on the held-out TEST data; T2: every species passes a blind check), so ONE detector can be trained on v2orc's classes plus this map's species."
status: "PRE-REGISTERED 2026-10-24 18:25:24 ICT (7ed0422). 1d STOPPED twice on its 50-sample floor (17, then 47 under Amendment A): nothing frozen, T1 NOT run, no TEST read; proposal P1 (120 ms, = the P2 diagnostic). Amendment B (engaged) after a FIT finding. Provisional P1 + B: T_h 0.479, TRAIN labels 2,140 kept / 1,307 in 2,660 whole frames, the T2 pack built (seed 21, 180 crops)"
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [orcsdun01-detector.md, thief-payon.md, payf07-prep.md, labels-v2-plan.md, training-cost.md, ../benchmarks/v2orc-vs-v1.md]
next_action: "The parent / Batt: decide 1d (10a; P1 = 120 ms recommended, P2 diagnostic also 120 ms), record it as Amendment C, then 10h: freeze, T1 on TEST, the frozen TRAIN labels, the T2 pack (seed 21) and two new blind labellers. Elder Willow is thin (100 boxes in whole frames): consider a staged block first (10i)."
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
