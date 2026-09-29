---
doc_type: decision
hypothesis: null
status: GO
role: null
verdict_date: 2026-09-29
verdict_ticket: null
supersedes: null
related: []
next_action: Keep the mux the single XTest writer as policies land; add input-log rotation/compression before long unattended runs.
---

# ADR-0002: Input mux — one writer, three modes, a human lease

- **Status:** accepted and implemented in the scaffold (2026-09-29)
- **Code:** `services/backend/src/poring_backend/mux.py` (pure state machine) and `state.py` (injector
  and log). Tests are in `services/backend/tests/test_mux.py` and `test_app.py`.
- **Related:** [ADR-0001 single RDP session](0001-single-rdp-session.md),
  [ADR-0003 env abstraction](0003-env-abstraction.md)

## Context

A human (browser) and a bot (vision agent) share one game session (ADR-0001). This needs:

- arbitration: who may act, and when;
- safety: no stuck keys when control changes hands, and no way to kill the RDP session from the
  input path;
- complete, attributed records of every input — the research data for imitation learning and
  evaluation;
- no bypass: an input path that skips the rules also skips the records.

## Decision

1. **Single-writer invariant.** Only the backend's `Injector` touches XTest.
   - It owns exactly one X connection and one worker thread, so events apply in exactly the order the
     mux decided them.
   - The agent never injects directly: `MuxedEnv` sends to `/internal/agent`.
   - noVNC is view-only.
2. **Modes.** The backend **always boots in `HUMAN`**, so a host reboot can never resume a bot on its own.

   | Mode | Human input | Bot input |
   |---|---|---|
   | `HUMAN` | passes | dropped (`mode=HUMAN`) |
   | `BOT` | dropped (`mode=BOT`) | passes |
   | `ASSIST` | always passes, and takes the **lease** | passes only while no lease is active (`human_lease`) |

3. **The lease** (`ASSIST_LEASE_S`, default 3 s) lasts 3 s after the last human event. It also lasts
   for as long as the human holds any key or button, so a held Shift or right-drag is never interrupted.
4. **Handoffs release what the loser holds.**
   - When a source loses control (a mode switch, or a human taking the lease), the mux emits synthetic
     key and button **ups** for everything that source holds.
   - Synthetic button releases carry no coordinates, so they never move the pointer the new controller
     is using.
   - `release_all` expands into explicit ups.
   - A closed browser tab or a disconnected agent releases everything that source holds. That cleanup
     runs as a shielded task, so it completes even while the connection handler is being cancelled.
5. **Refused before injection:**
   - unknown `KeyboardEvent.code`s (`unknown_key_code`). Meta keys are unmapped on purpose: they open the
     Windows Start menu.
   - xfreerdp client hotkeys Ctrl+Alt+D and Ctrl+Alt+Enter (`reserved_chord`), which would act on the
     one RDP session itself.
6. **Everything is logged.**
   - `data/input_log/YYYY-MM-DD.jsonl` (UTC days) gets one line per submitted event, accepted or
     dropped, plus one per synthetic release.
   - Fields: `t_mono_ns` (backend clock at decision), `t_wall`, `source=human|bot`, `mode`,
     `accepted`, `reason`, `synthetic`, `frame_id`, `event`. The event carries the sender's own
     timestamps.
7. **Channels.**
   - Human input and `set_mode` travel on `/ws/input`. Mode changes are a WebSocket message, so
     there's no REST/CORS surface.
   - The bot uses `/internal/agent` on a **second listener, `:8001`**: one uvicorn server with two
     sockets. It is reachable on the compose network only, and the route refuses connections that did
     not arrive on `:8001`.
   - Browser WebSockets must present an `Origin` in `ALLOWED_ORIGINS`, which blocks cross-site
     WebSocket hijacking from any LAN browser tab. Non-browser clients send no `Origin`.

## Consequences

**Positive**

- The rules are a pure function of (state, event, clock), so they are exhaustively unit-tested.
- Every input is attributed and recorded.
- Stuck keys are structurally prevented.

**Negative**

- One extra local hop (WebSocket, then the executor) on the bot's input path. Sub-millisecond; Phase 0
  measures it.
- All browser tabs share the single identity "human". One tab closing releases keys another tab holds.
- Mouse-heavy sessions write on the order of 1 GB/day of JSONL. Rotation and compression are a TODO
  before long unattended runs.

## Alternatives considered

- **Bot injects via XTest directly.** Races with the human, bypasses arbitration and the log. Rejected.
- **A lease without the "held keys" extension.** The bot could act mid-drag. Rejected.
- **REST endpoint for mode switching.** Adds a CORS surface for no gain over the input socket.
- **Shared-token auth on one public port** instead of the port split. A token in `.env` works too, but
  an unpublished listener cannot be reached from the LAN at all.
