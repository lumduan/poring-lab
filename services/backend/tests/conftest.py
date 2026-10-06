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


LAB_HOST = "192.168.1.169"
LAB_AID = 2000001


def make_green(state: Any, *, aid: int = LAB_AID, window_max_s: float = 120) -> None:
    """ADR-0016 in tests: the lab allowlist plus a fresh attestation, so BOT presses may pass.
    (Without it the interlock fails closed: no config file in a test's tmp dirs.)"""
    from poring_backend.interlock import EnvironmentsConfig
    from poring_env.clock import monotonic_ns
    from poring_packets.events import Attestation

    state.interlock.config = EnvironmentsConfig.model_validate({
        "version": 1, "attestation_max_age_s": 10, "window_max_s": window_max_s,
        "environments": [{"id": "lab-rathena", "status": "allowed", "adr": "ADR-0006",
                          "windows_host": LAB_HOST, "accounts": [LAB_AID, 2000002],
                          "signals": ["lab_host", "session"]}],
    })  # fmt: skip
    state.interlock.config_error = ""
    state.interlock.win_host = LAB_HOST
    state.interlock.attested(
        Attestation(t_mono_ns=monotonic_ns(), client_ip=LAB_HOST, session_live=True, aid=aid,
                    last_packet_age_ms=100, map_conns=1, server="lab-rathena"),
        monotonic_ns(),
    )  # fmt: skip


@pytest.fixture
def green_interlock() -> Callable[..., None]:
    return make_green


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "real_foreground: run the typing-only foreground gate for real (no stand-in)"
    )


@pytest.fixture(autouse=True)
def foreground_in_front(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """The typing-only foreground gate (2026-10-06) looks at the client's title bar; the fakes'
    64x36 frames have none. Tests that are not ABOUT the gate get the client in front;
    tests/test_foreground.py (marker ``real_foreground``) runs the real gate."""
    if request.node.get_closest_marker("real_foreground"):
        return
    from poring_backend.foreground import Check, ForegroundGate

    monkeypatch.setattr(ForegroundGate, "check", lambda self: Check(True, "ok", 0.0, 0.0, "x11"))
