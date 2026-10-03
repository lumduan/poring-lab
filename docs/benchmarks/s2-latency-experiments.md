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
