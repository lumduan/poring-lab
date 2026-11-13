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
