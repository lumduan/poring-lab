---
doc_type: decision
hypothesis: null
status: GO
role: null
verdict_date: 2026-09-29
verdict_ticket: null
supersedes: null
related: []
next_action: Add a replay Env (recorded frames + input log) for offline evaluation once Phase 0 capture data exists.
---

# ADR-0003: The Env contract — `grab()` pixels, `send_input()` mouse/keyboard

- **Status:** accepted and implemented in the scaffold (2026-09-29)
- **Code:** `packages/poring_env/` (checked with `mypy --strict`)
- **Related:** [ADR-0001 single RDP session](0001-single-rdp-session.md),
  [ADR-0002 input mux](0002-input-mux.md)

## Context

The project's core principle is that the agent perceives the game **only through pixels** and acts
**only through mouse and keyboard**. No memory reading and no packet injection. Packet capture is
allowed later, strictly as offline ground truth. The agent's code must also outlive today's transport
(X11 over Xvfb over RDP): replaying recordings for offline evaluation should need no agent changes.

## Decision

1. **One contract.** `poring_env.Env` has `grab() -> Frame` and `send_input(InputEvent)`, and nothing
   else. It is built from two small protocols, `FrameSource` and `InputSink`, which is what makes the
   transports swappable.

   | Implementation | Grab | Input | Used by |
   |---|---|---|---|
   | `X11Env` (`x11.py`) | mss → Xvfb | XTest | the backend only (the mux's injector) |
   | `MuxedEnv` (`remote.py`) | mss → Xvfb | WebSocket → backend mux | the vision agent |
   | *replay (TODO)* | recorded frames | recorded or ignored | offline evaluation |

2. **`Frame`** holds tightly packed BGRA exactly as X returns it, plus `frame_id` and `t_capture_ns`.
   `to_numpy()` and `bgr()` are zero-copy, read-only views. BGR is the OpenCV/ultralytics convention.
3. **The wire protocol lives in the same package** (`protocol.py`, Pydantic). Input events *are*
   `send_input`'s argument type.
   - The models are the single source of truth.
   - `poring-protocol-schema` exports the JSON Schema to `packages/poring_env/schema/`.
   - `json-schema-to-typescript` then generates `services/frontend/src/lib/protocol.gen.ts`.
   - A pytest snapshot fails whenever the committed schema drifts; `scripts/gen_protocol.sh`
     regenerates both files.
4. **Time and identity on every message:** `t_mono_ns` and `frame_id`.
   - `t_mono_ns` is the **sender's** monotonic clock. Docker gives containers no separate time
     namespace, so the backend and vision share the host's `CLOCK_MONOTONIC`. Their timestamps subtract
     directly.
   - The browser's `performance.now()` is a separate domain, related only through ping/pong echo
     (`Pong.echo_t_mono_ns`). The two clocks are never subtracted from each other.
   - `frame_id` is per grabber. Backend (stream) and vision (inference) number their frames
     independently. Detections carry the agent's `frame_id` **and** `t_capture_ns`, so any alignment
     with stream frames goes by time.
5. **Coordinates and keys are transport-neutral.**
   - Pointer positions are normalized to [0, 1].
   - Keys are `KeyboardEvent.code` (a physical key), mapped to the Linux evdev code and then to the X
     keycode (+8). That matches Xvfb's `evdev` XKB keycodes, which xfreerdp maps to RDP scancodes.
     There is no keysym or layout dependence; Windows applies its own layout.
6. **Extras keep the contract light.** Importing `poring_env` needs no display. `x11` (mss,
   python-xlib) and `remote` (websockets) are optional extras.

## Consequences

**Positive**

- Agent logic runs against fakes (`services/vision/tests`) and, later, a replay env, without touching
  its code.
- Latency is measurable end to end on one clock.
- Frontend types cannot silently drift from the backend.

**Negative**

- Two capture paths (stream and agent) mean two `frame_id` spaces; alignment goes by `t_capture_ns`.
- JavaScript parses the ns integers as float64, losing sub-microsecond precision after about 104 days
  of host uptime. Irrelevant at millisecond resolution; revisit only if sub-µs matters.
- mss and python-xlib connections are per thread, so callers dedicate a capture thread and an input
  thread (the backend does both).

## Alternatives considered

- **Vision receives frames from the backend over WebSocket.** Adds JPEG encode/decode, costs fidelity
  and latency, and couples the agent to the stream's rate. Rejected for the agent path; the stream is
  for humans.
- **A shared-memory ring buffer** between capture and consumers. A Phase 0+ optimization if
  measurements justify it.
- **Keysym-based keys (`event.key`).** Layout-dependent, and breaks under non-US layouts on either
  side. Rejected.
