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
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ro_agent as r  # noqa: E402

REFS = r.ROOT / "data/walk6/cursor_refs_rdp_v3.npz"
WALK_ONLY = ("walk",)


class GateUnavailable(RuntimeError):
    """The gate cannot judge the cursor here: never click instead."""


def prober(agent: Any, screen: Any, refs_path: Path = REFS, backend: str | None = None) -> Any:
    """A walk@9-reader prober with the v3 references, for the RDP path only."""
    import walk6 as w6
    import walk10 as w10

    if backend is None:
        import record_session

        backend = str(record_session.read_lock(r.ROOT / "state").backend)
    if backend != "rdp":
        raise GateUnavailable(f"cursor references exist only for RDP, the lock says {backend}")
    if not refs_path.exists():
        raise GateUnavailable(f"{refs_path} missing (cursor_diag.py + the talk calibration)")
    return w10.Prober9(agent, screen, w6.CursorRefs.load(refs_path))


def gated_click(pr: Any, u: float, v: float, allow: tuple[str, ...] = WALK_ONLY) -> dict[str, Any]:
    """Click the client-region pixel (u, v) only if the cursor there reads an allowed shape twice
    (the hover read and a no-motion re-read). Returns {"clicked", "why", "shape", "t_click"}."""
    if not pr.park():
        return {"clicked": False, "why": "stale_background", "shape": None}
    pr.hover(u, v)
    first = pr.read(u, v)["shape"]
    if first not in allow:
        return {"clicked": False, "why": f"cursor_{first}", "shape": first}
    again = pr.read(u, v)["shape"]
    if again not in allow:
        return {"clicked": False, "why": f"recheck_{again}", "shape": again}
    gx, gy, _, _ = r.game_region()
    t_click = r.ns()
    pr.agent.click(gx + round(u), gy + round(v))
    return {"clicked": True, "why": "ok", "shape": first, "t_click": t_click}
