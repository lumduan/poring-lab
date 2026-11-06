---
doc_type: decision
hypothesis: null
status: GO
role: null
verdict_date: 2026-10-06
verdict_ticket: null
supersedes: null
related: [ADR-0013, ADR-0016, ADR-0009, ADR-0014, ADR-0006, ADR-0004]
next_action: "Principle in force (Batt, 2026-10-06). Part B and Part C DEFERRED (may never be built); the ADR-0013 indicator: server-side alternatives only. Watch retirement criteria ACCEPTED. Cleanup DONE 2026-10-06 (Part 1 17:31, Part 2 18:55; read back: 2 firewall rules = the 2 exes present, Sunshine backup gone). Pending: AVC policies revert at the next reboot that happens anyway; 2026-11-05 review (archive the needed _kro_exes_NEVER_RUN originals to the NAS with sha256, delete that folder, re-decide the other revert material); fix ro_agent's proof bar for the conhost admin console before the next elevated step. 2026-10-15: Smart App Control OFF (Batt; Operator changes): read back 0 at 13:40:02, the client launches again; the Sunshine restart check is Batt's at Friday's 17:00 S2 session."
---

# ADR-0019: Windows stays clean

- **Status:** ACCEPTED (Batt, 2026-10-06). It is a design principle, and it binds every later
  proposal.
- **Prompted by:** the Part B design (ADR-0013's 2026-10-06 amendment), which would have put a
  reporting channel and an HMAC key on Windows.
- ➡️ 2026-10-09: [ADR-0021](0021-external-servers.md) (PROPOSED) is the new ADR this principle
  asks for, for the known need "attest a REMOTE server that has no sniffer". It weighs the
  server-side candidates first (its section 10) and proposes a generated, operator-run,
  exe-scoped firewall script: one-time OS config, nothing running, no key, no channel, its
  read-back carried to Settings by a person. Nothing changes until Batt accepts it.
- **Related:**
  - [ADR-0013](0013-windows-status-indicator.md): the indicator, the watcher and Part B;
  - [ADR-0016](0016-environment-interlock.md): the interlock, the finder, Part C;
  - [ADR-0009](0009-console-session-capture.md) / [ADR-0014](0014-s2-primary-bot-path.md):
    Sunshine and the console path.

## Decision

Batt's words:

> **WINDOWS STAYS CLEAN.** Its only job is to run the game and stream it. No poring-lab services,
> keys or reporting channels on Windows; all intelligence and safety logic live on the bot server.
> Updating official endpoints = drag a game file onto the Settings page, occasionally.

What that allows, and what it rules out:

| On Windows | Allowed? |
|---|---|
| The game client and its one-time config (clientinfo, the AssistAddr override, data fixes) | yes |
| Sunshine and a display for it to capture (a monitor, or a virtual display driver) | yes |
| One-time OS config with nothing of ours running (an exe-scoped firewall rule, a standard account, locale) | yes |
| A poring-lab program, script, scheduled task or service that RUNS | **no** (lab-only exceptions below, each with an exit) |
| A key, token or secret of ours | **no** |
| A channel that reports from Windows to the bot server, or a listener of ours | **no** |

**Lab-only exceptions.** These exist only in OUR lab, while we run client and data experiments.
They are not part of any user setup, and each one has a way out:
- the `poring-lab watch` task (retirement criteria below);
- the agent's own shell (the "poring-lab shell" shortcut and the lines ro_agent types);
- the SYSTEM task for tscon, which exists only because the lab moves its ONE session between RDP
  and the console.

**Updating official endpoints is a drag and drop.** Drop the official client's `data.grf` on the
Settings page ("Find servers from a game file", ADR-0016) and block what it finds. Nothing on
Windows reports them.

## The rule for future needs

1. **Look for a server-side solution first:** the bot server, the network, or the pixels.
2. **Only if none works:** write a new ADR that shows why each server-side option fails, and get
   Batt's approval. Nothing is added on Windows by amending an older ADR.

The known needs, and the server-side candidates to try first. These are not decided; they are
the places to look:

| Need | Server-side candidates |
|---|---|
| Attest a REMOTE server that has no sniffer (what Part C was for) | (a) the pixels: the server name the client shows at login and server select, read by vision, checked against the Settings list; (b) the network: see the Dell's game connections from outside it, e.g. the router's state table or flow log, or route the Dell's game ports through the bot server so the existing sniffer sees them (an infra decision, Batt's); (c) for a server WE host: signed attestations from its own sniffer (ADR-0016 remote notes) |
| Map several clients to their servers | one session and one Sunshine app per client, so the mapping is per stream, on the server; or the pixels (the server name in each client) |
| Show a person at the Dell what the bot is doing (ADR-0013's indicator) | the console in a browser on a phone or tablet next to the Dell; a light or sound driven by the bot server (e.g. through Home Assistant) |

➡️ 2026-10-09: for the first row, ADR-0021 (PROPOSED) finds that none of (a)-(c) PREVENTS a
connection per exe ((a) and (b) detect after the fact, (b) by routing would capture an external
server's traffic, (c) needs a server we host). It keeps (a) as an optional `login_screen` check
and proposes the Windows-side, one-time firewall config described there.

## Consequences

- **Part B is DEFERRED.** That is ADR-0013's 2026-10-06 amendment: the watcher POSTing to
  `/ingest/client-evidence`, with an HMAC key delivered by DPAPI. Under this principle it may never
  be built. No code, test or `.env` variable for it exists (checked 2026-10-06).
- **The client-side provider is DEFERRED with it** (ADR-0016 Part C, the `client_endpoint`
  signal).
- **ADR-0013's display-only indicator** (ACCEPTED 2026-10-02, never built) is a Windows-side
  helper, so it is NOT built under this principle. **Batt agreed (2026-10-06): server-side
  alternatives only** (the candidates above).
- **ADR-0013's "agentless" context was widened twice:** by Sunshine plus the tscon task, then by
  the 2026-10-05 watcher. This ADR sets the end state: the game, its config and Sunshine.
- **The SERVER keeps all the safety logic:**
  - the interlock and the sniffer attestation;
  - the user-managed environments and the forbidden list;
  - the game-file finder;
  - the mux, the foreground gate and the frame-age guard.

## Audit of the Dell (2026-10-06)

Two sources, both read-only:
- **The repo record:** docs, ADRs and memory, swept on 2026-10-06.
- **A live read-back:** 2026-10-06 16:36–16:44, five lines typed in the agent's own standard-user
  shell. Items marked **LIVE** were seen then. The others come from the record only. Admin-only
  places cannot be read from that shell.

The PC is an **OptiPlex 3090**, Windows 11 26H2 build 26300.9457, with Smart App Control ON
(LIVE). ➡️ Batt switched SAC OFF on 2026-10-15 ("Operator changes" below; the read-back was still
pending when that entry was written).

### (1) Essential for streaming

| Item | Runs? | State |
|---|---|---|
| Sunshine 2026.914 (MSI), service `SunshineService` | yes, Automatic, LocalSystem | **LIVE** Running. Its two inbound `Sunshine` rules admit only 192.168.1.13 (**LIVE**; profile "Any", not the planned Private). One paired client (`poring-lab-gamestream`). Config: output = the VDD, `ensure_only_display`. Runbook: [sunshine-msi-replace.md](../operations/sunshine-msi-replace.md) |
| Virtual display driver "VDD by MTT" + `C:\VirtualDisplayDriver\vdd_settings.xml` | a loaded driver | **LIVE** "Virtual Display Driver" OK; the folder exists |
| The VDD-only console layout (registry-persisted) | no | record: [console-display.md](../operations/console-display.md) |

### (2) One-time client/OS config, nothing running

| Item | State |
|---|---|
| `C:\RO-rAthena\` client: WARP-patched `PoringLab.exe`, dgVoodoo2, `DATA.INI`, `clientinfo.xml`/`sclientinfo.xml` → 192.168.1.13:6900, English UI text, `OptionInfo.lua`, HKCU Gravity keys | **LIVE** folder present; recipe in [rathena-client.md](../client/rathena-client.md) |
| AssistAddr override: four `externalsettings_kr*.lub` per client → `127.0.0.1:3000` ➡️ main client since 2026-11-05: → `192.168.1.13:8888` (rAthena's web-server; the originals kept in `C:\RO-rAthena\lub-backup-20261105\`) | record (ADR-0016; thai-data-experiment.md; rathena-client.md "The account settings") |
| Equip-window placeholders: 16×16 BMPs `btn_e_change/off/on _a/b/c` in `data\texture\<ACP name>\basic_interface\`, both clients | record (memory only until now; installed 2026-10-05 evening, verified) |
| Firewall group `poring-lab lab-only`: 12 outbound Block rules, one per lab exe in both client folders | **LIVE** all 12 present and enabled. ➡️ 2 since 18:55 (cleanup Part 2, below) |
| "Ragnarok Offline" shortcut → `C:\RO-rAthena\PoringLab.cmd` | **LIVE** |
| Standard account `poring-lab` (Users, Remote Desktop Users, Performance Monitor Users, Event Log Readers); Modify on `C:\RO-rAthena` | **LIVE** the ACE `dell-3090\poring-lab: Modify` |
| System locale th-TH, time zone UTC+7, Thai keyboard; per-user settings (clipboard history off, …); 7-Zip | record ([rathena-client.md](../client/rathena-client.md) "Windows settings changed") |

### (3) Lab-only agent tooling

| Item | State |
|---|---|
| "poring-lab shell" shortcut → `wt.exe` (not elevated); the lines ro_agent types (status checks, file-check) | **LIVE** |
| `\PoringLab\PoringLab-ToConsole` (SYSTEM, on demand: tscon to the console) + `C:\Program Files\PoringLab\to-console.ps1` + `C:\ProgramData\PoringLab\to-console.log` | **LIVE** the task is Ready, run as SYSTEM; it has no trigger, so it runs only when `capture_backend.py to-console` asks |
| `C:\RO-rAthena\_tools\` (WARP, dgVoodoo2, Process Monitor, PresentMon) | record |
| `\\tsclient\transfer` (RDP drive redirection; present only while RDP is up) | record (ADR-0004) |

### (4) Running services of ours

| Item | State |
|---|---|
| Scheduled task `poring-lab watch` → `%USERPROFILE%\poring-lab-watch\labwatch.ps1` (927 B) + `watch.log` | **LIVE** Running as `poring-lab`, pid 18932. **KILLED 0** since its first line, 2026-10-05 19:29:23. Its only visible trace is a Terminal window in the taskbar |

This is the ONLY poring-lab program that runs on Windows. Sunshine and the VDD are third party,
and they are the streaming job itself.

### (5) Leftovers: cleanup CANDIDATES for Batt (nothing was removed)

➡️ **DECIDED the same day:** see "Batt's cleanup decisions" below. Part 1 removed the
first rows on 2026-10-06 at 17:31. The table is the audit as found.

| Item | Evidence | Note |
|---|---|---|
| `C:\Users\poring-lab\Downloads\Sunshine-Windows-AMD64-installer.msi` (33,710,080 B) | **LIVE** | the installer; the product is installed |
| `%TEMP%\pl-vdd-ok` (0 B, 2026-10-03) | **LIVE** | the dead-man flag from the VDD-only switch |
| `C:\RO-rAthena-th\watch.log`, `watch-main.log` (2026-10-05) | **LIVE** | logs of the old `Start-Job` watchers |
| `C:\RO-rAthena-th\` (~3.8 GB) + the "Ragnarok Offline TH" shortcut | **LIVE** | the Thai-data experiment is STOPPED; the copy is kept as an option. It has no explicit `poring-lab` ACE: it is writable through C:\'s inherited "Authenticated Users: Modify" (**LIVE**) |
| `PoringLab_s0..s3.exe` in both clients | **LIVE** (named by the firewall rules) | WARP variants Smart App Control blocked; unused |
| RDP AVC policies `AVC444ModePreferred=1`, `AVCHardwareEncodePreferred=1` (HKLM) | **LIVE** | set for the H.264 trial; the lab runs `progressive` now, so their purpose is stale. Revert needs a reboot |
| `C:\ProgramData\PoringLab\sunshine-backup-20261002\` (admin-only), incl. the OLD Sunshine `cakey.pem` | record | the only rollback of the MSI swap; a private key on disk |
| `sunshine.conf.bak-*` next to the config | record | backups from 2026-10-02/03 |
| `C:\RO-rAthena\_backup\`, `_baseline\`, `_kro_exes_NEVER_RUN\` | record | revert material; the kRO launchers were never run |

### Batt's cleanup decisions (2026-10-06)

- **REMOVE:**
  - the Sunshine installer in Downloads;
  - `%TEMP%\pl-vdd-ok`;
  - the old watcher logs;
  - the admin-only Sunshine backup (it holds the OLD `cakey.pem`, a private key no longer used);
  - `PoringLab_s0..s3.exe` in both clients;
  - `C:\RO-rAthena-th` and its shortcut (the Thai-data decision is final; rathena-th stays a
    stopped SERVER-side option).
- **Then:** the firewall group's rule list must equal the `*.exe` actually present in the client
  folder, read back. After the removals that is the 2 main-client exes, so the 10 rules for
  `PoringLab_s0..s3` and the th copy go.
- **The exact lines** were shown to Batt before anything ran:
  - the standard-shell part runs from the agent's own shell;
  - the admin part runs from Batt's elevated console, with only the agreed lines typed.
- **Part 1 DONE 2026-10-06 17:28–17:31**, from the agent's own standard shell (Batt: "run Part 1",
  and add the 7-Zip installer `C:\RO-rAthena\_downloads\7z2603-x64.exe` to S1). S1–S3 ran with
  no error. The S4 read-back:
  - `left: 0` -- the Sunshine MSI, `pl-vdd-ok`, the 7-Zip installer, `C:\RO-rAthena-th` (with its
    old watcher logs and its `PoringLab_s0..s3`) and the TH shortcut are all gone;
  - `client exes: 2021-11-03_Ragexe_1635926200.exe, PoringLab.exe`;
  - poring-lab's desktop: Edge, poring-lab shell, Ragnarok Offline.
- **Part 2 DONE 2026-10-06 18:52–18:55**, in Batt's elevated console. He opened it and stayed
  hands-off; the agent typed A1–A4 only. A4's read-back:

      rules: 2
      C:\RO-rAthena\client\2021-11-03_Ragexe_1635926200.exe exists=True enabled=True Block
      C:\RO-rAthena\client\PoringLab.exe exists=True enabled=True Block
      exes: C:\RO-rAthena\client\2021-11-03_Ragexe_1635926200.exe, C:\RO-rAthena\client\PoringLab.exe
      backup left: False

  So the Sunshine backup with the OLD `cakey.pem` is gone, and the group's rule list equals the
  `*.exe` present.
  - A tooling gap found here: ro_agent's proof bar (`cls` + a bar of a fresh width) cannot prove a
    line ran in the classic conhost "Administrator: Windows PowerShell" window. It measures cells
    at the Terminal's width, so it reported "no fresh proof bar" for every line, and A2 and A3
    drew bars of the SAME pixel width. Each line was confirmed by screenshot instead, and A4's
    read-back proved A1–A3 had all run.
  - Fix before the next elevated step: measure the bar in that window's own cell width, or open
    the elevated console as a Terminal tab.
- **Code still naming the removed copy (DECISION → CODE):**
  - ro_agent's `th` profile is kept as data but now REFUSES with the reason: its shortcut position
    would click whatever icon is there now (`removed=`, tested).
  - `labwatch.ps1` on the Dell still lists `C:\RO-rAthena-th\client` in its path filter. That
    entry is intentionally inert: nothing is there, and the watch retires on its own criteria.
- **Prechecks (2026-10-06 17:05–17:08, read-only):**
  - 0 reparse points under either client folder;
  - nothing running from them;
  - `C:\RO-rAthena-th` is 955 files, 6.62 GB (it gained `thdata.grf`);
  - the TH shortcut is on poring-lab's Desktop.
- **AVC policies + reboot DONE 2026-10-06 (Batt: "reboot now rather than waiting").**
  - R1 and R2 ran 19:30–19:31 in Batt's elevated console. It was a Terminal tab this time, so the
    proof bar worked. R2 printed nothing; the agent's standard shell then read back
    `AVC values: 0`.
  - `Restart-Computer` from the agent's standard shell at 19:44:36 (the account holds
    SeShutdownPrivilege). Boot at 19:45:13; RDP reconnected by itself at 19:45:33, with two
    connect failures while down and no auth error.
- **Post-reboot verification (read-only):**
  - Host side: the lock stayed rdp/steady at SEQ 182, with one xfreerdp; `/health` ok; the mode
    is still ASSIST.
  - Windows services: `SunshineService` Running and Automatic; the VDD OK; the tscon task Ready.
  - The watch task:
    - it was running again 7 s after the RDP logon (start at 19:45:40);
    - its principal is `poring-lab, Interactive, Limited`, so it NEEDS the logon: it cannot run
      between boot and logon;
    - KILLED 0.
  - Firewall: 2 rules, both enabled Block. `AVC values: 0`. Caps Lock off.
  - The AssistAddr lubs and the Equip BMPs hash identical to the pre-reboot baseline
    (`externalsettings_kr*.lub` 477C1E90…, 301EA6CB…, 4B62906C…, 954EB544…; 9 × FA104C1C…).
    ➡️ The lub baseline changed on 2026-11-05 14:55 (AssistAddr → 192.168.1.13:8888, Batt's
    "fix it"): `_kr` 928E109D…, `_kr_qm` 64F26B9B…, `_kr_sak` F68D83BC…, `_kr_sak_qm` C9093422…
    (each +3 bytes; the old four are the backups in `C:\RO-rAthena\lub-backup-20261105\`).
  - A watched GM login (`recover gm --retries 0`):
    - the interlock was GREEN `lab-rathena`;
    - the client's only remote was `192.168.1.13:5121`;
    - KILLED 0, and no ragnarok/gnjoy/gravity name in the DNS cache;
    - then a logout (Alt+F4): online 0.
  - NOT verifiable from the RDP session: the console layout (VDD-only). `Screen.AllScreens` in
    RDP shows the RDP display, and the standard account cannot read the GraphicsDrivers topology.
    It is checked at the next console handover (the S2 session that cuts the `@stream` template).
    - ➡️ **Checked 2026-10-07 00:38, in the clean room after training: VDD-only.**
    - The stream showed the desktop and taskbar WITH tray icons.
    - A fresh process's `Screen.AllScreens` listed ONE display: `\\.\DISPLAY4`, primary, at 0,0,
      1440×900.
  - Found and fixed: ro_agent skipped its DESKTOP window while green, so the typing-only foreground
    gate refused its own console lines (`client_not_foreground`). It opens a desktop window even
    while green now (tested); it was worked around live with `capture_backend.py window desktop`.
  Run this in an elevated console just before that reboot, then read it back:
  `Remove-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\Terminal Services' -Name AVC444ModePreferred,AVCHardwareEncodePreferred`
- **KEEP for now, and review again on 2026-11-05 (after 30 stable days):**
  - `sunshine.conf.bak-*`;
  - `_backup\`, `_baseline\`, `_kro_exes_NEVER_RUN\` (revert material).
- **Found by the precheck, then decided by Batt:**
  - `C:\RO-rAthena\_downloads\7z2603-x64.exe`, the 7-Zip installer: REMOVED with Part 1.
  - The 9 Gravity exes in `_kro_exes_NEVER_RUN\` get **NO new firewall rules** (Batt): more rules
    to maintain, against this ADR. They are never run, SAC is on, and the account is standard.
- **At the 2026-11-05 review** (Batt), for `_kro_exes_NEVER_RUN\`:
  1. Archive the originals we may need to the NAS, each with its sha256. Example: the unpatched
     2021 Ragexe, for future re-patching.
  2. Then delete the folder from the Dell.

**Not ours (seen LIVE, no lab record):**
- CPU-Z;
- "RO Dev Serv" → `RagnarokClassic\Ragnarok.exe`, the community-server client. It is Batt's and is
  never touched (ADR-0006);
- Chrome and Edge.

### Record gaps fixed or noted by this audit

| Gap | Resolution |
|---|---|
| Model "OptiPlex 3080" in the README and ADR-0001 | **LIVE: OptiPlex 3090.** README fixed; the ADR keeps its history |
| Build 26200.9457 in rathena-client.md | **LIVE: 26300.9457** (26H2) |
| Sunshine rules' profile (planned Private) | **LIVE: Any**, with remote 192.168.1.13 only |
| `C:\RO-rAthena-th` ACL not recorded | **LIVE**: inherited Authenticated Users: Modify, no explicit ACE |
| CLAUDE.md says to avoid the Equip window | the placeholders fixed it on 2026-10-05; CLAUDE.md updated |
| thai-data-experiment.md: "the main client has no such override" | superseded the same day (both clients have it); pointer added |
| ADR-0006: "Thai data.grf first" | measured: Thai first crashes the exe; Thai LAST works; pointer added |
| environments.yaml `official-ro-thai` comment: the th-exe block rule as layer 1 | that rule was removed 2026-10-06 (the exe-scoped group replaced it); comment updated |
| Smart App Control "irreversible" vs "re-enabling supported" (two docs) | not resolved: SAC is ON (LIVE), and nobody plans to switch it. ➡️ 2026-10-15: SAC refused the lab client, and Batt switched it OFF ("Operator changes" below). The re-enable question stays open (rathena-client.md: supported from 26200.8117 on, by Microsoft's FAQ) |

## Operator changes

### 2026-10-15: Smart App Control OFF (Batt)
- **The change** (Batt, at the Dell): Windows Security > App & browser control > Smart App
  Control: Off. Microsoft Defender stays on.
- **The reason:** SAC blocked the unsigned lab client. Two launches from the desktop shortcut
  (10:21, 10:28 ICT) started nothing. Code Integrity logged event 3033 at each: `cmd.exe` "attempted
  to load ...\RO-rAthena\client\PoringLab.exe that did not meet the Enterprise signing level
  requirements". Sunshine's exes are unsigned too (`Get-AuthenticodeSignature`: NotSigned), so its
  next start was at the same risk (the S2 path).
- **Correction to the reason as first stated** ("SAC's evaluation mode switched to enforcement"):
  the record shows SAC ON (enforce, state 1) since at least 2026-09-30 (rathena-client.md; this
  ADR's audit). The same exe (12,896,256 B, 2026-09-30) ran under it until 2026-10-13. SAC decides
  by per-file-hash cloud reputation, so the likely trigger is a changed reputation verdict, not a
  mode switch. Claude's first report made the mode-switch guess; it was wrong.
- **Read-back (from the agent's standard shell):**
  - 11:06 ICT: `VerifiedAndReputablePolicyState` still 1. One launch at 11:07 was refused again
    (3033 at 11:07:07).
  - 12:16:27 ICT: still 1.
  - SAC was NOT yet off at those times.
  - ➡️ Batt then switched the "Smart App Control settings" subpage. **13:40:02 ICT:
    `VerifiedAndReputablePolicyState` = 0 (OFF).**
    - One launch at 13:40:46 reached the login screen in 6 s.
    - The GM logged in at 13:41:25 (interlock green).
    - guarded_build's auto re-login after the sniffer recreate launched it again, OK (13:46:13).
    - **SAC is OFF, read back.** Sunshine's restart check is Batt's, at the start of the S2
      session on Fri 2026-10-16 17:00.
- **What it affects:** the lab client, Sunshine's next start, and any other unsigned exe on the
  PC. Batt's community client is not touched by the lab (ADR-0006).
- **Sunshine survival check:** the standard user cannot restart `SunshineService` (its ACL gives
  interactive users no start/stop right). The check is Batt's restart from his elevated console at
  a safe moment (no stream running), then a read-back from the agent's shell: service Running, the
  process up, no new 3033. A stream follows in the next S2 session.

## One-off exceptions (each by Batt's word, logged BEFORE it runs, removed and read back after)

### 2026-11-07: the teaching kit's `--bench`, once, on the lab PC
- **Batt's word** (~05:5x ICT, answering "the only Windows this side can reach is the lab PC"):
  "Lab PC, one-off". The question: does detection run faster on a PC next to the client than on
  the bot server (docs/benchmarks/cpu-detector-speed.md)?
- **What runs:** `simple_bot.py --bench --model v1.onnx` from the PUBLIC teaching-kit branch, pinned
  at commit `35851e1` (GitHub's archive zip), with uv 0.11.33 (its release zip). It reads the kit's
  20 sample pictures and times the model; it sends NO game input, opens no listener and reports
  nothing anywhere (its output is read from the screen).
- **Where:** everything in ONE folder, `$env:TEMP\pl-bench`: uv, the kit, uv's cache, its
  downloaded Python. uv's cache, Python and tool directories are pointed there by variables set in
  the agent's shell only, and nothing is added to PATH.
- **The path:** the agent's own shell (`ro_agent.py open-terminal` / `console`), through the mux.
- **The exit:** before deleting, a scan for reparse points under the folder. Then
  `Remove-Item -Recurse -Force` on it, and a read-back: the folder, `%LOCALAPPDATA%\uv` and
  `~\.local` absent (as they were before, recorded first). The shell variables are removed too.
- **Result:** appended below after it runs.

## The `poring-lab watch` task: lab-only, and its retirement criteria (ACCEPTED, Batt 2026-10-06)

**Why it exists:** the th client caught the 2021 exe calling Gravity's
`kro-assit.ragnarok.co.kr:3000` (2026-10-05). The watch kills any lab exe that reaches anything
but 192.168.1.13 or loopback, and LOGS it.

**What covers the same risk with nothing of ours running:**
- the exe-scoped firewall group (layer 1, LIVE): it blocks, silently;
- the AssistAddr override in every lab client: the known call goes to loopback;
- the server-side interlock: the bot acts only with a fresh sniffer attestation of a lab session.

**What retiring it loses:** the LOG of an attempt. The firewall blocks an attempt without telling
us, and nothing server-side sees a blocked connection today. That evidence is why the watch stays
while experiments add unknown clients and data.

**Retire it when ALL of these hold (Batt decides):**
1. **No client or data experiment is open.** No new exe, GRF, data or locale pack, or client copy
   is being tried. The th copy is decided: removed, or kept but never launched.
2. **Layer 1 covers every lab exe.** The rule group's program list equals the set of `*.exe` under
   every lab client folder, each rule enabled, Block, excluding only 192.168.1.13 and loopback.
   This is read back after the last client change.
3. **Every lab client copy has the AssistAddr override**, read back by hash.
4. **The log is quiet:** KILLED 0 for at least 14 consecutive days of normal lab use, including at
   least 10 logins through character select (where the 2021 exe makes its AssistAddr call).
   - Today: KILLED 0 since 2026-10-05 19:29 (about 21 h).
5. **The server-side interlock is unchanged:** green only on a fresh lab-session attestation.

➡️ 2026-10-09: ADR-0021 (PROPOSED) would re-word criteria 2 and 5 on acceptance: an external
environment's exes are covered by their OWN generated group (its endpoints, not 192.168.1.13),
and an external environment is green on a confirmed rule set, not an attestation. Its client copy
must live outside `C:\RO-rAthena\client\` (this watch would kill it), and adding one re-opens
criterion 1.

**Retirement:**
- Two lines from the agent's own standard shell, where the task was registered:
  `Unregister-ScheduledTask 'poring-lab watch' -Confirm:$false`, then remove
  `%USERPROFILE%\poring-lab-watch`.
- Then read back: the task and the folder are both gone.
- Then update this ADR, ADR-0013, ADR-0016, CLAUDE.md and the README in the same unit of work.
- **It can come back:** a new client experiment may re-register the watch for that experiment's
  duration, from the ADR-0013 recipe. The retirement criteria apply again at its end.

## The user-facing Windows setup

**Game client (with its one-time config) + Sunshine.** That is the whole list. The step by step
is in [docs/windows-setup.md](../windows-setup.md).
➡️ 2026-10-09: ADR-0021 (PROPOSED) would add, for an external environment only, its generated
firewall script, run by a person once per allowlist change (nothing stays running). Not part of
it:
- RDP (the lab's human admin path);
- the watch;
- the agent's shell;
- the tscon task;
- anything poring-lab runs.
