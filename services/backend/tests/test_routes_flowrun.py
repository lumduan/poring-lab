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
        "flows": {FLOW: {"title": "t", "minutes": 120, "map": "xmas_dun02",
                         "defaults": {"heal_key": "F1", "fly_key": "F8", "home_key": "F9",
                                      "knife_key": "F4", "dagger_key": "F5"}}},  # fmt: skip
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


def test_a_start_carries_no_settings(client: TestClient, tmp_path: Path) -> None:
    """Batt 2026-11-13 ~14:4x: every setting lives in the config file (every map's, a map's own);
    a Run request names a flow and nothing else."""
    helper(tmp_path)
    assist(client)
    r = post(client, {"action": "start", "flow": FLOW, "settings": {"fly_key": "F8"}})
    assert r.status_code == 422  # extra fields are refused
    assert post(client, {"action": "start", "flow": FLOW}).status_code == 200
    req = json.loads((tmp_path / "settings" / "flowrun" / "request.json").read_text())
    assert set(req) == {"id", "action", "flow", "at"}


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


# --- 2026-11-13 (Batt: "nothing is fixed, we only put the defaults"; "a global config for every
# map's flow, a map's own on top"; scripts/flow_config.py is the registry) ----------------------
def put_config(c: TestClient, body: dict[str, Any], csrf: bool = True) -> Any:
    h = dict(H)
    if csrf:
        h["X-CSRF-Token"] = c.get("/settings/csrf", headers=H).json()["token"]
    return c.put("/flows/config", json=body, headers=h)


def test_the_config_every_map_then_a_maps_own(client: TestClient, tmp_path: Path) -> None:
    helper(tmp_path)  # its status lists the flow's map and defaults (the clash check reads them)
    d = tmp_path / "settings" / "flowrun"
    assert client.get("/flows/config", headers=H).json() == {"global": {}, "maps": {}}
    g = {"potion_below": 0.3, "fly_below": 0.15, "fly_rate": 200, "fly_rate_below": 0.6}
    r = put_config(client, {"scope": "global", "group": "survival", "values": g})
    assert r.status_code == 200, r.text
    r = put_config(client, {"scope": "map", "map": "xmas_dun02", "group": "loot",
                            "values": {"LOOT_TRIM_HOVERS": 12, "LOOT_MAX_S": 30}})  # fmt: skip
    assert r.status_code == 200, r.text
    doc = json.loads((d / "config.json").read_text())
    assert doc["v"] == 2 and doc["global"]["potion_below"] == 0.3
    assert doc["maps"]["xmas_dun02"] == {"LOOT_TRIM_HOVERS": 12, "LOOT_MAX_S": 30.0}
    # the helper reads the same file the same way
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
    import flow_config as fc
    import flow_run as fr

    vals, src = fr.config_of(fr.FLOWS[FLOW], fc.read_config(d))  # type: ignore[arg-type]
    assert vals["potion_below"] == 0.3 and src["potion_below"] == "global"
    assert vals["LOOT_TRIM_HOVERS"] == 12 and src["LOOT_TRIM_HOVERS"] == "map"
    # a group's values replace only that group's at that level; None removes them
    r = put_config(client, {"scope": "map", "map": "xmas_dun02", "group": "loot", "values": None})
    assert r.status_code == 200 and json.loads((d / "config.json").read_text())["maps"] == {}
    assert put_config(client, {"scope": "global", "group": "survival", "values": None}).status_code == 200
    assert json.loads((d / "config.json").read_text())["global"] == {}
    audit = (d / "config.jsonl").read_text().splitlines()
    assert len(audit) == 4 and json.loads(audit[1])["group"] == "loot"


def test_the_config_refuses_what_could_not_run(client: TestClient, tmp_path: Path) -> None:
    helper(tmp_path)
    d = tmp_path / "settings" / "flowrun"
    for body, word in (
        ({"scope": "global", "group": "survival", "values": {"potion_below": 0.33}}, "step"),
        ({"scope": "global", "group": "loot", "values": {"LOOT_TRIM_HOVERS": 99}}, "is not from"),
        ({"scope": "global", "group": "loot", "values": {"potion_below": 0.3}}, "not in the group"),
        ({"scope": "global", "group": "nope", "values": {}}, "unknown group"),
        ({"scope": "map", "group": "loot", "values": {}}, "map's name"),
        ({"scope": "global", "group": "keys", "values": {"dagger_key": "F4"}}, "both on F4"),
    ):  # fmt: skip
        r = put_config(client, body)
        assert r.status_code == 400 and word in r.json()["detail"]["detail"], (body, r.text)
    assert put_config(client, {"scope": "map", "map": "../etc", "group": "loot"}).status_code == 422
    ok = {"scope": "global", "group": "loot", "values": {"LOOT_TRIM_HOVERS": 12}}
    assert put_config(client, ok, csrf=False).status_code == 403
    assert not (d / "config.json").exists()  # nothing refused was written
    # a file a person must look at is never written over
    (d / "config.json").write_text("{not json")
    assert "not valid JSON" in client.get("/flows/config", headers=H).json()["broken"]
    r = put_config(client, ok)
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "config_file_broken"
    assert (d / "config.json").read_text() == "{not json"
