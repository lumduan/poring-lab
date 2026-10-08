"""scripts/weight_calibrate.py and scripts/weight_resolution.py (loot@1 P1): the packet labels for
calibration frames, and the resolution judge on SIMULATED readouts (each display rule applied to
known server weights). Synthetic item ids and weights only."""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cal = load("weight_calibrate")
res = load("weight_resolution")
S = 1_000_000_000


def stat(t_s: float, var: int, value: int) -> dict[str, Any]:
    return {"type": "stat_change", "t_mono_ns": int(t_s * S), "var": var, "value": value}


def test_frame_names_carry_the_host_clock() -> None:
    assert cal.frame_time_ns(Path("00012-184278636767482.jpg")) == 184278636767482
    assert cal.frame_time_ns(Path("000-route-before.png")) is None


def test_packet_labels_need_multiples_of_ten_and_a_settled_readout() -> None:
    truth = cal.WeightTruth([
        stat(1, 24, 900), stat(1, 25, 20300), stat(10, 24, 901), stat(20, 24, 910),
    ])  # fmt: skip
    settle = int(1.5 * S)
    assert truth.label(int(0.5 * S), settle) is None  # before any value
    assert truth.label(int(2.0 * S), settle) is None  # not settled yet
    assert truth.label(int(5.0 * S), settle) == (90, 2030)
    assert truth.label(int(12.0 * S), settle) is None  # 901: the display rule would decide
    assert truth.label(int(21.0 * S), settle) is None  # 910 changed 1 s ago
    assert truth.label(int(22.0 * S), settle) == (91, 2030)
    assert cal.parse_value(" 90 / 2030") == (90, 2030)


Rows = list[dict[str, Any]]


def simulate(rule: str, start: int, gives: list[int]) -> tuple[Rows, Rows]:
    """Readouts as the client would show them under ``rule``, around steps that give items of
    weight ``gives`` (rAthena units), plus the server's stat_change events."""
    show = res.RULES[rule]
    w, t = start, 1.0
    rows, events = [], [stat(0.5, 24, w)]
    for g in gives:
        before = f"{show(w)}/2030"
        t_before = t
        w += g
        t += 1.0
        events.append(stat(t - 0.5, 24, w))
        rows.append({"before": before, "after": f"{show(w)}/2030", "items": [[9000 + g, 1]],
                     "t_before_ns": int(t_before * S), "t_after_ns": int(t * S)})  # fmt: skip
    return rows, events


WEIGHTS = {9000 + g: g for g in range(1, 41)}


@pytest.mark.parametrize("rule", ["floor", "round", "ceil"])
def test_ten_light_steps_find_the_rule_and_the_resolution(rule: str) -> None:
    rows, events = simulate(rule, 900, [1] * 25)
    steps = res.build_steps(rows, WEIGHTS, res.parse_readout, res.server_weight_at(events))
    out = res.judge(steps)
    assert out["judged"] == 25 and out["display_rules_consistent"] == [rule]
    assert out["readouts_checked_against_server"] == 50
    assert out["move_spacing"] == [10]  # one shown unit per 10 rAthena units, whatever the rule
    first = {"floor": 10, "round": 5, "ceil": 1}[rule]
    assert out["moves_at"][0][0] == first
    assert out["moved_min"] == 1 and out["still_max"] == 1  # a lone light item may or may not move


def test_whole_unit_items_rise_by_exactly_their_weight() -> None:
    """The P1 positive case: items of known weight (multiples of 10) move the number by exactly
    weight / 10 under every rule."""
    rows, events = simulate("floor", 900, [10, 40, 20])
    out = res.judge(res.build_steps(rows, WEIGHTS, res.parse_readout, res.server_weight_at(events)))
    assert out["exact_steps"] == 3 and [r["shown_delta"] for r in out["steps"]] == [1, 4, 2]
    assert out["moves_at"] == [[10, 50, 70]]


def test_without_server_weights_the_rule_is_not_claimed() -> None:
    rows, _ = simulate("floor", 900, [1] * 12)
    for r in rows:
        r.pop("t_before_ns"), r.pop("t_after_ns")
    out = res.judge(res.build_steps(rows, WEIGHTS, res.parse_readout))
    assert out["display_rules_consistent"] is None and out["moves_at"] == [[10]]


def test_unknown_items_and_missing_readouts_are_not_judged() -> None:
    rows = [
        {"before": "90/2030", "after": "91/2030", "items": [[123456, 1]]},
        {"before": "91/2030", "after": None, "items": [[9010, 1]]},
        {"before": "93/2030", "after": "94/2030", "items": [[9010, 1]]},
    ]
    read = lambda v: None if v is None else res.parse_readout(v)  # noqa: E731
    out = res.judge(res.build_steps(rows, WEIGHTS, read))
    assert out["judged"] == 1 and "not in the KB" in out["steps"][0]["note"]
    assert "missing" in out["steps"][1]["note"]
    with pytest.raises(ValueError):
        res.parse_readout("90")


def test_the_plan_names_light_and_whole_unit_items() -> None:
    items = {
        "9101": {"weight": 1, "type": "Ammo", "aegis": "Test_Pebble"},
        "9102": {"weight": 10, "type": "Etc", "aegis": "Test_Goo"},
        "9103": {"weight": 1, "type": "Armor", "aegis": "Test_Blade"},  # not plain: skipped
    }
    text = "\n".join(res.plan(items))
    assert "@item 9101 1" in text and "@item 9102 1" in text and "9103" not in text
    assert math.isclose(res.RULES["round"](905) - res.RULES["floor"](905), 1)
