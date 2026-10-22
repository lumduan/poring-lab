"""World state at any frame time, from recorded packet events (B2, docs/phase2-plan.md).

Clock: events carry the kernel receive time on the host's CLOCK_MONOTONIC (t_mono_ns) and the server
tick IS that clock in ms mod 2^32 (docs/phase1-validation.md: 388/406 samples 0 ms, 18 at 1 ms). Lab
frames carry t_capture_ns on the same clock, so no fitting is needed.

What a frame SHOWS lags the server: a frame captured at t shows the world as it was at about
t - offset, where offset is the backend's packet->frame delay (benchmark p50, docs/benchmarks/). The
caller passes that offset per backend; this module only answers "where was everything at t".

Walks are interpolated along a shortest walk on the map cache's walkability (poring_dataset.walk, a
textbook A*; since 2026-10-04 it replaces the GPL port of rAthena's search: on 2540 recorded walks
it found every one, matched the port's cells on 2534 and every arrival exactly --
scripts/walk_check.py), with rAthena's step timing (speed ms per cell, *14/10 diagonally). Without a
map grid it falls back to poring_packets' diagonal-first path.

Actor state (Phase 3 M3, docs/phase3-plan.md section 3): `Timeline.state(gid, t)` says what a unit
SHOWS at t -- idle, walk, attacking, hurt or dying (sit: players only) -- and which way it faces,
from the walks above plus the ZC_NOTIFY_ACT, ZC_CHANGE_DIRECTION and vanish events
(poring_packets.world keeps them). The swing's state is "attacking": the pre-commit guard
(ADR-0012) refuses the shorter literal. The packets time an attack (the source's attack motion) and
a flinch (the target's damage motion); a die animation's length is in no packet, so it comes from
the caller's per-class table (the sprite catalog, M1) with a placeholder default. Two client-side
timings are NOT modelled here and belong to the render rule (M2), per rAthena's own notes on the
client (clif.cpp:5246-5254):
  * the client plays an attack at its ACT speed unless `src_speed` < 432, which speeds it up --
    the `attacking` state lasts the server's attack motion, not the animation;
  * the target flinches at the attacker's damage frame, not when the attack starts -- `hurt` starts
    at the attack's tick.
"""

import bisect
import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Any, Literal

from poring_dataset.mapcache import MapGrid
from poring_dataset.walk import walk_path
from poring_packets.world import (
    DEAD_KEEP_MS,
    HIDDEN_OPTIONS,
    MOVE_COST,
    MOVE_DIAGONAL_COST,
    TICK_MOD,
    Motion,
    Walk,
    World,
    direction_toward,
    heading_of,
    path_cells,
    ticks_since,
)

State = Literal["idle", "walk", "attacking", "hurt", "dying", "sit"]
# The die animation's length when the caller's table has no entry for a class. A PLACEHOLDER: the
# sprite catalog (M1) gives each class its die action's length, and M4 checks it on frames.
DEFAULT_DIE_MS = 2_000
PLAYER_IDS = range(2_000_000, 110_000_000)  # rAthena: START_ACCOUNT_NUM .. START_NPC_NUM


@dataclass(frozen=True, slots=True)
class EntityState:
    gid: int
    objtype: int
    job: int
    name: str
    x: float
    y: float
    moving: bool
    heading: int | None = None  # RO heading (0 = north, ccw): the step walked, else as appeared
    hidden: bool = False  # sent with an option the client draws as nothing (HIDDEN_OPTIONS)


@dataclass(frozen=True, slots=True)
class ActorState:
    """What one unit shows at `t_ns` (M3)."""

    gid: int
    t_ns: int
    state: State
    facing: int | None  # RO heading 0..7 (0 = north, counter-clockwise); None: never seen
    facing_from: str | None  # appear | turn | target | walk | stop: what set the facing
    x: float
    y: float
    job: int | None  # None for our own character
    since_ns: int | None  # when this state began (host clock, ms resolution); None: not seen
    duration_ms: int | None = None  # a timed state's length (attack, hurt, dying)
    other: int | None = None  # attack: the target's gid; hurt: the attacker's

    @property
    def elapsed_ms(self) -> float | None:
        """How far into its state the unit is at `t_ns` (an animation's phase); None when the
        state's start is unknown."""
        return None if self.since_ns is None else (self.t_ns - self.since_ns) / 1e6


@dataclass(frozen=True, slots=True)
class FrameWorld:
    t_ns: int
    map: str | None
    aid: int | None
    self_pos: tuple[float, float] | None
    entities: tuple[EntityState, ...]
    self_heading: int | None = None


def tick_of(t_ns: int) -> int:
    return (t_ns // 1_000_000) % TICK_MOD


class Timeline:
    def __init__(
        self,
        events: Iterable[Mapping[str, Any]],
        maps: Mapping[str, MapGrid] | None = None,
        *,
        snapshot_every: int = 256,
        die_ms: Mapping[int, int] | None = None,
        default_die_ms: int = DEFAULT_DIE_MS,
    ) -> None:
        """`die_ms`: the die animation's length (ms) per class (job); `default_die_ms` for the
        others."""
        self.events = sorted((dict(e) for e in events), key=lambda e: int(e["t_mono_ns"]))
        self.times = [int(e["t_mono_ns"]) for e in self.events]
        self.maps = dict(maps or {})
        self.die_ms = dict(die_ms or {})
        self.default_die_ms = default_die_ms
        # the world keeps a dead unit at least as long as its die animation can last
        keep = max(DEAD_KEEP_MS, default_die_ms, *self.die_ms.values())
        # A recorded session starts at its last map change, so login_accepted (which names our own
        # block id) is usually not in it, and our own entity_stop was ignored: a walk cut short kept
        # its planned end, and every box of those frames was projected from the wrong cell (found
        # by the T0 evaluation, 2026-10-04). Infer the id instead.
        logged_in = any(e.get("type") == "login_accepted" for e in self.events)
        self.inferred_aid = None if logged_in else infer_self_aid(self.events)
        first = World(dead_keep_ms=keep)
        first.aid = self.inferred_aid
        self._snapshots: list[tuple[int, World]] = [(0, first)]
        world = copy.deepcopy(first)
        for i, event in enumerate(self.events, 1):
            self._apply(world, event)
            if i % snapshot_every == 0:
                self._snapshots.append((i, copy.deepcopy(world)))

    @staticmethod
    def _apply(world: World, event: Mapping[str, Any]) -> None:
        etype = str(event["type"])
        if etype == "login_accepted":
            world.aid = int(event["aid"])
        world.apply(etype, dict(event))

    def world_at(self, t_ns: int) -> World:
        """A copy of the world after every event with t_mono_ns <= t_ns."""
        n = bisect.bisect_right(self.times, t_ns)
        k = bisect.bisect_right([s[0] for s in self._snapshots], n) - 1
        start, snap = self._snapshots[k]
        world = copy.deepcopy(snap)
        for event in self.events[start:n]:
            self._apply(world, event)
        return world

    def grid(self, map_name: str | None) -> MapGrid | None:
        """The map cache's grid for a packet map name. Packets say "prt_fild08.gat", the cache
        keys "prt_fild08": without this every walk fell back to the straight diagonal-first
        path instead of A* (found by the T0 evaluation, 2026-10-04)."""
        name = (map_name or "").removesuffix(".gat")
        return self.maps.get(name) if name else None

    def frame_world(self, t_ns: int) -> FrameWorld:
        return self._frame_of(self.world_at(t_ns), t_ns)

    def at(
        self, t_ns: int
    ) -> tuple[FrameWorld, tuple["ActorState", ...], dict[int, tuple[int, str]]]:
        """frame_world, states and walk_rule_facings at `t_ns` from ONE replay of the events."""
        return self.at_world(t_ns)[1:]

    def at_world(
        self, t_ns: int
    ) -> tuple[World, FrameWorld, tuple["ActorState", ...], dict[int, tuple[int, str]]]:
        """``at`` with the replayed World itself first (its entities' walks: the move vectors the
        orcsdun01 label fix 2 reads, docs/planning/orcsdun01-detector.md 3f)."""
        world = self.world_at(t_ns)
        return world, self._frame_of(world, t_ns), self._states_of(world, t_ns), \
            self._walk_rules_of(world, t_ns)  # fmt: skip

    def _frame_of(self, world: World, t_ns: int) -> FrameWorld:
        tick = tick_of(t_ns)
        grid = self.grid(world.map)
        self_pos, self_heading = None, None
        if world.self_walk is not None:
            *xy, self_heading = walk_state(world.self_walk, tick, grid)
            self_pos = (xy[0], xy[1])
        elif world.self_x is not None and world.self_y is not None:
            self_pos = (float(world.self_x), float(world.self_y))
        entities = []
        for ent in world.entities.values():
            heading = ent.dir
            if ent.walk is not None:
                x, y, step = walk_state(ent.walk, tick, grid)
                moving = (x, y) != (float(ent.walk.x1), float(ent.walk.y1))
                heading = step if step is not None else heading
            else:
                x, y, moving = float(ent.x), float(ent.y), False
            hidden = bool(ent.effect_state & HIDDEN_OPTIONS)
            entities.append(
                EntityState(ent.gid, ent.objtype, ent.job, ent.name, x, y, moving, heading, hidden)
            )
        return FrameWorld(t_ns, world.map, world.aid, self_pos, tuple(entities), self_heading)

    def state(self, gid: int, t_ns: int) -> ActorState | None:
        """What unit `gid` (our own account id included) shows at `t_ns`; None when it is not in
        sight then (nor dying)."""
        return self._state(self.world_at(t_ns), gid, t_ns)

    def states(self, t_ns: int) -> tuple[ActorState, ...]:
        """Every unit's state at `t_ns`: our own character first, then the entities in sight,
        then the ones playing their die animation."""
        return self._states_of(self.world_at(t_ns), t_ns)

    def _states_of(self, world: World, t_ns: int) -> tuple[ActorState, ...]:
        gids = [*([] if world.aid is None else [world.aid]), *world.entities, *world.dead]
        found = (self._state(world, gid, t_ns) for gid in gids)
        return tuple(s for s in found if s is not None)

    def walk_rule_facings(self, t_ns: int) -> dict[int, tuple[int, str]]:
        """Every entity in sight whose facing the WALK RULE sets at `t_ns` (walk_rule_facing):
        gid -> (heading, "walk_rule"). Entities missing here keep the Timeline's facing."""
        return self._walk_rules_of(self.world_at(t_ns), t_ns)

    def _walk_rules_of(self, world: World, t_ns: int) -> dict[int, tuple[int, str]]:
        grid = self.grid(world.map)
        out = {}
        for gid in world.entities:
            found = walk_rule_facing(world, gid, t_ns, grid)
            if found is not None:
                out[gid] = found
        return out

    def die_ms_of(self, job: int) -> int:
        return self.die_ms.get(job, self.default_die_ms)

    def _state(self, world: World, gid: int, t_ns: int) -> ActorState | None:
        grid = self.grid(world.map)
        if gid == world.aid:
            if world.self_x is None or world.self_y is None:
                return None
            return actor_state(gid, None, (world.self_x, world.self_y), world.self_walk,
                               world.self_motion, t_ns, grid)  # fmt: skip
        ent = world.entities.get(gid)
        if ent is not None:
            return actor_state(gid, ent.job, (ent.x, ent.y), ent.walk, ent.motion, t_ns, grid)
        ent = world.dead.get(gid)
        if ent is None or ent.died_tick is None:
            return None
        died_ms = ticks_since(tick_of(t_ns), ent.died_tick)
        duration = self.die_ms_of(ent.job)
        if not 0 <= died_ms < duration:
            return None
        died_ns = t_ns - died_ms * 1_000_000
        # where it fell and the way it faced: its state at the moment it died
        last = actor_state(gid, ent.job, (ent.x, ent.y), ent.walk, ent.motion, died_ns, grid)
        return replace(last, t_ns=t_ns, state="dying", since_ns=died_ns, duration_ms=duration,
                       other=None)  # fmt: skip


def actor_state(
    gid: int,
    job: int | None,
    cell: tuple[int, int],
    walk: Walk | None,
    motion: Motion,
    t_ns: int,
    grid: MapGrid | None,
) -> ActorState:
    """One unit's state at `t_ns`: a running action (attack, hurt) first, then walking, sitting,
    idle. The facing is the NEWEST of its turns (appear heading, ZC_CHANGE_DIRECTION, toward an
    attack's target), the step it walks (while walking; after arriving: its last step) and the
    step an entity_stop cut short."""
    tick = tick_of(t_ns)

    def ns_of(k: int) -> int:
        return t_ns - ticks_since(tick, k) * 1_000_000

    facings: list[tuple[int | None, int, str]] = []  # (tick it was set, heading, source)
    if motion.turn is not None:
        facings.append((motion.turn.tick, motion.turn.heading, motion.turn.source))
    if motion.cut is not None:
        cut_walk, cut_tick = motion.cut
        _, _, cut_step = walk_state(cut_walk, cut_tick, grid)
        if cut_step is not None:
            facings.append((cut_tick, cut_step, "stop"))
    x, y = float(cell[0]), float(cell[1])
    walking, arrived = False, None
    if walk is not None:
        x, y, step = walk_state(walk, tick, grid)
        if ticks_since(tick, walk.start_tick) >= 0:
            walking = (x, y) != (float(walk.x1), float(walk.y1))
            if not walking:
                arrived = (walk.start_tick + walk_ms(walk, grid)) % TICK_MOD
            if step is not None:
                facings.append((tick if arrived is None else arrived, step, "walk"))
    facing, facing_from, best = None, None, TICK_MOD + 1
    for set_at, heading, source in facings:  # the newest wins; a tie goes to the later source
        age = TICK_MOD if set_at is None else ticks_since(tick, set_at)
        if 0 <= age <= best:
            facing, facing_from, best = heading, source, age

    def shown(state: State, since: int | None, duration: int | None = None,
              other: int | None = None) -> ActorState:  # fmt: skip
        return ActorState(gid, t_ns, state, facing, facing_from, x, y, job, since, duration, other)

    action = motion.action
    if action is not None and action.active(tick):
        kind: State = "attacking" if action.kind == "attacking" else "hurt"
        return shown(kind, ns_of(action.start_tick), action.duration_ms, action.other)
    if walking and walk is not None:
        return shown("walk", ns_of(walk.start_tick))
    if motion.sitting:
        return shown("sit", None)
    # idle since the latest end we know of: an action's, a walk's arrival, a stop
    ends = [arrived, None if motion.cut is None else motion.cut[1]]
    if action is not None:
        ends.append((action.start_tick + action.duration_ms) % TICK_MOD)
    ages = [a for a in (ticks_since(tick, k) for k in ends if k is not None) if a >= 0]
    return shown("idle", t_ns - min(ages) * 1_000_000 if ages else None)


def walk_rule_facing(
    world: World, gid: int, t_ns: int, grid: MapGrid | None
) -> tuple[int, str] | None:
    """The orcsdun01 label fix's facing rule 1a (docs/planning/orcsdun01-detector.md 3b): a unit
    whose LAST MOVE has ENDED by `t_ns` (arrived on walk_state's timing, or cut short by a stop)
    faces that move's direction FROM -> TO (the packet's start and end cells; rAthena's rule for
    the direction of a cell, poring_packets.world.direction_toward), kept after it stops until a
    newer turn (ZC_CHANGE_DIRECTION, an appear heading, an attacker facing its target) or a newer
    attack changes it. None otherwise (still walking, no move seen, or a newer change): the
    caller keeps the Timeline's facing (actor_state). A tie goes to the change."""
    ent = world.entities.get(gid)
    if ent is None:
        return None
    tick = tick_of(t_ns)
    ended: tuple[int, Walk] | None = None
    if ent.walk is not None and ticks_since(tick, ent.walk.start_tick) >= 0:
        end = (ent.walk.start_tick + walk_ms(ent.walk, grid)) % TICK_MOD
        if ticks_since(tick, end) >= 0:
            ended = (end, ent.walk)
    elif ent.motion.cut is not None and ticks_since(tick, ent.motion.cut[1]) >= 0:
        ended = (ent.motion.cut[1], ent.motion.cut[0])
    if ended is None:
        return None
    end, walk = ended
    heading = direction_toward(walk.x1 - walk.x0, walk.y1 - walk.y0)
    if heading is None:
        return None
    age = ticks_since(tick, end)
    turn, action = ent.motion.turn, ent.motion.action
    if turn is not None and turn.tick is not None and 0 <= ticks_since(tick, turn.tick) <= age:
        return None
    if (action is not None and action.kind == "attacking"
            and 0 <= ticks_since(tick, action.start_tick) <= age):  # fmt: skip
        return None
    return heading, "walk_rule"


@lru_cache(maxsize=65536)
def _cells(grid: MapGrid | None, x0: int, y0: int, x1: int, y1: int) -> tuple[tuple[int, int], ...]:
    if grid is not None:
        path = walk_path(grid, x0, y0, x1, y1)
        if path is not None:
            return tuple(path)
    return tuple(path_cells(x0, y0, x1, y1))


def infer_self_aid(events: Iterable[Mapping[str, Any]]) -> int | None:
    """Our own block id when the events do not carry login_accepted: the one player-range id that
    stops or vanishes but never appears (every other unit enters our view by appearing). None when
    it is not exactly one. (From scripts/selfpos_calibrate.py, T0, 2026-10-04.)"""
    seen: set[int] = set()
    appeared: set[int] = set()
    for e in events:
        kind = e.get("type")
        if kind in ("entity_stop", "entity_vanish") and int(e["gid"]) in PLAYER_IDS:
            seen.add(int(e["gid"]))
        elif kind == "entity_appear":
            appeared.add(int(e["gid"]))
    candidates = seen - appeared
    return candidates.pop() if len(candidates) == 1 else None


def walk_state(walk: Walk, tick: int, grid: MapGrid | None) -> tuple[float, float, int | None]:
    """(x, y, heading): Walk.position_at along the real path when the map grid is known, and the
    heading of the step being walked (after arrival: of the last step; before it starts: None)."""
    elapsed = (tick - walk.start_tick) % TICK_MOD
    if elapsed > TICK_MOD // 2:  # before the walk started
        return float(walk.x0), float(walk.y0), None
    x, y = float(walk.x0), float(walk.y0)
    heading = None
    for cx, cy in _cells(grid, walk.x0, walk.y0, walk.x1, walk.y1):
        heading = heading_of(cx - x, cy - y)
        diagonal = cx != x and cy != y
        step = walk.speed * (MOVE_DIAGONAL_COST if diagonal else MOVE_COST) / MOVE_COST
        if elapsed < step:
            frac = elapsed / step
            return x + (cx - x) * frac, y + (cy - y) * frac, heading
        elapsed -= int(step)
        x, y = float(cx), float(cy)
    return float(walk.x1), float(walk.y1), heading


def walk_ms(walk: Walk, grid: MapGrid | None) -> int:
    """How long a walk takes (ms), on walk_state's path and step timing."""
    total, x, y = 0, walk.x0, walk.y0
    for cx, cy in _cells(grid, walk.x0, walk.y0, walk.x1, walk.y1):
        diagonal = cx != x and cy != y
        total += int(walk.speed * (MOVE_DIAGONAL_COST if diagonal else MOVE_COST) / MOVE_COST)
        x, y = cx, cy
    return total


def walk_position(walk: Walk, tick: int, grid: MapGrid | None) -> tuple[float, float]:
    """Walk.position_at, along the real path when the map grid is known."""
    x, y, _ = walk_state(walk, tick, grid)
    return x, y


# The client's world resets on these: a session's packets must start at the last one before the
# first frame, or the player's own position (and anything already on screen) is unknown.
ANCHOR_EVENTS = ("map_change", "char_selected")


def session_events(
    events: Iterable[Mapping[str, Any]],
    t0_ns: int,
    t1_ns: int,
    *,
    margin_ns: int = 5_000_000_000,
    lookback_ns: int = 30 * 60 * 1_000_000_000,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """The events a recording [t0, t1] needs: from the LAST map change / character select before
    t0 (at most ``lookback_ns`` earlier) through t1 + margin, so the timeline knows the map, the
    player's position and every entity already present. Without an anchor in reach: [t0 - margin,
    ...] and anchor None (labels then start at the next map change). Returns (events, anchor)."""
    ordered = sorted((dict(e) for e in events), key=lambda e: int(e["t_mono_ns"]))
    ordered = [e for e in ordered if int(e["t_mono_ns"]) <= t1_ns + margin_ns]
    latest: int | None = None
    anchor: dict[str, Any] | None = None
    for e in ordered:
        t = int(e["t_mono_ns"])
        if t > t0_ns:
            break
        if e["type"] in ANCHOR_EVENTS and t0_ns - t <= lookback_ns:
            latest = t  # the world resets at every anchor: only the last one counts
            anchor = {"type": e["type"], "seconds_before_t0": round((t0_ns - t) / 1e9, 1)}
    start_ns = t0_ns - margin_ns if latest is None else min(latest, t0_ns - margin_ns)
    return [e for e in ordered if int(e["t_mono_ns"]) >= start_ns], anchor
