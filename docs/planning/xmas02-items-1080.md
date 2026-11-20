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

### Amendment 1 (2026-11-20 21:38 ICT from `date`, before any 1080 item recording): recordings are banked BEFORE the tools merge

- **Section 3 said** "merged before the FIT session is recorded". A recording is raw (frames and
  packets); the labels and the fit are made from it later by the tools. Capture-first: the FIT
  session and the TRAIN / held-out pilots are recorded while the tools are built.
  - No label, fit or freeze is made before the tools merge.
- **The pilot protocol** (`/dev/shm/poring-lab-tmp/i1080/pilot_rec.sh LABEL MINUTES`, archived
  with the round):
  1. the zoom check (1.000 +- 0.01, the 1080 monster round's `zoom_check.py` and its reference
     frame);
  2. the chat-window standard;
  3. the recorder (`record_session.py --backend rdp --fps 1 --format png`, MINUTES + 4 min);
  4. ONE play run beside it: `screen_ab.py run --label <L>-play --screen 1080 --runs 1 --minutes
     MINUTES --model xmas02v1080` (stage2_ab's setup, not immune, its own detect server);
  5. the recorder stopped by its own PID, then `dataset_ship.py ship` (its checksums).
- **The first:** ifF (FIT / VAL), 25 min, started at about 21:38.

### Amendment 2 (2026-11-20 22:21 ICT from `date`): ifF banked; T-I3 merged; T-I5 PASSES (the bag empties at 1080)

- **ifF** (`20261120T214247-rdp-xmas02-ifF`): the zoom check 1.000 (err 10.5), the chat window
  standard, then the play run: 23.9 min, rc 0, 43 kills, 53 loot steps, 9 pickups.
  - 3,189,115,531 bytes in 13 files shipped to the NAS and checked; the local copy deleted.
  - Two first tries stopped at their own checks, before any recording:
    - the zoom check's warp did not land with the chat input open: it read "1.29", a non-match;
    - its warp line was refused as the third identical line in a row.
  - pilot_rec.sh now closes the chat and types `@heal` first.
- **T-I3** merged (7e0c12f9): `--labels items --link-cache` (the sub-agent's 9d48b90f, 11 tests).
- **T-I5, the cause of the 1080 drop failure, found and fixed:**
  - At 1080 the open inventory and the drop's quantity prompt were drawn shrunk inside the
    scaled world of the bot's picture. So the slot reads looked at the wrong pixels, a drag
    started off the slot, and the prompt's OK button was never seen.
  - The fixes: both are panels while found (8b613fa4 the inventory at its home (0, 120); and the
    prompt's OK button at the 720 box + (320, 150), searched +-40 px).
  - **The proof, twice** (at prt_fild08 268 107, the series' clear stand):
    - run 1: the loot after ifF, 12 stacks dropped;
    - run 2: 6 GM items plus the restock, 8 stacks dropped.
    - The packets show 13, then 8 floor_item_appear at her feet. The bag census read Etc empty
      after each.
  - Each clear-bag still ended rc 1: its own read of the restock came before the client had
    updated (F8 read 0, then 10). The series' setup judges by its own read after it (weight
    0.24, F8 10), so a chain goes on.
- So stagings may join TRAIN (section 3, T-I5). The overnight chain records natural-drop pilots
  first.

### Amendment 3 (2026-11-20 22:39 ICT from `date`, BEFORE any fit, label or freeze of 1080 item data): T-I1, T-I2, T-I4 merged; the decisions inside them

- **Merged** (6db430a4; the sub-agent's 3e771391, b0f762fe, 9e12d221, plus the parent's 4d315f35).
  Tests: test_fi_labels_1080.py (26), test_fi_eval.py (+4); the 720 tests unchanged and green.
  The play does not import these tools, so the merge did not touch the running pilot chain's
  code.
- **The 1080 rule has its own name, `xmas02-fi-1-1080`** (`FI_MAPS["xmas_dun02@1080"]`), so
  the cache tool tells the two rules apart. Each params file records its monster sha (720
  d4cc0a5d, 1080 9c73278f).
- **The bar box at 1080 is the 720 bar's size / 1.5 about its OWN centre (`BAR_ABOUT_1080 =
  "centre"`), not about her feet** (the brief's first guess):
  - measured on 60 frames of the 1080 MONSTER FIT v1f (not item data; a smoke of the tool):
    98.6 % of the bar's pixels inside the centre box, 15.2 % inside the feet box;
  - the reader on 720 fiT19 found the measured 720 bar (83.4 % inside);
  - **freeze-1080 refuses unless >= 95 % of the bar is inside it on ifF too.**
- **T_item** (section 3's 720 rule): the smallest 0.05 step whose absent pass rate is <= 0.5 %.
  - The rate is VIEW-WEIGHTED: each sprite's rate weighted by its share of the FIT session's
    clear item views, which is the 720 study's control.
  - The rate pooled over every sprite is reported, not used.
  - Then O3's absent rule: an id passing at T_item on > 1 % of the points is excluded.
- **Absent points: 400** (READY needs >= 200: a 0.5 % rate cannot be told with fewer). The 720
  freeze-v2 used 60.
- **The anchor and the scale** (fit_constants):
  - scales 0.85-1.15 compared on the views clear at every scale; the highest median NCC wins;
  - the anchor is the median (dx, dy) of the best scale's clear fits, the search edge left out;
  - READY needs >= 30 common views and >= 30 anchor fits.
- r_label 10, the margin 30, the self box and the unit box are world-size, so their 720 values
  carry over.
- fi_eval r6:
  - I1h >= 0.90, precision >= 0.95; every other bar as section 8a;
  - `--comparator xmas02fi5` is required (I5);
  - r6 reads 1080 label files, params and a round-6 key only.
- **Next:** fit-1080 on ifF, freeze-1080 (its sha recorded), then T1 (ifF's own labels pass G2),
  before any TRAIN label.

### Amendment 4 (2026-11-20 22:45 ICT from `date`, BEFORE any TRAIN label): FIT and THE FREEZE

- **fit-1080 on ifF** (22:2x-22:41, nice 19, 2 workers, a 4 GB cap; the report
  `b7abfe57...`): **READY**.
  - 913 candidate frames; 65 item views of which 44 were clear at every scale, on 5 floor items.
  - The scales' median NCC: 0.85 0.658, 0.90 0.730, **0.95 0.745**, 1.00 0.743, 1.05 0.601,
    1.10 0.408, 1.15 0.385. Best: 0.95.
  - Anchor (dx, dy) = (-3.0, 0.0), from 44 fits, none at the search edge. NCC median 0.745,
    p5 0.412. (720: (-4, +2), scale 1.0.)
  - The absent controls (400 points, view-weighted):
    - the rate at T 0.55 is 0.598 % (over 0.5 %), at **T 0.60 it is 0.209 %, so T_item = 0.60**
      (720: 0.65);
    - excluded (passing on > 1 % at 0.60): 529, 722, 911, 996, 2251, 7269. At 720 the list was
      7269, 996, 2251.
  - The bar check, on the FIT session's item-free frames: 96.4 % inside the centre box (>= 95 %:
    accepted), 14.0 % inside the feet box.
- **FROZEN: `/dev/shm/poring-lab-tmp/i1080/items-params-1080.json`, sha256
  `ad268afd7620fed45297ad5cf8776cddf5d0ac536a213462f270c5b344601233`** (22:45:10). Copied to
  the NAS with the round's scratch.
- Disclosed:
  - the fit stands on few distinct floor items (5): she picks most loot up within seconds, so
    still frames show few lying items;
  - the 30-fit minimum is met (44);
  - the TRAIN pilots add many more items, but they are labelled under THIS freeze.
- Next: T1 (ifF's own VAL labels at the frozen params pass G2).

### Amendment 5 (2026-11-20 22:46 ICT from `date`): T1 PASSES

- ifF labelled at the frozen params (`--spec 1080 --split val`, 22:46):
  - 1,539 frames recorded; 913 candidate frames, 848 kept; 30 item labels; 10 floor items in the
    packets.
- **G2: median |dx| 0.5, |dy| 1.0 px on 44 fits (4 floor items), 95.5 % within 3 px: PASS.**
- Disclosed: ifF's VAL is thin, 30 labels (720's p31 had 233). VAL only monitors the training;
  the bars are the held-outs'.
- (`fi_labels.py g2` takes no `--spec`: the label file carries its rule.)
- TRAIN labels start with the chain's pilots, each admitted by its own G2.

### Amendment 6 (2026-11-20 22:57 ICT from `date`): the overnight chain; natural pilots are thin in items; stagings follow it

- **The chain** (`/dev/shm/poring-lab-tmp/i1080/chain.sh`, from 22:23):
  - order: ifT1, ifT2, ifH1, ifT3, ifT4, ifT5, ifH2, ifT6, ifT7, ifT8, ifT9, ifT10, 25 min each;
  - stop rule: it stops at the first pilot that does not finish and ship (a person first);
  - a labeller (`label_loop.sh`) labels each TRAIN pilot at the freeze once it ships, then
    runs G2. Held-outs are never passed to it (the spec refuses them by name).
  - pilot_rec.sh now warps onto xmas_dun02 (114 23) and waits 8 s before the zoom check: from
    another map the loading screen outlasted the check's 2.5 s wait and it read "1.29".
- **ifT1:** 25.4 min, rc 0, shipped.
  - 938 of 1,097 candidate frames kept, **28 item labels** (16 floor items in the packets).
  - G2: n 64, median |dx| 2.0, |dy| 3.0 px, 90.6 % within 3: **PASS** (dy at its limit).
- **Natural pilots carry few item labels** (ifF 30, ifT1 28): she picks loot up within seconds.
  - Ten pilots give ~300. The 720 round 5 trained on 3,913 labels, most of them from stagings
    (fs1 alone: 701).
  - So **stagings at 1080 (ifs1..ifs3, held-out ifsH1) follow the chain.** T-I5 passed; immunity
    is toggled and JUDGED on a frame before each one, and off again after it.
  - Unattended stagings cannot judge immunity, so they wait for the morning.

### Amendment 7 (2026-11-21 00:28 ICT from `date`): thin TRAIN pilots are judged together

- **ifT2** (24.2 min, shipped): G2 **NOT_ENOUGH**, 15 clear fits (3 floor items; median |dx|
  1.0, |dy| 1.0 px). **ifT3** (25.3 min, shipped): G2 **NOT_ENOUGH**, 8 fits (2 floor items;
  2.0, 3.0 px). Neither is admitted by the plan's rule ("each admitted by its own G2").
  - ifH1 (held-out) played 18.8 min, rc 0, shipped; it is never labelled before T-eval.
- **The rule from now on**, written before any pooled number is computed (the two per-pilot
  medians above were seen):
  - after the chain, the TRAIN label files whose OWN G2 is NOT_ENOUGH are judged TOGETHER:
    their clear fits pooled, the same bar (median |dx|, |dy| <= 3 px on >= 30 fits);
  - PASS admits every one of them; FAIL or NOT_ENOUGH admits none;
  - a file whose own G2 PASSes is admitted alone (ifT1); one whose own G2 FAILs is never pooled;
  - the pool is one frozen params sha (ad268afd...) and TRAIN only, else it is refused.
  - Why: the 30-fit minimum is for a stable median; natural pilots pick their loot up in seconds
    and give 8-15 clear fits each, so no single one can reach it.
- Built: `fi_labels.py g2 --pool` (`pooled_g2`, its test), on branch cursor-p1; it merges after
  the chain with the cursor fix (no code change on main while the chain runs).
