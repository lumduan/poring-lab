---
doc_type: decision
hypothesis: null
status: GO
role: null
verdict_date: 2026-10-06
verdict_ticket: null
supersedes: null
related: [ADR-0013, ADR-0016, ADR-0009, ADR-0014, ADR-0006, ADR-0004]
next_action: "Principle in force (Batt, 2026-10-06). Part B (ADR-0013's 2026-10-06 amendment) and the client-side provider (ADR-0016 Part C) are DEFERRED and may never be built. The `poring-lab watch` task is lab-only; retire it when the criteria below hold (Batt's call). The leftovers in the audit are cleanup CANDIDATES for Batt; nothing was removed."
---

# ADR-0019: Windows stays clean

- **Status:** ACCEPTED (Batt, 2026-10-06). It is a design principle, and it binds every later
  proposal.
- **Prompted by:** the Part B design (ADR-0013's 2026-10-06 amendment), which would have put a
  reporting channel and an HMAC key on Windows.
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

## Consequences

- **Part B is DEFERRED.** That is ADR-0013's 2026-10-06 amendment: the watcher POSTing to
  `/ingest/client-evidence`, with an HMAC key delivered by DPAPI. Under this principle it may never
  be built. No code, test or `.env` variable for it exists (checked 2026-10-06).
- **The client-side provider is DEFERRED with it** (ADR-0016 Part C, the `client_endpoint`
  signal).
- **ADR-0013's display-only indicator** (ACCEPTED 2026-10-02, never built) is a Windows-side
  helper, so it is NOT built under this principle. If shared control needs it, start from the
  server-side candidates above. *(Applied here by the principle's wording; Batt can say
  otherwise.)*
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
(LIVE).

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
| AssistAddr override: four `externalsettings_kr*.lub` per client → `127.0.0.1:3000` | record (ADR-0016; thai-data-experiment.md) |
| Equip-window placeholders: 16×16 BMPs `btn_e_change/off/on _a/b/c` in `data\texture\<ACP name>\basic_interface\`, both clients | record (memory only until now; installed 2026-10-05 evening, verified) |
| Firewall group `poring-lab lab-only`: 12 outbound Block rules, one per lab exe in both client folders | **LIVE** all 12 present and enabled |
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
| Smart App Control "irreversible" vs "re-enabling supported" (two docs) | not resolved: SAC is ON (LIVE), and nobody plans to switch it |

## The `poring-lab watch` task: lab-only, and its retirement criteria (PROPOSED)

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
is in [docs/windows-setup.md](../windows-setup.md). Not part of it:
- RDP (the lab's human admin path);
- the watch;
- the agent's shell;
- the tscon task;
- anything poring-lab runs.
