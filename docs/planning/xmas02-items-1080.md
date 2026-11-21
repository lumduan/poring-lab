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

### Amendment 7a (2026-11-21 00:31 ICT from `date`): Amendment 7 departs from the 720 round 5 (disclosed)

- The 720 round 5 did NOT admit its thin pilots: fiT14, fiT16, fiT18, fiT19 and fiT22 had fewer
  than 30 verified fits and stayed out (xmas02-detector.md, the round-5 amendment adding fsTa5).
- Amendment 7 pools such pilots at 1080 instead. The bar per fit is unchanged; only the count is
  reached together. Found after Amendment 7's commit (b3f23772), still before any pooled number.
- The pooled pilots are reported apart in the round's results (their labels and the pooled G2),
  so the round can be read with them and without them.

### Amendment 8 (2026-11-21 03:42 ICT from `date`, BEFORE any staging of this round): the chain's end; the pooled G2 PASSES; the stagings' seeds

- **The chain** (22:23-03:23): all 12 pilots played (rc 0) and shipped; 0 deaths.
  - 8 of 12 ended on stock_keep (the last Fly Wing kept): ifT2, ifH1, ifT4, ifT5, ifH2, ifT6,
    ifT7, ifT9. 4 ran out their 25-min box: ifT1, ifT3, ifT8, ifT10. The setup restocks 10 Fly
    Wings; at 1080 most of them go on false goblin alarms (goblin-alarm-1080.md).
  - Minutes: ifT1 25.4, ifT2 24.2, ifH1 18.8, ifT3 25.3, ifT4 10.6, ifT5 18.9, ifH2 18.5,
    ifT6 13.1, ifT7 20.2, ifT8 25.4, ifT9 20.8, ifT10 25.3.
- **The TRAIN labels** (the labeller loop, frozen params ad268afd..., each file's own G2):

  | pilot | item labels | negatives | own G2 fits | own G2 |
  |---|---|---|---|---|
  | ifT1 | 28 | 910 | 64 | PASS |
  | ifT2 | 8 | 896 | 15 | NOT_ENOUGH |
  | ifT3 | 21 | 1019 | 8 | NOT_ENOUGH |
  | ifT4 | 0 | 308 | 2 | NOT_ENOUGH |
  | ifT5 | 8 | 655 | 8 | NOT_ENOUGH |
  | ifT6 | 0 | 497 | 0 | NOT_ENOUGH |
  | ifT7 | 5 | 658 | 5 | NOT_ENOUGH |
  | ifT8 | 7 | 874 | 8 | NOT_ENOUGH |
  | ifT9 | 12 | 766 | 33 | PASS |
  | ifT10 | 68 | 807 | 97 | PASS |

  - **The pooled G2 (Amendment 7), 03:27:44 at d8327115** (`fi_labels.py g2 --pool --out
    g2-pool.json` over the ten files; sha256 `2617d7b7f18edd51...`): admitted alone ifT1, ifT9,
    ifT10; pooled ifT2-ifT8: **n 46, median |dx| 2.0, |dy| 2.0 px, 76.1 % within 3 px, on 12
    floor items: PASS**. All seven are admitted.
  - So all ten TRAIN pilots are admitted: **157 item labels** (108 from the three passing alone,
    49 from the pool). Reported apart as Amendment 7a says.
  - ifH1 / ifH2 (held-out) are not labelled before the freeze for T-eval.
- **The stagings** (section 4; T-I5 passed). The cells are the tool's own plan (`stage_items.py
  spots --plan`): each spot's 3 x 3 pile plus every near stand (offsets (0,0), (2,0), (-2,0),
  (0,2)).
  - The method's check: it reproduces O24's record exactly (the 13 earlier stagings on this map:
    1,584 distinct cells; fsH1: 0 shared). Scratch `cells.py` (sha256 `ec3821fce4be963d...`),
    `earlier.json` (`64454e3031fdb584...`).
  - **ifsH1, the held-out: `--views near --n 6 --seed 2612229`**, spots (214,225), (27,203),
    (115,82), (115,214), (93,25), (138,179). Its 72 cells share NONE with the 14 earlier
    stagings (O24's 13 and fsH1) nor with ifs1-ifs3.
    - 12 spots are not possible: no 12-spot near plan in the seeds searched shares no cell
      (as O17's 400-seed search found). n 6 is fsH1's size. Seeds 2612100-2612228 each shared a
      cell; 2612229 is the first that does not.
  - **ifs1, ifs2, ifs3 (TRAIN): `--views near --n 12`, seeds 2612702, 2612705, 2612707**: the
    first three seeds from 2612701 whose 144 cells share none with fsH1 (the 720 held-out of 8b),
    with ifsH1 or with each other. They share 78 / 72 / 78 cells with the 720 TRAIN stagings
    (TRAIN with TRAIN: allowed).
  - Each staging: the bag cleared and the DB's save holding none of the set (`held` rc 0);
    immunity ON, judged on a frame; the zoom and chat checks; the 1 fps recorder; the staging; the
    ship (`stage_rec.sh`). Immunity OFF and read back after the last one.
  - The order: ifs1, ifs2, ifs3, then ifsH1, all before the training starts.

### Amendment 9 (2026-11-21 03:57 ICT from `date`): ifs1 stopped at its first spot; the cause (a tab click before any look, at 1080) fixed and proven; ifs1b re-stages it

- **ifs1** (seed 2612702, 03:45-03:48): immunity ON judged on a frame at 03:45 (the Chat tab's
  last line "You are now immune to attacks."; the chat's Battle Log tab had been in front, so the
  Chat tab was shown by the client's own tab control first). The zoom 1.000, the chat standard,
  the recorder. **Spot 0 stopped (rc 1): "dropped [candy, holy_scroll, red_herb,
  well_baked_cookie], not [... manacles ..., zargon]"**: Zargon and Manacles stayed in the bag.
  - Its 1-min recording is shipped (`20261121T034619-rdp-xmas02-ifs1`) and labelled: 4 floor
    items in the packets, 0 clear fits, own G2 NOT_ENOUGH: **not admitted** (it is a staging; the
    pooling of Amendment 7 is for the pilots).
- **The cause:** in the virtual 1080 client the open bag is a 1:1 panel only once a grab has seen
  it (`ro_agent.inventory_tick`, inside the grab path). `gm_state.clear_loot` (the staging's
  drop) clicked its first tab right after the inventory chord, before any grab, so that click
  was mapped as a WORLD click (x1.5 about the centre) and missed. The tab shown stayed the last
  one used (Use): its four stacks were dropped as if they were the Etc tab's, and the Etc tab
  (Zargon, Manacles) never showed.
  - Seen on a diagnostic frame (the same open-then-click order, nothing dropped): the bag showed
    its Eqp tab (the last one the staging had visited) after the Etc tab's click.
  - T-I5's proof did not catch it: clear-bag, bag_count and the staging's give frames each read
    the bag open BEFORE their first click; only clear_loot (and gm_state's storage step) did not.
- **The fix (9396e931, main):** `gm_state._tab` looks at the bag first in the virtual client
  (`inventory_tick(force=True)`); a bag that does not read open is never clicked (Stop). At
  1280x720 nothing changes. Tests: test_gm_state, test_ro_agent_panels; the staging, clear-bag,
  bag_count and click-census suites pass.
- **The proof on the lab (03:55):** `clear_loot` with the staged set's icons on the bag holding
  the two left items: **dropped zargon (etc slot 0) and manacles (etc slot 0)**, nothing else.
- **ifs1b re-stages ifs1's plan:** the same seed 2612702 and cells (TRAIN; Amendment 8's checks
  hold), a new label so the two recordings stay apart. Then ifs2, ifs3, ifsH1 as Amendment 8.
- Recorded for the cell search (Amendment 8, made exact): from seed 2612100, 200 twelve-spot near
  plans (2612100-2612299) each shared a cell with the 14 earlier stagings; 129 six-spot plans
  (2612100-2612228) each shared one, and 2612229 is the first that does not.

### Amendment 10 (2026-11-21 04:41 ICT from `date`; first committed as "04:43", a typed time, corrected): a slip -- the chat's Chat tab left in front; ifs1b and ifs2 give no labels; re-staged as ifs1c, ifs2b

- **The slip (mine):** at 03:45, to read the immunity reply, the chat window's Chat tab was
  brought to the front (the client's own tab control) and NOT switched back to Battle Log.
  The labeller keeps only frames in the HUNTING layout (1 row, the panel collapsed, the Battle
  Log tab: map_labels.layout_matches / client_layout TARGET["hunt"]). So every frame recorded
  after 03:45 failed that gate.
  - **ifs1b** (04:00-04:26, 12/12 spots, rc 0, shipped `20261121T040020-rdp-xmas02-ifs1b`): 1,080
    candidate frames, all `ui_layout_mismatch`; 0 labels (256 floor items in the packets). Not
    admitted. (ifs1's 0 fits, Amendment 9, had the same cause besides its stop.)
  - **ifs2** (seed 2612705, from 04:28): stopped on purpose at 04:37:42 (SIGTERM inside a still
    view at spot 3: the bag empty, no line being typed; the SIGINT at 04:31 was ignored, as a
    background job's is). Its 8-min recording is shipped (`20261121T042949-rdp-xmas02-ifs2`) and
    gives no labels for the same reason. Not admitted.
  - The cells are unaffected (the frames are simply not used); no held-out was touched.
- **Fixed:** the hunting layout restored by `client_layout.py ensure hunt` (step tab:battle,
  read back: 1 row, collapsed, battle). stage_rec.sh now also STOPS before its recorder unless
  `client_layout.py read` says the hunting layout.
- **Re-staged** (the same seeds and cells, new labels so the recordings stay apart), from 04:39:
  **ifs1c** (2612702), then ifs2b (2612705), ifs3 (2612707), ifsH1 (2612229, n 6), each
  starting only after the previous one ends with stage rc 0 in the same game session.
  - Immunity: ON, judged on the 03:45 frame; no login or recover since (ifs2's stop ended only
    the staging process).
  - ifs1c's checks at 04:40: the zoom 1.000, the chat standard, the layout "1 collapsed battle".

### Amendment 11 (2026-11-21 06:07 ICT from `date`, BEFORE any T2 answer): the TRAIN stagings; the T2 pack

- **The TRAIN stagings, labelled at the freeze, each admitted by its OWN G2:**

  | staging | seed | spots | rc | item labels | negatives | own G2 fits | own G2 |
  |---|---|---|---|---|---|---|---|
  | ifs1c | 2612702 | 12 / 12 | 0 | 118 | 244 | 1,283 (48 floor items; 1.0 / 2.0 px, 85.3 %) | PASS |
  | ifs2b | 2612705 | 12 / 12 | 0 | 82 | 205 | 1,014 (41; 1.0 / 2.0, 88.7 %) | PASS |
  | ifs3 | 2612707 | 6 / 12 | 1 | 37 | 135 | 401 (20; 1.0 / 2.0, 86.8 %) | PASS |

  - **ifs3 stopped at 05:52:39 after spot 5's views, before a typed line:** the chat window's
    padlock read neither open nor locked over that cell's pale floor (locked distance 3.5, its
    shape 0.209; the frame `chat-window/20261121-055237-unreadable.png` shows the standard
    window). It stopped as built. Its 6 spots are admitted by its own G2. The 6 left were not
    re-staged (the same cell would stop the same way); the reader is not changed in this round.
  - Few labels per staging at 1080 (720's fs1: 701): the items are drawn smaller in the bot's
    1280 x 720 picture, so more fail the fit (ifs1c: item_unfit 398, item_unsprited 369 of 1,109
    candidates); the open bag during each drop covers the panel's arrow (ui_layout_mismatch 373).
- **ifsH1 (the held-out staging, seed 2612229, n 6):** its first start (05:56) stopped at its own
  checks before recording (the same unreadable padlock refused the heal and warp lines where
  ifs3 stood). One walk click (cursor_probe_1080.walk_click: a point that read the WALK arrow,
  away from the 2 boxes) moved her; the padlock then read locked. The second start passed every
  check (zoom 1.000, chat standard, layout "1 collapsed battle") and records from 05:58:42. It is
  never labelled before the freeze.
- **The 1080 TRAIN, admitted:** ifT1-ifT10 (157 labels; Amendment 8) + ifs1c, ifs2b, ifs3 (237
  labels): **394 item labels**. Not admitted: ifs1, ifs1b, ifs2 (Amendments 9-10).
- **The T2 pack** (section 6; `fi_labels.py pack <the 13 admitted files> --spec 1080 --params
  <the freeze> --seed 71`, built 06:06:51 from 31a6d394):
  - 60 crops: N 15 / F 15 / M 10 / E 20 (10 plain, 10 hard; hard NCC 0.473-0.616), 40 floor items;
  - instructions cff8ee8b... (pinned), reference.png 6a665d79... (28 sprites);
  - the answer key sha256 `240bf444f219691a237458ab...` (never shown to a labeller);
  - the labellers: AI (started 06:06) and AJ, new blind subagents that see only the pack; scored
    once by `fi_blind_score.py` when both have answered, with section 6's bars.

### Amendment 12 (2026-11-21 06:14 ICT from `date`): T2 PASSES (scored once, 06:14)

- The blind labellers AI and AJ (new subagents that saw only the pack) answered all 60 crops
  (answers sha256 `b4ff62c8f2db3166...`, `db052a5bdb1c988b...`). `fi_blind_score.py --key
  <key-t2-seed71> AI AJ` (score sha256 recorded with the scratch):

  | labeller | good box, 40 item crops | item-present right, 60 | N | F | M | E right |
  |---|---|---|---|---|---|---|
  | AI | **0.925** (37) | **0.950** (57) | 0.80 (12/15) | 1.00 | 1.00 | 19/20 (1 unsure) |
  | AJ | **0.925** (37) | **0.967** (58) | 0.80 (12/15) | 1.00 | 1.00 | 20/20 |

  - Bars (section 6): good >= 0.90 and present right >= 0.95, each labeller: **PASS, PASS ->
    T2 PASS.** No fallback (the pooled bars hold).
  - Agreement: q1 59 / 60, q2 60 / 60. Both answered "unsure" on the same two near crops (a
    small object at a fading monster's arm) and "off" on the same near crop (a candy cane's
    tail out of the box). Near-her (N) is the weak stratum at 1080 (0.80 for both): reported.
- Next (section 7): the cache (the 720 round 5 linked, --pooled-g2 for the seven pooled pilots),
  then the training from xmas02fi5's last.pt.

### Amendment 13 (2026-11-21 06:23 ICT from `date`, BEFORE the cache is written): the cache and the training, fixed

- `build_frame_cache.py --pooled-g2` merged (c3063039; Amendment 7's pool recomputed from the
  label files, join `G2_POOLED`; a test). The dry run from main (sha256 `4ee64c4efbda90a2...`):
  - TRAIN, the 1080 part (13 sessions, none refused): ifT1 / ifT9 / ifT10 G2_PASS; ifT2-ifT8
    G2_POOLED (the pool n 46, 2.0 / 2.0 px, PASS); ifs1c / ifs2b / ifs3 G2_PASS;
  - its counts: 1,793 frames = 260 item frames (394 boxes) + 1,533 negatives (150 each from the
    ten pilots' own play frames, as round 5's session negatives; 1 per 3 item frames from the
    stagings), ~3.7 GB in 13 shards;
  - VAL = ifF (VAL_MONITOR, 30 item frames, 10 negatives); the linked round 5's TRAIN by reference;
  - **combined TRAIN: 49 sessions, 5,457 frames, 1,841 item frames, 4,307 labels, 3,616
    negatives.**
- **The cache step** (the dry run's command without --dry-run; the written counts must equal
  these, else no GPU step):

      python3 scripts/guarded_build.py --threshold 30 --sustain 30 "cache@7200=--labels items \
        --item-params <the freeze> --item-params-sha256 ad268afd... --fi-labels <ifF + the 13> \
        --class-list config/detector/classes-xmas02-fi.json --train <the 13> --val <ifF> \
        --session-negs <the 10 pilots> --link-cache xmas02-fi-r5-20261112 --pooled-g2 \
        --cache-id xmas02-fi-r6-1080-20261121 --image png"

- **The training** (section 7): epochs = min(12, max(3, floor(5400 / (0.64 x 5,457 + 100)))) =
  **3**; from xmas02fi5's `last.pt` (round 5, 331b1927...); one guarded step in the worker:

      python3 scripts/guarded_build.py --threshold 30 --sustain 30 "execdev:vision@43200=python -m \
        poring_vision.train --cache /datasets/.framecache/xmas02-fi-r6-1080-20261121 --epochs 3 \
        --batch 2 --workers 2 --name xmas02-fi-r6-1080-20261121 --mid-ckpt \
        --weights /datasets/archive/train/xmas02-fi-r5-20261112/weights/last.pt \
        --hsv-s 0.2 --close-mosaic 3 --scale 0.1"

  (imgsz 1280 and seed 20261004 are the trainer's defaults). Estimate: round 5's rate (0.52 s a
  frame-epoch) x 5,457 x 3 = ~2.4 h.
- After it: the freeze, the ONNX, then 8a / 8b once (sections 8a, 8b), then 8c in play.

### Amendment 14 (2026-11-21 07:31 ICT from `date`): the training YIELDS the GPU to Batt's live Run; a false freeze, stopped and cleaned

- **Batt's live Run** (`flowplay-poring-lab-live-11210548`, his PC, started 05:48) shares the Arc
  with the dev worker. Its own detection records (detections.jsonl, the live detect server):

  | window | calls | GPU path | median | p95 |
  |---|---|---|---|---|
  | live alone (before 06:13) | 1,589 | 100 % | 23.0 ms | 35.9 ms |
  | beside the dev probes' serve step (06:14-06:43) | 1,910 | 100 % | 22.9 ms | 36.2 ms |
  | **beside this round's training (06:44-07:28)** | 2,799 | 100 % | **35.3 ms** | **166.2 ms** |
  | after the training stopped (07:29-07:31) | 164 | 100 % | 22.4 ms | 32.4 ms |

  So the training slowed his bot's box reads (no CPU fallback, but 4.6 x at p95). His live tests
  come first: **the training was stopped at 07:28:51** (SIGINT to the trainer by its host pid, the
  guard's own first stop step; the guard: `FAILED rc=130`, the worker idle, nothing of ours on the
  GPU). Epoch 1 had ended (VAL, monitor only: P 0.931, R 0.899, mAP50 0.914); the mid-epoch
  checkpoint of 07:26 holds the rest (`--resume` continues at that batch).
- **A slip (mine), caught and cleaned:** the training's wrapper logged "train ended rc=0" (it
  read `$?` after a `$(date)` in the same line), which started the queued freeze on the
  interrupted model. It exported an ONNX (07:29) and began the archive copy; I killed it at the
  copy, before the local delete. Cleaned: the partial NAS copy (args, results, stream, the
  epoch-1 best/last, byte-identical to the local files) removed; the half-trained
  `xmas02fi6-last-736x1280.onnx` (sha256 e018503f...) removed from the detector folder (no server
  had listed it); the local run untouched. Its log is kept as `freeze-r6-ABORTED-0729.log`. The
  "FROZEN 4338e030..." line in it is NOT this round's freeze.
- **From now on** (`train_sup.sh`, scratch): the training resumes only while no live Run holds
  the GPU (live's detect socket absent), stops again by the same SIGINT if one starts, and resumes
  after. The freeze runs only when results.csv holds all 3 epochs and the last guarded step said
  ALL STEPS OK; every rc is captured before any other expansion.

### Amendment 15 (2026-11-21 08:17 ICT from `date`, BEFORE the freeze and BEFORE any held-out label): the evaluation's inputs, fixed

- **The training resumed** at 08:13:54 after Batt's live Run ended (07:42, his bag full) and the
  cursor probes' server step ended: "Resuming MID-EPOCH from mid.pt: epoch 2 batch 0/2729, state
  restored bitwise" (the epoch-end checkpoint; ~2 min of epoch 2 before the 07:28 stop redone).
- **After the freeze** (`train_sup.sh` -> `freeze_r6.sh`: the sha256, the ONNX, the guarded
  archive with absolute paths), one chain (`eval_chain_r6.sh`, scratch):
  - **8a:** ifH1, ifH2, ifsH1 labelled `--spec 1080 --eval-test --model <the archived frozen
    weights> --model-sha256 <the freeze's>` (the chain refuses unless the archive's sha256 is the
    freeze's); their refs; the new model's GPU predictions (predict_dir in the worker);
  - **the evaluation pack: `fi_labels.py pack --spec 1080 --round 6 --eval-test --seed 72`**
    (the seed fixed HERE; rounds 1-5 and T2 used 61, 63, 65-69, 71);
  - **8b:** the 720 round 5's held-out (fsH1, fiH1, fiH2): their own eval label files as
    archived on 11-12 (`scratch-archive/2026-11-12/.../xmas-fi/labels-eval-r5`, copied unchanged,
    sha256 listed), their refs, the new model's GPU predictions; the seed-69 key and the answers
    of U and V reused (section 8b: only the predictions are new);
  - GPU steps start only while no live Run holds the GPU and the dev worker is idle.
- Then two NEW blind labellers on the seed-72 pack, `fi_blind_score --both-good`, the latency
  steps (I5 against xmas02fi5), and `fi_eval --strata r6` once (8a), `--strata r5` once (8b).

### Amendment 16 (2026-11-21 09:47 ICT from `date`, BEFORE any answer to the evaluation pack and BEFORE any score): the held-out is SHORT -- one extension, by the earlier rounds' rule

- **The freeze (09:30:26):** `last.pt` sha256 `4014ae968b08ff9f99a377b5d6bfde404776e656d4a2454dca6061a8fbed94ef`
  (5,529,242 bytes; archived to `archive/train/xmas02-fi-r6-1080-20261121`, the NAS copy's
  sha256 the same); ONNX `xmas02fi6-last-736x1280.onnx` sha256 `3f05f9bb...` (names
  `["floor_item"]`); registered as `xmas02fi6` (903f0b3f; not in MAP_MODELS). The training ended
  ALL STEPS OK after 3 epochs (VAL, monitor only: P 0.931, R 0.897, mAP50 0.901).
- **The evaluation inputs (Amendment 15's chain, 09:31-09:42):** the held-out labelled
  `--eval-test` against it: ifH1 8 item labels (8 floor items in the packets), ifH2 9 (7),
  ifsH1 92 (124). The seed-72 pack: **55 crops, of them 35 ITEM crops** (natural 8, staging 27;
  both slots short) + 20 E. GPU predictions made for 8a and 8b. NOTHING answered or scored.
- **So 8a cannot be scored as registered:** I1h needs >= 40 evaluated crops and the pack holds 35
  item crops; I2 needs >= 20 drop episodes and the natural held-out holds 15 floor items. Under
  the plan both would be NO VERDICT ("never a pass") whatever the model does.
- **The extension (the earlier rounds' rule: a short held-out count takes the NEXT held-out
  session once -- "fiT3 next" -- and a second short count stays NO VERDICT):**
  - **ifsH2**: a held-out staging, `--views near --n 4 --seed 2612281`, spots (82,49), (192,127),
    (159,162), (213,93): its cells share NONE with all 18 stagings on this map (the 14 earlier,
    ifsH1, ifs1c, ifs2b, ifs3: 1,932 cells). No 6-spot plan is clean in seeds 2612230-2612399;
    4 spots is the largest found;
  - **ifH3, ifH4**: two natural-drop held-out pilots, the chain's own (pilot_rec.sh, 25 min,
    xmas02v1080, stage2_ab's setup, NOT immune: immunity OFF read back first);
  - the three names join the held-out refused by name (fi_labels.IF_HELD_OUT; fi_eval /
    fi_labels R6_STAGING for ifsH2), a code change with tests before they are labelled;
  - then ALL six held-out sessions labelled `--eval-test` against the same frozen model, a NEW
    pack `--round 6 --eval-test --seed 73` over all six (the seed-72 pack and key are set aside,
    never shown), two NEW blind labellers, and `fi_eval --strata r6` ONCE. A count still short
    then stays NO VERDICT and is reported so.
- 8b (the 720 round 5's held-out, its inputs complete) is unchanged and scored once beside it.

### Amendment 17 (2026-11-21 10:08 ICT from `date`): 8b FAILS (scored once, 10:08:06)

- **8b: the 720 round 5's own held-out** (fsH1, fiH1, fiH2; their eval labels, the seed-69 key
  sha256 `86695fbf9aee3e20...` and the answers of U / V, archived 11-12 and reused unchanged;
  both-good 81 crops), only the predictions new: xmas02fi6, GPU (predict_dir) and ONNX
  (fi_onnx_pred). `fi_eval --strata r5`, score sha256 `b80a832d7c63dd19...`:

  | bar (round 5's) | xmas02fi6, GPU | xmas02fi6, ONNX | xmas02fi5 (O26's score) | bar | verdict |
  |---|---|---|---|---|---|
  | I1 recall (aura-off, the pooled 81) | 0.901 (73 / 81) | 0.901 | 0.938 (76 / 81) | >= 0.85 | PASS |
  | I1 precision | 0.979 (776 / 793) | 0.978 (741 / 758) | 0.990 (803 / 811) | >= 0.85 | PASS |
  | I2 (a drop boxed in its first kept frame) | **0.75 (15 / 20)** | 0.75 | 0.85 (17 / 20) | >= 0.80 | **FAIL** |
  | I3 item-free frames with a box | **0.95 % (16 / 1,682)** | 0.95 % | 0.48 % (8) | <= 0.5 % | **FAIL** |
  | I3 ... inside her 5 x 5 | **0.36 % (6 / 1,682)** | 0.36 % | 0.12 % (2) | <= 0.2 % | **FAIL** |
  | I4 drop-less kills with a box on the death cell | 1.0 % (1 / 97) | 1.0 % | 1.0 % | <= 5 % | PASS |

- **8b: FAIL** ("at 720, no loss"): the 1080 round's model sees fewer drops at once and boxes
  about twice as many non-items on 720 pictures as xmas02fi5.
- Under section 8 **8c does not run for xmas02fi6** (it needs 8a AND 8b). 8a is still scored once
  as registered (Amendment 16's extension), and reported: it says whether the model helps AT
  1080. Any use of a model per screen size (xmas02fi6 at 1080 only, xmas02fi5 at 720) would be a
  new decision, Batt's, not this round's.

### Amendment 18 (2026-11-21 11:04 ICT from `date`, BEFORE any answer): the extended held-out and the seed-73 pack

- The extension (Amendment 16) recorded: ifsH2 (09:48-09:58, 4 / 4 spots, rc 0, immune: judged
  by two toggles 07:32-07:33), ifH3 (21.4 min) and ifH4 (23.2 min), both rc 0, NOT immune
  (immunity OFF read back at 09:59: "Returned to normal state."); all shipped. Code: the names
  refused for TRAIN and stratified (98f54533).
- All six labelled `--eval-test` against the frozen model (4014ae96):

  | held-out | item labels | floor items in the packets | negatives |
  |---|---|---|---|
  | ifH1 / ifH2 / ifH3 / ifH4 (natural) | 8 / 9 / 6 / 19 = 42 | 8 / 7 / 10 / 10 = 35 | 723 / 714 / 762 / 837 |
  | ifsH1 / ifsH2 (staging) | 92 / 17 = 109 | 124 / 85 | 136 / 89 |

- Refs over all six (4,029 frames), the GPU predictions over them (10:59), and **the pack
  `--round 6 --eval-test --seed 73`** (11:03:30): **80 crops, 60 ITEM crops** (natural 20,
  staging 40; both slots short of their caps) + 20 E; strata N 22 / F 37 / M 1 / E 20; the
  answer key sha256 `4908d9a98f278778...` (never shown). The seed-72 pack and key stay unused.
- Two NEW blind labellers, AK and AL (subagents that see only the pack), then `score_8a.sh`
  (scratch): the ONNX set, I5's CPU and GPU latency against xmas02fi5 in a quiet window,
  both-good, and `fi_eval --strata r6 --comparator xmas02fi5`, ONCE. Reported beside 8b's FAIL.

### Amendment 19 (2026-11-21 14:40 ICT from `date`, BEFORE the 8a score): Batt's decision -- a model per screen size; improve until it passes

- Asked (the 14:08 report, decision 3): "If 8a passes: use the new item model at 1080 only?"
  Batt answered "ใช้ ปรับปรุงให้ผ่าน" ("use it; improve it until it passes").
- Written before 8a is scored. score-8a.log's last line is 11:16:41, "both answer files hold
  80". No 8a number exists; the step waits for a quiet GPU.
- **A model per screen size** (a new decision, Batt's; Amendment 17 said it would be his):
  - at 1080 the 1080 round's model;
  - at 720 xmas02fi5 stays;
  - so 8b (720, no loss) no longer gates a 1080-only use. Its FAIL stands as recorded.
- **If 8a PASSES** (scored once, the bars of section 8a unchanged):
  - 8c runs at 1080 as registered: A = xmas02fi5, B = xmas02fi6, 3 valid runs a side;
  - if 8c passes, xmas02fi6 is deployed for 1080 only (live on Batt's word, as every promote).
- **If 8a or 8c FAILS:** a round 7, "improve it until it passes". Its changes are
  pre-registered before any of its data, and it gets a NEW 1080 held-out (this round's are
  spent once scored).
- The code that picks the item model by the client's screen size is built and tested before 8c.
  It is not built yet.

### Amendment 20 (2026-11-21 15:04 ICT from `date`): 8a FAILS on I3 (scored once, 14:59:41); a round 7 follows (Amendment 19)

- **8a** was scored once on the extended 1080 held-out by `score_8a.sh`. Inputs:
  - six sessions: ifH1-ifH4 natural, ifsH1-ifsH2 staging;
  - the seed-73 pack, with two new blind labellers, AK and AL;
  - `fi_eval --strata r6 --comparator xmas02fi5`; score sha256 `8aed934c6c24ba4b...`.
- It ran in the quiet window after Batt's dev Run ended (14:53:22): no live Run, the worker
  idle.

  | bar (section 8a) | xmas02fi6, GPU | ONNX | bar | verdict |
  |---|---|---|---|---|
  | I1h recall (both-good, pooled 6) | **1.000 (53 / 53)** | 1.000 | >= 0.90 on >= 40 | PASS |
  | I1n natural alone (reported) | 1.000 (16 / 16); staging 37 / 37 | same | reported | -- |
  | I1p precision | 0.963 (1,605 / 1,666) | 0.963 | >= 0.95 | PASS |
  | I2 drop boxed in its first kept frame | 0.889 (8 / 9) | same | >= 0.80 on >= 20 | NO VERDICT (9 < 20) |
  | I3 item-free frames with a box | **1.32 % (40 / 3,019)** | same | <= 0.5 % | **FAIL** |
  | I3 ... inside her 5 x 5 | **0.33 % (10 / 3,019)** | same | <= 0.2 % | **FAIL** |
  | I4 drop-less kills boxed | 2.8 % (2 / 71) | same | <= 5 % | PASS |
  | I5 GPU p95 (server forward) | 18.86 ms vs xmas02fi5 18.57 (1.016 x) | -- | <= 35 ms, <= 1.10 x | PASS |
  | I5 CPU p95 | 170.3 vs 169.0 ms (1.008 x) | -- | <= 1.10 x | PASS |

- **8a: FAIL.** At 1080 the model found every evaluated drop. It also boxed something that is
  not an item on 1.32 % of item-free frames, 2.6 x the bar, and on 0.33 % inside her 5 x 5.
  - The I1h set is 53 both-good crops of 38 distinct pictures (Amendment 18's caveat).
  - xmas02fi5 was not run on this held-out: the comparator enters I5 only.
- Under Amendment 19:
  - 8c does not run for xmas02fi6; it is not deployed; live keeps xmas02fi5.
  - **A round 7 follows ("improve until it passes"):**
    - its change, aimed at the false boxes, is pre-registered before any of its data;
    - it is scored once on a NEW 1080 held-out (this round's are now spent).
  - Its first step: look at the 40 I3 frames (where the boxes are, on what) to choose that
    change. That reading is diagnosis on a spent held-out; it scores nothing.
