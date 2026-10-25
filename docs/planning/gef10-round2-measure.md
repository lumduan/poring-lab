---
doc_type: measurement
hypothesis: "The two holes T1 found on TEST (gef10-detector.md 13r) are measurable on FIT and TRAIN without reading TEST: (1) the client's transient pickup notice can be detected from pixels, and some kept TRAIN labels lie under it; (2) a GAT height-step rule names the labels beside raised terrain, and those labels fit worse than the rest. The counts tell Batt what a round 2 would remove and keep."
status: "MEASURED (offline, FIT/TRAIN only)"
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [gef10-detector.md, rogue-gef10.md, ../benchmarks/gef10-eval.md, ../../scripts/gef10_r2_measure.py, ../../scripts/map_labels.py]
next_action: "Batt decides whether a round 2 is worth it (section 7). Measured: the notice detector is validated (587 / 595 positives, the 8 misses before the notice is drawn; 0 / 8,156 false) and removes NO TRAIN label (it fixes C1, not the data); the GAT-step rule (H 5, R 2) removes 6.0 % of the kept labels (all Green Plant), those labels fit no worse, and it does not reach 13r's cell (10 cells from the ramp). The Poporing case needs its own diagnosis. Nothing is frozen or decided."
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

## 1. The choices, stated BEFORE any label was counted (2026-10-26 03:35:54 ICT, from `date`; committed in 870bba8 before the counts)

(870bba8's heading said 03:37, an estimate ahead of the clock; the time above is `date`'s and
the commit's own, 03:35:55.)

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

## 2. RESULT: the notice detector's validation (03:41 ICT; `validate`)

Scanned: every candidate frame of the label files (the detector reads only the top 174 rows of
each PNG). 10 parts, 9,419 frames.

| part | role | frames | pickups (packets) | frames with a notice |
|---|---|---|---|---|
| watch cells 0-10 | FIT | 506 | 0 (immune) | 0 |
| pilot | FIT | 689 | 17 | 77 |
| pilot2 | FIT | 416 | 18 | 66 |
| a2 | TRAIN | 1,493 | 39 | 170 |
| a4 | TRAIN | 462 | 10 | 42 |
| w2 | TRAIN | 1,477 | 0 (immune watch) | 0 |
| s1, a1, a3, a6 | did not join TRAIN | 1,059 / 901 / 1,411 / 1,005 | 29 / 22 / 35 / 6 | 101 / 88 / 149 / 27 |

**Against the packets:**

| case | frames | detected | not detected |
|---|---|---|---|
| POSITIVE (a pickup <= 4.0 s before) | 595 | **587** | 8 |
| NEGATIVE (no pickup in the 10 s before) | 8,156 | **0** | 8,156 |

- **The 8 misses are all frames captured 0.028-0.060 s after the pickup packet** (pilot #511,
  pilot2 #92, a2 #1507, a4 #207 and #264, s1 #1294, a1 #864, a3 #1459). By eye, none of them shows
  the notice yet: the client had not drawn it. So they are correct negatives. Frames 0.1-1.0 s
  after a pickup: 133 / 133 detected.
- **By the pickup's age** (1-s bins, all parts): 0-1 s 142 / 150; 1-2 s 158 / 158; 2-3 s
  150 / 150; 3-4 s 137 / 137; 4-5 s 127 / 127; **5-6 s 6 / 120**; 6-10 s 0 / 421; 10 s and later
  0 / 6,088; no pickup at all 0 / 2,068. The notice lives about 5 s.
- **No false detection anywhere**, including the watch's 4-row layout (its hotbar lies in the
  band's x range) and w2's 1,477 frames.
- **Its geometry, every detection:** left edge x 541, rows y 76..105, always; the right edge
  varies with the item name (x 679 to 800, end exclusive). 13r's a7 notice (x 541-799) is the
  same box as a2's "541-800" (17 frames).
- By eye (the sheet, `/dev/shm`): the 8 misses (no notice drawn) and 8 sampled hits (each a
  notice, its box exactly on it).

## 3. RESULT: rule N, the notice over the kept labels (03:39 ICT; `measure`)

- **No kept label overlaps a detected notice: 0 of 2,413** in the TRAIN-joined parts, for every
  part and every species. None is half covered.
- 2 kept labels come within 16 px of one: pilot #545 (a Poporing, box x 501-535, 6 px left of
  the notice) and a2 #129 (an Orc Lady, 11 px left of it).
- **On C1's side (the standing labels, the prediction): 0 of 527 scored rows lie under a notice;
  3 lie within 16 px of one (none bad).**
- **Why the training labels are untouched:** a kept label passed the masked-NCC fit, and an opaque
  white box over the sprite fails that fit. So a label under the notice is already EXCLUDED, and
  its frame is not written. The hole 13r found is in **C1's measurement**: C1 scores the
  PREDICTION without a fit, so a monster drawn under the notice scores as a bad label.

## 4. RESULT: rule T, raised terrain (H = 5.0, R = 2; 03:39 ICT)

**Kept labels removed:** 144 of 2,413 (6.0 %); R = 1: 121.

| part | kept | removed by T |
|---|---|---|
| watch cells 0-10 | 822 | 31 (Orc Archer 20, Orc Lord 11; the Orc Lord's pile at cells (337-342, 193-200) and (50-51, 303-306)) |
| pilot | 152 | 1 (a Poporing at (319, 102), ON the plateau, altitude 40) |
| pilot2 | 46 | 0 |
| a2 | 275 | 24 (Poporing 16 at (109-114, 351-358), Orc Lady 8 at (200-236, 33-41)) |
| a4 | 196 | 0 |
| w2 | 922 | 88 (**Green Plant 74 of 74**: two plants at (301, 251) and (300, 253), altitude -24, beside a dip; Poporing 14) |

**Do those labels fit worse (the FIT-side check)? No.**

| scope | near a step (rule T) | the rest | Mann-Whitney p |
|---|---|---|---|
| FIT | n 32, NCC median 0.683 (p10 0.275) | n 988, 0.669 (p10 0.204) | 0.88 |
| TRAIN-joined | n 144, **0.796** (p10 0.667) | n 2,269, 0.695 (p10 0.294) | < 0.0001 (near fits BETTER) |

- Per species (TRAIN-joined), near vs the rest: Poporing 31 at 0.762 vs 0.770 (p 0.64); Orc
  Archer 20 at 0.676 vs 0.590 (p 0.06); Orc Lord 11 at 0.705 vs 0.682 (p 0.64); Orc Lady 8 at
  0.766 vs 0.699 (p 0.009); Green Plant 74 at 0.860, none elsewhere.
- By the distance to the nearest step > H (TRAIN-joined), median NCC: 0-2 cells 0.796 (144);
  3-5 0.694 (142); 6-10 0.706 (367); 11-15 0.697 (457); none within 15 cells 0.691 (1,303).
  There is no trend.
- |dy| of the fit: median 1 px near a step and elsewhere.
- **C1's side:** 19 of the 527 scored standing rows lie near a step; 1 of them is bad (5.3 %),
  against 7 bad of the other 508 (1.4 %). That one bad row is a2 #1977, a Poporing two cells from
  a ramp. **By eye its box lies under our damage digits ("302")**, beside the rock face, so it is
  another transient overlay, not a terrain error. Too few rows to tell either way.
- **The 13r sighting's cell:** the brief places it around (277, 86). There the client GAT is
  FLAT (altitude 0 over +-8 cells). The nearest step > 5 is **10 cells** east, where the ramp
  begins (x 287; > 4: 10 cells; > 8: 12). So rule T at R = 1 or 2 would NOT have removed that
  label, if the cell is right. TEST rows were not read here to check it. Reaching it would take
  R = 10, which removes **653 of 2,413 kept labels (27 %)**. By R: 0: 8; 1: 121; 2: 144; 3: 183;
  5: 286; 10: 653; 15: 1,110.
- **Sensitivity** (not chosen from): H = 4 removes 151 kept labels (cache frames 719 -> 664);
  H = 8 removes 118 (719 -> 668). The FIT check does not change: near labels fit as well or
  better (H = 8: FIT p 0.03, near better).

## 5. RESULT: both rules together, per species (H = 5.0, R = 2; the TRAIN-joined parts pooled)

"written" = kept labels in frames the cache would write (`map_frame`, floor 0.636). A removed
label takes its frame out, with that frame's other labels.

| species | kept | after N | after T | after N + T | removed | written | written after N + T | lost |
|---|---|---|---|---|---|---|---|---|
| Orc Lady 1273 | 920 | 920 | 912 | 912 | 0.9 % | 384 | 382 | 0.5 % |
| Orc Warrior 1023 | 272 | 272 | 272 | 272 | 0 % | 121 | 121 | 0 % |
| Poporing 1031 | 484 | 484 | 453 | 453 | 6.4 % | 300 | 276 | 8.0 % |
| Orc Baby 1686 | 54 | 54 | 54 | 54 | 0 % | 4 | 4 | 0 % |
| Orc Lord 1190 | 160 | 160 | 149 | 149 | 6.9 % | 9 | 9 | 0 % |
| Orc Archer 1189 | 449 | 449 | 429 | 429 | 4.5 % | 20 | 20 | 0 % |
| Green Plant 1080 | 74 | 74 | 0 | 0 | **100 %** | 74 | 0 | **100 %** |
| **all** | **2,413** | **2,413** | **2,269** | **2,269** | **6.0 %** | **912** | **812** | **11.0 %** |
| frames written | | | | | | **719** | **666** | **7.4 %** |

- Per part, frames written before -> after N + T: watch 61 -> 61; pilot 77 -> 76; pilot2 4 -> 4;
  a2 76 -> 72; a4 109 -> 109; w2 392 -> 344.
- Rule N changes nothing (section 3). All of the cost is rule T. Green Plant's two plants are half of
  the kept labels it removes (74 of 144) and three quarters of the written ones (74 of 100).

## 6. What else the C1 rows show (the TRAIN side's own bad labels)

- **C1 on the TRAIN-joined parts: 8 bad of 527 scored (1.5 %),** the own-C1 numbers of 13o / 13p
  reproduced: pilot 1 / 53, a2 1 / 64, w2 6 / 271, the watch 0 / 72, a4 0 / 67, pilot2 0 scored.
- **None of the 8 is under a notice.** All 8 carry facing `fix2:after_move` with a predicted
  heading that is not the best-matching one. In 7 of them the best of the 8 headings scores 0.14 to
  0.76 (over tau 0.092): **a facing error**. By eye, both w2 units (frames 24-26 and 852-854) are
  drawn exactly in their box, facing another way. The 8th is a2 #1977, under damage digits
  (section 4).
- **The sighting effect:** C1 counts FRAMES. One bad sighting gives 2-3 consecutive bad rows:
  w2's 6 bad rows are 2 units; a7's 5 were 2 sightings (13r). At ~60 scored rows, 4 bad rows fail
  T1 (3 / 61 = 4.9 % passes, 4 / 61 = 6.6 % fails), so **two sightings can fail it.**
- At the TRAIN side's row rate (1.5 %), independent rows would fail a 61-row T1 only 1.4 % of the
  time (binomial P(X >= 4)). Clustering raises that risk.
- An immune watch TEST like w2 (271 scored) is far less brittle than a hunt's 22-35.

## 7. What this means for the decision (Batt's; nothing here decides)

- **The notice rule is validated and cheap:** 587 / 595 positives (the 8 misses are frames before
  the notice was drawn), 0 / 8,156 false detections. It removes **no** TRAIN label, so it costs no
  training data. What it fixes is C1: the T1 measurement would drop a standing row under a detected
  notice, as it drops one under a static UI window. 13r's sighting 1 is that case.
- **The notice rule alone would not have rescued this TEST** (arithmetic on 13r's published
  numbers only, no TEST read): dropping the Orc Warrior's 2 to 6 rows (frames 505-510) leaves
  3 bad of 55-59 = 5.1-5.5 % > 5 %. Both sightings mattered, and a round 2 needs a NEW TEST anyway.
- **The GAT-step terrain rule, as briefed, is NOT supported by FIT / TRAIN:**
  - it removes 6.0 % of the kept labels (11.0 % of the written ones, 53 cache frames), including
    all of Green Plant;
  - those labels fit no worse than the rest;
  - it would not reach 13r's Poporing if that unit stood at (277, 86), ten cells from the ramp.
  - The Poporing case needs its own diagnosis first. Candidates, none measured here:
    - a client-vs-server position difference;
    - the drawn ground (GND) vs the GAT near the ramp;
    - damage digits, or another overlay.
- **A round 2's other risks:** the TRAIN-side background is 1.5 % bad rows, all of them facing
  errors (`fix2:after_move`) or overlays. T1's bar of 5 % on ~60 rows fails on two clustered
  sightings. A bigger standing-label TEST (an immune watch) would judge the rule, not the luck of
  the draw.
- **Other transient overlays seen** (not measured):
  - damage digits (yellow, over a2 #1977's box);
  - "Miss" texts.
  - A pixel rule for them would be built like this notice rule.

## 8. Where the outputs live (client-derived pixels and GAT: `/dev/shm` / NAS, never committed)

- The code: `scripts/gef10_r2_measure.py` and its pure tests
  (`services/backend/tests/test_gef10_r2_measure.py`, synthetic data only).
- The outputs: `/dev/shm/poring-lab-tmp/gef10-r2/`. They are archived to the NAS
  (`/mnt/poring-lab-datasets/scratch-archive/2026-10-26/gef10-r2/`) and listed in the report.
  - `scan-train.json`, `scan-out.json`: the detector per frame;
  - `validate-all.json`;
  - `heights.json`;
  - `measure-h{5,4,8}.json` and their per-label files;
  - `c1rows/`: the re-run C1 rows of the TRAIN-joined parts;
  - the by-eye sheets.
- Re-run:

      W=/home/batt/docker/poring-lab; L=/dev/shm/poring-lab-tmp/gef10-det/labels
      python $W/scripts/gef10_r2_measure.py scan $L/<part>.json ... --out scan.json
      python $W/scripts/gef10_r2_measure.py validate scan.json --sheet sheet.png --out validate.json
      python $W/scripts/gef10_r2_measure.py heights --gat <gef_fild10.gat> --out heights.json
      python $W/scripts/gef10_r2_measure.py measure $L/<TRAIN-joined parts>.json --scan scan.json \
          --gat <gef_fild10.gat> --h 5 --c1rows <check --rows files> --out measure.json
