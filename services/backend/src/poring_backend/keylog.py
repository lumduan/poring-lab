"""What the input log may keep of a person's typing (Batt 2026-11-18 ~22:3x: "the input log keeps
no character people type at all, only the number of keys"; a public project, and other people's
secrets must never land in a file of ours).

A key whose ``KeyboardEvent.code`` puts a CHARACTER into a text field is logged without its code
(its action and timing stay, so the count does); a control key (Alt, Tab, Escape, Enter, the
F-keys, the arrows, Backspace) keeps its code -- it types no character, and it is how a person's
Alt+Tab is found afterwards. ``scripts/purge_input_log.py`` removes the same keys from old logs.
"""

from __future__ import annotations

import re

# KeyboardEvent.code values that put a character into a text field.
PRINTABLE = re.compile(
    r"^(Key[A-Z]|Digit[0-9]|Numpad([0-9]|Decimal|Divide|Multiply|Subtract|Add|Comma|Equal)"
    r"|Space|Minus|Equal|BracketLeft|BracketRight|Backslash|Semicolon|Quote|Backquote|Comma"
    r"|Period|Slash|Intl[A-Za-z]+)$"
)


def is_printable(code: str) -> bool:
    """PURE: the key types a character (its code is never logged for a person)."""
    return PRINTABLE.match(code) is not None
