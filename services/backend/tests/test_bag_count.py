"""scripts/bag_count.py (docs/planning/econ-bag-count.md): the bag found by its oval lattice, the
items by their icons over this client's own empty slot, the counts by their pure-black digits,
and the pre-registered bar. Synthetic frames only (no client pixels)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import bag_count as bc  # noqa: E402
import slot_items as si  # noqa: E402

ORIGIN = (300, 200)


def _oval() -> np.ndarray:
    """The oval's pixels in its tight box (an ellipse touching all four edges)."""
    w, h = bc.OVAL_BOX[2], bc.OVAL_BOX[3]
    yy, xx = np.mgrid[0:h, 0:w]
    return ((xx + 0.5 - w / 2) / (w / 2)) ** 2 + ((yy + 0.5 - h / 2) / (h / 2)) ** 2 <= 1.0


def _font() -> dict[str, np.ndarray]:
    rng = np.random.default_rng(5)
    t = {str(d): rng.random((9, 6)) > 0.45 for d in range(10)}
    for g in t.values():
        g[0, :] = g[-1, :] = True
        g[:, 0] = g[:, -1] = True  # every glyph spans its cell: one run each
    t["1"] = t["1"][:, :5]
    return t


def _icons(n: int) -> dict[int, np.ndarray]:
    """n made-up item bitmaps (RGB, the key colour around a coloured blob)."""
    rng = np.random.default_rng(9)
    out = {}
    for k in range(n):
        a = np.zeros((24, 24, 3), np.uint8)
        a[..., 0] = a[..., 2] = 255  # the key colour
        a[3:20, 3:20] = rng.integers(20, 235, size=(17, 17, 3))
        out[1000 + k] = a
    return out


def _frame(
    items: list[tuple[int, int]],
    icons: dict[int, np.ndarray],
    font: dict[str, np.ndarray],
    origin: tuple[int, int] = ORIGIN,
) -> np.ndarray:
    """A 1920x1080 BGR frame with a bag at ``origin``: ``items`` (id, count) in reading order,
    then empty slots (white face, the oval)."""
    f = np.full((1080, 1920, 3), 90, np.uint8)
    ox, oy = origin
    f[oy : oy + 255, ox : ox + 280] = 255
    oval = _oval()
    for s in range(bc.SLOTS):  # every slot's oval first (drawn behind items too)
        x, y = bc.icon_xy(origin, s)
        dx, dy, w, h = bc.OVAL_BOX
        f[y + dy : y + dy + h, x + dx : x + dx + w][oval] = bc.OVAL[::-1]  # BGR
    for s, (iid, n) in enumerate(items):  # then the icons and their counts (the client: last)
        x, y = bc.icon_xy(origin, s)
        bmp = icons[iid]
        key = si.transparent(bmp)
        sq = f[y : y + 24, x : x + 24]
        sq[~key] = bmp[~key][:, ::-1]
        text = str(n)
        width = sum(font[ch].shape[1] for ch in text) + len(text) - 1
        # the client's rule: 1-3 digits from x + 14 (+ 1 for a leading '1'); 4 digits END at x + 26
        # (measured: "1000" = x+1 .. 26)
        left = x + 14 + (1 if text[0] == "1" else 0)
        cx = left if len(text) <= 3 else x + 26 - width + 1
        for ch in text:
            g = font[ch]
            f[y + bc.COUNT_DY : y + bc.COUNT_DY + 9, cx : cx + g.shape[1]][g] = 0
            cx += g.shape[1] + 1
    return f


def _refs(icons: dict[int, np.ndarray]) -> si.SlotRefs:
    return si.SlotRefs.from_icons(icons, {k: f"item {k}" for k in icons})


def _read(f: np.ndarray, refs: si.SlotRefs, font: dict[str, np.ndarray]) -> bc.TabRead:
    origin = bc.find_window(f)
    assert origin is not None
    empty = bc.empty_picture(f, origin)
    assert empty is not None
    return bc.TabRead("t", bc.read_tab(f, origin, bc.Pictures.over(refs, empty), empty, font))


def test_the_bag_is_found_at_its_exact_place_whatever_fills_it() -> None:
    font, icons = _font(), _icons(45)
    ids = list(icons)
    for n in (0, 1, 7, 20, 40):  # an empty tab, a row and a bit, all but two slots
        f = _frame([(ids[k], 1) for k in range(n)], icons, font)
        assert bc.find_window(f) == ORIGIN, n
        assert bc.window_at(f, ORIGIN)
        assert not bc.window_at(f, (ORIGIN[0] + bc.PITCH, ORIGIN[1]))  # a column off
        assert not bc.window_at(f, (ORIGIN[0], ORIGIN[1] + bc.PITCH))  # a row off


def test_no_bag_and_a_full_tab_find_nothing() -> None:
    font, icons = _font(), _icons(45)
    assert bc.find_window(np.full((1080, 1920, 3), 90, np.uint8)) is None
    ids = list(icons)
    full = _frame([(ids[k % 45], 1) for k in range(bc.SLOTS)], icons, font)
    assert bc.find_window(full) is None  # no empty slot: no lattice (never a guessed place)


def test_items_and_counts_read_exactly_one_to_four_digits() -> None:
    font, icons = _font(), _icons(12)
    refs = _refs(icons)
    ids = list(icons)
    # (a 3-digit count before a 4-digit one touches it -- the next test -- so not side by side here)
    items = [(ids[0], 1), (ids[1], 7), (ids[2], 17), (ids[3], 46), (ids[4], 100), (ids[5], 9),
             (ids[6], 1234), (ids[7], 588)]  # fmt: skip
    tab = _read(_frame(items, icons, font), refs, font)
    got = [(b.ids, b.count) for b in tab.items()]
    assert got == [((iid,), n) for iid, n in items]
    assert not tab.unread() and not tab.full
    assert bc.bag_totals([tab]) == {str(iid): n for iid, n in items}


def test_an_unknown_icon_or_a_hidden_count_is_unread_never_a_guess() -> None:
    font, icons = _font(), _icons(6)
    refs = _refs({k: v for k, v in icons.items() if k != 1005})  # 1005 is not in the archive
    ids = list(icons)
    f = _frame([(ids[0], 3), (ids[5], 2)], icons, font)
    tab = _read(f, refs, font)
    assert [b.ids for b in tab.items()] == [(ids[0],)]
    (u,) = tab.unread()
    assert u.slot == 1 and "no known icon" in u.why
    # the count's first digit covered (a pointer): unread, not the shorter "6"
    f2 = _frame([(ids[0], 16)], icons, font)
    x, y = bc.icon_xy(ORIGIN, 0)
    f2[y + bc.COUNT_DY + 3 : y + bc.COUNT_DY + 6, x + 15 : x + 19] = (40, 200, 40)
    tab2 = _read(f2, refs, font)
    assert not tab2.items() and tab2.unread()[0].why == "the count did not read"


def test_an_item_after_an_empty_slot_is_unread() -> None:
    font, icons = _font(), _icons(4)
    refs = _refs(icons)
    ids = list(icons)
    f = _frame([(ids[0], 2)], icons, font)
    # paste an icon into slot 5 (after empty slots): a pointer, a tooltip, a drag in progress
    x, y = bc.icon_xy(ORIGIN, 5)
    bmp = icons[ids[1]]
    key = si.transparent(bmp)
    f[y : y + 24, x : x + 24][~key] = bmp[~key][:, ::-1]
    origin = bc.find_window(f)
    assert origin is None or origin == ORIGIN  # the lattice may refuse (ovals not a tail)
    empty = bc.empty_picture(_frame([(ids[0], 2)], icons, font), ORIGIN)
    assert empty is not None
    slots = bc.read_tab(f, ORIGIN, bc.Pictures.over(refs, empty), empty, font)
    assert slots[5].kind == "unread" and "after an empty slot" in slots[5].why


def test_the_bar_b1_to_b4() -> None:
    read = {"totals": {"507": 8, "2401|2402": 1, "911": 46}, "unread": 0, "as_found": True,
            "seconds": 14.2}  # fmt: skip
    v = bc.judge(read, {507: 8, 2402: 1, 911: 46})
    assert v["B1_no_wrong"] and v["B2_read_98"] and v["B3_as_found"] and v["B4_20s"]
    v2 = bc.judge({**read, "totals": {"507": 9, "911": 46}}, {507: 8, 2402: 1, 911: 46})
    assert not v2["B1_no_wrong"] and v2["missed"] == [2402] and not v2["B2_read_98"]
    v3 = bc.judge({**read, "totals": {"999": 1}}, {507: 8})
    assert v3["wrong"][0]["why"] == "no such item in the bag"


@pytest.mark.parametrize("n", [1, 9, 46, 1234])
def test_read_count_alone(n: int) -> None:
    font, icons = _font(), _icons(1)
    f = _frame([(1000, n)], icons, font)
    assert bc.read_count(f, ORIGIN, 0, font) == n


def test_an_item_in_two_tabs_means_a_click_that_did_not_take() -> None:
    use = bc.TabRead("use", [bc.BagSlot(0, "item", (507,), 8), bc.BagSlot(1, "empty")])
    again = bc.TabRead("eqp", [bc.BagSlot(0, "item", (507,), 8), bc.BagSlot(1, "empty")])
    etc = bc.TabRead("etc", [bc.BagSlot(0, "item", (911,), 46)])
    assert bc.shared_items([use, etc]) == {}
    assert bc.shared_items([use, again, etc]) == {"eqp": {507}}


def test_the_measured_count_shapes_and_their_neighbours() -> None:
    """The runs measured on the trials' frames (icon-relative columns): T5's 123 (the trial that
    read it as 12 when the band stopped at x+28), T2's 1000, and T2's 46 with the NEXT slot's
    4-digit count spilling into its band at x+33."""
    c = bc.count_of_runs
    assert c([(15, 19, "1"), (21, 26, "2"), (28, 33, "3")]) == 123
    assert c([(1, 5, "1"), (7, 12, "0"), (14, 19, "0"), (21, 26, "0")]) == 1000
    assert c([(14, 19, "4"), (21, 26, "6"), (33, 37, "1"), (39, 44, "0")]) == 46
    assert c([(14, 19, "8")]) == 8 and c([(15, 19, "1")]) == 1
    # a 4-digit count with its first digit covered: the rest touches it, so unread (never 234)
    assert c([(7, 12, "2"), (14, 19, "3"), (21, 26, "4")]) is None
    assert c([(3, 5, None), (7, 12, "2"), (14, 19, "3"), (21, 26, "4")]) is None
    # a 3-digit count cut by something at its end, or a stray glyph: unread
    assert c([(15, 19, "1"), (21, 26, "2"), (28, 31, None)]) is None
    assert c([(14, 19, "0"), (21, 26, "7")]) is None  # a leading zero


def test_a_three_digit_count_touching_a_four_digit_neighbour_is_unread() -> None:
    """The client draws a 3-digit count to x+33 and the next slot's 4-digit count from its x+1
    (our x+33): they touch, so both are unread -- never a shorter number for either."""
    font, icons = _font(), _icons(3)
    refs = _refs(icons)
    ids = list(icons)
    tab = _read(_frame([(ids[0], 588), (ids[1], 1234), (ids[2], 5)], icons, font), refs, font)
    assert [b.slot for b in tab.unread()] == [0, 1]
    assert [(b.ids, b.count) for b in tab.items()] == [((ids[2],), 5)]
