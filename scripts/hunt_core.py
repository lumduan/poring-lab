"""hunt@N's PURE parts (Batt 2026-10-15 overnight: search-and-attack like a player, engagement
success >= 95 %; docs/demonstrations.md 3.39). The live loop is scripts/hunt.py.

- the SEARCH AREA and the VIEW FOOTPRINT;
- the COVERAGE grid ("last seen" per cell, staleness per 16 x 16 tile) and the goal choice;
- the SIGHTINGS memory (stationary targets kept, moving ones decay);
- routes (8-connected A*), waypoints and dead reckoning at the map's walk speed;
- the OFFLINE engagement judge (packets: our attack requests on the selected unit, its death) and
  the Wilson interval.
"""

from __future__ import annotations

import heapq
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

Cell = tuple[int, int]
TILE = 16
STALE_CAP_S = 600.0
STATIONARY_BONUS_S = 900.0
MOVING_BONUS_S, MOVING_TAU_S, MOVING_TTL_S = 300.0, 20.0, 60.0
STATIONARY_GAP_S = 10.0  # the same cell (+-1) seen twice this far apart: stationary
DIST_SCALE = 40.0  # score = staleness / (1 + path / DIST_SCALE)
WP_CELLS = 8  # a waypoint every this many path steps (inside the view in every direction)
LEAD_CELLS = 3  # the next click goes out when this few cells remain


# --- area and footprint ---------------------------------------------------------------------------


def search_area(ok: Any, keep_away: Iterable[tuple[int, int, int, int]], border: int = 20,
                margin: int = 6) -> Any:  # fmt: skip
    """Stand cells, minus a ``border`` and minus ``margin`` cells around each keep-away box
    (x, y, half_w, half_h: warp spans and NPC cells)."""
    a = np.asarray(ok, dtype=bool).copy()
    h, w = a.shape
    a[:border, :] = a[h - border :, :] = False
    a[:, :border] = a[:, w - border :] = False
    for x, y, hx, hy in keep_away:
        a[max(0, y - hy - margin) : y + hy + margin + 1,
          max(0, x - hx - margin) : x + hx + margin + 1] = False  # fmt: skip
    return a


def footprint(project: Any, in_view: Any, reach: int = 26) -> list[Cell]:
    """The cell offsets drawn on screen: ``project(offsets) -> (u, v)`` (flat ground) and
    ``in_view(u, v)`` (inside the game region, outside the static UI)."""
    offs = [(dx, dy) for dy in range(-reach, reach + 1) for dx in range(-reach, reach + 1)]
    uv = project(np.array(offs, dtype=float))
    return [o for o, (u, v) in zip(offs, uv, strict=True) if in_view(float(u), float(v))]


# --- coverage -------------------------------------------------------------------------------------


@dataclass
class Coverage:
    """Per-cell "last seen" (seconds); per-tile staleness over the search-area cells."""

    area: Any
    seen: Any = None
    first_seen: int = 0  # distinct area cells ever in view

    def __post_init__(self) -> None:
        if self.seen is None:
            self.seen = np.full(np.asarray(self.area).shape, -np.inf)

    def mark(self, pos: Cell, t: float, offsets: Sequence[Cell]) -> int:
        """The footprint at ``pos`` seen at ``t``; returns how many area cells were new."""
        h, w = self.seen.shape
        new = 0
        for dx, dy in offsets:
            x, y = pos[0] + dx, pos[1] + dy
            if 0 <= x < w and 0 <= y < h and self.area[y, x]:
                if self.seen[y, x] == -np.inf:
                    new += 1
                self.seen[y, x] = t
        self.first_seen += new
        return new

    def tiles(self, now: float) -> list[tuple[Cell, float]]:
        """(tile origin, staleness) for every tile with area cells; never seen = the cap."""
        out = []
        h, w = self.seen.shape
        for ty in range(0, h, TILE):
            for tx in range(0, w, TILE):
                a = np.asarray(self.area[ty : ty + TILE, tx : tx + TILE], dtype=bool)
                if not a.any():
                    continue
                s = self.seen[ty : ty + TILE, tx : tx + TILE][a]
                med = float(np.median(s))
                stale = STALE_CAP_S if med == -np.inf else min(STALE_CAP_S, now - med)
                out.append(((tx, ty), stale))
        return out


def tile_cell(area: Any, origin: Cell) -> Cell | None:
    """The tile's area cell nearest its centre."""
    tx, ty = origin
    a = np.asarray(area[ty : ty + TILE, tx : tx + TILE], dtype=bool)
    ys, xs = np.nonzero(a)
    if not len(xs):
        return None
    c = (TILE - 1) / 2
    i = int(np.argmin((xs - c) ** 2 + (ys - c) ** 2))
    return (tx + int(xs[i]), ty + int(ys[i]))


def choose_goal(cov: Coverage, pos: Cell, now: float, bonus: Mapping[Cell, float],
                exclude: Iterable[Cell] = ()) -> Cell | None:  # fmt: skip
    """The tile maximising (staleness + memory bonus) / (1 + distance / DIST_SCALE), as its area
    cell nearest the centre; tiles in ``exclude`` (unreachable before) are skipped."""
    skip = set(exclude)
    best, key = None, -1.0
    for origin, stale in cov.tiles(now):
        if origin in skip:
            continue
        cx, cy = origin[0] + TILE // 2, origin[1] + TILE // 2
        d = max(abs(cx - pos[0]), abs(cy - pos[1]))
        if d < TILE // 2:  # the tile we stand in is seen already
            continue
        s = (stale + bonus.get(origin, 0.0)) / (1 + d / DIST_SCALE)
        if s > key:
            best, key = origin, s
    return None if best is None else tile_cell(cov.area, best)


# --- memory ---------------------------------------------------------------------------------------


@dataclass
class Memory:
    """Target sightings: STATIONARY ones (the same cell +-1, >= STATIONARY_GAP_S apart) are kept
    until engaged or found gone; moving ones decay."""

    sightings: list[tuple[float, Cell]] = field(default_factory=list)
    stationary: dict[Cell, float] = field(default_factory=dict)

    def add(self, t: float, cell: Cell) -> None:
        for t0, c in self.sightings:
            if t - t0 >= STATIONARY_GAP_S and max(abs(c[0] - cell[0]), abs(c[1] - cell[1])) <= 1:
                self.stationary[cell] = t
                break
        self.sightings.append((t, cell))
        self.sightings = [(t0, c) for t0, c in self.sightings if t - t0 <= MOVING_TTL_S * 3]

    def forget(self, cell: Cell) -> None:
        """Engaged, or its cell was in view without it."""
        for c in [c for c in self.stationary if max(abs(c[0] - cell[0]), abs(c[1] - cell[1])) <= 1]:
            del self.stationary[c]

    def bonus(self, now: float) -> dict[Cell, float]:
        out: dict[Cell, float] = {}
        for t0, (x, y) in self.sightings:
            age = now - t0
            if age <= MOVING_TTL_S:
                key = (x - x % TILE, y - y % TILE)
                out[key] = out.get(key, 0.0) + MOVING_BONUS_S * math.exp(-age / MOVING_TAU_S)
        for x, y in self.stationary:
            key = (x - x % TILE, y - y % TILE)
            out[key] = out.get(key, 0.0) + STATIONARY_BONUS_S
        return out


# --- routes ---------------------------------------------------------------------------------------

STEP_MS = {False: 1.0, True: 1.4}  # RO: a diagonal step takes 14/10 of a straight one


def astar(ok: Any, start: Cell, goal: Cell, max_nodes: int = 200_000) -> list[Cell] | None:
    """8-connected A* on ``ok`` cells (octile costs); a diagonal step needs both side cells."""
    grid = np.asarray(ok, dtype=bool)
    h, w = grid.shape
    if not (grid[start[1], start[0]] and grid[goal[1], goal[0]]):
        return None

    def heur(c: Cell) -> float:
        dx, dy = abs(c[0] - goal[0]), abs(c[1] - goal[1])
        return max(dx, dy) + 0.4 * min(dx, dy)

    open_: list[tuple[float, float, Cell]] = [(heur(start), 0.0, start)]
    came: dict[Cell, Cell] = {}
    cost = {start: 0.0}
    n = 0
    while open_:
        _f, g, c = heapq.heappop(open_)
        if c == goal:
            path = [c]
            while c in came:
                c = came[c]
                path.append(c)
            return path[::-1]
        if g > cost.get(c, math.inf):
            continue
        n += 1
        if n > max_nodes:
            return None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if not dx and not dy:
                    continue
                nx, ny = c[0] + dx, c[1] + dy
                if not (0 <= nx < w and 0 <= ny < h) or not grid[ny, nx]:
                    continue
                if dx and dy and not (grid[c[1], nx] and grid[ny, c[0]]):
                    continue
                ng = g + STEP_MS[bool(dx and dy)]
                if ng < cost.get((nx, ny), math.inf):
                    cost[(nx, ny)] = ng
                    came[(nx, ny)] = c
                    heapq.heappush(open_, (ng + heur((nx, ny)), ng, (nx, ny)))
    return None


def waypoints(path: Sequence[Cell], every: int = WP_CELLS) -> list[Cell]:
    """Every ``every``-th cell after the start, and the end."""
    if len(path) < 2:
        return []
    out = [path[i] for i in range(every, len(path) - 1, every)]
    if not out or out[-1] != path[-1]:
        out.append(path[-1])
    return out


@dataclass
class Reckoner:
    """Our cell while walking: the clicked path at the map's speed (ms a straight step)."""

    ms_per_cell: float
    path: list[Cell] = field(default_factory=list)
    t0: float = 0.0

    def go(self, path: Sequence[Cell], t0: float) -> None:
        self.path, self.t0 = list(path), t0

    def where(self, t: float) -> Cell | None:
        if not self.path:
            return None
        left = (t - self.t0) * 1000.0
        for a, b in zip(self.path, self.path[1:], strict=False):
            step = self.ms_per_cell * STEP_MS[a[0] != b[0] and a[1] != b[1]]
            if left < step:
                return a
            left -= step
        return self.path[-1]

    def remaining(self, t: float) -> int:
        """Steps left to the path's end."""
        here = self.where(t)
        return 0 if here is None else len(self.path) - 1 - self.path.index(here)


# --- the offline judge ----------------------------------------------------------------------------


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def unit_positions(events: Sequence[Mapping[str, Any]]) -> dict[int, list[tuple[int, Cell, int]]]:
    """gid -> [(t, cell, job)] from entity_appear (a move gives its start cell; its end cell is
    reached later), objtype 5 (mobs) only."""
    out: dict[int, list[tuple[int, Cell, int]]] = {}
    for e in events:
        if e.get("type") == "entity_appear" and e.get("objtype") == 5:
            out.setdefault(int(e["gid"]), []).append(
                (int(e["t_mono_ns"]), (int(e["x"]), int(e["y"])), int(e.get("job", -1)))
            )
            if e.get("x1") is not None:
                out[int(e["gid"])].append((int(e["t_mono_ns"]) + 1, (int(e["x1"]), int(e["y1"])),
                                          int(e.get("job", -1))))  # fmt: skip
    return out


def judge_engagement(eng: Mapping[str, Any], events: Sequence[Mapping[str, Any]],
                     gm_aid: int = 2000002, targets: Iterable[int] = (1002, 1063, 1008, 1113),
                     near: int = 2) -> dict[str, Any]:  # fmt: skip
    """Batt's definitions (3.39, fixed before any data):
    - the SELECTED unit G: our first attack request after the selection, if its unit stood within
      ``near`` cells of the selected cell at that time; else the mob nearest the selected cell at
      the selection time (within ``near``);
    - SUCCESS: G died (entity_vanish reason 1) after at least one act of ours on G;
    - EXCLUDED (packets only): G changed species (metamorphosis), G vanished another way while we
      never hit it (reason != 1 and not out of sight), or G was killed with no act of ours."""
    t_sel, t_end = int(eng["t_select"]), int(eng["t_end"])
    sel = tuple(eng["target_cell"])
    pos = unit_positions([e for e in events if int(e.get("t_mono_ns", 0)) <= t_end + 60 * 10**9])

    def at(g: int, t: int) -> tuple[Cell, int] | None:
        last = None
        for tm, c, j in pos.get(g, []):
            if tm <= t:
                last = (c, j)
        return last

    first_req = next((e for e in events if e.get("type") == "attack_request"
                      and t_sel <= int(e["t_mono_ns"]) <= t_end), None)  # fmt: skip
    g = None
    if first_req is not None:
        cand = int(first_req["target_gid"])
        a = at(cand, int(first_req["t_mono_ns"]))
        if a is not None and max(abs(a[0][0] - sel[0]), abs(a[0][1] - sel[1])) <= near + 3:
            g = cand
    if g is None:
        best = None
        for gid in pos:
            a = at(gid, t_sel)
            if a is None:
                continue
            d = max(abs(a[0][0] - sel[0]), abs(a[0][1] - sel[1]))
            if d <= near and (best is None or d < best[0]):
                best = (d, gid)
        g = None if best is None else best[1]
    if g is None:
        return {"gid": None, "success": False, "excluded": False, "why": "no_unit_at_selection"}
    ours = [e for e in events if e.get("type") == "act" and int(e.get("src_gid", -1)) == gm_aid
            and int(e.get("target_gid", -1)) == g and e.get("kind") != "pickup"
            and int(e["t_mono_ns"]) >= t_sel]  # fmt: skip
    gone = next((e for e in events if e.get("type") == "entity_vanish" and int(e["gid"]) == g
                 and int(e["t_mono_ns"]) >= t_sel), None)  # fmt: skip
    jobs = {j for _t, _c, j in pos.get(g, [])}
    job_sel = (at(g, t_sel) or (None, -1))[1]
    if len(jobs) > 1 and any(j not in set(targets) for j in jobs):
        return {"gid": g, "success": False, "excluded": True, "why": "species_changed",
                "jobs": sorted(jobs)}  # fmt: skip
    died = gone is not None and int(gone.get("reason", -1)) == 1
    if died and ours:
        return {"gid": g, "job": job_sel, "success": True, "excluded": False, "why": "killed",
                "acts": len(ours), "t_death": int(gone["t_mono_ns"])}  # fmt: skip
    if died and not ours:
        return {"gid": g, "job": job_sel, "success": False, "excluded": True,
                "why": "killed_by_other"}  # fmt: skip
    if gone is not None and int(gone.get("reason", -1)) not in (0, 1) and not ours:
        return {"gid": g, "job": job_sel, "success": False, "excluded": True,
                "why": f"vanished_reason_{gone.get('reason')}"}  # fmt: skip
    return {"gid": g, "job": job_sel, "success": False, "excluded": False,
            "why": "hit_not_killed" if ours else "never_hit", "acts": len(ours)}  # fmt: skip
