"""Shared fakes for the backend tests."""

import os
import threading
from collections.abc import Callable
from typing import Any

import pytest

from poring_backend.clipboard import ConvertRequest, OwnerChanged, OwnershipLost, SelectionEvent


class FakeXfreerdp:
    """SelectionIO whose 'X server' holds one other client: xfreerdp in text-to-remote mode. It
    asks the new owner for TARGETS whenever ownership changes, and for UTF8_STRING on Ctrl+V."""

    WINDOW = 0x100
    RDP_HELPER = 0xC00005  # xfreerdp's cliprdr window: no WM_CLASS of its own, same client base
    CLASSES = {RDP_HELPER: "xfreerdp"}

    def __init__(self, *, listening: bool = True) -> None:
        self.listening = listening
        self._r, self._w = os.pipe()
        os.set_blocking(self._r, False)
        self._lock = threading.Lock()
        self._pending: list[SelectionEvent] = []
        self.current_owner = 0
        self.history: list[str] = []
        self.replies: list[tuple[str, object]] = []

    def push(self, *events: SelectionEvent) -> None:
        with self._lock:
            self._pending.extend(events)
        os.write(self._w, b"x")

    def ctrl_v(self) -> None:
        self.push(ConvertRequest("UTF8_STRING"))

    def take_by_foreign(self, owner: int) -> None:
        was_ours = self.current_owner == self.WINDOW
        self.current_owner = owner
        self.push(*([OwnershipLost()] if was_ours else []), OwnerChanged(owner))

    # --- SelectionIO ---
    @property
    def window(self) -> int:
        return self.WINDOW

    def fileno(self) -> int:
        return self._r

    def own(self) -> bool:
        self.current_owner = self.WINDOW
        self.history.append("own")
        if self.listening:
            self.push(OwnerChanged(self.WINDOW), ConvertRequest("TARGETS"))
        return True

    def release(self) -> None:
        if self.current_owner == self.WINDOW:
            self.current_owner = 0
            self.history.append("release")

    def owner(self) -> int:
        return self.current_owner

    def owner_class(self, window: int) -> str | None:
        return self.CLASSES.get(window)

    def events(self) -> list[SelectionEvent]:
        try:
            while os.read(self._r, 4096):
                pass
        except BlockingIOError:
            pass
        with self._lock:
            out, self._pending = self._pending, []
        return out

    def reply_targets(self, request: ConvertRequest, targets: tuple[str, ...]) -> None:
        self.replies.append(("targets", targets))

    def reply_data(self, request: ConvertRequest, data: bytes) -> None:
        self.replies.append(("data", data))

    def refuse(self, request: ConvertRequest) -> None:
        self.replies.append(("refuse", request.target))

    def close(self) -> None:
        os.close(self._r)
        os.close(self._w)


@pytest.fixture
def make_xfreerdp() -> Callable[..., Any]:
    """Factory for FakeXfreerdp (a fixture, because --import-mode=importlib forbids importing
    conftest). Instances are SelectionIO implementations."""
    fakes: list[FakeXfreerdp] = []

    def factory(*, listening: bool = True) -> FakeXfreerdp:
        fake = FakeXfreerdp(listening=listening)
        fakes.append(fake)
        return fake

    return factory
