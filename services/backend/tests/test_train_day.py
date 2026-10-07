"""scripts/runbooks/train-day.sh's frame-drop rule (Batt, 2026-10-07 ~15:40), run for real against
stub guard / quiet-gate commands: the abort stays immediate; a resume only after the quiet gate,
at the same ladder level; the 3rd frame-drop abort within 2 h stops and waits for Batt."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "runbooks" / "train-day.sh"

GUARD = """#!/usr/bin/env bash
# stub guarded_build: the first $DROPS calls end in an R3-HARD frame-drop abort, then success
n=$(cat "$STATE/calls" 2>/dev/null || echo 0); n=$((n + 1)); echo $n > "$STATE/calls"
echo "args: $*" >> "$STATE/args"
if [ "$n" -le "$DROPS" ]; then
  m1="[12:00:00] ABORT rundev:vision: R3-HARD drops: camera a dropping frames for 31 s"
  m2=" (skipped_fps 2.0, camera_fps 5.0); fleet 77.4 detections/s, detectors 39.1 ms,"
  echo "$m1$m2 skipping now: a (no resume)"
  exit 1
fi
echo "done"; exit 0
"""


def run(tmp_path: Path, drops: int, quiet_rc: int) -> tuple[str, str, str]:
    state = tmp_path / "state"
    state.mkdir()
    guard = tmp_path / "guard.sh"
    guard.write_text(GUARD)
    quiet = tmp_path / "quiet.sh"
    quiet.write_text(f"#!/usr/bin/env bash\necho quiet >> {state}/quiet\nexit {quiet_rc}\n")
    out = tmp_path / "out"
    env = {**os.environ, "GUARD": f"bash {guard}", "QUIET": f"bash {quiet}", "STATE": str(state),
           "DROPS": str(drops), "SLEEP_LEVEL": "1"}  # fmt: skip
    subprocess.run(["bash", str(SCRIPT), "test-run-nonexistent", "cache-x", "1", str(out)],
                   env=env, check=False, capture_output=True, timeout=60)  # fmt: skip
    args = (state / "args").read_text()
    return (out / "train.log").read_text(), args, (out / "drop-aborts.log").read_text() if (
        out / "drop-aborts.log").exists() else ""  # fmt: skip


@pytest.mark.parametrize("drops", [1, 2])
def test_drops_resume_after_the_quiet_gate_at_the_same_level(tmp_path: Path, drops: int) -> None:
    log, args, aborts = run(tmp_path, drops, quiet_rc=0)
    assert "TRAIN DONE" in log and log.count("15 quiet minutes: resuming") == drops
    assert args.count("--step-sleep-ms 100") == drops + 1  # never moved up the ladder
    assert len(aborts.splitlines()) == drops and "fleet 77.4 detections/s" in aborts


def test_the_third_drop_abort_within_2_hours_stops_and_waits(tmp_path: Path) -> None:
    log, args, aborts = run(tmp_path, drops=5, quiet_rc=0)
    assert "TRAIN STOPPED: 3 frame-drop aborts within 2 h" in log
    assert len(aborts.splitlines()) == 3 and args.count("args:") == 3
    assert "TRAIN DONE" not in log


def test_no_quiet_window_stops(tmp_path: Path) -> None:
    log, args, _ = run(tmp_path, drops=1, quiet_rc=2)
    assert "TRAIN STOPPED: no 15 quiet minutes within 2 h" in log and args.count("args:") == 1
