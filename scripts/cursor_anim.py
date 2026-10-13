#!/usr/bin/env python3
"""cursor@3 (Batt 2026-10-13, decision 3: "fix the windmill next: mask per-map ANIMATED regions
(measured with the cursor parked) plus a fresh background per hover; pre-register that as
cursor@3").

cursor@2 (demonstrations.md 3.36) failed its WALK bar on the held-out alberta (0.682): the
windmill's sails rotate (~2 s a cycle, measured 2026-10-10 with the cursor parked: 20-60k px of the
view change every 0.2 s), so the cursor mask |A - B| against ONE parked frame floods wherever a
sail moved after the park, and Prober9's 0.25 s "animated" map (two parked frames) catches only the
sails' last quarter-second. ProberAnim changes two things and nothing else:

1. **The ANIMATED REGION of the view**, measured with the cursor parked: CYCLE_FRAMES grabs,
   CYCLE_GAP_S apart (13 x 0.2 s = 2.4 s, longer than the windmill's cycle). A pixel is animated if
   ANY grab differs from the first by more than ANIM_DIFF (walk@9's threshold), grown by GROW_PX.
   It is cached per VIEW (`set_view((map, x, y))`: the camera follows the character, so one GM
   cell is one view), so it costs CYCLE_S once per view. Animated pixels never count as the cursor
   (Prober9's rule, over a whole cycle instead of a quarter-second).
2. **A FRESH background per hover:** the background is grabbed again right before each hover (the
   cursor still parked), not kept from the park.

The reader (cursor_robust's robust2: per-grab shapes + the no-entry ring) is unchanged. A cursor
that sits INSIDE the animated region loses those pixels from its mask: UNKNOWN, no click (fails
closed). `cursor_gate.prober(classifier="robust3")` builds it. Client pixels stay in RAM; nothing
is committed.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable, Hashable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

CYCLE_FRAMES, CYCLE_GAP_S = 13, 0.2  # 2.4 s: alberta's windmill turns once in ~2 s (2026-10-10)
ANIM_DIFF = 60  # summed |dB| above this = animated (walk@9 / walk10.ANIM_DIFF)
GROW_PX = 2


def grow(mask: Any, px: int = GROW_PX) -> Any:
    """8-neighbour dilation by ``px`` pixels (pure numpy)."""
    m = np.asarray(mask, dtype=bool)
    for _ in range(px):
        g = m.copy()
        g[1:, :] |= m[:-1, :]
        g[:-1, :] |= m[1:, :]
        g[:, 1:] |= m[:, :-1]
        g[:, :-1] |= m[:, 1:]
        g[1:, 1:] |= m[:-1, :-1]
        g[:-1, :-1] |= m[1:, 1:]
        g[1:, :-1] |= m[:-1, 1:]
        g[:-1, 1:] |= m[1:, :-1]
        m = g
    return m


def animated_region(frames: Sequence[Any], diff: int = ANIM_DIFF, px: int = GROW_PX) -> Any:
    """Every pixel that differs from the first frame by more than ``diff`` (summed over BGR) in ANY
    later frame, grown by ``px``. ``frames``: >= 2 equal-sized images."""
    if len(frames) < 2:
        raise ValueError("an animated region needs at least two frames")
    first = np.asarray(frames[0])[..., :3].astype(np.int16)
    region = np.zeros(first.shape[:2], dtype=bool)
    for f in frames[1:]:
        region |= np.abs(np.asarray(f)[..., :3].astype(np.int16) - first).sum(-1) > diff
    return grow(region, px)


def measure(grab: Callable[[], Any], n: int = CYCLE_FRAMES, gap: float = CYCLE_GAP_S,
            sleep: Callable[[float], None] = time.sleep) -> tuple[Any, list[Any]]:  # fmt: skip
    """``n`` grabs ``gap`` apart (the cursor parked, no motion): (the region, the frames)."""
    frames = []
    for k in range(n):
        if k:
            sleep(gap)
        frames.append(np.asarray(grab())[..., :3].copy())
    return animated_region(frames), frames


def prober_anim(agent: Any, screen: Any, refs: Any) -> Any:
    """A ProberAnim on walk10.Prober9 (the live gate's prober), reading with ``refs``."""
    import ro_agent as r
    import walk10 as w10

    class ProberAnim(w10.Prober9):  # type: ignore[misc,valid-type]
        def __init__(self, *a: Any, **kw: Any) -> None:
            super().__init__(*a, **kw)
            self.view: Hashable | None = None
            self.regions: dict[Hashable, Any] = {}
            self.region: Any = None
            self.park_background: Any = None  # Prober9's own background (kept for scoring)
            self.anim_short: Any = None  # Prober9's 0.25 s animated map (kept for scoring)

        def set_view(self, key: Hashable | None) -> None:
            """The view the next parks are in ((map, x, y) of the GM); None = never cache."""
            self.view = key

        def park(self) -> bool:
            ok = bool(super().park())
            if not ok:
                return ok
            self.park_background, self.anim_short = self.background, self.animated
            region = self.regions.get(self.view) if self.view is not None else None
            if region is None:
                region, _ = measure(lambda: self.screen.grab(*r.game_region())[1])
                if self.view is not None:
                    self.regions[self.view] = region
            self.region = region
            self.animated = self.anim_short | region
            return ok

        def hover(self, u: float, v: float) -> None:
            self.background = self.screen.grab(*r.game_region())[1]  # FRESH, the cursor parked
            super().hover(u, v)

    return ProberAnim(agent, screen, refs)
