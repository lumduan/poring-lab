---
doc_type: decision
hypothesis: null
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: Batt picks the option set (recommended a + c1 + c2 + c3); implement it with the acceptance test below BEFORE roadmap Phase 4 (fast loop with input through the mux).
---

# ADR-0005: The vision container must not have full X access

- **Status:** PROPOSED (2026-09-30). **Blocks roadmap Phase 4.** Nothing is implemented yet.
- **Tracked in:** [issue #1](https://github.com/lumduan/poring-lab/issues/1) (`blocks-phase-4`, `security`).
- **Related:**
  - [ADR-0002 input mux](0002-input-mux.md): "single input owner".
  - [ADR-0003 env abstraction](0003-env-abstraction.md): `Env.grab()`.
  - [ADR-0004 human-only clipboard + transfer](0004-human-only-clipboard-and-file-transfer.md).
  - [ADR-0006 sanctioned environments](0006-sanctioned-test-environments.md): its environment
    interlock (rule 2) is the other prerequisite of Phase 4. This ADR stops vision from bypassing
    the mux; ADR-0006 stops the mux from automating the wrong server.

## Problem

"The agent acts only through the mux" (ADR-0002) and "clipboard and files are human-only" (ADR-0004)
are enforced **by convention** at the X and network level. The code and the protocol enforce them;
the infrastructure does not.

1. **X is wide open.**
   - Xvfb runs with `-ac` (no access control).
   - vision mounts the socket directory `x11-unix:ro`, and `:ro` does **not** block `connect()`. The
     backend mounts it `:ro` too and drives XTEST through it.
   - So any process in the vision container can:
     - inject input through XTEST, bypassing the mux, the lease and the input log;
     - own CLIPBOARD, or read it during the ~1 s a human paste is being served (ADR-0004);
     - GetImage any window;
     - record every key the human types through the RECORD extension, which Xvfb enables.
2. **The network is flat.** vision sits on the default compose network with everything else:
   - it can open `ws://backend:8000/ws/input` with no Origin, and is accepted as **HUMAN** input
     (script clients are allowed by design);
   - it can call the `/transfer` routes with a *forged* Origin header (ADR-0004 requires an Origin,
     but cannot authenticate one).

Today vision's code does none of this. `test_guards.py` greps it, and the loop only calls
`X11Capture` and `MuxedEnv`. But a learned policy (Phase 4+), a compromised dependency or a
debugging shortcut is exactly what would.

## Options

### (a) Frames come from the backend; vision has no X at all

`Env.grab()` keeps its signature (ADR-0003) and gets a new implementation that reads frames the backend
captured. The backend already captures at 30 fps for the stream.

- **Transport, shared memory:** a POSIX shm ring (compose `ipc: "service:backend"`, or a dedicated
  tmpfs volume). The backend writes BGRA frames, each with a seqlock header; vision maps it
  **read-only**. Cost: one memcpy of ~3.7 MB per 1280×720 frame, sub-millisecond on this host, and no
  serialisation.
- **Transport, internal socket:** raw BGRA over `:8001`. That is ~110 MB/s at 30 fps through loopback
  TCP: simple, but CPU on both sides. JPEG would be cheaper, but loses the fidelity Phase 2/3 needs.
- **Trade-offs:**
  - One extra copy.
  - Vision's grab rate is coupled to the backend's capture: it can ask for on-demand capture, or take
    the latest ring slot.
  - A **single `frame_id` domain** for the stream, the agent and the logs. That is a *benefit*: today
    they number frames independently (ADR-0003).
  - **Latency and copies are to be measured in Phase 0**, alongside motion-to-photon.

### (b) X SECURITY extension: vision connects as an "untrusted" client

**Measured 2026-09-30** on a throwaway Xvfb (the same binary as the desktop's), with the cookie
required:

| Untrusted client attempts | Result |
|---|---|
| Connect with a wrong cookie | refused immediately |
| Query XTEST, MIT-SHM, XFIXES, RECORD, XInputExtension, BIG-REQUESTS | all hidden |
| `GetImage` on the root window | **BadAccess**: the capture vision needs is blocked |
| XTEST fake key | fails (extension hidden) |
| `SetSelectionOwner(CLIPBOARD)` | **succeeds**, and is visible to trusted clients (xfreerdp) |

**Rejected.** It blocks the one thing vision must do (capture), and it does *not* block the clipboard
ownership ADR-0004 worries about.

### (c) Close the X socket and segment the network

- **(c1) X auth cookie.** Drop `-ac` and start Xvfb with `-auth <cookie file>`. The cookie lives in a
  small volume mounted only in desktop (Xvfb, xfreerdp, x11vnc) and backend.
  - vision gets neither the cookie nor the `x11-unix` mount.
  - The measured wrong-cookie refusal above shows the gate works.
  - This *requires* (a), because vision then has no way to capture.
- **(c2) An internal `agent` network** (`internal: true`, pinned to a 10.x subnet, never 192.168.x;
  see CLAUDE.md rule 6), holding backend and vision only.
  - vision leaves the default network, so it can no longer reach the frontend or anything else.
  - The backend listens on every interface, so the **public routes must refuse clients from the agent
    subnet**: `/ws/*` and `/transfer/*` return 403, while `/internal/agent` stays `:8001`-only.
- **(c3) Drop unneeded X extensions:** `Xvfb -extension RECORD`, since nothing in the lab records.
  This removes keystroke recording by any X client, even a trusted one. It is cheap and independent.

## Recommendation

**(a) + (c1) + (c2) + (c3).** The resulting ownership:

| Actor | What it may use |
|---|---|
| desktop | Xvfb, xfreerdp, x11vnc |
| backend | the one XTEST writer, the capture, the clipboard owner |
| vision | pixels through the backend and input through `/internal/agent` only, so it structurally cannot do anything else |

(c3) can land any time. (a) and (c1) land together, then (c2).

## Acceptance test

A script run **from inside the vision container** passes only if every one of these holds:

| # | Attempt from vision | Must |
|---|---|---|
| 1 | Connect to `:99` | fail: no socket or no cookie. XTEST injection and CLIPBOARD ownership are therefore impossible (it tries both anyway, in case a socket exists) |
| 2 | `ws://backend:8000/ws/input` and `http://backend:8000/transfer/files`, with and without a forged Origin | be unreachable or refused |
| 3 | `ws://backend:8001/internal/agent` | work |
| 4 | `Env.grab()` | return frames at the agent's target rate with increasing `frame_id`s |

It goes in `scripts/` with the implementation, and is part of Phase 4's entry gate.

## Note (2026-10-02): S2 implements option (a) for the GameStream path

The S2 architecture (approved by Batt 2026-10-02; [docs/s2-plan.md](../s2-plan.md), ADR-0009 2026-10-02 amendment)
decodes the GameStream video once, into a shared-memory frame bus. vision maps the bus
**read-only** and never touches X on that path. That is option (a), with these specifics:
- a seqlock ring;
- latest-wins reads;
- per-consumer drop counters in `/health`;
- one `frame_id` domain for the bot, the console and the logs.

**What this closes, and what stays open:**
- It closes the X-access gap **for the GameStream path only**.
- RDP mode still renders into Xvfb. Options (c1)–(c3) are still needed for that path, unless vision
  also reads a bus there (a backend-fed ring from its X capture: the same code, another writer).
- The ADR's status is unchanged (PROPOSED) until Batt approves S2. This note records the intended
  implementation route only.

## Tracking

[lumduan/poring-lab#1](https://github.com/lumduan/poring-lab/issues/1), labelled `blocks-phase-4` and `security`.
