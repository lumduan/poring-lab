---
doc_type: research
hypothesis: "Before a Crusader DEFEND-SCAN run on orcsdun01 (aggressive orcs come to the character; the runner hovers the cells around it and reads the SWORD cursor), three offline facts are needed: how much the live v1 CPU detector sees there zero-shot, where the quiet REST spots are, and no-enter zones around both warps."
status: MEASURED (offline, 2026-10-22; the detector run 11:17-11:33 ICT and the rest-spot / zone runs 11:19-11:27, from `date`; no live action, no GPU; nothing trained or tuned on the blocks)
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [orcsdun01-detector.md, crusader-orcsdun01.md, crusader-orcsdun01-facts.md, ../../config/map_zones/README.md]
next_action: "The parent's pre-registered Crusader run reads this: boxes stay a SECONDARY trigger (v1 boxes 17-21 % of the visible orcsdun01 monsters, 8-14 % within 3 cells); rest spot candidates in section 2; config/map_zones/orcsdun01.yaml applies to any hunt_flow version with map_zones on (v52+) once merged."
title: "orcsdun01 prep for the Crusader defend-scan run: v1 zero-shot, rest spots, warp zones"
date: 2026-10-22
owner: Batt
---

# orcsdun01 prep: v1 zero-shot, rest spots, warp zones

**The brief (the parent session, 2026-10-22 ~11:10 ICT, for a pre-registered Crusader run on
orcsdun01 today):** DEFEND-SCAN. Aggressive orcs come to the character and it fights them in
melee. The runner hovers the cells around the drawn character and reads the client's SWORD cursor,
so detector boxes are a SECONDARY trigger. Three offline tasks:
1. v1 zero-shot on orcsdun01;
2. rest spots from the packets;
3. map zones around both warp spans. Batt delegated zone authoring again today: "author
   config/map_zones/orcsdun01.yaml (no-enter around both warp spans, delegated as before) and
   prove it".

**Data.** The three warp-and-watch blocks of [orcsdun01-detector.md](orcsdun01-detector.md)
section 2a (NAS, read-only): col1 `20261021T103231-orcsdun01-col1`, col2
`20261021T122650-orcsdun01-col2` (the pre-registered TEST block of the orcsdun01 detector
evaluation, reported SEPARATELY below), col3 `20261021T142100-orcsdun01-col3`.
- Batt explicitly authorised reading col1-col3 for this task (v1 zero-shot).
- Nothing is trained, tuned or fitted on them here.
- The truth model's parameters (the 120 ms offset, k 0.140) were fixed on col3 before this work
  (orcsdun01-detector.md 3c).

**Keep it honest.**
- The GM in these blocks is the Novice GM, immune (`@monsterignore`), never the Crusader.
- No monster attacked it: there are no packs around the character and no attack animations next
  to it.
- The defend-scan picture (orcs in melee contact, overlapping the Crusader's sprite) was never
  recorded. Section 1's "within 3 cells" numbers are the closest available proxy, not that
  picture.

## 0. Bottom line

1. **v1 is nearly blind on orcsdun01** (section 1). Pooled recall is 17-21 % of the visible
   monsters, and only 8-14 % within 3 cells of the GM. col1 / col2 (TEST) / col3: 16.7 / 20.0 /
   21.2 %, within 3 cells 8.2 / 10.2 / 14.1 %.
   - Orc Zombie, 80 of the 135 monsters, is boxed 7-10 % of the time (3-5 % within 3 cells).
   - Orc Skeleton (54-65 %) and Drainliar (53-59 %) do best.
   - The boxes it does draw are mostly right: 84-87 % precision, 96-100 % within 3 cells.
   - **False monster boxes within 100 px of the GM: 0 / 0 / 1** over 1,627 frames. The one is a
     second box on a real Orc Skeleton's shield, 3 cells away, not a phantom.
   - It drew **0 `player` boxes** on the Novice GM in all frames: under this lighting it does not
     see the character either.
   - Boxes can only ever be a secondary trigger here. A miss is the normal case, not the
     exception.
2. **Rest spots** (section 2):
   - map-wide: **(58,101)** is the strongest candidate. Its aggressive presence within 9 cells is
     33.7 unit-s/min, against a map median of 176. It is quiet in every block (21-48), its
     presence within 5 cells is 0.0, and the line-of-sight geometry agrees (E 0.9 against a
     median of 3.08). It sits in a wall corner with 5 open neighbours.
   - near the entrance (32,166): **(28,165)**, 4 steps away, at 88.4/min, and **(39,147)**, 19
     steps away, at 79.8/min. The entrance cell itself measured 133.8/min (2 dwells only).
   - Every presence number rests on 2-5 dwells of 30 s and swings a lot between blocks. Read the
     ranking as "probably quiet", not as a measured guarantee.
3. **Zones** (section 3): `config/map_zones/orcsdun01.yaml` adds two no-enter areas, each a warp
   span grown by 4 cells.
   - Cells taken: 62 walkable around in_orcs01, 81 around orcsdun02.
   - The proof: nothing is sealed off, 0 cells become unreachable, 1.53 % of the spawn cells
     fall in the zones.
   - Every sampled click INTO an area and onto a warp span is refused (400 / 400 for each area).

## 1. v1 zero-shot (`scripts/orc_v1_zeroshot.py`)

**What runs.** `unit_detector.UnitDetector()`, as `hunt_flow` builds it: the v1 ONNX model
`v1png-last-736x1280.onnx`, conf 0.25, IoU 0.5, 8 threads, on the CPU.
- It runs on every 20th recorded frame inside a dwell (the GM settled at its stand), outside the
  GM-command windows.
- The frames are 1280 x 720 game-region JPEG q80 at 5 Hz, the recorder's region.
- Live, the detector sees raw RDP frames, not JPEG: a caveat.

**The truth.** Every monster the packets place in the GM's view at the frame's time (the 120 ms
packet -> frame offset):
- its predicted sprite box from `render.predict_sprite`: species, the Timeline action and facing,
  k 0.140, flyers drawn above their cell;
- "visible" is v1's own rule (`labels_for_v1`): at least half on screen and less than half under
  the recorded UI layout;
- "clear of RSW models" means the box does not overlap a projected RSW model box (the 1c test of
  orcsdun01-detector.md 3c);
- the distance to the GM is Chebyshev in cells.

**Matching.** One-to-one and greedy, closest first, by the distance from the box centre to the
predicted box centre.
- **Tolerance: 40 px.** That is generous on purpose:
  - the facing errors of 3a/3c shift a predicted box sideways by up to about half its width;
  - C2 measured the position itself at 1 / 1 px.
- 24 px and 64 px are shown as a sensitivity check (below).
- **Recall** = the visible truth units matched by a `monster` box.
- **Precision** = the monster boxes matched to a monster, the visible ones first, then (pass 2)
  any other monster the packets place (partly off screen or under the UI): a box on those is not
  false.
- **Within 3 cells:** for truth, the unit's cell. For a box, its matched unit's cell; an unmatched
  box takes the projected cell nearest its foot.
- **Near the GM:** the unmatched monster boxes whose centre lies within 100 px of the GM's
  projected anchor (the camera centres on it).
- v1 outputs only player / monster / npc, so **precision exists only pooled, not per species.**
  - A box carries no species.
  - Per species, the table gives recall; the pooled precision covers all boxes.

**A visual check (scratch, not committed):** 3 col3 frames with the truth boxes drawn sat on the
drawn orcs, bats and plants. The misses are the detector's, not the truth's.

### 1a. col1 (`20261021T103231-orcsdun01-col1`)

| species | visible units (unit-frames) | recall | within 3 cells: n | recall within 3 | clear of RSW models: n | recall clear |
|---|---|---|---|---|---|---|
| Orc Zombie 1153 | 2303 | 7.3 % | 239 | 2.9 % | 1085 | 6.3 % |
| Familiar 1005 | 461 | 30.4 % | 49 | 24.5 % | 200 | 35.0 % |
| Steel Chonchon 1042 | 311 | 22.8 % | 36 | 2.8 % | 185 | 25.4 % |
| Orc Skeleton 1152 | 235 | 64.7 % | 13 | 61.5 % | 119 | 69.7 % |
| Black Mushroom 1084 | 232 | 20.7 % | 22 | 0.0 % | 7 | 71.4 % |
| Drainliar 1111 | 107 | 53.3 % | 12 | 25.0 % | 58 | 69.0 % |
| White Plant 1082 | 174 | 1.7 % | 7 | 0.0 % | 93 | 3.2 % |
| aggressive 4 | 3106 | 16.6 % | 313 | 9.6 % | 1462 | 17.9 % |
| **pooled** | 3823 | 16.7 % | 378 | 8.2 % | 1747 | 18.1 % |

- 584 frames (every 20th recorded frame; 155 outside a dwell and 13 in a GM window skipped).
- **Boxes:** 747 monster boxes = 1.28 per frame (+ 63 `npc`, 0 `player`).
  - Precision **85.7 %** (107 false; 48 of them a second box on an already-matched unit:
    92.1 % if duplicates count as hits).
  - Within 3 cells: 31 boxes, precision **100 %**.
  - False within 100 px of the GM: **0**.
- **Tolerance sensitivity:** recall 14.0 / 16.7 / 16.8 % and precision 71.9 / 85.7 / 86.3 % at
  24 / 40 / 64 px.
- **Time per frame:** worker p50 273 ms (p90 457, max 851); CPU 1.72 s (p90 1.99) over 8 threads.

### 1b. col2: the pre-registered TEST block (`20261021T122650-orcsdun01-col2`), separately

| species | visible units (unit-frames) | recall | within 3 cells: n | recall within 3 | clear of RSW models: n | recall clear |
|---|---|---|---|---|---|---|
| Orc Zombie 1153 | 2177 | 9.6 % | 215 | 2.8 % | 1135 | 9.3 % |
| Familiar 1005 | 340 | 36.8 % | 41 | 26.8 % | 195 | 38.5 % |
| Steel Chonchon 1042 | 306 | 33.0 % | 28 | 7.1 % | 160 | 38.1 % |
| Orc Skeleton 1152 | 299 | 53.5 % | 28 | 46.4 % | 157 | 53.5 % |
| Black Mushroom 1084 | 294 | 21.8 % | 23 | 0.0 % | 45 | 31.1 % |
| Drainliar 1111 | 153 | 54.2 % | 12 | 33.3 % | 81 | 50.6 % |
| White Plant 1082 | 143 | 0.0 % | 7 | 0.0 % | 99 | 0.0 % |
| aggressive 4 | 2969 | 19.4 % | 296 | 11.5 % | 1568 | 19.5 % |
| **pooled** | 3712 | 20.0 % | 354 | 10.2 % | 1872 | 20.4 % |

- 580 frames (159 outside a dwell, 13 in a GM window).
- **Boxes:** 882 monster boxes = 1.52 per frame (+ 52 `npc`, 0 `player`).
  - Precision **84.1 %** (140 false, 57 of them duplicates: 90.6 %).
  - Within 3 cells: 36 boxes, precision **100 %**.
  - False within 100 px of the GM: **0**.
- **Tolerance sensitivity:** recall 17.2 / 20.0 / 20.2 % and precision 72.2 / 84.1 / 84.8 % at
  24 / 40 / 64 px.
- **Time per frame:** worker p50 265 ms (p90 363, max 584); CPU 1.73 s (p90 1.94).

### 1c. col3 (`20261021T142100-orcsdun01-col3`)

| species | visible units (unit-frames) | recall | within 3 cells: n | recall within 3 | clear of RSW models: n | recall clear |
|---|---|---|---|---|---|---|
| Orc Zombie 1153 | 1836 | 9.7 % | 191 | 4.7 % | 955 | 8.7 % |
| Familiar 1005 | 384 | 38.3 % | 49 | 30.6 % | 196 | 39.3 % |
| Steel Chonchon 1042 | 238 | 27.3 % | 12 | 0.0 % | 116 | 23.3 % |
| Orc Skeleton 1152 | 259 | 62.2 % | 35 | 57.1 % | 137 | 67.9 % |
| Black Mushroom 1084 | 212 | 21.2 % | 24 | 0.0 % | 30 | 43.3 % |
| Drainliar 1111 | 131 | 58.8 % | 8 | 12.5 % | 84 | 64.3 % |
| White Plant 1082 | 109 | 0.0 % | 0 | -- | 74 | 0.0 % |
| aggressive 4 | 2610 | 21.6 % | 283 | 15.9 % | 1372 | 22.4 % |
| **pooled** | 3169 | 21.2 % | 319 | 14.1 % | 1592 | 21.8 % |

- 463 frames (126 outside a dwell, 13 in a GM window).
- **Boxes:** 775 monster boxes = 1.67 per frame (+ 50 `npc`, 0 `player`).
  - Precision **87.0 %** (101 false, 38 of them duplicates: 91.9 %).
  - Within 3 cells: 47 boxes, precision **95.7 %**.
- **False within 100 px of the GM: 1, in 1 frame,** and it is not a phantom: a second box on an
  Orc Skeleton's shield, 3 cells from the GM. Its head box was the match. Checked on the frame.
- **Tolerance sensitivity:** recall 18.8 / 21.2 / 21.4 % and precision 77.0 / 87.0 / 87.6 % at
  24 / 40 / 64 px.
- **Time per frame:** worker p50 274 ms, **p90 1,073 ms, max 11.1 s** (spikes under the host's
  load, at nice 19); CPU 1.81 s (p90 2.14).

### 1d. Reading it

**The three blocks agree** (pooled recall 16.7 / 20.0 / 21.2 %; col2, the test block, sits in
the middle).

| block | pooled recall | recall within 3 cells | Orc Zombie recall (within 3) | precision (within 3) | boxes / frame | false within 100 px of the GM |
|---|---|---|---|---|---|---|
| col1 | 16.7 % | 8.2 % | 7.3 % (2.9 %) | 85.7 % (100 %) | 1.28 | 0 |
| col2 (TEST) | 20.0 % | 10.2 % | 9.6 % (2.8 %) | 84.1 % (100 %) | 1.52 | 0 |
| col3 | 21.2 % | 14.1 % | 9.7 % (4.7 %) | 87.0 % (95.7 %) | 1.67 | 1 (a duplicate on a shield) |

- **Per species, the order is stable across blocks:**
  - Orc Skeleton 54-65 %;
  - Drainliar 53-59 %;
  - Familiar 30-38 %;
  - Steel Chonchon 23-33 %;
  - Black Mushroom ~21 %;
  - Orc Zombie 7-10 %;
  - White Plant 0-2 %.
  v1 never trained on an orcsdun01 frame or on any of these species, and the dungeon is dark
  (diffuse light 0.2-0.3).
- **Occlusion is not the reason.** Clear of the RSW model boxes, recall barely moves for the
  walkers (Orc Zombie 6-9 %). Only Black Mushroom, nearly always under canopy, gains (31-71 % on
  7-45 units).
- **Within 3 cells it is worse, not better.**
  - About 36 % of the units within 3 cells overlap the GM's own sprite: 138 of 378 in col1, 138
    of 354 in col2.
  - Recall among those is 4-7 %. Recall among the other near units is ~11-13 %, about the
    Orc-Zombie-heavy mix.
  - So a melee neighbour standing on the character is the case v1 misses most.
- **v1 never drew a `player` box** on 1,627 frames with the Novice GM at the centre. The 50-63
  `npc` boxes per block are not scored.
  - A Crusader sprite is a different picture: the 0 false boxes near the GM do not transfer to
    it as a measurement.
- **The boxes v1 does draw are right.** Most "false" boxes are second boxes on a real unit (the
  Orc Skeleton's shield and its body). Within 3 cells the three blocks drew 114 boxes, and all
  but 2 matched a monster.
- **Time.** About 0.27 s per frame (p50) and ~1.7-1.8 CPU-seconds over 8 threads. The tail
  (p90 0.36-1.07 s, one 11 s stall in col3) was measured at nice 19 under the host's load.
- **For the defend-scan run.** A v1 box near the character is trustworthy when it appears, but
  within 3 cells it appears for about 1 Orc Zombie in 20-35 (Orc Skeleton: about 1 in 2).
  - The SWORD-cursor scan must stay the primary trigger.
  - "No box" must never mean "no monster".


## 2. Rest spots (`scripts/orc_dungeon_prep.py rest-spots`)

**Method.** At 1 Hz inside every dwell, outside the GM windows, the packets' world gives every
monster the server has sent.
- The server sends what lies in the GM's view area: rAthena `area_size` 14 cells, Chebyshev. The
  data's own maximum is 15 (one cell more, at the edge of the area).
- A cell is OBSERVED in a second when its whole R-neighbourhood lies inside that area
  (Chebyshev(cell, GM) <= 14 - R).
- Its **presence** is the mean number of monsters within R cells over its observed seconds,
  written as unit-seconds per minute: 60 = one monster on average.
- **Presence is only known near where the GM stood:** within 5 cells of a stand for R = 9, 9 for
  R = 5.
- Over the three blocks: 6,633 dwell-seconds (col1 2,371, col2 2,376, col3 1,886), at 80 / 80 /
  64 stands of the 97-cell lattice.
- 5,994 of the 9,356 walkable cells are observed >= 60 s at both radii. Only those are ranked.
- **"Aggressive"** = Orc Zombie, Familiar, Orc Skeleton, Drainliar. Steel Chonchon (a looter) and
  the two plants are not aggressive; they are counted in "all".
- **The GM was immune.** Aggressive monsters wandered; they did not converge on it. Presence is
  the natural density around a cell, which is what decides how many find a resting Crusader.

**The candidates also pass:**
- the three stand-cell checks (`npc_click_test.check_warps`): outside both warp spans; outside
  the script-NPC touch areas (L3 `first_workflow.json` lists **0 script NPCs** on orcsdun01:
  verified); standable on the SERVER map cache;
- the main walkable component (client ∩ server);
- **outside the zones of section 3.**

They are ranked by the pooled aggressive presence within 9 cells. They must be observed in at
least 3 dwells and at least 2 blocks, and stand at least 8 cells apart.

**Reported beside each:**
- the per-block value (col1 / col2 / col3, with its observed seconds);
- a GEOMETRY prior **E**: the expected aggressive monsters that can see the cell. It is the count
  of spawnable cells within 10 with a clear straight line, x 110 / 9,181, the 3d method of
  crusader-orcsdun01-facts.md without its path rule. Over all walkable cells: p10 2.02, median
  3.08, mean 3.20, consistent with that doc's 3.19;
- the open 8-neighbours (how many can stand next to it at once);
- the path steps, 8-way with no corner cutting on the walkable grid minus the zones, to the nearest
  "hunting-area" cell (observed, presence >= the map median of 176.1 / min, 2,998 cells) and
  from the entrance cell (32,166).

**Map-wide (all observed cells): aggressive presence within 9 cells per minute, p10 94.7 / median
176.1 / p90 264.0.**

| cell | aggr. R9 /min | all R9 /min | aggr. R5 /min | all R5 /min | observed (R9 / R5) | aggr. R9 per block: col1 / col2 / col3 | E (geometry) | open neighbours | steps to hunting area | steps from (32,166) |
|---|---|---|---|---|---|---|---|---|---|---|
| **(a) the entrance cell (32,166)** (reference; 2 dwells, so not ranked) | 133.8 | 133.8 | 54.1 | 58.4 | 61 / 152 s, 2 dwells | 170 (30 s) / 99 (31 s) / -- | 2.59 | 8 | 5 | 0 |
| (a) near the entrance: **(28,165)** | 88.4 | 96.7 | 37.1 | 37.1 | 152 / 152 s, 5 dwells | 129 (59 s) / 79 (62 s) / 29 (31 s) | 2.34 | 6 | 7 | 4 |
| (a) near the entrance: **(39,147)** | 79.8 | 106.1 | 26.3 | 34.2 | 121 / 121 s, 4 dwells | 120 (31 s) / 48 (60 s) / 102 (30 s) | 1.91 | 5 | 6 | 19 |
| (a) near the entrance: (34,150) | 91.3 | 108.3 | 29.3 | 39.8 | 92 / 92 s, 3 dwells | 76 / 134 / 64 (30-31 s each) | 1.81 | 3 | 3 | 16 |
| (b) 1. **(58,101)** | 33.7 | 42.5 | **0.0** | 2.5 | 89 / 118 s, 3 dwells | 33 / 48 / 21 (29-31 s each) | **0.90** | 5 | 8 | 70 |
| (b) 2. (28,69) | 29.0 | 49.5 | 13.5 | 16.5 | 91 / 120 s, 3 dwells | 0 / 70 / 18 | 1.94 | 8 | 8 | 101 |
| (b) 3. (187,28) | 40.2 | 50.8 | 6.6 | 9.9 | 91 / 91 s, 3 dwells | 14 / 76 / 30 | 1.74 | 5 | 8 | 220 |
| (b) 4. (87,172) | 51.4 | 56.7 | 6.6 | 7.9 | 91 / 91 s, 3 dwells | 4 / 60 / 92 | 0.90 | 5 | 18 | 116 |
| (b) 5. (170,111) | 52.6 | 83.6 | 35.2 | 40.8 | 89 / 150 s, 3 dwells | 0 / 64 / 94 | 2.73 | 8 | 5 | 148 |

The (b) rows are ranked by the pooled aggressive R9 presence. (28,69) has the lowest pooled
value, but (58,101) is listed first because three things agree there: the low E, the 0.0 within 5
cells, and the narrowest spread across blocks. Every candidate passes the stand-cell checks and
lies outside the zones.

**What each place is:**
- **(58,101):** the north-east corner of the room west of the big central block. Walls N, NE and E,
  so 5 open neighbours, and the walls cut sight lines (E 0.9).
- **(28,69):** the west wall of the open hall around White Plant (58,67), one of the densest
  areas (crusader-orcsdun01-facts.md 3d). It is quiet in col1 and col3 but 70 in col2: the
  weakest case.
- **(187,28):** the east wall of the SE wing. It is 14 cells north of the orcsdun02 zone (zone
  edge y 14), in the wing the facts doc calls a dead end with one opening.
- **(87,172):** the far end of the N pocket (facts 3c), 18 steps from the hunting area.
- **(170,111):** the east side, mid-map.
- **(28,165) and (39,147),** near the entrance: the NW entrance wing's south-west corner and the
  south wall of its hall.
  - Both are below the map's p10 (94.7 / min) but well above the (b) spots: the NW wing is
    moderately busy.
  - The entrance cell itself (133.8) lies between the map's p10 and its median.
  - (34,150) has only 3 open neighbours: a narrow slot, one way out.

**Caveats (read before using a number):**
- **Small samples.** Each cell is seen in 2-5 dwells of 30 s, and seconds inside one dwell are
  strongly correlated. The per-block columns swing from 0 to ~90 for the same cell.
- **Winner's curse.** The quietest of ~6,000 noisy cells is biased low; the true value is likely
  higher. The geometry prior E is the noise-free cross-check. (58,101) and (87,172) are low on
  both; (170,111) is not (E 2.73, quiet only by the samples).
- **Presence is not aggro.** The Crusader is not immune. An aggressive monster within its view
  (about 10 cells for these species) with a clear line will come. So presence within 9 cells per
  minute is roughly the arrival pressure, not a count of fights.
- A unit-second count says nothing about packs. Section 0's pack numbers (crusader facts) still
  decide what a rest spot must survive.

## 3. Map zones (`config/map_zones/orcsdun01.yaml`)

**The file.** Two `no_enter` areas, each a warp span from `data/kb/warps.json` (touch area =
centre ± span) grown by **4 cells** on every side.
- 4 = the brief's >= 3, + 1. A click made while the GM moves can resolve up to ~3 cells further
  along its walk than the aimed cell (frames lag the server ~0.5 s). A destination just outside
  an area must still stop >= 1 cell short of the span.
- Nothing walkable lies beyond either span (both sit at the end of their corridor), so the larger
  margin seals nothing.
- `reviewed_by: "agent (delegated by batt, 2026-10-22)"`, with the `delegation:` note citing
  Batt's day-run brief; sha256 `84b4b34e…4ece41`.

| item | warp | span (touch area) | area (cells) | walkable cells taken | notes |
|---|---|---|---|---|---|
| `warp-in_orcs01` | orc01-1 (32,172) -> in_orcs01 30,180 (the exit) | 3,1: x 29-35 y 171-173 | x 25-39 y 167-177 | **62** | the warp's own arrival (32,170) is inside; the runner's entrance cell **(32,166) is one cell outside** (y 166 < 167) |
| `warp-orcsdun02` | orc03 (183,8) -> orcsdun02 21,185 (F2) | 4,2: x 179-187 y 6-10 | x 175-191 y 2-14 | **81** | the arrival from F2 (183,11) is inside |

**`python3 scripts/map_zones.py check orcsdun01`:** ok. no_cross 0 cells; no_enter 386 cells (143
of them walkable: 62 + 81).

**`python3 scripts/map_zones.py prove orcsdun01`:**

| grid | walkable | zone cells | pieces cut off (no corner rule / corner rule) | main component before -> after | newly unreachable | spawn cells in zones / cut |
|---|---|---|---|---|---|---|
| client ∩ server | 9,356 | 143 | 0 / 0 | 9,356 -> 9,213 | **0** | 143 of 9,356 (1.53 %) / 0 |
| the runner's stand grid | 9,311 | 98 | 0 / 0 | 9,311 -> 9,213 | **0** | (same) |
| the runner's search area | 8,815 | 0 | 0 | 8,815 -> 8,815 | | the search area already keeps warps 10 cells off |

`prove` samples clicks only into CUT pieces, and there are none. So the clicks were sampled per
AREA (`orc_dungeon_prep.py zone-clicks`, 400 samples each, seed 0, through `map_zones.walk_why`,
the runner's gate):

| area | walkable inside | span cells | clicks INTO it refused | clicks ONTO its warp span refused | outside -> outside clicks refused (over-reach, not a leak) |
|---|---|---|---|---|---|
| `warp-in_orcs01` | 62 | 13 | **400 / 400** (`dest_no_enter`) | **400 / 400** | 0 / 400 |
| `warp-orcsdun02` | 81 | 32 | **400 / 400** (`dest_no_enter`) | **400 / 400** | 13 / 400 |

- Every rest-spot candidate of section 2 lies outside both areas (the ranking excludes zone
  cells).
- **What it changes in a run:** `hunt_flow` applies the file only when the version has
  `map_zones` on (v52 onwards). Once this file is on main, a v52+ run on orcsdun01 loads it, and
  its `map_zones` event records the sha256 above. Without the file nothing changes (INERT).

## 4. Not done, and limits

- **No defend-scan frames exist.** The GM was immune and the Novice, so "within 3 cells" is the
  only proxy for a melee contact (section 1).
- The occlusion flag needs the RSW models. They were read from the NAS archive of 10-21
  (`scratch-archive/2026-10-21/poring-lab-tmp/orc-labels-fix/grf/data/model`), not re-extracted.
- The latency was measured at `nice 19` beside the host's other load (load average 13-19 on 64
  cores), not on an idle host: the live number may be lower.
- No live action, no GPU, nothing written to the NAS. The rows (per frame, client-derived boxes)
  stay local in `/dev/shm/poring-lab-tmp/orc-offline/` and are deleted at the end of the task.

## 5. Reproduce

    W=<checkout>; export PYTHONPATH=$W/scripts:$W/packages/poring_dataset/src:$W/packages/poring_env/src:$W/packages/poring_packets/src
    NAS=/mnt/poring-lab-datasets/detector-collection/orcsdun01
    nice -n 19 ionice -c3 python scripts/orc_v1_zeroshot.py run $NAS/<col1> $NAS/<col2> $NAS/<col3> --every 20
    python scripts/orc_v1_zeroshot.py table /dev/shm/poring-lab-tmp/orc-offline/zeroshot/*.rows.json --tol 40
    nice -n 19 python scripts/orc_dungeon_prep.py rest-spots $NAS/<col1> $NAS/<col2> $NAS/<col3>
    python scripts/orc_dungeon_prep.py zone-clicks --samples 400
    python scripts/map_zones.py check orcsdun01 && python scripts/map_zones.py prove orcsdun01

Run-time inputs (never committed): the detector env and model (`/dev/shm/poring-lab-detector`), the
decoded sprites and the GAT (`/dev/shm/poring-lab-tmp/{sprites,gat}`), the RSW
(`/dev/shm/poring-lab-tmp/orc/gat/data/orcsdun01.rsw`), the map cache (`_generated`), `data/kb`.
