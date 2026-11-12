"""A machine's OWN compose values never live in a tracked file (Batt 2026-11-12: "when they pull
our updates, nothing may overwrite their config"). Docker's standard compose.override.yaml is
gitignored, and every compose command of ours adds it LAST."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import guarded_build as gb  # noqa: E402


def test_the_override_is_gitignored_and_never_tracked() -> None:
    r = subprocess.run(["git", "check-ignore", "-q", "compose.override.yaml"], cwd=ROOT)
    assert r.returncode == 0
    tracked = subprocess.run(["git", "ls-files", "compose.override.yaml"], cwd=ROOT,
                             capture_output=True, text=True).stdout  # fmt: skip
    assert tracked == ""


def test_guarded_build_adds_it_only_when_present(tmp_path: Path) -> None:
    assert gb.local_override(tmp_path) == []
    (tmp_path / "compose.override.yaml").write_text("services: {}\n")
    assert gb.local_override(tmp_path) == ["-f", "compose.override.yaml"]


def test_dev_sh_and_verify_mount_add_it_last() -> None:
    dev = (ROOT / "scripts" / "dev.sh").read_text()
    assert "[ -f compose.override.yaml ] && LOCAL=(-f compose.override.yaml)" in dev
    assert '-f compose.yaml -f compose.dev.yaml "${LOCAL[@]}"' in dev
    vm = (ROOT / "scripts" / "verify_mount.py").read_text()
    assert '"-f", "compose.dev.yaml", *local,' in vm


def test_the_worker_command_adds_it_too() -> None:
    """The dedicated-nvidia review (2026-11-12): worker:vision / worker-stop take the override
    too, so a machine's own worker values (its memory cap, its volumes) live there as well."""
    src = (ROOT / "scripts" / "guarded_build.py").read_text()
    assert "overlay=PROFILE.worker_overlay), *local_override()," in src
