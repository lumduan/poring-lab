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
def cb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setenv("LAB_STATE_HOST_DIR", str(tmp_path / "state"))  # never the real state/
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
        self.hard_cap: int | None = 1_790_010_800

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
        monkeypatch.setattr(cb, "write_variant", lambda v: self.events.append(("variant", v)))
        monkeypatch.setattr(cb, "ensure_no_wm", lambda: self.events.append(("no-wm",)))
        monkeypatch.setattr(cb, "write_cleanroom", lambda *a: self.events.append(("cleanroom", *a)))
        monkeypatch.setattr(cb, "clear_cleanroom", lambda: self.events.append(("cleanroom-gone",)))
        monkeypatch.setattr(cb, "cleanroom_field", lambda key: self.hard_cap)
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
    assert "an external client" in capsys.readouterr().out


def test_external_to_console_keeps_the_lab_client_holding(cb: ModuleType) -> None:
    import inspect

    src = inspect.getsource(cb.cmd_to_console)
    ext = src.index("if external:")
    assert src.index('write_lock("console", "switching", EXTERNAL_REASON)') > ext
    # the external branch returns before console/steady (the lab client streams only on steady)
    assert src.index("return 0", ext) < src.index('write_lock("console", "steady"')


# --- the clean room (Batt, 2026-10-03) -----------------------------------------------------------


def test_to_rdp_checks_for_a_window_manager_before_rdp_may_connect(
    cb: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """V2 runs openbox on :99; rdp-loop wakes within 1 s of the lock and has no WM check."""
    w = World(cb)
    w.install(monkeypatch)
    assert cb.cmd_to_rdp(False) == 0
    assert w.index(("no-wm",)) < w.index(("lock", "rdp", "switching"))
    assert w.index(("lock", "rdp", "steady")) < w.index(("variant", "V1"))  # defaults restored
    assert w.index(("lock", "rdp", "steady")) < w.index(("cleanroom-gone",))  # console status off


class Room(World):
    def __init__(self, cb: ModuleType, phase: str, reason: str = "cleanroom") -> None:
        super().__init__(cb)
        self.text = f"BACKEND=console\nSEQ=7\nPHASE={phase}\nREASON={reason}\n"
        self.lab_clients = 0

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        super().install(monkeypatch)
        monkeypatch.setattr(self.cb, "read_host", lambda: ("console", 7, self.text))
        monkeypatch.setattr(self.cb, "running", lambda c: True)
        monkeypatch.setattr(
            self.cb, "count", lambda c, n: self.lab_clients if c == self.cb.GAMESTREAM else 0
        )


def test_stream_writes_the_variant_then_the_steady_lock(
    cb: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    room = Room(cb, "switching", "cleanroom-hold")
    room.install(monkeypatch)
    assert cb.cmd_stream("V2", 1_790_001_800) == 0
    status = ("cleanroom", "V2", 1_790_001_800, room.hard_cap)  # the hard cap is kept
    assert room.index(("variant", "V2")) < room.index(status)
    assert room.index(status) < room.index(("lock", "console", "steady"))


@pytest.mark.parametrize(
    ("phase", "reason", "lab_clients", "why"),
    [
        ("switching", "to-console-external", 0, "not in the clean room"),
        ("switching", "to-console", 0, "not in the clean room"),
        ("steady", "cleanroom", 0, "hold first"),
        ("switching", "cleanroom", 1, "one client at a time"),
    ],
)
def test_stream_refuses_outside_the_clean_room_or_with_a_lab_client_running(
    cb: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
    reason: str,
    lab_clients: int,
    why: str,
) -> None:
    room = Room(cb, phase, reason)
    room.lab_clients = lab_clients
    room.install(monkeypatch)
    with pytest.raises(cb.Stop, match=why):
        cb.cmd_stream("V1")
    assert not any(e[0] in ("lock", "variant", "cleanroom") for e in room.events)


def test_hold_moves_the_lock_before_the_cancel_and_resets_the_variant(
    cb: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    room = Room(cb, "steady")
    room.lab_clients = 1
    room.install(monkeypatch)
    monkeypatch.setattr(cb, "quit_stream", lambda: room.events.append(("quit",)) or "clean")
    assert cb.cmd_hold() == 0
    lock = room.index(("lock", "console", "switching"))
    assert lock < room.index(("quit",)) < room.index(("variant", "V1"))


def test_variants_are_whitelisted(cb: ModuleType) -> None:
    assert cb.variant_body("V3") == "CLIENT=s2spike\nWM=none\nGDB_AFTER_S=\n"
    assert cb.variant_body("V2") == "CLIENT=moonlight-qt\nWM=openbox\nGDB_AFTER_S=\n"
    with pytest.raises(cb.Stop):
        cb.variant_body("V9; rm -rf /")


def test_only_one_writer_at_a_time(
    cb: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import fcntl

    monkeypatch.setattr(cb, "FLOCK", tmp_path / "capture-backend.flock")
    with (tmp_path / "capture-backend.flock").open("a+") as other:
        fcntl.flock(other, fcntl.LOCK_EX)  # the runner (or the watchdog) holds it
        with pytest.raises(cb.Stop, match="holds the lock"), cb.mutation_lock(0.2):
            pass
        fcntl.flock(other, fcntl.LOCK_UN)
    with cb.mutation_lock(0.2):
        pass  # free again
