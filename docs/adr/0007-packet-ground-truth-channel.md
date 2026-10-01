---
doc_type: decision
hypothesis: null
status: GO
role: null
verdict_date: 2026-10-01
verdict_ticket: null
supersedes: null
related: []
next_action: Implemented and validated (docs/phase1-validation.md). Slim sniffer image in a guarded build window (no disk split, 2026-10-01); GAT in Phase 2.
---

# ADR-0007: Packet ground truth — a viewer-only channel and a separate captures volume

- Status: **ACCEPTED** (Batt, 2026-10-01). Proposed 2026-09-30. Implemented the same day; see
  "Acceptance decisions" and "Implementation notes" below, and
  [phase1-validation.md](../phase1-validation.md).
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
   - ➡️ TIGHTENED at implementation (2026-10-01): it **accepts only `VIEWER_NETWORKS`** (default
     `192.168.0.0/16`), so the gateway is refused too. See "Implementation notes".
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

## Acceptance decisions (Batt, 2026-10-01)

1. **Length tables are generated at build time from pinned sources, never committed.**
   - The sources are rAthena at `e985006…` (struct sizes and the C→S packet DB) and OpenKore's
     `recvpackets.txt` at `51de1dd…`, a cross-check that fills gaps.
   - `scripts/gen_packet_tables.py` writes `_generated/lengths.json` (gitignored).
   - What is committed is only the generator and `tables.lock.json`: input and output SHA-256, plus
     every rAthena/OpenKore disagreement. Any disagreement on a decoded id is fatal, and so is drift
     from the lock.
2. **The sniffer runs on the dev overlay** (the backend image plus the host source; no build). A
   slim image comes after the disk split.
3. **GAT later (Phase 2).** Until then, paths are rAthena's diagonal-first fallback. That is exact
   on open ground; around obstacles, the error is bounded by the detour.

## Implementation notes (2026-10-01)

- **The hairpin residual was real, and it is closed.**
  - A live probe from the sniffer container (vision's network position) dialled the *published*
    port with a forged Origin. Docker's proxy delivered it from the lab gateway `10.210.96.1`, the
    same address host scripts use, and it was **accepted**.
  - `/ws/packets` now accepts only `VIEWER_NETWORKS` (browsers keep their real LAN address through
    Docker's DNAT) and refuses the whole compose subnet, gateway included.
  - Re-probed: refused (`compose_peer`). Host scripts read `/captures` instead.
- **Entity identity** is the block id (AID @5 of the entry packets), not the char_id (GID @9, 0 for
  monsters). Found by the live entity check (`42e2d4d`).
- **Sensitive agent input.** `AgentInput.sensitive` makes the input log keep counts and timing
  only, and refuses a batch that leaves anything held. ro_agent types credentials this way.
  - This is not part of the packet channel, but it shipped with it.

