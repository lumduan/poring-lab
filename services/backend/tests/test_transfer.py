"""File transfer routes (ADR-0004): guards, round trip, caps, sanitising, audit log."""

import hashlib
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from poring_backend.config import Settings
from poring_backend.main import create_app
from poring_backend.routes_transfer import safe_name

ORIGIN = "http://lab.test:3000"
H = {"origin": ORIGIN}
MARKER = b"FILE-CONTENT-MARKER-5b2e"


class NoCapture:
    def grab(self) -> Any:
        raise RuntimeError("no display in this test")

    def close(self) -> None:
        pass


class NoInput:
    def send_many(self, events: list[Any]) -> None:
        pass

    def pointer(self) -> tuple[int, int]:
        return (0, 0)

    def has_window_class(self, needle: str) -> bool:
        return False

    def close(self) -> None:
        pass


Make = Callable[..., TestClient]


@pytest.fixture
def make(tmp_path: Path) -> Iterator[Make]:
    clients: list[TestClient] = []
    (tmp_path / "transfer").mkdir()

    def factory(**overrides: Any) -> TestClient:
        fields: dict[str, Any] = {
            "data_dir": tmp_path / "data",
            "transfer_dir": tmp_path / "transfer",
            "rdp_drives": "transfer",
            "public_port": 80,  # TestClient requests arrive on port 80
            "frontend_origins": ORIGIN,
            "status_hz": 20.0,
        }
        fields.update(overrides)
        app = create_app(Settings(**fields), capture_factory=NoCapture, input_factory=NoInput)
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.__exit__(None, None, None)


def url(name: str) -> str:
    return "/transfer/files/" + quote(name, safe="")


def audit(tmp_path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for path in sorted((tmp_path / "data" / "transfer_log").glob("*.jsonl"))
        for line in path.read_text().splitlines()
    ]


def test_round_trip_upload_list_download_delete(make: Make, tmp_path: Path) -> None:
    client = make()
    body = b"hello from the mac\n" + MARKER
    up = client.put(url("notes.txt"), content=body, headers=H)
    assert up.status_code == 200, up.text
    assert up.json() == {
        "name": "notes.txt",
        "size": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }
    assert (tmp_path / "transfer" / "notes.txt").read_bytes() == body

    listing = client.get("/transfer/files", headers=H).json()
    assert [(f["name"], f["kind"], f["size"]) for f in listing["files"]] == [
        ("notes.txt", "file", len(body))
    ]
    assert listing["max_file_bytes"] == 512 * 1024 * 1024 and listing["capacity_bytes"] > 0

    down = client.get(url("notes.txt"), headers=H)
    assert down.status_code == 200 and down.content == body
    assert down.headers["x-content-sha256"] == hashlib.sha256(body).hexdigest()
    assert down.headers["content-disposition"].startswith("attachment")

    assert client.delete(url("notes.txt"), headers=H).json() == {"deleted": "notes.txt"}
    assert not (tmp_path / "transfer" / "notes.txt").exists()
    assert [r["action"] for r in audit(tmp_path)] == ["upload", "download", "delete"]


def test_audit_log_is_metadata_only(make: Make, tmp_path: Path) -> None:
    client = make()
    client.put(url("secret.bin"), content=MARKER * 100, headers=H)
    client.get(url("secret.bin"), headers=H)
    records = audit(tmp_path)
    assert all(
        set(r) == {"t_wall", "action", "name", "size", "sha256", "ok", "reason", "client"}
        for r in records
    )
    for path in (tmp_path / "data").rglob("*"):
        if path.is_file():
            assert MARKER not in path.read_bytes(), f"file content leaked into {path}"


def test_thai_names_survive_and_download_with_rfc5987_name(make: Make, tmp_path: Path) -> None:
    client = make()
    name = "รายงาน ภาษาไทย.txt"
    assert client.put(url(name), content=b"x", headers=H).json()["name"] == name
    down = client.get(url(name), headers=H)
    assert down.status_code == 200
    assert "filename*=utf-8''" in down.headers["content-disposition"].lower()


@pytest.mark.parametrize(
    ("headers", "status", "reason"),
    [
        ({}, 403, "origin_required"),  # scripts and the agent send no Origin
        ({"origin": "http://evil.example"}, 403, "origin_not_allowed"),
    ],
)
def test_origin_is_required_on_every_method(
    make: Make, headers: dict[str, str], status: int, reason: str
) -> None:
    client = make()
    responses = [
        client.get("/transfer/files", headers=headers),
        client.put(url("a.txt"), content=b"x", headers=headers),
        client.get(url("a.txt"), headers=headers),
        client.delete(url("a.txt"), headers=headers),
    ]
    assert {(r.status_code, r.json()["detail"]["reason"]) for r in responses} == {(status, reason)}
    health = client.get("/health").json()
    assert sum(health["dropped_messages"]["transfer_http"].values()) == 4


def test_only_the_public_listener_serves_transfer(make: Make) -> None:
    client = make(public_port=8000)  # the request arrives on :80, i.e. "not the public port"
    response = client.get("/transfer/files", headers=H)
    assert (response.status_code, response.json()["detail"]["reason"]) == (
        404,
        "not_public_listener",
    )


def test_disabled_without_the_drive(make: Make) -> None:
    client = make(rdp_drives="")
    response = client.get("/transfer/files", headers=H)
    assert (response.status_code, response.json()["detail"]["reason"]) == (
        503,
        "transfer_disabled",
    )
    assert client.get("/health").json()["transfer_enabled"] is False


def test_size_cap(make: Make, tmp_path: Path) -> None:
    client = make(transfer_max_bytes=10)
    response = client.put(url("big.bin"), content=b"x" * 11, headers=H)
    assert response.status_code == 413
    assert response.json()["detail"] == {"reason": "too_large", "size": 11, "max_bytes": 10}
    assert not list((tmp_path / "transfer").iterdir())
    assert audit(tmp_path)[-1]["reason"] == "too_large"


def test_existing_names_need_overwrite(make: Make, tmp_path: Path) -> None:
    client = make()
    assert client.put(url("a.txt"), content=b"one", headers=H).status_code == 200
    clash = client.put(url("a.txt"), content=b"two", headers=H)
    assert (clash.status_code, clash.json()["detail"]["reason"]) == (409, "exists")
    ok = client.put(url("a.txt") + "?overwrite=true", content=b"two", headers=H)
    assert ok.status_code == 200
    assert (tmp_path / "transfer" / "a.txt").read_bytes() == b"two"


def test_windows_created_folders_are_listed_but_not_downloadable(
    make: Make, tmp_path: Path
) -> None:
    client = make()
    (tmp_path / "transfer" / "New folder").mkdir()
    (tmp_path / "transfer" / "full").mkdir()
    (tmp_path / "transfer" / "full" / "inner.txt").write_text("x")
    kinds = {f["name"]: f["kind"] for f in client.get("/transfer/files", headers=H).json()["files"]}
    assert kinds == {"New folder": "dir", "full": "dir"}
    assert client.get(url("New folder"), headers=H).status_code == 409
    assert client.delete(url("full"), headers=H).status_code == 409  # not empty
    assert client.delete(url("New folder"), headers=H).status_code == 200


def test_partial_uploads_are_hidden_and_swept_at_startup(make: Make, tmp_path: Path) -> None:
    (tmp_path / "transfer" / ".partial-deadbeef").write_bytes(b"half")
    client = make()
    assert client.get("/transfer/files", headers=H).json()["files"] == []
    assert not (tmp_path / "transfer" / ".partial-deadbeef").exists()


def test_cors_preflight_for_the_console(make: Make) -> None:
    client = make()
    response = client.options(
        url("a.txt"),
        headers={"origin": ORIGIN, "access-control-request-method": "PUT"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("report.pdf", "report.pdf"),
        ("  padded name.txt  ", "padded name.txt"),
        ('a:b?c*"d|e<f>.txt', "a_b_c__d_e_f_.txt"),
        ("CON.txt", "_CON.txt"),
        ("lpt1", "_lpt1"),
        ("trailing dots...", "trailing dots"),
        ("รายงาน.txt", "รายงาน.txt"),
        ("école.txt", "école.txt"),  # NFD -> NFC
    ],
)
def test_safe_name(raw: str, expected: str) -> None:
    assert safe_name(raw) == expected


@pytest.mark.parametrize(
    "raw", ["", ".", "..", "...", ".hidden", "a/b", "..\\x", "a\x00b", "a\nb", "ก" * 70]
)
def test_safe_name_rejects(raw: str) -> None:
    with pytest.raises(ValueError):
        safe_name(raw)


def test_existing_names_cannot_escape(make: Make) -> None:
    client = make()
    for bad in ("..", ".partial-x"):
        assert client.get(url(bad), headers=H).status_code in (400, 404)
