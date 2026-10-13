---
doc_type: decision
hypothesis: null
status: GO
role: null
verdict_date: 2026-10-01
verdict_ticket: null
supersedes: null
related: []
next_action: "➡️ 2026-10-10 02:50: the image carrying LoginScrub (f36276e, login ports from the environment + every login-shaped connection) is LIVE, verified by scripts/scrub_check.py and the §2a positive cases (demonstrations.md §2a). Amendment C (code from a source mount) ACCEPTED 2026-10-13 (Batt), BUILT the same day; live at the next guarded recreate:sniffer. History: Implemented and validated (docs/phase1-validation.md). The slim sniffer image is LIVE since 2026-10-03 (71 MB, guarded build; live re-verified: ingest, validation tagging, password zeroing). GAT in Phase 2."
---

# ADR-0007: Packet ground truth — a viewer-only channel and a separate captures volume

- Status: **ACCEPTED** (Batt, 2026-10-01). Proposed 2026-09-30. Implemented the same day; see
  "Acceptance decisions" and "Implementation notes" below, and
  [phase1-validation.md](../phase1-validation.md).
- Deciders: Batt
- ➡️ 2026-10-09: Amendment C (PROPOSED, at the end) would change Acceptance decision 2 in dev
  mode: the sniffer's code from a read-only source mount, no image build for a code change.
- ➡️ 2026-10-09: [ADR-0021](0021-external-servers.md) (PROPOSED) would add, for an allowed
  EXTERNAL server: nothing is captured there ~~by design~~ ➡️ BY DEFAULT (Batt, 2026-10-09
  ~15:20: only where that server's own rules permit it, recorded in Settings; ADR-0021 4.5);
  this channel's viewer shows an explicit
  `external` state (built dormant on `feat/console-layout`), and every packet-based tool reports
  "not available on this environment". Decision 4 (nothing in the agent path) is unchanged.
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
   ➡️ SUPERSEDED: there is no disk split (Batt, 2026-10-01). The slim image (`services/sniffer`,
   71 MB, the length table shipped in the wheel and checked at BUILD time) was built in a guarded
   weekend window and replaced the overlay on 2026-10-03. Live re-check after the switch: ingest
   connected, a GM relog captured (`login_accepted` → `map_enter`), 36 events tagged
   `validation_account`, and the GM password and user found 0 times in the new pcapng (the GM
   character name, the positive control, 7 times).
   ➡️ 2026-10-09: [Amendment C](#amendment-c-accepted-2026-10-13-proposed-2026-10-09-the-sniffers-code-from-a-read-only-source-mount-in-dev-mode)
   (PROPOSED, for Batt's acceptance) would run the sniffer's CODE from a read-only source mount in
   dev mode again, on the slim image's dependencies, so a code change needs no image build.
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

## Amendment (Batt, 2026-10-02): packet-assisted calibration at session start

**Context.** [phase2-plan.md](../phase2-plan.md) D3 proposes replacing the 42-click camera grid
with a short self-check at session start: a few walk clicks, each paired with the client's own
`self_move_request` target cell from the packets, then a homography fit. That moves a packet read
closer to decision time than this ADR's "offline ground truth only" line.

**Ruling.**
1. **Allowed, on our rAthena only, as a SETUP / ground-truth tool.**
   - It may run at session start and calibrate the camera (geometry, not world state).
   - Its output is a profile, the same artefact the operator grid produces.
2. **Never a per-action decision input.**
   - No packet value reaches the policy or the fast loop.
   - The agent-path isolation in Decision 4 is unchanged: no `Packet*` model on agent schemas,
     vision without `poring_packets`.
   - The calibration runs on the backend/tool side and hands the agent a profile, never packets.
3. **The deployable bot must also have a pixels-only calibration path,** for servers without packet
   access (the community server, ADR-0006). D3 must ship both. The pixels-only path is the one
   acceptance is judged on outside rAthena.
   ➡️ 2026-10-09: under ADR-0021 (PROPOSED) the pixels-only path is the ONLY calibration path on
   an external server; the packet-assisted tools report "not available" there.

**Consequences.** D3 moves from "needs Batt's ruling" to "planned". Its tests must show:
- the agent never receives packet-derived values, only the profile;
- the pixels-only path reaches the stored profile's residual on rAthena (validated against the
  packet-assisted fit there).


## Amendment C (ACCEPTED 2026-10-13; proposed 2026-10-09): the sniffer's code from a read-only source mount in dev mode

> ➡️ **ACCEPTED by Batt, 2026-10-13** (decision 7: "ADR-0007 Amendment C: ACCEPTED"). It is implemented as
> written below: the dev overlay, its guard test, and CLAUDE.md's dev-mode text. It goes live at a guarded
> `recreate:sniffer` in a measured quiet window, and the §2a positive cases are re-run after it.
> ➡️ **BUILT 2026-10-13** (`compose.dev.yaml` sniffer overlay; `poring_packets/selftest.py`; the
> sniffer stamps SNIFFER_COMMIT into its log and every capture's SHB; `guarded_build.sniffer_code_gate`;
> tests in test_guards / test_guarded_build / packages/poring_packets/tests/test_selftest.py). One
> stricter detail than point 6: `restart:sniffer` is REFUSED, because a restart keeps the environment
> (the old SNIFFER_COMMIT) of the container's creation; `recreate:sniffer` is the step. NOT LIVE until
> that guarded recreate (needs the client free + ASSIST for the GM's auto re-login).

**Status (as of 2026-10-09):** PROPOSED, for Batt's acceptance (his call of 2026-10-09 ~20:20: "Option C (sniffer code
from a bind-mounted source, no image build for code changes): write it as an amendment to
ADR-0007's slim-image decision for my acceptance"). Nothing is built or changed until he accepts.

**Context.**
- Every `poring_packets` change reaches the live sniffer only through a guarded `build:sniffer` +
  `recreate:sniffer` (Acceptance decision 2, as superseded on 2026-10-03; CLAUDE.md "Dev mode").
- Builds are the most IO-expensive step we run on the shared disk, and quant's live capture pays
  for them. On 2026-10-09 the build that carries the password-scrub fix (f36276e, ADR-0021 risk 1)
  aborted 18 s in, in a MEASURED quiet window (`quiet_start`: 10 min with no capture cgroup above
  25 %): 19:50:32 ICT the capture cron 99.9 %, quant-orderbook 99.1 %, quant-ticker 98.7 % full IO
  stall; the guard stopped it at 19:50:42 (quant-postgres 25.2 %). The context is ~15 MB, so the
  burst is the build itself (the uv install into a new layer and the layer export), not the
  context.
- A security fix therefore waits for a night slot (option D, 2026-10-10 02:00-04:00), and every
  future decoder change will too.

**Proposal (dev mode only; the image path is unchanged and stays the production form).**
1. **The slim image stays the dependency base.** Python, pydantic, websockets and the image's
   installed `poring_packets` are unchanged. A DEPENDENCY change (pyproject, uv.lock) still needs a
   guarded build.
2. **The code comes from the host, read-only.** `compose.dev.yaml` mounts
   `./packages/poring_packets/src` at `/dev-src/poring_packets:ro`, as the backend's overlay does
   today, and puts it first on `PYTHONPATH`. The rest of the hardening is unchanged: user 0:0 with
   only NET_RAW, the read-only rootfs, rathena's network namespace, the captures volume, no `./data`.
3. **A consistent snapshot per start.** The entrypoint copies the mounted package into the
   container's tmpfs and runs from that copy. An edit on the host can never be half-imported into
   a running sniffer (a lazy import of a newer module); it goes live only at the next start.
4. **The length table is checked at START instead of at build.** The mounted tree carries the
   locally generated `_generated/lengths.json` (gitignored, from `scripts/gen_packet_tables.py`).
   The sniffer runs the same `load()` check against `tables.lock.json` before it opens the socket
   and REFUSES to start on a mismatch (fail closed, as the build does now).
5. **A start-time scrub self-test, fail closed.** Before capturing, the sniffer feeds `LoginScrub`
   one synthetic login request per id in `LOGIN_REQUEST_IDS`, carrying a dummy secret, on a port
   from `SNIFF_LOGIN_PORTS` and on one that is not, and refuses to start unless every dummy secret
   is zeroed. A broken edit to the scrub can then never capture a real password: it cannot start.
6. **Only committed code goes live.** The guarded step that restarts the sniffer
   (`guarded_build.py recreate:sniffer` / `restart:sniffer`) refuses when `git status --porcelain
   packages/poring_packets` is not clean, and records the commit. The sniffer writes that commit
   (passed in the environment by the step) into its start log and into each capture's metadata, so a
   banked capture still names the decoder that produced it, as the image tag does today.
7. **Still one container start at a time.** A recreate is a container start: it goes through the
   guard (and `quiet_start` when the operator asks for a measured window), never alongside a vision
   cold start. After it, the interlock reads `no_session` until the next login and guarded_build
   re-logs the GM in by itself, as now.
8. **Tests.** `test_guards.py`'s `test_the_dev_overlay_runs_the_slim_sniffer_image` becomes: the dev
   overlay mounts ONLY `packages/poring_packets/src`, read-only, on the slim image; no other service
   gains a mount; vision still never sees `poring_packets` (Decision 4). New unit tests cover the
   start-time table check, the scrub self-test (including a deliberately broken scrub that must
   refuse) and the dirty-tree refusal.
9. **Rollback.** Remove the overlay entry: the image's own installed copy runs again, as today.

**What it costs.**
- The guarantee that the running decoder equals a built, table-checked image moves from build time
  to start time (points 4-6 restore it at start).
- One more host mount into a container that holds NET_RAW (read-only, code only).
- Production (non-dev) deployments keep the image path; this is the lab's dev loop.

**What it buys.** A decoder or scrub fix goes live with a guarded recreate (seconds of light IO)
instead of a build (the 2026-10-09 bursts), so a security fix no longer waits for a night slot.

**Decision needed from Batt:** accept / change / reject. Until then the sniffer stays on the image
path and tonight's option D build is the way the scrub goes live.
