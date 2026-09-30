---
doc_type: design
hypothesis: null
status: ACCUMULATING
role: null
verdict_date: 2026-09-30
verdict_ticket: null
supersedes: null
related: []
next_action: Fix RDP delivery (only ~15-18 of the game's 60 fps reach Xvfb during motion; xfreerdp sw decode ~10+ cores) before dataset collection; decide the UI-text option (data-only English msgstringtable recommended).
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

Tools added under `C:\RO-rAthena\_tools`: WARP, dgVoodoo2, Process Monitor, and PresentMon 2.6.0
(980,320 B, SHA-256 `b2a706bc…188f1af`, signed Intel Corporation, valid).

## Launch

```powershell
$env:__COMPAT_LAYER="RunAsInvoker"; Start-Process C:\RO-rAthena\client\PoringLab.exe -WorkingDirectory C:\RO-rAthena\client
```

## Server side (this repo)

- PACKETVER 20211103 and **PRE-RENEWAL** (`RATHENA_PRERE=yes`).
- tis620 end to end: the db server charset, `*_codepage`, and `chatlog.message VARBINARY(300)`.
- Thai names: `char_name_option 2`, plus `services/rathena/patches/0001-thai-trim-chars.patch`.
- Chat ground truth: `SELECT HEX(message) FROM chatlog`, decoded as cp874.
