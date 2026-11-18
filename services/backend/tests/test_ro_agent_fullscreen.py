"""ro_agent with a FULLSCREEN client (Batt 2026-11-18, docs/planning/fullscreen-client.md): no
title bar, so the client is in front when Windows' taskbar is absent; activating it never clicks
(a click lands in the game); the keyboard layout is read on the desktop just before the launch;
"no client" only when proven, never because it cannot tell."""

from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture()
def ro(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location("ro_agent_fullscreen", SCRIPTS / "ro_agent.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sig = tmp_path / "signatures"
    sig.mkdir()
    monkeypatch.setattr(module, "signature_path", lambda state: sig / f"{state}.npy")
    monkeypatch.setattr(module, "desktop", lambda: (1280, 720))
    monkeypatch.setattr(module, "game_region", lambda: (0, 0, 1280, 720))
    monkeypatch.setattr(module, "SHOTS", tmp_path)
    monkeypatch.setattr(module, "to_png", lambda *a, **k: None)
    return module


def calibrate(ro: ModuleType, state: str, box: list[int]) -> None:
    path = ro.signature_path(state)
    np.save(path, np.zeros((2, 2), np.float32))
    path.with_suffix(".json").write_text(json.dumps({"box": box}))


class FakeScreen:
    def full(self) -> np.ndarray:
        return np.zeros((720, 1280, 4), np.uint8)


SCREEN = FakeScreen()


class Clicks:
    def __init__(self) -> None:
        self.clicks: list[tuple[int, int]] = []

    def click(self, x: int, y: int) -> None:
        self.clicks.append((x, y))


def test_fullscreen_is_the_region_filling_the_session(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert ro.fullscreen()
    monkeypatch.setattr(ro, "game_region", lambda: (80, 77, 1280, 720))
    monkeypatch.setattr(ro, "desktop", lambda: (1440, 900))
    assert not ro.fullscreen()  # the lab's window
    monkeypatch.setattr(ro, "game_region", lambda: (0, 0, 1280, 720))
    assert not ro.fullscreen()  # a corner of a bigger session is not fullscreen


def test_the_taskbar_boxes_are_desktop_pixels(ro: ModuleType) -> None:
    calibrate(ro, "taskbar", [1020, 672, 170, 48])
    calibrate(ro, "taskbar_client_icon", [910, 676, 38, 40])
    assert ro.region_for("taskbar") == (1020, 672, 170, 48)
    assert ro.region_for("taskbar_client_icon") == (910, 676, 38, 40)


def test_activating_a_fullscreen_client_only_verifies_and_never_clicks(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = Clicks()
    with pytest.raises(ro.Stop, match="no taskbar template"):
        ro.activate_client(agent, SCREEN)
    calibrate(ro, "taskbar", [1020, 672, 170, 48])
    seen: dict[str, float] = {"taskbar": 49.9}
    monkeypatch.setattr(ro, "distance", lambda screen, state, after_ns=None: seen[state])
    ro.activate_client(agent, SCREEN)  # the taskbar absent: in front
    for shown in (0.0, 15.0):  # shown, or too close to call
        seen["taskbar"] = shown
        with pytest.raises(ro.Stop, match="not in front"):
            ro.activate_client(agent, SCREEN)
    assert agent.clicks == []  # never a click: in fullscreen it would land in the game


def test_the_layout_is_read_before_the_launch_and_stands_for_the_login(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    calibrate(ro, "taskbar", [1020, 672, 170, 48])
    state = {"taskbar": 0.0, "eng": True}
    monkeypatch.setattr(ro, "distance", lambda screen, st, after_ns=None: state[st])
    monkeypatch.setattr(ro, "is_state", lambda screen, st, after_ns=None: state[st])
    ro._ENG_AT = None
    ro.require_eng(SCREEN)  # the desktop shows (taskbar): the tray is read, and remembered
    assert ro._ENG_AT is not None
    state["taskbar"] = 49.9  # the client went fullscreen: the tray is gone
    ro.require_eng(SCREEN)  # the reading taken before the launch stands
    ro._ENG_AT = time.monotonic() - ro.ENG_FRESH_S - 1
    with pytest.raises(ro.Stop, match="hides the tray"):
        ro.require_eng(SCREEN)  # too old: no credentials typed
    ro._ENG_AT = None
    with pytest.raises(ro.Stop, match="hides the tray"):
        ro.require_eng(SCREEN)
    state.update(taskbar=0.0, eng=False)
    with pytest.raises(ro.Stop, match="not ENG"):
        ro.require_eng(SCREEN)


def test_no_client_only_when_proven(ro: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    """A minimized fullscreen client shows the desktop: 'absent' would launch a second client.
    Absent only with the taskbar shown AND the client's button nowhere on it."""
    calibrate(ro, "taskbar", [1020, 672, 170, 48])
    seen: dict[str, Any] = {"taskbar": 49.9, "icon": True}
    monkeypatch.setattr(ro, "distance", lambda screen, st, after_ns=None: seen[st])
    monkeypatch.setattr(ro, "taskbar_icon_found", lambda screen: seen["icon"])
    assert ro.client_absent(SCREEN) is False  # in front
    seen["taskbar"] = 0.0
    assert ro.client_absent(SCREEN) is False  # no icon template: cannot tell, never absent
    calibrate(ro, "taskbar_client_icon", [910, 676, 38, 40])
    assert ro.client_absent(SCREEN) is False  # its button is on the taskbar: running
    seen["icon"] = False
    assert ro.client_absent(SCREEN) is True


def test_the_client_button_is_found_wherever_the_taskbar_puts_it(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    from poring_backend.signature import grey_thumb

    rng = np.random.default_rng(7)
    icon = rng.integers(0, 255, (40, 38, 4), dtype=np.uint8)
    calibrate(ro, "taskbar_client_icon", [910, 676, 38, 40])
    np.save(ro.signature_path("taskbar_client_icon"), grey_thumb(icon))

    class Row:
        def __init__(self, at: int | None) -> None:
            self.row = np.zeros((40, 1280, 4), np.uint8)
            if at is not None:
                self.row[:, at : at + 38] = icon

        def grab(self, x: int, y: int, w: int, h: int) -> tuple[int, np.ndarray]:
            assert (x, y, w, h) == (0, 676, 1280, 40)
            return 0, self.row

    assert ro.taskbar_icon_found(Row(886))  # moved left by a closed program
    assert not ro.taskbar_icon_found(Row(None))
