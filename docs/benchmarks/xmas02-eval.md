---
doc_type: design
hypothesis: "A detector scoped to xmas_dun02, trained on immune lattice watches labelled under the frozen xmas02 rule (o3h or o3h-t), finds the map's four common species on held-out TEST data (Q1c: recall and precision >= 0.80 per species with >= 50 evaluated crops, classes collapsed) and boxes the runner's own patrol frames with precision >= 0.80 on still captures (P4A), where v1 saw 1 of 937 labels."
status: "PRE-REGISTERED 2026-11-06 (written before any xmas_dun02 watch is recorded, before the cache and before any model exists; the plan is docs/planning/xmas02-detector.md, ACCEPTED by Batt ~10:45, Amendment A). Nothing scored."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../planning/xmas02-detector.md, gef10-eval.md, payf07-eval.md, v2orc-vs-v1.md, ../planning/rogue-xmas02.md]
next_action: "Nothing here runs until the training ends. Before the cache: an amendment records the class list (its sha256), the frozen params' sha256 and the TEST sessions' ids."
title: "xmas02: the xmas_dun02 detector's evaluation (pre-registered)"
date: 2026-11-06
owner: Batt
---

# xmas02: does the map-scoped model see xmas_dun02's monsters? (pre-registered 2026-11-06)

Batt (2026-11-06 ~08:2x and ~10:45 ICT): a detector for xmas_dun02 on the GPU, "go ahead, training
may start". The label rule, the split, T1 / T2 and the class scheme are in
[xmas02-detector.md](../planning/xmas02-detector.md). This document fixes, BEFORE the data, the
cache and the model exist, how the model will be judged. It follows gef10-eval.md's method; the
differences are the map scope (D1), the collapsed-class verdict (Q1c) and the patrol test (P4A).

## The model (fixed now)

| | v1 (`v1png-20261008`, the live CPU detector) | the xmas02 model (to train) |
|---|---|---|
| classes | player, monster, npc | `config/detector/classes-xmas02.json`, written after T2 (plan 7): 0 player, 1 Myst Case (1249), 2 Cruiser (1248), 3 Cookie (1265), 4 Christmas Cookie (1246), or 3 `cookie_any` by plan 6's fallback; 1515 / 1607 only if they reach the tier. Its sha256 goes in an amendment BEFORE the cache |
| data | v1's sessions | a NEW cache, NOT linked (D1): the TRAIN watches by plan 3c, labelled under the frozen params; VAL = xw1 (monitor only) |
| init, epochs | COCO YOLO11n, 30 | gef10 round 2's `last.pt` (sha256 `ebfc7a9a...`, D4), 20 epochs (D13) |
| seed, imgsz, batch / workers, close_mosaic, hsv_s / hsv_h, scale | 20261004, 1280, 2 / 1, 10, 0.7 / 0.015, 0.5 | 20261004, 1280, 2 / 1, **3, 0.2 / 0.015, 0.1** (D13) |

- **The scored checkpoint:** `last.pt` after the LAST COMPLETED epoch when the training ends (the
  report says which and why if early). Never `best.pt` or `mid.pt`. TEST is not read before the
  training ends.
- **Detector settings for every score:** `poring_vision.predict_dir` in the GPU worker (R1-R3, the
  VRAM cap), imgsz 1280, conf 0.25, ultralytics' default NMS. P4A and the latency also run the
  CPU path the runner uses (ONNX through `UnitDetector`, nice 10).
- **A match** is the POSITION metric (`label_iou.match_position`): the detection's box centre lies
  inside the label box; one-to-one per frame, nearest centre first. Classes must agree for Q1s;
  for Q1c any of the map's MONSTER classes counts (plan T-9).

## The evaluation data (never read before T1; refused by name by every measuring command)

- **TEST** = the watch **xw5** (TEST stands only, plan 3a), the patrol **xp1** and **X2**
  (`20261105T225409-rdp-xmas02-x2`). Their session ids go in the pre-cache amendment.
- **T1** (plan 5) reads them once, as a check of the LABELS; it decides nothing here.
- **The TEST labels for scoring are made once, AFTER the training ends**, with the frozen params
  (the same rule the TRAIN labels were cached under). The command is recorded here then.

## The evaluation pack (after the training ends; seed 53)

- **The pool:** per tier species, the TEST labels KEPT under the frozen rule (one stratum, N: E0,
  plan D11).
- **The draw:** per species, sorted by (session, frame, gid), shuffled with `map_labels.t2_order`
  at seed 53, salt `xmas02`; **the first 60** (fewer: all).
- **The crops, the reference sheet (multi-view, plan 6) and the questions:** T2's format; the
  instructions file `docs/planning/xmas02-blind-instructions.txt`, byte-identical to T2's (its
  sha256 recorded in the plan's amendment before the T2 pack).
- **Two NEW blind labeller agents** each get ONLY the pack, its instructions and an answers path;
  the key stays apart.
- **A crop is EVALUATED** when BOTH labellers answer q1 = yes, q2 = good and q3 = the label's
  species (with `cookie_any`, either cookie species counts as that class).

## The scores (fixed now)

**Q1c (VERDICT), per tier species s**, on the frames of the evaluated crops, classes COLLAPSED:
- **recall** = the evaluated s crops whose box contains the centre of a detection of ANY monster
  class / the evaluated s crops;
- **precision** = those matches / the monster-class detections whose centre falls inside ANY
  evaluated crop's box of the frame (detections elsewhere are not scored: their truth is not
  verified);
- **the bar, for each tier species with >= 50 evaluated crops: recall >= 0.80 AND precision >=
  0.80.** Fewer: reported, no bar.

**P4A (VERDICT), the runner's view:** on X2 + xp1, rogue-xmas02.md 4A's rule with 4J's readings
(the simple truth from packets, boxes at least half behind the UI dropped, the standard chat window
of the session), **the pooled monster precision on the STILL captures** (no move of ours in the
500 ms before the capture: the scorer's own split) **>= 0.80, with >= 100 detections there**; fewer
detections: NO VERDICT. Why still only: frames lag the server ~0.5 s, so a moving truth box is
displaced.

**Reported, deciding nothing:**
- **X2's 4A bar** (recall >= 0.80 per species, pooled precision >= 0.80, all captures), v1 and the
  new model side by side; the same on xp1. Not a gate: its truth includes monsters hidden by
  terrain, models and popups (4J saw them; gef10's model, which passed Q1 at 0.983, had recall 0.397
  on that kind of truth: gef10-eval.md, Batt's demo);
- P4A's recall per species and its moving captures; the first sighting per unit;
- **Q1s:** Q1c's bars with the classes agreeing; the Cookie / Christmas Cookie confusion matrix on
  evaluated crops;
- false boxes by kind on 30 drawn at seed 53 from P4A's unmatched still detections, judged by eye
  (toy models, terrain, UI, our own character);
- Q1c split by TEST part (xw5 / xp1 / X2) and by under-a-model / under-terrain / clear;
- **CPU latency** (ONNX through `UnitDetector`, nice 10, the same 200 TEST frames): p50 / p95, v1
  beside; **p95 <= v1's x 1.10** is what the runner needs (gef10 round 2: 499 vs 617 ms);
- **G1 / G2** (v2orc-vs-v1.md, unchanged) for information only: the model is map-scoped (D1), the
  runner never runs it on prt_fild08.

**The verdict:**
- **The xmas02 model PASSES when Q1c holds for every tier species with a bar AND P4A holds.** No
  species with a bar: "not established".
- **Passing does NOT switch the live detector.** Deploying it on xmas_dun02 (plan T-11: a model
  per map, the species collapsed to `monster` for the runner) is Batt's decision.

## Known limits (stated now)

- **TEST holds out stands and times, not whole places** (3a's blocks are about one screen wide;
  neighbouring views overlap), and xp1 / X2 walk the same edge loop the watches see from inside.
- **The watches are still frames of an immune character** (no fights, E0); the patrol TEST is
  where the runner's own motion is judged (P4A), on still captures only.
- **Garm Baby, the Goblins and the MVP** are rare by construction (`@killmonster2` at each setup);
  their bars will most likely not exist.
- **Cookie vs Christmas Cookie** differ only in colour; Q1c (the verdict) does not depend on telling
  them apart, Q1s reports whether the model does.

## The run (plan)

1. **Before the cache (an amendment here):** the class list's sha256, the frozen params' sha256,
   the TRAIN sessions admitted by 3c, the TEST session ids.
2. **The cache:** a guarded `cache:` step, a dry run first, the sustained IO rule (`--threshold 30
   --sustain 30`), outside 09:30-10:15 / 14:00-14:45 on weekdays.
3. **The training:** D13's settings, `train-day.sh` with WORKER=1, MID_CKPT=1, R1-R3, the R2
   co-tenant rule (fit-first's VTON is never touched), the IO guard.
4. **After the training ends:** the TEST labels, then the seed-53 pack and its two labellers;
   P4A (X2 + xp1); the reported items; the latency. Each scorer is committed with a positive case
   before it scores. Scored ONCE; the results go below this line, with nothing above it edited
   except by a clock-labelled amendment.

## AMENDMENT 1 (2026-11-06 12:2x ICT, before any xmas_dun02 watch is complete, any label, cache or model): the scorer's fields

The scorer was built after this document (`eval_q1.py` Q1c / E1c, merged c8e75e9). This states
which of its fields decide, in the words of "The scores" above; no bar changes.
- **Q1c's verdict precision is the field `precision`:** gef10's rule ported literally with the
  classes collapsed. On the frames of species s's evaluated crops, every monster-class detection
  whose centre lies inside ANY evaluated crop's box is in the denominator, so an unmatched box over
  another species' evaluated crop counts against s too. `precision_own_boxes` (only the detections
  inside s's own evaluated boxes) is REPORTED beside it and decides nothing.
- **Bars apply to the tier species only** (plan D3: Myst Case, Cruiser, Cookie, Christmas Cookie,
  or `cookie_any`). The pack draws every species with a kept TEST label (gef10's draw); a non-tier
  species (Garm Baby, a Goblin) is reported with no bar whatever its count.

## RESULTS

(none yet)
