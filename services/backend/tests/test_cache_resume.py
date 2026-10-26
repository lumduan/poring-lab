"""scripts/runbooks/cache-resume.sh (Batt 2026-10-26 ~20:5x, option (a)): an IO-guard abort waits
for the measured quiet gate and resumes with the same arguments, up to MAX_RESUMES; anything else
stops at once. Run for real against a stub guard and a stub quiet gate."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "runbooks" / "cache-resume.sh"

GUARD = """#!/usr/bin/env bash
n=$(cat "$STATE/calls" 2>/dev/null || echo 0); n=$((n + 1)); echo $n > "$STATE/calls"
echo "args: $*" >> "$STATE/args"
what=$(echo "$OUTCOMES" | cut -d, -f$n); what=${what:-ok}
case "$what" in
  io) echo "[20:47:02] ABORT cache: quant-postgres full IO stall 26.9% (spike above 25.0%)"
      echo "[20:47:02] STOP VERIFIED cache after 1s: container gone"; exit 1 ;;
  unverified) echo "[20:47:02] ABORT cache: quant-postgres full IO stall 26.9% (spike)"; exit 1 ;;
  fail) echo "cache: FAILED rc=1"; exit 1 ;;
  *) echo "cache: done"; exit 0 ;;
esac
"""


def run(tmp_path: Path, outcomes: str, max_resumes: str = "12") -> tuple[int, str, list[str]]:
    state = tmp_path / "state"
    state.mkdir()
    (tmp_path / "guard.sh").write_text(GUARD)
    (tmp_path / "args.txt").write_text("--labels map --cache-id x")
    log = tmp_path / "log"
    env = {**os.environ, "GUARD": f"bash {tmp_path / 'guard.sh'}", "QUIET": "true",
           "STATE": str(state), "OUTCOMES": outcomes, "MAX_RESUMES": max_resumes,
           "TMPDIR": str(tmp_path)}  # fmt: skip
    p = subprocess.run(["bash", str(SCRIPT), str(tmp_path / "args.txt"), "14400", str(log)],
                       env=env, check=False, capture_output=True, timeout=60)  # fmt: skip
    return p.returncode, log.read_text(), (state / "args").read_text().splitlines()


def test_io_aborts_resume_with_the_same_arguments_until_done(tmp_path: Path) -> None:
    rc, log, args = run(tmp_path, "io,io,ok")
    assert rc == 0 and "CACHE DONE" in log and log.count("waiting for 10 measured quiet") == 2
    assert len(args) == 3 and len(set(args)) == 1  # the same arguments every time
    assert args[0].endswith("cache@14400=--labels map --cache-id x --resume")


def test_the_cap_pauses_and_other_failures_stop(tmp_path: Path) -> None:
    for d in ("cap", "fail", "unverified"):
        (tmp_path / d).mkdir()
    rc, log, args = run(tmp_path / "cap", "io,io,io", max_resumes="2")
    assert rc == 3 and "CACHE PAUSED: 2 resumes used" in log and len(args) == 3
    rc, log, _ = run(tmp_path / "fail", "fail,ok")
    assert rc == 2 and "not an IO-guard abort" in log
    rc, log, _ = run(tmp_path / "unverified", "unverified,ok")
    assert rc == 2 and "not verified" in log
