"""picking.py: the cell under a pixel = the first GAT TOP surface the camera ray comes down
through, on SYNTHETIC data only (a real GAT is client data, CLAUDE.md rule 4)."""

import numpy as np

from poring_dataset import gat as gatmod
from poring_dataset.camera import Camera
from poring_dataset.picking import pick_cells, safe_points

# the lab's indoor rig: the camera to the south-west, a 15 degree FOV, cells 5 units
INDOOR = Camera(np.radians(46), np.radians(44.8), 273.0, np.radians(15), 640.0, 362.0)
ORIGIN = (20, 20)


def gat(raised: set[tuple[int, int]] = frozenset(), size: int = 40) -> gatmod.Gat:  # type: ignore[assignment]
    tiles = np.zeros((size, size), gatmod.TILE)
    for x, y in raised:
        for corner in ("sw", "se", "nw", "ne"):
            tiles[y, x][corner] = -5.0  # one cell up (GAT heights are negative-up)
    return gatmod.Gat(size, size, "1.2", tiles)


def project(g: gatmod.Gat, rel: tuple[float, float]) -> np.ndarray:
    c = np.array([rel], dtype=float)
    return INDOOR.project(c, g.relative_altitude(ORIGIN, c))[0]


def test_on_flat_ground_the_projected_centre_picks_its_own_cell() -> None:
    g = gat()
    rels = [(dx, dy) for dx in range(-4, 5) for dy in range(-4, 5)]
    px = np.array([project(g, r) for r in rels])
    assert [tuple(c) for c in pick_cells(INDOOR, g, ORIGIN, px)] == rels


def test_a_raised_block_covers_the_floor_just_behind_it() -> None:
    """The prt_church kneeler case: the centre of the cell behind a one-cell-high block (on the
    side away from the camera) picks the BLOCK -- the server walked there 25 times."""
    row = {(x, 22) for x in range(14, 27)}  # a kneeler row two cells north of us
    g = gat(row)
    behind = (0, 3)
    got = tuple(pick_cells(INDOOR, g, ORIGIN, project(g, behind)[None])[0])
    assert got != behind and got[1] == 2  # the raised row, not the floor behind it


def test_a_side_wall_is_not_picked() -> None:
    """A ray that enters a raised block through its side passes through to the floor behind:
    counting walls mispredicted 18 logged clicks."""
    g = gat({(23, 20)})  # one raised cell east of us
    # the middle of the block's SOUTH face (the camera, south-west, sees it): half-way up
    side = INDOOR.project(np.array([[3.0, -0.5]]), np.array([2.5]))[0]
    assert tuple(pick_cells(INDOOR, g, ORIGIN, side[None])[0]) != (3, 0)
    # ... while a pixel on its top picks it
    assert tuple(pick_cells(INDOOR, g, ORIGIN, project(g, (3, 0))[None])[0]) == (3, 0)


def ring_ok(g: gatmod.Gat, target: tuple[int, int], u: float, v: float, m: float) -> bool:
    ring = [(m * np.cos(a), m * np.sin(a)) for a in np.linspace(0, 2 * np.pi, 16, endpoint=False)]
    around = np.array([(u + a, v + b) for a, b in ring] + [(u, v)])
    return all(tuple(c) == target for c in pick_cells(INDOOR, g, ORIGIN, around))


def test_safe_points_keep_their_margin_and_only_the_strip_behind_a_row_is_left() -> None:
    """Behind a CONTINUOUS kneeler row only a thin strip of the cell stays on screen: no 6 px
    (tier A) point, but 3 px (tier B) points; an open cell has tier-A points; a cell nothing picks
    has none at all."""
    row = {(x, 22) for x in range(14, 27)}
    g = gat(row)
    behind = (0, 3)
    assert safe_points(INDOOR, g, ORIGIN, behind, margin=6.0) == []
    strip = safe_points(INDOOR, g, ORIGIN, behind, margin=3.0, grid=1.0)
    assert strip and all(ring_ok(g, behind, u, v, 3.0) for u, v in strip)
    centre = project(g, behind)
    assert all(np.hypot(u - centre[0], v - centre[1]) > 1 for u, v in strip)  # its top covers it
    open_cell = (0, 5)
    pts = safe_points(INDOOR, g, ORIGIN, open_cell, margin=6.0)
    assert pts and all(ring_ok(g, open_cell, u, v, 6.0) for u, v in pts)
    assert all(np.hypot(a[0] - b[0], a[1] - b[1]) >= 8 for a in pts for b in pts if a != b)
    # a cell no pixel picks (beyond the map's edge: no tile to come down on) has no point at all
    assert safe_points(INDOOR, g, ORIGIN, (0, 20), margin=3.0, grid=1.0) == []
