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

**When the schedule starts:**
- When the step's own process first holds ≥ 500 MiB on the GPU (the model is loaded), or 120 s
  after its container starts, whichever comes first.
- Before that, its start-up (CUDA initialisation, dataset indexing) is little GPU load. Counting
  it as ON would bias the first pair toward passing.
- The absolute rules below apply from the first second.

> ➡️ **AMENDED 2026-10-07 ~12:50, before any run.**

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

## The ADAPTIVE DUTY CYCLE (Batt, 2026-10-07 ~16:25; pre-registered ~16:55, BEFORE its first run)
**Batt:** keep training RUNNING and adapt to the cameras: slow down, don't stop. Never a full
pause because of load alone. The frame-drop rule is the infra side's and stays. The IO guard and
R1 / R2 are unchanged.

**The levels:** the step sleep after every training batch is one of **100 / 200 / 400 / 800 /
2000 ms** (L0 … L4; L4 = the floor). It changes LIVE.
- `guarded_build`'s `DutyController` writes it to `state/train-duty/duty.json`, read-only in the
  container at `/lab-duty`. It writes on every change and as a 30 s heartbeat.
- The container re-reads it after every batch.
- A missing, stale (> 120 s) or garbled file means L4: fail slow, never fast.
- Vision cannot write the file. That is the one read-only mount added to the dev overlay
  (`test_guards.py`).

**The thresholds, from 2026-10-07's 1,235 distinct Frigate updates (11:04–16:42):**
- **The data:** fleet detections/s p50 29, p90 43, p95 50, p99 82; 92 % of updates < 45.
  - Skips began at 70–77/s WITH our job (detectors ~39 ms; a ceiling ~77/s) and at ~90/s without
    it (~33 ms; ~90/s).
  - 11 skip episodes; 6 of them had no job of ours running.
  - Half the bursts had a precursor above ~55/s 10–15 s before the skips; the others jumped in
    one update (e.g. 26 → 70).
- **Up, at once, any number of levels, on every distinct update:**

  | fleet load (detections/s) | level |
  |---|---|
  | < 40 | L0 (100 ms) |
  | 40–50 | L1 (200 ms) |
  | 50–55 | L2 (400 ms) |
  | 55–65 | L3 (800 ms) |
  | ≥ 65, or ANY camera skipping | L4 (2 s) |

- **Down, ONE level at a time:** only after 3 consecutive updates asking for less (~30–45 s), and
  ≥ 60 s since the last change (≥ 180 s after a frame-drop abort: the walk back up is slower).
- **No fresh Frigate update for 30 s → L4.** (After 60 s the R3 guard aborts: fail closed,
  unchanged.)

**The infra rules around it:**
- **A camera dropping frames for 30 s** → an IMMEDIATE, verified abort, logged with the fleet
  load. Then a wait for 15 quiet minutes (the gate re-arms until it passes; never a stop). Then a
  resume at L4, walking back up slowly.
  ➡️ **TEMPORARY AMENDMENT (Batt, 2026-10-08 ~11:25), see "The temporary load hold" below:** the
  resume ALSO waits until Frigate's rolling load is below ~60 detections/s.
- **The 3rd frame-drop abort within a rolling 2 h** → a CAP at ≥ L3 (800 ms) for the next 60 min,
  plus a `NOTIFY:` line (the session pushes it to Batt). It keeps running. *(This replaces the
  15:40 rule "3 aborts in 2 h → stop and wait".)*
- **A paired R3 latency trip** → the FLOOR rises one level (`DUTY_MIN`), and training resumes in
  30 s. At L4 it keeps running there.
- ~~**"R3 inconclusive"** → the FLOOR rises one level, and training resumes in 30 s.~~ ➡️
  **AMENDMENT (Batt, 2026-10-08 ~19:00): an INCONCLUSIVE measurement never stops the container.**
  "Inconclusive" is OUR paired-measurement rule, not the infra rule, and "can't measure" is not
  evidence of harm. It cost 74 % of epoch 29 at 18:33.
  - The duty cycle drops to the SLOWEST level (L4, 2000 ms) and HOLDS there.
  - The measurement starts a NEW series from the current window (`PairedR3.remeasure`); training
    goes on.
  - When the re-measurement PASSES, the hold is released, and the duty cycle walks back up one level
    at a time as always.
  - If the re-measurement TRIPS (a paired delta over +5 ms), the latency rule above applies.
  - If it is inconclusive again, it holds and re-measures again; still never a stop.
  - **Only the infra rule (a camera dropping frames for 30 s) stops at once**, as before. The IO
    guard and R2 are unchanged.
  - Logged as `R3: inconclusive measurement ... KEEP TRAINING at the slowest level`. It is never an
    `ABORT` line, so train-day.sh never treats it as a trip. `DUTY summary` shows `held`, and
    `R3 summary` shows `remeasures`.
  - Code: `guarded_build.run_process`, `frigate_r3.DutyController.hold`. Tests:
    `test_an_inconclusive_r3_keeps_training_at_the_slowest_level`,
    `test_without_a_duty_cycle_an_inconclusive_r3_still_aborts` (non-training steps unchanged),
    `test_frame_drops_still_stop_at_once_even_with_a_duty_cycle`.
  - **In effect from the next training start.** The attempt running at the change (since 18:34)
    loaded the earlier code, and a restart would itself cost its partial epoch.
- **The IO guard and R2:** unchanged (15-min pauses, at most 3).
- **The paired measurement's own 3-min OFF windows remain.** They are a measurement, not a load
  response.

**Reported:**
- **throughput per level:** the container's `duty_stats` lines, batches and seconds per level →
  batches/s;
- **time per level:** guarded_build's `DUTY summary`;
- every level change with its load;
- every abort with its load.

**Tests:** `test_frigate_r3.py` (the target bands, up/down, the floor, the cap, a silent Frigate,
the accounting, the atomic file), `test_train_r3.py` (the container's reader: an untrusted file is
the slowest level; the per-level accounting), `test_train_day.py` (the real script against stubs:
resume at L4 after a drop, the cap + NOTIFY without a stop, a re-armed gate, a latency trip raising
the floor).

## The temporary load hold on the resume (Batt, 2026-10-08 ~11:25) — TEMPORARY, with an exit
**Why:** on 2026-10-08 four camera-drop aborts in two hours came at Frigate's late-morning peak.
- 09:32, 10:03, 10:37 and 11:15, at 74–87 detections/s. Every one was at the SLOWEST duty level,
  and the cameras also skipped while nothing of ours ran.
- Each resume ran a few minutes at the slow levels and was then aborted. Without mid-epoch
  checkpoints, each abort also threw away its partial epoch: epoch 29 was trained and discarded
  four times.

**The rule:** after a frame-drop abort, the resume gate needs BOTH conditions:
- 15 continuous quiet minutes (unchanged);
- Frigate's rolling load below ~60 detections/s: the mean `detection_fps` over the last 10 min of
  observed distinct updates.

While the quiet minutes are met but the load is not, the gate logs a "held" line at most every 5
min. The cap and the NOTIFY after 3 aborts in 2 h are unchanged.

**Code:** `frigate_r3.py`:
- `TEMP_HOLD_MAX_LOAD = 60.0`, `TEMP_HOLD_WINDOW_S = 600`;
- `QuietGate(max_load=…)`;
- `quiet --max-load` (default the constant; 0 = off).
- Tests in `test_frigate_r3.py`.
- It went live at 11:27:57. The running gate was restarted by hand, and a NOTE line in the run's
  `train.log` says so.

**EXIT (Batt):** once mid-epoch checkpoints are merged AND their pre-registered resume proof passes
(docs/operations/mid-epoch-checkpoints.md), set `TEMP_HOLD_MAX_LOAD = None`. That reverts to the
continuous rule: resume after the quiet gate, capped. Record the date here when it is done.

## Frame-drop aborts: an automatic resume (Batt, 2026-10-07 ~15:40)
> ➡️ **AMENDED ~16:25:** "the 3rd abort within 2 h stops" is replaced by the cap + notify above.
> The resume now starts at L4.
- **The abort stays IMMEDIATE and unconditional** (the infra rule). Its message now carries the
  fleet load: detections/s, the detectors' ms, and which cameras are skipping (`fleet_load`).
- **`train-day.sh` resumes on its own** only after 15 continuous minutes in which no camera
  skipped a frame (`frigate_r3.py quiet`: observed distinct updates only; a Frigate silence over
  60 s restarts the clock).
  - It resumes at the SAME ladder level. The resumed step's paired R3 measures again, so a latency
    trip still moves up the ladder.
- **At most 3 frame-drop aborts per rolling 2 hours.** The 3rd STOPS and waits for Batt, and so
  does a gate that finds no quiet 15 minutes within 2 h.
  - The aborts are kept in `<run dir>/drop-aborts.log`.
- **Tests:** `test_frigate_r3.py` (the gate and the fleet-load line) and `test_train_day.py`
  (the real script against stub guard and gate commands).

## Results: the ladder re-run, 2026-10-07 (v0-JPEG matched run, `train-day.sh`)
Each pair: delta = ON − OFF latency (ms); kept only if the loads agree within ±20 %.

| level | step sleep | attempt | pairs (delta ms, kept ✓ / dropped ✗) | median of the kept | verdict |
|---|---|---|---|---|---|
| 0 | 0 ms | 0 (12:40–13:16) | +6.47✗ +6.37✓ +5.51✓ +6.41✓ +7.94✗ +7.82✓ | **+6.39** (4) | **TRIP** → level 1 (stop verified in 5 s) |
| 1 | 100 ms | 1 (13:17–14:24) | +6.28✗ +4.95✓ +2.97✓ +5.19✗ +9.12✗ +3.59✓ +1.64✗ +6.52✗ +3.49✗ +4.21✓ | +3.90 (4; the sampler's reconstruction) | none issued: the IO guard aborted at 14:24:11 (quant-postgres stall 29.3 %) before the guard's own 4th kept pair; stop verified in 5 s |
| 1 | 100 ms | 2 (14:39–15:24, `--resume`) | +3.75✗ +3.50✗ +4.60✓ +4.43✗ +3.42✓ +2.69✓ +6.00✗ | +3.42 (3) | pending: **R3-HARD at 15:24:20** (below), no resume |
| 2, 3 | 200, 400 ms | – | – | – | not reached |

- **What the ladder says:**
  - At 0 ms our training slows Frigate's detector by ~+6.4 ms at matched load (a TRIP).
  - At 100 ms it sits at ~+3.4 to +3.9 ms: under 5, but never formally passed. The guard's
    4th kept pair was cut off twice.
  - Load-matching drops about half the pairs. Frigate's load moved ±20 % between 3-min windows
    most of the afternoon.
- **The R3-HARD stop (15:24:20), attributed** (Frigate's collector, `stats-20261007.jsonl`):
  - At 15:23:53 EVERY camera, indoors and out, jumped to the same ~6.2 detections/s at once.
  - All three detectors saturated: duty cycle 1.0, the fleet capped at ~77 detections/s (=
    3 detectors at 39 ms). `cam-1-01-font-s` skipped frames for 32 s.
  - Frigate did not restart (uptime continuous), no camera process restarted, and the input fps
    did not change.
  - The drops CONTINUED ~25 s after our container was gone (skips 2.1 and 0.9 at 15:24:34 /
    15:24:54).
  - **Reading:** the trigger was fleet-wide: identical rates on a dozen cameras indoors and out
    cannot be one person moving. It looks like a scene-wide change or a simultaneous stream
    glitch; the recordings around 15:23:50 ICT would show which.
  - Our ON window (+3–4 ms per detection) lowered the ceiling, so it likely made the drops start
    sooner, but the burst alone kept them going.
  - It was NOT the operator's console use, which happened at 15:14–15:15 and takes only the
    game-input lease.
  - The absolute rule stopped the run as designed. The training is parked for Batt.

### The resume rule's first afternoon (2026-10-07): STOPPED for Batt at the 3rd frame-drop abort
| abort | ICT / UTC | camera that tripped | fleet load at the abort | what followed |
|---|---|---|---|---|
| 1 | 15:24:20 / 08:24:20 | cam-1-01-font-s | 77.4 det/s, detectors 39.1 ms | the quiet gate: drops again 15:30–15:37 with NO job of ours; quiet 15:37→15:52; resumed 15:52:33 |
| 2 | 16:01:39 / 09:01:39 | cam-1-06-back-n | 77.0 det/s, 39.2 ms, 4 cameras skipping | quiet 16:01→16:16; resumed 16:16:46 |
| 3 | 16:18:34 / 09:18:34 | cam-1-02-font-n | 77.6 det/s, 38.5 ms, 7 cameras skipping | **STOPPED: 3 within 2 h, waiting for Batt** (stop verified in 2 s) |

- **All three aborts sat at the same ceiling.** With our job ON, the 3 ONNX detectors run at
  ~38.5–39 ms, which caps Frigate at ~77 detections/s (3 / 0.039 s). Without us they run at
  ~33 ms, ~90/s. This afternoon's camera activity kept reaching 80–90/s.
- So at level 1 (100 ms) the job fits Frigate's latency budget (~+3–4 ms), but not its CAPACITY
  during busy periods.
- **Options for Batt:**
  - level 2 / 3 (200 / 400 ms) or training at night: zero risk, slower;
  - more detector capacity: needs his judgement.
- **Progress:** the run reached epoch 2 / 30 (3 %); `last.pt` holds epoch 1. Resume by hand:

      RESUME=1 SLEEP_LEVEL=1 scripts/runbooks/train-day.sh v0jpg-20261007 v0jpg-20261007 30 <dir> 2 1

  ➡️ SUPERSEDED the same day by the ADAPTIVE DUTY CYCLE below: `SLEEP_LEVEL` is gone; a hand
  resume is `RESUME=1 DUTY_START=4 scripts/runbooks/train-day.sh …`.
