"""cursor_5b_score.py (cursor-1080.md 5b, Amendments 8 and 9): the four-arm verdict lines."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import cursor_5b_score as c5  # noqa: E402


def run(kills_h: float, **k: Any) -> dict[str, Any]:
    return {"found": True, "minutes": 25.0, "rc": 0, "short": False, "deaths": 0,
            "kills_h": kills_h, **k}  # fmt: skip


def valid(r: dict[str, Any], minutes: float) -> bool:
    return bool(r.get("found")) and r.get("rc") in (0, 130, None)


def test_better_needs_more_than_two_standard_errors() -> None:
    a = [100.0, 104.0, 96.0]
    assert c5.better_line(a, [130.0, 134.0, 126.0])["verdict"] == "PASS"
    assert c5.better_line(a, [104.0, 108.0, 100.0])["verdict"] == "FAIL"  # +4: within 2 SE
    assert c5.better_line(a, [130.0])["verdict"] == "INCONCLUSIVE"
    assert c5.better_line(a, a)["verdict"] == "FAIL"  # equal is not better


def test_an_arm_is_worse_on_deaths_or_errors_and_not_better_on_kills_alone() -> None:
    a = [run(100), run(104), run(96)]
    good = [run(130), run(134), run(126)]
    assert c5.judge(a, good, valid)["verdict"] == "BETTER"
    assert c5.judge(a, [run(130, deaths=1), run(134), run(126)], valid)["verdict"] == "WORSE"
    assert c5.judge(a, [run(130, rc=1), run(134), run(126)], valid)["verdict"] == "WORSE"
    assert c5.judge(a, [run(101), run(103), run(99)], valid)["verdict"] == "NOT BETTER"
    assert c5.judge(a, [run(130)], valid)["verdict"] == "INCONCLUSIVE"
    got = c5.judge(a, good, valid, unknown=0.08)
    assert got["lines"]["unknown"]["verdict"] == "FAIL" and got["verdict"] == "NOT BETTER"
    assert "unknown" not in c5.judge(a, good, valid)["lines"]  # B only


def test_the_box_age_is_the_time_since_the_newest_detection_before_the_strike() -> None:
    det = [1_000_000_000, 2_000_000_000, 3_000_000_000]
    strikes = [
        {"kind": "strike", "by": "box", "t_ns": 2_200_000_000, "end": "damage"},
        {"kind": "strike", "by": "box", "t_ns": 3_700_000_000, "end": "bound"},
        {"kind": "strike", "by": "scan", "t_ns": 2_500_000_000, "end": "damage"},  # not a box's
        {"kind": "strike", "by": "box", "t_ns": 500_000_000, "end": "arrow"},  # none before it
    ]
    ages = c5.box_ages(det, strikes)
    assert [(round(a, 2), e) for a, e in ages] == [(0.2, "damage"), (0.7, "bound")]
    t = c5.age_table(ages)
    assert t["n"] == 2 and t["by_age"]["0-0.25"] == {"n": 1, "damage": 1}
    assert t["by_age"]["0.5-1"] == {"n": 1, "bound": 1} and t["by_age"][">=1"] == {"n": 0}


def test_the_unknown_share_counts_box_target_verdicts() -> None:
    ev = [
        {"kind": "box_target", "verdicts": ["unknown", "sword"]},
        {"kind": "box_target", "verdicts": ["sword"]},
        {"kind": "scan", "verdicts": ["unknown"]},
    ]
    assert c5.cursor_unknown(ev) == (1, 3)
    assert c5.DEFAULT["D"] == ["c5b-D1", "c5b-D2", "c5b-D3"]


def test_a_box_strike_became_an_attack_a_walk_or_nothing_before_the_next_one() -> None:
    import cursor_5b_packets as cp

    s = 10**9
    strikes = [
        {"kind": "strike", "by": "box", "t_ns": 10 * s},  # walk-up, then the attack at 11.2 s
        {"kind": "strike", "by": "box", "t_ns": 20 * s},  # walks only: the click met the ground
        {"kind": "strike", "by": "box", "t_ns": 22 * s},  # its attack comes after 6 s: none
        {"kind": "strike", "by": "scan", "t_ns": 40 * s},  # not a box's
    ]
    walks = [int(10.4 * s), int(20.3 * s), int(21.0 * s)]
    attacks = [int(11.2 * s), int(29.5 * s)]
    det = [int(9.6 * s), int(19.9 * s)]
    got = cp.strike_fates(strikes, attacks, walks, det)
    assert (got["strikes"], got["attacked"], got["walked"], got["none"]) == (3, 1, 1, 1)
    assert got["walks_without_attack"] == 2
    assert got["hover_to_attack_s"]["p50"] == 1.2 and got["box_to_attack_s"]["p50"] == 1.6
    assert cp.merge([got, got])["attack_share"] == round(2 / 6, 3)
