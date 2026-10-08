#!/usr/bin/env python3
"""walk@13 (docs/demonstrations.md 3.24): walk@12 + REFUSALS BECOME ALTERNATIVES (Batt 2026-10-08:
"safety is solved; the binding problem is now refusals. For walk@13, turn refusals into
ALTERNATIVES ... before declining"; direction approved ~17:00).

walk@12's route loop declined as soon as one round of click points was refused (`unit_stays`,
`no_click_point`), and substituted goals nobody had taken. walk@13's changes, exactly:
1. SHORTER POINTS ON THE POLYLINE. After walk@11's candidates (the farthest in-band cell within
   seg_max, its neighbours, the FARTHER points) come up to SHORTER = 4 nearer cells of the same
   plan, nearest last.
2. RE-PLAN AROUND REFUSALS. When a round clicks nothing, the refused cells join a per-route BLOCKED
   set and the route is planned again around them (`walk6.plan(w, target, blocked)`), at most
   REPLANS = 3 times per route. Lifetimes: a TALK cell (an NPC: NPCs do not move) and a cell with no
   safe point stay blocked for the route; a unit-envelope refusal for UNIT_BLOCK_S = 8 s (the unit
   memory's horizon). The route's target is never blocked. Only then walk@12's patience, substitute
   and decline.
3. A NEARBY GOAL WHEN THE GOAL SITS BESIDE AN NPC. If the goal cell or a cell next to it read TALK
   during the route, the target becomes the nearest walkable cell at Chebyshev distance 1-2 from the
   goal that is not next to any TALK cell and is reachable (`npc_substitute` in the evidence). The
   verifier counts it a success only if the SERVER shows an NPC within one cell of the goal; it is
   reported apart from plain arrivals.
4. "TAKEN" MEANS A UNIT STANDS ON THE GOAL. walk@12 substituted when a unit's ENVELOPE covered a
   click point within one cell of the goal (and the server showed nobody there in 12 of 50 crowd
   routes). walk@13 substitutes only when a fresh sighting in the unit memory (<= TAKEN_FRESH_S) has
   its FEET picked on the target cell; otherwise patience, then a decline.
5. SIGNBOARDS LEAVE THE WORK ZONE. Every candidate pixel inside a signboard's box grown by
   SIGN_MARGIN_PX is refused like a UI-window pixel. The signs come from `poring_env.signboard`
   (by SHAPE; shape only, no NPC requirement: the safe side for a mask) on a frame grabbed at each
   click step.
6. No first-click fix (idle@1: 0 failures in 120).

Everything else is walk@12's: its click step (rebound here so that its points come from walk@13's
zone_points), the TALK-cell block, the work zone, the unit gate, the harness exit, the preview and
the HUD (display only).

    walk13.py --scene indoor|outdoor|guild|town|dungeon|portal --condition clean|crowd --seed S
Pixels in, input out: the rule never reads packets.
"""

from __future__ import annotations

import argparse
import inspect
import signal
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from types import FunctionType
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import operator_hud  # noqa: E402
import ro_agent as r  # noqa: E402
import route_plan  # noqa: E402
import route_preview  # noqa: E402
import walk5 as w5  # noqa: E402
import walk6 as w6  # noqa: E402
import walk11 as w11  # noqa: E402
import walk12 as w12  # noqa: E402
import work_zone as wz  # noqa: E402
from walk11 import (  # noqa: E402
    CLICK_ATTEMPTS,
    CURSOR_REFS_V2,
    PATIENCE_S,
    PORTAL_LOAD_S,
    RELOCS,
    SCENES8,
    STALE_RETRIES,
    TRUST_CLICKS,
    UNCONFIRMED_STREAK,
    UNIT_SHAPES,
    UNITS,
    WAIT_BUDGET_S,
    WALK,
    click_candidates,
    farther_candidates,
    moved,
    preview,
    substitute_goal,
    waypoints,
)
from walk12 import POINTS_K, TALK, _terminate, engine_path, tier_points  # noqa: E402

from poring_env.signboard import find_signs  # noqa: E402

# walk@12's names (its constants and helpers, walk@11's included: the SAME objects). The names below
# are walk@13's own.
OWN = frozenset({"WALK8_RULE", "zone_points", "click_step", "walk_route", "run", "run11", "main",
                 "DemoLog", "SessionLog", "finish_failed", "finish_session"})  # fmt: skip
globals().update({k: v for k, v in vars(w12).items() if not k.startswith("__") and k not in OWN})

WALK8_RULE = "walk@13"
SHORTER = 4  # change 1: nearer cells of the same plan, after walk@11's candidates
REPLANS = 3  # change 2: re-plans around refused cells per route
UNIT_BLOCK_S = 8.0  # change 2: a unit-envelope refusal blocks its cell this long (the memory TTL)
NPC_RINGS = (1, 2)  # change 3: the NPC-adjacent substitute's rings around the goal
TAKEN_FRESH_S = 2.0  # change 4: a sighting this recent, its feet ON the target, is "taken"
# change 5: the sign's hit area ends 10 px past its outline (3.23: 0/5 walked at 5 px, 5/5 at 10)
SIGN_MARGIN_PX = 12.0  # ... + 2 px
SIGNS: dict[str, Any] = {"boxes": [], "t": 0}


def _rebind(fn: Callable[..., Any]) -> Any:
    """A function's code reading its global names from THIS module (walk@12's _walk11, here)."""
    fn = inspect.unwrap(fn)
    if not isinstance(fn, FunctionType):
        raise TypeError(f"not a plain function: {fn!r}")
    g = FunctionType(fn.__code__, globals(), fn.__name__, fn.__defaults__, fn.__closure__)
    g.__kwdefaults__ = fn.__kwdefaults__
    g.__doc__, g.__qualname__ = fn.__doc__, fn.__qualname__
    g.__annotations__ = dict(fn.__annotations__)
    g.__module__ = __name__
    return g


# --- change 5: signboards leave the work zone -----------------------------------------------


def refresh_signs(screen: Any) -> list[list[int]]:
    """The signboards on a frame grabbed NOW (client px, outline boxes)."""
    frame = screen.grab(*r.game_region())[1]
    signs = find_signs(np.ascontiguousarray(frame), exclude=route_preview.UI_WINDOWS)
    boxes = [[s.box.x0, s.box.y0, s.box.x1, s.box.y1] for s in signs]
    SIGNS.update(boxes=boxes, t=r.ns())
    return boxes


def under_sign(u: float, v: float, boxes: Sequence[Sequence[float]] | None = None) -> bool:
    m = SIGN_MARGIN_PX
    for x0, y0, x1, y1 in SIGNS["boxes"] if boxes is None else boxes:
        if x0 - m <= u <= x1 + m and y0 - m <= v <= y1 + m:
            return True
    return False


def zone_points(w: w5.World, end: tuple[int, int]
                ) -> tuple[list[tuple[float, float]], str, list[Any]]:  # fmt: skip
    """walk@12's zone_points with the signboards out of the work zone too (change 5): a pixel over a
    UI window (+12 px) or a sign (+SIGN_MARGIN_PX) does not exist for a click. Tier B only when tier
    A has none; "none" when neither has one."""
    refused: list[list[float]] = []
    for tier in ("A", "B"):
        pts = tier_points(w, end, tier)
        for u, v in pts[:POINTS_K]:
            p = [round(u, 1), round(v, 1)]
            if (not wz.in_work_zone(u, v) or under_sign(u, v)) and p not in refused:
                refused.append(p)
        inside = [(u, v) for u, v in pts if wz.in_work_zone(u, v) and not under_sign(u, v)]
        if inside:
            return inside[:POINTS_K], tier, refused
    return [], "none", refused


_click_step12 = _rebind(w12.click_step)  # walk@12's code; its zone_points is walk@13's (above)


def _click_step(pr: w6.Prober, w: w5.World, end: tuple[int, int],
                expect: str = WALK, accept_unnamed: bool = False) -> dict[str, Any]:  # fmt: skip
    """walk@12's click step on walk@13's work zone: the signs are found on a fresh frame first."""
    boxes = refresh_signs(pr.screen)
    step = _click_step12(pr, w, end, expect, accept_unnamed)
    if boxes:
        step["signs"] = boxes
    return dict(step)


click_step = operator_hud.hook_click_step(route_plan.hook_click_step(_click_step, engine_path))


# --- changes 1-4: the route loop ----------------------------------------------------------------


def shorter_candidates(w: w5.World, path: Sequence[tuple[int, int]], seg_max: int,
                       band: tuple[int, int, int, int], have: Sequence[tuple[int, int]]
                       ) -> list[tuple[int, int]]:  # fmt: skip
    """Change 1: up to SHORTER cells of the same plan NEARER than walk@11's candidates, the nearest
    last (a short click still makes progress)."""
    x0, y0, x1, y1 = band
    idx = [path.index(c) for c in have if c in path]
    first = min(idx) if idx else min(seg_max, len(path))
    out: list[tuple[int, int]] = []
    for i in range(first - 1, -1, -1):
        if len(out) >= SHORTER:
            break
        c = path[i]
        u, v = w.project([c])[0]
        if c not in have and x0 <= u <= x1 and y0 <= v <= y1:
            out.append(c)
    return out


def goal_taken(target: tuple[int, int], now_ns: int) -> list[str]:
    """Change 4: the classes of fresh sightings whose FEET the picking model put ON the target."""
    return [
        it.cls
        for it in UNITS["memory"].items
        if tuple(it.cell) == tuple(target) and (now_ns - it.t_ns) / 1e9 <= TAKEN_FRESH_S
    ]


def near_talk(cell: tuple[int, int], talk: set[tuple[int, int]]) -> bool:
    return any(max(abs(cell[0] - t[0]), abs(cell[1] - t[1])) <= 1 for t in talk)


def npc_substitute(w: w5.World, goal: tuple[int, int], talk: set[tuple[int, int]],
                   blocked: set[tuple[int, int]]) -> tuple[int, int] | None:  # fmt: skip
    """Change 3: the nearest walkable cell (ring 1, then 2; the shortest plan first) around a goal
    beside an NPC, not next to any TALK cell, reachable."""
    for ring in NPC_RINGS:
        best: tuple[int, tuple[int, int]] | None = None
        for dy in range(-ring, ring + 1):
            for dx in range(-ring, ring + 1):
                c = (goal[0] + dx, goal[1] + dy)
                if max(abs(dx), abs(dy)) != ring or c in blocked or c in talk:
                    continue
                if not (0 <= c[1] < w.walkable.shape[0] and 0 <= c[0] < w.walkable.shape[1]):
                    continue
                if not w.walkable[c[1], c[0]] or near_talk(c, talk):
                    continue
                path = w6.plan(w, c, blocked)
                if path is not None and (best is None or len(path) < best[0]):
                    best = (len(path), c)
        if best is not None:
            return best[1]
    return None


def walk_route(pr: w6.Prober, w: w5.World, goal: tuple[int, int], band: tuple[int, int, int, int],
               seg_max: int, log_seg: Any, noentry_mask: Any, read_position: Any = None,
               relocalise: Callable[..., dict[str, Any]] = w11.reloc2.relocalise,
               label: str = "walk@8", expect_goal: str = WALK,
               clock: Callable[[], float] = time.monotonic,
               fixed_at_start: bool = False) -> dict[str, Any]:  # fmt: skip
    """walk@11's route loop (walk@8: plan once, probe only the click point, fix the belief only in
    doubt) with walk@13's changes 1-4. A round that clicks nothing tries, in order: an
    NPC-adjacent goal (3), a re-plan around the refused cells (2, at most REPLANS), then walk@12's
    patience; after patience a substitute ONLY for a unit standing ON the target (4), else the
    decline."""
    events: list[dict[str, Any]] = []
    relocs = clicks = covered = replans = 0
    streak, streak_from = 0, None
    target, substitute, npc_sub = goal, None, None
    waited = 0.0
    unit_since: float | None = None
    fixed = fixed_at_start
    trust_left = TRUST_CLICKS if fixed_at_start else 0
    blocked: set[tuple[int, int]] = set()  # walk@9: targets a click did not walk to
    route_blocked: set[tuple[int, int]] = set()  # change 2: TALK and no-safe-point cells
    unit_blocked: dict[tuple[int, int], float] = {}  # change 2: cell -> clock() it expires
    talk: set[tuple[int, int]] = set()  # every TALK cell read on this route
    fix_fresh = fixed_at_start
    no_move: tuple[tuple[int, int], tuple[int, int]] | None = None

    def done(**kw: Any) -> dict[str, Any]:
        return {"events": events, "relocs": relocs, "clicks": clicks, "covered": covered,
                "substitute": substitute, "npc_substitute": npc_sub, "replans": replans,
                "waited_s": round(waited, 1), **kw}  # fmt: skip

    def blocked_now() -> set[tuple[int, int]]:
        now = clock()
        live = {c for c, t in unit_blocked.items() if t > now}
        out = blocked | route_blocked | live | ({goal} if substitute or npc_sub else set())
        out.discard(target)  # the route's target is never blocked
        return out

    def plan_once() -> list[tuple[int, int]] | None:
        path = w6.plan(w, target, blocked_now())
        if path is not None:
            events.append({"plan": [list(c) for c in waypoints(w.position, path)], "t": r.ns()})
        return path

    def relocate(why: str) -> str | None:
        nonlocal relocs, path, fixed, no_move, trust_left, fix_fresh
        if relocs >= RELOCS:
            return "relocalise_limit"
        rl = relocalise(pr.agent, pr.screen, w, noentry_mask, band)
        relocs += 1
        events.append({"relocalise": rl, "why": why, "t": r.ns()})
        if not rl["ok"]:
            return "relocalise_failed"
        fixed = fix_fresh = True
        if no_move is not None and w.position == no_move[0]:
            blocked.add(no_move[1])
            events.append({"blocked": list(no_move[1]), "t": r.ns()})
        no_move = None
        trust_left = TRUST_CLICKS
        path = plan_once()
        return None if path is not None else "no_plan"

    path = plan_once()
    if path is None:
        return done(decline="no_plan")
    pending: str | None = None
    for _ in range(CLICK_ATTEMPTS):
        if read_position is not None:
            pos = read_position()
            if pos is not None and pos != w.position:
                w.position = pos
                path = plan_once()
                if path is None:
                    return done(decline="no_plan")
        if pending is not None:
            why, pending = pending, None
            if d := relocate(why):
                return done(decline=d)
        if w.position == target:
            preview(pr.agent, w, w.position, [target], None, label)
            return done(arrived_belief=True)
        assert path is not None
        cands = click_candidates(w, path, seg_max, band) + farther_candidates(
            w, path, seg_max, band
        )
        cands += shorter_candidates(w, path, seg_max, band, cands)  # change 1
        if not cands:
            return done(decline="out_of_band")
        clicked = replanned = False
        unit_at: list[tuple[int, int]] = []
        refused: dict[tuple[int, int], str] = {}  # change 2: cell -> why, this round
        for end in cands:
            preview(pr.agent, w, w.position, waypoints(w.position, path), end, label)
            expect = expect_goal if end == goal else WALK
            step = click_step(pr, w, end, expect, accept_unnamed=fixed)
            for _ in range(STALE_RETRIES):
                if step["outcome"] != "stale_background":
                    break
                step = click_step(pr, w, end, expect, accept_unnamed=fixed)
            kept = {k: v for k, v in step.items() if k != "at"}
            events.append({"from": list(w.position), "end": list(end), "t": r.ns(), **kept})
            log_seg(step.get("t_click", r.ns()), w.position, end, step)
            for c in step.get("talk_cells", []):
                talk.add((int(c[0]), int(c[1])))
            if step["clicked"] and expect == "warp":
                n = max(abs(end[0] - w.position[0]), abs(end[1] - w.position[1]))
                time.sleep(n * w5.STEP_S + PORTAL_LOAD_S)
                return done(arrived_belief=True, portal=True)
            if step["clicked"]:
                n = max(abs(end[0] - w.position[0]), abs(end[1] - w.position[1]))
                frm = w.position
                w.position = end
                path = path[path.index(end) + 1 :]
                clicks += 1
                streak, streak_from = 0, None
                unit_since = None
                trust_left -= 1
                fix_fresh = False
                fixed = trust_left > 0
                time.sleep(n * w5.STEP_S + w5.ARRIVE_S)
                clicked = True
                did_move, frac = moved(pr.background, pr.screen.grab(*r.game_region())[1])
                events[-1]["moved"] = {"shifted": did_move, "frac": frac}
                if not did_move:
                    no_move = (frm, end)
                    pending = "no_move"
                    fixed, trust_left = False, 0
                break
            shape = step["target"][-1]["shape"] if step["target"] else None
            if shape == "noentry" and w.walkable[end[1], end[0]]:
                pending = "noentry"
                break
            if step["outcome"] == "no_safe_point":
                refused[end] = "no_safe_point"
                continue
            if step["outcome"].startswith(("covered_", "recheck_")):
                covered += 1
                if step["outcome"] == "covered_talk_cell" or shape == TALK:
                    refused[end] = "talk"
                    unit_at.append(end)
                elif shape in UNIT_SHAPES or step["outcome"] == "covered_unit_envelope":
                    refused[end] = "unit"
                    unit_at.append(end)
                continue
            if step["outcome"] == "unconfirmed":
                streak = streak + 1 if streak_from == w.position else 1
                streak_from = w.position
                if streak >= UNCONFIRMED_STREAK:
                    pending = "unconfirmed"
                    break
                continue
            if step["outcome"] == "neighbour" and fix_fresh:
                if end == target:
                    return done(decline="goal_disputed")
                blocked.add(end)
                events.append({"blocked": list(end), "why": "neighbour_after_fix", "t": r.ns()})
                path = plan_once()
                if path is None:
                    return done(decline="no_plan")
                replanned = True
                break
            if step["outcome"] == "neighbour":
                pending = "neighbour"
                break
        if clicked or replanned or pending is not None:
            continue
        outcomes = [e.get("outcome") for e in events[-len(cands) :]]
        unconfirmed = [o for o in outcomes if o != "no_safe_point"]
        if not unit_at and unconfirmed and all(o == "unconfirmed" for o in unconfirmed):
            pending = "unconfirmed_round"
            continue
        # change 3: the goal (or a cell next to it) read TALK -> a nearby goal, once per route
        if (npc_sub is None and substitute is None and expect_goal == WALK
                and near_talk(goal, talk)):  # fmt: skip
            sub = npc_substitute(w, goal, talk, blocked_now() | {goal})
            events.append({"npc_substitute": None if sub is None else list(sub),
                           "for": list(goal), "talk": sorted(list(c) for c in talk),
                           "t": r.ns()})  # fmt: skip
            if sub is not None:
                npc_sub, target = sub, sub
                unit_since = None
                path = plan_once()
                if path is None:
                    return done(decline="no_plan")
                continue
        # change 2: re-plan around this round's refused cells (never the target)
        if replans < REPLANS and refused:
            now = clock()
            for c, why in refused.items():
                if c == target:
                    continue
                if why == "unit":
                    unit_blocked[c] = now + UNIT_BLOCK_S
                else:
                    route_blocked.add(c)
            route_blocked.update(c for c in talk if c != target)  # the NPCs' own cells too
            new = w6.plan(w, target, blocked_now())
            if new is not None and new != path:
                replans += 1
                path = new
                live = sorted(list(c) for c, t in unit_blocked.items() if t > now)
                events.append({"replan": replans,
                               "blocked": {"route": sorted(list(c) for c in route_blocked),
                                           "unit": live},
                               "plan": [list(c) for c in waypoints(w.position, new)],
                               "t": r.ns()})  # fmt: skip
                continue
            events.append({"replan_none": True, "t": r.ns()})
        if not unit_at:
            return done(decline="no_click_point")
        now = clock()
        unit_since = now if unit_since is None else unit_since
        if now - unit_since < PATIENCE_S and waited < WAIT_BUDGET_S:
            time.sleep(0.5)
            waited += clock() - now
            continue
        # change 4: a substitute only for a unit standing ON the target
        if substitute is None and npc_sub is None and expect_goal == WALK:
            who = goal_taken(target, r.ns())
            events.append({"taken_check": list(target), "on_it": who, "t": r.ns()})
            if who:
                sub = substitute_goal(w, goal, {goal} | blocked_now())
                if sub is None:
                    return done(decline="goal_occupied")
                substitute, target = sub, sub
                events.append({"substitute": list(sub), "for": list(goal), "t": r.ns()})
                unit_since = None
                path = plan_once()
                if path is None:
                    return done(decline="no_plan")
                continue
        return done(decline="unit_stays")
    return done(decline="click_limit")


walk_route = operator_hud.hook_route(route_plan.hook_route_end(walk_route))  # type: ignore[no-redef]


class SessionLog(w12.SessionLog):
    """walk@12's session log, counting walk@13's route records and stamping its parameters."""

    current: SessionLog | None = None  # type: ignore[assignment]

    def __init__(self, session: str, root: Path | None = None) -> None:
        super().__init__(session, root)
        SessionLog.current = self
        w12.SessionLog.current = self

    def start(self, **meta: Any) -> None:
        super().start(**meta, shorter=SHORTER, replans=REPLANS, unit_block_s=UNIT_BLOCK_S,
                      npc_rings=list(NPC_RINGS), taken_fresh_s=TAKEN_FRESH_S,
                      sign_margin_px=SIGN_MARGIN_PX,
                      sign_finder="poring_env.signboard")  # fmt: skip

    def append(self, rec: Any) -> Any:
        got = super().append(rec)
        if rec.rule == WALK8_RULE:
            self.routes += 1
        return got


DemoLog = SessionLog
run11 = _rebind(w11.run)  # walk@11's harness, calling walk@13's walk_route / DemoLog / label
finish_session = _rebind(w12.finish_session)
finish_failed = _rebind(w12.finish_failed)
run = _rebind(w12.run)  # walk@12's decision 3 around run11 (the preview and the HUD enabled)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--scene", choices=sorted(SCENES8), required=True)
    ap.add_argument("--condition", choices=("clean", "crowd"), required=True)
    ap.add_argument("--n", type=int, default=56)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--label", default="walk13-alone")
    ap.add_argument("--crowd", type=int, default=4)
    ap.add_argument("--fix", choices=("where", "v2"), default="where")
    a = ap.parse_args()
    for p in (CURSOR_REFS_V2, w5.NOENTRY_MASK):
        if not p.exists():
            raise SystemExit(f"{p} missing: run the cursor calibrations (design time)")
    signal.signal(signal.SIGTERM, _terminate)
    return int(run(a.scene, a.condition, a.n, a.seed, a.label, a.crowd, a.fix))


if __name__ == "__main__":
    sys.exit(main())
