#!/usr/bin/env python3
"""PATROL ROUTES -- reviewed per-map waypoint circuits (Batt 2026-10-22, the Crusader's demo in
orcsdun01: the map is a LOOP around a central block, and Batt walks a fixed circuit of waypoints in
ONE direction, never back and forth, so they keep meeting monsters as they respawn). The twin of
map_zones.py: static map data (ADR-0015: static map knowledge at plan time), reviewed under the
SAME rules (``map_zones.review``: a person, or the agent under a person's RECORDED delegation) and
loaded fail closed. This module loads and checks a file, proves it on the map, and holds the PURE
walking helpers a runner uses. Until a map's file exists, nothing changes.

    map_routes.py check <map> [--root DIR]     load + schema (no map data needed)
    map_routes.py prove <map> [--root DIR]     on the map: every waypoint walkable and outside
                                               the zones, every leg connected (its length)

THE FILE: config/routes/<map>.yaml (the format: config/routes/README.md). No file = ``load`` ->
None = INERT. A file that exists but is wrong raises RouteError: the run must not start on it.

COORDINATES: map cells, x east, y NORTH, as map_zones (the minimap readout's, /where's and the
server's numbers); a grid is indexed [y, x] with that same y, no flip anywhere.

A ROUTE: its ``waypoints`` in the LISTED ORDER, which is the walking direction. ``kind`` loop: the
last waypoint connects back to the first (the closing leg); path: open, it ends at its last. A LEG
is two consecutive waypoints (and a loop's closing leg). A leg is walked on the ROUTE GRID (the
walkable cells minus every zone, ``map_zones.route_grid``, minus what the zones seal off), never
straight: ``prove`` checks every leg is connected there, with the runner's own router
(``hunt_core.astar``: 8-connected, octile costs, a diagonal step needs both side cells).

WALKING (Batt 2026-10-22: "afterwards resume at the NEXT waypoint AHEAD on the loop (never turn
back to a passed one)"):
- ``reached``: within ``tol`` cells (Chebyshev) of a waypoint;
- ``next_index``: the waypoint after i (cyclic on a loop; None past a path's end);
- ``resume_index``: after an interruption (a fight or a loot step moved the walker off its leg),
  the waypoint to walk to. k = the last waypoint reached or passed; the candidates are k+1 and k+2
  (cyclic). k+1 counts as PASSED -- the answer is k+2 -- when ``here`` is within ``tol`` of it, or
  strictly closer to the leg k+1 -> k+2 than to the leg k -> k+1 (Chebyshev distance to the
  straight segment, sampled one cell per step: ``seg_dist``); else the answer is k+1. Never k or
  a waypoint behind it;
- ``entry_index``: where to JOIN a route from any cell (the run's start, after a Fly Wing): the
  NEAREST waypoint j (the first on a tie), then the same rule with j as the candidate -- j counts
  as passed (the answer is the one after it) when ``here`` is within ``tol`` of it or strictly
  closer to the leg after j than to the leg before it (a path's first waypoint: to j itself).
On a path, None means its end is reached (nothing left to walk); on a loop the answer is never None.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hunt_core as hc  # noqa: E402
import map_zones as mz  # noqa: E402

Cell = tuple[int, int]
ROUTES_DIR = Path(__file__).resolve().parents[1] / "config" / "routes"
TOP_KEYS = frozenset({"map", "reviewed_by", "reviewed", "delegation", "source", "routes"})
ITEM_KEYS = ("id", "kind", "note", "waypoints")
KINDS = {"loop": 3, "path": 2}  # a route's kind -> its fewest waypoints
ROUTE_ID = re.compile(r"[a-z0-9-]{1,40}")
REACH_TOL = 2  # a waypoint counts as reached within this many cells (Chebyshev)
LEG_MAX_NODES = 200_000  # hunt_core.astar's own bound: a leg may cross the whole map


class RouteError(ValueError):
    """A routes file that exists but is wrong: the run must not start on it (fail closed)."""


@dataclass(frozen=True)
class Route:
    id: str
    kind: str  # "loop" | "path"
    note: str
    waypoints: tuple[Cell, ...]  # the LISTED order = the walking direction

    @property
    def loop(self) -> bool:
        return self.kind == "loop"

    def legs(self) -> list[tuple[int, int]]:
        """The legs as waypoint indices (i, j), in walking order; a loop's closing leg last."""
        n = len(self.waypoints)
        return [(i, i + 1) for i in range(n - 1)] + ([(n - 1, 0)] if self.loop else [])


@dataclass(frozen=True)
class Routes:
    map: str
    reviewed_by: str
    reviewed: str  # ISO date
    source: str  # where the waypoints came from (a demo session, an extractor, a drawing)
    routes: tuple[Route, ...]  # >= 1; a patrol hunt walks the first
    path: str = ""
    sha256: str = ""
    delegation: str = ""  # a delegated review's note (the person's decision it cites); else ""


# --- the file -------------------------------------------------------------------------------------


def _bad(source: str, msg: str) -> RouteError:
    return RouteError(f"{source}: {msg}")


def _route(it: Any, where: str, source: str, shape: tuple[int, int] | None, ids: set[str]
           ) -> Route:  # fmt: skip
    if not isinstance(it, dict):
        raise _bad(source, f"{where}: a mapping with {', '.join(ITEM_KEYS)}")
    keys = set(it)
    if keys != set(ITEM_KEYS):
        miss, extra = sorted(set(ITEM_KEYS) - keys), sorted(keys - set(ITEM_KEYS))
        raise _bad(source, f"{where}: keys must be {', '.join(ITEM_KEYS)} (missing {miss}, "
                           f"unknown {extra})")  # fmt: skip
    rid = it["id"]
    if not isinstance(rid, str) or not ROUTE_ID.fullmatch(rid):
        raise _bad(source, f"{where}: id {rid!r} is not 1-40 of [a-z0-9-]")
    where = f"route {rid!r}"
    if rid in ids:
        raise _bad(source, f"{where}: a duplicate id (ids are unique per file)")
    ids.add(rid)
    kind, note, raw = it["kind"], it["note"], it["waypoints"]
    if kind not in KINDS:
        raise _bad(source, f"{where}: kind {kind!r} is loop or path")
    if not isinstance(note, str) or not note.strip():
        raise _bad(source, f"{where}: a short note is required")
    if not isinstance(raw, list):
        raise _bad(source, f"{where}: waypoints is a list of [x, y] cells")
    wps = [mz._cell(p, f"{where} waypoint {k}", source, shape, RouteError)
           for k, p in enumerate(raw)]  # fmt: skip
    if kind == "loop" and len(wps) > KINDS["loop"] and wps[-1] == wps[0]:
        wps = wps[:-1]  # an explicitly closed loop: the repeated first waypoint is dropped
    if len(wps) < KINDS[kind]:
        raise _bad(source, f"{where}: {len(wps)} waypoint(s), a {kind} needs at least "
                           f"{KINDS[kind]}")  # fmt: skip
    for k in range(1, len(wps)):
        if wps[k] == wps[k - 1]:
            raise _bad(source, f"{where}: waypoint {k} repeats the one before it")
    if wps[-1] == wps[0]:
        raise _bad(source, f"{where}: its last waypoint is its first (a loop closes by itself; a "
                           "path that ends where it starts is a loop)")  # fmt: skip
    if kind == "loop" and all(mz._orient(wps[0], wps[1], c) == 0 for c in wps[2:]):
        raise _bad(source, f"{where}: its waypoints lie on one line, so the loop walks back and "
                           "forth (Batt: one direction, never back and forth)")  # fmt: skip
    return Route(rid, kind, note.strip(), tuple(wps))


def parse(data: Any, map_name: str, shape: tuple[int, int] | None = None,
          source: str = "<routes>") -> Routes:  # fmt: skip
    """PURE: the routes from the YAML's data, checked; RouteError on anything wrong. The review
    (reviewed_by, reviewed, delegation) is map_zones.review's, unchanged. ``shape`` (h, w): the
    map's grid -- every waypoint must lie on it."""
    if not isinstance(data, dict):
        raise _bad(source, "not a mapping (map, reviewed_by, reviewed, source, routes)")
    extra = sorted(set(data) - TOP_KEYS)
    if extra:
        raise _bad(source, f"unknown key(s) {extra} (allowed: {sorted(TOP_KEYS)})")
    if data.get("map") != map_name:
        raise _bad(source, f"map {data.get('map')!r} is not {map_name!r} (the file's name)")
    rb, reviewed, deleg = mz.review(data, source, "routes", RouteError)
    src = data.get("source")
    if not isinstance(src, str) or not src.strip():
        raise _bad(source, "source: where the waypoints came from (a demo session and its "
                           "extractor, a person's drawing) is required")  # fmt: skip
    raw = data.get("routes")
    if not isinstance(raw, list) or not raw:
        raise _bad(source, "routes: a list of at least one route")
    ids: set[str] = set()
    routes = tuple(_route(it, f"routes[{i}]", source, shape, ids) for i, it in enumerate(raw))
    return Routes(map=map_name, reviewed_by=rb, reviewed=reviewed, source=src.strip(),
                  routes=routes, delegation=deleg)  # fmt: skip


def load(map_name: str, root: Path | str = ROUTES_DIR, shape: tuple[int, int] | None = None
         ) -> Routes | None:  # fmt: skip
    """The reviewed routes for ``map_name`` from ``root``/<map>.yaml; None when there is no file
    (INERT: nothing changes). A file that is there but wrong raises RouteError (fail closed); so
    does a <map>.yml beside it (it would be silently ignored otherwise)."""
    if not mz.MAP_NAME.fullmatch(map_name):
        raise RouteError(f"map name {map_name!r} is not a file name")
    root = Path(root)
    if (root / f"{map_name}.yml").exists():
        raise RouteError(f"{root / (map_name + '.yml')}: routes files end in .yaml (rename it)")
    path = root / f"{map_name}.yaml"
    if not path.exists():
        return None
    raw = path.read_bytes()
    try:
        data = yaml.safe_load(raw.decode("utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise RouteError(f"{path}: not readable YAML ({exc})") from None
    r = parse(data, map_name, shape, source=str(path))
    return dataclasses.replace(r, path=str(path), sha256=hashlib.sha256(raw).hexdigest())


def summary(routes: Routes) -> dict[str, Any]:
    """The run-start record: the file, its review, its source and each route's shape."""
    return {
        "file": routes.path, "sha256": routes.sha256, "reviewed_by": routes.reviewed_by,
        "reviewed": routes.reviewed, **({"delegation": routes.delegation} if routes.delegation
                                         else {}),
        "source": routes.source,
        "routes": [{"id": r.id, "kind": r.kind, "waypoints": len(r.waypoints),
                    "legs": len(r.legs())} for r in routes.routes],
    }  # fmt: skip


# --- on the map -----------------------------------------------------------------------------------


def route_grid(grid: Any, zones: mz.Zones | None) -> Any:
    """PURE: where a leg may be walked -- ``grid`` minus every zone (``map_zones.route_grid``) minus
    the pieces the zones seal off (``map_zones.sealed_off``): the runners' own route grid
    (dungeon_hunt.py, hunt_flow.py). A new array."""
    g = np.asarray(grid, dtype=bool)
    rg = np.asarray(mz.route_grid(g, zones), dtype=bool)
    return rg & ~mz.sealed_off(g, rg) if zones is not None else rg.copy()


def leg_path(rgrid: Any, a: Cell, b: Cell, max_nodes: int = LEG_MAX_NODES) -> list[Cell] | None:
    """PURE: a leg a -> b walked on the route grid ``rgrid`` (hunt_core.astar, the runner's own
    router); None when an end is off the grid or closed, or no path exists."""
    g = np.asarray(rgrid, dtype=bool)
    h, w = g.shape
    if not all(0 <= c[0] < w and 0 <= c[1] < h for c in (a, b)):
        return None
    return hc.astar(g, a, b, max_nodes=max_nodes)  # type: ignore[no-any-return]


def path_cost(path: Sequence[Cell]) -> float:
    """A walked path's cost in straight steps (a diagonal step = 1.4: hunt_core.STEP_MS)."""
    steps = zip(path, path[1:], strict=False)
    return sum(hc.STEP_MS[a[0] != b[0] and a[1] != b[1]] for a, b in steps)


def closed_why(c: Cell, grid: Any, zones: mz.Zones | None) -> str | None:
    """PURE: why a waypoint cannot be stood on -- off the map, not walkable on ``grid``, inside a
    no-enter area, on a no-cross line (every zone named); None when it can."""
    g = np.asarray(grid, dtype=bool)
    h, w = g.shape
    if not (0 <= c[0] < w and 0 <= c[1] < h):
        return f"off the map ({w} x {h} cells)"
    if not g[c[1], c[0]]:
        return "not walkable"
    if zones is None:
        return None
    why = [f"inside no-enter area {z.id!r}" for z in zones.no_enter if mz.in_polygon(c, z.polygon)]
    why += [f"on no-cross line {z.id!r}" for z in zones.no_cross
            if any(c in mz.supercover(a, b) for a, b in z.segments())]  # fmt: skip
    return ", ".join(why) or None


def prove(routes: Routes, grid: Any, zones: mz.Zones | None) -> dict[str, Any]:
    """PURE: ``routes`` on the map. ``grid``: the walkable cells (the runner's stand grid);
    ``zones``: the map's zones (None: none). Every waypoint must be walkable and outside every
    zone (``closed_why``); every leg, a loop's closing one too, connected on the route grid
    (``route_grid``, ``leg_path``). Returns {"ok", "problems": [...], "routes": [{"id", "kind",
    "legs": [{"from", "to", "steps", "cost"}], "total_steps", "total_cost"}]} -- a leg's steps
    are its cells walked (8-connected), its cost in straight steps (a diagonal = 1.4)."""
    g = np.asarray(grid, dtype=bool)
    rg = route_grid(g, zones)
    problems: list[str] = []
    out = []
    for r in routes.routes:
        for k, c in enumerate(r.waypoints):
            why = closed_why(c, g, zones)
            if why is None and not rg[c[1], c[0]]:
                why = "sealed off by the zones"
            if why is not None:
                problems.append(f"route {r.id!r} waypoint {k} {list(c)}: {why}")
        legs = []
        for i, j in r.legs():
            a, b = r.waypoints[i], r.waypoints[j]
            p = leg_path(rg, a, b)
            if p is None:
                problems.append(f"route {r.id!r} leg {i} -> {j} ({list(a)} -> {list(b)}): not "
                                "connected on the route grid (the walkable cells minus the "
                                "zones)")  # fmt: skip
            legs.append({"from": i, "to": j, "steps": None if p is None else len(p) - 1,
                         "cost": None if p is None else round(path_cost(p), 1)})  # fmt: skip
        whole = all(leg["steps"] is not None for leg in legs)
        out.append({"id": r.id, "kind": r.kind, "waypoints": len(r.waypoints), "legs": legs,
                    "total_steps": sum(leg["steps"] for leg in legs) if whole else None,
                    "total_cost": round(sum(leg["cost"] for leg in legs), 1) if whole
                    else None})  # fmt: skip
    return {"ok": not problems, "problems": problems, "routes": out}


# --- walking (PURE) -------------------------------------------------------------------------------


def cheb(a: Sequence[int], b: Sequence[int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def reached(here: Cell, wp: Cell, tol: int = REACH_TOL) -> bool:
    """PURE: ``here`` is within ``tol`` cells (Chebyshev) of the waypoint."""
    return cheb(here, wp) <= tol


def next_index(route: Route, i: int) -> int | None:
    """PURE: the waypoint after ``i`` in the walking direction: cyclic on a loop; None past the
    end of a path."""
    n = len(route.waypoints)
    if not 0 <= i < n:
        raise IndexError(f"route {route.id!r}: no waypoint {i} (it has {n})")
    if route.loop:
        return (i + 1) % n
    return i + 1 if i + 1 < n else None


def prev_index(route: Route, i: int) -> int | None:
    """PURE: the waypoint before ``i``: cyclic on a loop; None before the start of a path."""
    n = len(route.waypoints)
    if not 0 <= i < n:
        raise IndexError(f"route {route.id!r}: no waypoint {i} (it has {n})")
    if route.loop:
        return (i - 1) % n
    return i - 1 if i > 0 else None


def seg_cells(a: Cell, b: Cell) -> list[Cell]:
    """PURE: the straight segment a -> b sampled one cell per step: n = its Chebyshev length, n + 1
    cells, each coordinate rounded half up (exact integers)."""
    n = cheb(a, b)
    if n == 0:
        return [a]
    dx, dy = b[0] - a[0], b[1] - a[1]
    return [(a[0] + (2 * i * dx + n) // (2 * n), a[1] + (2 * i * dy + n) // (2 * n))
            for i in range(n + 1)]  # fmt: skip


def seg_dist(here: Cell, a: Cell, b: Cell) -> int:
    """PURE: the Chebyshev distance from ``here`` to the straight segment a-b (``seg_cells``)."""
    return min(cheb(here, c) for c in seg_cells(a, b))


def _ahead(route: Route, here: Cell, k: int | None, j: int, tol: int) -> int | None:
    """The rule of the module docstring: ``j`` is the candidate, ``k`` the waypoint before it
    (None at a path's start). j counts as passed -- the one after it is the answer -- when
    ``here`` is within ``tol`` of it, or strictly closer to the leg after j than to the leg
    before it."""
    wp = route.waypoints
    after = next_index(route, j)
    if reached(here, wp[j], tol):
        return after
    if after is None:
        return j
    behind = seg_dist(here, wp[k], wp[j]) if k is not None else cheb(here, wp[j])
    return after if seg_dist(here, wp[j], wp[after]) < behind else j


def resume_index(route: Route, here: Cell, last_idx: int, tol: int = REACH_TOL) -> int | None:
    """PURE: after an interruption (a fight or a loot step moved the walker), the waypoint to walk
    to: k = ``last_idx``, the last waypoint reached or passed; the answer is k+1, or k+2 when k+1
    counts as passed (``here`` within ``tol`` of it, or strictly closer to the leg k+1 -> k+2 than
    to the leg k -> k+1). Cyclic on a loop; never k or one behind it. None: a path's end is
    reached."""
    j = next_index(route, last_idx)
    return None if j is None else _ahead(route, here, last_idx, j, tol)


def entry_index(route: Route, here: Cell, tol: int = REACH_TOL) -> int | None:
    """PURE: where to JOIN the route from any cell (the run's start, after a Fly Wing): the
    nearest waypoint (the first on a tie), or the one after it when ``here`` lies past it (within
    ``tol`` of it, or strictly closer to the leg after it than to the leg before it). None: a
    path's end is reached."""
    j = min(range(len(route.waypoints)), key=lambda i: cheb(here, route.waypoints[i]))
    return _ahead(route, here, prev_index(route, j), j, tol)


# --- the CLI --------------------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    ck = sub.add_parser("check", help="load config/routes/<map>.yaml and check its schema")
    ck.add_argument("map")
    ck.add_argument("--root", default=str(ROUTES_DIR))
    pv = sub.add_parser("prove", help="the routes on the map: waypoints, legs and their lengths")
    pv.add_argument("map")
    pv.add_argument("--root", default=str(ROUTES_DIR))
    a = ap.parse_args()
    if a.cmd == "prove":
        return _prove_cli(a.map, a.root)
    try:
        r = load(a.map, a.root)
    except RouteError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    if r is None:
        print(json.dumps({"ok": True, "file": None, "note": "no routes file: INERT"}))
        return 0
    print(json.dumps({"ok": True, **summary(r)}))
    return 0


def _prove_cli(map_name: str, root: str) -> int:
    """``prove``: on the runner's stand grid, loaded as scripts/dungeon_hunt.py loads it (the map's
    GAT from poring_dataset.camera.GAT_DIR, anim_region.stand_grid) with the map's zones -- the
    JSON of ``prove``; exit 1 on any problem, 2 when the map data is not there."""
    import anim_region as ar

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    try:
        gat = gatmod.parse((cam.GAT_DIR / f"{map_name}.gat").read_bytes())
        stand = np.asarray(ar.stand_grid(map_name, gat), dtype=bool)
    except Exception as exc:  # noqa: BLE001 -- refused: the proof needs the map's own grid
        print(json.dumps({"ok": False, "error": f"no stand grid for {map_name}: {exc}"}))
        return 2
    try:
        zones = mz.load(map_name, shape=stand.shape)
        r = load(map_name, root, stand.shape)
    except (mz.ZoneError, RouteError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    if r is None:
        print(json.dumps({"ok": False, "error": f"no routes file for {map_name}"}))
        return 1
    rep = prove(r, stand, zones)
    zf = {"file": zones.path, "sha256": zones.sha256} if zones is not None else None
    print(json.dumps({"map": map_name, **summary(r), "zones": zf,
                      "grid": {"shape": list(stand.shape), "walkable": int(stand.sum())},
                      **rep}))  # fmt: skip
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
