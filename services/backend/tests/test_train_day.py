"""scripts/runbooks/train-day.sh under the ADAPTIVE DUTY CYCLE (Batt, 2026-10-07 ~16:25), run for
real against stub guard / quiet-gate commands: training never stops for load; a frame-drop abort
stays immediate, then resumes at the slowest level after the quiet gate; the 3rd abort within 2 h
caps the speed for an hour and NOTIFIES (no stop); a latency trip raises the duty floor."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "runbooks" / "train-day.sh"

GUARD = """#!/usr/bin/env bash
# stub guarded_build: scripted outcomes per call (OUTCOMES: drop | latency | ok), env recorded
n=$(cat "$STATE/calls" 2>/dev/null || echo 0); n=$((n + 1)); echo $n > "$STATE/calls"
echo "call $n DUTY_START=$DUTY_START DUTY_MIN=$DUTY_MIN DUTY_CAP_LEVEL=$DUTY_CAP_LEVEL" \\
     "DUTY_AFTER_ABORT=$DUTY_AFTER_ABORT args: $*" >> "$STATE/args"
what=$(echo "$OUTCOMES" | cut -d, -f$n); what=${what:-ok}
m1="[12:00:00] ABORT rundev:vision: R3-HARD drops: camera a dropping frames for 31 s"
m2=" (skipped_fps 2.0, camera_fps 5.0); fleet 77.4 detections/s, detectors 39.1 ms"
case "$what" in
  drop) echo "$m1$m2 (no resume)"; echo "DUTY summary: {}"; exit 1 ;;
  latency) echo "[12:00:00] ABORT rundev:vision: R3 latency: paired median delta +6.1 ms"
           exit 1 ;;
  heldthenio) echo "[12:00:00] R3: inconclusive measurement: only 3 kept pairs -> KEEP TRAINING"
              echo "[12:30:00] ABORT rundev:vision: quant-postgres full IO stall 26.1% (spike)"
              exit 1 ;;
  *) echo "DUTY summary: {}"; echo done; exit 0 ;;
esac
"""


def run(tmp_path: Path, outcomes: str, quiet_fails: int = 0) -> tuple[str, list[str]]:
    state = tmp_path / "state"
    state.mkdir()
    guard = tmp_path / "guard.sh"
    guard.write_text(GUARD)
    quiet = tmp_path / "quiet.sh"
    quiet.write_text(
        "#!/usr/bin/env bash\n"
        f"q=$(cat {state}/q 2>/dev/null || echo 0); q=$((q + 1)); echo $q > {state}/q\n"
        f'[ "$q" -gt {quiet_fails} ]\n'
    )
    out = tmp_path / "out"
    env = {**os.environ, "GUARD": f"bash {guard}", "QUIET": f"bash {quiet}", "STATE": str(state),
           "OUTCOMES": outcomes, "IO_PAUSE_S": "0", "R3_PAUSE_S": "0"}  # fmt: skip
    for k in ("DUTY_START", "DUTY_MIN", "DUTY_CAP_LEVEL", "DUTY_CAP_UNTIL", "DUTY_AFTER_ABORT"):
        env.pop(k, None)
    subprocess.run(["bash", str(SCRIPT), "test-run-nonexistent", "cache-x", "1", str(out)],
                   env=env, check=False, capture_output=True, timeout=60)  # fmt: skip
    return (out / "train.log").read_text(), (state / "args").read_text().splitlines()


def test_a_drop_resumes_at_the_slowest_level_after_the_quiet_gate(tmp_path: Path) -> None:
    log, calls = run(tmp_path, "drop,ok")
    assert "TRAIN DONE" in log and "15 quiet minutes: resuming at the slowest level" in log
    assert "--duty-file /lab-duty/duty.json" in calls[0] and "DUTY_START=4" in calls[0]
    assert "DUTY_START=4" in calls[1] and "DUTY_AFTER_ABORT=1" in calls[1]
    assert (tmp_path / "out" / "drop-aborts.log").read_text().count("fleet 77.4") == 1


def test_three_drops_in_two_hours_cap_and_notify_but_never_stop(tmp_path: Path) -> None:
    log, calls = run(tmp_path, "drop,drop,drop,drop,ok")
    assert "TRAIN DONE" in log and "TRAIN STOPPED" not in log
    assert log.count("NOTIFY:") == 2  # at the 3rd and the 4th abort within 2 h
    assert "DUTY_CAP_LEVEL=0" in calls[2] and "DUTY_CAP_LEVEL=3" in calls[3]
    assert len(calls) == 5


def test_a_quiet_gate_that_times_out_is_re_armed_never_a_stop(tmp_path: Path) -> None:
    log, calls = run(tmp_path, "drop,ok", quiet_fails=2)
    assert log.count("re-arming the gate") == 2 and "TRAIN DONE" in log and len(calls) == 2


def test_a_latency_trip_raises_the_duty_floor_and_keeps_running(tmp_path: Path) -> None:
    log, calls = run(tmp_path, "latency,latency,ok")
    assert "the duty floor is now level 1" in log and "the duty floor is now level 2" in log
    assert "DUTY_MIN=0" in calls[0] and "DUTY_MIN=2" in calls[2] and "TRAIN DONE" in log


def test_a_kept_training_line_never_makes_a_later_io_abort_an_r3_trip(tmp_path: Path) -> None:
    """2026-10-08: an inconclusive R3 keeps training (no ABORT); an IO abort later in the SAME
    attempt is an IO trip (the long pause, counted), never an R3 floor raise."""
    log, calls = run(tmp_path, "heldthenio,ok")
    assert "TRAIN DONE" in log and "the duty floor is now level" not in log
    assert "pausing 0 s before the next attempt" in log and "DUTY_MIN=0" in calls[1]
