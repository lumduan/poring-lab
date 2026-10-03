---
doc_type: design
hypothesis: null
status: GO
role: null
verdict_date: 2026-10-02
verdict_ticket: null
supersedes: null
related: []
next_action: Step 1 DONE (V3 reliable, beats RDP). Step 2 (the frame bus) BUILT and tested offline 2026-10-03, with step-3/4 wiring (V3b, backend bus source, /health.framebus) committed but NOT deployed. Next, after Batt's approval only, the V3b clean-room run in section 9a (key->paint without the X mirror, + the Samsung display step).
---

# S2: GameStream without Xvfb, one decode, a frame bus for the bot and the human

**Status:** APPROVED by Batt (2026-10-02), together with ADR-0013 and step 0. Step 0 was
attempted on 2026-10-03 and is NOT done (§9, step 0, "Attempt 1"). It changes the architecture: it removes the
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

## 3a. Datasets and calibration come from the deployment path (Batt, 2026-10-03)

- **Training datasets are recorded through the deployment path:** S2 (H.264 → decode → frame
  bus), never RDP frames or X grabs, once S2 is the path the bot plays through. A model trained
  on one codec's artefacts and tested on another's is measuring the domain shift, not the policy.
- **UI templates and calibration are re-done on stream frames.** Evidence from the clean room
  alone: the ENG tray template needed a stream-specific copy (`eng_full_stream.npy`, 6.8 > 6.0 on
  RDP's), the RO window landed 1 px off after tscon, and the picture test had to move to the
  taskbar strip. Anything matched by pixels is calibrated on the frames it will run on.

## 4. Input path (no XTest on this path)

➡️ **BUILT 2026-10-03 (8820b3c), live verification pending; S2 is the bot's primary path
([ADR-0014](adr/0014-s2-primary-bot-path.md)).** As built:
- `s2spike/input_socket.py`, one peer, 0660, on the `s2-input` tmpfs;
- `poring_env/s2input.py` `GameStreamInput`, which waits for the S2 client's ack;
- the Injector's two sinks (console + a live socket → S2, else XTest; ReleaseAll on a switch);
- `poring_env.keymap.VK_BY_CODE`, with vk.py drift-tested;
- the wheel sends `LiSendHighResScrollEvent(±120)` per notch, as the V3b X path did;
- **no X window takes input**: an unmapped presence marker keeps the interlocks (Batt's choice).

The numbered text below is the plan as approved.

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

**Sunshine-side lessons from S1** ([ADR-0009](adr/0009-console-session-capture.md) "S1 PARKED"),
binding for s2-client:
1. Never end by killing the client. `/cancel` the app first: a dead client leaves the session
   running, and the next connect resumes it.
2. Display apply and revert need a console session: stream only on `console/steady`, and `/cancel`
   before the session leaves the console.
3. Sunshine rewrites its log at each start, so the client logs its own view of every session start
   and end.
4. Expect H.264 with 4 slices per frame, no reference-frame invalidation, encrypted RTSP, and audio
   packets even with audio on the host (s2-client drains and discards them).



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

0. **Early validation, before any S2 code (recommended: a temporary second Moonlight pairing from
   Batt's Mac).** No lab code and no build. It answers two questions at once.
   - **Does RO accept Sunshine's SendInput?** Checks:
     - keys (GM `@where`);
     - clicks (a walk, seen as a `self_move` packet in the sniffer);
     - right-drag (camera rotation);
     - Thai Kedmanee (`say`, then the chatlog HEX);
     - the Mouse Keys `Flags` before and after.
   - **Is the VDD stream healthy?** If the Mac's GPU-backed Moonlight renders at once under the same
     Sunshine config (VDD + `ensure_only_display`), S1's black first renderer is lab-side (ADR-0009
     "S1 PARKED").
   - **Cost** (Batt, ~30 min):
     - a Windows Firewall exception for the Mac's IP (admin; Sunshine's rules admit only this host
       today);
     - pairing by PIN in Sunshine's web UI (pc-only);
     - ~~the lab's gamestream stopped through `guarded_build.py` for the duration~~ ➡️ SUPERSEDED
       (2026-10-02, before attempt 1): `capture_backend.py to-console --yes-tscon --external` leaves
       the lock at console/switching (REASON `to-console-external`), so the lab's Moonlight HOLDS
       while the external one streams. No container stop/start; still never two streaming clients;
     - a tscon handover, **and only after it reports done does Batt start Desktop on the Mac**
       (attempt 1 lesson: started on RDP, the stream is black and the app keeps running);
     - Batt tests by hand; I read the chatlog and the sniffer.
   - **Revert, in the same session:**
     - `to-rdp`: the lab's `quit` (/cancel) also ends the EXTERNAL client's app (seen live in
       attempt 1), then the revert check;
     - unpair the Mac (Sunshine lists exactly ONE client again: `poring-lab-gamestream`; web UI,
       Troubleshooting → Unpair Devices → that row's own delete button, NEVER "Unpair All");
     - remove the firewall exception (exact program path, read back);
     - the lab's `moonlight list` still works (its pairing is intact).
   - **This is an explicit, time-boxed exception to CLAUDE.md rule 2** ("Sunshine pairs ONLY the
     lab's gamestream client"). It needs Batt's go, and the revert is checked, not assumed.
   - **Fallback:** step 1's spike also sends input (LiSend*) but needs a build window.
   - **Attempt 1, 2026-10-03 — NOT DONE; reverted, and none of its questions is answered.**
     - Done: the firewall exception (both enabled "Sunshine" rules → `192.168.1.13,192.168.110.55`,
       exact program path, read back); the Mac paired by PIN (state written 10:01:45; 2 clients,
       `sunshine_state.json` still SYSTEM + Administrators only).
     - What happened: Desktop was started on the Mac while the session was still on RDP (lock
       rdp/steady, no tscon). The Mac showed black with a cursor, as expected: Sunshine has no
       console session and logged "Trying to apply display device settings. API is available:
       false" every 5 s. Batt then left the Mac, and the app kept running (the retries continued),
       the same "an unquit client leaves the app running" lesson as S1's TERM.
     - 10:14: the lab's Moonlight `quit` (`capture_backend.QUIT_STREAM`) → `200 <cancel>1</cancel>`
       (rc 124, the CLI lingers). The retries stopped at 10:14:14: **one paired client's /cancel
       ends another client's app**, which is what to-rdp's "external" branch relies on.
     - Revert (Batt: "delete dell 3090 out"): the Mac was unpaired at 10:19:27 (read back after a
       page reload AND in the state file: 1 client, `poring-lab-gamestream`); the firewall was back to
       `192.168.1.13` on both rules at ~10:24 (read back); the lab's `moonlight list` returned rc 0
       (Desktop, Steam Big Picture).
     - NOT tested: SendInput (keys, clicks, right-drag), Thai Kedmanee, Mouse Keys, VDD stream
       health, and to-rdp's clean quit live (the session never left RDP). Mouse Keys (62) and the
       chatlog (max id 6) were not re-read: there was no console session and no in-game input, so
       nothing could have changed them.
     - Re-running it costs the same again (firewall exception + PIN), with Batt at the Mac.
1. **Spike** (throwaway, `/dev/shm`, an operator window for any build):
   - moonlight-common-c `.so` + PyAV;
   - connect with the paired identity under a console handover;
   - decode 30 s into `/dev/shm`;
   - measure decode CPU and `/cancel`→revert time.
   - Answers: does S2 work, what does it cost, and was S1's stall Moonlight's?
   - ➡️ **2026-10-03: built as the clean room's V3** (`services/gamestream/s2spike`, kept as S2's
     first piece, not thrown away; ADR-0009 "Clean room"). Pre-entry results:
     - moonlight-common-c at `8599b60`, the commit moonlight-qt 6.1.0 ships, so V1 and V3 speak
       the same protocol; the ctypes layout is checked against the pinned headers;
     - in the container, `selftest` OK; `serverinfo` PairStatus=1 with the lab certificate;
     - PyAV 19.0.1 decodes synthetic 4-slice 1440x900 H.264 at a p50 of 2.9 ms per frame,
       including the BGRA conversion, on the host.
     - Its first live run is the clean room's V3, if V1 and V2 stay black.
     - ➡️ **2026-10-03 13:38: V3 RAN LIVE and is RELIABLE** (ADR-0009 "Clean room"). Results:
       - first picture 4.7 s; connected in 0.13 s; 0 decode errors;
       - every functional check through the mux (the guarded GM login, keys, a walk, right-drag,
         Thai Kedmanee byte-exact);
       - SPEC v2: delivery 33 fps, packet→frame p50 119 ms, 1.5 lab cores, against RDP v2's
         23 fps, 376 ms and ~4.5 cores;
       - key→paint p50 / p95 138 / 350 ms (RDP 101 / 114): the tail to examine in S2.
       V1/V2 (Moonlight-qt) stayed black: the first SDL_RenderPresent hangs in Mesa llvmpipe GLX on
       Xvfb. **Step 1 is answered: S2 works, it costs less than RDP, and S1's stall was the lab
       client's GL present.**
   - **What is NOT S2 (Batt, 2026-10-03):** `x11_mirror_shim.py` blits V3's frames into the lab
     Xvfb and forwards the X input that reaches its window (mux → XTest → window → LiSend*).
     It is a **spike-only compatibility shim**, in its own module so it can be dropped. It exists
     only so the web console, rdp-loop's interlock and /health see V3 during the experiment.
   - **The final S2 stays as designed above:**
     - decode ONCE into the frame bus (§2);
     - the bot reads numpy frames from memory;
     - humans get JPEG from the same bus through the console's WebSocket (§3);
     - **no Xvfb anywhere in the GameStream path** (Xvfb optional, for noVNC debugging only);
     - input goes **mux → S2 client → Sunshine** (rule 3), once XTest is no longer the path (§4).
   - **V3 uses the lab client's identity** (one pairing). One client at a time is ENFORCED at
     stream start (`capture_backend.py stream` refuses while any lab client runs; the spike
     refuses unless the lock is console/steady, no xfreerdp window exists and no Moonlight-qt
     runs). The key is loaded through a sealed memfd and never written to a file (CLAUDE.md
     rule 2, amended).
2. The **frame bus** in `poring_env` (pure Python, fully tested without hardware).
   - ➡️ **2026-10-03: BUILT, tested offline, committed; not deployed.**
     - `poring_env/framebus.py` (stdlib + numpy; the layout and seqlock of §2; the writer also
       publishes its decode p50/p95 and a heartbeat; a new writer = a new inode, readers re-open);
       `poring_env/bus_source.py` `BusFrameSource` (grab waits for a strictly newer id).
     - A cross-process torture test (2 slots, ~12,000 frames/s, three reader processes): thousands
       of retries and overruns, **0 torn frames**. A slow reader does not slow the writer.
     - Ahead of their steps, also committed and inert until §9a is approved:
       - step 3's writer: s2spike `--framebus` (variant **V3b**, `PAINT=bus`): every decoded frame
         to the bus, the X window input-only and never painted, a 0.5 s heartbeat thread, the ring
         removed at exit; `framebus.py` vendored byte-identical (drift test);
       - step 4: the backend's `capture_select.py` reads the bus only in console mode with a live
         writer (else X11), `CONSOLE_FPS` (15) caps the JPEG view, `/health.framebus` carries the
         writer (fps, decode ms p50/p95, heartbeat) and the consumer counters;
       - ro_agent's screen helper reads the bus in that state too (V3b never paints X), stamped
         with the writer's decode time;
       - compose: the 64 MiB `framebus` tmpfs (gamestream rw, backend + vision ro, guarded),
         gamestream 1536m → 1600m.
     - ~~Still to do in step 3: the input socket (V3b still receives the mux's XTest through its
       input-only window). Step 6: vision's grab on the bus.~~ ➡️ **2026-10-03 evening: both BUILT**
       (§4 above; vision `VISION_FRAME_SOURCE=auto|bus|x11`, `poring_env.remote.make_env
       ("gamestream")`). Live verification in the S2 session (A4 through the socket).
3. **s2-client** in the `gamestream` image (writer + input socket + clean lifecycle). Moonlight-qt
   is removed.
4. **Backend** console mode: bus FrameSource, capped JPEG human view, `/health.framebus`.
5. **`GameStreamInput`** + the VK table; the live A4 functional checks. ➡️ BUILT 2026-10-03;
   A4 live pending.
6. **vision on the bus** (ADR-0005 (a)); the acceptance rows 3 and 4. ➡️ BUILT 2026-10-03 (the
   vision image built and `check_gpu` passed the same evening); rows 3–4 are verified with a live
   loop later. Full ADR-0005 closure is PROPOSED in ADR-0014.
   - Phase 3 note (Batt, 2026-10-03): RagLite's ACT/SPR decoding (Apache-2.0 option) is a later
     path to synthetic training data, i.e. sprites with exact labels (THIRD_PARTY.md).
7. **Benchmark** SPEC v2: S2 vs RDP (and S1 if it renders).
8. **Later**, each separately approved:
   - shared viewing (§10);
   - the status indicator (ADR-0013);
   - human-presence detection and the audit (§11).

## 9a. The next clean-room run: V3b, key→paint without the X mirror (PROPOSED — STOP for approval)

Nothing below has run. It needs Batt's go, then a guarded deploy window.

**Why.** V3's key→paint p95 was 350 ms against RDP's 114 ms. V3 painted each frame into Xvfb
(XPutImage of 5 MB) and the console then grabbed X again, so the mirror's two copies sit inside
that number. V3b removes both: decode → bus → the console's JPEG and the bot's numpy.

**Deploy (guarded, ~1 min, before the entry).**
1. `guarded_build.py recreate:gamestream@60`: mounts the `framebus` volume and the 1600m limit.
   No image build: the dev overlay already binds `s2spike/` and `bin/`.
2. `guarded_build.py recreate:backend@30`: a restart cannot add the new mount. A recreate boots
   HUMAN (the automatic ASSIST restore covers `restart:backend` only, as decided), so Batt sets
   ASSIST again. Read back `/health.framebus` = `active x11, writer null`.

**Run** (the clean-room tooling as before, watchdog boxes V3b 60 min, checks 45, hard cap 3 h):
1. `cleanroom.py preflight` → `start` → `variant V3b`: first picture through the BUS
   (`/health.framebus.active == "bus"`, writer fps ≈ 30, decode p95), steady, one-shot restream.
2. SPEC v2 bench, as V3's: delivery fps, packet→frame and **key→paint p50/p95** (target: under
   V3's 138 / 350 ms, at or near RDP's 101 / 114 ms), lab cores, HP-panel PSNR/SSIM. Same frames
   for the bot and the console: `frame_id` equal in the overlay and the agent log.
3. Functional re-check through the mux (V3b still takes input via XTest on its input-only window):
   GM `@where`, a walk, right-drag, Thai `say` + chatlog HEX.
4. The Samsung display step (below), if Batt approves it as part of this entry.
5. `cleanroom.py end`: to-rdp, Sunshine revert check, exit checks (the ring gone, `/health.framebus`
   back to x11).

**The Samsung display (Batt switched it on; restore it WITHOUT Win+P through RDP).**
- Read-only first (from RDP, in a "poring-lab shell"): `Get-PnpDevice -Class Monitor`,
  `WmiMonitorID`, and the persisted console topology under
  `HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers\Configuration` / `Connectivity`.
  `Screen.AllScreens` in an RDP session shows only the RDP display, so the console's screens are
  read inside the console session at the entry.
- ➡️ **Read 2026-10-03 15:22 (RDP, "poring-lab shell", standard account):**
  - `Get-PnpDevice -Class Monitor`: present/OK = `VDD by MTT` (MTT1337), `Generic Monitor
    (SAMSUNG)` (SAM07C0, UID249395) and a `Generic Monitor` (DEFAULT_MONITOR, UID256: the RDP
    display); not present = the LG ULTRAWIDE, an older SAMSUNG instance and a second default
    monitor. So the Samsung is connected and enumerated: inactive, not missing.
  - `Screen.AllScreens`: only `\\.\DISPLAY577`, primary, 1440×900 (the RDP display, as expected).
  - `WmiMonitorID`: Access denied; `HKLM\...\GraphicsDrivers\Configuration`: registry access not
    allowed. The standard account cannot read the console's topology from RDP: it is read inside
    the console session at the entry (`Screen.AllScreens`), or by Batt from an elevated console.
- Why not Win+P in RDP: it changes the RDP session's projection, not the console's topology, and
  can blank or drop the RDP view. The console topology changes only from the console session.
- Why it is VDD-only now: Sunshine's `dd_configuration_option = ensure_only_display` deactivates
  every other display at each stream start, and its revert at the end restores the topology that
  was active BEFORE the stream. The last revert (verified OK) restored a VDD-only topology, so the
  Samsung stays off until the console's topology itself changes.
- **Proposed method, during the V3b entry:**
  1. Batt, before the entry, in his elevated console: back up
     `C:\Program Files\Sunshine\config\sunshine.conf`, set `dd_configuration_option = disabled`,
     `Restart-Service SunshineService`, read the line back. (The agent never edits Sunshine's
     config: elevated, Batt's.)
  2. Enter and stream V3b. With the option disabled, Sunshine leaves the topology alone: the
     stream captures the VDD as it is (the only active display, primary, 1440×900).
  3. In the console session, through the stream, in a "poring-lab shell": `DisplaySwitch.exe
     /extend`. The VDD stays primary at 0,0 because it is the active display when /extend runs;
     the Samsung joins as a secondary. Verify with
     `Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Screen]::AllScreens`
     (two screens, the VDD primary at 0,0, 1440×900), and that GAME_REGION's signatures still
     match (the RO window does not move).
  4. If the Samsung became PRIMARY (the taskbar or the RO window moved): `cleanroom.py end`, and
     Batt fixes it at the Dell (Win+P there, or Display settings → "Make this my main display" on
     the VDD).
  5. After the exit, Batt restores `ensure_only_display` + restarts Sunshine. From then on each
     stream applies VDD-only and its revert restores VDD + Samsung (the topology active before
     it), which is the behaviour wanted.
- **Effects to check:** GAME_REGION and the 1:1 RO window are defined on the VDD at 0,0, so an
  extended Samsung to the right or left of it changes nothing the lab sees. A stream started while
  `ensure_only_display` is active still deactivates the Samsung for the stream's duration (by
  design); the revert brings it back.

**STOP: none of this runs before Batt approves this section.** ➡️ **APPROVED by Batt 2026-10-03**,
with push-and-wait points: (a) before entry, his elevated console sets
`dd_configuration_option = disabled`; (b) after the backend recreate, he sets ASSIST; (c) after
the exit, he restores `ensure_only_display`. Pushes at entry (with the hard cap) and at exit too.
- **Found while preparing it, and fixed first:** the bench's watchers (packet→frame, key→paint,
  delivery fps) and ro_agent's screenshots grabbed X, which V3b never paints. They now share
  `poring_backend/grabsource.py`, the backend's own rule (console + a live writer → the bus,
  else X). On the bus every new frame is used once, at its decode time, and each result records
  `frame_sources`. `cleanroom.py checks --box-min N` puts the bench and the checks in a watchdog
  box (a variant's box ends when it does).

**➡️ RESULT (2026-10-03 17:07–18:12; ADR-0009 "Clean room 2"):** V3b is RELIABLE on the bus.
SPEC v2 outdoor: key→paint p50/p95 **121 / 277 ms** (V3 138 / 350; RDP 101 / 114), packet→frame
114 / 268 ms, 30 fps, **1.03 lab cores** (V3 1.5, RDP 5.4); every watcher read `frame_sources: bus`.
Removing the mirror cut the key→paint tail by 73 ms; it is still above RDP's (next: Windows-side
capture/encode pacing at 30 fps). The Samsung method did NOT go as written: with
`dd_configuration_option = disabled` the console came up with the Samsung as the MAIN display and
every window out of the stream's sight. Batt then decided the console is **VDD-only** (the Samsung
is not preserved): set by device name in the console, `ensure_only_display` restored after the
exit; layout and emergency path in [operations/console-display.md](operations/console-display.md).
The watchdog also ended the first entry (a stale heartbeat while waiting on Batt); re-entered.

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
