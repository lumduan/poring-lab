---
doc_type: design
hypothesis: "Packet labels with payf07's o3h-all rule (fix 2 facing, 2b / 2c, the fit, o3h, the T_h floor on every label), re-measured on gef_fild10's own FIT data, PLUS a rule that LABELS monsters engaged in a fight with our character (drawn facing it, in the action the packets give), give per-species monster boxes for gef_fild10 (Orc Lady, Orc Warrior, Orc Baby, Poporing, Orc Lord, Orc Archer, the plants) that pass the training tier (T1: C1 <= 5 % on held-out TEST data; T2: every species in the tier passes a blind check, the engaged labels in their own stratum), and floor-item boxes from the items' own client sprites that pass their own geometric and blind checks, so ONE detector can be trained on payf07's 21 classes plus this map's monsters and items."
status: "PROPOSED 2026-10-25 (a subagent, offline). Nothing frozen, nothing trained. The parent freezes the parameters (or amends them) and decides sections 0's open items BEFORE any TEST frame is read."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [payf07-detector.md, orcsdun01-detector.md, labels-v2-plan.md, training-cost.md, target-items.md, item-class.md, rogue-gef10.md, gef10-prep.md, ../benchmarks/payf07-eval.md]
next_action: "The parent: read section 0 (the decisions), then section 12's order of work: s1-s6 labelled and joined by 3c, the parameters frozen, T1 on TEST, T2 (two new labellers), then the cache and the evaluation pre-registration before any GPU step."
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
