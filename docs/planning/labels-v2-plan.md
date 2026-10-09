---
title: "Labels v2: the plan -- classes and how each is labelled, the species scope of the planned maps, the data budget and collection plan, a DRAFT pre-registration of v2 vs v1"
status: PROPOSED
date: 2026-10-09
owner: Batt
extends: docs/planning/labels-v2.md
related: [training-cost.md, npc-click-test.md, ../phase3-plan.md, ../demonstrations.md, ../operations/vision-long-lived.md, ../benchmarks/v1-vs-v0png.md]
gate: "Plan + tooling only (Batt 2026-10-09 ~16:55). Nothing here was collected, trained or run live. Collection and training wait for the cold-start fix (option A, docs/operations/vision-long-lived.md, PROPOSED) and quiet IO windows (Batt). Section 5 is a DRAFT pre-registration for the parent to review; it binds nothing until it is moved into demonstrations.md (or a benchmark file) BEFORE any v2 data is collected."
---

# Labels v2: the plan

**Batt, verbatim (2026-10-09 ~16:55):** "Priority from Batt: the detector's blind spots are now the
main safety gap. In parallel with your queue, start labels v2 OFFLINE with one subagent when a slot
is free (tmpfs worktree, outside the market windows, no GPU, no client):
- classes/labels from packets + L3 + camera model: town NPCs (per sprite), a "warp" class from L3
  warp cells, the dialog cut-in as UI/hard negative, decorations (torches) as hard negatives verified
  against packets;
- the species scope for the planned maps (Byalan, Payon, Morroc, Lutie, Glast Heim) and which banked
  frames already cover them;
- the data budget per species (training-cost.md), the collection plan (sessions, GM steps), and the
  pre-registration for v2 vs v1.
Plan + tooling only; collection and training wait for the cold-start fix (option A) and quiet
windows."

**What already decides parts of this** (not re-decided here):
- [labels-v2.md](labels-v2.md) sections 1, 2, 2a and 3 (Batt ~13:15, ~16:10): the `warp` class from
  L3, hard negatives verified against the packets, the cut-in frames, the town NPC class from packets.
- [demonstrations.md](../demonstrations.md) 3.28: a map is walk-ready only when every L3 species AND
  (since ~16:10) its NPC sprites are in the detector's training scope.
- 3.32 item 5 / [npc-click-test.md](npc-click-test.md): the detector's recall on town NPCs is
  **1 / 2,195** sightings. That measurement is the targeted test's; this plan does not repeat it, it
  reuses its method for the v2 bar (section 5).
- [training-cost.md](training-cost.md): the data budget and the formula; its constants come from
  `packages/poring_flow/src/poring_flow/training_cost.json` through `poring_flow.prep.estimate`.

**The tooling** (this branch; host-tested on synthetic data, then run read-only on the banked
sessions in `/dev/shm/poring-lab-demo` and the local KB; nothing written outside `/dev/shm`):
- `packages/poring_dataset/src/poring_dataset/labels_v2.py`: the label generators. Tests:
  `packages/poring_dataset/tests/test_labels_v2.py`.
- `scripts/labels_v2.py`: `scope`, `budget`, `coverage`, `labels`, `negatives`, `verify-region`,
  `warp-measure`. Tests: `services/backend/tests/test_labels_v2_tool.py`.
- They reuse the v1 path unchanged: `qa_export.Labeler` (the backend's camera, the packet->frame
  offset, the GM-command windows, v1's sprite boxes), `Timeline`, `camera.project`,
  `render.predict_sprite`, `talk_calibrate.dialog_timeline`, `ui_mask.CUTIN_GUIDE`,
  `kb_build.classes_for`.

## 1. The class set and how each class is labelled

| id | class | head | labelled from | box |
|---|---|---|---|---|
| 0 | `player` | v1's | packets (objtype 0), v1 unchanged | v0's 34 x 74 at the projected feet |
| 1 | `monster` | v1's | packets (objtype 5), v1 unchanged | `predict_sprite` (catalogued species), else v0's 44 x 40 |
| 2 | `npc` | v1's, now **per sprite** | packets (objtype 6, a drawn class), the job id carried | the NPC's own sprite, else a measured extent, else the frame is EXCLUDED |
| 3 | `warp` | **NEW** | L3 warp cell AND the packets' drawn portal (job 45) AND a visible cell | the projected ground ring (section 1.3) |
| -- | the dialog cut-in | background | packets' dialog state + `ui_mask.CUTIN_GUIDE` | a verified region, never a box |
| -- | decorations (torches, flames, plants) | background | detector phantoms verified against the packets, clustered into sites | a verified region, never a box |

- **Ids 0-2 keep v1's meaning**, so v2 fine-tunes from v1's weights (training-cost.md's incremental
  strategy). Only `warp` is a new output.
- **Every frame is labelled completely or EXCLUDED** (`labels_v2.Frame.excluded` says why). An
  unlabelled drawn object would train as background. The exclusion reasons:
  `npc_unsized`, `portal_unconfirmed`, `warp_partial`, `warp_visibility_unknown`, `l3_warp_unseen`,
  `cutin_unmeasured`, `cutin_region_unavailable`, `self_dead`. v1's rules still apply: GM-command
  windows (2 s), hidden classes (111, 139, 32767), invisibility options, boxes mostly behind the
  fixed UI windows.

### 1.1 Players, and our own character
- v1 unchanged: other players from the packets.
- **Our own GM is NOT labelled by v1.** The S2 sessions' GM played hidden. The RDP runs' GM is
  VISIBLE, so in those frames a player sprite trains as background.
  - v2 carries it as SHADOW (`labels_v2.self_label`: v0's player box at the camera target), so no
    background region may touch it.
  - **Open (Batt):** label it `player`? The GM's appearance is fixed (Novice, Base/Job Lv 1, 3.20a),
    so one measured box would do.

### 1.2 NPCs per sprite (Batt ~16:10)
- **The cell:** each `entity_appear` with objtype 6 and a drawn class, from `Timeline` at the frame's
  capture time minus the packet->frame offset, projected through the camera at the GM's packet
  position: the v1 path (`labels_v2.npc_labels`).
- **The box, in this order:**
  1. **its own sprite:** `predict_sprite`'s idle envelope at the NPC's heading, the same rule as v1's
     monsters (kind `sprite_opaque` / `sprite_quad`);
  2. **a measured extent** (sprite px around the feet, scaled by f / z x k; kind `measured`);
  3. **neither:** v0's 34 x 74 at the feet (kind `unsized`), and the frame is EXCLUDED. A guild flag
     (job 722) is ~95 x 150 px (npc-click-test.md 7): a 34 x 74 box would leave most of it background.
- **The identity is the job id** (the sprite). NPC names are server text and are never committed:
  an NPC is keyed by map, job and cell (`labels_v2.npc_key`).
- **What it needs before any NPC frame is trainable** (none of it exists today):
  - **N1:** the job -> sprite file table. It comes from rAthena's NPC sprite constants at the pinned
    ref (a `kb_build` extension, generated locally, never committed), or from the client's own tables.
  - **N2:** the NPC SPR/ACT read from the GRF into `/dev/shm` (a `sprite_catalog.py` extension:
    `data\sprite\npc\`).
  - **N3:** a label check per sprite on banked frames (phase3-plan M5's check).
  - Player-class NPCs (job ids of player jobs) are composite sprites (body + head): measured
    extents instead.
- **Today:** every banked frame with an NPC on screen is excluded (`npc_unsized`): **1,226 of 2,026**
  banked frames. Of those, **872** have no other reason and would be admitted by N1-N3 alone.

### 1.3 `warp`: L3 cells, confirmed by the packets, visible from the camera
- **Labelled** (`labels_v2.warp_labels`) when all three hold:
  1. L3 lists a warp at the cell (`data/kb/route.json` `warps`);
  2. the packets show the drawn portal there (objtype 6, job 45);
  3. a person's visibility table calls the cell `visible`.
- **Why both L3 and the packets:**
  - L3 alone cannot tell a drawn portal from a hidden one (job 139), nor from one beyond the server's
    view (`AREA_CELLS` 14);
  - the packets alone are not L3 (Batt ~13:15: "auto-labelled from L3");
  - a drawn portal that L3 does not list EXCLUDES the frame (`portal_unconfirmed`).
  - **Found on the banked frames:** prt_church has a job-45 script NPC at (115,122) that is not an
    L3 warp. It excludes **227** church frames until the KB lists script NPCs with the portal sprite
    (npc-click-test.md's P1: every NPC file the server loads).
- **Why the visibility table (found on the banked frames, 2026-10-09):** the packets send a portal
  that map geometry hides.
  - Prontera's building doors are job-45 portals under their roofs: 12 / 12 aligned crops of
    (133,183) and (179,184) show only roof tiles.
  - prt_in (60,77) is behind a wall (its sparkles show above it).
  - prt_church (109,81) and prt_in (69,65) are cut by a wall (`partial`).
  - So the rule is per warp cell:
    - `visible`: labelled;
    - `occluded`: no label, and kept as shadow (no background region may touch it);
    - `partial` or not in the table: the frame is EXCLUDED.
  - The table is a person's reading of `labels_v2.py warp-measure`'s sheets (local:
    `/dev/shm/poring-lab-tmp/labels-v2/warp_visibility.json`; client pixels + rAthena cells, never
    committed).
  - Claude's provisional reading of the 12 banked warp cells: **4 visible** (iz_dun00 (168,173),
    alberta_in (78,44) and (64,31), prt_church (90,81)), **5 occluded**, **3 partial**. A person
    confirms before any cache is built.
  - A later per-frame check (a ring template's correlation) would handle cells whose visibility
    changes with the camera position. It is not built.
- **The box: a ground ring, not a billboard.**
  - The portal is a ring ON the floor, so its box is the bounding box of a projected ground circle
    of radius R around the cell centre (`labels_v2.PortalShape`, `portal_box`).
  - The camera's pitch and the depth come with it. The ellipse's height / width is ~0.7, sin of the
    44.4 degree pitch, as observed.
  - **R = 7 world units (~1.4 cells), PROVISIONAL.**
    - It is Claude's hand reading of the aligned crops (19 crops of the 3 visible portals that had
      ≥ 2 clean crops; the camera's px per world unit taken out).
    - Drawn back on the frames, the box encloses the ring in iz_dun00 (default camera) and alberta_in
      (indoor camera).
    - **How it is measured, for the person who confirms it:** `labels_v2.py warp-measure` crops every
      banked frame around each confirmed portal's projected cell, rescales each crop to one depth
      (f / z), masks the GM, the other units and the UI, and writes the crops' median and a sheet.
      The ring's outer edge is read on the median.
    - The tool's automatic "bright component" is only a HINT: bright floors (alberta_in's tiles) and
      iz_dun00's shrine light join the component, so it over-reads.
- **Banked today:** **140** frames carry a visible-portal label (iz_dun00, alberta_in, prt_church).
  **131** frames are excluded as `warp_partial`.

### 1.4 Hard negatives: verified regions, never boxes
- **The rule** (labels-v2.md section 2; `labels_v2.verify_region`): a region is BACKGROUND only when
  no unit's projected box overlaps it, grown by **20 px** (the camera fit's p95 click error).
  - "Units" means every projected box of the frame: monsters, NPCs, players, portals, our own GM,
    and the boxes hidden behind the UI or the cut-in (`Frame.projected`).
  - A region mostly under a fixed UI window is `ui`; one inside the shown cut-in is `cutin`.
- **The dialog cut-in** (labels-v2.md 2a):
  - **Shown when:** the packets' dialog state is open (`talk_calibrate.dialog_timeline`) with an NPC
    whose cut-in is measured (`ui_mask.CUTIN_GUIDE`, (957,249)-(1183,720), for the prontera guide).
  - **Measured to show none:** prt_church's two NPCs (job 67 at (103,76), job 120 at (103,71)).
  - **Anything else is `cutin_unmeasured`:** the frame is excluded.
  - Units at least half inside the shown cut-in are hidden (shadow), as for the fixed windows.
  - **Found:** on all **120** banked open-dialog guide frames, a job-722 guild flag's projected box
    overlaps the cut-in's extent: only 27 % of it is inside, the rest stands above the art. So under
    section 2's rule as written (the WHOLE extent), **0 / 120** frames qualify.
  - The phantom's own box (984,599)-(1033,644), the hand on the spear, qualifies on **120 / 120**
    (`verify-region`; the 12 closed frames are plain background there).
  - **Proposed:** verify the phantom's region, not the whole extent; the flag gets its own box
    (section 1.2).
- **Decorations:**
  - **Candidates:** detector boxes from the runs' `detections.jsonl` (raw batches, from 2026-10-09)
    and from the HUD scene log (`/dev/shm/poring-lab-route/scene.jsonl*`). The scene log's
    desktop-normalised retained boxes are converted to game px through its zone object
    (`labels_v2.py scene_candidates`). That log is a display TRACKER: its boxes can drift.
  - **Each candidate is judged** on the packets' world at its frame time (`verify_region`).
  - **Each accepted one is back-projected** from its box's foot to the ground (`ground_offset`, the
    inverse of the camera) and clustered into SITES of ≤ 2 cells.
  - **A site is a hard-negative SOURCE (PROPOSED)** with ≥ 10 accepted sightings seen from ≥ 3
    positions of ours (`SITE_MIN_SIGHTINGS`, `SITE_MIN_POSITIONS`). Every frame that uses it
    re-verifies its region on that frame.
- **Found on the banked runs** (`labels_v2.py negatives`):

| run | candidates | verdicts | accepted sites |
|---|---|---|---|
| iz_dun00 held-out 12:38 (HUD log) | 265 | warp 53, unit 89, background 112, GM window 11 | the wall TORCH beside the exit shrine, iz_dun00 (174.0,175.5): 35 sightings, 8 positions, conf 0.25-0.40 (Batt's "torch 29 %"); the shrine's pillar bases beside the portal (169.1,170.8): 37 sightings, 4 positions, conf 0.25-0.56 |
| guild re-run 13:54 (detections + HUD) | 239 | unit 167, background 58, GM window 9, off screen 4, UI 1 | a potted plant, alberta_in (54.0,48.3): 49 sightings, 6 positions, conf 0.26-0.61 |
| town re-run 14:06 (detections + HUD) | 5 | unit 1 (the guide's "monster 0.33": on the NPC itself), background 4 | none (one 4-sighting cluster) |

- **Reading the table:**
  - **Batt's portal phantom** ("monster 25 %") is the 53 `warp` verdicts: boxes over the visible
    portal.
  - **The torch site re-projects onto the flame** on each of the 4 frames drawn, from 4 positions
    of ours up to 23 cells apart. The plant site lands on the plant on the 2 frames drawn.
  - The small clusters (n < 10) stay candidates: tracker drift, or a monster the projection missed by
    more than 20 px.

### 1.5 Our own death
- A dead GM lies on the floor under the client's restart window: not a training frame.
- **The signal (`labels_v2.self_dead_spans`):**
  - our own `entity_vanish` with reason 1 (died) starts the span;
  - our next `map_change`, or a GM-command HP raise, ends it.
- **The positive case:** the iz_dun00 held-out run. All 8 banked frames with the restart window on
  screen are in a span; the frames between deaths are not.
- 3.33's immunity removes deaths from v2's collection; the rule guards the banked runs.

## 2. The species scope of the planned maps

**Source:** the local KB (`data/kb/spawns.json` + metamorphosis, `kb_build.classes_for`; generated at
run time, never committed), through `labels_v2.py scope`.
- Species are mob ids; `labels_v2.py scope --names` prints the names locally.
- The planned maps are the visual-diversity maps in kb_build.py (moc_fild12, pay_fild08, xmas,
  gl_prison), plus Byalan.
- `d` is the PROPOSED difficulty class: n normal, s static (no AI type), b boss / MVP.
  "similar" is Batt's call per species and needs the sprite catalog.
- T = trained in v1.

| block | map | species (spawn slots, d) | banked frames that place it on screen |
|---|---|---|---|
| Byalan | iz_dun00 | 1161 (65 n), 1141 (45 n), 1070 (15 n), 1068 (15 n), 1066 (15 n), 1084 (5 s) | 1141: 6, 1161: 5, 1068: 4, 1070: 3, 1066: 0, 1084: 0 (one run, 50 snapshots) |
| Byalan | iz_dun01 | + 1067 (15 n) | 0 (never visited) |
| Byalan, deeper | iz_dun02-04 | + 1044, 1045, 1065, 1069, 1108, 1144, 1158, 1264 (n), 1142 (s) | 0 |
| Payon | payon | a town: no spawns. NPC sprites: L3 lists none for payon | 0 |
| Payon | pay_fild08 | 1014 (70 n), 1010 (50 n), 1080 (10 s), 1083 (1 s); trained: 1002 T, 1008 T, 1018 T | new: 0; trained: from v1 |
| Morroc | moc_fild12 | 1050 (50 n), 1049 (50 n), 1047 (35 s), 1081 (10 s); trained: 1113 T | new: 0 |
| Lutie | xmas | a town: no spawns. NPC sprites: L3 lists none for xmas | 0 |
| Lutie | xmas_fild01 | 1242 (35 n), 1243 (20 n), 1515 (1 n), 1252 (1 b, MVP) | 0 |
| Glast Heim | gl_prison | 1197 (30 n), 1257 (20 n), 1201 (15 n), 1035 (10 n) | 0 |

**What the banked material covers** (`labels_v2.py coverage` over the 50 banked demo sessions with
frames, 2,026 frames):
- **New species:** only the 12:38 iz_dun00 held-out run places any on screen: 4 of the 6 iz_dun00
  species, **3 to 6 frames each** (budget: 1,500). Every other planned species: **0 frames.**
- **Trained species:** 1002 610 frames, 1063 92, 1008 56, 1113 26, 1018 1. These are banked demo
  frames; v1's NAS cache adds its 13,946 prt_fild08 / prt_church frames.
- **Town NPC sprites** (frames with the sprite on screen; ALL excluded today, `npc_unsized`):
  - prontera: 722 190, 105 176, 92 173, 99 142, 700 9, 84 / 85 / 86 3 each, 50 1, 874 1;
  - prt_church: 79 402, 67 339, 120 334, 71 165, 798 152, 741 142, 745 138, 60 90, 755 57;
  - alberta / alberta_in: 98 7, 59 6, 86 3, 89 4;
  - payon, xmas, morocc: 0.
- **Trainable today** under v2's rules: **571** frames (prt_fild08 500, prt_church 35, prontera 22,
  iz_dun00 11, alberta_in 3).
- **The other frames:**
  - 217 in GM-command windows (the route snapshots follow a GM line);
  - 1,226 `npc_unsized`, 227 `portal_unconfirmed`, 131 `warp_partial`, 10 `self_dead` (frames per
    reason; a frame can have several);
  - the cut-in is shown on 120 frames (the guide's dialogs, `ui_mask.CUTIN_GUIDE`).
- **The NAS-held sessions** (v0 / v1's caches; `build_frame_cache.SCENE_MAPS`, v1-vs-v0png.md's
  session table) hold prt_fild08 and prt_church only. So they cover no planned species.
  - Their per-species counts were not computed here: that reads their packets and frame indexes on
    the NAS.
  - `labels_v2.py coverage <recorded session>` reads `stream.idx.csv` + `packets.jsonl.gz` only (no
    decode). It runs in a quiet window.

**Walk-readiness (3.28) these gaps imply:**
- No planned map can become walk-ready before v2: every one has species with 0 frames.
- The towns also need their NPC sprites (N1-N3).
- prontera's and prt_church's NPC FRAMES already exist (above): what they wait for is the sprite path,
  not collection.

## 3. The data budget, the collection plan, the order

### 3.1 The budget per species (training-cost.md section 2, unchanged)
- **B = 1,500 training frames** containing the species, **≥ 3,000 instances**, **≥ 50 instances in
  every pose cell** (8 directions x its actions).
- d_s scales it: static 750, normal 1,500, boss 3,750. Validation and test frames come in v0's
  proportion (0.40).
- **Proposed for v2's non-species classes** (Batt to confirm):
  - **NPC sprites:** d = 0.5 per sprite (static: one pose per camera), **750 frames per sprite**.
    - A town frame holds most of its NPCs, so the method's linear sum OVERCOUNTS their compute.
    - Train compute is counted on the UNION of the town's frames, and each sprite must reach its own
      750.
  - **`warp`:** one class (portals look the same on every map, Batt): **750 frames** with a labelled
    visible portal, from ≥ 4 maps' backgrounds.
  - **Hard negatives:** at most ~10 % of the training frames, at least 50 frames per accepted site,
    and every cut-in-shown frame that verifies.

### 3.2 The estimate (`labels_v2.py budget` = `poring_flow.prep.estimate` on training_cost.json; NEW species and NEW maps only, in the order below)
- Constants are training-cost.md's ESTIMATES (status ESTIMATE until section 6 measures them).
- The Byalan row reproduces training-cost.md section 5 exactly (tested).

| block | new maps | new species (Σd) | map prep (h) | collect (S2 h) | train (compute h) | wall h: night / mix |
|---|---|---|---|---|---|---|
| Byalan | iz_dun00, iz_dun01 | 7 (6.5) | 10.4 | 8.45 | 15.42 | 24.5 / 30.5 |
| Payon | payon, pay_fild08 | 4 (3.0) | 10.4 | 3.9 | 7.12 | 11.3 / 14.1 |
| Morroc | moc_fild12 | 4 (3.0) | 5.2 | 3.9 | 7.12 | 11.3 / 14.1 |
| Lutie | xmas, xmas_fild01 | 4 (5.5; the MVP 2.5) | 10.4 | 7.15 | 13.05 | 20.7 / 25.8 |
| Glast Heim | gl_prison | 4 (4.0) | 5.2 | 5.2 | 9.49 | 15.1 / 18.8 |
| **the five blocks** | 8 | **23 (22.0)** | **41.6** | **28.6** | **52.2** | 82.9 / 103.3 |
| Byalan deeper (later) | iz_dun02-04 | 9 (8.5) | 15.6 | 11.05 | 20.17 | 32.0 / 39.9 |

- **Not in the estimate:**
  - the NPC sprites (N1-N3 are map prep: tooling, not S2 hours);
  - their training share, at 750 frames per sprite on the union of town frames: prontera's ~10 and
    prt_church's 9 sprites;
  - `warp` (750 frames);
  - the hard negatives;
  - the LUTIE MVP (1252, one spawn slot): Batt may drop it from scope (a workflow avoids it) or keep
    it at d 2.5.
- **The calendar it implies:** about 4 days of night-only training for the five blocks (82.9 h), plus
  ~29 S2 hours of collection that pause training. Batt sets the order and how many blocks one round
  takes.

### 3.3 The collection plan (waits for option A and quiet windows)
**Gates, before any collection session** (Batt):
- **G1:** the cold-start fix, option A: one long-lived vision container per day
  ([vision-long-lived.md](../operations/vision-long-lived.md), PROPOSED; its proof first). Until then
  every vision start is a cold start that stalled quant at ~100 % (2026-10-09 16:46).
- **G2:** quiet IO windows, measured by `scripts/runbooks/quiet_start.py`; never in a market window
  (09:30-10:15, 14:00-14:45 ICT); one container start at a time.
- **G3:** one Windows session: collection is S2 (the bot's primary path, ADR-0014; training-cost.md's
  "S2 hours") and pauses training; RDP walk runs cannot run alongside.
- **G4:** the KB covers the map: route.json warps (walk@17 B fails closed without them), spawns, the
  GAT extracted into `/dev/shm`, the indoor table, the camera check, the species' sprites catalogued
  (`sprite_catalog.py`; Byalan F1-F2 are, the other blocks are not).

**Each session** (M7's protocol, with today's safety layers):
1. **A CLEAN start:**
   - a client screenshot judged by the UI gate (`scripts/ui_gate.py`: no dialog, menu or window
     open; closes only by known steps);
   - the GM's fixed state checked (3.20a: Base / Job Lv 1, no notices);
   - **3.33's immunity** ON after each login (`@monsterignore`), judged per run offline (zero acts on
     the GM).
2. **Natural spawns first:** walk@17's long walks (3.31's legs) across the map. That covers the
   map's own spawns, its backgrounds, its portals (visible / occluded cells) and its decoration
   sites.
3. **Spawn blocks** for species the walks leave short, as M7 did:
   - `@monster <id> 8` at a planned cell (a walkable cell outside every warp area);
   - ~25 min of recording per species at the stream's own rate, sampled to the cache's ~2 fps;
   - `@killmonster2` between blocks.
   - The labels skip each GM line's 2 s window. Every typed line passes the UI gate and the typing
     guard (`chat_guard`: no 3rd identical line).
4. **Portal passes:** `@warp` beside each L3 warp cell of the map, so the person reading
   `warp-measure`'s sheets can classify it.
5. **Towns:** walk the NPC-dense spots (npc-click-test.md's stands). One deliberate dialog per NPC
   whose cut-in is unmeasured (`talk_calibrate.py drive`), so `ui_mask measure` gets its extent.
6. **After each session:**
   - `labels_v2.py coverage` (per species / sprite / class against the budget, and the exclusions)
     and `labels_v2.py negatives`;
   - the session ships to the NAS in a quiet window (`dataset_ship.py`; the banked tmpfs sessions
     first: labels-v2.md section 3 lists them).

**The order (PROPOSED):**
1. **Tooling first, no session:**
   - N1-N3 (NPC sprites) and the KB's P1 (script NPCs with the portal sprite; every NPC file);
   - the warp visibility table for the 12 banked cells, confirmed by a person;
   - `build_frame_cache.py --labels v2`: widen `SCENE_MAPS`, read demo sessions' snapshots and
     frames, write `labels_v2.V2_CLASSES` as the manifest's names, skip excluded frames;
   - bank the tmpfs sessions (labels-v2.md 3).
2. **Byalan** (iz_dun00 + iz_dun01): sprites catalogued, KB complete, the held-out dungeon's map.
3. **Towns' NPC sprites** (prontera, prt_church, alberta): mostly ALREADY banked. They need step 1,
   plus a session for sprites short of 750 frames.
4. **Payon, Morroc, Lutie, Glast Heim:** the visual-diversity maps, in the order walk@17's
   diversity block runs them. Each needs G4's sprite catalog.
5. **Byalan deeper** (iz_dun02-04): later, with a workflow that goes there.

## 4. The tooling, as built (this branch)

| piece | what it does | tested on |
|---|---|---|
| `labels_v2.warp_labels`, `l3_warps`, `portal_box`, `PortalShape`, `warp_key` | the `warp` rule of 1.3 | synthetic worlds through the real camera; the banked iz_dun00 / alberta_in frames, drawn |
| `labels_v2.npc_labels`, `drawn_npcs`, `npc_key` | NPCs per sprite (1.2) | synthetic; `predict_sprite` stubbed as in v1's tests |
| `labels_v2.cutin_for`, `assemble` | the cut-in as dynamic UI; one frame, fail closed | synthetic |
| `labels_v2.verify_region`, `ground_offset`, `cluster_sites`, `Site` | hard negatives (1.4) | synthetic; the camera's inverse round-trips |
| `labels_v2.self_dead_spans`, `self_label` | 1.1, 1.5 | synthetic; banked positive case |
| `labels_v2.Coverage` | counts per class / species / sprite, exclusions by frame | synthetic |
| `labels_v2.median_crop`, `bright_extent`, `otsu` | the portal measurement's helpers | synthetic |
| `scripts/labels_v2.py` | the CLI over banked sessions (demo or recorded) and the KB | temp sessions, a synthetic KB (ids only), a synthetic HUD log |

- **Tests:** 19 + 12 new, all passing; with `packages/poring_dataset/tests`, `test_guards.py`,
  `test_locale_guard.py`, `test_qa_export.py`, `test_kb_build.py`: all pass. Strict mypy is clean.
- **The banked runs above used:**

      labels_v2.py --kb <main>/data/kb coverage <the 50 sessions> \
        --warp-visibility /dev/shm/poring-lab-tmp/labels-v2/warp_visibility.json
      labels_v2.py --kb <main>/data/kb negatives <session> \
        --scene-log /dev/shm/poring-lab-route/scene.jsonl.1 /dev/shm/poring-lab-route/scene.jsonl
      labels_v2.py --kb <main>/data/kb verify-region <3 guide sessions> --region 984,599,1033,644
      labels_v2.py --kb <main>/data/kb warp-measure <sessions>

## 5. DRAFT pre-registration: v2 vs v1 (for the parent to review; it binds nothing yet)

**Hypothesis:** v2's labels (warp, NPCs per sprite, hard negatives, the new species) give a detector
that sees the new species and the town NPCs, stops calling portals, the cut-in and decorations
monsters, and loses nothing on v1's own sets.

**The models:**
- v1 = `v1png-20261008`'s last.pt (when its training ends).
- v2 = fine-tuned from it, training-cost.md's incremental strategy: the v2 budget plus an equal replay
  sample of v1's frames, E / 2 = 15 epochs, the same YOLO11n / imgsz 1280 / batch / AMP.
- Training seed 20261004 (v0 / v1's). One run each, no seed variance (stated, as for v1).

**The test sets** (never trained or selected on; split BY SESSION):

| set | what | why |
|---|---|---|
| T1 | v1's test sessions: indoor-c, the gold set (27 hand-checked frames), 054429 (domain shift, reported apart) | forgetting |
| T2 | per block, ONE natural-spawn session recorded for test only (a different start area and day from training) | the new species on their own maps |
| T3 | a held-out MAP per kind: iz_dun01 natural spawns if its species are trained from iz_dun00 + spawn blocks (1067 by spawn), and alberta's town (its NPC sprites partly shared with prontera) | generalisation to a map never trained |
| T4 | the banked tmpfs frames NOT used for training: the cut-in guide frames (120 + 12 closed) and the 12:38 iz_dun00 run | the phantoms Batt saw, on the frames that showed them |

**Metrics** (conf 0.25, the gate's threshold; scored against packet truth with v2's rules; each with
its 95 % Wilson interval):
- **M1** per class: precision and recall, position only (`gold_eval.py`'s position scorer: centre in
  the box, same class, one-to-one), per test set.
- **M2** per species recall on T2 / T3 (monsters with ≥ 50 sightings).
- **M3** town NPC recall PER SPRITE: npc-click-test.md 4.1's method (any class; the foot within 40 px
  or the feet inside the box grown by 20 px). Its v0-PNG baseline is 1 / 2,195.
- **M4** `warp` recall and precision on the visible confirmed portals.
- **M5** the phantom rates:
  - (a) **portal-as-monster:** frames with a visible portal on which a non-`warp` box overlaps it;
  - (b) **cut-in:** shown frames with any box ≥ 50 % inside the phantom's region (v0-PNG: 120 / 120);
  - (c) **decorations:** per accepted site, the frames with the site in view and a box on it.

**The bar (DRAFT numbers for Batt):**
- **B1, no forgetting:** on T1's gold set, monster P and R each ≥ v1's − 0.02.
- **B2:** every new species on T2: recall ≥ 0.90.
- **B3:** every town NPC sprite with ≥ 50 sightings on T3 / T4: recall ≥ 0.90.
- **B4:** `warp` recall ≥ 0.90 and portal-as-monster ≤ 2 %.
- **B5:** cut-in phantom ≤ 2 % of shown frames; each accepted site ≤ 2 % of its in-view frames.
- **Reported, no bar:** mAP50 / mAP50-95 per set, T3 apart, per-epoch validation curves.
- **Scored ONCE as written.** A failed B1 means v2 is not adopted, whatever B2-B5 say.

**Seeds reserved:** 20261200-20261209 for the T2 / T3 test sessions' harness draws (unused anywhere
on 2026-10-09).

## 6. What could not be determined offline

| item | why | what settles it |
|---|---|---|
| NPC sprite boxes (all 22 banked sprites) | no job -> sprite table, no NPC SPR/ACT extracted; player-class NPCs are composites | N1-N3 (section 1.2) |
| per-species counts on the NAS-held frames | needs the NAS sessions' packets + indexes | `labels_v2.py coverage` on them, in a quiet window |
| the portal ring radius | a hand reading of 19 crops; the automatic hint over-reads on bright floors | a person on `warp-measure`'s medians |
| the visibility of every warp on the planned maps | only 12 cells have banked frames | the portal passes of 3.3 step 4 |
| other NPCs' cut-ins, other anchors | never seen (ui_mask's own gap) | one deliberate dialog per NPC (3.3 step 5) |
| L3 completeness per map | route.json lists `warp` lines only (not script NPCs with the portal sprite, e.g. prt_church (115,122)); no NPC lists for payon / xmas / morocc | the KB's P1 (npc-click-test.md) |
| whether our GM is labelled `player` | a policy | Batt (1.1) |
| "similar" species (half budget) | needs the sprite catalog per species | Batt, per species |
| the HUD log's small sites (n < 10) | tracker drift vs a projection miss | more sightings, or `detections.jsonl` only |
| windows the UI gate cannot see in banked frames (the restart window when not dead, an options window) | the gate reads a dialog, a menu and four windows only | excluded only via `self_dead` today |
