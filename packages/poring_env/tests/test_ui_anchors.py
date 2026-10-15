"""poring_env.ui_anchors: windows found by template wherever they are; elements relative to them."""

from pathlib import Path

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


def test_locate_in_threads_gives_the_serial_answer() -> None:
    rng = np.random.default_rng(5)
    frame, win = scene(rng), window_image(rng)
    other = window_image(np.random.default_rng(6))
    frame[40:100, 30:150] = win
    frame[200:260, 400:520] = other
    anchors = registry(win)
    anchors.windows = {**anchors.windows, "v": WindowSpec("v", size=(120, 60))}
    anchors.templates["v"] = to_gray(other[:12])
    serial = anchors.locate(frame)
    assert serial == {"w": (30, 40), "v": (400, 200)}
    assert anchors.locate(frame, workers=4) == serial
    assert anchors.locate(scene(rng), workers=4) == {}


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


def test_templates_cut_at_known_origins_find_the_windows_after_a_move(tmp_path: Path) -> None:
    from poring_env.ui_anchors import cut_templates, load_templates, save_templates

    rng = np.random.default_rng(6)
    frame, win = scene(rng), window_image(rng)
    frame[20:80, 40:160] = win
    windows = {"w": WindowSpec("w", size=(120, 60), template_size=(120, 12))}
    save_templates(tmp_path, cut_templates(frame, {"w": (40, 20)}, windows))
    anchors = UiAnchors(windows, {"bar": ElementSpec("bar", "w", box=(10, 30, 100, 10))})
    anchors.templates.update(load_templates(tmp_path, windows))
    moved = scene(np.random.default_rng(7))
    moved[250:310, 400:520] = win  # dragged elsewhere
    assert anchors.locate(moved) == {"w": (400, 250)}


def test_a_translucent_window_is_found_over_any_background_with_its_stable_mask() -> None:
    from poring_env.ui_anchors import match_template, stable_masks

    rng = np.random.default_rng(8)
    glyphs = rng.random((14, 90)) < 0.25  # opaque "text" pixels; the rest is 30 % see-through glass
    ink = np.where(glyphs, 20.0, 230.0).astype(np.float32)

    def frame_with_strip(bg: np.ndarray, x: int, y: int) -> np.ndarray:
        out = bg.astype(np.float32).copy()
        under = out[y : y + 14, x : x + 90]
        out[y : y + 14, x : x + 90] = np.where(glyphs, ink, 0.7 * ink + 0.3 * under)
        return out

    bg1, bg2, bg3 = (rng.random((200, 300)).astype(np.float32) * 255 for _ in range(3))
    t1 = frame_with_strip(bg1, 10, 10)[10:24, 10:100]
    t2 = frame_with_strip(bg2, 10, 10)[10:24, 10:100]
    mask = stable_masks({"s": t1}, {"s": t2})["s"]
    assert 0.2 < mask.mean() < 0.4  # the glyphs only
    image = frame_with_strip(bg3, 150, 120)  # a third background, the window moved
    accept = WindowSpec("s", size=(90, 14)).max_distance
    masked = match_template(image, t1, mask)
    assert masked is not None and masked.origin == (150, 120)
    assert masked.distance <= accept  # chance-stable glass pixels keep it above 0, not above this
    plain = match_template(image, t1)
    assert plain is not None and plain.distance > accept  # unmasked, the glass makes it miss


# --- ADR-0012: the map stores keys, never text ------------------------------------------------


@pytest.mark.parametrize("key", ["msg.k0123abcd", "ui.ok", "ui.basic_info.close"])
def test_label_keys_are_message_keys_or_curated_aliases(key: str) -> None:
    assert ElementSpec("close", "w", box=(0, 0, 10, 10), label_key=key).label_key == key


@pytest.mark.parametrize(
    "text", ["Close", "close", "msg.k0123ABCD", "msg.k0123abc", "ui.", "ui.OK", "msg.0123abcd"]
)
def test_display_text_is_refused_as_a_label_key(text: str) -> None:
    with pytest.raises(ValueError, match="never text"):
        ElementSpec("close", "w", box=(0, 0, 10, 10), label_key=text)


@pytest.mark.parametrize("name", ["Close", "close button", "hp-bar", "1st", ""])
def test_window_and_element_names_are_canonical_identifiers(name: str) -> None:
    with pytest.raises(ValueError, match="canonical identifier"):
        WindowSpec(name, size=(10, 10))
    with pytest.raises(ValueError, match="canonical identifier"):
        ElementSpec(name, "w")


def test_the_shipped_registry_is_canonical_and_aliases_point_at_keys() -> None:
    from poring_env.ui_anchors import (
        ALIASES,
        ELEMENTS,
        WINDOWS,
        validate_aliases,
        validate_registry,
    )

    validate_registry(WINDOWS, ELEMENTS)
    validate_aliases(ALIASES)
    validate_aliases({"ui.ok": "msg.k0123abcd"})
    with pytest.raises(ValueError, match="not a message key"):
        validate_aliases({"ui.ok": "OK"})
    with pytest.raises(ValueError, match="unregistered window"):
        validate_registry(WINDOWS, {"x": ElementSpec("x", "nowhere")})


def test_the_minimap_readout_sits_inside_its_window_left_of_the_zoom_buttons() -> None:
    """Phase 3 T0: our own cell is read from ``minimap_xy``; the window is found by its zoom
    buttons, which the readout's box must never reach (a digit would then move the match)."""
    from poring_env.ui_anchors import CAPTURE_ORIGINS, ELEMENTS, WINDOWS

    window, element = WINDOWS["minimap"], ELEMENTS["minimap_xy"]
    assert element.window == "minimap" and element.label_key is None and not element.icon
    assert element.box is not None and window.template_size is not None
    dx, dy, w, h = element.box
    ww, wh = window.size
    assert dx >= 0 and dy >= 0 and dx + w <= ww and dy + h <= wh
    tx, ty = window.template_offset
    tw, th = window.template_size
    assert tx + tw <= ww and ty + th <= wh
    assert dx + w <= tx  # the readout stops where the buttons start
    ox, oy = CAPTURE_ORIGINS["minimap"]
    assert ox + ww <= 1280 and oy + wh <= 720  # right-anchored inside the 1280x720 game region
    # measured on the frozen layout (2026-10-04): the rect the reader parses, game-region pixels
    assert (ox + dx, oy + dy, w, h) == (1152, 145, 56, 15)
    anchors = UiAnchors(WINDOWS, ELEMENTS)
    assert anchors.resolve("minimap_xy", {"minimap": (ox, oy)}) == (1152 + 28, 145 + 7)


def test_labelled_boxes_follow_their_window_and_carry_only_keys() -> None:
    anchors = UiAnchors(
        {"w": WindowSpec("w", size=(120, 60))},
        {
            "ok": ElementSpec("ok", "w", box=(10, 40, 30, 12), label_key="msg.k0123abcd"),
            "bar": ElementSpec("bar", "w", box=(10, 30, 100, 10)),  # no text meaning: no key
        },
    )
    assert anchors.labelled_boxes({"w": (200, 100)}) == {
        "ok": ((210, 140, 30, 12), "msg.k0123abcd")
    }
    assert anchors.labelled_boxes({}) == {}  # window not on screen


def test_a_mask_cut_across_scenes_and_locales_drops_the_title_text() -> None:
    """ADR-0012: the same title bar in two locale packs differs only where its text is; masking
    across scenes AND locales leaves the chrome, so ONE template finds the window in both."""
    from poring_env.ui_anchors import stable_masks

    rng = np.random.default_rng(9)
    chrome = rng.random((14, 120)).astype(np.float32) * 255  # opaque window chrome
    text_cols = slice(30, 90)  # where the title's text is drawn

    def title(locale_seed: int) -> np.ndarray:
        strip = chrome.copy()
        glyphs = np.random.default_rng(locale_seed).random((14, 60)) < 0.4
        strip[:, text_cols] = np.where(glyphs, 15.0, chrome[:, text_cols])
        return strip

    en, th, en_other_scene = title(1), title(2), title(1)
    two_way = stable_masks({"t": en}, {"t": en_other_scene})["t"]  # the original call
    assert two_way.mean() == 1.0  # same locale: nothing to drop
    n_way = stable_masks({"t": en}, [{"t": en_other_scene}, {"t": th}])["t"]
    assert n_way[:, :30].all() and n_way[:, 90:].all()  # chrome stays
    assert n_way[:, text_cols].mean() < 0.7  # the glyphs that differ between locales are gone

    def frame_with(strip: np.ndarray, x: int, y: int) -> np.ndarray:
        out = rng.random((200, 300)).astype(np.float32) * 255
        out[y : y + 14, x : x + 120] = strip
        return out

    accept = WindowSpec("t", size=(120, 14)).max_distance
    for strip in (en, th):
        m = match_template(frame_with(strip, 100, 80), en, n_way)
        # chrome pixels within the tolerance of the glyph value stay in the mask by chance: > 0
        assert m is not None and m.origin == (100, 80) and m.distance < 1.0
    plain = match_template(frame_with(th, 100, 80), en)
    assert plain is not None and plain.distance > accept  # unmasked, the en text misses th


def test_variants_with_another_shape_are_ignored_per_name() -> None:
    from poring_env.ui_anchors import stable_masks

    t = np.zeros((4, 6), np.float32)
    masks = stable_masks({"a": t, "b": t}, [{"a": np.zeros((4, 5), np.float32)}, {"b": t + 10}])
    assert set(masks) == {"b"} and masks["b"].sum() == 0


def test_the_shortcut_windows_are_found_by_their_title_text_only() -> None:
    """2026-10-07: these windows share basic_info's title-bar style; a whole 200x15 title strip
    cross-matched status / inventory / equipment at 8.8-13.1. Their strips are the title TEXT
    (60x13 at dx 14) with a tighter max_distance (own 0.00, nearest other window 16.6, RDP)."""
    from poring_env import ui_anchors as ua

    for name in ("status", "skills", "inventory", "equipment"):
        spec = ua.WINDOWS[name]
        assert (spec.template_offset, spec.template_size, spec.max_distance) == (
            (14, 1),
            (60, 13),
            6.0,
        )
        assert name in ua.CAPTURE_ORIGINS
