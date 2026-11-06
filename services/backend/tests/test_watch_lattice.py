"""scripts/watch_lattice.py (docs/planning/xmas02-detector.md 2a / 3a, 2026-11-06): the immune
watch's stand lattice and its TRAIN / TEST split by cell blocks, fixed before any recording.
Positive case on the REAL map (run before the commit, the client GAT in /dev/shm): xmas_dun02
gives 436 lattice stands, 343 TRAIN, 88 TEST, 5 dropped beside the exit warp; all pass the three
checks."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import watch_lattice as wl  # noqa: E402


def test_the_test_rule_holds_out_a_fifth_of_the_blocks() -> None:
    """3a: 26 x 26-cell blocks on a 260 x 260 map, (bx + 3 by) mod 5 == 0 -> 20 of 100 blocks."""
    blocks = {(bx, by) for bx in range(10) for by in range(10) if wl.is_test((bx * 26, by * 26))}
    assert len(blocks) == 20
    assert wl.is_test((0, 0)) and wl.is_test((25, 25)) and not wl.is_test((26, 0))
    assert wl.is_test((26 * 2, 26 * 1))  # 2 + 3 = 5
    rows = [sum(wl.is_test((bx * 26, by * 26)) for bx in range(10)) for by in range(10)]
    assert rows == [2] * 10  # every block row holds two TEST blocks: no band of the map is all TEST


def test_lattice_nodes_snap_to_the_nearest_stand_or_are_skipped() -> None:
    s = np.zeros((30, 30), bool)
    s[5, 5] = True  # the node (5, 5) itself
    s[17, 18] = True  # node (16, 16): (18, 17) is within snap 3 (Chebyshev 2)
    s[16, 14] = True  # ... and so is (14, 16): squared distance 4 < 5 -> the nearer one wins
    s[5, 27] = True  # node (27, 5)? no: nodes are 5, 16, 27 -> (27, 5) is a node itself
    got = wl.lattice_points(s, 11, 3)
    assert got == [(5, 5), (27, 5), (14, 16)]
    assert wl.lattice_points(s, 11, 0) == [(5, 5), (27, 5)]  # no snap: only the nodes themselves
    tie = np.zeros((11, 11), bool)
    tie[4, 6] = tie[6, 4] = True  # node (5, 5): both at squared distance 2 -> the smaller y
    assert wl.lattice_points(tie, 11, 1) == [(6, 4)]


def test_stands_are_clear_main_component_cells_outside_the_zones() -> None:
    ok = np.zeros((20, 20), bool)
    ok[2:12, 2:12] = True  # a 10 x 10 room
    ok[15:18, 15:18] = True  # a 3 x 3 island: not the main component
    no_enter = np.zeros_like(ok)
    no_enter[2:12, 9:12] = True  # a zone over the room's east side
    s = wl.stands_mask(ok, no_enter, 2)
    ys, xs = np.nonzero(s)
    assert set(xs) == set(range(4, 7)) and set(ys) == set(range(4, 10))  # 5 x 5 clear, west part
    assert not s[16, 16]


def test_the_split_drops_the_stands_that_see_the_warp() -> None:
    cells = [(0, 0), (129, 130), (145, 142), (146, 130), (30, 0)]
    out = wl.split(cells, (129, 130, 16, 12))
    assert out["avoided"] == [(129, 130), (145, 142)]
    assert out["test"] == [(0, 0), (146, 130)] and out["train"] == [(30, 0)]  # 5 + 3 * 5 = 20
    assert wl.split(cells, None)["avoided"] == []


def test_a_three_check_refusal_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch
                                              ) -> None:  # fmt: skip
    import anim_region
    import map_prep
    import map_zones

    from poring_dataset import walkable as wk

    ok = np.zeros((40, 40), bool)
    ok[3:37, 3:37] = True
    monkeypatch.setattr(wk, "load_both", lambda m: (None, ok))
    monkeypatch.setattr(anim_region, "stand_grid", lambda m, gat: ok)
    monkeypatch.setattr(map_zones, "load", lambda *a, **k: None)
    calls: list[Any] = []

    def refuse(map_name: str, cells: Any) -> str:
        calls.append(cells)
        return "the server does not let the GM stand on: [(5, 5)] (refused)"

    monkeypatch.setattr(map_prep, "stand_check", refuse)
    with pytest.raises(SystemExit, match="nothing written"):
        wl.build("toy", tmp_path / "out", avoid=None)
    assert len(calls) == 1 and not (tmp_path / "out").exists()  # one call, every stand in it


def test_the_out_dir_must_be_ram() -> None:
    with pytest.raises(SystemExit, match="/dev/shm"):  # refused before anything is read or made
        wl.main(["build", "--map", "xmas_dun02", "--out-dir", "/var/tmp/watch-lattice-test"])
    assert not Path("/var/tmp/watch-lattice-test").exists()
