#!/usr/bin/python3
"""poring-lab-vram.service's helper (installed as /usr/local/libexec/poring-lab-vram.py): the
Intel GPU's VRAM use for the console's /hardware page (Batt 2026-11-12: "show VRAM too; you can
sudo anyway").

Why a root helper: i915 has NO unprivileged source for device-memory use. Its query ioctl reports
the free size only to CAP_PERFMON, and debugfs (/sys/kernel/debug, mode 0700) is root only. The
backend reads plain files only and runs unprivileged (hardware.py), so this loop, as root, reads
each i915 card's ``i915_gem_objects`` every PERIOD_S and writes the numbers, nothing else, to
``OUT_DIR/vram.json``. The backend sees OUT_DIR read-only at /host-shm (compose.yaml).

Every DRM card bound to i915 that has a ``local0`` region (a discrete card: the Arc's VRAM) gets
an entry; an integrated GPU has no local0 and is skipped. Clock: ``t_mono_ns`` is
CLOCK_MONOTONIC, the backend's own clock (one kernel), so it can judge the file's age.

stdlib only; it takes no input. The file is written through a directory handle opened with
O_NOFOLLOW (never through a symlink) and replaced atomically, mode 0644.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

PERIOD_S = 2.0
DRM = Path("/sys/class/drm")
DEBUGFS = Path("/sys/kernel/debug/dri")
OUT_DIR = Path("/dev/shm/poring-lab-hwshm")
OUT_NAME = "vram.json"
VERSION = 1
_CARD = re.compile(r"^card(\d+)$")
# the DRM buddy allocator's summary line of a region: "chunk_size: 4KiB, total: 6088MiB, free: ..."
_BUDDY = re.compile(r"total:\s*(\d+)\s*([KMG]i?B)\s*,\s*free:\s*(\d+)\s*([KMG]i?B)")
_USAGE = re.compile(r"^\s*usage:\s*(\d+)\s*$")
# a memory region's header line in the dump (i915_gem_objects prints one block per region)
_REGION = re.compile(r"^(system|stolen|local\d|smem|lmem)[\w-]*:")
_UNIT = {
    "KiB": 1 << 10,
    "MiB": 1 << 20,
    "GiB": 1 << 30,
    "KB": 1 << 10,
    "MB": 1 << 20,
    "GB": 1 << 30,
}


def parse_local0(text: str) -> dict[str, int] | None:
    """PURE: the ``local0`` region of an ``i915_gem_objects`` dump -> total / free / used bytes
    (the buddy allocator's line) and ``usage_b`` (TTM's own count, when printed); None when the
    dump has no local0 region (an integrated GPU) or no buddy line in it."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.startswith("local0:")), None)
    if start is None:
        return None
    usage: int | None = None
    for i, ln in enumerate(lines[start:]):
        if i and _REGION.match(ln):
            break  # the next region's header (stolen-local:, system-ttm:, local1: ...)
        m = _USAGE.match(ln)
        if m and usage is None:
            usage = int(m.group(1))
        b = _BUDDY.search(ln)
        if b:
            total = int(b.group(1)) * _UNIT[b.group(2)]
            free = int(b.group(3)) * _UNIT[b.group(4)]
            if not 0 <= free <= total:
                return None
            out = {"total_b": total, "free_b": free, "used_b": total - free}
            if usage is not None:
                out["usage_b"] = usage
            return out
    return None


def i915_cards(drm: Path = DRM) -> list[tuple[str, int, str | None]]:
    """(card name, DRM minor, PCI address) of every card bound to i915."""
    out: list[tuple[str, int, str | None]] = []
    for name in sorted(os.listdir(drm)) if drm.is_dir() else []:
        m = _CARD.match(name)
        if not m:
            continue
        try:
            driver = os.path.basename(os.readlink(drm / name / "device/driver"))
        except OSError:
            continue
        if driver != "i915":
            continue
        try:
            pci = os.path.basename(os.path.realpath(drm / name / "device"))
        except OSError:
            pci = None
        out.append((name, int(m.group(1)), pci))
    return out


def sample(drm: Path = DRM, debugfs: Path = DEBUGFS) -> dict[str, Any]:
    cards: dict[str, Any] = {}
    why: dict[str, str] = {}
    for name, minor, pci in i915_cards(drm):
        f = debugfs / str(minor) / "i915_gem_objects"
        try:
            got = parse_local0(f.read_text(errors="replace")[: 1 << 20])
        except OSError as exc:
            why[name] = f"{type(exc).__name__}: {exc.strerror or exc}"
            continue
        if got is None:
            why[name] = "no local0 region (an integrated GPU, or an unknown dump layout)"
            continue
        cards[name] = {"pci": pci, "region": "local0", **got}
    return {"v": VERSION, "t_mono_ns": time.monotonic_ns(), "cards": cards, "why": why}


def write(out_dir: Path, data: dict[str, Any]) -> None:
    """Atomically replace out_dir/OUT_NAME, through a directory handle that is never a symlink."""
    out_dir.mkdir(mode=0o755, exist_ok=True)
    dfd = os.open(out_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        tmp = f".{OUT_NAME}.{os.getpid()}"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644,
                     dir_fd=dfd)  # fmt: skip
        try:
            os.write(fd, (json.dumps(data, separators=(",", ":")) + "\n").encode())
            os.fchmod(fd, 0o644)
        finally:
            os.close(fd)
        os.replace(tmp, OUT_NAME, src_dir_fd=dfd, dst_dir_fd=dfd)
    finally:
        os.close(dfd)


def main(argv: list[str]) -> int:
    once = "--once" in argv
    while True:
        try:
            write(OUT_DIR, sample())
        except OSError as exc:  # the next tick tries again; systemd's journal keeps the reason
            print(f"poring-lab-vram: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        if once:
            return 0
        time.sleep(PERIOD_S)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
