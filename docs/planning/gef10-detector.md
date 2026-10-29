---
doc_type: design
hypothesis: "Packet labels with payf07's o3h-all rule (fix 2 facing, 2b / 2c, the fit, o3h, the T_h floor on every label), re-measured on gef_fild10's own FIT data, PLUS a rule that LABELS monsters engaged in a fight with our character (drawn facing it, in the action the packets give), give per-species monster boxes for gef_fild10 (Orc Lady, Orc Warrior, Orc Baby, Poporing, Orc Lord, Orc Archer, the plants) that pass the training tier (T1: C1 <= 5 % on held-out TEST data; T2: every species in the tier passes a blind check, the engaged labels in their own stratum), and floor-item boxes from the items' own client sprites that pass their own geometric and blind checks, so ONE detector can be trained on payf07's 21 classes plus this map's monsters and items."
status: "TRAINING (13z-13z-3): round 2's T1 PASSED on TEST2 2026-10-26 12:06 (13t, C1 1.9 %); the 10-epoch training on v2orc-payf07-gef10-20261026 runs since 2026-10-28 13:44; epoch 7 done 2026-10-29 09:18 (attempt 9 of train-day's auto-resumes). Round 1, SUPERSEDED by round 2: T1 FAILED 2026-10-26 03:16 ICT (13r): the monster tier failed, nothing of gef_fild10 trained in round 1. History: PROPOSED 2026-10-25 20:51:49 ICT (3e31b01); amendments A-D (21:10-21:42). FIT measured 21:03-22:00 (13): 1d STOPPED twice (<= 15 samples; proposal 120 ms), T_h 0.636 (after A: the watch's layout, B: crowded labels out of its set, C: exclusion facing_unknown), the engaged selection chose E2 (14 kept of 620), FIT C1 0.8 % (diagnostic), 142 FIT frames with a monster box under the proposal; floor items: 15 clean samples from ONE floor item. NOTHING FROZEN, no TEST read, nothing trained."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [payf07-detector.md, orcsdun01-detector.md, labels-v2-plan.md, training-cost.md, target-items.md, item-class.md, rogue-gef10.md, gef10-prep.md, ../benchmarks/payf07-eval.md]
next_action: "Finish the training (epochs 8-10; 13z-3: on the 12-h step limit the parent resumes ONCE with RESUME=1, Batt 2026-10-29), then score last.pt after the last completed epoch per gef10-eval.md. ➡️ The rest of this field is round 1's, SUPERSEDED by round 2 (13s-13t): T1 FAILED 2026-10-26 03:16 (13r: C1 5 / 61 = 8.2 % > 5 %; two a7 sightings: a pickup notice over an Orc Warrior, a Poporing beside a raised rock face). Nothing of gef_fild10 trains this round. Batt decides whether a round 2 (a popup rule + a raised-terrain rule, measured on FIT; a NEW TEST; T2 again) is worth it."
title: "A detector for gef_fild10's monsters and floor items: the facts, the split, the label rule (engaged units labelled), T1 / T2, the classes, the cache and training proposal, the evaluation plan (PROPOSED pre-registration)"
date: 2026-10-25
owner: Batt
---

# A detector for gef_fild10's monsters and floor items (PROPOSED pre-registration)

**Batt, 2026-10-25 ~12:3x ICT** (rogue-gef10.md section 0, decision 1, translated): "You may use
the GPU to train on the monsters and items of this map." rogue-gef10.md section 6: the labels follow
the o3h rule re-measured on this map's FIT data, with its T1 / T2 tiers, and "ENGAGED units
(Batt's clip) are part of that pre-registration, not an afterthought". Items: "labelled from
`floor_item_appear` + the camera model (the target-items method)".

**What this document is.** A PROPOSED pre-registration in payf07-detector.md's form, written by a
subagent offline. It fixes the split, the rules, the tiers and the class scheme at the commit time
of its first commit, and it records the FIT measurements made under it (section 13). The parent
freezes the parameters; anything the parent changes is a clock-labelled AMENDMENT committed BEFORE
the step it changes. A failed tier is reported, never re-run under the same bars.

## 0. The decisions this proposal needs (the parent's / Batt's)

| # | decision | proposed default | where |
|---|---|---|---|
| D1 | the split of the Orc Lord watch BY CELL: cells 0-10 FIT, cells 11-14 TEST | adopt | 3a |
| D2 | 1d: measured on FIT; if it stops (< 50 walker samples, or the sweep's edge), 120 ms (payf07's Amendment C: the same RDP frame bus) | adopt | 4b, 13 |
| D3 | the ENGAGED label rule: the variant chosen on FIT by 4h's selection rule (E1 / E2 / E3), labels kept only at the T_h floor, judged by T2 in their own stratum | adopt | 4h, 6 |
| D4 | a species with < 30 kept labels in T2's pool is NOT in the tier and NOT a class this round: its frames are excluded (`unchecked_species`) | adopt | 7 |
| D5 | a failing ENGAGED stratum excludes that species' engaged labels only (their frames are not whole); the species' other labels still train | adopt (Batt's "every species" applies to the species, not to this add-on) | 6 |
| D6 | the floor-item classes: Cyfar, Orcish Voucher, and one pooled `item` class for every other floor item | adopt | 8 |
| D7 | training: init from payf07's epoch-1 `last.pt`; `hsv_s` 0.2 (kept); **`scale` 0.1** (new: the Orc Lord differs from the Orc Warrior / Archer mainly by SIZE) | adopt | 10 |
| D8 | `dying_in_view`: a frame with a unit in its die animation on screen is not whole (a drawn, unlabelled sprite) | adopt | 4g |

## 1. The facts (read before this commit)

### 1a. What was read before this commit (and nothing else)

- **The three FIT sessions' `manifest.json` and their packets** (event-type counts, map changes,
  species appearance counts by job, deaths, the count of `act` packets with our character by
  species and direction, floor-item falls by item id). No monster or item POSITION was used for
  anything. No frame (PNG) of any session was decoded.
- **The watch's runner log** (`events.jsonl`: its 15 cells, the spawns, the dwells, the
  `@killmonster2` lines).
- **Client data, extracted to /dev/shm (client-derived, never committed):**
  - `gef_fild10.rsw` (MIXCRYPT, `grf_read.py --decode-mixcrypt`, Batt 2026-10-05 option (a), study
    only) and its 46 RSM models: `/dev/shm/poring-lab-tmp/gef10-det/grf/`;
  - the species' SPR / ACT (gef10-prep.md section 9's extraction; copied with the lab's and
    payf07's into one folder): `/dev/shm/poring-lab-tmp/gef10-det/sprites-all/`;
  - 13 floor-item sprites (`data\sprite\아이템\`, DES / MIXCRYPT decoded) and the client's
    `idnum2itemresnametable.txt`: `/dev/shm/poring-lab-tmp/gef10-det/items/`, `.../grf/data/`;
  - the label KB (the installed `data/kb/classes.json`, which holds gef_fild10 since 19:49, and the
    merged sprite-name table): `/dev/shm/poring-lab-tmp/gef10-det/kb/`.
- The drop tables (`data/kb/drops.json`), for expected counts only.
- **No TRAIN session was read** (4.05's s1, `20261025T204315-rdp-rogue-s1`, was being recorded
  from 20:43; nothing of it was opened). **No TEST session existed, and none is listed or opened by
  this work** (s7, s8; the watch's cells 11-14 are not read beyond the packet counts above).

### 1b. The species (pinned rAthena e985006, pre-renewal; gef10-prep.md 1a, 9)

| species (mob id) | spawns on gef_fild10 | walk (ms / cell) | idle sprite box (native px) | idle size | flies? | stem | idle hue / sat |
|---|---|---|---|---|---|---|---|
| Orc Lady (1273) | 70 | 200 | -25.5 -76 25.5 10 | 51 x 86 | no | `orc_lady` | 73° / 0.35 |
| Orc Warrior (1023) | 20 | 200 | -31.5 -83 33.5 13 | 65 x 96 | no | `ork_warrior` | 36° / 0.35 |
| Poporing (1031) | 15 | 300 | -18.5 -30 18.5 6 | 37 x 36 | no | `poporing` | 74° / 0.30 |
| Orc Baby (1686) | 5 | 200 | -12.5 -46.5 32.5 4.5 | 45 x 51 | no | `orc_baby` | 56° / 0.42 |
| Orc Lord (1190), MVP | 1 | 100 | -35.5 -89 45.5 11 | 81 x 100 | no | `orc_lord` | 41° / 0.38 |
| Orc Archer (1189; 1473 the same sprite) | the Orc Lord's 5 slaves | 300 | -23 -77.5 43 11.5 | 66 x 89 | no | `orc_archer` | 30° / 0.36 |
| Blue Plant (1079) | 3 + 3, fixed areas (46,350) / (287,61) +- 5 | immobile | -20 -15 20 15 | 40 x 30 | no | `blue_plant` | 220° / 0.64 |
| Green Plant (1080) | 3, (300,253) +- 5 | immobile | -20 -15 20 15 | 40 x 30 | no | `green_plant` | 83° / 0.42 |

- **No species flies** (every idle box reaches the ground): orcsdun01's flyer anchor (1b there) and
  W do not apply.
- **Look-alikes the class scheme and the blind check must separate:**
  - **Orc Lord vs Orc Warrior vs Orc Archer: the same colour** (hue 41 / 36 / 30°, sat 0.38 /
    0.35 / 0.36); they differ in SIZE (81 / 65 / 66 px wide idle) and gear. Hence D7's `scale`
    flag (10) and the instructions' "differ mainly in SIZE" (6);
  - the orcs of v2orc's classes (Orc Zombie 14, Orc Skeleton 13) are orcs too: in the reference;
  - Poporing (19, pay_fild07's class) vs Poring (3): hue 74° vs 2°;
  - Green Plant (20) vs White Plant (10) vs Blue Plant: hue 83° / 36° / 220°;
  - Orc Lady vs Poporing share a hue (73° / 74°) but not brightness (value 0.41 vs 0.79) or size.
- **1473 (G_ORC_ARCHER)** is summoned only when the Orc Lord has <= 3 slaves; it is not seen in any
  FIT session (1d) and is NOT a class (a frame with one in view is excluded, `unchecked_species`).
- **ENGAGED units:** 95 of the 110 normal monsters are aggressive (gef10-prep.md 7): they come to
  us, and a hunting frame often holds a monster fighting our character (1d's act counts).

### 1c. The map and its models

- 400 x 400 cells; client and server agree on every walkable cell (gef10-prep.md 2). Not indoor:
  the fitted OUTDOOR camera plus the GAT altitude, as pay_fild07 and orcsdun01.
- **The RSW:** version 2.1, **1,497 models from 46 RSM files** (pay_fild07: 1,212 from 9), sha256
  `b9b0e9bdafd8a3ca6249fbeecb64da0f5c09aa9bbd0d3a9534b56ccdbfe25bcf`; also 131 sounds and 18
  effects. Every RSM is version 1.4 and parses. The files, translated, by count:
  - trees and plants: leaves (626 placed), bush 01 (96), trunk 01 (93), vine 03 (70), tree 07
    (67), vine 01 (45), bush 00 (44), vine 02 (36), tree 02 (34), bush 02 (24), trunk 02 (17),
    mushroom 03 (16), a wood piece (10), mushroom 01 (5), rock (4), trees 04 / 05 / 06 (3 each);
  - the orc village: orc fence (131), skull (32), lotus (22), orc house (20), orc flag (18), bone
    (14), house door (9), bridge 02 (8), well bucket (6), well (4), axe (4), spider web (4), cart
    (3), drums (3 + 2), hero house and its door (2 + 2), skull arm (2), bridge 01 (2), wooden boxes
    (2 + 2), pillars (2 + 1), a bundle (2), firewood, a skull body, a ruined house, a barrel (1
    each).
- **The canopy, measured on the model geometry** (the cell footprint of each placed model's
  vertices, against the GAT's walkable cells; not yet a screen measure):
  - the 626 leaf planes float at altitude 44-62 (medians of their min / max), 16 x 16 cells each;
  - **45.9 % of the walkable cells lie under the footprint of a model taller than 20 altitude
    units, 39.7 % under a leaf plane**; 48.3 % under any model's footprint.
  - So, as on pay_fild07, most labels in tree areas will be "under a model box", and o3h's fit
    evidence decides (4e). The screen-space share per species is a FIT measurement (13).

### 1d. The sessions (recorder v5, RDP via the frame bus, 1 fps lossless PNG, 1280 x 720, packets)

| session | what | frames | packets | role (section 3) |
|---|---|---|---|---|
| `20261025T195325-rdp-ow1` (local `/dev/shm/poring-lab-rec/`, then the NAS) | the immune Rogue's Orc Lord watch: 15 lattice cells, at each `@monster 1190 1`, a 40-s dwell, `@killmonster2`; 19:53-20:07 | 835 | 3,312 | cells 0-10 FIT + TRAIN; cells 11-14 TEST |
| `20261025T200922-rdp-rogue-pilot` (NAS) | 4.05's pilot (hunting, immunity off); 20:09-20:25 | 940 | 1,940 | FIT + TRAIN |
| `20261025T203115-rdp-rogue-pilot2` (local, then the NAS) | 4.05's pilot 2 (arm S, Steal first); 20:31-20:42 | 523 | 1,560 | FIT + TRAIN |
| `*-rdp-rogue-s1` ... `s6` | 4.05's scored runs (40 min each), recorded tonight | (none at this commit) | | TRAIN, by the join rule (3c) |
| `*-rdp-rogue-s7`, `s8` | 4.05's scored runs 7 and 8 | (none at this commit) | | **TEST: never read, listed or opened before the freeze** |
| `20261025T202831` (17 frames) | a failed start | 17 | | not used |

**The packets, per FIT session** (counts only):

| | watch ow1 | pilot | pilot 2 |
|---|---|---|---|
| map changes (gef_fild10) | 15 (one per cell, `@warp`) | 2 (one before the recording) + 1 to prt_fild08 at the end | 3 (one before) + 1 to prt_fild08 |
| units seen, by species | Orc Archer 75, Orc Lady 19, Orc Lord 15 (spawned), Orc Warrior 9, Poporing 4, Orc Baby 2 | Orc Lady 17, Orc Archer 5, Poporing 5, Orc Warrior 3, **Orc Lord 1 (natural)**, a house-door portal 1, Poring 1 (prt_fild08) | Orc Lady 18, Orc Warrior 4, Poporing 1, Orc Baby 1 |
| deaths | (the `@killmonster2` lines) | Orc Lady 14, Orc Warrior 3 | Orc Lady 10, Orc Warrior 2, Poporing 1, Orc Baby 1 |
| `act` with our character (it -> us / us -> it) | 0 / 0 (immune) | Orc Lady 251 / 135, Orc Warrior 37 / 24 | Orc Lady 246 / 97, Orc Warrior 23 / 14, Orc Baby 24 / 6, Poporing 0 / 2 |
| floor-item falls | 0 | Cyfar 6, Orcish Voucher 3, Rough Oridecon 1 | Cyfar 8, Orcish Voucher 2, Large Jellopy 1, Milk 1 |

- The watch's structure (its log and its map changes): each cell = a `@warp` to the cell, the
  `@monster` line ~9 s later (the Orc Lord and its 5 Orc Archers appear near us), a 40-s dwell,
  `@killmonster2` (every monster on the map dies without drops and respawns). Cells are ~56 s
  apart. Its natural population is thin by construction (19 Orc Ladies over 15 cells).
- The 1189 Orc Archers stay within ~2 cells of the Orc Lord (`MOB_SLAVEDISTANCE`), so few of them
  are "isolated by 120 px" (C1's standing rule): C1 will judge the Orc Lord and its archers on few
  labels. That is a known limit, reported (5).

### 1e. Floor items (what will be on the floor, and how big it is drawn)

Expected falls from the drop tables (`data/kb/drops.json`, rates as mob_db, every `item_rate_*`
100; MVP drops out) times the FIT pilots' kill mix (Orc Lady 24, Orc Warrior 5, Poporing 1, Orc
Baby 1 in 25.8 min on gef_fild10), scaled to TRAIN's 6 x 40 min:

| item (id) | FIT expected / seen | TRAIN expected (6 x 40 min) | sprite (native px, w x h; ACT action 0, frame 0) |
|---|---|---|---|
| Cyfar (7053) | 11.2 / 14 | **~104** | 14 x 22 |
| Orcish Voucher (931) | 4.5 / 5 | **~42** | 21 x 19 |
| Iron (998) | 0.8 / 0 | ~8 | 19 x 17 |
| Sticky Mucus (938) | 0.6 / 0 | ~5 | 18 x 14 |
| Milk (519) | 0.5 / 1 | ~5 | 12 x 21 |
| Garlet (910) | 0.2 / 0 | ~1 | 15 x 17 |
| Large Jellopy (7126) | 0.1 / 1 | ~1 | 14 x 16 |
| Rough Oridecon (756) | 0.02 / 1 | ~0.2 | 16 x 13 |
| Axe (1301), Green Herb (511), Apple (512), Grape (514), Milk Bottle (7270) | <= 0.05 each | < 1 each | 34 x 30, 22 x 22, 12 x 14, 10 x 16, 21 x 22 |

- **Every item sprite has ONE action and ONE frame**: the drawn box is the sprite's own extent.
- **The client draws items at ~1:1 native pixels on this camera:** target-items.md 10.9a's
  templates (cut from pay_fild07 frames) are 13 x 16 (h x w) for Rough Oridecon, exactly this
  sprite's 16 x 13; item-class.md 8b's blind round found the TEMPLATE boxes too small ("the box
  cuts the item"), and named the sprite's own extent as the fix. This rule uses it (8).
- Snatcher steals do not change the floor: a stolen item goes straight to the bag.

## 2. What is reused from payf07, unchanged

From payf07-detector.md (2, 4, 11; its rule "payf07-o3h-all") and its tool `scripts/map_labels.py`:
- **fix 2's facing** (`orc_facing_study.fix2_heading`), **2b** (`next_move`, 150 ms timeline time)
  and **2c** (`ambiguous_view`);
- **boxes from the sprites:** the expected sprite (species, the Timeline state's action, the
  facing, the one-shot frame from its elapsed time or a looping action's best frame) at the
  projected position at the 1d time; the LABEL box = the best masked-NCC fit within +-r px; a fit
  below tau 0.092, at the search edge or unscorable is EXCLUDED (`crowd` / `ui` / `unfit`);
- **k 0.140, tau 0.092, the search +-16 px for C2, the fit radius +-6 px;**
- **the standing rule for C1 / C2** (idle >= 1 s, isolated 120 px from every unit incl. our own
  character, the box grown by 16 px clear of the UI and the frame edge);
- **o3h** (a label whose predicted box overlaps a model's projected box is kept only when its fit
  passes AND its NCC >= T_h) and **the T_h floor on EVERY kept label** (payf07 11's `weak_fit`: a
  label not under a model with NCC < T_h is excluded, and its frame is not whole);
- **a frame with any excluded monster label is not labelled whole** (it never enters the cache);
- the candidate frames (payf07 4f) without the staged inventory span (no items are staged here);
- the frame exclusions of payf07 4g: `warp_in_view` (objtype 6: the 9 portals and 5 script NPCs
  of this map; the warp / NPC classes' own rules are not built for it), `other_player`,
  `unchecked_species`;
- **Amendment B's engagement test** (an `act` between the unit and our character, either way, or
  our `attack_request` on it, within [tw - 3 s, tw + 1 s]); here it SELECTS the engaged rule (4h)
  instead of excluding;
- **the join rule 3c** (own C1 <= 0.050 on >= 50 standing labels scored);
- our own character's box (labels v2's self box, v0's 34 x 74 at the camera target) as `player`;
- the hunting layout read from pixels per frame (`client_layout.read` = `hunt`).

## 3. The split (FIT / TRAIN / TEST), fixed now (before any frame is read)

### 3a. The watch, by CELL (decision D1)

- **Cell k** = the time from the k-th `map_change` to gef_fild10 in the watch's packets (0-14, in
  time order; they are the log's 15 cells in its order) up to the next one (the last: to the end of
  the session).
- **Cells 0-10 are FIT (and TRAIN); cells 11-14 are TEST** (the last four: (82,137), (159,302),
  (335,159), (93,93)), as payf07's staged spots 8-11 were the last four.
- **Why a TEST share of the watch:** the Orc Lord and its archers are met only in the watch (and
  once, naturally, in the pilot). The scored runs type `@killmonster2` at their setup
  (rogue-gef10.md A4), so s7 / s8 may hold no Orc Lord at all. Without held-out cells, T1 and the
  evaluation would have no Orc Lord.

### 3b. The sessions

- **FIT** (every parameter is measured here and only here): watch cells 0-10 + `pilot` + `pilot2`.
- **TEST** (never read for fitting or training; read only by T1 after the freeze, and by the model
  evaluation): watch cells 11-14 + **s7 + s8** (by name: `*-rdp-rogue-s7`, `*-rdp-rogue-s8`). The
  tools refuse them by name and by cell.
- **TRAIN:** the FIT parts, and every 4.05 session admitted by 3c (s1-s6, and any other later
  gef_fild10 session of the same recording path that is not TEST).
- **T2's pool:** the kept labels (under the FROZEN parameters) of the FIT parts and of the TRAIN
  sessions admitted by 3c when the pack is built.

### 3c. The join rule for later sessions (payf07 3c, unchanged)

A session recorded AFTER this commit joins TRAIN (never TEST) when ALL hold: the same recording
path (manifest `backend` rdp, `recorder_version` 5, `format` png, `game_region` [80, 77, 1280,
720], `server` lab-rathena, `packets.jsonl.gz`); labelled by the frozen parameters with the frozen
tool; **its OWN C1 pooled <= 0.050 on >= 50 standing labels scored**; with fewer it is not added.
The FIT pilots train under the same own-C1 rule (`check --allow-fit`); the watch's FIT cells train
when the tier passes (as payf07's staged FIT spots).

## 4. The label rule, "gef10-o3h-e" (what changes for gef_fild10, and why)

### 4a. Map and models
gef_fild10, 400 x 400; its RSW and 46 RSMs (1c); their sha256 are frozen with the parameters. The
occlusion test is orcsdun01's 1c (each model's projected vertex box).

### 4b. 1d: the packet -> frame offset, re-measured on FIT (decision D2)
- payf07 4b with its Amendment A, unchanged: walkers walking ONE move through the whole sweep
  (0..500 ms, coarse 50 ms, then 10 ms within +-50), isolated 120 px, clear of the UI / edges by
  16 px and of every model box at every offset; the error = |best-NCC offset| within +-16 px of the
  rendered walk sprite; the smallest MEDIAN error wins.
- **The walkers:** every mobile species: 1273, 1023, 1686, 1031, 1190, 1189.
- **Stop:** fewer than 50 walker samples, or the best coarse offset at the sweep's edge (0 or
  500 ms): nothing is measured as frozen; then **the proposal is 120 ms** (payf07's Amendment C:
  the 1-fps recorder reads the same RDP frame bus as orcsdun01's warp_watch, 120 ms on 260
  samples there; payf07's FIT attempts put the minimum at 100-150 ms and its diagnostic on TRAIN
  sessions found 120 ms on 89 samples). The parent decides by an amendment. A diagnostic on TRAIN
  sessions (never TEST) may be added and is reported, never frozen.

### 4c. No anchor
No species flies. The per-species median best-NCC offset of FIT's clear kept labels is REPORTED.

### 4d. The fit radius
+-6 px for every species.

### 4e. T_h, re-measured on FIT
payf07 4e's definition with Amendment B's exclusion: **the pooled 5th percentile of the fit NCC of
FIT's kept labels that lie CLEAR of every model box and are NOT engaged** (every FIT candidate
frame; the fit, tau and edge rules of section 2). Frozen to 3 decimals. It applies (o3h) to labels
under a model box AND (the floor) to every other kept label, engaged ones included.

### 4f. The candidate frames
A frame (capture time t; timeline time tw = t - 1d) is a candidate only when ALL hold:
- the map at tw and at t is gef_fild10, and no `map_change` lies in [t - 5 s, t];
- **our character stands still:** its Timeline position is the same at every 100 ms from
  tw - 1,000 ms to t;
- outside the GM-command windows (the watch's `@monster` / `@killmonster2` lines, the runs'
  setup lines);
- the watch: inside a cell (after its first map change);
- the hunting layout read from pixels (`client_layout.read` = `hunt`); else `ui_layout_mismatch`.

### 4g. Frame-level exclusions (a frame is not labelled whole)
payf07 4g's (`warp_in_view`, `other_player`, `unchecked_species`) plus, NEW (decision D8):
- **`dying_in_view`:** a unit in its die animation (the Timeline's `dying` state, the sprite
  catalog's die length) whose anchor projects on screen. Why: the hunting runs kill ~70 monsters an
  hour (the pilots: 31 in 25.8 min); a dying sprite is drawn for its die animation and no rule
  labels it, so it would train as background. (v1 / v2 / payf07 had the same hole; it is closed
  here because kills are frequent and near the camera.)

### 4h. ENGAGED units: LABELLED (the change from payf07; decision D3)

**Who:** a monster is ENGAGED at tw by Amendment B's test (2).

**Why payf07's prediction failed for them** (payf07 10c, a FIT measurement there): engaged Elder
Willows fitted at median 0.127 against 0.784 for the others. Three causes are visible in the rules
themselves, none measured yet on this map:
- our own character stands next to the unit (melee), so the masked NCC is computed partly over OUR
  sprite's pixels;
- an engaged unit faces its fight, not its last walk: the client turns an attacker toward its
  target; fix 2 keeps a walk's facing when the attack's turn is older than the walk (3b's rule);
- the attack / hurt actions are one-shots whose phase (the elapsed time since the act) is off by
  up to 1d's offset and the client's own timing (the timeline's module notes: the client plays an
  attack at its ACT speed, the target flinches at the damage frame).

**The variants** (each with fix 2's rule for every NOT engaged unit, unchanged):

| variant | facing of an engaged unit | the images fitted | our own sprite |
|---|---|---|---|
| E0 (payf07 Amendment B) | -- | -- (EXCLUDED: `engaged`) | -- |
| E1 | fix 2's | the Timeline action as payf07 (its known frame when the phase is known) | not masked |
| E2 | WALKING: fix 2 (ii); otherwise TOWARD our character (rAthena's `direction_toward` from its cell to ours) | every frame of the Timeline action (the phase is not trusted) | **masked**: our self box (34 x 74 at our feet, + 4 px) is removed from the fit's valid pixels |
| E3 | as E2 | every frame of the Timeline action, of IDLE, of ATTACK and of HURT, at that facing; the best | masked, as E2 |

- For every variant: the fit radius +-6 px, tau, the edge rule, **the T_h floor** (4e), 2b; 2c only
  when the facing came from a move (fix 2's (iii)). The box = the fitted frame's extent, as every
  label. The label carries `engaged: true` (T2's stratum, the counts).
- **The selection, on FIT (measured, then frozen):** among E1, E2, E3, the variant that KEEPS the
  most engaged labels on FIT whose kept engaged fits have a **median |dx| <= 2 px AND median
  |dy| <= 2 px** (a true match sits near the prediction, as C2's 1 / 1 px on every species of
  pay_fild07 and orcsdun01; a spurious best-of-many fit wanders over the +-6 px window); ties go to
  the simpler variant (E1, then E2, then E3). If no variant meets the offset bar: **E0** (engaged
  units excluded, payf07's rule), reported.
- **Reported per variant (not deciding):** engaged fates per species; the share passing the floor;
  the median NCC; the median offsets; the kept engaged labels and the frames they make whole.
- **E0 stays the fallback** wherever T2 does not pass the engaged stratum (6, D5).

### 4i. Frozen with the parameters
1d, T_h, tau, k, the fit radius, the engaged variant, the RSW / RSM sha256, the tool's commit; the
file `/dev/shm/poring-lab-tmp/gef10-det/params.json` and its sha256, recorded in the RESULT
section. TEST is refused by the measuring commands (by session name and by cell).

## 5. T1: the geometric check (C1), on TEST

- **Data:** TEST (watch cells 11-14 + s7 + s8), every candidate frame (4f).
- **C1** = `bad_label` / standing labels scored (`label_check.classify`), pooled over the
  gef_fild10 species: the PREDICTION (fix 2's facing, the 1d time, no anchor, NO fit) at the
  projected position, after o3h's under-box rule, 2b and 2c. Engaged units are never standing
  (isolated 120 px from our character), so C1 judges the non-engaged rule only; the engaged rule is
  judged by T2's stratum (6).
- **T1 PASSES when C1 pooled <= 0.050** (the unrounded ratio).
- **Reported, not gating:** C1 per species and per TEST part (watch cells / s7 / s8); C2 per
  species (median |dx|, |dy| of the best-NCC offset within +-16 px; bar <= 4 px for a species with
  >= 20 standing labels); the exclusions by reason; the facing agreement by image.
- **C2 failing for a species is a STOP:** the parent tells Batt before any cache.

## 6. T2: the blind check (the parent runs the labellers)

- **The labellers:** two NEW blind labeller agents per round. Each sees ONLY the pack directory and
  `instructions.txt` = `docs/planning/gef10-blind-instructions.txt` (sha256
  `247b79197e47f732f4d1acf04bc6ed1ba2b7162c0c9fab26fe49cb5eab4b54b0`). The answer key lives in
  another directory.
- **Why new instructions:** payf07's (sha256 `dc3ee728…19f9`) describe "a forest field" and "a
  red-haired thief". Here: an open field with orc huts and fences, a red-haired ROGUE, monsters
  FIGHTING it (attack poses, flinching, overlapping the character), and orcs that differ mainly in
  SIZE. The questions, the answer format and the box drawing are unchanged.
- **The seed: 31** (21 / 22 payf07's rounds, 23 payf07's evaluation; 32 is this map's item round,
  33 / 34 are reserved for this map's monster / item evaluation).
- **Two strata per species**, from T2's pool (3b), each sorted by (session, frame, gid) and
  shuffled with `random.Random(f"gef10:31:{mob}:{stratum}")`, the first 30:
  - **N (not engaged):** the kept labels of units that are not engaged;
  - **E (engaged):** the kept labels with `engaged: true` (under the variant 4h chose).
  - Fewer than 30 in a stratum: all of them. A species with fewer than 30 kept labels in N is not
    in the tier (7, D4). A species with no E labels has no E stratum.
- **The reference** (`reference.png`): 12 species under letters A-L in a seeded order, MULTI-VIEW
  (orcsdun01 3l): the 8 gef_fild10 species (1273, 1023, 1031, 1686, 1190, 1189, 1079, 1080) +
  Poring (1002), White Plant (1082), Orc Zombie (1153), Orc Skeleton (1152).
- **The bars (unchanged), per species per stratum:** >= 90 % "good" from EACH labeller AND the
  species right on >= 95 %. Scored by `scripts/blind_score.py` (per stratum: the key records it).
- **T2 passes** when the N stratum passes for EVERY species in the tier. **An E stratum that fails**
  removes that species' engaged labels (their frames are not whole, as E0); it does not fail the
  tier (D5).

## 7. The class scheme (PROPOSED; the default if Batt does not answer by the time the labels pass)

**ONE model:** payf07's 21 classes, ids 0-20 UNCHANGED (`config/detector/classes-v2orc-payf07.json`),
then this map's new species, then the floor items:

| id | class | source |
|---|---|---|
| 0-2 | player, npc, warp | v2orc |
| 3-14 | Poring, Lunatic, Pupa, Drops, Creamy, Familiar, Steel Chonchon, White Plant, Black Mushroom, Drainliar, Orc Skeleton, Orc Zombie | v2orc |
| 15-20 | Elder Willow, Willow, Eggyra, Bigfoot, **Poporing (1031)**, **Green Plant (1080)** | payf07 (Poporing and Green Plant spawn here too: their ids are reused) |
| 21 | Orc Lady | 1273 |
| 22 | Orc Warrior | 1023 |
| 23 | Orc Baby | 1686 |
| 24 | Orc Lord | 1190 |
| 25 | Orc Archer | 1189 |
| 26 | Blue Plant | 1079 |
| 27 | Cyfar (floor item) | item 7053 |
| 28 | Orcish Voucher (floor item) | item 931 |
| 29 | item (every other floor item) | any other item id |

- **Conditional classes (D4):** a gef_fild10 species trains on this map's labels only with >= 30
  kept labels in T2's pool (N stratum) and its T2 pass. Otherwise it is not in the tier, and every
  frame with that species in view is excluded (`unchecked_species`), so it never trains as
  background. For Poporing and Green Plant (ids 19, 20) that means: no gef_fild10 box this round,
  and their pay_fild07 boxes (linked) still train. Expected thin: Blue Plant (6, two fixed areas
  far from the hunting start), Green Plant (3), Orc Baby (5), Orc Lord (the watch), Orc Archer.
- **Engaged labels use the species' class** (no new class). A thin class trains and is reported
  apart, with no bar of its own until it reaches 50 held-out labels (orcsdun01 section 4).
- **The floor-item classes (D6, section 8):** Cyfar and Orcish Voucher are the only items with
  enough floor items in TRAIN (~104 and ~42 expected, 1e) and the two that carry the value
  (rogue-gef10.md 2c). Every other floor item is the pooled class 29, so that no drawn floor item
  is ever left unlabelled in a cached frame. An item class with fewer than 40 kept labels from at
  least 10 floor items in TRAIN, or failing its blind check, does not train: every frame with such
  an item labelled is excluded (`unlabelled_item`).

## 8. The floor-item label rule, "gef10-items"

- **The floor span (item-class.md 3a, its frozen delays):** an item is on the floor from its
  `floor_item_appear` (either kind) to its `floor_item_vanish` or our map change. On a frame at t:
  LABELLED when `t_a + 2.2 s <= t < t_v`; the frame is excluded while `t_a <= t < t_a + 2.2 s`
  (`item_settling`) and while `t_v <= t < t_v + 0.6 s` (`item_vanishing`).
- **Where:** the item's fractional cell = `(x + OX[sub_x], y + OY[sub_y])` with item-class.md 8a's
  frozen sub-cell table (OX -0.189 / 0 / +0.185 / +0.376, OY -0.210 / 0 / +0.173 / +0.329 for sub
  3 / 6 / 9 / 12; the client's rule is map-independent), projected like a monster's anchor (the
  camera on our still cell, the GAT altitude). Only on the monsters' candidate frames (4f: our
  character still).
- **The box: the item's own client sprite** (its one ACT frame, rendered by the monsters' billboard
  rule `predict_sprite` at the projected point, + the item ANCHOR), fitted by the masked NCC within
  +-6 px. **The anchor** (one offset for all items, px) = the median best-NCC offset of FIT's
  clear item samples (aged >= 2.5 s and >= 1.0 s before the vanish, clear of our box, our bar and
  every unit's box, not under a model box, >= 30 px from the UI); >= 12 samples, else STOP (the
  items wait for more FIT data: an immune staged-items session on gef_fild10, the parent's call).
  **T_item** = the p5 of those samples' fit NCC (3 decimals). A label whose fit is below T_item or
  at the search edge is `item_unfit` (its frame is not whole). Under a model box: kept only when
  the fit passes T_item (o3h for items).
- **Item exclusions** (frame-level): `under_self` (our self box + 4 px), `under_self_bar`
  (target-items.md 10.3's (-36, 0, +36, +24) px at our feet), `under_unit` (any unit's predicted
  box over the item's box), `stacked` (two item boxes with IoU >= 0.5), `ui_partial` /
  `edge_partial`; wholly behind the UI or off screen: not drawn, no label.
- **A cached frame needs BOTH label sets whole** (item-class.md's Route M): the monster labels of
  section 4 AND every floor item's label.
- **Checks:** G2 on TEST (the median |dx|, |dy| of the item fit at the frozen anchor <= 3 px, a
  STOP, as item-class.md 5); the item blind round (seed 32) with item-class.md's instructions
  byte-identical (`docs/planning/gef10-item-blind-instructions.txt`, sha256
  `7d0a97041201f3d622f663115de9cb4d128afe4859706f388d1b35b3076e125c`, equal to
  `item_labels.INSTRUCTIONS`): per item class 40 item crops (at most 3 per floor item) + 20
  negatives; bars from EACH labeller: >= 90 % good box, >= 95 % item-present right.
- **What it needs that does not exist yet** (not built here): the item labeller over recorder
  sessions (item sprites rendered, the anchor fit), and the cache's Route M (monster + item boxes in
  one frame).

## 9. What passes the TRAINING TIER, and what follows

- **The monster tier passes** when T1 passes (5), T2 passes for every species in the tier (6, 7),
  and no C2 STOP. Then gef_fild10's TRAIN monster labels may train (engaged ones per their stratum).
- **The item tier** (per item class) passes with G2 (no STOP) and its blind round; independent of
  the monster tier, but an item frame enters the cache only with its monster labels whole.
- **If a tier fails,** nothing of it trains, and the report says which condition failed and by how
  much.

## 10. PROPOSED: the cache and the training run (nothing built here)

- **The cache:** `build_frame_cache.py --labels map` on the gef_fild10 TRAIN label files (frozen
  params, own-C1 checks), **linked to `v2orc-payf07-20261024`** (6,377 pay_fild07 frames + v2orc's
  16,169 by its own link: 22,546 in its manifest). A link to a cache that itself links is untested:
  the dry run must show its frames and shards resolve before the build.
- **Init weights (D7): payf07's epoch-1 `last.pt`**
  (`/mnt/poring-lab-datasets/archive/train/payf07-20261024/weights/last.pt` after 13g's archive):
  - it is v2orc's epoch-3 `last.pt` trained one more epoch on v2orc's data PLUS pay_fild07's 6,377
    frames (val mAP50 0.800 against v2orc's 0.805 on the same VAL: no forgetting measured);
  - it has seen outdoor fields, forest shade and canopy (pay_fild07), the nearest domain to
    gef_fild10, and Poporing / Green Plant, which spawn here too;
  - against: it is a mid-schedule checkpoint (lr not annealed), which does not matter for a new run;
    the class branch's last layers change shape (21 -> 30 classes) and start fresh either way.
  - v2orc's epoch-3 `last.pt` is the alternative: one epoch less of data, no field domain.
- **Settings:** YOLO11n, seed 20261004, imgsz 1280, batch 2, workers 1, `hsv_s` 0.2 (payf07's flag,
  kept), **`scale` 0.1** (new, D7: ultralytics' default 0.5 rescales an image by 0.5-1.5, which
  erases the 25 % width gap between the Orc Lord (81 px) and the Orc Warrior / Archer (65 / 66 px);
  the RO camera's zoom is fixed, so size is a real cue), E and close_mosaic as payf07 13b (10 / 3)
  unless the parent decides otherwise, WORKER=1 MID_CKPT=1, R1-R3, the IO guard, the 25 % VRAM cap.
- **Time (an estimate, waits for TRAIN data):** payf07's epoch 1 took 3,242 s of training for
  16,793 TRAIN frames (0.193 s per frame-epoch running). With N_g gef_fild10 frames written, an
  epoch is ~(16,793 + N_g) x 0.193 s; at E = 10 and payf07's N_g-free figure that is ~9.0 h
  running before stops. N_g is unknown until s1-s6 are labelled (payf07's hunting runs wrote 50-70 %
  of their candidate frames).

## 11. PROPOSED: the evaluation (to be pre-registered on its own, BEFORE training)

- **P1 per species** on TEST's blind-judged crops (seed 33, two NEW labellers, the frozen labels of
  watch cells 11-14 + s7 + s8): recall and precision >= 0.80 for a species with >= 50 evaluated
  crops; fewer: reported. **E1:** the same on the ENGAGED crops (its own bar at >= 50).
- **Items:** per item class on TEST's fitted item labels both labellers judge good (seed 34):
  recall and precision >= 0.80 at >= 50 crops.
- **No forgetting:** v1's gold set and held-out prt_fild08 sessions no worse than v1 (P 0.902 / R
  0.830); orcsdun01's col2 per v2orc-vs-v1.md; pay_fild07's TEST per payf07-eval.md.
- **Reported:** the Orc Lord vs Orc Warrior / Archer confusion, Poporing vs Poring, the plants;
  latency per frame on GPU vs CPU.

## 12. What the parent runs, in order

1. Read section 0; record the decisions (an amendment) BEFORE any TEST frame is read.
2. s1-s6 as they ship: label each with the frozen parameters (`map_labels.py labels --map
   gef_fild10`), and check its own C1 (`map_labels.py check`): 3c.
3. Freeze (`map_labels.py freeze --map gef_fild10`), then T1 on TEST (`check` on watch cells 11-14
   + s7 + s8): the first TEST read.
4. T2: the pack (seed 31, two strata) from the frozen labels; two NEW labellers; `blind_score.py`.
5. Items: the item labeller (8) and its checks, if built.
6. The evaluation pre-registered; then the cache (dry run first), then training (10).

## 13. RESULTS (appended below, clock-labelled; nothing above this line is edited after the pre-registration commit except by a labelled AMENDMENT)

### 13a. RESULT: 4b, 1d on FIT -- STOPPED (2 walker samples < 50); the proposal is 120 ms (D2)

- **Run** 2026-10-25 21:03:17-21:04:33 ICT at 9783aab's code (`map_labels.py offset --map
  gef_fild10`, FIT = watch cells 0-10 + pilot + pilot2; local
  `/dev/shm/poring-lab-tmp/gef10-det/fit/offset.json`). Nothing is frozen.
- **The candidates:** watch cells 0-10: 506 frames (dropped: the TEST cells and the time before
  cell 0, 217; GM windows 84; map changes 28); pilot 663 and pilot 2 401 at the sweep's 500 ms
  (our character moving 260 / 101).
- **The samples: 2** (both from the pilot). The watch gave 0: its Orc Archers stay within ~2 cells
  of the Orc Lord and of us (never isolated by 120 px), and its natural orcs are few; in the hunts
  the orcs walk straight into a fight. 4b's stop applies.
- The coarse curve (n = 2, median px; not evidence): 150 ms 6.4, every other offset 9.2-16.6.
- **By 4b, the proposal is 120 ms** (payf07 Amendment C's P1). D2 is the parent's.

### 13b. RESULT: 4e, T_h on FIT at 120 ms, attempt 1 -- every watch frame failed the hunting-layout check

- **Run** 2026-10-25 21:05:09-21:09:40 ICT at 9783aab (`threshold --proposed-offset-ms 120`;
  `fit/threshold-P1.json`): T_h came out 0.312 from 55 clear kept labels, **all from the two
  pilots**.
- **Why:** all 506 of the watch's FIT candidate frames were `ui_layout_mismatch`. By eye on two
  FIT frames (28 and 291) and from `client_layout.read`: the watch ran with the hotbar showing
  **4 rows** and the Basic Information panel **expanded** (the chat on Battle Log), not the hunting
  layout (1 row, collapsed). The pilots read as the hunting layout (pilot frame 300).
- Superseded by AMENDMENT A (below) and its re-run (13c). Kept for the record.

### AMENDMENT A (2026-10-25 21:10:53 ICT, from `date`; after 13b's FIT finding, BEFORE any parameter is frozen and before any TEST frame is read)

- **What changes (4f only, for the watch session):** a frame of the watch is a candidate when its
  layout READ from pixels has the hotbar at **4 rows** and the panel **expanded** (either chat
  tab); its UI rectangles are then `client_layout.RECTS["standard"]` (exactly that bar and panel;
  the chat window's rectangle is the same in both layouts, and the tab changes no rectangle).
  Every other session keeps the hunting layout of 4f.
- **Why:** the watch is the only source of the Orc Lord and its archers (3a), and its UI simply
  covers more of the screen; with the right rectangles the labels and their visibility / fit
  rules are the same rules. The layout is still read per frame: a watch frame in any other state
  is `ui_layout_mismatch`.
- **What stays:** everything else, including the split (3a), the stops and both tiers.

### 13c. RESULT: 1d and T_h re-run under Amendment A (FIT; nothing frozen)

- **1d** (21:11:51-21:13:28 ICT at eb84410, `fit/offset.json`; attempt 1 kept as
  `offset-attempt1.json`): **15 walker samples** (watch 13, pilot 2, pilot 2 none) < 50: **STOP**
  again. The coarse curve (n = 15, median px): 0 ms 17.7; 50 ms 10.0; **100 ms 3.6; 150 ms 5.8**;
  200 ms 14.4; 250-500 ms 13.6-18.4. The minimum lies at 100-150 ms, where orcsdun01 and payf07
  froze 120 ms. By 4b the proposal stays **120 ms** (D2).
- **T_h at 120 ms** (21:13:28-21:20:13 at eb84410, `fit/threshold-P1.json`; attempt 1 kept as
  `threshold-P1-attempt1.json`): **0.140** from 722 clear kept labels (p25 0.390, median 0.640).
  The watch's 506 FIT frames are all labelled now (2,257 fates).
- **Per species, the clear kept fits** (n, p5, median): Orc Lady 154, 0.412, 0.712; Orc Warrior
  31, 0.207, 0.680; Poporing 42, 0.718, 0.787; Orc Baby 1; **Orc Lord 97, 0.272, 0.663; Orc
  Archer 397, 0.126, 0.520**. The archers are 55 % of the measuring set and drag its p5 down.

### 13d. FIT diagnostic: the low fits are Orc Archers buried in their own pile (scratch, FIT only)

- Rows of the watch's FIT cells (`threshold --rows`, 21:20:53-21:23:47, `fit/th-watch-rows.json`)
  split by state, facing source, time since the `@monster` line and overlap with another FITTED
  box (`scratch/diag_th.py`): every split of the archers keeps a low tail (idle 117 of 380 under
  0.3; "after_move" facing 89 of 300; even those not overlapping another fitted box 8 of 43).
- **By eye on 12 low (< 0.3) and 12 high (>= 0.6) archer labels** (`scratch/archer_low.png`,
  `archer_high.png`, FIT frames): every low crop is an archer inside a tight pile of orcs (the
  Orc Lord's slaves are summoned onto its cell and follow within 2 cells), with the box in the
  right place but the archer mostly hidden by the others in front of it; some under emote bubbles
  or the summon's light. The overlap test on FITTED boxes misses these piles because the hidden
  neighbours fail their own fit (no fitted box).
- So the p5 measures mutual occlusion between monsters, not a visible label's evidence. payf07's
  measuring set had no such piles (its Amendment B removed the fights, the only units in contact).

### AMENDMENT B (2026-10-25 21:24:48 ICT, from `date`; after 13c / 13d's FIT diagnostics, BEFORE any parameter is frozen and before any TEST frame is read)

- **What changes (4e only):** T_h's measuring set = FIT's kept labels clear of every model box,
  NOT engaged, **and whose PREDICTED box overlaps no other drawn unit's predicted box** (every
  monster, player and our own character's self box, as the labeller's crowd test uses them).
  Still the pooled 5th percentile, frozen to 3 decimals.
- **Why:** 13d: the summoned archers stand in piles where each hides the others; their fits
  measure occlusion by units, which T_h (the evidence that a VISIBLE label is really drawn there)
  is not about. Units in contact are the same situation as payf07's engaged fights.
- **What stays:** the floor and o3h apply to EVERY kept label as before, crowded ones included (a
  buried archer's fit falls under the floor, so its frame is not whole); the label rule, C1, the
  split and the bars.

### 13e. RESULT: T_h under Amendment B, and what its low tail is (FIT; nothing frozen)

- **Run** 21:25:46-21:33:08 ICT at 3787d30 (`fit/threshold-P1.json`, rows `fit/th-rows-B.json`):
  **T_h = 0.265** from 222 clear, not engaged, uncrowded labels (p25 0.680, median 0.719); the
  pre-B set gives 0.140 (722). Per species (n, p5): Orc Lady 124, 0.498; Orc Warrior 23, 0.637;
  Poporing 41, 0.718; Orc Lord 8, 0.225; Orc Archer 25, 0.201. 91.8 % / 93.7 % of the Orc Lord's /
  archers' clear kept labels are crowded (their pile).
- **The low tail is the units whose FACING the packets never gave** (the Timeline's
  `facing_from` is None: no appear heading, turn, walk or stop seen; fix 2's (i)-(iii) do not
  cover them and the drawn view is a guess). Over every FIT fate: 43 of 3,333; clear and alone, 13
  with a median fit of 0.237 (10 of them under 0.3), against 0.727 (after a move), 0.714
  (walking), 0.743 (appear heading) for the others clear and alone. Without them the B set's p5
  is **0.636** (209 labels).
- The engaged selection started at 0.265 (21:33:08) was stopped at 21:34:24 (killed by PID) for
  Amendment C; nothing of it is used.

### AMENDMENT C (2026-10-25 21:34:34 ICT, from `date`; after 13e's FIT diagnostic, BEFORE any parameter is frozen and before any TEST frame is read)

- **What changes (2, the exclusions):** a new exclusion **2d `facing_unknown`**, handled as 2b /
  2c (the label is not kept, its frame is not whole; C1 drops it before scoring, as 2b / 2c): a
  unit whose drawn facing would come from the Timeline with NO source (no appear heading, no turn,
  no walk, no stop: `facing_from` None). It does not apply to an ENGAGED unit under E2 / E3
  (its facing is set toward our character, 4h).
- **Why:** 13e: those labels draw a guessed view and fit at a median 0.237 even when clear and
  alone; fix 2 was never defined for them. It is a label-quality rule (they are 43 of 3,333 FIT
  fates), and as a side effect T_h is no longer set by them.
- **What stays:** everything else, including Amendment B's measuring set.
- **For the parent (D9, new):** T_h is a strong lever here. Measured on FIT: 0.140 (A), 0.265
  (B), 0.636 (B without the unknown facings, a preview of C). payf07 and orcsdun01 froze 0.479 /
  0.48. 13f reports what each value keeps.

### AMENDMENT D (2026-10-25 21:42:11 ICT, from `date`; recording the parent's message of 21:39, rogue-gef10.md Amendment C, c650413; BEFORE any TEST frame is read)

- **The scored block restarted** after a minimap-reader fix; its runs are now **a1..a8** (then a9+),
  recordings `*-rdp-rogue-a1` .. `a8`.
- **TEST = watch cells 11-14 + a7 + a8** (by name `*-rdp-rogue-a7`, `*-rdp-rogue-a8`), replacing s7 /
  s8 everywhere in 3b, 5 and 11. The tools also keep refusing `*-rdp-rogue-s7` / `-s8` (they never
  exist).
- **TRAIN candidates (3c):** `20261025T204315-rdp-rogue-s1` (a partial 1,384-frame recording: its
  recorder stopped at ~21:09 on the IO guard, quant-postgres 27.3 %) and a1..a6. `s2`
  (`20261025T212506-rdp-rogue-s2`, 30 frames) is ignored (too short).
- Nothing else changes.

### 13f. RESULT: T_h under Amendment C, the box geometry and the occlusion test (FIT; nothing frozen)

**T_h** (21:35:55-21:41:59 ICT at 90dcf04; `fit/threshold-P1.json`, rows `fit/th-rows-C.json`):
**0.636** from 209 labels clear of every model box, not engaged, uncrowded, facing known (p25
0.687, median 0.723, p95 0.837). With crowded labels in (B's exclusion off): p5 0.136 (702).
Per species (the measuring set: n, p5, median): Orc Lady 119, 0.634, 0.717; Orc Warrior 23,
0.637, 0.687; Poporing 41, 0.718, 0.787; Orc Baby 1; Orc Lord 5, 0.691, 0.730; Orc Archer 20,
0.544, 0.709.

**What a value of T_h keeps on FIT** (D9; from the rows: frames that hold a monster fate and NO
engaged unit, 646 of the 1,071 with any fate; monster labels only, without 4g's frame rules, so an
upper bound of the whole frames; engaged units excluded, E0):

| T_h | whole frames (watch / pilot / pilot 2) | kept: Orc Lady | Orc Warrior | Poporing | Orc Baby | Orc Lord | Orc Archer |
|---|---|---|---|---|---|---|---|
| 0.265 (B) | 204 (91 / 108 / 5) | 222 | 31 | 109 | 5 | 226 | 688 |
| 0.479 (payf07's) | 150 (64 / 82 / 4) | 206 | 30 | 84 | 4 | 181 | 420 |
| **0.636 (C, measured)** | **134 (61 / 69 / 4)** | 179 | 30 | 68 | 3 | 126 | 175 |

- The floor mostly cuts the buried archers (688 -> 175) and labels under canopy (o3h: 874 of the
  1,143 under-box fits that pass tau lie below 0.636). The hunting pilots lose few whole frames:
  their frames are lost to the ENGAGED units instead (425 of the 1,071 frames hold one; 4h).

**The box geometry** (the fitted frame's box of FIT's clear kept labels, px; median w x h, with
p10-p90; the native idle box of 1b beside it):

| species | n | w (p10-p90) | h (p10-p90) | native idle | median fit offset (4c, reported) |
|---|---|---|---|---|---|
| Orc Lady | 149 | 50.6 (45.9-58.9) | 82.0 (74.3-92.7) | 51 x 86 | (1, 0) |
| Orc Warrior | 31 | 64.0 (56.8-71.4) | 94.8 (89.4-101.6) | 65 x 96 | (0, -1) |
| Poporing | 42 | 39.3 (36.5-41.7) | 36.3 (31.9-39.4) | 37 x 36 | (0, 0) |
| Orc Baby | 1 | 46 | 46 | 45 x 51 | (-2, 0) |
| Orc Lord | 94 | 76.7 (72.1-83.4) | 101.2 (96.1-108.0) | 81 x 100 | (0, 0) |
| Orc Archer | 385 | 62.4 (58.7-73.1) | 89.8 (85.1-93.7) | 66 x 89 | (0, -1) |

- The drawn scale is ~1:1 with the native sprite on this camera. **The size cue holds on screen:**
  the Orc Lord's box is ~20 % wider and ~7-13 % taller than the Orc Warrior's / Archer's (D7's
  `scale` flag).
- Every species' median fit offset is within 2 px (1 px for all with n > 1): no anchor (4c).

**The occlusion test (1c's projected model boxes, gef_fild10's 1,497 models):**
- **67.6 % of every FIT fate's predicted box overlaps a model box** (Orc Lady 63.3 %, Orc Warrior
  72.8 %, Poporing 81.3 %, Orc Baby 98.1 %, Orc Lord 65.9 %, Orc Archer 66.6 %); pay_fild07's
  forest was in the same range (o3h's evidence decides, as there).
- **Which models** (the first model whose box the FITTED box overlaps, for the under-box labels
  whose fit passed tau): leaves 418, tree 07 248, **orc house 180**, tree 02 153, trunk 01 40,
  vine 03 36, bush 01 35, others 14; 1,127 under-box fates have no fitted box (excluded before the
  fit, or the fit failed).
- The under-box fits that pass tau: n 1,143, median 0.411 (clear ones: 0.723): most labels under a
  canopy are poor evidence, as on pay_fild07 (0.676 there).

### 13g. RESULT: 4h's ENGAGED selection on FIT -- E2 is chosen, but it keeps only 14 engaged labels

- **Run** 21:41:59-21:48:40 ICT at 90dcf04's code (`map_labels.py engaged`, T_h 0.636, 1d 120 ms;
  `fit/engaged-P1.json`, sha256 `0b14ee60…999b`, rows `fit/engaged-rows.json`). Only frames with an
  engaged unit at tw are read: 428 (pilot 281, pilot 2 147; the watch has none: immune).

| variant | engaged fates | kept (fit passes, >= T_h) | median abs dx / dy of the kept | qualifies (<= 2 px) | whole frames among the 428 |
|---|---|---|---|---|---|
| E1 | 620 | 7 (1.1 %) | 0 / 1 | yes | 4 |
| **E2 (chosen)** | 620 | **14 (2.3 %)** | 0 / 1 | yes | 9 |
| E3 | 620 | 14 (2.3 %) | 0 / 1 | yes | 9 |

- E2 and E3 tie on 14; the tie goes to the simpler (4h). Kept per species under E2: Orc Lady 12
  (attacking 8, idle 2, walk 2), Orc Warrior 2 (walk). Orc Baby 0 of 21, Poporing 0 of 2.
- **Why so few:** under E2, 431 of the 620 fates fail the fit and **423 of them end at the +-6 px
  search edge** (395 called `crowd`: the predicted box touches our own); the 181 that pass fit at a
  median 0.18.
- **A scratch diagnostic** (`scratch/diag_engaged.py`, FIT pilots only, every 2nd candidate frame,
  21:58-22:00; `fit/diag-engaged-16px.json`): E2's prediction searched over +-16 px. Of 304
  engaged units, 245 peak inside the window; **the peaks are displaced systematically by the
  unit's side of us**: an attacker north-west of us (76 units) peaks at a median (+1, -9) px with
  NCC 0.650; south-east (47) at (+1, +6); north-east (18) at (-6.5, -8); south-west (36) at
  (-4.5, -1). So the client draws an engaged unit up to ~0.4 cell short of its packet cell along
  the side it came from (a client-side lag of the approach), beyond the +-6 px fit radius. At
  +-16 px, **76 of the 304 reach NCC >= 0.636** (60 attacking, 14 idle, 2 hurt; all Orc Lady),
  10 times E2's rate.
- **By eye** (`scratch/engaged_sheet.png`, 16 FIT crops; prediction red, the +-16 px fit green, our
  self box blue): the engaged orcs carry the client's overlays: damage numbers (large white
  digits), "Miss", the target's HP bar, name tags, our hand / sword cursor, and our own sprite;
  some engaged units stand under the canopy. Where the green box lands on the orc, it is the
  orc's body; the overlays are drawn over it.
- **What this means for D3 (the parent's):** the pre-registered selection chooses E2; it would
  label ~2 % of the engaged units (the rest exclude their frames, as payf07's E0). A variant **E4
  (E2 with a +-16 px fit radius for engaged units, the T_h floor unchanged)** would keep about ten
  times more on FIT; it is NOT pre-registered here and needs its own amendment and a T2 stratum
  before it trains.

### 13h. RESULT: C1 on FIT under the PROPOSED parameters (a DIAGNOSTIC: not T1, not 3c)

- **Run** 21:48:41-21:50:17 ICT (`check --fit-diagnostic`, `params-P1-proposed.json` sha256
  `275a8ed5…8121`; `fit/check-fit-diagnostic.json`): **C1 1 / 125 = 0.8 %** (the T1 bar is 5 %);
  Orc Lady 1 / 72, Poporing 0 / 41, Orc Warrior 0 / 12. C2: Orc Lady 1 / 1 px PASS, Poporing 0 / 1
  px PASS, Orc Warrior n 12 (no verdict).
- **The Orc Lord and its archers are never standing labels** (C1's standing rule needs 120 px of
  isolation; they stand in their pile): 1,608 standing candidates were `crowded`. T1 cannot judge
  them; T2 is their only check (a known limit, 1d).
- Per part: watch cells 0-10: 72 scored, 0 bad; pilot: 53 scored, 1 bad; **pilot 2: 0 scored** (a
  10-min hunt has no isolated standing monster: 3c's ">= 50 scored" may leave short hunts out).

### 13i. RESULT: the FIT labels under the PROPOSED parameters, through the cache's own frame rule

- **Labelled** 21:50:17-21:57:20 ICT (`labels-proposed/`: watch cells 0-10 `c9a1f202…`, pilot
  `425cdfae…`, pilot 2 `f8641d0f…`), then `build_frame_cache.map_frame` with the floor 0.636 (what
  a cache would write; our own `player` box not counted):

| part | candidates | frames written | ... with a monster box | boxes: Orc Lady | Poporing | Orc Archer | Orc Lord | Orc Warrior | engaged boxes |
|---|---|---|---|---|---|---|---|---|---|
| watch cells 0-10 | 506 | 131 | 61 | 45 | 4 | 20 | 9 | 4 | 0 |
| pilot | 689 | 275 | 77 | 34 | 44 | 0 | 0 | 0 | 9 (Orc Lady) |
| pilot 2 | 416 | 248 | 4 | 6 | 0 | 0 | 0 | 0 | 0 |
| **FIT** | **1,611** | **654** | **142** | **85** | **48** | **20** | **9** | **4** | **9** |

- **The frames lost, by reason** (a frame counts once per reason): `occluded_model` 686 (o3h at
  0.636), `crowd` 134, `weak_fit` 174, `next_move` 107, `ambiguous_view` 103, `dying_in_view` 59
  (D8's positive case: 59 frames with a die animation on screen), `facing_unknown` 36,
  `warp_in_view` 24 (the pilot's house door), `unfit` 20, `ui` 1.
- 🔴 **The yield is thin:** 142 FIT frames with a monster (8.8 % of the candidates). The causes, in
  order: the canopy and the orc houses (o3h), the Orc Lord's pile (crowd, weak fits), the engaged
  units of the hunts (13g). TRAIN (s1 + a1..a6, ~4.4 h of hunting) is expected to give the
  pilots' rate: (77 + 4) / 1,105 candidate frames ≈ 7 % of a hunt's candidates with a monster box,
  mostly Orc Lady and Poporing. A model trained on it would see very few Orc Warriors, Orc Babies
  and plants (0 so far).

### 13j. RESULT: the floor items on FIT (8)

- **Run** 21:57:20-21:57:45 ICT (`gef10_items.py measure`, pilot + pilot 2; `fit/items-P1.json`,
  sha256 `04307e93…a593`): 22 floor items (Cyfar 14, Orcish Voucher 5, Rough Oridecon 1, Large
  Jellopy 1, Milk 1); 240 labelled views on still frames (19 frames of the pilot, 85 of pilot 2).
- **Clean samples: 15, ALL from ONE floor item** (the pilot's Rough Oridecon): anchor **(-3, +1)
  px**, T_item **0.792**, MAD 0 / 0. 8's ">= 12 samples" holds literally, but from one place
  (target-items.md round 1 needed its amendment A for the same reason).
- **Why so few, per item** (views: reasons): Cyfar 47: under our HP bar 38 (the bot kills next to
  itself, the drop falls at its feet), young / vanishing 7, under a model 2; Orcish Voucher 105:
  under a model 49, beside another item 30, under our bar 20; Milk 41: under a model 40; Large
  Jellopy 30: beside another item 28.
- **Cyfar is picked up fast:** 8 of its 14 FIT floor items lived < 2.5 s (the bot's pickup), so they
  are never labelled (D_APPEAR 2.2 s); only 5 had any labelled still frame (13a's packets count:
  47 frames, 31 of them one item).
- **The drawn item boxes match the native sprites (scale 0.97-0.99):** Cyfar 13.5 x 21.2 px
  (native 14 x 22), Orcish Voucher 20.7 x 18.7 (21 x 19), Milk 11.8 x 20.7 (12 x 21), Rough
  Oridecon 15.5 x 12.6 (16 x 13), Large Jellopy 13.7 x 15.6 (14 x 16).
- **What it means (D10):** the hunting runs alone will not give per-item classes: nearly every
  floor item in view lies under our bar, under a tree / house, or beside another item. An immune
  staged-items session on gef_fild10's OPEN ground (stage_items.py's method, the target-items.md
  round-2 recipe: spots off the RSW footprints, Poporings cleared) is the way to the 40 labels /
  10 floor items per class of section 7.

### 13k. RESULT: 1d's diagnostic on a TRAIN session (never frozen)

- `offset --diagnostic` on s1 (21:57:45-21:58:20, `fit/offset-diag-s1.json`): 6 walker samples
  (1,015 candidates); the coarse minimum again at 100-150 ms (5.6 / 5.1 px median), every other
  offset >= 10 px. Over FIT (15) and s1 (6): 21 samples, every curve's minimum at 100-150 ms. The
  proposal stays 120 ms (D2); the 50-sample floor is not met.

### 13l. The PROPOSED parameters (NOT frozen) and the decisions for the parent

- `/dev/shm/poring-lab-tmp/gef10-det/params-P1-proposed.json` (sha256
  `275a8ed56b4ae7e4cc89a0d6c892a235ac947ccadde59584e617634a1a128121`), status
  `PROPOSED_NOT_FROZEN`: 1d 120 ms (P1), T_h 0.636 (`fit/threshold-P1.json`, sha256 `2f80b858…`),
  the engaged variant E2 (`fit/engaged-P1.json`), `dying_in_view`, tau 0.092, k 0.140, +-6 px, the
  RSW `b9b0e9bd…` and its 46 RSMs, labels `gef10-o3h-e`, the commit 4e40769.
- **The decisions** (section 0's D1-D8 stand; new ones from the FIT results):

| # | decision | the subagent's proposal | where |
|---|---|---|---|
| D2 | 1d = 120 ms (both FIT attempts and s1 stopped under 50 samples; every curve's minimum at 100-150 ms) | adopt P1 | 13a, 13c, 13k |
| D3 | the engaged variant: E2 as selected (14 FIT labels), or a NEW variant E4 (+-16 px for engaged units: ~10 x more on FIT) by its own amendment | E2 now; E4 as an amendment with its own T2 stratum if Batt wants the fights labelled | 13g |
| D9 | T_h: the measured 0.636 (Amendments B + C), or payf07's 0.479 | 0.636 (it costs ~11 % of the FIT whole frames against 0.479: 134 vs 150) | 13f |
| D10 | floor items: no item class from these hunts; an immune staged-items session on open ground first | adopt | 13j |
| D11 | the class list `classes-v2orc-payf07-gef10.json` (7) is NOT written: it waits for D4's tier and the item decision | -- | 7 |

- **Then, in order (section 12, with Amendment D's names):**

      W=/home/batt/docker/poring-lab; T=/dev/shm/poring-lab-tmp/gef10-det; cd $T
      # 0. after the decisions: freeze (the proposal's T_h and engaged files, the decision cited)
      python $W/scripts/map_labels.py freeze --map gef_fild10 --threshold fit/threshold-P1.json \
          --engaged fit/engaged-P1.json --decision "Amendment E (<time>): 1d = 120 ms (P1), ..." \
          --out params.json
      # 1. TRAIN: label s1 and a1..a6 (one at a time), their own C1 (3c)
      python $W/scripts/map_labels.py labels --map gef_fild10 /mnt/poring-lab-datasets/<sid> \
          --params params.json --classes $W/config/detector/classes-v2orc-payf07.json --out labels/<sid>.json
      python $W/scripts/map_labels.py check --map gef_fild10 /mnt/poring-lab-datasets/<sid> \
          --params params.json --out own-c1/<sid>.json
      # 2. T1 on TEST (the first TEST read): the watch's cells 11-14, a7, a8
      python $W/scripts/map_labels.py check --map gef_fild10 \
          /mnt/poring-lab-datasets/20261025T195325-rdp-ow1:spots=11-14 \
          /mnt/poring-lab-datasets/<a7> /mnt/poring-lab-datasets/<a8> --params params.json \
          --rows t1/rows.json --out t1/check.json
      # 3. T2: the pack (seed 31, strata N / E) from the frozen TRAIN labels, with the floor
      python $W/scripts/map_labels.py pack --map gef_fild10 labels/*.json --seed 31 \
          --min-fit <T_h> --pack-dir t2/pack --key-dir t2-key \
          --instructions $W/docs/planning/gef10-blind-instructions.txt \
          --instructions-sha256 247b79197e47f732f4d1acf04bc6ed1ba2b7162c0c9fab26fe49cb5eab4b54b0 \
          --out t2-build.json
      python $W/scripts/blind_score.py --key t2-key/answer_key.json A.json B.json --each-sample

  The labels of the FIT parts are re-made with the frozen file (the proposed ones are
  provisional). Every step runs one process at a time (`--workers 1`), niced, outside the market
  windows on a weekday.

### 13m. Where the outputs live (client-derived, never committed)

- **Kept in `/dev/shm/poring-lab-tmp/gef10-det/` (13 MB) for the parent's freeze, T1 and T2:**
  `params-P1-proposed.json`; `fit/` (every FIT output and log quoted above, the rows files, the
  superseded attempts `*-attempt*.json`, `steps.log` with the start / end of every step);
  `labels-proposed/` (the provisional FIT labels); `grf/` (gef_fild10.rsw, its 46 RSMs, the item
  name tables); `items/` (13 item sprites); `sprites-all/` (the decoded monster sprites, lab +
  pay_fild07 + gef_fild10); `kb/` (classes.json, the merged sprite-name table). A host reboot
  wipes them: the RSW / RSMs / item sprites are re-extracted with `grf_read.py extract ...
  --decode-mixcrypt` (1a's list).
- **Archived to the NAS, deleted locally (2026-10-25 ~22:05):** the scratch diagnostics and by-eye
  sheets quoted in 13b, 13d, 13g (`diag_th.py`, `diag_engaged.py`, `sheet.py`, `facts.py`, the
  runners, `archer_low.png`, `archer_high.png`, `engaged_sheet.png`, `watch_28.png`,
  `watch_291.png`, `pilot_300.png`): `/mnt/poring-lab-datasets/scratch-archive/2026-10-25/gef10-det-scratch/`
  (15 files, `checksums.sha256` verified).
- The watch recording is now read from `/mnt/poring-lab-datasets/20261025T195325-rdp-ow1` (the
  parent's 21:5x message: the local copy is deleted after its checksummed ship); the FIT label
  files store shard names and offsets only, so they resolve against the NAS root unchanged.

### 13n. The parent's DECISIONS and the FREEZE (2026-10-25 22:13 ICT from `date`; before any TRAIN label or TEST read)

Batt delegated the GPU work on this map's monsters and items (2026-10-25 ~12:3x). These
methodology choices are the parent's, made on the FIT results above and nothing else:
- **D1-D8: adopted** as section 0 proposes:
  - the watch split by cell, 0-10 FIT / 11-14 TEST;
  - D4 (< 30 kept labels: not a class this round) and D5 (a failing engaged stratum drops only
    that species' engaged labels);
  - the item classes Cyfar / Orcish Voucher / pooled `item`;
  - init payf07 epoch-1 with `scale` 0.1, and `dying_in_view`.
- **D2: 1d = 120 ms** (P1). Both FIT attempts stopped under 50 samples, and every curve's minimum
  lies at 100-150 ms.
- **D3: E2** as the pre-registered selection chose it. E4 (+-16 px for engaged units) is NOT
  adopted: it would need its own amendment and T2 stratum, and engaged boxes are a small add-on.
- **D9: T_h = 0.636**, the measured floor (Amendments B + C). payf07's 0.479 is not this map's
  number.
- **D10: no item class from the hunts this round.** Floor-item classes wait for an immune
  staged-items session on open ground (target-items.md's method). Until then, the detector trains
  on monsters only.
- **D11:** the class list is written after D4's tier, from the species that pass it.
- **TEST:** watch cells 11-14 + a7 + a8 (Amendment D). Nothing of TEST has been read.
- The freeze follows 13l's command, with this section cited as the decision.
- **FROZEN 2026-10-25 22:14 ICT:** `/dev/shm/poring-lab-tmp/gef10-det/params.json`, sha256
  `00ef6383883927e35991355f7d29597c0f918af73f65751885a53edfb1b0aac1` (`map_labels.py freeze`,
  threshold file sha256 `2f80b858a10d474a8b7e07990231cd4fa8906b32bd85701254b2a6d20b0f1395`). The
  TRAIN labels (s1, a1-a6 by 3c) follow, one session at a time.

### 13o. RESULT: the first TRAIN sessions under the frozen params (2026-10-25 22:14-22:23 ICT)

| session | frames labelled / whole | own C1 (bad / scored) | joins TRAIN (3c: >= 50 scored)? |
|---|---|---|---|
| s1 (`20261025T204315-rdp-rogue-s1`, partial: 1,384 frames) | 1,059 / 752 | 0 / 26 | no: 26 < 50 |
| a1 (`20261025T213953-rdp-rogue-a1`, death at 23.7 min) | 901 / 593 | 0 / 48 | no: 48 < 50 |

- The labels are clean where scored, but too few. A 25-40 min hunt gives under 50 standing labels.
- **The plan for data (no rule change):** IMMUNE lattice watches on gef_fild10, as 13a of
  payf07-detector.md did for Elder Willow (136 -> 409 boxes). They use 30-s dwells, `@warp` only
  and no spawn. They run in rogue-gef10.md Amendment E's gaps (no `@killmonster2`, so the Orc
  Lord's timer is untouched) and join TRAIN by 3c like any later session.

### 13p. TRAIN by 3c, the FIT labels re-made, and the T2 pack (2026-10-26 02:43 ICT from `date`)

**Joins TRAIN (own C1 <= 0.050 on >= 50 scored):**

| session | own C1 |
|---|---|
| a2 | 1 / 64 |
| a4 | 0 / 67 |
| **w2** (the immune lattice watch, 01:45-02:19) | 6 / 271 |

- **Out:** s1 (26 scored), a1 (48), a3 (25), a6 (4: it sat under a tree for 20 min). a5 is too
  short.
- **The FIT parts were re-labelled with the frozen params** (02:33-02:41): the watch's cells 0-10,
  the pilot and pilot2.
- **The T2 pack** (`map_labels.py pack`, seed 31, `--min-fit 0.636`, the instructions' sha256
  `247b7919...`): from the FIT parts + a2 + a4 + w2 only. 246 crops in 13 grids, 30 per stratum
  where the pool allows:
  - Orc Lady N 30 / E 30; Orc Warrior N 30 / E 6;
  - Poporing, Orc Baby, Orc Lord, Orc Archer and Green Plant N 30 each.
- Two NEW blind labellers (A, B) started; each sees only the pack and writes its own answers file.

### 13q. RESULT: T2 PASSES (scored 2026-10-26 02:55 ICT, `blind_score.py --each-sample`); the class list (D11) (02:55)

- **Labellers A and B** (new, blind; each saw only the pack): 246 crops each.
  - A answered 1 species "unsure" (crop 207, under a UI bar); B none.
  - Both judged every box "good".
- **N stratum** (210 crops): every species passes with BOTH labellers: good 1.00, species right
  0.967-1.00. That covers Orc Lady, Orc Warrior, Orc Baby, Orc Lord, Orc Archer, Poporing and
  Green Plant.
- **E stratum** (36 crops): Orc Lady (30) and Orc Warrior (6) pass. Their engaged labels train
  (D5).
- **D4:** Blue Plant 1079 had no kept label in the pool, so it is not a class this round.
- **D11, the class list:** `config/detector/classes-v2orc-payf07-gef10.json`, 26 classes.
  - payf07's ids 0-20 are unchanged;
  - added: 21 Orc Lady 1273, 22 Orc Warrior 1023, 23 Orc Baby 1686, 24 Orc Lord 1190, 25 Orc
    Archer 1189.
  - No item class this round (D10).
- **Next:** T1 on TEST (watch cells 11-14 + a7 + a8), once a8 is recorded and shipped.

### 13r. RESULT: T1 FAILS -- C1 5 / 61 = 8.2 % on TEST (bar <= 5.0 %); the monster tier fails, nothing of it trains (checked 2026-10-26 03:16:22 ICT, the parent)

- **The run:** `map_labels.py check --map gef_fild10` on the watch's cells 11-14 + a7 + a8, the
  FROZEN `params.json` (sha256 `00ef6383...b0aac1`), commit 1eab7c3.
  - The first and only read of TEST; `t1/check.json`, `t1/rows.json`.
- **C1 pooled: 5 bad of 61 scored = 0.082 > 0.050: T1 FAILS.** C2: no STOP (Poporing PASS, n 38;
  the other species NO_VERDICT, < 20 standing labels).

| TEST part | frames | candidates | scored | bad | C1 |
|---|---|---|---|---|---|
| watch cells 11-14 | 835 | 172 | 4 | 0 | 0.0 % |
| a7 | 1,374 | 1,171 | 35 | 5 | 14.3 % |
| a8 | 2,081 | 1,538 | 22 | 0 | 0.0 % |
| **pooled** | | | **61** | **5** | **8.2 %** |

| species | scored | bad |
|---|---|---|
| Poporing 1031 | 38 | 3 |
| Orc Lady 1273 | 14 | 0 |
| Orc Warrior 1023 | 6 | 2 |
| Orc Baby 1686 | 3 | 0 |

- **The five bad labels are TWO sightings in a7** (a report, read after the fail; it changes no
  rule of this round):
  1. **Orc Warrior gid 110020901, frames 505 / 510** (507-509 scored just above tau): its box (top
     at y 28) lies under the client's transient **"... - 1 obtained."** pickup notice (x 541-799,
     y 77-104). The sprite is drawn there; the notice covers it. The UI rule knows the static
     windows only, so the label was scored as visible.
  2. **Poporing gid 110020984, frames 548-550:** no match anywhere within +-16 px (best NCC 0.198
     at dx 12, dy -14). The box lies on a palm's leaf edge beside the raised rock face east of
     the orc village. A Poporing IS drawn about 120 px higher, on the rock top (its identity is
     not verified). A height or occlusion case the rule does not cover.
- **The consequence (section 9):**
  - The monster tier fails. NOTHING of gef_fild10 trains this round: no cache, no GPU run.
  - The pre-registered evaluation (`docs/benchmarks/gef10-eval.md`) has no model to score.
  - Not re-run under the same bars (section 0).
  - The T2 PASS (13q) and the class list stand as records.
- **MEASURED since (03:21-03:46, offline, FIT / TRAIN only):** [gef10-round2-measure.md](gef10-round2-measure.md). The notice rule is validated (587 / 595, 0 / 8,156 false) and removes NO kept TRAIN label: the masked-NCC fit already drops labels under it, so the hole is in C1, which scores the unfitted prediction. The raised-terrain rule below is NOT supported: 11.0 % of the written labels lost (all Green Plant), with no worse fit.
- **What a next round would need (PROPOSED when written, 03:19; read it with the measurement above):**
  - a rule for the transient pickup notice (and the other popups) over a label: pixel-detected
    and excluded like `ui_or_edge`;
  - a rule for labels on or beside raised terrain (cliff faces): measured on FIT;
  - a NEW TEST never read before it (e.g. tonight's a9-a12);
  - T2 again for the changed rule, two new labellers.
- **The live hunting detector is unchanged** (v1 on the CPU). The scored A/B block does not use a
  detector of this map.

### 13s. PRE-REGISTERED: ROUND 2 (the parent, 2026-10-26 11:07 ICT from `date`; BEFORE TEST2 is read and BEFORE w3 is recorded)

**R2-0. The basis:**
- Batt ~09:4x (rogue-gef10.md Amendment L, decision 3): "YOLO round 2: go; if it is not
  accurate, you may train YOLO on the monsters". His play is the minimum bar.
- **The live detector (v1) is not accurate on gef_fild10**
  ([gef10-round2.md](gef10-round2.md), on Batt's demo, packet truth):
  - recall 8.0 %: Orc Lady 1.4 %, Orc Warrior 8.8 %, Poporing 52.5 %;
  - at 0-5 cells, 2.4 %;
  - precision 18.7 %: 77.7 % of its boxes sit on scenery;
  - in 64 % of the frames with a monster in view, it drew no monster box at all.

**R2-1. Unchanged and frozen:**
- the label rule gef10-o3h-e and `params.json` (sha256 `00ef6383...b0aac1`);
- FIT (watch cells 0-10, pilot, pilot2) and TRAIN (a2, a4, w2), their label files;
- T2's seed-31 pack and its PASS (13q);
- the class list (26 classes, sha256 `66de5684...a7ff747c2`).
- No other session joins TRAIN before the cache.

**R2-2. Changed: C1 only.**
- `map_labels.py check --c1-rule round2`, at commit 8261acf.
- Round 1's C1, plus the pickup-notice exclusion: a predicted box overlapping a notice that
  `gef10_r2_measure.find_notices` finds (any area) is excluded as `notice`.
- The notice detector is validated at 587 / 595 positives and 0 / 8,156 false.
- On FIT / TRAIN the rule excludes 0 of 527 rows (C1 8 / 527 before and after), and round 1
  reproduces byte for byte.

**R2-3. TEST2** (whole sessions; never read before this commit, the parent attests; refused by
name by `labels` / `pack` / the cache):
- a9 `20261026T044312-rdp-rogue-a9`, a10 `20261026T052148-rdp-rogue-a10`, a11
  `20261026T055949-rdp-rogue-a11`;
- **w3**: an IMMUNE lattice watch on gef_fild10 recorded AFTER this commit, as w2 was.
  - `gef10-ow/w2.sh w3 41 33`: seed 41, 30-s dwells, @warp only, no spawn, no
    `@killmonster2`, 33 min, a 1-fps recorder.
  - Its name (`-rdp-w3`) is refused from this commit on.
  - It is added because hunting runs give 22-67 scored rows each. At ~60 rows, a rule as good as
    TRAIN's fails T1 about 8 % of the time (gef10-round2.md, the brittleness note). w2 gave 271.
- A session that fails `check_recording` is dropped and reported, never replaced.

**R2-4. T1 on TEST2, read ONCE, under round2:**
- C1 pooled over the gef_fild10 species <= 0.050, unrounded (the bar unchanged);
- **a verdict needs >= 100 scored rows** (fewer: NO VERDICT, not a fail);
- C2 unchanged: a FAIL is a STOP;
- reported: C1 per species and per session, the exclusions including `notice`, and the C1 per
  SIGHTING beside the row C1 (not gating).

**R2-5. T2 is NOT re-run.** The notice rule lives in `check` only. `labels`, the label files and
`pack` do not use it, so the seed-31 pack is unchanged by construction: 0 of 2,413 kept TRAIN
labels overlap a notice.

**R2-6. If T1 passes with no C2 STOP:** the cache and training exactly as recorded:
- `build_frame_cache.py --labels map` on the TRAIN label files, linked to
  `v2orc-payf07-20261024`; a dry run first (the 02:5x dry run: 2,232 gef10 frames);
- YOLO11n, seed 20261004, imgsz 1280, batch 2, workers 1;
- init from payf07's epoch-1 `last.pt`;
- hsv_s 0.2, scale 0.1, 10 epochs, close_mosaic 3;
- WORKER=1, MID_CKPT=1, R1-R3, the IO guard, the 25 % VRAM cap;
- outside 09:30-10:15 and 14:00-14:45 on weekdays.

**R2-7. The evaluation:** gef10-eval.md's method on TEST2, with seed 35 (its amendment, same
commit).

**R2-8. If T1 fails or gives NO VERDICT,** nothing trains; it is reported, never re-run under
the same bars, and Batt decides.

### 13t. RESULT: round 2's T1 PASSES on TEST2 -- C1 3 / 159 = 1.9 % (bar 5 %, >= 100 rows), no C2 STOP (checked 2026-10-26 12:06:45 ICT; recorded 12:08)

- **The run:** `map_labels.py check --map gef_fild10 --c1-rule round2` on a9, a10, a11 (NAS) and
  w3 (`20261026T112924-rdp-w3`, in /dev/shm until 17:00), the FROZEN params (sha256
  `00ef6383...b0aac1`, verified), commit 6a218c7. The first and only read of TEST2;
  `t1r2/check.json` and `rows.json`.
- **w3:** the watch ran its 33 min (11:29:26-12:02:52, 200 planned cells). Its recorder stopped
  after 280 frames on the IO guard (quant-postgres 31.4 % at SET hours). It passed
  `check_recording` and stayed in TEST2 as registered (never replaced).

| TEST2 part | frames | scored | bad | C1 |
|---|---|---|---|---|
| a9 | 2,106 | 35 | 2 | 5.7 % |
| a10 | 1,301 | 62 | 1 | 1.6 % |
| a11 | 1,835 | 12 | 0 | 0 % |
| w3 | 280 | 50 | 0 | 0 % |
| **pooled** | | **159** | **3** | **1.9 %: PASS** |

- **Per species:** Orc Lady 3 / 95, Poporing 0 / 48, Orc Warrior 0 / 16.
- **C2:** Orc Lady PASS (median |dx|, |dy| 1, 1), Poporing PASS (0.5, 1), Orc Warrior NO_VERDICT
  (16 < 20). No STOP.
- **The notice rule:** 16 frames had a notice, and it excluded 0 scored rows.
- **Reported, not gating:** C1 per SIGHTING 2 / 31 = 6.5 %. The 3 bad rows are two Orc Lady
  sightings: a9 gid 110023774 (two frames) and a10 gid 110023727.
- **Next (R2-6):** the cache with the dry-run arguments of 02:5x. That dry run returned rc 0 with
  2,232 gef_fild10 frames; the nested link `v2orc-payf07-20261024` resolves (20 sessions, 22,546
  frames, 31 shards); combined TRAIN 19,025 frames; no 3c refusal. It is built through
  `guarded_build.py cache@6300=`, capped to end before 14:00. Then the training as recorded.

### 13u. THE TRAINING SETTINGS, recorded BEFORE the launch (2026-10-26 12:13 ICT from `date`; gef10-eval.md "as recorded in gef10-detector.md BEFORE the launch")

- **Cache:** `v2orc-payf07-gef10-20261026`, being built now (13t).
- **Init weights:** payf07's epoch-1 `last.pt`,
  `/mnt/poring-lab-datasets/archive/train/payf07-20261024/weights/last.pt` (in the container
  `/datasets/archive/train/payf07-20261024/weights/last.pt`), sha256 `b2c2912017ea74ffb354621f2cac263d785eb3f29dcb5ec09725c6003f9ef767`.
- **Settings (section 10, unchanged):**
  - YOLO11n, seed 20261004, imgsz 1280, batch 2, workers 1;
  - **10 epochs**, `close_mosaic` 3, `hsv_s` 0.2, **`scale` 0.1**;
  - WORKER=1 (the long-lived worker, up since 2026-10-24 19:53 UTC), MID_CKPT=1;
  - R1-R3 and the adaptive duty cycle, the IO guard, the 25 % VRAM cap.
- **R2 at launch:** Ollama's `/api/ps` showed no model at 12:1x; the guard re-checks it before
  the start.
- **The launch (after the cache, outside 09:30-10:15 / 14:00-14:45):**

      WORKER=1 MID_CKPT=1 INIT_WEIGHTS=/datasets/archive/train/payf07-20261024/weights/last.pt \
        HSV_S=0.2 CLOSE_MOSAIC=3 SCALE=0.1 scripts/runbooks/train-day.sh gef10-20261026 \
        v2orc-payf07-gef10-20261026 10 /dev/shm/poring-lab-tmp/train-gef10 2 1

- **The scored checkpoint (gef10-eval.md):** `last.pt` after the last COMPLETED epoch.
- **Time:** ~(16,793 + 2,232) x 0.193 s ~ 1.0 h of training per epoch, about 10 h of running,
  but the duty cycle slows it under Frigate's load. payf07's single epoch took about 10 h of
  wall time.

### 13v. The cache build ABORTED on the IO guard (2026-10-26 12:16 ICT; recorded 12:16)

- `guarded_build.py cache@6300=`, the 13t arguments, started 12:10. The ow1 label file was
  copied to a name the guard's argument check accepts (`...-rdp-ow1-spots0-10.json`); its sha256
  is unchanged (`30030cc7...`).
- **[12:16:00] ABORT cache: frigate full IO stall 35.6 % (spike above 25 %).** STOP VERIFIED
  after 1 s: nothing of ours is left on the host or the GPU. No cache was written to completion.
- **The standing rule (memory, 2026-10-02):** after ONE abort, stop and ask. **Not retried.**
  Batt is asked whether to retry once after the SET session closes (17:05). Two recorders were
  also cut short by quant-postgres IO spikes during SET hours today (b1 at 9 min, w3 at 5 min).
- Training (13u) waits for the cache.

### 13w. The 20:05 retry REFUSED before any work; it resumes after c11 (2026-10-26 20:06 ICT from `date`)

- **[20:05:09] `cache: FAILED rc=1`.** The guard saw 0.0 % capture stall and 0 s above 10 %.
  - The cause: `/mnt/poring-lab-datasets/.framecache/v2orc-payf07-gef10-20261026 exists: pick
    another --cache-id (or --resume it)`.
  - The 12:10-12:16 build (13v) left `progress.json` and six shards (~2.5 GB). Nothing was read
    or written at 20:05.
- **The retry Batt approved (once, after 20:00) therefore has not run yet.** Its proper form is
  `--resume` with the SAME arguments (`cache-args-r2.txt`). The tool:
  - refuses different arguments;
  - checks each recorded shard's size on the NAS;
  - drops an incomplete session's shards.
  This is the path built for a cache the IO guard paused (Batt, 2026-10-06).
- **It starts the moment run c11 ends (~20:40).** c9 and c10 ran without the build's CPU load, so
  starting during c11 would have loaded one arm of the c9-c11 comparison alone.
- **Unchanged:**
  - the IO guard (`--sustain 30 --spike 25`); one abort means stop and ask Batt;
  - then the R2 check (Ollama `/api/ps`) and 13u's launch.

### 13x. The resume ABORTED on the IO guard; STOPPED, Batt asked (2026-10-26 20:51 ICT from `date`)

- **[20:47:02] `ABORT cache: quant-postgres full IO stall 26.9 % (spike above 25.0 %)`.**
  - STOP VERIFIED after 1 s: the container is gone, and nothing of ours is on the GPU or the host.
  - The resume had started at 20:39:19 and had passed its argument and shard checks.
- **This is the second abort of this cache** (12:16, 13v; 20:47). Batt approved ONE retry after
  20:00. **Nothing is retried.** Batt is asked (the standing rule).
- **Evidence that the spikes are the host's own, not this job's.** Today's 1-fps hunt recorders
  write only to RAM (/dev/shm). 10 of 11 were stopped by the same one-spike rule, with nothing
  heavy of ours running:

| recorder | frames | stop |
|---|---|---|
| b1 | 527 | quant-postgres 26.4 % |
| c1 | 560 | frigate 29.3 % |
| c3 | 345 | quant-postgres 29.8 % |
| c4 | 199 | quant-postgres 26.3 % |
| c5b | 891 | quant-postgres 27.0 % |
| c6 | 1,430 | local cap (12 GB unshipped), not the guard |
| c7 | 125 | quant-orderbook-engine 31.5 % |
| c8 | 412 | quant-postgres 26.4 % |
| c9 | 7 | quant-postgres 33.2 % |
| c10 | 9 | cron.service(capture-streaming-pro) 30.2 % |
| c11 | 141 | quant-postgres 31.2 % |

- **What it means.** Under "abort above 25 % once", a job of several hours will trip whatever it
  does. Separately, most of today's hunt recordings were cut short: round 3 loses those frames.
- **Options for Batt** (none taken):
  - (a) an AUTO-RESUME policy for this cache: after a trip, wait 10 quiet minutes and `--resume`,
    at most N times. The tool is built for it;
  - (b) a night window, if quant's spikes are rarer then (not measured yet);
  - (c) a higher spike limit for jobs whose own disk IO is small.
  - The recorders' guard is the same question.
  - ➡️ **SUPERSEDED: Batt chose (a) on 2026-10-26 ~20:5x** (rogue-gef10.md Amendment AC). Its quiet
    gate never found a window all night (21:13-05:13; longest gap 5.7 min). Then, on 2026-10-28,
    Batt approved running now on the grounds that our IO is small. The cache was DONE at 12:59
    (13y).

### 13y. The cache is DONE under a sustained-only IO rule (Batt 2026-10-28; recorded 2026-10-28 13:01 ICT from `date`)

- **Batt, 2026-10-28 ~12:5x** (quant-postgres is running a long job): *"see whether we can do it
  now, since we write little anyway"*.
- **What the job touches.** Only the last train session (`20261026T014529-rdp-w2`, 24 of 25 done
  before) was left.
  - It reads its PNG shards from the NAS (NFS) and writes tar shards straight to the NAS.
  - Labels, KB and params come from /dev/shm.
  - Nothing is written to the root disk (`build_frame_cache.py` docstring).
- **The probe** (scratch `io_probe.py`, 1-s samples), measuring three things:
  - each capture cgroup's full stall;
  - the root disk dm-0's read/write MB/s;
  - the builder's open-for-write files outside /mnt and /dev. A watcher would have SIGINTed the
    builder on the first such file.
- **The guard rule:** `--threshold 30 --sustain 30`, with no spike rule. It stops on 30 s of
  sustained stall above 30 %; the host's own 1-5 s bursts do not trip it.
  - In the 3 minutes before, with nothing of ours running, the 1-s samples showed 13 cgroup-seconds
    above 25 % (summed over the cgroups): quant-postgres max 60.0 %, cron capture 56.0 %, orderbook 42.8 %, ticker 49.0 %.
- **Result:** `[12:59:45] ALL STEPS OK (worst capture stall so far 22.7% on quant-postgres, 0s above
  30.0%)`.
  - It ran 12:56:19-12:59:45 (203.7 s). w2 kept 774 frames in 4 shards.
  - The cache now has 25 sessions and 24,778 frames (`progress.json`).
- **Before vs during (1-s samples):**

| window | dm-0 write MB/s mean / p95 | dm-0 read MB/s mean | quant-postgres stall mean / max | cgroup-seconds > 25 % (summed) | builder files open for write on local disk |
|---|---|---|---|---|---|
| OFF 12:52:21-12:55:46 | 1.09 / 1.97 | 2.82 | 4.5 / 60.0 | 13 | - |
| ON 12:56:20-12:59:45 | 1.33 / 3.65 | 0.34 | 5.3 / 64.5 | 4 | 0 of 182 samples |

  - No sign that the job raised the capture stall.
  - The write sensor sees the event it guards against: a positive case at 13:0x (a process
    holding a file open for write under `data/`) was flagged, and a /dev/shm file was not.
  - The guard's figure (22.7 %) is a 10-s window rate; the probe's are 1-s samples. So the probe's
    maxima run higher.
- **The old rule (`--spike 25` on the guard's 10-s windows) would not have tripped in these
  3.5 minutes either** (worst 22.7 %). That is luck of a quiet midday, not a property of the rule.
- **The training (13u) follows at once, under the same IO rule: 13z.**

### 13z. PRE-REGISTERED: the training launch (recorded 2026-10-28 13:01 ICT from `date`, BEFORE the launch)

- **The settings are 13u's, unchanged:**
  - the cache `v2orc-payf07-gef10-20261026` (13y);
  - init from payf07's `last.pt` (sha256 re-checked at 13:0x: `b2c29120...`, matches);
  - YOLO11n, seed 20261004, imgsz 1280, batch 2, workers 1;
  - 10 epochs, close_mosaic 3, hsv_s 0.2, scale 0.1;
  - WORKER=1, MID_CKPT=1, R1-R3 with the adaptive duty cycle, and the 25 % VRAM cap;
  - the scored checkpoint is `last.pt` after the last COMPLETED epoch (gef10-eval.md).
- **Changed: the IO rule only (Batt 2026-10-28, 13y).**
  - `IO_GUARD="--threshold 30 --sustain 30"` (new knob in train-day.sh, default unchanged).
  - `IO_RESUMES=20 IO_QUIET_MIN=0`: after an IO trip (now meaning 30 s of sustained stall), pause
    15 min, then `--resume`.
  - Option (a)'s measured-quiet gate is NOT used: its 25 %-per-second rule found no 10-minute
    window all night (13x).
- **What training writes locally:** checkpoints and logs under the worker's `/data/train/<run>`
  (`data/`, the root disk) -- `mid.pt` every ~5 min and `last.pt` each epoch, a few MB each for
  YOLO11n. It reads its shards from the NAS. The probe keeps logging dm-0 and the stalls until
  13:52.
- **Preconditions at launch:**
  - the vision worker is up since 2026-10-24 19:53 UTC (no cold start);
  - Ollama `/api/ps` shows no model (R2);
  - outside 09:30-10:15 / 14:00-14:45. A run in progress continues through 14:00; the runbook
    only refuses new starts and resumes inside a window.
- **VRAM at launch:** 9,924 MiB of 16,311 MiB in use before ours.
  - fit-first's `fitfirst_vton_worker.session` holds 6,376 MiB; Frigate's detectors and ffmpeg hold
    the rest.
  - R1 (Ollama + vision <= 9 GiB) holds: 0 + at most the 25 % cap.
  - Expected total ~12.4 GiB (ours peaked at 2,510 MiB in v0).
  - Infra observation only: fit-first's share is not covered by R1.
- **The launch:**

      WORKER=1 MID_CKPT=1 INIT_WEIGHTS=/datasets/archive/train/payf07-20261024/weights/last.pt \
        HSV_S=0.2 CLOSE_MOSAIC=3 SCALE=0.1 IO_GUARD="--threshold 30 --sustain 30" \
        IO_RESUMES=20 IO_QUIET_MIN=0 scripts/runbooks/train-day.sh gef10-20261026 \
        v2orc-payf07-gef10-20261026 10 /dev/shm/poring-lab-tmp/train-gef10 2 1

- **[13:02:08] attempt 0 REFUSED before any work:** `R2: another job of ours is on the GPU
  (/work/venv-diag-headless/bin/python (6376 MiB))`.
  - That process is fit-first's `fitfirst_vton_worker.session`, started 12:29:22 today.
  - R2's check (`frigate_r3.prestart`) refuses ANY non-Frigate GPU job, fail closed. It is
    not overridden.
  - The runbook pauses 900 s and retries (an R2 trip counts toward IO_RESUMES 20). So it starts
    by itself once the GPU is free, outside 14:00-14:45. Batt is told.

### 13z-1. AMENDMENT before attempt 2: the R2 CO-TENANT exception (Batt 2026-10-28 ~13:2x; recorded 2026-10-28 13:41 ICT from `date`)

- **Batt:** fit-first's VTON work is the TOP priority right now. Never touch it or stop it. Running
  beside it IS allowed.
- **The runbook was stopped by hand at 13:23:16**, while idle in its 900-s pause after attempt 1's
  refusal (13:17:09). This kept a half-edited check from being picked up. Nothing of ours was on
  the GPU.
- **What changed** (`frigate_r3.py`; `guarded_build.py` vision steps only; vlm_flag keeps plain R2):
  - **`CO_TENANTS = (b"fitfirst_vton_worker.session",)`**, matched by COMMAND LINE in
    `/proc/<pid>/cmdline`. nvidia-smi names it only `/work/venv-diag-headless/bin/python`.
  - **The start:** free VRAM >= our cap (25 % of the total = 4,077 MiB) + 1,024 MiB headroom,
    else REFUSED as R2. If nvidia-smi is unreadable, refuse (fail closed). Any other python job
    on the GPU is still refused.
  - **In the run, `CoTenantWatch`:**
    - It reads the free VRAM every 10 s. Below 1,024 MiB with a co-tenant present, our step stops:
      `ABORT ...: R2 co-tenant ...`, verified stop. train-day pauses 15 min and `--resume`s from
      `mid.pt`. Our share of the VRAM goes back to the co-tenant.
    - An `nvidia-smi pmon -s u -d 1` reader marks the co-tenant as computing when its sm column is
      not "-". While it computes, and for 30 s after, the duty file asks for **10,000 ms** per step
      (train.py's own maximum). With batch 2 at ~0.39 s, our share of the GPU then falls to ~4 %.
      After that the duty cycle's own level returns.
- **Checks:**
  - frigate_r3 / guarded_build / train_day tests: 139 passed (new: command-line matching,
    headroom, fail-closed reads, pmon rows from the real idle VTON, the yield and its end, the
    VRAM-trip ABORT); test_guards + vlm_flag green.
  - **Live, read-only:** the co-tenant-rule prestart said go (plain R2 still refused). The VTON
    worker was idle in pmon (sm "-", 6,376 MiB). memory (9,924, 16,311) MiB.
  - **Positive case, live:** the watch pointed at Frigate's always-computing detectors (a
    stand-in signature; nothing touched) saw 7 busy samples in 6 s and yielded. The pmon
    subprocess was stopped afterwards.
- **Not changed:** 13u's training settings, the IO rule (13z), R1, R3 and the duty cycle.

### 13z-2. Training progress and the first live co-tenant yield (recorded 2026-10-28 16:10 ICT from `date`)

- **Epoch 1** ended ~15:15 (`results.csv` time 5,415 s, training + validation). Its validation
  (mAP50 0.796, mAP50-95 0.569) is PROGRESS only; the verdict is gef10-eval.md's, on `last.pt`
  after the last completed epoch, as pre-registered.
- **Epoch 2** ran faster (~2.4 batches/s, 77 % at 52 min), with Frigate's fleet load low.
- **16:06:40, the first LIVE yield:** fit-first restarted its VTON worker at 16:05:34 (new pid
  1365657; nothing of ours touched it). The watch matched it by command line, saw it compute and
  set the 10 s step sleep ("DUTY a co-tenant computes: YIELDING"). That is the 13z-1 mechanism's
  live positive case on the real co-tenant.
- **The 12-h step limit** (`execdev:vision@43200`, PER ATTEMPT: each resume is a new guarded step
  with a fresh 12 h; ➡️ after the 16:07 abort below, the resumed attempt's limit is ~12 h after its
  start, ~04:2x on 10-29, not ~01:41; ➡️➡️ SUPERSEDED by 13z-3: nine attempts by 10-29 05:11, and
  the running attempt 9's limit is ~17:11 on 10-29) would have fallen at ~01:41 on 10-29 for
  attempt 0. The guard then prints `FAILED rc=124`, not an ABORT, and train-day ends "TRAIN
  STOPPED: not a guard trip" (exit 2). No automatic resume: `RESUME=1` with the same arguments, by
  hand or by Batt's decision (➡️ Batt 2026-10-29 ~09:5x, "continue training": the parent resumes
  it by hand on that stop, 13z-3). `mid.pt` bounds the loss to ~7 min.
- **Our disk footprint, measured** (the 2-h probe 13:45-15:45, NAS
  `scratch-archive/2026-10-28/train-gef10-io/`): `mid.pt` (42 MB, every ~7 min) and the epoch's
  `last.pt` / `best.pt` go to the root disk (`data/train`). After each mid write (15:37:02,
  15:43:49), quant-postgres stall rose to 42-50 % for 1-2 s. That is inside the sustained rule,
  and an infra suggestion (tmpfs for `mid.pt`), not a change. The probe's largest bursts (520 MB/s
  at 15:27:35, 445 MB/s at 15:39:27) are not ours.
- **16:07:28, an R3-HARD abort** (recorded 16:14 ICT from `date`): camera cam-1-02-font-n dropped
  frames for 30 s. At that moment the detectors were at 217.4 ms, five cameras were skipping
  (cam-1-01-font-s, -02-font-n, -08-side-s, -09-font-room-s, -10-living-room), and the fleet load
  was 14.2 detections/s.
  - What else was on the GPU: fit-first's VTON had restarted at 16:05:34 and was computing.
  - Ours had been yielding since 16:06:40 (one step per ~10 s).
  - The stop was verified (our python gone from the GPU). train-day then waits for 15 quiet
    minutes (16:07:37 on) and resumes at the slowest level, walking back up; 1 abort in 2 h.
  - By 16:13 Frigate was back to inference ~28-30 ms, 29-35 detections/s, no camera skipping,
    VTON idle.
  - Attribution: not settled. Our share of the GPU was near zero in the drop window. The VTON's
    start is the likelier cause; it is the top priority and is never touched.

### 13z-3. The night 10-28/29: attempts 2-9, epochs 2-7, and Batt's go-ahead (recorded 2026-10-29 09:52 ICT from `date`)

- **State at 09:52:** attempt 9 has run since 05:11:30 without a trip. Epoch 7 ended at 09:18
  (`results.csv`), so epoch 8 of 10 is running. `mid.pt` was written at 09:48.
- **Attempts since 13z-2** (train.log; every stop was verified by the guard, and train-day resumed
  by itself each time):

  | attempt | start (ICT) | end (ICT) | stop | train-day's path |
  |---|---|---|---|---|
  | 1 | 10-28 16:32:39 | 17:09:12 | IO: quant-postgres 58.7 % for 31 s | 900-s pause (IO trip 1 of 20) |
  | 2 | 17:24:23 | 19:06:53 | IO: quant-ticker-engine 52.1 % for 31 s | 900-s pause (IO trip 2) |
  | 3 | 19:22:01 | 20:19:38 | R3-HARD: cam-1-02-font-n drops 31 s; fleet 57.4 det/s, detectors 35.0 ms | 15 quiet min, slowest level (1 abort in 2 h) |
  | 4 | 20:34:47 | 20:50:30 | R3-HARD: cam-1-01-font-s drops 32 s; fleet 39.7 det/s, 30.4 ms; 3 cameras skipping | 15 quiet min (2 aborts in 2 h, no cap) |
  | 5 | 21:05:41 | 10-29 02:00:44 | R3-HARD: cam-1-02-font-n drops 32 s; fleet 1.4 det/s, 24.6 ms; 6+ cameras skipping | 15 quiet min (1 in 2 h) |
  | 6 | 02:15:57 | 04:04:27 | R3-HARD: cam-1-07-font-room-n, camera_fps 0.0 and skipped 0.0 for 32 s; fleet 16.2 det/s, 26.7 ms; "skipping now: none" | 15 quiet min (1 in 2 h) |
  | 7 | 04:19:36 | 04:40:38 | IO: quant-postgres 34.8 % for 31 s | 900-s pause (IO trip 3) |
  | 8 | 04:55:43 | 04:56:27 | IO: quant-postgres 47.9 % for 30 s (40 s into the attempt, at 2,000 ms) | 900-s pause (IO trip 4) |
  | 9 | 05:11:30 | running | -- | step limit ~17:11 on 10-29 |

  - The rule of 3 frame-drop aborts in 2 h never fired, so there was no cap and no NOTIFY. IO
    trips used: 4 of 20.
  - **Two of the R3-HARD stops look camera-side, not load** (infra observation; the stop stays
    absolute). At 02:00:44 the fleet load was 1.4 det/s and the detectors 24.6 ms, with six or more
    cameras skipping at once, while ours had held the slowest level (2,000 ms) for most of
    attempt 5 (14,327 s). At 04:04:27 cam-1-07-font-room-n's camera_fps was 0.0, which is a
    stalled stream, not skipped frames. Read-only at 09:5x: all 16 cameras show skipped_fps 0.0,
    cam-1-07 at 2.0 fps, detectors 27-30 ms.
- **Validation per epoch (PROGRESS only; the verdict is gef10-eval.md's on `last.pt` after the last
  completed epoch):**

  | epoch | mAP50 | mAP50-95 | precision | recall |
  |---|---|---|---|---|
  | 1 | 0.796 | 0.569 | 0.843 | 0.805 |
  | 2 | 0.809 | 0.589 | 0.833 | 0.823 |
  | 3 | 0.815 | 0.614 | 0.883 | 0.830 |
  | 4 | 0.823 | 0.612 | 0.886 | 0.837 |
  | 5 | 0.816 | 0.625 | 0.870 | 0.838 |
  | 6 | 0.827 | 0.625 | 0.882 | 0.834 |
  | 7 | 0.826 | 0.630 | 0.868 | 0.844 |

  Epochs 8-10 are the close_mosaic epochs (CLOSE_MOSAIC=3).
- **Speed:** epoch 7 took 72.5 min in attempt 9 (`results.csv` time 10,289 -> 14,640.9 s), mostly
  at the 100 ms level overnight. At that pace epochs 8-10 end ~13:00-14:00 today if nothing trips.
  Daytime Frigate load and VTON yields can slow it; the step limit at ~17:11 is the backstop.
- **Batt, 2026-10-29 ~09:5x: "เทรนต่อได้เลย" ("go ahead, continue the training").** The parent
  reads this as the answer to the open question on the step limit: if attempt 9 ends `FAILED
  rc=124` / "TRAIN STOPPED: not a guard trip", the parent resumes it ONCE by hand with `RESUME=1`
  and the 13z launch's arguments, outside 09:30-10:15 / 14:00-14:45. Any other "TRAIN STOPPED"
  (an unverified stop, the worker not ready) is still a stop for a person to look at. No setting
  changes.

### 13z-4. Epoch 8, and attempt 9 ended by an OOM kill that OUR scratch script caused (recorded 2026-10-29 10:50 ICT from `date`)

- **Epoch 8** ended at ~10:27 (`results.csv`: mAP50 0.827, mAP50-95 0.627; PROGRESS only),
  68.7 min in attempt 9.
- **10:35:36, the kernel OOM killer killed our training process** (PID 2201841 in
  poring-lab-vision-worker-1, oom_score_adj 500: the designed victim). The guard logged it at
  10:35:39 as `R3 frigate_unreachable: no fresh Frigate stats for 81 s`: Frigate was itself in D
  state in the storm. train-day treated it as a trip and pauses 900 s (resume ~10:53 from
  `mid.pt`, written ~10:3x).
- **The cause was ours: a scratch analysis for E3's icon fix** (`icon_study.py`, nice 10, started
  ~10:30). It kept every 16x14 icon crop as a numpy VIEW into a fresh 1280x720 float32 frame
  (~3.7 MB each), so it held ~24 GB. The host went to swap full (30.6 of 30.7 GB), IO full stall
  ~53 % (avg300), 64 tasks in D state. It was killed by PID at 10:42:07; by 10:43 IO full stall
  was ~1.5 % and ~29 GB RAM available. A peer session (candy-closet) flagged it first.
- **fit-first's VTON worker container (`fitfirst-vton-worker`) exited 137 at 10:38:20**
  (SIGKILL; Docker's OOMKilled=false; the kernel's only OOM kill today was ours; its last log line
  `claims blocked: watchdog_missing`). Not stopped by this session. It happened inside the memory
  crisis we caused. It is NOT restarted by us (Batt 2026-10-28: never touch it); Batt was told at
  once.
- **The rule taken from it:** scratch analysis runs under a memory cap with no swap
  (`systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0`), copies small crops out of big
  frames, and does not read large /dev/shm data in the day while it may sit in swap (reading
  swapped tmpfs pages is root-disk IO).
