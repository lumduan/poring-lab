#!/usr/bin/env python3
"""WALKS AS BLOCKS -- the pure core of "record a path by walking" as Batt designed it
(docs/planning/waypoints-npc-recording.md Amendment 5, 2026-11-22: "the system is only a block
generator"). The player walks; this module THINS her cell reads into a few points and GENERATES a
run of ordinary ``walk_to(cell(map, x, y))`` blocks (the palette's own block, concept
``nav.walk_to``; poring_flow/blocks.yaml, editor.PALETTE) for the flow of the map she is on. The
person edits them like any block, or writes them by hand without walking. Nothing new beyond that:
no path file, no multi-map path, no legs, exits or "wrong map" state. One map = one flow (a map
node's main tab); a map change is the /maps links' business, as it already is.

Everything here is PURE: no live read, no input, no file written, no lab service needed. The
recording page, the live reads (selfpos, /where on a minimap change) and the walker build on it.

COORDINATES: map cells, x east, y NORTH, as map_routes / map_zones and the IR's CellRef (the
minimap readout's, /where's and the server's numbers); a grid is indexed [y, x], no flip anywhere.

THINNING (``thin``; Amendment 1 b, kept from 1424b810): from the raw reads (t, map, x, y,
confirmed) to points, ONE RUN PER MAP STAY.
- Unconfirmed reads are dropped (their content is not looked at). Confirmed reads must be in time
  order. A MAP CHANGE ends the run on that map and starts the next map's: the result is every run
  in walking order (``Run``: its map, its points, the map she went to next), each to go into that
  map's own flow. A map visited twice gives two runs (two proposals for its flow).
- Within a run, consecutive reads of the same cell are one track point (standing still adds
  nothing). Kept: the run's first and last cells, every MARK (a time: the confirmed read nearest
  to it, the earlier on a tie), every TURN (below), and a point each time she has moved
  ``every_cells`` (Chebyshev) from the last kept one.
- A TURN: at a track point, the heading in (from the latest earlier point at least ``turn_span``
  cells away) and the heading out (to the first later point at least ``turn_span`` away) differ by
  more than ``turn_deg``; of consecutive such points, the sharpest (the middle one of a tie: a
  turn-back's tip).
- Never two kept points closer than ``min_step`` (Chebyshev), except at a run's ends or a mark: a
  turn or distance point that close to the last kept point, or to the next protected one, is not
  kept. A mark or a run's end on the last kept point's cell is merged into it.
- Every threshold is passed in (``ThinSettings``, our values as its defaults: Batt 2026-11-13,
  everything a user would set is a setting; Amendment 5 answer 10).

THE BLOCKS (``walk_blocks``): each point -> ``walk_to(cell("<map>", x, y))`` exactly as the studio
parses it (pyview's action shape: the block, its catalogue concept and default timeout, on_fail
stop), validated by the IR's own model. A MARK becomes the block's ``note`` (Amendment 5 answer 11;
the IR's ActionStmt.note, printed ``note="..."`` in the Python view). A walk_to has no arrival
radius: the earlier core's per-point radius went with its path file.

THE PROPOSAL (``propose`` / ``apply``; matpilot's UI lesson, Amendment 1: nothing changes in a
program without the person's click): the blocks inserted into a MAP NODE's main tab at a position,
as a NEW project loaded by the project model's own loader (``project.from_json``: the hostile-input
caps, the schema, the shape rules); the input project is never changed. ``apply`` hands the new
project over only while the project is still the one the proposal was made from.

THE ROUTE (``routes_in`` / ``route_at``; Amendment 5: "a run of consecutive walk_to blocks is the
route"): a maximal run of consecutive statements of ONE list (a main, a function's body, an if's
branch) that are walk_to blocks with a literal cell on one map. Anything else ends it: another
block, a walk_to on another map, a walk_to whose cell is held by a variable (not a known point).

THE WALK CHECK (``check_route``; section 3 item 2, Amendment 5 answers 1-2): each point and each
SEGMENT (two consecutive points) on the map's walk grid as given, with its zones -- map_routes' own
functions: ``route_grid`` (the walkable cells minus every zone and what the zones seal off),
``closed_why`` (a point that cannot be stood on), ``leg_path`` (hunt_core.astar, the runner's own
router) and ``path_cost``. No warp cell is cut from the grid (Batt: the user's line is followed; a
no-enter zone keeps her off a warp). A problem is a WARNING for the editor to draw red, never a
refusal: ok / closed / broken, or unproven when there is no grid for the map.

THE GPS REJOIN (``rejoin``; Amendment 5 "off the route: GPS", answer 5): knocked off by a monster
or any detour, she rejoins at the NEAREST cell ALONG the route's line (between two points too),
AHEAD of the last point she passed, and walks on from there; never back to the start.
- The line: each segment sampled one cell per step (``map_routes.seg_cells``), in walking order,
  from just after the last point passed (the whole line, its first point included, when she has
  passed none).
- NEAREST: by the straight-line distance between the cells, in cells (compared as squared whole
  numbers: exact) -- where a perpendicular from her meets the line, what a person and a GPS call
  the nearest point. Not Chebyshev: its ties grow with the distance (2d + 1 cells along a straight
  segment), so from far away "as near" would run a long way down the line. ``distance`` is still
  reported in Chebyshev cells (map_routes' measure, an 8-way step is one cell), as ``tol`` is.
- THE TIE RULE (exactly equal distances): the FIRST STRETCH of the equally near cells in walking
  order (a run of adjacent cells along the line), and of that stretch its FAR END. So a later part
  of the route that passes as near (an out-and-back route's way back, a loop) never makes her skip
  the part in between, and she never walks back along a stretch.
- ``next``: the walk_to to run once she is at the rejoin cell -- the first point AFTER that cell
  along the line (a rejoin ON point j continues with j + 1); None when none is left.
- DONE: she passed the last point; or the rejoin is on the last segment and she is within ``tol``
  of the last point (map_routes.reached's tolerance, the runner's 2 cells by default). Within tol
  of the last point alone is not enough: a loop ends where it starts.
- The distance ignores walls: the nearest cell may lie behind one (a question for Batt).
"""

from __future__ import annotations

import bisect
import json
import math
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path as FsPath
from typing import Any, NamedTuple

import numpy as np
from pydantic import ValidationError

sys.path.insert(0, str(FsPath(__file__).resolve().parent))
import map_routes as mr  # noqa: E402
import map_zones as mz  # noqa: E402

from poring_flow import ir  # noqa: E402
from poring_flow import project as pj  # noqa: E402
from poring_flow.catalogue import catalogue  # noqa: E402

Cell = tuple[int, int]

WALK_TO = "walk_to"  # the palette's block (editor.PALETTE), concept nav.walk_to
CELL_MAX = 2048  # a coordinate is 0 .. CELL_MAX - 1: the IR's CellRef (ir.Coord)
MARK_NOTE = "mark"  # a mark's note on its block (the person edits it like any note)
TIE_DEG = 1e-9  # two heading changes this close are equally sharp (float rounding, not a setting)
MAP_ID = re.compile(ir.MAP_ID)
NO_GRID = "no walk grid for this map: not proven"
NOT_CONNECTED = "not connected on the route grid (the walkable cells minus the zones)"


class PathError(ValueError):
    """A recording, a block list, a route or a proposal that is not valid: refused, nothing
    changes."""


def _int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _cell_problem(c: Any, what: str) -> str | None:
    if not isinstance(c, tuple) or len(c) != 2 or not all(_int(v) for v in c):
        return f"{what} is not a cell (x, y) of two whole numbers"
    if not all(0 <= v < CELL_MAX for v in c):
        return f"{what} {list(c)} is outside 0 .. {CELL_MAX - 1}"
    return None


def _cell_arg(cell: Any, what: str = "the cell") -> Cell:
    if not isinstance(cell, Sequence) or isinstance(cell, str) or len(cell) != 2:
        raise PathError(f"{what} is not (x, y)")
    c = (cell[0], cell[1])
    why = _cell_problem(c, what)
    if why is not None:
        raise PathError(why)
    return c


# --- thinning (Amendment 1 b) ---------------------------------------------------------------------


class Read(NamedTuple):
    """One raw read of her cell: its time (s, any one clock), the map, x, y, and whether the read
    was CONFIRMED (selfpos' re-read rule). Unconfirmed reads may carry None."""

    t: float
    map: str | None
    x: int | None
    y: int | None
    confirmed: bool


@dataclass(frozen=True)
class ThinSettings:
    every_cells: int = 10  # keep a point each time she has moved this far (Chebyshev)
    min_step: int = 3  # never two kept points closer, except at a run's ends or a mark
    turn_deg: float = 40.0  # a turn: the heading changes by MORE than this (180: turns off)
    turn_span: int = 3  # the headings are measured over at least this many cells


DEFAULTS = ThinSettings()


def settings_problem(s: Any) -> str | None:
    """PURE: why ``s`` is not usable thinning settings (None: they are)."""
    if not isinstance(s, ThinSettings):
        return "not thinning settings"
    for name in ("every_cells", "min_step", "turn_span"):
        v = getattr(s, name)
        if not _int(v) or v < 1:
            return f"{name} {v!r} is not a whole number of at least 1"
    d = s.turn_deg
    if not isinstance(d, int | float) or isinstance(d, bool) or not 0 < d <= 180:
        return f"turn_deg {d!r} is not a number of degrees above 0, at most 180"
    return None


@dataclass(frozen=True)
class Point:
    """A kept point: a cell, and ``mark`` when the person marked it while recording."""

    x: int
    y: int
    mark: bool = False

    @property
    def cell(self) -> Cell:
        return (self.x, self.y)


@dataclass(frozen=True)
class Run:
    """One stay on one map: its points in walking order, for that map's flow. ``next_map``: the
    map she went to when it ended (None: the recording ended on this map)."""

    map: str
    points: tuple[Point, ...]
    next_map: str | None = None

    def cells(self) -> tuple[Cell, ...]:
        return tuple(p.cell for p in self.points)


@dataclass(frozen=True)
class Thinned:
    runs: tuple[Run, ...]  # walking order, one per map stay
    dropped: int  # unconfirmed reads dropped


def _time(t: Any, what: str) -> float:
    if not isinstance(t, int | float) or isinstance(t, bool) or not math.isfinite(t):
        raise PathError(f"{what}: its time {t!r} is not a finite number")
    return float(t)


def _confirmed(reads: Iterable[Sequence[Any]]) -> tuple[list[tuple[float, str, Cell]], int]:
    """The confirmed reads as (t, map, cell), checked; and how many unconfirmed were dropped."""
    out: list[tuple[float, str, Cell]] = []
    n = 0
    for k, raw in enumerate(reads):
        n += 1
        if not isinstance(raw, Sequence) or isinstance(raw, str) or len(raw) != 5:
            raise PathError(f"read {k} is not (t, map, x, y, confirmed)")
        r = Read(*raw)
        if not isinstance(r.confirmed, bool):
            raise PathError(f"read {k}: confirmed is not true or false")
        if not r.confirmed:
            continue
        t = _time(r.t, f"read {k}")
        if not isinstance(r.map, str) or not MAP_ID.fullmatch(r.map):
            raise PathError(f"read {k}: map {r.map!r} is not a map name")
        x, y = r.x, r.y
        why = _cell_problem((x, y), f"read {k}'s cell")
        if why is not None or not isinstance(x, int) or not isinstance(y, int):
            raise PathError(why or f"read {k}'s cell is not two whole numbers")
        if out and t < out[-1][0]:
            raise PathError(f"read {k}: the confirmed reads are not in time order")
        out.append((t, r.map, (x, y)))
    return out, n - len(out)


def _nearest(times: Sequence[float], t: float) -> int:
    """The index of the time nearest ``t`` (the earlier on a tie); ``times`` sorted."""
    i = bisect.bisect_left(times, t)
    if i == 0:
        return 0
    if i == len(times):
        return i - 1
    return i - 1 if t - times[i - 1] <= times[i] - t else i


def _angle(u: Cell, v: Cell) -> float:
    """The angle between two non-zero vectors, degrees 0 .. 180."""
    dot = u[0] * v[0] + u[1] * v[1]
    c = dot / (math.hypot(*u) * math.hypot(*v))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def turn_angles(track: Sequence[Cell], span: int) -> list[float]:
    """PURE: each track point's heading change, degrees: in from the latest earlier point at least
    ``span`` cells away (Chebyshev), out to the first later one; 0 where either is missing."""
    n = len(track)
    out = [0.0] * n
    for i in range(1, n - 1):
        c = track[i]
        b = next((k for k in range(i - 1, -1, -1) if mr.cheb(track[k], c) >= span), None)
        f = next((k for k in range(i + 1, n) if mr.cheb(c, track[k]) >= span), None)
        if b is None or f is None:
            continue
        p, q = track[b], track[f]
        out[i] = _angle((c[0] - p[0], c[1] - p[1]), (q[0] - c[0], q[1] - c[1]))
    return out


def turn_points(track: Sequence[Cell], deg: float, span: int) -> list[int]:
    """PURE: the TURNS of a track: of each run of consecutive points turning by more than ``deg``
    (``turn_angles``), the sharpest; of several equally sharp, the middle one (a turn-back's
    points all read 180 degrees around its tip, and the tip is their middle)."""
    ang = turn_angles(track, span)
    out: list[int] = []
    i = 0
    while i < len(track):
        if ang[i] <= deg:
            i += 1
            continue
        j = i
        while j + 1 < len(track) and ang[j + 1] > deg:
            j += 1
        best = max(ang[i : j + 1])
        ties = [k for k in range(i, j + 1) if ang[k] >= best - TIE_DEG]
        out.append(ties[(len(ties) - 1) // 2])
        i = j + 1
    return out


def thin_track(track: Sequence[Cell], marked: Iterable[int], s: ThinSettings = DEFAULTS
               ) -> list[tuple[int, bool]]:  # fmt: skip
    """PURE: one run's kept points as (track index, mark), by the rules of the module docstring.
    ``track``: the run's cells with no two consecutive ones equal; ``marked``: marked indices."""
    n = len(track)
    marks = set(marked)
    if any(not 0 <= i < n for i in marks):
        raise PathError("a mark is outside the track")
    for i in range(1, n):
        if track[i] == track[i - 1]:
            raise PathError(f"track point {i} repeats the one before it")
    turns = set(turn_points(track, s.turn_deg, s.turn_span))
    protected = sorted({0, n - 1} | marks)
    out: list[list[Any]] = [[0, 0 in marks]]
    pi = 0
    for i in range(1, n):
        c, last = track[i], track[out[-1][0]]
        if i in marks or i == n - 1:
            if c == last:  # back on the last kept cell: that point takes this one's role
                out[-1][1] = out[-1][1] or i in marks
            else:
                out.append([i, i in marks])
            continue
        while protected[pi] <= i:
            pi += 1
        d = mr.cheb(c, last)
        if d < s.min_step or mr.cheb(c, track[protected[pi]]) < s.min_step:
            continue
        if i in turns or d >= s.every_cells:
            out.append([i, False])
    return [(int(i), bool(m)) for i, m in out]


def thin(reads: Iterable[Sequence[Any]], *, marks: Iterable[float] = (),
         settings: ThinSettings = DEFAULTS) -> Thinned:  # fmt: skip
    """PURE: the raw reads of a recording -> its RUNS, one per map stay (the module docstring's
    THINNING). ``reads``: (t, map, x, y, confirmed) in time order; ``marks``: the times the person
    marked a point; ``settings``: every threshold. PathError on bad input."""
    why = settings_problem(settings)
    if why is not None:
        raise PathError(f"settings: {why}")
    conf, dropped = _confirmed(reads)
    if not conf:
        raise PathError("no confirmed read: there is nothing to keep")
    times = [r[0] for r in conf]
    starts = [0] + [i for i in range(1, len(conf)) if conf[i][1] != conf[i - 1][1]]
    bounds = list(zip(starts, [*starts[1:], len(conf)], strict=True))
    marked = {_nearest(times, _time(m, f"mark {k}")) for k, m in enumerate(marks)}
    runs = []
    for a, b in bounds:
        track: list[Cell] = []
        run_of: list[int] = []
        for _t, _m, c in conf[a:b]:
            if not track or track[-1] != c:
                track.append(c)
            run_of.append(len(track) - 1)
        kept = thin_track(track, {run_of[i - a] for i in marked if a <= i < b}, settings)
        points = tuple(Point(track[i][0], track[i][1], m) for i, m in kept)
        runs.append(Run(conf[a][1], points, conf[b][1] if b < len(conf) else None))
    return Thinned(tuple(runs), dropped)


# --- the blocks (Amendment 5) ---------------------------------------------------------------------


def walk_block(map_id: str, cell: Sequence[int], note: str | None = None) -> ir.ActionStmt:
    """PURE: ONE ``walk_to(cell(map_id, x, y))`` block in the IR's own shape (the studio parser's:
    the catalogue's concept and default timeout, on_fail stop), with ``note`` (None: none).
    PathError when the IR refuses it (a map id, a coordinate, a note too long)."""
    x, y = _cell_arg(cell)
    spec = catalogue().blocks[WALK_TO].spec
    ref = {"kind": "cell", "map": map_id, "x": x, "y": y}
    data = {"kind": "action", "block": WALK_TO, "concept": spec.concept,
            "params": {"cell": {"kind": "lit", "value": ref}}, "timeout_s": spec.timeout_s,
            "note": note}  # fmt: skip
    try:
        return ir.ActionStmt.model_validate(data)
    except ValidationError as e:
        first = e.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        raise PathError(f"walk_to on {map_id!r} at {[x, y]}: {where}: {first['msg']}") from None


def walk_blocks(map_id: str, points: Iterable[Point | Sequence[int]], *,
                mark_note: str = MARK_NOTE) -> tuple[ir.ActionStmt, ...]:  # fmt: skip
    """PURE: a walk_to block per point, in order, on ``map_id`` (a ``Point`` or a cell (x, y)); a
    marked point's block carries ``mark_note``."""
    out = []
    for k, p in enumerate(points):
        if isinstance(p, Point):
            out.append(walk_block(map_id, p.cell, mark_note if p.mark else None))
        else:
            out.append(walk_block(map_id, _cell_arg(p, f"point {k}")))
    if not out:
        raise PathError("no point: there is no block to make")
    return tuple(out)


def run_blocks(run: Run, *, mark_note: str = MARK_NOTE) -> tuple[ir.ActionStmt, ...]:
    """PURE: a run's blocks, for its own map's flow."""
    return walk_blocks(run.map, run.points, mark_note=mark_note)


# --- the route in a flow (Amendment 5: consecutive walk_to blocks) --------------------------------


def walk_cell(stmt: Any, map_id: str | None = None) -> tuple[str, Cell] | None:
    """PURE: (map, cell) of a walk_to block whose cell is a LITERAL (on ``map_id`` when given);
    None for anything else (another block or statement, a cell held by a variable)."""
    if not isinstance(stmt, ir.ActionStmt) or stmt.block != WALK_TO:
        return None
    e = stmt.params.get("cell")
    if not isinstance(e, ir.Lit) or not isinstance(e.value, ir.CellRef):
        return None
    c = e.value
    if map_id is not None and c.map != map_id:
        return None
    return c.map, (c.x, c.y)


@dataclass(frozen=True)
class Route:
    """A maximal run of consecutive walk_to blocks of one statement list: statements ``start`` ..
    ``stop`` - 1, their cells in order, on ``map``. Route point i is statement start + i."""

    start: int
    map: str
    cells: tuple[Cell, ...]

    @property
    def stop(self) -> int:
        return self.start + len(self.cells)


def routes_in(stmts: Sequence[Any], map_id: str | None = None) -> tuple[Route, ...]:
    """PURE: every route of ONE statement list (a main, a function's body, a branch), in order.
    Nested bodies are lists of their own (pass them). ``map_id``: only walk_to cells on that map
    count (the map node's map); None: a walk_to on another map than the one before it ends that
    route and starts the next."""
    out: list[Route] = []
    start, here = 0, ""
    cells: list[Cell] = []
    for i, st in enumerate([*stmts, None]):
        wc = walk_cell(st, map_id) if st is not None else None
        if cells and (wc is None or wc[0] != here):
            out.append(Route(start, here, tuple(cells)))
            cells = []
        if wc is not None:
            if not cells:
                start, here = i, wc[0]
            cells.append(wc[1])
    return tuple(out)


def route_at(stmts: Sequence[Any], i: int, map_id: str | None = None) -> Route | None:
    """PURE: the route statement ``i`` belongs to (None: it is not a walk_to of one)."""
    return next((r for r in routes_in(stmts, map_id) if r.start <= i < r.stop), None)


# --- the proposal (Amendment 1's UI lesson: nothing changes without the person's click) -----------


@dataclass(frozen=True)
class Proposal:
    """``blocks`` inserted into map node ``node``'s main tab at ``at``: ``project`` is the NEW
    project, ``base`` the one it was made from (never changed), ``route`` the route the inserted
    blocks belong to in the new main (None when the first is not a walk_to with a literal cell)."""

    node: str
    at: int
    blocks: tuple[ir.StmtT, ...]
    base: pj.Project
    project: pj.Project
    route: Route | None


def propose(project: pj.Project, node_id: str, at: int, blocks: Sequence[ir.StmtT]) -> Proposal:
    """PURE: a proposal to insert ``blocks`` into map node ``node_id``'s main tab before statement
    ``at`` (0 .. its length: the length appends). Refused (PathError) for a node that is not a map
    node, a position outside the main, no blocks, or a walk_to on another map than the node's; the
    new project is loaded by the project model's own loader (its ProjectError when it refuses)."""
    node = project.node(node_id)
    if not isinstance(node, pj.MapNode):
        what = "no node" if node is None else f"the {node.kind} node"
        raise PathError(f"{node_id!r} is {what}: walk_to blocks go into a map node's flow")
    main = node.main
    if not _int(at) or not 0 <= at <= len(main):
        raise PathError(f"position {at!r} is outside {node_id}'s main (0 .. {len(main)})")
    blocks = tuple(blocks)
    if not blocks:
        raise PathError("no block to insert")
    for k, b in enumerate(blocks):
        if not isinstance(b, ir.StmtT):
            raise PathError(f"block {k} is not a statement of the flow IR")
        wc = walk_cell(b)
        if wc is not None and wc[0] != node.map.map:
            raise PathError(f"block {k}: walk_to {list(wc[1])} is on {wc[0]}; {node_id} is on "
                            f"{node.map.map}")  # fmt: skip
    new_stmts = [b.model_dump(mode="json", by_alias=True, context=ir.PROJECT_JSON) for b in blocks]
    data = pj.dump(project)
    for nd in data["nodes"]:
        if nd["id"] == node_id:
            for t in nd["tabs"]:
                if t["name"] == pj.MAIN:
                    t["main"][at:at] = new_stmts
    new = pj.from_json(json.dumps(data, ensure_ascii=False))
    new_node = new.node(node_id)
    assert isinstance(new_node, pj.MapNode)
    route = route_at(new_node.main, at, node.map.map) if walk_cell(blocks[0]) else None
    return Proposal(node_id, at, blocks, project, new, route)


def apply(proposal: Proposal, current: pj.Project) -> pj.Project:
    """PURE: the person clicked: the proposal's new project, while ``current`` is still the
    project it was made from (its layout too); PathError when it changed (make it again)."""
    if pj.canonical_json(current) != pj.canonical_json(proposal.base):
        raise PathError("the project changed since this proposal was made: make it again")
    return proposal.project


# --- the walk check (section 3 item 2; Amendment 5 answers 1-2) -----------------------------------


@dataclass(frozen=True)
class PointCheck:
    i: int
    cell: Cell
    status: str  # ok | closed | unproven
    why: str | None


@dataclass(frozen=True)
class SegmentCheck:
    i: int  # point i -> point i + 1
    a: Cell
    b: Cell
    status: str  # ok | broken | unproven
    why: str | None
    steps: int | None  # cells walked on the route grid (8-connected)
    cost: float | None  # in straight steps (a diagonal = 1.4)


@dataclass(frozen=True)
class RouteCheck:
    points: tuple[PointCheck, ...]
    segments: tuple[SegmentCheck, ...]

    @property
    def ok(self) -> bool:
        return all(p.status == "ok" for p in self.points) and all(
            s.status == "ok" for s in self.segments
        )

    @property
    def warnings(self) -> tuple[str, ...]:
        out = [f"point {p.i} {list(p.cell)}: {p.why}" for p in self.points if p.status != "ok"]
        out += [f"segment {s.i} -> {s.i + 1} ({list(s.a)} -> {list(s.b)}): {s.why}"
                for s in self.segments if s.status != "ok"]  # fmt: skip
        return tuple(out)

    def doc(self) -> dict[str, Any]:
        """The editor's JSON: every point and segment with its status, and the warnings."""
        return {
            "ok": self.ok,
            "warnings": list(self.warnings),
            "points": [{"i": p.i, "cell": list(p.cell), "status": p.status, "why": p.why}
                       for p in self.points],
            "segments": [{"from": s.i, "to": s.i + 1, "a": list(s.a), "b": list(s.b),
                          "status": s.status, "why": s.why, "steps": s.steps, "cost": s.cost}
                         for s in self.segments],
        }  # fmt: skip


def check_route(cells: Sequence[Sequence[int]], grid: Any,
                zones: mz.Zones | None = None) -> RouteCheck:  # fmt: skip
    """PURE: a route's points and segments on its map (the module docstring's WALK CHECK).
    ``grid``: the map's walkable cells ([y, x]; warp cells stay in), None: no grid (every status
    unproven); ``zones``: the map's zones (None: none). A walk problem is never refused: it is a
    status and a warning. PathError only for input that is not a route."""
    pts = [_cell_arg(c, f"point {k}") for k, c in enumerate(cells)]
    if not pts:
        raise PathError("a route has at least one point")
    pairs = list(zip(pts, pts[1:], strict=False))
    if grid is None:
        return RouteCheck(
            tuple(PointCheck(i, c, "unproven", NO_GRID) for i, c in enumerate(pts)),
            tuple(SegmentCheck(i, a, b, "unproven", NO_GRID, None, None)
                  for i, (a, b) in enumerate(pairs)),
        )  # fmt: skip
    g = np.asarray(grid, dtype=bool)
    rg = mr.route_grid(g, zones)
    points = []
    for i, c in enumerate(pts):
        why = mr.closed_why(c, g, zones)  # map_routes.prove's own waypoint rule
        if why is None and not rg[c[1], c[0]]:
            why = "sealed off by the zones"
        points.append(PointCheck(i, c, "ok" if why is None else "closed", why))
    segments = []
    for i, (a, b) in enumerate(pairs):
        ends = [f"point {p.i} {list(p.cell)}: {p.why}" for p in points[i : i + 2]
                if p.why is not None]  # fmt: skip
        path = None if ends else mr.leg_path(rg, a, b)
        if path is None:
            segments.append(SegmentCheck(i, a, b, "broken", "; ".join(ends) or NOT_CONNECTED,
                                         None, None))  # fmt: skip
        else:
            cost = round(mr.path_cost(path), 1)
            segments.append(SegmentCheck(i, a, b, "ok", None, len(path) - 1, cost))
    return RouteCheck(tuple(points), tuple(segments))


# --- the GPS rejoin (Amendment 5) -----------------------------------------------------------------


class Rejoin(NamedTuple):
    """Where she rejoins the route: ``cell`` on its line, ``distance`` to it (cells, Chebyshev),
    ``next`` the route point (walk_to) to run once there (None: none left), and ``done`` when
    nothing is left to walk."""

    cell: Cell
    next: int | None
    distance: int
    done: bool


def rejoin(cells: Sequence[Sequence[int]], here: Sequence[int], last: int | None = None,
           tol: int = mr.REACH_TOL) -> Rejoin:  # fmt: skip
    """PURE: the GPS rejoin of the module docstring. ``cells``: the route's points in order (a
    ``Route``'s cells); ``here``: her cell; ``last``: the last route point she passed (None: none
    yet); ``tol``: within it of the last point she is there. PathError on bad input."""
    pts = [_cell_arg(c, f"point {k}") for k, c in enumerate(cells)]
    me = _cell_arg(here, "her cell")
    n = len(pts)
    if not n:
        raise PathError("a route has at least one point")
    if last is not None and (not _int(last) or not 0 <= last < n):
        raise PathError(f"last {last!r} is not a point of the route (0 .. {n - 1})")
    if not _int(tol) or tol < 0:
        raise PathError(f"tol {tol!r} is not a whole number of at least 0")
    end = pts[-1]
    # the line ahead, in walking order: (a cell, the first point after it)
    line: list[tuple[Cell, int]] = [(pts[0], 1)] if last is None else []
    for k in range(0 if last is None else last, n - 1):
        seg = mr.seg_cells(pts[k], pts[k + 1])[1:]
        line += [(c, k + 1 if j < len(seg) - 1 else k + 2) for j, c in enumerate(seg)]
    to_end = mr.cheb(me, end)
    if not line:  # she passed the last point (or only repeats of it are left)
        return Rejoin(end, None, to_end, True)
    d2 = [(c[0] - me[0]) ** 2 + (c[1] - me[1]) ** 2 for c, _ in line]  # exact: whole numbers
    best = min(d2)
    i = d2.index(best)  # the first stretch of the nearest cells ...
    while i + 1 < len(line) and d2[i + 1] == best:
        i += 1  # ... at its far end
    cell, nxt = line[i]
    while nxt < n and pts[nxt] == cell:  # a point on the rejoin cell itself is reached there
        nxt += 1
    if nxt >= n - 1 and to_end <= tol:  # on the last segment, and at its end
        return Rejoin(end, None, to_end, True)
    return Rejoin(cell, nxt if nxt < n else None, mr.cheb(me, cell), False)
