"""THE ECONOMY DASHBOARD's export (scripts/econ_dash.py, Batt 2026-11-11): the counts per item,
species and consumable, the hours, the totals and their cross-check against dungeon_judge and
econ_row. Synthetic sessions use SYNTHETIC ids and prices (9xxxx; the price rules applied with
econ_items' own functions); the REAL positive cases (xmas02 p57 + p58, a survival trial with
potions) read the banked sessions and the run-time item table, and are skipped when absent."""

from __future__ import annotations

import gzip
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import dungeon_judge as dj  # noqa: E402
import econ_dash as ed  # noqa: E402
import econ_items as ei  # noqa: E402

S = 10**9
A = dj.AID
LOOT_A, LOOT_B, UNPRICED = 90001, 90002, 90200  # synthetic item ids
POTION_X, NO_SHOP = 90100, 90300  # synthetic consumables (a db type Healing; one no NPC sells)
MOB_X, MOB_Y = 91001, 91002  # synthetic species


def _row(
    sell: int, typ: str = "Etc", weight: float = 1.0, buy: int | None = None
) -> dict[str, Any]:
    """A synthetic item-table row, its derived prices by econ_items' own rules."""
    return {
        "name": None,
        "type": typ,
        "weight": weight,
        "sellable": True,
        "sell": sell,
        "sell_oc10": ei.overcharge(sell),
        "npc_buy": buy,
        "npc_buy_dc10": None if buy is None else ei.discount(buy),
    }


TABLE = {
    str(LOOT_A): _row(40, weight=2.0),
    str(LOOT_B): _row(7),
    str(POTION_X): _row(25, "Healing", 7.0, buy=50),
    str(NO_SHOP): _row(1, "Usable"),
}
NAMES = {str(LOOT_A): "loot-a", str(POTION_X): "potion-x"}  # synthetic display names
MOBS = {str(MOB_X): "mob-x"}


def pk(t: float, **kw: Any) -> dict[str, Any]:
    return {"t_mono_ns": int(t * S), **kw}


def ev(t: float, kind: str, **kw: Any) -> dict[str, Any]:
    return {"t_ns": int(t * S), "kind": kind, **kw}


def a_session(t0: float = 100.0) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """A 30-minute Rogue run: 4 kills (3 MOB_X, 1 MOB_Y), each dropping one item; 3 of the 4
    drops picked; 2 Snatcher gains (one of an item the table lacks); one unexplained gain (not
    income); 2 of our potions, one of somebody else's, one item no NPC sells, one use after the
    run's end."""
    events = [
        ev(t0, "run_start", strategy="P2", seed=1, version="t", map="testmap", char="rogue"),
        ev(t0 + 1800, "run_end", reason="time_box", counts={}),
    ]
    packets: list[dict[str, Any]] = []
    plan = [
        (MOB_X, LOOT_A, True, None),
        (MOB_X, LOOT_A, False, None),
        (MOB_X, LOOT_B, True, LOOT_A),
        (MOB_Y, LOOT_B, True, UNPRICED),
    ]
    for k, (mob, item, picked, snatch) in enumerate(plan):
        t, g, f = t0 + 60 + 300 * k, 1000 + k, 5000 + k
        packets += [
            pk(t - 10, type="entity_appear", gid=g, objtype=5, x=10, y=10, job=mob),
            pk(
                t - 0.5,
                type="attack_request",
                target_gid=g,
                action=7,
                kind="repeat",
                is_attack=True,
            ),
            pk(t, type="act", src_gid=A, target_gid=g, damage=300, kind="normal", action=0),
            pk(
                t + 0.2,
                type="floor_item_appear",
                kind="fall",
                floor_id=f,
                item_id=item,
                x=10,
                y=10,
                amount=1,
                identified=True,
                sub_x=0,
                sub_y=0,
            ),
            pk(t + 0.5, type="entity_vanish", gid=g, reason=1),
        ]
        if snatch is not None:  # Snatcher: a gain inside our own attack, no pickup request
            packets.append(pk(t + 0.3, type="pickup_result", ok=True, item_id=snatch, amount=1))
        if picked:
            packets += [
                pk(t + 2, type="pickup_request", floor_id=f),
                pk(t + 2.1, type="pickup_result", ok=True, item_id=item, amount=1),
                pk(t + 2.1, type="floor_item_vanish", floor_id=f),
            ]
    packets.append(pk(t0 + 1500, type="pickup_result", ok=True, item_id=LOOT_B, amount=1))
    for t in (t0 + 400, t0 + 700):
        packets.append(pk(t, type="use_item_result", item_id=POTION_X, aid=A, ok=True))
    packets.append(pk(t0 + 401, type="use_item_result", item_id=POTION_X, aid=123, ok=True))
    packets.append(pk(t0 + 800, type="use_item_result", item_id=NO_SHOP, aid=A, ok=True))
    packets.append(pk(t0 + 1801, type="use_item_result", item_id=POTION_X, aid=A, ok=True))
    return events, sorted(packets, key=lambda e: e["t_mono_ns"])


def write_session(
    root: Path, sid: str, events: list[dict[str, Any]], packets: list[dict[str, Any]]
) -> Path:
    d = root / sid
    d.mkdir(parents=True)
    (d / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    with gzip.open(d / "packets.jsonl.gz", "wt") as fh:
        fh.writelines(json.dumps(p) + "\n" for p in packets)
    (d / "manifest.json").write_text(json.dumps({"map": "testmap", "char": "rogue"}))
    return d


# --- the pure parts ------------------------------------------------------------------------------


def test_export_names_are_a_fixed_character_set() -> None:
    for ok in ("p57-p58", "xmas02.p57_p58", "A", "a" * 64):
        assert ed.valid_name(ok), ok
    for bad in ("", ".hidden", "../x", "a/b", "a\\b", "a b", "a" * 65, "-x", "x\n", "ไทย"):
        assert not ed.valid_name(bad), bad


def test_drops_by_item_counts_units_and_our_pickups_of_them() -> None:
    rows = [{"drops": [1, 2]}, {"drops": [3]}]
    fates = {
        1: {"item_id": LOOT_A, "fate": "picked"},
        2: {"item_id": LOOT_B, "fate": "left"},
        3: {"item_id": LOOT_A, "fate": "looter"},
    }
    got = ed.drops_by_item(rows, fates, {1: 1, 2: 3, 3: 1})
    assert got == {LOOT_A: {"dropped": 2, "picked": 1}, LOOT_B: {"dropped": 3, "picked": 0}}


def test_item_rows_income_is_picked_plus_stolen_and_unpriced_is_named() -> None:
    gains = [
        {"item_id": LOOT_A, "picked": 1, "stolen": 1, "snatched": 2, "other": 3, "staged": 4},
        {"item_id": UNPRICED, "picked": 0, "stolen": 0, "snatched": 1, "other": 0, "staged": 0},
    ]
    rows, unpriced = ed.item_rows(gains, {LOOT_B: {"dropped": 5, "picked": 0}}, TABLE, NAMES)
    assert unpriced == [UNPRICED]
    a, u, b = rows  # ordered by income units, then dropped, then id: never by a name
    assert (a["item_id"], a["income"], a["stolen"], a["stolen_steal"], a["stolen_snatcher"]) == (
        LOOT_A,
        4,
        3,
        1,
        2,
    )
    assert (a["other"], a["staged"], a["name"], a["sell"], a["sell_oc"]) == (
        3,
        4,
        "loot-a",
        40,
        ei.overcharge(40),
    )
    assert (u["item_id"], u["sell"], u["sell_oc"], u["name"]) == (UNPRICED, None, None, None)
    assert (b["item_id"], b["income"], b["dropped"]) == (LOOT_B, 0, 5)  # dropped, never gained


def test_consumable_rows_carry_both_prices_and_name_what_no_npc_sells() -> None:
    import econ_row as er

    rows, no_price = ed.consumable_rows([POTION_X, er.FLY, POTION_X, NO_SHOP], TABLE, NAMES)
    assert no_price == sorted([NO_SHOP, er.FLY])  # FLY is not in this synthetic table
    p = rows[0]
    assert (p["item_id"], p["used"], p["kind"], p["npc_buy"], p["npc_buy_dc"]) == (
        POTION_X,
        2,
        "potion",
        50,
        ei.discount(50),
    )
    assert {r["item_id"]: r["kind"] for r in rows}[er.FLY] == "fly_wing"  # by id, not by a name
    assert {r["item_id"]: r["npc_buy"] for r in rows}[NO_SHOP] is None


def test_totals_by_hand() -> None:
    run = {
        "hours": 0.5,
        "kills": 4,
        "items": [
            {"income": 2, "picked": 1, "stolen": 1, "sell": 40, "sell_oc": 49},
            {"income": 1, "picked": 0, "stolen": 1, "sell": None, "sell_oc": None},
        ],
        "consumables": [
            {"used": 2, "npc_buy": 50, "npc_buy_dc": 38},
            {"used": 1, "npc_buy": None, "npc_buy_dc": None},
        ],
    }
    t = ed.totals(run)
    assert (t["gross"], t["gross_oc"], t["cost"], t["cost_dc"]) == (80, 98, 100, 76)
    assert (t["gross_h"], t["gross_oc_h"], t["cost_h"], t["cost_dc_h"]) == (160, 196, 200, 152)
    assert (t["net_h"], t["net_best_h"], t["kills_h"]) == (-40, 44, 8.0)
    assert (t["income_units"], t["picked_units"], t["stolen_units"]) == (3, 1, 2)
    assert ed.totals({**run, "hours": 0})["gross_h"] is None  # never a division by zero


# --- a whole synthetic session, through dungeon_judge, from its DIRECTORY -------------------------


def test_a_session_directory_exports_every_count_and_agrees_with_the_judges(tmp_path: Path) -> None:
    d = write_session(tmp_path / "archive", "20261111T000000-synthetic", *a_session())
    r = ed.export_run(str(d), TABLE, NAMES, MOBS)
    assert r["session"] == "20261111T000000-synthetic" and r["dir"] == str(d)
    assert r["hours"] == 0.5 and r["window"]["source"] == "events run_start..run_end"
    assert (r["kills"], r["deaths"], r["char"], r["map"]) == (4, 0, "rogue", "testmap")
    got = {
        it["item_id"]: (
            it["picked"],
            it["stolen_snatcher"],
            it["income"],
            it["other"],
            it["dropped"],
            it["picked_of_dropped"],
        )
        for it in r["items"]
    }
    assert got == {
        LOOT_A: (1, 1, 2, 0, 2, 1),
        LOOT_B: (2, 0, 2, 1, 2, 2),
        UNPRICED: (0, 1, 1, 0, 0, 0),
    }
    assert [(s["mob_id"], s["name"], s["kills"]) for s in r["species"]] == [
        (MOB_X, "mob-x", 3),
        (MOB_Y, None, 1),
    ]
    cons = {c["item_id"]: (c["used"], c["npc_buy"], c["npc_buy_dc"]) for c in r["consumables"]}
    assert cons == {POTION_X: (2, 50, ei.discount(50)), NO_SHOP: (1, None, None)}
    t = r["totals"]  # 2 x 40 + 2 x 7 = 94 (the unpriced and the "other" gain are out)
    assert (t["gross"], t["gross_oc"]) == (94, 2 * ei.overcharge(40) + 2 * ei.overcharge(7))
    assert (t["cost"], t["cost_dc"]) == (100, 2 * ei.discount(50))
    assert t["net_h"] == round((94 - 100) / 0.5, 1) and t["kills_h"] == 8.0
    assert ed.check(r) == []  # == dungeon_judge's item value and econ_row's costs
    assert "unpriced_items" in r["why"] and "consumables_no_price" in r["why"]
    assert r["econ_row"]["picked_value"] == 40 + 7 + 7  # our kills' picked drops only


def test_a_disagreement_with_the_judges_is_reported() -> None:
    run = {
        "totals": {"gross": 10, "gross_oc": 12, "cost": 5, "cost_dc": 4},
        "judge_value": {"value": 11, "value_oc": 12},
        "econ_row": {"cost": 5.0, "cost_dc": 4.0, "picked_value": 3.0},
        "items": [{"picked_of_dropped": 1, "sell": 3}],
    }
    bad = ed.check(run)
    assert len(bad) == 1 and bad[0].startswith("gross")


def test_pooled_sums_counts_per_id_and_the_hours(tmp_path: Path) -> None:
    d1 = write_session(tmp_path, "20261111T000000-s1", *a_session())
    d2 = write_session(tmp_path, "20261111T010000-s2", *a_session(5000.0))
    runs = [ed.export_run(str(d), TABLE, NAMES, MOBS) for d in (d1, d2)]
    p = ed.pool_runs(runs)
    assert p["runs"] == 2 and p["hours"] == 1.0 and p["kills"] == 8
    assert {it["item_id"]: it["income"] for it in p["items"]} == {LOOT_A: 4, LOOT_B: 4, UNPRICED: 2}
    assert {s["mob_id"]: s["kills"] for s in p["species"]} == {MOB_X: 6, MOB_Y: 2}
    assert {c["item_id"]: c["used"] for c in p["consumables"]} == {POTION_X: 4, NO_SHOP: 2}
    assert p["totals"]["gross"] == 2 * runs[0]["totals"]["gross"]
    assert p["totals"]["gross_h"] == runs[0]["totals"]["gross_h"]  # same rate, twice the hours
    assert set(p["why"]["unpriced_items"]) == {"20261111T000000-s1", "20261111T010000-s2"}


def test_write_reads_back_and_the_listing_skips_foreign_names(tmp_path: Path) -> None:
    d = write_session(tmp_path / "s", "20261111T000000-synthetic", *a_session())
    run = ed.export_run(str(d), TABLE, NAMES, MOBS)
    doc = {"schema": ed.SCHEMA, "name": "t1", "runs": [run], "pooled": ed.pool_runs([run])}
    out = tmp_path / "dash"
    path = ed.write(doc, out)
    assert path == out / "t1.json" and json.loads(path.read_text())["runs"][0]["kills"] == 4
    (out / ".hidden.json").write_text("{}")
    (out / "bad name.json").write_text("{}")
    assert [x["name"] for x in ed.listing(out)] == ["t1"]
    with pytest.raises(ValueError):
        ed.write({**doc, "name": "../escape"}, out)
    assert ed.listing(tmp_path / "missing") == []


# --- REAL positive cases (read at test time; skipped when absent) --------------------------------

ARCHIVE = Path("/mnt/poring-lab-datasets/scratch-archive/2026-11-11/demo-sessions")
P57 = ARCHIVE / "20261111T082037-demo-dungeon-rogue-xmas_dun02-patrol-P2-xmas02-p57"
P58 = ARCHIVE / "20261111T084908-demo-dungeon-rogue-xmas_dun02-patrol-P2-xmas02-p58"


def _table() -> dict[str, Any] | None:
    env = os.environ.get("PORING_LAB_ECON_ITEMS")  # a worktree: the main checkout's table
    return dj.load_table(Path(env) if env else ei.OUT)


def _raw_gains(d: Path, t0: int, t1: int) -> int:
    """Independently of the judges: the units of every successful inventory gain in [t0, t1]."""
    with gzip.open(d / "packets.jsonl.gz", "rt") as fh:
        pkts = [json.loads(x) for x in fh]
    return sum(
        int(e.get("amount") or 1)
        for e in pkts
        if e.get("type") == "pickup_result" and e.get("ok") and t0 <= int(e["t_mono_ns"]) <= t1
    )


@pytest.mark.skipif(
    not (P57 / "packets.jsonl.gz").exists()
    or not (P58 / "packets.jsonl.gz").exists()
    or _table() is None,
    reason="the xmas02 p57 / p58 archive or the item table is not here",
)
def test_real_xmas02_p57_p58_hand_checked() -> None:
    """Hand-checked 2026-11-11 against the RAW packets (no judge code): p57 run_start..run_end
    25.002 min, 35 kills (a died vanish <= 1.5 s after our damaging act), 29 inventory gains =
    11 after our pickup request + 18 within 1 s of our attack act (Snatcher); p58 25.035 min, 65
    kills, 57 gains = 20 + 37; no item use of ours in either window (p57's one Fly Wing came
    0.37 s after its run_end). The zeny: the units x the db's Sell (Buy / 2) and x 1.24 truncated,
    summed by hand per item."""
    table = _table()
    assert table is not None
    runs = [ed.export_run(str(d), table, {}, {}) for d in (P57, P58)]
    want = [(35, 29, 11, 18, 14138, 17523), (65, 57, 20, 37, 24294, 30111)]
    for r, (k, inc, pick, stol, g, goc), d in zip(runs, want, (P57, P58), strict=True):
        t = r["totals"]
        assert (r["kills"], t["income_units"], t["picked_units"], t["stolen_units"]) == (
            k,
            inc,
            pick,
            stol,
        )
        assert (t["gross"], t["gross_oc"], t["cost"], t["cost_dc"]) == (g, goc, 0, 0)
        assert r["consumables"] == [] and r["deaths"] == 0
        assert sum(s["kills"] for s in r["species"]) == k
        assert all(it["stolen_steal"] == 0 for it in r["items"])  # Steal was off: all Snatcher
        assert inc == _raw_gains(d, r["window"]["t0_ns"], r["window"]["t1_ns"])
        assert ed.check(r) == []
    assert round(runs[0]["minutes"], 3) == 25.002 and round(runs[1]["minutes"], 3) == 25.035
    assert runs[1]["totals"]["kills_h"] == 155.78  # rogue-xmas02.md 4BS: E1 155.8 / h
    p = ed.pool_runs(runs)
    assert p["kills"] == 100 and p["totals"]["gross"] == 14138 + 24294


SURVIVAL_POTIONS = dj.SURVIVAL["potions"]  # 3.96's trial: 26 potions (survive_judge S2)


@pytest.mark.skipif(
    not dj.present(SURVIVAL_POTIONS) or _table() is None,
    reason="the survival trial or the item table is not here",
)
def test_real_consumables_from_a_survival_trial() -> None:
    """The consumable path on a REAL session with item uses: the potions per item id equal the
    judge's count (26, dungeon_judge's positive case vs survive_judge S2), and the cost equals
    econ_row.measure's."""
    table = _table()
    assert table is not None
    r = ed.export_run(SURVIVAL_POTIONS, table, {}, {}, map_name="prt_fild08")
    used = {c["item_id"]: c["used"] for c in r["consumables"]}
    assert used.get(dj.POTION) == 26
    assert r["totals"]["cost"] == r["econ_row"]["cost"] and ed.check(r) == []


def test_run_clock_gives_wall_start_end_and_the_flow() -> None:
    """Batt 2026-11-11: each run's start / end on the wall clock and the flow the bot ran."""
    ev = [{"kind": "run_start", "t_ns": 1_000_000_000_000, "strategy": "P2", "search": "patrol"}]
    w = {"t0": 1_000_000_000_000 + 12_500_000_000, "t1": 1_000_000_000_000 + 1_512_500_000_000}
    man = {"version": "dungeon@8.7", "fixes": {"walk_pick": [1], "bare_steal": [8.0]}}
    got = ed.run_clock("20261111T132028-demo-dungeon-rogue-m1-patrol-P2-xmas02-p63", ev, w, man)
    assert got["started"] == "2026-11-11 13:20:40" and got["ended"] == "2026-11-11 13:45:40"
    assert got["flow"] == {"runner": "dungeon@8.7", "strategy": "P2", "search": "patrol",
                           "label": "xmas02-p63", "flags": ["bare_steal", "walk_pick"]}  # fmt: skip
    none = ed.run_clock("not-a-session", [], w, {})
    assert none["started"] is None and none["ended"] is None


def test_candies_eaten_cost_the_npc_sale_they_forgo() -> None:
    """dungeon@9.31 (--heal-candy): Candy (529) and Candy Cane (530) have no NPC shop; a run eats
    looted ones, so each costs its NPC sale (no Discount on a sale). Other no-shop items stay
    unpriced."""
    table = {**TABLE, "530": _row(10, "Healing", 4.0), "529": _row(5, "Healing", 3.0)}
    rows, no_price = ed.consumable_rows([530, 530, 529, NO_SHOP], table, NAMES)
    got = {r["item_id"]: (r["used"], r["npc_buy"], r["npc_buy_dc"], r["price_basis"]) for r in rows}
    assert got[530] == (2, 10, 10, "forgone_sale")
    assert got[529] == (1, 5, 5, "forgone_sale")
    assert got[NO_SHOP] == (1, None, None, None)
    assert no_price == [NO_SHOP]
    assert sorted(ed.FORGONE_SALE_IDS) == [529, 530]
    potion = ed.consumable_rows([POTION_X], TABLE, NAMES)[0][0]
    assert potion["price_basis"] == "npc_buy"
