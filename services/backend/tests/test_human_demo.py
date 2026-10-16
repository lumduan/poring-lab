"""human_demo: the recorder of Batt's played demonstration. It must NEVER send input."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import human_demo as hd  # noqa: E402

SRC = (Path(__file__).resolve().parents[3] / "scripts" / "human_demo.py").read_text()


def test_the_recorder_holds_no_input_path() -> None:
    """No Agent, no ro_agent.session, no click / key / chord / gm call anywhere in the source."""
    code = "\n".join(line for line in SRC.splitlines() if not line.lstrip().startswith("#"))
    for pat in (r"\bAgent\(", r"\bsession\(", r"\.click\(", r"\.chord\(", r"\.drag\(",
                r"\.move\(", r"\.send\(", r"\br\.gm\(", r"type_line"):  # fmt: skip
        assert not re.search(pat, code), pat


def test_a_human_input_counts_only_after_arming() -> None:
    armed, now = 1_000_000_000_000, 1_000_000_000_000 + 30_000_000_000
    assert hd.first_input_after(armed, now, 71_000.0) is None  # last input yesterday
    assert hd.first_input_after(armed, now, 40.0) is None  # 10 s before arming
    t = hd.first_input_after(armed, now, 5.0)
    assert t == now - 5_000_000_000
    assert hd.first_input_after(armed, now, None) is None


def test_quiet_needs_the_age_and_no_lease() -> None:
    assert hd.quiet({"last_human_input_age_s": 61.0, "lease_active": False})
    assert not hd.quiet({"last_human_input_age_s": 59.0, "lease_active": False})
    assert not hd.quiet({"last_human_input_age_s": 120.0, "lease_active": True})
    assert not hd.quiet({"lease_active": False})


def test_only_human_lines_of_the_window_are_kept() -> None:
    def line(src: str, t: int) -> str:
        return json.dumps({"source": src, "t_mono_ns": t, "event": {"type": "mouse_move"}})

    lines = [line("human", 5), line("bot", 15), line("human", 15), line("human", 25), "not json"]
    got = hd.human_lines(lines, 10, 20)
    assert [json.loads(x)["t_mono_ns"] for x in got] == [15]
    assert all(json.loads(x)["source"] == "human" for x in got)
