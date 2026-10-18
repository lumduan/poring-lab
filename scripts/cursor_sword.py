#!/usr/bin/env python3
"""A DETECTOR-INDEPENDENT unit check at a click point: the client's own SWORD cursor (Batt
2026-10-18, decision 2 on the held-out map, option b).

On prt_fild06 (3.76) the species the detector never learned had no box, so the loot click's unit
check and the walk click's units gate could not see them: 21 of the 29 attack requests on
non-targets came from LOOT clicks, 5 from walk clicks. The client knows better: it draws its cursor
as a SWORD over ANY monster (and resolves it where a SECOND motion leaves the pointer: the arm C
nudge). So before a loot or a moving walk click, the pointer goes to the point in two motions and
the cursor there is read; SWORD = a unit we did not intend to strike = no click.

The reader needs no background (the robust reader's |A - B| mask needs a parked one, which a
scrolling camera never gives): only cursor_robust's COLOUR RECALL -- the share of a reference
cursor's own interior pixels whose colour is within TOL in the observed 64 x 64 crop (the
hotspot at its centre), best over the references of a class and over shifts of +-2 px.

Offline, leave-one-out on the 645 v3 references (2026-10-18, /dev/shm eval):
- SWORD recall of the 26 SWORD crops: min 0.791, p10 0.830; of every other crop: max 0.708
  (pickup), talk 0.660, walk 0.585 -> SWORD_MIN 0.75 separates all 645;
- WALK recall of the walk crops: p10 1.000 (min 0.591); of the SWORD crops: max 0.709 -> a drawn
  WALK arrow (>= DRAWN_MIN) with a low SWORD recall (< CLEAR_SWORD_MAX) = CLEAR;
- PICKUP recall of the pickup crops >= 0.997; of every other crop <= 0.660 (SWORD <= 0.223). The
  hand itself reads 0.63-0.71 as a SWORD, so a drawn hand (>= PICKUP_MIN) is CLEAR below SWORD_MIN
  (a first cut with one ceiling for both left every pickup crop UNKNOWN: no loot click at all).
The module's verdicts, leave-one-out: SWORD 26/26 sword; walk 468 clear + 23 unknown; pickup 9/9
clear; talk / warp / no-entry unknown (never clear, never sword).
Anything else is UNKNOWN (the client has not drawn its cursor there yet, or a shape we do not
expect): reads repeat until the wait ends, then UNKNOWN -- fail closed, no click.

These are thin margins (~0.04 each side of SWORD_MIN on static crops): a live positive case
through the same path, and the arm's own counts, decide whether it is used (the pre-registration).
Client pixels (the references) stay in data/; this module holds code only.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cursor_robust as cr  # noqa: E402

SWORD_MIN = 0.75  # SWORD recall at or above: a unit is under the pointer
DRAWN_MIN = 0.85  # WALK recall at or above: the client drew its arrow here ...
CLEAR_SWORD_MAX = 0.60  # ... and the SWORD recall stays below this: CLEAR
PICKUP_MIN = 0.90  # PICKUP recall at or above (and SWORD below SWORD_MIN): the hand, CLEAR
WALK_SUBSET = 16  # every 16th WALK prototype (the arrow over many backgrounds): ~31 of 491
HALF = cr.CROP // 2


class SwordRefs:
    """The SWORD, PICKUP and (a subset of) WALK prototypes of cursor_robust's references, with
    every (prototype, shift) pair precomputed per class."""

    def __init__(self, refs: cr.RobustRefs, exclude_ref: Sequence[int] = ()) -> None:
        self.refs = refs
        drop = {int(x) for x in exclude_ref}
        n_s = len(refs.shifts)
        self.pairs: dict[str, tuple[Any, Any]] = {}
        for name in ("sword", "pickup", "walk"):
            c = refs.classes.index(name)
            ks = [int(k) for k in refs.by_class[c] if int(refs.ref[k]) not in drop]
            if name == "walk":
                ks = ks[::WALK_SUBSET]
            kk = np.repeat(np.array(ks, dtype=np.int64), n_s)
            ss = np.tile(np.arange(n_s, dtype=np.int64), len(ks))
            self.pairs[name] = (kk, ss)

    @classmethod
    def load(cls, path: Path = cr.REFS_V3) -> SwordRefs:
        return cls(cr.RobustRefs.load(path))

    def recalls(self, crop: Any) -> dict[str, float]:
        """The best colour recall per class on a 64 x 64 crop centred on the pointer."""
        planes = self.refs._planes(np.asarray(crop)[..., :3])
        out = {}
        for name, (kk, ss) in self.pairs.items():
            got = self.refs._rec(planes, kk, ss)
            out[name] = round(float(got.max()) if len(got) else 0.0, 3)
        return out


def verdict(rec: dict[str, float]) -> str:
    """PURE: "sword" | "clear" | "unknown" from one read's recalls."""
    if rec["sword"] >= SWORD_MIN:
        return "sword"
    if rec["pickup"] >= PICKUP_MIN:
        return "clear"
    if rec["walk"] >= DRAWN_MIN and rec["sword"] < CLEAR_SWORD_MAX:
        return "clear"
    return "unknown"


def series(verdicts: Sequence[str]) -> str:
    """PURE: the decision over the reads so far: any SWORD = "sword" (fail toward safety); else
    "clear" once a read is CLEAR; else "unknown"."""
    if "sword" in verdicts:
        return "sword"
    return "clear" if "clear" in verdicts else "unknown"


def crop_at(screen: Any, gx0: int, gy0: int, u: float, v: float) -> Any:
    """The 64 x 64 crop around client pixel (u, v), the hotspot at its centre (BGR)."""
    x, y = gx0 + round(u) - HALF, gy0 + round(v) - HALF
    return np.ascontiguousarray(screen.grab(x, y, cr.CROP, cr.CROP)[1][..., :3])


def check(agent: Any, screen: Any, sw: SwordRefs, gx0: int, gy0: int, u: float, v: float, *,
          wait_s: float, gap_s: float = 0.03, approach_px: tuple[int, int] = (-3, -2),
          ) -> dict[str, Any]:  # fmt: skip
    """The pointer to (u, v) in TWO motions (the client draws and resolves its cursor where the
    second leaves it), then reads until a decision or ``wait_s``: {"verdict", "reads", "ms",
    "rec" (the last read's recalls)}. Moves only: never a click."""
    t0 = time.monotonic()
    agent.move(gx0 + round(u) + approach_px[0], gy0 + round(v) + approach_px[1])
    time.sleep(0.02)
    agent.move(gx0 + round(u), gy0 + round(v))
    seen: list[str] = []
    rec: dict[str, float] = {}
    while True:
        rec = sw.recalls(crop_at(screen, gx0, gy0, u, v))
        seen.append(verdict(rec))
        dec = series(seen)
        if dec != "unknown" or time.monotonic() - t0 >= wait_s:
            break
        time.sleep(gap_s)
    return {"verdict": dec, "reads": seen, "ms": round((time.monotonic() - t0) * 1e3),
            "rec": rec}  # fmt: skip
