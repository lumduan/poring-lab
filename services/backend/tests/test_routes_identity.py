"""/settings/run-identity (routes_identity.py, Batt 2026-11-19, ADR-0020 Amendment R): who may play
a Run, set on the Settings page by a person -- the mode, and the characters remembered by pressing
Remember (the Run helper reads the name line once). The backend is the store's only writer."""

from __future__ import annotations

import base64
import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from poring_backend import routes_identity, routes_settings
from poring_backend.config import Settings
from poring_backend.main import create_app
from poring_env import runidentity as ri

ORIGIN = "http://lab.test:3000"
H = {"origin": ORIGIN}
LAN = ("192.168.1.50", 50123)
PLATE = base64.b64encode(bytes(range(256)) * 19 + bytes(range(8))).decode()  # 116*14*3 = 4872


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


def make(tmp_path: Path, peer: tuple[str, int] = LAN) -> Iterator[TestClient]:
    (tmp_path / "settings").mkdir(exist_ok=True)
    s = Settings(data_dir=tmp_path / "data", public_port=80, frontend_origins=ORIGIN,
                 status_hz=20.0, settings_dir=tmp_path / "settings",
                 lab_state_dir=tmp_path / "lab-state", host_lan_ip="192.168.1.13",
                 win_host="192.168.1.169")  # fmt: skip
    app = create_app(s, capture_factory=NoCapture, input_factory=NoInput)
    with TestClient(app, client=peer) as c:
        yield c


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    yield from make(tmp_path)


def helper_alive(tmp_path: Path) -> Path:
    d = tmp_path / "settings" / "flowrun"
    d.mkdir(parents=True, exist_ok=True)
    (d / "status.json").write_text(json.dumps({"v": 1, "state": "idle", "t_wall": time.time()}))
    return d


def tok(c: TestClient) -> dict[str, str]:
    return {**H, "x-csrf-token": routes_settings.csrf_token(c.app.state.poring)}  # type: ignore[attr-defined]


def put(c: TestClient, body: dict[str, Any], csrf: bool = True) -> Any:
    return c.put("/settings/run-identity", headers=tok(c) if csrf else H, json=body)


def remember(c: TestClient, name: str, rev: int = 0) -> Any:
    return c.post("/settings/run-identity/remember", headers=tok(c),
                  json={"base_revision": rev, "name": name})  # fmt: skip


class FakeHelper:
    """The host's Run helper: answers the next "plate" request with ``answer``."""

    def __init__(self, d: Path, answer: dict[str, Any] | None) -> None:
        self.d, self.answer = d, answer
        self.seen: list[dict[str, Any]] = []
        self.t = threading.Thread(target=self.run, daemon=True)
        self.t.start()

    def run(self) -> None:
        end = time.monotonic() + 10
        while time.monotonic() < end:
            f = self.d / "request.json"
            if f.exists():
                req = json.loads(f.read_text())
                f.unlink()
                self.seen.append(req)
                if self.answer is not None:
                    (self.d / "plate.json").write_text(json.dumps({"id": req["id"], **self.answer}))
                return
            time.sleep(0.02)


def audit_actions(tmp_path: Path) -> list[str]:
    out = []
    for f in sorted((tmp_path / "settings" / "allowlist_audit").glob("*.jsonl")):
        out += [json.loads(ln)["action"] for ln in f.read_text().splitlines() if ln.strip()]
    return out


def test_no_file_is_any_with_nobody_remembered(client: TestClient) -> None:
    v = client.get("/settings/run-identity", headers=H).json()
    assert v["store"] == "default" and v["mode"] == "any" == v["default_mode"]
    assert v["characters"] == [] and v["revision"] == 0 and v["modes"] == ["any", "known", "mine"]
    assert v["helper_alive"] is False


def test_reads_are_the_console_browsers_only(client: TestClient) -> None:
    assert client.get("/settings/run-identity").status_code == 403  # no Origin: a script
    evil = client.get("/settings/run-identity", headers={"origin": "http://evil"})
    assert evil.status_code == 403


def test_a_person_sets_the_mode_and_it_is_written_read_back_and_audited(
    client: TestClient, tmp_path: Path
) -> None:
    r = put(client, {"base_revision": 0, "mode": "known", "characters": []})
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["saved"] and v["mode"] == "known" and v["revision"] == 1 and v["store"] == "ok"
    stored = ri.parse((tmp_path / "settings" / ri.FILE_NAME).read_text())
    assert isinstance(stored, ri.Store) and stored.mode == "known"
    assert audit_actions(tmp_path) == ["run_identity_mode"]
    again = put(client, {"base_revision": 1, "mode": "known", "characters": []}).json()
    assert again["saved"] is False and again["revision"] == 1  # nothing changed: no new revision


def test_writes_are_a_persons_never_a_script_the_lab_host_or_a_stale_page(
    client: TestClient, tmp_path: Path
) -> None:
    body = {"base_revision": 0, "mode": "known", "characters": []}
    assert put(client, body, csrf=False).json()["detail"]["reason"] == "csrf_invalid"
    peers = ((("192.168.1.13", 1), "lab_host_peer"), (("192.168.1.169", 1), "windows_host_peer"))
    for peer, why in peers:
        for c in make(tmp_path, peer):
            assert put(c, body).json()["detail"]["reason"] == why
    assert not (tmp_path / "settings" / ri.FILE_NAME).exists()
    assert put(client, body).status_code == 200
    stale = put(client, {**body, "mode": "any"})  # base 0 again: the page is behind
    assert stale.status_code == 409 and stale.json()["detail"]["reason"] == "revision_conflict"


def test_remember_stores_the_helpers_name_line_under_the_typed_name(
    client: TestClient, tmp_path: Path
) -> None:
    d = helper_alive(tmp_path)
    fake = FakeHelper(d, {"ok": True, "w": 116, "h": 14, "rgb": PLATE, "same_as": None})
    r = remember(client, "โร้กสายฟ้า")
    assert r.status_code == 200, r.text
    v = r.json()
    assert [c["name"] for c in v["characters"]] == ["โร้กสายฟ้า"] and v["revision"] == 1
    assert v["characters"][0]["rgb"] == PLATE and v["remembered"] == v["characters"][0]["id"]
    assert fake.seen and set(fake.seen[0]) == {"id", "action", "at"}  # it names nothing else
    assert fake.seen[0]["action"] == "plate"
    assert not (d / "plate.json").exists()  # the picture is kept in the store only
    assert "โร้ก" not in (d / "requests.jsonl").read_text()  # the typed name is not logged there
    assert audit_actions(tmp_path) == ["char_remember"]


def test_remember_refuses_in_words_and_keeps_nothing(client: TestClient, tmp_path: Path) -> None:
    assert remember(client, "A").json()["detail"]["reason"] == "helper_not_running"
    d = helper_alive(tmp_path)
    FakeHelper(d, {"ok": False, "why": "the name line is blank"})
    r = remember(client, "A")
    assert r.status_code == 409
    assert r.json()["detail"] == {"reason": "plate_failed", "detail": "the name line is blank"}
    FakeHelper(d, {"ok": True, "w": 116, "h": 14, "rgb": PLATE, "same_as": "Rogue76bd"})
    assert remember(client, "B").json()["detail"] == {"reason": "already_remembered",
                                                     "detail": "Rogue76bd"}  # fmt: skip
    FakeHelper(d, {"ok": True, "w": 10, "h": 14, "rgb": PLATE, "same_as": None})
    assert remember(client, "C").json()["detail"]["reason"] == "plate_failed"
    assert remember(client, " spaced").json()["detail"]["reason"] == "name_spaces_at_ends"
    assert not (d / "plate.json").exists()
    assert not (tmp_path / "settings" / ri.FILE_NAME).exists()


def test_remember_times_out_and_cleans_up(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = helper_alive(tmp_path)
    monkeypatch.setattr(routes_identity, "PLATE_WAIT_S", 0.4)
    FakeHelper(d, None)  # takes the request, never answers
    r = remember(client, "A")
    assert r.status_code == 504 and r.json()["detail"]["reason"] == "plate_timeout"


def test_a_waiting_request_is_never_overwritten(client: TestClient, tmp_path: Path) -> None:
    d = helper_alive(tmp_path)
    (d / "request.json").write_text('{"id": "a Run start waiting"}')
    assert remember(client, "A").json()["detail"]["reason"] == "helper_busy"
    assert "Run start" in (d / "request.json").read_text()


def test_rename_and_forget_by_the_whole_list_and_never_add_by_put(
    client: TestClient, tmp_path: Path
) -> None:
    d = helper_alive(tmp_path)
    for i, name in enumerate(("Thief8fce", "Rogue76bd")):
        FakeHelper(d, {"ok": True, "w": 116, "h": 14, "rgb": PLATE, "same_as": None})
        assert remember(client, name, rev=i).status_code == 200
    v = client.get("/settings/run-identity", headers=H).json()
    a, b = v["characters"]
    dup = put(client, {"base_revision": 2, "mode": "any",
                       "characters": [{"id": a["id"], "name": "ROGUE76BD"},
                                      {"id": b["id"], "name": b["name"]}]})  # fmt: skip
    assert dup.json()["detail"]["reason"] == "name_taken"  # names are unique, any case
    made_up = put(client, {"base_revision": 2, "mode": "any",
                           "characters": [{"id": "c_12345678", "name": "X"}]})  # fmt: skip
    assert made_up.json()["detail"]["reason"] == "unknown_character"  # new ones come by Remember
    r = put(client, {"base_revision": 2, "mode": "known",
                     "characters": [{"id": b["id"], "name": "Rogue (lab)"}]})  # fmt: skip
    v = r.json()
    assert [c["name"] for c in v["characters"]] == ["Rogue (lab)"] and v["mode"] == "known"
    assert v["characters"][0]["rgb"] == PLATE  # a rename keeps the picture
    assert sorted(c["action"] for c in v["changes"]) == ["char_forget", "char_rename",
                                                         "run_identity_mode"]  # fmt: skip
    assert audit_actions(tmp_path)[-3:] == ["run_identity_mode", "char_forget", "char_rename"]


def test_an_unreadable_store_is_shown_and_a_save_with_no_character_replaces_it(
    client: TestClient, tmp_path: Path
) -> None:
    (tmp_path / "settings" / ri.FILE_NAME).write_text("{")
    v = client.get("/settings/run-identity", headers=H).json()
    assert v["store"] == "unreadable" and "not JSON" in v["problem"]
    keep = put(client, {"base_revision": 0, "mode": "any",
                        "characters": [{"id": "c_12345678", "name": "X"}]})  # fmt: skip
    assert keep.json()["detail"]["reason"] == "store_unreadable_characters"
    assert remember(client, "A").json()["detail"]["reason"] == "store_unreadable"
    r = put(client, {"base_revision": 0, "mode": "any", "characters": []})
    assert r.status_code == 200 and r.json()["store"] == "ok" and r.json()["saved"]
