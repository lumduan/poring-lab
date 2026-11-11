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

Everything here is PURE (no input, no grabs): the runner (dungeon_hunt.py) does the clicks.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

BARE_STEAL_VERSION = "9.27"

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
    it read back, and ``fight_end`` when the fight ends."""

    armed: bool = True  # the dagger is on (the run starts armed)
    t_bare: float | None = None  # when the bare phase began (the unequip read back)
    n_lines0: int = 0  # the Battle Log line count at that moment
    popup_sig0: np.ndarray | None = None
    popup_box0: tuple[int, int] | None = None
    stolen: bool = False  # this fight's steal cue came
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

    def tick(self, t: float, lines: Sequence[Mapping[str, Any]], cur_rgb: np.ndarray | None,
             hp_share: float | None) -> tuple[str | None, str | None]:  # fmt: skip
        """("equip", why) when the dagger must go back on, else (None, None). why: "cyan" / "popup"
        (a steal cue), "time" (BARE_MAX_S), "hp" (BARE_HP_MIN)."""
        if self.armed or self.t_bare is None:
            return None, None
        if cyan_new(lines, self.n_lines0):
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
