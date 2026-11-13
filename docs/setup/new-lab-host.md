---
doc_type: runbook
hypothesis: null
status: ACTIVE
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../../README.md, ../../CLAUDE.md, ../windows-setup.md, ../client/rathena-client.md, ../operations/bot-server-handover.md, ../planning/bot-server-cutover.md, ../adr/0006-sanctioned-test-environments.md, ../adr/0016-environment-interlock.md, ../adr/0019-windows-stays-clean.md, ../adr/0022-vendor-neutral-accelerators.md, ../adr/0023-learner-mode.md, ../adr/0025-run-records-sqlite.md, ../operations/detector-cpu.md]
next_action: "Batt follows it on the new machine; every step that fails or reads differently is fixed HERE in the same session. Section 4.1 grows as more host values become override or .env settings; section 11 changes when ADR-0023's declared mode is built."
title: "A second poring-lab host from scratch: Docker, the services, the Windows PC, the detector"
date: 2026-11-12
owner: Batt
---

# A second poring-lab host from scratch

This manual sets up a **second, fully independent poring-lab installation** on a new Linux
machine, with its own Windows game PC. It never touches the running bot host (bot-server,
192.168.1.228) or its Windows PC.

How to read it:
- Every step gives the command, what it does, how to check it, and what to do if it fails.
- Placeholders: `<BOT_HOST_IP>` (the new Linux machine), `<WIN_PC_IP>` (its Windows game PC),
  `<ROUTER_IP>` (your router), `<NAS_IP>` (a NAS, if you have one).
- Commands marked **(unverified)** were not run while writing this. Every other repo command was
  checked against the script's own argparse or docstring on 2026-11-12.
- The authority is the repo's `CLAUDE.md`. Where this manual and `CLAUDE.md` disagree,
  `CLAUDE.md` wins; please fix this file.

## 0. What you get, what you need

**What you get:** the same stack as bot-server, in "dev mode" (the default, `CLAUDE.md`):
- `db` + `rathena` + `sniffer`: your own rAthena game server (pre-renewal, PACKETVER 20211103)
  and its packet ground truth (offline only);
- `backend` (the input mux, the stream, the safety interlock), `desktop` (the ONE RDP session
  into Windows), `frontend-dev` (the web console on port 3000);
- `vision-worker` + the detect server (only with a GPU, section 9);
- optional: `gamestream` (the Sunshine console path), `media-rec` (GPU video recordings).

**Hardware** (the lab's own host is the reference; it runs everything below at once):

| Part | Reference (the lab's host) | Recommended for a new host |
|---|---|---|
| CPU | a server CPU, 14 cores at 2.6 GHz (since 2026-11-13; before that, 8 cores at 1.7 GHz ran everything too) | 8 cores or more. RDP decode alone takes ~4.5 cores at 30 fps (progressive) |
| RAM | 15 GiB | 16 GB minimum, 32 GB if you train. The vision worker is capped at 11 GB |
| Disk | a 128 GB SATA SSD + a NAS for long-term data | 256 GB SSD or more without a NAS. Images ~15 GB; recordings 0.84 GB/h (video) or 7-8 GB/h (PNG) |
| GPU | an entry-level Intel Arc card (8 Xe cores, 6 GB of its own memory) | Intel Arc (proven), or none (CPU detector). See section 9 for NVIDIA |
| OS | Ubuntu 26.04.1 LTS, kernel 7.0 | Ubuntu 26.04 LTS. The Intel vision image is built FROM ubuntu:26.04, and its GPU runtime must match the host's kernel driver release |

**Also needed:**
- **A Windows game PC** on the same LAN, with a fixed address (a DHCP reservation). Section 7.
- **A third computer with a browser** (e.g. a laptop). The Settings page refuses writes from the
  bot host itself and from the game PC (ADR-0016). Section 7.4.
- **The LAN:** Batt's home LAN uses 192.168.1.0/24 plus VLANs 110, 111, 112 and 120 behind the
  router. Docker must never take any 192.168.x range (section 1).
- The host user should be **uid 1000** (the first user Ubuntu creates). The containers run as
  uid 1000 and write into the repo's bind mounts.

**What is NOT in git** (and must come from your game client, from your own private copy, or be
rebuilt):

| Item | Where it lives | Where it comes from |
|---|---|---|
| `.env` (secrets, addresses) | repo root, gitignored | `scripts/init_env.sh`, then you (section 3) |
| `settings/` (the Settings page's environment set, the foreground templates) | repo, gitignored | made at the first start + your Settings-page entries |
| `state/` (the capture lock and other run-time state) | repo, gitignored | the scripts |
| `data/` (KB, maps, UI templates, calibrations, logs) | repo, gitignored | rebuilt from your client (section 8), or Batt's private copy |
| model weights (`*.pt`) and exports (`*.onnx`) | NAS `archive/models`, `archive/train`; RAM | Batt's NAS archive, or retraining (section 9) |
| packet captures | Docker volume `captures` | the sniffer; they hold login packets: never shared |
| the game client | the Windows PC | your own client copy (section 7) |
| the study-only sprite decoder | `~/poring-lab-private/` | Batt's private copy; never in git (section 8) |
| the commit guard's fingerprints | `~/.cache/poring-lab/` | Batt's private copy (section 2) |
| the packet length table, the server map caches | `packages/*/_generated/` | generated on each host (section 6) |

Copying `data/`, the weights and `~/poring-lab-private/` **privately between Batt's own
machines** is allowed. Committing or publishing any of it is not (`CLAUDE.md` rule 4).

## 1. Ubuntu and Docker, from the start

### 1.1 The Docker address pool, BEFORE Docker is installed

Why: Docker picks subnets for its networks by itself. Its fallback pools reach into 192.168.x,
and Docker cannot see the VLANs behind your router. On 2026-09-29 an automatic 192.168.96.0/20
cut Batt's MacBook off from the old lab host. Writing the pool first means the very first start of
the daemon already uses safe ranges.

Write the daemon config (the same file bot-server runs, read back 2026-11-12). Paste the block
as it is; the closing `EOF` must start its line:

```bash
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json >/dev/null <<'EOF'
{
  "default-address-pools": [{"base": "10.210.0.0/16", "size": 24}],
  "bip": "10.209.255.1/24",
  "log-driver": "json-file",
  "log-opts": {"max-size": "10m", "max-file": "3"}
}
EOF
```

- Check: `cat /etc/docker/daemon.json` prints exactly that.
- If your own LAN uses any 10.209.x or 10.210.x address, stop and choose another base first.

### 1.2 Install Docker

**Option A, what bot-server runs (proven):** Ubuntu's own packages (docker.io 29.1.3,
docker-compose-v2 2.40.3, docker-buildx 0.30.1 on bot-server).

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 docker-buildx
```

**Option B, Docker's official apt repository** (the standard commands from docs.docker.com;
**(unverified)** whether Docker's repository already carries Ubuntu 26.04's suite):

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Pick ONE option. Then:

1. Join the docker group, then log out and in again (or `newgrp docker`):

   ```bash
   sudo usermod -aG docker "$USER"
   ```

2. Check the pool is live:

   ```bash
   docker info --format '{{json .DefaultAddressPools}}'
   ```

   It must print the 10.210.0.0/16 pool. `null` means the daemon ignored daemon.json: fix the
   file, then `sudo systemctl restart docker`.
3. Check the LAN route: `ip route get 192.168.110.55` must say `via <ROUTER_IP>`, never
   `dev br-...` or `dev docker0`. (192.168.110.55 is an address on one of Batt's VLANs; on another
   network, use any address on a segment behind your router.) Repeat this check after every new
   Docker network.

**The pin rule still applies.** Every compose project pins exactly one /24 inside 10.210.0.0/16.
poring-lab's `compose.yaml` already pins `10.210.96.0/24` (default) and `10.210.97.0/24` (the
internal `agent` network). On a separate machine these are local bridges: keep them. Never create a
network without `--subnet`.

### 1.3 Keep /dev/shm across logouts

The lab's run-time inputs (map files, sprites, the CPU detector) live in `/dev/shm` (RAM).
Ubuntu's logind deletes every `/dev/shm` file a user owns when that user's last session ends
(`RemoveIPC=yes`). On bot-server this deleted a full copy a minute after it was made (2026-11-07).
The fix bot-server runs:

```bash
sudo loginctl enable-linger "$USER"
sudo mkdir -p /etc/systemd/logind.conf.d
printf '[Login]\nRemoveIPC=no\n' | sudo tee /etc/systemd/logind.conf.d/poring-lab-keep-shm.conf
```

Check: `loginctl show-user "$USER" -p Linger` prints `Linger=yes`. The drop-in takes effect at
the next logind start (a reboot). A reboot still empties `/dev/shm`: section 8 rebuilds it.

### 1.4 The NAS (optional)

Batt's NAS exports admit bot-server ONLY (since 2026-11-07). A new host needs its own export rule
on the NAS (Batt's decision, made on the NAS) or no NAS at all. bot-server's mount line, for the
shape of yours **(unverified for another NAS)**:

```bash
sudo apt-get install -y nfs-common
sudo mkdir -p /mnt/poring-lab-datasets
echo '<NAS_IP>:/<export path> /mnt/poring-lab-datasets nfs _netdev,nofail,x-systemd.automount,x-systemd.idle-timeout=600,x-systemd.mount-timeout=30,nfsvers=4.2,soft,timeo=150,retrans=3,noatime,rw 0 0' | sudo tee -a /etc/fstab
sudo systemctl daemon-reload
ls /mnt/poring-lab-datasets
```

The vision worker mounts the NAS separately, as a Docker volume (section 4.1).

## 2. The code

1. Install uv (Astral's standard installer), then clone:

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   mkdir -p ~/docker && cd ~/docker
   git clone https://github.com/lumduan/poring-lab.git
   cd poring-lab
   ```

2. The host environment (poring_env, the backend, the tools; no torch):

   ```bash
   uv sync
   ```

   Check: `uv run python -c "import poring_env"` prints nothing and exits 0.
3. Enable the commit guard, once per clone:

   ```bash
   git config core.hooksPath .githooks
   git config --get core.hooksPath     # prints .githooks
   ```

   The pre-commit hook refuses client assets (GRF, GAT, SPR, lub, ...), locale packs, the private
   decoder, and any quoted string whose fingerprint is in `~/.cache/poring-lab/`. Without Batt's
   fingerprint files there it still refuses paths, but cannot recognise pack strings: copy
   `~/.cache/poring-lab/` privately from Batt's own copy if you will commit from this machine.
4. Agent sessions (Claude Code) in this repo also get three PreToolUse hooks from
   `.claude/settings.json`: raw docker refused, whole-file reads of big files refused, filesystem
   walks outside the repo refused. A human shell is not affected.
5. The disk-light test run (`CLAUDE.md`, Commands):

   ```bash
   export PYTHONDONTWRITEBYTECODE=1 TMPDIR=/dev/shm/poring-lab-tmp && mkdir -p "$TMPDIR"
   uv run pytest -p no:cacheprovider --basetemp="$TMPDIR/pytest"
   uv run ruff check --no-cache . && uv run ruff format --check --no-cache .
   uv run mypy --cache-dir=/dev/null
   ```

   Before section 6's generated tables exist, some tests fail because the tables are missing
   (bot-server's first run: 12 failures, 9 of them the map caches). Re-run after section 6.

## 3. `.env`

1. Create it (never overwrites an existing one; mode 600):

   ```bash
   scripts/init_env.sh
   ```

   It detects `HOST_LAN_IP` from the default route and fills every empty secret with a random
   value: the database, the inter-server account, and the test, agent and GM game accounts.
2. Check `HOST_LAN_IP` is `<BOT_HOST_IP>`. If not:
   `uv run python scripts/rotate_secrets.py set HOST_LAN_IP=<BOT_HOST_IP>`.
3. Set the host profile (section 5) and the Intel render group, if you have an Arc:

   ```bash
   getent group render                 # the third field is the gid, e.g. 991
   uv run python scripts/rotate_secrets.py set LAB_HOST_PROFILE=dedicated-intel RENDER_GID=<gid> VISION_MAX_VRAM_FRACTION=1.0
   ```

   With an NVIDIA card of the lab's own instead (no render group):
   `uv run python scripts/rotate_secrets.py set LAB_HOST_PROFILE=dedicated-nvidia VISION_MAX_VRAM_FRACTION=1.0`.

4. rAthena's web-server (the client's account settings, section 7.1):
   `uv run python scripts/rotate_secrets.py set RATHENA_WEB_SERVER=true`.
5. The Windows side comes later (section 7.3): `WIN_HOST` stays EMPTY until the game PC is ready.
   With `WIN_HOST` empty the desktop runs Xvfb only and never connects.

**The variables a new host must look at:**

| Variable | Set by | Note |
|---|---|---|
| `HOST_LAN_IP` | init_env.sh | rathena ADVERTISES it to clients as the char/map address. Never put it in rAthena's `bind_ip` |
| `LAB_HOST_PROFILE`, `RENDER_GID`, `VISION_MAX_VRAM_FRACTION` | you (`set`) | section 5 |
| `WIN_HOST`, `RDP_CERT_SHA256`, `GAME_REGION`, `RO_SHORTCUT`, `SHELL_SHORTCUT`, `RO_TRAY_LANG` | you (`set`), section 7 | non-secret |
| `WIN_LAB_USER`, `RDP_USER`, `RDP_PASSWORD`, `RDP_DOMAIN` | you, in a text editor | `set` refuses names that look secret (`_USER`, `PASSWORD`) |
| `WIN_LAB_PASSWORD` | `rotate_secrets.py rotate WIN_LAB_PASSWORD` | generated; the Windows account gets the same password (section 7.2) |
| `RATHENA_SERVER_USER` / `_PASSWORD` | init_env.sh | at most 23 characters: char and map truncate to 24-byte buffers |
| `RATHENA_WEB_SERVER` | you (`set`) | `true` for the client's account settings |
| `S2_REC_DIR` | you (`set`), console path only | empty means `/home/batt/poring-lab-rec/.s2-h264`: set it to your own home's path |
| `FRONTEND_ORIGINS` | leave empty | empty means `http://<BOT_HOST_IP>:3000` |

**Rules:**
- Never commit `.env`; never paste a password on a command line or into chat.
- Secrets are generated with `rotate_secrets.py rotate NAME` (it prints names only, never values,
  and reads the file back). Non-secret settings use `rotate_secrets.py set NAME=value`.
- After writing `.env`, a running container keeps its old values until it is recreated (section
  6).

## 4. Your configuration and git pull

Batt (2026-11-12): each user may use different servers and settings, and pulling the lab's updates
must never overwrite them. Everything that belongs to YOUR machine lives outside git:

| What | Where | What a `git pull` does to it |
|---|---|---|
| `.env` | repo root, gitignored | nothing. `.env.example` is the template: never edit it. When a pull adds a variable to `.env.example`, add it to your `.env` yourself |
| `settings/` | repo, gitignored | nothing (see below) |
| `state/`, `data/` | repo, gitignored | nothing |
| `compose.override.yaml` | repo root, gitignored | nothing (section 4.1) |
| Docker volumes (`db-data`, `captures`, `gamestream-state`) | Docker | nothing |
| `~/.cache/poring-lab`, `~/poring-lab-private`, `/dev/shm/poring-lab-*` | outside the repo | nothing |

**The Settings page's environment set** (`settings/environments.json`):
- It is seeded ONCE, into an empty store, from the shipped `config/environments.yaml`. The marker
  `settings/.environments-seeded` records that (`services/backend/src/poring_backend/envstore.py`).
- After the seed the store is the ONLY source. A pull that changes `config/environments.yaml`
  never touches an existing store.
- Servers are added and removed only on the Settings page, by a person (section 7.4).

**Pull safely:**
1. `git status` must show nothing to commit (gitignored files never show there).
2. `git pull`.
3. Then, as the change needs it: `uv sync` (if `uv.lock` changed); a guarded `restart:backend@30`
   (backend code); `recreate:sniffer@120` (`packages/poring_packets` code); `recreate:rathena@240`
   (its entrypoint or conf templates); a guarded `build:<svc>` (an image's dependencies).
4. Never run `git clean -x` or `-X`: they delete gitignored files, i.e. your `.env`, `data/`
   (with your run records, `data/econ/lab.sqlite`, section 10.1) and `settings/`.

Do not edit `compose.yaml` or `config/*.yaml` for your machine. A pull would conflict with your
edit, or silently replace it.

### 4.1 Host-specific values

A machine's own compose values go in Docker's standard `compose.override.yaml` at the repo root.
It is gitignored. Docker loads it last by itself when no `-f` is given, and `scripts/dev.sh`,
`scripts/guarded_build.py` (`local_override()`) and `scripts/verify_mount.py` add it LAST to their
`-f` lists (merged on main as 30ee5a4e). Values that `.env.example` already lists stay in `.env`.

**Example 1, the NAS volume** (another NAS than Batt's; checked by the maintainer with
`docker compose ... config --no-interpolate`):

```yaml
volumes:
  datasets-nas:
    driver_opts:
      type: nfs
      o: addr=<NAS_IP>,nfsvers=4.2,ro,soft
      device: ":/<export path>"
```

**Example 2, another GPU render node for vision** (devices merge by target; checked the same way):

```yaml
services:
  vision:
    devices:
      - /dev/dri/renderD129:/dev/dri/renderD128
```

**No NAS at all, a local folder instead** (standard Docker local-volume bind options;
**(unverified)** here):

```yaml
volumes:
  datasets-nas:
    driver_opts:
      type: none
      o: bind
      device: /srv/poring-lab-datasets
```

**A LAN outside 192.168.0.0/16:** set `VIEWER_NETWORKS` in your `.env` (since 2026-11-12;
`.env.example` lists it), e.g. `VIEWER_NETWORKS=10.0.1.0/24`. Settings-page writes and the packet
viewer accept only browsers on these networks (comma-separated CIDRs; default `192.168.0.0/16`). An
entry that overlaps the lab's own Docker subnets is dropped with a warning in the backend's log,
never admitted. Recreate the backend after changing it (a guarded `recreate:backend`).

Notes:
- Docker fixes a named volume's options when the volume is first created. Write the override
  BEFORE the first start of the vision worker; a change later needs the volume removed first.
- After writing the override: `scripts/dev.sh config -q` (read-only) must print nothing.

## 5. The host profile (ADR-0022)

A host profile tells the guards what this machine has (`scripts/host_profile.py`, chosen by
`LAB_HOST_PROFILE` in `.env`). Unset means `shared-nvidia`, the strict one.

| Profile | For | What it switches |
|---|---|---|
| `shared-nvidia` | the old VM 103: an NVIDIA GPU beside Frigate and Ollama, a disk beside live quant capture | GPU sharing rules R1-R3 (they need Frigate's stats), the IO guard on capture cgroups, SET-hour gates for shipping, a 100 GB recorder floor; the CUDA vision image |
| `dedicated-intel` | bot-server: an Intel Arc card, nothing else on the machine | no R1-R3, the IO guard watches nothing, no market gates, a 30 GB recorder floor; the Intel vision image (`compose.intel.yaml`, `compose.vision-worker.intel.yaml`: the render node, `PORING_ACCEL=xpu`, the worker capped at 11 GB) |
| `dedicated-nvidia` | a new machine whose NVIDIA card is the lab's alone (ADR-0022 Amendment 2026-11-12). Never VM 103 | the same dedicated rules as `dedicated-intel` (no R1-R3, the IO guard watches nothing, no market gates, a 30 GB recorder floor); the CUDA vision image and the NVIDIA reservation of `shared-nvidia`, GPU processes listed with `nvidia-smi`. Its overlays (`compose.nvidia.yaml`, `compose.vision-worker.nvidia.yaml`) change only the VRAM cap's default, 0.25 -> 1.0; the worker stays capped at 6 GB |

**Which to choose:**
- **An Intel Arc machine used only by the lab:** `dedicated-intel`.
- **A machine with no GPU, used only by the lab:** `dedicated-intel` too, and never start vision
  or the worker there (they need the render node). There is no CPU-only profile yet
  (docs/planning/second-install-gaps.md D); the default `shared-nvidia` would apply the old VM's
  market gates and its 100 GB floor.
- **An NVIDIA machine used only by the lab:** `dedicated-nvidia` (since 2026-11-12). Set
  `VISION_MAX_VRAM_FRACTION=1.0` in `.env` too (section 3): a value there wins over the overlay's
  default, and `.env.example` carries the old VM's 0.25. Never `shared-nvidia` on a new machine:
  it refuses every GPU step without a Frigate baseline (R3 fails closed).
- guarded_build refuses EVERY step on a host declared dedicated where a capture service (quant,
  Frigate) runs. That is intended: the declaration would be wrong.

**For the Intel GPU (once):**

```bash
sudo usermod -aG render,video "$USER"
lspci -k | grep -A3 -i vga          # the Arc with "Kernel driver in use: i915"
ls -l /dev/dri/renderD128
sudo apt-get install -y intel-opencl-icd libze-intel-gpu1 libze1 clinfo intel-gpu-tools
clinfo -l                            # lists the Arc
```

The host packages are for host-side checks only; the vision image carries its own runtime. Log out
and in after the group change.

**For an NVIDIA GPU (once; every step here is (unverified) on a dedicated host: the NVIDIA path ran
only on the old VM 103):**
- The NVIDIA driver, release **580 or newer**. The vision image is CUDA 13.0 (torch
  `2.14.0+cu130`, the build with sm_120 kernels for the newest NVIDIA cards); a CUDA 13.2 image refuses to start
  on an R580 driver. `nvidia-smi` on the host must list the card and a `Driver Version: 580.` or
  newer.
- The **NVIDIA Container Toolkit**, so that compose's `driver: nvidia` reservation works:
  install it from NVIDIA's own instructions, then `sudo nvidia-ctk runtime configure
  --runtime=docker` and restart Docker. That command edits `/etc/docker/daemon.json`: afterwards
  check that the address pool of section 1.1 is still there
  (`docker info --format '{{json .DefaultAddressPools}}'` must not print `null`).
- Then build the CUDA image (`build:vision`, section 6) and check the card from inside it:

  ```bash
  python3 scripts/guarded_build.py 'run:vision@600=python scripts/check_gpu.py'
  ```

  It checks that torch sees the card, the VRAM cap, that the build has the card's sm_ kernels, and
  that matmul + conv2d run.
- **Training needs more worker memory (Batt 2026-11-12: "write it in the docs").**
  - The vision worker is capped at **6 GB** (`compose.vision-worker.yaml`: `mem_limit` ==
    `memswap_limit`, no swap). That is enough to SERVE detections.
  - On bot-server the trainer's data-loader workers were OOM-killed at 6 GB
    (bot-server-migration.md 17a). The Intel overlay gives bot-server's worker 11 GB for that
    reason. The NVIDIA overlay keeps 6 GB, so a dedicated-NVIDIA host that TRAINS will most likely
    hit the same.
  - Raise it for your machine in `compose.override.yaml` (never in a tracked file), keeping the two
    values equal, then restart the worker (`worker-stop:vision`, `worker:vision`):

    ```yaml
    services:
      vision-worker:
        mem_limit: 12g
        memswap_limit: 12g
    ```

  - Pick a value that leaves the host room: the backend, desktop and the runner need ~4-6 GB, so a
    16 GB machine can give the worker ~8-10 GB, a 32 GB one 12-16 GB (unverified on an NVIDIA
    host).

## 6. Starting the services

**The rule:** every create, start, restart, recreate, build and pull goes through
`scripts/guarded_build.py`, one step at a time. `scripts/dev.sh` refuses those verbs unless the
guard is its parent. Read-only commands (`ps`, `logs`, `exec`, `config --no-interpolate`) and
`stop` go through `scripts/dev.sh` directly. On a dedicated host the IO guard watches nothing, so
the guard costs nothing; the `--sustain 30 --spike 25` flags seen in other docs matter only on a
shared host.

**Step syntax** (from the guard's docstring): `build:<svc>`, `pull:<svc>`,
`target:<svc>:<stage>:<image>`, `tables`, `start:<svc>[,<svc>...][@<seconds>]`,
`restart:...`, `recreate:...`, `rm:...`, `run:vision@<s>=<cmd>`, `worker:vision@<s>`,
`execdev:vision@<s>=<cmd>`, `worker-stop:vision`. Logs go to `$TMPDIR/poring-guarded-*.log`.
Exit 0 only when every step completed.

1. **Build the images** (one at a time; the vision image is ~12 GB, skip it without a GPU):

   ```bash
   python3 scripts/guarded_build.py build:rathena pull:db build:backend build:desktop
   python3 scripts/guarded_build.py target:rathena:build:poring-lab/rathena-build:local
   ```

2. **Generate the build-time tables** (from pinned rAthena / OpenKore sources; never committed,
   never copied: each host makes its own):

   ```bash
   python3 scripts/guarded_build.py tables
   uv run python scripts/gen_mapcache.py
   ```

   Check: both end without a lock mismatch. bot-server's tables were byte-identical to VM 103's.
3. **The sniffer image** (it refuses to build without the exact length table):

   ```bash
   python3 scripts/guarded_build.py build:sniffer
   ```

4. **Optional images:** `build:gamestream` (the console path, section 7.5) and, with a GPU,
   `build:vision`: the Intel image with `dedicated-intel` (the profile adds its overlay), the CUDA
   image with `dedicated-nvidia`.
5. **The game server first:**

   ```bash
   python3 scripts/guarded_build.py start:db@120 start:rathena@240
   scripts/smoke_test.sh --core
   ```

   `--core` checks db + rathena health, the LAN ports, the advertised IP and the tis620 database.
   It must print `SMOKE TEST (--core) PASSED`.
6. **The capture lock, then the rest** (the lock decides who owns the one Windows session):

   ```bash
   uv run python scripts/capture_backend.py init
   python3 scripts/guarded_build.py start:backend,desktop@90
   python3 scripts/guarded_build.py start:sniffer@120
   python3 scripts/guarded_build.py start:frontend-dev@120
   ```

   `start:sniffer` refuses an uncommitted `packages/poring_packets` and records the commit. The
   sniffer's start-time self-test must pass or it does not start.
7. **Check:**
   - `scripts/dev.sh ps`: every started service up (healthy where it has a check).
   - `curl -s http://<BOT_HOST_IP>:8000/health`: answers JSON.
   - Open `http://<BOT_HOST_IP>:3000` from your laptop: the console, mode badge HUMAN. The mux
     always boots HUMAN; only a person sets ASSIST or BOT.
   - `ip route get 192.168.110.55`: still `via <ROUTER_IP>`.
   - `uv run python scripts/capture_backend.py status`: host file, containers and `/health` agree.
8. **If it fails:** `scripts/dev.sh logs <svc>`, then section 13. The rathena build's rapidyaml
   race: `RATHENA_MAKE_JOBS=1` in `.env`, rebuild.

**Game accounts:** at every rathena start the entrypoint upserts the test, agent and GM accounts
from `.env`, in that order. On a fresh database that gives them 2000000, 2000001, 2000002
**(unverified on a new host; derived from the order)**. The interlock's shipped seed expects the
agent at 2000001 and the GM at 2000002, so keep the test account set at the first start.

## 7. The Windows game PC

The PC's one job is to run the game and stream it ([ADR-0019](../adr/0019-windows-stays-clean.md),
"Windows stays clean"). The user-facing list is [docs/windows-setup.md](../windows-setup.md); the
lab's full client recipe is [docs/client/rathena-client.md](../client/rathena-client.md).

> **Known limit TODAY: the game PC's address.** The sniffer's kernel filter is compiled for the
> client address 192.168.1.169 (`packages/poring_packets/src/poring_packets/capture.py`), and the
> interlock's shipped seed names the same address as the lab environment's Windows host
> (`windows_host`, a technical field taken from the seed only; the Settings page cannot change
> it). The bot can act only while BOTH match the game PC (ADR-0016 signals `lab_host` and
> `session`).
> - On a separate network, a DHCP reservation of 192.168.1.169 for the new game PC matches what
>   the code expects today.
> - On Batt's current LAN, 192.168.1.169 is the running lab's game PC. A second game PC there gets
>   another address, and then the human can play but every bot press is refused
>   (`environment_unattested`) until the Windows host becomes a setting (ADR-0023 decision 4;
>   docs/planning/endpoints-as-config.md C7). Do not edit code or config to get around it.

### 7.1 The client copy

1. A **separate** client folder, e.g. `C:\RO-<name>\`. Never patch, repoint or reuse another
   client in place; a community-server client is never touched (ADR-0006).
2. The lab's client: the 2021-11-03 exe (matches `PACKETVER=20211103`) with kRO data,
   WARP-patched, dgVoodoo2 (Direct3D under RDP), `DATA.INI` and the HKCU settings. Recipe:
   rathena-client.md.
3. `data\clientinfo.xml` and `data\sclientinfo.xml`: your server, `<BOT_HOST_IP>` port 6900.
4. The AssistAddr override BEFORE the first login: the four loose
   `data\luafiles514\lua files\service_korea\externalsettings_kr*.lub` files point the client's
   account-settings address at `<BOT_HOST_IP>:8888` (rAthena's web-server,
   `RATHENA_WEB_SERVER=true`). These are Lua bytecode: the string's 4-byte length changes with
   the address (rathena-client.md, "The account settings"; the byte-exact swap the cutover used is
   in docs/planning/bot-server-cutover.md step 2).
5. The Equip-window placeholder textures (the kRO data lacks them; without them modal boxes stop
   the game loop): rathena-client.md.
6. Smart App Control: the lab's setting is OFF (Batt, 2026-10-15; Defender stays on). Read it
   back as a standard user:
   `(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy').VerifiedAndReputablePolicyState`
   (0 = off). A launch that starts nothing: read `Microsoft-Windows-CodeIntegrity/Operational`.
7. A desktop shortcut that launches the client non-elevated (the lab's is named
   Ragnarok Offline).

### 7.2 The Windows account and OS settings

1. A dedicated **standard** account (the lab's is `poring-lab`): Users, Remote Desktop Users,
   Performance Monitor Users, Event Log Readers. Not an administrator. Modify on the client folder
   only.
2. Its password: generate it on the bot host with
   `uv run python scripts/rotate_secrets.py rotate WIN_LAB_PASSWORD`, read it from `.env`
   yourself, and type it when you create the account. Put the same account in `WIN_LAB_USER` /
   `RDP_USER` and the same password in `RDP_PASSWORD`, editing `.env` in a text editor.
3. Remote Desktop on; sleep, the screen lock and the screensaver off (a locked session shows the
   lock screen to the bot).
4. A DHCP reservation for the PC: `<WIN_PC_IP>` (read the known limit above first).
5. **The exe-scoped outbound firewall rule** (recommended; an administrator applies it, never
   OS-wide, never on another client). One Block rule per client exe, to every address except the
   bot host and loopback (Block wins over the default Allow). The shape ADR-0016 uses, with your
   addresses **(unverified as written: compute the two middle ranges around `<BOT_HOST_IP>`)**:

   ```powershell
   $exe = 'C:\RO-<name>\client\PoringLab.exe'
   New-NetFirewallRule -Group 'poring-lab lab-only' -DisplayName 'lab client: bot host only' `
     -Direction Outbound -Program $exe -Action Block `
     -RemoteAddress '0.0.0.0-126.255.255.255','128.0.0.0-<BOT_HOST_IP minus 1>','<BOT_HOST_IP plus 1>-255.255.255.255','::2-ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff'
   Get-NetFirewallRule -Group 'poring-lab lab-only' | Format-Table DisplayName, Enabled, Direction, Action
   ```

   Undo: `Remove-NetFirewallRule -Group 'poring-lab lab-only'`.
6. **Never install on the game PC for poring-lab:** a program, script or task that runs; keys or
   tokens; a reporting channel; another remote-desktop or streaming tool; antivirus exclusions.
   The lab-only pieces on Batt's PC (the watch task, the agent's shell shortcut, the tscon task)
   are listed with their exits in ADR-0019; a new install does not need them to play.

### 7.3 Connect the bot host (RDP)

Today's xmas_dun02 pilots run on the RDP path (their recordings are named `...-rdp-hunt-...`).

1. Pin the certificate (a pre-auth handshake only; it never logs in):

   ```bash
   python3 scripts/rdp_cert_fingerprint.py <WIN_PC_IP>
   uv run python scripts/rotate_secrets.py set RDP_CERT_SHA256=<the printed hex>
   ```

2. The address: `uv run python scripts/rotate_secrets.py set WIN_HOST=<WIN_PC_IP>`.
3. **One session only (ADR-0001):** connecting takes the Windows console and logs out whoever is
   there. Never run `mstsc` or another client against the PC while the stack runs.
4. Apply: `python3 scripts/guarded_build.py recreate:backend,desktop@90`.
5. Check: the console shows the Windows desktop; `scripts/dev.sh logs desktop` shows the connect
   line. Exit 5 = someone else took the session (it backs off 10 minutes); 132-159 = an
   authentication failure (it stops retrying: fix `.env`, recreate).
6. Launch the client in the session (the 1296 x 759 window = a 1:1 1280 x 720 client area in the
   1440 x 900 session), then set `GAME_REGION` (`x,y,w,h` of the client area) and `RO_SHORTCUT`
   with `rotate_secrets.py set`, and recreate the backend.

### 7.4 The Settings page and ASSIST (a person's acts)

1. From your **laptop** (not the bot host, not the game PC), open
   `http://<BOT_HOST_IP>:3000/settings`.
2. Lab rAthena: add your servers `<BOT_HOST_IP>` ports 6900, 6121 and 5121 and confirm them (the
   shipped suggestions name bot-server's address; do not confirm those). "Saved and checked" means
   the store was written and read back.
3. Back in the console: switch the mode to ASSIST. Only a person does this; the agent never
   confirms environment entries and never sets the mode.
4. Log in with the GM account, then check `/health` `environment`: green only with a fresh
   sniffer attestation of a lab account's live session from the game PC (and the known limit
   above).

### 7.5 Sunshine and the console path (optional)

The S2 console stream (Sunshine on the PC, the `gamestream` client here) is designed as the bot's
primary path (ADR-0014). Today the UI gate's S2 template set is NOT proven
(docs/operations/s2-gate-templates.md: one attempt, nothing cut), so on that path every typed line
is refused. Use RDP until it is proven. If you set it up anyway:
- the signed Sunshine MSI (docs/operations/sunshine-msi-replace.md); pair ONLY this bot host:
  `uv run python scripts/capture_backend.py pair <PIN>`;
- Sunshine's inbound firewall rules admit only `<BOT_HOST_IP>`; its web UI stays PC-only;
- a VDD-only display layout (docs/operations/console-display.md).

## 8. Client-derived data, rebuilt locally per client

Everything below comes from YOUR client's files or screen and is gitignored. **Templates cut
from one client build fit only that build**: a different exe, data, resolution, skin or path
(RDP vs S2) needs fresh cuts. You may copy Batt's `data/` privately instead, but then the client
copy must be the same build and layout.

The map and sprite files are read from a client GRF. The lab reads the Thai client's `data.grf`
(read-only on the NAS, `/mnt/poring-thai-src/ro_thai/data.grf`) because the lab's maps and sprites
are byte-identical to kRO there (docs/thai-data-experiment.md). Use your own client's GRF path.

| Item | Command (verified flags) | Lands in |
|---|---|---|
| packet length table, server map caches | section 6 step 2 | `packages/*/_generated/` |
| the knowledge base (rAthena data, GPL: never committed) | `uv run python scripts/kb_build.py --out data/kb --maps <maps...>`; the map chain (first_workflow, npc_cells, route) for xmas_dun02: docs/planning/xmas02-prep.md sections 8-9 | `data/kb/` |
| map GATs | `uv run python scripts/grf_read.py extract <GRF> 'data\xmas_dun02.gat' 'data\prt_fild08.gat' --out /dev/shm/poring-lab-tmp/gat --decode-des` | `/dev/shm/poring-lab-tmp/gat/data/` |
| the backend's GAT copy (the Flows / Maps pages) | `uv run python scripts/flows_gat.py` | `data/gat/` |
| sprites + their catalog | `uv run python scripts/sprite_catalog.py --aegis <names...> --decode-mixcrypt` | `/dev/shm/poring-lab-tmp/sprites`, `data/kb/sprite_catalog.json` |
| the CPU detector's environment and models | docs/operations/detector-cpu.md, "Rebuild after a host reboot" | `/dev/shm/poring-lab-detector/` |
| ro_agent's screen signatures | `uv run python scripts/ro_agent.py calibrate <STATE>`, `calibrate-shell` | `data/ro_agent/signatures/` |
| the typing-only foreground gate | `ro_agent.py calibrate client_title_active`, then `uv run python scripts/foreground_template.py install rdp` (and `install stream` for S2); `status` reads back | `settings/foreground/` |
| UI window anchors (ADR-0011) | `uv run python scripts/ui_anchors_tool.py capture`; the S2 set: `ui_gate.py bank-windows`, `cut-windows`, `prove-windows-offline` (s2-gate-templates.md) | `data/ui_anchors/` |
| NPC dialog reader (the UI gate's dialog check) | `scripts/talk_calibrate.py drive --npc ...`, then its offline cut and proofs (docstring) | `data/ui_anchors/npc_dialog/` |
| the chat window standard | `uv run python scripts/chat_window.py cut-tabs ...`, `cut-padlock ...`, then `read` / `ensure` (rathena-client.md, "The chat window standard") | `data/ui_anchors/` |
| battle-log glyphs, per language | `scripts/battle_log.py formats-init en`, `clusters`, `cut`, `cut-names` | `data/ui_anchors/battle_log/<lang>/` |
| minimap position digits | `scripts/selfpos_calibrate.py` (labelled by packet truth from recorded sessions) | `data/ui_anchors/minimap_digits.npz` |
| minimap references (which map she is on; dungeon@9.46) | `OMP_NUM_THREADS=2 python3 scripts/minimap_id.py build --grf <GRF> --decode-mixcrypt` (every server map of the map cache; ~30 s; most minimap bitmaps are MIXCRYPT: without the study decoder those maps read "cannot tell") | `data/minimap_refs/refs.npz` |
| hotbar stock digits | `scripts/hotbar_count.py cut --cal DIR` | `data/hotbar/digits.npz` |
| HP percent glyphs, job identity references | `scripts/hp_percent.py fit FRAMES_DIR` then `prove FRAMES_DIR` (labelled by hp packets); `scripts/crusader.py --char <char> init --name <NAME>` (once), `cut-name`, `cut-job <JOB>`; add `--no-db` on a server with no DB of ours (section 11.1) | `data/crusader/`, `data/thief/` |

Notes:
- `--decode-mixcrypt` needs the study-only decoder in `~/poring-lab-private/` (Batt, 2026-10-05:
  never in the repo; mode 700). Without it, MIXCRYPT sprites are refused and reported, never
  worked around.
- Everything in `/dev/shm` is gone after a reboot. Re-extract the GATs and sprites, rebuild the
  detector environment, and diff the new catalog against `data/kb/sprite_catalog.json`.
- The live cuts (ro_agent, ui_gate bank, talk_calibrate drive, chat_window) send input through the
  mux, so they need the console in ASSIST (section 7.4).
- Every UI tool that types first passes the UI gate; cut and prove its templates before any bot
  run, and judge a screenshot of the client before every scored run.

## 9. Choosing the detector

The bot's box watcher asks a unit detector for monster boxes several times a second. The model
file is the same on every backend (ADR-0022): the deployed ONNX, loaded only by its pinned sha256.
What changes is where the forward pass runs.

| Hardware | Profile | Path | `--box-detector` | Measured | Status |
|---|---|---|---|---|---|
| no GPU | `dedicated-intel` (section 5) | the CPU detector: onnxruntime, 16 threads, in `/dev/shm/poring-lab-detector` | `cpu` | bot-server's CPU, quiet, 8 threads: 122-126 ms p50 a call; VM 103, 16 threads: 110 ms quiet, 194-339 ms under load | works |
| Intel Arc | `dedicated-intel` | OpenVINO detect server IN the Intel vision worker, the CPU detector behind it | `gpu` (the default) | decision detections p95 22.2 ms on the lab's entry-level Arc card (pilot p78, 2026-11-12, rogue-xmas02.md 4CN); bare forward ~16 ms with the clock floor | the lab's live path |
| NVIDIA | `dedicated-nvidia` (section 5) | the torch CUDA (cu130) detect server IN the CUDA vision worker, `.pt` weights, the CPU detector behind it | `gpu` (the default) | 49-52 ms a call on the old host's NVIDIA card, on a SHARED host (VM 103, paused half the time while R3 measured) | usable on a new host with `dedicated-nvidia` (2026-11-12); not yet run on a dedicated host (unverified) |
| AMD | - | designed (ADR-0022), never built | - | - | not built |

OpenVINO on the CPU measured ~10 % faster than onnxruntime on bot-server's CPU
(bot-server-migration.md 2), but it runs only inside the Intel worker, which needs a render node:
a GPU-less host uses the onnxruntime CPU detector.

**Recommendation for a new machine: an Intel Arc with `dedicated-intel`.** It is the only GPU path
proven end to end on a dedicated host (the cutover smoke: 302 / 302 detections served by the Arc),
about 5x faster per call than the CPU, the image and overlays exist, and the CPU detector stays
behind it automatically. An NVIDIA card with `dedicated-nvidia` is the other GPU path: the one the
old VM 103 ran, not yet proven on a dedicated host. Without a GPU, the CPU detector works; it is
slower and the runner's grab-to-click time grows with it.

**Intel graphics built into the CPU** (asked by Batt 2026-11-12, a recent desktop Core Ultra):
use `dedicated-intel` too. Nothing in the Intel path is tied to the lab's Arc card:
- the overlay passes the render node;
- OpenVINO runs on Intel's integrated GPUs;
- the clock unit holds the GPU at ITS OWN highest clock (RP0, read from sysfs, not a fixed number).

What to know:
- **The model:** CPU models with an F in the suffix (F, KF) have NO built-in graphics.
- **Speed (unverified):** a desktop Core Ultra's built-in graphics has about 4 Xe cores and shares
  system RAM. The lab's Arc card has 8 Xe cores and its own GDDR6. Expect it slower than the card
  but far faster than a CPU, and
  measure it with the 45-s serve test (section 9's run block).
- **RAM:** the GPU borrows system memory. 32 GB is comfortable, 16 GB the minimum.
- **The OS:** a recent Intel chip needs a recent kernel and Intel compute runtime. Ubuntu 26.04 (as
  bot-server) is the safe choice (unverified on that chip).
- **Training:** training on it (torch-xpu) is unverified. Detection through OpenVINO is the solid
  part.
- **Not used yet:** its NPU (AI Boost). OpenVINO can target it, but the code does not yet.
- **The fallback:** a recent desktop CPU is much stronger per core than the lab's server CPU, so
  even the CPU detector should run faster than the 110-126 ms measured here (unverified).

**Which model a map uses (`scripts/unit_detector.py`):**
- `MAP_MODELS`: the map's own deployed model. Today only xmas_dun02:
  `xmas02gb-last-736x1280.onnx`, sha256 `b22d972b...` (since 2026-11-10; Myst Case, Cruiser and
  the two Cookies collapse to one `monster` class; Garm Baby stays its own class for `--garm-fly`).
  A map without an entry uses v1 (`v1png-last-736x1280.onnx`).
- `GPU_WEIGHTS`: the registry of everything the detect server may load, by name, each with its
  `.pt` (torch) and its ONNX (OpenVINO) and their sha256: v1, xmas02, xmas02gb, and the floor-item
  rounds xmas02fi to xmas02fi5 (served for evaluation only; not in MAP_MODELS).
- `--box-model map` (default) picks MAP_MODELS, `--box-model v1` is the rollback.
- `--box-detector gpu` (default): the GPU server first; on no server, a pause, a 250-ms timeout or a
  bad reply, the CPU's boxes, never none, retrying the GPU every 5 s. A wrong sha256 or an unsafe
  socket turns the GPU off for the run. `cpu` = the CPU only.

**Where the files come from:** never git. Batt's NAS keeps the deployed ONNX files in
`archive/models/` (with `SHA256SUMS`) and the training runs in `archive/train/`; the CPU detector's
copies go in `/dev/shm/poring-lab-detector/model/` with their `.names.json`. Without the NAS:
Batt's private copy, or retraining (the training steps in docs/development.md;
docs/planning/xmas02-detector.md).

**THE RULE for a new model** (xmas02-detector.md O25, after p84's refused start, 2026-11-12):
1. The round's ONNX (and its names file) goes into the NAS models folder BEFORE its `GPU_WEIGHTS`
   entry is committed. The detect server opens EVERY registered ONNX at start, so one missing file
   refuses the whole server.
2. Then a short serve test must list it, before any pilot.

**Run the GPU path beside a run (dedicated-intel):**

```bash
python3 scripts/guarded_build.py worker:vision@60
eval "$(.venv/bin/python scripts/unit_detector.py serve-cmd --backend openvino --seconds 1800)"
```

- `serve-cmd` prints the guarded `execdev:vision` step (OpenVINO, GPU, conversion on the card,
  f32, every GPU_WEIGHTS model from `/datasets/archive/models`); `eval` runs it in the foreground,
  so start the runner from a second terminal once `/dev/shm/poring-lab-detect/detect.sock` exists.
- Check: the step's output has a JSON line with `"detect_server": "listening"` whose `"models"`
  lists every registered name. A serve test is the same command with `--seconds 45`.
- It ends at its time box with `FAILED rc=124` (that is `timeout` ending the server). At the end
  of the day: `python3 scripts/guarded_build.py worker-stop:vision`.
- Other docs wrap `worker:vision` in `scripts/runbooks/quiet_start.py`. That waits for 10 quiet
  minutes and never starts inside the SET market-open windows, whatever the profile: on a
  dedicated host start the worker directly, as above.
- A device check without the server **(unverified)**:
  `python3 scripts/guarded_build.py 'run:vision@300=python -c "import openvino as ov; print(ov.Core().available_devices)"'`.

**Run the GPU path beside a run (dedicated-nvidia; (unverified) on a dedicated host):** the same two
steps, with the torch backend (serve-cmd's default):

```bash
python3 scripts/guarded_build.py worker:vision@60
eval "$(.venv/bin/python scripts/unit_detector.py serve-cmd --seconds 1800)"
```

- The torch server loads each `GPU_WEIGHTS` model's `.pt` checkpoint from the NAS's
  `/datasets/archive/train/...` (inside the worker) by its sha256, not the ONNX: every registered
  `.pt` must be there.
- The same check (the `"listening"` line), the same `rc=124` at the time box, the same
  `worker-stop:vision`. The device check is `scripts/check_gpu.py` (section 5).

**The Arc's clock floor** (recommended): between calls the card clocks down and a forward runs at
~29 ms instead of ~16 (FP32). bot-server holds the floor at RP0 with a oneshot unit:

```bash
sudo install -m 755 scripts/host/poring-lab-gpu-clock.sh /usr/local/libexec/poring-lab-gpu-clock.sh
sudo install -m 644 scripts/host/poring-lab-gpu-clock.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now poring-lab-gpu-clock.service
cat /sys/class/drm/card*/gt_min_freq_mhz      # 2450 on the lab's Arc card
```

(The unit runs `/usr/local/libexec/poring-lab-gpu-clock.sh`, so the `.sh` goes in first; the unit's
own header says so since 2026-11-12, second-install-gaps.md row L.) Undo:
`sudo systemctl disable --now poring-lab-gpu-clock.service`.

**The Arc's VRAM on the Hardware page** (optional, 2026-11-12): i915 has no unprivileged source of
device-memory use, so the page shows "n/a" until a small ROOT helper runs. It reads
`i915_gem_objects` from debugfs every 2 s and writes only the numbers to
`/dev/shm/poring-lab-hwshm/vram.json`. The backend reads that file (no capabilities, no network
in the unit; see the unit's header):

```bash
sudo install -D -m 755 scripts/host/poring-lab-vram.py /usr/local/libexec/poring-lab-vram.py
sudo install -m 644 scripts/host/poring-lab-vram.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now poring-lab-vram.service
cat /dev/shm/poring-lab-hwshm/vram.json       # t_mono_ns advances every 2 s
```

A running backend picks it up within one sample; one that reads the old code needs
`python3 scripts/guarded_build.py --sustain 30 --spike 25 restart:backend@30`. An NVIDIA host
needs neither (the page has no NVIDIA reader by design). Undo:
`sudo systemctl disable --now poring-lab-vram.service`.

## 10. The xmas_dun02 Rogue on YOUR lab server

**Before the first run:** the Rogue (the GM account's character; Base 99 / Job 50, AGI and DEX 99
on bot-server) is built with GM commands on your own server
(docs/planning/thief-payon.md for the build steps, rogue-gef10.md and rogue-xmas02.md for the rest);
the hunting UI layout (`scripts/client_layout.py`); the map's committed zones and route
(`config/map_zones/xmas_dun02.yaml`, `config/routes/xmas_dun02.yaml`); the KB for the map, its GAT
and sprites (section 8); the detector (section 9).

**The base runner command.** The night chain's runner scripts run from `/dev/shm` (scratch). A
verbatim copy from 2026-11-12 20:15 is committed in
[docs/records/pilot-chain/](../records/pilot-chain/README.md), and the command below is taken from
it: `run_pilot_v3.sh`'s fixed part, `pilot_rec2.sh`'s `BASE`, and the night series' arm A flags
(rogue-xmas02.md 4DD). (Corrected 2026-11-12 20:15: the hand-composed version had `--steal`,
which the chain never passes.) `--exp-first` and `--box-detector gpu` are defaults.

```bash
nice -n 10 uv run --quiet python scripts/dungeon_hunt.py run --char rogue --map xmas_dun02 \
    --strategy P2 --search patrol --walk-trust --npc-guard --miss-cue --loot trim --clear-map \
    --minutes 25 --seed <SEED> --label <LABEL> --box-strike --box-now \
    --self-recheck --still-strike --engage-screen \
    --reach-check --far-single --far-approach --explore --walk-pick --kill-gap --loot-first \
    --walk-pick-step --quiet-scan --garm-fly --garm-confirm 2 --late-confirm \
    --still-target --lead-press \
    --value-target --hud --hud-fast 0.2
```

- The chain starts the detect server first (`scripts/unit_detector.py serve-cmd --backend openvino
  --seconds <run + 150>`) and waits for its `"listening"` line; `run_pilot_v3.sh` shows how.
- `--clear-map` types `@killmonster2` at the start: the map's MVP and every monster on it die,
  then respawn (rogue-xmas02.md 4DI). It is a GM line, so `--player-mode` refuses it.

**Immunity and the MVP, in one paragraph.** The map's MVP (Stormy Knight) killed the Rogue in two
hits 0.4 s apart (p18, 2026-11-08), so runs are scheduled around it, never fought: with immunity ON
(`@monsterignore`, typed through `uv run python scripts/crusader.py --char thief gm --job rogue
'@monsterignore'`) warp to the map, `@mobsearch` the MVP, and `@killmonster2` it if it is alive; it
respawns 60-70 minutes after its death, so two 25-minute runs fit before the next window. Before
EVERY base run, immunity goes OFF and is judged from the server's answer line on a screenshot (the
toggle flips the state, and a relog clears it; the glow around the character is not the sign). The
runner never touches immunity. After the run: immunity ON again, judged. Between runs: the weight
under 48 % (`dungeon_hunt.py clear-bag --char rogue --out /dev/shm/...`). Never stage strong
monsters next to her without Batt.

**Where results land:**
- the session: `/dev/shm/poring-lab-demo/<YYYYmmddTHHMMSS>-demo-dungeon-rogue-xmas_dun02-patrol-P2-<LABEL>/`
  (`events.jsonl`, `detections.jsonl`, the manifest and packets);
- judged offline from packets: `uv run python scripts/dungeon_judge.py row <SID> --map xmas_dun02`;
- the economy page: `uv run python scripts/econ_dash.py export <SESSION_DIR> --name <NAME>`, then
  `/economy` in the console;
- recordings and sessions go to the NAS with `scripts/dataset_ship.py ship` (a 30 GB local floor
  on dedicated-intel). Recording on the RDP path needs the `media-rec` sidecar (an Intel GPU
  encoder); without one, `record_session.py --format png --fps 1`.

### 10.1 Run records in SQLite (ADR-0025)

Every judged run's counts can be kept in ONE local file,
`data/econ/lab.sqlite` ([ADR-0025](../adr/0025-run-records-sqlite.md)). It uses Python's built-in
`sqlite3`, so there is nothing to install. The raw session folders stay the source of truth: the
file is built from them, and it can always be rebuilt.

**Where it lives:** in `data/econ/`, beside the item table. It is gitignored, so a `git pull` never
touches it.
- Back it up by copying `lab.sqlite`, with its `lab.sqlite-wal` / `-shm` if present, while no
  `econ_db.py` command is running.
- Never run `git clean -x` (section 4): it deletes the file.

**Build, update, list, export:**

```bash
uv run python scripts/econ_db.py build  <SESSION_DIR_OR_ID> [...]    # (re)judge these runs into the file
uv run python scripts/econ_db.py update <SESSION_DIR_OR_ID> [...]    # only runs not in the file yet
uv run python scripts/econ_db.py list                                # one line per run
uv run python scripts/econ_db.py export --format csv --out ~/share/runs.csv   # ids and counts, for sharing
uv run python scripts/econ_db.py dashboard --runs <SID> [...] --name <NAME>   # the /economy page's JSON
```

- `build` and `update` need the item table, `data/econ/items.json`
  (`uv run python scripts/econ_items.py build`; docs/econ/economics.md section 2). Without it they
  refuse and create no file.
- A run that disagrees with the judges' cross-check is refused, and nothing is written for it.
- A CSV export writes four files: `runs.csv`, `runs_items.csv`, `runs_species.csv` and
  `runs_consumables.csv`. They are UTF-8 with a BOM, so Excel opens them correctly.
- `--format json` writes one file instead.
- An export carries numeric ids and counts only. `--with-names` adds item and monster names from
  YOUR `data/`. Those names are rAthena- or client-derived: keep such a file local, and never
  commit or publish it.
- `dashboard` writes the same JSON as `econ_dash.py export`. If the item table changed after a run
  was built, it says so: `build` that run again.

**Open it** in [DB Browser for SQLite](https://sqlitebrowser.org/) (File > Open Database, Browse
Data, Execute SQL), or in Python (pandas is not a lab dependency: install it in your own Python):

```python
import sqlite3, pandas as pd
con = sqlite3.connect("file:data/econ/lab.sqlite?mode=ro", uri=True)  # read-only
runs = pd.read_sql("SELECT session, map, kills, hours, kills / hours AS kills_h FROM runs", con)
items = pd.read_sql("SELECT session, item_id, income, dropped FROM run_items", con)
```

- Open it read-only, as above. The file is in WAL mode, so a reader does not block a running
  build.
- **A file made by a NEWER poring-lab is refused** with "made by a newer poring-lab: pull the
  update". It is never changed. Pull the update, and the newer code reads it.
- An older file is upgraded forward by itself the next time `econ_db.py` opens it. Your rows are
  kept.

## 11. A new game server (e.g. the Thai dev server): the rules

Batt (2026-11-12) played a Thai dev server by hand at level 99 and wants to try the bot there
later. Here is what the lab allows TODAY, what is being built, and the warnings.

**As built today:**
- [ADR-0006](../adr/0006-sanctioned-test-environments.md) sanctions exactly two environments:
  the self-hosted rAthena on the LAN, and one community bot-testing server whose permission
  evidence is still pending. Official servers and every other public server are forbidden, for
  every component, in every mode. This binds the lab bot-server and what its agent does. On a
  copy YOU run, you are the person who decides; the warnings below apply.
- The interlock ([ADR-0016](../adr/0016-environment-interlock.md)) lets the bot press keys only
  while an Allowed environment is ATTESTED: our own sniffer, on our own rAthena, sees a live
  session of a lab account from the game PC. In ASSIST only (a mode only a person sets), a
  bounded operator window of at most 120 s also passes presses, for login and desktop steps
  (`capture_backend.py window`). Releases are never gated.
- A server we do not run cannot be packet-attested, so **the bot cannot act on an external server
  as built today**, Allowed or not. Its presses are refused with `environment_unattested`.
  ➡️ SUPERSEDED 2026-11-12 for a DECLARED server: ADR-0023 decision 1 is built (next paragraph's
  pointer). A person's declaration on the Settings page can turn such a server green, labelled
  "declared by a person, not verified".
- Adding a server for the lab is a person's act on the Settings page PLUS an ADR-0006 entry with a
  permission record that names the exact host the client connects to
  ([ADR-0021](../adr/0021-external-servers.md) D14).
- **Batt may always play such a server himself, by hand**, as the human. No packet capture of a
  server we do not run unless its own rules allow it.

**Being built next: ADR-0023, learner mode** ([ADR-0023](../adr/0023-learner-mode.md), decided
2026-11-07, not built). ➡️ 2026-11-12: decision 1 (the declaration) is BUILT (ADR-0023, section
Implementation); decisions 3 and 4 are not. A person will be able to DECLARE a server owner's
permission on the Settings page. The bot may then act there, shown as "declared by a person, not
verified"; research counts only packet-verified sessions. A user's own servers, including their own
rAthena on a public address, will then work after one Settings-page entry. Batt's direction
(2026-11-12): no hard locks for other users ("the more we lock, the more it breaks later"), plain
warnings instead. Until that build lands, ADR-0006 / ADR-0016 stand as written.

**The warnings, for every user of the code** (ADR-0023 decision 5 makes the official-server list a
DEFAULT for other users; on the lab bot-server, ADR-0006's ban on official servers stays
absolute):
- Run the bot only on a server whose owner permits bots. Their rules can change; check them again
  before each new series.
- Official servers are blocked by default. Lifting that block is the user's own act and the user's
  own responsibility: it breaks those servers' rules and risks a ban of the account.
- Never collect, keep or publish other players' data: chat, names, screenshots stay local and
  pseudonymized.
- Keep a separate client copy per server; never repoint the one you play with.

This manual gives no way to weaken, bypass or fake the interlock, the attestation or the server
list, and none exists in the supported setup.

### 11.1 Hunting on a server where you are not a GM: `--player-mode`

On a server you do not run (a declared one, ADR-0023), your account is a normal player. The
hunting runner's usual setup types GM commands (`@warp`, `@heal`, `@item`, `@killmonster2`): there
they would fail, or appear in public chat. Run it with `--player-mode` there
([docs/planning/player-mode.md](../planning/player-mode.md)):

```bash
nice -n 10 uv run --quiet python scripts/dungeon_hunt.py run --player-mode --char <CHAR> \
    --map <MAP> --strategy P2 --search patrol <your other flags> --minutes 25 --seed <SEED> \
    --label <LABEL>
```

- **The runner types no line at all**, and reads nothing from the lab's database (since
  dungeon@9.35c the start's identity check skips it too: the name plate and the job, from the
  pixels alone).
- **Your own character, once, before the first run.** The runner knows two character slots:
  `crusader` and `rogue` (the Rogue's files live in `data/thief/`, so the tools below take
  `--char thief`). For a Rogue:
  1. Write its name file (never over an existing one):
     `uv run python scripts/crusader.py --char thief init --name '<NAME>'`
  2. Log the character in alone, with Basic Info open (Alt+V), and cut its references from the
     screen: `uv run python scripts/crusader.py --char thief cut-name --no-db`, then
     `... cut-job rogue --no-db`.
  3. Check it: `uv run python scripts/crusader.py --char thief check --job rogue --no-db` must print
     `"ok": true`.
  - ⚠️ **`--no-db` is a warning, not a lock.** On a server of someone else's there is no DB of
    ours to say who is online, so the identity rests on the pixels and on your word that the
    character on screen is the one you named. Each command prints a `WARNING:` line saying so.
  - Not configurable yet: the runner's table of each character's numbers and keys (max HP and SP,
    F1 potion, F2 Fly Wing, F3 Steal, F5 the dagger, Insert to sit) is the lab Rogue's. A character
    with other keys or stats needs that table changed in `scripts/dungeon_hunt.py` (`CHARS_CONF`;
    docs/planning/second-install-gaps.md row R).
- **You bring the character to the map yourself**, standing on open ground, with the chat input
  closed. The run starts where your character stands.
- **On the hotbar:** at least 5 Fly Wings on the Fly Wing key (F2) and 5 heal items (White
  Potions on F1; with `--heal-candy`, Candy Canes and Candies count too). The bag must weigh less
  than 48 % on Basic Info. Below any of these the run refuses, and says why.
- **It never warps, heals or restocks you.** It ends when only 1 Fly Wing is left. At the end it
  uses its own Fly Wing escape. Then, if a Butterfly Wing shows a count on its key (F8, or
  `--player-home-key KEY`), it presses it ONCE to send you to your save point. If it was resting,
  it stands up for that. Without a Butterfly Wing it stays seated. After a death it leaves the
  death dialog for you.
- **Refused with it:** `--clear-map`, `--stage-mob`, `--stage-at`, `--start-cell`,
  `--engage melee_ring`.
- **Not built yet:** Kafra warps, NPC shops and selling. Also nothing that keeps you away from an
  MVP: the only guard is the boss escape of `--engage-screen`, and it is unproven. A map with an
  MVP is at your own risk. On a map whose KB lists a boss, with neither `--engage-screen` nor
  `--garm-fly`, the run prints one `WARNING:` line at its start and goes on.
- **Not research:** a run on a declared server is never counted (ADR-0023 decision 2). Its record
  carries `fixes.player_mode`; no judge filters on it yet.
- **From the console: the Run button (2026-11-13).** `/flows?runner=xmas_dun02` has a "Run in the
  game" panel. Run starts exactly this player-mode runner with the Knife base (rogue-xmas02.md
  4DQ), at most 120 min, until Stop or until the Fly Wings run low. Stop ends it through its
  normal end (its packets, the stats, a Butterfly Wing home).
  - It needs the host helper running: `python3 scripts/flow_run.py serve` (detached), or its user
    unit `scripts/host/poring-lab-flowrun.service` (the install lines are in its header).
  - Its request rules are the Settings page's: your browser on the LAN, the console's address,
    never the lab host itself.
  - The command it runs is fixed in `scripts/flow_run.py` (`FLOWS`); a request only names a flow
    (and, since dungeon@9.45, the flow's five hotbar keys when its functions give them).
  - "Check the game" ticks the checklist from the screen (dungeon@9.45: `dungeon_hunt.py check`,
    read only); the map's name is not read, so check that she is on the map yourself.
    ➡️ Since dungeon@9.46 the map's name is read from the minimap's picture, once its references
    are built (the "minimap references" row of section 8's table); a player start refuses another
    map, and a start that cannot tell.

## 12. Known differences of the Thai client

From the docs and code only (the lab has never run, unpacked or patched the Thai client's exe;
docs/thai-data-experiment.md section 3):
- **The battle log.** The reader (`scripts/battle_log.py`) is language-independent: its events are
  fixed and each client language is DATA in `data/ui_anchors/battle_log/<lang>/` (the line
  formats, the glyph templates, the monster-name templates). English is the live, validated
  language. For Thai, the line formats and a parser fixture exist, but the **glyphs are not
  built**: they need unscaled full-client screenshots (PNG). Batt's crop was about 2x scaled, so
  `data/ui_anchors/battle_log/th/` holds his screenshots and a README only.
- **EXP lines at the maximum level.** At the maximum level the server still sends an EXP notice
  (rAthena at the lab's pinned commit does too). The Thai client in Batt's screenshot prints it as
  a zero-EXP base line and a zero-EXP job line after each kill, in its battle tab; two of its chat
  options were on (battle messages, EXP gained). The lab's 2021 client prints nothing at level
  99. `dungeon_hunt.py --exp-first` (dungeon@9.34, ON by default, rogue-xmas02.md 4CW) counts
  either line as the kill, first, and stops the hit-gap inference once any EXP line has appeared
  in a run.
- **UI templates are per client.** The Thai client draws its own window skins, fonts, tab names
  and chat layout. Every template in section 8 (foreground gate, UI anchors, NPC dialog, chat
  window tabs, digits, battle-log glyphs) must be cut and proven again from that client's frames.
- **No text cues in English.** The lab's rule since 2026-10-26: cues by sprite, shape, colour,
  place and digits, never by English words, so the same bot can read a Thai or Korean client.
- **The data files.** The Thai `data.grf` cannot sit in front of the 2021 exe (it crashes), and its
  own clientinfo names the official Thai servers, which `config/environments.yaml` ships as
  forbidden.

## 13. Troubleshooting and where to look

| Symptom | Cause and fix |
|---|---|
| A LAN device cannot reach the bot host after a Docker change | a bridge took a LAN range: `ip route get 192.168.110.55` says `dev br-...`. Remove that network, pin a /24 in 10.210.x, recreate; check `docker info` for the pool |
| `permission denied` on the Docker socket | the docker group needs a new login |
| `/dev/shm` files vanish | logind RemoveIPC: section 1.3. After a reboot: section 8 |
| `REFUSED` from `scripts/dev.sh` | create/start/build go through `guarded_build.py` |
| guarded_build refuses everything on a dedicated host | a capture service runs there: fix `LAB_HOST_PROFILE` |
| GPU steps refused with an R3 / Frigate reason | the host runs `shared-nvidia`: section 5 |
| `worker:vision` fails to start | no render node, wrong `RENDER_GID` (`getent group render`), or an unreachable NAS volume (section 4.1) |
| the detect server `REFUSED` with `FileNotFoundError ... archive/models/...` | a registered ONNX is missing from the models folder: section 9's rule |
| `quiet_start.py` waits for ever | it waits 10 quiet minutes and skips SET market windows on every host: on a dedicated host start the worker directly |
| bot presses refused, `environment_unattested` | read `/health` `environment`: servers not confirmed (`no_servers`); the capture lock not steady (`capture_backend.py status`); the game PC is not 192.168.1.169 (section 7); the sniffer restarted (no session until the next login) |
| a Settings save refused | from the bot host or the game PC (use a third computer); a LAN outside 192.168.0.0/16 (section 4.1); a stale page (reload: the CSRF token is per backend start) |
| ro_agent refuses "mux mode is HUMAN" | the mux boots HUMAN after every backend start; a person sets ASSIST |
| Failed to Connect to Server right after login | this client needs the server picked within ~1-2 s of the list |
| login works, then a hang at server or character select | `HOST_LAN_IP` is not the host's LAN address; `scripts/dev.sh logs rathena` shows the advertised address |
| map-server loops on the char server | inter-server credentials over 23 characters |
| garbled packets after character select | `PACKETVER` does not match the client exe: set it, `build:rathena`, `start:rathena@240` |
| Thai shows as `?` | the database must be tis620; `smoke_test.sh --core` checks it |
| RDP worked for months, then stopped | Windows renewed its certificate: re-pin (section 7.3) and recreate the desktop |
| the client shows an account-settings error at every login | the AssistAddr lubs do not point at `<BOT_HOST_IP>:8888`, or `RATHENA_WEB_SERVER` is not `true` |
| the client starts nothing on Windows | Smart App Control: read the CodeIntegrity log (section 7.1) |

**Where to look:**
- `curl -s http://<BOT_HOST_IP>:8000/health` (the mux, the interlock, drops, the stream, the RDP
  window) and the console's banner;
- `scripts/dev.sh ps` and `scripts/dev.sh logs <svc>`;
- `$TMPDIR/poring-guarded-*.log` (every guarded step);
- `uv run python scripts/capture_backend.py status`, `uv run python scripts/ui_gate.py status`,
  `uv run python scripts/foreground_template.py status`;
- the console's Hardware page (`/hardware`): CPU, memory, `/dev/shm`, disk, GPU;
- README "Troubleshooting" for RDP exit codes, FreeRDP 3 flags, clipboard and paste problems.
