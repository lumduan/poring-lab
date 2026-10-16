"""flow_judge: hunt-flow's offline judge (3.40), on synthetic packets."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import flow_judge as fj  # noqa: E402

S = 10**9
MOB = 110000001


def appear(t: float, g: int, x: int, y: int, job: int = 1002) -> dict:
    return {"type": "entity_appear", "objtype": 5, "gid": g, "x": x, "y": y, "job": job,
            "t_mono_ns": int(t * S)}  # fmt: skip


def ev(t: float, typ: str, **kw: object) -> dict:
    return {"type": typ, "t_mono_ns": int(t * S), **kw}


def base() -> list[dict]:
    return [ev(0.0, "self_move_request", x=12, y=10),
            ev(0.0, "self_move", x0=10, y0=10, x1=12, y1=10),
            appear(0.0, MOB, 15, 10)]  # fmt: skip


def pick_fixed(cell: tuple[int, int]):  # the click's picked cell, whatever the pixel
    return lambda origin, px: cell


def test_the_gm_walks_one_cell_per_150_ms_and_diagonals_take_longer() -> None:
    pts, moving = fj.gm_track([ev(1.0, "self_move", x0=0, y0=0, x1=2, y1=1)])
    assert [c for _, c in pts] == [(0, 0), (1, 1), (2, 1)]
    assert pts[1][0] == int(1.0 * S + 210e6) and pts[2][0] == int(1.0 * S + 360e6)
    assert moving == [(1 * S, int(1.0 * S + 360e6))]
    pts, moving = fj.gm_track([ev(1.0, "self_move", x0=0, y0=0, x1=5, y1=0),
                               ev(1.2, "entity_stop", gid=fj.GM, x=1, y=0)])  # fmt: skip
    assert pts[-1] == (int(1.2 * S), (1, 0)) and moving == [(1 * S, int(1.2 * S))]


def test_an_attack_click_that_lands_is_a_hit_with_its_range_and_timing() -> None:
    events = base() + [ev(2.3, "attack_request", target_gid=MOB),
                       ev(2.5, "act", src_gid=fj.GM, target_gid=MOB, damage=182, kind="normal"),
                       ev(2.6, "entity_vanish", gid=MOB, reason=1)]  # fmt: skip
    clicks = [fj.Click(int(2.0 * S), 600, 300)]
    out = fj.judge(events, clicks, [], 0, pick_fixed((15, 10)))
    assert out["trials"] == 1 and out["hits"] == 1 and out["why"] == {"hit": 1}
    row = out["trial_rows"][0]
    assert row["range"] == 3 and row["rank"] == 1 and row["click_to_hit"] == 0.5
    assert out["kills"] == 1


def test_a_click_on_a_monster_box_that_only_walks_is_a_walk_only_miss() -> None:
    events = base() + [ev(2.2, "self_move_request", x=15, y=11)]
    frames = [(int(1.8 * S), [[580, 280, 620, 320, 0.9, "monster"]])]
    out = fj.judge(events, [fj.Click(int(2.0 * S), 600, 300)], frames, 0, pick_fixed((15, 10)))
    assert out["why"] == {"walk_only": 1} and out["hits"] == 0


def test_a_box_older_than_half_a_second_is_no_attempt() -> None:
    events = base() + [ev(2.2, "self_move_request", x=15, y=11)]
    frames = [(int(1.2 * S), [[580, 280, 620, 320, 0.9, "monster"]])]
    out = fj.judge(events, [fj.Click(int(2.0 * S), 600, 300)], frames, 0, pick_fixed((15, 10)))
    assert out["trials"] == 0 and out["clicks"]["walk_click"] == 1


def test_a_re_click_while_already_hitting_is_a_follow_up_not_a_trial() -> None:
    events = base() + [ev(2.3, "attack_request", target_gid=MOB),
                       ev(2.5, "act", src_gid=fj.GM, target_gid=MOB, damage=50, kind="normal"),
                       ev(3.3, "attack_request", target_gid=MOB)]  # fmt: skip
    clicks = [fj.Click(int(2.0 * S), 600, 300), fj.Click(int(3.0 * S), 600, 300)]
    out = fj.judge(events, clicks, [], 0, pick_fixed((15, 10)))
    assert out["trials"] == 1 and out["clicks"]["follow_up"] == 1


def test_a_request_without_any_act_and_a_miss_are_failures() -> None:
    events = base() + [ev(2.3, "attack_request", target_gid=MOB)]
    out = fj.judge(events, [fj.Click(int(2.0 * S), 600, 300)], [], 0, pick_fixed((15, 10)))
    assert out["why"] == {"request_no_act": 1}
    events.append(ev(2.5, "act", src_gid=fj.GM, target_gid=MOB, damage=0, kind="normal"))
    out = fj.judge(events, [fj.Click(int(2.0 * S), 600, 300)], [], 0, pick_fixed((15, 10)))
    assert out["why"] == {"miss_only": 1}


def test_the_client_attacking_another_unit_than_the_one_clicked_is_other_unit() -> None:
    other = MOB + 1
    events = base() + [appear(0.0, other, 20, 10), ev(2.3, "attack_request", target_gid=other),
                       ev(2.5, "act", src_gid=fj.GM, target_gid=other, damage=99)]  # fmt: skip
    out = fj.judge(events, [fj.Click(int(2.0 * S), 600, 300)], [], 0, pick_fixed((15, 10)))
    assert out["why"] == {"other_unit": 1}


def test_npc_and_ui_clicks_are_not_trials_and_the_window_bounds_hold() -> None:
    events = base() + [ev(2.2, "npc_contact", npc_gid=5)]
    clicks = [fj.Click(int(2.0 * S), 600, 300), fj.Click(int(2.5 * S), 10, 10),
              fj.Click(int(700 * S), 600, 300)]  # fmt: skip
    out = fj.judge(events, clicks, [], 0, pick_fixed((15, 10)), in_ui=lambda u, v: u < 50)
    assert out["clicks"]["clicks"] == 1 and out["clicks"]["npc_click"] == 1 and out["trials"] == 0


def test_human_clicks_are_left_downs_of_source_human_in_client_px() -> None:
    def line(src: str, action: str, x: float, y: float, button: str = "left") -> str:
        return json.dumps({"source": src, "accepted": True, "t_mono_ns": 5,
                           "event": {"type": "mouse_button", "button": button, "action": action,
                                     "x": x, "y": y}})  # fmt: skip

    lines = [line("human", "down", 0.5, 0.5), line("human", "up", 0.5, 0.5),
             line("bot", "down", 0.5, 0.5), line("human", "down", 0.5, 0.5, "right"),
             line("human", "down", 0.01, 0.5)]  # fmt: skip
    got = fj.human_clicks(lines, (1440, 900), (80, 77, 1280, 720))
    assert [(c.u, c.v) for c in got] == [(720 - 80, 450 - 77)]


def test_idle_is_the_share_of_the_window_not_moving() -> None:
    _, moving = fj.gm_track([ev(0.0, "self_move", x0=0, y0=0, x1=10, y1=0)])
    assert abs(fj.moving_share(moving, 0, 3 * S) - 0.5) < 1e-9


def test_a_reused_gid_keeps_every_life() -> None:
    """rAthena reuses a dead mob's id for a later spawn (Batt's demo, 110019414)."""
    events = [appear(0.0, MOB, 5, 5), ev(10.0, "entity_vanish", gid=MOB, reason=1),
              appear(50.0, MOB, 9, 9)]  # fmt: skip
    life = fj.alive(events)
    assert fj.present(life, MOB, int(5 * S)) and not fj.present(life, MOB, int(20 * S))
    assert fj.present(life, MOB, int(60 * S))
    assert fj.died_before(life, MOB, int(10.3 * S), 0.5)
    assert not fj.died_before(life, MOB, int(11 * S), 0.5)


def test_the_primary_bar_allows_re_clicks_within_w() -> None:
    other = MOB + 1
    events = base() + [appear(0.0, other, 30, 30),
                       ev(2.3, "attack_request", target_gid=MOB),
                       ev(6.5, "act", src_gid=fj.GM, target_gid=MOB, damage=182),
                       ev(10.3, "attack_request", target_gid=other),
                       ev(16.0, "act", src_gid=fj.GM, target_gid=other, damage=182)]  # fmt: skip
    engs = [{"k": 0, "t_first_click": int(2.0 * S), "pred_cell": [15, 10]},
            {"k": 1, "t_first_click": int(10.0 * S), "pred_cell": [30, 30]},
            {"k": 2, "t_first_click": int(20.0 * S), "pred_cell": [60, 60]}]  # fmt: skip
    out = fj.bot_engagements(events, engs)
    assert [r["why"] for r in out["rows"]] == ["hit", "hit_late", "no_unit"]
    assert out["rows"][0]["t_hit_s"] == 4.5 and out["hit_within_w"] == 1 and out["counted"] == 3


def test_a_unit_killed_by_another_hand_is_excluded() -> None:
    events = base() + [ev(3.0, "entity_vanish", gid=MOB, reason=1)]
    out = fj.bot_engagements(events, [{"k": 0, "t_first_click": int(2.0 * S),
                                       "pred_cell": [15, 10]}])  # fmt: skip
    assert out["rows"][0]["why"] == "excluded:killed_by_other" and out["counted"] == 0


def test_idle_between_kills_is_a_death_to_our_next_click() -> None:
    events = base() + [ev(2.5, "act", src_gid=fj.GM, target_gid=MOB, damage=182),
                       ev(3.0, "entity_vanish", gid=MOB, reason=1)]  # fmt: skip
    clicks = [fj.Click(int(2.0 * S), 0, 0), fj.Click(int(3.8 * S), 0, 0)]
    out = fj.idle_between_kills(events, clicks, 0, int(100 * S))
    assert out == {"n": 1, "p50": 0.8, "p90": 0.8}


def test_the_queue_hit_through_counts_rank_0_dispatches() -> None:
    lines = [json.dumps({"kind": "dispatch", "rank": 0, "valid": True}),
             json.dumps({"kind": "dispatch", "rank": 0, "valid": False}),
             json.dumps({"kind": "dispatch", "rank": 1, "valid": True}),
             json.dumps({"kind": "walk_click"})]  # fmt: skip
    assert fj.queue_hit_through(lines) == {"dispatches": 2, "valid": 1, "rate": 0.5}


def test_unintended_attacks_are_requests_outside_every_engagement() -> None:
    events = [ev(1.0, "attack_request", target_gid=MOB), ev(10.0, "attack_request", target_gid=MOB),
              ev(30.0, "attack_request", target_gid=MOB)]  # fmt: skip
    engs = [{"t_first_click": int(0.9 * S), "t_end": int(2.0 * S)}]
    assert fj.unintended_attacks(events, engs, 0, int(20 * S)) == 1  # 10 s; 30 s is outside


def test_the_moving_share_counts_search_windows_only() -> None:
    lines = [json.dumps({"kind": "mode", "mode": "search", "t_ns": 0}),
             json.dumps({"kind": "mode", "mode": "engaged", "t_ns": int(10 * S)}),
             json.dumps({"kind": "mode", "mode": "search", "t_ns": int(20 * S)})]  # fmt: skip
    moving = [(int(5 * S), int(25 * S))]
    assert fj.search_moving_share(lines, moving, 0, int(30 * S)) == 0.5  # (5 + 5) / (10 + 10)


def test_stops_during_engagements_count_standstills_in_steer_and_engaged_windows() -> None:
    lines = [json.dumps({"kind": "mode", "mode": "search", "t_ns": 0}),
             json.dumps({"kind": "mode", "mode": "steer", "t_ns": int(10 * S)}),
             json.dumps({"kind": "mode", "mode": "engaged", "t_ns": int(14 * S)}),
             json.dumps({"kind": "mode", "mode": "search", "t_ns": int(20 * S)})]  # fmt: skip
    moving = [(0, int(5 * S)), (int(9 * S), int(12 * S)), (int(13 * S), int(15 * S)),
              (int(21 * S), int(25 * S))]  # fmt: skip
    out = fj.engagement_stops(lines, moving, 1, 0, int(30 * S))
    assert out == {"stops": 2, "engagements": 1, "per_engagement": 2.0}


def test_walk_click_accuracy_splits_moving_clicks_and_signs_the_error_along_the_motion() -> None:
    events = [
        ev(0.0, "self_move", x0=0, y0=0, x1=20, y1=0),  # east, 150 ms a cell
        ev(1.0, "self_move_request", x=13, y=0),  # meant 10: landed 3 AHEAD
        ev(4.0, "self_move_request", x=31, y=1),
    ]  # standing at 20, meant 30: 1 off
    walks = [{"t": int(0.95 * S), "to": [10, 0]}, {"t": int(3.95 * S), "to": [30, 0]},
             {"t": int(9.0 * S), "to": [5, 5]}]  # the last one never answered  # fmt: skip
    _pts, moving = fj.gm_track(events[:1])
    out = fj.walk_click_accuracy(events, walks, moving)
    assert out["moving"] == {"n": 1, "within_1": 0.0, "along_p50": 3.0}
    assert out["standing"] == {"n": 1, "within_1": 1.0, "along_p50": None}


def test_kills_split_by_whether_a_sword_read_engagement_asked_for_them() -> None:
    other = MOB + 1
    events = base() + [appear(0.0, other, 20, 10),
                       ev(2.3, "attack_request", target_gid=MOB),
                       ev(2.5, "act", src_gid=fj.GM, target_gid=MOB, damage=182),
                       ev(2.6, "entity_vanish", gid=MOB, reason=1),
                       ev(9.0, "attack_request", target_gid=other),  # a walk click turned attack
                       ev(9.4, "act", src_gid=fj.GM, target_gid=other, damage=182),
                       ev(9.5, "entity_vanish", gid=other, reason=1)]  # fmt: skip
    engs = [{"t_first_click": int(2.0 * S), "t_end": int(3.0 * S)}]
    assert fj.kills_by_origin(events, engs, 0, int(20 * S)) == {"engaged": 1, "unintended": 1}


def test_the_hard_bars_count_npc_contacts_map_changes_and_non_target_species() -> None:
    creamy = MOB + 7
    events = base() + [appear(0.0, creamy, 18, 10, job=1018),
                       ev(1.0, "map_change", map="prt_fild08.gat", x=1, y=1),  # before t0
                       ev(3.0, "act", src_gid=fj.GM, target_gid=MOB, damage=182),
                       ev(4.0, "act", src_gid=fj.GM, target_gid=creamy, damage=182),
                       ev(5.0, "npc_contact", npc_gid=5)]  # fmt: skip
    out = fj.hard_bars(events, int(2 * S), int(10 * S), {1002: "Poring"})
    assert out == {"npc_contacts": 1, "map_changes": 0, "non_target_jobs_hit": [1018],
                   "pass": False}  # fmt: skip


def test_heading_metrics_count_reversals_and_straight_runs() -> None:
    events = [ev(0.0, "self_move", x0=0, y0=0, x1=10, y1=0),  # east 10
              ev(2.0, "self_move", x0=10, y0=0, x1=10, y1=-5),  # a 90 deg turn: a new run
              ev(3.0, "self_move", x0=10, y0=-5, x1=10, y1=0)]  # back: a reversal  # fmt: skip
    out = fj.heading_metrics(events, 0, int(60 * S))
    assert out["reversals_per_min"] == 1.0
    assert out["mean_straight_run"] == round((10 + 5 + 5) / 3, 1)


def test_selection_metrics_measure_distance_and_nearest_at_the_dispatch() -> None:
    near, far = MOB + 1, MOB + 2
    events = [ev(0.0, "self_move", x0=10, y0=10, x1=10, y1=10),
              appear(0.0, near, 12, 10), appear(0.0, far, 17, 10)]  # fmt: skip
    lines = [
        json.dumps({"t_ns": int(1.0 * S), "kind": "dispatch", "track": 7, "valid": True}),
        json.dumps({"t_ns": int(2.0 * S), "kind": "target_reacquired", "track": 7, "as": 9}),
    ]
    engs = [{"k": 0, "track": 9, "t_first_click": int(3.0 * S)}]
    out = fj.selection_metrics(events, lines, [{"k": 0, "gid": far}], engs)
    assert out == {"n": 1, "nearest_share": 0.0, "dist_p50": 7.0, "dist_p90": 7.0}
    out = fj.selection_metrics(events, lines, [{"k": 0, "gid": near}], engs)
    assert out["nearest_share"] == 1.0 and out["dist_p50"] == 2.0


def test_landing_is_reported_by_species_with_clicks_per_landing() -> None:
    luna = MOB + 3
    events = base() + [appear(0.0, luna, 14, 10, job=1063)]
    rows = [{"k": 0, "gid": MOB, "why": "hit"}, {"k": 1, "gid": luna, "why": "hit_late"}]
    engs = [{"k": 0, "t_first_click": int(2 * S), "t_end": int(3 * S),
             "hovers": [{"clicked": 1, "aim_px": 4.0}]},
            {"k": 1, "t_first_click": int(5 * S), "t_end": int(9 * S), "hovers": []}]  # fmt: skip
    clicks = [{"t": int(2 * S), "kind": "strike"}, {"t": int(2.6 * S), "kind": "strike_burst"},
              {"t": int(5 * S), "kind": "strike"}]  # fmt: skip
    out = fj.species_landing(events, rows, engs, clicks)
    assert out["Poring"] == {"n": 1, "landed": 1, "rate": 1.0, "clicks_per_landing": 2.0,
                             "aim_px_p50": 4.0}  # fmt: skip
    assert out["Lunatic"]["landed"] == 0 and out["Lunatic"]["rate"] == 0.0
