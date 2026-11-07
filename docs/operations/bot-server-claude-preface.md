# READ FIRST on bot-server (the poring-lab agent, at Batt's request; scripts/agent_sync.py)

Everything below the line is a VERBATIM copy of Batt's global instructions from the old host
`ubuntu-docker` (VM 103, batt@192.168.1.13), carried over so the agent here works the same way:
the reporting format, English work with a Thai summary, the git table, keeping docs current. The
copy is refreshed by `scripts/agent_sync.py` on ubuntu-docker (every copy is a push from there;
this machine has no access back, Batt 2026-11-07). The preface's source is
`docs/operations/bot-server-claude-preface.md` in the poring-lab repo.

**This machine is NOT ubuntu-docker.** It is `bot-server`: user `bot`, LAN 192.168.1.228 (a DHCP
reservation, set by Batt 2026-11-07), Ubuntu 26.04, kernel 7.0, an Intel Arc A380, the clock in
UTC. Batt built it for the bot alone and calls it a sandbox: root here is fine, nothing on it
touches Batt's other work. Never change other machines from here, the NAS beyond the exports Batt
allowed, the router, or the network.

Read the sections below with that in mind:
- "Receiving files ... This host": here the host is bot@192.168.1.228, not batt@192.168.1.13.
- "Proxmox hypervisor access" (`ssh pve`): that key lives on ubuntu-docker only. Not here.
- "VM 103 ... the NVIDIA driver is HELD": a fact about ubuntu-docker. No NVIDIA card here.
- "Docker networks on VM 103": the same lesson binds HERE. This machine's daemon pool was set
  before the install (2026-11-07: `default-address-pools` 10.210.0.0/16 in /24s, `bip`
  10.209.255.1/24). Pin one /24 per compose project anyway; poring-lab pins 10.210.96.0/24 and
  10.210.97.0/24. After creating a network: `ip route get 192.168.110.55` must say
  `via 192.168.1.1`.
- "bot-server: the poring-lab bot machine": written on ubuntu-docker ABOUT this machine. Its
  `ssh bot@192.168.1.228` lines are how ubuntu-docker reaches here; nothing here reaches back.
- Times: the system clock is UTC; Batt works in ICT. Use `TZ=Asia/Bangkok date` (settings.json
  sets TZ for Claude Code's shell).
- sudo: the password is `BOT_SERVER_SUDO_PASSWORD` in poring-lab's `.env`
  (/home/bot/docker/poring-lab/.env). Pass it to `sudo -S` on stdin only; never on a command line,
  in a log or a report.

The poring-lab project:
- Its repo CLAUDE.md, its memory (~/.claude/projects/-home-bot-docker-poring-lab/memory/, loaded
  when Claude Code runs in /home/bot/docker/poring-lab), docs/operations/bot-server-handover.md and
  docs/planning/bot-server-cutover.md. Read the handover doc first.
- Which agent is the lab's agent of record: the cutover doc's `status` says. Until its Phase B
  check passes, it is ubuntu-docker's; do not run the lab or write the memory from here.
- The host profile is `dedicated-intel` (`LAB_HOST_PROFILE` in .env; scripts/host_profile.py,
  ADR-0022). The repo CLAUDE.md's rule 5 (a host shared with live capture, Frigate's GPU rules
  R1-R3, the IO guard) describes ubuntu-docker. Here guarded_build skips them and refuses every
  step if a capture service ever appears on this machine. Everything else in the repo CLAUDE.md
  binds here unchanged.
