"""/flows/run (routes_flowrun.py): the Run button's backend side (Batt 2026-11-13). A request is
written for the host helper only behind write_gate. Since 2026-11-14 (live-blocks.md 12) a start
and a check are a PROJECT's (its setting blocks decide the runner's settings): the runner-only
start and GET / PUT /flows/config are gone."""

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
    2026-11-13 #16: the body there names no action; since 2026-11-14 it is {project, node})."""
    tok = routes_settings.csrf_token(c.app.state.poring)  # type: ignore[attr-defined]
    path = "/flows/run"
    if body.get("action") == "check":
        path = "/flows/run/check"
        body = {k: v for k, v in body.items() if k != "action"}
    return c.post(path, headers={**H, **({"x-csrf-token": tok} if csrf else {})},
                  json=body)  # fmt: skip


def hunt_project(**node_vars: Any) -> dict[str, Any]:
    """test_live_player's project with a hunt core on its map node field (its keys from the
    functions), the node's setting blocks ``node_vars`` in a tab of their own."""
    sys.path.insert(0, str(Path(__file__).parent))
    import test_live_player as tl

    d = tl.project([tl.HUNT, tl.wing_exit()])
    if node_vars:
        field = next(n for n in d["nodes"] if n["id"] == "field")
        field["tabs"].append({"name": "settings", "main": None, "defs": [],
                              "vars": {k: tl.lit(v) for k, v in node_vars.items()}})  # fmt: skip
    return d


def check(c: TestClient, project: dict[str, Any] | None = None, csrf: bool = True) -> Any:
    return post(c, {"action": "check", "project": project or hunt_project(), "node": "field"},
                csrf)  # fmt: skip


def assist(c: TestClient) -> None:
    c.app.state.poring.mux.set_mode(Mode.ASSIST, time.monotonic_ns())  # type: ignore[attr-defined]


def test_no_helper_reads_as_such_and_refuses(client: TestClient) -> None:
    r = client.get("/flows/run", headers=H)
    assert r.status_code == 200 and r.json()["state"] == "no_helper"
    r = post(client, {"action": "stop"})
    assert r.status_code == 503 and r.json()["detail"]["reason"] == "helper_not_running"
    r = check(client)
    assert r.status_code == 503 and r.json()["detail"]["reason"] == "helper_not_running"


def test_the_runner_only_start_is_gone(client: TestClient, tmp_path: Path) -> None:
    """2026-11-14 (Batt: "there should be no runner [page]"; live-blocks.md 12): a start of the
    runner flow is refused in words (a start is a project's, POST /flows/run/project); nothing is
    written; extra fields are refused, never passed on."""
    helper(tmp_path)
    assist(client)
    for body in ({"action": "start", "flow": FLOW}, {"action": "start", "flow": "project"},
                 {"action": "start", "flow": FLOW, "keys": KEYS}):  # fmt: skip
        r = post(client, body)
        assert r.status_code == 400 and r.json()["detail"]["reason"] == (
            "project_has_its_own_route"), body  # fmt: skip
    assert post(client, {"action": "start", "flow": FLOW, "args": ["--x"]}).status_code == 422
    assert post(client, {"action": "start", "flow": FLOW, "settings": {}}).status_code == 422
    assert not (tmp_path / "settings" / "flowrun" / "request.json").exists()


def test_a_check_is_refused_while_another_input_writer_plays(
    client: TestClient, tmp_path: Path
) -> None:
    """matpilot round 17 N5: the helper's status names another input writer of ours playing (its
    `busy`: a night chain, a runner, the live block player, an A/B series); a check is refused
    with that reason before anything is written (the helper refuses it too; a project start the
    same, test_a_project_run_is_refused_with_words_the_page_can_say)."""
    why = "an A/B series is running (one input writer at a time)"
    helper(tmp_path, state="busy", busy=why)
    st = client.get("/flows/run", headers=H).json()
    assert st["state"] == "busy" and st["busy"] == why and st["helper_alive"] is True
    r = check(client)
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "input_writer_busy"
    assert not (tmp_path / "settings" / "flowrun" / "request.json").exists()
    helper(tmp_path, state="idle", busy=None)  # gone: the check is allowed again
    assert check(client).status_code == 200


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
    r = check(client)
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "already_running"
    assert post(client, {"action": "stop"}).status_code == 200
    helper(tmp_path, state="running", age=routes_flowrun.HELPER_FRESH_S + 5)  # the helper died
    r = post(client, {"action": "stop"})
    assert r.status_code == 503


# --- 2026-11-14 (Batt: "make them ALL blocks"; live-blocks.md 12): the settings file is gone ------
def test_the_settings_file_endpoints_are_gone(client: TestClient, tmp_path: Path) -> None:
    helper(tmp_path)
    assert client.get("/flows/config", headers=H).status_code == 404
    tok = client.get("/settings/csrf", headers=H).json()["token"]
    r = client.put("/flows/config", headers={**H, "X-CSRF-Token": tok},
                   json={"scope": "global", "group": "loot", "values": {}})  # fmt: skip
    assert r.status_code in (404, 405)
    assert not (tmp_path / "settings" / "flowrun" / "config.json").exists()


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
    """A project's check (2026-11-14): its node, the keys of its functions and EVERY setting
    block's value (the node's > Global's > the default), computed here and checked again by the
    helper; HUMAN mode is enough (a check reads the screen only)."""
    import flow_run as fr

    helper(tmp_path)
    d = tmp_path / "settings" / "flowrun"
    assert check(client, csrf=False).status_code == 403
    r = client.post("/flows/run/check", json={"project": hunt_project(), "node": "field"})
    assert r.status_code == 403 and not (d / "request.json").exists()  # no Origin
    r = check(client, hunt_project(knife_hp_min=0.6, LOOT_TRIM_HOVERS=12))
    assert r.status_code == 200, r.text
    req = json.loads((d / "request.json").read_text())
    assert (req["action"], req["flow"], req["node"]) == ("check", "project", "field")
    assert set(req) == {"id", "action", "flow", "node", "keys", "vals", "at"}
    assert req["keys"] == {"heal_key": "F1", "fly_key": "F8", "home_key": "F9",
                           "knife_key": "F4", "dagger_key": "F5"}  # fmt: skip
    assert req["vals"]["knife_hp_min"] == 0.6 and req["vals"]["LOOT_TRIM_HOVERS"] == 12
    assert req["vals"]["potion_below"] == fr.fc.DEFAULTS["potion_below"]  # nobody set it
    got = fr.parse_request(json.dumps(req))  # the helper takes exactly what was written
    assert isinstance(got, dict) and got["vals"] == req["vals"] and got["keys"] == req["keys"]
    log = json.loads((d / "requests.jsonl").read_text().splitlines()[-1])
    assert log["action"] == "check" and "vals" not in log and log["vals_n"] == len(req["vals"])
    helper(tmp_path, state="running")
    r = check(client)
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "already_running"


def test_a_check_is_refused_in_words_when_the_project_cannot_be_checked(
    client: TestClient, tmp_path: Path
) -> None:
    sys.path.insert(0, str(Path(__file__).parent))
    import test_live_player as tl

    helper(tmp_path)
    d = tmp_path / "settings" / "flowrun"
    for project, node, want in (
        (hunt_project(knife_hp_min=0.95), "field", "settings_refused"),
        (hunt_project(hud_fast=0.5, BOX_EVERY_S=0.5), "field", "settings_refused"),
        (tl.project([tl.press("F2"), tl.wing_exit()]), "field", "no_hunt_core"),
        (hunt_project(), "login", "not_a_map_node"),
        ({"format": "nope"}, "field", "invalid_project"),
    ):  # fmt: skip
        r = post(client, {"action": "check", "project": project, "node": node})
        assert r.status_code in (400, 422) and r.json()["detail"]["reason"] == want, r.text
    r = post(client, {"action": "check", "project": hunt_project(), "node": "field", "x": 1})
    assert r.status_code == 422
    assert not (d / "request.json").exists()  # nothing refused was passed on


def test_a_check_waits_for_the_one_reading_and_its_result_reads_back(
    client: TestClient, tmp_path: Path
) -> None:
    helper(tmp_path)
    st_file = tmp_path / "settings" / "flowrun" / "status.json"
    st = json.loads(st_file.read_text())
    st["check"] = {"state": "checking", "at": "2026-11-13T18:30:05+07:00", "flow": "project",
                   "items": [], "ok": None}  # fmt: skip
    st_file.write_text(json.dumps(st))
    r = check(client)
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "check_running"
    item = {"id": "chat", "ok": False, "words": "the chat input is open", "value": "open"}
    st["check"] = {**st["check"], "state": "done", "items": [item], "ok": False}
    st_file.write_text(json.dumps(st))
    got = client.get("/flows/run", headers=H).json()
    assert got["check"]["items"] == [item] and got["check"]["at"] == "2026-11-13T18:30:05+07:00"


def test_stop_carries_no_keys(client: TestClient, tmp_path: Path) -> None:
    helper(tmp_path, state="running")
    r = post(client, {"action": "stop", "keys": KEYS})
    assert r.status_code == 400 and r.json()["detail"]["reason"] == "keys_refused"
    assert not (tmp_path / "settings" / "flowrun" / "request.json").exists()


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
    named = client.post(
        "/flows/run/check",
        headers=hd,
        json={"action": "start", "project": hunt_project(), "node": "field"},
    )
    assert named.status_code == 422
    old = client.post("/flows/run/check", headers=hd, json={"flow": FLOW})  # the old body
    assert old.status_code == 422
    assert client.post("/flows/run", headers=hd, json={"flow": FLOW}).status_code == 422
    assert not (d / "request.json").exists()
    ok = client.post("/flows/run/check", headers=hd, json={"project": hunt_project(),
                                                            "node": "field"})  # fmt: skip
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
