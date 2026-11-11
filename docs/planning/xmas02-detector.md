---
doc_type: design
hypothesis: "Packet labels with gef_fild10's rule (o3h with the fit floor on every label, Amendments B and C, the pickup-notice rule in C1), re-measured on xmas_dun02's own FIT data and extended by a TERRAIN occluder candidate (the map's raised GAT blocks, adopted only by a FIT test fixed here), give per-species boxes for the four common species (Myst Case, Cruiser, Cookie, Christmas Cookie) that pass the training tier (T1: C1 <= 5 % on >= 100 held-out standing rows; T2: every tier species passes a blind check), so that a detector scoped to xmas_dun02, trained on immune lattice watches, sees those species on held-out data (Q1 collapsed: recall and precision >= 0.80 per species) and boxes the runner's own patrol frames with precision >= 0.80, where v1 saw 1 of 937 labels."
status: "xmas02-gb (Amendment M, a Garm Baby class): EVALUATED 2026-11-10 06:43-06:48 -- PASSES (M11: Garm Baby Q1s on gw3 59 evaluated crops / 24 dogs, recall 1.000, precision 0.922; the four species Q1c on pooled TEST recall 0.98-1.00, precision 0.93-0.94; CPU p95 0.955 x the deployed model's). DEPLOYED 2026-11-10 ~07:0x (M12). Amendment N (Batt): teach the hidden Garm Babies first; Amendment N1 PROPOSED 2026-11-10 (the occlusion study + a plan), NOT run (N2, Batt: option (a)). Amendment O PROPOSED 2026-11-10, ➡️ ACCEPTED by O1 10:29 (a floor-item class; a separate item model recommended; NOT accepted). Trained and frozen 2026-11-10 (M8). The 4-species xmas02 model: DEPLOYED 2026-11-07 (Amendment J, Batt: use it, and train it to see monsters while walking as well as standing). Walking: Amendment K's timing did not stand (K2); back to Batt. EVALUATED 2026-11-07 00:39: the model PASSES (xmas02-eval.md). The training ran 20 epochs (2026-11-06 20:53 - 11-07 00:01). ACCEPTED 2026-11-06 ~10:45 by Batt (Amendment A); recording under Amendment D; FIT + freeze (G), T1 PASS, T2 (H), the training launch (I)."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [rogue-xmas02.md, xmas02-prep.md, gef10-detector.md, item-class.md, gef10-round3.md, xmas02-item-blind-instructions.txt, ../benchmarks/gef10-eval.md, payf07-detector.md, orcsdun01-detector.md, training-cost.md, gef10-round2-measure.md, ../../scripts/map_labels.py, ../../scripts/warp_watch.py, ../../scripts/detector_vs_packets.py, ../../scripts/recorder_boxes.py]
next_action: "O19 (2026-11-11 10:2x): round 3 FAILS -- false boxes fixed (I3 0.42 %, I4 0.9 %, precision 0.994) but recall fell (aura 0.806, no aura 0.854); natural pilot drops stay at 62 % in rounds 2-3. A round 4 (more natural drops in TRAIN, balanced fight negatives) is Batt's decision."
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
| T-11 | (deployment, later) `BoxWatch` uses `UnitDetector()`'s default v1 and `cls == "monster"` | a model per map + the species collapsed; Batt's decision, after the evaluation. ➡️ BUILT 2026-11-07 (Amendment J): `unit_detector.for_map`, species -> `monster` in ONE NMS group | dungeon_hunt.py:992-1013 |

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

**The training (Amendment I): COMPLETE, 20:53:17-00:01:51 ICT (2026-11-07), rc 0, one attempt,
all 20 epochs.** Duty cycle: 100 ms for 7,456 s, 200 ms 2,047 s, 400 ms 652 s, 800 ms 607 s,
2,000 ms 546 s (82 changes); the guard's worst capture stall 9.9 % (cron.service), 0 s above 30 %.
VAL (xw1, monitor only) at epoch 20: P 0.979, R 0.978, mAP50 0.993, mAP50-95 0.910 (1,106 frames,
2,238 boxes). The scored checkpoint, `last.pt` after epoch 20, sha256 `5c5bb67a...`; its CPU
export `xmas02-last-736x1280.onnx` `293dca92...`. The evaluation's commands:
xmas02-eval.md AMENDMENT 3 (committed before any TEST label).

**THE EVALUATION (xmas02-eval.md, scored 2026-11-07 00:39 ICT): THE MODEL PASSES.** Q1c holds for
all four tier species (evaluated / recall / precision: Myst Case 59 / 1.000 / 0.881, Cruiser 56 /
0.982 / 0.873, Cookie 60 / 0.983 / 0.881, Christmas Cookie 58 / 0.983 / 0.877) and P4A holds (X2 +
xp1 still captures 689 / 728 = 0.946; v1 0 / 63). CPU p95 270.0 ms vs v1's 272.9. Moving captures
score ~0.22 (the ~0.5 s frame lag displaces the truth). Deploying it (T-11) is Batt's decision; the
details, the double cookie boxes and G1 / G2 are in xmas02-eval.md RESULTS.

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

**The cache (Amendment I; `guarded_build.py --threshold 30 --sustain 30 cache@7200=...`,
18:16:03-18:28:44): OK.** `/mnt/poring-lab-datasets/.framecache/xmas02-o3h-t-20261106`: **3,092
frames written** (TRAIN 1,986: xw2 1,034, xw3 543 + 409; VAL 1,106: xw1 183 + 923), 14 shards
(~6.2 GB, each re-hashed from the NAS), 757.9 s; the guard's worst 4.9 % (quant-orderbook-engine),
0 s above 30 %. The vision worker was started through `quiet_start` at 18:29.

**The vision worker's start (Amendment I) ABORTED by the IO guard; the training has NOT started;
PAUSED for Batt (one IO abort: stop and ask; Amendment D covers the recordings only).**
- `quiet_start.py --quiet-min 10 --limit 25 -- guarded_build.py --sustain 30 --spike 25
  worker:vision@120` began waiting at 18:29:08. Its 10-min clock restarted at 18:32:20-23
  (cron.service 34.4-100 %, quant-orderbook-engine 99.8 %, quant-ticker-engine 99.8 %: nothing of
  ours on the local disk then; the cache had ended 18:28:44, the scratch copy RAM -> NAS ran
  18:30:16-18:30:39). Quiet from 18:32:24; it started ONCE at 18:42:24.
- `worker:vision` up at 18:42:27 (worst 0.0 % then); **18:42:37 BREACH: quant-ticker-engine 32.8 %
  (spike above 25.0 %) -> the worker stopped**; `poring-lab-vision-worker-1` Exited (143), nothing
  of ours on the GPU (read back 18:43). The worker's cold start is the known IO burst (10-09), so
  this trip is most likely ours.
- The cache, the labels, the params and the class list stand; only the GPU step waits.

**The vision worker, attempt 2 (Batt ~20:3x: "let's get back to training our bot"; option (a) of the
18:4x report: ONE retry with the same tolerant rule, nothing loosened):** `quiet_start.py
--quiet-min 10 --limit 25 -- guarded_build.py --sustain 30 --spike 25 worker:vision@120` from
20:32 (GPU 3,537 / 16,311 MiB, Frigate only; Ollama empty). A second trip stops and asks again
(options b / c).

**The worker, attempt 2: UP.** quiet_start waited 20:32:05-20:50:52 (10 quiet minutes), `worker:vision`
up 20:50:55, settled 20:52:55 (idle, no CUDA context; worst stall 4.4 % on frigate).

**THE TRAINING STARTED 20:53:17** (Amendment I's launch, verbatim; log
`/dev/shm/poring-lab-tmp/train-xmas02/`): `execdev:vision` in the worker, `poring_vision.train --cache
/datasets/.framecache/xmas02-o3h-t-20261106 --epochs 20 --batch 2 --workers 1 --name xmas02-20261106`
(init gef10 r2 `last.pt`, MID_CKPT, the sustained IO rule); R2 co-tenant rule armed (fit-first's VTON
never touched), paired R3 (180 s ON / OFF), the duty cycle 2000 ms -> 100 ms by 20:58 (fleet 26.9
det/s); 1,406 MiB on the GPU. The scored checkpoint: `last.pt` after the last completed epoch.

### Amendment J (2026-11-07 ~06:0x ICT): Batt's answers to the 00:44 report

Batt's words (Thai, translated), answering the report's to-do list:
1. **Deploy:** "Use it, and train more too: it must see monsters while walking as well as when
   standing still."
2. **GPU or CPU, 8 or 16 threads:** "Compare: how much faster would the GPU be? And raising the CPU
   to 16 threads is OK."
3. **The Windows `--bench`:** "You may run it for me." Asked at ~05:5x which Windows: the only one
   this side can reach is the lab PC, which ADR-0019 keeps clean. Batt chose the one-off on the lab
   PC (an ADR-0019 exception, logged there): uv and the kit in one temporary folder, `--bench`
   (no game input), then everything removed and checked.
4. "The students' mouse problem: no need to follow it any more, close it."

**What was built (T-11), before any live use:**
- `unit_detector.THREADS` 8 -> 16 (every UnitDetector user; recorder_boxes and the HUD keep their
  own counts).
- `unit_detector.for_map(map)` with `MAP_MODELS["xmas_dun02"]`: the ONNX by name, its sha256 pinned
  (`293dca92...`; a different file fails closed), the four species renamed `monster`.
- `detector_worker.py`'s optional NMS groups: the renamed species are suppressed TOGETHER.
  Positive case on 113 real X2 frames: 197 -> 184 monster boxes; the 13 dropped boxes all
  overlapped a higher-scored box of another species (IoU > 0.5); 0 added; 0 doubles left
  (docs/operations/detector-cpu.md "Map-scoped models").
- `dungeon_hunt.py`: `BoxWatch` takes the map's model (`--box-model map`, the default; `--box-model
  v1` = the rollback) and logs a `box_model` event.

**"See monsters while walking as well as standing": what is known, and the order of the work.**
- The P4A gap (still precision 0.946, moving ~0.22) has TWO possible causes, and the evaluation
  cannot tell them apart:
  - (a) the scorer's truth on moving captures. `detector_vs_packets` places the packet truth at
    t - 120 ms (`mvp_watch_study.OFFSET_MS`, payf07's 1d) with our walk interpolated; the frames
    lag the server by ~0.5 s while we walk (memory: frames lag the server), so the truth moves
    ahead of the sprites;
  - (b) the model itself. The label rule drops every frame where our character moved in the last
    1 s (`map_labels.py` 4f, `self_moving`): **the model never trained on a frame taken while
    walking** (scroll, codec smear while the camera moves).
- The order:
  1. **Measure first, on non-TEST sessions** (xw1 VAL, TRAIN parts): the moving captures' truth
     re-timed by a sweep of the self / camera offset. A positive case: the still captures' scores
     must not change. If the re-timed truth brings moving recall and precision to the still values,
     cause (a) is the whole gap and the model needs no new data; the scorer is fixed instead.
  2. **Otherwise a round 2:** moving frames admitted to the labels with the measured timing,
     their fit checked as 4e does on FIT, the cache rebuilt, the model retrained. Its bar (moving
     recall and precision within a fixed margin of still, on TEST) is pre-registered here before
     its cache.

### Amendment K (2026-11-07 07:0x ICT, committed 07:09:00, before any walking frame is recorded): the walking data and the timing measurement

**What 07:00 showed (xw1, FIT; the deployed model at 16 threads, `--truth-offset-ms` sweep):** xw1 holds
NO moving capture. The lattice watch moves between stands by `@warp`, and so did TRAIN (xw2, xw3).
So the round-1 model never saw a frame taken while the camera follows our walk, and no non-TEST
session on this map holds one (X2 and xp1, the walking ones, are TEST). On xw1's still captures the
global offset is best at the frozen 120 ms (P 0.978 / R 0.916) and falls as it grows (250: 0.973 /
0.907; 400: 0.930 / 0.867; 550: 0.871 / 0.811; 700: 0.795 / 0.739; 900: 0.720 / 0.669). If walking
captures need more delay, it is the CAMERA's (our own walk), not the scene's: hence
`--self-offset-ms` (faffeca; 120 reproduces the default score in every field).

**K1. New sessions, by name (the same recorder rules as Amendment D: PNG, 1 fps, rdp, the sustained
IO rule, the bounded resume, the 100 GB floor, the unshipped cap, shipped the same day):**
- **FIT-walk = any `*-rdp-xmas02-xmw1`:** the ONLY session where the walking timing is measured.
- **CHECK-walk = any `*-rdp-xmas02-xmw2`:** read once by K3's check, then TRAIN.
- **TRAIN-walk = any `*-rdp-xmas02-xmw3`** (and further `xmw<n>`, n >= 3, by this rule).
- **TEST stays X2, xp1 and xw5**, by name, untouched until a round-2 evaluation (its own
  pre-registration).
- Each is recorded beside the deployed runner on its patrol (rogue-xmas02.md's p4 command with its
  own `--label xmas02-xmw<n>`, `--minutes 20`, the Rogue immune, `--clear-map`): mostly walking,
  some fights, as the bot really plays. A runner version change between sessions does not change a
  session's role.

**K2. The timing, on xmw1 only:** the deployed model's boxes (`recorder_boxes.py predict`, 16
threads) scored by `score-session` at the frozen 120 ms for the monsters, with the camera swept:
`--self-offset-ms` 120, 240, ..., 1200 (10 values).
- **L_self** = the value with the best F1 of the MOVING captures (precision and recall pooled), the
  smaller one on a tie within 0.005.
- A by-eye check before it is used: 12 moving captures (`random.Random(71)`), the truth drawn at
  120 and at L_self. L_self stands only if its boxes sit on the sprites in at least 10 of the 12.
  Otherwise the camera is not the cause, nothing is adopted, and it goes back to Batt.

**K3. The question "does the current model already see walking monsters?", on xmw2 (CHECK) at the
frozen L_self:**
- **YES** if moving recall >= still recall - 0.10 AND moving precision >= still precision - 0.05
  (>= 100 moving detections). The gap was the scorer's timing. The detector needs no walking data,
  and the walking timing goes into the scorer.
- **NO** otherwise: a round 2 with moving frames in the labels. map_labels admits a self-moving
  frame with the camera at L_self and the same fit floor (T_h) on every label. Its cache, training
  and evaluation (moving recall and precision within those margins of still on TEST, plus no
  regression on Q1c / P4A) are pre-registered as Amendment L BEFORE its cache.

**K2 RESULT (xmw1 = `20261107T071639-rdp-xmas02-xmw1`, recorded 07:16:39-07:37:33 beside the runner,
1,251 frames, 1.94 GB, one part, 0 pauses, shipped + verified 07:39; boxes: the deployed model, 8
threads; scored 07:47). VERDICT: L_self does NOT stand (by eye 7 / 12 < 10). Per K2, nothing is
adopted and the walking question goes back to Batt.**

| camera offset (ms; monsters at 120) | moving P | moving R | moving F1 | still P | still R |
|---|---|---|---|---|---|
| 120 (every score so far) | 156 / 507 = 0.308 | 154 / 514 = 0.300 | 0.304 | 0.941 | 0.844 |
| 240 | 0.483 | 0.470 | 0.476 | 0.941 | 0.844 |
| 360 | 0.639 | 0.624 | 0.631 | 0.941 | 0.844 |
| **480 (best F1: L_self by the rule)** | **364 / 507 = 0.718** | **361 / 508 = 0.711** | **0.715** | 0.941 | 0.844 |
| 600 | 0.643 | 0.631 | 0.637 | 0.941 | 0.844 |
| 720 | 0.523 | 0.512 | 0.517 | 0.953 | 0.855 |
| 960 | 0.292 | 0.283 | 0.287 | 0.925 | 0.826 |
| 1,200 | 0.154 | 0.154 | 0.154 | 0.816 | 0.745 |

- The still captures do not change up to 600 ms (the control: the camera offset only matters
  when we move).
- **The by-eye check** (`scripts/truth_draw.py`, 12 of 374 moving captures, seed 71; red = camera at
  120, green = at 480, yellow = the detections):
  - the green truth sits on the sprite in 7 (walk-00, 01, 03, 04, 07, 08, 11);
  - it is off in 5 (02, 05, 06, 09, 10). In 05 and 06 the sprite lies BETWEEN red and green (the
    lag there is ~300 ms); in 09 even green is short of it (more than 480); in 02 and 10 green is
    one to two cells off.
- **What it means (the rule's own wording, "the camera is not the cause", is too strong):** the
  camera's timing explains a large part of the walking gap (F1 0.30 -> 0.71 by the offset alone).
  But it is not ONE constant: the lag differs from capture to capture by several hundred ms. So no
  fixed offset gives a truth good enough to label walking frames or to score them. Every walking
  number so far (P4A's moving ~0.22, xmw1's 0.30 at 120) measures this timing more than the model.
- **K3 is not run** (it needs a standing L_self). xmw2 stays CHECK-walk by name, unread.
- **Options for Batt** (the report): (a) a per-capture camera estimate instead of a constant (e.g.
  the label tool's sprite fit with a search window wide enough for the residual, ~+-2 cells around
  480, its fit floor deciding; or the frame's own minimap readout as the camera's position); (b)
  skip the truth for walking frames and judge "sees while walking" by the live runner instead
  (strikes and kills from box engagements, packets as the referee). Either is a new
  pre-registration.


### Amendment L (2026-11-07 14:2x ICT): Batt delegates the walking choice; (b) chosen
- **Batt** (answering the 13:42 report, item 4): "เอาที่เดินได้สะดวก เลือกเองได้เลย" (take
  whichever works easily for walking; choose yourself).
- **Chosen: (b)**, judge "sees while walking" by the live runner, packets as the referee, NOT by a
  per-frame truth. Why:
  - the GPU path (docs/planning/gpu-live-detector.md, live since 2026-11-07) makes detections
    cheap, so live runs already carry many walking detections with their wall times
    (`detections.jsonl`) beside the packets;
  - (a) needs a per-capture camera estimate that has not been shown to work (K2's by-eye check
    gave 7 / 12 even at the best constant);
  - the runner's own outcome (a box -> a strike -> a kill) is what Batt asked for: the bot seeing
    monsters while it walks, not a frame score.
- **(a) stays the fallback** if (b) shows that walking sight is what limits kills.
- **First step, offline, folded into the "no hits" study of p7 + p8** (rogue-xmas02.md section 5,
  Batt "ได้" 2026-11-07): for monsters within reach in the packets while we walked, did the box
  watcher box them before we stopped, and which of those boxes became strikes and kills. Its
  measures and bars are pre-registered before it is read; no live run and no training follow
  until then.

### Amendment M (2026-11-09 ~21:0x ICT, written BEFORE any of its data): a Garm Baby class -- "Fly Wing when a Garm Baby is SEEN" (Batt)

**Batt's words** (2026-11-09, rogue-xmas02.md 4AY + after the p43 death): "fly wing when see garm
baby i[mmediately]", then "Go ahead with (c), including the immune spawns" (option (c) of the 20:4x
report: a Garm Baby class in this detector, so the runner flies when one comes INTO VIEW, not after
the Battle Log names it on contact; the data spawns Garm Babies near the IMMUNE Rogue).

- **Why the class failed before (Amendment H):** T2 good-box 83.3 % / 73.3 % (< 90 %), species 100
  / 86.7 %; the off boxes sat in crowded fights (packs). D3 also expected it rare (38 kept labels).
- **The new data (immune lattice watches, section 2a's protocol, with a SPAWN):** `stage_items.py
  watch --map xmas_dun02 --spawn 1515 --spawn-n 2 --dwell-s 40 --max-cells 16 --immune-confirmed`,
  each beside `record_session.py --backend rdp --fps 1 --format png` (PNG: a pre-registered
  detector study), the Rogue immune (judged on the Chat tab), `@killmonster2` after each dwell:
  - **gw1, gw2 (DEV = TRAIN):** `lattice-train.json` (3a's non-TEST stands), seeds 2611091 /
    2611092;
  - **gw3 (HELD-OUT = TEST):** 3a's TEST stands MINUS the 16 R2-W used (`lattice-test.json` minus
    stormy-knight-recognizer.md 8's cells: 72 stands), seed 2611093. Not read before the model is
    frozen.
  - Two dogs a stand, alone (the watch kills everything else between stands): the uncrowded frames
    T2 lacked. Safety: the Rogue is immune throughout (monsters ignore her); no world click.
- **The label rule, the frame exclusions, T1 / T2:** as section 4 / 5 / 6 froze them ("xmas02-o3h-t"),
  with 1515 IN the tier. **T2 again for Garm Baby** on a new blind pack from gw1 + gw2 (two NEW
  labellers, section 6's rule: good >= 90 % and species >= 95 % each); the four species are not
  re-checked (they passed).
- **If T2 passes:** classes-xmas02 gains `7 Garm Baby 1515` (a new file sha256, recorded); the cache
  = Amendment I's TRAIN + gw1 + gw2 (VAL xw1 as before); the training recipe as Amendment I, the
  class head fresh, 20 epochs (its exact launch committed in an amendment BEFORE the GPU step).
- **The bars (the held-out score, once):** Q1 for Garm Baby on gw3's standing frames: recall >= 0.80
  and precision >= 0.80 (section 9's Q1 rule); the four species keep Q1 on xw5 (>= 0.80 each); CPU
  p95 <= 300 ms. Then deployment and the runner's "seen -> Fly Wing" (rogue-xmas02.md, its own
  pre-registration and pilot).
- **If T2 fails:** the class is not trained; reported to Batt.

#### M1 (2026-11-09 21:3x ICT, before any labeller): gw1 / gw2 labels and the T2 pack

**How (a subagent, branch `feat/garm-class`, offline, CPU, a 4 GB scope without swap, nice 15):** the
worktree's sources with the main venv; the FROZEN params `d4cc0a5d...` (Amendment G) and the 11-06
inputs in /dev/shm (RSW + 37 RSMs, sprites, kb-sprites, the GAT); `map_labels.py labels` with
`classes-none.json` and `check --c1-rule round2` per session, exactly as TRAIN was labelled (11-06
`run-train.sh`). The tool commit is `a6abad45`: this amendment in the MapSpec (gw3's NAME refused like
TEST by labels / pack / the cache; Garm Baby in T2's tier whatever its pool; the Goblin keeps D3's
>= 30), with tests. Nothing in the label rule changed. (gw1's `labels` run started at 21:10 on
9e4a0e70's code; a6abad45 landed during it, and its file records `a6abad45`, the HEAD when it was
written: the label code is the same in both. gw1's C1, gw2 and both packs ran on a6abad45.)

**Positive case first:** xw3's second session (`20261106T160700-rdp-xmas02-xw3`, NAS) re-labelled on
bot-server gives **678 / 678 frames identical** to its 11-06 label file (counts and drops identical;
only `commit` and `labelled_at` differ). The frozen rule runs unchanged on this host.

**The sessions:** both manifests pass 3c's path (rdp, png, recorder v7, [80, 77, 1280, 720],
lab-rathena); 16 stands each of `lattice-train.json` (`73053842...`, Amendment A), none TEST by 3a;
2 dogs spawned per stand (`@monster 1515 2`), `@killmonster2` after each 40-s dwell.

| | gw1 | gw2 |
|---|---|---|
| recording / watch | `20261109T205355-rdp-gb-gw1` (924 frames, 1.86 GB, 732 packet events) / `20261109T205405-watch-xmas_dun02-gw1`, seed 2611091 | `20261109T210933-rdp-gb-gw2` (901, 1.95 GB, 852) / `20261109T210944-watch-xmas_dun02-gw2`, seed 2611092 |
| candidates (drops) | 758 (gm_window 113, map_change 40, other_map 13) | 749 (gm_window 107, map_change 45) |
| whole frames (frame exclusions) | 340 (dying_in_view 4) | 368 (dying_in_view 2) |
| frames the cache's rule writes (whole, no `weak_fit`) | 287 | 298 |
| kept (in whole frames): Myst Case / Cruiser / Cookie / Christmas Cookie | 232 (135) / 121 (33) / 55 (28) / 73 (23) | 167 (77) / 220 (118) / 159 (78) / 124 (92) |
| **kept Garm Baby (in whole frames)** | **771 (468)**; 714 pass the T_h floor | **836 (521)**; 762 pass the T_h floor |
| Garm Baby boxes in the frames the cache writes | 370 | 391 |
| Garm Baby excluded | occluded_model 171, occluded_terrain 144, ambiguous_view 71, unfit 46, next_move 26, crowd 8, facing_unknown 3 | occluded_model 173, occluded_terrain 80, ambiguous_view 57, unfit 35, next_move 28, ui 5, crowd 2 |
| Christmas Goblin | 0 | 0 |
| **own C1 (3c: <= 5 % on >= 50)** | **22 / 354 = 6.21 %: NOT ADMITTED** | **18 / 423 = 4.26 %: ADMITTED** |
| C1 Garm Baby / the four others | 22 / 213 = 10.3 % / 0 / 141 | 18 / 218 = 8.3 % / 0 / 205 |
| C2 (median abs dx, dy) | PASS x 5; Garm Baby n 213, 1 / 1 px | PASS x 5; Garm Baby n 218, 1 / 1 px |
| label file / own-C1 sha256 | `412ed242...` / `cf4b0c86...` | `f152ede6...` / `2e007e28...` |

**What looked wrong, and what was checked (packets, label files and the C1 rows only; no frame opened;
the check script, its outputs and the positive case's label file: NAS
`scratch-archive/2026-11-09/garm-m1/`, sha256-checked):**
1. **The bad C1 rows are Garm Baby FACING misses, not position misses.** Among the Garm Baby rows clear
   of models and terrain, by the gap between fix 2's predicted heading (`after_move`) and the best of
   the 8 headings at the predicted spot: 2-3 steps, bad in 21 of 23 (gw1) and 14 of 16 (gw2); 0-1
   step, bad in 0 of 134 (gw1) and 4 of 157 (gw2). In gw1's bad rows the best-of-8 NCC at the same
   spot is 0.23-0.70, against a prediction under tau (0.092).
   It hits 7 (gw1) and 8 (gw2) of 26 scored dog units, in runs of 1-4 frames at one cell. Of gw1's 44
   bad rows over both rules: 22 occluded_terrain and 18 unfit in the labels, 4 kept (one at NCC 0.725;
   three at 0.094-0.117, below T_h, so the cache drops their frames as `weak_fit`). Why the standing
   dogs face otherwise than their last step is NOT investigated here.
2. **The T_h floor is not in the label files.** They keep every label that passes tau; T_h ("the floor on
   EVERY kept label", 4a) is applied by the cache (`map_frame`, `weak_fit`) and by `pack --min-fit`. The
   11-06 pack ran without `--min-fit` (key `min_fit` null; the eval doc's "the T_h floor is part of the
   rule, so the pack takes no --min-fit" took the floor to be in the files). In the 11-06 key, Garm Baby
   had 10 of 30 crops below T_h, the Goblin 15, Cruiser 2, Christmas Cookie 1. On the floor-passing
   crops Garm Baby was good 19 / 20 and 18 / 20, species 20 / 20 for both (sub-floor: good 6 / 10 and
   4 / 10); the Goblin 15 / 15 everything (sub-floor: good 11 / 15 and 10 / 15). **Recorded only:
   Amendment H's verdict stands, and nothing is re-scored.**
3. **Our own character:** the dogs spawned 1-3 cells from the stand (gw1 1 / 2 / 3 cells: 1 / 15 / 16;
   gw2 5 / 10 / 17), never on our cell. Kept dog labels on our cell: gw1 0, gw2 2. No kept dog box lies
   >= 0.5 under our own `player` box (labels_v2.self_label; gw1 32 under 0.25 and 6 under 0.5, gw2 40
   and 8).
4. **The GM windows:** the spawned dogs' appear packets carry `gm_command`, so each spawn opens its own
   2-s window, beside the `@warp`, `@monster` and `@killmonster2` lines.
5. **The @killmonster2 gaps:** the candidate frames from a stand's kill to the next warp (gw1 85, gw2
   66) hold respawned common monsters only (24 and 22 kept labels), no dog. All 32 spawned dogs of each
   session have kept labels. gw2's packet anchor (70 s before its t0) carries gw1's last two dogs:
   packets only, no frame.

**So 3c admits gw2 and not gw1.** Section 3b's T2 pool is "the TRAIN sessions admitted when the pack is
built", while this amendment names gw1 + gw2; with point 2, the pack's sources and its floor are the
parent's to fix before any labeller. **Two candidate packs were built (21:33:38-21:34:09), BEFORE any
answer exists; ONE goes to the labellers, by an amendment; the other is deleted unseen.**

| candidate | sources | floor | crops | pools: Myst Case / Cruiser / Cookie / Christmas Cookie / Garm Baby | answer_key.json sha256 | pack file list sha256 |
|---|---|---|---|---|---|---|
| `gw2-floor` | gw2 (3c) | `--min-fit 0.536` (4a, as the cache writes) | 150 | 161 / 197 / 153 / 116 / 762 | `c1050420fe41258ab183aa4b2469f2881148ba1d3e0e86184fb7690f298d1cd7` | `b5eeab68...` |
| `gw12-asbuilt` | gw1 + gw2 (this amendment) | none (the 11-06 command) | 150 | 399 / 341 / 214 / 197 / 1,607 | `1c2f960214f15d0a3dfc64103c2e7da21b9f0ac965c1eeb40bde0f070edc20d3` | `e04abd66...` |

- Both: `map_labels.py pack --map xmas_dun02 --seed 51` (salt xmas02), 30 per species, tier [1249, 1248,
  1265, 1246, 1515], 8 grids; the instructions `docs/planning/xmas02-blind-instructions.txt`, **sha256
  `dc48fb1582300e704ac333497d7681b051c3448a5e0d17d42f17b0322bac48ed`** (T2's, unchanged); the
  multi-view reference, **`d389551c9bf5f463d1954e777a934f4f1a432548427aca977fb991d4fa71b310`,
  byte-identical to the 11-06 pack's** (the same 9 species and seed: letters A-I as then); pack.json
  `b59f4c4f3e13184aa937ee888442740339a78e5ea09f556c10f3345a069f0b14`.
- `gw12-asbuilt` drew no sub-floor Garm Baby crop (8 sub-floor crops among the others: Cruiser 5,
  Myst Case, Cookie and Christmas Cookie 1 each). Its Garm Baby crops: 15 gw1 + 15 gw2.
- Not built: gw1 + gw2 with the floor (one command, if the parent admits gw1 by an amendment).
- Where (client pixels, /dev/shm, never committed): `/dev/shm/poring-lab-tmp/gb/t2/<candidate>/{pack,
  key}`. The labellers' sha256-checked copy is `/dev/shm/poring-lab-tmp/blind-gb51-<candidate>/pack`,
  their answers `.../answers/{E,F}.json`; the key never lies under it.
- **The labellers:** two NEW blind agents, E and F (A, B: T2 of 11-06; C, D: the evaluation), each with
  the pack, its instructions and its own answers path only. **The verdict:** `blind_score.py`,
  section 6's bars for Garm Baby (1515) alone: good >= 90 % AND species >= 95 % from EACH labeller; the
  four common species are reported and decide nothing (this amendment).

#### M2 (2026-11-09 ~21:4x ICT, the parent, BEFORE any labeller): the choices M1 asked for

- **gw1 is NOT admitted.** 3c's join rule binds as written (own C1 <= 5 % on >= 50 rows): gw1
  6.21 % fails, gw2 4.26 % passes. Changing the rule after seeing the number would be post-hoc, so
  gw1 is outside T2's pool and outside TRAIN. Amendment M's "TRAIN + gw1 + gw2" becomes **TRAIN =
  Amendment I's TRAIN + gw2** (391 Garm Baby boxes in written frames). If the trained model falls
  short, more data comes from a NEW watch under 3c, never from gw1.
- **The T2 pack is `gw2-floor`** (gw2 only, `--min-fit 0.536`, 4a's floor, as the cache writes):
  T2 checks exactly the labels that train (M1 point 2: the 11-06 pack ran without the floor).
  Its answer key sha256 c1050420fe41258ab183aa4b2469f2881148ba1d3e0e86184fb7690f298d1cd7, pack.json
  b59f4c4f3e13184a..., the instructions dc48fb15... (T2's, unchanged), the reference d389551c...
- The other candidate (`gw12-asbuilt`) is deleted unseen.
- **T2's verdict** = `species_pass["1515"]` of blind_score.py over labellers E and F (both NEW):
  good >= 0.90 and species >= 0.95 each, on the 30 Garm Baby crops.

#### M3 (2026-11-09 21:45 ICT): T2 for Garm Baby -- PASS

Labellers E and F (both NEW, blind: the pack only), answers sha256 E fe4d2fad... / F 2a123a74...,
scored by `blind_score.py` against the key c1050420... at 21:45:10 (the pack `gw2-floor`, M2):

| species | E good / species | F good / species | verdict |
|---|---|---|---|
| **Garm Baby 1515** | **100 % / 100 %** | **100 % / 100 %** | **PASS** (>= 90 / >= 95 each) |
| Myst Case 1249 / Cookie 1265 / Christmas Cookie 1246 | 100 / 100 | 100 / 100 | reported |
| Cruiser 1248 | 100 / 100 | 96.7 / 100 (one "off": 095, a hat thrown above the box) | reported |

- Agreement q1 150 / 150, q2 149, q3 150; 149 crops good for both with the right species.
- Amendment H's failure (73-83 % good in crowded packs) does not recur on the uncrowded, spawned
  dogs. **Garm Baby becomes a class** (Amendment M): the class file, the cache (Amendment I's TRAIN
  + gw2) and the training launch follow, each committed before its step.

#### M4 (2026-11-09 21:5x ICT, before the cache's dry run): the class file

- **`config/detector/classes-xmas02-gb.json`, sha256
  `dd1d3f31e7e56a434c12c7c5a9640f29167cea1ed748c49c5b3303488b134be9`** = `classes-xmas02.json` plus
  **7 Garm Baby 1515**: 0 player, 1 npc, 2 warp (EMPTY fixed classes, as Amendment H), 3 Myst Case
  1249, 4 Cruiser 1248, 5 Cookie 1265, 6 Christmas Cookie 1246, **7 Garm Baby 1515**. Checked with
  the cache's own loader (`build_frame_cache.SpeciesClasses.load` + `names`, data/kb): player, npc,
  warp, mystcase, cruiser, cookie, cookie_xmas, garm_baby. The first seven ids and names are the
  deployed model's (Amendment I / eval AMENDMENT 3's `.names.json`), in the same order.
- **`classes-xmas02.json` is unchanged** (sha256 `9ab96672...`, Amendment H): the deployed model,
  its ONNX and its evaluation keep it.
- **The Christmas Goblin 1607 stays out** (T2 failed, Amendment H): a frame holding one stays
  excluded (`species_unlisted:1607`).
- **The old sessions' Garm Baby frames (Amendment I's TRAIN xw2 + xw3 x 2 and VAL xw1 x 2):** their
  11-06 label files are used UNCHANGED (each byte-identical to the sha256 the 11-06 cache manifest
  recorded, checked 21:5x; the own-C1 files too). Garm Baby was always in the MapSpec's `species`
  (D3's conditional tier), so the label pass fitted it and kept or excluded its labels exactly as
  the four others'; the 11-06 CACHE then refused every frame holding one as `species_unlisted:1515`
  (xw3 36 + 29 frames; xw2 and xw1 none), not as `unchecked_species` (that is the label pass's own
  frame exclusion for a species outside the MapSpec: Stormy Knight 1251's 30 frames, which stay
  out). With 1515 a class, such a frame is WRITTEN when it is whole by the unchanged rule (no
  excluded label of any species, no frame exclusion, every kept label clear of the models at or
  above the T_h floor 0.536, our own character placed), and its Garm Baby boxes train as class 7.
  Nothing in the label rule changes; the counts are the dry run's (M5).
- Context, recorded only: those old labels were never checked by a T2 that passed. M1 point 2
  found that on the 11-06 T2 key's floor-passing Garm Baby crops (drawn from these TRAIN sessions)
  both 11-06 labellers were good 19 / 20 and 18 / 20, species 20 / 20; the cache writes only
  floor-passing labels in whole frames. M3's PASS is on gw2's labels.

#### M5 (2026-11-09 21:5x ICT, before the cache step): the cache -- the dry run, and the command

**The inputs:** Amendment I's TRAIN (xw2 + xw3 x 2) and VAL (xw1 x 2) with their 11-06 label and own-C1
files unchanged (M4), plus **gw2** (`20261109T210933-rdp-gb-gw2`, M1's label file `f152ede6...` and
own C1 `2e007e28...` = ADDED; M2). gw1 is NOT in it (M2). gw3 (the held-out) is not named to any
command: map_labels' MapSpec refuses `-rdp-gb-gw3` by name like TEST (M1, `a6abad45`), and the cache
refuses a TEST part. The frozen params `d4cc0a5d...` (Amendment G); the class list M4's
(`dd1d3f31...`). Why the list is passed from `/dev/shm/poring-lab-tmp/gb/m5/classes-xmas02-gb.json`:
the guarded `cache:` step runs the MAIN checkout's builder and admits only relative paths (main has
no M4 until the parent merges) or absolute paths below `/dev/shm/poring-lab-tmp/`; that copy is
byte-identical to the committed file (sha256 `dd1d3f31...`, read 21:53), and the manifest records
the list's sha256.

**The dry run (21:53:15-21:53:25; main's `build_frame_cache.py`, the code the guarded step runs, with
the arguments below + `--dry-run`, nice 15, a 4 GB scope; its output
`/dev/shm/poring-lab-tmp/gb/m5/cache-dry.json`, sha256 `c183e121...`):** every TRAIN session
`join_rule_3c` ADDED (`would_refuse_3c` empty), VAL `VAL_MONITOR`.

| session | split | frames considered | frames written | boxes: Myst Case / Cruiser / Cookie / Christmas Cookie / **Garm Baby** | est. shards |
|---|---|---|---|---|---|
| xw2 `20261106T151122` | train | 1,589 | 1,034 (= 11-06) | 621 / 312 / 194 / 115 / **0** | 5 |
| xw3 `20261106T154241` | train | 932 | 543 (= 11-06) | 224 / 137 / 60 / 78 / **0** | 2 |
| xw3 `20261106T160700` | train | 678 | **416** (11-06: 409) | 259 / 83 / 27 / 49 / **7** | 2 |
| **gw2** `20261109T210933` | train | 749 | **298** | 66 / 95 / 63 / 68 / **391** (in 224 frames) | 2 |
| **TRAIN** | | 3,948 | **2,291** (11-06: 1,986) | **1,170 / 627 / 344 / 310 / 398** (Garm Baby in 231 frames) | 11 (~4.85 GB) |
| xw1 `20261106T115507` + `20261106T144500` | val | 1,628 | 1,106 (= 11-06) | 511 / 205 / 206 / 210 / **0** | 5 (~2.35 GB) |

(+ one `player` box per written frame: our own character.) gw2's 298 frames and 391 Garm Baby boxes
equal M1's count of what the cache's rule writes.

- **The old sessions' Garm Baby frames (M4), by the dry run:** of the 11-06 cache's 36 + 29 frames
  refused as `species_unlisted:1515` (both xw3 sessions), **7 are written now** (xw3 `160700`: 7
  Garm Baby boxes in 7 frames, which also bring 21 Myst Case and 7 Cruiser boxes); the other 58
  stay out for their own exclusions (a Garm Baby label excluded: `occluded_terrain`, `weak_fit`,
  `occluded_model`, `ambiguous_view`, `next_move`, `crowd`; or a Christmas Goblin
  `species_unlisted:1607`, 32 frames in xw3 `154241`; or Stormy Knight's `unchecked_species:1251`,
  30). xw2 and VAL hold no Garm Baby label in a written frame.
- **VAL holds no Garm Baby box**, so the trainer's VAL monitor reports no `garm_baby` AP. VAL
  decides nothing (D13); Garm Baby is judged only by the held-out score (Amendment M's bars).

**The cache step (exactly Amendment I's form; from the main checkout):**

    cd /home/bot/docker/poring-lab
    F=/dev/shm/poring-lab-tmp/xmas-det/fit; G=/dev/shm/poring-lab-tmp/gb/m1
    python3 scripts/guarded_build.py --threshold 30 --sustain 30 "cache@7200=--labels map --classes species \
      --class-list /dev/shm/poring-lab-tmp/gb/m5/classes-xmas02-gb.json --kb data/kb \
      --map-params $F/params.json --map-params-sha256 d4cc0a5d9e530e382e31ea9c9ae1fc1087dd31c37577b43b307eff65994fdb6e \
      --map-labels $F/labels/20261106T151122-rdp-xmas02-xw2.json $F/labels/20261106T154241-rdp-xmas02-xw3.json \
        $F/labels/20261106T160700-rdp-xmas02-xw3.json $G/labels/20261109T210933-rdp-gb-gw2.json \
        $F/labels/20261106T115507-rdp-xmas02-xw1.json $F/labels/20261106T144500-rdp-xmas02-xw1.json \
      --own-c1 $F/own-c1/20261106T151122-rdp-xmas02-xw2.json $F/own-c1/20261106T154241-rdp-xmas02-xw3.json \
        $F/own-c1/20261106T160700-rdp-xmas02-xw3.json $G/own-c1/20261109T210933-rdp-gb-gw2.json \
      --train 20261106T151122-rdp-xmas02-xw2 20261106T154241-rdp-xmas02-xw3 20261106T160700-rdp-xmas02-xw3 \
        20261109T210933-rdp-gb-gw2 \
      --val 20261106T115507-rdp-xmas02-xw1 20261106T144500-rdp-xmas02-xw1 \
      --cache-id xmas02-gb-o3h-t-20261109 --image png"

- Output: **`/mnt/poring-lab-datasets/.framecache/xmas02-gb-o3h-t-20261109`** (the builder's
  `--cache-id`; no `--link-cache`, D1). The sustained IO rule as Amendment I (on this dedicated host
  the guard watches no capture service: ADR-0022). A refusal or an abort stops here and is
  reported; nothing is loosened.
- The written counts must equal the dry run's (TRAIN 2,291, VAL 1,106, the boxes above); a
  difference stops before any GPU step.

**The cache (M5's command, 21:54:55-22:10:23 ICT): OK.**
`/mnt/poring-lab-datasets/.framecache/xmas02-gb-o3h-t-20261109`: **3,397 frames written** (TRAIN 2,291:
xw2 1,034, xw3 543 + 416, gw2 298; VAL 1,106: xw1 183 + 923), 16 shards (7.20 GB), 926.1 s; the
guard watched no capture service (dedicated host), 0 s above 30 %. **Every session's counts equal
the dry run's** (frames, boxes and frames per class id, exclusions by reason, `join_rule_3c`):
TRAIN boxes Myst Case 1,170 / Cruiser 627 / Cookie 344 / Christmas Cookie 310 / **Garm Baby 398**.
The manifest's names: player, npc, warp, mystcase, cruiser, cookie, cookie_xmas, **garm_baby**; its
class list sha256 `dd1d3f31...` (M4's); `manifest.json` sha256 `6a030c3353b51104600109d7cca81b79feb15bd08c891b1196a3816ffc21d239`.
Two shards re-hashed from the NAS match the manifest (`shard-000004`, `shard-000010`: gw2's).

#### M6 (2026-11-09 22:11 ICT, committed BEFORE the worker or any GPU step): the training launch

Amendment I's recipe on the M5 cache, with the init, the data-loader workers and the launch path
this host needs; each difference and its reason below.

- **The settings:** YOLO11n (the init's own architecture), imgsz 1280, seed 20261004 (train.py's
  default), **batch 2**, **20 epochs**, close_mosaic 3, hsv_s 0.2, hsv_h 0.015 (the default),
  scale 0.1, `--mid-ckpt` (MID_CKPT=1: `weights/mid.pt` every 640 batches or 300 s, the exact
  resume). The Arc path (ADR-0022): `PORING_ACCEL=xpu`, **FP32** (`accel.amp_ok()` is False: the A380
  has no float64, bot-server-migration.md 15), **`--workers 2`** (= train.py's
  `DEFAULT_WORKERS["xpu"]`, 17b: 1.36 vs 1.86 s an iteration; passed explicitly), the worker's
  11g memory cap and VRAM fraction 1.0 (the Intel overlay). 2,291 TRAIN frames = 1,146 batches an
  epoch; VAL 1,106 frames (monitor only, D13).
- **The init: the deployed xmas02 `last.pt`**, `/datasets/archive/train/xmas02-20261106/weights/last.pt`
  (NAS `archive/train/xmas02-20261106`), sha256
  `5c5bb67a746b42014935700f449ecbf45525bbddf250fb21738eb6248a2b8b7b` (read 21:4x; eval AMENDMENT 3's).
  **Why this one, and not gef10 r2's:** the same map, and 1,986 of the 2,291 TRAIN frames are the
  frames it was trained on; and **the code transfers a head of a different size**: ultralytics
  8.4.165 (vision's pin) builds the model from the checkpoint's YAML with nc = 8 (the cache's
  names) and loads every tensor whose shape matches. The Detect head's class-branch width
  `c3 = max(ch[0], min(nc, 100))` is 64 for nc 7 and 8, so only the class-output convolutions
  differ, and ultralytics' `cls_remap` (its default True; train.py does not set it;
  labels-v2-plan.md 4) copies their rows **by name**. So player, npc, warp, mystcase, cruiser,
  cookie and cookie_xmas start from the deployed model's rows, and **garm_baby's row starts
  fresh**. The training log's transfer and remap lines are recorded below as the check.
  - **Amendment M said "the class head fresh".** With this code, that holds for the new class only:
    the seven old rows are seeded by name. The same rule ran on 11-06 (gef10 r2's player / npc / warp
    rows seeded Amendment I's 7-class head, which Amendment I also called "fresh"). An all-fresh head
    needs a train.py change (no flag exists today); not made here.
- **The launch path: the guarded `execdev:` step that `train-day.sh` builds, WITHOUT its two duty
  arguments; not `train-day.sh` itself.** Why:
  - `train-day.sh` always adds `--step-sleep-ms 2000 --duty-file /lab-duty/duty.json`. On this host
    (dedicated-intel) guarded_build runs no duty cycle (`gpu_guards`: "R1-R3, the co-tenant watch
    and the duty cycle do not apply here (ADR-0022)"), so nothing writes `state/train-duty/duty.json`.
    The file there is VM 103's last one (`t_epoch` 2026-11-07 00:01 ICT), older than train.py's 120 s,
    so `read_duty` falls back to the slowest level: **2,000 ms of sleep after EVERY batch**, ~38 min
    an epoch, ~12.7 h over 20 epochs, beyond the step's 12-h limit.
  - Dropping the two arguments is exactly "the duty cycle does not apply here"; nothing else of the
    command changes. The IO guard stays as the runbook sets it (`--threshold 30 --sustain 30`; on
    this host it watches no capture service).
  - What is lost: train-day's resume loop. Here R2 / R3 do not run and the IO guard has nothing to
    trip on, so the only stops are the 12-h limit, a crash, or a person: then the resume below, by
    hand. Fixing train-day.sh (skip the duty arguments on a dedicated host) is a code change for
    later, reported, not made here.
- **The commands (from the main checkout):**

        cd /home/bot/docker/poring-lab
        python3 scripts/guarded_build.py worker:vision@120          # the worker; a dedicated host: no quiet_start window to measure
        python3 scripts/guarded_build.py --threshold 30 --sustain 30 \
          "execdev:vision@43200=python -m poring_vision.train --cache /datasets/.framecache/xmas02-gb-o3h-t-20261109 --epochs 20 --batch 2 --workers 2 --name xmas02-gb-20261109 --mid-ckpt --weights /datasets/archive/train/xmas02-20261106/weights/last.pt --hsv-s 0.2 --close-mosaic 3 --scale 0.1"

  The second runs detached (`systemd-run --user`, unit `poring-train-xmas02gb`) through
  `/dev/shm/poring-lab-tmp/gb/m6/launch.sh`; its guard output goes to
  `/dev/shm/poring-lab-tmp/gb/m6/train-guarded.out`, the trainer's own output to
  `/dev/shm/poring-lab-tmp/poring-guarded-execdev-vision.log`; the run's files to
  `data/train/xmas02-gb-20261109/` (`results.csv`, `weights/{last,mid}.pt`).
  - **A resume, if it stops early** (the same run, the exact mid-epoch resume; no `--weights` or
    augmentation flags, as train-day's `--resume`):

        python3 scripts/guarded_build.py --threshold 30 --sustain 30 \
          "execdev:vision@43200=python -m poring_vision.train --cache /datasets/.framecache/xmas02-gb-o3h-t-20261109 --epochs 20 --batch 2 --workers 2 --name xmas02-gb-20261109 --mid-ckpt --resume"

- **The scored checkpoint:** `data/train/xmas02-gb-20261109/weights/last.pt` after the LAST
  COMPLETED epoch (if it ends early: that epoch's, and why). Never `best.pt` or `mid.pt`. gw3, xw5,
  xp1 and X2 are not read before the training ends and its sha256 is recorded.
- **While it runs:** the worker is busy (one job at a time), so the live detector's GPU path (the
  detect server) cannot run beside it; no pilot runs (the brief). The parent stops the worker after
  the post-training GPU steps.

**After the training (the parent; the held-out score ONCE, Amendment M's bars UNCHANGED).**
Variables (bot-server):

      W=/home/bot/docker/poring-lab; F=/dev/shm/poring-lab-tmp/xmas-det/fit
      T=/dev/shm/poring-lab-tmp/xmas-det/eval-gb; E=$W/data/train/eval/xmas02gb   # /data/train/eval/xmas02gb in the worker
      M=/dev/shm/poring-lab-detector/model; N=/mnt/poring-lab-datasets
      A7=$N/scratch-archive/2026-11-07/xmas02-eval; A7E=$N/archive/train/eval/xmas02   # 11-07's evaluation inputs
      CAP="systemd-run --user --scope -q -p MemoryMax=4G -p MemorySwapMax=0"
      GB="python3 scripts/guarded_build.py --threshold 30 --sustain 30"

0. **The end:** `train-guarded.out` ends `execdev:vision: OK`, `results.csv` has 20 rows; the
   `last.pt` sha256 is recorded in an amendment (here or the eval doc) BEFORE any TEST or gw3 read.
1. **The ONNX export** (the deployed model's recipe: detector-cpu.md, eval AMENDMENT 3; a TEMPORARY
   RAM env, ~1.5 GB: `df -h /dev/shm` first, the lab's total <= 4 GB; removed after):

        bash $A7/onnx-export/build.sh       # /dev/shm/poring-lab-tmp/onnx-export: uv venv 3.12, torch cpu, ultralytics==8.4.165, onnx, onnxslim, onnxruntime
        X=/dev/shm/poring-lab-tmp/onnx-export; cp $W/data/train/xmas02-gb-20261109/weights/last.pt $X/xmas02gb-last.pt
        cd $X && .venv/bin/python -c "from ultralytics import YOLO; import json, shutil; m = YOLO('xmas02gb-last.pt'); \
            json.dump([m.names[i] for i in sorted(m.names)], open('xmas02gb-last-736x1280.names.json', 'w')); \
            shutil.move(m.export(format='onnx', imgsz=(736, 1280), simplify=True, device='cpu'), 'xmas02gb-last-736x1280.onnx')"
        mv $X/xmas02gb-last-736x1280.onnx $X/xmas02gb-last-736x1280.names.json $M/ && sha256sum $M/xmas02gb-last-736x1280.*
        rm -rf $X

   The names must read player, npc, warp, mystcase, cruiser, cookie, cookie_xmas, garm_baby.
2. **Garm Baby on gw3's standing frames: Q1 recall >= 0.80 AND precision >= 0.80** (section 9's
   rule: >= 50 evaluated crops, two NEW blind labellers, a crop evaluated when both say yes / good /
   the label's species). **Three things the parent fixes in an amendment BEFORE gw3 is read:**
   - **a tool gap:** `MapSpec.eval_suffixes` (xmas_dun02) lacks `-rdp-gb-gw3`, so `--eval-test`
     refuses gw3 today (it is refused everywhere else, as it must be). Add `XMAS02_GW3` to
     `eval_suffixes` with a test; merged before the labels;
   - **the pack's floor:** `--min-fit 0.536` or none (M1 point 2: the T_h floor is not in the label
     files; M2 took it for T2 "to check what trains"; 11-07's evaluation pack ran without it);
   - **which field decides for Garm Baby:** section 9's verdict Q1c COLLAPSES the classes (a Garm
     Baby boxed as any monster class counts); the runner's "Fly Wing when a Garm Baby is SEEN" needs
     the class to be garm_baby (Q1s, classes agreeing). Amendment M wrote "section 9's Q1 rule".

        $CAP nice -n 19 uv run python scripts/map_labels.py labels --map xmas_dun02 --eval-test \
            $N/20261109T212445-rdp-gb-gw3 --params $F/params.json --classes $F/classes-none.json \
            --out $T/labels-test/20261109T212445-rdp-gb-gw3.json
        $CAP nice -n 10 uv run python scripts/map_labels.py pack --map xmas_dun02 --eval-test \
            $T/labels-test/20261109T212445-rdp-gb-gw3.json --per-species 60 --seed 53 [--min-fit 0.536] \
            --pack-dir $T/pack-gw3 --key-dir $T/key-gw3 --instructions docs/planning/xmas02-blind-instructions.txt \
            --instructions-sha256 dc48fb1582300e704ac333497d7681b051c3448a5e0d17d42f17b0322bac48ed
        # two NEW blind labeller agents (G, H): the pack, its instructions, their own answers path only
        $CAP uv run python scripts/eval_q1.py refs $T/key-gw3/answer_key.json --out $E/q1-refs-gw3.json \
            --labels-dir $T/labels-test
        $GB "execdev:vision@1800=python -m poring_vision.predict_dir --weights /data/train/xmas02-gb-20261109/weights/last.pt \
            --refs /data/train/eval/xmas02gb/q1-refs-gw3.json --out /data/train/eval/xmas02gb/q1-pred-gw3.json"
        uv run python scripts/eval_q1.py score $T/key-gw3/answer_key.json $T/answers-gw3/G.json $T/answers-gw3/H.json \
            $E/q1-pred-gw3.json --cache-manifest $N/.framecache/xmas02-gb-o3h-t-20261109/manifest.json \
            --out $E/q1-score-gw3.json
        # Garm Baby's row: Q1c.per_species.garm_baby and Q1.per_species.garm_baby (the field the amendment names)

3. **The four species keep Q1 on xw5 (>= 0.80 each):** 11-07's TEST labels, pack key
   (`fc9facb1...`), labellers C / D (`01808a2b...` / `9c3817ba...`) and refs (`q1-refs.json`
   `c640936a...`) are reused AS THEY ARE (archived on the NAS; nothing re-labelled or re-asked), only
   the predictions are new:

        mkdir -p $T $E && cp $A7/eval/key/answer_key.json $T/key-1107.json && cp $A7/blind-eval53/answers/C.json \
            $A7/blind-eval53/answers/D.json $T/ && cp $A7E/q1-refs.json $A7E/latency-200-refs.json $E/
        sha256sum $T/key-1107.json $T/C.json $T/D.json $E/q1-refs.json $E/latency-200-refs.json   # = the values above / d89ec7eb...
        $GB "execdev:vision@1800=python -m poring_vision.predict_dir --weights /data/train/xmas02-gb-20261109/weights/last.pt \
            --refs /data/train/eval/xmas02gb/q1-refs.json --out /data/train/eval/xmas02gb/q1-pred-test.json"
        uv run python scripts/eval_q1.py score $T/key-1107.json $T/C.json $T/D.json $E/q1-pred-test.json \
            --cache-manifest $N/.framecache/xmas02-gb-o3h-t-20261109/manifest.json --out $E/q1-score-test.json

   **For the parent to fix before the score:** on 11-07, xw5 ALONE had 41 / 45 / 51 / 25 evaluated
   crops (Myst Case / Cruiser / Cookie / Christmas Cookie: `Q1c.split_session`), so section 9's
   >= 50 minimum leaves a bar for Cookie only there; the pooled TEST Q1c (xw5 + xp1 + X2: 59 / 56 /
   60 / 58) has all four, as the deployed model's verdict did (recall 0.98-1.00, precision
   0.873-0.881). Which one "Q1 on xw5" means is the parent's reading, recorded before the score.
4. **CPU p95 <= 300 ms** (the 200 refs, interleaved, nice 10, UnitDetector's 16 threads; the
   deployed model beside it):

        nice -n 10 uv run python scripts/eval_latency.py $E/latency-200-refs.json \
            --model xmas02=$M/xmas02-last-736x1280.onnx --model xmas02gb=$M/xmas02gb-last-736x1280.onnx \
            --out $E/latency-cpu.json

5. Then `python3 scripts/guarded_build.py worker-stop:vision` (verified), the results in
   xmas02-eval.md, and the run archived (`guarded_build.py archive:` to
   `archive/train/xmas02-gb-20261109`). Deployment and the runner's "seen -> Fly Wing" follow their
   own pre-registration (Amendment M).

**M6, as run (22:11-22:39 ICT; the training continues):**
- `worker:vision@120`: up 22:11:38, settled 22:13:38 (idle, nothing on the GPU).
- The training: unit `poring-train-xmas02gb` (systemd-run --user) started 22:14:03; the guard printed
  "host profile dedicated-intel is DEDICATED: R1-R3, the co-tenant watch and the duty cycle do not
  apply here" and ran M6's command unchanged.
- **The init, checked in the trainer's log:** `Overriding model.yaml nc=7 with nc=8`, **`Remapped 7/8
  cls head rows from pretrained weights by class name`**, `Transferred 499/499 items from pretrained
  weights` (garm_baby's row is the one not remapped). `amp=False` (FP32), `Using 2 dataloader
  workers`, `Using 2291 train, 1106 val images`. The optimizer: ultralytics' `optimizer=auto` (as in
  Amendment I's run: neither run set it) chose AdamW lr 0.000833, momentum 0.9 (its rule for a short
  schedule).
- **Epoch 1 completed at 22:38:3x: 1,410.8 s** (~1.0 iteration a second over 1,146 batches, plus the
  VAL pass and the mid-epoch checkpoints); GPU memory 2.1 GB. VAL (monitor only, D13; no Garm Baby in
  it): P 0.976, R 0.984, mAP50 0.992, mAP50-95 0.904. **At that pace the 20 epochs end ~06:0x ICT
  2026-11-10** (~7.8 h; inside the step's 12-h limit, which falls at ~10:14).

#### M7 (2026-11-09 ~22:4x ICT, the parent, while the training runs and BEFORE gw3 or TEST is read): the evaluation's open points (M6 "what looked wrong")

1. **The tool gap closed:** `MapSpec.eval_suffixes` (xmas_dun02) gains `-rdp-gb-gw3`, so
   `--eval-test` may label / pack gw3 with TEST (code + test in this commit). Nothing reads gw3
   before last.pt's sha256 is recorded (M6 step 0).
2. **gw3's pack floor:** `--min-fit 0.536` (4a's floor, as M2 chose for T2: the label rule's
   trusted boxes).
3. **Garm Baby is scored SPECIES-STRICT (Q1s: the box's class must be garm_baby):** the runner
   flies on a Garm Baby box, so a dog boxed as another species is a miss. Bars unchanged: recall
   >= 0.80 and precision >= 0.80 on >= 50 evaluated crops.
4. **The four common species keep section 9's verdict (Q1c), on POOLED TEST** (xw5 + xp1 + X2, as
   on 2026-11-07, where each had >= 50 evaluated crops; xw5 alone had 41 / 45 / 51 / 25): 11-07's
   key fc9facb1, answers C / D and refs reused, only the predictions new. Bars unchanged (>= 0.80).
5. **The class head as run:** 7 of the 8 class rows were seeded by name from the deployed model;
   only garm_baby started fresh (M6; the 11-06 run did the same from gef10 r2). Amendment M's
   "the class head fresh" is read as this; no restart.
6. **Recorded, not changed tonight:** `train-day.sh` passes a duty file that nothing writes on a
   dedicated host (a stale VM 103 file -> a 2-s sleep after every batch); M6 launched through
   execdev instead. A fix (skip the duty arguments on dedicated hosts) is its own change.
7. VAL (xw1) holds no Garm Baby, so the training's monitor says nothing about it; the held-out
   score decides.

#### M8 (2026-11-10 06:13 ICT, BEFORE any TEST or gw3 read): the training ended; THE SCORED MODEL FROZEN

- `train ended rc=0` at 06:11:34 ICT (started 2026-11-09 22:14:03): all 20 epochs, 28,642 s,
  FP32 on the Arc A380 (torch 2.15.0+xpu), peak 2,190 MiB, no step sleep; the guard's worst stall
  0.0 %.
- VAL (xw1 x 2, monitor only; NO Garm Baby in it) at epoch 20: P 0.983, R 0.984, mAP50 0.993,
  mAP50-95 0.922; AP50 player 0.995, mystcase 0.9947, cruiser 0.9883, cookie 0.9937, cookie_xmas
  0.9939.
- **The scored checkpoint:** `data/train/xmas02-gb-20261109/weights/last.pt` after epoch 20,
  **sha256 `85fb37a4cb606aad4636d605f9a2056dde6431a42559e052b1036aaac5f98d6b`** (5,534,234 bytes).
  Nothing is refitted after this line. Next: M6's steps 1-5 (the ONNX export, the evaluation once
  under M7, the worker stopped, the run archived).

#### M9 (2026-11-10 06:1x-06:3x ICT): the evaluation, part A (the export, gw3's labels and pack; before any labeller and any prediction)

**How (a subagent, branch `feat/garm-eval` from `a6043fad`, offline, CPU, a 4 GB scope without swap):**
the worktree's sources with the main venv (M1's way), the frozen params `d4cc0a5d...` (Amendment G)
and the 11-06 inputs in /dev/shm; gitignored local data linked read-only from the main checkout
(`data/kb`, and `packages/poring_dataset/src/poring_dataset/_generated`, the generated map cache:
`mapcache.load` checks every file against the committed lock). No GPU, no guarded step, no
prediction, no score. The model was re-hashed first: `last.pt` sha256 `85fb37a4...` (M8), 5,534,234
bytes.

**1. The ONNX export (M6 step 1, the deployed model's recipe):**
- The temporary env: the archived `$A7/onnx-export/build.sh` (sha256
  `0b1db27cc873a853071b6bd8ed91f9ffab6cb531b329be361732006c7ae3e2d2`, run from a byte-identical
  copy), 06:16:57-06:17:08, 1.5 GB in `/dev/shm/poring-lab-tmp/onnx-export` (the lab's /dev/shm
  1.9 GB at its peak): torch 2.15.0+cpu, ultralytics 8.4.165, onnx 1.23.2, onnxslim 0.1.99,
  onnxruntime 1.31.1. **Removed at 06:18** (the lab's /dev/shm back to 0.41 GB).
- The export: M6's Python unchanged (as a file), 06:17:37-06:17:44, `imgsz=(736, 1280)`,
  `simplify=True`, `device='cpu'`; opset 18; input `images` [1, 3, 736, 1280], output `output0`
  [1, 12, 19320] (4 + 8 classes); the ONNX's own metadata names the 8 classes, imgsz [736, 1280].
  The deployed model's export has the same producer (pytorch 2.15.0), opset and ultralytics.
- **`/dev/shm/poring-lab-detector/model/xmas02gb-last-736x1280.onnx`, sha256
  `b22d972b714f1461250710221802667c2c980af6299afd0e54c1778fdc53ce37`** (10,828,684 bytes), and
  **`xmas02gb-last-736x1280.names.json`, sha256
  `1c400d92fdd5df005243a1f7314aef759a21b2cf6cd80a33c09b96ff69582079`**: player, npc, warp,
  mystcase, cruiser, cookie, cookie_xmas, garm_baby (the class file's order, M4).
- The deployed `xmas02-last-736x1280.onnx` (`293dca92...`) and its `.names.json` (`af86aacc...`)
  are unchanged, re-hashed after the move; nothing else in the folder changed.

**2. gw3's labels (M6 step 2, M7 point 1; the frozen rule, as the 11-07 TEST labels were made):**
- The recording `$N/20261109T212445-rdp-gb-gw3`: its `checksums.sha256` verified on the NAS
  (06:18:45-06:19:23: 8 shards + packets OK); 916 frames, 932 packet events, rdp / png / recorder
  v7 / [80, 77, 1280, 720] / lab-rathena. The watch (`20261109T212455-watch-xmas_dun02-gw3`,
  events sha256 `77c722d4...`; not read by the label tool): seed 2611093, 16 stands of
  `lattice-test-gb.json` (`22c337b4...`), 16 spawns of `1515 x 2`, 16 dwells of 40 s, 16
  `@killmonster2`, `run_end: done`.
- `map_labels.py labels --map xmas_dun02 --eval-test` with `--params $F/params.json` (FROZEN
  `d4cc0a5d...`) and `--classes $F/classes-none.json` (`516cf0f5...`, the TRAIN and 11-07 TEST
  labels' file), nice 19, 06:20:01-06:25:22 (commit `a6043fad`, M7's `eval_suffixes`).
  A first call at 06:19:33 stopped while opening the session, before any frame was labelled: the
  worktree had no generated map cache (gitignored); linked read-only from the main checkout, rerun.
- **The label file: `/dev/shm/poring-lab-tmp/gb/eval/labels-test/20261109T212445-rdp-gb-gw3.json`,
  sha256 `662056b27b73dcc312c04e2229992da3b4f982881fdbde0d6678739a248bef79`**, `eval_test: true`.
  Candidates 759 of 916 (drops: gm_window 118, map_change 39); whole frames 394 (frame
  exclusions: dying_in_view 3).

| species | kept (in whole frames) | pass the T_h floor (the pack's pool) | units | under a model | excluded |
|---|---|---|---|---|---|
| Myst Case 1249 | 359 (192) | 347 | 11 | 53 | occluded_model 24, ambiguous_view 14, occluded_terrain 14, next_move 7, unfit 5, facing_unknown 2, ui 2, crowd 1 |
| Cruiser 1248 | 236 (116) | 205 | 13 | 26 | occluded_terrain 31, occluded_model 12, ambiguous_view 9, facing_unknown 9, next_move 3, unfit 1 |
| Cookie 1265 | 164 (84) | 157 | 5 | 48 | occluded_terrain 20, ambiguous_view 14, occluded_model 14, facing_unknown 8, next_move 4, unfit 3, crowd 1 |
| Christmas Cookie 1246 | 76 (39) | 73 | 4 | 28 | ambiguous_view 7, unfit 4, next_move 3, occluded_model 2 |
| **Garm Baby 1515** | **899 (566)** | **796** | **32 (all 32 spawned dogs)** | 136 | occluded_model 134, occluded_terrain 68, ambiguous_view 61, unfit 39, next_move 18, crowd 7, ui 1 |
| Christmas Goblin 1607 | 0 | 0 | 0 | 0 | - |

**3. The evaluation pack (M6 step 2, M7 point 2: `--min-fit 0.536`; the 11-07 pack's shape):**

    E=/dev/shm/poring-lab-tmp/gb/eval   # the brief's location (M6 named $T/pack-gw3, $T/key-gw3)
    map_labels.py pack --map xmas_dun02 --eval-test $E/labels-test/20261109T212445-rdp-gb-gw3.json \
        --per-species 60 --seed 53 --min-fit 0.536 --pack-dir $E/pack --key-dir $E/key \
        --instructions docs/planning/xmas02-blind-instructions.txt \
        --instructions-sha256 dc48fb1582300e704ac333497d7681b051c3448a5e0d17d42f17b0322bac48ed \
        --out $E/pack-build.json          # --out: required (11-07 found the same); M6 left it out

- Built 06:25:52-06:26:22 (nice 15; `/dev/shm/poring-lab-tmp/gb/eval/build_pack.sh`): **300 crops,
  15 grids**, salt xmas02. The tool's evaluation draw takes EVERY species with a kept label (as on
  11-07), so all five drew 60: pools Myst Case 347, Cruiser 205, Cookie 157, Christmas Cookie 73,
  **Garm Baby 796** (after the floor: weak_fit removed 12 / 31 / 7 / 3 / **103**).
- **Garm Baby's 60 crops: 25 of the 32 dogs** (1 crop: 9 dogs, 2: 6, 3: 5, 4: 3, 5: 1, 7: 1), 58
  frames, 9 under a model, fit 0.541-0.772 (median 0.629). The others: Myst Case 10 units, Cruiser
  11, Cookie 5, Christmas Cookie 4. 261 distinct frames in all.
- **The four common species' gw3 crops are reported and decide nothing**: their verdict is pooled
  TEST with 11-07's pack (M7 point 4). **Garm Baby's verdict is the scorer's `Q1` (the classes
  agreeing: Q1s), `per_species.garm_baby`** (M7 point 3): >= 50 evaluated crops, recall >= 0.80
  AND precision >= 0.80. Q1c for Garm Baby is reported beside it.
- **sha256 (recorded here BEFORE any labeller sees the pack):**
  - the instructions `instructions.txt` = `docs/planning/xmas02-blind-instructions.txt`:
    **`dc48fb1582300e704ac333497d7681b051c3448a5e0d17d42f17b0322bac48ed`** (T2's and the 11-07
    evaluation's, byte-identical; checked by the tool);
  - `reference.png` **`2cae63ada9b143397a8c4e147a7707b0ee48d0c46b55f3787914a66db134d4aa`**,
    byte-identical to the 11-07 evaluation pack's (the same 9 species and seed 53; the key's
    letters equal 11-07's);
  - `pack.json` `cdf9202f18d2303514704a30ec5a8ec81b71c94401e63dc5490a0ca7c4dc6590`;
  - **the answer key `$E/key/answer_key.json`
    `99f2acc70a7380931de81675e8a3010c8b6334aa7b296fccc8bbf080d0638891`** (min_fit 0.536, seed 53,
    eval_test, params `d4cc0a5d...`, its one source = the label file above);
  - the pack's file list `$E/pack-files.sha256` (318 files)
    `3030eb8ac4708a9be61726a29e64710ca3d9ca6d9d0e48531e3d5f760952556c`; `pack-build.json`
    `73088dcc...`.
- **The labellers' copy: `/dev/shm/poring-lab-tmp/blind-gb53-gw3/pack`**, sha256-checked against
  the file list (318 / 318), with an EMPTY `answers/` beside it. The key lives only under
  `$E/key`, never under the labellers' directory.

**4. The labellers: two NEW blind agents, G and H** (A, B: T2 of 11-06; C, D: the 11-07 evaluation;
E, F: T2 of Garm Baby, M3). Each gets ONLY its brief below (G's sha256 `b681753d...`, H's
`e855e350...`; the two differ only in the letter and the answers path): the pack, its instructions,
its own answers path. Never the key, the model, packets, labels, this document or the other
labeller. G's brief, verbatim (H: `H` for `G` in the first line and in `answers/H.json`):

    You are BLIND LABELLER G for a poring-lab blind label check. You work
    ALONE. Another labeller judges the same pack separately; you never see its work and it never sees
    yours.

    YOUR INPUTS (and nothing else):
    - The pack directory PACK = /dev/shm/poring-lab-tmp/blind-gb53-gw3/pack
      (reference.png, grids/grid_NN.png, crops/NNN.png, pack.json, instructions.txt).
    - Its instructions: PACK/instructions.txt. Read it FIRST, in full, and follow it exactly. It
      defines the three questions, the answer values and the answer format.

    YOUR OUTPUT (the only file you write):
    - ANSWERS = /dev/shm/poring-lab-tmp/blind-gb53-gw3/answers/G.json
      A JSON list with ONE object per crop listed in PACK/pack.json, EVERY crop, in the format the
      instructions give: {"crop": "001", "q1": ..., "q2": ..., "q3": ..., "note": ...}.

    HOW:
    - Look at PACK/reference.png first (the letters A-I, several views each). Then judge every crop:
      use the grids for an overview and open PACK/crops/NNN.png whenever a tile is too small to judge
      the box or the species. Judge each crop on its own pixels against reference.png.
    - When you cannot tell, answer "unsure" and say why in "note". Do not guess to fill a value.
    - Before you finish: re-read ANSWERS, check it parses as JSON, has exactly one object per crop
      in pack.json (no crop missing, none twice), and uses only the values the instructions allow.

    STRICTLY FORBIDDEN (the check is only valid if you see nothing but the pack):
    - Opening, listing or reading ANY path outside PACK, except writing your own ANSWERS file. In
      particular: no other directory under /dev/shm (no answer key, no labels, no other pack, no
      other answers file), no repository file or document, no NAS path, no model or detector
      output, no packet capture, no recording, no web search.
    - Writing anywhere but ANSWERS; changing or deleting anything in PACK.
    - Inferring the species from file names, crop numbers or their order (they carry no class
      information).
    - Running any program on the pack beyond viewing the images and reading pack.json /
      instructions.txt (no scripts, no image analysis tools, no model).
    - Contacting the other labeller or any other agent.

    SAFETY (poring-lab, CLAUDE.md rules 1-10, inherited): no docker or docker compose of any kind, no
    guarded steps, no GPU jobs, no game, Windows, GUI or input actions, no git commits, no filesystem
    walks (find, du, rg, tree, ls -R, recursive grep), no bulk reads of large files. Scratch, if you
    need any at all, goes nowhere: you need none.

    WHEN DONE: reply with (1) the ANSWERS path, (2) the number of crops answered, (3) counts of q1
    yes / no / unsure, q2 good / loose / off / n/a, q3 per letter + none / unsure, (4) any crop you
    found hard, by number, with one line each. Do not report anything about the key, the model or
    the other labeller (you have not seen them).

**5. Part B (after BOTH labellers; scored ONCE; M6 steps 2-4 under M7, the paths above).**
Variables (bot-server):

      W=/home/bot/docker/poring-lab; G=/dev/shm/poring-lab-tmp/gb/eval; B=/dev/shm/poring-lab-tmp/blind-gb53-gw3
      E=$W/data/train/eval/xmas02gb        # /data/train/eval/xmas02gb in the worker
      M=/dev/shm/poring-lab-detector/model; N=/mnt/poring-lab-datasets
      A7=$N/scratch-archive/2026-11-07/xmas02-eval; A7E=$N/archive/train/eval/xmas02
      WT=/dev/shm/poring-lab-wt/garm-eval
      PP="env PYTHONDONTWRITEBYTECODE=1 TMPDIR=/dev/shm/poring-lab-tmp OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH=$WT/scripts:$WT/packages/poring_env/src:$WT/packages/poring_dataset/src:$WT/packages/poring_packets/src:$WT/services/backend/src $W/.venv/bin/python"
      CAP="systemd-run --user --scope -q -p MemoryMax=4G -p MemorySwapMax=0"
      GB="python3 scripts/guarded_build.py --threshold 30 --sustain 30"   # from $W

- **B0, the inputs fixed before any score:** both answer files hashed; the labellers' pack
  unchanged; the key, the model and the reused 11-07 files re-hashed:

        sha256sum $B/answers/G.json $B/answers/H.json
        ( cd $B/pack && sha256sum -c --quiet $G/pack-files.sha256 ) && echo pack-unchanged
        sha256sum $G/key/answer_key.json $W/data/train/xmas02-gb-20261109/weights/last.pt  # 99f2acc7... / 85fb37a4...
        mkdir -p $E $G/test1107 && cp $A7/eval/key/answer_key.json $G/test1107/key-1107.json \
            && cp $A7/blind-eval53/answers/C.json $A7/blind-eval53/answers/D.json $G/test1107/ \
            && cp $A7E/q1-refs.json $A7E/latency-200-refs.json $E/
        sha256sum $G/test1107/key-1107.json $G/test1107/C.json $G/test1107/D.json $E/q1-refs.json $E/latency-200-refs.json
        # = fc9facb1... / 01808a2b... / 9c3817ba... / c640936a... / d89ec7eb... (read 06:2x: all five match on the NAS)

- **B1, gw3's refs** (the pack's 261 frames, read in place from the NAS; no latency draw: the
  latency keeps 11-07's 200 TEST frames):

        $CAP nice -n 15 $PP $WT/scripts/eval_q1.py refs $G/key/answer_key.json --out $E/q1-refs-gw3.json --labels-dir $G/labels-test

- **B2, the detections** (the worker; imgsz 1280, conf 0.25 = predict_dir's defaults):

        cd $W && $GB "execdev:vision@1800=python -m poring_vision.predict_dir --weights /data/train/xmas02-gb-20261109/weights/last.pt \
            --refs /data/train/eval/xmas02gb/q1-refs-gw3.json --out /data/train/eval/xmas02gb/q1-pred-gw3.json"
        cd $W && $GB "execdev:vision@1800=python -m poring_vision.predict_dir --weights /data/train/xmas02-gb-20261109/weights/last.pt \
            --refs /data/train/eval/xmas02gb/q1-refs.json --out /data/train/eval/xmas02gb/q1-pred-test.json"

- **B3, the scores, once each:**

        $CAP nice -n 15 $PP $WT/scripts/eval_q1.py score $G/key/answer_key.json $B/answers/G.json $B/answers/H.json \
            $E/q1-pred-gw3.json --cache-manifest $N/.framecache/xmas02-gb-o3h-t-20261109/manifest.json --out $E/q1-score-gw3.json
        # VERDICT Garm Baby (M7 3): Q1.per_species.garm_baby -- evaluated >= 50, recall >= 0.80 AND precision >= 0.80 ("pass")
        $CAP nice -n 15 $PP $WT/scripts/eval_q1.py score $G/test1107/key-1107.json $G/test1107/C.json $G/test1107/D.json \
            $E/q1-pred-test.json --cache-manifest $N/.framecache/xmas02-gb-o3h-t-20261109/manifest.json --out $E/q1-score-test.json
        # VERDICT the four species (M7 4): Q1c.per_species.{mystcase,cruiser,cookie,cookie_xmas} on pooled TEST, each >= 0.80 / >= 0.80

- **B4, CPU latency** (the 200 TEST frames, interleaved, UnitDetector's 16 threads; eval_latency
  sets nice 10 itself, so it is NOT started under a higher nice; the deployed model beside it):

        $CAP $PP $WT/scripts/eval_latency.py $E/latency-200-refs.json \
            --model xmas02=$M/xmas02-last-736x1280.onnx --model xmas02gb=$M/xmas02gb-last-736x1280.onnx --out $E/latency-cpu.json
        # bar (Amendment M): ms.xmas02gb.p95 <= 300

- Then M6 step 5 (the parent): `worker-stop:vision` (verified), the results here and in
  xmas02-eval.md (`xmas02-gb`), the run archived.

**What looked wrong, or needs the parent before part B (recorded; nothing changed):**
1. **The pack holds 300 crops, not 240:** the evaluation draw takes every species with a kept label,
   so gw3's four common species add 240 crops that decide nothing (point 3). It follows the tool
   and M6's command; it costs labeller time only.
2. **Garm Baby's crops are 60 views of 25 dogs** (one dog 7 times): the bar counts crops, as for
   every species before (the common species are 4-13 units on gw3 too), so the 60 are not 60
   independent dogs. Recorded only.
3. **The latency bar is new to this host:** 11-07's 270 ms p95 was measured on VM 103 at 8
   threads; here UnitDetector runs 16 threads on the Xeon E5-2609 v4, and
   cpu-detector-speed.md has one 16-thread p95 of the deployed xmas02 at 338.6 ms under load 14-23.
   Amendment M's bar is absolute (p95 <= 300 ms); B4 measures the deployed model beside it, and the
   report should give the load average. Whether a failure with the deployed model also above 300 ms
   reads as "the host, not the model" is the parent's to fix BEFORE B4, if at all.
4. gw3's own C1 was not run (not in M6 / M7); the blind check is what guards the labels scored.

#### M10 (2026-11-10 ~06:4x ICT, the parent, BEFORE any labeller, prediction or latency run): part A's open points

- **(a) The pack's 300 crops:** gw3's four common species (240 crops) are labelled too (the tool's
  evaluation draw); their gw3 numbers are REPORTED only -- their verdict stays M7 point 4's (pooled
  TEST, 11-07's labels).
- **(b) Garm Baby's 60 crops from 25 dogs (one dog 7 times):** the bar counts crops as section 9
  always has; the dog count is reported beside it.
- **(c) THE LATENCY BAR, made relative to this host:** Amendment M's "CPU p95 <= 300 ms" came from
  VM 103 (8 threads, 270 ms p95 on 2026-11-07); on bot-server (Xeon E5-2609 v4, 16 threads) the
  DEPLOYED model already measured 338.6 ms p95 under load (cpu-detector-speed.md), so an absolute
  300 would judge the host, not the model. **The bar: in B4's one run (both models, the same
  refs, interleaved as eval_latency does), the new model's CPU p95 <= 1.10 x the deployed model's;
  the absolute p95s and the load average are reported.** (The runner's live path is the GPU detect
  server, D1 p95 ~23 ms; the CPU detector is its fallback.)
- No other change: the Garm Baby bar (Q1s on gw3, >= 50 evaluated, recall and precision >= 0.80)
  and the four species' (Q1c on pooled TEST, >= 0.80) stand as M7 wrote them.

#### M11 (2026-11-10 06:40-06:50 ICT): THE RESULT (the held-out score, once) -- THE xmas02-gb MODEL PASSES

M9 section 5's commands B0-B4, each run ONCE, under M7 and M10's bars, by the subagent of M9 (worktree
`feat/garm-eval` at `d273cda0`). The labellers' answers were scored as given.

**B0, the inputs (06:40:54, before any score):** labellers G and H (both NEW, blind: the pack only),
300 answers each, sha256 **G `42c6bae192f36fd422e0012b42551418d81647b171dc2a299c50e4c5d7a65130`**,
**H `76dd98596bac3f283c99a9d13da64714316fb0d1e6583bc584b6c00a1fa13bba`**. The labellers' pack
matched its file list (318 / 318), so it was unchanged. The key `99f2acc7...` and `last.pt` `85fb37a4...` were
re-hashed. 11-07's key `fc9facb1...`, answers C `01808a2b...` / D `9c3817ba...`, refs `c640936a...`
and latency refs `d89ec7eb...` were copied from the NAS and all five matched.

**B1-B2, the refs and the detections:** gw3's refs, 261 frames (every image signature and tar member
name verified), `q1-refs-gw3.json` `0144eab7...`. Two guarded `execdev:vision` steps in the worker
(imgsz 1280, conf 0.25; the dedicated host: no capture service to watch, worst stall 0.0 %):
gw3 06:41:18-06:42:24, 261 frames, `q1-pred-gw3.json` `1613c8ea...`; TEST 06:42:29-06:43:31, 231
frames, `q1-pred-test.json` `39e7da4d...`. Each step ended "worker up and idle, nothing of ours on
the GPU". The worker was left running (the parent stops it).

**B3-B4, the scores (06:43:38-06:43:39) and the latency (06:44:25-06:48:35):**

| bar | measured | rule | verdict |
|---|---|---|---|
| **Garm Baby on gw3, Q1s** (the box's class garm_baby; M7 point 3) | **59 evaluated crops of 24 dogs** (of 60 crops / 25 dogs in the pack); **recall 59 / 59 = 1.000; precision 59 / 64 = 0.922** | >= 50 evaluated; recall >= 0.80 AND precision >= 0.80 | **PASS** |
| (beside it) Garm Baby on gw3, Q1c (classes collapsed) | 59 evaluated, recall 1.000, precision 59 / 68 = 0.868 (`precision_own_boxes` 0.908) | reported | - |
| **Myst Case, pooled TEST, Q1c** (M7 point 4; 11-07's key / C / D) | 59 evaluated, recall 1.000, precision 59 / 63 = 0.937 | >= 50; >= 0.80 / >= 0.80 | **PASS** |
| **Cruiser, pooled TEST, Q1c** | 56, recall 55 / 56 = 0.982, precision 55 / 59 = 0.932 | same | **PASS** |
| **Cookie, pooled TEST, Q1c** | 60, recall 1.000, precision 60 / 64 = 0.938 | same | **PASS** |
| **Christmas Cookie, pooled TEST, Q1c** | 58, recall 1.000, precision 58 / 62 = 0.935 | same | **PASS** |
| **CPU latency** (M10 (c): one run, both models, the same 200 TEST refs, interleaved, UnitDetector 16 threads, nice 10) | **xmas02gb p95 734.6 ms; deployed xmas02 p95 769.3 ms; ratio 0.955** (p50 557.9 / 548.8; max 909.7 / 920.9; boxes 533 / 540; 249.1 s) | new p95 <= 1.10 x the deployed p95 (<= 846.2 ms) | **PASS** |

- **The load during B4:** the 1-minute load average was 0.98 at the start (06:44:25). It rose with the run's own 16
  inference threads on the 8 cores to 14.7-16.3 from 06:46:16 to the end (17.1 at 06:48:35). No other job of ours
  ran beside it (the lab's live services as always: xfreerdp3 ~0.5 core, the backend, Xvfb). The absolute CPU numbers on this host are ~2.4-2.9x the 11-07 VM 103 run's (230 / 270 ms
  p50 / p95 at 8 threads), for both models alike. That is the host, which is why M10 made the bar relative. The live path is the GPU detect server; the CPU detector is
  its fallback.

**THE VERDICT: PASS.** Every bar of Amendment M as fixed by M7 and M10 holds: Garm Baby Q1s on gw3, the four
species' Q1c on pooled TEST and the relative CPU latency. **Passing does not switch the live detector:**
deploying xmas02-gb on xmas_dun02, and the runner's "seen -> Fly Wing" (rogue-xmas02.md), are Batt's
decision and their own pre-registration (Amendment M).

**Reported, deciding nothing:**
- **Labellers G and H:** the same 7 crops were not evaluated by both (q2 not good: Cruiser 6, Garm Baby 1).
  293 of 300 were evaluated.
- **gw3's four common species (M10 (a), reported only):** Q1s Myst Case 60 / 1.000 / 0.984, Cruiser 54 /
  1.000 / 1.000, Cookie 60 / 1.000 / 0.952, Christmas Cookie 60 / 1.000 / 1.000; Q1c 0.870 / 0.857 / 0.870
  / 0.870. Q1c pooled on gw3: 293 / 293 matched, 9 unmatched monster detections inside the evaluated
  boxes, precision 0.970.
- **Garm Baby's 5 unmatched garm_baby detections (Q1s), by geometry, no frame opened:** every one lies
  inside the boxes of TWO overlapping kept Garm Baby labels, the stand's two spawned dogs on top of each
  other (frames 257, 670 x 2, 672, 673). Most are the second dog, whose own label was not drawn into the pack.
  Frame 670 carries one garm_baby box more than its two dogs.
- **Garm Baby split:** clear 51 / 51 (precision 0.911), under a model 8 / 8 (1.000). Confusion (Q1,
  class-blind position match): garm_baby 59 / 59 seen as garm_baby.
- **No garm_baby box on the 231 pooled TEST frames,** which hold no Garm Baby label (xw5 + xp1 + X2's
  pack frames). There, 0 of the detections were garm_baby (player 232, cruiser 110, mystcase 100, cookie 99,
  cookie_xmas 76).
- **The four species on pooled TEST vs the deployed model (11-07, the same key and answers):** Q1c
  precision 0.937 / 0.932 / 0.938 / 0.935, against 0.881 / 0.873 / 0.881 / 0.877. Q1c pooled 232 / 233
  matched with 4 unmatched in boxes (0.983), against 230 / 233 with 8 (0.966, the cookie + cookie_xmas double boxes).
  Q1s Myst Case 59 / 1.000 / 0.983, Cruiser 56 / 0.982 / 0.982, Cookie 60 / 0.983 / 0.937, Christmas
  Cookie 58 / 0.983 / 1.000.
  Confusion: Christmas Cookie seen as cookie 1 (11-07: 5), cookie_xmas 56, mystcase 1; Cookie as cookie 59,
  cruiser 1; Cruiser 55, none 1; Myst Case 59.
- **TEST by part (Q1c: evaluated / recall / precision):**
  - xw5: Myst Case 41 / 1.000 / 0.953, Cruiser 45 / 0.978 / 0.957, Cookie 51 / 1.000 / 0.962, Christmas Cookie 25 / 1.000 / 0.926;
  - X2: 17 / 1.000 / 0.895, 9 / 1.000 / 0.818, 8 / 1.000 / 0.800, 27 / 1.000 / 0.931;
  - xp1: 1, 2, 1 and 6 crops, all 1.000.

**The outputs:**
- **Local `data/train/eval/xmas02gb/`, 460 KB:**
  - q1-refs-gw3, q1-pred-gw3 / -test, latency-cpu `2d7f0bec...`;
  - q1-score-gw3 `62057d18d4c0de2cdd27ad7303a2da0c8debbbdac96da6245414fa184151f9cd`;
  - q1-score-test `49330a83207830290105eba88fb3ccabc5ed3ac07e8503caa3ef37be16acfccc`;
  - the two reused 11-07 refs.
  They go to the NAS with the run in M6 step 5.
- **The evaluation scratch on the NAS `scratch-archive/2026-11-10/garm-eval/`:**
  - `gb/eval`: gw3's labels, the pack, the key, the 11-07 copies, the logs, the briefs, the scripts;
  - `blind-gb53-gw3`: the labellers' pack and answers G / H;
  - 667 files, `SHA256SUMS` `39b8b90a...`. The copy was verified, then the /dev/shm originals were deleted.
- **The two ONNX files stay in `/dev/shm/poring-lab-detector/model`** (M9).

#### M12 (2026-11-10 ~07:0x ICT, the parent): DEPLOYED -- xmas02-gb is the map's model

- **Why now:** M11 PASSED every bar, and Batt's "Go ahead with (c)" (2026-11-09 ~20:5x) was the
  class AND its pilot (rogue-xmas02.md 4BA).
- **The NAS archive (verified):** `archive/train/xmas02-gb-20261109/weights/last.pt` (85fb37a4...,
  + results.csv); `archive/models/xmas02gb-last-736x1280.onnx` (b22d972b...) + its names.json,
  `SHA256SUMS` updated and checked.
- **The code:** `unit_detector.MAP_MODELS["xmas_dun02"]` = the gb ONNX (its four species -> "monster",
  garm_baby kept), `gpu="xmas02gb"`; `GPU_WEIGHTS["xmas02gb"]` pins the .pt and the ONNX. The old
  `GPU_WEIGHTS["xmas02"]` stays for a ROLLBACK (MAP_MODELS back to it: one line).
- **What changes for the runner:** the box thread sees a Garm Baby as `garm_baby` (never a target);
  `--garm-fly` (9.19) acts on it. Nothing else in the base changes; the four species' boxes come
  from the better model (M11: precision 0.93-0.94 vs 0.87-0.88).
- Next: rogue-xmas02.md 4BA -- G0 (the Rogue immune, one staged Garm Baby), then the pilot.

### Amendment N (2026-11-10 ~07:1x ICT): Batt -- teach the detector the HIDDEN Garm Babies before "fly when seen"

**Batt's answer** to the 07:08 report (the choice between (a) piloting `--garm-fly` now and (b)):
"(b) ปิดไว้ก่อน แล้วสอนตัวตรวจจับให้รู้จักหมาที่โดนบังด้วย (ต้องอัดข้อมูลและเทรนใหม่) // ทำข้อนี้" -- keep
`--garm-fly` off, and teach the detector Garm Babies that scenery partly hides (new data, a retrain).

- **Why:** the frozen rule drops occluded labels (gw3: occluded_model 134 + occluded_terrain 68 of
  the dogs' candidates), so xmas02-gb never trained on a partly hidden dog and M11 never scored
  one; G0b (rogue-xmas02.md 4BB) met exactly that: a dog 3-11 cells away with no box for 4.5 s.
- **What comes next, each pre-registered before its data (N1...):** a study of how occluded dogs can
  be labelled reliably (the rule variant, its FIT test, T2 on occluded crops), the data (watches
  that put dogs near the map's models and raised blocks), a FRESH held-out (gw3 is spent; 56 unused
  TEST stands remain), the training (init xmas02-gb) and its bars (hidden-dog recall, the M11 bars
  not worse). `--garm-fly` stays off until then; the deployed xmas02-gb stays.

### Amendment N1 (PROPOSED, 2026-11-10, not yet accepted): partly hidden Garm Babies -- the study, a rule variant `xmas02-o3h-t-occ`, its FIT test, T2-occ, the data, the training and the bars

> **PROPOSED, NOT ACCEPTED.** Written offline (subagent, branch `feat/garm-occ`) for the parent and
> Batt, 2026-11-10 08:24-09:2x ICT. Nothing below is adopted, recorded, labelled or trained until a
> clock-labelled amendment (N2 ...) accepts it, BEFORE its data. Read: TRAIN gw2 and DEV gw1 only.
> gw3, xw5, xp1 and X2 were NOT opened (gw3's 16 stands were taken from its watch's own log, only to
> remove them from the free TEST stands; its published counts are M9's).

#### N1.0 What was read and run (offline; CPU at nice 15 in a 4 GB scope without swap; no GPU, nothing live)

- **gw2** (`20261109T210933-rdp-gb-gw2`, TRAIN by 3c) and **gw1** (`20261109T205355-rdp-gb-gw1`, NOT
  admitted by 3c and never trained: DEV evidence only), every candidate frame (749 / 758), through
  the FROZEN label stack unchanged (params `d4cc0a5d...`, `map_labels.labeler_for`, o3h-t), with each
  label's prediction kept for the geometry below; M1's label files for the frame-level counts.
- **The deployed xmas02-gb CPU ONNX** (`b22d972b...`, the unit_detector worker, 4 threads, conf 0.05,
  per-class NMS, no collapse) on every candidate frame of both (median 201 ms a frame).
- **G0b's runner archive** (`scratch-archive/2026-11-10/demo-sessions/...-xmas02-g0b`: its packets and
  `detections.jsonl`; a pilot, not a detector data set) and **p44's record** (rogue-xmas02.md
  section 5, the parent's 2c21af7c: one false garm_baby box).
- Scripts and outputs: NAS `scratch-archive/2026-11-10/garm-occ-study/` (53 files, `SHA256SUMS`
  `fcef932e...`, verified on the NAS): `occ_study.py` (geom / detect / stands), `analyze.py`,
  `summary.py`, `variant_yield.py`, `fit_dryrun.py`, `fp_player.py`, `rank_stands.py`, `g0b.py`, the
  per-label geometry (`geom*-*.json`), the detections (`det-*.json`), `stands.json`, the draft
  lattices, the crop sheets. Never committed (per-frame numbers and pixels of client data).

#### N1.1 How much of a dog is hidden: a geometry the frozen rule does not have

- The frozen rule's "under" tests say WHETHER, not how much: under a model = the sprite's box overlaps
  the model's whole projected VERTEX box, with no depth (a belt or a machine BEHIND the dog counts);
  under terrain = it overlaps the floor-to-top box of a raised (>= 10) cell south of it. On the
  excluded dogs those boxes cover a median 100 % of the label's box (models; terrain 88 % on gw2, 100 %
  on gw1), whatever is really hidden.
- **The study's estimate, per label at its predicted position:** every face of the 1,701 RSW models
  (118,915 triangles; `rsw.parse_rsm` skips the faces, the study reads them) and every GAT cell >= 1
  unit above the label's floor (a prism from the floor to its top; 24 rows south to 2 north, 8
  columns either side) are projected with the label's own scene. A pixel of the dog's drawn sprite
  (its frame's opaque pixels) is HIDDEN when a face covering it lies on the CAMERA's side of the
  dog's billboard plane (the vertical plane through its cell facing the camera's yaw: at yaw 0,
  south of the dog; interpolated perspective-correct). **v = the visible share of the sprite's
  opaque pixels**, the UI windows and the frame edge counted as hidden too (what the frame shows);
  v_scenery without them.
- A first version used the camera depth of the dog's feet: a wall right BEHIND a standing dog then
  "hid" half of it while its fit was 0.65 and kept. The plane test removed that (recorded so nobody
  repeats it).
- **It matches the pixels.** The fit NCC falls as v falls, while the NCC over the predicted-VISIBLE
  pixels only (the hidden ones masked out of the fit's valid map, +-6 px as the rule fits) stays at
  the clear dogs' level down to v 0.05 (all Garm Baby fates, median plain / masked NCC):

| v_scenery | gw2 n | gw2 plain / masked | gw1 n | gw1 plain / masked |
|---|---|---|---|---|
| >= 0.95 | 873 | 0.609 / 0.608 | 854 | 0.620 / 0.618 |
| 0.75-0.95 | 163 | 0.586 / 0.627 | 119 | 0.572 / 0.661 |
| 0.50-0.75 | 33 | 0.451 / 0.627 | 23 | 0.291 / 0.677 |
| 0.25-0.50 | 9 | 0.271 / 0.630 | 31 | 0.315 / 0.753 |
| 0.05-0.25 | 20 | 0.134 / 0.674 | 28 | 0.118 / 0.702 |
| < 0.05 | 118 | 0.095 / (no evidence: 7 % pass the floor) | 185 | 0.078 / (3 %) |

- **By eye** (15 gw2 crops, the hidden pixels tinted): the 6 with v 0.00 show only a wall, a block or a
  machine; in the 6 with v 0.14-0.61 the dog's back or head shows exactly outside the tint; the 3
  "box-only" ones (v >= 0.95, excluded as occluded_model) are whole dogs under the GM's spawn-message chat
  bubble, beside a summon glow and our own Rogue, or standing on a belt with a poor fit.

#### N1.2 The problem in numbers (TRAIN gw2; DEV gw1 beside it)

| | gw2 (TRAIN) | gw1 (DEV) |
|---|---|---|
| Garm Baby fates (candidate frames x visible dogs) / units | 1,216 / 32 | 1,240 / 32 |
| kept by the frozen rule | 836 | 771 |
| **excluded occluded_model + occluded_terrain** | **173 + 80 = 253** (21 units, 179 of 749 frames) | **171 + 144 = 315** (22 units, 252 of 758 frames) |
| of them, by the study's v: **fully hidden (< 0.05)** | **114 (45 %)**: model 76, terrain 38 | **177 (56 %)**: model 70, terrain 107 |
| **little (0.05-0.25)** | 20 (model 11, terrain 9) | 23 (18, 5) |
| **partly (0.25-0.50)** | 9 (2, 7) | 21 (13, 8) |
| **mostly visible (0.50-0.95)** | 76 (50, 26) | 61 (37, 24) |
| **not hidden ("box-only", >= 0.95)** | 34 (all model) | 33 (all model) |
| excluded ambiguous_view (2c: a facing ambiguity, NOT occlusion) | 57 (9 units; 44 of them v >= 0.95) | 71 (14 units; 47 of them v >= 0.95) |
| kept but partly hidden (v < 0.95: under terrain below the 10 step, or under a model with a good fit) | 123, all v >= 0.50 | 95 (9 at 0.25-0.50) |
| Garm Baby boxes the M5 cache WROTE from gw2, by v | 391: 337 >= 0.95, 50 at 0.75-0.95, 4 at 0.50-0.75, **none below 0.50** | (not in the cache) |

- The main occluders of the really hidden ones (v < 0.95): terrain 129 / model 90 (gw2), 191 / 91
  (gw1); the models: the block castles (`xmas_블럭성`), belt 02, the bear walls, the Santa bricks, a
  crane.

#### N1.3 The deployed xmas02-gb on these dogs (a garm_baby box >= 0.25 whose IoU with the dog's whole predicted box is >= 0.3 or whose centre lies in it; every verdict pooled)

| v | gw2 boxed | gw1 boxed | gw1 per episode (>= 2 frames in the band): seen within 3 frames |
|---|---|---|---|
| >= 0.95 | 842 / 846 (99.5 %) | 820 / 828 (99.0 %) | 60 / 60 |
| 0.50-0.95 | 214 / 223 (96 %) | 155 / 163 (95 %) | 30 / 31 (gw2 39 / 40) |
| 0.25-0.50 | 3 / 9 | 14 / 36 (39 %; score median 0.41-0.57) | 1 / 4 (gw2 0 / 1) |
| 0.05-0.25 | 1 / 20 | 0 / 28 | 0 / 4 (gw2 1 / 5) |
| < 0.05 | 0 / 118 | 0 / 185 | 0 / 19 (gw2 0 / 11) |

- gw2's frames that hold an excluded dog were never written (a frame with any excluded label is not
  written), but the same dogs' other frames trained; **gw1 never trained at all**: its row is the
  cleaner one, and the two agree.
- At conf 0.05 the low band gains a few weak boxes (gw2 0.25-0.50: 6 / 9, score median 0.23).
- garm_baby boxes >= 0.25 on no labelled dog's predicted box: 4 (gw2) and 5 (gw1) in ~1,000 each,
  none touching our own player box; whether each is a dog beyond the visibility rule (half off the
  frame or under the UI) or false was not resolved. Frames with a non-dog monster touching our box:
  10 and 8 (immune watches: monsters ignore us), so **these watches cannot measure p44's kind of
  false box.**

#### N1.4 Partly vs fully hidden: separable -- and G0b's dog was FULLY hidden

- **Separable, by the geometry and by the pixels:** about half the occlusion exclusions have v < 0.05
  (nothing of the dog on screen: no crop shows one, the masked fit finds nothing, the deployed model
  boxes 0 of 303 at conf 0.25); from v 0.05 up, the visible pixels fit like a clear dog's (N1.1). The partly hidden
  ones are a minority with a clear lower end; the "box-only" ones are not hidden at all (their
  exclusion is the floor on a poor fit under a model's box: overlays, glows, our own sprite).
- **G0b (rogue-xmas02.md 4BB), recomputed from its packets and the runner's detections:** the staged
  dog appeared at (10,19), 53 % visible from the start (7,21) (the rest hidden by terrain); 0.48 s
  before run_start it began walking to (6,17). In all five detections while it was on screen (0.99-
  4.13 s; we walked east, (7.6,21) -> (17.5,24)) it stood or walked at (7.8,17)-(6,17), **v = 0.00:
  fully behind the +30 terrain block 3.5-4.5 cells south of it**; on screen, not under any UI window.
  At 36.37 s it stood at (11,20), v 0.95, and was boxed garm_baby 0.969 at once (the predicted box
  (109,359)-(187,421) against the detection's (105,359)-(176,421)). The same geometry from (7,21): (9,18)
  23 % visible, (8..6,17) 0 %.
  **So the G0b miss was not a detector failure: there was nothing to see.** No training can box it;
  teaching partly hidden dogs could at most have given a box in the ~1 s it crossed (10,19) -> (9,18),
  half of it before run_start.

#### N1.5 What this means, before any design (for the parent and Batt)

1. **The deployed model already sees a dog when half or more of it shows** (95-96 %; 30 / 31 and
   39 / 40 such episodes within 3 frames), although it trained on no dog below 50 % visible.
2. **The gap is the 5-50 % band:** 29 (gw2) and 64 (gw1) of ~1,230 dog views per watch (2.4 % and
   5.2 %), boxed 4 / 29 and 14 / 64. That is the target of a retrain: a head or a back over a block, a dog walking
   out from behind one -- warnings of a fraction of a second to a few seconds earlier on the runner.
3. **Fully hidden dogs (9-15 % of views here) cannot be learned**, and G0b's was one. The Battle Log
   guard (fly on the first named line) stays the protection against them.
4. **False alarms already exist** (p44: 1 garm_baby box in 1,568 detections, a Cruiser under the
   Rogue). Teaching partial dog views can only push that kind of error up; N1.10's B5 / B6 measure it,
   and the runner's own rule may need a confirmation (N1.12 D9).
5. A cheap side gain, independent of 2: frames held out today only because a dog in them is FULLY
   hidden could be written (gw2 +36 frames, gw1 +62, each with its visible dogs and monsters).

#### N1.6 The rule variant `xmas02-o3h-t-occ` (Garm Baby only)

- **(a)** Everything as `xmas02-o3h-t` (the frozen params, tau, T_h, offset, E0, the frame exclusions)
  for every label except a **Garm Baby (1515) label the frozen rule excludes as `occluded_model` or
  `occluded_terrain`**. The four species are untouched (their labels byte-identical: a test).
- **(b)** For such a label: v (N1.1, committed as code: T-N1) and the MASKED fit (the hidden pixels
  out of the valid map; tau 0.092, +-6 px, not at the edge):
  - **v < V_full = 0.05 (fixed now): `hidden_full`**: no label (nothing to see). Its frame is written
    when it is otherwise whole -- only if decision D3 says so after T2-occ's stratum F; until then it
    stays excluded as today;
  - **V_min <= v < 0.95, the masked fit passing and the masked NCC >= T_h 0.536 (the frozen floor,
    unchanged): KEPT**, flagged `occluded` with v and the masked NCC, its box the **AMODAL** box: the
    whole sprite frame at the masked fit's offset (as every kept label's box is);
  - otherwise excluded with its frozen reason, as today.
- **(c)** Every other exclusion (2b next_move, 2c ambiguous_view, facing_unknown, crowd, ui, unfit,
  the frame exclusions, E0) and the T_h floor on every kept label (the cache's `weak_fit`, on the
  masked NCC for an `occluded` label) unchanged.
- **Why AMODAL, not the visible part:**
  - accuracy: the amodal box is the projection plus the fit that C1 / C2 measure (median 1 px); a
    visible-part box would inherit the occluder geometry's error at its cut edge (the GAT is a
    5-unit grid; the RSM faces approximate the drawn mesh) -- label noise exactly where the evidence
    is thinnest; v only decides KEEP or not, so its error moves no box;
  - one definition: every Garm Baby box in the cache is already the whole sprite, partly hidden
    ones included (54 of the 391 boxes the cache wrote from gw2 have 5-50 % of the dog hidden), and
    the camera's scale is fixed (D13: scale 0.1), so the whole box follows from any visible part;
  - the runner needs presence only (any garm_baby box -> the Fly Wing) and Q1 matches a detection by
    its centre in the box; T2's instructions already say sprites may be partly hidden (N1.7 adds
    the box sentence);
  - YOLO trains on full-extent boxes of occluded objects routinely (e.g. CrowdHuman's full-body
    boxes); a visible-part box would range from a sliver to the whole dog and look like other
    species' parts.
  - The cost: an amodal box spans the occluder too. The guards: V_min (>= V_min of the dog's own
    pixels in it are the dog), the masked floor, and the false-alarm bars (N1.10 B5, B6).
- **The name:** `xmas02-o3h-t-occ` (labels, params, cache id); `freeze` refuses the name without the
  variant's fields and the reverse (as Amendment G's rename rule).

#### N1.6b Its FIT test: V_min, fixed on FIT before any TEST (like 4f)

- **FIT = a NEW watch, `go1`** (N1.8), not gw1 / gw2 (this study read them; gw1 as FIT is the cheaper
  alternative, D2).
- **The population P (FIT's), chosen by the GEOMETRY, not by the frozen rule's verdict:** every
  Garm Baby label that is kept or fails only its fit (no 2b / 2c / facing_unknown / crowd / ui
  exclusion), uncrowded (Amendment B), with v in [0.05, 0.95). **The reference R:** the same, clear
  of every occluder box (models and terrain at the rule's own test) with v >= 0.95. For both, the
  MASKED fit (for R it equals the plain fit: nothing is masked). (Why not "the occlusion exclusions
  only": they are the fit FAILURES by construction, against a reference of successes; the first
  dry run did that and was biased.)
- **A band passes when ALL hold:** (i) n >= 30 (the LOW bands: >= 20); (ii) its masked-NCC median >=
  R's median - 0.05; (iii) its share passing the masked fit AND the floor (masked NCC >= T_h) >= R's
  share - 0.10; (iv) **C1-occ**: of its floor-passing STANDING labels (idle >= 1 s), the share whose
  PREDICTION (no shift; its frame, else the best of the action's frames, as C1) has a masked NCC <
  tau (0.092) is <= 5 % on >= 30 rows (LOW: >= 20) -- 3c's C1 bar on the visible pixels.
- **HIGH band [0.50, 0.95):** must pass, else the variant is NOT adopted (no occluded label is kept;
  V_full's dropping may still be adopted by D3).
- **LOW band:** **V_min = the smallest g in (0.15, 0.25, 0.35) whose band [g, 0.50) passes on its own**;
  none passes (or too few rows) -> V_min = 0.50. Steps 0.05 and 0.10 are reported, never chosen
  from; the grid, the margins, the minimum rows, V_full = 0.05 and the 0.95 top are fixed here.
- A failure is reported, never re-run under the same bars.
- **DEV dry run (this study's gw2 / gw1, NOT FIT; disclosed, decides nothing):**

| | R (clear): n, masked-NCC median, floor share | HIGH [0.50, 0.95): n, median, floor share, C1-occ | LOW [0.15, 0.50): n, median, floor share, C1-occ | [0.05, 0.15) (reported) |
|---|---|---|---|---|
| gw2 | 553, 0.620, 0.899 | 173, 0.640, 0.821, 1 / 65: **PASS** | 5, 0.667, 0.80, 0 / 0: too few | 10, 0.694, 1.00, 1 / 7 |
| gw1 | 489, 0.629, 0.857 | 127, 0.668, 0.929, 0 / 62: **PASS** | 27, 0.735, 1.00, 0 / 13: (iv) too few rows | 13, 0.565, 0.69, 2 / 3 |
| pooled | 1,042, 0.624, 0.879 | 300, 0.656, 0.867, 1 / 127: **PASS** | 32, 0.732, 0.97, 0 / 13: (iv) too few rows | 23, 0.677, 0.83, **3 / 10** |

  - The HIGH band would pass everywhere; the LOW band [0.15, 0.50) looks as good as the clear dogs
    (masked median 0.73, floor 97 %) but holds too few STANDING rows on ordinary stands, so on this
    data V_min would be 0.50. go1's occluder stands (N1.8: ~3-9x the partly hidden share) are what
    can fill it. Below 0.15 the prediction stops matching (C1-occ 3 / 10 bad): the grid starts at
    0.15 for that reason.
  - The frozen C1 on the same partly hidden standing dogs (no mask): 17 / 156 bad (10.9 %); with the
    mask (C1-occ) 1 / 127 in the HIGH band: the mask, not a looser bar, is what makes them pass.

#### N1.7 T2-occ: the blind check of the occluded labels (two NEW labellers, I and J)

- **The pack:** seed 55 (new), salt xmas02, from go1 + the admitted TRAIN watches labelled under the
  variant; Garm Baby only, three strata: **O** (kept `occluded`, v in [V_min, 0.95)) 30 crops, half
  of them with v < 0.50 when the pool holds them; **C**
  (clear, v >= 0.95) 10 crops, a control; **F** (`hidden_full`, v < 0.05, the whole box drawn where the
  dog stands) 15 crops, for D3. Mixed in one seeded order; the strata's sizes not stated in the pack
  (labeller A noticed the balance on 11-06).
- **The instructions:** a NEW file `docs/planning/xmas02-blind-instructions-occ.txt` (its sha256 in an
  amendment BEFORE the pack) = the current file plus:
  - "Some boxes are drawn around the WHOLE monster even where scenery hides part of it; the box then
    also covers the block, wall or model in front of it. Judge Q2 against the monster as it would
    stand unhidden: good when the visible part is inside the box where that part of the monster
    would be and the box would fit the whole monster; off when it cuts the visible part or misses
    the monster. A box with no part of a monster visible in it is no for Q1." and
  - **Q4:** "how much of the monster can you see? most / about half / a little / none" (REPORTED
    against v: does the geometry agree with the eye?).
- **The bars:** stratum O: good >= 90 % AND species >= 95 % AND Q1 yes >= 95 %, from EACH labeller (6's
  bars + Q1). C: section 6's. F (for D3): Q1 no or unsure on >= 90 % from each (nothing to see).
- O fails -> the occluded labels are not trained (Amendment H's rule); F fails -> hidden_full frames
  stay excluded.
- Tool gap: `blind_score.py` per stratum and Q4 (T-N4).

#### N1.8 The data plan

- **Stands from the geometry (no recording read):** for every lattice stand, the idle Garm Baby at
  every walkable cell within Chebyshev 1-5 of it (the spawn lands 1-3 cells away, M1 point 3, and the
  dog wanders), its v_scenery seen from the stand; a stand's score = the share of those cells where
  the dog is PARTLY hidden (0.25 <= v < 0.85), within 3 and within 5 cells. Computed for all 431 stands of
  both lattices (`stands.json` in the study's archive; 3.6 s a stand):

| stands | n | partly hidden share, cells within 3 (median / p90) | within 5 (median) | stands with >= 0.25 within 3 |
|---|---|---|---|---|
| TRAIN side, all | 343 | 0.049 / 0.205 | 0.094 | 17 |
| gw1 / gw2's own stands | 30 | **0.022** / 0.208 | 0.076 | 0 |
| **the 64 best TRAIN-side stands, minus gw1 / gw2's** (go1-go4, 16 each, dealt round-robin: each 0.195-0.224) | 64 | **0.203** / 0.292 | 0.193 | 17 |
| the 56 unused TEST stands | 56 | 0.033 / 0.229 | 0.084 | 4 |
| **their best 16** (goT) | 16 | **0.218** / 0.333 | 0.158 | 4 |

  The ranking: by (share within 3 + share within 5), then the fewest fully hidden cells within 3, then
  x, y. **So the occluder stands put a dog partly hidden ~3-9x as often as gw1 / gw2's stands did**
  (within 5 / within 3). go1's 16: (82,49) (128,146) (27,247) (150,225) (38,203) (170,72) (8,238)
  (18,225) (181,148) (93,16) (203,248) (192,194) (25,173) (159,118) (105,17) (179,71); goT's 16:
  (8,140) (126,192) (170,94) (247,206) (223,105) (203,159) (159,225) (223,236) (181,216) (247,192)
  (225,248) (181,81) (60,159) (146,16) (214,113) (8,16) (all TEST by 3a; none of R2-W's 16 or gw3's
  16).
- **The watches** (Amendment M's protocol unchanged: `stage_items.py watch --map xmas_dun02 --spawn
  1515 --spawn-n 2 --dwell-s 40 --max-cells 16 --immune-confirmed`, beside `record_session.py
  --backend rdp --format png --fps 1`, the Rogue immune and judged, `@killmonster2` after each dwell):

| watch | role | stands (lattice file, client-derived, /dev/shm) | seed |
|---|---|---|---|
| `go1` | **FIT** (N1.6b) + VAL monitor | `lattice-occ-go1.json`: ranks 1, 5, 9 ... (16) | 2611101 |
| `go2`, `go3`, `go4` | TRAIN by 3c, in order, until the stopping rule | `lattice-occ-go2/3/4.json`: ranks 2, 6, ... / 3, 7, ... / 4, 8, ... (16 each) | 2611102-4 |
| `goT` | **the FRESH held-out** | `lattice-occ-goT.json`: the 16 best of the 56 unused TEST stands | 2611109 |

  - The 64 TRAIN-side stands are the best of the 343 minus gw1 / gw2's 30, dealt round-robin so FIT
    and each TRAIN watch get the same mix. The files (the study's drafts are in its archive) are
    rebuilt by a committed rule (T-N5) and their sha256 recorded before go1.
  - `goT`'s name (`-rdp-gb-goT`, a label `gb-goT`) joins the MapSpec's TEST and eval suffixes BEFORE
    it records (refused by labels / pack / the cache; `--eval-test` only after the freeze).
- **3c, the join rule:** as written (its own C1 <= 5 % on >= 50 standing labels) PLUS C1-occ <= 5 % on
  its floor-passing standing `occluded` labels (>= 30, else reported). **A risk to say now:** gw1
  failed 3c (6.21 %) on Garm Baby FACING misses (M1 point 1): 1 of the 2 earlier dog watches was
  refused, so plan for one in two.
- **The stopping rule:** after each admitted TRAIN watch, count the `occluded` Garm Baby boxes in the
  frames the cache would write (gw2's re-labelled frames included); **stop at >= 300**, or after go4.
  The estimate: gw2 gives 29 on ordinary stands (V_min 0.25; N1.2's frame rule); the occluder stands
  should give several times that, but the per-frame blocks (the other dog excluded) cap it: ~60-120
  a watch, so 3 watches. A watch beyond the stop is not admitted (Amendment F's rule).
- **Disk and time:** gw1 / gw2 were 1.86 / 1.95 GB for 16 stands; each watch ~15 min of dwells, ~25-30
  min with the prep and the ship; 5 watches ~2.5 h on the one Windows session; shipped and verified
  one at a time (the recorder floor 30 GB on bot-server).

#### N1.9 The cache and the training

- **The cache:** M5's form; labels re-made under the variant for every session holding a Garm Baby
  (gw2, both xw3); xw2 and xw1 unchanged (byte-identical labels: a test); + the admitted go2-go4;
  **VAL: xw1 x 2 + go1** (a garm_baby AP that includes hidden dogs; monitor only). A dry run first,
  then the guarded `cache:` step; its counts must equal the dry run's.
- **No new class:** an occluded dog is `garm_baby` (class 7); the class list `dd1d3f31...` unchanged.
- **Init: xmas02-gb's `last.pt`** (`85fb37a4...`); every class row seeded by name.
- **The recipe: M6's** (YOLO11n, imgsz 1280, batch 2, workers 2, seed 20261004, close_mosaic 3, hsv_s
  0.2, scale 0.1, FP32 on the Arc, mid-epoch checkpoints, the execdev launch without train-day's
  duty arguments), **E epochs (D7: 20 as M6, or 10)**; the scored checkpoint `last.pt` after the last
  completed epoch, its sha256 recorded before goT is read.

#### N1.10 The evaluation (once, after the freeze) and its bars

- **The held-out: goT** under the variant (`--eval-test`); a pack, seed 57, Garm Baby strata O-low (60,
  or all), O-high (60) and C (60), two NEW labellers (K, L), N1.7's instructions; crops evaluated when both say yes /
  good / Garm Baby. Both models (new and deployed) predict the same refs (paired).
- **Bars (every one must PASS; fewer rows than its minimum -> NO VERDICT, never a pass):**
  - **B1, hidden dogs per crop (Q1s, the box's class garm_baby):** on goT's evaluated **O-low** crops
    (V_min <= v < 0.50; >= 30): recall >= 0.70; on its **O-high** crops (0.50 <= v < 0.95; >= 30):
    recall >= 0.90; precision >= 0.80 over both. (Why: the deployed model's 5-50 % band is 18 / 93 on
    this study's data and its 50-95 % band 369 / 386, so O-low is where the retrain must show, and
    O-high must not fall; a back over a wall is harder than a whole dog, and the runner gets several
    frames, B2.) The deployed model scored beside it on the same crops.
    **If FIT gives V_min = 0.50,** O-low does not exist and the variant only adds dogs the deployed
    model already boxes: the parent then re-decides D1 before any training.
  - **B2, hidden dogs per EPISODE (the runner's view):** of goT's partly hidden episodes (one dog in
    view with V_min <= v < 0.95 for >= 2 consecutive candidate frames, from the labels and the
    geometry), the share with a garm_baby box (>= 0.25) within the episode's first 3 frames >= 0.80
    (>= 20 episodes) AND >= the deployed model's share on the same episodes + 0.10. Reported beside:
    the same with 2 CONSECUTIVE boxes (D9's confirmation rule).
  - **B3, visible dogs not worse:** goT's C crops: Q1s recall >= 0.95, precision >= 0.85, AND recall >=
    the deployed model's on the same crops - 0.02.
  - **B4, the four species not worse:** Q1c on pooled TEST (11-07's key, C / D, refs: M7 point 4):
    recall and precision >= 0.80 each AND precision >= M11's - 0.03 (>= 0.907 / 0.902 / 0.908 / 0.905).
  - **B5, false alarms where a monster touches the Rogue (p44's kind; the parent, 2026-11-10):** on
    TEST-P (X2 + xp1, every recorded capture) and goT, the captures where a non-dog unit's projected
    box overlaps or touches our own projected box (packets) and no Garm Baby is within the view:
    garm_baby boxes >= 0.25: the new model <= the deployed model on the same captures, AND <= 1 per
    500 such captures; < 200 such captures -> NO VERDICT (the count is reported first).
  - **B6, false alarms on dog-free captures:** every capture of X2 + xp1 and goT's dog-free frames (the
    kill gaps) and the pooled TEST refs with no Garm Baby within view (packets): garm_baby boxes >=
    0.25 <= 1 per 1,000 captures (p44 live: 1 / 1,568) AND the new model <= the deployed model + 1.
  - **B7, CPU p95 <= 1.10 x the deployed model's** (M10 (c), one interleaved run).
- **Live, after deployment (rogue-xmas02.md's own pre-registration, not this document's):** shadow
  pilots of the base with `--garm-fly` OFF and the new model: a run is a "false-alarm run" when a
  garm_baby box >= the fly threshold appears with no job 1515 in view (packets); 4BA's G2 (<= 1 false
  alarm a run) judged on them before `--garm-fly` flies on anything.
- **The verdict:** PASS when B1-B7 all pass; deploying it and `--garm-fly` stay Batt's decisions.

#### N1.10b The false-alarm risk of occluded labels (the parent's p44 fact, 2026-11-10)

- **The fact:** p44 (08:22-08:48, the deployed xmas02-gb, no Garm Baby in the run by packets): ONE
  garm_baby box in 1,568 detections, FALSE: 0.768 at (621,330)-(686,398), just below our player box
  (624,293)-(659,364), while a Cruiser stood on (121,205), the cell below the Rogue at (121,206), in
  a fight (killed 5.2 s later). With `--garm-fly` on: one needless Fly Wing in 25 min (4BA's G2 allows
  <= 1 a run).
- **Why N1 can raise it:** (1) N1 teaches that a FRAGMENT of a monster beside an edge is a dog; a
  monster partly covered by our own sprite is the same picture to the model, and p44's box is exactly
  that; (2) an amodal box spans occluder pixels, so the model may learn edge context; (3) the training
  is ASYMMETRIC: partly hidden dogs become positives, but a Cruiser or a Myst Case half behind the
  Rogue never appears at all (E0 excludes the engaged unit and its frame; the crowd rule excludes
  neighbours), so nothing teaches "a fragment that is NOT a dog". The deployed model, which saw no
  dog below 50 % visible, already makes this error once a run.
- **What guards it here:** V_min and the masked floor (a kept occluded label always holds >= V_min of
  the dog's own pixels), B5 (frames where a monster touches the Rogue, paired against the deployed
  model) and B6 (dog-free captures), and the live shadow pilots before `--garm-fly` flies. What
  would REDUCE it (not in N1): hard negatives from hunting frames (D10) and a 2-detection
  confirmation in the runner (D9).

#### N1.11 The tools (offline, a tmpfs worktree, tests and a positive case each; before go1 records)

| # | what | positive case |
|---|---|---|
| T-N1 | `rsw.parse_rsm` keeps the faces; an occlusion module: model faces + GAT prisms vs the billboard plane, v per label (the study's code, cleaned) | this study's v on gw2 reproduced (the per-label table above) |
| T-N2 | the variant in `orc_labels_fix` / `map_labels` (`--occlusion o3h-t-occ`: the masked fit, `hidden_full`, `occluded` labels, v in the label files); `freeze` and the name | gw2 under the variant = this study's simulation (298 -> 363 frames at V_min 0.25); the four species byte-identical |
| T-N3 | `threshold` reports N1.6b's FIT test (both bands, C1-occ); `check` reports C1-occ (3c) | the DEV dry run above reproduced |
| T-N4 | `pack` strata O / C / F for Garm Baby; `blind_score.py` per stratum and Q4 | a synthetic answer file per stratum |
| T-N5 | the stand ranking + `lattice-occ-{go1,go2,go3,go4,goT}.json` by the rule above | the study's ranking reproduced |
| T-N6 | the cache: `occluded` labels as class 7, `weak_fit` on the masked NCC, `hidden_full` frames by D3 | the dry run's counts = the label files' |
| T-N7 | the evaluation: B2's episodes, B5 / B6's packet tests (a unit's projected box touching ours; Garm Baby in view) | p44-like: a staged frame list from the gw watches with a known count |

#### N1.12 Decisions for the parent / Batt

| # | decision | proposed default |
|---|---|---|
| D1 | **full N1, or stop here**, given N1.5 (the deployed model already sees dogs >= 50 % visible; the gain is the 5-50 % band, 2-5 % of dog views; G0b's dog was fully hidden, which no training fixes) | **Batt is told N1.5 first.** If (b) stands: the full N1. The alternative: keep xmas02-gb, measure B5 / B6 on it (offline, TEST-P), and decide `--garm-fly` with D9; hidden dogs stay covered by the Battle Log guard |
| D2 | FIT: a new watch `go1`, or gw1 (cheaper; read by this study) | `go1` |
| D3 | write frames whose excluded dogs are all `hidden_full` (v < 0.05) | yes, if T2-occ's stratum F passes |
| D4 | the scope: Garm Baby only, or every species' occluded labels too | Garm Baby only (the four species' M11 bars are not risked) |
| D5 | amodal boxes (N1.6) | amodal |
| D6 | the stands (N1.8's ranking; 64 TRAIN-side + 16 TEST) and the stopping rule (>= 300 occluded boxes, at most go2-go4) | adopt |
| D7 | epochs: 20 (M6) or 10 | 10 (a fine-tune of a model that already holds this map; ~half the GPU) |
| D8 | B1-B7's numbers (B1 0.70; B5 / B6 rates) | adopt |
| D9 | (rogue-xmas02.md's, recorded here as a dependency) the runner's confirmation: fly on ONE garm_baby box, or on 2 in consecutive detections (p44's false box was one frame; a partly hidden dog is usually seen in consecutive frames: N1.3's episodes) | the parent's pre-registration of `--garm-fly` decides |
| D10 | hard negatives for p44's case: frames with a monster overlapping our own sprite are never written today (E0 excludes the engaged unit, the crowd rule its neighbours) | a later round (gef10 4h's E2 / E3 path); B5 measures the risk now |

#### N1.13 Time and GPU (estimates)

- **Tools:** ~1 day of agent time (T-N1-T-N7), offline, in a tmpfs worktree.
- **Live:** 5 watches, ~2.5 h on the one Windows session, ~10 GB recorded and shipped one by one.
- **Labels, FIT, T2-occ:** ~10 min CPU a session; two labellers ~30 min.
- **GPU (the Arc, M8's rate 0.625 s a frame-epoch):** ~2,291 + 65 (gw2's new frames) + ~350 a TRAIN
  watch x 3 = **~3,400 frames: 10 epochs ~5.9 h, 20 epochs ~11.8 h** (at the 12-h step limit: one
  planned resume). The cache ~20 min; the evaluation ~1.5 h with the labellers.
- **Calendar:** ~2-3 days from an accepting amendment.

#### N1.14 What looked wrong, and the limits (recorded)

1. **The occlusion geometry is a model of the client, not the client:** GAT cell tops are flat 5-unit
   prisms; the RSM faces are frame 0 (animated belts and gears move); the billboard plane ignores the
   sprite's own depth. The pixels agree (N1.1), but T2-occ's Q4 and the masked floor are the checks.
2. **ambiguous_view is not occlusion** (fix 2's 2c, a facing ambiguity): 57 / 71 dogs, most fully
   visible; out of N1's scope.
3. **"occluded_model" is often not occlusion:** 34 / 33 excluded dogs are fully visible (v >= 0.95):
   the o3h floor on a poor fit under a model's box (GM chat bubbles, summon glows, our own Rogue, a
   facing miss). The variant leaves them excluded (the floor).
4. **The garm_baby boxes on no labelled dog** (4 + 5) were not resolved into dogs beyond the
   visibility rule vs false boxes.
5. **The watches cannot show p44's false box:** monsters ignore an immune Rogue (8-10 frames a
   session with a monster touching our box). B5 needs TEST-P's fights; enough such captures there is
   not known until counted.
6. **Episodes are short and few in the low band** (gw1 4 + 4, gw2 1 + 5 at 5-50 %): one watch on ordinary
   stands cannot score B2; goT's stands are chosen for it, and B2's minimum (20 episodes) may still
   give NO VERDICT.
7. The study's numbers are DEV: gw2 is TRAIN data of the deployed model (its excluded-dog frames
   were never written, the same dogs' other frames were); gw1 is clean but was refused by 3c.

### Amendment N2 (2026-11-10, Batt's answers received before 09:40 ICT from `date`): N1 is NOT run now

- Batt chose the parent's option (a) after N1.5: "ทำ a ตามที่แนะนำได้เลย" (do (a) as recommended).
  N1's data, labels and training are NOT started. The deployed xmas02-gb stays. The runner gets a
  2-detection confirmation instead (rogue-xmas02.md 4BE), and fully hidden dogs stay with the Battle
  Log guard.
- "ใช้ตามเกณฑ์ที่เสนอ" (use the proposed bars): N1.10's bars (B1-B7) and N1.12's proposals stand
  as accepted IF N1 is ever run. Its D2-D7 choices (FIT watch, D3, stands, epochs) would still need
  their own accepting amendment then.
- Floor items (rogue-xmas02.md "Study after p44", 3a): Batt said yes, "เทรนแยกเลย" (train it
  separately). Its plan follows as its own amendment (Amendment O), proposed by a study before any data.

### Amendment O (PROPOSED, 2026-11-10, not yet accepted): a FLOOR-ITEM class for the loot step -- the study, the label rule `xmas02-fi-1`, T2-items, the data, a separate item model, the bars

> **PROPOSED, NOT ACCEPTED.** Written offline (subagent, branch `feat/floor-item`) for the parent and
> Batt, 2026-11-10 09:44-10:4x ICT (`date`). Nothing below is adopted, recorded, labelled or trained
> until a clock-labelled amendment (O1 ...) accepts it, BEFORE its data. **Frames read: FIT p31 and
> DEV p38 only.** p20 and p39 were read by their PACKETS only (counts), never by a frame; p30 is a GPU
> video recording (refused, below). The monster TEST sessions (xw5, xp1, X2, gw3) were not opened.
> Not to be confused with rogue-xmas02.md 4AY, whose title is also "Amendment O" (Batt's answers of
> 2026-11-09); this one is xmas02-detector.md's, named by N2.

**Why (Batt 2026-11-10, rogue-xmas02.md 4BD 2: "teach it, train it separately, for confidence and
faster looting"):** 68-82 % of the Rogue's kills drop nothing on the floor (Snatcher steals during
the fight), yet every kill gets the full 9-cell loot hover (~3 s; 84-98 s a 25-min run); a kill with
a drop takes ~4.0 s (rogue-xmas02.md "Study after p44"). If the detector sees floor items, the loot
step can skip an empty floor and hover only the boxed cells.

#### O.0 What was read and run (offline; CPU at nice 15 in a 4 GB scope without swap, <= 4 threads; no GPU, nothing live)

- **The data:** the five banked 1-fps hunt recordings with packets (section "Study after p44"):
  `20261108T235614-rdp-s2-xmas_dun02-p20`, `20261109T075431-rdp-s3-xmas02-p30`,
  `20261109T082234-rdp-hunt-xmas02-p31`, `20261109T133046-rdp-hunt-xmas02-p38`,
  `20261109T143541-rdp-hunt-xmas02-p39`.
  - **FIT = p31** (every parameter below is fixed on it). **DEV = p38** (the same steps, reported,
    nothing tuned on it). **UNTOUCHED = p20 and p39** (packets counted only; no frame decoded).
  - **p30 is not usable:** its manifest `format` is `vpp-hevc444-10-q20` (the GPU video, ADR-0024),
    which 3c's recording path refuses until a parity check (map_labels `RECORDING_FORMATS`). Its 7
    floor items are counted in the packet facts only.
  - **The boss recognizer's use of p31 / p38 / p39** (stormy-knight-recognizer.md: p31 its round-1
    hunting negatives, p38 its round-2 DEV R2-H1, p39 its round-2 HELD-OUT R2-H2) does not interact:
    a different model on a different question (an aura rule's false positives), scored once and
    closed (NOT ADOPTED, 2026-11-09 19:46); its round 3 needs fresh recordings anyway (its own
    next_action). These frames carry no floor-item label today; labelling them for items changes
    nothing the recognizer measured. The floor items' HELD-OUT is a FRESH recording (O.6).
- **The client data (rule 4: /dev/shm only, never committed, deleted after):** the item resname
  table and the 28 item sprites (33 item ids) of the six species' drop tables (`data/kb/drops.json`),
  extracted with `grf_read.py extract ... --decode-des --decode-mixcrypt` into
  `/dev/shm/poring-lab-tmp/floor-item/`; the 11-06 inputs in `/dev/shm/poring-lab-tmp/xmas-det/`
  (RSW + RSMs, GAT, kb-sprites) read-only; the frozen monster params `d4cc0a5d...` (Amendment G).
- **The code:** the worktree's sources with the main venv; the label stack of map_labels
  (`RecSession`, the 120-ms 1d, the session's UI rectangles), gef10_items' item sprites and
  exclusions, item_labels' floor spans and sub-cell table (item-class.md 8a), the frozen monster
  label pass (`map_labels.py labels`, FIT and DEV only, for Route M below).
- **Scripts and outputs:** NAS `scratch-archive/2026-11-10/floor-item-study/` (47 files, `SHA256SUMS`
  `c2e169ac...`, verified on the NAS): `pk_stats.py` (packet facts), `cand_stats.py` (still frames), `fi_study.py`
  (per item view: the projection, the covers, the fits, 2 absent controls a frame), `fi_refit.py`
  (grey vs colour masked NCC at +-6 / 10 / 16 px), `scale_test.py`, `fi_rule.py` (the rule's dry
  run), `itemscale.py`, `sheet.py` (crop sheets), `an1-3.py`; the per-view rows, the monster labels
  of p31 / p38, the crop sheets looked at (client pixels: never committed). No new tool in
  `scripts/` (O.11 lists what an accepted plan needs).

#### O.1 The facts

**O.1a The drops (packets; all five recordings, counts only).**
- 87 floor items: 74 `fall` + 13 `in_sight`; our kills 221, **68 of them (30.8 %) with a drop**
  (p20 13 / 30, p30 5 / 13, p31 18 / 61, p38 15 / 53, p39 17 / 64).
- **The item lands ON the death cell, not anywhere in its 3 x 3:** 62 single drops on the death
  cell; 6 two-item drops on the death cell + (+1, -1) (rAthena's free-cell search for the second
  item). The fall packet comes 0.23-0.27 s (median 0.251) BEFORE the death vanish.
- **The death cell is next to the Rogue:** Chebyshev <= 1 in 218 of 221 kills (melee); by cell (rel
  to her, y up = north): (1,0) 40, (0,-1) 38, **(0,+1) 36 (16.3 %)**, (-1,0) 33, (1,1) 23, (-1,-1)
  22, (1,-1) 14, (-1,1) 10, other 5. The 74 falls relative to her: (1,0) 15, **(0,+1) 13 (17.6 %)**,
  (0,-1) 12, (-1,0) 9, (1,1) 9, (-1,-1) 7, (-1,1) 4, (1,-1) 2, other 3.
- **How long an item lies there** (appear -> vanish; at most 60.0 s, the expiry): median p20 20.8 s,
  p31 23.3 s (1 and 0 of their falls picked), p38 12.9 s (8 of 15 falls picked), **p39 3.9 s (18 of
  21 picked: the base with `--loot-first` picks ~3.8 s after the drop)**.
- **Still frames:** 53-65 % of each recording's frames are candidates (our character still, 4g);
  item views on still frames at age >= 2.2 s: p20 211 (14 items), p31 422 (19), p38 181 (15), p39
  62 (21).

**O.1b How an item looks on screen (FIT p31; DEV p38 beside it).**
- **The sprites:** each of the 33 ids is ONE action with ONE frame (no animation of its own);
  native extents 11 x 12 (Scell, the most common drop) to 36 x 26 (Sandals); the common ones Zargon
  15 x 17, Piece of Cake 17 x 17, Red Herb 17 x 18, Candy 17 x 20, Iron 19 x 17, Pearl 21 x 19,
  Manacles 23 x 21.
- **Drawn at a FIXED native scale 1.0, not the monsters' billboard scale** (which is 0.956 here,
  median): on FIT's clear views, a scale grid 0.90-1.10 gives the best median colour fit at 1.00 for
  Scell (32 views: 0.791 at 0.95 -> 0.911 at 1.00), Zargon (0.940 -> 0.960), Pearl (0.906 ->
  0.945) and Iron (0.632 -> 0.693); Candy 1.05, Cake flat 0.95-1.05, Manacles 0.95 (4 views each).
  DEV agrees (Scell 0.870 -> 0.895, Zargon 0.877 -> 0.912). gef10 13j's 0.97-0.99 box sizes were the
  same fact at another camera distance.
- **The anchor** (the drawn sprite centre minus the projected point of item-class.md 8a's sub/16
  cell, the camera on our still cell, the GAT altitude): FIT median **(-4, +2) px** over 192 clear
  samples from 13 floor items (aged >= 2.5 s, >= 1 s before the vanish, clear of our box, our bar,
  every unit, other items, models, terrain, >= 30 px from the UI and the edge); DEV (-5, +2) (73
  samples, 6 items). Around it (the colour fit, FIT, 184 clear fits): median |dx| 1, |dy| 1 px, p90
  5 / 2 px, 84 % within 3 px; DEV 1 / 1 px, 87 %. The sub-cell table needs no re-measure.
- **Off the prediction:** items lying on a conveyor belt and items far from us (5-13 cells) are
  drawn up to ~6-12 px off (by eye: a Scell on a belt ~10 px higher; p31 frame 160's Scell at a wall
  edge ~13 px higher); a +-6 px search misses them, +-10 px catches most.

**O.1c The fall and the vanish (FIT, by eye on 36 views younger than 3 s; 1 fps, so few).** Drawn at
its final spot at 0.56 s and 0.81 s (the two views where that spot showed), not yet at 0.045 s
(one); most views younger than ~1 s are covered by the dying monster and the hit flashes.
item-class.md 8a's frozen margins (settle 2.2 s, gone 0.6 s, measured on prt_fild08: the fall +
display ~1 s) cover it.
For the runner, the item has lain ~2.2 s when the loot step starts (the kill is noticed 1.96 s after
the death, the drop came 0.25 s before it).

**O.1d What covers an item at the runner's moment (FIT + DEV, BY EYE: the first still frame aged
2.0-3.6 s of each fall; 33 of the 34 falls have one).**

| | views | what |
|---|---|---|
| visible | 15 | whole on the floor beside her, below her bar, under a belt's edge |
| partly | 10 | under the bar's edge, a Cruiser's limb, a hit flash, a damage text |
| **hidden** | **8** | **5 behind her own body: EVERY drop on (0,+1)**; 2 behind a live Cruiser on the next cell; 1 under the mouse cursor (the loot hover's hand) |

- Over every still view aged >= 2.2 s (geometry, FIT 422 views): clear 197, under a model box 95
  (mostly low belts: most still visible), under our bar 87 (the old 72 x 24 px bar box), under a
  unit 24, inside a UI window 17, under our body 15.
- **Our HP / SP bar, measured on FIT** (60 frames, its blue frame): **(-31, +10, +28, +18) px** from
  our anchor (gef10's assumed box was (-36, 0, +36, +24)). Items on (+-1, 0) and (0, -1) mostly
  clear it.
- Other covers seen on frames the fit refused (O.4): our NAME under the bar (shown while the
  cursor is on her), the cursor's hand, damage digits, an emote bubble.

**O.1e Presence: a projected sprite at an empty spot fits too.** The same sprite placed at an empty
ground point of the same frame (no item within 3 cells, no unit within 2, clear of our box and bar
and the UI; 2 a frame): FIT 766 such ABSENT controls, DEV 418.

| fit (scale 1.0, around the anchored prediction) | absent p95 / p99 / max (FIT) | present-clear p5 / p50 (FIT, 197) | at 0.65: absent pass / clear kept (FIT) | DEV at 0.65 |
|---|---|---|---|---|
| grey +-6 (gef10's label fit) | 0.506 / 0.598 / 0.654 | 0.597 / 0.927 | 0.1 % / 83.0 % | 0.0 % / 60.7 % |
| grey +-10 | 0.562 / 0.630 / 0.662 | 0.597 / 0.927 | 0.4 % / 90.6 % | 0.2 % / 69.6 % |
| **colour +-10 (one vector of the 3 channels)** | **0.569 / 0.612 / 0.665** | **0.616 / 0.928** | **0.26 % (2 / 766) / 90.2 %** | **0.0 % / 79.5 %** |

- DEV's lower kept share is one floor item: a Manacles (24 views) fits at 0.34-0.75 (median 0.59);
  FIT's Manacles fits at 0.58-0.77 (median 0.77, 21 views). Manacles' best scale is 0.95 on both
  (4 views each). A per-item limit (O.14).

#### O.2 What this means, before any design (for the parent and Batt)

1. **Labels from packets work for items here:** at scale 1.0 and the FIT anchor the drawn item sits
   within 1 px (median) of the prediction, and a colour fit separates present from absent at 0.65.
2. **The runner's moment is the hard case:** at ~2.2 s the item lies on the cell next to her, often
   partly under her bar, a monster's limb or a flash; **1 in 6 drops (the (0,+1) cell) lies fully
   behind her own body** -- no model can see it. The runner must hover that one cell (O.10), not skip.
3. **The kill's drop cell is known:** it is the death cell (92 % of items; the rest at (+1,-1)), and
   the death cell is the target she was striking. The detector answers "is there something on it".
4. **A label rule that excludes every covered frame keeps few frames of the runner's moment** (O.4:
   10 of 34 falls have a kept label at age 2.2-4.0 s), so the item model learns mostly items lying a
   few cells away. Whether it boxes the covered ones is what the held-out per-episode bar (I2) and
   the runner's shadow pilot measure.

#### O.3 The label rule `xmas02-fi-1` (PROPOSED; every value fixed on FIT p31)

- **(a) The floor span** (item-class.md 3a, frozen there): an item is on the floor from its
  `floor_item_appear` (either kind) to its `floor_item_vanish` or our map change. On a frame at
  capture time t: LABELLED when t_a + 2.2 s <= t < t_v; the FRAME is excluded while t_a <= t < t_a +
  2.2 s (`item_settling`) and while t_v <= t < t_v + 0.6 s (`item_vanishing`; it covers the 1d's 120
  ms). Only the monsters' candidate frames (4g: our character still; GM windows, map changes,
  `ui_layout_mismatch` out).
- **(b) Where:** the cell (x + OX[sub_x], y + OY[sub_y]) with item-class.md 8a's frozen sub/16 table,
  projected like a monster's anchor (the camera on our cell at tw = t - 120 ms, the GAT altitude),
  **+ the ANCHOR (-4, +2) px** (O.1b; FIT).
- **(c) The box: the item's OWN client sprite** (its one frame; gef10-detector.md 8's fix of
  item-class.md 8b's too-small template boxes) **drawn at scale 1.0** (O.1b), moved by the best
  **masked COLOUR NCC within +-10 px** (O.1e; +-6 cut visible items on belts and far cells). Below
  **T_item = 0.65** or at the search edge: `item_unfit`.
  - T_item's rule, fixed with the table above: the smallest value on a 0.05 grid whose FIT
    absent-control pass rate is <= 0.5 %. Grey and +-16 are reported, not chosen.
- **(d) Frame exclusions** (a frame is written only when every item in it is labelled; reasons
  counted): `item_settling`, `item_vanishing`, `ui_partial` / `edge_partial` (wholly inside a UI
  window or off the region: not drawn, no label), `stacked` (two item boxes IoU >= 0.5),
  `under_self` (our self box, labels_v2's 34 x 74 + 4 px), **`under_bar` (the FIT-measured bar
  (-31, +10, +28, +18) px)**, `under_unit` (the generic unit box at tw and tw - 0.5 s, gef10 round 3
  4a), `item_unfit`, `item_unsprited` (an id without a sprite; none on this map).
  Under a model or terrain box: kept only when (c) passes (o3h for items, as gef10 8).
- **(e) One class, `floor_item`, for every item id.** The runner needs "something lies there"; the
  item's identity stays with the inventory icons (as gef10 round 3's option C, Batt 2026-10-29).
- **(f) A frame with no floor item on the floor and none settling or vanishing is a NEGATIVE** (no
  item label), whatever else is in it.
- **(g) Frozen at acceptance** in `/dev/shm/poring-lab-tmp/xmas-fi/params.json` (its sha256 in the
  accepting amendment): the anchor, the scale, the fit and its radius, T_item, the bar, the margins,
  the sub table, the sprite files' sha256, the tool's commit.

#### O.4 The rule on FIT and DEV (dry run, `fi_rule.py`; per frame keep / exclude)

| | FIT p31 | DEV p38 |
|---|---|---|
| candidate (still) frames | 938 | 991 |
| frames with a floor item on the floor, settling or vanishing | 379 | 201 |
| **frames kept with >= 1 item label** | **204** | **91** |
| **item labels kept / floor items** | **233 / 15** | **95 / 10** |
| by id | Scell 118, Candy 34, Pearl 27, Zargon 21, Cake 17, Iron 16 | Scell 71, Zargon 21, Red Herb 2, Manacles 1 |
| labels within 1 cell of her / 2-5 cells / farther | 61 / 59 / 113 | 24 / 52 / 19 |
| labels under a model box (kept by the fit) | 15 | 33 |
| frame exclusions (a frame may carry several) | item_unfit 99, under_bar 43, item_settling 42, under_unit 24, under_self 21, item_vanishing 1 | item_unfit 57, item_settling 33, under_bar 28, under_self 16, under_unit 11, item_vanishing 6 |
| item-free kept frames (negatives) | 575 | 779 |
| **Route M: also whole for MONSTERS** (the frozen o3h-t labels of the same frames) | **84 frames / 109 labels (41 %)** | **47 / 50 (52 %)** |
| falls with a kept label aged 2.2-4.0 s / at any age | 6 / 15 of 19 | 4 / 10 of 15 |

- **Why frames are not monster-whole (FIT, among the 204):** a monster `engaged` 116, `dying_in_view`
  19, `occluded_model` 16, `next_move` 8, other 9. The fight is where drops are.
- **What `item_unfit` is:** by eye, on 35 views of frames excluded ONLY by it (FIT + DEV, the first
  dry run at scale 0.95): 22 really covered (the cursor's hand, our name under the bar, damage
  digits, an emote, a Cruiser, our own body), 13 visible items the fit refuses (Manacles and Iron at
  0.5-0.63, a Scell on a belt ~10 px beyond the search). The final run (scale 1.0): 43 such frames on
  FIT (25 at the search edge; Scell 32 views, Manacles 9) and 27 on DEV (20 views the one Manacles).
  They cost frames, not wrong labels.
- **The geometric check (G2's form, gef10 round 3 4.3):** the median |dx|, |dy| of the clear views'
  colour fits at the anchored prediction: FIT 1 / 1 px (184 fits), DEV 1 / 1 px (52): PASS (<= 3 px).

#### O.5 T2-items: the blind check (two NEW labellers)

- **The pack (seed 61; 63 is the held-out evaluation's; salt `xmas02-fi`):** from the kept labels of
  FIT + the TRAIN sessions admitted when the pack is built (O.6), **at most 3 crops per floor item**:
  - **N (near) 15 crops:** labels within 1 cell of our cell (the runner's case);
  - **F (far) 15 crops:** labels 2+ cells away, clear of every model box;
  - **M (models) 10 crops:** labels under a model or terrain box, kept by the fit;
  - **E (empty) 20 crops:** 10 plain absent points (O.1e's rule) and 10 HARD ones (the absent points
    with the highest colour fit on TRAIN frames: floor patterns and decorations that look like loot);
    the box the size of a random drop of the map.
  - Mixed in one seeded order; the strata's sizes not stated in the pack.
- **The crops:** item_labels' form (96 x 96 around the box, x3, plain and boxed side by side, a cyan
  rectangle). **`reference.png`:** the 28 distinct floor sprites of the map's drop tables, each at
  native size x3 on the floor's orange and pale tiles, no names (client pixels: generated at pack
  time, its sha256 recorded before the labellers).
- **The instructions: `docs/planning/xmas02-item-blind-instructions.txt`, sha256
  `cff8ee8b7e738c13357c680072f9ce39762b652403a86a15ef462ff50e5fcdf5`** (committed with this
  proposal, unused until accepted): gef10's item instructions (`7d0a9704...`) plus the scene, the
  covers (bar, name, cursor, flashes), `reference.png`, and a `note` field.
- **The bars (gef10-detector.md 8, unchanged), from EACH labeller:** good box (q1 yes AND q2 good)
  >= 90 % on the 40 item crops AND item-present right (yes on an item crop, no on an E crop;
  `unsure` is wrong) >= 95 % on all 60. Per stratum reported.
- **Pre-registered fallbacks (each labeller):** N's good box < 90 % while F + M pass -> frames with a
  kept label within 1 cell of her do not train; M's < 90 % while N + F pass -> frames with an
  under-model label do not train. Any other failure: no item class this round (reported to Batt).
- Labellers: two NEW blind agents (letters assigned at launch; none of A-L), M9's brief form.

#### O.6 The data plan and the split (fixed at acceptance, before any new recording)

| role | sessions | what it gives (FIT / DEV dry run; estimates for the rest) |
|---|---|---|
| FIT -> **VAL** (monitor only, after re-labelling with the frozen file) | p31 | 204 frames / 233 labels / 15 floor items |
| **TRAIN, banked** | p38 (DEV) + p20 + p39 (UNTOUCHED), each by the join rule | p38 91 / 95 / 10; **estimates** p20 ~100 labels (211 still views x FIT's 0.55 kept share), p39 ~30 (62 x 0.5) |
| **TRAIN, new** (decision O-D4) | **fs1**: one immune STAGED-DROP watch, recorded 1 fps PNG | ~100 staged floor items of the map's 12 common ids, ~6 a spot, 18 non-TEST stands (3a), views at (0,0), (3,0), (0,3) (gef10 E3's design) |
| **HELD-OUT** (refused by name until the model is frozen) | **fiT1, fiT2**: two FRESH base pilots recorded 1 fps PNG beside the runner (fiT3 if I2 is short) | ~12-18 drops a run, ~1-2 labelled frames each (`--loot-first` picks at ~3.8 s); ~8-10 episodes and ~25-30 labels a run |
| not used | p30 (GPU video) | -- |

- **The join rule (3c's form, for items):** a session joins TRAIN only with the frozen tool and
  params, 3c's recording path, and its own G2 (the median |dx|, |dy| of its clear views' fits) <= 3
  px on >= 30 fits; else not admitted (reported). TEST, gw3, FIT and the fiT sessions are refused by
  name.
- **Why fs1 (cheapest per label):** a recorded base pilot gives ~25-30 labels (the base picks fast);
  a staged watch gives ~100 floor items covering the drop SET evenly (FIT's kept labels are 51 %
  Scell, DEV's 75 %), on many floors, with drops landing on HER 3 x 3 as kills' drops do. **Clean:** group 20
  has `item` (and `monster`, `killmonster2`, `monsterignore`; no `@dropall` / `@itemmap`), so items
  come from `@item` and the inventory's known drop path (`stage_items.py`, E3 / stage@6); **no
  xmas_dun02 species loots** (AI types 17 / 5 / 3 / 4 / 21; looters are 02 / 07); staged items are
  never income (a separate immune session, no hunting; they expire in 60 s), and the Rogue is immune. **Needs:** the
  store step first (`clear_loot` drops WHOLE stacks: her Scell / Zargon stock must be in storage),
  a `MAP_SETS["xmas_dun02"]` entry and its masked icon set (`cut-grf`, offline), the MVP clock (each
  spot's `@killmonster2`).
- **The stopping rule:** after the banked TRAIN + fs1: >= 300 floor_item boxes in written frames
  from >= 40 floor items, with >= 8 ids at >= 10 boxes each -> stop; else fs2 (the next 18 stands).
- **Disk:** fs1 ~4 GB, fiT1 / fiT2 ~3.3 GB each; one at a time, each shipped and verified before the
  next (root free 80.78 GB at 10:17 `df -B1`; the floor 30 GB).

#### O.7 The model: (a) xmas02-gb + a floor_item class, or (b) a separate item model

| | (a) one model: class 8 `floor_item` added, retrained from xmas02-gb's last.pt | **(b) a separate model `xmas02-fi` (one class), its own round** |
|---|---|---|
| frames that can train | **Route M only**: an item frame must also be whole for the monsters (O.4: 41-52 % of the item frames; the fight is the drop moment, and E0 excludes the engaged unit); each hunting session must also pass 3c's monster C1 | every item-whole frame (100 %) + item-free negatives (hunts, and the immune watches xw2 / xw3 / gw2: no drops) |
| risk to the deployed monster / Garm Baby model | retrained: every M11 bar must be re-scored (Q1c pooled TEST, Garm Baby Q1s on gw3), and the Fly Wing rides on it | **none: xmas02-gb is untouched** |
| inference | one call; items in every watcher detection | a second model, called ONCE per kill (the loot step), on the same detect server (it already serves several GPU_WEIGHTS models by name) |
| GPU time a call (the Arc, FP32; bot-server-migration.md 16-19) | +0 (the head grows 12 -> 13 channels) | +~16 ms server forward (~21 ms the bot's call, D1 p50 20.6 / p95 23.7 ms) per kill: ~62 calls, ~1.3 s a 25-min run |
| CPU fallback (onnxruntime, 4 threads, quiet: 168.5 / 170.5 ms p50 / p95 for this architecture, bot-server-migration.md 2; 16 threads under load: p50 558 / p95 735 ms, M11) | +0 | +~170 ms (4 threads) per kill, inside the 2.9-s loot step it replaces |
| training (M8's 0.625 s a frame-epoch on the Arc) | (2,291 + ~250 Route-M frames) x 20 epochs ~ **8.8 h** + the monster re-evaluation ~1 h | ~1,200 frames (~600 item frames + ~600 negatives) x 20 epochs ~ **4.2 h** |
| Batt's "train it separately" | a separate ROUND, but the same model | a separate round AND model |

**Recommendation: (b).** It keeps every item frame (2x (a)'s), never touches the model the Fly Wing
relies on, needs no monster re-evaluation, and costs ~20 ms of GPU per kill. (a) would be preferred
only if items were wanted in every watcher frame (e.g. a later "loot what is seen anywhere"); then
it can follow from (b)'s labels.
- **(b)'s recipe:** YOLO11n, imgsz 1280 (native: an 11 x 12 Scell spans ~1.4 cells of the stride-8
  head), **init xmas02-gb's last.pt** (`85fb37a4...`: its backbone knows this map; no class name
  matches, so ultralytics' cls_remap seeds none and the 1-row head starts fresh), M6's settings
  (batch 2, workers 2, seed 20261004, close_mosaic 3, hsv_s 0.2, hsv_h 0.015, scale 0.1, FP32, mid
  checkpoints, the execdev launch without train-day's duty arguments), **20 epochs**; the scored
  checkpoint `last.pt` after the last completed epoch, its sha256 recorded before fiT is read.
- Classes: `config/detector/classes-xmas02-fi.json` = [floor_item] (no `player`: the runner needs
  none from this model).

#### O.8 The cache (b)

- A new labels mode (`build_frame_cache.py --labels items`, T-O2): every item-whole frame of the
  admitted TRAIN sessions (all its items as class 0) + negatives: item-free candidate frames of the
  same sessions (1 per 3 written item frames, seeded) and of xw2 / xw3 / gw2 (300, seeded: floors,
  toys and monsters with nothing to find). VAL = p31 re-labelled (monitor only). A dry run first,
  then the guarded `cache:` step (the sustained IO rule); its counts must equal the dry run's.

#### O.9 The evaluation (once, after the freeze) and its bars

- **The held-out:** fiT1 + fiT2 (+ fiT3), labelled once with the frozen file (`--eval-test`); a pack,
  seed 63, every kept label up to 60 (<= 3 a floor item) + 20 E crops, two NEW labellers, O.5's
  instructions; a crop is EVALUATED when both say yes / good. Both the item model's GPU weights and
  its ONNX predict the same frames (predict_dir in the worker; conf 0.25).
- **Bars (every one must pass; fewer rows than its minimum -> NO VERDICT, never a pass):**
  - **I1 per crop:** recall >= 0.85 on >= 40 evaluated crops (a floor_item box >= 0.25 whose IoU with
    the crop's box is >= 0.3 or whose centre lies in it); **precision >= 0.85** over every floor_item
    box >= 0.25 on fiT's labelled frames, counting a box TRUE when it lies on a packet item on the
    floor (kept or not: a covered item is not a false box), FALSE when no item lies within 1 cell.
  - **I2 per EPISODE (the runner's view):** of fiT's drops from our kills with >= 1 kept-label frame,
    the share boxed in their FIRST such frame >= 0.80, on >= 20 episodes (fiT3 if short; a second
    short count is NO VERDICT). Reported beside: the (0,+1) drops (never labelled: behind her).
  - **I3 false items on item-free frames:** fiT's candidate frames with no floor item on the floor
    (packets): frames with a floor_item box >= 0.25 <= 1 per 200; inside the 5 x 5 around her <= 1
    per 500.
  - **I4 the runner's moments:** at each fiT kill WITHOUT a drop, the first frame 2.0-3.0 s after the
    death: a floor_item box on the death cell's 3 x 3 in <= 5 % of them (>= 40 such kills).
  - **I5 latency:** the GPU call p95 <= 35 ms (the worker, fiT's frames, as D1); the CPU ONNX p95 <=
    1.10 x the deployed xmas02gb's in one interleaved run (M10 (c)).
  - **(a) only, I6:** M11's bars on the new model (the four species' Q1c on pooled TEST each >= 0.80
    and precision >= M11's - 0.03; Garm Baby Q1s on gw3 >= 0.80 / 0.80). Under (b) the deployed model
    is untouched and I6 does not apply.
- **The verdict:** PASS when every bar holds; deploying it and the runner change stay Batt's.

#### O.10 The runner change it enables (a SKETCH, not code; its own pre-registration in rogue-xmas02.md)

- **`--loot-sight` (dungeon@9.20):** after a kill (exp line or hit gap), the death cell D = the lock's
  cell (the target she was striking; next to her in 218 / 221 kills). Grab a fresh frame, call the
  item model once (GPU; CPU fallback).
- The boxes -> cells (the box's centre minus the anchor, matched to the projected cells of her 5 x 5
  within ~12 px).
- **The plan:** hover the boxed cells of the 5 x 5, nearest first; **plus D when D = (0,+1)**
  (behind her body: 16 % of kills, where no box can be expected; one hover ~0.35 s); plus D + (+1,-1)
  when D is boxed or hidden (where a two-item drop puts its second item: 6 of 68 drops).
- **No box and D not hidden -> no hover at all** (`loot_skip` logged).
- **First a SHADOW pilot** (the 9 hovers unchanged; the item model's verdict logged at each kill;
  packets the referee): false skips (a drop present, no box, D not (0,+1)) <= 5 % of drops; skips
  on empty kills >= 80 %. Then the live A/B against the base: E1 kills / h and items / h, L1 / L3.
- **The estimate** (O.1a + the Study after p44): ~44 empty kills a run x ~2.7 s saved (2.9 s -> a
  frame and one call, or one hover when D = (0,+1)) + ~18 drop kills x ~1.5 s (only the boxed cell
  hovered) ~ **120-145 s a 25-min run (~8-10 %)**, before the false-skip losses the shadow pilot
  measures.

#### O.11 The tools (offline, a tmpfs worktree, tests and a positive case each; after acceptance, before fs1)

| # | what | positive case |
|---|---|---|
| T-O1 | the item label pass for xmas_dun02: gef10_items' freeze / label / g2 generalised by map (the item sprite dir and resname table, scale 1.0, the colour fit, T_item, the bar), `--eval-test` for fiT | a FIT frame with a known item at its prediction (p31 frame 1157: a Scell at (-6,-2), colour fit 0.938 at (-1, +1) px); this dry run's FIT counts reproduced (204 / 233 / 15) |
| T-O2 | `build_frame_cache.py --labels items` (item-whole frames + seeded negatives, one class) | the dry run's counts = the label files' |
| T-O3 | `pack` for items (strata N / F / M / E, hard negatives, `reference.png` from the sprites) + `item_blind_score.py` per stratum | a synthetic answer file per stratum |
| T-O4 | `stage_items.py` `MAP_SETS["xmas_dun02"]`: the 12 ids with the most expected drops (rates x p44's sight mix): Scell 911, Zargon 912, Well-baked Cookie 538, Piece of Cake 539, Manacles 1098, Red Herb 507, Candy 529, Iron 998, Pearl 722, Candy Cane 530, Rough Oridecon 756, Holy Scroll 12001; groups of 6 a spot; its `cut-grf` icon set; the spots on non-TEST stands | the icon proof (`drop`, rc 0) live, before fs1 |
| T-O5 | the evaluation: I1-I4 from labels, packets and predictions | a staged frame list with a known count |
| T-O6 | (deployment, later) `GPU_WEIGHTS["xmas02fi"]`, the loot step's call (its own pre-registration) | -- |

#### O.12 Decisions for the parent / Batt

| # | decision | proposed default |
|---|---|---|
| O-D1 | **(b) a separate item model or (a) a class in xmas02-gb** | **(b)** (O.7) |
| O-D2 | the rule `xmas02-fi-1` with FIT's values (anchor (-4, +2) px, scale 1.0, colour fit +-10 px, T_item 0.65, the measured bar, item-class's 2.2 / 0.6 s) | adopt; frozen at acceptance (O.3 (g)) |
| O-D3 | the split: FIT p31 -> VAL; DEV p38 + UNTOUCHED p20 / p39 -> TRAIN by the join rule; p30 out | adopt |
| O-D4 | **fs1, a staged-drop immune watch** (store step + icon set first; ~1 h live with the prep) | yes; the alternative is 2-3 more recorded base pilots (~25-30 labels each, Scell-heavy) |
| O-D5 | **the held-out: fiT1 + fiT2**, fresh recorded base pilots (fiT3 if I2 is short) | adopt (they can be the day's ordinary base pilots, recorded) |
| O-D6 | T2-items: strata N / F / M / E, the bars, the two fallbacks | adopt |
| O-D7 | epochs 20; classes [floor_item]; init xmas02-gb last.pt | adopt |
| O-D8 | the bars I1-I5 (I6 only under (a)) | adopt |
| O-D9 | the runner change: a shadow pilot before any skip goes live | adopt (rogue-xmas02.md's own pre-registration) |

#### O.13 Time and GPU (estimates)

- **Tools:** T-O1-T-O5 ~1 day of agent time (gef10_items holds most of T-O1 / T-O3).
- **Live:** fs1 ~1 h (the store step, the icon proof, a ~40-min watch, the ship); fiT1 / fiT2 2 x 25
  min (base pilots, recorded); ~11 GB written, shipped one at a time.
- **Labels, T2:** ~5-10 min CPU a session; two labellers ~30 min.
- **GPU, (b):** ~1,200 frames x 20 epochs x 0.625 s ~ **4.2 h** (one execdev step, inside 12 h); the
  cache ~10 min; the export + evaluation ~1 h with the labellers. **(a): ~8.8 h + ~1 h** re-scoring.
- **Calendar:** ~1.5-2 days from an accepting amendment.

#### O.14 What looked wrong, and the limits (recorded)

1. **One Manacles fits poorly** (DEV: median 0.59 at scale 1.0, 24 views; FIT's 0.77; best scale
   0.95 on both): a per-item drawing difference not understood; such frames fall to `item_unfit`
   (20 of DEV's 27 unfit-only views), so Manacles (a 9 % Cruiser drop) may be thin in TRAIN. fs1
   stages it; I1 / I2 report it apart.
2. **Belts and wall edges:** items on a conveyor belt or beside a raised block can be drawn ~10-13 px
   off the GAT projection (p31 frame 160); +-10 px catches most, the rest are `item_unfit`.
3. **The deployed moment is under-sampled** by a rule that excludes covered frames (10 of 34 falls
   labelled at age 2.2-4.0 s): I2 and the shadow pilot test it; teaching covered items would be its
   own amendment (N1's visible-share approach).
4. **The fall** was seen by eye on 3 clear views only (1 fps); the 2.2-s settle is conservative.
5. **Absent controls are a sample of empty floor near her**, not the hard places (toy models,
   decorations): T2's hard negatives and I3 / I4 cover those.
6. **The CPU fallback's environment:** at 10:11 `/dev/shm/poring-lab-detector` held `model/` only (no
   `.venv`); not investigated (an infra observation for the parent; the live path is the GPU server).
   ➡️ CHECKED BY THE PARENT 2026-11-10 10:27 ICT: NOT a fault. `.venv` is there (a dot-directory a
   plain `ls` does not list; dated 11-07 19:20), and its python imports onnxruntime 1.31.1.
7. The O.1b / O.1e numbers are FIT's (one recording, 13-16 floor items, 51 % of its kept labels
   Scell); DEV agrees on the anchor, the scale and the fit offsets but has one bad item (Manacles);
   p20 / p39 stay untouched.

### Amendment O1 (2026-11-10 10:29 ICT from `date`, the parent, under Batt's go-ahead): Amendment O ACCEPTED with its proposed defaults

- **Authority:** Batt, before 09:40 ICT: "สอน เทรนแยกเลย เพื่อความมั่นใจและรวมเร็วในการเก็บของ" (teach
  it; train it separately, for confidence and faster looting). The parent accepts O.12's defaults:
  - O-D1 (b): a SEPARATE one-class item model `xmas02-fi` (Batt's "train separately");
  - O-D2: the rule `xmas02-fi-1` with FIT's values, frozen when its tool (T-O1) first writes the
    params file;
  - O-D3: the split (p31 -> VAL; p38 + p20 + p39 -> TRAIN by the join rule; p30 out);
  - O-D4: fs1, the immune staged-drop watch, after T-O4's live icon proof;
  - O-D5: the held-out fiT1 + fiT2 (fiT3 if I2 is short), fresh base pilots recorded 1 fps PNG;
  - O-D6: T2-items with its strata, bars and fallbacks;
  - O-D7: 20 epochs, [floor_item], init xmas02-gb last.pt;
  - O-D8: the bars I1-I5;
  - O-D9: a shadow pilot before any loot skip goes live.
  Batt may still change any of them; nothing below has trained or labelled yet.
- **Done at acceptance (before any fiT recording):** `map_labels.XMAS02_FIT` = the names
  `-rdp-hunt-xmas02-fiT1..3`, in the xmas_dun02 MapSpec's `test_suffixes` (refused by NAME for the
  monster labels, T2's pool and the cache), NOT in its `eval_suffixes` (M7's monster evaluation is
  unchanged). Test: `test_o1_the_floor_item_held_out_is_refused_by_name`.
- **Next:**
  - fiT1 is recorded beside the day's next base pilot (rogue-xmas02.md 4BF);
  - the tools T-O1..T-O5 are built offline in a tmpfs worktree;
  - then fs1, T2-items, the cache, the training, and the evaluation, in O's order.

### O2 (2026-11-10 11:1x ICT from `date`, a subagent, branch `feat/fi-tools`): the tools as built (T-O1-T-O5, offline)

> Tool usage only (O.11); nothing above is changed. Offline: FIT p31 and DEV p38 frames only (p20,
> p39, p30, TEST, gw3 and fiT were not opened); no GPU, nothing live, nothing recorded.

**The frozen params (O.3 (g), O-D2):** `fi_labels.py freeze` wrote
`/dev/shm/poring-lab-tmp/xmas-fi/params.json` once, 11:08:32 ICT, commit `e4103675`, **sha256
`d1c5606b1677d02bf494efd93bceef82fafefc78b1af7c8905efb9c965b4e315`**: anchor (-4, +2), scale 1.0,
colour fit +-10, T_item 0.65, bar (-31, +10, +28, +18), 2.2 / 0.6 s, the sub table, the 1d 120 ms
of the monster params `d4cc0a5d...`, the RSW's sha256, and the 33 drop ids' sprite files (28
distinct sprites; none unsprited). A changed sprite file refuses every later run. (`b605a1d0`
after it changes only `reference.png`'s tile colours: the rule's code is the frozen commit's.)

**The tools (each with its tests in services/backend/tests; synthetic fixtures only):**

| # | command | what |
|---|---|---|
| T-O1 | `fi_labels.py label PART --split train\|val --params P --out L.json` | O.3 per candidate frame (keep / exclude + reasons, the fitted boxes, each view's G2 flag, the session's G2); TEST / gw3 / fiT / p30 refused by NAME before any read; p31 is VAL only |
| T-O1 | `fi_labels.py label PART --eval-test --model W --model-sha256 HEX --params P --out L.json` | fiT only, FROZEN params, the model re-hashed (no model: refused); adds every floor item's boxes, the 5 x 5, our kills with their drops and each no-drop kill's 2.0-3.0 s frame |
| T-O1 | `fi_labels.py g2 L.json... --out J` | O.6's join rule per session |
| T-O2 | `build_frame_cache.py --labels items --item-params P --item-params-sha256 HEX --fi-labels L... --class-list config/detector/classes-xmas02-fi.json --train S... [--neg-sessions xw2 xw3 gw2] --val p31 [--dry-run]` | item frames whole (class 0) + negatives (1 per 3 item frames; 300 pooled from the watches, which must be item-free); join verdicts G2_PASS / NEGATIVE_ONLY / VAL_MONITOR |
| T-O3 | `fi_labels.py pack L... --params P --seed 61 --out J` (T2-items); `--eval-test --seed 63` (O.9's pack) | strata N / F / M (a partition, N first) + E (10 plain, 10 hard), <= 3 a floor item, `reference.png` from the sprites, the pinned instructions |
| T-O3 | `fi_blind_score.py --key K A.json B.json [--both-good E.json]` | per stratum; PASS / FALLBACK_NEAR / FALLBACK_MODEL / FAIL |
| T-O4 | `stage_items.py spots --map xmas_dun02 --n 18 --seed S --plan`; `cut-grf --map xmas_dun02 --table T --icons D [--check]` | stage@8: O.11's 12 ids in groups of 6, spots on the lattice's TRAIN stands with every stand off 3a's TEST blocks, one `@killmonster2` per spot after its warp |
| T-O5 | `fi_labels.py refs L... --refs-out R.json` -> predict_dir; `fi_eval.py --labels L... --predictions gpu=P onnx=Q --key K --evaluated E [--gpu-timing P --cpu-latency C --cpu-item A --cpu-deployed B] --out J` | I1-I5, every prediction set; short counts NO VERDICT |

**Positive cases (real data, frozen params):**
- FIT p31 (`--split val`): 938 candidates, **204 kept frames / 233 labels / 15 floor items**, by id,
  distance (61 / 59 / 113), under-model 15 and every exclusion count = O.4; **938 of 938 frames
  identical** to the study's `rule3` dry run; **frame 1157: Scell 911 at (-6, -2), colour fit
  0.9378 at (-1, +1) px**. Label file sha256 `32437d99...`.
- DEV p38 (`--split train`): **91 / 95 / 10** = O.4; negatives 775, not O.4's 779: four item-free
  frames now fail the layout read (O.3 (a); the dry run skipped it). Label file `e340c06c...`.
- G2 under the frozen rule: FIT 253 clear fits, DEV 89, both median |dx| / |dy| 1 / 1 px: PASS
  (O.4's 184 / 52 used the old 72 x 24 bar and the unanchored box).
- Our kills (packets): p31 61 kills, 18 with a drop; p38 53, 15 (= O.1a).
- The cache dry run on these files: p38 91 frames / 95 boxes + 30 negatives (G2_PASS), p31 204 /
  233 + 68 (VAL_MONITOR): = the label files'.
- T2-items' scorer, I1-I5: synthetic answer files per stratum and a staged frame list (tests).

**Found (for the parent; nothing decided here):**
- **The masked icon set cannot pass stage@6's write gate as it stands: Scell's icon compares 30
  item pixels, below `MIN_ITEM_PX` 40** (`cut-grf --check`, every other masked check clean; the
  set's nearest pair is Iron / Piece of Cake at 34.0, beyond 20.0). Options: a lower floor for
  this icon with its own positive case, Scell left out of fs1 (it is already 51-75 % of FIT /
  DEV's labels) with the 13th id in, or another rule. The screen-cut references of all 12 are
  missing too (a live `give --frames` + `cut` makes them).
- O.11 names 12001 "Holy Scroll": the KB's name is Level 3 Heal (aegis Holy_Scroll_1_3); same id.

**T-O4's live chain (the parent's; gef10 AK / AK-1 / AK-5's order), from the main checkout:**
the store step, then `stage_items.py held --map xmas_dun02` rc 0; `give --map xmas_dun02
--frames`; the frames judged, the SPEC written, `cut SPEC --map xmas_dun02`; `cut-grf --map
xmas_dun02 --table /dev/shm/poring-lab-tmp/xmas-fi/grf/data/idnum2itemresnametable.txt --icons
'/dev/shm/poring-lab-tmp/xmas-fi/icons/data/texture/유저인터페이스/item'` (refuses today: Scell);
the given copies stored, `held` rc 0; `give --map xmas_dun02` (no frames); **`drop --map
xmas_dun02`: rc 0 (`all_and_only_the_set`) is the icon proof.**

### Amendment O3 (2026-11-10 11:30 ICT from `date`, the parent): the tools merged; two findings decided before any new label

- **Merged:** feat/fi-tools (ddd54d6a): T-O1 `fi_labels.py`, T-O2 `build_frame_cache.py --labels items`,
  T-O3 the pack + `fi_blind_score.py`, T-O4 stage@8's xmas_dun02 set (offline part), T-O5
  `fi_eval.py`. 63 new tests; the merged label / stage / census suites pass on main.
- **The params v1** (`/dev/shm/poring-lab-tmp/xmas-fi/params.json`) were frozen 11:08:32 by e4103675:
  sha256 `d1c5606b1677d02bf494efd93bceef82fafefc78b1af7c8905efb9c965b4e315`.
  - Positive cases: FIT p31 938 / 938 frames identical to the study's dry run (204 / 233 / 15);
    frame 1157's Scell at 0.9378; DEV p38 91 / 95 / 10.
  - G2 PASSES on both: 1 / 1 px medians.
- **O2 finding 7.1 (Scell's masked icon: 30 item px, under stage@6's MIN_ITEM_PX 40):** option (b).
  - Scell leaves fs1's staged set; the next id by O.11's own ranking (drop rate x p44's sight mix)
    joins in its place.
  - AK-5's pre-registered gate is NOT lowered.
  - Scell is already 51 % / 75 % of FIT's / DEV's kept labels, so fs1 loses little.
- **O2 finding 7.2 (sprites that "fit" bare floor):** a per-id rule, fixed on FIT + DEV's 59
  empty-floor absent points.
  - An id whose sprite fits >= T_item on > 1 % of them is treated as `item_unsprited`: a frame
    holding one is excluded, never labelled.
  - Today that is Bib 7269 (74.6 %), Rough Wind 996 (1.7 %) and Holy Bonnet 2251 (1.7 %). The other
    25 sprites, the 12 staged ids included, fit 0 %.
  - It needs a **params v2** (a new file, frozen by its tool, its sha256 recorded here). p31 (VAL)
    and p38 (TRAIN) are re-labelled under v2 before the cache.
  - v1 stays as the record of the positive cases.
- **Next:**
  - v2 + the fs1 set change (tools, offline);
  - then the live icon proof (O2 section 6's chain, the store step first);
  - then fs1, the TRAIN labels (p20, p39), T2-items, the cache, the training, the evaluation on
    fiT1 + fiT2.

#### O2, addendum (2026-11-10 11:4x ICT from `date`, the subagent, branch `feat/fi-tools`): params v2 and O3's fs1 set (tools, offline)

- **Params v2 (O3's absent rule):** `fi_labels.py freeze-v2 --v1 params.json --labels <p31> <p38>`
  wrote `/dev/shm/poring-lab-tmp/xmas-fi/params-v2.json` once, 11:38:47 ICT, commit `6bd49187`,
  **sha256 `aea6f1d2b938d6fdfa1ebadc0042ba3a9ce2448f8b22f2075f0c0cb48297bb2c`** (v1 `d1c5606b...`
  unchanged, its positive cases' record).
  - The rule as recorded in it: 60 absent points of O.1e's rule on FIT p31 + DEV p38's v1 kept
    frames (seed `per-sprite`; O2's check reproduced fit for fit), each of the 28 sprites fitted at
    each (59 fits each; one point scores for one sprite only); an id whose sprite fits >= T_item
    0.65 on MORE than 1 % is `item_unsprited`. The points, every fit and each sprite's rate are in
    the file.
  - **Excluded: Bib 7269 (44 / 59 = 74.6 %, max 0.870), Rough Wind 996 (1 / 59 = 1.7 %, max 0.681),
    Holy Bonnet 2251 (1 / 59 = 1.7 %, max 0.651)**; every other sprite 0 / 59.
- **p31 and p38 re-labelled under v2:** FIT p31 204 / 233 / 15 and DEV p38 91 / 95 / 10, **the same as
  v1, 938 of 938 and 991 of 991 frames identical**: neither recording holds an excluded id (their
  floor items: 911, 912, 529, 539, 722, 998, 1098 and 507, 979). G2 unchanged (253 / 89 fits,
  1 / 1 px). Label files `e4e6995d...` (p31) and `5db250eb...` (p38) in
  `/dev/shm/poring-lab-tmp/xmas-fi/labels-v2/`.
- **The fs1 set (O3, 7.1):** O.11's ranking (drop rate x p44's sight: Myst Case 23, Cruiser 18,
  Cookie 10, Christmas Cookie 8) reproduces O.11's twelve; 13th Cold Scroll 688 (0.08), 14th Chef
  King Orleans Vol.1 11002 (0.05).
  - **688 cannot join:** its grey masked icon lies 2.34 from Holy Scroll 12001's (< ICON_AMBIGUOUS
    20): clear_loot would read both "unknown" and drop neither, so their screen-cut proof refuses.
  - **11002 joins in Scell's place** (119 item pixels; its nearest of the set 46.4). The set: 912,
    538, 539, 1098, 507, 529, 998, 722, 530, 756, 12001, 11002, in groups of 6.
  - `cut-grf --check` (it now also names the set's own ambiguous pairs): no refusal but the 12
    screen-cut references a live `give --frames` + `cut` makes; `passes_once_screen_cut: true`.

### Amendment O4 (2026-11-10 11:46 ICT from `date`, the parent): params v2 recorded; fs1's 12th id confirmed

- **Params v2:** `/dev/shm/poring-lab-tmp/xmas-fi/params-v2.json`, frozen 11:38:47 by 6bd49187.
  - sha256 `aea6f1d2b938d6fdfa1ebadc0042ba3a9ce2448f8b22f2075f0c0cb48297bb2c`.
  - O3's absent rule excludes Bib 7269 (44 / 59), Rough Wind 996 (1 / 59) and Holy Bonnet 2251
    (1 / 59) as `item_unsprited`.
  - **v2 is the rule for every label from now on.** v1 (d1c5606b) stays the positive cases' record.
  - p31 / p38 under v2: unchanged, 938 / 938 and 991 / 991 frames identical (neither holds an
    excluded id).
- **fs1's set:** 11002 (Chef King Orleans Vol.1) takes Scell's place. The 13th by O.11's ranking,
  688, is NOT usable: its masked icon lies 2.34 from 12001's, inside ICON_AMBIGUOUS 20, so
  clear_loot could drop neither. The parent confirms "the next USABLE id by the ranking". cut-grf
  --check passes offline. The 12 screen-cut references come from the live chain (O2 section 6).
- Merged: feat/fi-tools again (O2 addendum, 36 + 9 tests). The worktree is removed.

### Amendment O5 (2026-11-10 12:39 ICT from `date`, the parent, BEFORE its run): the icon proof passed; fs1 pre-registered

- **The live icon proof (O2 section 6, AK-1's order), on prt_fild08 (268,107), the Rogue immune
  (12:28:31):**
  - `clear-bag` (12:30:05-12:31:55) -> `held` rc 0;
  - `give --frames` (12:32-12:33): the 12 in the @item order. Etc row 0: zargon, manacles, iron,
    pearl, rough_oridecon, orleans_book. Use: well_baked_cookie .. candy_cane at (2-6, 0),
    holy_scroll (0, 1). Eqp empty;
  - `cut` (the parent's SPEC, `/dev/shm/poring-lab-tmp/xmas-fi/icons-spec.json`): 12 cut, none
    missing;
  - `cut-grf`: every screen-cut icon against its own GRF icon at 0.81-4.35 (bar 10.0), rc 0;
  - the viewed copies cleared (`clear-bag` 12:34:37-12:36:30), `held` rc 0, a FRESH `give`, then
    `drop` (12:38:39): **rc 0, `all_and_only_the_set` true** (12 dropped, the stock kept). THE ICON
    PROOF PASSES.
- **fs1 (O.6's staged-drop watch), as follows:**
  - when `held --map xmas_dun02` returns rc 0 (the DB's save catches up);
  - the recorder first: `record_session.py --backend rdp --label xmas02-fs1 --seconds 3300 --fps 1
    --format png --max-bytes 8G`, stopped by SIGTERM after the run ends;
  - then `stage_items.py run --map xmas_dun02 --n 18 --seed 2611101 --immune-confirmed --label
    fs1`;
  - 18 spots, 54 stands, 108 floor items (9 per id, groups of 6), the spots of `spots --plan`
    (seed 2611101): 159,38 49,60 203,225 49,104 74,72 236,48 138,115 236,82 25,173 225,181
    192,194 82,192 104,138 104,236 138,170 71,137 170,115 203,148; one `@killmonster2` at each
    spot (the MVP clock);
  - **its use:** TRAIN, by the join rule (v2 params aea6f1d2, its own G2 <= 3 px on >= 30 fits),
    then O.6's stopping rule (>= 300 boxes from >= 40 floor items, >= 8 ids at >= 10 each, with the
    banked TRAIN). Short of it: fs2 on the next 18 stands;
  - a run that stops early (rc 1) is reported as is, and not re-run without a reason.
- **Disk:** ~45 min of 1-fps PNG, ~5.7 GB, on top of fiT1 3.42 + fiT2 3.50 GB unshipped. That is
  under the 20 GB cap and far over the 30 GB floor (73.8 GB free at 12:30). It ships after the
  SET close with the others. ➡️ Shipped 14:54-14:58 at once (O8: no market waits on bot-server).

### Amendment O6 (2026-11-10 13:20 ICT from `date`, the parent): fs1 done; the TRAIN joins; the stopping rule MET

- **fs1:** `stage_items.py run --map xmas_dun02 --n 18 --seed 2611101 --immune-confirmed --label fs1`.
  - 12:42:33-13:17:48, rc 0, reason "done": 18 spots, 108 items staged, one `@killmonster2` at each
    spot (12:42:52 .. 13:16:03).
  - The recording `20261110T124228-rdp-xmas02-fs1`: PNG, 2,154 frames, 4.63 GB, 2,981 packet
    events; stop "stopped by signal" at 13:18:24.
  - A slip, recorded: the parent's `A && B & RP=$!` backgrounded the whole list, so the planned
    TERM at 13:17:53 hit the subshell. The recorder itself was stopped by its PID 31 s later. The
    frames after the run's end show the last spot only.
- **The TRAIN labels under v2 (aea6f1d2) and the join rule (G2 <= 3 px on >= 30 fits):**

| session | kept frames | labels | floor items | G2 (median dx / dy, within 3 px) | join |
|---|---|---|---|---|---|
| p38 (DEV) | 91 | 95 | 10 | 1 / 1 px | ADMITTED (O3's re-label) |
| p20 | 57 | 82 | 8 | 1 / 2 px, 31.2 % | ADMITTED |
| p39 | 20 | 23 | 5 | 1 / **4** px, 19.4 % | NOT admitted (G2 FAIL) |
| fs1 | 143 | 701 | 68 | 0 / 1 px, 96.2 % (2,172 fits) | ADMITTED |
| p31 (FIT) | 204 | 233 | 15 | 1 / 1 px | VAL (monitor only) |

- fs1 by id: Holy Scroll 89, Rough Oridecon 78, Candy 71, Pearl 67, Red Herb 62, Orleans book 60,
  Candy Cane 56, Manacles 54, Cake 52, Cookie 50, Iron 50, Zargon 12.
  - By distance: within 1 cell 75, 2-5 cells 626.
  - Exclusions: ui_layout_mismatch 579, item_unfit 389, under_bar 164, under_self 136, stacked 49,
    under_unit 48, vanishing 35.
- **O.6's stopping rule:** TRAIN = 878 boxes (p38 95 + p20 82 + fs1 701) from 86 floor items, with
  12 ids at >= 10 boxes. That is over >= 300 / >= 40 / >= 8 ids: **MET. No fs2.**
- **Next:** T2-items (O.5: the pack from the TRAIN label files, seed 61, two NEW blind labellers,
  the bars and fallbacks), then the cache, the training (O-D7) and the evaluation on fiT1 + fiT2.

### Amendment O7 (2026-11-10, Batt's answer received by 13:38 ICT from `date`): O's defaults CONFIRMED

- Batt, to the 13:24 report's item 9.1 (the parent's O1 choices: a separate item model, the
  staged-drop watch, the held-out fiT1 / fiT2, the bars I1-I5, Scell -> 11002 in the staged set):
  "ทำได้เลย" (go ahead). O1's acceptance stands as Batt's. The queue is unchanged: the recordings
  ship after the SET close, then T2-items (seed 61), the cache, the training, the evaluation.

### Amendment O8 (2026-11-10 15:04 ICT from `date`, the parent): the recordings shipped; T2-items started

- **Shipped at once** (Batt 14:5x: no market waits on bot-server; `dataset_ship.py` gates SET hours
  on shared hosts only since d62eba78), each verified on the NAS, local copy deleted:
  - fs1 14:54:42-14:58:09 (19 files, 4.63 GB);
  - fiT1 14:58:09-;
  - fiT2 -15:03:33 (14 files, 3.50 GB).
  Root free 80.72 GB after.
- **T2-items pack** (O.5, seed 61; `fi_labels.py pack`, built 15:03:36 from main d62eba78):
  - from the TRAIN label files under v2: p38, p20, fs1;
  - 60 crops = N 15 / F 15 / M 10 / E 20 (10 plain + 10 hard; hard fits 0.525-0.603), 40 floor
    items, at most 3 crops each;
  - reference.png from the 28 sprites (6a665d79...); instructions cff8ee8b...;
  - answer key sha256 368d66f3f5cce5ea... (never shown to a labeller).
- Labellers: two NEW blind labellers, I and J (subagents that see only the pack). J starts when an
  agent slot frees (at most 2 agents at once). Scored by `fi_blind_score.py` with O.5's bars and
  fallbacks, once, when both have answered.

### Amendment O9 (2026-11-10 15:10 ICT from `date`, the parent, BEFORE the cache or any GPU step): the item cache and the training, pre-registered

- **Runs only if T2-items passes** (O.5's bars from both labellers I and J, or a pre-registered
  fallback; scored once by `fi_blind_score.py`).
- **The negatives' label files** (made 15:07-15:09 under v2): xw2 1,589 frames, xw3 932 + 678, gw2
  749. All are item-free: 0 floor items in their packets.
- **The dry run (15:1x, `build_frame_cache.py --labels items ... --dry-run`):**
  - TRAIN: 687 frames, 291 item frames / 878 boxes (p38 95, p20 82, fs1 701) + 396 negatives (1
    per 3 item frames from each item session + 300 pooled from xw2 / xw3 / gw2, seed default).
  - About 1.44 GB in 7 shards. VAL p31 (monitor only). `would_refuse_join` empty. 86 floor items.
- **The cache step (the dry run's command without `--dry-run`, from the main checkout):**

      L=/dev/shm/poring-lab-tmp/xmas-fi/labels-v2; P2=/dev/shm/poring-lab-tmp/xmas-fi/params-v2.json
      N="20261106T151122-rdp-xmas02-xw2 20261106T154241-rdp-xmas02-xw3 20261106T160700-rdp-xmas02-xw3 20261109T210933-rdp-gb-gw2"
      python3 scripts/guarded_build.py --threshold 30 --sustain 30 "cache@7200=--labels items \
        --item-params $P2 --item-params-sha256 aea6f1d2b938d6fdfa1ebadc0042ba3a9ce2448f8b22f2075f0c0cb48297bb2c \
        --fi-labels $L/<p38>.json $L/<p20>.json $L/<fs1>.json $L/<p31>.json $L/<xw2>.json $L/<xw3a>.json $L/<xw3b>.json $L/<gw2>.json \
        --class-list config/detector/classes-xmas02-fi.json \
        --train <p38> <p20> <fs1> $N --neg-sessions $N --neg-total 300 --val <p31> \
        --cache-id xmas02-fi-20261110 --image png"

  The written counts must equal the dry run's; a difference stops before any GPU step.
- **The training (O-D7; M6's recipe and launch path):**
  - one class [floor_item], 20 epochs, batch 2, workers 2, FP32 on the Arc, `--mid-ckpt`;
  - the init is xmas02-gb's `last.pt` (85fb37a4). The class head has 1 row, which matches no name
    of the init's, so it starts fresh; the backbone and neck are seeded;
  - hsv_s 0.2, close_mosaic 3, scale 0.1;
  - command:

        python3 scripts/guarded_build.py --threshold 30 --sustain 30 \
          "execdev:vision@43200=python -m poring_vision.train --cache /datasets/.framecache/xmas02-fi-20261110 --epochs 20 --batch 2 --workers 2 --name xmas02-fi-20261110 --mid-ckpt --weights /datasets/archive/train/xmas02-gb-20261109/weights/last.pt --hsv-s 0.2 --close-mosaic 3 --scale 0.1"

  - estimate: 687 frames x 20 epochs x 0.625 s (M8's rate) = ~2.4 h;
  - its log's transfer / remap lines are recorded as the check.
- **After it:** the scored model is frozen as M8 was. Then the evaluation, once: I1-I5 on fiT1 +
  fiT2 (`fi_labels.py label --eval-test`, `fi_eval.py`, the T2 pack seed 63 for I1's crops). Then
  `--loot-sight`'s pre-registration (a shadow pilot first).

### Amendment O10 (2026-11-10 15:12 ICT from `date`): T2-items PASSES -> the cache and the training run (O9)

`fi_blind_score.py --key <key> I.json J.json` (score sha256 9952dfc545cbcb76...), once:

| labeller | good box, 40 item crops (>= 90 %) | item present right, 60 crops (>= 95 %) | E (empty) right | verdict |
|---|---|---|---|---|
| I | 95.0 % (N 93.3, F 93.3, M 100) | 96.7 % | 20 / 20 (10 hard) | PASS |
| J | 95.0 % (N 93.3, F 93.3, M 100) | 96.7 % | 20 / 20 (10 hard) | PASS |

- The two labellers agree on all 60 crops (q1 and q2). Their only misses are the same two "unsure"
  item crops: 014, a brown blob at a monster's hand; 039, a dark item matching no reference.
  No "loose", no "off".
- Both labellers were blind: they saw only the pack (reference.png, 60 crops, the pinned
  instructions), never the key or each other.
- By O9: the cache step and the training run now.

- **O10, the run (by 15:18 ICT):**
  - the cache 15:12-15:17:35, OK: `/mnt/poring-lab-datasets/.framecache/xmas02-fi-20261110`, 959
    frames, 9 shards, 274.3 s. Every count equals the dry run's (TRAIN 687 / 878 boxes / 396
    negatives; VAL 272 / 233 / 68);
  - the training launched 15:18:02 (unit `poring-train-xmas02fi`,
    `/dev/shm/poring-lab-tmp/xmas-fi/train/launch.sh`, O9's command verbatim), the init's sha
    re-checked (85fb37a4);
  - the log: "Overriding model.yaml nc=8 with nc=1", "Transferred 493/499 items from pretrained
    weights" (the 6 = the class head, fresh as O9 says), 687 train / 272 val images, 2 workers,
    20 epochs.
- **O10, the training's first epochs (by 16:18 ICT):**
  - epoch 1: 3,019 s. Its validation took ~45 min at ~40 s a batch ("NMS time limit exceeded"):
    the fresh 1-class head floods NMS with low-confidence boxes;
  - epoch 2: 554 s with validation (val recall 0.51, precision 0.78);
  - the rest at ~9 min an epoch -> the end ~19:00 ICT, far inside the step's 12 h;
  - nothing changed in the recipe.

### Amendment O11 (2026-11-10 18:20 ICT from `date`, BEFORE any fiT read): the item training ended; THE SCORED MODEL FROZEN

- `train ended rc=0` at 18:19:15 ICT (started 15:18:02): all 20 epochs, 10,805 s, FP32 on the Arc,
  the guard's worst stall 0.0 %.
- VAL (FIT p31, monitor only) at epoch 20: P 0.960, R 0.906,
  mAP50 0.977, mAP50-95 0.683.
- **The scored checkpoint:** `data/train/xmas02-fi-20261110/weights/last.pt` after epoch 20, **sha256
  `e24e8f57548a3a6791b9756207fb2ffb11a8a0273c92db07f3bbcbe2196011a5`** (5,531,418 bytes). Nothing is refitted after this line.
- Next, in O.9's order: the ONNX export (M9's recipe), fiT1 + fiT2 labelled once with `--eval-test`,
  the eval pack (seed 63) and two NEW blind labellers, the predictions (GPU weights + ONNX, conf
  0.25), `fi_eval.py` I1-I5, once. The run is archived to the NAS (archive/train/xmas02-fi-20261110).

### Amendment O12 (2026-11-10 18:29 ICT from `date`, BEFORE any labeller answer or prediction on fiT): the export; fiT3 is added

- **The ONNX export (M9's recipe, a temporary RAM env, removed after):**
  `/dev/shm/poring-lab-detector/model/xmas02fi-last-736x1280.onnx`, sha256 `d149b3a759dd1c31...`;
  names `["floor_item"]` (d31e3c6c...).
- **fiT1 + fiT2 labelled once with `--eval-test`** (the frozen model e24e8f57 re-hashed; params v2):
  - fiT1: 946 candidate frames, 25 kept / 25 labels / 12 floor items (26 in packets), 67 kills, 21
    with a drop;
  - fiT2: 921, 18 / 20 / 8 (21 in packets), 60 kills, 19 with a drop.
- **The seed-63 pack on them is SHORT:** 43 item crops (N 40, F 3; `short` X 60) + 20 E.
  - I1's minimum (>= 40 evaluated crops) would hang on 3 crops; I2's (>= 20 episodes) is likely
    short too.
  - O.9's own remedy is **fiT3**. It is recorded NOW, beside the next pilot (p49).
  - The eval pack is then rebuilt over fiT1 + fiT2 + fiT3 (seed 63, the same rule), and the two
    NEW labellers judge that pack only.
  - This is decided from counts alone. No labeller has seen the seed-63 pack and no prediction has
    been made on any fiT frame. The 2-session pack is deleted unseen.
- fiT3's pilot changes nothing in the loot behaviour (LF-2 / LF-4 are position-reader changes), so it
  is a held-out of the same kind as fiT1 / fiT2; its run is recorded in rogue-xmas02.md.

### Amendment O13 (2026-11-10 19:37 ICT from `date`, BEFORE any score): the held-out's labels, the evaluated crops, the predictions, and how I5 is measured

- **fiT3** (`20261110T185223-rdp-hunt-xmas02-fiT3`, beside p49): 949 candidate frames, 24 kept / 24
  labels / 5 floor items (26 in packets), 64 kills, 22 with a drop.
- **The eval pack (seed 63, fiT1 + fiT2 + fiT3):** 74 crops = 54 item crops (N 48, F 6) + 20 E.
  Labellers K and L (NEW, blind) answered all 74 and agree on 72 / 74 (q1) and 71 / 74 (q2).
  **46 crops are EVALUATED** (both yes / good; I1's minimum is 40).
- **The predictions (conf 0.25), on all 2,799 judged frames (`fi_labels.py refs`):**
  - GPU: `predict_dir` in the worker with the frozen `last.pt` (e24e8f57);
  - ONNX: the same frames through `unit_detector.UnitDetector` (the runner's CPU path), written in
    predict_dir's format by a scratch script (archived with the evaluation).
- **Registered for the GPU measure:** `unit_detector.GPU_WEIGHTS["xmas02fi"]` (the archived last.pt
  e24e8f57 + the ONNX d149b3a7 in `archive/models`; tested). It is NOT in MAP_MODELS: the runner
  never calls it.
- **I5's GPU measure, fixed here:** "the GPU call p95 <= 35 ms (the worker, fiT's frames, as D1)".
  D1 is the runner's GpuDetector call on the host's clock through the detect server (OpenVINO on
  the Arc). So I5's GPU number comes from that path:
  - the guarded serve step (`unit_detector.py serve-cmd --backend openvino`, as every pilot);
  - a client calling `GpuDetector(weights="xmas02fi")` on 300 refs frames (every 9th key);
  - the deployed xmas02gb interleaved on the same frames, reported beside it.
  predict_dir's own wall time (p50 61 / p95 78 ms: ultralytics' Python pre- / post-processing on
  torch-xpu) is reported, NOT judged.
- **I5's CPU measure:** `eval_latency.py` on the same 300 frames, xmas02fi vs xmas02gb interleaved
  (UnitDetector, 16 threads, nice 10), run on a quiet host. The bar is xmas02fi's p95 <= 1.10 x
  xmas02gb's.
- Then `fi_eval.py`, once, with both prediction sets.

### Amendment O14 (2026-11-10 20:14 ICT from `date`): THE RESULT (the held-out score, once) -- THE xmas02-fi MODEL FAILS

`fi_eval.py` on fiT1 + fiT2 + fiT3 (score sha256 93be3bab1c9fcd82...), both prediction sets, once. The GPU
(`predict_dir`, last.pt e24e8f57) and the ONNX (UnitDetector, d149b3a7) give IDENTICAL results
(112 boxes on 111 frames each):

| bar | result | bar value | verdict |
|---|---|---|---|
| I1 recall (46 evaluated crops) | 32 / 46 = **0.696** | >= 0.85 on >= 40 | **FAIL** |
| I1 precision (every box on the judged frames) | 95 / 110 = 0.864 (15 false, 2 ambiguous) | >= 0.85 | PASS |
| I2 first kept-label frame boxed (episodes) | 14 / 25 = **0.56** | >= 0.80 on >= 20 | **FAIL** |
| I3 item-free frames with a box (any / her 5 x 5) | 12 / 2,454 = 0.49 % / 3 / 2,454 = 0.12 % | <= 0.5 % / <= 0.2 % | PASS |
| I4 kills without a drop with a box on the death cell's 3 x 3 | **0 / 124** | <= 5 % on >= 40 | PASS |
| I5 CPU p95 (interleaved, 300 frames, 16 threads) | 757.3 vs xmas02gb 726.1 ms = 1.043 x | <= 1.10 x | PASS |
| I5 GPU "as D1" | NO VERDICT (below) | <= 35 ms | NO VERDICT |

- **The verdict: FAIL** (I1 recall, I2). By O.9 the model is NOT deployed and the runner's
  `--loot-sight` is not pre-registered. GPU_WEIGHTS keeps the entry (served only, never a map's
  model); a removal is a one-line change, left as it is.
- **Where it misses:**
  - all 14 I1 misses are items within 1 cell of her: N 14 / 43; F 0 / 3;
  - by item: Candy Cane 530 4 / 4, Scell 911 5 / 11, Cookie 538 2 / 4, Zargon 912 3 / 17, Pearl,
    Candy, Cake 0;
  - the missed crops' label fit is lower (median NCC 0.794 vs 0.909 for the hits): partly covered
    by her sprite / bar, though both labellers judged them good;
  - the TRAIN mix explains it: boxes within 1 cell of her are ~12 % of TRAIN (p38 24 / 95, p20 7 / 82,
    fs1 75 / 701), but 43 of the 46 evaluated held-out crops. fs1 staged from views 0-3 cells away.
- **What works:** it never boxes an empty floor where the runner looks (I4 0 / 124, I3 under its
  bars). But at 70 % recall, "skip the loot step when no box" would skip ~30 % of the real drops.
- **I5 GPU, measured as O13 fixed, NOT judged:**
  - through the guarded serve step (OpenVINO; the listening line names xmas02fi d149b3a7) and
    `GpuDetector`, one model a run (the server serves one client at a time), 300 frames;
  - xmas02fi: call p50 51.1 / p95 63.6 ms, server forward p50 16.25 / p95 16.51 ms;
  - the deployed xmas02gb, the same harness: call p50 52.4 / p95 63.8 ms, server 16.6 / 16.85 ms;
  - so the harness adds ~35 ms that the live runner does not (xmas02gb's live D1 p95 22-26 ms in
    p44-p49); the item model is NOT slower than the deployed one;
  - a first, interleaved attempt was discarded: the second client got BlockingIOError and its CPU
    fallback loaded the host;
  - predict_dir's own wall time (p50 61 / p95 78 ms) is reported only.
- **Tool notes:**
  - fi_eval reads `--cpu-latency` as `{model: summary}`. eval_latency writes it under `"ms"`, so
    its `"ms"` block was passed as it is (no number changed; the file is archived);
  - fi_eval accepts GPU timing only in predict_dir's format. Both are follow-ups for the tool.
  - ➡️ 20:19 ICT (from `date`): the first is FIXED in 212fa291 (`cpu_latency_models` reads the
    `"ms"` block itself). Re-scoring from the raw latency-cpu.json gave a byte-identical
    fi-eval.json. The GPU-timing format stays as it is: I5 GPU needs a new harness first.
- **The evidence (archived 20:19 ICT, sha256 205 / 205 verified in the NAS copy, then deleted
  locally):** `scratch-archive/2026-11-10/fi-eval/`:
  - `xmas-fi/`: labels-v2, params, the eval label files, i5/ (serve log, latencies),
    onnx/ (onnx_pred.py, gpu_latency.py), fi-eval.json;
  - `blind-fi63/`: the blind pack, its answers, key and score;
  - `pred-xmas02fi/`: refs.json, pred-gpu.json, pred-onnx.json;
  - `SHA256SUMS`.
  The weights stay at `/datasets/archive/train/xmas02-fi-20261110/`.
- **For Batt (a round 2 would need its own amendment):**
  - more TRAIN drops ON and NEXT TO her: staged piles viewed from her own cell, and kills'
    drops from recorded pilots;
  - Candy Cane and Scell examples near her;
  - possibly a different box rule for items half under her sprite;
  - the held-out would again be fresh recordings.

### Amendment O15 (2026-11-10 21:10 ICT from `date`, BEFORE any round-2 recording): Batt's answers; THE AURA; round 2 pre-registered

**Batt's answers to the O14 report (quoted, then in English):**
1. "สอน" -- train a round 2. With: "ปรับให้ > 85% ถ้ามากกว่าแล้ว ก็สามารถปรับให้มากขึ้นไปอีกให้ใกล้ 95%
   ก็ได้ มีเวลาทำยาวๆ ทั้งคืน" -- get it above 85 %, then on toward 95 %; the whole night is
   available.
2. "ของที่พลาดทั้ง 14 ชิ้นอยู่ห่างตัว Rogue ไม่เกิน 1 ช่อง ... เพราะตัวเรา lv99 มีแสงด้วยเปล่า
   อยากให้ทดสอบแบบ lv อื่นด้วยนะ ที่ไม่มีแสงรอบตัว ต้องเก็บได้เหมือนกัน" -- is it because our
   character is Base 99 and has a glow? Test with another level too, one with no light around
   the character: it must pick up just the same.

**The aura (looked at, not yet measured):**
- The Rogue (Thief8fce) is Base 99; the client draws the level-99 aura at her feet (white / pink
  flares and a cyan ring).
- In the eval pack's crops it lies over the cells next to her:
  - 005 (Candy Cane, (-1,+1), MISSED) sits inside a pink-white flare;
  - 040 (Scell, (+1,0), MISSED) is pale under a cyan haze;
  - 010 (Zargon, (+1,0), hit) also has the cyan glow around it, but is dark and keeps its
    contrast.
- Round 1's TRAIN was ALL aura: p38, p20 and fs1 are all this Base 99 Rogue. Only ~12 % of its
  boxes were within 1 cell of her.
- The GM account's other characters have NO aura: Crus4b7e2 (Crusader, Base 60) and Valcd8bd6
  (Novice, Base 70), from the lab DB.

**Round 2: the data (one change of recipe: more near items, aura AND no aura).**
- TRAIN adds, labelled `--split train` under params v2 (aea6f1d2), each by the join rule (G2 <= 3 px
  on >= 30 fits):
  1. **fiT1, fiT2, fiT3**: round 1's held-out. It was scored ONCE (O14) and is TRAIN-eligible from
     this amendment (map_labels.XMAS02_FIT_R1). 43 of its 46 evaluated crops were within 1 cell of
     her, and it holds the natural Scell / Candy Cane drops that staging cannot place (Scell is
     outside the staged set, O3);
  2. **fs2**: the Rogue (aura). `stage_items.py --char thief run --map xmas_dun02 --views near --n 12
     --seed 2611121 --immune-confirmed --label fs2`. The near views (stage@9, `NEAR_OFFSETS`):
     (0,0) on the pile's centre, then (2,0), (-2,0), (0,2). Each off-pile view keeps 3 pile cells
     within 1 cell of her and none under her sprite. 12 spots, 48 stands, 72 items;
  3. **fs3**: the Crusader (NO aura). `stage_items.py --char crusader run ... --views near --n 12
     --seed 2611131 --label fs3`;
  4. round 1's TRAIN (p38, p20, fs1) and the negatives, as O9.
- **The held-out, never trained on (refused by NAME: map_labels.XMAS02_FIT, round 2):**
  - **fiT4, fiT5, fiT6**: base pilots p50-p52 recorded beside the runner (aura, natural drops);
  - **fsTa**: the Rogue (aura), `--views near --n 12 --seed 2611200 --label fsTa`;
  - **fsTn**: the Crusader (NO aura), `--views near --n 12 --seed 2611201 --label fsTn`;
  - the four stagings' cells (every stand + every 3 x 3 pile) were checked before this line: fsTa
    and fsTn share NO cell with fs1, fs2, fs3 or each other. fs2 and fs3 share one spot,
    (236,82), and fs2 and fs1 share one; both are TRAIN.
- **The recordings:** `record_session.py --backend rdp --label xmas02-<fsX> --seconds 2400 --fps 1
  --format png --max-bytes 6G`, started before the staging and stopped by ITS OWN PID right after
  the run ends (O6's slip); fiT4-fiT6 as fiT3 (`--label hunt-xmas02-fiT<n> --seconds 1620`).
- **Character switches** (the Crusader is the account's 2nd card): a client restart, the card,
  `enter_game`, the chat-window and UI-gate checks, `@monsterignore` judged by its answer line,
  `held` rc 0 before each staging. Then back to the Rogue, immune.

**T2-r2, the labels' check on the NEW data (beside the training, before any score):**
- A pack from fs2 + fs3 + fiT1-3's TRAIN labels, seed 65: up to 40 item crops (<= 3 a floor
  item, N stratum first) + 20 E crops.
- Two NEW blind labellers; `fi_blind_score.py`.
- O.5's bars: good box >= 90 % on the item crops, present right >= 95 %.
- A FAIL voids the round-2 model: it is never scored, and the report says why.

**The cache and the training (O9's recipe, changed only where written):**
- `build_frame_cache.py --labels items`, as O9, with the new label files in `--fi-labels` and
  `--train`. A dry run first; the written counts must equal it.
- The cache id: `xmas02-fi-r2-20261110`. VAL is FIT p31 (monitor only).
- **The init: round 1's `last.pt` (e24e8f57).** It has the same single class, so the head
  transfers too. 12 epochs, batch 2, workers 2, FP32 on the Arc, `--mid-ckpt`, hsv_s 0.2,
  close_mosaic 3, scale 0.1.
- The scored checkpoint is the last epoch's `last.pt`, frozen and sha256-recorded BEFORE any
  held-out file is read.

**The evaluation (O.9, with the strata Batt asked for; fi_eval gains them, with tests, BEFORE any
score):**
- The labels: `fi_labels.py label --eval-test` on fiT4-fiT6, fsTa and fsTn, once, after the model
  froze.
- The pack: seed 66, <= 3 crops a floor item, up to 70 aura item crops (fiT4-6 + fsTa) + up to 50
  no-aura (fsTn) + 20 E. Two NEW blind labellers; the evaluated crops = both labellers' good boxes.

| bar | what | value |
|---|---|---|
| I1a recall, AURA | fiT4-fiT6 + fsTa pooled; each source reported | >= 0.85 on >= 40 crops |
| I1n recall, NO AURA (Batt) | fsTn | >= 0.85 on >= 30 crops |
| I1 precision | every box on the judged frames of all five | >= 0.85 |
| I2 | fiT4-fiT6's episodes, as O.9 | >= 0.80 on >= 20 (short: NO VERDICT, reported) |
| I3, I4 | fiT4-fiT6, as O.9 | <= 0.5 % / <= 0.2 %; <= 5 % on >= 40 |
| I5 CPU | eval_latency vs xmas02gb, interleaved | <= 1.10 x |
| I5 GPU (fixed here: O14 had no verdict) | the detect server's forward p95, one model a run, the same harness and frames as xmas02gb | <= 1.10 x xmas02gb's AND <= 35 ms |

- Batt's 95 % is REPORTED beside I1a / I1n (a target, not a bar).
- **The verdict:** PASS when every bar holds. Deploying and `--loot-sight` stay Batt's. FAIL: a
  round 3 only by a new amendment, with what failed.

**The night's order (pipelined on the one Windows session and the one GPU):**
1. fs2 (Rogue) -> switch -> fs3 (Crusader) -> ship + label the TRAIN -> the cache -> the training
   starts (GPU);
2. during it: fsTn (Crusader) -> switch -> fsTa (Rogue); T2-r2; fi_eval's strata; the late-strike
   study (Batt's other idea; rogue-xmas02.md);
3. after it: the pilots p50-p52 (fiT4-fiT6; the detect server needs the GPU), then the
   evaluation.

### Amendment O15b (2026-11-10 22:23 ICT from `date`, BEFORE the cache's dry run): the TRAIN's admissions, a finding, the epoch rule

- **The TRAIN labels (v2, aea6f1d2; `fi_labels.py label --split train`):**

| session | kept frames with items | labels | within 1 cell | floor items | G2 (median dx / dy, within 3 px, fits) | join |
|---|---|---|---|---|---|---|
| fiT1 | 25 | 25 | 22 | 12 | 0 / 1 px, 38 fits | ADMITTED |
| fiT2 | 18 | 20 | 20 | 8 | 28 fits (< 30) | NOT admitted (G2 NOT_ENOUGH, by the letter) |
| fiT3 | 24 | 24 | 8 | 5 | 30 fits | ADMITTED |
| fs2 (the Rogue, aura) | 92 | 329 | 27 | 35 | 0 / 1 px, 96.4 %, 950 fits | ADMITTED |
| fs3 (the Crusader, NO aura) | 61 | 210 | 37 | 27 | 0 / 1 px, 92.7 %, 1,259 fits | ADMITTED |

- **A finding, recorded, NOT acted on tonight:** the near views give few labels within 1 cell
  (fs2: 27 of 329).
  - The rule excludes a WHOLE frame while any item lies under her self box (under_self, 198 frames
    in fs2) or her HP bar (under_bar, 158). At the pile's centre, most frames carry such an item.
  - So round 2 adds ~2x round 1's near-her boxes, not more: within 1 cell, fiT1 22 + fiT3 8 + fs2 27
    + fs3 37 = 94 new, beside round 1's ~105 (12 % of its 878). A rule that ignores only the covered
    item's region (not the frame) would be a v3 rule with its own T2: for Batt.
- **fs2's run:** 21:17:04-21:44:06, rc 0, 12 spots, 72 items, one `@killmonster2` at each spot. The
  recording `20261110T211705-rdp-xmas02-fs2`: 1,620 frames, 3.52 GB, shipped (rc 0, local
  deleted).
- **The Crusader's prep (fs3):**
  - the client restart, card 2, `enter_game`. The chat window was standard; no aura on the
    screenshot;
  - `@monsterignore`: "You are now immune to attacks.";
  - `@storeall` is NOT in group 20 (it came back as plain chat). Instead its Red Herb 507 x 40
    stack (a staged id: clear_loot would have dropped it with the staged one) was dropped by
    `clear_loot` restricted to the Red Herb icon. It is given back (`@item 507 40`) after the
    Crusader's last staging;
  - `held` rc 0 at 21:52:02.
- **A slip, fixed before any label:** 20:2x's archive of `/dev/shm/poring-lab-tmp/xmas-fi` took its
  run-time inputs too (the params, the item sprites, the GRF name table). They were restored from
  the NAS copy at 21:18 (119 files, sha256 verified).
- **The epoch rule (fixed here, BEFORE the dry run; O15 said 12):**
  - epochs = min(12, max(5, floor(9,000 s / (0.64 s x N_train + 100 s)))), N_train the dry run's
    TRAIN frame count;
  - 0.64 s a frame + ~100 s of VAL is O10's measured epoch (687 frames in ~9 min);
  - 9,000 s keeps the training's end ~2.5 h after its start, so the pilots p50-p53 (which need
    the GPU) and the evaluation fit before 06:00;
  - with the init already trained on this class (round 1's last.pt), fewer epochs are a
    fine-tune.
- **fs3's run:** 21:52:09-22:19:18, rc 0, 12 spots, 72 items. The
  recording `20261110T215210-rdp-xmas02-fs3` shipped (rc 0).
- **The dry run (22:2x):** TRAIN 955 frames (493 item frames, 1,466 boxes, 462 negatives), 165
  floor items, about 2.04 GB in 11 shards, `would_refuse_join` empty. VAL p31 as round 1.
- **So the epochs: floor(9,000 / (0.64 x 955 + 100)) = 12 -> 12** (O15's own number). The
  training's estimated end is ~2.4 h after its start.
- **Next, in order:** the cache (the dry run's command without `--dry-run`, guarded; its counts must
  equal the dry run's), then the training (O15's recipe, 12 epochs), then fsTn's and fsTa's
  stagings beside it.

### Amendment O15c (2026-11-10 23:19 ICT from `date`, BEFORE the model froze and before any held-out read): the cache, the training's start, T2-r2 PASSES, the held-out stagings

- **The cache** (22:23:59-22:30:19, guarded, rc 0): `/mnt/poring-lab-datasets/.framecache/
  xmas02-fi-r2-20261110`, 1,227 frames (TRAIN 955 + VAL 272, as the dry run), 13 shards, 377 s.
- **The training** started 22:30:31 (unit `poring-train-xmas02fi-r2`,
  `/dev/shm/poring-lab-tmp/xmas-fi/train-r2/launch.sh`, O15's recipe, 12 epochs).
  - The init re-hashed: e24e8f57.
  - The log: "Transferred 499/499 items from pretrained weights" (the same single class, the head
    included).
  - ~10 min an epoch, so the end is ~00:35.
  - VAL (monitor only) after epochs 1-3: P 0.962 / 0.978 / 0.967, R 0.967 / 0.973 / 0.874.
- **T2-r2** (O15: a pack from fs2 + fs3 + fiT1 + fiT3's TRAIN labels, seed 65, `pack --round 2`):
  - 60 crops = 40 item crops, ALL N (within 1 cell of the character), + 20 E (10 plain, 10 hard);
  - two NEW blind labellers, M and N, who saw only the pack;
  - `fi_blind_score.py` once, score sha256 8e6bc567...

| labeller | good box, 40 item crops (>= 90 %) | present right, 60 crops (>= 95 %) | E right | verdict |
|---|---|---|---|---|
| M | 95.0 % (38 / 40) | 96.7 % (58 / 60) | 20 / 20 (10 hard) | PASS |
| N | 95.0 % (38 / 40) | 96.7 % (58 / 60) | 20 / 20 (10 hard) | PASS |

  - They agree on all 60 (q1 and q2). Their only misses are the same two "unsure" crops (015,
    021: a round red-and-white object over a translucent corpse).
  - **T2-r2 PASSES: the round-2 model stands** (it is not voided).
- **The held-out stagings** (refused by name; nothing of them has been read, only shipped):
  - fsTn, the Crusader (no aura, seed 2611201): 22:19:30-22:46:49, rc 0, 12 spots. Recording
    `20261110T221931-rdp-xmas02-fsTn`, shipped (rc 0);
  - the Crusader's 40 Red Herbs were given back (`@item 507 40`, "Item created.");
  - the switch back to the Rogue: she logged in on xmas_dun02 (236,216) with monsters near, and
    `@monsterignore` answered "You are now immune to attacks." at once (a relog clears it);
  - fsTa, the Rogue (aura, seed 2611200): 22:49:12-23:16:01, rc 0, 12 spots. Recording
    `20261110T224913-rdp-xmas02-fsTa` (3.46 GB), shipped (rc 0).
- **Next:** at the training's end, freeze `last.pt` (sha256 here, before any held-out file is
  read), the ONNX export, `GPU_WEIGHTS["xmas02fi2"]`, then the held-out's `--eval-test` labels. The
  pilots p50-p53 follow (rogue-xmas02.md 4BM-4BO; fiT4-fiT6), then the evaluation pack (seed 66)
  and the score.

### Amendment O15d (2026-11-10 23:20 ICT from `date`, BEFORE its run): fs4, near-her TRAIN banked for a round 3 (NOT in round 2)

- **Why now:** the training holds the GPU until ~00:35 and the pilots need it, so the Windows
  session is idle. Batt (11-10 night): "train whatever can be trained, keep improving ... toward
  95 %".
- **fs4:** the Rogue (aura), `--views near --n 12 --seed 2611302 --label fs4`, recorded as
  O15's stagings.
  - Its cells (stands + piles) share NONE with the held-out fsTa / fsTn (checked before this
    line).
  - It is NOT in round 2's cache (frozen at 22:30) and not in its evaluation.
  - It is TRAIN-eligible by name for a later round, which needs its own amendment and a fresh
    held-out.
- **fs4's run:** 23:20:20-23:47:21, rc 0, 12 spots; the recording `20261110T232020-rdp-xmas02-fs4`
  is shipped.
- **fs5 (23:47 ICT, BEFORE its run):** the Crusader (NO aura), `--char crusader --views near --n 12
  --seed 2611305 --label fs5`. Like fs4: banked for a round 3, NOT in round 2, sharing no cell
  with fsTa / fsTn. The same Crusader prep as fs3 (the Red Herb stack dropped, then given back).
- **fs5's run:** 23:52:04-00:19:17, rc 0, 12 spots; the recording `20261110T235204-rdp-xmas02-fs5`
  is shipped. The Crusader's 40 Red Herbs were given back ("Item created."). The Rogue is back in,
  `@monsterignore` "You are now immune to attacks.".

### Amendment O15e (2026-11-11 00:22 ICT from `date`, BEFORE any held-out file is read): THE ROUND-2 MODEL FROZEN

- `train ended rc=0` at 2026-11-11 00:19:51 ICT (started 22:30:31): all 12 epochs, 6,483 s, FP32 on
  the Arc.
- VAL (FIT p31, monitor only) at epoch 12: P 0.953, R 0.949, mAP50 0.982, mAP50-95 0.735. Round 1
  at its epoch 20: 0.960 / 0.906 / 0.977 / 0.683.
- **The scored checkpoint:** `data/train/xmas02-fi-r2-20261110/weights/last.pt` after epoch 12,
  **sha256 `e381d68982fd4362569dcd405841624687f0e0faa2e9700847469ce2220bdc2b`** (5,530,394 bytes).
  Nothing is refitted after this line.
- Next, O15's order: the ONNX export, `GPU_WEIGHTS["xmas02fi2"]`, the held-out's `--eval-test`
  labels (fsTa, fsTn now; fiT4-fiT6 after their pilots), the pack (seed 66), two NEW blind
  labellers, the predictions, I5, `fi_eval.py --strata r2` once.

### Amendment O15f (2026-11-11 00:39 ICT from `date`): the export, the registration, the staged held-out's labels and GPU predictions (NO score read)

- **The ONNX export** (M9's recipe; the env script byte-identical, sha256 0b1db27c..., built in RAM,
  removed after):
  - `/dev/shm/poring-lab-detector/model/xmas02fi2-last-736x1280.onnx`, sha256 `7f148f3f63d56ddd...`;
  - names `["floor_item"]` (d31e3c6c..., as round 1);
  - copied to the NAS `archive/models/` (re-hashed).
- **The run archived** (guarded `archive:`, size + count verified, local deleted):
  `archive/train/xmas02-fi-r2-20261110`; its `last.pt` re-hashed e381d689 on the NAS.
- **Registered:** `GPU_WEIGHTS["xmas02fi2"]` (d115127e, tested). It is NOT in MAP_MODELS. Since
  p50 the detect server loads it and round 1's xmas02fi beside the map models (p50's listening
  line names all five): a difference from p49's three, noted for D1.
- **The held-out's `--eval-test` labels (the frozen e381d689 re-hashed; params v2):**
  - fsTn (no aura): 113 kept frames, 422 labels, 39 floor items, 86 within 1 cell;
  - fsTa (aura): 91 kept frames, 331 labels, 45 floor items, 91 within 1 cell.
- **The GPU predictions on them** (predict_dir in the worker, conf 0.25, 1,534 frames,
  `data/train/eval/xmas02fi2/pred-gpu-staged.json`): made 00:27-00:30.
  - The ONNX set (`fi_onnx_pred.py`, committed 29d8876a) was started, then stopped at 500 / 1,534
    so it would not load the host during p50 / p51; it is re-run whole after the pilots.
  - Nothing of either prediction set has been compared with any label.
- **The MVP window:** `@mobsearch` "1[dead]" from 00:21 (the stagings killed it at an unknown
  time). The 3-min poll read it alive at 00:36:09 ([123:43]); `@killmonster2` at 00:37:03, then
  "1[dead]". So p50 + p51 run before 01:37.

### Amendment O15g (2026-11-11 03:07 ICT from `date`, BEFORE any score): the held-out complete, the pack, the evaluated crops

- **The pilots' held-out** (`--eval-test`, e381d689 re-hashed): fiT4 (beside p50) 994 candidate
  frames, 18 labels / 8 floor items; fiT5 (p51) 932, 22 / 10; fiT6 (p52) 967, 24 / 10. Their refs:
  2,879 frames. GPU predictions 02:4x-02:50.
- **The pack (seed 66, `pack --round 2 --eval-test`, over fiT4-fiT6 + fsTa + fsTn):** 140 crops =
  120 item crops (70 aura + 50 no-aura; N 40, F 67, M 13) + 20 E. Nothing short.
- **Labellers O and P** (NEW, blind; told only that the character may look different):
  - they answered all 140 and agree on all 140 (q1 and q2);
  - each: q1 yes 119 / no 20 / unsure 1 (129, a cookie-like shape on a fallen monster); q2 good
    119;
  - both flagged 064 / 106 (a rod under a cake slice: the most central item judged).
- **EVALUATED (both yes / good): 119 crops.**
  - Aura 69: fiT4 4, fiT5 4, fiT6 5 (natural drops), fsTa 56 (staged). Its minimum is 40.
  - No aura 50: fsTn. Its minimum is 30.
  - The natural pilot drops are few (13 of 69). The per-source counts are reported beside I1a, as
    O15 said.
- **Still to come, then the score once:**
  - the ONNX set on the pilots (running);
  - I5 on 300 frames, every 14th of the 4,413 held-out refs: the detect server's forward time
    for xmas02fi2 and xmas02gb, one a run; eval_latency, interleaved, on a quiet host;
  - `fi_eval.py --strata r2` once, with both prediction sets merged over the five sessions
    (`merge_preds.py`: same weights, disjoint keys).

### Amendment O16 (2026-11-11 03:40 ICT from `date`): THE ROUND-2 RESULT (the held-out score, once) -- RECALL MET, FALSE BOXES FAIL

`fi_eval.py --strata r2` once at 03:39:29 (score sha256 c71b324f...). Inputs:
- both prediction sets merged over the five sessions (`fi_merge_preds.py`). The GPU set names one
  file by two paths: the staged half predicted 00:27-00:30 from the local `last.pt` (frozen
  e381d689 at 00:21), the pilots' half from the NAS copy (archived 00:30:59, re-hashed e381d689);
  `--weights-sha256 e381d689...` records it;
- I5 from the detect server (fi2 / gb one a run) and eval_latency on a quiet host.

The GPU and the ONNX sets give IDENTICAL I1-I4 results.

| bar | round 2 | round 1 (O14) | bar value | verdict |
|---|---|---|---|---|
| I1a recall, AURA (fiT4-6 + fsTa) | **64 / 69 = 0.928** (fsTa 56 / 56; fiT4 2 / 4, fiT5 2 / 4, fiT6 4 / 5) | 0.696 | >= 0.85 on >= 40 | PASS (Batt's 95 %: no) |
| I1n recall, NO AURA (fsTn, Batt) | **49 / 50 = 0.980** | - | >= 0.85 on >= 30 | PASS (95 %: yes) |
| I1 pooled (reported) | 113 / 119 = 0.950 | 0.696 | - | - |
| I1 precision | 3,912 / 4,067 = 0.962 (31 ambiguous) | 0.864 | >= 0.85 | PASS |
| I2 first kept-label frame boxed | **21 / 28 = 0.75** | 0.56 | >= 0.80 on >= 20 | **FAIL** |
| I3 item-free pilot frames with a box: any / her 5 x 5 | **108 / 2,519 = 4.29 % / 81 = 3.22 %** | 0.49 % / 0.12 % | <= 0.5 % / <= 0.2 % | **FAIL** |
| I4 drop-less kills with a box on the death cell's 3 x 3 | **15 / 133 = 11.3 %** | 0 / 124 | <= 5 % on >= 40 | **FAIL** |
| I5 GPU, server forward p95 | 16.41 vs xmas02gb 16.77 ms = 0.979 x | no verdict | <= 1.10 x and <= 35 ms | PASS |
| I5 CPU p95 | 721.4 vs 757.2 ms = 0.953 x | 1.043 x | <= 1.10 x | PASS |

- **VERDICT: FAIL** (I2, I3, I4). The model is not deployed; `--loot-sight` is not
  pre-registered.
- **What round 2 changed:** recall near her went from 0.70 to 0.93 (aura) and 0.98 (no aura), so
  the aura is no longer a blind spot. But the model now boxes things in the PILOTS' fights that are
  not items: item-free frames 9x more often, mostly within 2 cells of her, and the death cells of
  drop-less kills. TRAIN gained many near-her items (staged, standing still, no fight) and few
  near-her negatives with fights.
- **Where recall still misses:** all 6 misses are NATURAL drops (3 floor items in the pilots: fiT4
  #1422 x 2 frames, fiT5 #1439 x 2, fiT6 #1460) and fsTn #1159. The staged aura items are 56 / 56.

### Amendment O17 (2026-11-11 03:44 ICT from `date`, BEFORE its cache): ROUND 3 pre-registered -- fight negatives near her

- **Why (O16, looked at after the score):** round 2's false boxes in the pilots sit in FIGHTS: a
  Cruiser's mace head, a pale hit-effect fragment beside a Cruiser, a small puff on the floor.
  - Their confidences are high (I3's boxes: quartiles 0.34 / 0.47 / 0.70), so no threshold
    separates them.
  - Round 2's TRAIN took 1 negative per 3 item frames from each item session: ~8 fight frames
    per pilot, against hundreds of staged near-her items with no fight.
- **Batt (11-10 night):** keep improving toward 95 %, train whatever can be trained.
- **TRAIN r3** (params v2 aea6f1d2; each new session by the join rule G2):
  - round 2's TRAIN (O15b);
  - the banked fs4 (409 labels, G2 PASS) and fs5 (84, PASS);
  - round 2's held-out, scored ONCE (O16) and TRAIN-eligible from here (`map_labels.XMAS02_FIT_R2`):
    fiT4, fiT5, fiT6, fsTa, fsTn, relabelled `--split train`;
  - **the change: `--session-negs` (build_frame_cache, tested):** 150 item-free kept frames from
    EACH pilot in TRAIN (p38, p20, fiT1, fiT3, fiT4, fiT5, fiT6) instead of 1 per 3 item frames.
    Those are the frames where she stands in a fight with no item on the floor.
  - VAL: FIT p31 (monitor only).
- **The training:** init = round 2's `last.pt` (e381d689); O15's recipe otherwise.
  - Epochs = min(12, max(3, floor(6,000 s / (0.64 s x N_train + 100 s)))), N_train from the dry
    run.
  - 6,000 s keeps the end near 06:00 (Batt's window) from a ~04:05 start.
- **The held-out r3, fresh (refused by name: `map_labels.XMAS02_FIT`, round 3):**
  - fsTa3 (the Rogue, aura) and fsTn3 (the Crusader, no aura), near stagings on spots sharing NO
    cell with any TRAIN staging (fs1-fs5, fsTa, fsTn), staged tonight beside the training;
  - fiT7, fiT8, fiT9: base pilots recorded beside the next runs (the next session).
- **The bars: O15's, unchanged** (I1a / I1n >= 0.85, I1 precision, I2, I3, I4, I5; Batt's 95 %
  reported). `fi_eval` gains round 3's strata (`--strata r3`, the round-3 names) with a test
  BEFORE any score. The model is frozen and sha256-recorded before any held-out file is read; the
  evaluation is the next session's.

### Amendment O17b (2026-11-11 03:52 ICT from `date`, BEFORE the cache): round 3's admissions and epochs

- **The relabels (`--split train`, v2):**
  - fiT6 18-24 labels, G2 PASS (43 fits): ADMITTED;
  - fsTa 331 labels, PASS (1,140): ADMITTED;
  - fsTn 422, PASS (1,103): ADMITTED;
  - **fiT4 (29 fits) and fiT5 (26) NOT admitted** (G2 NOT_ENOUGH, by the letter, as fiT2). So
    they give no fight negatives either: `--session-negs` names p38, p20, fiT1, fiT3, fiT6 (150
    each).
- **The dry run:** TRAIN 2,147 frames (880 item frames, 2,736 boxes, 1,267 negatives), 322 floor
  items, ~4.6 GB in 17 shards, `would_refuse_join` empty. VAL p31 as before.
- **Epochs = min(12, max(3, floor(6,000 / (0.64 x 2,147 + 100)))) = 4.**
- The Rogue's bag was emptied (`clear-bag`, 03:47) for fsTa3.
- **O17c (03:55 ICT, BEFORE either staging):** round 3's held-out stagings:
  - fsTa3 = the Rogue, `--views near --n 12 --seed 2611446`;
  - fsTn3 = the Crusader, `--seed 2611681`;
  - both were checked to share NO cell with fs1-fs5, fsTa, fsTn;
  - `--session-negs` now takes plain names + `--session-negs-n 150` (96a9ecdb: the guarded cache
    step refuses '=' in an argument). The dry run's counts are unchanged.

### Amendment O17d (2026-11-11 04:17 ICT from `date`): the round-3 cache and training; fsTa3 stopped at spot 7 (kept as it is)

- **The cache** (03:53:46-04:06:02, guarded, rc 0): `xmas02-fi-r3-20261111`, 2,419 frames (TRAIN
  2,147 + VAL 272, as the dry run), 19 shards, 734 s.
- **The training** started 04:06 (unit `poring-train-xmas02fi-r3`, O17's recipe, 4 epochs, the init
  re-hashed e381d689; "Transferred 499/499"); ~17 min an epoch.
- **fsTa3** (the Rogue, seed 2611446) ran 03:55:47-04:09:56, **rc 1 after 6 of 12 spots** (36
  items).
  - At spot 7's second `@item` the chat-window check read 'unknown' ("obscured", the input bar open,
    an "obtained" popup over the busy floor; frame
    `chat-window/20261111-040948-unreadable.png`). It stopped before typing, as built.
  - It is KEPT as it is: a repeat under another name would not be refused by name.
  - Spot 7's one given Zargon is still in her bag (a clear-bag before her next staging).
  - The recording `20261111T035548-rdp-xmas02-fsTa3` is shipped. If round 3's aura stratum is
    short (< 40 evaluated crops with fiT7-fiT9), that stratum is NO VERDICT and more held-out
    comes from the next pilots.
- **fsTn3** (the Crusader, seed 2611681) started 04:17:07 (the herb stack dropped as before,
  `held` rc 0 at 04:16:58).

### Amendment O17e (2026-11-11 04:58 ICT from `date`): fsTn3 done; fsTa4 named, NOT staged

- **fsTn3** (the Crusader, seed 2611681): 04:17:07-04:44:14, rc 0, 12 / 12 spots. The recording is
  shipped. The Crusader's 40 Red Herbs were given back ("Item created."). The Rogue is back in, immune
  ("You are now immune to attacks."). Her bag was cleared (`clear-bag` 04:46, fsTa3's leftover
  Zargon), and she stands on prt_fild08's clear stand.
- **fsTa4** (a second aura held-out, because fsTa3 stopped at spot 7) is NAMED in
  `map_labels.XMAS02_FIT` and `fi_eval.R3_AURA` (tested). It is refused by name from TRAIN
  whatever happens.
  - It was NOT staged: in 400 seeds (2611700-2612099) no 12-spot near plan shares no cell with the
    nine stagings so far. The lattice's TRAIN stands are used up for near views.
  - The next session may stage fewer spots (`--n 6`) on a disjoint plan, or take round 3's aura
    held-out from the pilots fiT7-fiT9 alone.

### Amendment O17f (2026-11-11 05:23 ICT from `date`, BEFORE any round-3 held-out file is read): THE ROUND-3 MODEL FROZEN

- `train ended rc=0` at 05:22:24 ICT (started 04:06): 4 epochs, 4,463 s, FP32 on the Arc.
- VAL (FIT p31, monitor only) at epoch 4: P 0.986, R 0.937, mAP50 0.986, mAP50-95 0.704. Round 2 at
  its epoch 12: 0.953 / 0.949 / 0.982 / 0.735.
- **The scored checkpoint:** `archive/train/xmas02-fi-r3-20261111/weights/last.pt` after epoch 4,
  **sha256 `133589f32f802e5978f7c3b32bd9b8115a8694a0b319bbc7c64f86e69c633e5d`** (5,529,370 bytes;
  frozen at 05:22:32 locally, archived and re-hashed on the NAS). Nothing is refitted after this
  line.
- **The ONNX** (M9's recipe, the env removed after): `xmas02fi3-last-736x1280.onnx`, sha256
  `c0ca01bea1d1d2e5...`, names `["floor_item"]`; copied to `archive/models/`.
- `GPU_WEIGHTS["xmas02fi3"]` is registered (tested; NOT in MAP_MODELS).
- **Next session, O17's order:**
  - the held-out: fsTa3 (partial, 6 spots) + fsTn3 (12 spots), staged and shipped tonight, not
    read; + fiT7-fiT9 recorded beside the next base pilots; fsTa4 is named, not staged;
  - `--eval-test` labels, `pack --round 3 --eval-test --seed 67`, two NEW blind labellers, both
    prediction sets, I5 (server time vs xmas02gb; eval_latency), `fi_eval.py --strata r3` once.

### Amendment O18 (2026-11-11 06:01 ICT from `date`): Batt allows round 3's exam

- Batt: "allowed" (his one Thai word, not quoted: it is also a client UI string the
  locale-pack guard refuses): fiT7, fiT8 and fiT9 are recorded beside the next base pilots (p54-p56,
  rogue-xmas02.md 4BP) and round 3 is scored once with them + fsTa3 + fsTn3 (O17's bars, `--strata
  r3`, the pack seed 67).
- They are refused by name already (`map_labels.XMAS02_FIT`). The model is frozen (O17f, 133589f3).

### Amendment O18b (2026-11-11 09:37 ICT from `date`, BEFORE any score): round 3's held-out complete, the pack, I5 GPU

- **The held-out (`--eval-test`, 133589f3 re-hashed):**

| session | candidate frames | kept with items | labels | floor items | within 1 cell |
|---|---|---|---|---|---|
| fsTa3 (Rogue, aura, partial: 6 spots) | 582 | 24 | 87 | 13 | 30 |
| fsTn3 (Crusader, no aura) | 1,152 | 107 | 368 | 44 | 20 |
| fiT7 (beside p57) | 1,193 | 11 | 11 | 6 | 11 |
| fiT8 (beside p55) | 766 | 27 | 27 | 6 | 13 |
| fiT9 (beside p56) | 874 | 5 | 5 | 4 | 3 |

- Refs: 4,003 frames. GPU predictions 09:21-09:30 (predict_dir in the worker, the NAS weights
  133589f3). The ONNX set is running.
- **The pack (seed 67, `pack --round 3 --eval-test`):** 133 crops = 113 item crops (aura 63,
  SHORT 7 of 70: fsTa3's partial run; no-aura 50; N 42, F 68, M 3) + 20 E. Two NEW blind
  labellers, Q and R, are judging it.
- **I5 GPU (the detect server's forward time, one model a run, 300 frames, every 13th ref):**
  xmas02fi3 p95 16.84 ms vs xmas02gb 16.89 ms = 0.997 x. All 300 on the GPU path. I5 CPU
  (eval_latency, quiet host) comes after the ONNX set.
- **O18c (10:02 ICT, BEFORE any score): labellers Q and R** (NEW, blind) answered all 133 and agree
  on 132 / 133 (q1 and q2).
  - Q: yes 111 / no 20 / unsure 2; R: yes 110 / no 20 / unsure 3; every yes judged good.
  - Both flagged 084 / 128 (a grey cookie-like shape against the Crusader's robe) and 020 / 030
    / 108 (a beige cookie on a fading corpse).
  - **EVALUATED (both yes / good): 110 crops.** Aura 62 (fiT7 11, fiT8 14, fiT9 4 natural; fsTa3
    33 staged; minimum 40). No aura 48 (fsTn3; minimum 30).

### Amendment O19 (2026-11-11 10:25 ICT from `date`): THE ROUND-3 RESULT (scored once) -- FALSE BOXES FIXED, RECALL FELL

`fi_eval.py --strata r3` once at 10:25:15 (score sha256 6ae33fd8...). Inputs: both prediction sets
over the five sessions (4,003 frames); I5 from the detect server and eval_latency. The GPU and the
ONNX sets give IDENTICAL I1-I4.

| bar | round 3 | round 2 (O16) | round 1 (O14) | bar value | verdict |
|---|---|---|---|---|---|
| I1a recall, AURA | **50 / 62 = 0.806** (fsTa3 32 / 33; pilots fiT7 6 / 11, fiT8 12 / 14, fiT9 0 / 4) | 0.928 | 0.696 | >= 0.85 on >= 40 | **FAIL** |
| I1n recall, NO AURA | 41 / 48 = 0.854 | 0.980 | - | >= 0.85 on >= 30 | PASS (95 %: no) |
| I1 precision | 2,668 / 2,684 = 0.994 | 0.962 | 0.864 | >= 0.85 | PASS |
| I2 | 7 / 16 = 0.44 | 0.75 | 0.56 | >= 0.80 on >= 20 | NO VERDICT (short) |
| I3 any / her 5 x 5 | 0.42 % / **0.27 %** (7 / 2,598) | 4.29 / 3.22 % | 0.49 / 0.12 % | <= 0.5 % / <= 0.2 % | **FAIL** (5 x 5) |
| I4 | 1 / 112 = 0.9 % | 11.3 % | 0 % | <= 5 % | PASS |
| I5 GPU, server p95 vs xmas02gb | 16.84 vs 16.89 ms = 0.997 x | 0.979 x | - | <= 1.10 x, <= 35 ms | PASS |
| I5 CPU p95 vs xmas02gb | 730.8 vs 785.1 ms = 0.931 x | 0.953 x | 1.043 x | <= 1.10 x | PASS |

- **VERDICT: FAIL** (I1a; I3's 5 x 5). Not deployed.
- **What the fight negatives did:**
  - false boxes fell about tenfold: I3 4.29 % -> 0.42 %, I4 11.3 % -> 0.9 %, precision 0.962 ->
    0.994;
  - but the model became more cautious near her: recall aura 0.928 -> 0.806, no aura 0.980 ->
    0.854.
- **The lasting weak spot: NATURAL drops in the pilots.** Round 2's pilots 8 / 13 (62 %), round
  3's 18 / 29 (62 %), against the stagings' 97-100 %. A dropped item in a fight (corpses, hit
  effects, the item just landing) is not what the staged piles show.
- **For a round 4 (Batt's decision, own amendment):**
  - more NATURAL drops in TRAIN: label the pilots' kill drops (every base pilot's recording is a
    source; fiT4-fiT9 are scored once and TRAIN-eligible after their round);
  - keep the fight negatives but balance them: e.g. 75 a pilot, not 150;
  - or an operating threshold per stratum chosen on a VAL set of natural drops.

### Amendment O20 (2026-11-11 10:56 ICT from `date`, BEFORE its cache): ROUND 4 pre-registered -- more natural drops, half the fight negatives

- **Batt (11-11, to the 10:2x report):** "เทรน" (train). The agreed recipe: more drops that fell
  in real fights, and half the fight negatives.
- **TRAIN r4** (params v2; each new session by the join rule G2):
  - round 3's TRAIN (O17b);
  - round 3's held-out, scored ONCE (O19) and TRAIN-eligible from here (`map_labels.XMAS02_FIT_R3`):
    fiT7, fiT8, fiT9 (natural drops) and fsTa3, fsTn3, relabelled `--split train`;
  - `--session-negs` for every pilot in TRAIN, at **75** (round 3: 150).
- **The training:** init = round 3's `last.pt` (133589f3: it knows the fight negatives); O15's
  recipe otherwise.
  - Epochs = min(12, max(3, floor(5,400 s / (0.64 s x N_train + 100 s)))): the pilots wait for
    the GPU.
  - The model is frozen and sha256-recorded before any held-out file is read.
- **The held-out r4, fresh (refused by name, `map_labels.XMAS02_FIT`):**
  - fiT10-fiT13: the next base pilots (the escape's and R2b's, rogue-xmas02.md 4BU / 4BV)
    recorded beside them; natural drops, the stratum that failed;
  - fsTa4 (Rogue) and fsTn4 (Crusader): near stagings of 6 spots each, on cells sharing none with
    any TRAIN staging, staged during the training.
- **The bars: O15's, unchanged** (`--strata r4`, `pack --round 4 --eval-test --seed 68`). Batt's
  95 % is reported. Also reported: I1a on the pilots' natural drops alone (rounds 2 and 3: 62 %).

### Amendment O20b (2026-11-11 11:04 ICT from `date`, BEFORE the cache): round 4's admissions, the dry run, the epochs, the staging seeds

- **The relabels (`--split train`, v2):**
  - fiT8 27 labels, G2 PASS (43 fits): ADMITTED;
  - fsTa3 87, PASS (439): ADMITTED;
  - fsTn3 368, PASS (1,148): ADMITTED;
  - **fiT7 (12 fits) and fiT9 (15) NOT admitted** (G2 NOT_ENOUGH, by the letter).
  - A structural limit: a single pilot gives few still frames with a drop, so natural drops pile
    up slowly, ~5-27 labels a pilot. `--session-negs` 75 names p38, p20, fiT1, fiT3, fiT6,
    fiT8.
- **The dry run:** TRAIN 2,048 frames (1,038 item frames, 3,218 boxes, 1,010 negatives), 385 floor
  items, `would_refuse_join` empty.
- **Epochs = min(12, max(3, floor(5,400 / (0.64 x 2,048 + 100)))) = 3.**
- **The held-out stagings (6 spots each, cells shared with no staging so far):** fsTa4 = the
  Rogue, seed 2612104; fsTn4 = the Crusader, seed 2612190.
- **O20c (11:36 ICT):**
  - fsTa4 (Rogue, seed 2612104): 11:07:18-11:21:03, rc 0, 6 / 6 spots, shipped;
  - fsTn4 (Crusader, seed 2612190) STOPPED after spot 1 of 6: the chat-window check found no window
    over the busy orange floor (`chat-window/20261111-113449-no-window.png`; the window is plainly
    there). It stopped before typing, as built; the 1-spot recording is shipped and stays
    held-out (refused by name);
  - so the no-aura held-out is re-staged under the SAME label (`xmas02-fsTn4`, refused by name) on
    a new 6-spot plan, seed 2612601, which shares no cell with any staging so far;
  - round 4's training runs since 11:17 (3 epochs, 499 / 499 transferred).
- **O20d (11:5x ICT): the re-run stopped at its start (11:36:43, rc 1) on the same check, and the
  CAUSE is found and fixed in the reader (`chat_window.find`, `TOP_GAP`):**
  - at the Crusader's stand (37,62) ONE pixel of the window's white top border, x 583, read luma
    224 (RGB 226,221,231; WHITE is 225). The border's run split into 68..582 + 584..592, neither
    long enough, so a frame showing the standard window read "none found". Both stop frames
    (11:34:49, 11:36:41) were the same;
  - since: white runs at most 2 px apart join (`_white_runs`); the right border, the separator
    and the line pitch still decide. Both stop frames now read 6 lines, docked, LOCKED, tabs in
    order (next step: none);
  - the check against recorded frames (old reader at 19670419 vs new, offline, one frame per 30,
    at most 40 a session): 1,290 frames of the 36 xmas_dun02 sessions since 11-05. 2 change, both
    viewed: fsTa3 frame 839 ("seen in part" -> the standard window, input open; that is fsTa3's
    spot-7 stop) and fsTn4 frame 149 (none -> the standard window). The other 1,288 are
    unchanged (1,276 standard, 11 "f10", 1 "unknown", as before);
  - the 28-frame re-run recording (`20261111T113618-rdp-xmas02-fsTn4`, 0 spots) is shipped and
    marked INVALID (`dataset_ship.py mark-invalid`); fsTn4 is staged again on seed 2612601.
- **O20e (12:1x ICT): fsTn4 done; round 4 trained and FROZEN.**
  - fsTn4 (Crusader, seed 2612601): 11:58:17-12:11:39, rc 0, **6 / 6 spots**, session
    `20261111T115807-rdp-xmas02-fsTn4` (812 frames), shipped. The no-aura held-out is that session
    plus the 1-spot `20261111T113216` (both `-rdp-xmas02-fsTn4`); the INVALID 11:36 one is not
    labelled;
  - the training ended 12:12:32, rc 0 (3 epochs; 2,048 TRAIN / 272 val frames). Its own val (the
    TRAIN distribution, NOT a bar): P 0.983, R 0.940, mAP50 0.989, mAP50-95 0.739 (round 3:
    0.946 / 0.949 / 0.980 / 0.733);
  - **FROZEN 12:16:42: `last.pt` sha256 32e8afae15080d0373a987902f67d99e1619e30928da6aa8bae9725c45107656**
    (5,529,242 bytes), before any held-out file was read. The held-out labels (`--eval-test`, params
    v2) began 12:16:56 against it: fsTa4, then both fsTn4 sessions; fiT10-fiT13 follow their
    pilots.
  - The staging's last `@killmonster2` (12:09:42) did NOT leave the MVP dead: `@mobsearch` at 12:14
    found it alive at (29,142) (a respawn after an earlier staging kill). Killed 12:15:15, "1[dead]"
    read back; p59 started 12:16.

- **O20f (16:26 ICT, BEFORE any score): round 4's held-out complete, the predictions, the pack.**
  - The held-out labels (`--eval-test`, params v2, against the frozen 32e8afae; G2 PASS in every
    session): fsTa4 22 kept frames / 29 labels / 9 floor items; fsTn4 49 / 158 / 16 (and its
    1-spot part 0 / 0 / 0, 45 negatives); fiT10 29 / 32 / 9; fiT11 31 / 31 / 10; fiT12 31 / 31 /
    8; fiT13 20 / 24 / 9. fiT10 / fiT11 come from p59 / p60 (the Rogue IMMUNE, rogue-xmas02.md 4BW:
    a floor item's pixels do not depend on immunity); fiT12 / fiT13 from p61 / p62.
  - The GPU set (predict_dir in the worker, the NAS weights 32e8afae): 4,261 frames over the seven
    sessions, made in four parts (staged 12:11, fiT10-11 13:15, fiT12 15:32, fiT13 16:18) and merged
    (`fi_merge_preds.py`, one weights path). The ONNX set (3647fd35, fi_onnx_pred.py) in three parts:
    staged and fiT10-11 done, fiT12-13 running; never beside a scored pilot.
  - **The pack (seed 68, `pack --round 4 --eval-test`):** 134 crops = 114 item crops (F 76, N 38)
    + 20 E (10 plain, 10 hard); SHORT 6 in the no-aura stratum. Two NEW blind labellers, **S and
    T** (none of A-R), are judging it; each sees only the pack and its own answers file.
  - Nothing of either prediction set has been compared with any label.

### Amendment O21 (2026-11-11 16:5x ICT from `date`): THE ROUND-4 RESULT (scored once) -- NATURAL DROPS UP, NO AURA 100 %, STILL A FAIL

`fi_eval.py --strata r4` once at 16:51:09 (score sha256 0a58ac47...). Inputs: both prediction sets
over the seven sessions (4,261 frames), the pack seed 68's key, labellers S and T (agreement q1 /
q2 133 / 134; **113 crops both yes / good = EVALUATED**), I5 from a 600-s detect server holding
xmas02fi4 (registered IN MEMORY for it: today's pilots' servers stay as the base's) and
eval_latency (300 frames, every 14th ref, 16 threads, a quiet host). The GPU and ONNX sets give the
same I1 recall / I2 / I4 (precision 0.9922 / 0.9934).

| bar | round 4 | round 3 (O19) | round 2 (O16) | bar value | verdict |
|---|---|---|---|---|---|
| I1a recall, AURA | **54 / 69 = 0.783** (fsTa4 staged 14 / 16; pilots fiT10 7 / 11, fiT11 13 / 15, fiT12 8 / 14, fiT13 12 / 13) | 0.806 | 0.928 | >= 0.85 on >= 40 | **FAIL** |
| reported: the pilots' NATURAL drops alone | **40 / 53 = 0.755** | 0.62 | 0.62 | - | (the round's aim) |
| I1n recall, NO AURA | **44 / 44 = 1.000** (fsTn4) | 0.854 | 0.980 | >= 0.85 on >= 30 | PASS (Batt's 95 %: yes) |
| I1 precision | 2,028 / 2,044 = 0.992 | 0.994 | 0.962 | >= 0.85 | PASS |
| I2 | **18 / 25 = 0.72** | 7 / 16 (short) | 0.75 | >= 0.80 on >= 20 | **FAIL** |
| I3 any / her 5 x 5 | 0.37 % / **0.24 %** (7 / 2,975) | 0.42 / 0.27 % | 4.29 / 3.22 % | <= 0.5 % / <= 0.2 % | **FAIL** (5 x 5) |
| I4 | 2 / 170 = 1.2 % | 0.9 % | 11.3 % | <= 5 % | PASS |
| I5 GPU, server p95 vs xmas02gb | 16.62 vs 16.80 ms = 0.989 x | 0.997 x | 0.979 x | <= 1.10 x, <= 35 ms | PASS |
| I5 CPU p95 vs xmas02gb | 780.1 vs 797.7 ms = 0.978 x | 0.931 x | 0.953 x | <= 1.10 x | PASS |

- **VERDICT: FAIL** (I1a, I2, I3's 5 x 5). Not deployed; `xmas02fi4` is registered for I5 only
  (GPU_WEIGHTS after today's pilots, never in MAP_MODELS).
- **What round 4's change did (more natural fight drops in TRAIN, the fight negatives halved):**
  natural drops 62 % -> 75.5 %, the no-aura staging 85.4 % -> 100 %, false boxes stayed down
  (I3 any 0.37 %, I4 1.2 %, precision 0.992).
- **Why I1a fell anyway:** its rows changed. Round 3's aura stratum was half staged (fsTa3 33 of
  62, 32 hit); round 4's is three quarters natural (53 of 69). Staged aura items: 14 / 16 = 0.875.
  The missed rows sit in the pilots' fights (fiT12 6 of 14 missed); each missed row is listed in
  the score file.
- The next lever is again the natural drops beside fights (the stratum the bar now reads);
  Batt's 95 % is met by the no-aura stratum only.
