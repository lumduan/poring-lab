"""scripts/weight_digits.py: each step's readouts are the frame just before it and the last frame
before the next step (loot@1 P1, Batt 2026-10-08)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def test_the_readout_frame_is_the_newest_strictly_before_the_step(tmp_path: Path) -> None:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("weight_digits", SCRIPTS / "weight_digits.py")
    assert spec and spec.loader
    wd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wd)
    for k, t in enumerate((100, 200, 300)):
        (tmp_path / f"{k:05d}-{t}.jpg").write_bytes(b"")
    assert wd.frame_before(tmp_path, 250) == str(tmp_path / "00001-200.jpg")
    assert wd.frame_before(tmp_path, 300) == str(tmp_path / "00001-200.jpg")  # strictly before
    assert wd.frame_before(tmp_path, 100) is None
    assert sum(n for _, n in wd.PHASES["calib"]) == 10  # +10.0 shown: every digit 0-9 passes
