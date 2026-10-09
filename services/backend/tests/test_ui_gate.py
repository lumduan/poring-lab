"""scripts/ui_gate.py (Batt 2026-10-09, walk@17 item 6): the pure decision -- no Enter into an
unknown state; only a dialog showing CLOSE (no menu) is closed by Enter, a window by its chord;
NEXT, a menu, an unreadable or unstable state stop -- and the home-box window check."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[2].parent / "scripts"


@pytest.fixture(scope="module")
def ug() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("ui_gate", SCRIPTS / "ui_gate.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ui_gate"] = mod
    spec.loader.exec_module(mod)
    return mod


def obs(ok: bool = True, dialog: Any = None, menu: Any = None, windows: tuple[str, ...] = (),
        sig: str = "s", reason: str = "ok") -> dict[str, Any]:  # fmt: skip
    npc: dict[str, Any] = {"ok": ok, "reason": reason, "sig": sig}
    if dialog is not None:
        npc["dialog"] = {"button": dialog}
    if menu is not None:
        npc["menu"] = menu
    return {"npc": npc, "windows": list(windows)}


def test_clear_only_when_both_frames_agree_and_nothing_is_open(ug: Any) -> None:
    assert ug.decide(obs(), obs()) == {"do": "clear"}
    assert ug.decide(obs(sig="a"), obs(sig="b"))["why"] == "unstable"
    assert ug.decide(obs(windows=("inventory",)), obs())["why"] == "unstable"
    assert ug.decide(obs(ok=False, reason="button_unknown"), obs())["why"] == (
        "npc_unreadable:button_unknown"
    )


def test_only_a_close_button_is_closed_by_enter(ug: Any) -> None:
    assert ug.decide(obs(dialog="close"), obs(dialog="close")) == {"do": "enter_close"}
    assert ug.decide(obs(dialog="next"), obs(dialog="next"))["why"] == "npc_dialog_open:next"
    assert ug.decide(obs(dialog=None, menu={}), obs(menu={}))["why"] == "npc_menu_open"
    both = obs(dialog="close", menu={})
    assert ug.decide(both, both)["why"] == "npc_menu_open"  # a menu is never closed by Enter
    blank = {"npc": {"ok": True, "reason": "ok", "sig": "s", "dialog": {"button": None}},
             "windows": []}  # fmt: skip
    assert ug.decide(blank, blank)["why"] == "npc_dialog_open:no_button"


def test_a_window_is_closed_by_its_chord_after_the_npc_check(ug: Any) -> None:
    two = obs(windows=("skills", "inventory"))
    assert ug.decide(two, two) == {"do": "chord", "window": "inventory"}
    mixed = obs(dialog="next", windows=("inventory",))
    assert ug.decide(mixed, mixed)["do"] == "stop"  # the dialog first: never a key into it


def test_a_window_is_seen_only_at_its_home(ug: Any) -> None:
    from poring_env import ui_anchors as ua

    rng = np.random.default_rng(3)
    tmpl = rng.integers(0, 255, (20, 30)).astype(np.float32)
    spec = SimpleNamespace(template_offset=(0, 0), max_distance=4.0)
    reg = SimpleNamespace(windows={w: spec for w in ug.WINDOWS4},
                          templates={"inventory": tmpl}, masks={})  # fmt: skip
    hx, hy = ua.CAPTURE_ORIGINS["inventory"]
    frame = np.full((720, 1280, 3), 40, np.uint8)
    for dx, want in ((5, ["inventory"]), (ug.HOME_PX + 25, [])):
        f = frame.copy()
        f[hy : hy + 20, hx + dx : hx + dx + 30] = tmpl.astype(np.uint8)[..., None]
        assert ug.windows_at_home(f, reg) == want, dx
