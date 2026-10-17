from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import arm_judge as aj  # noqa: E402

S = aj.NS


def _mob_at(pos, g, t):  # noqa: ANN001, ANN202 -- the flow_judge.mob_at shape
    last = None
    for tm, c, _j in pos.get(g, ()):
        if tm > t:
            break
        last = c
    return last


def test_item_fates_tell_picked_looted_gone_and_expired_apart() -> None:
    ev = [
        {"t_mono_ns": 1 * S, "type": "entity_appear", "objtype": 5, "gid": 7},
        {"t_mono_ns": 2 * S, "type": "floor_item_appear", "kind": "fall", "floor_id": 1, "x": 10,
         "y": 10},
        {"t_mono_ns": 2 * S, "type": "floor_item_appear", "kind": "fall", "floor_id": 2, "x": 11,
         "y": 10},
        {"t_mono_ns": 2 * S, "type": "floor_item_appear", "kind": "fall", "floor_id": 3, "x": 30,
         "y": 30},
        {"t_mono_ns": 2 * S, "type": "floor_item_appear", "kind": "fall", "floor_id": 4, "x": 40,
         "y": 40},
        {"t_mono_ns": 3 * S, "type": "pickup_request", "floor_id": 1},
        {"t_mono_ns": 3 * S + 1, "type": "pickup_result", "ok": True},
        {"t_mono_ns": 3 * S + 2, "type": "floor_item_vanish", "floor_id": 1},
        {"t_mono_ns": 4 * S, "type": "floor_item_vanish", "floor_id": 2},  # mob 7 stands on it
        {"t_mono_ns": 4 * S, "type": "floor_item_vanish", "floor_id": 3},  # nobody near
        {"t_mono_ns": 70 * S, "type": "floor_item_vanish", "floor_id": 4},  # timed out
    ]  # fmt: skip
    pos = {7: [(1 * S, (11, 11), 1002)]}
    fates = {f: it["fate"] for f, it in aj.item_fates(ev, pos, _mob_at).items()}
    assert fates == {1: "picked", 2: "looter", 3: "gone", 4: "expired"}


def test_kills_and_their_drops() -> None:
    ev = [
        {"t_mono_ns": 5 * S, "type": "act", "src_gid": 2000002, "target_gid": 9, "damage": 180},
        {"t_mono_ns": 5 * S + S // 2, "type": "entity_vanish", "gid": 9, "reason": 1},
        {"t_mono_ns": 9 * S, "type": "entity_vanish", "gid": 8, "reason": 1},  # not our hit
    ]
    assert aj.kills_of(ev) == [(5 * S + S // 2, 9)]
    items = {1: {"t_fall": 5 * S + S // 4, "cell": (10, 10)},
             2: {"t_fall": 5 * S, "cell": (30, 30)},
             3: {"t_fall": 20 * S, "cell": (10, 10)}}  # fmt: skip
    assert aj.drops_of_kill(items, 5 * S + S // 2, (10, 11)) == [1]


SESSION = "20261017T181141-demo-hunt-flow29"


@pytest.mark.skipif(not (aj.DEMO / SESSION / "flow_judge.json").exists(),
                    reason="the real session is local only")  # fmt: skip
def test_strike_table_on_the_real_v29_run() -> None:
    t = aj.strike_table([aj.load(SESSION)])
    assert t["planned"] == {"A": 45, "B": 46, "C": 47}
    a = t["arms"]["A"]
    assert a["n"] == 77 and a["arrive_req_p50_p90"] == [1.41, 1.97]
    assert a["first_click"] == {"target": 55, "other": 8, "ground": 14, "none": 0}


def test_hardbar_live_stops_on_other_non_targets_but_counts_creamy() -> None:
    import hardbar_live as hb

    ev = [
        {"type": "entity_appear", "gid": 1, "job": 1002},
        {"type": "entity_appear", "gid": 2, "job": 1018},
        {"type": "entity_appear", "gid": 3, "job": 1031},
        {"type": "act", "src_gid": 2000002, "target_gid": 1, "damage": 180},
        {"type": "act", "src_gid": 2000002, "target_gid": 2, "damage": 170},
    ]
    got = hb.bars(ev)
    assert got["stop"] == {} and got["creamy_hits"] == 1
    got = hb.bars([*ev, {"type": "act", "src_gid": 2000002, "target_gid": 3, "damage": 9}])
    assert got["stop"] == {"non_target_hit:1031": 1}
    assert hb.bars([{"type": "npc_contact"}, {"type": "map_change"}])["stop"] == {
        "npc_contact": 1,
        "map_change": 1,
    }


def test_loot_stray_flags_a_treadmill_but_not_a_3x3_loot() -> None:
    ns = 1_000_000_000
    steps = [{"t_ns": 10 * ns, "s": 4.0, "cell": [300, 51]},
             {"t_ns": 30 * ns, "s": 4.0, "cell": [100, 100]}]  # fmt: skip
    pk = [{"type": "self_move", "t_mono_ns": t * ns, "x1": x, "y1": y}
          for t, x, y in ((7, 300, 51), (8, 304, 49), (9, 311, 44),   # the v32 run 1 treadmill
                          (27, 101, 100), (28, 99, 101))]  # fmt: skip
    got = aj.loot_stray(steps, pk)
    assert got == {"steps": 2, "stray_ge_4": 1, "share": 0.5, "max_p50": 11}


def test_hardbar_live_counts_a_held_out_maps_unknown_species_apart() -> None:
    import hardbar_live as hb

    ev = [{"type": "entity_appear", "gid": 4, "job": 1048},
          {"type": "act", "src_gid": 2000002, "target_gid": 4, "damage": 50}]  # fmt: skip
    assert hb.bars(ev)["stop"] == {"non_target_hit:1048": 1}  # prt_fild08: a hard bar
    got = hb.bars(ev, {1002, 1063, 1008}, {1048, 1051, 1080})
    assert got["stop"] == {} and got["apart_hits"] == {"1048": 1}


def test_ui_cover_tallies_in_view_seconds_under_each_window() -> None:
    import ui_cover as uc

    wins = ((0, 0, 220, 326), (230, 0, 520, 132))
    pts = [(100, 100, True), (300, 50, False), (640, 340, True), (2000, 10, True), (640, 800, True)]
    got = uc.tally(pts, wins)
    assert got["in_view_s"] == 3 and got["covered_s"] == 2 and got["targets_in_view_s"] == 2
    assert got["targets_covered_share"] == 0.5
    assert got["per_window_share"] == {"basic_info+menu": 0.3333, "shortcut_bar": 0.3333}
    assert uc.window_of(520, 132, wins) == 1 and uc.window_of(521, 50, wins) is None


def test_arm_spans_split_a_run_into_its_paced_and_default_blocks() -> None:
    ev = [{"t_ns": 0, "kind": "loop_start"}, {"t_ns": 5, "kind": "send_gap", "on": True},
          {"t_ns": 50, "kind": "x"}, {"t_ns": 65, "kind": "send_gap", "on": False},
          {"t_ns": 90, "kind": "y"}]  # fmt: skip
    assert aj.arm_spans(ev) == [(5, 65, True), (65, 90, False)]
    assert aj.arm_spans([{"t_ns": 1, "kind": "loop_start"}]) == []


def test_every_table_is_reachable_from_the_command_line() -> None:
    import inspect

    src = inspect.getsource(aj.main)
    for name in ("strike", "dead", "loot", "stray", "blocks", "species", "retry"):
        assert f'"{name}": {name}_table' in src


def test_retry_table_splits_a_real_run_without_losing_an_item() -> None:
    """v36's judge on a REAL session (v34 run 1, before any retry existed): the two parities
    together hold exactly the items and kills of ``loot_table``'s "all", and no retry counts."""
    import pytest

    sid = "20261018T013812-demo-hunt-flow34"
    if not (aj.DEMO / sid / "flow_judge.json").exists():
        pytest.skip("the v34 session is not banked on this host")
    s = aj.load(sid)
    rt = aj.retry_table([s])
    al = aj.loot_table([s])["all"]
    assert rt["retry"]["items"] + rt["none"]["items"] == al["items"]
    assert rt["retry"]["kills"] + rt["none"]["kills"] == al["kills"]
    assert rt["retry"]["item_picked"] + rt["none"]["item_picked"] == al["picked"]
    assert rt["retry"]["steps"] + rt["none"]["steps"] == 143
    assert not any(rt[a].get("retry_queued") or rt[a].get("retry_clicks") for a in rt)


def test_loot_stray_clicks_ignores_the_next_search_walk() -> None:
    ns = 1_000_000_000
    steps = [{"t_ns": 10 * ns, "s": 4.0, "cell": [300, 51]}]
    clicks = [{"t": 7 * ns, "kind": "loot"}, {"t": 8 * ns, "kind": "loot"},
              {"t": 10 * ns + ns // 5, "kind": "walk"}]  # fmt: skip
    pk = [{"type": "self_move", "t_mono_ns": 7 * ns + ns // 10, "x1": 301, "y1": 51},
          {"type": "self_move", "t_mono_ns": 8 * ns + ns // 10, "x1": 300, "y1": 52},
          {"type": "self_move", "t_mono_ns": 10 * ns + ns // 4, "x1": 320, "y1": 60}]  # fmt: skip
    assert aj.loot_stray(steps, pk)["stray_ge_4"] == 1  # the window caught the search walk
    got = aj.loot_stray_clicks(steps, clicks, pk)
    assert got["stray_ge_4"] == 0 and got["max_p50"] == 1
