"""scripts/lock_study.py (rogue-xmas02.md 4O): each strike gets one class, K / A / B / C / D; the
reader's damage lines match our hits one to one. Synthetic packets in the sessions' own schema."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import lock_study as ls  # noqa: E402

S = 1_000_000_000
US, T1, T2 = 2000002, 110000001, 110000002


def req(t: float, tgt: int) -> dict[str, object]:
    return {"type": "attack_request", "t_mono_ns": int(t * S), "target_gid": tgt}


def act(t: float, tgt: int, dmg: int = 100) -> dict[str, object]:
    return {"type": "act", "t_mono_ns": int(t * S), "src_gid": US, "target_gid": tgt,
            "damage": dmg}  # fmt: skip


def gone(t: float, tgt: int, reason: int) -> dict[str, object]:
    return {"type": "entity_vanish", "t_mono_ns": int(t * S), "gid": tgt, "reason": reason}


def test_our_gid_is_the_one_hitting_our_requested_targets() -> None:
    other = {"type": "act", "t_mono_ns": 5, "src_gid": 7, "target_gid": 99, "damage": 1}
    assert ls.our_gid([req(1, T1), act(1.5, T1), other]) == US


def test_each_class() -> None:
    k = [req(10.1, T1), act(10.5, T1), gone(11.0, T1, 1)]
    assert ls.classify(10 * S, 14 * S, k, US)["class"] == "K"
    a = [req(10.1, T1), act(10.5, T1), gone(20.0, T1, 0)]
    assert ls.classify(10 * S, 14 * S, a, US)["class"] == "A"
    b = [req(10.1, T1), act(10.5, T1, dmg=0), act(15.0, T1), gone(16.0, T1, 1)]
    rb = ls.classify(10 * S, 14 * S, b, US)
    assert rb["class"] == "B" and rb["died_later"] and rb["hit_s"] == 5.0 and rb["unlock_s"] == 4.0
    c = [req(10.1, T1), act(12.0, T2)]  # we hit another monster, never the target
    assert ls.classify(10 * S, 14 * S, c, US)["class"] == "C"
    assert ls.classify(10 * S, 14 * S, [req(13.0, T1)], US)["class"] == "D"  # request too late


def test_strikes_take_the_unlock_before_the_next_strike() -> None:
    events = [{"kind": "strike", "t_ns": 10 * S}, {"kind": "strike", "t_ns": 20 * S},
              {"kind": "unlock", "t_ns": 24 * S}]  # fmt: skip
    out = ls.strikes(events, [req(10.1, T1), req(20.1, T2)], US)
    assert [o["unlock_s"] for o in out] == [None, 4.0]


def test_the_reader_matches_each_hit_once() -> None:
    packets = [act(1.0, T1), act(1.2, T1), act(5.0, T1),
               {"type": "stat_change", "name": "base_exp", "t_mono_ns": 6 * S}]  # fmt: skip
    lines = [{"type": "damage", "t_ns": int(1.3 * S)}, {"type": "damage", "t_ns": int(1.5 * S)}]
    r = ls.reader(packets, lines, US)
    assert (r["our_hits"], r["matched"], r["exp_packets"], r["exp_lines"]) == (3, 2, 1, 0)
    assert r["lag_ms_p50"] == 300


def test_owned_time_and_the_walk_stop_summary() -> None:
    """rogue-xmas02.md 4Q (p10): each strike holds the fight until its unlock, the fight's end or
    the next strike; a walked strike cutting a REAL strike short (a request came) is counted."""
    events = [{"kind": "strike", "t_ns": 10 * S, "end": "walked"},  # no request: class D
              {"kind": "strike", "t_ns": 11 * S, "end": "walked"},  # a request came: cut short
              {"kind": "strike", "t_ns": 13 * S, "end": "bound"},  # D, locked until the unlock
              {"kind": "unlock", "t_ns": int(20.3 * S)},
              {"kind": "strike", "t_ns": 30 * S, "end": "arrow"},
              {"kind": "fight_end", "t_ns": 33 * S}]  # fmt: skip
    # 12.5 is within REQ_S of the 11-s strike only; 13's window holds no request
    out = ls.strikes(events, [req(12.5, T1), req(30.2, T2)], US)
    assert [o["class"] for o in out] == ["D", "C", "D", "C"]
    assert [o["owned_s"] for o in out] == [1.0, 2.0, 7.3, 3.0]
    ws = ls.walk_stop(out)
    assert (ws["walked"], ws["walked_not_d"], ws["d"]) == (2, 1, 2)
    assert ws["d_owned_s_p50"] == 4.15 and ws["d_owned_s_sum"] == 8.3
    # no strike after the last one and no end: the held time is unknown, not infinite
    assert ls.strikes([{"kind": "strike", "t_ns": 5 * S}], [], US)[0]["owned_s"] is None


def test_own_body_strikes_and_the_self_recheck_summary() -> None:
    """rogue-xmas02.md 4R (p11): strikes on the Rogue's own sprite, by class, and the rechecks."""
    assert ls.own_body({"u": 641.0, "v": 312.0}) and ls.own_body({"u": 641.0, "v": 360.0})
    assert not ls.own_body({"u": 675.0, "v": 336.0}) and not ls.own_body({"u": 641.0, "v": 386.0})
    assert not ls.own_body({})  # an old event without a point
    events = [{"kind": "strike", "t_ns": 10 * S, "u": 641.0, "v": 312.0, "by": "scan"},  # D
              {"kind": "strike", "t_ns": 20 * S, "u": 641.0, "v": 360.0, "by": "scan"},  # attacked
              {"kind": "strike", "t_ns": 30 * S, "u": 675.0, "v": 336.0, "by": "scan"},  # not own
              {"kind": "self_recheck", "t_ns": 9 * S, "verdict2": "unknown"},
              {"kind": "self_recheck", "t_ns": 19 * S, "verdict2": "sword"}]  # fmt: skip
    out = ls.strikes(events, [req(20.2, T1), req(30.3, T2)], US)
    assert [o["own_body"] for o in out] == [True, True, False]
    sr = ls.self_recheck(out, events)
    assert sr == {"own_body_strikes": 2, "own_body_d": 1, "own_body_d_lost": 1,
                  "own_body_attacked": 1, "rechecks": 2, "transient": 1,
                  "scan_attacked": 2}  # fmt: skip


def test_far_strikes_by_walking_and_the_retargets() -> None:
    """rogue-xmas02.md 4S (p12): far strikes (2+ cells), walking at the click or not."""
    events = [{"kind": "strike", "t_ns": 10 * S, "rel": [0, -6], "by": "walk_sword"},  # D, walking
              {"kind": "strike", "t_ns": 20 * S, "rel": [3, 1], "by": "box"},  # attacked, still
              {"kind": "strike", "t_ns": 30 * S, "rel": [1, 0], "by": "scan"},  # near
              {"kind": "still_retarget", "t_ns": 9 * S, "verdict": "sword"},
              {"kind": "still_retarget", "t_ns": 15 * S, "verdict": "clear"}]  # fmt: skip
    walk = {"type": "self_move", "t_mono_ns": int(9.5 * S)}
    out = ls.strikes(events, [walk, req(20.3, T1)], US)
    assert [(o["far"], o["walking"]) for o in out] == [(True, True), (True, False), (False, False)]
    fs = ls.far_strikes(out, events)
    assert fs == {"far": 2, "far_d": 1, "far_attacked": 1, "far_d_walking": 1, "far_walking": 1,
                  "retargets": 2, "retarget_lost": 1}  # fmt: skip


def test_r1a_a_strike_through_continued_hits_lost_nothing() -> None:
    """rogue-xmas02.md 4BI (Amendment R, R1-A): a class-D strike counts for R1 only if it LOST an
    attack. Our hits on T1 every 0.47 s go on across the click (study S-R1's kind a): not lost."""
    hits = [act(9.06 + 0.47 * i, T1) for i in range(4)]  # 9.06, 9.53, 10.00 ... 10.47
    r = ls.lost_attack(int(9.8 * S), hits, US)
    assert r == {"lost": False, "reason": "continued", "gid": T1, "before_s": -0.27,
                 "after_s": 0.2, "by": "hit"}  # fmt: skip
    # the target's death within 1.0 s after the click ends the attack, nothing lost (p45 732.5)
    r = ls.lost_attack(10 * S, [act(9.6, T1), gone(10.04, T1, 1)], US)
    assert (r["lost"], r["by"], r["after_s"]) == (False, "death", 0.04)


def test_r1a_lost_when_no_hit_before_or_the_hits_stop() -> None:
    assert ls.lost_attack(10 * S, [], US) == {"lost": True, "reason": "no_hit_before"}
    # the hit before is 1.2 s old: outside the window (kinds b / c: nothing was being hit)
    assert ls.lost_attack(10 * S, [act(8.8, T1), act(10.3, T1)], US)["reason"] == "no_hit_before"
    # hits before, but the next one 1.5 s after the click: the strike broke the attack
    r = ls.lost_attack(10 * S, [act(9.5, T1), act(11.5, T1)], US)
    assert r == {"lost": True, "reason": "stopped", "gids": [T1]}
    # the next hit lands on ANOTHER monster: not the same one, so lost
    assert ls.lost_attack(10 * S, [act(9.5, T1), act(10.4, T2)], US)["lost"]
    # a miss (damage 0) is no hit; a vanish that is not a death (reason 0) is no death
    assert ls.lost_attack(10 * S, [act(9.5, T1), act(10.4, T1, dmg=0)], US)["lost"]
    assert ls.lost_attack(10 * S, [act(9.5, T1), gone(10.4, T1, 0)], US)["lost"]
    # another source's hits are not ours
    other = {"type": "act", "t_mono_ns": int(9.5 * S), "src_gid": 7, "target_gid": T1, "damage": 9}
    assert ls.lost_attack(10 * S, [other, act(10.4, T1)], US)["lost"]
    # two monsters hit before: the one we kept hitting decides
    r = ls.lost_attack(10 * S, [act(9.4, T2), act(9.6, T1), act(10.3, T2)], US)
    assert (r["lost"], r["gid"]) == (False, T2)


def test_r1a_count_beside_the_old_one() -> None:
    """own_body_d stays as scored; own_body_d_lost drops the strikes that lost nothing."""
    events = [{"kind": "strike", "t_ns": 10 * S, "u": 641.0, "v": 312.0, "by": "scan"},  # kind a
              {"kind": "strike", "t_ns": 20 * S, "u": 641.0, "v": 336.0, "by": "loot_sword"},
              {"kind": "strike", "t_ns": 30 * S, "u": 675.0, "v": 336.0,
               "by": "scan"}]  # fmt: skip
    packets = [act(9.6, T1), act(10.07, T1), act(10.54, T1), act(29.5, T2), act(30.3, T2)]
    out = ls.strikes(events, packets, US)
    assert [o["class"] for o in out] == ["D", "D", "D"]
    assert [o["r1a"]["lost"] for o in out] == [False, True, False]
    sr = ls.self_recheck(out, events)
    assert (sr["own_body_d"], sr["own_body_d_lost"]) == (2, 1)
    # a strike that attacked carries no R1-A record
    assert "r1a" not in ls.strikes(events[:1], [req(10.1, T1)], US)[0]


def test_r1_bar_from_the_rate() -> None:
    """Amendment R, 3: lambda per base run, k = the smallest k with P(Poisson(4 lambda) >= k) <=
    0.05. Hand-checked: Poisson(3.0) P(>= 6) = 0.0839, P(>= 7) = 0.0335."""
    b = ls.r1_bar([0, 1, 0, 1, 1, 0, 2, 1])
    assert (b["runs"], b["strikes"], b["lambda"], b["pool_mean"]) == (8, 6, 0.75, 3.0)
    assert (b["k"], b["p_ge_k_minus_1"], b["p_ge_k"]) == (7, 0.0839, 0.0335)
    assert ls.poisson_sf(0, 3.0) == 1.0
    assert abs(ls.poisson_sf(1, 3.0) - (1 - 0.049787068)) < 1e-6
    assert ls.r1_bar([0, 0])["k"] == 1  # no strikes at all: any strike fails
