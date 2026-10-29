---
doc_type: design
hypothesis: "The 148 staged floor items of E3 + e3b (gef10-eyes-loot.md E3), labelled by gef10-detector.md section 8's frozen-in-shape item rule (packets place each item; its own client sprite gives the box; the anchor and T_item measured on FIT), pass G2 on held-out TEST and a blind round on what trains, so round 3 can add floor-item class(es) to round 2's monster detector without losing its monster accuracy."
status: "PROPOSED (2026-10-29 12:07 ICT from `date`): the split fixed BEFORE any read; ITEM CLASSES DECIDED by Batt 2026-10-29 ~12:2x: option C, ONE pooled `item` class (section 3). Nothing measured, frozen or trained."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [gef10-eyes-loot.md, gef10-detector.md, gef10-eval.md, item-class.md, rogue-gef10.md, target-items.md]
next_action: "Build section 5 offline (synthetic tests first): several staged sessions per map in map_labels, gef10_items label / g2 / pack, Route M. Frames are read only from the NAS copies after the 2026-10-30 03:05 ship; the GPU only after round 2's evaluation."
title: "gef10 round 3 (E5): floor-item classes from the staged sessions, on top of round 2's monsters (PROPOSED pre-registration)"
date: 2026-10-29
owner: Batt
---

# gef10 round 3 (E5): floor items from the staged sessions (PROPOSED)

**Batt, 2026-10-29 ~11:3x (translated):** "E5 (labels): go ahead, but do not let it affect the
other work." The plan is gef10-eyes-loot.md E5. This document is its pre-registration, written
before any frame of the staged sessions is read under the item rule.

## 1. What is held fixed, and what is not touched

- **Round 2 is not touched.** Its training (gef10-detector.md 13z) and its evaluation
  (gef10-eval.md, `last.pt` after the last completed epoch) go first. Round 3's cache and training
  use the GPU only after that evaluation is recorded (R2: one model at a time; fit-first's VTON is
  a co-tenant and never touched).
- **The monster rules stay frozen** (gef10-detector.md 13n / 13s: o3h-all, the engaged selection
  E2, T_h, the anchors). Round 3 re-uses round 2's monster labels unchanged; any NEW monster
  session (gef10-eyes-loot.md E5's b1, c1, c3-c8, Batt's demo) gets the same frozen labeller, and
  round 2's TEST / TEST2 sessions stay refused.
- **The item rule is gef10-detector.md section 8 ("gef10-items"),** unchanged in shape: the floor
  span (2.2 s settle / 0.6 s vanish margins), the sub-cell table, the item's own client sprite as
  the box, the ANCHOR and T_item measured on FIT (>= 12 clean samples, else STOP), the item
  exclusions, Route M (a cached frame needs the monster labels AND every floor item's label whole).
- **Not affecting other work:** every read of these recordings happens from the NAS copies after
  they ship (2026-10-30 03:05-04:25), under `systemd-run --user --scope -p MemoryMax=4G
  -p MemorySwapMax=0`, outside 09:30-10:15 / 14:00-14:45. No live client step is part of this plan.

## 2. The data and the split (FIXED HERE, before any read)

The staged sessions (immune Rogue, open ground, 1 fps PNG + packets):

| session | spots | staged floor items | role |
|---|---|---|---|
| `20261028T151136-rdp-stage-gef10-e3` (E3) | 0-18 (18 complete; spot 18 dropped 4 of 6) | 112 | TRAIN; spots 0-3 also FIT |
| `20261029T110813-rdp-stage-gef10-e3b` (e3b) | 0-5 | 36 | **TEST3 (held out)** |
| `20261028T160008-rdp-stage-gef10-e3x` | the extra end kill, no item in sight | 0 | not used |

- **TEST3 = e3b, all of it.** No tool has read an e3b frame (the recorder wrote it; the packets
  were read for the safety count and the falls). It is refused by name like round 2's TEST until
  the check that reads it (G2, section 4).
- **FIT = E3 spots 0-3** (the anchor and T_item, section 8's measurement). FIT is not held out
  from TRAIN (round 2 trained on its re-made FIT labels, 13p).
- **What was already read of E3, for the record:** the inventory crops of the drop checks
  (2026-10-28 frames-s18; 2026-10-29's icon study, killed at 10:42). No floor-item label, crop or
  fit was ever made from E3.
- **Expected yield, from the packets only** (rogue-gef10.md AK-3 / AK-6): TRAIN 112 floor items,
  9-11 per class; TEST3 36, 3-4 per class, of which spots 0-1's 12 were looted within 0.3-6.2 s
  (below the 2.2 s settle: no label), leaving 24.

## 3. The item classes: DECIDED -- option C, one pooled `item` class

**Batt, 2026-10-29 ~12:2x (received just before 12:22:33 from `date`):** "choose C". Round 3 adds ONE class, `item`, for every floor item
id (the 11 staged ids and any other). Its bar: >= 40 kept labels from >= 10 floor items in TRAIN
(112 staged floor items in E3), and the blind round's 40 crops at <= 3 per floor item. Cyfar /
Orcish Voucher identity stays with the inventory icons (stage@6). Option A (a Cyfar + Voucher
staging session) stays possible later without changing C's labels. The table below is the choice
as it was put to Batt.


The bars (gef10-detector.md section 7 / 8, unchanged): a class trains only with >= 40 kept labels
from >= 10 floor items in TRAIN AND a blind round of 40 crops per class, AT MOST 3 PER FLOOR ITEM,
taken from what trains. So a separate class needs **>= 14 floor items in TRAIN**.

| option | classes | data now | missing |
|---|---|---|---|
| **A** | round 2's D6: Cyfar, Orcish Voucher, + one pooled `item` class | pooled: ~100 floor items, enough. Cyfar 9, Voucher 10 in TRAIN | Cyfar / Voucher need >= 14 each in TRAIN: one more staged session of Cyfar + Voucher only (~12 spots, ~25 min, immune), recorded on disk |
| **B** | as A, but the blind round takes up to 4 crops per floor item | Cyfar 9 still < 10 floor items | still short for Cyfar |
| **C** | one pooled `item` class only | enough now | nothing; Cyfar / Voucher identity stays with the inventory icons (stage@6's masked match) |

**Recommendation: C now, A later if the bot needs item identity on the floor.** E2 ("loot end by
sight") needs only "is an item still there". C trains with today's data, and A's extra session can
follow without changing C's labels.

## 4. The checks (pre-registered as section 8; per class where classes exist)

1. **The anchor and T_item on FIT** (E3 spots 0-3): >= 12 clean samples from >= 4 floor items
   (round 2's FIT had 15 samples from ONE floor item; this adds the floor-item count), else STOP.
2. **TRAIN labels** under the frozen anchor and T_item; the class bar of section 3.
3. **G2 on TEST3:** the median |dx|, |dy| of the item fit at the frozen anchor <= 3 px, else STOP.
4. **The blind round** (seed 33; item-class.md's instructions byte-identical, sha256
   `7d0a9704...e125c`): per class 40 item crops (at most 3 per floor item) + 20 negatives; two new
   blind labellers; >= 90 % good box and >= 95 % item-present right from EACH.
5. **Route M in the cache** (both label sets whole); then round 3's training and evaluation get
   their own pre-registration (gef10-eval.md's protocol plus an item metric), after round 2's
   evaluation.

**The at-our-feet rule (the E5 decision named in gef10-eyes-loot.md):** KEPT as frozen. Frames with
an item under our own box or HP bar are EXCLUDED from the cache (not labelled empty). E3's (0, 0)
views give no item labels. Its (3, 0) and (0, 3) views were planned for exactly this and do.

## 4a. One detail fixed in code before any read (2026-10-29 12:29 ICT from `date`)

- `under_unit` (section 8: "any unit's predicted box over the item's box") uses the generic unit
  box (60 px wide, 100 px up to 6 px down from the unit's anchor, at tw and tw - 0.5 s). That is
  the box the FIT samples already use (`gef10_items.sample_reason`), and a superset of a unit's
  predicted box. It is conservative: it excludes more frames, never fewer.
- The label fit: +-6 px around the ANCHORED prediction (both its window and its render point
  move by the anchor); `item_unfit` below T_item or at the search edge. G2 refits +-10 px (the
  measurement radius), so an anchor error shows as an offset instead of hitting the edge.

## 5. What has to be built (offline, no GPU, no client)

- ✅ BUILT 2026-10-29: `gef10_items.py freeze / label / g2`. `label` refuses every TEST; `g2` reads
  TEST3 only. Rows are small JSON, within rule 7's limits. Tests on synthetic data (68cfdf6 + this).
- ✅ BUILT 2026-10-29: `gef10_items.py pack` (the blind pack, mirroring item_labels.py's: 40 crops at <= 3 per floor
  item + 20 empty-floor negatives).
- ✅ BUILT 2026-10-29 (68cfdf6): **several staged sessions per map in `map_labels`.** Today a MapSpec has ONE `staged` session and
  one `staged_kind`: GEF10's is the watch, one spot per map change. E3 and e3b are stage_items
  sessions, with one spot per first warp followed by drops (`spot_starts`, 3 views each). A
  per-session kind is needed so that `E3:spots=0-3` means stage_items spots. Round 2's behaviour
  stays pinned by its tests.
- Route M for gef_fild10 in `build_frame_cache.py` (its `item_sessions` path, today
  prt_fild08 / orcsdun01).
- Tests on synthetic data first; the real runs after the ship.
