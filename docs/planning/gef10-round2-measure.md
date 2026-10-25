---
doc_type: measurement
hypothesis: "The two holes T1 found on TEST (gef10-detector.md 13r) are measurable on FIT and TRAIN without reading TEST: (1) the client's transient pickup notice can be detected from pixels, and some kept TRAIN labels lie under it; (2) a GAT height-step rule names the labels beside raised terrain, and those labels fit worse than the rest. The counts tell Batt what a round 2 would remove and keep."
status: "MEASURED (offline, FIT/TRAIN only)"
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [gef10-detector.md, rogue-gef10.md, ../benchmarks/gef10-eval.md, ../../scripts/gef10_r2_measure.py, ../../scripts/map_labels.py]
next_action: "Batt decides whether a round 2 is worth it (section 7). Nothing here is frozen or decided: the rules below are CANDIDATES, measured only."
title: "gef10 round 2: the pickup-notice rule and the raised-terrain rule, measured on FIT and TRAIN (no TEST read)"
date: 2026-10-26
owner: Batt
---

# gef10 round 2: two candidate rules, measured on FIT and TRAIN

**Why.** T1 failed on TEST at 03:16 ICT (gef10-detector.md 13r: C1 5 / 61 = 8.2 %, bar 5 %).
Its five bad labels were two sightings in a7: an Orc Warrior under the client's transient pickup
notice, and a Poporing beside the raised rock face east of the orc village. Nothing of gef_fild10
trains this round. Batt decides in the morning whether a round 2 is worth it. This document gives
him the numbers.

**What this is NOT.** It changes no rule, no parameter (`params.json` sha256 `00ef6383...b0aac1`
stays frozen), no label file and no class list. The rules here are CANDIDATES. A round 2 would
need its own pre-registration, a NEW TEST never read before, and T2 again (13r).

**What was read.** Only the FIT parts (the watch's cells 0-10, pilot, pilot2) and the TRAIN
sessions (a2, a4, w2; for the detector's validation also s1, a1, a3, a6, which did not join
TRAIN). **No TEST data was read**: not the watch's cells 11-14, not a7 or a8, not `t1/rows.json`,
and no session recorded after 03:00 ICT tonight. The tool refuses them by name
(`gef10_r2_measure.refuse_test`).

## 1. The choices, stated BEFORE any label was counted (2026-10-26 03:37 ICT, from `date`; committed before the counts)

### 1a. The pickup notice

- **What it looks like** (measured on pilot2's frames 51-58 and 75-78, 0.2-7.2 s after a
  `pickup_result`): a white box with rounded corners, a 1-px neutral grey (~190-200) border line
  2 px inside its edge, white inside, the item's icon and dark text "<item> - 1 obtained.". On
  pilot2 its outer edge is x 541..731, y 76..105 (1280 x 720 game frame); 13r's a7 notice was
  x 541..799, so the LEFT edge stays at x 541 and the width follows the item name. It is drawn for
  about 4-5 s (present 4.2 s after the pickup, gone at 5.2 s on pilot2).
- **The detector** (`find_notices`, pure): in the band y 40-170, x 230-1135 (the top centre,
  between the hotbar and the minimap), a grey row with white rows above and below it (the top
  border line), a second such row 18-40 rows lower (the bottom one; 25 measured), both >= 40 px
  long and overlapping, and a grey border COLUMN with white on both sides at each end. The box is
  the outer white edge.
- **Its validation, against the packets** (an independent sensor that sees the event): POSITIVE
  frames = a `pickup_result` (ok) at most 4.0 s before the frame's capture time; NEGATIVE frames =
  none in the 10 s before. Frames 4-10 s after a pickup are the fade zone: reported per 1-s bin,
  not scored. Every disagreement is listed; a by-eye sheet (client pixels, `/dev/shm` only) shows
  the misses, the false detections and a sample of hits.
- **The rule N (candidate):** a kept label is removed when its box overlaps a detected notice in
  that frame (any area > 0). Reported beside it: the box at least half covered (v1's `visible`
  rule), and the box grown by 16 px (C1's standing rule keeps a box 16 px clear of the UI).

### 1b. Raised terrain

- **The heights** (`gat.Gat.altitude`: each cell's mean corner altitude, world units, up +; one
  cell is 5 units wide) of the client GAT `gef_fild10.gat` (sha256 `cc5f35be...`, client data,
  never committed). A cell's **STEP** = the largest |altitude difference| to its 8 neighbours.
- **The distribution** (`heights`, 03:34 ICT): over the 73,455 walkable cells the step is 0 for
  88 %, p95 1.38, p97.5 3.19, **p99 5.0**, p99.9 11.7; over all 160,000 cells p90 6.56, p99 22.1.
  The rock face east of the orc village is NOT a one-cell wall in the GAT: it is a RAMP of cliff
  cells (type 5) rising 0 -> 40 over about 10 cells (x 286-296 on rows 84-88), each cell 4-10 units
  above its neighbour (cliff cells: step median 6.9, p25 5.3, p10 3.6).
- **H = 5.0 world units** (chosen from that distribution): steeper than 99 % of the walkable
  cells, and one cell's width (a slope over 45 degrees to an orthogonal neighbour); it marks about
  three quarters of the cliff cells.
- **The rule T (candidate):** a kept label is removed when ANY cell within **R = 2** cells
  (Chebyshev) of its cell has a step > H. The label's cell = its unit's Timeline position at
  tw = t - 120 ms (1d), rounded. **R = 1 is reported beside it.** Sensitivity runs at H = 4 and
  H = 8 are reported, never chosen from.
- **The FIT-side check:** the fit NCC (the label file's `ncc`) of the kept labels near a step
  (rule T true) against the rest, on FIT and on all TRAIN-joined parts; and the NCC by the distance
  (cells) to the nearest step > H, in bins 0-2, 3-5, 6-10, 11-15, none within 15.
- **The C1-side check:** the standing labels C1 scores on the TRAIN-joined parts (re-run with
  `map_labels.py check --rows` under the frozen params: 527 scored, 8 bad, the own-C1 numbers of
  13o / 13p reproduced). Do the rules name the bad ones more often than the rest?

### 1c. The counts reported

Per part and per species: the kept labels; the kept labels in WRITTEN frames (what the cache
would write: `build_frame_cache.map_frame` at the floor 0.636, the class list
`classes-v2orc-payf07-gef10.json`; the cache's own self-box rule may drop a few more); and both
after N, after T, and after both. A removed label takes its whole frame out of the cache, as any
excluded monster label does (gef10-detector.md 2), so the written counts also lose the other
labels of that frame.

## 2. RESULT: the notice detector's validation

(appended below)
