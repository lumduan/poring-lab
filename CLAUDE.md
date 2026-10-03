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
2. **One Windows session, one display path at a time** (ADR-0001; amended 2026-10-02 with Batt's OK,
   ADR-0009). Windows client editions allow a single interactive session.
   - The path is the RDP session, OR the console-mode stream (Sunshine -> the `gamestream` client)
     under the capture-backend lock (`scripts/capture_backend.py`). Never both.
   - Never a second client: Sunshine pairs ONLY the lab's gamestream client; its firewall rules admit
     only this host; its web UI is `pc`-only. Its key never leaves the `gamestream-state` volume
     EXCEPT into the lab client's own process memory: Moonlight-qt, or the S2 spike through a sealed
     memfd, non-dumpable, cores off -- never a file (Batt, 2026-10-03).
   - The spike shares that identity, so ONE lab client at a time is enforced at stream start
     (`capture_backend.py stream` and the spike's own lock/process check), not just documented.
   - Never add any other RDP, VNC or streaming path into Windows.
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
   - CPU: desktop keeps `cpu_shares: 64` (cgroup v2 weight 12 vs the quant containers' 100) and `cpus: 8`,
     backend `cpu_shares: 256`. xfreerdp 3.15's software decode took 7-15 cores in motion, and 8 was the
     tightest cap with no fps loss (docs/phase0-latency.md). 3.32.1 takes ~4.5 (progressive) or ~1 (AVCthin)
     at 30 fps (h264-plan.md, Arm C). Pinned by `test_guards.py`.
   - The rAthena build stays capped (`RATHENA_MAKE_JOBS`).
   - gamestream (ADR-0009 console client) keeps `cpu_shares: 64`, `cpus: 4`, mem == memswap, a read-only
     rootfs and its pairing-key volume mounted nowhere else (`test_guards.py`).
   - vision keeps its VRAM cap (`VISION_MAX_VRAM_FRACTION`).
   - Don't remove these to make something fit; raise the limit consciously instead.
   - **Heavy builds and pulls go through `scripts/guarded_build.py`**, one image at a time. It
     aborts when capture IO stall exceeds 10%. The host has one shared virtual disk: on 2026-09-29
     an unguarded parallel build pushed capture IO stall from ≤4% to 82–88%. The torch vision
     image (~5 GB of writes) needs an operator-chosen window.
   - **No whole-file reads of session transcripts or big local files** (a grep over the ~330 MB
     transcript loaded the shared disk twice, 2026-10-02/03). The second hook,
     `scripts/hooks/guard_bigread.py`, refuses grep/rg/cat/awk/sed/sort/… on any `*.jsonl` under
     `~/.claude` and on any file over 50 MB on a disk-backed filesystem (`/dev/shm` and the NAS
     are exempt). Read a byte range instead: `tail -c 5000000 <file> | LC_ALL=C grep -F …`
     (`head -c`/`tail -c`/`dd count=`, ≤ 64 MB). `ionice` is no protection here: the disk's
     scheduler is `none`, which ignores I/O priorities.

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
       [issue #2](https://github.com/lumduan/poring-lab/issues/2), `blocks-phase-4`);
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
- **The rathena runtime is ONE tar in the image** (`/opt/rathena-runtime.tar`, 1784 entries, ~79 MB).
  - It is built inside the compile tmpfs, and the entrypoint extracts it into the 192m tmpfs at
    `/opt/rathena` on every start. So the ~1600 files never become per-file metadata on the shared disk.
  - The templates live in `/opt/rathena-conf-templates` (outside the tmpfs).
  - Keep the `clients will be sent to char … and map …` log line: `smoke_test.sh` greps for it.
  - Local source patches go in `services/rathena/patches/*.patch` (applied with `--fuzz=0`).
- **Thai is tis620 end to end.**
  - db `--character-set-server=tis620`; every `*_codepage: tis620`.
  - `chatlog.message` is `VARBINARY(300)` (byte-exact CP874 ground truth: decode `HEX(message)` as cp874).
  - The entrypoint refuses a non-tis620 database. Thai names: `char_name_option 2`, plus the
    0xAD (ญ) `TRIM_CHARS` patch.
- **Inter-server credentials are at most 23 characters** (`RATHENA_SERVER_USER`/`PASSWORD`). char and
  map truncate them to 24-byte buffers and login then rejects them.
- **In dev mode, bring core services up with `guarded_build.py start:<svc>@<s>`**, never `up:`
  (refused: it would recreate backend/desktop without their mounts).
- **FreeRDP is major 3**: **3.32.1** from trixie-backports since 2026-10-01 (Arm C). `xfreerdp3` is a link
  to `xfreerdp`, and the rollback image is `poring-lab/desktop:freerdp-3.15`. Use 3.x flag syntax only (see the README
  table). Credentials go through `/args-from:stdin`, never argv.
- **torch is `2.14.0+cu130`** from the explicit `pytorch-cu130` index declared in the **root**
  `pyproject.toml`. cu126 has no sm_120 kernels; cu132 images refuse to start on this R580 driver.

- **Packet ground truth (ADR-0007) never reaches the agent.**
  - `/ingest/packets` takes only the internal port and rathena's pinned `10.210.96.6`.
  - `/ws/packets` takes only `VIEWER_NETWORKS` (LAN browsers): the compose subnet, *gateway
    included*, is refused, because a container dialling the published port arrives from the
    gateway with any Origin it likes.
  - `poring_packets` is never imported by `poring_env`, never installed in vision, and never
    mounted there (`captures`).
  - Entity identity is the block id (AID @5), not the char_id.
- **Sensitive agent input:** `AgentInput.sensitive` gives one summary line in the input log (counts
  and timing). A batch that leaves a key or button held is refused (`sensitive_unbalanced`).
  Credentials are only ever typed that way.
- **Human secret typing** (ADR-0004 amendment c):
  - The console's "Secret typing" toggle (`SecretInput`, `Status.human_secret`) logs human keys
    without codes, and a paste without length or digest.
  - Any password typed or pasted through the console needs it on.
  - Human pastes log no digest and no length, in either mode (decided 2026-10-02).
  - `scripts/purge_input_log.py` removes printable human typing from old logs. The input log
    appends under a shared `flock`.
- **Driving Windows (ro_agent):**
  - **never the Run dialog**: Defender's ClickFix detection;
  - **the agent's own terminal is the "poring-lab shell" desktop shortcut** (Batt, 2026-10-03):
    `ro_agent.py open-terminal` reuses or opens it. The shortcut is `wt.exe -w new new-tab --title
    "poring-lab shell" --suppressApplicationTitle -d C:\RO-rAthena powershell.exe -NoLogo`, NOT
    "Run as administrator". It types only after that exact tab template is in front AND a
    pixel-checked marker says not elevated; any mismatch stops. Elevated consoles stay Batt's
    (UAC);
  - launch via the "Ragnarok Offline" shortcut; close with paced Alt+F4;
  - **verify the target is in front before typing**: client = active title-bar signature, console
    = tab template, secrets re-checked every 4 characters;
  - this client fails ("Failed to Connect to Server") unless the server is picked within ~1–2 s of
    the list;
  - the RDP session runs as the **standard** Windows account `poring-lab` (`WIN_LAB_*`). Anything
    needing admin is the operator's: he opens the elevated console and answers UAC. The agent never
    approves UAC, and .env never holds his Windows credentials;
  - secrets on Windows go only through `Read-Host -AsSecureString` as a sensitive batch
    (`ro_agent.py console-secret`), never a command line (PSReadLine history);
  - the lab runs `RDP_GFX=progressive`. On FreeRDP 3.32.1 it delivers 30 fps outdoors with 0 skips
    and p95 packet→frame 157 ms. `AVCthin` matches it at ~1/5 of the CPU but is lossy
    (docs/h264-plan.md, Arm C).
  - FreeRDP 3.32.1 claims X CLIPBOARD (empty) on every Windows-side copy, and the watchdog clears it.
    So `foreign_owner_clears` rising right after a Windows copy is expected (ADR-0004 amendment b).
- **The capture-backend lock decides who owns the ONE Windows session** (ADR-0009): `state/capture-backend`
  (KEY=word lines, `BACKEND=rdp|console`, `SEQ`, `PHASE`), a directory mounted read-only at `/lab-state`.
  - Its ONLY writer is `scripts/capture_backend.py` (`status`, `init`, `drill`, `to-rdp [--recover]`,
    `to-console [--external|--cleanroom]`, `stream --variant`, `hold`, `pair`): atomic rename, then
    read back on the host and in every container. Every writing command holds an exclusive flock
    (`/dev/shm`), so the clean-room runner, its watchdog and a human never write at once.
  - The clean room (2026-10-03, ADR-0009): `to-console --cleanroom` leaves the session on the
    console (REASON `cleanroom`); `stream --variant V1|V1gdb|V2|V3` writes the whitelisted
    `state/gamestream-variant` (CLIENT/WM/GDB_AFTER_S) that gamestream-loop.sh reads at each stream
    start; `hold` ends the stream (/cancel) and keeps the session there; streams are one-shot.
    `scripts/cleanroom.py` drives it, with a detached watchdog (`systemd-run --user`) that runs the
    clean to-rdp on a time box or the hard cap. After a host reboot mid-run: `to-rdp --recover` first.
  - The console shows the clean room from `state/cleanroom` (VARIANT/BOX_UNTIL/HARD_CAP, display
    only, same writer: `to-console --cleanroom --hard-cap`, `stream --box-until`; to-rdp removes it).
    The backend honours it only while the lock's REASON is `cleanroom*`. The banner's D3D/"ro_agent
    recover" advice is RDP-only (`services/frontend/src/lib/banner.ts`).
  - rdp-loop.sh connects only while it says `rdp`, and never while a Moonlight window is on the display;
    every wait wakes when the lock changes. Fail closed: no mount / malformed -> `hold`; mounted dir
    without the file -> `rdp`. The bash and Python readers are parity-tested (`test_capture_lock.py`).
  - In console mode the backend refuses paste (`console_backend`) and reports paste/files unavailable;
    `ro_agent` refuses on hold, during a handover, or when host file and `/health` disagree;
    `rdp_reconnect.sh` refuses unless `rdp`.
  - The bot may never hold Ctrl+Alt+Shift (`stream_hotkey_bot`): Moonlight's own hotkeys (+V types the
    X clipboard into Windows, +Q quits).
- **Human pastes are scrubbed** (ADR-0004 amendment): after every paste, the backend re-owns CLIPBOARD
  empty so Windows' copy is replaced. Released text otherwise stayed pasteable for over an hour.
  Paste audits log the event and its time only: no length, no digest (ADR-0004 amendment c,
  Batt 2026-10-02; even a 12-hex prefix confirmed a guessed password).
  `/health clipboard.rdp_empty_claims` counts FreeRDP 3.32's own (empty) CLIPBOARD claims apart from
  `foreign_owner_clears`, which stays the alarm (ADR-0004 amendment b).

## Dev mode (the default; there will be no disk split -- Batt, 2026-10-01)

- `compose.dev.yaml` via `scripts/dev.sh`:
  - `backend` runs the host source (read-only mount on `PYTHONPATH`); `python3 scripts/guarded_build.py --sustain 30 --spike 25 restart:backend@30`
    applies code changes;
  - `frontend-dev` runs `next dev` with all writes on tmpfs.
- `rathena` gets `entrypoint.sh` + `conf/import/groups.yml` bind-mounted, so the agent and GM accounts
  and group 20 apply with a recreate, not a build.
- `sniffer` runs the backend image with the host `poring_packets` source (`build: !reset`; it can
  never retag the stub over `poring-lab/backend:local`).
- **Every create/start/restart/recreate/build/pull goes through `scripts/guarded_build.py`** — enforced:
  `scripts/dev.sh` refuses unless the guard is its parent, and the repo's `.claude/settings.json` hook
  (`scripts/hooks/guard_docker.py`) refuses raw `docker`/`docker compose` forms. Don't route around them
  (python subprocess, `$(…)`); add a guarded step instead. Its sibling `guard_bigread.py` refuses
  whole-file reads of transcripts and big files (rule 5); both share the tokenizer `_shell.py`.
- After writing `.env` use `scripts/rotate_secrets.py set|rotate` (read-back built in); after editing a
  mounted file run `scripts/verify_mount.py` before claiming it took effect.
- **Single-file bind mounts (rdp-loop.sh, entrypoint.sh, groups.yml…) follow the INODE.** `sed -i`
  and most editors write a new file, so the container keeps the old one silently (three codec tests
  ran a stale `rdp-loop.sh` on 2026-10-01). Edit in place (`open(..., "w")`), or re-bind with a guarded
  `python3 scripts/guarded_build.py --sustain 30 --spike 25 recreate:<svc>@90`. A running
  `rdp-loop.sh` keeps its parsed functions: restart it with `supervisorctl stop rdp`, wait for zero
  xfreerdp3 processes (ADR-0001: never two sessions), then `supervisorctl start rdp`.
- Do not "fix" this by building images casually. An image build is a deliberate step: `scripts/guarded_build.py`
  (tolerant guard) in an operator-chosen window. There will be **no disk split** (Batt, 2026-10-01): keep the guards
  and the tar/tmpfs approach, and don't plan around a split.
  - Exception (Batt, 2026-09-30): rathena and db were built, pulled and started with the TOLERANT guard
    (`--sustain 30 --spike 25`) because quant capture gaps are backfilled at EOD. Other images still
    wait.
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
python3 scripts/guarded_build.py --sustain 30 --spike 25 'run:vision@600=python scripts/check_gpu.py'
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
| `services/frontend/src/` | console: `components/Console.tsx` (sockets), `StreamCanvas.tsx` (input capture), `PacketTimeline.tsx` |
| `packages/poring_packets/` | ADR-0007: capture, TCP/RO framing, first-slice decode, world state, sniffer; `tables.lock.json` |
| `scripts/gen_packet_tables.py` | build-time length tables from pinned rAthena + OpenKore (never committed) |
| `services/backend/src/poring_backend/{routes_packets,packets,display}.py` | ingest + viewer channel; black-screen detector |
| `scripts/ro_agent.py`, `measure_motion.py`, `measure_delay.py`, `pressure_sampler.py` | agent login/recovery/GM checks; motion and packet→frame benchmarks; quant pressure ±5 min |

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
