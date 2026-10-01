"""scripts/guarded_build.py: step parsing, and `up:` refused while the dev overlay runs.

A bare `compose up` in dev mode would recreate backend/desktop without their mounts and build the
production frontend, so dev-mode services come up through `start:` instead.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "guarded_build.py"


@pytest.fixture(scope="module")
def gb() -> ModuleType:
    spec = importlib.util.spec_from_file_location("guarded_build", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_build_and_pull(gb: ModuleType) -> None:
    step = gb.parse_step("build:rathena")
    assert (step.kind, step.services, step.label) == ("build", ["rathena"], "build:rathena")
    assert gb.parse_step("pull:db").services == ["db"]


def test_parse_start_with_and_without_seconds(gb: ModuleType) -> None:
    step = gb.parse_step("start:db,rathena@240")
    assert (step.kind, step.services, step.seconds) == ("start", ["db", "rathena"], 240.0)
    assert gb.parse_step("start:db").seconds == 180.0


def test_parse_up_default_seconds(gb: ModuleType) -> None:
    assert gb.parse_step("up").seconds == 180.0
    assert gb.parse_step("up:60").seconds == 60.0


@pytest.mark.parametrize("bad", ["start:", "start:db;rm", "build:", "pull:Db X", "nope:db"])
def test_parse_rejects_bad_steps(gb: ModuleType, bad: str) -> None:
    with pytest.raises(ValueError):
        gb.parse_step(bad)


def test_up_refused_while_dev_overlay_runs(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(gb, "dev_overlay_active", lambda: True)
    monkeypatch.setattr(gb, "cgroup_paths", lambda: pytest.fail("must refuse before watching"))
    monkeypatch.setattr(sys, "argv", ["guarded_build.py", "build:rathena", "up:60"])
    assert gb.main() == 2
    assert "up: refused" in capsys.readouterr().out


def test_unknown_step_exits_2_before_any_docker_call(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gb, "cgroup_paths", lambda: pytest.fail("must refuse before watching"))
    monkeypatch.setattr(sys, "argv", ["guarded_build.py", "frobnicate:db"])
    assert gb.main() == 2


def test_start_uses_dev_overlay_and_stops_only_its_services(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran: list[list[str]] = []
    monkeypatch.setattr(gb, "run_process", lambda label, cmd, guard: ran.append(cmd) or True)
    monkeypatch.setattr(gb, "watch", lambda seconds, guard, what, stop_cmd: ran.append(stop_cmd))
    gb.run_start(["db", "rathena"], 5, guard=None)
    up, stop = ran
    # core + sniffer profiles: start:sniffer is guarded too
    dev = ["scripts/dev.sh", "--profile", "core", "--profile", "sniffer"]
    assert up == [*dev, "up", "-d", "--no-build", "db", "rathena"]
    assert stop == [*dev, "stop", "db", "rathena"]


def test_parse_target_step(gb: ModuleType) -> None:
    step = gb.parse_step("target:rathena:build:poring-lab/rathena-build:local")
    assert (step.kind, step.services) == (
        "target",
        ["rathena", "build", "poring-lab/rathena-build:local"],
    )
    with pytest.raises(ValueError):
        gb.parse_step("target:rathena:build:bad tag")
