---
doc_type: plan
status: ACTIVE
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [xmas02-1080-detector.md, xmas02-detector.md, rogue-xmas02.md, screen-size-ab.md, fullscreen-client.md, ../../scripts/fi_labels.py, ../../scripts/fi_eval.py, ../../scripts/stage_items.py, ../../scripts/build_frame_cache.py]
next_action: "ROUND 11 (Amendment 41): xmas02fi9 = xmas02fi8 retrained with its own false boxes on rounds 8-10's spent held-outs as hard negatives (those 27 sessions join TRAIN), round 10's rule unchanged; a NEW held-out ifH41+ / ifsH11-12 (stagings in a later amendment), seed 79, scored ONCE by a wrapper committed first. Pass -> 8c (Batt deploys); fail -> round 12 from its diagnosis."
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

### Amendment 21 (2026-11-21 15:07 ICT from `date`): the 8a false boxes read (diagnosis on the spent held-out; scores nothing)

- **What I3 counted.** Script: `diag_i3.py`, scratch, which replays `fi_eval.i3`.
  - 45 boxes on 42 item-free frames; 10 of the boxes are inside her 5 x 5.
  - The four natural held-outs give the scored 40 frames: ifH1 9, ifH2 12, ifH3 8, ifH4 11.
    The stagings ifsH1 and ifsH2 have 1 frame each.
- **Confidence separates most of them.**
  - The 45 false boxes: 20 score 0.26-0.33, 10 score 0.37-0.47, and 15 score 0.57-0.77.
  - The 53 drops the model found: their best box scores 0.54-0.90.
  - A floor of 0.5 keeps all 53 drops and leaves 15 false frames: 13 of the natural 40, about
    0.43 % of 3,019.
  - Without the floor, the 0.5 % bar needs 15 frames or fewer.
- **The confident ones** (a contact sheet of the 15, scratch only):
  - 7 sit on the client's red NO-ENTRY cursor ring: ifH2 frames 497-502, all inside her 5 x 5,
    and ifH3 f152. At 1080 the client draws its cursor at native size (section 1), so it is
    item-sized in the virtual picture.
  - The other 8 are small round sprites on the floor, not identified from the crops.
- **Round 7's candidates** (not pre-registered yet; this amendment fixes no number):
  1. A 1080-only confidence floor near 0.5, the loot's own detector setting.
  2. "The bot's own cursor is never an item": an item box at the pointer's place is dropped.
     The runner always knows where it put the pointer.
  3. 1080 frames with the cursor rings as hard negatives in training.
- Any of them is scored on a NEW 1080 held-out (Amendment 19). The numbers above choose the
  candidates; they never pass them.

### Amendment 22 (2026-11-21 16:11 ICT from `date`, BEFORE any round-7 data): ROUND 7 pre-registered -- round 6's model plus a 1080 box rule (Batt: "use the recommended way", A + B)

- **Two facts read on the spent held-out, both diagnosis.** They choose the rule; they score
  nothing.
  - **The pointer is the wrong signal.** Measured from the input log's pointer at each frame's
    time: 2 of the 53 found drops lie within 20 px of the bot's pointer, 3 within 30 px. After a
    kill the pointer still rests where the drop falls. A pointer-distance rule would throw real
    drops away, so B is NOT "near the pointer".
  - **The ring's own pixels are the signal.** Pure red = R >= 150, G <= 30, B <= 30, counted in
    the box plus 6 px. The 8 false boxes on the no-entry cursor ring (the 7 confident ones and
    one at 0.27) hold 81-115 pure-red px each. All 53 found drops hold 0, and so do all 37
    other false boxes.
- **The model:** xmas02fi6 unchanged, frozen (pt 4014ae96..., ONNX 3f05f9bb...). No training
  in round 7 unless the rule fails (then C, Amendment 21, by a new amendment).
- **The rule** ("fi7"), applied to the item model's boxes at 1080 only (the virtual client),
  before any use:
  - A. Confidence floor **0.50**: a box under it is dropped.
  - B. The cursor ring: a box whose rectangle plus **6** px holds **>= 30** pure-red px
    (R >= 150, G <= 30, B <= 30) in the virtual frame is dropped.
- **The evaluation ("8a7"):** fi_eval applies the rule to the predictions (new options,
  `--item-floor`, `--ring-red`, built with tests before the held-out is labelled).
  - The bars are section 8a's, unchanged, each scored ONCE on a NEW 1080 held-out.
  - xmas02fi5 (the deployed model, no rule) is scored on the same held-out and reported beside
    it. That says what the change does at 1080; it is not a bar.
- **The new held-out:**
  - natural pilots NOT immune (immunity OFF read back before each), named ifH5, ifH6, ...;
    enough of them for I2's 20 first-frame episodes, which 8a's 4 pilots did not reach (9);
  - stagings immune (ifsH3, ...) for I1h's >= 40 evaluated crops;
  - every name refused for TRAIN and stratified, as Amendment 16 did.
  - Labelled `--eval-test` against the frozen model. One pack, seed **74**, recorded before any
    answer. Two NEW blind labellers.
- **If 8a7 passes:**
  - 8c runs at 1080 as section 8c registers it: A = xmas02fi5, B = xmas02fi6 + fi7, 3 valid runs
    a side;
  - the rule is built into the live player first: a setting, the Run-time filter of the item
    boxes (the runner's own LOOT_ITEMS_CONF is a function default, so a runner constant cannot
    move it);
  - if 8c passes, deploy at 1080 only, on Batt's word.
- **If 8a7 fails:** C (training with cursor-ring hard negatives) by a new amendment, and a new
  held-out again.

### Amendment 23 (2026-11-21 16:36 ICT from `date`, BEFORE any round-7 recording): the new held-out's stagings and order

- **The stagings** (`--views near --n 4`, the largest clean size, as ifsH2):
  - **ifsH3: seed 2612519**, spots (104,170), (170,25), (184,205), (38,126);
  - **ifsH4: seed 2612675**, spots (49,49), (25,236), (71,94), (96,170).
  - Their cells share NONE with the 19 earlier stagings on this map (1,980 distinct cells: the
    14 earlier, ifsH1, ifs1c, ifs2b, ifs3, ifsH2), nor with each other.
  - No 6-spot plan was clean in seeds 2612400-2612699; the 4-spot hits were 2612519, 2612589
    and 2612675. Scratch: `cells/earlier-r7.json`.
- **The order:**
  1. ifsH3, then ifsH4, IMMUNE. Judged at 16:09 on a frame after the dev client's crash
     recovery ("You are now immune to attacks."); the same game session since. `stage_rec.sh`.
  2. Immunity OFF, its reply read on a frame.
  3. The pilots ifH5 .. ifH10, NOT immune. `chain.sh` / `pilot_rec.sh`, 25 min each,
     xmas02v1080, stage2_ab's setup (now TOPUP_1080: the Fly Wing to 40 when under 30).
- **The dev client crashed after Batt's dev Run** (access violation, 14:53 .. 15:15). It was
  recovered at 16:08, and the round-7 recordings all come after that.

### Amendment 24 (2026-11-21 21:55 ICT from `date`, before the round-7 score is read): I5 is measured again, in a quiet window

- Round 7's score wrapper ran at 21:37-21:53 DURING 5b's run c5b-B1 (cursor-1080.md Amendment 11:
  its wait matched a quoted "CHAIN DONE"). So its I5 inputs are void:
  - the CPU latency ran beside B1's start;
  - the GPU latency queried B1's detect server (another model, under play).
- Its fi_eval output (score-r7.json, sha256 ff4f2b481f2dcd7e...) is kept UNREAD in
  data/train/eval/xmas02fi6-r7/void-r7a/. The report-only fi5 pass failed: round 7's strata need
  --comparator.
- **Scored by** xmas02_items_r7b_score.sh (docs/records/scorers), after 5b's chain ends, with no dev
  detect server and no screen_ab run.
  - I5 measured again: eval_latency and fi_gpu_latency, each model.
  - fi_eval again with ONLY the latency files replaced. The labels, the predictions (GPU + ONNX), the
    key, both blind labellers' answers and both-good.json are those of the first pass, so the item
    lines I1-I4 are the same by construction.
  - That run is the round's one score.

### Amendment 25 (2026-11-22 03:21 ICT from `date`): ROUND 7 FAILS on I2 and I3-any (scored once, 03:17:04); the false boxes read

- **The one score** (xmas02_items_r7b_score.sh, Amendment 24; `score-r7.json` sha256 4ea7ffaa...;
  5b's chain ended 03:03:48, no dev detect server, a live Run beside). xmas02fi6 + the fi7 rule
  (floor 0.50, ring 30 px, pad 6), GPU predictions (the ONNX ones give the same verdict):

  | line | got | bar | |
  |---|---|---|---|
  | I1h recall (strata decide) | 65 / 70 = 92.9 % | >= 90 % | PASS |
  | I1 precision | 1,297 / 1,352 = 95.9 % | >= 95 % | PASS |
  | I2 first frame of our kills' drops | 19 / 24 = **79.2 %** | >= 80 % | **FAIL** |
  | I3 any box on an item-free frame | 40 / 5,453 = **0.73 %** | <= 0.5 % | **FAIL** |
  | I3 inside her 5 x 5 | 9 / 5,453 = 0.17 % | <= 0.2 % | PASS |
  | I4 a box at a kill with no drop | 0 / 146 | <= 5 % | PASS |
  | I5 GPU server p95 | 24.85 ms (fi5 24.1; ratio 1.03) | <= 35 ms, <= 1.1 | PASS |
  | I5 CPU p95 ratio | 1.006 | <= 1.1 | PASS |

  - The rule dropped 179 boxes by the floor and 3 by the ring.
  - **Beside it (report-only), the deployed xmas02fi5 with no rule, the same held-out:** I3-any
    70 / 5,453 = 1.28 %, inside 5 x 5 34 = 0.62 %, precision 93.9 %, I1h 63 / 70 = 90.0 %, I2 the
    same 19 / 24. So round 7 cuts false-item frames 70 -> 40 and those near her 34 -> 9, and does
    not reach the bars. (The wrapper's report-only pass refused its arguments: the comparator's GPU
    file given twice. It was run again by hand without the GPU latency input.)
- **Not deployed.** No 8c. The fi7 rule is not built into the live player.
- **The false boxes read** (diagnosis on the now-spent held-out; it scores nothing; scratch
  `diag-r7/diag_r7.py`, which replays fi_eval.i3 after the rule: 42 boxes on 42 frames):
  - **The cursor ring is gone:** 41 of the 42 hold 0 pure-red pixels (the 42nd 26).
  - **19 are one object: the Cruiser's projectile** (a small red cylinder with a blue band). It
    shows beside Cruisers in their fights ("Miss" over her). It stays at one place for runs of
    frames (ifH10 frames 222-352, ifH9 980-1006) while she fights a Cruiser that does not move.
  - About 5: the client's own pointer (the white arrow or sword) at native size.
  - 4: a snowflake mark on the floor (ifH6 1163-1170, one place).
  - About 6: parts of monsters (a Myst Case's ribbon and eyes, a Cookie's head, a Cruiser);
    about 4: dust puffs and damage digits; the rest: small light blobs.
  - Confidence 0.50-0.85, 31-582 px from her.
- **I2's 5 misses** (the same 5 for fi5 and fi6): every one lies under a monster still dying,
  behind its fading body or a skill effect (2.8-5.9 s after the kill). Two of them had a box at
  0.49 and 0.50, at the floor.
- **So C as Amendment 22 wrote it (cursor-ring hard negatives) would not fix what is left.** Round 8
  is pre-registered next, before any round-8 data: hard negatives from the model's own false boxes
  on 1080 TRAIN frames (the Cruiser's projectile first), and drops under dying monsters as
  positives.

### Amendment 26 (2026-11-22 03:26 ICT from `date`, BEFORE any round-8 data): ROUND 8 pre-registered -- retrain with the model's own false boxes as hard negatives; the spent 1080 held-outs join TRAIN

- **Why** (Amendment 25): the fi7 rule removed the cursor ring. What is left are the model's own
  confusions: the Cruiser's projectile (19 of 42), the client's pointer, a snowflake mark, effects.
  A rule cannot name them all, so the model has to learn them as background. Batt's decision
  stands (Amendment 19: "improve it until it passes").
- **TRAIN** = round 6's TRAIN unchanged (Amendment 13: 49 sessions with the linked round-5 cache),
  plus the 14 SPENT 1080 held-out sessions of rounds 6 and 7: ifH1-ifH10 and ifsH1-ifsH4.
  - Each is labelled `fi_labels.py label --spec 1080 --split train` with the frozen params
    (ad268afd...), and judged by G2 as round 6 did (Amendment 7's pool for thin pilots).
  - They are released for TRAIN by name in code (a `released` list, round 8 on). --eval-test still
    reads them, so the old scores stay reproducible. ifF stays FIT / VAL only.
- **Negatives:**
  - the session negatives as round 6: 150 drawn from each pilot's own item-free kept frames (the
    10 new pilots too), and 1 per 3 item frames for the stagings;
  - **every hard negative:** an item-free kept frame (by its TRAIN labels) on which xmas02fi6
    boxed an item at conf >= 0.25 (fi_eval.CONF), with no rule. They are mined from:
    - the GPU predictions already made on the 14 spent held-outs. Counted at 03:2x on their
      eval labels' item-free frames: 42 (round 6) and 114 (round 7); the TRAIN labels decide the
      final set;
    - new CPU ONNX predictions of xmas02fi6 (its frozen ONNX) over the item-free kept frames of
      round 6's 10 TRAIN pilots (ifT1-ifT10).
  - A listed frame that the TRAIN labels do not keep as item-free is not written; it is counted.
    Each hard negative is written once (no oversampling).
- **The model, xmas02fi8:**
  - trained from xmas02fi6's last.pt (4014ae96...) with round 6's trainer settings (Amendment 13:
    --batch 2 --hsv-s 0.2 --close-mosaic 3 --scale 0.1, imgsz 1280, seed 20261004);
  - epochs by section 7's formula on the combined TRAIN (3 at the expected ~7,500 frames);
  - the fi7 rule unchanged at inference (floor 0.50, ring 30, pad 6). ("fi7" stays the rule's
    name; the model is fi8.)
- **The GPU:** the training starts after the ranged-attacker A/B's chain ends on the dev lab,
  because that A/B's arms share the Arc.
  - It does not stop for a live Run. Batt, 11-21 20:2x: "dev need not wait for live; live slower
    is fine".
  - The live detect server's minute p95 is logged during the training and reported. If Batt says
    otherwise, Amendment 14's yield comes back.
- **The new held-out:**
  - natural pilots ifH11, ifH12, ... (NOT immune, OFF read back before each; 25 min each;
    xmas02v1080). As many as I2's 20 first-frame episodes need (round 7: 6 pilots gave 24), so 6
    to start, then Amendment 16's one-extension rule;
  - stagings ifsH5 and ifsH6, immune. Their seeds and cells come in a later amendment, before any
    recording, and share no cell with any earlier staging;
  - every name refused for TRAIN in code before its first recording;
  - labelled --eval-test against the frozen xmas02fi8; one pack at seed **75**; two NEW blind
    labellers.
- **The bars:** section 8a's, unchanged (Amendment 25's table), scored ONCE by a wrapper committed
  before the score. Reported beside them (no bar): xmas02fi6 + fi7 and xmas02fi5 on the same
  held-out.
- **If it passes:** 8c at 1080 (A = xmas02fi5, B = xmas02fi8 + fi7, 3 valid runs a side).
  - The rule and the per-screen model picker are built into the live player first.
  - Then it is deployed at 1080 only, on Batt's word.
- **If it fails:** a round 9, pre-registered from its diagnosis.
- **Not in round 8:** items under a dying monster as labels. The label rule's `under_unit`
  exclusion stays; I2 is reported with its misses read.
- **Code first, with tests, before any round-8 label:**
  - fi_labels: round 8's held-out names (refused for TRAIN) and the released list;
  - build_frame_cache `--hard-negs FILE`;
  - fi_eval `--strata r8`;
  - the mining script.

### Amendment 27 (2026-11-22 03:57 ICT from `date`, BEFORE any round-8 recording): the new held-out's stagings and order

- **The stagings** (`--views near --n 4`, as round 7's):
  - **ifsH5: seed 2612744**, spots (225,137), (71,216), (192,104), (49,25);
  - **ifsH6: seed 2612749**, spots (115,159), (181,148), (38,104), (203,236).
  - Their cells share NONE with the 21 earlier stagings on this map (2,076 distinct cells: round
    7's 19 + ifsH3 + ifsH4, whose spots were recomputed and match Amendment 23), nor with each
    other. Seeds 2612700-2612999 gave 5 clean 4-spot plans (2612744, 2612749, 2612849, 2612934,
    2612948); the first two that share no cell are taken. Scratch: `cells/earlier-r8.json`.
- **The order**, after the ranged-attacker A/B's chain ends on the dev lab:
  1. ifsH5, then ifsH6, IMMUNE (`stage_rec.sh`; immunity ON judged on a frame first);
  2. immunity OFF, its reply read on a frame;
  3. the pilots ifH11 .. ifH16, NOT immune (`chain.sh` / `pilot_rec.sh`, 25 min each,
     xmas02v1080, TOPUP_1080).
- The recordings may run while xmas02fi8 trains on the GPU. They are labelled (--eval-test) only
  after its freeze (O.9).

### Amendment 28 (2026-11-22 07:50 ICT from `date`): the held-out pilots wait for the training; an aborted ifH12

- **Done so far:** ifsH5 (06:54-07:04) and ifsH6 (07:05-07:15), immune and shipped; immunity OFF
  judged at 07:15 ("Returned to normal state." on a frame); ifH11 (07:17-07:47) played and shipped.
- **The training started at 07:44:37** in the gap after ifH11: 62 sessions, 7,282 frames
  (2,095 with items, 5,187 negatives), 242 hard negatives all item-free by the TRAIN labels (202
  beyond the draw), written counts EQUAL to the dry run; 3 epochs from xmas02fi6's last.pt.
- **ifH12 was stopped at 07:49:25 by its own setup:** "the detect server refused". The dev GPU
  worker runs ONE job, and the training holds it. Amendment 27's "the recordings may run while
  xmas02fi8 trains" does not hold on this host: round 6's supervisor waited for the same reason.
  - That 36-frame recording was shipped; it is renamed on the NAS
    `20261122T074851-rdp-xmas02-ifH12-ABORTED` and is not part of the held-out.
- **The rest:** ifH12 .. ifH16 start once the training has ended (r8_pilots2.sh), with the same
  pilot_rec.sh. The held-out is then ifsH5, ifsH6, ifH11 .. ifH16; the one-extension rule
  (Amendment 16) still applies if I2 has fewer than 20 episodes.
- **A slip (mine), no data lost:** the first pilot launcher matched an older "STOP" line in the
  training log and started the pilots at 07:16, before the training. The second launcher waits for
  the training's own end lines only.


### Amendment 29 (2026-11-22 10:49 ICT from `date`, BEFORE any round-8 eval label): the supervisor killed for low memory; the run's end proven by its own files; the pilots resumed

- **What was killed (about 09:42):** the agent host (Claude Code) reaped two background shells
  when the machine ran low on memory: 592 MB available, swap 2.6 of 4 GB in use. The training's
  dataloader workers (4 processes, about 5 GB RSS each, mostly shared) were the largest user.
  - `r8_train.sh`: training run 1's guard, the live p95 watcher, and the freeze after the run;
  - `r8_pilots2.sh`: the waiter that starts ifH12 .. ifH16 after the training.
  - Neither was restarted until Batt said "ok" (11-22 ~10:4x), with a RAM check before each step.
- **The training ran on in the worker and ended at 10:37:19** (results.csv's epoch-3 row; the
  weights were written at 10:37:22). The killed guard never wrote ALL STEPS OK, so
  `freeze_r8b.sh` proves the end from the run's own files instead. All four hold:
  - no trainer process;
  - no `mid.pt` left (the trainer removes it at a run's end);
  - `last.pt` is stripped: its pickle reads epoch -1 and ema / updates None, as round 6's finished
    `last.pt` does (`ckpt_fields.py`, read from the opcodes, nothing executed). Both are
    5,529,242 bytes;
  - `last.pt` is not older than results.csv.
- **FROZEN 10:48:29:**
  - xmas02fi8 `last.pt` sha256 `74092985465cb990d814226fdfaf83d6abb5b9d90a52981bdec1caf175119d42`;
  - ONNX `xmas02fi8-last-736x1280.onnx` sha256
    `371c2f2cfaeefcca6d7e05c76932d8ecb5555464e3a1a7a32d6dbf52ed143297`, classes `["floor_item"]`;
  - archived to the NAS (size and count verified; the NAS `last.pt` has the same sha256), and the
    local copy removed.
  - The single-session validation (ifF) read mAP50 0.974 / 0.948 / 0.931 by epoch. That is not a
    bar; section 8a's bars are scored on the held-out.
- **The live detect server beside the training** (Amendment 26's report): 117 minute values
  were logged from 07:45:07 to 09:41:45, when the watcher was killed. The first was 23.85 ms;
  over the run the median was 155.7 ms, the p95 159.5 ms and the max 161.8 ms. Batt 11-22: dev
  work runs beside live without yielding.
- **Found before the pilots:** the dev Rogue was dead (frame 10:45: HP 1/5070, the death dialog,
  "[Cruiser] inflicts 142 / 145 damage points on you" in the Battle Log).
  - It had stood NOT immune at the stand since ifH12's setup (07:49). No run was playing; the
    death is not a pilot event.
  - It was revived with `@alive`, the dialog's "return to game" button, and the chat input closed.
    Judged on the 10:52 frame: HP 5070/5070, no dialog, the chat closed.
  - pilot_rec.sh's own setup (`@heal`, `@warp xmas_dun02 114 23`, the zoom and chat checks) runs
    before every pilot.
  - A possible cause of ranged-attacker-1080 Amendment 3's void A3 / R2 ("HP 0 after @heal" at
    setup) is a Cruiser shooting the idle Rogue at the same stand. Not proven.
- **The pilots resumed at 10:48:25** (`r8_pilots3.sh`): ifH12 .. ifH16, one `chain.sh` call
  each, every one only while MemAvailable >= 3,000 MB (else it waits, logged).
  - The freeze's CPU export ran beside ifH12's first minutes (10:48:29-10:49:03). The pilots are
    held-out recordings, not timed arms.
  - The eval (refs, GPU predictions, the seed-75 pack, two new blind labellers, the score
    wrapper committed first, fi_eval `--strata r8` once) follows the pilots. The worker is
    single-job.
- **For later trainings (Batt 11-22):** `--workers 2` becomes `--workers 1`. That is data-loading
  parallelism, not a model setting; it costs speed only.
  - Swap grew from 4 to 12 GB: `/swap2.img`, 8 GB, in fstab with `nofail`. RAM cannot grow for
    now.

### Amendment 30 (2026-11-22 14:44 ICT from `date`, BEFORE any blind answer and BEFORE any score): round 8's evaluation inputs; the score wrapper committed

- **The eval chain (`eval_chain_r8.sh`, 13:26-14:39), all steps rc 0:**
  - the frozen sha256 checked against the freeze log (74092985...);
  - the eight held-out sessions labelled `--eval-test` against xmas02fi8: ifsH5, ifsH6,
    ifH11 .. ifH16 (ifH12 is the 10:51 recording; the aborted 07:48 one is not in it);
  - refs: 6,543 frames;
  - GPU predictions of xmas02fi8, xmas02fi6 and xmas02fi5, and xmas02fi8's ONNX on the CPU;
  - the pack, `pack --round 8 --seed 75`: **87 crops**: N 27, F 27, M 13 (67 ITEM crops) and E 20
    (10 plain, 10 hard).
- **The held-out's size, counted from the LABELS only** (no prediction read):
  - I2: 21 drop episodes in the six natural pilots (61 drops of our kills; 8 behind her, 1 of
    them with a kept label). The minimum is 20;
  - I3: 5,630 item-free kept frames (minimums 200 / 500);
  - I4: 131 of our kills without a drop with a judged frame (1 more has none; minimum 40);
  - I1h: 67 item crops in the pack (minimum 40 evaluated: both labellers' good boxes decide).
  - Every minimum is met, so Amendment 16's one extension is not used.
- **For I5:** xmas02fi8 is registered for the detect server (ac1cda92; not in MAP_MODELS), and
  its ONNX is copied to the storage folder's models (`archive/models`, sha256 371c2f2c... read
  back), as xmas02fi6's was.
- **Two NEW blind labellers, L1 and L2:** fresh agents that open only the pack's folder
  (instructions, reference, crops) and write `t4/answers-eval-r8-L1.json` / `-L2.json`. They
  started at 14:41 and 14:4x, before this amendment, and no answer has been read.
- **The score:** `docs/records/scorers/xmas02_items_r8_score.sh`, committed here, runs ONCE after
  both answer files hold 87 entries:
  1. a latency sample (every 7th ref): CPU xmas02fi8 vs xmas02fi5; GPU, the detect server's
     forward, each model. It waits for no dev detect server, no screen_ab run, an idle worker and
     2.5 GB available; a live Run may play beside, and the log says so;
  2. both-good (`fi_blind_score`); a failed blind step stops with no score;
  3. THE BARS: `fi_eval --strata r8 --comparator xmas02fi5` on xmas02fi8's GPU and ONNX sets with
     the fi7 rule unchanged (floor 0.50, ring 30, pad 6);
  4. report only (no bar): xmas02fi6 + the fi7 rule, and xmas02fi5 without it, on the same
     evaluated crops.

### Amendment 31 (2026-11-22 15:21 ICT from `date`): ROUND 8 FAILS on I1h by one crop (scored once, 15:07:39); the misses read

- **The one score** (`xmas02_items_r8_score.sh`, committed in 2db1e6d2 before any answer; ran
  14:45-15:08; `score-r8.json` sha256 6876291d...; a live Run played beside). xmas02fi8 + the fi7
  rule (floor 0.50, ring 30 px, pad 6), GPU predictions; the ONNX ones give the same verdict on
  every line:

  | line | got | bar | |
  |---|---|---|---|
  | I1h recall (the stratum decides) | 53 / 59 = **89.8 %** | >= 90 % | **FAIL** |
  | I1 precision | 1,129 / 1,148 = 98.3 % | >= 95 % | PASS |
  | I2 first frame of our kills' drops | 18 / 21 = 85.7 % | >= 80 % | PASS |
  | I3 any box on an item-free frame | 15 / 5,425 = 0.28 % | <= 0.5 % | PASS |
  | I3 inside her 5 x 5 | 4 / 5,425 = 0.07 % | <= 0.2 % | PASS |
  | I4 a box at a kill with no drop | 2 / 131 = 1.5 % | <= 5 % | PASS |
  | I5 GPU server p95 | 24.16 ms (fi5 23.45; ratio 1.03) | <= 35 ms, <= 1.1 | PASS |
  | I5 CPU p95 ratio | 1.008 (178.3 vs 176.9 ms) | <= 1.1 | PASS |

  - The blind step: both labellers answered all 87; q1 agreed on 87, q2 on 84. Good boxes: L1 62,
    L2 59; both good: **59** (the evaluated crops). Every E crop answered "no" by both.
  - The rule dropped 124 boxes by the floor and 26 by the ring.
  - I1h by session: ifH11 0 / 3, ifH12 15 / 15, ifH13 12 / 12, ifH14 4 / 4, ifH15 8 / 9,
    ifH16 5 / 7, ifsH5 3 / 3, ifsH6 6 / 6 (natural 44 / 50, staging 9 / 9).
  - **Round 7's two failures are fixed:** I2 79.2 -> 85.7 %, I3-any 0.73 -> 0.28 %.
- **Beside it (report only, the same held-out and evaluated crops):**

  | | I1h | precision | I2 | I3-any | I3 5 x 5 | I4 |
  |---|---|---|---|---|---|---|
  | xmas02fi6 + the fi7 rule | 53 / 59 | 96.8 % | 19 / 21 | 29 = **0.53 %** | 6 = 0.11 % | 2 / 131 |
  | xmas02fi5, no rule (deployed) | 49 / 59 | 92.1 % | 17 / 21 | 86 = 1.59 % | 61 = 1.12 % | 5 / 131 |

- **Not deployed.** No 8c.
- **The 6 missed crops are 3 items** (from the predictions and the labellers' own notes, read after
  the score):
  - ifH11 floor item 403, frames 1090, 1091, 1095: an egg partly under a dark wooden block.
    xmas02fi8 boxed it on 1095 at conf 0.445, under the floor; on 1090 and 1091 it gave no box
    at the predictor's 0.25. xmas02fi6 and xmas02fi5 boxed it in none of the three.
  - ifH16 floor item 464, frames 991, 993: beside a post, with the pointer near. xmas02fi8 0.468
    on 991, under the floor; nothing on 993. xmas02fi6 boxed both (0.61, 0.52).
  - ifH15 floor item 454, frame 706: under damage digits. No model boxes it.
  - **So 2 of the 6 misses were the floor's** (boxes at 0.445 and 0.468); 4 had no box at all.
    xmas02fi8 is less sure of true items than xmas02fi6. It learnt 242 hard negatives, and the
    0.50 floor was fitted on xmas02fi6's round-6 boxes (Amendment 21).
  - I2's 3 misses: ifH11 1090 (the same egg), ifH12 1223 (floor item 410), ifH16 991.
- **The floor's sensitivity (on the now-spent held-out; it scores nothing; scratch
  `r8/sens/`):** xmas02fi8 + the rule (ring 30, pad 6) at other floors, GPU (ONNX the same counts):

  | floor | I1h | precision (false) | I2 | I3-any | I3 5 x 5 | I4 |
  |---|---|---|---|---|---|---|
  | 0.30 | 55 / 59 | 96.5 % (43) | 19 / 21 | 35 = 0.65 % | 10 = 0.18 % | 3 |
  | 0.35 | 55 / 59 | 97.3 % (33) | 19 / 21 | 26 = 0.48 % | 8 = 0.15 % | 3 |
  | **0.40** | **55 / 59** | 97.9 % (25) | 19 / 21 | 19 = 0.35 % | 6 = 0.11 % | 2 |
  | 0.45 | 54 / 59 | 98.1 % (22) | 19 / 21 | 17 = 0.31 % | 4 = 0.07 % | 2 |
  | 0.50 (scored) | 53 / 59 | 98.3 % (19) | 18 / 21 | 15 = 0.28 % | 4 = 0.07 % | 2 |

  At 0.40 every line would sit inside its bar here. That is fitted on this held-out, so it is not a
  pass. Round 9 tests it on a NEW one (Amendment 32).

### Amendment 32 (2026-11-22 15:21 ICT from `date`, BEFORE any round-9 data): ROUND 9 pre-registered -- xmas02fi8 unchanged, the fi7 rule's floor at 0.40, a NEW held-out

- **Why** (Amendment 31): round 8 misses I1h by one crop. 2 of its 6 misses are boxes the 0.50
  floor dropped (0.445, 0.468), and every other line passes with a margin. A floor is the
  smallest change that addresses what was found; a new training is not needed for it.
- **The change, and only it:** the fi7 rule's floor 0.50 -> **0.40**. Chosen on round 8's spent
  held-out (Amendment 31's table) by one rule: the highest floor, of 0.30-0.50 in steps of 0.05,
  that finds the most I1h crops. Ring 30 px and pad 6 are unchanged. The model is xmas02fi8
  unchanged (last.pt 74092985..., ONNX 371c2f2c...): no training, no new cache.
  - This is how round 7 got its rule: chosen on spent data (round 6's, Amendment 21), then
    tested on a new held-out.
- **The new held-out** (every name refused for TRAIN in code before its first recording):
  - **stagings, immune**, `--views near --n 4`, as rounds 7 and 8:
    - **ifsH7: seed 2612934**, spots (60,93), (225,205), (236,170), (137,214);
    - **ifsH8: seed 2613040**, spots (81,180), (236,38), (49,181), (159,192).
    - Their cells share NONE with the 23 earlier stagings on this map (2,172 distinct cells:
      `cells/earlier-r9.json` = round 8's file + ifsH5 + ifsH6), nor with each other.
      2612849 and 2612948 (round 8's other clean seeds) now share 12 cells each with ifsH5 /
      ifsH6. 2613040 is the first clean seed of 2613000-2613299.
  - **natural pilots ifH21, ifH22, ...**, NOT immune (OFF read back before each), 25 min each,
    xmas02v1080, the same chain (`chain.sh` / `pilot_rec.sh`). 6 to start, then Amendment 16's
    one extension if I2 has fewer than 20 episodes or the pack fewer than 40 item crops. The
    extension's names are reserved too: ifH21 .. ifH30.
  - The order: ifsH7, then ifsH8 (immunity ON judged on a frame first); immunity OFF, its reply
    read on a frame; then the pilots.
  - Labelled `--eval-test` against xmas02fi8 (the labels' model and params unchanged). One pack,
    `pack --round 9 --seed 76`; two NEW blind labellers.
- **The bars:** section 8a's, unchanged, scored ONCE by a wrapper committed before the score
  (round 8's wrapper with `--strata r9` and `--item-floor 0.4`). I5 is measured again in the same
  way (the model is the same; the rule is a CPU step after the detector).
  Reported beside them (no bar), on the same held-out: xmas02fi8 + the rule at 0.50 (round 8's),
  xmas02fi6 + the rule at 0.50, and xmas02fi5 with no rule.
- **Round 8's held-out is spent.** It stays refused for TRAIN until a training round releases it
  by name.
- **If it passes:** 8c at 1080 (A = xmas02fi5, B = xmas02fi8 + the fi7 rule at 0.40, 3 valid runs a
  side). The rule and the per-screen model picker are built into the live player first, then it is
  deployed at 1080 only, on Batt's word.
- **If it fails:** a round 10, pre-registered from its diagnosis.
- **Code first** (this commit's sibling): fi_labels' and fi_eval's round 9 names (ifH21-ifH30,
  ifsH7, ifsH8), seed 76 and `--strata r9`, with tests.

### Amendment 33 (2026-11-22 17:08 ICT from `date`, BEFORE any round-9 eval label): the dev client crashed during ifH22; that attempt is ABORTED and ifH22 is recorded again

- **Done so far:** ifsH7 and ifsH8 (immune, shipped), immunity OFF judged on a frame, then
  ifH21 (15:52-16:22: 1,637 frames, no pause, the time box ended normally; shipped).
- **ifH22's first attempt (recording from 16:23:41):** the dev client crashed at **16:28:38**
  (Windows showed the "Gravity(tm) Error Handler" box, Exception 0xc0000005 in PoringLab.exe, on
  a black desktop). The last game frame is frame 295 (16:28:37); frames 296-320 are the box (the
  recorder stores a frame on change, so 25 frames, one a minute, to 16:52).
  - The runner paused at 16:28:38 (the taskbar showed) and pressed nothing until the series'
    time-box Stop at 16:53. Its own log says "Ended: input_refused", but the series and
    `pilot_rec.sh` said `play rc=0`, so the session SHIPPED with 4 min 57 s of play.
  - It does not meet this held-out's definition (25-min natural pilots, Amendment 32). It is
    renamed on the NAS `20261122T162341-rdp-xmas02-ifH22-ABORTED` (its checksums verified after
    the rename) and is NOT part of the held-out, as round 8's ifH12 attempts (Amendment 28).
  - The decision rests on the crash alone: no label, box or item crop of that session was looked
    at (only frames 289-297's brightness and two frames of the error box).
- **ifH23's first start (16:53:43)** stopped before any recording: the identity check read no
  name plate (the box was on the screen), so nothing was typed; "zoom not default". Its
  leftovers are renamed `-aborted-1706`; no session was made.
- **Recovery (17:00-17:05):** the box's Exit closed the box but not the process; the server still
  had the Rogue online. Three PoringLab.exe processes were found from the agent's own
  non-elevated shell (today's crashed one and two windowless ones left from 11-20) and ended by
  id; the account went offline; one `ro_agent.py recover gm --retries 0` was in game at 17:05:40.
  The idle Rogue, not immune, had been killed while the crashed client held her session; each
  pilot's own start heals her (`@heal`) and warps her to the stand.
- **The rest:** ifH22 (recorded again under the same name), then ifH23 .. ifH26, by
  `r9_pilots2.sh` from 17:07. It adds one check after each pilot: the recording holds at least
  1,400 frames (a full pilot held 1,603-1,723 in rounds 8-9) and the run log has no PAUSED line;
  otherwise it stops for a person. Nothing else changes: the held-out is ifsH7, ifsH8 and
  ifH21 .. ifH26 (plus Amendment 32's one extension if a minimum is short), labelled, packed and
  scored as Amendment 32 says.

### Amendment 34 (2026-11-22 21:11 ICT from `date`, BEFORE any blind answer and BEFORE any score): round 9's evaluation inputs; the pack step run again after a command-line fix

- **The eval chain (`eval_chain_r9.sh`).** It waited for the pilots' own last line (19:42:06), then
  ran 19:42-20:54:
  - the frozen sha256 checked against the freeze log (74092985..., the archive matches);
  - the eight held-out sessions labelled `--eval-test` against xmas02fi8, all rc 0: ifsH7, ifsH8,
    ifH21 .. ifH26. ifH22 is the 17:08 recording; the crashed 16:23 attempt (`-ABORTED`,
    Amendment 33) is not in it;
  - refs: 6,753 frames;
  - GPU predictions of xmas02fi8, xmas02fi6 and xmas02fi5, and xmas02fi8's ONNX on the CPU, all
    rc 0.
- **The pack step stopped at the command line** (20:54:46, rc 2): `--round: invalid choice: '9'`.
  - Round 9's code (5a79a123) taught every pack function round 9 but left the parser's `--round`
    choices at 1-8. Its tests called the functions directly and never parsed the command line.
  - Fixed in **b3e13bba**: the choices are `PACK_ROUNDS` (1-9). A new test runs Amendment 32's own
    command line through `main()`. Nothing else changed: fi_eval is byte-identical to round 9's
    code commit, and fi_labels differs from it only in those parser lines.
  - The pack step alone was run again at b3e13bba (built 21:03:20, rc 0), with the chain's command
    unchanged: `pack --spec 1080 --round 9 --eval-test --seed 76` over the same eight label files.
    No pack existed before it, and no answer or score exists.
- **The pack (seed 76): 104 crops.** By stratum: N 36, F 45, M 3 (**84 ITEM crops**) and E 20 (10
  plain, 10 hard). The natural slot drew 53 of its 70 and the staging slot 31 of its 50 (the
  summary's `short`: 17 and 19).
- **The held-out's size, counted from the LABELS only** (no prediction read; `size_r9.py` with
  fi_eval's own selection rules):
  - I2: **23** drop episodes in the six natural pilots (49 drops of our kills; 11 behind her, 3 of
    them with a kept label). The minimum is 20;
  - I3: **5,922** item-free kept frames (minimums 200 / 500);
  - I4: **142** of our kills without a drop with a judged frame (2 more have none; minimum 40);
  - I1h: **84** item crops in the pack (minimum 40 evaluated: both labellers' good boxes decide).
  - Every minimum is met, so Amendment 32's one extension (ifH27+) is not used. The held-out is
    ifsH7, ifsH8 and ifH21 .. ifH26.
- **For I5:** the model is round 8's, unchanged. xmas02fi8 is still registered for the detect
  server, and its ONNX is the same file in the detector's model folder.
- **Two NEW blind labellers, L1 and L2:** fresh agents that open only the pack's folder
  (instructions, reference, crops) and write `t5/answers-eval-r9-L1.json` / `-L2.json`. They
  started at about 21:09 and 21:10, before this amendment, and no answer has been read.
- **The score:** `docs/records/scorers/xmas02_items_r9_score.sh`, committed in 2cdb4868 (15:27)
  before any round-9 label, is copied to the scratch `score_r9.sh` (`cmp` identical). It runs ONCE,
  after both answer files hold 104 entries. Its steps are Amendment 32's: the I5 latency sample,
  both-good, THE BARS (`fi_eval --strata r9 --item-floor 0.4`), then the report-only lines.

### Amendment 35 (2026-11-22 21:49 ICT from `date`): ROUND 9 FAILS on I3-any (scored once, 21:30:28); the misses read

- **The one score** (`score_r9.sh` = `xmas02_items_r9_score.sh`, committed in 2cdb4868 before any
  round-9 label; ran 21:11-21:30 after both answer files held 104; `score-r9.json` sha256
  5630fcef...; a live Run played beside). xmas02fi8 + the fi7 rule at floor **0.40** (ring 30 px,
  pad 6), GPU predictions. The ONNX ones give the same verdict on every line:

  | line | got | bar | |
  |---|---|---|---|
  | I1h recall (the stratum decides) | 78 / 81 = 96.3 % | >= 90 % | PASS |
  | I1 precision | 1,517 / 1,554 = 97.6 % (37 false, 10 ambiguous) | >= 95 % | PASS |
  | I2 first frame of our kills' drops | 20 / 23 = 87.0 % | >= 80 % | PASS |
  | I3 any box on an item-free frame | **34 / 5,702 = 0.60 %** | <= 0.5 % | **FAIL** |
  | I3 inside her 5 x 5 | 4 / 5,702 = 0.07 % | <= 0.2 % | PASS |
  | I4 a box at a kill with no drop | 0 / 142 = 0.0 % | <= 5 % | PASS |
  | I5 GPU server p95 | 24.22 ms (fi5 24.72; ratio 0.98) | <= 35 ms, <= 1.1 | PASS |
  | I5 CPU p95 ratio | 1.022 (193.0 vs 188.9 ms) | <= 1.1 | PASS |

  - The blind step: both labellers answered all 104; q1 agreed on 104, q2 on 103. Both said yes to
    all 84 item crops and no to all 20 E crops. Good boxes: L1 82, L2 81; both good: **81** (the
    evaluated crops).
  - The rule dropped 94 boxes by the floor and 23 by the ring (ONNX: 65 and 23).
  - I1h by session: ifH21 15 / 16, ifH22 6 / 6, ifH23 11 / 11, ifH24 2 / 2, ifH25 5 / 5, ifH26
    10 / 12, ifsH7 7 / 7, ifsH8 22 / 22 (natural 49 / 52, staging 29 / 29).
  - **Round 8's failure is fixed:** I1h 89.8 -> 96.3 %. The floor's cost shows on I3-any: 0.28 %
    (round 8 at 0.50) -> 0.60 %.
  - **A correction to Amendment 34:** its "I3: 5,922 item-free kept frames" counted the two stagings
    too. The bar's set is the six natural pilots' (fi_eval's own rule): **5,702**. Its minimums (200
    / 500) are met either way. Round 8's Amendment 30 had the same slip (5,630 vs the score's 5,425).
- **Beside it (report only, the same held-out and evaluated crops; no I5 for these lines):**

  | | I1h | precision | I2 | I3-any | I3 5 x 5 | I4 |
  |---|---|---|---|---|---|---|
  | xmas02fi8 + the rule at 0.50 (round 8's) | 77 / 81 | 97.9 % | 19 / 23 | 28 = 0.49 % | 2 = 0.04 % | 0 / 142 |
  | xmas02fi6 + the rule at 0.50 | 76 / 81 | 97.7 % | 21 / 23 | 24 = 0.42 % | 3 = 0.05 % | 0 / 142 |
  | xmas02fi5, no rule (deployed) | 73 / 81 | 94.1 % | 20 / 23 | 87 = 1.53 % | 41 = 0.72 % | 5 / 142 |

- **Not deployed.** No 8c.
- **The 34 false boxes on item-free frames** (read after the score; scratch `r9/diag-i3.json`,
  `r9/look/`):
  - **16 are two objects held across 8 frames each:**
    - ifH26 frames 298-305, one box at (620, 24) of the 1280 x 720 view, conf 0.79-0.85: a
      snowflake ornament on the wall at the view's TOP edge;
    - ifH23 frames 328-335, one box at (1271, 444), conf 0.47-0.72: an object cut off by the
      view's RIGHT edge.
  - 18 single frames, 4 of them inside her 5 x 5. Of the 6 looked at: part of her own body, a
    Christmas Cookie's body, floor sparkles, and small round blobs that may be scenery or items
    the labels do not know.
  - 6 of the 34 sit between 0.40 and 0.50 (so 0.50 leaves 28 = 0.49 %); 2 sit under 0.45.
- **The floor alone cannot pass both new held-outs** (both spent now; xmas02fi8 + the rule, ring 30,
  pad 6, GPU; scratch `r9/edge-sens.json`):

  | floor | round 8 (I1h / I3-any) | round 9 (I1h / I3-any) |
  |---|---|---|
  | 0.40 | 55 / 59 PASS / 19 = 0.35 % PASS | 78 / 81 PASS / 34 = 0.60 % **FAIL** |
  | 0.45 | 54 / 59 PASS / 17 = 0.31 % PASS | 77 / 81 PASS / 32 = 0.56 % **FAIL** |
  | 0.50 | 53 / 59 **FAIL** / 15 = 0.28 % PASS | 77 / 81 PASS / 28 = 0.49 % PASS |

  Every other line passes in all six cells. The floor trades I1h against I3-any, and each held-out
  sits on the edge of one of them.
- **A view-edge rule separates them** (diagnosis on the two spent held-outs; it scores nothing):
  drop a floor_item box whose CENTRE lies within M px of the 1280 x 720 view's left, right or
  bottom edge, or within T px of its top. The grid read: M 8 / 12 / 16, T 32 / 40, alone and
  together, at floors 0.40 / 0.45 / 0.50:
  - at floor 0.40, M 12 + T 32 drops 3 boxes on round 8 (I3-any 19 -> 16 = 0.29 %) and 17 on round 9
    (34 -> 17 = 0.30 %). Precision rises (round 9: 97.6 -> 98.7 %);
  - **it removes no true item on either held-out, at any floor:** I1h, I2 and I4 are unchanged in
    every cell (round 8: 55 / 59, 19 / 21; round 9: 78 / 81, 20 / 23);
  - M 16 + T 40 gives exactly the same counts as M 12 + T 32 on both; M 8 alone drops nothing;
  - every bar passes on both held-outs at floors 0.40 and 0.45 with it (0.50 still fails round 8's
    I1h).
  - **Why it is not only a fit:** a box centred within 12 px of a side or bottom edge is an object
    cut by the edge; the top 32 px of the view (48 real px at 1080) hold the client's hotbar row
    and, on this map, the wall's ornaments. The bot loots near her (its 5 x 5 and its walk range),
    never at the view's edge: an item there comes back into the view as she moves.

### Amendment 36 (2026-11-22 21:49 ICT from `date`, BEFORE any round-10 data): ROUND 10 pre-registered -- xmas02fi8 + the fi7 rule at 0.40 unchanged, PLUS the view-edge rule (M 12, T 32), on a NEW held-out

- **Why** (Amendment 35): round 9 misses I3-any by 6 boxes (34 against <= 28 allowed); 16 of the 34
  are two objects at the view's top and right edges. On both spent held-outs a view-edge rule drops
  only false boxes, and with it every bar passes on both. The floor alone cannot do that.
- **The change, and only it:** a third part of the rule, **C. the view edge**: after A (the floor,
  0.40) and B (the cursor ring, 30 px, pad 6), drop every floor_item box whose centre lies within
  **12 px** of the 1280 x 720 view's left, right or bottom edge, or within **32 px** of its top.
  - Chosen on the two spent held-outs by one rule: of the grid read (M 8 / 12 / 16, T 32 / 40), the
    smallest margins that drop the most false boxes while keeping every true item (I1h, I2) on
    both. M 12 + T 32 and M 16 + T 40 tie; the smaller is taken.
  - The model is xmas02fi8 unchanged (last.pt 74092985..., ONNX 371c2f2c...), the floor 0.40 and
    the ring unchanged: no training, no new cache.
  - This is how rounds 7 and 9 got their rules: chosen on spent data, then tested on a new
    held-out.
- **The new held-out** (every name refused for TRAIN in code before its first recording):
  - **stagings, immune**, `--views near --n 4`, as rounds 7-9:
    - **ifsH9: seed 2613315**, spots (59,116), (225,192), (236,101), (94,93);
    - **ifsH10: seed 2613433**, spots (93,192), (223,49), (38,236), (201,192).
    - Their cells share NONE with the 25 earlier stagings on this map (2,268 distinct cells:
      `cells/earlier-r10.json` = round 9's file + ifsH7 + ifsH8), nor with each other. 2613315 is
      the first clean seed of 2613300-2613599; 2613433 the next clean one sharing no cell with it.
  - **natural pilots ifH31, ifH32, ...**, NOT immune (OFF read back before each), 25 min each,
    xmas02v1080, the same chain (`chain.sh`), with round 9's check after each (>= 1,400 frames, no
    PAUSED line). 6 to start, then Amendment 16's one extension if I2 has fewer than 20 episodes or
    the pack fewer than 40 item crops. The extension's names are reserved too: ifH31 .. ifH40.
  - The order: ifsH9, then ifsH10 (immunity ON judged on a frame first); immunity OFF, its reply
    read on a frame; then the pilots.
  - Labelled `--eval-test` against xmas02fi8 (the labels' model and params unchanged). One pack,
    `pack --round 10 --seed 77`; two NEW blind labellers.
  - The size check counts I3 on the natural pilots only (Amendment 35's correction).
- **The bars:** section 8a's, unchanged, scored ONCE by a wrapper committed before any round-10
  label: round 9's wrapper with `--strata r10` and the edge rule (`--edge-margin 12 --edge-top 32`).
  I5 is measured again in the same way (the model is the same; the rule is a CPU step after the
  detector). Reported beside them (no bar), on the same held-out: xmas02fi8 + the rule at 0.40
  WITHOUT the edge (round 9's), xmas02fi6 + the rule at 0.50, and xmas02fi5 with no rule.
- **Round 9's held-out is spent.** It stays refused for TRAIN until a training round releases it by
  name.
- **Beside the natural pilots: the popup reader's 1080 run-time check** (item-popup-reader.md
  Amendment 6): `item_popup.py watch` runs from the dev checkout over each whole pilot. It only
  grabs pixels (no input, no file the pilot reads), so the held-out is unchanged by it.
- **If it passes:** 8c at 1080 (A = xmas02fi5, B = xmas02fi8 + the fi7 rule at 0.40 with the view
  edge, 3 valid runs a side). The rule and the per-screen model picker are built into the live
  player first, then it is deployed at 1080 only, on Batt's word.
- **If it fails:** a round 11, pre-registered from its diagnosis.
- **Code first** (this commit's sibling): the view-edge rule (`fi7_rule.edge_drop`, `fi_eval
  --edge-margin / --edge-top`), fi_labels' and fi_eval's round 10 names (ifH31-ifH40, ifsH9,
  ifsH10), seed 77 and `--strata r10`, with tests.

### Amendment 37 (2026-11-22 22:51 ICT from `date`, during round 10's pilots; changes no round-10 step): the player's part C built ahead, off

- **What:** the live player's fi7 rule (`flow_play.item_rule`, 1080 only, outside the byte-pinned
  runner) gains part C, the view edge, as two player settings beside `item_floor_1080` and
  `item_ring_1080`: **`item_edge_1080`** (the sides and bottom) and **`item_edge_top_1080`** (the
  top). Both are **0 = off by default**. It calls `fi7_rule.edge_drop`, the same test `fi_eval
  --edge-*` scores; a test pins the two equal on a grid of centres.
- **Why now:** if round 10 passes, 8c's arm B is `screen_ab --box-set loot_items=xmas02fi8
  --player-set item_floor_1080=0.4 --player-set item_ring_1080=30 --player-set item_edge_1080=12
  --player-set item_edge_top_1080=32`, and nothing waits on code.
- **It changes nothing in round 10:** the pilots play with the rule off (the defaults), and the
  held-out is scored offline by the committed wrapper. The dev checkout is fast-forwarded only after
  round 10's eval chain ends.
- Live gets it only with a promotion on Batt's word, and it stays off there until 8c passes.

### Amendment 38 (2026-11-23 03:05 ICT from `date`, BEFORE any answer and BEFORE any score): round 10's held-out is SHORT on I2 -- the one extension

- **The chain (Amendment 36):** the six pilots ifH31-ifH36 ran 22:43-01:47, each rc 0, >= 1,600
  frames, 0 PAUSED, under the popup watcher. eval_chain_r10.sh: the eight sessions labelled
  `--eval-test` against xmas02fi8 01:48-01:56 (all rc 0), refs 6,629 frames, GPU predictions fi8
  02:08, fi6 02:21, fi5 02:33, ONNX fi8 02:55, the seed-77 pack 03:01:12 (commit bee54533), CHAIN
  DONE.
- **The size check (labels and the pack summary only; `r10/size_r10.py`, I3 on the natural pilots):**

  | count | value | minimum | |
  |---|---|---|---|
  | I2: natural drop episodes | **18** (ifH31-ifH36: 4, 0, 2, 3, 5, 4; the stagings none) | 20 | **SHORT** |
  | I1h: item crops in the pack | 65 (85 crops: E 20, F 37, M 8, N 20) | 40 | met |
  | I3: item-free kept frames (natural) | 5,492 | 200 | met |
  | I4: drop-less kills judged | 133 (2 with no frame) | 40 | met |

- **So the one extension (Amendment 36 -> Amendment 16's rule):** three more natural pilots,
  **ifH37, ifH38, ifH39** (names reserved in Amendment 36; ifH40 stays unused), exactly as
  ifH31-ifH36: `chain.sh` (pilot_rec.sh: 25 min, xmas02v1080, stage2_ab's setup), NOT immune (OFF
  read back before the first), round 9's check after each (>= 1,400 frames, no PAUSED line). Three,
  not two, because one of the six gave no episode at all.
  - **Her build first:** after ifH36 ended, the Rogue was rebuilt for Batt's fists trial
    (fists-1080.md Amendment 1: stats, no weapon, other gear). It is put back to the build ifH31-
    ifH36 played with (Str 1, Agi 99, Vit 1, Int 1, Dex 99, Luk 1; Damascus +8 worn, its shortcut on
    F5, the Knife on F4; both Rosaries, the plain Manteau, Thief Clothes +0), and her status window
    is read against the old one (HIT 205, FLEE 246 + 1, Aspd 176) before ifH37.
  - The popup reader's round-4 watcher runs beside each (item-popup-reader.md Amendment 11): these
    recordings are sessions of its set w1080b.
- **Then, all eleven:** the three new sessions labelled `--eval-test` against xmas02fi8 (the eight
  labels unchanged); refs over all eleven, GPU predictions (fi8, fi6, fi5) and ONNX fi8 in
  `data/train/eval/xmas02fi8-r10x`; ONE pack `--round 10 --eval-test --seed 78` over all eleven
  (the seed-77 pack and key are set aside, never shown to anyone); two NEW blind labellers
  (t6/answers-eval-r10x-L1/L2.json); the score ONCE by
  `docs/records/scorers/xmas02_items_r10x_score.sh` (round 10's wrapper with these inputs only).
  A count still short then stays NO VERDICT and is reported so.
- **Code (cbdfa616, ruff 9c10d035):** `fi_labels.r10_seed` -- a round-10 pack that holds any of
  ifH37-ifH40 takes seed 78, else 77 (from the label files' names, then checked against their
  sessions); the wrapper above. Both committed before any extension label.
- The bars are section 8a's, unchanged.

### Amendment 39 (2026-11-23 06:24 ICT from `date`, BEFORE any blind answer and BEFORE any score): round 10's evaluation inputs with the extension; every minimum met

- **Her build before ifH37 (Amendment 38):** the fists build undone and the Knife-swap build of
  ifH31-ifH36 put back; her status window read against the old one (HIT 205, FLEE 246 + 1, Aspd
  176; weight 927 / 2,430); immunity OFF read back in the Chat tab ("Returned to normal state.")
  at 03:10 (`r10/immune_off_ext.ok` = 1).
- **The extension pilots (`r10x_pilots.sh`, 03:10-04:44):** ifH37 (03:10:55-03:41:08), ifH38
  (03:41:10-04:13:53), ifH39 (04:13:54-04:44:14); each `chain.sh` rc 0, 25.3-25.4 min of play,
  shipped, the economy recorded; round 9's check after each: 1,607 / 1,720 / 1,617 frames, 0 PAUSED.
  The popup reader's round-4 watcher ran beside each (its set w1080b; not read or scored here).
- **The eval chain (`eval_chain_r10x.sh`, 04:44-06:22):** it waited for the pilots' own last line;
  the frozen sha256 checked (74092985..., the archive matches); the three new sessions labelled
  `--eval-test` against xmas02fi8, all rc 0 (04:45-04:47); the eight earlier label files are
  untouched (their times 01:49-01:56); refs over all eleven: **9,791 frames**; GPU predictions fi8
  05:05, fi6 05:24, fi5 05:43; ONNX fi8 06:15; all rc 0, in `data/train/eval/xmas02fi8-r10x`.
- **The pack (seed 78, `--round 10 --eval-test` over all eleven; built 06:22:08 at 61a4f913):**
  **113 crops**: N 35, F 52, M 6 (**93 ITEM crops**) and E 20 (10 plain, 10 hard). The natural
  slot drew all 70 and the staging slot 23 of its 50 (the summary's `short`: no_aura 27). The
  answer key `key-eval-seed78/answer_key.json` sha256 `b4852e329d8f72f1...`. The seed-77 pack and
  key stay set aside, never shown.
- **The held-out's size, counted from the LABELS only** (no prediction read; `r10/size_r10x.py`,
  size_r10.py with the seed-78 pack summary; fi_eval's own selection rules):

  | count | value | minimum | |
  |---|---|---|---|
  | I2: natural drop episodes | **28** (ifH31-ifH39: 4, 0, 2, 3, 5, 4, 3, 2, 5; the stagings none) | 20 | met |
  | I1h: item crops in the pack | 93 | 40 evaluated | met (both labellers' good boxes decide) |
  | I3: item-free kept frames (natural) | 8,333 | 200 / 500 | met |
  | I4: drop-less kills judged | 203 (4 more with no frame) | 40 | met |

  I2's side counts: 101 drops of our kills, 19 behind her (4 of them with a kept label).
- **So the held-out is the eleven:** ifsH9, ifsH10, ifH31 .. ifH39. ifH40 stays unused.
- **For I5:** the model is round 8's, unchanged (xmas02fi8, still registered for the detect
  server; its ONNX the same file in the detector's model folder).
- **Two NEW blind labellers, L1 and L2:** fresh agents that open only the pack's folder
  (instructions, reference, crops) and write `t6/answers-eval-r10x-L1.json` / `-L2.json`. They
  started at about 06:22 and 06:23, before this amendment; no answer has been read.
- **The score:** `docs/records/scorers/xmas02_items_r10x_score.sh`, committed in cbdfa616 before
  any extension label, is copied to the scratch `score_r10x.sh` (`cmp` identical). It runs ONCE,
  after both answer files hold 113 entries: the I5 latency sample, both-good, THE BARS
  (`fi_eval --strata r10 --item-floor 0.4 --ring-red 30 --edge-margin 12 --edge-top 32`), then the
  report-only lines (fi8 without the edge, fi6 + the rule at 0.50, fi5 with no rule). The bars are
  section 8a's, unchanged.

### Amendment 40 (2026-11-23 06:54 ICT from `date`): ROUND 10 FAILS on I3-any (scored once, 06:47:49); the false boxes read

- **The one score** (`score_r10x.sh` = `xmas02_items_r10x_score.sh`, committed in cbdfa616 before
  any extension label; ran 06:25-06:48 after both answer files held 113; `score-r10.json` sha256
  c30364f658848622...; no live Run at the start, one beside the GPU-server step). xmas02fi8 + the
  fi7 rule at floor 0.40 (ring 30 px, pad 6) + the view edge (12 / 32), GPU predictions. The ONNX
  ones give the same verdict on every line:

  | line | got | bar | |
  |---|---|---|---|
  | I1h recall (the stratum decides) | 91 / 93 = 97.8 % | >= 90 % | PASS |
  | I1 precision | 1,557 / 1,630 = 95.5 % (73 false, 64 ambiguous) | >= 95 % | PASS |
  | I2 first frame of our kills' drops | 25 / 28 = 89.3 % | >= 80 % | PASS |
  | I3 any box on an item-free frame | **52 / 8,333 = 0.62 %** | <= 0.5 % | **FAIL** |
  | I3 inside her 5 x 5 | 7 / 8,333 = 0.08 % | <= 0.2 % | PASS |
  | I4 a box at a kill with no drop | 1 / 203 = 0.5 % | <= 5 % | PASS |
  | I5 GPU server p95 | 23.52 ms (fi5 23.94; ratio 0.98) | <= 35 ms, <= 1.1 | PASS |
  | I5 CPU p95 ratio | 1.006 (177.6 vs 176.5 ms) | <= 1.1 | PASS |

  - The blind step: both labellers answered all 113 and agreed on every q1 and q2: yes to all 93
    item crops (all good), no to all 20 E crops. Both good: **93** (the evaluated crops).
  - The rule dropped 209 boxes by the floor and 35 by the ring (ONNX 148 and 35); **the view edge
    dropped 1** (GPU and ONNX), and I3-any is 52 with or without it.
  - I1h by session: ifH31 9 / 9, ifH33 2 / 3, ifH34 4 / 5, ifH35 13 / 13, ifH36 12 / 12, ifH37
    7 / 7, ifH38 6 / 6, ifH39 15 / 15, ifsH9 8 / 8, ifsH10 15 / 15 (natural 68 / 70, staging
    23 / 23). Misses: ifH33 947, ifH34 513 (I2 misses those two and ifH39 395).
  - The six first pilots alone would fail too: 32 / 5,492 = 0.58 %; the extension added 20 / 2,841.
- **Beside it (report only, the same held-out and evaluated crops; no I5 for these lines):**

  | | I1h | precision | I2 | I3-any | I3 5 x 5 | I4 |
  |---|---|---|---|---|---|---|
  | xmas02fi8 + the rule at 0.40, no edge (round 9's) | 91 / 93 | 95.5 % | 25 / 28 | 52 = 0.62 % | 7 | 1 / 203 |
  | xmas02fi6 + the rule at 0.50 | 90 / 93 | 96.8 % | 25 / 28 | 38 = 0.46 % | 2 | 1 / 203 |
  | xmas02fi5, no rule (deployed) | 87 / 93 | 92.4 % | 25 / 28 | 130 = 1.56 % | 69 | 3 / 203 |

- **Not deployed.** No 8c.
- **The 52 false-box frames** (read after the score; scratch `r10/diag/diag_i3_r10x.py`, which
  replays fi_eval.i3 after the rule and the edge, and `r10/diag/look/`): 26 distinct objects.

  | what the box sits on | frames | where |
  |---|---|---|
  | **the snowflakes painted on ONE wall picture** (a snowman and a "MERRY X-MAS" ribbon) | **24** | ifH36 703-713 (947, 59); ifH38 542-550, two snowflakes at (790, 185) and (772, 280); ifH39 1541-1544 (619, 59) |
  | parts of monsters or of her own body (a toy soldier's hat, red boots, a green glove-like piece at a black map edge) | 11 | 3 of them inside her 5 x 5 |
  | small pale or white shapes (light blobs, a white cone) | 6 | 3 inside her 5 x 5 |
  | the foot of a lamp post (a scenery figure under a red lantern) | 4 | ifH33 424, 427; ifH35 806, 808 |
  | damage digits ("8" of 68, "5" of 53, a yellow "1") | 3 | |
  | light effects (a cyan swirl, a sparkle) | 2 | 1 inside her 5 x 5 |
  | other scenery (a red disc on a wall, a crane's hub) | 2 | |

  - The snowflake picture is fully inside the view, 59-280 px from its top: the edge rule cannot
    reach it. Round 9's top-edge ornament (ifH26, Amendment 35) and round 7's floor snowflake (ifH6,
    Amendment 25) were the same kind of mark. Without these 24 frames I3-any would be 28 = 0.34 %.
  - Confidence: the snowflakes 0.41-0.76; across all 52, 0.41-0.84.
- **The floor's sensitivity (on the now-spent held-out; it scores nothing; scratch `r10/diag/sens-*`):**
  xmas02fi8 + the rule + the edge, GPU:

  | floor | I1h | precision | I2 | I3-any | I3 5 x 5 | I4 |
  |---|---|---|---|---|---|---|
  | **0.40 (scored)** | 91 / 93 | 95.5 % | 25 / 28 | 52 = 0.62 % | 7 | 1 |
  | 0.45 | 91 / 93 | 96.5 % | 25 / 28 | 45 = 0.54 % | 6 | 1 |
  | 0.50 | 91 / 93 | 96.8 % | 25 / 28 | 41 = 0.49 % | 5 | 1 |

  The floor trades against I1h on round 8's held-out (0.50 fails it there: 53 / 59) and against
  I3-any here and on round 9's. Each held-out sits on one edge; the floor is not the fix.
- **So the model has to learn the scenery as background.** Round 11 is pre-registered next, from
  this diagnosis and before any round-11 data.

### Amendment 41 (2026-11-23 07:34 ICT from `date`, BEFORE any round-11 data): ROUND 11 pre-registered -- xmas02fi9: xmas02fi8 retrained on its own false boxes of the spent held-outs; those sessions join TRAIN; round 10's rule unchanged; a NEW held-out

- **Why (Amendment 40):** xmas02fi8 + the rule has failed exactly one bar on each of three held-outs
  (round 8 I1h at floor 0.50; rounds 9 and 10 I3-any at 0.40). What is left are SCENERY marks the
  model takes for items: 24 of round 10's 52 frames are the snowflakes painted on one wall picture;
  also a lamp post's foot, damage digits, monster and body parts. The same kind recurs (round 7's
  floor snowflake, round 9's top-edge ornament). A rule cannot name them, and the floor only trades
  I3-any against I1h. Round 8's recipe (the model's own false boxes as hard negatives) took I3-any
  from 0.73 % to 0.28 %; the snowflake picture was never among its negatives (rounds 9-10's
  held-outs did not exist yet). Batt's decision stands ("improve it until it passes").
- **TRAIN** = round 8's TRAIN unchanged (Amendment 28: its 26 sessions + the linked round-5 cache,
  62 sessions, 7,282 frames) PLUS the **27 SPENT held-out sessions of rounds 8-10**: ifH11-ifH16,
  ifsH5, ifsH6; ifH21-ifH26, ifsH7, ifsH8; ifH31-ifH39, ifsH9, ifsH10.
  - Released by exact name in code (`fi_labels.R11_RELEASED`, in `IF_RELEASED`); the reserved names
    never recorded (ifH17-ifH20, ifH27-ifH30, ifH40) stay refused; an `-ABORTED` session is never
    any split. `--eval-test` still reads them, so the old scores stay reproducible.
  - Each is labelled `fi_labels.py label --spec 1080 --split train` at the frozen params
    (ad268afd...) and judged by G2 as round 8 did (a session failing G2 is out, and counted).
- **Negatives:**
  - the session negatives as round 8: 150 from each pilot's own item-free kept frames, 1 per 3 item
    frames for the stagings;
  - **every hard negative:** an item-free kept frame on which xmas02fi8 boxed an item at
    conf >= 0.25 (fi_eval.CONF) with no rule, mined by `fi_hard_negs.py mine` from the GPU
    predictions ALREADY MADE on these 27 sessions (`archive/train/eval/xmas02fi8-r8`, `-r9`,
    `data/train/eval/xmas02fi8-r10x`) with their eval label files. **Counted at 07:3x: 294
    frames** over 25 sessions (1-25 each; the snowflake picture's ifH36 21, ifH38 14, ifH39 15;
    20,084 item-free frames read). The TRAIN labels decide the final set: a listed frame they do
    not keep item-free is counted, not written. Each is written once (no oversampling);
  - no new mining on round 8's own 26 TRAIN sessions (xmas02fi8 learnt from them).
- **The model, xmas02fi9:** trained from xmas02fi8's last.pt (74092985...) with round 8's trainer
  settings (`--batch 2 --hsv-s 0.2 --close-mosaic 3 --scale 0.1`, imgsz 1280 and seed 20261004 by
  default) and **`--workers 1`** (Batt 11-22); epochs by section 7's formula on the combined TRAIN
  (`min(12, max(3, 5400 // (0.64 N + 100)))`: 3 at the expected ~10,000 frames); VAL ifF, a monitor
  only; up to 3 resumes; then the freeze as round 8's (sha256, the 736 x 1280 ONNX, the archive) and
  its registration for the detect server (a commit before the score).
- **The rule at inference:** round 10's, unchanged: floor 0.40, ring 30 px, pad 6, view edge
  12 / 32 (`--item-floor 0.4 --ring-red 30 --edge-margin 12 --edge-top 32`).
- **The GPU:** the dev worker runs one job, so the training runs after the held-out pilots (they
  need the detect server), never beside them. It does not stop for a live Run; the live detect
  server's minute p95 is logged and reported.
- **The new held-out:**
  - **stagings ifsH11 and ifsH12**, immune; their seeds and cells come in a later amendment,
    before any recording, sharing no cell with any earlier staging on this map;
  - then immunity OFF, read back on a frame;
  - **natural pilots ifH41, ifH42, ...**, NOT immune, 25 min each, xmas02v1080, stage2_ab's setup,
    **her Knife-swap build** (rounds 8-10's; the fists trial's build is undone first and read
    against the old window: HIT 205, FLEE 246 + 1, Aspd 176). As many as I2's 20 episodes need: 6
    to start, then Amendment 16's one extension (3 more) if I2 is short;
  - **one procedure change, for her safety only:** the pre-run checks wait in town (fists-1080.md
    Amendment 4: `@warp prontera 156 191` before the checks and right after the zoom check), so she
    no longer stands ~1.5 min on xmas_dun02, not immune, before each run. The run's own setup warps
    her to its start cell as before, so the play is unchanged;
  - every name refused for TRAIN in code before its first recording (`R11_HELD_OUT`, ifH41-ifH50,
    ifsH11, ifsH12: this commit's sibling);
  - labelled `--eval-test` against the frozen xmas02fi9; ONE pack `--round 11 --eval-test` at seed
    **79**; two NEW blind labellers.
- **The bars:** section 8a's, unchanged, scored ONCE by a wrapper committed before any round-11
  label (`--strata r11` with round 10's rule; I5 for xmas02fi9 against xmas02fi5). Reported beside
  them (no bar), on the same held-out: xmas02fi8 + round 10's rule, xmas02fi6 + the rule at 0.50,
  xmas02fi5 with no rule.
- **If it passes:** 8c at 1080 (A = xmas02fi5, B = xmas02fi9 + round 10's rule through the player's
  settings, Amendment 37; 3 valid runs a side); deployed at 1080 only, on Batt's word.
- **If it fails:** a round 12, pre-registered from its diagnosis.
- **The order (estimates):** the fists trial ends ~08:55 -> her Knife-swap build back -> the
  stagings -> ifH41-ifH46 (~3.3 h), with the TRAIN labelling, the hard-negative list and the cache
  on the CPU beside them (held-out recordings are not timed arms) -> the training (~4-6 h with one
  loader worker) -> the freeze -> the eval chain, the labellers and the one score.
- **Code first (with tests, before any round-11 label):** fi_labels' round-11 names (refused for
  TRAIN), `R11_RELEASED`, seed 79 and `pack --round 11`; fi_eval `--strata r11`.

### Amendment 42 (2026-11-23 07:41 ICT from `date`, BEFORE any round-11 recording): the new held-out's stagings and order

- **The stagings** (`--views near --n 4`, as rounds 7-10):
  - **ifsH11: seed 2613859**, spots (102,82), (82,216), (212,69), (169,205);
  - **ifsH12: seed 2613886**, spots (236,115), (126,214), (148,169), (25,159).
  - Their cells share NONE with the 27 earlier stagings on this map (2,364 distinct cells:
    `cells/earlier-r11.json` = round 10's file + ifsH9 + ifsH10, whose spots were recomputed and
    match Amendment 36), nor with each other. Seeds 2613600-2613899 gave exactly these two clean
    4-spot plans (298 shared a cell; none was short).
- **The order**, after the fists trial ends (fists-1080.md) and her Knife-swap build is back and
  read against the old window:
  1. clear-bag (etc, use), judged by the agent on its weight, and the DB's save holding none of the
     set (`stage_items held`, as round 10's `r10_stage.sh`);
  2. ifsH11, then ifsH12, IMMUNE (`stage_rec.sh`; immunity ON judged on a frame first), each under
     the popup reader's round-4 watcher (its set w1080b counts only `record_session` pilots, so the
     stagings are outside it);
  3. immunity OFF, its reply read on a frame;
  4. the pilots ifH41 .. ifH46, NOT immune, 25 min each (`pilot_rec2.sh`: round 10's
     `pilot_rec.sh` with Amendment 41's town step), round 9's check after each (>= 1,400 frames, no
     PAUSED line), each under the round-4 watcher (w1080b sessions).
- The TRAIN labelling, the hard-negative list and the cache run on the CPU beside the recordings;
  the training starts after the pilots' own last line (the dev worker runs one job).
