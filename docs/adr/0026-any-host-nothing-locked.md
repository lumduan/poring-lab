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
     would make the GPU usable. ADR-0022 amendment 2026-11-17.
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

Branch `feat/any-host`; the commits are listed in the merge.
