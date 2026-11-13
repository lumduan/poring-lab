"""/flows/run (routes_flowrun.py): the Run button's backend side (Batt 2026-11-13). A request is
written for the host helper only behind write_gate, and only for a flow the helper lists."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from poring_backend import routes_flowrun, routes_settings
from poring_backend.config import Settings
from poring_backend.main import create_app
from poring_env.protocol import Mode


class NoCapture:  # as test_settings.py's
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


ORIGIN = "http://lab.test:3000"
H = {"origin": ORIGIN}
LAN = ("192.168.1.50", 50123)
FLOW = "xmas_dun02_rogue"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    (tmp_path / "settings").mkdir()
    s = Settings(data_dir=tmp_path / "data", public_port=80, frontend_origins=ORIGIN,
                 status_hz=20.0, settings_dir=tmp_path / "settings",
                 lab_state_dir=tmp_path / "lab-state", host_lan_ip="192.168.1.13",
                 win_host="192.168.1.169")  # fmt: skip
    app = create_app(s, capture_factory=NoCapture, input_factory=NoInput)
    with TestClient(app, client=LAN) as c:
        yield c


def helper(tmp_path: Path, state: str = "idle", age: float = 0.0) -> None:
    d = tmp_path / "settings" / "flowrun"
    d.mkdir(parents=True, exist_ok=True)
    st = {
        "v": 1,
        "state": state,
        "t_wall": time.time() - age,
        "flows": {FLOW: {"title": "t", "minutes": 120}},
    }
    (d / "status.json").write_text(json.dumps(st))


def post(c: TestClient, body: dict[str, Any], csrf: bool = True) -> Any:
    tok = routes_settings.csrf_token(c.app.state.poring)  # type: ignore[attr-defined]
    return c.post("/flows/run", headers={**H, **({"x-csrf-token": tok} if csrf else {})},
                  json=body)  # fmt: skip


def assist(c: TestClient) -> None:
    c.app.state.poring.mux.set_mode(Mode.ASSIST, time.monotonic_ns())  # type: ignore[attr-defined]


def test_no_helper_reads_as_such_and_refuses(client: TestClient) -> None:
    r = client.get("/flows/run", headers=H)
    assert r.status_code == 200 and r.json()["state"] == "no_helper"
    r = post(client, {"action": "start", "flow": FLOW})
    assert r.status_code == 503 and r.json()["detail"]["reason"] == "helper_not_running"


def test_a_start_writes_one_request_for_a_listed_flow(client: TestClient, tmp_path: Path) -> None:
    helper(tmp_path)
    r = post(client, {"action": "start", "flow": FLOW})
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "mode_not_assist"  # HUMAN
    assist(client)
    assert post(client, {"action": "start", "flow": "rm -rf"}).status_code == 400
    r = post(client, {"action": "start", "flow": FLOW})
    assert r.status_code == 200, r.text
    req = json.loads((tmp_path / "settings" / "flowrun" / "request.json").read_text())
    assert req["action"] == "start" and req["flow"] == FLOW
    assert set(req) == {"id", "action", "flow", "at"}
    log = (tmp_path / "settings" / "flowrun" / "requests.jsonl").read_text().splitlines()
    assert json.loads(log[-1])["client"] == LAN[0]
    # extra fields are refused, never passed on (a request names a flow, nothing else)
    assert post(client, {"action": "start", "flow": FLOW, "args": ["--x"]}).status_code == 422


def test_a_start_may_carry_settings_from_fixed_ranges(client: TestClient, tmp_path: Path) -> None:
    helper(tmp_path)
    assist(client)
    body = {
        "action": "start",
        "flow": FLOW,
        "settings": {"fly_key": "F8", "home_key": "F9", "weight_home": 0.5},
    }
    r = post(client, body)
    assert r.status_code == 200, r.text
    req = json.loads((tmp_path / "settings" / "flowrun" / "request.json").read_text())
    assert req["settings"] == {"fly_key": "F8", "home_key": "F9", "weight_home": 0.5}
    for bad in ({"fly_key": "F10"}, {"home_key": "Shift"}, {"weight_home": 0.95},
                {"weight_home": 0.1}, {"fly_key": "F8", "extra": 1}):  # fmt: skip
        assert (
            post(client, {"action": "start", "flow": FLOW, "settings": bad}).status_code == 422
        ), bad
    r = post(
        client, {"action": "start", "flow": FLOW, "settings": {"fly_key": "F8", "home_key": "F8"}}
    )
    assert r.status_code == 400 and r.json()["detail"]["reason"] == "settings_same_key"
    # Batt 2026-11-13 ~13:3x: the heal key, the Knife swap's keys and numbers are the person's too
    for bad in ({"knife_key": "F10"}, {"dagger_key": "Tab"}, {"heal_key": "F0"},
                {"knife_max_s": 0.1}, {"knife_max_s": 25}, {"knife_hp_min": 0.1},
                {"knife_hp_min": 0.95}):  # fmt: skip
        assert (
            post(client, {"action": "start", "flow": FLOW, "settings": bad}).status_code == 422
        ), bad
    for same in ({"knife_key": "F4", "dagger_key": "F4"}, {"heal_key": "F8", "fly_key": "F8"},
                 {"home_key": "F5", "dagger_key": "F5"}):  # fmt: skip
        r = post(client, {"action": "start", "flow": FLOW, "settings": same})
        assert r.status_code == 400 and r.json()["detail"]["reason"] == "settings_same_key", same
    mine = {"heal_key": "F2", "knife_key": "F6", "dagger_key": "F7", "knife_max_s": 0.2,
            "knife_hp_min": 0.35}  # fmt: skip
    r = post(client, {"action": "start", "flow": FLOW, "settings": mine})
    assert r.status_code == 200, r.text
    req = json.loads((tmp_path / "settings" / "flowrun" / "request.json").read_text())
    assert req["settings"] == mine  # the helper checks the whole set again (flow_run.settings_of)


def test_the_write_gate_holds(client: TestClient, tmp_path: Path) -> None:
    helper(tmp_path)
    assist(client)
    assert post(client, {"action": "start", "flow": FLOW}, csrf=False).status_code == 403
    r = client.post("/flows/run", json={"action": "start", "flow": FLOW})  # no Origin
    assert r.status_code == 403
    assert not (tmp_path / "settings" / "flowrun" / "request.json").exists()


def test_stop_and_busy(client: TestClient, tmp_path: Path) -> None:
    helper(tmp_path, state="idle")
    assist(client)
    r = post(client, {"action": "stop"})
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "nothing_running"
    helper(tmp_path, state="running")
    r = post(client, {"action": "start", "flow": FLOW})
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "already_running"
    assert post(client, {"action": "stop"}).status_code == 200
    helper(tmp_path, state="running", age=routes_flowrun.HELPER_FRESH_S + 5)  # the helper died
    r = post(client, {"action": "stop"})
    assert r.status_code == 503


# --- 2026-11-13 ~14:2x (Batt: "the heal and escape numbers: a global config for every map's flow;
# a map's flow that sets them again overrides it") ---------------------------------------------
def put_survival(c: TestClient, body: dict[str, Any], csrf: bool = True) -> Any:
    h = dict(H)
    if csrf:
        h["X-CSRF-Token"] = c.get("/settings/csrf", headers=H).json()["token"]
    return c.put("/flows/survival", json=body, headers=h)


def test_the_survival_numbers_every_map_then_a_maps_own(client: TestClient, tmp_path: Path) -> None:
    f = tmp_path / "settings" / "flowrun" / "survival.json"
    assert client.get("/flows/survival", headers=H).json() == {"global": {}, "maps": {}}
    g = {"potion_below": 0.3, "fly_below": 0.15, "fly_rate": 200, "fly_rate_below": 0.6}
    r = put_survival(client, {"scope": "global", "values": g})
    assert r.status_code == 200, r.text
    m = {"potion_below": 0.5, "fly_below": 0.25, "fly_rate": 120.4, "fly_rate_below": 0.55}
    assert (
        put_survival(client, {"scope": "map", "map": "xmas_dun02", "values": m}).status_code == 200
    )
    doc = json.loads(f.read_text())
    assert doc["v"] == 1 and doc["global"]["potion_below"] == 0.3
    assert doc["maps"]["xmas_dun02"]["fly_rate"] == 120.0  # whole HP per second
    got = client.get("/flows/survival", headers=H).json()
    assert got["maps"]["xmas_dun02"]["potion_below"] == 0.5 and got["global"]["fly_below"] == 0.15
    # the helper reads the same file the same way (scripts/flow_run.py, checked again there)
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
    import flow_run as fr

    vals, src = fr.survival_of(fr.FLOWS[FLOW], fr.read_survival(f))  # type: ignore[arg-type]
    assert vals["potion_below"] == 0.5 and set(src.values()) == {"map"}
    # clearing the map's own: every map's apply again; clearing every map's: the defaults
    assert (
        put_survival(client, {"scope": "map", "map": "xmas_dun02", "values": None}).status_code
        == 200
    )
    assert json.loads(f.read_text())["maps"] == {}
    assert put_survival(client, {"scope": "global", "values": None}).status_code == 200
    assert json.loads(f.read_text())["global"] == {}
    audit = (tmp_path / "settings" / "flowrun" / "survival.jsonl").read_text().splitlines()
    assert len(audit) == 4 and json.loads(audit[1])["map"] == "xmas_dun02"


def test_the_survival_numbers_are_refused_off_their_grid(
    client: TestClient, tmp_path: Path
) -> None:
    ok = {"potion_below": 0.4, "fly_below": 0.2, "fly_rate": 150, "fly_rate_below": 0.5}
    for bad in ({**ok, "potion_below": 0.33}, {**ok, "potion_below": 0.95},
                {**ok, "fly_below": 0.0},
                {**ok, "fly_rate": 20}, {**ok, "fly_rate": 5000}, {**ok, "fly_rate_below": 0.1},
                {**ok, "extra": 1}, {"potion_below": 0.4}):  # fmt: skip
        r = put_survival(client, {"scope": "global", "values": bad})
        assert r.status_code == 422, bad
    assert put_survival(client, {"scope": "map", "values": ok}).status_code == 400  # which map?
    assert put_survival(client, {"scope": "map", "map": "../etc", "values": ok}).status_code == 422
    assert put_survival(client, {"scope": "global", "values": ok}, csrf=False).status_code == 403
    # a file a person must look at is never written over
    f = tmp_path / "settings" / "flowrun" / "survival.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("{not json")
    assert client.get("/flows/survival", headers=H).json().get("broken") is True
    r = put_survival(client, {"scope": "global", "values": ok})
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "survival_file_broken"
    assert f.read_text() == "{not json"
