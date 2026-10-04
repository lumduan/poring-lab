"""The perspective camera (camera.py) and the GAT reader (gat.py) on SYNTHETIC data only: a real
GAT is client data and never enters the repository (CLAUDE.md rule 4)."""

import json
import struct
from pathlib import Path

import numpy as np
import pytest

from poring_dataset import gat as gatmod
from poring_dataset.camera import Camera, fit_camera, projector_for

NONE: frozenset[str] = frozenset()  # no indoor maps (the indoor rule: test_indoor_facing.py)


def synthetic_gat(width: int, height: int, alt: np.ndarray, types: np.ndarray) -> bytes:
    """A GAT 1.2 with every corner at -alt (RO's negative-up axis)."""
    head = struct.pack("<4sBBII", b"GRAT", 1, 2, width, height)
    tiles = np.zeros(width * height, gatmod.TILE)
    for corner in ("sw", "se", "nw", "ne"):
        tiles[corner] = -alt.ravel()
    tiles["type"] = types.ravel()
    return head + tiles.tobytes()


TRUE = Camera(np.radians(3), np.radians(45), 400.0, np.radians(15), 641.0, 362.0)
CELLS = np.array([(dx, dy) for dx in range(-12, 13, 3) for dy in range(-6, 9, 2)], float)


def test_the_default_rig_puts_north_up_and_east_right() -> None:
    cam = Camera(0.0, np.radians(45), 400.0, np.radians(15), 640.0, 360.0)
    (u0, v0), (ue, _), (_, vn) = cam.project(np.array([[0, 0], [3, 0], [0, 3]], float))
    assert (round(u0), round(v0)) == (640, 360)  # the player's feet at the target
    assert ue > u0 and vn < v0  # east -> right, north -> up the screen
    ((_, v_hill),) = cam.project(np.array([[0.0, 0.0]]), np.array([10.0]))
    assert v_hill < v0  # higher ground is drawn higher


def test_the_fit_recovers_the_camera_and_altitude_matters() -> None:
    rng = np.random.default_rng(7)
    alt = rng.uniform(-2, 9, len(CELLS))
    px = TRUE.project(CELLS, alt) + rng.normal(0, 0.3, (len(CELLS), 2))
    fit = fit_camera(CELLS, px, altitude=alt)
    assert fit.median_px < 1.0
    assert abs(np.degrees(fit.camera.pitch) - 45) < 0.5 and abs(fit.camera.distance - 400) < 10
    flat = fit_camera(CELLS, px)  # the same points, terrain ignored
    assert flat.p95_px > 4 * fit.p95_px


def test_a_gat_parses_and_reports_altitude_up_positive() -> None:
    alt = np.arange(12, dtype=float).reshape(3, 4)  # rises to the east and north
    types = np.zeros((3, 4), np.uint16)
    types[1, 2] = 1  # a wall
    grid = gatmod.parse(synthetic_gat(4, 3, alt, types))
    assert (grid.width, grid.height, grid.version) == (4, 3, "1.2")
    assert grid.altitude_at(3, 2) == 11.0 and grid.walkable()[1, 2] == np.False_
    rel = grid.relative_altitude((1, 1), np.array([[1.0, 0.0], [0.5, 0.5]]))
    assert rel[0] == pytest.approx(1.0) and rel[1] == pytest.approx(2.5)  # bilinear between


def test_the_walk_graph_follows_the_diagonal_rule() -> None:
    types = np.zeros((2, 2), np.uint16)
    types[0, 1] = 1  # (1, 0) is a wall: (0, 0) -> (1, 1) diagonally is cut
    grid = gatmod.parse(synthetic_gat(2, 2, np.zeros((2, 2)), types))
    g = gatmod.walk_graph(grid)
    edges = set(zip(g["src"].tolist(), g["dst"].tolist(), strict=True))
    assert (0, 3) not in edges and (0, 2) in edges and (2, 3) in edges
    assert set(g["cost"].tolist()) == {10}


@pytest.mark.parametrize(
    "data",
    [b"GRAX\x01\x02" + bytes(8), struct.pack("<4sBBII", b"GRAT", 1, 9, 1, 1) + bytes(20),
     struct.pack("<4sBBII", b"GRAT", 1, 2, 2, 2) + bytes(20), b"GR"],
)  # fmt: skip
def test_a_bad_gat_is_refused(data: bytes) -> None:
    with pytest.raises(gatmod.GatError):
        gatmod.parse(data)


def test_the_projector_uses_camera_and_gat_only_when_both_exist(tmp_path: Path) -> None:
    h = [[30.0, 0, 640.0], [0, -30.0, 360.0], [0, 0, 1.0]]
    block = {"yaw": 0.0, "pitch": float(np.radians(45)), "distance": 400.0,
             "fov": float(np.radians(15)), "cx": 640.0, "cy": 360.0, "height": 720}  # fmt: skip
    _, which = projector_for({"h": h}, "map_a", tmp_path, indoor_table=NONE)
    assert which == "homography"
    _, which = projector_for({"h": h, "camera": block}, "map_a", tmp_path, indoor_table=NONE)
    assert which == "homography"  # no GAT at hand: the flat fallback
    alt = np.zeros((20, 20))
    alt[10, 12] = 8.0
    (tmp_path / "map_a.gat").write_bytes(synthetic_gat(20, 20, alt, np.zeros((20, 20), np.uint16)))
    proj, which = projector_for(json.loads(json.dumps({"h": h, "camera": block})), "map_a",
                                tmp_path, indoor_table=NONE)  # fmt: skip
    assert which == "camera+gat:map_a"
    _, which = projector_for({"h": h, "camera": block}, "map_a.gat", tmp_path, indoor_table=NONE)
    assert which == "camera+gat:map_a"  # the packets name maps with their .gat suffix
    flat, hill = proj(np.array([[1.0, 0.0], [2.0, 0.0]]), (10, 10))
    assert hill[1] < flat[1]  # the raised cell is drawn higher
