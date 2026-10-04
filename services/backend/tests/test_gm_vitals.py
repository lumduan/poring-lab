"""scripts/gm_vitals.py: the GM's HP from the bar, the recovery decision and the click-time motion
check (Phase 3 Part C). Synthetic frames only: client pixels are never committed."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]


def load() -> ModuleType:
    path = ROOT / "scripts" / "gm_vitals.py"
    spec = importlib.util.spec_from_file_location("gm_vitals", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gm_vitals"] = mod
    spec.loader.exec_module(mod)
    return mod


gv = load()
BLUE = (210, 150, 60)  # BGR: the lit HP bar
RED = (60, 60, 210)  # BGR: the bar at low HP
EMPTY = (200, 198, 197)  # BGR: an empty stretch (grey)


def frame_with_bar(lit: float, colour: tuple[int, int, int] = BLUE) -> np.ndarray:
    """A game-region frame whose HP bar lights `lit` of its columns (the client's 0.85 at full)."""
    img = np.zeros((720, 1280, 3), np.uint8)
    x, y, w, h = gv.HP_BAR
    img[y : y + h, x : x + w] = EMPTY
    img[y : y + h, x : x + int(round(w * lit))] = colour
    return img


@pytest.mark.parametrize(
    ("lit", "expected"), [(0.85, 1.0), (0.53, 0.62), (0.37, 0.44), (0.0, 0.0)]
)  # fmt: skip
def test_hp_fraction_follows_the_lit_columns(lit: float, expected: float) -> None:
    assert gv.hp_fraction(frame_with_bar(lit)) == pytest.approx(expected, abs=0.02)


def test_a_red_bar_still_counts() -> None:
    assert gv.hp_fraction(frame_with_bar(0.1, RED)) == pytest.approx(0.1 / 0.85, abs=0.02)


def test_the_decision() -> None:
    assert gv.vitals_action(0.9, dead=False) is None
    assert gv.vitals_action(0.5, dead=False) == "heal"
    assert gv.vitals_action(1.0, dead=True) == "revive"  # a dead GM's bar can read half full
    assert gv.vitals_action(None, dead=False) is None


def grass(seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.clip(rng.normal((60, 120, 80), 6, (90, 90, 3)), 0, 255).astype(np.uint8)


def test_motion_ignores_the_cursor_and_the_marker_pulse() -> None:
    a, b = grass(), grass()
    b[45:80, 45:80] = 255  # the animated cursor changes at the crop's centre
    a[20:30, 10:30] = (170, 210, 60)  # the mint marker (BGR) in one frame only (its pulse)
    assert gv.motion_fraction(a, b) < 0.01


def test_motion_sees_a_sprite_walking_in() -> None:
    a, b = grass(), grass()
    b[5:40, 5:45] = (120, 120, 240)  # a pink sprite entered the target's crop
    assert gv.motion_fraction(a, b) > gv.MOTION_MAX
