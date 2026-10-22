"""demo_aftercare.py (Batt 2026-10-22, decision 8): every human demo ends with its character warped
to its safe stand and healed, then judged. The stands, the character rule, and that the recorder
itself stays input-free (the aftercare is a separate step)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import demo_aftercare as da  # noqa: E402


def test_each_character_has_a_safe_stand_and_old_sessions_are_the_gms() -> None:
    assert da.character_of({"character": "crusader"}) == "crusader"
    assert da.character_of({}) == "gm"
    assert da.STANDS["crusader"] == ("prt_fild08", 268, 107)
    with pytest.raises(ValueError):
        da.character_of({"character": "someone"})


def test_the_crusaders_lines_go_through_its_guarded_path() -> None:
    src = (ROOT / "scripts" / "demo_aftercare.py").read_text()
    assert 'cr.gm_line(agent, screen, cmd, "crusader")' in src
    assert "@heal" in src and "@warp" in src


def test_the_recorder_still_sends_no_input() -> None:
    src = (ROOT / "scripts" / "human_demo.py").read_text()
    for pat in ("Agent(", "session(", ".click(", ".chord(", ".keys(", "gm_line(", ".gm("):
        assert pat not in src, pat
