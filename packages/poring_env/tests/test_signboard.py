"""poring_env.signboard (Batt 2026-10-08): a signboard is found by its SHAPE -- an outlined icon
square with a title bar attached -- never by its colour. The drawn sign below copies the wedding
NPC's sign as measured on banked frames (icon 32 x 32, bar 129 x 24 four px down, a 1-px black
outline, a 1-px white halo); real client frames are never committed (CLAUDE.md rule 4)."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from poring_env.signboard import Rect, find_signs

WHITE, BLACK = (255, 255, 255), (0, 0, 0)
ORANGE, BROWN, PICTURE = (208, 130, 40), (103, 75, 38), (200, 180, 220)
Img = npt.NDArray[np.uint8]


def floor(channels: int = 4) -> Img:
    img = np.zeros((720, 1280, channels), np.uint8)
    img[..., :3] = (130, 150, 185)  # BGR: a beige floor
    return img


def paint(img: Img, x0: int, y0: int, x1: int, y1: int, rgb: tuple[int, int, int]) -> None:
    img[y0 : y1 + 1, x0 : x1 + 1, :3] = rgb[::-1]  # inclusive, RGB -> BGR


def outlined(img: Img, x0: int, y0: int, x1: int, y1: int) -> None:
    paint(img, x0 - 1, y0 - 1, x1 + 1, y1 + 1, WHITE)
    paint(img, x0, y0, x1, y1, BLACK)


def draw_sign(img: Img, x: int, y: int, bar_w: int = 129, side: int = 32) -> tuple[Rect, Rect]:
    bar = Rect(x + side - 1, y + 4, x + side - 1 + bar_w - 1, y + side - 5)
    outlined(img, bar.x0, bar.y0, bar.x1, bar.y1)
    paint(img, bar.x0 + 1, bar.y0 + 1, bar.x1 - 1, bar.y1 - 1, ORANGE)
    paint(img, bar.x0 + 3, bar.y0 + 3, bar.x1 - 3, bar.y1 - 3, BROWN)
    for k in range(bar.x0 + 10, bar.x1 - 10, 7):  # the title's white strokes
        paint(img, k, bar.y0 + 8, k + 1, bar.y1 - 8, WHITE)
    icon = Rect(x, y, x + side - 1, y + side - 1)
    outlined(img, icon.x0, icon.y0, icon.x1, icon.y1)
    paint(img, icon.x0 + 1, icon.y0 + 1, icon.x1 - 1, icon.y1 - 1, ORANGE)
    paint(img, icon.x0 + 4, icon.y0 + 4, icon.x1 - 4, icon.y1 - 4, PICTURE)  # the item picture
    return icon, bar


def test_a_drawn_sign_is_found_as_its_icon_and_bar() -> None:
    img = floor()
    icon, bar = draw_sign(img, 599, 459)
    (s,) = find_signs(img)
    assert s.icon == icon and s.bar == bar
    assert (s.box.w, s.box.h) == (160, 32)  # the size every real hit had
    (s3,) = find_signs(np.ascontiguousarray(img[..., :3]))  # BGR as well as BGRA
    assert s3 == s


def test_a_sea_of_warm_colours_is_not_a_sign() -> None:
    """The first finder's failure: floor, piano, robes and wood all have the sign's colours."""
    rng = np.random.default_rng(7)
    img = floor()
    warm = np.array([ORANGE, BROWN, (220, 150, 60), (190, 140, 110), (240, 200, 150)], np.uint8)
    patch = warm[rng.integers(0, len(warm), (390, 900))]
    img[140:530, 230:1130, :3] = patch[..., ::-1]
    paint(img, 500, 200, 700, 330, BROWN)  # a big dark-brown block, outlined in black, no halo
    for x0, x1 in ((500, 700),):
        paint(img, x0, 199, x1, 199, BLACK)
        paint(img, x0, 331, x1, 331, BLACK)
    sparse = rng.random((390, 900)) < 0.01  # scattered pure black and white pixels
    img[140:530, 230:1130, :3][sparse] = 0
    img[140:530, 230:1130, :3][np.roll(sparse, 1, axis=0)] = 255
    assert find_signs(img) == []


def test_nothing_larger_than_a_sign_can_be_is_returned() -> None:
    img = floor()
    draw_sign(img, 100, 100, bar_w=500)  # a bar far longer than any title
    draw_sign(img, 100, 300, side=60)  # an icon twice a sign's size
    outlined(img, 700, 300, 1000, 400)  # a big outlined box
    paint(img, 701, 301, 999, 399, ORANGE)
    assert find_signs(img) == []


def test_an_icon_alone_or_a_bar_alone_is_not_a_sign() -> None:
    img = floor()
    outlined(img, 300, 300, 331, 331)
    paint(img, 301, 301, 330, 330, ORANGE)
    outlined(img, 600, 300, 729, 323)
    paint(img, 601, 301, 728, 322, BROWN)
    assert find_signs(img) == []


def test_an_npc_must_stand_under_its_sign_wherever_one_could_be_seen() -> None:
    img = floor()
    draw_sign(img, 600, 300)  # centre x 679.5, bottom 331
    npc = (662.0, 428.0, 697.0, 520.0)  # measured: top 93-102 px below, centred
    assert len(find_signs(img, npcs=[npc])) == 1
    assert find_signs(img, npcs=[]) == []  # the NPC's place is in view and empty
    assert find_signs(img, npcs=[(900.0, 428.0, 935.0, 520.0)]) == []  # an NPC, not under it
    assert find_signs(img, npcs=[(662.0, 340.0, 697.0, 430.0)]) == []  # too close under it


def test_a_sign_whose_npc_cannot_be_seen_is_kept_on_its_shape() -> None:
    img = floor()
    draw_sign(img, 600, 587)  # bottom 618: its NPC stands below the client's bottom edge
    assert len(find_signs(img, npcs=[])) == 1
    img = floor()
    draw_sign(img, 400, 400)  # its NPC would stand under the chat window
    assert len(find_signs(img, npcs=[], exclude=[(0, 532, 600, 626)])) == 1


def test_a_sign_inside_a_ui_window_is_the_windows_and_one_touching_it_is_kept() -> None:
    img = floor()
    draw_sign(img, 40, 40)
    draw_sign(img, 600, 134)
    windows = [(0, 0, 220, 326), (230, 0, 620, 136)]  # the second touches the sign's top rows
    (s,) = find_signs(img, exclude=windows)
    assert s.icon.x0 == 600


def test_search_limits_the_look_and_keeps_image_coordinates() -> None:
    img = floor()
    icon, _ = draw_sign(img, 599, 459)
    draw_sign(img, 100, 100)
    (s,) = find_signs(img, search=(230, 140, 1130, 530))
    assert s.icon == icon
