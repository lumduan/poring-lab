"""rAthena's walk path search, ported exactly (src/map/path.cpp at RATHENA_REF).

The server and the game client walk the SAME cells: path.cpp's A* "is what game client uses" and its
binary heap "matches client bheap" (BHEAP_PUSH2/POP2/UPDATE in common/db.hpp). Ties between equal
f-costs are broken by that heap's sift order, so it is reproduced literally -- a different priority
queue would pick a different, equally short path around obstacles.

Quirks kept on purpose (they change which paths exist):
  * the node table has MAX_WALKPATH**2 slots indexed by (x + y*MAX_WALKPATH) & (size-1); a slot
    collision aborts the search (path.cpp's own FIXME);
  * the heuristic is Manhattan * MOVE_COST (inadmissible, like the client);
  * diagonals are allowed only when both orthogonal neighbours are passable (no corner cutting);
  * the length cap is sizeof(wpd->path) = MAX_WALKPATH * sizeof(enum) = 128 steps.
"""

from dataclasses import dataclass
from typing import Protocol

MOVE_COST = 10
MOVE_DIAGONAL_COST = 14
MAX_WALKPATH = 32
_SLOTS = MAX_WALKPATH * MAX_WALKPATH
_MAX_LEN = MAX_WALKPATH * 4  # sizeof(enum directions[MAX_WALKPATH]) in path.cpp's length check

_NORTH, _WEST, _SOUTH, _EAST = 1, 2, 4, 8
_OPEN, _CLOSED = 0, 1


class Grid(Protocol):
    @property
    def xs(self) -> int: ...

    @property
    def ys(self) -> int: ...

    def nopass(self, x: int, y: int) -> bool: ...


@dataclass(slots=True, eq=False)
class _Node:
    x: int = 0
    y: int = 0
    g: int = 0
    f: int = 0
    flag: int = _OPEN
    parent: "_Node | None" = None


def _h(x0: int, y0: int, x1: int, y1: int) -> int:
    return MOVE_COST * (abs(x1 - x0) + abs(y1 - y0))


def _index(x: int, y: int) -> int:
    return (x + y * MAX_WALKPATH) & (_SLOTS - 1)


class _Heap:
    """common/db.hpp BHEAP_*2 with the A* comparator NODE_MINTOPCMP (f_cost difference)."""

    def __init__(self) -> None:
        self.a: list[_Node] = []

    def _siftdown(self, start: int, idx: int) -> None:
        i = idx
        while i > start:
            parent = (i - 1) // 2
            if self.a[parent].f - self.a[i].f <= 0:
                break
            self.a[parent], self.a[i] = self.a[i], self.a[parent]
            i = parent

    def _siftup(self, idx: int) -> None:
        i = idx
        n = len(self.a)
        left = i * 2 + 1
        while left < n:
            right = i * 2 + 2
            if right >= n or self.a[left].f - self.a[right].f < 0:
                self.a[i], self.a[left] = self.a[left], self.a[i]
                i = left
            else:
                self.a[i], self.a[right] = self.a[right], self.a[i]
                i = right
            left = i * 2 + 1
        self._siftdown(idx, i)

    def push(self, node: _Node) -> None:
        self.a.append(node)
        self._siftdown(0, len(self.a) - 1)

    def pop(self) -> _Node:
        top = self.a[0]
        last = self.a.pop()
        if self.a:
            self.a[0] = last
            self._siftup(0)
        return top

    def update(self, node: _Node) -> bool:
        """False = not found (path.cpp logs and aborts the search)."""
        for i, candidate in enumerate(self.a):
            if candidate is node:
                self._siftdown(0, i)
                self._siftup(i)
                return True
        return False


def path_search(
    grid: Grid, x0: int, y0: int, x1: int, y1: int, *, easy: bool = False
) -> list[tuple[int, int]] | None:
    """Cells after (x0, y0) up to and including (x1, y1); None when rAthena finds no path."""
    if not (0 <= x0 < grid.xs and 0 <= y0 < grid.ys):
        return None
    if not (0 <= x1 < grid.xs and 0 <= y1 < grid.ys) or grid.nopass(x1, y1):
        return None
    if easy:
        return _easy_path(grid, x0, y0, x1, y1)
    return _astar(grid, x0, y0, x1, y1)


def _easy_path(grid: Grid, x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]] | None:
    dx = (x1 > x0) - (x1 < x0)
    dy = (y1 > y0) - (y1 < y0)
    x, y = x0, y0
    cells: list[tuple[int, int]] = []
    while len(cells) < MAX_WALKPATH:
        x, y = x + dx, y + dy
        cells.append((x, y))
        if x == x1:
            dx = 0
        if y == y1:
            dy = 0
        if dx == 0 and dy == 0:
            break
        if grid.nopass(x, y):
            break
    return cells if (x, y) == (x1, y1) else None


def _astar(grid: Grid, x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]] | None:
    tp = [_Node() for _ in range(_SLOTS)]
    heap = _Heap()
    start = tp[_index(x0, y0)]
    start.x, start.y, start.g, start.f, start.flag = x0, y0, 0, _h(x0, y0, x1, y1), _OPEN
    heap.push(start)
    xs, ys = grid.xs - 1, grid.ys - 1

    def add(x: int, y: int, g: int, parent: _Node, h: int) -> bool:
        """path.cpp add_path; True = error (abort the search)."""
        node = tp[_index(x, y)]
        if node.x == x and node.y == y:
            if g < node.g:
                node.g, node.parent, node.f = g, parent, g + h
                if node.flag == _CLOSED:
                    heap.push(node)
                elif not heap.update(node):
                    return True
                node.flag = _OPEN
            return False
        if node.x or node.y:  # the slot is taken by another cell (path.cpp FIXME)
            return True
        node.x, node.y, node.g, node.parent, node.f, node.flag = x, y, g, parent, g + h, _OPEN
        heap.push(node)
        return False

    while True:
        if not heap.a:
            return None
        current = heap.pop()
        x, y, g = current.x, current.y, current.g
        current.flag = _CLOSED
        if x == x1 and y == y1:
            break
        allowed = 0
        if y < ys and not grid.nopass(x, y + 1):
            allowed |= _NORTH
        if y > 0 and not grid.nopass(x, y - 1):
            allowed |= _SOUTH
        if x < xs and not grid.nopass(x + 1, y):
            allowed |= _EAST
        if x > 0 and not grid.nopass(x - 1, y):
            allowed |= _WEST

        def ok(d: int) -> bool:
            return (allowed & d) == d  # noqa: B023 -- evaluated within this iteration only

        error = False
        if ok(_SOUTH | _EAST) and not grid.nopass(x + 1, y - 1):
            error |= add(x + 1, y - 1, g + MOVE_DIAGONAL_COST, current, _h(x + 1, y - 1, x1, y1))
        if ok(_EAST):
            error |= add(x + 1, y, g + MOVE_COST, current, _h(x + 1, y, x1, y1))
        if ok(_NORTH | _EAST) and not grid.nopass(x + 1, y + 1):
            error |= add(x + 1, y + 1, g + MOVE_DIAGONAL_COST, current, _h(x + 1, y + 1, x1, y1))
        if ok(_NORTH):
            error |= add(x, y + 1, g + MOVE_COST, current, _h(x, y + 1, x1, y1))
        if ok(_NORTH | _WEST) and not grid.nopass(x - 1, y + 1):
            error |= add(x - 1, y + 1, g + MOVE_DIAGONAL_COST, current, _h(x - 1, y + 1, x1, y1))
        if ok(_WEST):
            error |= add(x - 1, y, g + MOVE_COST, current, _h(x - 1, y, x1, y1))
        if ok(_SOUTH | _WEST) and not grid.nopass(x - 1, y - 1):
            error |= add(x - 1, y - 1, g + MOVE_DIAGONAL_COST, current, _h(x - 1, y - 1, x1, y1))
        if ok(_SOUTH):
            error |= add(x, y - 1, g + MOVE_COST, current, _h(x, y - 1, x1, y1))
        if error:
            return None

    cells: list[tuple[int, int]] = []
    node: _Node | None = current
    while node is not None and node.parent is not None:
        cells.append((node.x, node.y))
        node = node.parent
    if len(cells) > _MAX_LEN:
        return None
    cells.reverse()
    return cells
