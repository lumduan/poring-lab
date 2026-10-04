"""predict_sprite, the billboard render rule (render.py), on SYNTHETIC sprites built here and the
committed camera fit (camera_console.json): real sprites and GATs are client data and never enter
the repository (CLAUDE.md rule 4)."""

import math
import struct
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from poring_dataset import camera as cm
from poring_dataset import gat as gatmod
from poring_dataset import render as rd
from poring_dataset.sprites import Act, Layer, MissingImageSize, Motion, Spr

CAMERA_JSON = cm.load_camera_json(Path(cm.__file__).parent / "camera_console.json")
NONE: frozenset[str] = frozenset()
INDOOR = frozenset({"prt_church"})
MOTIONS = (4, 6, 5, 3, 7)  # frames per group: idle, walk, attack, hurt, die
DELAYS = (4.0, 4.0, 1.0, 2.0, 1.0)  # 24 ms units per group
PLAYER = (100.0, 100.0)


def cameras() -> tuple[cm.Camera, cm.Camera]:
    out = cm.map_camera(CAMERA_JSON, "prt_fild08", INDOOR)
    ind = cm.map_camera(CAMERA_JSON, "prt_church", INDOOR)
    assert out is not None and ind is not None
    return out, ind


def quad(y: int, w: int, h: int, index: int = 0) -> Layer:
    return Layer(0, y, index, False, (255, 255, 255, 255), 1.0, 1.0, 0, 0, w, h)


def synthetic_act() -> Act:
    """5 groups x 8 directions. A frame's quad stands on the anchor; its WIDTH names the direction
    (10 + 2 * direction) and its HEIGHT the motion (20 + 4 * motion)."""
    actions = []
    for n in MOTIONS:
        for d in range(8):
            actions.append(tuple(Motion((quad(-(10 + 2 * m), 10 + 2 * d, 20 + 4 * m),))
                                 for m in range(n)))  # fmt: skip
    delays = tuple(DELAYS[g] for g in range(5) for _ in range(8))
    return Act((2, 5), tuple(actions), (), delays)


SHEET = rd.SpriteSheet(synthetic_act())


def predict(
    cam: cm.Camera, cell: tuple[float, float], heading: int = 4, **kw: Any
) -> rd.SpritePrediction:
    actor = rd.Actor(cell, heading, **kw)
    pred = rd.predict_sprite(actor, SHEET, rd.Scene(cam, PLAYER))
    assert pred is not None
    return pred


def test_the_scale_is_f_over_z_times_k() -> None:
    out, _ = cameras()
    f = (720 / 2) / math.tan(out.fov / 2)
    assert rd.focal_px(out) == pytest.approx(f) and f == pytest.approx(2734.47, abs=0.01)
    actor = rd.Actor(PLAYER, 4, elapsed_ms=0.0)
    for k in (rd.K_NOSTALRO, rd.K_KORANGAR):
        pred = rd.predict_sprite(actor, SHEET, rd.Scene(out, PLAYER), k)
        assert pred is not None
        assert pred.depth == pytest.approx(out.distance)  # the player's cell is the camera target
        assert pred.scale == pytest.approx(f / out.distance * k)
        assert pred.anchor_px == pytest.approx((out.cx, out.cy))
        x0, y0, x1, y1 = pred.box
        assert x1 - x0 == pytest.approx(pred.scale * (10 + 2 * pred.direction))
        assert (y1, y1 - y0) == pytest.approx((out.cy, pred.scale * 20))  # stands on the anchor
    kor = rd.predict_sprite(actor, SHEET, rd.Scene(out, PLAYER), rd.K_KORANGAR)
    nos = rd.predict_sprite(actor, SHEET, rd.Scene(out, PLAYER), rd.K_NOSTALRO)
    assert kor is not None and nos is not None
    assert kor.scale / nos.scale == pytest.approx(1.05)  # the 5 % the clients disagree on


def test_bottom_of_the_screen_draws_larger_than_the_top() -> None:
    out, _ = cameras()
    top = predict(out, (PLAYER[0], PLAYER[1] + 10))  # north: up the screen, farther
    bottom = predict(out, (PLAYER[0], PLAYER[1] - 10))  # south: down the screen, closer
    assert bottom.anchor_px[1] > out.cy > top.anchor_px[1]
    assert bottom.scale > top.scale and bottom.depth < top.depth
    assert bottom.scale / top.scale == pytest.approx(top.depth / bottom.depth)


def test_the_plans_pixels_per_world_unit_at_the_screen_edges() -> None:
    """docs/phase3-plan.md §2: outdoor 5.93 (top) / 6.83 (centre) / 7.73 (bottom) px per world
    unit; the exact rule at v = 0 and v = 720 lands within 0.5 % of them."""
    out, _ = cameras()

    def ppu_at(v_target: float, lo: float, hi: float) -> float:
        for _ in range(60):  # bisection on the row (north is up)
            mid = (lo + hi) / 2
            (_, v), _z = rd.anchor_and_depth(rd.Scene(out, PLAYER), (PLAYER[0], PLAYER[1] + mid))
            lo, hi = (mid, hi) if v > v_target else (lo, mid)
        _, z = rd.anchor_and_depth(rd.Scene(out, PLAYER), (PLAYER[0], PLAYER[1] + lo))
        return rd.focal_px(out) / z

    assert ppu_at(0.0, -40, 40) == pytest.approx(5.93, rel=0.005)
    assert rd.focal_px(out) / out.distance == pytest.approx(6.83, rel=0.005)
    assert ppu_at(720.0, -40, 40) == pytest.approx(7.73, rel=0.005)


def test_indoor_draws_1466x_larger_at_the_centre() -> None:
    out, ind = cameras()
    assert ind.distance == 273.0
    ratio = predict(ind, PLAYER).scale / predict(out, PLAYER).scale
    assert ratio == pytest.approx(out.distance / 273.0) and ratio == pytest.approx(1.466, abs=1e-3)


@pytest.mark.parametrize("heading", range(8))
def test_the_indoor_yaw_turns_the_sprite_direction(heading: int) -> None:
    out, ind = cameras()
    po, pi = predict(out, PLAYER, heading), predict(ind, PLAYER, heading)
    assert po.direction == (4 - heading) % 8  # outdoor: camera_dir 0 (looks north)
    assert pi.direction == (po.direction - 1) % 8  # +45 deg: camera_dir 7
    assert pi.action_index == pi.direction  # idle group 0
    width = (pi.box[2] - pi.box[0]) / pi.scale
    assert width == pytest.approx(10 + 2 * pi.direction)  # the frame drawn is that direction's


def test_the_envelope_holds_every_frame_of_the_action() -> None:
    out, _ = cameras()
    cell = (PLAYER[0] + 3.5, PLAYER[1] - 2.25)
    for group, n in enumerate(MOTIONS):
        env = predict(out, cell, 2, action=group)
        assert not env.phase_known and env.motion is None
        frames = []
        for m in range(n):
            if group == rd.MonsterAction.WALK:
                p = predict(out, cell, 2, action=group, walked_cells=(m + 0.5) * 4 / 7.4)
            else:
                p = predict(out, cell, 2, action=group, elapsed_ms=(m + 0.5) * DELAYS[group] * 24)
            assert p.phase_known and p.motion == m
            assert env.box[0] <= p.box[0] and env.box[1] <= p.box[1]
            assert env.box[2] >= p.box[2] and env.box[3] >= p.box[3]
            frames.append(p.box)
        union = (min(b[0] for b in frames), min(b[1] for b in frames),
                 max(b[2] for b in frames), max(b[3] for b in frames))  # fmt: skip
        assert env.box == pytest.approx(union)  # and nothing more


def test_frame_timing_follows_the_act_delays() -> None:
    act = SHEET.act
    at = rd.motion_at
    idle, walk, attack, hurt, die = (act.action_index(g, 0) for g in range(5))
    a = rd.MonsterAction
    # idle: a 96 ms loop frame (4 units x 24 ms), 4 frames
    assert [at(act, idle, rd.Actor(PLAYER, 0, a.IDLE, elapsed_ms=t)) for t in (0, 95.9, 96, 384)] \
        == [0, 0, 1, 0]  # fmt: skip
    # walk: by DISTANCE, one frame per 4 / 7.4 = 0.54 cells, 6 frames
    walked = (0.0, 0.54, 0.55, 6 * 4 / 7.4 + 0.01)
    assert [at(act, walk, rd.Actor(PLAYER, 0, a.WALK, walked_cells=w)) for w in walked] \
        == [0, 0, 1, 0]  # fmt: skip
    assert at(act, walk, rd.Actor(PLAYER, 0, a.WALK, elapsed_ms=500.0)) is None  # time alone: no
    # attack: once, at the packet's duration when given (500 ms / 5 frames), then held
    hold = [at(act, attack, rd.Actor(PLAYER, 0, a.ATTACK, elapsed_ms=t, duration_ms=500.0))
            for t in (0, 250, 499, 10_000)]  # fmt: skip
    assert hold == [0, 2, 4, 4]
    assert at(act, attack, rd.Actor(PLAYER, 0, a.ATTACK, elapsed_ms=50.0)) == 2  # 24 ms native
    # hurt and die: once at their delay, then the last frame stays
    assert at(act, hurt, rd.Actor(PLAYER, 0, a.HURT, elapsed_ms=100.0)) == 2
    assert at(act, die, rd.Actor(PLAYER, 0, a.DIE, elapsed_ms=60_000.0)) == 6
    assert at(act, idle, rd.Actor(PLAYER, 0, a.IDLE)) is None
    with pytest.raises(ValueError):
        at(act, idle, rd.Actor(PLAYER, 0, a.IDLE, elapsed_ms=-1.0))


def synthetic_gat(width: int, height: int, alt: np.ndarray) -> bytes:
    head = struct.pack("<4sBBII", b"GRAT", 1, 2, width, height)
    tiles = np.zeros(width * height, gatmod.TILE)
    for corner in ("sw", "se", "nw", "ne"):
        tiles[corner] = -alt.ravel()  # RO's negative-up axis
    return head + tiles.tobytes()


def test_the_anchor_is_the_phase2_projector_with_gat_altitude(tmp_path: Path) -> None:
    alt = np.zeros((40, 40))
    alt[22, 25] = 9.0
    alt[18:21, 10:14] = -4.0
    (tmp_path / "map_a.gat").write_bytes(synthetic_gat(40, 40, alt))
    proj, which = cm.projector_for(CAMERA_JSON, "map_a", tmp_path, indoor_table=NONE)
    assert which == "camera+gat:map_a"
    origin = (20, 20)
    scene = rd.load_scene(CAMERA_JSON, "map_a.gat", origin, tmp_path, indoor_table=NONE)
    assert scene.gat is not None
    for cell in ((25.0, 22.0), (11.0, 19.0), (23.4, 21.7), (20.0, 20.0)):
        offsets = np.array([[cell[0] - origin[0], cell[1] - origin[1]]])
        anchor, _z = rd.anchor_and_depth(scene, cell)
        np.testing.assert_allclose(anchor, proj(offsets, origin)[0], atol=1e-9)
    flat = rd.Scene(scene.camera, (20.0, 20.0))
    assert (  # the raised cell's sprite stands higher than on flat ground
        rd.anchor_and_depth(scene, (25.0, 22.0))[0][1]
        < rd.anchor_and_depth(flat, (25.0, 22.0))[0][1]
    )
    # a walking player: the altitude is relative to where the camera looks, not to its cell
    moving = rd.Scene(scene.camera, (24.5, 22.0), scene.gat)
    (_, v_mid), _ = rd.anchor_and_depth(moving, (24.5, 22.0))
    assert v_mid == pytest.approx(scene.camera.cy)


def test_indoor_maps_load_the_rotated_closer_camera(tmp_path: Path) -> None:
    scene = rd.load_scene(CAMERA_JSON, "prt_church", PLAYER, tmp_path, indoor_table=INDOOR)
    assert scene.gat is None and scene.camera.distance == 273.0
    assert math.degrees(scene.camera.yaw) == pytest.approx(math.degrees(cameras()[0].yaw) + 45.96)


def test_an_anchor_behind_the_camera_is_not_drawn() -> None:
    out, _ = cameras()
    actor = rd.Actor((PLAYER[0], PLAYER[1] - 130), 0, elapsed_ms=0.0)
    assert rd.predict_sprite(actor, SHEET, rd.Scene(out, PLAYER)) is None


def test_with_the_spr_the_box_and_mask_are_the_opaque_pixels() -> None:
    img = np.zeros((20, 10, 4), np.uint8)
    img[4:20, 2:8] = 255  # a 6 x 16 opaque body in a 10 x 20 image
    layer = Layer(0, -10, 0, False, (255, 255, 255, 255), 1.0, 1.0, 0, 0, None, None)
    act = Act((2, 5), tuple((Motion((layer,)),) for _ in range(40)), (), (4.0,) * 40)
    sheet = rd.SpriteSheet(act, Spr((2, 1), (img,), 1, None))
    out, _ = cameras()
    pred = rd.predict_sprite(rd.Actor(PLAYER, 0, elapsed_ms=0.0), sheet, rd.Scene(out, PLAYER),
                             with_mask=True)  # fmt: skip
    assert pred is not None and pred.box_kind == "opaque" and rd.SpriteSheet(act).box_kind == "quad"
    s = pred.scale
    assert pred.box == pytest.approx((out.cx - 3 * s, out.cy - 16 * s, out.cx + 3 * s, out.cy))
    assert pred.mask is not None and pred.mask_origin is not None
    i0, j0 = pred.mask_origin
    assert pred.mask.shape == (math.ceil(pred.box[3]) - j0, math.ceil(pred.box[2]) - i0)
    assert pred.mask.sum() == pytest.approx(6 * 16 * s * s, rel=0.15)
    ys, xs = np.nonzero(pred.mask)
    assert xs.min() + i0 >= math.floor(pred.box[0]) and xs.max() + i0 < math.ceil(pred.box[2])
    assert ys.min() + j0 >= math.floor(pred.box[1]) and ys.max() + j0 < math.ceil(pred.box[3])
    with pytest.raises(ValueError, match="SPR"):
        rd.SpriteSheet(act).alpha(0, 0)  # no pixels, no mask


def test_without_spr_or_act_sizes_the_box_is_refused_not_guessed() -> None:
    layer = Layer(0, -10, 0, False, (255, 255, 255, 255), 1.0, 1.0, 0, 0, None, None)
    act = Act((2, 4), tuple((Motion((layer,)),) for _ in range(40)))
    out, _ = cameras()
    with pytest.raises(MissingImageSize):
        rd.predict_sprite(rd.Actor(PLAYER, 0, elapsed_ms=0.0), rd.SpriteSheet(act),
                          rd.Scene(out, PLAYER))  # fmt: skip
