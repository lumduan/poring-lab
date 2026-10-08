"""scripts/chat_cue.py (loot@1 P5): the "item obtained" chat line from pixels. The cue is the NEWEST
line, cyan, whose leading glyphs match the "got" mask (not the "dropped" one), on a chat area whose
TEXT changed. Synthetic glyph blocks stand in for the client's text (client pixels are never
committed)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
CYAN, GREEN, SCENE = (0, 255, 255), (0, 255, 0), (120, 100, 90)


@pytest.fixture(scope="module")
def cc() -> ModuleType:
    spec = importlib.util.spec_from_file_location("chat_cue", SCRIPTS / "chat_cue.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def frame(lines: list[tuple[tuple[int, int, int], list[int]]], shift: int = 0) -> np.ndarray:
    """A client frame (RGB): the chat area with text lines bottom-up (newest LAST); each line is a
    colour and the x positions of 3-px glyph bars. ``shift`` moves the scene behind it."""
    img = np.zeros((720, 1280, 3), np.uint8)
    img[...] = SCENE
    img[545:600, :640] = (np.indices((55, 640)).sum(0)[..., None] * 7 + shift) % 60 + 40
    y = 596
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
