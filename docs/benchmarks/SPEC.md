---
doc_type: design
hypothesis: null
status: LIVING
role: null
verdict_date: 2026-10-02
verdict_ticket: null
supersedes: null
related: []
next_action: Run the RDP reference baseline under v1, then the Sunshine S1 run (ADR-0009). Any change to the procedure bumps the version and re-baselines.
---

# Capture-backend benchmark: SPEC v1

One fixed procedure for every capture backend: RDP today, Sunshine S1/S2 next, and later phases.
It is versioned: **any change to a condition, a metric or a method bumps `SPEC_VERSION`** (in
`scripts/benchlib.py`), and the reference backend is re-run under the new version before comparing.
A result from an older version is history; it is never compared with a newer one.

- **Harness:** `scripts/bench.py run --backend rdp|console --label NAME`.
- **Arithmetic:** `scripts/benchlib.py`, unit-tested in `services/backend/tests/test_bench.py`.
- **Output:**
  - `docs/benchmarks/<date>-<backend>-<confighash>-<label>.{json,md}`;
  - the running table [README.md](README.md), from `bench.py table`;
  - raw evidence (frames, raw delays) in `data/bench/runs/<run_id>/` (gitignored).

## 1. Fixed conditions

| Condition | v1 value | Why / verified |
|---|---|---|
| Scenes | **outdoor `prt_fild08 170 375`**, **indoor `prt_church 99 112`** | prt_fild08 170,375 is free of wandering NPCs, unlike new_4-1, where "Shion" blocks walks. The outdoor spot differs from the 2026-10-01 RDP arms (new_4-1), so **RDP is re-baselined under v1**. |
| Game window | 800×664 (client area 784×625 at `GAME_REGION`), dgVoodoo **FPSLimit 30** | docs/client/rathena-client.md |
| Display | 1280×800 for every backend (Xvfb; the console mode sets 1280×800 too) | Same `GAME_REGION`, signatures and crops |
| Camera | **Reset before every scene by a map change**: `@warp` to the other scene's map, then to the scene | Verified 2026-10-02: after a rotation, a map change restores the scene band exactly (0.0 % pixels changed). A **same-map** `@warp` does not (96 % changed). Zoom is never touched. |
| Chat | The 3 system lines every map change prints (feeding/call/homunculus) | Deterministic without typing; the chat crop is compared only right after a map change |
| UI state | Chat input closed (an empty open input + Enter closes it); no NPC dialog; no console in front | Hotkeys don't reach the game while the chat input has focus (2026-10-02) |
| Mux | ASSIST, GM online=1, a human lease pauses the agent | A run during which a lease paused input is **re-run** (0-fps seconds poison p10) |
| Viewers | Recorded (`preflight.viewers`) | A console viewer makes the backend's capture hub run; that is backend CPU, not counted in `lab_cores` |
| Lock | The capture-backend lock says the run's backend, `steady`; the host file agrees with `/health` | ADR-0009 |

## 2. Metrics (the same names for every backend)

| Metric | Method | Where |
|---|---|---|
| `delivery_fps` {median, p10, p90} | 60 s camera rotation (bot right-drag sweeps). A grab of the scene band counts as a frame when >1 % of pixels moved by >24 levels from the previous grab. Per-second counts, the 5-s lead-in and the tail dropped. | `measure_motion.measure_rotation` |
| `lab_cores_motion` {per container, total} | cgroup `cpu.stat usage_usec` of the display path (desktop: Xvfb + xfreerdp; gamestream: Moonlight) over the rotation | `measure_motion.cores_between` |
| `idle_cores` | The same, 120 s, no input, game visible (idle animation only), right after a camera reset | `bench.idle_cost` |
| `packet_to_frame_ms` {matched, trials, p50, p75, p90, p95, p99} | 40 click-to-walks, ±3 cells. The packet time is the sniffer's kernel time of our `self_move` (CLOCK_MONOTONIC). The frame time is the first grab whose scene band differs (>10 % of pixels by >24) from **the last grab before the packet** (the corrected method, 2026-10-01). | `measure_delay.measure_walks` |
| `key_to_paint_ms` (same fields) | 40 presses of **Escape**, which toggles the client-local "Game option" window (verified 2026-10-02; Alt+E/Alt+V do not reach the game). The send time is the agent's monotonic time just before the key goes out; the paint is the first grab of that window's region differing from the last pre-press grab. An even count leaves the window closed, and **Enter is never sent while it is open** (its first button returns to character select). | `bench.key_to_paint` |
| `fidelity` {crop: psnr_db, ssim} | Crops `hp_sp_panel` (2,19,216,110), `skill_bar` (230,1,290,65) and `chat` (4,549,580,46), client-relative. Compared with the **lossless reference** (below). SSIM is on luma, 11×11 Gaussian σ1.5. | `bench.fidelity`, `benchlib.psnr/ssim` |
| `windows_side` | Windows-side counters for the run's time windows (RDP: RemoteFX in/out fps, skips, encode ms; console: GPU VideoEncode %, Sunshine CPU). typeperf runs in the session's console and the summary is read from a screenshot. Annotated, not parsed. | manual for v1 |
| `label_iou`, `ocr_cer` | Placeholders: Phase 2 label IoU vs a hand-checked set (docs/phase2-plan.md), and the OCR track's character error rate | `null` in v1 |

**Percentiles:**
- **nearest rank over ALL trials**, a trial with no detected frame within 1.5 s counting as a miss
  (reported as `">1500"`);
- `matched/trials` is always reported;
- this reproduces the tables published on 2026-10-01 (`test_bench.py`).

## 3. The lossless reference (Batt, 2026-10-02)

- **Reference = the same UI crops captured lab-side over RDP with `RDP_GFX=off`.**
  - FreeRDP's legacy bitmap path: planar/interleaved.
  - NSCodec and RemoteFX are opt-in (`+nsc`/`+rfx`) and stay off.
  - `bench.py reference` switches to `off`, captures at the outdoor scene after a camera reset,
    stores `data/bench/reference/*.npy`, and switches back.
  - No new file channel exists (ADR-0004: file transfer is human-only).
- **Validated once**:
  1. A CopyFromScreen PNG of the game client area, taken in the session, is copied to the lab **by
     Batt, by hand**.
  2. `bench.py validate-reference PNG` proves that the RDP-off crops are bit-identical, or reports
     the residual.
  3. Until that has passed, fidelity numbers are marked "vs RDP-off (unvalidated)".
- **Validated 2026-10-02:** Batt's CopyFromScreen PNG (10:48:05) vs the RDP-off capture (10:46):
  `skill_bar` **bit-identical** (max diff 0). `hp_sp_panel` differs only in one block (the
  Base/Job level box, by 1 level in one channel): it is semi-transparent over the animated scene.
  `chat` shows the scene through it too. So the RDP-off path is lossless, and semi-transparent UI
  varies between any two captures.
- **Therefore each crop also has a static mask:** the pixels identical in both validation captures
  (`data/bench/reference/<crop>_static.npy`). Fidelity reports `psnr_static_db` over those pixels,
  which is the codec's loss alone, next to full-crop PSNR and SSIM.
- Static fractions measured: `hp_sp_panel` 0.917, `skill_bar` 1.0, `chat` 0.011. The chat crop is
  almost all scene-through-glass, so its fidelity numbers are indicative only; the codec verdict
  rests on `skill_bar` and the static part of `hp_sp_panel`.
- **Console runs** compare against the reference taken in RDP mode before the handover. The UI
  crops are screen-fixed and static, so they are identical across backends.

## 4. Config hash

`config_hash` = 12 hex of sha256 over canonical JSON of:
- the SPEC version and the backend;
- the client: name, version, codec (RDP: from rdp-loop's last `connecting to` line);
- the Xvfb resolution, `GAME_REGION`, FPSLimit and the scenes.

Same hash means the same configuration.

## 5. Interpreting a comparison

Explain every difference by mechanism, never by a single number:
- transport: TCP RDP vs UDP GameStream;
- encoder: RemoteFX progressive vs Quick Sync H.264;
- client decode: FreeRDP vs FFmpeg;
- the Xvfb hop: S1 vs S2;
- where the cursor is drawn: an X cursor vs composited into the video.
