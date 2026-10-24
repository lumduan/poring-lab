---
doc_type: design
hypothesis: "Batt's four target items (Rough Elunium 757, Rough Oridecon 756, Dead Branch 604, Honey 518), staged on pay_fild07's floor and labelled from the packets, are found from ONE 1-fps frame by per-item masked colour templates built on FIT spots: on held-out TEST spots recall >= 80 % and precision >= 90 % per item within +-6 px, with <= 1 false detection per 100 hunting frames per item."
status: PRE-REGISTERED (the commit time of this file; nothing measured yet)
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [item-class.md, thief-payon.md, ../demonstrations.md, ../../scripts/target_items.py, ../../scripts/stage_items.py, ../../scripts/item_labels.py]
next_action: "Build the FIT templates and the threshold, freeze (sha256 in section 9), then measure TEST, the negatives and the natural Dead Branch; write the result and the recommendation into section 9."
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
