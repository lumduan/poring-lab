---
doc_type: decision
hypothesis: null
status: GO
role: null
verdict_date: 2026-10-04
verdict_ticket: null
supersedes: null
related: [../planning/gpu-live-detector.md, ../benchmarks/cpu-detector-speed.md]
next_action: CLOSED for the S2 path (vision S2-only + c2, acceptance 5/5 PASS 2026-10-04). Re-run services/vision/acceptance/adr0005.py after any change to vision's mounts, networks or the backend's listeners; RDP-mode vision stays unsupported. AMENDMENT 2026-11-07 (Batt chose option A): the vision WORKER's detect socket, frames in and numbers out (section at the end); its acceptance re-run is row 6 plus rows 1-5 inside the worker.
---

# ADR-0005: The vision container must not have full X access

- **Status:** CLOSED for the S2 path (2026-10-04; Batt approved "vision S2-only + option c2").
  Its acceptance test passes 5/5, run inside vision while S2 streamed (below). Proposed 2026-09-30.
  vision is no longer a Phase 4 blocker; it runs on the S2 path only, and an RDP-mode vision is
  not supported (it would need (c1)/(c3) and a new acceptance run).
- ➡️ **Amended 2026-11-07 (Batt chose option A):** the vision WORKER also serves the host bot's
  detections through ONE unix socket in a host RAM directory: frames in, numbers out, the host
  as the only client. Still no X, no input path, no network. See the amendment at the end.
- **Option (c2) in three lines** (for the record):
  - an internal Docker network (`agent`, 10.210.97.0/24, gateway isolated) holds only the backend
    and vision;
  - vision leaves the default network, so it can reach nothing else (the host, the LAN, the
    internet);
  - the backend refuses that subnet on every listener but `:8001`, so the bot's one way in is
    `/internal/agent` through the mux.
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

## Note (2026-10-03): ADR-0014, the S2 path is the bot's path

- **Built:** the input socket (S2 step 3) and vision's bus source (`VISION_FRAME_SOURCE=bus`).
  vision no longer NEEDS X on the S2 path: frames come from the bus (option a), and input goes
  through `/internal/agent` → mux → the backend's socket.
- **PROPOSED for full closure (Batt decides):**
  - "vision S2-only": remove vision's `x11-unix` mount, so it cannot connect to X at all (acceptance
    row 1);
  - option (c2), the internal agent network (rows 2–3).
- This ADR stays PROPOSED and Phase 4 stays gated on it until then.

## Closure (2026-10-04): vision S2-only + option (c2), built and accepted
**Built:**
- `compose.yaml`: vision has no `x11-unix` mount and no DISPLAY. It reads the frame bus only
  (`VISION_FRAME_SOURCE=bus`), with `YOLO_OFFLINE`/`HF_HUB_OFFLINE`, and sits on the `agent`
  network ONLY.
  - `networks.agent`: `internal: true`, `gateway_mode_ipv4: isolated` (the host has no address
    on it), 10.210.97.0/24.
  - The backend is on `default` + `agent`.
- **The backend:** `AgentNetworkGuard`, the outermost ASGI middleware, refuses the agent subnet on
  every listener but the internal `:8001` (HTTP 403 / WebSocket 1008, counted in
  `/health.agent_network_refused`).
- **Host scripts** take the backend's address by the default network's NAME
  (`scripts/backend_addr.py`): two networks made the old template concatenate both addresses.
- `test_guards.py` pins all of it.

**The acceptance test**, `services/vision/acceptance/adr0005.py`, run with `guarded_build.py
'run:vision@120=python /opt/acceptance/adr0005.py'` (it gained a 5th row for c2):

| # | Row | 2026-10-04 09:4x (S2 not streaming) | 2026-10-04 10:15 ICT (S2 streaming, the session) |
|---|---|---|---|
| 1 | no X socket | PASS | PASS |
| 2 | `/ws/input`, `/transfer/files`, `/health` on :8000, with and without a forged Origin | PASS (all 403) | PASS (all 403) |
| 3 | `/internal/agent` works | PASS | PASS (first message `status`) |
| 4 | `Env.grab()` on the bus, rising frame ids at ≥ AGENT_HZ | SKIP (no writer) | **PASS: 156 frames in 5 s (31.2/s), rising** |
| 5 | network closed: the host's LAN/bridge/docker0 ports, the router, 1.1.1.1:443, external DNS | PASS | PASS |

## Amendment (2026-11-07): the vision worker's detect socket (gpu-live-detector.md option A)

- **Decision:** ACCEPTED by Batt, 2026-11-07, answering the GPU report's options ("เลือก A": pick
  A) and "อนุมัติให้ใช้ gpu แทน cpu ในการ detect ของ bot ได้เลย" (approved: the bot's detection
  may use the GPU instead of the CPU). The measurement behind it: docs/benchmarks/cpu-detector-speed.md
  sections 7-8 (FP32 GPU boxes = CPU boxes; ~360 MiB; ~10-19 % of the GPU at 10 Hz).
- **What changes:** the vision WORKER (`compose.vision-worker.yaml`; not the `vision` service)
  gets ONE more bind mount, the host's RAM directory `/dev/shm/poring-lab-detect` at `/detect`,
  read-write, so its detect server (`poring_vision.detect_server`) can create
  `/detect/detect.sock`. `guarded_build.py worker:vision` creates that directory first, as the
  host user, mode 0700 (a missing bind source would be created root-owned).
- **Direction and content: frames in, numbers out.**
  - The host bot (`scripts/unit_detector.GpuDetector`) is the ONLY client. It connects; vision
    never initiates anything and still reaches no host, LAN or internet address (row 5).
  - In: the letterboxed game-region frame (uint8 BGR at the model's input size), chosen and cut
    by the host. Out: the model head's raw float32 output.
  - The host decodes it with ITS OWN code, the same as its CPU worker's (letterbox, decode, NMS,
    class names, species collapse: `scripts/detector_worker.py`). Vision runs only the forward
    pass, in FP32, from weights it loads only by the pinned sha256.
- **What vision still cannot do:** reach X (row 1), send input other than through
  `/internal/agent` (rows 2-3), reach the network (row 5), see packet data. The socket carries no
  input and no command: a reply is numbers of one fixed shape.
- **The host side fails closed to the CPU detector** (unit tests in `test_unit_detector.py`):
  - the directory must be the host user's, mode 0700, not a symlink;
  - the socket is opened `O_PATH | O_NOFOLLOW` and must be a socket owned by the host user (a
    symlink planted there is refused, never followed), then connected through `/proc/self/fd`;
  - the hello must name the pinned weights (sha256), the model's input size and the output shape
    (1, 4 + classes, anchors); a reply of any other shape, or with a non-finite value, is a failure;
  - a timeout (250 ms), a refused connection or a bad reply gives the CPU's boxes for that frame
    and the next 5 s; a wrong sha256 or an unsafe socket turns the GPU off for the whole run.
- **Residual risks, accepted:**
  - vision can write files into `/detect`. It is RAM, counted in rule 7's /dev/shm budget, and the
    host reads nothing there but the socket;
  - vision chooses the numbers, so the boxes: the same trust the bot already gives the model.
    Every click still goes through the mux, the UI gate, and the hover verdict (a SWORD cursor)
    before a strike.
- **R1-R3 unchanged:** the detect server runs only as a guarded `execdev:vision` step (R2
  pre-start, the paired R3 pause windows, the IO guard, a verified stop). A paused or stopped worker
  means CPU boxes, never a blind bot.
- **Acceptance:**
  - `test_guards.py` pins the mount: the worker only, this exact host path, never the `vision`
    service or any other container;
  - the acceptance script gains row 6 (`/detect` is tmpfs and holds nothing but `detect.sock`) and
    runs inside the worker after the change, rows 1-5 included.

## Tracking

[lumduan/poring-lab#1](https://github.com/lumduan/poring-lab/issues/1), labelled `blocks-phase-4` and `security`.
