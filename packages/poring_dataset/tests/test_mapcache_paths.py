"""poring_dataset.mapcache + paths: rAthena's walkability and walk paths (docs/phase2-plan.md)."""

import struct
import zlib
from dataclasses import dataclass

import pytest

from poring_dataset import mapcache
from poring_dataset.walk import MAX_LEN, octile, straight_path, walk_path


def cache_bytes(maps: dict[str, tuple[int, int, bytes]]) -> bytes:
    body = b""
    for name, (xs, ys, cells) in maps.items():
        z = zlib.compress(cells)
        body += struct.pack("<12shhi", name.encode(), xs, ys, len(z)) + z
    return struct.pack("<IHH", 8 + len(body), len(maps), 0) + body


def test_parse_and_precedence() -> None:
    a = mapcache.parse(cache_bytes({"m1": (3, 2, bytes([0, 1, 5, 0, 3, 0]))}))
    b = mapcache.parse(cache_bytes({"m1": (2, 2, bytes(4)), "m2": (2, 2, bytes(4))}))
    grid = a["m1"]
    assert (grid.xs, grid.ys, grid.gat(1, 0), grid.gat(1, 1)) == (3, 2, 1, 3)
    merged = mapcache.merge([a, b])
    assert merged["m1"].xs == 3  # the first file containing a map wins
    assert set(merged) == {"m1", "m2"}


def test_bad_caches_are_refused() -> None:
    with pytest.raises(mapcache.MapCacheError):
        mapcache.parse(b"\x00" * 4)
    data = bytearray(cache_bytes({"m": (2, 2, bytes(4))}))
    data[0] += 1  # header size no longer matches
    with pytest.raises(mapcache.MapCacheError):
        mapcache.parse(bytes(data))


def test_nopass_matches_rathena_including_the_last_row_and_column() -> None:
    grid = mapcache.MapGrid("m", 4, 4, bytes([0, 0, 0, 0, 0, 1, 5, 0, 0, 3, 0, 0, 0, 0, 0, 0]))
    assert not grid.nopass(0, 0) and not grid.nopass(1, 2)  # 0 and 3 (water) are walkable
    assert grid.nopass(1, 1) and grid.nopass(2, 1)  # 1 = wall, 5 = cliff
    assert grid.nopass(3, 0) and grid.nopass(0, 3)  # last column / row: never passable
    assert grid.nopass(-1, 0) and grid.nopass(0, 9)


@pytest.mark.skipif(
    not (mapcache.GENERATED / "map_cache.base.dat").exists(), reason="run gen_mapcache"
)
def test_the_lab_maps_load_from_the_pinned_caches() -> None:
    maps = mapcache.load(prere=True)
    fild, church, newbie = maps["prt_fild08"], maps["prt_church"], maps["new_4-1"]
    assert (fild.xs, fild.ys, church.xs, church.ys, newbie.xs) == (400, 400, 200, 200, 200)
    assert not fild.nopass(170, 375)  # the benchmark's outdoor spot is walkable
    assert not church.nopass(99, 112)


# --- paths ---------------------------------------------------------------------------------------


@dataclass
class Ascii:
    """A grid drawn top row = highest y (RO's y grows north). '#' wall, '.' floor."""

    rows: list[str]

    def __post_init__(self) -> None:
        self.ys, self.xs = len(self.rows), len(self.rows[0])

    def nopass(self, x: int, y: int) -> bool:
        if x < 0 or x >= self.xs - 1 or y < 0 or y >= self.ys - 1:
            return True
        return self.rows[self.ys - 1 - y][x] == "#"


OPEN = Ascii(["." * 12] * 12)


def test_open_ground_is_the_shortest_octile_path() -> None:
    path = walk_path(OPEN, 1, 1, 6, 3)
    assert path is not None and path[-1] == (6, 3)
    assert len(path) == 5  # 2 diagonal + 3 straight
    steps = list(zip([(1, 1), *path], path, strict=False))
    assert all(max(abs(b[0] - a[0]), abs(b[1] - a[1])) == 1 for a, b in steps)


def test_walls_force_a_detour_and_corners_are_never_cut() -> None:
    grid = Ascii(
        [
            "..........",
            "..........",
            "....#.....",
            "....#.....",
            "....#.....",
            "..........",
            "..........",
            "..........",
        ]
    )
    path = walk_path(grid, 2, 4, 7, 4)
    assert path is not None and path[-1] == (7, 4)
    assert all(not grid.nopass(x, y) for x, y in path)
    full = [(2, 4), *path]
    for (ax, ay), (bx, by) in zip(full, full[1:], strict=False):
        if ax != bx and ay != by:  # a diagonal step needs both orthogonal neighbours free
            assert not grid.nopass(bx, ay) and not grid.nopass(ax, by)


def test_unreachable_and_bad_targets() -> None:
    boxed = Ascii(["......", ".###..", ".#.#..", ".###..", "......", "......"])
    assert walk_path(boxed, 0, 0, 2, 3) is None  # inside a closed box
    assert walk_path(OPEN, 1, 1, 11, 1) is None  # the last column is never passable
    assert walk_path(OPEN, 1, 1, 1, 1) == []  # already there


def test_easy_path_is_diagonal_then_straight_and_stops_at_obstacles() -> None:
    assert straight_path(OPEN, 1, 1, 4, 2) == [(2, 2), (3, 2), (4, 2)]
    wall = Ascii(["......", "......", "......", "..#...", "......", "......"])
    assert straight_path(wall, 1, 1, 4, 4) is None  # (2,2) is the wall


def path_cost(start: tuple[int, int], path: list[tuple[int, int]]) -> int:
    full = [start, *path]
    return sum(14 if (a[0] != b[0] and a[1] != b[1]) else 10
               for a, b in zip(full, full[1:], strict=False))  # fmt: skip


def test_the_walk_is_a_shortest_one_around_a_wall() -> None:
    """A shortest walk: its cost equals a brute-force breadth-first optimum on the same grid."""
    grid = Ascii(["..........", "..######..", "..#.......", "..#.####..", "..#....#..",
                  "..#####...", "..........", ".........."])  # fmt: skip
    path = walk_path(grid, 3, 3, 8, 1)
    assert path is not None and path[-1] == (8, 1)
    # Dijkstra by hand: the optimum cost
    import heapq

    best = {(3, 3): 0}
    todo = [(0, (3, 3))]
    while todo:
        c, (x, y) = heapq.heappop(todo)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                nx, ny = x + dx, y + dy
                if (
                    (dx or dy)
                    and not grid.nopass(nx, ny)
                    and not (dx and dy and (grid.nopass(x + dx, y) or grid.nopass(x, y + dy)))
                ):
                    nc = c + (14 if dx and dy else 10)
                    if nc < best.get((nx, ny), 1 << 30):
                        best[(nx, ny)] = nc
                        heapq.heappush(todo, (nc, (nx, ny)))
    assert path_cost((3, 3), path) == best[(8, 1)]


def test_the_walk_is_deterministic_and_bounded() -> None:
    assert walk_path(OPEN, 1, 1, 9, 6) == walk_path(OPEN, 1, 1, 9, 6)
    assert octile(5, 2) == 2 * 14 + 3 * 10
    wide = Ascii(["." * 40] * 3)
    assert walk_path(wide, 0, 0, MAX_LEN, 0) is not None
    assert walk_path(wide, 0, 0, MAX_LEN + 1, 0) is None  # beyond the server's path buffer
    # a detour that would need more than max_len steps does not exist either
    assert walk_path(OPEN, 1, 1, 9, 1, max_len=7) is None
    assert walk_path(OPEN, 1, 1, 9, 1, max_len=8) is not None


@dataclass
class Corridor:
    """Only `cells` are walkable."""

    cells: frozenset[tuple[int, int]]
    xs: int = 8
    ys: int = 40

    def nopass(self, x: int, y: int) -> bool:
        return (x, y) not in self.cells


def u_corridor(top: int, goal_y: int) -> Corridor:
    """A one-cell-wide U: up x=1 from y=1 to `top`, across to x=3, down x=3 to `goal_y`."""
    left = {(1, y) for y in range(1, top + 1)}
    right = {(3, y) for y in range(goal_y, top + 1)}
    return Corridor(frozenset(left | right | {(2, top)}))


def test_the_path_limit_is_the_servers_32_step_buffer() -> None:
    """rAthena e985006 path.hpp:14 MAX_WALKPATH 32; path.cpp:415 refuses a longer path. The goal
    is 2 cells away, but the only way there is round the U (no corner cutting)."""
    assert MAX_LEN == 32
    exact = walk_path(u_corridor(16, 1), 1, 1, 3, 1)  # 15 up, 2 across, 15 down
    assert exact is not None and len(exact) == 32 and exact[-1] == (3, 1)
    assert walk_path(u_corridor(16, 0), 1, 1, 3, 0) is None  # its only path is 33 steps
    longer = walk_path(u_corridor(16, 0), 1, 1, 3, 0, max_len=33)
    assert longer is not None and len(longer) == 33


def test_the_optional_altitude_cost_prefers_flat_ground() -> None:
    hill = {(x, 2) for x in range(3, 7)}

    def alt(x: int, y: int) -> float:
        return 20.0 if (x, y) in hill else 0.0

    flat = walk_path(OPEN, 1, 2, 8, 2)
    assert flat is not None and any(c in hill for c in flat)  # the server ignores height
    around = walk_path(OPEN, 1, 2, 8, 2, altitude=alt, climb=5.0)
    assert around is not None and not any(c in hill for c in around)
