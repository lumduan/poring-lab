#!/usr/bin/env python3
"""The hotbar's stock counts, read from pixels (dungeon@8.3; rogue-gef10.md Amendments J and M).

Why: dungeon@8.2's setup topped the stock up against the DB's last SAVE. rAthena writes the
inventory only on its autosave (minutes) or on events such as a storage close, never on `@save`
(chrif_save CSAVE_NORMAL carries no CSAVE_INVENTORY). a9 used its last Fly Wing after the last
save, so a10's setup added none, and a10 hunted with 0 wings and died (2026-10-26 05:45). The
hotbar draws the CURRENT count under each item, so the setup reads it there instead.

The font (calibrated 2026-10-26 10:32 on the 1-row hunting hotbar by drinking F1's potions 9 -> 0):
- the count is black (gray < INK), 9 rows tall, right-aligned at the slot's lower right;
- slot k (F1 = 0) has its digits in game-region x [259 + 29 k, 272 + 29 k), y [24, 33);
- an EMPTY slot (count 0) draws no digit AND no icon. A slot with no digit but an icon is
  unreadable (None), never 0.
- ITEM slots only: a skill slot's dark frame reaches into the count box (it reads None).

    hotbar_count.py cut --cal DIR [--out data/hotbar/digits.npz]   templates from the calibration
    hotbar_count.py read FRAME.png [--slots 0 1 2]                 a full-screen PNG (1440 x 900)

The templates are the client's own pixels: they live in data/ (gitignored), never in git.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import numpy.typing as npt

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "data" / "hotbar" / "digits.npz"
X0, X1, Y0, Y1 = 259, 272, 24, 33  # slot 0's count box, game-region px (end-exclusive)
PITCH = 29
ICON = (246, 5, 270, 22)  # slot 0's icon box inside its frame (x0, y0, x1, y1), end-exclusive
INK = 60  # gray below this is a digit's ink (the digits are pure black)
ICON_DARK = 180  # an icon has pixels below this; an empty slot is white (its frame is ~192)
ICON_EMPTY_SHARE = 0.02
CAL_ORIGIN = (300 - 80, 70 - 77)  # the calibration grabs: full-screen [70:120, 300:620]

Gray = npt.NDArray[np.float64]


# 2026-11-20, the live PC's client (its 2-row hotbar): a slot's count FOLLOWS a small "v" mark at
# the slot's bottom-left, LEFT-aligned, up to 4 digits -- slot k's mark in game-region x [257 + 29 k,
# 260 + 29 k), rows 31-32; its digits from x 262 + 29 k, rows 27-35 -- in the SAME glyphs as the
# lab's (the templates match its 588 / 60 / 111 exactly). The lab's right-aligned box above caught
# only part of them (None on every slot, and the 1-row bar clipped them). The mark picks the layout.
MARK = (257, 31, 260, 33)  # slot 0's mark (x0, y0, x1, y1), end-exclusive (3 + 2 px of ink)
MARK_INK = 0.75  # the share of the mark box that is ink when the mark is drawn
LEFT = (262, 27, 290, 36)  # slot 0's left-aligned count box (4 digits on the 7 px pitch)


def gray(frame: npt.NDArray[np.uint8]) -> Gray:
    return np.asarray(frame[..., :3], dtype=np.float64).mean(axis=2)


def box(slot: int) -> tuple[int, int, int, int]:
    """Slot ``slot``'s count box, game-region px (x0, y0, x1, y1), end-exclusive."""
    return X0 + PITCH * slot, Y0, X1 + PITCH * slot, Y1


def glyphs(ink: npt.NDArray[np.bool_]) -> list[npt.NDArray[np.bool_]]:
    """PURE: the ink box split into glyphs at its empty columns, each cropped to its own columns
    (all rows kept: the digits share their baseline)."""
    cols = ink.any(axis=0)
    out: list[npt.NDArray[np.bool_]] = []
    start = None
    for i, c in enumerate([*cols, False]):
        if c and start is None:
            start = i
        elif not c and start is not None:
            out.append(ink[:, start:i])
            start = None
    return out


def glyph_runs(ink: npt.NDArray[np.bool_]) -> list[tuple[int, npt.NDArray[np.bool_]]]:
    """PURE: ``glyphs`` with each glyph's first column."""
    cols = ink.any(axis=0)
    out: list[tuple[int, npt.NDArray[np.bool_]]] = []
    start = None
    for i, c in enumerate([*cols, False]):
        if c and start is None:
            start = i
        elif not c and start is not None:
            out.append((start, ink[:, start:i]))
            start = None
    return out


def left_layout(frame_gray: Gray, slot: int) -> bool:
    """PURE: slot ``slot`` draws the live client's mark before its count (``LEFT`` applies)."""
    x0, y0, x1, y1 = MARK
    box = frame_gray[y0:y1, x0 + PITCH * slot : x1 + PITCH * slot]
    return box.size > 0 and float((box < INK).mean()) >= MARK_INK


def read_left(frame_gray: Gray, slot: int,
              templates: dict[str, npt.NDArray[np.bool_]]) -> int | None:  # fmt: skip
    """PURE: the left-aligned count after the mark: the full-height glyphs from the box's first
    column, read left to right until the first that is not a digit; None when none is."""
    x0, y0, x1, y1 = LEFT
    ink = frame_gray[y0:y1, x0 + PITCH * slot : x1 + PITCH * slot] < INK
    runs = [(c, g) for c, g in glyph_runs(ink) if g[0].any() and g[-1].any()]
    if not runs or runs[0][0] > 1:
        return None
    digits = ""
    for _c, g in runs:
        d = match(g, templates)
        if d is None:
            break
        digits += d
    return int(digits) if digits and (len(digits) == 1 or digits[0] != "0") else None


def match(g: npt.NDArray[np.bool_], templates: dict[str, npt.NDArray[np.bool_]]) -> str | None:
    """PURE: the digit whose template equals the glyph exactly, else the unique one within 1
    differing pixel; else None (never a guess)."""
    dist = {}
    for d, t in templates.items():
        if t.shape == g.shape:
            dist[d] = int((t != g).sum())
    if not dist:
        return None
    ranked = sorted(dist.items(), key=lambda kv: kv[1])
    best_d, best = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 99
    return best_d if best <= 1 and second >= best + 3 else None


# Batt 2026-11-20: "a 0 does not end the run -- that is the player's own to prepare; we end only
# at a death" (the player owns the stock: warnings, never a lock). In a player's Run (the Run
# helper sets poring_env.selfpos.CONFIRM_READS_ENV) an EMPTY slot reads None, never 0, so no stock
# count ends the run (the runner's stock_out needs a 0; its stock_keep needs a count at or under
# PLAYER_WINGS_KEEP, which the player may set to 0 on /flows). Before this, the live PC's 11:55 Run
# ended on one 0 read between two unreadable ones, its Fly Wings still on F8. Lab A/Bs unchanged.
CONFIRM_READS_ENV = "PORING_CONFIRM_READS"  # poring_env.selfpos.CONFIRM_READS_ENV (a test pins it)


def player_run() -> bool:
    """A player's Run (the Run helper's env flag), where no empty slot reads 0."""
    return os.environ.get(CONFIRM_READS_ENV) == "1"


def read_count(frame_gray: Gray, slot: int,
               templates: dict[str, npt.NDArray[np.bool_]]) -> int | None:  # fmt: skip
    """Slot ``slot``'s count from a game-region gray frame; 0 for an empty slot (no digit and no
    icon); None when unreadable -- and, in a player's Run (``player_run``), None for an empty
    slot too: a player's stock never ends the run."""
    if left_layout(frame_gray, slot):  # the live PC's client: the mark, then the count (MARK)
        got = read_left(frame_gray, slot, templates)
        if got is not None:
            return got
    x0, y0, x1, y1 = box(slot)
    ink = frame_gray[y0:y1, x0:x1] < INK
    # 2026-11-13: an ICON's stray ink is no digit -- a digit's ink spans the box's height (all ten
    # templates touch its top and bottom rows); the Butterfly Wing's tail on F9 drew a 3-column
    # mark in the top rows before its "5", and the count read None (the wing home never pressed)
    gs = [g for g in glyphs(ink) if g[0].any() and g[-1].any()]
    if not gs:
        ix0, iy0, ix1, iy1 = ICON
        icon = frame_gray[iy0:iy1, ix0 + PITCH * slot : ix1 + PITCH * slot]
        if float((icon < ICON_DARK).mean()) >= ICON_EMPTY_SHARE:
            return None
        return None if player_run() else 0
    digits = [match(g, templates) for g in gs]
    if any(d is None for d in digits) or len(digits) > 2:
        return None
    return int("".join(d for d in digits if d is not None))


def load(path: Path = TEMPLATES) -> dict[str, npt.NDArray[np.bool_]]:
    z = np.load(path)
    return {k[1:]: z[k].astype(bool) for k in z.files}


def cut(cal: Path) -> dict[str, npt.NDArray[np.bool_]]:
    """The templates from the calibration grabs ``f1-N.npy`` (N = the count shown in slot 0):
    every digit of every N, checked to agree wherever a digit appears twice."""
    ox, oy = CAL_ORIGIN
    x0, y0, x1, y1 = box(0)
    out: dict[str, npt.NDArray[np.bool_]] = {}
    for f in sorted(cal.glob("f1-*.npy")):
        n = f.stem.split("-")[1]
        if n == "0":
            continue
        g = gray(np.load(f))
        ink = g[y0 - oy : y1 - oy, x0 - ox : x1 - ox] < INK
        gs = glyphs(ink)
        if len(gs) != len(n):
            raise SystemExit(f"{f.name}: {len(gs)} glyphs for {n!r}")
        for d, glyph in zip(n, gs, strict=True):
            if d in out and not np.array_equal(out[d], glyph):
                raise SystemExit(f"{f.name}: digit {d} differs from an earlier cut")
            out[d] = glyph
    missing = sorted(set("0123456789") - set(out))
    if missing:
        raise SystemExit(f"digits missing from the calibration: {missing}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cut")
    c.add_argument("--cal", type=Path, required=True)
    c.add_argument("--out", type=Path, default=TEMPLATES)
    r = sub.add_parser("read")
    r.add_argument("frames", type=Path, nargs="+", help="full-screen PNGs (the 1440 x 900 desktop)")
    r.add_argument("--slots", type=int, nargs="+", default=[0, 1, 2])
    r.add_argument("--templates", type=Path, default=TEMPLATES)
    a = ap.parse_args()
    if a.cmd == "cut":
        t = cut(a.cal)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        np.savez(a.out, **{f"d{k}": v for k, v in t.items()})
        print(json.dumps({"out": str(a.out), "digits": sorted(t), "shapes": {
            k: list(v.shape) for k, v in sorted(t.items())}}))  # fmt: skip
        return 0
    from PIL import Image

    sys.path.insert(0, str(ROOT / "scripts"))
    import ro_agent as ra

    gx, gy, gw, gh = ra.game_region()
    t = load(a.templates)
    for f in a.frames:
        full = np.asarray(Image.open(f).convert("RGB"))
        g = gray(full[gy : gy + gh, gx : gx + gw])
        print(f.name, {s: read_count(g, s, t) for s in a.slots})
    return 0


if __name__ == "__main__":
    sys.exit(main())
