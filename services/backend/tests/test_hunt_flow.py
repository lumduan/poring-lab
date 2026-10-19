"""hunt_flow: the pure parts of hunt-flow@1 (3.41): tracks, the queue, the approach, the strike."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

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


def test_v28_rests_in_two_motions_v29_is_abc_v30_drops_the_belief() -> None:
    assert hf.PARAMS[28]["ptr_rest_two"] and hf.PARAMS[28]["ptr_rest_ui"]
    assert not hf.PARAMS[27].get("ptr_rest_two") and not hf.PARAMS[28].get("fast_dead")
    assert hf.PARAMS[29]["abc"] and not hf.PARAMS[28].get("abc") and hf.PARAMS[29]["ptr_rest_two"]
    assert hf.PARAMS[30]["abc"] and not hf.PARAMS[30]["belief"] and hf.PARAMS[29]["belief"]


def test_v32_strikes_with_arm_c_and_tests_fast_dead_per_engagement() -> None:
    p = hf.PARAMS[32]
    assert p["abc"] and p["abc_arm"] == "C" and p["loot_death"] == "anim"
    assert p["fast_dead"] and p["fast_dead_ab"] and not hf.PARAMS[31].get("fast_dead")
    assert p["fast_dead_gone_s"] < p["dead_gone_s"] and p["fast_dead_min_s"] < p["dead_min_s"]


def test_v27_drops_a_deadlocked_steer() -> None:
    assert 5.0 <= hf.PARAMS[27]["steer_stuck_s"] <= 20.0 and not hf.PARAMS[26].get("steer_stuck_s")


def test_belief_ghost_skips_probed_tracks() -> None:
    import belief_map as bm

    ok = np.ones((60, 60), bool)
    bel = bm.BeliefMap(ok, bm.Kernel.default(), [bm.Variant("nl", pd=0.2, lead=0.5)])
    ns = 10**9
    bel.update(0, [(20.0, 20.0)])
    bel.update(ns // 2, [(20.0, 20.0)])
    g = hf.belief_ghost(bel, 3 * ns, [], 100.0, "nl")
    assert g is not None
    assert hf.belief_ghost(bel, 3 * ns, [], 100.0, "nl", skip={g["tid"]}) is None
    assert hf.PARAMS[28]["belief_probe_once"] and not hf.PARAMS[27].get("belief_probe_once")
    assert set(hf.VERSIONS) >= {28, 29, 30, 32}


def test_v31_loots_around_the_targets_last_box() -> None:
    p = hf.PARAMS[31]
    assert p["loot_death"] == "anim" and p["abc"] and not p["belief"]
    assert hf.PARAMS[30]["loot_death"] == "hybrid"


def test_v33_races_the_loot_items_first_and_chains_one_looter() -> None:
    p = hf.PARAMS[33]
    assert p["loot_race"] and p["loot_race_ab"] and p["loot_icons"] and p["looter_chain"]
    assert p["abc_arm"] == "C" and p["loot_death"] == "anim" and not hf.PARAMS[32].get("loot_race")
    assert 1 <= p["looter_cells"] <= 2 and p["looter_pending_s"] > p["give_up_s"]
    assert 33 in hf.VERSIONS
    # the base fix (both arms): the readout re-anchors a loot step before a stray cell, far
    # below the jump guard's threshold
    assert p["loot_refix"] and 1.0 <= p["loot_refix_cells"] < hf.JUMP_CELLS
    assert not hf.PARAMS[32].get("loot_refix")
    # never two parity-interleaved arms at once (loot steps follow engagements: confounded)
    assert not (p.get("fast_dead_ab") and p["loot_race_ab"])
    assert not p["fast_dead"]  # 3.72's verdict: the fast arm missed its 1.2 s bar (3.73's rule)


def test_items_first_puts_the_matched_items_first_nearest_the_gm() -> None:
    plan = hf.loot_plan((10, 10), 2, 1)
    far, near = ((12, 9), (700.0, 300.0)), ((10, 11), (650.0, 350.0))
    steps = hf.items_first(plan, [far, near])
    assert [s[0] for s in steps[:2]] == [(10, 11), (12, 9)]
    assert steps[0][2] == (650.0, 350.0) and steps[0][1] == (0.0, 0.0)
    assert [(c, j) for c, j, px in steps[2:]] == plan and all(px is None for *_x, px in steps[2:])
    assert hf.items_first(plan, []) == [(c, j, None) for c, j in plan]


def test_loot_union_plan_adds_the_first_kills_cells_once() -> None:
    plan = hf.loot_plan((10, 10), 2, 1)
    got = hf.loot_union_plan((10, 10), [[11, 11], [13, 10], [13, 10], (9, 12)], 2, 1)
    assert got[: len(plan)] == plan
    assert [c for c, _j in got[len(plan) :]] == [(13, 10), (9, 12)]  # (11, 11) is in the 3 x 3
    assert hf.loot_union_plan((10, 10), [], 2, 1) == plan


def test_area_centre_is_an_area_cell_nearest_the_centroid() -> None:
    a = np.zeros((20, 30), bool)
    a[2:6, 2:6] = True
    a[14:18, 20:28] = True  # the centroid falls between the blocks: the nearest area cell
    c = hf.area_centre(a)
    assert a[c[1], c[0]]
    assert hf.area_centre(hf.main_component(a)) == (23, 15)  # the larger block, ties row-first
    assert hf.MAP == "prt_fild08"  # the default; `run --map` replaces it


def test_v34_paces_input_in_alternating_blocks() -> None:
    p = hf.PARAMS[34]
    assert p["send_gap_s"] == 0.05 and p["send_gap_ab_min"] >= 5.0  # the old drain's minimum
    assert p["send_gap_ab"]  # alternating blocks in v34 itself
    assert not p["loot_race"]  # 3.73's verdict: the plain 3 x 3 for all
    assert not hf.PARAMS[33].get("send_gap_s") and 34 in hf.VERSIONS
    src = (Path(hf.__file__)).read_text()
    # the helpers that TYPE keep the default pacing (/where, the pipelined loop's weight clear;
    # the non-pipelined loop never paces: pace_tick runs only in the pipelined one)
    assert src.count("with typing_pace():") == 2 and src.count("pace_tick(now)") == 1


def test_v35_reads_the_species_on_the_boxs_own_frame() -> None:
    p = hf.PARAMS[35]
    assert p["species_own"] and not hf.PARAMS[34].get("species_own") and 35 in hf.VERSIONS
    assert p["species_own_ab"]  # interleaved per engagement (odd k: the own frame)
    assert not (p.get("fast_dead_ab") and p["species_own_ab"])  # never two parity arms at once
    assert p["send_gap_s"] and not p["loot_race"]  # on v34 (its base set at its pre-registration)
    assert not p["send_gap_ab"]  # 3.74's verdict: paced for the whole run, no blocks


def test_v36_retries_unit_skipped_loot_cells_once() -> None:
    p = hf.PARAMS[36]
    assert p["loot_retry"] and p["loot_retry_ab"] and p["loot_retry_wait_s"] == 0.6
    assert 36 in hf.VERSIONS and not hf.PARAMS[35].get("loot_retry")
    assert not (p["species_own_ab"] and p["loot_retry_ab"])  # never two parity arms at once
    assert not p["species_own"]  # 3.75's verdict: the stale-box check for all (landing fell)
    assert p["send_gap_s"] and not p["send_gap_ab"]  # paced for the whole run (3.74)
    step = ((10, 20), (0.0, 0.0), None)
    got = hf.loot_retry_of(step, "unit", True, 100.0, 0.6)
    assert got == ((10, 20), (0.0, 0.0), None, 100.6)
    assert hf.loot_retry_of(step, "unit", False, 100.0, 0.6) is None  # the plain arm
    for why in ("pink", "npc", "view"):  # only a unit near is worth waiting for
        assert hf.loot_retry_of(step, why, True, 100.0, 0.6) is None
    assert hf.loot_retry_of(got, "unit", True, 101.0, 0.6) is None  # never a retry's retry
    src = Path(hf.__file__).read_text()
    body = src[src.index("def loot_fixed_run(") : src.index("def loot_blobs_run(")]
    # the retry runs through the SAME loop body: one loot click, one unit / pink / npc check
    assert body.count("agent.click(") == 1 and body.count('why_ = "unit"') == 1
    assert body.count('why_ = "pink"') == 1 and body.count('why_ = "npc"') == 1


def test_nearest_cell_frac_equals_the_per_cell_loop() -> None:
    import json as json_
    import random

    import pytest

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    gp = cam.GAT_DIR / "prt_fild08.gat"
    if not gp.exists():
        pytest.skip("prt_fild08.gat not in GAT_DIR (client-derived, RAM only)")
    import ro_agent as r
    import walk5 as w5

    gat = gatmod.parse(gp.read_bytes())
    cj = json_.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                     .read_text())  # fmt: skip
    w = w5.World(cam.camera_from_json(cj["camera"]), gat, (250, 139))
    rng = random.Random(7)
    for _ in range(12):
        mp = (rng.uniform(200, 300), rng.uniform(100, 180))
        c0 = (int(mp[0]) + rng.randint(-3, 3), int(mp[1]) + rng.randint(-3, 3))
        u, v = rng.uniform(300, 1000), rng.uniform(150, 600)
        for rad in (2, 4, 9):
            slow = hf.nearest_cell(lambda c_, m_=mp: hf.frac_project(w, m_, c_), c0, u, v, rad)
            assert hf.nearest_cell_frac(w, mp, c0, u, v, rad) == slow


def test_v34_base_ignores_the_targets_own_corpse_briefly() -> None:
    p = hf.PARAMS[34]
    assert p["loot_corpse"] and 1.0 <= p["loot_corpse_s"] <= 3.0 and p["loot_corpse_px"] <= 40
    assert not hf.PARAMS[33].get("loot_corpse")
    src = Path(hf.__file__).read_text()
    # only monster boxes ON the corpse spot are dropped; an NPC box always blocks
    assert 'or x_.cls != "monster"]' in src


def test_v37_reads_the_cursor_before_loot_and_moving_walk_clicks() -> None:
    p = hf.PARAMS[37]
    assert p["cursor_sword"] and p["cursor_sword_ab"] and p["cursor_sword_wait_s"] == 0.35
    assert not p["loot_retry"] and not p["loot_retry_ab"]  # not adopted (3.77): Batt's call
    assert not p["species_own_ab"] and not p.get("fast_dead_ab")  # one parity arm only
    assert 37 in hf.VERSIONS and not hf.PARAMS[36].get("cursor_sword")
    src = Path(hf.__file__).read_text()
    loot = src[src.index("def loot_fixed_run(") : src.index("def loot_blobs_run(")]
    # after every existing check, before the one loot click; a non-clear verdict skips it
    assert loot.index('why_ = "pink"') < loot.index('sword_verdict(u_l, v_l, "loot")')
    assert loot.index('sword_verdict(u_l, v_l, "loot")') < loot.index("agent.click(")
    walk = src[src.index("def walk_click(") : src.index('click_log({"t": t_c')]
    moving = walk[walk.index("else:") :]
    assert moving.index('sword_verdict(u, v, "walk")') < moving.index("agent.click(")
    assert "return False" in moving[: moving.index("agent.click(")]


def test_v38_age_weighted_heading_prefers_ground_not_seen_for_long() -> None:
    """The search study's proposal (staged): the score per walking second of the ground a heading
    brings into OUR view, by how long since we saw it (search_study's curve, pinned here)."""
    import math as m

    import search_study as ss

    ages = np.array([0.0, 30.0, 600.0, 601.0, 1200.0, 1201.0, np.inf])
    assert np.allclose(hf.rel_yield(ages), ss.rel_yield(ages))
    area = np.ones((80, 80), dtype=bool)
    offs = [(dx, dy) for dy in range(-6, 7) for dx in range(-10, 11)]  # a small screen
    seen = np.full(area.shape, -1e9)
    seen[:, 40:] = 1000.0  # east was seen 10 s ago; west never
    east = hf.band_score_age(area, (40, 40), 0.0, seen, 1010.0, offs)
    west = hf.band_score_age(area, (40, 40), m.pi, seen, 1010.0, offs)
    assert east is not None and west is not None and west[0] > 2.5 * east[0]
    st = {"ang": 0.0}  # heading east, over ground seen 10 s ago: turn toward the never-seen west
    goal = hf.heading_goal_age(area, (40, 40), st, seen, 1010.0, offs)
    assert goal is not None and goal[0] < 40 and st["turn"] != 0.0
    # all ground never seen: a DIAGONAL brings the most new cells per walking second (a wide
    # screen gains both edges; Batt walks diagonally 49 % of steps, the bot 43 %): from east the
    # rule turns 45 deg, and on a diagonal it keeps it
    st2 = {"ang": 0.0}
    hf.heading_goal_age(area, (40, 40), st2, np.full(area.shape, -1e9), 1010.0, offs)
    assert abs(st2["turn"]) == 45.0
    st2b = {"ang": m.pi / 4}
    hf.heading_goal_age(area, (40, 40), st2b, np.full(area.shape, -1e9), 1010.0, offs)
    assert st2b["turn"] == 0.0
    walled = np.zeros((80, 80), dtype=bool)
    walled[40, 35:42] = True  # a dead end everywhere but back west
    st3 = {"ang": 0.0}
    hf.heading_goal_age(walled, (41, 40), st3, seen, 1010.0, offs)
    assert st3["turn"] == 180.0  # the only reversal: a real dead end


def test_v38_is_staged_with_blocks_and_its_own_memory() -> None:
    p = hf.PARAMS[38]
    assert p["heading_age"] and p["heading_age_ab"] and p["heading_age_block_min"] == 10.0
    assert not p.get("cursor_sword_ab") and not p["loot_retry_ab"]  # one A/B at a time
    src = Path(hf.__file__).read_text()
    assert "seen_grid[fy_[in_], fx_[in_]] = now_" in src  # the camera footprint, whole run
    assert "if age_on(now_):" in src and 'elif prm.get("heading_cov"):' in src


def test_the_sword_check_is_loot_only_on_untrained_species_maps_from_v38() -> None:
    """Batt 2026-10-18, decision 2 option a: the cursor's SWORD at LOOT clicks only, with a
    0.6 s wait, and only on a map holding species the detector never learned (a per-map flag)."""
    p = hf.PARAMS[38]
    assert p["cursor_sword_where"] == ("loot",) and p["cursor_sword_wait_s"] == 0.6
    assert hf.UNTRAINED_SPECIES == {"prt_fild08": False, "prt_fild06": True}
    for k in (0, 1, 2, 3):  # every engagement, no A/B
        assert hf.sword_check_wanted(p, "prt_fild06", "loot", k)
        assert not hf.sword_check_wanted(p, "prt_fild06", "walk", k)  # walk clicks unchanged
        assert not hf.sword_check_wanted(p, "prt_fild08", "loot", k)  # inert on prt_fild08
    assert not hf.sword_active(p, "prt_fild08") and hf.sword_active(p, "prt_fild06")
    try:
        hf.sword_active(p, "pay_fild03")  # unlisted: refused, someone decides the flag
        raise AssertionError("an unlisted map must refuse")
    except ValueError as e:
        assert "UNTRAINED_SPECIES" in str(e)
    # v37 as it ran (3.78): both kinds, odd k only, on any map
    v37 = hf.PARAMS[37]
    assert hf.sword_check_wanted(v37, "prt_fild08", "walk", 1)
    assert hf.sword_check_wanted(v37, "prt_fild08", "loot", 1)
    assert not hf.sword_check_wanted(v37, "prt_fild06", "loot", 2)
    assert not hf.sword_active(hf.PARAMS[36], "prt_fild06")
    src = Path(hf.__file__).read_text()
    body = src[src.index("def run(") :]
    # the refusal comes before any input (before the immunity read and the first grab)
    assert body.index("sword_active(prm, MAP)") < body.index("f0.immunity_confirmed()")
    assert 'sword_on(k, "walk")' in body and 'sword_on(int(eng_.get("k", 0)), "loot")' in body


def test_cont_fail_logging_keeps_the_gates_order_and_short_circuit() -> None:
    """3.79 amendment (log-only): cont_click's gates stay in their old order as an if / elif
    chain (short-circuited like the old `a and b and ...`), only the first failing one counted;
    the click itself is untouched."""
    assert hf.CONT_GATES == ("view", "grid", "units", "boxes", "refused", "guard")
    src = Path(hf.__file__).read_text()
    body = src[src.index("def cont_click(") : src.index("def cont_fail_note(")]
    chain = body[body.index("fail_: str | None = None") : body.index("if fail_ is not None:")]
    tests = ["if not (in_view(uu, vv) and in_view(gu, gv)):", "elif not grid[c_[1], c_[0]]:",
             "elif not units_clear(gu, gv):", "elif not boxes_clear(gu, gv):",
             "elif cont and not walk_ok(c_):", "elif not guard_ok(uu, vv, near_box):"]  # fmt: skip
    pos = [chain.index(x) for x in tests]
    assert pos == sorted(pos)
    names = [chain[chain.index("fail_ = ", p_) + 9 :].split('"')[0] for p_ in pos]
    assert tuple(names) == hf.CONT_GATES
    assert body.count("walk_click(") == 1 and '"map+units", why, extra_' in body
    assert 'ev({"kind": "cont_fail", "counts": dict(acc_)})' in src


def test_v39_the_steer_may_click_the_routes_tail() -> None:
    """The conversion study: near the end of a short route the order (>= 3 ahead) had no
    candidate and the GM stood; v39 then tries the route's remaining cells, its end first."""
    path = [(10, 10), (11, 10), (12, 10), (13, 10)]
    assert hf.ahead_candidates(path, (11.2, 10.0), (6, 5, 7, 4, 8, 3)) == []  # the old: none
    assert hf.ahead_candidates(path, (11.2, 10.0), (6, 5, 7, 4, 8, 3), tail=True) == [3, 2]
    assert hf.ahead_candidates(path, (13.0, 10.0), (3,), tail=True) == []  # at the end: none
    # Batt 16:2x: never "none" while the lead is off the end -- past it, or short of it
    assert hf.ahead_candidates(path, (14.6, 10.0), (6, 5, 3), tail=True) == [3]  # lead past it
    assert hf.ahead_candidates(path, (12.6, 10.0), (6, 5, 3), tail=True) == []  # its own cell
    assert hf.ahead_candidates(path, (14.6, 10.0), (6, 5, 3)) == []  # v38: unchanged
    assert hf.ahead_candidates([(10, 10)], (10.0, 10.0), (3,), tail=True) == []  # in the zone
    import random as rnd

    rg = rnd.Random(7)
    for _ in range(300):  # any route, any lead: empty only on the last cell or a 1-cell route
        n = rg.randint(1, 12)
        rt = [(10 + i, 10 + rg.choice((0, 0, 1))) for i in range(n)]
        lead = (rg.uniform(8, 25), rg.uniform(8, 13))
        got = hf.ahead_candidates(rt, lead, (6, 5, 7, 4, 8, 3), tail=True)
        assert got or n == 1 or (int(round(lead[0])), int(round(lead[1]))) == rt[-1], (rt, lead)
        assert all(0 < j < n for j in got) and len(set(got)) == len(got)
    long_ = [(x, 10) for x in range(10, 30)]  # a long route: the order first, then the tail
    got = hf.ahead_candidates(long_, (10.0, 10.0), (6, 5, 3), tail=True)
    assert got[:3] == [6, 5, 3] and got[3] == 19 and 6 not in got[3:] and 0 not in got
    p = hf.PARAMS[39]
    assert p["steer_tail"] and p["steer_tail_ab"] and not p["heading_age_ab"]
    assert 39 in hf.VERSIONS and not hf.PARAMS[38].get("steer_tail")
    src = Path(hf.__file__).read_text()
    assert 'cont_click(ap, ok, "steer", tcell,\n' in src and "tail=steer_tail_on(k)" in src
    # search clicks keep the old candidates (only the steer passes tail)
    assert src.count("tail=steer_tail_on(k)") == 1
    fb = src[src.index("v39: from the route point nearest the GM") :][:600]
    assert "if steer_tail_on(k) else 0" in fb and "step_target(ap, i0_, pos" in fb
    # the tail arm's cont_fail counts go apart; without the tail the keys are v38's
    assert 'cont_fail_note(why + ("+tail" if tail else "") + ("+box" if near_box else ""),' in src


def test_v39_dead_probe_is_log_only() -> None:
    """3.80 amendment (before v39's runs): at every dead call the probe logs what the false-dead
    fix could see -- and nothing else: no click, no state change, guarded so it never stops a
    run; on in v39 only."""
    src = Path(hf.__file__).read_text()
    i0 = src.index("def dead_probe(")
    body = src[i0 : src.index("\n                def ", i0)]  # up to the next nested def
    bads = (".click(", "walk_click(", "agent.move(", "done =", "eng_[", "eng =", "target =",
            "banned", "strike(")  # fmt: skip
    for bad in bads:
        assert bad not in body.replace('eng_["track"]', "").replace('eng_["k"]', ""), bad
    assert body.rstrip().endswith("ev(out_)")
    call = src[src.index('if prm.get("dead_probe"):') :][:400]
    assert "try:" in call and "dead_probe(eng, tr, unseen, live, t_now)" in call
    assert "except Exception" in call and "dead_probe_error" in call
    assert hf.PARAMS[39]["dead_probe"] and not hf.PARAMS[38].get("dead_probe")


def test_v40_candidate_risky_dead_call_stands_only_on_a_clean_death_cell() -> None:
    """Batt 16:2x: after a RISKY last burst the dead call stands only when the death-cell fix
    says "ok"; otherwise the engagement ends "skipped_risky" -- no loot step, the track stays
    selectable (re-engaged by the normal selection), never "dead". Inert in v38 / v39."""
    u = hf.risky_unproven
    assert u("risky", "gap_too_short") and u("risky", "still_visible") and u("risky", None)
    assert not u("risky", "ok")
    assert not u("arrow", "gap_too_short") and not u(None, None) and not u("gone", "unstable")
    for n in (38, 39):
        assert not hf.PARAMS[n].get("false_dead_fix")
    # v40 (3.81, base set by 3.80's verdict 7dd9524: v39 NOT adopted -> the old picker)
    p = hf.PARAMS[40]
    assert p["false_dead_fix"] and p["false_dead_ab"] and p["dead_probe"] and 40 in hf.VERSIONS
    assert not p["steer_tail"] and not p["steer_tail_ab"] and not p["heading_age"]
    moved = ("false_dead_fix", "false_dead_ab", "steer_tail", "steer_tail_ab")
    same = {k: v for k, v in p.items() if k not in moved}
    assert same == {k: v for k, v in hf.PARAMS[39].items() if k not in moved}
    src = Path(hf.__file__).read_text()
    blk = src[src.index('if prm.get("false_dead_fix") and (') :][:1700]
    assert 'done = "skipped_risky"' in blk and ".click(" not in blk
    assert 'if done == "dead":\n' in blk and "loot_after(eng, here_l)" in blk  # no loot if skipped
    dr = src[src.index("def death_reason_now(") :][:1400]
    assert "loot1.death_of(rig, lt, here2).reason" in dr
    for bad in (".click(", "walk_click(", "agent.move(", "strike(", "done ="):
        assert bad not in dr[: dr.index("return str(")], bad
    ee = src[src.index("def end_engagement(") :][:500]
    assert "if result not in SKIPPED_SELECTABLE:" in ee and "done_ids.add(" in ee
    assert "skipped_risky" in hf.SKIPPED_SELECTABLE


def test_v41_candidate_walkers_struck_from_further_only_when_set() -> None:
    """STAGED (not pre-registered): a WALKING target's strike range from strike_cells_walking (7)
    on odd k; standing targets and every current version unchanged."""

    class T:
        def __init__(self, v: tuple[float, float]) -> None:
            self.v = v

        def velocity(self) -> tuple[float, float]:
            return self.v

    walker, still = T((1.0, 0.0)), T((0.0, 0.0))
    base = {"strike_cells": 3, "strike_cells_standing": 7}
    assert hf.strike_range(walker, base, 1) == 3 and hf.strike_range(still, base, 1) == 7
    on = {**base, "strike_cells_walking": 7, "strike_walking_ab": True}
    assert hf.strike_range(walker, on, 1) == 7 and hf.strike_range(walker, on, 2) == 3
    assert hf.strike_range(walker, on) == 3  # no k: the base arm
    assert hf.strike_range(walker, {**on, "strike_walking_ab": False}, 2) == 7
    assert hf.strike_range(still, on, 2) == 7
    for n in (38, 39, 40):
        assert not hf.PARAMS[n].get("strike_cells_walking")
    # v41 (3.82, Batt's GO 2026-10-19): on v40 adopted -- the false-dead fix on every engagement
    p = hf.PARAMS[41]
    assert p["strike_cells_walking"] == 7 and p["strike_walking_ab"] and 41 in hf.VERSIONS
    assert p["false_dead_fix"] and not p["false_dead_ab"] and not p["steer_tail"]
    moved = ("false_dead_ab", "strike_cells_walking", "strike_walking_ab")
    same = {k: v for k, v in p.items() if k not in moved}
    assert same == {k: v for k, v in hf.PARAMS[40].items() if k not in moved}
    src = Path(hf.__file__).read_text()
    assert src.count("strike_range(target, prm, k)") == 1 and "target, prm, k) <" in src


def test_v42_candidate_steer_walk_guard_from_the_gm_box_only_when_set() -> None:
    """STAGED (Batt 2026-10-19 decision 1): the STEER's walk clicks refused within
    ``steer_guard_box_px`` of the GM's drawn box instead of the 120-px circle (the pink rule
    unchanged); search and loot clicks keep the circle; inert in v38-v41."""
    box = hf.GM_SPRITE_BOX
    assert hf.box_dist(640, 330, box) == 0.0 and hf.box_dist(600, 330, box) == 20.0
    w = hf.walk_guard_box_why
    assert w(640, 330, 0.0, box, 20.0, 0.001) == "near_gm_box"  # on the sprite
    assert w(605, 330, 0.0, box, 20.0, 0.001) == "near_gm_box"  # 15 px off its side
    assert w(595, 330, 0.0, box, 20.0, 0.001) is None  # 25 px off: the circle refused it
    assert hf.walk_guard_why(595, 330, 0.0, 120.0, 0.001) == "near_gm"
    assert w(595, 330, 0.01, box, 20.0, 0.001) == "pink"  # the pink rule unchanged
    # on the camera's projection: every 1-cell step stays refused, most cells at 2-3 are freed
    import conversion_phases as cp

    proj = cp.camera_projector()
    for ring, refused_max in ((1, 8), (2, 3), (3, 3)):
        offs = [(dx, dy) for dx in range(-ring, ring + 1) for dy in range(-ring, ring + 1)
                if max(abs(dx), abs(dy)) == ring]  # fmt: skip
        px = proj(offs)
        n = sum(w(float(u), float(v), 0.0, box, 20.0, 0.001) is not None for u, v in px)
        assert n == 8 if ring == 1 else n <= refused_max, (ring, n)
        assert all(hf.walk_guard_why(float(u), float(v), 0.0, 120.0, 0.001) for u, v in px
                   ) or ring == 3  # fmt: skip
    for n in (38, 39, 40, 41):
        assert hf.PARAMS[n].get("steer_guard_box_px") is None
    src = Path(hf.__file__).read_text()
    assert src.count("near_box=steer_box_on(k)") == 1  # the steer's call only
    assert 'cont_click(gp, grid_s, "search")' in src  # search: the circle, as before
    g = src[src.index("def guard_ok(") :][:2400]
    assert "if near_box:" in g and "walk_guard_box_why(" in g and "walk_guard_why(" in g
    assert "elif not guard_ok(uu, vv, near_box):" in src


def test_dead_end_ping_pong_fix_no_second_reversal_within_the_hysteresis() -> None:
    """Batt 2026-10-19 (a BUG, fixed): at a two-sided dead end the coverage heading reversed on
    every call (v39 run 2: 52 flips in ~110 s). With ``hyst_s`` a second dead end within it takes
    the best of the 8 compass headings instead -- and repeated calls agree; without it, the old
    behaviour (every call reverses) is unchanged."""
    area = np.zeros((40, 40), dtype=bool)
    area[20, 14:27] = True  # a short east-west corridor: both ways run 6 cells (< min_run 8)
    area[17:20, 20] = True  # a 3-cell stub north
    here = (20, 20)
    swept = np.full((40, 40), -1e9)

    def flips(hyst: float) -> list[float]:
        st: dict[str, object] = {"ang": 0.0}
        out = []
        for i in range(10):
            hf.heading_goal_cov(area, here, st, swept, 100.0 + 0.5 * i, hyst_s=hyst)
            out.append(float(st["turn"]))  # type: ignore[arg-type]
        return out

    old = flips(0.0)
    assert old == [180.0] * 10  # the bug: a reversal on every call
    new = flips(10.0)
    assert new[0] == 180.0 and new.count(180.0) == 1  # one reversal, then the escape
    assert all(t == 0.0 for t in new[2:])  # the escape's absolute choice holds
    for n in hf.PARAMS:
        if n <= 41:
            assert not hf.PARAMS[n].get("dead_end_hyst_s")


def test_pocket_escape_stuck_by_displacement_and_the_nearest_way_out() -> None:
    """Batt 2026-10-19 (a BUG, fixed with v42): v43 run 2 spent 53 min in a cliff / pond pocket,
    turning +-90 / +-135 (never the 180 of the ping-pong fix). stuck_pocket: mostly searching
    for 60 s, every cell within 18 of their centre, >= 80 cells walked -> the centre; escape_goal:
    the nearest cell reachable on the grid >= min_dist from it."""
    import hunt_core as hc

    lap = [(10, 10), (20, 10), (20, 20), (10, 20)]  # the corners of a 10-cell square
    samples = [(2.0 * i, lap[i % 4], True) for i in range(32)]  # 64 s walking it: 310 cells
    t = 64.0
    pk = hf.stuck_pocket(samples, t - 2.0, 60.0, 18.0, 80.0)
    assert pk is not None and abs(pk[0] - 15) < 2 and abs(pk[1] - 15) < 2
    assert hf.stuck_pocket(samples[:10], 18.0, 60.0, 18.0, 80.0) is None  # too little history
    engaged = [(x[0], x[1], False) for x in samples]
    assert hf.stuck_pocket(engaged, t - 2.0, 60.0, 18.0, 80.0) is None  # not searching
    line = [(2.0 * i, (10 + 2 * i, 10), True) for i in range(32)]
    assert hf.stuck_pocket(line, 62.0, 60.0, 18.0, 80.0) is None  # a straight walk: not stuck
    area = np.zeros((60, 60), dtype=bool)
    area[5:25, 5:25] = True  # the pocket
    area[24:26, 14:16] = True  # its narrow way out, south
    area[26:58, 5:58] = True  # the open field
    eg = hf.escape_goal(area, (15, 15), (15.0, 15.0), 26.0)
    assert eg is not None and max(abs(eg[0] - 15), abs(eg[1] - 15)) >= 26 and area[eg[1], eg[0]]
    assert hc.astar(area, (15, 15), eg) is not None
    closed = area.copy()
    closed[24:26, 14:16] = False
    closed[25, :] = False  # no way out
    assert hf.escape_goal(closed, (15, 15), (15.0, 15.0), 26.0) is None
    for n in hf.PARAMS:
        if n <= 41 or n == 43:
            assert not hf.PARAMS[n].get("stuck_window_s")
    assert hf.PARAMS[42]["stuck_window_s"] == 60.0  # v42 carries it (3.83 amendment 2)
    src = Path(hf.__file__).read_text()
    assert 'stuck_st["mode"] = m_' in src and '"kind": "stuck_escape"' in src


def test_pocket_escape_on_v43_run_2s_real_positions() -> None:
    """The fix's offline test on the REAL run (Batt: "test it on run 2's positions offline before
    the run"): it fires at the stall's start, and the escape has a real path out; never on a
    normal run. Skipped where the sessions are not banked."""
    import gzip
    import json as json_

    import hunt_core as hc
    import pytest

    root = Path("/dev/shm/poring-lab-demo")
    stall, normal = "20261019T164004-demo-hunt-flow43", "20261019T152849-demo-hunt-flow43"
    if not (
        (root / stall / "packets.jsonl.gz").exists() and (root / normal / "events.jsonl").exists()
    ):
        pytest.skip("the v43 sessions are not banked on this host")
    import arm_judge as aj
    import flow_judge as fj
    from anim_region import stand_grid

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    gat = gatmod.parse((cam.GAT_DIR / "prt_fild08.gat").read_bytes())
    area = hc.search_area(stand_grid("prt_fild08", gat), [], margin=10)

    def first_fire(sid: str) -> tuple[int, Any] | None:
        with gzip.open(root / sid / "packets.jsonl.gz", "rt") as fh:
            ev = sorted((json_.loads(x) for x in fh), key=lambda e: int(e["t_mono_ns"]))
        bot = [json_.loads(x) for x in (root / sid / "events.jsonl").read_text().splitlines()]
        t0 = next(int(e["t_ns"]) for e in bot if e["kind"] == "loop_start")
        track, _ = fj.gm_track(ev)
        srch = aj.mode_spans(bot, "search", t0, t0 + 3600 * 10**9)
        hist: list[Any] = []
        for s in range(0, 3600, 2):
            t = t0 + s * 10**9
            c = fj.at(track, t)
            if c is None:
                continue
            hist = [x for x in hist if s - x[0] <= 62] + [(float(s), c, any(
                a <= t < b for a, b in srch))]  # fmt: skip
            pk = hf.stuck_pocket(hist, float(s), 60.0, 18.0, 80.0)
            if pk is not None:
                return s, (c, pk)
        return None

    got = first_fire(stall)
    assert got is not None and 8 * 60 <= got[0] <= 10 * 60  # the stall began ~16:48 = minute 8
    c, pk = got[1]
    eg = hf.escape_goal(area, c, pk, 26.0)
    assert eg is not None and hc.astar(area, c, eg) is not None
    assert first_fire(normal) is None


def test_p4_candidate_135_turns_only_when_0_45_90_are_blocked() -> None:
    """P4 (Batt 2026-10-19: "reverse only when 0/45/90 are all blocked; matches my rule"), STAGED:
    with no135, the coverage heading takes +-135 only when no heading within +-90 runs; inert
    unless PARAMS set cov_135_only_blocked."""
    area = np.zeros((60, 60), dtype=bool)
    area[30, 30:40] = True  # east: a short run (10 cells)
    for k in range(1, 25):  # south-west at 135 deg from east: a long fresh run
        area[30 + k, 30 - k] = True
    here = (30, 30)
    swept = np.full((60, 60), -1e9)
    swept[28:33, 30:41] = 99.0  # the east run was just swept: low fresh share
    st: dict[str, object] = {"ang": 0.0}
    hf.heading_goal_cov(area, here, st, swept, 100.0, min_run=8)
    assert abs(float(st["turn"])) == 135.0  # today: the long fresh 135 wins over the swept east
    st2: dict[str, object] = {"ang": 0.0}
    hf.heading_goal_cov(area, here, st2, swept, 100.0, min_run=8, no135=True)
    assert float(st2["turn"]) == 0.0  # P4: east still runs >= 8, so no 135 turn
    blocked = area.copy()
    blocked[30, 31:40] = False  # now nothing within +-90 runs
    st3: dict[str, object] = {"ang": 0.0}
    hf.heading_goal_cov(blocked, here, st3, swept, 100.0, min_run=8, no135=True)
    assert abs(float(st3["turn"])) == 135.0  # blocked: the 135 is allowed
    for n in hf.PARAMS:
        assert not hf.PARAMS[n].get("cov_135_only_blocked")


def test_v42_params_on_the_adopted_v43_base() -> None:
    """3.83 (e3fc195, amendments ec4212d + 4d937b4): PARAMS[42] = v43's (ADOPTED, 3.84) + the
    steer's box guard and route tail on odd k + the pocket escape in both arms; nothing else
    moves."""
    p = hf.PARAMS[42]
    assert 42 in hf.VERSIONS
    assert p["steer_guard_box_px"] == 20 and p["steer_guard_ab"]
    assert p["steer_tail"] and p["steer_tail_ab"]
    assert (p["stuck_window_s"], p["stuck_extent"], p["stuck_walked"]) == (60.0, 18.0, 80.0)
    assert (p["stuck_escape_min"], p["stuck_zone_r"], p["stuck_zone_s"]) == (26.0, 22.0, 300.0)
    assert p["ui_layout"] == "hunt" and p["dead_end_hyst_s"] == 10.0
    assert p["false_dead_fix"] and not p["false_dead_ab"]
    assert not p.get("strike_cells_walking")  # v41 not adopted (3.82)
    assert not p.get("cov_135_only_blocked")  # P4 is v47's
    moved = ("steer_tail", "steer_tail_ab", "steer_guard_box_px", "steer_guard_ab",
             "stuck_window_s", "stuck_extent", "stuck_walked", "stuck_escape_min",
             "stuck_zone_r", "stuck_zone_s")  # fmt: skip
    same = {k: v for k, v in p.items() if k not in moved}
    assert same == {k: v for k, v in hf.PARAMS[43].items() if k not in moved}


def test_exp_dead_pure_parts() -> None:
    """3.87 (hunt-flow@44, 4d937b4; Batt approved the checked fallback ~19:5x): dead = a new BASE
    EXP line since the engagement's first attack click (each line used once; a job EXP line never
    counts); the pixel call with no line within exp_wait_s stands only on the death cell "ok"."""
    on = {"exp_dead": True, "exp_dead_ab": True}
    assert hf.exp_dead_on(on, 1) and hf.exp_dead_on(on, 3) and not hf.exp_dead_on(on, 2)
    assert hf.exp_dead_on({**on, "exp_dead_ab": False}, 2)
    assert not hf.exp_dead_on({}, 1)
    lines = [{"t_ns": 900, "type": "base_exp", "n": 6},  # before the first click: not ours
             {"t_ns": 1100, "type": "job_exp", "n": 3},  # a job line never counts
             {"t_ns": 1200, "type": "damage", "n": 2000},
             {"t_ns": 1300, "type": "base_exp", "n": 6}]  # fmt: skip
    used: set[int] = set()
    rec = hf.exp_line_for(lines, 1000, used)
    assert rec is not None and rec["t_ns"] == 1300
    assert hf.exp_line_for(lines, 1000, {1300}) is None  # used once only
    assert hf.exp_line_for(lines, 1300, used) is None  # strictly after the first click
    assert hf.checked_fallback("ok") == "dead"
    for why in ("no_track", "never_seen", None, "jumped"):
        assert hf.checked_fallback(why) == "skipped_unconfirmed"
    assert set(hf.SKIPPED_SELECTABLE) == {"skipped_risky", "skipped_unconfirmed"}
    for n in hf.PARAMS:
        if n <= 43:
            assert not hf.PARAMS[n].get("exp_dead")
    src = Path(hf.__file__).read_text()
    assert src.count('bl_tail.take_base_exp(int(eng["t_first_click"]))') == 1
    assert "if result not in SKIPPED_SELECTABLE:" in src
    assert src.count("done = checked_fallback(rs_)") == 1


def test_battle_log_tail_reads_appended_records(tmp_path: Path, monkeypatch: Any) -> None:
    """3.87: the runner's tail of the reader process's battle_log_live.jsonl -- partial lines wait
    for their newline; take_base_exp consumes each base EXP line once."""
    import time as _t

    class _P:
        pid = 4242

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            pass

        def wait(self, timeout: float = 0) -> int:
            return 0

    monkeypatch.setattr(hf.BattleLogTail, "_spawn", lambda self: _P())
    out = tmp_path / "battle_log_live.jsonl"
    tail = hf.BattleLogTail(out, 1)
    with out.open("a") as fh:
        fh.write(json.dumps({"t_ns": 5, "type": "base_exp", "n": 6}) + "\n")
        fh.write('{"t_ns": 9, "type": "base')
        fh.flush()
        end = _t.monotonic() + 3
        while _t.monotonic() < end and len(tail.lines) < 1:
            _t.sleep(0.02)
        assert len(tail.lines) == 1  # the partial line waits
        fh.write('_exp", "n": 4}\n')
        fh.flush()
    end = _t.monotonic() + 3
    while _t.monotonic() < end and len(tail.lines) < 2:
        _t.sleep(0.02)
    assert [x["t_ns"] for x in tail.lines] == [5, 9]
    assert tail.take_base_exp(0)["t_ns"] == 5 and tail.take_base_exp(0)["t_ns"] == 9
    assert tail.take_base_exp(0) is None
    assert tail.alive()
    tail.stop()


def test_v45_commit_rules_pure_parts() -> None:
    """3.86 (hunt-flow@45, 1a6e139): commit late at the edge (a target within 80 px of the
    screen's edge or a UI window waits for 3 boxed frames) and keep a lost target through a short
    dropout (hold_s 1.5 from the loss; the re-acquire radius 3 -> 6; out of the view / the zone
    drops it); 10-min blocks, odd = the rules. STAGED: inert in every PARAMS."""

    class B:
        def __init__(self, x0: float, y0: float, x1: float, y1: float) -> None:
            self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1

    def tr_at(u: float, v: float, n: int) -> hf.Track:
        t = hf.Track(1, [(0, (10, 10))])
        t.box = B(u - 20, v - 40, u + 20, v)
        t.boxes = [(i, t.box) for i in range(n)]
        return t

    no_ui = lambda u, v, m: False  # noqa: E731
    assert hf.edge_deferred(tr_at(50, 400, 1), 1280, 720, 80, 3, no_ui)  # left edge, 1 frame
    assert not hf.edge_deferred(tr_at(50, 400, 3), 1280, 720, 80, 3, no_ui)  # 3 frames: go
    assert hf.edge_deferred(tr_at(640, 700, 2), 1280, 720, 80, 3, no_ui)  # bottom edge
    assert not hf.edge_deferred(tr_at(640, 400, 1), 1280, 720, 80, 3, no_ui)  # inside: as now
    assert hf.edge_deferred(tr_at(640, 400, 1), 1280, 720, 80, 3, lambda u, v, m: m == 80)
    nobox = hf.Track(2, [(0, (1, 1))])
    assert not hf.edge_deferred(nobox, 1280, 720, 80, 3, no_ui)
    assert [hf.hold_radius(h, 3.0, 1.5) for h in (0.0, 0.49, 0.5, 1.0, 1.5, 9.0)] == [
        3.0, 3.0, 4.0, 5.0, 6.0, 6.0]  # fmt: skip
    assert hf.hold_drop(1.0, 1.5, True, True) is None
    assert hf.hold_drop(1.6, 1.5, True, True) == "hold_expired"
    assert hf.hold_drop(0.2, 1.5, False, True) == "pred_out_of_view"
    assert hf.hold_drop(0.2, 1.5, True, False) == "pred_out_of_zone"
    assert hf.block_on(100.0, 100.0, 10.0) == (0, False)
    assert hf.block_on(100.0, 100.0 + 601, 10.0) == (1, True)  # odd blocks = the rules
    assert hf.block_on(100.0, 100.0 + 1201, 10.0) == (2, False)
    for n in hf.PARAMS:
        assert not hf.PARAMS[n].get("commit_rules")
    src = Path(hf.__file__).read_text()
    assert src.count("edge_wait(") == 4  # the def + dispatch, preempt, retarget
    assert "if ok_ and edge_wait(cand, now):" in src
    assert 'if not moving and in_rng and hold_st.get("tid") == target.tid:' in src
    assert src.count("hold_drop(") == 2 and src.count("hold_radius(") == 2
