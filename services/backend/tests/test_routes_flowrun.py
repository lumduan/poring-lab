"""/flows/run (routes_flowrun.py): the Run button's backend side (Batt 2026-11-13). A request is
written for the host helper only behind write_gate, and only for a flow the helper lists."""

from __future__ import annotations

import json
import sys
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


def helper(tmp_path: Path, state: str = "idle", age: float = 0.0, busy: str | None = None) -> None:
    d = tmp_path / "settings" / "flowrun"
    d.mkdir(parents=True, exist_ok=True)
    st = {
        "v": 1,
        "state": state,
        "t_wall": time.time() - age,
        "busy": busy,
        "flows": {
            FLOW: {
                "title": "t",
                "minutes": 120,
                "map": "xmas_dun02",
                "defaults": {
                    "heal_key": "F1",
                    "fly_key": "F8",
                    "home_key": "F9",
                    "knife_key": "F4",
                    "dagger_key": "F5",
                    "knife_swap": True,
                },
            }
        },  # fmt: skip
    }
    (d / "status.json").write_text(json.dumps(st))


def post(c: TestClient, body: dict[str, Any], csrf: bool = True) -> Any:
    """POST /flows/run, or /flows/run/check for an action "check" (its own route since matpilot's
    2026-11-13 #16: the body there names no action)."""
    tok = routes_settings.csrf_token(c.app.state.poring)  # type: ignore[attr-defined]
    path = "/flows/run"
    if body.get("action") == "check":
        path = "/flows/run/check"
        body = {k: v for k, v in body.items() if k != "action"}
    return c.post(path, headers={**H, **({"x-csrf-token": tok} if csrf else {})},
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


def test_a_start_or_a_check_is_refused_while_another_input_writer_plays(
    client: TestClient, tmp_path: Path
) -> None:
    """matpilot round 17 N5: the helper's status names another input writer of ours playing (its
    `busy`: a night chain, a runner, the live block player, an A/B series); a start and a check
    are refused with that reason before anything is written (the helper refuses them too)."""
    why = "an A/B series is running (one input writer at a time)"
    helper(tmp_path, state="busy", busy=why)
    assist(client)
    st = client.get("/flows/run", headers=H).json()
    assert st["state"] == "busy" and st["busy"] == why and st["helper_alive"] is True
    for body in ({"action": "start", "flow": FLOW}, {"action": "check", "flow": FLOW}):
        r = post(client, body)
        assert r.status_code == 409 and r.json()["detail"]["reason"] == "input_writer_busy", body
    assert not (tmp_path / "settings" / "flowrun" / "request.json").exists()
    helper(tmp_path, state="idle", busy=None)  # gone: Run is allowed again
    assert post(client, {"action": "start", "flow": FLOW}).status_code == 200


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
    r = put_config(client, {"scope": "global", "group": "survival", "values": None})
    assert r.status_code == 200
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


def test_the_end_picture_is_served_to_the_console(client: TestClient, tmp_path: Path) -> None:
    """matpilot 2026-11-13: "show end.png as an image, not a server path"."""
    helper(tmp_path)
    assert client.get("/flows/run/end.png", headers=H).status_code == 404
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
    (tmp_path / "settings" / "flowrun" / "end.png").write_bytes(png)
    r = client.get("/flows/run/end.png", headers=H)
    assert r.status_code == 200 and r.content == png and r.headers["content-type"] == "image/png"


# --- dungeon@9.45 (Batt 2026-11-13 "do it"): the start checklist ticked from the game screen; the
# flow's keys (Batt: every hotbar key from a FUNCTION of the flow) ---------------------------------
KEYS = {"heal_key": "F2", "fly_key": "F3", "home_key": "F6", "knife_key": "F7", "dagger_key": "F9"}


def test_a_check_is_one_request_behind_the_write_gate(client: TestClient, tmp_path: Path) -> None:
    helper(tmp_path)  # HUMAN: a check reads the screen only, so it needs no ASSIST
    d = tmp_path / "settings" / "flowrun"
    assert post(client, {"action": "check", "flow": FLOW}, csrf=False).status_code == 403
    r = client.post("/flows/run/check", json={"flow": FLOW})  # no Origin
    assert r.status_code == 403 and not (d / "request.json").exists()
    r = post(client, {"action": "check", "flow": FLOW})
    assert r.status_code == 200, r.text
    req = json.loads((d / "request.json").read_text())
    assert (
        req["action"] == "check"
        and req["flow"] == FLOW
        and set(req) == {"id", "action", "flow", "at"}
    )
    assert json.loads((d / "requests.jsonl").read_text().splitlines()[-1])["action"] == "check"
    assert post(client, {"action": "check", "flow": "rm -rf"}).status_code == 400
    helper(tmp_path, state="running")
    r = post(client, {"action": "check", "flow": FLOW})
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "already_running"


def test_a_check_waits_for_the_one_reading_and_its_result_reads_back(
    client: TestClient, tmp_path: Path
) -> None:
    helper(tmp_path)
    st_file = tmp_path / "settings" / "flowrun" / "status.json"
    st = json.loads(st_file.read_text())
    st["check"] = {"state": "checking", "at": "2026-11-13T18:30:05+07:00", "flow": FLOW,
                   "items": [], "ok": None}  # fmt: skip
    st_file.write_text(json.dumps(st))
    r = post(client, {"action": "check", "flow": FLOW})
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "check_running"
    item = {"id": "chat", "ok": False, "words": "the chat input is open", "value": "open"}
    st["check"] = {**st["check"], "state": "done", "items": [item], "ok": False}
    st_file.write_text(json.dumps(st))
    got = client.get("/flows/run", headers=H).json()
    assert got["check"]["items"] == [item] and got["check"]["at"] == "2026-11-13T18:30:05+07:00"


def test_the_flows_keys_go_with_start_and_check_all_five(
    client: TestClient, tmp_path: Path
) -> None:
    helper(tmp_path)
    assist(client)
    d = tmp_path / "settings" / "flowrun"
    for action in ("check", "start"):
        r = post(client, {"action": action, "flow": FLOW, "keys": KEYS})
        assert r.status_code == 200, r.text
        assert r.json()["keys"] == KEYS
        req = json.loads((d / "request.json").read_text())
        assert req["keys"] == KEYS and req["action"] == action
        assert json.loads((d / "requests.jsonl").read_text().splitlines()[-1])["keys"] == KEYS
    (d / "request.json").unlink()
    for keys, word in (({**KEYS, "steal_key": "F1"}, "only heal_key"),
                       ({k: v for k, v in KEYS.items() if k != "dagger_key"}, "lack dagger_key"),
                       ({**KEYS, "fly_key": "F10"}, "not a row-1 hotbar key")):  # fmt: skip
        r = post(client, {"action": "start", "flow": FLOW, "keys": keys})
        assert r.status_code == 400 and r.json()["detail"]["reason"] == "keys_refused", r.text
        assert word in r.json()["detail"]["detail"], (keys, r.text)
    helper(tmp_path, state="running")
    r = post(client, {"action": "stop", "keys": KEYS})
    assert r.status_code == 400 and "not stop" in r.json()["detail"]["detail"]
    assert not (d / "request.json").exists()  # nothing refused was passed on
    # any other field is still refused (a request names a flow and the flow's keys, nothing else)
    assert post(client, {"action": "check", "flow": FLOW, "settings": {}}).status_code == 422


def test_the_check_has_its_own_route_and_a_start_body_can_never_be_a_check(
    client: TestClient, tmp_path: Path
) -> None:
    """matpilot 2026-11-13 #16: a guard tells a start from a check by the route; POST /flows/run
    with action "check" is refused, a check body that names an action is refused (422), and a body
    without an action never reaches the helper."""
    helper(tmp_path)
    d = tmp_path / "settings" / "flowrun"
    tok = routes_settings.csrf_token(client.app.state.poring)  # type: ignore[attr-defined]
    hd = {**H, "x-csrf-token": tok}
    bad = client.post("/flows/run", headers=hd, json={"action": "check", "flow": FLOW})
    assert bad.status_code == 400 and bad.json()["detail"]["reason"] == "check_has_its_own_route"
    named = client.post("/flows/run/check", headers=hd, json={"action": "start", "flow": FLOW})
    assert named.status_code == 422
    assert client.post("/flows/run", headers=hd, json={"flow": FLOW}).status_code == 422
    assert not (d / "request.json").exists()
    ok = client.post("/flows/run/check", headers=hd, json={"flow": FLOW})
    assert ok.status_code == 200
    assert json.loads((d / "request.json").read_text())["action"] == "check"


# --- Run of a PROJECT (live-blocks.md stage 1): POST /flows/run/project ---------------------------
def _project(main: list[Any] | None = None) -> dict[str, Any]:
    """test_live_player's project, its field main after the world rule (the save point)."""
    sys.path.insert(0, str(Path(__file__).parent))
    import test_live_player as tl

    save = tl.action("assert_save_point", "core.assert_save_point", {"cell": tl.lit(
        {"kind": "cell", "map": "geffen", "x": 119, "y": 40})}, 1.0)  # fmt: skip
    return tl.project([save, *(main if main is not None else [tl.press("F2"), tl.wing_exit()])])


@pytest.fixture(autouse=True)
def no_kb(monkeypatch: pytest.MonkeyPatch) -> None:
    """A test has no local KB: the project's static data is "not loaded" (the linter then skips
    the map sheets, and the real run-start verdict refuses: no static data)."""
    from poring_backend import routes_flows

    monkeypatch.setattr(routes_flows, "_world", lambda *_a, **_k: (None, []))


def post_project(c: TestClient, body: dict[str, Any]) -> Any:
    tok = routes_settings.csrf_token(c.app.state.poring)  # type: ignore[attr-defined]
    return c.post("/flows/run/project", headers={**H, "x-csrf-token": tok}, json=body)


def reason(r: Any) -> str:
    return str(r.json()["detail"]["reason"])


@pytest.fixture
def allowed(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """The run-start verdict as it reads with the lab's static data (the KB is not in a test):
    allowed; every other check stays real."""
    from poring_flow import live, runstart

    seen: list[Any] = []

    def verdict(c: Any, findings: list[Any], **kw: Any) -> Any:
        seen.append((c, findings, kw))
        return runstart.Verdict(True, "h", (), (), ())

    monkeypatch.setattr(live, "verdict", verdict)
    return seen


def test_a_project_run_writes_the_checked_project_and_one_request(
    client: TestClient, tmp_path: Path, allowed: list[Any]
) -> None:
    import hashlib

    from poring_flow import project as pj

    helper(tmp_path)
    body = {"project": _project(), "node": "field"}
    assert reason(post_project(client, body)) == "mode_not_assist"  # HUMAN: nothing written
    d = tmp_path / "settings" / "flowrun"
    assert not (d / "project.json").exists() and not (d / "request.json").exists()
    assist(client)
    r = post_project(client, body)
    assert r.status_code == 200, r.text
    got = r.json()
    p = pj.from_json(json.dumps(body["project"]))
    assert got["project_hash"] == pj.project_hash(p) and got["flow"] == "project"
    raw = (d / "project.json").read_bytes()
    assert raw == pj.canonical_json(p).encode() and hashlib.sha256(raw).hexdigest() == got[
        "project_hash"]  # fmt: skip
    req = json.loads((d / "request.json").read_text())
    assert set(req) == {"id", "action", "flow", "node", "project_hash", "max_s", "at"}
    assert (req["action"], req["flow"], req["node"]) == ("start", "project", "field")
    import flow_run as fr  # the helper takes exactly what the backend wrote

    assert fr.parse_request(json.dumps(req)) == {k: req[k] for k in req if k != "at"}
    log = [json.loads(x) for x in (d / "requests.jsonl").read_text().splitlines()]
    assert log[-1]["project"] == "live_test" and "nodes" not in log[-1]  # who, what, its hash
    assert allowed and allowed[0][2]["runtime_max_s"] == 86_400


def test_a_project_with_a_hunt_core_carries_its_keys(
    client: TestClient, tmp_path: Path, allowed: list[Any]
) -> None:
    sys.path.insert(0, str(Path(__file__).parent))
    import test_live_player as tl

    helper(tmp_path)
    assist(client)
    r = post_project(client, {"project": _project([tl.HUNT, tl.wing_exit()]), "node": "field"})
    assert r.status_code == 200, r.text
    keys = {"heal_key": "F1", "fly_key": "F8", "home_key": "F9", "knife_key": "F4",
            "dagger_key": "F5"}  # fmt: skip
    assert r.json()["keys"] == keys
    req = json.loads((tmp_path / "settings" / "flowrun" / "request.json").read_text())
    assert req["keys"] == keys


def test_a_project_run_is_refused_with_words_the_page_can_say(
    client: TestClient, tmp_path: Path, allowed: list[Any]
) -> None:
    sys.path.insert(0, str(Path(__file__).parent))
    import test_live_player as tl

    helper(tmp_path)
    assist(client)
    d = tmp_path / "settings" / "flowrun"
    walk = tl.action("walk_to", "nav.walk_to", {"cell": tl.lit({"kind": "cell", "map":
                                                               "xmas_dun02", "x": 9, "y": 9})},
                     120.0)  # fmt: skip
    r = post_project(client, {"project": _project([walk, tl.wing_exit()]), "node": "field"})
    assert r.status_code == 400 and reason(r) == "not_live"
    (row,) = r.json()["detail"]["detail"]
    assert row == {"path": "field/main/main.1", "what": "walk_to",
                   "words": "walk_to cannot play live yet (stage 4)"}  # fmt: skip
    r = post_project(client, {"project": _project([tl.call("no_such_function")]), "node": "field"})
    assert r.status_code == 400 and reason(r) == "lint_errors"
    assert r.json()["detail"]["detail"]["count"] >= 1
    r = post_project(client, {"project": _project(), "node": "login"})
    assert r.status_code == 400 and reason(r) == "not_a_map_node"
    r = post_project(client, {"project": {"format": "nope"}, "node": "field"})
    assert r.status_code == 422 and reason(r) == "invalid_project"
    r = post_project(client, {"project": _project(), "node": "field", "argv": ["--clear-map"]})
    assert r.status_code == 422 and reason(r) == "invalid_body"
    no_keys = _project([tl.HUNT])  # a hunt core whose map node has no wing home: no home key
    r = post_project(client, {"project": no_keys, "node": "field"})
    assert r.status_code == 400 and reason(r) in ("keys_refused", "lint_errors")
    assert not (d / "request.json").exists() and not (d / "project.json").exists()
    # the helper's state: running, or not answering
    helper(tmp_path, state="running")
    assert reason(post_project(client, {"project": _project(), "node": "field"})) == (
        "already_running"
    )
    helper(tmp_path, state="busy", busy="the night chain is running (one input writer at a time)")
    r = post_project(client, {"project": _project(), "node": "field"})
    assert r.status_code == 409 and reason(r) == "input_writer_busy"  # round 17 N5
    assert r.json()["detail"]["detail"] == "the night chain is running (one input writer at a time)"
    helper(tmp_path, age=60.0)
    r = post_project(client, {"project": _project(), "node": "field"})
    assert r.status_code == 503 and reason(r) == "helper_not_running"
    # a project start never goes through POST /flows/run
    helper(tmp_path)
    r = post(client, {"action": "start", "flow": "project"})
    assert r.status_code == 400 and reason(r) == "project_has_its_own_route"


def test_the_run_start_verdict_is_the_engines_and_refuses_without_static_data(
    client: TestClient, tmp_path: Path
) -> None:
    """No KB in a test: the real verdict fails closed (no static data), and says so."""
    helper(tmp_path)
    assist(client)
    r = post_project(client, {"project": _project(), "node": "field"})
    assert r.status_code == 400 and reason(r) == "run_start_refused", r.text
    assert "no static data" in json.dumps(r.json()["detail"]["detail"])


def test_a_project_run_needs_the_write_gate(client: TestClient, tmp_path: Path) -> None:
    helper(tmp_path)
    assist(client)
    r = client.post("/flows/run/project", headers=H, json={"project": _project(), "node": "field"})
    assert r.status_code == 403  # no CSRF token
    r = client.post("/flows/run/project", headers={"origin": "http://evil.test"},
                    json={"project": _project(), "node": "field"})  # fmt: skip
    assert r.status_code == 403
