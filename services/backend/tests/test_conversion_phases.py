"""conversion_phases: the CONVERSION study's phase timeline (packets as ground truth), on synthetic
packets for each milestone, plus REAL-session positive cases (skipped when the banked sessions are
absent)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import conversion_phases as cp  # noqa: E402
import search_study as ss  # noqa: E402

S = 10**9
A, B, C = 110000001, 110000002, 110000003
BATT = "20261016T093835-demo-human-demo"
BOT = "20261018T112036-demo-hunt-flow37"
DEMO = Path("/dev/shm/poring-lab-demo")


def ev(t: float, typ: str, **kw: object) -> dict:
    return {"type": typ, "t_mono_ns": int(round(t * S)), **kw}


def appear(t: float, g: int, x: int, y: int, job: int = 1002, **kw: object) -> dict:
    return ev(t, "entity_appear", objtype=5, gid=g, x=x, y=y, job=job, **kw)


def fake_project(offs: object) -> np.ndarray:
    """10 px per cell, the GM at (500, 300)."""
    return np.asarray(offs, dtype=float).reshape(-1, 2) * 10.0 + np.array([500.0, 300.0])


FP = {(dx, dy) for dx in range(-8, 9) for dy in range(-8, 9)}


def scenario() -> list[dict]:
    """The GM stands at (100, 100); target A appears 10 cells east at t=1 (free); the GM walks
    toward it at 1.5 (8 cells, 150 ms a cell), the subject clicks at 2.9, the client walks the last
    cell at 3.0 and sends the attack request, the hit lands at 3.3 and A dies at 4.2; pickups at 5.0
    and 6.5. Target B appears 10 cells north at 4.0 (busy: A is alive) and leaves at 7.0."""
    return [
        ev(0.0, "map_change", x=100, y=100),
        appear(1.0, A, 110, 100),
        ev(1.5, "self_move_request", x=108, y=100),
        ev(1.5, "self_move", x0=100, y0=100, x1=108, y1=100),
        ev(3.0, "attack_request", target_gid=A),
        ev(3.0, "self_move", x0=108, y0=100, x1=109, y1=100),
        ev(3.3, "act", src_gid=cp.GM, target_gid=A, damage=100, kind="normal"),
        appear(4.0, B, 100, 110),
        ev(4.2, "entity_vanish", gid=A, reason=1),
        ev(5.0, "pickup_request", floor_id=1),
        ev(6.5, "pickup_request", floor_id=2),
        ev(7.0, "entity_vanish", gid=B, reason=0),
    ]


def inputs(fld: ss.Field, **kw: object) -> cp.Inputs:
    return cp.Inputs(cp.Paths(fld), fake_project, FP, **kw)  # type: ignore[arg-type]


# --- the cohort -----------------------------------------------------------------------------------


def test_entries_reproduce_turn_toward_free_and_busy() -> None:
    fld = ss.Field(scenario())
    rows = cp.entries(fld, 0, 20 * S)
    tt = ss.turn_toward(fld, 0, 20 * S)
    assert [(r["gid"], r["busy"]) for r in rows] == [(A, False), (B, True)]
    assert sum(not r["busy"] for r in rows) == tt["free_any"]["n"] == 1
    assert sum(r["busy"] for r in rows) == tt["busy"]["n"] == 1


def test_turn_is_a_walk_within_45_deg_or_an_attack() -> None:
    fld = ss.Field(scenario())
    cmds = cp.commands(fld.events)
    ct = [c[0] for c in cmds]
    assert cp.turn_time(fld, cmds, ct, 1 * S, A, 20 * S) == (int(1.5 * S), 3 * S)
    # B (north) is never walked toward nor attacked
    assert cp.turn_time(fld, cmds, ct, 4 * S, B, 7 * S) == (None, None)


def test_chain_end_follows_the_gid_across_view_flicker() -> None:
    evs = [ev(0.0, "map_change", x=100, y=100), appear(10.0, C, 114, 100),
           ev(12.0, "entity_vanish", gid=C, reason=0), appear(13.0, C, 113, 100),
           ev(20.0, "entity_vanish", gid=C, reason=1), appear(40.0, C, 113, 100),
           ev(41.0, "entity_vanish", gid=C, reason=0)]  # fmt: skip
    fld = ss.Field(evs)
    assert cp.chain_end(fld, C, 10 * S, 12 * S, 0) == (20 * S, 1)  # back within 10 s: one presence
    assert cp.chain_end(fld, C, 40 * S, 41 * S, 0) == (41 * S, 0)
    assert cp.chain_end(fld, C, 10 * S, 12 * S, 0, flicker_s=0.5) == (12 * S, 0)


# --- the milestones -------------------------------------------------------------------------------


def test_in_range_and_on_screen_from_packet_cells() -> None:
    fld = ss.Field(scenario())
    # the GM reaches (107, 100) at 1.5 + 7 x 0.15 = 2.55 s: within 3 of A at (110, 100)
    assert cp.first_within(fld, A, 1 * S, 5 * S, 3) == int(2.55 * S)
    # melee: the client's last step (108 -> 109) lands at 3.15
    assert cp.first_within(fld, A, 1 * S, 5 * S, 1) == int(3.15 * S)
    # A is 10 cells off at the entry; the footprint is +-8: on screen once the GM is at 102 (1.8 s)
    assert cp.onscreen_time(fld, A, 1 * S, 5 * S, FP) == int(1.8 * S)
    assert cp.onscreen_time(fld, B, 4 * S, 7 * S, FP) is None  # (-9, 10) after A's kill: off


def test_detect_needs_a_box_at_the_lagged_projection() -> None:
    fld = ss.Field(scenario())
    paths = cp.Paths(fld)
    # at 1.4 s (= 2.0 - LAG_S) the GM still stands at 100: A projects to (600, 300)
    frames = [(int(1.9 * S), [[100.0, 100.0, 120.0, 120.0, 0.9, "monster"]]),
              (int(2.0 * S), [[590.0, 280.0, 610.0, 300.0, 0.9, "monster"]]),
              (int(2.1 * S), [[590.0, 280.0, 610.0, 300.0, 0.9, "monster"]])]  # fmt: skip
    ft = [f[0] for f in frames]
    assert cp.detect_time(frames, ft, paths, A, 1 * S, 5 * S, fake_project) == 2 * S
    # an item box at the same place is no detection
    items = [(int(2.0 * S), [[590.0, 280.0, 610.0, 300.0, 0.9, "item"]])]
    assert cp.detect_time(items, [items[0][0]], paths, A, 1 * S, 5 * S, fake_project) is None
    # without the lag the projection is the walking GM's: A reads ~6.7 cells off at 2.0, 6 at 2.1
    # (33 / 40 px from the box): the lag is what puts the box on it
    assert cp.detect_time(frames, ft, paths, A, 1 * S, 5 * S, fake_project, px=20.0) == 2 * S
    assert cp.detect_time(frames, ft, paths, A, 1 * S, 5 * S, fake_project, lag_s=0.0,
                          px=20.0) is None  # fmt: skip


def test_pointer_reach_and_approach_start() -> None:
    fld = ss.Field(scenario())
    paths = cp.Paths(fld)
    # A's body point at t - 0.6 while the GM stands (t < 2.1): (600, 300 + PTR_DV); a sample
    # whose t - 0.6 precedes the entry (1.0) shows no A yet and is skipped
    ptr = cp.Pointer(t=[int(1.5 * S), int(1.7 * S), int(1.9 * S), int(2.0 * S), int(2.05 * S)],
                     u=[600.0, 300.0, 450.0, 560.0, 595.0],
                     v=[291.0, 300.0, 300.0, 300.0, 291.0])  # fmt: skip
    t_reach, t_start = cp.pointer_times(ptr, paths, A, 1 * S, 5 * S, fake_project)
    assert t_reach == 2 * S  # 41 px away (<= PTR_PX); the 1.5 sample sat on it before A showed
    assert t_start == int(1.9 * S)  # the last sample >= PTR_FAR_PX (120 px) away: 150 px
    assert cp.pointer_times(ptr, paths, B, 4 * S, 7 * S, fake_project) == (None, None)


def test_bot_selection_by_cell_and_by_engaged_track() -> None:
    evs = scenario()
    fld = ss.Field(evs)
    paths = cp.Paths(fld)
    bot = [{"t_ns": int(2.2 * S), "kind": "dispatch", "track": 3, "valid": True,
            "cell": [109.6, 100.4]},
           {"t_ns": int(2.3 * S), "kind": "dispatch", "track": 4, "valid": True,
            "cell": [130.0, 130.0]},
           {"t_ns": int(2.4 * S), "kind": "dispatch", "track": 5, "valid": False,
            "cell": [110.0, 100.0]},
           {"t_ns": int(2.5 * S), "kind": "preempt", "to": 7, "from": 3}]  # fmt: skip
    engs = [{"track": 7, "t_first_click": int(2.9 * S), "pred_cell": [110.0, 101.0]}]
    sels = cp.bot_selections(fld, bot, engs, paths)
    assert (int(2.2 * S), A, "cell", 3) in sels
    assert (int(2.5 * S), A, "track", 7) in sels  # the preempted track's engagement attacked A
    assert all(t != int(2.3 * S) and t != int(2.4 * S) for t, _g, _h, _k in sels)
    assert cp.selection_agreement([*sels, (int(2.2 * S), A, "track", 3)]) == {
        "both": 1,
        "agree": 1.0,
    }


def test_milestones_of_a_killed_free_target() -> None:
    fld = ss.Field(scenario())
    frames = [(int(2.0 * S), [[590.0, 280.0, 610.0, 300.0, 0.9, "monster"]])]
    inp = inputs(fld, frames=frames, selections=[(int(2.2 * S), A, "cell", 3)],
                 clicks=[int(1.4 * S), int(2.9 * S)])  # fmt: skip
    m = cp.milestones(fld, inp, A, 1 * S, int(4.2 * S), 1, 20 * S)
    assert m["t_enter"] == 1 * S
    assert m["t_onscreen"] == int(1.8 * S)
    assert m["t_detect"] == 2 * S
    assert m["t_notice"] == int(2.2 * S)
    assert m["t_turn"] == int(1.5 * S)
    assert m["t_inrange3"] == int(2.55 * S)
    assert m["t_click"] == int(2.9 * S)  # the last click <= T_REQ before the request
    assert m["t_attack_req"] == 3 * S
    assert m["t_inrange1"] == int(3.15 * S)
    assert m["t_hit"] == int(3.3 * S)
    assert m["t_kill"] == int(4.2 * S)
    assert (m["n_hits"], m["n_misses"], m["dist_turn"]) == (1, 0, 10)
    rows = [m]
    tab = cp.phase_table(rows)
    assert tab["enter->attack_req"]["p50"] == 2.0
    assert tab["inrange3->click"]["p50"] == 0.35
    assert tab["click->hit"]["p50"] == 0.4
    assert cp.orders(rows) == {"turn > notice > inrange3 > click > attack_req > inrange1 > hit > "
                               "kill": 1}  # fmt: skip
    hk = cp.hit_kill(rows)
    assert (hk["kills"], hk["hits_per_kill"], hk["hit_to_kill_s"]["p50"]) == (1, 1.0, 0.9)


def test_a_kill_needs_an_act_of_ours() -> None:
    evs = [e for e in scenario() if e["type"] not in ("act", "attack_request")]
    fld = ss.Field(evs)
    m = cp.milestones(fld, inputs(fld), A, 1 * S, int(4.2 * S), 1, 20 * S)
    assert m["t_hit"] is None and m["t_kill"] is None and m["t_attack_req"] is None


# --- the decomposition ----------------------------------------------------------------------------


def test_loot_window_is_the_pickup_chain_after_a_kill() -> None:
    evs = scenario()
    assert cp.loot_windows(evs, [int(4.2 * S)]) == [(int(4.2 * S), int(6.5 * S))]
    assert cp.loot_windows(evs, [int(4.2 * S)], gap_s=1.0) == [(int(4.2 * S), 5 * S)]
    assert cp.loot_windows(evs, [int(20 * S)]) == []


def test_decomposition_labels_and_sums_to_the_in_view_time() -> None:
    evs = scenario()
    fld = ss.Field(evs)
    frames = [(int(2.0 * S), [[590.0, 280.0, 610.0, 300.0, 0.9, "monster"]])]
    inp = inputs(fld, frames=frames, selections=[(int(2.2 * S), A, "cell", 3)],
                 clicks=[int(2.9 * S)])  # fmt: skip
    lives = {(g, a): cp.milestones(fld, inp, g, a, b, r, 20 * S, horizon_s=None)
             for a, b, g, r in fld.tlives}  # fmt: skip
    s = ss.scan(fld, 0, 20 * S, None)
    kills = ss.kill_times(evs, 0, 20 * S)
    s.kills = len(kills)
    dec = cp.decompose(fld, s, lives, cp.loot_windows(evs, kills))
    sec = dec["seconds"]
    # A: in view 1.0 -> 4.2; B: 4.0 -> 7.0 (the loot chain covers 4.2 -> 6.5)
    assert dec["samples_in_view"] == 24  # 1.0 .. 6.75 every 0.25 s
    assert sec == {
        "UNNOTICED_OFFSCREEN|killed": 0.5,  # 1.0, 1.25: before the turn at 1.5
        "TURNED|killed": 1.25,  # 1.5 .. 2.5: 10, 9, 7, 5, 4 cells off
        "IN_RANGE|killed": 0.25,  # 2.75: 2 cells off, the click comes at 2.9
        "CLICKED_WALK_UP|killed": 0.25,  # 3.0: clicked, still 2 cells off
        "CLICKED_REACH|killed": 0.25,  # 3.25: 1 cell, the hit lands at 3.3
        "FIGHT|killed": 0.75,  # 3.5 .. 4.0 (B in view at 4.0: A outranks it)
        "LOOT|loot": 2.5,  # 4.25 .. 6.5: the pickup chain after A's kill, B unnoticed
        "UNNOTICED_OFFSCREEN|never_attacked": 0.25,  # 6.75: B, (-9, 10) off the footprint
    }
    assert dec["moving"]["TURNED|killed"] == 5  # the walk runs 1.5 -> 2.7
    pk = cp.per_kill(dec, 1)
    assert pk["sum_check_s"] == 0.0
    assert pk["in_view_s_per_kill"] == round(24 * 0.25, 2)
    assert ss.presence_summary([s])["some_s_per_kill"] == pk["in_view_s_per_kill"]


# --- real sessions --------------------------------------------------------------------------------


def _need(*sids: str) -> None:
    for sid in sids:
        if not (DEMO / sid / "packets.jsonl.gz").exists():
            pytest.skip(f"banked session {sid} absent")


@pytest.mark.skipif(not (DEMO / BATT).exists(), reason="Batt's demo is not banked here")
def test_real_batt_cohort_decomposition_and_one_attack() -> None:
    _need(BATT)
    r = cp.analyse(BATT, DEMO)
    s = cp.summary([r])
    # the cohort is turn_toward's: 40 free entries, 78 % attacked within 10 s
    assert s["cohort_check"]["free_n"] == 40 == r.turn_toward["free_any"]["n"]
    assert s["cohort_check"]["attacked_10s"] == 0.78 == r.turn_toward["free_any"]["attacked_10s"]
    # the decomposition sums to presence_summary's 6.8 s per kill (50 kills)
    assert r.kills == 50
    assert s["decomposition"]["sum_check_s"] == 0.0
    assert s["decomposition"]["in_view_s_per_kill"] == r.some_s_per_kill == 6.8
    # one of his attacks, checked by hand on the packets and his input log
    m = next(x for x in r.rows if x["gid"] == HAND_BATT["gid"] and x["t_enter"] == HAND_BATT["a"])
    for k, v in HAND_BATT["ms"].items():
        assert m[k] == v, k


@pytest.mark.skipif(not (DEMO / BOT).exists(), reason="the v37 run is not banked here")
def test_real_bot_cohort_and_one_engagement() -> None:
    _need(BOT)
    r = cp.analyse(BOT, DEMO)
    s = cp.summary([r])
    assert s["cohort_check"]["match"] and s["cohort_check"]["free_n"] == 157
    assert s["cohort_check"]["attacked_10s"] == r.turn_toward["free_any"]["attacked_10s"] == 0.28
    assert s["decomposition"]["sum_check_s"] == 0.0
    # presence_summary rounds to 0.1 s: 14.05 vs 14.1
    assert abs(s["decomposition"]["in_view_s_per_kill"] - r.some_s_per_kill) <= 0.05
    m = next(x for x in r.rows if x["gid"] == HAND_BOT["gid"] and x["t_enter"] == HAND_BOT["a"])
    for k, v in HAND_BOT["ms"].items():
        assert m[k] == v, k


# Checked by hand on the packets (2026-10-18). Batt: a Pupa (3 hits) entering at (199, 312) while
# he walked south-west: his walk command at +0.213 s (to 209,306) is within 45 deg of its bearing
# from his cell then (211, 299); his click +5.454 s, the client's own walk-up request (199, 313)
# +5.483, the GM within 3 at +5.843 ((199, 315): grid +5.85) and 1 at +6.143 (grid +6.15); the
# attack request +6.083; damage 181 / 183 / 183 at +6.224 / 7.529 / 8.819; died +9.725.
_A1 = 860153672155472
HAND_BATT: dict = {"gid": 110019353, "a": _A1, "ms": {
    "t_turn": _A1 + 213340539, "t_click": 860159126493716, "t_attack_req": 860159754836687,
    "t_inrange3": _A1 + int(5.85 * S), "t_inrange1": _A1 + int(6.15 * S),
    "t_hit": 860159896581122, "t_kill": 860163396679199, "n_hits": 3}}  # fmt: skip
# The bot (v37): a Poring entering at (300, 71 -> 72); its SEARCH walk at +0.477 s (295,82 -> 77)
# is within 45 deg of it (a coincidental turn); the bot's dispatch of track 25 at +1.12 s had its
# cell 3 cells north (not matched: track churn), its retarget to track 27 (the engaged one) at
# +3.219 is the notice; strike click +3.832, the client's walk-up (300, 73) +3.912, within 3 at
# +4.123 ((300, 75): grid +4.15), within 1 at +4.423 (grid +4.45), the attack request +4.345,
# damage 191 at +4.516, died +5.414.
_A2 = 1038972108351589
HAND_BOT: dict = {"gid": 110054342, "a": _A2, "ms": {
    "t_turn": 1038972585157720, "t_notice": 1038975326901370, "t_click": 1038975940283407,
    "t_attack_req": 1038976453285534, "t_inrange3": _A2 + int(4.15 * S),
    "t_inrange1": _A2 + int(4.45 * S), "t_hit": 1038976624214638, "t_kill": 1038977522033284,
    "n_hits": 1}}  # fmt: skip
