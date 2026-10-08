#!/usr/bin/env python3
"""Training AVAILABILITY per wall-clock window, from guarded_build's rundev outputs (read-only).

    train_availability.py --c 0.293 --day 2026-10-07 OUT [OUT ...] \
        --window night=2026-10-07T20:00..2026-10-08T05:00 \
        [--lost 2026-10-08T09:11:52..2026-10-08T09:32:53]

docs/planning/training-cost.md: wall-clock = compute / availability.
- compute-equivalent seconds: the time a step RAN and was not R3-paused at duty level l, times
  c / (c + sleep_l). c is the pure compute per batch (sleep and pauses excluded).
- availability = compute-equivalent seconds / wall seconds. Stopped time (aborts, quiet waits, IO
  pauses, timeouts) counts 0.
- effective: also minus the partial epochs a stop discarded (``--lost``: epoch end -> the stop).
The OUT files are read in the order given. Their [HH:MM:SS] stamps are ICT; the first file starts
on ``--day``, and a stamp more than an hour earlier than the previous one has crossed midnight.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path

SLEEP_S = {0: 0.1, 1: 0.2, 2: 0.4, 3: 0.8, 4: 2.0}  # the duty levels (docs/operations/r3-paired.md)
STAMP = re.compile(r"\[(\d\d:\d\d:\d\d)\]")
Seg = tuple[int, datetime, datetime]
Span = tuple[datetime, datetime]


def parse(lines_per_file: Iterable[list[str]], day: datetime) -> tuple[list[Seg], list[Span]]:
    """(level, start, end) running segments and (start, end) R3 pause windows."""
    segs: list[Seg] = []
    pauses: list[Span] = []
    last: datetime | None = None
    for lines in lines_per_file:
        cur: int | None = None
        t_cur = end = None
        p0: datetime | None = None
        for line in lines:
            m = STAMP.match(line)
            if not m:
                continue
            t = day + (datetime.strptime(m.group(1), "%H:%M:%S") - datetime(1900, 1, 1))
            if last is not None and t < last - timedelta(hours=1):
                day += timedelta(days=1)
                t += timedelta(days=1)
            last = end = t
            if a := re.search(r"DUTY start level (\d)", line):
                cur, t_cur = int(a.group(1)), t
            elif (b := re.search(r"DUTY level (\d) -> (\d)", line)) and cur is not None:
                assert t_cur is not None
                segs.append((cur, t_cur, t))
                cur, t_cur = int(b.group(2)), t
            elif "R3 pause " in line:
                p0 = t
            elif "R3 unpause " in line and p0 is not None:
                pauses.append((p0, t))
                p0 = None
            elif "ABORT" in line and cur is not None:
                assert t_cur is not None
                segs.append((cur, t_cur, t))
                cur = None
        if cur is not None and t_cur is not None and end is not None:
            segs.append((cur, t_cur, end))
        if p0 is not None and end is not None:
            pauses.append((p0, end))
    return segs, pauses


def _ov(a: datetime, b: datetime, c: datetime, d: datetime) -> float:
    return max(0.0, (min(b, d) - max(a, c)).total_seconds())


def window(
    segs: list[Seg], pauses: list[Span], c: float, a: datetime, b: datetime
) -> dict[str, float]:
    """Wall, running, paused and compute-equivalent seconds in [a, b)."""
    comp = run = paused = 0.0
    for lv, x, y in segs:
        r = _ov(x, y, a, b)
        p = sum(_ov(max(x, pa), min(y, pb), a, b) for pa, pb in pauses if pb > x and pa < y)
        run += r
        paused += p
        comp += (r - p) * c / (c + SLEEP_S[lv])
    return {"wall": (b - a).total_seconds(), "running": run, "paused": paused, "compute": comp}


def _span(s: str) -> Span:
    lo, hi = s.split("..")
    return datetime.fromisoformat(lo), datetime.fromisoformat(hi)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("outs", nargs="+", help="guarded_build rundev outputs, in time order")
    ap.add_argument("--c", type=float, required=True, help="pure compute seconds per batch")
    ap.add_argument("--day", required=True, help="the first file's date, YYYY-MM-DD (ICT)")
    ap.add_argument("--window", action="append", default=[], help="NAME=START..END (ISO, ICT)")
    ap.add_argument("--lost", action="append", default=[], help="START..END: a discarded epoch")
    a = ap.parse_args(argv)
    texts = [Path(f).read_text(errors="replace").replace("\r", "\n").splitlines() for f in a.outs]
    segs, pauses = parse(texts, datetime.fromisoformat(a.day))
    lost = [_span(s) for s in a.lost]
    head = ("window", "wall h", "running", "paused", "avail", "effective")
    print(f"{head[0]:<12} {head[1]:>7} {head[2]:>8} {head[3]:>7} {head[4]:>6} {head[5]:>9}")
    for w in a.window:
        name, span = w.split("=", 1)
        lo, hi = _span(span)
        r = window(segs, pauses, a.c, lo, hi)
        gone = sum(window(segs, pauses, a.c, max(x, lo), min(y, hi))["compute"]
                   for x, y in lost if y > lo and x < hi)  # fmt: skip
        wall = r["wall"]
        run, pau, comp = r["running"] / wall, r["paused"] / wall, r["compute"] / wall
        eff = (r["compute"] - gone) / wall
        print(f"{name:<12} {wall / 3600:>7.2f} {run:>8.1%} {pau:>7.1%} {comp:>6.2f} {eff:>9.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
