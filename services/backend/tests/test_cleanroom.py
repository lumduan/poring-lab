"""scripts/cleanroom.py: the clean-room watchdog's decisions and the runner's picture test.
Fakes only: no Docker, no Windows, no systemd."""

import importlib.util
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
CONSOLE = ("console", "steady", "cleanroom")
T = 1_790_000_000.0


@pytest.fixture
def cr(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ModuleType:
    monkeypatch.setenv("CLEANROOM_DIR", str(tmp_path / "cleanroom"))
    spec = importlib.util.spec_from_file_location("cleanroom", SCRIPTS / "cleanroom.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def status(**kw: float | str) -> dict[str, float | str]:
    return {"hard_cap_ts": T + 3 * 3600, "box_until_ts": T + 20 * 60, "variant": "V1", **kw}


def test_rdp_steady_means_done_once_entered(cr: ModuleType) -> None:
    st = status(entry_ts=T - 60, entered_ts=T - 30)
    assert cr.decide(T, st, ("rdp", "steady", "to-rdp-done"), False, 0) == "done"


def test_before_the_entry_rdp_steady_is_not_done(cr: ModuleType) -> None:
    """2026-10-03: the watchdog starts BEFORE to-console, saw rdp/steady, called it done and
    exited -- the room would have run unguarded."""
    starting = status(phase="starting", entry_ts=T)
    assert cr.decide(T + 5, starting, ("rdp", "steady", "to-rdp-done"), False, 0) == "wait"
    failed = status(phase="enter-failed", entry_ts=T)
    assert cr.decide(T + 5, failed, ("rdp", "steady", "to-rdp-done"), False, 0) == "done"
    stale = cr.decide(T + cr.ENTRY_GRACE_S + 1, starting, ("rdp", "steady", ""), False, 0)
    assert stale == "done"  # a start that never entered does not keep a watchdog forever


def test_a_half_done_to_rdp_is_not_done(cr: ModuleType) -> None:
    """rdp/switching = a to-rdp that did not finish: the watchdog still acts on it (--recover)."""
    late = T + 3 * 3600 + 1
    assert cr.decide(late, status(), ("rdp", "switching", "to-rdp"), False, 0) == "exit:hard cap"


def test_within_the_box_with_a_fresh_heartbeat_it_waits(cr: ModuleType) -> None:
    assert cr.decide(T + 60, status(), CONSOLE, False, 30) == "wait"


def test_the_runners_box_wins_by_five_minutes(cr: ModuleType) -> None:
    box_end = T + 20 * 60
    assert cr.decide(box_end + 299, status(), CONSOLE, False, 10) == "wait"
    assert cr.decide(box_end + 300, status(), CONSOLE, False, 10).startswith("exit:V1's box")


def test_a_stale_heartbeat_fires(cr: ModuleType) -> None:
    v = cr.decide(T + 60, status(box_until_ts=0), CONSOLE, False, cr.HEARTBEAT_STALE_S)
    assert v.startswith("exit:runner heartbeat stale")


def test_a_human_at_the_console_defers_everything_but_the_hard_cap(cr: ModuleType) -> None:
    late_box = T + 20 * 60 + 600
    assert cr.decide(late_box, status(), CONSOLE, True, 10).startswith("defer:")
    assert cr.decide(T + 60, status(), CONSOLE, True, 10**6).startswith("defer:")
    assert cr.decide(T + 3 * 3600, status(), CONSOLE, True, 10) == "exit:hard cap"


@pytest.mark.parametrize(
    ("health", "active"),
    [
        ({"lease_active": True, "last_human_input_age_s": 500.0}, True),
        ({"lease_active": False, "last_human_input_age_s": 30.0}, True),
        ({"lease_active": False, "last_human_input_age_s": 500.0}, False),
        ({"lease_active": False, "last_human_input_age_s": None}, False),
    ],
)
def test_human_activity(cr: ModuleType, health: dict[str, object], active: bool) -> None:
    assert cr.human_active(health) is active


def test_black_and_picture_frames(cr: ModuleType) -> None:
    black = np.zeros((900, 1440, 4), np.uint8)
    assert not cr.is_picture(cr.classify_frame(black))
    cursor_only = black.copy()
    cursor_only[400:420, 700:712, :3] = 255  # the black S1 stream showed only a cursor
    assert not cr.is_picture(cr.classify_frame(cursor_only))
    desktop = np.random.default_rng(1).integers(0, 255, (900, 1440, 4), dtype=np.uint8)
    assert cr.is_picture(cr.classify_frame(desktop))
    qt_warning = black.copy()  # Moonlight's own window, top-left, on an otherwise black session
    qt_warning[:600, :1280, :3] = 51
    qt_warning[250:300, 400:900, :3] = 230
    assert not cr.is_picture(cr.classify_frame(qt_warning))  # the 2026-10-03 false positive


def test_status_round_trip_and_heartbeat(cr: ModuleType) -> None:
    assert cr.load_status() == {}
    cr.save_status(phase="entered", variant="V2")
    cr.save_status(box_until_ts=5.0)
    st = cr.load_status()
    assert (st["phase"], st["variant"], st["box_until_ts"]) == ("entered", "V2", 5.0)
    assert cr.heartbeat_age(T) == float("inf")
    cr.heartbeat()
    assert cr.heartbeat_age(cr.time.time()) < 5


def test_the_checks_box_is_enforced_like_a_variants(cr: ModuleType) -> None:
    """After a reliable variant the bench and the functional checks run in their own box
    (cleanroom.py checks); before it existed only the heartbeat and the hard cap bounded them."""
    st = status(phase="checks", box_until_ts=T + 45 * 60)
    assert cr.decide(T + 45 * 60 + 299, st, CONSOLE, False, 10) == "wait"
    verdict = cr.decide(T + 45 * 60 + 300, st, CONSOLE, False, 10)
    assert verdict == "exit:the checks box expired"


def test_checks_needs_a_running_room_and_sets_the_box(cr: ModuleType) -> None:
    with pytest.raises(SystemExit, match="no clean room"):
        cr.cmd_checks(45)
    cr.save_status(phase="streaming", variant="V3b", box_until_ts=0)
    assert cr.cmd_checks(60) == 0
    st = cr.load_status()
    assert st["phase"] == "checks" and st["box_until_ts"] > cr.time.time() + 59 * 60
    cr.save_status(phase="checks")
    with pytest.raises(SystemExit, match="already running"):
        cr.cmd_start(180)  # never a second room on top
