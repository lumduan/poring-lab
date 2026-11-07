"""ADR-0022 decision 3: a host profile says what a host has, instead of code assuming it.

The profile is named by LAB_HOST_PROFILE: the environment first, else the repo's `.env`. Unset
means `shared-nvidia` -- ubuntu-docker (VM 103), the STRICT profile. A host is dedicated only by
declaration, never by default, and guarded_build refuses a declared-dedicated host that runs the
capture services the shared rules protect (`dedicated_refusal`).

    shared-nvidia     ubuntu-docker: the RTX 5060 Ti beside Frigate and Ollama, the disk beside
                      quant capture. R1-R3 and the IO guard apply (CLAUDE.md rule 5).
    dedicated-intel   bot-server (192.168.1.228): the Arc A380, nothing else on the machine
                      (Batt 2026-11-07: "use it fully, no limits like this machine"). No R1-R3
                      (no Frigate), no IO guard (no capture to protect). The Intel vision image
                      (compose.intel.yaml, compose.vision-worker.intel.yaml).

Stdlib only: guarded_build runs under the system python3.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ENV_KEY = "LAB_HOST_PROFILE"
DEFAULT = "shared-nvidia"


@dataclass(frozen=True)
class HostProfile:
    name: str
    accel: str  # poring_vision.accel kind: cuda | xpu | cpu
    shared: bool  # True: R1-R3 and the IO guard (Frigate's GPU, quant's disk)
    vision_overlay: tuple[str, ...]  # compose files after compose.yaml for the vision service
    worker_overlay: tuple[str, ...]  # ... after compose.vision-worker.yaml for the worker
    detect_backend: str  # poring_vision.detect_server --backend
    gpu_lister: str  # how our GPU processes are found: nvidia-smi | drm-fdinfo


PROFILES = {
    "shared-nvidia": HostProfile(
        "shared-nvidia", "cuda", True, (), (), "torch", "nvidia-smi"
    ),
    "dedicated-intel": HostProfile(
        "dedicated-intel", "xpu", False, ("compose.intel.yaml",),
        ("compose.vision-worker.intel.yaml",), "openvino", "drm-fdinfo",
    ),
}  # fmt: skip


def dotenv_value(key: str, path: Path) -> str | None:
    """The first `KEY=value` line of a .env file (no quotes, no expansion: the lab's .env style)."""
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return None
    for line in lines:
        k, eq, v = line.partition("=")
        if eq and k.strip() == key:
            return v.strip()
    return None


def current(env: Mapping[str, str] | None = None, dotenv: Path = REPO / ".env") -> HostProfile:
    """This host's profile; an unknown name is refused (exit), never replaced by a default."""
    name = (os.environ if env is None else env).get(ENV_KEY) or dotenv_value(ENV_KEY, dotenv)
    name = name or DEFAULT
    if name not in PROFILES:
        raise SystemExit(f"{ENV_KEY}={name!r}: not one of {sorted(PROFILES)} (ADR-0022)")
    return PROFILES[name]


def files(*base: str, overlay: tuple[str, ...] = ()) -> list[str]:
    """`-f` arguments: the base compose files, then the profile's overlay (it must come last)."""
    return [arg for name in (*base, *overlay) for arg in ("-f", name)]


def ours_unreadable(d: Path) -> bool:
    """An fdinfo we may not read, of a process of our uid: does it matter? Non-dumpable processes
    (systemd --user, sd-pam, the SSH session itself) are unreadable by design and never hold our
    GPU work; one whose command line names our code (`poring`) does matter. A command line we
    cannot read matters too (fail closed)."""
    try:
        return b"poring" in (d / "cmdline").read_bytes()
    except FileNotFoundError:
        return False
    except PermissionError:
        return True


def drm_pids(proc: Path = Path("/proc"), uid: int | None = None) -> list[int] | None:
    """Every process holding a DRM (GPU) file: its fdinfo has a `drm-driver:` line (i915, xe,
    amdgpu). None when one of OUR processes running our code cannot be read: the answer would be
    unverifiable (2026-11-07: failing on ANY unreadable own process made it unanswerable over
    SSH, whose sshd-session is non-dumpable)."""
    me = os.getuid() if uid is None else uid
    out: list[int] = []
    for d in proc.iterdir():
        if not d.name.isdigit():
            continue
        try:
            owner = d.stat().st_uid
            fds = list((d / "fdinfo").iterdir())
        except FileNotFoundError:
            continue  # the process ended
        except PermissionError:
            if owner == me and ours_unreadable(d):
                return None
            continue
        for fd in fds:
            try:
                text = fd.read_text(errors="replace")
            except FileNotFoundError:
                continue
            except PermissionError:
                if owner == me and ours_unreadable(d):
                    return None
                break
            if "\ndrm-driver:" in f"\n{text}":
                out.append(int(d.name))
                break
    return sorted(out)
