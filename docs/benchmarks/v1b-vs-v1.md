---
doc_type: design
hypothesis: "Twenty more epochs of v1's own recipe, started from v1's final weights, give a detector that points at monsters at least as well as v1 on Batt's hand-checked gold set."
status: SCORED
role: null
verdict_date: 2026-10-12
verdict_ticket: null
supersedes: null
related: [v1-vs-v0png.md, ../operations/mid-epoch-checkpoints.md, ../operations/vision-long-lived.md]
next_action: "➡️ 2026-10-13 (Batt, decision 11): the divergence below DID change what is trained next: label quality first, no more epochs on v1; the analysis is ../planning/label-quality.md (PROPOSED). History: SCORED 2026-10-12 ~03:10: FAIL as written (gold, position, monsters: v1b P 0.888 / R 0.790 vs v1 0.902 / 0.830); v1 stays the candidate. Reported: v1b is better on the test sessions against v1's own labels (mAP50-95 +0.016 to +0.064)."
---

# v1b vs v1: v1's training continued (pre-registered 2026-10-11 ~07:47 ICT at commit 0ae7eb9, BEFORE the run starts)

**Batt (2026-10-11 ~07:40 ICT):** "today all cams use less gpu, please use this golden time to
continue training to monday 05:00".

**Why this run:** v1 (`v1png-20261008`, 30 epochs, TRAIN DONE 2026-10-10 08:22) had not plateaued:
- its validation mAP50-95 rose 0.698 -> 0.715 over its last five epochs (25-30), on its own labels;
- its train losses were still falling (box 0.569 -> 0.501).

The only other queued training (labels v2) waits on collection. The run is called **v1b**.

## The run (fixed now)
- **Name:** `v1b-20261011`; **data:** the SAME cache as v1 (`v1png-20261008`: the same frames and
  labels, the same splits).
- **Start:** v1's final weights (`/data/train/v1png-20261008/weights/last.pt`, epoch 30) through
  `train-day.sh`'s new `INIT_WEIGHTS` (train.py `--weights`).
- **Recipe:** v1's, unchanged (train.py's defaults as v1 used them):
  - imgsz 1280, batch 2, workers 1;
  - close_mosaic 10, the seed 20261004;
  - the optimizer and lr schedule as train.py picks them for v1.
  - Only two things differ: **20 epochs** (not 30), and **MID_CKPT=1** (proven 2026-10-11,
    mid-epoch-checkpoints.md).
- **Where:** inside the long-lived vision worker (option A, `execdev:`). The worker is started
  once through the quiet launcher.
  - Every attempt goes through `train-day.sh`'s guards (IO + R1-R3, the adaptive duty cycle,
    verified stops), one attempt per measured quiet window (chain12b's discipline).
  - The market windows do not apply on Sunday; Monday's begin after the deadline.
- **Deadline:** no attempt starts after Mon 2026-10-12 03:00 ICT. At Mon 04:30 a running attempt is
  stopped (SIGINT, the documented pause; mid.pt keeps the place), and the worker is stopped by
  05:00. A run cut short is **NOT evaluated**: it is a pause, not a result. Resuming it is Batt's
  call.

## Method (fixed now): v1-vs-v0png.md's method, v1b against v1
- **Weights:** `last.pt` of both runs (v1: epoch 30; v1b: its final epoch), not best.pt.
- **PRIMARY:** the gold set, model vs hand, POSITION ONLY, monsters.
  - Batt's 27 hand-checked frames (154 boxes); each model's detections at conf 0.25
    (`poring_vision.predict_dir`).
  - Scored with `scripts/gold_eval.py score --metric position`.
  - v1's side is its scored predictions (`pred-v1png-20261008.json`): monsters TP / FP / FN 83 / 9
    / 17, precision 0.902, recall 0.830.
  - **v1b is "at least as good" if its monster precision AND recall are both >= v1's.**
- **Reported, no decision:**
  - NPCs on the gold set (v1: 52 / 1 / 2);
  - the gold set's box metrics (IoU >= 0.5, with v1-vs-v0png's caveat);
  - mAP50 / mAP50-95 on the v1 test labels per held-out session: indoor-c, the gold session
    indoor-v2, and 054429 (domain shift, reported apart). v1's numbers are its 2026-10-10 evals
    (c15).
  - The per-epoch validation curve.
- **Caveat carried over (31a5bea):** 2 of the 27 gold frames fall in a span where our GM lay dead.
  It applies to both models alike.
- **Consequence:**
  - **PASS:** v1b becomes the candidate in v1's place.
  - **FAIL:** v1 stays.
  - Either way the LIVE detector is unchanged: whether any v1-line model replaces v0 is Batt's
    decision (it needs the CPU ONNX export).

## Results
**SCORED 2026-10-12 ~03:10 ICT, once, as written.**
- **The run:** chain17, 2026-10-11 07:48 -> 2026-10-12 03:05 ICT, inside the vision worker.
  - Worker UP 08:10:37 (quiet launcher). TRAIN DONE 03:02:34 (20 / 20). Evals 03:03-03:05. Worker
    STOPPED 03:05:54, nothing of ours on the GPU.
  - Three attempts:
    - attempt 0: 08:53-11:57, ended by R3-HARD (cam-1-01-font-s drops, fleet 87.6 det/s);
    - attempt 1: 12:41-16:19, ended by R3-HARD (cam-1-06-back-n drops, fleet 81.5 det/s);
    - attempt 2: 18:06-03:02.
  - Each abort: STOP VERIFIED in 5 s, then 15 quiet Frigate minutes and a quiet IO window. The
    resume was MID-EPOCH from mid.pt and bitwise, e.g. epoch 3 batch 1,949 / 4,097. These were the
    first live mid-epoch resumes.
  - Epoch time: ~85 min by day, ~30 min at night. Final epoch: val P 0.924, R 0.859, mAP50 0.909,
    mAP50-95 0.743 (v1's final 0.715; each on v1's own val labels, reported only).

**PRIMARY -- the gold set (27 frames, 154 boxes), POSITION metric, monsters, conf 0.25:**

| model | monster TP / FP / FN | precision | recall | centre px median / p90 |
|---|---|---|---|---|
| v1 (`v1png-20261008`, re-scored here: identical to 2026-10-10) | 83 / 9 / 17 | **0.902** | **0.830** | 6.84 / 14.59 |
| v1b (`v1b-20261011`) | 79 / 10 / 21 | 0.888 | 0.790 | 7.16 / 14.87 |

**VERDICT: FAIL -- v1b is NOT "at least as good" as v1: its monster precision AND recall are both
lower. v1 stays the candidate.** The difference is 4 hits, 1 false positive and 4 misses on 100 hand
boxes.

**Reported, no decision:**
- **NPCs, gold, position:** v1b 51 / 2 / 3 (P 0.962, R 0.944); v1 52 / 1 / 2 (0.981, 0.963).
- **Gold box metrics (IoU >= 0.5), monsters:**
  - v1b P 0.539, R 0.48, mean IoU 0.570;
  - v1 0.522, 0.48, 0.578.
  - (v1-vs-v0png's caveat: the gold set encodes v0's box convention.)
- **Test sessions on the v1 labels** (mAP50 / mAP50-95; monster AP50 / AP):

  | session (frames) | v1 | v1b |
  |---|---|---|
  | indoor-c (1,166) | 0.772 / 0.566; 0.762 / 0.559 | **0.832 / 0.630; 0.837 / 0.637** |
  | 054429, domain shift (1,077) | 0.694 / 0.584; 0.523 / 0.397 | 0.704 / 0.600; 0.564 / 0.445 |
  | indoor-v2, the gold session (268) | 0.781 / 0.559; 0.701 / 0.483 | 0.809 / 0.591; 0.725 / 0.517 |

- **The divergence, stated:** against v1's AUTOMATIC labels, v1b is better on every test session.
  Against the HAND-checked gold boxes, it is slightly worse.
  - One reading (not tested): the extra epochs fit v1's label convention more closely, and that
    convention is not exactly what a person marks.
    ➡️ **Measured 2026-10-13 ([label-quality.md](../planning/label-quality.md) §4.1), not a verdict:**
    22 of v1b's 31 gold errors (12 FN + 10 FP) are in the 2 dead-GM frames, where every detector scored
    (v0-baseline, v0-JPEG, v0-PNG, v1, v1-ONNX, v1b; v0-ONNX finds 1) finds none of the 12 monsters and draws boxes up and to the right
    of them (v1b: median +97.9, -96.0 px; v1: 0 / 8 / 12 there): the training session indoor-b's dead-GM
    span carries labels displaced that way. On the 25 other frames v1 is 83 / 1 / 5 and v1b
    79 / 0 / 9. **Box by box (§4.8): v1b misses 6 units v1 finds, none in the dead-GM frames, and 4 of
    the 6 are units the training labels get wrong** (our own walk 2, chat window 1, top window 1); it
    finds 2 that v1 misses.
  - The gold set is small: 100 monster boxes, so 4 boxes move recall by 0.04.
  - Neither is decided here. The pre-registered primary decides, and it says v1 stays.
- **Outputs:** `/dev/shm/poring-lab-tmp/gpu-day/c17/` (local); predictions
  `data/train/eval/gold/20261004T103815-console-s2-indoor-v2/pred-v1b-20261011.json`.
