from __future__ import annotations

import json
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
    for name in ("strike", "dead", "loot", "stray", "blocks", "species", "retry", "sword"):
        assert f'"{name}": {name}_table' in src
    assert '"heading"' in src and "heading_table(a.sessions)" in src  # v38: its own loader
    assert '"approach"' in src and "approach_table(a.sessions)" in src  # v39: the same
    assert '"deadprobe"' in src and "deadprobe_table(a.sessions)" in src  # 3.80 amendment
    assert '"falsedead"' in src and "falsedead_table(a.sessions)" in src  # v40


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


def test_apart_why_names_the_click_behind_each_non_target_attack() -> None:
    """3.76's classifier: a synthetic case, then the REAL held-out run (21 of 29 via loot)."""
    import apart_why as aw
    import pytest

    pk = [{"type": "entity_appear", "gid": 7, "job": 1051, "t_mono_ns": 0},
          {"type": "entity_appear", "gid": 8, "job": 1002, "t_mono_ns": 0},
          {"type": "attack_request", "target_gid": 8, "t_mono_ns": 5},
          {"type": "attack_request", "target_gid": 7, "t_mono_ns": 20}]  # fmt: skip
    cl = [{"t": 3, "kind": "strike", "track": 1}, {"t": 18, "kind": "loot", "src": "fixed"}]
    rows = aw.classify(pk, cl)
    assert [(r["job"], r["kind"], r["via"]) for r in rows] == [(1051, "loot", "fixed")]
    sid = "20261018T060344-demo-hunt-flow35"
    if not (aw.DEMO / sid / "packets.jsonl.gz").exists():
        pytest.skip("the held-out session is not banked on this host")
    s = aw.summary(aw.classify(*aw.load(sid)))
    assert s["requests"] == 29 and s["by_kind"]["loot"] == 21 and s["by_kind"]["walk"] == 5
    assert s["by_job"]["1051"] == 19  # Thief Bug, the looter on our piles


def test_sword_precision_on_the_real_held_out_run() -> None:
    """3.78's offline check of the cursor's SWORD (run A, prt_fild06): what stood at each checked
    point (packets). A SWORD verdict mostly had a mob within 1-2 cells (the undetected Thief Bugs);
    a CLEAR walk point almost never did."""
    import pytest

    sid = "20261018T101834-demo-hunt-flow37"
    if not (aj.DEMO / sid / "packets.jsonl.gz").exists():
        pytest.skip("the v37 run A session is not banked on this host")
    got = aj.sword_precision(aj.load(sid))
    ls, wc = got["loot_sword"], got["walk_clear"]
    assert ls["n"] == 46 and ls["mob_within_1"] >= 0.7 * ls["n"] and ls["job_1051"] >= 30
    assert wc["n"] == 336 and wc["mob_within_1"] <= 5
    assert got["walk_sword"]["mob_within_2"] == got["walk_sword"]["n"]


def test_heading_spans_are_clock_blocks_from_the_first_heading_arm() -> None:
    """v38: block b = [T0 + b * 10 min, ...), T0 = block 0's event; a block without its own event
    takes the alternation; a broken alternation or a missing block 0 refuses."""
    m = 60 * S
    ev = [{"t_ns": 5 * S, "kind": "loop_start"},
          {"t_ns": 100 * S, "kind": "heading_arm", "block": 0, "on": True},
          {"t_ns": 100 * S + 10 * m + 37 * S, "kind": "heading_arm", "block": 1, "on": False},
          # block 2 never re-planned (a long engagement): no event of its own
          {"t_ns": 100 * S + 34 * m, "kind": "walk_click"}]  # fmt: skip
    sp = aj.heading_spans(ev)
    assert [(a - 100 * S, b - 100 * S, on) for a, b, on in sp] == [
        (0, 10 * m, True), (10 * m, 20 * m, False), (20 * m, 30 * m, True),
        (30 * m, 34 * m, False)]  # fmt: skip
    bad = [*ev[:2], {"t_ns": 100 * S + 11 * m, "kind": "heading_arm", "block": 1, "on": True}]
    with pytest.raises(ValueError, match="alternation"):
        aj.heading_spans(bad)
    with pytest.raises(ValueError, match="block 1"):
        aj.heading_spans([{"t_ns": 0, "kind": "heading_arm", "block": 1, "on": True}])
    assert aj.heading_spans([{"t_ns": 0, "kind": "loop_start"}]) == []


def test_heading_table_splits_a_real_run_without_losing_a_kill() -> None:
    """The v38 judge on a REAL session (v37 run B, before v38 existed), with a NULL split (odd
    10-min blocks called "age"): the two arms hold exactly the run's kills in the judged window,
    its six blocks, and every engagement; the search measures come out for both arms."""
    import search_study as ss

    sid = "20261018T112036-demo-hunt-flow37"
    if not (aj.DEMO / sid / "flow_judge.json").exists():
        pytest.skip("the v37 session is not banked on this host")

    def null(sess):  # noqa: ANN001, ANN202
        b, out = 0, []
        while sess.t0 + b * 600 * S < sess.w1:
            out.append((sess.t0 + b * 600 * S, min(sess.t0 + (b + 1) * 600 * S, sess.w1),
                        b % 2 == 1))  # fmt: skip
            b += 1
        return out

    out = aj.heading_table([sid], spans_of=null)
    sess = ss.load_session(sid)
    kept = [(a, z) for a, z, _on in null(sess) if z - a >= 60 * S]
    assert out["age"]["blocks"] + out["cov"]["blocks"] == len(kept) == 6
    assert out["age"]["kills"] + out["cov"]["kills"] == sum(
        len(ss.kill_times(sess.events, a, z)) for a, z in kept)  # fmt: skip
    n_eng = sum(int(x["t_first_click"]) >= kept[0][0] and int(x["t_first_click"]) < kept[-1][1]
                for x in sess.engagements)  # fmt: skip
    assert sum(int(out[a]["landing"].split("/")[1]) for a in ("age", "cov")) == n_eng
    for arm in ("age", "cov"):
        o = out[arm]
        assert 0.2 < o["reswept_120s"] < 0.8 and o["encounters_per_none_min"] > 0
        assert 10 < o["sight_per_10min"] < 80 and o["kills_per_sighting"] is not None
    rows = out["per_run"][sid]["block_rows"]
    assert [r["block"] for r in rows] == [0, 1, 2, 3, 4, 5]
    assert [r["arm"] for r in rows] == ["cov", "age"] * 3


def test_mode_spans_and_the_engagement_a_moment_belongs_to() -> None:
    """v39's arm of a steer span = the k the runner holds then: the engagements created (first
    clicks) before it. Spans end at the next mode event, clipped to the judged window."""
    ev = [{"t_ns": 10, "kind": "mode", "mode": "search"},
          {"t_ns": 20, "kind": "mode", "mode": "steer"},
          {"t_ns": 25, "kind": "walk_click"},
          {"t_ns": 30, "kind": "mode", "mode": "engaged"},
          {"t_ns": 40, "kind": "mode", "mode": "steer"}]  # fmt: skip
    assert aj.mode_spans(ev, "steer", 0, 100) == [(20, 30), (40, 100)]
    assert aj.mode_spans(ev, "steer", 22, 50) == [(22, 30), (40, 50)]
    assert aj.mode_spans(ev, "steer", 31, 39) == []
    fcs = [28, 55]  # engagement 0's first click at 28, engagement 1's at 55
    assert [aj.k_at(fcs, t) for t in (20, 28, 29, 40, 55, 60)] == [0, 0, 1, 1, 1, 2]


def test_approach_table_splits_a_real_run_without_losing_an_engagement() -> None:
    """The v39 judge on a REAL session (v38 run 1, no per-engagement change: a parity null):
    the arms hold every engagement in the judged window and every steer second; the measures
    come out for both arms."""
    import search_study as ss

    sid = "20261018T141820-demo-hunt-flow38"
    if not (aj.DEMO / sid / "flow_judge.json").exists():
        pytest.skip("the v38 session is not banked on this host")
    out = aj.approach_table([sid])
    sess = ss.load_session(sid)
    n_eng = sum(sess.t0 <= int(x["t_first_click"]) < sess.w1 for x in sess.engagements)
    assert out["tail"]["engagements"] + out["base"]["engagements"] == n_eng == 151
    steer_s = sum(b - a for a, b in aj.mode_spans(sess.bot_events, "steer", sess.t0,
                                                  sess.w1)) / S  # fmt: skip
    assert abs(out["tail"]["steer_min"] + out["base"]["steer_min"] - steer_s / 60) < 0.2
    for arm in ("tail", "base"):
        o = out[arm]
        assert 0.1 < o["steer_moving_share"] < 0.9 and o["stops_per_steer_min"] > 0
        assert o["to3_n"] > 30 and 0 < o["to3_s_p50"] <= o["approach_s_p50"] + 5
        assert 0.3 < o["landing_share"] < 1.0
    run = out["per_run"][sid]
    assert set(run["arms"]) == {"tail", "base"} and "rel_steer_moving_share" in run
    assert sum(out[a]["steer_walk_clicks"] for a in ("tail", "base")) > 300


def test_approach_table_counts_the_creamy_a_steer_walk_click_became() -> None:
    """The safety side's POSITIVE case from a real run: v38 run 2's one Creamy attack request
    (gid 110054292, 1.1 s after a steer walk click: the client walked up first) is counted as a
    steer walk click turned into an attack on ANOTHER unit, in the arm of that moment."""
    sid = "20261018T152216-demo-hunt-flow38"
    if not (aj.DEMO / sid / "flow_judge.json").exists():
        pytest.skip("the v38 session is not banked on this host")
    out = aj.approach_table([sid])
    assert out["tail"]["walk_to_attack_other"] + out["base"]["walk_to_attack_other"] == 1


def test_walker_table_classes_every_engagement_of_a_real_run() -> None:
    """v41's judge on v38 run 1 (no per-engagement change: a parity null): every engagement in
    the judged window lands in exactly one class per arm; walkers are a real share (the
    conversion study: ~40 %); near -> click is never negative; flow_judge's landing agrees."""
    import search_study as ss

    sid = "20261018T141820-demo-hunt-flow38"
    if not (aj.DEMO / sid / "flow_judge.json").exists():
        pytest.skip("the v38 session is not banked on this host")
    out = aj.walker_table([sid])
    sess = ss.load_session(sid)
    n_eng = sum(sess.t0 <= int(x["t_first_click"]) < sess.w1 for x in sess.engagements)
    assert out["fix"]["all"]["engagements"] + out["base"]["all"]["engagements"] == n_eng == 151
    for arm in ("fix", "base"):
        o = out[arm]
        assert sum(o[c]["engagements"] for c in o if c != "all") == o["all"]["engagements"]
        assert o["walker"]["near_to_click_s_n"] == o["walker"]["engagements"]
        assert 0 <= o["walker"]["near_to_click_s_p50"] <= o["walker"]["approach_s_p50"] + 1e-9
    walkers = out["fix"]["walker"]["engagements"] + out["base"]["walker"]["engagements"]
    assert walkers == 60  # 28 + 32
    rows = json.loads((aj.DEMO / sid / "flow_judge.json").read_text())["engagements_w"]["rows"]
    landed = sum(int(out[a]["all"]["landing"].split("/")[0]) for a in ("fix", "base"))
    assert len(rows) == n_eng and landed == sum(r["why"] == "hit" for r in rows)
    assert "rel_walker_near_to_click_s_mean" in out["per_run"][sid]


def test_deadprobe_table_counts_every_dead_call_of_a_run_without_probes() -> None:
    """The 3.80 amendment's judge on v38 run 1 (before the probe existed): every dead call is
    covered by the truth (150, flow_judge.dead_call_truth), none probed, no table rows."""
    sid = "20261018T141820-demo-hunt-flow38"
    if not (aj.DEMO / sid / "flow_judge.json").exists():
        pytest.skip("the v38 session is not banked on this host")
    assert aj.deadprobe_table([sid]) == {"coverage": {"dead_calls": 150}}


def test_falsedead_table_splits_a_real_run_without_losing_an_engagement() -> None:
    """v40's judge on v38 run 1 (no fix: a parity null): the arms hold every engagement and
    every risky-ended dead call; nothing skipped; each false dead call there had its target
    alive at the end (flow_judge.dead_call_truth agrees on the run's 27 "target alive")."""
    import flow_judge as fj
    import search_study as ss

    sid = "20261018T141820-demo-hunt-flow38"
    if not (aj.DEMO / sid / "flow_judge.json").exists():
        pytest.skip("the v38 session is not banked on this host")
    out = aj.falsedead_table([sid])
    f, b = out["fix"], out["base"]
    assert f["engagements"] + b["engagements"] == 151
    assert f.get("skipped", 0) + b.get("skipped", 0) == 0
    sess = ss.load_session(sid)
    rows = json.loads((aj.DEMO / sid / "flow_judge.json").read_text())["engagements_w"]["rows"]
    tr = fj.dead_call_truth(sess.events, sess.engagements, rows, sess.t0, sess.w1)
    risky = [w for w, e in tr.values() if e == "risky"]
    assert f["risky_ended"] + b["risky_ended"] == len(risky)
    alive = sum(w == "target_alive" for w in risky)
    assert f["dead_called_alive"] + b["dead_called_alive"] == alive
    assert 0.3 < f["loot_share"] < 0.9 and 0.3 < b["loot_share"] < 0.9
