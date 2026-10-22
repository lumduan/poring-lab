"""orcsdun01 prep (docs/planning/orcsdun01-dungeon-prep.md): the pure parts of the v1 zero-shot
scorer (scripts/orc_v1_zeroshot.py) and the rest-spot presence (scripts/orc_dungeon_prep.py), on
SYNTHETIC rows and grids; and the committed zones file's own check (config/map_zones/orcsdun01.yaml:
it parses, its reviewer is the delegated one, and both areas cover their warp span + 4)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import map_zones  # noqa: E402
import orc_dungeon_prep as odp  # noqa: E402
import orc_v1_zeroshot as zs  # noqa: E402

# --- the zero-shot matcher ---------------------------------------------------------------------


def test_greedy_match_is_one_to_one_and_closest_first() -> None:
    truth = [(0, 0, 10, 10), (100, 0, 110, 10)]
    boxes = [(2, 0, 12, 10), (1, 0, 11, 10), (300, 0, 310, 10)]
    m = zs.greedy_match(truth, boxes, tol=40)
    assert [(t, b) for t, b, _ in m] == [(0, 1)]  # box 1 is closer; box 0 gets nothing (1-to-1)
    assert zs.greedy_match(truth, boxes, tol=0.5) == []
    assert zs.greedy_match([], boxes, 40) == [] and zs.greedy_match(truth, [], 40) == []


def test_cheb_and_nearest_cell() -> None:
    assert zs.cheb((10, 10), (13, 8)) == 3
    assert zs.cheb((10.4, 10), (13.6, 10)) == 4  # rounded cells
    cells = [(0, 0), (1, 0), (0, 1)]
    uv = [(100, 100), (130, 110), (95, 70)]
    assert zs.nearest_cell((128, 109), cells, uv) == (1, 0)
    assert zs.nearest_cell((0, 0), [], []) is None


def _t(mob: int, box: tuple[float, ...], cheb: int, visible: bool = True,
       under: bool = False) -> dict[str, Any]:  # fmt: skip
    return {"mob": mob, "box": list(box), "cheb": cheb, "visible": visible, "under_model": under}


def _b(box: tuple[float, ...], cls: str = "monster", foot_cheb: int | None = 9) -> dict[str, Any]:
    return {"box": list(box), "cls": cls, "foot_cheb": foot_cheb}


def test_score_frame_counts_recall_precision_near_and_false_near_gm() -> None:
    row = {
        "gm_anchor": [640, 360],
        "truth": [
            _t(1153, (600, 300, 640, 380), cheb=1),  # hit by box 0
            _t(1005, (900, 100, 940, 140), cheb=8),  # missed
            _t(1042, (100, 600, 140, 640), cheb=9, visible=False),  # half under the UI: pass 2
        ],
        "boxes": [
            _b((602, 302, 642, 382), foot_cheb=1),  # matches the Orc Zombie
            _b((101, 601, 141, 641)),  # matches the not-visible unit in pass 2: not false
            _b((650, 330, 690, 400), foot_cheb=0),  # false, 30 px from the GM, within 3 cells
            _b((620, 310, 650, 370), foot_cheb=1),  # false, a duplicate on the Orc Zombie
            _b((900, 100, 940, 140), cls="player"),  # another class on the bat: "any class" hit
        ],
    }
    fs = zs.score_frame(row, tol=40)
    assert fs.truth_vis == [(1153, True, True, True), (1005, False, True, False)]
    assert fs.boxes == 4 and fs.box_matched == 2
    assert fs.box_near == 3 and fs.box_near_matched == 1
    assert fs.false_near_gm == 2 and fs.duplicates == 1
    s = zs.summarize([row, row], tol=40)
    assert s["pooled"]["recall"] == 0.5 and s["pooled"]["recall_near"] == 1.0
    assert s["pooled"]["recall_any_class"] == 1.0
    assert s["precision"] == 0.5 and s["boxes_per_frame"] == 4.0
    assert s["species"]["1005"]["recall"] == 0.0 and s["frames_with_false_near_gm"] == 2
    # a tighter tolerance loses the matches it should (the sensitivity rows of the table)
    assert zs.summarize([row], tol=1.0)["pooled"]["recall"] == 0.0


def test_timing_quantiles() -> None:
    rows = [{"det_ms": v, "wall_ms": v + 1, "cpu_ms": None} for v in (10.0, 20.0, 30.0)]
    t = zs.timing(rows)
    assert t["worker_ms"]["p50"] == 20.0 and t["wall_ms"]["max"] == 31.0 and t["cpu_ms"] is None


# --- rest-spot presence ------------------------------------------------------------------------


def test_box_count_matches_brute_force() -> None:
    rng = np.random.default_rng(1)
    pts = [(int(x), int(y)) for x, y in rng.integers(0, 30, size=(40, 2))]
    got = odp.box_count(pts, (30, 30), 4)
    for y in range(30):
        for x in range(30):
            want = sum(1 for px, py in pts if max(abs(px - x), abs(py - y)) <= 4)
            assert got[y, x] == want


def test_observed_mask_and_presence_rates() -> None:
    m = odp.observed_mask((10, 10), (40, 40), view=14, r=9)
    assert m.sum() == 11 * 11 and m[15, 15] and not m[16, 10]
    assert odp.observed_mask((10, 10), (40, 40), view=3, r=9).sum() == 0
    p = odp.Presence((40, 40), radii=(9,), view=14)
    p.add((10, 10), [(12, 10, 1153), (12, 11, 1042)], dwell=0)  # 1 aggressive + 1 looter
    p.add((10, 10), [], dwell=0)
    p.add((10, 10), [(12, 10, 1153)], dwell=1)
    assert p.obs[9][10, 10] == 3 and p.dwells[9][10, 10] == 2
    assert p.rate(9, "agg")[10, 10] == pytest.approx(2 / 3)
    assert p.rate(9, "all")[10, 10] == pytest.approx(3 / 3)
    assert np.isnan(p.rate(9, "agg", min_obs=4)[10, 10]) and np.isnan(p.rate(9)[30, 30])


def test_bfs_no_corner_cutting() -> None:
    ok = np.ones((3, 3), dtype=bool)
    ok[1, 0] = ok[0, 1] = False  # (0,0) only diagonally next to (1,1): blocked by the corner rule
    assert odp.bfs(ok, (1, 1))[0, 0] == -1
    ok[1, 0] = True
    assert odp.bfs(ok, (1, 1))[0, 0] == 2  # around the corner
    d = odp.multi_bfs(np.ones((1, 6), dtype=bool), np.eye(1, 6, 5, dtype=bool))
    assert d.tolist() == [[5, 4, 3, 2, 1, 0]]


def test_free_neighbours_and_pick_spots() -> None:
    ok = np.ones((5, 5), dtype=bool)
    assert odp.free_neighbours(ok, (2, 2)) == 8 and odp.free_neighbours(ok, (0, 0)) == 3
    score = np.arange(25, dtype=float).reshape(5, 5)
    elig = np.ones((5, 5), dtype=bool)
    elig[0, 0] = False
    assert odp.pick_spots(score, elig, top=2, min_sep=2) == [(1, 0), (3, 0)]


def test_static_reach_walls_block_the_line() -> None:
    ok = np.ones((9, 9), dtype=bool)
    sp = np.zeros((9, 9), dtype=bool)
    sp[4, 0] = True  # one spawnable cell, 4 west of the centre
    assert odp.static_reach(ok, sp, r=4)[4, 4] == 1
    ok[4, 2] = False  # a wall on the line
    assert odp.static_reach(ok, sp, r=4)[4, 4] == 0
    assert odp.static_reach(ok, sp, r=3)[4, 4] == 0  # out of range


# --- the committed zones file ------------------------------------------------------------------


def test_orcsdun01_zones_file_is_delegated_and_covers_both_spans() -> None:
    z = map_zones.load("orcsdun01", ROOT / "config" / "map_zones", (200, 200))
    assert z is not None
    assert z.reviewed_by == "agent (delegated by batt, 2026-10-22)"
    assert z.delegation.startswith("Batt 2026-10-22 day-run brief")
    assert not z.no_cross and [n.id for n in z.no_enter] == ["warp-in_orcs01", "warp-orcsdun02"]
    spans = {"warp-in_orcs01": (32, 172, 3, 1), "warp-orcsdun02": (183, 8, 4, 2)}
    for ne, (x, y, sx, sy) in spans.items():
        item = next(n for n in z.no_enter if n.id == ne)
        for cx in range(x - sx - 4, x + sx + 5):
            for cy in range(y - sy - 4, y + sy + 5):
                assert map_zones.in_polygon((cx, cy), item.polygon), (ne, cx, cy)
    assert not map_zones.in_no_enter(z, (32, 166))  # the runner's entrance cell stays outside
    assert map_zones.in_no_enter(z, (32, 170)) and map_zones.in_no_enter(z, (183, 11))
