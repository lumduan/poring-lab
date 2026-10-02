"""poring_env.ui_anchors: windows found by template wherever they are; elements relative to them."""

import numpy as np
import pytest

from poring_env.ui_anchors import (
    ElementSpec,
    Resolver,
    UiAnchors,
    WindowSpec,
    match_template,
    to_gray,
)


def scene(rng: np.random.Generator) -> np.ndarray:
    return rng.integers(0, 256, (360, 640, 3), dtype=np.uint8)


def window_image(rng: np.random.Generator) -> np.ndarray:
    win = np.full((60, 120, 3), 230, np.uint8)
    win[:12] = rng.integers(0, 256, (12, 120, 3), dtype=np.uint8)  # a distinctive title bar
    win[30:40, 10:110] = (40, 40, 220)  # an "HP bar"
    return win


def registry(win: np.ndarray, icon: np.ndarray | None = None) -> UiAnchors:
    anchors = UiAnchors(
        {"w": WindowSpec("w", size=(120, 60))},
        {
            "bar": ElementSpec("bar", "w", box=(10, 30, 100, 10)),
            "icon": ElementSpec("icon", "w", icon=True),
        },
    )
    anchors.templates["w"] = to_gray(win[:12])
    if icon is not None:
        anchors.templates["icon"] = to_gray(icon)
    return anchors


@pytest.mark.parametrize("origin", [(0, 0), (200, 150), (519, 299)])
def test_windows_are_found_wherever_they_are_moved(origin: tuple[int, int]) -> None:
    rng = np.random.default_rng(1)
    frame, win = scene(rng), window_image(rng)
    x, y = origin
    frame[y : y + 60, x : x + 120] = win
    anchors = registry(win)
    found = anchors.locate(frame)
    assert found == {"w": origin}
    assert anchors.resolve("bar", found) == (x + 60, y + 35)  # moves with its window


def test_a_missing_window_resolves_to_none() -> None:
    rng = np.random.default_rng(2)
    anchors = registry(window_image(rng))
    frame = scene(rng)
    assert anchors.locate(frame) == {}
    assert anchors.resolve("bar", {}) is None


def test_icons_are_found_inside_their_window_whichever_slot() -> None:
    rng = np.random.default_rng(3)
    frame, win = scene(rng), window_image(rng)
    icon = rng.integers(0, 256, (10, 10, 3), dtype=np.uint8)
    win[44:54, 70:80] = icon  # the icon sits in some slot
    frame[100:160, 300:420] = win
    anchors = registry(win, icon)
    origins = anchors.locate(frame)
    assert anchors.resolve("icon", origins, frame) == (300 + 75, 100 + 49)


def test_match_template_is_exact_on_a_planted_patch() -> None:
    rng = np.random.default_rng(4)
    img = rng.random((50, 70)).astype(np.float32)
    m = match_template(img, img[20:30, 33:48].copy())
    assert m is not None and m.origin == (33, 20) and m.distance == pytest.approx(0, abs=1e-5)


def test_resolver_maps_cells_through_the_camera_and_refuses_without_one() -> None:
    camera = np.array([[30.0, 0, 392.0], [0, -30.0, 330.0], [0, 0, 1.0]])
    assert Resolver(UiAnchors({}, {}), camera).cell(2, 1) == (452, 300)
    with pytest.raises(ValueError):
        Resolver(UiAnchors({}, {})).cell(0, 0)
