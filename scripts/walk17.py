#!/usr/bin/env python3
"""walk@17 (docs/demonstrations.md 3.32; design docs/planning/walk17.md, approved by Batt
2026-10-09): walk@15's decision code + the typing policy, warp areas and long walks.

walk@15 (3.26) is READY (3.28: 186 / 200, 0 safety) but types where@2's pattern ("/ex", then /where
twice) on every relocalisation, which the typing policy forbids from walk@17 on (3.29a), and its
held-out runs walked into warp areas (guild route 0: a goal inside alberta_in's exit warp; iz_dun00:
the exit warp 3 times). Its routes are one A* plan of at most PLAN_MAX = 48 steps, too short for a
walk across a map (tour@1, 3.31).

The changes, exactly:
A. POSITION: the minimap first, /where only where there is none (Batt 2026-10-09 13:42).
   - The RELOCALISATION (walk@8's doubt path, and walk@11's fix at a route's start) reads the
     minimap readout (poring_env.selfpos): two equal reads on two distinct fresh frames, on the
     map, walkable, within PLAUSIBLE_CELLS of the belief. Nothing is typed.
   - Only where NEITHER read shows a readout (the client draws none indoors) does it type /where:
     where@3 (`where_fix.fix_once`), ONE line per need, tagged with its reason class (ADR-0020 #10).
     It is never prepared within the guard's retry interval of walk@17's previous /where, nor once
     the guard refused one for the run's budget or as a 3rd identical line in a row (only another
     slash line resets that count, and walk@17 types none); the typing guard stays the authority.
   - The run's budget: WHERE_PER_ROUTE x its routes (56 for a tuning run), set by
     `chat_guard.start_run` when the session starts (the run id = the session id).
   - A miss (the reads disagree, off the map, not walkable, implausible, a stale frame, no /where
     answer) is no fix: a route START goes on dead reckoning, a DOUBT declines (walk@15's route
     loop: `relocalise_failed`). Nothing is typed again for that need. where@2 (`fix_v2`) and "/ex"
     are never used.
B. WARP AREAS are not walkable for a walk (held-out guild route 0, iz_dun00).
   - The PLANNER (every walk6.plan call of walk@15's decision code and harness: the route loop, the
     re-plan, the substitutes, the side cells, the harness's goal draw and the portal scene's start
     search) blocks every L3 warp trigger area (data/kb/route.json: cell +- span) of the run's map.
     The harness's other start draw (a walkable cell near the scene's start, no plan) is walk@11's,
     unchanged: it is not covered (3.32 states where that matters).
   - Only a plan whose intent IS the portal (expect_goal="warp"; the portal scene's harness search)
     may enter the area(s) holding its goal. Every other area stays blocked for it too.
   - The CLICK STEP refuses a walk click whose cell lies inside a warp area (no_safe_point).
   - So the HARNESS never draws a goal inside a warp area (its goal draw plans with this planner).
   - A map that route.json does not list fails CLOSED: the run refuses to start.
C. LONG WALKS: chained legs through waypoints (Batt 13:42, tour@1).
   - A route whose A* path (warp areas blocked, no length limit) is longer than PLAN_MAX = 48 steps
     is split into legs at waypoints: cells of that path about every LEG_STEPS = 40 steps, each
     walkable and outside every warp area, each leg at most PLAN_MAX steps.
   - Each leg is walked by walk@15's route loop as a route is today; the route's own intent
     (a portal) applies to its last leg only.
   - No click is farther than CLICK_MAX_SAFE = 14 server steps (docs/planning/poring-nav.md): the
     rules' farthest candidate is SEG_OPEN + 3 + FARTHER = 12 cells along the plan (asserted at
     import), and the click step refuses a cell whose server path (the GAT's own A*) is longer.
D. The HARNESS as on main (3.29a): walk@11's run with @killmonster2 only when CLEAN needs it, the
   typing guard, open_chat's re-check, the portal target fix, and the detector's batch log
   (detections.jsonl in the session).
AMENDMENT 4 (Batt 2026-10-15, decision 4: "Client GAT vs server map cache: every walk rule and
planner uses only cells walkable in BOTH sources (intersection)"): the cells the client's GAT calls
walkable but the SERVER's map cache does not let a character stand on (poring_dataset.walkable;
its last row and column included) join B's mechanisms, for EVERY intent:
   - every plan blocks them (warp_blocked; the portal's plans too);
   - the harness's start draw never offers them (`_Walk5`'s world, every scene);
   - the CLICK STEP refuses a click on one (no_safe_point, "server_nopass"), the portal click too.
   - A map either source lacks fails CLOSED: the run refuses to start.
   On the tuning maps it changes nothing: prt_church has no such cell; prt_fild08's 799 all lie on
   the server's last row / column, none 8-adjacent to a client-walkable cell off that row / column
   (no plan from the map's interior can reach them).
NOT carried: walk@16's F (Batt 2026-10-09 ~14:00: "no measurable effect beyond run-to-run noise;
fewer rules"). Everything else is walk@15's, the same code rebound here: walk@14's route loop,
walk@15's NPC clearance (D) and side cells never where the route stood (E), walk@13's click step.
walk@15's module is untouched (test_walk17.py; scripts/bytecode_proof.py).

    walk17.py --scene indoor|outdoor|guild|town|dungeon|portal --condition clean|crowd --seed S
Pixels in, input out: the rule never reads packets.
"""

from __future__ import annotations

import argparse
import contextlib
import inspect
import json
import signal
import sys
import time
import types
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chat_guard  # noqa: E402
import operator_hud  # noqa: E402
import ro_agent as r  # noqa: E402
import route_plan  # noqa: E402
import walk5 as _walk5  # noqa: E402
import walk6 as _walk6  # noqa: E402
import walk11 as w11  # noqa: E402
import walk12 as w12  # noqa: E402
import walk13 as w13  # noqa: E402
import walk14 as w14  # noqa: E402
import walk15 as w15  # noqa: E402
import where_fix as wf  # noqa: E402
from walk11 import CURSOR_REFS_V2, FARTHER, SCENES8, SEG_INDOOR, SEG_OPEN, UNITS, WALK  # noqa: E402
from walk12 import _terminate  # noqa: E402
from walk15 import VISITED  # noqa: E402  (E's set: the SAME object walk@15's code fills)

from poring_env import selfpos  # noqa: E402

# walk@15's names (and through it walk@14's, 13's, 12's, 11's: the SAME objects); walk@17's follow
globals().update({k: v for k, v in vars(w15).items() if not k.startswith("__")})

WALK8_RULE = "walk@17"

# A: the relocalisation
PLAUSIBLE_CELLS = wf.PLAUSIBLE_CELLS  # 6: a fix farther than this from the belief is refused
MINIMAP_GAP_S = 0.15  # between the two reads (loot@1's minimap_cell)
MINIMAP_FRESH_TRIES = 6  # grabs for a second, DISTINCT frame before the pair is "stale"
WHERE_PER_ROUTE = 1  # the run's /where budget = this x its routes (56 for a tuning run)
REASON_START = "walk@17 route_start_indoor"  # ADR-0020 #10's reason classes (indoor = no readout)
REASON_DOUBT = "walk@17 belief_in_doubt"
DIGITS = r.ROOT / selfpos.DEFAULT_TEMPLATES  # the minimap digit templates (data/, local)
WHERE: dict[str, Any] = {"last_t": None, "spent": None, "retry_s": None, "asked": 0, "held": 0}
SPENT = ("guard:where_budget", "guard:repeat")  # guard refusals that hold for the rest of the run

# B: warp areas
ROUTE_KB = r.ROOT / "data/kb/route.json"  # L3 warps (local, never committed)
# "nopass" (amendment 4): the cells the client calls walkable and the SERVER's map cache does not
WARPS: dict[str, Any] = {"map": None, "areas": [], "cells": frozenset(), "intent": WALK,
                         "nopass": frozenset()}  # fmt: skip
ROUTE: dict[str, Any] = {"active": False, "intent": WALK}  # set while a route (leg) runs

# C: long walks
PLAN_MAX = _walk5.PLAN_MAX  # 48: one leg = one walk6.plan
LEG_STEPS = 40  # a waypoint about every this many steps of the full path
FULL_MAX = 10_000  # the full path's A* has no practical length limit
CLICK_MAX_SAFE = 14  # the server's unconditional per-click limit (poring-nav.md section 2)
assert max(SEG_INDOOR, SEG_OPEN) + 3 + FARTHER <= CLICK_MAX_SAFE  # the farthest candidate (C)


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


# --- A: the minimap first, /where only where there is none ---------------------------------------


def reset_where() -> None:
    """A new run: no /where asked yet, nothing spent, the guard's retry interval (L2)."""
    WHERE.update(last_t=None, spent=None, asked=0, held=0,
                 retry_s=float(chat_guard.policy()["where_retry_s"]))  # fmt: skip


def _grab(screen: Any) -> tuple[Any, int, int]:
    """(the game region, BGR; the frame bus's frame_id or -1; its time)."""
    region = r.game_region()
    meta = getattr(screen, "grab_meta", None)
    if meta is not None:
        t, img, fid, _ = meta(*region)
    else:
        t, img = screen.grab(*region)
        fid = -1
    return np.asarray(img)[..., :3], int(fid), int(t)


def minimap_fix(screen: Any, digits: Any, belief: tuple[int, int],
                walkable: Any) -> dict[str, Any]:  # fmt: skip
    """A: our cell from the minimap readout -- two reads on two DISTINCT fresh frames (a new
    frame_id on the frame bus, else a new grab time), equal, on the map, walkable, within
    PLAUSIBLE_CELLS of ``belief``. ``why`` is "ok", "no_readout" (neither read shows one: the only
    case in which /where may be typed), or the miss: "stale", "disagree", "off_map",
    "not_walkable", "implausible". Nothing is typed here."""
    img, fid, t = _grab(screen)
    first = selfpos.read_minimap(img, digits)
    second = None
    for _ in range(MINIMAP_FRESH_TRIES):
        time.sleep(MINIMAP_GAP_S)
        img2, fid2, t2 = _grab(screen)
        if (fid2 != fid) if (fid >= 0 and fid2 >= 0) else (t2 != t):
            second = selfpos.read_minimap(img2, digits)
            break
    reads = [first.xy, None if second is None else second.xy]
    out: dict[str, Any] = {"reads": [None if x is None else list(x) for x in reads],
                           "reasons": [first.reason, "stale" if second is None else second.reason],
                           "xy": None, "t": r.ns()}  # fmt: skip
    a, b = reads
    if second is None:
        return {**out, "why": "stale"}
    if a is None and b is None:
        return {**out, "why": "no_readout"}
    if a is None or b is None or a != b:
        return {**out, "why": "disagree"}
    x, y = a
    if not (0 <= y < walkable.shape[0] and 0 <= x < walkable.shape[1]):
        return {**out, "why": "off_map"}
    if not walkable[y, x]:
        return {**out, "why": "not_walkable"}
    if max(abs(x - belief[0]), abs(y - belief[1])) > PLAUSIBLE_CELLS:
        return {**out, "why": "implausible"}
    return {**out, "xy": (x, y), "why": "ok"}


def where_held(now: float) -> str | None:
    """A: why walk@17 does not even PREPARE a /where now (activating the client, the chat area's
    baseline): within the guard's retry interval of its own previous one, or after the guard
    refused one for the rest of the run (SPENT: the budget, or a 3rd identical slash line in a
    row). The guard stays the authority: it also counts other processes' lines."""
    if WHERE["spent"]:
        return str(WHERE["spent"])
    last, retry = WHERE["last_t"], WHERE["retry_s"]
    if retry is None:
        retry = WHERE["retry_s"] = float(chat_guard.policy()["where_retry_s"])
    if last is not None and 0 <= now - last < retry:
        return "where_retry"
    return None


def _where_relocalise(templates: dict[str, Any],
                      digits: Any = None) -> Callable[..., dict[str, Any]]:  # fmt: skip
    """A: walk@15's relocalisation interface (walk@11's `where_relocalise(templates)` factory, the
    /where templates), minimap first. ``digits``: the minimap's (default: DIGITS)."""
    mm_digits = selfpos.load_digit_templates(DIGITS) if digits is None else digits

    def relocalise(agent: Any, screen: Any, w: Any, mask: Any, band: Any) -> dict[str, Any]:
        mm = minimap_fix(screen, mm_digits, w.position, w.walkable)
        if mm["xy"] is not None:
            old, w.position = w.position, tuple(mm["xy"])
            return {"ok": True, "from": list(old), "to": list(w.position), "method": "minimap",
                    "minimap": mm, "rejects": [], "t": mm["t"]}  # fmt: skip
        if mm["why"] != "no_readout":  # the client shows a readout here: a miss, nothing typed
            return {"ok": False, "left": None, "method": "minimap", "minimap": mm,
                    "rejects": [f"minimap:{mm['why']}"], "t": mm["t"]}  # fmt: skip
        reason = REASON_DOUBT if ROUTE["active"] else REASON_START
        now = time.monotonic()
        held = where_held(now)
        if held is not None:
            WHERE["held"] += 1
            return {"ok": False, "left": None, "method": "where", "minimap": mm, "reason": reason,
                    "rejects": [f"held:{held}"], "t": r.ns()}  # fmt: skip
        WHERE["last_t"], WHERE["asked"] = now, WHERE["asked"] + 1
        got = wf.fix_once(agent, screen, templates, w.position, w.walkable, reason)
        spent = [x for x in got["rejects"] if x in SPENT]
        if spent:
            WHERE["spent"] = spent[0].removeprefix("guard:")
        if got["xy"] is None:
            return {"ok": False, "left": None, "method": "where", "minimap": mm, "reason": reason,
                    "rejects": got["rejects"], "t": got["t"]}  # fmt: skip
        old, w.position = w.position, tuple(got["xy"])
        return {"ok": True, "from": list(old), "to": list(w.position), "method": "where",
                "minimap": mm, "reason": reason, "rejects": [], "t": got["t"]}  # fmt: skip

    return relocalise


# the live preview's fix display (display only), as walk@12 hooks walk@11's factory
where_relocalise = route_plan.hook_relocalise(_where_relocalise)


# --- B: warp areas are not walkable for a walk ---------------------------------------------------


def warp_areas(mapname: str, kb: Path | None = None) -> list[dict[str, Any]]:
    """The map's L3 warp trigger areas (cell +- span). A map route.json does not list fails
    CLOSED: walk@17's B cannot hold there."""
    route = json.loads((ROUTE_KB if kb is None else kb).read_text())
    if mapname not in route["warps"]:
        raise SystemExit(f"walk@17: {mapname} has no L3 warp list (data/kb/route.json): warp areas "
                         "unknown, B cannot hold -- extend the KB first (kb_route.py)")  # fmt: skip
    out = []
    for x in route["warps"][mapname]:
        cx, cy, sx, sy = int(x["x"]), int(x["y"]), int(x["span_x"]), int(x["span_y"])
        cells = frozenset((cx + dx, cy + dy) for dx in range(-sx, sx + 1)
                          for dy in range(-sy, sy + 1))  # fmt: skip
        out.append({"cell": (cx, cy), "span": (sx, sy), "to_map": x.get("to_map"), "cells": cells})
    return out


def server_nopass(mapname: str) -> frozenset[tuple[int, int]]:
    """Amendment 4 (decision 4): the cells the client's GAT calls walkable but the SERVER's map
    cache does not let a character stand on (poring_dataset.walkable.both False there). A map
    either source lacks fails CLOSED."""
    from poring_dataset import walkable as wk

    try:
        gat, both = wk.load_both(mapname)
    except wk.MapSourceError as exc:
        raise SystemExit(f"walk@17: {exc} -- amendment 4 cannot hold") from None
    ys, xs = np.nonzero(np.asarray(gat.walkable(), dtype=bool) & ~both)
    return frozenset(zip(xs.tolist(), ys.tolist(), strict=True))


def use_map(mapname: str, intent: str = WALK, areas: list[dict[str, Any]] | None = None,
            nopass: frozenset[tuple[int, int]] | None = None) -> None:  # fmt: skip
    """The run's map (its warp areas, the server's NOPASS cells) and the harness's own plan intent
    ("warp" only for the portal scene, whose start search plans TO the portal)."""
    got = warp_areas(mapname) if areas is None else areas
    off = server_nopass(mapname) if nopass is None else frozenset(nopass)
    WARPS.update(map=mapname, areas=got, intent=intent, nopass=off,
                 cells=frozenset().union(*(a["cells"] for a in got)))  # fmt: skip


def warp_area_of(cell: Sequence[int]) -> dict[str, Any] | None:
    c = (int(cell[0]), int(cell[1]))
    return next((a for a in WARPS["areas"] if c in a["cells"]), None)


def plan_intent() -> str:
    return str(ROUTE["intent"] if ROUTE["active"] else WARPS["intent"])


def warp_blocked(goal: Sequence[int]) -> frozenset[tuple[int, int]]:
    """B: the cells a plan to ``goal`` may not enter -- every warp area, except, for the portal
    intent only, the area(s) holding the goal; and (amendment 4) every server-NOPASS cell, for
    every intent."""
    if WARPS["map"] is None:
        raise RuntimeError("walk@17: no map's warp areas are loaded (use_map): fail closed")
    if plan_intent() != "warp":
        return frozenset(WARPS["cells"]) | WARPS["nopass"]
    g = (int(goal[0]), int(goal[1]))
    keep = [a["cells"] for a in WARPS["areas"] if g not in a["cells"]]
    return frozenset().union(*keep) | WARPS["nopass"]


class _Walk6:
    """walk6 as walk@17's code sees it: every name is walk6's, except `plan` (B)."""

    def __getattr__(self, name: str) -> Any:
        return getattr(_walk6, name)

    @staticmethod
    def plan(w: Any, goal: tuple[int, int], blocked: set[tuple[int, int]]) -> Any:
        """walk6.plan with every warp area blocked (B), unless this plan's intent is the portal."""
        return _walk6.plan(w, goal, set(blocked) | warp_blocked(goal))


w6 = _Walk6()


class _Walk5:
    """walk5 as walk@17's code sees it: every name is walk5's, except `World` (AMENDMENT, Batt
    2026-10-13, decision 15: "never draw a harness start inside a warp area"). In a WALK scene the
    world's `walkable` grid offers no warp-area cell, so walk@11's seeded start draw (a walkable
    cell within +-8 of the scene's start, no plan check) can never land inside a trigger area. The
    planner's grid is untouched (B blocks those cells already); the portal scene's world is
    unchanged (its start search plans TO the portal). AMENDMENT 4 (decision 4): in EVERY scene the
    world offers no server-NOPASS cell either."""

    def __getattr__(self, name: str) -> Any:
        return getattr(_walk5, name)

    @staticmethod
    def World(camera: Any, gat: Any, position: tuple[int, int]) -> Any:  # noqa: N802
        world = _walk5.World(camera, gat, position)
        if WARPS["map"] is not None:
            hide = WARPS["nopass"] | (WARPS["cells"] if plan_intent() != "warp" else frozenset())
            if hide:
                walk = np.array(world.walkable, dtype=bool, copy=True)
                for x, y in hide:
                    if 0 <= y < walk.shape[0] and 0 <= x < walk.shape[1]:
                        walk[y, x] = False
                world.walkable = walk
        return world


w5 = _Walk5()

# the decision code that PLANS, rebound so that its planner is walk@17's (B); the same code
substitute_goal = _rebind(w11.substitute_goal)  # walk@8's substitute ring
npc_substitute = _rebind(w13.npc_substitute)  # walk@13's change 3
_side14 = _rebind(w14.side_cell)  # walk@14's B


def side_cell(w: Any, target: tuple[int, int], blocked: set[tuple[int, int]],
              talk: set[tuple[int, int]], tried: set[tuple[int, int]]
              ) -> tuple[int, int] | None:  # fmt: skip
    """walk@15's side cell (E: every cell this route stood on counts as tried) on walk@14's
    search, rebound to walk@17's planner (B)."""
    return _side14(w, target, blocked, talk, tried | VISITED)  # type: ignore[no-any-return]


@contextlib.contextmanager
def _route(intent: str) -> Iterator[None]:
    """While a route (leg) runs: its plan intent (B) and the /where reason class (A)."""
    old = dict(ROUTE)
    ROUTE.update(active=True, intent=intent)
    try:
        yield
    finally:
        ROUTE.clear()
        ROUTE.update(old)


# --- B + C: the click step ------------------------------------------------------------------------


def server_steps(w: Any, end: Sequence[int]) -> int | None:
    """C: the server's own path length from the believed cell to ``end`` (the GAT's A*, nothing
    of ours blocked), None beyond CLICK_MAX_SAFE or with no path."""
    from poring_dataset.walk import walk_path

    path = walk_path(_walk6.Grid(w.walkable, set()), int(w.position[0]), int(w.position[1]),
                     int(end[0]), int(end[1]), max_len=CLICK_MAX_SAFE)  # fmt: skip
    return None if path is None else len(path)


def click_step(pr: Any, w: Any, end: tuple[int, int], expect: str = WALK,
               accept_unnamed: bool = False) -> dict[str, Any]:  # fmt: skip
    """walk@15's click step (it notes where we stand, E). Before it, three refusals, all
    "no_safe_point" for walk@15's route loop (the next point; the cell re-planned around):
    B: a walk click whose cell lies inside a warp area (the portal click is the portal's);
    amendment 4: a click (any intent) on a cell the SERVER does not let a character stand on;
    C: a cell farther than CLICK_MAX_SAFE server steps."""
    if expect == WALK and (area := warp_area_of(end)) is not None:
        VISITED.add((int(w.position[0]), int(w.position[1])))
        return {"clicked": False, "outcome": "no_safe_point", "target": [], "tier": "none",
                "warp_area": list(area["cell"])}  # fmt: skip
    if (int(end[0]), int(end[1])) in WARPS["nopass"]:
        VISITED.add((int(w.position[0]), int(w.position[1])))
        return {"clicked": False, "outcome": "no_safe_point", "target": [], "tier": "none",
                "server_nopass": [int(end[0]), int(end[1])]}  # fmt: skip
    if server_steps(w, end) is None:
        VISITED.add((int(w.position[0]), int(w.position[1])))
        return {"clicked": False, "outcome": "no_safe_point", "target": [], "tier": "none",
                "beyond_click_max": CLICK_MAX_SAFE}  # fmt: skip
    return dict(w15.click_step(pr, w, end, expect, accept_unnamed))


# --- C: long walks, chained legs ------------------------------------------------------------------


def full_path(w: Any, goal: tuple[int, int]) -> list[tuple[int, int]] | None:
    """C: the route's whole A* path, warp areas blocked (B), no practical length limit."""
    from poring_dataset.walk import walk_path

    got = walk_path(_walk6.Grid(w.walkable, set(warp_blocked(goal))), int(w.position[0]),
                    int(w.position[1]), int(goal[0]), int(goal[1]), max_len=FULL_MAX)  # fmt: skip
    return None if got is None else [(int(x), int(y)) for x, y in got]


def leg_ends(path: Sequence[tuple[int, int]], walkable: Any) -> list[int] | None:
    """C: the indices on ``path`` where legs end: a waypoint about every LEG_STEPS steps (walkable,
    outside every warp area, the nearest such cell to the mark), each leg at most PLAN_MAX steps;
    the goal's index last. None: no waypoint fits a leg."""
    n, i, ends = len(path), 0, []
    while n - i > PLAN_MAX:
        mark = i + LEG_STEPS - 1
        span = range(i, min(n - 1, i + PLAN_MAX))
        for k in sorted(span, key=lambda j: (abs(j - mark), j)):
            x, y = path[k]
            if walkable[y, x] and warp_area_of((x, y)) is None:
                break
        else:
            return None
        ends.append(k)
        i = k + 1
    ends.append(n - 1)
    return ends


_route14 = _rebind(w14.walk_route)  # walk@14's route loop: click_step, side_cell, w6 are walk@17's
_leg15 = _rebind(w15._walk_route)  # walk@15's route (VISITED cleared) around it: ONE leg


def _walk_route(pr: Any, w: Any, goal: tuple[int, int], *args: Any, expect_goal: str = WALK,
                fixed_at_start: bool = False, **kwargs: Any) -> dict[str, Any]:  # fmt: skip
    """C: a route no longer than PLAN_MAX is walk@15's route, unchanged; a longer one is walked as
    legs through waypoints, each leg walk@15's route. The record is the legs' events in order
    (a {"leg": ...} mark before each), their counts summed, and the end (decline, arrival, the
    goal's substitutes) of the leg that ended the route."""
    goal = (int(goal[0]), int(goal[1]))
    with _route(expect_goal):
        path = full_path(w, goal)
        if path is None or len(path) <= PLAN_MAX:
            did = dict(_leg15(pr, w, goal, *args, expect_goal=expect_goal,
                              fixed_at_start=fixed_at_start, **kwargs))  # fmt: skip
            return {**did, "legs": 1}
        ends = leg_ends(path, w.walkable)
        if ends is None:
            return {"events": [], "relocs": 0, "clicks": 0, "covered": 0, "substitute": None,
                    "npc_substitute": None, "replans": 0, "sides": 0, "waited_s": 0.0,
                    "decline": "no_waypoint", "legs": 0, "full_steps": len(path)}  # fmt: skip
    wps = [path[k] for k in ends[:-1]]
    label = str(kwargs.pop("label", "walk@8"))
    done: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for j, k in enumerate(ends):
        last = j == len(ends) - 1
        to, intent = (goal, expect_goal) if last else (path[k], WALK)
        mark = {"leg": j + 1, "of": len(ends), "from": list(w.position), "to": list(to),
                "t": r.ns()}  # fmt: skip
        with _route(intent):
            did = dict(_leg15(pr, w, to, *args, expect_goal=intent,
                              fixed_at_start=fixed_at_start if j == 0 else False,
                              label=f"{label} leg {j + 1}/{len(ends)}", **kwargs))  # fmt: skip
        done.append((mark, did))
        if not last and not did.get("arrived_belief"):
            break
    return merge_legs(done, len(ends), wps, len(path))


def merge_legs(done: list[tuple[dict[str, Any], dict[str, Any]]], n_legs: int,
               wps: list[tuple[int, int]], steps: int) -> dict[str, Any]:  # fmt: skip
    """C: one route record from its legs (see _walk_route)."""
    mark, end = done[-1]
    finished = len(done) == n_legs  # the goal's own leg ran: its substitutes are the route's
    out = dict(end)
    out["events"] = [e for m, d in done for e in (m, *d.get("events", []))]
    for key in ("relocs", "clicks", "covered", "replans", "sides"):
        out[key] = sum(int(d.get(key) or 0) for _, d in done)
    out["waited_s"] = round(sum(float(d.get("waited_s") or 0) for _, d in done), 1)
    if not finished:
        out["substitute"] = out["npc_substitute"] = None
        out["decline"] = end.get("decline") or "leg_unfinished"
        out["leg_declined"] = mark["leg"]
    out["legs"] = n_legs
    out["legs_walked"] = len(done)
    out["full_steps"] = steps
    out["waypoints"] = [list(c) for c in wps]
    keys = ("decline", "arrived_belief", "substitute", "npc_substitute", "clicks", "relocs")
    out["leg_ends"] = [{"to": m["to"], **{k: d.get(k) for k in keys}} for m, d in done]
    return out


walk_route = operator_hud.hook_route(route_plan.hook_route_end(_walk_route))


# --- the session and the harness (D) --------------------------------------------------------------


class SessionLog(w15.SessionLog):
    """walk@15's session log, counting walk@17's route records and stamping its parameters. Its
    start opens the run's /where budget in the typing guard (A): the run id is the session id."""

    current: SessionLog | None = None  # type: ignore[assignment]

    def __init__(self, session: str, root: Path | None = None) -> None:
        super().__init__(session, root)
        for cls in (SessionLog, w15.SessionLog, w14.SessionLog, w13.SessionLog, w12.SessionLog):
            cls.current = self

    def start(self, **meta: Any) -> None:
        budget = WHERE_PER_ROUTE * int(meta.get("n") or 0)
        reset_where()
        chat_guard.start_run(self.session, budget)
        areas = [{"cell": list(a["cell"]), "span": list(a["span"]), "to_map": a["to_map"]}
                 for a in WARPS["areas"]]  # fmt: skip
        super().start(**meta, minimap_first=True, where_run=self.session, where_budget=budget,
                      where_retry_s=WHERE["retry_s"], warp_map=WARPS["map"], warp_areas=areas,
                      walkable="client∩server", server_nopass_cells=len(WARPS["nopass"]),
                      plan_max=PLAN_MAX, leg_steps=LEG_STEPS, click_max_safe=CLICK_MAX_SAFE,
                      npc_envelope_substitute=False)  # fmt: skip

    def append(self, rec: Any) -> Any:
        got = super().append(rec)
        if rec.rule == WALK8_RULE:
            self.routes += 1
        return got


DemoLog = SessionLog
run11 = _rebind(w11.run)  # walk@11's harness (3.29a): walk@17's route, relocalisation, planner, log
finish_session = _rebind(w12.finish_session)
finish_failed = _rebind(w12.finish_failed)
_run12 = _rebind(w12.run)


def run(scene: str, condition: str, n: int, seed: int, label: str, crowd: int,
        fix: str = "where") -> int:  # fmt: skip
    """walk@12's run (every exit finishes the session) with walk@15's unit memory, the map's warp
    areas (B; an unlisted map refuses to start), its server-NOPASS cells (amendment 4; a map
    either source lacks refuses to start) and a fresh /where state (A)."""
    if fix != "where":
        raise SystemExit("walk@17 relocalises by the minimap and where@3 only (fix='where')")
    use_map(SCENES8[scene][0], "warp" if scene == "portal" else WALK)
    reset_where()
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
    ap.add_argument("--label", default="walk17-alone")
    ap.add_argument("--crowd", type=int, default=4)
    a = ap.parse_args()
    for p in (CURSOR_REFS_V2, w5.NOENTRY_MASK, wf.TEMPLATES_V2, DIGITS, ROUTE_KB):
        if not p.exists():
            raise SystemExit(f"{p} missing: run the calibrations / the KB build (design time)")
    signal.signal(signal.SIGTERM, _terminate)
    return run(a.scene, a.condition, a.n, a.seed, a.label, a.crowd, "where")


if __name__ == "__main__":
    sys.exit(main())
