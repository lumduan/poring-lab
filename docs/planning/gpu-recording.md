---
doc_type: design
hypothesis: "Recording the RDP path's GAME_REGION frames with the Arc A380's hardware video encoder (VA-API, low-power VDEnc) instead of today's 1-fps lossless PNG cuts the recorder's CPU per frame and the bytes per hour by a large factor, makes 5-10 fps recordings fit bot-server's disk, and keeps what the frames are used for (detector boxes, UI text, colour cues) within pre-registered bars against the PNG originals."
status: "PROPOSED 2026-11-08. Round 3 (20:43-21:42 ICT): VALID, CANDIDATE vpp-hevc444-10-q20 (GPU conversion to 10-bit 4:4:4, HEVC CQP 20 all-intra): 8.7 ms CPU a frame, 0.15-0.21 x PNG, PSNR 44.3 / 40.4 dB, boxes 166 / 166, every bar PASS (section 8.4). Rounds 1-2: no candidate (S2; Q3, diagnosed in 8.3). STAGE 2 (one side-by-side recording, PNG + the candidate through a contained sidecar fed by one RAM pipe) BUILT and PRE-REGISTERED 2026-11-08 22:46:20 ICT (section 9.1), NOT RUN. Adoption needs Batt's decision and an ADR-0010 amendment (section 3). Stage 2 (2026-11-09 05:00-05:33): the side-by-side recording beside p20 checked -- VERDICT PASS on every bar (9.3): video 0.84 vs PNG 5.69 GB/h at 1 fps, 18.3 vs 136.1 ms CPU a frame, no detector latency cost. STAGE 3 DECIDED by Batt 2026-11-09 ~06:3x (ADR-0024) and BUILT on feat/recording-stage3 (9.4): rdp records video-only by default, one reader API (poring_dataset.frames); live verification pending."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../adr/0024-gpu-video-recordings.md, ../../packages/poring_dataset/src/poring_dataset/frames.py, ../../scripts/media_rec.py, ../../services/media-probe/mediarec.sh, ../adr/0010-dataset-format.md, bot-server-migration.md, ../benchmarks/h264-vs-png.md, ../benchmarks/v0-png-vs-jpeg.md, ../adr/0005-vision-x-access.md, ../adr/0019-windows-stays-clean.md, ../adr/0022-vendor-neutral-accelerators.md, ../../scripts/gpu_rec_bench.py, ../../services/media-probe/recbench.sh, ../../scripts/record_session.py, ../records/scorers/gpu_rec_r1_fingerprint.py, ../records/scorers/gpu_rec_r2_ssim_sim.py]
next_action: "Stage 3 BUILT (9.4, ADR-0024): the parent's live checks after the merge -- one short video-only recording beside a pilot, dataset_check.py on it, then each switched reader on stage 2's p20 with PORING_FRAME_SOURCE=png and =video, outputs compared (9.4's list)."
title: "A hardware-encoded (VA-API) recording path: design and a pre-registered bench"
date: 2026-11-08
owner: Batt
---

# A hardware-encoded (VA-API) recording path (design, 2026-11-08)

## 0. Batt's request, and what this phase is
- **Batt, 2026-11-08** (after the VA-API probe, bot-server-migration.md section 18): "interested,
  and it is probably the faster way too". Design a recording path on the Arc's hardware encoder
  instead of 1-fps lossless PNG, and a bench that proves or disproves it on REAL lab frames.
- **Phase 1 (this commit):** the design and the bench tool. Nothing ran on the GPU: the parent is
  profiling the live detector on the Arc, and a media-engine load now would confound it.
- **Phase 2 (later, the parent's "GPU free"):** section 7's commands, then section 8.
- Scope: the RDP path (`record_session.py --backend rdp`, PNG today). The console (S2) path
  already records Sunshine's own H.264 bitstream (ADR-0010 note 2026-10-04) and is unchanged.

### 0a. The recommendation at a glance
1. **Run the bench (stage 1).** It costs one guarded one-shot container (~10 min on a free Arc) and
   ~20-30 min of host CPU to score.
2. **What it should make faster** (each number "to measure", section 4):
   - the recorder's CPU per frame: PNG costs ~235-250 ms of CPU a frame (measured on VM 103,
     h264-vs-png P1/P3); the probe's VA-API encode costs ~3 ms (synthetic frames);
   - bytes per hour, and so shipping time and disk headroom: PNG is 5.5-8.3 GB/h at 1 fps;
   - and so 5-10 fps recordings, which PNG cannot afford on bot-server (20 GB unshipped cap:
     14-22 min at 10 fps).
3. **What it will NOT make faster: training.** Section 17b: at `--workers 2` the data pipeline no
   longer limits (1.36 s an iteration whatever the decode). Training reads the frame cache, whose
   format is a separate decision.
4. **It cannot be lossless** (section 3): VDEnc has no lossless mode that ffmpeg can ask for, and
   the BGR -> YUV conversion rounds by itself. So it needs **an ADR-0010 amendment, Batt's
   decision**. There are precedents: console sessions are Sunshine's lossy H.264 (2026-10-04), and
   training caches are JPEG q95 (2026-10-09).
5. **The arm the evidence should favour:** HEVC 4:4:4 all-intra, if the A380's VDEnc offers it
   (UI text and 1-px coloured lines survive 4:4:4); else HEVC 4:2:0 all-intra. The bench decides by
   a fixed rule (section 6.5), not by taste.
6. **Placement:** a contained encoder SIDECAR (the media-probe image) fed by the host recorder.
   No render node in the backend (the input writer, rule 3), no media packages on the host.
7. **PNG stays** for every study that fits a pixel threshold or a template (Miss cue, target items,
   MVP watch, UI templates) until that tool passes its own parity on decoded frames.

## 1. What is already known (read, not re-measured)
| fact | source |
|---|---|
| The Arc's VA-API: iHD 26.1.2, VA-API 1.23, ffmpeg 8.0.1; encode H.264 / HEVC / VP9 / AV1 by **low-power VDEnc only** (EncSliceLP), plus JPEG; decode H.264, HEVC (8-12 bit, 4:2:0 / 4:2:2 / 4:4:4), VP9, AV1, JPEG | bot-server-migration.md 18 |
| VA-API encode ~3 CPU ms a frame, 400+ fps; PSNR at 6 Mbit/s better than the CPU encoders (H.264 46.5 vs x264 44.3; HEVC 47.0; AV1 47.4); measured on a synthetic 1440x900 clip, NV12 already in RAM | idem |
| The VA-API JPEG path has a colour-range defect (washed out). ➡️ Its likely cause, unknown primaries giving the driver's BT.601-limited default, is in 8.1 | idem |
| The probe service `media-probe`: profile probe, network none, read-only, cap_drop ALL, renderD128 only, 2g, 4 CPUs; its image `poring-lab/media-probe:local` is kept (ID `312dfd87b5c3` on 2026-11-08) | compose.yaml, test_guards |
| The RDP recorder runs ON THE HOST: the backend grabs GAME_REGION (`ro_agent.Screen`, a `docker exec -i` pipe of raw BGRA), the host process skips unchanged frames, encodes PNG (`shards.encode_png`: filter 0 on every row, zlib level 1) and writes tar shards to `~/poring-lab-rec` | record_session.py, shards.py, ro_agent.py |
| PNG per frame (NAS manifests, 1280 x 720): xmas02-x2 (xmas_dun02) 1,536,518 B; rogue-c1 (gef_fild10) 2,308,854 B; ow1 2,257,611 B; 25 RDP sessions 10-25..29 7.0-8.4 GB/h at 1 fps | the manifests, ADR-0010 amendment 2026-11-05 |
| The recorder process at 1 fps PNG: 0.235 cores; at 3 fps 0.758 (VM 103) -> ~235-253 ms of CPU a frame. The backend's grab: 0.107 cores at 1 fps | h264-vs-png.md (P1, P3) |
| Console H.264 (Sunshine, every frame, IDR 1 s): ~2.5 GB/h | ADR-0010 note 2026-10-04 |
| Training reads the FRAME CACHE (build_frame_cache.py, host, one sequential pass per session), JPEG q95 by default since Batt 2026-10-09 (no detection gain for PNG's ~5x size); xmas02-o3h-t was built as PNG | v0-png-vs-jpeg.md, the cache manifest |
| Training on the Arc: 1.86 s an iteration at `--workers 0`, **1.36 s at 2 = 4**; past 2 the data pipeline no longer limits | bot-server-migration.md 17b |
| bot-server's root disk: 122.2 GB, 81.8 GB free (`df -B1`, 2026-11-08 16:16 ICT); floor 30 GB; 20 GB unshipped cap | ADR-0010 amendment 2026-11-08 |

## 2. Where the encoder runs, and how frames reach it (question 1)
Today's data path, RDP: `backend (X grab) --docker exec pipe, raw BGRA--> host recorder (PNG) -->
~/poring-lab-rec`. The frames already reach a host process, so the encoder can be fed there
without touching the backend.

| | A. encoder SIDECAR (recommended) | B. the host itself | C. the backend | D. the desktop |
|---|---|---|---|---|
| data path | backend -> host recorder (as today) -> raw frames to ffmpeg in a sidecar -> bitstream back to the recorder, which writes the session | backend -> host recorder -> ffmpeg (host) or PyAV `hevc_qsv` in-process | encode right after the grab; only the bitstream crosses the pipe | encode beside xfreerdp |
| who holds the render node | the sidecar only (a second GPU tenant beside the vision worker) | the host recorder (user bot is already in `render`) | the input writer | the RDP client's container |
| media stack | the media-probe image: pinned base digest, iHD 26.1.2, ffmpeg 8.0.1 | host packages (iHD, libva, ffmpeg; or Intel's VPL GPU runtime for PyAV's `hevc_qsv`/`h264_qsv` -- PyAV 19.0.1 has QSV and no `*_vaapi`): outside any pinned image, moved by Ubuntu updates | a backend image rebuild with iHD + ffmpeg | a desktop image rebuild |
| rule 3 (one input writer) | unaffected: no X, no `s2-input`, no network, no mux | unaffected | **cost**: a large GPU driver and media stack inside the input writer; a GPU hang stalls it | n/a |
| rule 2 (one display path) | unaffected | unaffected | unaffected | **cost**: the display path's own container |
| rule 5 (limits) | mem == memswap, oom_score_adj 500, a CPU cap, pinned by test_guards. GPU: VDEnc is a fixed-function engine apart from the EUs the detector uses, but memory bandwidth and power are shared: stage 2 measures the detector's latency with the encoder running | host processes have no cgroup limit unless we add one | the backend's limits now cover a media stack | |
| rule 7 (RAM / disk) | no writable path at all if the data goes over stdin/stdout; or one RAM FIFO directory. The session is written by the host recorder to `~/poring-lab-rec`, sequential files, as today | as today | as today | |
| rule 8 / ADR-0005 | not vision; no X, no clipboard / transfer, no detect socket, no `agent` network; it sees only the game-region pixels the recorder already holds | the same pixels | the backend already sees them | |
| ADR-0010 | **an amendment** (the format; section 3) | idem | idem | idem |
| ADR-0019 | nothing on Windows | idem | idem | idem |
| ADR-0022 (host profiles) | dedicated-intel only; VM 103 (NVIDIA) would need NVENC: out of scope | idem | idem | |
| extra CPU in the data path | a second hop of raw frames (2.76-3.7 MB a frame: ~110 MB/s at 30 fps). Over `docker exec` stdio the daemon relays every byte; FIFOs in a RAM directory bound into the sidecar avoid the daemon. **Stage 2 measures both** | none | none (the bitstream is small) | |

- **Recommended: A.** It keeps every isolation property the lab has and reuses an image that is
  already built and pinned. Its one cost, the second raw-frame hop, is measured in stage 2, where B
  is the fallback if the hop proves expensive (Batt's call: B puts unpinned packages on the host).
- **C is not recommended.** Section 18 already refused the render node in the backend for the
  console JPEG (~0.07 cores saved). Its one real advantage, sparing the backend -> host pipe the
  raw frames, matters only at high fps. That is stage 5's question, measured with the grab path.
- How the sidecar would run (stage 2, not built): an idle container started by a guarded step,
  like the vision worker (`sleep infinity`), and `docker exec -i` (control) per session. Never
  `docker compose run` from the recorder: the hook and rule 5 send every start through
  guarded_build.
  ➡️ **SUPERSEDED by 9.1 (stage 2, built 2026-11-08):** the idle sidecar started by a guarded step
  stands, but frames reach it through ONE named pipe in a RAM directory, not `docker exec -i`
  (9.1's table says why), so only the pipe is measured, not "both" as the table row above says.

## 3. Lossless or lossy (question 2)
- **Lossless is not available on this path.**
  - Encode is low-power VDEnc only (section 1).
  - `h264_vaapi`: no High 4:4:4 Predictive, so no transform-bypass lossless.
  - `hevc_vaapi`: no transquant-bypass option; its `-qp` runs 1..52 (0 means "unset").
  - `av1_vaapi` has no `-qp`. Its quality is `-global_quality` (the base q index), and 0 means
    "unset" to ffmpeg's vaapi_encode, so AV1's lossless mode cannot even be requested.
  - These are ffmpeg 8's vaapi_encode as we know it. Phase 2 saves the image's own
    `ffmpeg -h encoder=...` (`help-*.txt`) to confirm. The two exploratory arms (`x-hevc444-q1`,
    `x-av1-g1`) show the best quality the hardware path gives.
- **The colour conversion is lossy by itself.**
  - BGR -> 8-bit YUV -> BGR rounds, even at 4:4:4 (about +/-1 per channel).
  - True lossless for RGB needs RGB coding: PNG, FFV1, libx264rgb, all CPU encoders.
  - The control arm `ctl-yuv444` measures this floor (bar V1). Any YUV codec, however good, sits
    below it.
- ⇒ **ADR-0010's "lossless" cannot hold for a session recorded this way.** Adopting it is an
  ADR-0010 amendment or a new ADR: **Batt's decision.** Nothing in this design changes ADR-0010.
  - The lab has accepted loss twice already: console sessions record Sunshine's H.264 (Batt
    2026-10-04, C4), and training caches are JPEG q95 (Batt 2026-10-09, after a matched rerun
    showed no detection loss).
  - The bars (section 6) are therefore set **relative to JPEG q95, the lossy input Batt already
    accepted for training**, plus absolute floors.
- **4:4:4 or 4:2:0.**
  - 4:2:0 halves the chroma resolution both ways. Luma edges survive; thin coloured features do
    not: they lose saturation and bleed into their neighbours.
  - In RO that means:
    - the no-entry cue, a pure-red ring (G, B <= ~18) of 1-2 px on a fixed r18 circle;
    - red and yellow damage numbers, coloured chat text, the minimap's dots;
    - 1-px coloured UI borders, the cursor's red pixels, the walk marker's green.
  - The lab's own pixel cues are colour thresholds on exactly such features, so 4:4:4 matters
    wherever frames feed a cue. The bench measures it with a saturated-colour keep rate (Q6) and
    the UI crops (Q4, Q5).
  - **HEVC Main 4:4:4 8-bit** encode exists on Gen12+ VDEnc in Intel's media driver. Whether
    `vainfo` lists `VAProfileHEVCMain444 : VAEntrypointEncSliceLP` on this A380 is checked in phase
    2 (`vainfo.txt`). The 4:4:4 arms report "unavailable" otherwise.
  - H.264 and AV1 VDEnc are 4:2:0 only (AV1 Main profile).
- **All-intra or a GOP.**
  - **All-intra** (`-g 1`, every frame an IDR) has four properties:
    - every frame decodes alone (bar D1);
    - a damaged frame costs only itself;
    - the size per frame does not depend on fps or motion;
    - a session keeps the PNG shards' meaning: one record, one picture.
  - Random access matters for the tools that read chosen frames: qa_export, gold_eval, the
    labelling tools, m4_validate, recorder_boxes. The cache builder reads sequentially anyway.
    H264Session's seek at IDR 1 s costs ~100-300 ms a frame (h264-vs-png).
  - **A GOP** is smaller at high fps, but its cost per frame follows the motion.
  - Recommendation: all-intra at 1-5 fps. A GOP only if all-intra's GB/h at >= 10 fps is too high.
    The bench's motion clips estimate it (`*-g30` arms).

## 4. What it buys (question 3)
**GB per hour** (decimal GB; all-intra size per frame does not depend on fps):

| | 1 fps | 5 fps | 10 fps | 30 fps |
|---|---|---|---|---|
| PNG today (1.54-2.31 MB a frame, the manifests) | 5.5-8.3 | 27.7-41.6 | 55.3-83.1 | 166-249 |
| an all-intra arm, B bytes a frame | B x 0.0036 | B x 0.018 | B x 0.036 | B x 0.108 |
| a GOP arm | from the ref samples (`-g 30` = an IDR every 30 s) | the 5-fps motion clip | the 10-fps clip | the 30-fps clip |
| console H.264 (Sunshine, for scale) | -- | -- | -- | ~2.5 (every frame, IDR 1 s) |

(B in MB; `gpu_rec_bench.rates` computes the table from the run.)

- **On bot-server's disk** (81.8 GB free, a 30 GB floor, a 20 GB unshipped cap), PNG's unshipped
  cap fills in 2.4-3.6 h at 1 fps and in 14-22 min at 10 fps. An arm at, say, a quarter of PNG's
  size (bar S1's limit) gives four times those.
- **CPU per frame.**
  - PNG: ~235-253 ms of the recorder process a frame on VM 103 (h264-vs-png: grab copy, the
    unchanged check, `encode_png`, the tar write). That is 2.4 cores at 10 fps.
  - VA-API: ~3 ms for the encode alone (section 18, synthetic NV12), plus the BGRA -> YUV
    conversion, plus the hop to the sidecar.
  - The bench times the container side from raw BGRA in RAM (S2, S3) and `encode_png` on the host
    on the same frames. Stage 2 times the whole recorder (its CpuMeter).
- **Shipping:** `dataset_ship` time follows the bytes: rsync at ~41 MB/s (`--bwlimit 40000`) plus
  the local and NAS sha256 passes. It shrinks by exactly the size ratio.
- **Training-side decode.**
  - Training on the Arc is NOT decode-bound any more (17b: 2 workers = 4 workers = 1.36 s an
    iteration; the step itself is ~0.8 s + a 0.5 s forward/backward).
  - The trainer reads the frame cache, not the sessions. A recording format change leaves the
    cache format (JPEG q95 / PNG) as it is.
  - **So training gets no faster.** A video frame cache with VA-API decode in the trainer is a
    separate idea with no measured benefit today; not proposed.
  - The cache BUILD (host, one pass per session) would decode HEVC on the CPU instead of inflating
    PNG. The bench reports both per frame (`host_sw_ms` + `host_bgr_ms` vs `repo_decode_ms` /
    `pil_decode_ms`), plus the container's VA-API and software decode (`dec_va_*`, `dec_sw_*`).
- **Which "faster" this is:**

  | "faster" | does the design deliver it? |
  |---|---|
  | recording CPU per frame | yes, expected by a large factor: to measure (S2) |
  | disk bytes, shipping time | yes, by the size ratio: to measure (S1) |
  | higher fps recordings | yes, as a consequence of the two above; the grab path's own cost at 10 fps is stage 5's |
  | training speed | **no** (17b) |
  | the cache build | unknown: reported, not graded (D3 numbers) |

## 5. What it risks (question 4)
| risk | who is affected | how it is checked | who decides |
|---|---|---|---|
| detector boxes move on decoded frames | the detector trained on, and run on, recordings (recorder_boxes, gold_eval) | bench P1-P3 against the PNG with the deployed CPU detector (`unit_detector.for_map`), relative to JPEG q95 (P2) | the bars |
| labels | **none**: labels are projected from packets, not pixels | -- | -- |
| train-on-decoded, run-on-live domain shift | the detector, through the cache | the JPEG q95 precedent (no loss); a second lossy generation through the cache's JPEG q95 is bar G1 | the bars, then Batt |
| cues FITTED from recordings and APPLIED live | miss_cue, target_items (colour templates), mvp_watch_study (crops), UI templates if cut from a recording | Q4-Q6 here; each tool's own parity before it may read decoded frames; until then they record PNG (`--format png` stays) | each tool's owner, Batt |
| scorers and judges that read pixels | `git grep`: `scripts/*_judge.py`, `scripts/*_score.py` and `docs/records/scorers/` read packets and events; `npc_click_score` reads its own talk-cal PNGs, not session shards | none needed; re-check when a scorer starts reading shards | -- |
| the session readers | build_frame_cache, qa_export, gold_eval, m4_validate (all branch on `manifest["format"]` between h264 and png), recorder_boxes (+ truth_draw), cursor_unknown, label_quality, labels_v2, map_labels, miss_cue, mvp_watch_study, target_items | each needs the new format's reader (stage 4), one consumer at a time | stage 4 |
| determinism / hash checks | `dataset_check.py` compares H.264 sessions with the live client's checksums; a PNG session has nothing to check | HEVC / AV1 / H.264 decoding is bit-exact by the standards for conformant decoders: bar D2 checks VA-API = software decoder = the host's pinned PyAV on every frame. A new session format would store per-frame YUV md5s (at ship time or offline), with the BGR conversion pinned (BT.709, full range) | the bars, then stage 4 |
| ADR-0010's "lossless" | every reader that assumes it | -- | **Batt: an ADR-0010 amendment or a new ADR** |
| the encoder and the live detector share the Arc | the bot's detection latency | stage 2: the detect server's p50 / p95 with the encoder running vs without | stage 2's bar |
| an encoder failure mid-session | that session | the recorder stops with a `stop_reason` (fail closed), never a silent PNG fallback. ➡️ That is the rule for a video-ONLY recording (stage 3 on). In stage 2 (9.1) the PNG is always recorded and is the reference: the video side's failure ends the video only and is recorded in the manifest, never silently | stage 2's code |
| the colour convention itself (range / matrix mix-ups, like the VA JPEG defect) | every number | bar V1 (`ctl-yuv444`) and the `vpp-hevc420-q20` arm (the GPU's own conversion) | V1 voids the run |

## 6. The bench, PRE-REGISTERED (2026-11-08 16:29:19 ICT, the commit that adds this doc; before any number)
### 6.1 Inputs (real lab frames, the NAS read-only)
| sample | session | what | frames |
|---|---|---|---|
| `xmas_dun02` | `20261105T225409-rdp-xmas02-x2` (1,320 frames) | indoor dungeon, the chat window standard in force | 2 runs x 50 contiguous frames |
| `gef_fild10` | `20261026T120547-rdp-rogue-c1` (560 frames) | outdoor field, textured, the worst case for size | 2 runs x 50 contiguous frames |
| `motion30` / `motion10` / `motion5` | `20261004T130548-console-p3-outdoor-a` (S2, prt_fild08) | 150 consecutive 30-fps frames from 300 s in, each verified against the live checksum; 10 / 5 fps = every 3rd / 6th (hard links) | 150 / 50 / 25, **SIZE ONLY** (the source is already lossy H.264) |

- No prt_fild08 RDP PNG session exists on the NAS (the RDP PNG sessions are pay_fild07,
  gef_fild10 and xmas_dun02). gef_fild10 is the outdoor sample.
- Runs start at `round((k + 0.5) * F / runs) - 25` (`run_starts`): xmas02 frames 305 and 965,
  rogue-c1 115 and 395. The PNG bytes are copied verbatim, never re-encoded.
- RAM: about 0.7 GB in, at most 1.2 GB out (the container stops encoding past it). The sample step
  refuses beyond rule 7's limits.

### 6.2 The arms
Every encode is VA-API low-power from the PNGs. The colour conversion: swscale BGR -> YUV, BT.709,
full range, the stream tagged so; the host inverts it the same way (`COLOR`). Each run is its own
stream.

| arm | mode | what |
|---|---|---|
| `ctl-yuv444` | control | BGR -> YUV 4:4:4 -> raw, 10 frames a run: the colour round trip alone (V1) |
| `ctl-yuv420` | control | the same at 4:2:0: the floor of every 4:2:0 arm (reported) |
| `hevc420-q14`, `hevc420-q20`, `hevc420-q26` | intra | HEVC Main, CQP 14 / 20 / 26, every frame an IDR (`-g 1 -bf 0`), AUDs |
| `hevc444-q14`, `hevc444-q20`, `hevc444-q26` | intra | HEVC RExt 4:4:4 (upload vuyx, else vuya), CQP 14 / 20 / 26 |
| `h264-420-q20` | intra | H.264 High, CQP 20 |
| `av1-420-g40`, `av1-420-g80` | intra | AV1, CQP base q index 40 / 80 |
| `vpp-hevc420-q20` | intra, GPU conversion | as `hevc420-q20`, with the BGRA -> NV12 conversion on the GPU (`scale_vaapi`, BT.709 full) |
| `hevc420-q20-g30`, `hevc444-q20-g30`, `h264-420-q20-g30` | GOP | an IDR every 30 frames, no B-frames; on the ref samples and the motion clips |
| `x-hevc444-q1`, `x-av1-g1` | exploratory | the lowest quantiser ffmpeg can ask for, 10 frames a run; reported, never graded |
| `ref-jpeg95` | reference (host) | the training cache's own encoder, `build_frame_cache.jpeg(q=95)` |

`hevc420-q20` also runs on the motion clips (intra vs GOP at the same rate). An arm whose
`vainfo` profile is missing reports "unavailable".

### 6.3 Measures (the host's pinned PyAV, software decode, one thread; per frame, then per arm and sample)
- **quality** against the PNG original:
  - PSNR over every pixel and channel (capped at 100); SSIM of BT.601 luma (8 x 8 uniform window,
    stride 1);
  - PSNR per UI crop: `basic_info` (0, 0, 220, 140), `chat` (0, 600, 600, 120), `minimap`
    (1138, 21, 124, 120). A crop that shows the world in some session is still graded;
  - the largest absolute error;
  - the **saturated-colour keep rate**: of the PNG pixels clearly saturated in one channel (it
    >= 144, the other two <= 16), the share still saturated after decoding (>= 128, others <= 32);
  - **gen2**: PSNR of `jpeg95(decoded)` against the PNG.
- **detector parity:**
  - the deployed CPU detector per map: `for_map("xmas_dun02")` = xmas02, `for_map("gef_fild10")`
    = v1;
  - PNG boxes vs decoded boxes, one-to-one at IoU >= 0.7, same class and species
    (`gpu_live_parity.match_same_class`);
  - matched / PNG boxes, matched / decoded boxes; the matched pairs' largest coordinate difference
    (median, p95).
- **D1:** each access unit decoded by a fresh decoder gives the same YUV planes (md5) as the
  sequential decode.
- **D2:** the container's VA-API decode, its software decode (`-f framemd5`, the planar format)
  and the host's PyAV agree on every frame.
- **size:** bytes per frame (all packets, headers included), IDR and inter sizes for the GOP arms;
  GB/h by `rates`.
- **CPU:**
  - in the container: `-benchmark` utime + stime per frame over 600 frames (the first ref
    sample's first 30 frames as raw BGRA in RAM, looped: `gef_fild10`, the outdoor one, by name
    order), conversion included; the conversion alone and the raw read as baselines; VA and
    software decode the same way;
  - on the host: `encode_png` (level 1, the recorder's), PIL's PNG decode (the trainer's
    `cv2.imdecode` stand-in), the repo's `decode_png` (the cache builder's), PyAV decode + BGR
    conversion.

### 6.4 The bars
Each bar is evaluated per ref sample, on every graded arm (intra, vpp, gop). The values live in
`gpu_rec_bench.BARS`, and a test keeps this table and the code equal.

| bar | key | what | value |
|---|---|---|---|
| V1 | `V1_psnr` | VALIDITY: `ctl-yuv444`'s mean game PSNR on every ref sample is at least (else the colour handling is not what the bench assumes, and nothing else is judged) | 45.0 |
| V1 | `V1_maxabs` | ... and its largest absolute error at most | 4.0 |
| Q1 | `Q1_psnr_vs_jpeg` | mean game PSNR >= `ref-jpeg95`'s on the same frames plus | 0.0 |
| Q2 | `Q2_psnr_min` | the worst frame's game PSNR, dB, at least | 36.0 |
| Q3 | `Q3_ssim_vs_jpeg` | mean luma SSIM >= `ref-jpeg95`'s plus | -0.002 |
| Q3 | `Q3_ssim_min` | ... and the worst frame's SSIM at least | 0.97 |
| Q4 | `Q4_crop_vs_jpeg` | every UI crop's mean PSNR minus `ref-jpeg95`'s, at least | -0.5 |
| Q5 | `Q5_crop_min` | every UI crop's worst frame PSNR, dB, at least | 32.0 |
| Q6 | `Q6_sat_keep` | the saturated-colour keep rate at least | 0.95 |
| Q6 | `Q6_min_pixels` | ... graded only with at least this many saturated core pixels in the sample (else NA) | 1000 |
| G1 | `G1_gen2` | gen2 mean PSNR minus `ref-jpeg95`'s mean PSNR, at least | -1.0 |
| P1 | `P1_of` | matched / PNG boxes and matched / decoded boxes, each at least | 0.97 |
| P | `P_min_boxes` | P1-P3 graded only with at least this many PNG boxes in the sample (else NA: underpowered) | 100 |
| P2 | `P2_vs_jpeg` | both fractions >= `ref-jpeg95`'s plus | -0.01 |
| P3 | `P3_coord_med` | the matched pairs' median largest coordinate difference, px, at most | 1.0 |
| P3 | `P3_coord_p95` | ... and its p95, px, at most | 3.0 |
| D1 | -- | intra / vpp: every frame decodes alone to the same planes | every frame |
| D2 | -- | intra / vpp: VA-API = software = host, every frame | every frame |
| S1 | `S1_size_ratio` | bytes per frame <= this x the PNG's, every ref sample | 0.25 |
| S2 | `S2_cpu_ms` | intra / vpp: the container's CPU ms per encoded frame (raw BGRA in RAM, conversion included) at most | 15.0 |
| S2 | `S2_png_ratio` | ... and at most this x the host's `encode_png` on the same frames | 0.1 |
| S3 | `S3_fps` | intra / vpp: the encode's frames a second, at least | 60.0 |

- **How V1's values were set (before any bench number).** The host-side end-to-end test
  (`test_sample_then_score_end_to_end`) round-trips a SYNTHETIC 1280 x 720 frame through 8-bit
  BT.709 full-range 4:4:4 with swscale (PyAV) and gets 48.7 dB with a largest error of 2. That
  is the rounding floor of any YUV path; the ideal-rounding figure is ~52.8 dB. A first draft's
  50 dB would have voided a correct run, so V1 is 45 dB / 4. A range or matrix mix-up errs by
  more than 10 on saturated colours (the test's limited-range case), far below either value. This
  is a check of the tool on made-up pixels, not a measurement of the hypothesis.

### 6.5 The decision rule
1. **V1 first.** If it fails on any ref sample, the run is INVALID: no verdict. The cause is found
   and the bench re-run, with an amendment here written before the re-run.
2. An arm PASSES when no bar FAILS on any ref sample, P1-P3 are powered (not NA) on at least one
   sample, and S2 / S3 were measured.
3. **The CANDIDATE** is the passing intra / vpp arm with the smallest mean bytes per frame over the
   ref samples (`gpu_rec_bench.verdict`). The GOP arms are graded and reported, but they are not
   candidates in this stage (section 3: all-intra first).
4. No candidate means no adoption. The report names the closest arm's failing bars.
5. **No re-tuning after seeing numbers.** A new arm, or a changed bar, needs an amendment here
   (timestamped from `date`) BEFORE its run.
   - The one exception: an arm that fails to RUN, or a decoder check that cannot run, because an
     option or format name is wrong for this ffmpeg may be re-run once with the corrected name,
     written here first. Its bars do not change.
6. The verdict says what the hardware path CAN do. Adopting it is stage 2 onwards, and Batt's.

### 6.6 AMENDMENT: round 2, the GPU conversion with the right colours (PRE-REGISTERED 2026-11-08 18:35:58 ICT, before any round-2 run)
**Batt, 2026-11-08 ~18:0x:** "try fixing the colours too". Written after round 1 (section 8) and
its diagnosis (8.1), and before round 2 runs. **The bars (6.4) and the decision rule (6.5) do not
change.** This amendment adds arms, two notes on method, and two reports.

**Round 2's arms** (`gpu_rec_bench.ROUNDS[2]`, in the container's order; `sample --round 2`):

| arm | mode | what | why it is in |
|---|---|---|---|
| `ctl-yuv444` | control | as round 1 | V1 (validity), and the swscale twin of the 4:4:4 GPU controls |
| `ctl-yuv420` | control | as round 1 | the swscale twin of the 4:2:0 GPU controls |
| `gctl-vpp420-r1` | GPU control | BGRA -> `scale_vaapi=out_color_matrix=bt709:out_range=full:format=nv12` (round 1's exact options) -> downloaded raw, 10 frames a run | the defect's positive case: the fingerprint must see it |
| `gctl-vpp420` | GPU control | the same plus `out_color_primaries=bt709:out_color_transfer=bt709` | the fix alone: only the primaries and the transfer differ from the row above |
| `gctl-vpp444` | GPU control | the fix, to 8-bit 4:4:4 (`vuyx`, else `vuya`) | the candidate's conversion, without the encoder |
| `gctl-vpp444-tv` | GPU control | the fix with `out_range=limited`, DECLARED limited | is the limited range honoured? (the fallback candidate's conversion) |
| `hevc444-q20` | intra | round 1's closest arm, unchanged | the reference, so round 2 stands on its own |
| `vpp-hevc444-q20` | vpp (candidate) | BGRA uploaded, the fix to 4:4:4 `vuyx` on the GPU, then exactly `hevc444-q20`'s encoder options | the target: hevc444-q20's quality without its 13.4 ms CPU conversion |
| `vpp-hevc444-q20-tv` | vpp (candidate) | the same at limited range (`out_range=limited`, tagged `-color_range tv`, inverted limited by the scorer) | the fallback if the driver honours only the limited range |

Considered and left out:
- **A GPU 4:2:0 encode arm.** Every 4:2:0 arm of round 1 failed Q2, Q5 and Q6, even the
  CPU-converted `hevc420-q14`. The 4:2:0 floor fails them by itself (`ctl-yuv420`: worst frame
  32.5 dB < 36, the chat crop 24.8 < 32, saturated keep 0.76 < 0.95). Right colours cannot change
  that. The 4:2:0 conversion's colours are still measured, as a control (`gctl-vpp420`).
- **Other QPs.** In round 1, q14 failed S1 on gef_fild10 and q26 failed Q2-Q4. QP 20 is the only
  one in range, and keeping hevc444-q20's options isolates the conversion.
- **RGB straight into the encoder.** vainfo lists `VA_RT_FORMAT_RGB32` for `VAProfileHEVCMain444 /
  VAEntrypointEncSliceLP`. Which conversion the driver would apply, and how ffmpeg would tag the
  stream, cannot be known offline. It is an idea for round 3.

**How each arm is graded and reported:**
- **The candidates and the reference:** 6.4's bars, unchanged, on every ref sample. 6.5's rule
  applies, with round 2's intra / vpp arms as the candidate set.
- **The GPU controls (`gctl`) are reported, never graded, and never void the run.** V1 stays the
  only validity bar. Each control reports (`gpu_rec_bench.controls_summary`):
  - its round trip against the PNG, inverted with its DECLARED convention: PSNR, largest error,
    saturated keep (read like V1);
  - **the luma fingerprint:** a least-squares fit Y = a_r R + a_g G + a_b B + c over the PNG's
    pixels and the Y plane the GPU wrote. It is NAMED as the nearest of BT.709 / BT.601 x full /
    limited when it lies within 3 levels (`FIT_NAMED_LEVELS`), else "none". A limited range shows
    as scale ~0.859 and offset ~16, BT.601 as a_r / scale ~0.3;
  - for the full-range ones: its Y / U / V planes against swscale's planes of the same frames
    (`ctl-yuv420` / `ctl-yuv444`, the same 10 frames a run).
- **The fingerprint's known-good case:** `ctl-yuv444` and `ctl-yuv420` get the same fit. On
  swscale's own conversions of test frames, every convention is named back within 1 level (the
  unit tests).
- **What the controls mean, decided now:**
  - `ctl-yuv444` and `ctl-yuv420` must be named `bt709-full`. Otherwise the fingerprint is not
    trusted and its names are not used; the numbers are still reported.
  - `gctl-vpp420-r1` is predicted to be `bt601-limited` (8.1). If it is named anything else, 8.1's
    inference is wrong and is recorded as such. The arms are graded either way.
  - If `gctl-vpp420` and `gctl-vpp444` are named `bt709-full`, and `gctl-vpp444-tv` is named
    `bt709-limited`, the mechanism (the primaries) is confirmed.
  - A candidate whose control is NOT named as declared is expected to fail Q1-Q6. It is reported
    with that cause.
- **What each stream says it is:** the VUI (range, matrix) as PyAV reads it, against the arm's
  declaration (`vui`, `vui_ok`). It is reported, not a bar; a stage-2 format would need it right.

**Two notes on method** (they apply to every round-2 arm, the reference included):
1. **The declared range.** An arm declares `color_range`: pc (full, round 1's `COLOR`) or tv
   (limited). The stream's `-color_range` tag and the scorer's inverse follow it; the matrix is
   BT.709 everywhere.
   - Every round-1 arm declares pc, so its commands and its numbers do not change
     (`test_round_1_is_the_original_table_unchanged`).
   - Round 1's own score gives the same verdict and rates with this code
     (`test_round_1_score_gives_the_same_verdict_and_rates_today`; run once against the score in the
     main checkout's `data/` before this amendment was stamped: PASS).
2. **S2 and S3 are graded on the MEDIAN of 3 timing passes,** run round-robin: pass 1 of every
   timed arm (with its decode timings), then pass 2 of each, then pass 3. Why:
   - round 1 timed each arm once, and its first timed arm paid a warm-up: `hevc420-q14` took
     26.9 ms, against 22.5 for `hevc420-q20` and 22.0 for `hevc420-q26` (stime 3.25 s vs 1.34 /
     1.33);
   - the target's margin is thin. S2's limit on xmas_dun02 is 0.1 x 91.05 = 9.1 ms, and round 1's
     `vpp-hevc420-q20` took 9.0 ms on the same upload + VPP path (4:2:0 out).
   - The bar's value, its unit and what is timed (600 raw BGRA frames in RAM, conversion
     included) do not change. Every pass is reported (`cpu_ms_passes`).
   - **Expected, not a bar:** `vpp-hevc444-q20` near 9 ms, so S2 can go either way on xmas_dun02.
     gef_fild10's limit is 15 ms.

**The outcomes, decided now:**
- V1 fails: the run is INVALID (6.5.1).
- A candidate passes: it is round 2's CANDIDATE (the smaller one if both pass). Adoption is still
  stage 2, and Batt's. A tv candidate would also need its range recorded in the session format
  (stage 4).
- No candidate: the report names the closest arm's failing bars. If S2 alone fails, that is a
  question about the bar, for Batt; it is not a reason to re-run.
- 6.5.5's one exception still holds. An arm that fails to RUN because an option or format name is
  wrong for this ffmpeg (`out_color_primaries`, `vuyx` for scale_vaapi) may be re-run once with
  the corrected name, written here first. A new evidence file, `help-scale_vaapi.txt`, saves the
  filter's own option list.

### 6.7 AMENDMENT: round 3, a GPU 4:4:4 path that keeps neutral grey (PRE-REGISTERED 2026-11-08 20:32:43 ICT, before any round-3 run)
**Batt, 2026-11-08 ~19:5x:** "try round 3": the GPU's scaling / processing step. Written after
round 2 (8.2) and its diagnosis (8.3), before round 3 runs. **The bars (6.4) and the decision rule
(6.5) do not change.** This amendment adds arms, reported measures and two notes on method.

**Why these arms (8.3):** round 2's GPU 4:4:4 conversion is NOT a filter. It writes the chroma of
neutral pixels one level low (127 / 127). Black then decodes as (0, 1, 0), and SSIM's dark windows
turn that into the Q3 failure on xmas_dun02. Its 4:2:0 path, with the same options, is nearly
exact. So round 3 asks: which GPU 4:4:4 path writes neutral grey at mid?
- Each new arm is round 2's path with ONE change. A test pins that
  (`test_round_3_changes_one_thing_per_arm_and_keeps_its_references`).
- Each change comes as a control (the conversion alone) AND a candidate (the same conversion
  into `vpp-hevc444-q20`'s encoder options), so a control that keeps grey can still give this
  round's candidate.

**Round 3's arms** (`gpu_rec_bench.ROUNDS[3]`, in the container's order; `sample --round 3`):

| arm | mode | what | why it is in |
|---|---|---|---|
| `ctl-yuv444` | control | as round 1 | V1 (validity); the swscale twin; the new measures' known-good case |
| `gctl-vpp444` | GPU control | round 2's, unchanged (scale_vaapi mode `hq`, ffmpeg's default; BGRA uploaded; VUYX out), 10 frames a run | the defect's positive case: the neutral measure must see it |
| `gctl-vpp444-fast` | GPU control | the same with `mode=fast` (scale_vaapi 256), 5 frames a run | the scaling mode may pick another VPP engine at 1:1, and engines round differently (8.3 row 3: the 4:2:0 output is nearly exact) |
| `gctl-vpp444-dflt` | GPU control | the same with `mode=default` (0: the driver's choice), 5 frames a run | idem |
| `gctl-vpp444-bgr0` | GPU control | the same, the frames uploaded as `bgr0` (BGRX: the same bytes, no alpha), 5 frames a run | an alpha-less input may take another conversion path |
| `gctl-vpp444-10` | GPU control | the same, to 10-bit 4:4:4 (`xv30`, VA's Y410), 5 frames a run | at 10 bits, a one-code error is a quarter of an 8-bit level, and black stays black. swscale's own 10-bit full-range conversion writes neutral chroma at 511 and still decodes black exactly (the round-3 end-to-end test's stand-in) |
| `hevc444-q20` | intra | round 1's, unchanged | the CPU-converted reference, so round 3 stands on its own |
| `vpp-hevc444-q20` | vpp (candidate) | round 2's, unchanged | round 2's closest arm, the reference |
| `vpp-hevc444-q20-fast` | vpp (candidate) | `vpp-hevc444-q20` with `mode=fast` | as its control |
| `vpp-hevc444-q20-dflt` | vpp (candidate) | `vpp-hevc444-q20` with `mode=default` | as its control |
| `vpp-hevc444-q20-bgr0` | vpp (candidate) | `vpp-hevc444-q20` uploading `bgr0` | as its control |
| `vpp-hevc444-10-q20` | vpp (candidate) | the 10-bit conversion into HEVC Main 4:4:4 10 (`VAProfileHEVCMain444_10`, EncSliceLP and VLD in round 2's vainfo), the same `-qp 20` | as its control. HEVC's QP_Y is the same step RELATIVE to the sample range at any bit depth (the decoder adds QpBdOffset), so QP 20 is the like-for-like quantiser |
| `gctl-vpp444-tv` | GPU control | round 2's, unchanged, LAST | 8.3 row 6's inference about the tv path's black, measured. The one arm the out cap may skip (below) |

Considered and left out:
- **"No scaling step":** in this ffmpeg, scale_vaapi is the only VA-API filter that converts
  colour (`help-scale_vaapi.txt`; the other VA-API filters keep the input format). At 1:1 it
  already does no scaling: round 2 WAS the conversion-only path. Its `mode` flag is the one
  scaling knob left, so it is in.
- **`nl_anamorphic`** (768): a non-linear scaler for aspect changes; meaningless at 1:1.
- **Chroma siting** (`out_chroma_location`): RGB in, 4:4:4 out, so no chroma sample is placed
  anywhere.
- **VUYA instead of VUYX out:** the same 8-bit layout with an alpha byte. Nothing points to another
  path, so it is left for a later round if every 8-bit variant keeps the fault.
- **RGB straight into the encoder** (6.6's idea): which conversion the driver would apply, and how
  ffmpeg would tag it, still cannot be known offline. Its output could not be told apart from a
  fault.
- **A lower QP, or the tv arm at another QP:** that tunes past the cause instead of removing it.
  The tv path's precision loss (8.3 row 6) is its own.
- **GPU 4:2:0:** nearly exact, but its floor fails Q2, Q5 and Q6 by itself (6.6).

**How each arm is graded and reported:**
- **The candidates and the reference:** 6.4's bars, unchanged, on every ref sample. 6.5's rule
  applies, with round 3's intra / vpp arms as the candidate set.
- **The controls are reported, never graded, and never void the run;** V1 stays the only validity
  bar. Since round 3 they also report (`controls_summary`; `score` prints them):
  - their own SSIM (mean, min). It was in round 2's score already, but nothing printed it;
  - SSIM split into DARK 8 x 8 windows (the PNG's luma mean < 16, `DARK_LUMA`) and the rest, and
    the dark share (`ssim_parts`);
  - `black_keep`: the share of pure-black PNG pixels decoded exactly black (`black_counts`);
  - `neutral` (4:4:4 only, `neutral_counts`), on the PNG's neutral pixels (B = G = R):
    - U's and V's mean error from mid, in 8-bit levels;
    - `uv_mid`: the share with both U and V within half an 8-bit level of mid (exactly 128 at 8
      bits; 511..513 at 10);
    - the same on black (`black_uv_mid`), and black's luma error from the range's black
      (`black_y_mean_err`: 0 full, 16 limited);
  - U and V against swscale's, beside Y.
- **Every graded arm also reports** its SSIM split dark / rest and its `black_keep` (`ssim`
  lines, `ssim_summary`). Reported, not a bar.
- **What the controls mean, decided now:**
  - `ctl-yuv444` must show `uv_mid` = 1.0 and `black_keep` = 1.0 on both samples. Otherwise the
    new measures are not trusted (their numbers are still reported).
  - `gctl-vpp444` is predicted (8.3) to show, on both samples:
    - `uv_mid` <= 0.5, with U's and V's mean errors near -1;
    - `black_keep` <= 0.5;
    - on xmas_dun02, `ssim_dark` below `ssim_rest`.
    If it does not, 8.3's inference is wrong and is recorded as such. The arms are graded either
    way.
  - A variant whose control has `uv_mid` >= 0.99 and `black_keep` >= 0.99 on both samples "keeps
    neutral grey". Its candidate is EXPECTED to pass Q3 on xmas_dun02. That is an expectation for
    the report, not a bar.
  - `gctl-vpp444-tv` is predicted to show `black_y_mean_err` < 0 and `black_keep` near 1 (8.3
    row 6: its black luma sits below 16 and is clipped).
  - A candidate whose control keeps grey and that still fails Q3 points at the encoder side (8.3
    row 7). It is recorded so; nothing is re-run for it.

**Two notes on method:**
1. **The new controls run on the first 5 frames of each run (`frames` 5),** round 2's controls on
   10. Why:
   - a 4:4:4 raw run of 10 frames is 36.9 MB, and round 3 at 10 would write ~1.4 GB into the
     container's /out against its 1.2 GB cap (`OUT_CAP`, rule 7). At 5 it writes ~1.12 GB;
   - the 5 are the first 5 of `gctl-vpp444`'s 10, so every control sees the same frames;
   - `gctl-vpp444-tv` runs last, because the cap skips whatever comes after it is reached. Only a
     10-bit stream far larger than its 8-bit twin would reach it.
2. **The BGRX arm's timing input is the same raw bytes DECLARED `bgr0`** (`-pix_fmt bgr0`), not
   converted. That is what the recorder would hand over: its grab is BGRA with the alpha unused.
   - Every other arm's timing is round 2's, unchanged (BGRA in), and so are round 2's arms'
     commands (`test_recbench_sh_round_3_uploads_as_declared_and_keeps_round_2s_commands`).
   - S2 / S3 are still the median of 3 passes, round-robin.

**The outcomes, decided now:**
- V1 fails: the run is INVALID (6.5.1).
- One or more candidates pass: the smallest is round 3's CANDIDATE (6.5.3). Adoption is still
  stage 2, and Batt's.
  - A 10-bit candidate would also need stage 4's readers to take 10-bit 4:4:4. PyAV decodes it in
    software (the unit tests), and VA-API lists the decode profile.
- No candidate: the report names the closest arm's failing bars, and what the controls say about
  the cause.
- 6.5.5's one exception still holds. An arm that fails to RUN because a name is wrong for this
  ffmpeg (`mode=fast` / `mode=default`, `bgr0`, `xv30` for scale_vaapi or hwdownload, the 10-bit
  `-profile:v rext`) may be re-run once with the corrected name, written here first.
  - A format the driver refuses is not a name error. It is reported as failed, and nothing is
    re-run.
- **Expected, not bars:** the container ~6 min (13 arms; round 2's 9 took 3 min); /out ~1.12 GB;
  `score` ~25 min of host CPU (6 graded arms with the detector; round 2's 3 took 12).

## 7. Phase 2: the exact commands (the parent runs them; nothing here ran in phase 1)
Preconditions:
- the GPU is free (no detect-server step, no training, no pilot on the Arc);
- no pilot needs the CPU during `score`: the detector uses 8 threads;
- `/dev/shm` has room for ~2 GB (`df -h /dev/shm`; the lab's total stays <= 4 GB).

**Step 0, the shell** (from the worktree, or the main checkout once this branch is merged):

```bash
TZ=Asia/Bangkok date; df -h /dev/shm
docker image ls poring-lab/media-probe --format '{{.ID}} {{.CreatedAt}}'  # 312dfd87b5c3 on 11-08
cd /dev/shm/poring-lab-wt/gpu-rec
ln -s /home/bot/docker/poring-lab/.env .env   # compose needs it; gitignored; removed in step 5
export PYTHONDONTWRITEBYTECODE=1 TMPDIR=/dev/shm/poring-lab-tmp
export PYTHONPATH=$PWD/scripts:$PWD/packages/poring_env/src:$PWD/packages/poring_dataset/src:$PWD/packages/poring_packets/src:$PWD/services/backend/src:$PWD/services/vision/src
```

**Step 1, sample the real frames** (host; the NAS read-only; refuses beyond rule 7):

```bash
systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 \
  /home/bot/docker/poring-lab/.venv/bin/python scripts/gpu_rec_bench.py sample \
    --session 20261105T225409-rdp-xmas02-x2:xmas_dun02 \
    --session 20261026T120547-rdp-rogue-c1:gef_fild10 \
    --motion 20261004T130548-console-p3-outdoor-a
df -h /dev/shm
```

**Step 2, the container** (guarded, one-shot, nothing built: the image exists). The start step
watches for its full time; then wait for the exit, read the log, and remove the container:

```bash
python3 scripts/guarded_build.py start:media-recbench@600
timeout 1800 docker wait poring-lab-media-recbench-1
docker logs poring-lab-media-recbench-1 2>&1 | tail -60
python3 scripts/guarded_build.py rm:media-recbench
tail -40 /dev/shm/poring-lab-recbench/out/results.txt
```

**Step 3, score** (host CPU, ~20-30 min with the CPU detector):

```bash
systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 \
  /home/bot/docker/poring-lab/.venv/bin/python scripts/gpu_rec_bench.py score \
    --out /home/bot/docker/poring-lab/data/bench/gpu-rec/20261108-recbench.json
```

**Step 4, record section 8:** the numbers, the capability answers from `vainfo.txt` /
`vainfo-all.txt` / `help-*.txt`, and the verdict; times from `TZ=Asia/Bangkok date`. Re-print the
verdict any time with `gpu_rec_bench.py verdict <json>`.

**Step 5, clean up the same day** (CLAUDE.md rule 7). Copy the small evidence (`out/*.txt`,
`out/*.tsv`, `out/md5/`) to the NAS scratch-archive if wanted, then:

```bash
rm /dev/shm/poring-lab-wt/gpu-rec/.env
rm -rf /dev/shm/poring-lab-recbench
```

### 7.2 Round 2: the exact commands (6.6; the parent runs them, nothing here ran in its phase 1)
Preconditions: as in section 7 (the GPU free; no pilot needing the CPU during `score`).
`/dev/shm` needs room for ~1.6 GB: ~0.36 GB in, at most 1.2 GB out, ~0.8 GB expected. Round 1's
root must be gone (`sample` refuses an existing one).

**Step 0, the shell.** Run it from the main checkout once `design/gpu-recording-r2` is merged.
From the worktree `/dev/shm/poring-lab-wt/gpu-rec2` instead, link the main `.env` in first, as in
section 7, and remove it in step 5.

```bash
TZ=Asia/Bangkok date; df -h /dev/shm
docker image ls poring-lab/media-probe --format '{{.ID}} {{.CreatedAt}}'  # 312dfd87b5c3 on 11-08
ls -d /dev/shm/poring-lab-recbench 2>/dev/null && echo "a previous root is there: rm -rf it first"
cd /home/bot/docker/poring-lab
export PYTHONDONTWRITEBYTECODE=1 TMPDIR=/dev/shm/poring-lab-tmp
export PYTHONPATH=$PWD/scripts:$PWD/packages/poring_env/src:$PWD/packages/poring_dataset/src:$PWD/packages/poring_packets/src:$PWD/services/backend/src:$PWD/services/vision/src
```

**Step 1, sample round 2.** The same sessions and runs as round 1; no motion clips, because round
2 has no GOP arm:

```bash
systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 \
  /home/bot/docker/poring-lab/.venv/bin/python scripts/gpu_rec_bench.py sample --round 2 \
    --session 20261105T225409-rdp-xmas02-x2:xmas_dun02 \
    --session 20261026T120547-rdp-rogue-c1:gef_fild10
cat /dev/shm/poring-lab-recbench/in/round /dev/shm/poring-lab-recbench/in/timing_reps  # 2 and 3
df -h /dev/shm
```

**Step 2, the container.** The same guarded one-shot as round 1, with nothing built. Round 1 took
8 min for 17 arms; round 2 has 9 arms and 3 timing passes.

```bash
python3 scripts/guarded_build.py start:media-recbench@600
timeout 1800 docker wait poring-lab-media-recbench-1
docker logs poring-lab-media-recbench-1 2>&1 | tail -60
python3 scripts/guarded_build.py rm:media-recbench
tail -40 /dev/shm/poring-lab-recbench/out/results.txt
grep -E 'gctl|vpp-hevc444' /dev/shm/poring-lab-recbench/out/status.tsv  # ok, or why not
```

**Step 3, score** (host CPU; the detector runs on 3 graded arms instead of round 1's 13, so expect
well under round 1's 26 min):

```bash
systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 \
  /home/bot/docker/poring-lab/.venv/bin/python scripts/gpu_rec_bench.py score \
    --out /home/bot/docker/poring-lab/data/bench/gpu-rec/$(TZ=Asia/Bangkok date +%Y%m%d)-recbench-r2.json
```

It prints the verdict, one `control` line per GPU control and sample (declared, PSNR, `fit`,
scale / offset, Y against swscale), and a `vui_mismatch` line for any stream whose VUI disagrees
with its declaration.

**Step 4, record section 8.2.** Record, with times from `TZ=Asia/Bangkok date`:
- the controls against 6.6's "what the controls mean": the known-good names first, then
  `gctl-vpp420-r1`'s;
- the graded arms' bars and the verdict;
- S2's three passes for each candidate;
- what `help-scale_vaapi.txt` and the status notes say about `vuyx`.

**Step 5, clean up the same day,** as in section 7. Copy `out/*.txt`, `out/*.tsv` and `out/md5/`
to the NAS `scratch-archive/<date>/recbench-r2/` if they are wanted, then
`rm -rf /dev/shm/poring-lab-recbench`.

### 7.3 Round 3: the exact commands (6.7; the parent runs them, nothing here ran in its phase 1)
Preconditions: as in section 7 (the GPU free; no pilot needing the CPU during `score`).
- `/dev/shm` needs room for ~1.6 GB: ~0.36 GB in, at most 1.2 GB out, ~1.12 GB expected.
- Round 2's root must be gone (`sample` refuses an existing one).

**Step 0, the shell.** Run it from the main checkout once `design/gpu-recording-r3` is merged.
From the worktree `/dev/shm/poring-lab-wt/gpu-rec3` instead, link the main `.env` in first, as in
section 7, and remove it in step 5.

```bash
TZ=Asia/Bangkok date; df -h /dev/shm
docker image ls poring-lab/media-probe --format '{{.ID}} {{.CreatedAt}}'  # 312dfd87b5c3 on 11-08
ls -d /dev/shm/poring-lab-recbench 2>/dev/null && echo "a previous root is there: rm -rf it first"
cd /home/bot/docker/poring-lab
export PYTHONDONTWRITEBYTECODE=1 TMPDIR=/dev/shm/poring-lab-tmp
export PYTHONPATH=$PWD/scripts:$PWD/packages/poring_env/src:$PWD/packages/poring_dataset/src:$PWD/packages/poring_packets/src:$PWD/services/backend/src:$PWD/services/vision/src
```

**Step 1, sample round 3.** The same sessions and runs as rounds 1 and 2; no motion clips:

```bash
systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 \
  /home/bot/docker/poring-lab/.venv/bin/python scripts/gpu_rec_bench.py sample --round 3 \
    --session 20261105T225409-rdp-xmas02-x2:xmas_dun02 \
    --session 20261026T120547-rdp-rogue-c1:gef_fild10
cat /dev/shm/poring-lab-recbench/in/round /dev/shm/poring-lab-recbench/in/timing_reps  # 3 and 3
df -h /dev/shm
```

**Step 2, the container.** The same guarded one-shot as before, with nothing built: 13 arms, 3
timing passes, ~6 min expected.

```bash
python3 scripts/guarded_build.py start:media-recbench@600
timeout 1800 docker wait poring-lab-media-recbench-1
docker logs poring-lab-media-recbench-1 2>&1 | tail -60
python3 scripts/guarded_build.py rm:media-recbench
tail -40 /dev/shm/poring-lab-recbench/out/results.txt
grep -vP '\tok\t' /dev/shm/poring-lab-recbench/out/status.tsv  # failed / unavailable / skipped
grep -E 'fast|dflt|bgr0|-10' /dev/shm/poring-lab-recbench/out/status.tsv
du -sb /dev/shm/poring-lab-recbench/out  # ~1.12e9 expected, cap 1.2e9
```

**Step 3, score** (host CPU; the detector runs on 6 graded arms, so ~25 min):

```bash
systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 \
  /home/bot/docker/poring-lab/.venv/bin/python scripts/gpu_rec_bench.py score \
    --out /home/bot/docker/poring-lab/data/bench/gpu-rec/$(TZ=Asia/Bangkok date +%Y%m%d)-recbench-r3.json
```

It prints:
- the verdict;
- one `control` line per control and sample, now with its SSIM (mean, min, dark, rest), the dark
  share, `black_keep` and `neutral`;
- one `ssim` line per graded arm and sample;
- a `vui_mismatch` line for any stream whose VUI disagrees with its declaration.

**Step 4, record section 8.4.** Record, with times from `TZ=Asia/Bangkok date`:
- the controls against 6.7's "what the controls mean": the known-good `ctl-yuv444` first, then
  `gctl-vpp444`'s prediction, then each variant and `gctl-vpp444-tv`;
- the graded arms' bars, their `ssim` lines and the verdict;
- S2's three passes for each candidate;
- every status note: `fmt-*`, failures, skips.
- The tests can then pin round 3's score like round 2's
  (`test_round_2_score_gives_the_same_verdict_rates_and_controls_today`). From a worktree, point
  them at the main checkout's scores with `GPU_REC_SCORES=/home/bot/docker/poring-lab/data/bench/gpu-rec`.

**Step 5, clean up the same day,** as in section 7. Copy `out/*.txt`, `out/*.tsv` and `out/md5/`
to the NAS `scratch-archive/<date>/recbench-r3/` if they are wanted, then
`rm -rf /dev/shm/poring-lab-recbench`.

## 8. Results (phase 2)
**Run 2026-11-08** (the parent; section 7's commands from the main checkout after the merge):
sample 17:14-17:15, the container 17:15:08-17:23:06 (guarded `start:media-recbench@600`, worst
stall 0.0 %; 80 runs ok, 0 failed), score 17:26-17:52. Results:
`data/bench/gpu-rec/20261108-recbench.json`; the small outputs (vainfo, help, tsv, md5) on the NAS
`scratch-archive/2026-11-08/recbench/`.

**VERDICT: VALID (V1 PASS: 48.8 / 50.4 dB, max error 2), NO CANDIDATE.** By rule 4, nothing is
adopted. **The closest arm, `hevc444-q20`, fails ONE bar: S2** (the container's CPU per frame).

| | PNG (today) | JPEG q95 (the cache) | **hevc444-q20** | hevc444-q14 | vpp-hevc420-q20 |
|---|---|---|---|---|---|
| bytes a frame, xmas_dun02 / gef_fild10 | 1.27 / 2.34 MB | 0.27 / 0.54 MB | **0.19 / 0.49 MB** | 0.30 / 0.73 | 0.13 / 0.35 |
| GB per hour at 1 / 10 fps | 8.4 / 84.1 | - | **1.75 / 17.5** | 2.62 / 26.2 | 1.25 / 12.5 |
| PSNR mean (min), xmas / gef | lossless | 32.9 / 33.7 | **43.5 (41.9) / 39.8 (39.2)** | 46.8 / 43.7 | 25.4 / 28.5 |
| SSIM mean, xmas / gef | 1 | 0.993 / 0.992 | **0.994 / 0.992** | 0.997 / 0.997 | 0.615 / 0.975 |
| detector boxes vs PNG, xmas (166 boxes) | - | - | **166 / 166, p95 0.3 px** | 166 / 166 | 166 / 166, 0.7 px |
| CPU a frame | encode 91 / 160 ms (host) | - | **21.9 ms** (container) | 22.2 | 9.0 |
| encode speed | - | - | 161 fps | 159 | 246 |
| failing bars | - | - | **S2 only** | S1 (gef), S2 | Q1-Q6, G1 (colour) |

- **What it buys, measured:** ~5-7 x fewer bytes than PNG at a quality ~10 dB above the JPEG q95
  cache the trainer reads today, the same detector boxes on xmas_dun02 (gef_fild10 has 17 boxes:
  P is underpowered there), every frame decodes alone and bit-identically on VA-API, ffmpeg and
  PyAV (D1, D2). The CPU per frame is 4-7 x below PNG's encode (21.9 vs 91-160 ms).
- **Why S2 fails:** 13.4 ms of the 21.9 is swscale's BGRA -> YUV 4:4:4 on the CPU
  (`conv_yuv444p`). The GPU-side conversion (`vpp-hevc420-q20`, 9.0 ms) is cheap, but its colours
  come out wrong (25-28 dB, SSIM 0.39 at worst): most likely a range or matrix mismatch in
  `scale_vaapi`, the same family as section 18's washed-out JPEG (not proven).
  ➡️ **Diagnosed in 8.1 (the same evening, no GPU run):** the GPU wrote BT.601 LIMITED-range YUV
  into a stream tagged, and scored, as BT.709 full range. Both were found: the range and the
  matrix.
- **Not answered by this run:** Batt's "faster" for training (the trainer reads the JPEG cache,
  section 4); the second hop's cost (stage 2).
- **Next (an amendment BEFORE any re-run, Batt's go):** a GPU-side conversion with the right range
  (and 4:4:4 if `scale_vaapi` / the VPP can output it), graded on the same bars; or a decision on
  S2's bar itself (it was set at 0.1 x PNG; the arm is 0.14-0.24 x).
  ➡️ Batt chose the first ("try fixing the colours too", ~18:0x). It is ROUND 2: amendment 6.6
  (pre-registered 18:35:58 ICT) and its commands, 7.2. S2's bar is unchanged.

### 8.1 Why `vpp-hevc420-q20`'s colours were wrong (diagnosis, 2026-11-08 18:07-18:35 ICT, no GPU run)
**The answer:** the GPU wrote **BT.601, LIMITED-range** YUV, while the stream was tagged, and
scored, as BT.709 full range.
- The range is most of the loss: the picture is washed out, black at 16 and white at 235.
- The matrix shows in the saturated colours.
- The cause, inferred from ffmpeg's and Intel's source: round 1's `scale_vaapi` named the matrix
  and the range, but not the **colour primaries**. The driver then falls back to BT.601 limited.

| # | step | evidence | status |
|---|---|---|---|
| 1 | The tag and the scorer agree, and are the same for the CPU-converted arms | Every round-1 encode log prints the output stream as `vaapi(pc, bt709/unknown/unknown)`: range pc, matrix BT.709, primaries and transfer unknown. It does so for `vpp-hevc420-q20` and `hevc420-q20` alike (NAS `scratch-archive/2026-11-08/recbench/logs/e-gef_fild10-{vpp-hevc420-q20,hevc420-q20}-r0.log`). hevc_vaapi writes its VUI from these fields: full range, matrix 1. The scorer ignores the VUI and inverts with BT.709 full (`COLOR`) | **proven** for the log lines and the scorer. The VUI bits themselves are not dumped: the bitstreams went in round 1's step 5 |
| 2 | Only the conversion differs | `hevc420-q20` and `vpp-hevc420-q20` share the encoder, the QP, the GOP, the tags, the decoder and the scorer. The CPU-converted one sits at the 4:2:0 floor (xmas 32.9 dB, against `ctl-yuv420`'s 33.0); the GPU one sits at 25.4 | **proven**: the defect is in the pixel values `scale_vaapi` wrote |
| 3 | Which values: a fingerprint | Round 1's 200 PNG frames (the same runs, read from the NAS) converted to 4:2:0 by swscale under four hypotheses, read back as BT.709 full, with round 1's metrics (`docs/records/scorers/gpu_rec_r1_fingerprint.py`, 18:19-18:24 ICT; table below). Only BT.601 limited matches all four columns on both samples | **inferred**, strongly: one hypothesis matches four measures on two samples, and each of the other three misses at least one by far |
| 4 | Why the GPU did it | ffmpeg 8.0 (`libavfilter/vaapi_vpp.c`): when the driver lists `VAProcColorStandardExplicit`, ffmpeg passes the explicit properties (primaries, transfer, matrix, range) instead of a named standard. Intel's media-driver (master, `ddi_vp_functions.cpp`, `VpSetColorStandardExplictly`): for a YUV target the colour space is chosen from `colour_primaries` ALONE (the matrix is not read). BT.709 primaries give `CSpace_BT709` / `_FullRange` by the range flag, BT.601 primaries `CSpace_BT601` / `_FullRange`, and **anything else `CSpace_BT601`**, BT.601 limited, with the log line "unknown Color Standard for YUV format". The PNG input carries no primaries and round 1 set none | **inferred** from the source, read and not tested here. Not checked: that iHD 26.1.2 lists Explicit (the list was not found in master), and that 26.1.2 matches master. If Explicit were not listed, ffmpeg would pick the BT.709 standard with the full-range flag, which would have been right; the measured BT.601-limited points to the explicit path |
| 5 | The same cause explains section 18's washed-out VA-API JPEG | The probe's `scale_vaapi=format=nv12`, and its `out_range=full:out_color_matrix=bt470bg` variant, set no primaries either: BT.601 limited inside a full-range JPEG. That is why `out_range=full` did not fix it | **inferred** (the probe's per-variant numbers were not kept) |

The fingerprint (step 3). Each simulation leaves out the QP 20 coding loss and the GPU's own chroma
filter. Both cost round 1's measured row a little more (gef_fild10: 28.5 measured, 29.3 simulated).

| conversion written, read as BT.709 full | PSNR mean (min), xmas / gef | SSIM mean (min), xmas / gef | saturated keep, xmas / gef | basic_info crop PSNR, xmas / gef |
|---|---|---|---|---|
| round 1's `vpp-hevc420-q20` (measured) | 25.38 (24.44) / 28.50 (27.65) | 0.615 (0.388) / 0.975 (0.973) | 0.186 / 0.114 | 22.7 / 22.6 |
| BT.709 full (the bench's own convention) | 33.02 (32.30) / 34.19 (32.95) | 0.998 (0.997) / 0.999 (0.999) | 0.837 / 0.604 | 35.4 / 35.5 |
| BT.709 limited | 25.39 (24.66) / 29.18 (28.27) | 0.623 (0.395) / 0.987 (0.985) | 0.700 / 0.454 | 22.4 / 22.4 |
| **BT.601 limited** | **25.67 (24.80) / 29.28 (28.61)** | **0.623 (0.395) / 0.986 (0.984)** | **0.189 / 0.079** | **22.2 / 22.1** |
| BT.601 full | 32.33 (31.22) / 32.67 (31.25) | 0.997 (0.995) / 0.997 (0.996) | 0.591 / 0.284 | 35.6 / 35.7 |

- **The LIMITED range collapses SSIM on the dark dungeon:** 0.615 measured, 0.623 simulated. Black
  lifted to 16 swamps SSIM's luminance term wherever the scene is dark. The range also takes the UI
  crop down to 22 dB. Only the two limited hypotheses reproduce PSNR and SSIM; the full-range ones
  are 7-8 dB off.
- **The MATRIX is what the saturated-colour keep rate separates.** BT.709 limited would keep 0.70 /
  0.45 of the saturated pixels, BT.601 limited 0.19 / 0.08; round 1 measured 0.19 / 0.11. Pure
  red, for example, written BT.601 limited and read BT.709 full, comes back as RGB (255, 36, 10):
  its G rises above the keep limit of 32. Written BT.709 limited, it comes back as (239, 15, 15),
  still kept (swscale, checked).
- **The fix to test (6.6):** name the primaries and the transfer too
  (`out_color_primaries=bt709:out_color_transfer=bt709`). Round 2 tests steps 3 and 4 directly:
  - `gctl-vpp420-r1` (round 1's exact options, downloaded raw) must come out `bt601-limited` by
    the fingerprint;
  - `gctl-vpp420` (the same plus the primaries) must come out `bt709-full`.


### 8.2 Round 2's results (run 2026-11-08: sample 18:53, the container 18:53-19:03, score 19:35-19:47 ICT)
**VERDICT: VALID (V1 PASS), NO CANDIDATE. The colour fix WORKS; the GPU-converted
`vpp-hevc444-q20` passes S2 (8.7 ms CPU a frame) and every other bar but ONE: Q3 (SSIM) on
xmas_dun02.** Results: `data/bench/gpu-rec/20261108-recbench-r2.json`; the small outputs on the NAS
`scratch-archive/2026-11-08/recbench-r2/`.

The controls (reported, not graded; the luma fingerprint):

| control | xmas_dun02 | gef_fild10 |
|---|---|---|
| `gctl-vpp420-r1` (round 1's options) | **bt601-limited** (scale 0.858, offset 16.0): 8.1's diagnosis CONFIRMED | bt601-limited |
| `gctl-vpp420` (+ the primaries) | bt709-full, Y vs swscale mean 0.03, max 1 | bt709-full |
| `gctl-vpp444` (the fix, 4:4:4 on the GPU) | bt709-full, 46.5 dB, Y vs swscale mean -0.37, max 2 | bt709-full, 46.6 dB |
| `gctl-vpp444-tv` | bt709-limited (the range honoured) | bt709-limited |

The arms:

| | hevc444-q20 (CPU conversion) | **vpp-hevc444-q20** | vpp-hevc444-q20-tv |
|---|---|---|---|
| CPU a frame (median of 3 passes) | 21.8 ms (S2 FAIL) | **8.7 ms (S2 PASS: <= 15 and <= 0.1 x PNG's 89 / 162)** | 8.6 ms |
| encode speed | 161 fps | **283 fps** | 282 fps |
| bytes vs PNG, xmas / gef | 0.15 / 0.21 | **0.15 / 0.21** | 0.14 / 0.19 |
| PSNR mean, xmas / gef (JPEG q95 32.9 / 33.7) | 43.5 / 39.8 | **42.4 / 39.4** | 41.5 / 38.4 |
| SSIM mean (min), xmas | 0.994 (0.990) | **0.978 (0.969): Q3 FAIL** (needs >= 0.9915 and min >= 0.97) | 0.992 (0.987) |
| SSIM mean, gef | 0.992 | 0.992 | 0.989: Q3 FAIL |
| UI crops vs JPEG, xmas (Q4, >= -0.5 dB) | +2.26 | +0.19 | **-1.03: FAIL** |
| detector boxes vs PNG, xmas (166) | 166 / 166, p95 0.3 px | **166 / 166, 0.3 px** | 166 / 166, 0.3 px |
| failing bars | S2 | **Q3 (xmas) only** | Q3 (gef), Q4 (xmas) |

- **Read:** the GPU conversion is now right in colour and cheap (8.7 ms, 2.5 x below the CPU
  conversion, 10-19 x below PNG's encode). On xmas_dun02 its SSIM sits below the CPU-converted
  arm's (0.978 vs 0.994) at nearly the same PSNR (42.4 vs 43.5): a structural difference, not a
  colour one. Most likely the VPP's scaling path filters the picture even at 1:1 (not proven).
  ➡️ **SUPERSEDED by 8.3 (the same evening, no GPU run): NOT a filter.**
  - The loss is already in the conversion alone: round 2's own control, SSIM 0.987. It was in this
    score but not printed.
  - The GPU writes NEUTRAL chroma one level low, so black decodes as (0, 1, 0).
  - SSIM's dark windows, 30 % of xmas_dun02, magnify it.
- **Next (an amendment BEFORE any re-run; Batt's go):** the VPP's scaling mode / filters (e.g.
  `scale_vaapi`'s mode, or no scale step at all with only the colour conversion) graded on the
  same bars; or a decision on Q3 for this arm (it misses the mean by 0.014 and the minimum by
  0.001).
  ➡️ Batt chose round 3 ("try round 3", ~19:5x). It is amendment 6.7 (pre-registered
  2026-11-08 20:32:43 ICT), aimed at 8.3's cause, and its commands are 7.3. Q3 is unchanged.

### 8.3 Why `vpp-hevc444-q20` fails Q3 on xmas_dun02 (diagnosis, 2026-11-08 20:03-20:27 ICT, no GPU run)
**The answer:** round 2's GPU 4:4:4 conversion is NOT a filter. It writes the chroma of
**neutral** (grey and black) pixels one level low: U = V = 127 where swscale writes 128.
- A one-level error is invisible in PSNR, but black then decodes as (B, G, R) = (0, 1, 0).
- SSIM's luminance constant C1 = (0.01 x 255)^2 = 6.5 makes that cost 5 % of every black window.
- 30 % of xmas_dun02's windows are dark, against 0.02 % of gef_fild10's. That is the whole SSIM
  gap, and why only xmas_dun02 fails.

Sources: round 2's score (`data/bench/gpu-rec/20261108-recbench-r2.json`, its NAS copy
`scratch-archive/2026-11-08/recbench-r2/`). And a CPU simulation on the same frames
(`docs/records/scorers/gpu_rec_r2_ssim_sim.py`, run 20:04:13-20:05:59 ICT): it reads the NAS
read-only, uses no GPU, and is committed verbatim as it ran.

| # | finding | evidence | status |
|---|---|---|---|
| 1 | The SSIM loss is already in the GPU's CONVERSION, before any encoder | `gctl-vpp444` (the conversion alone, downloaded raw) on xmas_dun02: SSIM **0.98719** (min 0.98213), against swscale's `ctl-yuv444` **0.99942** (0.99915). Same 20 frames, same inverse (`to_bgr`), same metric. That alone is below Q3's mean bar for the arms (0.9915). On gef_fild10: 0.99973 against 0.99963, no loss. The numbers were in the score's control `quality`. `controls_summary` did not print SSIM, so round 2's report could not say it | **proven** (`test_round_2_score_gives_the_same_verdict_rates_and_controls_today` pins them) |
| 2 | It is not a spatial filter (scaling, sharpening, denoise) | The GPU's planes against swscale's, every pixel of those frames: Y at most 2 levels away, U and V at most 1. Every Y difference is downward: the mean equals minus the mean absolute (-0.366 / 0.366 on xmas, -0.399 / 0.399 on gef). A kernel with unit DC gain moves edge pixels both up AND down, and the UI crops are high-contrast text. Chroma siting cannot apply: RGB in, 4:4:4 out, nothing subsampled | the numbers **proven**; "no filter" **inferred** from them, strongly |
| 3 | The 4:4:4 output path rounds wrongly, not scale_vaapi's colour options | `gctl-vpp420` (the same options, NV12 out): Y +0.03 / +0.01, at most 1 level. `gctl-vpp444` (VUYX out): Y -0.37 / -0.40, one-sided. Its chroma error depends on the content: xmas U -0.397, V -0.289 (dark, many neutral pixels); gef U -0.041, V +0.012 | **proven** for the numbers; which hardware path each output format takes is not known offline |
| 4 | WHICH error costs the SSIM: the neutral chroma, not the luma | The simulation perturbs swscale's own 4:4:4 planes of the same 20 frames per sample and scores them with the bench's own metrics (table below). One model reproduces SSIM mean AND min on BOTH samples to 0.0001: Y rounded one-sidedly low, plus U and V one level low on neutral pixels. The Y bias alone costs no SSIM. The chroma alone costs all of it, all in dark windows | **inferred**, strongly: one model fits four numbers on two samples. Its PSNR is 1.1 dB high on xmas (47.6 vs 46.5), and its Y mean -0.28 against -0.37, so the GPU makes some further small error that the model leaves out |
| 5 | Why only xmas_dun02 | Dark 8 x 8 windows (the PNG's luma mean < 16): **30.4 %** of xmas_dun02's, **0.02 %** of gef_fild10's. swscale decodes Y = 0, U = V = 127 as (0, 1, 0), and 127 / 128 or 128 / 127 as black: only both low tints black. In a black window, SSIM is then 1 - 0.587^2 / (0.587^2 + 6.5) = **0.950** (the unit test pins it) | **proven** (arithmetic, swscale checked, the measured shares) |
| 6 | Why `vpp-hevc444-q20-tv` kept SSIM on xmas but failed elsewhere | `gctl-vpp444-tv`'s luma offset is 15.16 / 15.46, not 16, so its black sits BELOW the limited range's black, and the decoder clips it: (15, 127, 127) decodes black, while (16, 127, 127) decodes (0, 1, 0) (swscale, checked). Its control's SSIM on xmas: 0.99919. Its losses are elsewhere: a limited range codes 220 luma levels for 256, so it is ~1 dB lower everywhere (the conversion 45.4 vs 46.5 dB, the arm 41.5 / 38.4 vs 42.4 / 39.4). That fails Q4 (xmas crops -1.03 dB) and Q3 on gef (0.9891 < 0.9902) | the clip **inferred** (whether the tv path's chroma is low too was not measured: no limited twin); the precision cost **proven** by the numbers |
| 7 | The encoder's share | The arm's gap (`hevc444-q20` 0.99414 to `vpp-hevc444-q20` 0.97765, -0.0165) is larger than the conversion's (-0.0122). The encoder options are identical. The controls cover 10 frames a run, the arms 50; the encoder may also spend its bits differently on a tinted black | **not explained**; round 3's per-arm dark / rest split measures it |

The simulation (row 4). Each model is applied to swscale's BT.709 full-range 4:4:4 planes of
the controls' 20 frames per sample (the first 10 of each run). "Neutral" means swscale wrote U =
V = 128 there. Read back and scored as the bench does. Its first row reproduces `ctl-yuv444`
exactly.

| model, read as BT.709 full | PSNR, xmas / gef | SSIM mean (min), xmas | SSIM mean (min), gef | SSIM dark / rest windows, xmas | Y / U / V mean vs swscale, xmas |
|---|---|---|---|---|---|
| **measured, `gctl-vpp444`** | **46.49 / 46.60** | **0.98719 (0.98213)** | **0.99973 (0.99972)** | (not measured in round 2) | **-0.37 / -0.40 / -0.29** |
| swscale (= `ctl-yuv444`) | 50.36 / 48.77 | 0.99942 (0.99915) | 0.99963 (0.99963) | 0.99957 / 0.99933 | 0 / 0 / 0 |
| Y one level low everywhere | 45.31 / 43.72 | 0.99890 (0.99795) | 0.99956 (0.99951) | 0.99745 / 0.99926 | -0.72 / 0 / 0 |
| Y rounded low (floor(Y + 0.1), never above swscale) | 48.43 / 46.72 | 0.99950 (0.99902) | 0.99974 (0.99973) | 0.99923 / 0.99955 | -0.28 / 0 / 0 |
| U, V one level low on neutral pixels | 49.17 / 48.39 | 0.98679 (0.98174) | 0.99963 (0.99962) | **0.96088** / 0.99932 | 0 / -0.30 / -0.30 |
| U, V one level low on dark pixels (luma < 16) | 48.95 / 48.72 | 0.98642 (0.98124) | 0.99963 (0.99962) | 0.95948 / 0.99933 | 0 / -0.33 / -0.33 |
| **Y rounded low + U, V low on neutral pixels** | **47.63 / 46.48** | **0.98722 (0.98214)** | **0.99974 (0.99973)** | 0.96164 / 0.99955 | -0.28 / -0.30 / -0.30 |
| Y rounded low + U, V low on dark pixels | 47.44 / 46.69 | 0.98696 (0.98198) | 0.99974 (0.99973) | 0.96078 / 0.99955 | -0.28 / -0.33 / -0.33 |

- **What is not known offline:** why the VUYX path rounds this way, and whether another VPP path
  does not. Which engine (fixed-function or kernel) the driver picks per output format and
  scaling mode was not read from the driver's source here, and the bench measures it anyway.
- **What round 3 measures that round 2 did not** (6.7):
  - the neutral pixels' chroma directly (`neutral`: `uv_mid`, the mean errors, black);
  - `black_keep`;
  - the dark / rest SSIM split, for every control and every graded arm;
  - U and V beside Y against swscale;
  - the controls' own SSIM, printed.
- **What this changes:** the target is a GPU 4:4:4 path whose neutral chroma comes out at mid
  (6.7's arms), not a "no-filter" path.


### 8.4 Round 3's results (run 2026-11-08: sample 20:42, the container 20:43-20:50, score 21:22-21:42 ICT)
**VERDICT: VALID (V1 PASS), CANDIDATE `vpp-hevc444-10-q20`.** Three GPU-converted arms now pass
every bar (`vpp-hevc444-q20-dflt`, `vpp-hevc444-q20-bgr0`, `vpp-hevc444-10-q20`); the rule (6.5.3)
picks the smallest, the 10-bit one. Results: `data/bench/gpu-rec/20261108-recbench-r3.json`; the
small outputs on the NAS `scratch-archive/2026-11-08/recbench-r3/`.

The conversion alone (controls; xmas_dun02 / gef_fild10):

| control | PSNR | SSIM | black kept | SSIM in dark windows |
|---|---|---|---|---|
| `ctl-yuv444` (swscale, CPU) | 50.4 / 48.8 | 0.9994 / 0.9996 | 1.0 / 1.0 | 0.9997 / 0.9991 |
| `gctl-vpp444` (round 2's path: scale_vaapi's default `hq` mode) | 46.5 / 46.6 | 0.9872 / 0.9997 | **0.0 / 0.0** | **0.959** / 0.997 |
| `gctl-vpp444-fast` | 46.3 / 46.6 | 0.9884 / 0.9997 | 0.0 / 0.0 | 0.960 / 0.997 |
| `gctl-vpp444-dflt` (`mode=default`) | 54.5 / 53.2 | 0.9996 / 0.9998 | 1.0 / 1.0 | 0.9998 / 0.9995 |
| `gctl-vpp444-bgr0` (a BGRX upload) | 54.4 / 53.1 | 0.9996 / 0.9998 | 1.0 / 1.0 | 0.9998 / 0.9995 |
| `gctl-vpp444-10` (10-bit xv30) | 60.0 / 69.4 | 0.99999 / 1.0 | 1.0 / 1.0 | 1.0 / 1.0 |

- 8.3's diagnosis CONFIRMED: round 2's path turned black into (0, 1, 0) (black kept 0.0) and lost
  its SSIM in dark windows only; `mode=default`, a BGRX upload and 10 bits each keep black, and
  convert closer to the source than swscale does.

The candidate (graded on the same bars as rounds 1-2):

| | PNG today | JPEG q95 (the cache) | **vpp-hevc444-10-q20** |
|---|---|---|---|
| CPU a frame (median of 3 passes 8.5-9.0) | encode 89 / 159 ms | - | **8.7 ms** (S2 PASS) |
| encode speed | - | - | **279 fps** |
| bytes vs PNG, xmas / gef | 1 | 0.21 / 0.23 | **0.15 / 0.21** (1.74 GB / h at 1 fps; PNG 8.4) |
| PSNR mean (min), xmas / gef | lossless | 32.9 / 33.7 | **44.3 (42.7) / 40.4 (39.8)** |
| SSIM mean (min), xmas / gef | 1 | 0.9935 / 0.9922 | **0.9947 (0.9909) / 0.9922 (0.9916)** |
| detector boxes vs PNG, xmas (166) | - | - | **166 / 166, p95 0.3 px** (gef 16 / 17: P underpowered) |

- **Next (section 9, Batt's go): stage 2**, one side-by-side recording (PNG and this encode of the
  same session), then an ADR-0010 amendment (the recordings stop being lossless) -- Batt's
  decision. `mode=default` 8-bit is the fallback if 10-bit HEVC Main 4:4:4 10 is refused by a
  reader.
  ➡️ Batt's go ~21:5x ("do it now"): stage 2 is built and PRE-REGISTERED in 9.1; its commands are
  9.2; not run yet.

## 9. The staged plan (question 5)

```text
stage 0  design + bench, bars pre-registered        (this commit)
   |
stage 1  the bench on real frames (section 7)        -> a candidate arm, or "no"
   |       "no": record it; PNG stays (stop here)
   |
stage 2  ONE side-by-side recording (Batt's go)       -> the full-session bars (9.1)
   |       the media-rec sidecar + record_session --format <candidate> --also-png:
   |       every kept frame to BOTH writers. Bars, pre-registered before it:
   |       sizes and the recorder's CPU (CpuMeter, the hop included), the detect
   |       server's p50 / p95 with and without the encoder, recorder_boxes on both,
   |       every frame decoded and checked
   |
stage 3  ADR-0010 amendment (Batt decides)            -> which format for which purpose
   |       ➡️ DECIDED 2026-11-09 as ADR-0024 and BUILT (9.4)
   |       PNG stays selectable, and REQUIRED for cue-fitting studies until each
   |       passes its own parity on decoded frames
   |
stage 4  readers adopt it one at a time               -> a poring_dataset reader first,
   |       then build_frame_cache, then qa_export, gold_eval, m4_validate, recorder_boxes,
   |       the label tools; each checked on stage 2's session against its PNG twin
   |
stage 5  higher fps (5-10), Batt's call per window    -> the grab path's own cost at
           that rate (backend X grab + the BGRA pipe: ~37 MB/s at 10 fps), GOP or not
```

- **A cheaper lossless alternative, not measured here:** today's PNG writer filters no row
  (`filter 0`) at zlib level 1, so it stores 1.54-2.31 MB of a 2.76 MB raw frame. Row filters (Up
  or Paeth) or a CPU lossless video codec (FFV1) might cut that without giving up ADR-0010's
  promise, at a CPU cost on this 1.7 GHz Xeon that nobody has measured. If stage 1 says "no", that
  is the next question.

### 9.1 STAGE 2, PRE-REGISTERED (2026-11-08 22:46:20 ICT, the commit that adds it; before any stage-2 run)
**Batt, 2026-11-08 ~21:5x:** "do it now": stage 2, ONE side-by-side recording of a real bot session,
every kept frame written both as today's lossless PNG and through round 3's candidate, so that Batt
can decide the ADR-0010 question (stage 3: recordings no longer lossless).
- **Phase 1 (this commit):** the code, the sidecar, the tests, these bars and the commands (9.2).
  Nothing ran on the GPU, no container was started, nothing was recorded: the parent runs live
  pilots on the Arc all night and runs 9.2 beside one of them.
- **What stage 2 adds to stage 1:** stage 1 graded 200 sampled frames per map, encoded from PNG
  files in a one-shot container. Stage 2 grades ONE WHOLE SESSION recorded live, on the frame path
  the recorder really uses (the grab's raw BGRA, through the hop), with what it costs the recorder
  and the live detector beside it.

**The mechanism: how the frames reach the encoder.**

```text
backend (X grab) --docker exec pipe, raw BGRA (as today)--> host recorder (record_session.py)
                                                               |  PNG -> session/shard-*.tar
                                  raw BGRA, alpha set to 255   |  (unchanged; the reference)
                          ONE named pipe (FIFO) in a RAM dir:  v  /dev/shm/poring-lab-mediarec
      the sidecar media-rec (the media-probe image; no network, read-only, the render node only):
      ffmpeg: hwupload -> scale_vaapi (BT.709 full, xv30) -> hevc_vaapi Main 4:4:4 10, CQP 20,
      all-intra, AUDs                                          |
                       sequential, the local disk:             v  ~/poring-lab-rec/.media-rec/.<sid>.hevc
      at the end the recorder RENAMES it into the session (one filesystem, no copy):
      session/video.hevc + video.idx.csv + video.ffmpeg.log   (dataset_ship ships them with it)
```

| option | the hop | its CPU | containment | chosen |
|---|---|---|---|---|
| `docker exec -i`, ffmpeg's stdin (section 2's sketch) | host -> dockerd -> containerd-shim -> ffmpeg | the daemon relays every byte in user space (3.7 MB a frame, several copies), charged to dockerd and the shim: CpuMeter cannot see it | a docker action in the recorder's own path; an exec cannot be signalled (the Docker API), and its stdin dies with the client | no |
| **one FIFO in a RAM directory bound into the sidecar** | host write -> the kernel pipe (1 MiB) -> ffmpeg's read | one kernel copy on each side, charged to the recorder (the feed thread) and to the sidecar's cgroup: both measured (C1, C3) | the recorder makes no docker call but read-only `inspect`; the sidecar is started and removed by guarded steps; /dev/shm holds only small control files (the pipe's buffer is kernel memory) | **yes** |
| a second FIFO back (the recorder writes the bitstream) | as above, plus ~0.3 MB a frame back | one more copy | no disk bind in the sidecar | no: the S2 client's `.s2-h264` is the precedent for a dot-named disk directory that a container writes and the recorder renames from |
| the encoder on the host (B) | none | none | unpinned media packages on the host | no (section 2) |

- **Why the output goes to the disk, not RAM:** a 30-min stream is ~0.9 GB (1.74 GB/h at 1 fps,
  against PNG's 8.4), at the edge of rule 7's 1 GB item in /dev/shm and past it for longer sessions. A recording is a
  sequential file on the root disk (rule 7, 2026-10-29). The dot-named directory is never listed
  by dataset_ship; its size counts in the recorder's local caps and in `--max-bytes`.
- **Matching every frame to its PNG twin:** `video.idx.csv` has one row per kept PNG frame:
  `frame_id`, `t_mono_ns` (the PNG record's own), `video_index` (its place in the stream: all
  intra, no B-frames, `-fps_mode passthrough`, one access unit per fed frame, in order), `status`
  (`fed`, `dropped_queue_full`, `write_failed`, `not_fed_<state>`) and the write's start / end
  (host CLOCK_MONOTONIC, the detect log's clock). The manifest's `format` stays `png`, so every
  reader reads the session as before; its `video` block describes the side stream.
- **Fail-safe: the PNG is the reference.**
  - The PNG loop never waits for the video: a kept frame is put on a bounded queue (8 frames,
    ~30 MB); a full queue drops THAT frame from the video (its row says so); a feed thread writes the
    queue to the pipe.
  - The encoder closing its pipe (EPIPE), a frame write blocked for 20 s, or the feed thread ending
    fails the VIDEO side once, with its reason (`video.status` / `reason`), and the PNG frames go on
    to the session's end. The recorder prints one warning.
  - A video side that cannot START (no sidecar, a refused job, another recorder holding it)
    refuses the recording before any frame (part 0); a later `--resume` part records PNG only and
    says why.
  - The sidecar ends a job whose recorder never opened the pipe (a watchdog gives ffmpeg
    end-of-file after 60 s), and a container stop ends a running job cleanly (SIGINT to ffmpeg).
  - Without `--also-png` the format is refused: lossy-only recordings wait for the ADR-0010
    amendment.
- **The encoder is round 3's candidate, unchanged** (`test_the_sidecar_runs_round_3s_candidate_
  exactly` pins every option to `gpu_rec_bench.ARMS`): `format=bgra,hwupload,scale_vaapi=
  out_color_matrix=bt709:out_range=full:out_color_primaries=bt709:out_color_transfer=bt709:
  format=xv30`, `-fps_mode passthrough -c:v hevc_vaapi -low_power 1 -profile:v rext -rc_mode CQP
  -qp 20 -g 1 -bf 0 -aud 1`, tagged `-color_range pc -colorspace bt709 -color_primaries bt709
  -color_trc bt709`. The one input difference: the bench encoded PNGs (ffmpeg turns them into BGRA
  with alpha 255); the recorder feeds the grab's BGRA with its alpha SET to 255 (the grab does not
  specify it), so the uploaded bytes are the same kind.

**The bars** (graded on the one session; the values live in `media_rec.STAGE2_BARS` and, for
stage 1's, `gpu_rec_bench.BARS`; a test keeps this table and the code equal):

| bar | key | what | value |
|---|---|---|---|
| K1 | `K1_missing` | every kept PNG frame has a decoded twin: kept minus matched at most this, every fed frame decoded, none undecodable | 0 |
| F1 | -- | every decoded frame signals pc / bt709 (the declared convention; stage 1 reported it) | every frame |
| D1 | -- | every access unit decodes ALONE to the same planes (stage 1's D1) | every frame |
| Q1-Q6, G1, P1-P3, S1 | 6.4's keys | stage 1's bars with stage 1's values (6.4), over EVERY frame of the session, against the JPEG q95 of the same frames; the map's deployed CPU detector (`unit_detector.for_map`) on the PNG, the decoded frame and the JPEG; P powered at 100 PNG boxes | 6.4 |
| C1 | `C1_video_ms` | the video side's CPU per fed frame: the feed thread (the alpha copy, the pipe write) plus the sidecar's cgroup over the recording (the pipe read, upload, VPP, encode, file write), ms, at most | 20.0 |
| C2 | `C2_png_ratio` | ... and at most this x the PNG writer's CPU per kept frame in the same session (`png_writer_cpu_s`: encode + tar, the recorder's own thread) | 0.2 |
| C3 | `C3_hop_ms` | the hop's host side alone (the feed thread) per fed frame, ms, at most | 5.0 |
| L1 | `L1_p50_ms` | the detect server's GPU calls (detect_speed's measure: `detections.jsonl`, path gpu) logged inside the recording's [t0, t1]: p50 minus the BASELINE pilot's, ms, at most | 1.0 |
| L2 | `L2_p95_ms` | ... p95 minus the baseline's, ms, at most | 3.0 |
| L3 | `L3_gpu_share` | ... the share of calls the GPU answered (the rest fell back to the CPU) minus the baseline's, at least | -0.01 |
| L | `L_min_calls` | L1-L3 graded only with at least this many calls in the recording's window AND in the baseline (else NA) | 500 |

- **Stage 1's own bars, not graded here:** `S2` and `S3` (the container's encode timing from raw
  frames in RAM; C1-C3 measure the whole video side instead) and `D2` (the VA-API decode in the
  container: stage 2 runs no container decode, and stage 1 proved VA = software = host for this
  encoder on every frame).
- **The baseline:** the most recent pilot on the same map, with the detect server on the GPU and
  no recorder beside it, NAMED in 9.3 before `check` runs (`--baseline`).
- **Why these values** (set before any stage-2 number):
  - C1 20 ms: S2's 15 ms for the encode from RAM (stage 1 measured 8.7), plus 5 for the hop.
  - C2 0.2: S2 held the encode alone to 0.1 x `encode_png`; the hop is allowed as much again.
    Today's PNG writer costs ~89-159 ms a frame on bot-server (stage 1's `encode_png`).
  - C3 5 ms: one 3.7 MB copy (the alpha) and one 3.7 MB pipe write a frame.
    - Honest note: 5.0 was written in `media_rec.py` BEFORE the stub end-to-end test ran. That test
      then measured the feed thread at 4.6 ms a frame (5 frames, nice 19, beside the libx265
      stand-in encoding on the same CPU), and a microbenchmark on an idle core 2.8 ms (copy and
      alpha 1.45, the pipe write 1.33). The value is kept as written: a live C3 near the limit is
      the CPU contention the bar exists to see.
  - L1 1 ms: recent pilots' GPU call p50 is 20.5-20.6 ms (detect_speed), so 1 ms is ~5 %. L2 3 ms
    on the tail. L3: a GPU call slower than `GPU_CALL_S` (250 ms) falls back to the CPU, so a drop
    in the GPU's share is contention the latencies alone could hide.
- **Measured and reported, never graded:**
  - sizes and GB per hour of both files; the recorder's CPU per kept frame with the feed and
    without it (the process minus the feed thread), the PNG writer's, the sidecar's; the backend's
    cores (the grab, the same in both);
  - the hop's write latency (p50, p95, max) and the queue's high-water mark;
  - inside the recording, the detect calls that meet a frame's write (its span + 50 ms) against the
    rest: the same pilot and minutes, paired by time; and the pilot's calls outside the recording
    when the pilot ran longer;
  - `recorder_boxes`' own comparison (IoU 0.5) of the two box files, written beside the score in
    its row format (boxes only, never pixels), ready for `detector_vs_packets.py`.
- **The decision rule:**
  1. PASS: no bar FAILS, and every bar is MEASURED. NA is allowed only for Q6 (too few saturated
     pixels, as in stage 1); P must be powered, and L1-L3 need the pilot and the baseline.
  2. A PASS is the evidence for Batt's stage 3 (the ADR-0010 amendment), not an adoption.
  3. A FAIL names its bars. Nothing is re-run and no bar re-tuned without an amendment here first,
     timestamped from `date`. A run that cannot complete (the sidecar refused, the pilot ended
     early) is re-run as it is, once, written here first.
  4. A video side that FAILED mid-session (a stall, EPIPE) fails K1 by construction; its PNG
     session stays an ordinary PNG session.
- **Expected, not bars:** 0.15-0.21 x PNG's bytes (stage 1); C1 ~11-15 ms; C3 ~3 ms; no measurable
  L1 / L2 change at 1 fps (an encode is ~4 ms of VDEnc a second, a fixed-function engine apart from
  the EUs the detector uses; the memory bandwidth is shared); `check` ~1 s a frame with the
  detector (~30-40 min for 1800 frames).
- **Not checkable offline** (phase 1 had no GPU and no container): that this ffmpeg takes these
  options from a pipe at 1 fps (`-video_size` / `-framerate` on rawvideo, `-fs`, `-n`,
  `-stats_period` are new to this path; the encode options are stage 1's); compose's `${HOME}` in
  the bind source and the start of a service by name outside its active profile (stage 1's
  `start:media-recbench` did the same); the sidecar's cgroup CPU file on bot-server; the encoder's
  per-frame CPU at 1 fps (stage 1 timed a 600-frame burst); whether the grab's alpha matters.

### 9.2 Stage 2: the exact commands (the parent runs them; nothing here ran in phase 1)
Preconditions:
- the media-probe image is there (`312dfd87b5c3` on 11-08); nothing is built;
- the root disk has the room: a 30-min session at 1 fps is ~2.3-4.2 GB of PNG (1.27-2.34 MB a
  frame) plus ~0.9 GB of video; `--max-bytes 8G` counts both; the 30 GB floor and the 20 GB
  unshipped cap stay;
- a pilot about to start on the Arc (its detector on the GPU path), and a BASELINE pilot's session
  directory (the same map, no recorder) to name in 9.3.

**Step 0, the shell** (the main checkout once this branch is merged; from the worktree
`/dev/shm/poring-lab-wt/gpu-rec-s2` instead, link the main `.env` in first, as in section 7, and
remove it in step 5):

```bash
TZ=Asia/Bangkok date; df -B1 /home/bot; df -h /dev/shm
docker image ls poring-lab/media-probe --format '{{.ID}} {{.CreatedAt}}'  # 312dfd87b5c3 on 11-08
cd /home/bot/docker/poring-lab
export PYTHONDONTWRITEBYTECODE=1 TMPDIR=/dev/shm/poring-lab-tmp
export PYTHONPATH=$PWD/scripts:$PWD/packages/poring_env/src:$PWD/packages/poring_dataset/src:$PWD/packages/poring_packets/src:$PWD/services/backend/src:$PWD/services/vision/src
PY=/home/bot/docker/poring-lab/.venv/bin/python
```

**Step 1, the sidecar's two directories** (ours, 0700; idempotent), then **the sidecar** (guarded,
long-lived, idle until a job):

```bash
$PY scripts/media_rec.py prep
python3 scripts/guarded_build.py start:media-rec@60
docker logs poring-lab-media-rec-1 2>&1 | tail -3   # "mediarec: ready: ffmpeg version 8.0.1 ..."
$PY scripts/media_rec.py status                       # state running; ctl and rec empty
```

**Step 2, the recording, beside the pilot** (start it once the pilot is in the field; it records
for 30 min, or until the pilot's session ends and you stop it with Ctrl+C / SIGTERM: a signal ends
it cleanly):

```bash
$PY scripts/record_session.py --backend rdp --label s2-<map>-<pilot> --seconds 1800 --fps 1 \
  --format vpp-hevc444-10-q20 --also-png --max-bytes 8G
```

- It prints one JSON line at the end: `frames`, `stop_reason`, and `video` (`status`, `reason`,
  `fed`, `by_status`). A `WARNING: the video side failed` line during the run means the PNG goes
  on alone (the reason is in the manifest).
- Read-only looks during the run: `ls -la ~/poring-lab-rec/.media-rec`,
  `docker logs poring-lab-media-rec-1 2>&1 | tail -3`.

**Step 3, stop and remove the sidecar** (after the recording has printed its line):

```bash
python3 scripts/guarded_build.py rm:media-rec
$PY scripts/media_rec.py status   # state absent; rec empty (its stream was renamed into the session)
```

**Step 4, the check** (host CPU, after the pilot; the detector runs 3 times a frame, ~1 s a frame):

```bash
S=$(ls -d ~/poring-lab-rec/*-rdp-s2-* | tail -1)
systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 nice -n 19 \
  $PY scripts/media_rec.py check "$S" --map <map> --pilot <PILOT_SESSION_DIR> \
    --baseline <BASELINE_PILOT_SESSION_DIR> --det-threads 4 \
    --out /home/bot/docker/poring-lab/data/bench/gpu-rec/$(TZ=Asia/Bangkok date +%Y%m%d)-stage2.json
```

- It prints the verdict, completeness, sizes and CPU, then one line per bar; exit 0 only on PASS.
  The two box files land beside the score (`*.png-boxes.jsonl`, `*.video-boxes.jsonl`).
- Then ship the session as usual (`scripts/dataset_ship.py`): the video files go with it.

**Step 5, record 9.3** (times from `TZ=Asia/Bangkok date`): the baseline's name first, then the
bars and the verdict, the CPU split, the latency lines (in the recording, the baseline, near /
far from an encode, outside the recording), the video block's `by_status`; then clean up:
`rm -rf /dev/shm/poring-lab-mediarec` (a lock file only) and, from a worktree, its `.env` link.

### 9.3 Stage 2's results
**Named BEFORE the check runs (2026-11-08 23:24:39 ICT):**
- the BASELINE pilot (same map, the GPU detect path, no recorder): rogue-xmas02.md p19,
  `20261108T232242-demo-dungeon-rogue-xmas_dun02-patrol-P2-xmas02-p19` (`--far-single`, 25 min);
  a caveat for L1-L3: p19 ran its first ~10 min on p18's still-running detect server (the same
  flags and floor) and switched to its own step at ~23:32 (a few seconds of CPU fallback);
- the RECORDED pilot: p20 (rogue-xmas02.md 4AB), the same flags, the recorder beside it.

**The check (2026-11-09 05:00:25-05:33:19 ICT, host CPU, after the night's last pilot; the
command of 9.2 step 4 with `--det-threads 4`; out `data/bench/gpu-rec/20261109-stage2.json`, not
committed): VERDICT PASS -- every quality and stage-2 bar, nothing unmeasured, detector-powered.**
- The recording: `20261108T235614-rdp-s2-xmas_dun02-p20` (beside pilot p20, 21 min, stop
  "duration"), 1,200 kept frames, every one fed, decoded and matched (undecodable 0, missing 0,
  shard cuts none, D1: all 1,200 decoded alone and identical).
- Sizes: PNG 1,579,630 B a frame, video 232,957 B (ratio 0.1475); at 1 fps 5.69 vs 0.84 GB an hour.
- CPU a frame: the PNG writer 136.1 ms, the video path 18.3 ms (the sidecar 15.0, the feed 3.3);
  the backend 0.23 cores.

| bar | measured | rule | |
|---|---|---|---|
| Q1 | 43.42 dB | >= jpeg 32.23 + 0.0 | PASS |
| Q2 | 41.40 dB | >= 36.0 | PASS |
| Q3 | 0.99375 / 0.98899 | mean >= jpeg 0.99413 - 0.002, min >= 0.97 | PASS |
| Q4 | 2.848 | every crop's mean - jpeg's >= -0.5 | PASS |
| Q5 | 40.77 | >= 32.0 | PASS |
| Q6 | 1.0 (326,753) | >= 0.95 | PASS |
| G1 | -0.209 | >= -1.0 | PASS |
| P1 / P2 | 0.9973 / 0.9973 | >= 0.97; >= jpeg (0.9947 / 0.9921) - 0.01 | PASS |
| P3 | median 0.1, p95 0.4 px | <= 1.0 / <= 3.0 | PASS |
| D1 | 1,200 / 1,200 | every frame alone | PASS |
| S1 | 0.1475 | <= 0.25 | PASS |
| K1 | kept - matched 0; 1,200 / 1,200 decoded | <= 0 | PASS |
| F1 | 1,200 / 1,200 signal pc / bt709 | every decoded frame | PASS |
| C1 | 18.27 ms | <= 20.0 | PASS |
| C2 | 18.27 vs the PNG writer's 136.08 ms | <= 0.2 x | PASS |
| C3 | 3.27 ms | <= 5.0 | PASS |
| L1 | p50 20.5 vs the baseline p19's 20.6 ms (-0.1) | recording - baseline <= 1.0 | PASS |
| L2 | p95 22.1 vs 21.9 ms (+0.2) | <= 3.0 | PASS |
| L3 | GPU share 1.0 vs 0.9967 (+0.0033) | >= -0.01 | PASS |

- **What it means (9.1's rule 2):** the evidence for Batt's stage 3 -- the ADR-0010 amendment
  (recordings no longer lossless) -- not an adoption. Lossy-only recordings stay refused until then.

### 9.4 Stage 3: DECIDED (Batt, 2026-11-09 ~06:3x ICT)

Batt's answer to the 05:37 report: "ใช้ การ์ดจอแทนได้เลย" -- use the GPU video in place of PNG.
On 9.3's PASS, recordings on the RDP path become `vpp-hevc444-10-q20` (lossy, 10-bit 4:4:4 HEVC,
CQP 20, all-intra) without the PNG twin. The ADR-0010 amendment records the decision; the
recorder's default, the video-only path and the session readers follow (built in a worktree,
merged after review). Until that merge, recordings stay as they are.
➡️ The decision is recorded as a NEW ADR with a pointer in ADR-0010 (CLAUDE.md: "supersede it
explicitly"), not as an amendment inside it: [ADR-0024](../adr/0024-gpu-video-recordings.md).

**What was built (branch `feat/recording-stage3`, 2026-11-09; no GPU, no container, nothing
recorded):**
- `record_session.py` (recorder v7):
  - `--backend rdp` with no `--format` records the video ONLY (`format` vpp-hevc444-10-q20, no
    shards); `--format png` records PNG as before, to any `--out`; `--also-png` with the video
    format (explicit or the default) is stage 2's side-by-side, unchanged;
  - a video side that cannot start refuses every part; one that fails mid-session stops the
    recording (`stop_reason: video_failed: ...`); `--resume` / `--state-file` take the video
    format;
  - the manifest: `format`, `frames` = the frames the stream holds (its access units counted once
    at the end, `video.access_units`), `kept`, `bytes` = the stream's, `png_level` null;
    `--max-bytes` and the local caps count the stream as in stage 2; a resumed recording's byte
    budget counts both files of a side-by-side part (`bytes_total`).
- `media_rec.py`: `video.idx.csv` gains the PNG record's `t_wall`, `bus_frame_id`, `source`
  (`EXTRA_FIELDS`); `check` refuses a video-only session (no PNG twin to grade against).
- `poring_dataset.frames` (new), one API for PNG and video sessions:
  - `frame_refs(session)`: every frame's ref (frame_id, t_mono_ns, the file, offset, size: the
    PNG member, or the access unit), from the index only;
  - `read_ref(ref)`: one frame as BGR (the access unit decoded ALONE, BT.709 full range, the
    VUI and the size checked);
  - `iter_frames` / `iter_bgr(session, every=N)`: in recording order, lazily decoded;
  - `nearest_ref`, `frame_source` (`PORING_FRAME_SOURCE=png|video`: a stage-2 session read from
    either), `png_required` (the cue studies' refusal), `verify_video` (dataset_check's pass);
  - the access units are split by the stream's own NAL syntax (H.265 7.4.2.4.4), the same split
    as libavcodec's parser (pinned by a test on streams with and without AUDs).
- The readers on it: build_frame_cache, qa_export, gold_eval, label_quality, m4_validate,
  recorder_boxes (+ truth_draw), labels_v2, map_labels, detector_vs_packets; map_labels' and
  detector_vs_packets' recording pins take recorder v7 but PNG ONLY (the parent's review: their
  pre-registered gates were fitted on lossless frames; a video session is refused there until a
  pre-registered parity check -- live check 4).
- The cue studies refuse a video recording (ADR-0024 decision 4): miss_cue, target_items,
  mvp_watch_study, cursor_unknown. warp_watch is not a reader of these sessions (its own JPEG
  shards): unchanged.
- `dataset_check.py`: a video session is checked by `verify_video`; `dataset_ship` needed no
  change (it ships every data file; a test ships and verifies a video-only session).

**Not verifiable offline -- the parent's live checks after the merge** (bot-server, the sidecar
up, beside a pilot as in 9.2):
1. a short video-only recording: `record_session.py --backend rdp --label s3-<map> --seconds 300
   --fps 1 --max-bytes 2G` (no `--format`): exit 0, `format` vpp-hevc444-10-q20, `frames` ==
   `kept` == `video.access_units`, `stop_reason` duration, no shard in the session, the
   `.media-rec` directory empty after it;
2. `dataset_check.py <that session>` (exit 0: every access unit decoded alone, every fed row
   matched);
3. the refusal: the same command with the sidecar removed (`rm:media-rec`) refuses before any
   frame and leaves no session directory;
4. each switched reader on stage 2's session `20261108T235614-rdp-s2-xmas_dun02-p20`, once with
   `PORING_FRAME_SOURCE=png` and once with `=video`, the outputs compared: `recorder_boxes.py
   predict` (the boxes: the stage-2 check's own comparison is the reference, P1 0.9973),
   `detector_vs_packets.py score-session` on both box files, `qa_export.py` (the same frame ids),
   `build_frame_cache.py --dry-run` (the same frames), `map_labels.py labels` (the same kept
   frames: its layout check and the fit read pixels), `labels_v2.py` npc-sheet;
5. `dataset_ship.py ship` of the step-1 session after 17:00 (verified, local copy deleted).

## 10. What phase 1 changed
- `scripts/gpu_rec_bench.py` (new): `sample` / `score` / `verdict`; ARMS and BARS, the single
  source of both tables above.
- `services/media-probe/recbench.sh` (new): the container side. It is bound read-only into the
  probe's image, so phase 2 builds nothing.
- `compose.yaml`: the one-shot service `media-recbench` (profile `recbench`): media-probe's
  isolation plus exactly three binds (the script read-only, `/dev/shm/poring-lab-recbench/in`
  read-only, `.../out`; the two RAM binds never create their source, so a start without the
  sample step is refused), user 1000, 3g (the /out pages are charged to it).
- `docs/adr/0010-dataset-format.md` and `bot-server-migration.md` section 18: a pointer here
  (PROPOSED, not decided; ADR-0010 itself unchanged).
- `services/backend/tests/test_guards.py`: pins that service. `services/backend/tests/
  test_gpu_rec_bench.py`: the pure helpers, the verdict, and the host decode path (D1's positive
  and negative case on a CPU-encoded stream).

### 10.1 What round 2's phase 1 changed (branch `design/gpu-recording-r2`, no GPU, no docker)
- `scripts/gpu_rec_bench.py`:
  - `ROUNDS` (round 1 = the original table, unchanged; round 2 = 6.6's), `round_arms`,
    `sample --round`. `sample` writes `in/round` and `in/timing_reps`; `score` and `verdict` read
    the round back, and a score without one is round 1's;
  - the `Arm` fields `vpp` (scale_vaapi's options) and `color_range` (pc / tv, the declared range),
    `arm_color`, and the mode `gctl`;
  - the GPU controls' scorer (`score_gctl`, `raw_planes` for NV12 / VUYX / VUYA, `planar_array`),
    the luma fingerprint (`luma_fit`, `name_convention`, `CONVENTIONS`), `plane_diff`,
    `controls_summary`;
  - `decode_stream` / `to_bgr` invert with the arm's declared convention and report the VUI
    (`vui_of`);
  - `merge_timing`: the median of the timing passes; one pass is exactly round 1's `timing_row`.
- `services/media-probe/recbench.sh`:
  - reads the two new fields;
  - takes the vpp / gctl conversion from the arm, and the `-color_range` tag from its declaration;
  - the `gctl` branch: upload, `scale_vaapi`, download, raw;
  - `TREPS` timing passes, round-robin;
  - saves `help-scale_vaapi.txt`.
- `services/backend/tests/test_gpu_rec_bench.py`:
  - round 1 pinned: its arms, their fields and order, the default table;
  - round 1's own score gives the same verdict and rates (it runs where `data/` has it);
  - the timing merge on round 1's real rows;
  - the raw layouts against swscale's own;
  - the gctl path read exactly like the ctl path;
  - the fingerprint names all four conventions, and names nothing it does not know;
  - a declared limited range: positive and negative case, and the VUI;
  - round 2 end to end on stand-ins: the r1 control named `bt601-limited`;
  - round 2's container side with stub tools.
- `docs/records/scorers/gpu_rec_r1_fingerprint.py`: 8.1's simulation, verbatim as it ran.

### 10.2 What round 3's phase 1 changed (branch `design/gpu-recording-r3`, no GPU, no docker)
- `scripts/gpu_rec_bench.py`:
  - `ROUNDS[3]` / `TIMING_REPS[3]` (6.7's table), the arms, `VPP_FAST` / `VPP_MDEF`,
    `HEVC444_10`;
  - the `Arm` field `upload` ("-" = BGRA, rounds 1 and 2's; `bgr0`), last before `args`;
  - 10-bit: `raw_planes` reads `xv30`, `plane_depth`, `yuv_frame` (yuv444p10le planes into a
    frame, which this PyAV's `from_ndarray` refuses), and `frame_planes` keeps 2 bytes a sample
    (D1 / D2 in yuv444p10le);
  - reported, never graded:
    - `ssim_parts` / `DARK_LUMA` (`ssim_luma` unchanged, now its mean);
    - `black_counts`;
    - `neutral_counts` / `neutral_summary`;
    - in `frame_metrics` / `summarise`, the controls' and every graded arm's `ssim_dark`,
      `ssim_rest`, `dark_share`, `black_keep`;
    - `controls_summary` adds the controls' SSIM, U / V against swscale and `neutral`;
    - `ssim_summary` (printed as `ssim` lines, saved as the score's `ssim`).
- `services/media-probe/recbench.sh`:
  - reads `upload`; uploads it before scale_vaapi (vpp / gctl);
  - a vpp arm's timing input is the same raw bytes declared in it;
  - round 1 and 2's commands are unchanged.
- `services/backend/tests/test_gpu_rec_bench.py`:
  - round 3's table: one change per arm, its references, the order;
  - rounds 1 and 2 upload BGRA;
  - round 2's real score: the same verdict, rates and controls today, and 8.3's proven numbers.
    It runs where the score exists (`GPU_REC_SCORES` points a worktree at the main checkout's);
  - the XV30 layout (swscale's and by hand);
  - 10-bit planes and their inverse;
  - the dark-window SSIM and black kept (the 0.950 of 8.3 row 5);
  - the neutral measure (positive, negative, 10-bit, limited);
  - round 3 end to end on stand-ins, including a 10-bit libx265 stream;
  - round 3's container side with stub tools.
- `docs/records/scorers/gpu_rec_r2_ssim_sim.py`: 8.3's simulation, verbatim as it ran.

### 10.3 What stage 2's phase 1 changed (branch `feat/gpu-recording-stage2`, no GPU, no docker)
- `scripts/media_rec.py` (new): the video side's host half (`VideoFeed`: the job, the pipe, the
  bounded queue and feed thread, the fail-safe, the index, the rename), `prep` / `status`, and the
  offline `check` (every frame against its PNG twin with gpu_rec_bench's metrics and bars, the
  stage-2 bars `STAGE2_BARS`, the latency split, recorder_boxes' comparison).
- `services/media-probe/mediarec.sh` (new): the sidecar's entry, bound read-only into the
  media-probe image (nothing built): one job at a time, round 3's candidate exactly, a watchdog for
  a recorder that never came, a clean stop.
- `compose.yaml`: the long-lived service `media-rec` (profile `mediarec`): media-probe's isolation
  plus exactly three binds (the script read-only, the RAM control directory, the disk's
  `.media-rec`; neither created by Docker), user 1000, 1g, 2 CPUs.
- `scripts/record_session.py`: `--format vpp-hevc444-10-q20 --also-png` (rdp only; the format alone
  is refused); every kept frame offered to the video side, which never blocks the PNG loop; the
  manifest's `video` block, `png_writer_cpu_s`, `cpu_wall_s`, the sidecar's cores in `cpu_cores`;
  `--max-bytes` and the local caps count both files. `RECORDER_VERSION` stays 6 (manifest fields
  and files beside the shards only).
- `services/backend/tests/test_guards.py`: pins the sidecar (isolation, binds, profile, nowhere
  else), its host side's directories, and that the input writer never holds a GPU node.
- `services/backend/tests/test_media_rec.py` (new): the candidate's options, the job regex (and
  bash agrees), each stage-2 bar failing alone, the verdict rule, the latency split, VideoFeed
  against a simulated sidecar (happy, the encoder dying, a stall, no sidecar, two recorders), and
  END TO END with the real `mediarec.sh` and a stub ffmpeg (libx265 4:4:4 10-bit on the CPU):
  `record()` writes the PNG session and its video twin, an encoder crash leaves the PNG session
  whole, then `check` decodes every frame.
- `README.md`: the media services' row.

### 10.4 What stage 3 changed (branch `feat/recording-stage3`, no GPU, no docker)
See 9.4 "What was built" and ADR-0024's "Implementation". The tests: `packages/poring_dataset/
tests/test_frames.py` (the API on synthetic PNG and video sessions: the access-unit split against
libavcodec's, decode alone = in order, the convention and size refusals, a short stream, a cut
shard, the sources), `services/backend/tests/test_video_readers.py` (every switched reader on a
video session gives its PNG twin's frames; the cue studies refuse; dataset_check), and in
`test_media_rec.py` video-only END TO END with the real `mediarec.sh` and the CPU stand-in encoder
(record() writes a video-only session that the API reads back frame for frame; an encoder crash
stops the recording with the frames already in the stream; no sidecar refuses every part).
