---
doc_type: design
hypothesis: "v1's automatic labels differ from Batt's hand-checked gold set in a few systematic, measurable ways, and each can be named, counted and given a label fix that is measured without tuning on the gold set."
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../benchmarks/v1b-vs-v1.md, ../benchmarks/v1-vs-v0png.md, ../phase3-plan.md, labels-v2-plan.md]
next_action: "Batt: choose which fixes of section 6 go into the next training (G1 first: exclude dead-GM frames, as labels v2 already does). Nothing has been changed, trained or run."
title: "Label quality: the auto-labels against Batt's gold convention, gap by gap"
date: 2026-10-13
owner: Batt
extends: docs/benchmarks/v1b-vs-v1.md
gate: "OFFLINE analysis only (Batt 2026-10-13, decision 11). No label was changed, nothing was trained, no model was run (existing gold-set prediction files were read). Every fix in section 6 is a PROPOSAL with a pre-registration sketch. The gold set judges; it never tunes: the what-ifs in section 5 are measured ON it and are upper bounds."
---

# Label quality: the auto-labels against Batt's gold convention

**Batt (2026-10-13, decision 11):** "Next training: fix LABEL QUALITY toward my gold convention
(compare auto-label boxes vs gold, find the systematic gaps) before labels v2; no more epochs on v1."

**Why:** v1b (v1 + 20 epochs) beat v1 against v1's own AUTOMATIC test labels, but lost to it on Batt's
hand-checked gold set ([v1b-vs-v1.md](../benchmarks/v1b-vs-v1.md)). So the auto-labels and the person
disagree somewhere, systematically. This doc finds where, and by how much.

All numbers come from `scripts/label_quality.py` (section 8 reproduces them). Its outputs are
client-derived and stay in /dev/shm.

## 0. The answer in short

**Ranked by what each gap costs on the gold set's POSITION metric (monsters) and how much of the
training data it touches.** The what-ifs (section 5) are in-sample upper bounds.

| # | gap | the v1 LABELS on gold (26 position errors: 17 FN + 9 FP) | the trained MODELS on gold | training frames touched (1 s grid, 3,795) | proposed fix |
|---|---|---|---|---|---|
| G1 | **a dead GM whose position the packets got wrong:** for the rest of the span every label sits ~4 cells off its unit | none (the gold's dead frames are not affected) | **all 7 detectors scored (v0 to v1b, ONNX included) find at most 1 of the 12 monsters in the 2 dead-GM gold frames and draw 8-10 boxes ~(+95..+100, -96..-101) px away** | indoor-b: 608 frames (16 %), every label displaced | exclude dead-GM frames (labels v2's `self_dead` already does) |
| G2 | **our own walk: the camera lags the packets** by ~100-125 ms, so the whole frame's labels shift | **16 of 26** (8 FN + 8 FP, 2 frames); NPCs 8 of 8 | v1 misses 0, v1b 2 | 157 frames (4.1 %) shifted > 20 px | delay OUR position only, by a constant measured WITHOUT the gold set |
| G3 | **the UI-window rule drops visible units:** the chat window is translucent; prt_church draws no minimap; the small top window is not where the rule has it | **7 FN** (chat 4, minimap 2, top window 1) | **every detector misses the chat unit of frame 240; v1b and the v0 models also miss the chat unit of frame 180 and the top-window unit of frame 260** (v1 and v1-ONNX find those two); none misses the minimap ones | chat 629 units in 543 frames (14 %); minimap 121; top window 29; notifier 93 | a measured UI layout per session; the chat window translucent except its input bar |
| G4 | **the edge rule:** a unit less than half on screen gets no box; a person boxes its visible part | 1 FN | none | 567 units in 491 frames (13 %) | box the visible part, with a minimum visible size |
| G5 | **box size (the IoU metric only):** v1 boxes are 1.34 x wider and 1.45 x taller than the gold's 44 x 40 | no position error; **48 of the IoU metric's 110 errors** | (not measured) | every monster box | write the box convention first (§5f), then label to it |

**Measured and NOT a gap:** a projection or k error (Batt's own placements show no position or depth
dependence, R^2 <= 0.02); the vertical and horizontal anchor (correcting either by Batt's moved boxes
loses 2 or gains 1 position error, and costs IoU); the walk envelope's high centre (it is right for position: replacing it costs 12
position errors). One species only (Poring, 1002): per-species size is not measurable on this set.

**The largest finding is G1, and it is in the TRAINING data, not in the gold set.** In the training
session indoor-b our GM lay dead from 586 s to the end of the recording (608 of its 1,161 grid frames,
52 %), and for that whole span the labels sit about 4 cells from the units (looked at on two decoded
frames, 700 s and 1,150 s). Every detector trained on it learned to put boxes on the empty floor under
the restart window: on the gold set's 2 dead-GM frames, v0-baseline, v0-JPEG, v0-PNG, v1, v1-ONNX and v1b find **none** of the 12 monsters (v0-ONNX
finds 1). On the 25 other gold frames v1 scores **83 / 1 / 5 (P 0.988, R 0.943)**, the live v1-ONNX
**83 / 0 / 5**, v1b 79 / 0 / 9.

**v1b against v1 (decision 11's question), box by box (section 4.8):** v1b's 4 fewer hits are NOT in the
dead-GM frames. It misses 6 units v1 finds, all on alive frames, and 4 of the 6 are units the training
labels get wrong: frame 180's 2 units shifted by our own walk (G2) and its chat-window unit (G3), and the
top-window unit of frame 260 (G3). It finds 2 that v1 misses. Most of what the extra epochs lost (4 of 6
units) is where the labels are systematically wrong; a small sample, one run each.

## 1. What was compared

- **The gold set:** Batt's hand check of `20261004T103815-console-s2-indoor-v2` (27 frames, 100 monster
  and 54 NPC boxes, all on prt_church; `data/qa/handcheck/<session>.json`, sha256 `e3e68082...6aa0`).
- **The /qa bundle Batt edited** (`services/frontend/.qa-local/<session>/labels.json`, the v0 labels
  of 2026-10-04 11:41): each hand box is classified by what he did to the box he was shown.
- **The auto-labels:** v0 and v1 (k = 0.140) from `qa_export.Labeler`, the labeller build_frame_cache
  used, at the same packet->frame offset (113.9 ms).
- **The reproduction is proven three ways:**
  - the v1 labels reproduced for the 27 frames equal the v1png cache's own YOLO txt (shard 46): **27 of
    27 frames**, largest edge difference 0.0009 px; the same check on the v0 labels: **0 of 27** (it can
    fail);
  - `relabel()`, which re-derives a frame's labels from the dumped unit facts (the what-ifs turn its
    knobs), returns all 27 gold frames unchanged for v0 and v1, and all 7,252 census frames for v1;
  - `score()` reproduces label_iou's numbers exactly (section 3 = phase3-plan §5e / §5f), and is pinned
    equal to label_iou on random boxes in the tests.
- **The census** (section 4.7): the v1png cache's 10 sessions on a 1 s grid between each recording's t0
  and t1, with build_frame_cache's own skips (GM-command windows, off-scene maps). The cache keeps ~2
  frames a second of the H.264 sessions and every frame of the PNG ones, evenly spread, so the SHARES carry
  over; the counts are grid seconds, not cache frames.

## 2. The gold set itself: what it can judge

| monster boxes | n | what Batt did |
|---|---|---|
| accepted | 43 | the v0 box he was shown, unchanged |
| moved | 44 | the v0 box moved, its 44 x 40 size kept |
| resized | 4 | resized |
| added | 9 | drawn where no auto box was |
| deleted | 2 | an auto box removed |

NPCs: 43 accepted, 9 moved, 2 resized.

- **One species:** all 100 monster boxes are Porings (1002).
- **82 % of the monster boxes are exactly 44 x 40**, v0's box (§5e): box SIZE in the gold set is v0's
  convention. Batt's own 13 boxes (added + resized) are median **55.0 x 43.7 px** (p10 40.8 x 21.5, p90
  63.6 x 52.9).
- **Two position conventions live side by side.** For idle units while our GM stands, the hand box's
  centre relative to the unit's projected anchor (its cell centre on the ground):
  - accepted (n = 32): **-20.0 px** (p10 -20.04, p90 -19.97): v0's box, hanging from the anchor;
  - moved (n = 18): **-12.45 px** (p10 -21.24, p90 -2.38): Batt's placement, ~7.5 px lower, its bottom
    edge 7.55 px BELOW the anchor (p10 -2.49, p90 +17.62).
  - The moved boxes are the ones Batt found off: selected on their error, so their median overstates any
    bias. The accepted ones say only that v0 was within his tolerance.
- **Consequence:** 43 of the 100 monster positions (and 43 of the 54 NPC ones) are v0's own output, so a
  label is partly scored on its agreement with v0. The position metric (centre inside the hand box) tolerates this; IoU does not.

## 3. Labels against the gold set

| labels | metric | monsters TP / FP / FN | P | R | median centre px / mean IoU | NPCs TP / FP / FN |
|---|---|---|---|---|---|---|
| v0 | position | 80 / 10 / 20 | 0.889 | 0.800 | 0.07 | 50 / 4 / 4 |
| v1 | position | 83 / 9 / 17 | 0.902 | 0.830 | 6.10 | 50 / 4 / 4 |
| v0 | IoU >= 0.5 | 58 / 32 / 42 | 0.644 | 0.580 | 0.901 | 45 / 9 / 9 |
| v1 | IoU >= 0.5 | 41 / 51 / 59 | 0.446 | 0.410 | 0.587 | 45 / 9 / 9 |

**Every v1 monster box paired with its hand box by unit (gid):**
- our GM standing (n = 84): **81 centres inside the hand box**; centre dx +1.36, dy +2.54 px (p10 -8.66,
  p90 +6.15); width x 1.33, height x 1.43; median IoU 0.50.
- our GM walking (n = 8, frames 70 and 180): **0 inside**; dx **-35.72 px**.
- by what Batt did (GM standing): accepted idle (n = 32) dy +4.32, all inside; accepted walking (n = 11)
  dy -5.86, all inside; moved idle (n = 18) dx +7.17, dy -4.43, 17 inside; moved walking (n = 14) dx
  +6.94, dy +3.34, 13 inside.
- GM dead (frames 280, 290; n = 10): all inside, dx +0.01, dy +4.09: the gold's dead frames agree.

**Every v1 position error (monsters), by cause:**

| cause | FN | FP |
|---|---|---|
| our own walk (the whole frame shifted) | 8 | 8 |
| UI window: chat | 3 | |
| UI window: minimap | 2 | |
| "off screen": the edge rule (frame 200) | 1 | |
| "off screen": a gid mix-up, really the chat window (frame 240, section 4.3) | 1 | |
| UI window: top window | 1 | |
| one idle unit 22 px off (frame 90) | 1 | 1 |
| **total** | **17** | **9** |

NPCs: all 4 FN and 4 FP are our own walk. v0, for reference: FN 20 = own walk 7, chat 4, "off screen" 3,
unit position 3 (idle 2, walk 1), minimap 2, top window 1; FP 10 = own walk 7, unit position 3.

## 4. The gaps

### 4.1 G1: a dead GM whose position the packets got wrong (training data)
- **What:** in the training session `20261004T141832-console-p3-indoor-b`, 153 ms after a monster hit our
  GM, the server acknowledged a walk of ours from (98,109) to (94,108), inside that hit's damage motion.
  The GM died 2,592 ms later (586.33 s into the recording). The packets, and so the labels, put us at
  (94,108) for the rest of the session; the screen does not.
- **Seen:** `label_quality.py peek` at 700 s and 1,150 s of indoor-b: every box sits up and to the right of
  its unit, on empty floor (looked at by eye; the pixels stay in /dev/shm). If the camera stayed where that
  walk started, the labels carry **(+107.5, -131.7) px** at our cell (census `dead_spans`).
- **The models learned it.** On the gold set's 2 dead-GM frames, whose labels are right (section 3), every
  detector misses 11 or 12 of the 12 monsters and draws boxes this far from the nearest real one (median):

  | model | all 27 frames TP / FP / FN | dead-GM frames TP / FP / FN | false box offset dx / dy (px) | the other 25 frames TP / FP / FN (P / R) |
  |---|---|---|---|---|
  | v1 (`v1png-20261008`, last.pt) | 83 / 9 / 17 | 0 / 8 / 12 | +99.6 / -99.2 | **83 / 1 / 5** (0.988 / 0.943) |
  | v1-ONNX (CPU, 736 x 1280: the live detector) | 83 / 8 / 17 | 0 / 8 / 12 | +99.6 / -99.2 | **83 / 0 / 5** (1.000 / 0.943) |
  | v1b (`v1b-20261011`) | 79 / 10 / 21 | 0 / 10 / 12 | +97.9 / -96.0 | 79 / 0 / 9 (1.000 / 0.898) |
  | v0-PNG (`v0png-20261006`) | 78 / 13 / 22 | 0 / 10 / 12 | +95.9 / -100.5 | 78 / 3 / 10 (0.963 / 0.886) |
  | v0-ONNX (CPU, v0png best.pt) | 79 / 12 / 21 | 1 / 9 / 11 | +95.3 / -101.1 | 78 / 3 / 10 (0.963 / 0.886) |
  | v0-JPEG (`v0jpg-20261007`) | 74 / 11 / 26 | 0 / 9 / 12 | +95.0 / -101.0 | 74 / 2 / 14 (0.974 / 0.841) |
  | v0-baseline (`v0-baseline-20261004`) | 76 / 14 / 24 | 0 / 9 / 12 | +95.0 / -98.9 | 76 / 5 / 12 (0.938 / 0.864) |

  The detectors' learned offset points the same way as the labels' displacement in indoor-b, at a similar
  size: they learned "restart window => boxes up and to the right".
- **How common:** dead-GM spans hold 714 of 3,795 training grid frames (18.8 %): indoor-b 608, outdoor-b
  55, s2-outdoor 51. On what was checked only indoor-b's is displaced: `peek` shows 054429's span (test,
  595 s) and s2-outdoor's (train, 85 s) with the labels on their units (the minimap's coordinate readout
  shows the packets' cell), and the gold session's own dead frames agree with Batt's boxes (section 3).
  The census's signature (`dead_spans`: the last walk before a death acknowledged inside the damage motion
  of a hit on us) flags 2 of the 12 dead spans of the 10 sessions: indoor-b's (displaced) and 054429's at
  581 s (the walk 1,908 ms before the death, 638 ms after the hit; NOT displaced at 595 s). **A candidate,
  not a detector: pixels decide.**
- **Cost:** none for the labels on gold; for the models, 11-12 FN + 8-10 FP of each one's gold errors
  (v1: 20 of its 26; v1b: 22 of its 31).

### 4.2 G2: our own walk, the camera lags the packets
- **What:** in the 2 gold frames where our GM walks (70, 180) every label, monster and NPC alike, is
  shifted the same way: frame medians -32.6 px and -38.6 px in x. A camera error, not a unit error.
- **Measured:** delaying our own position only (the units unchanged), the median centre error over the 11
  pairs falls from **34.8 px at 0 ms to 9.3 px at 100 ms and 8.9 px at 125 ms**, then rises (14.0 at 150
  ms). Both frames agree; it rests on 2 frames.
- **Cost on gold:** 16 of v1's 26 position errors and all 8 of the NPCs'. What-if at 125 ms: monsters
  91 / 1 / 9, all 8 units of the 2 frames found, no new false box; NPC errors -5. The detectors are hardly
  affected (v1 misses none of those units, v1b 2): they read pixels.
- **How common:** our GM walks in 166 training grid frames (4.4 %); at 125 ms the labels move > 20 px in
  157; per session, the median shift while walking is 21-36 px.

### 4.3 G3: the UI-window rule drops visible units
- **What:** `labels.MAX_UI_COVER` drops a unit whose box is half under `ui_layout.UI_RECTS`, the frozen
  layout measured 2026-10-02. On the gold session (S2, prt_church), seen on its frames and in the hand
  boxes:
  - **the chat window is translucent:** units behind its text area are visible and Batt boxed them
    (frames 180, 240, 280, 290);
  - **no minimap is drawn on prt_church** (UI_RECTS's own comment says the minimap is for outdoor maps,
    but the rule applies it everywhere): frames 150 and 260;
  - **no window is drawn in the small top window's rectangle**: a unit Batt boxed at (705, 22), frame 260.
- **Frame 240 is counted as "off screen" in section 3, but is a chat-window unit:** Batt's box there
  carries the gid of a unit the packets put 191 px lower, off screen (its foot at y 785.5; his box centre
  y 594.3); the translucent-chat what-if finds another unit, behind the chat window, inside his box. He
  re-used a box.
- **What-ifs (v1, monsters, position):** no minimap rect: 85 / 9 / 15 (frames 150 and 260 found, no new
  false box). Plus a translucent chat and no top window / notifier: 88 / 12 / 12 (frames 240, 280, 290
  found too; 3 new false boxes: one at (29.9, 616.6), near the chat's input bar, that Batt did not box;
  one in the walking frame 180, where the whole frame is shifted; one at (680.2, 19.7), next to Batt's box
  at (705, 22)).
- **The models:** on the 25 alive frames every detector misses the chat-window unit of frame 240; v1b and
  the four v0 detectors also miss the chat-window unit of frame 180 and the top-window unit of frame 260,
  which v1 and v1-ONNX find; none misses the minimap-area units.
- **How common (train):** chat 629 monster units in 543 frames (14 %); minimap 121 units in 111 frames
  (indoor-b only); top window 29; notifier 93; against 10,524 monster labels kept.

### 4.4 G4: the edge rule
- A unit gets a box only if at least half of it is on screen; Batt boxes the visible part. Frame 200: the
  packets put the unit's foot at x 1286.9 (past the 1280 edge); Batt's box is 36.2 x 43.1 at x 1261.9.
  1 FN; no detector misses it.
- **How common (train):** 567 partly visible units in 491 frames (13 %).

### 4.5 G5: box size (the IoU metric)
- v1 monster boxes: median **58.88 x 57.79 px**, i.e. **1.338 x and 1.445 x** the gold's 44 x 40; against
  the 9 of Batt's own boxes that a v1 box pairs with, **1.112 x wider and 1.308 x taller**.
- The phase-unknown envelope inflates them over a single frame: idle 1.05 x wide, 1.07 x tall; walking
  1.11 x wide, **1.44 x tall** (the bounce).
- **Cost (IoU only; the position metric ignores size):** v1 at 44 x 40 about the same centre: 65 / 27 / 35
  (mean IoU 0.721) instead of 41 / 51 / 59 (0.587): 48 of the IoU metric's 110 errors. Scaled to Batt's own
  ratio: 64 / 28 / 36 (0.668).
- This is §5f's open point: the gold set cannot judge a tight box until a box convention is written.

### 4.6 Measured and NOT a gap
- **Projection / k:** on Batt's moved idle boxes, dy against screen y: slope 0.0015 px/px, R^2 0.004
  (n = 18); dx against x: 0.0062, R^2 0.02; dy against the sprite scale: R^2 0.0. No depth- or
  position-dependent offset. (On the accepted boxes dy against scale is a line, slope -10.97, R^2 0.999,
  by construction: v0's box is a fixed 20 px above the anchor while v1's centre scales with the sprite.)
- **Vertical anchor:** v1's idle centre is 16.33 px above the anchor (p10-p90: 18.36-14.24), between v0's
  20.0 and Batt's moved 12.45; its box reaches 12.62 px below the anchor (v0's stops at it). Moving v1 down
  by the moved boxes' median (4.43 px, leave-one-frame-out): position 82 / 10 / 18 (-2 errors), mean IoU
  -0.034. Not a fix.
- **Horizontal:** Batt's moved boxes sit 7.17 px left of v1's centres; shifting v1 left (leave-one-frame-
  out): position 84 / 9 / 16 (+1), IoU 38 / 55 / 62 (-7). Not a fix on this evidence (the moved boxes are
  selected on their error).
- **Walk envelope:** v1's walking centre is 25.87 px above the anchor (idle 16.33). Replacing it by the
  idle envelope: position 77 / 15 / 23 (**-12 errors**), IoU +12. The high centre is right for position.
- **The gold's dead-GM frames:** their boxes are valid (section 3). Excluding them from the score removes
  2 label errors (the chat units of frames 280, 290) and every model's G1 errors.

### 4.7 The census (1 s grid, packets only)

| split | frames | GM dead | GM walking (labels > 20 px off at 125 ms) | monsters labelled (walking) | dropped: chat | minimap | top / notifier | edge |
|---|---|---|---|---|---|---|---|---|
| train | 3,795 | 714 | 166 (157) | 10,524 (3,726) | 629 (543 frames) | 121 | 29 / 93 | 567 (491 frames) |
| val | 1,551 | 138 | 116 (104) | 5,702 (2,011) | 486 | 12 | 4 / 45 | 298 |
| test | 1,906 | 283 | 123 (110) | 5,308 (1,880) | 412 | 21 | 16 / 39 | 345 |

outdoor-a (train, 1,202 frames) has no monster at all.

### 4.8 v1b against v1, box by box (the question behind decision 11)
`label_quality.py models` with v1 first: every hand box one model finds and the other misses.

| | boxes | in the dead-GM frames | which (frame / hand box: the training label's problem there) |
|---|---|---|---|
| v1b misses, v1 finds | 6 | 0 | 180/0, 180/2 (our own walk shifted the labels: G2); 180/3 (behind the chat window: G3); 260/6 (top-window rectangle: G3); 250/6, 270/2 (labels right) |
| v1b finds, v1 misses | 2 | 0 | 140/0, 210/2 (labels right) |
| false boxes | v1b +1 | +2 in dead frames | -1 on alive frames |

- So the net -4 hits are on ALIVE frames, and 4 of the 6 lost units are units the training labels drop or
  shift (G2, G3). This is consistent with the reading in v1b-vs-v1.md (the extra epochs fit v1's labels
  more closely), in a specific form: the lost units are mostly ones the labels get WRONG. Not proven: 6
  units, one run each.
- **v1-ONNX (the live detector since 11:47) against v1:** the same misses exactly (0 more, 0 fewer) and 1
  false box fewer (an alive frame).

## 5. The what-ifs (each gap closed alone; v1, monsters, IN-SAMPLE)

| what-if | fitted on gold? | position TP / FP / FN | errors removed | IoU TP / FP / FN | errors removed | mean IoU | NPC position errors removed |
|---|---|---|---|---|---|---|---|
| as is | - | 83 / 9 / 17 | - | 41 / 51 / 59 | - | 0.587 | - |
| our own walk, lag 125 ms | yes (2 frames) | 91 / 1 / 9 | **16** | 44 / 48 / 56 | 6 | 0.593 | 5 |
| exclude the dead-GM frames (25 frames) | no | 73 / 9 / 15 | 2 | 33 / 49 / 55 | 6 | 0.592 | 0 |
| no minimap rect | no | 85 / 9 / 15 | 2 | 43 / 51 / 57 | 2 | 0.584 | 0 |
| no minimap / top window / notifier, chat translucent | no | 88 / 12 / 12 | 2 | 44 / 56 / 56 | -2 | 0.583 | 0 |
| no minimap / top window / notifier | no | 85 / 10 / 15 | 1 | 43 / 52 / 57 | 1 | 0.584 | 0 |
| shift x by the moved boxes (LOFO) | yes | 84 / 9 / 16 | 1 | 38 / 55 / 62 | -7 | 0.571 | 0 |
| box 44 x 40 | no | 83 / 9 / 17 | 0 | 65 / 27 / 35 | **48** | 0.721 | 0 |
| box at Batt's own ratio | yes | 83 / 9 / 17 | 0 | 64 / 28 / 36 | 46 | 0.668 | 0 |
| shift y by the moved boxes (LOFO) | yes | 82 / 10 / 18 | -2 | 43 / 49 / 57 | 4 | 0.553 | 0 |
| walking units: the idle envelope | no | 77 / 15 / 23 | -12 | 47 / 45 / 53 | 12 | 0.583 | 0 |
| combined: no minimap + lag | yes | 93 / 1 / 7 | 18 | 46 / 48 / 54 | 8 | 0.590 | 5 |
| combined: + chat translucent | yes | 97 / 2 / 3 | 21 | 48 / 51 / 52 | 7 | 0.592 | 5 |
| combined: no minimap + lag + 44 x 40 | yes | 93 / 1 / 7 | 18 | 71 / 23 / 29 | 58 | 0.718 | 5 |

- **"Fitted on gold"**: a constant was chosen by looking at these 27 frames, so the row is an upper bound.
  The others are rule changes, but they too were chosen after seeing the gold set.
- v0 beside it: as is 80 / 10 / 20; lag 125 ms 87 / 4 / 13 (13 errors removed); no minimap 82 / 10 / 18.

## 6. Proposed fixes, each with a pre-registration sketch

**Order:** G1 first (the largest effect on the models, and the fix exists), then G3 and G2 (14 % and 4 %
of training frames), G4, then G5 (it needs a decision before any code).

1. **G1: exclude dead-GM frames from training** (labels v2's `self_dead` already does).
   - Evidence that does not use the gold set: `peek` on indoor-b's span (displaced) and two other spans
     (not displaced). Before relying on the census's walk signature anywhere: `peek` every span it flags.
   - Pre-registration sketch: the next model trains on the same frames minus the dead-GM spans, its recipe
     otherwise v1's; scored ONCE on the gold set split by GM alive / dead (`label_quality.py models`).
     Bars: on the 2 dead frames, recall above 0 / 12 and fewer than 9 false boxes; on the 25 alive frames,
     precision AND recall >= v1's on the same frames (83 / 1 / 5: P 0.988, R 0.943).
2. **G3: a measured UI layout per session, the chat window translucent.**
   - Per session, find which windows are drawn and where (the UI gate's templates already find the
     client's windows: `poring_env.ui_sets`); drop a unit only under an OPAQUE drawn window; treat the
     chat window's text area as translucent and its input bar as opaque (measure the bar once).
   - Pre-registration sketch: the rule written and measured on sessions OTHER than the gold one; the gold
     set scored once (at most the 7 UI FN found; any new false box counted); then a fresh hand check of
     ~20 frames of another session with many chat-window units (the census lists them per session).
3. **G2: delay our own position by a measured constant** (our character only, never the units).
   - Measure it WITHOUT the gold set: on outdoor maps the minimap shows our cell as digits; read them
     frame by frame while we walk and fit the delay between the packets and the readout (or use /where
     lines). Fix the constant, then score the gold set once (at most 16 errors removed).
   - The simplest alternative, no constant: drop frames where our GM moved in the last ~300 ms (4.4 % of
     training frames).
4. **G4: box the visible part of a unit at the frame edge**, with a minimum visible size (e.g. 8 px each
   way), checked against a fresh hand check (gold: +1).
5. **G5: write the box convention first** (§5f: halo in or out, envelope or single frame), then generate
   labels for it. Batt's own boxes (55 x 44) and the 44 x 40 ones cannot both be the convention. The
   current gold set cannot judge a tight box; re-checking its 100 monster boxes under the written
   convention is the measurement (Batt's call, §5f).

## 7. What could not be determined
- ~~v1's own gold predictions are missing~~ ➡️ **CORRECTED 2026-10-13 ~12:30: they were never missing.**
  `pred-v1png-20261008.json` (and today's `pred-v1onnx-cpu.json`) are in the main checkout's
  `data/train/eval/gold/<session>/`; an `ls | head` cut the listing at 10 lines and hid them. v1's split
  is now in section 4.1 and the v1b-vs-v1 answer in section 4.8.
- **Why indoor-b's walk was never shown on screen:** the census's signature (a walk acknowledged inside a
  hit's damage motion) is a candidate, not a detector (section 4.1).
- **G2's lag** rests on 2 frames and 11 units.
- **Per-species size and anchor:** the gold set has one species.
- **Whether v1b lost to v1 BECAUSE of these gaps** is suggested, not proven (section 4.8: 4 of its 6
  extra misses are units the labels get wrong; 6 units is a small sample, and one run each).
- v1b's 14 misses where the label was right (10 in the dead-GM frames) have no detection within 40 px at
  all: missed detections, not misplaced boxes.

## 8. Reproduce
Outputs go to /dev/shm (client-derived numbers and pixels; never committed). From a checkout with
`data/` (the hand check, the KB) and the generated map caches, at commit 7e3a3fc or later (the census
below ran at a7fea33, whose census code f7da9ce keeps; a second run reproduced every total):

    S=/dev/shm/poring-lab-tmp/label-quality G=data/train/eval/gold/20261004T103815-console-s2-indoor-v2
    uv run python scripts/label_quality.py dump 20261004T103815-console-s2-indoor-v2 --out $S/dump.json
    uv run python scripts/label_quality.py cache $S/dump.json \
        /mnt/poring-lab-datasets/.framecache/v1png-20261008/shard-000046.tar
    uv run python scripts/label_quality.py report $S/dump.json > $S/report.json
    uv run python scripts/label_quality.py models $S/dump.json $G/pred-v1png-20261008.json \
        $G/pred-v1b-20261011.json $G/pred-v1onnx-cpu.json $G/pred-v0png-20261006.json \
        $G/pred-v0onnx-cpu.json $G/pred-v0jpg-20261007.json $G/pred-v0-baseline-20261004.json
    uv run python scripts/label_quality.py census \
        /mnt/poring-lab-datasets/.framecache/v1png-20261008/manifest.json > $S/census.json
    uv run python scripts/label_quality.py peek 20261004T141832-console-p3-indoor-b 700 $S/peek.png

From a worktree, add `--data <checkout>/data --bundles <checkout>/services/frontend/.qa-local
--mapcache <checkout>/packages/poring_dataset/src/poring_dataset/_generated`. The census reads only the
packet files and manifests from the NAS (~15 min of CPU at 1 s steps); `cache` reads only the shard's tar
headers and txt members; `peek` reads one GOP (H.264) or one PNG.
