"""scripts/rule_run.py walk@3 (docs/demonstrations.md 3.5): the two-motion hover, the systematic
stop, and the hover constants mirrored in the L2 binding (drift)."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from poring_skills.resolve import load_l2

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture(scope="module")
def rr() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("rule_run", SCRIPTS / "rule_run.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["rule_run"] = module
    spec.loader.exec_module(module)
    return module


class FakeAgent:
    def __init__(self) -> None:
        self.moves: list[tuple[int, int]] = []

    def move(self, x: int, y: int) -> None:
        self.moves.append((x, y))


class FakeScreen:
    def __init__(self) -> None:
        self.grabs: list[tuple[int, int, int, int]] = []

    def grab(self, x: int, y: int, w: int, h: int) -> tuple[int, np.ndarray]:
        self.grabs.append((x, y, w, h))
        return 0, np.zeros((h, w, 4), np.uint8)


def test_the_hover_is_two_motion_events_ending_on_the_cell(
    rr: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One jump drew the marker 0/18 times, a second move 18/18 (probe 2026-10-07)."""
    monkeypatch.setattr(rr.time, "sleep", lambda s: None)
    agent, screen = FakeAgent(), FakeScreen()
    assert rr.hover_marker(agent, screen, 500, 400) == 0
    assert agent.moves == [(497, 397), (500, 400)]
    assert len(screen.grabs) == 1 and screen.grabs[0][:2] == (500 - 45, 400 - 45)


def test_systematic_decline_needs_k_identical_declines_in_a_row(rr: ModuleType) -> None:
    k = rr.SYSTEMATIC_K
    assert rr.systematic_decline(["no_marker"] * (k - 1)) is None
    assert rr.systematic_decline(["no_marker"] * k) == "no_marker"
    assert rr.systematic_decline([None] * k) is None
    assert rr.systematic_decline(["no_marker"] * (k - 1) + [None]) is None
    assert rr.systematic_decline(["no_selfpos"] + ["no_marker"] * (k - 1)) is None
    assert rr.systematic_decline([None] + ["no_marker"] * k) == "no_marker"


def test_the_hover_constants_match_the_l2_binding(rr: ModuleType) -> None:
    import empty_cell as ec

    cue = load_l2("kro-20211103-prere")["cue"]["walk_marker"]
    hover = cue["hover"]
    assert hover["approach_px"] == rr.HOVER_APPROACH_PX
    assert hover["approach_s"] == rr.HOVER_APPROACH_S
    assert hover["settle_s"] == rr.HOVER_S
    assert cue["rdp"]["min_marker_px"] == ec.MIN_MARKER_PX_V2
    assert cue["rdp"]["crop_px"] == ec.CROP[2] == ec.CROP[3]
    assert "s2" not in cue  # not calibrated on the console path: resolution fails closed
