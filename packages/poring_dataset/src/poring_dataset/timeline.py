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
"""

import bisect
import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from poring_dataset.mapcache import MapGrid
from poring_dataset.walk import walk_path
from poring_packets.world import (
    MOVE_COST,
    MOVE_DIAGONAL_COST,
    TICK_MOD,
    Walk,
    World,
    heading_of,
    path_cells,
)


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
    ) -> None:
        self.events = sorted((dict(e) for e in events), key=lambda e: int(e["t_mono_ns"]))
        self.times = [int(e["t_mono_ns"]) for e in self.events]
        self.maps = dict(maps or {})
        self._snapshots: list[tuple[int, World]] = [(0, World())]  # (events applied, state)
        world = World()
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

    def frame_world(self, t_ns: int) -> FrameWorld:
        world = self.world_at(t_ns)
        tick = tick_of(t_ns)
        grid = self.maps.get(world.map or "")
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
            entities.append(
                EntityState(ent.gid, ent.objtype, ent.job, ent.name, x, y, moving, heading)
            )
        return FrameWorld(t_ns, world.map, world.aid, self_pos, tuple(entities), self_heading)


@lru_cache(maxsize=65536)
def _cells(grid: MapGrid | None, x0: int, y0: int, x1: int, y1: int) -> tuple[tuple[int, int], ...]:
    if grid is not None:
        path = walk_path(grid, x0, y0, x1, y1)
        if path is not None:
            return tuple(path)
    return tuple(path_cells(x0, y0, x1, y1))


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
