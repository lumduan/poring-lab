"""Run disk-heavy docker steps ONE AT A TIME and back off the moment live capture suffers.

This host keeps Docker, the quant capture engines and their databases on ONE virtual disk (no IO
isolation). On 2026-09-29 an unguarded parallel build pushed the capture engines' IO stall from
<=4% to 82-88%. So on this host, heavy builds/pulls go through this script.

It watches the IO *full*-stall rate of the capture cgroups (from cumulative `total=` counters, not
avg10) and backs off above --threshold percent over a --window-second rolling window:
  build:<svc>   docker compose build <svc>                  breach -> SIGINT (build cancelled)
  pull:<svc>    docker compose pull <svc>                   breach -> SIGINT
  up:<seconds>  compose up -d (core+remote), watch seconds  breach -> compose stop

    python3 scripts/guarded_build.py --threshold 10 build:desktop build:rathena pull:db up:180
    python3 scripts/guarded_build.py build:vision   # ~5 GB of writes: run in an operator window

Logs go to $TMPDIR/poring-guarded-*.log. Exit 0 only if every step completed without a breach.
"""

import argparse
import collections
import os
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
    def __init__(self, paths: dict[str, Path], threshold: float, window: float) -> None:
        self.paths, self.threshold, self.window = paths, threshold, window
        self.samples: collections.deque[tuple[float, dict[str, int]]] = collections.deque()
        self.worst = (0.0, "")

    def breach(self) -> tuple[str, float] | None:
        now = time.monotonic()
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
        return (name, rate) if rate > self.threshold else None


def run_process(label: str, cmd: list[str], guard: Guard) -> bool:
    log = LOGDIR / f"poring-guarded-{label.replace(':', '-')}.log"
    print(f"[{ts()}] {label}: {' '.join(cmd)}  (log {log.name})", flush=True)
    with log.open("w") as fh:
        proc = subprocess.Popen(cmd, cwd=REPO, stdout=fh, stderr=subprocess.STDOUT)
        while proc.poll() is None:
            hit = guard.breach()
            if hit:
                print(
                    f"[{ts()}] ABORT {label}: {hit[0]} full IO stall {hit[1]:.1f}% "
                    f"(threshold {guard.threshold}%)",
                    flush=True,
                )
                proc.send_signal(2)
                proc.wait(timeout=120)
                return False
            time.sleep(2)
    ok = proc.returncode == 0
    print(
        f"[{ts()}] {label}: {'OK' if ok else f'FAILED rc={proc.returncode}'} "
        f"(worst capture stall so far {guard.worst[0]:.1f}% on {guard.worst[1] or '-'})",
        flush=True,
    )
    return ok


def run_up(seconds: float, guard: Guard) -> bool:
    if not run_process("up", ["docker", "compose", *RUNTIME, "up", "-d"], guard):
        return False
    print(f"[{ts()}] watching the running stack for {seconds:.0f}s", flush=True)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        hit = guard.breach()
        if hit:
            print(
                f"[{ts()}] BREACH while running: {hit[0]} {hit[1]:.1f}% -> stopping the stack",
                flush=True,
            )
            subprocess.run(["docker", "compose", *RUNTIME, "stop"], cwd=REPO)
            return False
        time.sleep(2)
    print(
        f"[{ts()}] stack settled (worst capture stall {guard.worst[0]:.1f}% on "
        f"{guard.worst[1] or '-'})",
        flush=True,
    )
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("steps", nargs="+")
    ap.add_argument("--threshold", type=float, default=10.0)
    ap.add_argument("--window", type=float, default=10.0)
    args = ap.parse_args()
    guard = Guard(cgroup_paths(), args.threshold, args.window)
    print(f"[{ts()}] watching: {', '.join(guard.paths)}", flush=True)
    for step in args.steps:
        kind, _, arg = step.partition(":")
        if kind == "build":
            ok = run_process(
                step, ["docker", "compose", *ALL, "build", "--progress=plain", arg], guard
            )
        elif kind == "pull":
            ok = run_process(step, ["docker", "compose", *ALL, "pull", arg], guard)
        elif kind == "up":
            ok = run_up(float(arg or 180), guard)
        else:
            print(f"unknown step {step}", flush=True)
            return 2
        if not ok:
            return 1
    print(
        f"[{ts()}] ALL STEPS OK (worst capture stall {guard.worst[0]:.1f}% on {guard.worst[1]})",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
