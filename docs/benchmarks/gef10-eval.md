---
doc_type: design
hypothesis: "A detector trained on v2orc + pay_fild07's cached data plus gef_fild10's TRAIN labels (gef10-o3h-e, frozen 2026-10-25 22:14) finds gef_fild10's species on held-out TEST data (recall and precision >= 0.80 for each species with >= 50 evaluated crops) without losing prt_fild08 (v1's gold set and held-out set no worse than v1)."
status: "ROUND 2 SCORED 2026-10-29 17:04 ICT (RESULT R2): the gef10 round-2 model does NOT PASS. G1 FAILS on precision (monster P 0.867 < 0.882); Q1 PASSES for Orc Lady, Orc Warrior and Poporing (recall 0.983, precision 1.000 each); G2 PASSES; CPU p95 499 ms <= v1 x 1.10. Round 1: NOT RUN (T1 failed 2026-10-26 03:16). Pre-registered 2026-10-26; amendments R2 (10-26 11:07), R2-2 (10-29 12:53), R2-3 (10-29 13:22)."
role: null
verdict_date: 2026-10-29
verdict_ticket: null
supersedes: null
related: [../planning/gef10-detector.md, payf07-eval.md, v2orc-vs-v1.md, ../planning/rogue-gef10.md]
next_action: "Batt decides what follows the G1 failure (RESULT R2): the live detector stays v1. Nothing here is re-scored: a new model or a reading of G1 needs its own pre-registration."
---

# gef10: gef_fild10's species, without forgetting prt_fild08 (pre-registered 2026-10-26)

Batt (2026-10-25 ~12:3x ICT): "you may use the GPU to train on the monsters and items of this map".
The label rule, the split, T2 and the class list are in
[gef10-detector.md](../planning/gef10-detector.md) (13n-13q). This document fixes, BEFORE the cache
and the run exist, how the model will be judged. It copies payf07-eval.md's method; only the map,
the classes and the TEST data change.

## The model (fixed now)

| | v1 (`v1png-20261008`, the live CPU detector) | the gef10 model (to train) |
|---|---|---|
| classes | player, monster, npc | `config/detector/classes-v2orc-payf07-gef10.json` (sha256 `66de5684…a7ff747c2`): payf07's ids 0-20 unchanged + Orc Lady 21 (1273), Orc Warrior 22 (1023), Orc Baby 23 (1686), Orc Lord 24 (1190), Orc Archer 25 (1189). No item class (D10) |
| data | v1's sessions, v1 labels | a NEW cache: `v2orc-payf07-20261024` LINKED unchanged + gef_fild10's TRAIN under `gef10-o3h-e` (params sha256 `00ef6383…b0aac1`): the watch's cells 0-10, the pilot, pilot2, a2, a4, w2, and any later session that passes 3c before the build |
| model, seed, imgsz, batch / workers | YOLO11n, 20261004, 1280, 2 / 1 | the same |
| starting weights, epochs, `hsv_s`, `close_mosaic`, `scale` | COCO YOLO11n, 30, 0.7, 10, 0.5 | **as recorded in gef10-detector.md BEFORE the launch** (section 10 proposes: payf07's epoch-1 `last.pt`, 10 epochs, `hsv_s` 0.2, `close_mosaic` 3, `scale` 0.1). A run launched with other values is not this evaluation's model |
| VAL | v1's val sessions | v1's val sessions only (val monitors training and decides nothing) |

- **The scored checkpoint:** `last.pt` after the LAST COMPLETED epoch when the training ends (the
  planned final one, or an earlier one if the run is stopped; the report states which and why).
  Never `best.pt`, never `mid.pt`. TEST is not read before the training ends.
- **The detector settings for every score:** `poring_vision.predict_dir` (the GPU worker, R1-R3,
  the 25 % VRAM cap), imgsz 1280, **conf 0.25**, ultralytics' default NMS.
- **A match** is the POSITION metric (`label_iou.match_position`): the classes agree and the
  detection's box centre lies inside the label box; one-to-one per frame, nearest centre first.

## The evaluation data: gef_fild10's TEST (never read before T1)

- **TEST = the Orc Lord watch's cells 11-14** (`20261025T195325-rdp-ow1:spots=11-14`) **+ a7
  (`20261026T010738-rdp-rogue-a7`) + a8** (gef10-detector.md Amendment D). They are in no cache and
  were never read for a parameter.
- **T1** (gef10-detector.md 5) reads them once, as a check of the LABELS. It decides nothing here.
- **The TEST labels for scoring are made once, AFTER the training ends:** `map_labels.py labels
  --map gef_fild10` with the frozen `params.json`. That is the rule the TRAIN labels were cached
  under, including the ENGAGED variant E2.

## The evaluation pack (after the training ends; seed 33)

- **The pool:** per species, the TEST labels KEPT under `gef10-o3h-e`, from any candidate frame.
  The two strata: N (not engaged) and E (engaged).
- **The draw:** per species and stratum, the pool sorted by (session, frame, gid), shuffled with
  `map_labels.t2_order` at seed 33, **the first 60** (fewer: all of them).
- **The crops, the reference sheet and the questions:** T2's format.
- **The instructions:** `docs/planning/gef10-blind-instructions.txt`, byte-identical (sha256
  `247b7919…4b54b0`).
- **Two NEW blind labeller agents** each get ONLY the pack, its instructions and an answers path.
  The key stays apart.
- **A crop is EVALUATED** when BOTH labellers answer q1 = yes, q2 = good and q3 = the label's
  species.

## The scores (fixed now)

**Q1, gef_fild10 per species s (stratum N)**, on the frames of the evaluated crops (position metric):
- **recall** = the evaluated s crops whose box contains the centre of a class-s detection / the
  evaluated s crops;
- **precision** = those matches / the class-s detections whose centre falls inside ANY evaluated
  crop's box of the frame. Detections elsewhere are not scored: their truth is not verified.
- **The bar, for each gef_fild10 species with >= 50 evaluated crops: recall >= 0.80 AND precision
  >= 0.80.** Fewer: reported, no bar.

**E1, the ENGAGED stratum:** the same two numbers on the evaluated E crops, per species. Its own
bar applies at >= 50 evaluated crops; fewer: reported.

**G1, v1's gold set** (v2orc-vs-v1.md G1, unchanged): **P >= 0.882 AND R >= 0.810**, every
monster-species class collapsed to `monster`.

**G2, v1's prt_fild08 held-out set** (v2orc-vs-v1.md G2, unchanged): **monster recall and
precision each >= v1's on the same frames - 0.02**. v1 is re-scored first with the same command.

**Reported, deciding nothing:**
- pay_fild07's TEST (payf07-eval.md's Q1 method, seed 23), if its labels and pack exist by then:
  the old map's species;
- orcsdun01 (v2orc-vs-v1.md's P1, seed 3);
- per species, IoU >= 0.5 precision and recall;
- whole-frame precision and mAP50 on TEST frames labelled whole;
- **the look-alike confusion** for each evaluated crop:
  - Orc Lord vs Orc Warrior vs Orc Archer (the `scale` 0.1 flag's reason);
  - Poporing vs Poring;
  - Orc Baby vs the other orcs;
- Q1 split by TEST part (watch cells 11-14 / a7 / a8) and by under-a-model / clear;
- the latency per frame at imgsz 1280: GPU in the worker and CPU ONNX (nice 10), p50 / p95 over
  the same 200 frames, v1 beside.

**The verdict:**
- **The gef10 model PASSES if Q1 holds for every species with a bar, and G1 and G2 hold.**
- Passing does NOT switch the live detector: that is Batt's decision.
- **For the bot to hunt gef_fild10 by sight (Batt decides; this states the numbers only):**
  - Q1 passes for Orc Lady and Orc Warrior with their bars EXISTING;
  - the Orc Lord's bar exists and passes (the flee rule could then use the class instead of, or
    beside, the aura rule; a separate proof);
  - G1 and G2 hold, and the CPU p95 latency is <= v1's p95 x 1.10.

## Known limits (stated now)

- **TEST's hunting part (a7, a8) is the same map as TRAIN:** Q1 measures held-out monsters and
  times, not held-out places.
- **The Orc Lord and the Archers come from the watch** (spawned, the Rogue immune). In TEST they
  are watch cells 11-14 only. The scored runs have none, by the schedule (rogue-gef10.md Amendment
  E). Their bars may not exist.
- **Canopy:** 67.6 % of FIT fates lay under a model box (13f). The o3h rule keeps only labels whose
  sprite fits, so Q1 measures the visible monsters.
- **No item class** this round (D10).

## The run (plan)

1. **The cache:** a guarded `cache:` step (a dry run first, the nested link checked), outside
   09:30-10:15 / 14:00-14:45 on weekdays.
2. **The training:** the settings recorded in gef10-detector.md BEFORE the launch. `train-day.sh`
   with WORKER=1, MID_CKPT=1, R1-R3, the IO guard, the 25 % VRAM cap.
3. **After the training ends:**
   - the TEST labels, then the seed-33 pack and its two labellers;
   - G1 and G2, with v1 re-scored first;
   - the latency.
   - Each scorer is committed with a positive case before it scores. Scored ONCE. The results go
     below this line, with nothing above it edited.

## RESULT (2026-10-26 03:19 ICT): not run

T1 failed at 03:16 (C1 5 / 61 = 8.2 % on TEST, bar 5 %; [gef10-detector.md 13r](../planning/gef10-detector.md)).
By that plan's section 9, nothing of gef_fild10 trains this round. No cache was built and no model
exists, so nothing above is scored. TEST (watch cells 11-14, a7, a8) has now been read by T1 and a
look at its bad labels. A later round needs a NEW TEST and its own pre-registration.

## AMENDMENT R2 (2026-10-26 11:07 ICT from `date`, BEFORE TEST2 is read and BEFORE any round-2 model exists): round 2 (gef10-detector.md 13s)

- **TEST becomes TEST2:** a9, a10, a11 and the immune watch w3, recorded after 13s's commit.
  Round 1's TEST is spent and is not used.
- **The evaluation pack's seed is 35** (33 is this document's round-1 seed, never drawn). The
  draw, the strata, the instructions (sha256 `247b7919...`), the two NEW blind labellers, Q1 / E1
  / G1 / G2 and their bars, the position metric, conf 0.25 and the scored checkpoint are
  unchanged.
- `labels` refuses TEST2 by name. The step that makes TEST2's evaluation labels (after
  training) passes TEST2 explicitly, and its command is recorded in this document then.
- **Reported, deciding nothing:** the new model on Batt's demo (`detector_vs_packets.py`), beside
  v1's numbers (gef10-round2.md: recall 8.0 %, precision 18.7 %).

## AMENDMENT R2-2 (2026-10-29 12:53 ICT from `date`, BEFORE TEST2's evaluation labels exist and BEFORE the training ends): the details the plan left open, and the tools it needs

An inventory of the run (read-only, 2026-10-29 ~12:5x) found that none of the steps above runs
end-to-end with today's code. The tools are built and tested before any of them reads TEST2. This
amendment fixes, before that, every detail the plan did not state:

- **TEST2's evaluation labels:** `map_labels.py labels --eval-test2`, a new flag:
  - gef_fild10 only, and only parts whose name ends in a TEST2 suffix (a9, a10, a11, w3);
  - round 1's TEST and round 3's TEST3 stay refused;
  - the FROZEN round-2 `params.json` (gef10-detector.md 13n / 13s);
  - `--classes config/detector/classes-v2orc-payf07.json`, the TRAIN labels' file;
  - one part per run. The output records `"eval_test2": true`.
- **The pool is the labels KEPT under gef10-o3h-e, which includes the weak_fit floor:**
  `--min-fit 0.636` (T_h, the floor on EVERY label, as the cache and T2 applied it).
- **The draw:** `map_labels.py pack --eval-test2 --per-species 60 --seed 35`:
  - every species with at least one kept TEST2 label is in the pool (no conditional tier: "fewer:
    all of them");
  - per species and stratum (N / E), the first 60 by `t2_order`;
  - T2's crop / reference-sheet format and the instructions (sha256 `247b7919...`), unchanged.
- **The detections:** `poring_vision.predict_dir` with `last.pt` after the last completed epoch,
  imgsz 1280, conf 0.25, ultralytics' NMS:
  - on exactly the frames that carry a pack crop, read IN PLACE from the NAS shards (a new
    `--refs` input; no extraction to /dev/shm or the disk, rule 7);
  - the guarded step `execdev:vision` with `--threshold 30 --sustain 30` (the training's IO rule);
  - R1-R3 and the 25 % VRAM cap; fit-first's VTON is a co-tenant and never touched.
- **The scorer:** `scripts/eval_q1.py` (new, committed with a positive case before it scores):
  - EVALUATED = both labellers answer q1 yes, q2 good and q3 = the label's species;
  - Q1 (stratum N) and E1 (stratum E) per species, with the position metric
    (`label_iou.match_position`);
  - precision counts only class-s detections whose centre falls inside an evaluated crop's box of
    that frame;
  - the splits and the look-alike confusion as listed under "Reported".
- **G1:** `gold_eval.py score` on the gold set from the NAS archive
  (`archive/train/eval/gold/20261004T103815-console-s2-indoor-v2/`), v1's
  `pred-v1png-20261008.json` and the new model in ONE command. Every species class is collapsed
  to `monster` (a new `--collapse-species`; player, npc and warp are kept).
- **G2:** a new `gold_eval.py score-cache` on the `v1png-20261008` cache's held-out session
  054429:
  - v1's labels, read from the shards in place;
  - v1's `last.pt` and the new `last.pt` as two predictions in ONE command, so v1 is re-scored
    first with the same command;
  - species collapsed as G1.
- **The latency:**
  - the 200 frames are the first 200, by a seed-35 shuffle, of the TEST2 frames that carry a pack
    crop;
  - GPU: `predict_dir --timing` in the worker, per-frame ms, p50 / p95;
  - CPU: the new model exported to ONNX by docs/operations/detector-cpu.md's recipe, run through
    `UnitDetector` at nice 10 beside v1's `v1png-last-736x1280.onnx` on the same 200 frames,
    p50 / p95. `unit_detector.py`'s 3-name mapping is generalised first, because the new model
    has 26 classes.
- **Reported, deciding nothing:**
  - Batt's demo: `predict_dir` on its 5 Hz JPEGs (`human-demos/20261026T095021-...`), turned
    into `detector_vs_packets.py`'s box rows (species collapsed to `monster`), beside v1's logged
    numbers. The recorder's frame times, not live grab times.
  - pay_fild07's TEST (seed 23) and orcsdun01's P1 (seed 3): NOT run. No labels or packs exist
    for them, and building them is out of this evaluation's scope.
- **Disclosure:** TEST2's frames were opened ONCE before this, by the parent, for the miss-cue
  study (rogue-gef10.md Amendment S, the "Miss" cue's held-back set, 10-26 ~14:4x). That read the client's
  "Miss" sprite, not monster labels. No detector parameter, label rule or setting of this run came
  from it.
- Unchanged: the model, Q1 / E1 / G1 / G2's bars, the strata, the two NEW blind labellers, the
  verdict rule, and "Passing does NOT switch the live detector".

## AMENDMENT R2-3 (2026-10-29 13:22 ICT from `date`, BEFORE TEST2's evaluation labels exist): how the built scorer reads the rules

The tools of R2-2 are built and tested on non-TEST data:
- `map_labels.py labels / pack --eval-test2` (ff86b81);
- `predict_dir --refs / --glob / --timing` (c9ae15c);
- `eval_q1.py` (d73ae62);
- `gold_eval.py --collapse-species / --gold-dir / score-cache / refs` (1ff3f10);
- `unit_detector` names (c038e40);
- `detector_vs_packets.py --boxes / from-predict` (715ab66).

Their positive cases, real data, none of it TEST:
- G1 reproduced EXACTLY from the NAS gold dir: v1 83 / 9 / 17, P 0.902, R 0.830.
- G2's 054429 truth: 1,077 frames, 4,186 boxes; its own labels as detections give 1.0 / 1.0.
- Round 2's T2 pack (TRAIN labels):
  - a perfect detector gives 1.0 / 1.0 for every species;
  - a shifted detector gives recall 0;
  - a wrong-class detector gives recall 0.

Where the written rule needed a reading, it is fixed here:
1. **Precision when a frame holds crops of both strata:**
   - ONE position match per frame over all of its evaluated crops;
   - a matched detection counts for its own crop's stratum only;
   - an unmatched class-s detection counts against stratum X when its centre lies in an evaluated
     X box;
   - `strata_overlap` (frames with both) is reported.
   With one stratum per frame this is the rule as written.
2. **The verdict:** as written, Q1 (stratum N) for every species with a bar, plus G1 and G2.
   E1's bar is reported on its own and does not enter the verdict.
3. **No bar, no pass:** if no gef_fild10 species reaches 50 evaluated crops in Q1, then:
   - Q1 has NO verdict (not a vacuous pass);
   - the model's verdict is "not established";
   - the numbers are reported.
4. **Class names** come from the training cache's manifest: the KB's aegis names in lower case,
   e.g. `orc_lady`, `ork_warrior`, `orc_baby`, `orc_lord`, `orc_archer`, `poporing`,
   `green_plant`. Class list sha256 `66de5684...a7ff747c2`.
5. **"Q1 split by TEST part"** is by TEST2 session (a9, a10, a11, w3) and by
   under-a-model / clear / unknown. Round 1's watch cells 11-14 / a7 / a8 are spent.
6. **The look-alike confusion:**
   - a class-blind one-to-one position match per frame;
   - for each evaluated crop, the class of the detection matched to it, if any;
   - a player, npc or warp detection can appear there.

## RESULT R2 (scored 2026-10-29 17:04 ICT from `date`; the round-2 model, AMENDMENTS R2 / R2-2 / R2-3)

**VERDICT: the gef10 round-2 model does NOT PASS. G1 FAILS on precision: monster P 0.867 < 0.882.**
Q1 passes for every species with a bar (Orc Lady, Orc Warrior, Poporing), and G2 passes. Under
"the verdict" above, all three must hold. Passing would not have switched the live detector
either: that stays Batt's decision.

### The scored model
- `last.pt` after epoch 10 of 10, the last completed epoch, as planned (gef10-detector.md 13z-5):
  `data/train/gef10-20261026/weights/last.pt`, sha256 `ebfc7a9a...6cc0b6`.
- The training ended 2026-10-29 16:26. Nothing read TEST2 before that, except as disclosed in R2-2.
- Detector settings: `predict_dir` in the vision worker, imgsz 1280, conf 0.25, ultralytics' NMS.
  Every step was guarded (`execdev:vision`, `--threshold 30 --sustain 30`, R1-R3) and none tripped.
  The worst capture stall was 13.7 %.

### Q1 (stratum N; the verdict) and E1 (stratum E; reported)
- **TEST2's evaluation labels:** the four parts were labelled under the FROZEN params
  (00ef6383...) between 16:30:51 and 16:49:00. Every file records `eval_test2: true`.
- **The pack (seed 35, `--min-fit 0.636`):** 245 crops in 13 grids.
  - N: Orc Lady 60 (from a pool of 245), Orc Warrior 60 (pool 60), Poporing 60 (pool 138), Orc
    Baby 0.
  - E: Orc Lady 60 (pool 219), Orc Warrior 1, Poporing 2, Orc Baby 2.
  - The weak_fit floor removed 264 / 49 / 27 / 7 labels (Lady / Warrior / Poporing / Baby).
  - TEST2 has no Orc Lord and no Orc Archer label (by its schedule).
- **Two NEW blind labellers:** A ran 16:52-16:56 and B 16:57-17:02. Each saw only the pack.
  - B's `mkdir -p` listing showed that A.json existed. B reports never opening it.
- **240 of 245 crops were EVALUATED.** Every species call of both labellers matched the label.
  The 5 not evaluated:
  - 135 and 162 (Orc Baby, E, a9, under a model): leaves only, a "Miss" above. A answered no, B
    unsure. Both of TEST2's Orc Baby crops are therefore canopy-hidden.
  - 093 (Orc Lady, N, w3): loose for both labellers.
  - 062 and 153 (Orc Lady, E): "off" for B (the weapon or arm reaches past the box).
- **Q1 (N, 179 evaluated; the bar is >= 50 evaluated, recall AND precision >= 0.80):**

  | species | evaluated | matched | recall | precision | bar | result |
  |---|---|---|---|---|---|---|
  | Orc Lady (orc_lady) | 59 | 58 | 0.983 | 1.000 | yes | PASS |
  | Orc Warrior (ork_warrior) | 60 | 59 | 0.983 | 1.000 | yes | PASS |
  | Poporing (poporing) | 60 | 59 | 0.983 | 1.000 | yes | PASS |

  - **By TEST2 part,** recall per species: a9 1.000 / 0.875 / 0.963; a10 0.963 / 1.000 / 1.000;
    a11 1.000 / 1.000 / -; w3 1.000 / 1.000 / 1.000 (Lady / Warrior / Poporing). Every precision
    is 1.000.
  - **Under a model vs clear:** under 0.960 / 0.978 / 1.000 (25 / 46 / 25 crops); clear
    1.000 / 1.000 / 0.971 (34 / 14 / 35).
  - **Look-alikes (class-blind match):** no confusion. Each species' one miss is "none"; no other
    orc, Poring or Orc Baby class was matched to any crop.
- **E1 (E, 61 evaluated; reported, not in the verdict, R2-3 item 2):**
  - Orc Lady: 58 evaluated, 58 matched, recall 1.000, precision 0.906 (6 unmatched orc_lady
    detections inside the boxes), bar PASS. Under a model: 2 crops, precision 0.4. Clear: 56
    crops, 0.949.
  - Orc Warrior: 1 evaluated, matched as orc_lady (no bar).
  - Poporing: 2 evaluated, 1 matched (no bar).
  - `strata_overlap`: 0 frames.

### G1 (v1's gold set, species collapsed, the position metric): FAIL

| model | monster TP / FP / FN | P | R | bar P >= 0.882 AND R >= 0.810 |
|---|---|---|---|---|
| v1 (`pred-v1png-20261008.json`, re-scored in the same command) | 83 / 9 / 17 | 0.902 | 0.830 | (the reference) |
| gef10 round 2 | 85 / 13 / 15 | **0.867** | 0.850 | **FAIL (P)** |

- **NPC (reported):** v1 52 / 1 / 2; new 52 / 5 / 2 (P 0.981 vs 0.912).
- **The 13 monster FPs (reported, deciding nothing)** are all class `poring`, conf 0.32-0.93.
  - 11 are in two frames, 280 and 290. In those frames BOTH models also miss 5-6 hand boxes each
    (v1's FN 6 / 6, the new model's 6 / 5).
  - 8 of the 13 lie within 20 px of a v1 FP in the same frame.
  - Outside frames 280 and 290 the new model has 2 FPs (conf 0.32 and 0.33).
  - Two fewer FPs would have passed (85 / 96 = 0.885). The bar is applied as written.

### G2 (v1's prt_fild08 held-out session 054429, 1,077 frames, 4,186 truth boxes): PASS

| model | monster TP / FP / FN | P | R | bar (each >= v1 - 0.02) |
|---|---|---|---|---|
| v1 (re-scored first, same command) | 1833 / 719 / 735 | 0.718 | 0.714 | P >= 0.698, R >= 0.694 |
| gef10 round 2 | 1817 / 742 / 751 | 0.710 | 0.708 | **PASS** |

- NPC: v1 P 0.898 / R 0.900; new 0.894 / 0.900.
- The new model also made 16 `player` detections; the truth has no player box.

### Latency at imgsz 1280 (the same 200 frames: seed 35 over the pack's 238 frames)

| path | v1 p50 / p95 ms | gef10 round 2 p50 / p95 ms |
|---|---|---|
| GPU (`predict_dir --timing`, the worker; wall time per predict call) | 23.0 / 34.7 | 25.1 / 40.8 |
| CPU (ONNX 736 x 1280 through UnitDetector, 8 threads, nice 10, interleaved per frame) | 248.3 / 616.9 | 261.3 / 499.3 |

- GPU max: 4.69 s / 4.88 s. In both runs that is the FIRST frame (CUDA warm-up); the next
  frames peak at 52-55 ms.
- CPU p95 499.3 <= v1's 616.9 x 1.10 = 678.6.
- The CPU run read the frames in place from the NAS and took 145.6 s. On these gef_fild10 frames
  v1 made 95 boxes and the new model 560 (at UnitDetector's own threshold).
- The ONNX export (detector-cpu.md's recipe): `/dev/shm/poring-lab-detector/model/
  gef10r2-last-736x1280.onnx` + `.names.json` (the 26 names in id order, sha256 `d263f379...`;
  ids 21-25 = orc_lady, ork_warrior, orc_baby, orc_lord, orc_archer, as the class file).

### Batt's demo (reported only, deciding nothing)
- `predict_dir` on its 4,666 5 Hz JPEGs, scored by `detector_vs_packets.py score --boxes` (species
  collapsed; the recorder's frame times; 4,237 captures scored).
- **The new model:** recall 0.397 (1,727 / 4,355 truth boxes in view; one-to-one 0.378),
  precision 0.577 (1,827 / 3,169).
- **v1, logged live** (gef10-round2.md): recall 8.0 %, precision 18.7 %.
- By our motion:
  - while our character moved in the 500 ms before: recall 0.050 (n 999);
  - still: 0.500 (n 3,356).
- By state: walk 0.241, idle 0.416, attacking 0.417, hurt 0.528.
- By distance: 0-5 cells 0.390, 6-10 0.300, 11-15 0.496.
- First sight: 67 of 84 unit episodes detected, median delay 2.4 s (p90 4.4 s).
- Precision by FP type: 1,126 FPs elsewhere, 130 within 16 px of a unit, 72 on a dying unit,
  14 on our own character.
- GPU wall time per frame: p50 72.6 ms, p95 99.2 ms (n 4,480 in the window). The max of 182 s is
  one call that spanned an R3 pause of the worker.

### For the bot to hunt gef_fild10 by sight (the numbers only; Batt decides)
- Q1 passes for Orc Lady and Orc Warrior with their bars: YES.
- The Orc Lord's bar exists and passes: NO. TEST2 has no Orc Lord label, so the bar does not
  exist.
- G1 and G2 hold: NO (G1 fails).
- CPU p95 <= v1's x 1.10: YES (499.3 <= 678.6).

### Not done, as R2-2 stated or as built
- pay_fild07's TEST and orcsdun01's P1: not run (R2-2).
- Per-species IoU >= 0.5 precision / recall and whole-frame mAP50 on TEST2 frames: NOT computed.
  R2-2 built no tool for them, and they are "reported, deciding nothing".

### The commands (as run)

      W=/home/batt/docker/poring-lab; T=/dev/shm/poring-lab-tmp/gef10-det; E=$W/data/train/eval/gef10-r2
      CAP="systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0"
      GB="python3 scripts/guarded_build.py --threshold 30 --sustain 30"
      # 1. TEST2's evaluation labels (16:30:51-16:49:00), one part per run, nice 19 ($T/label_test2.sh):
      $CAP nice -n 19 python $W/scripts/map_labels.py labels --map gef_fild10 --eval-test2 \
          /mnt/poring-lab-datasets/<part> --params $T/params.json \
          --classes $W/config/detector/classes-v2orc-payf07.json --out $T/labels-test2/<part>.json
      #    parts: 20261026T044312-rdp-rogue-a9, 20261026T052148-rdp-rogue-a10,
      #           20261026T055949-rdp-rogue-a11, 20261026T112924-rdp-w3
      # 2. the pack (16:50), seed 35:
      $CAP nice -n 10 python $W/scripts/map_labels.py pack --map gef_fild10 --eval-test2 $T/labels-test2/*.json \
          --per-species 60 --seed 35 --min-fit 0.636 --pack-dir $T/eval-r2/pack --key-dir $T/eval-r2-key \
          --instructions $W/docs/planning/gef10-blind-instructions.txt \
          --instructions-sha256 247b79197e47f732f4d1acf04bc6ed1ba2b7162c0c9fab26fe49cb5eab4b54b0 \
          --out $T/eval-r2-build.json
      # 3. refs (the pack's frames + the 200 latency frames):
      $CAP python $W/scripts/eval_q1.py refs $T/eval-r2-key/answer_key.json --out $E/q1-refs.json \
          --latency-200 35 --latency-out $E/latency-200-refs.json --labels-dir $T
      # 4. detections (the worker, R1-R3, 25 % VRAM cap; imgsz 1280, conf 0.25 = predict_dir's defaults):
      $GB "execdev:vision@1800=python -m poring_vision.predict_dir --weights /data/train/gef10-20261026/weights/last.pt \
          --refs /data/train/eval/gef10-r2/q1-refs.json --out /data/train/eval/gef10-r2/q1-pred-gef10r2.json"
      # 5. G1 (16:33): the new model on the gold frames, then v1 and the new model in ONE score:
      $GB "execdev:vision@900=python -m poring_vision.predict_dir --weights /data/train/gef10-20261026/weights/last.pt \
          --images /datasets/archive/train/eval/gold/$S/frames --out /data/train/eval/gef10-r2/g1-pred-gef10r2.json"
      python $W/scripts/gold_eval.py score $S --metric position --collapse-species --gold-dir $G \
          $G/pred-v1png-20261008.json $E/g1-pred-gef10r2.json
      #    S=20261004T103815-console-s2-indoor-v2; G=/mnt/poring-lab-datasets/archive/train/eval/gold/$S
      # 6. G2 (16:33-16:38): refs, v1 then the new model, ONE score:
      $CAP python $W/scripts/gold_eval.py refs --out $E/g2-refs.json
      $GB "execdev:vision@1800=python -m poring_vision.predict_dir --weights <v1 | new>/last.pt \
          --refs /data/train/eval/gef10-r2/g2-refs.json --out /data/train/eval/gef10-r2/g2-pred-<v1 | gef10r2>.json"
      #    v1 = /datasets/archive/train/v1png-20261008/weights/last.pt
      $CAP python $W/scripts/gold_eval.py score-cache --metric position $E/g2-pred-v1.json $E/g2-pred-gef10r2.json
      # 7. latency, GPU: predict_dir --timing on latency-200-refs.json, v1 then the new model;
      #    CPU: the ONNX export (detector-cpu.md's recipe, in /dev/shm/poring-lab-detector) + names sidecar, then
      nice -n 10 python $W/scripts/eval_latency.py $E/latency-200-refs.json \
          --model v1=$M/v1png-last-736x1280.onnx --model gef10r2=$M/gef10r2-last-736x1280.onnx --out $E/latency-cpu.json
      # 8. Batt's demo (16:37-16:48, reported only):
      $GB "execdev:vision@2400=python -m poring_vision.predict_dir --weights /data/train/gef10-20261026/weights/last.pt \
          --images /datasets/human-demos/20261026T095021-demo-human-demo-gef10/frames --glob *.jpg --timing \
          --out /data/train/eval/gef10-r2/demo-pred-gef10r2.json"
      python $W/scripts/detector_vs_packets.py from-predict $E/demo-pred-gef10r2.json --out $E/demo-boxes-gef10r2.jsonl
      $CAP nice -n 10 python $W/scripts/detector_vs_packets.py score $D --map gef_fild10 --layout hunt --window-s 898 \
          --chat-rect 0,615,600,709 --boxes $E/demo-boxes-gef10r2.jsonl --out $E/demo-score-gef10r2.json
      #    D=/mnt/poring-lab-datasets/scratch-archive/2026-10-26/demo-sessions/20261026T095021-demo-human-demo-gef10
      # 9. Q1 / E1 after both labellers:
      python $W/scripts/eval_q1.py score $T/eval-r2-key/answer_key.json A.json B.json $E/q1-pred-gef10r2.json \
          --cache-manifest /mnt/poring-lab-datasets/.framecache/v2orc-payf07-gef10-20261026/manifest.json --out $E/q1-score.json

### Where the outputs live (client-derived pixels stay off git)
- `data/train/eval/gef10-r2/` (local, ~5 MB): the predictions, the refs, and the G1 / G2 / Q1 /
  latency / demo scores.
- `/dev/shm/poring-lab-tmp/gef10-det/`: `labels-test2/`, `eval-r2/pack` (25 MB),
  `eval-r2-key/`, `eval-r2-answers/` (A.json, B.json) and `eval-r2-build.json`.
- The NAS copy (same day): `scratch-archive/2026-10-29/gef10-eval-r2/` (below once it is made).
