"""/settings/econ-prices (routes_econprices.py, Batt 2026-11-21): the /economy page's saved prices --
"a drop whose price is unknown: blank for the user to type; the system remembers it when Update is
pressed, so next time it need not be typed again"."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from poring_env import econprices as ep

sys.path.insert(0, str(Path(__file__).resolve().parent))  # the sibling test's app fixture
from test_routes_identity import H, make, tok  # noqa: E402


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    yield from make(tmp_path)


def put(c: TestClient, body: dict[str, Any], csrf: bool = True) -> Any:
    return c.put("/settings/econ-prices", headers=tok(c) if csrf else H, json=body)


def test_none_saved_is_the_default(client: TestClient) -> None:
    d = client.get("/settings/econ-prices", headers=H).json()
    assert d["store"] == "default" and d["sell"] == {} and d["buy"] == {} and d["revision"] == 0


def test_update_saves_read_back_and_audited(client: TestClient, tmp_path: Path) -> None:
    r = put(client, {"base_revision": 0, "sell": {"7037": 120, "912": 0}, "buy": {"601": 60}})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["saved"] is True and d["revision"] == 1 and d["sell"] == {"7037": 120, "912": 0}
    want = ep.Store(1, {"7037": 120, "912": 0}, {"601": 60})
    assert ep.parse((tmp_path / "settings" / ep.FILE_NAME).read_text()) == want
    text = "".join(
        p.read_text() for p in (tmp_path / "settings" / "allowlist_audit").glob("*.jsonl")
    )
    assert "The economy prices" in text and "sell #912: - -> 0" in text
    again = {"base_revision": 1, "sell": {"7037": 120, "912": 0}, "buy": {"601": 60}}
    assert put(client, again).json()["saved"] is False  # the same prices: nothing written
    assert put(client, {"base_revision": 0, "sell": {}, "buy": {}}).status_code == 409


@pytest.mark.parametrize("sell", [{"abc": 1}, {"0": 5}, {"07": 5}, {"12": -1}, {"12": 1.5},
                                  {"12": True}, {"100000": 1}])  # fmt: skip
def test_a_bad_price_or_id_is_refused(client: TestClient, sell: dict[str, Any]) -> None:
    r = put(client, {"base_revision": 0, "sell": sell, "buy": {}})
    assert r.status_code in (400, 422)


def test_only_a_person_s_browser_writes(client: TestClient, tmp_path: Path) -> None:
    assert (
        put(client, {"base_revision": 0, "sell": {"1": 1}, "buy": {}}, csrf=False).status_code
        == 403
    )
    assert not (tmp_path / "settings" / ep.FILE_NAME).exists()


def test_the_pure_store() -> None:
    s = ep.Store(3, {"501": 25}, {})
    assert ep.parse(ep.dumps(s)) == s
    assert ep.parse("[]") == "not version 1"
    assert isinstance(ep.parse('{"version": 1, "revision": -1}'), str)
    assert ep.side_problem({str(i): 1 for i in range(1, ep.MAX_ENTRIES + 2)}, "sell")
