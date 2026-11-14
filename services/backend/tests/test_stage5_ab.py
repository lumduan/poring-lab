"""scripts/stage5_ab.py: section 10's live A/B (live-blocks.md 10.1) -- the stage-4a box (B4)
against the one box with the drink at 50 % and the candies eaten (B5)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import stage5_ab as ab  # noqa: E402


def test_the_series_alternates_b4_and_b5() -> None:
    runs = ab.series("s", 2)
    assert [r.arm for r in runs] == ["B4", "B5", "B5", "B4"]
    assert [r.label for r in runs] == ["s-r01B4", "s-r02B5", "s-r03B5", "s-r04B4"]


def test_both_arms_play_with_the_same_settings_and_only_b5_eats(tmp_path: Path) -> None:
    doc = ab.plan_doc("s", 1, 20, "alternate", tmp_path / "s")
    assert isinstance(doc, dict), doc
    arms = doc["arms"]
    assert "eat" in arms["B5"]["box_plays"] and "eat" not in arms["B4"]["box_plays"]
    assert arms["B5"]["box_eat"] and not arms["B4"]["box_eat"]
    assert arms["B4"]["box_roles"] == arms["B5"]["box_roles"]
    assert doc["vals"]["alarm_fast"] is True and doc["vals"]["alarm_solo"] == 0.7
    assert doc["bar"] is ab.BAR and len(doc["runs"]) == 2


def _sc(label: str, arm: str, pair: int, **kw: object) -> ab.Score5:
    sc = ab.Score5(label, arm, pair, found=True)
    for k, v in kw.items():
        setattr(sc, k, v)
    return sc


def test_the_score_reads_the_eats_the_time_under_50_and_the_alarm() -> None:
    sc = ab.Score5("x", "B5", 1)
    ev = [{"kind": "hp_read", "pct": 60, "t_ns": 0},
          {"kind": "hp_read", "pct": 40, "t_ns": 1_000_000_000},
          {"kind": "hp_read", "pct": 45, "t_ns": 2_000_000_000},
          {"kind": "hp_read", "pct": 70, "t_ns": 9_000_000_000},  # a gap: held at most HOLD_S
          {"kind": "press", "what": "eat", "key": "F6"}, {"kind": "press", "what": "potion"},
          {"kind": "garm_seen", "inside": True}, {"kind": "garm_seen"}]  # fmt: skip
    ab.score_eat(sc, ev)
    assert sc.eats == 1 and sc.garm_inside == 1 and sc.garm_between == 1
    assert sc.hp_s == 1.0 + 1.0 + ab.HOLD_S and sc.under50_s == 1.0 + ab.HOLD_S


def test_deaths_count_over_every_run_that_played_not_only_the_valid_pairs() -> None:
    """Section 7's flaw: a death ended its run early (invalid), so a death line over the valid
    pairs never saw one. Here a short B5 run that died still counts."""
    scores = [
        _sc("r01B4", "B4", 1, minutes=20.0, kills=50, openers=30, hp_s=1000.0, under50_s=300.0),
        _sc("r02B5", "B5", 1, minutes=20.0, kills=52, openers=35, eats=3, hp_s=1000.0,
            under50_s=100.0),
        _sc("r03B5", "B5", 2, minutes=2.0, deaths=1),
        _sc("r04B4", "B4", 2, minutes=20.0, kills=48, openers=31, hp_s=1000.0, under50_s=250.0),
    ]  # fmt: skip
    v = ab.verdict(scores, 20.0)
    assert v["lines"]["deaths"] == {"B4": 0, "B5": 1, "pass": False}
    assert v["verdict"] == "FAIL" and v["pairs_valid"] == 1 and v["invalid"] == ["r03B5"]
    assert v["lines"]["under50"]["pass"] is True and v["lines"]["eat"]["pass"] is True
    assert v["lines"]["kills_h"]["pass"] is None  # one valid pair: not judged


def test_the_bar_passes_on_three_good_pairs() -> None:
    scores = []
    for p in (1, 2, 3):
        scores.append(_sc(f"a{p}", "B4", p, minutes=20.0, kills=50 + p, openers=30, potions=2,
                          hp_s=1000.0, under50_s=300.0))  # fmt: skip
        scores.append(_sc(f"b{p}", "B5", p, minutes=20.0, kills=51 + p, openers=33, potions=5,
                          eats=2, hp_s=1000.0, under50_s=80.0))  # fmt: skip
    v = ab.verdict(scores, 20.0)
    assert v["verdict"] == "PASS", v
    assert v["lines"]["report"]["potion_cost_z_h"] == {"B4": 7200, "B5": 18000}
