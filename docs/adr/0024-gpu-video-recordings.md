---
doc_type: decision
hypothesis: null
status: ACCEPTED (decided by Batt 2026-11-09 ~06:3x ICT; built on feat/recording-stage3, live verification pending)
role: null
verdict_date: 2026-11-09
verdict_ticket: null
supersedes: "ADR-0010's lossless-frames rule for RDP recordings (ADR-0010 decision 1, '<frame_id>.png: lossless pixels'); the rest of ADR-0010 stands"
related: [0010-dataset-format.md, 0022-vendor-neutral-accelerators.md, 0005-vision-x-access.md, 0019-windows-stays-clean.md, ../planning/gpu-recording.md, ../../scripts/record_session.py, ../../scripts/media_rec.py, ../../packages/poring_dataset/src/poring_dataset/frames.py]
next_action: "The parent's live checks after the merge (gpu-recording.md 9.4): one short video-only recording beside a pilot on bot-server, dataset_check.py on it, then each switched reader run on stage 2's session p20 with PORING_FRAME_SOURCE=png and =video and the two outputs compared. The cue-fitting studies (miss_cue, target_items, mvp_watch_study, cursor_unknown, UI templates) stay on --format png until each passes its own parity on decoded frames."
---

# ADR-0024: RDP recordings are GPU-encoded HEVC video, no longer lossless PNG

## Context
- **ADR-0010 (2026-10-02)** made a recording a directory of tar shards of LOSSLESS frames:
  `<frame_id>.png`, "exactly what the capture path delivered". The console path has recorded
  Sunshine's own lossy H.264 since 2026-10-04 (ADR-0010's note), so only the RDP path still wrote
  PNG: 1.54-2.31 MB a frame, 5.5-8.4 GB an hour at 1 fps, ~89-159 ms of the recorder's CPU a frame
  on bot-server (stage 1's `encode_png`).
- **The plan** (docs/planning/gpu-recording.md, Batt 2026-11-08: "interested, and it is probably
  the faster way too") put the recorder on the Arc A380's hardware encoder (VA-API, low-power
  VDEnc) in a contained sidecar. VDEnc has no lossless mode ffmpeg can ask for, and the BGR -> YUV
  conversion rounds by itself (plan section 3): any such recording is lossy, so adopting it needed
  Batt's decision on ADR-0010.
- **What was measured, before the decision, against pre-registered bars:**
  - stage 1 (plan 8.4, 2026-11-08, 200 sampled real frames per map): round 3's candidate
    `vpp-hevc444-10-q20` passed every bar: 8.7 ms of CPU a frame, 0.15-0.21 x PNG's bytes, PSNR
    44.3 / 40.4 dB (xmas_dun02 / gef_fild10), the deployed detector's boxes 166 / 166 on xmas_dun02;
    every access unit decodes alone and bit-identically on VA-API, ffmpeg and the host's PyAV;
  - stage 2 (plan 9.1 / 9.3, 2026-11-09 05:00-05:33, ONE whole live session, 1,200 frames,
    recorded as PNG and video side by side beside pilot p20): VERDICT PASS on every bar --
    every frame fed, decoded and matched; 0.84 vs PNG's 5.69 GB an hour at 1 fps (ratio 0.1475);
    the video side 18.3 ms of CPU a frame against the PNG writer's 136.1; PSNR 43.42 dB (min 41.40),
    SSIM 0.99375; the detector's boxes P1 / P2 0.9973, p95 shift 0.4 px; every frame signals pc /
    bt709; no detect-server latency cost (p50 20.5 vs 20.6 ms, p95 22.1 vs 21.9, GPU share 1.0).
- **Batt, 2026-11-09 ~06:3x ICT**, answering the 05:37 report: "ใช้ การ์ดจอแทนได้เลย" -- use the
  GPU video in place of PNG.

## Decision
1. **The default RDP recording is `vpp-hevc444-10-q20`**, video only, no PNG twin:
   - the encoder is round 3's candidate exactly (`gpu_rec_bench.ARMS`, pinned by
     `test_media_rec.py`): the grab's BGRA (alpha set to 255) uploaded, `scale_vaapi` to 10-bit
     4:4:4 (`xv30`) with BT.709 FULL range and the primaries / transfer named, `hevc_vaapi`
     low-power, RExt (Main 4:4:4 10), CQP 20, every frame an IDR (`-g 1 -bf 0`), access unit
     delimiters, the stream tagged bt709 / pc;
   - it runs in the contained sidecar `media-rec` (the media-probe image: no network, a read-only
     root, the render node only), fed by `record_session.py` through ONE named pipe in
     `/dev/shm/poring-lab-mediarec`; the stream is written sequentially to
     `~/poring-lab-rec/.media-rec` and renamed into the session at the end (plan 9.1's mechanism,
     unchanged).
2. **The session layout of a video recording** (recorder v7):

       <session>/video.hevc         the HEVC elementary stream (Annex B), all-intra
       <session>/video.idx.csv      one row per KEPT frame: frame_id, t_mono_ns (the grab's,
                                    the packets' CLOCK_MONOTONIC), video_index (its access unit),
                                    status (fed | dropped_queue_full | write_failed |
                                    not_fed_<state>), write_start_ns, write_end_ns, and the PNG
                                    record's own t_wall, bus_frame_id, source
       <session>/video.ffmpeg.log   the encoder's log
       <session>/packets.jsonl.gz   unchanged (pseudonymised, ADR-0010 decision 1)
       <session>/manifest.json      format "vpp-hevc444-10-q20", shards [], frames = the frames the
                                    stream holds, kept = the frames offered, bytes = the stream's,
                                    video = the encoder's block (status, reason, fed, by_status,
                                    access_units, sidecar image), png_level null

3. **PNG stays selectable** (`--format png`, to any `--out`), and stage 2's side-by-side stays
   (`--also-png`: a PNG session with its video twin; the PNG is the reference there).
4. **PNG stays REQUIRED for the studies that fit pixel cues or templates on recordings and apply
   them live** -- `miss_cue`, `target_items`, `mvp_watch_study`, `cursor_unknown`, and UI templates
   cut from a recording -- until each passes its own parity on decoded frames (plan section 5 and
   0a.7). **The same for the pre-registered detector studies** (the parent's review, 2026-11-09):
   `map_labels.check_recording` (xmas02-detector.md 3c / T-3: its frame gates were fitted on PNG)
   and `detector_vs_packets.check_session` (the X2 rule) accept recorder v7 but only `format
   png`; a video session is refused there until a pre-registered parity check (live check 4). Those tools refuse a video recording (`poring_dataset.frames.png_required`): never an
   empty read of a session that lists no shards. Record their sessions with `--format png`.
5. **One reader API for both layouts**: `poring_dataset.frames` (frame refs from the index only;
   one frame decoded by its own access unit; a session iterated every N-th frame; the nearest
   frame to a time). Every session reader goes through it: build_frame_cache, qa_export, gold_eval,
   label_quality, m4_validate, recorder_boxes, truth_draw, labels_v2, map_labels,
   detector_vs_packets. `PORING_FRAME_SOURCE=video` reads a stage-2 session from its video twin
   (the parity run of each reader: plan stage 4).
6. **Fail closed, never a silent fallback:**
   - a video side that cannot START (no sidecar, a refused job, another recorder holding it)
     refuses the recording, every part (there is no PNG to fall back on);
   - a video side that FAILS mid-session (the encoder closed its pipe, a write blocked 20 s)
     stops the recording cleanly, `stop_reason: video_failed: ...`; the frames already in the
     stream are the session (manifest `frames` counts only those);
   - a frame the encoder's queue could not take is lost, and its index row says so.
7. **Unchanged from ADR-0010 and its amendments:** a session is a directory with its manifest
   written last; the packet window and pseudonymisation; the backend tag and config hash; the
   game region; the fps cap (1 by Batt's rule); the local root, the free-space floor (30 GB on
   bot-server), the 20 GB unshipped cap, the size cap per recording (`--max-bytes`, which counts
   the stream), the IO rules and `--resume` (now for the video format too), the market-open
   windows; shipping (every data file checksummed, re-hashed on the NAS, then the local copy
   deleted), the NAS layout, the 365-day retention, pins. The console's H.264 and the training
   frame cache (JPEG q95 by default) are not touched by this ADR.

## Consequences
- **Lossy.** A recorded frame is no longer "exactly what the capture path delivered": stage 2
  measured PSNR 43.4 dB (min 41.4) against the PNG of the same grab, ~10 dB above the JPEG q95
  the trainer already reads. Pixel-exact tools cannot read a video session (decision 4).
- **A reader must decode video.** The host's pinned PyAV (19.0.1, software HEVC, one thread)
  decodes each access unit alone, then swscale converts with BT.709 full range; a frame that does
  not signal that convention, or is not the game region's size, is refused. Per frame this is
  slower than PNG on bot-server: stage 1 measured 82-144 ms (decode 68.6-131.5 + conversion
  12.6-13.5) against PNG's 38-50 ms. The frame cache build and the offline studies take that
  extra CPU; training does not (it reads the cache, plan 17b). Opening a session scans the stream
  once for its access units (one `find` per NAL unit, memory-mapped).
- **The sidecar must be up to record.** `guarded_build.py start:media-rec@60` before the first
  recording; a recording without it is refused, not degraded. The format exists only on a host
  with the Arc (dedicated-intel, ADR-0022); elsewhere record `--format png`.
- **The disk and the shipping shrink ~6.8 x** (0.84 vs 5.69 GB/h at 1 fps): bot-server's 20 GB
  unshipped cap holds ~24 h of 1-fps recording instead of ~3.5 h. Higher frame rates are a later,
  separate decision (plan stage 5).
- **No live per-frame checksum.** The sidecar only encodes, so there is nothing like the console's
  `stream.hash.csv`; `dataset_check.py` verifies a video session by decoding every access unit
  alone and matching it to its index row (stage 1 proved the decoders agree bit for bit; the
  shipped file's sha256 guards its bytes).
- **`RECORDER_VERSION` 7.** The study pins that read recordings (map_labels.check_recording,
  detector_vs_packets.SESSION_VERSIONS) take v7 and both formats; a v8 is refused until read.

## Implementation (2026-11-09, branch feat/recording-stage3)
- `packages/poring_dataset/src/poring_dataset/frames.py` (new): the API of decision 5.
- `scripts/record_session.py`: the default format on rdp, the video-only loop, the manifest, the
  fail rules of decision 6, `--resume` for the video format.
- `scripts/media_rec.py`: the index's PNG-record columns; `check` refuses a video-only session (it
  grades a video against its PNG twin).
- The readers of decision 5 switched; the studies of decision 4 refuse; `dataset_check.py` checks
  video sessions.
- Tests: `packages/poring_dataset/tests/test_frames.py`, `services/backend/tests/
  test_video_readers.py`, the video-only end-to-end tests in `test_media_rec.py` (the real
  `mediarec.sh`, a CPU stand-in encoder), a video-only ship in `test_dataset_ship.py`.
- Live verification: the parent's, after the merge (gpu-recording.md 9.4).
