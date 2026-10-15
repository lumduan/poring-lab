"""hunt_core: the search plan, the memory, routes and the engagement judge (3.39's definitions)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import hunt_core as hc  # noqa: E402

S = 1_000_000_000


def test_search_area_drops_border_and_keep_away_boxes() -> None:
    ok = np.ones((100, 100), dtype=bool)
    a = hc.search_area(ok, [(50, 50, 1, 1)], border=10, margin=2)
    assert not a[5, 50] and not a[50, 95]
    assert not a[50, 50] and not a[53, 53] and a[54, 54]


def test_coverage_marks_new_cells_and_ranks_stale_far_tiles() -> None:
    area = np.ones((64, 64), dtype=bool)
    cov = hc.Coverage(area)
    offs = [(dx, dy) for dx in range(-8, 9) for dy in range(-8, 9)]
    assert cov.mark((8, 8), 0.0, offs) == 17 * 17  # every footprint cell is new and inside
    n0 = cov.first_seen
    assert cov.mark((8, 8), 1.0, offs) == 0 and cov.first_seen == n0
    goal = hc.choose_goal(cov, (8, 8), 10.0, {})
    assert goal is not None and max(goal) >= 16  # an unseen tile, not the one we stand in


def test_choose_goal_follows_the_memory_bonus() -> None:
    area = np.ones((64, 64), dtype=bool)
    cov = hc.Coverage(area)
    cov.seen[:, :] = 0.0  # everything seen at t = 0
    goal = hc.choose_goal(cov, (8, 8), 100.0, {(48, 48): 900.0})
    assert goal is not None and goal[0] >= 48 and goal[1] >= 48


def test_memory_keeps_stationary_and_decays_moving() -> None:
    m = hc.Memory()
    m.add(0.0, (10, 10))
    m.add(12.0, (11, 10))  # the same place 12 s later: stationary
    assert (11, 10) in m.stationary
    b = m.bonus(12.0)
    assert b[(0, 0)] >= hc.STATIONARY_BONUS_S
    m.forget((10, 10))
    assert not m.stationary
    assert m.bonus(12.0 + hc.MOVING_TTL_S * 2) == {}


def test_astar_routes_around_walls_and_needs_side_cells_for_diagonals() -> None:
    ok = np.ones((20, 20), dtype=bool)
    ok[5, 0:15] = False  # a wall with a gap on the right
    path = hc.astar(ok, (2, 2), (2, 8))
    assert path is not None and path[0] == (2, 2) and path[-1] == (2, 8)
    assert all(ok[y, x] for x, y in path)
    assert any(x >= 15 for x, _ in path)
    blocked = np.ones((3, 3), dtype=bool)
    blocked[0, 1] = blocked[1, 0] = False
    assert hc.astar(blocked, (0, 0), (1, 1)) is None  # no corner cutting


def test_waypoints_and_reckoner() -> None:
    path = [(i, 0) for i in range(20)]
    assert hc.waypoints(path, 8) == [(8, 0), (16, 0), (19, 0)]
    rk = hc.Reckoner(200.0)
    rk.go(path[:9], 0.0)
    assert rk.where(0.0) == (0, 0) and rk.where(0.45) == (2, 0) and rk.where(9.0) == (8, 0)
    assert rk.remaining(0.45) == 6 and rk.remaining(9.0) == 0
    rk.go([(0, 0), (1, 1)], 0.0)
    assert rk.where(0.25) == (0, 0) and rk.where(0.29) == (1, 1)  # a diagonal step takes 280 ms


def test_wilson() -> None:
    lo, hi = hc.wilson(57, 60)
    assert 0.86 < lo < 0.87 and 0.98 < hi < 0.99
    assert hc.wilson(0, 0) == (0.0, 1.0)


def _ev(t: float, **kw: object) -> dict[str, object]:
    return {"t_mono_ns": int(t * S), **kw}


def test_judge_success_needs_our_hit_and_the_death() -> None:
    events = [
        _ev(0, type="entity_appear", objtype=5, gid=7, x=10, y=10, job=1002),
        _ev(2, type="attack_request", target_gid=7),
        _ev(3, type="act", src_gid=2000002, target_gid=7, kind="normal", damage=5),
        _ev(9, type="entity_vanish", gid=7, reason=1),
    ]
    eng = {"t_select": 1 * S, "t_end": 10 * S, "target_cell": [10, 11]}
    j = hc.judge_engagement(eng, events)
    assert j["success"] and j["gid"] == 7 and j["why"] == "killed"


def test_judge_failures_and_exclusions() -> None:
    eng = {"t_select": 1 * S, "t_end": 10 * S, "target_cell": [10, 10]}
    walked = [_ev(0, type="entity_appear", objtype=5, gid=7, x=10, y=10, job=1002)]
    assert hc.judge_engagement(eng, walked)["why"] == "never_hit"
    other = walked + [_ev(5, type="entity_vanish", gid=7, reason=1)]
    assert hc.judge_engagement(eng, other)["why"] == "killed_by_other"
    morph = walked + [_ev(4, type="entity_appear", objtype=5, gid=7, x=10, y=10, job=1018)]
    j = hc.judge_engagement(eng, morph)
    assert j["excluded"] and j["why"] == "species_changed"
    hit = walked + [_ev(3, type="act", src_gid=2000002, target_gid=7, kind="normal")]
    assert hc.judge_engagement(eng, hit)["why"] == "hit_not_killed"
    assert hc.judge_engagement(eng, [])["why"] == "no_unit_at_selection"
