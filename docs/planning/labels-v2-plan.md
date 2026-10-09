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
  - ~~**Open (Batt):** label it `player`?~~ ➡️ **DECIDED (Batt 2026-10-09 ~19:30): label our GM as
    "player"** (`scripts/labels_v2.py` passes `self_label` with the labelled units; hidden behind
    the UI or the cut-in, it goes to shadow like any unit). The GM's appearance is fixed (Novice,
    Base/Job Lv 1, 3.20a), so v0's player box at the camera target is used until one is measured.

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
    ➡️ **2026-10-09 ~19:30 (section 7.3): it is a `warp` LINE**, npc/quests/quests_prontera.txt:2174,
    a file route.json's hand list does not read. `kb_first_workflow.py --also prt_church` lists it.
    `labels_v2.l3_warps` still reads route.json: pointing it at the new KB is a follow-up, not done.
    ➡️ DONE 2026-10-09 ~21:15 (e6f3b1d, merged 748260d): route.json's warp lists now come from this KB's COMPLETE per-map list (kb_route.py; prt_church gains (115,122) and (166,106)), so labels_v2 and npc_noclick read the completed lists.
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
    ➡️ **CONFIRMED by Batt, 2026-10-09 ~20:20** ("The warp visibility table (4 visible / 5
    occluded / 3 partial): CONFIRMED"), from the contact sheet sent at ~19:55. The local table is
    unchanged.
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

**The order: ➡️ DECIDED 2026-10-09 ~18:20 (Batt; section 7, verbatim there):**
1. **Tooling, no session:** N1-N3, KB P1, the warp visibility table. KB P1 for the first
   workflow's maps is built (`scripts/kb_first_workflow.py`, section 7).
2. **The TRAINING GROUNDS** (new_N-M), with their NPCs and warps (section 7.1-7.3).
3. **The Merchant job-change maps** (alberta_in, alberta and the delivery destinations, section 7.4).
4. **Everything else later:** towns at large, the diversity maps, Byalan.

**➡️ SUPERSEDED the same day by the order above (Batt ~18:20, "replaces my town-first
suggestion").** Kept as history: the town-first order this section first proposed.
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
| L3 completeness per map | route.json lists `warp` lines only (not script NPCs with the portal sprite, e.g. prt_church (115,122)); no NPC lists for payon / xmas / morocc | the KB's P1 (npc-click-test.md). ➡️ **Built for the first workflow's maps** (section 7.3, `kb_first_workflow.py`): every file the server loads. prt_church (115,122) turned out to be a `warp` line (npc/quests/quests_prontera.txt:2174), from a file route.json does not read; `--also prt_church` lists it |
| whether our GM is labelled `player` | a policy | Batt (1.1) |
| "similar" species (half budget) | needs the sprite catalog per species | Batt, per species |
| the HUD log's small sites (n < 10) | tracker drift vs a projection miss | more sightings, or `detections.jsonl` only |
| windows the UI gate cannot see in banked frames (the restart window when not dead, an options window) | the gate reads a dialog, a menu and four windows only | excluded only via `self_dead` today |

## 7. First workflow scope: the Novice training grounds -> Merchant (2026-10-09 ~19:30)

**Batt, verbatim (2026-10-09 ~18:20):** "Batt's call for labels v2 ORDER (replaces my town-first
suggestion): start with the NOVICE TRAINING GROUNDS. A novice can reach the Merchant job
requirements there alone, so it's exactly the first workflow's scope; it has both monsters to
attack and monsters NOT to attack (a real test of ADR-0020's target/ignore lists); some species are
already in our data; the account 2000001 was already there (new_4-1). Verify from the pinned server
data (local, nothing committed) before planning:
1. the training-ground maps (names, connections, warps), their spawns per map, and which species
   must NOT be attacked and why (quest/protected/other), from the scripts;
2. every NPC there (for KB P1 and the NPC sprite set);
3. the full Novice -> Merchant path from L3: every map the job change needs beyond the training
   grounds (the merchant guild in Alberta, any delivery/quest maps), so the scope covers the whole
   first workflow;
4. then the budget with training-cost.md (species, NPC sprites, warps on those maps only) and the
   collection plan.
New order: tooling (N1-N3, KB P1, visibility table) -> TRAINING GROUNDS (+ their NPCs and warps) ->
the Merchant job-change maps -> everything else later (towns at large, diversity maps, Byalan)."

**How it was verified (offline; nothing collected, nothing committed from the server tree):**
- **The tool:** `scripts/kb_first_workflow.py` (tests: `services/backend/tests/test_kb_first_workflow.py`,
  synthetic snippets only). It writes `data/kb/first_workflow.json` (gitignored, local): per map the
  warps, spawns, every NPC keyed by `file:line` (sprite id, cell, facing, kind, drawn, what its
  script warps / tests / calls), mapflags, and the Novice -> Merchant path. Names, menus and serials
  stay in that JSON; this section quotes ids, map names, cells and counts only.
- **Which files:** the map-server's own list, not a hand list. A pre-renewal map-server loads
  `npc/pre-re/scripts_main.conf` (map.cpp `map_reloadnpc`); the tool follows its `npc:` / `delnpc:`
  / `import:` lines with `map_reloadnpc_sub`'s rules: **522 files**, every one parsed, **0 parse
  problems** (unbalanced script, unknown definition type). rAthena e985006, pre-renewal.
- **Which maps:** derived (module docstring): the char-server's start points, closed over the warp
  lines and the literal NPC warps; the Merchant job script's NPCs and the functions it defines;
  travel between them on (map, room) nodes (section 7.4).

      export PYTHONPATH=$PWD/scripts:$PWD/packages/poring_dataset/src:$PWD/packages/poring_flow/src
      M=/home/batt/docker/poring-lab
      $M/.venv/bin/python scripts/kb_first_workflow.py build --kb-dir $M/data/kb \
        --mapcache-dir $M/packages/poring_dataset/src/poring_dataset/_generated --also prt_church
      $M/.venv/bin/python scripts/kb_first_workflow.py summary          # ids / cells / counts
      $M/.venv/bin/python scripts/kb_first_workflow.py check-packets /dev/shm/poring-lab-demo/2026*
      $M/.venv/bin/python scripts/kb_first_workflow.py budget --kb-dir $M/data/kb

### 7.1 The training-ground maps (a)

**The maps.** The server's map list has 20: new_N-M, N = 1..5 copies, M = 1..4 stages. Within a
stage the five copies are the SAME map: their server walkability grids are byte-identical (map
cache), so there are **4 layouts**. ~~Visual identity of the copies (client files) is not verified.~~
➡️ **2026-10-09 ~20:40: VERIFIED, IDENTICAL per layout in the client files too** (Batt's 7.7 item 4
condition; `scripts/map_identity.py check`, tests `services/backend/tests/test_map_identity.py`):
- **The client has no separate files for the copies.** Its rename table
  (data\resnametable.txt) sends every new_N-M's .rsw, .gnd and .gat to ONE file set per stage,
  new_zone0M (15 aliased names per stage). No new_N-M file exists in the archive, so every copy of
  a stage opens the same RSW, GND and GAT entries, and with them the same textures and models.
- **Per layout: IDENTICAL, 4 / 4.** Stage 1: 21 RSW models (235 placed), 39 textures (10 ground,
  the rest the models' own). Stage 2: 18 models (139), 31 textures. Stage 3: 13 models (239),
  27 textures. Stage 4: 7 models (303), 18 textures. 0 missing and 0 unreadable references.
- **Client and server agree:** each copy's client GAT against the server's map cache, 20 / 20 maps:
  0 cells differ in walkability, 0 in cell type.
- **Every file parsed** (RSW 2.1, GND 1.7, RSM 1.4); the RSW parse ends exactly at the quad tree.
  Stage 2-4's RSWs are MIXCRYPT; they were read with the host-local study decoder (grf_read
  `--decode-mixcrypt`, Batt 2026-10-05 option (a): offline, study only).
- **The caveat: one archive.** This is the host's only client GRF, the Thai data.grf on the NAS.
  The lab client draws from the kRO data.grf on the Dell. The 12 KB species' sprites were
  byte-identical between the two (thai-data-experiment.md 3d), but nobody has compared the map
  files or the rename table. Two cheap checks would close it, and each needs a person on the Dell:
  the kRO table's new_N-M lines, or the declared sizes of the new_zone0M entries in both GRFs.
- The hashes and the client's file names stay in the local JSON
  (`/dev/shm/poring-lab-tmp/labels-prep/map_identity.json`), never committed.

**16 are reachable; new_2-4, new_3-4, new_4-4, new_5-4 are never reached** (they carry mapflags
only). All 20 carry the mapflags nobranch, nomemo, nopenalty, noteleport.

**Which copy a character is on.** Not a script rule: the CHAR server places a new pre-renewal
character at one of five start points, new_N-1 (53,111), N picked at random (conf/char_athena.conf
`start_point_pre`; char.cpp:1400, `rnd() % start_point_count`). So 2000001 got copy 4 at creation.
The copy only matters on stages 1 and 2; after that every novice shares the same maps:

| stage | maps used | how a novice gets there | leaves by |
|---|---|---|---|
| 1, the yard | new_N-1, its own copy | char creation (53,111) | portal (148,112) span 2,2 -> new_N-2 (100,9); or job 727 at (53,114) -> new_1-2 (99,99) once the tutor flags are set (novice.txt:219) |
| 2, the reception | new_N-2, its own copy | the yard's portal | job 86 at (100,29): -> **new_1-2** (100,70) for everyone (novice.txt:118), or skip the training -> one of 6 towns at random with a savepoint (novice.txt:135-158). Portal (100,6) back to new_N-1 (144,112) |
| 2, the school | **new_1-2 only** | the reception, any copy | job 92 at (38,182): savepoint new_1-2 (23,188), warp **new_1-3** (96,21) (novice.txt:2542-2543); tutors send to (28,178) beside it |
| 3, combat | **new_1-3 first**, then any new_N-3 | the school | job 84 at (95,30) on every copy moves between copies: from 1-3 to 2-3 / 3-3 (random) or 4-3 / 5-3 (random); from 2-3 / 3-3 back to 1-3 or to 4-3 / 5-3; from 4-3 / 5-3 to 1-3 or 2-3 / 3-3 (novice.txt:2647-2718). Job 85 at (96,174) -> **new_1-4** (99,10) (novice.txt:2740) |
| 4, the exam | **new_1-4 only** | job 85, any combat copy | job 46 at (100,29): graduation (section 7.4) or a random field start (novice.txt:3762-3836) |

- Inside new_N-2 two internal portal pairs join its rooms: (126,106) -> (160,171), (156,171) ->
  (123,106); (73,106) -> (41,172), (46,172) -> (78,106). New_N-3 and new_1-4 have no portals.
- The other exits: the school's job 117 at (118,108) sends to a town chosen at run time
  (`warp .@mapn$`, novice.txt:1371, 1434).

**Spawns** (novice.txt:4278-4302; every line is `map,0,0`: anywhere on the map, no respawn delay
given). Nothing else spawns on these maps (no script `monster` command names them):

| map | species (count) | job EXP per kill, spawn-weighted | kills to Novice JL10 (1,151 job EXP) | NPC-sell zeny per kill | kills to 1,000 z |
|---|---|---|---|---|---|
| new_1-3 | 1002 (10), 1113 (10), 1063 (10), 1011 (10), 1184 (5) | 2.22 | 518 | 7.78 | 129 |
| new_2-3, new_3-3 | 1009 (10), 1050 (10), 1010 (10), 1012 (10), 1184 (5) | 4.00 | 288 | 15.69 | 64 |
| new_4-3 | 1052 (10), 1051 (10), 1053 (10), 1014 (10), 1184 (5) | 32.67 | 35 | 16.54 | 60 |
| new_5-3 | 1052 (10), 1051 (1), 1053 (1), 1014 (1), 1184 (5) | 16.17 | 71 | 14.64 | 68 |
| the other 12 | none | | | | |

- Job EXP from mob_db at the server's rates (exp.conf: 100 / 100); zeny from the local KB's drop
  tables at their effective rates (drops.json) times the NPC sell price. Kills are assumed in spawn
  proportion. The tutors' own job EXP gifts (while JL < 7) are ignored, so the kill counts are
  upper bounds. **Batt's premise holds on the data:** the job level, the skill points and the
  zeny the job change needs (7.4) are all reachable on the combat maps, and new_1-2's shop (job 90
  at (28,185)) buys the loot.

### 7.2 Species NOT to attack, and why (b)

**The scripts name none.** Checked in every loaded file that names these maps:
- the 25 `monster` lines carry no event label; novice.txt has no kill counter (`OnMyMobDead`,
  `mobcount`, `killmonster`), no quest on a species, no "protected" flag; the maps carry no mapflag
  beyond the four above (nopenalty: no EXP loss on death);
- the combat trainer (job 84 at (95,30), novice.txt:2647) warns in general that many of them are
  aggressive, naming no species;
- the only "do not attack" rule in the scripts is about OTHER PLAYERS' targets: the battle tutor
  (job 84 at new_1-2 (17,182), novice.txt:2193; its lines 2340 and 2444) discourages attacking a
  monster someone else is already fighting. It concerns the community server, not species.

**What the DATA says** (mob_db; AI bits from mob.hpp's `MONSTER_TYPE_xx`). These are candidate
reasons for an IGNORE list, NOT script reasons; the list is Batt's:

| species | where | level / HP | job EXP | AI | why it might be IGNORE |
|---|---|---|---|---|---|
| 1184 | every new_N-3, 5 each | 1 / 30 | **0** | 04, **aggressive** | worth nothing toward JL10, and it attacks first: the case ADR-0020 open question 24 asks about (an aggressive species on IGNORE) |
| 1014 | new_4-3 (10), new_5-3 (1) | 16 / 510 | 108 | 01 | far above a level-1 novice (the copies the trainer calls harder) |
| 1053, 1051 | new_4-3 (10 each), new_5-3 (1 each) | 10 / 170, 6 / 126 | 18, 5 | 07: looter + **assist** | hitting one draws the others |
| 1009 | new_2-3, new_3-3 (10) | 5 / 92 | 5 | 03: assist | as above |
| 1261 | 1 in each of alberta, prontera, geffen, morocc, izlude, payon (respawn 2-3 h) | 38 / 2,980 | 688 | 02, looter | the Merchant path's towns (7.4): a city cleaner, npc/pre-re/mobs/citycleaners.txt (its header states the purpose: monsters that clean the cities); far beyond a novice |

**A proposal for ADR-0020's target / ignore test** (MW3's positive case, Batt decides): new_1-3,
TARGET 1002, 1113, 1063, 1011; IGNORE 1184. All five are on one map, four are trained or new
there, and the ignored one is aggressive.

### 7.3 Every NPC there (c), and how completeness was checked

| map(s) | NPCs by kind | drawn sprite ids | drawn portal cells |
|---|---|---|---|
| new_N-1 (each copy) | 3 dialog, 1 invisible (sprite 111 at (66,114): a clickable spot on the map art) | 105 (144,116) and (144,107); 727 (53,114) | 1 |
| new_1-2 | 11 dialog, 1 shop | 86 (100,29), 751 (99,105), 753 (83,111), 726 (115,111), 117 (118,108), 92 (161,182) and (38,182), 754 (182,182), 47 (184,172), 105 (121,101), 84 (17,182); shop 90 (28,185) | 5 |
| new_2..5-2 | 1 dialog | 86 (100,29) | 5 each |
| new_N-3 (each copy) | 2 dialog | 84 (95,30), 85 (96,174) | 0 |
| new_1-4 | 2 dialog | 46 (100,29), 57 (91,22) | 0 |
| new_2..5-4 | none | | 0 |

- **The training grounds' NPC sprite set (N1-N3): 15 drawn sprites:** 46, 47, 57, 84, 85, 86, 90,
  92, 105, 117, 726, 727, 751, 753, 754. Sprite 111 is not drawn.
- **No training-ground script calls `cutin` or any function**, so no dialog there shows a cut-in
  (labels-v2.md 2a: nothing to measure). On the Merchant path, the two Kafra-sprite quest NPCs
  (prontera (248,42), izlu2dun (106,58)) do call `cutin`: unmeasured, so their dialog frames are
  excluded until `ui_mask measure` has them.
- **The Merchant path's maps** (7.4), every NPC there (whole maps, not only along a route):

| map | NPCs: dialog / shop / script portal / invisible (trigger) | drawn sprites | portal cells | spawns |
|---|---|---|---|---|
| alberta_in | 25 / 6 / 0 / 1 | 23 | 25 | none |
| alberta | 47 / 1 / 0 / 2 | 36 | 11 | 1261 x1 |
| prontera | 78 / 10 / 0 / 4 (+2 triggers) | 47 | 20 | 1261 x1 |
| geffen | 42 / 2 / 1 / 3 | 32 | 11 | 1261 x1 |
| geffen_in | 30 / 7 / 0 / 2 | 26 | 25 | none |
| morocc | 39 / 0 / 1 / 1 (+1 trigger) | 29 | 13 | 1261 x1 |
| morocc_in | 22 / 3 / 0 / 0 | 20 | 36 | none |
| izlude | 24 / 4 / 0 / 2 | 23 | 8 | 1261 x1 |
| izlu2dun | 3 / 0 / 0 / 0 | 3 | 1 | none |
| payon | 63 / 3 / 0 / 5 (+1 trigger) | 38 | 16 | 1261 x1 |

  "Drawn" counts NPCs whose script hides them at start (`hideonnpc` / `disablenpc` of themselves)
  as conditional, not drawn: the packets confirm it on prt_church's six wedding-row NPCs
  (effect_state 2).

**How completeness is checked (KB P1):**
1. **Every loaded file is parsed** the way the server splits it: 522 / 522, 0 problems. An NPC on a
   scope map can only come from a top-level definition (script, duplicate, shop, warp, monster,
   mapflag) or a script command that places something at run time.
2. **Every line of every loaded file that names a scope map is accounted for** (`completeness` in
   the JSON): a comment, a definition on that map, a warp line to it, another map's definition that
   names it, or a script statement classified by its command (warp, savepoint, condition, dialog
   text, array). **0 unclassified lines; 0 run-time placements** (`monster`, `areamonster`,
   `movenpc`, `setcell`, `setwall`, `duplicate_dynamic`) on any scope map. The files the server does
   NOT load (the renewal tree, tests) are listed apart and ignored.
3. **Against the banked packets** (`check-packets`, the 85 demo sessions in tmpfs): every NPC object
   (objtype 6) the server showed on a covered map is in the KB at that cell with that sprite:
   **49 / 49** (prontera 16, prt_church 19, alberta_in 6, alberta 2, izlu2dun 2, prt_fild08 3,
   iz_dun00 1), 0 at a wrong sprite, 0 missing. The training grounds have NO banked packets: their
   check is the first collection session's packets.
4. **Two facts found on the way:** prt_church (115,122) is a `warp` line
   (npc/quests/quests_prontera.txt:2174; section 1.3's 227 excluded frames); prontera's five
   guild flags (job 722) come from the guild files and are in the KB.

### 7.4 The Novice -> Merchant path (d)

**The steps** (keys are the script lines; the dialog choices are in the local JSON):
1. **Yard -> reception -> school** (7.1). The reception asks the player to TYPE their character's
   name (`input`, novice.txt:86) before the training option.
2. **Combat (new_N-3):** reach Novice JL10, put 9 skill points into Basic Skill, earn 1,000 zeny
   (start zeny 0, char_athena.conf; sell loot to new_1-2's shop, reached back through the savepoint
   new_1-2 (23,188)).
3. **Exam (new_1-4):** first job 57 at (91,22) (any job's information sets the flag the exam
   needs, novice.txt:4023-4229), then job 46 at (100,29), which needs free weight
   (`checkweight`, novice.txt:2760) and the flag (novice.txt:2765). Its aptitude test is a series of
   menus; then either the job it suggests or the player's own pick from a six-job menu
   (`S_UserJobchoice`, novice.txt:3860).
   **Merchant either way:** savepoint alberta (30,232), warp **alberta_in (62,44)**
   (novice.txt:3518-3519 suggested, 3970-3971 picked). Items: 4 free Kafra teleport tickets
   (item 7060) on the suggested path (novice.txt:3482), 5 on the picked one (novice.txt:3932).
4. **The application** (alberta_in, job 86 at (53,43), merchant.txt:34; the job changer): Basic
   Skill > 8 (`F_CanChangeJob`, Global_Functions.txt:626-628), the 1,000 zeny fee or 500 now and 500
   at the end (merchant.txt:329, 343, 131). The script then picks the delivery AT RANDOM:
   `rand(1,4)` (merchant.txt:383), each with two serial numbers (`rand(2)`, merchant.txt:486), so
   8 states; the Byalan option also hands a message item (1072; 200 z reward at the end).
5. **The storehouse** (alberta_in, job 83 at (28,29), merchant.txt:498; reached from the
   arrival room through the internal portal (64,31) -> (24,29)): pick the destination (4-option
   menu) and TYPE the 7-digit serial (`input`, merchant.txt:685; 1,000,000-5,000,000). A wrong
   serial still gives a box, the wrong one.
6. **The delivery:** one of four NPCs swaps the box for a voucher (table below).
7. **Back to the storehouse** (the voucher check: a wrong or missing voucher FAILS the test,
   merchant.txt:553, as does admitting a lost package, 581 and 607; the job changer then erases the
   record, merchant.txt:100-106, and nothing returns the fee), then **the job changer**
   (merchant.txt:155: the job change).

**The four delivery options** (every one the script can choose). Routes are on (map, room) nodes,
from and back to the storehouse's room; Kafra teleports on the free tickets:

| option (state values) | destination NPC | route (fewest moves), map changes | Kafra hops (tickets) | zeny |
|---|---|---|---|---|
| 1, 2 | prontera (248,42), sprite 116 (merchant.txt:941) | alberta_in -> alberta -> Kafra -> prontera; back by Kafra; 4 | 2 | 0 |
| 3, 4 | geffen_in (155,122), sprite 47 (merchant.txt:860) | alberta -> Kafra prontera -> Kafra geffen -> door (61,180) -> geffen_in; back the same way; 8 | 4 | 0 |
| 5, 6 | morocc_in (140,102), sprite 86 (merchant.txt:775) | alberta -> Kafra morocc -> door (274,269) -> morocc_in, then its internal portal (144,122) -> (144,106); back through (144,109) -> (144,125) and (136,136); 6 | 2 | 0 |
| 7, 8 | izlu2dun (106,58), sprite 116 (kafras.txt:601 calling merchant.txt's `F_MercKafra`, pre-renewal only) | NO Kafra goes there. Fewest moves: alberta boat (189,151, sprite 100) 500 z -> izlude; izlude boat (201,181) 150 z -> izlu2dun; back izlu2dun (108,27) free -> izlude; izlude (182,186) 250 z -> alberta; 6 | 0 | 900 |
| 7, 8, least zeny | | Kafra prontera, Kafra izlude, boat 150 z, back, Kafra payon, Kafra alberta; 8 | 4 | 150 |

- **Every map the job change needs beyond the training grounds:** alberta_in, alberta (the
  savepoint town), prontera, geffen, geffen_in, morocc, morocc_in, izlude, izlu2dun, and payon (the
  least-zeny Byalan route only). Walking between the towns (fields only) is not used: it is 18 to 30
  map changes per round trip and crosses field maps outside this scope.
- **The interiors are rooms.** A map-level route was wrong in every interior (alberta_in, geffen_in,
  morocc_in: the door a map-level search picked does not reach the NPC's room). The routes above
  are checked cell by cell on the server's walkability grid, including the arrival from
  graduation: (62,44) reaches the job changer directly and the storehouse through (64,31).
- **Transport NPCs** are literal script warps whose script tests no variable (boats, a warper);
  quest NPCs that warp under a condition are never used. A fee is the script's own `Zeny < N` before
  the warp; a script that charges otherwise is counted as unknown and never relied on.

### 7.4a The delivery-dialog classifier: DESIGN FACTS (2026-10-09 ~21:30, offline) and AS BUILT (2026-10-10, offline; NOT verified live)
Batt ~19:30: "build it as a CLASSIFIER over the KNOWN set from L3 (4 destinations x 2 serials = 8
variants), like the T3 menu reader; never free OCR. Verify on the live dialog before relying on it."
Read from the pinned merchant.txt (local; no script text or serial is committed here):
- **Where the 8 variants show:**
  1. the ASSIGNMENT (the application, merchant.txt ~383-410): one page names the destination in
     plain black text (a destination word per option: the Prontera / Geffen / Morocc / Byalan
     line), then `S_GiveSerial` (merchant.txt:480) shows a page of four short lines whose last is
     the 7-digit serial;
  2. the REMINDER: every later talk to the job changer while the test runs (merchant.txt:183-247,
     `job_merchant_q2` 1-8) restates the destination and the serial on ONE page. So the variant can
     be re-read at any time before the storehouse, and a live capture does not need a new
     application per variant.
     ➡️ CORRECTED 2026-10-10 (AS BUILT below, from the L3 extract): not one page. The reminder is
     6-7 pages; the destination and the serial are on 2-3 of them, and the serial page's own
     wording is unique to its destination, so it classifies with no context. The conclusion (re-read
     at any time, no new application per variant) stands.
- **The serial is COLOURED** (`^3355FF`, then `^000000`). T3's reader refuses any coloured row
  (`coloured_text`, by design for menus). The classifier needs a colour-ink path for that one line:
  ink = distance to the script's blue, then the SAME glyph matching, against only the 2 serials of
  the destination read on the plain line (a closed set of 2, never free digits).
- **A second pixel source:** `setquest` 1009-1012, one quest id per destination, so the quest window
  (Alt+U, an L2 shortcut) shows the destination too. A disagreement between the dialog and the quest
  window is a STOP (hand over), never a guess.
- **Glyphs:** the dialog's font is expected to be the menu's (T3 glyphs, `menu_glyphs.npz`); the
  dialog window's background is the npc_dialog white. Both are checked on live frames before use;
  any character of the 8 variants missing from the glyph set (digits, capitals) is cut from a
  labelled live frame (talk_calibrate), as T3's were.
  ➡️ CHECKED 2026-10-10 on BANKED dialog frames (AS BUILT below): the same font (32 shared
  characters, identical bitmaps); the background is (247,247,247), the menu's plain row colour, not
  white. But the dialog's word GAPS differ from the menu's, so the glyph set is cut from DIALOG
  lines (`dialog_variants.py cut`), not T3's file as it stands.
- **Batt's c (2 easiest first):** only the prontera and morocc_in variants (4 of 8) are acted on;
  the geffen_in and izlu2dun variants are classified too (so the hand-over says which), then STOP
  before the storehouse's serial input and before any fare.
- **The live verification needs a dialog on screen.** Two ways, both for Batt:
  (a) the agent account's own application, in the workflow (the real fee, once);
  (b) the GM applying first (needs Job Lv 10 + Basic Skill 9, which learn_skill@1 builds, and 500 or
  1,000 zeny, which the GM lacks: no zeny command in group 20; and it writes the GM's job_merchant_q
  variables, which persist). Not started.

**AS BUILT (2026-10-10 ~00:30-01:30 ICT, offline, branch `feat/dialog-variant`; nothing live, nothing
pre-registered).** No script text, serial number or client pixel is committed; the numbers below are
counts.

What exists:
- `packages/poring_env/src/poring_env/dialog_variant.py` (mypy strict):
  - `read_page`: the dialog's text area (T2's geometry) cut into 16-row bands on its 21-px line
    pitch, T3's glyph matching per band on a MULTI-INK map (black + every ^RRGGBB code the
    candidate pages use);
  - `classify`: the closed set (rules below); `classify_frame` = both;
  - `Conversation`: folds the pages of one talk (a destination page gives the context the
    assignment's serial page needs; pages that disagree = `conflict_*`);
  - `decide`: prontera / morocc_in variants -> `act`, geffen_in / izlu2dun -> `hand_over`, None ->
    `stop` (Batt's c).
  - Results: `ok` (a variant), `destination_only`, `no_variant_info` (a page every variant shows).
    Fail-closed reasons: `glyph_missing:<chars>` (checked before reading), `lineK:<unknown_glyph |
    ambiguous_glyph | unexplained_gap | mixed_colour | coloured_text | foreign_pixels |
    leading_blank>`, `overflow` (a 7th line), `beyond_wrap` (ink right of the wrap width: the
    scrollbar), `no_page_matches`, `destination_conflict`, `destination_unknown`,
    `serial_not_candidate`, `wrap_inconsistent`, `ambiguous_variant`.
- `scripts/dialog_variants.py`: `extract` (L3, local: `data/kb/merchant_delivery.json`, gitignored),
  `coverage`, `measure-wrap`, `cut` + `selfcheck` (a dialog glyph set from banked labelled frames,
  and its held-out check), `prove` (the live bar, fixed in its docstring; runs once merchant frames
  are banked).
- Tests: `packages/poring_env/tests/test_dialog_variant.py` (16: synthetic font, invented pages),
  `services/backend/tests/test_dialog_variants.py` (4: a synthetic script).

The extract: a small interpreter runs the job changer for every random path of the application and
for every variant's reminder (a statement it does not know stops it). Result: 8 variants (4
destinations x 2 serial slots; slot = the order of the variant value), quests 1009-1012 one per
destination, 48 distinct pages (16 show one variant, i.e. its serial; 15 one destination; 17 every
variant), 0 problems.

Design choices:
- **Wrapping, MEASURED** (`measure-wrap` on the 7 banked talk@1 calibration sessions: 28 pages, 126
  lines, 59 wraps, PASS). The client word-wraps by PIXEL width, not by character count (a
  41-character line fitted where a 35-character one wrapped). Every line that fit ended its ink at
  text-area column <= 213; every wrap was where the next word would have ended at >= 214. The
  classifier maps physical lines onto mes lines only when they join (one space) into the mes line
  AND every wrap is where that rule puts it (+-1 px). So not "any wrap": a wrap the client would not
  make is `wrap_inconsistent`.
- **Colour ink.** Each pixel is a background-to-ink blend of the ink that leaves the least residual
  (black or a page's colour code, drawn as the client's 15-bit colour: ^6666CC drew exactly
  (99,99,206) on the banked frames); a pixel no ink explains is foreign. Each glyph takes the colour
  of >= 90 % of its ink. Coloured glyphs are WILDCARDS in the plain match, compared only after the
  plain text (and the conversation) fixed ONE destination, against that destination's <= 2 serials.
- **Margins.** Per glyph: T3's (`max_score`, `min_margin`). Per line: the smallest glyph margin
  (returned). Per variant: the distance, at the read glyph boxes, from the read to every other
  eligible page (the score differences where characters differ; infinite when the glyph count, a
  colour or a width differs); below `min_margin` -> `ambiguous_variant`.
- **Where the variant is read.** The reminder's serial page classifies with no context (its wording
  is unique to its destination). The assignment's serial page is the same text for all 4
  destinations and needs the destination page before it. The workflow reads every page of the talk,
  folds them, and acts only on a folded variant; a refused page is no decision (re-read the
  reminder).

Glyph coverage (characters as counts per class only):

| glyph set | chars | missing, all 48 pages (of 67 needed) | missing, the 31 variant / destination pages (of 60) |
|---|---|---|---|
| T3 as cut (`menu_glyphs.npz`) | 33 | 34: 10 digit, 10 upper, 7 lower, 7 punct | 27: 10 digit, 7 upper, 4 lower, 6 punct |
| dialog cut, the 3 T3-cut sessions (local experiment, `/dev/shm`) | 54 | 15: 7 digit, 6 upper, 1 lower, 1 punct | 11: 7 digit, 4 upper |
| both sets' characters | 55 | 14: 7 digit, 5 upper, 1 lower, 1 punct | 10: 7 digit, 3 upper |

- Of the 27 characters T3 lacks on the variant pages, 18 occur in banked packet-labelled dialogs (14
  sessions: talk@1 calibration + npc-click). 9 (7 digits, 2 capitals) occur in NO banked dialog:
  only a merchant dialog on screen gives them.
- The serial's digits are drawn ONLY in blue: `cut` redraws a band of the page's inks in black
  before T3's fit (`as_black`; the font is crisp, so the shapes are unchanged).

Offline evidence on real pixels (banked dialogs of OTHER NPCs; NOT the merchant proof):
- The dialog font IS the menu font: 32 characters in both sets, same widths, identical bitmaps.
- The GAPS differ: in the dialog, in-word gaps are 1-3 columns (an ellipsis: 3) and spaces 4-6 (the
  menus showed 1-2 and 5 only). T3's set as cut refuses most dialog lines (`unexplained_gap`). The
  classifier's glyph set must be cut from DIALOG lines, including the merchant's own (its
  assignment serial page holds an ellipsis). `cut` splits a band's words at >= 4 blank columns.
- `selfcheck`, each banked page its own closed-set member:
  - cut on the 3 T3-cut sessions (54 characters), judged on the 4 T3-prove sessions: 58 frames
    right (24 on pages with coloured text), 0 wrong, 10 refused (`beyond_wrap`: the guide's page
    with a scrollbar);
  - the reverse split (44 characters): 60 right (24 coloured), 0 wrong, 54 refused (6
    `beyond_wrap`, 48 `unknown_glyph`: characters that cut never saw). PASS both ways.
- Page length, estimated from glyph widths: every variant / destination page fits the 6 visible
  lines (the geffen_in assignment's destination page is borderline at 6). One generic page needs 7:
  the client shows a scrollbar and the reader refuses it, harmless under the fold.

What must be measured LIVE before relying on it (Batt's (a) or (b) above):
1. The cut: the 9 characters no banked dialog shows, and the merchant's own lines (ellipsis gaps, the
   blue serial): `dialog_variants.py cut` on the banked merchant session(s).
2. The serial's blue: ^3355FF is predicted to draw as (49,82,255); the ink tolerance (32) is checked
   on the first frame.
3. The wrap column (213) and the page lengths, on the merchant's own pages.
4. `dialog_variants.py prove` on sessions NOT used by the cut, to the bar in its docstring: 0 wrong;
   every banked serial page read as its variant and every destination page as its destination;
   unknowns counted; only the variants actually banked are proven.
5. The quest window (the second source) is NOT built.

### 7.5 The budget (e) (training-cost.md's method, `kb_first_workflow.py budget`)

`poring_flow.prep.estimate` on training_cost.json, NEW species and NEW maps only, blocks in Batt's
order; trained = labels_v2.TRAINED (1002, 1063, 1008, 1113, 1018); difficulty =
labels_v2.difficulty (all "normal" here).

| block | maps (new) | new species (Σd) | map prep h (a clone group once) | collect S2 h | train compute h | wall h: night / mix | NPC sprites first met | drawn portal cells |
|---|---|---|---|---|---|---|---|---|
| training grounds | 16 (4 layouts) | 10 (10.0): 1009, 1010, 1011, 1012, 1014, 1050, 1051, 1052, 1053, 1184. Trained: 1002, 1063, 1113 | 83.2 (20.8) | 13.0 | 23.73 | 37.7 / 47.0 | 15 | 30 |
| Merchant guild | alberta_in, alberta (2) | 1 (1.0): 1261 | 10.4 | 1.3 | 2.37 | 3.8 / 4.7 | 45 | 36 |
| delivery: morocc_in | morocc, morocc_in (2) | 0 | 10.4 | 0 | 0 | 0 | 23 | 50 |
| delivery: geffen_in | prontera, geffen, geffen_in (3) | 0 | 15.6 | 0 | 0 | 0 | 26 | 56 |
| delivery: prontera | (prontera above) | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| delivery: izlu2dun | izlude, izlu2dun, payon (3) | 0 | 15.6 | 0 | 0 | 0 | 11 | 25 |
| **total** | **26** | **11 (11.0)** | **135.2 (72.8)** | **14.3** | **26.1** | **41.4 / 51.7** | **120** | **197** |

- **Map prep dominates** because the formula counts every NEW map: the training grounds' 16 maps
  are 4 layouts, 5 copies each. If a clone group counts once (Batt), the training grounds cost
  20.8 h, not 83.2 h.
- **"Similar" (half budget) candidates:** within this scope only 1053 / 1051 (a variant pair, both
  on new_4-3 / new_5-3). Batt, with the sprite catalog.
- **Not in the estimate** (as in 3.2): the NPC sprites (750 frames each on the union of frames:
  15 for the training grounds, 105 more on the towns if whole towns are in scope), `warp` (one class,
  750 frames from >= 4 maps' backgrounds: the training grounds give 2 layouts with portals, so the
  class needs town portals too), the hard negatives.
- **1261 needs spawn blocks:** one per town, respawning every 2-3 h; natural frames will not reach
  1,500.

### 7.6 The collection plan (f) (waits for G1 option A and G2 quiet windows; nothing collected)

- **Gates:** G1-G3 as in 3.3. **G4 for these maps:** this KB (built); the GATs of the 4 training
  layouts and the path towns extracted into `/dev/shm` (alberta, alberta_in, prontera are already);
  the camera: the client's indoor table lists alberta_in, geffen_in and morocc_in, not the training
  maps (outdoor camera); the sprite catalog for the 11 new species; N1-N3 for the 15 training-ground
  sprites first.
  - ➡️ **GATs + camera: DONE 2026-10-09 ~20:45.**
    - `scripts/map_identity.py gat` wrote each server map name's GAT into the GAT dir
      (`/dev/shm/poring-lab-tmp/gat/data`), resolved through the client's rename table: all 20
      new_N-M (each its stage's new_zone0M), plus morocc and morocc_in. alberta, alberta_in and
      prontera were already there, byte-unchanged.
    - `scripts/flows_gat.py` then copied them to `data/gat` (the MW2 mount; gitignored).
    - **Indoor table:** no training map is listed, under the server name or the opened new_zone0M
      name, so the outdoor camera applies. alberta_in and morocc_in are listed (indoor).
  - **Found on the way (needs a decision before the Merchant maps' labels):** on this host's GRF,
    two route towns' client GATs do NOT match the server's walkability.
    - `map_identity.py check --group <town>` counts the cells: alberta 5,091 differ (4,836 walkable
      only in the client, 255 only on the server); morocc 6,999 (4,482 / 2,517); prontera 46 (the
      known 46, thai-data-experiment.md 1).
    - alberta_in and morocc_in: 0 differ. The 20 training maps: 0 differ (7.1).
    - The projection reads the CLIENT GAT's altitude (camera.py), so labels on alberta and morocc
      may not fit the map the lab client draws. The kRO data on the Dell decides it, and it is not
      on this host (7.1's caveat). Until then, treat alberta and morocc GATs as unverified.
  - ➡️ **N1 (the NPC id -> sprite file table): BUILT 2026-10-09 ~20:50, along the route only**
    (Batt 7.7 item 7). `scripts/npc_sprites.py build` writes `data/kb/npc_sprites.json` (local,
    never committed). Its Lua table reader is `scripts/lua51_tables.py`. Tests:
    `services/backend/tests/test_npc_sprites.py`.
    - **Scope rule:**
      - the training grounds: every drawn NPC;
      - the Merchant route, for Batt's two first destinations (prontera, morocc_in): the
        graduation arrival, the job changer, the storehouse, the KB's `walk_kafra` legs out and
        back (a Kafra leg walks to the nearest Kafra of the same service);
      - shortest paths on the server grid between those stops;
      - an NPC counts when it is within 14 cells (Chebyshev) of a path cell. That is the server's
        `area_size`: nothing farther is ever sent to the client.
    - **Counts:**
      - training grounds: the 15 sprites of 7.3;
      - the Merchant route: 29 sprites (alberta 12, alberta_in 5, morocc 7, morocc_in 5,
        prontera 8), 6 of them shared with the training grounds;
      - **38 distinct sprites** in total, against 120 for whole towns (7.5).
    - **Three sources agree on all 38:**
      - rAthena's constant (npc.hpp);
      - the client's own tables (npcidentity.lub constant -> id, jobname.lub id -> sprite name;
        compiled Lua, read without running it);
      - the archive: SPR + ACT present under data\sprite\npc\ for every one.
    - The sprite name is the constant's name in all 38 cases. None is a composite player-class
      sprite, and none is a monster sprite. Most SPRs are MIXCRYPT (the study decoder, as for the
      monsters).
  - ➡️ **N2 (the NPC SPR/ACT): DONE 2026-10-09 ~20:55 for the same 38 sprites.**
    - The command: `scripts/sprite_catalog.py --npc-from data/kb/npc_sprites.json
      --decode-mixcrypt`, with a new NPC mode (`--npc` / `--npc-from`) and a test.
    - It reads data\sprite\npc\ the way the monsters are read and writes the same record format.
      Outputs, all local: `data/kb/npc_sprite_catalog.json`, `data/kb/npc_sprite_names.json`
      (job -> stem, for `labels_v2.py --npc-sprite-names`), and the decoded files in
      `/dev/shm/poring-lab-tmp/sprites/data/sprite/npc/` (for `--npc-sprites`).
    - **38 / 38 decoded:** 30 MIXCRYPT SPRs (study decoder) and 8 plain.
    - **Integrity:** 11,104 ACT 2.5 layer sizes equal their SPR image sizes, 0 mismatches.
    - **Boxes:** `predict_sprite` boxes all 38 through labels_v2's own loader (`npc_sheets`),
      every box OPAQUE. Native idle sizes: 32-59 sprite px wide, 73-108 tall.
  - ➡️ **The sprite catalog for the 11 new species: DONE 2026-10-09 ~21:00.**
    - The species: 1009, 1010, 1011, 1012, 1014, 1050, 1051, 1052, 1053, 1184, 1261.
    - **The client's own name decides the file.** `scripts/npc_sprites.py mob-names` reads
      jobname.lub and writes `data/kb/monster_sprite_names.json` (local).
      - For **4 of the 11** (1011, 1051, 1053, 1184) the client draws a sprite whose name is NOT
        rAthena's aegis name.
      - The trained 1002, 1063 and 1113 match.
      - **Follow-up, not done here:** `qa_export.Sheets` (v1's loader, reused by labels_v2) looks
        a monster's files up by the aegis name (classes.json). It would find no sheet for those 4
        and fall back to v0's 44 x 40 box. It should read the stem from that table.
        ➡️ **DONE 2026-10-09 ~22:00 (branch feat/collect-v2, 1ddcf75):** `Sheets` takes the
        client's stem from `monster_sprite_names.json` when it lists the species, else the aegis
        name. A species with neither gets no sheet and is reported (`labels_v2.py coverage`:
        `sprite_lookup_missing`). It was worse than 4: classes.json lists only the prt_fild08 /
        iz_dun00-01 species, so ALL 11 new species had fallen back. On the local KB all 16 of
        the scope now resolve, 0 missing.
    - **The catalog:** `scripts/sprite_catalog.py --decode-mixcrypt` on the 12 old + 11 new names
      (the client's stems).
      - 23 / 23 species have ACT + SPR decoded, all boxes OPAQUE.
      - The 12 old records reproduce the stored catalog exactly (0 differ).
      - `data/kb/sprite_catalog.json` now holds 23 species. The decoded files are in
        `/dev/shm/poring-lab-tmp/sprites/data/sprite/` (local).
    - **For Batt's "similar" call (7.5):** 1051 and 1053 use the SAME SPR (byte-identical images)
      with different ACTs. 1053 is drawn larger: idle 50 x 36 against 35 x 25 native px.
  - ➡️ **N3 preparation: READY FOR A PERSON 2026-10-09 ~21:10. Not judged.**
    - The command: `scripts/labels_v2.py npc-sheet <the banked demo sessions> --npc-sprites ...
      --npc-sprite-names data/kb/npc_sprite_names.json` (new subcommand, tests in
      `test_labels_v2_tool.py`).
    - It takes the labels' own path (`Session.frame`, so the boxes a v2 cache would train on).
      Per NPC sprite it writes a contact sheet: up to 8 crops spread over the sightings, the
      `predict_sprite` box in green, M5's NCC printed on each crop.
    - It also gives `label_check`'s NCC for every sighting: the M5 metric, with M4's tau 0.092 as
      a reference line only.
    - Output: `/dev/shm/poring-lab-tmp/labels-prep/n3/` (PNG + JSON; client pixels, never
      committed). It read the 78 banked demo sessions that have packets and skipped the 9 that
      have none.
    - **9 of the 38 route sprites appear in banked frames, 382 sightings in all:**

      | job | maps | sightings (sessions) | NCC median (p10) | below 0.092 (UI-covered) |
      |---|---|---|---|---|
      | 59 | alberta_in | 6 (2) | 0.059 (0.005) | 4 (1) |
      | 84 | prt_in | 3 (1) | 0.473 | 0 |
      | 85 | prt_in | 3 (1) | 0.349 | 0 |
      | 86 | alberta_in, prt_in | 6 (2) | 0.136 (0.119) | 0 |
      | 89 | alberta | 4 (1) | 0.414 | 0 |
      | 92 | prontera | 176 (5) | 0.451 (0.272) | 0 |
      | 98 | alberta_in | 7 (2) | 0.182 (0.041) | 1 |
      | 105 | prontera | 176 (5) | 0.313 (0.212) | 1 |
      | 874 | prontera | 1 (1) | 0.520 | 0 |

    - **What needs a person:** the 9 sheets. Job 59 on alberta_in (indoor camera) scores low, and
      on its sheet the box sits right of the drawn sprite in several crops. A person decides
      whether that is a label error (the indoor camera, the heading) or the NCC.
    - The other 29 sprites have no banked sighting.
      - The training-ground maps themselves were never banked. Still, 5 of their 15 sprites (84,
        85, 86, 92, 105) were seen on other maps: the same files, so the same check.
      - The other 10 (46, 47, 57, 90, 117, 726, 727, 751, 753, 754) wait for the first collection
        session.
    - ➡️ **Claude's reading of the 9 sheets (2026-10-09 ~21:30; for Batt to confirm, as with the warp
      sheet):**
      - **Fit (the box holds the drawn sprite, edges within a few px):** 84 (prt_in), 89 (alberta),
        92 (prontera, all 8), 874 (prontera, 1 crop), 105 (prontera; the guide's halberd tip sticks
        out on the left in 2 crops, the body fits).
      - **Shifted RIGHT on alberta_in, in most crops:** 59 (4 of 6), 86 (3 of its 4 alberta_in
        crops; its prt_in crop fits), 98 (2-3 of 7): the box's left edge sits near the sprite's
        middle, i.e. about a third of a sprite width (~15-25 px) to the right. 85 (prt_in) is
        shifted ~10 px the same way. The outdoor and town sprites do not shift.
      - **So the shift is a label (projection) error on the indoor camera, not the sprite or the
        NCC:** the same sprite (86) fits on prt_in in one crop and not on alberta_in. Two crops (86
        #5, 98 #6) also show a closer camera (a zoomed view), where the box still roughly fits.
      - **Consequence:** indoor NPC boxes (alberta_in at least) are NOT trainable until the indoor
        projection offset is explained (the indoor camera's yaw / distance per map, or the GM's
        packet position lag); the training grounds are outdoor-camera maps and are not affected.
        alberta_in is the job changer's map, so this blocks the Merchant maps' NPC labels, not the
        training grounds'.
  - ➡️ **L3 warp lists on these maps (walk@17's B; labels_v2's `warp` class): DONE 2026-10-09
    ~21:15.**
    - `scripts/kb_route.py` now takes first_workflow.json's COMPLETE list for every map that KB
      covers: the `warp` lines of every loaded file, plus the touch-triggered script NPCs that
      warp (cell ± trigger span).
    - A map without portals gets an empty list, which reads as "none"; a map with no entry reads
      as "unknown", and walk@17 refuses it.
    - `REQUIRED_WARP_MAPS` (the 20 copies and the 10 route maps) fails the run closed when one is
      missing. Test: `test_kb_route.py`.
    - route.json was regenerated LOCALLY: 83 -> 107 maps, every other key unchanged.
    - **Warp areas per map:**
      - new_N-1: 1 each;
      - new_N-2: 5 each;
      - new_N-3 and new_N-4: 0 (listed empty);
      - alberta 11, alberta_in 25, prontera 20, morocc 14 (13 + 1 touch NPC), morocc_in 36,
        geffen 13 (11 + 2 touch NPCs), geffen_in 25, izlude 8, izlu2dun 1, payon 16.
    - **Against the old hand list:** nothing was dropped. Added: prt_church +2 (the quest-file
      `warp` lines (115,122) and (166,106); the first is 1.3's portal_unconfirmed case), izlude +1,
      payon +1. alberta, alberta_in, prontera, iz_dun00, izlu2dun and prt_fild08 are the same sets.
- **Accounts:** the GM (2000002) collects, with 3.33's immunity after each login, the fixed GM
  state checked and the UI gate before each run. It reaches any copy by `@warp` (the copies are
  clones). **The agent account 2000001 is not used for collection:** its quest state on new_4-1 is
  the workflow's starting state, and its tutorial variables are unknown offline (open question 5).
- **Sessions, in Batt's order:**
  1. **new_1-3** natural spawns (walk@17's legs): 1011 and 1184 new, 1002 / 1113 / 1063 trained.
  2. **new_2-3** (new_3-3 is the same set): 1009, 1010, 1012, 1050, 1184.
  3. **new_4-3**: 1014, 1051, 1052, 1053, 1184 (new_5-3 has the same species, sparser: keep it
     and new_3-3 for test sessions, T2).
  4. Spawn blocks (`@monster <id> 8`, ~25 min each, `@killmonster2` between) for species short of
     1,500 frames after 1-3.
  5. **NPC and portal passes:** new_1-2 (11 NPCs, the shop, 5 portals), a yard and a reception
     copy, new_1-4: standing views per sprite toward 750 frames, and the portal cells for the
     visibility table. No dialog is needed for the cut-in (none there).
  6. **Then the Merchant maps** (Batt's step 3): alberta_in / alberta, then the delivery maps; 1261
     by spawn blocks.
- **The target / ignore test** (7.2's proposal) runs later, on the trained detector, with the
  player account: an ignored 1184 beside the targets, zero acts on it (the server's act packets,
  offline), as MW3 specifies.
- **Frames to bank:** per new species 1,500 training frames with >= 3,000 instances (+ 0.40 for
  validation and test); per NPC sprite 750; `warp` 750 in total.

### 7.6a Collection WITHOUT walking until walk@17 is ready (Claude, 2026-10-09 ~21:15; for Batt's review, flagged in the weekend report)
**Why:** 3.3's sessions take natural spawns along walk@17's long walks, but walk@17 has not run its
tuning yet (gated by item 5's NPC-click test and the static no-click layer, demonstrations.md 3.32).
Waiting for walk@17's readiness would push every collection session past the weekend.
**The variant (collect@1, to build; nothing collected yet):** the same gates and the same session
protocol, with every MOVE made by `@warp` instead of a walk:
- per map, K seeded spots: walkable cells outside every L3 warp area (route.json, fail closed) and
  >= 8 cells from every L3 NPC, spaced >= 12 cells apart; the GM `@warp`s to each and DWELLS T s
  while the session records (natural spawns wander through the view);
- spawn blocks as 3.3 (`@monster <id> 8` beside the spot, `@killmonster2` between);
- portal passes as 3.3 (`@warp` beside each L3 warp cell);
- the GM is immune (3.33, `@monsterignore` after each login), at the fixed state, and the UI gate +
  typing guard pass every typed line. **The GM makes NO world click at all** (no walk, no attack, no
  talk): the session's safety signal must stay empty (`attack_request`, `npc_contact`,
  `pickup_request`, any GM act), judged offline per session.
**What it loses:** frames of the camera scrolling with a walking GM (each dwell is a static camera);
the walk legs are added once walk@17 is ready. The labels skip each GM line's 2 s window as before.

➡️ **AS BUILT 2026-10-09 ~22:00 (Claude, branch feat/collect-v2; offline only, NOTHING run live,
nothing collected; not a pre-registration).** Code: `scripts/collect_v2.py` (its docstring holds the
full protocol and the findings), `scripts/runbooks/collect-v2.sh`; tests
`services/backend/tests/test_collect_v2.py` (synthetic grids, KB snippets and events).
- **Commands:**

      .venv/bin/python scripts/collect_v2.py plan --map new_1-3 --seed S      # offline, read it
      .venv/bin/python scripts/collect_v2.py immune-on                         # once per GM login
      .venv/bin/python scripts/collect_v2.py immune-confirm --shot <its PNG>   # after reading it
      .venv/bin/python scripts/collect_v2.py preflight --map new_1-3 --seed S  # no input
      scripts/runbooks/collect-v2.sh new_1-3 S /dev/shm/poring-lab-tmp/collect/<run> [options]
      .venv/bin/python scripts/collect_v2.py judge <session>                   # the runbook runs it

  Options: `--spots K` (6), `--dwell-s` (120), `--blocks ID ...` (default: the map's own species),
  `--block-s` (300), `--block-repeats R` (1), `--count` (8), `--portal-dwell-s` (60),
  `--no-portals`, `--max-minutes` (55; one S2 recording is capped at 3600 s).
- **The plan, as built:** spots = walkable cells (the client GAT AND the server's map cache when it
  is on the host; @warp tests the server's CELL_CHKNOPASS), outside every warp area, Chebyshev >= 8
  from EVERY L3 NPC (npc_cells.json, drawn or not, plus route.json's groups; a map not declared
  complete fails closed), >= 12 apart, and an open view (>= 50 % walkable in +-7). Portal-pass
  cells: Chebyshev 3-5 from each warp AREA, outside every area, >= 3 from any NPC. Blocks: the map's
  own species in KB order, one spot each in rotation (a spot needs room for 2 x count monsters).
  The GM lines are simulated against the typing guard's repeat rule; a warp to the cell the GM
  stands on is never typed.
- **The plan for new_1-3, seed 20261010 (counts only):** 6 / 6 spots from 7,492 candidates, nearest
  NPC 15-32 cells, open view 0.72-1.0; 0 portal passes (new_N-3 has no warp); 5 blocks (1002, 1113,
  1063, 1011, 1184; 8 each, spawn box +-4); 21 GM lines, longest identical run 1, 0 guard
  violations; @warp check OK; ~38.9 min at the defaults. new_2-3 and new_4-3: the same counts
  (one layout). new_1-2: 6 spots, 5 / 5 portal cells, no blocks; new_1-1: 6 spots, 1 / 1 portal.
- **The session order:** natural dwells first, spawn blocks after, portal passes last.
  `@killmonster2` only ends a block, never starts a session (finding below); a crashed run's block
  is removed at the next start by `@killmonster2 <map>`. A heal or revive need after the start
  means the immunity condition failed: the run recovers and STOPS (rc 3).
- **@warp finding (pinned e985006):** `ACMD_FUNC(mapmove)` refuses only on the destination's
  `nowarpto` or the source's `nowarp` for a group without `any_warp` (atcommand.cpp:632, 636), or
  when `pc_job_can_entermap` says no (pc.cpp:15471: db/pre-re/job_noenter_map.txt is empty, so
  zone 0 -> allowed). The training maps carry nobranch / nomemo / nopenalty / noteleport only;
  noteleport is checked by @jump (atcommand.cpp:739) and random warps (pc.cpp:7216), nomemo by
  @memo (pc.cpp:7242), never by @warp. **So group 20 can @warp into and within new_N-M.** A
  non-walkable target becomes a random free cell within 10 (atcommand.cpp:626-631): the judge
  checks where each warp landed (map_change).
- **@killmonster2 finding:** it kills EVERY monster of the map, the natural spawns too (only WoE
  guardians are spared; atcommand.cpp:2422-2464). A natural one respawns after max(1 s, its delay)
  (mob.cpp:1092); the training maps give no delay, so they return ~1 s later at random cells. A
  @monster one is freed (mob.cpp:1068-1069, 3640-3645).
- **@monster placement:** each of the N lands within int(sqrt(N)) + 2 cells of the GM
  (atcommand.cpp:2393): +-4 for 8. Spawned monsters wander off: the 3.33 check's 3 Familiars all
  left the GM's view within ~200 s, so several shorter blocks (`--block-repeats`) keep more of
  them on screen than one long block.
- **Immunity:** `@monsterignore` is a TOGGLE (atcommand.cpp:9025-9038), and 3.33 read its answer
  from a screenshot (no pixel reader exists). So the driver never types it. `immune-on` types it
  once per GM LOGIN and saves the client's answer. The login is identified by a marker from the DB:
  `char.last_login` (set at every character select, char.cpp:121-123) + `login.logincount`, read as
  `ro_agent.gm` already reads `online_chars`. A person (or the parent) reads the answer and runs
  `immune-confirm`. `run` / `preflight` refuse unless it is confirmed for the CURRENT login: any
  re-login means OFF, so refused. The judge then checks per session: zero acts targeting the GM.
- **The judge** (`collect_v2.py judge SESSION`, offline):
  - safety: no attack / NPC-contact / pickup / self-move request from any client, and no GM act of
    kind normal or pickup;
  - immunity: no act targets the GM, with the monster moves counted;
  - the sensor's POSITIVE case: the GM's own typed lines seen client -> server;
  - where each warp landed, and each block's monsters.

  It was run on REAL banked sessions (local), and each signal fired:
  - the 3.33 immune check: 0 acts on the GM, 134 monster moves, its deliberate click = 2 attack
    requests, 8 / 8 lines seen, the warp landed as typed, 3 / 3 Familiars counted;
  - monster-click (GM not immune): 5 acts on the GM, so the immunity check fails;
  - pickup: pickup requests and acts; npc-garnet: npc_contact.
- **What the parent must verify LIVE before the first session** (none of it was possible offline):
  1. **The UI gate refuses every typed line on S2 today.** `ui_gate._require_ready`: its T2
     templates are RDP-cut, and it refuses while the lock says console. As built, `preflight`
     stops there, before the recorder.
     - Unblock it with S2 templates for the gate (a live cut + a reviewed change), or collect over
       RDP, which needs a decision: 3.3 names S2.
     - ➡️ **2026-10-09: the reviewed change is BUILT (branch `feat/s2-gate-templates`), the live cut
       is NOT done.** The gate is path-aware (`poring_env.ui_sets`): on console it reads
       `data/ui_anchors/s2/` only while its `proof.json` says windows + T2 are proven on S2. Until
       the session in `docs/operations/s2-gate-templates.md` passes, preflight still stops here
       (now with "the s2 template set is not proven").
  2. **The GM-state template is RDP-cut too** (gm_state.py, measured on RDP frames). Check on the
     stream that `gm_state.py check` reads Lv 1 / 1 (and `gm_vitals` the HP bar) before relying on
     it.
     - ➡️ **2026-10-09: gm_state is path-aware too** (same rule: the S2 `gm_levels` + `gm_notices`
       must be proven; it refuses on S2 until then). Preflight's `gm_state_template` check is now
       `gm_state.require_ready()`. `gm_vitals` is NOT covered by this change.
  3. **immune-on -> read the shot -> immune-confirm,** after every GM login. guarded_build's
     automatic GM re-login also counts.
  4. **The S2 foreground template** (installed 2026-10-07; re-cut if the client window moved), and
     `--check-client` on the stream.
  5. **A pilot first:** a short `--max-minutes`, `--spots 2`, `--blocks <one id>`. Then judge it:
     safety and immunity pass, the sensor sees every line, warps land as planned, the block
     appears.
  6. **One lab client logged in** (the GM). Requests from any other client fail the judge too.

### 7.7 Open questions for Batt

➡️ **DECIDED 2026-10-09 ~19:30 (Batt).** The questions below are kept as history; this is the answer
to each.
1. **Dialog reader:** "build it as a CLASSIFIER over the KNOWN set from L3 (4 destinations x 2
   serials = 8 variants), like the T3 menu reader; never free OCR. Verify on the live dialog before
   relying on it."
   ➡️ BUILT OFFLINE 2026-10-10 (branch `feat/dialog-variant`, 7.4a AS BUILT): NOT verified live;
   the live cut + `prove` wait for a merchant dialog on screen (7.4a (a) or (b)).
2. **IGNORE list:** 1184 IGNORE (no job EXP, aggressive); 1014 AVOID for a novice.
3. **Deliveries:** "support the 2 easiest destinations first; on any other, stop safely and hand
   over to a person (before paying anything irreversible). Extend later."
   - By the 7.4 table, the two easiest are prontera (2 Kafra hops) and morocc_in (2 hops + internal
     portals).
   - Check before building: the fee may be paid BEFORE the random assignment is known. Then "before
     anything irreversible" means before the serial is typed and before any fare.
4. **Map prep per LAYOUT (4),** "after verifying the copies are visually identical too
   (RSW/GND/textures), not only the GAT."
5. **2000001:** a read-only check, for planning only (never a rule input). Done 19:40 ICT; see the
   facts below.
6. **Typing:** the character name and the serial go through the typing guard and the UI /
   foreground gates.
7. **NPC sprites only along the route.**
8. (the follow-up stays open.) ➡️ DONE 2026-10-09 ~21:15 (e6f3b1d, merged 748260d): route.json's warp lists now come from this KB's COMPLETE per-map list (kb_route.py; prt_church gains (115,122) and (166,106)), so labels_v2 and npc_noclick read the completed lists.

**Also decided (same message):**
- A NEW L1 concept for the job change: allocating skill points (Basic Skill > 8) through the skill
  window, with its own alone-test (to be designed and pre-registered).
- Labels v2: label OUR GM as "player"; verify the phantom's REGION (not the whole extent); the
  DRAFT bar (section 5) is OK.
- **2000001, read-only (19:40):** one character (char_id 150001), a Novice at Base / Job Lv 1, all
  six stats 1, **48 unspent status points**, 0 skill points, 0 zeny.
  - Inventory: the starter Knife (1201) and Cotton Shirt (2301).
  - last / save map new_4-1 (61,114), next to the start point.
  - No quests, no character or account variables.
  - So the workflow starts at the reception, and it also needs status-point allocation
    (`char.allocate_stat`).


1. **The delivery is told only in dialog text.** The destination and the serial number come from
   the job changer's dialog (merchant.txt:383-415); the storehouse wants the destination picked and
   the serial TYPED. A wrong guess fails the test and costs the fee. So the first workflow must
   read dialog text from pixels (no reader exists), or Batt picks another way.
2. **The IGNORE list:** the scripts give no species reason; 7.2's data candidates (1184, 1014,
   1051 / 1053, 1009; 1261 in towns) are yours to choose.
3. **The four delivery options:** the script picks one at random, so a workflow that cannot choose
   must cover all four (10 maps). Keep all four, or narrow the scope (each retry costs the fee)?
4. **Map prep for clone copies:** 16 maps or 4 layouts (83.2 h vs 20.8 h)?
5. **2000001's state:** which tutorial / quest variables it has (it decides each NPC's branch). A
   read-only look at its character variables, or its own dialogs, before the workflow is designed.
6. **Typing:** the reception wants the character name and the storehouse a serial: two typed
   inputs for the typing guard and the foreground gate.
7. **Whole towns or routes only:** the towns hold 105 of the 120 NPC sprites; a route through a town
   meets far fewer. Train every sprite of a scope map (3.28's rule as written), or only those near
   the route?
8. **Follow-up, not done:** `labels_v2.l3_warps` and `npc_noclick` still read route.json; pointing
   them at this KB is a separate change.
   ➡️ DONE 2026-10-09 ~21:15 (e6f3b1d, merged 748260d): route.json's warp lists now come from this KB's COMPLETE per-map list (kb_route.py; prt_church gains (115,122) and (166,106)), so labels_v2 and npc_noclick read the completed lists.
