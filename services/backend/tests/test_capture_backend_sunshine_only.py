"""capture_backend.py on a SUNSHINE-ONLY host (2026-11-17, docs/setup/sunshine-windows.md): RDP is
off, so the lock goes rdp/steady -> console/steady without tscon and back without an RDP client,
and every RDP-path refusal (rule 2: one display path) holds. Fakes only: no Docker, no Windows."""

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "capture_backend.py"
NO_RDP = "WIN_HOST=192.168.1.50\nRDP_USER=\nRDP_PASSWORD=\n"
WITH_RDP = "WIN_HOST=192.168.1.50\nRDP_USER=lab\nRDP_PASSWORD=x\n"


@pytest.fixture
def cb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setenv("LAB_STATE_HOST_DIR", str(tmp_path / "state"))
    spec = importlib.util.spec_from_file_location("capture_backend", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ENV_FILE", tmp_path / ".env")
    (tmp_path / ".env").write_text(NO_RDP)
    return module


class Host:
    """A Sunshine-only host: what runs, what each container's environment says, the logs."""

    def __init__(self, cb: ModuleType) -> None:
        self.cb = cb
        self.events: list[tuple[Any, ...]] = []
        self.desktop_env = "disabled"
        self.xfreerdp = 0
        self.lab_clients = 0
        self.is_paired = True
        self.reachable = True

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cb = self.cb
        monkeypatch.setattr(cb, "running", lambda container: True)
        monkeypatch.setattr(cb, "verify_everywhere", lambda body: self.events.append(("seen",)))
        monkeypatch.setattr(cb, "sh", self.sh)
        monkeypatch.setattr(cb, "count", self.count)
        monkeypatch.setattr(cb, "paired", lambda: self.is_paired)
        monkeypatch.setattr(cb, "sunshine_reachable", lambda host: self.reachable)
        monkeypatch.setattr(cb, "wait_log", self.wait_log)
        monkeypatch.setattr(cb, "quit_stream", lambda: self.events.append(("quit",)) or "clean")
        monkeypatch.setattr(cb, "term_until_zero", lambda *a, **k: self.events.append(("term",)))
        monkeypatch.setattr(cb, "write_variant", lambda v, k=None: self.events.append(("var", v)))
        monkeypatch.setattr(cb, "clear_cleanroom", lambda: self.events.append(("cleanroom-gone",)))

    def sh(self, *cmd: str, **kw: Any) -> subprocess.CompletedProcess[str]:
        if cmd[:3] == ("docker", "exec", self.cb.DESKTOP) and cmd[-1] == self.cb.RDP_ENV_PROBE:
            return subprocess.CompletedProcess(cmd, 0, self.desktop_env + "\n", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def count(self, container: str, names: str) -> int:
        if container == self.cb.DESKTOP:
            return self.xfreerdp
        return self.lab_clients

    def wait_log(self, container: str, pattern: str, since: str, timeout: float) -> str:
        self.events.append(("log", container, pattern))
        return "2026-11-17T10:00:00+0000 s2spike: FIRST FRAME decoded: 1440x900"

    def lock(self) -> tuple[str, str, str]:
        backend, _, text = self.cb.read_host()
        return backend, self.cb.lock_phase(text), self.cb.lock_reason(text)


def test_rdp_env_follows_rdp_loops_rule(cb: ModuleType, tmp_path: Path) -> None:
    """rdp-loop.sh connects only with WIN_HOST, RDP_USER and RDP_PASSWORD ALL set."""
    assert cb.rdp_env() == "disabled"
    (tmp_path / ".env").write_text(WITH_RDP)
    assert cb.rdp_env() == "configured"
    (tmp_path / ".env").write_text("WIN_HOST=\nRDP_USER=lab\nRDP_PASSWORD=x\n")
    assert cb.rdp_env() == "disabled"
    (tmp_path / ".env").write_text("# RDP_USER=lab\nWIN_HOST=w\nRDP_PASSWORD=x\n")
    assert cb.rdp_env() == "disabled"  # a comment is not a value
    (tmp_path / ".env").unlink()
    assert cb.rdp_env() == "unknown"


def test_the_desktop_probe_names_no_value(cb: ModuleType) -> None:
    probe = cb.RDP_ENV_PROBE
    assert "echo configured" in probe and "echo disabled" in probe
    assert "echo $" not in probe and "printenv" not in probe and "env" not in probe.split()


def test_init_then_sunshine_only_streams_the_s2_variant(
    cb: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = Host(cb)
    host.install(monkeypatch)
    assert cb.cmd_init() == 0
    assert host.lock() == ("rdp", "steady", "init")  # nothing connects, gamestream holds: pair now
    assert cb.cmd_to_console_sunshine_only() == 0
    assert host.lock() == ("console", "steady", "sunshine-only")
    variant = host.events.index(("var", "S2"))
    streaming = next(i for i, e in enumerate(host.events) if e[0] == "log" and "streaming" in e[2])
    first = next(i for i, e in enumerate(host.events) if e[0] == "log" and "FIRST FRAME" in e[2])
    assert variant < streaming < first  # the variant before the lock, the first frame last
    # idempotent: a second run (a resumed wizard) changes nothing
    before = cb.read_host()[2]
    assert cb.cmd_to_console_sunshine_only() == 0 and cb.read_host()[2] == before


@pytest.mark.parametrize(
    ("setup", "match"),
    [
        (lambda h, p: p.write_text(WITH_RDP), "RDP is configured in .env"),
        (lambda h, p: p.unlink(), "no readable .env"),
        (lambda h, p: setattr(h, "desktop_env", "configured"), "RUNNING desktop still has RDP"),
        (lambda h, p: setattr(h, "xfreerdp", 1), "an xfreerdp client runs"),
        (lambda h, p: setattr(h, "is_paired", False), "running and paired"),
        (lambda h, p: setattr(h, "reachable", False), "not reachable"),
        (lambda h, p: setattr(h, "lab_clients", 1), "already run in gamestream"),
    ],
)
def test_sunshine_only_refuses_before_any_write(
    cb: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, setup: Any, match: str
) -> None:
    host = Host(cb)
    host.install(monkeypatch)
    cb.cmd_init()
    before = cb.read_host()[2]
    setup(host, tmp_path / ".env")
    with pytest.raises(SystemExit, match=match):
        cb.cmd_to_console_sunshine_only()
    assert cb.read_host()[2] == before and ("var", "S2") not in host.events


def test_sunshine_only_starts_only_from_rdp_steady(
    cb: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    Host(cb).install(monkeypatch)
    cb.write_lock("console", "switching", "to-console")
    with pytest.raises(SystemExit, match="starts from rdp/steady"):
        cb.cmd_to_console_sunshine_only()


def test_back_to_rdp_ends_the_stream_through_sunshine_first(
    cb: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = Host(cb)
    host.install(monkeypatch)
    cb.cmd_init()
    cb.cmd_to_console_sunshine_only()
    host.events.clear()
    assert cb.cmd_to_rdp_sunshine_only() == 0
    assert host.lock() == ("rdp", "steady", "sunshine-only-off")
    assert host.events[:2] == [("seen",), ("quit",)]  # console/switching, then the /cancel
    assert ("term",) in host.events and ("var", "V1") in host.events
    host.events.clear()
    assert cb.cmd_to_rdp_sunshine_only() == 0 and host.events == []  # already there


def test_a_plain_to_rdp_is_refused_on_a_host_without_rdp(
    cb: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    Host(cb).install(monkeypatch)
    cb.write_lock("console", "steady", "sunshine-only")
    with pytest.raises(SystemExit, match="to-rdp --sunshine-only"):
        cb.cmd_to_rdp(recover=False)
    assert cb.read_host()[0] == "console"


def test_back_to_rdp_refuses_on_an_rdp_host(
    cb: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    Host(cb).install(monkeypatch)
    (tmp_path / ".env").write_text(WITH_RDP)
    cb.write_lock("console", "steady", "to-console")
    with pytest.raises(SystemExit, match="RDP is configured"):
        cb.cmd_to_rdp_sunshine_only()


def test_pair_refuses_while_a_lab_client_streams(
    cb: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = Host(cb)
    host.install(monkeypatch)
    host.lab_clients = 1
    with pytest.raises(SystemExit, match="end the stream first"):
        cb.cmd_pair("1234")


def test_paired_is_read_only_and_says_why(
    cb: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    host = Host(cb)
    host.install(monkeypatch)
    assert cb.cmd_paired() == 0 and capsys.readouterr().out.strip() == "paired"
    host.is_paired = False
    assert cb.cmd_paired() == 1 and capsys.readouterr().out.strip() == "not paired"
    monkeypatch.setattr(cb, "running", lambda container: False)
    assert cb.cmd_paired() == 2
    assert not (Path(cb.STATE) / "capture-backend").exists()  # nothing written
