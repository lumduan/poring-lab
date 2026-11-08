---
doc_type: design
hypothesis: "Recording the RDP path's GAME_REGION frames with the Arc A380's hardware video encoder (VA-API, low-power VDEnc) instead of today's 1-fps lossless PNG cuts the recorder's CPU per frame and the bytes per hour by a large factor, makes 5-10 fps recordings fit bot-server's disk, and keeps what the frames are used for (detector boxes, UI text, colour cues) within pre-registered bars against the PNG originals."
status: "PROPOSED 2026-11-08. Phase 2 RUN 17:14-17:52 ICT: VALID, NO CANDIDATE (section 8). The closest arm hevc444-q20 passes every quality, parity and size bar (5-7 x smaller than PNG, 43.5 dB vs JPEG q95 32.9) and fails only S2 (21.9 ms CPU a frame vs 15). Adoption needs Batt's decision and an ADR-0010 amendment (section 3)."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../adr/0010-dataset-format.md, bot-server-migration.md, ../benchmarks/h264-vs-png.md, ../benchmarks/v0-png-vs-jpeg.md, ../adr/0005-vision-x-access.md, ../adr/0019-windows-stays-clean.md, ../adr/0022-vendor-neutral-accelerators.md, ../../scripts/gpu_rec_bench.py, ../../services/media-probe/recbench.sh, ../../scripts/record_session.py]
next_action: "Batt: (a) an amendment for a GPU-side colour conversion (vpp with the right range, 4:4:4 if possible) graded on the same bars, or (b) revisit S2's bar (0.1 x PNG); then stage 2 (one side-by-side recording, section 9)."
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
| The VA-API JPEG path has a colour-range defect (washed out) | idem |
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
| an encoder failure mid-session | that session | the recorder stops with a `stop_reason` (fail closed), never a silent PNG fallback | stage 2's code |
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
- **Not answered by this run:** Batt's "faster" for training (the trainer reads the JPEG cache,
  section 4); the second hop's cost (stage 2).
- **Next (an amendment BEFORE any re-run, Batt's go):** a GPU-side conversion with the right range
  (and 4:4:4 if `scale_vaapi` / the VPP can output it), graded on the same bars; or a decision on
  S2's bar itself (it was set at 0.1 x PNG; the arm is 0.14-0.24 x).

## 9. The staged plan (question 5)

```text
stage 0  design + bench, bars pre-registered        (this commit)
   |
stage 1  the bench on real frames (section 7)        -> a candidate arm, or "no"
   |       "no": record it; PNG stays (stop here)
   |
stage 2  ONE side-by-side recording (Batt's go)       -> the full-session bars
   |       the media-rec sidecar + record_session --format <candidate> --also-png:
   |       every kept frame to BOTH writers. Bars, pre-registered before it:
   |       sizes and the recorder's CPU (CpuMeter, the hop included), the detect
   |       server's p50 / p95 with and without the encoder, recorder_boxes on both,
   |       every frame decoded and checked
   |
stage 3  ADR-0010 amendment (Batt decides)            -> which format for which purpose
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
