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
