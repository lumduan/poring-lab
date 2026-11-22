"""/routes/record (routes_routerec.py): the console's Record route button, the backend side
(docs/planning/waypoints-npc-recording.md Amendment 11). A request is written for the host helper
(scripts/route_rec.py) only behind routes_settings.write_gate, unchanged; the backend starts
nothing and needs no mux mode (the person plays, the bot does not)."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from poring_backend import routes_routerec, routes_settings
from poring_backend.config import Settings
from poring_backend.main import create_app


class NoCapture:  # as test_routes_flowrun.py's
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


def rdir(tmp_path: Path) -> Path:
    return tmp_path / "settings" / "routerec"


def helper(tmp_path: Path, state: str = "idle", age: float = 0.0, busy: str | None = None,
           **extra: Any) -> None:  # fmt: skip
    d = rdir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    st = {"v": 1, "state": state, "detail": "d", "t_wall": time.time() - age, "busy": busy,
          "check": None, "recording": None, "last": None, "notifications": [], **extra}  # fmt: skip
    (d / "status.json").write_text(json.dumps(st))


def post(c: TestClient, body: dict[str, Any], csrf: bool = True) -> Any:
    tok = routes_settings.csrf_token(c.app.state.poring)  # type: ignore[attr-defined]
    return c.post("/routes/record", headers={**H, **({"x-csrf-token": tok} if csrf else {})},
                  json=body)  # fmt: skip


def request_of(tmp_path: Path) -> dict[str, Any]:
    got = json.loads((rdir(tmp_path) / "request.json").read_text())
    assert isinstance(got, dict)
    return got


def test_no_helper_reads_as_such_and_refuses(client: TestClient, tmp_path: Path) -> None:
    r = client.get("/routes/record", headers=H)
    assert r.status_code == 200
    st = r.json()
    assert st["state"] == "no_helper" and st["helper_alive"] is False
    assert "poring-lab-routerec.service" in st["detail"] and st["notifications"] == []
    for action in ("check", "start", "stop"):
        r = post(client, {"action": action})
        assert r.status_code == 503 and r.json()["detail"]["reason"] == "helper_not_running"
    assert not (rdir(tmp_path) / "request.json").exists()


def test_the_status_says_whether_the_helper_is_alive(client: TestClient, tmp_path: Path) -> None:
    note = {
        "id": "20261122T150000-2",
        "kind": "map_change",
        "level": "action",
        "text": "New map: type /where in the chat.",
        "at": "t",
        "recording": "20261122T150000",
    }
    helper(tmp_path, notifications=[note])
    st = client.get("/routes/record", headers=H).json()
    assert st["helper_alive"] is True and st["state"] == "idle" and st["notifications"] == [note]
    helper(tmp_path, state="recording", age=routes_routerec.HELPER_FRESH_S + 5)
    st = client.get("/routes/record", headers=H).json()
    assert st["helper_alive"] is False and "has not answered" in st["detail"]
    assert client.get("/routes/record").status_code == 403  # the console-browser gate: an Origin


def test_the_write_gate_holds(client: TestClient, tmp_path: Path) -> None:
    helper(tmp_path)
    assert post(client, {"action": "start"}, csrf=False).status_code == 403
    assert client.post("/routes/record", json={"action": "start"}).status_code == 403  # no Origin
    assert not (rdir(tmp_path) / "request.json").exists()


def test_the_lab_host_and_the_windows_host_may_not_record(tmp_path: Path) -> None:
    """write_gate unchanged: any process on the lab host can forge the Origin, and the Windows
    host is the PC the bot drives."""
    (tmp_path / "settings").mkdir()
    s = Settings(data_dir=tmp_path / "data", public_port=80, frontend_origins=ORIGIN,
                 status_hz=20.0, settings_dir=tmp_path / "settings",
                 lab_state_dir=tmp_path / "lab-state", host_lan_ip="192.168.1.13",
                 win_host="192.168.1.169")  # fmt: skip
    helper(tmp_path)
    for peer, reason in ((("192.168.1.13", 5000), "lab_host_peer"),
                         (("192.168.1.169", 5000), "windows_host_peer")):  # fmt: skip
        app = create_app(s, capture_factory=NoCapture, input_factory=NoInput)
        with TestClient(app, client=peer) as c:
            r = post(c, {"action": "start"})
            assert r.status_code == 403 and r.json()["detail"]["reason"] == reason
    assert not (rdir(tmp_path) / "request.json").exists()


def test_a_check_is_one_request_with_who_asked(client: TestClient, tmp_path: Path) -> None:
    helper(tmp_path)
    r = post(client, {"action": "check"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["action"] == "check" and len(body["id"]) == 32
    req = request_of(tmp_path)
    assert set(req) == {"id", "action", "at"} and req["id"] == body["id"]
    (logged,) = [
        json.loads(x) for x in (rdir(tmp_path) / "requests.jsonl").read_text().splitlines()
    ]
    assert logged["id"] == body["id"] and logged["client"] == "192.168.1.50"
    assert logged["origin"] == ORIGIN


def test_a_start_carries_the_map_and_nothing_else(client: TestClient, tmp_path: Path) -> None:
    helper(tmp_path)
    r = post(client, {"action": "start", "map": "xmas_dun02"})
    assert r.status_code == 200 and r.json()["map"] == "xmas_dun02"
    assert request_of(tmp_path)["map"] == "xmas_dun02"
    r = post(client, {"action": "start"})
    assert r.status_code == 200 and "map" not in request_of(tmp_path)
    (rdir(tmp_path) / "request.json").unlink()
    for bad in ({"action": "start", "map": "../../etc"}, {"action": "start", "map": "Prt_Fild"},
                {"action": "start", "argv": ["--x"]}, {"action": "record"}, {}):  # fmt: skip
        assert post(client, bad).status_code == 422, bad
    r = post(client, {"action": "check", "map": "xmas_dun02"})
    assert r.status_code == 400 and r.json()["detail"]["reason"] == "map_goes_with_start"
    assert not (rdir(tmp_path) / "request.json").exists()


def test_a_start_is_refused_while_a_bot_of_ours_plays(client: TestClient, tmp_path: Path) -> None:
    """A route recording is the PERSON's play (the helper refuses it too); a check only reads the
    screen, so it passes."""
    why = "the live block player is playing (one input writer at a time)"
    helper(tmp_path, state="busy", busy=why)
    r = post(client, {"action": "start"})
    assert r.status_code == 409 and r.json()["detail"] == {"reason": "input_writer_busy",
                                                            "detail": why}  # fmt: skip
    assert not (rdir(tmp_path) / "request.json").exists()
    assert post(client, {"action": "check"}).status_code == 200


def test_one_recording_at_a_time_and_stop_only_while_one_records(
    client: TestClient, tmp_path: Path
) -> None:
    helper(tmp_path, state="idle")
    r = post(client, {"action": "stop"})
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "nothing_recording"
    for state in ("starting", "recording", "stopping"):
        helper(tmp_path, state=state)
        for action in ("check", "start"):
            r = post(client, {"action": action})
            assert r.status_code == 409 and r.json()["detail"]["reason"] == "already_recording"
    helper(tmp_path, state="stopping")
    assert post(client, {"action": "stop"}).status_code == 409  # stopping already
    helper(tmp_path, state="recording")
    r = post(client, {"action": "stop"})
    assert r.status_code == 200 and request_of(tmp_path)["action"] == "stop"
    helper(tmp_path, state="recording", age=routes_routerec.HELPER_FRESH_S + 5)  # it died
    assert post(client, {"action": "stop"}).status_code == 503


def test_no_mux_mode_is_needed(client: TestClient, tmp_path: Path) -> None:
    """The mux boots HUMAN; a route recording is the person's play and sends no input."""
    helper(tmp_path)
    assert client.app.state.poring.mux.mode.value == "HUMAN"  # type: ignore[attr-defined]
    assert post(client, {"action": "start"}).status_code == 200


def test_the_refusal_rule_is_pure() -> None:
    def st(state: str, alive: bool = True, busy: str | None = None) -> dict[str, Any]:
        return {"state": state, "helper_alive": alive, "busy": busy}

    body = routes_routerec.RecordBody
    assert routes_routerec.refusal(body(action="check"), st("idle")) is None
    assert routes_routerec.refusal(body(action="start"), st("ended")) is None
    assert routes_routerec.refusal(body(action="start"), st("failed")) is None
    assert routes_routerec.refusal(body(action="start"), st("busy", busy="x")) == (
        409, "input_writer_busy")  # fmt: skip
    assert routes_routerec.refusal(body(action="check"), st("busy", busy="x")) is None
    assert routes_routerec.refusal(body(action="stop"), st("starting")) is None
    assert routes_routerec.refusal(body(action="stop"), st("ended")) == (409, "nothing_recording")
    assert routes_routerec.refusal(body(action="check"), st("idle", alive=False)) == (
        503, "helper_not_running")  # fmt: skip
