#!/usr/bin/env python3
"""Host pressure evidence around lab changes (CLAUDE.md rule 5): is the quant stack affected?

    pressure_sampler.py run OUT.csv SECONDS
        1 s samples, append-only CSV: cpu.pressure + io.pressure totals (some/full, us) of the quant
        cgroups and cron, plus cpu.stat usage/throttling of the lab containers. Read-only on /sys.
        Keep OUT on /dev/shm (rule 7).

    pressure_sampler.py around OUT.csv HH:MM:SS [--window 300]
        The "5 min before / after" reading for an event at wall time HH:MM:SS (the CSV's t_wall,
        host local time): per quant cgroup, the % of wall time with ANY task (some) / ALL tasks
        (full) stalled on IO and CPU, before vs after; plus each lab container's mean cores.

    pressure_sampler.py peaks OUT.csv FROM TO [--bin 10]
        Worst 10 s io_full bins for quant-postgres between two wall times (HH:MM:SS).

io_full is the number to watch: the share of time quant-postgres had all of its runnable tasks
stalled on IO (the 2026-09-29 incident pushed it from <=4 % to 82-88 %).
"""

import argparse
import csv
import subprocess
import sys
import time
from pathlib import Path

QUANT = [
    "quant-postgres",
    "quant-orderbook-engine",
    "quant-ticker-engine",
    "quant-crypto-engine",
    "quant-marketdata-engine",
    "quant-mongo",
]
LAB = [
    "poring-lab-desktop-1",
    "poring-lab-backend-1",
    "poring-lab-frontend-dev-1",
    "poring-lab-rathena-1",
    "poring-lab-sniffer-1",
]
CRON = "cron.service"


def cgroup(name: str) -> Path | None:
    if name == CRON:
        return Path("/sys/fs/cgroup/system.slice/cron.service")
    cid = subprocess.run(
        ["docker", "inspect", "-f", "{{.Id}}", name], capture_output=True, text=True
    ).stdout.strip()
    return Path(f"/sys/fs/cgroup/system.slice/docker-{cid}.scope") if cid else None


def pressure_totals(path: Path) -> list[str]:
    return [line.split("total=")[1] for line in path.read_text().splitlines()]


def run(out: Path, seconds: float) -> None:
    paths = {n: cgroup(n) for n in [*QUANT, CRON, *LAB]}
    cols = ["t_mono", "t_wall"]
    for n in [*QUANT, CRON]:
        cols += [f"{n}.cpu_some", f"{n}.cpu_full", f"{n}.io_some", f"{n}.io_full"]
    for n in LAB:
        cols += [f"{n}.usage_us", f"{n}.throttled_us"]
    new = not out.exists()
    with out.open("a") as fh:
        if new:
            fh.write(",".join(cols) + "\n")
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            row = [f"{time.monotonic():.3f}", time.strftime("%H:%M:%S")]
            for n in [*QUANT, CRON]:
                p = paths[n]
                try:
                    assert p is not None
                    cpu = pressure_totals(p / "cpu.pressure")
                    io = pressure_totals(p / "io.pressure")
                    row += [cpu[0], cpu[1], io[0], io[1]]
                except Exception:  # noqa: BLE001 -- a missing cgroup is an empty cell, not a crash
                    row += ["", "", "", ""]
                    paths[n] = cgroup(n)
            for n in LAB:
                p = paths[n]
                try:
                    assert p is not None
                    stat = dict(line.split() for line in (p / "cpu.stat").read_text().splitlines())
                    row += [stat.get("usage_usec", ""), stat.get("throttled_usec", "")]
                except Exception:  # noqa: BLE001 -- recreated container: new cgroup next time
                    row += ["", ""]
                    paths[n] = cgroup(n)
            fh.write(",".join(row) + "\n")
            fh.flush()
            time.sleep(1.0)


def load(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open() as fh:
        reader = csv.reader(fh)
        header = next(reader)
        return header, [r for r in reader if len(r) == len(header)]


def seconds_of(hms: str) -> int:
    h, m, s = (int(x) for x in hms.split(":"))
    return h * 3600 + m * 60 + s


def rate(rows: list[list[str]], col: int, scale: float) -> float | None:
    """Mean rate of a cumulative counter over rows (per wall second), times `scale`."""
    pts = [(float(r[0]), float(r[col])) for r in rows if r[col]]
    if len(pts) < 2:
        return None
    # Counters reset when a container is recreated: sum the positive deltas only.
    total = sum(max(0.0, b[1] - a[1]) for a, b in zip(pts, pts[1:], strict=False))
    span = pts[-1][0] - pts[0][0]
    return total / span * scale if span > 0 else None


def window(rows: list[list[str]], start: int, end: int) -> list[list[str]]:
    return [r for r in rows if start <= seconds_of(r[1]) < end]


def fmt(v: float | None, unit: str = "%") -> str:
    return "   n/a" if v is None else f"{v:6.2f}{unit}"


def around(path: Path, at: str, width: int) -> None:
    header, rows = load(path)
    t = seconds_of(at)
    before, after = window(rows, t - width, t), window(rows, t, t + width)
    print(f"{path.name}: event {at}, {width} s before ({len(before)} samples) / after", end="")
    print(f" ({len(after)} samples)")
    print(f"{'cgroup':28} {'io_full b/a':>17} {'io_some b/a':>17} {'cpu_some b/a':>17}")
    for n in [*QUANT, CRON]:
        if f"{n}.io_full" not in header:
            continue
        cells = []
        for metric in ("io_full", "io_some", "cpu_some"):
            col = header.index(f"{n}.{metric}")
            # pressure totals are microseconds of stall per second of wall time -> % (1e-4).
            cells.append(f"{fmt(rate(before, col, 1e-4))} {fmt(rate(after, col, 1e-4))}")
        print(f"{n:28} {cells[0]:>17} {cells[1]:>17} {cells[2]:>17}")
    print(f"{'lab container':28} {'cores b/a':>17} {'throttled b/a':>17}")
    for n in LAB:
        if f"{n}.usage_us" not in header:
            continue
        use, thr = header.index(f"{n}.usage_us"), header.index(f"{n}.throttled_us")
        cores = f"{fmt(rate(before, use, 1e-6), '')} {fmt(rate(after, use, 1e-6), '')}"
        throttled = f"{fmt(rate(before, thr, 1e-4))} {fmt(rate(after, thr, 1e-4))}"
        print(f"{n:28} {cores:>17} {throttled:>17}")


def peaks(path: Path, start: str, end: str, bin_s: int) -> None:
    header, rows = load(path)
    col = header.index("quant-postgres.io_full")
    sel = window(rows, seconds_of(start), seconds_of(end))
    bins: list[tuple[float, str]] = []
    for i in range(0, max(0, len(sel) - bin_s), bin_s):
        chunk = sel[i : i + bin_s + 1]
        v = rate(chunk, col, 1e-4)
        if v is not None:
            bins.append((v, chunk[0][1]))
    for v, at in sorted(bins, reverse=True)[:10]:
        print(f"{at}  quant-postgres io_full {v:6.2f}% ({bin_s} s bin)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("out", type=Path)
    r.add_argument("seconds", type=float)
    a = sub.add_parser("around")
    a.add_argument("csv", type=Path)
    a.add_argument("at")
    a.add_argument("--window", type=int, default=300)
    p = sub.add_parser("peaks")
    p.add_argument("csv", type=Path)
    p.add_argument("start")
    p.add_argument("end")
    p.add_argument("--bin", type=int, default=10)
    args = ap.parse_args()
    if args.cmd == "run":
        if not str(args.out).startswith("/dev/shm/"):
            sys.exit("keep the CSV on /dev/shm (CLAUDE.md rule 7)")
        run(args.out, args.seconds)
    elif args.cmd == "around":
        around(args.csv, args.at, args.window)
    else:
        peaks(args.csv, args.start, args.end, args.bin)


if __name__ == "__main__":
    main()
