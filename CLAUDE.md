# CLAUDE.md — poring-lab

Private research lab: a **vision-based Ragnarok Online agent**. There are exactly **two sanctioned
environments** ([ADR-0006](docs/adr/0006-sanctioned-test-environments.md)):
- the self-hosted rAthena in this repo, on the LAN, for controlled ground truth;
- a community bot-testing server, for multi-party social research.

Official servers and every other public server are forbidden. Start with `README.md` (topology,
ports, quickstart) and `docs/adr/`.

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
   - **Heavy builds and pulls go through `scripts/guarded_build.py`**, one image at a time. It
     aborts when capture IO stall exceeds 10%. The host has one shared virtual disk: on 2026-09-29
     an unguarded parallel build pushed capture IO stall from ≤4% to 82–88%. The torch vision
     image (~5 GB of writes) needs an operator-chosen window.

6. **Never put a Docker network on a 192.168.x subnet on this host.** The LAN uses 192.168.1, 110, 111, 112
   and 120, and Docker can't see the segments behind the router. On 2026-09-29 an auto-assigned
   192.168.96.0/20 cut the operator's MacBook off from VM 103 (home-assistant-ops OS-034).
   `compose.yaml` pins `10.210.96.0/24`; keep it pinned. Health check:
   `ip route get 192.168.110.55` must say `via 192.168.1.1`, never `dev br-…`.

7. **Scratch and evidence files go to `/dev/shm`, never host `/tmp`** (Batt, 2026-09-30). Host `/tmp`
   sits on the same root LV as live capture; `/dev/shm` is RAM. That covers screenshots, frames,
   probe scripts and temporary compose overlays. Host `/tmp` itself is not reconfigured.
   - Keep test and tool caches off the disk too: `TMPDIR=/dev/shm/...`, `pytest --basetemp`,
     `mypy --cache-dir=/dev/null`, `ruff --no-cache` (see Commands).
8. **Clipboard and file transfer are human-only** (ADR-0004):
   - never add a clipboard or file message to `AgentToBackend` / `InputEvent`;
   - never mount the `transfer` volume anywhere but desktop and backend;
   - never log paste text or file contents.
   - The mux refuses a bot Ctrl+V / Meta+V / Shift+Insert.
   - Vision's direct X access is the open gap, [ADR-0005](docs/adr/0005-vision-x-access.md). It
     blocks Phase 4.

9. **Environment allowlist** (ADR-0006). Automation (BOT/ASSIST) may act only on the sanctioned
   environments in ADR-0006, verified by an interlock signal, not by judgment. Other players' chat
   data stays local and pseudonymized. Concretely:
   - **Official servers and any other public server: forbidden** for every component, in every mode.
   - **The community server:**
     - it counts as forbidden while its permission evidence is pending
       (`docs/environments/community-server.md`);
     - even with evidence, **no agent automation runs there until the interlock exists** (the
       GitHub issue labelled `blocks-phase-4`);
     - Batt may play there manually, as the human;
     - pixels and input only; no packet capture unless its rules allow it.
   - **Client profiles:** the existing community-server client on Windows stays **untouched**. rAthena
     gets a **separate client copy**. Never modify one to serve the other.
   - **Other players' chat, names and screenshots** stay local (gitignored `data/` or scratch),
     pseudonymized in any dataset, never pushed.

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
- **Dropped messages are never silent** (ADR-0004, decision 4). All three WebSocket channels read
  through `routes_public.read_message`. A drop is counted in `/health` `dropped_messages`, logged as a
  rate-limited WARNING (type and reason only), and answered with an `ErrorReply`. A new channel must
  use the same reader. Mux refusals are counted in `input_refused`.
- **The clipboard lives on its own X connection and thread** (`clipboard.py`, python-xlib is not
  thread-safe). Two python-xlib traps found the hard way:
  - `SelectionClear`'s field is `atom`, not `selection`;
  - extension event classes are cloned per display, so match XFixes events by
    `isinstance(e, xfixes.SelectionNotify)` plus `sub_code`, never by the subclass.
  - `scripts/clipboard_x11_check.py` exercises it against a real Xvfb.
- **`RDP_CLIPBOARD` / `RDP_DRIVES` are keywords, not flags** (`rdp-loop.sh`): `off|text-to-remote`
  and `""|transfer`. Anything else stays off. The backend reads the same two variables.
- **The console's keyboard focus is a hidden `<textarea>`** (`StreamCanvas.tsx`), so the browser can
  paste natively. `keyDecision()` in `services/frontend/src/lib/keys.ts` decides:
  - forward: prevented and sent by code;
  - paste: ⌘V on macOS, Ctrl+V elsewhere, Shift+Insert. It is not prevented and **never forwarded**;
    the paste event becomes a `ClipboardPaste`;
  - local: left to the viewer's OS.
  - Don't move key capture back to a non-editable element, or ⌘V stops working.
- **Keys are `KeyboardEvent.code`**, mapped to the evdev code and then the X keycode (+8) in
  `poring_env/keymap.py`. Meta is mapped only for the console toolbar's Win button; the browser never
  forwards physical Meta. `scripts/gen_protocol.sh` also regenerates the frontend's `keycodes.gen.ts`
  (drift-tested).
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

## Dev mode (in use until the disk split)

- `compose.dev.yaml` via `scripts/dev.sh`:
  - `backend` runs the host source (read-only mount on `PYTHONPATH`); `scripts/dev.sh restart backend`
    applies code changes;
  - `frontend-dev` runs `next dev` with all writes on tmpfs.
- Do not "fix" this by building images. Builds wait for the weekend disk split (docs/ROADMAP.md).
- Inside `frontend-dev`: `docker exec -w /app poring-lab-frontend-dev-1 corepack pnpm lint`, and
  likewise `typecheck` and `test`.
- The 24 h IO baseline: `scripts/io_baseline.py` → `data/metrics/io_pressure_*.csv`; stop it with
  `kill $(cat data/metrics/io_baseline.pid)`.

## Commands

```bash
uv sync                                   # host dev env (poring_env + backend + tools; no torch)
# Disk-light (rule 7): nothing lands in host /tmp or in on-disk caches.
export PYTHONDONTWRITEBYTECODE=1 TMPDIR=/dev/shm/poring-lab-tmp && mkdir -p "$TMPDIR"
uv run pytest -p no:cacheprovider --basetemp="$TMPDIR/pytest"   # all Python tests
uv run ruff check --no-cache . && uv run ruff format --check --no-cache .
uv run mypy --cache-dir=/dev/null         # strict: packages/poring_env/src + services/backend/src
scripts/gen_protocol.sh                   # protocol schema + TS types
(cd services/frontend && node --test src/lib/*.test.ts)   # unit tests, no deps needed
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
| `services/backend/src/poring_backend/clipboard.py` | ADR-0004: X CLIPBOARD owner + watchdog (own thread) |
| `services/backend/src/poring_backend/routes_transfer.py` | ADR-0004: `/transfer/*` (public port, Origin required, audit log) |
| `services/backend/src/poring_backend/drops.py` | never-silent drops: counter, rate-limited WARNING, `ErrorReply` |
| `services/desktop/bin/rdp-loop.sh` | the one RDP session + exit-code policy + ADR-0004 keywords |
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
