---
doc_type: decision
hypothesis: null
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: S1 PARKED (Batt, 2026-10-02) at 'Windows side works, the Moonlight-qt main loop stalls'. No gdb. S2 (docs/s2-plan.md) is the path; its step 0 (a temporary Mac Moonlight pairing) also tells whether the stall is lab-side. to-rdp now ends the stream cleanly (Moonlight quit -> Sunshine /cancel) and checks Sunshine's revert. S2 step 0 attempt 1 (2026-10-03) was reverted unanswered: the Mac app was started before the handover. The lab client's quit (/cancel) ended the Mac's app, so /cancel is host-wide.
---

# ADR-0009: Console-session capture as a second display mode (Sunshine first, VNC fallback)

- **Status:** PROPOSED (2026-10-01). ➡️ **2026-10-02: Batt approved the Sunshine install and the S1
  trial** ("Sunshine research gets the weight"); RDP stays the default until he decides otherwise.
  - Sunshine v2026.914.233613 is installed on the Dell by Batt (UAC). ➡️ Note 2026-10-02: the running
    binary logs "Sunshine version: 2025.924.154138 commit: 86188d47". That tag-vs-version mismatch
    is unexplained; check the MSI's properties before quoting a version.
    ➡️ **RESOLVED the same evening (read-only): the signature-checked v2026.914 MSI NEVER RAN.**
    - The running Sunshine is the **April EXE install**.
    - `C:\Program Files\Sunshine` and its `uninstall.exe` were created 2026-04-04 23:09, and the
      uninstall key is a plain `Sunshine` (an EXE installer), not an MSI `{GUID}`.
    - `sunshine.exe` is 2025.924.154138, built 2025-09-24, Authenticode **NotSigned**.
    - The Application log covers 2025-12-31 onward and holds 212 MsiInstaller events since 09-28,
      but **none mention Sunshine**.
    - So the binary in use is unverified and unsigned. Replacing it with the verified MSI is Batt's
      decision: uninstall the EXE first and keep `config\` (conf, apps, state = the pairing).
    ➡️ **REPLACED 2026-10-02 21:41–22:15** ([sunshine-msi-replace.md](../operations/sunshine-msi-replace.md)):
    - MSI `{F4B3C08C-…}` 2026.914.233613 is now installed.
    - The installed `sunshine.exe` and `sunshinesvc.exe` are byte-identical to the payload of the
      signed, digest-verified MSI (LizardByte does not sign the exes).
    - Config, pairing and server identity were restored hash-identical.
    - The firewall admits 192.168.1.13 only; `sunshine_state.json` is admin-only.
    - The pending Samsung revert was dropped; see the runbook's recovery section. The MSI was checked first:
    SHA-256 = GitHub's digest, Authenticode Valid, signer CN=David Lane = LizardByte's maintainer.
  - Revisions below (2026-10-02): the S1 client is **moonlight-qt**, not moonlight-embedded; the
    **capture-backend lock** replaces the proposed `RDP_MODE` override.
- **Deciders:** Batt.
- **Plan and evidence:** [console-capture-plan.md](../console-capture-plan.md). Every fact there
  carries its source URL, or is marked UNVERIFIED.
- **Related:**
  - [ADR-0001](0001-single-rdp-session.md): one RDP session. This ADR would **amend** it.
  - [ADR-0002](0002-input-mux.md): input mux, unchanged.
  - [ADR-0003](0003-env-abstraction.md): Env contract, gains a transport.
  - [ADR-0004](0004-human-only-clipboard-and-file-transfer.md): clipboard and files, RDP-mode only.
  - [ADR-0005](0005-vision-x-access.md): S2 helps close it.
  - [ADR-0006](0006-sanctioned-test-environments.md): unchanged; the interlock is still required.

## Context

- **The RDP leg caps what reaches the lab.** It delivers 6–12 fps of the 784×625 game for ~6.5
  desktop cores of FreeRDP software decode, whatever the codec ([h264-plan.md](../h264-plan.md)).
  Arm C tests FreeRDP 3.32.1.
- **The game itself renders at 60 fps** on the PC's Intel UHD 630 (i5-10500T).
- **The Windows console session** can be captured on the GPU with Desktop Duplication and encoded
  with Quick Sync. The lab would then decode one hardware-encoded H.264 stream instead of RDP's
  surface commands.
- **Batt's order (2026-10-01):** Arm C first, then VNC if needed. Sunshine is built regardless,
  after Arm C.

Three facts shape the decision:

1. **Windows 11 Pro has one interactive session.**
   - RDP owns it today.
   - A console capture tool sees only the session attached to the physical console. Sunshine's
     service starts in `WTSGetActiveConsoleSessionId()` [S].
   - The session must therefore be **moved** to the console (`tscon <id> /dest:console`), not
     duplicated.
2. **Sunshine or VNC is a new path into Windows that accepts any authenticated client.**
   - CLAUDE.md hard rule 2 forbids "a second RDP or VNC path into Windows".
   - Hard rule 3 requires every input to pass the mux.
3. **Without RDP, ADR-0004's cliprdr paste and `\\tsclient` files do not exist.**
   - Sunshine has neither: no clipboard sync and no file transfer in its docs.
   - Apollo and the VNC servers have bidirectional clipboards.

## Decision (proposed)

1. **Two display modes, never at once: RDP mode (today's default) and console mode.**
   - There is still exactly **one Windows session**: the same session ID, moved between RDP and the
     console.
   - ➡️ **Implemented (2026-10-02) as the capture-backend lock**, not an `RDP_MODE` override:
     `state/capture-backend` (`BACKEND=rdp|console`), mounted read-only in desktop, backend and
     gamestream; its only writer is `scripts/capture_backend.py`, and `/health` reports it.
     rdp-loop connects only under `rdp`, gamestream streams only under `console`, and each refuses
     while the other's window is on the display. The handover writes the lock first; only then
     does tscon run (`to-console --yes-tscon`).
   - Leaving console mode clears the hold, and RDP takes the session back.
   - Each switch is explicit and logged.
2. **Sunshine is the console-mode server; VNC is the fallback.**
   - Sunshine: the upstream LizardByte build, service install, `capture=ddx`, `encoder=quicksync`,
     H.264 only, gamepad off, `origin_web_ui_allowed=pc`, stream encryption on the LAN.
   - The fallback: TightVNC 2.8.88 or UltraVNC 1.8.3.0, with the clipboard and file transfer off.
     TigerVNC winvnc is unmaintained and excluded.
   - Apollo is rejected: it diverges from upstream and syncs the clipboard.
3. **One client, through the mux.**
   - Sunshine is paired with **exactly one client: the lab's**. Pairing any other Moonlight is
     forbidden, because it would be an input writer outside the mux.
   - The firewall admits only 192.168.1.13.
   - The agent never holds the Sunshine web-UI credentials; pairing PINs are Batt's.
     ➡️ **Amended 2026-10-02 (Batt, in conversation):** the agent may perform the pairing itself:
     the PIN entry and Send in Batt's logged-in web UI, for the lab's own gamestream client only.
     The web-UI credentials stay Batt's.
4. **The lab-side client comes in two stages:**
   - **S1:** ➡️ **moonlight-qt** (6.1.0, the official AppImage) rendering into Xvfb `:99`, in the
     `gamestream` service. Nothing downstream changes. Why not moonlight-embedded: its X11 mouse is
     relative-only and warps the pointer to a fixed point on every move (`src/input/x11.c`), while
     moonlight-qt takes X events through SDL and has `--absolute-mouse`
     (`LiSendMousePositionEvent`), so the mux's XTest positions arrive as positions. The live proof
     is the A4 input check.
   - **S2:** our own `poring_env` transport on moonlight-common-c (ctypes) and PyAV.
     - Frames come from a `FrameSource` stamped on the host `CLOCK_MONOTONIC`.
     - Input goes through an `XInput`-compatible sink behind the unchanged `Injector`/`InputMux`.
     - The backend then owns the frames, and vision reads them from it (ADR-0005 option a).
5. **ADR-0004 in console mode:**
   - no clipboard channel exists;
   - ⌘V becomes **typed paste** (`LiSendUtf8TextEvent` in S2), with the same guarantees:
     human-only, never in `AgentToBackend`, digest-only audit, refused for BOT;
   - nothing reaches the Windows clipboard, so there is nothing to scrub;
   - file transfer stays an RDP-mode activity (hybrid).
6. **Amend CLAUDE.md hard rule 2 and ADR-0001 when this is accepted.** Proposed text: *"One Windows
   session and one display path at a time: the RDP session, or the console-mode server of ADR-0009
   with the RDP loop held. Never both, never a second client."*

## Gate: what ACCEPTED requires

➡️ **Reworded 2026-10-02:** "2× the best RDP arm" can no longer hold -- FreeRDP 3.32.1 already
delivers the game's full 30 fps outdoors (h264-plan.md, Arm C). The comparison is now the fixed
benchmark (docs/benchmarks/SPEC.md v1) against the RDP v1 baseline:
- delivery at the 30 fps cap, outdoor and indoor (no worse than RDP);
- packet → frame p75 and key → paint p75 ≤ RDP's, or a lab-side CPU saving worth a small loss;
- fidelity of the UI crops vs the lossless reference: no worse than RDP's;
- the RO client accepts Sunshine's SendInput keyboard and mouse. This is **UNVERIFIED**, and is the
  first thing tested;
- the console switch works with **no** second session ever appearing (`qwinsta` before and after).

If S1 fails on input but passes on video, S2 is the next step. If video fails, VNC V1 is.

## Consequences

**Positive**
- Hardware encode at the source, and one H.264 decode in the lab.
- No RemoteFX "insufficient client resources" skips.
- S2 also gives vision frames without X access.

**Negative / risks**
- **A new authenticated network service on the PC.** The firewall, single pairing and web-UI
  exposure must be audited after every Sunshine update.
- **Sunshine runs as SYSTEM** and can capture the secure desktop. The lab could see UAC prompts.
  Typed passwords stay masked, and "the agent never approves UAC" stays policy.
- **Console mode leaves the screen unlocked** on the PC. Physical access to the Dell is not a lab
  threat today; Batt's call.
- **Paste and files are weaker in console mode** (typed paste only, no file transfer).
- **Smart App Control is ON** on the PC. Unsigned installers (possibly the VNC servers) are blocked,
  and switching SAC off is irreversible, so it is not planned for.
- The Phase 0 baselines are RDP-path numbers. Console mode needs its own.

## Alternatives considered

| Alternative | Why not (now) |
|---|---|
| Stay on RDP (Arm C, then the GDI path) | Still running. This ADR only proceeds if Batt wants it regardless (he does) or Arm C falls short |
| VNC first | Weaker auth (8-character DES) and CPU encode on the PC; kept as the fallback |
| Apollo (Sunshine fork) | Bidirectional clipboard sync (ADR-0004); divergence from upstream |
| Parsec and other cloud-brokered tools | Account and cloud dependency; not open source |
| Hyper-V VM | A separate, queued track (Batt, 2026-10-01) |

## Pairing, as it actually went (2026-10-02)

Six attempts to one pairing. Every step below is a trap the next pairing would hit again:

1. **The login on the PC predated this install.** `sunshine_state.json` dated from an earlier Sunshine
   (2026-04-04) and held an unknown login plus **one paired device**. Batt chose the reset: stop the
   service, set the file aside (`sunshine_state.json.bak-20261002`), start it again. The first-run
   page then created a new login in the browser, with no secret on any command line. That also
   removed April's device.
2. **The client asks first.** Sunshine only accepts a PIN for a pending `getservercert`, so a Send
   with no request waiting fails.
3. **Moonlight's identity must persist.** The `gamestream-state` volume (`/home/desk/.config`) was
   root-owned, so Moonlight minted a new identity on every run. That had two effects:
   - a stale pending session (Sunshine keys it by Moonlight's fixed uniqueid `0123456789ABCDEF` and
     keeps its first client certificate) failed the next attempt at **stage 4**;
   - a pairing could never have stuck, because the next stream would arrive as a stranger.

   The fix: the image creates the directory owned by `desk` (`test_guards.py`), and the existing
   volume was chowned. If a stage-4 failure ever recurs, restart `SunshineService` before retrying.
4. **`paired()` checked the wrong field.** It grepped Moonlight's own identity `certificate`; now it
   requires a stored server certificate (`[hosts] N\srvcert`, `test_capture_backend.py`).
5. **Edge's autofill dropdown covers Send.** The agent dismisses it with Escape and re-verifies the
   page before clicking.
6. **Moonlight's pair CLI never exits after a success.** It waits on its dialog until the timeout
   (rc 124), so success is read from the saved pairing, not from the exit code.

**Result:** Sunshine lists **exactly one** device, `poring-lab-gamestream`. Moonlight's config holds
the host's certificate.

## S1 handover 1 (2026-10-02 15:24–15:26): stopped, back to RDP

**Worked:**
- The lock and both interlocks: gamestream held while an xfreerdp window existed, then streamed;
  rdp-loop held.
- Sunshine: `Desktop` launched, encryption on, **`h264_qsv`** encoding at 29.97 fps capture and
  ~15 Mbps (Quick Sync works on driver 27.20.100.9664).
- Moonlight: 1440x900x30 negotiated; first video packet after 300 ms; 21.4 fps decoded (a static
  lock screen), 0 % dropped, 0.53 ms queue.
- `to-rdp` restored exactly one xfreerdp in 16 s; the RO client kept running.

**Stopped on (an unexpected Windows state):**
1. **tscon failed:** `Error [1326]: The user name or password is incorrect`. It was typed into
   Batt's elevated console (user badso), but session 2 belongs to `poring-lab`, and connecting
   another user's session needs that user's password. The session was left disconnected, and the
   stream showed the lock screen. **tscon must run in the session owner's console** (poring-lab,
   no password). The `--admin-console` route that sent it to Batt's console was removed.
2. **The console is 1920x1080.** Sunshine scaled it into the 1440x900 stream, letterboxed, so
   GAME_REGION would not match. It could not change the mode: "Trying to apply display device
   settings. API is available: false", repeated every 5 s after the stream while RDP owned the
   session. Possibly the API needs a user session on the console (untested). Otherwise Batt sets
   1440x900 on the console, or a VDD or dummy plug provides it.
3. **The Moonlight window was 80 % of the screen** (1152x720 at 144,90) with `--display-mode
   windowed` and no window manager. It is now `borderless` (code; needs a guarded gamestream
   rebuild). ➡️ **SUPERSEDED the same day:** borderless needs a WM, and a WM's resize left the
   stream black. Replaced by the 1920x1200 canvas (see "Handovers 2–5" below).
4. **`to-console` called the stream up on the "Starting…" window**, before tscon had even run. It
   now waits for Moonlight's "Received first video packet".
5. **Sunshine logged "A mouse was not detected. Sunshine will enable Mouse Keys while streaming".**
   That is a Windows accessibility change, to check after each console session.

## S1 handovers 2–5 (2026-10-02 16:50–18:10): Windows side solved, lab-side geometry fixed by a canvas

**Windows side, solved in this order:**
1. **VDD.**
   - The driver: "VDD by MTT" 25.7.23 (a beta). SignPath-signed UMDF driver, hardware id `MttVDD`.
     The signature was checked before Batt installed it with devcon (exit 1 = "reboot suggested";
     the device was OK without one).
   - Modes: 1440x900, 1280x800, 1600x900 and 1920x1080 at 60 Hz, set in
     `C:\VirtualDisplayDriver\vdd_settings.xml`.
   - Sunshine:
     - `output_name` = the VDD's device id `{9acddf6d-43cc-576e-9aff-0c5fc80b4cc8}` (`\\.\DISPLAY4`;
       the Samsung is `{2583f328-…}`, `\\.\DISPLAY1`);
     - `dd_configuration_option = ensure_only_display`: only the VDD during a stream, reverted after;
     - `dd_resolution_option = auto`: the client asks for the size.
   - Backups: `sunshine.conf.bak-20261002*` next to the config.
2. **A stream started before tscon captured an empty display.** Sunshine's display API reports
   "API is available: false" until a user session is on the console.
   - Now: `to-console` writes `console/steady` only after tscon, and gamestream streams only on
     `console/steady`.
   - `to-rdp` stops Moonlight first, then waits 8 s, so Sunshine reverts its display settings while
     the session is still on the console.
3. **tscon from poring-lab's own console: Error 5 (Access denied).** A standard user may not move
   its own session to the console.
   - Batt created a one-time SYSTEM scheduled task, `\PoringLab\PoringLab-ToConsole`. It runs
     `C:\Program Files\PoringLab\to-console.ps1` (an admin-only folder), which finds poring-lab's
     session and runs `tscon <id> /dest:console`.
   - poring-lab may only read and run the task (0x1200a9). It logs to
     `C:\ProgramData\PoringLab\to-console.log`.
   - `to-console` types the run with a 10 s delay, so the line completes before RDP drops.
   - Verified: tscon exit 0, and the console desktop was visible through the stream at 17:52.

**Lab side: the Moonlight window.**
- **What it does:** without a window manager, `--display-mode windowed` opens at the stream's own
  size only if that is under 80 % of the screen in both directions (`Session::getWindowDimensions`).
  On the 1440x900 Xvfb it opened 1152x720, centred.
- **What it drops:** while it builds its renderer, Moonlight drops window events ("Dropping window
  event during flush: 6 (1440 900)"). After a dropped resize the window stayed black. This happened
  with every resize during start-up:
  - an immediate one;
  - after an 8 s settle;
  - after the first packet + 3 s;
  - by a kiosk WM (matchbox).
- **The one success:** a two-step resize by hand, well after the flush, rendered once. Too fragile
  to build on.

**Decision (Batt, 2026-10-02 ~18:12): a bigger canvas.**
- `XVFB_RESOLUTION=1920x1200x24` is the canvas. `SESSION_SIZE=1440x900` is the Windows session,
  drawn 1:1 at the canvas' top-left, in both modes.
- **rdp-loop:** `/size:1440x900 /window-position:0x0` instead of `/f`.
- **gamestream:**
  - windowed at the stream's size, which is under 80 % of 1920x1200, so it opens natively at
    1440x900, centred at 240,150;
  - `place_stream` (xdotool) **moves** it to 0,0 and never resizes it;
  - no window manager in either mode.
- **Everyone else:**
  - the backend's stream and capture, vision, `ro_agent` and `latency_probe` crop to the session
    and normalise input over it;
  - so GAME_REGION (80,77,1280,720), every signature and the console view are unchanged;
  - `/health` shows `session_size`.
- **Guards** (`test_guards.py`, `test_capture_lock.py`):
  - every display consumer gets the same `SESSION_SIZE`;
  - the canvas satisfies the 80 % rule;
  - the placer only moves.
- **Deployed 18:30–18:34:** a guarded gamestream build, then recreates of desktop, backend and
  gamestream. quant-postgres io_full stayed ≈4 % for the 5 min before and after each; the guard
  never aborted.
- **Verified in RDP mode:**
  - Xvfb is 1920x1200;
  - the FreeRDP window is `1440x900+0+0`;
  - the agent's shots are the 1440x900 session.

## S1 handover 6 (2026-10-02 18:44–18:55): the canvas works; the stream stays black (OPEN)

**Worked:**
- The SYSTEM-task tscon, again.
- Sunshine on the VDD (`ensure_only_display`), re-set from Batt's elevated console with a backup
  (`sunshine.conf.bak-20261002-canvas`).
- First video packet after 300 ms.
- Moonlight opened its window at **native 1440x900** (+240,+150) on the 1920x1200 canvas, so the
  80 % rule no longer applies.
- `to-rdp` restored exactly one xfreerdp; the RO client and the GM (online=1) survived.
- Mouse Keys `Flags` = 62 (off) before and after.

**Found and fixed:**
1. **The placer never matched:** the stream window is titled "<host> - Moonlight", class
   `com.moonlight_stream.Moonlight`. It now searches by class. A hand move to 0,0 was accepted.
2. **Keys vanished after `to-rdp`:** SDL focuses its window with RevertToNone, so when Moonlight
   closed, the X focus was None. `/f` used to re-take the focus; windowed `/size` expects a WM.
   - rdp-loop resets the focus to PointerRoot before every connect (live);
   - gamestream does the same after every stream (in the image at the next build).
3. **llvmpipe started 64 rasterizer threads** (one per vCPU) inside `cpus: 4`, and 50 % of periods
   were throttled. `LP_NUM_THREADS=2` removed the throttling.

**Not fixed (OPEN): nothing is presented.**
- 8.9 Mbit/s of video arrives and FFmpeg decodes it, but XDamage stays frozen and every pixel of the
  canvas is 0.
- Moonlight's main thread is parked in `futex_wait_queue`, with no CPU time, and processes no
  window events.
- These made no difference:
  - LP_NUM_THREADS=2;
  - `SDL_RENDER_DRIVER=software` (no GL at all);
  - `SDL_AUDIODRIVER=dummy` (the container has no ALSA device, so SDL had fallen back to its `disk`
    driver on a read-only rootfs).
- Handover 1 (no VDD, tscon failed, lock screen) DID render. The differences since then are the
  console session being live and the display change.
- The next step needs stacks. `GAMESTREAM_GDB_AFTER_S=N` runs Moonlight under gdb (with
  ptrace_scope 1 only a parent may trace) and dumps every thread's stack.
- gdb is not in the image: three guarded builds (19:06, 19:07, 19:09) each spiked quant IO 30–49 %
  and were aborted. It needs an operator window.

**How S1 results must be read (Batt, 2026-10-02):** RDP vs S1 does NOT isolate the protocol.
- FreeRDP draws bitmaps into Xvfb through X11 (cheap).
- Moonlight presents through OpenGL, which in this GPU-less container is llvmpipe (CPU-emulated).
- So any S1-vs-RDP difference mixes protocol AND renderer. A fairer S1 number would force a software
  2D path (`SDL_RENDER_DRIVER=software`, verified to be honoured: "SDL renderer backend: software")
  and label both results.
- S1's value is functional:
  - does RO accept Sunshine's SendInput;
  - Thai input;
  - Mouse Keys revert;
  - display revert after `ensure_only_display`.
- Performance conclusions come from S2 (in-process decode, no Xvfb hop), planned after this report.

## Amendment (Batt, 2026-10-02): S1 interpretation, the S2 architecture, shared viewing and control

**Status of this amendment: APPROVED** (Batt, 2026-10-02: "the S2 plan + ADR-0013, including step
0"; this amendment is that plan's ADR record). The plan is [docs/s2-plan.md](../s2-plan.md). Step 0
was attempted on 2026-10-03 and is not done; nothing of S2 itself is implemented yet.

**1. S1 interpretation (correction).** "RDP vs S1 isolates the protocol" is withdrawn.
- FreeRDP draws bitmaps into Xvfb through X11.
- Moonlight presents through OpenGL, which in a GPU-less Xvfb container is llvmpipe (CPU-emulated).
  That presentation cost, not the GameStream protocol, filled 4 cores (handover 6).
- Every S1-vs-RDP number is therefore labelled **"protocol + renderer"**. A fairer S1 number forces
  SDL's software 2D renderer (`SDL_RENDER_DRIVER=software`; verified honoured on 2026-10-02:
  "SDL renderer backend: software") and is labelled separately.
- **S1's value is functional:**
  - SendInput acceptance by RO;
  - Thai input;
  - the Mouse Keys revert;
  - the display revert after `ensure_only_display`.
- Performance conclusions come from S2.

**2. S2: a "bot view" separate from the "human view", with no Xvfb hop**
(s2-plan.md §1–§7, §9).
- **The client:**
  - a GameStream client in the `gamestream` service (moonlight-common-c through ctypes);
  - **decodes once** with PyAV;
  - writes a shared-memory **frame bus** with per-consumer latest-wins reads.
- **The consumers:**
  - the bot reads every frame;
  - the human view (JPEG to the console) is capped and never delays the bot;
  - both views carry the same `frame_id` / `t_mono_ns`.
- **Input:** the mux (every rule intact) sends to s2-client's GameStream input channel through a
  socket only the backend writes. It is implemented as a `poring_env` `gamestream` backend, so the
  policy code doesn't change.
- **Lifecycle:** the stream ends cleanly (`/cancel`) before the lock returns to `rdp`, so Sunshine
  reverts its display settings while the console session still exists (the pending revert of
  2026-10-02).
- **What does not change:** Xvfb stays for RDP mode and noVNC only. The capture-backend lock keeps
  choosing the one session.
- **Later, only if measurements need it:** NVDEC.

**3. Shared viewing (future capability).**
- Sunshine captures the console, which is what the physical monitor shows. A person at the Dell, the
  bot and the web console can watch the same session at once, which RDP can't (it locks the
  console).
- Modes:
  - **Lab**: VDD only, fixed 1440×900;
  - **Shared viewing**: the physical display; the resolution follows the monitor, so it depends on
    Part D's resolution-agnostic projection.
- Watch-only (a HINT mode, no bot input) is simple. Shared control needs item 4.

**4. Shared control (future capability; design only).**
- (a) A **display-only Windows status indicator** (green/orange/blue): [ADR-0013](0013-windows-status-indicator.md).
- (b) **Agentless human-presence detection** from pixels:
  - the main signal: the RO cursor sprite against the mux's last commanded position, with a
    tolerance for in-flight moves and the measured frame delay;
  - on detection: a `human_local` lease, so the bot pauses.
- (c) **An audit of control episodes, never of keystrokes.**
- Console/GameStream mode only.

## S1 PARKED (Batt, 2026-10-02): lessons, and the display investigation

**Decision.** S1 is parked at **"the Windows side works, the Moonlight-qt main loop stalls"**.
- No gdb build. S2 is the path.
- S1's functional questions (SendInput, Thai, Mouse Keys, display revert) move to S2's step 0.

**Display investigation (logs only).**
- **Hypothesis (Batt):** a display or resolution change at stream start (the VDD-only topology,
  a mode change, or the session moving display) triggers a stream reconfiguration that
  Moonlight-qt deadlocks on.
- **Verdict: INCONCLUSIVE.** It is refuted for a reconfiguration that *Moonlight saw*, and
  unresolvable on Sunshine's side.

| Evidence | Source | Says |
|---|---|---|
| The 18:52 run (handover 6, complete log): `Video stream is 1440x900x30 (format 0x1)`, **one** `Reinit context to 1440x912`, no further reinit or resolution change, then silence until TERM | gamestream container log | Moonlight saw no mid-stream reconfiguration before the stall |
| The same run: "Global video stats" **empty** at quit; "Quit event received" processed on TERM | same | decode units stopped reaching the decoder almost at once; the main loop was waiting (back-pressure from a renderer that never ran), not dead |
| Handover 1 (15:24): `/launch`, Samsung 1920x1080 with "API is available: false" (**no** topology change, the session not on the console), window 1152x720 scaled: **rendered 21.4 fps** | transcript | the only run that rendered |
| Every later Moonlight connect: `/resume`, `<resume>1</resume>` ×9 | transcript | each TERM left the app running on Sunshine, and the next connect resumed it |
| 18:44 (after the 18:42 Sunshine restart, so a fresh launch): VDD + `ensure_only_display`: **black** | ADR-0009 handover 6 | launch vs resume alone does not explain it |
| 17:52 (after the 17:45 Sunshine start, so a fresh launch, VDD + `ensure_only_display`): black, then **rendered after a post-flush resize** recreated the renderer | ADR-0009 handovers 2–5 | the stream content was fine under the topology change. The first renderer (created during the flush) produced nothing |
| Sunshine's own log for 15:24–18:54 | `sunshine.log` | **gone**: Sunshine rewrites its log at each start (it now begins at 18:54:53). All of the day's Sunshine reads were screenshots |

**Reading.**
- The stream itself was decodable under the VDD topology change (17:52).
- What fails is Moonlight-qt's first renderer on this Xvfb with no WM, after a topology change at
  stream start, and nothing recovers it. Handover 1, with no topology change, rendered first time.
- So a display change at stream start *correlates* with the black first renderer. The stall is
  lab-side (Moonlight-qt / SDL on Xvfb), not a broken stream.
- The cheap decisive test is S2's step 0: the same Sunshine config streamed to a real Moonlight on
  Batt's Mac. If the Mac renders at once, the lab-side reading holds.
  ➡️ **2026-10-03: attempt 1 did NOT answer it.** The Mac app was started while the session was still
  on RDP, so it showed black for the known reason (lesson 2), not as evidence about the stall. It
  was reverted ([s2-plan.md](../s2-plan.md) §9, step 0, "Attempt 1"). The question stays open.

**Sunshine-side lessons (S2 consumes the same stream).**
1. **A TERM-killed client leaves the app session running.** The next connect is a `/resume` of a
   stale session, possibly launched under another display topology.
   - Always end with Moonlight's `quit` (Sunshine `/cancel`).
   - to-rdp now does this; S2 will call `/cancel` itself.
   - **`/cancel` is host-wide, not per-client** (seen live 2026-10-03, S2 step 0 attempt 1). The
     lab client's `quit` ended the app session the Mac had started (`<cancel>1</cancel>`, and
     Sunshine's apply retries stopped at once). A client that just disconnects (the Mac, like
     a TERM-killed one) leaves the app running.
2. **Display apply and revert need a session on the console** ("API is available: false"
   otherwise).
   - Apply happens at stream start, so the stream starts only on `console/steady`.
   - Revert happens at session end, so the session must end **before** the session leaves the
     console.
   - A missed revert retries every 5 s until the next console session, and meanwhile the Samsung
     stays dark (left so on purpose by Batt, 2026-10-02). ➡️ SUPERSEDED 22:15 the same day: the new
     Sunshine dropped the pending revert at its first start, so a console session will NOT restore
     the Samsung. Batt will use Win+P at the Dell (the runbook's "Samsung display recovery").
   - An app started while the session is NOT on the console (2026-10-03, the Mac) streams black and
     retries the apply every 5 s until it is cancelled.
3. **Sunshine rewrites `sunshine.log` at every start**, including the helper restart when the session
   moves (18:54:53). Evidence must be copied out during the handover.
4. **Stream facts:**
   - H.264 (format 0x1), 1440x900x30, coded 1440x912;
   - "Reference frame invalidation is not supported by this host";
   - the encoder is configured for 4 slices per frame;
   - `rtspenc` (encrypted RTSP);
   - audio streams even with `--audio-on-host`.

**to-rdp (code, 2026-10-02).**
1. Lock to console/switching.
2. Moonlight `quit` on a private Xvfb `:51` in gamestream (the paired identity stays in its
   volume).
3. The streaming client's log must show the session end; TERM only as a reported fallback.
4. 15 s while still on the console.
5. RDP back.
6. A read-only check of Sunshine's log, typed in poring-lab's console. It answers with a coloured
   block, read from pixels: rc 3 plus the remedy if the revert is still pending.

It runs at the next handover; it is not yet exercised live.



## Clean room (Batt, 2026-10-03): one console move, the lab client varies

**Why.** S1's black stream mixed two suspects: the Windows side (the handover, VDD, Sunshine) and
the lab side (Moonlight-qt + SDL on Xvfb). Every RDP↔console switch between attempts also changed
the Windows side. So the session moves to the console **once**, RDP holds for the whole experiment,
and only the lab client varies:
- **V1:** Moonlight-qt as-is (the image only adds the placer/focus fixes);
- **V2:** Moonlight-qt + openbox (the stall correlated with "Xvfb with no WM");
- **V3:** the S2 spike (`services/gamestream/s2spike`: moonlight-common-c + PyAV, no Moonlight-qt,
  no SDL, no GL).

The Mac is only the fallback.

**Mechanics** (all through `capture_backend.py`, the only lock writer):
- `to-console --cleanroom` (REASON `cleanroom`, console/switching);
- `stream --variant` (refuses while any lab client runs) writes the whitelisted
  `state/gamestream-variant`, then console/steady;
- `hold` (/cancel, the session stays) between variants. Each variant gets a fresh launch, so the
  topology cycles: ro_agent re-checks the client before any input;
- `to-rdp` at the end. It now refuses to let RDP connect while a WM runs or a stale
  `_NET_SUPPORTING_WM_CHECK` is set;
- under a cleanroom REASON a stream is **one-shot** (a crashing client never loops `/launch`).

`scripts/cleanroom.py` runs the variants with time boxes (V1 20 min, V2 30, V3 60, checks 45;
first picture within 90 s; reliable = 60 s steady and a second launch). A detached watchdog
(`systemd-run --user`) runs the clean to-rdp on a box (+5 min), a stale heartbeat or the 3 h hard
cap. It defers to a human except at the hard cap, and never loops.

**V2 vs the 2026-10-02 matchbox lesson.** The kiosk WM was removed because it RESIZED Moonlight's
window during renderer set-up. openbox here:
- has no decorations, no maximize and no resize;
- has no key or mouse bindings (it can't eat the bot's Alt+F4 or clicks);
- keeps its config in /tmp (never `~/.config`, the pairing volume);
- runs only around its own stream, opt-in through the variant file only.

**V3's X window is a spike-only shim** (`x11_mirror_shim.py`), not S2. It exists so the console,
rdp-loop's interlock and /health see V3, and it forwards the mux's XTest input to LiSend*
(rule 3 intact). Final S2 (docs/s2-plan.md):
- frame bus;
- numpy for the bot;
- JPEG from the bus for humans;
- no Xvfb in the GameStream path;
- input mux → S2 client → Sunshine.

**Identity.** V3 is the same paired client (one pairing). One client at a time is enforced at
stream start. The key reaches V3 only through a sealed memfd in its own non-dumpable process
(cores off; CLAUDE.md rule 2 amended with Batt's OK).

**Results:** pending (to be filled when the clean room runs).
