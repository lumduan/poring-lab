"""scripts/lab_servers.py: which sniffer holds which server's events (2026-10-05, rathena-th)."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
ROOT = SCRIPTS.parent


@pytest.fixture
def ls(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.delenv("PORING_SERVER", raising=False)
    spec = importlib.util.spec_from_file_location("lab_servers", SCRIPTS / "lab_servers.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["lab_servers"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_default_is_todays_server_and_select_switches(ls: ModuleType) -> None:
    assert (ls.server(), ls.sniffer()) == ("lab-rathena", "poring-lab-sniffer-1")
    assert ls.select("lab-rathena-th") == "lab-rathena-th"
    assert ls.sniffer() == "poring-lab-sniffer-th-1"
    assert ls.select(None) == "lab-rathena-th"  # no --server: the environment stays


def test_an_unknown_server_is_refused(ls: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORING_SERVER", "official")
    with pytest.raises(SystemExit, match="unknown server"):
        ls.sniffer()


def test_every_sniffer_names_a_configured_environment(ls: ModuleType) -> None:
    envs = yaml.safe_load((ROOT / "config" / "environments.yaml").read_text())["environments"]
    assert set(ls.SNIFFERS) <= {e["id"] for e in envs}
    services = yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]
    for server, container in ls.SNIFFERS.items():
        svc = container.removeprefix("poring-lab-").removesuffix("-1")
        assert services[svc]["environment"]["SNIFFER_SERVER_ID"] == server
