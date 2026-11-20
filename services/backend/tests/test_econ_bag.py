"""scripts/econ_bag.py: one Run's /economy entry from two bag censuses (econ-bag-count.md)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import econ_bag as eb  # noqa: E402

TABLE = {
    "601": {"name": "wing A", "type": "Delayconsume", "sell": 30, "sell_oc10": 37, "npc_buy": 60,
            "npc_buy_dc10": 45, "weight": 5},
    "504": {"name": "potion A", "type": "Healing", "sell": 600, "sell_oc10": 744,
            "npc_buy": 1200, "npc_buy_dc10": 912, "weight": 15},
    "911": {"name": "etc A", "type": "Etc", "sell": 80, "sell_oc10": 99, "weight": 10},
    "912": {"name": "etc B", "type": "Etc", "sell": 240, "sell_oc10": 297, "weight": 10},
    "602": {"name": "wing B", "type": "Delayconsume", "sell": 150, "sell_oc10": 186,
            "npc_buy": 300, "npc_buy_dc10": 228, "weight": 5},
    "12324": {"name": "wing C", "type": "Delayconsume", "sell": 0, "sell_oc10": 0,
              "weight": 0},
    "1201": {"name": "thing A", "type": "Thing", "sell": 25, "sell_oc10": 31, "weight": 400},
}  # fmt: skip
EVENTS = [
    {"t_ns": 1_000 * eb.NS, "kind": "run_start", "map": "xmas_dun02", "strategy": "P2",
     "version": "dungeon@8.7"},
    {"t_ns": 1_100 * eb.NS, "kind": "kill"},
    {"t_ns": 1_200 * eb.NS, "kind": "kill"},
    {"t_ns": 1_000 * eb.NS + 1800 * eb.NS, "kind": "run_end"},
]  # fmt: skip


def census(totals: dict[str, int], unread: int = 0, full: list[str] | None = None) -> dict:
    return {"census": {"totals": totals, "unread": unread, "full_tabs": full or []}}


def test_rises_are_income_falls_of_consumables_are_used() -> None:
    a = census({"601": 20, "504": 10, "911": 46, "1201": 1})
    b = census({"601": 17, "504": 4, "911": 58, "912": 5, "1201": 1})
    run = eb.run_from_bags(a, b, EVENTS, TABLE, {})
    assert run["hours"] == 0.5 and run["kills"] == 2
    assert {(r["item_id"], r["income"]) for r in run["items"]} == {(911, 12), (912, 5)}
    assert {(r["item_id"], r["used"]) for r in run["consumables"]} == {(601, 3), (504, 6)}
    t = run["totals"]
    assert t["gross"] == 12 * 80 + 5 * 240
    assert t["cost"] == 3 * 60 + 6 * 1200
    assert t["kills_h"] == 4.0
    assert "stolen = 0" in run["why"]["source"]


def test_a_shared_icon_is_priced_only_when_its_items_agree() -> None:
    a = census({"602|12324": 2})
    b = census({"602|12324": 5})
    run = eb.run_from_bags(a, b, EVENTS, TABLE, {})
    (row,) = run["items"]
    assert row["ids"] == [602, 12324] and row["sell"] is None
    assert "602|12324" in run["why"]["shared_icons_unpriced"]


def test_unread_slots_full_tabs_and_lost_items_are_said() -> None:
    a = census({"1201": 1, "911": 3}, unread=1)
    b = census({"911": 3}, full=["etc"])
    run = eb.run_from_bags(a, b, EVENTS, TABLE, {})
    assert "1 bag slot(s) unread" in run["why"]["unread_slots"]
    assert "etc" in run["why"]["full_tabs"]
    assert "1201" in run["why"]["fell_not_used"] and not run["consumables"]


def test_no_window_is_refused() -> None:
    with pytest.raises(ValueError):
        eb.run_from_bags(census({}), census({}), EVENTS[1:3], TABLE, {})
