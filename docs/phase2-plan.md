---
doc_type: design
hypothesis: null
status: ACCUMULATING
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: Switch the client to a 1280x720 client area (frozen for Phase 2), re-run the benchmark there, then the calibration recording (click grid + GM-spawned Porings) AT 1280x720 -> projection residuals; capture the UI anchor templates on the same layout.
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
| B1 | `shards`, `scripts/record_session.py` | WebDataset tar shards: lossless PNG (stdlib), per-frame JSON, manifest, packets for the window | shards done + tested; recorder in progress |
| B2 | `timeline` | `Timeline(events).frame_world(t)`: the world at a frame's time. Snapshots + replay; walks interpolated along the real path with rAthena's timing; per-backend latency offset passed in (benchmark p50) | done + tested |
| B3 | `mapcache`, `paths`, `scripts/gen_mapcache.py` | rAthena map caches at the pinned SHA. The `import → pre-re → base` order is the lab's, `prere=yes`: **prt_fild08 / prt_church exist only in `db/pre-re`**. Walkability is CELL_CHKNOPASS: gat 1 and 5, last row and column. rAthena's A* is ported **exactly**, including the client-matching binary heap's tie order and the node-slot collision quirk | done + tested; hashes equal the running server's files |
| B4 | `projection` | Normalised-DLT homography from cell offsets (player-relative) to pixels; residuals in px | done + tested; the live calibration fit is pending |
| B5 | `labels`, `scripts/qa_export.py`, `/qa` | Boxes from projected foot points, per-class sizes v0, YOLO lines, GM exclusions; the QA overlay on the console's `OverlayCanvas` | labels done + tested; QA in progress |
| B6 | `metrics` | IoU, greedy per-class matching at 0.5 → precision / recall / mean IoU (the benchmark's `label_iou`) | done + tested; the hand-checked set is pending |

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
- **Exact numbers:** the session size, `GAME_REGION`, and whether the client is scaled. They are
  recorded in docs/client/rathena-client.md once set.

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
- **Scope now:** HP/SP bars and text, chat input, hotbar slots, the Game option window. The
  templates and offsets are measured on the frozen 1280×720 layout; the geometry in code until then
  is provisional.
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

1. Camera reset by a map change; GM at `prt_fild08 170,375`.
2. **Click grid.** The agent clicks a grid of pixel offsets around the character (not on the
   character). For each click, the client's own `self_move_request` (target cell) pairs a click
   pixel with a cell offset: the client's own pixel→cell pick, no detection needed.
3. **Validation:** GM `@monster poring` near the character. Their packet cells, projected, vs their
   sprites' detected foot points → residual px.
4. The recorder records the whole run (≤ 2 min, /dev/shm) to measure MB per minute and to feed the
   first `/qa` overlay.

## What is deliberately NOT here yet

- **Per-class box sizes beyond v0:** the hand-checked set comes first.
- **Monster HP and attacks:** packets 0x0977 and 0x08C8 are in the length table but not decoded
  (phase1 note).
- **Anything that reads frames live for the agent:** Phase 3/4, behind ADR-0005.
