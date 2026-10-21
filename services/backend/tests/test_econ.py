"""ECONOMICS (Batt 2026-10-21): scripts/econ_items.py (the item table's price rules),
scripts/econ_model.py (drop rules, the ratios, trips) and scripts/econ_row.py (the per-run row).
The pure parts are tested on synthetic data; the REAL positive cases use v52 run 1 (a banked
session) and the item table built at run time (GPL-derived data, never committed: skipped when
it is not built on this host)."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import econ_items as ei  # noqa: E402
import econ_model as em  # noqa: E402
import econ_row as er  # noqa: E402

S = 10**9
V52 = "20261021T092850-demo-hunt-flow52"


# --- econ_items: the price rules (pc.cpp, itemdb.cpp, npc.cpp at the pin) ------------------------


def test_overcharge_and_discount_lv10_round_down_per_unit() -> None:
    """pc.cpp:5689-5719: 5 + 2 lv - (lv == 10) = 24 % at lv 10; (int32)(v x 124 / 100.)."""
    assert ei.skill_rate(10) == 24 and ei.skill_rate(9) == 23 and ei.skill_rate(0) == 0
    assert ei.overcharge(600) == 744  # White Potion's sell
    assert ei.overcharge(3) == 3  # 3.72 truncated: Jellopy gains nothing
    assert ei.overcharge(5) == 6 and ei.overcharge(9) == 11  # Clover 6.2, Red Herb 11.16
    assert ei.overcharge(0) == 0  # min_shop_sell 0
    assert ei.discount(1200) == 912 and ei.discount(60) == 45  # 45.6 truncated
    assert ei.discount(1) == 1  # 0.76 -> 0 -> min_shop_buy 1


def test_effective_prices_follow_itemdb() -> None:
    """itemdb.cpp:1185-1193: a missing side from the other, then the exploit guard."""
    assert ei.effective_prices(6, None)[:2] == (6, 3)  # Jellopy: sell = buy / 2
    assert ei.effective_prices(7, None)[:2] == (7, 3)  # integer division
    assert ei.effective_prices(None, 10)[:2] == (20, 10)
    assert ei.effective_prices(100, 80)[:2] == (100, 1)  # 100/124 < 80/75: the guard
    assert ei.effective_prices(None, None)[:2] == (0, 0)


def test_shop_line_discount_flag_and_prices() -> None:
    """npc.cpp:4091-4105 (a plain shop is discountable unless its first entry is no) and
    :4146-4148 (-1 = the item's value_buy)."""
    assert ei.shop_entries("83,1750:-1,501:50") == (True, [(1750, -1), (501, 50)])
    assert ei.shop_entries("83,no,501:-1") == (False, [(501, -1)])
    assert ei.shop_price(-1, 1200) == 1200 and ei.shop_price(50, 1200) == 50
    it = {"aegis": "X", "type": "Healing", "weight_db": 70, "buy_db": 50, "sell_db": None}
    offers = [{"key": "a:1", "map": "m", "x": 1, "y": 1, "listed": -1, "discount": True,
               "floating": False},
              {"key": "b:2", "map": "m", "x": 2, "y": 2, "listed": 40, "discount": False,
               "floating": False}]  # fmt: skip
    row = ei.price_item(it, offers)
    assert row["sell"] == 25 and row["sell_oc10"] == 31 and row["weight"] == 7.0
    assert row["npc_buy"] == 40  # the cheaper shop
    assert row["npc_buy_dc10"] == 38  # 50 x 0.76 at the discountable shop beats 40 plain
    nosell = ei.price_item({**it, "no_sell": True}, [])
    assert nosell["sell"] == 0 and not nosell["sellable"] and nosell["npc_buy"] is None


# --- econ_model: drop rules, the ratios, trips ---------------------------------------------------


def test_effective_rate_is_mob_db_rate_on_the_lab_config() -> None:
    """mob.cpp:6847-6905 + mob_getdroprate 2818-2889 with drops.conf's defaults: identity,
    clamped to [1, 10000]; the classes and multipliers when a config changes them."""
    assert em.effective_rate(7000, "Etc", {}) == 7000
    assert em.effective_rate(1, "Card", {}) == 1
    assert em.effective_rate(10000, "Etc", {}) == 10000
    assert em.effective_rate(3000, "Etc", {"item_rate_common": 200}) == 6000
    assert em.effective_rate(6000, "Etc", {"item_rate_common": 200}) == 10000  # max clamp
    assert em.effective_rate(3000, "Healing", {"item_rate_common": 200}) == 3000  # other class
    assert em.effective_rate(3000, "Healing", {"item_rate_heal": 50}) == 1500
    assert em.effective_rate(3000, "Etc", {"item_rate_common_boss": 300}, boss="boss") == 9000
    assert em.effective_rate(100, "Etc", {"drop_rateincrease": True}) == 101
    assert em.rate_class("DelayConsume") == "common"  # the switch's default (mob.cpp:6888)
    with pytest.raises(ValueError):
        em.effective_rate(100, "Etc", {"drops_by_luk": 1})


def test_kill_stats_and_the_rares_rule() -> None:
    drops = [
        {"p": 0.5, "sell": 10, "sell_oc": 12, "weight": 1.0, "rare": False, "base": 5000},
        {"p": 0.1, "sell": 100, "sell_oc": 124, "weight": 2.0, "rare": False, "base": 1000},
        {"p": 0.0001, "sell": 10, "sell_oc": 12, "weight": 1.0, "rare": True, "base": 1},
    ]
    k = em.kill_stats(drops)
    assert k["ev"] == pytest.approx(15.0) and k["ew"] == pytest.approx(0.7)
    # E[X^2] = Var + E^2, Var = 0.5*0.5*100 + 0.1*0.9*10000 = 25 + 900
    assert k["ev2"] == pytest.approx(925 + 225)
    assert em.kill_stats(drops, key="sell_oc")["ev"] == pytest.approx(18.4)
    assert em.kill_stats(drops, L=0.5)["ev"] == pytest.approx(7.5)
    assert em.is_rare(10, "Etc") and not em.is_rare(11, "Etc")
    assert em.is_rare(5000, "Card") and em.is_rare(5000, "PetEgg")


def test_ratios_by_hand() -> None:
    """V 10, W 2, K 100, L 0.5: G = 500 z/h, 100 weight/h; C 100 -> F 1 h; T 0.1 h -> u = 1/1.1;
    N = u x G = 454.5; payback 10000 / N = 22 h; ROE = N / 10000."""
    r = em.ratios(10.0, 2.0, 1150.0, 100.0, 0.5, 100.0, 0.1, 0.0, 10000.0)
    assert r["G_h"] == 500.0 and r["weight_h"] == 100.0 and r["fill_h"] == 1.0
    assert r["u"] == round(1 / 1.1, 4) and r["net_h"] == round(500 / 1.1, 1)
    assert r["payback_h"] == round(10000 / (500 / 1.1), 1)
    assert r["V_per_W"] == 5.0
    # a trip fee is paid once per cycle of F + T hours
    rf = em.ratios(10.0, 2.0, 1150.0, 100.0, 0.5, 100.0, 0.1, fee=110.0)
    assert rf["net_h"] == round(500 / 1.1 - 110 / 1.1, 1)
    # costs: cost ratio and the Sharpe-like ratio of 10-min windows (n = K / 6 kills)
    rc = em.ratios(10.0, 2.0, 1150.0, 60.0, 1.0, None, None, cost_h=120.0)
    assert rc["cost_ratio"] == 0.2 and rc["net_h"] is None  # no C, T: no trips
    n = 10.0
    assert rc["sharpe_10min"] == round((n * 10 - 20) / math.sqrt(n * 1150.0), 2)


def test_grid_costs_diagonal_rule() -> None:
    """A diagonal step needs both orthogonal cells free (path.cpp); straight 1, diagonal 1.4."""
    xs, ys = 4, 4
    nopass = [False] * 16
    for x in range(4):
        nopass[x + 3 * 4] = True  # the last row and column never pass (MapGrid.nopass)
    for y in range(4):
        nopass[3 + y * 4] = True
    d, lab = em.grid_costs(nopass, xs, ys, {0: (0.0, 7)}, 1.0)
    assert d[1 + 1 * 4] == pytest.approx(1.4) and lab[1 + 1 * 4] == 7
    nopass[1 + 0 * 4] = True  # block (1, 0): the diagonal (0,0) -> (1,1) needs (1,0) and (0,1)
    d2, _ = em.grid_costs(nopass, xs, ys, {0: (0.0, 7)}, 1.0)
    assert d2[1 + 1 * 4] == pytest.approx(2.0)  # down then right
    assert math.isinf(d2[3])


def test_trip_fields_across_a_portal() -> None:
    """Map A (no NPC) has a portal at (0, 0) to map B's (0, 0); B has a shop at (2, 0)."""

    class G:
        def __init__(self, xs: int, ys: int) -> None:
            self.xs, self.ys, self.cells = xs, ys, bytes(xs * ys)

    grids = {"A": G(6, 2), "B": G(10, 2)}
    portals = {"A": [{"x": 0, "y": 0, "span_x": 0, "span_y": 0, "to_map": "B", "to_x": 0,
                      "to_y": 0, "extra_s": 0.0}]}  # fmt: skip
    f = em.trip_fields(grids, portals, {"B": [(6, 0, 3)]}, ["A", "B"], step_s=1.0, change_s=2.0)
    # B: from (0, 0) to within 3 cells of (6, 0) = 3 steps; A's (4, 0): 4 steps + 2 + 3
    assert f["B"][0][0] == 3.0 and f["A"][0][4] == 9.0 and f["A"][1][4] == 3
    s = em.trip_summary(f["A"], [{"label": 0}, {}, {}, {"map": "B", "x": 6, "y": 0}], sell_s=20.0)
    assert s["goal"] == {"map": "B", "x": 6, "y": 0} and s["goal_share"] == 1.0
    assert s["T_s"] == round(2 * s["one_way_mean_s"] + 20.0, 1)
    assert em.route_maps(portals, "A", ["B"], ["A", "B"]) == ["A", "B"]
    assert em.route_maps(portals, "B", ["A"], ["A", "B"]) == []  # no way back from B


# --- econ_row: the per-run row --------------------------------------------------------------------


def test_split_carry_own_drops_then_looted() -> None:
    """mob.cpp:2556-2571: own drops in drop-list order, then what a looter carried."""
    order = [909, 1202, 938, 512, 713, 512, 619, 4001]  # Poring's list (mob_db order)
    assert er.split_carry([909, 512], order) == 2
    assert er.split_carry([909, 909], order) == 1  # one list entry drops once: 2nd is carried
    assert er.split_carry([512, 909], order) == 1  # out of order: the Jellopy was carried
    assert er.split_carry([705], order) == 0  # a Lunatic's Clover from a Poring
    assert er.split_carry([512, 512], order) == 2  # two Apple entries
    assert er.split_carry([], order) == 0
    # a looter takes a whole stack: an amount > 1 is never a monster's own drop (one unit each)
    assert er.split_carry([909], order, [40]) == 0
    assert er.split_carry([909, 512], order, [1, 3]) == 1


def test_windows_and_sharpe() -> None:
    t0 = 0
    w1 = int(1500 * S)  # 2 full 10-min windows; the partial third is dropped
    booked = [(int(10 * S), 100.0), (int(700 * S), 50.0), (int(800 * S), -20.0),
              (int(1300 * S), 999.0)]  # fmt: skip
    w = er.windows(t0, w1, booked)
    assert w == [600.0, 180.0]
    m, sd, sh, why = er.sharpe(w)
    assert m == 390.0 and sd == pytest.approx(math.sqrt(2 * 210.0**2)) and why is None
    assert sh == pytest.approx(390.0 / sd)
    assert er.sharpe([5.0])[2] is None and er.sharpe([5.0])[3]


def test_measure_synthetic_run() -> None:
    """Two kills, three drops (one picked, one left, one carried), a potion, a death."""
    table = {"909": {"sell": 3, "sell_oc10": 3, "weight": 1.0, "type": "Etc"},
             "512": {"sell": 7, "sell_oc10": 8, "weight": 2.0, "type": "Etc"},
             "504": {"sell": 600, "sell_oc10": 744, "weight": 15.0, "type": "Healing",
                     "npc_buy": 1200, "npc_buy_dc10": 912}}  # fmt: skip
    pk = [
        {"type": "entity_appear", "objtype": 5, "gid": 1, "job": 1002, "t_mono_ns": 0},
        {"type": "entity_appear", "objtype": 5, "gid": 2, "job": 1002, "t_mono_ns": 0},
        {"type": "stat_change", "name": "max_weight", "value": 49700, "t_mono_ns": 0},
        {"type": "stat_change", "name": "weight", "value": 6630, "t_mono_ns": 0},
        {
            "type": "floor_item_appear",
            "kind": "fall",
            "floor_id": 11,
            "amount": 1,
            "t_mono_ns": int(60 * S),
        },
        {
            "type": "floor_item_appear",
            "kind": "fall",
            "floor_id": 12,
            "amount": 1,
            "t_mono_ns": int(60 * S),
        },
        {
            "type": "floor_item_appear",
            "kind": "fall",
            "floor_id": 13,
            "amount": 1,
            "t_mono_ns": int(120 * S),
        },
        {
            "type": "use_item_result",
            "aid": er.AID,
            "item_id": 504,
            "ok": True,
            "t_mono_ns": int(300 * S),
        },
        {
            "type": "use_item_result",
            "aid": 99,
            "item_id": 504,
            "ok": True,
            "t_mono_ns": int(301 * S),
        },  # someone else's: not ours
        {"type": "entity_vanish", "gid": er.AID, "reason": 1, "t_mono_ns": int(900 * S)},
    ]
    items = {
        11: {"item_id": 909, "fate": "picked", "t_end": int(61 * S)},
        12: {"item_id": 909, "fate": "out_of_sight", "t_end": int(200 * S)},
        13: {"item_id": 512, "fate": "picked", "t_end": int(121 * S)},
    }
    rows = [{"t": int(60 * S), "gid": 1, "drops": [11, 12]},
            {"t": int(120 * S), "gid": 2, "drops": [13]}]  # fmt: skip
    order = {"1002": [909, 1202, 938, 512, 713, 512, 619, 4001]}
    r = er.measure(pk, 0, int(1200 * S), rows, items, table, drop_order=order)
    assert r["kills"] == 2 and r["K"] == 6.0 and r["kill_mix"] == {"1002": 2}
    assert r["dropped_value"] == 13.0 and r["picked_value"] == 10.0 and r["V"] == 5.0
    assert r["L_value"] == round(10 / 13, 4) and r["L_count"] == round(2 / 3, 4)
    assert r["carry_items"] == 1 and r["carry_value"] == 3.0  # kill 1's 2nd Jellopy
    assert r["picked_weight"] == 3.0 and r["W"] == 1.5 and r["V_per_W"] == round(10 / 3, 2)
    assert r["consumables"] == {"potion": 1} and r["cost"] == 1200.0 and r["cost_dc"] == 912.0
    assert r["deaths"] == 1 and r["deaths_h"] == 3.0
    assert r["gross_h"] == 30.0 and r["cost_h"] == 3600.0 and r["net_h"] == -3570.0
    assert r["cost_ratio"] == 120.0
    assert r["win_z_h"] == [round((10 - 1200) * 6, 1), 0.0]
    assert r["max_weight"] == 4970.0 and r["weight0"] == 663.0
    assert r["fill_h_50"] == round((2485 - 663) / (6.0 * 1.5), 3)


# --- REAL positive cases (v52 run 1; the item table built at run time) ----------------------------


def _built() -> bool:
    return ei.OUT.exists() and (er.DEMO / V52 / "packets.jsonl.gz").exists()


@pytest.mark.skipif(not _built(), reason="the item table or the v52 session is not on this host")
def test_real_run_v52_hand_checked_kill_and_totals() -> None:
    """v52 run 1 (a REAL session, hand-checked 2026-10-21): the Lunatic (1063) killed at
    +190.48 s (gid 110054259) dropped Clover (705, floor 15022) and Red Herb (507, floor 15023),
    both picked. Clover: Buy 10 -> sell 5, OC 6, weight 1; Red Herb: Buy 18 -> sell 9, OC 11,
    weight 3 (db/pre-re/item_db_etc.yml:172-177, item_db_usable.yml:144-149). So that kill is
    worth 14 z picked (17 with OC) and 4 weight. The run: 102 kills in 1.0005 h (flow_judge's
    102.0 / h), 127 drops worth 658 z, 104 picked worth 546 z (183 weight)."""
    import loot_complete as lc
    import search_study as ss

    tab = er._table()
    assert (tab["705"]["sell"], tab["705"]["sell_oc10"], tab["705"]["weight"]) == (5, 6, 1.0)
    assert (tab["507"]["sell"], tab["507"]["sell_oc10"], tab["507"]["weight"]) == (9, 11, 3.0)
    sess = ss.load_session(V52)
    rows, items = lc.session_rows_items(V52, sess)
    k = next(r for r in rows if r["gid"] == 110054259 and abs((r["t"] - sess.t0) / S - 190.48)
             < 0.05)  # fmt: skip
    assert sorted(k["drops"]) == [15022, 15023]
    assert [items[f]["item_id"] for f in sorted(k["drops"])] == [705, 507]
    assert all(items[f]["fate"] == "picked" for f in k["drops"])
    one = er.measure(sess.events, sess.t0, sess.w1, [k], items, tab)
    assert one["picked_value"] == 14.0 and one["picked_value_oc"] == 17.0
    assert one["picked_weight"] == 4.0 and one["kill_mix"] == {"1063": 1}
    r = er.row(V52, sess=sess, rows_items=(rows, items))
    assert r["kills"] == 102 and r["K"] == 102.0
    assert r["dropped_items"] == 127 and r["dropped_value"] == 658.0
    assert r["picked_items"] == 104 and r["picked_value"] == 546.0
    assert r["picked_weight"] == 183.0 and r["V"] == 5.35 and r["L_value"] == 0.8298
    assert r["consumables"] == {} and r["deaths"] == 0
    assert r["max_weight"] == 4970.0 and r["weight0"] == 663.0  # STR 99 Novice: 20000 + 99 x 300


@pytest.mark.skipif(not _built(), reason="the item table or the v52 session is not on this host")
def test_real_weights_match_the_servers_weight_packets() -> None:
    """POSITIVE CASE for the table's weights: in v52 run 1 every one of our 104 successful
    pickups moved the server's weight stat by exactly the table's weight_db x amount."""
    tab = er._table()
    pk = er._packets(V52)
    w = pend = None
    ok = bad = 0
    for e in pk:
        if e.get("type") == "pickup_result" and e.get("ok"):
            pend = e
        elif e.get("type") == "stat_change" and e.get("name") == "weight":
            if pend is not None and w is not None:
                exp = int(tab[str(pend["item_id"])]["weight_db"]) * int(pend["amount"])
                ok += e["value"] - w == exp
                bad += e["value"] - w != exp
            pend, w = None, e["value"]
    assert ok == 104 and bad == 0


def test_measure_counts_redrops_from_the_end() -> None:
    """A looter's re-drop of our own item is carried, and the looted list comes LAST
    (mob.cpp:2556-2571): link_redrops may name the own copy of the same item id, so the split
    counts the links and cuts that many from the end."""
    table = {"909": {"sell": 3, "sell_oc10": 3, "weight": 1.0, "type": "Etc"}}
    pk = [{"type": "entity_appear", "objtype": 5, "gid": 1, "job": 1002, "t_mono_ns": 0}]
    pk += [{"type": "floor_item_appear", "kind": "fall", "floor_id": f, "amount": 1,
            "t_mono_ns": int(60 * S)} for f in (21, 22)]  # fmt: skip
    items = {21: {"item_id": 909, "fate": "picked", "t_end": int(61 * S)},
             22: {"item_id": 909, "fate": "picked", "t_end": int(62 * S)}}  # fmt: skip
    rows = [{"t": int(60 * S), "gid": 1, "drops": [21, 22], "redrop_fids": [21]}]
    order = {"1002": [909, 1202, 938, 512, 713, 512, 619, 4001]}
    r = er.measure(pk, 0, int(600 * S), rows, items, table, drop_order=order)
    assert r["carry_items"] == 1 and r["own_items_by_species"] == {"1002": {"909": 1}}
