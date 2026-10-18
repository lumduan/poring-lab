"""conversion_misses: the CONVERSION study's misses half (why a FREE target in view is not
attacked within 10 s), on synthetic packets / frames / bot logs, plus REAL-session positive cases
checked by hand in the logs (skipped when the banked sessions are absent)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import conversion_misses as cm  # noqa: E402
import flow_judge as fj  # noqa: E402
import search_study as ss  # noqa: E402

S = 10**9
A, B = 110000001, 110000002
DEMO = Path("/dev/shm/poring-lab-demo")
BATT = "20261016T093835-demo-human-demo"
V37 = "20261018T112036-demo-hunt-flow37"
V36 = "20261018T070558-demo-hunt-flow36"
GM_CELL = (50, 50)


def ev(t: float, typ: str, **kw: object) -> dict:
    return {"type": typ, "t_mono_ns": int(t * S), **kw}


def appear(t: float, g: int, x: int, y: int, job: int = 1002) -> dict:
    return ev(t, "entity_appear", objtype=5, gid=g, x=x, y=y, job=job)


def bev(t: float, kind: str, **kw: object) -> dict:
    return {"t_ns": int(t * S), "kind": kind, **kw}


def screen() -> cm.Screen:
    """A synthetic camera: 32 px per cell across, 24 px per cell up, the GM at (640, 360);
    the footprint |dx| <= 12, |dy| <= 10."""
    offs = frozenset((dx, dy) for dx in range(-12, 13) for dy in range(-10, 11))

    def pick(origin: Any, pts: Any) -> Any:
        p = np.atleast_2d(np.asarray(pts, dtype=float))
        return np.stack([np.round((p[:, 0] - 640) / 32), np.round((360 - p[:, 1]) / 24)], axis=1)

    return cm.Screen(offs, pick)


def box(dx: int, dy: int, side: float = 30.0) -> list[Any]:
    u, vf = 640 + 32 * dx, 360 - 24 * dy + 4  # observe() lifts the foot 4 px before the pick
    return [u - side / 2, vf - side, u + side / 2, vf, 0.9, "monster"]


def frames(t1: float, every: list[list[Any]] | None = None,
           until: float = 99.0) -> list[tuple[int, Any]]:  # fmt: skip
    """A frame every 0.3 s on [0, t1): ``every`` drawn on frames before ``until``."""
    out = []
    t = 0.0
    while t < t1:
        bx = list(every or []) if t < until else []
        out.append((int(t * S), bx))
        t = round(t + 0.3, 3)
    return out


def run(events: list[dict], frs: list[tuple[int, Any]], bot: tuple[dict, ...] = (),
        engs: tuple[dict, ...] = (), clicks: tuple[dict, ...] = ()) -> list[dict]:  # fmt: skip
    fld = ss.Field(events)
    scr = screen()
    obs = cm.observe(frs, fld, scr, lag_s=0.0)
    st = cm.bot_state(list(bot), list(engs), list(clicks), fld, 60 * S, obs)
    rows = [r for r in cm.free_entries(fld, 0, 60 * S) if r["latk"] is None]
    return [cm.classify(r, fld, scr, obs, st, lag_s=0.0) for r in rows]


BASE = [ev(0.0, "map_change", x=50, y=50)]


# --- the cohort -----------------------------------------------------------------------------------


def test_the_cohort_is_turn_toward_s_free_any_row_for_row() -> None:
    events = [*BASE, appear(1.0, A, 60, 50),  # free; attacked at 4 s, dead at 5 s
              ev(4.0, "attack_request", target_gid=A), ev(5.0, "entity_vanish", gid=A, reason=1),
              appear(20.0, B, 58, 50), appear(20.5, 110000003, 45, 50),  # B free, C not (B near)
              ev(31.0, "attack_request", target_gid=B)]  # fmt: skip
    fld = ss.Field(events)
    rows = cm.free_entries(fld, 0, 60 * S)
    tt = ss.turn_toward(fld, 0, 60 * S)["free_any"]
    assert len(rows) == tt["n"] == 2
    attacked = sum(r["latk"] is not None for r in rows)
    assert attacked / len(rows) == tt["attacked_10s"] == 0.5
    late = next(r for r in rows if r["gid"] == B)
    assert late["latk"] is None and late["latk_any"] == 11.0


# --- the decision list ----------------------------------------------------------------------------


def test_a_target_outside_the_camera_footprint_is_off_screen() -> None:
    events = [*BASE, appear(1.0, A, 52, 63)]  # dy 13 > the footprint's 10, inside the view (14)
    (c,) = run(events, frames(12.0))
    assert c["cause"] == "off_screen" and c["on_s"] == 0


def test_on_screen_only_while_the_bot_fights_another_mob_is_busy() -> None:
    # B (a non-target: A stays free) is engaged from 0.5 s, dies at 11.5 s, looted to 15 s
    events = [*BASE, appear(0.2, B, 49, 49, job=1018), ev(0.6, "attack_request", target_gid=B),
              appear(4.0, A, 60, 50), ev(11.5, "entity_vanish", gid=B, reason=1)]  # fmt: skip
    engs = [{"k": 0, "track": 9, "t_first_click": int(0.5 * S), "t_end": int(15.0 * S),
             "loot": {"s": 0.3}}]  # fmt: skip
    clicks = [{"t": int(0.5 * S), "kind": "strike", "track": 9}]
    (c,) = run(events, frames(16.0, every=[box(10, 0)]), engs=tuple(engs), clicks=tuple(clicks))
    assert c["cause"] == "busy:fight" and c["free_on_s"] < 1.0
    assert "converting_other" in c["flags"] and c["idle_s"] < 1.0


def test_on_screen_with_the_bot_free_and_no_box_is_undetected() -> None:
    (c,) = run([*BASE, appear(1.0, A, 60, 50)], frames(12.0))
    assert c["cause"] == "undetected" and c["on_s"] > 9


def test_a_floor_item_sized_box_is_gated() -> None:
    (c,) = run([*BASE, appear(1.0, A, 60, 50)], frames(12.0, every=[box(10, 0, side=12.0)]))
    assert c["cause"] == "gated:min_box_px"


def test_a_creamy_sized_box_is_gated_by_the_size_gate() -> None:
    (c,) = run([*BASE, appear(1.0, A, 60, 50)], frames(12.0, every=[box(10, 0, side=52.0)]))
    assert c["cause"] == "gated:creamy_size"


def test_a_passing_box_the_bot_never_pursued_is_never_attended_none() -> None:
    (c,) = run([*BASE, appear(1.0, A, 60, 50)], frames(12.0, every=[box(10, 0)]))
    assert c["cause"] == "never_attended:none" and c["first_pass_s"] is not None


def test_pursuing_another_target_is_never_attended_pursuing_target() -> None:
    events = [*BASE, appear(1.0, A, 60, 50), appear(2.0, B, 40, 50)]  # B enters 10 cells west
    bot = [bev(2.5, "dispatch", track=7, rank=0, q_len=1, valid=True, cell=[40.0, 50.0])]
    (c,) = [x for x in run(events, frames(12.0, every=[box(10, 0), box(-10, 0)]), bot=tuple(bot))
            if x["gid"] == A]  # fmt: skip
    assert c["cause"] == "never_attended:pursuing_target"


def test_a_pursued_target_whose_boxes_stop_is_lost_undetected() -> None:
    events = [*BASE, appear(1.0, A, 60, 50)]
    bot = [bev(1.5, "dispatch", track=5, rank=0, q_len=1, valid=True, cell=[60.0, 50.0]),
           bev(6.5, "target_lost", track=5)]  # fmt: skip
    (c,) = run(events, frames(12.0, every=[box(10, 0)], until=4.0), bot=tuple(bot))
    assert c["cause"] == "attended:target_lost:undetected" and c["pursued"]


def test_a_tracker_split_of_the_same_monster_does_not_end_the_attention() -> None:
    events = [*BASE, appear(1.0, A, 60, 50), appear(2.0, B, 40, 50)]
    bot = [
        bev(1.5, "dispatch", track=5, rank=0, q_len=1, valid=True, cell=[60.0, 50.0]),
        bev(3.0, "retarget", **{"from": 5, "to": 6}),
        bev(3.1, "dispatch", track=6, rank=0, q_len=2, valid=False, cell=[60.0, 50.0]),
        bev(5.0, "retarget", **{"from": 6, "to": 7}),
        bev(5.1, "dispatch", track=7, rank=1, q_len=2, valid=False, cell=[40.0, 50.0]),
    ]
    (c,) = [x for x in run(events, frames(12.0, every=[box(10, 0), box(-10, 0)]), bot=tuple(bot))
            if x["gid"] == A]  # fmt: skip
    assert c["cause"] == "attended:retarget_away:target"


def test_attacked_after_10_s_is_late_with_its_delay_cause() -> None:
    events = [*BASE, appear(1.0, A, 60, 50), ev(13.5, "attack_request", target_gid=A)]
    bot = [bev(1.5, "dispatch", track=5, rank=0, q_len=1, valid=True, cell=[60.0, 50.0])]
    (c,) = run(events, frames(14.0, every=[box(10, 0)]), bot=tuple(bot))
    assert c["cause"] == "attacked_late" and c["delay"] == "attended:steering"
    assert c["late_s"] == 2.5


def test_pursuit_segments_follow_the_executor_s_target() -> None:
    bot = [
        bev(1.0, "dispatch", track=1, valid=False, cell=[0, 0]),
        bev(1.1, "dispatch", track=2, valid=True, cell=[0, 0]),
        bev(2.0, "preempt", to=3, **{"from": 2}),
        bev(3.0, "target_lost", track=3),
        bev(4.0, "zone_plan", track=4),
        bev(5.0, "target_dropped", track=4, why="no_path"),
    ]
    segs = cm.pursuit_segments(bot, 10 * S)
    assert [(s[2], s[3]) for s in segs] == [(2, "preempt_away"), (3, "target_lost"),
                                            (4, "dropped:no_path")]  # fmt: skip


def test_attention_end_skips_a_switch_to_another_track_of_the_same_gid() -> None:
    segs = [(0, 2 * S, 1, "retarget_away"), (2 * S, 4 * S, 2, "target_lost")]
    assert cm.attention_end(segs, {1: A, 2: A}, A, 9 * S) == ("target_lost", None)
    assert cm.attention_end(segs, {1: A, 2: B}, A, 9 * S) == ("retarget_away", B)
    assert cm.attention_end(segs, {1: A}, A, 1 * S) == ("open", None)


def test_hover_cause_names_the_first_clicked_hover_s_delay() -> None:
    c_ok = {"clicked": 1, "read": "direct", "path": "direct", "arm_eff": "C", "fallback": None}
    fb = {**c_ok, "arm_eff": "A", "fallback": "species_unsure"}
    rr = {"clicked": None, "read": "unknown", "path": "std"}
    assert cm.hover_cause([c_ok])[0] == "arm_C"  # type: ignore[index]
    assert cm.hover_cause([fb])[0] == "fallback:species_unsure"  # type: ignore[index]
    assert cm.hover_cause([rr, c_ok])[0] == "reread:unknown"  # type: ignore[index]
    assert cm.hover_cause([rr]) is None


def test_the_packet_only_list_sees_busy_attack_loot_and_left_view() -> None:
    scr = screen()
    events = [
        *BASE,
        appear(1.0, A, 60, 50),
        ev(3.0, "attack_request", target_gid=99),
        ev(10.0, "entity_vanish", gid=A, reason=0),
        appear(20.0, B, 60, 50),
        ev(22.0, "pickup_request", floor_id=1),
        ev(30.0, "entity_vanish", gid=B, reason=0),
        appear(40.0, 110000003, 60, 50),
        ev(42.0, "entity_vanish", gid=110000003, reason=0),
    ]
    fld = ss.Field(events)
    ft = [f[0] for f in frames(60.0)]
    got = [cm.classify_packets(r, fld, scr, ft) for r in cm.free_entries(fld, 0, 60 * S)]
    assert got == ["busy_attack", "busy_loot", "left_view"]


def test_cause_table_ranks_by_idle_seconds_per_kill() -> None:
    rows = [{"cause": "x", "inview_s": 10.0, "idle_s": 2.0},
            {"cause": "y", "inview_s": 5.0, "idle_s": 5.0}]  # fmt: skip
    t = cm.cause_table(rows, kills=5, n_free=10)
    assert list(t) == ["y", "x"] and t["y"]["idle_s_per_kill"] == 1.0
    assert t["x"]["s_per_kill"] == 2.0 and t["x"]["share_free"] == 0.1


def test_strike_landing_and_a_false_death() -> None:
    events = [*BASE, appear(0.5, A, 60, 50), ev(2.0, "attack_request", target_gid=A),
              ev(3.0, "entity_vanish", gid=A, reason=1),
              appear(10.0, B, 55, 50), ev(10.5, "entity_appear", objtype=5, gid=B, x=56, y=50,
                                          job=1002)]  # fmt: skip
    clicks = [{"t": int(1.9 * S), "kind": "strike", "track": 1},
              {"t": int(11.0 * S), "kind": "strike", "track": 2}]  # fmt: skip
    bot = [bev(10.6, "dispatch", track=2, valid=True, cell=[55.0, 50.0])]
    engs = [{"k": 0, "track": 1, "t_first_click": int(1.9 * S), "t_end": int(5 * S),
             "result": "dead", "loot": {"s": 1.0}},
            {"k": 1, "track": 2, "t_first_click": int(11 * S), "t_end": int(14 * S),
             "result": "dead", "loot": {"s": 2.5}}]  # fmt: skip
    fld = ss.Field(events)
    st = cm.bot_state(bot, engs, clicks, fld, 60 * S)
    out = cm.strike_landing(clicks, bot, engs, fld, st, 0, 60 * S)
    assert out["gm_standing/mob_still"] == {"n": 1, "landed": 1, "share": 1.0}
    assert out["gm_standing/mob_walking"]["landed"] == 0  # B moved 55 -> 56 in the 1 s before
    assert out["dead_calls"] == {"true": 1, "false": 1, "false_share": 0.5, "false_loot_s": 2.5}


def test_approach_profile_measures_the_closing_and_the_walk() -> None:
    events = [*BASE, appear(1.0, A, 60, 50), ev(4.0, "self_move", x0=50, y0=50, x1=56, y1=50)]
    fld = ss.Field(events)
    out = cm.approach_profile([{"t": int(1 * S), "gid": A, "cause": "x"}], fld)
    assert out["x"]["n"] == 1 and out["x"]["dist_p50"][0] == 10.0
    assert out["x"]["dist_p50"][3] == 4.0 and out["x"]["walked_p50_p90"] == [0.0, 0.0]


# --- REAL sessions: positive cases checked by hand in the logs ------------------------------------


_CACHE: dict[str, Any] = {}


def _real(sid: str, rel: list[float]) -> dict[float, dict]:
    """classify() on the real session's free entries at ``rel`` s after t0 (frames within 40 s
    of them, so the test stays fast)."""
    if not (DEMO / sid / "packets.jsonl.gz").exists():
        pytest.skip(f"{sid} not banked here")
    try:
        scr = cm.load_screen("prt_fild08")
    except (OSError, SystemExit, ValueError) as e:  # the GAT is not extracted here
        pytest.skip(f"no camera / GAT: {e}")
    if sid not in _CACHE:
        sess = ss.load_session(sid, DEMO)
        _CACHE[sid] = (sess, ss.Field(sess.events))
    sess, fld = _CACHE[sid]
    rows = {round((r["t"] - sess.t0) / S, 2): r for r in cm.free_entries(fld, sess.t0, sess.w1)}
    want = {k: rows[k] for k in rel}
    lo = min(r["t"] for r in want.values()) - 40 * S
    hi = max(r["t"] for r in want.values()) + 40 * S
    frs = [f for f in cm.load_frames(sid, DEMO) if lo <= f[0] < hi]
    obs = cm.observe(frs, fld, scr)
    import json

    clicks = [json.loads(x) for x in (DEMO / sid / "clicks.jsonl").read_text().splitlines() if x]
    st = cm.bot_state(sess.bot_events, sess.engagements, clicks, fld, sess.w1, obs)
    return {k: cm.classify(r, fld, scr, obs, st) for k, r in want.items()}


def test_real_v37_lost_while_the_detector_missed_it_on_screen() -> None:
    """v37 +367.98 s, Poring 110054322: dispatched +370.43, a tracker split (track 107 -> 108),
    the tag read refused (no tag, 1.2 s) at +375.13, track 108 lost at +375.97 while the Poring
    stood 5 cells from the GM ON SCREEN with NO box from +375.0; it left the view at +378.06."""
    c = _real(V37, [367.98])[367.98]
    assert c["cause"] == "attended:target_lost:undetected" and c["pursued"]


def test_real_v37_a_strike_with_no_attack_request_then_a_false_death() -> None:
    """v37 +1140.27 s, Poring 110054338: struck while moving at +1144.17 (2 clicks, burst end
    "gone"), NO attack request; the bot's dead rule called it dead, looted 3.76 s, then preempted
    the same Poring again: attack request at +1153.81 (13.5 s)."""
    c = _real(V37, [1140.27])[1140.27]
    assert c["cause"] == "attacked_late" and c["delay"] == "attended:strike_no_request"
    assert c["late_s"] == pytest.approx(3.54, abs=0.01)


def test_real_v37_ignored_while_pursuing_another_target() -> None:
    """v37 +691.38 s, Pupa 110054278 (14 cells, on screen 2.8 s): the bot dispatched track 223 at
    +693.82 -- Lunatic 110054273 -- and never tracked the Pupa, which left the view at +695.04."""
    c = _real(V37, [691.38])[691.38]
    assert c["cause"] == "never_attended:pursuing_target" and "left_view" in c["flags"]


def test_real_batt_left_view_entries_by_the_packet_list() -> None:
    if not (DEMO / BATT / "packets.jsonl.gz").exists():
        pytest.skip(f"{BATT} not banked here")
    try:
        scr = cm.load_screen("prt_fild08")
    except (OSError, SystemExit, ValueError) as e:
        pytest.skip(f"no camera / GAT: {e}")
    sess = ss.load_session(BATT, DEMO)
    fld = ss.Field(sess.events)
    rows = [r for r in cm.free_entries(fld, sess.t0, sess.w1) if r["latk"] is None]
    ft = [f[0] for f in cm.load_frames(BATT, DEMO)]
    got = [cm.classify_packets(r, fld, scr, ft) for r in rows]
    assert len(rows) == 9  # turn_toward: 40 free, attacked_10s 0.78
    assert got.count("left_view") + got.count("off_screen") >= 7
    assert all(fj.cheb(r["cell"], r["here"]) >= 12 for r in rows)
