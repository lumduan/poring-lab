"""Is this host's GPU READY for the vision worker, and what should the setup recommend? (Batt
2026-11-17: "the setup should detect the GPU itself and recommend it to the user; with no GPU, use
the CPU"; "every user's hardware is different".)

A container brings everything but the GPU's kernel driver: that one piece is the host's (it shares
the host kernel). So the check is what a container cannot fix:
    NVIDIA  the driver (release >= NVIDIA_MIN_DRIVER: the vision image is CUDA 13.0) and the NVIDIA
            Container Toolkit (what compose's `driver: nvidia` reservation needs), plus the VRAM;
    Intel   a render node (/dev/dri/renderD*), the user in its group, the i915/xe kernel driver;
    AMD     no vision image for it yet: the CPU detector;
    none    the CPU detector.
Anything not ready -> the recommendation is dedicated-cpu (it always works) WITH the fixes that
would make the GPU usable; the person may still choose the GPU profile. The proof that the GPU path
runs is later and real: the vision image's own check (scripts/check_gpu.py in the worker).

Sizing: the vision worker's memory cap from the host's RAM (VISION_WORKER_MEM), the VRAM share 1.0
on a dedicated host. Stdlib only (the wizard's pre-flight runs before `uv sync`).
"""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

NVIDIA_MIN_DRIVER = 580  # CUDA 13.0 (torch 2.14.0+cu130); a CUDA 13.2 image refuses an R580 driver
TOOLKIT_BINARIES = (
    "nvidia-container-runtime-hook",
    "nvidia-container-toolkit",
    "nvidia-ctk",
    "nvidia-container-cli",
)
INTEL_DRIVERS = ("i915", "xe")
# The worker's cap: what the host can spare beside the backend, desktop and the runner (~4-6 GB,
# docs/setup/new-lab-host.md section 5), between 4 and 16 GiB.
HOST_RESERVE_GIB, WORKER_MIN_GIB, WORKER_MAX_GIB = 6, 4, 16

Runner = Callable[[Sequence[str]], tuple[int, str]]  # (rc, stdout)
Which = Callable[[str], str | None]


@dataclass(frozen=True)
class GpuReady:
    vendor: str  # nvidia | intel | amd | none
    ready: bool  # the GPU path can be set up here as it is
    profile: str  # the recommended LAB_HOST_PROFILE
    build_vision: bool  # build the GPU vision image
    found: tuple[str, ...] = ()  # what was seen, in plain words
    fixes: tuple[str, ...] = ()  # what would make the GPU usable (each a manual pointer)
    vram_gib: float | None = None
    worker_mem: str = ""  # VISION_WORKER_MEM proposal ("" = leave the overlay's default)
    vram_fraction: str = ""  # VISION_MAX_VRAM_FRACTION proposal
    notes: tuple[str, ...] = field(default_factory=tuple)

    def summary(self) -> str:
        head = {"nvidia": "an NVIDIA GPU", "intel": "an Intel GPU", "amd": "an AMD GPU"}.get(
            self.vendor, "no GPU"
        )
        state = "ready" if self.ready else "NOT ready" if self.vendor != "none" else ""
        parts = [f"{head}{' ' + state if state else ''}", *self.found]
        return "; ".join(parts) + f" -> {self.profile}"


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def nvidia_driver(root: Path = Path("/")) -> tuple[int, int] | None:
    """The loaded NVIDIA kernel module's version, from /proc/driver/nvidia/version
    ("NVRM version: NVIDIA UNIX Open Kernel Module for x86_64  580.95.05  Release Build ...")."""
    m = re.search(r"Kernel Module.*?\s(\d{3,4})\.(\d+)", _read(root / "proc/driver/nvidia/version"))
    return (int(m.group(1)), int(m.group(2))) if m else None


def nvidia_vram_gib(run: Runner, which: Which) -> float | None:
    if which("nvidia-smi") is None:
        return None
    rc, out = run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"])
    if rc != 0:
        return None
    sizes = [int(x) for x in re.findall(r"^\s*(\d+)\s*$", out, re.M)]
    return round(max(sizes) / 1024, 1) if sizes else None


def docker_has_nvidia_runtime(run: Runner) -> bool | None:
    rc, out = run(["docker", "info", "--format", "{{json .Runtimes}}"])
    return None if rc != 0 else '"nvidia"' in out


def intel_driver(root: Path = Path("/")) -> str | None:
    drm = root / "sys/class/drm"
    if not drm.is_dir():
        return None
    for card in sorted(drm.iterdir()):
        if (
            re.fullmatch(r"card\d+", card.name)
            and _read(card / "device/vendor").strip() == "0x8086"
        ):
            link = card / "device/driver"
            if link.exists():
                return os.path.basename(os.path.realpath(link))
    return None


def render_group_ok(root: Path = Path("/"), groups: Sequence[int] | None = None) -> bool | None:
    """The user may open the render node (in its group). None: there is no render node."""
    dri = root / "dev/dri"
    nodes = sorted(dri.glob("renderD*")) if dri.is_dir() else []
    if not nodes:
        return None
    mine = set(os.getgroups() if groups is None else groups)
    try:
        gid = nodes[0].stat().st_gid
    except OSError:
        return None
    return gid in mine or os.geteuid() == 0


def worker_mem(ram_gib: float | None) -> str:
    if ram_gib is None:
        return ""
    gib = int(ram_gib) - HOST_RESERVE_GIB
    return f"{max(WORKER_MIN_GIB, min(WORKER_MAX_GIB, gib))}g"


def recommend(
    vendor: str,
    *,
    ram_gib: float | None,
    root: Path = Path("/"),
    run: Runner | None = None,
    which: Which = shutil.which,
    groups: Sequence[int] | None = None,
    os_release: str | None = None,
) -> GpuReady:
    """The recommendation for a host whose detected GPU vendor is ``vendor``
    (setup_core.detect_gpu)."""
    run = run or (lambda cmd: (127, ""))
    mem = worker_mem(ram_gib)
    if vendor == "nvidia":
        found, fixes = [], []
        drv = nvidia_driver(root)
        if drv is None:
            fixes.append("load the NVIDIA driver (release 580 or newer): new-lab-host.md section 5")
        else:
            found.append(f"driver {drv[0]}.{drv[1]:02d}")
            if drv[0] < NVIDIA_MIN_DRIVER:
                fixes.append(
                    f"update the NVIDIA driver to release {NVIDIA_MIN_DRIVER} or newer "
                    "(the vision image is CUDA 13.0): new-lab-host.md section 5"
                )
        if not any(which(b) for b in TOOLKIT_BINARIES):
            fixes.append(
                "install the NVIDIA Container Toolkit, then `sudo nvidia-ctk runtime "
                "configure --runtime=docker` and restart Docker: new-lab-host.md section 5"
            )
        else:
            found.append("container toolkit")
            if docker_has_nvidia_runtime(run) is False:
                found.append("Docker has no 'nvidia' runtime yet (nvidia-ctk runtime configure)")
        vram = nvidia_vram_gib(run, which)
        if vram is not None:
            found.append(f"{vram:g} GiB VRAM")
        ready = not fixes
        return GpuReady(
            "nvidia",
            ready,
            "dedicated-nvidia" if ready else "dedicated-cpu",
            ready,
            tuple(found),
            tuple(fixes),
            vram,
            mem if ready else "",
            "1.0" if ready else "",
        )
    if vendor == "intel":
        found, fixes, notes = [], [], []
        drv = intel_driver(root)
        if drv in INTEL_DRIVERS:
            found.append(f"kernel driver {drv}")
        else:
            fixes.append(
                "the Intel GPU has no i915/xe kernel driver loaded: new-lab-host.md section 5"
            )
        member = render_group_ok(root, groups)
        if member is None:
            fixes.append("no render node (/dev/dri/renderD*): new-lab-host.md section 5")
        elif not member:
            fixes.append(
                "add yourself to the render group (`sudo usermod -aG render,video "
                "$USER`, then log out and in): new-lab-host.md section 5"
            )
        else:
            found.append("render node")
        release = os_release if os_release is not None else _read(root / "etc/os-release")
        if 'VERSION_ID="26.04"' not in release:
            notes.append(
                "the Intel vision image is built FROM ubuntu:26.04 and its GPU runtime must "
                "match the host's driver release; other Ubuntu releases are unverified"
            )
        ready = not fixes
        return GpuReady(
            "intel",
            ready,
            "dedicated-intel" if ready else "dedicated-cpu",
            ready,
            tuple(found),
            tuple(fixes),
            None,
            mem if ready else "",
            "1.0" if ready else "",
            tuple(notes),
        )
    if vendor == "amd":
        return GpuReady(
            "amd",
            False,
            "dedicated-cpu",
            False,
            ("no AMD vision image yet",),
            (),
            None,
            "",
            "",
            ("the CPU detector serves (manual section 9)",),
        )
    return GpuReady(
        "none",
        False,
        "dedicated-cpu",
        False,
        (),
        (),
        None,
        "",
        "",
        ("the CPU detector serves (manual section 9)",),
    )
