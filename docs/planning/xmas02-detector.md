---
doc_type: design
hypothesis: "Packet labels with gef_fild10's rule (o3h with the fit floor on every label, Amendments B and C, the pickup-notice rule in C1), re-measured on xmas_dun02's own FIT data and extended by a TERRAIN occluder candidate (the map's raised GAT blocks, adopted only by a FIT test fixed here), give per-species boxes for the four common species (Myst Case, Cruiser, Cookie, Christmas Cookie) that pass the training tier (T1: C1 <= 5 % on >= 100 held-out standing rows; T2: every tier species passes a blind check), so that a detector scoped to xmas_dun02, trained on immune lattice watches, sees those species on held-out data (Q1 collapsed: recall and precision >= 0.80 per species) and boxes the runner's own patrol frames with precision >= 0.80, where v1 saw 1 of 937 labels."
status: "RECORDING under Amendment D (Batt 2026-11-06 ~14:0x: daytime recording with the sustained-only IO rule + an automatic resume; xw1 attempt 1 was cut at 5.5 min by a one-spike trip, section 12). ACCEPTED 2026-11-06 ~10:45 by Batt ('go ahead, training may start, start the plan now'), recorded as Amendment A (section 13) before any recording: D0 answered by a 100 GB recorder floor, D1-D14 adopted as proposed; T-5 needs no new driver (stage_items.py watch + record_session.py), the lattice by watch_lattice.py (343 TRAIN-side + 88 TEST stands). Was: PROPOSED 2026-11-06 (pre-registration draft, written offline by a subagent)."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [rogue-xmas02.md, xmas02-prep.md, gef10-detector.md, ../benchmarks/gef10-eval.md, payf07-detector.md, orcsdun01-detector.md, training-cost.md, gef10-round2-measure.md, ../../scripts/map_labels.py, ../../scripts/warp_watch.py, ../../scripts/detector_vs_packets.py, ../../scripts/recorder_boxes.py]
next_action: "Record the xw1 continuation (Amendment D's commands, from 14:45), then xw2 (and xw3 if the caps allow) before 17:00; from 17:00 ship each session (verified, deleted), then xw3-xw5 and xp1 each shipped before the next; then FIT (section 11 step 5). The tool gaps T-1-T-10 are built (Amendments B, C)."
title: "A detector for xmas_dun02's monsters: the facts, the data plan, the split, the label rule (terrain candidate), T1 / T2, the classes, the cache and training proposal, the evaluation (PROPOSED pre-registration)"
date: 2026-11-06
owner: Batt
---

# A detector for xmas_dun02's monsters (PROPOSED pre-registration)

**Batt, 2026-11-06 ~08:2x ICT** (rogue-xmas02.md 4E' 1, translated): a detector for this map on
the GPU if X2 shows v1 does not see its monsters, "Go ahead, approved". The GPU pause of
2026-10-29 is lifted FOR THIS; every GPU step keeps R1-R3 and the R2 co-tenant rule (fit-first's
VTON is the top priority, never touched), through guarded_build only; the plan is pre-registered
before any GPU step. **X2 FAILED at 08:4x** (rogue-xmas02.md:777-801): v1's `monster` class hit
1 of 937 labels (Myst Case 0 / 348, Cruiser 1 / 208, Cookie 0 / 174, Christmas Cookie 0 / 207),
precision 1 / 66.

**What this document is.** gef10-detector.md's form, adapted. It fixes the split, the rules, the
tiers, the class scheme and the evaluation's bars at its commit time. Every number marked **FIT**
is measured on the FIT watch, never guessed here. The parent freezes the parameters; any change
is a clock-labelled AMENDMENT committed BEFORE the step it changes. A failed tier is reported,
never re-run under the same bars.

## 0. The decisions this proposal needs (Batt's / the parent's)

> ➡️ ANSWERED 2026-11-06 ~10:45 (Batt): D0 by a 100 GB recorder floor; D1-D14 adopted as
> proposed. Amendment A (section 13).

| # | decision | proposed default | where |
|---|---|---|---|
| D0 | **the root disk** (infra, Batt): 123.96 GB free at 09:08 against the recorder's 120 GB floor; other tenants take ~0.68 GB/h | Batt frees >= 10 GB before the data plan; otherwise record only while the floor allows (the recorder stops cleanly at the floor). Never lower the floor, never record to RAM | 2c |
| D1 | **scope:** the new model replaces v1 ONLY on xmas_dun02 (the runner picks its model by map; v1 stays live everywhere else) | adopt; G1 / G2 are then reported, not gating. The alternative (one model for all maps, gef10's 26 classes + this map's, G1 / G2 gating) costs ~5 x the GPU time (8) | 7, 9 |
| D2 | **classes:** one class per tier species + `player`; the runner collapses them to `monster` | adopt, with 6's pre-registered Cookie / Christmas Cookie merge as the only fallback | 6, 7 |
| D3 | **the tier:** the four common species. Garm Baby and Christmas Goblin conditional (>= 30 kept labels; not expected). Stormy Knight OUT | adopt; a frame with an out-of-tier species in view is excluded (`unchecked_species`) | 1b, 7 |
| D4 | **init weights:** gef10 round 2's `last.pt` (sha256 `ebfc7a9a...`) | adopt; v1's `last.pt` is the alternative | 8 |
| D5 | **floor items:** no item class this round | adopt (gef10 13j: hunts give no clean item labels; Snatcher's steals go to the bag) | 4h |
| D6 | **the collection:** immune lattice watches (FIT, TRAIN, TEST) + one immune patrol recording (TEST) | adopt | 2a |
| D7 | **how much:** FIT 30 min; TRAIN 3 x 30 min, more by the stopping rule (max 5); TEST a 30-min watch + a 20-min patrol + X2 | adopt | 2b, 2d |
| D8 | **X2:** TEST of the runner's view (TEST-P), disclosed; never FIT or TRAIN | adopt | 2e |
| D9 | **the split:** TEST stand blocks by a rule fixed now + sessions by name | adopt | 3 |
| D10 | **terrain:** the `o3h-t` candidate, adopted only by 4f's FIT test | adopt the test | 4f |
| D11 | **engaged units:** E0 this round (excluded; the immune data has none) | adopt | 4i |
| D12 | **1d** on a STOP (< 50 walker samples or the sweep's edge): 120 ms | adopt (payf07 Amendment C, gef10 D2: the same RDP frame bus) | 4b |
| D13 | **training:** YOLO11n, imgsz 1280, batch 2, workers 1, seed 20261004, 20 epochs, close_mosaic 3, hsv_s 0.2, hsv_h 0.015, scale 0.1; VAL = the FIT watch (monitor only) | adopt | 8 |
| D14 | **the evaluation's verdict:** Q1c (collapsed) + P4A (patrol precision); per-species agreement, X2's 4A bar, G1 / G2, latency reported | adopt; pre-registered in its own doc BEFORE the cache | 9 |

## 1. The facts (read before this commit)

### 1a. What was read (and nothing else)

- The docs: rogue-xmas02.md (0, 1, 4A, 4E', 4J, 5), xmas02-prep.md (1, 6, 7), gef10-detector.md,
  gef10-eval.md, gef10-round2-measure.md 1b / 4, payf07-detector.md (1c, 10f, 10i, 10m, 11),
  orcsdun01-detector.md (2, 3n-6), training-cost.md.
- The code paths named in 1f (read, not run).
- **Client data, extracted this morning to /dev/shm (MIXCRYPT, `grf_read.py --decode-mixcrypt`,
  Batt 2026-10-05 option (a), study only), measured, then DELETED:** `xmas_dun02.rsw` and its 37
  RSMs (840 KB). The client GAT already in `/dev/shm/poring-lab-tmp/gat/data/` (X1's).
- **The gef10 cache's manifest** (`/mnt/poring-lab-datasets/.framecache/v2orc-payf07-gef10-20261026/manifest.json`):
  per-session frames and boxes (1g).
- **X2:** its `manifest.json` only, plus the numbers already published in rogue-xmas02.md 5. No
  X2 frame, packet or box was opened for this plan.
- `df` of the root disk (09:08). No other session exists on this map: pilots p1-p5 were
  unrecorded.

### 1b. The species (pinned rAthena e985006, pre-renewal; rogue-xmas02.md 1, xmas02-prep.md 1, 6)

| species (mob id) | spawns | walk (ms / cell) | AI | idle box (native px) | idle hue / sat | X2 labels (4A) | tier |
|---|---|---|---|---|---|---|---|
| Myst Case (1249) | 50 | 400 | passive | 65 x 77 (hops ~3 px) | 4° / 0.51 | 348 | yes |
| Cruiser (1248) | 35 | 400 | aggressive, ranged 7 | 39 x 98 | 355° / 0.42 | 208 | yes |
| Cookie (1265) | 20 | 200 | passive, assist | 27 x 55 | **44° / 0.32** | 174 | yes |
| Christmas Cookie (1246) | 20 | 400 | passive | 27 x 55 | **3° / 0.45** | 207 | yes |
| Garm Baby (1515) | 1 (30-min respawn) | 450 | aggressive | 74 x 60 | 267° / 0.20 | reported | conditional |
| Christmas Goblin (1607) | MVP slave only | 100 | aggressive | 42 x 68 (hops) | 2° / 0.32 | reported | conditional |
| Stormy Knight (1251), MVP | 1 (60-70 min) | 200 | aggressive | 141 x 133 | 334° / 0.38 | reported | **out** |

- **No species flies** (every idle box reaches the ground): no anchor (4c).
- **Cookie and Christmas Cookie share their images and boxes; only the palette differs**
  (xmas02-prep.md:328-332). Colour is the only cue: hsv augmentation stays mild (D13), the T2
  reference shows both in colour, and 6 pre-registers what happens if labellers cannot tell them.
- **Garm Baby and the Goblins will be rare by construction:** every watch's setup types
  `@killmonster2` (the MVP cleared, Batt's decision 3), which also restarts Garm Baby's 30-min
  respawn; Goblins come only with the MVP. The MVP is not stealable and has its own recognizer
  (X4); it is not a class here.
- Monster density: 127 on 50,183 walkable cells (2.5 per 1,000) against gef_fild10's ~119 on
  72,656 (1.6 per 1,000; gef10-prep.md 1).

### 1c. The map and its models (client GAT + RSW, measured 2026-11-06 ~09:0x)

- 260 x 260 cells; 50,702 type-0 cells on the client GAT (50,183 after the server's edge rule,
  xmas02-prep.md 1). The GAT sha256 starts `4cf9265fcce2fec4`.
- **The RSW:** version 2.1, sha256 `a5104e37fc40b4bf9091f88e1a47ad567640be4b8f78e8c18485858c5f35c9da`,
  **1,701 models from 37 RSM files** (gef_fild10: 1,497 from 46), 268 lights, 25 sounds.
  **Every RSM is version 1.4 and parses** with `poring_dataset.rsw` (which reads 1.x only). The
  files, translated, by count: conveyor belt 02 (809), gear (265), crane (120), inner boxes 3 / 2
  / 1 (64 / 63 / 41), bear wall (63), dice (38), conveyor belt 01 (38), open box (30), block
  castle (22), duck (21), toy robot (18), clown (16), rocking horse (15), Santa Poring (14),
  switch, Santa brick toy, machine Poring (10 each), and 18 more with 1-4 each.
- **The models are LOW:** 17.0 % of the walkable cells lie under a model's cell footprint, and only
  **7.6 % under a model taller than 20 altitude units** (gef_fild10 45.9 %, gef10-detector.md:113).
  The belts (median 4.6 units) and gears (7.4) lie on the floor; the tall ones are the cranes
  (median 28.1), the bear walls (26.5, up to 66) and the block castles (78.5).
- 🔴 **The occlusion here is TERRAIN, not models.** On the GAT (altitude up +; the walkable
  median 0, the non-walkable median +20), 11,031 non-walkable cells stand >= 10 units up (9,631
  >= 20, 2,675 >= 30), in 144 connected blocks (median 10 cells; 14 have exactly 4 cells, the
  2 x 2 pillars' size). **10.9 % of the walkable cells have such a block 1-4 cells SOUTH of
  them**, i.e. between them and the outdoor camera (yaw 0: the eye south, looking north).
  14,034 walkable cells are themselves raised >= 10 (platforms). The o3h rule's occluders are
  RSW models only (`orc_labels_fix.Occluders`), so it does not see these blocks. X2's by-eye
  check already saw truth boxes "on raised orange blocks (a monster behind them)"
  (rogue-xmas02.md:784-785). gef10's T1 failure 2 (a Poporing beside a rock face, 13r) was the
  same family; its GAT-step proximity rule was NOT supported there (gef10-round2-measure.md 4).
  This map's blocks are walls, not ramps (a raised cell beside the floor steps up a median 16.2
  units, p90 30; gef_fild10's cliff cells 6.9 a cell): 4f's candidate is view-dependent instead.
  (Measured on geometry only, not on screen; the screen share is a FIT measurement.)
- **Monster-like scenery = hard negatives:** ducks, toy robots, clowns, rocking horses, Santa
  Porings, machine Porings (~94 placed). Where v1's 65 false boxes on X2 sat was not read here.
- The only warp: the exit at (129,130) (a 3 x 3 trigger); no script NPC (xmas02-prep.md 0).

### 1d. The camera and the recording path

- Not in `indoorrswtable.txt`: the fitted OUTDOOR camera (`camera_rdp.json`) plus the GAT
  heights, as gef_fild10 (xmas02-prep.md:446-450). **X2's 12-frame by-eye check passed** (4J):
  the projected truth sits on the monsters. This plan re-checks it on FIT with fitted boxes (4e).
- X2's manifest: `backend` rdp, 1,320 frames from the frame bus, PNG level 1, `game_region`
  [80, 77, 1280, 720], `server` lab-rathena, **`recorder_version` 6**, 92.2 MB/min, the root-disk
  sink with `min_free` 120 GB. The 2026-11-05 standard chat window: (0, 585, 600, 720)
  (xmas02-prep.md:391).

### 1e. The sessions that exist, and what must be recorded

- **Exists:** X2 only (`20261105T225409-rdp-xmas02-x2`, NAS; 22 min; the immune Rogue patrolling
  the edge loop under dungeon@8.5, so mostly walking; 2 kills; packets 1,361 events).
- **Must be recorded:** everything for FIT, TRAIN and TEST (2b). No FIT data exists.

### 1f. The tooling: what exists, what is missing (none built here)

| # | gap | why it matters | file:line |
|---|---|---|---|
| T-1 | `map_labels` UI rectangles use `client_layout.RECTS`, whose chat window is the LEGACY (0, 532, 600, 626) | every 11-05+ frame's in-view and UI rules would use the wrong chat window. Fix: the session's `chat_window.for_sid(sid).rect`, and the nested `notice_left` dropped (score-session's fix) | map_labels.py:739-749; client_layout.py:53-62 |
| T-2 | no `XMAS02` MapSpec | cells 260 x 260, RSW / models in /dev/shm, species, walkers, fit_px, FIT / TEST role tables, TEST names (3b), conditional species, reference, labels name, salt `xmas02`, `dying_rule` | map_labels.py:126-238 |
| T-3 | `check_recording` wants `recorder_version` 5 | X2 and every new recording are v6 (e5d892f: only the IO rule and `guard_rule` changed): today the tool refuses them. Accept 5 or 6, as detector_vs_packets does | map_labels.py:710-716; detector_vs_packets.py:102 |
| T-4 | no terrain occluders | 4f's `o3h-t` candidate, reported both ways by `threshold` and `check` | orc_labels_fix.py:517-564 |
| T-5 | `warp_watch.py run` records its OWN 5-Hz JPEG to the NAS; the label tool reads recorder PNG sessions | a no-recorder mode beside `record_session.py` (as gef10's w2 was run), the hunting layout kept, the lattice built by 3a's rule | warp_watch.py:28-31 |
| T-6 | `recorder_boxes.py` rows carry the model's class names; the scorer counts `monster` only | the species collapsed to `monster` in the rows, with a positive case | detector_vs_packets.py:513 |
| T-7 | `build_frame_cache --labels map` takes TRAIN sessions only; VAL comes from a linked cache | D1 + D13: a map-labelled VAL session (monitor only) | build_frame_cache.py:152, 1899 |
| T-8 | C1's notice rule (`--c1-rule round2`) is gef_fild10's only | generalised to this map | map_labels.py:26-34 |
| T-9 | the evaluation's TEST labels and pack (`--eval-test2`) are gef_fild10's only; `eval_q1` scores classes as they are | a per-map eval flag and a collapsed-class score (Q1c) | map_labels.py:36-47 |
| T-10 | T2 instructions + reference for this map | a new instructions file (its sha256 in an amendment before the pack) | 5 |
| T-11 | (deployment, later) `BoxWatch` uses `UnitDetector()`'s default v1 and `cls == "monster"` | a model per map + the species collapsed; Batt's decision, after the evaluation | dungeon_hunt.py:992-1013 |

Every tool gets tests and a positive case before it reads FIT; TEST stays refused by name.

### 1g. The yields of earlier rounds (the gef10 cache's manifest; boxes = written frames + monster boxes)

| session | kind | minutes | frames written | monster boxes | per minute |
|---|---|---|---|---|---|
| gef10 `w2` | immune lattice watch, 30-s dwells | 34 | 774 | 542 | **15.9** |
| payf07 `watch-w1` | immune lattice watch | 40 | 1,052 | 1,016 | **25.4** |
| gef10 `pilot` | hunting run | 16 | 275 | 78 | 4.9 |
| gef10 `a2` | scored hunting run | (40-min block) | 870 | 81 | ~2 |

- (boxes - frames = monster boxes: each written frame carries one `player` box; this reproduces
  gef10 13i's pilot 78 and payf07 10f's staged 242.)
- **gef10's whole TRAIN was 2,232 frames with 906 monster boxes**, and its model passed Q1 at
  recall 0.983 / precision 1.000 for Orc Lady, Orc Warrior and Poporing (gef10-eval.md RESULT R2).
  training-cost.md's budget (1,500 frames / 3,000 instances PER species) was never met by any map.
- gef10's hunts gave 22-67 standing rows each (too few for 3c's 50: 13o); w2 gave 271.

## 2. The data plan (within CLAUDE.md rule 7 and the 120 GB floor)

### 2a. How: an immune lattice watch, with one patrol recording held out

| | immune lattice watch (warp_watch's protocol + record_session 1 fps PNG) | the patrol runner (dungeon_hunt patrol, immune, as X2) |
|---|---|---|
| frames the label rule can use (our character still, 4g) | nearly all after each warp's settle | only stops: stalls, fights, scans (p4 / p5 walked ~14 waypoints a minute) |
| standing rows for C1 / 3c | many (w2 271) | few (hunts 22-67) |
| views | the whole map, every background; the edge band by its stands | the edge loop only (the runner's real view) |
| monsters it walks past | not covered (the camera is still) | covered, but not labelable while moving |
| risk | none new (the protocol of orcsdun01 / payf07 / gef10) | none new (X2's command) |

- **So the watches give the labels, and the patrol tests the runner's view.** A detector trained
  on still frames must be judged on moving ones: P4A (9) does that on X2 + xp1.
- **The watch:** the Rogue immune (`collect_v2.py immune-on`, the screenshot read and
  `immune-confirm` for THIS login), the hunting layout (1 row, collapsed, Battle Log) and the
  2026-11-05 standard chat window, judged on a screenshot BEFORE the recorder starts (gef10's
  Amendment A lost a whole watch to the wrong layout). Setup: `@killmonster2` (the MVP cleared).
  Per stand: `@warp xmas_dun02 x y` through ro_agent.gm (UI gate, chat window check, typing
  guard), a 2.5-s settle, a **30-s dwell** (orcsdun01 / gef10's dwell; ~40 s a stand with the
  typing: ~45 stands per 30 min). No spawn, no world click. The chat input closed after the last
  line.
- **The stands:** the three-check stand cells (client and server walkable, outside the warp span
  and the zone, a fully walkable 5 x 5) on an ~11-cell lattice, minus the stands that see the exit
  warp (|dx| <= 16, |dy| <= 12 of (129,130): their frames would be `warp_in_view`). A scratch
  approximation (5 x 5 walkable only) gives ~221 stands, 45 of them within 12 cells of the edge
  loop.

### 2b. The recordings

| name (label) | role | protocol | stands | minutes | ~GB at 92.2 MB/min |
|---|---|---|---|---|---|
| `xw1` (`xmas02-xw1`) | FIT (+ VAL, D13) | watch, seed 2611061 | non-TEST, seeded order | 30 | 2.8 |
| `xw2`, `xw3`, `xw4` | TRAIN by 3c | watches, seeds 2611062-4 | non-TEST, new orders | 30 each | 2.8 each |
| (`xw6`, `xw7`) | TRAIN, only if 2d asks | watches | non-TEST | 30 each | 2.8 each |
| `xw5` | TEST | watch, seed 2611065 | **TEST stands only** | 30 | 2.8 |
| `xp1` (`xmas02-xp1`) | TEST-P | X2's 4A command with `--label xmas02-xp1`, dungeon@8.7, immune, MVP cleared | the edge loop | 20 | 1.85 |
| X2 (exists) | TEST-P | | | 22 | (NAS) |

- **Totals for the default plan:** 6 new recordings, **170 minutes, ~15.7 GB written and shipped
  one at a time**, never more than ~2.8 GB on the root disk at once. `record_session.py --backend
  rdp --format png --fps 1 --out /home/batt/poring-lab-rec --max-bytes 3G` (xp1 `2G`), then
  `dataset_ship.py ship <session>` (X2's 2.03 GB took ~2 min) BEFORE the next recording.
- **Live time:** ~40 min per watch (setup + 30 min + ship), ~4 h for the six, on the one Windows
  session (it serialises with X3 and the hunt_flow A/B).
- **Not in a market window** (09:30-10:15, 14:00-14:45 weekdays), and best outside SET hours:
  10 of 11 recorders on 2026-10-26 were cut by quant's own spikes (gef10 13x).
- xw5 and xp1 may be recorded any time after this commit; their names are refused by every
  measuring and training command from now (3b), and nothing reads them before T1.

### 2c. The disk arithmetic (D0)

- **09:08:** 123.96 GB free; the floor (`dataset_ship.MIN_FREE_BYTES`, 120 x 10^9) leaves
  **3.96 GB**. X2's ship left 130.5 GB at 23:32: other tenants took **~0.68 GB/h** since
  (6.54 GB in 9.6 h).
- The recorder refuses below the floor at its start and stops cleanly mid-recording
  (record_session.py:35-38): the failure is a short session, not a full disk.
- **At ~0.68 GB/h the floor is crossed around 15:00 today with nothing of ours recorded.** A
  30-min watch needs ~3.1 GB of headroom at its start (2.8 GB + its own drift): that holds only
  until ~10:20, i.e. for ONE watch right after the 09:30-10:15 window. A 20-min block (~2.1 GB)
  fits until ~12:00. Shipping between recordings does not restore what the drift took.
- **So the six recordings need the drift covered:** >= 10 GB freed by Batt keeps a 30-min watch
  possible for ~16 h from its freeing (enough for the ~4 h of 2b).
- Infra observation only. Nothing here frees, moves or lowers anything.

### 2d. The stopping rule for TRAIN (fixed now)

- After each TRAIN watch: label it (frozen params), its own C1 (3c), and count the boxes in its
  WHOLE frames per tier species.
- **Stop when every tier species has >= 300 boxes in whole TRAIN frames** (about gef10's
  per-species scale, which passed Q1; a planning target, not a bar), or after 5 TRAIN watches.
- **The estimate (FIT replaces it):** 1g's 16-25 boxes a minute times this map's 1.5 x density,
  less an unknown terrain loss, at X2's sighting mix (Myst Case 37 %, Cruiser and Christmas
  Cookie 22 %, Cookie 19 %): ~140-230 Cookie boxes per watch, so 2-3 TRAIN watches. Frames
  written: ~700 per watch (w2: 52 % of its candidates).

### 2e. X2's role (D8)

- X2 is **TEST-P** for the new model: P4A (9) and X2's own 4A numbers, v1 beside the new model on
  the same frames and truth. It is also a T1 part (5).
- **Disclosure:** X2 was scored for v1 (692 s of CPU boxes, the simple truth on every frame) and
  12 of its frames were judged by eye with truth boxes drawn (4J). This plan uses its PUBLISHED
  counts (the species mix, 1g / 2d). It was never labelled under any o3h rule, no parameter of
  this plan comes from it, and the new model never sees it. It is refused by name for FIT and
  TRAIN.

## 3. The split, fixed now (before any frame is recorded or read)

### 3a. The stands, by cell (D9)

- **Blocks of 26 x 26 cells:** bx = x // 26, by = y // 26 (10 x 10 blocks). **A stand is TEST when
  (bx + 3 * by) mod 5 == 0** (20 blocks: 19.9 % of the walkable cells, 19.0 % of the edge loop's
  cells; ~44 of the ~221 approximate stands).
- FIT and TRAIN watches dwell only at the other stands; the TEST watch xw5 only at TEST stands.
- A block is about one screen wide (31 x 23 cells in view), so views from neighbouring stands still
  overlap: TEST holds out stands and times, not whole places (a known limit, as gef10-eval.md's).

### 3b. The sessions

- **FIT** (every parameter is measured here and only here): **xw1**.
- **TEST** (read only by T1 after the freeze, and by the evaluation): **xw5, xp1 and X2**, by name
  (`*-rdp-xmas02-xw5`, `*-rdp-xmas02-xp1`, `20261105T225409-rdp-xmas02-x2`), refused by
  `offset`, `threshold`, `engaged`, `labels`, `pack` and the cache from this commit.
- **TRAIN:** xw2-xw4 (and xw6-xw7 if 2d asks), each by 3c; **VAL:** xw1 (D13).
- **T2's pool:** the kept labels (frozen parameters) of xw1 and of the TRAIN sessions admitted
  when the pack is built.

### 3c. The join rule (payf07 / gef10 3c; the recording path updated)

A session recorded after this commit joins TRAIN (never TEST) when ALL hold: manifest `backend`
rdp, `recorder_version` 5 or 6 (T-3), `format` png, `game_region` [80, 77, 1280, 720], `server`
lab-rathena, packets present; labelled by the frozen parameters and tool; **its own C1 pooled <=
0.050 on >= 50 standing labels scored**. A hunting session (immunity off) may join only by this
rule, with its engaged units excluded (E0).

## 4. The label rule, "xmas02-o3h-t" (or "xmas02-o3h" if 4f does not adopt terrain)

### 4a. Reused from gef10 / payf07, unchanged

fix 2's facing, 2b `next_move`, 2c `ambiguous_view`, **2d `facing_unknown`** (Amendment C); boxes
from the sprites at the 1d time, the masked-NCC fit within +-6 px, tau 0.092, k 0.140, the search
+-16 px for C2; the standing rule for C1 / C2 (idle >= 1 s, isolated 120 px, clear of the UI and
the frame edge by 16 px); o3h; **the T_h floor on EVERY kept label** (payf07 11, `weak_fit`);
a frame with any excluded label is not written; our own box as `player`; `dying_in_view`
(gef10's D8); the hunting layout read from pixels per frame.

### 4b. 1d, re-measured on FIT (D12)

payf07 4b with its Amendment A: walkers walking one move through the sweep (0-500 ms), isolated,
clear of the UI and of every model box. Walkers: 1249, 1248, 1265, 1246 (1515 if seen). **Stop**
below 50 samples or at the sweep's edge: then 120 ms (D12). Immune watches with 127 wandering
monsters should give more walkers than gef10's piles (15 samples); that is FIT's to say.

### 4c-4d. No anchor; the fit radius

No species flies. The per-species median best-NCC offset of FIT's clear kept labels is REPORTED
(Myst Case and the Goblin hop ~3 px, inside +-6). +-6 px for every species.

### 4e. T_h, re-measured on FIT

The pooled 5th percentile of the fit NCC of FIT's kept labels that are clear of every model box
(and of terrain if 4f adopts it), not engaged, **uncrowded (Amendment B) and facing-known
(Amendment C)**, frozen to 3 decimals (gef10 0.636, payf07 0.479: per map). **If it comes out
below 0.40,** the parent looks at 12 low and 12 high FIT crops before freezing (gef10 13d), and any
change is an amendment. Reported with it: what each candidate value keeps (gef10 13f's table),
the fitted box sizes per species against the native ones, and **the drawn hue of Cookie vs
Christmas Cookie** on clear labels (does the colour cue survive on screen?).

### 4f. The terrain candidate `o3h-t` (D10), and its adoption test on FIT

- **A terrain occluder** = a GAT cell >= 10 units above the label's own cell, lying SOUTH of it
  (y < the label's y: nearer the yaw-0 camera), drawn as the box from its floor to its top (its
  corners through `rsw.project_points`, the label's scene). The label is **under terrain** when
  its predicted box overlaps any such cell's screen box.
- **Under terrain is treated exactly as under a model** by o3h: kept only with its fit passing
  AND NCC >= T_h; out of T_h's measuring set; C1 treats it as o3h treats an under-model label.
- **The adoption test (FIT, fixed now):** among FIT's clear-of-models, not engaged, uncrowded,
  facing-known fitted labels, the under-terrain ones against the rest. **Adopt `o3h-t` when n
  under terrain >= 30, their median NCC is lower by >= 0.05, and Mann-Whitney p < 0.01.** Else
  plain o3h (the floor still guards every label) and the counts are reported. The 10-unit step is
  fixed now; 5 and 20 are reported, never chosen from.
- Why view-dependent: gef10's proximity rule cut good labels that fit no worse (6.0 % of the
  kept, all of Green Plant); here a block hides only what stands behind it.

### 4g. The candidate frames

A frame (capture t; tw = t - 1d) is a candidate when ALL hold: the map is xmas_dun02 at tw and t;
no `map_change` in [t - 5 s, t] (each same-map @warp is one); **our character still** (the same
Timeline cell every 100 ms from tw - 1 s to t); outside the GM-command windows (each @warp, the
setup's `@killmonster2` and immunity lines); **the hunting layout read from pixels with the
session's chat window** (`chat_window.for_sid`), else `ui_layout_mismatch`.

### 4h. Frame-level exclusions (a frame is not written)

`warp_in_view` (the exit portal), `other_player`, `unchecked_species` (1515, 1607, 1251 unless in
the tier), `dying_in_view`, a floor item in view (`unlabelled_item`: no item class, D5; the
immune watches drop nothing), and our character under Hallucination (EFST_ILLUSION; counted, not
expected with immunity). The UI windows are the hunting layout's with the session's chat window
(T-1). C1 also drops a standing label under a pickup notice (round 2's rule, T-8).

### 4i. Engaged units: E0 (D11)

Amendment B's test (an act either way with our character, or our attack request, within [tw - 3 s,
tw + 1 s]) EXCLUDES the unit; its frame is not written. The immune watches have none. gef10's E2
kept 2.3 % of its engaged units (13g), so the fight is not worth a variant this round. A later
round may label engaged units from X3's recordings (Cruisers fight from 7 cells, so our own sprite
covers them less than gef10's melee orcs) under its own amendment and T2 stratum.

### 4j. Frozen with the parameters

1d, T_h, tau, k, the fit radius, o3h or o3h-t (with its step), the RSW / RSM / GAT sha256, the
tool's commit: `/dev/shm/poring-lab-tmp/xmas-det/params.json` and its sha256, in the RESULTS.

## 5. T1: the geometric check (C1), on TEST

- **Data:** xw5 + xp1 + X2, every candidate frame (4g). C1 = bad / standing labels scored, the
  PREDICTION (no fit) after o3h's (or o3h-t's) under-box rule, 2b, 2c, 2d and the notice rule.
- **T1 PASSES when C1 pooled <= 0.050 (unrounded) on >= 100 scored rows;** fewer rows: NO
  VERDICT, never a pass (gef10 round 2's rule). C2 per species with >= 20 standing labels: median
  |dx|, |dy| <= 4 px; **a C2 failure is a STOP** (the parent tells Batt before any cache).
- Reported: C1 per species, per part, and per SIGHTING; the exclusions by reason; the
  under-terrain counts.

## 6. T2: the blind check (two NEW labellers)

- Each labeller sees only the pack and the new instructions file (T-10; its sha256 recorded in an
  amendment BEFORE the pack). It describes a toy-factory floor (orange and pale tiles), toy models
  that are scenery (ducks, robots, clowns, rocking horses, Santa Porings), a red-haired Rogue, and
  **two species that differ ONLY in colour (tan vs red)**. Questions, answer format and box drawing
  as gef10's.
- **Seed 51**, salt `xmas02`; per tier species the first 30 kept labels of `t2_order` (fewer: all).
  One stratum (N): no engaged labels this round.
- **The reference** (MULTI-VIEW, orcsdun01 3l): Myst Case, Cruiser, Cookie, Christmas Cookie,
  Garm Baby, Christmas Goblin, Stormy Knight, Poring (1002), Santa Poring (1062, the model's
  look-alike, extracted at run time).
- **The bars (unchanged):** per species, >= 90 % good from EACH labeller AND the species right on
  >= 95 %. T2 passes when every tier species passes.
- **The one pre-registered fallback:** if Cookie or Christmas Cookie fails ONLY on species, every
  wrong species answer being the other of the two, and both pass good >= 90 %, the two train as
  ONE class (`cookie_any`); the runner fights both alike. Any other failure: gef10's D4 / D5 (the
  species is not a class; its frames are excluded).

## 7. The classes (D1-D3)

`config/detector/classes-xmas02.json`, written after T2 from the species that pass: **0 player,
1 Myst Case (1249), 2 Cruiser (1248), 3 Cookie (1265), 4 Christmas Cookie (1246)** (or 3
`cookie_any` by 6), then 1515 / 1607 only if they reach the tier. Names: the KB's aegis names in
lower case, as gef10's list. No `npc` (none on the map), no `warp` (its frames are excluded), no
item class (D5).

- **Map-scoped (D1):** the model runs only on xmas_dun02; the runner maps its monster classes to
  `monster` (T-11), so a Cookie / Christmas Cookie confusion costs the runner nothing.
- **The alternative (one model for all maps):** gef10's 26 classes unchanged + these four as
  26-29, the gef10 cache linked, G1 / G2 gating (8, 9).

## 8. PROPOSED: the cache and the training (nothing built here)

- **The cache:** `build_frame_cache.py --labels map` on the TRAIN label files (frozen params, own
  C1 by 3c), xw1 as VAL (T-7; its labels re-made with the frozen file, as gef10 13p re-made its
  FIT labels), no link (D1); a dry run first; a guarded `cache:` step with the
  sustained IO rule `--threshold 30 --sustain 30` (Batt 2026-10-28; the old spike rule aborted
  gef10's cache twice, 13v / 13x). It reads the PNG shards from the NAS and writes the shards to
  the NAS (~2,100 frames, ~3.4 GB; w2's 774 frames took 204 s).
- **Init (D4):** gef10 round 2's `last.pt`,
  `/mnt/poring-lab-datasets/archive/train/gef10-20261026/weights/last.pt`, sha256 `ebfc7a9a...`
  (it has seen prt_fild08, orcsdun01, pay_fild07 and gef_fild10); the class head starts fresh.
- **Settings (D13):** YOLO11n, seed 20261004, imgsz 1280, batch 2, workers 1, **20 epochs** (a
  map-only TRAIN is ~1/9 of gef10's frames, so 20 epochs are ~1/5 of its frame-epochs),
  close_mosaic 3, `hsv_s` 0.2 and `hsv_h` 0.015 (+-5.4° against the 41° Cookie gap), `scale` 0.1
  (the RO camera's zoom is fixed: size is real). The scored checkpoint: `last.pt` after the last
  COMPLETED epoch.
- **Under R1-R3 (CLAUDE.md rule 5):** `train-day.sh` with WORKER=1 (one long-lived vision worker;
  its cold start is an IO burst: `worker:vision` once, in a quiet window, at ~:06 past an hour),
  MID_CKPT=1, the adaptive duty cycle, the paired R3 with the absolute camera-drop stop, the 25 %
  VRAM cap (4,077 MiB); **R2 co-tenant:** free VRAM >= our cap + 1,024 MiB at the start, a stop
  below 1,024 MiB in the run, the 10-s yield while fit-first's VTON computes; never touched.
  Ollama's `/api/ps` empty. `IO_GUARD="--threshold 30 --sustain 30" IO_RESUMES=20
  IO_QUIET_MIN=0`. No scratch job beside it except under `MemoryMax=4G MemorySwapMax=0` (13z-4's
  OOM). The runner's CPU detector keeps priority (the loader niced first).
- **The cost (an estimate; N_x = TRAIN frames written, ~2,100 by 2d):**

| | frame-epochs | compute (0.193 s, payf07's measure) | wall (0.505 s: gef10's 26.7 h for 190,250) |
|---|---|---|---|
| **map-scoped (default)** | 2,100 x 20 = 42,000 | **~2.3 h** | **~6 h** |
| one model for all maps | (19,025 + 2,100) x 10 = 211,250 | ~11.3 h | ~30 h |

  The 12-h step limit (per attempt) and train-day's own resumes cover the default with room.

## 9. PROPOSED: the evaluation (its own doc, `docs/benchmarks/xmas02-eval.md`, pre-registered BEFORE the cache)

- **TEST labels** made once AFTER the training ends (frozen params; xw5, xp1, X2). **The pack:
  seed 53**, the first 60 per tier species by `t2_order`, two NEW labellers, 6's instructions and
  reference; a crop is EVALUATED when both answer yes / good / the label's species.
- **Q1c (verdict): per tier species with >= 50 evaluated crops, recall >= 0.80 AND precision >=
  0.80, classes COLLAPSED** (a detection of any of the map's monster classes counts; precision
  over those detections whose centre falls inside an evaluated crop's box: the gef10 rule).
- **P4A (verdict): on the patrol TEST (X2 + xp1), 4A's rule (the simple truth, UI boxes dropped,
  rogue-xmas02.md 4A / 4J), the pooled monster precision >= 0.80 on the STILL captures** (no move
  of ours in the 500 ms before: the scorer's own split), with >= 100 detections there, else NO
  VERDICT. Why still only: frames lag the server ~0.5 s, so a moving truth box is displaced.
- **Reported, deciding nothing:**
  - **X2's 4A bar** (recall >= 0.80 per species, pooled precision >= 0.80, all captures) for v1
    and the new model side by side; also on xp1. Not a gate: its truth includes monsters hidden
    by terrain, models and popups (4J saw them), and gef10's model, which passed Q1 at 0.983, had
    recall 0.397 on that kind of truth (Batt's demo, gef10-eval.md:353);
  - P4A's recall per species and its moving captures; first sight; FPs by kind (toy models by eye
    on 30 false boxes);
  - Q1s: the same bars with the classes agreeing, and the Cookie / Christmas Cookie confusion;
  - CPU latency (ONNX through UnitDetector, 200 TEST frames, nice 10): **p95 <= v1's x 1.10** is
    what the runner needs (gef10r2: 499 vs 617 ms);
  - G1 / G2 (gef10-eval.md's), because the model is map-scoped (D1). Under the alternative they
    gate, as before (gef10 round 2 failed G1 by two false boxes: 0.867 < 0.882).
- **The verdict:** PASS when Q1c holds for every tier species with a bar and P4A holds; no
  species with a bar means "not established". **Passing does not switch the live detector:**
  deploying it on xmas_dun02 (T-11) is Batt's decision.

## 10. What this plan does differently from gef10, and why

| gef10's problem | here |
|---|---|
| 1d STOPPED twice (2, then 15 walker samples: orcs in piles and fights) | immune watches with wandering monsters; the 120 ms fallback pre-registered (D12) |
| Amendment A: the watch ran in the wrong layout, every frame `ui_layout_mismatch` | the layout and the chat window judged on a screenshot before each recording; T-1 for the 11-05 chat window |
| Amendments B / C: T_h dragged down by piles and unknown facings | both in from the start (4e) |
| 13i: thin yield (8.8 % of candidates with a box); 13o: hunts below 3c's 50 rows | TRAIN from watches (w2's 271 rows); the stopping rule (2d) |
| 13r: T1 failed on two sightings in 61 rows (a notice; a rock face) | the notice rule in C1, a terrain candidate tested on FIT, a verdict needs >= 100 rows, a whole TEST watch |
| 13v / 13x: the cache aborted twice on one-spike IO trips | the sustained rule from the start (8) |
| 13z: R2 refused the VTON; 13z-4: our scratch OOM | the co-tenant rule; scratch only under a memory cap |
| ~27 h of wall time for 10 epochs on a shared GPU | map-scoped: ~6 h |
| round 2 failed G1 (precision 0.867 < 0.882) on prt_fild08's gold set | map-scoped: the model never runs on prt_fild08; G1 / G2 reported (D1) |
| payf07 T2 round 1: weak fits; orcsdun01: species failed until a multi-view sheet | the floor on every label and the multi-view reference from the start |
| gef10 13j: floor items unlabelable from hunts | no item class (D5) |

## 11. What the parent runs, in order (rough times)

1. Record section 0's answers as Amendment A (D0 first). (minutes)
2. The tool gaps T-1-T-10, offline, tests and positive cases, in a tmpfs worktree. (~3-4 h agent
   time; no market-window disk steps)
3. The client inputs in /dev/shm (seconds; also after any host reboot):

        python3 scripts/grf_read.py extract /mnt/poring-thai-src/ro_thai/data.grf 'data\xmas_dun02.rsw' \
            --out /dev/shm/poring-lab-tmp/xmas-det/grf --decode-mixcrypt
        # then the 37 RSMs the RSW names ('data\model\' + each model_file), --decode-mixcrypt --decode-des
        # sprites: X1's archive (xmas02-prep.md 7) merged with Poring / Santa Poring; the KB: data/kb's
        # classes.json + the MERGED monster_sprite_names.json (never copied over data/kb's)

4. The lattice file by 3a's rule (offline, minutes). Then **xw1** (live, ~40 min) -> ship.
5. FIT (CPU, niced, a 4 GB scope, ~1 h): `offset`, `threshold` (both rules), 4f's test, the
   labels, a C1 diagnostic, the yields; the PROPOSED params. Then the parent's decisions and the
   FREEZE (an amendment).
6. **xw2-xw4** (live, ~40 min each, each shipped before the next), each labelled + own C1 (~10 min
   each); 2d's stopping rule. **xw5** and **xp1** whenever the disk allows (any time after this
   commit).
7. T1 on xw5 + xp1 + X2 (~10 min) -> T2 pack (seed 51) and two NEW labellers (~30 min) -> the
   class list.
8. `docs/benchmarks/xmas02-eval.md` pre-registered (9). Then the cache (~15 min) ->
   `worker:vision` (a quiet window) -> training (~6 h wall) -> the evaluation (~1.5 h, labellers
   included).

Calendar: ~2 days if D0 is answered today; the weekend has no market windows.

## 12. RESULTS (appended below, clock-labelled; nothing above this line is edited after the pre-registration commit except by a labelled AMENDMENT)

**xw1, attempt 1 (2026-11-06; recorder session `20261106T115507-rdp-xmas02-xw1`, watch
`20261106T115540-watch-xmas_dun02-xw1`): STOPPED by the recorder's IO guard after 5.5 min.**
- Setup (11:50-11:55): the client restarted onto the Rogue (Thief8fce, Lv 99 / 50), the game-entry
  chat check passed; the hunting layout read from pixels (`client_layout.py read`: 1 row, panel
  collapsed, Battle Log); `stage_items.py immune-on` at 11:53:51, its frame read: "You are now
  immune to attacks."; `@warp xmas_dun02 7 21`, `@killmonster2` ("All monsters killed!"); a judged
  screenshot.
- The recorder (Amendment A's command + `--seconds 1980`) started 11:55:07; the watch 11:55:40
  (seed 2611061, `lattice-train.json`, 30-s dwells, ~42 s a stand).
- **12:00: the recorder stopped itself: `io_guard: quant-ticker-engine 28.3% (spike above 25.0%)`**
  (the tolerant DISK_RULE of a disk sink), after **328 frames, 662,527,701 bytes (121.4 MB/min),
  248 packet events**. It warned "SET hours" at its start (plan 2b: best outside SET hours; gef10
  13x: 10 of 11 recorders on 10-26 were cut by quant's own spikes).
- The watch went on with nothing recording; it was stopped by SIGINT inside a dwell at 12:02:20
  (stand 10 of its order; no line half-typed). The Rogue stays immune and idle at (93,148); the
  frame judged clean.
- **By the standing rule (one IO abort: stop and ask), recordings and shipping are PAUSED for
  Batt.** The partial session (662.5 MB) stays on the root disk until shipped (`dataset_ship`
  refuses SET hours anyway).

**Amendment D's calm wait, live positive case (14:12:24-14:17, read-only, nothing recorded):**
`record_session.wait_ready(first=False)` against the REAL capture cgroups (7: quant-postgres,
-ticker-engine, -orderbook-engine, -marketdata-engine, -mongo, frigate, the capture-streaming-pro
cron), the market-open window ignored for this check: **ok after 268.4 s** (269 polls, 57 busy).
quant-postgres went above 10 % at 22 s (13.6-16.4 %), the worst was **26.9 %** (it would have tripped
the old one-spike rule at 25 %; the sustained rule needs 30 s above 30 %), and the wait released 60 s
after the last busy poll. The script and its output: `/dev/shm/poring-lab-tmp/xmas-det/resume-check/`.

**xw1, continuation (Amendment D; recorder session `20261106T144500-rdp-xmas02-xw1`, watch
`20261106T144252-watch-xmas_dun02-xw1b`): COMPLETE, one part, no pause.**
- Prep 14:42: `@killmonster2` ("All monsters killed!"), the frame judged clean (chat closed, no
  dialog or notice icon, HP 100 %). The chain started 14:42:50; the recorder waited out the
  market-open window and began part 0 at **14:45:00**; the watch had warped to stand 6 at 14:43:01,
  waited 115.1 s, warped there AGAIN at 14:45:08 and dwelt (Amendment D's re-warp, live).
- **Stands 6-41 of seed 2611061's order (36 dwells, each recorded whole in part 0, no redo)**; the
  25-min box ended the watch at 15:10:16, the recorder ended on the SIGINT at 15:10:19.
- **1,515 frames, 3,275,661,572 bytes (129.7 MB/min), 1,069 packet events.** The guard (`>30.0% for
  30s`): worst **32.1 % on quant-postgres, 4 s above 30 %**: no stop; the old one-spike rule (25 %)
  would have cut this part too.
- The end frame judged clean at (192,127), HP 100 % all along (immunity held).
- **FIT = the two `*-rdp-xmas02-xw1` sessions: 42 whole dwells** (6 + 36), ~30 min of watch.

**xw2 (TRAIN candidate, Amendment F; recorder session `20261106T151122-rdp-xmas02-xw2`, watch
`20261106T151123-watch-xmas_dun02-xw2`): COMPLETE, one part, no pause.**
- Prep 15:10:50: `@killmonster2`, the frame judged clean. Part 0 from 15:11:22; seed 2611062,
  stands 0-42 (43 dwells, each recorded whole, no redo, no wait); the 30-min box ended it at
  15:41:26; the end frame clean at (137,214), HP 100 %.
- **1,804 frames, 3,910,784,149 bytes (130.1 MB/min), 1,417 packet events.**
- **The guard: worst 79.5 % on quant-postgres, 79 s above 30 % in all, never 30 s in a row: no
  stop.** Not attributed: our recorder writes ~2.2 MB/s sequentially, and quant's own bursts reached
  47-68 % on 10-09 with nothing of ours running (host-disk notes). Reported to Batt as an infra
  observation; the rule is Batt's (Amendment D).
- xw3 started 15:42:39 (seed 2611063, session `20261106T154241-rdp-xmas02-xw3`).

**xw3, part 1 (recorder session `20261106T154241-rdp-xmas02-xw3`, watch
`20261106T154241-watch-xmas_dun02-xw3`): STOPPED at 16:00:17 by the chat-window check, nothing
typed.** Prep 15:42:08 (`@killmonster2`, judged clean); seed 2611063, stands 0-24 (25 whole dwells,
one part, no pause); **1,057 frames, 2,059,108,049 bytes (116.9 MB/min), 1,006 packet events**; the
guard's worst 36.4 % on quant-postgres, 11 s above 30 %.
- **Why:** standing at stand 24 (37,159), before typing stand 25's `@warp`, the padlock read closed 5.6 / open 19.7 by grey (margin 14.1 < 15)
  and 0.366 / 0.229 by colour shape (margin 0.137 < 0.15): "unknown", the same on three read-only
  re-reads (a static floor). The frame shows the standard window (6 lines, docked, tabs Battle Log |
  Chat), nothing over it.
- **Measured before changing anything (16:03, offline, `padlock-study/` in scratch):** 153 recorded
  frames of today's watches (one per 30; the padlock LOCKED in all) read 151 locked + 2 unknown (that
  stand); 35 archived 11-05 / 11-06 chat-window frames with a window read 17 open (grey margin
  >= 39.9, shape margin -0.28 .. -0.30), 17 locked and the stop frame unknown.
- **The reader's shape margin is 0.10 since (chat_window.PADLOCK_SHAPE_MARGIN, test with the real
  readings):** every one of the 188 frames then reads its truth; only the 3 unknowns change (to
  locked). The live re-read at the stand: locked. Grey's own rule is unchanged.
- xw3 continues from stand 25 with the rest of its 30-min box (Amendment D's `--start-cell`).

**xw3, part 2 (recorder session `20261106T160700-rdp-xmas02-xw3`, watch
`20261106T160701-watch-xmas_dun02-xw3b`): COMPLETE.** Prep 16:06:36 (`@killmonster2` typed past the
check at the same stand, judged clean); `--start-cell 25 --max-minutes 12.5`; stands 25-42 (18 whole
dwells, one part, no pause, no wait); **768 frames, 1,605,104,451 bytes (125.4 MB/min), 641 packet
events**; the guard's worst 23.6 %. The chat check passed every line (three "tabs unread, typing goes
on" notes on the second tab's label, as on xw1). **xw3 = 43 whole dwells over two sessions.**

**xw5 (TEST, `lattice-test.json`, seed 2611065) started 16:20:44** (session
`20261106T162044-rdp-xmas02-xw5`); prep 16:20:22 judged clean.

**xw5 (TEST; recorder session `20261106T162044-rdp-xmas02-xw5`, watch
`20261106T162045-watch-xmas_dun02-xw5`): COMPLETE, one part, no pause.** Seed 2611065 over
`lattice-test.json` (88 TEST stands), stands 0-42 (43 whole dwells); the 30-min box ended it at
16:51:04; **1,819 frames, 3,935,165,749 bytes (129.8 MB/min), 1,028 packet events**; the guard's
worst 24.7 %. Nothing reads it before T1 (3b).
- **The afternoon's recordings (all on the root disk until the 17:00 ships):** xw1 x 2 (FIT, 42
  dwells), xw2 (43), xw3 x 2 (43), xw5 (TEST, 43): **6 sessions, 15.46 GB**; root free 108.65 GB at
  16:51 (`df -B1`).

**The 17:00 ships (Amendment D): all six sessions on the NAS, 17:00:52-17:10:55.** `dataset_ship.py
ship`, one at a time (tolerant disk rule, no trip): each hashed, rsynced, RE-HASHED on the NAS,
indexed in INDEX.jsonl, then deleted locally. xw1 663,096,484 + 3,278,294,658; xw2 3,913,919,075;
xw3 2,060,931,443 + 1,606,432,755; xw5 3,938,302,466 bytes (the NAS manifests carry each
`checksums_sha256`). The local root is empty; root free 123.75 GB at 17:11 (`df -B1`).

**xp1 (TEST-P, Amendment E; recorder session `20261106T171533-rdp-xmas02-xp1`, runner
`20261106T171539-demo-dungeon-rogue-xmas_dun02-patrol-P2-xmas02-xp1`): COMPLETE.**
- Prep 17:14: the frame judged clean at (214,113) and `chat_window.py read` standard (the log's new
  scrollbar changes nothing: locked 5.1 / open 69.1, tabs in order). The recorder 17:15:33, the
  runner (dungeon@8.7, seed 2611066) 17:15:39-17:36:25, ended by its 20-min box, the home warp typed.
- **The recorder: 1,252 frames, 1,920,691,249 bytes (after the ship), one part, no pause.**
- **The judge (packets, `dungeon_judge.py row`): hard bars PASS** (0 NPC contact, 0 attack on a
  non-monster or an unknown target, 0 other-map change; the 1 same-map change is its Fly Wing);
  0 deaths; 13 engagements (9 box, 3 walk-sword, 1 stall scan), 4 strikes (1 landed) + 6 burst
  clicks, 1 kill; 770 walk clicks (627 trusted), 143 column dodges.
- **Shipped 17:36-17:38** (re-hashed on the NAS, local deleted); root free 124.00 GB at 17:38.

**FIT's C1, a diagnostic (`check --allow-fit`, the frozen params; not T1's verdict):** under o3h-t
2 bad labels of 592 scored (0.34 %), under o3h 5 / 609 (0.82 %); C2 PASS for the four tier species
(median |dx|, |dy| 1 px).

**T1 on TEST (section 5; `map_labels.py check --c1-rule round2` on xw5 + xp1 + X2 with the frozen
params, 17:39:53-17:45:14; t1.json sha256 `5c6b3bf5d8e0116f...`): PASS.**
- **C1 pooled 7 bad of 607 scored = 1.15 %** (bar <= 5.0 % on >= 100 rows). Per species: Christmas
  Cookie 4 / 127 (3.15 %), Cruiser 2 / 181 (1.10 %), Myst Case 1 / 133 (0.75 %), Cookie 0 / 166.
  Per part: xw5 1 / 415 (0.24 %), xp1 2 / 45 (4.44 %), X2 4 / 147 (2.72 %).
- **C2 PASS for the four** (median |dx|, |dy| 1 px; Cookie dy 1.5 px). No C2 stop.
- Beside it, the same frames under o3h (not frozen): 26 / 650 = 4.0 %: the terrain rule 4f adopted
  takes most of the bad labels out (occluded_terrain 59 + under_terrain_kept 30 dropped).
- Exclusions: not_standing 1,158, frame_with_standing 559, ui_or_edge 332, crowded 194,
  under_model_kept 112, ambiguous_view 62, occluded_terrain 59, occluded_model 51, next_move 44,
  under_terrain_kept 30, unscored 16, facing_unknown 10, frame_with_notice 8.
- TEST is not read again before the evaluation (section 9).

**TRAIN by 2d / 3c (17:36-17:58; `map_labels.py labels` + `check --c1-rule round2`, the frozen
params, `--classes` an EMPTY extra list: only the MapSpec's six species count as checked in 4g's
whole-frame rule, no class decision before T2):**

| session | own C1 (3c: <= 5 % on >= 50) | C2 | boxes in whole frames: Myst Case / Cruiser / Cookie / Christmas Cookie |
|---|---|---|---|
| xw2 `20261106T151122` | 2 / 695 = 0.29 % ADMITTED | PASS x4 | 691 / 373 / 221 / 143 |
| xw3 `20261106T154241` | 0 / 307 = 0.00 % ADMITTED | PASS x4 | 260 / 197 / 82 / 104 |
| xw3 `20261106T160700` | 1 / 228 = 0.44 % ADMITTED | PASS x4 | 289 / 99 / 30 / 53 |
| **TRAIN total** | | | **1,240 / 669 / 333 / 300** |

- **2d's stopping rule is MET after xw3: every tier species has >= 300 boxes in whole TRAIN frames**
  (Christmas Cookie exactly 300). **xw4 is not recorded** (Amendment F). Garm Baby and the Goblin:
  no kept label in a whole frame; Stormy Knight (1251, OUT) showed in xw3's first session (the
  MVP's respawn after the 15:42 `@killmonster2`): its frames are `unchecked_species`, not whole.
- FIT's labels (xw1, two sessions; for T2's pool and VAL): whole-frame boxes 582 / 244 / 226 / 233.
- Next: the T2 pack (seed 51, salt xmas02, 30 per tier species) from xw1 + xw2 + xw3.

**The T2 pack (section 6; built 17:59:10-17:59:34, BEFORE any answer exists):** `map_labels.py pack`
from the five label files (xw1 x 2, xw2, xw3 x 2), seed 51, salt xmas02, the instructions file
`dc48fb15...` (Amendment C). **180 crops: 30 per tier species**, from pools of Myst Case 2,707,
Cruiser 1,277, Cookie 804, Christmas Cookie 707, **Garm Baby 38 and Christmas Goblin 88** (D3's
conditional species reached the tier: >= 30 kept labels); 9 grid pages, the multi-view reference
(9 letters). sha256: pack.json `a27af707...`, answer_key.json `bbc74039...`, reference.png
`d389551c...`. Two NEW blind labeller agents (A, B) started ~18:00, each with ONLY the pack, the
instructions and its own answers path; the key stays outside the pack. Scored by
`scripts/blind_score.py` against section 6's bars.

## 13. AMENDMENTS (clock-labelled; each committed BEFORE the step it changes)

### Amendment A (2026-11-06 11:2x ICT, committed before xw1): Batt's answers to section 0

**Batt's words** (the reply to the 09:42 report, in this session before 10:49:46, the turn's first
`date`): on the disk, "ปลดบล็อคเรื่องนี้เลย บอก HA ด้วย และฉันปรับเกณฑ์เพิ่มให้ด้วยเป็น 100gb จะได้ไม่ไปกวน
HA บ่อย" (unblock this now, tell HA too; I set the margin to 100 GB so we don't bother HA often); on
this plan, "ทำได้เลย เริ่มเทรนได้ เริ่มทำแผนเลย" (go ahead, training may start, start the plan now).

- **D0 (the disk): ANSWERED by the floor.** `dataset_ship.MIN_FREE_BYTES` = 100 GB (8b46640,
  ADR-0010 "Amendment 2026-11-06"). Root free 123.14 GB at 11:10 (`df -B1`): ~23 GB above the floor,
  ~8 x one 30-min watch's ~3 GB. HA was told at 11:1x (information only). HA's own reading (its
  message, 11:0x): ~1.28 GB/h lately, from quant's Postgres between the nightly retention runs
  (~9.3 GB back at 21:07). Nothing else changes: one recording at a time on the root disk,
  shipped and verified on the NAS, then deleted, before the next.
- **D1-D14: ADOPTED as proposed** (one model for xmas_dun02 only; the four tier species, one
  class each, collapsed for the runner; gef10 round 2's `last.pt`; no item class; immune lattice
  watches + one patrol; FIT 30 min, TRAIN 3 x 30 min by 2d's rule, TEST xw5 + xp1 + X2; 3a's split;
  4f's terrain test; E0; 1d 120 ms on a STOP; D13's training settings; D14's verdict).
- **"Training may start"** is read as: the GPU steps run when the plan reaches them (after T1, T2,
  the class list and the evaluation's own pre-registration, section 11 step 8), under R1-R3 and
  the R2 co-tenant rule. It skips none of the steps before them.

**T-5 resolved without a new driver (read 11:1x).** The watches that fed gef10 (w2) and payf07
(watch-w1) ran `stage_items.py watch` (the immune character warps over a lattice file, 30-s
dwells, typed `@warp` lines only through crusader.gm_line's name + job check, no world click)
BESIDE the 1-fps recorder (`record_session.py`, PNG, the root-disk sink): exactly 2a's protocol.
Its `CHAR` / `JOB` are the Rogue's (`thief` / `rogue`). `warp_watch.py` (its own 5-Hz JPEG
recorder) is not used. Immunity: `stage_items.py immune-on` (@monsterignore on a FRESH login, then
a person reads the frame) -> `--immune-confirmed`.

**The lattice, by a committed tool (`scripts/watch_lattice.py`, tests), its rule fixed here:**
- a stand = a stand-grid cell (client and server walkable, outside warp spans and touch areas),
  outside the zones, in the main component, with a fully walkable 5 x 5 (`--min-clear 2`);
- one stand per node of an 11-cell grid (nodes at 5 + 11 k), the nearest stand within 3 cells when
  the node is not one;
- the stands within |dx| <= 16, |dy| <= 12 of the exit warp (129,130) dropped (2a);
- TEST by 3a ((x // 26 + 3 (y // 26)) mod 5 == 0);
- all stands of both files pass the three stand-cell checks in ONE `check_warps` call.

| | stands | blocks | file sha256 |
|---|---|---|---|
| TRAIN side (xw1 FIT, xw2-xw4, xw6-xw7) | 343 | 80 | `7305384271101c45a34944ed7c453913a8e7cf1dbb84283588002b5512bb62d3` |
| TEST (xw5) | 88 | 20 | `98d3f0d4ec3b1574ba647a83cb51dbd2baa036c6418ab88f68ccd3fdaa7ef677` |
| dropped (see the warp) | 5 | | |

- From 26,386 stand cells; GAT sha256 `4cf9265fcce2fec4...`, zones `89ea7a9c...` (the 11-05
  20:16 commit changed only that file's comments).
- The plan's "~221 stands" (2a) was a scratch approximation with no snapping. At ~40 s a stand a
  30-min watch uses ~45 of them, in its own seeded order (`watch_cells`: xw1 seed 2611061 ...
  xw5 2611065), so more stands only spread the watches wider.
- The files live in `/dev/shm/poring-lab-tmp/xmas-det/lattice/` (client-derived, never
  committed); the command rebuilds them byte-identical (its sha256 above).

**The command per watch (xw1 shown; the others change only the label, seed and lattice):**

        uv run python scripts/record_session.py --backend rdp --format png --fps 1 \
            --out /home/batt/poring-lab-rec --max-bytes 3G --label xmas02-xw1     # beside, then:
        uv run python scripts/stage_items.py watch --map xmas_dun02 \
            --lattice /dev/shm/poring-lab-tmp/xmas-det/lattice/lattice-train.json \
            --seed 2611061 --label xw1 --max-minutes 30 --immune-confirmed

- Before it: the Rogue switched to (client restart onto its card), `@killmonster2` (the MVP
  cleared), `stage_items.py immune-on` + the frame read, a judged screenshot of the layout and the
  standard chat window. After it: the recorder stopped, `dataset_ship.py ship`, the NAS copy
  verified, the local copy deleted, BEFORE the next watch.
- Not in 14:00-14:45 or 09:30-10:15 on weekdays.

**The other tool gaps (T-1-T-4, T-6-T-10)** are built offline in tmpfs worktrees (at most two
subagents), each with tests and a positive case, before the FIT step reads xw1.

### Amendment B (2026-11-06 12:2x ICT, before FIT reads anything): the label tools as built (T-1, T-2, T-3, T-8, T-9; merged c8e75e9)

- **T-1:** `map_labels.session_ui_rects` takes the session's chat window (detector_vs_packets'
  helpers): sessions from 2026-11-05 12:00 get the standard window (0, 585, 600, 720) and no
  `notice_left`; older ones keep `RECTS` exactly (all 544 pre-cutover NAS session names: 1,088 /
  1,088 (sid, layout) pairs identical; gef10 w2's rects identical old vs new code).
- **T-2:** `MAPS["xmas_dun02"]` = this plan's spec (cells, the /dev/shm RSW / RSMs / sprites, the
  tier and conditional species, Stormy Knight unchecked, walkers, fit +-6, no anchor, salt
  `xmas02`, T2 seed 51, eval seed 53 / 60 per species, `dying_rule`). Roles BY NAME: FIT =
  `*-rdp-xmas02-xw1` (any session of that name), TEST = `*-rdp-xmas02-xw5`, `*-rdp-xmas02-xp1`, X2.
  offset / threshold / engaged / labels refuse a TEST part by its directory name BEFORE reading it;
  pack and the cache refuse TEST label files. Checked on X2's real path: each refused before
  reading.
- **E0 (D11) is enforced, not just defaulted:** `engaged_fixed="E0"`, so the label stack keeps
  Amendment C's `facing_unknown` and Amendment B's `crowded` flag (gef10's EngagedLabeler at E0);
  freeze writes `engaged_variant` E0 and refuses any other.
- **T-3:** `check_recording` accepts `recorder_version` 5 or 6 (X2's manifest now passes; it was
  refused).
- **T-8:** xmas_dun02's C1 always runs the pickup-notice rule (`round2`; `round1` refused). The
  notice band was measured on gef_fild10; `check` records that (`notice_band_measured_on`).
- **T-9:** `--eval-test` (labels and pack read only xw5, xp1, X2, under the FROZEN params, seed 53,
  60 per species); `eval_q1` adds Q1c / E1c beside Q1 / E1 (gef10 round 2's archived evaluation
  re-scored: every old key identical; Q1c 0.983 / 0.983 / 0.983 for its three species).
- **The labels' name is `xmas02-o3h`;** it becomes `xmas02-o3h-t` only if 4f's FIT test adopts the
  terrain occluders (T-4, the other branch), by the freeze.
- **NOT built (4h), stated before FIT:** the frame exclusions `unlabelled_item` (a floor item in
  view) and our character under Hallucination (EFST_ILLUSION). The immune watches make neither
  happen by construction: no kill, so no drop; monsters ignore us, so no skill on us. The FIT
  report counts both from the packets (floor-item appearances; EFST_ILLUSION on our unit). Any
  count above zero on a watch is reported, and **these exclusions must exist before any HUNTING
  session joins TRAIN** (3c).
- **`cookie_any` (6's fallback)** would need the cache manifest to map two species to one class
  (`eval_q1.class_map` refuses that today): built only if T2 triggers it, by its own amendment.

### Amendment C (2026-11-06 12:3x ICT, before FIT reads anything): the other tools as built (T-4, T-6, T-7, T-10; merged d31ed25)

- **T-4, the terrain candidate:** `orc_labels_fix.TerrainOccluders` exactly as 4f fixes it (a GAT
  cell >= 10 altitude units above the label's own cell, south of it, drawn from the label's floor
  to its top through `rsw.project_points`; overlap by any area). It refuses an indoor camera (yaw
  over 5 degrees: "south" no longer means "nearer the camera"). `MAPS["xmas_dun02"].terrain` is ON:
  `threshold` reports o3h AND o3h-t (o3h-t's own T_h, clear of terrain too) and 4f's adoption test
  on 4e's set (each condition reported apart; steps 5 and 20 reported); `freeze` takes the rule the
  test chose (`occlusion`, its T_h, the GAT's sha256); `check` scores both rules from one pass; the
  verdict is the frozen rule's. Every other map runs as before (the switch off).
- **The geometric share (1c) did NOT reproduce as worded.** Every other 1c count reproduced exactly
  (11,031 / 9,631 / 2,675 raised cells, 144 blocks, 14,034 raised walkable cells). "Walkable cells
  with a >= 10 block 1-4 cells south in the same column" is 6,452 / 50,702 = **12.7 %** (8.4 % with
  4f's relative rise; 12.3-19.0 % with +-1 column), not 10.9 %. With the real idle sprites and the
  camera on each cell, the boxes under terrain at step 10 are 13.9 % (Myst Case), 13.8 % (Cruiser),
  12.0 % (each cookie) of the 50,702 cells. No decision used 10.9 %; the screen share is FIT's to
  measure (4f).
- **The labels' name:** `xmas02-o3h`, and **renamed `xmas02-o3h-t` by the freeze's own amendment if
  4f adopts terrain**, before any label file is written. The params' `occlusion` field records the
  rule either way.
- **T-6:** the species -> `monster` collapse is applied in the scorer (`detector_vs_packets score /
  score-session --classes LIST`); the rows on disk keep the model's class names (species agreement
  stays readable). Positive case: gef10 round 2's 26-class output on Batt's demo collapses exactly
  to its published rows (4,666 rows, 8,488 boxes).
- **T-7:** a labelled `--val` session (xw1, D13) is written to the val split under the frozen
  params, `join_rule_3c` = `VAL_MONITOR` (no own C1, never trains); every refusal kept.
- **T-10, the T2 instructions:** `docs/planning/xmas02-blind-instructions.txt`, **sha256
  `dc48fb1582300e704ac333497d7681b051c3448a5e0d17d42f17b0322bac48ed`**; the questions, answer
  format and box drawing are gef10's. **One wording differs from section 6:** the colour pair is
  described as "dressed in pale GREEN, the other in red", not "tan vs red". The rendered reference
  shows Cookie (1265) in pale green clothes and Christmas Cookie (1246) in red, both with tan
  faces; 1b's 44° "tan" hue was the mean over all idle pixels, skin included (pixels with green >
  red: Cookie 44.4 %, Christmas Cookie 0 %). The instructions must describe what a labeller sees.
  `scripts/reference_sheet.py --preset xmas_dun02` builds the multi-view sheet (9 species, the
  pack's own letters); it was built once at seed 51 and looked at (every species rendered).
- **Open before the cache (decided in the class-list amendment after T2):** the cache's
  `SpeciesClasses` requires the fixed classes {player, npc, warp}, while section 7 lists only
  `player` + the species. Either npc / warp stay as EMPTY fixed classes (the species then start at
  id 3) or the loader takes a map-scoped fixed set. No class id is used before then.

### Amendment D (2026-11-06 14:1x ICT, committed 14:15:52, before any further recording): Batt's answer on the IO guard; pause and resume

**Batt's words** (the reply to the 13:5x summary of what waited on them, in this session after
13:58:26, the turn's first `date`): "ทำต่อเลยได้นี้ ผ่อนผันให้ ทำระบบ retry ไว้กลับมารันต่อด้วยก็ได้
ร่วมกับ หยุดเฉพาะตอนดิสก์ช้าต่อเนื่อง 30 วินาที ไม่หยุดเพราะกระตุกครั้งเดียว" (go ahead, I grant the
relaxation; a retry system that comes back and runs on is fine too, together with: stop only when
the disk is slow for 30 s straight, not for one spike). It picks option 2 of the 13:5x summary
(daytime recording with a sustained-only guard) and adds the resume.

- **The guard, for every xmas02 recording from now (the xw1 continuation, xw2-xw5, xp1):**
  `record_session.py --io-rule sustained` stops a part only on stall above 30 % for 30 s, never on
  one spike, on the root-disk sink and in SET hours too. Everything else on the disk stays: the
  100 GB floor and the 20 GB unshipped cap (the recorder refuses at a start and stops mid-part),
  one recorder at a time, and the market-open windows (09:30-10:15, 14:00-14:45 weekdays: the
  recorder itself waits them out and ends a part when one begins).
- **The resume (`--resume 6 --state-file /dev/shm/poring-lab-tmp/xmas-det/rec-state-<name>.json`):**
  a part stopped by the IO guard or a market-open window is followed by a NEW SESSION of the same
  label once the disk is calm: every capture cgroup at or under 10 % for 60 s without a break, at
  least 120 s after the stop; at most 6 resumes and 1 h of pauses in all per recording.
  `--seconds` / `--max-bytes` budget all the parts together. Any other stop (duration, size or
  local cap, a refusal, the resume or pause cap) ends the recording.
- **Each part is its own session.** The name rules (Amendment B: FIT = any `*-rdp-xmas02-xw1`, TEST
  = any `*-rdp-xmas02-xw5` / `-xp1`) take every part, and the label tool picks frames from packets
  (`map_labels.RecSession.candidate`: still, outside the GM windows, after the map change), not
  from the watch's events, so a part needs nothing from the watch.
- **The watch (stage_items.py, stage@7), `--recorder-state` = the same file:** a dwell waits until
  the recorder banks frames; after ANY wait the stand is warped to again (a map change inside the
  new part: its packets' anchor and the monsters on screen come fresh); a dwell the recorder did not
  bank whole (a pause or a new part inside it) is dwelt again, at most 3 times, else the watch
  stops; waits are outside the `--max-minutes` box; a recorder that ends, goes stale (no beat for
  10 s) or never writes its state (120 s) stops the watch.
- **The standing rule "after ONE IO abort: stop and ask"** is replaced, FOR THESE RECORDINGS ONLY,
  by this bounded resume (Batt's answer). A recording that ends on its resume or pause cap, or any
  stop of the watch other than its time box, still stops the chain and is reported to Batt.
- **xw1:** attempt 1's session (`20261106T115507-rdp-xmas02-xw1`) stays FIT by its name. It holds 6
  WHOLE dwells (stands 0-5 of seed 2611061's order; dwell 6 ended 2.4 s after the recorder
  stopped, so it is not whole), 287.8 s from the recording's start to the end of dwell 5. **The
  continuation:** the same seed and lattice, `--start-cell 6 --max-minutes 25`, so FIT holds ~30
  min of watch in all, as 2b planned.
- **`--max-bytes 5G` (was 3G):** attempt 1 wrote 121.4 MB/min, not 2b's 92.2: a 30-min part is
  ~3.6 GB, over 3G. The unshipped cap (20 GB) and the floor are what protect the disk.
- **Shipping, this afternoon:** `dataset_ship` refuses SET hours (09:30-17:00) by design, and a
  ship reads the disk at up to ~40 MB/s, ~20x the recorder's write rate. Until 17:00 the sessions
  stay on the root disk under the recorder's own caps (124.5 GB free at 13:58, `df -B1`; the
  partial xw1 0.66 GB), and from 17:00 each is shipped, verified on the NAS and deleted. This
  replaces 2b's and Amendment A's "shipped before the next" for the afternoon only; after the
  17:00 ships, each recording is shipped before the next again.
- **Not changed:** the label rule, the split, the seeds, the lattice files and their sha256, the
  stands, the protocol (immune Rogue, `@killmonster2` before each watch, a judged screenshot), the
  per-watch time box (30 min of watch), the TEST names.

**Built and tested before this commit** (record_session.py + stage_items.py; tests
`test_record_session_resume.py`, `test_stage_items_watch.py`): the market-open windows; the
sustained rule does not stop on a scripted burst like xw1's 12:00 trip (its 10-s mean 29.9 %,
over the 25 % spike line as xw1's 28.3 % was) and does stop on 30 s above 30 %; the calm wait (120 s when calm all along, 160 s when calm from 100 s,
a burst resets it, the budget and a signal end it); the parts loop (budgets left, part indices,
which stops resume, the resume cap, a refusal, h264 refused, the state file ends "ended"); the
watch on a fake clock (a pause inside stand 1's dwell -> stand 1 warped to and dwelt again in part
B, stands 0 and 2 once; a 10-min wait outside a 1-min box; `--start-cell`; a recorder that ends or
never comes stops it; without `--recorder-state` the stage@6 lines exactly).

**The commands (the xw1 continuation shown; the others change the label, seed, lattice, start cell
and time box as 2b / Amendment A say):**

        uv run python scripts/record_session.py --backend rdp --format png --fps 1 \
            --out /home/batt/poring-lab-rec --max-bytes 5G --seconds 3000 --label xmas02-xw1 \
            --io-rule sustained --resume 6 \
            --state-file /dev/shm/poring-lab-tmp/xmas-det/rec-state-xw1.json     # first, then:
        uv run python scripts/stage_items.py watch --map xmas_dun02 \
            --lattice /dev/shm/poring-lab-tmp/xmas-det/lattice/lattice-train.json \
            --seed 2611061 --label xw1b --start-cell 6 --max-minutes 25 --immune-confirmed \
            --recorder-state /dev/shm/poring-lab-tmp/xmas-det/rec-state-xw1.json
        # when the watch ends: SIGINT the recorder by its PID (it finalises the open part)

### Amendment E (2026-11-06 14:4x ICT, committed 14:46:25, before xp1 records): xp1's seed, size cap and recorder

- **The seed: `--seed 2611066`** (the watch seeds' series, 2611061-2611065, plus one). 2b's "X2's 4A
  command with `--label xmas02-xp1`" would repeat X2's `--seed 20261105`; X2 and xp1 are both
  TEST-P, so a different seed makes the second patrol a different draw of the runner's choices
  instead of the same one twice. No TRAIN or FIT data depends on it.
- **The command:** `dungeon_hunt.py run --char rogue --map xmas_dun02 --strategy P2 --search patrol
  --walk-trust --npc-guard --miss-cue --loot trim --clear-map --minutes 20 --seed 2611066 --label
  xmas02-xp1` (dungeon@8.7, the Rogue immune, the MVP cleared by `--clear-map`), the recorder
  started first: `record_session.py --backend rdp --format png --fps 1 --out
  /home/batt/poring-lab-rec --max-bytes 3G --seconds 1500 --label xmas02-xp1 --io-rule sustained
  --resume 6 --state-file /dev/shm/poring-lab-tmp/xmas-det/rec-state-xp1.json`, SIGINT by its PID
  when the runner ends.
- **`--max-bytes 3G` (2b said 2G):** at attempt 1's measured 121.4 MB/min a 20-min patrol is ~2.4 GB.
- **The runner does not wait for a recorder pause** (unlike the watch, Amendment D): frames during
  a pause are simply not in TEST. P4A and X2's 4A numbers score the recorded parts only; the report
  states the pause time.
- Recorded after the 17:00 ships (outside SET hours), shipped before the next recording.

### Amendment F (2026-11-06 15:1x ICT, before xw3 records): recording ahead of FIT, and 2d's rule in order

- Section 11 puts FIT (step 5) before xw2-xw4 (step 6). With the Windows session free this
  afternoon, **xw2 (started 15:11:21) and xw3 are recorded BEFORE FIT**. Nothing reads them before
  the freeze: FIT reads only the `*-rdp-xmas02-xw1` sessions (3b), so the order of recording changes
  no parameter.
- **2d's stopping rule is applied at labelling time, in the watches' order:** xw2 is labelled
  (frozen params) and counted first, then xw3, then xw4; TRAIN admits watches in that order until
  every tier species has >= 300 boxes in whole TRAIN frames (or 5 TRAIN watches). **A watch
  recorded beyond the stop is not admitted to TRAIN** (it stays on the NAS, unused, and the report
  says so).
- xw4 waits for xw2's and xw3's counts (2d's estimate: 2-3 TRAIN watches).


### Amendment G (2026-11-06 17:3x ICT, before any TRAIN or TEST label file is written): FIT's results and the FREEZE

FIT ran 17:12-17:27 (`map_labels.py offset` then `threshold`, CPU, nice 10, a 4 GB scope) on the two
`*-rdp-xmas02-xw1` sessions as shipped to the NAS; files in `/dev/shm/poring-lab-tmp/xmas-det/fit/`.

| step | result | file sha256 |
|---|---|---|
| 4b, 1d | **120 ms** (median 2.236 px at 120 and 130 ms; 200 samples, 53 units: Myst Case 121, Cruiser 35, Christmas Cookie 32, Cookie 12) | offset.json `54f85b2b2180eaaa...` |
| 4e, o3h's T_h | **0.418** (the p5 of 1,459 kept labels clear of every model box; p50 0.788) | threshold.json `9c46923789440dab...` |
| 4f, terrain | **ADOPTED at step 10:** n under terrain 96 (>= 30), median NCC 0.537 vs 0.794, drop **0.257** (>= 0.05), Mann-Whitney p **1.9e-18** (< 0.01); step 5 also passes (134, 0.215, 4.5e-20). **o3h-t's T_h 0.536** (its own set: 1,363 clear of terrain too) | (in threshold.json) |
| 4i | E0 (D11, fixed) | |

- Per tier species (clear kept): Myst Case 771 (p5 0.336), Cruiser 298 (0.398), Cookie 272 (0.592),
  Christmas Cookie 253 (0.536); Garm Baby and the Goblin: no fate on FIT. Under a model box (fit
  passed): 21.8 % pooled, most under `xmas_블럭성.rsm` (117) and `xmas_벨트02.rsm` (85).
- **The FREEZE (mechanical by the pre-registered rules, nothing chosen by hand):**
  `map_labels.py freeze --map xmas_dun02 --offset fit/offset.json --threshold fit/threshold.json
  --out fit/params.json` at 17:32:03, commit c17761e: **labels `xmas02-o3h-t`, status FROZEN,
  offset 120 ms, occlusion o3h-t, T_h 0.536, E0, dying_in_view on. params.json sha256
  `d4cc0a5d9e530e382e31ea9c9ae1fc1087dd31c37577b43b307eff65994fdb6e`.**
- **The rename (Amendment C):** the MapSpec's `labels` is `xmas02-o3h-t` (c17761e), and the freeze
  now REFUSES a label name and a 4f rule apart (a test each way).
- Next, in 2d's order (Amendment F): xw2's labels + its own C1 (3c) + its boxes per species; then
  xw3; T1 on TEST (xw5 + xp1 + X2) after xp1 ships; the T2 pack (seed 51).

### Amendment H (2026-11-06 18:1x ICT, before the cache): T2's result and the class list

**T2 (section 6; the pack of 17:59, two NEW blind labellers A and B, scored by `blind_score.py` against
the key `bbc74039...`; answers-A sha256 `e80cb42a68d4986583ab...`, answers-B `0e592639872e14a0af89...`):**

| species | A good / species | B good / species | verdict |
|---|---|---|---|
| Myst Case 1249 | 100 % / 100 % | 100 % / 100 % | PASS |
| Cruiser 1248 | 90.0 % / 96.7 % | 93.3 % / 96.7 % | PASS |
| Cookie 1265 | 100 % / 100 % | 100 % / 96.7 % | PASS |
| Christmas Cookie 1246 | 100 % / 100 % | 100 % / 100 % | PASS |
| Garm Baby 1515 | 83.3 % / 100 % | 73.3 % / 86.7 % | FAIL (good < 90 %) |
| Christmas Goblin 1607 | 86.7 % / 90.0 % | 83.3 % / 83.3 % | FAIL (good and species) |

- Agreement: Q1 180 / 180, Q2 166, Q3 171; 158 crops good for both with the right species.
- **The four core species pass; Cookie and Christmas Cookie are told apart** (species >= 96.7 % each
  way), so 6's `cookie_any` fallback does not apply.
- **Garm Baby and the Christmas Goblin (D3's conditional species, in the tier by >= 30 kept labels)
  FAIL: by section 6's "any other failure" rule (gef10's D4 / D5) they are NOT classes and their
  frames are excluded** (the cache's species reasons). Both labellers' "off" boxes sit in crowded
  fights (the goblins' and Garm Baby's packs, the soldiers' thrown-hat frames).
- Labeller notes, reported: A saw after answering that every species had 30 crops (the pack's
  balance can hint; future packs could hide it); A extended two notes afterwards with no label
  changed. B: Q2 has no rule for a small cut or a hidden body; both used notes.

**The class list: `config/detector/classes-xmas02.json`, sha256
`9ab96672cd9d2b822c45b87c7f903c04900e304f0466018a7bbdfcdfc4e491be`:** 0 player, 1 npc, 2 warp
(EMPTY fixed classes: `build_frame_cache.SpeciesClasses` requires player / npc / warp, Amendment C's
open question answered without a code change), **3 Myst Case 1249, 4 Cruiser 1248, 5 Cookie 1265,
6 Christmas Cookie 1246.** Section 7's ids shift by 2; the runner maps 3-6 to `monster` (T-11).

### Amendment I (2026-11-06 18:1x ICT, committed 18:18, before the worker or any GPU step): the training launch

Section 8 as written (D4, D13; Amendment A: "training may start" = when the plan reaches it, under
R1-R3 and the R2 co-tenant rule), with the inputs fixed by eval AMENDMENT 2:
- **The cache:** `xmas02-o3h-t-20261106` (the guarded `cache:` step of 18:16, sustained IO rule;
  dry run: TRAIN 1,986 frames, boxes Myst Case 1,083 / Cruiser 525 / Cookie 281 / Christmas
  Cookie 242; VAL 1,106 frames; xw2 + xw3 x 2 with `join_rule_3c` ADDED, xw1 x 2 VAL_MONITOR).
- **Init:** gef10 round 2's `last.pt`, `/mnt/poring-lab-datasets/archive/train/gef10-20261026/weights/last.pt`,
  sha256 `ebfc7a9a2475ff6117f4...` (read 18:17); the class head starts fresh (7 classes).
- **The worker:** `quiet_start.py --quiet-min 10 --limit 25 -- python3 scripts/guarded_build.py
  --sustain 30 --spike 25 worker:vision@120` once the cache has finished (quiet_start measures the
  window and never starts in a market-open window).
- **The launch:**

        WORKER=1 MID_CKPT=1 INIT_WEIGHTS=/datasets/archive/train/gef10-20261026/weights/last.pt \
          HSV_S=0.2 CLOSE_MOSAIC=3 SCALE=0.1 IO_GUARD="--threshold 30 --sustain 30" \
          IO_RESUMES=20 IO_QUIET_MIN=0 scripts/runbooks/train-day.sh xmas02-20261106 \
          xmas02-o3h-t-20261106 20 /dev/shm/poring-lab-tmp/train-xmas02 2 1

  (YOLO11n, seed 20261004, imgsz 1280, batch 2, workers 1, 20 epochs, close_mosaic 3, hsv_s 0.2,
  hsv_h 0.015 = the default, scale 0.1; the 25 % VRAM cap; the adaptive duty cycle; paired R3 with
  the absolute camera-drop stop.)
- **At 18:17 (read-only):** GPU 3,537 / 16,311 MiB used (Frigate's three detectors + ffmpeg);
  fit-first's `fitfirst-vton-worker` container up and holding NO GPU memory; Ollama `/api/ps`
  empty. The guard re-checks R1 / R2 (and the co-tenant headroom) at every start.
- **The scored checkpoint:** `last.pt` after the last COMPLETED epoch (eval doc). TEST is not read
  before the training ends. After it: `worker-stop:vision`.
