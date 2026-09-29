"""KeyboardEvent.code -> Linux evdev code -> X keycode.

``KeyboardEvent.code`` names a *physical* key position, independent of the browser's keyboard
layout. Xvfb's default XKB keycode set is ``evdev``, where X keycode = Linux input-event code + 8,
and xfreerdp maps those keycodes to RDP scancodes. So a physical key travels browser -> X -> RDP ->
Windows without any keysym lookup, and the Windows side applies its own layout (ADR-0003).

Left/Right Meta are deliberately absent: they open the Windows Start menu over the game.
"""

# Values from linux/input-event-codes.h.
EVDEV_BY_CODE: dict[str, int] = {
    "Escape": 1,
    "Digit1": 2,
    "Digit2": 3,
    "Digit3": 4,
    "Digit4": 5,
    "Digit5": 6,
    "Digit6": 7,
    "Digit7": 8,
    "Digit8": 9,
    "Digit9": 10,
    "Digit0": 11,
    "Minus": 12,
    "Equal": 13,
    "Backspace": 14,
    "Tab": 15,
    "KeyQ": 16,
    "KeyW": 17,
    "KeyE": 18,
    "KeyR": 19,
    "KeyT": 20,
    "KeyY": 21,
    "KeyU": 22,
    "KeyI": 23,
    "KeyO": 24,
    "KeyP": 25,
    "BracketLeft": 26,
    "BracketRight": 27,
    "Enter": 28,
    "ControlLeft": 29,
    "KeyA": 30,
    "KeyS": 31,
    "KeyD": 32,
    "KeyF": 33,
    "KeyG": 34,
    "KeyH": 35,
    "KeyJ": 36,
    "KeyK": 37,
    "KeyL": 38,
    "Semicolon": 39,
    "Quote": 40,
    "Backquote": 41,
    "ShiftLeft": 42,
    "Backslash": 43,
    "KeyZ": 44,
    "KeyX": 45,
    "KeyC": 46,
    "KeyV": 47,
    "KeyB": 48,
    "KeyN": 49,
    "KeyM": 50,
    "Comma": 51,
    "Period": 52,
    "Slash": 53,
    "ShiftRight": 54,
    "NumpadMultiply": 55,
    "AltLeft": 56,
    "Space": 57,
    "CapsLock": 58,
    "F1": 59,
    "F2": 60,
    "F3": 61,
    "F4": 62,
    "F5": 63,
    "F6": 64,
    "F7": 65,
    "F8": 66,
    "F9": 67,
    "F10": 68,
    "NumLock": 69,
    "ScrollLock": 70,
    "Numpad7": 71,
    "Numpad8": 72,
    "Numpad9": 73,
    "NumpadSubtract": 74,
    "Numpad4": 75,
    "Numpad5": 76,
    "Numpad6": 77,
    "NumpadAdd": 78,
    "Numpad1": 79,
    "Numpad2": 80,
    "Numpad3": 81,
    "Numpad0": 82,
    "NumpadDecimal": 83,
    "IntlBackslash": 86,
    "F11": 87,
    "F12": 88,
    "NumpadEnter": 96,
    "ControlRight": 97,
    "NumpadDivide": 98,
    "PrintScreen": 99,
    "AltRight": 100,
    "Home": 102,
    "ArrowUp": 103,
    "PageUp": 104,
    "ArrowLeft": 105,
    "ArrowRight": 106,
    "End": 107,
    "ArrowDown": 108,
    "PageDown": 109,
    "Insert": 110,
    "Delete": 111,
    "Pause": 119,
    "ContextMenu": 127,
}

EVDEV_TO_X11_OFFSET = 8

CONTROL_CODES = frozenset({"ControlLeft", "ControlRight"})
ALT_CODES = frozenset({"AltLeft", "AltRight"})


class UnknownKeyCode(ValueError):
    """The KeyboardEvent.code has no mapping (or is deliberately excluded)."""


def is_known(code: str) -> bool:
    return code in EVDEV_BY_CODE


def x11_keycode(code: str) -> int:
    """X keycode for a KeyboardEvent.code under Xvfb's default evdev keycode set."""
    try:
        return EVDEV_BY_CODE[code] + EVDEV_TO_X11_OFFSET
    except KeyError:
        raise UnknownKeyCode(code) from None
