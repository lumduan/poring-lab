"""scripts/bag_count.py (docs/planning/econ-bag-count.md): the bag found by its oval lattice (its
rows too: 7 x 6 by default, taller when the player drags it), the items by their icons over this
client's own empty slot, the counts by their pure-black digits, and the pre-registered bar.
Synthetic frames only (no client pixels)."""

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
    rows: int = 6,
    canvas: tuple[int, int] = (1080, 1920),
    count_dx: int = 0,
) -> np.ndarray:
    """A BGR frame (``canvas``: h, w) with a 7 x ``rows`` bag at ``origin``: ``items`` (id, count)
    in reading order, then empty slots (white face, the oval). ``count_dx``: every count drawn
    this many px right of the lab's place (Batt's live client: -2)."""
    f = np.full((*canvas, 3), 90, np.uint8)
    ox, oy = origin
    ww, wh = bc.window_size(rows)
    f[oy : oy + wh, ox : ox + ww] = 255
    oval = _oval()
    for s in range(bc.COLS * rows):  # every slot's oval first (drawn behind items too)
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
        left = x + 14 + (1 if text[0] == "1" else 0) + count_dx
        cx = left if len(text) <= 3 else x + 26 - width + 1 + count_dx
        for ch in text:
            g = font[ch]
            f[y + bc.COUNT_DY : y + bc.COUNT_DY + 9, cx : cx + g.shape[1]][g] = 0
            cx += g.shape[1] + 1
    return f


def _refs(icons: dict[int, np.ndarray]) -> si.SlotRefs:
    return si.SlotRefs.from_icons(icons, {k: f"item {k}" for k in icons})


def _read(f: np.ndarray, refs: si.SlotRefs, font: dict[str, np.ndarray]) -> bc.TabRead:
    bag = bc.find_bag(f)
    assert bag is not None
    empty = bc.empty_picture(f, bag.origin, rows=bag.rows)
    assert empty is not None
    pics = bc.Pictures.over(refs, empty)
    return bc.TabRead("t", bc.read_tab(f, bag.origin, pics, empty, font, rows=bag.rows))


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
    full = _frame([(ids[k % 45], 1) for k in range(bc.COLS * 6)], icons, font)
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
    empty = bc.empty_picture(_frame([(ids[0], 2)], icons, font), ORIGIN, rows=6)
    assert empty is not None
    slots = bc.read_tab(f, ORIGIN, bc.Pictures.over(refs, empty), empty, font, rows=6)
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


# --- a taller window (Batt's live bag is 7 x 9, 2026-11-21): the rows are read, never assumed -----
def _counts(n: int) -> list[int]:
    """n stack counts of 1-3 digits that the measured shapes read: no '1' after the first digit
    (the test font's '1' is a column narrower; count_of_runs' shapes allow that for a LEADING '1'
    only, the client's measured place)."""
    out = [v for v in range(2, 999, 23) if "1" not in str(v)[1:]]
    return out[:n]


def _hider(seed: int = 3) -> np.ndarray:
    """An item bitmap with NO key colour over the oval's box (dark, opaque): a slot that shows no
    oval at all, the worst case for the rows rule."""
    a = np.random.default_rng(seed).integers(20, 150, size=(24, 24, 3)).astype(np.uint8)
    a[:3] = (255, 0, 255)  # some key colour (a real bitmap's) away from the oval
    return a


@pytest.mark.parametrize("rows", [6, 7, 9, 12])
def test_a_bag_is_found_with_its_rows_whatever_fills_it(rows: int) -> None:
    """The title bar above row 0 shows no slot, every row of the window does: the rows are the
    window's, also when its first rows are full of items (a 7 x 6 placement three rows down would
    fit the ovals alone: the old rule's silent wrong place)."""
    font, icons = _font(), _icons(90)
    ids = list(icons)
    slots = bc.COLS * rows
    for n in (0, 1, 6, 7, 20, 21, 35, slots - 2):
        f = _frame([(ids[k], 1) for k in range(n)], icons, font, rows=rows)
        assert bc.find_bag(f) == bc.Bag(ORIGIN, rows), (rows, n)
        assert bc.find_window(f) == ORIGIN and bc.rows_at(f, ORIGIN) == rows
        assert bc.window_at(f, ORIGIN, rows) and bc.window_at(f, ORIGIN)
        assert not bc.window_at(f, ORIGIN, rows + 1) and not bc.window_at(f, ORIGIN, rows - 1)
        assert not bc.window_at(f, (ORIGIN[0] + bc.PITCH, ORIGIN[1]))  # a column off
        assert not bc.window_at(f, (ORIGIN[0], ORIGIN[1] + bc.PITCH))  # a row off
        lower = (ORIGIN[0], ORIGIN[1] + bc.PITCH * (rows - 6))  # the 7 x 6 placement at its foot
        assert rows == 6 or not bc.window_at(f, lower, 6)
    # one slot left: below LATTICE_MIN ovals, no bag (as at 7 x 6)
    f = _frame([(ids[k], 1) for k in range(slots - 1)], icons, font, rows=rows)
    assert bc.find_bag(f) is None and bc.window_at(f, ORIGIN, rows)


def test_a_7x9_bag_reads_every_item_and_count() -> None:
    font, icons = _font(), _icons(40)
    refs = _refs(icons)
    ids = list(icons)
    items = list(zip(ids[:30], _counts(29) + [7], strict=True))  # rows 0-3 full, row 4 two items
    # (the last one short: a 3-digit count reaches x+33, into the next (empty) square: unread)
    f = _frame(items, icons, font, rows=9)
    tab = _read(f, refs, font)
    assert len(tab.slots) == 63 and not tab.unread() and not tab.full
    assert [(b.ids, b.count) for b in tab.items()] == [((iid,), n) for iid, n in items]
    assert [b.slot for b in tab.slots if b.kind == "empty"] == list(range(30, 63))
    assert bc.grid_signature(f, ORIGIN, rows=9).shape == (63, 3)
    x, y = bc.icon_xy(ORIGIN, 62)  # the last slot: row 8, column 6
    assert (x, y) == (
        ORIGIN[0] + bc.ICON0[0] + 6 * bc.PITCH,
        ORIGIN[1] + bc.ICON0[1] + 8 * bc.PITCH,
    )


def test_a_bag_taller_than_the_frame_or_rows_max() -> None:
    """A bag cut by the frame's bottom edge is found with the rows the frame shows, at its TRUE
    origin: its hidden rows come after an empty slot it shows, so they are empty (items fill a tab
    in reading order) and the count is exact. Fewer than ROWS_MIN rows shown, or a window taller
    than ROWS_MAX: no bag (never a guessed part of one)."""
    font, icons = _font(), _icons(12)
    refs = _refs(icons)
    ids = list(icons)
    items = list(zip(ids, _counts(12), strict=True))
    oy = 1080 - (bc.ICON0[1] + bc.OVAL_BOX[1] + bc.OVAL_BOX[3] + bc.PITCH * 5)  # row 5's box fits
    tall = _frame(items, icons, font, origin=(300, oy), rows=9, canvas=(1500, 1920))
    cut = np.ascontiguousarray(tall[:1080])
    assert bc.find_bag(cut) == bc.Bag((300, oy), 6)
    assert bc.find_bag(tall) == bc.Bag((300, oy), 9)
    tab = _read(cut, refs, font)
    assert [(b.ids, b.count) for b in tab.items()] == [((iid,), n) for iid, n in items]
    assert bc.find_bag(np.ascontiguousarray(tall[: 1080 - bc.PITCH])) is None  # 5 rows shown
    big = _frame(items, icons, font, rows=bc.ROWS_MAX + 1, canvas=(1500, 1920))
    assert bc.find_bag(big) is None and bc.rows_at(big, ORIGIN) is None
    assert bc.find_bag(_frame(items, icons, font, rows=bc.ROWS_MAX, canvas=(1500, 1920))) == (
        bc.Bag(ORIGIN, bc.ROWS_MAX)
    )


def test_a_new_items_glow_shows_its_slot() -> None:
    """A NEW item draws a pink glow where the oval was: its slot still shows (a row of new
    items, a Run's loot at its end census, keeps the window's rows)."""
    font, icons = _font(), _icons(30)
    ids = list(icons)
    f = _frame([(ids[k], 1) for k in range(21)], icons, font, rows=9)
    glow = np.array([247, 150, 255], np.uint8)  # BGR of (255, 150, 247)
    for s in range(14, 21):  # row 2: seven new items, their ovals turned pink
        x, y = bc.icon_xy(ORIGIN, s)
        dx, dy, w, h = bc.OVAL_BOX
        box = f[y + dy : y + dy + h, x + dx : x + dx + w]
        oval = np.all(box == np.asarray(bc.OVAL[::-1], np.uint8), axis=2)
        box[oval] = glow
    assert bc.find_bag(f) == bc.Bag(ORIGIN, 9)


def test_a_row_that_hides_every_oval_cuts_the_window_and_the_census_check_sees_it() -> None:
    """A row whose seven icons all hide the oval shows no slot, so the window's top is found below
    it: on a 7 x 6 bag that leaves fewer than ROWS_MIN rows (no bag: a clear failure); on a taller
    bag this one frame cannot tell it from the title bar (a known limit: ~1e-9 for a row of real
    icons). The census reads four tabs at the found place and checks each one (window_at with the
    rows): another tab shows that row's slots, so the found place fails there and find_bag finds
    the true window -- the census stops ("the bag moved"), never reads a wrong place."""
    font, icons = _font(), _icons(40)
    hider = _hider()
    icons[999] = hider
    ids = [i for i in icons if i != 999]
    # 7 x 6: row 2 (slots 14-20) hides every oval
    items6 = [(ids[k] if not 14 <= k < 21 else 999, 1) for k in range(25)]
    assert bc.find_bag(_frame(items6, icons, font)) is None
    # 7 x 9: the same row 2 -> the 6 rows below it look like a whole window
    items9 = [(ids[k] if not 14 <= k < 21 else 999, 1) for k in range(25)]
    one_tab = _frame(items9, icons, font, rows=9)
    wrong = bc.find_bag(one_tab)
    assert wrong == bc.Bag((ORIGIN[0], ORIGIN[1] + 3 * bc.PITCH), 6)
    other_tab = _frame([(ids[k], 1) for k in range(5)], icons, font, rows=9)
    assert not bc.window_at(other_tab, wrong.origin, wrong.rows)
    assert bc.find_bag(other_tab) == bc.Bag(ORIGIN, 9) != wrong


def _thin() -> np.ndarray:
    """A THIN item bitmap (a tooth, a talon, a sword): a 2 px stroke over the key colour, so its
    cell still shows >= OVAL_SHARE of the oval."""
    a = np.zeros((24, 24, 3), np.uint8)
    a[..., 0] = a[..., 2] = 255  # the key colour
    a[2:22, 11:13] = (40, 90, 160)
    return a


def test_a_thin_icon_is_an_item_not_a_hole_before_the_tail() -> None:
    """A thin icon leaves the oval showing, but every item shows a count: find_bag takes its cell
    for an item, so the bag is found at its exact place and read whole (the oval rule alone saw a
    hole before the empty tail: no bag there, or one a few pixels off). rows_at keeps the oval
    rule (a pointer may rest on the bag where it looks); the census falls back to find_bag."""
    font, icons = _font(), _icons(10)
    icons[2000] = _thin()
    refs = _refs(icons)
    ids = list(icons)[:10]
    items = [(ids[0], 3), (2000, 1), (ids[1], 46), (ids[2], 7)]
    f = _frame(items, icons, font, rows=9)
    x, y = bc.icon_xy(ORIGIN, 1)
    assert bc.oval_share(bc.square(f, ORIGIN, 1)) >= bc.OVAL_SHARE  # the oval shows through it
    assert bc.find_bag(f) == bc.Bag(ORIGIN, 9)
    assert not bc.window_at(f, ORIGIN, 9)  # the oval rule alone: a hole before the tail
    tab = _read(f, refs, font)
    assert [(b.ids, b.count) for b in tab.items()] == [((iid,), n) for iid, n in items]
    assert not tab.unread()
    # its count is what tells it from an empty slot: with an empty cell's pixels where its digits
    # were, it is a hole before the tail again
    ex, ey = bc.icon_xy(ORIGIN, 62)
    rows, cols = slice(bc.COUNT_DY, bc.COUNT_DY + bc.COUNT_ROWS), slice(14, 27)
    f[y + rows.start : y + rows.stop, x + cols.start : x + cols.stop] = f[
        ey + rows.start : ey + rows.stop, ex + cols.start : ex + cols.stop
    ]
    assert bc.find_bag(f) != bc.Bag(ORIGIN, 9)


# --- 2026-11-23: Batt's live client (a 7 x 10 bag, its counts 2 px left, taller tabs) ------------


# (a count drawn RIGHT of the lab's place would reach into the next slot's icon, where the shapes
# rightly refuse it: no client seen does that; Batt's draws them 2 px left)
@pytest.mark.parametrize("dx", [0, -1, -2])
def test_a_client_whose_counts_sit_elsewhere_is_learned_from_its_own_counts(dx: int) -> None:
    """Batt's live client draws every count 2 px LEFT of the lab's ("89" at x+12, a leading '1' at
    x+13): the census learns the shift from the tab's own clean counts and reads them all."""
    font, icons = _font(), _icons(45)
    ids = list(icons)
    stacks = [(ids[k], n) for k, n in enumerate([89, 1, 304, 120, 506, 194, 24, 44, 15, 5, 1000])]
    f = _frame(stacks, icons, font, rows=10, count_dx=dx)
    origin = bc.find_window(f)
    assert origin == ORIGIN
    sh, votes = bc.count_shift(f, origin, range(bc.COLS * 10), font)
    assert sh == -dx and votes >= bc.COUNT_SHIFT_VOTES
    empty = bc.empty_picture(f, origin, rows=10)
    assert empty is not None
    pics = bc.Pictures.over(_refs(icons), empty)
    tab = bc.TabRead("t", bc.read_tab(f, origin, pics, empty, font, rows=10, shift=sh))
    assert [b.count for b in tab.items()] == [n for _i, n in stacks]
    if dx:  # the lab's own shapes (no shift) read none of them: the old live result
        old = bc.TabRead("t", bc.read_tab(f, origin, pics, empty, font, rows=10))
        assert old.items() == [] and len(old.unread()) == len(stacks)


def test_the_count_shift_needs_agreeing_counts() -> None:
    assert bc.shift_of([]) is None and bc.shift_of([(3, 8, None)]) is None
    assert bc.shift_of([(12, 17, "8"), (19, 24, "9")]) == 2  # Batt's "89"
    assert bc.shift_of([(13, 17, "1")]) == 2  # a leading '1' one column in
    assert bc.shift_of([(14, 19, "3")]) == 0  # the lab's
    font, icons = _font(), _icons(5)
    one = _frame([(list(icons)[0], 7)], icons, font, count_dx=-2)  # a single count: one vote
    assert bc.count_shift(one, ORIGIN, range(bc.COLS * 6), font) == (0, 0)


def test_a_taller_window_stretches_its_tabs() -> None:
    """The lab's 7 x 6 keeps its measured tabs; Batt's 7 x 10 (centres measured ~61 / 144 / 227 /
    310, each ~83 px tall) is clicked inside each of its tabs."""
    assert {n: bc.tab_xy(n, 6) for n in bc.TABS} == bc.TABS
    measured = {"use": (20, 100), "eqp": (102, 185), "etc": (187, 267), "fav": (270, 352)}
    for n, (y0, y1) in measured.items():
        x, y = bc.tab_xy(n, 10)
        assert x == 10 and y0 + 8 <= y <= y1 - 8, (n, y)
    ys = [bc.tab_xy(n, 12)[1] for n in bc.TABS]
    assert ys == sorted(ys) and ys[-1] < bc.ICON0[1] + bc.PITCH * 12 + bc.TAB_BOTTOM_PAD
