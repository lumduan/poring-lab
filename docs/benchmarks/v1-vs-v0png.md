---
doc_type: design
hypothesis: "Labels v1 (k = 0.140, PROVISIONAL) train a detector that points at monsters at least as well as v0-PNG's, on Batt's hand-checked gold set."
status: PRE-REGISTERED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../phase3-plan.md, v0-png-vs-jpeg.md]
next_action: "Build the v1png cache (after the v0-JPEG matched-batch run and its evals), then train v1 when R1-R3 allow, under the ADAPTIVE DUTY CYCLE (Batt 2026-10-08: it replaces the 0.3 step-sleep setting; bar unchanged) and with MID-EPOCH checkpoints if their resume equivalence is proven first (Batt 2026-10-08); score ONCE as written here."
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

## Results
Not yet: no v1 model exists.
