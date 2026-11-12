#!/usr/bin/env python3
"""Start ONE command only in a MEASURED quiet IO window (Batt 2026-10-09, option D for v1 tonight:
"resume v1 only in a measured quiet window (no quant burst in the last 10 min), one attempt, no
auto-retry after an IO trip").

Why: on 2026-10-09 the vision container's cold start put quant-postgres / quant-ticker / the capture
cron at ~100 % full IO stall within seconds (16:46:23), and quant has bursts of its own over 25 %
(16:11-16:35 baseline, nothing of ours starting). So a start waits until the capture cgroups have
been quiet for --quiet-min minutes, measured each second exactly as scripts/io_baseline.py does
(the kernel's io.pressure "full" total, differenced per interval).

    quiet_start.py [--quiet-min 10] [--limit 25] [--max-wait-h 8] -- COMMAND ...

"Quiet": no second in the last --quiet-min minutes with any capture cgroup's full stall above
--limit % (the guard's spike threshold). It never starts inside the market-open windows
(09:30-10:15, 14:00-14:45 ICT, Monday to Friday: not on Saturday or Sunday, Batt 2026-10-09). It
runs COMMAND once, returns its exit code, logs every decision.

On a DEDICATED host profile (dedicated-intel / dedicated-nvidia; ADR-0022) there is no capture
stack to protect and no market wait (Batt 2026-11-10, bot-server: "we no longer wait for anything
of the quant work"; second-install-gaps.md row E): it logs that and runs COMMAND at once.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections import deque
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import host_profile as hp  # noqa: E402
import io_baseline as iob  # noqa: E402

ICT = timezone(timedelta(hours=7))
MARKET = ((930, 1015), (1400, 1445))  # ICT hhmm, [start, end)
WATCHED = [*iob.CAPTURE, iob.CRON[0]]


def in_market(now: datetime) -> bool:
    """Inside a market-open window, Monday to Friday ICT (the Thai market is shut at weekends)."""
    t = now.astimezone(ICT)
    hhmm = t.hour * 100 + t.minute
    return t.weekday() < 5 and any(a <= hhmm < b for a, b in MARKET)


def waits_apply(profile: hp.HostProfile) -> bool:
    """PURE: the quiet and market-open windows guard a SHARED host's capture stack only."""
    return bool(profile.shared)


def quiet(window: deque[tuple[float, float]], now: float, need_s: float, limit: float) -> bool:
    """PURE: the window covers at least need_s seconds back from now, and no sample in it is above
    limit. window holds (t_mono, the max full % over the watched cgroups in that second)."""
    if not window or now - window[0][0] < need_s:
        return False
    return all(v <= limit for t, v in window if now - t <= need_s)


def log(msg: str, fh: object) -> None:
    now = datetime.now(UTC)
    line = f"{now.astimezone(ICT):%F %T} ICT / {now:%T} UTC {msg}"
    print(line, flush=True)
    print(line, file=fh, flush=True)  # type: ignore[call-overload]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("--quiet-min", type=float, default=10.0)
    ap.add_argument("--limit", type=float, default=25.0)
    ap.add_argument("--max-wait-h", type=float, default=8.0)
    ap.add_argument("--log", type=Path, default=Path("/dev/shm/poring-lab-tmp/quiet_start.log"))
    ap.add_argument("command", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    cmd = a.command[1:] if a.command[:1] == ["--"] else a.command
    if not cmd:
        ap.error("no command")
    need = a.quiet_min * 60
    window: deque[tuple[float, float]] = deque()
    prev: dict[str, tuple[float, int]] = {}
    paths: dict[str, Path] = {}
    last_resolve = -1e9
    deadline = time.monotonic() + a.max_wait_h * 3600
    worst: tuple[float, str] = (0.0, "")
    watched = list(WATCHED)
    with a.log.open("a") as fh:
        prof = hp.current()
        if not waits_apply(prof):
            log(f"host profile {prof.name}: dedicated, no capture stack and no market wait (Batt "
                f"2026-11-10): starting ONCE now: {cmd}", fh)  # fmt: skip
            rc = subprocess.run(cmd, check=False).returncode
            log(f"command exited rc={rc}", fh)
            return rc
        if iob.frigate_io_ignored(cmd, time.time()):  # Batt 2026-11-07: that day only
            watched = [w for w in watched if w != "frigate"]
            log("frigate's IO stall is NOT watched for this worker:vision start (Batt 2026-11-07, "
                "io_baseline.FRIGATE_IO_IGNORED)", fh)  # fmt: skip
        log(f"waiting for {a.quiet_min:g} quiet min (no capture cgroup > {a.limit:g} %): {cmd}", fh)
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now - last_resolve > 60:
                paths = {k: v for k, v in iob.resolve().items() if k in watched}
                last_resolve = now
            peak, who = 0.0, ""
            for name, path in paths.items():
                got = iob.read(path)
                if got is None:
                    continue
                total = got[2]
                if name in prev:
                    t0, tot0 = prev[name]
                    pct = 100.0 * (total - tot0) / 1e6 / max(1e-6, now - t0)
                    if pct > peak:
                        peak, who = pct, name
                prev[name] = (now, total)
            window.append((now, peak))
            while window and now - window[0][0] > need + 5:
                window.popleft()
            if peak > a.limit:
                worst = max(worst, (peak, who))
                log(f"burst: {who} {peak:.1f} % -- the {a.quiet_min:g}-min clock restarts", fh)
            if quiet(window, now, need, a.limit):
                if in_market(datetime.now(UTC)):
                    time.sleep(1.0)
                    continue
                log(f"QUIET for {a.quiet_min:g} min: starting ONCE", fh)
                rc = subprocess.run(cmd, check=False).returncode
                log(f"command exited rc={rc}", fh)
                return rc
            time.sleep(1.0)
        log(f"no quiet window within {a.max_wait_h:g} h (worst burst {worst}): NOT started", fh)
    return 4


if __name__ == "__main__":
    sys.exit(main())
