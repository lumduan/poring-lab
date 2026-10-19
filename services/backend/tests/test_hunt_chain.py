"""scripts/hunt_chain.py (Batt 2026-10-18 night): queues the remaining pre-registered runs of ONE
version; it sends no input, stops on a lease / a non-ASSIST mode / any run not ending on its time
box / the control file, and runs every run niced with the live hard-bar monitor beside it."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import hunt_chain as hc  # noqa: E402


def test_health_gate_stops_on_a_lease_or_another_mode() -> None:
    assert hc.health_ok({"mode": "ASSIST", "lease_active": False}) is None
    assert hc.health_ok({"mode": "HUMAN", "lease_active": False}) == "mode HUMAN"
    assert hc.health_ok({"mode": "BOT", "lease_active": False}) == "mode BOT"
    assert hc.health_ok({"mode": "ASSIST", "lease_active": True}) == "a human lease is active"


def test_control_file_is_a_content_marker(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    ctl = tmp_path / "chain.ctl"
    monkeypatch.setattr(hc, "CTL", ctl)
    assert hc.control() == "run"  # absent: run
    ctl.write_text("stop\n")
    assert hc.control() == "stop"
    ctl.write_text("run\n")
    assert hc.control() == "run"


def test_the_chain_sends_no_input_and_stops_on_any_non_time_box_end() -> None:
    src = Path(hc.__file__).read_text()
    for bad in (".click(", ".move(", ".key(", "send_input", "AgentInput", "Agent("):
        assert bad not in src, bad
    assert '"nice", "-n", "10"' in src and '"hardbar_live.py"' not in src
    assert '"scripts/hardbar_live.py",\n                     "watch"' in src
    assert "if rc != 0:" in src and "return 3" in src
    assert "while runner_running():" in src  # never two runners
    # the monitor is bound to THIS run's process (Batt 2026-10-19), never "any runner of V"
    assert '"watch", str(a.version), "--pid", str(run.pid)]' in src


def test_hardbar_monitor_binds_to_one_runner_and_never_re_binds() -> None:
    """The night's stale monitor (2026-10-19): a watch for "any runner of version V" latched onto
    each next chained run. pick_runner resolves ONE runner from the pid it was given (the python
    itself, or the nice -> uv run wrapper the chain holds) and finds nothing once it is gone,
    even while the next runner of the same version runs."""
    import hardbar_live as hb

    ps = ["100 1 nice -n 10 uv run python scripts/hunt_flow.py run --version 41 --minutes 60.0",
          "101 100 uv run python scripts/hunt_flow.py run --version 41 --minutes 60.0 --seed 1",
          "102 101 /x/.venv/bin/python3 scripts/hunt_flow.py run --version 41 --minutes 60.0",
          "200 1 /x/.venv/bin/python3 scripts/hunt_flow.py run --version 40 --minutes 60.0",
          "300 1 /x/.venv/bin/python3 scripts/hardbar_live.py watch 41 --pid 100"]  # fmt: skip
    assert hb.pick_runner(ps, 102, 41) == 102  # the python itself
    assert hb.pick_runner(ps, 100, 41) == 102  # nice -> uv run -> python
    assert hb.pick_runner(ps, 101, 41) == 102
    assert hb.pick_runner(ps, 200, 41) is None  # another version
    assert hb.pick_runner(ps, 300, 41) is None  # not a runner
    assert hb.pick_runner(ps, 999, 41) is None  # gone
    # the bound runner ended, the NEXT chained runner of the same version runs: no re-bind
    nxt = [
        "400 1 nice -n 10 uv run python scripts/hunt_flow.py run --version 41 --minutes 60.0",
        "402 400 /x/.venv/bin/python3 scripts/hunt_flow.py run --version 41 --minutes 60.0",
    ]
    assert hb.pick_runner(nxt, 102, 41) is None
    src = Path(hb.__file__).read_text()
    assert "def runner_pid(" not in src  # the version-wide lookup is gone
    w = src[src.index("def watch(") :]
    assert "if pick_runner(_ps(), pid, version) != pid:" in w and "os.kill(pid, signal.SIGINT)" in w
