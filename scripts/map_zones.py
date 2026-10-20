#!/usr/bin/env python3
"""MAP ZONES -- Batt's per-map FORBIDDEN zones (Batt 2026-10-20 ~21:0x, "map traps": the bot
walked through a NARROW ENTRANCE into a big room and kept circling inside it; the pocket escape
never fired, the room is large). Batt authors the zones by hand; this module loads and checks his
file and holds the PURE geometry the runner (hunt_flow.py) enforces. Until his file exists,
nothing changes in the bot.

    map_zones.py check <map> [--root DIR]     validate a file, print what it removes

THE FILE: config/map_zones/<map>.yaml (the format: config/map_zones/README.md). Static map data,
Batt's own knowledge (ADR-0015: static map knowledge at plan time), reviewed: the loader refuses a
file without ``reviewed_by`` -- the agent never approves a zone. No file = ``load`` -> None =
INERT. A file that exists but is wrong raises ZoneError: the run must not start on it.

COORDINATES: map cells, x east, y NORTH -- the server's, /where's and the minimap readout's (x, y).
The runner's grids are numpy arrays indexed [y, x] with that SAME y: gat.py reads tile x + y *
width and reshapes to (height, width), walkable.both() keeps it, and hunt_flow reads
``area[c[1], c[0]]`` / ``ok[mm[1], mm[0]]`` with the readout's (x, y) -- no flip anywhere. So a
zone point (x, y) is grid[y, x]. Cell (x, y) is the closed square [x - 0.5, x + 0.5] x
[y - 0.5, y + 0.5] around its centre (x, y).

TWO KINDS
- no_cross: a polyline that acts as a WALL. Rasterised as a CLOSED SUPERCOVER: every cell whose
  closed square a segment touches (a pass exactly through a cell corner takes all four cells). So
  no 8-connected step between two cells off the raster can meet the line -- with or without
  hunt_core.astar's diagonal rule (zone_path's and unstall_cells' BFS have none); the tests check
  every adjacent pair. A step (centre to centre) VIOLATES a line when it meets it anywhere -- a
  touch or a collinear run counts (conservative) -- except at the step's own START: a GM standing
  on a line (the client's own path put it there) may step off it.
- no_enter: a polygon (closed implicitly) = an AREA: the cells whose CENTRE is inside it or on its
  boundary. A path ENTERS it when it visits such a cell of a polygon its start is not in: a GM
  inside walks out (``exit_path``) without breaking the rule. An area is not a wall: a 1-cell
  diagonal strip can be passed corner to corner; a wall is a no_cross line.
"""

from __future__ import annotations

import argparse
import dataclasses
import functools
import hashlib
import heapq
import json
import math
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hunt_core as hc  # noqa: E402

Cell = tuple[int, int]
ZONES_DIR = Path(__file__).resolve().parents[1] / "config" / "map_zones"
# a reviewer the loader refuses: the agent (any of its names) never approves a zone
AGENT_NAMES = frozenset({"agent", "ai", "assistant", "auto", "automatic", "bot", "claude"})
# the client-route proxy's A* bound: a walk click is <= ~15 cells away; an unreachable end costs
# ~55 ms at this bound (20,000 nodes: ~300 ms; measured 2026-10-20 on a 400 x 400 grid)
ROUTE_MAX_NODES = 4_000
TOP_KEYS = frozenset({"map", "reviewed_by", "reviewed", "no_cross", "no_enter"})
MAP_NAME = re.compile(r"[A-Za-z0-9_@-]{1,40}")


class ZoneError(ValueError):
    """A zones file that exists but is wrong: the run must not start on it (fail closed)."""


@dataclass(frozen=True)
class NoCross:
    id: str
    note: str
    points: tuple[Cell, ...]  # a polyline, >= 2 points

    def segments(self) -> list[tuple[Cell, Cell]]:
        return list(zip(self.points, self.points[1:], strict=False))


@dataclass(frozen=True)
class NoEnter:
    id: str
    note: str
    polygon: tuple[Cell, ...]  # >= 3 points, closed implicitly


@dataclass(frozen=True)
class Zones:
    map: str
    reviewed_by: str
    reviewed: str  # ISO date
    no_cross: tuple[NoCross, ...] = ()
    no_enter: tuple[NoEnter, ...] = ()
    path: str = ""
    sha256: str = ""


# --- the file -------------------------------------------------------------------------------------


def _bad(source: str, msg: str) -> ZoneError:
    return ZoneError(f"{source}: {msg}")


def _cell(v: Any, where: str, source: str, shape: tuple[int, int] | None) -> Cell:
    ok_ = (isinstance(v, (list, tuple)) and len(v) == 2
           and all(isinstance(c, int) and not isinstance(c, bool) for c in v))  # fmt: skip
    if not ok_:
        raise _bad(source, f"{where}: {v!r} is not a cell [x, y] of two integers")
    x, y = int(v[0]), int(v[1])
    if shape is not None and not (0 <= x < shape[1] and 0 <= y < shape[0]):
        raise _bad(source, f"{where}: ({x}, {y}) is off the map ({shape[1]} x {shape[0]} cells)")
    return (x, y)


def _orient(a: Sequence[int], b: Sequence[int], c: Sequence[int]) -> int:
    """The sign of (b - a) x (c - a): +1 left of a->b, -1 right, 0 on its line. Exact (ints)."""
    v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return (v > 0) - (v < 0)


def _on_segment(a: Cell, b: Cell, p: Cell) -> bool:
    return (_orient(a, b, p) == 0 and min(a[0], b[0]) <= p[0] <= max(a[0], b[0])
            and min(a[1], b[1]) <= p[1] <= max(a[1], b[1]))  # fmt: skip


def segments_meet(a: Cell, b: Cell, c: Cell, d: Cell) -> bool:
    """PURE: the CLOSED segments a-b and c-d share a point (a crossing, a touch, a collinear
    overlap; a zero-length segment is its point). Exact on integer cells."""
    d1, d2 = _orient(c, d, a), _orient(c, d, b)
    d3, d4 = _orient(a, b, c), _orient(a, b, d)
    if d1 * d2 < 0 and d3 * d4 < 0:
        return True
    return ((d1 == 0 and _on_segment(c, d, a)) or (d2 == 0 and _on_segment(c, d, b))
            or (d3 == 0 and _on_segment(a, b, c))
            or (d4 == 0 and _on_segment(a, b, d)))  # fmt: skip


def _poly_area2(poly: Sequence[Cell]) -> int:
    return sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0]
               * poly[i][1] for i in range(len(poly)))  # fmt: skip


def _check_polygon(poly: list[Cell], where: str, source: str) -> None:
    n = len(poly)
    if len(set(poly)) != n:
        raise _bad(source, f"{where}: a point repeats (the polygon closes by itself)")
    if _poly_area2(poly) == 0:
        raise _bad(source, f"{where}: no area (its points are collinear)")
    edges = [(poly[i], poly[(i + 1) % n]) for i in range(n)]
    for i in range(n):
        prv, v, nxt = poly[i - 1], poly[i], poly[(i + 1) % n]
        back = (prv[0] - v[0]) * (nxt[0] - v[0]) + (prv[1] - v[1]) * (nxt[1] - v[1]) > 0
        if _orient(prv, v, nxt) == 0 and back:
            raise _bad(source, f"{where}: its edges fold back at {v}")
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue  # the closing edge and the first one share poly[0]
            if segments_meet(*edges[i], *edges[j]):
                raise _bad(source, f"{where}: its edges cross ({edges[i]} and {edges[j]})")


def _items(data: dict[str, Any], kind: str, field: str, min_n: int, source: str,
           shape: tuple[int, int] | None, ids: set[str]
           ) -> list[tuple[str, str, list[Cell]]]:  # fmt: skip
    raw = data.get(kind)
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise _bad(source, f"{kind}: a list of items, not {type(raw).__name__}")
    out = []
    for i, it in enumerate(raw):
        where = f"{kind}[{i}]"
        if not isinstance(it, dict):
            raise _bad(source, f"{where}: a mapping with id, note and {field}")
        keys = set(it)
        if keys != {"id", "note", field}:
            miss, extra = sorted({"id", "note", field} - keys), sorted(keys - {"id", "note", field})
            raise _bad(source, f"{where}: keys must be id, note, {field} (missing {miss}, "
                               f"unknown {extra})")  # fmt: skip
        zid, note = it["id"], it["note"]
        if not isinstance(zid, str) or not zid.strip():
            raise _bad(source, f"{where}: id {zid!r} is not a non-empty string")
        where = f"{kind} {zid!r}"
        if zid in ids:
            raise _bad(source, f"{where}: a duplicate id (ids are unique per file)")
        ids.add(zid)
        if not isinstance(note, str) or not note.strip():
            raise _bad(source, f"{where}: a short note is required")
        pts_raw = it[field]
        if not isinstance(pts_raw, list):
            raise _bad(source, f"{where}: {field} is a list of [x, y] cells")
        pts = [_cell(p, f"{where} point {k}", source, shape) for k, p in enumerate(pts_raw)]
        if kind == "no_enter" and len(pts) > 3 and pts[-1] == pts[0]:
            pts = pts[:-1]  # an explicitly closed polygon: the repeated first point is dropped
        if len(pts) < min_n:
            raise _bad(source, f"{where}: {len(pts)} point(s), at least {min_n}")
        if kind == "no_cross":
            for k in range(1, len(pts)):
                if pts[k] == pts[k - 1]:
                    raise _bad(source, f"{where}: point {k} repeats the one before it")
        else:
            _check_polygon(pts, where, source)
        out.append((zid, note.strip(), pts))
    return out


def parse(data: Any, map_name: str, shape: tuple[int, int] | None = None,
          source: str = "<zones>") -> Zones:  # fmt: skip
    """PURE: Batt's zones from the YAML's data, checked; ZoneError on anything wrong. ``shape``
    (h, w): the map's grid -- every point must lie on it."""
    if not isinstance(data, dict):
        raise _bad(source, "not a mapping (map, reviewed_by, reviewed, no_cross, no_enter)")
    extra = sorted(set(data) - TOP_KEYS)
    if extra:
        raise _bad(source, f"unknown key(s) {extra} (allowed: {sorted(TOP_KEYS)})")
    if data.get("map") != map_name:
        raise _bad(source, f"map {data.get('map')!r} is not {map_name!r} (the file's name)")
    rb = data.get("reviewed_by")
    if not isinstance(rb, str) or not rb.strip():
        raise _bad(source, "no reviewed_by: a zones file names the PERSON who reviewed it (the "
                           "agent never approves zones)")  # fmt: skip
    if set(re.split(r"[^a-z0-9]+", rb.strip().lower())) & AGENT_NAMES:
        raise _bad(source, f"reviewed_by {rb!r}: the agent never approves zones (a person does)")
    rv = data.get("reviewed")
    if isinstance(rv, date):  # YAML reads 2026-10-21 as a date (a datetime is one too)
        reviewed = date(rv.year, rv.month, rv.day).isoformat()
    elif isinstance(rv, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", rv.strip()):
        try:
            reviewed = date.fromisoformat(rv.strip()).isoformat()
        except ValueError:
            raise _bad(source, f"reviewed {rv!r} is not a date") from None
    else:
        raise _bad(source, f"reviewed {rv!r}: the review date, ISO (YYYY-MM-DD), is required")
    ids: set[str] = set()
    nc = _items(data, "no_cross", "points", 2, source, shape, ids)
    ne = _items(data, "no_enter", "polygon", 3, source, shape, ids)
    return Zones(map=map_name, reviewed_by=rb.strip(), reviewed=reviewed,
                 no_cross=tuple(NoCross(i, n, tuple(p)) for i, n, p in nc),
                 no_enter=tuple(NoEnter(i, n, tuple(p)) for i, n, p in ne))  # fmt: skip


def load(map_name: str, root: Path | str = ZONES_DIR, shape: tuple[int, int] | None = None
         ) -> Zones | None:  # fmt: skip
    """Batt's zones for ``map_name`` from ``root``/<map>.yaml; None when there is no file (INERT:
    nothing changes). A file that is there but wrong raises ZoneError (fail closed); so does a
    <map>.yml beside it (it would be silently ignored otherwise)."""
    if not MAP_NAME.fullmatch(map_name):
        raise ZoneError(f"map name {map_name!r} is not a file name")
    root = Path(root)
    if (root / f"{map_name}.yml").exists():
        raise ZoneError(f"{root / (map_name + '.yml')}: zones files end in .yaml (rename it)")
    path = root / f"{map_name}.yaml"
    if not path.exists():
        return None
    raw = path.read_bytes()
    try:
        data = yaml.safe_load(raw.decode("utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise ZoneError(f"{path}: not readable YAML ({exc})") from None
    z = parse(data, map_name, shape, source=str(path))
    return dataclasses.replace(z, path=str(path), sha256=hashlib.sha256(raw).hexdigest())


# --- rasters --------------------------------------------------------------------------------------


def _box_hit(a: Cell, b: Cell, x: int, y: int, closed: bool) -> bool:
    """The segment a-b meets cell (x, y)'s square: CLOSED (a touch counts) or its open interior.
    Separating axes (x, y, the segment's normal) in doubled integer coordinates: exact."""
    ax, ay, bx, by = 2 * a[0], 2 * a[1], 2 * b[0], 2 * b[1]
    x0, x1, y0, y1 = 2 * x - 1, 2 * x + 1, 2 * y - 1, 2 * y + 1
    if closed:
        if max(min(ax, bx), x0) > min(max(ax, bx), x1):
            return False
        if max(min(ay, by), y0) > min(max(ay, by), y1):
            return False
    else:
        if (a[0], a[1]) == (b[0], b[1]):
            return (a[0], a[1]) == (x, y)
        if not (max(min(ax, bx), x0) < min(max(ax, bx), x1)):
            return False
        if not (max(min(ay, by), y0) < min(max(ay, by), y1)):
            return False
    s = [_orient((ax, ay), (bx, by), c) for c in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))]
    if closed:
        return not (all(v > 0 for v in s) or all(v < 0 for v in s))
    return not (all(v >= 0 for v in s) or all(v <= 0 for v in s))


def supercover(a: Cell, b: Cell, closed: bool = True) -> list[Cell]:
    """PURE: the cells the segment a-b (cell centres) meets -- ``closed``: every cell whose
    closed square it touches (the no-cross raster); else every cell whose interior it passes
    through (where a straight walk goes). Row-major order."""
    xa, xb = sorted((a[0], b[0]))
    ya, yb = sorted((a[1], b[1]))
    return [(x, y) for y in range(ya - 1, yb + 2) for x in range(xa - 1, xb + 2)
            if _box_hit(a, b, x, y, closed)]  # fmt: skip


def in_polygon(p: Cell, poly: Sequence[Cell]) -> bool:
    """PURE: the point (a cell centre) inside the polygon or on its boundary (even-odd, exact)."""
    inside = False
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if _on_segment(a, b, p):
            return True
        if (a[1] > p[1]) != (b[1] > p[1]):
            dy = b[1] - a[1]
            lhs, rhs = (p[0] - a[0]) * dy, (p[1] - a[1]) * (b[0] - a[0])
            if (lhs < rhs) if dy > 0 else (lhs > rhs):
                inside = not inside
    return inside


def _poly_mask(poly: Sequence[Cell], shape: tuple[int, int]) -> Any:
    """The cells (x, y) whose centre is inside ``poly`` or on its boundary, (h, w) bool."""
    h, w = shape
    out = np.zeros((h, w), dtype=bool)
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    x0, x1, y0, y1 = max(0, min(xs)), min(w - 1, max(xs)), max(0, min(ys)), min(h - 1, max(ys))
    if x0 > x1 or y0 > y1:
        return out
    gx, gy = np.meshgrid(np.arange(x0, x1 + 1, dtype=np.int64),
                         np.arange(y0, y1 + 1, dtype=np.int64))  # fmt: skip
    inside = np.zeros(gx.shape, dtype=bool)
    on = np.zeros(gx.shape, dtype=bool)
    n = len(poly)
    for i in range(n):
        (ax, ay), (bx, by) = poly[i], poly[(i + 1) % n]
        cr = (bx - ax) * (gy - ay) - (by - ay) * (gx - ax)
        on |= ((cr == 0) & (gx >= min(ax, bx)) & (gx <= max(ax, bx))
               & (gy >= min(ay, by)) & (gy <= max(ay, by)))  # fmt: skip
        dy = by - ay
        if dy:
            lhs, rhs = (gx - ax) * dy, (gy - ay) * (bx - ax)
            inside ^= ((ay > gy) != (by > gy)) & ((lhs < rhs) if dy > 0 else (lhs > rhs))
    out[y0 : y1 + 1, x0 : x1 + 1] = inside | on
    return out


@functools.lru_cache(maxsize=8)
def _masks(zones: Zones, shape: tuple[int, int]) -> tuple[Any, tuple[Any, ...]]:
    """(the no-cross raster, one mask per no-enter polygon) on ``shape``; read-only, cached."""
    h, w = shape
    nc = np.zeros((h, w), dtype=bool)
    for item in zones.no_cross:
        for a, b in item.segments():
            for x, y in supercover(a, b, closed=True):
                if 0 <= x < w and 0 <= y < h:
                    nc[y, x] = True
    polys = tuple(_poly_mask(z.polygon, shape) for z in zones.no_enter)
    for m in (nc, *polys):
        m.flags.writeable = False
    return nc, polys


def _shape(shape: Sequence[int]) -> tuple[int, int]:
    return (int(shape[0]), int(shape[1]))


def no_cross_mask(zones: Zones, shape: Sequence[int]) -> Any:
    """PURE: the no-cross lines' CLOSED supercover on an (h, w) grid (a new array)."""
    return _masks(zones, _shape(shape))[0].copy()


def no_enter_mask(zones: Zones, shape: Sequence[int]) -> Any:
    """PURE: the cells whose centre is inside or on the boundary of any no-enter polygon."""
    out = np.zeros(_shape(shape), dtype=bool)
    for m in _masks(zones, _shape(shape))[1]:
        out |= m
    return out


def apply(ok: Any, area: Any, zones: Zones | None) -> tuple[Any, Any]:
    """PURE: (ok_z, area_z) -- ``ok`` minus the no-cross raster (a GM inside a no-enter area
    still walks out over its cells), ``area`` minus no-enter minus no-cross. ``zones`` None: the
    very same two objects back, unchanged (INERT)."""
    if zones is None:
        return ok, area
    shape = np.shape(ok)
    nc = no_cross_mask(zones, shape)
    return (np.asarray(ok, dtype=bool) & ~nc,
            np.asarray(area, dtype=bool) & ~no_enter_mask(zones, shape) & ~nc)  # fmt: skip


def route_grid(grid: Any, zones: Zones | None) -> Any:
    """PURE: ``grid`` minus no-enter minus no-cross -- what a planned route may use (an approach,
    an escape, the stall breaker); None: the same object back."""
    if zones is None:
        return grid
    shape = np.shape(grid)
    return np.asarray(grid, dtype=bool) & ~no_enter_mask(zones, shape) & ~no_cross_mask(
        zones, shape)  # fmt: skip


# --- checks ---------------------------------------------------------------------------------------


def polys_at(zones: Zones, c: Cell) -> frozenset[int]:
    """PURE: the indices of the no-enter polygons whose area holds cell ``c`` (its centre inside
    or on the boundary)."""
    out = set()
    for i, z in enumerate(zones.no_enter):
        xs, ys = [p[0] for p in z.polygon], [p[1] for p in z.polygon]
        if (min(xs) <= c[0] <= max(xs) and min(ys) <= c[1] <= max(ys)
                and in_polygon(c, z.polygon)):  # fmt: skip
            out.add(i)
    return frozenset(out)


def in_no_enter(zones: Zones | None, c: Cell) -> bool:
    return zones is not None and bool(polys_at(zones, c))


def _segs(zones: Zones) -> list[tuple[Cell, Cell]]:
    return [s for item in zones.no_cross for s in item.segments()]


def step_crosses(a: Cell, b: Cell, s: Cell, t: Cell) -> bool:
    """PURE: the step a -> b meets the no-cross segment s-t anywhere but at ``a`` alone (a touch
    and a collinear run count; leaving a line one stands on does not)."""
    if not segments_meet(a, b, s, t):
        return False
    if not _on_segment(s, t, a):
        return True
    if _orient(s, t, b) != 0:
        return False  # off the line's direction: they share only a
    dx, dy = t[0] - s[0], t[1] - s[1]
    pa = (a[0] - s[0]) * dx + (a[1] - s[1]) * dy
    pb = (b[0] - s[0]) * dx + (b[1] - s[1]) * dy
    return min(max(pa, pb), dx * dx + dy * dy) > max(min(pa, pb), 0)  # a run along it


def path_violates(path: Sequence[Sequence[int]], zones: Zones | None) -> str | None:
    """PURE: why a path of cells (each step centre to centre) breaks the zones -- "no_cross" (a
    step meets a no-cross line, ``step_crosses``), "no_enter" (a cell inside a no-enter polygon
    its START is not in: a path from inside walking out does not enter) -- the first one along
    the path; None when it keeps them (or no zones)."""
    if zones is None or not path:
        return None
    cells = [(int(c[0]), int(c[1])) for c in path]
    home = polys_at(zones, cells[0])
    segs = _segs(zones)
    for a, b in zip(cells, cells[1:], strict=False):
        if any(step_crosses(a, b, s, t) for s, t in segs):
            return "no_cross"
        if polys_at(zones, b) - home:
            return "no_enter"
    return None


def segment_violates(a: Cell, b: Cell, zones: Zones | None) -> str | None:
    """PURE: the STRAIGHT walk a -> b: "no_cross" (it meets a line, ``step_crosses``), "no_enter"
    (it passes through the interior of a cell of a no-enter polygon ``a`` is not in); None."""
    if zones is None:
        return None
    if any(step_crosses(a, b, s, t) for s, t in _segs(zones)):
        return "no_cross"
    home = polys_at(zones, a)
    if zones.no_enter and any(polys_at(zones, c) - home for c in supercover(a, b, closed=False)):
        return "no_enter"
    return None


def client_route(free: Any, frm: Cell, to: Cell, max_nodes: int = ROUTE_MAX_NODES
                 ) -> list[Cell] | None:  # fmt: skip
    """PURE: the proxy for the CLIENT's own path of a click (it paths on its own map, not on our
    zoned grids): hunt_core.astar on the ZONE-FREE walkable grid ``free``, both ends allowed;
    None when off the grid, unreachable or past ``max_nodes``."""
    g = np.asarray(free, dtype=bool)
    h, w = g.shape
    if not all(0 <= c[0] < w and 0 <= c[1] < h for c in (frm, to)):
        return None
    if not (g[frm[1], frm[0]] and g[to[1], to[0]]):
        g = g.copy()
        g[frm[1], frm[0]] = g[to[1], to[0]] = True
    return hc.astar(g, frm, to, max_nodes=max_nodes)


def walk_why(zones: Zones | None, free: Any, frm: Cell, to: Cell, exit_ok: bool = False,
             max_nodes: int = ROUTE_MAX_NODES) -> str | None:  # fmt: skip
    """PURE: why a click that makes the client walk ``frm`` -> ``to`` (a walk click, an attack
    click's walk-in, a loot click) breaks the zones; None when it does not, or no zones (INERT).
    - "dest_no_enter": ``to`` inside a no-enter polygon -- with ``exit_ok`` (walk clicks) allowed
      only inside polygons ``frm`` is in already (the way out);
    - "straight_no_cross" / "straight_no_enter": the straight segment (``segment_violates``);
    - "route_no_cross" / "route_no_enter": the client's path proxy (``client_route`` on the
      zone-free grid ``free``; skipped when ``free`` is None or no proxy path exists)."""
    if zones is None:
        return None
    frm, to = (int(frm[0]), int(frm[1])), (int(to[0]), int(to[1]))
    dest = polys_at(zones, to)
    if dest and (not exit_ok or dest - polys_at(zones, frm)):
        return "dest_no_enter"
    why = segment_violates(frm, to, zones)
    if why is not None:
        return f"straight_{why}"
    if free is not None:
        p = client_route(free, frm, to, max_nodes)
        why = None if p is None else path_violates(p, zones)
        if why is not None:
            return f"route_{why}"
    return None


def exit_path(ok_z: Any, area_z: Any, here: Cell, zones: Zones | None = None,
              max_nodes: int = 200_000) -> list[Cell] | None:  # fmt: skip
    """PURE: the SHORTEST way (octile costs; 8-connected, a diagonal step needs both side cells:
    hunt_core.astar's rules) from ``here`` to the nearest cell of ``area_z``, over ``ok_z`` (the
    stand grid minus the no-cross raster: never across a line) -- ``here`` itself always allowed.
    With ``zones`` the no-cross raster is removed again and the cells of every no-enter polygon
    ``here`` is NOT in are closed: the path leaves its own area and enters no other. [here] when
    ``here`` is in ``area_z``; None when no area cell is reachable."""
    g = np.asarray(ok_z, dtype=bool)
    a = np.asarray(area_z, dtype=bool)
    h, w = g.shape
    here = (int(here[0]), int(here[1]))
    if not (0 <= here[0] < w and 0 <= here[1] < h):
        return None
    if zones is not None:
        nc, polys = _masks(zones, (h, w))
        home = polys_at(zones, here)
        g = g & ~nc
        for i, m in enumerate(polys):
            if i not in home:
                g = g & ~m
    g = g.copy()
    g[here[1], here[0]] = True
    a = a & g
    if a[here[1], here[0]]:
        return [here]
    cost: dict[Cell, float] = {here: 0.0}
    came: dict[Cell, Cell] = {}
    heap: list[tuple[float, Cell]] = [(0.0, here)]
    n = 0
    while heap:
        d, c = heapq.heappop(heap)
        if d > cost.get(c, math.inf):
            continue
        if a[c[1], c[0]]:
            out = [c]
            while out[-1] in came:
                out.append(came[out[-1]])
            return out[::-1]
        n += 1
        if n > max_nodes:
            return None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if not dx and not dy:
                    continue
                nx, ny = c[0] + dx, c[1] + dy
                if not (0 <= nx < w and 0 <= ny < h) or not g[ny, nx]:
                    continue
                if dx and dy and not (g[c[1], nx] and g[ny, c[0]]):
                    continue
                nd = d + hc.STEP_MS[bool(dx and dy)]
                if nd < cost.get((nx, ny), math.inf):
                    cost[(nx, ny)] = nd
                    came[(nx, ny)] = c
                    heapq.heappush(heap, (nd, (nx, ny)))
    return None


def summary(zones: Zones, shape: Sequence[int], ok: Any = None, area: Any = None
            ) -> dict[str, Any]:  # fmt: skip
    """The run-start record: the file, its review, the items and the cells they take."""
    nc, ne = no_cross_mask(zones, shape), no_enter_mask(zones, shape)
    out: dict[str, Any] = {
        "file": zones.path, "sha256": zones.sha256, "reviewed_by": zones.reviewed_by,
        "reviewed": zones.reviewed, "no_cross": [z.id for z in zones.no_cross],
        "no_enter": [z.id for z in zones.no_enter], "no_cross_cells": int(nc.sum()),
        "no_enter_cells": int(ne.sum()),
    }  # fmt: skip
    if ok is not None:
        out["ok_removed"] = int((np.asarray(ok, dtype=bool) & nc).sum())
    if area is not None:
        out["area_removed"] = int((np.asarray(area, dtype=bool) & (nc | ne)).sum())
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    ck = sub.add_parser("check", help="validate config/map_zones/<map>.yaml on the map's grid")
    ck.add_argument("map")
    ck.add_argument("--root", default=str(ZONES_DIR))
    a = ap.parse_args()
    try:
        from poring_dataset import walkable as wk

        both = np.asarray(wk.load_both(a.map)[1], dtype=bool)
    except Exception as exc:  # noqa: BLE001 -- refused: the map's bounds are part of the check
        print(json.dumps({"ok": False, "error": f"no walkable grid for {a.map}: {exc}"}))
        return 2
    try:
        z = load(a.map, a.root, both.shape)
    except ZoneError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    if z is None:
        print(json.dumps({"ok": True, "file": None, "note": "no zones file: INERT"}))
        return 0
    taken: dict[str, int] = {}
    for it in z.no_cross:
        cs = {c for a_, b_ in it.segments() for c in supercover(a_, b_)}
        taken[it.id] = sum(int(both[y, x]) for x, y in cs
                           if 0 <= x < both.shape[1] and 0 <= y < both.shape[0])  # fmt: skip
    for ne in z.no_enter:
        taken[ne.id] = int((_poly_mask(ne.polygon, both.shape) & both).sum())
    print(json.dumps({"ok": True, **summary(z, both.shape, both), "walkable_taken": taken}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
