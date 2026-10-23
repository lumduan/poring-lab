---
doc_type: design
hypothesis: "A detector trained with the class `item` (Route-U frames labelled from the packets, ../planning/item-class.md) finds floor items on held-out sessions of each map with recall and precision >= 0.80."
status: PRE-REGISTERED 2026-10-23 (BEFORE any item label exists and BEFORE any model with an item class exists; amendments only before training starts, clock-labelled)
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../planning/item-class.md, v2orc-vs-v1.md, ../planning/orcsdun01-detector.md]
next_action: "If the item tier of ../planning/item-class.md section 6 passes for a map and a model is trained with the item class: score ONCE, after training ends, as written here."
---

# The item class: per-map recall and precision on held-out data (pre-registered 2026-10-23)

Batt, decision 3 (2026-10-23 ~22:1x): "... pre-register the label checks and the evaluation
(per-map item recall/precision on held-out sessions; then "loot by sight" as a later bot
version)." And: "Score only after training ends, against the pre-registered evaluation
(v2orc-vs-v1.md + the item evaluation)."

**Why a new file, not an amendment of v2orc-vs-v1.md:** the item class has its own data (Route-U
frames of new sessions), its own label rule, its own packs and its own bars. v2orc-vs-v1.md's
monster verdict (P1, G1, G2) stays exactly as pre-registered there and is scored by its own rules
on the same model; nothing here changes it, and nothing there decides this.

## The model

The model trained by the overnight run with the class list `config/detector/classes-v2orc-item.json`
(the 15 classes of `classes-v2orc.json` + `item` at id 15: 16 classes), the item frames of
`../planning/item-class.md` section 6 (Route U, TRAIN data of each map whose item tier passed),
the rest as v2orc-vs-v1.md fixes it (YOLO11n, 30 epochs, seed 20261004, imgsz 1280, batch 2 /
workers 1). The weights scored: `last.pt` at the last epoch, conf 0.25 (v1's and v2orc's).

## The evaluation data (held out, per map)

- **prt_fild08:** the TEST sessions `20261021T223812-demo-hunt-flow54` and
  `20261022T032441-demo-hunt-flow55`.
- **orcsdun01:** the TEST block of the 2026-10-22 Crusader demo, frame times [669.5 s, end] from its
  first frame (`../planning/item-class.md` section 2; the same session as its FIT and TRAIN blocks,
  a stated limit).
- **The frames:** every 3rd frame of each, labelled by `../planning/item-class.md` sections 3a-3f
  (the frozen params; NOT only Route U: the item evaluation scores only `item` detections, so frames
  with monsters are evaluated too; a frame with ANY item exclusion is not evaluated, so every item on
  an evaluated frame is labelled).

## The evaluation pack (after training ends; seed 6)

- Drawn by seed 6 from the TEST data's KEPT item labels: **up to 60 item crops per map** (at most 3
  per floor item) **+ 20 negative crops per map** (empty floor, the same rule as round 1).
- Two NEW blind labeller agents, the same `instructions.txt` as round 1 (byte-identical), the same
  crop format.
- **An item label is EVALUATED when BOTH labellers answer q1 = yes and q2 = good.**
- The negatives decide nothing here; their q1 answers are reported (the labellers' own reliability).

## The scores (fixed now)

Per map, on the frames of the evaluated labels (the position metric of v2orc-vs-v1.md):
- **recall** = the evaluated labels whose box contains the centre of an `item` detection, pairs
  one-to-one per frame (the nearest centre first) / the evaluated labels;
- **precision** = TP / (TP + FP), where TP = the matches above, a detection whose centre lies inside
  another (not evaluated) item label box of the same frame is IGNORED, and FP = an `item` detection
  whose centre lies inside NO item label box of the frame. This is valid because an evaluated frame
  carries a complete item truth (no item exclusion fired on it);
- **the bars, for a map with >= 50 evaluated labels: recall >= 0.80 AND precision >= 0.80.** Fewer:
  reported, no bar.

**Reported, deciding nothing:**
- 3f-style precision (only detections whose centre falls inside an evaluated box, as P1 of
  v2orc-vs-v1.md amendment A);
- recall split by Route U (unit-free) vs frames with monsters on screen; by item id; by fresh vs
  in-sight items;
- the FP detections' places: on a corpse / on a monster's sprite (by the packets' boxes) / elsewhere;
- the item class's confusion with the monster classes (an item label matched by a monster-class
  detection);
- the item class's IoU >= 0.5 precision / recall.

**The verdict:** the item class PASSES on a map if both bars hold there. Passing does not change the
live bot: "loot by sight" (the bot clicking what the detector boxes as `item`) is a LATER bot
version, pre-registered on its own with these numbers as its input.

## The run (plan)

1. The labels, G1 and blind round 1 (`../planning/item-class.md` sections 4-6).
2. The cache and the training: the parent's, with the monsters (the IO rules, R1-R3).
3. After the last epoch: the TEST labels exist already (built with the frozen params before
   training); the seed-6 pack is drawn, judged by two new labellers, then the model's detections are
   scored once with the command written into the result. Results are added below this line, with
   nothing above it edited.
