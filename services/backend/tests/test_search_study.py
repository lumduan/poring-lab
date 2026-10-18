"""search_study: the SEARCH study's offline measures (packets as ground truth), on synthetic
packets, plus REAL-session positive cases (skipped when the banked sessions are absent)."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import flow_judge as fj  # noqa: E402
import search_study as ss  # noqa: E402

S = 10**9
A, B, C, R_ = 110000001, 110000002, 110000003, 110000004
BATT = "20261016T093835-demo-human-demo"
BOT = "20261018T070558-demo-hunt-flow36"
DEMO = Path("/dev/shm/poring-lab-demo")


def ev(t: float, typ: str, **kw: object) -> dict:
    return {"type": typ, "t_mono_ns": int(t * S), **kw}


def appear(t: float, g: int, x: int, y: int, job: int = 1002, **kw: object) -> dict:
    return ev(t, "entity_appear", objtype=5, gid=g, x=x, y=y, job=job, **kw)


def stand(x: int, y: int) -> list[dict]:
    return [ev(0.0, "map_change", x=x, y=y)]


# --- kills per sighting ---------------------------------------------------------------------------


def test_kills_per_sighting_is_kills_per_hour_over_sight_per_10_min() -> None:
    assert ss.kills_per_sighting(300.0, 44.0) == 6.82
    assert ss.kills_per_sighting(148.7, 25.5) == 5.83
    assert ss.kills_per_sighting(100.0, 0.0) is None


def test_a_kill_needs_our_act_and_conversion_uses_the_windowed_sight() -> None:
    events = [*stand(50, 50), appear(1.0, A, 55, 50), appear(1.0, B, 45, 50),
              ev(2.0, "act", src_gid=fj.GM, target_gid=A, damage=180, kind="normal"),
              ev(2.5, "entity_vanish", gid=A, reason=1),
              ev(3.0, "entity_vanish", gid=B, reason=1)]  # fmt: skip
    assert ss.kill_times(events, 0, 60 * S) == [int(2.5 * S)]
    out = ss.conversion(events, 0, 60 * S)
    assert out["kills"] == 1 and out["kills_per_hour"] == 60.0
    assert out["sight_per_10min"] == 20.0 and out["kills_per_sighting"] == 3.0


# --- the view sweep -------------------------------------------------------------------------------


def test_a_straight_walk_brings_29_new_cells_a_step_and_re_sweeps_nothing() -> None:
    fld = ss.Field([ev(0.0, "self_move", x0=50, y0=50, x1=70, y1=50)])
    s = ss.scan(fld, 0, 4 * S)
    out = ss.sweep_summary(s)
    assert out["new_in_view_per_cell"] == 29.0
    assert out["reswept_share"] == {"<=5s": 0.0, "<=30s": 0.0, "<=120s": 0.0}
    assert out["diagonal_share"] == 0.0
    assert out["age_weighted_new_per_min"] == out["fresh_per_min"]  # all of it never seen


def test_a_diagonal_step_brings_about_57_cells_the_square_view_rewards_diagonals() -> None:
    fld = ss.Field([ev(0.0, "self_move", x0=50, y0=50, x1=70, y1=70)])
    out = ss.sweep_summary(ss.scan(fld, 0, 5 * S))
    assert 54 <= out["new_in_view_per_cell"] <= 57
    assert out["diagonal_share"] == 1.0


def test_walking_back_re_sweeps_the_ground_just_seen() -> None:
    fld = ss.Field([ev(0.0, "self_move", x0=50, y0=50, x1=70, y1=50),
                    ev(3.0, "self_move", x0=70, y0=50, x1=50, y1=50)])  # fmt: skip
    s = ss.scan(fld, 0, 7 * S)
    out = ss.sweep_summary(s)
    # out: 20 fresh columns; back: 20 columns all seen 0.25-6 s before
    assert out["reswept_share"]["<=30s"] == 0.5 and out["reswept_share"]["<=120s"] == 0.5
    assert 0.0 < out["reswept_share"]["<=5s"] < 0.5
    assert int(s.fresh.sum()) == 20 * 29


def test_the_walkable_mask_counts_only_walkable_cells() -> None:
    wk = np.ones((120, 120), dtype=bool)
    wk[60:, :] = False  # the half above y 60 is a cliff
    fld = ss.Field([ev(0.0, "self_move", x0=50, y0=50, x1=70, y1=50)])
    out = ss.sweep_summary(ss.scan(fld, 0, 4 * S, walkable=wk))
    assert out["new_in_view_per_cell"] == 24.0  # y 36..59 of 36..64


# --- presence, stretches --------------------------------------------------------------------------


def test_no_target_stretches_and_the_time_per_kill() -> None:
    events = [*stand(50, 50), appear(2.0, A, 55, 50),
              ev(4.9, "act", src_gid=fj.GM, target_gid=A, damage=900, kind="normal"),
              ev(5.0, "entity_vanish", gid=A, reason=1)]  # fmt: skip
    fld = ss.Field(events)
    s = ss.scan(fld, 0, 10 * S)
    s.kills = len(ss.kill_times(events, 0, 10 * S))
    out = ss.presence_summary([s])
    assert out["stretches"] == 2 and out["stretch_mean_s"] == 3.5  # 0-2 s and 5-10 s
    assert out["none_s_per_kill"] == 7.0 and out["some_s_per_kill"] == 3.0
    assert out["none_share"] == 0.7
    assert out["encounters_per_none_min"] == round(2 / (7 / 60), 2)


def test_a_creamy_is_not_a_target_and_a_far_one_is_not_in_view() -> None:
    events = [*stand(50, 50), appear(0.5, A, 55, 50, job=1018), appear(0.5, B, 66, 50)]
    s = ss.scan(ss.Field(events), 0, 2 * S)
    assert int(s.n_targets.max()) == 0


# --- yield by age --------------------------------------------------------------------------------


def test_an_entry_is_classed_by_how_long_ago_its_cell_was_in_view() -> None:
    events = [
        ev(0.0, "self_move", x0=50, y0=50, x1=80, y1=50),
        appear(1.5, A, 74, 50),  # GM at (60, 50): its cell comes into view now, never seen
        ev(4.5, "self_move", x0=80, y0=50, x1=50, y1=50),
        appear(8.0, B, 43, 50),
    ]  # GM back at (57, 50): (43, 50) was in view ~7 s ago
    s = ss.scan(ss.Field(events), 0, 10 * S)
    y = ss.yield_by_age(s)
    assert y["never"]["entries"] == 1 and y["<=30s"]["entries"] == 1
    assert sum(v["entries"] for v in y.values()) == 2
    assert ss.age_class(math.inf) == len(ss.AGE_NAMES) - 1
    assert ss.AGE_NAMES[ss.age_class(700.0)] == "10-20min"


def test_block_density_pools_fresh_ground_and_its_entries() -> None:
    events = [ev(0.0, "self_move", x0=50, y0=50, x1=90, y1=50), appear(2.0, A, 77, 50)]
    s = ss.scan(ss.Field(events), 0, 8 * S)
    dens = ss.block_density([s], min_cells=1)
    assert sum(s.block_entries.values()) == 1
    assert dens[(1, 1)] > 0 and ss.ground_density(s, dens) is not None


# --- the path -------------------------------------------------------------------------------------


def test_straight_runs_and_reversals_match_flow_judge() -> None:
    events = [
        ev(0.0, "self_move", x0=50, y0=50, x1=60, y1=50),
        ev(2.0, "self_move", x0=60, y0=50, x1=70, y1=52),  # ~11 deg: the same run
        ev(4.0, "self_move", x0=70, y0=52, x1=60, y1=52),
    ]  # back: a reversal
    fld = ss.Field(events)
    runs, rev, walked = ss.straight_runs(fld, 0, 6 * S)
    hm = fj.heading_metrics(events, 0, 6 * S)
    assert rev == 1 and runs == [20, 10] and walked == 30
    assert hm["mean_straight_run"] == round(sum(runs) / len(runs), 1)


# --- turning, engagement ends --------------------------------------------------------------------


def test_turning_toward_a_target_that_enters_off_heading() -> None:
    events = [ev(0.0, "self_move", x0=50, y0=50, x1=90, y1=50),
              appear(1.5, A, 62, 63),  # GM at (60, 50), walking east; A to the north
              ev(2.5, "self_move_request", x=63, y=60),  # GM at (66, 50): toward A
              ev(4.0, "attack_request", target_gid=A)]  # fmt: skip
    out = ss.turn_toward(ss.Field(events), 0, 20 * S)
    off = out["free_off_heading"]
    assert off["n"] == 1 and off["turned_2s"] == 1.0 and off["turn_lat_p50"] == 1.0
    assert off["attacked_10s"] == 1.0 and off["attack_lat_p50"] == 2.5
    assert out["busy"]["n"] == 0


def test_an_engagement_end_with_none_in_view_its_wait_and_a_remembered_target() -> None:
    events = [
        *stand(50, 50),
        appear(0.0, A, 56, 50),
        ev(3.9, "act", src_gid=fj.GM, target_gid=A, damage=900, kind="normal"),
        ev(4.0, "entity_vanish", gid=A, reason=1),
        # R walks east out of the view (reason 0) at x 65: remembered 15 cells away
        appear(0.5, R_, 64, 50, x1=70, y1=50, speed=400),
        ev(1.3, "entity_vanish", gid=R_, reason=0),
        appear(9.0, C, 63, 50),
    ]  # the next target: 3 s after the end at 6 s
    fld = ss.Field(events)
    s = ss.scan(fld, 0, 20 * S)
    out = ss.ends_summary(fld, s, [int(2 * S), int(6 * S)], 0, 20 * S)
    assert out["ends"] == 2 and out["none_in_view"] == 1 and out["none_share"] == 0.5
    assert out["wait_p50_p75_p90_s"][0] == 3.0
    assert out["remembered_15_25_share"] == 1.0 and out["remembered_nearest_p50"] == 15.0
    assert out["next_target_from"] == {"standing": 1}


# --- the proposal's scorer ------------------------------------------------------------------------


def test_rel_yield_follows_the_age_table() -> None:
    got = ss.rel_yield([0.0, 300.0, 900.0, 1500.0, math.inf]).tolist()
    assert got == [0.32, 0.32, 0.5, 0.82, 1.0]
    mids = [10.0, 60.0, 200.0, 400.0, 900.0, 1500.0, math.inf]  # one age inside each class
    assert ss.rel_yield(mids).tolist() == list(ss.CLASS_REL)
    assert [ss.age_class(a) for a in mids] == list(range(len(ss.AGE_NAMES)))


def test_band_score_prefers_never_seen_ground_and_diagonals_per_walking_second() -> None:
    area = np.ones((200, 200), dtype=bool)
    last = np.full((200, 200), ss.NEVER)
    here = (100, 100)
    east = ss.band_score(area, area, here, 0.0, last, 100 * S)
    ne = ss.band_score(area, area, here, math.pi / 4, last, 100 * S)
    assert east is not None and ne is not None
    assert east[2] == ne[2] == 40 and east[1] == 40 * 29
    assert ne[0] > 1.3 * east[0]  # 57 cells / 0.21 s against 29 / 0.15 s
    seen = last.copy()
    seen[:, 115:] = 95 * S  # the ground east was in view 5 s ago
    east2 = ss.band_score(area, area, here, 0.0, seen, 100 * S)
    assert east2 is not None and east2[0] == pytest.approx(0.32 * east[0])
    wall = area.copy()
    wall[:, 105:] = False
    assert ss.band_score(wall, wall, here, 0.0, last, 100 * S) is None  # a 4-cell run


def test_ray_cells_follow_hunt_flow_ray_run_angle() -> None:
    import hunt_flow as hf

    area = np.ones((120, 120), dtype=bool)
    area[:, 90:] = False
    for deg in (0, 30, 45, 100, 200, 315):
        a = math.radians(deg)
        cells = ss.ray_cells(area, (60, 60), a, 40)
        n, last = hf.ray_run_angle(area, (60, 60), a, 40)
        assert len(cells) - 1 == n and cells[-1] == last


# --- REAL sessions (positive cases; skipped when the banked sessions are absent) ------------------


def _need(sid: str) -> None:
    if not (DEMO / sid / "packets.jsonl.gz").exists():
        pytest.skip(f"{sid} not banked here")


def test_real_batt_demo_is_6_82_kills_per_sighting_and_its_no_target_stretches() -> None:
    _need(BATT)
    sess = ss.load_session(BATT, DEMO)
    cv = ss.conversion(sess.events, sess.t0, sess.w1)
    assert cv["kills"] == 50 and cv["kills_per_hour"] == 300.0
    assert cv["sight_per_10min"] == 44.0 and cv["kills_per_sighting"] == 6.82
    fld = ss.Field(sess.events)
    s = ss.scan(fld, sess.t0, sess.w1)
    s.kills = cv["kills"]
    pr = ss.presence_summary([s])
    assert pr["none_share"] == 0.43 and pr["stretches"] == 41
    assert pr["none_s_per_kill"] == 5.2 and pr["some_s_per_kill"] == 6.8
    path = ss.path_summary(fld, s, sess.t0, sess.w1)
    assert path["reversals_per_min"] == 3.6 and path["straight_run_mean"] == 16.9


def test_real_bot_run_its_kills_per_sighting_and_engagement_ends() -> None:
    _need(BOT)
    sess = ss.load_session(BOT, DEMO)
    cv = ss.conversion(sess.events, sess.t0, sess.w1)
    assert cv["kills_per_hour"] == 188.8 and cv["sight_per_10min"] == 37.5
    assert cv["kills_per_sighting"] == 5.03
    fld = ss.Field(sess.events)
    s = ss.scan(fld, sess.t0, sess.w1)
    ends = [int(e["t_end"]) for e in sess.engagements if e.get("t_end")]
    out = ss.ends_summary(fld, s, ends, sess.t0, sess.w1, sess.bot_events)
    assert out["ends"] == 216 and out["none_in_view"] == 84
    # the bot resumed its search heading unchanged after most "none" ends
    assert out["next_heading_turn"].get("kept", 0) >= 70


def test_real_bot_run_heading_regret_with_the_client_gat() -> None:
    _need(BOT)
    wk = ss.load_walkable("prt_fild08")
    if wk is None:
        pytest.skip("prt_fild08.gat not extracted here (client data: generated at run time)")
    sess = ss.load_session(BOT, DEMO)
    fld = ss.Field(sess.events)
    reg = ss.heading_regret(fld, sess.bot_events, sess.t0, sess.t0 + 600 * S, wk,
                            ss.search_area_of(wk))  # fmt: skip
    assert reg["n"] >= 30
    assert reg["chosen_over_best_sum"] is not None and 0.5 < reg["chosen_over_best_sum"] < 1.0
