"""Summarise the IO-pressure baseline (scripts/io_baseline.py). Read-only, stdlib only.

Feeds the disk-split window and a possible Postgres checkpoint tuning on the quant side. It changes
nothing anywhere.

    python3 scripts/io_summary.py                          # newest data/metrics/io_pressure_*.csv
    python3 scripts/io_summary.py --events events.jsonl    # + docker events for lab overlap
    python3 scripts/io_summary.py --around 2026-09-30T19:05:00+07:00 --minutes 5

Reports, in ICT (UTC+7):
  1. every quant-postgres full-stall window >= --threshold % (consecutive 10 s samples merged), with
     any lab activity overlapping it: lab container events (``--events``: ``docker events --format
     '{{json .}}'`` lines), console input (data/input_log), lab-cgroup IO stall, and ``--marks``;
  2. per-hour mean / max for the last ``--hours``;
  3. the quietest 2-hour windows (lowest mean, non-overlapping).
``--around`` prints the samples from ``--minutes`` before to ``--minutes`` after a moment instead.
"""

import argparse
import csv
import json
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ICT = timezone(timedelta(hours=7))
PG = "quant-postgres.full"
LAB = ("lab-desktop", "lab-backend", "lab-frontend-dev", "lab-frontend", "lab-rathena", "lab-db")


@dataclass
class Sample:
    t: datetime
    pg: float
    lab_full: float  # worst lab-cgroup full stall % in this interval


@dataclass
class Window:
    start: datetime
    end: datetime
    peak: float
    samples: list[Sample] = field(default_factory=list)


def ict(t: datetime) -> str:
    return t.astimezone(ICT).strftime("%m-%d %H:%M:%S")


def load(path: Path) -> list[Sample]:
    out: list[Sample] = []
    with path.open() as fh:
        for row in csv.DictReader(fh):
            if not row.get(PG):
                continue
            lab = [float(row[f"{c}.full"]) for c in LAB if row.get(f"{c}.full")]
            out.append(
                Sample(datetime.fromisoformat(row["utc"]), float(row[PG]), max(lab, default=0.0))
            )
    return out


def windows(samples: list[Sample], threshold: float) -> list[Window]:
    found: list[Window] = []
    for s in samples:
        if s.pg < threshold:
            continue
        last = found[-1] if found else None
        if last is not None and s.t - last.end <= timedelta(seconds=15):
            last.end, last.peak = s.t, max(last.peak, s.pg)
            last.samples.append(s)
        else:
            found.append(Window(s.t - timedelta(seconds=10), s.t, s.pg, [s]))
    return found


def input_seconds(data_dir: Path) -> dict[datetime, int]:
    """Console input events per UTC second (human + bot), from data/input_log."""
    counts: dict[datetime, int] = defaultdict(int)
    for path in sorted((data_dir / "input_log").glob("*.jsonl")):
        with path.open() as fh:
            for line in fh:
                try:
                    t = datetime.fromisoformat(json.loads(line)["t_wall"])
                except (ValueError, KeyError):
                    continue
                counts[t.replace(microsecond=0)] += 1
    return counts


def lab_events(path: Path | None) -> list[tuple[datetime, str]]:
    if path is None:
        return []
    out = []
    for line in path.read_text().splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        attrs = e.get("Actor", {}).get("Attributes", {})
        if attrs.get("com.docker.compose.project") != "poring-lab":
            continue
        t = datetime.fromtimestamp(e["timeNano"] / 1e9, tz=UTC)
        out.append((t, f"{attrs.get('com.docker.compose.service', '?')} {e.get('Action')}"))
    return out


def marks(path: Path | None) -> list[tuple[datetime, datetime, str]]:
    """Lines: <start ISO> <end ISO> <label...> (known lab actions)."""
    if path is None:
        return []
    out = []
    for line in path.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            start, end, label = line.split(maxsplit=2)
            out.append((datetime.fromisoformat(start), datetime.fromisoformat(end), label))
    return out


def overlap(
    w: Window,
    events: list[tuple[datetime, str]],
    known: list[tuple[datetime, datetime, str]],
    inputs: dict[datetime, int],
) -> str:
    lo, hi = w.start - timedelta(seconds=30), w.end + timedelta(seconds=30)
    found = [f"{label} ({ict(t)})" for t, label in events if lo <= t <= hi]
    found += [label for a, b, label in known if a <= hi and b >= lo]
    active = sorted(t for t in inputs if lo <= t <= hi)
    if active:
        n = sum(inputs[t] for t in active)
        found.append(f"console input ({n} events, {ict(active[0])}..{ict(active[-1])})")
    lab = max(s.lab_full for s in w.samples)
    if lab >= 1.0:
        found.append(f"lab cgroup IO stall {lab:.1f}%")
    return "; ".join(found) if found else "none"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("csv", nargs="?", type=Path)
    ap.add_argument("--threshold", type=float, default=20.0)
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--events", type=Path)
    ap.add_argument("--marks", type=Path)
    ap.add_argument("--around")
    ap.add_argument("--minutes", type=float, default=5.0)
    args = ap.parse_args()

    path = args.csv or max((REPO / "data" / "metrics").glob("io_pressure_*.csv"), default=None)
    if path is None:
        print("no data/metrics/io_pressure_*.csv", file=sys.stderr)
        return 1
    samples = load(path)
    if not samples:
        print(f"{path}: no quant-postgres samples", file=sys.stderr)
        return 1
    print(f"{path.name}: {len(samples)} samples, {ict(samples[0].t)} .. {ict(samples[-1].t)} ICT")

    if args.around:
        at = datetime.fromisoformat(args.around)
        span = timedelta(minutes=args.minutes)
        for label, lo, hi in (("before", at - span, at), ("after", at, at + span)):
            part = [s for s in samples if lo <= s.t < hi]
            values = [s.pg for s in part]
            print(f"\n{label} {ict(lo)} .. {ict(hi)}: n={len(values)}", end="")
            if values:
                print(f" mean={statistics.fmean(values):.2f}% max={max(values):.2f}%")
                print("  " + " ".join(f"{v:.1f}" for v in values))
            else:
                print()
        return 0

    events = lab_events(args.events)
    known = marks(args.marks)
    inputs = input_seconds(REPO / "data")

    found = windows(samples, args.threshold)
    print(f"\n1. quant-postgres full stall >= {args.threshold:g}% ({len(found)} windows)")
    for w in found:
        print(
            f"  {ict(w.start)} .. {ict(w.end)}  peak {w.peak:5.1f}%  "
            f"lab overlap: {overlap(w, events, known, inputs)}"
        )

    horizon = samples[-1].t - timedelta(hours=args.hours)
    by_hour: dict[str, list[float]] = defaultdict(list)
    for s in samples:
        if s.t >= horizon:
            by_hour[s.t.astimezone(ICT).strftime("%m-%d %H:00")].append(s.pg)
    print(f"\n2. per-hour quant-postgres full stall, last {args.hours:g} h (ICT)")
    for hour, values in by_hour.items():
        mean, peak = statistics.fmean(values), max(values)
        print(f"  {hour}  mean {mean:5.2f}%  max {peak:5.1f}%  n={len(values)}")

    width = 720  # 2 h of 10 s samples
    ranked = []
    for i in range(0, max(0, len(samples) - width), 30):  # every 5 min
        chunk = samples[i : i + width]
        ranked.append((statistics.fmean(s.pg for s in chunk), max(s.pg for s in chunk), chunk))
    ranked.sort(key=lambda r: r[0])
    chosen: list[tuple[float, float, list[Sample]]] = []
    for mean, peak, chunk in ranked:
        if all(chunk[-1].t < c[0].t or chunk[0].t > c[-1].t for _, _, c in chosen):
            chosen.append((mean, peak, chunk))
        if len(chosen) == 3:
            break
    print("\n3. quietest 2-hour windows (lowest mean quant-postgres full stall)")
    for mean, peak, chunk in chosen:
        print(f"  {ict(chunk[0].t)} .. {ict(chunk[-1].t)}  mean {mean:.2f}%  max {peak:.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
