"""scripts/chat_cue.py (loot@1 P5): the "item obtained" chat line from pixels. The cue is the NEWEST
line, cyan, whose leading glyphs match the "got" mask (not the "dropped" one), on a chat area whose
TEXT changed. Synthetic glyph blocks stand in for the client's text (client pixels are never
committed)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
CYAN, GREEN, SCENE = (0, 255, 255), (0, 255, 0), (120, 100, 90)
sys.path.insert(0, str(SCRIPTS))

import chat_window as cw  # noqa: E402


@pytest.fixture(autouse=True)
def frozen_layout(monkeypatch: pytest.MonkeyPatch) -> None:
    """These frames draw the FROZEN layout (chat_window.LEGACY), as recorded before 2026-11-05."""
    monkeypatch.setenv(cw.ENV, "legacy")


@pytest.fixture(scope="module")
def cc() -> ModuleType:
    spec = importlib.util.spec_from_file_location("chat_cue", SCRIPTS / "chat_cue.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def frame(lines: list[tuple[tuple[int, int, int], list[int]]], shift: int = 0,
          g: Any = cw.LEGACY) -> np.ndarray:  # fmt: skip
    """A client frame (RGB): the chat area of the chat window ``g`` with text lines bottom-up
    (newest LAST); each line is a colour and the x positions of 3-px glyph bars. ``shift`` moves
    the scene behind it. The frozen layout's rows: area 545..600, the input box's border 596..598,
    the arrows 548..592, the newest line's bottom 590 (inside the cue area, y < 593)."""
    t, b = g.text_top, g.bottom
    img = np.zeros((720, 1280, 3), np.uint8)
    img[...] = SCENE
    img[t : b - 24, :640] = (np.indices((b - 24 - t, 640)).sum(0)[..., None] * 7 + shift) % 60 + 40
    img[b - 28 : b - 26, :640] = 255  # the input box's white border (outside the message lines)
    img[t + 3 : b - 32, 585:595] = 255 if shift % 2 else 0  # the scrollbar's white arrows, moving
    y = b - 34  # the newest line's bottom, inside the cue area
    for colour, xs in reversed(lines):
        for x in xs:
            img[y - 9 : y, 7 + x : 10 + x] = colour
        y -= 14
    return img


GOT = [0, 6, 14, 20, 26, 34, 40]  # two words, as glyph bars
DROPPED = [0, 6, 14, 18, 22, 30, 36, 42]


@pytest.fixture
def cues(cc: ModuleType) -> dict[str, np.ndarray]:
    got, _ = cc.newest_prefix(cc.area_of(frame([(CYAN, GOT)])))
    dropped, _ = cc.newest_prefix(cc.area_of(frame([(CYAN, DROPPED)])))
    assert got is not None and dropped is not None
    return {"got": got, "dropped": dropped}


def test_a_new_got_line_is_the_cue(cc: ModuleType, cues: dict[str, np.ndarray]) -> None:
    before = frame([(GREEN, [0, 10, 20])])
    after = frame([(GREEN, [0, 10, 20]), (CYAN, GOT)], shift=13)  # the scene moved behind it
    got = cc.check(before, after, cues)
    assert got["cue"] and got["kind"] == "got", got


def test_a_dropped_line_or_a_non_cyan_newest_line_is_no_cue(cc: ModuleType,
                                                           cues: dict[str, np.ndarray]
                                                           ) -> None:  # fmt: skip
    before = frame([(GREEN, [0, 10, 20])])
    dropped = cc.check(before, frame([(GREEN, [0, 10, 20]), (CYAN, DROPPED)]), cues)
    assert not dropped["cue"] and dropped["kind"] == "dropped"
    # an @item: "got" then a green notice BELOW it -- the newest line is not the got line
    item = cc.check(before, frame([(CYAN, GOT), (GREEN, [0, 10, 20])]), cues)
    assert not item["cue"] and item["why"] == "newest_not_cyan"


def test_an_unchanged_chat_is_no_cue_even_with_the_scene_moving(cc: ModuleType,
                                                               cues: dict[str, np.ndarray]
                                                               ) -> None:  # fmt: skip
    same = [(GREEN, [0, 10, 20]), (CYAN, GOT)]
    got = cc.check(frame(same), frame(same, shift=29), cues)  # an old got line, a walk
    assert not got["cue"] and got["changed_px"] == 0, got


def test_white_scene_border_and_scrollbar_are_never_a_line(cc: ModuleType,
                                                           cues: dict[str, np.ndarray]
                                                           ) -> None:  # fmt: skip
    """2026-10-09 00:41: the input box's white border and the scrollbar read as a newer line, and
    white scene highlights counted as a change. An old got line + a walk must be no cue AND be read
    as the old got line (the right reason)."""
    same = [(GREEN, [0, 10, 20]), (CYAN, GOT)]
    before, after = frame(same), frame(same, shift=31)
    after[560:570, 300:400] = 255  # a white highlight of the scene, moving behind the window
    got = cc.check(before, after, cues)
    assert not got["cue"] and got["kind"] == "got" and got["changed_px"] < cc.CHANGED_PX, got


def test_the_cue_reads_the_chat_window_at_its_2026_11_05_standard(
    cc: ModuleType, cues: dict[str, np.ndarray], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The live default: the window docked bottom-left with 6 lines (chat_window.STANDARD). The
    same got line drawn there is the cue; read with the frozen layout's area it is not."""
    monkeypatch.setenv(cw.ENV, "standard")
    assert cc._area() == cw.STANDARD.cue_area == (0, 598, 570, 688)
    before = frame([(GREEN, [0, 10, 20])], g=cw.STANDARD)
    after = frame([(GREEN, [0, 10, 20]), (CYAN, GOT)], shift=13, g=cw.STANDARD)
    got = cc.check(before, after, cues)
    assert got["cue"] and got["kind"] == "got", got
    monkeypatch.setenv(cw.ENV, "legacy")
    assert not cc.check(before, after, cues)["cue"]
