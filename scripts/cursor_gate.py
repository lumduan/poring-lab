"""The cursor gate for EVERY non-rule world click (Batt, 2026-10-08, decision 6).

where@2's harness clicked blind (3-8 cells, no cursor check) and attacked field monsters (24 hits)
and contacted NPCs. A harness, calibration or benchmark click on the game world now goes through
`gated_click`: park, hover with two motions, read the cursor (walk@9's reader: animated pixels and
static green excluded) against the v3 references, re-read with no motion, and click ONLY when both
reads are an allowed shape (`walk`; `warp` only for an intended portal click). Unknown, sword, talk,
pickup or noentry = no click, with the reason returned.

Fails closed: no reference file, or a capture path the references were not cut on (they are RDP
references; S2 has none yet), raises instead of clicking. UI clicks (title bars, login screens,
tabs, dialog buttons) are not world clicks and do not use it; `test_click_census.py` lists them.

THE READER (Batt 2026-10-13, decision 3: "SWITCH the live gate to robust2 now"; demonstrations.md
3.36's ADOPTION, a safety-driven adoption that departs from its bar 4): the default classifier is
`robust2` -- cursor_robust.RobustRefs per grab (0 cross-shape / 0 false WALK over 6,731 reads) plus
the no-entry RING over the series (v3 read the no-entry blink frames twice as WALK, 4/255). A WALK
intent reads the FULL 6-grab series, 0.1 s apart, no early stop (cursor@2's measured procedure,
npc_click_test.read_series), and clicks only on `series_verdict` == walk (cursor-robust.md 6a).
Other intents (TALK, a portal's WARP) keep the early-stop reads. `classifier="v3"` stays available
by name (walk6.CursorRefs); pre-registered rules that load v3 themselves are unchanged.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ro_agent as r  # noqa: E402

REFS = r.ROOT / "data/walk6/cursor_refs_rdp_v3.npz"
WALK_ONLY = ("walk",)
CLASSIFIERS = ("robust2", "v3")
DEFAULT_CLASSIFIER = "robust2"  # Batt 2026-10-13 (decision 3); "v3" only by name
SERIES_GRABS, SERIES_GAP_S = 6, 0.1  # cursor@2: npc_click_test.READ_GRABS / READ_GAP_S


class GateUnavailable(RuntimeError):
    """The gate cannot judge the cursor here: never click instead."""


def prober(agent: Any, screen: Any, refs_path: Path = REFS, backend: str | None = None,
           classifier: str = DEFAULT_CLASSIFIER) -> Any:  # fmt: skip
    """A walk@9-reader prober (park, two-motion hover, animated pixels excluded) on the v3
    references, read by `classifier` (robust2 by default), for the RDP path only."""
    import walk6 as w6
    import walk10 as w10

    if classifier not in CLASSIFIERS:
        raise GateUnavailable(f"unknown cursor classifier {classifier!r} (one of {CLASSIFIERS})")
    if backend is None:
        import record_session

        backend = str(record_session.read_lock(r.ROOT / "state").backend)
    if backend != "rdp":
        raise GateUnavailable(f"cursor references exist only for RDP, the lock says {backend}")
    if not refs_path.exists():
        raise GateUnavailable(f"{refs_path} missing (cursor_diag.py + the talk calibration)")
    if classifier == "v3":
        pr = w10.Prober9(agent, screen, w6.CursorRefs.load(refs_path))
    else:
        import cursor_robust as cr

        pr = w10.Prober9(agent, screen, cr.RobustRefs.load(refs_path))
    pr.classifier = classifier
    return pr


def read_series(pr: Any, u: float, v: float, n: int = SERIES_GRABS,
                gap: float = SERIES_GAP_S) -> tuple[list[str], list[int]]:  # fmt: skip
    """``n`` grabs ``gap`` apart with no motion, each read as Prober9 reads (its parked background,
    animated pixels excluded): the shape per grab and the red RING pixels per grab
    (cursor_robust.ring_pixels). npc_click_test.read_series's grab and mask, without its logging."""
    import cursor_robust as cr
    import numpy as np
    import walk6 as w6

    gx, gy, _, _ = r.game_region()
    px, py = gx + round(u), gy + round(v)
    b = pr._crop(pr.background, u, v, 32)
    anim = pr._crop(pr.animated[..., None].astype(np.uint8), u, v, 32)[..., 0] > 0
    shapes: list[str] = []
    rings: list[int] = []
    for g in range(n):
        if g:
            time.sleep(gap)
        big = pr.screen.grab(px - 60, py - 60, 120, 120)[1][..., :3]
        a = big[28:92, 28:92]
        mask = w6.cursor_mask(a, np.where(anim[..., None], a, b))
        shapes.append(str(pr.refs.match(a, mask)["shape"]))
        rings.append(cr.ring_pixels(a, mask))
    return shapes, rings


def gated_click(pr: Any, u: float, v: float, allow: tuple[str, ...] = WALK_ONLY) -> dict[str, Any]:
    """Click the client-region pixel (u, v) only if the cursor there reads an allowed shape twice
    (the hover read and a no-motion re-read; for robust2 and a WALK intent, the 6-grab series with
    the ring). Returns {"clicked", "why", "shape", "t_click"}; the series adds "shapes", "rings"."""
    if not pr.park():
        return {"clicked": False, "why": "stale_background", "shape": None}
    pr.hover(u, v)
    extra: dict[str, Any] = {}
    if getattr(pr, "classifier", "v3") == "robust2" and "walk" in allow:
        import cursor_robust as cr

        shapes, rings = read_series(pr, u, v)
        shape, why = cr.series_verdict(shapes, rings)
        extra = {"shapes": shapes, "rings": rings}
        if shape not in allow:
            return {"clicked": False, "why": f"robust2_{shape}:{why}", "shape": shape, **extra}
    else:
        shape = pr.read(u, v)["shape"]
        if shape not in allow:
            return {"clicked": False, "why": f"cursor_{shape}", "shape": shape}
        again = pr.read(u, v)["shape"]
        if again not in allow:
            return {"clicked": False, "why": f"recheck_{again}", "shape": again}
    gx, gy, _, _ = r.game_region()
    t_click = r.ns()
    pr.agent.click(gx + round(u), gy + round(v))
    return {"clicked": True, "why": "ok", "shape": shape, "t_click": t_click, **extra}
