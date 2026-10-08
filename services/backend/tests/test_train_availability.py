"""scripts/train_availability.py: training availability = compute-equivalent / wall seconds,
from the guard's DUTY / R3 lines (docs/planning/training-cost.md)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture(scope="module")
def ta() -> ModuleType:
    path = SCRIPTS / "train_availability.py"
    spec = importlib.util.spec_from_file_location("train_availability", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["train_availability"] = mod
    spec.loader.exec_module(mod)
    return mod


LOG = [
    "[23:00:00] DUTY start level 4 (2000 ms)",
    "[23:30:00] DUTY level 4 -> 0 (100 ms step sleep); fleet 10.0 detections/s",
    "[00:00:00] R3 pause poring-lab-vision-rundev-1",
    "[00:30:00] R3 unpause poring-lab-vision-rundev-1",
    "[01:00:00] ABORT rundev:vision: R3-HARD drops: camera x dropping frames for 31 s",
]


def test_running_paused_and_compute_cross_midnight(ta: ModuleType) -> None:
    segs, pauses = ta.parse([LOG], datetime(2026, 10, 7))
    assert [(lv, a.isoformat(), b.isoformat()) for lv, a, b in segs] == [
        (4, "2026-10-07T23:00:00", "2026-10-07T23:30:00"),
        (0, "2026-10-07T23:30:00", "2026-10-08T01:00:00"),
    ]
    r = ta.window(segs, pauses, 0.3, datetime(2026, 10, 7, 23), datetime(2026, 10, 8, 2))
    assert r["wall"] == 3 * 3600 and r["running"] == 2 * 3600 and r["paused"] == 1800
    # level 4: 1800 s x 0.3/2.3; level 0: (5400 - 1800) s x 0.3/0.4; the hour after the abort: 0
    assert r["compute"] == pytest.approx(1800 * 0.3 / 2.3 + 3600 * 0.75)


def test_a_window_clips_and_stopped_time_counts_zero(ta: ModuleType) -> None:
    segs, pauses = ta.parse([LOG], datetime(2026, 10, 7))
    r = ta.window(segs, pauses, 0.3, datetime(2026, 10, 8, 1), datetime(2026, 10, 8, 3))
    assert r["running"] == 0 and r["compute"] == 0


def test_the_cli_reports_effective_after_a_discarded_epoch(
    ta: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = tmp_path / "out"
    f.write_text("\n".join(LOG) + "\n")
    ta.main([str(f), "--c", "0.3", "--day", "2026-10-07",
             "--window", "n=2026-10-07T23:30..2026-10-08T00:00",
             "--lost", "2026-10-07T23:30..2026-10-07T23:45"])  # fmt: skip
    row = capsys.readouterr().out.splitlines()[1].split()
    assert row[0] == "n" and float(row[4]) == pytest.approx(0.75)
    assert float(row[5]) == pytest.approx(0.38, abs=0.01)  # half the window was discarded
