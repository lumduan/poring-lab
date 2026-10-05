"""scripts/guarded_build.py: step parsing, and `up:` refused while the dev overlay runs.

A bare `compose up` in dev mode would recreate backend/desktop without their mounts and build the
production frontend, so dev-mode services come up through `start:` instead.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "guarded_build.py"


def record(ran: list[list[str]], cmd: list[str]) -> bool:
    ran.append(cmd)
    return True


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
    monkeypatch.setattr(gb, "run_process", lambda label, cmd, guard, env=None: record(ran, cmd))
    monkeypatch.setattr(gb, "watch", lambda seconds, guard, what, stop_cmd: ran.append(stop_cmd))
    gb.run_start(["db", "rathena"], 5, guard=None)
    up, stop = ran
    # core + sniffer + gamestream + th profiles: start:sniffer / gamestream / rathena-th guarded too
    dev = ["scripts/dev.sh", "--profile", "core", "--profile", "sniffer", "--profile", "gamestream",
           "--profile", "th"]  # fmt: skip
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


def test_recreate_forces_and_still_stops_only_its_services(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran: list[list[str]] = []
    monkeypatch.setattr(gb, "run_process", lambda label, cmd, guard, env=None: record(ran, cmd))
    monkeypatch.setattr(gb, "watch", lambda seconds, guard, what, stop_cmd: ran.append(stop_cmd))
    step = gb.parse_step("recreate:desktop@90")
    assert (step.kind, step.services, step.seconds) == ("recreate", ["desktop"], 90.0)
    gb.run_start(step.services, step.seconds, guard=None, recreate=True)
    up, stop = ran
    assert up[-3:] == ["--no-build", "--force-recreate", "desktop"]
    assert stop[-2:] == ["stop", "desktop"]


def test_builds_use_the_lab_builder_without_touching_the_global_one(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[list[str], dict[str, str] | None]] = []
    monkeypatch.setattr(gb, "cgroup_paths", lambda: [])
    monkeypatch.setattr(
        gb, "run_process", lambda label, cmd, guard, env=None: calls.append((cmd, env)) or True
    )
    monkeypatch.setattr(sys, "argv", ["guarded_build.py", "build:desktop", "pull:db"])
    assert gb.main() == 0
    (build, build_env), (pull, pull_env) = calls
    assert build[:3] == ["docker", "compose", "--profile"] and "build" in build
    assert build_env is not None and build_env["BUILDX_BUILDER"] == "default"
    assert pull_env is None  # only builds pick a builder
    assert not any("buildx" in c and "use" in c for c in build)  # never `docker buildx use`


def test_lab_builder_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LAB_BUILDX_BUILDER", "armbuilder")
    spec = importlib.util.spec_from_file_location("guarded_build_override", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.build_env()["BUILDX_BUILDER"] == "armbuilder"


def test_run_step_is_vision_only_and_never_starts_dependencies(gb: ModuleType) -> None:
    """check_gpu.py needs `compose run`; a second gamestream would be a second lab client and a
    second desktop a second xfreerdp, so run: knows exactly one service (2026-10-03)."""
    step = gb.parse_step("run:vision@600=python scripts/check_gpu.py")
    assert (step.kind, step.services, step.seconds) == ("run", ["vision"], 600.0)
    assert gb.run_cmd(step) == [
        "timeout", "600", "docker", "compose", "--profile", "vision", "run", "--rm",
        "--no-deps", "vision", "python", "scripts/check_gpu.py",
    ]  # fmt: skip
    for refused in ("run:gamestream=true", "run:desktop=true", "run:vision", "run:vision="):
        with pytest.raises(ValueError):
            gb.parse_step(refused)


def test_rundev_adds_only_the_vision_dev_overlay(gb: ModuleType) -> None:
    """Training iterates on the host's vision source (compose.vision-dev.yaml, read-only) without a
    ~5 GB image rebuild; still vision only, still never its dependencies (2026-10-04)."""
    step = gb.parse_step("rundev:vision@3600=python -m poring_vision.train --smoke")
    assert (step.kind, step.services, step.seconds) == ("rundev", ["vision"], 3600.0)
    assert gb.run_cmd(step) == [
        "timeout", "3600", "docker", "compose", "-f", "compose.yaml", "-f",
        "compose.vision-dev.yaml", "--profile", "vision", "run", "--rm", "--no-deps", "vision",
        "python", "-m", "poring_vision.train", "--smoke",
    ]  # fmt: skip
    for refused in ("rundev:gamestream=true", "rundev:vision", "rundev:backend=true"):
        with pytest.raises(ValueError):
            gb.parse_step(refused)


def test_a_target_image_tag_never_becomes_a_log_directory(gb: ModuleType) -> None:
    """target:<svc>:<stage>:poring-lab/<x>:local put a `/` into the log name and the step crashed
    before docker ran (2026-10-03)."""
    label = gb.parse_step("target:gamestream:s2build:poring-lab/gamestream-s2build:local").label
    path = gb.log_path(label)
    assert path.parent == gb.LOGDIR and "/" not in path.name


class Backend:
    """A fake backend for restart:backend -- its /health before and after, and the call order."""

    def __init__(self, gb: ModuleType, tmp_path: Path, mode: str, restored: bool = True) -> None:
        self.gb, self.mode, self.restored = gb, mode, restored
        self.events: list[str] = []
        self.restarted = False
        self.marker = tmp_path / "mux-restore"

    def install(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, rc: bool = True) -> None:
        gb = self.gb
        monkeypatch.setattr(gb, "STATE", tmp_path)
        monkeypatch.setattr(gb, "backend_health", self.health)

        def run_process(label: str, cmd: list[str], guard: object, env: object = None) -> bool:
            self.events.append(f"restart marker={self.marker.exists()}")
            self.restarted = True
            return rc

        monkeypatch.setattr(gb, "run_process", run_process)
        monkeypatch.setattr(
            gb, "watch", lambda *a: self.events.append(f"watch marker={self.marker.exists()}")
        )

    def health(self, timeout: float = 3) -> dict[str, object]:
        if not self.restarted:
            return {"mode": self.mode, "capture_backend": {"backend": "rdp", "seq": 40}}
        mode = self.mode if self.restored else "HUMAN"
        return {"mode": mode, "mode_restored": self.restored, "capture_backend": {"seq": 40}}


def test_restart_backend_in_assist_writes_the_marker_and_removes_it_once_up(
    gb: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = Backend(gb, tmp_path, "ASSIST")
    fake.install(monkeypatch, tmp_path)
    gb.run_restart(["backend"], 30, guard=None)
    # present for the restart, gone BEFORE the watch (a crash during it must boot HUMAN)
    assert fake.events == ["restart marker=True", "watch marker=False"]
    out = capsys.readouterr().out
    assert "MODE=ASSIST SEQ=40" in out and "OWNER=guarded_build" in out
    assert "mux after the restart: ASSIST (restored automatically)" in out


@pytest.mark.parametrize("mode", ["HUMAN", "BOT"])
def test_restart_backend_outside_assist_writes_no_marker(
    gb: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    fake = Backend(gb, tmp_path, mode)
    fake.install(monkeypatch, tmp_path)
    gb.run_restart(["backend"], 30, guard=None)
    assert fake.events == ["restart marker=False", "watch marker=False"]


def test_a_failed_restart_still_removes_the_marker(
    gb: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = Backend(gb, tmp_path, "ASSIST")
    fake.install(monkeypatch, tmp_path, rc=False)
    assert gb.run_restart(["backend"], 30, guard=None) is False
    assert not fake.marker.exists()


def test_a_restart_of_other_services_never_asks_the_backend(
    gb: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = Backend(gb, tmp_path, "ASSIST")
    fake.install(monkeypatch, tmp_path)
    no_health = lambda timeout=3: pytest.fail("not a backend restart")  # noqa: E731
    monkeypatch.setattr(gb, "backend_health", no_health)
    gb.run_restart(["desktop"], 30, guard=None)
    assert fake.events == ["restart marker=False", "watch marker=False"]


def test_a_recreate_of_the_backend_in_assist_restores_like_a_restart(
    gb: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Batt, 2026-10-04: a guarded recreate:backend keeps ASSIST on the same marker conditions."""
    fake = Backend(gb, tmp_path, "ASSIST")
    fake.install(monkeypatch, tmp_path)
    gb.run_start(["backend"], 30, guard=None, recreate=True)
    assert fake.events == ["restart marker=True", "watch marker=False"]
    assert "mux after the recreate: ASSIST (restored automatically)" in capsys.readouterr().out


@pytest.mark.parametrize("mode", ["HUMAN", "BOT"])
def test_a_recreate_outside_assist_writes_no_marker(
    gb: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    fake = Backend(gb, tmp_path, mode)
    fake.install(monkeypatch, tmp_path)
    gb.run_start(["backend"], 30, guard=None, recreate=True)
    assert fake.events == ["restart marker=False", "watch marker=False"]


def test_a_plain_start_never_writes_the_marker(
    gb: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = Backend(gb, tmp_path, "ASSIST")
    fake.install(monkeypatch, tmp_path)
    gb.run_start(["backend"], 30, guard=None)
    assert fake.events == ["restart marker=False", "watch marker=False"]


def test_a_failed_recreate_still_removes_the_marker(
    gb: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = Backend(gb, tmp_path, "ASSIST")
    fake.install(monkeypatch, tmp_path, rc=False)
    assert gb.run_start(["backend"], 30, guard=None, recreate=True) is False
    assert not fake.marker.exists()


def test_it_runs_on_the_hosts_bare_python3() -> None:
    """guarded_build.py is run as `python3 scripts/guarded_build.py` (no venv, no pydantic). Its
    mode_restore import once pulled in poring_env.protocol and crashed before any step."""
    import subprocess

    res = subprocess.run(
        [sys.executable, "-S", str(SCRIPT), "frobnicate:db"],  # -S: no site-packages at all
        capture_output=True, text=True, timeout=30, check=False,
    )  # fmt: skip
    assert res.returncode == 2, res.stderr
    assert "Traceback" not in res.stderr


# --- the auto GM recover after a sniffer restart (Batt, 2026-10-04) -------------------------------


def health(mode: str = "ASSIST", backend: str = "rdp", phase: str = "steady",
           state: str = "red", config: str = "ok") -> dict:  # fmt: skip
    return {"mode": mode, "capture_backend": {"backend": backend, "phase": phase, "seq": 9},
            "environment": {"state": state, "config": config}}  # fmt: skip


@pytest.mark.parametrize(
    ("h", "why"),
    [
        (None, "no /health"),
        (health(mode="BOT"), "never BOT"),
        (health(mode="HUMAN"), "ASSIST only"),
        (health(backend="hold", phase=""), "steady only"),
        (health(phase="switching"), "steady only"),
        (health(config="config_missing"), "config"),
        (health(state="green"), "already green"),
    ],
)  # fmt: skip
def test_the_auto_recover_runs_only_under_batts_conditions(
    gb: ModuleType, h: Any, why: str
) -> None:
    assert why in (gb.recover_gate(h) or "")


def test_the_gate_opens_for_assist_on_a_steady_lock_rdp_or_console(gb: ModuleType) -> None:
    assert gb.recover_gate(health()) is None
    assert gb.recover_gate(health(backend="console")) is None
    assert gb.recover_gate(health(state="window")) is None  # a login window open: still not green


class Done:
    def __init__(self, rc: int) -> None:
        self.returncode = rc


def test_one_attempt_then_green(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: Any
) -> None:
    states = iter([health(), health(state="red"), health(state="green")])
    monkeypatch.setattr(gb, "backend_health", lambda: next(states))
    monkeypatch.setattr(gb, "LOGDIR", tmp_path)
    calls: list[list[str]] = []
    assert gb.auto_recover_gm(run=lambda cmd, **kw: calls.append(cmd) or Done(0),
                              sleep=lambda s: None)  # fmt: skip
    assert len(calls) == 1
    assert calls[0][-6:] == ["recover", "gm", "--retries", "0", "--agent-id", "auto_recover"]
    assert calls[0][0].endswith(".venv/bin/python")
    out = capsys.readouterr().out
    assert "reason=auto_recover" in out and "auto GM recover OK" in out


def test_a_failure_is_reported_never_retried(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: Any
) -> None:
    monkeypatch.setattr(gb, "backend_health", lambda: health())
    monkeypatch.setattr(gb, "LOGDIR", tmp_path)
    calls: list[list[str]] = []
    assert not gb.auto_recover_gm(run=lambda cmd, **kw: calls.append(cmd) or Done(3),
                                  sleep=lambda s: None)  # fmt: skip
    assert len(calls) == 1  # one attempt
    assert "FAILED (rc 3): stop and report" in capsys.readouterr().out
    # logged in, but never green: also a failure
    assert not gb.auto_recover_gm(run=lambda cmd, **kw: Done(0), sleep=lambda s: None)


def test_skipped_is_not_a_failure(gb: ModuleType, monkeypatch: pytest.MonkeyPatch,
                                  capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    monkeypatch.setattr(gb, "backend_health", lambda: health(mode="BOT"))
    ran: list[Any] = []
    assert gb.auto_recover_gm(run=lambda cmd, **kw: ran.append(cmd), sleep=lambda s: None)
    assert ran == [] and "SKIPPED: mux BOT" in capsys.readouterr().out


@pytest.mark.parametrize(("step", "expected"), [
    ("restart:sniffer", True), ("recreate:sniffer", True), ("restart:backend", False),
    ("start:sniffer", False), ("recreate:desktop", False),
])  # fmt: skip
def test_only_a_sniffer_restart_or_recreate_triggers_it(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch, step: str, expected: bool
) -> None:
    monkeypatch.setattr(gb, "run_process", lambda *a, **k: True)
    monkeypatch.setattr(gb, "watch", lambda *a, **k: True)
    monkeypatch.setattr(gb, "write_restore_marker", lambda: None)
    monkeypatch.setattr(gb, "backend_health", lambda: None)
    called: list[int] = []
    monkeypatch.setattr(gb, "auto_recover_gm", lambda: called.append(1) or True)
    s = gb.parse_step(step)
    if s.kind == "restart":
        gb.run_restart(s.services, 1, None)
    else:
        gb.run_start(s.services, 1, None, recreate=s.kind == "recreate")
    assert bool(called) is expected



def test_rm_step_stops_and_removes_only_its_containers(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2026-10-05: a clean switch between rathena and rathena-th. Containers only: never volumes
    (no -v) or images."""
    step = gb.parse_step("rm:sniffer,rathena")
    assert (step.kind, step.services) == ("rm", ["sniffer", "rathena"])
    with pytest.raises(ValueError):
        gb.parse_step("rm:bad name")
    ran: list[list[str]] = []
    monkeypatch.setattr(gb, "run_process", lambda label, cmd, guard, env=None: record(ran, cmd))
    monkeypatch.setattr(gb, "cgroup_paths", lambda: {})
    monkeypatch.setattr(gb.sys, "argv", ["guarded_build.py", "rm:sniffer,rathena"])
    monkeypatch.setattr(gb, "Guard", lambda *a, **k: _FakeGuard())
    assert gb.main() == 0
    assert ran == [[*gb.DEV, "rm", "-s", "-f", "sniffer", "rathena"]]
    assert "-v" not in ran[0]


class _FakeGuard:
    paths: dict[str, str] = {}

    def describe(self) -> str:
        return "test"

    def summary(self) -> str:
        return "test"
