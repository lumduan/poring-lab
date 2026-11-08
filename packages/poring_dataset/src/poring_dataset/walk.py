"""Walk paths on a map's walkability grid: textbook A* (Hart, Nilsson & Raphael, 1968), written
for this lab from the algorithm's published definition (Post-S2 round E1, 2026-10-04).

It replaces paths.py, a literal port of rAthena's GPL path.cpp (removed; THIRD_PARTY.md).
CLEAN-ROOM SCOPE, stated plainly: this file was written without the GPL source open and copies none
of its structure (no fixed node table, no client heap order, no Manhattan heuristic). Its author
HAD read that source before, so it is not a strict clean-room implementation. One number was later
taken from the pinned source as a FACT, with no code (Phase 3 T0, 2026-10-04): the path limit
MAX_LEN, cited where it is defined.

The model (the game's documented movement rules, not anyone's code):
  * 8-neighbour steps; a straight step costs 10, a diagonal 14 -- the server's step timing (a
    diagonal step takes speed * 14 / 10 ms, poring_packets.world);
  * no corner cutting: a diagonal step needs both orthogonal neighbours walkable;
  * walks longer than ``max_len`` steps (default 32, the server's path buffer: MAX_LEN) do not
    exist;
  * the start cell is where the unit stands (never re-checked); the target must be walkable.

The search: octile distance as the heuristic (admissible and consistent for 10/14 costs, so the
first time the target is popped its path is a shortest one). Ties are broken deterministically --
lowest f, then lowest h (closer to the target), then insertion order -- so the same query always
returns the same path. Among EQUALLY short paths around an obstacle the game may pick another;
scripts/walk_check.py measures how often that matters against recorded walks.

Optional: an altitude cost (off by default) adds ``climb`` per world unit of height difference
between neighbouring cells, for planners that prefer flat ground. The default walks what the server
walks, which ignores height.
"""

import heapq
from collections.abc import Callable
from typing import Protocol

STRAIGHT = 10
DIAGONAL = 14
# The pinned server (rAthena e985006) keeps a walk in a 32-step buffer and refuses a longer path:
# path.hpp:14 MAX_WALKPATH 32, path.hpp:29-32 `path[MAX_WALKPATH]` of the one-byte `directions`
# (path.hpp:16), path.cpp:415 `len > sizeof(wpd->path)` fails the search; its straight walk stops
# at the same 32 (path.cpp:303). A fact read from the source, not code. 9,636 recorded walks were
# all found within it, the longest 14 steps (scripts/walk_check.py, 2026-10-04).
MAX_LEN = 32
STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))


class Grid(Protocol):
    @property
    def xs(self) -> int: ...

    @property
    def ys(self) -> int: ...

    def nopass(self, x: int, y: int) -> bool: ...


def octile(dx: int, dy: int) -> int:
    """The cost of the cheapest unobstructed walk across (dx, dy)."""
    dx, dy = abs(dx), abs(dy)
    return DIAGONAL * min(dx, dy) + STRAIGHT * (max(dx, dy) - min(dx, dy))


def walk_path(
    grid: Grid,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    *,
    max_len: int = MAX_LEN,
    altitude: Callable[[int, int], float] | None = None,
    climb: float = 0.0,
) -> list[tuple[int, int]] | None:
    """The cells after (x0, y0) up to and including (x1, y1) on a shortest walk, [] when already
    there, None when there is none within ``max_len`` steps (or a point is off the map, or the
    target is not walkable)."""
    if not (0 <= x0 < grid.xs and 0 <= y0 < grid.ys):
        return None
    if not (0 <= x1 < grid.xs and 0 <= y1 < grid.ys) or grid.nopass(x1, y1):
        return None
    if (x0, y0) == (x1, y1):
        return []
    if max(abs(x1 - x0), abs(y1 - y0)) > max_len:
        return None  # even a straight walk is too long
    start, goal = (x0, y0), (x1, y1)
    g: dict[tuple[int, int], float] = {start: 0.0}
    steps: dict[tuple[int, int], int] = {start: 0}
    parent: dict[tuple[int, int], tuple[int, int]] = {}
    closed: set[tuple[int, int]] = set()
    order = 0
    h0 = octile(x1 - x0, y1 - y0)
    frontier: list[tuple[float, int, int, tuple[int, int]]] = [(float(h0), h0, order, start)]
    while frontier:
        _f, _h, _o, cell = heapq.heappop(frontier)
        if cell in closed:
            continue  # a stale entry: the cell was reached cheaper since
        if cell == goal:
            path = [cell]
            while path[-1] in parent:
                path.append(parent[path[-1]])
            path.pop()  # the start
            return path[::-1]
        closed.add(cell)
        cx, cy = cell
        for dx, dy in STEPS:
            nx, ny = cx + dx, cy + dy
            nxt = (nx, ny)
            if nxt in closed or grid.nopass(nx, ny):
                continue
            if dx and dy and (grid.nopass(cx + dx, cy) or grid.nopass(cx, cy + dy)):
                continue  # no corner cutting
            n_steps = steps[cell] + 1
            if n_steps + max(abs(x1 - nx), abs(y1 - ny)) > max_len:
                continue  # cannot reach the goal within max_len steps from here
            cost = g[cell] + (DIAGONAL if dx and dy else STRAIGHT)
            if altitude is not None and climb:
                cost += climb * abs(altitude(nx, ny) - altitude(cx, cy))
            if cost < g.get(nxt, float("inf")):
                g[nxt], steps[nxt], parent[nxt] = cost, n_steps, cell
                h = octile(x1 - nx, y1 - ny)
                order += 1
                heapq.heappush(frontier, (cost + h, h, order, nxt))
    return None


def straight_path(grid: Grid, x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]] | None:
    """Diagonal steps first, then straight -- no search; None as soon as a cell is not walkable
    (the cheap walk a client tries before searching)."""
    cells: list[tuple[int, int]] = []
    x, y = x0, y0
    while (x, y) != (x1, y1):
        x += (x1 > x) - (x1 < x)
        y += (y1 > y) - (y1 < y)
        if grid.nopass(x, y):
            return None
        cells.append((x, y))
    return cells


# What the lab server accepts for ONE walk click (dungeon@9.12, rogue-xmas02.md 4AE). Two facts, no
# code: `max_walk_path: 17` is read from the running server's conf/battle/client.conf:42
# (2026-11-09); a walk whose straight line is blocked is refused beyond 14 steps -- MEASURED on the
# lab's own packets: of 2,933 move requests made standing (pilots p13r-p21, xmas_dun02), the rule
# below called all 2,607 answered ones accepted and 325 of the 326 the server never answered refused
# (no path 141, longer than 17: 132, a blocked line and longer than 14: 52).
MAX_CLICK_WALK = 17
MAX_DETOUR_WALK = 14


def line_clear(grid: Grid, x0: int, y0: int, x1: int, y1: int) -> bool:
    """Every cell of the textbook Bresenham line (Bresenham, 1965) from (x0, y0) to (x1, y1), both
    ends included, is passable."""
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx, sy = (1 if x1 > x0 else -1), (1 if y1 > y0 else -1)
    err = dx - dy
    x, y = x0, y0
    while True:
        if grid.nopass(x, y):
            return False
        if (x, y) == (x1, y1):
            return True
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy


def click_walk_ok(grid: Grid, x0: int, y0: int, x1: int, y1: int, *,
                  max_walk: int = MAX_CLICK_WALK,
                  max_detour: int = MAX_DETOUR_WALK) -> bool:  # fmt: skip
    """Would the server walk us from (x0, y0) to (x1, y1) on ONE click: a walk exists, it is at most
    ``max_walk`` steps, and at most ``max_detour`` unless the straight line is clear."""
    path = walk_path(grid, x0, y0, x1, y1)
    if path is None or len(path) > max_walk:
        return False
    return len(path) <= max_detour or line_clear(grid, x0, y0, x1, y1)
