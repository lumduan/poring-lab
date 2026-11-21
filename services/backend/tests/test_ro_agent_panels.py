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
                          {"left": 30, "text_top": 579, "bottom": 700, "lines": 6})  # fmt: skip
    assert got["basic_info"]["real_xy"] == [40, 60]
    assert got["basic_info"]["virtual"] == [0, 0, 230, 150]
    assert got["hotbar"]["real_xy"] == [496, 300]  # the lab box starts 4 px left of the origin
    assert got["chat"]["virtual"] == [0, 578, 600, 142] and got["chat"]["real_xy"] == [30, 559]
    nine = ro.panel_places(None, None, {"left": 0, "text_top": 537, "bottom": 700, "lines": 9})
    assert nine["chat"]["virtual"] == [0, 536, 600, 184]  # its own height, its bottom on 719
    assert nine["chat"]["real_xy"] == [0, 517] and set(nine) == {"chat"}
    # Batt 2026-11-19: "do not limit the width" -- a wider window keeps its own width
    wide = ro.panel_places(None, None, {"left": 10, "right": 769, "text_top": 607, "bottom": 700,
                                        "lines": 4})  # fmt: skip
    assert wide["chat"]["virtual"] == [0, 606, 763, 114] and wide["chat"]["real_xy"] == [10, 587]
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
    assert words[1].startswith("the hotbar found at (700, 600) (9 of 9") and "moved" in words[1]
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


def test_a_window_still_missing_is_searched_for_less_often(ro: ModuleType) -> None:
    """2026-11-19: Batt's hotbar was never found -- a 1.7 s search every 15 s on this host."""
    frame = frame_with(basic=(0, 0), hotbar=None)  # no hotbar, no chat
    ro._panels_tick(frame)
    assert ro._PANELS["misses"] == 0 and ro.missing_wait(ro._PANELS) == ro.PANEL_SEARCH_S
    for n in (1, 2, 3, 4):
        ro._PANELS["checked"], ro._PANELS["searched"] = 0.0, 0.0
        ro._panels_tick(frame)
        assert ro._PANELS["misses"] == n
    waits = [ro.missing_wait({"misses": m}) for m in range(6)]
    assert waits == [15.0, 30.0, 60.0, 120.0, 120.0, 120.0]
    ro._PANELS["checked"], ro._PANELS["searched"] = 0.0, 0.0
    ro._panels_tick(frame_with(basic=(0, 0), hotbar=(230, 0)))  # a new window: the clock resets
    assert ro._PANELS["misses"] == 0 and "hotbar" in ro._PANELS["found"]


def test_a_search_after_the_first_never_runs_inside_the_grab(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    monkeypatch.delenv(ro.PANEL_SEARCH_SYNC_ENV)
    release, started = threading.Event(), threading.Event()

    def slow_find(screen: Any = None, real: Any = None) -> Any:
        started.set()
        release.wait(5)
        return {}

    monkeypatch.setattr(ro, "find_panels", slow_find)
    t0 = time.monotonic()
    ro._search_again(np.zeros((4, 4, 3), np.uint8))
    ro._search_again(np.zeros((4, 4, 3), np.uint8))  # one at a time: no second thread
    assert time.monotonic() - t0 < 0.5 and started.wait(2)
    th = ro._SEARCH[0]
    assert th is not None and th.is_alive() and th.daemon
    release.set()
    th.join(5)
    assert not th.is_alive()


# --- xmas02-items-1080.md T-I5 (2026-11-20): the open inventory is a panel at 1080 ---------------
def _bag_frame(open_: bool, rows: int = 6) -> np.ndarray:
    """A 1920x1080 BGRA real frame; with ``open_`` an EMPTY 7 x ``rows`` bag at the inventory's
    home (its ovals, bag_count's rule)."""
    import bag_count as bc

    f = np.full((1080, 1920, 4), 90, np.uint8)
    if open_:
        ox, oy = (0, 120)
        ww, wh = bc.window_size(rows)
        f[oy : oy + wh, ox : ox + ww, :3] = 255
        w, h = bc.OVAL_BOX[2], bc.OVAL_BOX[3]
        yy, xx = np.mgrid[0:h, 0:w]
        oval = ((xx + 0.5 - w / 2) / (w / 2)) ** 2 + ((yy + 0.5 - h / 2) / (h / 2)) ** 2 <= 1.0
        for s in range(bc.COLS * rows):
            x, y = bc.icon_xy((ox, oy), s)
            dx, dy = bc.OVAL_BOX[0], bc.OVAL_BOX[1]
            f[y + dy : y + dy + h, x + dx : x + dx + w, :3][oval] = bc.OVAL[::-1]
    return f


class BagScreen:
    def __init__(self, frame: np.ndarray) -> None:
        self.frame, self.grabs = frame, []

    def grab_meta(self, x: int, y: int, w: int, h: int) -> tuple[int, np.ndarray, int, str]:
        self.grabs.append((x, y, w, h))
        return 0, self.frame[y : y + h, x : x + w], -1, "x11"


def test_the_open_inventory_is_a_one_to_one_panel_at_1080(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ro, "desktop", lambda: (1920, 1080))
    monkeypatch.setattr(ro, "real_game_region", lambda: (0, 0, 1920, 1080))
    monkeypatch.setattr(ro, "_INV", {"origin": None, "t": -1e9})
    import gm_state as gs

    scr = BagScreen(_bag_frame(True))
    assert ro.inventory_tick(scr, now=10.0) is True
    assert scr.grabs and scr.grabs[0][2] * scr.grabs[0][3] < 200_000  # a small box, not the frame
    view = ro.client_view()
    assert view.panel_at(*gs.slot_centre(0, 0)).name == "inventory"
    sx, sy = gs.slot_centre(3, 2)
    assert view.to_real(sx, sy) == (sx, sy)  # a slot: 1:1, where RO draws it
    wx, wy = view.to_real(*gs.DROP_AT)  # the ground: the world's scale about the centre
    assert (round(wx), round(wy)) == (round(960 + 1.5 * (gs.DROP_AT[0] - 640)),
                                      round(540 + 1.5 * (gs.DROP_AT[1] - 360)))  # fmt: skip
    # checked again only after INV_CHECK_S; then closed: the place is the world again
    scr.frame = _bag_frame(False)
    assert ro.inventory_tick(scr, now=10.1) is True  # within INV_CHECK_S: the last answer
    assert ro.inventory_tick(scr, now=10.0 + ro.INV_CHECK_S) is False
    assert ro.client_view().panel_at(*gs.slot_centre(0, 0)) is None
    # Amendment 9: before a click into the bag the look is FORCED, whatever the last one's age
    scr.frame = _bag_frame(True)
    t = 10.0 + ro.INV_CHECK_S + 0.1
    assert ro.inventory_tick(scr, now=t) is False  # within INV_CHECK_S of the closed read
    assert ro.inventory_tick(scr, now=t, force=True) is True
    assert ro.client_view().panel_at(*gs.slot_centre(0, 0)).name == "inventory"


def test_a_taller_inventory_is_a_taller_panel(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The panel is the found window's size: 7 x its rows, read from the pixels (Batt's live bag is
    7 x 9, 2026-11-21); a 7 x 6 bag's panel ends below its sixth row."""
    monkeypatch.setattr(ro, "desktop", lambda: (1920, 1080))
    monkeypatch.setattr(ro, "real_game_region", lambda: (0, 0, 1920, 1080))
    monkeypatch.setattr(ro, "_INV", {"origin": None, "t": -1e9})
    import gm_state as gs

    scr = BagScreen(_bag_frame(True, rows=9))
    assert ro.inventory_tick(scr, now=10.0) is True
    assert scr.grabs[0][2] * scr.grabs[0][3] < 200_000  # the tallest window's box, still small
    sx, sy = gs.slot_centre(3, 8)  # the ninth row
    assert ro.client_view().panel_at(sx, sy).name == "inventory"
    assert ro.client_view().to_real(sx, sy) == (sx, sy)
    scr.frame = _bag_frame(True, rows=6)
    assert ro.inventory_tick(scr, now=11.0) is True
    assert ro.client_view().panel_at(sx, sy) is None  # below a 7 x 6 bag: the world
    assert ro.client_view().panel_at(*gs.slot_centre(3, 5)).name == "inventory"


def test_the_quantity_prompt_is_found_and_mapped_one_to_one_at_1080(
    ro: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-I5: the drop's quantity prompt, native-size near the centre (measured at 1920x1080: its OK
    button at the 720 box + (320, 150)), is searched only while the bag is open and is then a
    panel: its OK box reads at its 720 place in the bot's picture."""
    import gm_state as gs

    monkeypatch.setattr(ro, "desktop", lambda: (1920, 1080))
    monkeypatch.setattr(ro, "real_game_region", lambda: (0, 0, 1920, 1080))
    monkeypatch.setattr(ro, "_INV", {"origin": None, "t": -1e9, "prompt": None})
    f = _bag_frame(True)
    ref = np.load(gs.LOOT_DIR / "prompt_ok.npy")
    bx, by, bw, bh = gs.PROMPT_OK_BOX
    g = np.clip(np.round(ref), 0, 255).astype(np.uint8)
    f[by + 150 : by + 150 + bh, bx + 320 : bx + 320 + bw, :3] = g[..., None]
    scr = BagScreen(f)
    assert ro._prompt_ok_at(scr, (0, 0, 1920, 1080)) == (bx + 320, by + 150)
    assert ro.inventory_tick(scr, now=5.0) is True
    view = ro.client_view()
    assert view.panel_at(bx + 5, by + 5).name == "prompt"
    assert view.to_real(bx, by) == (bx + 320, by + 150)
    # no prompt on the screen: none found, no panel
    scr.frame = _bag_frame(True)
    assert ro.inventory_tick(scr, now=5.0 + ro.INV_CHECK_S) is True
    assert ro.client_view().panel_at(bx + 5, by + 5) is None
