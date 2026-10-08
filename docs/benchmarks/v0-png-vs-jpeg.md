---
doc_type: design
hypothesis: null
status: ACCUMULATING
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [phase3-plan.md, h264-vs-png.md]
next_action: "2026-10-08 21:03: the matched-batch rerun (v0jpg-20261007, JPEG at batch 2) is SCORED: the 054429 domain-shift gain was the BATCH SIZE, not the format (JPEG b2 0.710 vs PNG 0.704 mAP50); in domain a tie; gold monster recall 0.52 vs 0.56 (4 boxes, one run each). PARKED for Batt: whether later caches return to JPEG (PNG costs ~5x storage for no measured gain). v1 stays PNG as pre-registered."
---

# v0-PNG vs v0-JPEG: the same frames, the same labels, a different image format

Batt (2026-10-06): train v0 on a lossless PNG cache as the one-variable baseline for the later
v0-vs-v1 comparison. Report it only after the run ends, at matching epochs, on the same held-out
sessions and the gold set.

## What differs between the two runs (stated first)

| | v0-JPEG (`v0-baseline-20261004`) | v0-PNG (`v0png-20261006`) |
|---|---|---|
| cache | `v0-baseline-20261004b`, JPEG q95 | `v0png-20261006`, lossless PNG |
| frames, split | 13,946; train outdoor-a/b/d, indoor-b, s2-outdoor; val outdoor-c, indoor-a; test indoor-c, 054429, indoor-v2 | the same |
| labels | v0 | v0 + the self-ID fix (only outdoor-b changes: 1,659 → 1,648 boxes) |
| model, epochs, seed | YOLO11n 1280, 30, 20261004 | the same |
| **batch / workers** | **4 / 2** | **2 / 1** (Batt's daytime rule) |
| run | 2026-10-04/05, one resume | 2026-10-06 13:18 → 10-07 00:31, three guard-trip resumes |

So this is NOT a clean one-variable comparison:
- the batch size differs, and a smaller batch makes more updates per epoch;
- there is one run each, so there is no seed variance;
- the labels differ slightly (0.7 % of one training session's boxes).

## Method
- **Matching epochs:** `last.pt` of both, i.e. epoch 30. v0-JPEG's best epoch was 26, so `best.pt`
  would not match.
- **The same test images:** every model is run on the PNG cache's test frames
  (`--cache v0png-20261006 --split test --sessions S`). Those are the lossless decoded frames the
  agent sees in deployment, with the same (fixed) labels for both.
- **The gold set:** Batt's 27 hand-checked frames of indoor-v2 (154 boxes). Both models'
  detections (conf 0.25) are scored with `label_iou`'s own scorer (`scripts/gold_eval.py`;
  per-class greedy match at IoU ≥ 0.5), so they compare directly with the v0 auto labels' own
  score.
- Every eval ran guarded, one at a time (2026-10-07 00:50–00:57). Each summary is checked by its
  own `sessions` / `eval` / `cache` fields.

## Results: held-out sessions, the same PNG frames, epoch 30

| test set | frames | JPEG mAP50 / 50-95 | PNG mAP50 / 50-95 | Δ mAP50 / 50-95 |
|---|---|---|---|---|
| indoor-c (held out, in domain) | 1,166 | 0.767 / 0.573 | 0.782 / 0.567 | +0.016 / −0.006 |
| indoor-v2, gold session, AUTO labels | 268 | 0.766 / 0.547 | 0.769 / 0.545 | +0.003 / −0.002 |
| **054429 (domain shift)**, reported apart | 1,077 | **0.484 / 0.384** | **0.704 / 0.584** | **+0.221 / +0.200** |

Per class:

| test set | class | JPEG AP50 / AP | PNG AP50 / AP |
|---|---|---|---|
| indoor-c | monster | 0.741 / 0.540 | 0.760 / 0.532 |
| indoor-c | npc | 0.792 / 0.606 | 0.804 / 0.602 |
| 054429 | monster | 0.464 / 0.382 | 0.515 / 0.389 |
| 054429 | **npc** | **0.503 / 0.387** | **0.894 / 0.779** |
| indoor-v2 (auto) | monster | 0.661 / 0.446 | 0.659 / 0.437 |
| indoor-v2 (auto) | npc | 0.872 / 0.647 | 0.879 / 0.653 |

Precision and recall on 054429: JPEG 0.656 / 0.502, PNG 0.793 / 0.791.

Inference: 4.9–5.4 ms per image for both; peak VRAM 694 MiB in eval (the cap is 3,962).

## Results: the gold set (model vs hand, 27 frames, 154 boxes)

| | P | R | mean IoU | TP / FP / FN | monster TP / FP / FN | npc TP / FP / FN |
|---|---|---|---|---|---|---|
| v0 AUTO labels (B6 reference) | 0.715 | 0.669 | 0.935 | 103 / 41 / 51 | 58 / 32 / 42 | 45 / 9 / 9 |
| v0-JPEG model | 0.706 | 0.656 | 0.817 | 101 / 42 / 53 | 54 / 36 / 46 | 47 / 6 / 7 |
| v0-PNG model | 0.715 | 0.669 | 0.816 | 103 / 41 / 51 | 56 / 35 / 44 | 47 / 6 / 7 |

The overall counts of the PNG model and of the auto labels are EQUAL by coincidence. Per class
they differ, and so does the IoU; this was checked, not assumed.

## Validation curves (each run on its OWN format's val frames: confounded, shown for shape)

| epoch | JPEG mAP50 / 50-95 | PNG mAP50 / 50-95 |
|---|---|---|
| 5 | 0.776 / 0.575 | 0.826 / 0.622 |
| 10 | 0.761 / 0.609 | 0.843 / 0.661 |
| 20 | 0.815 / 0.681 | 0.856 / 0.700 |
| 30 | 0.804 / 0.679 | 0.864 / 0.705 |

Best by mAP50-95: JPEG epoch 26 (0.691); PNG epoch 29 (0.707).

## Reading
1. **In domain, the image format makes no measurable difference** (indoor-c and indoor-v2 within
   ±0.02).
2. **On the domain-shift set, PNG is far better**: +0.22 mAP50, almost all of it NPC (AP50 0.50
   → 0.89).
   - This fits 054429's diagnosis (2026-10-05): its pixels differ (PNG-era 1 fps recorder), not
     its labels.
   - A model trained on JPEG q95 frames meets lossless frames there.
   - It is NOT attributed to the format alone: batch 2 vs 4 and a single run each could also
     move a cross-domain number this much.
3. **The gold set says the v0 models are bounded by their labels.**
   - Both models reach the auto labels' own precision and recall against the hand-check, with
     looser boxes (IoU 0.82 vs 0.94).
   - Better in-domain detection needs better labels (v1, M5), not a different image format.

## Cost
- Training took 8.6 h of compute for PNG (batch 2, data-loading bound) vs 4.3 h for JPEG
  (batch 4).
- Frigate inference during the PNG run: median 32.0 ms, p95 63.9 (7,531 samples at 5 s). Without
  a GPU job: 26.4 / 49.8.

## The matched-batch rerun: RESULTS (`v0jpg-20261007`, done 2026-10-08 20:59 ICT / 13:59 UTC)

Batt asked for it on 2026-10-07: v0-JPEG at batch 2 / workers 1, with the same seed, split and
epochs, on a JPEG cache rebuilt with today's labels (`v0jpg-20261007`, the same labels as
`v0png-20261006`). So the image format is now the only variable.
- **Scored as the earlier comparison was:** last.pt (epoch 30) on the PNG cache's test frames, and
  `gold_eval.py` on the 27 gold frames.
- **The run:** the adaptive duty cycle, resumes after IO-guard pauses, and the R3 paired measurement.
- **No numeric bar was pre-registered for it.** It answers the attribution question, so it is
  reported as measured.

| test set | frames | JPEG b4 (`v0-baseline`) | **JPEG b2 (matched)** | PNG b2 | PNG − JPEG b2 |
|---|---|---|---|---|---|
| indoor-c (in domain) | 1,166 | 0.767 / 0.573 | **0.753 / 0.558** | 0.782 / 0.567 | +0.029 / +0.009 |
| indoor-v2 (gold session, auto labels) | 268 | 0.766 / 0.547 | **0.773 / 0.571** | 0.769 / 0.545 | −0.004 / −0.026 |
| **054429 (domain shift)** | 1,077 | 0.484 / 0.384 | **0.710 / 0.608** | 0.704 / 0.584 | **−0.006 / −0.024** |

Values are mAP50 / mAP50-95. On 054429, the matched JPEG run scores monster 0.519 / 0.396 and NPC
0.901 / 0.819 (AP50 / AP); PNG scores 0.515 / 0.389 and 0.894 / 0.779.

**The gold set** (model vs hand, conf 0.25, IoU ≥ 0.5):

| | P | R | mean IoU | monster TP / FP / FN | npc TP / FP / FN |
|---|---|---|---|---|---|
| JPEG b2 (matched) | 0.712 | 0.643 | 0.828 | 52 / 33 / 48 | 47 / 7 / 7 |
| PNG b2 | 0.715 | 0.669 | 0.816 | 56 / 35 / 44 | 47 / 6 / 7 |

**Reading:**
1. **The domain-shift gain was the BATCH SIZE, not the format.** JPEG at batch 2 scores 0.710 on
   054429, against PNG's 0.704; JPEG at batch 4 scored 0.484. "Reading 2" above is therefore
   ATTRIBUTED: the format did not cause it.
2. In domain, the two formats tie again (within ±0.03 mAP50, and the sign flips between sessions).
3. On the gold set, PNG finds 4 more monsters (recall 0.56 vs 0.52) at the same precision. That is
   one run each, with no seed variance, and 4 boxes of 100: not separable from noise.
4. **Storage (Batt's call, PARKED):** with this run, PNG's ~5× storage shows no measurable detection
   gain. v1 stays on PNG as its pre-registration fixes (`v1-vs-v0png.md`, not moved after seeing
   data). Whether LATER caches go back to JPEG is Batt's decision.

## Open (Batt's call)
- ➡️ **ANSWERED 2026-10-08 by the matched-batch rerun (above): the 054429 gain was the batch size.**
  The original open item:
- **Attribution:** one matched-batch run, e.g. PNG at batch 4 in a night window (≈ 4–5 h) or JPEG
  at batch 2. It shows whether the 054429 gain is the format.
- v1 stays blocked on M4, as before.
