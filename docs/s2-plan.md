---
doc_type: design
hypothesis: null
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: Batt approves (or amends) this plan, ADR-0009's 2026-10-02 S2 amendment and ADR-0013. Nothing here is implemented. Step 1 is a throwaway spike in an operator-chosen build window.
---

# S2: GameStream without Xvfb, one decode, a frame bus for the bot and the human

**Status:** PLAN, awaiting Batt's approval (2026-10-02). It changes the architecture: it removes the
Xvfb hop for GameStream and adds a Windows-side helper (that helper is ADR-0013, built later).

**Sources:**
- Batt's capture-direction note, 2026-10-02.
- [ADR-0009](adr/0009-console-session-capture.md): S1 and its 2026-10-02 amendment.
- [ADR-0005](adr/0005-vision-x-access.md): option (a).
- [ADR-0002](adr/0002-input-mux.md): the mux.
- [ADR-0003](adr/0003-env-abstraction.md): the Env contract.

## 0. Why S2, and why the S1 numbers can't answer the question

**S1 runs Sunshine → Moonlight-qt → Xvfb → X capture.** It was meant to isolate the protocol
against RDP. It can't:

| Path | How a frame reaches the lab's pixels | Cost measured 2026-10-02 |
|---|---|---|
| RDP | FreeRDP decodes progressive, then **X11 bitmap puts** into Xvfb | ~4.5 cores at 30 fps (h264-plan Arm C) |
| S1 | Moonlight decodes H.264, then presents through **OpenGL**, which here is llvmpipe (CPU-emulated GL) | 4.2 cores (cap), 64 rasterizer threads, 50 % of CFS periods throttled |

- An S1-vs-RDP difference therefore mixes **protocol and renderer**.
- S1 also stalls: Moonlight's main thread parks in a futex and never presents (OPEN, ADR-0009
  handover 6).
- **S1's remaining value is functional:**
  - does RO accept Sunshine's SendInput;
  - Thai input;
  - Mouse Keys revert;
  - the display revert after `ensure_only_display`.
- S2 answers all four too, because it uses the same GameStream input channel.

**Batt's principle:** the bot needs pixels in memory, not a window. Drawing frames into a window
only to grab them back is wasted work, and humans watch through the web console anyway.

## 1. Architecture

```
                                              ┌─▶ bot view:   ring slot → numpy → perception
Sunshine ──GameStream──▶ s2-client ──▶ frame bus ─┤   (every frame, lowest latency, read-only map)
 (Windows, console)      decode ONCE     (shm ring)└─▶ human view: backend → JPEG → /ws/stream → console
                         (PyAV/FFmpeg)                 (capped fps, quality knob)
                              ▲
backend mux (all rules) ──────┘ input socket → LiSend*() → GameStream input channel → SendInput
Xvfb: not used for GameStream (it stays for RDP mode and for noVNC debugging only)
```

| Component | Where | What |
|---|---|---|
| **s2-client** | replaces Moonlight-qt in the `gamestream` service (it keeps the pairing key in `gamestream-state`) | [moonlight-common-c](https://github.com/moonlight-stream/moonlight-common-c) (the reference GameStream library: RTSP, ENet control, RTP+FEC video, encryption, input) as a pinned shared library, driven from Python through ctypes. HTTPS launch/cancel in Python with the existing client certificate. **PyAV** decodes the H.264 units once. |
| **frame bus** | a tmpfs volume `framebus`: s2-client **rw** (the only writer), backend and vision **ro** | a seqlock ring of N slots (§2) |
| **backend** | unchanged role | `console` mode: its FrameSource reads the bus, its InputSink writes the input socket. `rdp` mode: X11 as today. The capture-backend lock picks which. |
| **vision** | no X at all on this path | `Env.grab()` reads the bus read-only (ADR-0005 option (a)). Input goes through `/internal/agent` as today. |
| **poring_env** | the library | a new `gamestream` env backend: `BusFrameSource` + `GameStreamInput`. **Policy and agent code are unchanged.** |

**What does not change:**
- The mux and all its rules: lease, source, paste refusal, sensitive batches, audit, and "never
  silent" drops.
- The lock (ADR-0009): `rdp` vs `console`, one session.
- Every message keeps `frame_id` and `t_mono_ns`.

## 2. The frame bus

**Layout.** One file in the `framebus` tmpfs volume (`/framebus/ring`), `mmap`ed.

| Part | Fields |
|---|---|
| Global header | magic, version, `slots`, `slot_bytes`, `latest` (index of the newest committed slot), writer pid, writer heartbeat `t_mono_ns` |
| Per slot | `seq` (odd while being written), `frame_id`, `t_mono_ns` (decode-complete), `t_pts` (stream PTS), `w`, `h`, `stride`, `fmt`, then the pixels |

**Writer** (s2-client only):
1. pick slot `(latest + 1) % N`;
2. `seq += 1` (odd);
3. write the header and pixels;
4. `seq += 1` (even);
5. publish `latest`.

It never waits for a reader.

**Readers** (backend, vision): latest-wins.
1. Read `latest`, then the slot's `seq` (it must be even).
2. Copy the pixels out (~5 MB at 1440×900 BGRA, sub-millisecond), or use a short-lived view.
3. Re-check `seq`. If it changed, it's an **overrun**: retry once, then count it.
4. **Drops per consumer** = gaps in the `frame_id`s it consumed. A slow consumer (the browser path)
   skips frames and never delays the writer or the bot.

**Sizing.** N = 8 slots × 5.2 MB = 42 MB of RAM, charged to the writer container (its
`mem_limit` == `memswap_limit` rises by that, consciously; CLAUDE.md rule 5).

**Format.** BGRA first: it is the existing `Frame` format, so every consumer works unchanged.
- *Later option:* carry I420 on the bus (1.9 MB/frame). The JPEG encoder can take YUV without a
  colour conversion, and only the bot converts.

**Clock and identity:**
- `frame_id` is assigned by the writer: one domain for the bot, the console and the logs (the
  ADR-0005 (a) benefit).
- `t_mono_ns` is the host's CLOCK_MONOTONIC (the containers share the kernel), so the console
  overlay shows exactly the frame the bot saw.

**/health** gains `framebus`:
- writer: fps, decode ms p50/p95, last heartbeat;
- consumers: one entry each (`stream`, `vision`) with frames read, drops and overruns. vision reports
  its counters in its agent heartbeat (a protocol addition, via `scripts/gen_protocol.sh`).

## 3. Quality of service per consumer

| Consumer | Rate | Quality | Note |
|---|---|---|---|
| bot (vision / ro_agent grabs) | every frame | lossless copy of the decoded frame | lowest latency; reads straight from the ring |
| human (web console) | capped: `CONSOLE_FPS`, default 15 | `JPEG_QUALITY` knob (default 80) | encoded by the backend from the newest slot; never holds a slot |
| recorder (`record_session.py`) | every frame | lossless (PNG shards, ADR-0010) | a third reader, same rules |

## 4. Input path (no XTest on this path)

1. The backend's mux decides exactly as today. Then its `InputSink` for `console` mode
   (`GameStreamInput`) writes each event to a **unix socket** in a small tmpfs volume `s2-input`.
   Only backend and gamestream mount it, and only the backend can write: the one-writer rule of
   ADR-0002 holds.
2. s2-client maps the events to moonlight-common-c calls:
   - mouse moves → `LiSendMousePositionEvent(x, y, SESSION_W, SESSION_H)`, absolute, normalised to
     the session;
   - buttons → `LiSendMouseButtonEvent`;
   - wheel → `LiSendScrollEvent`;
   - keys → `LiSendKeyboardEvent(VK, modifiers)`.
3. `KeyboardEvent.code` → Windows VK is a new generated table, like `keycodes.gen.ts` today and
   drift-tested.
4. Thai stays the Windows-side Kedmanee layout, exactly as with RDP; A4 verifies it.

**Refusals stay where they are:**
- the bot may not paste, nor hold Ctrl+Alt+Shift;
- sensitive batches are summarised;
- console mode refuses paste (it already does).

s2-client executes only what arrives on that socket.

## 5. Session lifecycle, and the display-revert lesson

- s2-client streams only on `console/steady`, like gamestream today.
- **On `to-rdp` it ends the stream CLEANLY** while the session is still on the console:
  1. `LiStopConnection`;
  2. the GameStream HTTPS `/cancel` (quit the app);
  3. a bounded wait.
- Only then does the lock move.
- **Why:** 2026-10-02, Moonlight was killed with TERM. Sunshine ended the session late, the session
  had already returned to RDP, and the display revert has been pending ever since ("API is
  available: false" every 5 s).
- The bounded wait is measured during the spike: how long Sunshine takes from `/cancel` to its
  revert.

## 6. Tests

| Area | Test |
|---|---|
| frame bus | a writer and N readers in threads/processes; seqlock torture (a reader never returns a torn frame); latest-wins; drops counted per consumer; a slow reader never slows the writer (timing bound); a corrupt or old-version header is refused |
| s2-client (unit) | decode-unit assembly from a recorded H.264 elementary stream → PyAV → the ring; the input socket → `LiSend*` with a fake library (ctypes stub); a malformed message is refused and counted |
| input mapping | `KeyboardEvent.code` → VK table drift test; absolute coordinates over SESSION_SIZE round-trip (the same contract as `to_pixels`) |
| backend | `console` mode reads the bus; the JPEG cap holds `CONSOLE_FPS`; `/health.framebus` fields; mux rules unchanged (the existing tests run against the new sink) |
| guards (`test_guards.py`) | `framebus` mounted rw only in gamestream, ro in backend/vision, nowhere else; `s2-input` only in backend + gamestream; gamestream no longer mounts the X socket; vision has no X mount on the GameStream path |
| live (A3/A4) | one session; VDD 1440×900; the bot's frame = the console view (the same `frame_id`); keys, clicks, right-drag, Thai Kedmanee → chatlog HEX; Mouse Keys before/after; display revert after `to-rdp` (Sunshine log); the ADR-0005 acceptance rows 3 and 4 |

## 7. Benchmark plan

- **Procedure:** SPEC v2 unchanged (`scripts/bench.py`, the same scenes, same 1280×720 client).
  Tables: fps outdoor, packet→frame p50/p95, key→paint, static UI bit-exact, and lab CPU per
  container.
- **One definition change, stated in the write-up:** "frame" = **the frame available to the bot**.
  - RDP: the X grab after Xvfb is drawn.
  - S2: the ring slot after decode.
  - S1: the X grab (if S1 ever renders). This is the honest comparison point for an agent.
- **Rows:**
  - RDP v2 (the baseline: 23 fps outdoor, p50 376 / p95 521 ms);
  - S2;
  - S1 only if it renders, labelled "protocol + llvmpipe renderer".

**Expected CPU (estimates, to be measured, not promises):**

| Stage | Cores |
|---|---|
| RTP/FEC/decrypt (moonlight-common-c) | ~0.05 |
| H.264 decode, 1440×900@30, FFmpeg software | ~0.3–0.5 |
| colour conversion to BGRA (swscale) | ~0.1–0.2 |
| ring write | < 0.05 |
| human-view JPEG at 15 fps | ~0.1 |
| **total** | **~0.6–0.9**, vs ~4.5 (RDP progressive) and 4.2+ (S1) |

**GPU (NVDEC) decode:** a later optimisation, only if measurements require it (60 fps, several
streams, or decode-to-GPU feeding YOLO). Not now.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Building moonlight-common-c needs a C toolchain layer, which is IO-heavy on this host (three builds aborted on 2026-10-02) | a multi-stage build; the toolchain only in a throwaway stage; an **operator-chosen window**; or compile once in `/dev/shm` and COPY the `.so` (decided in step 1) |
| Reusing Moonlight-qt's pairing identity (its certificate and key inside `Moonlight.conf`) | read it in place inside the gamestream container (the key never leaves that volume, CLAUDE.md rule 2). If that fails: unpair the old client in Sunshine first, then pair the new one. Exactly one paired client, always |
| Python callbacks per decode unit | 30–60 calls/s is trivial for ctypes; PyAV decodes with the GIL released |
| moonlight-common-c API drift | pin a commit SHA; a tiny ctypes surface (connection start/stop, decoder callbacks, five input calls) |
| GPLv3 (moonlight-common-c) | a private lab; fetched at build, never vendored into the repo |
| S1's stall cause is on the Windows/Sunshine side, not Moonlight's | **the spike tells us immediately:** if PyAV decodes the real desktop, Moonlight-qt was the culprit |
| RAM for the ring | 42 MB, a conscious `mem_limit` raise |

## 9. Order of implementation (each step ends in a report; nothing starts before approval)

1. **Spike** (throwaway, `/dev/shm`, an operator window for any build):
   - moonlight-common-c `.so` + PyAV;
   - connect with the paired identity under a console handover;
   - decode 30 s into `/dev/shm`;
   - measure decode CPU and `/cancel`→revert time.
   - Answers: does S2 work, what does it cost, and was S1's stall Moonlight's?
2. The **frame bus** in `poring_env` (pure Python, fully tested without hardware).
3. **s2-client** in the `gamestream` image (writer + input socket + clean lifecycle). Moonlight-qt
   is removed.
4. **Backend** console mode: bus FrameSource, capped JPEG human view, `/health.framebus`.
5. **`GameStreamInput`** + the VK table; the live A4 functional checks.
6. **vision on the bus** (ADR-0005 (a)); the acceptance rows 3 and 4.
7. **Benchmark** SPEC v2: S2 vs RDP (and S1 if it renders).
8. **Later**, each separately approved:
   - shared viewing (§10);
   - the status indicator (ADR-0013);
   - human-presence detection and the audit (§11).

## 10. Shared viewing (future capability; designed now)

Sunshine captures the **console**, which is what the physical monitor shows. Unlike RDP, which
locks the console, a person at the Dell, the bot and the web console can all see the same session
at once. Uses: AI remote support, an AI learning helper for kids.

| Mode | Capture | Use |
|---|---|---|
| **Lab** (current) | VDD only (`ensure_only_display`), fixed 1440×900 | nobody at the machine; a fixed resolution (GAME_REGION, the frozen 1280×720 client) |
| **Shared viewing** | the physical display (or a duplicate to it) | a person uses the machine while the bot or console watches. The resolution follows the real monitor, so it **depends on resolution-agnostic projection** ([phase2-plan.md](phase2-plan.md) Part D) |

- **Watch-only** (the bot sends no input, e.g. a HINT mode) is simple: the mux in HUMAN mode, the
  bot reading the bus.
- **Shared control** needs §11 and ADR-0013.

## 11. Shared control (design now, build later)

### 11a. Status indicator on Windows (bot → human)

A small always-on-top, click-through, transparent corner overlay, like a camera LED:

| Colour | Meaning |
|---|---|
| green | the bot is only observing |
| orange | the bot is acting (clicking/typing): don't touch the mouse |
| blue | a human is in control; the bot is paused |

- It is a Windows-side helper, a departure from "agentless". **Scope and limits: [ADR-0013](adr/0013-windows-status-indicator.md).**
- It appears in captured frames, so it sits **outside GAME_REGION** and its rectangle is
  **masked in perception**: the bot never interprets its own indicator.

### 11b. Human-presence detection (human → bot), agentless and pixels only

The backend knows every input it sent. Anything on screen our inputs did not cause came from a
person.

- **Primary signal: the cursor.**
  - Locate RO's software cursor sprite by template (the anchor-map machinery, ADR-0011).
  - Compare it with the position the mux last commanded.
  - A mismatch beyond a tolerance is foreign input. The tolerance allows for moves still in flight
    and for the measured frame delay (the packet→frame p95 of the active backend).
- **Secondary signals:**
  - characters appearing in a focused input field with no mux keys;
  - a window opening or closing with no command behind it.
- **NOT a signal:** general pixel change. The game animates constantly.
- **On detection:**
  - the mux grants a lease to a new source `human_local`, so the bot pauses and the indicator turns
    blue;
  - it releases after a configurable quiet period.
  - `human_local` is a mux state, not an input path: nothing is injected for it.
- **Expected detection latency ≈** the packet→frame delay plus a debounce. RDP is not the mode
  here: in RDP mode the console is locked, so no local user can exist. For S2 it comes from step 7's
  numbers.
- **Console/GameStream mode only.**
- **Tests on recorded sessions:**
  - commanded-only moves never trigger;
  - injected foreign moves (a cursor displaced in the frames) do;
  - in-flight moves within the delay budget don't.

### 11c. Audit, with privacy built in

- **Log control episodes:** who had control, from when to when, the signal that caused each
  switch, and optionally the inferred cursor path.
- **NEVER log a local user's keystrokes or typed text.** Capturing them would need a Windows-side
  keylogger, which is out of bounds: the same principle as never logging clipboard contents
  (ADR-0004).
