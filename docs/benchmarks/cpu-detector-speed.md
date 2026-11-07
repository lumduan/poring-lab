---
doc_type: benchmark
hypothesis: "The bot's slow boxes (2-4 frames a second) come from the model's CPU inference itself, not from the remote display path: Batt's local-PC run of the teaching kit showed 150-435 ms a frame too."
status: "MEASURED 2026-11-06 21:47-21:56 ICT on the lab server (Xeon E5-2695 v4, 64 logical CPUs) while the xmas02 training ran beside it (load average 10 -> 38). ➡️ 2026-11-07: the lab PC measured too (section 6: i5-10500T best 95.5 ms vs the server's 110.3, same kit and pictures); the GPU (sections 7-8): ~22-29 ms a detection, ~7-9x the 16-thread CPU; FP32 parity 1.000 with the CPU boxes; 360 MiB and ~10-19 % of the GPU at 10 Hz; R3 no verdict (2 unmatched pairs, -2.0 / +4.1 ms)."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../../teaching/simple-bot/simple_bot.py, ../../scripts/unit_detector.py, ../../scripts/detector_worker.py, gef10-eval.md, xmas02-eval.md]
next_action: "DECIDED 2026-11-07 ~05:5x (Batt): the live bot goes to 16 threads (unit_detector.THREADS, done 8d2ab43); the Windows --bench ran ONCE on the lab PC (section 6, ADR-0019 one-off, removed); Batt 2026-11-07 ~09:2x: MOVE the live detector to the GPU after this report (section 8: how heavy). ➡️ DONE 2026-11-07: Batt chose option A; built, proven and live (docs/planning/gpu-live-detector.md sections 5-7)."
title: "How fast is the v1 detector on a CPU? Threads, the live worker path, INT8"
date: 2026-11-06
owner: Batt
---

# How fast is the v1 detector on a CPU? (2026-11-06)

Batt (~21:3x): even running the teaching kit on the PC with the RO client, the boxes come slowly
(the kit's HUD showed detect 144-435 ms, 2-4 fps), so the delay is not the remote path. Measured
here on the 20 prt_fild08 sample frames (1280 x 720), the v1 model (YOLO11n, ONNX, 1 x 3 x 736 x
1280), onnxruntime 1.31.1 CPU. The server was busy: the xmas02 training (GPU + its loader), quant,
Frigate; load average 10 at the first run, 23-38 later. Every number below is a p50 / p95 of 30-40
timed detections after 3-6 warm-up runs.

## 1. Threads (`simple_bot.py --bench`, in-process, nice 0, load ~10-14)

| threads | p50 ms | p95 ms | fps |
|---|---|---|---|
| 1 | 436.5 | 471.4 | 2.28 |
| 2 | 274.8 | 340.7 | 3.55 |
| 4 | 179.4 | 231.7 | 5.36 |
| 8 | 145.3 | 176.1 | 6.81 |
| 16 | **110.0** | **123.6** | **9.00** |
| auto (0) | 458.0 | 607.4 | 2.18 |

- **onnxruntime's auto threads is the SLOWEST** setting here: it starts one thread per physical core
  (32) and they busy-wait ("spin") against everything else on the machine.
- Spinning off (`session.intra_op.allow_spinning = 0`, load ~23): auto 507 -> 281 ms, but fixed
  counts get slower (8: 159 -> 243 ms; 16: 123 -> 210 ms). Best: spinning on, a fixed 16.
- **The kit's default is now half the logical CPUs, at most 8** (never auto), with `--threads N`.

## 2. The live bot's path (`unit_detector.UnitDetector`: a worker process, 8 threads, nice 10)

- Round trip p50 227.6 / p95 572.4 ms; the worker's own inference p50 219.1 / p95 562.9 ms: **the
  pipe costs ~8.5 ms**; the time is the model's.
- In-process at nice 10 (load ~26): 8 threads 147.5 / 193.7 ms, 16 threads 129.3 / 145.7 ms. So
  nice 10 is not what slows it.
- Alternating the two paths frame by frame in one run (load ~23): medians close (8 threads: kit 250
  vs live 270 ms; 16: 199 vs 227 ms) but the live worker had a long tail (p95 792 / 523 vs 274 / 256
  ms). That A/B ran two spinning sessions on the same CPUs, so the tail is partly its own artefact.
- **The machine's load sets the speed:** 8 threads gave 145 ms at load ~10 and 250 ms at load ~23.

## 3. INT8 (onnxruntime static quantization, QDQ, per-channel, calibrated on the 20 samples)

- The whole model in INT8: 102.7 / 112.3 ms at 8 threads (-33 %) but **0 boxes**: the Detect head
  concatenates box coordinates (0-1280) and class scores (0-1) in one tensor, which one 8-bit scale
  cannot hold.
- The head (`/model.23/`, 84 of 320 nodes) kept in FP32: 44 of the FP32 model's 47 boxes matched at
  IoU >= 0.7 (3 lost), and **no speed-up left** (8 threads 151 vs 157 ms; 16: 117 vs 132 ms). This
  Broadwell Xeon has no VNNI; a newer CPU might gain more (a PC's `--bench` with an INT8 file would
  show it). Not worth it here.

## 4. What would make the boxes faster (candidates, not decided)

1. **The GPU for the live detector** (the RTX 5060 Ti): YOLO11n at 1280 is typically a few ms on a
   GPU, against 110-270 ms here. The biggest lever by far, and Batt's decision: the hunt detector
   stays on the CPU until Batt decides (GPU rules R1-R3, fit-first's VTON co-tenant). A short guarded
   GPU measurement would come first.
2. **16 threads for the live bot** (`unit_detector.THREADS = 8` today): ~15-25 % faster when the
   machine has room; more threads also compete harder with quant and Frigate on a busy host.
3. **A smaller detection area**: the model sees 1280 x 736; a crop of ~768 x 448 around the
   character is ~2.7x fewer pixels (roughly that much faster), but needs an ONNX exported at that
   size (after the training, on the vision worker) and sees less of the field (the search wants
   width; fights do not).
4. **Detection beside the loop** (a background thread): the loop acts on the latest boxes instead of
   waiting for each inference; the boxes are no fresher, but clicks are not delayed by them.
5. INT8: not on this CPU (3 above).

## Raw outputs

`/dev/shm/poring-lab-tmp/bench-server.txt` (the kit's BENCH_JSON line) and the scratch scripts
`/dev/shm/poring-lab-tmp/bench/{spin,prod,prod2,ab,int8}.py` (archived to the NAS scratch-archive
the same day).

## 5. The GPU measurement (written 2026-11-07 06:16 ICT, BEFORE it runs; a measurement, no bar)

Batt (~05:5x): "Compare: how much faster would the GPU be?" One guarded `execdev:vision` step in
the vision worker (R1-R3, fit-first's VTON never touched), `poring_vision.bench_gpu`:

    python3 scripts/runbooks/quiet_start.py --quiet-min 10 --limit 25 -- \
        python3 scripts/guarded_build.py --sustain 30 --spike 25 worker:vision@120
    python3 scripts/guarded_build.py --sustain 30 --spike 25 'execdev:vision@1080=python -m
        poring_vision.bench_gpu --refs /datasets/archive/train/eval/xmas02/latency-200-refs.json
        --weights v1=/datasets/archive/train/v1png-20261008/weights/last.pt
        --weights xmas02=/datasets/archive/train/xmas02-20261106/weights/last.pt
        --out /data/train/eval/gpu-bench/bench.json
        --sustain-model xmas02 --no-sustain-half --sustain-s 600 --rate 10'
    python3 scripts/guarded_build.py worker-stop:vision

- **Phase A:** v1 and xmas02, each in FP32 and FP16. 10 warm-up predicts, then one predict per
  frame of the 200 TEST frames of xmas02-eval.md's CPU latency run (the same frames as its
  `latency-cpu.json`). Each is timed from the call to the boxes on the host, with ultralytics' split.
  Plus the bare forward pass, 100 times.
- **Phase B:** xmas02 FP32 (the heavier precision: if it passes R3, FP16 does) at 10 predicts a
  second for 600 s. That is the load a GPU box watcher would put on the card. guarded_build's paired
  R3 (60-s windows for a step this short) reports what it costs Frigate.
- **Parity:** the boxes are kept and checked on the host against the CPU ONNX path (UnitDetector,
  per-class NMS) on the same frames: monster boxes matched at IoU >= 0.7, per precision.
- **The CPU side, at the same hour:** eval_latency's interleaved CPU run on the same 200 frames at
  16 threads (host load recorded), so the ratio is like for like.
- **Reported, not decided:** the speed-up, FP16's parity, R3's paired delta, the VRAM peak. Moving
  the live detector to the GPU stays Batt's decision. A live GPU path would also need a frame route
  from the host bot into the worker; that route is NOT measured here.

## 6. The lab PC vs the server, same kit, same pictures (2026-11-07 06:30-06:48 ICT)

Batt's one-off ADR-0019 exception (logged there before it ran): the teaching kit's `--bench`, pinned
at commit `35851e1`, ran ONCE on the lab PC from the agent's shell. Its `v1.onnx` hashed `32b448a1...`
there, the same file as the server's `v1png-last-736x1280.onnx`. Then the same commit ran on the
server at 06:47:55. Both used the same 20 sample pictures and onnxruntime 1.31.1, and found 2.3
boxes a picture.

| threads | lab PC: i5-10500T, 6 cores / 12 logical, 31.7 GB, Windows 11, the RO client open | server: Xeon E5-2695 v4, 64 logical, load ~10 -> 24 |
|---|---|---|
| 1 | 237.5 / 242.7 ms (4.20 fps) | 464.5 / 685.7 ms (2.02 fps) |
| 2 | 147.9 / 159.0 (6.69) | 262.3 / 285.9 (3.78) |
| 4 | 116.8 / 126.7 (8.43) | 179.5 / 226.8 (5.53) |
| 6 | 122.2 / 130.9 (8.15) | - |
| 8 | 119.0 / 124.4 (8.43) | 138.2 / 171.2 (7.02) |
| 12 | **95.5 / 99.2 (10.43)** | 119.2 / 140.3 (8.24) |
| 16 | - | **110.3 / 123.5 (9.01)** |
| auto | 122.4 / 134.2 (8.10) | 241.1 / 440.1 (3.46) |

(p50 / p95 per picture, 30 timed detections after 3 warm-ups.)

- **Batt's observation holds:** the boxes are slow on a PC next to the client too. The PC is about
  twice as fast per thread (newer cores, higher clock), but at each machine's best the gap is ~13 %
  (95.5 vs 110.3 ms). A CPU gives ~100 ms a picture either way, so the remote path is not the cause.
- **On the PC, auto is not the slowest** (122 ms, its 6 physical cores, nothing else busy); on the
  busy server it is (241 ms).
- **The lab PC's C++ runtime is from 2016:** `msvcp140.dll` 14.00.24215.1 in System32, and no
  `vcruntime140_1.dll` / `msvcp140_1.dll`. onnxruntime 1.31.1 failed to import ("DLL load failed").
  - The kit's README says to install the Visual C++ Redistributable. That is a system install
    (admin, UAC: Batt's), so it was not done.
  - Instead the run took Microsoft's DLLs (14.51.36247, signatures Valid: Microsoft Windows Software
    Compatibility Publisher) from the `msvc-runtime` wheel, put beside onnxruntime INSIDE the temporary
    folder, and removed with it.
  - A student PC with an old runtime fails the same way. The README's note names `access
    violation`; this PC printed `DLL load failed ... The specified module could not be found`.
- The server's numbers above ran from the RAM detector env. That env has no OpenCV, so the bench's
  one `cv2.imread` was a stand-in returning the same JPEGs decoded once by Pillow; the timed code is
  the kit's own.

## 7. The GPU measurement: RESULT (2026-11-07 09:08-09:17 ICT; section 5's plan, unchanged)

The vision worker started at 09:06:03, through quiet_start (it had waited since 06:17:51: Frigate's
own bursts restarted the 10-min clock 172 times). Its start's worst capture stall was 2.9 %.
`execdev:vision` ran from 09:08:27.

**Phase A finished; phase B was ABORTED at 09:16:34 by R3-HARD.** Camera cam-1-01-font-s dropped
frames for 32 s (skipped_fps 2.9; five cameras skipping; fleet 90.1 detections/s). Our container had
been PAUSED (R3's OFF window) since 09:15:34, so the GPU held nothing of ours when the drop happened.
The same camera named all four hard aborts of 2026-10-25 and kept dropping after our stop then
(memory: cam-1-01-font-s drops on its own). The stop was VERIFIED at 09:16:37, and the worker stopped
(guarded `worker-stop:vision`) at 09:17:30. Not retried: the stop is absolute; a retry is Batt's call.

| model, precision | GPU: call to boxes, p50 / p95 (n 200, 0 paused) | of which inference p50 | CPU 16 threads, same frames, 06:18 |
|---|---|---|---|
| v1 FP32 | **21.8 / 28.0 ms** | 16.6 ms | 194.2 / 237.7 ms |
| v1 FP16 | 24.1 / 32.0 ms | 19.2 ms | - |
| xmas02 FP32 | **24.0 / 31.0 ms** | 17.5 ms | 212.0 / 338.6 ms |
| xmas02 FP16 | 27.5 / 31.9 ms | 20.7 ms | - |

- **The GPU is ~8-9x faster at p50 and ~8-11x at p95** than 16 CPU threads on this server: ~22-24 ms a
  detection instead of ~194-212 ms. The CPU was measured at load 14-23, the GPU beside Frigate's
  three detectors.
- **FP16 is no faster** for a model this small: the call is dominated by the fixed costs. The
  preprocess (~3 ms) and the postprocess (1-2.5 ms) are inside the wall time.
- **Not measured (lost to the abort; the file is written only at the end):**
  - the bare forward pass;
  - the parity of the GPU boxes with the CPU's (`scripts/gpu_parity.py` waits for a full run);
  - phase B's cost to Frigate. One R3 pair only, not kept (load 8.8 vs 6.1 det/s): ON 26.96 vs OFF
    23.03 ms.
- **Not in these numbers:** a live GPU path also needs the frame route from the host bot into the
  worker (section 5). Even so, it would cut p7's grab-to-hover time (rogue-xmas02.md) by ~0.2-0.3 s
  a detection.
- The printed phase A lines and the step's log: `scratch-archive/2026-11-07/gpu-bench/`.

## 8. The rerun for what section 7 lost, and "how heavy" (written 2026-11-07 09:3x ICT, BEFORE it runs)

Batt (~09:2x), answering section 7's decisions:
1. "Move it [the live detector to the GPU]. Before moving, report how heavy the GPU use is."
2. "Measure it [the parity and the Frigate cost] now."
3. Camera drops are acceptable today: the one-day R3 relaxation (docs/operations/r3-paired.md,
   1346168).

- **The worker:** the same quiet_start start as section 5 (unchanged: its cold start is the IO
  burst).
- **The bench:** section 5's command, unchanged, with one exception: the step's IO guard is
  `--threshold 30 --sustain 30` with no spike. That is the 2026-10-28 rule for small-local-IO jobs:
  the bench reads its 200 frames from the NAS and writes one JSON. With `--spike 25`, one of
  Frigate's own bursts (25-41 % this morning) would end it.
- **"How heavy", read-only beside the step:**
  - `nvidia-smi` every 0.5 s: GPU-wide utilization, memory used, power;
  - `nvidia-smi pmon` every 1 s: our process's SM % and its memory.
- **Reported:**
  - our process's peak and typical memory (with torch's own peak);
  - our SM % and the GPU-wide utilization, phase B ON windows vs OFF (paused) windows: the cost of
    a 10 Hz detector;
  - the power delta;
  - R3's paired ON-OFF delta of Frigate's detector (the trip is +5 ms);
  - the parity (`scripts/gpu_parity.py`): monster boxes matched at IoU >= 0.7, per precision;
  - the forward pass;
  - any relaxed drops.
- Nothing is moved by this measurement. The move (a frame route from the host bot into the worker,
  then a pre-registered pilot) is designed after this report.

### 8 RESULT (2026-11-07 10:00-10:18 ICT; section 8's plan, unchanged)

- **The run:**
  - The worker started at 10:00:27, with Frigate's IO left out of the gate (Batt's one-day exception,
    bf29335).
  - The bench: 10:02:36-10:14:58, rc 0, worst capture stall 5.0 %, no camera drop (no relaxed drop
    needed). The worker stopped (verified) at 10:15:02.
  - Then the CPU parity on the host.

| model, precision | GPU call to boxes p50 / p95 | bare forward p50 / p95 | torch peak | parity: GPU monster boxes = CPU's (IoU >= 0.7) |
|---|---|---|---|---|
| v1 FP32 | 21.6 / 31.3 ms | 18.3 / 25.7 ms | 96 MiB | 49 / 49 = 1.000 (and 49 / 49 of the GPU's) |
| v1 FP16 | 26.1 / 35.0 | 22.4 / 26.5 | 97 MiB | 48 / 49 = 0.980 (48 / 50) |
| xmas02 FP32 | 29.2 / 43.7 | 19.6 / 26.3 | 106 MiB | 340 / 340 = 1.000 (340 / 340) |
| xmas02 FP16 | 26.3 / 32.7 | 22.4 / 28.1 | 102 MiB | 340 / 340 = 1.000 |

- **Parity:** in FP32 the GPU gives the CPU's boxes, one for one, for both models. FP16 lost one v1
  box (and added one).
- **Speed:** phase A again 22-29 ms a call (section 7: 22-24 ms; Frigate busier now, people at
  home). FP16 is again not faster. The bare forward pass is 18-20 ms, so the call adds only
  ~3-10 ms of pre / post work.
- **Sustained at 10 Hz (xmas02 FP32, phase B: 3,354 calls in the 600 s, 3 across a pause):** p50
  45.2 / p95 59.0 ms a call, slower than one at a time but still ~4-5x the CPU's.

**How heavy (read-only nvidia-smi beside the step; ON = ours running, OFF = paused by R3):**
| | ON | OFF |
|---|---|---|
| GPU-wide utilization (0.5 s samples), mean / p50 / p95 | 25.0 / 23 / 52 % | 21.2 / 15 / 73 % |
| power, mean / p95 | 42.7 / 52.5 W | 40.4 / 62.1 W |
| GPU memory used (whole card) | 3,894 MiB of 16,311 | 3,894 (ours stays loaded while paused); 3,529 before the step |
| OUR process (pmon, 1 s): memory | 360 MiB | 360 MiB |
| OUR process: SM % when sampled busy, mean / p50 / p95 | 17.8 / 19 / 33 % (151 of 262 samples) | - |

- **Our process holds 360 MiB of GPU memory**: the card's 3,529 -> 3,894 MiB, about 2 % of it, far
  inside R1's 9 GiB.
- **It uses ~17-19 % of the GPU's compute when busy, ~10 % averaged over time, at 10 detections a
  second.**
- **The GPU-wide ON-OFF difference** (+3.8 points mean utilization, +2.3 W) UNDERSTATES our share:
  Frigate's own load was lower in our ON windows (17.8-18.6 det/s) than in the OFF ones (26.4-26.5).
- **R3, Frigate's detector:** 2 pairs, ON 27.59 vs OFF 29.63 ms (-2.04) and ON 30.70 vs OFF 26.61
  ms (+4.10). Neither was kept (load not matched within +-20 %), so this is NO R3 verdict: a
  short step cannot reach R3's 4 kept pairs on a day this variable. Both deltas are under the +5 ms
  trip.
- Files: `data/train/eval/gpu-bench/bench.json` (moved to the NAS), the samplers, the parity and
  the logs: `scratch-archive/2026-11-07/gpu-bench2/`.

