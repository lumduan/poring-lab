"""Record IO pressure of the live-capture cgroups and the poring-lab containers (stdlib only).

    setsid nohup python3 scripts/io_baseline.py --hours 24 >/dev/null 2>&1 &
    kill "$(cat data/metrics/io_baseline.pid)"      # stop early

Every --interval seconds it appends ONE wide CSV row (small append, no fsync) to
data/metrics/io_pressure_<start>.csv (gitignored). Per cgroup:
  <name>.full10  kernel "full" avg10 (%)          <name>.some10  kernel "some" avg10 (%)
  <name>.full    full-stall % over the last interval, from the cumulative total (exact)
Used to pick the disk-split window and guard thresholds (scripts/guarded_build.py). Container ids
are re-resolved every minute, so restarts are followed; a missing cgroup leaves empty cells.
"""

import argparse
import csv
import os
import signal
import subprocess
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CAPTURE = [
    "quant-orderbook-engine",
    "quant-ticker-engine",
    "quant-crypto-engine",
    "quant-marketdata-engine",
    "quant-postgres",
    "quant-mongo",
    "frigate",
]
# vision-worker: option A's long-lived vision container (docs/operations/vision-long-lived.md)
LAB = ["desktop", "backend", "frontend-dev", "frontend", "rathena", "db", "vision", "vision-worker"]
CRON = ("cron.service", Path("/sys/fs/cgroup/system.slice/cron.service/io.pressure"))
# Batt 2026-11-07 ~09:4x ICT (asked: "can the worker's start also ignore Frigate's IO stall for
# today, still guarding every quant cgroup?" -> "Ignore Frigate today"): for a `worker:vision`
# START only, and only inside this window, Frigate's IO stall neither gates runbooks/quiet_start.py
# nor aborts guarded_build's guard for that step. Every quant cgroup and cron's capture still do.
# docs/operations/r3-paired.md "2026-11-07". Outside the window: unchanged, no code change needed.
_ICT = timezone(timedelta(hours=7))
FRIGATE_IO_IGNORED = (datetime(2026, 11, 7, 9, 0, tzinfo=_ICT).timestamp(),
                      datetime(2026, 11, 8, 0, 0, tzinfo=_ICT).timestamp())  # fmt: skip


def frigate_io_ignored(command: Sequence[str], now: float) -> bool:
    """PURE: Frigate's IO stall is left out for this command at ``now`` (epoch s): a worker:vision
    start, inside FRIGATE_IO_IGNORED."""
    starts = any(str(a).startswith("worker:vision") for a in command)
    return starts and FRIGATE_IO_IGNORED[0] <= now < FRIGATE_IO_IGNORED[1]


def resolve() -> dict[str, Path]:
    """name -> io.pressure path for every watched cgroup that currently exists."""
    out = subprocess.run(
        [
            "docker",
            "ps",
            "--no-trunc",
            "--format",
            '{{.ID}} {{.Names}} {{.Label "com.docker.compose.project"}} '
            '{{.Label "com.docker.compose.service"}}',
        ],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    paths: dict[str, Path] = {}
    for line in out.splitlines():
        cid, name, project, service = (line.split(" ") + ["", "", "", ""])[:4]
        cg = Path(f"/sys/fs/cgroup/system.slice/docker-{cid}.scope/io.pressure")
        if name in CAPTURE:
            paths[name] = cg
        elif project == "poring-lab" and service in LAB:
            paths[f"lab-{service}"] = cg
    paths[CRON[0]] = CRON[1]
    return {k: v for k, v in paths.items() if v.exists()}


def read(path: Path) -> tuple[float, float, int] | None:
    try:
        some, full = path.read_text().splitlines()[:2]
    except OSError:
        return None
    avg10 = lambda line: float(line.split("avg10=")[1].split()[0])  # noqa: E731
    return avg10(some), avg10(full), int(full.split("total=")[1])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--interval", type=float, default=10.0)
    args = ap.parse_args()

    outdir = REPO / "data" / "metrics"
    outdir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(UTC)
    csv_path = outdir / f"io_pressure_{started:%Y%m%dT%H%M%SZ}.csv"
    pid_path = outdir / "io_baseline.pid"
    pid_path.write_text(f"{os.getpid()}\n")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    names = CAPTURE + [f"lab-{s}" for s in LAB] + [CRON[0]]
    header = ["utc", "mono_s"] + [f"{n}.{m}" for n in names for m in ("full10", "some10", "full")]
    deadline = time.monotonic() + args.hours * 3600
    paths: dict[str, Path] = {}
    last_resolve = -1e9
    previous: dict[str, tuple[float, int]] = {}  # name -> (mono, full_total_us)
    try:
        with csv_path.open("a", newline="", buffering=1) as fh:
            writer = csv.writer(fh)
            writer.writerow(header)
            while time.monotonic() < deadline:
                now = time.monotonic()
                if now - last_resolve >= 60:
                    paths, last_resolve = resolve(), now
                row: list[object] = [datetime.now(UTC).isoformat(timespec="seconds"), f"{now:.1f}"]
                for name in names:
                    sample = read(paths[name]) if name in paths else None
                    if sample is None:
                        row += ["", "", ""]
                        previous.pop(name, None)
                        continue
                    some10, full10, total = sample
                    rate = ""
                    if name in previous and now > previous[name][0]:
                        t0, tot0 = previous[name]
                        rate = f"{100 * (total - tot0) / 1e6 / (now - t0):.2f}"
                    previous[name] = (now, total)
                    row += [f"{full10:.2f}", f"{some10:.2f}", rate]
                writer.writerow(row)
                time.sleep(max(0.0, args.interval - (time.monotonic() - now)))
    finally:
        pid_path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
