---
doc_type: design
hypothesis: "poring-lab moves whole from VM 103 (ubuntu-docker, 192.168.1.13) to bot-server (192.168.1.228): the game server, the lab stack, the agent; a check script proves nothing was left behind; then VM 103 is cleaned of poring-lab."
status: "IN PROGRESS 2026-11-07. Batt approved the whole move ('move rathena too, and do the Windows side for me'), Docker on bot-server, and the NAS exports. Phase A (prepare bot-server) under way; Phase B (cutover) needs Batt for UAC on Windows and the Settings page; Phase C (clean VM 103) only after scripts/migration_check.py passes."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [bot-server-migration.md, ../operations/bot-server-handover.md, ../adr/0022-vendor-neutral-accelerators.md, ../adr/0001-single-rdp-session.md, ../adr/0019-windows-stays-clean.md]
next_action: "Phase A: bot-server's .env (HOST_LAN_IP .228, WIN_HOST EMPTY until the cutover), the images built there, the Intel vision image + host profile, migration_check.py with a source manifest. Then a cutover window with Batt."
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
1. Docker with the address pools set first (done 17:4x).
2. `.env` there (`HOST_LAN_IP=192.168.1.228`, `WIN_HOST=`), `data/` pre-copied, the fingerprints.
3. The images built there; the Intel vision image and its compose override (`/dev/dri`, the
   render group) instead of the NVIDIA reservation (ADR-0022).
4. A host profile: bot-server is DEDICATED. No Frigate, so no R1-R3; no quant capture, so the IO
   guard has nothing to protect.
5. The stack started there WITHOUT the desktop's RDP and without the S2 stream. rathena, db,
   sniffer and backend can run beside VM 103's lab: the Windows client still points at .13.
6. `scripts/migration_check.py`: `manifest` on VM 103, `check` on bot-server.

## 3. Phase B: the cutover (a window with Batt)
1. VM 103: the runner idle, the RDP loop stopped and its client ended; the lab's containers
   stopped.
2. The final sync: db dump, captures, transfer, settings, state, data, the agent's history.
3. bot-server: `WIN_HOST` set, the full stack up.
4. **Windows** (the agent through the mux; UAC prompts are Batt's: the agent never approves
   them):
   - the client's server address (clientinfo) -> 192.168.1.228;
   - the four AssistAddr lubs -> 192.168.1.228:8888;
   - the "poring-lab lab-only" firewall group: each exe rule's allowed remote address .13 ->
     .228 (elevated);
   - Sunshine's two inbound rules -> .228 (elevated);
   - the "poring-lab watch" task checked for .13.
5. **Batt on the Settings page:** the lab server's environment entry .13 -> .228 (a person's act:
   the agent never confirms environment entries).
6. The check: `migration_check.py check` PASS; then a live smoke (login, a walk, a short hunt).
7. GitHub from bot-server: `gh auth login` by Batt, so the agent there can push.

## 4. Phase C: clean VM 103 (only after Phase B's check passes; Batt's order)
The poring-lab containers, images, volumes and build cache; the repo directory; `/dev/shm/poring-lab-*`;
`~/.cache/poring-lab`; `~/poring-lab-rec`; the NAS mount units (Batt's sudo); the agent's project
folder in `~/.claude`. The exact list is shown before it runs; the global CLAUDE.md keeps its
bot-server section.
