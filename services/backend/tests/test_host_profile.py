"""scripts/host_profile.py + guarded_build (ADR-0022 decision 3): a host is DEDICATED only by
declaration; VM 103 (unset) keeps every shared rule and exactly its old compose commands."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import host_profile as hp  # noqa: E402


def load_gb(monkeypatch: pytest.MonkeyPatch, profile: str | None) -> ModuleType:
    if profile is None:
        monkeypatch.setenv(hp.ENV_KEY, "")  # empty = unset; the repo's .env is not read by tests
        monkeypatch.setattr(hp, "dotenv_value", lambda key, path: None)
    else:
        monkeypatch.setenv(hp.ENV_KEY, profile)
    path = ROOT / "scripts" / "guarded_build.py"
    spec = importlib.util.spec_from_file_location(f"gb_{profile}", path)
    assert spec and spec.loader
    gb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gb)
    return gb


def test_unset_is_the_strict_shared_profile_and_a_typo_is_refused(tmp_path: Path) -> None:
    assert hp.current({}, tmp_path / "missing.env").name == "shared-nvidia"
    env = tmp_path / ".env"
    env.write_text("# c\nHOST_LAN_IP=192.168.1.228\nLAB_HOST_PROFILE=dedicated-intel\n")
    prof = hp.current({}, env)
    assert (prof.name, prof.accel, prof.shared, prof.detect_backend) == (
        "dedicated-intel", "xpu", False, "openvino")  # fmt: skip
    assert hp.current({hp.ENV_KEY: "shared-nvidia"}, env).shared is True  # the environment first
    with pytest.raises(SystemExit, match="not one of"):
        hp.current({hp.ENV_KEY: "dedicated"}, env)


def test_dedicated_nvidia_is_the_cuda_path_without_the_shared_rules(tmp_path: Path) -> None:
    """ADR-0022 Amendment 2026-11-12 (Batt: "NVIDIA on a new machine still needs a profile"):
    shared-nvidia's CUDA path -- torch on cuda, nvidia-smi -- on a DEDICATED host, through its own
    two overlays."""
    env = tmp_path / ".env"
    env.write_text("HOST_LAN_IP=10.0.1.5\nLAB_HOST_PROFILE=dedicated-nvidia\n")
    prof = hp.current({}, env)
    assert prof == hp.HostProfile(
        "dedicated-nvidia", "cuda", False, ("compose.nvidia.yaml",),
        ("compose.vision-worker.nvidia.yaml",), "torch", "nvidia-smi",
    )  # fmt: skip
    shared = hp.PROFILES["shared-nvidia"]
    assert (prof.accel, prof.detect_backend, prof.gpu_lister) == (
        shared.accel, shared.detect_backend, shared.gpu_lister)  # fmt: skip
    assert shared.shared and not prof.shared
    for name in (*prof.vision_overlay, *prof.worker_overlay):
        assert (ROOT / name).is_file(), name
    assert sorted(hp.PROFILES) == ["dedicated-intel", "dedicated-nvidia", "shared-nvidia"]
    assert hp.DEFAULT == "shared-nvidia"  # a host is dedicated only by declaration


def test_vm103_keeps_exactly_its_old_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    gb = load_gb(monkeypatch, None)
    assert gb.PROFILE.name == "shared-nvidia"
    assert gb.VISION_DEV == ["-f", "compose.yaml", "-f", "compose.vision-dev.yaml"]
    assert gb.VISION_FILES == []
    assert gb.VISION_WORKER == ["-f", "compose.yaml", "-f", "compose.vision-worker.yaml",
                                "--profile", "vision-worker"]  # fmt: skip


def test_bot_server_adds_its_overlays_last(monkeypatch: pytest.MonkeyPatch) -> None:
    gb = load_gb(monkeypatch, "dedicated-intel")
    assert gb.VISION_DEV == ["-f", "compose.yaml", "-f", "compose.vision-dev.yaml",
                             "-f", "compose.intel.yaml"]  # fmt: skip
    assert gb.VISION_FILES == ["-f", "compose.yaml", "-f", "compose.intel.yaml"]
    assert gb.VISION_WORKER == ["-f", "compose.yaml", "-f", "compose.vision-worker.yaml",
                                "-f", "compose.vision-worker.intel.yaml",
                                "--profile", "vision-worker"]  # fmt: skip
    step = gb.parse_step("rundev:vision@60=python -c pass")
    assert gb.run_cmd(step)[4:10] == gb.VISION_DEV


def test_a_dedicated_nvidia_host_adds_its_overlays_last(monkeypatch: pytest.MonkeyPatch) -> None:
    gb = load_gb(monkeypatch, "dedicated-nvidia")
    assert gb.VISION_DEV == ["-f", "compose.yaml", "-f", "compose.vision-dev.yaml",
                             "-f", "compose.nvidia.yaml"]  # fmt: skip
    assert gb.VISION_FILES == ["-f", "compose.yaml", "-f", "compose.nvidia.yaml"]
    assert gb.VISION_WORKER == ["-f", "compose.yaml", "-f", "compose.vision-worker.yaml",
                                "-f", "compose.vision-worker.nvidia.yaml",
                                "--profile", "vision-worker"]  # fmt: skip
    step = gb.parse_step("rundev:vision@60=python -c pass")
    assert gb.run_cmd(step)[4:10] == gb.VISION_DEV


def test_a_dedicated_nvidia_host_lists_its_gpu_with_nvidia_smi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The NVIDIA case of the GPU lister (not the DRM fdinfo walk): an abort is verified the way
    VM 103 verifies it."""
    gb = load_gb(monkeypatch, "dedicated-nvidia")

    def no_drm() -> None:
        raise AssertionError("drm_pids on an NVIDIA host")

    monkeypatch.setattr(gb.host_profile, "drm_pids", no_drm)
    seen: list[list[str]] = []

    def fake_run(cmd: list[str], **kw: object) -> object:
        seen.append(cmd)
        return type("R", (), {"stdout": "4242\n77\n"})()

    monkeypatch.setattr(gb.subprocess, "run", fake_run)
    assert gb.gpu_pids() == [4242, 77]
    assert seen[0][0] == "nvidia-smi"


def test_a_dedicated_host_skips_r1_r3_and_a_shared_one_keeps_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gb = load_gb(monkeypatch, None)
    step = gb.parse_step("rundev:vision@60=python -c pass")
    called: list[str] = []
    monkeypatch.setattr(gb, "gpu_rules", lambda s, b: called.append("r3") or None)
    for name in ("dedicated-intel", "dedicated-nvidia"):
        assert gb.gpu_guards(step, Path("x"), hp.PROFILES[name]) == (None, None, None), name
    assert called == []  # never asks Frigate there
    assert gb.gpu_guards(step, Path("x"), hp.PROFILES["shared-nvidia"]) is None  # refused
    assert called == ["r3"]


def test_a_declared_dedicated_host_with_capture_services_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gb = load_gb(monkeypatch, None)
    shared = hp.PROFILES["shared-nvidia"]
    for ded in (hp.PROFILES["dedicated-intel"], hp.PROFILES["dedicated-nvidia"]):
        assert gb.dedicated_refusal(["quant-postgres", "frigate"], ded) is not None
        why = gb.dedicated_refusal(["quant-postgres", "frigate"], ded)
        assert "frigate, quant-postgres" in str(why) and ded.name in str(why)
        assert gb.dedicated_refusal(["cron.service(capture-streaming-pro)"], ded) is None
    assert gb.dedicated_refusal(["quant-postgres"], shared) is None


def test_the_guard_with_nothing_to_watch_never_trips(monkeypatch: pytest.MonkeyPatch) -> None:
    gb = load_gb(monkeypatch, None)
    guard = gb.Guard({}, 10.0, 10.0, sustain=30.0)
    assert guard.breach() is None and guard.breach() is None
    assert "dedicated host" in guard.describe()


def test_drm_holders_are_found_and_unreadable_own_processes_are_unverifiable(
    tmp_path: Path,
) -> None:
    proc = tmp_path / "proc"
    for pid, infos in {"11": ["pos:\t0\nflags:\t02\n"],
                       "12": ["pos:\t0\n", "pos:\t0\ndrm-driver:\ti915\ndrm-client-id:\t7\n"],
                       "13": []}.items():  # fmt: skip
        (proc / pid / "fdinfo").mkdir(parents=True)
        for i, text in enumerate(infos):
            (proc / pid / "fdinfo" / str(i)).write_text(text)
    (proc / "self").mkdir()
    (proc / "13" / "cmdline").write_bytes(b"python\0-m\0poring_vision.detect_server\0")
    (proc / "14" / "fdinfo").mkdir(parents=True)
    (proc / "14" / "cmdline").write_bytes(b"sshd-session: bot@notty\0")
    assert hp.drm_pids(proc) == [12]
    (proc / "14" / "fdinfo").chmod(0)  # the SSH session: non-dumpable, never our GPU work
    try:
        if os.access(proc / "14" / "fdinfo", os.R_OK):
            pytest.skip("running as root: permissions are not enforced")
        assert hp.drm_pids(proc) == [12]  # skipped: it does not run our code
        (proc / "13" / "fdinfo").chmod(0)
        assert hp.drm_pids(proc) is None  # OUR code and unreadable: the answer is unverifiable
        assert hp.drm_pids(proc, uid=os.getuid() + 1) == [12]  # someone else's: skipped
    finally:
        (proc / "13" / "fdinfo").chmod(0o755)
        (proc / "14" / "fdinfo").chmod(0o755)
