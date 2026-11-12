#!/usr/bin/env python3
"""Do the containers see the files the host has? (the single-file bind-mount inode trap)

A single-file bind mount follows the file's INODE. `sed -i`, most editors and `git checkout`
replace the file with a new inode, and the running container silently keeps the old one: on
2026-10-01 three RDP codec tests ran a stale rdp-loop.sh. This compares sha256 host vs container
for every single-file bind mount in compose.dev.yaml (read with --no-interpolate: no secrets).

    python3 scripts/verify_mount.py            # all running dev-overlay services
    python3 scripts/verify_mount.py desktop    # one service

Exit 1 on any mismatch, with the fix: re-bind through the guard,
    python3 scripts/guarded_build.py --sustain 30 --spike 25 recreate:<svc>@90
(and edit such files in place next time).
"""

import hashlib
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def file_mounts(run: Runner = _run) -> list[tuple[str, Path, str]]:
    """(service, host file, container path) for every single-file bind mount of the dev overlay."""
    local = (["-f", "compose.override.yaml"] if (ROOT / "compose.override.yaml").is_file()
             else [])  # this machine's own values, last (Batt 2026-11-12)  # fmt: skip
    cfg = run(["docker", "compose", "-f", "compose.yaml", "-f", "compose.dev.yaml", *local,
               "--profile", "*", "config", "--no-interpolate", "--format", "json"])  # fmt: skip
    out: list[tuple[str, Path, str]] = []
    for svc, spec in json.loads(cfg.stdout)["services"].items():
        for vol in spec.get("volumes", []):
            if vol.get("type") == "bind":
                src = Path(vol["source"])
                if src.is_file():
                    out.append((svc, src, vol["target"]))
    return out


def container_of(svc: str, run: Runner = _run) -> str | None:
    name = f"poring-lab-{svc}-1"
    state = run(["docker", "inspect", "-f", "{{.State.Running}}", name])
    return name if state.returncode == 0 and state.stdout.strip() == "true" else None


def check(services: list[str], run: Runner = _run) -> list[str]:
    problems: list[str] = []
    for svc, host, target in file_mounts(run):
        if services and svc not in services:
            continue
        name = container_of(svc, run)
        if name is None:
            continue
        want = hashlib.sha256(host.read_bytes()).hexdigest()
        got = run(["docker", "exec", name, "sha256sum", target])
        seen = got.stdout.split()[0] if got.returncode == 0 and got.stdout else "unreadable"
        status = "ok" if seen == want else "STALE"
        shown = host.relative_to(ROOT) if host.is_relative_to(ROOT) else host
        print(f"{status:6} {svc:12} {shown} -> {target}")
        if seen != want:
            problems.append(f"{svc}:{target}")
    return problems


def main() -> None:
    problems = check(sys.argv[1:])
    if problems:
        print(f"\n{len(problems)} stale mount(s). Re-bind with the guard, e.g.:\n"
              "  python3 scripts/guarded_build.py --sustain 30 --spike 25 recreate:<svc>@90",
              file=sys.stderr)  # fmt: skip
        sys.exit(1)


if __name__ == "__main__":
    main()
