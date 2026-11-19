---
doc_type: decision
hypothesis: null
status: "ACCEPTED (decided by Batt 2026-11-17); BUILT 2026-11-17 on feat/any-host (see Implementation)"
role: null
verdict_date: 2026-11-17
verdict_ticket: null
supersedes: null
related: [0016-environment-interlock.md, 0022-vendor-neutral-accelerators.md, 0023-learner-mode.md, ../setup/new-lab-host.md, ../planning/second-install-gaps.md, ../planning/endpoints-as-config.md]
next_action: "Prove it on a machine the lab knows nothing about: Batt's second server (an NVIDIA RTX 5060, 16 GB, his own NAS setup) with his second Windows PC, as a new user who clones the repository and runs ./setup.sh. Every lab assumption it still hits is a row in docs/planning/second-install-gaps.md."
---

# ADR-0026: Any host, nothing locked

- **Status:** ACCEPTED 2026-11-17 by Batt; built the same day (Implementation, below).
- **Batt's words (Thai, translated), 2026-11-17:**
  - On a hard-coded GPU: "If it is this specific, users cannot even start installing and learning.
    The setup should detect the graphics card by itself and recommend it to the user; with no GPU,
    use the CPU instead."
  - "Most users have no NAS: just set where the files are stored in the setup."
  - "Don't lock an IP or anything."
  - "Remember that every user's hardware is different: our project should run on any hardware,
    in containers."
  - Asked whether to do the four items in steps or all at once: "Do all of it." The starter
    detector model: v1 from the teaching-kit branch ("ได้", yes).
  - The test of done: "Suppose you know nothing about my new server, but you must make poring-lab
    run, like a user who clones this project. Otherwise there will be many issues on this project's
    GitHub for us to chase."

## Context

A second copy of poring-lab could not run anywhere but the lab, for reasons a reader of the code
could list in an hour:
- the game PC's address 192.168.1.169 and the lab server's 192.168.1.228 were written into the
  shipped environment set (`config/environments.yaml`): another PC was red `host_mismatch` forever;
- the long-term storage was the lab's NAS mount `/mnt/poring-lab-datasets`, in about 60 files, and
  the vision worker's volume was an NFS mount of 192.168.1.6;
- the Compose project name, the container, network, volume and image names, six host ports, the two
  subnets and rathena's pinned address were fixed, so a second copy on ONE host took over the live
  lab's containers (the 2026-11-17 audit: its setup would have recreated the live rathena with new
  random passwords);
- the host profiles knew only NVIDIA and Intel, and a host with no usable GPU had to pretend to be
  an Intel one; the Run helper started the Intel (OpenVINO) detect server on every host; the detect
  server opened all 8 lab models and refused to start without them;
- a new user had no detector model at all.

## Decision

1. **Every install value has ONE source: the environment, else `.env`, else a default.** The lab's
   values ARE the defaults (or its own `.env` lines), so the live lab changes nothing.
   `scripts/lab_env.py` reads them for host tools; compose interpolates the same keys with the same
   defaults (a test keeps them equal).

   | Key | Default | What follows it |
   |---|---|---|
   | `COMPOSE_PROJECT_NAME` | `poring-lab` | every container, network, volume and image name; `/dev/shm/<project>-*` RAM paths |
   | `LAB_STORE_DIR` | `~/poring-lab-store` | long-term storage (datasets, archives, recordings, scratch archives, deployed models); the vision worker's `/datasets` |
   | `RATHENA_LOGIN_PORT` / `_CHAR_` / `_MAP_` / `_WEB_PORT` | 6900 / 6121 / 5121 / 8888 | rAthena listens on them (char and map are advertised: published X:X), the sniffer's kernel filter and server names, the environment set's server suggestion |
   | `NOVNC_PORT`, `BACKEND_PORT`, `CONSOLE_PORT` | 6080, 8000, 3000 | the published ports, the console's backend URL |
   | `LAB_NET_PREFIX`, `LAB_AGENT_NET_PREFIX` | 10.210.96, 10.210.97 | the two pinned /24s (always inside 10.210.0.0/16, CLAUDE.md rule 6), rathena's pinned .6, the backend's ingest peer and refused subnets |
   | `VISION_WORKER_MEM` | the overlay's (6g; Intel 11g) | the vision worker's memory cap |
   | `DETECTOR_DIR` | `~/.local/share/<project>/detector` | the CPU detector's environment and models (the lab: `/dev/shm/poring-lab-detector`) |

2. **No address of the lab's in anything shipped.** The environment set names this install's server
   and game PC by token (`${HOST_LAN_IP}`, `${WIN_HOST}`, `${RATHENA_*_PORT}`); the backend fills
   them in with its own values. The Windows PC is a person's setting on the Settings page
   (ADR-0023 decision 4, built here).
3. **No NAS assumed.** The storage folder is a plain folder; a NAS is the user's own mount at it, or
   (like the lab) an NFS volume in the machine's own `compose.override.yaml`.
4. **The setup detects the hardware and RECOMMENDS; the person decides; nothing is a dead end.**
   - The GPU: what a container cannot bring is checked (the NVIDIA driver release and the Container
     Toolkit; the Intel kernel driver and the render group). Not ready, or no GPU, or AMD -> the
     recommendation is the new `dedicated-cpu` profile (the CPU detector), WITH the fixes that
     would make the GPU usable. ADR-0022 amendment 2026-11-17. ➡️ AMD since 2026-11-18: a ready
     card (amdgpu, its render node) gets `dedicated-amd`, the Vulkan image (ADR-0022 Amendment
     2026-11-18b; Batt chose option (b)).
   - The sizes: the vision worker's memory from the host's RAM.
   - The starter detector model: v1 (`v1.onnx` of the teaching-kit branch, published 2026-11-06),
     sha256-pinned; `scripts/detector_setup.py` sets up the CPU detector with it.
   - The names, ports and subnets: checked free on the host; a project name whose containers
     another folder created is refused (Batt's own proposal, 2026-11-17).

## Consequences

- A clone on any Linux host with Docker gets a working install from `./setup.sh`, with or without
  a GPU, a NAS or the lab's network; two copies can share one host with two names, ports and
  subnets.
- The lab must keep its own values where they differ from the defaults: `LAB_STORE_DIR` and
  `DETECTOR_DIR` in its `.env`, and its NFS volume in its `compose.override.yaml` (the deploy of
  2026-11-17 wrote them; the compose config was proven equal otherwise).
- The rule for new code: a value a user's machine decides is a key with a default, never a
  constant (Batt 2026-11-13 "everything user-settable" for the bot's own settings; this ADR for
  the install). A grep test guards each family (container names, the NAS path, LAN addresses in
  compose and the environment set).
- Not covered (still lab-only, listed in second-install-gaps.md): the client-derived run-time data
  (GAT, sprites: section 8 of the manual, from the user's own client), the interlock's account
  numbers (row P), the lab characters' table (row R), the map-scoped detector models (lab-trained;
  a new user runs v1).

## Implementation (2026-11-17)

Merged to main as 28802e4f (branch `feat/any-host`, two parallel branches inside it):

| Commit | What |
|---|---|
| 5092dadf | `scripts/lab_env.py`; compose interpolates the project name, ports, subnets, images and the storage volume; `dev.sh -p`; `.env.example`, init_env.sh |
| e5180c85 | the shipped environment set by token; the Windows PC on the Settings page (ADR-0023 decision 4) |
| 7b3a7ca5 | `scripts/detector_setup.py` (the CPU detector + v1 from teaching-kit) |
| c476dadc, 7092b269 | `dedicated-cpu`; `scripts/gpu_ready.py` |
| a40ea815 | the game ports end to end (rAthena's conf templates + entrypoint, the sniffer's filter) |
| 2a149429, 1f780c40 | the storage folder in guarded_build and ~37 scripts (a subagent) |
| b44dbb30, 952b8ddb | every Docker name from the project; `scripts/lab_project.sh` (a subagent) |
| 5bb5826e, 14966a17 | a plain storage folder ships; the S2 recording default from the home |
| f731b071, 06724a22 | guarded_build refuses vision on `dedicated-cpu`; the detect server serves the models present; the Run helper per profile |
| 187e2862, 926a20d5 | the wizard: the name, subnet, port and GPU checks; its screens and dry run |
| e58ac012, 6ffc7fdf | the docs; the runner kept byte-identical (its proofs pin it) |

Checks before the merge: ruff and mypy clean; the full Python suite 6,311 passed, 81 skipped, 2
failed in the worktree (both need gitignored lab data and pass in the main checkout); the frontend
557 passed, 1 skipped, typecheck and lint clean.

Proven live on the lab the same evening:
- Before the merge the lab got its own values (`LAB_STORE_DIR=/mnt/poring-lab-datasets`,
  `DETECTOR_DIR=/dev/shm/poring-lab-detector` in `.env`; its NFS volume in `compose.override.yaml`).
  The merged compose config (`--no-interpolate`, the new defaults filled in) then differed from the
  saved one ONLY by the new environment lines at the lab's values, the gamestream build argument and
  the S2 recording default; volumes, ports, networks and images identical.
- The backend, rathena and sniffer recreates and the four section 2a positive cases:
  docs/demonstrations.md section 2a ("Re-proven again after the 2026-11-17 evening recreates").
- The second-copy case, from another folder on this host (a worktree): `./setup.sh --check` said
  `FAIL Docker name: 'poring-lab' belongs to the poring-lab copy in /home/bot/docker/poring-lab`;
  the dry run planned the name `poring-lab-2`, the subnets 10.210.98/99, the ports 7900 / 7121 /
  8121 / 9888 / 7080 / 9000, and no step on the lab's containers. In the lab's own folder: the name
  and subnets are its own, nothing moves.

Not covered yet (second-install-gaps.md): row U (a new NVIDIA host's GPU server has no `.pt`;
Batt's decision ➡️ FIXED 2026-11-18, Batt "use B": the NVIDIA detect server runs the ONNX,
ADR-0022 Amendment 2026-11-18), row V (the Settings page needs a third browser, by design), the runner's lab-only
`--loot-items` path (`/dev/shm/poring-lab-detector/model`, kept: the runner is pinned by its
proofs), the Thai-client and locale NAS shares of the Thai experiment, and the client-derived run
data (section 8 of the manual).

## Implementation 2026-11-19: two copies on one host (Batt: a LIVE copy beside the dev lab)

Batt, 2026-11-19: "clone the project to `~/bot/`, separate from poring-lab, so both open in Docker
at once; I will use it with another Windows host". This machine then runs TWO labs: the dev lab
(`~/docker/poring-lab`, project `poring-lab`) the agent develops, and the live copy
(`~/bot/poring-lab-live`, project `poring-lab-live`) Batt tests before teaching.

- **Already per copy** (2026-11-17): every Docker name, the ports, the two subnets, the storage
  folder, the compose-mounted RAM folders (`/dev/shm/<project>-detect`, `-hwshm`, `-mediarec`)
  and the capture-backend flock.
- **Made per copy now** (`lab_env.shm`; the lab's names stay as they were):
  - the Run helper's scratch, i.e. its Stop file, its run folders and its logs (`flow_run.SCRATCH`;
    before this, one copy's Stop file stopped the other's Run);
  - the Run's TMPDIR;
  - the window-find file (`ro_agent` / `chat_window` `PANELS_FILE`; before this, the other copy's
    windows would have been read);
  - the route plans (`route_plan.PLAN_DIR`).
- **The Run labels name the copy** (`flowplay-<project>-MMDDHHMM`; the lab keeps `flowplay-`).
  The byte-pinned runner writes every copy's sessions into ONE folder (`dungeon_hunt.DEMO`,
  `/dev/shm/poring-lab-demo`), named for the label, so no copy reads, scores or cleans another
  copy's session.
- **Shared on purpose, read-only:**
  - the client-derived run-time inputs in `/dev/shm/poring-lab-tmp` (GAT, sprites, calibrations);
  - the CPU detector folder (`/dev/shm/poring-lab-detector`: the models and the venv);
  - the guarded-build guard's own files (one heavy step at a time on the host is the point).
- **"One input writer at a time" is per copy** (`flow_run.copy_ps_lines`: only processes whose
  working folder is this copy). Before this, the live helper read the dev lab's Run as its own
  busy writer, and neither copy could play while the other did. Each copy writes to its own
  Windows through its own mux, so two Runs at once are two separate input paths.
- **Tested** by `test_lab_names.py::test_a_copy_s_run_helper_and_readers_keep_their_own_ram` and
  `test_flow_run.py::test_another_copy_s_run_never_makes_this_copy_busy`.
