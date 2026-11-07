---
doc_type: design
hypothesis: "poring-lab moves whole from VM 103 (ubuntu-docker, 192.168.1.13) to bot-server (192.168.1.228): the game server, the lab stack, the agent; a check script proves nothing was left behind; then VM 103 is cleaned of poring-lab."
status: "IN PROGRESS 2026-11-07. Batt approved the whole move ('move rathena too, and do the Windows side for me'), Docker on bot-server, and the NAS exports. Phase A DONE (19:3x ICT): every image built there (vision as the Intel image), the stack up beside VM 103's (no RDP, no stream), the RAM runtime pushed (and bot-server's logind made to keep /dev/shm), the db move rehearsed (18/18 CHECKSUM TABLE equal), the generated tables regenerated there byte-identical, the full test suite green on BOTH hosts (VM 103 4,596 / bot-server 4,597 passed, 0 failed), the prep check PASS 43 / FAIL 0 / SKIP 1 at 20:0x (the db rows wait for the cutover). Phase B (cutover) needs Batt for UAC on Windows and the Settings page; Phase C (clean VM 103) only after the final check passes. The agent of record is still ubuntu-docker's."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [bot-server-migration.md, ../operations/bot-server-handover.md, ../adr/0022-vendor-neutral-accelerators.md, ../adr/0001-single-rdp-session.md, ../adr/0019-windows-stays-clean.md]
next_action: "A cutover window with Batt (Phase B, about an hour): the UAC prompt on Windows (step 3), the Settings page entry (step 7), the gamestream-state choice (pipe copy or re-pair), gh auth login (step 10)."
title: "The cutover: poring-lab from VM 103 to bot-server"
date: 2026-11-07
owner: Batt
---

# The cutover: poring-lab from VM 103 to bot-server

## 0. Batt's decisions (2026-11-07 ~17:4x ICT)
- "Move rathena too, and please do the Windows side for me."
- "Docker on the new machine: yes, install it, set it up correctly."
- "Extend the rule so you can do NAS exports 8 and 9" (done: all three admit .228).
- "When the new machine is ready, write a script that checks the move and the completeness of
  moving poring-lab to the new machine, the agent included. The new machine has Claude Code; copy
  all the poring-lab history."
- "After the move is finished and the check passes, delete everything poring-lab on VM 103: the
  docker files, images, cache, tmp/, and the chat agent too."
- "Add the knowledge of connecting to bot-server to VM 103; the new machine does not need to
  connect back." (Done: the global CLAUDE.md section and a memory. Every copy is a push from
  VM 103.)

## 1. The inventory on VM 103 (2026-11-07 17:4x, read-only)
| What | Size | How it moves |
|---|---|---|
| the repo (tracked) | 26 MB `.git` | `git clone` from GitHub (done; `git pull` before the cutover) |
| `.env` | secrets | copied at Phase A, then `HOST_LAN_IP=192.168.1.228`; **`WIN_HOST` empty until the cutover** (else bot-server's desktop container would take the ONE Windows session: ADR-0001) |
| `settings/` (the environment set + audit, the foreground templates) | 52 KB | copied at the cutover (they change while the lab runs) |
| `state/` (the capture lock, the variant, the interlock window, the duty level) | 28 KB | copied at the cutover |
| `data/` (kb, gat, ui_anchors, weights, nametags, input logs, ...) | 462 MB | pre-copied in Phase A, re-synced at the cutover |
| `.venv`, caches | 341 MB | rebuilt there (`uv sync`), never copied |
| volume `db-data` (MariaDB: accounts, characters) | 172 MB | a consistent `mariadb-dump` at the cutover, the db stopped for writes; restored there |
| volume `captures` (+ `captures-th`) | 92 MB + 1 MB | tar stream at the cutover |
| volume `gamestream-state` (Sunshine's pairing key) | 4.6 KB | **Batt's choice:** volume to volume through a pipe (the key never lands as a file), or a fresh pairing with Sunshine's PIN |
| volume `transfer` | small | tar stream at the cutover |
| volumes `framebus`, `s2-input`, `x11-unix`, `datasets-nas` | run-time | recreated by compose |
| images (vision 10.3 GB, gamestream 1.35, desktop 0.86, rathena 0.41 + build 0.60, backend 0.42, sniffer 0.28, mariadb 0.46) | ~14.7 GB | REBUILT on bot-server from the repo (VM 103's shared disk stays out of it); vision as the Intel image (ADR-0022) |
| `/dev/shm/poring-lab-*` (detector env, kb, rathena source, sprites, route, ...) | run-time | rebuilt there (the "after a reboot" procedure) |
| `~/.cache/poring-lab` (the locale-pack guard's fingerprints, private ones too) | 180 KB | copied (mode kept) |
| `~/poring-lab-rec` | empty | nothing |
| the agent: memory, history | 5.6 GB | copied 15:08-15:14; re-synced at the cutover (`rsync --append` for the growing transcript) |
| NAS mounts | - | done on bot-server (7, 8, 9) |

## 2. Phase A: prepare bot-server (no effect on the live lab)
1. ✅ Docker with the address pools set first (17:4x ICT).
2. ✅ `.env` there (`HOST_LAN_IP=192.168.1.228`, `WIN_HOST=`, and since 18:1x
   `LAB_HOST_PROFILE=dedicated-intel`, `RENDER_GID=991`, `VISION_MAX_VRAM_FRACTION=1.0`), `data/`
   pre-copied, the fingerprints.
3. ✅ The images built there, 18:18-18:47 ICT: desktop, backend, frontend, gamestream, sniffer,
   rathena (+ its build stage), and the INTEL vision image (`Dockerfile.intel`, 11.8 GB) with its
   overlays (`compose.intel.yaml`, `compose.vision-worker.intel.yaml`; ADR-0022 Implementation).
   The sniffer needs the packet length table, which is generated, never copied: it was generated
   there (`scripts/gen_packet_tables.py`) and is byte-identical to VM 103's (sha256 0e523cc6...).
   A guarded `run:vision` saw the A380 (torch 2.15.0+xpu), OpenVINO listed `GPU`, an ultralytics
   forward ran on xpu.
4. ✅ The host profile (`scripts/host_profile.py`): bot-server is DEDICATED. guarded_build skips
   R1-R3 there and its IO guard watches nothing ("no capture service on this host"); it refuses
   if a capture service ever appears.
5. ✅ The stack started there 18:48-19:04 ICT through guarded_build (dev mode, as on VM 103): db,
   rathena, backend, desktop (Xvfb only: `WIN_HOST` empty), sniffer, frontend-dev; NOT gamestream.
   All healthy; the networks pinned 10.210.96.0/24 + 10.210.97.0/24 and the VLAN route via the
   router; rathena advertises 192.168.1.228:6121 / :5121; the sniffer's self-test PASS; the mux
   boots HUMAN. Its db is a FRESH one (the entrypoint's bootstrap): the cutover restores VM 103's
   dump over it.
6. ✅ `scripts/migration_check.py`: a fresh manifest on VM 103, `scripts/agent_sync.py` (the
   rehearsal, 19:08), `check --phase prep` on bot-server: PASS 27, FAIL 0, SKIP 1 (the db rows).
   ➡️ Grown since: the runtime rows (item 7), the generated tables (item 8): PASS 43 / FAIL 0 /
   SKIP 1 at 20:0x ICT.
8. ✅ The generated tables and the full suite: bot-server's first full run (4,576 passed, 12
   failed) found the server map caches (`poring_dataset/_generated`, build-time output like the
   packet table) never generated there: `scripts/gen_mapcache.py` there, all four byte-identical
   to VM 103's and the lock; the check compares both `_generated` trees now. 3 more failures were
   the run's launch (a shell `&` ignores SIGINT; they pass in the foreground), and the backend tests
   now pin the default host profile (bot-server's .env made 7 fail before). Then BOTH hosts green:
   VM 103 4,596 passed / 60 skipped; bot-server 4,597 passed / 59 skipped (20:10 ICT).
7. ✅ The RAM runtime on bot-server (`/dev/shm`, gone at every reboot there too), 19:15-19:20
   ICT: `scripts/runtime_sync.py` pushes `migration_check.RUNTIME` RAM to RAM (the KB, the rathena
   source, the detector's models, the GAT maps, the sprites, the calibrations, the chat guard;
   2,277 files) and builds the CPU detector's environment there with VM 103's exact package set
   (onnxruntime 1.31.1, numpy 2.5.4). The check hashes every file.
   - 🔴 **Found on the way:** bot-server's logind deleted ALL of `bot`'s `/dev/shm` whenever its
     last login session ended (the default `RemoveIPC=yes`): the first push was gone a minute
     later, and so was the Arc test's detector environment earlier. Fixed 19:17 ICT (the sandbox,
     Batt's root grant): `loginctl enable-linger bot` + `/etc/systemd/logind.conf.d/
     poring-lab-keep-shm.conf` (`RemoveIPC=no`, for the next logind start). Proven: a marker
     written by one SSH session survived its end; the check has a row for it (`Linger=yes`).
   - After a bot-server reboot: run `runtime_sync.py` again while VM 103 still has the files, or
     rebuild from the NAS (the after-reboot steps; the GRF is mounted there).

## 3. Phase B: the cutover (a window with Batt, about an hour)
The order keeps ONE Windows session (ADR-0001) and keeps VM 103's mux alive while the Windows side
still needs typing. Every Windows line is typed by the agent through VM 103's mux in ASSIST; the
elevated ones only after Batt opens the elevated console and answers UAC (the agent never does).
Times are written from `date` as they happen.

**Rehearsed already (2026-11-07):** the db move (`db_move.py`: 18 / 18 `CHECKSUM TABLE` equal, 185
rows, 19:26-19:29 ICT), the agent push (`agent_sync.py`), the RAM runtime (`runtime_sync.py`), the
prep check (PASS 43 / FAIL 0 / SKIP 1, 20:0x ICT).

1. **Freeze the game on VM 103.** Runner idle, `/health` no lease. The client closed by its own
   paced Alt+F4 (rathena saves the characters); then `scripts/dev.sh --profile sniffer stop sniffer
   rathena`.
2. **Windows, standard user** (the agent's `poring-lab shell`; each file backed up first to
   `C:\RO-rAthena\move-backup-<date>\`, changed only if the old text occurs EXACTLY as expected,
   read back by sha256). A byte-exact swap through Latin-1 (codepage 28591: one byte = one char):

        $bk = "C:\RO-rAthena\move-backup-$(Get-Date -f yyyyMMdd)"; New-Item -ItemType Directory -Force $bk | Out-Null
        $L1 = [Text.Encoding]::GetEncoding(28591)
        function Swap($f, $o, $n, $want) { $s = $L1.GetString([IO.File]::ReadAllBytes($f)); $c = ([regex]::Matches($s, [regex]::Escape($o))).Count; if ($c -ne $want) { "REFUSED $f : $c x"; return }; Copy-Item $f $bk; [IO.File]::WriteAllBytes($f, $L1.GetBytes($s.Replace($o, $n))); "{0} {1}" -f (Get-FileHash $f).Hash.Substring(0, 12), $f }

   - `data\clientinfo.xml`, `data\sclientinfo.xml` (in `C:\RO-rAthena\client\`): `>192.168.1.13<`
     -> `>192.168.1.228<`, once each.
   - The four AssistAddr lubs (`data\luafiles514\lua files\service_korea\externalsettings_kr.lub`,
     `_kr_qm`, `_kr_sak`, `_kr_sak_qm`): Lua 5.1 bytecode, so the string constant's 4-byte length
     changes with it (rathena-client.md, the account settings): `04 12 00 00 00
     "192.168.1.13:8888" 00` -> `04 13 00 00 00 "192.168.1.228:8888" 00`, once each:

        $o = -join ([char[]](4, 0x12, 0, 0, 0)) + '192.168.1.13:8888' + [char]0
        $n = -join ([char[]](4, 0x13, 0, 0, 0)) + '192.168.1.228:8888' + [char]0

   - `%USERPROFILE%\poring-lab-watch\labwatch.ps1` (the LAB-ONLY watch): `192.168.1.13` ->
     `192.168.1.228`, the count read first (read-only) and passed as `$want`; then
     `Stop-ScheduledTask 'poring-lab watch'; Start-ScheduledTask 'poring-lab watch'` and its log's
     next `alive` line.
3. **Windows, elevated** (Batt opens the console, UAC is Batt's; the agent types only these):

        Get-NetFirewallRule -Group 'poring-lab lab-only' | Get-NetFirewallAddressFilter | Set-NetFirewallAddressFilter -RemoteAddress '0.0.0.0-126.255.255.255','128.0.0.0-192.168.1.227','192.168.1.229-255.255.255.255','::2-ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff'
        $exe = 'C:\Program Files\Sunshine\sunshine.exe'; Get-NetFirewallApplicationFilter -Program $exe | Get-NetFirewallRule | Set-NetFirewallRule -RemoteAddress 192.168.1.228
        Get-NetFirewallRule -Group 'poring-lab lab-only' | % { '{0} {1} {2}' -f $_.DisplayName, $_.Enabled, (($_ | Get-NetFirewallAddressFilter).RemoteAddress -join ',') }
        Get-NetFirewallApplicationFilter -Program $exe | Get-NetFirewallRule | % { '{0} {1} {2}' -f $_.DisplayName, $_.Enabled, (($_ | Get-NetFirewallAddressFilter).RemoteAddress -join ',') }

   (The ranges are ADR-0016's with the lab host moved: everything but .228 and loopback.) Batt
   closes the console; the agent reads both back again from its standard shell.
4. **Hand the session over (never two).** VM 103: end the RDP client by its pid inside the desktop
   container and see ZERO xfreerdp3 BEFORE anything else (`supervisorctl stop rdp` alone leaves
   it running); stop gamestream, backend, frontend-dev, desktop (stop, not remove: Phase C).
5. **The data, VM 103 -> bot-server:**
   - `db_move.py dump` (VM 103's db still up), then stop VM 103's db; scp the dump; on
     bot-server stop rathena + sniffer, `db_move.py restore`, start them (guarded); delete both
     dump copies once the check's db rows pass;
   - `guarded_build.py voldump:captures=/mnt/poring-lab-datasets/archive/captures/captures-<date>.tar.gz`
     (and `captures-th`): the packet captures to the NAS archive, file count verified; bot-server's
     sniffer starts its own volume (long-term = the NAS, 2026-10-21). `transfer` is a tmpfs
     (nothing to move); `framebus`, `s2-input`, `x11-unix`, `datasets-nas` are recreated;
   - `settings/`, `state/` (the capture lock, the variant, the duty level excluded), `data/` by
     rsync; `scripts/runtime_sync.py --items-only` (the chat guard and the calibrations as they are
     now); `~/.cache/poring-lab`;
   - `gamestream-state` (Sunshine's pairing key): **Batt's choice**, volume to volume through a
     pipe (the key never lands as a file), or a fresh pairing with Sunshine's PIN;
   - the agent: `migration_check.py manifest`, copy it, then `scripts/agent_sync.py`.
6. **bot-server takes the session:** `rotate_secrets.py set WIN_HOST=192.168.1.169` (read back),
   then a guarded `recreate:desktop` (and gamestream): the RDP loop connects.
7. **Batt:** the Settings page (http://192.168.1.228:3000): the lab server's environment entry .13 ->
   .228 (a person's act: the agent never confirms environment entries); then ASSIST.
8. **The smoke** (agent): a judged screenshot; the client launched and logged in (the interlock
   green on the sniffer's attestation from .228; the UI gate; the chat window standard); `/where`;
   a short walk; a 5-min hunt on xmas_dun02 with the GPU box path (the Arc's detect server).
9. **The check:** `migration_check.py check --manifest <M> --phase final` PASS (WIN_HOST set, the
   containers up, db counts AND checksums). Then `config/environments.yaml`'s lab host -> .228
   (the seed's suggestion; the store is Batt's) and the docs, committed.
10. **GitHub:** Batt runs `gh auth login` on bot-server, so its agent can push.

**Rollback** before step 4: the backups back (the same `Swap` with old and new exchanged, or a copy
from `$bk`), the two firewall lines with .13, start VM 103's rathena + sniffer. After step 4: the
same, plus bot-server's `WIN_HOST=` empty and a recreate of its desktop, then VM 103's stack started.

## 4. Phase C: clean VM 103 (only after Phase B's check passes; Batt's order)
The poring-lab containers, images, volumes and build cache; the repo directory; `/dev/shm/poring-lab-*`;
`~/.cache/poring-lab`; `~/poring-lab-rec`; the NAS mount units (Batt's sudo); the agent's project
folder in `~/.claude`. The exact list is shown before it runs; the global CLAUDE.md keeps its
bot-server section.
