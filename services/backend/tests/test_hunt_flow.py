"""hunt_flow: the pure parts of hunt-flow@1 (3.41): tracks, the queue, the approach, the strike."""

from __future__ import annotations

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
