---
doc_type: design
hypothesis: "Floor items labelled from the packets (exact cell, sub-cell, drop and vanish times), projected by the monsters' camera model on frames where our character stands still, give boxes a blind check accepts, so a detector class `item` can be trained with the monsters."
status: PRE-REGISTERED 2026-10-23 22:38:40 ICT (a46893d; amendments A 19201ea, B 62454f8). RESULT 2026-10-23 23:0x -- the item TRAINING TIER FAILS on both maps (G1 prt_fild08 35.7 % > 5 %; orcsdun01 9 scored < 50, no verdict), so by section 6 the item class does NOT train tonight
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [orcsdun01-detector.md, labels-v2.md, ../benchmarks/item-class.md, ../benchmarks/v2orc-vs-v1.md]
next_action: "Batt's call (section 8): G1 failed as written; the blind round 1 pack (seed 5) is built and may still be run to judge the FITTED labels (it cannot make a map train under section 6). Options for a new pre-registration in 8: a G1 that judges geometry (G2-style offset) instead of the matcher's recall, a model-occlusion rule for items under trees, the cursor / corpse exclusions."
title: "An ITEM class for the detector: the label rule, the measurements, the checks and the training tier (pre-registered)"
date: 2026-10-23
owner: Batt
---

# An `item` class for the detector (pre-registered)

**Batt, decision 3 (verbatim, received 2026-10-23 ~22:1x ICT):** "NEW, the biggest lever (Batt
agrees): an ITEM class for the detector, trained TONIGHT with the monsters. Label ground items from
the packets (exact cell, item id, drop/pickup/vanish times) on banked sessions (prt_fild08 +
orcsdun01), project them like monsters (an item's sprite sits at a sub-cell offset and is drawn
after a fall animation: measure both), blind-check a sample, pre-register the label checks and the
evaluation (per-map item recall/precision on held-out sessions; then "loot by sight" as a later bot
version)."

**And:** "GPU, as soon as BOTH tiers pass (monster labels and item labels): train overnight ... If
the item labels pass but a monster species still fails (or the reverse), say which and train what
passed only if the pre-registration allows it; otherwise report and don't train. Score only after
training ends, against the pre-registered evaluation (v2orc-vs-v1.md + the item evaluation)."

This file is committed BEFORE any item label is built, measured or checked. Its commit time is the
pre-registration time. A rule or parameter below changes only by a clock-labelled AMENDMENT written
BEFORE the step it changes. The evaluation is [../benchmarks/item-class.md](../benchmarks/item-class.md)
(a new file, not an amendment of v2orc-vs-v1.md: a new class with its own data, its own packs and
its own bars; v2orc-vs-v1.md's monster scores stay exactly as pre-registered there).

Read before this commit (the inventory, packets and file lists only): the packet event counts of
the candidate sessions, their frame-file names (capture times) and manifests, and the floor
occupancy of the orcsdun01 demo over time (to cut its blocks, section 2). No frame was read and no
item was projected.

## AMENDMENT A (written 2026-10-23 22:4x ICT, the commit time of this amendment; BEFORE any item label, measurement or check exists: nothing has been measured, built or read but the inventory)

Four readings the pre-registration left open, fixed before the step each one touches:
1. **"KEPT" item labels (section 5's blind round 1 and its negatives) = the labels that TRAIN:**
   the item labels of KEPT ROUTE-U frames (3g) of the map's TRAIN data, and the negatives come from
   the same kept Route-U frames. The blind check judges what would train, as the monsters' did. A
   map with fewer than 40 such labels is sampled whole.
2. **G1's scope** is every labelled frame's item that passes 3a-3e (Route U or not; the fit not
   yet applied), on the TRAIN data, as written. Route U decides the cache, not G1.
3. **Outside Route U (the evaluation frames of ../benchmarks/item-class.md) no `under_unit` rule
   applies:** an item covered by a monster fails the fit (`unfit`) or, if it passes, is judged by
   the seed-6 blind pack like any other evaluated label. Nothing is added.
4. **The orcsdun01 cuts, exactly** (seconds after the demo's first frame, the computation of
   section 2): FIT [0, 282.913519548), TRAIN [302.913519548, 649.527039097), TEST
   [669.527039097, end]. Frames between are in no block.

## AMENDMENT B (written 2026-10-23 22:5x ICT, the commit time of this amendment; AFTER the prt_fild08 FIT measurement, BEFORE the freeze and BEFORE any TRAIN or TEST frame is read)

**What happened:** section 4.5's rule returned NO value for `D_APPEAR` on prt_fild08's FIT data
(`measure_prt_fild08.json`). The present share of fresh drops at their final spot is low even when
settled (plateau over ages [2, 3] s = 0.325), so the 0.1-s bins up to 2.0 s (n 26-86 each) scatter
around it (0.17-0.45 from 0.9 s on) and "every bin >= 0.95 x plateau" never holds. The tool
(`freeze`, written before the measurement) stops in that case.

**The change (the only one):** `D_APPEAR = 2.0 s + the pre-registered 0.2 s margin = 2.2 s`.
- 2.0 s is the start of section 4.5's own PLATEAU window: the pre-registration already defines ages
  >= 2.0 s as "settled". The value comes from that definition and the margin, not from the bins.
- It is the conservative side: frames up to 2.2 s after a drop are EXCLUDED (`item_settling`),
  never labelled.
- Reported, NOT used: the bins rise from <= 0.05 (ages 0-0.6 s) to ~0.3 from 0.9-1.1 s, so the
  fall + display delay itself looks like ~1 s (item_icons.py's 2026-10-17 `FALL_SETTLE_S` was 1.1 s).
- Nothing else changes. In particular G1 keeps TAU[map] (Youden) and its 5.0 % bar, although the
  FIT data's TPR at TAU is 0.754 (FPR 0.031): that predicts a G1 near 25 %, i.e. a FAIL by the
  pre-registered tier. It is not changed after that was seen; G1 runs and is reported as written.

## 1. What the packets say (OFFLINE ground truth, ADR-0007)

- `floor_item_appear` kind `fall` = ZC_ITEM_FALL_ENTRY5 0x0ADD: a FRESH drop (a kill, a throw):
  floor id, item id, cell x / y, sub-cell `sub_x` / `sub_y`, amount, drop effect.
- `floor_item_appear` kind `in_sight` = ZC_ITEM_ENTRY 0x009D: an item ALREADY on the floor coming
  into our view (map entry, a walk). Same fields, no fall.
- `floor_item_vanish` = ZC_ITEM_DISAPPEAR 0x00A1: picked up, expired, or out of OUR sight. The
  packet does not say which; for a label it does not matter (it is no longer drawn).
- rAthena places a mob drop at `sub_x, sub_y` in {3, 6, 9, 12} ((r & 3) * 3 + 3). How the client
  draws a sub-cell is NOT known here: roBrowser reads `cell - 0.5 + sub / 12` (hypothesis H12,
  used by `drop_blobs.py` / `item_icons.py` so far); it is MEASURED (section 4).
- The decoder exists since 2026-10-08 (loot@1 P2). Sessions before that have no floor-item
  events.

## 2. The sessions and the split (fixed now, by session; before any label exists)

Inventory (packets: event counts; frames: the file listing):

| map | session(s) | frames | fresh drops (`fall`) | `in_sight` | camera | UI |
|---|---|---|---|---|---|---|
| prt_fild08 | 37 bot hunt recordings 2026-10-19 20:21 .. 10-22 04:25 (`hunt-recordings/`, v42-v55) | ~18,100 a session (5 Hz, JPEG q80, 1 h) | 92-273 a session | 0-56 | our GM walks most of the time (hunting); still while fighting | the hunt layout (v43, 2026-10-19), checked per frame |
| prt_fild08 | Batt's 2026-10-16 demo | 3,888 | 64 | 0 | Batt's | before the hunt layout: NOT used |
| orcsdun01 | Batt's 2026-10-22 Crusader demo `20261022T184536-demo-human-demo-orcsdun01-crusader` | 4,880 (5 Hz, 977 s) | 136 (12 item ids) | 0 | Batt walks and fights | the hunt layout, checked per frame (3f's adapter) |
| orcsdun01 | col1 / col3 (warp and watch) | 15,028 / 12,030 | **0** | 0 | still GM | no item ever on the floor: no item label hole |
| orcsdun01 | col2 | -- | -- | -- | -- | the monster TEST block: NOT read for anything |
| orcsdun01 | the 2026-10-21 demo | none on the NAS (225 packets, 0 human input) | -- | -- | -- | not usable |
| orcsdun01 | the 3.98 / 3.99 / 4.00 bot runs | strike shots only (3f) | -- | -- | -- | not usable (no capture times) |

**prt_fild08 split (by session):**
- **FIT** (the measurements of section 4 only): `20261020T093755-demo-hunt-flow48`,
  `20261020T104057-demo-hunt-flow48`.
- **TRAIN:** `20261020T151005-demo-hunt-flow49`, `20261020T161139-demo-hunt-flow49`,
  `20261020T183131-demo-hunt-flow50`, `20261021T092850-demo-hunt-flow52`,
  `20261021T150152-demo-hunt-flow53`, `20261022T012118-demo-hunt-flow55`.
- **TEST (held out; not read before training ends except to build its labels and G1, which read
  no detection):** `20261021T223812-demo-hunt-flow54`, `20261022T032441-demo-hunt-flow55`.

**orcsdun01 split: ONE usable session, so it is split BY TIME (a stated deviation from "by
session").** The cuts are where the floor is empty for +-10 s (no item spans two blocks), nearest
to 1/3 and 2/3 of the frame span (computed from the packets alone, 2026-10-23 22:3x), and the
+-10 s around each cut belong to no block:
- **FIT:** frame times [0, 282.9) s from the first frame (31 fresh drops, 1,413 frames);
- **TRAIN:** [302.9, 649.5) s (52 drops, 1,731 frames);
- **TEST:** [669.5, end] s (51 drops, 1,537 frames).
- **Honest limit:** the same session, character, player and light. It measures held-out ITEMS
  and moments, not held-out sessions.

## 3. The label rule (`scripts/item_labels.py`; every parameter named here)

**3a. On the floor, and when.** An item (floor id) is on the floor from its `floor_item_appear`
(time `t_a`, either kind) to its `floor_item_vanish` (`t_v`), or our `map_change`, or the session's
last packet. On a frame with capture time `t_f` (the file name's `t_mono_ns`, the same host clock
as the packets):
- **labelled** when `t_a + D_APPEAR <= t_f < t_v`;
- the FRAME is EXCLUDED (`item_settling`) when `t_a <= t_f < t_a + D_APPEAR` (falling, or not yet
  drawn: the display lag);
- the FRAME is EXCLUDED (`item_vanishing`) when `t_v <= t_f < t_v + D_GONE` (still drawn: the
  display lag);
- `D_APPEAR` (the fall + display delay) and `D_GONE` are MEASURED on the FIT sessions (section 4)
  and frozen. `D_APPEAR` applies to both kinds (an `in_sight` item has no fall; the longer delay is
  the conservative side).
- **Item truth known:** a frame earlier than the first `map_change` in the session's packet stream
  is EXCLUDED (`item_truth_unknown`): an item put on the floor before the stream began would be
  drawn and unlabelled.

**3b. Where.** The item's fractional cell = `(x + OX[sub_x], y + OY[sub_y])` with the sub-cell
table MEASURED on the FIT sessions (section 4; H12 = `sub / 12 - 0.5` is the starting
hypothesis). Its ground point is projected exactly as the monsters' anchors are
(`labels_v2.project_cell`: the session backend's fitted camera `camera_rdp.json`, the map's GAT
altitude, the camera on our character's cell). The sprite centre = the ground point + the item's
ANCHOR (px, per item id, measured on the map's FIT data).

**3c. Only while our character stands still** (`self_moving` otherwise). Our position (the
Timeline's, from our own `self_move` / stops) must be the same cell (within 0.01) at every 0.1-s
step of `[t_f - STILL_S, t_f]`, `STILL_S = 0.8 s`. An item never moves, so with a still camera the
packet -> frame offset does not enter its position (it is longer than every display lag measured
here: 120 ms on warp_watch's path, ~0.38-0.6 s on the hunt runner's). Our character dead
(`labels_v2.self_dead_spans`): `self_dead`.

**3d. The box.** Per item id, a TEMPLATE (RGB + the mask of the item's own pixels) is built from
the map's FIT data (`item_icons.build_template`: saliency seeds, the median, the mask, masked-NCC
re-alignment; client-derived, never committed). The PREDICTED box = the template mask's tight box,
`PAD = 1` px on each side, centred on the predicted sprite centre. The LABEL box = the predicted box
moved by the best masked colour NCC (`item_icons.match_maps`) within `+-R_FIT = 4` px. A best NCC
below `TAU[map]` or at the search edge = `unfit`. An item id with no template on its map =
`item_untemplated`. Justification: the drawn sprite's own extent is what a box should hold (the
monsters' fitted-sprite rule, 3b item 0 there), and the fit's tau is ALSO the test that the item is
really drawn there (covered by a model, a corpse, the cursor: unfit).

**3e. Occlusion and crowding** (each is a FRAME exclusion, counted under its own name):
- `under_self`: the item's predicted box overlaps our own character's box (`labels_v2.self_label`:
  v0's `player` 34 x 74 at our feet);
- **units (Route U, 3g):** item frames carry no other unit, so an item under a monster, an NPC or
  another player cannot occur in a kept frame;
- `stacked`: two items' predicted boxes overlap with IoU >= `STACK_IOU = 0.5` (one hides the other);
  lower overlaps are labelled as two boxes;
- `ui_partial` / `edge_partial`: an item box partly inside a UI window of the recorded layout
  (`client_layout.RECTS["hunt"]`) or partly outside the game region. Wholly inside a window or
  wholly off screen: not drawn, no label, no exclusion;
- **map models (the monsters' 1c):** the parameter `MODEL_OCCLUSION = "none"` for items: an item
  hidden by a model is not drawn, so the fit fails (`unfit`) and the frame is excluded. The
  monster side's 1c box rule (or its round-4 occlusion option) is NOT applied to items. If Batt
  wants it applied, it is an amendment before the labels are built.
- `ui_layout_mismatch`: the frame's layout read from pixels (`client_layout.read`) is not `hunt`.

**3f. A frame** carries a complete item truth only if NO exclusion of 3a-3e fires for ANY item of
the frame; then every item on screen is labelled. As for the monsters: a frame is labelled
completely or EXCLUDED, never half-labelled.

**3g. Which frames enter the training cache: ROUTE U (unit-free), fixed now.** A cache frame must
be complete for EVERY class, and no monster pre-registration admits the new sessions' monster
labels (prt_fild08's hunt recordings are new sessions; the orcsdun01 demo failed 3f's own C1 at
14.8 %). So an item frame enters the cache only when the packets place NO unit but our own character
on screen: no entity (monster, NPC or portal of any class, other player) of the Timeline's world at
any 0.1-s step of `[t_f - STILL_S, t_f]` whose ground anchor projects inside
`[-80, 1360] x [-40, 880]` px (the game region plus a sprite's reach). Such a frame's complete label
set is: its items (class `item`) + our own character (`player`, labels_v2's self rule, as the v2
frames). Dying units are not units (the world's `dead`), as in v1 / v2 (no class labels a corpse).
- **ROUTE M (not used tonight, named so it needs no amendment):** if, and only if, the monster
  pre-registration in force admits a session's monster labels, its frames may enter when BOTH label
  sets keep the frame.
- **Sampling:** every 3rd frame (the cache's 5-Hz rate, `--every-jpeg 3`) of the frames with at
  least one item label; every 15th of the Route-U frames without one (negatives: grass, flowers,
  corpses), so still empty frames do not swamp the cache.

## 4. The MEASUREMENTS (FIT data only), then FROZEN

On each map's FIT data, `item_labels.py measure` (frames read every 0.4 s of GM-still time):
1. **Templates** per item id: samples = items aged >= 2.5 s and >= 1.0 s before their vanish (fixed
   margins, before any delay is measured), on GM-still frames, no other item within 24 px, clear of
   our box (+8 px), no unit within 1 cell, >= 44 px inside the region and >= 30 px from every UI
   window; <= 8 samples per floor item, >= 1 s apart; >= 12 samples or no template.
2. **The sub-cell table** `OX[s]`, `OY[s]` (s in 3, 6, 9, 12; cells), prt_fild08 FIT only (the
   client's rule is map-independent): each sample's best-NCC sprite centre (within +-10 px of the
   H12 prediction) against the projection, solved jointly with the per-item anchors by least
   squares through the camera's local Jacobian, `OX[6] = OY[6]` fixed at H12's 0 (a constant goes
   into the anchors). Reported: H12's and H16's (`(sub - 8) / 16`) residuals beside it.
3. **The anchors** (px, per item id per map): the median of (best-NCC sprite centre - the projected
   ground point under the measured table).
4. **TAU[map]**: the masked NCC (best within +-R_FIT) of each template at its settled samples
   (present) and at EMPTY floor (absent: a projected point with no floor item within 3 cells, no unit
   within 2 cells, clear of our box and the UI, one per present sample on the same frames); tau =
   the threshold maximising TPR - FPR (Youden), frozen per map.
5. **D_APPEAR** (prt_fild08 FIT; the orcsdun01 FIT block's value is reported as a cross-check):
   fresh drops on GM-still frames, clear of our box, no other item within 24 px; per 0.1-s bin of
   age `t_f - t_a` in [0, 3] s, the share with NCC >= TAU at the final predicted spot (+-2 px).
   Plateau = the share at ages [2, 3] s. `D_APPEAR` = the start of the first bin from which every bin
   up to 2.0 s has share >= 0.95 x plateau, **+ 0.2 s**.
6. **D_GONE** (the same data): per 0.1-s bin of `t_f - t_v` in [0, 1.5] s, the present share.
   `D_GONE` = the first bin start from which every bin up to 1.5 s has share <= 0.10, + 0.2 s. With
   fewer than 30 frames in those bins: `D_GONE = 1.0 s` (fixed fallback).
- **Frozen:** `params.json` (the table, the anchors, the template sizes, TAU, the delays, every
  constant of section 3) + `templates_<map>.npz`, their sha256 quoted in section 8 with the clock
  time, BEFORE any TRAIN or TEST frame is read. TRAIN and TEST sessions are never read by
  `measure` (the tool refuses them by name).
- **A REAL positive case** (committed test): a fit-session frame where a known drop is visible at
  its predicted spot (the test reads the NAS frame and skips when the NAS is absent).

## 5. The label checks (bars fixed now)

**G1, the geometric check (the monsters' C1):** on every TRAIN session's labelled frames (every
3rd), per item that passes 3a-3e (before the fit decides `unfit`): the masked NCC of its template
AT the PREDICTED position (no fit; within +-1 px), `bad_label` when < TAU[map].
- **Bar: G1 pooled per map <= 5.0 %** (the unrounded ratio; Batt's training tier for the monsters,
  3f T1). With fewer than 50 items scored on a map: no verdict, that map's items do not train.
- **G2 (reported, a STOP not a verdict, as the monsters' C2):** the median |dx|, |dy| of the best
  offset within +-8 px; if it exceeds 3 px on a map, the parent tells Batt before any cache.
- Reported: per item id, per session; the exclusions per reason; the TEST sessions' G1 (no bar).

**B, the blind check, round 1 (seed 5; seeds 0-4 are the monsters'):**
- **Two NEW blind labeller agents** (the parent launches them; each sees ONLY the pack directory
  and its `instructions.txt`, never the key).
- **Per map: 40 ITEM crops** drawn by seed 5 from the KEPT (fitted) item labels of the map's TRAIN
  data (at most 3 crops per floor item; a map with fewer than 40 kept labels is sampled whole)
  **+ 20 NEGATIVE crops** (empty floor: a projected ground point on a kept GM-still frame of the same
  TRAIN data with no floor item within 3 cells and no unit within 2 cells, clear of our box and the
  UI; the box = the map's median item box size), shuffled together, numbered.
- **Each crop:** 96 x 96 px of the frame around the box centre, enlarged 3x, shown twice side by
  side: plain, and with the box drawn (1 px, cyan).
- **The questions** (`instructions.txt`, written now, below): q1 an item in the box? q2 the box.
- **Bars, per map, from EACH labeller:**
  - **>= 90 % "good box"** on the ITEM crops (q1 = yes AND q2 = good);
  - **item-present right >= 95 %** on ALL crops (q1 = yes on an item crop, q1 = no on a negative;
    "unsure" is wrong).
- Scored by `scripts/item_blind_score.py --key KEY ANSWERS_A ANSWERS_B` (committed with tests).

**The instructions (`instructions.txt`, word for word):**

```
You are a blind labeller. Each numbered image is a crop of a game screenshot (a
third-person view looking down at the ground), enlarged 3x. Each image shows the
SAME crop twice, side by side: LEFT plain, RIGHT with a thin cyan rectangle drawn
on it. Use the left copy to see what is under the rectangle's lines.

For EVERY crop answer two questions about the RIGHT copy's rectangle:

q1: Is there a DROPPED ITEM inside the rectangle? A dropped item is a small loose
    object lying on the ground (loot), for example a gem, a fruit, a bottle, a
    feather, a bone, a nail, a herb, a card, a weapon. Answer "yes", "no" or
    "unsure". These are NOT dropped items: characters, monsters, monster corpses
    or splats, plants or flowers growing from the ground, rocks, shadows, the mouse
    cursor, and any user-interface element.

q2: Only if q1 is "yes": does the rectangle fit THAT item?
    "good"  = it encloses the item, with at most a few pixels of slack, and cuts
              nothing off;
    "loose" = it encloses the item but with clearly too much empty ground (on
              some side more than about half the item's own size);
    "off"   = it cuts off part of the item, or is shifted so the item is not
              inside it.
    If several items are in the rectangle, judge the most central one.
    If q1 is not "yes", answer "-".

Write your answers to the file named in your task as a JSON list, one entry per
crop, every crop answered, for example:
[{"crop": "007", "q1": "yes", "q2": "good"},
 {"crop": "008", "q1": "no", "q2": "-"}]
Judge only what you see. Do not open any other file, and do not infer anything
from file names or crop order.
```

## 6. The training tier for the item class (operational)

- **A map's item labels TRAIN only if BOTH hold on that map:** G1 pooled <= 5.0 % (>= 50 scored)
  AND the blind round 1 passes both bars from both labellers. A map that fails contributes NO item
  frame (its Route-U frames are not added at all).
- **The frames:** Route U only (3g), TRAIN data only, sampled as 3g; each frame's label set = its
  items + our own `player` box. FIT and TEST data never enter the cache.
- **Independent of the monster tiers (the pre-registration ALLOWS it):** Route-U frames hold no
  monster, so the item class can train with whatever monster data passes its own tier (v1's
  prt_fild08 sessions with the species split, plus orcsdun01's monster data only if ITS tier
  passes). If the item tier passes and an orcsdun01 monster species fails, the run may train
  "v1 + species split + item"; if the item tier fails on both maps, the item class is not added and
  the monster run is as its own pre-registration says.
- **The class id:** `item` is appended after the 15 classes of `config/detector/classes-v2orc.json`
  (id 15), in `config/detector/classes-v2orc-item.json`.
- **Known holes, reported, not fixed tonight:**
  - v1's ten sessions (2026-10-03/04) predate the floor-item decoder. Their packets show 0-3 monster
    deaths each (15 in all, no damage act of ours), so a drawn item there is rare but would be an
    unlabelled item;
  - the monster blocks col1 / col3 have no floor item at all (0 events): no hole.

## 7. Not tonight

"Loot by sight" (the bot clicking items the detector boxes, instead of templates and packets'
absence) is a LATER bot version, pre-registered on its own after the item evaluation is scored.

## 8. RESULTS (appended below, clock-labelled; nothing above this line is edited after the pre-registration commit except by a labelled AMENDMENT)

### 8a. RESULT (2026-10-23, clock times from `date` and the commits)

**The order of events:** pre-registration a46893d 22:38:40; amendment A 19201ea 22:41:04; tools
f3e2a36 22:50:23; prt_fild08 FIT measured 22:45:57-22:53:38; amendment B 62454f8 22:55:00;
orcsdun01 FIT measured 22:55; **FROZEN 22:55:49** (`params.json` sha256
`1c1348abdaa3cf1d90e76b24361615ab26fce0116ee170fadb7a66681ceec639`; templates prt_fild08
`bd43befa…7fee7b`, orcsdun01 `95dadfd5…936051`); TRAIN + TEST labels 22:56-23:06; G1 23:07; blind
pack 23:07:47. No TRAIN or TEST frame was read before the freeze; col2 was never read.

**The measurements (FIT only; section 4):**

| what | prt_fild08 (FIT flow48 x 2) | orcsdun01 (FIT block, 283 s) |
|---|---|---|
| clean samples / floor items | 261 / 88 | 61 / 8 |
| templates (item ids; samples) | 7: 909 (84), 705 (37), 512 (23), 713 (19), 949 (17), 507 (12), 515 (10); 11-15 x 13-15 px | 2: 935 (13), 938 (10), from 2 floor items each |
| sub-cell table OX (cells, s = 3 / 6 / 9 / 12) | -0.189 / 0 / +0.185 / +0.376 | (prt_fild08's) |
| sub-cell table OY | -0.210 / 0 / +0.173 / +0.329 | (prt_fild08's) |
| table fit | 249 rows, 224 used (25 beyond 3 MAD), median residual 2.07 px | -- |
| median anchor residual (reported) | H12 3.92 px, **H16 1.68 px**, measured 2.22 px | -- |
| anchors (sprite centre - ground point) | x -4.3 .. -6.8 px, y -0.4 .. +4.9 px per item | x -4.2 / -6.0, y -0.1 / -1.1 |
| TAU (Youden) | **0.612** (TPR 0.754, FPR 0.031; 260 / 260) | **0.789** (TPR 0.70, FPR 0.0; 40 / 40) |
| D_APPEAR | section 4.5's rule: NO VALUE (plateau 0.325) -> **2.2 s** by amendment B | (cross-check, not used: 2.1 s) |
| D_GONE | **0.6 s** (344 frames; bins <= 0.10 from 0.4 s) | (cross-check: 0.3 s, 46 frames) |

- **The sub-cell step is 1/16 of a cell per sub unit** (3 units = 0.185-0.21 cells), i.e. the
  client reads `sub / 16` (H16's slope), not roBrowser's `sub / 12` that drop_blobs.py and
  item_icons.py assume. H12 misplaces a sub 12 item by ~0.12-0.17 cells (~4 px).
- The fall + display delay itself looks like ~1 s (the present share rises from <= 0.05 before
  0.6 s to ~0.3 from 0.9-1.1 s); amendment B's 2.2 s is the conservative value used.
- **The REAL positive case** (committed test, it ran): flow48 frame `03019-1206122021953374`,
  floor id 12726 (a Jellopy in a Poring's splat): NCC 0.80 at +-1 px of the frozen prediction
  (best offset 1 / 1 px), the same template at an empty point of that frame 0.10.

**THE LABELS (every 3rd frame; section 3):**

| map / split | sessions | frames considered | kept | kept Route U (with items) | item labels kept (in Route U) | floor items in Route U |
|---|---|---|---|---|---|---|
| prt_fild08 TRAIN | 6 | 25,628 | 1,699 | 1,188 (539) | 1,430 (761) | 178 |
| prt_fild08 TEST | 2 | 8,498 | 507 | 416 (170) | 296 (193) | 47 |
| orcsdun01 TRAIN block | 1 | 329 | 8 | 2 (1) | 7 (1) | 1 |
| orcsdun01 TEST block | 1 | 347 | 0 | 0 | 0 | 0 |

Frame exclusions per reason (a frame can carry several; a `self_moving` frame is not judged
further):
- prt_fild08 TRAIN: self_moving 20,868; item_settling 2,107; item_vanishing 916; unfit 679;
  item_truth_unknown 334; under_self 157; item_untemplated 112; ui_partial 37; stacked 5;
  edge_partial 1.
- prt_fild08 TEST: self_moving 6,977; item_settling 644; item_vanishing 278; unfit 226;
  item_untemplated 163; under_self 60; item_truth_unknown 40; stacked 15; edge_partial 7.
- orcsdun01 TRAIN: item_untemplated 144; self_moving 128; item_settling 85; item_vanishing 48;
  unfit 17; under_self 10. TEST: item_untemplated 310; unfit 105; item_settling 91; under_self 61;
  self_moving 64; item_vanishing 48.
- **The yield is thin by construction:** the bot walks most of the time (81 % of the TRAIN frames
  considered are `self_moving`), and in the inventory's sample (every 30th frame of the first FIT
  session) only 21 of 145 still frames were unit-free.

**G1 / G2 (section 5; `item_labels.py check`):**

| map | split | scored | bad (NCC at the prediction < TAU) | G1 | bar <= 5.0 % (>= 50) | G2 median abs dx / dy |
|---|---|---|---|---|---|---|
| prt_fild08 | **TRAIN (gates)** | 2,088 | 745 | **35.7 %** | **FAIL** | 1 / 1 px |
| prt_fild08 | TEST (reported) | 455 | 153 | 33.6 % | -- | 1 / 1 px |
| orcsdun01 | **TRAIN (gates)** | 9 | 2 | 22.2 % | **NO VERDICT (< 50)** | 0 / 0 px |
| orcsdun01 | TEST (reported) | 3 | 3 | 100 % | -- | 8 / 1 px |

- prt_fild08 TRAIN per item id (n, bad share): 909 678, 48.7 %; 705 519, 32.4 %; 512 431, 31.8 %;
  949 84, 34.5 %; 507 92, 27.2 %; 713 217, 20.3 %; 515 67, 17.9 %. Route-U items alone: 35.4 %.
- **As amendment B predicted from the FIT TPR (0.754), G1 fails.** TAU is a Youden threshold, so a
  quarter of the FIT data's own clean items already score under it.
- **What the "bad" items are (by eye, 16 random TRAIN rows, `diagnostics/g1_bad.png`; NOT a
  measurement):** 4 lie under TREE CANOPY (only a sparkle shows: map-model occlusion, which
  `MODEL_OCCLUSION = "none"` left to the fit); 4 under the bot's own HAND CURSOR (with the
  client's item-name tag beside it); 3 in or under a CORPSE / dying monster / a live Poring; 3
  visibly 3-8 px off the prediction (an item beside the box); 2 with nothing visible at all. G2's
  median of 1 / 1 px says the geometry is right for most; these are its tail.
- **The fitted (kept) labels are a different set:** a label is kept only with NCC >= TAU within
  +-4 px, so the cases above are mostly `unfit` (their frames excluded), not mislabelled.

**THE VERDICT (section 6, as written): the item TRAINING TIER FAILS on both maps.**
- prt_fild08: G1 35.7 % > 5.0 %. orcsdun01: 9 scored < 50 (no verdict; and only 2 item templates
  from 4 floor items: `item_untemplated` excluded 144 of its 329 TRAIN frames considered and 310
  of 347 TEST).
- **=> The item class does NOT train tonight; nothing of it enters the cache.** The monster run is
  unaffected (its own pre-registration).
- **The blind round 1 pack is built anyway** (it cannot make a map train under section 6; it
  measures the FITTED labels, as round 2 did for the monsters in orcsdun01-detector.md 3d):
  `/dev/shm/poring-lab-tmp/item-r1/blind-pack-seed5/` (62 crops: prt_fild08 40 items + 20 negatives;
  orcsdun01, sampled whole, 1 item + 1 negative; `instructions.txt` byte-identical to section 5),
  key `/dev/shm/poring-lab-tmp/item-r1/answer-key-seed5/answer_key.json`, scored by
  `scripts/item_blind_score.py --key <key> <answers A> <answers B>`.

**For Batt (new decisions, a new pre-registration; NOT taken here):**
1. Replace G1's matcher-recall test by a geometry test (G2's offset, a bar fixed in advance) and let
   the blind check judge the fitted labels -- the analogue of the monsters' 3d / 3f split.
2. Exclude items under map models (the monsters' 1c box rule or its round-4 successor), under our
   own cursor (its drawn position is in the input log), and within N s of a death on their cell
   (the corpse), instead of leaving them to the fit.
3. More item templates (orcsdun01 has 2; prt_fild08's rare drops have none): a longer FIT, or
   templates decoded from the client's own item sprites.
4. More frames: Route U holds 761 of the 1,430 kept TRAIN item labels; the other 669 sit on frames
   with monsters on screen, which need the monsters' labels too (Route M), and no monster
   pre-registration covers the hunt recordings.
5. The `sub / 16` reading should replace `sub / 12` in drop_blobs.py / item_icons.py (measured
   here; their own evaluation would need a re-run).
