---
doc_type: plan
hypothesis: null
status: ACTIVE
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../setup/new-lab-host.md, ../adr/0023-learner-mode.md, ../adr/0022-vendor-neutral-accelerators.md]
next_action: "Fix A and B first (they stop a second install); then N, J, K, D, E; the stale-doc items as they are touched."
---

# What stops or trips a second installation (found writing docs/setup/new-lab-host.md)

Recorded 2026-11-12 11:19 ICT from `date`. The list comes from the manual's author, who read the repo
against a fresh install. Batt's rule of the same day applies to every fix: a user's own values live
in gitignored files (`.env`, `settings/`, `compose.override.yaml`, `data/`), never in a tracked
file, and a pull never breaks them.

| # | Gap | Effect on a new install | Status |
|---|---|---|---|
| A | The game PC's address 192.168.1.169 is hard-coded: capture.py's COMPILED BPF constants, sniffer.py's CLIENT_IP default, config/environments.yaml `windows_host` (a seed-only TECHNICAL field) | A second game PC can never be packet-attested for the lab rAthena (its presses are refused). ADR-0023's declared mode does not use it; the lab's own attested path does | OPEN (needs a BPF built from a setting; ADR-0023 decision 4) |
| B | VIEWER_NETWORKS (default 192.168.0.0/16) is not passed by compose.yaml nor in .env.example | On another LAN range the Settings writes and /ws/packets refuse | FIXED 2026-11-12: `VIEWER_NETWORKS` from .env (compose passes it, default unchanged; overlaps with our Docker subnets dropped) |
| C | The Settings seed suggests 192.168.1.228 servers | Wrong suggestion for every other host (they are added by hand) | OPEN |
| D | No `dedicated-nvidia` and no CPU-only host profile | A new NVIDIA host refuses every GPU step (shared-nvidia's R3 needs Frigate); a CPU-only host must declare dedicated-intel | OPEN |
| E | quiet_start.py ignores the host profile (10 quiet minutes, SET windows) | Contradicts "no market waits on bot-server" (Batt 11-10) | OPEN |
| F | Option A's worker still reads "NOT proven / NOT switched" in places (vision-long-lived.md heading, README, guarded_build docstring, compose.vision-worker.yaml header) | Misleads a reader | OPEN (doc) |
| G | detector-cpu.md names xmas02 (293dca92) for xmas_dun02; MAP_MODELS uses xmas02gb (b22d972b) since 11-10 | Misleads a reader | OPEN (doc) |
| H | ADR-0006's implementation table: "2 Interlock: Not built", no pointer to ADR-0016 (built 2026-10-04) | Misleads a reader | OPEN (doc) |
| I | CLAUDE.md rule 2 / ADR-0014: "S2 is the bot's primary path"; the S2 UI-gate set is unproven, today's pilots run on RDP | Misleads a reader | OPEN (doc) |
| J | Hard-coded /home/batt paths: guarded_build MEASURE_ROOTS, compose.dev.yaml S2_REC_DIR default, an .env.example comment | measure:/archive: refuse other users' paths | OPEN |
| K | Stale VM 103 address 192.168.1.13: init_env.sh HOST_LAN_IP fallback, .env.example, compose.yaml comment, windows-setup.md | A new .env starts with a wrong address | OPEN |
| L | The gpu-clock unit's install text omits copying its .sh to /usr/local/libexec | The unit fails to start | OPEN (doc) |
| M | scripts/check_gpu.py is NVIDIA-only; README's GPU check points only at it | No committed Intel device check besides a serve test | OPEN |
| N | The detect server opens EVERY GPU_WEIGHTS ONNX at start (8 files, incl. evaluation-only rounds) | A new host needs all 8 files to serve one map | OPEN (a serve-cmd model subset) |
| O | README / CLAUDE.md still show raw `docker compose up -d` / `restart desktop` lines the guard refuses | Confusing | OPEN (doc) |
| P | The interlock's accounts [2000001, 2000002] depend on RATHENA_TEST_USER at the first rathena start (upsert order) | Fragile (unverified) | OPEN |
| Q | The xmas_dun02 base flag list lives only in scratch scripts | The manual's section-10 command is composed by hand | OPEN |
