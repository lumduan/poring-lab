"""The indoor camera rule, movement under rotation, billboard facing and the hidden-NPC filter
(Post-S2 round B1/B3/B4/B5, 2026-10-04)."""

from pathlib import Path

import numpy as np
import pytest

from poring_dataset import camera as cm
from poring_dataset import labels as lb
from poring_dataset.timeline import EntityState, FrameWorld, Timeline, tick_of
from poring_packets.world import heading_of

FIT = cm.Camera(0.0, np.radians(45), 400.0, np.radians(15), 640.0, 360.0)
CAMERA_JSON = {
    "h": [[30.0, 0, 640.0], [0, -30.0, 360.0], [0, 0, 1.0]],
    "camera": {"yaw": 0.0, "pitch": float(np.radians(45)), "distance": 400.0,
               "fov": float(np.radians(15)), "cx": 640.0, "cy": 360.0, "height": 720},
}  # fmt: skip
# the shape of the client's table: CRLF, comments, a trailing '#', mixed case
TABLE_TEXT = "// indoor maps\r\nprt_church.rsw#\r\n\r\nPRT_IN.rsw#  // inns\r\n"


def test_the_indoor_table_parses_the_clients_format() -> None:
    table = cm.parse_indoor_table(TABLE_TEXT)
    assert table == frozenset({"prt_church", "prt_in"})
    assert cm.is_indoor("prt_church.gat", table) and cm.is_indoor("PRT_IN", table)
    assert not cm.is_indoor("prt_fild08", table) and not cm.is_indoor(None, table)


def test_a_missing_indoor_table_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(cm.IndoorTableMissing):
        cm.load_indoor_table(tmp_path)
    with pytest.raises(cm.IndoorTableMissing):  # the projector refuses rather than guess outdoor
        cm.projector_for(CAMERA_JSON, "prt_church", tmp_path)
    (tmp_path / cm.INDOOR_TABLE).write_bytes(TABLE_TEXT.encode("latin-1"))
    assert "prt_church" in cm.load_indoor_table(tmp_path)


def test_indoor_maps_rotate_the_fitted_camera_and_nothing_else() -> None:
    indoor = cm.camera_for_map(FIT, True)
    assert np.isclose(np.degrees(indoor.yaw), cm.INDOOR_YAW_DEG)
    assert (indoor.pitch, indoor.distance, indoor.fov, indoor.cx, indoor.cy) == (
        FIT.pitch, FIT.distance, FIT.fov, FIT.cx, FIT.cy)  # fmt: skip
    assert cm.camera_for_map(FIT, False) is FIT
    measured = CAMERA_JSON | {"indoor": {"yaw_deg": 45.0}}  # B2 records the measured sign
    assert cm.indoor_yaw_deg(measured) == 45.0 and cm.indoor_yaw_deg(CAMERA_JSON) == -45.0


def test_indoor_maps_never_fall_back_to_the_outdoor_homography(tmp_path: Path) -> None:
    table = frozenset({"prt_church"})
    proj, which = cm.projector_for(CAMERA_JSON, "prt_church.gat", tmp_path, indoor_table=table)
    assert which == "camera(flat):indoor prt_church"  # no GAT: the flat ROTATED camera
    rotated = cm.camera_for_map(FIT, True)
    np.testing.assert_allclose(proj(np.array([[3.0, 0.0]]), (0, 0)),
                               rotated.project(np.array([[3.0, 0.0]])))  # fmt: skip
    _, which = cm.projector_for(CAMERA_JSON, "prt_fild08", tmp_path, indoor_table=table)
    assert which == "homography"  # outdoor without a GAT: unchanged
    with pytest.raises(ValueError, match="indoor"):
        cm.projector_for({"h": CAMERA_JSON["h"]}, "prt_church", tmp_path, indoor_table=table)


@pytest.mark.parametrize(
    ("yaw_deg", "north_px_dir"),
    [(0.0, (0.0, -1.0)),  # north is straight up the screen
     (90.0, (-1.0, 0.0)),  # looking east: north points left
     (-90.0, (1.0, 0.0)),  # looking west: north points right
     (45.0, (-1.0, -1.0)), (-45.0, (1.0, -1.0))],  # diagonals: up-left / up-right
)  # fmt: skip
def test_screen_vectors_rotate_with_the_camera(yaw_deg: float, north_px_dir: tuple) -> None:
    cam = cm.Camera(np.radians(yaw_deg), np.radians(45), 400.0, np.radians(15), 640.0, 360.0)
    v = cm.screen_vector(cam, (0.0, 3.0))
    want = np.array(north_px_dir) / np.linalg.norm(north_px_dir)
    got = v / np.linalg.norm(v)
    # the vertical screen axis is foreshortened by the pitch: compare the signs and the quadrant
    assert np.all(np.sign(np.round(got, 6)) == np.sign(want))
    if yaw_deg in (0.0, 90.0, -90.0):
        assert np.allclose(got, want, atol=1e-6)


def test_click_for_cell_goes_through_the_maps_projector() -> None:
    rotated = cm.camera_for_map(FIT, True)

    def proj(offsets: np.ndarray, _origin: tuple[int, int]) -> np.ndarray:
        return rotated.project(offsets)

    u, v = cm.click_for_cell(proj, (2, 3), (100, 100))
    ((pu, pv),) = rotated.project(np.array([[2.0, 3.0]]))
    assert (u, v) == (pytest.approx(pu), pytest.approx(pv))
    # and NOT the yaw-0 grid the driver used to assume
    ((ou, ov),) = FIT.project(np.array([[2.0, 3.0]]))
    assert abs(u - ou) + abs(v - ov) > 20


def test_look_heading_and_the_ported_facing_formula() -> None:
    assert [cm.look_heading(np.radians(d)) for d in (0, 45, 90, 180, -45, -90, 359.75)] == [
        0, 7, 6, 4, 1, 2, 0]  # fmt: skip
    n, s, w, e = 0, 4, 2, 6  # RO headings
    yaw0 = 0.0
    # the default camera looks north: walking north shows the back, walking south the front
    assert cm.displayed_direction(n, yaw0) == cm.SPRITE_DIRECTIONS.index("N")
    assert cm.displayed_direction(s, yaw0) == cm.SPRITE_DIRECTIONS.index("S")
    assert cm.displayed_direction(w, yaw0) == cm.SPRITE_DIRECTIONS.index("W")
    assert cm.displayed_direction(e, yaw0) == cm.SPRITE_DIRECTIONS.index("E")
    east = np.radians(90)  # looking east (the eye on the west side)
    assert cm.displayed_direction(e, east) == cm.SPRITE_DIRECTIONS.index("N")  # walks away
    assert cm.displayed_direction(w, east) == cm.SPRITE_DIRECTIONS.index("S")  # walks towards
    assert cm.displayed_direction(n, east) == cm.SPRITE_DIRECTIONS.index("W")  # north is left
    # 45 degrees: every heading shifts by exactly one sprite direction
    for h in range(8):
        shifted = cm.displayed_direction(h, np.radians(-45))
        assert shifted == (cm.displayed_direction(h, 0.0) + 1) % 8


def test_heading_of_a_step() -> None:
    steps = ((0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 0))
    assert [heading_of(*d) for d in steps] == [0, 1, 2, 3, 4, 5, 6, 7, None]


def _appear(t: int, gid: int, *, x: int, y: int, objtype: int = 5, job: int = 1002,
            heading: int | None = None, x1: int | None = None, y1: int | None = None,
            tick: int | None = None) -> dict:  # fmt: skip
    e = {"t_mono_ns": t, "type": "entity_appear", "kind": "stand" if x1 is None else "move",
         "gid": gid, "char_id": 0, "objtype": objtype, "job": job, "speed": 100, "name": "x",
         "x": x, "y": y, "heading": heading}  # fmt: skip
    if x1 is not None:
        e |= {"x1": x1, "y1": y1, "move_start_tick": tick}
    return e


def test_the_timeline_carries_the_heading_and_the_walk_direction() -> None:
    t0 = 10_000_000_000
    events = [
        {"t_mono_ns": t0 - 1, "type": "char_selected", "map": "prt_fild08"},
        {"t_mono_ns": t0, "type": "map_enter", "x": 50, "y": 50},
        _appear(t0 + 1, 1, x=52, y=50, heading=6),  # standing, facing east
        _appear(t0 + 2, 2, x=40, y=40, x1=40, y1=36, tick=tick_of(t0 + 2)),  # walking south
    ]
    tl = Timeline(events)
    world = tl.frame_world(t0 + 150_000_000)  # 150 ms into the walk (speed 100: step 2)
    by_gid = {e.gid: e for e in world.entities}
    assert by_gid[1].heading == 6 and not by_gid[1].moving
    assert by_gid[2].heading == 4 and by_gid[2].moving
    done = {e.gid: e for e in tl.frame_world(t0 + 2_000_000_000).entities}
    assert done[2].heading == 4 and not done[2].moving  # keeps facing its last step


def test_labels_skip_invisible_npcs_and_carry_the_facing() -> None:
    def ent(gid: int, objtype: int, job: int, heading: int | None) -> EntityState:
        return EntityState(gid, objtype, job, "e", 51.0, 50.0, False, heading)

    frame = FrameWorld(0, "prt_church", None, (50.0, 50.0), (
        ent(1, 6, 111, 0), ent(2, 6, 139, 0), ent(3, 6, 32767, 0), ent(4, 6, 45, 0),  # hidden
        ent(5, 6, 86, 4),  # a real NPC sprite facing south
        ent(6, 5, 111, 2),  # a MONSTER with that number is not an NPC class: kept
        ent(7, 0, 0, None),  # a player with no heading yet
    ))  # fmt: skip

    def proj(offsets: np.ndarray, _origin: tuple[int, int]) -> np.ndarray:
        return FIT.project(offsets)

    out = {b.gid: b for b in lb.labels_for(frame, proj, (1280, 720), camera_yaw=0.0)}
    assert set(out) == {5, 6, 7}
    assert out[5].facing == cm.SPRITE_DIRECTIONS.index("S")
    assert out[6].facing == cm.SPRITE_DIRECTIONS.index("W")
    assert out[7].facing is None
    rotated = {b.gid: b for b in lb.labels_for(frame, proj, (1280, 720),
                                               camera_yaw=np.radians(-45))}  # fmt: skip
    assert rotated[5].facing == cm.SPRITE_DIRECTIONS.index("SW")
    assert all(b.facing is None for b in lb.labels_for(frame, proj, (1280, 720)))
