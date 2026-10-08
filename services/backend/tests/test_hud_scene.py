"""scripts/hud_scene.py's SceneTracker (Batt 2026-10-08, the retained H.264-style HUD scene): screen
objects never shift, world objects ride ONE global motion, detection only DISCOVERS changes, and a
still scene sends nothing but keyframes."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
REGION, DESKTOP = (80, 77, 1280, 720), (1440, 900)
WINDOWS = [(0, 0, 220, 326), (1135, 14, 1266, 162)]


@pytest.fixture(scope="module")
def hs() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("hud_scene", SCRIPTS / "hud_scene.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hud_scene"] = mod  # its dataclass resolves its module by name
    spec.loader.exec_module(mod)
    return mod


def unit(cls: str, x: float, y: float, w: float = 30, h: float = 60, conf: float = 0.8) -> dict:
    return {"kind": "unit", "cls": cls, "conf": conf, "box": [x - w / 2, y - h, x + w / 2, y]}


def test_the_keyframe_holds_the_screen_anchored_zone_and_ui_windows(hs: ModuleType) -> None:
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS)
    k = t.keyframe()
    kinds = [(o["kind"], o["anchor"]) for o in k["objects"]]
    assert kinds == [("zone", "screen"), ("window", "screen"), ("window", "screen")]
    assert k["objects"][1]["box"] == {
        "x": 80 / 1440,
        "y": 77 / 900,
        "w": 220 / 1440,
        "h": 326 / 900,
    }
    assert k["offset"] == {"x": 0.0, "y": 0.0}


def test_a_static_npc_rides_the_global_motion_and_sends_nothing_new(hs: ModuleType) -> None:
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS)
    d = t.observe([unit("npc", 700, 400)], t.offset.copy())
    assert d is not None and [o["cls"] for o in d["add"]] == ["npc"] and d["seq"] == 1
    assert not t.motion((0.1, -0.2))  # sub-threshold jitter: no motion, no message
    for _ in range(10):  # we walk: the scene scrolls 3 px a frame, the NPC with it
        assert t.motion((-3.0, 2.0))
    seen_at = np.array([700 - 30.0, 400 + 20.0])  # where the NPC now is on screen
    assert t.observe([unit("npc", *seen_at)], t.offset.copy()) is None  # matched, did not move
    assert t.seq == 1


def test_a_moving_monster_gets_a_move_and_a_missed_unit_is_removed(hs: ModuleType) -> None:
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS)
    t.observe([unit("monster", 600, 300), unit("npc", 900, 500)], t.offset.copy())
    d = t.observe([unit("monster", 620, 300), unit("npc", 900, 500)], t.offset.copy())
    assert d is not None and len(d["move"]) == 1 and d["add"] == [] and d["remove"] == []
    assert t.observe([unit("monster", 620, 300)], t.offset.copy()) is None  # npc missed once
    d = t.observe([unit("monster", 620, 300)], t.offset.copy())  # ... and twice: gone
    assert d is not None and len(d["remove"]) == 1


def test_a_still_scene_sends_no_deltas(hs: ModuleType) -> None:
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS)
    t.observe([unit("npc", 700, 400), unit("npc", 300, 450)], t.offset.copy())
    for _ in range(20):
        assert not t.motion((0.05, 0.0))
        assert t.observe([unit("npc", 701, 400), unit("npc", 300, 451)], t.offset.copy()) is None


def test_every_message_is_valid_protocol(hs: ModuleType) -> None:
    import json

    from poring_env.protocol import parse_display_to_backend

    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS)
    for _ in range(50):  # far enough that world boxes leave [0, 1] at offset 0
        t.motion((-30.0, 0.0))
    sign = {"kind": "sign", "cls": "sign", "conf": None, "box": [601, 459, 758, 490]}
    d = t.observe([unit("npc", 700, 400), sign], t.offset.copy())
    for msg in (
        {"type": "hud_scene", "t_mono_ns": 1, "frame_id": 3, **t.keyframe()},
        {"type": "hud_delta", "t_mono_ns": 1, "frame_id": 3, **d},
        {"type": "hud_motion", "t_mono_ns": 1, "frame_id": 3, "offset": t.offset_norm()},
    ):
        parse_display_to_backend(json.dumps(msg))
    assert d["add"][0]["box"]["x"] > 1.0  # a world box at offset 0 may leave the screen
