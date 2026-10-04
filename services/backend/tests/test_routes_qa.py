"""B6 hand-check routes (Post-S2 round Part D): guards, validation, size cap, round trip."""

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from poring_backend.config import Settings
from poring_backend.main import create_app

ORIGIN = "http://lab.test:3000"
H = {"origin": ORIGIN}
SID = "20261004T120000-console-s2-indoor"
LAN = ("192.168.1.50", 50123)


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

    def factory(peer: tuple[str, int] = LAN, **overrides: Any) -> TestClient:
        fields: dict[str, Any] = {
            "data_dir": tmp_path / "data", "public_port": 80, "frontend_origins": ORIGIN,
            "status_hz": 20.0,
        }  # fmt: skip
        fields.update(overrides)
        app = create_app(Settings(**fields), capture_factory=NoCapture, input_factory=NoInput)
        client = TestClient(app, client=peer)
        client.__enter__()
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.__exit__(None, None, None)


def doc(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "session": SID, "size": [1280, 720], "author": "batt",
        "frames": [
            {"frame_id": 12, "t_mono_ns": 5, "status": "accepted",
             "boxes": [{"x1": 1, "y1": 2, "x2": 30, "y2": 40, "cls": "monster", "gid": 7}]},
            {"frame_id": 13, "t_mono_ns": 6, "status": "edited",
             "boxes": [{"x1": 5, "y1": 5, "x2": 50, "y2": 90, "cls": "npc", "gid": None}]},
        ],
    }  # fmt: skip
    return base | over


def test_round_trip(make: Make, tmp_path: Path) -> None:
    client = make()
    assert client.get(f"/qa/handcheck/{SID}", headers=H).status_code == 404
    r = client.put(f"/qa/handcheck/{SID}", json=doc(), headers=H)
    assert r.status_code == 200, r.text
    assert r.json() == {"saved": SID, "frames": 2, "edited": 1}
    saved = json.loads((tmp_path / "data" / "qa" / "handcheck" / f"{SID}.json").read_text())
    assert saved["frames"][1]["boxes"][0]["cls"] == "npc" and "saved_at" in saved
    got = client.get(f"/qa/handcheck/{SID}", headers=H).json()
    assert got["frames"] == saved["frames"]


@pytest.mark.parametrize(
    ("peer", "headers", "status", "reason"),
    [
        (LAN, {}, 403, "origin_required"),
        (LAN, {"origin": "http://evil.test"}, 403, "origin_not_allowed"),
        (("10.210.96.1", 1), H, 403, "compose_peer"),  # a container via the compose gateway
        (("8.8.8.8", 1), H, 403, "not_a_lan_viewer"),
        (("10.210.97.7", 1), H, 403, "agent_network"),  # ADR-0005 c2: refused before the route
    ],
)  # fmt: skip
def test_who_may_not(
    make: Make, peer: tuple[str, int], headers: dict[str, str], status: int, reason: str
) -> None:
    client = make(peer=peer)
    r = client.put(f"/qa/handcheck/{SID}", json=doc(), headers=headers)
    assert r.status_code == status
    assert r.json()["detail"]["reason"] == reason


def test_the_internal_listener_never_serves_it(make: Make) -> None:
    client = make(public_port=8000)  # requests arrive on 80: not the public listener
    assert client.get(f"/qa/handcheck/{SID}", headers=H).status_code == 404


@pytest.mark.parametrize(
    "bad",
    [
        doc(session="20261004T120000-other"),  # the body names another session
        doc(frames=[{"frame_id": 1, "t_mono_ns": 1, "status": "maybe", "boxes": []}]),
        doc(frames=[{"frame_id": 1, "t_mono_ns": 1, "status": "edited",
                     "boxes": [{"x1": 0, "y1": 0, "x2": 1, "y2": 1, "cls": "poring"}]}]),
        doc(author="batt; rm -rf"),
        doc(extra_field=1),
    ],
)  # fmt: skip
def test_bodies_are_validated(make: Make, bad: dict[str, Any]) -> None:
    client = make()
    r = client.put(f"/qa/handcheck/{SID}", json=bad, headers=H)
    assert r.status_code == 422


def test_bad_session_names_and_huge_bodies_are_refused(make: Make) -> None:
    client = make()
    assert client.put("/qa/handcheck/..%2Fetc", json=doc(), headers=H).status_code in (400, 404)
    assert client.put("/qa/handcheck/not-a-session", json=doc(), headers=H).status_code == 400
    big = b"x" * (2 * 1024 * 1024 + 1)
    r = client.put(f"/qa/handcheck/{SID}", content=big, headers=H)
    assert r.status_code == 413
    health = client.get("/health").json()
    drops = health["dropped_messages"]["qa_http"]
    assert drops.get("bad_session", 0) >= 1 and drops.get("too_large", 0) == 1
