---
doc_type: design
hypothesis: null
status: ACCUMULATING
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: Done at 1280x720 (2026-10-02) -- client switched, SPEC v2 baseline, camera calibrated, first session recorded and auto-labelled (40/40 frames boxed). Next -- Batt picks the persistent sink (ADR-0010; 489 MB/min lossless), then the hand-checked set for B6 (label IoU) and the v0 box-size/foot-offset refinement.
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
| B4 | `projection` | Normalised-DLT homography from cell offsets (player-relative) to pixels; residuals in px | **calibrated 2026-10-02 at 1280×720** (`camera_default.json`): 42/42 clicks, residual median 13.3 / p95 23.8 px; standing Porings 6–10 px |
| B5 | `labels`, `scripts/qa_export.py`, `/qa` | Boxes from projected foot points, per-class sizes v0, YOLO lines, GM exclusions; the QA overlay on the console's `OverlayCanvas` | first QA 2026-10-02: 40/40 sampled frames boxed, boxes on the Porings, ~8 px high (foot offset v0) |
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
- **Exact numbers (set 2026-10-02):**
  - OptionInfo `WIDTH`×`HEIGHT` 1296×759, the outer frame, gives a **1280×720 client area,
    rendered 1:1**. The client renders at its client-area size and is never scaled (measured).
  - The window sits at saved position 72/46 → `GAME_REGION=80,77,1280,720`.
  - The session (`XVFB_RESOLUTION`) is **1440×900**.
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

## What is deliberately NOT here yet

- **Per-class box sizes beyond v0:** the hand-checked set comes first.
- **Monster HP and attacks:** packets 0x0977 and 0x08C8 are in the length table but not decoded
  (phase1 note).
- **Anything that reads frames live for the agent:** Phase 3/4, behind ADR-0005.
