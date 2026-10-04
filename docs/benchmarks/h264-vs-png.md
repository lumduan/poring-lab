---
doc_type: design
hypothesis: null
status: ACCUMULATING
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: DECIDED 2026-10-04 -- Batt switched the default to H.264 at IDR 1 s (an override of the pre-registered rule, his reasons below). Training reads a per-session frame cache, not random access (offline seek, below).
---

# Raw H.264 vs PNG datasets: pre-registered (2026-10-04, Post-S2 round Part C)

**Why.** PNG datasets are heavy on the disk shared with live quant capture.
- 10 fps PNG tripped the IO guard (26.5 % quant-postgres stall, 2026-10-03), so Batt chose fps 1.
- fps 1 keeps 1 frame of every 30 the S2 client decodes.

The S2 client already holds the encoded stream: Sunshine's H.264 at ≤ 20 Mb/s, every frame. If the
bitstream decodes bit-identically offline, it IS the dataset. It would cost a fraction of the bytes
per kept frame, and the frames it skips are no longer lost.

**What C1/C2 built** (no image rebuild: dev overlay + host source):
- `s2spike/h264rec.py`: the client writes the Annex-B access units exactly as it feeds them to its
  decoder. Alongside them it writes:
  - an index: AU, frame_id, frame number/type, IDR flag, pts, offset, length, receive time,
    decode-complete time;
  - a 64-bit checksum (crc32 + adler32) of every decoded BGRA frame.

  It is controlled by a control file with a dead-man touch. It starts at an IDR it asks for. An IDR
  timer asks for one every N s.
- `s2spike/h264check.py` (in gamestream, the only place with PyAV) measures three things:
  - **determinism:** re-decode from byte 0, compare every frame's checksum;
  - **random access:** a fresh decoder from the preceding IDR to a random target, converting
    only the target;
  - **decode throughput.**
- `record_session.py --format h264 --idr-every N` drives a recording, moves it into a session
  (`stream.*`), and records the packets, CPU and freeze spans the same way PNG sessions do.

**Dry run** (synthetic, 2026-10-04 09:2x ICT, in gamestream, libx264 1440x900, keyint 60, real-time
30 fps). The plumbing works end to end; this is not a C3 result:

| What | Result |
|---|---|
| Frames recorded | 150/150 |
| Checksums identical | 150/150 |
| Checksums dropped | 0 |
| Decode | 161 fps |
| Seek (31 AUs back to the IDR) | p50 101 ms |
| Checksum cost (benchmarked, 1440x900 BGRA) | crc32+adler32 4.7 ms/frame vs blake2b-128 20.8 ms/frame |

The checksum cost is why the plan's blake2b was replaced: 0.14 vs 0.62 cores at 30 fps.
Determinism of two decodes is not an adversarial question.

## The runs (one variable at a time)

**Common to every run:**
- the S2 session (console, V-S2), outdoor prt_fild08;
- `dataset_activity.py --scene outdoor --seed 20261004`, started with each run, 3 min;
- the quant pressure sampler running throughout.

| Run | Format | Knob |
|---|---|---|
| P1 | PNG | `--fps 1` (today's default) |
| P3 | PNG | `--fps 3` |
| H0 | H.264 | `--idr-every 0` (never ask) |
| H5 | H.264 | `--idr-every 5` |
| H2 | H.264 | `--idr-every 2` |
| H1 | H.264 | `--idr-every 1` |
| H2b | H.264 | `--idr-every 2` again: the **A/A** repeat of H2 |

**Measured per run:**
- write MB/s and MB/min;
- frames kept per second;
- cores: the gamestream and backend containers (cgroup `usage_usec`), plus the recorder process;
- quant io_full: the worst stall and the seconds above 10 % (guard summary + sampler);
- for H.264 only:
  - random-access ms (p50/p95/max);
  - offline decode fps;
  - determinism (identical / compared, missing).

**Baselines already measured** (NAS manifests):
- PNG fps 1: **129.4 MB/min**, 1 frame/s (outdoor, 2026-10-04 05:44, worst stall 8.2 %);
- PNG fps 3: **377.7 MB/min**, ≤ 3 frames/s (probe 05:36, 7.4 %);
- PNG fps 10: 526 MB/min and an IO-guard stop.

## Pre-registered expectations (written before any C3 run)

1. **Determinism:** 100 % of compared frames identical, in every H.264 run. Anything less means
   H.264 is not a dataset format here, whatever else it wins.
2. **Size:** H0 ≤ 150 MB/min, because the bitrate is capped at 20 Mb/s. Expected well below that
   for a mostly static field, ~40–110 MB/min.
3. **Value per byte:** H0 keeps ~30 frames/s, against P1's 1 frame/s at 129 MB/min. That is ≥ 30×
   the frames for ≤ the bytes.
4. **IDR cost:** if Sunshine runs constant-bitrate, MB/min stays within ±20 % across H0/H5/H2/H1
   (IDRs then cost quality, not bytes). Otherwise H1 grows by ≤ +30 % over H0.
5. **Random access, p95:**
   - H1 ≤ 150 ms;
   - H2 ≤ 250 ms;
   - H5 ≤ 600 ms;
   - H0 is bounded only by the distance back to the recording's start (reported, not judged).
6. **Cores:** recording adds ≤ 0.25 cores to gamestream (checksums ~0.14 + writes). P1's cost is
   the backend grab + the PNG encode in the recorder process.
7. **Quant IO:** no H.264 run's worst stall exceeds P1's, and none trips the guard (< 10 % sustained).
8. **A/A:** H2 and H2b agree within ±15 % on MB/min and ±25 % on seek p95. A larger spread means the
   per-run numbers are noise at this length, and the comparison has to say so.

## The C4 decision rule (a proposal to Batt; the default stays PNG until he decides)

Propose H.264 as the dataset format, at the IDR interval with the smallest MB/min whose seek p95 is
≤ 250 ms, only if ALL of the following hold:
- determinism is 100 %;
- MB/min ≤ P1's;
- the quant stall ≤ P1's;
- the A/A agrees.

Otherwise PNG fps 1 stays, and the report says which condition failed. Consumers that need pixels
(qa_export, label_iou, training) would then read frames through `h264check`'s decoder from the
nearest IDR. That integration is NOT built until Batt approves.

## Results

*(appended after the S2 session, below this line, never above it)*

### C3, 2026-10-04 (the S2 session, 10:51–11:32 ICT = 03:51–04:32 UTC)
**The conditions:**
- the S2 client (V-S2, 60 fps requested, ~30.4 delivered), outdoor prt_fild08;
- `dataset_activity.py --scene outdoor --seed 20261004 --spawn-every 60`: 22–24 walks per run;
- 3 min per run, one after another.

**A first attempt was discarded.** The driver's hover check missed the ground marker over grass,
so the run had 4 walks. It was fixed (`empty_cell.py`) and all seven runs were restarted. The
discarded run's session was deleted unshipped.

**Every session is on the NAS, verified:** `20261004T105213-console-c3-p1` … `T112733-…-c3-h2b`.

| Run | Format | IDR | MB/s | MB/min | Frames kept/s | MB per kept frame | Cores: gamestream / backend / recorder | quant-postgres io_full avg (worst 10 s bin) | IDRs | Identical / compared | Seek p50 / p95 / max ms | Decode fps |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P1 | PNG fps 1 | — | 2.07 | **124.2** | 1.00 | 2.072 | 0.709 / 0.107 / 0.235 | 2.85 % (4.9) | — | — | — | — |
| P3 | PNG fps 3 | — | 6.24 | 374.7 | 3.00 | 2.084 | 0.720 / 0.139 / 0.758 | 3.93 % (8.0) | — | — | — | — |
| H0 | H.264 | none | 0.53 | **32.1** | 30.36 | 0.018 | 1.072 / 0.063 / 0.004 | 3.30 % (6.4) | 1 | 5514 / 5514 | 20566 / 33140 / 33140 | 103.1 |
| H5 | H.264 | 5 s | 0.64 | 38.3 | 30.48 | 0.021 | 1.111 / 0.064 / 0.003 | 3.60 % (7.6) | 37 | 5541 / 5541 | 447 / 1174 / 1174 | 98.6 |
| H2 | H.264 | 2 s | 0.79 | 47.5 | 30.73 | 0.026 | 1.163 / 0.067 / 0.003 | 4.47 % (7.0) | 91 | 5566 / 5566 | 304 / 569 / 569 | 88.2 |
| H1 | H.264 | 1 s | 0.68 | 40.7 | 31.33 | 0.022 | 1.176 / 0.371 / 0.003 | 2.71 % (5.1) | 182 | 5690 / 5690 | 145 / 314 / 314 | 101.2 |
| H2b | H.264 | 2 s (A/A) | 0.79 | 47.1 | 30.73 | 0.026 | 1.177 / 0.377 / 0.004 | 2.95 % (5.9) | 91 | 5599 / 5599 | 263 / 495 / 495 | 99.0 |

Notes:
- No run tripped the IO guard, and no 10 s bin of any quant cgroup exceeded 10 % in the whole
  session (worst 8.2 %, P3).
- Every H.264 set is complete: no dropped checksum, no undecodable unit, no queue overflow, no
  gap.
- The offline check ran in gamestream WHILE the stream continued (the next run waited for it), so
  its decode fps and seek times are measured on a contended decoder.
- Backend 0.37 cores in H1/H2b against 0.06 earlier is not explained by the recorder (it does not
  touch the backend). A console viewer opening is the likely cause; it is not verified.

### Against the pre-registration
| # | Expectation | Result | Verdict |
|---|---|---|---|
| 1 | 100 % identical | 5 runs, 27,910/27,910 frames identical | ✅ |
| 2 | H0 ≤ 150 MB/min (expected ~40–110) | 32.1 | ✅ (below the expected band) |
| 3 | ≥ 30× the frames for ≤ P1's bytes | 30.4 frames/s at 32–48 MB/min vs 1/s at 124: **2.6–3.9× fewer bytes, ~30× the frames, 80–115× less per kept frame** | ✅ |
| 4 | IDR cost: CBR ±20 % across arms, else H1 ≤ +30 % over H0 | H5 +19 %, H1 +27 %, H2 +48 % (A/A +47 %): **not monotonic** (H1 < H2) | ⚠️ inconclusive: the scene's own variation is as large as the IDR effect |
| 5 | seek p95: H1 ≤ 150, H2 ≤ 250, H5 ≤ 600 ms | 314 / 569 (A/A 495) / 1174 | ❌ all about 2× the expectation (a contended decoder at ~100 fps ≈ 8–10 ms per access unit) |
| 6 | recording adds ≤ 0.25 gamestream cores | +0.36 to +0.47 (vs P1's 0.709) | ❌ — but the lab TOTAL is 1.14–1.23 cores vs P1's 1.05 and P3's 1.62: the PNG encode in the recorder process is gone |
| 7 | no H.264 run's worst stall above P1's | 5.1–7.6 % vs P1 4.9 %; averages 2.7–4.5 % for all seven | ❌ as worded; all within the session's background (no guard trip, no bin > 10 %) |
| 8 | A/A within ±15 % MB/min, ±25 % seek p95 | −0.8 % and −13 % | ✅ |

### C4: the pre-registered rule and the proposal (Batt decides; the default stays PNG)
**The rule:** propose H.264 only if ALL hold. The result:
- determinism ✅;
- MB/min ≤ P1's ✅;
- quant stall ≤ P1's ❌, as worded;
- A/A ✅;
- seek p95 ≤ 250 ms at the chosen interval ❌ (best: H1 314 ms).

**⇒ By the rule, PNG fps 1 stays the default.** The two failing conditions are random-access
latency and a stall comparison that sits inside the background noise.

**The proposal for Batt** (his decision): H.264 with an IDR every 1 s, after one more measurement:
the seek on an IDLE decoder, not gamestream mid-stream.
- **For:**
  - ~3× fewer bytes than fps 1 PNG while keeping EVERY frame instead of 1 in 30;
  - bit-identical offline decode;
  - the recorder costs less than the PNG encoder in total cores.
- **Against:**
  - a frame costs ~150–300 ms to reach;
  - every consumer (qa_export, label_iou, training) needs a decoder: PyAV lives only in the
    gamestream image today;
  - the dataset format (ADR-0010) changes.
- **If accepted:**
  1. an ADR-0010 amendment;
  2. a frame reader in `poring_dataset` (PyAV in the host env or a decode service);
  3. `qa_export` reading `stream.h264`;
  4. then the switch of `record_session.py`'s default.

### Offline seek re-measure (pre-registered 2026-10-04 12:4x ICT, BEFORE the run)
**Why:** Batt's C4 decision (2026-10-04) noted that C3's seek was measured on a CONTENDED decoder
(`h264check` in gamestream while the stream ran).

**Conditions:**
- the host, R1 at rest (no stream running), normal priority;
- the stream file held in memory (no IO in the timing);
- the reader that training and QA use (`poring_dataset.h264`): the live decoder's configuration
  (LOW_DELAY, 2 slice threads), a fresh decoder per GOP, BGRA conversion of the returned frames
  only, and every returned frame checked against the live checksum.

**Arms:** sessions H1, H2 and H5 (IDR every 1, 2, 5 s). Per session:
- N = 200 random single frames (from the preceding IDR to the target);
- N = 200 random 16-frame clips;
- seed 20261004.

**Reported:** p50 / p95 / p99 ms, ms per useful frame, AUs decoded, the host's load average.

**Expected** (from the dry run's ~6 ms per access unit uncontended):
- H1 single-frame p50 ≤ 100 ms, p95 ≤ 200 ms;
- H1 16-frame clip p50 ≤ 250 ms (≤ 16 ms per frame);
- H2 ≈ 2× and H5 ≈ 5× H1's from-IDR distance.

A caveat already known before the run: the host determinism pass ran at `nice 10` and reached only
44–50 frames/s (decode + conversion + checksum). The host is shared with Frigate and the quant
stack, so "uncontended" here means no stream, not an idle machine.

#### Results (2026-10-04 12:34–12:51 ICT = 05:34–05:51 UTC; host: 64 cores, load average 9–16)
The stream was not running (R1). The HOST was not idle: Frigate, the quant stack and Ollama ran as
usual (load 9–16).

| Arm | Session | Single frame p50 / p95 / p99 ms | AUs decoded (p50) | 16-frame clip p50 / p95 / p99 ms | ms per clip frame |
|---|---|---|---|---|---|
| live config (2 threads), verify | H1 (IDR 1 s) | **196.8 / 304.7 / 353.0** | 17 | **733.6 / 948.6 / 1090.5** | 45.9 |
| live config, verify | H2 (IDR 2 s) | 319.8 / 567.9 / 683.7 | 31 | 909.3 / 1298.0 / 1411.1 | 56.8 |
| live config, verify | H5 (IDR 5 s) | 652.7 / 1235.2 / 1346.0 | 80 | 1157.6 / 1791.2 / 2144.5 | 72.3 |
| 4 slice threads, verify (N = 100) | H1 | 171.2 / 254.9 / 306.6 | – | 720.2 / 857.7 / 1030.7 | 45.0 |
| 4 slice threads, no per-read verify (N = 100) | H1 | 152.6 / 243.1 / 260.7 | – | 537.2 / 637.9 / 771.0 | 33.6 |

**Where a frame's time goes** (H1, the same host):

| Step | Cost |
|---|---|
| decode | 12.6 ms per access unit (2 slice threads) / 6.0 ms (4 threads; Sunshine sends 4 slices) |
| BGRA conversion | 2.5 ms per frame |
| the checksum | 9.0 ms per frame |

4 threads kept every checksum identical: the output stays bit-exact.

**Against the pre-registration: all FAIL.** H1 single p50 197 vs ≤ 100 ms, p95 305 vs ≤ 200; clip
p50 734 vs ≤ 250. H2 and H5 scale as expected with the IDR distance.
- **The pre-registration's basis was wrong.** It extrapolated from the synthetic libx264 dry run;
  Sunshine's real stream costs ~2× more per access unit, on a loaded host.
- **The C3 numbers were not "the contended decoder" either.** The in-gamestream check (H1 p50/p95
  145/314) was about as fast as this offline host run.

**Consequence (for the Phase 3 plan):** random access is NOT how training should read H.264.
- One sequential pass per session (~6–13 ms per access unit decode-only, converting only the
  sampled frames) builds a frame cache, and training reads the cache.
- The full checksum pass (`dataset_check.py`) runs once per session; per-read verification is then
  optional.

### C4: DECIDED by Batt (2026-10-04): H.264 with an IDR every 1 s is the default
Batt overrode the pre-registered rule. In his words, the failed criteria measured the wrong thing:
- the seek was measured on a contended decoder;
- the cores criterion counted gamestream only;
- the stall comparison sat within background noise.

**Implemented:**
- `record_session.py`:
  - h264 by default on console (IDR 1 s), png on rdp;
  - `--format png --fps 1` stays selectable;
  - the S2 client's limits are checked up front;
  - recorder v5.
- The reader `poring_dataset.h264`: GOP decoding, clips, freeze spans, the per-frame checksum,
  the decoder-build check.
- `scripts/dataset_check.py`: a full determinism pass on the HOST after shipping. On the 5 C3
  sessions it found **27,910 / 27,910 frames identical**: the host build equals the live client's.
- `qa_export.py` reads either format.

