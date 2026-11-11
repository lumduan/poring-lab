"""GET /economy/list and /economy/data/{name} (routes_economy.py, Batt 2026-11-11): read-only,
the public listener only, names from a fixed character set that cannot leave the directory.
Synthetic export files in a tmp DATA_DIR."""

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from poring_backend.config import Settings
from poring_backend.main import create_app
from poring_backend.routes_economy import resolve, valid_name

ORIGIN = "http://lab.test:3000"
LAN = ("192.168.1.20", 40000)


class NoCapture:
    def grab(self) -> Any:
        raise RuntimeError("no X in this test")

    def close(self) -> None:
        pass


class NoInput:
    def send_many(self, events: Any) -> None:
        pass

    def pointer(self) -> tuple[int, int]:
        return (0, 0)

    def has_window_class(self, needle: str) -> bool:
        return False

    def close(self) -> None:
        pass


def dash_dir(tmp_path: Path) -> Path:
    return tmp_path / "data" / "econ" / "dashboard"


def put(tmp_path: Path, name: str, doc: Any, mtime: float | None = None) -> Path:
    d = dash_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(doc if isinstance(doc, str) else json.dumps(doc))
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    return p


@pytest.fixture
def make(tmp_path: Path) -> Iterator[Any]:
    clients: list[TestClient] = []

    def factory(peer: tuple[str, int] = LAN, **overrides: Any) -> TestClient:
        fields: dict[str, Any] = {
            "data_dir": tmp_path / "data",
            "public_port": 80,
            "frontend_origins": ORIGIN,
            "lab_state_dir": tmp_path / "lab-state",
            "hardware_root": tmp_path / "no-host",
        }
        fields.update(overrides)
        (tmp_path / "lab-state").mkdir(exist_ok=True)
        (tmp_path / "data").mkdir(exist_ok=True)
        app = create_app(Settings(**fields), capture_factory=NoCapture, input_factory=NoInput)
        client = TestClient(app, client=peer)
        client.__enter__()
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.__exit__(None, None, None)


def drops(client: TestClient) -> dict[str, int]:
    out: dict[str, int] = client.get("/health").json()["dropped_messages"].get("economy_http", {})
    return out


def test_names_are_a_fixed_character_set() -> None:
    for ok in ("p57-p58", "xmas02.p57_p58", "A1", "a" * 64):
        assert valid_name(ok), ok
    for bad in ("", ".x", "..", "../x", "a/b", "a\\b", "a b", "a%2Fb", "a" * 65, "-x", "ไทย"):
        assert not valid_name(bad), bad


def test_resolve_stays_inside_the_directory(tmp_path: Path) -> None:
    root = dash_dir(tmp_path)
    root.mkdir(parents=True)
    assert resolve(root, "ok") == (root / "ok.json").resolve()
    assert resolve(root, "../ok") is None
    outside = tmp_path / "secret.json"
    outside.write_text("{}")
    (root / "link.json").symlink_to(outside)  # a symlink out of the directory is refused
    assert resolve(root, "link") is None


def test_the_list_and_one_export_as_written(make: Any, tmp_path: Path) -> None:
    doc = {"schema": "poring-lab.econ-dashboard.v1", "name": "b", "runs": [{"kills": 3}]}
    put(tmp_path, "a.json", {"schema": "x"}, mtime=1_000.0)
    p = put(tmp_path, "b.json", doc, mtime=2_000.0)
    put(tmp_path, ".b.json.part", "{")  # the exporter's temp file: never listed
    put(tmp_path, "bad name.json", "{}")
    put(tmp_path, "notes.txt", "x")
    client = make()
    body = client.get("/economy/list").json()
    assert [x["name"] for x in body["exports"]] == ["b", "a"]  # newest first
    assert body["exports"][0]["bytes"] == p.stat().st_size
    r = client.get("/economy/data/b", headers={"origin": ORIGIN})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
    assert r.content == p.read_bytes() and r.json()["runs"] == [{"kills": 3}]
    assert r.headers["access-control-allow-origin"] == ORIGIN  # the console may read it


def test_no_export_yet_is_an_empty_list_with_the_reason(make: Any) -> None:
    body = make().get("/economy/list").json()
    assert body["exports"] == [] and "econ_dash.py" in body["why"]


def test_bad_names_missing_files_and_broken_files(make: Any, tmp_path: Path) -> None:
    put(tmp_path, "broken.json", "{not json")
    outside = tmp_path / "secret.json"
    outside.write_text("{}")
    (dash_dir(tmp_path) / "link.json").symlink_to(outside)
    client = make()
    for name, status, reason in (
        ("%2E%2E", 400, "bad_name"),
        (".hidden", 400, "bad_name"),
        ("a%20b", 400, "bad_name"),
        ("a%00b", 400, "bad_name"),
        ("link", 400, "outside_dir"),
        ("missing", 404, "not_found"),
        ("broken", 422, "not_json"),
    ):
        r = client.get(f"/economy/data/{name}")
        assert (r.status_code, r.json()["detail"]["reason"]) == (status, reason), name
    for url in ("/economy/data/..%2Fsecret", "/economy/data/../secret"):  # a "/" never routes here
        r = client.get(url)
        assert r.status_code == 404 and r.json() == {"detail": "Not Found"}, url
    assert drops(client) == {"bad_name": 4, "outside_dir": 1, "not_json": 1}


def test_the_agents_internal_listener_never_serves_it(make: Any, tmp_path: Path) -> None:
    put(tmp_path, "b.json", {"schema": "x"})
    client = make(public_port=8000, internal_port=80)  # requests arrive on 80 = the internal one
    for url in ("/economy/list", "/economy/data/b"):
        r = client.get(url)
        assert r.status_code == 404 and r.json()["detail"]["reason"] == "not_public_listener"
    assert drops(client) == {"not_public_listener": 2}


def test_the_agent_network_is_refused_before_the_route(make: Any) -> None:
    r = make(peer=("10.210.97.7", 1)).get("/economy/list")  # ADR-0005 c2
    assert r.status_code == 403 and r.json()["detail"]["reason"] == "agent_network"


def test_the_routes_never_write(make: Any, tmp_path: Path) -> None:
    put(tmp_path, "b.json", {"schema": "x"})
    before = sorted(p.name for p in dash_dir(tmp_path).iterdir())
    client = make()
    client.get("/economy/list")
    client.get("/economy/data/b")
    client.get("/economy/data/missing")
    assert sorted(p.name for p in dash_dir(tmp_path).iterdir()) == before
    for method in ("put", "post", "delete"):
        assert getattr(client, method)("/economy/data/b").status_code == 405
