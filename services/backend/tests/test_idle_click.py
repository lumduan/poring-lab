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


def test_the_sign_box_is_the_title_bar_found_by_its_shape_not_its_colour(ic: ModuleType) -> None:
    """The clicks go under the bar, so the bar's bottom outline is the measured edge. A field of the
    sign's own colours is no sign (the first finder's colour union made one giant false box)."""
    img = np.full((720, 1280, 4), 120, np.uint8)  # BGRA floor

    def box(x0: int, y0: int, x1: int, y1: int, bgr: tuple[int, int, int]) -> None:
        img[y0 : y1 + 1, x0 : x1 + 1, :3] = bgr

    for x0, y0, x1, y1, inner in ((630, 463, 758, 486, (38, 75, 103)),  # the bar, then the icon
                                  (599, 459, 630, 490, (220, 180, 200))):  # fmt: skip
        box(x0 - 1, y0 - 1, x1 + 1, y1 + 1, (255, 255, 255))  # the white halo
        box(x0, y0, x1, y1, (0, 0, 0))  # the black outline
        box(x0 + 1, y0 + 1, x1 - 1, y1 - 1, (40, 130, 208))  # the orange border
        box(x0 + 4, y0 + 4, x1 - 4, y1 - 4, inner)
    assert ic.sign_box(img) == (630, 463, 758, 486)
    warm = np.full((720, 1280, 4), 120, np.uint8)
    warm[140:530, 230:1130, :3] = (40, 140, 220)  # the sign's orange over half the world
    assert ic.sign_box(warm) is None


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
