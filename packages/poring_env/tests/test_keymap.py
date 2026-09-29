import pytest

from poring_env.keymap import EVDEV_BY_CODE, UnknownKeyCode, is_known, x11_keycode


@pytest.mark.parametrize(
    ("code", "keycode"),
    # Reference values as `xev` reports them on an evdev-keycode X server.
    [
        ("Escape", 9),
        ("KeyA", 38),
        ("KeyQ", 24),
        ("KeyZ", 52),
        ("Digit1", 10),
        ("Enter", 36),
        ("Space", 65),
        ("F1", 67),
        ("F10", 76),
        ("F11", 95),
        ("F12", 96),
        ("ArrowLeft", 113),
        ("ArrowUp", 111),
        ("ArrowRight", 114),
        ("ArrowDown", 116),
        ("ShiftLeft", 50),
        ("ControlLeft", 37),
        ("AltLeft", 64),
        ("NumpadEnter", 104),
    ],
)
def test_known_x11_keycodes(code: str, keycode: int) -> None:
    assert x11_keycode(code) == keycode


def test_no_two_codes_share_a_keycode() -> None:
    values = list(EVDEV_BY_CODE.values())
    assert len(values) == len(set(values))


@pytest.mark.parametrize("code", ["MetaLeft", "MetaRight", "KeyÄ", "", "Fn"])
def test_unmapped_codes_are_rejected(code: str) -> None:
    assert not is_known(code)
    with pytest.raises(UnknownKeyCode):
        x11_keycode(code)
