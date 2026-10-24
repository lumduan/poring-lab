---
doc_type: design
hypothesis: "A detector trained on v2orc's data (v1's prt_fild08 sessions + orcsdun01's TRAIN blocks) plus pay_fild07's TRAIN labels (payf07-o3h-all) finds pay_fild07's species on held-out TEST data (recall and precision >= 0.80 for each species with >= 50 evaluated crops), and loses neither prt_fild08 (v1's gold set and held-out set no worse than v1) nor orcsdun01 (v2orc-vs-v1.md's P1 on col2)."
status: PRE-REGISTERED 2026-10-24 (BEFORE the cache is built and BEFORE any model with the payf07 classes exists; amendments only before training starts, clock-labelled)
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../planning/payf07-detector.md, v2orc-vs-v1.md, item-class.md, ../planning/orcsdun01-detector.md, ../planning/training-cost.md]
next_action: "Build the cache (../planning/payf07-detector.md 12e), launch the run with its settings recorded in 12 BEFORE it starts, then score ONCE, after training ends, as written here."
---

# payf07: pay_fild07's species, without forgetting prt_fild08 or orcsdun01 (pre-registered 2026-10-24)

Batt (2026-10-24 ~18:0x ICT, as relayed by the parent): "I think you should train YOLO for the
monsters in this map too." `../planning/payf07-detector.md` section 8 asked for the evaluation to be
pre-registered BEFORE training. Its proposal is the starting point: per species on TEST's
blind-judged crops (a new seed, two new labellers), recall and precision >= 0.80 for a species with
>= 50 evaluated crops; v1's gold set and held-out prt_fild08 sessions no worse than v1; orcsdun01's
col2 per `v2orc-vs-v1.md`.

This file is written and committed BEFORE the cache is built and BEFORE any model with these
classes exists. It is scored once, as written.

**Why a new file, not an amendment of v2orc-vs-v1.md:** this model has other classes (21), other
data (pay_fild07's TRAIN) and its own TEST. v2orc-vs-v1.md stays as pre-registered for v2orc (never
scored: stopped at epoch 3, `../planning/orcsdun01-detector.md` 3n). Its G1, G2 and P1 are reused
here by reference, unchanged.

## The model (fixed now)

| | v1 (`v1png-20261008`, the live CPU detector) | the payf07 model (to train) |
|---|---|---|
| classes | player, monster, npc | `config/detector/classes-v2orc-payf07.json` (sha256 `aa78912d…8da9a80`): v2orc's ids 0-14 unchanged (player 0, npc 1, warp 2, the 12 v2orc species 3-14) + Elder Willow 15 (1033), Willow 16 (1010), Eggyra 17 (1116), Bigfoot 18 (1060), Poporing 19 (1031), Green Plant 20 (1080) |
| data | v1's sessions, v1 labels | the cache of `../planning/payf07-detector.md` 12e: v2orc's cache `v2orc-fix2-w-o3h-20261024` LINKED unchanged (train / val / test as there) + pay_fild07's TRAIN under `payf07-o3h-all` (staged spots 0-7, t1b, s-pilot, s1, and any later session that passes 3c before the build) |
| model, seed, imgsz, batch / workers | YOLO11n, 20261004, 1280, 2 / 1 | the same |
| starting weights, epochs, `hsv_s`, `close_mosaic` | COCO YOLO11n, 30, 0.7, 10 | **as recorded in payf07-detector.md 12 BEFORE the launch** (12f proposes: v2orc's epoch-3 `last.pt`, 10 epochs, `hsv_s` 0.2, `close_mosaic` 3). A run launched with other values than the recorded ones is not this evaluation's model |
| VAL | v1's val sessions | v1's val sessions only (as v2orc: val monitors training and decides nothing) |

**The scored checkpoint:** `last.pt` after the LAST COMPLETED epoch when the training ends: the
planned final epoch, or an earlier one if the run is stopped (by Batt or the parent; the report
states the epoch and why). Never `best.pt` (picked by val fitness), never `mid.pt`. TEST is not read
before the training ends, so where a run stops cannot be chosen on TEST.

**The detector settings for every score below:** `poring_vision.predict_dir` (the GPU worker, R1-R3,
the 25 % VRAM cap), imgsz 1280, **conf 0.25** (v1's and v2orc's), ultralytics' default NMS
(class-aware, IoU 0.7, max_det 300).

**What "a match" is:** the POSITION metric (`label_iou.match_position`, v1's primary): a detection
matches a label when the classes agree and the detection's box CENTRE lies inside the label box;
pairs are one-to-one per frame, greedily by ascending centre distance. No IoU threshold is used for
the bars. The IoU numbers reported below use IoU >= 0.5 (`label_iou.score`, the same greedy
one-to-one per class).

## The evaluation data: pay_fild07's TEST (held out since 7ed0422)

- **TEST = staged spots 8-11 of `20261024T170356-rdp-stage-items-b` + `20261024T131838-rdp-thief-t2`
  (the whole session)** (`../planning/payf07-detector.md` 3a / 3b). Never in any cache; never read
  for a parameter. T1 (10k) read only the PREDICTION on it.
- **The TEST labels are made once, AFTER the training ends:** `map_labels.py labels` with the frozen
  `params.json` (sha256 `e93367fe…dc2de14`), section 4f's candidate frames, the frozen rule and
  Amendment B, then 11's `weak_fit` floor (T_h 0.479 on every label NOT under a model) =
  `payf07-o3h-all`, the rule the TRAIN labels were cached under. The tool refuses TEST today; that
  refusal is lifted for this one step by an explicit option added then (its commit recorded in the
  result).

## The evaluation pack (after the training ends; seed 23)

- **The pool:** per species, the TEST labels KEPT under `payf07-o3h-all` (any candidate frame,
  whole or not, as orcsdun01 3f's evaluation tier).
- **The draw:** per species, the pool sorted by (session, frame, gid), shuffled with
  `random.Random(f"payf07:23:{mob}")` (`map_labels.t2_order`, seed 23; rounds 1 and 2 used 21 and
  22), **the first 60** (fewer: all of them, so a species can reach the 50-crop bar). The species:
  the six of pay_fild07 (a species with no TEST label is reported as such: T1 found no Green Plant
  in TEST). No controls.
- **The crops, the multi-view reference sheet (12 species, letters by seed 23) and the questions:**
  T2's (`map_labels.py pack`'s format), unchanged.
- **The instructions:** `docs/planning/payf07-blind-instructions.txt`, byte-identical (sha256
  `dc3ee728…19f9`).
- **Two NEW blind labeller agents,** each given ONLY the pack, its instructions and an answers path
  outside it; the key stays apart (T2's procedure).
- **A crop is EVALUATED** when BOTH labellers answer q1 = yes, q2 = good and q3 = the label's
  species.

## The scores (fixed now)

**Q1, pay_fild07 per species s**, on the frames of the evaluated crops (the position metric):
- **recall** = the evaluated s crops whose box contains the centre of a class-s detection (one-to-one
  per frame, nearest centre first) / the evaluated s crops;
- **precision** = those matches / the class-s detections whose centre falls inside ANY evaluated
  crop's box of the frame (of any species, so a Willow box on an evaluated Elder Willow counts against
  Willow's precision). Detections elsewhere in the frame are not scored here: their truth is not
  verified (orcsdun01 3f's P1, v2orc-vs-v1.md Amendment A);
- **the bar, for each pay_fild07 species with >= 50 evaluated crops: recall >= 0.80 AND precision
  >= 0.80.** Fewer: reported, no bar.

**G1, v1's gold set** (v2orc-vs-v1.md G1, unchanged): Batt's 27 hand-checked frames of
`20261004T103815-console-s2-indoor-v2`; every monster-species class collapsed to `monster`; the
position metric. **Bar: P >= 0.882 AND R >= 0.810.**

**G2, v1's prt_fild08 held-out set** (v2orc-vs-v1.md G2, unchanged): `20261004T054429-console-s2-outdoor`
on v1's test labels collapsed to `monster`. **Bar: monster recall and precision (position) each
>= v1's on the same frames - 0.02**, v1 re-scored first with the same command.

**O1, orcsdun01 (no forgetting)** = v2orc-vs-v1.md's P1 as amended by its Amendments A and B,
unchanged: col2 (`20261021T122650-orcsdun01-col2`, never read so far) labelled after the training with
`v2orc-fix2+W+o3h` (the frozen params sha256 `fe1fb9b3…f6d5af`, W, o3h), the seed-3 evaluation pack
(up to 60 crops per species), two NEW labellers, round 2's instructions (sha256 `1253e64b…fae13`).
**Bar: for each orcsdun01 species with >= 50 evaluated crops, recall and precision >= 0.80.**
- The seed-3 pack does not depend on the model. If v2orc's epoch-3 `last.pt` is scored on it too,
  its numbers are reported beside (deciding nothing).

**Reported, deciding nothing:**
- per species, the IoU >= 0.5 precision / recall on the evaluated crops' frames;
- **whole-frame precision** per pay_fild07 species: on TEST frames labelled WHOLE (every visible
  monster of the six species labelled, our own `player` box added as in the cache), a class-s
  detection whose centre lies in no label box of the frame is a false positive; and mAP50 on them;
- **the look-alike confusion:** for each evaluated crop, the class of the detection matched to its
  box by position IGNORING the class (if any): Elder Willow <-> Willow (the `hsv_s` flag,
  payf07-detector.md 7), Poporing <-> Poring, Green Plant <-> White Plant;
- **E1, ENGAGED Elder Willows** (Batt's clip; Amendment B leaves them without a label box): in TEST's
  candidate frames, every Elder Willow in Amendment B's `engaged` set whose projected ground anchor
  lies on the frame and outside `client_layout.RECTS["hunt"]`: the share with a class-15 detection
  whose box contains the anchor; and the share with a class-16 (Willow) one;
- Q1 split by TEST part (staged spots 8-11 / t2) and by under-a-model / clear;
- our own `player` box on TEST whole frames (recall, position);
- **latency per frame at imgsz 1280:** GPU PyTorch in the vision worker (25 % cap) and CPU ONNX with
  the live pipeline's settings (nice 10), p50 / p95 over the same 200 frames, v1 beside.

**The verdict:**
- **The payf07 model PASSES if Q1 holds for every species with a bar, and G1, G2 and O1 hold.**
- Passing does NOT switch the live detector: that is Batt's decision.

**What the numbers must be for the bot to use it (Batt decides; this states the numbers only):**
- **pay_fild07 hunting by sight:** Q1 passes for the species used, **Elder Willow's bar EXISTS (>= 50
  evaluated crops) and passes** (fewer evaluated Elder Willow crops = no evidence for the species the
  model was asked for), G1 and G2 hold, and the CPU p95 latency is <= v1's p95 x 1.10 on the same
  200 frames.
- **orcsdun01:** O1 holds (orcsdun01 is ended, 3n; reported for completeness).
- A species without a bar, or failing its bar, is not shown to be detected, whatever the verdict.

## Known limits (stated now)

- **Engaged units are not in Q1:** Amendment B excludes them from every label (their fits were
  spurious, 10c), so Q1 measures idle and walking monsters. E1 reports the engaged Elder Willows
  without a bar.
- **t2 is a hunting run on the same map:** its backgrounds were seen in training (the staged TEST
  spots are >= 25 cells from the FIT spots). Q1 measures held-out MONSTERS and times, not held-out
  places (as orcsdun01's col2).
- **Elder Willow's TEST size is unknown until the TEST labels exist:** T1 scored 25 standing Elder
  Willow labels in TEST (10k); the kept labels include walkers too. If fewer than 50 are evaluated,
  Elder Willow has no bar (above).
- **Our own `player` box** is v0's 34 x 74 at the camera target (labels v2), too tall for a sitting
  Thief; it is reported, not barred.

## The run (plan)

1. **The cache:** `../planning/payf07-detector.md` 12e's guarded `cache:` step (after the branch is
   merged; outside 09:30-10:15 / 14:00-14:45 on weekdays).
2. **The training:** the settings recorded in 12 BEFORE the launch; `train-day.sh` with WORKER=1,
   MID_CKPT=1, R1-R3, the IO guard, the 25 % VRAM cap, the quiet launcher.
3. **After the training ends:** the TEST labels (above), the seed-23 pack and its two labellers; G1
   and G2 (v1 re-scored first); col2's labels and the seed-3 pack (O1); the latency. Each scorer is
   committed with a positive case on real data before it scores (scorers-must-be-committed). Scored
   ONCE; the results are added below this line, with nothing above it edited.
