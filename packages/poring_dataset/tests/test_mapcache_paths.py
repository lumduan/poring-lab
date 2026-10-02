"""poring_dataset.mapcache + paths: rAthena's walkability and walk paths (docs/phase2-plan.md)."""

import struct
import zlib
from dataclasses import dataclass

import pytest

from poring_dataset import mapcache
from poring_dataset.paths import path_search


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
    path = path_search(OPEN, 1, 1, 6, 3)
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
    path = path_search(grid, 2, 4, 7, 4)
    assert path is not None and path[-1] == (7, 4)
    assert all(not grid.nopass(x, y) for x, y in path)
    full = [(2, 4), *path]
    for (ax, ay), (bx, by) in zip(full, full[1:], strict=False):
        if ax != bx and ay != by:  # a diagonal step needs both orthogonal neighbours free
            assert not grid.nopass(bx, ay) and not grid.nopass(ax, by)


def test_unreachable_and_bad_targets() -> None:
    boxed = Ascii(["......", ".###..", ".#.#..", ".###..", "......", "......"])
    assert path_search(boxed, 0, 0, 2, 3) is None  # inside a closed box
    assert path_search(OPEN, 1, 1, 11, 1) is None  # the last column is never passable
    assert path_search(OPEN, 1, 1, 1, 1) == []  # already there


def test_easy_path_is_diagonal_then_straight_and_stops_at_obstacles() -> None:
    assert path_search(OPEN, 1, 1, 4, 2, easy=True) == [(2, 2), (3, 2), (4, 2)]
    wall = Ascii(["......", "......", "......", "..#...", "......", "......"])
    assert path_search(wall, 1, 1, 4, 4, easy=True) is None  # (2,2) is the wall
