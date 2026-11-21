"""The fi7 rule at RUN time (xmas02-items-1080.md Amendment 22, round 7): the live player drops the
floor-item model's boxes under the floor (A) or on the no-entry cursor ring (B), at 1080 only, by
two player settings that are OFF by default (until 8a7 and 8c pass). The runner's frames are BGR
(from BGRA); the ring test counts pure red in RGB, so the channels are swapped -- pinned here."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import flow_play as fp  # noqa: E402

from poring_flow import settings as st  # noqa: E402


def box(x0: float, y0: float, cls: str = "floor_item", score: float = 0.8) -> Any:
    return types.SimpleNamespace(x0=x0, y0=y0, x1=x0 + 16, y1=y0 + 16, cls=cls, score=score)


def frame_with(x: int, y: int, bgr: tuple[int, int, int]) -> Any:
    """A 720 x 1280 BGR frame (the runner's) with a 12 x 12 patch of one colour at (x, y)."""
    img = np.full((720, 1280, 3), 90, dtype=np.uint8)
    img[y : y + 12, x : x + 12] = bgr
    return img


def test_the_ring_is_found_in_the_runners_bgr_frame_and_blue_is_not() -> None:
    red_bgr = frame_with(102, 102, (0, 0, 255))  # pure RED, written B, G, R
    blue_bgr = frame_with(102, 102, (255, 0, 0))  # pure BLUE: never a ring
    b = box(100, 100)
    assert fp.item_boxes_kept([b], red_bgr, 0.0, 30) == []  # the ring (144 red px) dropped
    assert fp.item_boxes_kept([b], blue_bgr, 0.0, 30) == [b]  # channels the right way round


def test_the_floor_drops_faint_item_boxes_only_and_other_classes_pass() -> None:
    img = frame_with(500, 500, (90, 90, 90))
    faint, sure, exact = box(10, 10, score=0.3), box(40, 40, score=0.8), box(70, 70, score=0.5)
    mob = box(100, 100, cls="monster", score=0.1)
    assert fp.item_boxes_kept([faint, sure, exact, mob], img, 0.5, 0) == [sure, exact, mob]
    # a monster box on the ring is never dropped (only floor_item boxes are judged)
    red = frame_with(102, 102, (0, 0, 255))
    on_ring = box(100, 100, cls="monster")
    assert fp.item_boxes_kept([on_ring], red, 0.5, 30) == [on_ring]


def test_both_off_by_default_and_player_settings() -> None:
    for name in ("item_floor_1080", "item_ring_1080"):
        f = st.BY_NAME[name]
        assert f.optional and f.player and f.group == "loot" and st.DEFAULTS[name] == 0.0


def test_the_rule_wraps_the_detector_only_at_1080_and_only_when_set(monkeypatch: Any) -> None:
    import ro_agent as r
    import unit_detector as ud

    def fake(self: Any, img: Any) -> list[Any]:
        return [box(10, 10, score=0.3), box(40, 40, cls="monster")]

    monkeypatch.setattr(ud.GpuDetector, "detect", fake)
    monkeypatch.setattr(ud.UnitDetector, "detect", fake)
    on = {**st.flag_defaults(), "item_floor_1080": 0.5}
    monkeypatch.setattr(r, "virtual_active", lambda: True)
    with fp.item_rule(on):
        got = ud.GpuDetector.detect(types.SimpleNamespace(), np.zeros((720, 1280, 3), np.uint8))
    assert [b.cls for b in got] == ["monster"]  # the faint item box dropped
    assert ud.GpuDetector.detect is fake  # restored
    with fp.item_rule({**st.flag_defaults()}):  # off: the detector untouched
        assert ud.GpuDetector.detect is fake
    monkeypatch.setattr(r, "virtual_active", lambda: False)
    with fp.item_rule(on):  # 720: untouched
        assert ud.GpuDetector.detect is fake


def test_a_failing_filter_gives_the_detectors_own_boxes(monkeypatch: Any) -> None:
    import ro_agent as r
    import unit_detector as ud

    out = [box(10, 10, score=0.3)]
    monkeypatch.setattr(ud.GpuDetector, "detect", lambda self, img: out)
    monkeypatch.setattr(ud.UnitDetector, "detect", lambda self, img: out)
    monkeypatch.setattr(r, "virtual_active", lambda: True)
    monkeypatch.setattr(
        fp, "item_boxes_kept", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))
    )
    with fp.item_rule({**st.flag_defaults(), "item_ring_1080": 30.0}):
        assert ud.GpuDetector.detect(types.SimpleNamespace(), None) == out


@pytest.mark.parametrize("name", ["item_floor_1080", "item_ring_1080"])
def test_never_a_runner_flag(name: str) -> None:
    """The live player applies it (flow_play.item_rule); no runner argv ever carries it."""
    f = st.BY_NAME[name]
    assert f.player and not f.flag
