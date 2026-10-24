---
doc_type: design
hypothesis: "Batt's four target items (Rough Elunium 757, Rough Oridecon 756, Dead Branch 604, Honey 518), staged on pay_fild07's floor and labelled from the packets, are found from ONE 1-fps frame by per-item masked colour templates built on FIT spots: on held-out TEST spots recall >= 80 % and precision >= 90 % per item within +-6 px, with <= 1 false detection per 100 hunting frames per item."
status: "ROUND 2 (open ground, multi-templates) PRE-REGISTERED 2026-10-24 (section 10; its commit time); no round-2 pixel read yet. ROUND 1 RESULT 2026-10-24 (5ed077c 18:31:23): ALL FOUR FAIL the recall bar (757 19.0 %, 756 40.0 %, 604 66.7 %, 518 66.7 %; bar 80 %); precision 100 % and 0 false detections in 4,392 hunting frames for every item; the natural Dead Branch FOUND (0.8 px). Trees hide 29.3 % of the TEST labels (no detector can pass on this TEST set). PRE-REGISTERED fbc077e 17:48:17, amendment A b0bdc10 18:00:54, frozen 18:05:45."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [item-class.md, thief-payon.md, ../demonstrations.md, ../../scripts/target_items.py, ../../scripts/target_items_r2.py, ../../scripts/stage_items.py, ../../scripts/item_labels.py]
next_action: "Round 2 (section 10): fit, freeze, score TEST / TEST-NEG, then the recommendation. Round 1's (section 9b): (1) a live 'loot by sight' fast path for 518 / 604 only, as its own pre-registration, the hover sweep kept as fallback; (2) a CPU re-staging on OPEN ground for the Roughs (757 had one visible FIT floor item) before any GPU item class; (3) stage_items.py: spots away from tree models, Poporings cleared first."
title: "Target items from pixels: staged Rough Elunium / Rough Oridecon / Dead Branch / Honey on pay_fild07, template matching, held-out spots (pre-registered)"
date: 2026-10-24
owner: Batt
---

# Target items from pixels (pre-registered)

**Batt (2026-10-24 ~16:0x ICT, translated from Thai):** "Try training the target drop items, e.g.
Rough Elunium, Rough Oridecon, Dead Branch, for pickup accuracy." The targets are his four: Rough
Elunium (757), Rough Oridecon (756), Dead Branch (604), Honey (518), the high-value items players
vend. The Thief bot (Base 50) hunts pay_fild07 (pre-renewal); its loot step today is item-agnostic
(it hovers ground cells for the client's pickup cursor, ~25 hovers, ~11 s per kill). Seeing the
targets from pixels would let a later bot version prioritise them and click them directly ("loot
by sight").

This file is committed BEFORE any frame's pixels are read (FIT or TEST, of any session). Its commit
time is the pre-registration time. A rule or a parameter below changes only by a clock-labelled
AMENDMENT written BEFORE the step it changes. **Read before this commit:** the packets of the four
sessions (event counts, floor-item spans, lifetimes, the Poporing next to the looted items), their
manifests, the staging tool's events.jsonl, the staged session's frame INDEX (the timestamps in its
per-frame JSON; no PNG decoded), and `target_items.py inventory` (packet-only label counts per
split, with the provisional 36-px geometry of 3c). No pixel was read.

## AMENDMENT A (written 2026-10-24 18:00 ICT from `date`; the commit time of this amendment is its time. AFTER the first FIT run, BEFORE the freeze and BEFORE any TEST or TEST-NEG frame is read)

**What happened:** section 4.2's builder returned NO template for 757 (Rough Elunium); 756, 604
and 518 built (sizes 11 x 14, 12 x 18, 21 x 19 px; alignment medians 0-1 px). 757's 55 FIT samples
come from 4 floor items: 131 (spot 2, 10 samples), 139 (spot 4, 15), 143 (spot 5, 17), 147 (spot
6, 13). By eye on the FIT crops (Claude, 2026-10-24 ~17:58, `scratch/s757.png`): 131 lies under a
willow's hanging branches (the rock shows through, partly), 139 under a willow (barely visible),
147 under a leaf canopy (not visible at all); only 143 (open dirt) shows the rock. The median of
the seeded windows is the ground's colour (centre RGB 47 / 81 / 28 vs the ring's 49 / 84 / 33),
so the foreground mask fails. Lowering the mask threshold (30 / 24 / 18) builds templates of
grass and leaves (anchors -12 / -11 / -13 px): not a fix.

**The change (the only one; 757 only):** for an item whose builder returns no template, the
template samples are restricted to the floor items judged VISIBLE by eye on the FIT crops: for
757, floor id **143** (17 samples; the sprite is the same for every floor item of an id). Its
alignment check (4.4) runs on those samples. Everything else is unchanged: 757's threshold (4.5) is
chosen on ALL its FIT labels (occluded ones included) and FIT-NEG, and TEST counts every labelled
757 as pre-registered.

**Reported:** the canopy is the main limit seen on FIT: by eye on the FIT contact sheet, spot 1's
four items are under a canopy in every view, spots 2 / 4 / 6 have one to four items under
trees; spots 0, 3, 5 are open ground. Measured numbers come with the result.

## 1. The data and what the packets say (OFFLINE ground truth, ADR-0007)

| set | recording (NAS) | frames | what the packets say |
|---|---|---|---|
| STAGED | `20261024T170356-rdp-stage-items-b` (1 fps PNG, 1280 x 720 game region, the hunt layout, RDP) | 1,538 | 12 spots; at each, 4 fresh drops (`fall`) of the targets, one each (spot 0: stacks of 2-3, the same sprite); every same-map @warp is a `map_change` and the items come back `in_sight` (same floor id) |
| NEG | `20261024T123622-rdp-thief-t1b`, `20261024T131838-rdp-thief-t2` (4.03 hunts, 1 fps PNG) | 2,271 + 2,292 | NO target item ever appears; other floor items do (907 x 38, 948 x 4, 919 x 3, 938 x 2, 643, 5015, 507): the realistic confusers; both start on prt_fild08 |
| PILOT | `20261024T164555-rdp-thief-s-pilot` (4.04 pilot, 1 fps PNG) | 523 | ONE natural target: Dead Branch floor id 117, fell 158.3 s after the first frame at (113, 183) sub (9, 9); picked up by the bot at 169.9 s; also 7 x 907 |

- **The staged items' lives:** 40 of 48 lived exactly 60.0 s (the server's expiry). **All eight
  of spots 7 and 8 were LOOTED by a Poporing** within 0.2-4.2 s of their fall (the packets show the
  Poporing walking onto each item's cell just before its vanish). So spots 7 and 8 have no
  labelled item; their frames still count as frames where a detection is false (3c, 5).
- At each spot the four drops take ~20 s (one every ~4-6 s, the inventory window open); the five
  still views follow (offset (0, 0) right after the last drop, then (+3, 0), (0, +3), (-3, 0),
  (0, -3) by same-map @warp, ~16.7 s apart). Items alive per view (packets, spots 0-6 and 9-11):
  4, 4, 4 falling to 3 (the first drop expires; at spot 0 just before the view), 1 falling to 0,
  then 0: the 5th view (0, -3) never shows an item, the 4th at most one, briefly.

## 2. The split (fixed now)

- **By SPOT, as the brief proposed:** spots 0-7 = **FIT** (templates, anchors, the threshold),
  spots 8-11 = **TEST** (never read before the freeze). A spot's frames are its still windows
  (3a).
- **FIT-NEG (the threshold's negatives, read on FIT):** (i) every FIT still-window frame
  (detections away from every present item of the same id are false), and (ii) the PILOT's frames
  on pay_fild07 (from its map change + 5 s) OUTSIDE [the Dead Branch's fall - 60 s, its vanish +
  60 s]. Why (ii): the staged frames alone have no walking, no other floor item and only 8 places;
  the threshold must not be fitted on the TEST negatives either. The pilot's Dead Branch window
  stays a separate natural case (section 6).
- **TEST-NEG:** every frame of NEG (t1b + t2) while on pay_fild07 (from each pay_fild07 map
  change + 5 s, `map_spans`), never read before the freeze.
- **The inventory** (`target_items.py inventory`, packets only, with 3c's provisional 36-px
  SAMPLE_BOX: the counts move a little once the anchors exist):

| split | frames | labelled + fully in view (757 / 756 / 604 / 518) | floor items | exclusions (items) |
|---|---|---|---|---|
| FIT (spots 0-7) | 285 | 93 / 87 / 123 / 155 | 6 / 6 / 7 / 7 | under_self 78, stacked 40, under_unit 32, vanishing 2 |
| TEST (spots 8-11) | 113 | 35 / 38 / 36 / 43 | 3 / 3 / 3 / 3 | under_self 35, under_unit 7, vanishing 4 |

- **Honest limit:** TEST is 3 floor items per id (spots 9, 10, 11), one session, one character,
  one afternoon's light. It measures held-out PLACES and moments, not sessions. A per-instance
  recall is reported beside the pooled one.

## 3. The label rule (`scripts/target_items.py`, reusing `item_labels.py`'s pure parts)

**3a. Frames.** A STAGED frame is evaluated when its capture time (the per-frame JSON's
`t_mono_ns`, the packets' clock) lies in a still window: [a `still` event + `STILL_LEAD_S` = 0.5 s,
the first `map_change` packet after it), at most `STILL_MAX_S` = 8.0 s after it (the next @warp
ends the view; the 5-s sleep is followed by the typing of the next line). Frame exclusions:
`item_truth_unknown` (before the first map change), `self_moving` (our position not the same cell
at every 0.1-s step of [t_f - 0.8 s, t_f], item_labels' STILL_S), `self_dead`, and
`ui_layout_mismatch` (`client_layout.read` on the frame's pixels is not `hunt`: e.g. the chat tab
switched while a GM line is typed). The drop phase (inventory open, an icon dragged under the
cursor) is never evaluated.

**3b. Which items, and when.** `item_labels.floor_items` (appear .. vanish or our map change; a
re-appearance after a @warp is a new span) and `item_labels.phase` with **`D_APPEAR` = 2.2 s,
`D_GONE` = 0.6 s: item-class.md 8a's frozen values** (the client's display rule; not re-measured).
An item is PRESENT on a frame while `t_a <= t_f < t_v + D_GONE`; LABELLED while `phase == on`.

**3c. Where.** The item's cell = `(x + OX[sub_x], y + OY[sub_y])` with **item-class.md 8a's
measured sub-cell table** (OX -0.189 / 0 / +0.185 / +0.376, OY -0.210 / 0 / +0.173 / +0.329 for
sub 3 / 6 / 9 / 12; the client's rule is map-independent), projected by `item_labels.Geo`
(labels_v2.project_cell: camera_rdp.json, pay_fild07's GAT, the camera on our still cell). The
predicted sprite CENTRE = that ground point + the item's ANCHOR (px, per item id, measured on FIT,
section 4). The item's BOX for every exclusion = a square of `ITEM_BOX` = 28 px on the centre
(before the anchors exist, FIT sampling and the inventory use `SAMPLE_BOX` = 36 px on the ground
point).

**3d. Item exclusions** (an excluded item stays PRESENT: a detection on it is not false; it is not
in the recall denominator):
- `hidden` (wholly under a UI window of `client_layout.RECTS["hunt"]` or off the region): not
  drawn, dropped; `ui_partial`, `edge_partial`: partly;
- `under_self`: the box overlaps our own box (labels_v2.self_label, 34 x 74 at our feet, + 4 px);
- `under_unit`: the box overlaps any other unit's generic box (60 px wide, 100 px above its
  projected anchor to 6 px below) at any 0.1-s step of [t_f - 1.0 s, t_f] (frames lag the server
  ~0.5 s): monsters (Poporing, Willow, Elder Willow, Eggyra, Bigfoot), players, NPCs;
- `stacked`: two present items' boxes with IoU >= 0.5 (both);
- `settling` / `vanishing` (3b's phases).
- **Map models (trees) are NOT excluded**: the packets cannot place a canopy. A target under a
  tree stays in the denominator (conservative); the TEST misses are looked at by eye and the
  canopy share reported (labelled as by eye, not a measurement).
- "**Fully in view**" = labelled with no exclusion: the recall denominator.

## 4. The detector, and what FIT measures (then FROZEN)

**The detector (pixels only; `target_items.scan`):** per item id one template (RGB + the mask of
the item's own pixels). Over the WHOLE 1280 x 720 frame: the masked colour NCC
(`item_icons.match_maps`), its local maxima within +-2 px with NCC >= `CAND_NCC` = 0.45, centres
inside the hunt layout's UI rectangles or our own sprite's FIXED screen box (labels_v2's player box
at the camera target + 4 px: a constant, the camera follows us) dropped, greedy NMS within 10 px by
NCC; per candidate also the masked RMS colour distance and the INLIER share (item_icons' rule:
mask pixels within 32 of the template in every channel). A DETECTION = a candidate with NCC >=
`t_ncc`, RMS <= `t_rms` and inlier share >= `t_inl` (per item, frozen).

**FIT, in this order:**
1. **Samples** (per item): FIT still-window frames passing 3a's packet rules, the item labelled and
   fully in view under the 36-px SAMPLE_BOX, aged >= 2.5 s and >= 1.0 s before its vanish, no other
   present item's ground point within 24 px, its ground point >= 44 px inside the region and >= 30
   px from every UI window (item_labels' sampling margins). A crop of 89 x 89 px around the
   projected ground point. No per-instance cap (each floor item gives <= ~25 frames).
2. **Templates** (`build_seeded`; client-derived, /dev/shm only): every crop's sprite centre starts
   at the SEED (+2 px down, -5 px left of the ground point: item-class's prt_fild08 anchors), a
   29 x 29 window (`HALF` = 14); item_icons' foreground mask (pixels off their crop's own ground in
   >= 60 % of the crops; the largest components), re-centred on the mask's centroid, the median and
   the consistency mask (MAD <= 40, when it keeps >= half); then each crop re-aligned by masked NCC
   within +-6 px and the best 80 % kept; 4 rounds. The template = the median cut to the mask's
   tight box. **`MIN_SAMPLES` = 12**, else the item has no template (no verdict).
3. **The anchor** (per item) = the median sprite-centre offset from the ground point of the kept
   crops.
4. **The alignment check (a STOP):** on the FIT samples, the best-NCC position within +-8 px of the
   predicted centre; if an item's median |dx| or |dy| exceeds **3 px**, the labels are misaligned:
   stop and report with frame names and offsets (no threshold, no TEST read).
5. **The threshold** (per item): from FIT's candidates, over the grid `t_ncc` 0.45 .. 0.98 (step
   0.01) x `t_rms` 15 .. 80 (step 5) or none x `t_inl` 0.0 .. 0.9 (step 0.1): the triple with the
   **highest FIT recall** (3d's labelled items of FIT spots, the 28-px geometry, a detection within
   6 px) **subject to FIT-NEG false detections <= `FIT_FALSE_MAX` = 0.5 per 100 FIT-NEG frames**
   (half of the TEST-NEG bar: a margin); ties: fewer false, the higher NCC, the lower RMS, the
   higher inlier share. False on FIT-NEG = a detection of item i not within 6 px (Chebyshev) of a
   PRESENT floor item of id i.
- **Frozen:** `params.json` (every constant of sections 3-5, the anchors, the thresholds, the
  template sizes) + `templates.npz`, both under /dev/shm/poring-lab-tmp/target-items/params/,
  their sha256 quoted in section 9 with the clock time, BEFORE any TEST or TEST-NEG frame is read.
  The tool refuses `scan --set test|neg` without the frozen files.

## 5. The measures and the BARS (per item; fixed now)

- **Recall (TEST):** over the TEST frames' labelled, fully-in-view items: the share with a
  detection of the SAME id within **+-6 px** (Chebyshev) of the predicted centre. **Bar: >= 80 %.**
- **Precision (TEST):** over every detection of item i on TEST frames (spots 8-11, 3a): the share
  within 6 px of a PRESENT floor item of id i (labelled or excluded, any phase). **Bar: >= 90 %.**
  (No detection at all: no precision, the item fails.)
- **False detections (TEST-NEG):** detections of item i per 100 TEST-NEG frames (every one is
  false: no target is on the floor). **Bar: <= 1.0.**
- **An item PASSES** only with all three bars; with fewer than `N_MIN` = 20 labelled TEST items it
  has NO verdict.
- **Reported, no bar:** FIT recall and FIT-NEG rate at the frozen threshold; per-instance TEST
  recall; the misses by eye (canopy, cursor, name tags, a monster); the item sizes (px); the
  candidates' counts; and, AFTER the verdict and labelled NOT the verdict, the curves of TEST
  recall and TEST-NEG false rate against `t_ncc`.

## 6. The natural Dead Branch (PILOT; reported, no bar)

The pilot's frames in [its fall + D_APPEAR, its vanish): per frame the frozen detector's 604
detections, the predicted centre when our character is still (3a's rule), and the distance of the
nearest 604 detection. **FOUND** = a 604 detection within 6 px of the predicted centre on at least
one still frame; while we walk, the projection is off (the frame lag), so moving frames report the
nearest 604 detection anywhere in the region and its distance, as context only.

## 7. The recommendation (written with the result)

- **(a)** template matching is enough for a "loot by sight" bot version, for the items that PASS
  (which ones); or
- **(b)** it is not (for the others): what a learned detector would need (an item class trained on
  the GPU later, under R1-R3; the parent decides), with an estimate of the staged spots / frames per
  item, and what limits it, with numbers: the item size in px, the forest background (the FIT-NEG /
  TEST-NEG false rates), occlusion by our character / monsters (3d's counts) / trees (by eye), and
  the 60-s life plus the Poporing looting (section 1).

## 8. Rules of this study

- Packets are labels only; the detector reads pixels only (a fixed UI rectangle set and our own
  fixed sprite box are constants of the client, not packet data).
- Client-derived outputs (frames, crops, templates, candidates, label files): ONLY
  /dev/shm/poring-lab-tmp/target-items/. Code, tests (pure parts, synthetic data) and this doc in
  the repo. Item names: ids and plain English labels.
- Offline CPU only (`nice -n 15`), no GPU, no live action.

## 9. RESULTS (appended below, clock-labelled; nothing above this line is edited after the pre-registration commit except by a labelled AMENDMENT)

### 9a. FIT and the FREEZE (2026-10-24; clock times from `date` and the commits)

**The order of events** (commit times; file times of the scratch outputs): pre-registration
fbc077e 17:48:17; the FIRST pixel read of the study, a FIT frame (spot 1) 17:53:42
(`scratch/fit_look_202.png`); the FIT contact sheet 17:54:13; the first FIT run ended 17:58:41
(757: no template); the 757 crops sheet 18:00:12; amendment A b0bdc10 18:00:54; the FIT re-run
ended 18:05:34; **FROZEN 2026-10-24 18:05:45 +0700**: `params.json` sha256 `ed19713cda41ad9b08deb74e0bb23a9588d7f1f40bedcbaaff474f8fb2c882af`,
`templates.npz` sha256 `345d895011dc4b02314124f7cfd366a418f904d537efbc1370f7e9ad13468ce2`
(/dev/shm/poring-lab-tmp/target-items/params/). No TEST (spots 8-11) or TEST-NEG (t1b, t2) frame
had been read; the pilot's Dead Branch window (section 6) neither.

**The FIT measurements** (FIT eval frames 285, all `ok`, none `ui_layout_mismatch`; FIT-NEG = those
285 + 366 pilot frames = 651):

| item | FIT samples (floor items) | template built from | template h x w px (mask px) | anchor du / dv px | alignment median abs dx / dy (NCC median, p10) | threshold NCC / RMS / inlier | FIT recall (labelled) | FIT-NEG false / 100 frames | candidates / frame (NCC >= 0.45) |
|---|---|---|---|---|---|---|---|---|---|
| 757 Rough Elunium | 55 (4) | floor 143 only (amendment A), 16 kept | 14 x 16 (136) | -5.5 / +0.5 | 0 / 0 (0.977, 0.967) | 0.90 / 20 / 0.8 | 0.266 (94) | 0.0 | 62.8 |
| 756 Rough Oridecon | 81 (5) | all, 68 kept (5) | 11 x 14 (71) | -4.5 / +1.0 | 1 / 1 (0.782, 0.149) | 0.78 / 35 / 0.8 | 0.516 (95) | 0.0 | 12.4 |
| 604 Dead Branch | 104 (6) | all, 84 kept (5) | 12 x 18 (73) | -6.5 / +3.5 | 0 / 0 (0.838, 0.340) | 0.75 / 25 / 0.7 | 0.618 (131) | 0.0 | 184.6 |
| 518 Honey | 135 (7) | all, 112 kept (7) | 21 x 19 (265) | -5.0 / +1.0 | 0 / 0 (0.925, 0.312) | 0.72 / 55 / 0.7 | 0.639 (155) | 0.0 | 298.4 |

- **Correction to amendment A's text:** its "by eye ... ~17:58" is an estimate and wrong: the 757
  crops sheet was written at 18:00:12 (file time) and looked at right after; the amendment itself
  is its commit, 18:00:54. Nothing else in it changes.
- No alignment STOP (all medians <= 1 px): the packet labels sit on the sprites.
- **FIT recall is 0.27-0.64 at zero FIT-NEG false detections.** The FIT spots' canopy (amendment A's
  by-eye note: spot 1 all four items, spots 2 / 4 / 6 some) is in that denominator by the
  pre-registration (3d), so FIT already predicts TEST recall well under 80 % unless the TEST spots
  are open ground. Written here before any TEST read.

### 9b. RESULT (committed 2026-10-24 18:31:23, 5ed077c; clock times from `date` and file times)

**The order of events (after 9a):** the first TEST read 18:06:32 (`scan --set test`, 18 minutes
after the pre-registration commit 17:48:17 and 47 s after the freeze 18:05:45); the pilot's Dead
Branch window 18:07; TEST-NEG (t1b + t2) 18:07:29-18:29:29; `score` 18:29:36. TEST frames: 113,
all `ok` (none `ui_layout_mismatch`); TEST-NEG frames: 4,392 (pay_fild07 only).

**THE VERDICT (section 5, as written): ALL FOUR ITEMS FAIL** (the recall bar; the other two bars
pass for every item).

| item | threshold NCC / RMS / inlier | TEST labelled (floor items) | recall (bar >= 80 %) | per floor item (spot 9 / 10 / 11) | precision (bar >= 90 %) | TEST-NEG false / 100 frames (bar <= 1.0) | verdict |
|---|---|---|---|---|---|---|---|
| 757 Rough Elunium | 0.90 / 20 / 0.8 | 42 (3) | **19.0 %** (8) | 8/14, 0/14, 0/14 | 100 % (8 / 8) | **0.0** (0 in 4,392) | **FAIL** |
| 756 Rough Oridecon | 0.78 / 35 / 0.8 | 45 (3) | **40.0 %** (18) | 10/18, 8/15, 0/12 | 100 % (18 / 18) | **0.0** | **FAIL** |
| 604 Dead Branch | 0.75 / 25 / 0.7 | 36 (3) | **66.7 %** (24) | 12/13, 12/15, 0/8 | 100 % (24 / 24) | **0.0** | **FAIL** |
| 518 Honey | 0.72 / 55 / 0.7 | 51 (3) | **66.7 %** (34) | 19/19, 15/15, 0/17 | 100 % (34 / 34) | **0.0** | **FAIL** |

- TEST item exclusions (not in the denominators): under_self 13, under_unit 5; no stacked, UI or
  edge case. Spot 8 (looted, section 1) adds frames only: no detection there.
- Not one false detection anywhere: 0 on the 113 TEST frames away from the items, 0 on 4,392
  hunting frames (walking and fighting frames, with Resin 907 and the other floor items of
  section 1 as confusers).

**The natural Dead Branch (PILOT, section 6): FOUND.** All 9 frames of its window ([fall + 2.2 s,
the pickup at 169.9 s): frames 000000153-000000161) had our character still, and on every one the
frozen 604 detector put exactly one detection **0.8 px** from the predicted centre (NCC 0.83 >=
0.75). No other 604 detection in those frames.

**Why recall fails (measured; the by-eye parts labelled):**
1. **Trees: 51 of the 174 labelled TEST items (29.3 %) have NO candidate at all** (masked NCC <
   0.45 within 6 px): every one is at spot 11, which stands under a willow (by eye, contact sheet
   `scratch/test_sheet_1.png`: the hanging branches cover all four items in every view). On FIT the
   same measure is 177 of 475 labels (37.3 %; spot 1 under a canopy, spots 2 / 4 / 6 partly, by
   eye). No pixel detector, template or learned, finds an item the client draws under a canopy.
   **On this TEST set they cap recall below the 80 % bar for EVERY item, even for a perfect
   detector:** 757 28 / 42 = 66.7 %, 756 33 / 45 = 73.3 %, 604 28 / 36 = 77.8 %, 518 34 / 51 =
   66.7 %.
2. **On open ground (spots 9-10; POST-HOC, NOT the verdict) at the frozen thresholds:** 518 **100 %**
   (34 / 34), 604 **85.7 %** (24 / 28), 756 54.5 % (18 / 33), 757 28.6 % (8 / 28), still with 0
   false detections in 4,392 hunting frames. By eye on the TEST sheets (one frame per view), the
   open-ground misses are VISIBLE items: 756 on bare dirt (spot 9, view (0, 0)); 757 at the forest
   edge (spot 9, view (+3, 0)) and beside a bush in its shade (spot 10, views (0, 0), (+3, 0),
   (0, +3)); 604 on grass (spot 10, view (0, 0)); and 756 under our own HP / SP bar (spot 10, view
   (+3, 0)): the bar is drawn below our feet, outside the 34 x 74 `under_self` box, so it is an
   occluder the label rule does not exclude.
3. **The FIT-chosen colour gates are what cost the Roughs and the Dead Branch on open ground**
   (POST-HOC, NOT the verdict; `posthoc_curves.json`): with the RMS and inlier gates removed,
   756 reaches 78.8 % on open ground at NCC >= 0.79 with 0.0 false / 100 hunting frames, and 604
   96.4 % at NCC >= 0.76 with 0.02 / 100. For Honey the gates are essential: without them NCC >=
   0.80 alone gives 0.91 false / 100 frames and NCC >= 0.70 gives 100 / 100, while with them it
   stays 0.0 down to NCC 0.62.
4. **757's template comes from ONE floor item** (amendment A: 3 of its 4 FIT floor items lay under
   trees), so its FIT threshold went to NCC 0.90 / RMS 20. On the open TEST spots its best NCC at
   the label has median 0.715 (27 of 28 >= 0.6): the template is too specific to one place's
   light. TEST-NEG candidates were kept only down to the frozen NCC - 0.10, so a lower 757
   threshold cannot be judged on this data.

**What limits it, with numbers:**
- **Item size:** templates (the mask's tight box) 757 14 x 16 px (136 mask px), 756 11 x 14
  (71), 604 12 x 18 (73), 518 21 x 19 (265). The two Roughs are the smallest and the least
  colourful: 756 has 71 sprite pixels.
- **The forest background:** 12-298 NCC >= 0.45 local maxima per frame per item (FIT); the colour
  gates (RMS, inlier share) are what bring false detections to zero (point 3).
- **Occlusion:** trees 29.3 % of TEST labels and 37.3 % of FIT labels with no candidate (point 1);
  our own character 13 TEST labels excluded (`under_self`), monsters 5 (`under_unit`).
- **The 60-s life and the looters:** 40 of 48 staged items lived exactly 60.0 s; 8 of 48 (all of
  spots 7 and 8) were taken by a Poporing 0.2-4.2 s after their fall. At 1 fps, after the 2.2-s
  display delay, a detector has ~57 frames: time is not the limit, the Poporing is.
- **Cost:** the whole-frame scan of 4 templates took ~1.8 s of one core per frame here (4,392
  frames in 1,320 s on 6 workers, PNG decode and the NAS read included); a live version would scan
  a region around the kill, as item_icons.py does (~60 ms per call on 200 x 200, 7 templates).

**THE RECOMMENDATION (section 7):**
- **(a) is NOT met for any item by the pre-registered bars.** The closest are **Honey (518) and
  Dead Branch (604)**: on open ground 100 % and 85.7 % at the frozen thresholds, precision 100 %,
  zero false detections in 4,392 hunting frames, and the natural Dead Branch found 0.8 px from its
  cell. A "loot by sight" version could ADD them as a fast path (a seen 518 / 604 clicked
  directly) while the hover sweep stays the fallback for everything else; that is a new, live
  pre-registration (the parent and Batt decide), not a conclusion of this one.
- **(b) for the Roughs (757, 756), and for any target under a tree:**
  - Under a canopy the item is not drawn visibly: no detector fixes that. The bot keeps a non-visual
    fallback there (the hover sweep), or a camera step; the staging should pick OPEN-ground spots.
  - **Before any GPU:** re-stage on open ground for more VISIBLE floor items per Rough (757 had 1,
    756 had 5) and fit the gates on more of them (multi-template per lighting), with FIT-NEG from
    real hunting frames. It is CPU-only and reuses this tool.
  - **A learned item class (GPU later, R1-R3; the parent decides): an ESTIMATE, not a measurement.**
    ~300 visible labelled boxes per item from >= 30 floor items. Measured yield here: 12 spots gave
    3 floor items per id at TEST and 4-7 at FIT; after the looters (2 of 12 spots) and the trees
    (29-37 % of labels), ~8-10 visible labelled frames per item per spot. So ~30-40 open-ground
    spots, i.e. 3-4 staging runs like this one (27 min each: 1,636 s for 12 spots), ~1.5-2 h.
    Packets cannot tell a canopy, so its labels also need a visibility rule (a blind check of the
    boxes or a map-model mask) before any training.
- **For the next staging run (stage_items.py):** choose spots away from tree models, and clear or
  avoid Poporings near the spot first.

**Scratch** (client-derived, never committed or shipped). KEPT in
/dev/shm/poring-lab-tmp/target-items/ (4.2 MB, for a re-score or the parent's decision): the
frozen `params/` (params.json, templates.npz, frozen.json, fit_report.json), `scan/` (the
candidates of TEST, TEST-NEG and the pilot window), score.json, the post-hoc JSONs, the logs.
DELETED 2026-10-24 18:32: the contact sheets and crop sheets (`scratch/`, 11 MB), the FIT sample
crops (8.6 MB), the FIT candidates (8.5 MB), the frame indexes (0.7 MB; rebuilt on demand).

## 10. PRE-REGISTERED: round 2 (open ground)

**Batt's ask stands** (2026-10-24 ~16:0x: "train the target drop items ... for pickup accuracy").
Round 1 (sections 1-9) failed the recall bar for all four items, mostly because trees hid 29 % of
its TEST labels and the Roughs' templates came from too few visible floor items (9b). Its three
recommendations are what this round tests: staging on OPEN ground (done: stage-c below),
MULTI-templates per item, and FIT-NEG from real hunting frames.

This section is committed BEFORE any round-2 frame's pixels are read. Its commit time is the
pre-registration time; a rule below changes only by a clock-labelled AMENDMENT (10.8) written
BEFORE the step it changes. Sections 1-9 are round 1's and stay as they are. **Read before this
commit (no pixel of stage-c, s4, s5, s6 was decoded):** the packets of stage-c, t1b, t2, s1, s2,
s4, s5, s6 (floor items, lifetimes, map spans), stage-c's manifest and events.jsonl, the frame
indexes (tar headers and per-frame JSON only), the canopy mask stage@2 used, round 1's outputs
(`/dev/shm/poring-lab-tmp/target-items/`, read-only), and `target_items_r2.py inventory`
(packet-only counts, 10.2). The code (`scripts/target_items_r2.py`, tests
`services/backend/tests/test_target_items_r2.py`, synthetic data only) is in this commit.

### 10.1 The data (OFFLINE ground truth, ADR-0007)

| set | recording (NAS) | what the packets say | role |
|---|---|---|---|
| STAGE-C | `20261024T222352-rdp-stage-items-c` (1,554 frames, 1 fps PNG, RDP, the hunt layout), events `/dev/shm/poring-lab-demo/20261024T222356-stage-items-pay_fild07-c/events.jsonl` | stage@2 `--open`, seed 8, 2026-10-24 22:23-22:51: 12 spots outside the RSW tall-model footprints (widened 3 cells, 6 north), the same four items dropped at each; 48 falls. Items alive the full 60.0 s at spots 0, 3, 4, 6, 8, 10, 11; EARLY vanishes (looted: 0.2-20 s after the fall) at spots 1 (0.2-3.9 s), 2 (2.9-15.5 s), 5 (1.1-1.7 s), 7 (8.8-20.1 s), 9 (0.5-2.6 s) | FIT spots 0-7, TEST spots 8-11 |
| STAGE-B | `20261024T170356-rdp-stage-items-b` (round 1's staging; READ in round 1) | section 1 | FIT: spots 0, 3, 5, 9, 10 only |
| t1b | `20261024T123622-rdp-thief-t1b` (4.03 hunt) | no target item; 2,400 s on pay_fild07 | FIT-NEG |
| s4, s5 | `20261024T193810-rdp-thief-s4`, `20261024T201949-rdp-thief-s5` (4.04 hunts) | no target item; 2,405 s + 2,400 s on pay_fild07 | TEST-NEG |
| NATURAL | the 4.04 pilot `20261024T164555-rdp-thief-s-pilot` and s6 `20261024T210115-rdp-thief-s6` | the pilot's Dead Branch (floor 117, section 6); s6: Rough Elunium 291 at (114, 161) living 2.4 s, Dead Branch 293 / 296 / 304 living 3.4 / 1.0 / 4.5 s (the bot picked them up) | reported, no bar |

- Not used: t2 (round 1's TEST-NEG; kept unread by round 2 as a reserve), s1, s2 (no target item
  either), s3 (staged items back from a looter), stage-b's spots 1, 2, 4, 6, 11 (under trees by
  eye in round 1) and 7, 8 (looted).
- The canopy mask stage@2 used is NOT a usable visibility rule for stage-b: it puts 47 of stage-b's
  48 falls inside the widened footprints, including round 1's open spots 0, 3, 5, 9, 10 where
  Honey was found 100 % (9b). Stage-b's spots are therefore chosen by round 1's by-eye notes
  (amendment A: spots 0, 3, 5 open ground; 9b: spots 9-10 open, spot 11 under a willow), written
  before this round.

### 10.2 The split (fixed now)

- **FIT** = stage-c spots 0-7 + stage-b spots 0, 3, 5, 9, 10 (templates, variants, anchors,
  thresholds). Why stage-b: stage-c's FIT spots give only 4 floor items per id that live the full
  60 s (spots 0, 3, 4, 6); stage-b's five open spots add 5 more per id from other places and other
  light (another afternoon), which is what the multi-templates need. Stage-b's spots 9 and 10 were
  round 1's TEST: they are not round 2's TEST, so they may be FIT here.
- **TEST** = stage-c spots 8-11 (spot 9's items vanished within 2.6 s: frames only, like round 1's
  spots 7-8). Never read before the freeze.
- **FIT-NEG** = (i) every FIT still-window frame (detections away from every present item of the
  same id are false) and (ii) t1b's frames on pay_fild07 (from each pay_fild07 map change + 5 s).
  Why t1b: round 1 read it only through its frozen detector's scan (no frame looked at, no
  parameter fitted on it), it is a real hunt (walking, fighting, Resin 907 and other floor items,
  name tags, skill effects), and it keeps both 4.04 sessions below unseen.
- **TEST-NEG** = s4 + s5's frames on pay_fild07 (same span rule), never read by any target-item
  detector before the freeze. Why not t2: s4 and s5 were never scanned in any round, they are the
  4.04 runner (Steal casts, its own UI states) rather than the 4.03 one FIT-NEG comes from, and
  together they are ~4,700 frames (round 1's TEST-NEG: 4,392).
- **The inventory** (`target_items_r2.py inventory`, packets only, the provisional 36-px
  SAMPLE_BOX geometry; the counts move a little once the anchors exist):

| split | frames (all `ok` by the packets) | labelled + fully in view (757 / 756 / 604 / 518) | floor items | exclusions (item views) |
|---|---|---|---|---|
| FIT | 430 | 83 / 113 / 132 / 142 | 8 / 9 / 9 / 9 | under_self_bar 103, under_self 84, stacked 40, under_unit 16, vanishing 8 |
| TEST | 138 | 37 / 47 / 40 / 61 | 3 / 3 / 3 / 3 | under_self_bar 38, under_unit 14, vanishing 3 |

- **Honest limit (as round 1):** TEST is 3 floor items per id (stage-c spots 8, 10, 11), one
  session, one character, one evening. Per-floor-item recall is reported beside the pooled one.

### 10.3 The label rule: round 1's section 3 with ONE change

Round 1's section 3 applies unchanged (frames in the still windows, `D_APPEAR` 2.2 s / `D_GONE`
0.6 s, the sub-cell table, the 28-px ITEM_BOX, the exclusions; trees are NOT excluded), with one
addition: **`under_self_bar`**: an item whose box touches our own HP / SP bar's box, `BAR` =
(-36, 0, +36, +24) px around our feet (the projection of our cell; x right, y down), is excluded
like `under_self` (it stays PRESENT). Why: round 1's 9b saw a TEST 756 centred (-32, +19) px from
our feet hidden under the bar, outside the 34 x 74 self box. The box is a generous guess around
that observation, not a measurement. The same box at the camera target is added to the detector's
fixed no-go boxes (10.4). **Reported beside the verdict, not the verdict:** TEST recall under
round 1's rule (the bar exclusion off).

### 10.4 The detector: MULTI-templates (then FROZEN)

**Per item one sprite MASK and K colour VARIANTS:**
1. **Samples:** round 1's section 4.1 rules (the item labelled and fully in view under the 36-px
   SAMPLE_BOX, aged >= 2.5 s, >= 1.0 s before its vanish, no other item's ground point within
   24 px, the region and UI margins), on the FIT frames of both sessions, `ui_layout` `hunt` only;
   89 x 89 crops around the projected ground point.
2. **The pooled template:** round 1's `build_seeded` (unchanged maths, now `build_seeded_core`)
   on ALL of the item's FIT samples: the mask (the tight box), the median colours (variant 0), the
   anchor (the median sprite-centre offset of the kept crops). `MIN_SAMPLES` = 12, else the item
   has no template and NO verdict. There is no visible-floor-item filter this time (round 1's
   amendment A is not carried over); any rescue needs an amendment before the freeze.
3. **The variants (several samples, views, places):** for every FIT floor item ("place") with >=
   `MIN_PLACE_SAMPLES` = 5 crops kept by the pooled build, the median of those crops' final
   windows (aligned by the pooled build), cut to the pooled tight box, under the pooled mask. A
   place's variant pools its views (the 4 @warp offsets put it at different screen positions);
   the floor sprite has one state (no animation; the fresh-drop phase is excluded by `D_APPEAR`).
   Variants = [pooled, place 1, place 2, ...].
4. **The alignment check (a STOP):** round 1's 4.4 with the pooled template on all FIT samples
   (median |dx| or |dy| > 3 px: stop, no threshold, no TEST read).
5. **The scan (pixels only, `scan_multi`):** over the whole 1280 x 720 frame, the POOLED
   template's masked colour NCC (`item_icons.match_maps`); its local maxima within +-2 px with NCC
   >= `GEN_NCC` = 0.35 whose centres lie outside the hunt layout's UI rectangles, our own sprite's
   fixed box (round 1) and our bar's fixed box (10.3); each re-scored by EVERY variant at every
   offset within +-2 px (the same masked NCC, RMS colour distance and inlier share as round 1,
   computed directly) and moved to its best (variant, offset) by NCC; kept with NCC >=
   `CAND_NCC` = 0.45 and a centre still outside the no-go boxes; greedy NMS within 10 px by NCC.
   A candidate carries the best variant's NCC, RMS and inlier share. A DETECTION = a candidate
   with NCC >= `t_ncc`, RMS <= `t_rms`, inlier share >= `t_inl` (per item, frozen).
6. **The colour gates and the threshold (per item, on FIT):** round 1's 4.5 unchanged: the grid
   `t_ncc` 0.45 .. 0.98 x `t_rms` 15 .. 80 or none x `t_inl` 0.0 .. 0.9; the triple with the
   **highest FIT recall** (the labelled FIT items, 28-px geometry, a detection within 6 px)
   **subject to FIT-NEG <= `FIT_FALSE_MAX` = 0.5 false detections per 100 FIT-NEG frames**; ties:
   fewer false, the higher NCC, the lower RMS, the higher inlier share. False on FIT-NEG = a
   detection not within 6 px (Chebyshev) of a PRESENT floor item of that id (every t1b detection
   is false).
- **Frozen:** `params.json` (every constant, the spots, the sessions, the anchors, the variant
  keys, the thresholds) + `templates.npz` (masks, pooled colours, variants), under
  /dev/shm/poring-lab-tmp/target-items-r2/params/, their sha256 quoted in 10.9 with the clock
  time, BEFORE any TEST, TEST-NEG or NATURAL frame is read. `scan` refuses without them.

### 10.5 The measures and the BARS (per item; the SAME as round 1's section 5)

- **Recall (TEST)** over the labelled, fully-in-view TEST items (10.3): a detection of the same id
  within **+-6 px** of the predicted centre. **Bar >= 80 %.**
- **Precision (TEST)** over every detection of the item on the TEST frames: within 6 px of a
  PRESENT floor item of that id. **Bar >= 90 %** (no detection at all: the item fails).
- **False detections (TEST-NEG):** per 100 TEST-NEG frames (s4 + s5). **Bar <= 1.0.**
- **PASS** only with all three; fewer than `N_MIN` = 20 labelled TEST items: NO verdict.
- **Reported, no bar:** FIT recall and FIT-NEG rate at the frozen threshold; per-floor-item TEST
  recall; which variant made each hit; TEST recall under round 1's rule (10.3); the misses by eye;
  TEST-NEG per session and on non-hunt layouts; and, AFTER the verdict and labelled NOT the
  verdict, the curves of TEST recall and TEST-NEG false rate against `t_ncc`.

### 10.6 The natural cases (reported, no bar)

Section 6's rule on the NATURAL sessions: every frame in [a target's fall + `D_APPEAR`, its
vanish); FOUND = a detection of its id within 6 px of the predicted centre on a frame where our
character is still (3a). The s6 items lived 1.0-4.5 s, so 0-3 frames each are expected, mostly
while we walk to them (then the nearest detection is context only).

### 10.7 The recommendation (written with the result)

Which items qualify for a "loot by sight" fast path (a seen target clicked directly, the hover
sweep kept as the fallback; its live use is its own pre-registration, Batt and the parent decide),
and whether a learned item class (GPU, R1-R3) is still needed, for which items, with the numbers
that limit it.

### 10.8 Amendments (clock-labelled, appended here, each BEFORE the step it changes)

(none yet)

### 10.9 RESULTS (appended below, clock-labelled)
