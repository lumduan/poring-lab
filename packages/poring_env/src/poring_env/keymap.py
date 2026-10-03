"""KeyboardEvent.code -> Linux evdev code -> X keycode.

``KeyboardEvent.code`` names a *physical* key position, independent of the browser's keyboard
layout. Xvfb's default XKB keycode set is ``evdev``, where X keycode = Linux input-event code + 8,
and xfreerdp maps those keycodes to RDP scancodes. So a physical key travels browser -> X -> RDP ->
Windows without any keysym lookup, and the Windows side applies its own layout (ADR-0003).

Left/Right Meta (the Windows key) are mapped so the console's toolbar can send Win; the browser
never forwards a *physical* Meta press (that belongs to the viewer's own OS). See ADR-0002.
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
    "MetaLeft": 125,
    "MetaRight": 126,
    "ContextMenu": 127,
}

EVDEV_TO_X11_OFFSET = 8

# KeyboardEvent.code -> Windows virtual-key code, as Moonlight-qt 6.1.0 sends them (keyboard.cpp):
# the S2 path's input socket (s2-plan section 4) sends VKs by PHYSICAL position; Sunshine turns
# each back into a US-layout scancode, so Windows applies ITS layout (Thai Kedmanee included).
# The source of truth: services/gamestream/s2spike/vk.py keeps a byte-equal copy (drift-tested;
# that image has no poring_env).
VK_BY_CODE: dict[str, int] = {
    **{f"Key{c}": 0x41 + i for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")},
    **{f"Digit{d}": 0x30 + d for d in range(10)},
    **{f"F{n}": 0x70 + n - 1 for n in range(1, 13)},
    **{f"Numpad{d}": 0x60 + d for d in range(10)},
    "Escape": 0x1B,
    "Minus": 0xBD,
    "Equal": 0xBB,
    "Backspace": 0x08,
    "Tab": 0x09,
    "BracketLeft": 0xDB,
    "BracketRight": 0xDD,
    "Enter": 0x0D,
    "NumpadEnter": 0x0D,  # Moonlight-qt sends VK_RETURN for both ("FIXME: Is this correct?")
    "ControlLeft": 0xA2,
    "ControlRight": 0xA3,
    "Semicolon": 0xBA,
    "Quote": 0xDE,
    "Backquote": 0xC0,
    "ShiftLeft": 0xA0,
    "ShiftRight": 0xA1,
    "Backslash": 0xDC,
    "IntlBackslash": 0xE2,
    "Comma": 0xBC,
    "Period": 0xBE,
    "Slash": 0xBF,
    "NumpadMultiply": 0x6A,
    "NumpadAdd": 0x6B,
    "NumpadSubtract": 0x6D,
    "NumpadDecimal": 0x6E,
    "NumpadDivide": 0x6F,
    "AltLeft": 0xA4,
    "AltRight": 0xA5,
    "Space": 0x20,
    "CapsLock": 0x14,
    "NumLock": 0x90,
    "ScrollLock": 0x91,
    "PrintScreen": 0x2C,
    "Pause": 0x13,
    "Home": 0x24,
    "End": 0x23,
    "PageUp": 0x21,
    "PageDown": 0x22,
    "Insert": 0x2D,
    "Delete": 0x2E,
    "ArrowLeft": 0x25,
    "ArrowUp": 0x26,
    "ArrowRight": 0x27,
    "ArrowDown": 0x28,
    "MetaLeft": 0x5B,
    "MetaRight": 0x5C,
    "ContextMenu": 0x5D,
}

CONTROL_CODES = frozenset({"ControlLeft", "ControlRight"})
ALT_CODES = frozenset({"AltLeft", "AltRight"})
SHIFT_CODES = frozenset({"ShiftLeft", "ShiftRight"})
META_CODES = frozenset({"MetaLeft", "MetaRight"})


class UnknownKeyCode(ValueError):
    """The KeyboardEvent.code has no mapping (or is deliberately excluded)."""


def is_known(code: str) -> bool:
    return code in EVDEV_BY_CODE


def windows_vk(code: str) -> int:
    try:
        return VK_BY_CODE[code]
    except KeyError:
        raise UnknownKeyCode(code) from None


def x11_keycode(code: str) -> int:
    """X keycode for a KeyboardEvent.code under Xvfb's default evdev keycode set."""
    try:
        return EVDEV_BY_CODE[code] + EVDEV_TO_X11_OFFSET
    except KeyError:
        raise UnknownKeyCode(code) from None


def typescript_module() -> str:
    """The frontend's copy of the known codes (services/frontend/src/lib/keycodes.gen.ts)."""
    codes = "\n".join(f'  "{code}",' for code in EVDEV_BY_CODE)
    return (
        "/* GENERATED by scripts/gen_protocol.sh from poring_env.keymap.EVDEV_BY_CODE. "
        "DO NOT EDIT. */\n"
        "\n"
        "/** KeyboardEvent.code values the backend can inject (anything else is dropped). */\n"
        f"export const KNOWN_CODES = [\n{codes}\n] as const;\n"
        "\n"
        "export type KnownCode = (typeof KNOWN_CODES)[number];\n"
    )
