"""scripts/route_demo.py's checks must catch the bugs they are for (Batt 2026-10-08: a check
proves it can see a positive case):
- GLUED: on a scrolling scene, a world-anchored ring scores ~0 px, while a ring fixed in screen
  pixels (the first preview) scores the whole scroll;
- FEET: a line that starts on the feet measured on the frame scores ~0 px, while a line that starts
  at the fixed anchor (the timing preview, while the camera lags) scores the feet's offset."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
ANCHOR = (640.75, 361.89)


@pytest.fixture(scope="module")
def rd() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("route_demo", SCRIPTS / "route_demo.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["route_demo"] = mod
    spec.loader.exec_module(mod)
    return mod


def frames(tmp: Path, n: int, step: tuple[int, int], feet: Any) -> list[tuple[int, Path]]:
    """The camera pans `step` px a frame over a muted texture; our HP/SP bar under feet(k)."""
    rng = np.random.default_rng(1)
    g = rng.random((1100, 1700)).astype(np.float32)
    for _ in range(3):
        g = (np.roll(g, 1, 0) + g + np.roll(g, -1, 0) + np.roll(g, 1, 1) + np.roll(g, -1, 1)) / 5
    g = (g - g.min()) / (g.max() - g.min())
    world = np.stack([g * 120 + 40, g * 130 + 50, g * 140 + 60], -1).astype(np.uint8)
    (tmp / "frames").mkdir()
    out = []
    for k in range(n):
        x0, y0 = 100 + k * step[0], 100 + k * step[1]
        img = world[y0 : y0 + 720, x0 : x0 + 1280].copy()
        fx, fy = feet(k)
        bx, by = int(round(fx - 0.75 - 30)), int(round(fy + 22.6 - 4.5))
        img[by : by + 4, bx : bx + 60] = (60, 200, 40)
        img[by + 4 : by + 9, bx : bx + 60] = (220, 90, 40)
        t = 1_000_000_000 + k * 100_000_000
        p = tmp / "frames" / f"{k:05d}-{t}.npy"
        np.save(p, img)
        out.append((t, p))
    return out


def live(n: int, ring: Any, start: Any) -> list[dict[str, Any]]:
    """Live messages in DESKTOP px (the game region at (80, 77))."""
    return [{"t_mono_ns": 1_000_000_000 + k * 100_000_000,
             "points": [{"x": (start(k)[0] + 80) / 1440, "y": (start(k)[1] + 77) / 900,
                         "kind": "feet"},
                        {"x": (ring(k)[0] + 80) / 1440, "y": (ring(k)[1] + 77) / 900,
                         "kind": "goal"}]}
            for k in range(n)]  # fmt: skip


@pytest.fixture
def screen(monkeypatch: pytest.MonkeyPatch, rd: ModuleType) -> None:
    monkeypatch.setattr(rd.r, "desktop", lambda: (1440, 900))
    monkeypatch.setattr(rd.r, "game_region", lambda: (80, 77, 1280, 720))


def feet_k(k: int) -> tuple[float, float]:  # the camera lags: the feet run ahead of the anchor
    return (ANCHOR[0] + 4.0 * k, ANCHOR[1] + 2.0 * k)


def test_the_glued_check_passes_a_glued_ring_and_fails_a_screen_fixed_one(
    rd: ModuleType, tmp_path: Path, screen: None
) -> None:
    fs = frames(tmp_path, 8, (6, 3), feet_k)  # the camera pans 6 px right, 3 px down a frame
    glued = live(8, lambda k: (820 - 6 * k, 320 - 3 * k), feet_k)  # the ring moves with the scene
    stuck = live(8, lambda k: (820, 320), feet_k)  # the first preview: fixed in screen pixels
    ok = rd.check(tmp_path, fs, glued, np.array([m["t_mono_ns"] for m in glued]))
    bad = rd.check(tmp_path, fs, stuck, np.array([m["t_mono_ns"] for m in stuck]))
    assert ok["walking_ring_error_px"]["median"] <= 1.0
    assert bad["walking_ring_error_px"]["median"] == pytest.approx(np.hypot(6, 3), abs=1.0)


def test_the_feet_check_passes_a_line_on_the_feet_and_fails_one_on_the_anchor(
    rd: ModuleType, tmp_path: Path, screen: None
) -> None:
    fs = frames(tmp_path, 8, (6, 3), feet_k)
    on_feet = live(8, lambda k: (820 - 6 * k, 320 - 3 * k), feet_k)
    on_anchor = live(8, lambda k: (820 - 6 * k, 320 - 3 * k), lambda k: ANCHOR)
    ok = rd.check(tmp_path, fs, on_feet, np.array([m["t_mono_ns"] for m in on_feet]))
    bad = rd.check(tmp_path, fs, on_anchor, np.array([m["t_mono_ns"] for m in on_anchor]))
    assert ok["walking_feet_to_line_px"]["median"] <= 1.5
    assert bad["walking_feet_to_line_px"]["max"] >= 15  # the offset the timing preview showed
    assert (tmp_path / "frames.csv").exists()
