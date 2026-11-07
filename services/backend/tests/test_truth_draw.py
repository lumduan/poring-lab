"""scripts/truth_draw.py (xmas02-detector.md Amendment K, K2): the by-eye pool and draw."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import truth_draw as td  # noqa: E402


def test_the_pool_is_moving_in_both_with_a_scored_unit() -> None:
    a = [{"t": 1, "moving": True, "units": [{"box": [0, 0, 1, 1]}]},
         {"t": 2, "moving": True, "units": []},
         {"t": 3, "moving": False, "units": [{"box": [0, 0, 1, 1]}]},
         {"t": 4, "moving": True, "units": [{"box": [0, 0, 1, 1]}]}]  # fmt: skip
    b = [{"t": 1, "moving": True}, {"t": 2, "moving": True}, {"t": 3, "moving": True},
         {"t": 4, "moving": False}]  # fmt: skip
    assert td.pool(a, b) == [1]


def test_the_draw_is_seeded_sorted_and_capped() -> None:
    times = list(range(100))
    one = td.draw_sample(times, 12, 71)
    assert one == td.draw_sample(times, 12, 71) and one == sorted(one) and len(one) == 12
    assert td.draw_sample([5, 3], 12, 71) == [3, 5]


def test_boxes_skip_units_without_one() -> None:
    assert td.boxes({"units": [{"box": [1, 2, 3, 4, 9]}, {"box": None}]}) == [[1.0, 2.0, 3.0, 4.0]]
