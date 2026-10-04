"""SPR/ACT parsing and frame composition (sprites.py) on SYNTHETIC bytes built here: real sprites
are client data and never enter the repository (CLAUDE.md rule 4)."""

import struct
from typing import Any

import numpy as np
import pytest

from poring_dataset import sprites as sp

MAGENTA = 7  # the palette entry set to the magenta key below


def palette() -> np.ndarray:
    pal = np.zeros((256, 4), np.uint8)
    pal[:, 0] = np.arange(256)  # R = index, so a pixel's colour names its index
    pal[:, 1] = 255 - np.arange(256)
    pal[:, 2] = 40
    pal[0] = (10, 20, 30, 0)  # index 0 is transparent whatever its colour
    pal[MAGENTA] = (0xFF, 0x00, 0xFF, 0)
    return pal


def rle(indices: np.ndarray) -> bytes:
    """SPR 2.1 encoding: zero runs as 0x00 + count (<= 255), literals as themselves."""
    out, flat, i = bytearray(), indices.ravel().tolist(), 0
    while i < len(flat):
        if flat[i] == 0:
            run = 1
            while i + run < len(flat) and flat[i + run] == 0 and run < 255:
                run += 1
            out += bytes((0, run))
            i += run
        else:
            out.append(flat[i])
            i += 1
    return bytes(out)


def spr_bytes(
    version: tuple[int, int],
    indexed: list[np.ndarray],
    rgba: list[np.ndarray] | None = None,
    pal: np.ndarray | None = None,
) -> bytes:
    major, minor = version
    rgba = rgba or []
    out = bytearray(b"SP" + bytes((minor, major)) + struct.pack("<H", len(indexed)))
    if version >= (1, 2):
        out += struct.pack("<H", len(rgba))
    for ix in indexed:
        h, w = ix.shape
        out += struct.pack("<HH", w, h)
        if version >= (2, 1):
            enc = rle(ix)
            out += struct.pack("<H", len(enc)) + enc
        else:
            out += ix.astype(np.uint8).tobytes()
    for img in rgba:
        h, w = img.shape[:2]
        out += struct.pack("<HH", w, h) + img[::-1, :, ::-1].tobytes()  # bottom-up, A,B,G,R
    if version >= (1, 1):
        out += (palette() if pal is None else pal).tobytes()
    return bytes(out)


def layer(x: int = 0, y: int = 0, index: int = 0, **kw: Any) -> sp.Layer:
    base: dict[str, Any] = dict(mirror=False, color=(255, 255, 255, 255), zoom_x=1.0, zoom_y=1.0,
                                angle=0, sprite_type=0, width=None, height=None)  # fmt: skip
    base.update(kw)
    return sp.Layer(x, y, index, **base)


def act_bytes(act: sp.Act) -> bytes:
    """Serialise an Act at its own version (the inverse of parse_act, for round trips)."""
    v = act.version
    out = bytearray(b"AC" + bytes((v[1], v[0])) + struct.pack("<H", len(act.actions)) + bytes(10))
    for motions in act.actions:
        out += struct.pack("<I", len(motions))
        for m in motions:
            out += bytes(range(32)) + struct.pack("<I", len(m.layers))
            for ly in m.layers:
                out += struct.pack("<iiiI", ly.x, ly.y, ly.sprite_index, int(ly.mirror))
                if v >= (2, 0):
                    out += bytes(ly.color)
                    out += (struct.pack("<ff", ly.zoom_x, ly.zoom_y) if v >= (2, 4)
                            else struct.pack("<f", ly.zoom_x))  # fmt: skip
                    out += struct.pack("<iI", ly.angle, ly.sprite_type)
                if v >= (2, 5):
                    out += struct.pack("<II", ly.width or 0, ly.height or 0)
            if v >= (2, 0):
                out += struct.pack("<i", m.event_id)
            if v >= (2, 3):
                out += struct.pack("<I", len(m.attach_points))
                for p in m.attach_points:
                    out += struct.pack("<IiiI", 0, p.x, p.y, p.attribute)
    if v >= (2, 1):
        out += struct.pack("<I", len(act.events))
        for name in act.events:
            out += name.encode("cp949").ljust(40, b"\x00")
    if v >= (2, 2):
        out += struct.pack(f"<{len(act.delays)}f", *act.delays)
    return bytes(out)


# --- SPR ---------------------------------------------------------------------------------------


def test_spr_21_decodes_rle_palette_and_rgba_images() -> None:
    ix = np.array([[0, 0, 0, 5], [9, MAGENTA, 0, 0], [0, 0, 0, 0]], np.uint8)  # runs + literals
    top_down = np.arange(2 * 3 * 4, dtype=np.uint8).reshape(2, 3, 4) + 1
    spr = sp.parse_spr(spr_bytes((2, 1), [ix], [top_down]))
    assert spr.version == (2, 1) and spr.indexed_count == 1 and len(spr.images) == 2
    img = spr.images[0]
    assert img.shape == (3, 4, 4) and spr.size(0) == (4, 3)
    assert tuple(img[0, 3]) == (5, 250, 40, 255) and tuple(img[1, 0]) == (9, 246, 40, 255)
    assert img[..., 3].sum() == 2 * 255  # index 0 AND the magenta key are transparent
    assert not img[ix == 0].any() and not img[1, 1].any()
    np.testing.assert_array_equal(spr.images[1], top_down)  # ABGR bottom-up -> RGBA top-down
    assert spr.image_index(0, 0) == 0 and spr.image_index(0, 1) == 1
    assert spr.image_index(-1, 0) is None and spr.image_index(1, 1) is None  # out of range


def test_the_rle_zero_count_is_one_pixel_and_overruns_are_clipped() -> None:
    out = sp._rle_zero_decode(bytes((3, 0, 0, 4, 0, 200)), 4)
    assert out.tolist() == [3, 0, 4, 0]  # 0x00 0x00 = one zero; the last run stops at the end


@pytest.mark.parametrize("version", [(1, 1), (1, 2), (2, 0)])
def test_older_spr_versions_store_raw_indices(version: tuple[int, int]) -> None:
    ix = np.array([[1, 0], [0, 2]], np.uint8)
    rgba = [np.full((1, 1, 4), 200, np.uint8)] if version >= (1, 2) else []
    spr = sp.parse_spr(spr_bytes(version, [ix], rgba))
    assert spr.version == version and len(spr.images) == 1 + len(rgba)
    assert spr.images[0][..., 3].tolist() == [[255, 0], [0, 255]]


def test_spr_10_needs_its_palette_given() -> None:
    data = spr_bytes((1, 0), [np.array([[3]], np.uint8)])
    with pytest.raises(sp.SpriteFormatError, match="palette"):
        sp.parse_spr(data)
    spr = sp.parse_spr(data, palette=palette())
    assert tuple(spr.images[0][0, 0]) == (3, 252, 40, 255)


@pytest.mark.parametrize(
    "data",
    [b"XP\x01\x02", b"SP\x09\x09" + bytes(4), b"SP\x01",
     spr_bytes((2, 1), [np.ones((4, 4), np.uint8)])[:-10]],  # the palette cut short
)  # fmt: skip
def test_a_bad_spr_is_refused(data: bytes) -> None:
    with pytest.raises(sp.SpriteFormatError):
        sp.parse_spr(data)


# --- ACT ---------------------------------------------------------------------------------------


def rich_act(version: tuple[int, int]) -> sp.Act:
    """Two actions exercising every field the version carries (the rest stay at defaults)."""
    v24, v25 = version >= (2, 4), version >= (2, 5)
    a = layer(3, -7, 1, mirror=True, color=(10, 20, 30, 40), zoom_x=1.5,
              zoom_y=0.5 if v24 else 1.5, angle=90, sprite_type=1,
              width=11 if v25 else None, height=13 if v25 else None)  # fmt: skip
    b = layer(-2, 4, 0, width=0 if v25 else None, height=0 if v25 else None)
    points = (sp.AttachPoint(5, -6, 1),) if version >= (2, 3) else ()
    m0 = sp.Motion((a, b), 1, points)
    m1 = sp.Motion((), -1, ())
    events = ("atk", "poring_move.wav") if version >= (2, 1) else ()
    delays = (4.0, 0.0) if version >= (2, 2) else ()
    return sp.Act(version, ((m0, m1), (m1,)), events, delays)


@pytest.mark.parametrize("version", [(2, 0), (2, 1), (2, 2), (2, 3), (2, 4), (2, 5)])
def test_act_round_trips_at_every_version(version: tuple[int, int]) -> None:
    act = rich_act(version)
    assert sp.parse_act(act_bytes(act)) == act


def test_act_25_fields_and_timing() -> None:
    act = sp.parse_act(act_bytes(rich_act((2, 5))))
    first = act.actions[0][0].layers[0]
    assert (first.zoom_x, first.zoom_y, first.width, first.height) == (1.5, 0.5, 11, 13)
    assert first.mirror and first.angle == 90 and first.color == (10, 20, 30, 40)
    assert act.actions[0][0].attach_points == (sp.AttachPoint(5, -6, 1),)
    assert act.events == ("atk", "poring_move.wav")
    assert act.delay_ms(0) == 4 * 24.0 and act.delay_units(1) == 1.0  # 0 plays at one unit
    old = sp.parse_act(act_bytes(rich_act((2, 0))))
    assert old.delays == () and old.delay_ms(0) == 24.0 and old.events == ()


def test_the_action_index_is_group_times_8_plus_direction() -> None:
    motion = (sp.Motion(()),)
    act = sp.Act((2, 5), tuple(motion for _ in range(40)))
    assert act.groups == 5
    assert act.action_index(2, 3) == 19 and act.action_index(1, 9) == 9  # direction mod 8
    assert act.action_index(7, 0) == 56 % 40  # past the table: wraps (act.rs:570)


@pytest.mark.parametrize("data", [b"AX\x05\x02", b"AC\x09\x02" + bytes(12), b"AC\x05\x02\x01"])
def test_a_bad_act_is_refused(data: bytes) -> None:
    with pytest.raises(sp.SpriteFormatError):
        sp.parse_act(data)


# --- composition -------------------------------------------------------------------------------


def sheet(*images: np.ndarray) -> sp.Spr:
    return sp.Spr((2, 1), tuple(images), len(images), None)


def act_of(*layers: sp.Layer) -> sp.Act:
    return sp.Act((2, 5), ((sp.Motion(tuple(layers)),),))


def rgba_image(h: int, w: int, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = rng.integers(1, 255, (h, w, 4), dtype=np.uint8)
    img[..., 3] = 255
    return img


def test_a_layer_is_centred_on_its_offset_from_the_anchor() -> None:
    img = rgba_image(2, 3)
    rgba, (ox, oy) = sp.compose_frame(sheet(img), act_of(layer(0, -1)), 0, 0)
    np.testing.assert_array_equal(rgba, img)  # copied texel for texel
    assert (ox, oy) == (1.5, 2.0)  # the quad spans x -1.5..1.5, y -2..0 around the anchor
    assert sp.opaque_bbox(rgba) == (0, 0, 3, 2)
    assert sp.opaque_extent(sheet(img), act_of(layer(0, -1)), 0, 0) == (-1.5, -2.0, 1.5, 0.0)
    assert sp.quad_extent(act_of(layer(0, -1)), 0, 0, sheet(img)) == (-1.5, -2.0, 1.5, 0.0)


def test_mirror_flips_the_layer_about_its_centre() -> None:
    img = rgba_image(2, 3, 1)
    rgba, origin = sp.compose_frame(sheet(img), act_of(layer(4, 2, mirror=True)), 0, 0)
    np.testing.assert_array_equal(rgba, img[:, ::-1])
    assert origin == (-2.5, -1.0)  # the quad is x 2.5..5.5, y 1..3: the anchor is off-canvas


def test_zoom_scales_each_axis_about_the_layer_centre() -> None:
    img = rgba_image(2, 2, 2)
    rgba, (ox, oy) = sp.compose_frame(sheet(img), act_of(layer(0, 0, zoom_x=2.0, zoom_y=3.0)), 0, 0)
    np.testing.assert_array_equal(rgba, np.repeat(np.repeat(img, 3, axis=0), 2, axis=1))
    assert (ox, oy) == (2.0, 3.0)


def test_a_quarter_turn_rotates_the_layer_clockwise_on_screen() -> None:
    img = np.zeros((1, 3, 4), np.uint8)
    img[0, :, 3] = 255
    img[0, :, 0] = (50, 100, 150)  # left, middle, right
    rgba, (ox, oy) = sp.compose_frame(sheet(img), act_of(layer(0, 0, angle=90)), 0, 0)
    assert rgba.shape == (3, 1, 4) and (ox, oy) == (0.5, 1.5)
    assert rgba[:, 0, 0].tolist() == [50, 100, 150]  # y down: +90 deg turns left->top


def test_layers_blend_in_order_with_their_tint() -> None:
    red = np.zeros((2, 2, 4), np.uint8)
    red[..., 0], red[..., 3] = 255, 255
    green = np.zeros((2, 2, 4), np.uint8)
    green[..., 1], green[..., 3] = 255, 255
    act = act_of(layer(0, 0, 0), layer(1, 0, 1, color=(255, 255, 255, 128)))  # half-alpha on top
    rgba, (ox, oy) = sp.compose_frame(sheet(red, green), act, 0, 0)
    assert rgba.shape == (2, 3, 4) and (ox, oy) == (1.0, 1.0)
    assert tuple(rgba[0, 0]) == (255, 0, 0, 255)  # red alone
    assert tuple(rgba[0, 1]) == (127, 128, 0, 255)  # green at 128/255 over red
    a = 128 / 255
    assert tuple(rgba[0, 2]) == (0, 255, 0, round(a * 255))  # green alone, half transparent


def test_tint_scales_the_colour() -> None:
    img = np.full((1, 1, 4), 200, np.uint8)
    rgba, _ = sp.compose_frame(sheet(img), act_of(layer(color=(255, 128, 0, 255))), 0, 0)
    assert tuple(rgba[0, 0]) == (200, 100, 0, 200)


def test_layers_that_draw_nothing_are_skipped() -> None:
    img = rgba_image(1, 1)
    for ly in (layer(index=-1), layer(index=5), layer(zoom_x=0.0), layer(color=(9, 9, 9, 0))):
        rgba, origin = sp.compose_frame(sheet(img), act_of(ly), 0, 0)
        assert rgba.shape == (0, 0, 4) and origin == (0.0, 0.0)
        assert sp.opaque_bbox(rgba) is None


def test_the_opaque_box_ignores_transparent_margins() -> None:
    img = np.zeros((6, 6, 4), np.uint8)
    img[2:4, 1:3] = 255
    rgba, (ox, oy) = sp.compose_frame(sheet(img), act_of(layer(0, -3)), 0, 0)
    assert sp.opaque_bbox(rgba) == (1, 2, 3, 4)
    assert sp.opaque_extent(sheet(img), act_of(layer(0, -3)), 0, 0) == (-2.0, -4.0, 0.0, -2.0)
    assert sp.quad_extent(act_of(layer(0, -3)), 0, 0, sheet(img)) == (-3.0, -6.0, 3.0, 0.0)


def test_the_quad_extent_needs_no_pixels_when_the_act_carries_sizes() -> None:
    act = act_of(layer(2, -10, width=8, height=20), layer(0, 0, 1, width=4, height=2, angle=90))
    assert sp.quad_extent(act, 0, 0) == (-2.0, -20.0, 6.0, 2.0)  # the turned 4x2 is 2 wide, 4 high
    with pytest.raises(sp.MissingImageSize):
        sp.quad_extent(act_of(layer(0, 0)), 0, 0)  # ACT < 2.5 sizes, no SPR: unknown
    ghost = layer(0, 0, width=500, height=500, color=(255, 255, 255, 0))  # tinted invisible
    assert sp.quad_extent(act_of(layer(0, -1, width=2, height=2), ghost), 0, 0) == (-1, -2, 1, 0)
    assert sp.union([None, (0, 0, 1, 1), (-1, 2, 0, 3)]) == (-1, 0, 1, 3)
    assert sp.union([None]) is None


def test_the_act_size_overrides_the_image_size() -> None:
    img = rgba_image(2, 2, 3)
    rgba, origin = sp.compose_frame(sheet(img), act_of(layer(0, 0, width=4, height=2)), 0, 0)
    np.testing.assert_array_equal(rgba, np.repeat(img, 2, axis=1))  # stretched to the ACT's 4x2
    assert origin == (2.0, 1.0)
