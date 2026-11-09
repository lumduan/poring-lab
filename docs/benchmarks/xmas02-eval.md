---
doc_type: design
hypothesis: "A detector scoped to xmas_dun02, trained on immune lattice watches labelled under the frozen xmas02 rule (o3h or o3h-t), finds the map's four common species on held-out TEST data (Q1c: recall and precision >= 0.80 per species with >= 50 evaluated crops, classes collapsed) and boxes the runner's own patrol frames with precision >= 0.80 on still captures (P4A), where v1 saw 1 of 937 labels."
status: "SCORED 2026-11-07 00:39 ICT: THE xmas02 MODEL PASSES (Q1c: all four tier species, recall 0.98-1.00, precision 0.87-0.88; P4A still precision 0.946 on 728 detections). Pre-registered 2026-11-06; Amendments 2 and 3 before the cache and before any TEST read."
role: null
verdict_date: 2026-11-07
verdict_ticket: null
supersedes: null
related: [../planning/xmas02-detector.md, gef10-eval.md, payf07-eval.md, v2orc-vs-v1.md, ../planning/rogue-xmas02.md]
next_action: "Batt decides whether to deploy it on xmas_dun02 (plan T-11: a model per map, species collapsed to monster; the double cookie boxes suggest class-agnostic NMS). Nothing switches the live detector until then."
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

## AMENDMENT 2 (2026-11-06 18:1x ICT, before the cache): the run's fixed inputs

As "The run" step 1 requires, before the cache:
- **The class list:** `config/detector/classes-xmas02.json`, sha256 `9ab96672cd9d2b822c45b87c7f903c04900e304f0466018a7bbdfcdfc4e491be`:
  0 player, 1 npc, 2 warp (empty), **3 Myst Case 1249, 4 Cruiser 1248, 5 Cookie 1265, 6 Christmas
  Cookie 1246** (T2 passed the four; Garm Baby and the Christmas Goblin failed T2 and are not
  classes: plan Amendment H). The model table's "0 player, 1 Myst Case ..." reads with the ids
  shifted by 2. **The tier species with a bar (Q1c) are these four**; no `cookie_any`.
- **The frozen label params:** `xmas02-o3h-t`, params.json sha256
  `d4cc0a5d9e530e382e31ea9c9ae1fc1087dd31c37577b43b307eff65994fdb6e` (plan Amendment G: 1d 120 ms,
  o3h-t, T_h 0.536, E0).
- **TRAIN (admitted by 3c):** `20261106T151122-rdp-xmas02-xw2`, `20261106T154241-rdp-xmas02-xw3`,
  `20261106T160700-rdp-xmas02-xw3`. **VAL (monitor only, D13):** `20261106T115507-rdp-xmas02-xw1`,
  `20261106T144500-rdp-xmas02-xw1`.
- **TEST:** `20261106T162044-rdp-xmas02-xw5` (xw5), `20261106T171533-rdp-xmas02-xp1` (xp1),
  `20261105T225409-rdp-xmas02-x2` (X2). T1 read them once (plan section 12: PASS); nothing else
  reads them before the training ends.

## AMENDMENT 3 (2026-11-07 00:1x ICT, after the training ended and BEFORE any TEST label, pack, prediction or score): the scored checkpoint, the P4A split, the commands

**The training ended normally:** Amendment I's launch (xmas02-detector.md) ran 20:53:17-00:01:51
ICT, rc 0, ONE attempt (no IO restart), **all 20 epochs completed**. Duty cycle: 100 ms for
7,456 s, 200 ms 2,047 s, 400 ms 652 s, 800 ms 607 s, 2,000 ms 546 s (82 changes). The guard's
worst capture stall 9.9 % (cron.service), 0 s above 30 %.
- **The scored checkpoint:** `data/train/xmas02-20261106/weights/last.pt` after epoch 20, sha256
  `5c5bb67a746b42014935700f449ecbf45525bbddf250fb21738eb6248a2b8b7b` (the plan's rule: the last
  completed epoch; nothing ended early).
- VAL (xw1, monitor only, D13; it decides nothing) at epoch 20: P 0.979, R 0.978, mAP50 0.993,
  mAP50-95 0.910.
- **The CPU export** (for P4A and the latency; detector-cpu.md's recipe, imgsz (736, 1280),
  simplify, device cpu): the worker image has no `onnx`, so the export ran in a TEMPORARY RAM env
  (`/dev/shm/poring-lab-tmp/onnx-export`, ultralytics 8.4.165 as the recipe; removed after the
  export). `/dev/shm/poring-lab-detector/model/xmas02-last-736x1280.onnx` sha256 `293dca92...`, and
  `.names.json` (the .pt's names in id order: player, npc, warp, mystcase, cruiser, cookie,
  cookie_xmas) sha256 `af86aacc...`.

**P4A's "still" precision, built (the scorer had the still / moving split for RECALL only).**
`detector_vs_packets.py score-session` now also writes `precision_by_self_motion` (moving /
still: detections, tp, precision), counted from the SAME verdicts as `precision`, after the UI
drop, on the same 500 ms rule (`SELF_MOVE_NS`). Nothing else in the output changes.
- **Positive case (a REAL session, before any new-model box exists):** v1's X2 rows of 2026-11-06
  (x2-score.json) re-scored by the new code: every published field is IDENTICAL (precision 1 / 66,
  each species' recall, the 4A verdict), and the new split is moving 1 / 40 + still 0 / 26 = 1 / 66,
  equal to a count straight from the `--pairs` file.
- **P4A** = (X2 still tp + xp1 still tp) / (X2 still detections + xp1 still detections), the new
  model's rows, `--classes config/detector/classes-xmas02.json` with the export's names; >= 100
  pooled still detections, else NO VERDICT.

**The commands** (gef10-eval.md R2-2's, with this map's flags). Variables:

      W=/home/batt/docker/poring-lab; F=/dev/shm/poring-lab-tmp/xmas-det/fit
      T=/dev/shm/poring-lab-tmp/xmas-det/eval; E=$W/data/train/eval/xmas02
      M=/dev/shm/poring-lab-detector/model; N=/mnt/poring-lab-datasets
      CAP="systemd-run --user --scope -q -p MemoryMax=4G -p MemorySwapMax=0"
      GB="python3 scripts/guarded_build.py --threshold 30 --sustain 30"

1. **The TEST labels**, one part per run, nice 19: `--classes` is the TRAIN labels' file
   (`classes-none.json`, "the same rule the TRAIN labels were cached under"); the T_h floor is part
   of the rule (4a), so the pack takes no `--min-fit` (as T2's pack, `min_fit` null):

        $CAP nice -n 19 uv run python scripts/map_labels.py labels --map xmas_dun02 --eval-test \
            $N/<part> --params $F/params.json --classes $F/classes-none.json --out $T/labels-test/<part>.json
        # parts: 20261106T162044-rdp-xmas02-xw5, 20261106T171533-rdp-xmas02-xp1, 20261105T225409-rdp-xmas02-x2

2. **The pack**, seed 53, 60 per species (fewer: all), T2's instructions (sha256 `dc48fb15...`):

        $CAP nice -n 10 uv run python scripts/map_labels.py pack --map xmas_dun02 --eval-test $T/labels-test/*.json \
            --per-species 60 --seed 53 --pack-dir $T/pack --key-dir $T/key \
            --instructions docs/planning/xmas02-blind-instructions.txt \
            --instructions-sha256 dc48fb1582300e704ac333497d7681b051c3448a5e0d17d42f17b0322bac48ed

   **Two NEW blind labeller agents (C, D)**, each given ONLY the pack directory, the instructions
   file inside it and its own answers path (`$T/answers/C.json`, `D.json`); the key directory is
   never named to them; T2's brief otherwise.
3. **The refs** (the pack's frames + the 200 latency frames, seed 53), read in place from the NAS:

        $CAP uv run python scripts/eval_q1.py refs $T/key/answer_key.json --out $E/q1-refs.json \
            --latency-200 53 --latency-out $E/latency-200-refs.json --labels-dir $T/labels-test

4. **The Q1 detections** (the worker; R1-R3; imgsz 1280, conf 0.25 = predict_dir's defaults):

        $GB "execdev:vision@1800=python -m poring_vision.predict_dir --weights /data/train/xmas02-20261106/weights/last.pt \
            --refs /data/train/eval/xmas02/q1-refs.json --out /data/train/eval/xmas02/q1-pred-xmas02.json"

5. **Q1c / Q1s** after both labellers:

        uv run python scripts/eval_q1.py score $T/key/answer_key.json $T/answers/C.json $T/answers/D.json \
            $E/q1-pred-xmas02.json --cache-manifest $N/.framecache/xmas02-o3h-t-20261106/manifest.json --out $E/q1-score.json

6. **P4A** (the CPU path, UnitDetector, nice 10, 8 threads), X2 and xp1, then one score each:

        $CAP nice -n 10 uv run python scripts/recorder_boxes.py predict $N/<session> \
            --model $M/xmas02-last-736x1280.onnx --threads 8 --out $E/p4a-<x2|xp1>-xmas02-boxes.jsonl
        $CAP nice -n 19 uv run python scripts/detector_vs_packets.py score-session $N/<session> \
            --boxes $E/p4a-<x2|xp1>-xmas02-boxes.jsonl --map xmas_dun02 --layout hunt --chat auto --ui-boxes drop \
            --classes config/detector/classes-xmas02.json --names $M/xmas02-last-736x1280.names.json \
            --sprites "$X1/sprites/data/sprite/몬스터" --sprite-names $X1/kb-sprites/monster_sprite_names.json \
            --pairs $E/p4a-<x2|xp1>-xmas02-pairs.json --out $E/p4a-<x2|xp1>-xmas02.json
        # X1=$N/scratch-archive/2026-11-05/x1 (X2's own sprite inputs). v1 beside it: X2 = the 11-06
        # rows re-scored above; xp1 = the same two commands with $M/v1png-last-736x1280.onnx, no --classes.

7. **The 30 false boxes by eye:** every still capture's non-tp verdict in the two new-model pairs
   files, listed as (session, t, detection index) in sorted order, `random.Random(53).sample(.., 30)`
   (all, if fewer), each drawn on its frame and judged: toy model, terrain, UI, our own character,
   a real monster the truth missed, other.
8. **CPU latency** (the 200 refs, interleaved, nice 10):

        nice -n 10 uv run python scripts/eval_latency.py $E/latency-200-refs.json \
            --model v1=$M/v1png-last-736x1280.onnx --model xmas02=$M/xmas02-last-736x1280.onnx --out $E/latency-cpu.json

9. **G1 / G2** (information only, D1): gef10-eval.md's commands 5-6 with this model's `last.pt`;
   v1's G1 file is the gold set's `pred-v1png-20261008.json`; v1's G2 file is gef10-r2's
   `g2-pred-v1.json` if `gold_eval.py refs` writes byte-identical refs, else v1 is predicted again.
10. Then `worker-stop:vision` (verified), and the results below.

## AMENDMENT 4 (2026-11-09 22:1x ICT, before the GPU step): a second model, xmas02-gb (Garm Baby)

Everything above and the RESULTS below are about the DEPLOYED xmas02 model (4 species,
`classes-xmas02.json`) and stay as they are. A second model with an 8th class, Garm Baby 1515
(Batt 2026-11-09), is trained from it: its data, class file (`classes-xmas02-gb.json`), cache
(`xmas02-gb-o3h-t-20261109`), launch and post-training commands, and its bars (Garm Baby Q1 on the
held-out watch gw3; the four species' Q1 on xw5; CPU p95 <= 300 ms) are in
[xmas02-detector.md](../planning/xmas02-detector.md) Amendment M (M4-M6). Its results go there or
below, labelled `xmas02-gb`; nothing here is re-scored.

➡️ **RESULT (2026-11-10 06:43-06:48 ICT): xmas02-gb PASSES** -- Garm Baby Q1s on gw3 (59 evaluated
crops of 24 dogs, recall 1.000, precision 0.922), the four species' Q1c on POOLED TEST (M7 point 4:
recall 0.98-1.00, precision 0.93-0.94) and the CPU p95 RELATIVE to the deployed model on bot-server
(M10: 734.6 vs 769.3 ms, 0.955 <= 1.10). The bars as amended (M7, M10) and the full result:
[xmas02-detector.md](../planning/xmas02-detector.md) M11. Not deployed: Batt's decision.

## RESULTS

### VERDICT (2026-11-07 00:39 ICT): THE xmas02 MODEL PASSES -- Q1c holds for all four tier species and P4A holds

| bar | result | pass |
|---|---|---|
| Q1c Myst Case (>= 50 evaluated: recall >= 0.80 AND precision >= 0.80) | 59 evaluated, recall 1.000, precision 0.881 | YES |
| Q1c Cruiser | 56, recall 0.982, precision 0.873 | YES |
| Q1c Cookie | 60, recall 0.983, precision 0.881 | YES |
| Q1c Christmas Cookie | 58, recall 0.983, precision 0.877 | YES |
| P4A (X2 + xp1 still captures: precision >= 0.80 with >= 100 detections) | 689 / 728 = 0.946 | YES |

- **Passing does NOT switch the live detector** (above): deploying it on xmas_dun02 (plan T-11, the
  species collapsed to `monster` for the runner) is Batt's decision.
- Scored ONCE, with Amendment 3's commands. Two differences from them, both before any score:
  - `map_labels.py pack` needs `--out` (gef10's had it; the amendment left it out): the first
    call stopped on the argument error before reading anything; rerun with `--out $T/pack-build.json`.
  - The pairs file now carries the kept boxes its verdicts index (e787b01, 00:18:25, output only;
    v1's X2 re-score stayed identical), so step 7's draw could find the boxes.

### The inputs as made
- **TEST labels** (00:15:08-00:25:14, nice 19, `eval_test: true`, params `d4cc0a5d...` FROZEN):
  xw5 1,147 kept (Christmas Cookie 127, Cruiser 440, Myst Case 285, Cookie 295; Garm Baby and the
  Goblin 0), xp1 and X2 after it.
- **The pack** (00:26:34, seed 53, salt xmas02, 60 per species): 240 crops, pools Myst Case 402,
  Cruiser 534, Cookie 358, Christmas Cookie 290 (no other species had a kept TEST label); 12 grids;
  the 9-letter multi-view reference. sha256: pack.json `46c13024...`, answer_key.json `fc9facb1...`,
  reference.png `2cae63ad...`, instructions.txt `dc48fb15...` (T2's, byte-identical). The pack was
  copied (sha256-checked) to `/dev/shm/poring-lab-tmp/blind-eval53/pack`, away from the key.
- **Two NEW blind labellers C and D** (00:26:5x-00:33), each given only the pack, its instructions
  and its answers path. C: q1 yes 240; q2 good 233, off 7. D: q1 yes 240; q2 good 237, loose 1, off
  2. Neither marked any box as a toy model. Answers sha256 C `01808a2b...`, D `9c3817ba...` (in the
  scorer's fields A, B). Scored as given; D's note that two of its "good" hat cases could be "off"
  was not acted on (blind protocol).
- **Evaluated** (both: yes / good / the label's species): 233 of 240 (C's q2 not good 7, D's 3).
- **The Q1 detections** (00:27:38-00:28:20, the worker; 231 frames; imgsz 1280, conf 0.25):
  `q1-pred-xmas02.json` sha256 `99ee7e1a...`. The worker was stopped at 00:28:41 (verified: exited,
  nothing of ours on the GPU).

### Q1c (VERDICT) and Q1s (reported)
- **Q1c pooled:** 233 evaluated, 230 matched (recall 0.987), precision 0.966.
- **Q1c's precision is lower than each species' recall because of 8 DOUBLE BOXES:** all 8 unmatched
  detections inside the evaluated boxes are a `cookie` + `cookie_xmas` pair on ONE sprite (IoU > 0.5;
  ultralytics' NMS is per class). Under Amendment 1's literal field every species' frame set counts
  them. `precision_own_boxes`: Myst Case 0.983, Cruiser 1.000, Cookie 1.000, Christmas Cookie 0.891.
- **Q1s (the classes agreeing):** Myst Case 59 / 59 (precision 0.983), Cruiser 55 / 56 (0.982),
  Cookie 58 / 60 (0.879), Christmas Cookie 56 / 58 (1.000): every bar passes.
- **The Cookie / Christmas Cookie confusion** (evaluated crops, the class each was seen as):
  Cookie -> cookie 58, cruiser 1, none 1; Christmas Cookie -> cookie_xmas 51, **cookie 5**, mystcase
  1, none 1. Cruiser -> cruiser 55, none 1. Myst Case -> mystcase 59.
- **By TEST part** (Q1c: evaluated, recall, precision): xw5 Myst Case 41 / 1.000 / 0.891, Cruiser
  45 / 0.978 / 0.898, Cookie 51 / 0.980 / 0.909, Christmas Cookie 25 / 1.000 / 0.833; X2 17 / 1.000 /
  0.895, 9 / 1.000 / 0.818, 8 / 1.000 / 0.800, 27 / 0.963 / 0.929; xp1 1, 2, 1 and 6 crops (recall
  1.000 each; too few to read).
- **Under a model or terrain vs clear** (Q1s; the scorer splits Q1 only): under -- Myst Case 8 / 8,
  Cruiser 13 / 13, Cookie 12 / 12 (precision 0.80), Christmas Cookie 11 / 11; clear -- 51 / 51,
  42 / 43, 46 / 48, 45 / 47.

### P4A (VERDICT): the runner's view on the patrol TEST (X2 + xp1), the CPU path
The new model's rows (`recorder_boxes.py predict`, UnitDetector, 8 threads, nice 10), scored by
4A's rule with 4J's readings (`--classes classes-xmas02.json`, UI boxes dropped, the session's
chat window).

| | X2 new | X2 v1 | xp1 new | xp1 v1 |
|---|---|---|---|---|
| captures scored | 1,159 | 1,159 | 1,232 | 1,232 |
| **still precision** | **489 / 511 = 0.957** | 0 / 26 | **200 / 217 = 0.922** | 0 / 37 |
| moving precision | 81 / 369 = 0.220 | 1 / 40 | 103 / 474 = 0.217 | 1 / 93 |
| all-captures precision | 570 / 880 = 0.648 | 1 / 66 | 303 / 691 = 0.438 | 1 / 130 |
| still recall | 482 / 558 = 0.864 | 0 / 558 | 198 / 265 = 0.747 | 0 / 265 |
| moving recall | 79 / 379 = 0.208 | 1 / 379 | 102 / 505 = 0.202 | 1 / 505 |
| first sightings detected | 77 / 94 (median 0.97 s, p90 3.0 s) | 1 / 94 | 85 / 111 (1.02 s, p90 4.0 s) | 1 / 111 |
| monster in view, no detection at all | 57 / 604 captures | 569 / 604 | 47 / 482 | 442 / 482 |
| UnitDetector ms per frame (p50 / p95) | 235 / 374 | (11-06: 2 threads) | 226 / 281 | 221 / 262 |

- **P4A pooled still: 689 / 728 = 0.946 (>= 100 detections): PASS.**
- **What the moving captures show:** the precision falls from ~0.94 to ~0.22 and the recall to
  ~0.21 when we moved in the 500 ms before the capture. That is the truth's displacement the plan
  named (frames lag the server ~0.5 s: memory frames-lag-server-half-second), not the detector:
  the same boxes on still captures are right 94.6 % of the time. A moving truth needs the lag
  model before it can score anything.
- **X2's and xp1's 4A bar (reported, not a gate): FAIL for both models.** New model, recall per
  species on all captures: X2 Myst Case 0.578, Cruiser 0.538, Cookie 0.477, Christmas Cookie 0.797;
  xp1 0.363, 0.521, 0.250, 0.363 (precision 0.648 / 0.438). v1: 0.000-0.005 everywhere.
- **The 30 false still boxes by eye** (step 7; the pool is all 39 = 728 - 689; seed 53; X2 15, xp1
  15; the scorer's verdicts: 15 near a unit, 14 elsewhere, 1 on a dying unit):
  - **23 sit on a REAL monster** the packet truth put >= 16 px away or did not have: Cookies,
    Christmas Cookies, Cruisers (the toy soldiers with a sword and a tall hat), a Myst Case on a
    belt, two in a fight with our Rogue;
  - **4 on scenery toys:** the stacked red figures (twice, X2 at the same spot), a pile of presents,
    a seated toy robot;
  - **3 unsure:** our own Rogue behind a potted plant (its HP / SP bar shows), a sprite cut by the
    frame's bottom edge, a gift box behind a raised block (a Myst Case or a scenery present).
  - So most of P4A's 5.4 % "false" boxes are truth misses; the scenery share is about 4 in 30.
- **Double boxes on the CPU path too:** cookie + cookie_xmas pairs (IoU > 0.5) on one sprite, X2
  13 of 964 monster boxes, xp1 6 of 716. Collapsing the species BEFORE the NMS (class-agnostic)
  would remove them for the runner; that is a deployment detail, decided by nobody yet.

### CPU latency (reported; the runner needs p95 <= v1's x 1.10)
- The 200 TEST frames (seed 53), UnitDetector, 8 threads, nice 10, interleaved (00:37:31-00:39:26,
  load average ~12-16): **v1 p50 228.0 / p95 272.9 ms; xmas02 p50 230.5 / p95 270.0 ms. 270.0 <=
  300.2: YES.** Boxes on these frames: v1 59, xmas02 540.

### G1 / G2 (information only, D1: the model is map-scoped and never runs on prt_fild08)
- **G1** (the 27 indoor gold frames, position metric, species collapsed): v1 monster 83 tp / 9 fp /
  17 fn (P 0.902, R 0.830, as published); **xmas02 0 / 28 / 100 (P 0.000, R 0.000)** and npc 0 / 54.
- **G2** (1,077 cached v1 frames; refs byte-identical to round 2's, so v1's file is round 2's and
  its score reproduces round 2's exactly): v1 monster P 0.718 / R 0.714; **xmas02 P 0.147 / R
  0.072.** Under the alternative (a single model everywhere) both would fail; the map-scoped plan
  (D1) never asks it to.

### Where the outputs live
- `data/train/eval/xmas02/` (local, 2.8 MB): q1-refs, q1-pred, q1-score, latency-200-refs,
  latency-cpu, the P4A boxes / pairs / scores (new and v1), g1 / g2 predictions and scores.
- `/dev/shm/poring-lab-tmp/xmas-det/eval/` (labels-test, pack, key, fp30, logs) and
  `/dev/shm/poring-lab-tmp/blind-eval53/` (the pack copy, answers C / D): to the NAS
  `scratch-archive/2026-11-07/` today (rule 7).
- The run `data/train/xmas02-20261106/` (the scored last.pt) and the eval folder: to the NAS
  `archive/train/` by a guarded `archive:` step, as gef10's.
