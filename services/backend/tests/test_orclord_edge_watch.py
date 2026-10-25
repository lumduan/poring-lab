"""orclord_edge_watch (round 2 of the Orc Lord practice): the plan is pure -- every planned stand
lies in the area, the approach ends outside NEAR, cells are spread out, and the plan is seeded."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import orclord_edge_watch as ow  # noqa: E402


def test_the_approach_starts_out_of_view_and_stops_before_near() -> None:
    path = ow.approach((100, 100), (1, 0))
    assert path[0] == (100 + ow.FAR, 100)
    assert [ow.cheb(p, (100, 100)) for p in path] == [17, 14, 11, 8]
    assert all(ow.cheb(p, (100, 100)) > ow.NEAR for p in path)


def test_the_plan_keeps_every_stand_in_the_area_and_cells_apart() -> None:
    area = np.zeros((200, 200), bool)
    area[20:180, 20:180] = True
    area[90:110, :] = False  # a wall: approaches across it are refused
    cells = ow.plan(area, 6, seed=3)
    assert len(cells) == 6
    for c in cells:
        for x, y in [c["cell"], *c["path"]]:
            assert area[y, x]
    for i, a in enumerate(cells):
        for b in cells[i + 1 :]:
            assert ow.cheb(tuple(a["cell"]), tuple(b["cell"])) >= 2 * ow.FAR
    assert ow.plan(area, 6, seed=3) == cells and ow.plan(area, 6, seed=4) != cells


def test_a_run_needs_the_immunity_read_by_a_person() -> None:
    import argparse

    a = argparse.Namespace(immune_confirmed=False)
    try:
        ow.run(a)
    except SystemExit as exc:
        assert "immune-confirmed" in str(exc)
    else:
        raise AssertionError("ran without --immune-confirmed")
