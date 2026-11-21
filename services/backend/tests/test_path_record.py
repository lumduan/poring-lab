"""path_record: the pure core of "record a path by walking" (docs/planning/
waypoints-npc-recording.md section 3 items 1-3, Amendment 1 b-d) -- the versioned path format and
its checks, thinning raw cell reads into waypoints (distance, turns, map changes, marks, the
minimum step), each leg proven on its map's walk grid with map_routes' own functions, the pure
edits, and "resume at the nearest waypoint AHEAD" by map_routes' own rules. Every grid here is
SYNTHETIC (no client data)."""

from __future__ import annotations

import dataclasses
import json
import random
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import map_routes as mr  # noqa: E402
import map_zones as mz  # noqa: E402
import path_record as pr  # noqa: E402

H, W = 40, 40


def fix_grid() -> Any:
    """40 x 40 cells, [y, x], y north: the walkable square x, y 2..37, a WALL at x 20 for y 2..30
    (its gap: y 31..37), and a SEALED ROOM x 31..37, y 2..9 (walls x 30 and y 10, no door)."""
    ok = np.zeros((H, W), dtype=bool)
    ok[2:38, 2:38] = True
    ok[2:31, 20] = False
    ok[2:11, 30] = False
    ok[10, 30:38] = False
    return ok


def wp(x: int, y: int, r: int = 2, mark: bool = False) -> pr.Waypoint:
    return pr.Waypoint(x, y, r, mark)


def leg(m: str, cells: Any, ex: pr.Exit = pr.END, r: int = 2) -> pr.Leg:
    return pr.Leg(m, tuple(wp(x, y, r) for x, y in cells), ex)


def two_legs() -> pr.WalkPath:
    return pr.WalkPath("to kafra", (
        leg("fix_a", [(5, 5), (15, 5), (15, 15)], pr.Exit("walk_exit", cell=(16, 16))),
        leg("fix_b", [(30, 30), (25, 30)]),
    ))  # fmt: skip


def walk(m: str, cells: Any, t0: float = 0.0, dt: float = 0.15) -> list[tuple[Any, ...]]:
    return [(t0 + k * dt, m, x, y, True) for k, (x, y) in enumerate(cells)]


def line(a: tuple[int, int], b: tuple[int, int]) -> list[tuple[int, int]]:
    return mr.seg_cells(a, b)


# --- the model and its file -----------------------------------------------------------------------


EXAMPLE = {
    "format": "poring-lab-path", "v": 1, "name": "to kafra",
    "legs": [
        {"map": "fix_a",
         "points": [{"x": 5, "y": 5, "r": 2}, {"x": 15, "y": 5, "r": 2, "mark": True},
                    {"x": 15, "y": 15, "r": 3}],
         "exit": {"kind": "walk_exit", "cell": [16, 16]}},
        {"map": "fix_b", "points": [{"x": 30, "y": 30, "r": 2}],
         "exit": {"kind": "npc_warp", "talk": "kafra warp"}},
        {"map": "fix_c", "points": [{"x": 8, "y": 9, "r": 2}], "exit": {"kind": "item_warp"}},
        {"map": "fix_d", "points": [{"x": 3, "y": 4, "r": 0}], "exit": {"kind": "end"}},
    ],
}  # fmt: skip


def test_the_file_round_trips_exactly() -> None:
    p = pr.from_json(EXAMPLE)
    assert p.legs[0].waypoints[1] == pr.Waypoint(15, 5, 2, True)
    assert p.legs[0].exit == pr.Exit("walk_exit", cell=(16, 16))
    assert p.legs[1].exit == pr.Exit("npc_warp", talk="kafra warp")
    assert p.legs[2].exit == pr.Exit("item_warp") and p.legs[3].exit == pr.END
    assert pr.to_json(p) == EXAMPLE
    text = pr.dumps(p)
    assert pr.loads(text) == p and pr.loads(text.encode()) == p
    assert json.loads(text) == EXAMPLE
    bare = text.replace("to kafra", "").replace("kafra warp", "")
    assert " " not in bare and "\n" not in bare  # canonical: no insignificant whitespace
    proc = pr.from_json({**EXAMPLE, "legs": [
        {"map": "fix_c", "points": [{"x": 8, "y": 9, "r": 2}],
         "exit": {"kind": "item_warp", "proc": "fly_home"}},
        EXAMPLE["legs"][3]]})  # fmt: skip
    assert proc.legs[0].exit.proc == "fly_home"


def test_any_script_names_are_data() -> None:
    thai = "ไปหาคาฟร่า"
    p = pr.rename(two_legs(), thai)
    assert p.name == thai and pr.loads(pr.dumps(p)).name == thai
    assert thai in pr.dumps(p)  # stored as is (UTF-8), not escaped
    hostile = 'x"); import os  #'  # a name is text: stored and read back, never run
    assert pr.loads(pr.dumps(pr.rename(two_legs(), hostile))).name == hostile


def _set(path: list[Any], value: Any) -> Any:
    d = json.loads(json.dumps(EXAMPLE))
    cur = d
    for k in path[:-1]:
        cur = cur[k]
    if value is KeyError:
        del cur[path[-1]]
    else:
        cur[path[-1]] = value
    return d


@pytest.mark.parametrize(("path", "value", "why"), [
    (["format"], "other", "format"),
    (["v"], 2, "version 2"),
    (["v"], True, "version True"),
    (["v"], "1", "version '1'"),
    (["extra"], 1, "unknown ['extra']"),
    (["name"], KeyError, "missing ['name']"),
    (["name"], "", "the path's name is empty"),
    (["name"], " to kafra", "spaces at its ends"),
    (["name"], "é", "NFC"),
    (["name"], "a\x07b", "control or format character"),
    (["name"], "a​b", "control or format character"),
    (["name"], "a‮b", "control or format character"),
    (["name"], "x" * 61, "longer than 60"),
    (["name"], 5, "not text"),
    (["legs"], [], "at least one leg"),
    (["legs"], {}, "legs is not a list"),
    (["legs", 0, "map"], "../etc", "is not a map name"),
    (["legs", 0, "map"], "", "is not a map name"),
    (["legs", 0, "extra"], 1, "unknown ['extra']"),
    (["legs", 0, "points"], [], "at least one point"),
    (["legs", 0, "points", 0, "x"], True, "two whole numbers"),
    (["legs", 0, "points", 0, "x"], -1, "outside 0 .. 1023"),
    (["legs", 0, "points", 0, "y"], 1024, "outside 0 .. 1023"),
    (["legs", 0, "points", 0, "x"], 5.0, "two whole numbers"),
    (["legs", 0, "points", 0, "r"], 16, "radius 16"),
    (["legs", 0, "points", 0, "r"], -1, "radius -1"),
    (["legs", 0, "points", 0, "r"], KeyError, "missing ['r']"),
    (["legs", 0, "points", 0, "mark"], 1, "mark is not true or false"),
    (["legs", 0, "points", 0, "color"], "red", "unknown ['color']"),
    (["legs", 0, "points", 1, "x"], 5, "repeats the one before it"),
    (["legs", 0, "exit", "kind"], "teleport", "kind 'teleport'"),
    (["legs", 0, "exit", "cell"], KeyError, "warp cell is not a cell"),
    (["legs", 0, "exit", "cell"], [1], "is not a cell [x, y]"),
    (["legs", 0, "exit", "talk"], "x", "kind walk_exit takes no talk"),
    (["legs", 1, "exit", "talk"], KeyError, "talk name is not text"),
    (["legs", 1, "exit", "talk"], " kafra", "talk name has spaces"),
    (["legs", 2, "exit", "proc"], "fly home", "not a function name"),
    (["legs", 2, "exit", "cell"], [1, 2], "kind item_warp takes no cell"),
    (["legs", 1, "exit", "kind"], "end", "kind end takes no talk"),
    (["legs", 2, "exit", "kind"], "end", "only the last leg ends the path"),
    (["legs", 3, "exit", "kind"], "item_warp", "the last leg: its exit is end"),
    (["legs", 3, "exit", "cell"], [1, 2], "kind end takes no cell"),
])  # fmt: skip
def test_a_wrong_file_is_refused(path: list[Any], value: Any, why: str) -> None:
    with pytest.raises(pr.PathError, match=None) as exc:
        pr.from_json(_set(path, value))
    assert why in str(exc.value), str(exc.value)


def test_the_limits_and_unreadable_text_are_refused() -> None:
    many = {**EXAMPLE, "legs": [EXAMPLE["legs"][1]] * 32 + [EXAMPLE["legs"][3]]}
    with pytest.raises(pr.PathError, match="33 legs"):
        pr.from_json(many)
    pts = [{"x": i % 1000, "y": i // 1000, "r": 2} for i in range(1001)]
    with pytest.raises(pr.PathError, match="1001 points"):
        pr.from_json({**EXAMPLE, "legs": [{"map": "fix_a", "points": pts,
                                           "exit": {"kind": "end"}}]})  # fmt: skip
    for bad in ("{", "[1, 2]", "null", "﻿{}"):
        with pytest.raises(pr.PathError):
            pr.loads(bad)
    with pytest.raises(pr.PathError, match="larger than"):
        pr.loads(" " * (pr.LOADS_MAX_BYTES + 1))


def test_problem_of_never_raises_and_names_the_fault() -> None:
    assert pr.problem_of(two_legs()) is None
    assert pr.problem_of(42) == "not a path"
    assert pr.problem_of(pr.WalkPath(3, ())) == "the path's name is not text"  # type: ignore[arg-type]
    assert pr.problem_of(pr.WalkPath("p", ())) == "a path has at least one leg"
    bad_leg = pr.WalkPath("p", (pr.Leg("fix_a", (wp(1, 1), "x")),))  # type: ignore[arg-type]
    assert pr.problem_of(bad_leg) == "leg 0 (fix_a) point 1 is not a waypoint"
    tup = pr.WalkPath("p", (pr.Leg("fix_a", (wp(1, 1),), pr.Exit("end", cell=(1, 1))),))
    assert pr.problem_of(tup) == "leg 0 (fix_a)'s exit: kind end takes no cell"
    with pytest.raises(pr.PathError, match="not a path"):
        pr.checked(42)  # type: ignore[arg-type]


def test_a_function_name_is_the_flow_irs_own() -> None:
    """item_warp's ``proc`` names a flow FUNCTION: the same pattern as poring_flow.ir.NAME."""
    from poring_flow import ir

    assert f"^{pr.PROC_NAME.pattern}$" == ir.NAME
    assert set(pr.EXIT_KINDS) - {"end"} == {"walk_exit", "npc_warp", "item_warp"}


# --- thinning (Amendment 1 b) ---------------------------------------------------------------------


def cells_of(t: pr.Thinned, k: int = 0) -> list[tuple[int, int]]:
    return [w.cell for w in t.path.legs[k].waypoints]


def test_a_straight_walk_keeps_a_point_every_n_cells() -> None:
    t = pr.thin(walk("fix_a", line((0, 5), (30, 5))), " east ")
    assert cells_of(t) == [(0, 5), (10, 5), (20, 5), (30, 5)]
    assert t.path.name == "east" and t.notes == () and t.dropped == 0
    assert all(w.radius == pr.DEFAULT_RADIUS == mr.REACH_TOL for w in t.path.legs[0].waypoints)
    assert t.path.legs[0].exit == pr.END


def test_a_turn_is_kept_where_it_is() -> None:
    t = pr.thin(walk("fix_a", line((0, 5), (14, 5)) + line((14, 6), (14, 30))), "L")
    assert cells_of(t) == [(0, 5), (10, 5), (14, 5), (14, 15), (14, 25), (14, 30)]


def test_a_turn_back_keeps_its_tip() -> None:
    t = pr.thin(walk("fix_a", line((0, 5), (15, 5)) + line((14, 5), (2, 5))), "back")
    assert (15, 5) in cells_of(t)
    assert cells_of(t) == [(0, 5), (10, 5), (15, 5), (5, 5), (2, 5)]


def test_a_staircase_line_is_not_a_turn() -> None:
    """An 8-direction walk of a 1:2 slope zig-zags cell by cell; over turn_span it is straight."""
    cells = [(i, i // 2) for i in range(0, 41)]
    assert max(pr.turn_angles(cells, 3)) < pr.DEFAULTS.turn_deg
    t = pr.thin(walk("fix_a", cells), "slope")
    assert cells_of(t) == [(0, 0), (10, 5), (20, 10), (30, 15), (40, 20)]


def test_unconfirmed_reads_are_dropped_and_standing_adds_nothing() -> None:
    reads = walk("fix_a", line((0, 5), (12, 5)))
    reads[3:3] = [(0.40, None, None, None, False), (0.41, "far_map", 900, 900, False)]
    reads += [(9.0 + k, "fix_a", 12, 5, True) for k in range(50)]  # standing at the end
    reads += [(60.0 + k * 0.1, "fix_a", 12 + k % 2, 5, True) for k in range(40)]  # a 1-cell jitter
    t = pr.thin(reads, "drop")
    assert t.dropped == 2 and len(t.path.legs) == 1
    assert cells_of(t) == [(0, 5), (10, 5), (13, 5)]  # the jitter's last cell ends the path


def test_the_settings_are_passed_in() -> None:
    reads = walk("fix_a", line((0, 5), (14, 5)) + line((14, 6), (14, 30)))
    s = pr.ThinSettings(every_cells=6, min_step=2, turn_deg=170.0, turn_span=3, radius=4)
    t = pr.thin(reads, "L", settings=s)
    # (14, 29) is 1 cell from the end, closer than min_step 2: not kept
    assert cells_of(t) == [(0, 5), (6, 5), (12, 5), (14, 11), (14, 17), (14, 23), (14, 30)]
    assert {w.radius for w in t.path.legs[0].waypoints} == {4}
    loose = pr.thin(reads, "L", settings=dataclasses.replace(pr.DEFAULTS, every_cells=50))
    assert cells_of(loose) == [(0, 5), (14, 5), (14, 30)]  # the turn alone
    off = pr.thin(reads, "L", settings=dataclasses.replace(pr.DEFAULTS, every_cells=50,
                                                           turn_deg=180))  # fmt: skip
    assert cells_of(off) == [(0, 5), (14, 30)]


@pytest.mark.parametrize(("change", "why"), [
    ({"every_cells": 0}, "every_cells 0"),
    ({"min_step": 1.5}, "min_step 1.5"),
    ({"turn_span": True}, "turn_span True"),
    ({"turn_deg": 0}, "turn_deg 0"),
    ({"turn_deg": 181}, "turn_deg 181"),
    ({"turn_deg": float("nan")}, "turn_deg nan"),
    ({"radius": 16}, "radius 16"),
])  # fmt: skip
def test_bad_settings_are_refused(change: dict[str, Any], why: str) -> None:
    s = dataclasses.replace(pr.DEFAULTS, **change)
    assert why in str(pr.settings_problem(s))
    with pytest.raises(pr.PathError, match="settings: "):
        pr.thin(walk("fix_a", [(1, 1)]), "x", settings=s)
    assert pr.settings_problem(pr.DEFAULTS) is None


def test_the_minimum_step_holds_except_at_a_mark() -> None:
    reads = walk("fix_a", line((0, 5), (11, 5)) + line((11, 6), (11, 20)))
    turn_only = dataclasses.replace(pr.DEFAULTS, every_cells=50)
    assert cells_of(pr.thin(reads, "L", settings=turn_only)) == [(0, 5), (11, 5), (11, 20)]
    t = pr.thin(reads, "L")  # the corner is 1 cell from the kept (10, 5): closer than 3
    assert cells_of(t) == [(0, 5), (10, 5), (11, 15), (11, 20)]
    marked = pr.thin(reads, "L", marks=[reads[11][0] + 0.01])  # read 11 = (11, 5), the corner
    # the mark is kept; the distance point (10, 5) 1 cell before it is not (the next protected)
    assert cells_of(marked) == [(0, 5), (11, 5), (11, 15), (11, 20)]
    assert [w.mark for w in marked.path.legs[0].waypoints] == [False, True, False, False]
    near = pr.thin(reads, "L", marks=[reads[9][0], reads[11][0]])  # (9, 5) and (11, 5): marks
    assert cells_of(near) == [(0, 5), (9, 5), (11, 5), (11, 15), (11, 20)]  # 2 apart: both kept


def test_a_mark_takes_the_read_nearest_in_time() -> None:
    reads = walk("fix_a", line((0, 5), (20, 5)), dt=1.0)
    for m, cell in ((4.4, (4, 5)), (4.5, (4, 5)), (4.6, (5, 5)), (-3.0, (0, 5)), (99.0, (20, 5))):
        t = pr.thin(reads, "m", marks=[m])
        marks = [w.cell for w in t.path.legs[0].waypoints if w.mark]
        assert marks == [cell], (m, marks)
    with pytest.raises(pr.PathError, match="mark 0"):
        pr.thin(reads, "m", marks=[float("inf")])


def test_a_mark_back_on_a_kept_cell_merges_into_it() -> None:
    reads = walk("fix_a", [(5, 5), (6, 5), (5, 5)])
    t = pr.thin(reads, "m", marks=[reads[2][0]])
    assert t.path.legs[0].waypoints == (pr.Waypoint(5, 5, 2, True),)


def test_a_map_change_ends_the_leg_and_assumes_a_walk_exit() -> None:
    a = walk("fix_a", line((5, 5), (25, 5)))
    b = walk("fix_b", line((30, 30), (30, 10)), t0=10.0)
    c = walk("fix_a", line((3, 3), (8, 3)), t0=20.0)
    t = pr.thin(a + b + c, "maps")
    assert [lg.map for lg in t.path.legs] == ["fix_a", "fix_b", "fix_a"]
    assert cells_of(t, 0) == [(5, 5), (15, 5), (25, 5)]
    assert cells_of(t, 1) == [(30, 30), (30, 20), (30, 10)]
    assert cells_of(t, 2) == [(3, 3), (8, 3)]
    assert t.path.legs[0].exit == pr.Exit("walk_exit", cell=(25, 5))
    assert t.path.legs[1].exit == pr.Exit("walk_exit", cell=(30, 10))
    assert t.path.legs[2].exit == pr.END
    assert len(t.notes) == 2 and "is assumed (check it)" in t.notes[0]
    assert "changed to fix_b" in t.notes[0] and "[25, 5]" in t.notes[0]


def test_a_map_change_is_kept_even_one_cell_from_the_last_point() -> None:
    a = walk("fix_a", line((5, 5), (16, 5)))  # (15, 5) kept by distance, (16, 5) ends the leg
    b = walk("fix_b", [(30, 30), (31, 30)], t0=10.0)
    t = pr.thin(a + b, "near")
    assert cells_of(t, 0) == [(5, 5), (16, 5)]  # (15, 5) is 1 cell from the leg's end: not kept
    assert cells_of(t, 1) == [(30, 30), (31, 30)]  # the ends of a leg: closer than min_step


def test_the_leave_events_name_how_each_map_was_left() -> None:
    a = walk("fix_a", line((5, 5), (25, 5)))  # t 0 .. 3.0
    b = walk("fix_b", line((30, 30), (30, 10)), t0=10.0)  # t 10 .. 13.0
    c = walk("fix_c", [(3, 3)], t0=20.0)
    talk, wing = pr.Exit("npc_warp", talk="kafra warp"), pr.Exit("item_warp")
    t = pr.thin(a + b + c, "maps", leaves=[(2.0, pr.Exit("npc_warp", talk="hello")), (3.5, talk),
                                           (12.0, wing), (25.0, pr.Exit("item_warp"))])  # fmt: skip
    assert t.path.legs[0].exit == talk and t.path.legs[1].exit == wing
    assert t.path.legs[2].exit == pr.END
    assert any("leg 0: a leave by npc_warp at t=2 is not used" in n for n in t.notes)
    assert any("t=25 came after the last map change" in n for n in t.notes)
    early = pr.thin(a + b + c, "maps", leaves=[(-1.0, talk), (0.5, wing)])
    assert early.path.legs[0].exit == wing  # before the first read: the first leg; the latest
    assert pr.thin(a + b + c, "maps", leaves=[(0.5, wing), (-1.0, talk)]).path == early.path
    with pytest.raises(pr.PathError, match="end is not a way to leave"):
        pr.thin(a + b, "x", leaves=[(1.0, pr.END)])
    with pytest.raises(pr.PathError, match="talk name is empty"):
        pr.thin(a + b, "x", leaves=[(1.0, pr.Exit("npc_warp", talk=""))])
    with pytest.raises(pr.PathError, match="leave 0 is not"):
        pr.thin(a + b, "x", leaves=[(1.0,)])  # type: ignore[list-item]
    with pytest.raises(pr.PathError, match="leave 0 is not an exit"):
        pr.thin(a + b, "x", leaves=[(1.0, "npc_warp")])  # type: ignore[list-item]


@pytest.mark.parametrize(("reads", "why"), [
    ([], "no confirmed read"),
    ([(0.0, "fix_a", 1, 1, False)], "no confirmed read"),
    ([(0.0, "fix_a", 1, 1)], "read 0 is not (t, map, x, y, confirmed)"),
    (["abcde"], "read 0 is not"),
    ([(0.0, "fix_a", 1, 1, 1)], "confirmed is not true or false"),
    ([(float("nan"), "fix_a", 1, 1, True)], "not a finite number"),
    ([(0.0, None, 1, 1, True)], "map None"),
    ([(0.0, "fix_a", -1, 1, True)], "outside 0 .. 1023"),
    ([(0.0, "fix_a", 1.0, 1, True)], "two whole numbers"),
    ([(1.0, "fix_a", 1, 1, True), (0.5, "fix_a", 2, 1, True)], "not in time order"),
])  # fmt: skip
def test_bad_reads_are_refused(reads: Any, why: str) -> None:
    with pytest.raises(pr.PathError) as exc:
        pr.thin(reads, "x")
    assert why in str(exc.value), str(exc.value)


def test_a_bad_name_or_too_many_points_refuse_the_recording() -> None:
    with pytest.raises(pr.PathError, match="the path's name is empty"):
        pr.thin(walk("fix_a", [(1, 1)]), "   ")
    with pytest.raises(pr.PathError, match="the path's name is not text"):
        pr.thin(walk("fix_a", [(1, 1)]), None)  # type: ignore[arg-type]
    s = pr.ThinSettings(every_cells=1, min_step=1)  # every cell kept: 1001 points
    with pytest.raises(pr.PathError, match="1001 points, a leg has at most 1000"):
        pr.thin(walk("fix_a", line((0, 5), (1000, 5))), "long", settings=s)


def random_walk(seed: int, n: int) -> list[tuple[int, int]]:
    rnd = random.Random(seed)
    x, y, out = 100, 100, [(100, 100)]
    dx, dy = 1, 0
    for _ in range(n):
        if rnd.random() < 0.15:
            dx, dy = rnd.choice([(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1)])
        x, y = min(max(x + dx, 0), 200), min(max(y + dy, 0), 200)
        out.append((x, y))
    return out


@pytest.mark.parametrize("seed", range(6))
def test_the_thinning_rules_hold_on_a_random_walk(seed: int) -> None:
    """The rules as properties of thin_track on a random walk: the kept points are the track's
    own, in order, from its first to its last cell; no two consecutive ones closer than min_step
    unless one is a mark or an end; a point is kept before she gets every_cells away (unless the
    next protected point is near); every mark is kept and flagged. thin() keeps the same cells."""
    cells = random_walk(seed, 600)
    track = [c for k, c in enumerate(cells) if k == 0 or c != cells[k - 1]]
    n = len(track)
    rnd = random.Random(seed + 100)
    marked = set(rnd.sample(range(n), 5))
    s = pr.ThinSettings(every_cells=8, min_step=3, turn_deg=50.0, turn_span=3)
    kept = pr.thin_track(track, marked, s)
    idx = [i for i, _ in kept]
    assert idx == sorted(set(idx)) and idx[0] == 0 and track[idx[-1]] == track[-1]
    flag = dict(kept)
    for m in marked:  # kept, or merged into the kept point on its cell just before it
        assert flag.get(m) or any(flag[j] and track[j] == track[m] for j in idx if j < m), m
    prot = sorted({0, n - 1} | marked)
    for i, j in zip(idx, idx[1:], strict=False):
        protected = i in prot or j in prot
        assert protected or mr.cheb(track[i], track[j]) >= s.min_step, (i, j)
        for k in range(i + 1, j):
            if k in marked:
                continue
            nxt = next(p for p in prot if p > k)
            far = mr.cheb(track[k], track[i]) >= s.every_cells
            assert not far or mr.cheb(track[k], track[nxt]) < s.min_step, (i, k, j)
    reads = walk("fix_a", cells, dt=0.2)
    run_read = [k for k in range(len(cells)) if k == 0 or cells[k] != cells[k - 1]]  # a run's 1st
    assert len(run_read) == n
    t = pr.thin(reads, "walk", marks=[reads[run_read[m]][0] for m in marked], settings=s)
    assert t.path.legs[0].cells() == tuple(track[i] for i in idx)
    assert [w.mark for w in t.path.legs[0].waypoints] == [m for _, m in kept]


def test_thin_track_refuses_a_track_with_repeats() -> None:
    with pytest.raises(pr.PathError, match="repeats"):
        pr.thin_track([(1, 1), (1, 1)], ())
    with pytest.raises(pr.PathError, match="outside the track"):
        pr.thin_track([(1, 1), (2, 1)], [5])
    assert pr.thin_track([(1, 1)], [0]) == [(0, True)]


# --- the proof (section 3 item 2) -----------------------------------------------------------------


def test_a_good_path_proves_with_each_segments_length() -> None:
    p = two_legs()
    rep = pr.prove(p, {"fix_a": fix_grid(), "fix_b": fix_grid()})
    assert rep["ok"] and rep["problems"] == []
    a = rep["legs"][0]
    assert a["leg"] == 0 and a["map"] == "fix_a"
    assert [s["status"] for s in a["segments"]] == ["ok", "ok"]
    assert [(s["from"], s["to"], s["steps"], s["cost"]) for s in a["segments"]] == [
        (0, 1, 10, 10.0), (1, 2, 10, 10.0)]  # fmt: skip
    assert a["exit"] == {"cell": [16, 16], "why": None, "status": "ok", "steps": 1, "cost": 1.4}
    assert a["total_steps"] == 21 and a["total_cost"] == 21.4
    assert [pt["status"] for pt in a["points"]] == ["ok"] * 3
    assert rep["legs"][1]["exit"] is None and rep["legs"][1]["total_steps"] == 5


def test_a_broken_segment_and_a_closed_point_are_named() -> None:
    p = pr.WalkPath("bad", (leg("fix_a", [(10, 10), (34, 5), (20, 15), (25, 25)]),))
    rep = pr.prove(p, {"fix_a": fix_grid()})
    a = rep["legs"][0]
    assert not rep["ok"]
    assert [s["status"] for s in a["segments"]] == ["broken", "broken", "broken"]
    assert [pt["status"] for pt in a["points"]] == ["ok", "ok", "closed", "ok"]
    assert a["points"][2]["why"] == "not walkable"
    assert a["total_steps"] is None and a["total_cost"] is None
    assert rep["problems"][0] == "leg 0 (fix_a): point 2 [20, 15]: not walkable"
    assert rep["problems"][1].startswith("leg 0 (fix_a): segment 0 -> 1 ([10, 10] -> [34, 5]): "
                                         "not connected on the route grid")  # fmt: skip
    around = pr.WalkPath("around", (leg("fix_a", [(10, 10), (30, 20)]),))
    seg = pr.prove(around, {"fix_a": fix_grid()})["legs"][0]["segments"][0]
    assert seg["status"] == "ok" and seg["steps"] > 20  # walked round the wall's end, not through


def test_the_proof_is_map_routes_own() -> None:
    """Parity: the same waypoints as a map_routes PATH route give the same steps, costs and
    number of problems through map_routes.prove (zones too)."""
    box = ((4, 20), (9, 20), (9, 25), (4, 25))
    zones = mz.Zones(map="fix_a", reviewed_by="batt", reviewed="2026-11-22", no_cross=(),
                     no_enter=(mz.NoEnter("ne0", "n", box),))  # fmt: skip
    cells = [(5, 5), (15, 5), (15, 15), (6, 22), (25, 33), (34, 5), (12, 30)]
    p = pr.WalkPath("par", (leg("fix_a", cells),))
    for z in (None, zones):
        ours = pr.prove_leg(p.legs[0], fix_grid(), z)
        theirs = mr.prove(mr.Routes(map="fix_a", reviewed_by="batt", reviewed="2026-11-22",
                                    source="synthetic",
                                    routes=(mr.Route("leg", "path", "n", tuple(cells)),)),
                          fix_grid(), z)  # fmt: skip
        legs = theirs["routes"][0]["legs"]
        assert [(s["steps"], s["cost"]) for s in ours["segments"]] == [
            (s["steps"], s["cost"]) for s in legs]  # fmt: skip
        assert len(ours["problems"]) == len(theirs["problems"]) > 0
        assert ours["total_steps"] == theirs["routes"][0]["total_steps"]
    zp = pr.prove_leg(p.legs[0], fix_grid(), zones)
    assert zp["points"][3]["why"] == "inside no-enter area 'ne0'"


def test_a_zone_sealed_point_is_closed_as_map_routes_says() -> None:
    gap = ((20, 30), (20, 38))
    zones = mz.Zones(map="fix_a", reviewed_by="batt", reviewed="2026-11-22",
                     no_cross=(mz.NoCross("nc0", "n", gap),), no_enter=())  # fmt: skip
    p = pr.WalkPath("seal", (leg("fix_a", [(10, 10), (25, 10)]),))
    rep = pr.prove(p, {"fix_a": fix_grid()}, {"fix_a": zones})  # the line shuts the wall's gap
    a = rep["legs"][0]
    assert [pt["status"] for pt in a["points"]] == ["ok", "closed"]
    assert a["points"][1]["why"] == "sealed off by the zones"  # the smaller (east) piece
    assert a["segments"][0]["status"] == "broken"
    assert pr.prove(p, {"fix_a": fix_grid()})["ok"]  # without the zones: connected


def test_the_exit_cell_is_proven_too() -> None:
    closed = pr.WalkPath("x", (
        leg("fix_a", [(5, 5), (15, 5)], pr.Exit("walk_exit", cell=(20, 5))),
        leg("fix_b", [(30, 30)])))  # fmt: skip
    rep = pr.prove(closed, {"fix_a": fix_grid(), "fix_b": fix_grid()})
    ex = rep["legs"][0]["exit"]
    assert ex["status"] == "closed" and ex["why"] == "not walkable"
    assert "the exit's warp cell [20, 5]: not walkable" in rep["problems"][0]
    sealed = dataclasses.replace(closed, legs=(
        leg("fix_a", [(5, 5), (15, 5)], pr.Exit("walk_exit", cell=(33, 5))),
        closed.legs[1]))  # fmt: skip
    rep = pr.prove(sealed, {"fix_a": fix_grid(), "fix_b": fix_grid()})
    assert rep["legs"][0]["exit"]["status"] == "broken"
    assert "point 1 -> the exit's warp cell [33, 5]: not connected" in rep["problems"][0]


def test_a_map_without_a_grid_is_not_proven() -> None:
    rep = pr.prove(two_legs(), {"fix_a": fix_grid()})
    assert not rep["ok"] and rep["problems"] == [
        "leg 1 (fix_b): no walk grid for this map: not proven"]  # fmt: skip
    b = rep["legs"][1]
    assert [s["status"] for s in b["segments"]] == ["unproven"]
    assert [pt["status"] for pt in b["points"]] == ["unproven", "unproven"]
    assert rep["legs"][0]["ok"]
    rep = pr.prove(two_legs(), {"fix_b": fix_grid()})
    assert rep["legs"][0]["exit"]["status"] == "unproven"
    with pytest.raises(pr.PathError):
        pr.prove(pr.WalkPath("", two_legs().legs), {})


def test_an_off_map_point_is_closed() -> None:
    p = pr.WalkPath("off", (leg("fix_a", [(5, 5), (45, 5)]),))
    a = pr.prove(p, {"fix_a": fix_grid()})["legs"][0]
    assert a["points"][1]["why"] == "off the map (40 x 40 cells)"
    assert a["segments"][0]["status"] == "broken"


# --- edits (section 3 item 2) ---------------------------------------------------------------------


def test_the_edits_return_a_new_path() -> None:
    p = two_legs()
    before = pr.dumps(p)
    moved = pr.move_point(p, 0, 1, (16, 6))
    assert moved.legs[0].cells() == ((5, 5), (16, 6), (15, 15)) and moved.legs[1] == p.legs[1]
    marked = pr.WalkPath(p.name, (dataclasses.replace(p.legs[0], waypoints=(
        wp(5, 5), wp(15, 5, 4, True), wp(15, 15))), p.legs[1]))  # fmt: skip
    assert pr.move_point(marked, 0, 1, (9, 9)).legs[0].waypoints[1] == pr.Waypoint(9, 9, 4, True)
    ins = pr.insert_point(p, 0, 1, [10, 5])
    assert ins.legs[0].cells() == ((5, 5), (10, 5), (15, 5), (15, 15))
    assert pr.insert_point(p, 0, 3, (20, 20), radius=5).legs[0].waypoints[3] == wp(20, 20, 5)
    assert pr.insert_point(p, 1, 0, (31, 31)).legs[1].cells()[0] == (31, 31)
    assert pr.delete_point(p, 0, 0).legs[0].cells() == ((15, 5), (15, 15))
    assert pr.set_radius(p, 0, 2, 0).legs[0].waypoints[2].radius == 0
    talk = pr.Exit("npc_warp", talk="kafra warp")
    assert pr.set_exit(p, 0, talk).legs[0].exit == talk
    assert pr.rename(p, "  é ").name == "é"  # NFC, the ends' spaces removed
    assert pr.dumps(p) == before  # nothing was changed in place


@pytest.mark.parametrize(("edit", "why"), [
    (lambda p: pr.move_point(p, 0, 1, (5, 5)), "point 1 [5, 5] repeats the one before it"),
    (lambda p: pr.move_point(p, 0, 3, (1, 1)), "has no point 3"),
    (lambda p: pr.move_point(p, 2, 0, (1, 1)), "no leg 2"),
    (lambda p: pr.move_point(p, 0, 0, (-1, 1)), "outside 0 .. 1023"),
    (lambda p: pr.move_point(p, 0, 0, (1,)), "is not (x, y)"),
    (lambda p: pr.move_point(p, True, 0, (1, 1)), "no leg True"),
    (lambda p: pr.insert_point(p, 0, 4, (1, 1)), "has no point 4"),
    (lambda p: pr.insert_point(p, 0, 1, (1, 1), radius=99), "radius 99"),
    (lambda p: pr.delete_point(pr.delete_point(p, 1, 0), 1, 0), "keeps at least one point"),
    (lambda p: pr.delete_point(pr.move_point(p, 0, 2, (5, 5)), 0, 1), "repeats"),
    (lambda p: pr.set_radius(p, 0, 0, -1), "radius -1"),
    (lambda p: pr.set_exit(p, 0, pr.END), "only the last leg ends the path"),
    (lambda p: pr.set_exit(p, 1, pr.Exit("item_warp")), "the last leg: its exit is end"),
    (lambda p: pr.set_exit(p, 0, pr.Exit("walk_exit")), "warp cell is not a cell"),
    (lambda p: pr.rename(p, "\t"), "the path's name is empty"),
    (lambda p: pr.rename(p, 5), "not text"),
])  # fmt: skip
def test_an_edit_that_breaks_the_path_is_refused(edit: Any, why: str) -> None:
    with pytest.raises(pr.PathError) as exc:
        edit(two_legs())
    assert why in str(exc.value), str(exc.value)


# --- walking (Amendment 1 d) ----------------------------------------------------------------------


def test_the_leg_is_map_routes_open_route() -> None:
    r = pr.leg_route(two_legs(), 0)
    assert r == mr.Route("leg-0", "path", "fix_a", ((5, 5), (15, 5), (15, 15)))
    assert not r.loop and mr.next_index(r, 2) is None


def test_entry_and_resume_are_map_routes_rules_with_equal_radii() -> None:
    p = pr.WalkPath("w", (leg("fix_a", [(5, 5), (15, 5), (15, 15), (5, 15), (5, 25)]),))
    r = pr.leg_route(p, 0)
    for x in range(0, 30, 2):
        for y in range(0, 30, 2):
            assert pr.ahead(p, 0, "fix_a", (x, y)) == mr.entry_index(r, (x, y), 2)
            for last in range(5):
                assert pr.ahead(p, 0, "fix_a", (x, y), last) == mr.resume_index(r, (x, y), last, 2)


def test_ahead_never_turns_back_and_ends_with_the_leg() -> None:
    p = two_legs()
    assert pr.ahead(p, 0, "fix_a", (4, 5)) == 1  # at the first point: the next one
    assert pr.ahead(p, 0, "fix_a", (14, 6), last=0) == 2  # point 1 reached: point 2
    assert pr.ahead(p, 0, "fix_a", (5, 5), last=1) == 2  # back at the start: still ahead
    assert pr.ahead(p, 0, "fix_a", (15, 14), last=1) is None  # the last point: the exit next
    assert pr.ahead(p, 0, "fix_a", (5, 5), last=2) is None
    assert pr.ahead(p, 1, "fix_b", (29, 30)) == 1


def test_each_points_own_radius_decides_when_it_is_reached() -> None:
    near = (4, 5)  # 1 cell from point 0, beside the segment 0 -> 1
    tight = pr.WalkPath("w", (pr.Leg("fix_a", (wp(5, 5, 0), wp(15, 5), wp(15, 15))),))
    assert pr.ahead(two_legs(), 0, "fix_a", near) == 1
    assert pr.ahead(tight, 0, "fix_a", near) == 0  # radius 0: not reached until on it
    assert pr.reached(two_legs(), 0, 0, near) and not pr.reached(tight, 0, 0, near)
    wide = pr.WalkPath("w", (pr.Leg("fix_a", (wp(5, 5), wp(15, 5, 6), wp(15, 15))),))
    assert pr.ahead(wide, 0, "fix_a", (10, 6), last=0) == 2  # within 6 of point 1
    assert pr.ahead(two_legs(), 0, "fix_a", (10, 6), last=0) == 1


def test_another_map_stops_with_the_words() -> None:
    with pytest.raises(pr.WrongMap) as exc:
        pr.ahead(two_legs(), 1, "fix_a", (30, 30))
    assert str(exc.value) == "she is on fix_a, the path expects fix_b"
    assert isinstance(exc.value, pr.PathError)
    with pytest.raises(pr.PathError, match="has no point 7"):
        pr.ahead(two_legs(), 0, "fix_a", (5, 5), last=7)
    with pytest.raises(pr.PathError, match="no leg 5"):
        pr.ahead(two_legs(), 5, "fix_a", (5, 5))
