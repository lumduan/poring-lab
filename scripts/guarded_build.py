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
  recreate:<svc>[,<svc>...][@<seconds>]
                the same with --force-recreate (re-binds single-file mounts, e.g. after a
                bind-mounted script was replaced by a new inode). An unguarded force-recreate of
                desktop on 2026-10-01 hit 30.8 % quant-postgres io_full for 10 s.

    python3 scripts/guarded_build.py build:desktop build:rathena pull:db up:180        # strict 10%
    python3 scripts/guarded_build.py --sustain 30 --spike 25 build:rathena             # tolerant
    python3 scripts/guarded_build.py --sustain 30 --spike 25 start:db@120 start:rathena@240
    python3 scripts/guarded_build.py build:vision   # ~5 GB of writes: run in an operator window

Logs go to $TMPDIR/poring-guarded-*.log. Exit 0 only if every step completed without a breach.
"""

import argparse
import collections
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LOGDIR = Path(os.environ.get("TMPDIR", "/tmp"))
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
ALL = ["--profile", "core", "--profile", "remote", "--profile", "vision"]
RUNTIME = ["--profile", "core", "--profile", "remote"]
# Dev mode (compose.yaml + compose.dev.yaml, see scripts/dev.sh) plus the core and sniffer profiles,
# so `start:sniffer` is guarded too (an unguarded sniffer recreate right after a guarded db/rathena
# start coincided with 67 % quant-postgres io_full for ~20 s, 2026-10-01). `up -d <services>` still
# starts only the named services.
DEV = ["scripts/dev.sh", "--profile", "core", "--profile", "sniffer"]
SERVICE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class Step:
    """One parsed command-line step (see the module docstring)."""

    def __init__(self, kind: str, services: list[str], seconds: float | None = None) -> None:
        self.kind, self.services, self.seconds = kind, services, seconds

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
    raise ValueError(f"unknown step {step}")


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


def run_process(label: str, cmd: list[str], guard: Guard) -> bool:
    log = LOGDIR / f"poring-guarded-{label.replace(':', '-')}.log"
    print(f"[{ts()}] {label}: {' '.join(cmd)}  (log {log.name})", flush=True)
    with log.open("w") as fh:
        proc = subprocess.Popen(cmd, cwd=REPO, stdout=fh, stderr=subprocess.STDOUT)
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


def run_restart(services: list[str], seconds: float, guard: Guard) -> bool:
    if not run_process("restart:" + ",".join(services), [*DEV, "restart", *services], guard):
        return False
    return watch(seconds, guard, ", ".join(services), [*DEV, "stop", *services])


def run_start(services: list[str], seconds: float, guard: Guard, *, recreate: bool = False) -> bool:
    label = ("recreate:" if recreate else "start:") + ",".join(services)
    force = ["--force-recreate"] if recreate else []
    if not run_process(label, [*DEV, "up", "-d", "--no-build", *force, *services], guard):
        return False
    return watch(seconds, guard, ", ".join(services), [*DEV, "stop", *services])


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
            ok = run_process(step.label, cmd, guard)
        elif step.kind == "pull":
            ok = run_process(step.label, ["docker", "compose", *ALL, "pull", *step.services], guard)
        elif step.kind == "target":
            ok = run_process(step.label, target_build_cmd(*step.services), guard)
        elif step.kind == "up":
            ok = run_up(step.seconds or 180, guard)
        elif step.kind == "restart":
            ok = run_restart(step.services, step.seconds or 180, guard)
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
