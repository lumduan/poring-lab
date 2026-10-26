"""patrol_sim (2026-10-26): the offline patrol walk. order_breaks counts a reached waypoint that is
not the next one on the loop; on gef_fild10 (when its GAT is local) every case finishes its laps in
order -- the positive case of the fix it found (the oscillation at waypoint 64)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import patrol_sim as ps  # noqa: E402


def test_order_breaks_counts_skips_and_turnbacks_on_a_loop() -> None:
    assert ps.order_breaks([0, 1, 2, 3, 0, 1], 4) == 0  # a lap and on
    assert ps.order_breaks([0, 1, 3], 4) == 1  # skipped 2
    assert ps.order_breaks([5, 6, 5], 10) == 1  # turned back


def test_gef_fild10_through_legs_finish_two_laps_in_order() -> None:
    try:
        env = ps.load("gef_fild10")
    except (OSError, FileNotFoundError) as exc:
        pytest.skip(f"no local map data: {exc}")
    for ahead, through, step in ((7, False, 6), (12, True, 3), (12, True, 10)):
        out = ps.simulate(env, ahead, through, step, laps=2, ticks=6000)
        assert out["laps"] == 2 and out["order_breaks"] == 0, out
