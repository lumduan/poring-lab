---
doc_type: design
hypothesis: null
status: ACCUMULATING
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: Done at 1280x720 (2026-10-02) -- client switched, SPEC v2 baseline, camera calibrated, first session recorded and auto-labelled (40/40 frames boxed). Sink chosen (ADR-0010, TrueNAS) but waits for Batt's NAS recipe; then the hand-checked set for B6 (label IoU) and the v0 box-size/foot-offset refinement. Part D (presentation-agnostic policy) is a plan -- D1 done, D4/D5 next in RDP mode.
last_reviewed: 2026-10-02
---

# Phase 2 plan: projection calibration and auto-labeling (offline foundation)

Phase 2 turns recorded sessions into labelled frames.
- **Backend-agnostic:** it is built on `poring_env` frames and packet events, never on one capture
  backend.
- **Offline:** recorded data and code only; no Windows control, no mux, no service lifecycles.
  Recording itself is the one live step.
- **Format:** [ADR-0010](adr/0010-dataset-format.md).

## Building blocks (`packages/poring_dataset`)

| # | Module | What | Status (2026-10-02) |
|---|---|---|---|
| B1 | `shards`, `scripts/record_session.py` | WebDataset tar shards: lossless PNG (stdlib), per-frame JSON, manifest, packets from the last map change before the first frame (`timeline.session_events`) | done; first session 2026-10-02: 120 s, 532 frames, **489 MB/min** at 1280×720 |
| B2 | `timeline` | `Timeline(events).frame_world(t)`: the world at a frame's time. Snapshots + replay; walks interpolated along the real path with rAthena's timing; per-backend latency offset passed in (benchmark p50) | done + tested |
| B3 | `mapcache`, `paths`, `scripts/gen_mapcache.py` | rAthena map caches at the pinned SHA. The `import → pre-re → base` order is the lab's, `prere=yes`: **prt_fild08 / prt_church exist only in `db/pre-re`**. Walkability is CELL_CHKNOPASS: gat 1 and 5, last row and column. rAthena's A* is ported **exactly**, including the client-matching binary heap's tie order and the node-slot collision quirk | done + tested; hashes equal the running server's files |
| B4 | `projection` | Normalised-DLT homography from cell offsets (player-relative) to pixels; residuals in px | **calibrated 2026-10-02 at 1280×720** (~~`camera_default.json`~~ ➡️ `camera_rdp.json` since 2026-10-03: one camera per backend): 42/42 clicks, residual median 13.3 / p95 23.8 px; standing Porings 6–10 px. ➡️ **2026-10-03: the perspective camera + the map's GAT altitude WINS on held-out points** (`camera.py`, `gat.py`, `camera_fit.py`). Pre-registered hypothesis: terrain height causes part of the residual; SUPPORTED. Leave-one-out over the 42 clicks: homography 14.7/26.6 px, flat camera 12.3/32.0, **camera + altitude 9.4/18.6**. GM-spawn feet: static 8.2/9.9 → **6.0/6.7** (all 28: 8.8/51.1 → 6.6/47.0; the moving ones' tail is timing). Fit: yaw 0.1°, pitch 44.8°, distance 400.7, centre (640.8, 361.9). Both are stored; the homography is the fallback without a GAT. Sources: THIRD_PARTY.md |
| B5 | `labels`, `scripts/qa_export.py`, `/qa` | Boxes from projected foot points, per-class sizes v0, YOLO lines, GM exclusions; the QA overlay on the console's `OverlayCanvas` | first QA 2026-10-02: 40/40 sampled frames boxed, boxes on the Porings, ~8 px high (foot offset v0). ➡️ **2026-10-04, the first S2 datasets** (section "S2 datasets" below): outdoor labels OK with camera + GAT; **indoor labels INVALID**: indoor maps use a different camera, and invisible NPCs get boxes |
| B6 | `metrics` | IoU, greedy per-class matching at 0.5 → precision / recall / mean IoU (the benchmark's `label_iou`) | done + tested; the hand-checked set is pending |

## S2 datasets (2026-10-03/04, the first through the bot's path, ADR-0014)

All sessions were recorded from the S2 frame bus, every frame with its bus `frame_id`
(recorder v3). Each was shipped to the NAS, re-hashed and verified, and its local copy deleted.

| session | what | frames | size | rate | labels (qa_export, camera + GAT) |
|---|---|---|---|---|---|
| `20261003T215314-console-s2-outdoor` | outdoor, fps 10 target | 441 (1.7 min) | 0.92 GB | 526 MB/min | 40/40 frames boxed, on target |
| `20261004T053620-console-s2-probe` | outdoor probe, fps 3, PNG level 6 | 360 (2 min) | 0.76 GB | 378 MB/min | not exported |
| `20261004T054429-console-s2-outdoor` | outdoor 20 min, fps 1 | 1,200 | 2.59 GB | 129 MB/min (7.8 GB/h) | 18/19 sampled frames boxed, camera + GAT prt_fild08 |
| `20261004T060842-console-s2-indoor` | indoor 20 min, fps 1 | 1,176 | 1.99 GB | 101 MB/min (6.0 GB/h) | **INVALID**: the outdoor camera on a diagonal indoor view |

**Write rate and the quant IO guard.** The fps 10 run tripped the recorder's guard after 1.7 min:
~9 MB/s of PNG, quant-postgres io_full 65.7 % in one 10 s bin (21:54:55 ICT).
- A 1280×720 game frame is about 2.1 MB as PNG at zlib level 1 *and* at level 6: textured scenes
  barely compress.
- The fps 10 target only reached ~4.2 fps.
- Batt chose fps 1 under the armed guard (2026-10-04). Both 20-min sessions then ran with the worst
  stall at 8.2 % and no stall window.
- 3 fps (6.3 MB/s) also kept the guard quiet in a 2-min probe, but it is above the budget Batt
  approved.

**Open, before these sessions feed Phase 3:**
1. **An indoor camera.** prt_church is drawn on a diagonal: both reference clients hard-code an
   indoor yaw of about −45° and a narrower zoom band (THIRD_PARTY.md sources), and both of our
   calibrations are outdoor. Calibrate per map class (indoor/outdoor), and record the class in the
   camera file.
2. **Invisible NPCs.** objtype 6 entities with no sprite get boxes; the label filter must drop them.
3. **The activity driver must not click entities.** Indoors its walk clicks hit Porings (attacks)
   and NPCs (dialogs), and the GM was killed. Click only empty cells, using the walk graph and the
   entities' projected cells.
4. **The GM-spawn validation needs a detector that works on H.264 frames.** The pink-blob foot
   detector matched neighbours' feet on S2 frames.

➡️ **2026-10-04 (Post-S2 round Part B, live in the S2 session): items 1–4 are DONE.** The old
indoor session is marked INVALID on the NAS (`dataset_ship.py mark-invalid`) and kept.
1. **The indoor camera, by the client's own rule + one measurement** (`camera.py`; nostalro's rule,
   THIRD_PARTY.md). A map is indoor iff it is in the client's `indoorrswtable.txt` (extracted to
   /dev/shm, never committed). B2 (`scripts/camera_validate.py`, prt_church) measured the model:
   - **The yaw is +45° in our convention** (fitted 45.96°): the sign was the open question.
   - **The camera is also closer: distance 273 vs 400 outdoors.** The narrower indoor clamp band
     pulls the default in.
   - **Rotation alone was not enough:** clicks median 78 px; Poring spawns 40/88 px.
   - **Rotation + distance:** clicks median 11.3 / p95 18.6 px (the fit); on the HELD-OUT
     single-Poring spawns 11.5 / 21.7 px (20 frames, 5 spawns). The outdoor fit's own level is
     8.9 / 18.1.
   - **The other models on the same spawns:** yaw 0 gave 84.5 / 149.4 px, and −45° gave
     136.7 / 251.7.
   - Both are recorded in `camera_<backend>.json` "indoor". RDP carries the console values over,
     marked NOT measured.
2. **Invisible NPCs, two paths:**
   - classes 111/139/32767 and 45 portals (rAthena's facts);
   - AND any unit sent with an invisibility option (effectState HIDE/CLOAK/INVISIBLE). The
     church's six "Single Army" event NPCs have ordinary sprite classes, and the B6′ sheet showed
     them as a staircase of empty boxes.

   The option needs the sniffer's decoder: a guarded sniffer rebuild, or the session's packets
   replayed from pcapng.
3. **The activity driver clicks only empty walkable cells.** Two checks, both at decision time:
   - the map's GAT walkability (static data);
   - a pixel check: hovered, a walkable empty cell shows the client's GROUND MARKER (mint
     chevrons, 180–314 px in a 90×90 crop). An entity shows none (Porings: 0).

   The first idea, a template of the walk cursor, failed: RO's cursor is animated (it spins). The
   clicks go through the map's projector (`click_for_cell`), so a rotated camera walks where it
   means to. B6′: 35 walks, 25 hover rejections, 0 GM failures, nobody killed.
4. **The spawn detector:** one Poring at a time, new pink pixels against a background frame,
   outside the client's UI windows and the chat. The GM command's own pink chat text was the first
   run's false match.
5. **Facing (billboards):** labels carry the sprite direction the client draws:
   `displayed_direction`, nostalro's formula, with the heading from the packets (PosDir) or the
   step walked. A rotated camera therefore needs no rotated-sprite training: the facing label
   accounts for it.
6. **Boxes behind the client's UI windows are dropped** (`ui_layout.UI_RECTS`, the frozen layout:
   ≥ 50 % covered). The B6′ sheet showed labels under the hotkey bar and the Basic Information
   window.

**B6′ (the new indoor set):** `20261004T103815-console-s2-indoor-v2`, 5 min at fps 1, 300 frames,
110.8 MB/min.
- Its sheet showed boxes on the Porings and the church NPCs. The two problems above (event NPCs,
  UI occlusion) were found on it and fixed after it.
- Its packets were then REPLAYED from the banked pcapng through the effectState decoder (the
  manifest's `packets_source` says so), and the sheet re-checked: the staircase is gone, and so are
  the boxes under the UI.
- Shipped to the NAS and verified. The `/qa` bundle is exported for Batt's hand-check
  (`label_iou.py score` once saved).
- The old indoor set is marked INVALID and kept.

**From 2026-10-04 (Batt, C4) new console sessions are H.264 with an IDR every 1 s** (ADR-0010
note): every frame is kept at ~2.5 GB/h, and each is verified on the host after shipping
(`dataset_check.py`). `qa_export` and `label_iou` read both formats.

**The first H.264 datasets: the Phase 3 S2 session, 2026-10-04 13:01–15:34 ICT (06:01–08:34 UTC).**
- Seven sessions, IDR 1 s; all shipped to the NAS and verified (15:40–15:43). The local copy was
  deleted, leaving 164.5 GB free.
- Totals: 225,786 frames, 4.97 GB, 119.4 min.
  - 40.8–42.7 MB/min against the pre-registered ~41.
  - 8 freezes (0.067/min against ~0.1).
  - 0 queue overflows, 0 gaps, 0 decode errors.
- **Host determinism** (`dataset_check.py`, every frame vs the live checksum), 15:44–17:04 ICT:
  - **225,786 / 225,786 frames identical** in all 7 sessions: 0 mismatched, 0 missing hashes,
    0 undecodable;
  - the decoder build matches the recording's (PyAV 19.0.1, libavcodec 63.1.102);
  - 45–53 frames/s at `nice 10`;
  - results in `data/bench/h264/<session>.check.json`.
- Each session's usable content differs, because the activity driver failed three ways during the
  session (each fixed and committed the same day):

| Session | Min | On scene | GM activity | Note |
|---|---|---|---|---|
| p3-outdoor-a | 20.0 | 20.0 | idle: the driver stopped at start | the `poring-lab shell` covered the client's title bar → `minimize_consoles` first |
| p3-indoor-a | 9.4 | 9.4 | 152 walks | stopped by the IO guard (Frigate 27.8 %); quant was fine |
| p3-outdoor-b | 20.0 | 4.0 | 24 walks | walked into the gate to prontera at 240 s, then died there (provoked Porings) and lay dead behind the restart menu |
| p3-indoor-b | 20.0 | 20.0 | 73 walks | the GM died at ~585 s (provoked Porings) and stayed dead to the end |
| p3-outdoor-c | 20.0 | 17.5 | 94 walks, 6 re-entries | four gate exits, each recovered by the new re-entry |
| p3-outdoor-d | 20.0 | 20.0 | 123 walks | clean: targets kept south of the gate |
| p3-indoor-c | 10.0 | 10.0 | 76 walks | clean |

- The first indoor-a attempt, with no scene entry (walking prt_fild08 through the prt_church
  projector), was discarded (34 s).
- **Driver fixes** (`dataset_activity.py`):
  - minimise consoles, then enter the scene, before the walk;
  - re-enter after 3 consecutive empty picks;
  - outdoor targets kept south of the start row.
- The GM itself is level 1 (40 HP). Making it survive fights is a Batt decision
  ([phase3-plan.md](phase3-plan.md) §9).
- **The auto-label check** (`qa_export --max 24 --sheet`):
  - outdoor-d: 24/24 frames boxed;
  - indoor-c: 23/24 frames boxed;
  - by eye, boxes sit on the Porings and NPCs on both maps, and hidden NPCs are not boxed.
  - The v0 limits are visible: empty boxes under tree canopies (occlusion), offsets on walking
    Porings (timing), and indoor boxes tighter than the ~1.34× larger indoor sprites. `predict_sprite`
    (phase3-plan.md M2) addresses the last.

## Resolution: FROZEN at a 1280×720 client area (Batt, 2026-10-02)

- **Why the window was small, and why that no longer holds.** It was cut to 800×664 when pixel
  count looked like the fps cap. Arm C proved the cap was FreeRDP 3.15's client path; 3.32 delivers
  30 fps.
- **Why 1280×720 is better:**
  - more play area;
  - an uncramped UI (the OCR track);
  - larger sprites (YOLO).
- **Frozen for Phase 2.** Calibration, recordings and datasets happen ONLY at this geometry: the
  cell→pixel mapping is resolution-specific. Nothing was calibrated at 800×664, so nothing needs
  discarding; the benchmark's fidelity reference is re-captured.
- **Exact numbers (set 2026-10-02):**
  - OptionInfo `WIDTH`×`HEIGHT` 1296×759, the outer frame, gives a **1280×720 client area,
    rendered 1:1**. The client renders at its client-area size and is never scaled (measured).
  - The window sits at saved position 72/46 → `GAME_REGION=80,77,1280,720`.
  - The session is **1440×900**. ➡️ Since 2026-10-02 evening that is `SESSION_SIZE`, drawn 1:1 at
    the top-left of a 1920×1200 Xvfb canvas (`XVFB_RESOLUTION`; ADR-0009 amendment, Part D1 below).
    Before that, the session was the whole `XVFB_RESOLUTION` screen. GAME_REGION is unchanged.
  - Evidence and the rejected borderless route: docs/client/rathena-client.md.

## UI anchor map ([ADR-0011](adr/0011-ui-anchor-map.md), built alongside projection)

- **Two coordinate systems, one pixel space.**
  - World entities: cell → pixel through the projection (B4).
  - UI elements: window-relative → pixel through `poring_env.ui_anchors`.
- **Layer 1, windows.** Found by title-bar template wherever they are dragged; RO windows are
  fixed-size.
- **Layer 2, elements.** Boxes relative to the window, or icon templates for things that move
  between slots.
- **The seam.** `Resolver` takes `ui("chat_input")` / `cell(dx, dy)` and returns a pixel. Policy
  never holds a pixel, so resolution, window moves and capture backends never touch it.
- **Scope now:** HP/SP bars and text, chat input, hotbar slots, the Game option window.
  - **Measured 2026-10-02** on the frozen 1280×720 layout (ADR-0011 table).
  - The templates carry stable masks, because RO windows are translucent.
  - `scripts/ui_anchors_tool.py check` locates the windows on a live or saved frame.
- **Not everything is a vector.** Predictable UI layout goes to the anchor map; anything moving
  every frame goes to projection.

## Clock and alignment

- **One clock:**
  - packet events carry the kernel receive time on the host's `CLOCK_MONOTONIC`;
  - the server tick is that clock in ms mod 2³² (phase1-validation: 0–1 ms);
  - frames carry `t_capture_ns` on the same clock.
- **A frame lags the world it shows** by the capture backend's packet→frame delay. The labels for a
  frame captured at t use `frame_world(t − offset[backend])`, where offset is the backend's
  benchmark p50 (RDP v1 baseline, then S1).
- **Camera:** the projection holds for the **default camera** only.
  - A map change resets it (verified 2026-10-02).
  - Right-drag (rotation) and wheel (zoom) break it. Both pass through the mux, so the input log
    marks every frame after one as `camera_dirty` until the next map change.
  - Terrain height bends the flat-ground homography. Residuals are reported per area.

## Calibration (the one live step, RDP mode, ASSIST, under the IO guard)

> **Done 2026-10-02 at 1280×720.** Findings that changed the procedure:
>
> - **The spot moved from 170,375 to 268,107.** 170,375 (the bench scene) has 2 open cells and
>   lies 24 cells from the Prontera gate warp. The widened click grid walked the GM into it. The
>   map cache picked 268,107: walkable 37 cells in every direction, more than 100 cells from every
>   edge portal.
> - **Validation:** standing Porings 6–10 px off, with a steady ~8 px vertical bias (projected cell
>   centre vs sprite feet). Walking ones are off by up to 72 px, because the frames were projected
>   without the backend offset. The labels use the offset (packet→frame p50, 376 ms on RDP v2).
> - **A recording must carry the world state from the last map change.** With only [t0 − 5 s, …]
>   the player's position was unknown and the first export boxed 0/40 frames. The recorder (v2) now
>   starts its packets at that map change (anchor in the manifest), and `--repack` rebuilds an old
>   session from the sniffer's 7-day archive.
> - **Volume:** 489 MB/min of lossless 1280×720 PNG, i.e. ~29 GB/h. The effective capture rate was
>   4.4 fps against the 10 fps cap, because the grab of a changed 1280×720 frame dominates.

1. Camera reset by a map change; GM at `prt_fild08 170,375`.
2. **Click grid.** The agent clicks a grid of pixel offsets around the character (not on the
   character). For each click, the client's own `self_move_request` (target cell) pairs a click
   pixel with a cell offset: the client's own pixel→cell pick, no detection needed.
3. **Validation:** GM `@monster poring` near the character. Their packet cells, projected, vs their
   sprites' detected foot points → residual px.
4. The recorder records the whole run (≤ 2 min, /dev/shm) to measure MB per minute and to feed the
   first `/qa` overlay.

## Part D (plan only): the policy never depends on presentation

**Resolution and language are one goal.** The policy speaks intents on keys. Pixels come from the
anchor map and the projection (ADR-0011); text comes from a locale pack (ADR-0012). A new screen
size or a new language changes calibration and data, never policy.

| # | Step | Status |
|---|---|---|
| D1 | The session area: capture and input over `SESSION_SIZE`, independent of the canvas | ✅ done 2026-10-02 |
| D2 | Projection per resolution profile | plan |
| D3 | Auto-calibration at session start: packet-assisted on rAthena (setup only) + a pixels-only path | plan; ruled 2026-10-02 (ADR-0007 amendment) |
| D4 | Player-like UI management through the anchor map | plan; next |
| D5 | A hotkey table verified live | plan; next, together with D4 ➡️ SUPERSEDED 2026-10-07: demonstrated live in `docs/phase4-ui.md` (L2 file `packages/poring_skills/l2/kro-20211103-prere.yaml`) |
| D6 | Acceptance: the same keyed action at two languages and two sizes | after D2 + ADR-0012 packs |

### D1: the session area (first step toward resolution independence, DONE)

- **The layout:** `SESSION_SIZE=1440x900` is the Windows session, drawn 1:1 at the top-left of a
  `1920x1200` Xvfb canvas.
- **Capture and input:** the backend's stream and capture, vision, `ro_agent` and the latency probe
  crop to the session and normalise input over it. One variable for every consumer, guarded by
  `test_guards.py`.
- **What stayed put:** GAME_REGION, every signature and every agent coordinate.
- **Why now:** Moonlight's console-mode window only opens at native size when the stream is under
  80 % of the screen (ADR-0009, handovers 2–6). It does open at native size now.
  - S1 itself is still open: Moonlight's main thread stalls at stream start.
  - That stall is independent of this layout.
- **What it leaves to D2:** the client area is still the one frozen profile (1280×720). D1 only
  decoupled the session from the screen.

### D2: projection per resolution profile

- **A profile:** client-area size, plus its default-camera homography (B4), plus its anchor
  templates (ADR-0011).
- **Stored as data:** `camera_<w>x<h>.json` next to today's `camera_default.json`, and templates
  per profile.
- **Selection:** the agent picks the profile from the measured client area, never from config
  alone.
- **A new profile repeats B4's procedure once** (the click grid at a safe spot, the Poring
  validation). Labels and datasets record their profile.
- **Mixing profiles inside one dataset is allowed,** because the labels are cells, not pixels.
  Training sets say which profiles they hold.

### D3: auto-calibration at session start (ruled 2026-10-02, ADR-0007 amendment)

- **The idea:** replace the 42-click grid with a short self-check at session start.
  - A handful of walk clicks, each paired with the client's own `self_move_request` target cell.
  - Fit the homography.
  - Accept if the residual median is within the stored profile's.
  - Otherwise keep the stored profile and flag it.
- **The open question:** the pairing reads packets. That is fine offline, and the camera is
  geometry, not world state (ADR-0011's open point). But a calibration *at session start* moves
  that read closer to decision time. **Batt decides** whether it stays on the offline side of
  ADR-0007's line, or whether D3 must stay an operator step.
  ➡️ **RULED 2026-10-02** ([ADR-0007 amendment](adr/0007-packet-ground-truth-channel.md)):
  - packet-assisted calibration at session start is allowed on rAthena as a SETUP / ground-truth
    tool: it outputs a profile, never a per-action input;
  - the deployable bot must also have a **pixels-only** calibration path (for servers without
    packet access), and D3 ships both.

### D4: manage the UI like a player, through the anchor map

The policy states the UI it needs; a small UI manager makes it so with keyed actions.
- **Inventory:** `locate()` says which windows are open and where. Unknown overlaps count as "not
  visible".
- **Invariants the manager keeps:**
  - Basic Info (HP/SP) is always visible and uncovered;
  - the chat window is minimised until a chat intent needs it;
  - windows the current task does not use are closed (keyed close buttons via `label_key`, or the
    verified hotkey from D5).
- **Small screens:** a per-profile layout rule says which windows fit and where they dock (relative
  to the client edges). Positions are anchors, never absolute pixels.
- **Intents:** `ensure_visible(window.basic_info)`, `ensure_closed(window.inventory)`,
  `ensure_minimised(window.chat)`. Each is verified by the next `locate()`, not assumed.

### D5: hotkey table, verified live

- **Expected bindings:** classic RO conventions, **to verify on our client and per capture
  backend.** Verified = the window appears or disappears in `locate()` within the packet→frame
  delay.

| Hotkey | Expected window | Verified |
|---|---|---|
| Escape | Game option (toggle) | ✅ RDP, 2026-10-02 (SPEC `key_to_paint_ms`) |
| Alt+V | Basic Info (toggle / expand) | ❌ did not reach the game, 2026-10-02 |
| Alt+E | Inventory | ❌ did not reach the game, 2026-10-02 |
| Alt+Q | Equipment | to verify |
| Alt+S | Skill list | to verify |
| Alt+A | Status | to verify |
| Alt+Z / Alt+G / Alt+H | Party / Guild / Friends | to verify |
| F12 | Hotkey bar (toggle) | to verify |

- **Why Alt+E / Alt+V did not reach the game: NOT established.** SPEC.md records only the fact.
  Candidates, cheapest test first:
  1. **Windows menu activation:** an Alt press and release on its own activates the window's menu
     and eats the next key. Test: Alt down → letter down/up → Alt up, as one chord, with no gap.
  2. **Hold length:** the client may sample keyboard state (DirectInput) more slowly than a 50 ms
     XTest hold. Test: 100 / 200 ms holds.
  3. **Chat focus:** the letter went into the chat input. Test: with the chat input unfocused,
     checked by its anchor.
  4. **Remote path:** xfreerdp's keyboard grab or the RDP scancode mapping for Alt combinations.
     Test: the same chord in Notepad in the session.
- **Per backend:** console mode (S1, Sunshine `SendInput`) gets the same table separately.

### D6: acceptance

- **ADR-0012's en ↔ th test:** the same keys resolve, and "open Basic Info, read HP, close it"
  runs.
- **The same scripted action at two client sizes** once D2 has a second profile.
- **One code path, no edits between the runs.**

**Order:** D1 (done) → D4 + D5 (RDP mode, no new data) → ADR-0012 packs (blocked on the NAS) →
D2 when a second resolution is wanted → D3 (both paths) → D6.

## What is deliberately NOT here yet

- **Per-class box sizes beyond v0:** the hand-checked set comes first.
- **Monster HP and attacks:** packets 0x0977 and 0x08C8 are in the length table but not decoded
  (phase1 note).
- **Anything that reads frames live for the agent:** Phase 3/4, behind ADR-0005.
