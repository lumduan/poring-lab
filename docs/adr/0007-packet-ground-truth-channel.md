---
doc_type: decision
hypothesis: null
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: Batt decides (with docs/phase1-plan.md). If accepted, implement with the guards listed below before any packet event reaches the console.
---

# ADR-0007: Packet ground truth — a viewer-only channel and a separate captures volume

- Status: PROPOSED (2026-09-30)
- Deciders: Batt
- Related:
  - [phase1-plan.md](../phase1-plan.md);
  - [ADR-0005](0005-vision-x-access.md), the vision isolation gap;
  - CLAUDE.md hard rule 1 (pixels in; packets are offline ground truth only).

## Context

Phase 1 decodes our own rAthena traffic into a timeline (map, entities, movement, HP/SP, chat),
aligned to frames on the host's CLOCK_MONOTONIC. It is ground truth for labelling and evaluation.
Humans also want it live next to the screen, to learn and debug.

Two facts about today's stack make a naive design break principle 2 (no packet data at decision
time):
1. **`vision` mounts `./data`** (`compose.yaml`). Captures written under `data/` would be readable by
   the agent.
2. **The network is flat** (ADR-0005). vision can open any `:8000` WebSocket without an Origin; all
   routers are mounted on both listeners; and the sniffer, which shares rathena's namespace, can
   reach `:8001`, where `/internal/agent` would accept it as the BOT.

## Decision

1. **Captures live in a new named volume `captures`.**
   - It is mounted read-write by `sniffer` and read-only by `backend`, and by nothing else.
   - Never under `./data`.
   - The password bytes of CA_LOGIN are zeroed before anything is written.
2. **Ingest.** The sniffer pushes decoded events to the backend on a dedicated route,
   `/ingest/packets`.
   - It is accepted only on the internal listener, and only from rathena's pinned IP.
   - It is one-way.
   - It is never `/internal/agent`.
3. **Viewer channel.** `/ws/packets` on the public listener `:8000`, with its own bounded outbox. It
   refuses, and counts each refusal (never silent):
   - connections that arrived on the internal port;
   - any peer in the compose subnet (`10.210.96.0/24`), which covers vision;
   - connections without a browser Origin in the allowlist.
4. **Nothing in the agent path can carry packet data.**
   - No `Packet*` model is reachable from the agent-side schemas (`agent_to_backend`, `input_event`,
     `backend_to_agent`); `test_protocol` reachability tests enforce this.
   - vision's image doesn't install `poring_packets`.
   - `test_guards` fails if vision sources mention `poring_packets`, `/ws/packets` or `captures`, or
     if vision mounts `captures`.

## Consequences

- The console gets a live, read-only packet timeline, and principle 2 stays enforceable by tests
  rather than by convention.
- The compose-subnet refusal is the same mechanism as ADR-0005's option (c2), applied early to this
  one route. When ADR-0005 moves vision onto its own `agent` network, the check stays valid; it can
  then name that subnet instead.
- The ADR-0005 gap itself (vision's direct X access, and `:8000 /ws/input` as HUMAN) is **not** closed
  by this ADR. It remains a Phase 4 blocker. This ADR only guarantees that the new channel doesn't
  widen it.
- One more route to test on both listeners, and one more volume in the guard tests.
