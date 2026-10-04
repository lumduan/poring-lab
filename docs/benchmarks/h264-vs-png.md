---
doc_type: design
hypothesis: null
status: ACCUMULATING
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: Run C3 (seven 3-min runs) in the one S2 session; append results below; C4 = a proposal to Batt, the default stays PNG until he decides.
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
