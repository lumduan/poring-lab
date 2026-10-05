"""scripts/nas_drop.py against a FAKE NAS (no ssh): authenticated, Dell-only, read back; never a
foreign share; a readonly dataset is snapshotted BEFORE it is unlocked."""

import importlib.util
import json
import shlex
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "nas_drop.py"
DS = "tank-main/poring-lab/locale-packs"
MP = "/mnt/" + DS


@pytest.fixture
def nd(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location("nas_drop", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeNAS:
    def __init__(self, readonly: str = "OFF") -> None:
        self.shares: list[dict[str, Any]] = [
            {"id": 9, "name": "torrents", "path": "/mnt/tank-main/torrents", "comment": "",
             "enabled": True},
        ]  # fmt: skip
        self.readonly = readonly
        self.snaps: list[str] = []
        self.log: list[str] = []

    def __call__(self, cmd: str) -> str:
        argv = shlex.split(cmd)
        if argv[0] == "docker":
            return "2026-09-23T01:35:17Z restarts=0 running\n"
        if argv[0] == "test" or argv[0] == "smbstatus":
            return ""
        if argv[:2] == ["zfs", "list"]:
            return argv[-1] + "\n" if argv[-1].split("@")[1] in self.snaps else ""
        assert argv[:2] == ["midclt", "call"], cmd
        method, args = argv[2], [json.loads(a) for a in argv[3:]]
        self.log.append(method)
        return json.dumps(self.midclt(method, args))

    def midclt(self, method: str, args: list[Any]) -> Any:
        if method == "sharing.smb.query":
            if not args:
                return self.shares
            ((_, _, name),) = args[0]
            return [s for s in self.shares if s["name"] == name]
        if method == "sharing.smb.create":
            self.shares.append({**args[0], "id": 30, "enabled": True})
            return self.shares[-1]
        if method == "sharing.smb.delete":
            self.shares = [s for s in self.shares if s["id"] != args[0]]
            return True
        if method == "pool.dataset.query":
            ds = {"id": DS, "mountpoint": MP, "readonly": {"value": self.readonly}}
            ((_, op, value),) = args[0]
            return (
                [ds] if (op == "=" and value == DS) or (op == "^" and DS.startswith(value)) else []
            )
        if method == "pool.dataset.update":
            self.readonly = args[1]["readonly"]
            return {}
        if method == "zfs.snapshot.create":
            self.snaps.append(args[0]["name"])
            return {}
        raise AssertionError(method)


def test_open_creates_an_authenticated_dell_only_share_and_reads_it_back(
    nd: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeNAS()
    monkeypatch.setattr(nd, "nas", fake)
    assert nd.main(["open", "poring-locale-th", "--dataset", DS, "--subdir", "th",
                    "--host", "192.168.1.169"]) == 0  # fmt: skip
    created = fake.shares[-1]
    assert created["path"] == MP + "/th" and created["ro"] is True and created["guestok"] is False
    assert (created["hostsallow"], created["hostsdeny"], created["browsable"]) == (
        ["192.168.1.169"], ["ALL"], False,
    )  # fmt: skip
    assert nd.MARKER in created["comment"]
    assert json.loads(capsys.readouterr().out)["id"] == 30


@pytest.mark.parametrize(
    ("argv", "why"),
    [
        (["open", "torrents2", "--dataset", DS, "--host", "192.168.1.169"], "poring-"),
        (["open", "poring-x", "--dataset", "tank-main/ix-apps", "--host", "192.168.1.169"], "only"),
        (
            ["open", "poring-x", "--dataset", DS, "--subdir", "../..", "--host", "1.2.3.4"],
            "relative",
        ),
    ],
)
def test_open_refuses_outside_its_lane(
    nd: ModuleType, monkeypatch: pytest.MonkeyPatch, argv: list[str], why: str
) -> None:
    monkeypatch.setattr(nd, "nas", FakeNAS())
    with pytest.raises(SystemExit, match=why):
        nd.main(argv)


def test_rw_on_a_readonly_dataset_snapshots_before_unlocking(
    nd: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeNAS(readonly="ON")
    monkeypatch.setattr(nd, "nas", fake)
    with pytest.raises(SystemExit, match="--unlock"):
        nd.main(["open", "poring-drop", "--dataset", DS, "--host", "192.168.1.169", "--rw"])
    assert nd.main(["open", "poring-drop", "--dataset", DS, "--host", "192.168.1.169", "--rw",
                    "--unlock"]) == 0  # fmt: skip
    assert fake.log.index("zfs.snapshot.create") < fake.log.index("pool.dataset.update")
    assert fake.snaps[0].startswith("pre-drop-") and fake.readonly == "OFF"
    assert fake.shares[-1]["ro"] is False


def test_close_deletes_only_a_marked_share_and_can_relock(
    nd: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeNAS()
    monkeypatch.setattr(nd, "nas", fake)
    with pytest.raises(SystemExit, match="not a nas_drop share"):
        nd.main(["close", "torrents"])
    assert any(s["name"] == "torrents" for s in fake.shares)  # untouched
    nd.main(["open", "poring-drop", "--dataset", DS, "--host", "192.168.1.169"])
    capsys.readouterr()
    assert nd.main(["close", "poring-drop", "--lock"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert not any(s["name"] == "poring-drop" for s in fake.shares)
    assert fake.readonly == "ON" and out["locked"].startswith(DS + "@pristine-")
    assert nd.main(["close", "poring-drop"]) == 0  # idempotent: already closed


def test_midclt_accepts_a_bare_python_literal(
    nd: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2026-10-05: sharing.smb.delete printed `True`; the close crashed after the delete, before
    its read-backs. JSON stays JSON; a bare literal is mapped; anything else comes back as text."""
    for out, want in (('[{"id": 1}]', [{"id": 1}]), ("True", True), ("None", None), ("", None),
                      ("weird", "weird")):  # fmt: skip
        monkeypatch.setattr(nd, "nas", lambda cmd, o=out: o + "\n")
        assert nd.midclt("x") == want
