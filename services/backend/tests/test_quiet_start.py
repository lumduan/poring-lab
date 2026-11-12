"""scripts/runbooks/quiet_start.py (Batt 2026-10-09, option D): a start only after a MEASURED quiet
window -- no capture cgroup above the limit for the whole window, never in a market-open window."""

from __future__ import annotations

import importlib.util
import sys
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest

RUNBOOKS = Path(__file__).resolve().parents[3] / "scripts" / "runbooks"


@pytest.fixture(scope="module")
def qs() -> ModuleType:
    sys.path.insert(0, str(RUNBOOKS.parent))
    spec = importlib.util.spec_from_file_location("quiet_start", RUNBOOKS / "quiet_start.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_quiet_needs_the_whole_window_below_the_limit(qs: ModuleType) -> None:
    w: deque[tuple[float, float]] = deque((float(t), 2.0) for t in range(0, 601))
    assert qs.quiet(w, 600.0, 600.0, 25.0)
    assert not qs.quiet(w, 600.0, 900.0, 25.0)  # not yet 15 min of samples
    w2 = deque(w)
    w2[300] = (300.0, 47.3)  # one burst second inside the window
    assert not qs.quiet(w2, 600.0, 600.0, 25.0)
    assert not qs.quiet(deque(), 0.0, 600.0, 25.0)


def test_never_in_a_market_open_window(qs: ModuleType) -> None:
    ict = lambda h, m: datetime(2026, 10, 9, h - 7, m, tzinfo=UTC)  # noqa: E731
    assert qs.in_market(ict(9, 30)) and qs.in_market(ict(14, 44))
    assert not qs.in_market(ict(10, 15)) and not qs.in_market(ict(14, 45))
    assert not qs.in_market(ict(21, 0))


def test_market_windows_only_on_weekdays(qs: ModuleType) -> None:
    # Batt 2026-10-09: the 09:30-10:15 / 14:00-14:45 windows do not apply on Saturday or Sunday.
    sat = datetime(2026, 10, 10, 9 - 7, 45, tzinfo=UTC)
    sun = datetime(2026, 10, 11, 14 - 7, 10, tzinfo=UTC)
    mon = datetime(2026, 10, 12, 9 - 7, 45, tzinfo=UTC)
    assert not qs.in_market(sat) and not qs.in_market(sun)
    assert qs.in_market(mon)


def test_batts_one_day_frigate_exclusion_is_a_worker_start_on_that_day_only() -> None:
    """Batt 2026-11-07: a worker:vision START leaves Frigate's IO stall out, that day only; the
    quant cgroups and cron's capture always stay watched."""
    import io_baseline as iob

    t0, t1 = iob.FRIGATE_IO_IGNORED
    start = ["python3", "scripts/guarded_build.py", "--sustain", "30", "worker:vision@120"]
    assert iob.frigate_io_ignored(start, t0 + 60) and iob.frigate_io_ignored(start, t1 - 1)
    assert not iob.frigate_io_ignored(start, t1) and not iob.frigate_io_ignored(start, t0 - 1)
    assert not iob.frigate_io_ignored(["execdev:vision@600=python -m x"], t0 + 60)
    assert not iob.frigate_io_ignored(["worker-stop:vision"], t0 + 60)
    root = Path(__file__).resolve().parents[3]
    qs = (root / "scripts/runbooks/quiet_start.py").read_text()
    assert 'watched = [w for w in watched if w != "frigate"]' in qs
    gb = (root / "scripts/guarded_build.py").read_text()
    assert 'if all(s.kind == "worker" for s in steps) and io_baseline.frigate_io_ignored(' in gb
    assert 'paths.pop("frigate", None)' in gb


def test_a_dedicated_host_never_waits(qs: ModuleType) -> None:
    """second-install-gaps.md row E (Batt 2026-11-10: no market waits on bot-server)."""
    import host_profile as hp

    assert qs.waits_apply(hp.PROFILES["shared-nvidia"]) is True
    for name in ("dedicated-intel", "dedicated-nvidia"):
        assert qs.waits_apply(hp.PROFILES[name]) is False
    src = (RUNBOOKS / "quiet_start.py").read_text()
    # the dedicated branch runs the command BEFORE any IO sample or market check
    assert src.index("if not waits_apply(prof):") < src.index("while time.monotonic() < deadline:")
