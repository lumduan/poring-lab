"""poring_dataset.walk.click_walk_ok / line_clear: the server's one-click walk (dungeon@9.12)."""

from dataclasses import dataclass

from poring_dataset.walk import MAX_CLICK_WALK, MAX_DETOUR_WALK, click_walk_ok, line_clear


@dataclass
class G:
    rows: list[str]  # '#' = not passable

    @property
    def xs(self) -> int:
        return len(self.rows[0])

    @property
    def ys(self) -> int:
        return len(self.rows)

    def nopass(self, x: int, y: int) -> bool:
        if not (0 <= x < self.xs and 0 <= y < self.ys):
            return True
        return self.rows[y][x] == "#"


def test_constants() -> None:
    assert (MAX_CLICK_WALK, MAX_DETOUR_WALK) == (17, 14)


def test_line_clear_open_and_blocked() -> None:
    g = G(["....", "....", "...."])
    assert line_clear(g, 0, 0, 3, 2)
    wall = G(["..#.", "..#.", "...."])
    assert not line_clear(wall, 0, 0, 3, 0)
    assert line_clear(wall, 0, 2, 3, 2)  # the bottom row passes under the wall


def test_short_straight_walk_ok() -> None:
    g = G(["." * 20] * 3)
    assert click_walk_ok(g, 0, 1, 10, 1)
    assert click_walk_ok(g, 0, 1, 17, 1)  # 17 steps, a clear line
    assert not click_walk_ok(g, 0, 1, 18, 1)  # 18 > max_walk


def test_no_path_refused() -> None:
    g = G(["..#..", "..#..", "..#.."])
    assert not click_walk_ok(g, 0, 1, 4, 1)


def test_detour_over_14_refused_when_the_line_is_blocked() -> None:
    # a wall at x=5 from y=0..6 with the gap at y=7: from (3,0) to (7,0) the walk goes down and
    # back up -- 7 + 7 + ... steps, over 14 with the line blocked
    rows = ["....." + "#" + "....." for _ in range(7)] + ["..........."]
    g = G(rows)
    assert not line_clear(g, 3, 0, 7, 0)
    assert not click_walk_ok(g, 3, 0, 7, 0)
    # allowed when the detour limit is raised: the rule, not the search, refused it
    assert click_walk_ok(g, 3, 0, 7, 0, max_detour=17)


def test_short_detour_ok() -> None:
    rows = ["....#....", "....#....", "........."]
    g = G(rows)
    assert not line_clear(g, 2, 0, 6, 0)
    assert click_walk_ok(g, 2, 0, 6, 0)  # 6 steps around the wall's end
