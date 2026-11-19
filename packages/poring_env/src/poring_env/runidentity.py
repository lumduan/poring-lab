"""Who may play a Run: the Settings page's store (Batt 2026-11-19, ADR-0020 Amendment R).

Batt: "make any the default, this machine too, and settable in Settings; the character names set
in Settings -- .env is hard for a new user (a restart); on Settings, Save and it works at once";
the "Remember this character" button "in Settings too".

The store is ONE file of the human-only settings store, ``settings/run-identity.json``:

    {"v": 1, "revision": 3, "mode": "any" | "known" | "mine",
     "characters": [{"id": "c_1a2b3c4d", "name": "Rogue76bd", "remembered": "<ISO time>",
                     "w": 116, "h": 14, "rgb": "<base64 of h*w*3 bytes, row by row>"}]}

- WRITER: the backend only (routes_identity.py), on a person's Save from a LAN browser
  (routes_settings.write_gate: the console's Origin, the CSRF token, never the lab host or the
  Windows host). A character's name-line picture ("plate") is cut ONLY when a person presses
  Remember (the Run helper reads the screen once, crusader.py plate); nothing cuts one by itself.
- READERS: the Run's checks on the host (crusader.check, db=False), every time they run, so a
  Save applies to the next check or Run without a restart.
- NO FILE = the default: ``any`` with no character (every install, the lab too).
- A file that does not parse is NOT the default: a Run's identity line fails with the words
  (fail closed: a broken file never loosens a "known" back to "any").

This module is pure (stdlib only): the format, its limits and its checks, shared by the backend
and the host scripts so the two cannot drift.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

FILE_NAME = "run-identity.json"
VERSION = 1
MODES = ("any", "known", "mine")
DEFAULT_MODE = "any"  # Batt 2026-11-19: every install's default, the lab's too
MAX_CHARACTERS = 50
MAX_NAME = 24  # RO names are at most 23 bytes; a person's label may be a little longer
# The name line Basic Info draws (crusader.NAME_BOX: x 4-120, y 22-36 of the 1280x720 client)
PLATE_W = 116
PLATE_H = 14
ID_RE = re.compile(r"c_[0-9a-f]{8}")


@dataclass(frozen=True)
class Character:
    id: str
    name: str
    remembered: str
    w: int
    h: int
    rgb: bytes  # h*w*3 bytes, row by row

    def as_json(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "remembered": self.remembered, "w": self.w,
                "h": self.h, "rgb": base64.b64encode(self.rgb).decode("ascii")}  # fmt: skip


@dataclass(frozen=True)
class Store:
    revision: int = 0
    mode: str = DEFAULT_MODE
    characters: tuple[Character, ...] = field(default_factory=tuple)

    def as_json(self) -> dict[str, Any]:
        return {"v": VERSION, "revision": self.revision, "mode": self.mode,
                "characters": [c.as_json() for c in self.characters]}  # fmt: skip

    def names(self) -> list[str]:
        return [c.name for c in self.characters]


DEFAULT = Store()


def name_problem(name: Any) -> str | None:
    """PURE: why this is not a usable character name (None: it is). Any script (Thai, Korean,
    ...): the name is a label a person types; the bot compares the name line's PICTURE."""
    if not isinstance(name, str):
        return "name_missing"
    if not name.strip():
        return "name_empty"
    if name != name.strip():
        return "name_spaces_at_ends"
    if len(name) > MAX_NAME:
        return "name_too_long"
    if any(unicodedata.category(ch).startswith("C") for ch in name):
        return "name_control_character"
    return None


def same_name(a: str, b: str) -> bool:
    return a.casefold() == b.casefold()


def mode_problem(mode: Any) -> str | None:
    return None if mode in MODES else "mode_unknown"


def _character(raw: Any) -> Character | str:
    if not isinstance(raw, dict):
        return "a character is not an object"
    if set(raw) != {"id", "name", "remembered", "w", "h", "rgb"}:
        return "a character has missing or extra fields"
    cid, name, when, w, h, rgb = (raw[k] for k in ("id", "name", "remembered", "w", "h", "rgb"))
    if not isinstance(cid, str) or not ID_RE.fullmatch(cid):
        return "a character id is malformed"
    why = name_problem(name)
    if why is not None:
        return f"character {cid}: {why}"
    if not isinstance(when, str) or len(when) > 40:
        return f"character {cid}: its time is malformed"
    if not all(isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 512 for v in (w, h)):
        return f"character {cid}: its size is malformed"
    if not isinstance(rgb, str):
        return f"character {cid}: its picture is malformed"
    try:
        data = base64.b64decode(rgb, validate=True)
    except (binascii.Error, ValueError):
        return f"character {cid}: its picture is not base64"
    if len(data) != w * h * 3:
        return f"character {cid}: its picture is not {w}x{h} RGB"
    return Character(id=cid, name=name, remembered=when, w=w, h=h, rgb=data)


def parse(text: str) -> Store | str:
    """PURE: the store, or why the file is not one (the words a Run's check shows)."""
    try:
        raw = json.loads(text)
    except ValueError:
        return "not JSON"
    if not isinstance(raw, dict):
        return "not an object"
    if raw.get("v") != VERSION:
        return f"version {raw.get('v')!r} (this install reads {VERSION})"
    if set(raw) != {"v", "revision", "mode", "characters"}:
        return "missing or extra fields"
    rev = raw["revision"]
    if isinstance(rev, bool) or not isinstance(rev, int) or rev < 0:
        return "the revision is malformed"
    if mode_problem(raw["mode"]) is not None:
        return f"the mode {raw['mode']!r} is none of {', '.join(MODES)}"
    chars = raw["characters"]
    if not isinstance(chars, list) or len(chars) > MAX_CHARACTERS:
        return f"the characters are not a list of at most {MAX_CHARACTERS}"
    out: list[Character] = []
    for c in chars:
        got = _character(c)
        if isinstance(got, str):
            return got
        if any(o.id == got.id for o in out):
            return f"character id {got.id} twice"
        if any(same_name(o.name, got.name) for o in out):
            return f"the name {got.name!r} twice"
        out.append(got)
    return Store(revision=rev, mode=raw["mode"], characters=tuple(out))


def dumps(store: Store) -> str:
    return json.dumps(store.as_json(), ensure_ascii=False, indent=1) + "\n"


def plate_problem(w: Any, h: Any, rgb: Any) -> str | None:
    """PURE: a name line the Run helper cut is usable (its size and its bytes)."""
    if (w, h) != (PLATE_W, PLATE_H):
        return f"the name line is {w}x{h}, not {PLATE_W}x{PLATE_H}"
    if not isinstance(rgb, str):
        return "the name line has no picture"
    try:
        data = base64.b64decode(rgb, validate=True)
    except (binascii.Error, ValueError):
        return "the name line's picture is not base64"
    if len(data) != PLATE_W * PLATE_H * 3:
        return "the name line's picture has the wrong size"
    return None
