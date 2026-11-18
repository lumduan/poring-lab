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
    monkeypatch.setattr(module, "real_game_region", lambda: (0, 0, 1280, 720))
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


class GrabScreen(FakeScreen):
    def grab(self, x: int, y: int, w: int, h: int) -> tuple[int, np.ndarray]:
        return 0, np.zeros((h, w, 4), np.uint8)


SCREEN_GRAB = GrabScreen()


class Clicks:
    def __init__(self) -> None:
        self.clicks: list[tuple[int, int]] = []

    def click(self, x: int, y: int) -> None:
        self.clicks.append((x, y))


def test_fullscreen_is_the_region_filling_the_session(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert ro.fullscreen()
    monkeypatch.setattr(ro, "real_game_region", lambda: (80, 77, 1280, 720))
    monkeypatch.setattr(ro, "desktop", lambda: (1440, 900))
    assert not ro.fullscreen()  # the lab's window
    monkeypatch.setattr(ro, "real_game_region", lambda: (0, 0, 1280, 720))
    assert not ro.fullscreen()  # a corner of a bigger session is not fullscreen


def test_the_taskbar_boxes_are_desktop_pixels(ro: ModuleType) -> None:
    calibrate(ro, "taskbar", [1020, 672, 170, 48])
    calibrate(ro, "taskbar_client_icon", [910, 676, 38, 40])
    assert ro.region_for("taskbar") == (1020, 672, 170, 48)
    assert ro.region_for("taskbar_client_icon") == (910, 676, 38, 40)


def test_the_taskbar_boxes_follow_the_screen_s_bottom(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cut at 1280x720 (the session stored with the box): at 1920x1080 the tray moves by the
    size difference; the client's button only by the height (its row is searched across)."""
    cuts = (("taskbar", [1020, 672, 170, 48]), ("taskbar_client_icon", [910, 676, 38, 40]))
    for state, box in cuts:
        np.save(ro.signature_path(state), np.zeros((2, 2), np.float32))
        ro.signature_path(state).with_suffix(".json").write_text(
            json.dumps({"box": box, "session": [1280, 720]}))  # fmt: skip
    monkeypatch.setattr(ro, "desktop", lambda: (1920, 1080))
    assert ro.region_for("taskbar") == (1660, 1032, 170, 48)
    assert ro.region_for("taskbar_client_icon") == (910, 1036, 38, 40)
    seen: dict[str, Any] = {}
    monkeypatch.setattr(ro, "grab_after", lambda s, region, after: seen.setdefault("r", region))
    monkeypatch.setattr(ro, "grey_thumb", lambda img: np.zeros((2, 2), np.float32))
    ro.calibrate(SCREEN_GRAB, "taskbar", [1660, 1032, 170, 48])
    saved = json.loads(ro.signature_path("taskbar").with_suffix(".json").read_text())
    assert saved == {"box": [1660, 1032, 170, 48], "session": [1920, 1080]}


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


def test_on_an_unmeasured_size_a_login_dialog_is_found_and_moves_its_points(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase 2: at 1920x1080 the service dialog is FOUND (here at its 1080p place, the vector
    (320, 225) measured 2026-11-18); its check box and its OK point move by that vector, and the
    server list's OK takes the same one; a dialog not found yet stops instead of guessing."""
    from poring_backend.signature import grey_thumb

    monkeypatch.setattr(ro, "real_game_region", lambda: (0, 0, 1920, 1080))
    monkeypatch.setattr(ro, "desktop", lambda: (1920, 1080))
    blocks = np.random.default_rng(9).integers(0, 255, (8, 36, 4), dtype=np.uint8)
    dialog = np.ascontiguousarray(np.repeat(np.repeat(blocks, 8, 0), 8, 1)[:60, :281])
    np.save(ro.signature_path("service_select"), grey_thumb(dialog))
    ro.signature_path("service_select").with_suffix(".json").write_text(
        json.dumps({"box": [505, 371, 281, 60]}))  # fmt: skip
    frame = np.zeros((1080, 1920, 4), np.uint8)
    frame[596 : 596 + 60, 825 : 825 + 281] = dialog
    monkeypatch.setattr(ro, "grab_after", lambda s, region, after: frame[
        region[1] : region[1] + region[3], region[0] : region[0] + region[2]])  # fmt: skip
    ro._VECTORS.clear()
    with pytest.raises(ro.Stop, match="not found"):
        ro.layout("service_ok")
    assert ro.distance(None, "service_select") == 0.0
    assert ro._VECTORS["service_select"] == (320, 225)
    assert ro.region_for("service_select") == (825, 596, 281, 60)
    assert ro.layout("service_ok") == (714 + 320, 555 + 225)
    assert ro.layout("server_ok") == ro.layout("service_ok")
    monkeypatch.setattr(ro, "real_game_region", lambda: (80, 77, 1280, 720))
    assert ro.region_for("service_select") == (585, 448, 281, 60)  # measured: no vector


# --- the virtual 1280x720 client (phase 2, milestone 4) ------------------------------------------


def raw_screen(ro: ModuleType, frame: np.ndarray) -> Any:
    """A Screen whose raw grabs are crops of one synthetic real frame (the virtual ones are the
    real Screen's code, which grabs the real client through the same method)."""

    class Raw(ro.Screen):  # type: ignore[misc,name-defined]
        def __init__(self) -> None:
            self.frame = frame

        def grab_meta(self, x: int, y: int, w: int, h: int) -> Any:
            if x >= ro.VIRTUAL_X0:
                return super().grab_meta(x, y, w, h)
            return 7, np.ascontiguousarray(self.frame[y : y + h, x : x + w]), 42, "bus"

    return Raw()


def test_a_1080p_client_is_seen_and_driven_through_the_virtual_one(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """At 1920x1080 the code built on 1280x720 gets the virtual client: its region at the far
    origin, pointer positions mapped by the measured vectors (the world x1.5 about the centre, the
    saved panels as they are, the minimap +640), grabs cut from the virtual frame."""
    monkeypatch.setattr(ro, "real_game_region", lambda: (0, 0, 1920, 1080))
    monkeypatch.setattr(ro, "desktop", lambda: (1920, 1080))
    monkeypatch.setattr(ro, "_POINTER", None)
    vx0 = ro.VIRTUAL_X0
    assert ro.virtual_active() and ro.game_region() == (vx0, 0, 1280, 720)
    assert ro.fullscreen()  # decided on the REAL region
    assert ro.real_xy(vx0 + 700, 300) == (1050, 450)  # the world: 960 + 1.5 * 60, 540 - 1.5 * 60
    assert ro.real_xy(vx0 + 10, 10) == (10, 10)  # Basic Info: its saved pixels
    assert ro.real_xy(vx0 + 1200, 50) == (1840, 50)  # the minimap: the top-right corner's vector
    assert ro.real_xy(37, 530) == (37, 530)  # a desktop pixel (an icon): as is
    # the runner's raw double-click normalises a virtual pixel by the desktop: mapped in send
    ev = {"type": "mouse_button", "x": (vx0 + 700) / 1920, "y": 300 / 1080, "action": "down"}
    out = ro.virtual_event(ev)
    assert (round(out["x"] * 1920), round(out["y"] * 1080)) == (1050, 450)
    assert ro.virtual_event({"type": "key", "code": "F1"}) == {"type": "key", "code": "F1"}
    # a grab at the far origin is the virtual frame: the world shrunk back, the panels in place
    yy, xx = np.mgrid[0:1080, 0:1920]
    frame = np.dstack([xx % 256, yy % 256, (xx // 256) * 16, np.full_like(xx, 255)]).astype(
        np.uint8
    )
    frame[0:150, 0:230] = (11, 11, 11, 255)  # Basic Info
    fake = raw_screen(ro, frame)
    t, crop, fid, path = fake.grab_meta(vx0 + 0, 0, 230, 150)
    assert (t, fid, path) == (7, 42, "bus") and (crop[..., :3] == 11).all()
    _, world, _, _ = fake.grab_meta(vx0 + 700, 300, 1, 1)
    assert tuple(world[0, 0]) == tuple(frame[450, 1050])
    monkeypatch.setattr(ro, "real_game_region", lambda: (80, 77, 1280, 720))
    monkeypatch.setattr(ro, "desktop", lambda: (1440, 900))
    assert not ro.virtual_active() and ro.game_region() == (80, 77, 1280, 720)  # the lab window


def test_the_pointer_s_own_picture_is_pasted_unscaled_over_the_world(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ro, "real_game_region", lambda: (0, 0, 1920, 1080))
    monkeypatch.setattr(ro, "desktop", lambda: (1920, 1080))
    monkeypatch.setattr(ro, "_POINTER", None)
    ro.real_xy(ro.VIRTUAL_X0 + 700, 300)  # the pointer went there
    view = ro.client_view()
    cursor = [p for p in view.panels if p.name == "cursor"]
    assert cursor and cursor[0].virtual[:2] == (688, 288) and cursor[0].real_xy == (1038, 438)
    ro.real_xy(ro.VIRTUAL_X0 + 10, 10)  # over Basic Info: the panel itself carries it
    assert not [p for p in ro.client_view().panels if p.name == "cursor"]


def test_the_login_dialogs_stay_in_real_pixels_under_the_virtual_client(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ro, "real_game_region", lambda: (0, 0, 1920, 1080))
    monkeypatch.setattr(ro, "desktop", lambda: (1920, 1080))
    ro._VECTORS.clear()
    ro._VECTORS["service_select"] = (320, 225)
    np.save(ro.signature_path("service_select"), np.zeros((8, 36), np.float32))
    ro.signature_path("service_select").with_suffix(".json").write_text(
        json.dumps({"box": [505, 371, 281, 60]}))  # fmt: skip
    assert ro.layout("service_ok") == (714 + 320, 555 + 225)  # real, never at the far origin
    assert ro.region_for("service_select") == (825, 596, 281, 60)
