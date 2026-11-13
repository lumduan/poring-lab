"""MW2's /flows routes: computation only (lint, simulate, the Python view, the catalogue), behind
the console-browser gate, the CSRF token and a rate limit; hostile bodies are refused; nothing is
stored and nothing reaches the mux. Since the project model (format 3, Batt 2026-11-13) the POST
routes take {"project": ...}; the old {"flow": ...} is a 400 (docs/planning/project-model.md)."""

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
FIXTURES = REPO / "services/frontend/src/lib/flow/fixtures"
PROJECT_JSON = FIXTURES / "project_sample.json"
XMAS_JSON = FIXTURES / "project_xmas_dun02.json"
ENVS = REPO / "config/environments.yaml"


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
            "status_hz": 20.0, "settings_dir": tmp_path / "settings", "environments_file": ENVS,
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
    """The IR 2 sample GET /flows/sample still serves."""
    return dict(json.loads(SAMPLE_JSON.read_text()))


def project() -> dict[str, Any]:
    """The two-map sample PROJECT (format 3): login -> character -> town -> field."""
    return dict(json.loads(PROJECT_JSON.read_text()))


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
    # #17: the configured run-time limits (flows_settings.runtime_limits; Batt's defaults for now)
    assert doc["runtime_limits"] == {"default_s": 14_400, "max_s": 86_400}
    assert "basic_info" in doc["windows"] and "walk_to" in doc["palette"]
    # Amendment C (2026-11-13): the hotbar key block, the runner block and where it may run
    (key,) = doc["blocks"]["press_key"]["spec"]["params"]
    assert key["type"] == "str" and key["options"] == [f"F{i}" for i in range(1, 10)]
    assert {p["type"] for p in doc["blocks"]["dungeon_hunt"]["spec"]["params"]} == {"proc"}
    assert doc["runner_maps"] == ["xmas_dun02"]
    # the project model: the session blocks, the credentials by name, the tab-name rule
    assert {"login", "choose_character"} <= set(doc["blocks"])
    assert doc["credentials"] == ["lab_gm", "lab_player"]
    assert doc["project"] == {"format": "poring-lab.project", "version": 3}
    assert doc["tab_name_rule"]["pattern"] == "^[a-z][a-z0-9_]{0,19}$"
    assert {"global", "list", "built_in", "match"} <= set(doc["tab_name_rule"]["refused"])
    assert [s["id"] for s in doc["servers"] if s["lab"]] == ["lab-rathena"]
    s = client.get("/flows/sample", headers=H).json()
    assert s["flow"] == sample() and s["world"] == "sample"
    w = client.get("/flows/world?source=sample&maps=town_1&walk=true", headers=H).json()
    assert list(w["maps"]) == ["town_1"] and len(w["walk"]["town_1"]) == 90
    assert {n["key"] for n in w["maps"]["town_1"]["npcs"]} == {"n_kafra", "n_guide", "n_warper"}


@pytest.mark.parametrize("route", ["lint", "simulate", "python"])
def test_the_old_flow_body_is_refused_with_a_clear_400(make: Make, route: str) -> None:
    """The project model, section 8 (Batt's answer 6): IR 2 flows are not converted. An older
    browser tab sending {"flow": ...} hears why, in plain words."""
    client = make()
    r = post(client, route, {"flow": sample(), "world": "sample"})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == {
        "reason": "format_changed",
        "message": "the flow format changed: a project (format 3)",
    }
    # an IR 2 flow sent AS the project is refused too, by the engine, with the same words
    r = post(client, route, {"project": sample(), "world": "sample"})
    assert r.status_code == 422 and r.json()["detail"]["reason"] == "invalid_project"
    assert r.json()["detail"]["errors"][0].startswith("the flow format changed: a project")


def test_lint_simulate_python(make: Make) -> None:
    client = make()
    proj = project()
    r = post(client, "lint", {"project": proj, "world": "sample"})
    assert r.status_code == 200, r.text
    lint = r.json()
    assert len(lint["project_hash"]) == 64
    assert set(lint) >= {"counts", "findings", "run", "project_hash", "by_node", "effective"}
    assert lint["counts"]["error"] == 0, [f["message"] for f in lint["findings"]]
    # every finding names its node and tab; the path is "<node>/<tab>/<site>"
    for f in lint["findings"]:
        assert set(f) >= {"rule", "severity", "layer", "path", "message", "ack", "node", "tab"}
        if f["tab"]:
            assert f["path"].startswith(f"{f['node']}/{f['tab']}")
    # the real L2/L3/L4 bindings are not there for these blocks: READINESS items, by node (#6)
    assert lint["by_node"]["town"]["readiness"] >= 1
    assert {f["severity"] for f in lint["findings"] if f["rule"] == "bindings"} == {"readiness"}
    assert lint["run"]["allowed"] is False and "readiness item" in lint["run"]["summary"]
    assert "no configured maximum run time" not in lint["run"]["reasons"]  # the routes give one
    too_long = post(client, "lint", {"project": {**proj, "max_runtime_s": 90_000},
                                     "world": "sample"})  # fmt: skip
    assert "max_runtime_s 90000 is above the configured maximum 86400 (the Settings page)" in [
        f["text"] for f in too_long.json()["findings"]
    ]
    r = post(client, "simulate", {"project": proj, "world": "sample",
                                  "scenario": {"horizon_s": 300, "timeline": [
                                      {"t": 200, "set": {"is_dead": True}}]}})  # fmt: skip
    assert r.status_code == 200, r.text
    sim = r.json()
    assert sim["project_hash"] == lint["project_hash"]
    trace = sim["trace"]
    assert "death_respawn" in [x["kind"] for x in trace["transitions"]]
    assert [s["kind"] for s in trace["play"][:2]] == ["login", "character"]
    assert trace["play"][0]["node"] == "login/main/main.0" and trace["play"][2]["block"] == "town"
    assert trace["session"]["map"] == "town" and trace["session"]["length_s"] == 11.0
    assert sim["lint"]["counts"] == lint["counts"]
    py = post(client, "python", {"project": proj}).json()
    assert py["project_hash"] == lint["project_hash"]
    paths = [f["path"] for f in py["files"]]
    assert paths == ["login/main.py", "character/main.py", "town/main.py", "field/main.py",
                     "global/keys.py", "project.py"]  # fmt: skip
    keys = next(f for f in py["files"] if f["path"] == "global/keys.py")
    assert (keys["node"], keys["tab"]) == ("global", "keys")
    assert 'def butterfly_wing():\n    press_key("F9")' in keys["text"]
    assert NoInput.sent == []  # nothing ever reached an input path
    # the local world: no sheets generated for these synthetic maps -> unsupported, fail closed
    local = post(client, "lint", {"project": proj, "world": "local"}).json()
    assert any(f["rule"] == "map_sheet" for f in local["findings"])


def test_the_xmas_dun02_project_simulates_from_login(make: Make) -> None:
    """Its 0-error lint is the engine's test (test_project.py: no static data, the zones
    provider, the local KB); here the sample sheets lack its maps and this backend has no zones
    files: only those refuse (fail closed)."""
    client = make()
    proj = json.loads(XMAS_JSON.read_text())
    lint = post(client, "lint", {"project": proj, "world": "sample"}).json()
    errs = {f["rule"] for f in lint["findings"] if f["severity"] == "error"}
    assert errs <= {"map_sheet", "zones_missing"} and "map_sheet" in errs
    sim = post(client, "simulate", {"project": proj, "world": "sample",
                                    "scenario": {"horizon_s": 40}}).json()  # fmt: skip
    play = sim["trace"]["play"]
    assert [s["kind"] for s in play[:2]] == ["login", "character"]
    assert play[0]["server"] == "lab-rathena" and play[0]["credential"] == "lab_gm"
    assert all(s["block"] in (None, "xmas_dun02", "geffen") for s in play)


def test_a_secret_in_a_login_is_never_echoed(make: Make) -> None:
    """Section 5: a credential is a NAME. A value that looks like a secret is an error, and
    neither it, its project's hash nor the Python view carries it back (ADR-0004 c)."""
    client = make()
    proj = project()
    secret = "Hunter2-pass!"
    proj["nodes"][0]["tabs"][0]["main"][0]["params"]["credential"]["value"] = secret
    for route in ("lint", "simulate", "python"):
        r = post(client, route, {"project": proj, "world": "sample"})
        assert r.status_code == 200, r.text
        assert secret not in r.text and r.json()["project_hash"] is None
    lint = post(client, "lint", {"project": proj, "world": "sample"}).json()
    assert [f["rule"] for f in lint["findings"] if f["severity"] == "error"] == [
        "session_credential"]  # fmt: skip


def test_simulate_gives_the_play_list_with_encounters(make: Make) -> None:
    """The Maps page (2026-11-10): the run in order, with a monster placed for each attack
    (`encounters`, from `seed`) and the NPC each talk stands at; still computation only."""
    client = make()
    body = {"project": project(), "world": "sample",
            "scenario": {"horizon_s": 120, "encounters": True, "seed": 3}}  # fmt: skip
    r = post(client, "simulate", body)
    assert r.status_code == 200, r.text
    play = r.json()["trace"]["play"]
    kinds = {s["kind"] for s in play}
    assert {"login", "character", "walk", "talk", "fight", "exit", "item"} <= kinds
    fights = [s for s in play if s["kind"] == "fight"]
    assert fights and all(s["mob"] in (9101, 9102, 9105, 9109) and s["at"] for s in fights)
    assert next(s for s in play if s["kind"] == "talk")["at"] == [56, 44]  # n_kafra's cell
    item = next(s for s in play if s["kind"] == "item")
    assert (item["proc"], item["key"]) == ("butterfly_wing", "F9")
    assert post(client, "simulate", body).json()["trace"]["play"] == play  # the seed repeats
    # Run starts on a map node: a scenario may start there (no session)
    on_map = post(client, "simulate", {**body, "scenario": {"start_block": "field"}}).json()
    assert on_map["trace"]["play"][0]["block"] == "field" and on_map["trace"]["session"] is None
    bad = post(client, "simulate", {**body, "scenario": {"seed": -1}})
    assert bad.status_code == 422 and bad.json()["detail"]["reason"] == "invalid_scenario"
    assert NoInput.sent == []


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
        client.post("/flows/lint", json={"project": project()}, headers=headers),
    ):
        assert r.status_code == status
        assert r.json()["detail"]["reason"] == reason


def test_never_on_the_internal_listener(make: Make) -> None:
    client = make(public_port=8000)  # requests arrive on 80: not the public listener
    assert client.get("/flows/catalogue", headers=H).status_code == 404
    assert post(client, "lint", {"project": project()}).status_code == 404


def test_compute_needs_the_csrf_token_and_is_rate_limited(make: Make) -> None:
    client = make()
    r = post(client, "python", {"project": project()}, headers=H)
    assert r.status_code == 403 and r.json()["detail"]["reason"] == "csrf_invalid"
    forged = {**H, "x-csrf-token": "9999999999." + "0" * 64}
    assert post(client, "python", {"project": project()}, headers=forged).status_code == 403
    body = {"project": project(), "world": "sample"}
    codes = [post(client, "lint", body).status_code for _ in range(21)]
    assert codes[:20] == [200] * 20 and codes[-1] == 429  # lint and simulate: 20 a minute
    # the Python view has its own budget (2026-11-09, the studio's side pane): 120 a minute
    codes = [post(client, "python", {"project": project()}).status_code for _ in range(121)]
    assert codes[:120] == [200] * 120 and codes[-1] == 429
    drops = client.get("/health").json()["dropped_messages"]["flows_http"]
    assert drops["csrf_invalid"] == 2 and drops["rate_limited"] >= 2


def test_hostile_bodies(make: Make) -> None:
    client = make()
    big = {"project": {"pad": "x" * (2 << 20)}}
    assert post(client, "lint", big).json()["detail"]["reason"] == "too_large"
    r = post(client, "lint", {"project": {"pad": "x" * (1 << 20)}})  # under the body cap
    assert r.json()["detail"]["reason"] == "invalid_project"
    assert "at most 1048576" in r.json()["detail"]["errors"][0]
    deep: Any = {"kind": "lit", "value": 1}
    for _ in range(300):
        deep = {"kind": "not", "term": deep}
    r = post(client, "lint", {"project": {**project(), "stop_when": deep}})
    assert r.status_code == 422 and r.json()["detail"]["reason"] == "too_deep"
    raw = {**hdr(client), "content-type": "application/json"}
    r = client.post("/flows/lint", content=b"{not json", headers=raw)
    assert r.status_code == 422 and r.json()["detail"]["reason"] == "invalid_body"
    r = post(client, "lint", {"project": {**project(), "version": 4}})
    assert r.status_code == 422 and r.json()["detail"]["reason"] == "invalid_project"
    assert r.json()["detail"]["errors"] == [
        "version 4 is not supported: this engine reads format 3"
    ]
    # a shape problem names its node, tab and path
    bad = project()
    bad["nodes"][2]["tabs"][0]["name"] = "town_tab"
    r = post(client, "lint", {"project": bad})
    assert r.json()["detail"]["reason"] == "invalid_project"
    assert {"node": "town", "tab": "town_tab", "path": "town/town_tab",
            "message": "the first tab of town is its main tab (named main), not town_tab"} in (
        r.json()["detail"]["problems"])  # fmt: skip
    r = post(client, "lint", {"project": project(), "world": "/etc"})
    assert r.json()["detail"]["reason"] == "invalid_body"
    r = post(client, "simulate", {"project": project(), "scenario": {"horizon_s": 1e9}})
    assert r.json()["detail"]["reason"] == "invalid_scenario"
    r = post(client, "simulate", {"project": project(), "scenario": {"start_block": "nowhere"}})
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
    lint = post(client, "lint", {"project": project(), "world": "local"}).json()
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
