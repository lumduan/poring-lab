---
doc_type: design
hypothesis: null
status: ACCUMULATING
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: Run C0a/C0b (A/A) in the S2 session, then E1..E5 in order; append each result below its pre-registration.
---

# S2 key→paint tail: pre-registered experiments (2026-10-03)

**Why.** V3b (the S2 client on the frame bus) beats RDP on fps, cores and packet→frame. Its
key→paint tail is worse, though: p50/p95 121/277 ms vs RDP v2 101/114
([V3b run](2026-10-03-console-26fa31049e16-cleanroom-v3b-framebus.md)).

**The distribution is bimodal.** p75 is 132.6 ms but p90 is 257.4 ms: roughly 1 trial in 8 pays
about +130 ms. That shape points to something periodic or bursty, not to a uniformly slower path.

**Rules.**
- Each run's hypothesis, expected effect and keep/revert rule are written HERE before the run.
  Its result is appended under it afterwards and never edited.
- One variable per run.
- Builds and benchmarks never overlap.

## Method (fixed for every run)

- **Procedure:** `scripts/bench.py exp --label <run>`, outdoor only (`prt_fild08 170 375`).
  - 30 s of camera rotation: delivery fps and lab cores.
  - 30 click-walks: packet→frame.
  - 60 Escape presses at 1.5 s spacing: key→paint, p50 … p99 and n.
  - Whole-run cores.
  - Output: `docs/benchmarks/experiments/<run_id>.json`.
- **Variant:** S2 (`PAINT=bus INPUT=socket`). Input is mux → s2-input socket → Sunshine; frames are
  read from the bus. Each run's knobs are written into the variant file by
  `cleanroom.py variant S2 --knob K=V` and recorded in the result's `config.variant`.
- **Clocks.** key→paint is measured from the moment the bench sends the key to the decode-complete
  time (`t_publish_ns`) of the first bus frame where ≥10 % of the Game-option region changed.
  - The S2 client logs every frame to `frames.csv`: `receiveTimeMs`, `enqueueTimeMs`, Sunshine's
    `frameHostProcessingLatency`, dequeue ns, publish ns, decode µs.
  - moonlight-common-c's ms clock is `PltGetMillis()` = `CLOCK_MONOTONIC`. Checked in
    `src/Platform.c` at the pinned commit 8599b60 (blob 4f99885). It is the same clock as the
    lab's `t_mono_ns`, so each trial splits at its painting frame into:

    | part | span |
    |---|---|
    | `to_receive` | key sent → the frame's first packet. Mux, socket, Sunshine input, Windows, the game's next frame, capture, encode, network. ms resolution. |
    | `host` | Sunshine's own capture → send. Part of `to_receive`. |
    | `receive` | first → last packet |
    | `queue` | enqueued → taken by the decode thread |
    | `decode` | decode + BGRA conversion + publish |

    This is experiment **3d**, measurement parity: the split no longer depends on how the frame
    was grabbed.
- **Caveat that stays:** the RDP numbers are X grabs, while the S2 numbers are decode-complete
  times. RDP's key→paint therefore includes its grab-loop phase; S2's does not.
- **Noise band.** C0a and C0b are the same configuration run twice. Their |Δp50| and |Δp95| form
  the band.
  - An effect counts only when it exceeds **2 × the band** in the predicted direction.
  - With n = 60, p95 is the 57th of 60 values and p99 is nearly the maximum. The `split` is the
    evidence for *where* time goes, the quantiles for *how much*.
- **Keep / revert.** Keep a change when key→paint p95 improves beyond the noise threshold, p50 does
  not worsen beyond it, and fps and cores stay within budget (gamestream `cpus: 4`). Otherwise
  revert it. Kept changes accumulate into the next run's control.
- **Stop.** Stop when the remaining candidates' effects fall inside the A/A band, or when the tail
  is gone (p95 within 2 × band of p50 + 33 ms, one game frame).

## Runs, in order

### C0a, C0b: the control, twice (A/A)
- **Config:** S2, 30 fps, `EVIDENCE=inline`, `DECODE_THREADS=2`. These are the V3b defaults, with
  socket input.
- **Expected:** key→paint about V3b's (121/277). If socket input (no X window, no XTest) shifts it,
  that is a finding on its own, compared against V3b.

### E1 (3b-1): evidence off the decode thread
- **Change:** `EVIDENCE=thread`. The 2 s evidence PNG (1440×900) is encoded on its own thread,
  latest-only, instead of on the decode thread.
- **Hypothesis:** the bimodal tail is the decode thread blocked by the PNG encode. A key whose
  frame arrives during that encode waits for it.
  - Prediction: `queue` p95 falls from ~100+ ms to a few ms.
  - Prediction: key→paint p95/p99 fall clearly (towards p50 + 33 ms) and p50 barely changes.
- **Keep** if p95 improves beyond the noise threshold.

### E2 (3b-2): decoder threads
- **Change:** `DECODE_THREADS=1`, then `DECODE_THREADS=4`: two runs, slice threading.
- **Hypothesis:** threads change only `decode` ms, by a few ms either way. Bus publishing stays
  under 2 ms.
- **Expected:** p50 ± a few ms; p95 unchanged. Keep the fastest only if its gain exceeds the
  noise threshold; otherwise stay at 2.

### E3 (3a): 60 fps stream
- **Change:** `FPS=60`. The launch asks Sunshine for 1440×900×60, and `dd_refresh_rate_option=auto`
  sets the VDD to 60 Hz. The game stays capped at 30.
- **Hypothesis:** half the capture/encode slot and half the pacing wait.
- **Expected:** p50 down 8–15 ms; p95 down if part of the tail is slot pacing; decode cores up
  (about ×1.5–2).
- **Keep** if p95 or p50 improves beyond the noise threshold, cores ≤ 2 for gamestream and fps is
  not lower.

### E4, E5 (3c): Sunshine, one change per run, restored after each
Batt makes these changes in his elevated console. For each run:
1. back up `sunshine.conf`;
2. change ONE key;
3. restart Sunshine;
4. run;
5. restore and read back.

A Sunshine restart ends the stream: `hold` → push Batt → re-stream.

- **E4:** `capture = wgc` instead of ddx. Hypothesis: DDX's frame-pacing buffer is part of `host`
  / `to_receive`. Expected: `host` changes; key→paint ±.
- **E5:** `encoder = software` (`sw_tune = zerolatency` if the build supports it) instead of
  QuickSync. Hypothesis: QSV's lookahead/async depth adds a frame. Expected: `host` down 5–15 ms at
  a higher Windows CPU cost; key→paint p50 down by about the same.
- **Keep** only with Batt's OK. Windows CPU matters on the Dell.

## Results

(appended after each run; never edited)

### 2026-10-03 20:32–21:18, the S2 session (variant S2: bus + input socket)
Key→paint is p50 / p95 / p99 in ms. A p99 of `>1500` means at least one trial had no painting
frame within 1.5 s. The split columns are p50 / p95 ms at each trial's painting frame. fps is the
median (p10) during rotation. "gs cores" is gamestream in motion.

| run | run_id | key→paint | matched | to_receive | host | queue | decode | packet→frame | fps | gs cores |
|---|---|---|---|---|---|---|---|---|---|---|
| C0a | `2026-10-03T2032-45d162f8b03f-C0a` | 123.2 / 293.5 / >1500 | 59/60 | 105.9 / 142.1 | 5.7 | 0.7 / 157.4 | 8.9 / 12.8 | 120.0 / >1500 (22/30) | 30 (26) | 0.93 |
| C0b | `2026-10-03T2037-45d162f8b03f-C0b` | 132.6 / 367.7 / >1500 | 57/60 | 110.5 / 150.9 | 5.7 | 0.9 / 168.9 | 9.3 / 13.4 | 115.6 / 256.7 (29/30) | 28 (23) | 0.93 |
| E1 | `2026-10-03T2044-2a41c1450007-E1-evidence-thread` | 123.1 / 169.6 / >1500 | 59/60 | 110.3 / 154.6 | 5.7 | 0.7 / 1.1 | 9.5 / 12.7 | 102.2 / >1500 (28/30) | 30 (28) | 1.0 |
| E2 dt=1 | `2026-10-03T2050-6b4d63df5173-E2-dt1` | 135.8 / 160.3 / >1500 | 59/60 | 117.9 / 136.7 | 6.2 | 0.7 / 1.1 | 11.3 / 19.7 | 116.9 / 208.5 (30/30) | 30 (28) | 0.94 |
| E2 dt=4 | `2026-10-03T2056-2348dcbbbf52-E2-dt4` | 129.2 / >1500 / >1500 | 54/60 | 115.4 / 142.5 | 5.7 | 0.5 / 1.2 | 6.4 / 9.3 | 97.2 / >1500 (27/30) | 30 (28) | 0.97 |
| E3 fps=60 | `2026-10-03T2112-cceeee742be8-E3-fps60` | 110.4 / 127.1 / 133.8 | 60/60 | 96.8 / 112.0 | 7.4 | 0.8 / 1.1 | 9.1 / 11.4 | 98.0 / 109.9 (30/30) | 30 (5) | 0.9 |

- **A/A band** (C0a vs C0b): |Δp50| 9.4 ms, |Δp95| 74.2 ms. The 2× thresholds are 18.8 / 148 ms
  (n = 60 per run, so p95 is noisy, as pre-registered).
- **E1 KEPT.** The bimodal tail WAS the decode thread blocked by the evidence PNG encode:
  - queue p95 fell from 157–169 ms to 1.1 ms;
  - key→paint p95 fell from 293–368 ms (mean ≈ 330) to 169.6 ms (Δ ≈ −160, beyond 148);
  - p50 is unchanged (123).

  Pre-registered prediction: CONFIRMED.
- **E2 (decoder threads):** decode p50/p95 is 11.3/19.7 ms with 1 thread, 9.5/12.7 with 2 (E1),
  and 6.4/9.3 with 4. Key→paint moves within the band, so **threads stay at 2**, as the rule says.
  Bus publishing: included in `decode` (dequeue → publish), well under 2 ms beyond the decode itself.
- **E3 (60 fps): NOT decided by the rule yet.**
  - Key→paint 110.4 / 127.1 / 133.8 with 60/60 matched, against E1's 123.1 / 169.6.
  - Δp50 −12.7 and Δp95 −42.5 are both under the 2× thresholds.
  - The split shows the mechanism: `to_receive` 96.8/112.0 against E1's 110.3/154.6, beyond
    to_receive's own A/A band (±4.6 / ±8.8).
  - Gamestream cores are unchanged (0.90).
  - **fps p10 fell to 5**, but see "network drops" below: this is not 60 fps-specific.
- **E4 (capture = wgc): DROPPED before running.** Sunshine's docs say wgc "is not compatible with
  the Sunshine service", and the Dell runs Sunshine as `SunshineService`. Testing it would mean
  running Sunshine as a user app: a different deployment, Batt's decision, not a one-key change.
- **Finding, network drops:** the S2 client logs "Network dropped 1 frame … Waiting for IDR frame"
  25–77 times per stream at 30 fps too, roughly once per 10 s. The host has no reference-frame
  invalidation, so each drop freezes the picture until a full IDR.
  - The container's UDP sockets dropped nothing: `RcvbufErrors` 0, per-socket drops 0.
  - `enp6s18` (virtio) RX drops +1 in a 60 s window with 0 client drops in that window.
  - So the loss is upstream of the VM, or Sunshine's send pacing. Open, and the likely source of
    the stray 1–6 unmatched key presses per run (the bench records them per run from E3 on).

### E3-confirm (pre-registered 2026-10-03 21:25, BEFORE the runs)
- **Why:** E3's effect sits between the quantile rule (not met) and the split (met).
- **Runs:** one more E1 (`EVIDENCE=thread`, 30 fps) and one more E3 (`EVIDENCE=thread`, 60 fps),
  in that order. That gives the order A, B, A, B together with the first pair.
- **Decision on the POOLED n = 120 per arm:** keep 60 fps if pooled key→paint p95 improves by more
  than the 2 × A/A threshold scaled to n = 120 (148 / √2 ≈ 105 ms) OR pooled p50 improves by more
  than 18.8 / √2 ≈ 13 ms, with fps (median) and cores not worse. Otherwise stay at 30.
