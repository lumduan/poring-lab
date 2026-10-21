"""regen_walk.py (3.96f): the regen trial's offline judge, on a synthetic trial."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import regen_walk as rw  # noqa: E402

S = 10**9


def pk(t: float, **kw: object) -> dict:
    return {"t_mono_ns": int(t * S), **kw}


def hp(t: float, v: int) -> dict:
    return pk(t, type="stat_change", name="hp", value=v)


def rec(t: float, amount: int) -> dict:
    return pk(t, type="recovery", name="hp", var=5, amount=amount)


def test_ticks_reconstruct_the_hp_between_absolute_updates() -> None:
    # an IRP tick (no absolute hp) then a natural tick: the absolute jumps by 155 + 33 -- still a
    # natural tick of 33 over the reconstructed value; a potion (+350) is not regen
    got = rw.ticks([hp(0, 2000), rec(5, 155), hp(6, 2188), hp(7, 2538), hp(12, 2571)])
    assert [(x["kind"], x["amount"]) for x in got] == [("irp", 155), ("natural", 33),
                                                       ("natural", 33)]  # fmt: skip


def test_the_judge_classes_ticks_by_walking() -> None:
    packets = [
        hp(0, 2000),
        rec(10, 155),  # S: IRP while standing
        hp(12, 2188),  # S: natural
        pk(61, type="self_move", x0=268, y0=107, x1=273, y1=107),  # W: 5 cells = 0.75 s
        pk(62, type="self_move", x0=273, y0=107, x1=264, y1=107),  # 9 cells: 62.0 .. 63.35
        hp(63, 2221),  # W: natural while walking
        pk(70, type="act", kind="normal", src_gid=2000002, target_gid=7),  # an attack in W
    ]
    events = [
        {"kind": "phase_end", "cycle": 0, "phase": "S", "t0": 0, "t1": 60 * S},
        {"kind": "phase_end", "cycle": 0, "phase": "W", "t0": 60 * S, "t1": 120 * S},
    ]
    got = rw.judge(events, packets)
    s, w = got["phases"]
    assert (s["irp_ticks"], s["natural_ticks"], s["regen_hp_per_min"]) == (1, 1, 188.0)
    assert (w["irp_ticks"], w["natural_ticks"], w["natural_while_walking"]) == (0, 1, 1)
    assert 0 < w["walking_share"] < 0.05
    assert got["positive_recovery_decoded"] is True
    assert got["irp_while_walking_total"] == 0
    assert got["attacks_in_S_or_W"] == 1


def test_walk_targets_stay_inside_the_checked_box() -> None:
    assert rw.walk_target(268, True) == 273 and rw.walk_target(273, False) == 264
    assert all(258 <= x <= 278 for x in rw.WALK_X)
