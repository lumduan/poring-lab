---
doc_type: runbook
hypothesis: null
status: ACTIVE (written 2026-10-23; nothing built)
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../adr/0001-single-rdp-session.md, ../h264-plan.md, ../../services/desktop/Dockerfile]
next_action: "Nothing until a FreeRDP 3.32.1 regression needs a rollback. Then build it in an operator-chosen window, as below."
title: "Rebuilding the FreeRDP 3.15 rollback image from git (the image itself was removed 2026-10-23)"
date: 2026-10-23
owner: Batt
---

# Rebuilding the FreeRDP 3.15 rollback image from git

**Why this exists:**
- The rollback image `poring-lab/desktop:freerdp-3.15` was removed on 2026-10-23 at ~03:15 ICT, in
  the host's approved image cleanup (home-assistant-ops OS-039 phase 3 A).
- Batt's decision 8 on the 2026-10-23 overnight report: "FreeRDP 3.15 rollback: don't rebuild now;
  document how to rebuild it from git; I'll edit CLAUDE.md:288."
- **Nothing is built by this document.**

## What the 3.15 image is

The desktop image is two FreeRDP layers on one Dockerfile (`services/desktop/Dockerfile`):
- **The dependency layer:** trixie's `freerdp3-x11=3.15.0+dfsg-2.1+deb13u*` plus Xvfb, x11vnc,
  websockify and supervisor. It asserts `version 3.15`.
- **The Arm C layer:** the second `RUN`, which adds trixie-backports and upgrades ONLY FreeRDP to
  `3.32.1+dfsg-1~bpo13*`. It was added by 3057f13 (2026-10-01), and its assertions are
  `version 3.32`, `WITH_GFX_H264=ON` and FFmpeg.

**The 3.15 image is today's Dockerfile with the Arm C layer removed.** Everything after that layer
stays as it is: noVNC, the `desk` user, `bin/` (rdp-loop.sh), the 1440x900 session and the
healthcheck. So it keeps every desktop change made since 2026-10-01; it is not the
2026-09-30 tree.

## The recipe

Run it in an operator-chosen window. It is an image build under the IO guard: never in
09:30-10:15 or 14:00-14:45 ICT on weekdays, and start at about :06.

1. **Make a tmpfs worktree** (never an on-disk checkout):

        git -C /home/batt/docker/poring-lab worktree add /dev/shm/poring-lab-wt/freerdp315 -b ops/freerdp-315-rollback main

2. **Edit its Dockerfile.** In `/dev/shm/poring-lab-wt/freerdp315/services/desktop/Dockerfile`:
   - delete the Arm C `RUN` block: from `RUN echo 'deb http://deb.debian.org/debian trixie-backports main'`
     to its last line, `... && rm /tmp/bc` (lines 38-47 at 6b6ec1c), and its comment block, lines
     35-37;
   - name the stage: `FROM debian:trixie-20260918-slim AS rollback`.
   - Nothing else changes.
3. **Build it under the guard WITHOUT touching `:local`.** Run the WORKTREE's copy of the guard. Its
   `REPO` is the worktree, so the compose config and the build context come from there.

        python3 /dev/shm/poring-lab-wt/freerdp315/scripts/guarded_build.py --sustain 30 --spike 25 target:desktop:rollback:poring-lab/desktop:freerdp-3.15

   - `target:` runs `docker build --target <stage> -t <image>` with the service's compose build args
     (`target_build_cmd`, `scripts/guarded_build.py:989-999`).
   - Never use `build:desktop`: it would retag `poring-lab/desktop:local`, the image the lab runs.
   - **Not tested:** this exact invocation from a worktree.
4. **Check it.**
   - The build itself asserts `xfreerdp3 --version` = 3.15.
   - Then read it back: `docker image inspect poring-lab/desktop:freerdp-3.15`.
5. **Remove the worktree and its branch.** The branch is never merged.

        git -C /home/batt/docker/poring-lab worktree remove /dev/shm/poring-lab-wt/freerdp315
        git -C /home/batt/docker/poring-lab branch -D ops/freerdp-315-rollback

## Rolling back (a separate decision, Batt's)

Point `:local` at the rollback, then recreate the desktop under the guard:

        docker tag poring-lab/desktop:freerdp-3.15 poring-lab/desktop:local
        python3 scripts/guarded_build.py --sustain 30 --spike 25 recreate:desktop@90

- ADR-0001: never two RDP sessions. The recreate replaces the one session.
- If the docker hook refuses `docker tag`, a guarded step is needed. Never route around the hook.
- **Going forward again:** a guarded `build:desktop` from main restores 3.32.1 as `:local`.

## Caveats

- **Not byte-identical to the removed image.**
  - The apt globs pick the newest `3.15.0+dfsg-2.1+deb13uN` in trixie at build time (security
    point releases).
  - If trixie no longer carries 3.15.0, build that layer from `snapshot.debian.org` at 2026-09-18,
    the base image's date.
- **rdp-loop.sh's comments name 3.32's exit codes 160 / 161.** 3.15 never returns them; the enum
  is identical up to 159 (3057f13). `scripts/rdp_reconnect.sh` counts both binary names.
- **3.15's cost** (docs/h264-plan.md, Arm C): progressive 9 fps outdoors / 7 indoors, against
  3.32.1's 30 / 17; 6.8 cores; and packet -> frame p95 over 1.5 s. A rollback is for a 3.32.1
  regression, not for speed.
- **CLAUDE.md:288 still names the removed image.** That edit is Batt's (decision 8).
