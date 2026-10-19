"""reversals_study (Batt 2026-10-19, decision 3): the reversal attribution, on synthetic packets +
a runner log, plus a REAL-session positive case (skipped when the banked session is absent)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import flow_judge as fj  # noqa: E402
import reversals_study as rs  # noqa: E402

S = 10**9
GM = 2000002
DEMO = Path("/dev/shm/poring-lab-demo")
REAL = "20261019T053131-demo-hunt-flow40"  # v40 run 4 (5.92 reversals / min in flow_judge.json)


def p(t: float, typ: str, **kw: object) -> dict:
    return {"type": typ, "t_mono_ns": int(t * S), **kw}


def b(t: float, kind: str, **kw: object) -> dict:
    return {"kind": kind, "t_ns": int(t * S), **kw}


def leg(t: float, x0: int, y0: int, x1: int, y1: int) -> list[dict]:
    return [p(t, "self_move_request", x=x1, y=y1), p(t, "self_move", x0=x0, y0=y0, x1=x1, y1=y1)]


def scene() -> tuple[list[dict], list[dict], list[dict]]:
    """Search east 10 cells; a target dispatched BEHIND (west) -> the steer reverses; the kill;
    a 2-cell loot leg back east (the loot reverses); the search RESUMES west (a third reversal)."""
    packets = [
        p(0.0, "map_change", x=50, y=50),
        *leg(0.2, 50, 50, 60, 50),  # search east (reaches 60,50 at 1.7 s)
        *leg(3.08, 60, 50, 52, 50),  # steer west to the target (reaches 52,50 at 4.28 s)
        p(4.6, "attack_request", target_gid=7),
        p(4.7, "act", src_gid=GM, target_gid=7, damage=150),
        p(5.0, "entity_vanish", gid=7, reason=1),
        *leg(6.58, 52, 50, 54, 50),  # a loot click 2 cells east
        *leg(8.28, 54, 50, 44, 50),  # the search heading resumed: west
    ]
    bot = [
        b(0.05, "mode", mode="search"),
        b(0.06, "heading_goal", ang=0.0, turn=0.0),
        b(2.8, "dispatch", track=1, valid=True, cell=[50.0, 51.0]),
        b(2.81, "mode", mode="steer"),
        b(4.5, "mode", mode="engaged"),
        b(8.0, "loot_fixed", s=2.0, cell=[52, 50]),
        b(8.01, "engagement", k=0, result="dead"),
        b(8.05, "heading_goal", ang=180.0, turn=180.0),
        b(8.1, "mode", mode="search"),
    ]
    clicks = [
        {"t": int(0.12 * S), "kind": "walk", "why": "search", "to": [60, 50], "at": [50, 50],
         "lead": [0.0, 0.0]},
        {"t": int(3.0 * S), "kind": "walk", "why": "steer", "to": [52, 50], "at": [60, 50]},
        {"t": int(4.5 * S), "kind": "strike", "pred_cell": [51, 50]},
        {"t": int(6.5 * S), "kind": "loot", "cell": [54, 50]},
        {"t": int(8.2 * S), "kind": "walk", "why": "search", "to": [44, 50], "at": [54, 50]},
    ]  # fmt: skip
    return packets, bot, clicks


def test_legs_reconcile_with_heading_metrics_and_each_reversal_is_attributed() -> None:
    packets, bot, clicks = scene()
    ls = rs.attribute(rs.legs(packets, 0, 12 * S), rs.Context(packets, bot, clicks))
    hm = fj.heading_metrics(packets, 0, 12 * S)
    revs = [x for x in ls if x.rev]
    assert len(revs) == 3 and hm["reversals_per_min"] == round(3 / 0.2, 2)
    assert rs.turn_hist(ls) == hm["turn_hist_45"]
    assert [x.cause for x in ls] == ["search:straight", "steer:new_target", "loot", "search:resume"]
    assert [x.mode for x in ls] == ["search", "steer", "loot", "search"]
    assert [x.pkt for x in ls] == ["search", "approach", "post_kill", "post_kill"]
    by_i = {x.i: x for x in ls}
    assert [rs.decision(r, by_i[r.prev]) for r in revs] == [
        "target_behind", "cell_behind", "heading_back"]  # fmt: skip
    assert ls[1].boundary == "new_target" and ls[1].info["start"] and ls[3].boundary == "after_end"
    # the loot leg's NET effect: without it the resume turns from the steer leg (both west)
    assert rs.reversals_without(ls, ()) == 3 and rs.reversals_without(ls, ("loot",)) == 1


def test_mode_minutes_carve_the_loot_step_out_and_sum_to_the_window() -> None:
    _packets, bot, _clicks = scene()
    mm = rs.mode_minutes(rs.mode_track(bot), rs.loot_spans(bot), 0, 12 * S)
    assert mm["loot"] == round(2.0 / 60, 3) and mm["pre"] == round(0.05 / 60, 3)
    assert abs(sum(mm.values()) - 0.2) < 0.002


def test_counts_pool_and_decompose_add_up() -> None:
    packets, bot, clicks = scene()
    ctx = rs.Context(packets, bot, clicks)
    ls = rs.attribute(rs.legs(packets, 0, 12 * S), ctx)
    c = rs.counts(ls, 0.2, rs.mode_minutes(ctx.mt, ctx.loots, 0, 12 * S),
                  rs.window_extra(ctx, 0, 12 * S))  # fmt: skip
    assert sum(c["by_cause"].values()) == c["reversals"] == 3
    assert c["kills"] == 1 and c["engagements"] == 1 and c["net"]["loot"] == 2
    two = rs.summarise(rs.pool([c, c]))
    assert two["reversals_per_min"] == 15.0 and two["by_cause"]["loot"]["n"] == 2
    d = rs.decompose(rs.summarise(c), two)
    assert d["sum"]["observed"] == 0.0 and abs(d["sum"]["total"]) < 0.05


@pytest.mark.skipif(not (DEMO / REAL / "packets.jsonl.gz").exists(),
                    reason="the real session is local only")  # fmt: skip
def test_a_real_run_every_reversal_heading_metrics_counts_is_attributed() -> None:
    import search_study as ss

    s = rs.study(REAL, DEMO)
    sess = ss.load_session(REAL, DEMO)
    hm = fj.heading_metrics(sess.events, sess.t0, sess.w1)
    c = s["counts"]
    mins = (sess.w1 - sess.t0) / S / 60
    # the totals reconcile exactly with flow_judge's ruler on the same window
    assert round(c["reversals"] / mins, 2) == hm["reversals_per_min"]
    assert s["turn_hist_45"] == hm["turn_hist_45"]
    assert round(c["cells"] / mins, 1) == hm["cells_walked_per_min"]
    assert c["rev135"] == hm["turn_hist_45"][3]
    # ... and the attribution covers every one of them, on every axis
    revs = [x for x in s["legs"] if x.rev]
    assert len(revs) == c["reversals"] > 300
    for axis in ("by_cause", "by_mode", "by_boundary", "by_pkt", "by_pair", "by_cause_decision"):
        assert sum(c[axis].values()) == c["reversals"], axis
    assert all(r.cause and r.mode in rs.MODES and r.pkt for r in revs)
    assert rs.reversals_without(s["legs"], ()) == c["reversals"]
    assert abs(sum(c["mode_minutes"].values()) - mins) < 0.01
    # the positive case itself: this run's engagement turns are there to be found
    assert c["by_cause"].get("steer:new_target", 0) > 50 and c["by_cause"].get("loot", 0) > 30
