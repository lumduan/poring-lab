# Development and the lab's guarded steps

<!-- Moved from the root README on 2026-11-13 (Batt: "the README only for setup; the rest in docs/"). -->

**Mechanical guard (2026-10-01).** `scripts/dev.sh` refuses `up create build pull run restart start
down rm`, any `--force-recreate`, and an interpolated `config` unless `scripts/guarded_build.py` is its
parent process. For agent sessions, the repo's `.claude/settings.json` PreToolUse hook
(`scripts/hooks/guard_docker.py`) also refuses the same verbs typed as raw `docker` / `docker compose`.
Read-only commands (`ps logs exec inspect config --no-interpolate`) and `stop` stay allowed.
The raw `docker compose ...` lines elsewhere in these docs are for a person on a plain (non-dev)
install; in dev mode use the matching guarded step (`start:`, `restart:`, `recreate:`) instead
(docs/planning/second-install-gaps.md row O).
A second hook (`scripts/hooks/guard_bigread.py`, 2026-10-03) refuses whole-file reads (grep, rg,
cat, awk, sed, sort, …) of session transcripts (`~/.claude/**/*.jsonl`) and of files over 50 MB on
the shared disk; a byte-bounded `head -c`/`tail -c`/`dd count=` (≤ 64 MB) passes.
`scripts/verify_mount.py` checks that containers see the current single-file bind mounts.

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
  python3 scripts/guarded_build.py --sustain 30 --spike 25 build:vision   # ~5 GB of writes
  python3 scripts/guarded_build.py --sustain 30 --spike 25 'run:vision@600=python scripts/check_gpu.py'
  ```
- **Training (Phase 3, AGPL vision component, ADR-0018):**
  - vision reads the NAS datasets **read-only** (`datasets-nas` → `/datasets`, soft NFS, vision only);
  - frames come as tar shards built on the host by `scripts/build_frame_cache.py` (one sequential pass
    per session, split by session) under `/mnt/poring-lab-datasets/.framecache/<id>/`;
  - `rundev:` mounts the host's vision source read-only, so no image rebuild is needed.
  - GPU runs follow the sharing rules R1–R3 (`scripts/frigate_r3.py`, enforced by the guard); the old
    20:00–05:00 window is retired (Batt, 2026-10-07):
  ```bash
  python3 scripts/guarded_build.py --sustain 30 --spike 25 \
    'rundev:vision@3600=python -m poring_vision.train --cache /datasets/.framecache/<id> --smoke'
  python3 scripts/guarded_build.py --sustain 30 --spike 25 \
    'rundev:vision@900=python -m poring_vision.train --cache /datasets/.framecache/<id> --eval /data/train/<run>/weights/best.pt --split test'
  ```
  - **Option A, the long-lived vision worker** (PROVEN + SWITCHED 2026-10-10; `docs/operations/vision-long-lived.md`):
    one idle vision container per day (`compose.vision-worker.yaml`), started once in a measured quiet
    window; each attempt is an `execdev:` inside it, with the same R2/R3, IO-guard and verified-stop
    rules. `train-day.sh` uses it only with `WORKER=1`. Its live proof is
    `scripts/runbooks/worker_proof.py`.
  ```bash
  python3 scripts/runbooks/quiet_start.py -- \
    python3 scripts/guarded_build.py --sustain 30 --spike 25 worker:vision@120
  python3 scripts/guarded_build.py --sustain 30 --spike 25 \
    'execdev:vision@3600=python -m poring_vision.train --cache /datasets/.framecache/<id> --smoke'
  python3 scripts/guarded_build.py worker-stop:vision
  ```
- **Agent loop:**
  ```bash
  docker compose --profile remote --profile vision up -d
  ```
  Set `VISION_DEBUG_BOX=true` to see a box on the overlay without a model.

## Capture backends, benchmark and Phase 2 tools

- **Who owns the Windows session:** `python3 scripts/capture_backend.py status` (host file, every
  container, `/health`). `init`, `drill` (a live lock test), `pair PIN`, `to-console [--yes-tscon]`,
  `to-rdp [--recover]`. The lock file is `state/capture-backend` (gitignored, mounted read-only).
- **Benchmark:** `scripts/bench.py run --backend rdp|console --label NAME`, `reference`,
  `validate-reference PNG`, `table` -- procedure in [docs/benchmarks/SPEC.md](benchmarks/SPEC.md),
  results in [docs/benchmarks/](benchmarks/README.md).
- **Phase 2 (offline):** `scripts/gen_mapcache.py` (pinned rAthena map caches),
  `scripts/record_session.py`, `scripts/calibrate_projection.py`, `scripts/qa_export.py` + the console
  page `/qa` (dev server only). See [docs/phase2-plan.md](phase2-plan.md).
- **UI anchors (ADR-0011):** `scripts/ui_anchors_tool.py capture [--mask-png]` cuts the window
  templates into `data/ui_anchors/` (gitignored); `check` locates the windows on a live or saved frame.

## Development

```bash
uv sync                               # host venv: poring_env + backend + dev tools (not torch)
uv run pytest                         # mux, protocol round trips + schema drift, keymap, app e2e, loop
uv run ruff check . && uv run ruff format --check .
uv run mypy                           # --strict on packages/poring_env (and the backend)
scripts/gen_protocol.sh               # after editing poring_env/protocol.py: schema + TS types
(cd services/frontend && corepack pnpm install && corepack pnpm lint && corepack pnpm typecheck)
```

- **Python:** 3.12, a uv workspace (`packages/poring_env`, `packages/poring_packets`,
  `packages/poring_dataset`, `services/backend`, `services/vision`),
  ruff, and `mypy --strict`.
- **Wire protocol:** the Pydantic models in `poring_env.protocol` are the source of truth. The JSON
  Schema and the TypeScript are generated from them and committed, and CI-style tests fail on drift.
- **vision's GPU dependencies install only inside its container:**
  - torch `2.14.0+cu130`, from the explicit cu130 index declared in the root `pyproject.toml`;
  - ultralytics, with headless OpenCV.
- **Architecture decisions:** [`docs/adr/`](adr/).
