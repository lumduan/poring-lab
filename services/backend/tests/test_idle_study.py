"""scripts/idle_study.py: the idle decomposition's pure functions on SYNTHETIC runner events and
packets (the module docstring's mechanisms, one case each), the TRIM rule's estimate, and two
positive cases modelled on a REAL run (4.05 c7, 20261026T170913, measured 2026-10-26): its loot
step at 595 s and its patrol dead end at 1312 s. A last test re-measures c7 when it is banked."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import idle_study as st  # noqa: E402

S = st.NS
DEMO = Path("/dev/shm/poring-lab-demo")
C7 = "20261026T170913-demo-dungeon-rogue-gef_fild10-patrol-P2-c7"
C8 = "20261026T174709-demo-dungeon-rogue-gef_fild10-patrol-P2-c8"


def ns(t: float) -> int:
    return round(t * S)


def ev(t: float, kind: str, **kw: object) -> dict:
    return {"t_ns": ns(t), "kind": kind, **kw}


def hp(t: float, quick: bool = False, pos: object = (10, 10)) -> dict:
    return ev(t, "hp_read", pct=80, quick=quick or None, pos=None if quick else pos)


def loot_step(t0: float, hover_s: float, n_list: int, n_sweep: int, picks: dict[int, int],
              kills: int = 1, sword_at: int | None = None) -> list[dict]:  # fmt: skip
    """A v1 loot step as the runner logs it: one guard_tick read after every hover, a loot click
    after the hover of each rank in ``picks`` (rank -> distance) and its coded wait, a strike
    after the hover ``sword_at`` (then the step ends), the loot_step record at its end."""
    out, t, rank = [], t0, 0
    for k in range(1, n_list + n_sweep + 1):
        t += hover_s
        rank += 1
        out.append(hp(t, quick=True))
        if k in picks:
            d = picks[k]
            out.append(ev(t + 0.01, "loot_click", rel=[d, 0], why="list" if k <= n_list else
                          "sweep"))  # fmt: skip
            t += st.PICK_S + st.PICK_CELL_S * d + 0.05
        if sword_at == k:
            out.append(ev(t + 0.01, "strike", t_end_ns=ns(t + 0.5)))
            t += 0.5
            break
    nl, ns_ = (min(rank, n_list), max(0, rank - n_list))
    out.append(ev(t, "loot_step", ms=round((t - t0) * 1000), hovered=rank, list_hovered=nl,
                  sweep_hovered=ns_, picks=len(picks), list_kills=kills,
                  end="fight" if sword_at else "done"))  # fmt: skip
    return out


# --- the runner's own timeline -------------------------------------------------------------------


def test_ticks_are_the_non_quick_reads_and_fights_run_engage_to_end() -> None:
    e = [hp(1.0), hp(1.2, quick=True), hp(1.4), ev(2.0, "engage", by="box"), ev(3.0, "kill"),
         ev(4.0, "fight_end"), ev(5.0, "engage", by="battle_log"),
         ev(6.0, "press", what="fly")]  # fmt: skip
    assert st.ticks(e) == [1 * S, ns(1.4)]
    assert st.quick_reads(e) == [ns(1.2)]
    f = st.fights(e)
    assert [(x["by"], x["t0"], x["t1"], len(x["kills"])) for x in f] == [
        ("box", 2 * S, 4 * S, 1), ("battle_log", 5 * S, 6 * S, 0)]  # fmt: skip


def test_a_loot_step_s_picks_carry_their_hover_rank_and_coded_wait() -> None:
    e = loot_step(10.0, 0.4, n_list=25, n_sweep=10, picks={1: 0, 6: 1})
    (s,) = st.loot_steps(e)
    assert s["hovered"] == 35 and len(s["reads"]) == 35
    assert [(p["rank"], p["d"]) for p in s["picks"]] == [(1, 0), (6, 1)]
    a, b = s["picks"][1]["wait"]
    assert round((b - a) / S, 2) == st.PICK_S + st.PICK_CELL_S  # sleep(0.45 + 0.2 * d)
    assert s["cut"] == s["reads"][24]  # the list ends with its 25th hover; the sweep follows


def test_trim_keeps_the_first_nine_hovers_and_never_sweeps() -> None:
    # 35 hovers, a pick at ranks 1 and 21: TRIM 9 stops after the 9th hover, loses the 21st
    (s,) = st.loot_steps(loot_step(0.0, 0.4, n_list=25, n_sweep=10, picks={1: 0, 21: 2}))
    span, lost, late = st.trim_cut(s, 9)
    assert span is not None and span[0] == s["reads"][8] and span[1] == s["t1"]
    assert (lost, late) == (1, False)
    # a step of <= 9 hovers is unchanged
    (s2,) = st.loot_steps(loot_step(0.0, 0.4, n_list=7, n_sweep=0, picks={2: 1}))
    assert st.trim_cut(s2, 9) == (None, 0, False)
    # a SWORD found at hover 20: the trimmed step ends at its 9th hover, the strike is not saved
    (s3,) = st.loot_steps(loot_step(0.0, 0.4, n_list=25, n_sweep=0, picks={}, sword_at=20))
    span3, lost3, late3 = st.trim_cut(s3, 9)
    assert span3 == (s3["reads"][8], s3["strike"]) and (lost3, late3) == (0, True)
    # a fight with no kill (an empty list): the sweep alone ran, the trimmed step makes nothing
    (s4,) = st.loot_steps(loot_step(0.0, 0.4, n_list=0, n_sweep=10, picks={}, kills=0))
    assert st.trim_cut(s4, 9)[0] == (s4["t0"], s4["t1"])
    out = st.loot_summary([s, s2, s3, s4], trims=((9, False),))
    assert out["picks"] == 3 and out["picks_by_rank"] == {"<=9": 2, ">9": 1}
    assert out["trim"]["9"]["picks_lost"] == 1 and out["trim"]["9"]["late_swords"] == 1


def test_scans_split_by_verdict_kill_and_stall() -> None:
    e = [hp(0.0), ev(1.0, "engage", by="box"),
         ev(4.0, "scan", purpose="defend", ms=3000, found=None),  # no kill yet: empty, no kill
         ev(4.1, "kill"),
         ev(7.1, "scan", purpose="defend", ms=3000, found=None),  # after the kill
         ev(7.2, "fight_end"),
         ev(9.0, "stall"), ev(12.0, "scan", purpose="defend", ms=2990, found=None),
         ev(20.0, "engage", by="battle_log"),
         ev(21.0, "scan", purpose="defend", ms=1000, found=[600.0, 300.0])]  # fmt: skip
    sp = st.mech_spans(e, 30 * S)
    assert sp["scan_empty_no_kill"] == [(1 * S, 4 * S)]
    assert sp["scan_empty_after_kill"] == [(ns(4.1), ns(7.1))]
    assert sp["stall_scan"] == [(ns(9.01), 12 * S)]
    assert sp["scan_found"] == [(20 * S, 21 * S)]
    assert sp["fight_other"] == [(1 * S, ns(7.2)), (20 * S, 30 * S)]


def test_walk_decision_ui_watch_timer_fly_and_dead_end() -> None:
    e = [hp(0.0), ev(0.9, "walk", clicked=True), hp(1.1), hp(1.3),
         hp(1.5), ev(2.4, "walk", clicked=True),  # the next decision, its tick from 1.5 s
         hp(2.6), hp(3.7),  # a 1.1-s tick with nothing logged: the UI watch
         hp(3.9), ev(4.0, "press", what="fly")]  # fmt: skip
    e += [hp(4.2 + 0.2 * k, pos=None) for k in range(16)] + [hp(7.5)]  # 5 Hz, no position
    e += [ev(10.0 + 0.2 * k, "goal", len=None) for k in range(10)]  # a dead end, 2 s
    e += [ev(20.0, "goal", len=None)]  # a lone skip: its own short span
    sp = st.mech_spans(e, 30 * S)
    assert sp["walk_decision"] == [(0, ns(0.9)), (ns(1.5), ns(2.4))]
    assert sp["walk_timer"][0] == (ns(0.9), ns(1.5))
    assert sp["ui_watch"] == [(ns(2.6), ns(3.7))]
    assert sp["fly_settle"] == [(4 * S, ns(7.5))]  # to the next read WITH a position
    assert sp["patrol_dead_end"] == [(10 * S, ns(12.0)), (20 * S, ns(20.2))]


def test_every_second_lands_in_exactly_one_mechanism_first_of_the_order() -> None:
    segs = [(0, 10 * S, "search"), (10 * S, 20 * S, "idle"), (20 * S, 30 * S, "search")]
    causes = ["search_walk", "idle_inside_search", "search_walk"]
    spans = {"loot_list_hover": [(12 * S, 14 * S)], "walk_decision": [(11 * S, 15 * S)],
             "walk_timer": [(15 * S, 16 * S), (17 * S, 18 * S)]}  # fmt: skip
    out = st.attribute(segs, causes, spans, keep=["idle_inside_search"])
    d = out["idle_inside_search"]
    assert d["loot_list_hover"] == {"s": 2.0, "n": 1}
    assert d["walk_decision"] == {"s": 2.0, "n": 1}  # 11-12 and 14-15: the loot hover wins
    assert d["walk_timer"] == {"s": 2.0, "n": 2}
    assert d["other"]["s"] == 4.0
    assert round(sum(v["s"] for v in d.values()), 6) == 10.0
    assert set(out) == {"idle_inside_search"}


def test_walk_cadence_finds_the_stops_and_the_longer_leg_estimate() -> None:
    def move(t: float, a: tuple[int, int], b: tuple[int, int]) -> dict:
        return {"type": "self_move", "t_mono_ns": ns(t), "x0": a[0], "y0": a[1],
                "x1": b[0], "y1": b[1]}  # fmt: skip

    # three 6-cell walks (0.9 s each) clicked 1.25 s apart: two 0.35-s stops
    pk = [move(0.0, (0, 0), (6, 0)), move(1.25, (6, 0), (12, 0)), move(2.5, (12, 0), (18, 0))]
    segs = [(0, ns(0.9), "search"), (ns(0.9), ns(1.25), "idle"),
            (ns(1.25), ns(2.15), "search"), (ns(2.15), ns(2.5), "idle"),
            (ns(2.5), 4 * S, "search")]  # fmt: skip
    causes = ["search_walk", "idle_inside_search"] * 2 + ["search_walk"]
    evs = [ev(-1.0, "goal", len=12, to=[12, 0]), ev(0.0, "walk", clicked=True, **{"from": [0, 0]},
                                                    to=[7, 0]),
           ev(1.25, "walk", clicked=True, **{"from": [6, 0]}, to=[12, 0])]  # fmt: skip
    w = st.walk_cadence(pk, evs, 0, 4 * S, segs, causes, extend=(1, 3))
    assert w["stops_inside_search"]["short_n"] == 2
    assert w["stops_inside_search"]["short_s"] == 0.7
    assert w["extend_saved_s"] == {"1": 0.3, "3": 0.7}  # min(stop, k x 0.15 s)
    assert w["target_is_goal_share"] == 0.5 and w["click_gap_s_median"] == 1.25


def test_gain_follows_the_time_budget_convention() -> None:
    # 163 kills in 6446.5 s (c5b + c6 + c7 pooled): 91.0 / h; 863.2 s saved -> 105.1 / h
    g = st.gain(163, 6446.5, 863.2)
    assert g == {"kills_h": 91.0, "kills_h_new": 105.1, "gain": 14.1}
    assert st.gain(0, 100.0, 1.0)["gain"] is None


# --- positive cases modelled on a REAL run (4.05 c7, measured 2026-10-26) -------------------------


def test_c7_like_loot_step_the_one_pick_on_our_own_cell_then_34_empty_hovers() -> None:
    """c7's loot step at 595 s (events, measured): list_kills 1, planned 25, 25 list + 10 sweep
    hovers (35 guard_tick reads), ONE pick, on our own cell (rel 0,0: rank 1), 15,166 ms; the
    trimmed step would have stopped 10.75 s earlier. c7 in all: 39 loot steps, 412.4 s, 32
    picks, 29 of them at a hover rank <= 9."""
    e = loot_step(595.0, 0.40, n_list=25, n_sweep=10, picks={1: 0}, kills=1)
    (s,) = st.loot_steps(e)
    assert (s["hovered"], s["list_hovered"], s["sweep_hovered"], len(s["picks"])) == (35, 25, 10, 1)
    span, lost, late = st.trim_cut(s, 9)
    assert span is not None and (lost, late) == (0, False)
    assert 10.0 < (span[1] - span[0]) / S < 11.5  # c7's real step: 10.75 s
    assert s["tail_s"] > 13.0  # c7's: 15.17 s - (0.83 s + its 0.45-s wait) = 13.9 s


def test_c7_like_patrol_dead_end_until_the_idle_watchdog() -> None:
    """c7 at 1312 s (events, measured): standing at 152,309, every patrol waypoint came back with
    no route (412 skip / route-less goal events in 45.8 s), until the IDLE_MAX_S (45 s) watchdog
    pressed a Fly Wing. In c7 the dead ends took 62.8 s of idle inside search (6 spans; 1.40 s
    per kill of its 45 kills)."""
    e = [hp(1312.0 + 0.2 * k) for k in range(230)]
    e += [ev(1312.5 + 0.111 * k, "goal", len=None, wp=k % 80) for k in range(412)]
    e += [ev(1358.4, "stuck", why="idle"), ev(1358.4, "press", what="fly")]
    sp = st.mech_spans(sorted(e, key=lambda x: x["t_ns"]), 1400 * S)
    (dead,) = sp["patrol_dead_end"]
    assert 45.0 < (dead[1] - dead[0]) / S < 46.5


def test_real_c7_when_banked() -> None:
    """Re-measures c7 (skipped where its session files are not banked)."""
    if not (DEMO / C7 / "packets.jsonl.gz").exists():
        pytest.skip(f"{C7} not banked here")
    import time_budget as tb

    e, pk, _man, t0, t1 = tb.load_window(C7, None)
    r = st.study(pk, e, t0, t1)
    assert r["kills"] == 45
    lo = r["loot"]
    assert (lo["steps"], lo["picks"], lo["picks_by_rank"]) == (39, 32, {"<=9": 29, ">9": 3})
    assert lo["trim"]["9"]["picks_lost"] == 3
    assert 250.0 < lo["trim"]["9"]["saved_s"] < 266.0  # measured 258.1 s
    assert 60.0 < r["by_cause"]["idle_inside_search"]["patrol_dead_end"]["s"] < 66.0  # 62.81 s


def test_real_c8_the_rule_read_after_it_was_fixed_keeps_every_pickup() -> None:
    """c8 ended after the TRIM rule (9 hovers, no sweep) was committed on c5b-c7 (760f439,
    18:20:57): all 29 of its pickups came within the first 9 hovers, so the trim would have lost
    none and saved 308.7 s (skipped where c8 is not banked)."""
    if not (DEMO / C8 / "packets.jsonl.gz").exists():
        pytest.skip(f"{C8} not banked here")
    import time_budget as tb

    e, pk, _man, t0, t1 = tb.load_window(C8, None)
    lo = st.study(pk, e, t0, t1)["loot"]
    assert (lo["steps"], lo["picks"], lo["picks_by_rank"]) == (56, 29, {"<=9": 29, ">9": 0})
    assert lo["trim"]["9"]["picks_lost"] == 0
    assert 300.0 < lo["trim"]["9"]["saved_s"] < 318.0  # measured 308.7 s
