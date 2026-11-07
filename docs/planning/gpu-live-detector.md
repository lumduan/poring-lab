---
doc_type: design
hypothesis: "The live box watcher's detection moved to the GPU (~22-45 ms a detection instead of ~200-340 ms on 16 CPU threads, the same boxes in FP32) cuts the grab-to-click time that made p7's box strikes miss walking monsters (rogue-xmas02.md 4M), within R1-R3 and without opening a new input or X path into vision."
status: "PROPOSED 2026-11-07 (Batt ~09:2x: 'move it; before moving, report how heavy the GPU use is'). The report: docs/benchmarks/cpu-detector-speed.md sections 7-8. Batt picks the option below; nothing is built."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../benchmarks/cpu-detector-speed.md, rogue-xmas02.md, ../adr/0005-vision-x-access.md, ../operations/vision-long-lived.md, ../operations/r3-paired.md, ../../scripts/unit_detector.py, ../../services/vision/src/poring_vision/bench_gpu.py]
next_action: "Batt chooses A, B or C (section 3). Then the chosen option's ADR amendment (if any), the build with tests, and a pre-registered pilot against the CPU box watcher."
title: "The live detector on the GPU: how the host bot's frames reach it (options)"
date: 2026-11-07
owner: Batt
---

# The live detector on the GPU (PROPOSED, options)

## 1. What is measured (cpu-detector-speed.md sections 7-8)
- **Speed:** 22-29 ms per detection on the RTX 5060 Ti (bare forward 18-20 ms). At 10 Hz it is
  45 / 59 ms (p50 / p95). Against 16 CPU threads on the same frames, the same hour: 194-212 /
  238-339 ms.
- **The same boxes:** in FP32 the GPU's monster boxes equal the CPU's one for one (v1 49 / 49,
  xmas02 340 / 340). FP16 is not faster.
- **How heavy:** 360 MiB of GPU memory; ~17-19 % of the GPU's compute when busy, ~10 % averaged,
  at 10 Hz.
- **R3 (Frigate's detector):** no verdict, 2 unmatched pairs at -2.0 / +4.1 ms.
- **Why it matters (rogue-xmas02.md 4M):** 13 of 18 fresh boxes sat on their monster at the grab,
  and those monsters had walked away by the hover 1.2-1.6 s later. A box survives 72 % at the grab,
  50 % 0.4 s later, 28 % from 0.8 s on.

## 2. The constraints
- **R1-R3** (CLAUDE.md rule 5): GPU work runs as a guarded step (`guarded_build.py`), never as an
  unguarded host process. A long run lives under the paired R3 monitor (27 min ON / 3 min OFF by
  `docker pause`: during an OFF window the GPU detector is frozen).
- **The R2 co-tenant rule:** fit-first's VTON is never touched. Ours needs its cap + 1 GiB free
  at the start; we have 360 MiB.
- **ADR-0005 (vision isolation):**
  - vision reads the S2 frame bus only, has no X access and lives on the internal agent network;
  - the RDP frame ring is backend-private.
  - **The live runs use the RDP path today**, so vision cannot see their frames.
- **ADR-0002 / rule 1:** a detector returns boxes only. No input path, no packet data.
- **Rule 7:** RAM environments count toward /dev/shm's 4 GB.

## 3. The options
| | how the frames reach the GPU | what changes | cost / risk |
|---|---|---|---|
| **A (recommended)** | the host bot sends each frame over a unix socket in a RAM directory mounted ONLY into the vision worker; a detect server there (a long `execdev:vision` step) answers with the boxes; `unit_detector` gets a `GpuDetector` with the CPU detector as its fallback | an ADR-0005 amendment: frames IN, boxes OUT through that one socket (no input, no X, no network); the worker's compose gets the mount; the box watcher picks GPU or CPU per call | ~2-5 ms to copy a frame; during R3's OFF windows (3 min of every 30) the fallback serves the CPU boxes |
| B | the live bot moves to the S2 console path, where the worker reads the frame bus itself and returns boxes over the same kind of socket | the live runs switch from RDP to S2 (ADR-0014 names S2 the bot's primary path, but the runs and all their checks have used RDP lately) | the largest change: every live check re-proven on S2 |
| C | a GPU onnxruntime environment on the host, in RAM | none in the containers | it bypasses guarded_build's R1-R3 enforcement (not allowed as the rules stand); a ~2-3 GB RAM environment (rule 7) |

## 4. A's plan, if chosen (each step its own commit; the pilot pre-registered)
1. **ADR-0005 amendment:** the socket directory (e.g. `/dev/shm/poring-lab-detect`), its one
   protocol (detector_worker's: frame bytes in, JSON boxes out), mounted read-write ONLY in the
   vision worker and read by host scripts; `test_guards.py` pins it.
2. **`poring_vision.detect_server`:** serves one client at a time, under the VRAM cap, FP32,
   per-model groups as `unit_detector` (species collapsed before NMS).
3. **`unit_detector.GpuDetector`:** the same `detect()` interface. A timeout (e.g. 150 ms) falls
   back to the CPU detector, so R3's pauses and a stopped worker never blind the bot. The box
   watcher logs which path gave each box.
4. **The guarded long step:** `execdev:vision@<run length>` for the detect server beside a live
   run, under the paired R3 monitor and the duty rules.
5. **A pre-registered pilot:** the CPU and GPU box watchers interleaved, together with the
   latency fix p7 asked for (a detection right after the settle, one hover). Measured: grab-to-hover
   time, SWORD share at the box, kills an hour; R3's delta on Frigate over the run.
