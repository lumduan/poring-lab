# poring-lab

A lab for a **vision-based Ragnarok Online bot** that you run on your own rAthena server, on your
own LAN. The bot sees the game **only through pixels** and plays **only through mouse and keyboard**:
no memory reading, no packet injection. Packet capture is used offline, as ground truth.

**Documentation: [docs/README.md](docs/README.md)** (the console, the architecture, troubleshooting,
the research). The full setup manual is [docs/setup/new-lab-host.md](docs/setup/new-lab-host.md).

> **Where the bot may play.** Only on game servers you allow on the console's Settings page, and
> only with the server owner's permission. Official servers are forbidden. See
> [ADR-0006](docs/adr/0006-sanctioned-test-environments.md) and
> [ADR-0023](docs/adr/0023-learner-mode.md).

## What you need

- **A Linux server** for the bot and the game server: Ubuntu 26.04 LTS, 8 or more CPU cores, 16 GB
  RAM (32 GB to train), an SSD with 256 GB or more. A GPU is optional (an Intel Arc or NVIDIA card)
  and makes the detector faster; without one, the CPU detector runs.
- **A Windows PC** on the same LAN, for the game client only, with a fixed address.
- **A third computer with a browser** for the console. The Settings page refuses writes from the
  server and from the game PC.
- **A Ragnarok Online client** that matches the server's `PACKETVER` (`20211103` by default, in
  `.env`). It is not included, and client files are never committed.

## Quick start

The full steps, with a check and a fix for each, are in the
[setup manual](docs/setup/new-lab-host.md). In short:

1. **Set Docker's address pool BEFORE installing Docker**, so Docker never takes a 192.168.x range
   from your LAN, then install Docker and keep `/dev/shm` across logouts (manual, sections 1.1 to
   1.3). These are the only steps that need `sudo`; the wizard never runs it.
2. **Set up the Windows PC with Sunshine** first: [docs/setup/sunshine-windows.md](docs/setup/sunshine-windows.md)
   (the signed installer, its own login, the firewall scoped to the bot server, a display, a fixed
   address). The wizard needs Sunshine running and the PC's address.
3. **Get the code and run the setup wizard** on the bot server:

   ```bash
   git clone https://github.com/lumduan/poring-lab.git
   cd poring-lab
   ./setup.sh
   ```

   `./setup.sh` checks Linux, git and uv (a missing uv is installed only after you say yes), runs
   `uv sync` and enables the commit guard, then opens the wizard (manual, section 6.1). Its screens:
   pre-flight checks and the host profile; this server's address (detected); the console port
   (default 3000, changeable); the Windows PC's address and a Sunshine test; a review, then `.env`
   (random secrets on a new one, nothing regenerated on an existing one); the install, every build
   and start through `scripts/guarded_build.py`; the Sunshine pairing (you type its PIN on the PC);
   a stream test; and a summary with the console's address. It resumes where it stopped.
   `./setup.sh --check` shows the status without changing anything; `./setup.sh --dry-run` prints
   every step.
4. **Open the console** at `http://HOST_LAN_IP:CONSOLE_PORT` (3000 unless you changed it) from a
   third computer. It always starts in HUMAN mode; only a person switches it to ASSIST or BOT.
5. **Set up the game client** on the PC ([docs/windows-setup.md](docs/windows-setup.md) sections
   1 and 2), then choose the detector (manual, section 9).

> **Known limit of the Sunshine-only setup.** You can watch the PC and play through the console.
> The bot cannot type on this path yet: its UI-gate templates for the console stream are not cut
> or proven, so every typed game line is refused, and the bot programs do not run there
> ([sunshine-windows.md](docs/setup/sunshine-windows.md) section 11). The lab itself runs on RDP.

### Without the wizard (advanced)

The same steps by hand (manual, sections 2 to 6):

```bash
git clone https://github.com/lumduan/poring-lab.git
cd poring-lab
uv sync
git config core.hooksPath .githooks
scripts/init_env.sh                 # .env: random secrets, HOST_LAN_IP from the default route
getent group render                 # the third field is the gid
uv run python scripts/rotate_secrets.py set LAB_HOST_PROFILE=dedicated-intel RENDER_GID=<gid> VISION_MAX_VRAM_FRACTION=1.0
python3 scripts/guarded_build.py build:rathena pull:db build:backend build:desktop
python3 scripts/guarded_build.py target:rathena:build:poring-lab/rathena-build:local
python3 scripts/guarded_build.py tables && uv run python scripts/gen_mapcache.py
python3 scripts/guarded_build.py build:sniffer
python3 scripts/guarded_build.py start:db@120 start:rathena@240
scripts/smoke_test.sh --core        # must print: SMOKE TEST (--core) PASSED
uv run python scripts/capture_backend.py init
python3 scripts/guarded_build.py start:backend,desktop@90
python3 scripts/guarded_build.py start:sniffer@120
python3 scripts/guarded_build.py start:frontend-dev@120
```

Use `dedicated-nvidia` instead of `dedicated-intel` for an NVIDIA card (manual, section 5). For the
Sunshine path add `build:gamestream`, `start:gamestream@60` and the pairing (manual, section 7.5);
for RDP, section 7.3.

## Configuration

- Every setting comes from **`.env`**; [`.env.example`](.env.example) lists them all.
- Host-specific changes go in **`compose.override.yaml`** (gitignored). A `git pull` never
  overwrites `.env`, `compose.override.yaml`, `settings/` or `data/` (manual, section 4).
- `LAB_HOST_PROFILE` describes your machine: a dedicated host with an Intel or NVIDIA GPU, or a
  host shared with other services (manual, section 5).

## Ports

Everything binds to `HOST_LAN_IP`. Keep it on a trusted LAN.

| Port | What |
|---|---|
| `CONSOLE_PORT` (3000) | the web console (`.env`; the wizard asks for it) |
| 8000 | the backend (stream, input, health) |
| 6900, 6121, 5121 | the rAthena login, char and map servers |
| 8888 | the rAthena web server (the client's account settings) |
| 6080 | noVNC, view-only, **no authentication** |

Every service and port: [docs/services-and-ports.md](docs/services-and-ports.md).

## License

Apache-2.0 ([LICENSE](LICENSE)), except `services/vision`, which is AGPL-3.0-only
([services/vision/LICENSE](services/vision/LICENSE)) because it imports ultralytics
([ADR-0018](docs/adr/0018-component-licensing.md)). Third-party work and its terms:
[THIRD_PARTY.md](THIRD_PARTY.md).
