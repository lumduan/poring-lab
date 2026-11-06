---
doc_type: benchmark
hypothesis: "The bot's slow boxes (2-4 frames a second) come from the model's CPU inference itself, not from the remote display path: Batt's local-PC run of the teaching kit showed 150-435 ms a frame too."
status: "MEASURED 2026-11-06 21:47-21:56 ICT on the lab server (Xeon E5-2695 v4, 64 logical CPUs) while the xmas02 training ran beside it (load average 10 -> 38). The Windows side waits for Batt's --bench output."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../../teaching/simple-bot/simple_bot.py, ../../scripts/unit_detector.py, ../../scripts/detector_worker.py, gef10-eval.md, xmas02-eval.md]
next_action: "Batt runs `uv run simple_bot.py --bench --model v1.onnx` on a Windows PC and sends the BENCH_JSON line; Batt decides whether the live bot's detector may move to the GPU (the biggest lever, a measurement first), and whether the live bot goes to 16 threads."
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
