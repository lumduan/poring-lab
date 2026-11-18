"""scripts/gpu_ready.py (Batt 2026-11-17: "detect the GPU and recommend it; no GPU -> the CPU"):
what a container cannot bring (the driver, the toolkit, the render group) decides the
recommendation, and anything not ready falls back to dedicated-cpu WITH the fixes, never a dead
end."""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import gpu_ready as g  # noqa: E402

DRIVER_580 = (
    "NVRM version: NVIDIA UNIX Open Kernel Module for x86_64  580.95.05  Release Build"
    "  (dvs-builder@U16-I3-B03-4-3)  Thu Sep 18 10:31:32 UTC 2025\n"
)
DRIVER_550 = (
    "NVRM version: NVIDIA UNIX x86_64 Kernel Module  550.120  Fri Sep 13 10:10:01 UTC 2024\n"
)


def nvidia_root(tmp_path: Path, version: str = DRIVER_580) -> Path:
    (tmp_path / "proc/driver/nvidia").mkdir(parents=True)
    (tmp_path / "proc/driver/nvidia/version").write_text(version)
    return tmp_path


def runner(answers: dict[str, tuple[int, str]]) -> g.Runner:
    def run(cmd: Sequence[str]) -> tuple[int, str]:
        return answers.get(cmd[0], (127, ""))

    return run


def which_of(*present: str) -> g.Which:
    return lambda name: f"/usr/bin/{name}" if name in present else None


def test_an_nvidia_card_with_driver_and_toolkit_is_recommended(tmp_path: Path) -> None:
    root = nvidia_root(tmp_path)
    run = runner({"nvidia-smi": (0, "8151\n"), "docker": (0, '{"nvidia":{},"runc":{}}')})
    r = g.recommend(
        "nvidia", ram_gib=15.6, root=root, run=run, which=which_of("nvidia-ctk", "nvidia-smi")
    )
    assert (r.ready, r.profile, r.build_vision) == (True, "dedicated-nvidia", True)
    assert r.vram_gib == 8.0 and (r.worker_mem, r.vram_fraction) == ("9g", "1.0")
    assert "driver 580.95" in r.found and not r.fixes
    assert r.summary().startswith("an NVIDIA GPU ready; driver 580.95")


def test_a_card_older_than_the_cuda_builds_gets_the_cpu_detector(tmp_path: Path) -> None:
    """2026-11-18: R580 still drives Pascal (GTX 10), but the CUDA image's builds carry code for
    compute capability 7.5 and newer only (onnxruntime-gpu 1.31.1: sm_75 ... sm_120a, no PTX). An
    RTX 5060 (12.0) is ready; a GTX 1080 (6.1) falls back to the CPU and says why."""

    def smi(cap: str) -> g.Runner:
        def run(cmd: Sequence[str]) -> tuple[int, str]:
            if cmd[0] == "nvidia-smi":
                return (0, f"{cap}\n") if "--query-gpu=compute_cap" in cmd else (0, "8151\n")
            return (0, '{"nvidia":{},"runc":{}}')

        return run

    root = nvidia_root(tmp_path)
    which = which_of("nvidia-ctk", "nvidia-smi")
    new = g.recommend("nvidia", ram_gib=15.6, root=root, run=smi("12.0"), which=which)
    assert (new.ready, new.profile) == (True, "dedicated-nvidia")
    assert "compute capability 12.0" in new.found and not new.fixes
    old = g.recommend("nvidia", ram_gib=15.6, root=root, run=smi("6.1"), which=which)
    assert (old.ready, old.profile, old.build_vision) == (False, "dedicated-cpu", False)
    assert len(old.fixes) == 1 and "compute capability 6.1" in old.fixes[0]
    assert "GTX 16 / RTX 20 and newer" in old.fixes[0]
    assert g.nvidia_compute_caps(smi("7.5\n8.6"), which) == [(7, 5), (8, 6)]
    assert g.nvidia_compute_caps(smi("[N/A]"), which) is None  # unknown: no verdict from it


def test_an_old_driver_or_no_toolkit_falls_back_to_the_cpu_with_the_fixes(tmp_path: Path) -> None:
    old = g.recommend(
        "nvidia",
        ram_gib=16,
        root=nvidia_root(tmp_path / "a", DRIVER_550),
        which=which_of("nvidia-ctk"),
    )
    assert (old.ready, old.profile, old.build_vision, old.worker_mem) == (
        False,
        "dedicated-cpu",
        False,
        "",
    )
    assert any("release 580 or newer" in f for f in old.fixes)
    bare = g.recommend("nvidia", ram_gib=16, root=nvidia_root(tmp_path / "b"), which=which_of())
    assert bare.profile == "dedicated-cpu"
    assert any("NVIDIA Container Toolkit" in f for f in bare.fixes)
    unloaded = g.recommend("nvidia", ram_gib=16, root=tmp_path / "c", which=which_of("nvidia-ctk"))
    assert any("load the NVIDIA driver" in f for f in unloaded.fixes)


def test_a_toolkit_without_the_docker_runtime_is_ready_but_noted(tmp_path: Path) -> None:
    r = g.recommend(
        "nvidia",
        ram_gib=32,
        root=nvidia_root(tmp_path),
        run=runner({"docker": (0, '{"runc":{}}')}),
        which=which_of("nvidia-container-runtime-hook"),
    )
    assert r.ready and r.worker_mem == "16g"  # 32 GiB: the cap's upper bound
    assert any("no 'nvidia' runtime" in f for f in r.found)


def intel_root(tmp_path: Path, driver: str = "i915") -> Path:
    card = tmp_path / "sys/class/drm/card0/device"
    card.mkdir(parents=True)
    (card / "vendor").write_text("0x8086\n")
    (tmp_path / "drivers" / driver).mkdir(parents=True)
    (card / "driver").symlink_to(tmp_path / "drivers" / driver)
    (tmp_path / "dev/dri").mkdir(parents=True)
    (tmp_path / "dev/dri/renderD128").write_text("")
    return tmp_path


def test_an_intel_card_needs_its_driver_and_the_render_group(tmp_path: Path) -> None:
    root = intel_root(tmp_path)
    gid = (root / "dev/dri/renderD128").stat().st_gid
    ok = g.recommend(
        "intel", ram_gib=15.0, root=root, groups=[gid], os_release='VERSION_ID="26.04"\n'
    )
    assert (ok.ready, ok.profile, ok.worker_mem, ok.notes) == (True, "dedicated-intel", "9g", ())
    if os.geteuid() != 0:
        out = g.recommend(
            "intel",
            ram_gib=15.0,
            root=root,
            groups=[gid + 12345],
            os_release='VERSION_ID="26.04"\n',
        )
        assert out.profile == "dedicated-cpu" and any("render group" in f for f in out.fixes)
    other_os = g.recommend(
        "intel", ram_gib=15.0, root=root, groups=[gid], os_release='VERSION_ID="24.04"\n'
    )
    assert other_os.ready and any("ubuntu:26.04" in n for n in other_os.notes)


def test_no_gpu_gets_the_cpu_detector(tmp_path: Path) -> None:
    r = g.recommend("none", ram_gib=8, root=tmp_path)
    assert (r.ready, r.profile, r.build_vision) == (False, "dedicated-cpu", False)
    assert any("CPU detector" in n for n in r.notes)


def amd_root(tmp_path: Path, driver: str | None = "amdgpu", igpu: bool = True) -> Path:
    """An AMD card at card1 / renderD129, beside an Intel iGPU at card0 / renderD128 (a common
    desktop): its OWN render node must be the one proposed. As sysfs: /sys/class/drm/cardN/device
    is the PCI device, with its vendor, its driver link and drm/renderDN."""
    cards = [("card1", "0x1002", driver, "renderD129")]
    if igpu:
        cards.insert(0, ("card0", "0x8086", "i915", "renderD128"))
    (tmp_path / "dev/dri").mkdir(parents=True)
    for card, vendor, drv, node in cards:
        pci = tmp_path / "sys/devices" / card
        (pci / "drm" / node).mkdir(parents=True)
        (pci / "vendor").write_text(vendor + "\n")
        if drv is not None:
            (tmp_path / "drivers" / drv).mkdir(parents=True, exist_ok=True)
            (pci / "driver").symlink_to(tmp_path / "drivers" / drv)
        cls = tmp_path / "sys/class/drm" / card
        cls.mkdir(parents=True)
        (cls / "device").symlink_to(pci, target_is_directory=True)
        (tmp_path / "dev/dri" / node).write_text("")
    return tmp_path


def test_an_amd_card_gets_the_vulkan_profile_with_its_own_render_node(tmp_path: Path) -> None:
    """ADR-0022 Amendment 2026-11-18b (Batt chose option (b)): an AMD card on amdgpu, its render
    node open to the user -> dedicated-amd, the Vulkan image, GPU_RENDER_NODE = the card's own
    node (never the iGPU's renderD128), and the note that RADV itself is unverified."""
    root = amd_root(tmp_path)
    gid = (root / "dev/dri/renderD129").stat().st_gid
    r = g.recommend("amd", ram_gib=15.0, root=root, groups=[gid])
    assert (r.ready, r.profile, r.build_vision) == (True, "dedicated-amd", True)
    assert (r.render_node, r.worker_mem, r.vram_fraction) == ("/dev/dri/renderD129", "9g", "1.0")
    assert r.found == ("kernel driver amdgpu", "render node /dev/dri/renderD129")
    assert r.fixes == () and r.notes == (g.AMD_UNVERIFIED,)
    assert "unverified" in g.AMD_UNVERIFIED and "check_webgpu.py" in g.AMD_UNVERIFIED
    if os.geteuid() != 0:
        out = g.recommend("amd", ram_gib=15.0, root=root, groups=[gid + 12345])
        assert (out.profile, out.render_node) == ("dedicated-cpu", "")
        assert any("render group" in f for f in out.fixes)


def test_an_amd_card_on_the_old_radeon_driver_or_none_gets_the_cpu_detector(
    tmp_path: Path,
) -> None:
    """RADV (Mesa's Vulkan driver) runs on amdgpu only: the old radeon driver, or none, is a fix
    and the CPU detector meanwhile, never a vision image that cannot reach the card."""
    for n, (driver, words) in enumerate([("radeon", "old radeon"), (None, "no amdgpu")]):
        root = amd_root(tmp_path / str(n), driver=driver, igpu=False)
        gid = (root / "dev/dri/renderD129").stat().st_gid
        r = g.recommend("amd", ram_gib=15.0, root=root, groups=[gid])
        assert (r.ready, r.profile, r.build_vision, r.render_node) == (
            False, "dedicated-cpu", False, ""
        ), driver  # fmt: skip
        assert any(words in f for f in r.fixes), r.fixes
    bare = g.recommend("amd", ram_gib=15.0, root=tmp_path / "empty")
    assert bare.profile == "dedicated-cpu" and any("render node" in f for f in bare.fixes)


def test_the_worker_cap_follows_the_ram() -> None:
    assert [g.worker_mem(x) for x in (None, 7.6, 15.5, 31.2, 64.0)] == [
        "",
        "4g",
        "9g",
        "16g",
        "16g",
    ]
