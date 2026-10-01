"""scripts/dev.sh refuses create/start/recreate/build/pull unless guarded_build.py is its parent."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
DEV = ROOT / "scripts" / "dev.sh"


@pytest.fixture
def fake_docker(tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text('#!/bin/sh\necho "DOCKER $*"\n')
    docker.chmod(0o755)
    return {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}


def run(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(DEV), *args], env=env, capture_output=True, text=True)


@pytest.mark.parametrize(
    "args",
    [
        ("up", "-d", "backend"),
        ("--profile", "sniffer", "up", "-d", "--no-build", "sniffer"),
        ("restart", "backend"),
        ("start", "rathena"),
        ("create", "desktop"),
        ("build", "desktop"),
        ("pull", "db"),
        ("run", "--rm", "vision", "true"),
        ("down",),
        ("rm", "-f", "sniffer"),
        ("config",),
        ("config", "--format", "json"),
    ],
)
def test_refused_without_the_guard(fake_docker: dict[str, str], args: tuple[str, ...]) -> None:
    res = run(fake_docker, *args)
    assert res.returncode == 64, res
    assert "DOCKER" not in res.stdout
    assert "guarded_build.py" in res.stderr or "--no-interpolate" in res.stderr


@pytest.mark.parametrize(
    "args",
    [
        ("ps",),
        ("logs", "-f", "frontend-dev"),
        ("exec", "backend", "true"),
        ("stop", "frontend-dev"),
        ("config", "--no-interpolate"),
        ("--profile", "core", "config", "-q"),
    ],
)
def test_read_only_and_stop_pass_through(
    fake_docker: dict[str, str], args: tuple[str, ...]
) -> None:
    res = run(fake_docker, *args)
    assert res.returncode == 0, res
    assert res.stdout.startswith("DOCKER compose -f compose.yaml -f compose.dev.yaml")
    assert res.stdout.rstrip().endswith(" ".join(args))


def test_the_guard_as_parent_may_create_and_recreate(
    fake_docker: dict[str, str], tmp_path: Path
) -> None:
    """dev.sh checks /proc/$PPID/cmdline for scripts/guarded_build.py."""
    guard = tmp_path / "scripts" / "guarded_build.py"
    guard.parent.mkdir()
    guard.write_text(
        "import subprocess, sys\n"
        f"r = subprocess.run(['bash', {str(DEV)!r}, *sys.argv[1:]])\n"
        "sys.exit(r.returncode)\n"
    )
    res = subprocess.run(
        [sys.executable, str(guard), "up", "-d", "--no-build", "--force-recreate", "desktop"],
        env=fake_docker, capture_output=True, text=True,
    )  # fmt: skip
    assert res.returncode == 0, res
    assert "up -d --no-build --force-recreate desktop" in res.stdout
