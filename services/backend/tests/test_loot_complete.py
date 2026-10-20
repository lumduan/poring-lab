"""loot_complete.py (Batt 2026-10-20: LOOT COMPLETENESS = picked / dropped by OUR kills): the pure
parts. The real-session positive cases are in docs/demonstrations.md 3.89 (Batt's demo 61 / 63,
v44's arms 46.3 / 61.4 %)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import loot_complete as lc  # noqa: E402

S = 10**9


def test_a_re_engaged_target_belongs_to_its_last_engagement() -> None:
    engs = [{"k": 3, "t_first_click": 1 * S, "result": "skipped_risky"},
            {"k": 8, "t_first_click": 5 * S, "result": "dead", "loot": {"s": 2.0}},
            {"k": 9, "t_first_click": 9 * S, "result": "dead", "loot": {"s": 2.0}}]  # fmt: skip
    gid = {3: 77, 8: 77, 9: 77}
    assert lc.owner_of(77, 6 * S, engs, gid)["k"] == 8  # not k 9 (its click came after the kill)
    assert lc.owner_of(77, 2 * S, engs, gid)["k"] == 3
    assert lc.owner_of(78, 6 * S, engs, gid) is None
    assert not lc.looted(engs[0]) and lc.looted(engs[1]) and not lc.looted(None)


def test_completeness_counts_every_kill_and_its_fates() -> None:
    rows = [{"k": 1, "result": "dead", "looted": True, "fates": ["picked", "picked"]},
            {"k": 2, "result": "skipped_risky", "looted": False,
             "fates": ["out_of_sight", "looter"]},
            {"k": None, "result": None, "looted": False, "fates": ["picked"]},
            {"k": 3, "result": "dead", "looted": True, "fates": []}]  # fmt: skip
    s = lc.summary(rows)
    assert s["kills"] == 4 and s["items"] == 5 and s["picked"] == 3
    assert s["completeness"] == 0.6 and s["out_of_sight_share"] == 0.2
    assert s["abandoned_kills"] == 2 and s["abandoned_items"] == 3
    assert lc.column(s) == "3/5 = 60.0 % | left behind 20 % | looters 20 % | expired 0 %"
    a = lc.arms(rows)
    assert a["fix"]["kills"] == 2 and a["base"]["kills"] == 1 and a["no_engagement"]["kills"] == 1


def test_the_null_spans_every_pool_and_split() -> None:
    rows = {f"s{i}": [{"k": k, "result": "dead", "looted": True,
                       "fates": ["picked" if (k + i) % 3 else "out_of_sight"]}
                      for k in range(40)] for i in range(4)}  # fmt: skip
    n = lc.null(rows, [f"s{i}" for i in range(4)])
    assert n["pools"] == 1 and n["n"] == len(lc.SPLITS)
    lo, hi = n["completeness_points"]
    assert lo <= hi and len(n["completeness_all"]) == len(lc.SPLITS)


def test_a_looters_re_drop_of_our_item_is_counted_once() -> None:
    """Step 4 (LOOTER RECOVERY): a looter that took our item drops it again at its death -- the
    same item. Real case: v49 run 1b (20261020T140632, a dense field) had 82 such re-drops among
    its 251 items; net completeness 55.6 % against the gross 37.5 %, 24 looted items recovered."""
    items = {
        1: {"t_fall": 0, "fate": "looter", "item_id": 909, "t_end": 5, "looter_gids": [77]},
        2: {"t_fall": 0, "fate": "out_of_sight", "item_id": 909, "t_end": 9},
        3: {"t_fall": 20, "fate": "picked", "item_id": 909, "t_end": 22},  # 77's re-drop of 1
        4: {"t_fall": 20, "fate": "picked", "item_id": 512, "t_end": 22},  # its own drop
    }
    rows = [
        {"t": 0, "gid": 10, "k": 1, "result": "dead", "looted": True,
         "fates": ["looter", "out_of_sight"], "drops": [1, 2]},
        {"t": 20, "gid": 77, "k": 3, "result": "dead", "looted": True,
         "fates": ["picked", "picked"], "drops": [3, 4]},
    ]  # fmt: skip
    lc.link_redrops(rows, items)
    assert rows[0]["redrops"] == 0 and rows[1]["redrops"] == 1 and rows[1]["redrops_picked"] == 1
    s = lc.summary(rows)
    assert s["items"] == 4 and s["picked"] == 2 and s["completeness"] == 0.5
    assert s["redrops"] == 1 and s["recovered"] == 1 and s["completeness_net"] == round(2 / 3, 4)


def test_kill_to_the_last_pickup_is_batts_ruler() -> None:
    """Batt 18:11 (3.91): his loot time beside ours -- kill -> the LAST pickup of that kill's
    items, over the kills with a pickup. Real case: his demo (20261016T093835) gives p50 1.563 s
    over 39 kills, his 1.56 s (flow_judge.loot_metrics)."""
    items = {
        1: {"t_fall": 0, "fate": "picked", "item_id": 1, "t_end": int(1.2 * S), "cell": (5, 5)},
        2: {"t_fall": 0, "fate": "picked", "item_id": 2, "t_end": int(2.5 * S), "cell": (5, 6)},
        3: {"t_fall": 10 * S, "fate": "looter", "item_id": 3, "t_end": 13 * S, "cell": (9, 9)},
        4: {"t_fall": 20 * S, "fate": "picked", "item_id": 4, "t_end": 21 * S, "cell": (1, 1)},
    }
    rows = lc.kill_rows([(0, 7), (10 * S, 8), (20 * S, 9)], items, lambda g, t: None, [], {},
                        0, 30 * S)  # fmt: skip
    assert [r["last_pick_s"] for r in rows] == [2.5, None, 1.0]
    s = lc.summary(rows)
    assert s["kill_to_last_pickup_n"] == 2 and s["kill_to_last_pickup_p50"] == 2.5
    assert s["kill_to_last_pickup_mean"] == 1.75
