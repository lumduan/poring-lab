"""to-rdp from console ends the stream CLEANLY (2026-10-02): Moonlight's `quit` asks Sunshine to end
the session while it is still on the console, TERM is only a reported fallback, the lock moves after
the revert wait, and a still-pending Sunshine revert is reported (rc 3) with its remedy.
Fakes only: no Docker, no Windows."""

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture
def cb() -> ModuleType:
    spec = importlib.util.spec_from_file_location("capture_backend", SCRIPTS / "capture_backend.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class World:
    """Records every side effect of a handover in order."""

    def __init__(self, cb: ModuleType, *, lock: str = "console") -> None:
        self.cb = cb
        self.lock = lock
        self.events: list[tuple[Any, ...]] = []
        self.session_ends = True  # Sunshine ends the session after `quit`
        self.client_leaves = True  # the streaming Moonlight exits by itself
        self.revert = "OK"
        self.quit_rc = 0

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cb = self.cb
        monkeypatch.setattr(cb, "read_host", lambda: (self.lock, 1, "steady"))
        monkeypatch.setattr(cb, "write_lock", self.write_lock)
        monkeypatch.setattr(cb, "verify_everywhere", lambda body: None)
        monkeypatch.setattr(cb, "sh", self.sh)
        monkeypatch.setattr(cb, "wait_log", self.wait_log)
        monkeypatch.setattr(cb, "count", self.count)
        monkeypatch.setattr(cb, "term_until_zero", self.term)
        monkeypatch.setattr(cb, "revive_rdp_loop_if_idle", lambda since: None)
        monkeypatch.setattr(cb, "verify_sunshine_revert", self.verify)
        monkeypatch.setattr(cb, "STREAM_EXIT_S", 0.0)
        monkeypatch.setattr(cb.time, "sleep", lambda s: self.events.append(("sleep", s)))

    def write_lock(self, backend: str, phase: str, reason: str) -> str:
        self.events.append(("lock", backend, phase))
        return f"BACKEND={backend}\nSEQ=2\nPHASE={phase}\n"

    def sh(self, *cmd: str, **kw: Any) -> subprocess.CompletedProcess[str]:
        if "quit" in " ".join(cmd):
            self.events.append(("quit",))
            return subprocess.CompletedProcess(cmd, self.quit_rc, "", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def wait_log(self, container: str, pattern: str, since: str, timeout: float) -> str:
        if pattern == self.cb.STREAM_END_RX:
            if not self.session_ends:
                raise self.cb.Stop("no session end")
            self.events.append(("session-ended",))
            return "00:01:49 - SDL Info (0): Quit event received"
        return "rdp-loop: connecting to win.test"

    def count(self, container: str, names: str) -> int:
        if container == self.cb.GAMESTREAM:
            if ("quit",) not in self.events:
                return 1  # the lab's Moonlight streams until the quit
            return 0 if self.client_leaves or ("term", container) in self.events else 1
        return 1  # exactly one xfreerdp

    def term(self, container: str, names: str, **kw: Any) -> None:
        self.events.append(("term", container))

    def verify(self) -> str:
        self.events.append(("verify",))
        return self.revert

    def index(self, event: tuple[Any, ...]) -> int:
        return self.events.index(event)


def test_to_rdp_ends_the_stream_through_sunshine_before_the_lock_moves(
    cb: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    w = World(cb)
    w.install(monkeypatch)
    assert cb.cmd_to_rdp(False) == 0
    switching = w.index(("lock", "console", "switching"))
    quit_ = w.index(("quit",))
    settle = w.index(("sleep", cb.SUNSHINE_REVERT_S))
    rdp = w.index(("lock", "rdp", "switching"))
    assert switching < quit_ < w.index(("session-ended",)) < settle < rdp
    # no TERM of the stream client before the session left the console
    assert ("term", cb.GAMESTREAM) not in w.events[:rdp]
    assert w.events.index(("lock", "rdp", "steady")) < w.index(("verify",))
    assert "Sunshine reverted its display settings" in capsys.readouterr().out


def test_term_is_only_a_reported_fallback_when_the_client_lingers(
    cb: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    w = World(cb)
    w.client_leaves = False
    w.install(monkeypatch)
    assert cb.quit_stream() == "client-killed"
    assert w.index(("quit",)) < w.index(("term", cb.GAMESTREAM))
    assert "did not leave by itself: TERM" in capsys.readouterr().out


def test_no_session_end_is_reported_unclean(
    cb: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    w = World(cb)
    w.session_ends = False
    w.install(monkeypatch)
    cb.cmd_to_rdp(False)
    assert "UNCLEAN END" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("verdict", "message"),
    [
        ("PENDING", "The next console session reverts it"),
        ("UNVERIFIED", "check it by hand"),
    ],
)
def test_a_revert_that_is_not_confirmed_returns_3_with_the_remedy(
    cb: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    verdict: str,
    message: str,
) -> None:
    w = World(cb)
    w.revert = verdict
    w.install(monkeypatch)
    assert cb.cmd_to_rdp(False) == 3
    out = capsys.readouterr().out
    assert f"SUNSHINE REVERT {verdict}" in out and message in out
    assert ("lock", "rdp", "steady") in w.events  # RDP is back either way


def test_recover_from_rdp_neither_quits_nor_checks_the_revert(
    cb: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    w = World(cb, lock="rdp")
    w.install(monkeypatch)
    assert cb.cmd_to_rdp(True) == 0
    assert ("quit",) not in w.events and ("verify",) not in w.events


def test_quit_runs_on_a_private_display_with_the_paired_identity(cb: ModuleType) -> None:
    script = cb.QUIT_STREAM.format(t=30)
    assert "DISPLAY=:51" in script and ":99" not in script
    assert 'AppRun quit "$WIN_HOST"' in script and "timeout 30" in script


def _frame(h: int = 200, w: int = 600) -> np.ndarray:
    return np.full((h, w, 3), 12, np.uint8)  # the console's near-black background


def test_marker_classifier(cb: ModuleType) -> None:
    red, green = (197, 15, 31), (19, 161, 14)  # Windows Terminal Campbell DarkRed / DarkGreen
    f = _frame()
    assert cb.classify_marker(f) is None
    f[100:118, 20:380] = green
    assert cb.classify_marker(f) == "OK"
    f = _frame()
    f[100:118, 20:380] = red
    assert cb.classify_marker(f) == "PENDING"
    f[150:168, 20:380] = green  # the newest (bottom-most) marker wins
    assert cb.classify_marker(f) == "OK"
    f = _frame()
    f[100:118, 20 : 20 + cb.MARKER_MIN_RUN - 1] = red  # too short: a red word, not the marker
    assert cb.classify_marker(f) is None
    f = _frame()
    f[::2, ::3] = green  # scattered green pixels (text, game) never make a run
    assert cb.classify_marker(f) is None


def test_an_external_clients_session_is_cancelled_without_waiting_for_a_lab_client(
    cb: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """S2 step 0: Batt's Mac streams; the lab's Moonlight never did. to-rdp still sends the cancel
    and relies on the revert check, never on the lab client's log."""
    w = World(cb)
    w.install(monkeypatch)
    monkeypatch.setattr(cb, "count", lambda c, n: 0 if c == cb.GAMESTREAM else 1)
    assert cb.quit_stream() == "external"
    assert ("quit",) in w.events and ("session-ended",) not in w.events
    assert "external client's session" in capsys.readouterr().out


def test_external_to_console_keeps_the_lab_client_holding(cb: ModuleType) -> None:
    import inspect

    src = inspect.getsource(cb.cmd_to_console)
    ext = src.index("if external:")
    assert src.index('write_lock("console", "switching", EXTERNAL_REASON)') > ext
    # the external branch returns before console/steady (the lab client streams only on steady)
    assert src.index("return 0", ext) < src.index('write_lock("console", "steady"')
