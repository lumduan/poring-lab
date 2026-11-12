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
   - Scoped exception (Batt 2026-10-17, ADR-0007 Amendment D):
     - `agent-demo` sessions (`scripts/agent_play.py`, the agent playing a competition round)
       may READ the sniffer's archive during play;
     - lab rAthena only, passive only;
     - never the bot or its code;
     - results labelled "packet-assisted".
2. **One Windows session, one display path at a time** (ADR-0001; amended 2026-10-02 with Batt's OK,
   ADR-0009). Windows client editions allow a single interactive session.
   - The path is the RDP session, OR the console-mode stream (Sunshine -> the `gamestream` client:
     the S2 client, or Moonlight-qt) under the capture-backend lock (`scripts/capture_backend.py`).
     Never both. **S2 is the bot's primary path** (ADR-0014, Batt 2026-10-03): frames from the frame
     bus, input from the mux over the `s2-input` socket. RDP is the human's admin path.
   - Never a second client: Sunshine pairs ONLY the lab's gamestream client; its firewall rules admit
     only this host; its web UI is `pc`-only. Its key never leaves the `gamestream-state` volume
     EXCEPT into the lab client's own process memory: Moonlight-qt, or the S2 spike through a sealed
     memfd, non-dumpable, cores off -- never a file (Batt, 2026-10-03).
   - The spike shares that identity, so ONE lab client at a time is enforced at stream start
     (`capture_backend.py stream` and the spike's own lock/process check), not just documented.
   - Never add any other RDP, VNC or streaming path into Windows.
   - Never make the loop retry fast on auth failure (account lockout).
   - Never make it fight a human: exit 5 backs off for 10 minutes.
3. **One input writer** (ADR-0002). Only the backend's `Injector` sends input: XTest, or the S2
   input socket in console mode (`s2-input`, mounted ONLY in backend + gamestream; ADR-0014). Every
   input passes `InputMux`.
   - The agent sends to `/internal/agent`.
   - noVNC stays view-only by default.
   - New input paths go **through** the mux, never around it.
4. **Never commit game-client assets** (`*.grf`, `*.gpf`, client exe/dll, a client's `data/` folder),
   `.env`, anything under `data/`, model weights, or packet captures (RO login packets carry
   credentials). `.gitignore` enforces this; don't weaken it.
   - Client-derived data (GAT, sprites, anything read from a GRF) and knowledge-base data derived
     from rAthena (GPL) are generated locally at run time (`/dev/shm`, `data/`) and never committed
     (Batt, 2026-10-03). The pre-commit hook refuses map and sprite files even with `git add -f`.
   - ONE scoped exception (Batt 2026-11-06, "put them in the branch, so others can clone it at
     once"): the ORPHAN branch `teaching-kit` (the student kit, `teaching/simple-bot`) carries the
     v1 detector's ONNX (`v1.onnx`) and 20 prt_fild08 sample frames from the lab server (our own
     characters only). The repo is PUBLIC, so they are published. `main` and every other branch
     still never carry model weights or client pictures.
   - Reusing open-source RO work: a permissive license means port with attribution; copyleft or
     unclear means ideas only, write our own. Read the LICENSE at the exact commit first and record
     it in `THIRD_PARTY.md`. Never open cheat or memory-patching repos.
5. **This host is shared with live 24/7 capture services, Frigate (NVR) and Ollama.**
   - ➡️ This rule describes ubuntu-docker (VM 103), host profile `shared-nvidia` (the default).
     bot-server declares `LAB_HOST_PROFILE=dedicated-intel` (ADR-0022, Batt 2026-11-07: "no limits
     like this machine"): there guarded_build skips R1-R3 and idles the IO guard, and refuses if a
     capture service ever appears (`scripts/host_profile.py`). Rule 6's pinned subnets and every
     other rule bind on both hosts. `dedicated-nvidia` (ADR-0022 amendment 2026-11-12, Batt) is the
     same dedicated rules on a new host's own NVIDIA card (no VRAM cap); never VM 103.
   - ➡️ **Batt 2026-11-10, bot-server: "we no longer wait for anything of the quant work: this
     machine is our own, the GPU is ours alone; use it fully."** No market-hour waits there: no SET
     hours, no market-open windows. `dataset_ship.py` gates SET hours on a SHARED host only
     (`market_gate_applies`). Recordings, shipping, GPU training and disk-heavy steps run any time.
   - Every lab container keeps `mem_limit` equal to `memswap_limit` (no swap) and `oom_score_adj: 500`.
   - CPU: desktop keeps `cpu_shares: 64` (cgroup v2 weight 12 vs the quant containers' 100) and `cpus: 8`,
     backend `cpu_shares: 256`. xfreerdp 3.15's software decode took 7-15 cores in motion, and 8 was the
     tightest cap with no fps loss (docs/phase0-latency.md). 3.32.1 takes ~4.5 (progressive) or ~1 (AVCthin)
     at 30 fps (h264-plan.md, Arm C). Pinned by `test_guards.py`.
   - The rAthena build stays capped (`RATHENA_MAKE_JOBS`).
   - gamestream (ADR-0009 console client) keeps `cpu_shares: 64`, `cpus: 4`, mem == memswap, a read-only
     rootfs and its pairing-key volume mounted nowhere else (`test_guards.py`).
   - vision keeps its VRAM cap (`VISION_MAX_VRAM_FRACTION`).
   - **GPU sharing rules R1–R3** (infra side, adopted by Batt 2026-10-07). They are HARD limits for any
     GPU work of ours, and they replace the retired 20:00–05:00 GPU window: R1–R3 decide, not the
     clock.
     - **R1:** Ollama + vision VRAM ≤ 9 GiB combined.
     - **R2:** one model at a time. Never run qwen3-vl alongside training or eval; refuse to start
       while Ollama's `/api/ps` shows a loaded model.
       **Co-tenant exception** (Batt 2026-10-28): fit-first's VTON worker is the TOP priority on the
       GPU. Never touch or stop it. Our capped vision steps (guarded_build only; vlm_flag keeps plain
       R2) may run beside it under three conditions, all in `frigate_r3.py`:
       - at the start, the free VRAM covers our cap + 1 GiB;
       - in the run, free VRAM below 1 GiB beside it stops our step (an R2 trip);
       - while it computes, the training yields (10 s step sleep).
       This is `CO_TENANTS`, matched by command line.
     - **R3:** stop if our job slows the Frigate detector by > 5 ms, measured like with like
       (Batt 2026-10-07, `docs/operations/r3-paired.md`).
       - The step's container is paused and unpaused in 3-min OFF/ON windows (60 s for short
         steps).
       - Each ON window is paired with its adjacent OFF windows; only pairs under similar Frigate
         load (±20 % detections/s) count.
       - The trip is the median paired delta > 5 ms over ≥ 4 pairs.
       - Long runs are monitored at 27 min ON / 3 min OFF.
       - ➡️ 2026-11-07 09:00-24:00 ICT ONLY (Batt): camera drops are logged, not a stop
         (`frigate_r3.DROPS_RELAXED`, docs/operations/r3-paired.md); absolute again after it.
       - Stop HARD if any camera drops frames (`skipped_fps`) for 30 s: ABSOLUTE, no baseline,
         IMMEDIATE. The abort logs the fleet detection load.
       - Training never stops for load (Batt, 2026-10-07): the ADAPTIVE DUTY CYCLE sets the step
         sleep from Frigate's live load (100 ms … 2 s; a read-only `state/train-duty` mount).
         After a frame-drop abort it resumes at the slowest level once 15 quiet minutes pass
         (the TEMPORARY extra hold, Frigate's 10-min mean load < 60 det/s, EXITED 2026-10-11 when
         re-proof 2 of mid-epoch checkpoints passed: `TEMP_HOLD_MAX_LOAD = None` in frigate_r3.py).
         The 3rd abort within 2 h caps it at ≥ 800 ms for an hour and NOTIFIES Batt.
         An INCONCLUSIVE paired measurement never stops training (Batt 2026-10-08): it holds the
         slowest level and re-measures; only camera frame drops stop at once.
         `docs/operations/r3-paired.md`.
     - `scripts/frigate_r3.py` (`PairedR3`) implements them, and `guarded_build.py` enforces them on
       every `run:`/`rundev:`/`execdev:` vision step (pre-start refusal + pause/unpause + in-run abort).
       Since 2026-10-10 (option A, docs/operations/vision-long-lived.md 5b) GPU work runs as
       `execdev:` inside ONE long-lived worker (`worker:vision` once per day in a quiet window,
       `worker-stop:vision` at the end); its first CUDA run is the IO burst, later runs are warm.
     - Every abort unpauses the container and VERIFIES the stop: container gone, no process of ours
       on the GPU, else escalation.
     - Ollama is called from HOST scripts only, never by joining a poring-lab container to its
       network (ADR-0005 isolation stays).
   - Don't remove these to make something fit; raise the limit consciously instead.
   - **Heavy builds and pulls go through `scripts/guarded_build.py`**, one image at a time. It
     aborts when capture IO stall exceeds 10%. The host has one shared virtual disk: on 2026-09-29
     an unguarded parallel build pushed capture IO stall from ≤4% to 82–88%. The torch vision
     image (~5 GB of writes) needs an operator-chosen window.
     ➡️ 2026-11-07 09:00-24:00 ICT ONLY (Batt): a `worker:vision` start leaves Frigate's IO stall
     out of quiet_start and its guard (`io_baseline.FRIGATE_IO_IGNORED`); quant still gates.
   - **No whole-file reads of session transcripts or big local files** (a grep over the ~330 MB
     transcript loaded the shared disk twice, 2026-10-02/03). The second hook,
     `scripts/hooks/guard_bigread.py`, refuses grep/rg/cat/awk/sed/sort/… on any `*.jsonl` under
     `~/.claude` and on any file over 50 MB on a disk-backed filesystem (`/dev/shm` and the NAS
     are exempt). Read a byte range instead: `tail -c 5000000 <file> | LC_ALL=C grep -F …`
     (`head -c`/`tail -c`/`dd count=`, ≤ 64 MB). `ionice` is no protection here: the disk's
     scheduler is `none`, which ignores I/O priorities.
   - **No filesystem WALKS outside the repo** (Batt, 2026-10-06, after a `find /` ran for the THIRD
     time). The third hook, `scripts/hooks/guard_walk.py`, refuses find, du, rg, ag, fd, tree,
     `ls -R` and recursive grep in these cases:
     - rooted at `/` or under `/mnt` (the NAS automounts);
     - on any network or automount filesystem;
     - on any disk-backed filesystem (the root LV, Docker's overlays, the other local disk),
       unless inside the repo.
     RAM filesystems (`/dev/shm`) are fine. Roots built at run time (`$VAR`, `$(…)`) are refused.
     Use a specific path, `ls`, `stat`, `findmnt`, `df` or `git ls-files`.
   - **Subagents inherit all of this** (Batt, 2026-10-07). Paste the block in
     `docs/operations/subagent-brief.md` into every subagent brief:
     - no `.venv`, `node_modules`, builds or many-small-file trees on the shared disk;
     - **worktrees live in tmpfs** (Batt, 2026-10-08): the parent creates them with
       `git worktree add /dev/shm/poring-lab-wt/<name> -b <branch>`, never the harness's on-disk
       worktree isolation (a checkout is a many-small-file tree);
     - **no env builds**: the main `.venv` with the worktree's sources first on `PYTHONPATH`;
     - **at most 2 subagents start at once**, staggered;
     - guarded steps only; the docker, bigread and walk hooks apply;
     - remove its worktree and its `/dev/shm` leftovers after the merge.
   - **No disk-heavy steps at the market opens** (Batt, 2026-10-08, after IO trips at ~14:25 two
     days running): no worktrees, env work or cache builds between 09:30 and 10:15 ICT or between
     14:00 and 14:45 ICT, Monday to Friday (not on Saturday or Sunday: Batt 2026-10-09). That
     applies to every agent, the parent included.
     ➡️ VM 103 (shared-nvidia) only. On bot-server none of the market-hour rules apply (Batt
     2026-11-10).

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
   - **Short-lived** (Batt, 2026-10-21): scratch and evidence go to the NAS
     (`/mnt/poring-lab-datasets/scratch-archive/<date>/`) or are deleted, the SAME DAY their
     verdict is recorded. Only run-time inputs (GAT, sprites, calibrations, chat guard) and what a
     running job uses stay. Every report states /dev/shm usage.
   - **Size limits** (Batt, 2026-10-29): `/dev/shm` stays off the root LV only while it fits in
     RAM. Every swap file is on the root LV, so anything that overflows becomes random 4 KiB swap IO
     on the disk shared with capture. On 10-19, reading 0.39 GiB back stalled quant-postgres to
     52.8 %. On 10-29, a 24 GB scratch leak filled swap and the OOM killer took our training.
     - A scratch item of up to 1 GB may go to `/dev/shm`. `/dev/shm` in total stays at or under
       4 GB.
     - Anything larger, and EVERY RECORDING, goes to the root disk as sequential files. Write it
       paced or under the IO guard. For recordings that is `record_session.py`'s default `--out
       /home/batt/poring-lab-rec`, with the tolerant DISK_RULE.
     - Run-time environments that would be many-small-file trees on the shared disk stay in RAM
       and count toward the 4 GB. Today that is `/dev/shm/poring-lab-detector` (its `.venv`,
       ~1.5 GB).
8. **Clipboard and file transfer are human-only** (ADR-0004):
   - never add a clipboard or file message to `AgentToBackend` / `InputEvent`;
   - never mount the `transfer` volume anywhere but desktop and backend;
   - never log paste text or file contents.
   - The mux refuses a bot Ctrl+V / Meta+V / Shift+Insert.
   - Vision has NO X access (ADR-0005 closed on the S2 path, Batt 2026-10-04: vision S2-only +
     option c2):
     - no `x11-unix` mount; it reads the frame bus only;
       ➡️ ADR-0005 Amendment 2026-11-07 (Batt chose gpu-live-detector.md option A): the vision
       WORKER also serves the host bot's detections through ONE unix socket, the host's
       `/dev/shm/poring-lab-detect` at `/detect` (the worker only). Frames in, numbers out; the
       host is the only client and fails closed to the CPU detector;
     - it lives ONLY on the internal `agent` network (10.210.97.0/24, `gateway_mode_ipv4:
       isolated`);
     - the backend refuses that network on every listener but `:8001` (`AgentNetworkGuard`).

     Keep all of them (`test_guards.py`). The acceptance test is
     `services/vision/acceptance/adr0005.py`. Host scripts take the backend's address by the
     DEFAULT network's name (`scripts/backend_addr.py`).

9. **Environment allowlist** (ADR-0006). Automation (BOT/ASSIST) may act only on the sanctioned
   ➡️ **ADR-0023 decision 1 BUILT 2026-11-12** (Batt: "don't lock; we cannot control other people;
   write a warning"). It applies only to an allowed environment the lab CANNOT verify; one with
   packet `signals` is refused (`declaration_not_for_attested`).
   - A person may DECLARE the server owner's permission on the Settings page, as a typed statement.
     It is stored in their own gitignored `settings/`; an import or a shipped file never carries it.
   - The interlock is then green there, labelled "declared by a person, not verified" (`verified`
     false). Packet-attested environments are tried first.
   - Research counts only packet-verified sessions. The agent never declares.
   - The lab agent still runs pilots only on the environments Batt names.
   - NOT built: decisions 3-4 (a learner's Windows gets only the remote program; the Windows host
     as a console setting).
   environments in ADR-0006, verified by an interlock signal, not by judgment. Other players' chat
   data stays local and pseudonymized.
   - **The interlock is built** (ADR-0016 ACCEPTED 2026-10-04): a LOGIC interlock driven by
     the USER-MANAGED environment set (`settings/environments.json`, seeded once from
     `config/environments.yaml`; since 2026-10-06). BOT presses pass only while:
     - an `allowed` environment is attested: the lock is steady, `WIN_HOST` matches, and the
       sniffer's attestation is ≤ 10 s old for a live lab-account session;
     - or, in ASSIST only, a bounded operator window is open (`capture_backend.py window
       login|desktop`, ≤ 120 s, tied to the lock SEQ).

     Releases always pass; green → red releases what the bot holds. Adding a server = a person on the
     Settings page (+ an ADR-0006 entry for this lab), never code. The interlock itself adds no OS lock. Since 2026-10-05 (Batt) the
     lab clients get an EXE-SCOPED layer-1 allowlist: one Block rule per lab exe, for every remote
     address except 192.168.1.13 and loopback; never OS-wide, never the community client. It is
     applied from Batt's elevated console (APPLIED 2026-10-06, read back; group
     `poring-lab lab-only`; 12 rules at first, 2 since 2026-10-06 18:55, one per exe actually
     present, after ADR-0019's cleanup; ADR-0016). Layer 2 is the durable `poring-lab watch` task
     (ADR-0013 amendment; re-triggers every 1 min since 2026-10-06). It is LAB-ONLY, not part of
     any user setup, and has retirement criteria in ADR-0019.
     The SERVER allowlist (host:port per environment) is confirmed by a person on the console's
     Settings page (2026-10-06; human-only writes, below). Its client-side provider and the
     Windows reporting channel are DEFERRED (ADR-0019, rule 10).
     ro_agent opens per-phase windows itself.
   - Concretely:
   - **Official servers and any other public server: forbidden** for every component, in every mode.
   - **The community server:**
     - it counts as forbidden while its permission evidence is pending
       (`docs/environments/community-server.md`);
     - even with evidence, **no agent automation runs there**: its config entry is `pending` with no
       signals (packet capture is not allowed there), so it can never be green;
     - Batt may play there manually, as the human;
     - pixels and input only; no packet capture unless its rules allow it.
   - **Client profiles:** the existing community-server client on Windows stays **untouched**. rAthena
     gets a **separate client copy**. Never modify one to serve the other.
   - **Other players' chat, names and screenshots** stay local (gitignored `data/` or scratch),
     pseudonymized in any dataset, never pushed.

10. **Windows stays clean** ([ADR-0019](docs/adr/0019-windows-stays-clean.md), Batt 2026-10-06).
    - The Windows PC's only job is to run the game and stream it.
    - No poring-lab services, keys or reporting channels on Windows. All intelligence and safety
      logic live on the bot server.
    - The user setup is the game client with its one-time config, plus Sunshine
      (`docs/windows-setup.md`).
    - Official endpoints are updated by dragging a game file onto the Settings page.
    - **Any new need looks for a server-side solution FIRST** (the server, the network, the
      pixels). A Windows-side piece needs a NEW ADR showing why each server-side option fails, and
      Batt's approval. Part B / Part C and ADR-0013's indicator are deferred under this rule.
    - Lab-only exceptions, each with an exit: the `poring-lab watch` task, the agent's shell, and
      the tscon SYSTEM task.

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
- **Human releases with nothing held are not sent** (Batt, 2026-10-07): in ASSIST a human
  `release_all` takes the lease and makes the bot let go.
  - The console sends one on blur, hidden tab or paste ONLY while it holds something
    (`lib/watch.ts` `releaseNeeded`).
  - `AppState.release_source` submits nothing for a source that holds nothing.
  - "Watch only" (per tab, off on load) forwards no input at all; `mayForward` is the backstop in
    `Console.send`. A new `BrowserToBackend` type must be classified in `watch.ts` (typecheck
    fails otherwise).
- **Keys are `KeyboardEvent.code`**, mapped to the evdev code and then the X keycode (+8) in
  `poring_env/keymap.py`. Meta is mapped only for the console toolbar's Win button; the browser never
  forwards physical Meta. `scripts/gen_protocol.sh` also regenerates the frontend's `keycodes.gen.ts`
  (drift-tested).
- **The mux boots in `HUMAN`**, and a handoff always releases what the losing source holds.
  Sole exception (ADR-0002 amendment, 2026-10-03; recreate added 2026-10-04): `guarded_build.py
  restart:backend` or `recreate:backend` in ASSIST writes `state/mux-restore` and removes it once
  the backend is up; only ASSIST, only within 120 s, only with the same lock SEQ. Never BOT; any
  other boot stays HUMAN. Nothing else writes that file.
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

- **The human-only settings store** (2026-10-06): `./settings/` (gitignored) is mounted read-write
  into the BACKEND ONLY (`/lab-settings`; `test_guards.py`). It holds the USER-MANAGED environment
  set (`environments.json`, `envstore.py`) + its audit log and the foreground gate's templates.
  vision can write `./data`, so nothing that decides safety may live there.
  - The set is seeded ONCE from `config/environments.yaml` (Allowed servers become suggestions);
    after that the store wins and the interlock reads ONLY it (fail closed: missing/invalid -> red).
  - Asymmetric rules (`envstore.classify`): tightening easy; loosening Allowed normal; loosening
    Forbidden HARD (typed reason + subject retyped, one per save, audited).
  - Settings writes (`PUT /settings/environments`) only from a LAN browser with the console's
    Origin AND the CSRF token (`GET /settings/csrf`, header `X-CSRF-Token`), at most 20/min per
    client. Never `:8001`, never the lab host itself (`lab_host_peer`: host processes can forge the
    Origin), never `WIN_HOST` (`windows_host_peer`). Every refusal is audited.
  - **The agent never confirms environment entries, by any route**: the first confirmation is a
    person's act.
  - A new YAML key in `environments.yaml` needs the backend running the new schema FIRST
    (`extra="forbid"`: an early edit fails closed with `config_invalid`).
- **The game-file finder** (2026-10-06, `services/frontend/src/lib/gamefile/`, ADR-0016): every
  dropped file is HOSTILE.
  - It is parsed in a Web Worker in the browser, by slices, with a 20 s kill and hard caps
    (`scan.ts` `LIMITS`). It is never uploaded. A GRF gives only its header, its table and the
    clientinfo / externalsettings entries.
  - Encrypted entries are never decrypted. All scanning is linear, with no regex on file text.
  - Extracted values are rendered as TEXT only. Never add `innerHTML` / `dangerouslySetInnerHTML`
    or a link built from them (`gamefile.test.ts` scans `src/`).
  - The default target is BLOCK. Allowed means nothing pre-ticked, a checkbox, and an
    outside-LAN warning.
  - Every page has a nonce CSP (`src/proxy.ts`, `src/lib/csp.ts`). A new script source,
    `eval`, or an inline script breaks it -- keep `csp.test.ts` green and check the pages for
    violations.
- **The typing-only foreground gate** (2026-10-06, `poring_backend/foreground.py`):
  - A bot batch with a key DOWN needs the client's active title bar on a ≤ 400 ms frame of the
    path in use. Its keys are refused otherwise, and held bot keys are released.
  - Clicks, moves, the wheel and releases never ask.
  - A `desktop` operator window (ASSIST) exempts the agent's own console steps. So any ro_agent
    step that types outside the client must open a desktop window first (`ensure_window("desktop",
    ...)`).
  - Templates: `scripts/foreground_template.py install rdp|stream`. BOTH are installed.
    - The S2 `@stream` template was cut 2026-10-07 00:40 in an unattended clean room and measured
      against the pre-registered limits: active 0.0 / 0.4 (≤ 6); visible but unfocused 29.5
      (≥ 15); covered 163.7.
    - It was verified live on the bus: unfocused → refused `client_not_foreground`, active → ok.
    - Re-cut it if the client window or its title moves.
  - Tests that send bot keys get the client in front (conftest); `real_foreground` opts out.
- **The RDP frame bus** (Batt 2026-10-08, `poring_backend/rdp_bus.py`; LIVE since the 17:45
  backend restart): ONE X grabber fans the same frame (its `frame_id` and capture time) out to
  every consumer on the RDP path, as S2 does.
  - It grabs on XDamage (≤ 30 fps) with a 100 ms keepalive, only while the lock says `rdp`.
  - It writes the backend-PRIVATE `/dev/shm/rdp-ring`, never the shared `framebus` volume:
    vision stays S2-only (ADR-0005).
  - `GrabSource` (ro_agent's helper, the bench, the foreground gate) and `CaptureSelector` (the
    console) read it while it heart-beats, else X.
  - `RDP_FRAMEBUS=off` disables it; `/health` `rdp_bus` reports it.
- **Route previews are LIVE only** (Batt 2026-10-08): a walk rule publishes its plan in map CELLS
  (`scripts/route_plan.py`: `enable` once per run; `preview` + the `hook_*` wrappers, which change no
  argument and no result). The daemon `scripts/route_previewd.py` re-projects it from what the
  screen shows and sends `RoutePreview` with `live: true`, which the protocol requires. Never add a
  screen-pixel (one-shot) preview back: it floated off the character as the camera scrolled.
- **The frame-age guard** (2026-10-04, `poring_env/freshness.py`): never act on a stale picture.
  - Presses are refused (`StaleFrame`) when the S2 stream is older than `STREAM_MAX_AGE_MS` (150),
    or the cited frame is older than `CITED_MAX_AGE_MS` (400). Releases always pass.
  - ro_agent judges an action only on a frame decoded after it (`grab_after`).
  - `/health.framebus.stalls` counts freezes.
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
    (UAC). ONE such window: when open-terminal has to open a new one (the old one minimised), it
    closes the others (`close-extra-shells`: WM_CLOSE to exact-title windows, never the front);
  - **before asking Batt for a file drop**, run `ro_agent.py file-check "<path>"` (size, time,
    sha256 on Windows) and give him the printed `Copy-Item … '\\tsclient\transfer\'` line
    (Batt, 2026-10-03). Agent reads/writes in `/transfer` are ADR-0004 exceptions: rare, each one
    in its "Exceptions log";
  - **every typed GAME line passes the UI GATE first** (`scripts/ui_gate.py`, Batt 2026-10-09,
    mandatory): `ro_agent.open_chat` and `bench.close_chat` check the client from pixels (talk@1's
    NPC dialog / menu reader + the four cut windows) and close only by KNOWN steps (Enter on a dialog
    showing CLOSE; a window's own chord); anything else stops. Never press Enter into an unknown state.
    The capture lock picks the template set (`poring_env.ui_sets`, 2026-10-09; gm_state too): rdp ->
    `data/ui_anchors`; console -> `data/ui_anchors/s2` ONLY while its `proof.json` (written only by
    the prove commands) says it is proven with the same bytes; else every typed line is refused.
    Never hand-edit `proof.json`; the live cut is `docs/operations/s2-gate-templates.md`;
  - **the CHAT WINDOW is checked at every game entry and before every typed line** (Batt
    2026-11-05; `scripts/chat_window.py`, docs/client/rathena-client.md "The chat window standard").
    - `ro_agent.enter_game` and `ro_agent.open_chat` (after the UI gate) run it.
    - The standard: docked at the client's bottom-left (left 0, last row 719), 6 lines, the padlock
      CLOSED, and two tabs IN ORDER: Battle Log | Chat (the tab of the replies to typed lines; the
      client's NewTab_2, renamed by Batt's decision 2026-11-05).
    - A moved or resized window is put back only by the client's own controls: F10, the padlock,
      Enter behind the UI gate, a drag of the white input bar.
    - Missing or swapped tabs stop: nothing is typed.
    - Never click the chat window's "+" / "-": they add / delete TABS (11-04);
    cut-off line had left a `>>` prompt that swallowed tscon), then `cls` + a proof bar of a
    fresh width it waits for. A marker of a fixed width proves nothing (a stale one passed);
  - launch via the "Ragnarok Offline" shortcut; close with paced Alt+F4;
  - **every lab client copy carries the AssistAddr override BEFORE its first login** (2026-10-05):
    the 2021 exe opens the kRO data's `AssistAddr` at character select (Gravity's
    `kro-assit.ragnarok.co.kr:3000`). Four loose `data\luafiles514\lua files\service_korea\
    externalsettings_kr*.lub` set it to `127.0.0.1:3000` (client config, never an exe patch; rAthena's
    web auth stays off). Both `C:\RO-rAthena` and `C:\RO-rAthena-th` have them
    (docs/thai-data-experiment.md section 4; ADR-0016 known-forbidden endpoints).
    ➡️ SINCE 2026-11-05 (Batt: fix the red "error when loading the data account settings" at every
    login): the main client's four lubs say `192.168.1.13:8888`, rAthena's own web-server
    (`RATHENA_WEB_SERVER=true`, published on `HOST_LAN_IP:8888`; it serves the client's account /
    character UI settings). Still client config only; the official address is never used
    (docs/client/rathena-client.md "The account settings");
  - the Equip window (Alt+Q / its button) needs button textures the lab's kRO data lacks.
    Without them, modal "Resource File Loading fail" boxes stop the game loop, and the session
    times out at 60 s. Placeholder BMPs were installed in BOTH clients on 2026-10-05 (verified;
    listed in ADR-0019's audit). Any new client copy needs them too;
  - chords are paced (`CHORD_STEP_S`, 60 ms): one instantaneous batch is ignored by the client;
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
  - **The console's display layout is VDD-only** (Batt, 2026-10-03): Sunshine `ensure_only_display`
    plus a registry-persisted VDD-only console layout. Symptom of a drift: the streamed VDD shows an
    empty desktop and a taskbar WITHOUT tray icons (another display became main). Recovery and the
    blind rack path: `docs/operations/console-display.md`. Keep the clean room's heartbeat alive
    while waiting on a human (`cleanroom.py checks --box-min N` + a heartbeat loop): the watchdog
    ends a room after 10 min without one (it did, 2026-10-03 17:19). The loop must STOP when
    `heartbeat` fails: it refuses while a room runs without its watchdog. On 2026-10-04 a fixed 4 h
    unit limit killed a 6 h room's watchdog, and a blind loop kept the room alive ~3 h past its cap.
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
- `sniffer` runs its own SLIM image (`poring-lab/sniffer:local`, ADR-0007 decision 2; first built
  f8c1531, REBUILT 2026-10-08 07:31 from 8533fcd's tree: `attack_request` / `npc_contact` are live,
  each proven by a deliberate positive case, demonstrations.md §2a; REBUILT AGAIN 2026-10-08 17:51
  from 8be6261: the length table's 5 variable packets (chat rooms, 0x097B) + loot@1's floor-item /
  pickup decoders; the §2a positive cases are re-run after it; REBUILT 2026-10-10 02:50 from
  6b90746: the credential scrub LoginScrub (login ports from `SNIFF_LOGIN_PORTS` + every
  login-shaped connection), verified by `scripts/scrub_check.py`, §2a re-run);
  banked captures are re-decoded offline with `guarded_build.py replay:<FROM>..<TO>` (UTC hours; a
  one-off, network-less, read-only container from the sniffer image -- never an exec into the
  live sniffer) and judged per session by `scripts/replay_safety.py`;
  ~~it has NO dev overlay~~ ➡️ **since ADR-0007 Amendment C (ACCEPTED, Batt 2026-10-13) its dev
  overlay runs the decoder CODE from the host** (`packages/poring_packets/src`, read-only, copied to
  tmpfs at each start; `test_guards.py`). The start-time self-test (`poring_packets.selftest`: the
  length table + the credential scrub on dummy secrets) must PASS, or the sniffer refuses to start.
  So a `poring_packets` CODE change goes live with a guarded `recreate:sniffer`, which refuses a dirty
  `packages/poring_packets` and records the commit (SNIFFER_COMMIT: the start log and every capture's
  header). `restart:sniffer` is refused: it would keep the old commit. A DEPENDENCY change still needs
  `build:sniffer`, and `replay:` still decodes with the image's copy. After a sniffer restart the
  interlock says `no_session` until the next login.
  - guarded_build then re-logs the GM in BY ITSELF (Batt, 2026-10-04): `recover gm --retries 0
    --agent-id auto_recover`.
  - It runs only in ASSIST, on a steady rdp/console lock, with the interlock config ok and not
    already green.
  - One attempt: a failure is rc 1 and a report, never a retry loop.
- **Every create/start/restart/recreate/build/pull goes through `scripts/guarded_build.py`** — enforced:
  `scripts/dev.sh` refuses unless the guard is its parent, and the repo's `.claude/settings.json` hook
  (`scripts/hooks/guard_docker.py`) refuses raw `docker`/`docker compose` forms. Don't route around them
  (python subprocess, `$(…)`); add a guarded step instead. Its siblings `guard_bigread.py` and `guard_walk.py` refuse
  whole-file reads of transcripts and big files, and filesystem walks outside the repo (rule 5); all
  three share the tokenizer `_shell.py`.
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
python3 scripts/nas_drop.py open poring-<x> --dataset tank-main/poring-lab/<ds> --host 192.168.1.169
python3 scripts/nas_drop.py close poring-<x> [--lock]   # temporary Dell-only SMB drop, read back
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
| `packages/poring_packets/` | ADR-0007: capture, TCP/RO framing, first-slice decode + the act/turn packets (Phase 3 M3), world state, sniffer; `tables.lock.json` |
| `packages/poring_dataset/src/poring_dataset/{h264,sprites,render,timeline}.py` | Phase 3: the H.264 reader (`iter_every`: one pass), SPR/ACT (nostalro port), `predict_sprite`, `Timeline.state` |
| `services/vision/src/poring_vision/{train,shards}.py` | Phase 3 training (AGPL, ADR-0018): YOLO from NAS tar shards, read-only; run via `guarded_build.py rundev:vision` |
| `scripts/{kb_build,sprite_catalog,build_frame_cache,m4_spawns,gm_vitals}.py`, `poring_env/selfpos.py` | Phase 3: the KB (data/kb), the sprite catalog, the frame cache, the M4 protocol, the GM's vitals from pixels, T0 |
| `scripts/{gen_mapcache_th,mapcache_diff,lab_servers}.py`, compose profile `th` | the Thai-data experiment (2026-10-05): rathena-th/db-th/sniffer-th, ONE AT A TIME with rathena; attestations name their `server` (ADR-0016 amendment); `ro_agent.py --profile th` |
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

## How we work

- **Local disk = ACTIVE working sets only; long-term = the NAS only** (Batt, 2026-10-21).
  - Long-term means datasets, recordings, session evidence, model weights, caches not in active
    use, and archives. They live ONLY on the NAS (`/mnt/poring-lab-datasets/...`; old local items
    under `archive/`, scratch under `scratch-archive/`).
  - The local disk (repo, `data/`, Docker) holds only what is in use. Each item has a retention note
    in `docs/operations/disk-audit.md` (e.g. `data/input_log`: the last 2 days).
  - Move with `guarded_build.py archive:<src>=<dst>`: a paced rsync, a size+count check, then the
    local delete, all under the IO guard. Measure with `measure:du=<path>` (one path a step) and
    `measure:docker-df`.
  - Never park /dev/shm overflow on the local disk. The 10-19/20 shm archive (4.1 GB, with
    symlinks back into /dev/shm) did exactly that; it was moved on 2026-10-21. (➡️ This is about
    LONG-TERM copies. Since 2026-10-29, rule 7's size limits send large ACTIVE scratch and every
    recording to the root disk directly, as a working set until it is shipped to the NAS.)
  - **Every report states our local disk footprint** (and /dev/shm's).
- **End-to-end playable demos are a REGULAR milestone** (Batt, 2026-10-15). They do not wait for
  every piece to be perfect.
  - When: every 2-3 days, or whenever a new skill passes.
  - What: the VERIFIED pieces assembled into a short supervised loop Batt can watch live.
  - How: HUD (perception + decision layers) and the route preview ON; Batt in Watch only;
    time-boxed; unscored; the GM immune (`@monsterignore`) with its fixed state restored before
    and after; the UI gate on every typed line; safety counted from packets.
  - Report: what slowed it down most, RANKED BY TIME LOST, so the next improvements follow what
    Batt actually sees.
  - The first one is farm@0 (2026-10-15 evening, prt_fild08). Each demo is recorded in
    `docs/demonstrations.md` §6 "Playable demos".

## Docs to keep in sync

- `README.md`: ports, services, troubleshooting, when any of them change.
- `.env.example`: every variable `compose.yaml` reads.
- `docs/adr/*`: when a decision changes, supersede it explicitly (a new ADR plus a pointer in the old
  one); don't silently edit history.
