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
