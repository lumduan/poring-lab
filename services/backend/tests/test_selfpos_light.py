"""selfpos_light (rogue-xmas02 X1b): the truth labels of the readout crops and the strip measure."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def sl() -> ModuleType:
    path = ROOT / "scripts/selfpos_light.py"
    spec = importlib.util.spec_from_file_location("selfpos_light", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["selfpos_light"] = mod
    spec.loader.exec_module(mod)
    return mod


GID = 2000002


def warp(t: int, x: int, y: int, map_: str = "xmas_dun02.gat") -> dict:
    return {"type": "map_change", "t_mono_ns": t, "map": map_, "x": x, "y": y}


def sample(i: int, stand: int, sent: list[int], t_cmd: int, t_grab: int) -> dict:
    return {"i": i, "stand": stand, "sent": sent, "k": 0, "t_cmd_ns": t_cmd, "t_grab_ns": t_grab}


def test_a_crop_is_labelled_by_the_warp_it_stands_after(sl: ModuleType) -> None:
    events = [
        warp(100, 7, 21),
        {"type": "move", "gid": 110000001, "t_mono_ns": 150},  # a monster: not ours
        warp(300, 7, 33),
        warp(500, 9, 40),  # the server put us elsewhere
        {"type": "entity_stop", "gid": GID, "t_mono_ns": 750, "x": 9, "y": 41},
        warp(900, 7, 60, "prt_fild08.gat"),
    ]
    samples = [
        sample(0, 0, [7, 21], 90, 200),  # landed where sent, stood: labelled
        sample(1, 1, [7, 33], 290, 400),
        sample(2, 2, [9, 45], 490, 600),  # landed at 9,40
        sample(3, 2, [9, 40], 490, 800),  # an own stop after the warp: moved
        sample(4, 3, [7, 60], 890, 950),  # another map
        sample(5, 4, [7, 70], 960, 970),  # no warp after its command
    ]
    got = sl.label(samples, events, "xmas_dun02", GID)
    assert [s["truth"] for s in got] == [[7, 21], [7, 33], None, None, None, None]
    assert [s["why"] for s in got][2:] == [
        "landed at 9,40", "moved after the warp", "landed on prt_fild08.gat",
        "no map_change after the typed @warp",
    ]  # fmt: skip


def test_the_scene_median_leaves_the_opaque_glyph_pixels_out(sl: ModuleType) -> None:
    g = np.full((15, 56), 200.0, np.float32)  # a pale floor
    g[3:12, 10:40:2] = 252.0  # strokes
    g[3:12, 9:39:2] = 0.0  # their shadows
    assert sl.scene_median(g) == 200.0
    assert sl.scene_median(g) >= sl.LIGHT_STRIP
