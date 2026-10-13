"""scripts/cursor_anim.py (cursor@3, Batt 2026-10-13): the animated region of a view, measured with
the cursor parked over a whole cycle, cached per view and unioned with Prober9's 0.25 s map; a
fresh background before each hover. Synthetic frames only (no client pixels)."""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def _load(name: str) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ca() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    return _load("cursor_anim")


def sail(angle: float, h: int = 120, w: int = 160) -> np.ndarray:
    """A grey floor with a white bar (a windmill sail) through (80, 60) at ``angle``."""
    img = np.full((h, w, 3), 90, np.uint8)
    for t in np.linspace(-50, 50, 400):
        x, y = int(round(80 + t * math.cos(angle))), int(round(60 + t * math.sin(angle)))
        if 0 <= x < w and 0 <= y < h:
            img[max(0, y - 2) : y + 3, max(0, x - 2) : x + 3] = 240
    return img


def test_a_whole_cycle_covers_the_sails_sweep_and_nothing_static(ca: ModuleType) -> None:
    frames = [sail(k * math.pi / 12) for k in range(13)]  # a half-turn sweeps the whole disc
    region = ca.animated_region(frames)
    yy, xx = np.mgrid[0:120, 0:160]
    r = np.hypot(xx - 80, yy - 60)
    assert region[(r > 8) & (r < 45)].mean() > 0.97  # the swept disc (the hub never changes)
    assert not region[r > 56].any()  # the floor outside the sweep: not animated
    two = ca.animated_region(frames[:2])  # Prober9's two parked frames: a sliver only
    assert two[(r > 8) & (r < 45)].mean() < 0.3


def test_measure_grabs_n_frames_gap_apart(ca: ModuleType) -> None:
    k = {"n": 0}
    slept: list[float] = []

    def grab() -> Any:
        k["n"] += 1
        return sail(k["n"] * 0.3)

    region, frames = ca.measure(grab, n=5, gap=0.2, sleep=slept.append)
    assert len(frames) == 5 and slept == [0.2] * 4 and region.any()
    with pytest.raises(ValueError):
        ca.animated_region(frames[:1])


def test_prober_anim_caches_per_view_unions_and_takes_a_fresh_background(
    ca: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("walk5", "walk6", "reloc2", "where_fix", "walk7", "walk8", "walk9", "walk10"):
        _load(name)
    w6, w10 = sys.modules["walk6"], sys.modules["walk10"]
    r = sys.modules["ro_agent"]
    monkeypatch.setattr(r, "game_region", lambda: (0, 0, 160, 120))
    short = np.zeros((120, 160), bool)
    short[0, 0] = True

    def fake_park(self: Any) -> bool:
        self.background, self.animated = sail(0.0), short.copy()
        return True

    monkeypatch.setattr(w10.Prober9, "park", fake_park)
    hovers: list[tuple[float, float]] = []
    monkeypatch.setattr(w6.Prober, "hover", lambda self, u, v: hovers.append((u, v)))
    calls = {"n": 0}
    disc = np.zeros((120, 160), bool)
    disc[20:100, 40:120] = True

    def fake_measure(grab: Any, **kw: Any) -> tuple[Any, list[Any]]:
        calls["n"] += 1
        return disc, []

    monkeypatch.setattr(ca, "measure", fake_measure)

    class Screen:
        def __init__(self) -> None:
            self.k = 0

        def grab(self, *a: Any) -> tuple[int, np.ndarray]:
            self.k += 1
            return 0, sail(self.k * 0.5)

    pr = ca.prober_anim(None, Screen(), refs=None)
    pr.set_view(("alberta", 129, 48))
    assert pr.park() and calls["n"] == 1
    assert pr.animated[0, 0] and pr.animated[50, 80] and not pr.animated[5, 5]
    assert pr.park_background is not None and pr.anim_short[0, 0] and not pr.anim_short[50, 80]
    assert pr.park() and calls["n"] == 1  # the same view: cached
    pr.set_view(("alberta", 130, 48))
    assert pr.park() and calls["n"] == 2  # a new view: measured again
    pr.set_view(None)
    assert pr.park() and pr.park() and calls["n"] == 4  # no view: never cached
    before = pr.background
    pr.hover(10.0, 20.0)
    assert hovers == [(10.0, 20.0)] and pr.background is not before  # FRESH before the hover


def test_the_probe_arm_keeps_v3_references_and_saves_robust2s_inputs() -> None:
    src = (SCRIPTS / "npc_click_test.py").read_text()
    assert 'cursor_gate.prober(agent, screen, classifier="v3" if kind == "probe" else None)' in src
    for key in ('arrays["b2"]', 'arrays["anim2"]', 'arrays["region"]'):
        assert key in src
