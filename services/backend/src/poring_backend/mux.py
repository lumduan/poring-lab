"""Input mux: the ONLY path from any input source to XTest (ADR-0002).

A pure state machine -- no I/O, clock injected -- so every rule below is unit-tested.

Modes
  HUMAN   only human input passes.
  BOT     only bot input passes.
  ASSIST  human input always passes and takes a *lease*; bot input passes only while no lease is
          active. The lease lasts ``lease_ns`` after the last human event and, beyond that, for as
          long as the human holds any key or button.

Handoffs
  Whenever a source loses control (mode switch, or a human taking the lease in ASSIST) the mux
  emits synthetic releases for every key/button that source still holds, so nothing stays stuck
  down -- e.g. the bot mid right-drag when the human grabs the mouse.

Reserved chords
  Ctrl+Alt+D and Ctrl+Alt+Enter are xfreerdp client hotkeys (disconnect / fullscreen toggle). They
  would act on the ONE RDP session itself, so they are never delivered.

Paste chords (ADR-0004)
  The clipboard is a human-only tool. The bot may never press Ctrl+V, Meta+V (Windows clipboard
  history) or Shift+Insert -- in either key order, because X autorepeats a held XTest key, so
  "hold V, then press Ctrl" pastes too. The human is unaffected.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from poring_env.keymap import ALT_CODES, CONTROL_CODES, META_CODES, SHIFT_CODES, is_known
from poring_env.protocol import (
    NO_FRAME,
    InputEvent,
    Key,
    Mode,
    MouseButton,
    ReleaseAll,
)

RESERVED_CHORD_KEYS = frozenset({"KeyD", "Enter", "NumpadEnter"})

# key -> the modifiers that turn it into a paste (ADR-0004). Checked in both key orders.
PASTE_CHORDS: dict[str, frozenset[str]] = {
    "KeyV": CONTROL_CODES | META_CODES,
    "Insert": SHIFT_CODES,
}

ButtonName = Literal["left", "middle", "right"]


class Source(StrEnum):
    HUMAN = "human"
    BOT = "bot"


_ALLOWED: dict[Mode, frozenset[Source]] = {
    Mode.HUMAN: frozenset({Source.HUMAN}),
    Mode.BOT: frozenset({Source.BOT}),
    Mode.ASSIST: frozenset({Source.HUMAN, Source.BOT}),
}


@dataclass(frozen=True, slots=True)
class Routed:
    """One event to inject, with provenance for the input log."""

    source: Source
    event: InputEvent
    synthetic: bool
    reason: str


@dataclass(frozen=True, slots=True)
class Decision:
    accepted: bool
    reason: str
    inject: tuple[Routed, ...] = ()


class InputMux:
    def __init__(self, *, lease_ns: int, mode: Mode = Mode.HUMAN) -> None:
        self._lease_ns = lease_ns
        self._mode = mode
        self._keys: dict[Source, set[str]] = {s: set() for s in Source}
        self._buttons: dict[Source, set[ButtonName]] = {s: set() for s in Source}
        self._last_human_ns: int | None = None

    # --- queries ----------------------------------------------------------------------------------

    @property
    def mode(self) -> Mode:
        return self._mode

    def holds_anything(self, source: Source) -> bool:
        return bool(self._keys[source] or self._buttons[source])

    def held(self, source: Source) -> tuple[frozenset[str], frozenset[str]]:
        """(keys, buttons) currently held by ``source``."""
        return frozenset(self._keys[source]), frozenset(self._buttons[source])

    def lease_active(self, now_ns: int) -> bool:
        if self._mode is not Mode.ASSIST:
            return False
        if self.holds_anything(Source.HUMAN):
            return True
        return self._last_human_ns is not None and now_ns < self._last_human_ns + self._lease_ns

    def lease_until_ns(self, now_ns: int) -> int | None:
        """When the ASSIST human lease ends if the human does nothing more; None = no lease."""
        if not self.lease_active(now_ns):
            return None
        if self.holds_anything(Source.HUMAN):
            return now_ns + self._lease_ns
        assert self._last_human_ns is not None
        return self._last_human_ns + self._lease_ns

    # --- transitions ------------------------------------------------------------------------------

    def set_mode(self, mode: Mode, now_ns: int) -> tuple[Routed, ...]:
        """Switch mode; returns releases for every source that loses control."""
        if mode is self._mode:
            return ()
        released: list[Routed] = []
        for source in Source:
            if source not in _ALLOWED[mode]:
                released += self._release(source, now_ns, reason="mode_release")
        self._mode = mode
        self._last_human_ns = None  # a new mode starts without a lease
        return tuple(released)

    def submit(self, source: Source, event: InputEvent, now_ns: int) -> Decision:
        if isinstance(event, Key) and not is_known(event.code):
            return Decision(False, "unknown_key_code")
        if source not in _ALLOWED[self._mode]:
            return Decision(False, f"mode={self._mode}")
        if source is Source.BOT and self.lease_active(now_ns):
            return Decision(False, "human_lease")
        if self._is_reserved_chord(source, event):
            return Decision(False, "reserved_chord")
        if source is Source.BOT and self._is_paste_chord(source, event):
            return Decision(False, "paste_chord_bot")

        inject: list[Routed] = []
        if source is Source.HUMAN and self._mode is Mode.ASSIST:
            # The human takes (or keeps) the lease: the bot lets go of everything first.
            inject += self._release(Source.BOT, now_ns, reason="handoff_release")
        if isinstance(event, ReleaseAll):
            inject += self._release(source, now_ns, reason="release_all")
        else:
            self._track(source, event)
            inject.append(Routed(source, event, synthetic=False, reason="ok"))
        if source is Source.HUMAN:
            self._last_human_ns = now_ns
        return Decision(True, "ok", tuple(inject))

    # --- internals --------------------------------------------------------------------------------

    def _is_reserved_chord(self, source: Source, event: InputEvent) -> bool:
        if not (isinstance(event, Key) and event.action == "down"):
            return False
        if event.code not in RESERVED_CHORD_KEYS:
            return False
        keys = self._keys[source]
        return bool(keys & CONTROL_CODES) and bool(keys & ALT_CODES)

    def _is_paste_chord(self, source: Source, event: InputEvent) -> bool:
        if not (isinstance(event, Key) and event.action == "down"):
            return False
        keys = self._keys[source]
        modifiers = PASTE_CHORDS.get(event.code)
        if modifiers is not None and keys & modifiers:
            return True
        # The other order: a modifier going down while the paste key is already held.
        return any(event.code in mods and key in keys for key, mods in PASTE_CHORDS.items())

    def _track(self, source: Source, event: InputEvent) -> None:
        if isinstance(event, Key):
            if event.action == "down":
                self._keys[source].add(event.code)
            else:
                self._keys[source].discard(event.code)
        elif isinstance(event, MouseButton):
            if event.action == "down":
                self._buttons[source].add(event.button)
            else:
                self._buttons[source].discard(event.button)

    def _release(self, source: Source, now_ns: int, *, reason: str) -> list[Routed]:
        routed: list[Routed] = [
            Routed(
                source,
                Key(t_mono_ns=now_ns, frame_id=NO_FRAME, code=code, action="up"),
                synthetic=True,
                reason=reason,
            )
            for code in sorted(self._keys[source])
        ]
        routed += [
            Routed(
                source,
                MouseButton(t_mono_ns=now_ns, frame_id=NO_FRAME, button=button, action="up"),
                synthetic=True,
                reason=reason,
            )
            for button in sorted(self._buttons[source])
        ]
        self._keys[source].clear()
        self._buttons[source].clear()
        return routed
