---
doc_type: decision
hypothesis: null
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: S1 handover 1 (2026-10-02) stopped -- tscon from Batt's console failed (1326) and the console stayed 1920x1080. Before the next attempt -- rebuild gamestream (borderless window), make the console 1440x900 (Batt), tscon from poring-lab's own console. RDP stays the default.
---

# ADR-0009: Console-session capture as a second display mode (Sunshine first, VNC fallback)

- **Status:** PROPOSED (2026-10-01). ➡️ **2026-10-02: Batt approved the Sunshine install and the S1
  trial** ("Sunshine research gets the weight"); RDP stays the default until he decides otherwise.
  - Sunshine v2026.914.233613 is installed on the Dell by Batt (UAC). The MSI was checked first:
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

