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
