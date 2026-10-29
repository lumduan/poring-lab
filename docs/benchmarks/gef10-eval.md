---
doc_type: design
hypothesis: "A detector trained on v2orc + pay_fild07's cached data plus gef_fild10's TRAIN labels (gef10-o3h-e, frozen 2026-10-25 22:14) finds gef_fild10's species on held-out TEST data (recall and precision >= 0.80 for each species with >= 50 evaluated crops) without losing prt_fild08 (v1's gold set and held-out set no worse than v1)."
status: "NOT RUN: T1 FAILED 2026-10-26 03:16 ICT (gef10-detector.md 13r), so no gef10 model is trained this round and this evaluation has nothing to score. Was: PRE-REGISTERED 2026-10-26 (BEFORE the cache is built and BEFORE any model with the gef10 classes exists)"
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../planning/gef10-detector.md, payf07-eval.md, v2orc-vs-v1.md, ../planning/rogue-gef10.md]
next_action: "None this round (T1 failed, gef10-detector.md 13r). A round 2 would need its own TEST and its own evaluation pre-registration; this one is not reused with TEST read."
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
