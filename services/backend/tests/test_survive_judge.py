"""survive_judge.py (3.96): the survival trials' offline judge, on a synthetic trial."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import survive_judge as sj  # noqa: E402

S = 10**9


def pk(t: float, **kw: object) -> dict:
    return {"t_mono_ns": int(t * S), **kw}


def test_a_trial_scored_against_the_server() -> None:
    packets = [
        pk(0.0, type="stat_change", name="max_hp", value=1000),
        pk(0.0, type="stat_change", name="hp", value=1000),
        pk(0.0, type="stat_change", name="sp", value=300),
        pk(1.2, type="stat_change", name="sp", value=270),  # Auto Guard (30), after read 1
        pk(2.0, type="stat_change", name="hp", value=500),  # crosses 55 %
        pk(2.6, type="use_item_result", item_id=504, aid=sj.AID, ok=True),
        pk(2.7, type="use_item_result", item_id=504, aid=123, ok=True),  # someone else's
        pk(2.8, type="stat_change", name="hp", value=900),
        pk(5.0, type="stat_change", name="hp", value=200),
        pk(5.5, type="use_item_result", item_id=601, aid=sj.AID, ok=True),
        pk(9.0, type="stat_change", name="hp", value=1),  # a death reads hp 1 ...
        pk(9.0, type="entity_vanish", gid=sj.AID, reason=1),
    ]  # ... the vanish is the cue
    events = [
        {"t_ns": int(t * S), "kind": "hp_read", "frac": f}
        for t, f in ((1.0, 1.0), (2.5, 0.52), (4.0, 0.88), (6.0, 0.20), (10.0, 0.0))
    ]
    events.append({"t_ns": int(10.5 * S), "kind": "death"})
    out = sj.judge(events, packets, offset_s=0.0)
    # two crossings below 55 %: 1000 -> 500 (a potion 0.6 s later) and 900 -> 200 (the Fly Wing)
    assert out["S2"] == {"crossings_below_55": 2, "answered_within_1_5s": 1, "potions": 1,
                         "potions_above_80": 0}  # fmt: skip
    assert (
        out["S3"]["escapes"] == 1 and out["S3"]["before_death"] and out["S3"]["hp_at_escape"] == 0.2
    )
    assert out["S4"]["casts"] == 1
    assert out["S6"]["server_deaths"] == 1 and out["S6"]["stop_after_s"] == 1.5
    # reads with true HP < 100 %: t=2.5 (500 -> 0.50 vs 0.52), t=4 (900 -> 0.90 vs 0.88), t=6 (0.20)
    assert (
        out["S1"]["n"] == 4
        and out["S1"]["within_5pct"] == 1.0
        and out["S1"]["over_read_share"] == 0.0
    )
    assert out["hp_min"] == 1


def test_maxhp_falls_back_when_no_max_hp_packet_is_in_the_window() -> None:
    packets = [pk(5.0, type="stat_change", name="hp", value=500)]
    events = [
        {"t_ns": int(t * S), "kind": "hp_read", "frac": f} for t, f in ((4.0, 1.0), (6.0, 0.5))
    ]
    assert sj.judge(events, packets, offset_s=0.0)["S1"]["n"] == 0  # no MaxHP: nothing judged
    out = sj.judge(events, packets, offset_s=0.0, max_hp=1000)
    assert out["S1"]["n"] == 1 and out["S1"]["within_5pct"] == 1.0 and out["max_hp"] == 1000
