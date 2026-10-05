"""scripts/record_session.py ends a recording CLEANLY on SIGINT/SIGTERM (2026-10-05: the M4 re-run
stops it when its spawns are done): the signal only sets a flag, the loop ends as on its duration,
and the shards + manifest are finalised -- an uncaught KeyboardInterrupt skipped that."""

import importlib.util
import signal
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def test_a_signal_only_sets_the_stop_flag() -> None:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("record_session", SCRIPTS / "record_session.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.STOP == {"flag": False}
    mod.request_stop(signal.SIGINT, None)
    assert mod.STOP["flag"] is True
    src = (SCRIPTS / "record_session.py").read_text()
    assert src.count('while time.monotonic() < t_end and not STOP["flag"]:') == 2  # png and h264
    assert src.count('stop_reason = "stopped by signal"') == 2
