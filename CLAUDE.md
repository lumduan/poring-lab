# CLAUDE.md — poring-lab

Private research lab: a **vision-based Ragnarok Online agent**, tested **only** against the self-hosted
rAthena in this repo, on the LAN. Start with `README.md` (topology, ports, quickstart) and `docs/adr/`.

## Hard rules (never break these)

1. **Pixels in, mouse and keyboard out.**
   - The agent perceives only through `Env.grab()` and acts only through `Env.send_input()`.
   - No memory reading, no packet injection, and no packet data at decision time.
   - Packet capture (the `sniffer` service) is **offline ground truth only**.
2. **One RDP session** (ADR-0001). Windows client editions allow a single interactive session.
   - Never add a second RDP or VNC path into Windows.
   - Never make the loop retry fast on auth failure (account lockout).
   - Never make it fight a human: exit 5 backs off for 10 minutes.
3. **One input writer** (ADR-0002). Only the backend's `Injector` uses XTest, and every input passes
   `InputMux`.
   - The agent sends to `/internal/agent`.
   - noVNC stays view-only by default.
   - New input paths go **through** the mux, never around it.
4. **Never commit game-client assets** (`*.grf`, `*.gpf`, client exe/dll, a client's `data/` folder),
   `.env`, anything under `data/`, model weights, or packet captures (RO login packets carry
   credentials). `.gitignore` enforces this; don't weaken it.
5. **This host is shared with live 24/7 capture services, Frigate (NVR) and Ollama.**
   - Every lab container keeps `mem_limit` equal to `memswap_limit` (no swap) and `oom_score_adj: 500`.
   - The rAthena build stays capped (`RATHENA_MAKE_JOBS`).
   - vision keeps its VRAM cap (`VISION_MAX_VRAM_FRACTION`).
   - Don't remove these to make something fit; raise the limit consciously instead.

## Invariants worth knowing before you edit

- **Every pipeline message carries `t_mono_ns` and `frame_id`.**
  - `t_mono_ns` is the *sender's* monotonic clock. Backend and vision share the host's
    `CLOCK_MONOTONIC`; the browser is a separate clock domain (ping/pong only). Never subtract across
    domains.
  - `frame_id` is per grabber: the backend stream and the vision agent number their frames
    independently.
- **The Pydantic models in `packages/poring_env/src/poring_env/protocol.py` are the protocol's source
  of truth.**
  - After any change, run `scripts/gen_protocol.sh` and commit both
    `packages/poring_env/schema/protocol.schema.json` and
    `services/frontend/src/lib/protocol.gen.ts`.
  - `test_committed_schema_matches_models` fails on drift. Never hand-edit the generated files.
- **Keys are `KeyboardEvent.code`**, mapped to the evdev code and then the X keycode (+8) in
  `poring_env/keymap.py`. Meta keys are intentionally unmapped.
- **The mux boots in `HUMAN`**, and a handoff always releases what the losing source holds.
  Disconnect cleanup runs as a shielded task (`AppState.release_source`), because handlers can be
  cancelled mid-cleanup.
- **`/internal/agent` accepts only connections that arrived on the internal listener `:8001`**
  (`scope["server"]`). `:8001` is never published.
- **rAthena `char_ip` / `map_ip` are ADVERTISED addresses and must be `HOST_LAN_IP`.** Never set
  `bind_ip` to it. The conf files are rendered from `services/rathena/conf/import/*.tmpl` on every
  container start.
- **FreeRDP is major 3** (`xfreerdp3`, Debian trixie 3.15). Use 3.x flag syntax only (see the README
  table). Credentials go through `/args-from:stdin`, never argv.
- **torch is `2.14.0+cu130`** from the explicit `pytorch-cu130` index declared in the **root**
  `pyproject.toml`. cu126 has no sm_120 kernels; cu132 images refuse to start on this R580 driver.

## Commands

```bash
uv sync                                   # host dev env (poring_env + backend + tools; no torch)
uv run pytest                             # all Python tests
uv run ruff check . && uv run ruff format --check .
uv run mypy                               # strict: packages/poring_env/src + services/backend/src
scripts/gen_protocol.sh                   # protocol schema + TS types
(cd services/frontend && corepack pnpm lint && corepack pnpm typecheck)
scripts/init_env.sh                       # first-time .env
docker compose --profile core --profile remote up -d --build && scripts/smoke_test.sh
docker compose --profile vision run --rm vision python scripts/check_gpu.py
for p in core remote vision sniffer '*'; do docker compose --profile "$p" config -q; done
```

pnpm, ruff and mypy are not installed on the host. Use `corepack pnpm` (the version is pinned in
`services/frontend/package.json`) and `uv run`.

## Key files

| Path | What |
|---|---|
| `compose.yaml` | all services, profiles, limits, LAN binds |
| `packages/poring_env/src/poring_env/` | `env.py` contract, `protocol.py` wire models, `x11.py` (mss + XTest), `remote.py` (MuxedEnv), `keymap.py` |
| `services/backend/src/poring_backend/` | `mux.py` (pure state machine), `state.py` (injector, log, status), `stream.py` (capture hub), `routes_*.py`, `main.py` (two-socket server) |
| `services/desktop/bin/rdp-loop.sh` | the one RDP session + exit-code policy |
| `services/rathena/entrypoint.sh` | conf rendering, DB bootstrap, server supervision |
| `services/vision/src/poring_vision/` | loop skeleton; `detector.py` / `policy.py` hold the TODO stubs |
| `services/frontend/src/` | console: `components/Console.tsx` (sockets), `StreamCanvas.tsx` (input capture) |

## Conventions

- Python 3.12, uv workspace, ruff (100 cols; `E,F,I,UP,B,SIM`), `mypy --strict` on `packages/`.
- Tests: pytest (`asyncio_mode=auto`, importlib mode). vision's loop tests run on the host without
  torch, because its modules import GPU libraries lazily. Keep it that way.
- Conventional commits (`feat(backend): …`, `fix(desktop): …`, `docs: …`).
- No secrets in the repo; everything comes from `.env` (see `.env.example`).
- **Frontend:** Next.js 16, which differs from most training data. Read `services/frontend/AGENTS.md`
  and `node_modules/next/dist/docs/` before changing Next code. The backend URL is read at request
  time (`await connection()`), never baked in at build.
- **ADRs:** in `docs/adr/`, with the `research-doc-metadata` frontmatter.

## Docs to keep in sync

- `README.md`: ports, services, troubleshooting, when any of them change.
- `.env.example`: every variable `compose.yaml` reads.
- `docs/adr/*`: when a decision changes, supersede it explicitly (a new ADR plus a pointer in the old
  one); don't silently edit history.
