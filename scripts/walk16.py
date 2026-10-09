#!/usr/bin/env python3
"""walk@16 (docs/demonstrations.md 3.27): walk@15 + F, an NPC-envelope refusal at the goal triggers
walk@13's NPC substitute (Batt, 2026-10-09: "approved ... still judged by the server").

walk@15 (3.26) made zero contacts, but its NPC clearance (D, an NPC's envelope radius 1) refuses a
goal BESIDE an NPC through the unit gate, and walk@13's NPC substitute fired only on a TALK cursor
read. Such a goal waited out its patience and declined `unit_stays` (walk@15 indoor clean route 44:
the goal one cell from an NPC; the gate's nearest box an NPC at 0.0 px, three times).

The one change, exactly:
F. When the click step refuses the route's GOAL (its own points, walk intent, no substitute yet)
   with `covered_unit_envelope` and the gate's nearest unit is an NPC, every remembered NPC
   sighting within NPC_SUB_NEAR = 1 cell of the goal joins the route's TALK set, as if its cell had
   read TALK. walk@13's NPC substitute then runs as it does for a TALK read: ring 1, then 2, never
   on or next to a TALK/NPC cell, the shortest plan first. An NPC two cells away does not trigger
   it (the verifier counts a substitute only with a drawn NPC within one cell of the goal,
   demo_verify.npc_near), and nothing else changes.

Everything else is walk@15's (the same code: walk@14's route loop rebound here, walk@15's memory,
side cells and visited set).

    walk16.py --scene indoor|outdoor|guild|town|dungeon|portal --condition clean|crowd --seed S
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import operator_hud  # noqa: E402
import route_plan  # noqa: E402
import walk5 as w5  # noqa: E402
import walk11 as w11  # noqa: E402
import walk12 as w12  # noqa: E402
import walk13 as w13  # noqa: E402
import walk14 as w14  # noqa: E402
import walk15 as w15  # noqa: E402
from walk11 import CURSOR_REFS_V2, SCENES8, UNITS, WALK  # noqa: E402
from walk12 import _terminate  # noqa: E402

# walk@15's names (and through it walk@14's, 13's, 12's, 11's: the SAME objects); walk@16's follow
globals().update({k: v for k, v in vars(w15).items() if not k.startswith("__")})

WALK8_RULE = "walk@16"
NPC_SUB_NEAR = 1  # F: an NPC sighting this close to the goal (the verifier's npc_near rule)
GOAL: list[tuple[int, int]] = []  # F: the route's goal (one entry while a route runs)


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


# --- F: an NPC-envelope refusal at the goal reads as TALK --------------------------------------


def npc_cells_near(goal: tuple[int, int]) -> list[tuple[int, int]]:
    """The remembered NPC sightings within NPC_SUB_NEAR cells of the goal."""
    return sorted({(int(it.cell[0]), int(it.cell[1])) for it in UNITS["memory"].items
                   if it.cls == "npc" and w14._cheb(it.cell, goal) <= NPC_SUB_NEAR})  # fmt: skip


def click_step(pr: Any, w: Any, end: tuple[int, int], expect: str = WALK,
               accept_unnamed: bool = False) -> dict[str, Any]:  # fmt: skip
    """walk@15's click step (it notes where we stand); F adds the NPC cells beside the goal to the
    step's TALK cells when the goal's own points were refused by an NPC's envelope."""
    step = dict(w15.click_step(pr, w, end, expect, accept_unnamed))
    if not GOAL or end != GOAL[0] or expect != WALK:
        return step
    env = (step["target"][-1].get("envelope") or {}) if step.get("target") else {}
    if step["outcome"] != "covered_unit_envelope" or env.get("nearest") != "npc":
        return step
    cells = npc_cells_near(end)
    if cells:
        known = [list(c) for c in step.get("talk_cells", [])]
        step["talk_cells"] = known + [list(c) for c in cells if list(c) not in known]
        step["npc_envelope_talk"] = [list(c) for c in cells]
    return step


_route14 = _rebind(w14.walk_route)  # walk@14's route loop: its click_step is ours, side_cell 15's


def _walk_route(pr: Any, w: Any, goal: tuple[int, int], *args: Any,
                **kwargs: Any) -> dict[str, Any]:  # fmt: skip
    w15.VISITED.clear()  # E (walk@15): per route
    GOAL[:] = [(int(goal[0]), int(goal[1]))]
    try:
        return dict(_route14(pr, w, goal, *args, **kwargs))
    finally:
        GOAL.clear()


walk_route = operator_hud.hook_route(route_plan.hook_route_end(_walk_route))


class SessionLog(w15.SessionLog):
    """walk@15's session log, counting walk@16's route records and stamping its parameters."""

    current: SessionLog | None = None  # type: ignore[assignment]

    def __init__(self, session: str, root: Path | None = None) -> None:
        super().__init__(session, root)
        for cls in (SessionLog, w15.SessionLog, w14.SessionLog, w13.SessionLog, w12.SessionLog):
            cls.current = self

    def start(self, **meta: Any) -> None:
        super().start(**meta, npc_envelope_substitute=True, npc_sub_near=NPC_SUB_NEAR)

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
    UNITS["memory"] = w15.NpcClearMemory()
    return int(_run12(scene, condition, n, seed, label, crowd, fix))


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--scene", choices=sorted(SCENES8), required=True)
    ap.add_argument("--condition", choices=("clean", "crowd"), required=True)
    ap.add_argument("--n", type=int, default=56)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--label", default="walk16-alone")
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
