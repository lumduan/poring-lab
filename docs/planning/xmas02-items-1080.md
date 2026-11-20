---
doc_type: plan
status: ACTIVE
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [xmas02-1080-detector.md, xmas02-detector.md, rogue-xmas02.md, screen-size-ab.md, fullscreen-client.md, ../../scripts/fi_labels.py, ../../scripts/fi_eval.py, ../../scripts/stage_items.py, ../../scripts/build_frame_cache.py]
next_action: "Build tools T-I1..T-I5 offline (tests first), then record the 1080 FIT session."
title: "The floor-item model at 1920x1080: a 1080 round of the item detector, the 720 round 5's recipe with only the screen changed (pre-registration)"
date: 2026-11-20
owner: Batt
---

# The floor-item model at 1080 (pre-registration, 2026-11-20)

Written before any 1080 item data exists. Nothing below is edited after its commit, except by a
labelled, clock-stamped amendment (section 11).

## 0. What Batt asked

- 2026-11-20 ~21:1x, after 8c of xmas02-1080-detector.md: the next work, in this order, "long":
  1. the item model at 1080;
  2. the cursor at 1080;
  3. the false goblin alarms.
- His observation the same evening, from the live 1080 PC: "the bot does not pick up all the
  loot" (xmas02-1080-detector.md Amendment 22).
- This plan decides the item round only. Deployment of its model is Batt's decision.

## 1. The facts this plan stands on

- **The 720 model, xmas02fi5** (xmas02-detector.md O26 / O27): PASSED every bar at 720.
  - I1h recall 76 / 81 = 0.938; natural drops 43 / 45 = 0.956 (Batt's 95 % met); precision
    0.990; I2 0.85; I3 0.48 % / 0.12 %; I4 1.0 %; I5 GPU 1.005 x, CPU 0.948 x.
  - Its recipe:
    - labels from packets (fi_labels.py, rule xmas02-fi-1; params v2 aea6f1d2...);
    - a cache of every admitted TRAIN session under one params file;
    - training from the previous round's last.pt;
    - two new blind labellers per pack;
    - fi_eval's I1-I5.
- **At 1080 it sees about a third to a half of what it sees at 720** (screen-size-ab.md):
  - s11scr r01A: 0.21 items seen a loot step at 720 against 0.05-0.11 at 1080;
  - 0.30 picked a step against 0.02.
  - 8c (2026-11-20, xmas02v1080 at 1080): loot/h 134.4 against 155.0 at 720.
  - Batt's live Run: 9 picks for 20 kills in 12.8 min.
- **The tools are 720-only today** (the parent's code read, 2026-11-20):
  - fi_labels' XMAS02_FI spec takes the 720 monster params only (d4cc0a5d; `freeze` refuses
    others), its VAL split is p31 only, and its pixel constants were fitted on 720 frames:
    anchor (-4, +2), scale 1.0, T_item 0.65, the bar box (-31, 10, 28, 18), MARGIN_PX 30, the
    floor tile colours. The studies that measured them were scratch.
  - build_frame_cache's `--labels items` refuses `--link-cache` and takes one item-params sha
    for every label file. fi_eval takes one params sha and one model.
  - `pack --round` takes 1-5; `fi_eval --strata` takes r2-r5.
  - stage_items drops through the inventory with an icon set proven at 720 only. The same drop
    failed at 1080 on 2026-11-20 ("slot 0 did not drop twice", xmas02-1080-detector.md
    Amendment 21).
- **The 1080 picture** (fullscreen-client.md, xmas02-1080-detector.md 1-4):
  - the bot works on the VIRTUAL 1280 x 720 picture: the world scaled, the panels pasted, their
    ghosts black;
  - native-size things (floor-item NAME labels, small HP bars, the cursor) are not scaled with
    the world;
  - the monster round's 1080 camera params are params-1080.json `9c73278f...` (T_h 0.504,
    offset 120 ms);
  - camera zoom must read 1.000 +- 0.01 before every recording.

## 2. The approach (the 1080 monster round's, applied to items)

1. A 1080 FIT session (natural drops, not immune), then the item constants FITTED on it and
   FROZEN, then T1.
2. 1080 TRAIN sessions (natural-drop pilots, plus stagings once the drop works at 1080), each
   admitted by G2.
3. T2: two new blind labellers on a 1080 item pack.
4. One cache: the 720 round 5's TRAIN (linked, its own params v2) plus the 1080 TRAIN (the 1080
   item params). VAL = the 1080 FIT session.
5. Training from xmas02fi5's last.pt (`331b1927...`), imgsz 1280, epochs by the r4 / r5 rule.
6. The bars (section 8), each scored once, then the play block.

## 3. The tools (offline, tests first; merged before the FIT session is recorded)

- **T-I1 fi_labels, a 1080 spec:**
  - XMAS02_FI_1080 takes params-1080.json as its monster params (`9c73278f...`);
  - its FIT / VAL session is the 1080 FIT session;
  - its held-out names (section 4) are refused by name until the freeze;
  - its constants come from the 1080 item params (T-I2), never from the 720 ones.
- **T-I2 the item constants at 1080, fitted and frozen** (committed code, not scratch):
  - the anchor (dx, dy) and the sprite scale: the median offset of the masked colour fits on the
    FIT session's clear views;
  - T_item by the 720 rule (the smallest 0.05 step whose FIT absent-control pass rate is
    <= 0.5 %);
  - the bar box and the self box, measured on the 1080 virtual frames;
  - `freeze-1080` writes `items-params-1080.json`. Its sha is recorded before any TRAIN label.
- **T-I3 build_frame_cache, `--labels items` with `--link-cache`:** the 720 round 5's item cache
  linked under its own params, the 1080 labels under theirs. Each part's params sha is checked
  against its own label files.
- **T-I4 the pack and fi_eval for round 6:** `pack --round 6` and `fi_eval --strata r6` (the 1080
  held-outs; natural and staging reported apart).
- **T-I5 the inventory drop at 1080** (gm_state.clear_loot, used by stage_items and clear-bag):
  - the cause of 2026-11-20's failure found and fixed;
  - proven at 1080 by a positive case: 6 items dropped and seen on the floor by the packets,
    twice, before any staging.
  - Until it passes, TRAIN takes natural-drop pilots only.

## 4. The data at 1080 (the lab's Rogue Thief8fce; aura off; zoom 1.000; lab fullscreen 1920 x 1080)

- **FIT / VAL: one natural-drop pilot `xmas02-ifF`**: a 25-min runner run (not immune) with the
  recorder (1 fps, png). It is never TRAIN.
- **TRAIN:**
  - natural-drop pilots `xmas02-ifT<n>` (25 min each, not immune), as the 720 fiT were;
  - stagings `xmas02-ifs<n>` (immune, `stage_items.py --views near --n 12`, cells from the
    lattice's TRAIN stands), once T-I5 passes.
  - Target: >= 8 admitted pilots and, if T-I5 passes, >= 3 stagings.
- **Held-out, recorded before the training starts and untouched until the freeze:**
  - two natural-drop pilots `xmas02-ifH1`, `xmas02-ifH2`;
  - one staging `xmas02-ifsH1` (cells shared with no other staging), if T-I5 passes.
- Each recording: the zoom check first, immunity read back as the plan says, and the
  checksums verified on the NAS before the local copy goes.

## 5. FIT, the freeze and T1

- G2 on the FIT session: the median |dx|, |dy| of its clear views' colour fits <= 3 px, on >= 30
  fits.
- The freeze writes the 1080 item params. Then T1: the FIT session's own labels at the frozen
  params pass G2.
- If T1 fails, no TRAIN label is made. The cause gets its own amendment.

## 6. T2 (the blind check of the 1080 labels)

- `fi_labels.py pack` on the 1080 TRAIN labels, the T2-items strata (N, F, M, E), seed 71.
- Two new blind labellers, AI and AJ, with the item instructions `cff8ee8b...` and only the
  paths changed.
- The bar, each labeller: good box >= 90 % on the item crops AND item-present right >= 95 % on
  all crops. A failure voids the 1080 labels.

## 7. The cache and the training

- The cache: the 720 round 5's TRAIN linked (T-I3), plus every admitted 1080 TRAIN session and
  its negatives (1 per 3 item frames, plus the session negatives as round 5).
  - VAL = the 1080 FIT session. A `--dry-run` first; the written counts must equal it.
- The training: `poring_vision.train --cache <id> --weights <xmas02fi5's last.pt>` with
  `--hsv-s 0.2 --close-mosaic 3 --scale 0.1`, imgsz 1280, seed 20261004.
  - Epochs: min(12, max(3, floor(5400 / (0.64 N + 100)))), N the TRAIN frames.
  - It runs as one guarded `execdev:vision` step, with the mid-epoch checkpoints.

## 8. The bars, each scored ONCE ("the minimum is what 720 achieved", as the 1080 monster round)

### 8a. At 1080, on the 1080 held-outs (fi_eval, strata r6)

| line | measure | 720 round 5 achieved | bar at 1080 |
|---|---|---|---|
| I1h | recall, pooled held-out, >= 40 evaluated crops | 0.938 | >= 0.90 |
| I1n | the natural drops alone (reported beside it) | 0.956 | reported; Batt's 95 % reported |
| I1p | precision | 0.990 | >= 0.95 |
| I2 | drops boxed in their first kept frame, >= 20 episodes | 0.85 | >= 0.80 |
| I3 | item-free frames with a box / inside her 5 x 5 | 0.48 % / 0.12 % | <= 0.5 % / <= 0.2 % |
| I4 | drop-less kills with a box on the death cell, >= 40 kills | 1.0 % | <= 5 % |
| I5 GPU | D1 server forward p95 (fi_gpu_latency, a guarded serve step) | 16.7 ms | <= 35 ms and <= 1.10 x xmas02fi5's |
| I5 CPU | p95, interleaved, 16 threads, nice 10 | 0.948 x | <= 1.10 x xmas02fi5's |

A count under its minimum is NO VERDICT, never a pass.

### 8b. At 720, no loss (the 720 round 5's own held-outs)

- fiH1, fiH2 and fsH1, with their archived keys and answers (labellers U, V) reused; only the
  predictions are new.
- The round 5 bars: I1h >= 0.85 on >= 40, precision >= 0.85, I3 and I4 as registered. Reported
  beside xmas02fi5's own numbers.

### 8c. In play at 1080 (the decisive bar; after 8a and 8b pass)

- `screen_ab.py` at 1080, the box naming xmas02v1080:
  - A = `--loot-items xmas02fi5`, B = `--loot-items <the new model>`;
  - 3 valid runs a side, 20 min each, stage2_ab's setup.
- Judged:
  - loot/h: mean(B) - mean(A) > +2 SE (better), as the reason for the round;
  - kills/h no worse than -2 SE;
  - deaths B <= A; errors none new.
- Reported:
  - the loot steps' share with an item seen;
  - the picks a kill;
  - the economy's z/h, each as a % of Batt's run (228.5 kills/h, 135,737 common z/h).

## 9. The order and the times (estimates)

1. T-I1 to T-I4 offline, with tests: ~3 h. T-I5 (the drop at 1080): ~1-2 h with its proof.
2. ifF recorded and shipped: ~40 min. FIT, the freeze and T1: ~1 h.
3. The TRAIN pilots: 25 min each plus the setup. Overnight from the detached chain (chain.py),
   about 8-10 in a night.
4. The held-outs: ~1.5 h. T2: ~1 h. The cache: ~30 min. The training: a few hours. 8a / 8b:
   ~2 h. 8c: ~2 h.

## 10. Not in this round

- The cursor at 1080 (next, Batt's order), with "the bot walks past monsters" (2026-11-20: of 42
  chosen boxes, 10 struck; the cursor verdict "unknown" 19).
- The false goblin alarms (after it).
- The loot step's timing (the 4CZ settle lesson: items asked about 1.96-3.10 s after the fall).

## 11. RESULTS and AMENDMENTS (clock-labelled; nothing above is edited after this commit except by a labelled amendment)
