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


def test_to_console_refuses_without_a_running_paired_gamestream(
    cb: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cb, "count", lambda container, names: 1)
    monkeypatch.setattr(cb, "running", lambda container: False)
    with pytest.raises(SystemExit, match="gamestream must be running and paired"):
        cb.cmd_to_console(yes_tscon=True)
    assert cb.read_host() == ("rdp", 0, "")  # refused before any lock write


def test_pair_rejects_a_bad_pin(cb: ModuleType) -> None:
    with pytest.raises(SystemExit, match="4 digits"):
        cb.cmd_pair("12a4")


@pytest.mark.parametrize(
    ("hosts", "expected"),
    [
        ("1\\srvcert=@ByteArray(-----BEGIN CERTIFICATE-----\\nMIIB...)\n", True),
        ("1\\srvcert=@ByteArray()\n", False),  # a known but unpaired host
        ("", False),  # only Moonlight's own identity
    ],
)
def test_paired_means_a_stored_server_certificate_not_our_identity(
    cb: ModuleType, tmp_path: Path, hosts: str, expected: bool
) -> None:
    """[General] certificate is Moonlight's own identity, written on first run: it must not count
    as paired (the old check did, 2026-10-02). Run through grep -E, as in the container."""
    import subprocess

    conf = tmp_path / "Moonlight.conf"
    conf.write_text(
        "[General]\ncertificate=@ByteArray(-----BEGIN CERTIFICATE-----\\nOWN)\nkey=@ByteArray(x)\n"
        f"\n[hosts]\n{hosts}size=1\n"
    )
    res = subprocess.run(["grep", "-q", "-E", cb.PAIRED_HOST_RX, str(conf)], check=False)
    assert (res.returncode == 0) is expected
