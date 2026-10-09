"""ONE PLANNER, cross-checked (Batt 2026-10-09, ADR-0020 contradictions #18; open question 15).

The flow linter must route the way the executor walks: "two planners that can disagree let a flow
lint clean and fail live". Until the linter routes with the executor's planner itself (the swap
waits: ADR-0020 section 5 and open question 15 say why), this test holds the two together:

- MW1's linter planner: `poring_flow.sheet.Walk.route`, its own A* on a map sheet's walk grid;
- the executor's planner: `poring_dataset.walk.walk_path`, the client's own path rules (8-way, a
  straight step 10, a diagonal 14, no corner cutting), which the walk rules plan with.

For sampled pairs of walkable cells on every sheet map, the two must agree on:
- REACHABILITY (both find a path, or neither does), with the executor's planner unbounded;
- the path COST, exactly (both are shortest paths under one cost model);
- the number of STEPS within 2 (two equally cheap paths can trade 7 straight steps for 5 diagonal
  ones), and each path must be a legal walk under the client's rules.
The executor plans ONE walk of at most PLAN_MAX = 48 steps (scripts/walk5.py) and MW1's linter has
no such limit: that difference is recorded (the legs it would refuse), not hidden.

The committed maps are synthetic (the MW2 sample's sheets, seeded random mazes). The lab's real
maps are LOCAL (client data, never committed): set PORING_FLOW_CROSSCHECK_GAT to a GAT directory
(e.g. data/gat, made by scripts/flows_gat.py) to run the same check on them, plus a check that the
linter's GAT reader (poring_flow.kbsheet.read_gat) and the executor's (poring_dataset.gat) see the
same walkable cells.
"""

from __future__ import annotations

import json
import os
import random
from collections.abc import Callable
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import pytest

from poring_dataset import gat as dgat
from poring_dataset.walk import DIAGONAL, STRAIGHT, walk_path
from poring_flow.kbsheet import read_gat
from poring_flow.sheet import MapSheet, Walk

Cell = tuple[int, int]
PLAN_MAX = 48  # scripts/walk5.py: the executor's one-plan step limit (it then splits into clicks)
STEP_TOLERANCE = 2


class SheetGrid:
    """`poring_dataset.walk.Grid` over a map sheet's walk grid (the very cells the linter reads)."""

    def __init__(self, walk: Walk) -> None:
        self.walk = walk
        self.xs, self.ys = walk.width, walk.height

    def nopass(self, x: int, y: int) -> bool:
        return not self.walk.walkable((x, y))


def cost(path: list[Cell]) -> int:
    return sum(
        DIAGONAL if a[0] != b[0] and a[1] != b[1] else STRAIGHT
        for a, b in zip(path, path[1:], strict=False)
    )


def legal(walk: Walk, path: list[Cell]) -> bool:
    """Every cell walkable; every step one of the 8 neighbours; no corner cutting."""
    for a, b in zip(path, path[1:], strict=False):
        dx, dy = b[0] - a[0], b[1] - a[1]
        if max(abs(dx), abs(dy)) != 1 or not walk.walkable(b):
            return False
        if (
            dx
            and dy
            and not (walk.walkable((a[0] + dx, a[1])) and walk.walkable((a[0], a[1] + dy)))
        ):
            return False
    return all(walk.walkable(c) for c in path)


@dataclass
class Tally:
    pairs: int = 0
    reachable: int = 0
    unreachable: int = 0
    # legs whose cheapest walk is longer than the executor's ONE plan (PLAN_MAX steps): the plan
    # then refuses the leg, or takes a DEARER walk of at most PLAN_MAX steps than the linter's
    longer_than_plan: int = 0
    plan_refuses: int = 0
    plan_dearer: int = 0
    step_diffs: int = 0  # equally cheap paths with another step count (within the tolerance)
    disagreements: list[str] | None = None

    def __post_init__(self) -> None:
        self.disagreements = []


Planner = Callable[..., "list[Cell] | None"]


def cross_check(walk: Walk, pairs: list[tuple[Cell, Cell]], planner: Planner = walk_path) -> Tally:
    t = Tally()
    grid = SheetGrid(walk)
    unbounded = walk.width * walk.height
    assert t.disagreements is not None
    for a, b in pairs:
        t.pairs += 1
        mine = walk.route(a, b)  # MW1: both ends included, or None
        tail = planner(grid, a[0], a[1], b[0], b[1], max_len=unbounded)
        theirs = None if tail is None else [a, *tail]
        if (mine is None) != (theirs is None):
            lin = "no path" if mine is None else "a path"
            exe = "no path" if theirs is None else "a path"
            t.disagreements.append(f"{a}->{b}: linter {lin}, executor {exe}")
            continue
        if mine is None or theirs is None:
            t.unreachable += 1
            continue
        t.reachable += 1
        if not (legal(walk, mine) and legal(walk, theirs)):
            t.disagreements.append(f"{a}->{b}: an illegal walk")
        if cost(mine) != cost(theirs):
            t.disagreements.append(f"{a}->{b}: cost {cost(mine)} vs {cost(theirs)}")
        diff = abs(len(mine) - len(theirs))
        if diff > STEP_TOLERANCE:
            t.disagreements.append(f"{a}->{b}: {len(mine) - 1} vs {len(theirs) - 1} steps")
        t.step_diffs += diff > 0
        if len(mine) - 1 > PLAN_MAX:
            t.longer_than_plan += 1
            plan = planner(grid, a[0], a[1], b[0], b[1], max_len=PLAN_MAX)
            if plan is None:
                t.plan_refuses += 1
            else:
                assert cost([a, *plan]) > cost(mine) and len(plan) <= PLAN_MAX
                t.plan_dearer += 1
    return t


def sample_pairs(
    walk: Walk, n: int, seed: int, reach: int | None = None
) -> list[tuple[Cell, Cell]]:
    rng = random.Random(seed)
    cells = [(x, y) for y in range(walk.height) for x in range(walk.width) if walk.walkable((x, y))]
    out = []
    while len(out) < n and cells:
        a = rng.choice(cells)
        if reach is None:
            b = rng.choice(cells)
        else:  # a leg of a flow: a target within `reach` cells
            near = (a[0] + rng.randint(-reach, reach), a[1] + rng.randint(-reach, reach))
            if not walk.walkable(near):
                continue
            b = near
        out.append((a, b))
    return out


def maze(w: int, h: int, seed: int, walls: float) -> Walk:
    rng = random.Random(seed)
    rows = ["".join("#" if rng.random() < walls else "." for _ in range(w)) for _ in range(h)]
    return Walk(width=w, height=h, rows=rows)


def sample_sheets() -> dict[str, Walk]:
    root = resources.files("poring_flow") / "examples" / "sheets" / "sample"
    out = {}
    for name in ("town_1", "field_1"):
        sheet = MapSheet.model_validate(json.loads((root / f"{name}.json").read_text()))
        assert sheet.walk is not None
        out[name] = sheet.walk
    return out


# --- the committed, synthetic maps --------------------------------------------------------------
@pytest.mark.parametrize("name", ["town_1", "field_1"])
def test_the_planners_agree_on_the_sample_sheets(name: str) -> None:
    walk = sample_sheets()[name]
    t = cross_check(walk, sample_pairs(walk, 150, seed=18))
    assert t.disagreements == [] and t.reachable >= 100


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_the_planners_agree_on_random_mazes(seed: int) -> None:
    """Dense walls: many detours, corners and cut-off pockets (unreachable pairs)."""
    walk = maze(48, 40, seed, walls=0.3)
    t = cross_check(walk, sample_pairs(walk, 120, seed=seed))
    assert t.disagreements == []
    assert t.reachable >= 30 and t.unreachable >= 1  # both cases are exercised


def test_long_legs_are_the_known_difference() -> None:
    """The linter routes a leg of any length; the executor plans one walk of at most 48 steps, so
    a longer leg is refused by one plan (it needs waypoints) -- or, when a walk of at most 48 steps
    exists, the plan takes that DEARER walk instead of the linter's cheapest one."""
    walk = maze(120, 20, 7, walls=0.0)
    t = cross_check(walk, [((0, 0), (100, 10)), ((0, 0), (40, 5))])
    assert t.disagreements == [] and (t.longer_than_plan, t.plan_refuses) == (1, 1)
    # found by the random mazes: the cheapest walk takes more than 48 steps, and one plan of at
    # most 48 steps exists, dearer -- the executor would walk ANOTHER route than the linter checked
    dear = cross_check(maze(48, 40, 4, walls=0.3), [((1, 22), (46, 16))])
    assert dear.disagreements == []
    assert (dear.longer_than_plan, dear.plan_refuses, dear.plan_dearer) == (1, 0, 1)


def test_the_cross_check_sees_a_disagreeing_planner() -> None:
    """A deliberate positive case: a planner that cuts corners (the client does not) must be
    caught, or a zero above would prove nothing."""

    def corner_cutter(
        grid: SheetGrid, x0: int, y0: int, x1: int, y1: int, *, max_len: int
    ) -> list[Cell] | None:
        """A diagonal dash with no corner check and no search."""
        cells, x, y = [], x0, y0
        while (x, y) != (x1, y1):
            x += (x1 > x) - (x1 < x)
            y += (y1 > y) - (y1 < y)
            if grid.nopass(x, y):
                return None
            cells.append((x, y))
        return cells

    rows = ["....", ".#..", "....", "...."]
    walk = Walk(width=4, height=4, rows=rows)
    t = cross_check(walk, [((0, 0), (2, 1)), ((0, 1), (1, 0))], planner=corner_cutter)
    assert t.disagreements  # the corner-cutting dash is illegal, or disagrees on reachability


# --- the lab's real maps (LOCAL only) -----------------------------------------------------------
GAT_DIR = os.environ.get("PORING_FLOW_CROSSCHECK_GAT")


@pytest.mark.skipif(not GAT_DIR, reason="local only: set PORING_FLOW_CROSSCHECK_GAT=<GAT dir>")
def test_the_planners_agree_on_the_labs_real_maps() -> None:
    gats = sorted(Path(str(GAT_DIR)).glob("*.gat"))
    assert gats, f"no GAT in {GAT_DIR}"
    report = {}
    for path in gats:
        mine = read_gat(path)  # the linter's grid (kbsheet)
        assert mine is not None, path.name
        theirs = dgat.parse(path.read_bytes()).walkable()  # the executor's grid
        assert theirs.shape == (mine.height, mine.width)
        same = all(
            mine.walkable((x, y)) == bool(theirs[y, x])
            for y in range(mine.height)
            for x in range(mine.width)
        )
        assert same, f"{path.name}: the two GAT readers see different walkable cells"
        t = cross_check(mine, sample_pairs(mine, 40, seed=18, reach=60))
        assert t.disagreements == [], (path.name, t.disagreements[:5])
        report[path.stem] = (
            t.pairs,
            t.reachable,
            t.unreachable,
            t.longer_than_plan,
            t.plan_refuses,
            t.plan_dearer,
            t.step_diffs,
        )
    print(
        "\ncross-check (pairs, reachable, unreachable, legs > 48 steps, of which one plan refuses /"
        " takes a dearer walk, equal-cost walks with another step count):"
    )
    for name, row in report.items():
        print(f"  {name}: {row}")
