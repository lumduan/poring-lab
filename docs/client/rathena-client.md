---
doc_type: design
hypothesis: null
status: ACCUMULATING
role: null
verdict_date: 2026-09-30
verdict_ticket: null
supersedes: null
related: []
next_action: Finish Stage 4 (login, character, Thai chat line vs chatlog cp874); then decide Thai Test A vs B and the client resolution.
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
  - Windows 11 RDP gives no hardware path: the HAL and T&L devices fail with "Cannot init d3d", and
    the software RGB device draws black.
  - dgVoodoo2's `DDraw.dll` + `D3DImm.dll` translate it to D3D11, and it renders.
- **Windows (Batt, 2026-09-30):** system locale th-TH (ANSI code page 874), the Thai Kedmanee
  keyboard, time zone (UTC+07:00) Bangkok.
- **Smart App Control is On.** It blocks new unsigned exes: WARP variants other than the first
  `PoringLab.exe` were refused (Code Integrity 3033). Turning SAC off is irreversible on Windows 11,
  so it stays on.

## Launch

```powershell
$env:__COMPAT_LAYER="RunAsInvoker"; Start-Process C:\RO-rAthena\client\PoringLab.exe -WorkingDirectory C:\RO-rAthena\client
```

## Server side (this repo)

- PACKETVER 20211103 and **PRE-RENEWAL** (`RATHENA_PRERE=yes`).
- tis620 end to end: the db server charset, `*_codepage`, and `chatlog.message VARBINARY(300)`.
- Thai names: `char_name_option 2`, plus `services/rathena/patches/0001-thai-trim-chars.patch`.
- Chat ground truth: `SELECT HEX(message) FROM chatlog`, decoded as cp874.
