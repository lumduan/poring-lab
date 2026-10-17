"""hunt_flow: the pure parts of hunt-flow@1 (3.41): tracks, the queue, the approach, the strike."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import hunt_flow as hf  # noqa: E402

S = 10**9


def test_a_standing_monster_has_no_velocity_despite_a_cell_of_noise() -> None:
    tr = hf.Track(0, [(0, (10, 10)), (int(0.5 * S), (11, 10)), (int(1.0 * S), (10, 10))])
    assert tr.velocity() == (0.0, 0.0)
    assert tr.predict(int(2.0 * S)) == (10.0, 10.0)


def test_a_walking_monster_is_predicted_ahead_capped_at_one_second() -> None:
    tr = hf.Track(0, [(0, (10, 10)), (int(0.4 * S), (11, 10)), (int(1.2 * S), (13, 10))])
    vx, vy = tr.velocity()
    assert abs(vx - 2.5) < 1e-9 and vy == 0.0
    assert tr.predict(int(5.0 * S)) == (15.5, 10.0)  # 1 s ahead at most


def test_sightings_join_the_nearest_track_and_unseen_tracks_drop() -> None:
    tracks, nid = hf.update_tracks([], 0, [("a", (10, 10)), ("b", (20, 20))], 0, 2.0, 2.0)
    assert nid == 2 and [t.seen[-1][1] for t in tracks] == [(10, 10), (20, 20)]
    tracks, nid = hf.update_tracks(tracks, int(0.3 * S), [("a2", (11, 10))], nid, 2.0, 2.0)
    assert nid == 2 and tracks[0].box == "a2" and len(tracks[0].seen) == 2
    tracks, nid = hf.update_tracks(tracks, int(2.5 * S), [("c", (40, 40))], nid, 2.0, 2.0)
    assert [t.tid for t in tracks] == [2]  # the two old ones went unseen > 2 s


def test_the_queue_takes_the_nearest_and_skips_a_dropped_spot() -> None:
    near = hf.Track(0, [(0, (12, 10))])
    far = hf.Track(1, [(0, (20, 10))])
    assert hf.choose([far, near], (10, 10), 0) is near
    assert hf.choose([far, near], (10, 10), 0, banned=[(5.0, (12, 10))], now_s=10.0) is far
    assert hf.choose([far, near], (10, 10), 0, banned=[(5.0, (12, 10))], now_s=30.0) is near


def test_the_approach_stops_short_of_the_monster_and_the_strike_waits_for_the_stop() -> None:
    area = np.ones((40, 40), bool)
    path = hf.approach_path(area, (5, 5), (15.0, 5.0), short=2)
    assert path is not None and path[-1] == (13, 5)
    assert hf.approach_path(area, (5, 5), (7.0, 5.0), short=2) is None  # already there
    assert hf.strike_due(False, (13, 5), (15.4, 5.2), 3)
    assert not hf.strike_due(True, (13, 5), (15.0, 5.0), 3)  # never while walking
    assert not hf.strike_due(False, (5, 5), (15.0, 5.0), 3)


def test_the_queue_is_a_chained_path_with_standing_targets_first() -> None:
    a = hf.Track(0, [(0, (12, 10))])  # 2 from us
    b = hf.Track(1, [(0, (22, 10))])  # 2 from c, 10 from a
    c = hf.Track(2, [(0, (20, 10))])  # 8 from a
    q = hf.plan_queue([b, c, a], (10, 10), 0, depth=3)
    assert [t.tid for t in q] == [0, 2, 1]  # each next nearest to the previous one
    walker = hf.Track(3, [(0, (11, 10)), (int(0.4 * S), (11, 12)), (int(1.0 * S), (11, 13))])
    q = hf.plan_queue([walker, a], (10, 10), int(1.0 * S), depth=1)
    assert [t.tid for t in q] == [0]  # the walker (3 away + 2) loses to the standing one (2)
    assert hf.plan_queue([a, b], (10, 10), 0, depth=3, banned=[(0.0, (12, 10))], now_s=1.0)[0] is b


def test_a_planned_target_is_dispatched_only_while_tracked_and_fresh() -> None:
    a = hf.Track(0, [(0, (12, 10))], box="b", box_t=0)
    assert hf.valid_at_dispatch(a, [a], int(0.3 * S), 0.4)
    assert not hf.valid_at_dispatch(a, [a], int(0.5 * S), 0.4)  # stale
    assert not hf.valid_at_dispatch(a, [], int(0.1 * S), 0.4)  # the tracker dropped it


class _Box:
    def __init__(self, x0: float, y0: float, x1: float, y1: float) -> None:
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1


def test_a_walk_click_keeps_clear_of_where_tracked_monsters_will_be() -> None:
    def project(c: tuple[float, float]) -> tuple[float, float]:  # 30 px a cell, feet at the cell
        return c[0] * 30.0, c[1] * 30.0

    standing = hf.Track(0, [(0, (10, 10))], box=_Box(285, 260, 315, 300), box_t=0)
    # drawn centred 20 px above its feet (300 px): a click there is refused, 3 cells away is fine
    assert not hf.track_clear(300, 280, [standing], 0, 1.0, 60, project)
    assert hf.track_clear(390, 300, [standing], 0, 1.0, 60, project)
    walker = hf.Track(1, [(0, (10, 10)), (int(0.4 * S), (12, 10)), (int(1.2 * S), (14, 10))],
                      box=_Box(405, 260, 435, 300), box_t=int(1.2 * S))  # fmt: skip
    # where it WILL be in 1 s (16.5, 10): refused although no box is there now
    assert not hf.track_clear(16.5 * 30, 280, [walker], int(1.2 * S), 1.0, 60, project)


def test_a_target_whose_track_was_restarted_is_carried_on_by_the_nearest_new_one() -> None:
    old = hf.Track(0, [(0, (10, 10))])
    near = hf.Track(5, [(int(0.5 * S), (12, 10))])
    far = hf.Track(6, [(int(0.5 * S), (20, 10))])
    assert hf.reacquire_target(old, [far, near], int(0.5 * S), 3.0) is near
    assert hf.reacquire_target(old, [far], int(0.5 * S), 3.0) is None
    assert hf.reacquire_target(old, [near], int(0.5 * S), 3.0, exclude=[5]) is None  # a dead one


def test_v4_strikes_a_standing_target_from_7_cells_and_a_walking_one_from_3() -> None:
    standing = hf.Track(0, [(0, (17, 10)), (int(1.0 * S), (17, 10))])
    walking = hf.Track(1, [(0, (10, 10)), (int(0.4 * S), (12, 10)), (int(1.2 * S), (14, 10))])
    assert hf.strike_range(standing, hf.PARAMS[4]) == 7
    assert hf.strike_range(walking, hf.PARAMS[4]) == 3
    assert hf.strike_range(standing, hf.PARAMS[3]) == 3  # earlier versions unchanged
    assert hf.strike_due(False, (10, 10), standing.predict(int(1.0 * S)), 7)


def test_v5_tries_points_about_6_ahead_of_where_the_gm_is() -> None:
    path = [(10 + i, 10) for i in range(20)]
    assert hf.ahead_candidates(path, (13.4, 10.2), (6, 5, 7)) == [9, 8, 10]  # nearest index 3
    assert hf.ahead_candidates(path, (27.0, 10.0), (6, 5, 7)) == []  # off the end: re-plan
    assert hf.ahead_candidates([], (0, 0), (6,)) == []


def test_v5_odometry_is_read_at_the_minimap_read_time() -> None:
    hist = [(0, np.array([0.0, 0.0])), (int(0.1 * S), np.array([0.5, 0.0])),
            (int(0.2 * S), np.array([1.0, 0.0]))]  # fmt: skip
    assert hf.odo_at(hist, int(0.15 * S))[0] == 0.5
    assert hf.odo_at(hist, int(5 * S))[0] == 1.0
    assert hf.odo_at([], 0) is None


def test_the_shadow_palette_keeps_cursor_colours_not_grass() -> None:
    a = np.zeros((4, 4, 3), np.uint8)
    a[0, 0] = (224, 224, 224)  # the arrow's light fill
    a[0, 1] = (20, 20, 20)  # its outline
    a[0, 2] = (0, 0, 224)  # the no-entry ring's red (BGR)
    a[0, 3] = (60, 140, 70)  # grass
    m = hf.palette_mask(a)
    assert m[0, 0] and m[0, 1] and m[0, 2] and not m[0, 3]


def test_v7_the_floor_velocity_is_measured_over_the_newest_window() -> None:
    hist = [(int(t * S), np.array([4.0 * t, -2.0 * t])) for t in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5)]
    vx, vy = hf.odo_velocity(hist, 0.3)
    assert abs(vx - 4.0) < 1e-9 and abs(vy + 2.0) < 1e-9
    assert hf.odo_velocity(hist[:1], 0.3) == (0.0, 0.0)
    still = [(int(t * S), np.array([7.0, 7.0])) for t in (0.0, 0.1, 0.2, 0.3)]
    assert hf.odo_velocity(still, 0.3) == (0.0, 0.0)


def test_v7_a_walk_click_leads_by_velocity_times_the_measured_lag() -> None:
    # v5's packets: clicks landed ~3.3 cells ahead at ~6.7 cells/s -> 0.5 s
    assert hf.lead_origin((100.0, 50.0), (6.6, 0.0), 0.5) == (103.3, 50.0)
    assert hf.lead_origin((100.0, 50.0), (0.0, 0.0), 0.5) == (100.0, 50.0)  # standing: none


def test_v7_projects_from_a_fractional_origin_by_moving_the_cell() -> None:
    class FlatWorld:  # 32 px a cell, the camera on ``position``
        position: tuple[int, int] = (0, 0)

        def project(self, cells: object) -> np.ndarray:
            c = np.asarray(cells, dtype=float) - np.asarray(self.position, dtype=float)
            return c * 32.0 + (640.0, 360.0)

    w = FlatWorld()
    u, v = hf.frac_project(w, (10.25, 20.0), (12, 20))
    assert w.position == (10, 20) and (u, v) == (640.0 + 1.75 * 32, 360.0)
    assert hf.frac_project(w, (10.0, 20.0), (12, 20)) == (640.0 + 2 * 32, 360.0)


def test_v7a2_the_client_is_where_our_commands_walked_it_since_the_frame() -> None:
    at = (100.0, 50.0)
    cmds = [(int(1.0 * S), (110, 50))]  # east, clicked before the window
    x, y = hf.commanded_lead(at, cmds, int(2.0 * S), 0.6)
    assert abs(x - 104.0) < 0.1 and y == 50.0  # 0.6 s at 150 ms a cell
    diag = [(int(1.0 * S), (110, 60))]
    dx, dy = hf.commanded_lead(at, diag, int(2.0 * S), 0.6)
    assert abs(dx - 100.0 - 0.6 / 0.21) < 0.1 and abs(dy - 50.0 - 0.6 / 0.21) < 0.1


def test_v7a2_a_new_command_turns_the_replay_and_arrival_stops_it() -> None:
    at = (100.0, 50.0)
    cmds = [(int(1.0 * S), (110, 50)), (int(1.7 * S), (101, 40))]  # north after 0.3 s
    x, y = hf.commanded_lead(at, cmds, int(2.0 * S), 0.6)
    # 0.3 s east (2 cells), then diagonal until x is within half a cell (0.1 s), then north
    assert abs(x - 101.5) < 0.1 and abs(y - 48.2) < 0.15
    x, _y = hf.commanded_lead(at, [(0, (102, 50))], int(2.0 * S), 0.6)
    assert abs(x - 101.5) < 0.1  # arrived (within half a cell): it stops
    assert hf.commanded_lead(at, [], int(2.0 * S), 0.6) == at  # nothing commanded: as measured


def test_v8_the_main_component_leaves_a_ledge_strip_out() -> None:
    area = np.zeros((10, 20), bool)
    area[1:9, 1:12] = True  # the big field
    area[2:4, 15:18] = True  # a ledge strip, not connected
    main = hf.main_component(area)
    assert main[5, 5] and not main[3, 16] and int(main.sum()) == 8 * 11


def test_v8_escape_cells_are_the_nearest_main_cells() -> None:
    main = np.zeros((10, 20), bool)
    main[1:9, 1:12] = True
    assert hf.escape_cells(main, (16, 3), reach=10, k=2) == [(11, 1), (11, 2)]
    assert hf.escape_cells(main, (16, 3), reach=2) == []


def test_v8a2_the_escape_retreats_along_cells_we_walked() -> None:
    trail = [(float(t), (100 - t, 50)) for t in range(30)]  # walked west, 1 cell a second
    here = (71, 50)  # now, at t = 30
    got = hf.trail_cells(trail, here, 30.0, near=6, far=20, min_age_s=3.0, k=3)
    assert got == [(77, 50), (78, 50), (79, 50)]  # the most recent that are >= 6 away
    assert hf.trail_cells(trail, here, 30.0, near=40) == []
    main = np.zeros((10, 20), bool)
    main[1:9, 1:12] = True
    assert all(hf.cheb(c, (12, 5)) >= 6 for c in hf.escape_cells(main, (12, 5), near=6))


class _B:
    def __init__(self, x: float, y: float) -> None:
        self.x0, self.y0, self.x1, self.y1 = x - 10, y - 10, x + 10, y + 10


def test_v9_a_target_stands_when_its_recent_boxes_agree() -> None:
    still = [(int(t * S), _B(500 + (t % 2), 300)) for t in (9.2, 9.5, 9.8, 10.0)]
    assert hf.box_still(still, int(10.1 * S), 0.9, 8.0)
    hop = [
        (int(9.4 * S), _B(470, 300)),
        (int(9.7 * S), _B(485, 300)),
        (int(10.0 * S), _B(500, 300)),
    ]
    assert not hf.box_still(hop, int(10.1 * S), 0.9, 8.0)
    assert not hf.box_still(still[-2:], int(10.1 * S), 0.9, 8.0)  # too few frames to say


def test_v9a2_the_minimap_picture_tells_a_map_change_from_a_moved_arrow() -> None:
    rng = np.random.default_rng(1)
    ref = rng.integers(0, 255, (120, 124, 3), dtype=np.uint8)
    moved = ref.copy()
    moved[50:62, 60:72] = 255  # the GM arrow somewhere else
    assert hf.map_same(ref, moved)
    other = rng.integers(0, 255, (120, 124, 3), dtype=np.uint8)
    assert not hf.map_same(ref, other)
    assert not hf.map_same(ref, other[:100])


class _Bx:
    def __init__(self, x0: float, y0: float, x1: float, y1: float, score: float = 0.9) -> None:
        self.x0, self.y0, self.x1, self.y1, self.score = x0, y0, x1, y1, score


def test_v10_the_strict_gate_reads_only_where_there_is_risk() -> None:
    gm = (640.0, 340.0)
    b = _Bx(800, 300, 830, 330)
    assert hf.gate_reasons(b, [], gm, 45.0, 0.6, False, False) == []  # click it directly
    assert hf.gate_reasons(b, [_Bx(825, 320, 860, 350)], gm, 45.0, 0.6, False, False) == [
        "intersect"]  # fmt: skip
    assert hf.gate_reasons(b, [_Bx(835, 300, 860, 330)], gm, 45.0, 0.6, False, False) == []
    near = _Bx(645, 320, 675, 350)  # centre 660,335: 20 px from the GM's sprite
    assert hf.gate_reasons(near, [], gm, 45.0, 0.6, False, False) == ["near_gm"]
    assert hf.gate_reasons(_Bx(800, 300, 830, 330, 0.55), [], gm, 45.0, 0.6, True, True) == [
        "low_conf", "npc_near", "ignore_species"]  # fmt: skip


def test_v11_target_cost_is_distance_plus_a_walking_penalty() -> None:
    standing = hf.Track(0, [(0, (10, 10)), (int(1.0 * S), (10, 10))])
    walking = hf.Track(1, [(0, (10, 10)), (int(1.0 * S), (13, 10))])
    assert hf.target_cost(standing, (4, 10), int(1.0 * S), 2.0) == 6.0
    assert hf.target_cost(walking, (4, 10), int(1.0 * S), 2.0) == 9.0 + 2.0


def test_v11_the_zone_path_ends_at_the_nearest_cell_within_range() -> None:
    grid = np.ones((30, 40), bool)
    p = hf.zone_path(grid, (5, 10), (20, 10), 7)
    assert p is not None and p[0] == (5, 10) and p[-1] == (13, 10) and len(p) == 9
    assert hf.zone_path(grid, (15, 12), (20, 10), 7) == [(15, 12)]  # already inside
    grid[:, 10] = False  # a wall between
    assert hf.zone_path(grid, (5, 10), (20, 10), 7) is None


def test_v12_the_sweep_runs_a_lane_shifts_then_comes_back() -> None:
    area = np.zeros((40, 60), bool)
    area[5:35, 5:55] = True
    st: dict = {}
    assert hf.sweep_goal(area, (10, 10), st) == (50, 10)  # the lane east to the edge (40 max)
    assert hf.sweep_goal(area, (54, 10), st) == (54, 22) and st["phase"] == "shift"
    assert hf.sweep_goal(area, (54, 22), st) == (14, 22) and st["h"] == (-1, 0)  # back west
    assert hf.ray_run(area, (54, 10), (1, 0), 40) == 0


def test_v12_a_turn_back_costs_a_penalty() -> None:
    assert hf.reversal_penalty((10, 10), (2, 10), (1, 0), 4.0) == 4.0  # behind: 180 deg
    assert hf.reversal_penalty((10, 10), (10, 2), (1, 0), 4.0) == 0.0  # 90 deg: no penalty
    assert hf.reversal_penalty((10, 10), (2, 10), None, 4.0) == 0.0


def test_v12_a_new_down_arrow_counts_and_an_old_one_does_not() -> None:
    reg = np.full((60, 90, 3), (90, 140, 60), np.uint8)
    cur = reg.copy()
    for i, row in enumerate(range(30, 34)):  # a down-pointing triangle, 9 px wide at the top
        cur[row, 40 + i : 49 - i] = 250
    assert hf.arrow_blobs(cur) and not hf.arrow_blobs(reg)
    assert hf.arrow_new(reg, cur)
    assert not hf.arrow_new(cur, cur)  # it was already there
    up = reg.copy()
    for i, row in enumerate(range(30, 34)):  # pointing up: not the marker
        up[row, 44 - i : 45 + i] = 250
    assert not hf.arrow_blobs(up)


def test_v12_the_burst_jitter_scales_with_the_sprite() -> None:
    lunatic, poring = _Bx(100, 100, 133, 127), _Bx(100, 100, 140, 138)
    assert hf.burst_aim(lunatic, 0) == (116.5, 113.5)
    assert hf.burst_aim(lunatic, 1)[1] - 113.5 < hf.burst_aim(poring, 1)[1] - 119.0


def test_v13_only_a_clearly_better_target_preempts() -> None:
    assert hf.preempt_better(3.0, None, 4, 2.0)  # no current target
    assert hf.preempt_better(1.0, 3.0, 4, 2.0)  # 2 cells closer
    assert not hf.preempt_better(2.0, 3.0, 4, 2.0)  # 1 cell closer: a neighbour, no flip
    assert hf.preempt_better(3.0, 5.0, 4, 2.0)  # the current one left the zone


def test_v16_ncc_finds_the_template_where_it_was_moved() -> None:
    rng = np.random.default_rng(3)
    frame = rng.uniform(0, 255, (120, 140))
    tpl = frame[40:72, 50:84].copy()  # a 32 x 34 sprite crop at (50, 40)
    moved = rng.uniform(0, 255, (120, 140))
    moved[55:87, 63:97] = tpl  # it moved to (63, 55)
    x, y, sc = hf.ncc_search(moved, tpl)
    assert (x, y) == (63, 55) and sc > 0.99
    assert hf.ncc_search(moved[:10, :10], tpl)[2] == -1.0


def test_v18_the_heading_holds_then_turns_45_before_90_and_reverses_last() -> None:
    area = np.zeros((60, 60), bool)
    area[5:55, 5:55] = True
    st: dict = {"ang": 0.0}
    assert hf.heading_goal(area, (10, 30), st, None) == (50, 30) and st["turn"] == 0.0
    # a block ahead, open diagonals: +-45 deg first
    blocked = np.ones((60, 80), bool)
    blocked[28:33, 56:58] = False  # a short wall ahead
    st45: dict = {"ang": 0.0}
    g = hf.heading_goal(blocked, (50, 30), st45, None)
    assert abs(abs(st45["turn"]) - 45) < 1e-9 and g is not None
    # at the area's east edge the diagonals leave at once too: +-90 deg
    hf.heading_goal(area, (54, 30), st, None)
    assert abs(abs(st["turn"]) - 90) < 1e-9
    corridor = np.zeros((20, 60), bool)
    corridor[10, 5:55] = True  # a dead-end corridor: nothing but back
    st2: dict = {"ang": 0.0}
    hf.heading_goal(corridor, (54, 10), st2, None)
    assert st2["turn"] == 180.0


def test_v18_the_first_heading_is_the_longest_compass_ray() -> None:
    area = np.zeros((60, 60), bool)
    area[28:33, 5:55] = True  # a wide east-west corridor
    assert hf.start_heading(area, (10, 30)) == 0.0  # east: 44 cells
    assert abs(hf.start_heading(area, (50, 30)) - math.pi) < 1e-9  # west


def test_v18_the_minimap_arrow_points_to_its_narrow_tip_not_its_prongs() -> None:
    def arrow(rot: int) -> np.ndarray:
        img = np.zeros((40, 40, 3), np.uint8)
        for i in range(8):  # an arrowhead pointing +x: prongs at the back, a notch, a tip at x=27
            half = (7 - i) // 2
            img[20 - half : 21 + half, 20 + i] = 255
        img[20, 20:22] = 0  # the notch between the prongs
        return np.rot90(img, rot).copy()

    for rot, want in ((0, 0.0), (1, -math.pi / 2), (2, math.pi), (3, math.pi / 2)):
        ang = hf.minimap_heading(arrow(rot))
        assert ang is not None
        assert abs((ang - want + math.pi) % (2 * math.pi) - math.pi) < 0.3, (rot, ang)
    assert hf.minimap_heading(np.zeros((40, 40, 3), np.uint8)) is None


def test_v20_the_tag_is_also_searched_under_the_pointer() -> None:
    from types import SimpleNamespace

    b = SimpleNamespace(x0=100, y0=100, x1=140, y1=136)
    assert hf.tag_boxes(b, (300.0, 200.0), False) == [b]
    got = hf.tag_boxes(b, (300.0, 200.0), True)
    assert got[0] is b and (got[1].x0, got[1].y0, got[1].x1, got[1].y1) == (280, 182, 320, 218)
    assert hf.PARAMS[20]["tag_follow"] and hf.PARAMS[20]["focus"] and hf.PARAMS[20]["name_tag"]
    assert not hf.PARAMS[20].get("retarget")  # one change against v18 (v19 built, not run)


def test_walk_guard_refuses_near_the_gm_and_near_pink_and_ignores_the_gm_hair() -> None:
    crop = np.zeros((200, 200, 3), np.uint8)
    crop[...] = (70, 130, 150)  # the dirt road (yellow-brown, BGR): never pink
    share = hf.pink_share(crop, (600, 400), 700.0, 500.0, 80, hf.GUARD_EXCLUDE)
    assert share == 0.0
    crop[90:100, 120:130] = (140, 120, 230)  # a Poring's / Creamy's pink (BGR), 20 px away
    share = hf.pink_share(crop, (600, 400), 700.0, 500.0, 80, hf.GUARD_EXCLUDE)
    assert share > 0.001
    assert hf.walk_guard_why(700.0, 500.0, share, 120.0, 0.001) == "pink"
    assert hf.walk_guard_why(700.0, 500.0, 0.0, 120.0, 0.001) is None
    assert hf.walk_guard_why(700.0, 400.0, 0.0, 120.0, 0.001) == "near_gm"  # 85 px from the GM
    gm = np.zeros((200, 200, 3), np.uint8)
    gm[...] = (50, 140, 60)  # grass (BGR)
    gm[30:60, 80:100] = (120, 90, 220)  # the GM's red-pink hair (BGR) inside its own box
    assert hf.pink_share(gm, (560, 260), 640.0, 340.0, 80, hf.GUARD_EXCLUDE) == 0.0
    assert hf.PARAMS[16]["walk_guard"] and not hf.PARAMS[15].get("walk_guard")
    rgb = np.zeros((200, 200, 3), np.uint8)
    rgb[...] = (230, 120, 140)  # pink given as RGB reads as blue-ish in BGR: not pink
    assert hf.pink_share(rgb, (600, 400), 700.0, 500.0, 80, hf.GUARD_EXCLUDE) == 0.0


def test_the_opportunistic_strike_skips_a_target_dropped_here_within_the_ban() -> None:
    near = hf.Track(0, [(0, (12, 10))], box="b", box_t=0)
    other = hf.Track(1, [(0, (13, 12))], box="b", box_t=0)
    assert hf.nearest_close([near, other], (10, 10), 0, 4, 1.0) is near
    banned = [(100.0, (12, 10))]  # v15 run 1: near was dropped (three refused tag reads)
    got = hf.nearest_close([near], (10, 10), 0, 4, 1.0, (), banned, 105.0, 15.0)
    assert got is None
    assert hf.nearest_close([near], (10, 10), 0, 4, 1.0, (), banned, 116.0, 15.0) is near
    far_ban = [(100.0, (30, 30))]
    assert hf.nearest_close([near], (10, 10), 0, 4, 1.0, (), far_ban, 105.0, 15.0) is near


def test_the_stall_breaker_walks_to_a_reachable_cell_away_from_the_pocket() -> None:
    import random

    grid = np.zeros((40, 40), bool)
    grid[20, 2:6] = True  # a pocket at the west edge ...
    grid[10:30, 6:30] = True  # ... opening onto the field
    got = hf.unstall_cells(grid, (2, 20), random.Random(1), 6, 14, 4)
    assert len(got) == 4
    for c in got:
        assert grid[c[1], c[0]] and hf.cheb(c, (2, 20)) >= 6
    assert hf.unstall_cells(np.zeros((5, 5), bool), (2, 2), random.Random(1)) == []


def test_walk_guard_from_v17_leaves_the_client_windows_out_of_the_pink_count() -> None:
    crop = np.zeros((200, 200, 3), np.uint8)
    crop[...] = (50, 140, 60)  # grass (BGR)
    crop[150:160, 10:20] = (40, 40, 220)  # a red window icon at client (510-520, 550-560)
    share = hf.pink_share(crop, (500, 400), 560.0, 500.0, 80, hf.GUARD_EXCLUDE)
    assert share > 0.001
    ui = [(0.0, 532.0, 600.0, 626.0)]  # the chat window
    assert hf.pink_share(crop, (500, 400), 560.0, 500.0, 80, hf.GUARD_EXCLUDE, ui) == 0.0
    assert hf.PARAMS[17]["guard_ui_mask"] and not hf.PARAMS[16].get("guard_ui_mask")


def test_from_v16_every_attack_click_needs_the_tag_and_the_cache_is_short_and_local() -> None:
    p = hf.PARAMS[16]
    assert p["name_tag"] and p["tag_every_click"]  # v16 attempt 1: the read path hit a Creamy
    assert p["tag_cache_s"] <= 3.0 and p["tag_cache_px"] <= 60.0
    assert hf.PARAMS[20]["tag_every_click"] and not hf.PARAMS[15].get("tag_every_click")


def test_walk_guard_from_v21_leaves_our_own_drawn_cursor_out() -> None:
    crop = np.zeros((200, 200, 3), np.uint8)
    crop[...] = (50, 140, 60)  # grass (BGR)
    crop[95:105, 95:105] = (40, 40, 220)  # the no-entry cursor's red ring where our pointer rests
    assert hf.pink_share(crop, (500, 400), 640.0, 500.0, 80, hf.GUARD_EXCLUDE) > 0.001
    got = hf.pink_share(crop, (500, 400), 640.0, 500.0, 80, hf.GUARD_EXCLUDE, (), (598.0, 498.0))
    assert got == 0.0


def test_v21_loots_by_frame_difference_on_v20() -> None:
    p = hf.PARAMS[21]
    assert p["loot_blobs"] and p["guard_ptr_mask"] and p["tag_follow"] and p["loot_sweep"]
    assert 1.0 <= p["loot_before_s"] <= 2.5
    assert not hf.PARAMS[20].get("loot_blobs")


def test_v22_the_heading_turns_away_from_ground_we_swept() -> None:
    area = np.ones((80, 80), bool)
    swept = np.full(area.shape, -1e9)
    st: dict = {"ang": 0.0}  # heading east
    g = hf.heading_goal_cov(area, (40, 40), st, swept, 1000.0)
    assert st["turn"] == 0.0 and g is not None and g[0] > 40  # all fresh: keep the heading
    swept[:, 41:] = 990.0  # the east was in our view 10 s ago
    st2: dict = {"ang": 0.0}
    hf.heading_goal_cov(area, (40, 40), st2, swept, 1000.0)
    assert abs(st2["turn"]) in (90.0, 135.0) and st2["fresh"] > 0.5  # turn toward fresh ground
    assert hf.fresh_share(swept, 1000.0, (20, 40), 5, 180.0) == 1.0
    assert hf.fresh_share(swept, 1000.0 + 200.0, (60, 40), 5, 180.0) == 1.0  # swept long ago
    assert hf.PARAMS[22]["heading_cov"] and hf.PARAMS[22]["loot_blobs"]


def test_v23_is_batts_fixed_loot_workflow_on_v22() -> None:
    p = hf.PARAMS[23]
    assert p["loot_fixed"] and p["heading_cov"] and p["species_shadow"]
    assert not p.get("loot_icons")  # the item-sprite version stays built and unrun
    assert not hf.PARAMS[22].get("loot_fixed")
    plan = hf.loot_plan((100, 50), p["loot_center_clicks"], p["loot_ring_clicks"])
    assert [c for c, _ in plan[:3]] == [(100, 50), (100, 50), (101, 49)]  # burst, then SE
    assert len(plan) == p["loot_center_clicks"] + 8 * p["loot_ring_clicks"] == 10
    assert {c for c, _ in plan} == {(100 + dx, 50 + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
    assert len(plan) * p["loot_interval_s"] <= p["loot_fixed_max_s"]


def test_new_pink_counts_only_pink_that_was_not_there_before() -> None:
    pink = (180, 90, 230)  # BGR: a Poring's (or a Creamy's) colours
    before = np.zeros((200, 200, 3), np.uint8)
    before[90:110, 90:110] = pink  # the corpse splat, there before the death
    after = before.copy()
    assert hf.new_pink_px(after, before, 100, 100, 40) == 0
    assert hf.new_pink_px(after, None, 100, 100, 40) == 400
    # the camera followed the GM: the ground (and the corpse) moved 30 px left on screen
    moved = np.zeros_like(before)
    moved[90:110, 60:80] = pink
    assert hf.new_pink_px(moved, before, 70, 100, 40, shift=(-30.0, 0.0)) == 0
    assert hf.new_pink_px(moved, before, 70, 100, 40) > 100  # unaligned it would block the loot
    moved[130:150, 130:150] = pink  # a Creamy flies in: 400 new pink pixels
    p = hf.PARAMS[23]
    assert hf.new_pink_px(moved, before, 140, 140, p["loot_pink_r"],
                          shift=(-30.0, 0.0)) > p["loot_pink_max_px"]  # fmt: skip
    apple = np.zeros_like(before)
    apple[95:103, 95:103] = (40, 30, 200)  # an Apple-sized red sprite: 64 px, not a Creamy
    assert (
        0 < hf.new_pink_px(apple, before * 0, 100, 100, p["loot_pink_r"]) <= p["loot_pink_max_px"]
    )


def test_shifted_crop_is_the_region_zero_outside() -> None:
    img = np.arange(5 * 6 * 3, dtype=np.int32).reshape(5, 6, 3)
    c = hf.shifted_crop(img, 1, 2, 3, 2)
    assert (c == img[2:4, 1:4]).all()
    c = hf.shifted_crop(img, -1, -1, 3, 3)  # one row and one column outside
    assert (c[0] == 0).all() and (c[:, 0] == 0).all() and (c[1:, 1:] == img[0:2, 0:2]).all()


def test_v24_loots_around_the_last_strike_or_beside_the_gm() -> None:
    p = hf.PARAMS[24]
    assert p["loot_death"] == "hybrid" and p["loot_fixed"] and not hf.PARAMS[23].get("loot_death")
    assert p["loot_interval_s"] < hf.PARAMS[23]["loot_interval_s"]
    assert hf.death_cell_hybrid((101, 50), (100, 50)) == (101, 50)  # beside the GM: as clicked
    assert hf.death_cell_hybrid((100, 50), (100, 50)) == (100, 50)
    assert hf.death_cell_hybrid((104, 47), (100, 50)) == (101, 49)  # far: the GM's neighbour
    assert hf.death_cell_hybrid((100, 56), (100, 50)) == (100, 51)


def test_nearest_cell_inverts_a_projection() -> None:
    def proj(c: tuple[int, int]) -> tuple[float, float]:
        return 640 + 32 * (c[0] - 100) - 0.0, 360 - 24 * (c[1] - 50)

    assert hf.nearest_cell(proj, (100, 50), 640 + 64 + 5, 360 - 24 * 3 + 4) == (102, 53)
    assert hf.nearest_cell(proj, (100, 50), 640, 360) == (100, 50)


def test_frame_guard_clamps_moves_and_refuses_clicks_off_the_frame() -> None:
    from collections import Counter

    sent: list[tuple[str, int, int]] = []

    class Fake:
        def move(self, x: int, y: int) -> None:
            sent.append(("move", x, y))

        def click(self, x: int, y: int, button: str = "left") -> None:
            sent.append(("click", x, y))

        def send(self, ev: list[dict[str, object]]) -> str:
            return "passed"

    n: Counter[str] = Counter()
    g = hf.FrameGuard(Fake(), (8, 30, 1280, 720), n)
    g.move(700, 18)  # v23 attempt 2: a pre-motion above the frame
    g.click(700, 20)
    g.click(700, 300)
    assert sent == [("move", 700, 30), ("click", 700, 300)]
    assert n == Counter({"clamped": 1, "refused": 1})
    assert g.send([]) == "passed"  # everything else passes through
    g.wait_for_human = "hook"  # an attribute set on the guard lands on the real agent
    assert g._a.wait_for_human == "hook"


def test_v25_skips_the_tag_only_when_sure_and_strikes_walking_in() -> None:
    p = hf.PARAMS[25]
    assert p["species_skip"] and p["strike_moving"] and p["name_tag"] and p["risk_gate"]
    assert p["loot_death"] == "hybrid"  # on v24
    assert not hf.PARAMS[24].get("species_skip") and not hf.PARAMS[24].get("strike_moving")
    import nametag

    assert "Creamy" not in nametag.TARGET_NAMES  # a sure Creamy never skips the tag


def test_new_pink_leaves_the_gm_sprite_out_when_asked() -> None:
    after = np.zeros((200, 200, 3), np.uint8)
    after[50:70, 90:110] = (180, 90, 230)  # the GM's hair, "new" against a shifted BEFORE
    before = np.zeros_like(after)
    assert hf.new_pink_px(after, before, 100, 80, 40) == 400
    assert hf.new_pink_px(after, before, 100, 80, 40, exclude=(85.0, 45.0, 115.0, 75.0)) == 0
    assert hf.PARAMS[25]["loot_pink_gm_exclude"] and not hf.PARAMS[24].get("loot_pink_gm_exclude")


def test_belief_ghost_picks_a_hidden_live_track_and_skips_our_kills() -> None:
    import belief_map as bm

    ok = np.ones((60, 60), bool)
    bel = bm.BeliefMap(ok, bm.Kernel.default(), [bm.Variant("nl", pd=0.2, lead=0.5)])
    ns = 10**9
    bel.update(0, [(20.0, 20.0), (40.0, 40.0)])
    bel.update(ns // 2, [(20.0, 20.0), (40.0, 40.0)])  # two sightings each
    t = 3 * ns  # both unseen 2.5 s
    g = hf.belief_ghost(bel, t, [], 100.0, "nl")
    assert g is not None and g["probes"] and 2.4 <= g["unseen_s"] <= 2.6
    assert hf.cheb(g["probes"][0], g["last"]) <= 2
    # one of them is where we just killed something: only the other is a ghost
    g2 = hf.belief_ghost(bel, t, [(99.0, (20, 20))], 100.0, "nl")
    assert g2 is not None and hf.cheb(g2["last"], (40, 40)) <= 1
    assert hf.belief_ghost(bel, t, [(99.0, (20, 20)), (99.0, (40, 40))], 100.0, "nl") is None
    assert hf.belief_ghost(bel, 20 * ns, [], 100.0, "nl") is None  # unseen too long


def test_v26_retargets_and_v27_adds_the_belief_map() -> None:
    p26, p27 = hf.PARAMS[26], hf.PARAMS[27]
    assert p26["retarget"] and p26["species_skip"] and not hf.PARAMS[25].get("retarget")
    assert p27["belief"] and p27["retarget"] and not p26.get("belief")
    assert p27["belief_unseen"] == (1.0, 10.0) and 0 < p27["belief_pd"] < 1
    assert set(hf.VERSIONS) >= {24, 25, 26, 27}


def test_v25_widens_the_loot_unit_margin() -> None:
    assert hf.PARAMS[25]["loot_unit_px"] >= 60 and "loot_unit_px" not in hf.PARAMS[24]


def test_v26_rests_the_pointer_on_the_ui() -> None:
    import route_preview

    assert hf.PARAMS[26]["ptr_rest_ui"] and not hf.PARAMS[25].get("ptr_rest_ui")
    x0, y0, x1, y1 = route_preview.UI_WINDOWS[0]  # the Basic Information window
    assert x0 + 20 <= hf.REST_PX[0] <= x1 - 20 and y0 + 20 <= hf.REST_PX[1] <= y1 - 20


def test_v28_fast_dead_is_staged_on_v27() -> None:
    p = hf.PARAMS[28]
    assert p["fast_dead"] and p["belief"] and not hf.PARAMS[27].get("fast_dead")
    assert p["fast_dead_gone_s"] < p["dead_gone_s"] and p["fast_dead_min_s"] < p["dead_min_s"]


def test_v27_drops_a_deadlocked_steer() -> None:
    assert 5.0 <= hf.PARAMS[27]["steer_stuck_s"] <= 20.0 and not hf.PARAMS[26].get("steer_stuck_s")
