#!/usr/bin/env python3
"""LEARN THIS CLIENT'S OWN WALK ARROW at a Run's start (Batt 2026-11-19: "yes, fix cause C";
ADR-0020 Amendment V).

Why: the cursor readers (cursor_sword) match the client's cursor by its COLOURS against the lab
client's references (data/walk6/cursor_refs_rdp_v3.npz). Batt's Thai client draws the same arrow
in other colours: its walk recall read 0.53-0.93 where the lab's reads 0.94-0.99, so most of his
scan cells read "unknown" (4-7 "clear" of 40-59 per Run; the lab client 60-76 %). An "unknown"
hover waits out its whole read time, and the no-entry ring is only checked on a "clear" one.

How -- MOVES ONLY, never a click or a key:
1. the pointer is parked away from the points; each point's crop is grabbed twice (pixels that
   change between the two are animated scenery: never the cursor);
2. each POINT around her is hovered in two motions (as every hover); GRABS crops follow;
3. every crop is the REAL client's pixels around the real pointer, unscaled: what the readers see
   at that point (in the virtual 1280x720 view the pointer's own box is pasted unscaled,
   ro_agent.CURSOR_BOX);
4. the cursor's own pixels are |A - B| (walk6.cursor_mask; animated pixels and the green walk
   marker ignored);
5. a crop is KEPT only when its mask is the walk arrow BY SHAPE ALONE (colour-free: the F of
   precision and coverage against the lab's prototypes >= SHAPE_MIN, and every other class's
   >= MARGIN lower), and the lab's SWORD reads under cursor_sword.CLEAR_SWORD_MAX on it (a sword
   over a monster is never learned as the arrow).
   Pre-registered 2026-11-19 on the lab's 645 references, leave-one-out: 421 of 491 walk arrows
   pass (86 %), 0 of the 154 sword / hand / talk / no-entry / warp references do;
6. the kept crops -- the cursor's pixels only, the rest zeroed -- join cursor_sword's references
   for this process (cursor_sword.LEARNED; the runner's SwordRefs.load takes them). Held in
   memory, never written: Batt 2026-11-18, no pictures.

A still scene is needed (she stands at a Run's start); a scrolling one spoils every mask, and
nothing is learned (the lab's references alone, as before). Never refuses a Run.
"""

from __future__ import annotations

import sys
import time
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cursor_robust as cr  # noqa: E402
import cursor_sword as csw  # noqa: E402

SHAPE_MIN = 0.95  # the walk class's best shape F (precision x coverage) at or above
MARGIN = 0.15  # ... and every other class's at least this much lower
ANIM_DIFF = 60  # walk10.ANIM_DIFF: summed |B1 - B2| above this = an animated pixel
ANIM_S = 0.25  # the second background grab after this
HOVER_S = 0.45  # after the second motion: the client redraws its cursor ~0.2-0.4 s later
GRABS, GRAB_GAP_S = 3, 0.12  # crops per point (the arrow animates)
PARK = (1250, 380)  # walk6.PARKS[0]: the world's right edge, away from her and the points
APPROACH = (-3, -2)  # cursor_sword.check's first motion
# her place in the virtual client and the points around her (~3-4 cells: off her own sprite,
# clear of the chat window, Basic Info and the hotbar at their lab places)
CENTRE = (640, 300)
POINTS = ((-130, 0), (130, 0), (0, -110), (0, 110), (-110, -90), (110, -90), (-110, 90),
          (110, 90))  # fmt: skip
KEEP_MAX = 24  # learned crops kept (a few per point)
HALF = cr.CROP // 2


def shape_scores(refs: cr.RobustRefs, mask: Any) -> dict[str, float]:
    """PURE: per class, the best F (2 p c / (p + c)) of the mask's precision and coverage over
    the class's prototypes and shifts -- the shape alone, no colour."""
    prec, cov, _ = refs._mask_terms(np.asarray(mask, dtype=bool))
    f = np.where(prec + cov > 0, 2 * prec * cov / np.maximum(prec + cov, 1e-9), 0.0)
    return {c: float(f[refs.by_class[k]].max()) if len(refs.by_class[k]) else 0.0
            for k, c in enumerate(refs.classes)}  # fmt: skip


def is_walk_arrow(scores: dict[str, float]) -> bool:
    """PURE: the walk arrow by shape: its F >= SHAPE_MIN and every other class MARGIN lower."""
    fw = scores.get("walk", 0.0)
    other = max((v for k, v in scores.items() if k != "walk"), default=0.0)
    return fw >= SHAPE_MIN and fw - other >= MARGIN


def judge(refs: cr.RobustRefs, sword: csw.SwordRefs, a: Any, b: Any, anim: Any
          ) -> tuple[str, tuple[Any, Any] | None]:  # fmt: skip
    """PURE: one hover crop ``a`` against its parked background ``b`` (``anim``: animated
    pixels): ("kept", (the cursor's pixels, mask)) or (why not, None)."""
    import walk6 as w6

    a3 = np.asarray(a)[..., :3]
    b_mod = np.where(np.asarray(anim, dtype=bool)[..., None], a3, np.asarray(b)[..., :3])
    mask = w6.cursor_mask(a3, b_mod)
    if int(mask.sum()) < cr.MIN_PX:
        return "no_cursor", None
    if not is_walk_arrow(shape_scores(refs, mask)):
        return "shape", None
    if sword.recalls(a3)["sword"] >= csw.CLEAR_SWORD_MAX:
        return "sword", None
    cut = np.where(mask[..., None], a3, 0).astype(np.uint8)
    return "kept", (cut, mask)


def real_point(r: Any, u: float, v: float) -> tuple[int, int]:
    """A virtual-client point -> desktop pixels, without moving ro_agent's pointer record."""
    gx, gy, _, _ = r.game_region()
    if r.virtual_active():
        fx, fy = r.client_view().to_real(u, v)
        return int(round(fx)), int(round(fy))
    return int(gx + round(u)), int(gy + round(v))


def learn(agent: Any, screen: Any, r: Any, points: Sequence[tuple[int, int]] = POINTS,
          refs: cr.RobustRefs | None = None) -> dict[str, Any]:  # fmt: skip
    """Hover ``points`` (offsets from CENTRE) and learn this client's walk arrow into
    cursor_sword.LEARNED. Returns {"kept", "used", "why": Counter, "points", "ms"}."""
    t0 = time.monotonic()
    refs = refs or cr.RobustRefs.load()
    sword = csw.SwordRefs(refs)
    gx, gy, _, _ = r.game_region()
    pts = [(CENTRE[0] + dx, CENTRE[1] + dy) for dx, dy in points]
    reals = [real_point(r, u, v) for u, v in pts]

    def crop(p: tuple[int, int]) -> Any:
        x, y = p
        return np.ascontiguousarray(screen.grab(x - HALF, y - HALF, cr.CROP, cr.CROP)[1][..., :3])

    agent.move(gx + PARK[0] + APPROACH[0], gy + PARK[1] + APPROACH[1])
    agent.move(gx + PARK[0], gy + PARK[1])
    time.sleep(HOVER_S)
    b1 = [crop(p) for p in reals]
    time.sleep(ANIM_S)
    b2 = [crop(p) for p in reals]
    anims = [
        np.abs(x.astype(int) - y.astype(int)).sum(-1) > ANIM_DIFF
        for x, y in zip(b1, b2, strict=True)
    ]
    why: Counter[str] = Counter()
    kept: list[tuple[Any, Any]] = []
    for (u, v), p, b, anim in zip(pts, reals, b2, anims, strict=True):
        agent.move(gx + u + APPROACH[0], gy + v + APPROACH[1])
        agent.move(gx + u, gy + v)
        time.sleep(HOVER_S)
        for g in range(GRABS):
            if g:
                time.sleep(GRAB_GAP_S)
            verdict, got = judge(refs, sword, crop(p), b, anim)
            why[verdict] += 1
            if got is not None and len(kept) < KEEP_MAX:
                kept.append(got)
    agent.move(gx + PARK[0], gy + PARK[1])  # the pointer off the points again
    used = len(kept) >= csw.LEARN_MIN
    csw.LEARNED[:] = kept if used else []
    return {"kept": len(kept), "used": used, "why": dict(why), "points": len(pts),
            "ms": round((time.monotonic() - t0) * 1e3)}  # fmt: skip


def words(res: dict[str, Any]) -> str:
    """The run log's line for a learning result."""
    why = res.get("why") or {}
    parts = ", ".join(f"{k} {n}" for k, n in sorted(why.items()))
    if res.get("used"):
        return (f"the cursor: learned this client's own walk arrow ({res['kept']} crops from "
                f"{res['points']} points around her: {parts}; {res['ms']} ms; in memory for this "
                "Run only, never saved): the readers now know its colours")  # fmt: skip
    return (f"WARNING (the Run plays on): the cursor's walk arrow was not learned "
            f"({res.get('kept', 0)} crops kept, {csw.LEARN_MIN} needed: {parts or 'no read'}): "
            "the lab's references alone -- on another client its scan cells may read 'unknown'. "
            "She must stand still on open ground at the Run's start")  # fmt: skip
