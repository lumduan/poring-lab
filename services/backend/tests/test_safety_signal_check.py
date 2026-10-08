"""scripts/safety_signal_check.py: the positive case needs BOTH our request and the server's act
from us, inside the window after the click (Batt, 2026-10-08: prove a signal can fire)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture(scope="module")
def ssc() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "safety_signal_check", SCRIPTS / "safety_signal_check.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_positive_case_needs_the_request_and_the_act_in_the_window(ssc: ModuleType) -> None:
    gm, mob, t = 2000002, 110023393, 10_000_000_000
    req = {"type": "attack_request", "target_gid": mob, "t_mono_ns": t + 100_000_000}
    act = {
        "type": "act",
        "kind": "normal",
        "src_gid": gm,
        "target_gid": mob,
        "t_mono_ns": t + 900_000_000,
    }
    late = {**act, "t_mono_ns": t + 9_000_000_000}
    theirs = {**act, "src_gid": mob, "target_gid": gm}
    assert ssc.judge_attack([req, act], t)["pass"] is True
    assert ssc.judge_attack([act], t)["pass"] is False  # the blind sensor: acts but no request
    assert ssc.judge_attack([req, late], t)["pass"] is False  # outside the 5 s window
    assert ssc.judge_attack([req, theirs], t)["pass"] is False  # the monster hit US
