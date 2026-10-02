"""scripts/capture_backend.py: the only writer of the capture-backend lock (ADR-0009)."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "capture_backend.py"


@pytest.fixture
def cb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setenv("LAB_STATE_HOST_DIR", str(tmp_path / "state"))
    spec = importlib.util.spec_from_file_location("capture_backend", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "verify_everywhere", lambda body: None)  # no docker in tests
    return module


def test_writes_are_atomic_and_seq_always_increases(cb: ModuleType, tmp_path: Path) -> None:
    assert cb.read_host() == ("rdp", 0, "")  # no file yet: the default
    first = cb.write_lock("console", "switching", "to-console")
    second = cb.write_lock("console", "steady", "to-console-done")
    assert "SEQ=1\n" in first and "SEQ=2\n" in second
    assert cb.read_host()[:2] == ("console", 2)
    assert not list((tmp_path / "state").glob(".*.tmp"))  # renamed into place


def test_seq_survives_an_unreadable_lock(cb: ModuleType, tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    (state / "capture-backend").write_text("BACKEND=bogus\nSEQ=41\n")
    assert cb.read_host()[0] == "hold"
    assert "SEQ=42\n" in cb.write_lock("rdp", "switching", "recover")


def test_init_is_idempotent(cb: ModuleType) -> None:
    assert cb.cmd_init() == 0
    body = cb.read_host()[2]
    assert cb.cmd_init() == 0 and cb.read_host()[2] == body  # an existing lock is left alone


def test_bad_words_never_reach_the_file(cb: ModuleType) -> None:
    with pytest.raises(ValueError):
        cb.write_lock("console", "steady", "two words")
    assert cb.read_host() == ("rdp", 0, "")


def test_console_and_pair_are_not_available_yet(
    cb: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.argv", ["capture_backend.py", "to-console"])
    with pytest.raises(SystemExit, match="not available until gamestream"):
        cb.main()
