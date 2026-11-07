#!/usr/bin/env python3
"""Push the RAM run-time inputs from ubuntu-docker to bot-server, RAM to RAM
(migration_check.RUNTIME: the GAT maps, sprites, calibrations, the chat guard, the KB, the rathena
source it reads, the detector's models), and build the CPU detector's environment there with
exactly ubuntu-docker's package set (docs/planning/bot-server-cutover.md Phase A 7 and Phase B 2).
Run on ubuntu-docker; every copy is a push.

    python3 scripts/runtime_sync.py --dry-run     # the commands, nothing sent
    python3 scripts/runtime_sync.py               # the items, then the detector environment
    python3 scripts/runtime_sync.py --items-only  # the items (e.g. the chat guard at the cutover)

/dev/shm is wiped by every reboot of either host. After a bot-server reboot, run this again while
ubuntu-docker still has them, or rebuild there from the NAS (docs/operations/detector-cpu.md, the
after-reboot steps). `migration_check.py check` compares every file by sha256.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import migration_check as mc  # noqa: E402

REMOTE = "bot@192.168.1.228"
SSH = ["ssh", "-o", "BatchMode=yes"]
RSYNC = ["rsync", "-a", "--mkpath", "--bwlimit=15000", "-e", "ssh -o BatchMode=yes"]
PIN = re.compile(r"^[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+$")
DETECTOR = "/dev/shm/poring-lab-detector"


def item_copy(name: str, is_dir: bool) -> list[str]:
    """PURE: the rsync of one RUNTIME item; a directory is made IDENTICAL there (`--delete`
    inside that directory only), a file is replaced."""
    src, dst = f"{mc.SHM}/{name}", f"{REMOTE}:{mc.SHM}/{name}"
    if is_dir:
        return [*RSYNC, "--delete", f"{src}/", f"{dst}/"]
    return [*RSYNC, src, dst]


def detector_env_cmd(pins: list[str]) -> str:
    """PURE: the remote shell that (re)builds bot-server's detector environment with these pins
    (each `name==version`, refused otherwise: they are spliced into a shell line)."""
    bad = [p for p in pins if not PIN.match(p)]
    if bad or not pins:
        raise SystemExit(f"detector pins: refused {bad or 'an empty set'}")
    return (
        f"set -e; D={DETECTOR}; mkdir -p $D; cd $D; "
        "export UV_CACHE_DIR=$D/uv-cache UV_LINK_MODE=copy; "
        "if [ -L .venv ] || [ ! -x .venv/bin/python ]; then rm -rf .venv; "
        "~/.local/bin/uv venv -q .venv --python 3.12; fi; "
        f"~/.local/bin/uv pip install -q --python .venv/bin/python {' '.join(sorted(pins))}; "
        'rm -rf "$D/uv-cache"; '
        '.venv/bin/python -c "import onnxruntime, numpy; '
        "print('detector env:', onnxruntime.__version__, numpy.__version__)\""
    )


def source_pins() -> list[str]:
    """ubuntu-docker's detector environment, package by package (its own interpreter answers)."""
    code = ("import importlib.metadata as m; "
            "print('\\n'.join(sorted(f\"{d.metadata['Name']}=={d.version}\" "
            "for d in m.distributions())))")  # fmt: skip
    out = subprocess.run([str(mc.DETECTOR_PY), "-c", code], capture_output=True, text=True,
                         check=True).stdout  # fmt: skip
    return [line for line in out.splitlines() if line and not line.startswith(("pip==", "uv=="))]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="print the commands; send nothing")
    ap.add_argument("--items-only", action="store_true", help="no detector environment")
    a = ap.parse_args(argv)
    steps = []
    for name in mc.RUNTIME:
        src = mc.SHM / name
        if not src.exists():
            print(f"{name}: ABSENT here: nothing to push (the check will name it)")
            continue
        steps.append((f"runtime-{name.replace('/', '-')}", item_copy(name, src.is_dir())))
    env = None if a.items_only else detector_env_cmd(source_pins())
    if a.dry_run:
        for label, cmd in steps:
            print(f"{label}: {' '.join(cmd)}")
        print(f"detector env -> {REMOTE}: {env}")
        return 0
    import guarded_build as gb  # the IO guard (VM 103's capture services)

    for label, cmd in steps:
        guard = gb.Guard(gb.cgroup_paths(), 30.0, 10.0, sustain=30.0)
        if not gb.run_process(label, cmd, guard):
            print(f"{label}: STOPPED/FAILED (worst stall {guard.worst}); nothing after it ran")
            return 1
    print(f"{len(steps)} items pushed", flush=True)
    if env is None:
        return 0
    r = subprocess.run([*SSH, REMOTE, env], capture_output=True, text=True, check=False)
    print((r.stdout + r.stderr).strip())
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
