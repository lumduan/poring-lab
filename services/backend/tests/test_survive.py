"""survive.py (3.96, pre-registered 2026-10-21 18:03): the pure survival rules."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import survive as sv  # noqa: E402


def test_the_rate_needs_half_a_window_and_counts_falling_as_positive() -> None:
    assert sv.rate_hp_s([(0.0, 1.0)], 0.0) is None
    assert sv.rate_hp_s([(0.0, 1.0), (0.5, 0.98)], 0.5) is None  # spans < half the 2-s window
    r = sv.rate_hp_s([(0.0, 1.0), (1.0, 0.9), (2.0, 0.8)], 2.0, max_hp=1000)
    assert r is not None and abs(r - 100.0) < 1e-6


def test_potion_below_60_paced_and_capped() -> None:
    st = sv.State()
    assert sv.decide(st, 0.0, 0.70, {"S2"}) == []
    assert [w for w, _ in sv.decide(st, 0.1, 0.55, {"S2"})] == ["potion"]
    assert sv.decide(st, 0.3, 0.55, {"S2"}) == []  # inside the 0.7-s gap, the bar has not risen
    assert [w for w, _ in sv.decide(st, 0.4, 0.58, {"S2"})] == ["potion"]  # it rose: allowed
    assert [w for w, _ in sv.decide(st, 0.5, 0.595, {"S2"})] == ["potion"]  # rose again
    assert sv.decide(st, 1.3, 0.50, {"S2"}) == []  # 3 already within 2 s: the cap


def test_the_escape_fires_on_low_hp_or_a_fast_fall_and_wins_over_a_potion() -> None:
    st = sv.State()
    assert [w for w, _ in sv.decide(st, 0.0, 0.20, {"S2", "S3"})] == ["fly"]  # below 25 %
    st = sv.State()
    fired = [(i, sv.decide(st, i * 0.5, f, {"S3"})) for i, f in enumerate((0.95, 0.90, 0.85))]
    assert [x for _i, x in fired[:2]] == [[], []]  # the rate needs half the 2-s window first
    assert [w for w, _ in fired[2][1]] == ["fly"]  # 0.10 / 1.0 s = 526 HP/s at 5260 HP
    assert sv.decide(st, 2.5, 0.70, {"S3"}) == []  # at most once per 3 s


def test_auto_guard_is_a_toggle_cast_only_after_the_icon_is_absent_1_s() -> None:
    st = sv.State()
    assert sv.decide(st, 0.0, 1.0, {"S4"}, ag_on=None) == []  # unknown: never press
    assert sv.decide(st, 0.0, 1.0, {"S4"}, ag_on=True) == []  # already on (another cast)
    assert sv.decide(st, 1.0, 1.0, {"S4"}, ag_on=False) == []  # absent, but not 1 s yet
    assert sv.decide(st, 2.0, 1.0, {"S4"}, ag_on=False) == [("autoguard", "first cast")]
    assert sv.decide(st, 100.0, 1.0, {"S4"}, ag_on=False) == []  # our cast: 300 s not over
    assert sv.decide(st, 290.0, 1.0, {"S4"}, ag_on=True) == []  # still on near the end
    assert sv.decide(st, 302.5, 1.0, {"S4"}, ag_on=False) == []  # absent for 0 s so far
    assert sv.decide(st, 303.6, 1.0, {"S4"}, ag_on=False) == [("autoguard", "recast")]


def test_a_blink_resets_the_absence_clock_and_endure_fires_on_a_fast_fall() -> None:
    st = sv.State()
    sv.decide(st, 0.0, 1.0, {"S4"}, ag_on=False)
    sv.decide(st, 0.8, 1.0, {"S4"}, ag_on=True)  # the icon back (a blink): the clock restarts
    assert sv.decide(st, 1.2, 1.0, {"S4"}, ag_on=False) == []
    st = sv.State()
    for i, f in enumerate((1.0, 0.98, 0.96)):  # 0.02 / 0.5 s = 210 HP/s
        got = sv.decide(st, i * 0.5, f, {"S5"})
    assert [w for w, _ in got] == ["endure"]


def test_no_rule_is_on_unless_its_set_says_so() -> None:
    st = sv.State()
    assert sv.decide(st, 0.0, 0.05, sv.SETS["T-S6"]) == []  # the death-stop set presses nothing
    assert sv.SETS["T-S3"] & {"S2"} == set() and sv.SETS["T-S2"] & {"S3"} == set()


def test_the_icon_search_finds_the_template_in_the_status_column() -> None:
    import numpy as np

    rng = np.random.default_rng(1)
    tmpl = rng.integers(0, 255, (32, 32, 3), dtype=np.uint8)
    mask = np.ones((32, 32), bool)
    frame = np.full((720, 1280, 3), 90, np.uint8)
    assert not sv.ag_present(frame, tmpl, mask)
    frame[201:233, 1233:1265] = tmpl  # a second icon slot below the first
    assert sv.ag_present(frame, tmpl, mask)
