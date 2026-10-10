---
doc_type: design
hypothesis: "Labels v1 (k = 0.140, PROVISIONAL) train a detector that points at monsters at least as well as v0-PNG's, on Batt's hand-checked gold set."
status: SCORED
role: null
verdict_date: 2026-10-10
verdict_ticket: null
supersedes: null
related: [../phase3-plan.md, v0-png-vs-jpeg.md]
next_action: "SCORED 2026-10-10: v1 >= v0-PNG on the primary (gold, position, monsters: P 0.902 vs 0.857, R 0.830 vs 0.780). Batt: whether v1 replaces v0-PNG as the live detector (the CPU ONNX export for the walk/loot rules is a separate step)."
---

# v1 vs v0-PNG: the same frames, the same format, different labels (pre-registered 2026-10-07)

Batt (2026-10-07):
- proceed with labels v1 in parallel to M4;
- the per-species split vanishes when measured like with like (M4 2e);
- v1's labels point at monsters at least as well as v0's on the gold set (§5f).

This file is written and committed BEFORE any v1 model exists. It is scored once, as written.

## What differs, stated first

| | v0-PNG (`v0png-20261006`, done) | v1-PNG (`v1png-<date>`, to build) |
|---|---|---|
| frames, split | 13,946; train outdoor-a/b/d, indoor-b, s2-outdoor; val outdoor-c, indoor-a; test indoor-c, 054429, indoor-v2 | the same sessions and split (`build_frame_cache.py` with the same lists) |
| image format | lossless PNG | the same |
| **labels** | **v0**: fixed 44×40 / 34×74 boxes from the projected foot point | **v1**: `predict_sprite` boxes (the client's idle/walk envelope or the known one-shot frame), **k = 0.140 (korangar), PROVISIONAL** |
| model, epochs, seed, imgsz | YOLO11n, 30, 20261004, 1280 | the same |
| batch / workers | 2 / 1 | 2 / 1 (if it differs, a stated confound) |
| step sleep | 0 (no R3 guard yet) | the 0.3 setting found under R3 (duty cycle only; it does not change the maths, but stated) |

- k = 0.140 is PROVISIONAL. M4 2e left k open: ODD k_h 0.1467 matched neither prior; k_w 0.1387
  is within 1 % of korangar. The fresh M4 session decides.
- A later k change means a rebuild + retrain, not a redesign.
- One run each, so there is no seed variance.

## Method (fixed now)
- **Weights:** `last.pt` of both runs (epoch 30), not best.pt.
- **Test images:** the PNG test frames of the held-out sessions:
  - indoor-c, in domain;
  - indoor-v2, the gold session;
  - 054429, the domain-shift set, reported APART.
- **PRIMARY: the gold set, model vs hand, POSITION ONLY, monsters.**
  - Batt's 27 hand-checked frames (154 boxes).
  - Each model's detections at conf 0.25 (`poring_vision.predict_dir`).
  - Scored with `scripts/gold_eval.py score --metric position` (`label_iou`'s position scorer:
    centre in the hand box, same class, one-to-one by centre distance).
  - **v1 is "at least as good" if its monster precision AND recall are both ≥ v0-PNG's.**
- **Reported, no decision:**
  - The gold set's box metrics (IoU ≥ 0.5, mean IoU), with the caveat that the gold set encodes
    v0's size convention: 82 % of its monster boxes are v0's 44 × 40 (§5e). So box metrics
    favour v0 by construction.
  - mAP50 / mAP50-95 per test session against BOTH label sets, a 2 × 2: each model on the v0png
    test labels and on the v1png test labels. The frames are the same; only the label files
    differ.
  - NPC numbers (v1 changes no NPC box).
  - Per-epoch validation curves (each on its own labels: confounded, for shape only).

## The run (plan; R1–R3 decide when, day or night)
1. **The cache**, after the v0-JPEG matched-batch run and its evals (not concurrently, so the
   Frigate deltas stay attributable):

       scripts/runbooks/cache-day.sh /dev/shm/poring-lab-tmp/v1-cache v1png-<date> \
         --train <v0png's 5> --val <its 2> --test <its 3> --labels v1 --k 0.140

   - The size is measured from v0png: the same frames and format, so ~22 GB / 47 shards on the NAS.
   - Reported: frames, boxes per session, shards, bytes, the manifest + shard sha256.
2. **Training:**

       SLEEP_LEVEL=<the 0.3 level> scripts/runbooks/train-day.sh v1png-<date> v1png-<date> 30 <dir> 2 1

   It starts on a fresh baseline with R2 clear, through guarded_build (IO + R1–R3).
   - ➡️ **SUPERSEDED (Batt, 2026-10-08): `SLEEP_LEVEL` is gone.** The ADAPTIVE DUTY CYCLE
     (docs/operations/r3-paired.md, Batt 2026-10-07) replaced the step-sleep ladder;
     `train-day.sh` no longer reads `SLEEP_LEVEL`. v1 trains under the duty cycle, as v0-JPEG did:

         scripts/runbooks/train-day.sh v1png-<date> v1png-<date> 30 <dir> 2 1

     **The bar and the scoring are unchanged.** Only the operating setting moved, and it is the
     same for v0-JPEG, the run v1 follows.
   - **Mid-epoch checkpoints (Batt, 2026-10-08):** v1 runs ~15–16 h through daytime Frigate peaks,
     so an abort must not throw away a partial epoch. They are added before v1 starts, and only
     after a short run proves the resume equivalent. Otherwise v1 keeps epoch-level checkpoints.
     Either way the choice is recorded here before v1 starts.
3. **Evals:** the same chain as v0-JPEG's:
   - last.pt on the PNG test frames;
   - `predict_dir` on the gold frames;
   - `gold_eval.py score --metric position` (primary) and the IoU score (reported);
   - plus the 2 × 2 mAP (both models × both test-label sets).

## The cache: BUILT (2026-10-08 22:20–23:41 ICT / 15:20–16:41 UTC, `cache-day.sh`, attempt 0, no guard trip)
- `v1png-20261008`: labels v1, k = 0.140, PNG, the same 10 sessions and split as v0png, with
  `build_frame_cache.py`'s defaults.
- **13,946 frames, 47 shards, 23,091,722,240 bytes** on the NAS. Every shard was
  read back against the manifest's sha256: **0 mismatched**.
- `manifest.json` sha256 `c11423e346657364e522664d710656a61e6c0b6c7973c029f1707910b9a4e3b6`.

| session | split | frames | boxes |
|---|---|---|---|
| 20261004T150114-console-p3-outdoor-d | train | 2,309 | 12,377 |
| 20261004T130548-console-p3-outdoor-a | train | 2,582 | 5,164 |
| 20261004T135714-console-p3-outdoor-b | train | 472 | 1,639 |
| 20261004T141832-console-p3-indoor-b | train | 2,421 | 16,371 |
| 20261003T215314-console-s2-outdoor | train | 409 | 1,346 |
| 20261004T143947-console-p3-outdoor-c | val | 2,124 | 10,240 |
| 20261004T133558-console-p3-indoor-a | val | 1,118 | 6,712 |
| 20261004T152232-console-p3-indoor-c | test | 1,166 | 5,940 |
| 20261004T054429-console-s2-outdoor | test | 1,077 | 4,186 |
| 20261004T103815-console-s2-indoor-v2 | test | 268 | 1,493 |

- The v1 labels change only monster boxes. NPC boxes are v0's, as stated above, but the box COUNTS
  per session also differ a little from v0png's (e.g. outdoor-d 12,377 vs 12,474), because
  `predict_sprite` drops boxes it cannot place. Reported, not a decision.

## Results
~~Not yet: no v1 model exists.~~ ➡️ **SCORED 2026-10-10 ~10:05 ICT, once, as written** (v1 `last.pt`, epoch 30,
TRAIN DONE 2026-10-10 08:22 ICT; the evals ran inside the long-lived vision worker, option A,
chain15; outputs `/dev/shm/poring-lab-tmp/gpu-day/c15/`).

**PRIMARY -- the gold set (Batt's 27 hand-checked frames, 154 boxes), POSITION metric, monsters, conf
0.25 (`gold_eval.py score --metric position`):**

| model | monster TP / FP / FN | precision | recall | centre px median / p90 |
|---|---|---|---|---|
| v0-PNG (`v0png-20261006`) | 78 / 13 / 22 | 0.857 | 0.780 | 7.0 / 15.2 |
| **v1 (`v1png-20261008`)** | **83 / 9 / 17** | **0.902** | **0.830** | 6.8 / 14.6 |

**VERDICT: v1 is "at least as good" -- its monster precision AND recall are both >= v0-PNG's (both are
higher).** NPCs: identical (52 / 1 / 2, precision 0.981, recall 0.963 for both).

**Reported, no decision:**
- **The gold set's box metrics (IoU >= 0.5), monsters:** v1 precision 0.522, recall 0.48, mean IoU 0.578;
  v0-PNG 0.615, 0.56, 0.766. As stated before the run, the gold set encodes v0's 44 x 40 size
  convention (82 % of its monster boxes), so box metrics favour v0 by construction.
- **The 2 x 2 mAP (mAP50 / mAP50-95; monster AP50 / AP), the same PNG test frames, two label sets:**

| test set (frames) | v0 model, v0 labels | v1 model, v0 labels | v0 model, v1 labels | v1 model, v1 labels |
|---|---|---|---|---|
| indoor-c (1,166) | 0.782 / 0.567 (v0-png-vs-jpeg.md) | 0.565 / 0.312; monster 0.348 / 0.052 | 0.608 / 0.333; monster 0.413 / 0.064 | **0.772 / 0.566; monster 0.762 / 0.559** |
| indoor-v2, gold session (268) | 0.769 / 0.545 (ibid.) | 0.579 / 0.338; monster 0.297 / 0.041 | 0.571 / 0.345; monster 0.263 / 0.038 | **0.781 / 0.559; monster 0.701 / 0.483** |
| 054429, domain shift (1,077), apart | 0.704 / 0.584 (ibid.) | 0.631 / 0.438; monster 0.396 / 0.104 | 0.613 / 0.429; monster 0.332 / 0.078 | **0.694 / 0.584; monster 0.523 / 0.397** |

  Each model scores best on its own label convention (the box-size convention differs), so the
  cross cells mostly measure that convention, not the detector; the decision is the position metric
  above, as pre-registered.
- **Runtime:** inference 5.35 ms / image at 1280 (indoor-c), peak VRAM 694 MiB (cap 3,962 MiB).

- **Mid-epoch checkpoints, recorded by the overnight chain BEFORE v1 started (2026-10-08 23:44:01 ICT):** FAIL: proof run B2 (the first --resume from mid.pt, expected to die at rc 86) CRASHED with rc 1, RuntimeError in fused Adam (params, grads, exp_avgs and exp_avg_sqs must have the same dtype, device and layout) right after the bitwise state restore; compare was not run. v1 keeps epoch-level checkpoints (MID_CKPT unset), as pre-registered. The proof: `/dev/shm/poring-lab-tmp/gpu-night/proof-B2-221713.out`.
