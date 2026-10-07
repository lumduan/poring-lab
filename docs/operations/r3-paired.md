---
doc_type: design
hypothesis: "Our GPU job's effect on Frigate's detector is measured like with like: paired ON/OFF windows under similar Frigate load, judged by the median paired delta."
status: PRE-REGISTERED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../../CLAUDE.md, ../demonstrations.md]
next_action: "Build PairedR3 (frigate_r3.py + guarded_build docker pause/unpause), test it, then re-run the step-sleep ladder 0/100/200/400 ms with it. No GPU training until it is in place (Batt, 2026-10-07)."
---

# R3, measured like with like: the paired ON/OFF design (pre-registered 2026-10-07)

## Why the first R3 measurement was confounded
Batt, 2026-10-07 ~12:35: the cameras showed a lot of motion.
- The first R3 rule compared a 60 s window of our training against a baseline taken minutes
  EARLIER. Two things changed at once: our training, and the cameras' activity.
- Frigate's detector latency depends on its own load (more motion → more detections →
  +0.16 ms per detection/s, measured without load today). Within the hour the load moved 50 %
  (baseline medians from 23.7 to 35.8 detections/s).

**What the first ladder's data say** (Frigate's own collector, 10 s samples): in all four training
windows, Frigate's detection load was LOWER than in the baseline before it, and the latency was
higher anyway:

| level | inference p50 | its baseline | detections/s (vs baseline) |
|---|---|---|---|
| sleep 0 ms | 33.4 | 29.8 | 20.8 vs 27.3 |
| sleep 100 ms | 33.1 | 29.8 | 22.3 vs 27.3 |
| sleep 200 ms | 31.0 | 29.0 | 19.8 vs 23.7 |
| sleep 400 ms | 33.0 | 30.5 | 30.0 vs 35.8 |

So the effect looks real. But a fair measurement must still compare like with like ("baseline
under the same load", the infra rule).

## The design
**Mechanism:**
- The GPU step's container is named (guarded_build).
- An OFF window = `docker pause` of that container: its processes are frozen, nothing of ours
  runs on the GPU (its memory stays allocated: R1 is unchanged).
- An ON window = `docker unpause`.
- It works for training and evaluation alike, with no change to their code.
- A paused container cannot handle SIGINT, so every abort UNPAUSES it first. Then comes the
  verified stop (container gone, GPU free, else escalation).

**Windows:**
- Training steps (timeout > 20 min), MEASUREMENT phase: 180 s ON, 180 s OFF, alternating, starting
  ON. The first 30 s after each switch are discarded (settle; Frigate's stats refresh about every
  15 s).
- Short steps (eval, predict; timeout ≤ 20 min): 60 s windows with a 20 s settle, for the whole
  step.
- A window counts only with ≥ 6 distinct Frigate updates after the settle (≥ 3 for short steps).
- **The window values:**
  - LATENCY = the median of the mean-of-detectors `inference_speed` over its updates;
  - LOAD = the median fleet `detection_fps`.

**Pairs:**
- Each ON window is paired with the OFF windows adjacent to it: the one before (if any) and the
  one after. OFF = the mean of their latencies, and the mean of their loads.
- A pair is KEPT only if |LOAD_on − LOAD_off| ≤ 20 % of LOAD_off (similar Frigate load). A
  dropped pair is recorded with its loads.
- Delta = LATENCY_on − LATENCY_off.

**Verdict (MEASUREMENT phase):**
- **TRIP:** after ≥ 4 kept pairs, the median delta > 5.0 ms. The step is aborted (`ABORT … R3
  paired latency`, verified stop) and counted as an R3 latency trip, so `train-day.sh` moves up
  the step-sleep ladder.
- **PASS:** after ≥ 4 kept pairs, the median delta ≤ 5.0 ms. A training step goes to MONITORING;
  a short step simply runs on (its windows continue to its end).
- **INCONCLUSIVE:** fewer than 4 kept pairs after 10 cycles (60 min). The step is aborted, fail
  closed, cause "Frigate load too variable to measure".

**MONITORING (training, after PASS):**
- 27 min ON, then 3 min OFF, repeated.
- Each OFF forms a pair with the last 180 s of the ON before it (30 s settle), with the same
  kept-pair rule.
- TRIP if the median delta of the last 4 kept pairs > 5.0 ms.

**Unchanged, and ABSOLUTE:**
- **Frame drops:** any camera with `skipped_fps` > 0 on every update for ≥ 30 s (≥ 2 updates),
  or `camera_fps` below half its median over the OFF windows so far, is an R3-HARD stop (no
  resume), at any time, ON or OFF.
  - No baseline floor any more (Batt: "regardless").
  - Before the first OFF window, the camera_fps reference is a 60 s pre-start read.
- **Frigate unreachable** for 60 s → abort (fail closed).
- **Ollama loads a model** → abort (R2: yield).

**What is retired:**
- the 60 s rolling-median rule;
- the 3 h baseline file requirement;
- the re-baseline pauses.

`frigate_r3.py baseline` stays as a reporting tool.

## The ladder re-run (pre-registered)
- Step sleep 0 → 100 → 200 → 400 ms, each judged by its own MEASUREMENT phase as above.
- The first PASS level continues the run in MONITORING. A TRIP moves one level up. A TRIP at
  400 ms stops the run and parks the setting for Batt.
- The matched settings (batch 2, workers 1, imgsz 1280, seed, 30 epochs, cache v0jpg-20261007)
  are unchanged.
- Reported per level: the kept and dropped pairs (each with its ON/OFF latency and load), the
  median delta, and the verdict.
