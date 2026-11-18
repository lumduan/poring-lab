"""The virtual 1280x720 client (docs/planning/fullscreen-client.md section 7): the vectors that map
any real client to the 1280x720 one the bot was built on, and back."""

from __future__ import annotations

import numpy as np
import pytest

from poring_env.clientview import (
    VIRTUAL_H,
    VIRTUAL_W,
    ClientView,
    Panel,
    anchor_point,
    anchored_view,
)

# the lab's 1280x720 layout, in virtual pixels (Basic Info at the top-left, the minimap at the
# top-right, the chat window docked at the bottom-left)
LAYOUT = (
    ("basic_info", (0, 0, 220, 140), "tl"),
    ("minimap", (1136, 14, 128, 144), "tr"),
    ("chat", (0, 580, 600, 140), "bl"),
)


def test_the_anchors_are_the_corners_edges_and_centre() -> None:
    assert anchor_point("tl", 1920, 1080) == (0.0, 0.0)
    assert anchor_point("br", 1920, 1080) == (1920.0, 1080.0)
    assert anchor_point("c", 1920, 1080) == (960.0, 540.0)
    assert anchor_point("t", 1920, 1080) == (960.0, 0.0)
    assert anchor_point("r", 1920, 1080) == (1920.0, 540.0)


def test_a_panel_keeps_its_vector_from_its_anchor() -> None:
    """At 1920x1080 the minimap stays 144 px from the right edge (+640 in x), the chat window
    stays on the bottom edge (+360 in y), Basic Info stays at the top-left."""
    size = (1920, 1080)
    assert Panel.anchored("m", (1136, 14, 128, 144), "tr", size).real_xy == (1776, 14)
    assert Panel.anchored("c", (0, 580, 600, 140), "bl", size).real_xy == (0, 940)
    assert Panel.anchored("b", (0, 0, 220, 140), "tl", size).real_xy == (0, 0)
    assert Panel.anchored("x", (600, 700, 80, 20), "b", size).real_xy == (920, 1060)


def test_the_lab_client_is_the_identity_wherever_its_window_is() -> None:
    view = anchored_view((80, 77, 1280, 720), "window", LAYOUT)
    assert view.identity
    assert view.to_real(640, 360) == (720, 437)  # the window's origin added, nothing else
    assert view.to_virtual(720, 437) == (640, 360)
    frame = np.random.default_rng(1).integers(0, 255, (900, 1440, 3), dtype=np.uint8)
    assert np.array_equal(view.virtual_frame(frame), frame[77:797, 80:1360])


def test_fullscreen_1080p_maps_the_world_from_the_centre_and_the_ui_by_its_anchors() -> None:
    view = anchored_view((0, 0, 1920, 1080), "fullscreen", LAYOUT)
    assert not view.identity
    assert view.to_real(640, 360) == (960, 540)  # the player, at the centre
    assert view.to_real(700, 300) == (1020, 480)  # a world point: the same vector from it
    assert view.to_real(1200, 50) == (1840, 50)  # in the minimap: +640 in x
    assert view.to_real(10, 700) == (10, 1060)  # in the chat window: +360 in y
    for v in ((640, 360), (700, 300), (1200, 50), (10, 700), (100, 100), (1279, 719)):
        assert view.to_virtual(*view.to_real(*v)) == pytest.approx(v)


def test_a_scaled_world_and_its_inverse() -> None:
    view = anchored_view((0, 0, 1920, 1080), "fullscreen", LAYOUT, world_scale=1.5)
    assert view.to_real(700, 300) == (1050, 450)  # 960 + 1.5 * 60, 540 - 1.5 * 60
    assert view.to_virtual(1050, 450) == pytest.approx((700, 300))
    assert view.to_real(1200, 50) == (1840, 50)  # the UI never scales


def test_the_virtual_frame_puts_the_world_and_every_panel_where_the_bot_expects_them() -> None:
    """A synthetic 1920x1080 frame: a world whose pixels encode their own position, and three
    panels of one colour each at their anchored real places."""
    h, w = 1080, 1920
    yy, xx = np.mgrid[0:h, 0:w]
    frame = np.stack([xx % 256, yy % 256, (xx // 256) * 16 + (yy // 256)], -1).astype(np.uint8)
    view = anchored_view((0, 0, w, h), "fullscreen", LAYOUT)
    colours = {"basic_info": 11, "minimap": 22, "chat": 33}
    for p in view.panels:
        x, y = p.real_xy
        _, _, pw, ph = p.virtual
        frame[y : y + ph, x : x + pw] = colours[p.name]
    out = view.virtual_frame(frame)
    assert out.shape == (VIRTUAL_H, VIRTUAL_W, 3)
    for name, box, _ in LAYOUT:
        x, y, pw, ph = box
        assert (out[y : y + ph, x : x + pw] == colours[name]).all(), name
    # a world pixel: virtual (700, 300) shows the real (1020, 480)
    assert tuple(out[300, 700]) == tuple(frame[480, 1020])


def test_a_client_smaller_than_the_virtual_one_leaves_its_outside_black() -> None:
    view = anchored_view((0, 0, 1024, 768), "fullscreen", LAYOUT)
    frame = np.full((768, 1024, 3), 200, dtype=np.uint8)
    out = view.virtual_frame(frame)
    assert (out[360, 0] == 0).all()  # the world beyond a 1024-wide client: nothing to show
    assert (out[360, 640] == 200).all()


def test_a_panel_drawn_over_another_wins() -> None:
    a = Panel("a", (0, 0, 100, 100), (0, 0))
    b = Panel("b", (50, 50, 100, 100), (500, 500))
    view = ClientView((0, 0, 1280, 720), panels=(a, b))
    p = view.panel_at(60, 60)
    assert p is not None and p.name == "b"
    assert view.to_real(60, 60) == (510, 510)


def test_a_panel_leaves_no_shrunk_ghost_in_the_world() -> None:
    """The lab's chat window stays at its SAVED pixels (0, 580) in 1080p, lying ON the world: shrunk
    by the world transform it would show again near virtual (0, 387); that place in the world layer
    is blanked, the panel itself pasted at its virtual place (measured live 2026-11-18)."""
    chat = Panel("chat", (0, 580, 600, 140), (0, 580))
    view = ClientView((0, 0, 1920, 1080), "fullscreen", 1.5, None, (chat,))
    frame = np.full((1080, 1920, 3), 90, dtype=np.uint8)
    frame[580:720, 0:600] = 33
    out = view.virtual_frame(frame)
    gy = int(360 + (580 - 540) / 1.5)  # where the ghost would be: 386
    assert (out[gy + 5, 10] == 0).all()  # blanked, not 33
    assert (out[600, 10] == 33).all()  # the panel at its virtual place
    assert (out[100, 640] == 90).all()  # the world elsewhere
