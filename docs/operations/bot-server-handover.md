---
doc_type: runbook
hypothesis: null
status: "ACTIVE. 2026-11-07 21:57 ICT: THE LAB RUNS ON BOT-SERVER (bot-server-cutover.md 3a). The agent of record is bot-server's from the final agent push of that night (agent_sync.py after the last memory write on ubuntu-docker); from then on ubuntu-docker's agent writes no memory and its project folder goes in Phase C (C11)."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../planning/bot-server-migration.md, nas-sink.md, subagent-brief.md, ../../CLAUDE.md]
next_action: "On bot-server: start Claude Code in /home/bot/docker/poring-lab; read this file, the cutover doc's 3a / 4 and the memory index first. Batt decides Phase C."
title: "Handover: the poring-lab agent's knowledge on bot-server"
date: 2026-11-07
owner: Batt
---

# Handover: the poring-lab agent's knowledge on bot-server

## 0. Batt's request (2026-11-07 ~15:0x ICT)
Batt, in Thai, translated: "Before moving, transfer the Claude Code agent's knowledge of
everything involved, e.g. the NAS connection, the summaries, talking with me in English and
summarising in Thai, including the whole poring-lab conversation history. In the future you will
move yourself to the bot server and move poring-lab there entirely. Once the GPU test passes, we
train and run at full speed without touching this machine's GPU again."

## 1. What was copied (2026-11-07 15:08-15:1x ICT, ubuntu-docker -> bot-server)
| What | From (ubuntu-docker, user batt) | To (bot-server, user bot) | Notes |
|---|---|---|---|
| Global instructions | `~/.claude/CLAUDE.md` | `/home/bot/.claude/CLAUDE.md` | Batt's text VERBATIM under a "READ FIRST on bot-server" preface: which sections describe ubuntu-docker (receiving files "this host", `ssh pve`, the NVIDIA hold, Docker networks on VM 103), the UTC clock, sudo, where the project knowledge is |
| Settings | `~/.claude/settings.json` | merged into `/home/bot/.claude/settings.json` | taken: `env` (TZ=Asia/Bangkok, retries), model, effort, auto-compact, tui. Batt's existing `theme` kept; backup `settings.json.bak-20261107`. NOT taken: the quant projects' hooks and auto-mode context, the permissions (Batt's choice there) |
| Skills | `~/.claude/skills/` | `/home/bot/.claude/skills/` | bilingual-report (the English report + Thai summary), research-doc-metadata (doc front matter), roadmap-format, craft-prompt, claude-code-restart. NOT taken: aws-infra-ops, brother-ql-printing (other projects), `synced` |
| Project memory | `~/.claude/projects/-home-batt-docker-poring-lab/memory/` (70 files) | `~/.claude/projects/-home-bot-docker-poring-lab/memory/` | loaded when Claude Code runs in `/home/bot/docker/poring-lab` (the folder name follows the repo path) |
| The conversation history | the same project folder: `5aab5193-...jsonl` (2.03 GB: the ONE poring-lab session since 2026-09-29), `5aab5193-.../subagents/` (396 files, 3.56 GB), `.../tool-results/` (1.3 MB) | the same names, beside the memory | a snapshot: the session kept growing after the copy. Paced rsync (15 MB/s) under the IO guard (> 30 % for 30 s stops it) |
| The repo | GitHub `lumduan/poring-lab` | `/home/bot/docker/poring-lab` | a clone at 83305f3 (pull it before work) |

**The copy, measured:**
- 15:08:16-15:14:28 ICT, 5,598,263,100 bytes at 15.0 MB/s;
- worst capture stall 16.6 % (Frigate), 0 s above the rule's 30 %;
- file counts equal on both sides: 396 subagent transcripts, 22 tool results, 70 memory files; the
  main transcript's snapshot is 2,032,765,816 bytes;
- rsync checks each file it sends with its own checksum. A second sha256 pass was not run: it
  would re-read 5.6 GB from the shared disk.

**Not copied, on purpose:**
- credentials: `~/.claude/.credentials.json`, `~/.claude.json` (Batt logged Claude Code in on
  bot-server themselves, 2026-11-07 ~14:39), the SSH keys (`pve`, TrueNAS root, GitHub);
- `~/.claude/history.jsonl` (every project's prompts), other projects' transcripts, caches, plans;
- the lab's secrets and run-time state: `.env`, `settings/`, `state/`, `data/`. They move at the
  cutover (bot-server-migration.md).

➡️ **2026-11-08 additions** (the C11 follow-up, bot-server-cutover.md 4a):
- **The history's final push** came from the C11 handoff at 09:36:40 ICT; VM 103's copy is
  deleted. bot-server's Claude Code cleanup (default `cleanupPeriodDays` 30) then pruned the
  session's tool-results older than 30 days: 22 at the copy above, 17 now. Batt's fix:
  - `~/.claude/settings.json` sets `cleanupPeriodDays: 365`;
  - a NAS copy at `archive/agent-history/20261108-vm103-session-5aab5193/` (489 files,
    SHA256SUMS, README).
- **`~/poring-lab-private/`** (5 files, mode 700; `__pycache__` not copied) MOVED from VM 103.
  - It holds the study-only decoder that `scripts/grf_read.py` loads for `--decode-mixcrypt`
    (never in the repo; Batt 2026-10-05).
  - The 11-07 copy and the migration check had missed it. HA (VM 103's agent) moved it on Batt's
    order: sha256 checked on bot-server, then deleted on VM 103 at 10:23:32 ICT.
  - Re-verified here, and `grf_read.load_mixcrypt()` loads it.

## 2. Where the knowledge is, and how to use it on bot-server
- **Start here:** the repo's `CLAUDE.md` (the lab's rules), the memory index (`MEMORY.md`, loaded
  automatically), `docs/planning/bot-server-migration.md` and this file.
- **The memory is the distilled history.** Prefer it. A memory names files and flags as they were
  when written: check them before relying on one.
- **The raw history** (`5aab5193-...jsonl`, 2 GB) is for looking things up, never for reading
  whole. Byte ranges only, as on ubuntu-docker (`tail -c 5000000 <file> | LC_ALL=C grep -F ...`).
  The repo's `guard_bigread` hook refuses whole-file greps of `*.jsonl` under `~/.claude` there
  too.
- **Talking with Batt:**
  - the global CLAUDE.md's "Working language", "The FINAL REPORT goes in ONE fenced code block"
    and "Git result reporting";
  - the bilingual-report skill: the English report in one fenced block, then the Thai summary with
    "(ดูข้อ N ในรายงาน)" pointers, ending with "สิ่งที่ต้องทำ / ต้องตัดสินใจ";
  - Batt answers a report inline: "// <answer>" after each numbered item;
  - they/them for Batt.
- **The NAS** (`docs/operations/nas-sink.md`):
  - TrueNAS SCALE at 192.168.1.6. Agents use `ssh root@192.168.1.6` and `midclt` only, read-only
    unless Batt approves, and read Frigate's state before and after any change.
  - That key exists on ubuntu-docker only.
  - The poring-lab NFS exports: id 7 (datasets, rw), 8 (locale-packs, rw), 9 (thai-client-data,
    ro).
  - ubuntu-docker mounts them by fstab automount (`soft,vers=4.2,timeo=150,retrans=3,noatime`).
  - bot-server has `nfs-common`. ➡️ Since 2026-11-07 15:23, export 7 (datasets) admits
    192.168.1.228. bot-server mounts it at `/mnt/poring-lab-datasets` with the same options, as an
    fstab automount (114 MB/s read; bot-server-migration.md 11). ~~Exports 8 and 9 still admit
    .13 only.~~ ➡️ SUPERSEDED ~17:4x the same day: 8 and 9 admit .228 too (Batt extended the
    rule), mounted at `/mnt/poring-locale-packs` and `/mnt/poring-thai-src`.
- **The tools:** `scripts/bot_server_sudo.sh` (a root script on bot-server, the password on
  stdin), `scripts/guarded_copy.py` (a copy under the IO guard), `scripts/agent_sync.py` (the
  agent's push: memory, history, skills, CLAUDE.md under the preface in
  `bot-server-claude-preface.md`), `scripts/migration_check.py` (manifest here, check there) and
  `scripts/host_profile.py` (`LAB_HOST_PROFILE=dedicated-intel` there, ADR-0022).
- **sudo on bot-server:**
  - the password is `BOT_SERVER_SUDO_PASSWORD` in `.env`, passed to `sudo -S` on stdin only;
  - root is fine there (Batt: a sandbox);
  - out of bounds: other machines, the NAS's configuration, the router, and network changes that
    reach beyond bot-server.

## 3. What bot-server is for now
- **Training moves there first** (Batt 2026-11-07: "move it; that is why this machine exists").
  The Arc A380 test passed (bot-server-migration.md 9).
- ~~The live lab stays on ubuntu-docker until the full move ... waits on the hardware limits~~
  ➡️ SUPERSEDED 2026-11-07 ~17:4x: Batt decided the WHOLE lab moves, rathena and the Windows side
  included, and corrected the sizing (bot-server-migration.md 12: the disk and RAM suffice with
  the NAS). The plan, its phases and their state: `docs/planning/bot-server-cutover.md`.

## 4. At the cutover
The cutover doc's Phase B is the procedure. The agent's part:
1. `python3 scripts/migration_check.py manifest --out <M>` on ubuntu-docker, copied to
   bot-server (mode 600).
2. `python3 scripts/agent_sync.py` on ubuntu-docker: the memory made identical, every transcript's
   new tail (`--append`), the skills, CLAUDE.md rebuilt (preface + Batt's text verbatim), read
   back. No memory is written between 1 and 3.
3. `python3 scripts/migration_check.py check --manifest <M> --phase final` on bot-server: PASS.
4. From then on, bot-server's memory is the record; ubuntu-docker's agent stops writing it.
Rehearsed 2026-11-07 19:08 ICT (phase prep): every agent row PASS.
