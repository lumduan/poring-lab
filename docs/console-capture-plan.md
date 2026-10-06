---
doc_type: design
hypothesis: null
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: "➡️ DONE and superseded: approved and installed 2026-10-02/03 (Sunshine MSI, VDD, the tscon task; ADR-0009). What is on Windows now, and the rule for anything more: ADR-0019 (Windows stays clean, live audit 2026-10-06)."
---

# Console-session capture: plan (Sunshine primary, VNC fallback)

**PLAN ONLY.** Nothing in this document is installed or configured yet. The decision record is
[ADR-0009](adr/0009-console-session-capture.md) (PROPOSED).

Sources were fetched on 2026-10-01 from the URLs given inline (known pages only, no web search).
- **[S]** = read from source code, not from documentation.
- **UNVERIFIED** = no fetched page confirms it. It becomes a test step, never an assumption.

## 0. Why look past RDP at all

- **The RDP leg is the lab's delivery ceiling.** Up to Arm C, every codec delivers **6–12 fps** of a
  784×625 game window for **~6.5 desktop cores** of FreeRDP software decode:
  - progressive, AVC444 and AVCthin alike;
  - the Windows side skips 17–28 frames/s for "Insufficient Client Resources".
  - Details: [h264-plan.md](h264-plan.md).
- Arm C (FreeRDP 3.32.1) tests whether a newer client moves that ceiling. Its result is in
  h264-plan.md, "Arm C".
- **The console session avoids the RDP path entirely.**
  - The game renders on the Intel UHD 630 at 60 fps (PresentMon,
    [rathena-client.md](client/rathena-client.md)).
  - A console capture tool encodes those frames with **Quick Sync** (hardware).
  - The lab decodes **one** H.264 stream of ~1 MP, which costs a fraction of one core in software.
- **Batt's order (2026-10-01):** Arm C first; if it is not enough, VNC. Sunshine will be built
  regardless, after Arm C. Hyper-V is a separate, queued track.

## 1. The display must exist with the monitor off

### Facts
- **Desktop Duplication captures only from the GPU used for display.** Sunshine: "On Windows, Sunshine
  uses the Desktop Duplication API which only supports capturing from the GPU used for display"
  ([getting_started.md](https://github.com/LizardByte/Sunshine/blob/master/docs/getting_started.md)).
  - Every DXGI-based VNC server has the same constraint.
  - No active display output means nothing to capture.
- **Sunshine's own documentation names only a dongle**: "connect a display or HDMI dummy display
  dongle" (the eGPU note in getting_started.md).
- **The Moonlight wiki says the same** ([Troubleshooting](https://github.com/moonlight-stream/moonlight-docs/wiki/Troubleshooting)):
  - "If you want to stream without a monitor connected, you can buy a cheap headless HDMI dongle";
  - "Ensure your monitor is powered on".
- **What awesome-sunshine lists under "Virtual Displays"**
  ([awesome-sunshine](https://github.com/LizardByte/awesome-sunshine)):
  - Virtual-Display-Driver, now [VirtualDrivers/Virtual-Display-Driver](https://github.com/VirtualDrivers/Virtual-Display-Driver);
  - parsec-vdd;
  - virtual-display-rs.
- **Sunshine can turn a display on.** Its documented knob is `dd_configuration_option=ensure_active`
  ("Activate the display if it's currently inactive",
  [configuration.md](https://github.com/LizardByte/Sunshine/blob/master/docs/configuration.md)).
- **A monitor that is plugged in but powered off: UNVERIFIED.** No doc covers it, and it depends on
  the connector and the monitor.
  - With HDMI, the source's +5 V usually keeps the EDID readable, and many monitors keep hot-plug
    asserted in soft-off.
  - Many DisplayPort monitors drop hot-plug when off, and Windows then removes the output.

### How to check it safely, in increasing order of cost
1. **Today, read-only, from the RDP session.**
   - Command: `Get-PnpDevice -Class Monitor`.
   - Shows whether the physical monitor's device node is present (`OK`) or only remembered (`Unknown`).
   - Results are in section 8.
2. **First test after approval, nothing installed.**
   - Move the session to the console (section 2), wait, then return to RDP.
   - Then read `Microsoft-Windows-Kernel-PnP` / the monitor's device status and the session state.
3. **With Sunshine installed.**
   - Sunshine's log lists the outputs it found (`output_name` = the device_id GUID in the log).
   - `%ProgramFiles%\Sunshine\tools\dxgi-info.exe` prints adapters and outputs (configuration.md,
     `adapter_name`).
   - Run it in the console session.

### Fallback if the display disappears with the monitor off

| Option | What | Pros | Cons |
|---|---|---|---|
| **A. HDMI dummy plug (recommended)** | An EDID emulator in the HDMI port | Hardware; nothing to install, sign or update. Works before logon. This is what Sunshine and Moonlight name. | Fixed EDID modes: 1280×800 may not be offered, so the lab's 1280×800 calibrations would need 1280×720 or 1920×1080 (re-calibrate `GAME_REGION`). The physical monitor is then a second output unless unplugged. |
| B. Keep the monitor on | Brightness 0 / input switched away | Nothing to buy | Batt's monitor is a monitor, not lab hardware; the panel ages. |
| C. Virtual display driver (VDD) | [VirtualDrivers/Virtual-Display-Driver](https://github.com/VirtualDrivers/Virtual-Display-Driver) **25.7.23** (2025-07-23), MIT, an IddCx driver | Any mode (exactly 1280×800). Signed: the release notes say "Includes Signed Virtual Display Driver", and the README credits SignPath.io; test signing only for ARM64. | A **kernel-adjacent driver install** with admin rights. The README warns to uninstall it before major GPU driver updates or risk a black screen. Not tested here. |
| D. Apollo's SudoVDA | Built into the Apollo fork (section 3.6) | Creates and removes a display per stream | A fork that diverges from upstream; signing **UNVERIFIED**; it brings clipboard sync (rejected, section 6). |

**Recommendation:** run check 1 today, and check 2 as the first approved step. If the output
disappears, buy **A**. C stays the fallback when A's modes don't fit.

## 2. Session switching: one Windows session, moved, never duplicated

### Today
- The `poring-lab` session is an RDP session (`rdp-tcp#N`). The physical console shows the lock
  screen.
- ADR-0001: Windows 11 client editions allow one interactive session.

### Facts
- **tscon** ([Microsoft Learn](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/tscon)):
  - syntax: `tscon {<sessionID>|<sessionname>} [/dest:<sessionname>] [/password:<pw>|/password:*] [/v]`;
  - it needs "Full Control access permission or Connect special access permission";
  - it fails without `/password` when the target session belongs to another user;
  - the same page says **"You can't connect to the console session."**
- **The `/dest:console` trick is community-documented, not Microsoft-documented.** The Moonlight wiki:
  `tscon $session /dest:console` "will terminate your RDP session but leave it unlocked". The wiki
  also says RDP leaves the PC "technically locked, causing streaming issues even after
  disconnecting".
- **Sunshine runs as SYSTEM in the console session [S].** `sunshinesvc` launches `Sunshine.exe` in
  `WTSGetActiveConsoleSessionId()`, and restarts it on `WTS_CONSOLE_CONNECT`
  ([sunshinesvc.cpp](https://github.com/LizardByte/Sunshine/blob/master/tools/sunshinesvc.cpp)).
  - So it follows the session onto the console automatically.
  - It cannot see an RDP session. That is consistent with the wiki; there is no Sunshine doc statement.

### Switching procedure (to verify step by step; nothing here has been run)
1. **Hold the RDP loop**, so it cannot reconnect and steal the session back. This needs a new
   whitelisted override keyword (proposal: `RDP_MODE=console`): `rdp-loop.sh` idles while it is set,
   and `/health` reports `display_path: console`.
   - Until that exists: `supervisorctl stop rdp`. But a desktop container restart would then
     reconnect RDP, kick the console session to the lock screen, and stop the capture.
2. **Who runs tscon. Cheapest first, all UNVERIFIED:**
   - **a. `poring-lab` itself, not elevated: try first.**
     - Default RDP-Tcp permissions give Remote Desktop Users "User Access", which includes Connect
       (to verify on this PC).
     - Connecting **its own** session needs no password, and no UAC.
   - **b. Batt's elevated console** (he answers UAC himself).
     - The session belongs to `poring-lab`, so tscon needs `/password:*`.
     - That is an **interactive prompt**, never a command line. The agent may type it only as a
       sensitive batch, via `ro_agent.py console-secret`.
   - **c. A scheduled task running as SYSTEM**, created once by Batt and runnable by `poring-lab`.
     - Needs no password, but it is a standing privilege grant. Last resort.
3. **Order, so there is never a race and never two sessions:**
   1. In the session's console, type `Start-Sleep 10; tscon <id> /dest:console`.
   2. Within the 10 s, the lab stops the RDP client (step 1).
   3. The session is now *disconnected*, and tscon moves it onto the physical console, unlocked.
   - There is exactly one Windows session throughout: the same session ID, moved.
4. **Back to RDP.** Clear the hold, and rdp-loop connects. RDP takes the session from the console,
   and the console locks. This is the ADR-0001 behaviour, unchanged.
   - Sunshine keeps running but captures the lock screen. It may also capture the logon desktop,
     because SYSTEM follows the input desktop [S]
     ([display_base.cpp](https://github.com/LizardByte/Sunshine/blob/master/src/platform/windows/display_base.cpp)).
5. **Locking while on the console.** Read-only checks today (section 8), changes only with Batt's
   approval:
   - screen saver + `ScreenSaverIsSecure`;
   - `InactivityTimeoutSecs` (machine policy);
   - Dynamic Lock;
   - the power plan: display off is harmless if capture continues (to verify), but sleep must be
     **never**.
6. **After a reboot.** The console shows the logon screen.
   - Today's recovery is: RDP logon, then steps 1–3.
   - **Sysinternals Autologon v3.10** ([Learn](https://learn.microsoft.com/en-us/sysinternals/downloads/autologon))
     would log `poring-lab` on at boot. But:
     - "the password is encrypted in the registry as an LSA secret, a user with administrative
       rights can easily retrieve and decrypt it";
     - its CLI form puts the password in argv (use the GUI only).
   - **Not recommended now**: reboots are rare, and the RDP path recovers.

## 3. Sunshine (primary)

### 3.1 What and where
- **Release:** Sunshine **v2026.914.233613** (2026-09-15), `Sunshine-Windows-AMD64-installer.msi`,
  33,710,080 bytes, GPL-3.0.
  - Source: [releases API](https://api.github.com/repos/LizardByte/Sunshine/releases/latest).
  - Requirements ([README](https://github.com/LizardByte/Sunshine/blob/master/README.md)): Windows 11+,
    and an Intel "Skylake or newer with QuickSync". The UHD 630 qualifies.
- **Installation**: as a service by default ("This is the default when installing Sunshine from the
  Windows installer").
  - The service is `SunshineService` (`tools\sunshinesvc.exe`).
  - The installer adds **program-based** firewall rules (`netsh … program=sunshine.exe`) for TCP and
    UDP from **any** address ([add-firewall-rule.bat](https://github.com/LizardByte/Sunshine/blob/master/src_assets/windows/misc/firewall/add-firewall-rule.bat)).

### 3.2 Configuration (all keys from [configuration.md](https://github.com/LizardByte/Sunshine/blob/master/docs/configuration.md))

| Key | Value | Why |
|---|---|---|
| `capture` | `ddx` | Desktop Duplication. `wgc` "is not compatible with the Sunshine service". |
| `encoder` | `quicksync` | The UHD 630's hardware encoder |
| `qsv_preset` | `veryfast` (A/B against the default `medium`) | Encode latency |
| `qsv_coder` | `cavlc` | "faster decode", which matters on our software decoder |
| `hevc_mode` / `av1_mode` | off (H.264 only) | One codec to decode; the UHD 630 has no AV1 encode |
| `minimum_fps_target` | 30 | Default 0 = half the stream fps. Keeps frames flowing when the scene is static (the measurement tools need steady frames) |
| `fec_percentage` | 20 (default), then A/B with 5–10 | The LAN has negligible loss; FEC costs bitrate and encode work |
| `origin_web_ui_allowed` | **`pc`** (default `lan`) | Web UI from the Windows PC itself only |
| `bind_address` | the PC's LAN address | Default empty = all interfaces |
| `lan_encryption_mode` | 1 or 2 (default 0 = no stream encryption on the LAN) | Video crosses the LAN in the clear otherwise. Our client must support it (to verify) |
| `upnp` | disabled (default) | — |
| `dd_configuration_option` | `ensure_active` if section 1 shows an inactive output; otherwise `disabled` (default) | — |
| `keyboard` / `mouse` | on | Input (section 3.4) |
| `controller` / `gamepad` | **off** | No ViGEmBus, no virtual gamepad driver |

- **There are no `fps` or `resolutions` keys.** The client asks for width, height and fps at launch,
  and `dd_resolution_option` decides whether Windows' mode changes.
- **Our request:** 1280×800 at 30 fps, then 60.
  ➡️ **SUPERSEDED 2026-10-02: 1440×900.** The lab session grew to hold the frozen 1280×720 client
  area (docs/client/rathena-client.md). gamestream requests 1440×900, and the console desktop
  must be 1440×900 so `GAME_REGION` stays 80,77,1280,720. The 1280×800 lines below are history.
  - That matches today's Xvfb desktop exactly, so `GAME_REGION`, the ro_agent signatures and the
    measurement tools carry over unchanged.
  - The game window itself (800×664) cannot be streamed alone: Sunshine captures an output, not a
    window.
- **Whether Sunshine scales or crops when the request differs from the desktop mode: UNVERIFIED.**
  So the console desktop should be **set to 1280×800** (Batt, Settings → Display): the dummy plug
  must offer it, or the VDD.
- **No dedicated low-latency switch is documented.** `performance_tuning.md` has only AMD and NVIDIA
  tips. Latency comes from the preset, CAVLC, no B-frames (GameStream streams have none), and
  our decoder flags (section 3.5).

### 3.3 Pairing, firewall, web UI
- **Web UI:** `https://localhost:47990`, with a self-signed certificate.
  - Batt creates the username and password on first run, as the human, in the browser; never on a
    command line.
  - With `origin_web_ui_allowed=pc` it is reachable only from the PC itself.
  - Reset: `sunshine --creds …`. That is an argv secret, so use it only interactively and never from
    the agent.
- **Pairing (once):**
  1. Our client starts it (`/pair?…phrase=getservercert` on TCP 47989, then the challenge rounds;
     [libgamestream client.c](https://github.com/moonlight-stream/moonlight-embedded/blob/master/libgamestream/client.c) [S]).
  2. The client shows a 4-digit PIN.
  3. Batt enters it in the web UI (or `POST /api/pin {"pairing_id","pin","name"}` with web-UI basic
     auth; [api.md](https://github.com/LizardByte/Sunshine/blob/master/docs/api.md)).
  - **The agent never holds the web UI credentials.**
- **Exactly one paired client: ours.** Pairing any other Moonlight (Batt's Mac, a phone) would be a
  **second input writer that bypasses the mux**, so it is forbidden.
  - Check: `/api/clients/list` in the web UI after pairing.
  - ADR-0009 makes this a rule.
- **Ports** ([Network.vue](https://github.com/LizardByte/Sunshine/blob/master/src_assets/common/assets/web/configs/tabs/Network.vue), offsets from the base `port` 47989 [S]):

  | Protocol | Port | Use |
  |---|---|---|
  | TCP | 47984 | HTTPS (pair, launch) |
  | TCP | 47989 | HTTP |
  | TCP | 47990 | Web UI |
  | TCP | 48010 | RTSP |
  | UDP | 47998 | Video |
  | UDP | 47999 | Control |
  | UDP | 48000 | Audio |

  UDP 48002 and 48010 are not in the current table.
- **Firewall.** Batt restricts the installer's program rules to the lab host and to the private
  profile, in an elevated console. This takes no secret, so the agent may type it into his console:

        Get-NetFirewallRule | ? DisplayName -like '*unshine*' |
          Set-NetFirewallRule -RemoteAddress 192.168.1.13 -Profile Private

  Then read the rules back (`Get-NetFirewallAddressFilter`) before reporting success. TCP 47990
  needs no remote access at all with `pc`.

### 3.4 Input: the biggest unknown
- **How Sunshine injects input** (getting_started.md / troubleshooting.md, "Windows"): keyboard and
  mouse go through **libvirtualhid**.
  - With the separately installed **Virtual HID Broker** plus a **paid licence**: keys and relative
    mouse appear as a real HID device ("Raw Input").
  - Without them: the free **SendInput** fallback.
  - **Absolute mouse positioning always uses Windows input injection.**
- **The docs warn:** "the Windows cursor may still move even though a game that listens only for Raw
  Input receives nothing".
- **Whether the RO client accepts SendInput keyboard and mouse: UNVERIFIED. This is the first thing
  to test**, before any client work. On the console it is cheap:
  - Batt's own Moonlight would do it, but it would be a second client. Not allowed (3.3).
  - Instead, test with the lab's client in S1 (3.5).
  - The XTest → xfreerdp → RDP → Windows path that works today is a different path. It proves
    nothing about SendInput from a SYSTEM process in the console session.
- **We do not want the paid HID broker.** Absolute positioning (which our normalized pointer needs)
  bypasses it anyway.

### 3.5 Our client: two stages
None of the linked projects is a Python GameStream client
([moonlight-common-c](https://github.com/moonlight-stream/moonlight-common-c),
[moonlight-embedded](https://github.com/moonlight-stream/moonlight-embedded),
[awesome-sunshine](https://github.com/LizardByte/awesome-sunshine)).

➡️ **SUPERSEDED 2026-10-02: S1 uses moonlight-qt in its own `gamestream` service** (ADR-0009
revision). moonlight-embedded's X11 mouse turned out relative-only, and it warps the pointer
(`src/input/x11.c`); moonlight-qt takes X events via SDL with `--absolute-mouse`. The paragraph
below is the original plan, kept as history.

**S1: moonlight-embedded inside the desktop container, rendering into Xvfb `:99`.** This is the
quickest way to a measurement.
- moonlight-embedded **v2.7.1** (2025-11-30), GPL-3.0. CLI: `moonlight pair|stream|list|quit`,
  `-width -height -fps -bitrate -codec h264 -platform x11|sdl|fake` [S].
- Pairing and launch are done by its `libgamestream`.
- **Not in Debian** (packages.debian.org and tracker.debian.org: no results). It is built from source
  (CMake; curl, OpenSSL, expat, uuid, avahi-client, FFmpeg, X11/EGL dev packages).
  - That is a **guarded desktop image build**, and its tarball export burst, measured on 2026-10-01:
    ~1–5 s at 70–100 % quant io_full with today's `armbuilder` (docker-container) builder.
- **What it buys:** nothing downstream changes.
  - The backend still captures Xvfb with XDamage.
  - The mux still injects with XTest into the moonlight window.
  - vision still grabs Xvfb.
  - `measure_motion.py`, `measure_delay.py` and `latency_probe.py` give directly comparable numbers.
- **What it risks:** how moonlight-embedded reads input on `-platform x11` is **UNVERIFIED**.
  - It may read evdev devices (`/dev/input`), not X events. Then XTest input would never reach it.
  - If so, S1 measures video only, and input moves to S2.
- `xfreerdp` and `moonlight` must never both be connected: the `RDP_MODE=console` hold (section 2)
  is the interlock.

**S2: our own client in the backend, a new `poring_env` transport.**
- **Libraries:**
  - `libmoonlight-common.so` (CMake, shared by default; it needs its bundled ENet) for
    RTSP/control/video/input;
  - `libgamestream.so` (from moonlight-embedded) for pair/serverinfo/launch, which moonlight-common-c
    does not do;
  - both wrapped with **ctypes**.
- **Video is pull-based:** `CAPABILITY_PULL_RENDERER` + `LiWaitForNextVideoFrame` /
  `LiCompleteVideoFrame` ([Limelight.h](https://github.com/moonlight-stream/moonlight-common-c/blob/master/src/Limelight.h) [S]).
  - So there is no C → Python callback on the hot path.
  - Decode units are Annex-B, with SPS/PPS as separate entries on IDR frames.
- **Decode: PyAV 19.0.0** (2026-09-29, BSD-3, Python ≥3.12; manylinux wheel 35 MB with FFmpeg 8
  bundled; [PyPI](https://pypi.org/pypi/av/json)). Untested recipe:

        ctx = av.CodecContext.create("h264", "r")
        ctx.flags |= av.codec.context.Flags.low_delay   # no reorder delay
        ctx.thread_type = "SLICE"                       # FRAME threads add a frame of delay each
        for pkt in ctx.parse(annexb): frames = ctx.decode(pkt)
        bgra = frame.to_ndarray(format="bgra")          # Frame is BGRA (ADR-0003)

  `decode()` is "not thread-safe": one decode thread.
- **Input:**

  | Our event | moonlight-common-c call |
  |---|---|
  | Pointer, normalized [0, 1] | `LiSendMousePositionEvent(x, y, refW, refH)` (absolute; SendInput on the host) |
  | Buttons | `LiSendMouseButtonEvent` |
  | Wheel | `LiSendScrollEvent` |
  | Keys | `LiSendKeyboardEvent(vk, action, modifiers)`. The code is a **Win32 virtual-key code, US layout**, so `keymap.py` gets a `KeyboardEvent.code → VK` table next to the evdev one (drift-tested like `keycodes.gen.ts`). `always_send_scancodes` (default on) keeps scancodes for games. |

  Remote input is always AES-encrypted with the `rikey` from `/launch` (`STREAM_CONFIGURATION`).
- **Fitting it into the existing seams. The mux, the input log and the agent code stay unchanged:**
  - **Input.** The backend's `Injector` takes a factory for the `XInput` protocol (`send_many`,
    `pointer`, `has_window_class`, `close`; `services/backend/src/poring_backend/state.py`).
    - A `GameStreamInput` implements it.
    - `pointer` returns the last position the mux sent (the stream does not report the host cursor).
    - `has_window_class` becomes "stream connected".
    - `InputMux`, the leases, sensitive batches, `balanced()` and the input log are untouched.
  - **Frames.** `poring_env` gets an optional `gamestream` extra with a `GameStreamSource`
    (`FrameSource`): `grab()` returns the newest decoded frame.
    - `frame_id` = per-grabber counter (as today).
    - `t_capture_ns` = **host `CLOCK_MONOTONIC` at decode completion**, the same clock domain as the
      backend and vision, so `t_mono_ns` arithmetic is unchanged.
    - The receive time of the frame's first packet is kept beside it. The difference is the decode
      cost.
    - Sunshine's per-frame host processing latency is in the decode unit
      (`frameHostProcessingLatency`, to verify in `Limelight.h`). It is a *duration*, never
      subtracted across clocks.
  - **The capture hub** (`stream.py`) gets a `gamestream` source beside `damage`.
  - **vision** gets frames **from the backend** instead of from X. That is exactly the ADR-0005
    recommendation (section 7).
  - `CompositeEnv(GameStreamSource, GameStreamInput)` is the `Env` for offline tools. The ADR-0003
    table gains a row.
- **Size:** the ctypes surface is ~15 functions plus 4 structs. Pairing can stay a one-off
  `moonlight pair` run (S1's binary) whose cert/key the backend reuses.

### 3.6 Apollo (considered, not chosen)
[Apollo](https://github.com/ClassicOldSong/Apollo) **v0.4.6** (2025-07-13, GPL-3.0) is a Sunshine fork
that adds:
- SudoVDA virtual displays that match each client;
- per-client permissions;
- **clipboard sync**;
- an input-only mode.

Its author says it "will no longer be compatible with OG Sunshine and OG Moonlight eventually".
- Clipboard sync is a bidirectional side channel, against ADR-0004.
- Divergence from upstream is a maintenance risk.
- **Not chosen.** SudoVDA alone has no releases (signing **UNVERIFIED**).

## 4. VNC fallback

VNC needs the **same console switch** (section 2): a Windows VNC server serves the console.

| | TightVNC | UltraVNC | TigerVNC winvnc |
|---|---|---|---|
| Version | **2.8.88** (2026-06-19) | **1.8.3.0** (Sept 2026) | — |
| Licence | GPLv2 (commercial also offered) | GPL-3.0 | GPL |
| Capture | Desktop Duplication since 2.8.53 ([whatsnew](https://www.tightvnc.com/whatsnew.php)) | "DDengine": `ddengine64.dll` on Windows 8+, a **binary blob** in the repo [S] | — |
| Encodings | Tight (JPEG), ZRLE, Hextile, … | Tight, ZRLE, Ultra, Zstd, … [S] | — |
| Auth | Standard VNC auth: DES challenge, **password truncated to 8 characters** (RFC 6143 §7.2.2) | VNC 8-byte password; MS-Logon III (X25519 + AES-256-GCM, added in 1.8.2.4 together with 10 CVE fixes) | — |
| Notes | Also "possible to connect to an active RDP session" (2.8.53): **not used**, it would be a second path into the RDP session | Recent CVE history | "currently unmaintained … may not work if … Remote desktop features are in use" ([README](https://github.com/TigerVNC/tigervnc)): **excluded** |

**Lab-side client, same two stages as Sunshine:**
- **V1.** `vncviewer` (TigerVNC viewer, an X11 app) fullscreen in Xvfb `:99` instead of xfreerdp.
  - Everything downstream stays unchanged.
  - XTest input reaches it as ordinary X events, so this input path is *likely* to work, unlike
    moonlight-embedded's.
  - Debian package `tigervnc-viewer`: version to confirm at build time.
  - Disable clipboard in the viewer: `-AcceptClipboard=0 -SendClipboard=0 -SetPrimary=0`.
- **V2.** A Python RFB client behind the same `FrameSource` / `XInput` seams as S2. Today's options
  are weak:
  - [vncdotool](https://github.com/sibson/vncdotool) 1.4.2 is Twisted (not asyncio). It offers only
    Raw by default; Tight exists only in the unreleased 2.0.0.dev0.
  - [asyncvnc](https://github.com/barneygale/asyncvnc) 1.3.0 (2023) does Raw and Zlib only, and it
    handles clipboard updates (strip them).
  - A minimal own RFB client with Tight/JPEG is ~500 lines. Only if V1's numbers justify it.

**VNC's weak authentication: mitigations, all required:**
1. Firewall: TCP 5900 from 192.168.1.13 only, private profile.
2. Bind to the LAN interface (or `LoopbackOnly` plus an SSH tunnel; that needs Windows OpenSSH
   server, another install, so not first).
3. A random 8-character password, written to `.env` with `rotate_secrets.py`, never echoed.
4. Server-side **clipboard and file transfer off** (TightVNC: the clipboard options; UltraVNC: file
   transfer + clipboard off).
5. **The view-only password unset** (it would be a second viewer path).

MS-Logon III would be the strong option, but TigerVNC's viewer doesn't speak it.

## 5. Measurement plan (the same tables as the RDP arms)

Each stage (S1, S2, V1) gets the **Arm C tables**, from `scripts/measure_arm.sh LABEL`:
1. **Delivery:** frames reaching the lab per second during camera rotation (median, p10–p90),
   indoor (`prt_church 99 112`) and outdoor (`new_4-1 53 111`), 60 s each.
2. **Cost:** client cores (desktop container for S1/V1, backend for S2), threads, and idle cores with
   the game visible.
3. **Host side** (replaces the RemoteFX counters, which do not exist off-RDP):
   - `\GPU Engine(*engtype_VideoEncode)\Utilization Percentage` via `typeperf`;
   - the encoder's own stats (Sunshine log);
   - the game's own fps (PresentMon, as in rathena-client.md).
4. **Freshness:** packet → frame delay, 40 walks at `prt_fild08 170 375` (`measure_delay.py walks 40
   --as gm`), reported as p50 / p75 / p90 / p95.
5. **Input latency:** key → paint (`latency_probe.py`, Phase 0 method) and click → response.
6. **Glass-to-glass (optional, Batt):** a 240 fps phone video of the physical monitor beside the lab
   console, for one key press series. It is the only measurement that includes Windows' own
   present/scan-out.

**Gate to adopt console mode as the lab default:** every condition must hold.
- Outdoor delivery ≥ 2× the best RDP arm.
- Packet → frame p75 ≤ the best RDP arm's.
- RO accepts the input path (keyboard, click, chat).
- ADR-0009 accepted, including the rule-2 amendment.

## 6. What is lost without RDP, and the human-only replacements

| RDP feature | ADR | Console mode | Replacement that keeps ADR-0004's guarantees |
|---|---|---|---|
| ⌘V paste (T1, cliprdr: X CLIPBOARD → Windows clipboard, then a scrub) | 0004 | Gone. Sunshine has no clipboard sync (no mention in configuration, getting_started or troubleshooting) | **Typed paste.** In S2: `LiSendUtf8TextEvent` (what Moonlight's Ctrl+Alt+Shift+V does, [Setup Guide](https://github.com/moonlight-stream/moonlight-docs/wiki/Setup-Guide)). Sunshine types the text as Unicode input, so **nothing lands on the Windows clipboard and there is nothing to scrub**. Conditions: human-only (`ClipboardPaste` from a browser on `/ws/input`, as today); never in `AgentToBackend` (rule 8 unchanged); the audit keeps the 12-hex digest (➡️ dropped 2026-10-02, ADR-0004 amendment c: event and time only); refused for BOT by the existing mux rule. **UNVERIFIED** whether RO's chat box accepts Unicode injection; Notepad-class fields should. S1 has no equivalent: the backend could type ASCII as key events (a sensitive batch), and Thai would need Kedmanee positions (`ro_agent say --thai-keys`). |
| `\\tsclient\transfer` files (F1, rdpdr) | 0004 | Gone | **Hybrid:** switch to RDP mode for file work (section 2, step 4). An SMB share would be a new network service with its own attack surface: not proposed. |
| Pinned server certificate (`RDP_CERT_SHA256`) | 0001 | — | Sunshine pairing (mutual certificates) for HTTPS; `lan_encryption_mode` ≥ 1 for the stream; input always AES |
| Exit-code reconnect policy | 0001 | — | S1: moonlight's exit codes need the same never-fight-a-human mapping (to define). S2: the backend owns reconnects. |

**Recommendation: a hybrid.**
- RDP mode remains the default for human work.
- Console mode is entered for capture and agent sessions.
- Each switch is explicit and logged, and costs one tscon.

## 7. Impact on the ADRs and the Phase 0 baselines

- **ADR-0001 (one RDP session).**
  - The invariant becomes **one Windows session and one display path at a time**: RDP mode *or*
    console mode, never both.
  - **CLAUDE.md hard rule 2** ("Never add a second RDP or VNC path into Windows") needs an explicit
    amendment for Batt: Sunshine or VNC is allowed only as the console-mode path, and never
    concurrently with RDP.
  - The FreeRDP pin text also changes if Arm C keeps 3.32.
- **ADR-0002 (input mux).**
  - Unchanged in S1 and V1 (XTest into the viewer window).
  - In S2 the mux is unchanged and only the `Injector`'s `XInput` implementation is swapped.
  - **New exposure:** Sunshine or VNC accept any authenticated client. "One input writer" now also
    depends on exactly one paired client and the firewall restriction.
- **ADR-0003 (Env contract).** Unchanged. A new implementation row (`GameStreamSource` /
  `GameStreamInput`).
- **ADR-0004 (clipboard and files).**
  - T1 and F1 exist only in RDP mode. In console mode, paste is the typed-paste replacement above
    (or absent).
  - Apollo, and server-side VNC clipboard, are rejected for being bidirectional.
  - The scrub and the watchdog stay as they are for RDP mode.
- **ADR-0005 (vision X access).**
  - S1 and V1 leave the gap as it is.
  - S2 makes the backend the frame owner. Serving frames to vision from the backend is ADR-0005's
    recommended option (a), so S2 **helps close** issue #1.
- **ADR-0006 (environments).**
  - Sunshine captures the **whole console**: if Batt plays the community-server client there, the lab
    sees it. Manual play is allowed; automation still needs the interlock (issue #2).
  - Packet capture is unaffected (the sniffer runs on the Linux side).
- **ADR-0007 (packet ground truth).** Unaffected.
- **Phase 0 baselines** (key → sent 91 ms; RDP leg 66–75 ms; capture 30 fps; codec tables) are all
  RDP-path numbers. Console mode needs its own baseline with the same scripts. S1/V1 keep them valid
  without changes.

## 8. Read-only checks on the Windows PC (2026-10-01)

Typed into a non-admin PowerShell in the `poring-lab` RDP session (FreeRDP 3.32.1, 21:53–21:56 ICT).
No admin, nothing changed.

| Check | Result | Meaning |
|---|---|---|
| `qwinsta` | `services` 0 Disc; `console` 1 Conn (no user); `rdp-tcp#0` **poring-lab 2 Active** | One interactive session, ID 2. That is the session tscon would move. |
| `Get-PnpDevice -Class Monitor` | **`DISPLAY\SAM07C0\4&26270E7D&0&UID249395`: OK, Present = True** (the Samsung on the Intel adapter), **with its panel powered off**. Also: `DEFAULT_MONITOR …UID256` OK (the RDP virtual monitor). Three remembered, not present: `GSM5AFB`, `SAM07C0 …UID0`, `DEFAULT_MONITOR …UID200803`. | Check 1 **passes**: the powered-off monitor keeps its output present. A dummy plug is probably unnecessary. Check 2 (on the console) still decides. |
| Display adapters | Microsoft Remote Display Adapter 10.0.26100.9278 at 1280×800 (the RDP session); **Intel UHD Graphics 630, driver 27.20.100.9664, at 1920×1080** | The console desktop is 1920×1080. Either stream 1920×1080 and crop, or set 1280×800 if the Samsung's EDID offers it (to check on the console). Whether Sunshine's QSV path needs a newer Intel driver than 27.20.100.9664 is **UNVERIFIED**; RDP's own Quick Sync works with it (event 170, Arm A). |
| `WmiMonitorConnectionParams` (HDMI vs DP) | No output as a standard user | Connector type unknown; it needs admin. Not needed while check 1 passes. |
| `Get-NetFirewallProfile` | Domain, Private, Public all **enabled**; default inbound NotConfigured (= block) | Sunshine's program rules (any address) must be narrowed to 192.168.1.13 (3.3) |
| Smart App Control (`CI\Policy` `VerifiedAndReputablePolicyState`) | **1 = ON (enforce)** | Unsigned or unknown-reputation installers and binaries are **blocked**. The Sunshine MSI is Authenticode-signed; the VNC servers' signing is UNVERIFIED and may be refused outright. SAC cannot be turned back on once off, so **switching it off is not an option to plan around**. |
| Screen saver (`HKCU\Control Panel\Desktop`) | `ScreenSaveActive` 1; `ScreenSaverIsSecure` and `ScreenSaveTimeOut` empty | No secure screen saver, so nothing locks the console on idle |
| `InactivityTimeoutSecs` (machine policy) | unset | No machine inactivity lock |
| Power | High performance; sleep (AC) **never**; display off (AC) **never** | Nothing to change |
| OS / CPU | Windows 11 Pro, build 26300; **Intel Core i5-10500T** (UHD 630) | Sunshine's minimums (Windows 11+, Skylake+ with Quick Sync) are met |

## 9. Software to install on Windows: for Batt's approval

Nothing is installed until Batt approves each line. He runs every installer himself, elevated, and
checks the signature first with `Get-AuthenticodeSignature <file>`.

| # | Software | Source | Version | Size | Signature | Needed for |
|---|---|---|---|---|---|---|
| 1 | Sunshine (`Sunshine-Windows-AMD64-installer.msi`) | https://github.com/LizardByte/Sunshine/releases/tag/v2026.914.233613 | v2026.914.233613 (2026-09-15) | 33,710,080 B | Authenticode: the MSI has a DigitalSignature stream, issuer "Microsoft ID Verified CS AOC CA 03" / "… Code Signing PCA 2021" (chain **not validated**; Batt validates) | S1/S2. In the installer: no gamepad, no Virtual HID |
| 2a | HDMI dummy plug (hardware) | Any local shop | — | — | n/a | Only if check 1/2 shows the output disappears with the monitor off |
| 2b | Virtual-Display-Driver (instead of 2a) | https://github.com/VirtualDrivers/Virtual-Display-Driver/releases (`winget install --id=VirtualDrivers.Virtual-Display-Driver -e`) | 25.7.23 (2025-07-23) | `VDD.Control.25.7.23.zip` 71.2 MB | "Signed" per the release notes and README (SignPath); not checked here | Only if 2a's modes don't fit |
| 3 | Sysinternals Autologon | https://learn.microsoft.com/en-us/sysinternals/downloads/autologon | v3.10 | 495 KB zip | Microsoft signing not stated on the page (**UNVERIFIED**) | **Not recommended now** |
| 4 | TightVNC Server (VNC fallback only) | https://www.tightvnc.com/download.php | 2.8.88 (2026-06-19) | to read at download | **UNVERIFIED** | Only if Sunshine fails |
| 4' | UltraVNC (alternative to 4) | https://uvnc.com/downloads/ultravnc/172-ultravnc-1-8-3-0.html | 1.8.3.0 | to read at download | **UNVERIFIED**; ships a binary-blob DLL | Only if 4 is unsuitable |

**Lab side** (Linux, no Windows approval, but builds go through `guarded_build.py`):
- ~~moonlight-embedded v2.7.1 built from source into the desktop image (S1)~~ ➡️ moonlight-qt 6.1.0
  AppImage in the `gamestream` image (sha256 pinned) (S1);
- `libmoonlight-common` + `libgamestream` shared libraries and PyAV 19.0.0 in the backend (S2);
- `tigervnc-viewer` from Debian (V1).

**Smart App Control** decides whether unsigned installers can run at all. Its state is recorded in
section 8.

## 10. Order once approved (each step stops on failure)

1. Console-switch test with nothing installed (section 2): tscon variant a, display check 2, back
   to RDP. → Decide whether to buy the dummy plug.
2. Batt installs Sunshine (item 1), sets the web UI credentials, applies the 3.2 configuration and
   the firewall restriction. The agent types only non-secret commands into his elevated console, and
   reads every setting back.
3. ➡️ (2026-10-02: a guarded **gamestream** build with moonlight-qt, and the capture-backend lock
   instead of the hold below) Guarded desktop build with moonlight-embedded (S1); pairing with Batt's PIN; the
   `RDP_MODE=console` hold.
4. S1 measurement (section 5), **plus the SendInput test** (3.4).
5. Decide: S2, V1, or stay on RDP. Record it in ADR-0009 (ACCEPTED or REJECTED).
