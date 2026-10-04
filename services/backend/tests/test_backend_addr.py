"""scripts/backend_addr.py: the backend's DEFAULT-network address, by network NAME. With two
networks (ADR-0005 option c2) the old `{{range .Networks}}{{.IPAddress}}{{end}}` concatenated
both."""

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture(scope="module")
def ba() -> ModuleType:
    spec = importlib.util.spec_from_file_location("backend_addr", SCRIPTS / "backend_addr.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_default_network_is_indexed_by_name(ba: ModuleType) -> None:
    seen: list[list[str]] = []

    def run(cmd: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="10.210.96.5\n", stderr="")

    assert ba.backend_ip(run=run) == "10.210.96.5"
    fmt = seen[0][3]
    assert 'index .NetworkSettings.Networks "poring-lab_default"' in fmt and "range" not in fmt


def test_a_missing_container_is_empty_not_an_exception(ba: ModuleType) -> None:
    def run(cmd: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="No such object")

    assert ba.backend_ip(run=run) == ""


def test_no_host_script_concatenates_network_addresses() -> None:
    for script in SCRIPTS.glob("*.py"):
        if script.name == "backend_addr.py":
            continue  # it quotes the old pattern in its docstring
        assert "{{range .NetworkSettings.Networks}}" not in script.read_text(), script.name
