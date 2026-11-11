"""bare_steal (rogue-xmas02.md 4BX, dungeon@9.27): Batt's bare-hand steal -- the language-free steal
cues (the item popup by its frame, a new item-colour Battle Log line) and the phase's state."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def bs() -> ModuleType:
    path = ROOT / "scripts/bare_steal.py"
    spec = importlib.util.spec_from_file_location("bare_steal", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bare_steal"] = mod
    spec.loader.exec_module(mod)
    return mod


def scene(v: int = 120) -> np.ndarray:
    return np.full((720, 1280, 3), v, np.uint8)


def draw_popup(img: np.ndarray, bs: ModuleType, width: int = 188, ink: int = 40) -> np.ndarray:
    """The popup as measured on fiT14: a 2-px white border column at the left edge, a grey inner
    line, white top / bottom border rows from left + 3 (rounded corners), a white fill with an
    icon and text (dark marks; never read)."""
    x0, t, b = bs.POPUP_LEFT, bs.POPUP_TOP, bs.POPUP_BOTTOM
    x1 = x0 + width - 1
    img[t + 2 : b - 1, x0 : x0 + 2] = 255
    img[t + 2 : b - 1, x0 + 2] = 190
    img[t + 2 : b - 1, x0 + 3 : x1 - 1] = 254
    img[t, x0 + 3 : x1 - 1] = 255
    img[b, x0 + 3 : x1 - 1] = 255
    img[t + 8 : t + 22, x0 + 8 : x0 + 22] = ink  # the item's icon
    img[t + 10 : t + 20, x0 + 30 : x0 + 30 + width // 2 : 3] = ink  # its text, as strokes
    return img


def test_the_popup_is_found_by_its_frame_at_its_fixed_place(bs: ModuleType) -> None:
    for w in (150, 188, 230):
        box = bs.popup_box(draw_popup(scene(), bs, w))
        assert box is not None and box[0] == bs.POPUP_LEFT
        assert abs((box[1] - box[0] + 1) - w) <= 2
    assert bs.popup_box(scene()) is None  # no popup
    assert bs.popup_box(scene(255)) is None  # a white scene: no border column, no edges


def test_a_white_patch_elsewhere_or_without_its_edges_is_no_popup(bs: ModuleType) -> None:
    moved = scene()
    moved[bs.POPUP_TOP : bs.POPUP_BOTTOM + 1, 600:800] = 255  # white, but not at the fixed left
    assert bs.popup_box(moved) is None
    no_bottom = draw_popup(scene(), bs)
    no_bottom[bs.POPUP_BOTTOM - 1 : bs.POPUP_BOTTOM + 1] = 120  # the bottom border hidden
    assert bs.popup_box(no_bottom) is None


def test_a_popup_is_new_once_and_again_only_with_other_contents(bs: ModuleType) -> None:
    a = draw_popup(scene(), bs, 188)
    new, box, sig = bs.popup_new(None, None, a)
    assert new and box is not None and sig is not None
    jitter = draw_popup(scene(), bs, 190)  # the same popup, its right end 2 px off
    jitter[bs.POPUP_TOP + 8 : bs.POPUP_TOP + 22, bs.POPUP_LEFT + 8 : bs.POPUP_LEFT + 22] = 40
    assert not bs.popup_new(sig, box, jitter)[0]
    other = draw_popup(scene(), bs, 240, ink=150)  # another item: another icon, a longer name
    assert bs.popup_new(sig, box, other)[0]
    assert not bs.popup_new(None, None, scene())[0]


def test_the_battle_log_cue_is_a_new_line_of_the_item_colour_not_its_words(bs: ModuleType) -> None:
    lines = [{"colour": "yellow", "text": "x"}, {"colour": "cyan", "text": None}]
    assert bs.cyan_new(lines, 1)
    assert not bs.cyan_new(lines, 2)
    assert not bs.cyan_new([{"colour": "yellow"}, {"colour": "red"}], 0)


def test_the_phase_unequips_once_then_equips_on_a_cue_a_timeout_or_low_hp(bs: ModuleType) -> None:
    st = bs.BareSteal()
    assert st.engage() == "unequip"
    st.unequipped(10.0, n_lines=3, sig=None, box=None)
    assert st.engage() is None  # bare already
    quiet = [{"colour": "yellow"}] * 3
    assert st.tick(11.0, quiet, scene(), 0.9) == (None, None)
    assert st.tick(11.5, [*quiet, {"colour": "cyan"}], scene(), 0.9) == ("equip", "cyan")
    st.equipped()
    assert st.engage() is None  # this fight stole: no second bare phase
    st.fight_end()
    assert st.engage() == "unequip"  # the next target
    st.unequipped(20.0, n_lines=0, sig=None, box=None)
    assert st.tick(20.5, [], draw_popup(scene(), bs), 0.9) == ("equip", "popup")
    st.equipped()
    st.fight_end()
    st.unequipped(30.0, n_lines=0, sig=None, box=None)
    assert st.tick(30.5, [], scene(), 0.4) == ("equip", "hp")
    st.equipped()
    st.fight_end()
    st.unequipped(40.0, n_lines=0, sig=None, box=None)
    assert st.tick(40.0 + bs.BARE_MAX_S, [], scene(), 0.9) == ("equip", "time")


def test_a_popup_still_shown_from_before_the_bare_phase_is_no_cue(bs: ModuleType) -> None:
    """A loot popup from the last fight may still show when the bare phase begins: only a NEW
    one (other contents) is a steal."""
    old = draw_popup(scene(), bs, 188)
    _, box, sig = bs.popup_new(None, None, old)
    st = bs.BareSteal()
    st.unequipped(0.0, n_lines=0, sig=sig, box=box)
    assert st.tick(0.5, [], old, 0.9) == (None, None)
    assert st.tick(1.0, [], scene(), 0.9) == (None, None)  # it faded
    assert st.tick(1.5, [], old, 0.9) == ("equip", "popup")  # drawn again: a new gain


REC = Path("/mnt/poring-lab-datasets/20261111T132013-rdp-hunt-xmas02-fiT14")


@pytest.mark.skipif(not REC.exists(), reason="the p63 recording is not mounted")
def test_a_real_steal_frame_shows_the_popup_and_the_frame_before_does_not(bs: ModuleType) -> None:
    """The real case (fiT14 = p63): the first steal (a pickup_result with no pickup_request, at
    t_mono 342928646027850) is drawn on frame 61 (0.13 s later) and not on frame 60."""
    import io
    import tarfile

    from PIL import Image

    with tarfile.open(REC / "shard-000000.tar") as tf:
        before = np.asarray(Image.open(io.BytesIO(tf.extractfile("000000060.png").read()))  # type: ignore[union-attr]
                            .convert("RGB"))  # fmt: skip
        after = np.asarray(Image.open(io.BytesIO(tf.extractfile("000000061.png").read()))  # type: ignore[union-attr]
                           .convert("RGB"))  # fmt: skip
    assert bs.popup_box(after) is not None
    assert bs.popup_box(before) is None
