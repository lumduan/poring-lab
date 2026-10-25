---
doc_type: design
hypothesis: "A detector trained on v2orc + pay_fild07's cached data plus gef_fild10's TRAIN labels (gef10-o3h-e, frozen 2026-10-25 22:14) finds gef_fild10's species on held-out TEST data (recall and precision >= 0.80 for each species with >= 50 evaluated crops) without losing prt_fild08 (v1's gold set and held-out set no worse than v1)."
status: PRE-REGISTERED 2026-10-26 (BEFORE the cache is built and BEFORE any model with the gef10 classes exists; amendments only before training starts, clock-labelled)
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../planning/gef10-detector.md, payf07-eval.md, v2orc-vs-v1.md, ../planning/rogue-gef10.md]
next_action: "T1 on TEST (gef10-detector.md 12 step 3); the cache (dry run first); the run with its settings recorded BEFORE the launch; then score ONCE, after training ends, as written here."
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
