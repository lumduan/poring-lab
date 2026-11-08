"""scripts/quick_drop_study.py (rogue-xmas02.md 4W): --quick-drop's scorer."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import quick_drop_study as qd  # noqa: E402


def test_held_on_d_counts_class_d_only() -> None:
    st = [{"class": "D", "owned_s": 7.0}, {"class": "D", "owned_s": 2.0},
          {"class": "K", "owned_s": 9.0}, {"class": "D", "owned_s": None}]  # fmt: skip
    assert qd.held_on_d(st) == {"d": 2, "held_median_s": 4.5, "held_total_s": 9.0}
    assert qd.held_on_d([]) == {"d": 0, "held_median_s": None, "held_total_s": 0.0}


def test_drops_match_the_strike_before_each() -> None:
    ev = [{"kind": "strike", "t_ns": 100}, {"kind": "quick_drop", "t_ns": 150, "why": "no_arrow",
                                            "rearm": True},
          {"kind": "strike", "t_ns": 200}, {"kind": "quick_drop", "t_ns": 260, "why": "no_hit",
                                            "rearm": False},
          {"kind": "quick_drop", "t_ns": 50, "why": "no_arrow", "rearm": True}]  # fmt: skip
    got = qd.drops(ev, {100: "D", 200: "A"})
    assert got["quick_drops"] == 3 and got["by_why"] == {"no_arrow": 2, "no_hit": 1}
    assert got["rearmed"] == 2 and got["dropped_classes"] == {"D": 1, "A": 1, "none": 1}
    assert got["good_dropped"] == 1
