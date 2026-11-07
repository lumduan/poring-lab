---
doc_type: design
hypothesis: "poring-lab moves whole from VM 103 (ubuntu-docker, 192.168.1.13) to bot-server (192.168.1.228): the game server, the lab stack, the agent; a check script proves nothing was left behind; then VM 103 is cleaned of poring-lab."
status: "PHASE B DONE 2026-11-07 21:57 ICT (Batt's window 20:33-21:57): the lab RUNS ON BOT-SERVER -- the Windows session, rathena with the moved db (18/18 CHECKSUM TABLE equal at the restore), the interlock green from bot-server's own sniffer, a 5-min xmas_dun02 smoke hunt (hard bars PASS, 302/302 detections by the Arc via OpenVINO). The final check and the agent push follow (section 3a); Phase C (clean VM 103) waits for Batt's go on the shown list."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [bot-server-migration.md, ../operations/bot-server-handover.md, ../adr/0022-vendor-neutral-accelerators.md, ../adr/0001-single-rdp-session.md, ../adr/0019-windows-stays-clean.md]
next_action: "Batt: the go for Phase C (the deletion list in section 4). The agent of record is bot-server's from the final agent push (section 3a). Open: building ADR-0023's learner mode (decided by Batt the same night, not built)."
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

### 3a. As run (2026-11-07, times ICT from `date`)
The runbook above, with ONE deliberate reorder: Batt had not reached VM 103's console 16 min after
the call for the UAC, so the session was handed to bot-server FIRST and every action of Batt's
(ASSIST, the UAC, the Settings entry) happened on bot-server's console in one place. Safe because
the firewall rules found (step 2's read-only inventory: exactly 4 name the lab host) never touch
RDP; the client stayed closed until the firewall was changed.

| Time | Step |
|---|---|
| 20:33 | judged screenshot; the client closed by its own Alt+F4 (`ro_agent close`) |
| 20:34 | VM 103 rathena + sniffer stopped (the game frozen) |
| 20:38-20:46 | Windows, standard shell: read-only counts first (each lub's length-prefixed `192.168.1.13:8888` once, clientinfo / sclientinfo `>192.168.1.13<` once, labwatch.ps1 once), every enabled firewall rule naming the host (4); then the byte-exact Latin-1 swap with ORDINAL counting (.NET's culture-sensitive IndexOf can skip NULs). New sha256 prefixes: `_kr` 445315FBFFBC, `_kr_qm` B387A0217653, `_kr_sak` 3FF20052EE2E, `_kr_sak_qm` E695EC50F2D6, clientinfo / sclientinfo 4AB5CCAD4EE4, labwatch.ps1 C03F3A7856F4. Backups in `C:\RO-rAthena\move-backup-20261107\`, their hashes = the 11-05 baseline. The watch task restarted (pid 11568). |
| 20:47 | `db_move.py`: dump (6,280,911 bytes, 185 rows) -> restore on bot-server: counts AND 18/18 CHECKSUM TABLE equal |
| 20:51 | Sunshine's pairing key: `docker exec` tar, container -> SSH pipe -> container (never a file); deterministic tar digests equal (05a694da...); owner desk, modes kept |
| 21:03-21:04 | VM 103: `supervisorctl stop rdp`; the client ended by its container pid (`sh -c kill`: the desktop image has no `ps`/`kill` binary); ZERO clients by `docker top`. (A first "0" came from the missing `ps`, not a check.) VM 103's gamestream, frontend-dev, backend, desktop stopped; its db kept for the manifest |
| 21:05 | `voldump:captures` (340 files) and `captures-th` (6) to `/mnt/poring-lab-datasets/archive/captures/`, counts verified |
| 21:07 | settings / state / data / ~/.cache / the RAM runtime synced (today's input log by `--append`: bot-server's copy was a byte prefix); dry run: 0 left |
| 21:07-21:10 | bot-server `WIN_HOST=192.168.1.169` (`rotate_secrets.py set`, read back); backend, desktop, gamestream recreated; its RDP shows the Windows desktop; gamestream holding |
| 21:27-21:32 | Batt: ASSIST, the Admin terminal + UAC on bot-server's console; the agent typed 3 lines: `lab-only` ranges -> everything but .228 and loopback, Sunshine's 2 rules -> .228; read back: exactly 4 rules name the host, all .228 |
| 21:36-21:37 | Batt closed the Admin console; Settings: lab-rathena (and lab-rathena-th) .228:6900/6121/5121 confirmed, .13 removed (audited, from 192.168.110.55) |
| 21:38-21:41 | smoke: the client launched, the GM account logged in through .228 (login, char, map; the web-server's `/userconfig/load` served = the lubs work); the interlock GREEN (`lab-rathena`, AID 2000002, attested from bot-server's sniffer). `recover gm` itself stopped "never came online=1": it waits for the .env GM character while the client entered its remembered Rogue slot (VM 103 behaves the same) |
| 21:44 | a GM line (`@where`, as the Rogue through crusader.py): UI gate + chat window + server answer |
| 21:46-21:48 | the Intel vision worker (`worker:vision`); the detect server IN the worker on OpenVINO / the Arc, the pinned xmas02 ONNX from the NAS (293dca92...); immunity OFF (toggled twice: it resets at a login; judged on the answer) |
| 21:49-21:54 | `dungeon_hunt.py run ... --minutes 5 --label cutover-smoke` (p9's flags): 4 kills, 0 deaths, loot completeness 1.0, hard bars PASS (0 other-map changes, 0 NPC contacts, 0 non-monster attacks); **302 / 302 detections served by the Arc**, 0 CPU fallbacks |
| 21:57 | immunity back ON (judged), the Rogue at its rest spot prt_fild08 268,107 |

**Found on the way (fixed or recorded):**
- `host_profile.drm_pids` failed closed on ANY unreadable process of ours, and over SSH the
  sshd-session / systemd --user / sd-pam are non-dumpable: `worker:vision` said "GPU
  unverifiable". Fixed (92fa93c): only an unreadable process running our code counts.
- The OpenVINO detect server was designed as a HOST process on bot-server with the Arc test's
  venv in `~/survey`, which went with Batt's approved cleanup; no host environment there has
  OpenVINO now. It ran IN the Intel worker instead (the image has it). ➡️ SETTLED by Batt (~22:3x):
  the worker. `unit_detector.py serve-cmd --backend openvino --seconds N` prints that guarded
  step; the two pinned ONNX files live on the NAS in `archive/models/` (SHA256SUMS beside them).
- bot-server's backend stays HUMAN at a boot (by design); ASSIST is Batt's.
- Batt's design point (2026-11-07 ~21:5x): servers that permit bots but cannot be packet-verified
  (a community server, a class server a teacher hosts) can never be green today. ➡️ DECIDED by
  Batt ~22:1x: [ADR-0023](../adr/0023-learner-mode.md) learner mode (a person-declared permission,
  nothing on a learner's Windows but the remote program, the Windows host entered on the console);
  not built yet.

## 4. Phase C: clean VM 103 (only after Phase B's check passes; Batt's order)
The exact list, inventoried read-only 2026-11-07 ~22:0x ICT. Nothing here runs before Batt's go.
Deletes on VM 103's shared disk go one at a time under the IO guard (weekend / off-market).

| # | What | Size | Why it is safe |
|---|---|---|---|
| C1 | containers: sniffer, rathena, backend, gamestream, desktop, frontend-dev, vision-worker (stopped), db (still up: stopped after the final manifest) | - | the lab runs on bot-server |
| C2 | images: poring-lab/vision (10.3 GB), gamestream (1.35), desktop (0.86), rathena-build (0.60), rathena:pv20211103-prere-yes (0.41), backend (0.42), sniffer (0.28); mariadb:11.8.9 (0.46), node:24.17.0-slim (0.33) | ~15.0 GB | rebuilt on bot-server; no other project's compose / Dockerfile names the two base images (top-level files checked). NOT node:24.22.0-trixie-slim: not ours |
| C3 | volumes: db-data (moved: 18/18 CHECKSUM TABLE equal), captures + captures-th (on the NAS archive, counts verified), gamestream-state (piped, digests equal; deleting it leaves ONE copy of the pairing key, on bot-server), x11-unix; tmpfs / NFS definitions: transfer, framebus, s2-input, datasets-nas | ~0.27 GB | see each |
| C4 | networks poring-lab_default (10.210.96.0/24), poring-lab_agent (10.210.97.0/24) | - | frees the pins on VM 103 |
| C5 | build cache of the default builder | up to 31.9 GB, SHARED | other projects build with it too: Batt's judgement (all, or none) |
| C6 | /home/batt/docker/poring-lab (repo, .venv, data, .env with secrets, .claude/settings.local.json) | 1.1 GB | bot-server has the repo (git), data (checked), .env |
| C7 | /dev/shm/poring-lab-* (12 items) | ~380 MB | the run-time inputs are on bot-server (sha256-checked) |
| C8 | ~/.cache/poring-lab (fingerprints), ~/poring-lab-rec (empty), 2 stale `tail -F` watchers of old /dev/shm logs | small | copied / unused |
| C9 | the NAS automounts on VM 103 (/mnt/poring-lab-datasets, -locale-packs, -thai-src: fstab + units) | - | Batt's sudo |
| C10 | NAS exports 7, 8, 9: drop 192.168.1.13 (bot-server keeps .228) | - | the allowed midclt rule; Frigate read before/after |
| C11 | the agent: ~/.claude/projects/-home-batt-docker-poring-lab (history + memory) | ~5.7 GB | LAST, after this session ends (it writes there until then): one command for Batt, or the next VM 103 session |

**Kept:** the global CLAUDE.md's bot-server section; ~/.claude/skills (global, other projects use
them); the NAS archive copies.
