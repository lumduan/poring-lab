"""OPTION A, the long-lived vision worker (docs/operations/vision-long-lived.md; Batt 2026-10-09):
guarded_build's worker: / execdev: / worker-stop: steps, the verified stop in EXEC MODE (fakes for
docker, the worker's processes and nvidia-smi on a fake clock), PairedR3 on the worker, the
TEST-only forced stop, and the proof runbook (scripts/runbooks/worker_proof.py) offline."""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "guarded_build.py"
PROOF = ROOT / "scripts" / "runbooks" / "worker_proof.py"
INIT = [b"/sbin/docker-init", b"--", b"sleep", b"infinity"]
SLEEP = [b"sleep", b"infinity"]
TRAIN = [b"python", b"-m", b"poring_vision.train", b"--smoke"]


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gb() -> ModuleType:
    return _load("guarded_build_worker", SCRIPT)


@pytest.fixture(autouse=True)
def _own_logdir(gb: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Step logs go to the TEST's directory, never the live $TMPDIR (2026-10-08 18:50)."""
    monkeypatch.setattr(gb, "LOGDIR", tmp_path)


# --- the steps' argv ----------------------------------------------------------------------------
def test_execdev_runs_the_command_inside_the_worker_with_two_bounds(gb: ModuleType) -> None:
    """The inner `timeout` bounds the PROCESS (a killed `docker exec` client never stops what it
    started); the outer one the client, 60 s later. No shell, the worker by name, vision only."""
    step = gb.parse_step("execdev:vision@3600=python -m poring_vision.train --smoke")
    assert (step.kind, step.services, step.seconds) == ("execdev", ["vision"], 3600.0)
    assert gb.exec_cmd(step) == [
        "timeout", "3660", "docker", "exec", "poring-lab-vision-worker-1",
        "timeout", "--kill-after=30", "3600", "python", "-m", "poring_vision.train", "--smoke",
    ]  # fmt: skip
    assert gb.exec_cmd(gb.parse_step("execdev:vision=true"))[:2] == ["timeout", "660"]
    for refused in ("execdev:gamestream=true", "execdev:vision", "execdev:vision=",
                    "execdev:backend=true", "execdev:vision@x=true"):  # fmt: skip
        with pytest.raises(ValueError):
            gb.parse_step(refused)


def test_the_worker_steps_start_and_stop_only_the_worker(gb: ModuleType) -> None:
    assert gb.parse_step("worker:vision").seconds == 120.0
    assert gb.parse_step("worker:vision@90").seconds == 90.0
    stop = gb.parse_step("worker-stop:vision")
    assert (stop.kind, stop.services, stop.seconds) == ("worker-stop", ["vision"], None)
    for refused in ("worker:gamestream", "worker:", "worker-stop:vision@5", "worker:vision@x",
                    "worker-stop:backend"):  # fmt: skip
        with pytest.raises(ValueError):
            gb.parse_step(refused)
    files = ["-f", "compose.yaml", "-f", "compose.vision-worker.yaml", "--profile", "vision-worker"]
    assert gb.worker_start_cmd() == ["docker", "compose", *files, "up", "-d", "--no-deps",
                                     "--no-build", "vision-worker"]  # fmt: skip
    assert gb.worker_stop_cmd() == ["docker", "compose", *files, "stop", "vision-worker"]


def test_only_the_idle_entrypoint_counts_as_idle(gb: ModuleType) -> None:
    assert gb.idle_argv(SLEEP) and gb.idle_argv(INIT)
    assert gb.idle_argv([b"/usr/bin/tini", b"--", b"sleep", b"infinity"])
    for job in ([b"timeout", b"60", b"sleep", b"infinity"], TRAIN, [], [b"sleep", b"60"],
                [b"sh", b"-c", b"sleep infinity"]):  # fmt: skip
        assert not gb.idle_argv(job), job
    procs = {1: (0, INIT), 2: (1, SLEEP), 7: (50, [b"timeout", *TRAIN]), 8: (7, TRAIN),
             9: (1, TRAIN)}  # fmt: skip
    assert set(gb.busy(procs)) == {7, 8, 9}
    assert gb.exec_roots(procs) == [7, 9]  # the exec'd top + an orphan adopted by the init


# --- the verified stop in EXEC MODE -------------------------------------------------------------
class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def sleep(self, dt: float) -> None:
        self.t += dt


class World:
    """The worker from the host: its processes (cgroup.procs), the GPU (nvidia-smi), the host's
    docker exec client, docker itself -- on a fake clock.

    ``sigint_exits_after``: the job exits this long after its SIGINT (None: ignores it);
    ``kill9``: kill -9 removes a process; ``cuda_sticks``: its CUDA context outlives the process
    (an EXITING task: gone from cgroup.procs, still in the worker's cgroup, still on the GPU) until
    the worker is killed, or for ever with ``docker_kill_frees`` False."""

    def __init__(self, clock: _Clock, *, sigint_exits_after: float | None = 4.0,
                 kill9: bool = True, cuda_sticks: bool = False, docker_kill_frees: bool = True,
                 nvidia_ok: bool = True, host_client: bool = False,
                 paused: bool = False) -> None:  # fmt: skip
        self.clock = clock
        self.state = "paused" if paused else "running"
        self.procs: dict[int, tuple[int, list[bytes]]] = {
            1001: (900, INIT),
            1002: (1001, SLEEP),
            2001: (50, [b"timeout", b"--kill-after=30", b"3600", *TRAIN]),
            2002: (2001, TRAIN),
            2003: (2002, TRAIN),  # a dataloader worker
        }
        self.gpu = {2002, 4242}  # 4242: Frigate's detector (root, not ours)
        self.exiting: set[int] = set()  # left cgroup.procs, still in the worker's cgroup
        self.host = {3001} if host_client else set()
        self.sigint_exits_after, self.kill9 = sigint_exits_after, kill9
        self.cuda_sticks, self.docker_kill_frees = cuda_sticks, docker_kill_frees
        self.nvidia_ok = nvidia_ok
        self.exit_at: float | None = None
        self.signals: list[tuple[int, int]] = []
        self.docker: list[list[str]] = []

    def _gone(self, pids: set[int]) -> None:
        for pid in pids:
            self.procs.pop(pid, None)
            if pid in self.gpu:
                if self.cuda_sticks:
                    self.exiting.add(pid)
                else:
                    self.gpu.discard(pid)

    def tick(self) -> None:
        if self.exit_at is not None and self.clock.t >= self.exit_at:
            self.exit_at = None
            self._gone({2001, 2002, 2003})

    # the fakes
    def docker_state(self, name: str) -> tuple[str, str]:
        assert name == "poring-lab-vision-worker-1"
        return self.state, "cid0"

    def worker_procs(self, name: str) -> dict[int, tuple[int, list[bytes]]] | None:
        self.tick()
        return {} if self.state == "stopped" else dict(self.procs)

    def gpu_pids(self) -> list[int] | None:
        self.tick()
        return sorted(self.gpu) if self.nvidia_ok else None

    def pid_cgroup(self, pid: int) -> str:
        inside = pid in self.procs or pid in self.exiting
        return "0::/system.slice/docker-cid0.scope\n" if inside else "0::/system.slice/frigate\n"

    def own_pids(self, pattern: bytes, pids: list[int] | None = None) -> list[int]:
        self.tick()
        if pattern == b"poring_vision":
            pool = list(self.procs) if pids is None else pids
            return [p for p in pool if p in self.procs and b"poring_vision" in b" ".join(
                self.procs[p][1])]  # fmt: skip
        assert pattern == b"docker\x00exec\x00poring-lab-vision-worker-1\x00"
        return sorted(self.host)

    def kill(self, pid: int, sig: int) -> None:
        self.signals.append((pid, sig))
        if sig == 2 and pid == 2001 and self.sigint_exits_after is not None:
            self.exit_at = self.clock.t + self.sigint_exits_after
        if sig == 9 and self.kill9:
            self.host.discard(pid)
            self._gone({pid})

    def run(self, cmd: list[str], **kw: object) -> None:
        self.docker.append(cmd)
        if cmd[:2] == ["docker", "unpause"]:
            self.state = "running"
        if cmd[:2] == ["docker", "kill"] and "--signal" not in cmd:
            self.state = "stopped"
            self.procs.clear()
            if self.docker_kill_frees:
                self.gpu -= {2002} | self.exiting
                self.exiting.clear()

    def install(self, gb: ModuleType, monkeypatch: pytest.MonkeyPatch) -> World:
        for name in ("docker_state", "worker_procs", "gpu_pids", "pid_cgroup", "own_pids"):
            monkeypatch.setattr(gb, name, getattr(self, name))
        monkeypatch.setattr(gb.os, "kill", self.kill)
        monkeypatch.setattr(gb.subprocess, "run", self.run)
        return self


def _verify(gb: ModuleType, world: World, clock: _Clock, host: bool = True) -> bool:
    return bool(gb.verify_stop("execdev:vision", gb.WORKER, True, gb.EXEC_HOST if host else None,
                               t0=0.0, sleep=clock.sleep, clock=clock, exec_mode=True))  # fmt: skip


def test_an_exec_that_exits_on_its_sigint_is_verified_with_the_worker_up(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The guard's SIGINT reached only the client: the exec'd process gets its OWN SIGINT (its top,
    the inner timeout, which forwards it), exits, and the worker stays up and idle."""
    clock = _Clock()
    world = World(clock).install(gb, monkeypatch)
    assert _verify(gb, world, clock)
    out = capsys.readouterr().out
    assert world.signals == [(2001, 2)] and world.docker == []
    assert "STOP VERIFIED execdev:vision after 4s" in out and "ESCALAT" not in out
    assert "up and idle (no CUDA context)" in out and world.state == "running"
    assert world.gpu == {4242}  # Frigate's detector is never ours


def test_a_lingering_exec_is_killed_inside_the_worker_and_verified(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """It ignores the SIGINT: after STOP_VERIFY_S, kill -9 of every job process in the worker (and
    the host client); verified with the worker still up -- no docker kill needed."""
    clock = _Clock()
    world = World(clock, sigint_exits_after=None, host_client=True).install(gb, monkeypatch)
    assert _verify(gb, world, clock)
    out = capsys.readouterr().out
    assert world.signals[0] == (2001, 2)
    assert set(world.signals[1:]) == {(2001, 9), (2002, 9), (2003, 9), (3001, 9)}
    assert "STOP NOT VERIFIED execdev:vision after 30s" in out
    assert "STOP VERIFIED execdev:vision after escalation" in out and "up and idle" in out
    assert not any(c[:2] == ["docker", "kill"] for c in world.docker)
    assert "WORKER KILLED" not in out and world.state == "running"


def test_a_cuda_context_left_after_the_kill_kills_the_worker_then_verifies(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """kill -9 took the processes, but the GPU still lists one of the worker's (an exiting task in
    its cgroup): `docker kill` of the worker itself, logged WORKER KILLED, then verified."""
    clock = _Clock()
    world = World(clock, sigint_exits_after=None, cuda_sticks=True).install(gb, monkeypatch)
    assert _verify(gb, world, clock)
    out = capsys.readouterr().out
    assert ["docker", "kill", "poring-lab-vision-worker-1"] in world.docker
    assert "our GPU processes [2002]" in out and "WORKER KILLED" in out
    assert "STOP VERIFIED execdev:vision after escalation" in out
    assert "worker poring-lab-vision-worker-1 stopped" in out and world.gpu == {4242}


def test_a_context_that_survives_the_worker_kill_is_stop_unverified(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    clock = _Clock()
    world = World(clock, sigint_exits_after=None, cuda_sticks=True, docker_kill_frees=False)
    world.install(gb, monkeypatch)
    assert not _verify(gb, world, clock)
    out = capsys.readouterr().out
    assert "WORKER KILLED" in out
    assert "STOP-UNVERIFIED execdev:vision: our GPU processes [2002] STILL PRESENT" in out


def test_an_unverifiable_gpu_is_never_called_verified_and_never_kills_the_worker(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """nvidia-smi not answering is not evidence: STOP-UNVERIFIED. The worker is idle, so killing it
    would change nothing about what the GPU holds."""
    clock = _Clock()
    world = World(clock, nvidia_ok=False).install(gb, monkeypatch)
    assert not _verify(gb, world, clock)
    out = capsys.readouterr().out
    assert "STOP-UNVERIFIED execdev:vision: GPU unverifiable (nvidia-smi failed)" in out
    assert not any(c[:2] == ["docker", "kill"] for c in world.docker)


def test_an_unreadable_worker_is_never_called_verified(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    clock = _Clock()
    world = World(clock).install(gb, monkeypatch)
    monkeypatch.setattr(gb, "worker_procs", lambda name: None)
    assert not _verify(gb, world, clock)
    assert "unverifiable (its state / cgroup unreadable)" in capsys.readouterr().out


def test_a_paused_worker_is_unpaused_before_its_job_is_signalled(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = _Clock()
    world = World(clock, paused=True).install(gb, monkeypatch)
    assert _verify(gb, world, clock)
    assert world.docker[0] == ["docker", "unpause", "poring-lab-vision-worker-1"]


def test_a_normal_end_leaves_the_worker_idle_and_checks_it(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    clock = _Clock()
    world = World(clock).install(gb, monkeypatch)
    world._gone({2001, 2002, 2003})
    assert gb.settle_exec("execdev:vision", gb.WORKER, gb.EXEC_HOST, 0, sleep=clock.sleep,
                          clock=clock)  # fmt: skip
    out = capsys.readouterr().out
    assert "the exec ended (rc=0)" in out and "up and idle" in out and world.signals == []


def test_a_client_that_died_alone_never_leaves_the_training_running(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The docker exec client ended (a daemon hiccup, a SIGINT to it by hand) but the training runs
    on in the worker: it is STOPPED and verified, never left running unguarded."""
    clock = _Clock()
    world = World(clock, sigint_exits_after=1.0).install(gb, monkeypatch)
    assert gb.settle_exec("execdev:vision", gb.WORKER, gb.EXEC_HOST, 130, sleep=clock.sleep,
                          clock=clock)  # fmt: skip
    out = capsys.readouterr().out
    assert "the docker exec client ended (rc=130) but worker busy" in out
    assert world.signals == [(2001, 2)] and "ESCALAT" not in out
    assert "STOP VERIFIED execdev:vision after" in out and "up and idle" in out


def test_a_stop_unverified_after_a_normal_end_fails_the_step(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    clock = _Clock()
    World(clock, nvidia_ok=False).install(gb, monkeypatch)
    assert not gb.settle_exec("execdev:vision", gb.WORKER, gb.EXEC_HOST, 0, sleep=clock.sleep,
                              clock=clock)  # fmt: skip
    assert "STOP-UNVERIFIED" in capsys.readouterr().out


def test_a_rundev_stop_is_untouched_by_exec_mode(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without exec_mode, verify_stop is the rundev one (a container that must be GONE)."""
    clock = _Clock()
    monkeypatch.setattr(gb, "verify_exec_stop", lambda *a, **k: pytest.fail("exec mode used"))
    monkeypatch.setattr(gb, "container_running", lambda name: False)
    monkeypatch.setattr(gb, "gpu_pids", lambda: [])
    monkeypatch.setattr(gb, "own_pids", lambda pat, pids=None: [])
    assert gb.verify_stop("rundev:vision", "c1", True, t0=0.0, sleep=clock.sleep, clock=clock)


# --- run_process on the worker: PairedR3, the abort, the TEST-only forced stop -------------------
class _QuietGuard:
    paths: dict[str, str] = {}

    def breach(self) -> None:
        return None

    def describe(self) -> str:
        return "test"

    def summary(self) -> str:
        return "test"


class _Schedule:
    """A PairedR3 stand-in: starts when told, pause, unpause (one closed cycle), then a latency
    trip -- unless ``trip`` is False."""

    def __init__(self, trip: bool = True) -> None:
        self.started, self.ticks, self.trip = False, 0, trip
        self.windows: list[dict[str, Any]] = [{"phase": "pre", "t0": 0.0}]

    def poll(self) -> None:
        pass

    def start(self) -> None:
        self.started = True
        self.windows.append({"phase": "on", "t0": 1.0})

    def tick(self) -> str | None:
        self.ticks += 1
        act = {1: "pause", 2: "unpause"}.get(self.ticks)
        if act:
            self.windows[-1]["t1"] = float(self.ticks)
            self.windows.append({"phase": "off" if act == "pause" else "on", "t0": 0.0})
        return act

    def summary(self) -> dict[str, Any]:
        return {"verdict": "pending", "pairs": [{"on": 1, "kept": True, "delta": 0.4}]}

    def breach(self) -> tuple[str, str, bool] | None:
        hit = ("latency", "paired median ON-OFF delta +6.00 ms", False)
        return hit if self.trip and self.ticks >= 3 else None


def _docker_recorder(gb: ModuleType, monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    docker: list[list[str]] = []
    real_run = gb.subprocess.run

    def run(cmd: list[str], **kw: object) -> object:
        if cmd[0] == "docker":
            docker.append(cmd)
            return None
        return real_run(cmd, **kw)

    monkeypatch.setattr(gb.subprocess, "run", run)
    monkeypatch.setattr(gb, "container_running", lambda name: True)
    monkeypatch.setattr(gb, "our_gpu_mib", lambda: 1400)
    monkeypatch.setattr(gb.time, "sleep", lambda s: None)
    return docker


def test_the_paired_schedule_pauses_and_unpauses_the_worker_and_its_stop_is_exec_verified(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """r3-paired.md unchanged: OFF = docker pause of the step's container -- here the WORKER, which
    freezes the exec'd process in it; an abort unpauses before its SIGINT and is verified in exec
    mode with the worker and the host pattern of the docker exec client."""
    docker = _docker_recorder(gb, monkeypatch)
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(gb, "verify_stop", lambda *a, **k: calls.append((a, k)) or True)
    r3 = _Schedule()
    ok = gb.run_process("execdev:vision", ["sleep", "30"], _QuietGuard(), r3=r3,
                        container=gb.WORKER, gpu=True, host=gb.EXEC_HOST,
                        exec_mode=True)  # fmt: skip
    out = capsys.readouterr().out
    w = "poring-lab-vision-worker-1"
    assert ok is False and r3.started
    assert docker == [["docker", "pause", w], ["docker", "unpause", w], ["docker", "unpause", w]]
    assert f"R3 pause {w}" in out and "ABORT execdev:vision: R3 latency: paired" in out
    assert calls == [(("execdev:vision", w, True, gb.EXEC_HOST), {"t0": calls[0][1]["t0"],
                                                                  "exec_mode": True})]  # fmt: skip


def test_an_io_trip_on_the_worker_is_verified_in_exec_mode(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(gb, "verify_stop", lambda *a, **k: calls.append((a, k)) or True)
    monkeypatch.setattr(gb.subprocess, "run", lambda cmd, **kw: None)

    class IoHit(_QuietGuard):
        def breach(self) -> tuple[str, float, str]:  # type: ignore[override]
            return ("quant-postgres", 29.8, "spike above 25.0%")

    assert gb.run_process("execdev:vision", ["sleep", "30"], IoHit(), container=gb.WORKER,
                          gpu=True, host=gb.EXEC_HOST, exec_mode=True) is False  # fmt: skip
    assert calls[0][0] == ("execdev:vision", gb.WORKER, True, gb.EXEC_HOST)
    assert calls[0][1]["exec_mode"] is True


def test_the_test_flag_forces_the_io_trip_path_after_one_measured_cycle(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """TEST ONLY (proof step 4): one planned R3 ON/OFF cycle runs, its pairs are printed, then the
    step is aborted exactly as on an IO trip (unpause, SIGINT, the exec-mode verified stop)."""
    docker = _docker_recorder(gb, monkeypatch)
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(gb, "verify_stop", lambda *a, **k: calls.append((a, k)) or True)
    r3 = _Schedule(trip=False)
    ok = gb.run_process("execdev:vision", ["sleep", "30"], _QuietGuard(), r3=r3,
                        container=gb.WORKER, gpu=True, host=gb.EXEC_HOST, exec_mode=True,
                        test_abort_cycles=1)  # fmt: skip
    out = capsys.readouterr().out
    assert ok is False and gb.r3_cycles(r3) == 1
    assert "ABORT execdev:vision: TEST forced stop after 1 R3 ON/OFF cycle(s)" in out
    assert 'R3 summary: {"verdict": "pending", "pairs": [{"on": 1' in out
    assert docker[-1] == ["docker", "unpause", gb.WORKER] and calls[0][1]["exec_mode"] is True


def test_without_the_test_flag_a_cycle_never_stops_anything(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _docker_recorder(gb, monkeypatch)
    monkeypatch.setattr(gb, "verify_stop", lambda *a, **k: pytest.fail("no stop expected"))
    monkeypatch.setattr(gb, "settle_exec", lambda *a, **k: True)
    ok = gb.run_process("execdev:vision", ["true"], _QuietGuard(), r3=_Schedule(trip=False),
                        container=gb.WORKER, gpu=True, host=gb.EXEC_HOST,
                        exec_mode=True)  # fmt: skip
    assert ok is True and "TEST forced" not in capsys.readouterr().out


def test_a_normal_exec_end_is_settled_and_a_failed_settle_fails_the_step(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[Any, ...]] = []
    monkeypatch.setattr(gb, "settle_exec", lambda *a, **k: seen.append(a) or False)
    assert gb.run_process("execdev:vision", ["true"], _QuietGuard(), container=gb.WORKER,
                          gpu=True, host=gb.EXEC_HOST, exec_mode=True) is False  # fmt: skip
    assert seen == [("execdev:vision", gb.WORKER, gb.EXEC_HOST, 0)]
    monkeypatch.setattr(gb, "settle_exec", lambda *a, **k: pytest.fail("rundev never settles"))
    assert gb.run_process("rundev:vision", ["true"], _QuietGuard()) is True


# --- main(): the refusals, then the same rules as rundev: --------------------------------------
class _FakeGuard(_QuietGuard):
    pass


def _main(gb: ModuleType, monkeypatch: pytest.MonkeyPatch, *argv: str) -> int:
    monkeypatch.setattr(gb, "cgroup_paths", lambda: {})
    monkeypatch.setattr(gb, "Guard", lambda *a, **k: _FakeGuard())
    monkeypatch.setattr(gb.sys, "argv", ["guarded_build.py", *argv])
    return int(gb.main())


STEP = "execdev:vision@3600=python -m poring_vision.train --smoke"


def test_execdev_is_refused_unless_the_worker_is_ready_before_any_gpu_rule(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(gb, "worker_not_ready", lambda name=None: "down (x stopped): start it")
    monkeypatch.setattr(gb, "gpu_rules", lambda *a: pytest.fail("worker first"))
    monkeypatch.setattr(gb, "run_process", lambda *a, **k: pytest.fail("nothing runs"))
    assert _main(gb, monkeypatch, STEP) == 3
    assert "REFUSED execdev:vision: WORKER down (x stopped)" in capsys.readouterr().out


def test_execdev_keeps_every_rundev_prestart_refusal(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(gb, "worker_not_ready", lambda name=None: None)
    monkeypatch.setattr(gb.frigate_r3, "prestart", lambda path: "R2: Ollama has a model loaded")
    monkeypatch.setattr(gb, "run_process", lambda *a, **k: pytest.fail("nothing runs"))
    assert _main(gb, monkeypatch, STEP) == 3
    assert "REFUSED execdev:vision: R2: Ollama" in capsys.readouterr().out


def test_execdev_runs_in_the_worker_with_r3_the_duty_cycle_and_exec_mode(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gb, "worker_not_ready", lambda name=None: None)
    monkeypatch.setattr(gb.frigate_r3, "prestart", lambda path: None)
    monkeypatch.setattr(gb.frigate_r3, "camera_reference", lambda: {})
    seen: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def run_process(*a: Any, **k: Any) -> bool:
        seen.append((a, k))
        gb.log_path(a[0]).write_text("done\n")  # the step's log, printed by main()
        return True

    monkeypatch.setattr(gb, "run_process", run_process)
    step = STEP + " --duty-file /lab-duty/duty.json"
    assert _main(gb, monkeypatch, "--test-abort-after-cycles", "1", step) == 0
    (label, cmd, _), kw = seen[0]
    assert label == "execdev:vision" and cmd == gb.exec_cmd(gb.parse_step(step))
    assert kw["container"] == gb.WORKER and kw["host"] == gb.EXEC_HOST
    assert kw["gpu"] is True and kw["exec_mode"] is True and kw["test_abort_cycles"] == 1
    assert kw["r3"].short is False and kw["duty"] is not None


def test_the_test_flag_needs_a_gpu_step(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _main(gb, monkeypatch, "--test-abort-after-cycles", "1", "worker-stop:vision") == 2
    assert "only with a GPU step" in capsys.readouterr().out


# --- the worker's readiness, start and stop -------------------------------------------------------
IDLE = {1001: (900, INIT), 1002: (1001, SLEEP)}


def _ready_world(gb: ModuleType, monkeypatch: pytest.MonkeyPatch, state: str = "running",
                 procs: dict[int, Any] | None = None,
                 mounts: dict[str, str] | None = None) -> None:  # fmt: skip
    monkeypatch.setattr(gb, "docker_state", lambda name: (state, "cid0"))
    monkeypatch.setattr(gb, "worker_procs", lambda name: IDLE if procs is None else procs)
    good = {dst: str(src) for dst, src in gb.WORKER_MOUNTS.items()}
    monkeypatch.setattr(gb, "worker_mounts", lambda name: good if mounts is None else mounts)


@pytest.mark.parametrize(("state", "procs", "mounts", "expected"), [
    ("absent", None, None, "down (poring-lab-vision-worker-1 absent)"),
    ("stopped", None, None, "down (poring-lab-vision-worker-1 stopped)"),
    ("paused", None, None, "not ready (poring-lab-vision-worker-1 paused)"),
    ("unknown", None, None, "not ready (poring-lab-vision-worker-1 unknown)"),
    ("running", {**IDLE, 7: (5, TRAIN)}, None, "is busy: 7 (python -m poring_vision.train"),
    ("running", None, {"/data": "/elsewhere/data"}, "was not started from this checkout"),
    ("running", None, None, None),
])  # fmt: skip
def test_the_worker_is_ready_only_up_idle_and_from_this_checkout(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch, state: str, procs: Any, mounts: Any,
    expected: str | None,
) -> None:  # fmt: skip
    _ready_world(gb, monkeypatch, state, procs, mounts)
    why = gb.worker_not_ready()
    assert (why is None) if expected is None else (why is not None and expected in why), why


def test_an_unreadable_worker_is_not_ready(gb: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    _ready_world(gb, monkeypatch)
    monkeypatch.setattr(gb, "worker_procs", lambda name: None)
    assert "unreadable" in (gb.worker_not_ready() or "")


def test_a_worker_start_runs_compose_under_the_io_guard_then_checks_it_idle(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    states = iter(["absent", "running", "running", "running"])
    monkeypatch.setattr(gb, "docker_state", lambda name: (next(states), "cid0"))
    monkeypatch.setattr(gb, "worker_procs", lambda name: IDLE)
    monkeypatch.setattr(gb, "gpu_pids", lambda: [4242])
    ran: list[list[str]] = []
    monkeypatch.setattr(gb, "run_process", lambda label, cmd, guard: ran.append(cmd) or True)
    watched: list[tuple[float, list[str]]] = []
    monkeypatch.setattr(gb, "watch", lambda s, g, what, stop: watched.append((s, stop)) or True)
    assert gb.run_worker(120, _FakeGuard()) == 0
    assert ran == [gb.worker_start_cmd()] and watched == [(120, gb.worker_stop_cmd())]
    assert "WORKER UP poring-lab-vision-worker-1: idle" in capsys.readouterr().out


def test_a_worker_that_is_not_idle_after_its_start_fails_it(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    states = iter(["stopped", "running", "running", "running"])
    monkeypatch.setattr(gb, "docker_state", lambda name: (next(states), "cid0"))
    monkeypatch.setattr(gb, "worker_procs", lambda name: {**IDLE, 1003: (1001, TRAIN)})
    monkeypatch.setattr(gb, "gpu_pids", lambda: [1003])
    monkeypatch.setattr(gb, "run_process", lambda *a, **k: True)
    monkeypatch.setattr(gb, "watch", lambda *a, **k: True)
    assert gb.run_worker(120, _FakeGuard()) == 1
    assert "WORKER NOT IDLE after its start" in capsys.readouterr().out


def test_a_running_worker_is_never_restarted(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Up and idle: nothing is started (a compose up could RECREATE it and kill a job). Busy or
    paused: REFUSED."""
    monkeypatch.setattr(gb, "run_process", lambda *a, **k: pytest.fail("no compose"))
    _ready_world(gb, monkeypatch)
    assert gb.run_worker(120, _FakeGuard()) == 0
    assert "already up and idle: nothing started" in capsys.readouterr().out
    _ready_world(gb, monkeypatch, procs={**IDLE, 7: (5, TRAIN)})
    assert gb.run_worker(120, _FakeGuard()) == 3
    _ready_world(gb, monkeypatch, state="paused")
    assert gb.run_worker(120, _FakeGuard()) == 3


def test_worker_stop_refuses_while_a_job_runs_and_verifies_the_stop(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ran: list[list[str]] = []
    monkeypatch.setattr(gb, "run_process", lambda label, cmd, guard: ran.append(cmd) or True)
    _ready_world(gb, monkeypatch, procs={**IDLE, 7: (5, TRAIN)})
    assert gb.run_worker_stop(_FakeGuard()) == 3 and ran == []
    assert "REFUSED worker-stop:vision" in capsys.readouterr().out
    states = iter(["running", "stopped"])
    monkeypatch.setattr(gb, "docker_state", lambda name: (next(states), "cid0"))
    monkeypatch.setattr(gb, "worker_procs", lambda name: IDLE)
    monkeypatch.setattr(gb, "gpu_pids", lambda: [4242])
    monkeypatch.setattr(gb, "own_pids", lambda pat, pids=None: [])
    assert gb.run_worker_stop(_FakeGuard()) == 0 and ran == [gb.worker_stop_cmd()]
    assert "WORKER STOPPED poring-lab-vision-worker-1" in capsys.readouterr().out
    monkeypatch.setattr(gb, "docker_state", lambda name: ("absent", ""))
    assert gb.run_worker_stop(_FakeGuard()) == 0


def test_main_returns_the_worker_steps_codes(
    gb: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gb, "run_worker", lambda seconds, guard: 3)
    assert _main(gb, monkeypatch, "worker:vision@60") == 3
    monkeypatch.setattr(gb, "run_worker_stop", lambda guard: 0)
    assert _main(gb, monkeypatch, "worker-stop:vision") == 0


# --- the proof runbook, offline ------------------------------------------------------------------
@pytest.fixture(scope="module")
def proof() -> ModuleType:
    sys.path.insert(0, str(ROOT / "scripts"))
    return _load("worker_proof", PROOF)


def test_the_proof_runs_the_plans_six_steps_and_only_guarded_docker(
    proof: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(proof.sys, "argv", ["worker_proof.py", "--cache", "v1-x", "--dry-run"])
    assert proof.main() == 0
    lines = capsys.readouterr().out.splitlines()
    assert [ln.split(":")[0] for ln in lines] == [
        "STEP 1 start", "STEP 2 idle", "STEP 3 probe", "STEP 4 forced", "STEP 5 warm",
        "STEP 6 stop",
    ]  # fmt: skip
    one, two, three, four, five, six = lines
    assert "quiet_start.py --quiet-min 10 --limit 25 -- python3 scripts/guarded_build.py" in one
    assert one.endswith("worker:vision@120") and "(reads only)" in two
    assert "execdev:vision@600=python -c" in three and "import torch, ultralytics" in three
    assert "cuda.is_initialized()" in three and "quiet_start" not in three
    assert four.startswith("STEP 4 forced: DUTY_START=4 DUTY_MIN=4 python3")
    assert "--test-abort-after-cycles 1 'execdev:vision@3600=python -m poring_vision.train" in four
    assert "--smoke" in four and "--duty-file /lab-duty/duty.json" in four
    assert "--test-abort" not in five and "execdev:vision@5400=" in five and "-warm" in five
    assert six.endswith("worker-stop:vision")
    for line in lines:  # every docker action goes through the guard
        assert "docker " not in line.replace("guarded_build", "")


def test_the_probe_parses_into_one_argv_without_a_shell(proof: ModuleType, gb: ModuleType) -> None:
    _, cmd = proof.commands("c", 10, "t", 3600, 5400, 1)[3]
    step = gb.parse_step(cmd[-1])
    assert step.command[:2] == ["python", "-c"] and len(step.command) == 3
    assert step.command[2] == proof.PROBE


def test_the_proof_reads_the_guards_stop_facts(proof: ModuleType) -> None:
    lines = [
        "[20:01:00] R3 schedule started [x]",
        "[20:07:10] ABORT execdev:vision: TEST forced stop after 1 R3 ON/OFF cycle(s) (...)",
        '[20:07:10] R3 summary: {"mode": "measure", "verdict": "pending", "median_delta_ms": 0.9,'
        ' "kept_pairs": 1, "remeasures": 0, "pairs": [{"on": 1, "kept": true, "delta": 0.9}]}',
        "[20:07:10] SIGINT 2001 (the exec'd process in poring-lab-vision-worker-1)",
        "[20:07:16] STOP VERIFIED execdev:vision after 6s: the exec'd process gone, ...",
    ]
    f = proof.guard_facts(lines)
    assert f["forced"] and f["verified"] and not f["unverified"] and not f["escalated"]
    assert (f["stop_s"], f["pairs"], f["kept"], f["worker_killed"]) == (6, 1, 1, False)
    g = proof.guard_facts(["STOP VERIFIED execdev:vision after escalation (47s); worker x",
                           "ESCALATED: docker kill x -- WORKER KILLED: start it"])  # fmt: skip
    assert g["stop_s"] == 47 and g["escalated"] and g["worker_killed"]


def test_the_proof_summarises_the_capture_stall_window(proof: ModuleType, tmp_path: Path) -> None:
    csv = tmp_path / "io.csv"
    head = ["utc", "mono_s"] + [f"{n}.{m}" for n in ("quant-postgres", "cron.service")
                                for m in ("full10", "some10", "full")]  # fmt: skip
    rows = [",".join(head)]
    for s, (pg, cron) in enumerate([(1.0, 0.0), (99.5, 40.0), (30.0, 2.0), (80.0, 0.0)]):
        rows.append(f"2026-10-09T13:00:{s:02d}+00:00,{s}.0,0,0,{pg},0,0,{cron}")
    csv.write_text("\n".join(rows) + "\n")
    t0 = datetime(2026, 10, 9, 13, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 10, 9, 13, 0, 1, tzinfo=UTC)
    out = proof.io_window(csv, t0, t1)
    assert "quant-postgres 99.5% (3 s > 25%)" in out and "cron.service 40.0% (1 s > 25%)" in out
    late = datetime(2026, 10, 9, 14, 0, 0, tzinfo=UTC)
    assert "no rows" in proof.io_window(csv, late, late)


def test_the_proof_never_starts_a_step_in_or_just_before_a_market_window(
    proof: ModuleType,
) -> None:
    ict = proof.ICT
    assert proof.in_market(datetime(2026, 10, 9, 9, 40, tzinfo=ict))
    assert proof.in_market(datetime(2026, 10, 9, 13, 50, tzinfo=ict))  # 14:00 is 10 min away
    assert not proof.in_market(datetime(2026, 10, 9, 19, 40, tzinfo=ict))
    assert not proof.in_market(datetime(2026, 10, 9, 10, 15, tzinfo=ict))
    assert proof.parse_steps("1-6") == [1, 2, 3, 4, 5, 6] and proof.parse_steps("3,5") == [3, 5]
    for bad in ("0", "7", "4-2", "3,3"):
        with pytest.raises(ValueError):
            proof.parse_steps(bad)


def test_the_proof_reads_the_worker_io_profile(proof: ModuleType) -> None:
    mib = 1 << 20
    prof = [(0.0, 0, 0), (1.0, 500 * mib, mib), (2.0, 900 * mib, mib), (12.0, 1000 * mib, 2 * mib)]
    text = proof.profile_text(prof)
    assert "read 1000 MiB" in text and "peak read 500 MiB/s at +1 s" in text
    assert "no samples" in proof.profile_text([])
