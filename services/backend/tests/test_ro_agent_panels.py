"""ro_agent's FOUND windows (teaching-prerun.md 4f, Batt 2026-11-19: "make it work with every
client"): each window found by its shape is moved, in the virtual 1280x720 client, to its lab
place -- even a 1280x720 window whose panels a player dragged elsewhere is then virtual; a window
not found keeps the lab's place; another process reads the same find from a shared file."""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))
TESTS = Path(__file__).resolve().parents[3] / "packages" / "poring_env" / "tests"
sys.path.insert(0, str(TESTS))

import test_panelfind as tp  # noqa: E402  (the synthetic windows)

from poring_env import panelfind as pf  # noqa: E402


@pytest.fixture()
def ro(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location("ro_agent_panels", SCRIPTS / "ro_agent.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "desktop", lambda: (1280, 720))
    monkeypatch.setattr(module, "real_game_region", lambda: (0, 0, 1280, 720))
    monkeypatch.setattr(module, "_POINTER", None)
    return module


def frame_with(basic: tuple[int, int] | None, hotbar: tuple[int, int] | None,
               h: int = 720, w: int = 1280) -> np.ndarray:  # fmt: skip
    """A BGRA frame (grey, B = G = R) with the synthetic windows."""
    lum = tp.world(h, w)
    if hotbar is not None:
        tp.draw_hotbar(lum, hotbar)
    if basic is not None:
        tp.draw_basic(lum, basic)
    g = np.clip(lum, 0, 255).astype(np.uint8)
    return np.dstack([g, g, g, np.full_like(g, 255)])


class Found:
    def __init__(self, origin: tuple[int, int], score: int = 9, of: int = 9) -> None:
        self.origin, self.score, self.of = origin, score, of


def test_each_found_window_is_its_lab_box_moved_by_its_vector(ro: ModuleType) -> None:
    got = ro.panel_places(Found((40, 60)), Found((500, 300)),
                          {"left": 30, "text_top": 580, "bottom": 700, "lines": 6})  # fmt: skip
    assert got["basic_info"]["real_xy"] == [40, 60]
    assert got["basic_info"]["virtual"] == [0, 0, 230, 150]
    assert got["hotbar"]["real_xy"] == [496, 300]  # the lab box starts 4 px left of the origin
    assert got["chat"]["virtual"] == [0, 578, 600, 142] and got["chat"]["real_xy"] == [30, 559]
    nine = ro.panel_places(None, None, {"left": 0, "text_top": 0, "bottom": 700, "lines": 9})
    assert nine["chat"]["virtual"] == [0, 536, 600, 184]  # its own height, its bottom on 719
    assert nine["chat"]["real_xy"] == [0, 517] and set(nine) == {"chat"}
    assert ro.panel_places(None, None, {"left": 1, "text_top": 2, "bottom": None,
                                        "lines": None, "obscured": True}) == {}  # fmt: skip


def test_the_lab_layout_is_not_moved_and_stays_1_to_1(ro: ModuleType) -> None:
    lab = ro.panel_places(Found((0, 0)), Found((230, 0)),
                          {"left": 0, "text_top": 598, "bottom": 719, "lines": 6})  # fmt: skip
    assert not ro.panels_moved(lab, (1280, 720))
    assert ro.panels_moved(ro.panel_places(Found((400, 0)), None, None), (1280, 720))


def test_a_1280x720_window_with_dragged_windows_becomes_virtual(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert not ro.virtual_active() and ro.client_view().identity  # nothing found: as before
    frame = frame_with(basic=(400, 300), hotbar=(700, 600))
    st = ro.find_panels(real=frame)
    assert st["moved"] and set(st["found"]) == {"basic_info", "hotbar"}
    assert st["missing"] == ["chat"]
    assert ro.virtual_active() and ro.game_region() == (ro.VIRTUAL_X0, 0, 1280, 720)
    view = ro.client_view()
    assert view.to_real(10, 10) == (410, 310)  # a point of Basic Info: where it was found
    assert view.to_real(300, 10) == (300 - 230 + 700, 610)  # a hotbar slot: the found hotbar
    vf = view.virtual_frame(frame[..., :3])
    # Basic Info at its lab place (its 220 px: the lab's boxes overlap the hotbar's by 4 columns)
    assert (vf[0:150, 0:220] == frame[300:450, 400:620, :3]).all()


def test_another_process_reads_the_find_for_the_same_region_while_fresh(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    ro.find_panels(real=frame_with(basic=(400, 300), hotbar=None))
    shared = json.loads(ro.panels_file().read_text())
    assert shared["found"]["basic_info"]["origin"] == [400, 300]
    ro._PANELS.clear()  # another process: no find of its own
    ro._PANELS_FILE_CACHE[0] = 0.0
    assert ro._panel_state()["found"]["basic_info"]["origin"] == [400, 300]
    monkeypatch.setattr(ro, "real_game_region", lambda: (8, 8, 1280, 720))  # another client place
    ro._PANELS_FILE_CACHE[0] = 0.0
    assert ro._panel_state() == {}
    monkeypatch.setattr(ro, "real_game_region", lambda: (0, 0, 1280, 720))
    shared["t_wall"] = time.time() - ro.PANELS_TTL_S - 1  # too old
    ro.panels_file().write_text(json.dumps(shared))
    ro._PANELS_FILE_CACHE[0] = 0.0
    assert ro._panel_state() == {}


def test_the_tick_finds_once_rechecks_cheaply_and_searches_again_only_when_due(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    real_find = ro.find_panels

    def find(screen: Any = None, real: Any = None) -> Any:
        calls.append("find")
        return real_find(screen, real)

    monkeypatch.setattr(ro, "find_panels", find)
    frame = frame_with(basic=(0, 0), hotbar=(230, 0))
    ro._panels_tick(frame)
    assert calls == ["find"]  # the first frame finds
    ro._panels_tick(frame)
    assert calls == ["find"]  # within PANEL_CHECK_S: nothing
    ro._PANELS["checked"] = 0.0
    ro._panels_tick(frame)
    assert calls == ["find"]  # re-checked at their places: the found ones are there
    moved = frame_with(basic=(400, 300), hotbar=(230, 0))
    ro._PANELS["checked"] = 0.0
    ro._panels_tick(moved)
    assert calls == ["find"]  # Basic Info gone from its place, but the chat is missing anyway
    ro._PANELS["checked"], ro._PANELS["searched"] = 0.0, 0.0
    ro._panels_tick(moved)
    assert calls == ["find", "find"]  # a search is due: it finds the moved one
    assert ro._PANELS["found"]["basic_info"]["origin"] == [400, 300]


def test_the_virtual_grab_path_finds_and_moves_the_windows(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ro, "real_game_region", lambda: (0, 0, 1920, 1080))
    monkeypatch.setattr(ro, "desktop", lambda: (1920, 1080))
    frame = frame_with(basic=(900, 500), hotbar=(1200, 900), h=1080, w=1920)

    class Raw(ro.Screen):  # type: ignore[misc,name-defined]
        def __init__(self) -> None:
            pass

        def grab_meta(self, x: int, y: int, w: int, h: int) -> Any:
            if x >= ro.VIRTUAL_X0:
                return super().grab_meta(x, y, w, h)
            return 7, np.ascontiguousarray(frame[y : y + h, x : x + w]), 42, "bus"

    _, crop, _, _ = Raw().grab_meta(ro.VIRTUAL_X0, 0, 230, 150)  # Basic Info's lab box
    assert (crop[:, :220, :3] == frame[500:650, 900:1120, :3]).all()


def test_the_run_log_says_where_each_window_was_found(ro: ModuleType) -> None:
    st = ro.find_panels(real=frame_with(basic=(0, 0), hotbar=(700, 600)))
    words = ro.panels_words(st)
    assert words[0] == "Basic Info found at (0, 0) (11 of 11 of its shape's cues): the lab's place"
    assert words[1].startswith("the hotbar found at (700, 600) (13 of 13") and "moved" in words[1]
    assert words[2].startswith("the chat window NOT found") and "cannot be read" in words[2]
    assert words[3] == "the minimap: the top-right corner (RO keeps it there)"
    assert ro.panels_words({}) == ["the windows: not looked for yet (the lab's places are assumed)"]


def test_the_finders_and_the_lab_origins_agree(ro: ModuleType) -> None:
    """The lab's origins are where the finders put the lab's own windows (measured 2026-11-19)."""
    lum = tp.draw_basic(tp.draw_hotbar(tp.world(), ro.LAB_WINDOW_ORIGINS["hotbar"]),
                        ro.LAB_WINDOW_ORIGINS["basic_info"])  # fmt: skip
    assert pf.find_hotbar(lum).origin == ro.LAB_WINDOW_ORIGINS["hotbar"]  # type: ignore[union-attr]
    assert pf.find_basic_info(lum).origin == (0, 0)  # type: ignore[union-attr]
    assert ro.CHAT_LAB_BOTTOM == 578 + 142 - 1
