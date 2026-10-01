"""scripts/verify_mount.py: detects a container still holding an old single-file bind mount."""

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "verify_mount.py"


@pytest.fixture(scope="module")
def vm() -> ModuleType:
    spec = importlib.util.spec_from_file_location("verify_mount", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["verify_mount"] = mod
    spec.loader.exec_module(mod)
    return mod


def fake_runner(host_file: Path, container_text: bytes):  # type: ignore[no-untyped-def]
    cfg = {"services": {"desktop": {"volumes": [
        {"type": "bind", "source": str(host_file), "target": "/usr/local/bin/rdp-loop.sh"},
        {"type": "volume", "source": "x11-unix", "target": "/tmp/.X11-unix"},
    ]}}}  # fmt: skip

    def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        if "config" in cmd:
            out = json.dumps(cfg)
        elif cmd[:2] == ["docker", "inspect"]:
            out = "true\n"
        else:  # docker exec … sha256sum
            out = f"{hashlib.sha256(container_text).hexdigest()}  /usr/local/bin/rdp-loop.sh\n"
        return subprocess.CompletedProcess(cmd, 0, out, "")

    return run


def test_matching_mount_is_ok(vm: ModuleType, tmp_path: Path) -> None:
    f = tmp_path / "rdp-loop.sh"
    f.write_bytes(b"v2")
    assert vm.check([], run=fake_runner(f, b"v2")) == []


def test_stale_mount_is_reported(vm: ModuleType, tmp_path: Path) -> None:
    f = tmp_path / "rdp-loop.sh"
    f.write_bytes(b"v2")
    assert vm.check([], run=fake_runner(f, b"v1")) == ["desktop:/usr/local/bin/rdp-loop.sh"]
