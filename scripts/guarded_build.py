"""Run disk-heavy docker steps ONE AT A TIME and back off the moment live capture suffers.

This host keeps Docker, the quant capture engines and their databases on ONE virtual disk (no IO
isolation). On 2026-09-29 an unguarded parallel build pushed the capture engines' IO stall from
<=4% to 82-88%. So on this host, heavy builds/pulls go through this script.

It watches the IO *full*-stall rate of the capture cgroups (from cumulative `total=` counters, not
avg10) over a --window-second rolling window. A breach is:
  * default (strict): any window above --threshold percent;
  * with --sustain S: the SAME cgroup above --threshold for S seconds in a row;
  * with --spike P: any window above P percent, whatever --sustain says.
On a breach:
  build:<svc>   docker compose build <svc>                  -> SIGINT (build cancelled)
  pull:<svc>    docker compose pull <svc>                   -> SIGINT
  up:<seconds>  compose up -d (core+remote), watch seconds  -> compose stop
                REFUSED while the dev overlay (scripts/dev.sh) runs: a plain `compose up` would
                recreate backend/desktop without their mounts and build the production frontend.
  target:<svc>:<stage>:<image>
                docker build --target <stage> -t <image> with the service's compose build args (e.g.
                the rathena toolchain stage for scripts/gen_packet_tables.py)  -> SIGINT
  start:<svc>[,<svc>...][@<seconds>]
                scripts/dev.sh --profile core up -d --no-build <svcs>, watch seconds (default 180)
                -> stops ONLY those services. The dev-mode way to bring up db/rathena.
  restart:<svc>[,<svc>...][@<seconds>]
                scripts/dev.sh restart <svcs> (e.g. backend after a code change), then watch.
                With backend: if the mux is in ASSIST, ASSIST comes back by itself (ADR-0002
                amendment, 2026-10-03): state/mux-restore (MODE=ASSIST, the lock SEQ, WRITTEN,
                OWNER) is written before the restart and REMOVED as soon as the new backend answers
                /health, so a later crash or unplanned restart still boots HUMAN. BOT is never
                restored; a handover in between (SEQ changed) or a marker over 120 s old -> HUMAN.
  recreate:<svc>[,<svc>...][@<seconds>]
                the same with --force-recreate (re-binds single-file mounts, e.g. after a
                bind-mounted script was replaced by a new inode). With backend: ASSIST comes back
                by itself, on the same marker conditions as restart (Batt, 2026-10-04). An
                unguarded force-recreate of desktop on 2026-10-01 hit 30.8 % quant-postgres
                io_full for 10 s.
                With sniffer (restart or recreate; Batt, 2026-10-04): a sniffer restart loses the
                account binding, so the environment interlock says no_session until the GM logs in
                again. After the step settles, the GM is re-logged in BY ITSELF
                (`ro_agent.py recover gm --retries 0 --agent-id auto_recover`, reason
                auto_recover) ONLY when the mux is ASSIST (never BOT), the capture lock is
                rdp/steady or console/steady, the interlock config is ok and it is not already
                green. One attempt: a failure stops here (rc 1) and is reported, never retried.
  rm:<svc>[,<svc>...]
                scripts/dev.sh rm -s -f <svcs>: stop and REMOVE those containers (never volumes or
                images); the next start recreates them identically from compose. For a clean
                switch between rathena and rathena-th (2026-10-05).
  replay:<FROM>..<TO>[@<seconds>]
                OFFLINE re-decode of the banked captures (ADR-0007; Batt 2026-10-08) with the
                CURRENT decoders: the sniffer's capture-*.pcapng opened in [FROM, TO] (UTC hours,
                YYYYmmddTHH) plus the one open at FROM, through `python -m poring_packets.replay`
                in a ONE-OFF container from poring-lab/sniffer:local -- never the live sniffer
                (its 256 MB would be shared): no network, captures read-only, every capability
                dropped, uid 1000, mem == memswap 1g, oom_score_adj 500, 2 CPUs, reads capped at
                REPLAY_READ_BPS on the root LV. Output: $REPLAY_OUT/<FROM>..<TO>/events.jsonl.
                Packets stay offline ground truth: nothing here reaches the agent.
  replaydev:<FROM>..<TO>[@<seconds>]
                the same container, with THIS checkout's packages/poring_packets/src mounted
                READ-ONLY first on PYTHONPATH (2026-10-08, loot@1 P2): decoders added since the
                sniffer image was built are replayed WITHOUT rebuilding it (the live sniffer is
                untouched; the image only lends its Python). Needs the generated length table
                in that source (scripts/gen_packet_tables.py; its sha256 is checked against the
                lock as always). Output: $REPLAY_OUT/<FROM>..<TO>-dev/events.jsonl.
  tables[@<seconds>][=--update-lock]
                scripts/gen_packet_tables.py under the IO guard (2026-10-08: the generator starts
                its own throwaway toolchain containers, and a container start can storm the
                shared disk). Niced; its only options are --update-lock / --accept-drift.
                Afterwards the sniffer needs `build:sniffer` + `recreate:sniffer` for the new
                table to be live.
  run:<svc>[@<seconds>]=<command>
                docker compose --profile <svc> run --rm --no-deps <svc> <command>, killed after
                <seconds> (default 600), its output's tail printed. ONLY `vision` (check_gpu.py):
                a second gamestream would be a second lab client, a second desktop a second
                xfreerdp (ADR-0001/0009). The hook and scripts/dev.sh refuse a raw `compose run`.
  rundev:<svc>[@<seconds>]=<command>
                the same with `-f compose.yaml -f compose.vision-dev.yaml`: the host's vision
                source read-only, first on PYTHONPATH (training runs iterate without rebuilding the
                ~5 GB torch image; the overlay adds nothing else, test_guards). ONLY `vision`.
                Both are GPU jobs, so the GPU sharing rules apply (scripts/frigate_r3.py; infra
                side, Batt 2026-10-07; the 20:00-05:00 window is retired, these decide):
                  before: REFUSED (rc 3) while Ollama has a model loaded or another job of ours
                  is on the GPU (R2), without a Frigate baseline <= 3 h old, or with Frigate's
                  stats unreachable (R3, fail closed);
                  during: beside the IO guard, `ABORT <label>: R3 <kind>` + SIGINT on a +5 ms
                  detector slowdown (60 s median), Frigate unreachable for 60 s, Ollama loading a
                  model, or (training only, right after an epoch ends) a baseline due for
                  re-measurement; `ABORT <label>: R3-HARD drops ... (no resume)` when a camera
                  drops frames for 30 s. --frigate-baseline PATH overrides the baseline file.
  OPTION A, the long-lived vision worker (docs/operations/vision-long-lived.md; Batt 2026-10-09:
  BUILT and unit-tested, NOT proven live, NOT switched -- train-day.sh uses it only with WORKER=1):
  worker:vision[@<seconds>]
                start THE worker once: `docker compose -f compose.yaml -f
                compose.vision-worker.yaml --profile vision-worker up -d --no-deps --no-build
                vision-worker`, then watch the IO guard for <seconds> (default 120; a breach stops
                it) and check it is IDLE (docker-init + `sleep infinity`) with nothing of ours on
                the GPU. The same image, mounts, limits and network as a rundev: run
                (tests/test_guards.py), plus ONE mount: /dev/shm/poring-lab-detect at /detect,
                the detect server's socket (ADR-0005 Amendment 2026-11-07), created first as
                ours, mode 0700 (else REFUSED). Its entrypoint never imports torch, so it holds
                no CUDA context. It is the day's ONE cold start: run it through
                scripts/runbooks/quiet_start.py (a measured quiet window). Already up and idle:
                nothing is started. Busy, paused or unreadable: REFUSED (rc 3).
  execdev:vision[@<seconds>]=<command>
                <command> INSIDE the worker: `timeout <seconds+60> docker exec
                poring-lab-vision-worker-1 timeout --kill-after=30 <seconds> <command>`. The INNER
                timeout bounds the process: a killed `docker exec` client never stops what it
                started (the Docker API cannot signal an exec). Everything of rundev: holds: the
                same R2/R3 pre-start refusals, the PairedR3 ON/OFF windows (docker pause / unpause
                of the WORKER), the IO guard, the duty file. REFUSED (rc 3) unless the worker is up,
                unpaused, IDLE (one job at a time) and started from THIS checkout (its source, duty,
                data and detect mounts): `REFUSED execdev:vision: WORKER down ...` / `... WORKER not
                ready ...`. A stop is verified in EXEC MODE (verify_stop): the worker idle again,
                nothing of ours on the GPU, no client left on the host; escalation SIGINT -> kill -9
                -> docker kill of the worker (`WORKER KILLED`), else STOP-UNVERIFIED. A normal end
                is checked the same way: a client that ended while the worker is still busy is
                stopped.
  worker-stop:vision
                `docker compose ... stop vision-worker`, then checks it is down with nothing of ours
                on the GPU. REFUSED (rc 3) while a job runs in it (or it is paused).
  cache[@<seconds>]=<args>
                the HOST frame-cache builder, `nice -n 19 .venv/bin/python
                scripts/build_frame_cache.py <args>` (it reads sessions from the NAS and writes tar
                shards to it; nothing on the root disk), killed after <seconds> (default 7200).
                Its arguments: options, ids, relative paths, and absolute paths only below
                /dev/shm/poring-lab-tmp/ (RAM scratch inputs). Nothing else runs through it. A
                breach sends SIGINT: re-run with `--resume` later (Batt, 2026-10-06: daytime caches
                pause on a trip and resume, never retry fast).
  measure:du=<path> | measure:docker-df | measure:buildx-du
                the DISK AUDIT's measurements (Batt, 2026-10-21: "measure ... under the IO guard,
                nice 19 + ionice idle; one directory at a time; stop on any guard trip"). du:
                `nice -n 19 ionice -c3 du -s -x --block-size=1 <path>`, ONE path per step, and only
                under OUR roots (MEASURE_ROOTS: the repo, the shm archive, ~/.cache/poring-lab):
                never a quant or system directory. docker-df: `docker system df -v` (it walks
                the overlay dirs: once pushed quant-postgres to 15-18 % alone). buildx-du: the
                lab builder's (default) cache records. Read-only; a trip kills it and stops the run.
  archive:<src>=<dst>
                the disk audit's MOVE to the NAS (Batt, 2026-10-21: "long-term files live ONLY on
                the NAS ... copy to the NAS paced (chunked, IO guard) ... verify, then delete
                locally"). <src> under MEASURE_ROOTS, <dst> under NAS_ARCHIVE_ROOT and NOT existing.
                Three phases, each under the guard: `rsync -a --bwlimit` (paced) -> a size+count
                check (`rsync -a -n --itemize-changes` must list NOTHING) -> `rm -rf <src>`. A trip
                or a failed check stops before the delete. One item per step.
  voldump:<volume>=<dst.tar.gz> | volrm:<volume>=<dst.tar.gz>
                a STOPPED volume to the NAS, then removed (Batt, 2026-10-22, decision 7: "db-th-data
                dump to the NAS then remove"). Only VOLUME_ALLOWED volumes (db-th-data); voldump:
                also the captures (VOLUME_DUMP: the bot-server cutover, never volrm). voldump:
                refused while any container that mounts it runs, or when <dst> (under
                NAS_ARCHIVE_ROOT, *.tar.gz) exists; a COLD copy of the data directory -- a one-off,
                network-less container of the volume's own image as its owner (cap-drop ALL),
                `tar czf -` to the host's <dst> -- then the file count of the volume must equal
                the archive's. volrm: only when <dst> is there and readable (`tar tzf`): `compose
                rm -s -f` of its service, then `docker volume rm`. Restore: untar into a volume.

    python3 scripts/guarded_build.py build:desktop build:rathena pull:db up:180        # strict 10%
    python3 scripts/guarded_build.py --sustain 30 --spike 25 build:rathena             # tolerant
    python3 scripts/guarded_build.py --sustain 30 --spike 25 start:db@120 start:rathena@240
    python3 scripts/guarded_build.py build:vision   # ~5 GB of writes: run in an operator window
    python3 scripts/guarded_build.py 'run:vision@600=python scripts/check_gpu.py'  # GPU check
    python3 scripts/guarded_build.py --sustain 30 --spike 25 \
        'rundev:vision@3600=python -m poring_vision.train --cache /datasets/.framecache/ID --smoke'
    python3 scripts/guarded_build.py --sustain 30 --spike 25 \
        'cache@7200=--train S1 S2 --val S3 --test S4 --cache-id ID --labels v0 --resume'
    python3 scripts/runbooks/quiet_start.py -- \
        python3 scripts/guarded_build.py --sustain 30 --spike 25 worker:vision@120
    python3 scripts/guarded_build.py --sustain 30 --spike 25 \
        'execdev:vision@3600=python -m poring_vision.train --cache /datasets/.framecache/ID --smoke'
    python3 scripts/guarded_build.py worker-stop:vision

--test-abort-after-cycles N is TEST ONLY (the worker proof: scripts/runbooks/worker_proof.py,
step 4): once a GPU step's R3 schedule has closed N ON/OFF cycles (N measured pairs, as in any
run), the step is aborted exactly as on an IO trip (an ABORT line, unpause, SIGINT, the verified
stop). Never in a production run: train-day.sh and eval.sh never pass it.

Logs go to $TMPDIR/poring-guarded-*.log. Exit 0 only if every step completed without a breach.
"""

import argparse
import collections
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "services" / "backend" / "src"))
sys.path.insert(0, str(REPO / "packages" / "poring_env" / "src"))
from poring_backend.mode_restore import RESTORE_NAME, format_marker  # noqa: E402

sys.path.insert(0, str(REPO / "scripts"))
import frigate_r3  # noqa: E402
import host_profile  # noqa: E402
import io_baseline  # noqa: E402

STATE = Path(os.environ.get("LAB_STATE_HOST_DIR", REPO / "state"))
BACKEND = "poring-lab-backend-1"
LOGDIR = Path(os.environ.get("TMPDIR", "/dev/shm/poring-lab-tmp"))  # rule 7: never host /tmp
LOGDIR.mkdir(parents=True, exist_ok=True)
CONTAINERS = [
    "quant-orderbook-engine",
    "quant-ticker-engine",
    "quant-crypto-engine",
    "quant-marketdata-engine",
    "quant-postgres",
    "quant-mongo",
    # The NVR's 24/7 recording IO: R3 covers its detector, not its disk (Batt 2026-10-09: it stays).
    "frigate",
]
EXTRA_CGROUPS = {"cron.service(capture-streaming-pro)": "/sys/fs/cgroup/system.slice/cron.service"}
ALL = [
    "--profile", "core", "--profile", "remote", "--profile", "vision", "--profile", "gamestream",
    "--profile", "sniffer", "--profile", "th",
]  # fmt: skip
RUNTIME = ["--profile", "core", "--profile", "remote"]
# Dev mode (compose.yaml + compose.dev.yaml, see scripts/dev.sh) plus the core and sniffer profiles,
# so `start:sniffer` is guarded too (an unguarded sniffer recreate right after a guarded db/rathena
# start coincided with 67 % quant-postgres io_full for ~20 s, 2026-10-01). `up -d <services>` still
# starts only the named services.
# gamestream (the Sunshine/Moonlight console-mode client, ADR-0009) is guarded the same way, and
# so is `th` (2026-10-05): db-th, rathena-th, sniffer-th. rathena-th runs ONE AT A TIME with
# rathena (same pinned IP and ports: Docker refuses the second); switch with
#   scripts/dev.sh --profile sniffer stop sniffer rathena      (stop needs no guard)
#   python3 scripts/guarded_build.py --sustain 30 --spike 25 start:rathena-th,sniffer-th@240
# and back. The auto GM recover stays `sniffer`-only: the -th client logs in by itself or by hand.
DEV = [
    "scripts/dev.sh", "--profile", "core", "--profile", "sniffer", "--profile", "gamestream",
    "--profile", "th",
]  # fmt: skip
# Lab image builds use dockerd's own BuildKit ("default"): it writes only the new layers. The global
# builder on this host is Batt's arm64 `armbuilder` (docker-container driver), which re-loads every
# finished image into dockerd as a full tarball -- a ~5 s, 66-100 % quant io_full burst on
# 2026-10-01 -- and cannot resolve a local `FROM poring-lab/...:local` base. Only the build
# subprocesses get this; the global builder (`docker buildx use`) is never touched.
LAB_BUILDER = os.environ.get("LAB_BUILDX_BUILDER", "default")
SERVICE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
RUN_ALLOWED = frozenset({"vision"})  # see run: in the docstring
# measure:du= (the disk audit, Batt 2026-10-21): poring-lab's own paths only, never quant / system
MEASURE_ROOTS = (
    Path(__file__).resolve().parents[1],
    Path("/home/batt/poring-lab-shm-archive"),
    Path("/home/batt/.cache/poring-lab"),
)
NAS_ARCHIVE_ROOT = Path("/mnt/poring-lab-datasets")  # archive: destinations (tank-main/poring-lab)
ARCHIVE_BWLIMIT_KIB = 20000  # ~20 MB/s off the shared disk
MEASURE_FIXED = {
    "docker-df": ["docker", "system", "df", "-v"],
    "buildx-du": ["docker", "buildx", "du", "--builder", "default", "--verbose"],  # LAB_BUILDER
}
# voldump: / volrm: (Batt 2026-10-22, decision 7): volume -> (the service that mounts it, its image,
# the files' owner); the image is local (pull_policy never); the owner reads without DAC_OVERRIDE
VOLUME_ALLOWED = {"db-th-data": ("db-th", "mariadb:11.8.9", "999:999")}
# voldump: ONLY (never volrm:): the sniffer's packet captures, to the NAS archive at the bot-server
# cutover (Batt 2026-11-07, the whole move; long-term = the NAS only, 2026-10-21). Root-owned 0644
# files: read as nobody, cap-drop ALL, network none, read-only.
VOLUME_DUMP = {
    **VOLUME_ALLOWED,
    "captures": ("sniffer", "poring-lab/sniffer:local", "65534:65534"),
    "captures-th": ("sniffer-th", "poring-lab/sniffer:local", "65534:65534"),
}
COMPOSE_PROJECT = "poring-lab"
REPLAY_RANGE = re.compile(r"^(\d{8}T\d{2})\.\.(\d{8}T\d{2})$")
CAPTURE_NAME = re.compile(r"^capture-(\d{8}T\d{6})Z\.pcapng$")
REPLAY_IMAGE = "poring-lab/sniffer:local"
REPLAY_OUT = Path("/dev/shm/poring-lab-tmp/replay")  # RAM: rule 7
REPLAY_DEVICE = "/dev/dm-0"  # the root LV (Docker's volumes); the disk shared with live capture
REPLAY_READ_BPS = "20mb"
REPLAY_AIDS = ("2000002", "2000001")  # the GM and the normal account: tagged, never logged
REPLAY_DEV_SRC = REPO / "packages" / "poring_packets" / "src"  # replaydev: mounted read-only


class Step:
    """One parsed command-line step (see the module docstring)."""

    def __init__(
        self,
        kind: str,
        services: list[str],
        seconds: float | None = None,
        command: list[str] | None = None,
    ) -> None:
        self.kind, self.services, self.seconds = kind, services, seconds
        self.command = command or []

    @property
    def label(self) -> str:
        return f"{self.kind}:{','.join(self.services)}" if self.services else self.kind


def parse_step(step: str) -> Step:
    kind, _, arg = step.partition(":")
    if kind in ("build", "pull"):
        if not SERVICE.match(arg):
            raise ValueError(f"{step}: expected {kind}:<service>")
        return Step(kind, [arg])
    if kind == "target":
        parts = arg.split(":", 2)
        if len(parts) != 3 or not SERVICE.match(parts[0]) or not SERVICE.match(parts[1]):
            raise ValueError(f"{step}: expected target:<svc>:<stage>:<image>")
        if not re.match(r"^[a-z0-9][a-z0-9._/-]*:[A-Za-z0-9._-]+$", parts[2]):
            raise ValueError(f"{step}: bad image tag")
        return Step(kind, parts)
    if kind == "up":
        return Step(kind, [], float(arg or 180))
    if kind in ("start", "recreate", "restart"):
        names, _, secs = arg.partition("@")
        services = names.split(",")
        if not all(SERVICE.match(s) for s in services):
            raise ValueError(f"{step}: expected {kind}:<svc>[,<svc>...][@<seconds>]")
        return Step(kind, services, float(secs or 180))
    if kind == "rm":
        services = arg.split(",")
        if not all(SERVICE.match(s) for s in services):
            raise ValueError(f"{step}: expected rm:<svc>[,<svc>...]")
        return Step(kind, services)
    if kind in ("run", "rundev", "execdev"):
        head, eq, command = arg.partition("=")
        name, _, secs = head.partition("@")
        argv = shlex.split(command)
        if not eq or not argv or not SERVICE.match(name):
            raise ValueError(f"{step}: expected {kind}:<svc>[@<seconds>]=<command>")
        if name not in RUN_ALLOWED:
            raise ValueError(f"{step}: run: is allowed only for {', '.join(sorted(RUN_ALLOWED))}")
        return Step(kind, [name], float(secs or 600), argv)
    if kind in ("worker", "worker-stop"):
        name, _, secs = arg.partition("@")
        if name not in RUN_ALLOWED or (kind == "worker-stop" and secs):
            raise ValueError(f"{step}: expected worker:vision[@<seconds>] or worker-stop:vision")
        return Step(kind, [name], float(secs or 120) if kind == "worker" else None)
    if kind in ("replay", "replaydev"):
        rng, _, secs = arg.partition("@")
        m = REPLAY_RANGE.match(rng)
        if m is None or m.group(1) > m.group(2):
            raise ValueError(f"{step}: expected {kind}:<YYYYmmddTHH>..<YYYYmmddTHH>[@<seconds>]")
        return Step(kind, [m.group(1), m.group(2)], float(secs or 3600))
    if step.split("=", 1)[0].split("@", 1)[0] == "tables":
        head, eq, command = step.partition("=")
        _, _, secs = head.partition("@")
        argv = shlex.split(command)
        if (
            head not in ("tables", f"tables@{secs}")
            or (eq and not argv)
            or any(a not in TABLES_ARGS for a in argv)
        ):
            raise ValueError(f"{step}: expected tables[@<seconds>][=--update-lock|--accept-drift]")
        return Step("tables", [], float(secs or 1800), argv)
    if kind == "measure":
        what, eq, path = arg.partition("=")
        if what in MEASURE_FIXED and not eq:
            return Step("measure", [what])
        if what != "du" or not eq:
            raise ValueError(f"{step}: expected measure:du=<path>|docker-df|buildx-du")
        target = Path(path)
        if not target.is_absolute() or ".." in target.parts:
            raise ValueError(f"{step}: an absolute path without '..'")
        if not any(target == r or r in target.parents for r in MEASURE_ROOTS):
            raise ValueError(f"{step}: only under {', '.join(str(r) for r in MEASURE_ROOTS)}")
        return Step("measure", ["du"], None, [str(target)])
    if kind in ("voldump", "volrm"):
        name, eq, dst_s = arg.partition("=")
        dst = Path(dst_s)
        allowed = VOLUME_DUMP if kind == "voldump" else VOLUME_ALLOWED
        if name not in allowed:
            raise ValueError(f"{step}: only {', '.join(sorted(allowed))}")
        if not eq or not dst.is_absolute() or ".." in dst.parts or not dst.name.endswith(".tar.gz"):
            raise ValueError(f"{step}: expected {kind}:<volume>=<abs dst>.tar.gz")
        if NAS_ARCHIVE_ROOT not in dst.parents:
            raise ValueError(f"{step}: dst only below {NAS_ARCHIVE_ROOT}")
        return Step(kind, [name], None, [str(dst)])
    if kind == "archive":
        src_s, eq, dst_s = arg.partition("=")
        src, dst = Path(src_s), Path(dst_s)
        if not eq or not src.is_absolute() or not dst.is_absolute():
            raise ValueError(f"{step}: expected archive:<abs src>=<abs dst>")
        if ".." in src.parts or ".." in dst.parts:
            raise ValueError(f"{step}: no '..'")
        if not any(r in src.parents for r in MEASURE_ROOTS):
            raise ValueError(f"{step}: src only BELOW {', '.join(str(r) for r in MEASURE_ROOTS)}")
        if NAS_ARCHIVE_ROOT not in dst.parents:
            raise ValueError(f"{step}: dst only below {NAS_ARCHIVE_ROOT}")
        return Step("archive", ["archive"], None, [str(src), str(dst)])
    if kind == "cache" or step.startswith("cache@") or step.startswith("cache="):
        head, eq, command = step.partition("=")
        _, _, secs = head.partition("@")
        argv = shlex.split(command)
        if head not in ("cache", f"cache@{secs}") or not eq or not argv:
            raise ValueError(f"{step}: expected cache[@<seconds>]=<build_frame_cache args>")
        if any(not cache_arg_ok(a) for a in argv):
            raise ValueError(f"{step}: cache: takes build_frame_cache options and session ids")
        return Step("cache", [], float(secs or 7200), argv)
    raise ValueError(f"unknown step {step}")


# ADR-0022: this host's profile (LAB_HOST_PROFILE; unset = shared-nvidia, VM 103). Its compose
# overlay comes LAST on every command that creates or builds vision; shared-nvidia has none, so
# VM 103's commands are exactly what they were.
PROFILE = host_profile.current()
VISION_DEV = host_profile.files("compose.yaml", "compose.vision-dev.yaml",
                                overlay=PROFILE.vision_overlay)  # rundev: the overlay  # fmt: skip
# run: and build:/pull:/target: take compose's default file set unless the profile adds an overlay
VISION_FILES = (host_profile.files("compose.yaml", overlay=PROFILE.vision_overlay)
                if PROFILE.vision_overlay else [])  # fmt: skip


def container_name(step: Step) -> str:
    """The run:/rundev: step's container, NAMED so an abort can stop the container itself."""
    return f"poring-lab-{step.services[0]}-{step.kind}-{os.getpid()}"


def run_cmd(step: Step) -> list[str]:
    svc = step.services[0]
    seconds = str(int(step.seconds or 600))
    files = VISION_DEV if step.kind == "rundev" else VISION_FILES
    return [
        "timeout", seconds, "docker", "compose", *files, "--profile", svc, "run", "--rm",
        "--name", container_name(step), "--no-deps", svc, *step.command,
    ]  # fmt: skip


# --- OPTION A: the long-lived vision worker (docs/operations/vision-long-lived.md) ---------------
WORKER_SERVICE = "vision-worker"
WORKER = "poring-lab-vision-worker-1"  # compose's name for the ONE worker container
VISION_WORKER = [*host_profile.files("compose.yaml", "compose.vision-worker.yaml",
                                     overlay=PROFILE.worker_overlay),
                 "--profile", WORKER_SERVICE]  # fmt: skip
EXEC_GRACE_S = 60  # the docker exec client outlives the inner timeout by this much
EXEC_KILL_AFTER_S = 30  # the inner timeout's SIGKILL, this long after its SIGTERM
EXEC_SETTLE_S = 10  # after the client ends: orphaned children get this long to exit by themselves
# The step's host-side processes: the outer `timeout` and the `docker exec` client (cmdline bytes).
EXEC_HOST = b"docker\x00exec\x00" + WORKER.encode() + b"\x00"
# The worker must run THIS checkout's source, duty file, data dir and the detect directory
# (container path -> host path):
# the duty file guarded_build writes and the results it reads are this checkout's.
# ADR-0005 Amendment 2026-11-07: the detect server's socket directory (RAM), the host's only
# GPU-detector route (scripts/unit_detector.GpuDetector); created here, ours, mode 0700.
DETECT_DIR = Path("/dev/shm/poring-lab-detect")
WORKER_MOUNTS = {
    "/opt/vision-src": REPO / "services" / "vision" / "src",
    "/lab-duty": REPO / "state" / "train-duty",
    "/data": REPO / "data",
    "/detect": DETECT_DIR,
}
WORKER_STATES = {"running": "running", "paused": "paused", "created": "stopped",
                 "exited": "stopped", "dead": "stopped"}  # fmt: skip


def exec_cmd(step: Step) -> list[str]:
    """execdev: the command INSIDE the long-lived worker. Two bounds: the inner `timeout` stops the
    process (killing a `docker exec` client never stops what it started: the API cannot signal an
    exec), the outer one the client, EXEC_GRACE_S later."""
    seconds = int(step.seconds or 600)
    return [
        "timeout", str(seconds + EXEC_GRACE_S), "docker", "exec", WORKER,
        "timeout", f"--kill-after={EXEC_KILL_AFTER_S}", str(seconds), *step.command,
    ]  # fmt: skip


def ensure_detect_dir(path: Path = DETECT_DIR) -> str | None:
    """The worker's /detect source must exist BEFORE the start (docker would create a missing bind
    source root-owned): a directory of ours, mode 0700, not a symlink. None when it is, else why
    not (the start is refused)."""
    try:
        path.mkdir(mode=0o700, exist_ok=True)
        st = path.lstat()
    except OSError as exc:
        return f"{path}: {exc}"
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid():
        return f"{path}: not a directory of ours (mode {oct(st.st_mode)}, uid {st.st_uid})"
    path.chmod(0o700)
    return None


def worker_start_cmd() -> list[str]:
    return ["docker", "compose", *VISION_WORKER, "up", "-d", "--no-deps", "--no-build",
            WORKER_SERVICE]  # fmt: skip


def worker_stop_cmd() -> list[str]:
    return ["docker", "compose", *VISION_WORKER, "stop", WORKER_SERVICE]


def docker_state(name: str) -> tuple[str, str]:
    """(state, container id): running | paused | stopped | absent | unknown (docker not answering,
    or restarting / being removed)."""
    try:
        r = subprocess.run(["docker", "inspect", "-f", "{{.Id}} {{.State.Status}}", name],
                           capture_output=True, text=True, timeout=15, check=False)  # fmt: skip
    except (OSError, subprocess.SubprocessError):
        return "unknown", ""
    if r.returncode != 0:
        return ("absent", "") if "no such" in (r.stderr or "").lower() else ("unknown", "")
    parts = (r.stdout or "").split()
    if len(parts) != 2:
        return "unknown", ""
    return WORKER_STATES.get(parts[1], "unknown"), parts[0]


def _argv(raw: bytes) -> list[bytes]:
    return raw[:-1].split(b"\x00") if raw.endswith(b"\x00") else (raw.split(b"\x00") if raw else [])


def worker_procs(name: str) -> dict[int, tuple[int, list[bytes]]] | None:
    """The HOST's view of the worker's processes: {host pid: (ppid, argv)} from its cgroup; {} when
    it is not running; None when that cannot be read (fail closed: unverifiable)."""
    state, cid = docker_state(name)
    if state in ("stopped", "absent"):
        return {}
    if state == "unknown":
        return None
    try:
        procs = Path(f"/sys/fs/cgroup/system.slice/docker-{cid}.scope/cgroup.procs").read_text()
        pids = [int(p) for p in procs.split()]
    except (OSError, ValueError):
        return None
    out: dict[int, tuple[int, list[bytes]]] = {}
    for pid in pids:
        try:
            status = Path(f"/proc/{pid}/status").read_text()
            ppid = int(status.split("\nPPid:", 1)[1].split()[0])
            out[pid] = (ppid, _argv(Path(f"/proc/{pid}/cmdline").read_bytes()))
        except (OSError, IndexError, ValueError):
            continue  # exited meanwhile
    return out


def idle_argv(argv: list[bytes]) -> bool:
    """The worker's idle entrypoint: `sleep infinity` and its init (`docker-init -- sleep
    infinity`). Anything else in it is a job."""
    if argv == [b"sleep", b"infinity"]:
        return True
    return (len(argv) == 4 and argv[0].rsplit(b"/", 1)[-1] in (b"docker-init", b"tini")
            and argv[1:] == [b"--", b"sleep", b"infinity"])  # fmt: skip


def busy(procs: dict[int, tuple[int, list[bytes]]]) -> dict[int, tuple[int, list[bytes]]]:
    return {p: v for p, v in procs.items() if not idle_argv(v[1])}


def exec_roots(procs: dict[int, tuple[int, list[bytes]]]) -> list[int]:
    """The tops of what runs in the worker beyond its entrypoint (an exec'd process's parent is the
    containerd shim, outside the container): the processes a SIGINT goes to first."""
    b = busy(procs)
    return sorted(p for p, (ppid, _) in b.items() if ppid not in b)


def describe(procs: dict[int, tuple[int, list[bytes]]]) -> str:
    words = [f"{p} ({b' '.join(v[1]).decode(errors='replace')[:70] or 'zombie'})"
             for p, v in sorted(procs.items())]  # fmt: skip
    return ", ".join(words)


def worker_mounts(name: str) -> dict[str, str] | None:
    """The worker's bind mounts {container path: host path}, or None when docker does not answer."""
    try:
        cmd = ["docker", "inspect", "-f", "{{json .Mounts}}", name]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=True).stdout
        return {str(m["Destination"]): str(m.get("Source", "")) for m in json.loads(out)}
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError):
        return None


def worker_not_ready(name: str = WORKER) -> str | None:
    """Why an execdev: must NOT start in the worker now, or None: up, unpaused, idle (one job at a
    time), and started from THIS checkout."""
    state, _ = docker_state(name)
    if state in ("stopped", "absent"):
        return (f"down ({name} {state}): start it with worker:vision@<s>, through quiet_start "
                "(a measured quiet window)")  # fmt: skip
    if state != "running":
        return f"not ready ({name} {state}): a person must look"
    procs = worker_procs(name)
    if procs is None:
        return f"not ready ({name}: its processes are unreadable)"
    if busy(procs):
        return f"not ready ({name} is busy: {describe(busy(procs))}): one job at a time"
    mounts = worker_mounts(name) or {}
    wrong = {dst: mounts.get(dst) for dst, src in WORKER_MOUNTS.items()
             if dst not in mounts or Path(mounts[dst]).resolve() != src.resolve()}  # fmt: skip
    if wrong:
        return (f"not ready ({name} was not started from this checkout: {wrong}); its source, "
                "duty file and data must be this checkout's")  # fmt: skip
    return None


def select_captures(names: list[str], first: str, last: str) -> list[str]:
    """The capture files that can hold packets of the UTC hours [first, last]: every file opened in
    that range, plus the last one opened before it (rotation is hourly or by size, so it may still
    run into `first`). In time order, as the replay needs them."""
    stamped = sorted((m.group(1)[:11], n) for n in names if (m := CAPTURE_NAME.match(n)))
    before = [n for h, n in stamped if h < first]
    inside = [n for h, n in stamped if first <= h <= last]
    return ([before[-1]] if before else []) + inside


def replay_out(step: Step) -> Path:
    """Where a replay writes its events.jsonl (RAM); replaydev: apart, with a -dev suffix."""
    suffix = "-dev" if step.kind == "replaydev" else ""
    return REPLAY_OUT / f"{step.services[0]}..{step.services[1]}{suffix}"


def replay_cmd(step: Step, volume: str, files: list[str], name: str) -> list[str]:
    """The one-off replay container (see replay: / replaydev: in the docstring). File names are
    validated."""
    assert files and all(CAPTURE_NAME.match(f) for f in files)
    out = replay_out(step)
    dev = (
        ["-v", f"{REPLAY_DEV_SRC}:/repo-src:ro", "-e", "PYTHONPATH=/repo-src",
         "-e", "PYTHONDONTWRITEBYTECODE=1"]
        if step.kind == "replaydev" else []
    )  # fmt: skip
    paths = " ".join(shlex.quote(f"/captures/{f}") for f in files)
    aids = " ".join(f"--validation-aid {a}" for a in REPLAY_AIDS)
    script = (f"ls -l {paths} >&2 && python -m poring_packets.replay {paths} {aids} "
              f"> /out/events.jsonl")  # fmt: skip
    return [
        "timeout", str(int(step.seconds or 3600)), "docker", "run", "--rm", "--name", name,
        "--network", "none", "--read-only", "--tmpfs", "/tmp:size=16m",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", "1000:1000",
        "--memory", "1g", "--memory-swap", "1g", "--oom-score-adj", "500", "--cpus", "2",
        "--device-read-bps", f"{REPLAY_DEVICE}:{REPLAY_READ_BPS}",
        "-v", f"{volume}:/captures:ro", "-v", f"{out}:/out", *dev,
        "--entrypoint", "sh", REPLAY_IMAGE, "-c", script,
    ]  # fmt: skip


def captures_volume() -> str:
    """The Docker volume mounted at the live sniffer's /captures."""
    import lab_servers

    fmt = '{{range .Mounts}}{{if eq .Destination "/captures"}}{{.Name}}{{end}}{{end}}'
    out = subprocess.run(["docker", "inspect", lab_servers.sniffer(), "--format", fmt],
                         capture_output=True, text=True, check=True).stdout.strip()  # fmt: skip
    if not out:
        raise RuntimeError("the sniffer has no /captures volume")
    return out


def list_captures(volume: str) -> list[str]:
    out = subprocess.run(
        ["docker", "run", "--rm", "--network", "none", "--cap-drop", "ALL", "--user", "1000:1000",
         "-v", f"{volume}:/captures:ro", "--entrypoint", "ls", REPLAY_IMAGE, "/captures"],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    return out.split()


def container_running(name: str) -> bool:
    out = subprocess.run(["docker", "ps", "-q", "--filter", f"name=^/{name}$"],
                         capture_output=True, text=True, check=False).stdout  # fmt: skip
    return bool(out.strip())


STOP_VERIFY_S = 30.0  # a guard stop must be CONFIRMED within this many seconds of the SIGINT ...
ESCALATED_VERIFY_S = 15.0  # ... else escalate (docker kill / kill -9) and confirm within this


def own_pids(pattern: bytes, pids: list[int] | None = None) -> list[int]:
    """Our (same uid) processes whose command line contains ``pattern``; ``pids`` limits the search
    (e.g. to the GPU's compute processes). Never this process itself."""
    me, uid = os.getpid(), os.getuid()
    out = []
    for pid in pids if pids is not None else [int(p) for p in os.listdir("/proc") if p.isdigit()]:
        try:
            if pid == me or os.stat(f"/proc/{pid}").st_uid != uid:
                continue
            if pattern in Path(f"/proc/{pid}/cmdline").read_bytes():
                out.append(pid)
        except OSError:
            continue
    return out


def gpu_pids() -> list[int] | None:
    """Every compute process on the GPU (nvidia-smi; on an Intel / AMD host the DRM file holders,
    host_profile.drm_pids), or None when that cannot be answered."""
    if PROFILE.gpu_lister == "drm-fdinfo":
        return host_profile.drm_pids()
    try:
        query = ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"]
        out = subprocess.run(query, capture_output=True, text=True, timeout=15, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return [int(x) for x in out.split() if x.strip().isdigit()]


def leftovers(container: str | None, gpu: bool, host: bytes | None) -> list[str]:
    """What of an aborted step is still alive: its container, OUR processes on the GPU (command
    line naming poring_vision), its host-side processes. Empty = the stop is verified."""
    left = []
    if container is not None and container_running(container):
        left.append(f"container {container}")
    if gpu:
        pids = gpu_pids()
        if pids is None:
            left.append("GPU unverifiable (nvidia-smi failed)")
        else:
            ours = own_pids(b"poring_vision", pids)
            if ours:
                left.append(f"our GPU processes {ours}")
    if host is not None:
        procs = own_pids(host)
        if procs:
            left.append(f"host processes {procs} ({host.decode()})")
    return left


def pid_cgroup(pid: int) -> str:
    """/proc/<pid>/cgroup ("" when gone): an EXITING task (a CUDA context being torn down) has
    already left cgroup.procs but still names its cgroup here."""
    try:
        return Path(f"/proc/{pid}/cgroup").read_text()
    except OSError:
        return ""


def gpu_ours_exec(worker: str, pids: list[int], procs: dict[int, Any]) -> list[int]:
    """GPU compute processes of ours in exec mode: in the worker (its processes, or its cgroup for
    one that is exiting), or ours by command line anywhere (poring_vision)."""
    cid = docker_state(worker)[1]
    inside = {p for p in pids if p in procs or (cid and f"docker-{cid}.scope" in pid_cgroup(p))}
    return sorted(set(own_pids(b"poring_vision", pids)) | inside)


def exec_leftovers(worker: str, host: bytes | None) -> list[str]:
    """EXEC MODE (execdev:): what of the step is still alive. The worker itself stays up: stopped
    means it runs only its idle entrypoint again (the exec'd process and every child gone), no GPU
    process of ours (in the worker, or ours by command line), no client left on the host. Empty =
    verified. Unreadable = never verified (fail closed)."""
    left = []
    procs = worker_procs(worker)
    if procs is None:
        left.append(f"worker {worker} unverifiable (its state / cgroup unreadable)")
        procs = {}
    jobs = busy(procs)
    if jobs:
        left.append(f"worker busy: {describe(jobs)}")
    pids = gpu_pids()
    if pids is None:
        left.append("GPU unverifiable (nvidia-smi failed)")
    else:
        ours = gpu_ours_exec(worker, pids, procs)
        if ours:
            left.append(f"our GPU processes {ours}")
    if host is not None:
        hosts = own_pids(host)
        if hosts:
            left.append(f"host processes {hosts} (the docker exec client)")
    return left


def _signal(pid: int, sig: int, where: str) -> None:
    name = {2: "SIGINT", 9: "kill -9"}.get(sig, f"signal {sig}")
    try:
        os.kill(pid, sig)
        print(f"[{ts()}] {'ESCALATED: ' if sig == 9 else ''}{name} {pid} ({where})", flush=True)
    except OSError as exc:
        print(f"[{ts()}] {name} {pid} ({where}) failed ({exc})", flush=True)


def worker_word(worker: str) -> str:
    state = docker_state(worker)[0]
    if state == "running":
        return f"worker {worker} up and idle (no CUDA context)"
    return f"worker {worker} {state}"


def verify_exec_stop(
    label: str, worker: str, host: bytes | None, *, t0: float, sleep: Any, clock: Any
) -> bool:
    """verify_stop in EXEC MODE (option A). The SIGINT the guard sent reached only the host-side
    `docker exec` client, never the process it started, so: (1) SIGINT to the exec'd process (the
    tops of what runs in the worker beyond its entrypoint), confirmed within STOP_VERIFY_S; (2)
    ESCALATE: kill -9 of every job process in the worker, our GPU processes and the host client,
    confirmed within ESCALATED_VERIFY_S; (3) if the GPU still lists ours or the worker is still
    busy: `docker kill` of the worker itself (logged `WORKER KILLED`: the next execdev needs a new
    worker: start), confirmed within ESCALATED_VERIFY_S. Else STOP-UNVERIFIED, a person must look.
    Signals go from the host by host pid (same uid, no daemon round trip, and no new process in the
    worker that would read as a job)."""
    if docker_state(worker)[0] == "paused":  # an R3 OFF window: a frozen process cannot exit
        subprocess.run(["docker", "unpause", worker], capture_output=True, check=False)
        print(f"[{ts()}] {label}: {worker} was paused: unpaused", flush=True)
    nudged = False
    left = exec_leftovers(worker, host)
    while left and clock() - t0 < STOP_VERIFY_S:
        if not nudged:
            nudged = True
            for pid in exec_roots(worker_procs(worker) or {}):
                _signal(pid, 2, f"the exec'd process in {worker}")
        sleep(2)
        left = exec_leftovers(worker, host)
    if not left:
        print(f"[{ts()}] STOP VERIFIED {label} after {clock() - t0:.0f}s: the exec'd process gone, "
              f"no process of ours on the GPU or left on the host; {worker_word(worker)} "
              f"[{frigate_r3.stamp()}]", flush=True)  # fmt: skip
        return True
    print(f"[{ts()}] STOP NOT VERIFIED {label} after {STOP_VERIFY_S:.0f}s ({'; '.join(left)}): "
          f"ESCALATING [{frigate_r3.stamp()}]", flush=True)  # fmt: skip
    procs = worker_procs(worker) or {}
    gpu = gpu_ours_exec(worker, gpu_pids() or [], procs)
    for pid in sorted(set(busy(procs)) | (set(gpu) & set(procs))):
        _signal(pid, 9, f"in {worker}")
    for pid in sorted(set(gpu) - set(procs)):
        _signal(pid, 9, "ours on the GPU")
    for pid in own_pids(host) if host is not None else []:
        _signal(pid, 9, "the host's docker exec client")

    def settle() -> list[str]:
        t1 = clock()
        now = exec_leftovers(worker, host)
        while now and clock() - t1 < ESCALATED_VERIFY_S:
            sleep(2)
            now = exec_leftovers(worker, host)
        return now

    left = settle()
    if any(x.startswith(("our GPU processes", "worker busy")) for x in left):
        subprocess.run(["docker", "kill", worker], capture_output=True, check=False)
        print(f"[{ts()}] ESCALATED: docker kill {worker} ({'; '.join(left)} after kill -9) -- "
              f"WORKER KILLED: start it again (worker:vision@<s>, through quiet_start) before the "
              f"next execdev [{frigate_r3.stamp()}]", flush=True)  # fmt: skip
        left = settle()
    if not left:
        print(f"[{ts()}] STOP VERIFIED {label} after escalation ({clock() - t0:.0f}s); "
              f"{worker_word(worker)} [{frigate_r3.stamp()}]", flush=True)  # fmt: skip
        return True
    print(f"[{ts()}] STOP-UNVERIFIED {label}: {'; '.join(left)} STILL PRESENT after escalation -- "
          f"stop it by hand [{frigate_r3.stamp()}]", flush=True)  # fmt: skip
    return False


def verify_stop(
    label: str,
    container: str | None,
    gpu: bool,
    host: bytes | None = None,
    *,
    t0: float | None = None,
    sleep: Any = time.sleep,
    clock: Any = time.monotonic,
    exec_mode: bool = False,
) -> bool:
    """Every guard stop is VERIFIED, never assumed (Batt, 2026-10-07): within STOP_VERIFY_S of the
    SIGINT the step's container must be gone, no process of ours on the GPU, no host process of
    the step left. A container still up gets its own SIGINT (the compose client may not forward
    it: 2026-10-07 11:06, the training ran on for 10.5 min). Past the deadline: ESCALATE (`docker
    kill`, `kill -9` of our leftover processes), logged, and confirm again within
    ESCALATED_VERIFY_S. False = still not stopped: STOP-UNVERIFIED, a person must look.
    ``exec_mode`` (execdev:): ``container`` is the long-lived worker, which STAYS up: see
    verify_exec_stop."""
    t0 = clock() if t0 is None else t0
    if exec_mode and container is not None:
        return verify_exec_stop(label, container, host, t0=t0, sleep=sleep, clock=clock)
    nudged = False
    left = leftovers(container, gpu, host)
    while left and clock() - t0 < STOP_VERIFY_S:
        if not nudged and container is not None and any(x.startswith("container") for x in left):
            subprocess.run(["docker", "kill", "--signal", "INT", container],
                           capture_output=True, check=False)  # fmt: skip
            print(f"[{ts()}] {label}: container still up after the SIGINT: SIGINT to {container}",
                  flush=True)  # fmt: skip
            nudged = True
        sleep(2)
        left = leftovers(container, gpu, host)
    if not left:
        print(f"[{ts()}] STOP VERIFIED {label} after {clock() - t0:.0f}s: container gone, no "
              f"process of ours on the GPU or left on the host [{frigate_r3.stamp()}]",
              flush=True)  # fmt: skip
        return True
    print(f"[{ts()}] STOP NOT VERIFIED {label} after {STOP_VERIFY_S:.0f}s ({'; '.join(left)}): "
          f"ESCALATING [{frigate_r3.stamp()}]", flush=True)  # fmt: skip
    if container is not None and container_running(container):
        subprocess.run(["docker", "kill", container], capture_output=True, check=False)
        print(f"[{ts()}] ESCALATED: docker kill {container}", flush=True)
    pids = (own_pids(b"poring_vision", gpu_pids() or []) if gpu else []) + (
        own_pids(host) if host is not None else []
    )
    for pid in pids:
        try:
            os.kill(pid, 9)
            print(f"[{ts()}] ESCALATED: kill -9 {pid}", flush=True)
        except OSError as exc:
            print(f"[{ts()}] ESCALATED: kill -9 {pid} failed ({exc})", flush=True)
    t1 = clock()
    left = leftovers(container, gpu, host)
    while left and clock() - t1 < ESCALATED_VERIFY_S:
        sleep(2)
        left = leftovers(container, gpu, host)
    if not left:
        print(f"[{ts()}] STOP VERIFIED {label} after escalation ({clock() - t0:.0f}s) "
              f"[{frigate_r3.stamp()}]", flush=True)  # fmt: skip
        return True
    print(f"[{ts()}] STOP-UNVERIFIED {label}: {'; '.join(left)} STILL PRESENT after escalation -- "
          f"stop it by hand [{frigate_r3.stamp()}]", flush=True)  # fmt: skip
    return False


CACHE_ARG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")  # session ids, ids, numbers, paths
# Absolute inputs only from the RAM scratch root (rule 7: client- / GPL-derived label files, frozen
# parameters, a map's KB live in /dev/shm, never on the shared disk; payf07-detector.md 12).
CACHE_SHM_ROOT = "/dev/shm/poring-lab-tmp/"


def cache_arg_ok(arg: str) -> bool:
    """A cache: step argument: an option, a session / cache id or relative path, or an absolute
    path below CACHE_SHM_ROOT with no '..' component."""
    if arg.startswith("-") or CACHE_ARG.match(arg):
        return True
    rest = arg[len(CACHE_SHM_ROOT) :]
    return (arg.startswith(CACHE_SHM_ROOT) and CACHE_ARG.match(rest) is not None
            and ".." not in rest.split("/"))  # fmt: skip


CACHE_PY = REPO / ".venv" / "bin" / "python"


def measure_cmd(step: Step) -> list[str]:
    if step.services == ["du"]:
        return ["nice", "-n", "19", "ionice", "-c3", "du", "-s", "-x", "--block-size=1",
                *step.command]  # fmt: skip
    return list(MEASURE_FIXED[step.services[0]])


def archive_cmds(step: Step) -> tuple[list[str], list[str], list[str]]:
    """The archive: step's copy, check and delete commands (a dir is copied by its contents)."""
    src, dst = step.command
    a, b = (f"{src}/", f"{dst}/") if Path(src).is_dir() else (src, dst)
    nice = ["nice", "-n", "19", "ionice", "-c3"]
    copy = [*nice, "rsync", "-a", f"--bwlimit={ARCHIVE_BWLIMIT_KIB}", a, b]
    check = [*nice, "rsync", "-a", "-n", "--itemize-changes", a, b]
    return copy, check, [*nice, "rm", "-rf", "--", src]


def volume_cmds(name: str, dst: str) -> tuple[list[str], list[str], list[str]]:
    """PURE: voldump's dump (stdout -> dst), its volume file count, and its archive file count."""
    _svc, image, owner = VOLUME_DUMP[name]
    vol = f"{COMPOSE_PROJECT}_{name}"
    one_off = ["docker", "run", "--rm", "--network", "none", "--cap-drop", "ALL", "--user", owner,
               "-v", f"{vol}:/v:ro", "--entrypoint"]  # fmt: skip
    nice = ["nice", "-n", "19", "ionice", "-c3"]
    dump = ["sh", "-c", shlex.join([*nice, *one_off, "tar", image, "czf", "-", "-C", "/v", "."])
            + " > " + shlex.quote(dst)]  # fmt: skip
    count_vol = ["sh", "-c", shlex.join([*one_off, "find", image, "/v", "-type", "f"])
                 + " | wc -l"]  # fmt: skip
    count_tar = ["sh", "-c", "tar tzvf " + shlex.quote(dst) + " | grep -c '^-'"]
    return dump, count_vol, count_tar


def _last_int(label: str) -> int | None:
    lines = [
        x.strip() for x in log_path(label).read_text(errors="replace").splitlines() if x.strip()
    ]
    try:
        return int(lines[-1])
    except (IndexError, ValueError):
        return None


def run_volume(step: Step, guard: "Guard") -> bool:
    name, dst = step.services[0], Path(step.command[0])
    svc, _image, _owner = VOLUME_DUMP[name]
    vol = f"{COMPOSE_PROJECT}_{name}"
    running = subprocess.run(["docker", "ps", "-q", "--filter", f"volume={vol}"],
                             capture_output=True, text=True).stdout.strip()  # fmt: skip
    if running:
        print(f"[{ts()}] {step.label}: REFUSED: a running container mounts {vol}", flush=True)
        return False
    dump, count_vol, count_tar = volume_cmds(name, str(dst))
    if step.kind == "voldump":
        if dst.exists():
            print(f"[{ts()}] {step.label}: REFUSED: {dst} exists (never overwrite)", flush=True)
            return False
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not run_process(f"{step.label}-dump", dump, guard):
            return False
        if not run_process(f"{step.label}-count-vol", count_vol, guard):
            return False
        if not run_process(f"{step.label}-count-tar", count_tar, guard):
            return False
        n_vol, n_tar = _last_int(f"{step.label}-count-vol"), _last_int(f"{step.label}-count-tar")
        if not n_vol or n_vol != n_tar:
            print(f"[{ts()}] {step.label}: CHECK FAILED: {n_vol} files in {vol}, {n_tar} in "
                  f"{dst}", flush=True)  # fmt: skip
            return False
        print(f"[{ts()}] {step.label}: verified ({n_vol} files, {dst.stat().st_size} bytes) -> "
              f"{dst}", flush=True)  # fmt: skip
        return True
    if not dst.exists() or not run_process(f"{step.label}-count-tar", count_tar, guard) \
            or not _last_int(f"{step.label}-count-tar"):  # fmt: skip
        print(f"[{ts()}] {step.label}: REFUSED: no readable dump at {dst}", flush=True)
        return False
    if not run_process(f"{step.label}-rm", [*DEV, "rm", "-s", "-f", svc], guard):
        return False
    return run_process(f"{step.label}-volume-rm", ["docker", "volume", "rm", vol], guard)


def run_archive(step: Step, guard: "Guard") -> bool:
    src, dst = (Path(p) for p in step.command)
    if not src.exists() or src.is_symlink():
        print(f"[{ts()}] {step.label}: REFUSED: {src} missing or a symlink", flush=True)
        return False
    if dst.exists():
        print(f"[{ts()}] {step.label}: REFUSED: {dst} exists (never overwrite)", flush=True)
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    copy, check, delete = archive_cmds(step)
    if not run_process(f"{step.label}-copy", copy, guard):
        return False
    if not run_process(f"{step.label}-check", check, guard):
        return False
    diff = [x for x in log_path(f"{step.label}-check").read_text(errors="replace").splitlines()
            if x.strip()]  # fmt: skip
    if diff:
        print(f"[{ts()}] {step.label}: CHECK FAILED ({len(diff)} differ): {diff[:5]}", flush=True)
        return False
    print(f"[{ts()}] {step.label}: verified (size + count: nothing differs) -> deleting {src}",
          flush=True)  # fmt: skip
    return run_process(f"{step.label}-delete", delete, guard)


def cache_cmd(step: Step) -> list[str]:
    """The host frame-cache builder, niced; never a shell, never another script (cache: step)."""
    return [
        "timeout", str(int(step.seconds or 7200)), "nice", "-n", "19", str(CACHE_PY),
        "scripts/build_frame_cache.py", *step.command,
    ]  # fmt: skip


TABLES_ARGS = ("--update-lock", "--accept-drift")


def tables_cmd(step: Step) -> list[str]:
    """The packet-table generator, niced; never a shell, never another script (tables: step)."""
    return ["timeout", str(int(step.seconds or 1800)), "nice", "-n", "19", str(CACHE_PY),
            "scripts/gen_packet_tables.py", *step.command]  # fmt: skip


def cache_env() -> dict[str, str]:
    """Rule 7: no bytecode, no temp files on the root disk."""
    return {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
            "TMPDIR": os.environ.get("TMPDIR", "/dev/shm/poring-lab-tmp")}  # fmt: skip


def log_path(label: str) -> Path:
    """$TMPDIR/poring-guarded-<label>.log; a target's image tag must not become a directory."""
    return LOGDIR / f"poring-guarded-{re.sub(r'[^A-Za-z0-9_.,@-]', '-', label)}.log"


def target_build_cmd(service: str, stage: str, image: str) -> list[str]:
    """`docker build --target` with the build args compose would pass for <service>."""
    cfg = json.loads(subprocess.run(
        ["docker", "compose", *VISION_FILES, *ALL, "config", "--format", "json"],
        cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout)  # fmt: skip
    build = cfg["services"][service]["build"]
    cmd = ["docker", "build", "--progress=plain", "--target", stage, "-t", image]
    for key, value in sorted((build.get("args") or {}).items()):
        cmd += ["--build-arg", f"{key}={value}"]
    return [*cmd, build["context"]]


def dev_overlay_active() -> bool:
    """True if any running poring-lab container was created through scripts/dev.sh."""
    out = subprocess.run(
        ["docker", "ps", "--filter", "label=com.docker.compose.project=poring-lab",
         "--format", '{{.Label "com.docker.compose.project.config_files"}}'],
        capture_output=True, text=True,
    ).stdout  # fmt: skip
    return "compose.dev.yaml" in out


def ts() -> str:
    return time.strftime("%H:%M:%S")


def cgroup_paths() -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for name in CONTAINERS:
        cid = subprocess.run(
            ["docker", "inspect", "-f", "{{.Id}}", name], capture_output=True, text=True
        ).stdout.strip()
        if cid:
            paths[name] = Path(f"/sys/fs/cgroup/system.slice/docker-{cid}.scope/io.pressure")
    for name, cg in EXTRA_CGROUPS.items():
        paths[name] = Path(cg) / "io.pressure"
    return {k: v for k, v in paths.items() if v.exists()}


def full_total_us(path: Path) -> int:
    return int(path.read_text().splitlines()[1].split("total=")[1])


class Guard:
    def __init__(
        self,
        paths: dict[str, Path],
        threshold: float,
        window: float,
        *,
        sustain: float = 0.0,
        spike: float | None = None,
    ) -> None:
        self.paths, self.threshold, self.window = paths, threshold, window
        self.sustain, self.spike = sustain, spike
        self.samples: collections.deque[tuple[float, dict[str, int]]] = collections.deque()
        self.above_since: dict[str, float] = {}  # cgroup -> start of its current over-threshold run
        self.worst = (0.0, "")
        self.seconds_above = 0.0  # time during which some cgroup was above --threshold
        self._last = time.monotonic()

    def describe(self) -> str:
        if not self.paths:
            return "nothing: no capture service on this host (a dedicated host, ADR-0022)"
        rule = f">{self.threshold}%"
        if self.sustain:
            rule += f" for {self.sustain:.0f}s"
        if self.spike is not None:
            rule += f" or >{self.spike}% once"
        return rule

    def breach(self) -> tuple[str, float, str] | None:
        now = time.monotonic()
        dt, self._last = now - self._last, now
        if not self.paths:
            return None
        self.samples.append((now, {k: full_total_us(p) for k, p in self.paths.items()}))
        while self.samples and now - self.samples[0][0] > self.window:
            self.samples.popleft()
        (t0, a), (t1, b) = self.samples[0], self.samples[-1]
        if t1 - t0 < self.window * 0.8:
            return None
        rates = {k: 100.0 * (b[k] - a[k]) / 1e6 / (t1 - t0) for k in b}
        name, rate = max(rates.items(), key=lambda kv: kv[1])
        if rate > self.worst[0]:
            self.worst = (rate, name)
        if rate > self.threshold:
            self.seconds_above += dt
        if self.spike is not None and rate > self.spike:
            return name, rate, f"spike above {self.spike}%"
        for cg, r in rates.items():
            if r <= self.threshold:
                self.above_since.pop(cg, None)
                continue
            since = self.above_since.setdefault(cg, now)
            if now - since >= self.sustain:
                return cg, r, f"above {self.threshold}% for {now - since:.0f}s"
        return None

    def summary(self) -> str:
        return (
            f"worst capture stall so far {self.worst[0]:.1f}% on {self.worst[1] or '-'}, "
            f"{self.seconds_above:.0f}s above {self.threshold}%"
        )


def build_env() -> dict[str, str]:
    """The environment of a build subprocess: the lab builder, nothing else changed."""
    return {**os.environ, "BUILDX_BUILDER": LAB_BUILDER}


def abort(
    proc: "subprocess.Popen[bytes]",
    label: str,
    container: str | None = None,
    gpu: bool = False,
    host: bytes | None = None,
    exec_mode: bool = False,
) -> bool:
    """SIGINT the step, then VERIFY it stopped (verify_stop); True only when verified."""
    t0 = time.monotonic()
    if container is not None:  # a PAUSED container (an R3 OFF window) cannot handle SIGINT
        subprocess.run(["docker", "unpause", container], capture_output=True, check=False)
    proc.send_signal(2)
    try:
        proc.wait(timeout=STOP_VERIFY_S)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=30)
    if exec_mode:
        return verify_stop(label, container, gpu, host, t0=t0, exec_mode=True)
    return verify_stop(label, container, gpu, host, t0=t0)


def r3_cycles(r3: Any) -> int:
    """The ON/OFF cycles the R3 schedule has closed (each closed OFF window ends one)."""
    return sum(1 for w in getattr(r3, "windows", []) if w.get("phase") == "off" and "t1" in w)


def settle_exec(label: str, worker: str, host: bytes | None, rc: int | None, *,
                sleep: Any = time.sleep, clock: Any = time.monotonic) -> bool:  # fmt: skip
    """After the `docker exec` client ended by itself: the worker must be idle again with nothing of
    ours on the GPU. Orphaned children get EXEC_SETTLE_S; what is left then is STOPPED (exec-mode
    verify_stop) -- a client that died alone (daemon hiccup, a SIGINT to it by hand) must never
    leave a training running unguarded in the worker. False only when that stop is unverified."""
    left = exec_leftovers(worker, host)
    for _ in range(EXEC_SETTLE_S):
        if not left:
            break
        sleep(1)
        left = exec_leftovers(worker, host)
    if not left:
        state = docker_state(worker)[0]
        print(f"[{ts()}] {label}: the exec ended (rc={rc}); {worker_word(worker)}, nothing of ours "
              f"on the GPU [{frigate_r3.stamp()}]", flush=True)  # fmt: skip
        if state != "running":
            print(f"[{ts()}] {label}: WORKER DOWN after the step ({worker} {state}): the next "
                  "execdev needs worker:vision@<s> (through quiet_start)", flush=True)  # fmt: skip
        return True
    print(f"[{ts()}] {label}: the docker exec client ended (rc={rc}) but {'; '.join(left)}: "
          f"stopping what is left in the worker [{frigate_r3.stamp()}]", flush=True)  # fmt: skip
    return verify_stop(label, worker, True, host, sleep=sleep, clock=clock, exec_mode=True)


def run_process(
    label: str,
    cmd: list[str],
    guard: Guard,
    env: dict[str, str] | None = None,
    r3: "frigate_r3.PairedR3 | None" = None,
    container: str | None = None,
    gpu: bool = False,
    host: bytes | None = None,
    duty: "frigate_r3.DutyController | None" = None,
    exec_mode: bool = False,
    test_abort_cycles: int = 0,
    cowatch: "frigate_r3.CoTenantWatch | None" = None,
) -> bool:
    """Run one step under the IO guard (and R3 / the duty cycle for GPU steps). ``cowatch`` (GPU
    steps; frigate_r3's R2 co-tenant exception): a co-tenant short of VRAM stops the step as an R2
    trip, and while it computes a duty-cycled step yields (YIELD_MS step sleep). ``exec_mode``
    (execdev:): ``container`` is the long-lived worker the command runs in -- R3 pauses it, a stop
    is verified in exec mode, and a normal end must leave it idle (settle_exec).
    ``test_abort_cycles``: TEST ONLY (--test-abort-after-cycles)."""
    log = log_path(label)
    seen: Any = None
    beat = 0.0
    yielded = False

    def yield_ms() -> int | None:
        return frigate_r3.YIELD_MS if yielded else None

    if duty is not None:  # the container must find a level before its first batch
        frigate_r3.write_duty(DUTY_FILE, duty.level, -1.0)
        beat = time.time()
        ms = frigate_r3.DUTY_LEVELS_MS[duty.level]
        print(
            f"[{ts()}] DUTY start level {duty.level} ({ms} ms) [{frigate_r3.stamp()}]", flush=True
        )
    builder = env.get("BUILDX_BUILDER") if env else None
    builder = f" [BUILDX_BUILDER={builder}]" if builder else ""
    print(f"[{ts()}] {label}: {' '.join(cmd)}{builder}  (log {log.name})", flush=True)
    with log.open("w") as fh:
        proc = subprocess.Popen(cmd, cwd=REPO, stdout=fh, stderr=subprocess.STDOUT, env=env)
        t_up: float | None = None
        while proc.poll() is None:
            hit = guard.breach()
            if hit:
                print(
                    f"[{ts()}] ABORT {label}: {hit[0]} full IO stall {hit[1]:.1f}% ({hit[2]})",
                    flush=True,
                )
                if duty is not None:
                    print(f"[{ts()}] DUTY summary: {json.dumps(duty.summary())}", flush=True)
                abort(proc, label, container, gpu, host, exec_mode)
                return False
            cotrip = cowatch.vram_trip(time.monotonic()) if cowatch is not None else None
            if cotrip:
                # NB: "ABORT <step>: R2 co-tenant ..." -- train-day.sh treats it like an IO trip
                # (a pause, then --resume); our share of the VRAM goes back to the co-tenant
                print(f"[{ts()}] ABORT {label}: {cotrip} [{frigate_r3.stamp()}]", flush=True)
                if duty is not None:
                    print(f"[{ts()}] DUTY summary: {json.dumps(duty.summary())}", flush=True)
                abort(proc, label, container, gpu, host, exec_mode)
                return False
            if r3 is not None:
                r3.poll()
                if duty is not None:
                    now, before = time.time(), duty.level
                    last = r3.last
                    if last is not None and last["updated"] != seen:
                        seen = last["updated"]
                        skipping = any(sk > 0 for _, sk in last["cameras"].values())
                        duty.update(now, float(last["detection_fps"]), skipping)
                        load = float(last["detection_fps"])
                    else:
                        duty.tick(now)
                        load = -1.0
                    was = yielded
                    yielded = cowatch is not None and cowatch.yielding(time.monotonic())
                    if yielded != was:
                        why_y = (
                            "a co-tenant computes: YIELDING"
                            if yielded
                            else f"the co-tenant idle {frigate_r3.YIELD_HOLD_S:g} s: back to"
                        )
                        ms_y = (
                            frigate_r3.YIELD_MS
                            if yielded
                            else frigate_r3.DUTY_LEVELS_MS[duty.level]
                        )
                        print(f"[{ts()}] DUTY {why_y} ({ms_y} ms step sleep) "
                              f"[{frigate_r3.stamp()}]", flush=True)  # fmt: skip
                    if (duty.level != before or yielded != was
                            or now - beat >= frigate_r3.DUTY_HEARTBEAT_S):  # fmt: skip
                        frigate_r3.write_duty(DUTY_FILE, duty.level, load, now, yield_ms())
                        beat = now
                    if duty.level != before:
                        ms = frigate_r3.DUTY_LEVELS_MS[duty.level]
                        print(
                            f"[{ts()}] DUTY level {before} -> {duty.level} ({ms} ms step sleep); "
                            f"fleet {load:.1f} detections/s [{frigate_r3.stamp()}]",
                            flush=True,
                        )
                if not r3.started and container is not None and container_running(container):
                    t_up = t_up or time.monotonic()
                    if (
                        our_gpu_mib() >= R3_START_MIB
                        or time.monotonic() - t_up >= R3_START_FALLBACK_S
                    ):
                        r3.start()
                        print(f"[{ts()}] R3 schedule started [{frigate_r3.stamp()}]", flush=True)
                act = r3.tick() if container is not None else None
                if act:
                    subprocess.run(["docker", act, container], capture_output=True, check=False)
                    print(f"[{ts()}] R3 {act} {container} [{frigate_r3.stamp()}]", flush=True)
                if (duty is not None and duty.held and r3.mode == "monitor"
                        and r3.result[0] == "pass"):  # fmt: skip
                    duty.hold(time.time(), False)
                    med = r3.result[1] or 0.0
                    print(f"[{ts()}] R3 re-measurement PASSED ({med:+.2f} ms over "
                          f"{r3.result[2]} kept pairs): the slowest-level hold is released "
                          f"[{frigate_r3.stamp()}]", flush=True)  # fmt: skip
                r3hit = r3.breach()
                if r3hit and r3hit[0] == "inconclusive" and duty is not None:
                    # Batt 2026-10-08: "can't measure" is not evidence of harm, and our own rule:
                    # KEEP TRAINING at the slowest level and re-measure; never stop the container.
                    # Only the infra rule (camera frame drops, HARD) stops at once, as before.
                    now = time.time()
                    duty.hold(now, True)
                    frigate_r3.write_duty(DUTY_FILE, duty.level, -1.0, now, yield_ms())
                    beat = now
                    r3.remeasure(now)
                    ms = frigate_r3.DUTY_LEVELS_MS[duty.level]
                    # NB: never the string "R3 inconclusive" here -- the running train-day.sh greps
                    # it to classify an ABORT, and this is not one
                    print(f"[{ts()}] R3: inconclusive measurement: {r3hit[1]} -> KEEP "
                          f"TRAINING at the slowest level ({ms} ms step sleep), re-measuring "
                          f"(series {r3.remeasures}); never a stop [{frigate_r3.stamp()}]",
                          flush=True)  # fmt: skip
                    r3hit = None
                if r3hit:
                    kind, detail, hard = r3hit
                    tag = (
                        f"R3-HARD {kind}: {detail} (no resume)" if hard else f"R3 {kind}: {detail}"
                    )
                    print(f"[{ts()}] ABORT {label}: {tag} [{frigate_r3.stamp()}]", flush=True)
                    print(f"[{ts()}] R3 summary: {json.dumps(r3.summary())}", flush=True)
                    if duty is not None:
                        print(f"[{ts()}] DUTY summary: {json.dumps(duty.summary())}", flush=True)
                    abort(proc, label, container, gpu, host, exec_mode)
                    return False
                if test_abort_cycles and r3_cycles(r3) >= test_abort_cycles:
                    # TEST ONLY (the worker proof, step 4): the IO trip's own path, on demand
                    print(f"[{ts()}] ABORT {label}: TEST forced stop after {r3_cycles(r3)} R3 "
                          "ON/OFF cycle(s) (--test-abort-after-cycles; handled as an IO trip) "
                          f"[{frigate_r3.stamp()}]", flush=True)  # fmt: skip
                    print(f"[{ts()}] R3 summary: {json.dumps(r3.summary())}", flush=True)
                    if duty is not None:
                        print(f"[{ts()}] DUTY summary: {json.dumps(duty.summary())}", flush=True)
                    abort(proc, label, container, gpu, host, exec_mode)
                    return False
            time.sleep(2)
    ok = proc.returncode == 0
    if exec_mode and container is not None:
        ok = settle_exec(label, container, host, proc.returncode) and ok
    if r3 is not None:
        print(f"[{ts()}] R3 summary: {json.dumps(r3.summary())}", flush=True)
    if duty is not None:
        print(f"[{ts()}] DUTY summary: {json.dumps(duty.summary())}", flush=True)
    print(
        f"[{ts()}] {label}: {'OK' if ok else f'FAILED rc={proc.returncode}'} ({guard.summary()})",
        flush=True,
    )
    return ok


def watch(seconds: float, guard: Guard, what: str, stop_cmd: list[str]) -> bool:
    print(f"[{ts()}] watching {what} for {seconds:.0f}s", flush=True)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        hit = guard.breach()
        if hit:
            print(
                f"[{ts()}] BREACH while running: {hit[0]} {hit[1]:.1f}% ({hit[2]}) -> stopping",
                flush=True,
            )
            subprocess.run(stop_cmd, cwd=REPO)
            return False
        time.sleep(2)
    print(f"[{ts()}] {what} settled ({guard.summary()})", flush=True)
    return True


def run_up(seconds: float, guard: Guard) -> bool:
    if not run_process("up", ["docker", "compose", *RUNTIME, "up", "-d"], guard):
        return False
    return watch(seconds, guard, "the running stack", ["docker", "compose", *RUNTIME, "stop"])


def backend_health(timeout: float = 3) -> dict[str, Any] | None:
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    from backend_addr import backend_ip  # the DEFAULT network's address (two networks since c2)

    ip = backend_ip(BACKEND)
    if not ip:
        return None
    try:
        with urllib.request.urlopen(f"http://{ip}:8000/health", timeout=timeout) as resp:
            data: dict[str, Any] = json.loads(resp.read())
    except (OSError, ValueError):
        return None
    return data


def write_restore_marker() -> Path | None:
    """Before a backend restart: the marker, ONLY if the mux is in ASSIST and the lock not hold."""
    health = backend_health()
    mode = health.get("mode") if health else None
    lock = (health or {}).get("capture_backend") or {}
    if mode != "ASSIST" or lock.get("backend") not in ("rdp", "console"):
        why = "no /health" if health is None else f"mode {mode}, lock {lock.get('backend')}"
        print(f"[{ts()}] mux restore: none ({why}) -> the backend boots HUMAN", flush=True)
        return None
    body = format_marker(int(lock.get("seq", 0)), int(time.time()))
    path = STATE / RESTORE_NAME
    tmp = STATE / f".{RESTORE_NAME}.tmp"
    tmp.write_text(body, encoding="ascii")
    tmp.replace(path)
    if path.read_text(encoding="ascii") != body:
        raise SystemExit("mux restore marker: read-back differs from what was written")
    print(f"[{ts()}] mux restore: ASSIST marker written ({' '.join(body.split())})", flush=True)
    return path


def remove_restore_marker(path: Path) -> None:
    path.unlink(missing_ok=True)
    gone = not path.exists()
    print(f"[{ts()}] mux restore: marker {'removed' if gone else 'STILL PRESENT'}", flush=True)
    if not gone:
        raise SystemExit(f"{path} is still there: remove it by hand before any other restart")


def await_backend(timeout: float = 60) -> dict[str, Any] | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        health = backend_health()
        if health is not None:
            return health
        time.sleep(1)
    return None


# --- the auto GM recover after a sniffer restart (Batt, 2026-10-04) ------------------------------
AUTO_RECOVER_AGENT = "auto_recover"
RECOVER_TIMEOUT_S = 300
GREEN_WAIT_S = 20


def recover_gate(health: dict[str, Any] | None) -> str | None:
    """Why the auto GM recover must NOT run now, or None: Batt's conditions, all of them."""
    if health is None:
        return "no /health"
    mode = health.get("mode")
    if mode != "ASSIST":
        return f"mux {mode} (ASSIST only; never BOT)"
    lock = health.get("capture_backend") or {}
    if lock.get("backend") not in ("rdp", "console") or lock.get("phase") != "steady":
        return f"lock {lock.get('backend')}/{lock.get('phase')} (rdp or console, steady only)"
    env = health.get("environment") or {}
    if env.get("config") != "ok":
        return f"interlock config {env.get('config')!r}"
    if env.get("state") == "green":
        return "the interlock is already green: nothing to recover"
    return None


def auto_recover_gm(*, run: Any = subprocess.run, sleep: Any = time.sleep) -> bool:
    """The GM's re-login after a sniffer restart: ONE attempt, as a plain subprocess (never under
    run_process: an IO-guard SIGINT must not land mid-login). False = it ran and failed."""
    why = recover_gate(backend_health())
    if why is not None:
        print(f"[{ts()}] auto GM recover SKIPPED: {why}", flush=True)
        return True
    log = log_path("auto-recover-gm")
    cmd = [str(REPO / ".venv" / "bin" / "python"), str(REPO / "scripts" / "ro_agent.py"),
           "recover", "gm", "--retries", "0", "--agent-id", AUTO_RECOVER_AGENT]  # fmt: skip
    print(f"[{ts()}] auto GM recover: reason=auto_recover, one attempt (log {log})", flush=True)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": str(LOGDIR)}
    with log.open("w") as fh:
        try:
            rc: int | str = run(cmd, stdout=fh, stderr=subprocess.STDOUT, env=env, check=False,
                                timeout=RECOVER_TIMEOUT_S).returncode  # fmt: skip
        except subprocess.TimeoutExpired:
            rc = f"timeout after {RECOVER_TIMEOUT_S} s"
    if rc != 0:
        tail = log.read_text(errors="replace").strip().splitlines()[-6:]
        print(f"[{ts()}] auto GM recover FAILED (rc {rc}): stop and report. Log tail:", flush=True)
        for line in tail:
            print(f"  | {line}", flush=True)
        return False
    for _ in range(GREEN_WAIT_S):
        state = ((backend_health() or {}).get("environment") or {}).get("state")
        if state == "green":
            print(f"[{ts()}] auto GM recover OK: the interlock is green again", flush=True)
            return True
        sleep(1)
    print(f"[{ts()}] auto GM recover FAILED: logged in, but the interlock is not green after "
          f"{GREEN_WAIT_S} s (state {state}): stop and report", flush=True)  # fmt: skip
    return False


def run_with_restore(
    label: str, cmd: list[str], services: list[str], guard: Guard, *, what: str
) -> bool:
    """Run a backend-replacing step with the ASSIST restore marker (ADR-0002 amendment): written
    before, removed as soon as the new backend answers /health, and in any case on the way out."""
    marker = write_restore_marker() if "backend" in services else None
    try:
        if not run_process(label, cmd, guard):
            return False
        if marker is not None:
            health = await_backend()
            remove_restore_marker(marker)  # at once: a crash from here on must boot HUMAN
            mode = health.get("mode") if health else "no /health within 60 s"
            restored = bool(health and health.get("mode_restored"))
            note = "restored automatically" if restored else "NOT restored: set it in the console"
            print(f"[{ts()}] mux after the {what}: {mode} ({note})", flush=True)
    finally:
        if marker is not None and marker.exists():
            remove_restore_marker(marker)
    return True


def run_restart(services: list[str], seconds: float, guard: Guard) -> bool:
    label = "restart:" + ",".join(services)
    if not run_with_restore(label, [*DEV, "restart", *services], services, guard, what="restart"):
        return False
    if not watch(seconds, guard, ", ".join(services), [*DEV, "stop", *services]):
        return False
    return auto_recover_gm() if "sniffer" in services else True


def run_start(services: list[str], seconds: float, guard: Guard, *, recreate: bool = False) -> bool:
    label = ("recreate:" if recreate else "start:") + ",".join(services)
    force = ["--force-recreate"] if recreate else []
    cmd = [*DEV, "up", "-d", "--no-build", *force, *services]
    if recreate:
        # Batt, 2026-10-04: ASSIST survives a guarded RECREATE too, on the same marker conditions
        # as a restart (ASSIST only, never BOT; same lock SEQ; <= 120 s).
        ok = run_with_restore(label, cmd, services, guard, what="recreate")
    else:
        ok = run_process(label, cmd, guard)
    if not ok:
        return False
    if not watch(seconds, guard, ", ".join(services), [*DEV, "stop", *services]):
        return False
    return auto_recover_gm() if recreate and "sniffer" in services else True


def run_worker(seconds: float, guard: Guard) -> int:
    """worker:vision@S -- start the long-lived worker (0 ok, 1 failed, 3 refused)."""
    label = "worker:vision"
    state, _ = docker_state(WORKER)
    if state == "running":
        why = worker_not_ready()
        if why is not None:
            print(f"[{ts()}] REFUSED {label}: {WORKER} is up but {why}", flush=True)
            return 3
        print(f"[{ts()}] {label}: {WORKER} is already up and idle: nothing started", flush=True)
        return 0
    if state not in ("stopped", "absent"):
        print(f"[{ts()}] REFUSED {label}: {WORKER} is {state}: a person must look", flush=True)
        return 3
    why = ensure_detect_dir()
    if why is not None:
        print(f"[{ts()}] REFUSED {label}: the detect directory: {why}", flush=True)
        return 3
    if not run_process(label, worker_start_cmd(), guard):
        return 1
    if not watch(seconds, guard, f"the vision worker {WORKER}", worker_stop_cmd()):
        return 1
    procs, pids = worker_procs(WORKER), gpu_pids()
    gpu = None if pids is None else sorted(set(pids) & set(procs or {}))
    if docker_state(WORKER)[0] == "running" and procs and not busy(procs) and gpu == []:
        print(f"[{ts()}] WORKER UP {WORKER}: idle ({describe(procs)}), nothing of it on the GPU "
              f"(no CUDA context) [{frigate_r3.stamp()}]", flush=True)  # fmt: skip
        return 0
    print(f"[{ts()}] WORKER NOT IDLE after its start ({WORKER} {docker_state(WORKER)[0]}; "
          f"processes {describe(procs) if procs else procs}; on the GPU {gpu}): a person must "
          "look", flush=True)  # fmt: skip
    return 1


def run_worker_stop(guard: Guard) -> int:
    """worker-stop:vision -- stop the idle worker, verified (0 ok, 1 failed, 3 refused)."""
    label = "worker-stop:vision"
    state, _ = docker_state(WORKER)
    if state in ("stopped", "absent"):
        print(f"[{ts()}] {label}: {WORKER} is already {state}", flush=True)
        return 0
    procs = worker_procs(WORKER) if state == "running" else None
    if procs is None or busy(procs):
        what = f"busy: {describe(busy(procs))}" if procs else state
        print(f"[{ts()}] REFUSED {label}: {WORKER} is {what} -- end or abort its execdev step "
              "first", flush=True)  # fmt: skip
        return 3
    if not run_process(label, worker_stop_cmd(), guard):
        return 1
    state, pids = docker_state(WORKER)[0], gpu_pids()
    ours = own_pids(b"poring_vision", pids or [])
    if state in ("stopped", "absent") and pids is not None and not ours:
        print(f"[{ts()}] WORKER STOPPED {WORKER} ({state}), nothing of ours on the GPU "
              f"[{frigate_r3.stamp()}]", flush=True)  # fmt: skip
        return 0
    gpu = "unverifiable" if pids is None else ours
    print(f"[{ts()}] WORKER STOP NOT VERIFIED: {WORKER} {state}, GPU {gpu}: a person must look",
          flush=True)  # fmt: skip
    return 1


def results_csv(step: Step) -> Path | None:
    """A training step's per-epoch results.csv (ultralytics, under the shared ./data mount): R3's
    re-baseline waits for a new row there, so a planned stop loses no epoch. None for non-training
    steps (eval, predict): they never stop for a re-baseline."""
    argv = step.command
    if "poring_vision.train" not in argv or "--eval" in argv or "--name" not in argv:
        return None
    i = argv.index("--name")
    return REPO / "data" / "train" / argv[i + 1] / "results.csv" if i + 1 < len(argv) else None


SHORT_STEP_S = 1200  # eval / predict: 60 s windows (docs/operations/r3-paired.md)
R3_START_MIB = 500  # the schedule starts once the step holds this much on the GPU (model loaded)
R3_START_FALLBACK_S = 120.0


DUTY_FILE = REPO / "state" / "train-duty" / "duty.json"  # read-only in the container: /lab-duty


def duty_for(step: Step, env: dict[str, str] | None = None) -> "frigate_r3.DutyController | None":
    """The adaptive duty cycle for a training step that reads the duty file (`--duty-file`); its
    start / floor / cap come from train-day.sh (DUTY_START, DUTY_MIN, DUTY_CAP_LEVEL,
    DUTY_CAP_UNTIL, DUTY_AFTER_ABORT)."""
    if "--duty-file" not in step.command:
        return None
    e = os.environ if env is None else env
    return frigate_r3.DutyController(
        time.time(),
        start=int(e.get("DUTY_START", frigate_r3.DUTY_FLOOR)),
        minimum=int(e.get("DUTY_MIN", 0)),
        cap_level=int(e.get("DUTY_CAP_LEVEL", 0)),
        cap_until=float(e.get("DUTY_CAP_UNTIL", 0)),
        after_abort=e.get("DUTY_AFTER_ABORT") == "1",
    )


def gpu_rules(step: Step, baseline: Path) -> "frigate_r3.PairedR3 | None":  # noqa: ARG001
    """R2 + R3 before a GPU step: the PAIRED ON/OFF measurement to run beside the IO guard
    (docs/operations/r3-paired.md), or None after printing why the step is REFUSED. Its ON/OFF
    schedule starts once the step loads the GPU (run_process)."""
    why = frigate_r3.prestart(None, co_tenants=frigate_r3.CO_TENANTS)
    if why:
        print(f"[{ts()}] REFUSED {step.label}: {why} [{frigate_r3.stamp()}]", flush=True)
        return None
    tenants = ", ".join(t.decode() for t in frigate_r3.CO_TENANTS)
    print(f"[{ts()}] R2 co-tenants (Batt 2026-10-28; never touched): {tenants} may stay on the "
          f"GPU; beside one, stop below {frigate_r3.COTENANT_FLOOR_MIB} MiB free VRAM and yield "
          f"({frigate_r3.YIELD_MS} ms step sleep) while it computes", flush=True)  # fmt: skip
    short = (step.seconds or 600) <= SHORT_STEP_S
    win, settle, _ = frigate_r3.SHORT_WIN if short else frigate_r3.TRAIN_WIN
    print(f"[{ts()}] R3 (paired): {win:g} s ON / {win:g} s OFF windows ({settle:g} s settle) by "
          f"docker pause; abort if the median ON-OFF detector delta > +{frigate_r3.DELTA_MS:g} ms "
          f"over >= {frigate_r3.PAIR_MIN} load-matched pairs; any camera dropping frames for "
          f"{frigate_r3.DROP_S:g} s; Ollama loading a model", flush=True)  # fmt: skip
    return frigate_r3.PairedR3(short=short, cam_ref=frigate_r3.camera_reference(), started=False)


GpuGuards = tuple[
    "frigate_r3.PairedR3 | None", "frigate_r3.CoTenantWatch | None",
    "frigate_r3.DutyController | None",
]  # fmt: skip


def gpu_guards(step: Step, baseline: Path, profile: host_profile.HostProfile | None = None
               ) -> GpuGuards | None:  # fmt: skip
    """The rules a GPU step runs under on THIS host: (R3, the R2 co-tenant watch, the duty cycle),
    or None when the step is refused. A shared host (VM 103) gets all three, exactly as before; a
    DEDICATED host none (ADR-0022 decision 3, Batt 2026-11-07: "use it fully, no limits like this
    machine": no Frigate, no Ollama, no co-tenant there)."""
    prof = PROFILE if profile is None else profile
    if not prof.shared:
        print(f"[{ts()}] {step.label}: host profile {prof.name} is DEDICATED: R1-R3, the co-tenant "
              "watch and the duty cycle do not apply here (ADR-0022)", flush=True)  # fmt: skip
        return None, None, None
    r3 = gpu_rules(step, baseline)
    if r3 is None:
        return None
    return r3, frigate_r3.CoTenantWatch().start(), duty_for(step)


def dedicated_refusal(found: list[str], profile: host_profile.HostProfile | None = None
                      ) -> str | None:  # fmt: skip
    """A host DECLARED dedicated must not run what the shared rules protect: any capture service
    (quant, Frigate) found there means the declaration is wrong, and every step is refused."""
    prof = PROFILE if profile is None else profile
    hit = sorted(n for n in found if n in CONTAINERS)
    if prof.shared or not hit:
        return None
    return (
        f"REFUSED: host profile {prof.name} says DEDICATED, but {', '.join(hit)} run here: "
        "the shared rules protect them. Fix LAB_HOST_PROFILE (ADR-0022)."
    )


def our_gpu_mib() -> int:
    """MiB on the GPU held by OUR processes (uid + poring_vision in the command line)."""
    try:
        query = [
            "nvidia-smi",
            "--query-compute-apps=pid,used_memory",
            "--format=csv,noheader,nounits",
        ]
        out = subprocess.run(query, capture_output=True, text=True, timeout=15, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return 0
    rows = [line.split(",") for line in out.splitlines() if "," in line]
    mib = {int(p): int(m) for p, m in rows if p.strip().isdigit() and m.strip().isdigit()}
    return sum(mib[p] for p in own_pids(b"poring_vision", list(mib)))


# --- ADR-0007 Amendment C (ACCEPTED, Batt 2026-10-13): the sniffer's code from the host -----------
SNIFFER_SRC = "packages/poring_packets"


def sniffer_code_gate(steps: list[Step], root: Path = REPO,
                      git: Any = subprocess.run) -> str | None:  # fmt: skip
    """A step that (re)creates the sniffer runs its code from the host tree (compose.dev.yaml's
    sniffer overlay), so only COMMITTED code may go live: a dirty packages/poring_packets refuses.
    The commit is recorded (SNIFFER_COMMIT, read by compose at create time and stamped into the
    sniffer's start log and every capture's header). `restart:sniffer` refuses: a restart keeps
    the environment of the container's creation, so it could run new code under an old commit --
    use `recreate:sniffer`. Returns a refusal, or None (and sets os.environ["SNIFFER_COMMIT"])."""
    kinds = ("start", "recreate", "restart")
    hit = [s for s in steps if s.kind in kinds and "sniffer" in s.services]
    if not hit:
        return None
    if any(s.kind == "restart" for s in hit):
        return ("restart:sniffer: refused -- the sniffer runs the host's code (ADR-0007 "
                "Amendment C) and a restart keeps its old SNIFFER_COMMIT; "
                "use recreate:sniffer")  # fmt: skip
    st = git(["git", "status", "--porcelain", "--", SNIFFER_SRC], cwd=root, capture_output=True,
             text=True, check=False)  # fmt: skip
    if st.returncode != 0:
        return f"sniffer: refused -- git status failed ({st.returncode}): the code cannot be named"
    if st.stdout.strip():
        return (f"sniffer: refused -- {SNIFFER_SRC} has uncommitted changes; only committed code "
                "goes live (ADR-0007 Amendment C)")  # fmt: skip
    head = git(["git", "rev-parse", "--short=12", "HEAD"], cwd=root, capture_output=True,
               text=True, check=False)  # fmt: skip
    commit = head.stdout.strip()
    if head.returncode != 0 or not commit:
        return "sniffer: refused -- the commit cannot be read"
    os.environ["SNIFFER_COMMIT"] = commit
    print(f"[{ts()}] sniffer code: {commit} (committed; passed as SNIFFER_COMMIT)", flush=True)
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("steps", nargs="+")
    ap.add_argument("--threshold", type=float, default=10.0)
    ap.add_argument("--window", type=float, default=10.0)
    ap.add_argument("--sustain", type=float, default=0.0, help="seconds above --threshold")
    ap.add_argument("--spike", type=float, default=None, help="abort at once above this %%")
    ap.add_argument(
        "--frigate-baseline", type=Path, default=frigate_r3.BASELINE,
        help="R3: the Frigate baseline (frigate_r3.py baseline) for vision steps",
    )  # fmt: skip
    ap.add_argument(
        "--test-abort-after-cycles", type=int, default=0, metavar="N",
        help="TEST ONLY (worker proof): abort a GPU step as on an IO trip once its R3 schedule has "
             "closed N ON/OFF cycles",
    )  # fmt: skip
    args = ap.parse_args()
    try:
        steps = [parse_step(s) for s in args.steps]
    except ValueError as exc:
        print(exc, flush=True)
        return 2
    if args.test_abort_after_cycles:
        if args.test_abort_after_cycles < 0 or not any(
            s.kind in ("run", "rundev", "execdev") for s in steps
        ):
            print("--test-abort-after-cycles: a positive N, and only with a GPU step (run:, "
                  "rundev:, execdev:)", flush=True)  # fmt: skip
            return 2
        print(f"[{ts()}] TEST ONLY: GPU steps are aborted as on an IO trip after "
              f"{args.test_abort_after_cycles} R3 ON/OFF cycle(s)", flush=True)  # fmt: skip
    if any(s.kind == "up" for s in steps) and dev_overlay_active():
        print(
            "up: refused -- the dev overlay (scripts/dev.sh) is running. A plain `compose up` "
            "would recreate backend/desktop without their mounts and build the production "
            "frontend. Use start:<svc>[,<svc>...][@<seconds>].",
            flush=True,
        )
        return 2
    if (why := sniffer_code_gate(steps)) is not None:
        print(why, flush=True)
        return 2
    paths = cgroup_paths()
    if (why := dedicated_refusal(list(paths))) is not None:
        print(why, flush=True)
        return 2
    if not PROFILE.shared:  # nothing of the shared host's to protect here (ADR-0022)
        paths = {}
    if all(s.kind == "worker" for s in steps) and io_baseline.frigate_io_ignored(
        args.steps, time.time()
    ):  # Batt 2026-11-07: that day, a worker:vision start leaves Frigate's IO stall out
        paths.pop("frigate", None)
        print(f"[{ts()}] frigate's IO stall is NOT watched for this worker:vision start (Batt "
              "2026-11-07, io_baseline.FRIGATE_IO_IGNORED)", flush=True)  # fmt: skip
    guard = Guard(paths, args.threshold, args.window, sustain=args.sustain, spike=args.spike)
    print(f"[{ts()}] rule: abort if {guard.describe()}", flush=True)
    print(f"[{ts()}] watching: {', '.join(guard.paths)}", flush=True)
    for step in steps:
        if step.kind == "build":
            cmd = ["docker", "compose", *VISION_FILES, *ALL, "build", "--progress=plain",
                   *step.services]  # fmt: skip
            ok = run_process(step.label, cmd, guard, env=build_env())
        elif step.kind == "pull":
            ok = run_process(step.label, ["docker", "compose", *VISION_FILES, *ALL, "pull",
                                          *step.services], guard)  # fmt: skip
        elif step.kind == "target":
            ok = run_process(step.label, target_build_cmd(*step.services), guard, env=build_env())
        elif step.kind in ("run", "rundev"):
            rules = gpu_guards(step, args.frigate_baseline)
            if rules is None:
                return 3
            r3, cowatch, duty = rules
            try:
                ok = run_process(
                    step.label,
                    run_cmd(step),
                    guard,
                    r3=r3,
                    container=container_name(step),
                    gpu=True,
                    duty=duty,
                    test_abort_cycles=args.test_abort_after_cycles,
                    cowatch=cowatch,
                )
            finally:
                if cowatch is not None:
                    cowatch.stop()
            tail = log_path(step.label).read_text(errors="replace").splitlines()[-80:]
            print("\n".join(f"  | {line}" for line in tail), flush=True)
        elif step.kind == "execdev":
            why = worker_not_ready()
            if why is not None:
                print(f"[{ts()}] REFUSED {step.label}: WORKER {why} [{frigate_r3.stamp()}]",
                      flush=True)  # fmt: skip
                return 3
            rules = gpu_guards(step, args.frigate_baseline)
            if rules is None:
                return 3
            r3, cowatch, duty = rules
            try:
                ok = run_process(
                    step.label,
                    exec_cmd(step),
                    guard,
                    r3=r3,
                    container=WORKER,
                    gpu=True,
                    host=EXEC_HOST,
                    duty=duty,
                    exec_mode=True,
                    test_abort_cycles=args.test_abort_after_cycles,
                    cowatch=cowatch,
                )
            finally:
                if cowatch is not None:
                    cowatch.stop()
            tail = log_path(step.label).read_text(errors="replace").splitlines()[-80:]
            print("\n".join(f"  | {line}" for line in tail), flush=True)
        elif step.kind in ("worker", "worker-stop"):
            rc = (
                run_worker(step.seconds or 120, guard)
                if step.kind == "worker"
                else run_worker_stop(guard)
            )
            if rc:
                return rc
            ok = True
        elif step.kind == "tables":
            ok = run_process(step.label, tables_cmd(step), guard, env=cache_env(),
                             host=b"scripts/gen_packet_tables.py")  # fmt: skip
            tail = log_path(step.label).read_text(errors="replace").splitlines()[-20:]
            print("\n".join(f"  | {line}" for line in tail), flush=True)
        elif step.kind == "archive":
            ok = run_archive(step, guard)
        elif step.kind in ("voldump", "volrm"):
            ok = run_volume(step, guard)
        elif step.kind == "measure":
            ok = run_process(step.label, measure_cmd(step), guard)
            tail = log_path(step.label).read_text(errors="replace").splitlines()
            print("\n".join(f"  | {line}" for line in tail[-200:]), flush=True)
        elif step.kind == "cache":
            ok = run_process(step.label, cache_cmd(step), guard, env=cache_env(),
                             host=b"scripts/build_frame_cache.py")  # fmt: skip
            tail = log_path(step.label).read_text(errors="replace").splitlines()[-20:]
            print("\n".join(f"  | {line}" for line in tail), flush=True)
        elif step.kind in ("replay", "replaydev"):
            table = REPLAY_DEV_SRC / "poring_packets" / "_generated" / "lengths.json"
            if step.kind == "replaydev" and not table.exists():
                print(f"[{ts()}] {step.label}: {table} missing: run scripts/gen_packet_tables.py "
                      "in this checkout first", flush=True)  # fmt: skip
                return 1
            volume = captures_volume()
            files = select_captures(list_captures(volume), *step.services)
            if not files:
                print(f"[{ts()}] {step.label}: no capture file in that range", flush=True)
                return 1
            out = replay_out(step)
            out.mkdir(parents=True, exist_ok=True)
            name = f"poring-lab-replay-{os.getpid()}"
            print(
                f"[{ts()}] {step.label}: {len(files)} file(s) {files[0]} .. {files[-1]}", flush=True
            )
            ok = run_process(step.label, replay_cmd(step, volume, files, name), guard,
                             container=name)  # fmt: skip
            tail = log_path(step.label).read_text(errors="replace").splitlines()[-20:]
            print("\n".join(f"  | {line}" for line in tail), flush=True)
            if ok:
                n = sum(1 for _ in (out / "events.jsonl").open())
                print(f"[{ts()}] {step.label}: {n} events -> {out / 'events.jsonl'}", flush=True)
        elif step.kind == "up":
            ok = run_up(step.seconds or 180, guard)
        elif step.kind == "restart":
            ok = run_restart(step.services, step.seconds or 180, guard)
        elif step.kind == "rm":
            ok = run_process(step.label, [*DEV, "rm", "-s", "-f", *step.services], guard)
        else:
            ok = run_start(
                step.services, step.seconds or 180, guard, recreate=step.kind == "recreate"
            )
        if not ok:
            return 1
    print(f"[{ts()}] ALL STEPS OK ({guard.summary()})", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
