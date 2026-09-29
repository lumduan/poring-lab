# poring-lab

Private research lab for a **vision-based Ragnarok Online agent**, tested **only** against a self-hosted
rAthena server on the LAN.

> **Core principle.** The agent perceives the game **only through pixels** and acts **only through
> mouse and keyboard**. There is no memory reading and no packet injection. Packet sniffing is allowed
> later, and only as **offline** ground truth for evaluating perception.

This repository is the **scaffold**: containers, wiring, health checks, the environment contract,
a minimal stream/input round trip, and the input mux. Detection, policy, training, packet decoding,
humanization and LLM integration are clearly marked TODOs.

## Topology

```
 Windows host (OptiPlex 3080)                     Ubuntu Docker host (HOST_LAN_IP)
┌────────────────────────────────┐               ┌────────────────────────────────────────────────────────────────┐
│ ONE interactive session        │   RDP :3389   │ desktop   xfreerdp3 /f (no WM) ──► Xvfb :99 1280x720           │
│   └─ RO client                 │ ◄──────────── │           x11vnc (view-only) ──► noVNC :6080                   │
│        │                       │  exactly one  │                                     │ /tmp/.X11-unix (volume)  │
│        │ game traffic          │               │              ┌──────────────────────┴────┐                     │
│        │ 6900 / 6121 / 5121    │               │              ▼ grab (ro)                 ▼ grab (ro)           │
│        └────────────────────── │ ──────────►   │ rathena      backend :8000               vision (GPU)          │
│                                │               │  login       JPEG stream                 grab → infer →        │
│                                │               │  char        INPUT MUX ◄─────────────    decide → act          │
│                                │               │  map          └─► XTest                  (:8001, internal)     │
│                                │               │   │          (the only input writer)                           │
│                                │               │   ▼          ▲ /ws/input   │ /ws/stream                        │
│                                │               │  db          │             ▼                                   │
│                                │               │              frontend :3000 ◄──► your browser                  │
│                                │               │  sniffer (placeholder, in rathena's network namespace)         │
└────────────────────────────────┘               └────────────────────────────────────────────────────────────────┘
```

- Pixels flow Windows → RDP → `xfreerdp3` → Xvfb framebuffer. From there, `backend` grabs them for
  the browser stream and `vision` grabs them for inference, both from the shared X socket.
- Input flows browser/agent → **backend mux** → XTest → Xvfb → `xfreerdp3` → RDP → Windows. The mux is
  the only writer (ADR-0002).

## Services and profiles

| Service | Profile(s) | What it is |
|---|---|---|
| `db` | core, sniffer | MariaDB 11.8 LTS, named volume, never published |
| `rathena` | core, sniffer | login/char/map built from a pinned commit with `PACKETVER`. It renders `conf/import/*.txt` from `.env` on every start and imports the schema on first start. |
| `desktop` | remote | Xvfb + the ONE `xfreerdp3` session + view-only x11vnc/noVNC, under supervisord |
| `backend` | remote | FastAPI: screen stream, input mux, JSONL input log, internal agent API |
| `frontend` | remote | Next.js console: video canvas, overlay canvas, mode switch, FPS/latency |
| `vision` | vision | GPU agent loop skeleton (torch 2.14 cu130 + ultralytics), `scripts/check_gpu.py` |
| `sniffer` | sniffer | Placeholder only (see `services/sniffer/README.md`) |

`sniffer` shares rathena's network namespace, so `--profile sniffer` brings `db` and `rathena` up with it.
`vision` works on its own, but it has nothing to look at until `remote` runs.

## Ports

| Host bind | Service | Purpose | Exposure |
|---|---|---|---|
| `HOST_LAN_IP:6900` | rathena | login server | LAN |
| `HOST_LAN_IP:6121` | rathena | char server (advertises `HOST_LAN_IP`) | LAN |
| `HOST_LAN_IP:5121` | rathena | map server (advertises `HOST_LAN_IP`) | LAN |
| `HOST_LAN_IP:3000` | frontend | web console | LAN |
| `HOST_LAN_IP:8000` | backend | `/health`, `/ws/stream`, `/ws/input` | LAN |
| `HOST_LAN_IP:6080` | desktop | noVNC — **no authentication** | LAN |
| — (`:8001`) | backend | `/internal/agent` | compose network only |
| — (`:3306`) | db | MariaDB | compose network only |
| — (`:5900`) | desktop | x11vnc | inside the container only |
| outbound → `WIN_HOST:3389` | desktop | the single RDP session | LAN |

**Security:**
- Everything published binds to `HOST_LAN_IP`, never `0.0.0.0`.
- **noVNC has no authentication.** It is view-only by default (`NOVNC_VIEW_ONLY=true`).
- The backend's browser WebSockets require an `Origin` listed in `ALLOWED_ORIGINS`.
- The agent API is not published at all.
- Keep all of this on a trusted LAN.

## Quickstart

```bash
scripts/init_env.sh                          # .env from .env.example: detects HOST_LAN_IP, random secrets
docker compose --profile core --profile remote up -d --build
scripts/smoke_test.sh                        # health, LAN ports, >=30 frames, input round trip, input log
```

- **Web console:** `http://HOST_LAN_IP:3000`. Click the screen to control it; switch between HUMAN,
  ASSIST and BOT at the top.
- **Debug view:** `http://HOST_LAN_IP:6080` (noVNC, view-only).
- **GPU check:**
  ```bash
  docker compose --profile vision build
  docker compose --profile vision run --rm vision python scripts/check_gpu.py
  ```
- **Agent loop:**
  ```bash
  docker compose --profile remote --profile vision up -d
  ```
  Set `VISION_DEBUG_BOX=true` to see a box on the overlay without a model.
- **RDP:** without `WIN_HOST`/`RDP_USER`/`RDP_PASSWORD` in `.env`, the desktop runs Xvfb-only (a black
  screen). Everything else still works. Fill them in, then `docker compose restart desktop`.

**Game accounts:** `RATHENA_NEW_ACCOUNT=yes` lets you create an account from the client login screen by
suffixing a new username with `_M` or `_F` (e.g. `bot01_M`).

### Windows host checklist (the RO client side)

1. Enable Remote Desktop. Use a dedicated account in "Remote Desktop Users" and put it in `RDP_*`.
2. Give the host a fixed IP (DHCP reservation) → `WIN_HOST`.
3. Disable sleep, the screen lock and the screensaver. A locked session shows the lock screen to the agent.
4. Run the RO client **inside the RDP session** at `XVFB_RESOLUTION` (default 1280x720).
5. The client must match `PACKETVER` (its executable date) and point at `HOST_LAN_IP:6900`. Client
   patching and `clientinfo.xml` live on Windows; **never copy client files into this repo** (see
   `.gitignore`).
6. Optional: set `RDP_CERT_SHA256` to the RDP certificate's SHA-256 so the connection is pinned instead
   of `/cert:ignore`.

## Development

```bash
uv sync                               # host venv: poring_env + backend + dev tools (not torch)
uv run pytest                         # mux, protocol round trips + schema drift, keymap, app e2e, loop
uv run ruff check . && uv run ruff format --check .
uv run mypy                           # --strict on packages/poring_env (and the backend)
scripts/gen_protocol.sh               # after editing poring_env/protocol.py: schema + TS types
(cd services/frontend && corepack pnpm install && corepack pnpm lint && corepack pnpm typecheck)
```

- **Python:** 3.12, a uv workspace (`packages/poring_env`, `services/backend`, `services/vision`),
  ruff, and `mypy --strict`.
- **Wire protocol:** the Pydantic models in `poring_env.protocol` are the source of truth. The JSON
  Schema and the TypeScript are generated from them and committed, and CI-style tests fail on drift.
- **vision's GPU dependencies install only inside its container:**
  - torch `2.14.0+cu130`, from the explicit cu130 index declared in the root `pyproject.toml`;
  - ultralytics, with headless OpenCV.
- **Architecture decisions:** [`docs/adr/`](docs/adr/).

## Troubleshooting

**Login works, then the client hangs or disconnects at server/character select.**
- The char/map servers are advertising the wrong IP. `HOST_LAN_IP` must be this host's LAN address.
- Check `docker compose logs rathena | grep "clients will be sent"`.
- Never set rAthena's `bind_ip` to the LAN IP: it doesn't exist inside the container.

**The RDP session keeps dropping or never connects.** Windows client editions allow **one**
interactive session. `rdp-loop` reacts to xfreerdp3's exit code:

| Exit | Meaning | What happens |
|---|---|---|
| **5** | someone else took the session | backs off for 10 minutes. Don't use `mstsc` against the Windows host while the stack runs. |
| **132 / 134 / 135 / 148–159** | authentication or account failure | **stops retrying** (account-lockout risk). Fix `.env`, then `docker compose restart desktop`. |
| 16–26 | licensing, or a bad command-line flag | stops |
| anything else | network trouble, host booting | backs off, 2 s → 60 s |

Watch it with `docker compose logs -f desktop`.

**FreeRDP 2 vs 3 flags.** This image pins FreeRDP **3.15** (`xfreerdp3`). 2.x spellings aren't even
compiled in:

| Purpose | 2.x | 3.x (used here) |
|---|---|---|
| ignore certificate | `/cert-ignore` | `/cert:ignore` (or `/cert:deny,fingerprint:sha256:<hex>`) |
| H.264 | `/gfx-h264`, `/gfx:avc444` | `/gfx:AVC444` (Debian builds only; Ubuntu's FreeRDP 3 has no H.264) |
| keyboard layout | `/kbd:0x409` | `/kbd:layout:0x409` |
| credentials off argv | `/from-stdin` | `/args-from:stdin` (must be the only argument) |
| binary | `xfreerdp` | `xfreerdp3` |

**noVNC is black.** That's normal without RDP credentials: Xvfb is empty. Check the `RDP window` field
in the console's stats panel.

**`cudaGetDeviceCount == 0` in vision, while `nvidia-smi` works on the host.**
- If the Proxmox host had hardware work, verify the GPU's PCI address (BDF) in VM 103's passthrough
  config (see `~/docker/frigate/CLAUDE.md`).
- `no kernel image is available` means the wrong torch wheel. This project needs **cu130** (sm_120).
- A `nvidia/cuda:13.2*` base image refuses to start on this host's R580 driver.

**The rAthena build fails in `rapidyaml`.** That's a parallel-make race. Set `RATHENA_MAKE_JOBS=1` in
`.env` and rebuild.

**The client disconnects right after character select, or shows garbled packets.** `PACKETVER` doesn't
match the client executable. Set it in `.env`, then run
`docker compose --profile core build rathena && docker compose --profile core up -d`.

## Next step: Phase 0 (capture FPS and end-to-end latency)

`scripts/ws_probe.py` already reports stream FPS and backend-side capture→encode→send latency. Phase 0
extends it:

- **mss XShm grab rate at 1280×720,** measured in the backend and in vision.
- **Motion-to-photon latency:** inject a key through the mux that toggles a large, fixed UI element.
  Time it from the mux's `t_mono_ns` to the first changed pixel. Everything runs on one host clock.
- **Codec comparison:** run the above for each `RDP_GFX` codec (autodetect/AVC444, `progressive`,
  `off` = lossless legacy), and score fidelity against a lossless on-Windows screenshot.
