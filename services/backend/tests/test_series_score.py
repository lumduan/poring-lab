"""scripts/series_score.py: an A / B series pooled per arm (rogue-xmas02.md 4DD)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_judge as dj  # noqa: E402
import series_score as ss  # noqa: E402

TABLE = {"912": {"sell_oc10": 120}, "722": {"sell_oc10": 4500}, "507": {"sell_oc10": 12}}


def run(kills: int, hours: float, items: list[dict[str, Any]], deaths: int = 0,
        p95: float | None = 22.0, req: int = 300, ign: int = 1) -> dict[str, Any]:  # fmt: skip
    return {"judge": {"kills": kills, "hours": hours, "deaths": deaths, "items": items},
            "speed": None if p95 is None else {"gpu_ms_p95": p95},
            "refusals": {"requests": req, "ignored": ign}}  # fmt: skip


def item(i: int, name: str, **n: int) -> dict[str, Any]:
    return {"item_id": i, "name": name, **{f: n.get(f, 0) for f in (*ss.INCOME, "other", "staged")}}


def test_the_income_rule_is_the_judges() -> None:
    assert ss.INCOME == dj.INCOME  # picked + stolen + snatched: the bot's own gains
    assert ss.COMMON_MAX == 3000


def test_an_arm_pools_counts_over_hours_and_splits_the_rare() -> None:
    runs = [
        run(60, 0.5, [item(912, "item-a", picked=2, snatched=8), item(722, "item-r", picked=1)]),
        run(
            30,
            0.25,
            [item(507, "item-c", stolen=5, other=9, staged=4), item(999, "item-x", picked=1)],
        ),  # fmt: skip
    ]
    got = ss.arm_score(runs, TABLE)
    assert got["kills_h"] == 120.0  # 90 / 0.75 h, not the mean of two rates
    assert got["common_h"] == round((10 * 120 + 5 * 12) / 0.75, 1)  # other / staged: not income
    assert got["gross_oc_h"] == round((10 * 120 + 4500 + 5 * 12) / 0.75, 1)
    assert got["rare"] == {"item-r": 1} and got["unpriced"] == [999]
    assert got["items_h"] == round(17 / 0.75, 1) and got["w1_counts"] == [2, 600]


def test_the_decision_is_4dds_bars() -> None:
    a = ss.arm_score([run(40, 0.25, [item(912, "item-a", picked=50)])] * 4, TABLE)
    b_ok = ss.arm_score([run(42, 0.25, [item(912, "item-a", picked=51)])] * 4, TABLE)
    assert ss.decide(b_ok, a)["verdict"] == "JOIN"  # +5 % kills, more common income
    b_slow = ss.arm_score([run(41, 0.25, [item(912, "item-a", picked=60)])] * 4, TABLE)
    got = ss.decide(b_slow, a)
    assert got["verdict"] == "FLAG" and got["bars"]["D1_kills_h"] is False  # +2.5 % < 3 %
    b_poor = ss.arm_score([run(42, 0.25, [item(912, "item-a", picked=49)])] * 4, TABLE)
    assert ss.decide(b_poor, a)["bars"]["D2_common_h"] is False
    b_dead = ss.arm_score([run(42, 0.25, [item(912, "item-a", picked=51)], deaths=1)] * 4, TABLE)
    assert ss.decide(b_dead, a)["bars"]["harm_deaths"] is False
    b_slowgpu = ss.arm_score([run(42, 0.25, [item(912, "item-a", picked=51)], p95=36.0)] * 4,
                             TABLE)  # fmt: skip
    assert ss.decide(b_slowgpu, a)["bars"]["harm_d1_p95"] is False
    b_unread = ss.arm_score([run(42, 0.25, [item(912, "item-a", picked=51)], p95=None)] * 4,
                            TABLE)  # fmt: skip
    assert ss.decide(b_unread, a)["bars"]["harm_d1_p95"] is False  # an unread run never passes
    three = ss.arm_score([run(42, 0.25, [])] * 3, TABLE)
    assert ss.decide(three, a)["verdict"] == "NO_VERDICT"


def test_mvp_sightings_count_distinct_knights_in_view() -> None:
    import sk_flee_score as sk

    assert ss.KNIGHT == sk.KNIGHT
    pk = [{"type": "entity_appear", "gid": 5, "job": ss.KNIGHT},
          {"type": "entity_appear", "gid": 5, "job": ss.KNIGHT},  # the same one again
          {"type": "entity_appear", "gid": 6, "job": 1002},
          {"type": "entity_vanish", "gid": 7, "job": ss.KNIGHT}]  # fmt: skip
    assert ss.mvp_sightings(pk) == 1
    assert ss.mvp_sightings([]) == 0
