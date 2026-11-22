"""path_blocks: the recorder as a BLOCK GENERATOR (docs/planning/waypoints-npc-recording.md
Amendment 5) -- thinning raw cell reads into points, one run per map stay; the run as ordinary
walk_to blocks in the flow IR's own shape; a pure proposal that inserts them into a map node's
flow; the route (consecutive walk_to blocks) extracted from a flow; each segment checked on the
walk grid with map_routes' own functions (a warning, never a refusal); and the GPS rejoin. Every
grid and project here is SYNTHETIC (no client data): numpy grids, and the committed sample project
and sheets (town_1 / field_1)."""

from __future__ import annotations

import dataclasses
import json
import random
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
import map_routes as mr  # noqa: E402
import map_zones as mz  # noqa: E402
import path_blocks as pb  # noqa: E402

from poring_flow import editor, ir, pyproject  # noqa: E402
from poring_flow import project as pj  # noqa: E402

SAMPLE = REPO / "services/frontend/src/lib/flow/fixtures/project_sample.json"
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


def walk(m: str, cells: Any, t0: float = 0.0, dt: float = 0.15) -> list[tuple[Any, ...]]:
    return [(t0 + k * dt, m, x, y, True) for k, (x, y) in enumerate(cells)]


def line(a: tuple[int, int], b: tuple[int, int]) -> list[tuple[int, int]]:
    return mr.seg_cells(a, b)


def cells_of(t: pb.Thinned, k: int = 0) -> list[tuple[int, int]]:
    return list(t.runs[k].cells())


def sample() -> pj.Project:
    return pj.from_json(SAMPLE.read_text(encoding="utf-8"))


def zones_of(no_enter: Any = (), no_cross: Any = ()) -> mz.Zones:
    return mz.Zones(map="fix_a", reviewed_by="batt", reviewed="2026-11-22",
                    no_cross=tuple(no_cross), no_enter=tuple(no_enter))  # fmt: skip


# --- thinning (Amendment 1 b, one run per map) ----------------------------------------------------


def test_a_straight_walk_keeps_few_points_and_gives_few_blocks() -> None:
    t = pb.thin(walk("fix_a", line((0, 5), (30, 5))))
    assert cells_of(t) == [(0, 5), (10, 5), (20, 5), (30, 5)]
    assert t.dropped == 0 and len(t.runs) == 1 and t.runs[0].next_map is None
    blocks = pb.run_blocks(t.runs[0])
    assert len(blocks) == 4  # 31 reads -> 4 walk_to blocks
    assert [pb.walk_cell(b) for b in blocks] == [("fix_a", c) for c in cells_of(t)]


def test_a_turn_is_kept_where_it_is() -> None:
    t = pb.thin(walk("fix_a", line((0, 5), (14, 5)) + line((14, 6), (14, 30))))
    assert cells_of(t) == [(0, 5), (10, 5), (14, 5), (14, 15), (14, 25), (14, 30)]


def test_a_turn_back_keeps_its_tip() -> None:
    t = pb.thin(walk("fix_a", line((0, 5), (15, 5)) + line((14, 5), (2, 5))))
    assert cells_of(t) == [(0, 5), (10, 5), (15, 5), (5, 5), (2, 5)]


def test_a_staircase_line_is_not_a_turn() -> None:
    """An 8-direction walk of a 1:2 slope zig-zags cell by cell; over turn_span it is straight."""
    cells = [(i, i // 2) for i in range(0, 41)]
    assert max(pb.turn_angles(cells, 3)) < pb.DEFAULTS.turn_deg
    assert cells_of(pb.thin(walk("fix_a", cells))) == [(0, 0), (10, 5), (20, 10), (30, 15),
                                                        (40, 20)]  # fmt: skip


def test_unconfirmed_reads_are_dropped_and_standing_adds_nothing() -> None:
    reads = walk("fix_a", line((0, 5), (12, 5)))
    reads[3:3] = [(0.40, None, None, None, False), (0.41, "far_map", 900, 900, False)]
    reads += [(9.0 + k, "fix_a", 12, 5, True) for k in range(50)]  # standing at the end
    reads += [(60.0 + k * 0.1, "fix_a", 12 + k % 2, 5, True) for k in range(40)]  # a 1-cell jitter
    t = pb.thin(reads)
    assert t.dropped == 2 and len(t.runs) == 1  # the unconfirmed far_map read is no map change
    assert cells_of(t) == [(0, 5), (10, 5), (13, 5)]  # the jitter's last cell ends the run


def test_the_settings_are_passed_in() -> None:
    reads = walk("fix_a", line((0, 5), (14, 5)) + line((14, 6), (14, 30)))
    s = pb.ThinSettings(every_cells=6, min_step=2, turn_deg=170.0, turn_span=3)
    # (14, 29) is 1 cell from the end, closer than min_step 2: not kept
    assert cells_of(pb.thin(reads, settings=s)) == [(0, 5), (6, 5), (12, 5), (14, 11), (14, 17),
                                                     (14, 23), (14, 30)]  # fmt: skip
    loose = pb.thin(reads, settings=dataclasses.replace(pb.DEFAULTS, every_cells=50))
    assert cells_of(loose) == [(0, 5), (14, 5), (14, 30)]  # the turn alone
    off = dataclasses.replace(pb.DEFAULTS, every_cells=50, turn_deg=180)
    assert cells_of(pb.thin(reads, settings=off)) == [(0, 5), (14, 30)]


@pytest.mark.parametrize(("change", "why"), [
    ({"every_cells": 0}, "every_cells 0"),
    ({"min_step": 1.5}, "min_step 1.5"),
    ({"turn_span": True}, "turn_span True"),
    ({"turn_deg": 0}, "turn_deg 0"),
    ({"turn_deg": 181}, "turn_deg 181"),
    ({"turn_deg": float("nan")}, "turn_deg nan"),
])  # fmt: skip
def test_bad_settings_are_refused(change: dict[str, Any], why: str) -> None:
    s = dataclasses.replace(pb.DEFAULTS, **change)
    assert why in str(pb.settings_problem(s))
    with pytest.raises(pb.PathError, match="settings: "):
        pb.thin(walk("fix_a", [(1, 1)]), settings=s)
    assert pb.settings_problem(pb.DEFAULTS) is None


def test_the_minimum_step_holds_except_at_a_mark() -> None:
    reads = walk("fix_a", line((0, 5), (11, 5)) + line((11, 6), (11, 20)))
    turn_only = dataclasses.replace(pb.DEFAULTS, every_cells=50)
    assert cells_of(pb.thin(reads, settings=turn_only)) == [(0, 5), (11, 5), (11, 20)]
    t = pb.thin(reads)  # the corner is 1 cell from the kept (10, 5): closer than 3
    assert cells_of(t) == [(0, 5), (10, 5), (11, 15), (11, 20)]
    marked = pb.thin(reads, marks=[reads[11][0] + 0.01])  # read 11 = (11, 5), the corner
    # the mark is kept; the distance point (10, 5) 1 cell before it is not (the next protected)
    assert cells_of(marked) == [(0, 5), (11, 5), (11, 15), (11, 20)]
    assert [p.mark for p in marked.runs[0].points] == [False, True, False, False]
    near = pb.thin(reads, marks=[reads[9][0], reads[11][0]])  # (9, 5) and (11, 5): marks
    assert cells_of(near) == [(0, 5), (9, 5), (11, 5), (11, 15), (11, 20)]  # 2 apart: both kept


def test_a_mark_takes_the_read_nearest_in_time() -> None:
    reads = walk("fix_a", line((0, 5), (20, 5)), dt=1.0)
    for m, cell in ((4.4, (4, 5)), (4.5, (4, 5)), (4.6, (5, 5)), (-3.0, (0, 5)), (99.0, (20, 5))):
        marks = [p.cell for p in pb.thin(reads, marks=[m]).runs[0].points if p.mark]
        assert marks == [cell], (m, marks)
    with pytest.raises(pb.PathError, match="mark 0"):
        pb.thin(reads, marks=[float("inf")])


def test_a_mark_back_on_a_kept_cell_merges_into_it() -> None:
    reads = walk("fix_a", [(5, 5), (6, 5), (5, 5)])
    assert pb.thin(reads, marks=[reads[2][0]]).runs[0].points == (pb.Point(5, 5, True),)


def test_a_map_change_splits_the_recording_by_map() -> None:
    a = walk("fix_a", line((5, 5), (25, 5)))
    b = walk("fix_b", line((30, 30), (30, 10)), t0=10.0)
    c = walk("fix_a", line((3, 3), (8, 3)), t0=20.0)
    t = pb.thin(a + b + c, marks=[b[0][0]])
    assert [(r.map, r.next_map) for r in t.runs] == [("fix_a", "fix_b"), ("fix_b", "fix_a"),
                                                     ("fix_a", None)]  # fmt: skip
    assert cells_of(t, 0) == [(5, 5), (15, 5), (25, 5)]  # ends where she left fix_a
    assert cells_of(t, 1) == [(30, 30), (30, 20), (30, 10)]
    assert cells_of(t, 2) == [(3, 3), (8, 3)]  # a second stay on fix_a: a run of its own
    assert [p.mark for p in t.runs[1].points] == [True, False, False]  # the mark's own map
    blocks = [pb.run_blocks(r) for r in t.runs]
    assert {pb.walk_cell(b)[0] for b in blocks[1]} == {"fix_b"}  # type: ignore[index]
    assert {pb.walk_cell(b)[0] for b in blocks[0] + blocks[2]} == {"fix_a"}  # type: ignore[index]
    # Amendment 7: a run that ended in a map change leaves out the cell read just before it (the
    # warp, often); the map's own take_exit crosses. The last stay keeps its end.
    assert [pb.walk_cell(b)[1] for b in blocks[0]] == [(5, 5), (15, 5)]
    assert [pb.walk_cell(b)[1] for b in blocks[1]] == [(30, 30), (30, 20)]
    assert [pb.walk_cell(b)[1] for b in blocks[2]] == [(3, 3), (8, 3)]
    kept = pb.run_blocks(t.runs[0], keep_exit_cell=True)
    assert [pb.walk_cell(b)[1] for b in kept] == [(5, 5), (15, 5), (25, 5)]


def test_a_one_point_stay_before_a_map_change_gives_no_block() -> None:
    a = walk("fix_a", [(5, 5)])
    b = walk("fix_b", [(30, 30), (31, 30)], t0=10.0)
    t = pb.thin(a + b)
    assert cells_of(t, 0) == [(5, 5)] and pb.run_blocks(t.runs[0]) == ()


def test_a_map_change_is_kept_even_one_cell_from_the_last_point() -> None:
    a = walk("fix_a", line((5, 5), (16, 5)))  # (15, 5) kept by distance, (16, 5) ends the run
    b = walk("fix_b", [(30, 30), (31, 30)], t0=10.0)
    t = pb.thin(a + b)
    assert cells_of(t, 0) == [(5, 5), (16, 5)]  # (15, 5) is 1 cell from the run's end: not kept
    assert cells_of(t, 1) == [(30, 30), (31, 30)]  # the ends of a run: closer than min_step


@pytest.mark.parametrize(("reads", "why"), [
    ([], "no confirmed read"),
    ([(0.0, "fix_a", 1, 1, False)], "no confirmed read"),
    ([(0.0, "fix_a", 1, 1)], "read 0 is not (t, map, x, y, confirmed)"),
    (["abcde"], "read 0 is not"),
    ([(0.0, "fix_a", 1, 1, 1)], "confirmed is not true or false"),
    ([(float("nan"), "fix_a", 1, 1, True)], "not a finite number"),
    ([(0.0, None, 1, 1, True)], "map None"),
    ([(0.0, "../etc", 1, 1, True)], "is not a map name"),
    ([(0.0, "fix_a", -1, 1, True)], "outside 0 .. 2047"),
    ([(0.0, "fix_a", 1.0, 1, True)], "two whole numbers"),
    ([(1.0, "fix_a", 1, 1, True), (0.5, "fix_a", 2, 1, True)], "not in time order"),
])  # fmt: skip
def test_bad_reads_are_refused(reads: Any, why: str) -> None:
    with pytest.raises(pb.PathError) as exc:
        pb.thin(reads)
    assert why in str(exc.value), str(exc.value)


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
    s = pb.ThinSettings(every_cells=8, min_step=3, turn_deg=50.0, turn_span=3)
    kept = pb.thin_track(track, marked, s)
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
    t = pb.thin(reads, marks=[reads[run_read[m]][0] for m in marked], settings=s)
    assert t.runs[0].cells() == tuple(track[i] for i in idx)
    assert [p.mark for p in t.runs[0].points] == [m for _, m in kept]


def test_thin_track_refuses_a_track_with_repeats() -> None:
    with pytest.raises(pb.PathError, match="repeats"):
        pb.thin_track([(1, 1), (1, 1)], ())
    with pytest.raises(pb.PathError, match="outside the track"):
        pb.thin_track([(1, 1), (2, 1)], [5])
    assert pb.thin_track([(1, 1)], [0]) == [(0, True)]


# --- the blocks: walk_to in the IR's own shape ----------------------------------------------------


def test_a_generated_block_is_the_studios_own_walk_to() -> None:
    """The sample project's hand-made walk_to (town_1 97, 71) and the generated one are the same
    IR statement, field for field (concept, default timeout, on_fail, no note)."""
    town = sample().node("town")
    assert town is not None
    made = next(s for s in town.main if pb.walk_cell(s) is not None)
    assert pb.walk_block("town_1", (97, 71)) == made
    assert made.model_dump(mode="json") == {
        "kind": "action", "block": "walk_to", "concept": "nav.walk_to",
        "params": {"cell": {"kind": "lit", "value": {"kind": "cell", "map": "town_1", "x": 97,
                                                     "y": 71}}},
        "timeout_s": 120.0, "on_fail": "stop", "outcome_to": None, "note": None}  # fmt: skip


def test_the_generated_blocks_validate_in_the_ir() -> None:
    blocks = pb.walk_blocks("fix_a", [pb.Point(5, 5), pb.Point(15, 5, True), (15, 15)])
    for b in blocks:
        again = ir.ActionStmt.model_validate_json(b.model_dump_json())
        assert again == b and again.block == "walk_to" and again.concept == "nav.walk_to"
    assert [b.note for b in blocks] == [None, pb.MARK_NOTE, None]  # a mark becomes a note
    thai = "ไปหาคาฟร่า"  # a note is a person's text in any script: stored as data
    assert pb.walk_blocks("fix_a", [pb.Point(1, 2, True)], mark_note=thai)[0].note == thai


@pytest.mark.parametrize(("call", "why"), [
    (lambda: pb.walk_block("../x", (1, 1)), "params.cell"),
    (lambda: pb.walk_block("fix_a", (1, 1), note="x" * 201), "note"),
    (lambda: pb.walk_block("fix_a", (2048, 1)), "outside 0 .. 2047"),
    (lambda: pb.walk_block("fix_a", (1,)), "is not (x, y)"),
    (lambda: pb.walk_blocks("fix_a", []), "no point"),
    (lambda: pb.walk_blocks("fix_a", [(1, True)]), "point 0 is not a cell"),
])  # fmt: skip
def test_a_block_the_ir_refuses_is_refused(call: Any, why: str) -> None:
    with pytest.raises(pb.PathError) as exc:
        call()
    assert why in str(exc.value), str(exc.value)


# --- the route in a flow --------------------------------------------------------------------------


def stmts(*items: Any) -> list[Any]:
    out = []
    for it in items:
        if isinstance(it, tuple) and len(it) == 3:
            out.append(pb.walk_block(it[0], it[1:]))
        else:
            out.append(it)
    return out


def test_the_route_stops_at_a_block_that_is_not_a_walk_to() -> None:
    talk = ir.ActionStmt.model_validate({"kind": "action", "block": "talk_npc",
                                         "concept": "npc.talk", "timeout_s": 60,
                                         "params": {"npc": {"kind": "lit", "value": {
                                             "kind": "npc", "key": "n_kafra"}}}})  # fmt: skip
    by_var = ir.ActionStmt.model_validate({
        "kind": "action", "block": "walk_to", "concept": "nav.walk_to", "timeout_s": 120,
        "params": {"cell": {"kind": "var", "name": "HOME"}}})  # fmt: skip
    nested = ir.If.model_validate({"kind": "if", "cond": {"kind": "lit", "value": True},
                                   "then": [pb.walk_block("m", (9, 9)).model_dump()]})  # fmt: skip
    body = stmts(("m", 1, 1), ("m", 2, 5), talk, ("m", 3, 3), ("m", 4, 4), ("m", 5, 5), by_var,
                 ("m", 6, 6), ("o", 7, 7), ("o", 8, 8), nested, ("m", 9, 1))  # fmt: skip
    routes = pb.routes_in(body)
    assert [(r.start, r.stop, r.map, r.cells) for r in routes] == [
        (0, 2, "m", ((1, 1), (2, 5))),
        (3, 6, "m", ((3, 3), (4, 4), (5, 5))),
        (7, 8, "m", ((6, 6),)),  # a walk_to on another map ends it
        (8, 10, "o", ((7, 7), (8, 8))),
        (11, 12, "m", ((9, 1),)),  # an if's branch is a list of its own
    ]  # fmt: skip
    only_m = pb.routes_in(body, map_id="m")
    assert [(r.start, r.stop) for r in only_m] == [(0, 2), (3, 6), (7, 8), (11, 12)]
    assert pb.route_at(body, 4) == routes[1] and pb.route_at(body, 2) is None
    assert pb.route_at(body, 6) is None and pb.route_at(body, 9, map_id="m") is None
    assert pb.routes_in(nested.then) == (pb.Route(0, "m", ((9, 9),)),)
    assert pb.routes_in([]) == ()


# --- the proposal: insert into a map node's flow (nothing changes without a click) ----------------


def test_insertion_returns_a_new_project_and_leaves_the_input_unchanged() -> None:
    p = sample()
    before = pj.canonical_json(p)
    old_main = p.node("town").main  # type: ignore[union-attr]
    blocks = pb.walk_blocks("town_1", [(55, 45), (55, 60), pb.Point(85, 60, True)])
    prop = pb.propose(p, "town", 1, blocks)
    assert pj.canonical_json(p) == before and prop.base is p  # the input is untouched
    new_main = prop.project.node("town").main  # type: ignore[union-attr]
    assert new_main == [old_main[0], *blocks, *old_main[1:]]
    for n in p.nodes:  # every other node is the same
        if n.id != "town":
            assert prop.project.node(n.id) == n
    # the inserted blocks join the hand-made walk_to after them: ONE route of four points
    assert prop.route == pb.Route(1, "town_1", ((55, 45), (55, 60), (85, 60), (97, 71)))
    assert pb.apply(prop, p) is prop.project  # the click
    # the Python view prints and reads them back as the studio's own blocks
    files = pyproject.print_files(prop.project)
    town = next(f.text for f in files if f.path == "town/main.py")
    assert '    walk_to(cell("town_1", 55, 60))\n' in town
    assert '    walk_to(cell("town_1", 85, 60), note="mark")\n' in town
    back = pyproject.parse_files({f.path: f.text for f in files})
    assert pj.canonical_json(back) == pj.canonical_json(prop.project)


def test_the_inserted_blocks_add_no_lint_finding() -> None:
    """The project's own lint, with the synthetic sample sheets: the new blocks on open cells of
    town_1 add no finding (the sample's own save-point warning stays as it was)."""
    p, world = sample(), editor.sample_world()
    prop = pb.propose(p, "town", 1, pb.walk_blocks("town_1", [(55, 45), (55, 60), (85, 60)]))
    found = {(f.rule, f.severity, f.text) for f in pj.project_lint(p, world=world)[1]}
    assert {(f.rule, f.severity, f.text) for f in pj.project_lint(prop.project, world=world)[1]
            } == found  # fmt: skip


def test_insertion_at_the_ends_and_the_route_it_makes() -> None:
    p = sample()
    two = pb.walk_blocks("town_1", [(40, 40), (50, 50)])
    first = pb.propose(p, "town", 0, two)
    assert first.route == pb.Route(0, "town_1", ((40, 40), (50, 50)))  # set_save_point ends it
    n = len(p.node("town").main)  # type: ignore[union-attr]
    last = pb.propose(p, "town", n, two)
    assert last.project.node("town").main[-2:] == list(two)  # type: ignore[union-attr]
    stop = ir.Stop(reason="done")
    assert pb.propose(p, "town", 0, [stop]).route is None  # any IR statement may be inserted


@pytest.mark.parametrize(("node", "at", "blocks", "why"), [
    ("nowhere", 0, "town_1", "'nowhere' is no node"),
    ("login", 0, "town_1", "'login' is the login node"),
    ("global", 0, "town_1", "'global' is the global node"),
    ("town", -1, "town_1", "position -1 is outside town's main (0 .. 3)"),
    ("town", 4, "town_1", "position 4 is outside"),
    ("town", True, "town_1", "position True is outside"),
    ("town", 0, None, "no block to insert"),
    ("town", 0, "field_1", "block 0: walk_to [5, 5] is on field_1; town is on town_1"),
    ("town", 0, "bad", "block 0 is not a statement of the flow IR"),
])  # fmt: skip
def test_a_proposal_that_cannot_be_made_is_refused(node: str, at: Any, blocks: Any,
                                                   why: str) -> None:  # fmt: skip
    if blocks is None:
        bl: Any = []
    elif blocks == "bad":
        bl = [{"kind": "stop", "reason": "x"}]  # JSON, not an IR statement
    else:
        bl = pb.walk_blocks(blocks, [(5, 5)])
    with pytest.raises(pb.PathError) as exc:
        pb.propose(sample(), node, at, bl)
    assert why in str(exc.value), str(exc.value)


def test_a_proposal_applies_only_to_the_project_it_was_made_from() -> None:
    p = sample()
    prop = pb.propose(p, "town", 1, pb.walk_blocks("town_1", [(55, 45)]))
    assert pb.apply(prop, pj.from_json(pj.to_json(p))) is prop.project  # an equal copy: fine
    moved = pb.propose(p, "town", 0, pb.walk_blocks("town_1", [(40, 40)])).project
    with pytest.raises(pb.PathError, match="the project changed"):
        pb.apply(prop, moved)


def test_the_project_loader_still_decides() -> None:
    """The new project goes through the project model's own loader: a shape it refuses (a
    `return` in a main) comes back as its ProjectError, naming the node, the tab and the site."""
    with pytest.raises(pj.ProjectError) as exc:
        pb.propose(sample(), "town", 1, [ir.Return()])
    assert exc.value.messages == ["town/main/main.1: return belongs inside a function (a def), "
                                  "not in main"]  # fmt: skip


# --- the walk check (map_routes' own functions; a warning, never a refusal) -----------------------


def test_a_good_route_checks_with_each_segments_length() -> None:
    rep = pb.check_route([(5, 5), (15, 5), (15, 15), (16, 16)], fix_grid())
    assert rep.ok and rep.warnings == ()
    assert [(s.i, s.status, s.steps, s.cost) for s in rep.segments] == [
        (0, "ok", 10, 10.0), (1, "ok", 10, 10.0), (2, "ok", 1, 1.4)]  # fmt: skip
    assert [p.status for p in rep.points] == ["ok"] * 4
    doc = rep.doc()
    assert doc["ok"] and doc["segments"][2] == {"from": 2, "to": 3, "a": [15, 15], "b": [16, 16],
                                                "status": "ok", "why": None, "steps": 1,
                                                "cost": 1.4}  # fmt: skip
    assert json.loads(json.dumps(doc)) == doc


def test_a_blocked_grid_breaks_a_segment_with_its_reason() -> None:
    rep = pb.check_route([(10, 10), (34, 5), (20, 15), (25, 25)], fix_grid())
    assert not rep.ok
    assert [s.status for s in rep.segments] == ["broken", "broken", "broken"]
    assert [p.status for p in rep.points] == ["ok", "ok", "closed", "ok"]
    assert rep.segments[0].why == pb.NOT_CONNECTED  # into the sealed room
    assert rep.segments[1].why == rep.segments[2].why == "point 2 [20, 15]: not walkable"
    assert rep.warnings[0] == "point 2 [20, 15]: not walkable"
    assert rep.warnings[1].startswith("segment 0 -> 1 ([10, 10] -> [34, 5]): not connected")
    around = pb.check_route([(10, 10), (30, 20)], fix_grid()).segments[0]
    assert around.status == "ok" and around.steps is not None and around.steps > 20  # round the end


def test_a_no_enter_zone_is_respected() -> None:
    box = ((4, 20), (9, 20), (9, 25), (4, 25))
    zones = zones_of(no_enter=[mz.NoEnter("ne0", "n", box)])
    inside = pb.check_route([(2, 22), (6, 22)], fix_grid(), zones)
    assert inside.points[1].why == "inside no-enter area 'ne0'"
    assert inside.segments[0].status == "broken"
    # the band y 20..25 west of the wall closed but for the box (x 4..9): the only way north
    g = fix_grid()
    g[20:26, 2:4] = False
    g[20:26, 10:20] = False
    across = pb.check_route([(5, 15), (5, 30)], g)
    assert across.ok  # without the zone: straight through
    blocked = pb.check_route([(5, 15), (5, 30)], g, zones)  # the zone shuts the south-west off
    assert blocked.segments[0].status == "broken"
    assert blocked.segments[0].why == "point 0 [5, 15]: sealed off by the zones"


def test_a_warp_cell_is_not_cut_but_a_zone_on_it_is_respected() -> None:
    """Batt (Amendment 5 answer 1): no warp cell is cut from the grid -- the user's line is
    followed; a no-enter zone keeps her off a warp. A one-cell doorway that is a warp stays open
    unless a zone closes it."""
    g = fix_grid()
    g[31:38, 20] = False
    g[33, 20] = True  # the only way through the wall: say it is a warp cell
    assert pb.check_route([(10, 33), (30, 33)], g).ok
    door = zones_of(no_enter=[mz.NoEnter("warp", "n", ((19, 32), (21, 32), (21, 34), (19, 34)))])
    rep = pb.check_route([(10, 33), (30, 33)], g, door)
    assert rep.segments[0].status == "broken"


def test_the_check_is_map_routes_own() -> None:
    """Parity: the same points as a map_routes PATH route give the same steps, costs and number of
    problems through map_routes.prove (zones too)."""
    box = ((4, 20), (9, 20), (9, 25), (4, 25))
    zones = zones_of(no_enter=[mz.NoEnter("ne0", "n", box)])
    cells = [(5, 5), (15, 5), (15, 15), (6, 22), (25, 33), (34, 5), (12, 30)]
    for z in (None, zones):
        ours = pb.check_route(cells, fix_grid(), z)
        theirs = mr.prove(mr.Routes(map="fix_a", reviewed_by="batt", reviewed="2026-11-22",
                                    source="synthetic",
                                    routes=(mr.Route("r", "path", "n", tuple(cells)),)),
                          fix_grid(), z)  # fmt: skip
        legs = theirs["routes"][0]["legs"]
        assert [(s.steps, s.cost) for s in ours.segments] == [(s["steps"], s["cost"])
                                                             for s in legs]  # fmt: skip
        closed = sum(p.status != "ok" for p in ours.points)
        broken = sum(s.status != "ok" for s in ours.segments)
        assert closed + broken == len(theirs["problems"]) > 0


def test_a_zone_sealed_point_is_closed_as_map_routes_says() -> None:
    zones = zones_of(no_cross=[mz.NoCross("nc0", "n", ((20, 30), (20, 38)))])
    rep = pb.check_route([(10, 10), (25, 10)], fix_grid(), zones)  # the line shuts the wall's gap
    assert [p.status for p in rep.points] == ["ok", "closed"]
    assert rep.points[1].why == "sealed off by the zones"  # the smaller (east) piece
    assert rep.segments[0].status == "broken"
    assert pb.check_route([(10, 10), (25, 10)], fix_grid()).ok  # without the zones: connected


def test_no_grid_is_unproven_and_an_off_map_point_is_closed() -> None:
    rep = pb.check_route([(5, 5), (6, 6)], None)
    assert [p.status for p in rep.points] == ["unproven", "unproven"]
    assert [(s.status, s.why) for s in rep.segments] == [("unproven", pb.NO_GRID)]
    assert not rep.ok and len(rep.warnings) == 3
    off = pb.check_route([(5, 5), (45, 5)], fix_grid())
    assert off.points[1].why == "off the map (40 x 40 cells)"
    assert off.segments[0].status == "broken"
    one = pb.check_route([(20, 20)], fix_grid())
    assert one.segments == () and one.points[0].status == "closed"
    with pytest.raises(pb.PathError, match="at least one point"):
        pb.check_route([], fix_grid())


def test_the_check_agrees_with_the_studios_route_lint_on_the_sample_sheet() -> None:
    """On the synthetic town_1 sheet, a segment the check breaks is a leg the project lint's
    `routes` rule calls unreachable (the same blocks inserted), and only those."""
    world = editor.sample_world()
    rows = world.sheet("town_1").walk.rows  # type: ignore[union-attr]
    grid = np.array([[ch == "." for ch in r] for r in rows])  # rows[y][x], as map_routes' [y, x]
    cells = [(55, 45), (55, 60), (70, 45), (85, 60), (85, 30)]  # (70, 45) is inside the block
    rep = pb.check_route(cells, grid)
    assert [s.status for s in rep.segments] == ["ok", "broken", "broken", "ok"]
    prop = pb.propose(sample(), "town", 1, pb.walk_blocks("town_1", cells))
    unreachable = {f.where.site for f in pj.project_lint(prop.project, world=world)[1]
                   if f.rule == "routes"}  # fmt: skip
    # segment i ends at route point i + 1 = main statement 1 + i + 1 (the route starts at 1)
    assert unreachable == {f"main.{2 + s.i}" for s in rep.segments if s.status == "broken"}


# --- the GPS rejoin -------------------------------------------------------------------------------


L_ROUTE = [(0, 10), (20, 10), (20, 30), (40, 30)]


def test_knocked_sideways_mid_segment_rejoins_on_it_ahead_never_behind() -> None:
    for x in range(1, 17):  # nearer to (20, 10) the vertical segment may be as near (below)
        for dy in (1, 2, 3, -2):
            r = pb.rejoin(L_ROUTE, (x, 10 + dy), last=0)
            assert r == pb.Rejoin((x, 10), 1, abs(dy), False), (x, dy, r)  # the foot, then on
    behind = pb.rejoin(L_ROUTE, (0, 13), last=0)  # beside the passed point 0
    assert behind == pb.Rejoin((1, 10), 1, 3, False)  # ahead of it, never on or behind it


def test_knocked_back_behind_the_last_point_still_goes_ahead() -> None:
    r = pb.rejoin(L_ROUTE, (5, 10), last=1)  # she passed (20, 10), then was pushed back west
    assert r == pb.Rejoin((20, 11), 2, 15, False)  # never back to (20, 10) or before it
    assert pb.rejoin(L_ROUTE, (0, 10), last=1) == pb.Rejoin((20, 11), 2, 20, False)


def test_past_the_last_point_is_done() -> None:
    assert pb.rejoin(L_ROUTE, (5, 5), last=3) == pb.Rejoin((40, 30), None, 35, True)
    assert pb.rejoin(L_ROUTE, (39, 31), last=2) == pb.Rejoin((40, 30), None, 1, True)  # within tol
    far = pb.rejoin(L_ROUTE, (45, 30), last=2)
    assert far == pb.Rejoin((40, 30), None, 5, False)  # walk to the last point first
    assert pb.rejoin(L_ROUTE, (45, 30), last=2, tol=5).done
    loop = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 1)]  # ends 1 cell from where it starts
    assert pb.rejoin(loop, (0, 0), last=0) == pb.Rejoin((1, 0), 1, 1, False)  # not done


def test_far_away_rejoins_the_nearest_segment_ahead() -> None:
    assert pb.rejoin(L_ROUTE, (35, 22), last=0) == pb.Rejoin((35, 30), 3, 8, False)  # the last
    assert pb.rejoin(L_ROUTE, (30, 15), last=0) == pb.Rejoin((20, 15), 2, 10, False)  # vertical
    assert pb.rejoin(L_ROUTE, (35, 5), last=0) == pb.Rejoin((20, 10), 2, 15, False)  # the corner
    assert pb.rejoin(L_ROUTE, (30, 15), last=2) == pb.Rejoin((30, 30), 3, 15, False)  # passed


def test_near_a_corner_the_next_segment_may_be_nearer() -> None:
    assert pb.rejoin(L_ROUTE, (22, 12), last=0) == pb.Rejoin((20, 12), 2, 2, False)
    assert pb.rejoin(L_ROUTE, (18, 13), last=0) == pb.Rejoin((20, 13), 2, 2, False)


def test_equally_near_cells_take_the_first_stretch_at_its_far_end() -> None:
    there_and_back = [(0, 0), (10, 0), (20, 0), (10, 0), (0, 0)]
    for x in range(1, 20):  # the way back passes the same cells: never skip to it
        r = pb.rejoin(there_and_back, (x, 1), last=0)
        assert r.cell == (x, 0) and r.next == (1 if x < 10 else 2), (x, r)
    tip = pb.rejoin(there_and_back, (20, 2), last=1)
    assert tip == pb.Rejoin((20, 0), 3, 2, False)  # the tip itself, then the way back
    diag = [(0, 0), (4, 4)]  # from (3, 0): (1, 1) and (2, 2) are equally near (squared 5)
    assert pb.rejoin(diag, (3, 0)) == pb.Rejoin((2, 2), 1, 2, False)  # the stretch's far end


def test_a_rejoin_on_a_point_continues_with_the_next_one() -> None:
    assert pb.rejoin(L_ROUTE, (20, 10), last=0) == pb.Rejoin((20, 10), 2, 0, False)
    assert pb.rejoin(L_ROUTE, (20, 30)) == pb.Rejoin((20, 30), 3, 0, False)
    start = pb.rejoin(L_ROUTE, (0, 10))  # none passed yet: the first point is on the line
    assert start == pb.Rejoin((0, 10), 1, 0, False)
    assert pb.rejoin(L_ROUTE, (0, 9)) == pb.Rejoin((0, 10), 1, 1, False)
    dup = [(0, 0), (5, 0), (5, 0), (9, 0)]  # a repeated point is reached with the first
    assert pb.rejoin(dup, (5, 1), last=0) == pb.Rejoin((5, 0), 3, 1, False)
    assert pb.rejoin(dup, (5, 0), last=1) == pb.Rejoin((6, 0), 3, 1, False)
    assert pb.rejoin([(3, 3)], (4, 4)) == pb.Rejoin((3, 3), None, 1, True)
    assert pb.rejoin([(3, 3)], (9, 9)) == pb.Rejoin((3, 3), None, 6, False)


def test_the_rejoin_runs_on_a_flows_route() -> None:
    """The route of a map node's flow and its rejoin: route point i is main statement start + i."""
    prop = pb.propose(sample(), "town", 1, pb.walk_blocks("town_1", [(55, 45), (55, 60),
                                                                      (85, 60)]))  # fmt: skip
    route = prop.route
    assert route is not None and route.start == 1
    r = pb.rejoin(route.cells, (70, 63), last=1)  # knocked off the (55, 60) -> (85, 60) segment
    assert r == pb.Rejoin((70, 60), 2, 3, False)
    main = prop.project.node("town").main  # type: ignore[union-attr]
    assert pb.walk_cell(main[route.start + r.next]) == ("town_1", (85, 60))  # the walk_to to run


@pytest.mark.parametrize(("args", "why"), [
    (([], (1, 1)), "at least one point"),
    ((L_ROUTE, (1,)), "her cell is not (x, y)"),
    ((L_ROUTE, (1, 1), 4), "last 4 is not a point"),
    ((L_ROUTE, (1, 1), -1), "last -1"),
    ((L_ROUTE, (1, 1), True), "last True"),
    ((L_ROUTE, (1, 1), 0, -1), "tol -1"),
    (([(1, 1), (1, -2)], (1, 1)), "point 1 [1, -2] is outside"),
])  # fmt: skip
def test_a_bad_rejoin_question_is_refused(args: Any, why: str) -> None:
    with pytest.raises(pb.PathError) as exc:
        pb.rejoin(*args)
    assert why in str(exc.value), str(exc.value)
