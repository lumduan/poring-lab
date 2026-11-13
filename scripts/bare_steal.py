#!/usr/bin/env python3
"""Batt's BARE-HAND STEAL technique for the Rogue (2026-11-11, rogue-xmas02.md 4BX; dungeon@9.27):
Snatcher (RG_SNATCHER Lv 10) steals on the Rogue's melee hits. Bare hands hit faster and weaker
than the dagger, so the monster lives long enough for a steal; once a steal SUCCEEDS the dagger
goes back on at once (its hotkey), and the kill is finished with it.

    on a new target, armed  -> UNEQUIP: Alt+Q (the equipment window), a double-click on the
                               weapon slot, Alt+Q again (Batt's way), each step read back;
    bare, a steal cue        -> EQUIP: the dagger's hotkey (F5 by default: Batt's example);
    bare, no cue in time     -> EQUIP anyway (BARE_MAX_S), or at once when the HP falls under
                               BARE_HP_MIN (bare hands kill slowly; she must not die for a steal).

THE CUES ARE LANGUAGE-FREE (Batt 2026-11-11: "do not fix anything to English only: dev servers in
Thai and Korean are coming"; also feedback-no-english-text-cues, 10-26). Neither reads a word:
- the POPUP: the client's item-obtained box, a white rounded box at a FIXED place (measured on the
  p63 recording fiT14, 2026-11-11: rows 76-105 of the 1280 x 720 game region, its left edge at
  x 541 on every frame, its width 183-198 px with the item's name); only its presence and its
  contents' change are read, never its text;
- the BATTLE LOG: a NEW line of the item-gain colour (cyan, battle_log.colour_of: pixels) after
  the bare phase began. In the bare phase she clicks no loot, so an item gained then is a steal
  (p63: all 38 item gains with no pickup request of ours were steals, each with one cyan line
  within 0.13 s and the popup).
Offline, the packets judge every cue (a pickup_result with no pickup_request of ours = a steal).

Two variants (dungeon_hunt.py, both OFF by default):
- 9.27b --bare-ready (Batt 2026-11-11 after p65 / p66): the dagger comes off while IDLE (after the
  loot), so a new target is struck bare at once: BareSteal.wait_bare, then begin at that strike;
- 9.27c --steal-opener KEY: a weak opener weapon (a Knife) on hotbar KEY instead of bare hands --
  its key puts it on, F5 the dagger back; the two slots read together (weapon_state).

Everything here is PURE (no input, no grabs): the runner (dungeon_hunt.py) does the clicks.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hotbar_count as hb  # noqa: E402 -- the hotbar's calibrated slot boxes (pure, numpy only)

BARE_STEAL_VERSION = "9.27"
STEAL_CUES = ("both", "popup")  # dungeon@9.27d (--steal-cue)

# The item-obtained popup (game-region px; fiT14 frames 61-64, 103-106, 135-138, 2026-11-11)
POPUP_TOP, POPUP_BOTTOM = 76, 105  # its white rows, inclusive
POPUP_LEFT = 541  # its left edge: the same on every frame (the width follows the text)
POPUP_LEFT_TOL = 2
POPUP_MIN_W, POPUP_MAX_W = 60, 520
POPUP_WHITE = 245.0  # luma of its fill (255 on the frames; the text and the icon are darker)
POPUP_FILL_SHARE = 0.55  # of a white column's rows: the text and the icon leave gaps
POPUP_SIG = (POPUP_LEFT + 4, POPUP_TOP + 3, POPUP_LEFT + 180, POPUP_BOTTOM - 3)  # x0, y0, x1, y1
POPUP_CHANGE = 12.0  # mean abs luma difference of the signature crop: new contents
POPUP_WIDTH_TOL = 4  # px: a width change above this is a new popup (another name)

ITEM_COLOUR = "cyan"  # battle_log.colour_of's class of the item-gain line (p63: 81 of 81)

BARE_MAX_S = 8.0  # bare-handed this long with no steal cue: the dagger goes on anyway
BARE_HP_MIN = 0.5  # HP share under which the dagger goes on at once
EQUIP_KEY = "F5"  # the hotbar slot holding the dagger (Batt: "any free F1-F9, e.g. F5")
EQUIP_SLOT = 4  # hotbar row 1 index of EQUIP_KEY (F1 = 0)
# The DEFAULTS above; a run sets its own with configure() (Batt 2026-11-13: "everything a user can
# set again; we only put the defaults"): the dagger's key, the Knife's time, the HP rule.
KNIFE_MAX_RANGE = (0.2, 20.0)  # s: --knife-max-s (Batt's example "F4, wait 200 ms, F5" = 0.2)
KNIFE_HP_RANGE = (0.2, 0.9)  # HP share: --knife-hp-min


def configure_refused(equip_key: str | None = None, max_s: float | None = None,
                      hp_min: float | None = None) -> str | None:  # fmt: skip
    """PURE: why these values cannot be the run's (None: they can; a None keeps the default)."""
    if equip_key is not None and not (len(equip_key) == 2 and equip_key[0] == "F"
                                      and equip_key[1] in "123456789"):  # fmt: skip
        return f"the dagger key {equip_key!r} is not a row-1 hotbar key (F1-F9)"
    if max_s is not None and not (KNIFE_MAX_RANGE[0] <= max_s <= KNIFE_MAX_RANGE[1]):
        return f"the Knife's time {max_s} s is outside {KNIFE_MAX_RANGE[0]}-{KNIFE_MAX_RANGE[1]} s"
    if hp_min is not None and not (KNIFE_HP_RANGE[0] <= hp_min <= KNIFE_HP_RANGE[1]):
        return f"the dagger's HP rule {hp_min} is outside {KNIFE_HP_RANGE[0]}-{KNIFE_HP_RANGE[1]}"
    return None


def configure(equip_key: str | None = None, max_s: float | None = None,
              hp_min: float | None = None) -> dict[str, Any]:  # fmt: skip
    """Set the run's own values (once, before the run's first read; a None keeps the current one)
    and return the previous ones (a test puts them back with ``configure(**prev)``)."""
    global EQUIP_KEY, EQUIP_SLOT, BARE_MAX_S, BARE_HP_MIN
    why = configure_refused(equip_key, max_s, hp_min)
    if why:
        raise ValueError(why)
    prev = {"equip_key": EQUIP_KEY, "max_s": BARE_MAX_S, "hp_min": BARE_HP_MIN}
    if equip_key is not None:
        EQUIP_KEY, EQUIP_SLOT = equip_key, int(equip_key[1]) - 1
    if max_s is not None:
        BARE_MAX_S = float(max_s)
    if hp_min is not None:
        BARE_HP_MIN = float(hp_min)
    return prev


# --- the swaps (dungeon@9.27; measured LIVE 2026-11-11 on the lab client by the parent agent,
# 1280 x 720 game region, RDP) ------------------------------------------------------------------
EQUIP_WINDOW = "equipment"  # ui_anchors / ui_gate's name; its own chord (Alt+Q) is a TOGGLE
EQUIP_HOME = (185, 300)  # where it reads open (ui_anchors.CAPTURE_ORIGINS; ~0.8 s after the chord)
WEAPON_SLOT = (18, 102)  # the weapon slot, window px (game-region (203, 402) at its home): a
# double-click there takes the dagger off (the Battle Log shows a RED line)
OPEN_S = 1.2  # the window must read open this soon after the chord (measured ~0.8 s)
LATE_S = 0.8  # not open by OPEN_S: watched this much longer, so a LATE one is closed again
OFF_S = 1.0  # the F5 slot must read BARE this soon after the double-click
CLOSE_S = 1.0  # the window must read closed this soon after the closing chord
ON_S = 0.8  # the F5 slot must read ARMED this soon after an equip press (a CYAN line follows)
POLL_S = 0.1  # the reads' rhythm (the RDP bus sends a frame at least every 0.1 s)
FAIL_STOP = 3  # this many failed swaps IN A ROW stop the run (never fight in an unknown state)
# THE WEAPON STATE READOUT (the parent, live 11-11): the F5 slot draws the dagger's icon ONLY while
# the dagger is in the bag (bare); worn, the slot is EMPTY (white: hotbar_count's empty slot). So
# armed <=> the slot looks as it did at the run's start, when the setup read it EMPTY. The crop is
# hotbar_count's calibrated ICON box of the slot; a pixel CHANGED when its grey moved by more than
# SLOT_PX from the reference, and the slot reads BARE when at least SLOT_SHARE of the crop changed.
# Picked on synthetic crops (test_bare_steal): on a 24 x 17 white slot, codec noise of +-6 grey
# changes 0 % of it; an icon of 6 x 10 dark px (a thin blade, 15 % of the crop) changes 15 %; the
# threshold sits at a third of that. A per-pixel share, not a mean: a thin icon moves the crop's
# MEAN by ~26 grey. The parent checks both numbers live (slot_stats is logged with each read).
SLOT_PX = 40.0
SLOT_SHARE = 0.05
SLOT_DARK = 40.0  # a crop darker than this on average is unreadable (a teleport's dark frames)


def slot_gray(frame: np.ndarray) -> np.ndarray:
    """PURE: a game-region frame as hotbar_count's grey (the channels' mean: BGR or RGB alike)."""
    return hb.gray(np.asarray(frame))


def slot_crop(gray: np.ndarray, slot: int | None = None) -> np.ndarray:
    """PURE: hotbar row 1 slot ``slot``'s icon box (hotbar_count.ICON, its PITCH) from a game-region
    grey frame, as a copy (the reference must not follow the frame buffer). None: the dagger's
    slot, as configured (read at call time, never at import)."""
    slot = EQUIP_SLOT if slot is None else slot
    x0, y0, x1, y1 = hb.ICON
    return np.asarray(gray[y0:y1, x0 + hb.PITCH * slot : x1 + hb.PITCH * slot], np.float64).copy()


def slot_empty(gray: np.ndarray, slot: int | None = None) -> bool:
    """PURE: hotbar_count's EMPTY slot (no digit and no icon): read_count's 0 with no digit
    templates (a digit then reads None, never 0). None: the dagger's slot, as configured."""
    return hb.read_count(gray, EQUIP_SLOT if slot is None else slot, {}) == 0


def slot_bare(crop: np.ndarray, ref: np.ndarray) -> bool | None:
    """PURE: True = the slot shows the dagger (it is in the bag: BARE), False = it looks as the
    armed reference, None = unreadable (a dark frame, or a crop of another shape)."""
    c, r_ = np.asarray(crop, np.float64), np.asarray(ref, np.float64)
    if c.shape != r_.shape or not c.size or float(c.mean()) < SLOT_DARK:
        return None
    return float((np.abs(c - r_) > SLOT_PX).mean()) >= SLOT_SHARE


def slot_stats(crop: np.ndarray, ref: np.ndarray | None = None) -> dict[str, float]:
    """PURE: the numbers logged with the reads (the parent checks the thresholds live)."""
    c = np.asarray(crop, np.float64)
    out = {"mean": round(float(c.mean()), 1),
           "dark_share": round(float((c < hb.ICON_DARK).mean()), 3)}  # fmt: skip
    if ref is not None and np.shape(ref) == c.shape:
        d = np.abs(c - np.asarray(ref, np.float64))
        out.update(diff=round(float(d.mean()), 1), changed=round(float((d > SLOT_PX).mean()), 3))
    return out


# --- --steal-opener (dungeon@9.27c, Batt 2026-11-11 ~19:15): a weak OPENER weapon (a Knife, ATK 17)
# on its own hotbar key instead of bare hands. Its key puts it on (the dagger goes to the bag: F5
# shows the dagger), F5 puts the dagger back (the opener goes to the bag: its key shows it again).
# A worn item's hotbar icon is not drawn (measured live for the F5 dagger, 11-11), so the two slots
# together are the weapon state's readout.
OPENER_VERSION = "9.27c"


def slot_counted(gray: np.ndarray, slot: int) -> bool:
    """PURE: the slot draws a COUNT (hotbar_count's black digits in its count box): a stack, never
    a weapon (equipment has no count)."""
    x0, y0, x1, y1 = hb.box(slot)
    return bool((np.asarray(gray)[y0:y1, x0:x1] < hb.INK).any())


def opener_worn(gray: np.ndarray, slot: int, ref_shows: np.ndarray) -> bool | None:
    """PURE: the opener's slot -- False = it looks as at the run's start (the opener's icon: in
    the bag), True = it reads EMPTY by hotbar_count's rule (no digit, no icon: the opener worn),
    None = unreadable (dark) or neither (another icon)."""
    crop = slot_crop(gray, slot)
    if not crop.size or float(crop.mean()) < SLOT_DARK:
        return None
    if slot_bare(crop, ref_shows) is False:
        return False
    return True if slot_empty(gray, slot) else None


def weapon_state(dagger_in_bag: bool | None, opener_on: bool | None) -> str | None:
    """PURE (--steal-opener): the two slots as ONE state -- "armed" (the dagger worn: F5 empty, the
    opener's icon on its key), "opener" (the opener worn: F5 shows the dagger, the opener's slot
    empty), "bare" (both in the bag), "odd" (both slots empty: cannot be with one weapon hand),
    None (a slot unreadable)."""
    if dagger_in_bag is None or opener_on is None:
        return None
    if dagger_in_bag:
        return "opener" if opener_on else "bare"
    return "odd" if opener_on else "armed"


def _luma(rgb: np.ndarray) -> np.ndarray:
    a = np.asarray(rgb)[..., :3].astype(np.float32)
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


def _run_from(row_white: np.ndarray, x: int, gap: int = 2) -> int | None:
    """The last column of the white run that starts at ``x`` (gaps of <= ``gap`` px joined: JPEG
    or anti-aliasing), None when ``x`` itself is not white."""
    if not 0 <= x < row_white.size or not row_white[x]:
        return None
    end, miss = x, 0
    for c in range(x + 1, row_white.size):
        if row_white[c]:
            end, miss = c, 0
        else:
            miss += 1
            if miss > gap:
                break
    return end


def popup_box(frame_rgb: np.ndarray) -> tuple[int, int] | None:
    """PURE: the popup's (left, right) columns on a game-region RGB frame, None when it is not
    drawn. Its frame, measured on fiT14 (2026-11-11): a 2-px WHITE border column at x 541-542 over
    the box's rows (a grey inner line at x 543), the top border row POPUP_TOP and the bottom border
    row POPUP_BOTTOM white from x 544 (rounded corners) to the box's right end; between them the
    fill, the icon and the text (never read). All three edges must be there, and the top and the
    bottom must end together: a bright scene that is white at this place does not draw them."""
    lum = _luma(frame_rgb)
    if lum.shape[0] <= POPUP_BOTTOM or lum.shape[1] <= POPUP_LEFT + POPUP_MIN_W:
        return None
    white = lum >= POPUP_WHITE
    inner = slice(POPUP_TOP + 4, POPUP_BOTTOM - 4)
    x0 = next((x for x in range(POPUP_LEFT - POPUP_LEFT_TOL, POPUP_LEFT + POPUP_LEFT_TOL + 1)
               if float(white[inner, x].mean()) >= 0.9), None)  # fmt: skip
    if x0 is None:
        return None
    start = x0 + 3  # past the rounded corner
    top = _run_from(white[POPUP_TOP], start) or _run_from(white[POPUP_TOP + 1], start)
    bot = _run_from(white[POPUP_BOTTOM], start) or _run_from(white[POPUP_BOTTOM - 1], start)
    if top is None or bot is None or abs(top - bot) > 3:
        return None
    x1 = max(top, bot) + 2  # the rounded right corner
    if not POPUP_MIN_W <= x1 - x0 + 1 <= POPUP_MAX_W:
        return None
    return x0, x1


def popup_sig(frame_rgb: np.ndarray) -> np.ndarray:
    """PURE: the popup's contents (the icon and the first part of the text) as luma, to tell a
    NEW popup from the same one still shown."""
    x0, y0, x1, y1 = POPUP_SIG
    return _luma(np.asarray(frame_rgb)[y0:y1, x0:x1]).copy()


Box = tuple[int, int]


def popup_new(prev_sig: np.ndarray | None, prev_box: Box | None,
              cur_rgb: np.ndarray) -> tuple[bool, Box | None, np.ndarray | None]:  # fmt: skip
    """PURE: (a NEW popup on ``cur_rgb``?, its box, its signature). New = drawn now and either not
    drawn on the previous frame or drawn with other contents (another item, or a new count)."""
    box = popup_box(cur_rgb)
    if box is None:
        return False, None, None
    sig = popup_sig(cur_rgb)
    if prev_box is None or prev_sig is None or prev_sig.shape != sig.shape:
        return True, box, sig
    # the right end jitters 1-2 px on one popup (fiT14 frames 132, 789, 1189, 1191: 4 false
    # onsets before this tolerance); a new item's name changes the width by more
    wider = abs((box[1] - box[0]) - (prev_box[1] - prev_box[0])) > POPUP_WIDTH_TOL
    changed = float(np.abs(sig - prev_sig).mean()) >= POPUP_CHANGE or wider
    return changed, box, sig


def cyan_new(lines: Sequence[Mapping[str, Any]], n0: int) -> bool:
    """PURE: a Battle Log line of the item-gain COLOUR among ``lines[n0:]`` (the live reader's
    lines; the colour is read from pixels, so any language). Its text is never read."""
    return any(ln.get("colour") == ITEM_COLOUR for ln in lines[n0:])


@dataclass
class BareSteal:
    """PURE state of the bare-hand phase (one fight at a time). The runner calls ``engage`` on a
    new target's first strike, ``tick`` every loop, ``equipped`` / ``unequipped`` after each swap
    it read back, and ``fight_end`` when the fight ends. --bare-ready: ``wait_bare`` (bare, no
    phase) after an idle unequip or a fight ended bare, ``begin`` at the next first strike."""

    armed: bool = True  # the dagger is on (the run starts armed)
    t_bare: float | None = None  # when the bare phase began (the unequip read back)
    n_lines0: int = 0  # the Battle Log line count at that moment
    popup_sig0: np.ndarray | None = None
    popup_box0: tuple[int, int] | None = None
    stolen: bool = False  # this fight's steal cue came
    cue: str = "both"  # dungeon@9.27d (--steal-cue): "both" (as merged) or "popup" (no cyan line)
    log: list[dict[str, Any]] = field(default_factory=list)

    def engage(self) -> str | None:
        """A new target: "unequip" while armed and this fight has not stolen yet, else None."""
        if self.armed and not self.stolen:
            return "unequip"
        return None

    def unequipped(self, t: float, n_lines: int, sig: np.ndarray | None,
                   box: tuple[int, int] | None) -> None:  # fmt: skip
        self.armed, self.t_bare, self.n_lines0 = False, t, n_lines
        self.popup_sig0, self.popup_box0 = sig, box

    def wait_bare(self) -> None:
        """dungeon@9.27b (--bare-ready): bare with NO phase -- the dagger came off while idle, or a
        target's fight ended bare. No cue, no BARE_MAX_S runs until ``begin`` (the next target's
        first strike)."""
        self.armed, self.t_bare = False, None
        self.popup_sig0, self.popup_box0 = None, None

    def begin(self, t: float, n_lines: int, sig: np.ndarray | None,
              box: tuple[int, int] | None) -> None:  # fmt: skip
        """dungeon@9.27b: the bare phase starts at this first strike (the dagger already off):
        BARE_MAX_S, the Battle Log's line count and the popup shown are all taken NOW."""
        self.unequipped(t, n_lines, sig, box)

    def tick(self, t: float, lines: Sequence[Mapping[str, Any]], cur_rgb: np.ndarray | None,
             hp_share: float | None) -> tuple[str | None, str | None]:  # fmt: skip
        """("equip", why) when the dagger must go back on, else (None, None). why: "cyan" / "popup"
        (a steal cue; "popup" only when ``cue`` is "popup"), "time" (BARE_MAX_S), "hp"
        (BARE_HP_MIN)."""
        if self.armed or self.t_bare is None:
            return None, None
        # 9.27d: "popup" ignores the Battle Log -- 4BY / p69: the live reader re-emits OLD cyan
        # lines (a "put on", a loot gain line), 57 % of p69's cyan equips came with no steal
        if self.cue != "popup" and cyan_new(lines, self.n_lines0):
            self.stolen = True
            return "equip", "cyan"
        if cur_rgb is not None:
            new, box, sig = popup_new(self.popup_sig0, self.popup_box0, cur_rgb)
            if new:
                self.stolen = True
                return "equip", "popup"
            if box is None:  # the old popup faded: the next one is new however it looks
                self.popup_sig0, self.popup_box0 = None, None
        if hp_share is not None and hp_share < BARE_HP_MIN:
            return "equip", "hp"
        if t - self.t_bare >= BARE_MAX_S:
            return "equip", "time"
        return None, None

    def equipped(self) -> None:
        self.armed, self.t_bare = True, None

    def fight_end(self) -> None:
        """The fight is over: the next target starts a new bare phase."""
        self.stolen = False
