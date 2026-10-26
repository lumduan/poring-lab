#!/usr/bin/env python3
"""--rest house (docs/planning/gef10-house-rest.md; OFF by default): rest INSIDE an orc house
(in_orcs01) instead of sitting in the field, as Batt did in his demo (2026-10-26 ~10:05, "I rest
on this map because it is safer"). PURE planning only; dungeon_hunt.py drives it.

    house_rest.py table [--kb DIR] [--mapcache DIR]       the door / exit table (JSON)
    house_rest.py steps SID [SID...] [--demo DIR]         route steps from each rest decision of
                                                          the runs to the nearest sealed door

THE GEOMETRY (static map knowledge, read at run time from data/kb/warps.json, the client GAT of
in_orcs01 and the server's map cache; nothing of either is committed):
- a HOUSE = a door warp on the field (gef_fild10 -> in_orcs01, span 1,1) paired with the house's
  own EXIT warp inside (in_orcs01 -> gef_fild10) whose span lies next to the door's ARRIVAL cell
  and whose return cell lies next to the door (``houses``);
- every other warp of in_orcs01 is FORBIDDEN (orc01 -> orcsdun01, orc02 -> orcsdun02:
  ``forbidden_warps``);
- a house is USABLE only when its room is SEALED: on the interior's walkable grid (client AND
  server, both 8-connected rules) the arrival cell reaches its own exit and NO forbidden warp cell
  (``room_check``). Three houses are sealed (gef018 / gef019 / gef020); the other two hold a
  dungeon warp 24 steps from the arrival (gef021: orc02, gef022 -- Batt's door: orc01) and are
  never used. In a sealed room nothing the runner does -- a wrong click, a client detour -- can
  reach the dungeon: the only warp its walk can touch is its own exit.

THE TRIP (``Trip``: a closed transition table; any other event in a state is a STOP):
  walk (to an APPROACH cell: on the route grid, just outside the door's no-enter area) -> door
  (ONE click on the door's centre; the zones of every OTHER item still hold for that walk) ->
  inside (pixels: the load gap, then Basic Info back with NO minimap readout and a dark
  interior) -> rest (sit at once; no walk inside) -> exit (stand; ONE click on the exit span's
  centre, projected from the arrival cell by the indoor camera + in_orcs01's GAT) -> back (pixels:
  a load gap, then the minimap readout at the exit's return cell) -> field.

MAP CHANGES (``Transition``): pixels only -- Basic Info's HP text unreadable for >= GAP_MIN_S
(the client's loading screen), then readable again; inside = no minimap readout for INSIDE_S and
a dark frame; back = the readout within RETURN_TOL of the house's return cell. Batt's own door
step (his demo frames, 2026-10-26 10:05:59) is the positive case: the loading screen for 3.0 s
(HP unread, frame mean 175), one black frame, then HP read with no readout, frame mean 26-39 (the
field's 97-112). Never packets.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections import Counter, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

Cell = tuple[int, int]
ROOT = Path(__file__).resolve().parents[1]
FIELD = "gef_fild10"
HOUSE_MAP = "in_orcs01"
EXIT_NEAR = 3  # the exit's span lies within this many cells (Chebyshev) of the door's arrival
BACK_NEAR = 4  # the exit's return cell lies within this many cells of the door warp
FORBIDDEN_MIN = 10  # the exit click cell's Chebyshev distance to every forbidden span (brief)
APPROACH_R = 7  # an approach cell lies within this many cells (Chebyshev) of the door centre
APPROACH_STEPS = 9  # ... and the client's own path from it to the door is at most this long
GAP_MIN_S = 1.0  # Basic Info unreadable this long = the client's loading screen (Batt: 3.4 s)
GAP_STOP_S = 2.0  # a gap this long with no door / exit click and no Fly Wing = a STOP
INSIDE_S = 1.5  # after the gap: HP read, no minimap readout, dark, for this long = inside
DARK_MAX = 70.0  # the interior's frame mean (Batt's room 26-39; the field 97-112 in his frames)
RETURN_TOL = 4  # back on the field: the readout within this many cells of the return cell
ENTER_MAX_S = 8.0  # the door click -> the load gap must start within this long (Batt: 0.8 s)
EXIT_MAX_S = 8.0  # the exit click -> the load gap must start within this long
LOAD_MAX_S = 20.0  # a load gap longer than this = a STOP (the loading screen hangs)
BACK_READ_S = 6.0  # back on the field: no readout this long (a bright frame) = own knowledge


# --- the geometry -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Warp:
    name: str
    cell: Cell
    span: tuple[int, int]
    to_map: str
    to: Cell

    def cells(self) -> list[Cell]:
        """The touch area: centre +- span (rAthena's warp cells; map_zones' convention)."""
        (x, y), (sx, sy) = self.cell, self.span
        return [(cx, cy) for cx in range(x - sx, x + sx + 1) for cy in range(y - sy, y + sy + 1)]

    def contains(self, c: Sequence[int]) -> bool:
        return (abs(c[0] - self.cell[0]) <= self.span[0]
                and abs(c[1] - self.cell[1]) <= self.span[1])  # fmt: skip

    def cheb_to(self, c: Sequence[int]) -> int:
        """Chebyshev cells from ``c`` to the nearest cell of the touch area (0 = on it)."""
        dx = max(0, abs(c[0] - self.cell[0]) - self.span[0])
        dy = max(0, abs(c[1] - self.cell[1]) - self.span[1])
        return max(dx, dy)


@dataclass(frozen=True)
class House:
    door: Warp  # on the field: -> HOUSE_MAP at door.to (the arrival)
    exit: Warp  # inside: -> FIELD at exit.to (the return cell)

    @property
    def name(self) -> str:
        return self.door.name

    @property
    def arrival(self) -> Cell:
        return self.door.to

    @property
    def back(self) -> Cell:
        return self.exit.to


def _cheb(a: Sequence[int], b: Sequence[int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def warps_of(kb: Mapping[str, Any], map_name: str) -> list[Warp]:
    """PURE: data/kb/warps.json's rows for ``map_name`` as Warps."""
    return [Warp(str(w["name"]), (int(w["x"]), int(w["y"])),
                 (int(w["span_x"]), int(w["span_y"])), str(w["to_map"]),
                 (int(w["to_x"]), int(w["to_y"]))) for w in kb.get(map_name, [])]  # fmt: skip


def houses(kb: Mapping[str, Any], field: str = FIELD, house_map: str = HOUSE_MAP) -> list[House]:
    """PURE: each field door into ``house_map`` paired with its OWN exit: the one exit back to
    ``field`` whose span lies within EXIT_NEAR of the door's arrival AND whose return cell lies
    within BACK_NEAR of the door. A door with no such exit, or with two, raises ValueError (fail
    closed: the runner refuses to start)."""
    doors = [w for w in warps_of(kb, field) if w.to_map == house_map]
    exits = [w for w in warps_of(kb, house_map) if w.to_map == field]
    out = []
    for d in doors:
        mine = [e for e in exits
                if e.cheb_to(d.to) <= EXIT_NEAR and _cheb(e.to, d.cell) <= BACK_NEAR]  # fmt: skip
        if len(mine) != 1:
            raise ValueError(f"door {d.name} {d.cell}: {len(mine)} matching exits in {house_map}")
        out.append(House(d, mine[0]))
    return out


def forbidden_warps(kb: Mapping[str, Any], field: str = FIELD,
                    house_map: str = HOUSE_MAP) -> list[Warp]:  # fmt: skip
    """PURE: every warp of ``house_map`` that does NOT lead back to ``field`` (the dungeons)."""
    return [w for w in warps_of(kb, house_map) if w.to_map != field]


def steps_from(grid: Any, start: Cell, corner: bool = True, max_steps: int | None = None) -> Any:
    """PURE: 8-connected BFS steps from ``start`` on ``grid`` (-1 = unreached); ``corner``: a
    diagonal step needs both side cells (rAthena's and hunt_core.astar's rule); without it the
    reach is a SUPERSET of the client's moves."""
    return steps_from_many(grid, [start], corner, max_steps)


def steps_from_many(grid: Any, starts: Sequence[Cell], corner: bool = True,
                    max_steps: int | None = None) -> Any:  # fmt: skip
    """PURE: ``steps_from`` from the NEAREST of several cells (a multi-source BFS): a door's
    approach cells -> every cell's steps to the nearest of them (the grid is symmetric)."""
    g = np.asarray(grid, dtype=bool)
    h, w = g.shape
    d = np.full((h, w), -1, dtype=np.int32)
    q: deque[Cell] = deque()
    for start in starts:
        if 0 <= start[0] < w and 0 <= start[1] < h and g[start[1], start[0]]:
            d[start[1], start[0]] = 0
            q.append((int(start[0]), int(start[1])))
    while q:
        x, y = q.popleft()
        n = int(d[y, x])
        if max_steps is not None and n >= max_steps:
            continue
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                xx, yy = x + dx, y + dy
                if (dx == dy == 0) or not (0 <= xx < w and 0 <= yy < h) or not g[yy, xx]:
                    continue
                if d[yy, xx] >= 0 or (corner and dx and dy and not (g[y, xx] and g[yy, x])):
                    continue
                d[yy, xx] = n + 1
                q.append((xx, yy))
    return d


def _min_steps(d: Any, cells: Sequence[Cell]) -> int | None:
    h, w = d.shape
    vals = [int(d[c[1], c[0]]) for c in cells if 0 <= c[0] < w and 0 <= c[1] < h
            and d[c[1], c[0]] >= 0]  # fmt: skip
    return min(vals) if vals else None


def exit_click(house: House, walk_in: Any) -> Cell | None:
    """PURE: the cell to click to leave: the exit warp's own centre when walkable (every span here
    is >= 1, so a click one cell off still lands on the touch area); else the walkable touch-area
    cell with the largest margin to the area's edge, nearest the arrival; None when none is
    walkable."""
    g = np.asarray(walk_in, dtype=bool)
    h, w = g.shape
    cells = [c for c in house.exit.cells() if 0 <= c[0] < w and 0 <= c[1] < h and g[c[1], c[0]]]
    if not cells:
        return None
    if house.exit.cell in cells:
        return house.exit.cell
    (x, y), (sx, sy) = house.exit.cell, house.exit.span

    def margin(c: Cell) -> int:
        return min(sx - abs(c[0] - x), sy - abs(c[1] - y))

    def key(c: Cell) -> tuple[int, int, Cell]:
        return (-margin(c), max(abs(c[0] - house.arrival[0]), abs(c[1] - house.arrival[1])), c)

    return min(cells, key=key)


def room_check(house: House, walk_in: Any, forbidden: Sequence[Warp],
               npcs: Sequence[tuple[Cell, int]] = ()) -> dict[str, Any]:  # fmt: skip
    """PURE: the room behind ``house``'s door on the interior walkable grid ``walk_in`` (client
    AND server). ``sealed``: from the arrival, with AND without the corner rule (the superset of
    the client's moves), the own exit is reachable and NO forbidden warp cell is. Also: the exit
    click cell, its steps from the arrival, its Chebyshev distance to every forbidden span (the
    brief's >= FORBIDDEN_MIN), and each touch NPC's (cell, span) distance from the click cell."""
    click = exit_click(house, walk_in)
    out: dict[str, Any] = {"house": house.name, "door": list(house.door.cell),
                           "arrival": list(house.arrival), "exit": house.exit.name,
                           "exit_span": [house.exit.cell[0] - house.exit.span[0],
                                         house.exit.cell[0] + house.exit.span[0],
                                         house.exit.cell[1] - house.exit.span[1],
                                         house.exit.cell[1] + house.exit.span[1]],
                           "back": list(house.back),
                           "click": None if click is None else list(click)}  # fmt: skip
    g = np.asarray(walk_in, dtype=bool)
    arr_ok = bool(g[house.arrival[1], house.arrival[0]])
    reach: dict[str, dict[str, int | None]] = {}
    for corner in (True, False):
        d = steps_from(g, house.arrival, corner=corner)
        tag = "corner_rule" if corner else "no_corner_rule"
        reach[tag] = {w.name: _min_steps(d, w.cells()) for w in forbidden}
        reach[tag]["exit"] = _min_steps(d, house.exit.cells())
        if click is not None:
            reach[tag]["click"] = (int(d[click[1], click[0]]) if d[click[1], click[0]] >= 0
                                   else None)  # fmt: skip
    out["arrival_walkable"] = arr_ok
    out["steps"] = reach
    out["sealed"] = bool(arr_ok and all(
        reach[k]["exit"] is not None and all(reach[k][w.name] is None for w in forbidden)
        for k in reach))  # fmt: skip
    out["forbidden_cheb_from_click"] = (None if click is None else
                                        {w.name: w.cheb_to(click) for w in forbidden})  # fmt: skip
    out["forbidden_cheb_from_arrival"] = {w.name: w.cheb_to(house.arrival) for w in forbidden}
    out["npc_cheb_from_click"] = (None if click is None else
                                  [max(0, max(abs(c[0] - click[0]), abs(c[1] - click[1])) - s)
                                   for c, s in npcs])  # fmt: skip
    return out


def usable_why(check: Mapping[str, Any]) -> str | None:
    """PURE: why a house may NOT be used (None = usable): not sealed, no exit click cell, the click
    not reached from the arrival, or a forbidden span within FORBIDDEN_MIN of the click."""
    if not check["arrival_walkable"]:
        return "arrival not walkable"
    if check["click"] is None:
        return "no walkable exit cell"
    if not check["sealed"]:
        return "not sealed: a forbidden warp is reachable from the arrival"
    if check["steps"]["corner_rule"].get("click") is None:
        return "the exit click cell is not reached from the arrival"
    near = {k: v for k, v in (check["forbidden_cheb_from_click"] or {}).items()
            if v < FORBIDDEN_MIN}  # fmt: skip
    if near:
        return f"a forbidden span within {FORBIDDEN_MIN} of the click: {near}"
    return None


def zones_without(zones: Any, door: Warp) -> Any:
    """PURE: ``zones`` minus the no-enter polygons that hold the door's centre (its own grown
    area); every other item stays. The door click's walk is checked against this."""
    import map_zones as mz

    if zones is None:
        return None
    keep = tuple(z for i, z in enumerate(zones.no_enter) if i not in mz.polys_at(zones, door.cell))
    return dataclasses.replace(zones, no_enter=keep)


def door_free(ok: Any, both: Any, door: Warp) -> Any:
    """PURE: the zone-free grid the client paths the door click on: the stand grid ``ok`` (which
    keeps every warp span and touch area off) with ONLY this door's touch area opened where it is
    walkable (``both``: client AND server). A new array."""
    g = np.array(ok, dtype=bool)
    b = np.asarray(both, dtype=bool)
    h, w = g.shape
    for cx, cy in door.cells():
        if 0 <= cx < w and 0 <= cy < h:
            g[cy, cx] = bool(b[cy, cx])
    return g


def approach_cells(house: House, okr: Any, free: Any, zones: Any, r_: int = APPROACH_R,
                   max_steps: int = APPROACH_STEPS) -> list[Cell]:  # fmt: skip
    """PURE: the cells the door click may be made from: on the route grid ``okr`` (so outside
    every no-enter area, the door's own included), within ``r_`` (Chebyshev) of the door centre,
    and the click's walk -- the straight segment and the client's own path on ``free``
    (``door_free``: no warp span but this door's) -- keeps every zone but the door's own area
    (map_zones.walk_why), in at most ``max_steps`` steps. Nearest to the door first."""
    import map_zones as mz

    zw = zones_without(zones, house.door)
    ok = np.asarray(free, dtype=bool)
    g = np.asarray(okr, dtype=bool)
    h, w = g.shape
    (x0, y0) = house.door.cell
    out = []
    for cx in range(max(0, x0 - r_), min(w, x0 + r_ + 1)):
        for cy in range(max(0, y0 - r_), min(h, y0 + r_ + 1)):
            c = (cx, cy)
            if not g[cy, cx] or (zones is not None and mz.in_no_enter(zones, c)):
                continue
            if mz.walk_why(zw, ok, c, house.door.cell) is not None:
                continue
            p = mz.client_route(ok, c, house.door.cell)
            if p is None or len(p) - 1 > max_steps:
                continue
            out.append(c)
    return sorted(out, key=lambda c: (max(abs(c[0] - x0), abs(c[1] - y0)), c))


def choose(here: Cell, plans: Sequence[tuple[House, Sequence[Cell]]], okr: Any,
           max_steps: int) -> tuple[House, Cell, int] | None:  # fmt: skip
    """PURE: the house to rest in: the one whose nearest APPROACH cell is the fewest route-grid
    steps from ``here`` (BFS on ``okr`` with the corner rule; ties: the door's name), within
    ``max_steps``; None when none is."""
    d = steps_from(okr, here, corner=True, max_steps=max_steps)
    best: tuple[int, str, House, Cell] | None = None
    for house, cells in plans:
        for c in cells:
            n = int(d[c[1], c[0]])
            if n < 0:
                continue
            if best is None or (n, house.name) < (best[0], best[1]):
                best = (n, house.name, house, c)
    return None if best is None else (best[2], best[3], best[0])


def exit_point(camera: Any, gat_in: Any, house: House, click: Cell) -> tuple[float, float]:
    """PURE: the game-region pixel of the exit click, the character standing on the ARRIVAL cell
    (the screen centre): ``camera`` is in_orcs01's (indoor: poring_dataset.camera.map_camera),
    ``gat_in`` its client GAT (the floor's altitude; None = flat)."""
    rel = np.array([[click[0] - house.arrival[0], click[1] - house.arrival[1]]], dtype=float)
    alt = None if gat_in is None else gat_in.relative_altitude(house.arrival, rel)
    ((u, v),) = camera.project(rel, alt)
    return float(u), float(v)


# --- the map changes (pixels) -------------------------------------------------------------------


@dataclass
class Transition:
    """PURE tracker of ONE expected map change, fed one read per frame after OUR click:
    ``step(t, hp_ok, xy, mean)`` -> "wait" | "inside" | "back" | "none" (no load gap: the warp did
    not fire) | "stop:<why>". ``expect``: "inside" (the door click) or "back" (the exit click)."""

    expect: str
    t_click: float
    back: Cell | None = None
    gap_t0: float | None = None
    gap_t1: float | None = None
    since: float | None = None  # after the gap: the first read of the expected signature
    seen_dark: float | None = None

    def step(self, t: float, hp_ok: bool, xy: Cell | None, mean: float) -> str:
        if self.gap_t1 is None:
            if not hp_ok:
                if self.gap_t0 is None:
                    self.gap_t0 = t
                if t - self.gap_t0 > LOAD_MAX_S:
                    return "stop:the loading screen did not end"
                return "wait"
            if self.gap_t0 is not None and t - self.gap_t0 >= GAP_MIN_S:
                self.gap_t1 = t
            else:
                self.gap_t0 = None  # a blink, not a load
                if t - self.t_click > (ENTER_MAX_S if self.expect == "inside" else EXIT_MAX_S):
                    return "none"
                return "wait"
        if not hp_ok:
            return "stop:Basic Info lost again after the load"
        if self.expect == "inside":
            if xy is not None:
                return f"stop:a minimap readout {list(xy)} after the door (another map)"
            if mean > DARK_MAX:
                self.since = None
                if t - self.gap_t1 > 3 * INSIDE_S:
                    return f"stop:no minimap but a bright frame (mean {mean:.0f}): unknown map"
                return "wait"
            self.since = t if self.since is None else self.since
            return "inside" if t - self.since >= INSIDE_S else "wait"
        assert self.back is not None
        if xy is not None:
            d = max(abs(xy[0] - self.back[0]), abs(xy[1] - self.back[1]))
            if d <= RETURN_TOL:
                return "back"
            return f"stop:readout {list(xy)} {d} cells from {list(self.back)}"
        if mean <= DARK_MAX:
            self.seen_dark = t
            if t - self.gap_t1 > 3 * INSIDE_S:
                return "stop:still a dark frame with no minimap after the exit's load"
            return "wait"
        return "back" if t - self.gap_t1 >= BACK_READ_S else "wait"


def gap_unexpected(gap_s: float, since_fly_s: float, since_click_s: float, fly_jump_s: float
                   ) -> bool:  # fmt: skip
    """PURE (house mode's map-change bar on the FIELD): Basic Info unreadable for >= GAP_STOP_S
    with no Fly Wing within ``fly_jump_s`` (a Fly Wing reloads the map: every gap >= 0.8 s in the
    allowed 8.x runs followed one) and no door / exit click within ENTER_MAX_S = a map change
    nobody asked for: STOP."""
    return gap_s >= GAP_STOP_S and since_fly_s > fly_jump_s and since_click_s > ENTER_MAX_S


# --- the trip (a closed transition table) -------------------------------------------------------

STATES = ("field", "walk", "door", "inside", "rest", "exit", "back")
NEXT: dict[tuple[str, str], str] = {
    ("field", "rest_wanted"): "walk",
    ("walk", "left_rest"): "field",  # a fight / Fly Wing took the walk; the rest decides again
    ("walk", "fallback"): "field",  # no house in reach / the walk timed out: today's field rest
    ("walk", "door_click"): "door",
    ("door", "inside"): "inside",
    ("door", "none"): "walk",  # the warp did not fire (one retry; then the fallback)
    ("door", "hit"): "field",  # hit before any load gap: still on the field, fight
    ("inside", "sat"): "rest",
    ("rest", "done"): "exit",
    ("exit", "exit_click"): "exit",
    ("exit", "back"): "back",
    ("back", "resumed"): "field",
}


class TripStop(RuntimeError):
    """An event the trip's table does not allow in its state: the runner STOPS (r.Stop)."""


@dataclass
class Trip:
    state: str = "field"
    house: str | None = None
    log: list[tuple[str, str, str]] = dataclasses.field(default_factory=list)

    def advance(self, event: str) -> str:
        nxt = NEXT.get((self.state, event))
        if nxt is None:
            raise TripStop(f"house trip: event {event!r} in state {self.state!r}")
        self.log.append((self.state, event, nxt))
        self.state = nxt
        return nxt

    @property
    def off_field(self) -> bool:
        """In a state where the field logic (sustain's Fly Wing, the position rules) must not
        run: from the door click until the field's readout is back."""
        return self.state in ("door", "inside", "rest", "exit", "back")


# --- the offline table (the doc's) --------------------------------------------------------------


def table(kb: Mapping[str, Any], walk_in: Any, npcs: Sequence[tuple[Cell, int]] = ()
          ) -> list[dict[str, Any]]:  # fmt: skip
    hs = houses(kb)
    fb = forbidden_warps(kb)
    rows: list[dict[str, Any]] = []
    for h in hs:
        c = room_check(h, walk_in, fb, npcs)
        c["usable_why"] = usable_why(c)
        rows.append(c)
    return rows


def rest_decisions(events: Sequence[Mapping[str, Any]]) -> list[tuple[Cell, int | None]]:
    """PURE: each ``rest_go`` of a dungeon_hunt run with our cell then (the last position read
    before it) and its HP percent; a rest_go before any position read is skipped."""
    out: list[tuple[Cell, int | None]] = []
    pos: Cell | None = None
    for e in events:
        if e.get("kind") == "hp_read" and e.get("pos"):
            pos = (int(e["pos"][0]), int(e["pos"][1]))
        elif e.get("kind") == "rest_go" and pos is not None:
            out.append((pos, e.get("pct")))
    return out


def _stats(xs: Sequence[float]) -> dict[str, float] | None:
    if not xs:
        return None
    a = np.asarray(xs, dtype=float)
    return {"n": len(a), "median": float(np.median(a)), "p75": float(np.percentile(a, 75)),
            "p90": float(np.percentile(a, 90)), "max": float(a.max()),
            "mean": round(float(a.mean()), 1)}  # fmt: skip


def field_grids(map_name: str = FIELD) -> tuple[Any, Any, Any, Any]:
    """(ok, okr, zones, both) for ``map_name`` exactly as dungeon_hunt.run builds them: the stand
    grid, the route grid minus what the zones seal off, the zones, client AND server walkable.
    Local run-time data only (the client GAT in /dev/shm, L3, the map cache)."""
    import map_zones as mz
    from anim_region import stand_grid

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod
    from poring_dataset import walkable as wk

    gat = gatmod.parse((cam.GAT_DIR / f"{map_name}.gat").read_bytes())
    ok = stand_grid(map_name, gat)
    zones = mz.load(map_name, shape=ok.shape)
    okr = mz.route_grid(ok, zones)
    okr = okr & ~mz.sealed_off(ok, okr)
    return ok, okr, zones, wk.load_both(map_name)[1]


def cmd_steps(sids: Sequence[str], demo: Path, kb: Mapping[str, Any], max_steps: int,
              min_hp: int) -> dict[str, Any]:  # fmt: skip
    """The estimate's walking side (gef10-house-rest.md section 6): the route-grid steps from
    every rest decision of the runs ``sids`` to the nearest USABLE (sealed) door's approach cell,
    and to any door's, on the grids dungeon_hunt.run builds (stand grid, zones, route grid minus
    what the zones seal off). Reads the runs' events only."""
    from poring_dataset import walkable as wk

    ok, okr, zones, both = field_grids(FIELD)
    walk_in = wk.load_both(HOUSE_MAP)[1]
    fb = forbidden_warps(kb)
    hs = houses(kb)
    usable = {h.name for h in hs if usable_why(room_check(h, walk_in, fb)) is None}
    dist = {h.name: steps_from_many(okr, approach_cells(h, okr, door_free(ok, both, h.door),
                                                       zones)) for h in hs}  # fmt: skip
    rows: list[dict[str, Any]] = []
    for sid in sids:
        evs = [json.loads(ln) for ln in (demo / sid / "events.jsonl").open()]
        for here, pct in rest_decisions(evs):
            got = {n: int(d[here[1], here[0]]) for n, d in dist.items() if d[here[1], here[0]] >= 0}
            best_u = min(((v, n) for n, v in got.items() if n in usable), default=None)
            best_a = min(((v, n) for n, v in got.items()), default=None)
            rows.append({"sid": sid, "at": list(here), "pct": pct,
                         "usable": None if best_u is None else list(best_u),
                         "any": None if best_a is None else list(best_a)})  # fmt: skip
    su = [r["usable"][0] for r in rows if r["usable"]]
    qual = [r for r in rows if r["usable"] and r["usable"][0] <= max_steps
            and (r["pct"] or 0) >= min_hp]  # fmt: skip
    return {"usable": sorted(usable), "rows": rows, "steps_usable": _stats(su),
            "steps_any": _stats([r["any"][0] for r in rows if r["any"]]),
            "qualifying": len(qual), "of": len(rows),
            "qualifying_steps": _stats([r["usable"][0] for r in qual]),
            "doors": dict(sorted(Counter(r["usable"][1] for r in rows
                                         if r["usable"]).items()))}  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("table")
    t.add_argument("--kb", default=str(ROOT / "data" / "kb"))
    t.add_argument("--mapcache", default=None, help="the server map cache dir (default: the "
                   "package's _generated)")  # fmt: skip
    s = sub.add_parser("steps", help="the route steps from each rest decision of the runs to the "
                       "nearest sealed door (gef10-house-rest.md section 6)")  # fmt: skip
    s.add_argument("sids", nargs="+")
    s.add_argument("--kb", default=str(ROOT / "data" / "kb"))
    s.add_argument("--demo", default="/dev/shm/poring-lab-demo")
    s.add_argument("--max-steps", type=int, default=120)
    s.add_argument("--min-hp", type=int, default=30, help="HP percent")
    a = ap.parse_args()
    from poring_dataset import mapcache
    from poring_dataset import walkable as wk

    kb = json.loads((Path(a.kb) / "warps.json").read_text())
    if a.cmd == "steps":
        print(json.dumps(cmd_steps(a.sids, Path(a.demo), kb, a.max_steps, a.min_hp), indent=1))
        return 0
    mc = Path(a.mapcache) if a.mapcache else mapcache.GENERATED
    _gat, both = wk.load_both(HOUSE_MAP, mapcache_dir=mc)
    print(json.dumps(table(kb, both), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
