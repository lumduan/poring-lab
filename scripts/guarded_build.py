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
  run:<svc>[@<seconds>]=<command>
                docker compose --profile <svc> run --rm --no-deps <svc> <command>, killed after
                <seconds> (default 600), its output's tail printed. ONLY `vision` (check_gpu.py):
                a second gamestream would be a second lab client, a second desktop a second
                xfreerdp (ADR-0001/0009). The hook and scripts/dev.sh refuse a raw `compose run`.
  rundev:<svc>[@<seconds>]=<command>
                the same with `-f compose.yaml -f compose.vision-dev.yaml`: the host's vision
                source read-only, first on PYTHONPATH (training runs iterate without rebuilding the
                ~5 GB torch image; the overlay adds nothing else, test_guards). ONLY `vision`.
  cache[@<seconds>]=<args>
                the HOST frame-cache builder, `nice -n 19 .venv/bin/python
                scripts/build_frame_cache.py <args>` (it reads sessions from the NAS and writes tar
                shards to it; nothing on the root disk), killed after <seconds> (default 7200).
                Nothing else runs through it. A breach sends SIGINT: re-run with `--resume` later
                (Batt, 2026-10-06: daytime caches pause on a trip and resume, never retry fast).

    python3 scripts/guarded_build.py build:desktop build:rathena pull:db up:180        # strict 10%
    python3 scripts/guarded_build.py --sustain 30 --spike 25 build:rathena             # tolerant
    python3 scripts/guarded_build.py --sustain 30 --spike 25 start:db@120 start:rathena@240
    python3 scripts/guarded_build.py build:vision   # ~5 GB of writes: run in an operator window
    python3 scripts/guarded_build.py 'run:vision@600=python scripts/check_gpu.py'  # GPU check
    python3 scripts/guarded_build.py --sustain 30 --spike 25 \
        'rundev:vision@3600=python -m poring_vision.train --cache /datasets/.framecache/ID --smoke'
    python3 scripts/guarded_build.py --sustain 30 --spike 25 \
        'cache@7200=--train S1 S2 --val S3 --test S4 --cache-id ID --labels v0 --resume'

Logs go to $TMPDIR/poring-guarded-*.log. Exit 0 only if every step completed without a breach.
"""

import argparse
import collections
import json
import os
import re
import shlex
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
    if kind in ("run", "rundev"):
        head, eq, command = arg.partition("=")
        name, _, secs = head.partition("@")
        argv = shlex.split(command)
        if not eq or not argv or not SERVICE.match(name):
            raise ValueError(f"{step}: expected {kind}:<svc>[@<seconds>]=<command>")
        if name not in RUN_ALLOWED:
            raise ValueError(f"{step}: run: is allowed only for {', '.join(sorted(RUN_ALLOWED))}")
        return Step(kind, [name], float(secs or 600), argv)
    if kind == "cache" or step.startswith("cache@") or step.startswith("cache="):
        head, eq, command = step.partition("=")
        _, _, secs = head.partition("@")
        argv = shlex.split(command)
        if head not in ("cache", f"cache@{secs}") or not eq or not argv:
            raise ValueError(f"{step}: expected cache[@<seconds>]=<build_frame_cache args>")
        if any(not a.startswith("-") and not CACHE_ARG.match(a) for a in argv):
            raise ValueError(f"{step}: cache: takes build_frame_cache options and session ids")
        return Step("cache", [], float(secs or 7200), argv)
    raise ValueError(f"unknown step {step}")


VISION_DEV = ["-f", "compose.yaml", "-f", "compose.vision-dev.yaml"]  # rundev: the overlay


def run_cmd(step: Step) -> list[str]:
    svc = step.services[0]
    seconds = str(int(step.seconds or 600))
    files = VISION_DEV if step.kind == "rundev" else []
    return [
        "timeout", seconds, "docker", "compose", *files, "--profile", svc, "run", "--rm",
        "--no-deps", svc, *step.command,
    ]  # fmt: skip


CACHE_ARG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")  # session ids, ids, numbers, paths
CACHE_PY = REPO / ".venv" / "bin" / "python"


def cache_cmd(step: Step) -> list[str]:
    """The host frame-cache builder, niced; never a shell, never another script (cache: step)."""
    return [
        "timeout", str(int(step.seconds or 7200)), "nice", "-n", "19", str(CACHE_PY),
        "scripts/build_frame_cache.py", *step.command,
    ]  # fmt: skip


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
        ["docker", "compose", *ALL, "config", "--format", "json"],
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
        rule = f">{self.threshold}%"
        if self.sustain:
            rule += f" for {self.sustain:.0f}s"
        if self.spike is not None:
            rule += f" or >{self.spike}% once"
        return rule

    def breach(self) -> tuple[str, float, str] | None:
        now = time.monotonic()
        dt, self._last = now - self._last, now
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


def run_process(
    label: str, cmd: list[str], guard: Guard, env: dict[str, str] | None = None
) -> bool:
    log = log_path(label)
    builder = env.get("BUILDX_BUILDER") if env else None
    builder = f" [BUILDX_BUILDER={builder}]" if builder else ""
    print(f"[{ts()}] {label}: {' '.join(cmd)}{builder}  (log {log.name})", flush=True)
    with log.open("w") as fh:
        proc = subprocess.Popen(cmd, cwd=REPO, stdout=fh, stderr=subprocess.STDOUT, env=env)
        while proc.poll() is None:
            hit = guard.breach()
            if hit:
                print(
                    f"[{ts()}] ABORT {label}: {hit[0]} full IO stall {hit[1]:.1f}% ({hit[2]})",
                    flush=True,
                )
                proc.send_signal(2)
                proc.wait(timeout=120)
                return False
            time.sleep(2)
    ok = proc.returncode == 0
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("steps", nargs="+")
    ap.add_argument("--threshold", type=float, default=10.0)
    ap.add_argument("--window", type=float, default=10.0)
    ap.add_argument("--sustain", type=float, default=0.0, help="seconds above --threshold")
    ap.add_argument("--spike", type=float, default=None, help="abort at once above this %%")
    args = ap.parse_args()
    try:
        steps = [parse_step(s) for s in args.steps]
    except ValueError as exc:
        print(exc, flush=True)
        return 2
    if any(s.kind == "up" for s in steps) and dev_overlay_active():
        print(
            "up: refused -- the dev overlay (scripts/dev.sh) is running. A plain `compose up` "
            "would recreate backend/desktop without their mounts and build the production "
            "frontend. Use start:<svc>[,<svc>...][@<seconds>].",
            flush=True,
        )
        return 2
    guard = Guard(
        cgroup_paths(), args.threshold, args.window, sustain=args.sustain, spike=args.spike
    )
    print(f"[{ts()}] rule: abort if {guard.describe()}", flush=True)
    print(f"[{ts()}] watching: {', '.join(guard.paths)}", flush=True)
    for step in steps:
        if step.kind == "build":
            cmd = ["docker", "compose", *ALL, "build", "--progress=plain", *step.services]
            ok = run_process(step.label, cmd, guard, env=build_env())
        elif step.kind == "pull":
            ok = run_process(step.label, ["docker", "compose", *ALL, "pull", *step.services], guard)
        elif step.kind == "target":
            ok = run_process(step.label, target_build_cmd(*step.services), guard, env=build_env())
        elif step.kind in ("run", "rundev"):
            ok = run_process(step.label, run_cmd(step), guard)
            tail = log_path(step.label).read_text(errors="replace").splitlines()[-80:]
            print("\n".join(f"  | {line}" for line in tail), flush=True)
        elif step.kind == "cache":
            ok = run_process(step.label, cache_cmd(step), guard, env=cache_env())
            tail = log_path(step.label).read_text(errors="replace").splitlines()[-20:]
            print("\n".join(f"  | {line}" for line in tail), flush=True)
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
