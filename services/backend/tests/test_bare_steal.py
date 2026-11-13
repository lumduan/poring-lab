"""bare_steal (rogue-xmas02.md 4BX, dungeon@9.27): Batt's bare-hand steal -- the language-free steal
cues (the item popup by its frame, a new item-colour Battle Log line) and the phase's state."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def bs() -> ModuleType:
    path = ROOT / "scripts/bare_steal.py"
    spec = importlib.util.spec_from_file_location("bare_steal", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bare_steal"] = mod
    spec.loader.exec_module(mod)
    return mod


def scene(v: int = 120) -> np.ndarray:
    return np.full((720, 1280, 3), v, np.uint8)


def draw_popup(img: np.ndarray, bs: ModuleType, width: int = 188, ink: int = 40) -> np.ndarray:
    """The popup as measured on fiT14: a 2-px white border column at the left edge, a grey inner
    line, white top / bottom border rows from left + 3 (rounded corners), a white fill with an
    icon and text (dark marks; never read)."""
    x0, t, b = bs.POPUP_LEFT, bs.POPUP_TOP, bs.POPUP_BOTTOM
    x1 = x0 + width - 1
    img[t + 2 : b - 1, x0 : x0 + 2] = 255
    img[t + 2 : b - 1, x0 + 2] = 190
    img[t + 2 : b - 1, x0 + 3 : x1 - 1] = 254
    img[t, x0 + 3 : x1 - 1] = 255
    img[b, x0 + 3 : x1 - 1] = 255
    img[t + 8 : t + 22, x0 + 8 : x0 + 22] = ink  # the item's icon
    img[t + 10 : t + 20, x0 + 30 : x0 + 30 + width // 2 : 3] = ink  # its text, as strokes
    return img


def test_the_popup_is_found_by_its_frame_at_its_fixed_place(bs: ModuleType) -> None:
    for w in (150, 188, 230):
        box = bs.popup_box(draw_popup(scene(), bs, w))
        assert box is not None and box[0] == bs.POPUP_LEFT
        assert abs((box[1] - box[0] + 1) - w) <= 2
    assert bs.popup_box(scene()) is None  # no popup
    assert bs.popup_box(scene(255)) is None  # a white scene: no border column, no edges


def test_a_white_patch_elsewhere_or_without_its_edges_is_no_popup(bs: ModuleType) -> None:
    moved = scene()
    moved[bs.POPUP_TOP : bs.POPUP_BOTTOM + 1, 600:800] = 255  # white, but not at the fixed left
    assert bs.popup_box(moved) is None
    no_bottom = draw_popup(scene(), bs)
    no_bottom[bs.POPUP_BOTTOM - 1 : bs.POPUP_BOTTOM + 1] = 120  # the bottom border hidden
    assert bs.popup_box(no_bottom) is None


def test_a_popup_is_new_once_and_again_only_with_other_contents(bs: ModuleType) -> None:
    a = draw_popup(scene(), bs, 188)
    new, box, sig = bs.popup_new(None, None, a)
    assert new and box is not None and sig is not None
    jitter = draw_popup(scene(), bs, 190)  # the same popup, its right end 2 px off
    jitter[bs.POPUP_TOP + 8 : bs.POPUP_TOP + 22, bs.POPUP_LEFT + 8 : bs.POPUP_LEFT + 22] = 40
    assert not bs.popup_new(sig, box, jitter)[0]
    other = draw_popup(scene(), bs, 240, ink=150)  # another item: another icon, a longer name
    assert bs.popup_new(sig, box, other)[0]
    assert not bs.popup_new(None, None, scene())[0]


def test_the_battle_log_cue_is_a_new_line_of_the_item_colour_not_its_words(bs: ModuleType) -> None:
    lines = [{"colour": "yellow", "text": "x"}, {"colour": "cyan", "text": None}]
    assert bs.cyan_new(lines, 1)
    assert not bs.cyan_new(lines, 2)
    assert not bs.cyan_new([{"colour": "yellow"}, {"colour": "red"}], 0)


def test_the_phase_unequips_once_then_equips_on_a_cue_a_timeout_or_low_hp(bs: ModuleType) -> None:
    st = bs.BareSteal()
    assert st.engage() == "unequip"
    st.unequipped(10.0, n_lines=3, sig=None, box=None)
    assert st.engage() is None  # bare already
    quiet = [{"colour": "yellow"}] * 3
    assert st.tick(11.0, quiet, scene(), 0.9) == (None, None)
    assert st.tick(11.5, [*quiet, {"colour": "cyan"}], scene(), 0.9) == ("equip", "cyan")
    st.equipped()
    assert st.engage() is None  # this fight stole: no second bare phase
    st.fight_end()
    assert st.engage() == "unequip"  # the next target
    st.unequipped(20.0, n_lines=0, sig=None, box=None)
    assert st.tick(20.5, [], draw_popup(scene(), bs), 0.9) == ("equip", "popup")
    st.equipped()
    st.fight_end()
    st.unequipped(30.0, n_lines=0, sig=None, box=None)
    assert st.tick(30.5, [], scene(), 0.4) == ("equip", "hp")
    st.equipped()
    st.fight_end()
    st.unequipped(40.0, n_lines=0, sig=None, box=None)
    assert st.tick(40.0 + bs.BARE_MAX_S, [], scene(), 0.9) == ("equip", "time")


def test_bare_with_no_phase_waits_for_the_first_strike_to_begin_one(bs: ModuleType) -> None:
    """dungeon@9.27b (--bare-ready): the dagger off while idle, or a fight ended bare -- no cue,
    no BARE_MAX_S, no HP rule in the pure phase until ``begin`` (the first bare strike)."""
    st = bs.BareSteal()
    st.wait_bare()  # the idle unequip
    assert not st.armed and st.t_bare is None and st.engage() is None  # no swap: bare already
    lines = [{"colour": "cyan"}] * 2  # the loot step's item lines
    assert st.tick(99.0, lines, draw_popup(scene(), bs), 0.3) == (None, None)
    st.begin(100.0, n_lines=2, sig=None, box=None)
    assert st.t_bare == 100.0 and st.n_lines0 == 2 and not st.armed
    assert st.tick(100.5, lines, scene(), 0.9) == (None, None)  # the old lines are no cue
    assert st.tick(100.0 + bs.BARE_MAX_S, lines, scene(), 0.9) == ("equip", "time")
    st.begin(200.0, n_lines=2, sig=None, box=None)
    assert st.tick(200.5, [*lines, {"colour": "cyan"}], scene(), 0.9) == ("equip", "cyan")
    st.fight_end()
    st.wait_bare()  # the target died bare: the phase ends, she stays bare
    assert not st.armed and st.t_bare is None and st.popup_box0 is None
    assert st.tick(300.0, [], scene(), 0.9) == (None, None)


def test_a_popup_still_shown_from_before_the_bare_phase_is_no_cue(bs: ModuleType) -> None:
    """A loot popup from the last fight may still show when the bare phase begins: only a NEW
    one (other contents) is a steal."""
    old = draw_popup(scene(), bs, 188)
    _, box, sig = bs.popup_new(None, None, old)
    st = bs.BareSteal()
    st.unequipped(0.0, n_lines=0, sig=sig, box=box)
    assert st.tick(0.5, [], old, 0.9) == (None, None)
    assert st.tick(1.0, [], scene(), 0.9) == (None, None)  # it faded
    assert st.tick(1.5, [], old, 0.9) == ("equip", "popup")  # drawn again: a new gain


REC = Path("/mnt/poring-lab-datasets/20261111T132013-rdp-hunt-xmas02-fiT14")


@pytest.mark.skipif(not REC.exists(), reason="the p63 recording is not mounted")
def test_a_real_steal_frame_shows_the_popup_and_the_frame_before_does_not(bs: ModuleType) -> None:
    """The real case (fiT14 = p63): the first steal (a pickup_result with no pickup_request, at
    t_mono 342928646027850) is drawn on frame 61 (0.13 s later) and not on frame 60."""
    import io
    import tarfile

    from PIL import Image

    with tarfile.open(REC / "shard-000000.tar") as tf:
        before = np.asarray(Image.open(io.BytesIO(tf.extractfile("000000060.png").read()))  # type: ignore[union-attr]
                            .convert("RGB"))  # fmt: skip
        after = np.asarray(Image.open(io.BytesIO(tf.extractfile("000000061.png").read()))  # type: ignore[union-attr]
                           .convert("RGB"))  # fmt: skip
    assert bs.popup_box(after) is not None
    assert bs.popup_box(before) is None


# --- the weapon state readout: the F5 slot (dungeon@9.27; the parent's live finding 2026-11-11:
# the slot draws the dagger only while it is in the bag) ------------------------------------------


def hotbar(bag: bool = False, noise: int = 0, seed: int = 0) -> np.ndarray:
    """A game-region frame's hotbar: white slots (hotbar_count: an empty slot is white, its frame
    ~192), the dagger's icon in slot 4 while it is in the BAG (a thin blade: 6 x 10 dark px in the
    24 x 17 icon box), optional codec noise."""
    img = np.full((40, 600, 3), 120, np.int16)
    img[3:34, 240:520] = 235
    for k in range(9):  # each slot's frame line
        img[3:34, 245 + 29 * k] = 192
    if bag:
        x0 = 246 + 29 * 4 + 9
        img[8:18, x0 : x0 + 6] = 60
    if noise:
        img += np.random.default_rng(seed).integers(-noise, noise + 1, img.shape).astype(np.int16)
    return np.clip(img, 0, 255).astype(np.uint8)


def test_the_f5_slot_reads_armed_bare_or_unreadable_against_its_armed_reference(
        bs: ModuleType) -> None:  # fmt: skip
    worn = bs.slot_gray(hotbar())
    assert bs.slot_empty(worn)  # hotbar_count's rule: no icon, no digit = the dagger worn
    ref = bs.slot_crop(worn)
    assert ref.shape == (17, 24)
    assert bs.slot_bare(bs.slot_crop(bs.slot_gray(hotbar(noise=6, seed=1))), ref) is False
    bag = bs.slot_gray(hotbar(bag=True))
    assert not bs.slot_empty(bag)
    assert bs.slot_bare(bs.slot_crop(bag), ref) is True
    noisy_bag = bs.slot_crop(bs.slot_gray(hotbar(bag=True, noise=6, seed=2)))
    assert bs.slot_bare(noisy_bag, ref) is True
    dark = np.full((40, 600, 3), 10, np.uint8)  # a teleport's dark frame: no hotbar drawn
    assert bs.slot_bare(bs.slot_crop(bs.slot_gray(dark)), ref) is None
    assert bs.slot_bare(ref[:5], ref) is None  # another shape: unreadable, never a guess
    # the numbers behind SLOT_PX / SLOT_SHARE (the comment at the constants)
    st_noise = bs.slot_stats(bs.slot_crop(bs.slot_gray(hotbar(noise=6, seed=3))), ref)
    st_bag = bs.slot_stats(bs.slot_crop(bag), ref)
    assert st_noise["changed"] == 0.0 and st_bag["changed"] == round(60 / 408, 3)
    assert st_bag["changed"] / 2.5 >= bs.SLOT_SHARE and st_bag["diff"] < 30  # a mean misses it
    assert (bs.SLOT_PX, bs.SLOT_SHARE, bs.SLOT_DARK) == (40.0, 0.05, 40.0)


def two_slots(dagger_bag: bool, opener_bag: bool, noise: int = 0, seed: int = 0,
              count: bool = False) -> np.ndarray:  # fmt: skip
    """--steal-opener's hotbar (dungeon@9.27c): the dagger's icon on F5 (slot 4) while it is in the
    bag, the opener's (a Knife: 8 x 6 dark px) on F4 (slot 3) while it is in the bag; ``count``
    draws a stack's digit in F4's count box instead (not a weapon)."""
    img = hotbar(bag=dagger_bag, noise=0).astype(np.int16)
    x0 = 246 + 29 * 3
    if opener_bag:
        img[9:15, x0 + 8 : x0 + 16] = 50
    if count:
        img[9:15, x0 + 8 : x0 + 16] = 50
        img[25:32, 259 + 29 * 3 + 8 : 259 + 29 * 3 + 10] = 0  # a black "1"
    if noise:
        img += np.random.default_rng(seed).integers(-noise, noise + 1, img.shape).astype(np.int16)
    return np.clip(img, 0, 255).astype(np.uint8)


def test_the_opener_and_the_dagger_slots_read_as_one_weapon_state(bs: ModuleType) -> None:
    """dungeon@9.27c: a worn item's icon is not drawn, so the dagger worn = F5 empty and the
    opener in the bag = its icon on F4 (the run's start), and the opener worn = F4 empty and the
    dagger's icon on F5."""
    start = bs.slot_gray(two_slots(False, True))
    ref5, refk = bs.slot_crop(start), bs.slot_crop(start, 3)
    assert bs.slot_empty(start) and not bs.slot_empty(start, 3) and not bs.slot_counted(start, 3)

    def state(img: np.ndarray) -> str | None:
        g = bs.slot_gray(img)
        return bs.weapon_state(bs.slot_bare(bs.slot_crop(g), ref5), bs.opener_worn(g, 3, refk))

    assert state(two_slots(False, True)) == "armed"
    assert state(two_slots(False, True, noise=6, seed=4)) == "armed"
    assert state(two_slots(True, False)) == "opener"  # the Knife worn, the dagger in the bag
    assert state(two_slots(True, False, noise=6, seed=5)) == "opener"
    assert state(two_slots(True, True)) == "bare"  # both in the bag
    assert state(two_slots(False, False)) == "odd"  # both slots empty: cannot be
    assert state(np.full((40, 600, 3), 10, np.uint8)) is None  # dark: unreadable
    other = two_slots(False, False)
    other[6:20, 246 + 29 * 3 + 2 : 246 + 29 * 3 + 20] = 90  # ANOTHER icon on F4: neither
    assert bs.opener_worn(bs.slot_gray(other), 3, refk) is None and state(other) is None
    assert bs.slot_counted(bs.slot_gray(two_slots(False, False, count=True)), 3)
    assert [bs.weapon_state(a, b) for a, b in ((None, True), (True, None))] == [None, None]
    assert bs.OPENER_VERSION == "9.27c"


def test_the_swap_geometry_is_the_live_measurement(bs: ModuleType) -> None:
    """The parent's live numbers (2026-11-11): the equipment window at home (185, 300), its
    weapon slot at window (18, 102) = game-region (203, 402), the dagger on F5 = hotbar slot 4."""
    assert bs.EQUIP_WINDOW == "equipment" and bs.EQUIP_HOME == (185, 300)
    (hx, hy), (sx, sy) = bs.EQUIP_HOME, bs.WEAPON_SLOT
    assert (hx + sx, hy + sy) == (203, 402)
    assert (bs.EQUIP_KEY, bs.EQUIP_SLOT) == ("F5", 4)
    assert (bs.OPEN_S, bs.LATE_S, bs.OFF_S, bs.CLOSE_S, bs.ON_S) == (1.2, 0.8, 1.0, 1.0, 0.8)
    assert bs.POLL_S == 0.1
    assert bs.FAIL_STOP == 3


def test_the_popup_only_cue_ignores_the_battle_log(bs: ModuleType) -> None:
    """dungeon@9.27d (--steal-cue popup, rogue-xmas02.md 4CE): a new cyan line is no cue (p69:
    57 % of cyan equips had no steal: old lines re-read); a new popup still is."""
    st = bs.BareSteal(cue="popup")
    st.unequipped(0.0, n_lines=0, sig=None, box=None)
    assert st.tick(0.5, [{"colour": "cyan"}], scene(), 0.9) == (None, None)
    assert st.tick(1.0, [{"colour": "cyan"}], draw_popup(scene(), bs), 0.9) == ("equip", "popup")
    assert bs.BareSteal().cue == "both" and bs.STEAL_CUES == ("both", "popup")


# --- dungeon@9.42 (Batt 2026-11-13: "everything a user can set again; we only put the defaults") --
def test_configure_sets_the_runs_own_dagger_key_and_knife_numbers(bs: ModuleType) -> None:
    """The defaults stay the module's; a run's configure() moves the dagger's key AND the slot its
    picture is read from (read at call time: a default argument bound at import would not)."""
    gray = np.full((720, 1280), 255.0)
    gray[0:10, 0:10] = 0.0
    before = bs.slot_crop(gray).copy()
    prev = bs.configure("F7", 0.2, 0.35)
    try:
        assert (bs.EQUIP_KEY, bs.EQUIP_SLOT, bs.BARE_MAX_S, bs.BARE_HP_MIN) == ("F7", 6, 0.2, 0.35)
        assert np.array_equal(bs.slot_crop(gray), bs.slot_crop(gray, 6))  # the new slot, by default
        st = bs.BareSteal()
        st.wait_bare()
        st.begin(10.0, n_lines=0, sig=None, box=None)
        assert st.tick(10.1, [], scene(), 0.9) == (None, None)
        assert st.tick(10.25, [], scene(), 0.9) == ("equip", "time")  # Batt's "wait 200 ms"
        st.begin(20.0, n_lines=0, sig=None, box=None)
        assert st.tick(20.05, [], scene(), 0.3) == ("equip", "hp")  # under the person's 35 %
    finally:
        bs.configure(**prev)
    assert (bs.EQUIP_KEY, bs.EQUIP_SLOT, bs.BARE_MAX_S, bs.BARE_HP_MIN) == ("F5", 4, 8.0, 0.5)
    assert np.array_equal(bs.slot_crop(gray), before)
    assert "row-1" in str(bs.configure_refused("F10"))
    assert "outside" in str(bs.configure_refused(None, 0.1))
    assert "outside" in str(bs.configure_refused(None, 25.0))
    assert "outside" in str(bs.configure_refused(None, None, 0.95))
    assert bs.configure_refused("F1", 0.2, 0.2) is None and bs.configure_refused() is None
    with pytest.raises(ValueError):
        bs.configure(None, 30.0)
