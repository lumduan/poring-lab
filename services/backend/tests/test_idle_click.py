"""scripts/idle_click.py (idle@1, demonstrations 3.23): the signboard box from pixels, and the
offline judge (a move request within 2 s of the click; a skipped trial is never judged)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture(scope="module")
def ic() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("idle_click", SCRIPTS / "idle_click.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_sign_box_is_its_orange_border_down_to_its_dark_outline(ic: ModuleType) -> None:
    img = np.full((720, 1280, 4), 120, np.uint8)  # BGRA floor
    img[461:489, 601:757, :3] = (40, 140, 220)  # the orange border (BGR)
    img[464:486, 640:750, :3] = (41, 74, 106)  # the brown bar inside
    img[489:491, 601:629, :3] = 0  # the icon square's dark outline below
    img[600:640, 50:150, :3] = (40, 140, 220)  # orange OUTSIDE the search area: ignored
    assert ic.sign_box(img) == (601, 461, 756, 490)
    assert ic.sign_box(np.full((720, 1280, 4), 120, np.uint8)) is None


def test_the_judge_needs_a_move_request_within_two_seconds(ic: ModuleType) -> None:
    S = 1_000_000_000
    trials = [{"condition": "N2", "clicked": True, "t_click": 10 * S},
              {"condition": "N2", "clicked": True, "t_click": 20 * S},
              {"condition": "T15", "clicked": False}]  # fmt: skip
    events = [{"type": "self_move_request", "t_mono_ns": 10 * S + S // 2},
              {"type": "self_move_request", "t_mono_ns": 20 * S + 3 * S}]  # fmt: skip
    v = ic.judge(trials, events)["per_condition"]
    assert v["N2"] == {"clicked": 2, "walked": 1, "failed": 1, "skipped": 0}
    assert v["T15"]["skipped"] == 1 and trials[0]["walked"] and not trials[1]["walked"]
