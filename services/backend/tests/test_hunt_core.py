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


def test_hunt_gone_needs_both_frames_and_time() -> None:
    import hunt

    from poring_dataset import deathcell as dcm

    seen = [dcm.Sighting(0, (0, 0, 1, 1))]
    miss = [dcm.Sighting(k * S // 2, None) for k in range(1, 6)]  # 5 frames, up to 2.5 s
    assert not hunt.gone(seen + miss[:4], 3 * S, 5, 2.5)  # 4 frames only
    assert not hunt.gone(seen + miss, 2 * S, 5, 2.5)  # 5 frames, 2.0 s
    assert hunt.gone(seen + miss, 3 * S, 5, 2.5)


def test_nearest_in_finds_the_closest_area_cell() -> None:
    area = np.zeros((30, 30), dtype=bool)
    area[10:20, 10:20] = True
    assert hc.nearest_in(area, area, (5, 15)) == (10, 15)
    assert hc.nearest_in(np.zeros((5, 5), dtype=bool), None, (2, 2)) is None


def test_hunt_reacquire_takes_the_box_nearest_the_last_feet_near_the_selection() -> None:
    from dataclasses import dataclass

    import hunt
    import ro_agent as r

    @dataclass
    class B:
        x0: float
        y0: float
        x1: float
        y1: float

    class Samp:
        def __init__(self, frames: list[tuple[int, list[B]]]) -> None:
            self.frames = frames

        def since(self, k: int) -> list[tuple[int, list[B]]]:
            return self.frames[k:]

    near_last, near_sel, far = B(100, 100, 120, 120), B(200, 100, 220, 120), B(400, 100, 420, 120)
    cells = {id(near_last): (12, 10), id(near_sel): (10, 10), id(far): (30, 10)}

    def pick(bs: list[B]) -> list[tuple[B, tuple[int, int]]]:
        return [(b, cells[id(b)]) for b in bs]

    now = r.ns()
    three = Samp([(now, [far, near_sel, near_last])])
    got = hunt.reacquire(three, pick, (110.0, 120.0), (10, 10), 4)
    assert got is not None and got[1] is near_last  # nearest the feet, within 4 of the selection
    assert hunt.reacquire(Samp([(now, [far])]), pick, (110.0, 120.0), (10, 10), 4) is None
    stale = Samp([(now - 5 * S, [near_last])])
    assert hunt.reacquire(stale, pick, (110.0, 120.0), (10, 10), 4) is None  # an old frame


def test_walk_positions_step_along_the_walk_and_stop_where_stopped() -> None:
    walk = [_ev(0, type="entity_appear", objtype=5, gid=7, x=10, y=10, x1=14, y1=12, speed=400,
                job=1002)]  # fmt: skip
    pos = hc.walk_positions(walk)[7]
    cells = [c for _t, c, _j in pos]
    assert cells == [(10, 10), (11, 11), (12, 12), (13, 12), (14, 12)]  # diagonal first
    assert pos[2][0] == int(0.8 * S)  # two steps at 400 ms
    stopped = hc.walk_positions(walk + [_ev(0.5, type="entity_stop", gid=7, x=11, y=11)])[7]
    assert [c for _t, c, _j in stopped] == [(10, 10), (11, 11), (11, 11)]
    eng = {"t_select": int(1.3 * S), "t_end": 10 * S, "target_cell": [13, 12]}
    assert hc.judge_engagement(eng, walk)["gid"] is not None  # the destination: within 2
    assert hc.judge_engagement(eng, walk, along_walk=True)["gid"] == 7  # at (13, 12) by then


def test_hunt_fight_zone_is_an_ellipse_in_cells_around_the_gm() -> None:
    from dataclasses import dataclass

    import hunt

    @dataclass
    class B:
        x0: float
        y0: float
        x1: float
        y1: float

    zone = (np.array([640.0, 362.0]), 34.0, 21.5, 2.5)  # the GM's feet; one cell's px

    def box_at(u: float, v: float) -> B:  # feet = bottom centre
        return B(u - 10, v - 30, u + 10, v)

    assert hunt.in_zone(box_at(640 + 34, 362), zone)  # one cell east
    assert hunt.in_zone(box_at(640, 362 + 2 * 21.5), zone)  # two cells south
    assert not hunt.in_zone(box_at(640 + 3 * 34, 362), zone)  # three cells east
    assert not hunt.in_zone(box_at(640 + 2 * 34, 362 + 2 * 21.5), zone)  # 2.8 cells diagonal


def test_hunt_still_boxes_need_the_whole_span_within_px() -> None:
    from dataclasses import dataclass

    import hunt

    @dataclass
    class B:
        x0: float
        y0: float
        x1: float
        y1: float

    still, walker = B(100, 100, 120, 130), B(300, 100, 320, 130)

    def moved(b: B, dx: float) -> B:
        return B(b.x0 + dx, b.y0, b.x1 + dx, b.y1)

    frames = [(int(k * 0.15 * S), [moved(still, 1), moved(walker, 8 * k)]) for k in range(5)]
    got = hunt.still_boxes(frames, 0.5, 6.0)
    assert len(got) == 1 and got[0].x0 == 101  # the walker moved 8 px a frame
    assert hunt.still_boxes(frames[:2], 0.5, 6.0) == []  # 0.15 s: too short a span
