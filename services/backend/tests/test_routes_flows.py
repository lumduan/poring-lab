"""MW2's /flows routes: computation only (lint, simulate, the Python view, the catalogue), behind
the console-browser gate, the CSRF token and a rate limit; hostile bodies are refused; nothing is
stored and nothing reaches the mux."""

from __future__ import annotations

import json
import struct
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from poring_backend import routes_settings
from poring_backend.config import Settings
from poring_backend.main import create_app

ORIGIN = "http://lab.test:3000"
H = {"origin": ORIGIN}
LAN = ("192.168.1.50", 50123)
REPO = Path(__file__).resolve().parents[3]
SAMPLE_JSON = REPO / "packages/poring_flow/src/poring_flow/examples/town_warp_farm.json"


class NoCapture:
    def grab(self) -> Any:
        raise RuntimeError("no display in this test")

    def close(self) -> None:
        pass


class NoInput:
    sent: list[Any] = []

    def send_many(self, events: list[Any]) -> None:
        NoInput.sent.extend(events)

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
            "status_hz": 20.0, "settings_dir": tmp_path / "settings",
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


def sample() -> dict[str, Any]:
    return dict(json.loads(SAMPLE_JSON.read_text()))


def hdr(client: TestClient) -> dict[str, str]:
    return {**H, "x-csrf-token": routes_settings.csrf_token(client.app.state.poring)}  # type: ignore[attr-defined]


def post(client: TestClient, route: str, body: Any, **kw: Any) -> Any:
    return client.post(f"/flows/{route}", json=body, headers=kw.pop("headers", hdr(client)), **kw)


def test_catalogue_and_sample(make: Make) -> None:
    client = make()
    r = client.get("/flows/catalogue?client=kro-20211103-prere", headers=H)
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["blocks"]["open_window"]["badge"] == "verified_rdp"
    assert "basic_info" in doc["windows"] and "walk_to" in doc["palette"]
    s = client.get("/flows/sample", headers=H).json()
    assert s["flow"] == sample() and s["world"] == "sample"
    w = client.get("/flows/world?source=sample&maps=town_1&walk=true", headers=H).json()
    assert list(w["maps"]) == ["town_1"] and len(w["walk"]["town_1"]) == 90
    assert {n["key"] for n in w["maps"]["town_1"]["npcs"]} == {"n_kafra", "n_guide", "n_warper"}


def test_lint_simulate_python(make: Make) -> None:
    client = make()
    flow = sample()
    r = post(client, "lint", {"flow": flow, "world": "sample"})
    assert r.status_code == 200, r.text
    lint = r.json()
    assert len(lint["flow_hash"]) == 64
    # the real L2/L3/L4 bindings are not there for these blocks: reported as unsupported, by node
    assert lint["by_owner"]["block:town"]["unsupported"] >= 1
    assert all(f["owner"] in ("flow", "global", "block:town", "block:farm")
               for f in lint["findings"])  # fmt: skip
    r = post(client, "simulate", {"flow": flow, "world": "sample",
                                  "scenario": {"horizon_s": 300, "timeline": [
                                      {"t": 200, "set": {"is_dead": True}}]}})  # fmt: skip
    assert r.status_code == 200, r.text
    sim = r.json()
    assert sim["flow_hash"] == lint["flow_hash"]
    assert "death_respawn" in [x["kind"] for x in sim["trace"]["transitions"]]
    assert sim["lint"]["counts"] == lint["counts"]
    py = post(client, "python", {"flow": flow}).json()
    assert py["python"].startswith("flow(\n") and py["flow_hash"] == lint["flow_hash"]
    assert NoInput.sent == []  # nothing ever reached an input path
    # the local world: no sheets generated for these synthetic maps -> unsupported, fail closed
    local = post(client, "lint", {"flow": flow, "world": "local"}).json()
    assert any(f["rule"] == "map_sheet" for f in local["findings"])


@pytest.mark.parametrize(
    ("peer", "headers", "status", "reason"),
    [
        (LAN, {}, 403, "origin_required"),
        (LAN, {"origin": "http://evil.test"}, 403, "origin_not_allowed"),
        (("10.210.96.1", 1), H, 403, "compose_peer"),
        (("8.8.8.8", 1), H, 403, "not_a_lan_viewer"),
        (("10.210.97.7", 1), H, 403, "agent_network"),  # ADR-0005 c2: refused before the route
    ],
)  # fmt: skip
def test_who_may_not(
    make: Make, peer: tuple[str, int], headers: dict[str, str], status: int, reason: str
) -> None:
    client = make(peer=peer)
    for r in (
        client.get("/flows/catalogue", headers=headers),
        client.post("/flows/lint", json={"flow": sample()}, headers=headers),
    ):
        assert r.status_code == status
        assert r.json()["detail"]["reason"] == reason


def test_never_on_the_internal_listener(make: Make) -> None:
    client = make(public_port=8000)  # requests arrive on 80: not the public listener
    assert client.get("/flows/catalogue", headers=H).status_code == 404
    assert post(client, "lint", {"flow": sample()}).status_code == 404


def test_compute_needs_the_csrf_token_and_is_rate_limited(make: Make) -> None:
    client = make()
    r = post(client, "python", {"flow": sample()}, headers=H)
    assert r.status_code == 403 and r.json()["detail"]["reason"] == "csrf_invalid"
    forged = {**H, "x-csrf-token": "9999999999." + "0" * 64}
    assert post(client, "python", {"flow": sample()}, headers=forged).status_code == 403
    codes = [post(client, "python", {"flow": sample()}).status_code for _ in range(21)]
    assert codes[:19] == [200] * 19 and codes[-1] == 429  # 20 a minute (one was refused above)
    drops = client.get("/health").json()["dropped_messages"]["flows_http"]
    assert drops["csrf_invalid"] == 2 and drops["rate_limited"] >= 1


def test_hostile_bodies(make: Make) -> None:
    client = make()
    big = {"flow": {"pad": "x" * (2 << 20)}}
    assert post(client, "lint", big).json()["detail"]["reason"] == "too_large"
    r = post(client, "lint", {"flow": {"pad": "x" * (1 << 20)}})  # under the body cap: MW1's cap
    assert r.json()["detail"]["reason"] == "invalid_flow"
    assert "at most 1048576" in r.json()["detail"]["errors"][0]
    deep: Any = {"kind": "lit", "value": 1}
    for _ in range(300):
        deep = {"kind": "not", "term": deep}
    r = post(client, "lint", {"flow": {**sample(), "stop_when": deep}})
    assert r.status_code == 422 and r.json()["detail"]["reason"] == "too_deep"
    raw = {**hdr(client), "content-type": "application/json"}
    r = client.post("/flows/lint", content=b"{not json", headers=raw)
    assert r.status_code == 422 and r.json()["detail"]["reason"] == "invalid_body"
    bad = {**sample(), "ir": 2}
    r = post(client, "lint", {"flow": bad})
    assert r.status_code == 422 and r.json()["detail"]["reason"] == "invalid_flow"
    assert any("ir" in m for m in r.json()["detail"]["errors"])
    r = post(client, "lint", {"flow": sample(), "world": "/etc"})
    assert r.json()["detail"]["reason"] == "invalid_body"
    r = post(client, "simulate", {"flow": sample(), "scenario": {"horizon_s": 1e9}})
    assert r.json()["detail"]["reason"] == "invalid_scenario"
    r = post(client, "simulate", {"flow": sample(), "scenario": {"start_block": "nowhere"}})
    assert r.status_code == 422 and r.json()["detail"]["reason"] == "invalid_scenario"
    r = client.get("/flows/world?maps=../../etc", headers=H)
    assert r.json()["detail"]["reason"] == "invalid_query"


def test_cors_preflight_allows_the_console_to_post(make: Make) -> None:
    client = make()
    r = client.options("/flows/lint", headers={
        "origin": ORIGIN, "access-control-request-method": "POST",
        "access-control-request-headers": "content-type,x-csrf-token"})  # fmt: skip
    assert r.status_code == 200
    assert "POST" in r.headers["access-control-allow-methods"]
    r = client.options("/flows/lint", headers={
        "origin": "http://evil.test", "access-control-request-method": "POST"})  # fmt: skip
    assert r.status_code == 400


def test_without_the_flow_engine_the_routes_answer_503(
    make: Make, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = make()
    monkeypatch.setitem(sys.modules, "poring_flow", None)
    r = client.get("/flows/catalogue", headers=H)
    assert r.status_code == 503 and r.json()["detail"]["reason"] == "flow_engine_unavailable"


def test_the_local_world_is_built_from_the_kb(make: Make, tmp_path: Path) -> None:
    """MW2-0 at run time: sheets from the extracted KB (synthetic here), keys and their labels."""
    kb = tmp_path / "data" / "kb"
    (kb / "bindings").mkdir(parents=True)
    l3 = {
        "warp": {"cells": {"by_map": {"m_town": [
            {"x": 5, "y": 1, "to_map": "m_field", "to_x": 2, "to_y": 2}]}}},
        "npc": {"positions": {"npcs": [{"name": "Guide#t", "map": "m_town", "x": 3, "y": 4}]},
                "menus": {"by_npc": {"Guide#t": [{"options": ["Go."]}]}}},
    }  # fmt: skip
    (kb / "bindings" / "lab-rathena.json").write_text(json.dumps(l3))
    client = make()
    w = client.get("/flows/world?source=local&server=lab-rathena&maps=m_town", headers=H).json()
    npc = w["maps"]["m_town"]["npcs"][0]
    assert npc["key"].startswith("n_") and w["labels"]["npcs"][npc["key"]] == "Guide#t"
    assert w["labels"]["options"][npc["menu"][0]] == "Go."
    assert w["maps"]["m_town"]["warps"][0]["to_map"] == "m_field"
    lint = post(client, "lint", {"flow": sample(), "world": "local"}).json()
    assert isinstance(lint["world_notes"], list)


def test_the_gat_mount_gives_real_walkability(
    make: Make, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Batt 2026-10-09: simulate on REAL routes. The bindings name the HOST's GAT directory, which
    the container cannot read; PORING_GAT_DIR (compose.dev: the read-only /lab-gat) overrides it."""
    kb = tmp_path / "data" / "kb"
    (kb / "bindings").mkdir(parents=True)
    l3 = {"map": {"walkability": {"gat_dir": str(tmp_path / "not-here")}}}
    (kb / "bindings" / "lab-rathena.json").write_text(json.dumps(l3))
    gats = tmp_path / "gat"
    gats.mkdir()
    rows = ["..#", "..#", "..."]
    tiles = b"".join(
        struct.pack("<4fHH", 0, 0, 0, 0, 1 if c == "#" else 0, 0) for row in rows for c in row
    )
    (gats / "m_town.gat").write_bytes(struct.pack("<4sBBII", b"GRAT", 1, 2, 3, 3) + tiles)
    url = "/flows/world?source=local&server=lab-rathena&maps=m_town&walk=true"
    without = make().get(url, headers=H).json()
    assert any("not readable here" in n for n in without["notes"])
    assert "m_town" not in without.get("walk", {})
    monkeypatch.setenv("PORING_GAT_DIR", str(gats))
    got = make().get(url, headers=H).json()
    assert not any("not readable" in n for n in got["notes"])
    assert got["walk"]["m_town"] == rows


def test_a_chunked_body_is_capped_while_it_is_read(make: Make) -> None:
    client = make()

    def chunks() -> Any:
        for _ in range(40):
            yield b"x" * 65536  # 2.5 MiB without a content-length

    r = client.post("/flows/lint", content=chunks(), headers=hdr(client))
    assert r.status_code == 413 and r.json()["detail"]["reason"] == "too_large"


def test_world_reads_are_rate_limited(make: Make) -> None:
    client = make()
    codes = [
        client.get("/flows/world?source=sample&maps=town_1", headers=H).status_code
        for _ in range(61)
    ]
    assert codes[:60] == [200] * 60 and codes[60] == 429
