---
doc_type: design
hypothesis: "The live box watcher's detection moved to the GPU (~22-45 ms a detection instead of ~200-340 ms on 16 CPU threads, the same boxes in FP32) cuts the grab-to-click time that made p7's box strikes miss walking monsters (rogue-xmas02.md 4M), within R1-R3 and without opening a new input or X path into vision."
status: "LIVE 2026-11-07: Batt chose option A ('เลือก A') and approved the GPU for the bot's detection ('อนุมัติให้ใช้ gpu แทน cpu ในการ detect ของ bot ได้เลย'). ADR-0005 Amendment 2026-11-07. Built 61a04ca; the live path PASSED (section 6a: parity 1.000, the fallback in R3's pauses); pilot p8 PASSED G1 / G2 and R3 (section 7: 98.5 % GPU-served outside the pauses, 94 vs 305 ms, R3 median -0.50 ms over 4 kept pairs), so dungeon_hunt's box watcher uses the GPU by default (the CPU behind it)."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../benchmarks/cpu-detector-speed.md, rogue-xmas02.md, ../adr/0005-vision-x-access.md, ../operations/vision-long-lived.md, ../operations/r3-paired.md, ../../scripts/unit_detector.py, ../../services/vision/src/poring_vision/bench_gpu.py]
next_action: "Run the detect server as a guarded execdev step beside every dungeon_hunt run that should use the GPU (docs/operations/detector-cpu.md 'The GPU path'). Possible later work: the server's forward is 37-38 ms vs ultralytics' 22-29 (section 6a)."
title: "The live detector on the GPU: how the host bot's frames reach it (options)"
date: 2026-11-07
owner: Batt
---

# The live detector on the GPU (ACCEPTED: option A)

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
2. **`poring_vision.detect_server`:** serves one client at a time (➡️ since 2026-11-12 several,
   decisions first: ADR-0005 Amendment 2026-11-12), under the VRAM cap, FP32,
   per-model groups as `unit_detector` (species collapsed before NMS).
3. **`unit_detector.GpuDetector`:** the same `detect()` interface. A timeout (e.g. 150 ms) falls
   back to the CPU detector, so R3's pauses and a stopped worker never blind the bot. The box
   watcher logs which path gave each box.
4. **The guarded long step:** `execdev:vision@<run length>` for the detect server beside a live
   run, under the paired R3 monitor and the duty rules.
5. **A pre-registered pilot:** the CPU and GPU box watchers interleaved, together with the
   latency fix p7 asked for (a detection right after the settle, one hover). Measured: grab-to-hover
   time, SWORD share at the box, kills an hour; R3's delta on Frigate over the run.

## 5. Decision and the build (2026-11-07)
- **Batt:** option A ("เลือก A"); the bot's detection may use the GPU instead of the CPU
  ("อนุมัติให้ใช้ gpu แทน cpu ในการ detect ของ bot ได้เลย"). ADR-0005 Amendment 2026-11-07.
- **One change from section 4's sketch, for parity:** the host keeps the letterbox, the decoding
  and the NMS (`scripts/detector_worker.py`'s own functions). The GPU server runs only the forward
  pass and returns the head's raw output. So the CPU and GPU paths differ only in the forward
  (ONNX on the CPU vs torch FP32 on the GPU), and the species collapse needs no second copy.

## 6. The live path's positive case (pre-registered BEFORE it runs, 2026-11-07)
The build (61a04ca) is unit-tested with a stand-in net. This run proves the real path: the worker's
detect server on the GPU, the host's `GpuDetector`, the deployed models.

- **Steps (Saturday: no market-window rule):**
  1. The worker, through quiet_start (today Frigate's IO is left out of the start's gate,
     `io_baseline.FRIGATE_IO_IGNORED`; quant still gates):

         python3 scripts/runbooks/quiet_start.py --quiet-min 10 --limit 25 -- \
             python3 scripts/guarded_build.py --sustain 30 --spike 25 worker:vision@120

  2. ADR-0005's acceptance inside the worker, after the mount change (the ADR's own rule):

         python3 scripts/guarded_build.py --threshold 30 --sustain 30 \
             'execdev:vision@180=python /opt/acceptance/adr0005.py'

  3. The detect server for 900 s (a short step: R3's 60 s ON / OFF windows), the command
     `scripts/unit_detector.py serve-cmd --seconds 900` prints, and beside it, once it listens,
     under the scratch memory cap:

         systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 \
             .venv/bin/python scripts/gpu_live_parity.py \
             --refs /mnt/poring-lab-datasets/archive/train/eval/xmas02/latency-200-refs.json \
             --out /dev/shm/poring-lab-tmp/gpu-live/parity.json --soak-s 300 --soak-hz 2

     The 200 frames are this morning's (section 8 of the benchmark), read from the NAS.
- **Bars:**
  - **P1 parity (the deciding bar):** for each deployed model (v1 for prt_fild08, xmas02 with
    its species collapse for xmas_dun02), matched / CPU boxes >= 0.99 AND matched / GPU boxes
    >= 0.99, one to one at IoU >= 0.7 with the same class and species. Expected 1.000: this
    morning's FP32 parity with ultralytics' own pre- and post-processing was 1.000, and now
    only the forward differs.
  - **P2 served:** every frame gets GPU boxes within 240 s (an R3 OFF window is 60 s).
  - **P3 the fallback, live:** in the 300 s soak at 2 Hz, every call returns boxes. Calls during
    R3's OFF windows are the CPU's, each with its reason, and after each `R3 unpause` the GPU
    serves again within 6 s (GPU_RETRY_S 5 s + one call). If no OFF window falls in the soak, P3
    is reported as not exercised.
  - **P4 speed:** the GPU call on the host's clock (the frame to the decoded boxes, socket
    included) p50 <= 60 ms (the benchmark's call: 22-29 ms).
  - **Acceptance:** rows 1, 2, 3, 5 and 6 PASS; row 4 SKIPs without an S2 stream (as on
    2026-10-04 09:4x).
- **Reported beside them:** our process's GPU memory, R3's pairs (a verdict is unlikely in 15
  min), any relaxed camera drops, the worst capture stall.
- **A FAIL of P1 or the acceptance:** no live run on the GPU; the cause is found first. A FAIL of
  P3 or P4: reported, and the pilot waits for a fix.

### 6a. RESULT (2026-11-07 12:26-12:55 ICT): PASS (P1-P4 and the acceptance); pilot p8 may run
- **The worker:** quiet_start waited 12:26:38-12:36:38 (10 quiet minutes; Frigate left out of the
  start's gate today), then started it 12:36:39-12:38:44: idle, no CUDA context, worst capture
  stall 0.3 %. The new mount read back: `/detect <- /dev/shm/poring-lab-detect (rw)`, the
  directory `drwx------ batt`.
- **ADR-0005 acceptance inside the worker (12:39:0x):** rows 1 (no X), 2 (the public listener
  refused, with and without a forged Origin: all 403), 3 (`/internal/agent` works), 5 (the
  network closed) and **6 (`/detect` is tmpfs, empty)** PASS; row 4 SKIP (no S2 stream), so the
  script exits 3 as designed (guarded_build prints `FAILED rc=3` for it).
- **The detect server:** 12:39:56-12:55:01, listening from 12:40:2x with both pinned weights
  (`v1 03d539796183`, `xmas02 5c5bb67a746b`). The socket was `srw------- batt`, removed at the
  end. It ended at its 900 s time box (`rc=124`: `timeout` ends a server this way); the stop was
  verified (the worker idle, nothing of ours on the GPU).

| bar | result | verdict |
|---|---|---|
| P1 parity, v1 | 59 CPU / 59 GPU boxes, 59 matched (1.000 / 1.000), largest coordinate difference 0.1 px | PASS |
| P1 parity, xmas02 (collapsed) | 533 / 533, 533 matched (1.000 / 1.000), 0.1 px | PASS |
| P2 served | 0 of 400 frames unserved (51 fallbacks while paused, each retried) | PASS |
| P3 the fallback, live | soak 12:44:09-12:49:08, 599 calls at 2 Hz, every one with boxes. Outside OFF windows 339 / 354 by the GPU (95.8 %); inside them 243 / 245 by the CPU. The GPU served again 3.5 s and 4.1 s after the two unpauses (bar 6 s) | PASS |
| P4 speed | the GPU call on the host's clock p50 51.8 / 49.1 ms, p95 72.1 / 64.1 ms (v1 / xmas02; bar p50 <= 60) | PASS |

- **The fallbacks' reasons (soak):** 233 `down` (inside the 5-s retry gap: no time lost), 18
  `BlockingIOError` (a paused server's full backlog refuses the connect at once), 7
  `TimeoutError` (250 ms lost, then the CPU). A fallback call took 245 ms p50 and 752 ms at most
  (a timeout, then a CPU detection).
- **Where the time goes:** the server's own forward (the canvas to the GPU, the forward, the output
  back) is 37-38 ms p50. That is slower than this morning's ultralytics predict (22-29 ms);
  the socket and the host's decode add ~11 ms. It still beats 16 CPU threads (194-339 ms) by
  4-7x. Shortening it is possible later work, not a blocker.
- **How heavy:** our process held 336 MiB with both models; the card went 3,529 -> 3,870 MiB.
- **R3:** 2 pairs, neither kept (Frigate's load 14.0 vs 22.0 and 10.5 vs 15.7 detections/s),
  deltas -0.35 / -0.36 ms: no verdict. No relaxed camera drops. Worst capture stall 22.4 %
  (quant-ticker-engine), 0 s above the step's 30 %.
- Scratch: `/dev/shm/poring-lab-tmp/gpu-live/` (parity.json, the logs, the GPU sampler), to the
  NAS today.

## 7. Pilot p8 on the GPU (rogue-xmas02.md 4N; 2026-11-07 12:56-13:36 ICT): G1, G2 and R3 PASS
- **G1:** of the detections that asked for the GPU outside R3's OFF windows, the GPU served 1,063
  / 1,079 (98.5 %; bar 90 %). The 16 others: 15 `down` (the 5-s retry gap after an unpause), 1
  `BlockingIOError`. Inside the OFF windows 2 / 724 (the pause edges).
- **G2:** the box target's fresh detection, request to boxes, p50 94 ms when the GPU served it vs
  305 ms when the CPU did (bar <= 100 and <= half).
- **R3 over the run: PASS** (4 kept pairs, median -0.50 ms; then 27-min monitoring). No relaxed
  camera drops; worst capture stall 12.0 %. During R3's measuring phase the worker was paused
  half the time (180-s windows), so ~41 % of the run's detections were the CPU's: by design.
- **How heavy, live (1 Hz + the box targets' requests):** 336 MiB; GPU-wide utilization 15.8 %
  unpaused vs 12.5 % paused, power +0.6 W (confounded).
- **Decision (pre-registered):** `dungeon_hunt.py --box-detector gpu` is the default; `cpu` is
  the rollback. Without a detect-server step the CPU serves alone (the socket is absent: no time
  lost).
- p8's own runner bars (E1 kills, E2 box misses) FAILED: rogue-xmas02.md section 5.
