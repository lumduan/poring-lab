"""SEARCH GAP (scripts/search_gap.py): the pure helpers on SYNTHETIC data only. The properties the
analysis relies on: positions along a walk (diagonals x 1.4, the newest segment wins), one-to-one
nearest-first matching, visits split on gaps, the swept area counts each cell once (and only the
accepted ones), FIGHT / LOOT intervals from packets, and the world built from appear / vanish
(a walk re-sent to a unit already in view is not a new life; a walk begun before it came into
view starts at its move_start_tick)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
NS = 10**9


@pytest.fixture(scope="module")
def sg() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("search_gap", SCRIPTS / "search_gap.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["search_gap"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_walk_at_straight_and_diagonal(sg: ModuleType) -> None:
    t0 = 1_000 * 10**6
    assert sg.walk_at((0, 0), (3, 0), t0, 100.0, t0) == (0.0, 0.0)
    assert sg.walk_at((0, 0), (3, 0), t0, 100.0, t0 + 150 * 10**6) == pytest.approx((1.5, 0.0))
    assert sg.walk_at((0, 0), (3, 0), t0, 100.0, t0 + 10 * NS) == (3.0, 0.0)
    # a diagonal step takes 140 ms at 100 ms / cell
    assert sg.walk_at((0, 0), (1, 1), t0, 100.0, t0 + 70 * 10**6) == pytest.approx((0.5, 0.5))
    assert sg.walk_end((0, 0), (2, 1), t0, 100.0) == t0 + 240 * 10**6


def test_walker_newest_segment_wins(sg: ModuleType) -> None:
    w = sg.Walker()
    w.add(10 * NS, (0, 0), (0, 0), 150.0)
    w.add(12 * NS, (5, 5), (8, 5), 100.0)
    assert w.at(9 * NS) is None
    assert w.at(11 * NS) == (0.0, 0.0)
    assert not w.moving(11 * NS)
    assert w.at(12 * NS + 100 * 10**6) == pytest.approx((6.0, 5.0))
    assert w.moving(12 * NS + 100 * 10**6)
    assert not w.moving(13 * NS)
    w.add(11 * NS, (1, 1), (1, 1), 150.0)  # inserted in time order
    assert w.at(11 * NS + 1) == (1.0, 1.0)


def test_greedy_match_is_one_to_one_nearest_first(sg: ModuleType) -> None:
    pts = [(100.0, 100.0), (110.0, 100.0), (500.0, 500.0)]
    feet = [(108.0, 100.0), (300.0, 300.0)]
    m = sg.greedy_match(pts, feet, 40.0)
    # the nearer point takes the box; the other has none left within 40 px
    assert m == {1: (0, pytest.approx(2.0))}
    assert sg.greedy_match(pts, [], 40.0) == {}


def test_visits_split_on_gaps(sg: ModuleType) -> None:
    ts = [0, int(0.3 * NS), int(0.6 * NS), int(2.0 * NS), int(2.3 * NS), int(9 * NS)]
    assert sg.visits(ts, 1.0) == [(0, 3), (3, 5), (5, 6)]
    assert sg.visits([], 1.0) == []


def test_sweep_counts_each_cell_once_and_only_accepted(sg: ModuleType) -> None:
    offs = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
    seen: set[tuple[int, int]] = set()
    assert sg.sweep([(0, 0)], offs, seen) == 9
    assert sg.sweep([(0, 0), (1, 0)], offs, seen) == 3  # one new column
    assert sg.sweep([(0, 0)], offs, set(), lambda q: q[0] >= 0) == 6


def test_screen_ui_ring(sg: ModuleType) -> None:
    assert sg.on_screen(640, 360) and not sg.on_screen(2, 360) and not sg.on_screen(640, 10)
    # the body (20 px above the feet) decides
    assert sg.under_ui(100, 330, [(0, 0, 220, 326)])
    assert not sg.under_ui(100, 350, [(0, 0, 220, 326)])
    assert sg.ring_of(0) == "0-3" and sg.ring_of(9) == "7-9" and sg.ring_of(15) == ">14"


def test_footprint_from_a_projector(sg: ModuleType) -> None:
    # a flat orthographic camera: 40 px a cell, the GM at the screen centre
    def project(offs: list[tuple[int, int]]) -> list[tuple[float, float]]:
        return [(640 + 40 * dx, 360 + 40 * dy) for dx, dy in offs]

    fp = sg.footprint_offsets(project, reach=30)
    assert (0, 0) in fp and (15, 0) in fp and (16, 0) not in fp
    assert (0, 8) in fp and (0, 9) not in fp and (0, -8) in fp and (0, -9) not in fp


def test_net_displacement(sg: ModuleType) -> None:
    pos = [(0.0, 0.0), (1.0, 0.0), None, (3.0, 1.0)]
    assert sg.net_displacement(pos, 2) == [2.0]  # (3, 1) vs (1, 0); None pairs are skipped


def ev(t: float, typ: str, **kw: object) -> dict[str, object]:
    return {"t_mono_ns": int(t * NS), "type": typ, **kw}


def test_busy_intervals_fight_and_loot(sg: ModuleType) -> None:
    events = [
        ev(10, "attack_request", target_gid=7),
        ev(10.5, "act", src_gid=sg.GM, target_gid=7, damage=100),
        ev(11.0, "entity_vanish", gid=7, reason=1),
        ev(12.0, "pickup_request", floor_id=1),
        ev(13.0, "pickup_request", floor_id=2),
        ev(30.0, "attack_request", target_gid=8),  # alone: + the 1 s tail
    ]
    fight, loot = sg.busy_intervals(events)
    assert fight == [(10 * NS, 11 * NS), (30 * NS, 31 * NS)]  # cut at its death
    assert loot == [(11 * NS, 13 * NS + 1)]


def mob(t: float, kind: str, a: tuple[int, int], b: tuple[int, int] | None = None,
        start_ms: int | None = None) -> dict[str, object]:  # fmt: skip
    e = ev(t, "entity_appear", objtype=5, gid=5, job=1002, kind=kind, x=a[0], y=a[1], speed=400)
    if b is not None:
        e.update(x1=b[0], y1=b[1], move_start_tick=start_ms)
    return e


def test_build_world_lives_and_walk_start(sg: ModuleType) -> None:
    # server_tick in ms == t_mono_ns / 1e6 (the shared monotonic clock)
    events = [
        ev(100.0, "self_move", server_tick=100_000, x0=10, y0=10, x1=12, y1=10),
        mob(101.0, "stand", (20, 10)),
        mob(102.0, "move", (20, 10), (24, 10), 102_000),  # a walk re-sent while in view
        ev(105.0, "entity_vanish", gid=5, reason=0),
        mob(110.0, "move", (30, 10), (34, 10), 109_200),  # came in mid-walk, begun 0.8 s before
    ]
    w = sg.build_world(events)
    assert w.lives[5] == [(101 * NS, 105 * NS, 0), (110 * NS, None, -1)]
    assert w.alive_at(5, 103 * NS) and not w.alive_at(5, 107 * NS)
    assert w.mobs[5].at(102 * NS + 400 * 10**6) == pytest.approx((21.0, 10.0))
    assert w.mobs[5].at(110 * NS) == pytest.approx((32.0, 10.0))
    assert w.gm_moving == [(100 * NS, 100 * NS + 300 * 10**6)]
