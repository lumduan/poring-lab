---
doc_type: decision
hypothesis: null
status: GO
role: null
verdict_date: 2026-10-03
verdict_ticket: null
supersedes: null
related: []
next_action: The live S2 session verifies the input socket (A4 through it) and runs the key->paint tail experiments; Batt decides the resting state (R1 recommended) and whether vision becomes S2-only (ADR-0005).
---

# ADR-0014: S2 is the bot's primary capture and input path

- **Status:** DECIDED by Batt, 2026-10-03: "S2 is the bot's primary capture + input path; record it
  as an ADR". The parts marked **PROPOSED** below are still his to decide: the resting state, the
  routine S2-session procedure, and full ADR-0005 closure.
- **Builds on:** [ADR-0009](0009-console-session-capture.md) (one Windows session, the
  capture-backend lock, the clean room) and [docs/s2-plan.md](../s2-plan.md) (the S2 architecture).
- **Keeps:** [ADR-0001](0001-single-rdp-session.md), as amended by ADR-0009: one session, one display
  path. [ADR-0002](0002-input-mux.md): one input writer, every input through the mux.
  [ADR-0004](0004-human-only-clipboard-and-file-transfer.md): clipboard and files are human-only
  and RDP-only.

## The S2 path
The lab's own GameStream client (`services/gamestream/s2spike`) streams from Sunshine on the Dell.
It decodes **once** and publishes every decoded frame to the frame bus (`/framebus/ring`, a seqlock
ring in RAM). No Xvfb sits in the data path:

```
Windows console session (VDD-only) -> Sunshine (QuickSync, ddx) -> S2 client: decode once
   frames: -> frame bus -> backend (console view, /health) + vision (BusFrameSource, read-only)
   input:  mux (HUMAN/BOT/ASSIST, lease, log) -> Injector -> s2-input socket -> S2 client -> LiSend*
```

- **Input, S2 step 3 (2026-10-03):** the backend's Injector, which is still the ONE writer, sends
  each batch the mux accepted over a unix socket to the S2 client. The socket sits on the `s2-input`
  tmpfs, mounted ONLY in backend and gamestream (`test_guards.py`). The client acks once its LiSend*
  calls have returned, so `t_injected` keeps its meaning.
- **No window takes input.** An unmapped *presence* window (WM_CLASS `moonlight`/`S2client`) keeps
  rdp-loop's interlock, `/health` and to-console's gate unchanged. Batt chose this.
- **The variant:** `S2` = `PAINT=bus INPUT=socket`, in `state/gamestream-variant`.

## Evidence (SPEC v2, 2026-10-02/03)

| run | fps out | fps in | lab cores, motion | idle | packet→frame p50 / p95 ms | key→paint p50 / p95 ms | HP/SP PSNR |
|---|---|---|---|---|---|---|---|
| RDP v2 (FreeRDP 3.32.1, progressive) | 23 | 13 | 5.41 | 0.47 | 375.9 / 521.2 | **101.1 / 114.1** | lossless |
| V3 (S2 client painting X) | 33 | 5 | 1.50 | 1.24 | 118.9 / 302.2 | 137.6 / 350.3 | 37.9 dB |
| **V3b (S2 client → frame bus)** | **30** | **16** | **1.03** | 0.78 | **113.9 / 268.3** | 121.0 / 277.1 | 37.85 dB |

Runs: [RDP v2](../benchmarks/2026-10-02-rdp-d16fcc9cff64-v2-baseline.md),
[V3](../benchmarks/2026-10-03-console-5c7e5e8e1301-cleanroom-v3-s2spike.md),
[V3b](../benchmarks/2026-10-03-console-26fa31049e16-cleanroom-v3b-framebus.md).

**Caveats.**
- **Clocks differ.** S2 times are the bus frame's decode-complete time. RDP times are an X grab, so
  RDP's key→paint includes its grab-loop phase and S2's does not. Measurement parity (the
  per-frame split) is part of the experiments below.
- **S2 is lossy.** H.264 at 20 Mb/s gives about 38 dB on the HP/SP crop, against RDP's lossless
  progressive codec. Phase 2 re-baselines its templates and anchors on stream frames for that reason.
- **The open gap is key→paint's tail** (p95 277 vs 114). V3b's distribution is bimodal: p75 133 ms,
  p90 257 ms. The pre-registered experiments are in
  [s2-latency-experiments.md](../benchmarks/s2-latency-experiments.md); their results are appended
  there and summarised here when known.

## Roles
| Path | For | Notes |
|---|---|---|
| **S2** | perception, datasets, the fast loop (BOT/ASSIST) | Frames from the bus; input over the socket. Everything the bot sees and does. |
| **RDP** | the human's admin path | ADR-0004's clipboard and `\\tsclient\transfer` exist only over RDP, and elevated work happens there. Batt answers UAC; the agent never does. |

The capture-backend lock still decides which path owns the one session (ADR-0009). The two never
run at once.

## Resting state (PROPOSED: Batt decides)
| | R1: RDP at rest, S2 sessions on demand | R2: S2 at rest |
|---|---|---|
| Idle cost | 0.47 lab cores (RDP v2) | ~0.78 lab cores (V3b), and Windows encodes continuously |
| Admin tools (paste, files) | ready | need a switch to RDP (~1 min handover) |
| Bot readiness | one handover (~1 min) before a session | immediate |
| Risk surface | the known, long-run path | the S2 client running for days is not yet measured |

**Recommendation: R1** until the routine S2 session (below) has a few clean runs, then reconsider
R2.

## Routine "S2 session" (PROPOSED: follows the resting-state decision)
This replaces the ad-hoc clean room for normal work. A planned `scripts/s2session.py
start|status|extend|end`, built on cleanroom.py's machinery, would provide:
- REASON `s2session`, variant `S2` (plus whitelisted experiment knobs);
- a watchdog with a hard cap and boxes, as in the clean room (a 10-min stale heartbeat ends the
  session; it defers to a human at the console);
- a heartbeat kept by the runner and by every long job (recorder, bench);
- exit checks: one session (`qwinsta`), ensure_only_display restored, the lock back to `rdp`;
- **clients restarted, not one-shot.** A crashing S2 client is retried with backoff, but never
  faster than gamestream-loop's existing rule.

This weekend uses `cleanroom.py`, the approved tooling. `s2session.py` is built once Batt picks
R1 or R2.

## Consequences
- **Phase 2 is re-baselined on stream frames:** calibration (`camera_console.json`), stream variants
  of every template and anchor, and the chat template re-cut. Datasets are recorded through S2:
  - `record_session.py` v3 stores the bus `frame_id` and decode time;
  - it stops on a non-bus frame;
  - `qa_export` matches the offset run by backend, client and paint.
- **ADR-0005 on the S2 path:**
  - The frame bus (option a) and the input socket remove vision's NEED for X; vision uses
    `VISION_FRAME_SOURCE=bus`.
  - **PROPOSED for full closure:**
    - "vision S2-only": drop vision's `x11-unix` mount, so it cannot reach X at all;
    - option (c2), the internal agent network, for rows 2–3 of ADR-0005's acceptance test.
  - Batt decides. Until then ADR-0005 stays PROPOSED and Phase 4 stays gated on it.
- **ADR-0002 is unchanged in substance.** One writer: the Injector picks a sink (XTest or the S2
  socket); it never adds a second writer. A switch first sends ReleaseAll to the sink being left.
- **CLAUDE.md rule 2** now reads: the path is the RDP session, OR the console-mode stream (Sunshine
  → the S2 client, or Moonlight-qt) under the capture-backend lock.
- **Not yet verified live (2026-10-03, pending the S2 session):**
  - A4 through the socket: `@where`, walk, right-drag, Thai HEX, Flags 62;
  - the input leg in `/health.input_sink`;
  - the presence marker satisfying to-console's gate.
