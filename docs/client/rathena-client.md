---
doc_type: design
hypothesis: null
status: ACCUMULATING
role: null
verdict_date: 2026-09-30
verdict_ticket: null
supersedes: null
related: []
next_action: RDP delivery is client decode; the lab runs RDP_GFX=progressive under the poring-lab account (2026-10-01). Next: FreeRDP 3.32.1 (docs/h264-plan.md Arm C) in a guarded build window.
---

# The rAthena client on Windows (C:\RO-rAthena)

This is the recipe for the lab's RO client. It connects only to this repo's rAthena on the LAN
(ADR-0006). Nothing in here is a client file: the exe, the GRFs and the clientinfo files never
enter the repo (`.gitignore`).

## Hard rule: RagnarokClassic is never touched

The Windows PC also runs the unrelated "RagnarokClassic" client, in
`C:\Program Files (x86)\Gravity Game Tech\RagnarokClassic`. Its settings live in
`HKLM\SOFTWARE\WOW6432Node\Gravity Soft\Ragnarok`, the key every kRO client uses. So:

- Everything of ours lives under `C:\RO-rAthena\`.
- The exe is patched with **HKLMtoHKCU**, so its settings live in `HKCU\Software\Gravity Soft\` instead.
- It is launched **without elevation** (`__COMPAT_LAYER=RunAsInvoker`). A non-elevated process
  cannot write RagnarokClassic's HKLM key or its Program Files folder.
- kRO's own launcher, Setup and RSU are **never run**; they sit in `_kro_exes_NEVER_RUN\`. The
  launcher and RSU would also upgrade the data to GRF v3, which breaks this exe.
- Baseline: `C:\RO-rAthena\_baseline\` holds a `reg export` of RagnarokClassic's key, plus its
  top-level listing, recorded before any client step. Every comparison so far matches.
  - Caveat: a folder listing reads the timestamps the parent folder caches, and NTFS can refresh
    them later (a `_tmpEmblem` entry did). So compare each entry's own record (`Get-Item`).

## Versions

| Piece | What | Verified |
|---|---|---|
| Exe | `2021-11-03_Ragexe_1635926200` (rAthena calls it RagexeRE) = PACKETVER 20211103 | Archive from Gravity's patch server `ropatch.gnjoy.com/Patchfile_Test/`: SHA-256 `7d6d0f54…7b575cf`, matching the mirror's published checksum. Exe: 12,903,960 B, i386, PE 2021-11-03 07:29:53 UTC, Authenticode valid (GRAVITY Co., Ltd.), VirusTotal 0/67 (`3f11ce85…1c3baa35`). |
| Data | kRO `Ragnarok_210607.zip` from `rofull.gnjoy.com` (Gravity CDN), 3,495,514,814 B | 7-Zip extracted 912 files / 3,752,605,608 B: `data.grf` (0x200), `rdata.grf`. The approved `RAG_SETUP_211105.exe` turned out to be InstallShield, which 7-Zip can't extract, so this zip is used instead (Batt, 2026-09-30). |
| Patcher | WARP `Neo-Mind/WARP` branch `rock_win32` (zip 13,820,311 B) | `WARP.exe` and `WARP_console.exe` match GitHub byte for byte. |
| Wrapper | dgVoodoo2 v2.87.5 (`DDraw.dll` + `D3DImm.dll`, x86, in the client folder only) | Zip 9,268,078 B, SHA-256 `5FFDE692…A1040850` (checked on Windows and on the host). `dgVoodooWatermark = false`, or it stamps its logo into every frame. |
| Diagnostics | 7-Zip 26.03 x64; Sysinternals Process Monitor | Both signed and verified. |

## Patches (warp-session.yml)

`WARP_console.exe -using warp-session.yml` builds `PoringLab.exe` from the source exe, which is
kept. WARP output is deterministic: same session, same hash.

- **Required:** No1and1Arg, NoHardCodedAddr, NoFilenameCheck, UseOldLogin, CallKoreaClientInfo,
  GRFsFromIni, HKLMtoHKCU.
- **LAN-only:** NoGNJoyLaunch. `NoHardCodedIP` is approved too, but WARP cancels it on this exe
  ("no known hard-coded IPs").
- **DataFolderFirst.** kRO's `data.grf` ships its own `data\clientinfo.xml` pointing at Gravity,
  and GRF contents win by default. Without this patch the first login would go to Gravity.
- **Optional:** NoNagle, FixChatAt.
- **Thai "Test A":** LoadKrExtSettings, and CustomFontName = Tahoma. Session input type 10 is text,
  as the hex of the NUL-terminated string.
- **Never:** NoWavyScreen, or any packet-key or encryption patch (rAthena's keys are 0 for this
  date).

## Client configuration (all under C:\RO-rAthena\client or HKCU)

- `DATA.INI`: `[Data]` with `0=rdata.grf`, `1=data.grf`.
- `data\clientinfo.xml` and `data\sclientinfo.xml`: address 192.168.1.13, port 6900, langtype 5,
  servicetype korea.
- **Settings keys.** Without `HKCU\Software\Gravity Soft\RenewSetup` and `...\Ragnarok`, the client
  loops at 100 % CPU trying to launch Setup.exe (found with Process Monitor).
  - Both keys hold: `GUIDDRIVER` (16 zero bytes, the primary display), and `GUIDDEVICE` = Direct3D
    HAL `{84E63DE0-46AA-11CF-816F-0000C020156E}`.
  - Also: `WIDTH`, `HEIGHT`, `BITPERPIXEL` 32, `ISFULLSCREENMODE` 0, `DEVICECNT` 0, `MODECNT` 0.
- **Rendering in the RDP session.** The client draws through DirectDraw/Direct3D 7.
  - Native D3D7 has no hardware path in the RDP session: the HAL and T&L devices fail with "Cannot
    init d3d", and the software RGB device draws black.
  - dgVoodoo2's `DDraw.dll` + `D3DImm.dll` translate it to D3D11. That D3D11 device runs on the
    **Intel UHD 630 hardware**, not WARP (measured 2026-09-30, see "Render performance"). Windows 11
    Pro already renders RDP sessions on the hardware GPU by default.
- **Windows (Batt, 2026-09-30):** system locale th-TH (ANSI code page 874), the Thai Kedmanee
  keyboard, time zone (UTC+07:00) Bangkok.
- **Smart App Control is On** (`VerifiedAndReputablePolicyState=1`, build 26200.9457). It blocks new
  unsigned exes: WARP variants other than the first `PoringLab.exe` were refused (Code Integrity
  3033). ➡️ SUPERSEDED 2026-09-30: turning SAC off is **no longer** irreversible on this build. See
  "UI text and Smart App Control" below.

## Render performance (2026-09-30)

The hypothesis was that the game renders at ~8–10 fps on WARP (software). **Rejected.** The game
renders at 60 fps on the Intel GPU; the bottleneck is RDP *delivery* of those frames to our Xvfb.

| Metric | 1280×720 (baseline) | 1280×800 (after) | Method |
|---|---|---|---|
| Game fps (idle) | 60.2 (1 % low 51.8) | 60.1 (1 % low 51.1) | PresentMon 2.6.0, 40–60 s, DXGI |
| Game fps (walking) | 60.3 (1 % low 51.6) | – | PresentMon, 25 s |
| D3D11 adapter | Intel UHD 630: 3D 46–48 %; Basic Render (WARP) 0 % | same, 48 % | `\GPU Engine(*)` per PID, LUID mapped via `HKLM\SOFTWARE\Microsoft\DirectX` |
| Client CPU | 28–31 % of one core | 26 % | process CPU delta over 10 s |
| Frames reaching Xvfb during motion | median 17.2 fps (8.7–20.4) | median 15.6 fps (7.7–15.8) | right-drag camera rotation (full-scene motion), counted as grabs differing by >1 % of pixels by >24 levels |
| Desktop container CPU during motion | 1000–1800 % (xfreerdp3, 393 threads) | 1000–1500 % | `docker stats` |
| Minimum click hold (UI) | 20 ms registers 6/6 | 20 ms 6/6 | status-window toggle, 6 trials × 20/50/80/120/200 ms |
| UI click → response | p50 114 / p95 140 ms from press; 60 / 87 ms from release | 119 / 141; 64 / 87 | same toggle, N=20, persistent-change detector |
| RDP leg (bot key → changed pixel, L1+L2) | p50 82 / p95 122 ms | p50 82 / p95 101 ms | `latency_probe.py cursor --k1 ControlLeft+KeyA --k2 ArrowRight --via agent`, N=40 |

- **Why clicks seemed to need 100–120 ms holds:** the earlier bot sent press and release in the same
  instant. With any real hold ≥ 20 ms the game registers every click. The bot's default hold is now
  **50 ms** (3 frames at 60 fps).
- **RDP pipeline A/B (FreeRDP side, one reconnect each, override file):** frame-ack off 18.3 fps, AVC420
  14.2, AVC444 16.6, progressive 16.7, RFX 16.0, default 17.2. No codec beats the others beyond run
  noise. The default (autodetect) is kept.
- **Not changed:** the RDS policies (`bEnumerateHWBeforeSW`, the AVC policies) and `DWMFRAMEINTERVAL` are
  all absent (default) and were left so. The GPU is already hardware. DWMFRAMEINTERVAL only lifts a
  30 fps cap that delivery (~17 fps) doesn't reach. dgVoodoo stays `OutputAPI=bestavailable`,
  `Adapters=all`.
- **Open (before dataset collection):** the ~17 fps delivery ceiling. xfreerdp's software GDI decode
  burns 10+ host cores during motion, and the Windows-side encoder load is unmeasured. Next candidates:
  the Windows RDP encoder (Task Manager / RdpCoreTS events 162/170), AVC hardware encode, and
  capturing the game on Windows instead of over RDP.
- World click → movement latency was not measured cleanly. lab_1 walked into monsters and the
  detector's targets were blocked, so this was stopped at Batt's request; Batt walks, the lab
  measures passively.

## UI text and Smart App Control (research only, 2026-09-30; nothing changed)

**UI text.**
- **Cause, confirmed on-box.** Any langtype other than 0 makes the exe read `data\msgstringtable.txt`
  (WARP ReadTxtFile code: `cmp [g_serviceType], 0`). Neither `data.grf` nor `rdata.grf` contains it,
  hence "NO MSG".
  - The chat-tab mojibake comes from the Korean `data\luafiles514\lua files\msgstring_kr.lub` /
    `msgstring_kr_s.lub` (both present in the GRFs), drawn with THAI_CHARSET, which langtype 5
    forces.
- **Option 1 (recommended), data only, no new exe:**
  - an English `msgstringtable.txt` from llchrisll/ROenglishRE (commit `8e6a3c85`, "Default Client
    Date Update to 2021-11-03", 3,970 lines);
  - plus English `msgstring_kr.lub` / `msgstring_kr_s.lub`, in `client\data\` (DataFolderFirst
    already makes it win over the GRF);
  - ASCII is a subset of CP874 and Tahoma covers Latin, so it renders under langtype 5, and Thai chat
    is unaffected;
  - check the ID count against the exe's embedded table with WARP's read-only "Extract msgstringtable"
    extension;
  - license: none in the repo, "educational purposes only", files "can be distributed, used and
    modified freely";
  - risk: strings hard-coded in the exe stay Korean or mojibake.
- **Other options:**
  - a Thai table (po456asd/ro1_client_thai_translation, GPL-3.0, 3,775 lines, gaps to fill);
  - a new exe: TranslateClient, or langtype 0 + charset 222 (WARP CustomFontCharset / NEMO
    SetFontCharset). A new unsigned exe is blocked by SAC.

**Smart App Control.**
- **Re-enable without reinstall is supported** from 26200.8117 (KB5086672) / 26200.8246 (KB5083769).
  Microsoft's SAC FAQ says "Recent Windows updates allow Smart App Control to be re-enabled without
  requiring a clean installation." This box is **26200.9457**. Current state On (enforce).
- No per-file exception exists. A self-signed signature doesn't help (it needs a Trusted Root Program
  CA). Reputation (ISG) is per file hash, so every re-patched exe starts unknown. DLLs are evaluated
  at load too.

## English UI text (applied 2026-10-01; data only, no new exe)

- Source: llchrisll/ROenglishRE commit `8e6a3c85` (2022-01-25, "Default Client Date Update to
  2021-11-03"). The Pre-Renewal tree has no msgstring files, so the Renewal ones are used.
- Each file's git blob was verified against the commit tree.
- Copied into the client's data folder, which wins over the GRF via DataFolderFirst. None of the names
  existed before, so there was nothing to back up.

| File (under `C:\RO-rAthena\client\`) | Bytes | git blob | SHA-256 |
|---|---|---|---|
| `data\msgstringtable.txt` | 132,571 | `1e996b63…` | `ede8a073…be59f5c5` |
| `data\luafiles514\lua files\msgstring_kr.lub` | 23,149 | `8860ba8e…` | `17bfdebe…72b88bade` |
| `data\luafiles514\lua files\msgstring_kr_s.lub` | 23,056 | `df3e1d3e…` | `633df944…8a80c3944` |

**Line count check.** WARP 1.5.3's read-only "Extract msgstringtable" extension, run on the unpatched
source exe (output to `_scratch\`):
- The exe's built-in table has **3,970** entries; ROenglishRE has **3,970**, so the IDs line up.
- ~~3,238 entries are identical, because the exe already embeds English text for most IDs.~~
  ➡️ **SUPERSEDED 2026-10-03 by a byte-level extract of the same exe** (`scripts/msgtable_extract.py`,
  sha256 `3f11ce85…1c3baa35`): the built-in table is the **KOREAN original** (3,521 of 3,970 lines
  carry cp949 Korean, all decode; 449 are ASCII). Only **354** lines equal ROenglishRE at the same
  id. The ids DO line up: 3,571 of the 3,616 differing lines have the same `%`-placeholder
  signature as the English line at that id, and decoded spot-checks are translation pairs. Where
  the 3,238 came from is unknown (the WARP output was never kept).

**Result, in frames:**
- "NO MSG" is gone: "Basic Information", the job name, "Regular Chat" / "Battle Log", and the login
  window's English labels.
- Thai chat still works: `สวัสดี ทดสอบ` typed via Kedmanee renders in the chat log line and the bubble,
  and `chatlog` row 2 is byte-identical to its cp874 encoding.
- Revert: delete the three files.

## Windows settings changed (before → after, revert)

| Setting | Before | After | Revert |
|---|---|---|---|
| System locale (non-Unicode) | en-US, ACP 1252 | th-TH, ACP 874 | `Set-WinSystemLocale en-US`, reboot |
| Time zone | US Pacific (clock read UTC-7 at 16:50 ICT; exact ID shown on screen, not transcribed) | SE Asia Standard Time (UTC+07:00) | `Set-TimeZone -Id <old id>` |
| Keyboard | "th" language with no keyboard | th + Kedmanee `041E:0000041E` | remove the tip from `Get-WinUserLanguageList`, `Set-WinUserLanguageList` |
| HKCU `Software\Gravity Soft\Ragnarok`, `\RenewSetup` | absent | our graphics values | delete both keys |
| 7-Zip 26.03 | not installed | installed | Apps → uninstall |
| RDS policies, DWMFRAMEINTERVAL | absent | **unchanged** | – |
| `C:\RO-rAthena\_downloads\RAG_SETUP_211105.exe` | 3,427,631,040 B | **deleted** (C: +3.19 GB) | re-download from `rofull.gnjoy.com` |
| UI text files in `client\data\` | absent | 3 files (see "English UI text") | delete them |
| `client\savedata\OptionInfo.lua` `WIDTH`/`HEIGHT` (2026-10-01) | 1024 / 768 | **800 / 664** (`OLD_*` kept 1024/768) | restore from `C:\RO-rAthena\_backup\2026-10-01-window\` |
| `client\savedata\OptionInfo.lua` (2026-10-02) | 800 / 664, `Window_XPos/YPos` 240 / 68 | **1296 / 759** (`OLD_*` too), **72 / 46** | restore from `C:\RO-rAthena\_backup\2026-10-02-1280x720\` |
| `client\dgVoodoo.conf` (2026-10-02) | `ExtraEnumeratedResolutions = 800x664` | `= 1296x759` | restore from the same backup |
| `client\dgVoodoo.conf` (2026-10-01) | `ExtraEnumeratedResolutions =` (empty), `FPSLimit = 0` | `ExtraEnumeratedResolutions = 800x664`, **`FPSLimit = 30`** | restore from the same backup |
| Desktop shortcut "Ragnarok Offline" + `C:\RO-rAthena\PoringLab.cmd` (2026-10-01, Batt's request) | absent | the launcher (`__COMPAT_LAYER=RunAsInvoker`, then `start /D client PoringLab.exe`) and a shortcut to it | delete both |
| PSReadLine history (2026-10-01 incident) | – | one line removed (a GM password the agent typed into a console by mistake; rotated) | – |

| Windows account `poring-lab` (2026-10-01) | – | STANDARD local user; groups Users, Remote Desktop Users, Performance Monitor Users, Event Log Readers; the RDP session runs as it | `Remove-LocalUser poring-lab` (admin); restore the RDP creds in .env |
| `C:\RO-rAthena` ACL (2026-10-01) | Batt/admins only | + `poring-lab:(OI)(CI)M` (Modify, inherited by all 72 dirs) | `icacls C:\RO-rAthena /remove poring-lab`; before-state in `_backup\2026-10-01-account\icacls_root_before.txt` |
| HKLM `…\Policies\Microsoft\Windows NT\Terminal Services` (2026-10-01) | no values (subkey `Client` only) | `AVC444ModePreferred=1`, `AVCHardwareEncodePreferred=1` (one reboot, 17:48) | `reg import C:\RO-rAthena\_backup\2026-10-01-h264\ts_policies_before.reg` after deleting both values, then reboot |
| batt's PSReadLine history | – | one line removed 2026-10-01 (a GM password typed into a console by mistake; rotated) | – |

Backups taken before the window change: `C:\RO-rAthena\_backup\2026-10-01-window\` holds
`OptionInfo.lua` (2,773 B), `dgVoodoo.conf` (21,967 B) and `gravity_hkcu.reg` (32,564 B; HKCU
`Gravity Soft` still says 800×600, which the client ignores in favour of `OptionInfo.lua`).

Tools added under `C:\RO-rAthena\_tools`: WARP, dgVoodoo2, Process Monitor, and PresentMon 2.6.0
(980,320 B, SHA-256 `b2a706bc…188f1af`, signed Intel Corporation, valid).

## Launch

Double-click **"Ragnarok Offline"** on the desktop (2026-10-01). It runs `C:\RO-rAthena\PoringLab.cmd`:

```bat
@set __COMPAT_LAYER=RunAsInvoker
@start "" /D C:\RO-rAthena\client C:\RO-rAthena\client\PoringLab.exe
```

The same thing from a PowerShell console:

```powershell
$env:__COMPAT_LAYER="RunAsInvoker"; Start-Process C:\RO-rAthena\client\PoringLab.exe -WorkingDirectory C:\RO-rAthena\client
```

## Windows account `poring-lab` (2026-10-01)

The lab's RDP session no longer uses Batt's administrator account. `.env` holds `WIN_LAB_USER` /
`WIN_LAB_PASSWORD`, and `RDP_USER` / `RDP_PASSWORD` point at them. Batt's own Windows credentials
were removed from `.env`.

- **Created** in an admin console Batt opened (UAC). The password was typed into
  `Read-Host -AsSecureString` as sensitive input (`ro_agent.py console-secret WIN_LAB_PASSWORD
  --admin`), so it never reached a command line or history.
  - `New-LocalUser poring-lab -PasswordNeverExpires -AccountNeverExpires`.
  - **Groups:** Users, Remote Desktop Users, Performance Monitor Users (typeperf), Event Log
    Readers (RdpCoreTS events 162/170).
  - **Not Administrators.**
- **Files:** Modify on `C:\RO-rAthena` only (inherited). RagnarokClassic's folder and its HKLM key
  are not writable by a standard user, which is intended. Re-compared after the switch: registry
  hashes identical, listing unchanged.
- **Per-user settings applied in its session:**
  - Thai Kedmanee (`th`, `041E:0000041E`) next to en-US;
  - clipboard history OFF and cloud clipboard OFF;
  - Widgets OFF (Settings; the `TaskbarDa` registry write is blocked by UCPD);
  - Windows Terminal `"experimental.rightClickContextMenu": true` (right-click no longer pastes;
    backup `settings.json.bak-poringlab`);
  - conhost QuickEdit OFF;
  - HKCU `Gravity Soft\Ragnarok` + `RenewSetup` imported from
    `_backup\2026-10-01-window\gravity_hkcu.reg`;
  - the "Ragnarok Offline" shortcut on its desktop (`RO_SHORTCUT=37,548`).
  - First-run prompts declined: privacy (Batt finished that screen), Edge location access ("No"),
    OneDrive Windows Backup ("No thanks").
- **Proven:**
  - shortcut launch, non-elevated;
  - agent player login as sensitive input;
  - online=1 and drawing;
  - a Thai line typed via Kedmanee: `chatlog` `CAC7D1CAB4D5` = "สวัสดี" (cp874), byte-exact;
  - the GM account, and `@where` / `@warp` / `@hide`.
- **Anything needing admin later** (policies, installs, account changes) is requested from Batt:
  he opens the elevated console and enters credentials at UAC. The agent never approves UAC, and
  its tooling refuses to.
- **Revert:**
  - in .env, set `RDP_USER`/`RDP_PASSWORD` back to Batt's account (Batt types them), then recreate
    the desktop;
  - in an admin console: `icacls C:\RO-rAthena /remove poring-lab`, then `Remove-LocalUser
    poring-lab`;
  - optionally delete `C:\Users\poring-lab`.

## Window 800×664, FPS cap 30 (2026-10-01)

> ➡️ **SUPERSEDED 2026-10-02 by a 1296×759 window = a 1:1 1280×720 client area** (next section).
> This section is kept as history; its "slightly scaled" line was never true (see the correction there).

- **Where the resolution lives:** `savedata\OptionInfo.lua` (`WIDTH`, `HEIGHT`, `OLD_*`,
  `ISFULLSCREENMODE`). HKCU `Gravity Soft\Ragnarok` `WIDTH`/`HEIGHT` (800×600) is ignored.
  - 2019+ clients force 1024×768 when the height is below 664, so 800×600 needs a new exe, which
    Smart App Control blocks. **800×664** is the smallest supported size.
  - dgVoodoo enumerates it via `ExtraEnumeratedResolutions = 800x664`.
- **The client sizes the window's *outer* frame to the configured size.**
  - At 1024×768 the client area was **1008×729** at (136,31), and its bottom ~15 px sat under the
    taskbar (the chat input was clipped).
  - At 800×664 it is **784×625 at (248,99)**, entirely above the taskbar.
  - So the game is presented slightly scaled (0.98×0.94). UI text stays readable at native
    resolution (checked by reading crops of the Basic Information window, hotkey bar and chat).
    ➡️ **WRONG, corrected 2026-10-02:** the client renders at its client-area size, 1:1. This
    line was inferred from the window arithmetic, never measured (next section).
  - No OCR engine is installed on the host, so this was a visual check.
- **Character select is laid out for ≥ 1024 px**: at 800 wide its left slot column and right info
  panel are clipped. Enter still starts the game, and the agent never needs the clipped parts.
- `GAME_REGION=248,99,784,625` in `.env` drives the black-screen detector and ro_agent.
- **Effect on delivery** (`phase0-latency.md`): none material.
  - Output stays 5.5–6.4 fps during camera rotation.
  - Windows skips ~25/s for "insufficient client resources".
  - The bottleneck is xfreerdp's decode of RemoteFX progressive ([h264-plan.md](../h264-plan.md)).
- **`FPSLimit = 30`** (dgVoodoo): outdoor A/B, output **8.5 vs 6.4 fps**, skips 21.3 vs 25.1/s,
  Xvfb p90 14 vs 10, same desktop CPU. **Kept.**
  - The minimum click hold with the cap: 20 ms and 50 ms both register 6/6. ro_agent holds 50 ms.

## Window 1296×759 = a 1:1 1280×720 client area, session 1440×900 (2026-10-02)

Batt's decision: a 1280×720 client area, **frozen for Phase 2** (docs/phase2-plan.md). Set via
`OptionInfo.lua` as before; no exe change.

- **The client renders at its CLIENT-AREA size, 1:1. Nothing is scaled** (measured 2026-10-02;
  this corrects the 800×664 section above).
  - The Select-Service dialog measures **280×198 px** at client 1264×681 and at 1280×720. A
    1296×759 → 1280×720 scale would make it 276×188. It is 280 wide at 784×625 too.
  - Text sharpness (mean |gradient| over the dialog's text) is equal within 2 % at both sizes.
  - Windows' own numbers (`GetWindowRect` / `GetClientRect`, user32 through the poring-lab
    console): window 1296×759, **client 1280×720 at (8,31)**, style `0x16C20000` (caption, no
    resize frame).
- **So `WIDTH`×`HEIGHT` = 1296×759** (the outer frame: client = outer − (16, 39)) gives exactly a
  1280×720 client with the title bar kept. ro_agent's title-bar activation works unchanged.
- **Placement:** the client reopens at its saved `Window_XPos`/`Window_YPos` (clamped to the screen)
  and saves them on exit. Set to **72/46**, so in the 1440×900 session the client area is at
  **(80,77)**: `GAME_REGION=80,77,1280,720`. The desktop icon column (x < 76) and the taskbar stay
  clear. A drag moves the window and every screen-coordinate tool with it, which is what ADR-0011's
  anchors are for.
- **Session 1440×900** (`XVFB_RESOLUTION`): the 1296×759 window plus the 48-px taskbar need more than
  800 px of height. It is 16:10 like 1280×800, so the console's fit mode letterboxes the same.
- **dgVoodoo:** only `ExtraEnumeratedResolutions = 1296x759` changed, by analogy with 800×664.
  Whether the client needs the mode enumerated was NOT tested. Everything else is as on 2026-10-01.
- **Rejected: borderless.** dgVoodoo's `WindowedAttributes = borderless` applies only to apps it
  FORCES windowed (its own conf comment: "attributes for forced windowed appearance"). Tried
  2026-10-02 with `ISFULLSCREENMODE 1` + dgVoodoo `FullScreenMode false`:
  - the window became a desktop-sized popup over the taskbar;
  - it minimised itself on every focus loss;
  - the 720-px render was stretched to 800;
  - the mouse was not remapped (clicks landed ~10 % low).

  It was reverted the same hour; the file diffs against the backup were read back.
- **Backup:** `C:\RO-rAthena\_backup\2026-10-02-1280x720\` holds `OptionInfo.lua` (2,772 B) and
  `dgVoodoo.conf` (21,975 B) as they were at 800×664.

## Agent automation (scripts/ro_agent.py) — what the client and Windows require

- **The server must be chosen within ~1–2 s of the server list arriving.** Otherwise this client
  fails with "Failed to Connect to Server", **without even dialling the char server**, and exits on
  OK.
  - Found 2026-10-01. Batt picking at 1.3 s worked; the agent picking at 2–37 s failed 9/9, by
    Enter, click and double-click alike. A 0.8 s fixed-delay pick worked every time since.
  - The login reply, the packet bytes and the accounts are identical either way, so this is a
    client-side timer.
- **Edit keys injected back-to-back in one batch are dropped** (4 of 24 Backspaces registered).
  Typed characters arrive intact (they come as `WM_CHAR`). So fields are cleared with paced
  Backspaces.
- **A freshly launched window takes its first click as activation**, and the service-select OK may
  need a second click.
- **Alt+F4 must be paced** (60 ms steps). Then it closes the client at once, with no prompt.
- **Desktop layout differs per account and per session.** The shortcut position comes from
  `RO_SHORTCUT`. The tray's ENG indicator moved (1086 → 1115 px) between two sessions of the same
  account, so the ENG check slides a template along the tray. The wallpaper turns black after an
  RDP reconnect, so recalibrate icon signatures after the first reconnect.
- **First-run popups take focus** (Edge location, OneDrive backup): every GM/chat action
  re-activates the client and verifies its active title first.
- **No Run-dialog commands.** Run-dialog PowerShell one-liners tripped Microsoft Defender:
  - `Behavior:Win32/SuspClickFix.G3` and `VirTool:Script/AmsiSuspClickfix.B`, severity 5,
    2026-10-01 11:47 and 12:36;
  - the processes were killed;
  - ClickFix is the attack that tricks users into pasting commands into Win+R, so this is the
    detection working, and **no exclusion was added**.
  - Instead: launch via the desktop shortcut; close with Alt+F4; diagnostics are typed into an
    already-open PowerShell console, found by its tab template and re-verified before typing.
- **Foreground discipline** (three slips on 2026-10-01, all caught or contained):
  1. A console covered the client: the GM password went into it, ran, and reached PSReadLine
     history. The line was removed and the password rotated.
  2. A dark-pixel heuristic took the black wallpaper for a console: Enter reached the desktop and
     raised CPU-Z's UAC prompt, which was declined.
  3. A console covered the client's title bar: camera right-drags pasted the Windows clipboard
     (Batt's test password) onto a prompt. It was not executed, and was cleared.

  The rules now in code:
  - the client is verified in front by its **active** title-bar signature (inactive scores ~30);
  - consoles by a tab template;
  - secrets are re-verified every 4 characters;
  - measurements refuse to run with a console visible.

## Server side (this repo)

- PACKETVER 20211103 and **PRE-RENEWAL** (`RATHENA_PRERE=yes`).
- tis620 end to end: the db server charset, `*_codepage`, and `chatlog.message VARBINARY(300)`.
- Thai names: `char_name_option 2`, plus `services/rathena/patches/0001-thai-trim-chars.patch`.
- Chat ground truth: `SELECT HEX(message) FROM chatlog`, decoded as cp874.
- **The GM group (group 20 "Validation", `services/rathena/conf/import/groups.yml`):**
  - `where`, `who`, `whomap`, `mapmove` (`@warp`), `mobsearch`, `monster`, `killmonster2`,
    `hide`;
  - **`alive` and `heal`, added 2026-10-04 (Batt; lab server only).** The level-1 GM (40 HP)
    was killed twice by Porings during dataset collection and lay dead behind the restart
    menu.
  - Applied by editing the file IN PLACE, then a guarded `recreate:rathena,sniffer` (the
    sniffer shares rathena's network namespace). The auto GM recover re-logged the GM in
    38 s.
  - Read back 20:23 ICT:
    - the server's `conf/import/groups.yml` sha256 equals the repo's (`68102fc4…2405`);
    - `@heal` ran ("HP and SP have already been recovered.", logged in `atcommandlog`);
    - `@alive` ran and declined ("You're not dead." / "@alive failed."). A refused
      command would have gone out as normal chat instead.
    - rAthena logs only commands that succeed, so a failed `@alive` leaves no row.
  - Every successful command lands in `atcommandlog` (`LogCommands: true`).
