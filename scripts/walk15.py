#!/usr/bin/env python3
"""walk@15 (docs/demonstrations.md 3.26): walk@14 + NPC CLEARANCE (a safety fix) + a side-cell fix.

walk@14 (3.25) indoor CLEAN made an NPC CONTACT (route 44, session 20261009T004436): a rule click on
cell (97, 101) contacted "Wedding Staff#w" standing on (97, 100), ONE cell away, 0.17 s after the
click. The cursor had read WALK twice, the marker named the cell, and the gate's nearest NPC box was
18.9 px from the click point (its margin is 12 px; an NPC's radius is 0). The click step is
walk@13's, unchanged since walk@12: walk@11-13 had made no contact in 12 runs, and the route used
none of walk@14's changes. Whatever the client picked (an idle animation frame larger than the hover
frame, or a detector box smaller than the sprite), a click NEXT to an NPC can contact it.

The two changes, exactly:
D. NPC CLEARANCE: an NPC sighting's envelope has radius NPC_RADIUS = 1 (it was 0): the NPC's box
   moved onto each neighbouring cell, + walk@11's 12 px margin, so no click point picks a cell next
   to a detected NPC. NPCs do not move, so walk@14's side approach and walk@13's re-plan route
   around the refusal.
E. A SIDE CELL IS NEVER A CELL THIS ROUTE HAS STOOD ON (walk@14 indoor CLEAN route 25 tried the
   cell it had just come from as its second side).

Everything else is walk@14's (the same code: its route loop and memory rebound here).

    walk15.py --scene indoor|outdoor|guild|town|dungeon|portal --condition clean|crowd --seed S
Pixels in, input out: the rule never reads packets.
"""

from __future__ import annotations

import argparse
import inspect
import signal
import sys
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import operator_hud  # noqa: E402
import route_plan  # noqa: E402
import unit_gate as ug  # noqa: E402
import walk5 as w5  # noqa: E402
import walk11 as w11  # noqa: E402
import walk12 as w12  # noqa: E402
import walk13 as w13  # noqa: E402
import walk14 as w14  # noqa: E402
from walk11 import CURSOR_REFS_V2, SCENES8, UNITS, WALK  # noqa: E402
from walk12 import _terminate  # noqa: E402

# walk@14's names (and through it walk@13's, 12's, 11's: the SAME objects); walk@15's own follow
globals().update({k: v for k, v in vars(w14).items() if not k.startswith("__")})

WALK8_RULE = "walk@15"
NPC_RADIUS = 1  # D: an NPC's envelope: the cells next to it too
VISITED: set[tuple[int, int]] = set()  # E: the cells this route has stood on


def _rebind(fn: Callable[..., Any]) -> Any:
    """A function's code reading its global names from THIS module."""
    fn = inspect.unwrap(fn)
    if not isinstance(fn, types.FunctionType):
        raise TypeError(f"not a plain function: {fn!r}")
    g = types.FunctionType(fn.__code__, globals(), fn.__name__, fn.__defaults__, fn.__closure__)
    g.__kwdefaults__ = fn.__kwdefaults__
    g.__doc__, g.__qualname__ = fn.__doc__, fn.__qualname__
    g.__annotations__ = dict(fn.__annotations__)
    g.__module__ = __name__
    return g


# --- D: NPC clearance -------------------------------------------------------------------------


class NpcClearMemory(w14.StaticMemory):
    """walk@14's memory (its static streaks, walk@11's matching and TTL); an NPC's envelope has
    radius NPC_RADIUS."""

    def envelopes(self, camera: Any, gat: Any, belief: tuple[int, int], now_ns: int,
                  horizon_s: float, monster_ms_per_cell: int) -> list[ug.Envelope]:  # fmt: skip
        out: list[ug.Envelope] = []
        for it in self.items:
            age = max(0.0, (now_ns - it.t_ns) / 1e9)
            rad = ug.radius_cells(it.cls, age + horizon_s, monster_ms_per_cell)
            if w14.is_static(it, now_ns):
                rad = min(rad, w14.STATIC_RADIUS)
            if it.cls == "npc":
                rad = max(rad, NPC_RADIUS)
            rel = (it.cell[0] - belief[0], it.cell[1] - belief[1])
            cells = np.array([(rel[0] + dx, rel[1] + dy) for dx in range(-rad, rad + 1)
                              for dy in range(-rad, rad + 1)], dtype=float)  # fmt: skip
            alt = None if gat is None else gat.relative_altitude(belief, cells)
            feet = camera.project(cells, alt)
            boxes = [(u - it.w / 2, v - it.h, u + it.w / 2, v) for u, v in feet]
            out.append(ug.Envelope(it.cls, rel, rad, boxes))
        return out


# --- E: a side cell is never one this route has stood on ---------------------------------------


def side_cell(w: Any, target: tuple[int, int], blocked: set[tuple[int, int]],
              talk: set[tuple[int, int]], tried: set[tuple[int, int]]
              ) -> tuple[int, int] | None:  # fmt: skip
    """walk@14's side cell, with every cell this route stood on counted as tried."""
    return w14.side_cell(w, target, blocked, talk, tried | VISITED)  # type: ignore[no-any-return]


def click_step(pr: Any, w: Any, end: tuple[int, int], expect: str = WALK,
               accept_unnamed: bool = False) -> dict[str, Any]:  # fmt: skip
    """walk@14's click step (walk@13's, with its sign mask), noting where we stand (E)."""
    VISITED.add((int(w.position[0]), int(w.position[1])))
    return dict(w14.click_step(pr, w, end, expect, accept_unnamed))


_route14 = _rebind(w14.walk_route)  # walk@14's route loop: its side_cell / click_step are ours


def _walk_route(*args: Any, **kwargs: Any) -> dict[str, Any]:
    VISITED.clear()  # E: per route
    return dict(_route14(*args, **kwargs))


walk_route = operator_hud.hook_route(route_plan.hook_route_end(_walk_route))


class SessionLog(w14.SessionLog):
    """walk@14's session log, counting walk@15's route records and stamping its parameters."""

    current: SessionLog | None = None  # type: ignore[assignment]

    def __init__(self, session: str, root: Path | None = None) -> None:
        super().__init__(session, root)
        for cls in (SessionLog, w14.SessionLog, w13.SessionLog, w12.SessionLog):
            cls.current = self

    def start(self, **meta: Any) -> None:
        super().start(**meta, npc_radius=NPC_RADIUS, side_never_visited=True)

    def append(self, rec: Any) -> Any:
        got = super().append(rec)
        if rec.rule == WALK8_RULE:
            self.routes += 1
        return got


DemoLog = SessionLog
run11 = _rebind(w11.run)
finish_session = _rebind(w12.finish_session)
finish_failed = _rebind(w12.finish_failed)
_run12 = _rebind(w12.run)


def run(scene: str, condition: str, n: int, seed: int, label: str, crowd: int,
        fix: str = "where") -> int:  # fmt: skip
    """walk@12's run (every exit finishes the session) with walk@15's unit memory."""
    UNITS["memory"] = NpcClearMemory()
    return int(_run12(scene, condition, n, seed, label, crowd, fix))


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--scene", choices=sorted(SCENES8), required=True)
    ap.add_argument("--condition", choices=("clean", "crowd"), required=True)
    ap.add_argument("--n", type=int, default=56)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--label", default="walk15-alone")
    ap.add_argument("--crowd", type=int, default=4)
    ap.add_argument("--fix", choices=("where", "v2"), default="where")
    a = ap.parse_args()
    for p in (CURSOR_REFS_V2, w5.NOENTRY_MASK):
        if not p.exists():
            raise SystemExit(f"{p} missing: run the cursor calibrations (design time)")
    signal.signal(signal.SIGTERM, _terminate)
    return run(a.scene, a.condition, a.n, a.seed, a.label, a.crowd, a.fix)


if __name__ == "__main__":
    sys.exit(main())
