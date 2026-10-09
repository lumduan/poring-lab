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
k=$(echo "$*" | grep -o '[a-z]*:vision@' | head -1 | cut -d: -f1)  # rundev | execdev (WORKER=1)
m1="[12:00:00] ABORT $k:vision: R3-HARD drops: camera a dropping frames for 31 s"
m2=" (skipped_fps 2.0, camera_fps 5.0); fleet 77.4 detections/s, detectors 39.1 ms"
case "$what" in
  drop) echo "$m1$m2 (no resume)"; echo "DUTY summary: {}"; exit 1 ;;
  latency) echo "[12:00:00] ABORT $k:vision: R3 latency: paired median delta +6.1 ms"
           exit 1 ;;
  io) echo "[12:00:00] ABORT $k:vision: quant-postgres full IO stall 45.8% (spike)"; exit 1 ;;
  r2) echo "[12:00:00] REFUSED $k:vision: R2: Ollama has a model loaded (x)"; exit 3 ;;
  crash) echo "Traceback: something else"; exit 1 ;;
  heldthenio) echo "[12:00:00] R3: inconclusive measurement: only 3 kept pairs -> KEEP TRAINING"
              echo "[12:30:00] ABORT $k:vision: quant-postgres full IO stall 26.1% (spike)"
              exit 1 ;;
  wdown) echo "[12:00:00] REFUSED $k:vision: WORKER down (poring-lab-vision-worker-1 stopped)"
         exit 3 ;;
  wbusy) echo "[12:00:00] REFUSED $k:vision: WORKER not ready (busy: 77 (python))"; exit 3 ;;
  wkill) echo "[12:00:00] ABORT $k:vision: quant-postgres full IO stall 45.8% (spike)"
         echo "[12:01:00] ESCALATED: docker kill poring-lab-vision-worker-1 (x) -- WORKER KILLED"
         echo "[12:01:15] STOP VERIFIED $k:vision after escalation (75s)"; exit 1 ;;
  *) echo "DUTY summary: {}"; echo done; exit 0 ;;
esac
"""


def run(tmp_path: Path, outcomes: str, quiet_fails: int = 0) -> tuple[str, list[str]]:
    log, args, _rc = run_rc(tmp_path, outcomes, quiet_fails)
    return log, args


def run_rc(tmp_path: Path, outcomes: str, quiet_fails: int = 0, clock: str = "1200",
           extra: dict[str, str] | None = None) -> tuple[str, list[str], int]:  # fmt: skip
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
    sleeper = tmp_path / "sleep.sh"
    sleeper.write_text(f'#!/usr/bin/env bash\necho slept "$1" >> {state}/slept\n')
    out = tmp_path / "out"
    env = {**os.environ, "GUARD": f"bash {guard}", "QUIET": f"bash {quiet}", "STATE": str(state),
           "OUTCOMES": outcomes, "IO_PAUSE_S": "0", "R3_PAUSE_S": "0", "CLOCK_HHMM": clock,
           "SLEEP": f"bash {sleeper}"}  # fmt: skip
    for k in (
        "DUTY_START",
        "DUTY_MIN",
        "DUTY_CAP_LEVEL",
        "DUTY_CAP_UNTIL",
        "DUTY_AFTER_ABORT",
        "MAX_ATTEMPTS",
        "WORKER",
    ):
        env.pop(k, None)
    env.update(extra or {})
    p = subprocess.run(["bash", str(SCRIPT), "test-run-nonexistent", "cache-x", "1", str(out)],
                       env=env, check=False, capture_output=True, timeout=60)  # fmt: skip
    return (out / "train.log").read_text(), (state / "args").read_text().splitlines(), p.returncode


def test_the_exit_code_tells_done_from_paused_from_stopped(tmp_path: Path) -> None:
    """2026-10-09: train-day exited 0 on 'TRAIN PAUSED' (epoch 17 of 30), and a chain gating on
    rc 0 evaluated an unfinished checkpoint. 0 done, 2 stopped, 3 paused."""
    for d in ("done", "paused", "stopped"):
        (tmp_path / d).mkdir()
    log, _, rc = run_rc(tmp_path / "done", "ok")
    assert rc == 0 and "TRAIN DONE" in log
    log, _, rc = run_rc(tmp_path / "paused", "io,io,io,io")
    assert rc == 3 and "TRAIN PAUSED" in log and "TRAIN DONE" not in log
    log, _, rc = run_rc(tmp_path / "stopped", "crash")
    assert rc == 2 and "TRAIN STOPPED" in log


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


def test_no_attempt_starts_inside_a_market_open_window(tmp_path: Path) -> None:
    """Batt 2026-10-09: auto-resumes at 14:12 and 14:33 tripped the IO guard; an attempt due
    inside 09:30-10:15 or 14:00-14:45 ICT waits until the window ends (+1 min)."""
    for d in ("in", "edge", "out"):
        (tmp_path / d).mkdir()
    log, _, rc = run_rc(tmp_path / "in", "ok", clock="1410")
    assert rc == 0 and "market-open window: waiting 2160 s before attempt 0" in log
    assert (tmp_path / "in" / "state" / "slept").read_text().split() == ["slept", "2160"]
    log, _, _ = run_rc(tmp_path / "edge", "ok", clock="0930")
    assert "waiting 2760 s" in log
    log, _, _ = run_rc(tmp_path / "out", "ok", clock="1445")
    assert "market-open window" not in log and not (tmp_path / "out" / "state" / "slept").exists()


def test_max_attempts_one_never_retries_after_any_stop(tmp_path: Path) -> None:
    """Option D (Batt 2026-10-09): one container start; an IO trip or an R3 stop ends it, PAUSED."""
    for d in ("io", "drop", "ok"):
        (tmp_path / d).mkdir()
    log, args, rc = run_rc(tmp_path / "io", "io,ok", extra={"MAX_ATTEMPTS": "1"})
    assert rc == 3 and "MAX_ATTEMPTS=1" in log and len(args) == 1
    log, args, rc = run_rc(tmp_path / "drop", "drop,ok", extra={"MAX_ATTEMPTS": "1"})
    assert rc == 3 and len(args) == 1 and "waiting for 15 quiet minutes" not in log
    log, args, rc = run_rc(tmp_path / "ok", "ok", extra={"MAX_ATTEMPTS": "1"})
    assert rc == 0 and "TRAIN DONE" in log


# --- WORKER=1: option A, every attempt an execdev: in the long-lived worker (NOT switched) ---
W1 = {"WORKER": "1"}


def test_worker_1_runs_the_same_training_as_an_execdev_and_the_default_stays_rundev(
    tmp_path: Path,
) -> None:
    for d in ("worker", "default"):
        (tmp_path / d).mkdir()
    _, args, rc = run_rc(tmp_path / "worker", "ok", extra=W1)
    _, plain, _ = run_rc(tmp_path / "default", "ok")
    assert rc == 0 and len(args) == 1 and len(plain) == 1
    assert (
        "args: --sustain 30 --spike 25 execdev:vision@43200=python -m poring_vision.train"
        in (args[0])
    )
    assert "rundev:" not in args[0] and "execdev:" not in plain[0]
    assert args[0].replace("execdev:", "rundev:") == plain[0]  # nothing else differs


def test_worker_1_keeps_the_exit_codes(tmp_path: Path) -> None:
    for d in ("done", "paused", "stopped"):
        (tmp_path / d).mkdir()
    log, _, rc = run_rc(tmp_path / "done", "ok", extra=W1)
    assert rc == 0 and "TRAIN DONE" in log
    log, args, rc = run_rc(tmp_path / "paused", "io,r2,io,io", extra=W1)
    assert rc == 3 and "TRAIN PAUSED: 3 IO/R2 resumes used" in log and len(args) == 4
    log, _, rc = run_rc(tmp_path / "stopped", "crash", extra=W1)
    assert rc == 2 and "TRAIN STOPPED: not a guard trip" in log


def test_worker_1_keeps_max_attempts_and_the_r3_flows(tmp_path: Path) -> None:
    for d in ("max", "latency", "drop"):
        (tmp_path / d).mkdir()
    log, args, rc = run_rc(tmp_path / "max", "io,ok", extra={**W1, "MAX_ATTEMPTS": "1"})
    assert rc == 3 and "MAX_ATTEMPTS=1" in log and len(args) == 1
    log, args, rc = run_rc(tmp_path / "latency", "latency,ok", extra=W1)
    assert rc == 0 and "the duty floor is now level 1" in log and "DUTY_MIN=1" in args[1]
    log, args, rc = run_rc(tmp_path / "drop", "drop,ok", extra=W1)
    assert rc == 0 and "15 quiet minutes: resuming at the slowest level" in log
    assert "DUTY_AFTER_ABORT=1" in args[1]


def test_worker_1_never_retries_into_a_worker_that_is_down_busy_or_killed(tmp_path: Path) -> None:
    """A worker start is a cold start a person times (quiet_start): down or killed -> PAUSED at
    once; not ready (busy, paused, another checkout's) -> STOPPED. No 15-minute retry loop."""
    for d in ("down", "busy", "killed"):
        (tmp_path / d).mkdir()
    log, args, rc = run_rc(tmp_path / "down", "wdown,ok", extra=W1)
    assert rc == 3 and "the vision worker is down" in log and len(args) == 1
    log, args, rc = run_rc(tmp_path / "busy", "wbusy,ok", extra=W1)
    assert rc == 2 and "the vision worker is not ready" in log and len(args) == 1
    log, args, rc = run_rc(tmp_path / "killed", "wkill,ok", extra=W1)
    assert rc == 3 and "docker kill of the vision worker" in log and len(args) == 1
