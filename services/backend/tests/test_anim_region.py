"""anim_region.py's pure parts (Batt 2026-10-15, decision 3; demonstrations.md 3.32 amendment 3)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import anim_region as ar  # noqa: E402

from poring_dataset.picking import NONE  # noqa: E402


def test_lattice_takes_ok_points_moves_near_ones_and_drops_the_rest() -> None:
    ok = np.ones((20, 20), dtype=bool)
    ok[4, 4] = False  # the first lattice point: moves to its nearest ok cell
    ok[8:20, 8:20] = False  # a block with no ok cell within 3 of (12,12) or (12,4)...
    got = ar.lattice(ok, step=8, move_within=3)
    assert got["moved"] == [[(4, 4), (3, 3)]]  # ties by y then x: (3,3) first
    assert (12, 12) in got["dropped"]  # the block's centre has nothing within 3
    assert (3, 3) in got["stands"] and (12, 4) in got["stands"] and (4, 12) in got["stands"]
    assert all(ok[y, x] for x, y in got["stands"])


def test_lattice_stands_are_unique() -> None:
    ok = np.zeros((10, 10), dtype=bool)
    ok[5, 5] = True  # every lattice point within 3 moves to the same cell
    got = ar.lattice(ok, step=2, move_within=3)
    assert got["stands"] == [(5, 5)]


def test_refine_stands_skips_measured_and_stays_in_radius() -> None:
    ok = np.ones((40, 40), dtype=bool)
    out = ar.refine_stands([(20, 20)], ok, done=[(20, 20)], step=3, radius=6)
    assert (20, 20) not in out
    assert all(max(abs(x - 20), abs(y - 20)) <= 6 for x, y in out)
    assert (23, 20) in out and (14, 26) in out  # aligned to the stand


def test_exclusion_covers_self_park_and_windows() -> None:
    ex = ar.exclusion((720, 1280), (640.0, 400.0), {"chat": (0, 600)}, {"chat": (597, 93)},
                      park=(1250, 380))  # fmt: skip
    assert ex[400 - ar.SELF_UP, 640] and ex[400 + ar.SELF_DOWN, 640]
    assert not ex[400 - ar.SELF_UP - 1, 640]
    assert ex[380, 1250] and ex[380 - ar.PARK_HALF, 1250]
    assert ex[650, 300] and ex[600 - ar.UI_MARGIN, 0]
    assert not ex[100, 100]


def test_counted_drops_excluded_pixels() -> None:
    m = np.ones((4, 4), dtype=bool)
    ex = np.zeros((4, 4), dtype=bool)
    ex[0] = True
    assert int(ar.counted(m, ex).sum()) == 12


def test_view_cells_back_projects_sampled_pixels() -> None:
    mask = np.zeros((10, 10), dtype=bool)
    mask[2, 2] = mask[2, 3] = mask[4, 6] = True  # (3, 2) is off the stride-2 grid

    def pick(px: np.ndarray) -> np.ndarray:  # u // 2 east, v // 2 north; u 6 picks nothing
        return np.array([[NONE, NONE] if u == 6 else [int(u) // 2, int(v) // 2] for u, v in px])

    assert ar.view_cells(mask, pick, (100, 200), stride=2) == {(101, 201)}


def test_region_is_the_grown_union() -> None:
    reg = ar.region_of({(0, 0): [(5, 5)], (9, 9): [(5, 5), (20, 20)]}, grow=1)
    assert len(reg) == 18 and (4, 4) in reg and (21, 21) in reg and (6, 7) not in reg


def test_audit_drops_views_whose_gm_was_elsewhere() -> None:
    measures = [{"t0": 100, "stand": [5, 5], "map": "alberta"},
                {"t0": 300, "stand": [9, 9], "map": "alberta"},
                {"t0": 50, "stand": [1, 1], "map": "alberta"}]  # fmt: skip
    positions = [(90, "alberta.gat", 5, 5), (250, "alberta.gat", 8, 9)]
    assert ar.audit_positions(measures, positions) == {
        1: "GM at alberta.gat (8,9), stand (9, 9)",
        2: "no position before it",
    }


def test_load_region_is_none_when_never_measured(tmp_path: Path) -> None:
    assert ar.load_region("nowhere", tmp_path) is None
    (tmp_path / "m.json").write_text('{"cells": [[1, 2], [3, 4]]}')
    assert ar.load_region("m", tmp_path) == {(1, 2), (3, 4)}
