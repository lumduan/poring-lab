#!/usr/bin/env python3
"""walk@14 (docs/demonstrations.md 3.25): walk@13 + the two failure causes its tuning runs showed.

walk@13 (3.24) indoor CLEAN scored 46 / 50 and indoor CROWD 40 / 50, with zero safety events. The
failures (indoor clean's four, then crowd's ten: 6 no_click_point, 2 relocalise_limit, 1 unit_stays,
1 npc_substitute the server did not justify):
- 2 x `unit_stays` (routes 6, 47): a "monster" envelope covered the goal for a whole minute. The
  server had NO monster there: all 29 monster refusals of that clean run were the v0 detector
  reading a church NPC (Pastor#1011 at (87, 127) / Crusader at (95, 127)) as a monster. An NPC
  read as a monster gets a monster's growing envelope instead of an NPC's radius 0, and it never
  moves away, so patience cannot help;
- 2 x `no_click_point` (routes 19, 41): the route stopped one cell short. The GOAL cell itself had
  no safe point / a re-check read unknown from the last cell, and walk@13 never re-plans its target.

The three changes, exactly:
A. A STATIC UNIT keeps a small envelope. A sighting that has stayed within STATIC_JITTER cell of
   where its current streak began, for >= STATIC_S seconds over >= STATIC_SEEN sightings, gets
   STATIC_RADIUS (1 cell: one step within the click latency) instead of the growing radius.
   rAthena's monsters pause <= 5 s between moves (walk11's PATIENCE_S); a unit still for 8 s is an
   immobile monster (a plant), an NPC read as a monster, or scenery. Its own box is still refused.
C. A CELL REFUSED BY AN UNKNOWN OR RE-CHECK READ (`covered_unknown`, `recheck_*`, not a unit, not
   TALK) joins the per-route blocked set, like walk@13's no-safe-point cells, so the re-plan goes
   around it. walk@13 left those cells out (crowd route 0 declined from its start after 2 unknown
   reads, with no re-plan).
B. APPROACH THE TARGET FROM ANOTHER SIDE. When a round clicks nothing and the TARGET's own points
   were refused for a non-unit reason (no safe point, a re-check, an unconfirmed read), the rule
   walks first to a SIDE cell: Chebyshev 1-2 from the target, walkable, reachable, not next to a
   TALK cell, not where we stand, from which the target HAS work-zone points (the picking model);
   the shortest plan first. At most SIDES = 2 per route, then walk@13's own steps.

Everything else is walk@13's (its click step with the sign mask, its route-loop changes 1-4, the
harness, the preview and the HUD). walk@13's module is untouched (test_walk14.py).

    walk14.py --scene indoor|outdoor|guild|town|dungeon|portal --condition clean|crowd --seed S
Pixels in, input out: the rule never reads packets.
"""

from __future__ import annotations

import argparse
import copy
import inspect
import math
import signal
import sys
import time
import types
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import operator_hud  # noqa: E402
import ro_agent as r  # noqa: E402
import route_plan  # noqa: E402
import unit_gate as ug  # noqa: E402
import walk5 as w5  # noqa: E402
import walk6 as w6  # noqa: E402
import walk11 as w11  # noqa: E402
import walk12 as w12  # noqa: E402
import walk13 as w13  # noqa: E402
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
from walk12 import TALK, _terminate, tier_points  # noqa: E402
from walk13 import (  # noqa: E402
    REPLANS,
    UNIT_BLOCK_S,
    click_step,
    goal_taken,
    near_talk,
    npc_substitute,
    shorter_candidates,
)

# walk@13's names (walk@12's and walk@11's included: the SAME objects); walk@14's own follow
globals().update({k: v for k, v in vars(w13).items() if not k.startswith("__")})

WALK8_RULE = "walk@14"
STATIC_S = 8.0  # A: still this long (rAthena's idle pause <= 5 s + margin) ...
STATIC_SEEN = 3  # ... over at least this many sightings ...
STATIC_JITTER = 1  # ... within this many cells of where the streak began (box jitter)
STATIC_RADIUS = 1  # ... keeps this envelope: one step within the click latency
SIDES = 2  # B: side approaches per route
SIDE_RINGS = (1, 2)


# --- A: a static unit keeps a small envelope -----------------------------------------------------


@dataclass
class StaticSeen(ug.Seen):
    anchor: tuple[int, int] = (0, 0)  # where the current streak began
    since_ns: int = 0  # when it began
    n: int = 1  # sightings in the streak


class StaticMemory(ug.UnitMemory):
    """walk@11's unit memory (the SAME matching and TTL: ug.UnitMemory.observe's code) plus each
    unit's STILL streak: where it began, when, and how many sightings."""

    items: list[StaticSeen]  # type: ignore[assignment]

    def observe(self, boxes: Sequence[Any], camera: Any, gat: Any, belief: tuple[int, int],
                t_ns: int, monster_ms_per_cell: int, pick: Any = None) -> None:  # fmt: skip
        if pick is None:
            from poring_dataset.picking import pick_cells as pick
        self_px = camera.project(np.zeros((1, 2)), np.zeros(1))[0]
        self.items = [i for i in self.items if (t_ns - i.t_ns) / 1e9 <= self.ttl_s]
        for b in boxes:
            fx, fy = b.foot
            if math.hypot(fx - self_px[0], fy - self_px[1]) <= ug.SELF_PX:
                continue
            rel = tuple(int(c) for c in pick(camera, gat, belief, np.array([[fx, fy]]))[0])
            if abs(rel[0]) > 10**5:
                rel = ug._nearest_cell(camera, fx, fy)
            cell = (belief[0] + rel[0], belief[1] + rel[1])
            best, bi = None, None
            for i, it in enumerate(self.items):
                if it.cls != b.cls:
                    continue
                reach = ug.radius_cells(b.cls, (t_ns - it.t_ns) / 1e9, monster_ms_per_cell)
                d = _cheb(it.cell, cell)
                if d <= max(reach, 1) and (best is None or d < best):
                    best, bi = d, i
            anchor, since, n = cell, t_ns, 1
            if bi is not None:
                prev = self.items[bi]
                if _cheb(prev.anchor, cell) <= STATIC_JITTER:
                    anchor, since, n = prev.anchor, prev.since_ns, prev.n + 1
            seen = StaticSeen(b.cls, cell, b.x1 - b.x0, b.y1 - b.y0, t_ns, anchor, since, n)
            if bi is None:
                self.items.append(seen)
            else:
                self.items[bi] = seen

    def envelopes(self, camera: Any, gat: Any, belief: tuple[int, int], now_ns: int,
                  horizon_s: float, monster_ms_per_cell: int) -> list[ug.Envelope]:  # fmt: skip
        out: list[ug.Envelope] = []
        for it in self.items:
            age = max(0.0, (now_ns - it.t_ns) / 1e9)
            rad = ug.radius_cells(it.cls, age + horizon_s, monster_ms_per_cell)
            if is_static(it, now_ns):
                rad = min(rad, STATIC_RADIUS)
            rel = (it.cell[0] - belief[0], it.cell[1] - belief[1])
            cells = np.array([(rel[0] + dx, rel[1] + dy) for dx in range(-rad, rad + 1)
                              for dy in range(-rad, rad + 1)], dtype=float)  # fmt: skip
            alt = None if gat is None else gat.relative_altitude(belief, cells)
            feet = camera.project(cells, alt)
            boxes = [(u - it.w / 2, v - it.h, u + it.w / 2, v) for u, v in feet]
            out.append(ug.Envelope(it.cls, rel, rad, boxes))
        return out


def _cheb(a: Sequence[int], b: Sequence[int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def is_static(it: Any, now_ns: int) -> bool:
    return bool(isinstance(it, StaticSeen) and it.n >= STATIC_SEEN
                and (it.t_ns - it.since_ns) / 1e9 >= STATIC_S)  # fmt: skip


# --- B: approach the target from another side ----------------------------------------------------


def points_from(w: w5.World, cell: tuple[int, int], target: tuple[int, int]) -> int:
    """How many work-zone pixels (tier A, else B) pick ``target`` if we stood on ``cell``."""
    wc = copy.copy(w)
    wc.position = cell
    for tier in ("A", "B"):
        pts = [p for p in tier_points(wc, target, tier) if wz.in_work_zone(*p)]
        if pts:
            return len(pts)
    return 0


def side_cell(w: w5.World, target: tuple[int, int], blocked: set[tuple[int, int]],
              talk: set[tuple[int, int]], tried: set[tuple[int, int]]
              ) -> tuple[int, int] | None:  # fmt: skip
    """B: the nearest reachable cell 1-2 from the target, from which the target has work-zone
    points: not where we stand, not blocked, not tried, not next to a TALK cell."""
    for ring in SIDE_RINGS:
        best: tuple[int, tuple[int, int]] | None = None
        for dy in range(-ring, ring + 1):
            for dx in range(-ring, ring + 1):
                c = (target[0] + dx, target[1] + dy)
                if max(abs(dx), abs(dy)) != ring or c == w.position or c in blocked or c in tried:
                    continue
                if not (0 <= c[1] < w.walkable.shape[0] and 0 <= c[0] < w.walkable.shape[1]):
                    continue
                if not w.walkable[c[1], c[0]] or near_talk(c, talk):
                    continue
                path = w6.plan(w, c, blocked)
                if path is None or (best is not None and len(path) >= best[0]):
                    continue
                if points_from(w, c, target):
                    best = (len(path), c)
        if best is not None:
            return best[1]
    return None


# --- the route loop: walk@13's, with B -----------------------------------------------------------


def walk_route(pr: w6.Prober, w: w5.World, goal: tuple[int, int], band: tuple[int, int, int, int],
               seg_max: int, log_seg: Any, noentry_mask: Any, read_position: Any = None,
               relocalise: Callable[..., dict[str, Any]] = w11.reloc2.relocalise,
               label: str = "walk@8", expect_goal: str = WALK,
               clock: Callable[[], float] = time.monotonic,
               fixed_at_start: bool = False) -> dict[str, Any]:  # fmt: skip
    """walk@13's route loop (its changes 1-4, unchanged) + B: a round in which the TARGET's own
    points were refused for a non-unit reason walks first to a side cell (at most SIDES), before
    walk@13's NPC substitute, re-plan, patience and decline."""
    events: list[dict[str, Any]] = []
    relocs = clicks = covered = replans = sides = 0
    streak, streak_from = 0, None
    target, substitute, npc_sub = goal, None, None
    via_for: tuple[int, int] | None = None  # B: while walking to a side cell, the real target
    tried_sides: set[tuple[int, int]] = set()
    waited = 0.0
    unit_since: float | None = None
    fixed = fixed_at_start
    trust_left = TRUST_CLICKS if fixed_at_start else 0
    blocked: set[tuple[int, int]] = set()
    route_blocked: set[tuple[int, int]] = set()
    unit_blocked: dict[tuple[int, int], float] = {}
    talk: set[tuple[int, int]] = set()
    fix_fresh = fixed_at_start
    no_move: tuple[tuple[int, int], tuple[int, int]] | None = None

    def done(**kw: Any) -> dict[str, Any]:
        return {"events": events, "relocs": relocs, "clicks": clicks, "covered": covered,
                "substitute": substitute, "npc_substitute": npc_sub, "replans": replans,
                "sides": sides, "waited_s": round(waited, 1), **kw}  # fmt: skip

    def blocked_now() -> set[tuple[int, int]]:
        now = clock()
        live = {c for c, t in unit_blocked.items() if t > now}
        out = blocked | route_blocked | live | ({goal} if substitute or npc_sub else set())
        out.discard(target)
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
        if w.position == target and via_for is not None:  # B: on the side cell; the target again
            events.append({"side_reached": list(target), "t": r.ns()})
            target, via_for = via_for, None
            path = plan_once()
            if path is None:
                return done(decline="no_plan")
        if w.position == target:
            preview(pr.agent, w, w.position, [target], None, label)
            return done(arrived_belief=True)
        assert path is not None
        cands = click_candidates(w, path, seg_max, band) + farther_candidates(
            w, path, seg_max, band
        )
        cands += shorter_candidates(w, path, seg_max, band, cands)
        if not cands:
            return done(decline="out_of_band")
        clicked = replanned = False
        unit_at: list[tuple[int, int]] = []
        refused: dict[tuple[int, int], str] = {}
        target_refused: str | None = None  # B: why the TARGET's own points were refused
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
                if end == target:
                    target_refused = "no_safe_point"
                continue
            if step["outcome"].startswith(("covered_", "recheck_")):
                covered += 1
                if step["outcome"] == "covered_talk_cell" or shape == TALK:
                    refused[end] = "talk"
                    unit_at.append(end)
                elif shape in UNIT_SHAPES or step["outcome"] == "covered_unit_envelope":
                    refused[end] = "unit"
                    unit_at.append(end)
                else:  # C: an unknown / re-check read: something covers it, re-plan around it
                    refused[end] = "occluded"
                    if end == target:
                        target_refused = step["outcome"]
                continue
            if step["outcome"] == "unconfirmed":
                if end == target:
                    target_refused = "unconfirmed"
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
        # B: the target's own points were refused (not by a unit): approach it from another side
        if (target_refused is not None and target not in unit_at and via_for is None
                and sides < SIDES and expect_goal == WALK):  # fmt: skip
            s = side_cell(w, target, blocked_now(), talk, tried_sides | {w.position})
            events.append({"side": None if s is None else list(s), "for": list(target),
                           "why": target_refused, "t": r.ns()})  # fmt: skip
            if s is not None:
                tried_sides.add(s)
                sides += 1
                via_for, target = target, s
                path = plan_once()
                if path is None:
                    return done(decline="no_plan")
                continue
        if (npc_sub is None and substitute is None and expect_goal == WALK
                and near_talk(goal, talk)):  # fmt: skip
            sub = npc_substitute(w, goal, talk, blocked_now() | {goal})
            events.append({"npc_substitute": None if sub is None else list(sub),
                           "for": list(goal), "talk": sorted(list(c) for c in talk),
                           "t": r.ns()})  # fmt: skip
            if sub is not None:
                npc_sub, target, via_for = sub, sub, None
                unit_since = None
                path = plan_once()
                if path is None:
                    return done(decline="no_plan")
                continue
        if replans < REPLANS and refused:
            now = clock()
            for c, why in refused.items():
                if c == target:
                    continue
                if why == "unit":
                    unit_blocked[c] = now + UNIT_BLOCK_S
                else:
                    route_blocked.add(c)
            route_blocked.update(c for c in talk if c != target)
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
        if substitute is None and npc_sub is None and via_for is None and expect_goal == WALK:
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


class SessionLog(w13.SessionLog):
    """walk@13's session log, counting walk@14's route records and stamping its parameters."""

    current: SessionLog | None = None  # type: ignore[assignment]

    def __init__(self, session: str, root: Path | None = None) -> None:
        super().__init__(session, root)
        SessionLog.current = self
        w13.SessionLog.current = self
        w12.SessionLog.current = self

    def start(self, **meta: Any) -> None:
        super().start(**meta, static_s=STATIC_S, static_seen=STATIC_SEEN,
                      static_jitter=STATIC_JITTER, static_radius=STATIC_RADIUS,
                      sides=SIDES, side_rings=list(SIDE_RINGS))  # fmt: skip

    def append(self, rec: Any) -> Any:
        got = super().append(rec)
        if rec.rule == WALK8_RULE:
            self.routes += 1
        return got


DemoLog = SessionLog


def _rebind(fn: Callable[..., Any]) -> Any:
    """A function's code reading its global names from THIS module (walk@12's _walk11, here)."""
    fn = inspect.unwrap(fn)
    if not isinstance(fn, types.FunctionType):
        raise TypeError(f"not a plain function: {fn!r}")
    g = types.FunctionType(fn.__code__, globals(), fn.__name__, fn.__defaults__, fn.__closure__)
    g.__kwdefaults__ = fn.__kwdefaults__
    g.__doc__, g.__qualname__ = fn.__doc__, fn.__qualname__
    g.__annotations__ = dict(fn.__annotations__)
    g.__module__ = __name__
    return g


run11 = _rebind(w11.run)  # walk@11's harness, calling walk@14's walk_route / DemoLog / label
finish_session = _rebind(w12.finish_session)
finish_failed = _rebind(w12.finish_failed)
_run12 = _rebind(w12.run)  # walk@12's decision 3 around run11 (the preview and the HUD enabled)


def run(scene: str, condition: str, n: int, seed: int, label: str, crowd: int,
        fix: str = "where") -> int:  # fmt: skip
    """walk@12's run (decision 3: every exit finishes the session) with walk@14's unit memory."""
    UNITS["memory"] = StaticMemory()
    return int(_run12(scene, condition, n, seed, label, crowd, fix))


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--scene", choices=sorted(SCENES8), required=True)
    ap.add_argument("--condition", choices=("clean", "crowd"), required=True)
    ap.add_argument("--n", type=int, default=56)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--label", default="walk14-alone")
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
