"""scripts/gm_state.py (Batt 2026-10-09 ~16:00): the GM's fixed test state -- the level lines'
check (two frames must agree), the restore decision, and the crop geometry."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[2].parent / "scripts"


@pytest.fixture(scope="module")
def gs() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("gm_state", SCRIPTS / "gm_state.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gm_state"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_both_frames_must_agree(gs: Any) -> None:
    m = gs.MATCH
    assert gs.decide(0.5, m) == "fixed"
    assert gs.decide(m + 1, m + 9) == "restore"
    assert gs.decide(0.5, m + 1) == "unstable" and gs.decide(m + 1, 0.5) == "unstable"


def test_a_changed_digit_is_far_from_the_template(gs: Any) -> None:
    rng = np.random.default_rng(5)
    frame = rng.integers(180, 230, (720, 1280, 3)).astype(np.uint8)
    x, y, w, h = gs.LEVEL_BOX
    template = gs.crop(frame)
    assert template.shape == (h, w) and gs.distance(frame, template) == 0.0
    other = frame.copy()
    other[y + 3 : y + 12, x + 50 : x + 56] = 20  # a 6 x 9 dark digit where the level number sits
    assert gs.distance(other, template) > gs.MATCH
    assert gs.distance(frame[:50, :50], template) == float("inf")  # a wrong size never matches
    noisy = np.clip(frame.astype(int) + rng.integers(-12, 13, frame.shape), 0, 255).astype(np.uint8)
    assert gs.distance(noisy, template) <= gs.MATCH  # codec-level noise is not a change
    one = frame.copy()
    one[y + 4 : y + 9, x + 52] = 10  # a 1 x 5 stroke: the smallest digit change (1 -> 4, say)
    assert gs.distance(one, template) > gs.MATCH


def test_the_restore_lines_lower_both_levels_then_heal(gs: Any) -> None:
    assert gs.RESTORE == ("@baselevelup -98", "@joblevelup -49", "@heal")
    assert len(set(gs.RESTORE)) == len(gs.RESTORE)  # never an identical line in a row


def test_the_notices_are_seen_only_when_shown(gs: Any) -> None:
    """Each notice on its OWN pixels: the see-through shortcut window must not matter."""
    rng = np.random.default_rng(9)
    frame = rng.integers(60, 200, (720, 1280, 3)).astype(np.uint8)
    refs: dict[str, Any] = {}
    for name, box in (("badge", gs.BADGE_BOX), ("levelup_icon", gs.ICON_BOX)):
        _x, _y, w, h = box
        refs[name] = rng.integers(0, 255, (h, w)).astype(np.float32)
        mask = np.zeros((h, w), bool)
        mask[2:12, 2:12] = True
        refs[f"{name}_mask"] = mask
    assert gs.notices(frame, refs) == []
    for name, box in (("badge", gs.BADGE_BOX), ("levelup_icon", gs.ICON_BOX)):
        x, y, w, h = box
        shown = frame.copy()
        shown[y + 2 : y + 12, x + 2 : x + 12] = refs[name].astype(np.uint8)[2:12, 2:12, None]
        shown[y + 20 : y + 30, x + 20 : x + 30] = 0  # the scene behind changes: irrelevant
        assert gs.notices(shown, refs) == [name], name
