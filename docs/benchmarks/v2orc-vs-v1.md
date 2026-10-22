---
doc_type: design
hypothesis: "A per-species detector trained on v1's data plus orcsdun01 warp-and-watch blocks finds orcsdun01's species and does not lose prt_fild08 (v1's gold set and held-out set no worse than v1)."
status: PRE-REGISTERED 2026-10-21 (BEFORE any v2orc model exists; amendments only before training starts, clock-labelled)
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../planning/orcsdun01-detector.md, v1-vs-v0png.md, ../planning/labels-v2-plan.md, ../operations/vision-long-lived.md]
next_action: "Pass the plan's 3f TRAINING tier (C1 pooled on col1 <= 5 %, every orcsdun01 species passing blind round 3), build the combined cache, then train (train-day.sh, WORKER=1, MID_CKPT=1) and score ONCE as written here, with Amendment A's P1."
---

# v2orc vs v1: per-species classes + orcsdun01, without forgetting prt_fild08 (pre-registered 2026-10-21)

Batt's order, item 6 (2026-10-21 ~09:1x): "EVALUATION, pre-registered before training: per-species
recall/precision on held-out orcsdun01 sessions; prt_fild08 gold set and held-out sessions must
not get worse than v1 (and Creamy recall reported); latency per frame on GPU vs CPU."

This file is written and committed BEFORE any v2orc model exists. It is scored once, as written.

## Amendment A (2026-10-22, before any training; the clock time is the commit time of `../planning/orcsdun01-detector.md` 3f's first commit)

Batt (2026-10-22 ~19:4x): "two tiers: TRAINING at C1 <= 5 % with every species passing the blind
check; EVALUATION only on crops both blind labellers judged good (col2 stays TEST)". The plan's
3f makes this operational. Two lines below change; nothing else does.
- **The labels row:** orcsdun01 labels train only if 3f's TRAINING tier passes:
  - C1 pooled on col1 <= 5 %;
  - every orcsdun01 species passes the blind check, round 3.
  - It replaces "used ONLY if the camera check and the blind label check pass for that species".
  - The orcsdun01 TRAIN data: col1, col3 and the 2026-10-22 sessions 3f admits. col2 stays TEST.
- **P1:** counted only on col2 crops that BOTH blind labellers of a post-training evaluation pack
  judged good with the right species (3f's EVALUATION tier: seed 3, up to 60 crops per species,
  recall and precision as 3f defines them).
  - The bar is unchanged (>= 0.80 each, for a species with >= 50 evaluated crops).
  - It replaces "The labels are the same packet labels the training used".

## The model and the data (fixed now)

| | v1 (`v1png-20261008`, the live CPU detector) | v2orc (to train) |
|---|---|---|
| classes | player, monster, npc | the plan's section 4: player 0, npc 1, warp 2, then one class per monster species: 1002 1063 1008 1113 1018 1005 1042 1082 1084 1111 1152 1153 (`config/detector/classes-v2orc.json`) |
| data | v1's sessions, v1 labels | v1's train / val sessions RE-LABELLED per species (the same frames, `--every` and split) + the orcsdun01 TRAIN blocks |
| orcsdun01 split | - | **TEST = the block labelled `col2`, all of it, held out.** TRAIN = every other orcsdun01 block recorded before training starts. VAL = v1's val sessions only (val monitors training; it decides nothing) |
| labels | v1 (`predict_sprite`, k 0.140) | the same labeller, per-species classes. orcsdun01 labels are used ONLY if the camera check (plan section 3) and the blind label check (plan section 5) pass for that species. ➡️ AMENDED (Amendment A, 2026-10-22): the plan's 3f TRAINING tier decides |
| model, epochs, seed, imgsz | YOLO11n, 30, 20261004, 1280 | the same (from the same COCO YOLO11n weights; the head has more classes) |
| batch / workers | 2 / 1 | 2 / 1. If the hunt's CPU detector slows while training, the loader is niced or its workers lowered; any change is recorded |
| image format | PNG | the v1 sessions' frames as v1's cache (PNG); the orcsdun01 frames as recorded (JPEG q80); stated, not a variable here |

- **Honest limit of the orcsdun01 test:** col2 is a different time with a fresh population, because
  `dynamic_mobs` respawns everything at each entry. But it uses the same 97 stands, so the
  backgrounds were seen in training. It measures held-out MONSTERS, not held-out places.
- **Familiar (1005) and Drainliar (1111)** differ only by a tint. The augmentations stay v1's
  (ultralytics' defaults; `train.py` exposes none). Its hue jitter, `hsv_h` 0.015, shifts hue by
  at most ~5 degrees, far less than Drainliar's (250, 69, 96) tint. Their confusion is reported.

## The scores (fixed now)

**P1, orcsdun01 per species**, on col2 (the weights are `last.pt` at epoch 30, conf 0.25):
- Scored by `label_iou`'s POSITION scorer (v1's primary, `gold_eval.py score --metric position`):
  the centre falls in the label box, the class matches, and pairs are one-to-one. The labels are
  the same packet labels the training used. ➡️ AMENDED (Amendment A, 2026-10-22): only the col2
  crops both blind labellers judged good count.
- **The bar, for each species with >= 50 labels in col2: recall >= 0.80 AND precision >= 0.80.**
- A species with fewer labels is reported, with no bar.

**G1, v1's gold set:** Batt's 27 hand-checked frames of `20261004T103815-console-s2-indoor-v2`
(prt_church, spawned Porings; 100 monster boxes).
- Monster classes are collapsed to `monster`. The position metric is used.
- **Bar: P >= 0.882 AND R >= 0.810** (v1 PyTorch: 0.902 / 0.830, minus 0.02).

**G2, v1's prt_fild08 held-out set:** `20261004T054429-console-s2-outdoor` (natural spawns: Poring,
Lunatic, Pupa, 1 Creamy), on v1's test labels collapsed to `monster`.
- **Bar: monster recall and precision (position) each >= v1's on the same frames - 0.02.** v1 is
  re-scored first with the same command, so like is compared with like.

**Reported, deciding nothing:**
- per-species IoU >= 0.5 precision / recall and mAP50 on col2;
- the confusion between 1005 and 1111;
- **Creamy (1018) recall:** on 054429, and on v52's hunt recordings (prt_fild08 natural spawns,
  never trained on), if the labeller reads them before the score;
- npc / player numbers;
- **latency per frame at imgsz 1280:**
  - GPU: PyTorch in the vision worker, the 25 % VRAM cap;
  - CPU: ONNX with the live pipeline's settings, nice 10;
  - p50 / p95 over the same 200 frames, v1 beside.

**The verdict:**
- **v2orc PASSES if P1 holds for every species with a bar, and G1 and G2 hold.**
- Passing does NOT switch the live detector. That is Batt's separate decision (his item 7).
- If G1 or G2 fails, v2orc forgot prt_fild08: reported with the per-class numbers.

## The run (plan)

1. **The labels:**
   - the camera check on col1 (the plan's section 3 bars);
   - the blind check on every species' sample (the plan's section 5 bars);
   - a species that fails is excluded from training and from P1, and is reported.
2. **The cache** (`build_frame_cache.py`, the per-species classes; outside 09:30-10:15 /
   14:00-14:45; shards on the NAS, read back):
   - v1's sessions and split, re-labelled;
   - plus the orcsdun01 blocks.
   - Reported: the frames and boxes per class.
3. **The training** (`scripts/runbooks/train-day.sh`, WORKER=1, MID_CKPT=1): through guarded_build,
   with R1-R3, the IO guard, the 25 % VRAM cap and the quiet launcher.
   - The hunt's `det_fps` / latency is measured before and during training.
4. **The scoring:** once, after epoch 30, with the commands above. The results are added below this
   line, with nothing above it edited.
