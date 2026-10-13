"""poring_env.npc_dialog (talk@1 T2): the dialog and menu windows from pixels, on SYNTHETIC frames
drawn to the measured geometry (white frame, grey border lines, the grey text area, a button image,
the menu's rows, highlight band and scrollbar). No client pixels."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from poring_env import npc_dialog as nd
from poring_env.ui_anchors import ELEMENTS, WINDOWS

G = nd.GEOMETRY
H, W = 480, 640
GREY_BORDER = 198
RNG = np.random.default_rng(3)
NEXT_IMG = (RNG.random((20, 42)) * 120 + 100).astype(np.uint8)
CLOSE_IMG = (RNG.random((20, 42)) * 120 + 100).astype(np.uint8)
# the NEXT button's highlighted (hover / focus) look: NEXT's ink on a different fill
HI_IMG = np.clip(NEXT_IMG.astype(int) - 70, 0, 255).astype(np.uint8)
OK_IMG = (RNG.random((20, 42)) * 120 + 100).astype(np.uint8)
CANCEL_IMG = (RNG.random((20, 42)) * 120 + 100).astype(np.uint8)
ARROW = (60, 70, 160)  # BGR, a dark blue arrow
THUMB = (230, 160, 90)


def scene(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return (rng.random((H, W, 3)) * 255).astype(np.uint8)


def _frame(img: np.ndarray, origin: tuple[int, int], window: str) -> np.ndarray:
    w, h = G.size(window)
    x, y = origin
    win = img[y : y + h, x : x + w]
    win[:] = 255
    c = G.corner
    win[2, c : w - c] = GREY_BORDER
    win[h - 3, c : w - c] = GREY_BORDER
    win[c : h - c, 2] = GREY_BORDER
    win[c : h - c, w - 3] = GREY_BORDER
    return win


def draw_dialog(img: np.ndarray, origin: tuple[int, int], button: str | None,
                seed: int = 0) -> None:  # fmt: skip
    win = _frame(img, origin, nd.DIALOG)
    x, y, w, h = G.dialog_text
    win[y : y + h, x : x + w] = 247
    rng = np.random.default_rng(seed)
    ix, iy, iw, ih = G.dialog_ink
    ink = rng.random((ih - 30, iw - 60)) < 0.15
    win[iy + 2 : iy + 2 + ih - 30, ix + 1 : ix + 1 + iw - 60][ink] = 0
    bx, by, bw, bh = G.dialog_button
    if button is not None:
        img_b = {"next": NEXT_IMG, "next_hi": HI_IMG}.get(button, CLOSE_IMG)
        win[by : by + bh, bx : bx + bw] = img_b[..., None]


def draw_menu(img: np.ndarray, origin: tuple[int, int], highlight: int | None,
              thumb: tuple[int, int] | None, seed: int = 0) -> None:  # fmt: skip
    win = _frame(img, origin, nd.MENU)
    lx, ly, lw, lh = G.menu_list
    win[ly : ly + lh, lx : lx + lw] = 247
    rng = np.random.default_rng(seed)
    for k in range(G.rows):
        top = G.row_top + k * G.row_pitch
        if k == highlight:
            win[top : top + G.row_h - 1, lx : lx + lw] = (255, 222, 206)
        tx, tw = G.row_text
        ink = rng.random((10, 120)) < 0.3
        win[top + 2 : top + 12, tx + 3 : tx + 123][ink] = 0
    if thumb is not None:
        for name in (nd.UP, nd.DOWN):
            ax, ay, aw, ah = G.element_box(name)
            win[ay + 2 : ay + ah - 2, ax + 3 : ax + aw - 3] = ARROW
        tx, ty, tw, th = G.track
        win[ty : ty + th, tx + 2 : tx + tw - 2] = (222, 222, 214)  # the track (BGR)
        win[ty + thumb[0] : ty + thumb[1], tx + 2 : tx + tw - 2] = THUMB
    for name, image in ((nd.OK, OK_IMG), (nd.CANCEL, CANCEL_IMG)):
        bx, by, bw, bh = G.element_box(name)
        win[by : by + bh, bx : bx + bw] = image[..., None]


D0, M0 = (201, 101), (201, 301)


@pytest.fixture(scope="module")
def templates() -> nd.DialogTemplates:
    dialogs, menus, scrolled = [], [], []
    for i in range(4):
        f = scene(100 + i)
        draw_dialog(f, D0, "next", seed=i)
        draw_menu(f, M0, i % 4, (0, 22) if i % 2 else (10, 30), seed=i)
        dialogs.append(f)
        menus.append(f)
        scrolled.append(f)
    closes = []
    blanks = []
    for i in range(2):
        f = scene(200 + i)
        draw_dialog(f, D0, "close", seed=10 + i)
        closes.append(f)
        f2 = scene(300 + i)
        draw_dialog(f2, D0, None, seed=20 + i)
        blanks.append(f2)
    images: dict[str, nd.Gray] = {}
    masks: dict[str, nd.Gray] = {}
    images[nd.DIALOG], masks[nd.DIALOG] = nd.cut_window(dialogs + closes + blanks,
                                                        [D0] * 8, nd.DIALOG)  # fmt: skip
    images[nd.MENU], masks[nd.MENU] = nd.cut_window(menus, [M0] * 4, nd.MENU)
    images[nd.NEXT] = nd.cut_element(dialogs, [D0] * 4, nd.NEXT)
    images[nd.CLOSE] = nd.cut_element(closes, [D0] * 2, nd.CLOSE)
    images[nd.BLANK] = nd.cut_element(blanks, [D0] * 2, nd.BLANK)
    for name in (nd.OK, nd.CANCEL, nd.UP, nd.DOWN):
        images[name] = nd.cut_element(menus, [M0] * 4, name)
    for name in (nd.UP, nd.DOWN):
        masks[name] = nd.arrow_mask(scrolled, [M0] * 4, name)
    t = nd.DialogTemplates(images, masks)
    assert t.missing == ()
    return t


def test_the_geometry_is_the_anchor_maps() -> None:
    assert G.dialog_size == WINDOWS["npc_dialog"].size and G.menu_size == WINDOWS["npc_menu"].size
    assert G.dialog_button == ELEMENTS["npc_dialog_next"].box == ELEMENTS["npc_dialog_close"].box
    for k in range(G.rows):
        assert G.row_box(k) == ELEMENTS[f"npc_menu_row_{k + 1}"].box
    for name in ("npc_menu_up", "npc_menu_down", "npc_menu_ok", "npc_menu_cancel"):
        assert G.element_box(name) == ELEMENTS[name].box
    for name, spec in ELEMENTS.items():
        if spec.window in ("npc_dialog", "npc_menu"):
            dx, dy, w, h = spec.box or (0, 0, 0, 0)
            ww, wh = WINDOWS[spec.window].size
            assert min(dx, dy) >= 0 and dx + w <= ww and dy + h <= wh, name
    m = nd.structural_mask(nd.DIALOG)
    x, y, w, h = G.dialog_ink
    assert m[y : y + h, x : x + w].sum() == 0 and m[0:6, 0:6].sum() == 0 and m.mean() > 0.2


@pytest.mark.parametrize("origin", [(201, 101), (40, 20), (330, 250)])
def test_a_dialog_is_found_anywhere_with_its_button(templates: nd.DialogTemplates,
                                                    origin: tuple[int, int]) -> None:  # fmt: skip
    for button in ("next", "close", None):
        f = scene(7)
        draw_dialog(f, origin, button, seed=99)
        st = nd.state(f, templates)
        assert st.ok, st.reason
        assert st.dialog is not None and st.dialog.rect[:2] == origin
        assert st.dialog.button == button and st.menu is None and not st.gone


def test_a_menu_reads_its_highlight_and_scrollbar(templates: nd.DialogTemplates) -> None:
    for highlight, thumb, up, down in (
        (0, (0, 22), False, True),
        (2, (8, 30), True, True),
        (3, (17, 39), True, False),
        (None, (5, 27), True, True),
    ):
        f = scene(8)
        draw_dialog(f, D0, None, seed=5)
        draw_menu(f, M0, highlight, thumb, seed=6)
        st = nd.state(f, templates)
        assert st.ok, st.reason
        m = st.menu
        assert m is not None and m.rect[:2] == M0 and st.dialog is not None
        assert (m.highlight_row, m.can_scroll_up, m.can_scroll_down) == (highlight, up, down)
        assert m.thumb == thumb and m.scrollbar
        assert m.rows[0] == (M0[0] + 11, M0[1] + 25, 243, 16)
        assert nd.centre(m.ok_rect) == (M0[0] + 187 + 21, M0[1] + 95 + 10)


def test_a_short_menu_has_no_scrollbar(templates: nd.DialogTemplates) -> None:
    f = scene(9)
    draw_menu(f, M0, 1, None, seed=1)
    st = nd.state(f, templates)
    assert st.ok and st.menu is not None
    assert (st.menu.scrollbar, st.menu.can_scroll_up, st.menu.can_scroll_down) == (False,) * 3


def test_no_window_is_gone(templates: nd.DialogTemplates) -> None:
    st = nd.state(scene(10), templates)
    assert st.ok and st.gone and all(f.verdict == "absent" for f in st.finds)


def test_fail_closed(templates: nd.DialogTemplates) -> None:
    f = scene(11)
    draw_dialog(f, D0, "next", seed=3)
    f[D0[1] + 160 : D0[1] + 170, D0[0] + 240 : D0[0] + 260] = (40, 200, 40)  # a cursor on NEXT
    assert nd.state(f, templates).reason == "button_unknown"
    f = scene(12)
    draw_dialog(f, D0, "next", seed=3)
    f[D0[1] + 40 : D0[1] + 100, D0[0] : D0[0] + 40] = scene(13)[:60, :40]  # an occluder
    st = nd.state(f, templates)
    assert not st.ok and st.reason == "npc_dialog_uncertain"
    f = scene(14)
    draw_menu(f, M0, 1, (0, 22), seed=2)
    y = M0[1] + 25 + 16 * 2
    f[y : y + 15, M0[0] + 11 : M0[0] + 40] = (30, 160, 30)  # row 3's margin covered
    assert nd.state(f, templates).reason == "row_background"
    f = scene(15)
    draw_menu(f, M0, 1, (0, 22), seed=2)
    y = M0[1] + 25 + 16 * 3
    f[y : y + 15, M0[0] + 11 : M0[0] + 267] = (255, 222, 206)  # two highlighted rows
    assert nd.state(f, templates).reason == "highlight_ambiguous"
    f = scene(16)
    draw_menu(f, M0, 1, (0, 22), seed=2)
    ax, ay, aw, ah = G.up_arrow
    f[M0[1] + ay : M0[1] + ay + ah, M0[0] + ax : M0[0] + ax + aw] = 247  # one arrow gone
    assert nd.state(f, templates).reason == "scrollbar_partial"
    t2 = nd.DialogTemplates({k: v for k, v in templates.images.items() if k != nd.MENU},
                            templates.masks)  # fmt: skip
    assert nd.state(scene(17), t2).reason.startswith("no_templates")


def test_missing_close_template_makes_close_unknown(templates: nd.DialogTemplates) -> None:
    t = nd.DialogTemplates({k: v for k, v in templates.images.items() if k != nd.CLOSE},
                           templates.masks)  # fmt: skip
    assert t.missing == ()  # CLOSE is not required to load ...
    f = scene(18)
    draw_dialog(f, D0, "close", seed=4)
    assert nd.state(f, t).reason == "button_unknown"  # ... but is never guessed


def test_same_state_and_hints(templates: nd.DialogTemplates) -> None:
    f = scene(19)
    draw_dialog(f, (60, 60), "next", seed=8)
    a = nd.state(f, templates)
    b = nd.state(f, templates, hints={nd.DIALOG: (60, 60)})
    assert nd.same_state(a, b) and b.dialog is not None and b.dialog.rect[:2] == (60, 60)
    c = nd.state(f, templates, hints={nd.DIALOG: (201, 101)})  # a stale hint: searched anyway
    assert nd.same_state(a, c)
    g = scene(19)
    draw_dialog(g, (60, 60), "close", seed=8)
    assert not nd.same_state(a, nd.state(g, templates))
    assert not nd.same_state(nd.NpcUiState(False, "x", 0.0), nd.NpcUiState(False, "x", 0.0))


def test_border_check_and_round_trip(tmp_path: Path, templates: nd.DialogTemplates) -> None:
    f = scene(20)
    draw_dialog(f, D0, "next")
    assert nd.border_ok(f, D0, nd.DIALOG) and not nd.border_ok(f, (D0[0] + 3, D0[1]), nd.DIALOG)
    assert not nd.border_ok(f, M0, nd.MENU)
    templates.meta["sessions"] = ["s1"]
    templates.save(tmp_path / "t")
    back = nd.load_templates(tmp_path / "t")
    assert (
        back.missing == () and back.meta["sessions"] == ["s1"] and back.params == templates.params
    )
    assert nd.state(f, back).dialog is not None
    doc = (
        (tmp_path / "t" / nd.PARAMS_FILE).read_text().replace('"row_pitch": 16', '"row_pitch": 17')
    )
    (tmp_path / "t" / nd.PARAMS_FILE).write_text(doc)
    with pytest.raises(ValueError, match="geometry"):
        nd.load_templates(tmp_path / "t")


def test_params_are_ordered() -> None:
    with pytest.raises(ValueError):
        nd.Params(window_accept=0.3, window_absent=0.2)
    with pytest.raises(ValueError):
        nd.Params(edge_accept=0.5, edge_absent=0.3)


def test_the_highlighted_next_reads_as_next_only_with_its_template(
    templates: nd.DialogTemplates,
) -> None:
    """Batt 2026-10-13 (decision 2): the NEXT button's highlighted look (npc-click@1's stop, 3.32a).
    Without its template the reader is unchanged (button_unknown: stop); with it, NEXT. The plain
    looks still read as before, and NEXT's two looks never refuse each other."""
    f = scene(7)
    draw_dialog(f, D0, "next_hi", seed=99)
    st = nd.state(f, templates)
    assert not st.ok and st.reason == "button_unknown"
    his = []
    for i in range(2):
        h = scene(400 + i)
        draw_dialog(h, D0, "next_hi", seed=30 + i)
        his.append(h)
    images = dict(templates.images)
    images[nd.NEXT_HI] = nd.cut_element(his, [D0] * 2, nd.NEXT_HI)
    t2 = nd.DialogTemplates(images, dict(templates.masks), templates.params)
    st = nd.state(f, t2)
    assert st.ok and st.dialog is not None and st.dialog.button == "next"
    for button in ("next", "close", None):
        g = scene(7)
        draw_dialog(g, D0, button, seed=99)
        st = nd.state(g, t2)
        assert st.ok and st.dialog is not None and st.dialog.button == button
    # two looks of one button: grouped, the margin is taken against the OTHER buttons only
    crop = images[nd.NEXT_HI]
    label, _ = nd.classify_button(crop, (nd.NEXT, nd.NEXT_HI, nd.CLOSE), t2,
                                  same={nd.NEXT_HI: nd.NEXT})  # fmt: skip
    assert label == nd.NEXT_HI
