"""/settings/run-log (routes_runlog.py, Batt 2026-11-21): the Run log's settings, set on the
Settings page by a person -- record or not (default not), the folder, the total size cap."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from poring_env import runlog as rl

sys.path.insert(0, str(Path(__file__).resolve().parent))  # the sibling test's app fixture
from test_routes_identity import H, make, tok  # noqa: E402


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    yield from make(tmp_path)


def put(c: TestClient, body: dict[str, Any], csrf: bool = True) -> Any:
    return c.put("/settings/run-log", headers=tok(c) if csrf else H, json=body)


def body(**kw: Any) -> dict[str, Any]:
    return {"base_revision": 0, "record": True, "folder": "logs/bot", "max_total_mb": 100, **kw}


def test_the_default_is_off_and_shown_as_the_default(client: TestClient) -> None:
    r = client.get("/settings/run-log", headers=H)
    assert r.status_code == 200
    d = r.json()
    assert d["store"] == "default" and d["record"] is False and d["folder"] == "logs/bot"
    assert d["max_total_mb"] == 100 and d["files"] == ["story.jsonl", "story.log"]


def test_a_person_saves_it_read_back_and_audited(client: TestClient, tmp_path: Path) -> None:
    r = put(client, body(folder="/mnt/nas/bot-logs", max_total_mb=250))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["saved"] is True and d["revision"] == 1 and d["record"] is True
    f = tmp_path / "settings" / rl.FILE_NAME
    want = rl.Store(revision=1, record=True, folder="/mnt/nas/bot-logs", max_total_mb=250)
    assert rl.parse(f.read_text()) == want
    audit = (tmp_path / "settings" / "allowlist_audit").glob("*.jsonl")
    text = "".join(p.read_text() for p in audit)
    assert "The Run log" in text and "record on" in text
    # the same values again: nothing saved; an old revision: refused
    assert put(client, body(base_revision=1, folder="/mnt/nas/bot-logs",
                            max_total_mb=250)).json()["saved"] is False  # fmt: skip
    assert put(client, body(base_revision=0)).status_code == 409


@pytest.mark.parametrize(("change", "reason"), [
    ({"folder": "logs/../../etc"}, "folder_dotdot"), ({"folder": "  "}, "folder_empty"),
    ({"folder": "/"}, "folder_root"), ({"max_total_mb": 0}, "max_out_of_range")])  # fmt: skip
def test_a_bad_folder_or_cap_is_refused(client: TestClient, change: dict[str, Any],
                                        reason: str) -> None:  # fmt: skip
    r = put(client, body(**change))
    assert r.status_code == 400 and r.json()["detail"]["reason"] == reason


def test_only_a_person_s_browser_writes(client: TestClient, tmp_path: Path) -> None:
    assert put(client, body(), csrf=False).status_code == 403  # no CSRF token
    assert not (tmp_path / "settings" / rl.FILE_NAME).exists()


def test_an_unreadable_file_shows_the_default_until_a_person_saves(
    client: TestClient, tmp_path: Path
) -> None:
    (tmp_path / "settings" / rl.FILE_NAME).write_text("not json")
    d = client.get("/settings/run-log", headers=H).json()
    assert d["store"] == "unreadable" and d["record"] is False and d["problem"]
    r = put(client, body(base_revision=7))
    assert r.status_code == 200 and r.json()["revision"] == 8
    assert json.loads((tmp_path / "settings" / rl.FILE_NAME).read_text())["record"] is True
