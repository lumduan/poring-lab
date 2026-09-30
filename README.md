# poring-lab

Private research lab for a **vision-based Ragnarok Online agent**. There are exactly two sanctioned
environments ([ADR-0006](docs/adr/0006-sanctioned-test-environments.md)):
- a self-hosted rAthena server on the LAN, for ground truth;
- a community bot-testing server, for multi-party social research. It stays manual-only until its
  permission evidence is recorded and the environment interlock exists.

Official and other public servers are forbidden.

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
│ ONE interactive session        │   RDP :3389   │ desktop   xfreerdp3 /f (no WM) ──► Xvfb :99 1280x800           │
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
| `rathena` | core, sniffer | login/char/map built from a pinned commit with `PACKETVER` (20211103, pre-renewal). The image ships the runtime tree as ONE tar, extracted into a 192m tmpfs on every start (~78 MiB). It renders `conf/import/*.txt` from `.env`, imports the schema on first start, and upserts the optional test account. Thai: tis620 end to end. |
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
| `HOST_LAN_IP:3000` | frontend **or** frontend-dev | web console (run one of them) | LAN |
| `HOST_LAN_IP:8000` | backend | `/health`, `/ws/stream`, `/ws/input`, `/transfer/*` (ADR-0004) | LAN |
| `HOST_LAN_IP:6080` | desktop | noVNC — **no authentication** | LAN |
| — (`:8001`) | backend | `/internal/agent` | compose network only |
| — (`:3306`) | db | MariaDB | compose network only |
| — (`:5900`) | desktop | x11vnc | inside the container only |
| outbound → `WIN_HOST:3389` | desktop | the single RDP session | LAN |

**Security:**
- Everything published binds to `HOST_LAN_IP`, never `0.0.0.0`.
- **noVNC has no authentication.** It is view-only by default (`NOVNC_VIEW_ONLY=true`).
- The backend's browser WebSockets require an `Origin` listed in `FRONTEND_ORIGINS`. The `/transfer`
  routes and clipboard paste additionally require one to be *present*, so scripts and the agent can't
  use them.
- The agent API is not published at all.
- Keep all of this on a trusted LAN.

## Web console now (no image builds): `frontend-dev`

Until the disk split lets images be built safely, the console runs as a dev server with **no image
builds and no disk-heavy writes** (`compose.dev.yaml`, driven by `scripts/dev.sh`):

- `backend` runs its source straight from the host, mounted read-only and put first on `PYTHONPATH`.
  Picking up code changes is a restart, not a rebuild.
- `frontend-dev` runs `next dev` on the local `node:24.17.0-slim` image (no pull):
  - the source is mounted read-only at `/src`, then copied into tmpfs and kept in sync;
  - tmpfs caps: `/app` 2 GiB (`node_modules` + pnpm store), `/app/.next` 1 GiB, `/tmp` 256 MiB;
  - `mem_limit` 3.5 GiB, read-only rootfs, core dumps off.

```bash
scripts/dev.sh up -d backend frontend-dev     # start (desktop keeps its RDP session)
scripts/dev.sh restart backend                # pick up backend / poring_env code changes
scripts/dev.sh logs -f frontend-dev           # dev server output
scripts/dev.sh stop frontend-dev              # console off
```

Open **http://192.168.1.13:3000** (`HOST_LAN_IP`). What it gives you:
- **View:** Fit (aspect ratio kept, letterboxed) or 1:1.
- **Input:** click the screen to give it keyboard focus. That focus lives in a hidden textarea, so
  ⌘V pastes your clipboard into Windows (ADR-0004). Leaving it, or hiding the tab, releases
  everything held.
- **Toolbar:** Ctrl+Alt+Del (sent as Ctrl+Alt+End, RDP's secure-attention mapping), Win, Alt+Tab, Esc,
  Release keyboard.
- **Header:** mode switch and ASSIST lease. **Panel:** stats. A banner shows if the stream or RDP is down.

**Workstation alternative:** run the console on your own machine against this backend.
1. Add your browser's origin to the backend allowlist in `.env`:
   `FRONTEND_ORIGINS=http://192.168.1.13:3000,http://localhost:3000`
2. Apply it: `scripts/dev.sh up -d backend`.
3. Run the console:

```bash
cd services/frontend && corepack pnpm install
BACKEND_PUBLIC_URL=http://192.168.1.13:8000 corepack pnpm dev    # open http://localhost:3000
```

`FRONTEND_ORIGINS` is the backend's WebSocket Origin allowlist: comma-separated, and unknown origins are
refused. It defaults to `http://${HOST_LAN_IP}:3000`. Stream rate and quality are `STREAM_FPS` (30) and
`JPEG_QUALITY` (80). The stream is sent without WebSocket compression: JPEG doesn't compress, and
deflate cost 8 fps on the event loop.

**Latency (Phase 0, [docs/phase0-latency.md](docs/phase0-latency.md)).** The stream grabs when the
screen changes (`STREAM_CAPTURE=damage`, at most `STREAM_MAX_FPS=60`); `fixed` restores the old
`STREAM_FPS` grid. `/health` has a `latency` block:
- capture/encode/send;
- the open tab's network, decode and paint times, with the clock-offset uncertainty.

`scripts/latency_probe.py` (inside the backend container) measures the segments and switches the
knobs live through the loopback-only `/debug/stream-tuning`: `capture`, `max_fps`, `jpeg_quality`,
and the console's `paint` and `move_interval_ms`.

## Clipboard and file transfer (human-only, ADR-0004)

Both are **off by default**. For this lab `.env` sets:

```bash
RDP_CLIPBOARD=text-to-remote   # off | text-to-remote  (text Mac -> Windows only; never Windows -> X)
RDP_DRIVES=transfer            # "" | transfer        (\\tsclient\transfer in Windows)
```

Applying a change reconnects the RDP session once, because desktop and backend are recreated together:
`scripts/dev.sh up -d --no-deps desktop backend`.

- **Paste to Windows:** click the target field in the remote screen, then press **⌘V** there, as
  in Windows App.
  - Off macOS the paste chord is Ctrl+V; Shift+Insert works everywhere.
  - On a Mac, physical Ctrl+V still reaches Windows as Ctrl+V (Windows-internal paste).
  - A toast on the screen shows the result.
  - The "Paste to Windows" panel stays as a fallback: paste into its box, check it, then Send (⌘Enter).
  - Up to **64 KiB** of UTF-8; Thai is fine. It works over plain HTTP: the page uses the `paste`
    event, not `navigator.clipboard`.
  - The backend owns the X clipboard for about a second, the mux sends Ctrl+V as the human, and then
    it lets go. Windows keeps no copy.
  - Refused in BOT mode, and only accepted from the console page.
  - Logged as length + sha256, never the text.
- **Files ⇄ Windows** (console panel):
  - Uploads land in `\\tsclient\transfer` (Win+R in Windows).
  - Whatever Windows saves there can be downloaded from the panel.
  - A **512 MiB tmpfs** (RAM, never the disk), emptied when desktop and backend stop.
  - **Large files such as a multi-GB game client: use SMB or a direct download on Windows**, not
    this.
  - Audited in `data/transfer_log/` (name, size, sha256).
- The bot can use neither. The mux refuses a bot Ctrl+V / Meta+V / Shift+Insert, the agent protocol
  has no such messages, and a watchdog clears any foreign X clipboard owner. The remaining gap (vision
  can still reach X directly) is [ADR-0005](docs/adr/0005-vision-x-access.md), which blocks Phase 4.

## Quickstart

```bash
scripts/init_env.sh                          # .env from .env.example: detects HOST_LAN_IP, random secrets
python3 scripts/guarded_build.py build:desktop build:backend build:rathena build:frontend pull:db up:180
scripts/smoke_test.sh                        # health, LAN ports, >=30 frames, input round trip, input log
```

**On this host (dev mode, `scripts/dev.sh`):** `up:` is refused because it would recreate the dev
containers. Bring the game server up with `start:` instead, using the tolerant IO guard (Batt,
2026-09-30):

```bash
python3 scripts/guarded_build.py --sustain 30 --spike 25 build:rathena pull:db start:db@120 start:rathena@240
scripts/smoke_test.sh --core                 # db + rathena health, LAN ports, advertised IP, tis620
```

`guarded_build.py` builds one image at a time and backs off if the host's live capture services start
stalling on disk IO. On a dedicated machine, `docker compose --profile core --profile remote up -d --build`
does the same thing unguarded.

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
suffixing a new username with `_M` or `_F` (e.g. `bot01_M`). `RATHENA_TEST_USER` / `RATHENA_TEST_PASSWORD`
(generated by `init_env.sh`, only in `.env`) are upserted as a player account on every rathena start.

### Windows host checklist (the RO client side)

1. Enable Remote Desktop. Use a dedicated account in "Remote Desktop Users" and put it in `RDP_*`.
2. Give the host a fixed IP (DHCP reservation) → `WIN_HOST`.
3. Disable sleep, the screen lock and the screensaver. A locked session shows the lock screen to the agent.
4. Run the RO client **inside the RDP session** at `XVFB_RESOLUTION` (default 1280x800; the 1024×740 client window plus the taskbar need the height).
5. Use a **separate client copy for rAthena** (ADR-0006). **Leave the existing community-server
   client untouched:** never patch, repoint or reuse it in place.
   - The rAthena copy must match `PACKETVER` (its executable date) and point at `HOST_LAN_IP:6900`.
   - Client patching and `clientinfo.xml` live on Windows. **Never copy client files into this
     repo** (see `.gitignore`).
   - The recipe (exe, data, WARP patches, HKCU settings, the dgVoodoo2 wrapper that RDP needs, Thai
     locale): [docs/client/rathena-client.md](docs/client/rathena-client.md). It lives in
     `C:\RO-rAthena\` and is launched non-elevated.
6. Pin the RDP certificate: `python3 scripts/rdp_cert_fingerprint.py <WIN_HOST>` prints the
   `RDP_CERT_SHA256=` line for `.env` (pre-auth handshake only; it never logs in). Unpinned means
   `/cert:ignore`.

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

**RDP worked for months, then stopped connecting.** Windows renews its self-signed RDP certificate
about every six months, so the pinned fingerprint no longer matches. `rdp-loop` treats that as a
TLS failure and backs off; no credentials are sent. Re-pin:
`python3 scripts/rdp_cert_fingerprint.py <WIN_HOST>`, update `.env`, then
`docker compose restart desktop`.

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
`python3 scripts/guarded_build.py --sustain 30 --spike 25 build:rathena start:rathena@240`.

**map-server loops "Connection to Char Server lost" / login logs "Invalid password" for the server
account.** The inter-server `RATHENA_SERVER_USER`/`PASSWORD` must be at most 23 characters. char and
map keep them in 24-byte buffers and silently truncate longer ones.

**Thai shows as `?` or chat lines are missing from `chatlog`.** The database must be tis620
(`scripts/smoke_test.sh --core` checks this). The db volume takes `--character-set-server=tis620`
only when it is first initialised; the rathena entrypoint refuses anything else.

**The client hangs at 100 % CPU with no window, or says "Cannot init d3d".** See
[docs/client/rathena-client.md](docs/client/rathena-client.md). Causes: missing HKCU `RenewSetup`/`Ragnarok`
keys (it loops trying to run Setup.exe), and DirectDraw/Direct3D 7 under RDP (needs the dgVoodoo2 wrapper).

**Paste does nothing, or says "did not paste".** The toast on the screen, or the panel's message,
names the cause. If ⌘V shows no toast at all, the screen didn't have keyboard focus: click it first.
- `rdp_clipboard_not_listening`: `RDP_CLIPBOARD` is not `text-to-remote`, or RDP is reconnecting.
  Check the connect line in `scripts/dev.sh logs desktop`, which reads `clipboard=… drives=…`.
- `no_data_request`: the focused Windows window ignored Ctrl+V. Click a text field in the remote screen
  first. The game's chat box needs to be open.
- `mode_bot`: switch the mux to HUMAN or ASSIST.
- Every refusal is also counted in `/health` (`input_refused`, `clipboard.foreign_owner_clears`).

**`\\tsclient\transfer` is missing in Windows.**
- `RDP_DRIVES=transfer` must be set in `.env`, and the desktop recreated.
- Drives appear only for sessions started after that.
- Explorer may need `\\tsclient` typed in full.

**A message was dropped.** The backend never drops silently. The console banner shows it, and
`/health` has `dropped_messages{channel: {reason: n}}`. A WARNING names the channel, message type and
reason (e.g. `missing:key.t_mono_ns`), never the contents. Script clients must send `t_mono_ns` on
every message.

## Roadmap

Research phases 0–6, current status and the ordered plan: [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Next step: Phase 0 (capture FPS and end-to-end latency)

`scripts/ws_probe.py` already reports stream FPS and backend-side capture→encode→send latency
(30.0 fps; capture→encode p50 ~11 ms; encode→send p50 ~0.6 ms on 2026-09-29). Phase 0 extends it:

- **mss XShm grab rate at 1280×720,** measured in the backend and in vision.
- **Motion-to-photon latency:** inject a key through the mux that toggles a large, fixed UI element.
  Time it from the mux's `t_mono_ns` to the first changed pixel. Everything runs on one host clock.
- **Codec comparison:** run the above for each `RDP_GFX` codec (autodetect/AVC444, `progressive`,
  `off` = lossless legacy), and score fidelity against a lossless on-Windows screenshot.
