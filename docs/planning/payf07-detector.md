---
doc_type: design
hypothesis: "Packet labels with the orcsdun01 o3h rule (fix 2 facing, 2b / 2c, the map's RSW models with a fit-evidence gate), re-measured on pay_fild07's own FIT data, give per-species monster boxes for pay_fild07 (Elder Willow, Willow, Eggyra, Bigfoot, Poporing, Green Plant) that pass the training tier (T1: C1 <= 5 % on the held-out TEST data; T2: every species passes a blind check), so ONE detector can be trained on v2orc's classes plus this map's species."
status: "PRE-REGISTERED at the commit time of this section's first commit (2026-10-24, ICT), BEFORE any label is built and before any TEST frame is read"
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [orcsdun01-detector.md, thief-payon.md, payf07-prep.md, labels-v2-plan.md, training-cost.md, ../benchmarks/v2orc-vs-v1.md]
next_action: "Build the map-parameterised label tool and its tests; measure and FREEZE 1d and the o3h threshold on FIT; run T1 on TEST; build the T2 blind pack (the parent runs the labellers)."
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
