# Services and ports

<!-- Moved from the root README on 2026-11-13 (Batt: "the README only for setup; the rest in docs/"). -->

## Services and profiles

| Service | Profile(s) | What it is |
|---|---|---|
| `db` | core, sniffer | MariaDB 11.8 LTS, named volume, never published |
| `rathena` | core, sniffer | login/char/map built from a pinned commit with `PACKETVER` (20211103, pre-renewal). The image ships the runtime tree as ONE tar, extracted into a 192m tmpfs on every start (~78 MiB). It renders `conf/import/*.txt` from `.env`, imports the schema on first start, and upserts the optional test account. Thai: tis620 end to end. |
| `desktop` | remote | Xvfb + the ONE `xfreerdp3` session + view-only x11vnc/noVNC, under supervisord. CPU: low weight (`cpu_shares: 64`) and an 8-core ceiling, because xfreerdp's software decode takes 7-15 cores in full-scene motion. |
| `backend` | remote | FastAPI: screen stream, input mux, JSONL input log, internal agent API |
| `frontend` | remote | Next.js console: video canvas, overlay canvas, mode switch, FPS/latency |
| `vision` | vision | GPU agent loop skeleton (torch 2.14 cu130 + ultralytics), `scripts/check_gpu.py` |
| `sniffer` | sniffer | ADR-0007 packet ground truth, offline/human-console only, plus the ADR-0016 session ATTESTATION (yes/no + account id + age, never world data). Its own slim image (`poring-lab/sniffer:local`): a `poring_packets` change needs a guarded `build:sniffer` + `recreate:sniffer`. Root with only `NET_RAW`, read-only rootfs. Writes pcapng (password bytes zeroed) + `events-*.jsonl.gz` to the `captures` volume (hourly / 256 MB; 7 days / 20 GB) and feeds `/ingest/packets`. Needs `scripts/gen_packet_tables.py` run once (the length table is build-time generated, never committed). |

| `gamestream` | gamestream | ADR-0009 console mode: moonlight-qt shows the Sunshine stream of the Windows **console** session in the same Xvfb :99 (input from the mux's XTest, absolute mouse). Streams only while the capture-backend lock says `console`; idles under `rdp`. Read-only rootfs, AppImage unpacked into tmpfs, pairing key in the `gamestream-state` volume (mounted here only). |

| `db-th`, `rathena-th`, `sniffer-th` | th | **The Thai-data experiment (Batt, 2026-10-05; ADR-0006 environment 1b):** a SEPARATE rAthena with the same image, SHA and pre-renewal mode; its own database (`db-th-data`) and captures (`captures-th`); a map cache generated from the Thai client's GRF by rAthena's own tool (`scripts/gen_mapcache_th.py` → `data/mapcache-th/`, never committed), installed as `db/import/map_cache.dat`. **One at a time with `rathena`:** the same pinned IP and LAN ports, so Docker refuses to start both. Its sniffer attests `server=lab-rathena-th` (ADR-0016 amendment). Its client is the separate copy `C:\RO-rAthena-th\` (`ro_agent.py --profile th`). |

| `media-probe`, `media-recbench`, `media-rec` | probe, recbench, mediarec | The GPU recording plan ([docs/planning/gpu-recording.md](planning/gpu-recording.md); bot-server's Arc only): the media-probe image (iHD + ffmpeg 8; no network, a read-only root, the DRM render node only). `media-probe` and `media-recbench` are one-shot evidence runs; `media-rec` is the RDP recordings' encoder sidecar (ADR-0024: the video IS the recording by default; stage 2's `--also-png` adds the PNG twin), idle until `record_session.py --backend rdp` feeds it raw frames through one named pipe in `/dev/shm/poring-lab-mediarec` (sections 9.1, 9.4). Started and removed only by `guarded_build.py` (`start:media-rec@60`, `rm:media-rec`). |

`sniffer` shares rathena's network namespace, so `--profile sniffer` brings `db` and `rathena` up with it.
To switch to the Thai-data server and back (stop needs no guard; start does):

    scripts/dev.sh --profile sniffer stop sniffer rathena
    python3 scripts/guarded_build.py --sustain 30 --spike 25 start:db-th,rathena-th,sniffer-th@240
    # ... and back:
    scripts/dev.sh --profile th stop sniffer-th rathena-th
    python3 scripts/guarded_build.py --sustain 30 --spike 25 start:rathena,sniffer@240
`vision` works on its own, but it has nothing to look at until `remote` runs.

## Ports

| Host bind | Service | Purpose | Exposure |
|---|---|---|---|
| `HOST_LAN_IP:6900` | rathena | login server | LAN |
| `HOST_LAN_IP:6121` | rathena | char server (advertises `HOST_LAN_IP`) | LAN |
| `HOST_LAN_IP:5121` | rathena | map server (advertises `HOST_LAN_IP`) | LAN |
| `HOST_LAN_IP:8888` | rathena | web-server (`RATHENA_WEB_SERVER=true`): the client's account / character UI settings and emblems over HTTP, at its `AssistAddr` (2026-11-05). Its load routes are **unauthenticated** upstream | LAN |
| `HOST_LAN_IP:3000` | frontend **or** frontend-dev | web console (run one of them) | LAN |
| `HOST_LAN_IP:8000` | backend | `/health`, `/hardware` (the host's CPU/RAM/GPU/temps/power; this listener only), `/economy/*` (the economy dashboard's exports, read-only; this listener only), `/ws/stream`, `/ws/input`, `/transfer/*` (ADR-0004), `/ws/packets` (ADR-0007: LAN viewers only, `VIEWER_NETWORKS`; receive-only) | LAN |
| `HOST_LAN_IP:6080` | desktop | noVNC — **no authentication** | LAN |
| — (`:8001`) | backend | `/internal/agent`; `/ingest/packets` (only from rathena's pinned `10.210.96.6`, the sniffer's namespace) | compose networks only (`default` + the internal `agent` network) |
| — (`:3306`) | db | MariaDB | compose network only |
| — (`:5900`) | desktop | x11vnc | inside the container only |
| outbound → `WIN_HOST:3389` | desktop | the single RDP session | LAN |

**Security:**
- Everything published binds to `HOST_LAN_IP`, never `0.0.0.0`.
- **noVNC has no authentication.** It is view-only by default (`NOVNC_VIEW_ONLY=true`).
- The backend's browser WebSockets require an `Origin` listed in `FRONTEND_ORIGINS`. The `/transfer`
  routes and clipboard paste additionally require one to be *present*, so scripts and the agent can't
  use them.
- The agent API is not published at all. The agent's own network (`agent`, internal) reaches only
  the backend, and the backend refuses it on `:8000` (`/health.agent_network_refused`).
- Host scripts address the backend by its DEFAULT-network IP (`scripts/backend_addr.py`): with two
  networks, a `{{range .Networks}}` template concatenates both addresses.
- Keep all of this on a trusted LAN.
