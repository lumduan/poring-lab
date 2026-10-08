"""scripts/route_demo.py's GLUED check must catch the bug it is for (Batt 2026-10-08: a check proves
it can see a positive case): on a scrolling scene, a world-anchored ring scores ~0 px, a ring fixed
in screen pixels (the old preview) scores the whole scroll."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture(scope="module")
def rd() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("route_demo", SCRIPTS / "route_demo.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["route_demo"] = mod
    spec.loader.exec_module(mod)
    return mod


def frames(tmp: Path, n: int, step: tuple[int, int]) -> list[Path]:
    rng = np.random.default_rng(1)
    world = rng.integers(0, 255, (1100, 1700, 3), dtype=np.uint8)
    out = []
    for k in range(n):
        x0, y0 = 100 + k * step[0], 100 + k * step[1]
        p = tmp / f"{k:05d}-{1_000_000_000 + k * 100_000_000}.npy"
        np.save(p, world[y0 : y0 + 720, x0 : x0 + 1280])
        out.append(p)
    return out


def live(n: int, ring: Any) -> list[dict[str, Any]]:
    return [{"t_mono_ns": 1_000_000_000 + k * 100_000_000,
             "points": [{"x": ring(k)[0] / 1440, "y": ring(k)[1] / 900, "kind": "goal"}]}
            for k in range(n)]  # fmt: skip


def test_the_check_passes_a_glued_ring_and_fails_a_screen_fixed_one(
    rd: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rd.r, "desktop", lambda: (1440, 900))
    fs = frames(tmp_path, 8, (6, 3))  # the camera pans 6 px right, 3 px down a frame
    glued = live(8, lambda k: (900 - 6 * k, 400 - 3 * k))  # the ring moves with the scene
    stuck = live(8, lambda k: (900, 400))  # the old preview: fixed in screen pixels
    t = np.array([m["t_mono_ns"] for m in glued])
    ok = rd.check(fs, glued, t)
    bad = rd.check(fs, stuck, t)
    assert ok["walking_ring_error_px"]["median"] <= 1.0
    assert bad["walking_ring_error_px"]["median"] == pytest.approx(np.hypot(6, 3), abs=1.0)
