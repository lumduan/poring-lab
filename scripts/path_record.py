#!/usr/bin/env python3
"""RECORDED PATHS -- the pure core of "record a path by walking" (docs/planning/
waypoints-npc-recording.md section 3 items 1-3, Amendment 1 b-d, Amendment 3; Batt 2026-11-20/21:
the path recorder and the /maps waypoint editor built OFFLINE, in parallel). Everything here is
PURE: no live read, no input, no file written, no lab service needed. The live recorder (selfpos
reads, /where on a minimap change), the editor's UI and the walk_path block build on it.

A PATH (``WalkPath``): a NAME a person typed and its LEGS in walking order, one per map:
- a leg: the map's name, its WAYPOINTS in walking order, and how the map is LEFT (``Exit``);
- a waypoint: a cell (x, y) and its ARRIVAL RADIUS in cells (Chebyshev, map_routes.reached's
  measure; Amendment 1 d: a waypoint is a checkpoint with a radius), plus ``mark`` when the person
  marked it while recording;
- an exit, in the flow IR's own words (poring_flow.ir.Exit, the /maps graph's exits):
  ``walk_exit`` (a warp CELL on the leg's map, walked onto), ``npc_warp`` (the NAME of a recorded
  NPC talk: talk_npc("<name>")), ``item_warp`` (a Butterfly Wing; ``proc``: the flow FUNCTION it
  runs, as the IR's Exit.proc -- optional: absent = not chosen yet, the recorder cannot know it)
  and ``end`` (the path's end: its last leg, and only that one).
Names (the path's, a talk's) are a person's text in any script: checked (``name_problem``), stored
as data, never turned into code or a file name.

COORDINATES: map cells, x east, y NORTH, as map_routes / map_zones (the minimap readout's, /where's
and the server's numbers); a grid is indexed [y, x] with that same y, no flip anywhere.

THE FILE (JSON, versioned; ``to_json`` / ``from_json``, ``dumps`` / ``loads``)::

    {"format": "poring-lab-path", "v": 1, "name": "to kafra",
     "legs": [{"map": "prontera",
               "points": [{"x": 156, "y": 60, "r": 2}, {"x": 156, "y": 70, "r": 2, "mark": true}],
               "exit": {"kind": "walk_exit", "cell": [156, 72]}},
              {"map": "prt_in",
               "points": [{"x": 20, "y": 30, "r": 2}],
               "exit": {"kind": "end"}}]}

Every key is required except ``mark`` (absent = false) and the exit's kind-specific ones:
``cell`` for walk_exit only, ``talk`` for npc_warp only, ``proc`` (optional) for item_warp only.
Unknown keys, another format or another version are refused (fail closed).

THINNING (``thin``; Amendment 1 b: record raw reads, then thin them): from the raw reads
(t, map, x, y, confirmed) to waypoints.
- Unconfirmed reads are dropped (their content is not looked at). Confirmed reads must be in time
  order; a run of reads on one map is a LEG, and a MAP CHANGE ends it and starts the next.
- Within a leg, consecutive reads of the same cell are one track point (standing still adds
  nothing). Kept: the leg's first and last cells (the map changes, the path's start and end),
  every MARK (a time: the confirmed read nearest to it, the earlier on a tie), every TURN (below),
  and a point each time she has moved ``every_cells`` (Chebyshev) from the last kept one.
- A TURN: at a track point, the heading in (from the latest earlier point at least ``turn_span``
  cells away) and the heading out (to the first later point at least ``turn_span`` away) differ by
  more than ``turn_deg``; of consecutive such points, the sharpest (the middle one of a tie: a
  turn-back's tip).
- Never two kept points closer than ``min_step`` (Chebyshev), except at a map change, the path's
  ends, or a mark: a turn or distance point that close to the last kept point, or to the next
  protected one, is not kept. A mark or a leg's end on the last kept point's cell is merged into it.
- How each leg was left: a LEAVE event (t, Exit) the recorder saw (an NPC talk, a wing) belongs
  to the leg whose time it falls in (from its first read up to the next leg's first read; before
  the first read: the first leg); the latest one in a leg wins. A leg that ends in a map change
  with no leave event gets a walk_exit at its last read cell -- an ASSUMPTION the result's
  ``notes`` say, for the person to check. The last leg's exit is ``end``.
- Every threshold is passed in (``ThinSettings``, our values as its defaults: Batt 2026-11-13,
  everything a user would set is a setting).

THE PROOF (``prove`` / ``prove_leg``; section 3 item 2): each leg on its map's walk grid, the way
``map_routes.prove`` proves a route's legs, with its own functions: the route grid
(``map_routes.route_grid``: the walkable cells minus every zone and what they seal off), each
waypoint open (``map_routes.closed_why``, then "sealed off by the zones"), each SEGMENT (two
consecutive waypoints, and a walk_exit's last waypoint -> its warp cell) connected there
(``map_routes.leg_path``: hunt_core.astar, the runner's own router; its cost by
``map_routes.path_cost``). Every point and segment gets a status for the editor to draw (ok /
closed / broken / unproven: no grid for that map).

EDITS (section 3 item 2: drag, insert, delete a point; also a radius, an exit, the name): PURE
functions that return a NEW path, re-validated (``PathError`` when the result is not a valid path).

WALKING (Amendment 1 d, section 3 item 3): ``ahead`` -- the waypoint to walk to on a leg, by
map_routes' own rules on the leg as an open route (``leg_route``): with no history (the walk's
start, a new map) ``map_routes.entry_index`` (the nearest waypoint, or the one past it); after an
interruption, from the last waypoint reached, ``map_routes.resume_index`` (the next one AHEAD,
never a passed one). The candidate's OWN radius is the reach tolerance (map_routes uses the
tolerance only on the candidate). Another map than the leg's stops with the words "she is on
<map>, the path expects <map>" (``WrongMap``), never a guess.
"""

from __future__ import annotations

import bisect
import dataclasses
import json
import math
import re
import sys
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path as FsPath
from typing import Any, NamedTuple

import numpy as np

sys.path.insert(0, str(FsPath(__file__).resolve().parent))
import map_routes as mr  # noqa: E402
import map_zones as mz  # noqa: E402

Cell = tuple[int, int]

FORMAT = "poring-lab-path"
VERSION = 1
NAME_MAX = 60  # characters, any script
LEGS_MAX = 32
POINTS_MAX = 1000  # per leg (a sanity bound on the file and the editor, not a setting)
CELL_MAX = 1024  # a coordinate is 0 .. CELL_MAX - 1 (the proof checks the map's own size)
RADIUS_MAX = 15  # cells
DEFAULT_RADIUS = mr.REACH_TOL  # the runner's reach tolerance (2 cells)
LOADS_MAX_BYTES = 2_000_000
TIE_DEG = 1e-9  # two heading changes this close are equally sharp (float rounding, not a setting)
EXIT_KINDS = ("walk_exit", "npc_warp", "item_warp", "end")
PROC_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,47}")  # poring_flow.ir.NAME (a function's name)
TOP_KEYS = frozenset({"format", "v", "name", "legs"})
LEG_KEYS = frozenset({"map", "points", "exit"})
POINT_KEYS = frozenset({"x", "y", "r", "mark"})
EXIT_KEYS = {"walk_exit": {"cell"}, "npc_warp": {"talk"}, "item_warp": {"proc"}, "end": set()}


class PathError(ValueError):
    """A path (or an edit, a recording, a file) that is not valid: refused, nothing changes."""


class WrongMap(PathError):
    """She is not on the leg's map: the walk stops with these words (never a guess)."""


# --- the model ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Waypoint:
    x: int
    y: int
    radius: int = DEFAULT_RADIUS  # the arrival radius, cells (Chebyshev)
    mark: bool = False  # the person marked it while recording

    @property
    def cell(self) -> Cell:
        return (self.x, self.y)


@dataclass(frozen=True)
class Exit:
    kind: str  # EXIT_KINDS
    cell: Cell | None = None  # walk_exit: the warp cell walked onto (on the leg's map)
    talk: str | None = None  # npc_warp: the recorded NPC talk's name
    proc: str | None = None  # item_warp: the function it runs (None: not chosen)


END = Exit("end")


@dataclass(frozen=True)
class Leg:
    map: str
    waypoints: tuple[Waypoint, ...]  # the walking order
    exit: Exit = END

    def cells(self) -> tuple[Cell, ...]:
        return tuple(w.cell for w in self.waypoints)


@dataclass(frozen=True)
class WalkPath:
    name: str
    legs: tuple[Leg, ...]  # the walking order, one per map crossed


# --- the checks -----------------------------------------------------------------------------------


def _int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def clean_name(text: str) -> str:
    """A typed name as it is stored: its ends' spaces removed, Unicode NFC (two spellings of the
    same letters are one name). Nothing else is changed; ``name_problem`` still decides."""
    return unicodedata.normalize("NFC", text).strip()


def name_problem(name: Any, what: str = "the name") -> str | None:
    """PURE: why ``name`` is not a usable name (None: it is). Any script; at most NAME_MAX
    characters; no control or format character; stored clean (``clean_name``)."""
    if not isinstance(name, str):
        return f"{what} is not text"
    if not name.strip():
        return f"{what} is empty"
    if name != name.strip():
        return f"{what} has spaces at its ends"
    if unicodedata.normalize("NFC", name) != name:
        return f"{what} is not stored in Unicode NFC"
    if len(name) > NAME_MAX:
        return f"{what} is longer than {NAME_MAX} characters"
    if any(unicodedata.category(ch).startswith("C") for ch in name):
        return f"{what} holds a control or format character"
    return None


def _cell_problem(c: Any, what: str) -> str | None:
    if not isinstance(c, tuple) or len(c) != 2 or not all(_int(v) for v in c):
        return f"{what} is not a cell (x, y) of two whole numbers"
    if not all(0 <= v < CELL_MAX for v in c):
        return f"{what} {list(c)} is outside 0 .. {CELL_MAX - 1}"
    return None


def _point_problem(w: Any, what: str) -> str | None:
    if not isinstance(w, Waypoint):
        return f"{what} is not a waypoint"
    why = _cell_problem((w.x, w.y), what)
    if why is not None:
        return why
    if not _int(w.radius) or not 0 <= w.radius <= RADIUS_MAX:
        return f"{what}: its radius {w.radius!r} is not a whole number 0 .. {RADIUS_MAX}"
    if not isinstance(w.mark, bool):
        return f"{what}: mark is not true or false"
    return None


def exit_problem(e: Any, what: str = "the exit") -> str | None:
    """PURE: why ``e`` is not a valid exit (None: it is). Only its own kind's field is given."""
    if not isinstance(e, Exit):
        return f"{what} is not an exit"
    if e.kind not in EXIT_KINDS:
        return f"{what}: kind {e.kind!r} is not one of {', '.join(EXIT_KINDS)}"
    given = {"cell": e.cell is not None, "talk": e.talk is not None, "proc": e.proc is not None}
    extra = sorted(k for k, v in given.items() if v and k not in EXIT_KEYS[e.kind])
    if extra:
        return f"{what}: kind {e.kind} takes no {', '.join(extra)}"
    if e.kind == "walk_exit":
        return _cell_problem(e.cell, f"{what}'s warp cell")
    if e.kind == "npc_warp":
        return name_problem(e.talk, f"{what}'s talk name")
    if e.proc is not None and (not isinstance(e.proc, str) or not PROC_NAME.fullmatch(e.proc)):
        return f"{what}: proc {e.proc!r} is not a function name (a letter, then letters, digits, _)"
    return None


def problem_of(path: Any) -> str | None:
    """PURE: why ``path`` is not a valid path (None: it is). Never raises."""
    if not isinstance(path, WalkPath):
        return "not a path"
    why = name_problem(path.name, "the path's name")
    if why is not None:
        return why
    if not isinstance(path.legs, tuple) or not path.legs:
        return "a path has at least one leg"
    if len(path.legs) > LEGS_MAX:
        return f"{len(path.legs)} legs: a path has at most {LEGS_MAX}"
    last = len(path.legs) - 1
    for k, leg in enumerate(path.legs):
        if not isinstance(leg, Leg):
            return f"leg {k} is not a leg"
        if not isinstance(leg.map, str) or not mz.MAP_NAME.fullmatch(leg.map):
            return f"leg {k}: map {leg.map!r} is not a map name (1-40 of A-Z a-z 0-9 _ @ -)"
        where = f"leg {k} ({leg.map})"
        wps = leg.waypoints
        if not isinstance(wps, tuple) or not wps:
            return f"{where}: a leg has at least one point"
        if len(wps) > POINTS_MAX:
            return f"{where}: {len(wps)} points, a leg has at most {POINTS_MAX}"
        for i, w in enumerate(wps):
            why = _point_problem(w, f"{where} point {i}")
            if why is not None:
                return why
            if i and w.cell == wps[i - 1].cell:
                return f"{where} point {i} {list(w.cell)} repeats the one before it"
        why = exit_problem(leg.exit, f"{where}'s exit")
        if why is not None:
            return why
        if k == last and leg.exit.kind != "end":
            return f"{where} is the last leg: its exit is end (a {leg.exit.kind} needs a next leg)"
        if k != last and leg.exit.kind == "end":
            return f"{where}: only the last leg ends the path (legs follow it)"
    return None


def checked(path: WalkPath) -> WalkPath:
    """``path`` itself when it is valid; PathError (``problem_of``'s words) when it is not."""
    why = problem_of(path)
    if why is not None:
        raise PathError(why)
    return path


# --- the file -------------------------------------------------------------------------------------


def _point_json(w: Waypoint) -> dict[str, Any]:
    return {"x": w.x, "y": w.y, "r": w.radius, **({"mark": True} if w.mark else {})}


def _exit_json(e: Exit) -> dict[str, Any]:
    out: dict[str, Any] = {"kind": e.kind}
    if e.cell is not None:
        out["cell"] = list(e.cell)
    if e.talk is not None:
        out["talk"] = e.talk
    if e.proc is not None:
        out["proc"] = e.proc
    return out


def to_json(path: WalkPath) -> dict[str, Any]:
    """The path as its JSON document (a valid path only: PathError otherwise)."""
    checked(path)
    return {"format": FORMAT, "v": VERSION, "name": path.name,
            "legs": [{"map": lg.map, "points": [_point_json(w) for w in lg.waypoints],
                      "exit": _exit_json(lg.exit)} for lg in path.legs]}  # fmt: skip


def _keys(d: Any, need: frozenset[str] | set[str], allowed: frozenset[str] | set[str], what: str
          ) -> dict[str, Any]:  # fmt: skip
    if not isinstance(d, dict):
        raise PathError(f"{what} is not a JSON object")
    miss, extra = sorted(need - set(d)), sorted(set(d) - allowed)
    if miss or extra:
        raise PathError(f"{what}: missing {miss}, unknown {extra}")
    return d


def _cell_of(v: Any, what: str) -> Cell:
    if not isinstance(v, list) or len(v) != 2:
        raise PathError(f"{what} is not a cell [x, y]")
    return (v[0], v[1])


def _exit_of(d: Any, what: str) -> Exit:
    d = _keys(d, {"kind"}, {"kind", "cell", "talk", "proc"}, what)
    kind = d["kind"]
    if kind not in EXIT_KEYS:
        raise PathError(f"{what}: kind {kind!r} is not one of {', '.join(EXIT_KINDS)}")
    extra = sorted(set(d) - {"kind"} - EXIT_KEYS[kind])
    if extra:
        raise PathError(f"{what}: kind {kind} takes no {', '.join(extra)}")
    cell = _cell_of(d["cell"], f"{what}'s warp cell") if "cell" in d else None
    return Exit(kind, cell=cell, talk=d.get("talk"), proc=d.get("proc"))


def from_json(data: Any) -> WalkPath:
    """PURE: the path from its JSON document, checked (``problem_of``); PathError on anything
    wrong: another format or version, a missing or unknown key, an invalid path."""
    d = _keys(data, TOP_KEYS, TOP_KEYS, "the path")
    if d["format"] != FORMAT:
        raise PathError(f"format {d['format']!r} is not {FORMAT!r}")
    if not _int(d["v"]) or d["v"] != VERSION:
        raise PathError(f"version {d['v']!r} (this install reads {VERSION})")
    raw = d["legs"]
    if not isinstance(raw, list):
        raise PathError("legs is not a list")
    if len(raw) > LEGS_MAX:
        raise PathError(f"{len(raw)} legs: a path has at most {LEGS_MAX}")
    legs = []
    for k, rl in enumerate(raw):
        lg = _keys(rl, LEG_KEYS, LEG_KEYS, f"leg {k}")
        pts = lg["points"]
        if not isinstance(pts, list):
            raise PathError(f"leg {k}: points is not a list")
        if len(pts) > POINTS_MAX:
            raise PathError(f"leg {k}: {len(pts)} points, a leg has at most {POINTS_MAX}")
        wps = []
        for i, rp in enumerate(pts):
            p = _keys(rp, {"x", "y", "r"}, POINT_KEYS, f"leg {k} point {i}")
            wps.append(Waypoint(p["x"], p["y"], p["r"], p.get("mark", False)))
        legs.append(Leg(lg["map"], tuple(wps), _exit_of(lg["exit"], f"leg {k}'s exit")))
    return checked(WalkPath(d["name"], tuple(legs)))


def dumps(path: WalkPath) -> str:
    """The path's canonical JSON text (sorted keys, no insignificant whitespace, UTF-8 as is):
    what a store writes."""
    return json.dumps(to_json(path), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def loads(text: str | bytes) -> WalkPath:
    """The path from its JSON text (at most LOADS_MAX_BYTES); PathError on anything wrong."""
    if len(text) > LOADS_MAX_BYTES:
        raise PathError(f"the text is larger than {LOADS_MAX_BYTES} bytes")
    try:
        data = json.loads(text)
    except (ValueError, UnicodeDecodeError) as exc:
        raise PathError(f"not readable JSON ({exc})") from None
    return from_json(data)


# --- thinning (Amendment 1 b) ---------------------------------------------------------------------


class Read(NamedTuple):
    """One raw read of her cell: its time (s, any one clock), the map, x, y, and whether the read
    was CONFIRMED (selfpos' re-read rule). Unconfirmed reads may carry None."""

    t: float
    map: str | None
    x: int | None
    y: int | None
    confirmed: bool


@dataclass(frozen=True)
class ThinSettings:
    every_cells: int = 10  # keep a point each time she has moved this far (Chebyshev)
    min_step: int = 3  # never two kept points closer, except at a map change, the ends, a mark
    turn_deg: float = 40.0  # a turn: the heading changes by MORE than this (180: turns off)
    turn_span: int = 3  # the headings are measured over at least this many cells
    radius: int = DEFAULT_RADIUS  # each kept waypoint's arrival radius


DEFAULTS = ThinSettings()


def settings_problem(s: Any) -> str | None:
    """PURE: why ``s`` is not usable thinning settings (None: they are)."""
    if not isinstance(s, ThinSettings):
        return "not thinning settings"
    for name in ("every_cells", "min_step", "turn_span"):
        v = getattr(s, name)
        if not _int(v) or v < 1:
            return f"{name} {v!r} is not a whole number of at least 1"
    d = s.turn_deg
    if not isinstance(d, int | float) or isinstance(d, bool) or not 0 < d <= 180:
        return f"turn_deg {d!r} is not a number of degrees above 0, at most 180"
    if not _int(s.radius) or not 0 <= s.radius <= RADIUS_MAX:
        return f"radius {s.radius!r} is not a whole number 0 .. {RADIUS_MAX}"
    return None


@dataclass(frozen=True)
class Thinned:
    path: WalkPath
    notes: tuple[str, ...]  # what the person should check (an assumed exit, an unused event)
    dropped: int  # unconfirmed reads dropped


def _time(t: Any, what: str) -> float:
    if not isinstance(t, int | float) or isinstance(t, bool) or not math.isfinite(t):
        raise PathError(f"{what}: its time {t!r} is not a finite number")
    return float(t)


def _confirmed(reads: Iterable[Sequence[Any]]) -> tuple[list[tuple[float, str, Cell]], int]:
    """The confirmed reads as (t, map, cell), checked; and how many unconfirmed were dropped."""
    out: list[tuple[float, str, Cell]] = []
    n = 0
    for k, raw in enumerate(reads):
        n += 1
        if not isinstance(raw, Sequence) or isinstance(raw, str) or len(raw) != 5:
            raise PathError(f"read {k} is not (t, map, x, y, confirmed)")
        r = Read(*raw)
        if not isinstance(r.confirmed, bool):
            raise PathError(f"read {k}: confirmed is not true or false")
        if not r.confirmed:
            continue
        t = _time(r.t, f"read {k}")
        if not isinstance(r.map, str) or not mz.MAP_NAME.fullmatch(r.map):
            raise PathError(f"read {k}: map {r.map!r} is not a map name")
        x, y = r.x, r.y
        why = _cell_problem((x, y), f"read {k}'s cell")
        if why is not None or not isinstance(x, int) or not isinstance(y, int):
            raise PathError(why or f"read {k}'s cell is not two whole numbers")
        if out and t < out[-1][0]:
            raise PathError(f"read {k}: the confirmed reads are not in time order")
        out.append((t, r.map, (x, y)))
    return out, n - len(out)


def _nearest(times: Sequence[float], t: float) -> int:
    """The index of the time nearest ``t`` (the earlier on a tie); ``times`` sorted."""
    i = bisect.bisect_left(times, t)
    if i == 0:
        return 0
    if i == len(times):
        return i - 1
    return i - 1 if t - times[i - 1] <= times[i] - t else i


def _angle(u: Cell, v: Cell) -> float:
    """The angle between two non-zero vectors, degrees 0 .. 180."""
    dot = u[0] * v[0] + u[1] * v[1]
    c = dot / (math.hypot(*u) * math.hypot(*v))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def turn_angles(track: Sequence[Cell], span: int) -> list[float]:
    """PURE: each track point's heading change, degrees: in from the latest earlier point at least
    ``span`` cells away (Chebyshev), out to the first later one; 0 where either is missing."""
    n = len(track)
    out = [0.0] * n
    for i in range(1, n - 1):
        c = track[i]
        b = next((k for k in range(i - 1, -1, -1) if mr.cheb(track[k], c) >= span), None)
        f = next((k for k in range(i + 1, n) if mr.cheb(c, track[k]) >= span), None)
        if b is None or f is None:
            continue
        p, q = track[b], track[f]
        out[i] = _angle((c[0] - p[0], c[1] - p[1]), (q[0] - c[0], q[1] - c[1]))
    return out


def turn_points(track: Sequence[Cell], deg: float, span: int) -> list[int]:
    """PURE: the TURNS of a track: of each run of consecutive points turning by more than ``deg``
    (``turn_angles``), the sharpest; of several equally sharp, the middle one (a turn-back's
    points all read 180 degrees around its tip, and the tip is their middle)."""
    ang = turn_angles(track, span)
    out: list[int] = []
    i = 0
    while i < len(track):
        if ang[i] <= deg:
            i += 1
            continue
        j = i
        while j + 1 < len(track) and ang[j + 1] > deg:
            j += 1
        best = max(ang[i : j + 1])
        ties = [k for k in range(i, j + 1) if ang[k] >= best - TIE_DEG]
        out.append(ties[(len(ties) - 1) // 2])
        i = j + 1
    return out


def thin_track(track: Sequence[Cell], marked: Iterable[int], s: ThinSettings = DEFAULTS
               ) -> list[tuple[int, bool]]:  # fmt: skip
    """PURE: one leg's kept points as (track index, mark), by the rules of the module docstring.
    ``track``: the leg's cells with no two consecutive ones equal; ``marked``: marked indices."""
    n = len(track)
    marks = set(marked)
    if any(not 0 <= i < n for i in marks):
        raise PathError("a mark is outside the track")
    for i in range(1, n):
        if track[i] == track[i - 1]:
            raise PathError(f"track point {i} repeats the one before it")
    turns = set(turn_points(track, s.turn_deg, s.turn_span))
    protected = sorted({0, n - 1} | marks)
    out: list[list[Any]] = [[0, 0 in marks]]
    pi = 0
    for i in range(1, n):
        c, last = track[i], track[out[-1][0]]
        if i in marks or i == n - 1:
            if c == last:  # back on the last kept cell: that point takes this one's role
                out[-1][1] = out[-1][1] or i in marks
            else:
                out.append([i, i in marks])
            continue
        while protected[pi] <= i:
            pi += 1
        d = mr.cheb(c, last)
        if d < s.min_step or mr.cheb(c, track[protected[pi]]) < s.min_step:
            continue
        if i in turns or d >= s.every_cells:
            out.append([i, False])
    return [(int(i), bool(m)) for i, m in out]


def thin(reads: Iterable[Sequence[Any]], name: str, *, marks: Iterable[float] = (),
         leaves: Iterable[tuple[float, Exit]] = (), settings: ThinSettings = DEFAULTS
         ) -> Thinned:  # fmt: skip
    """PURE: the raw reads of a recording -> a PATH (the module docstring's THINNING). ``reads``:
    (t, map, x, y, confirmed) in time order; ``name``: the path's name (``clean_name`` applied);
    ``marks``: the times the person marked a point; ``leaves``: (t, Exit) events the recorder saw
    (an NPC talk, a wing); ``settings``: every threshold. PathError on bad input."""
    why = settings_problem(settings)
    if why is not None:
        raise PathError(f"settings: {why}")
    if not isinstance(name, str):
        raise PathError("the path's name is not text")
    conf, dropped = _confirmed(reads)
    if not conf:
        raise PathError("no confirmed read: there is nothing to keep")
    times = [r[0] for r in conf]
    notes: list[str] = []
    starts = [0] + [i for i in range(1, len(conf)) if conf[i][1] != conf[i - 1][1]]
    bounds = list(zip(starts, [*starts[1:], len(conf)], strict=True))
    marked = {_nearest(times, _time(m, f"mark {k}")) for k, m in enumerate(marks)}
    chosen: dict[int, tuple[float, Exit]] = {}
    for k, ev in enumerate(leaves):
        if not isinstance(ev, Sequence) or len(ev) != 2:
            raise PathError(f"leave {k} is not (t, exit)")
        t, ex = _time(ev[0], f"leave {k}"), ev[1]
        why = exit_problem(ex, f"leave {k}")
        if why is not None:
            raise PathError(why)
        if ex.kind == "end":
            raise PathError(f"leave {k}: end is not a way to leave a map")
        leg = max(0, bisect.bisect_right([times[a] for a in starts], t) - 1)
        if leg == len(starts) - 1:
            notes.append(f"a leave by {ex.kind} at t={t:g} came after the last map change: the "
                         "path ends with its last leg, so it is not used")  # fmt: skip
            continue
        old = chosen.get(leg)
        if old is not None:
            lost = old if t >= old[0] else (t, ex)
            notes.append(f"leg {leg}: a leave by {lost[1].kind} at t={lost[0]:g} is not used (a "
                         "later one in the same leg is)")  # fmt: skip
            if t < old[0]:
                continue
        chosen[leg] = (t, ex)
    legs = []
    for k, (a, b) in enumerate(bounds):
        track: list[Cell] = []
        run_of: list[int] = []
        for _t, _m, c in conf[a:b]:
            if not track or track[-1] != c:
                track.append(c)
            run_of.append(len(track) - 1)
        kept = thin_track(track, {run_of[i - a] for i in marked if a <= i < b}, settings)
        wps = tuple(Waypoint(track[i][0], track[i][1], settings.radius, m) for i, m in kept)
        here = conf[a][1]
        if k == len(bounds) - 1:
            ex = END
        elif k in chosen:
            ex = chosen[k][1]
        else:
            ex = Exit("walk_exit", cell=track[-1])
            notes.append(f"leg {k} ({here}): no leave was recorded before the map changed to "
                         f"{conf[b][1]}: a walk exit at its last read cell {list(track[-1])} is "
                         "assumed (check it)")  # fmt: skip
        legs.append(Leg(here, wps, ex))
    return Thinned(checked(WalkPath(clean_name(name), tuple(legs))), tuple(notes), dropped)


# --- the proof (section 3 item 2) -----------------------------------------------------------------


def _open_why(c: Cell, g: Any, rg: Any, zones: mz.Zones | None) -> str | None:
    """map_routes.prove's own waypoint rule: closed_why, then sealed off by the zones."""
    why = mr.closed_why(c, g, zones)
    if why is None and not rg[c[1], c[0]]:
        why = "sealed off by the zones"
    return why


def _segment(rg: Any, a: Cell, b: Cell) -> dict[str, Any]:
    p = mr.leg_path(rg, a, b)
    return {"status": "ok" if p is not None else "broken",
            "steps": None if p is None else len(p) - 1,
            "cost": None if p is None else round(mr.path_cost(p), 1)}  # fmt: skip


_NOT_CONNECTED = "not connected on the route grid (the walkable cells minus the zones)"


def prove_leg(leg: Leg, grid: Any, zones: mz.Zones | None = None) -> dict[str, Any]:
    """PURE: one leg on its map (the module docstring's PROOF). ``grid``: the map's walkable cells
    ([y, x]); ``zones``: the map's zones (None: none). Returns {"ok", "problems", "points": [{"i",
    "cell", "status" ok|closed, "why"}], "segments": [{"from", "to", "status" ok|broken, "steps",
    "cost"}], "exit": None or (a walk_exit) {"cell", "status" ok|closed|broken, "why", "steps",
    "cost"}, "total_steps", "total_cost"} -- the totals over the segments and the exit's, None
    when one is broken."""
    g = np.asarray(grid, dtype=bool)
    rg = mr.route_grid(g, zones)
    cells = leg.cells()
    problems: list[str] = []
    points = []
    for i, c in enumerate(cells):
        why = _open_why(c, g, rg, zones)
        if why is not None:
            problems.append(f"point {i} {list(c)}: {why}")
        points.append({"i": i, "cell": list(c), "status": "ok" if why is None else "closed",
                       "why": why})  # fmt: skip
    segments = []
    for i in range(len(cells) - 1):
        seg = {"from": i, "to": i + 1, **_segment(rg, cells[i], cells[i + 1])}
        if seg["status"] != "ok":
            problems.append(f"segment {i} -> {i + 1} ({list(cells[i])} -> {list(cells[i + 1])}): "
                            f"{_NOT_CONNECTED}")  # fmt: skip
        segments.append(seg)
    walked = list(segments)
    ex: dict[str, Any] | None = None
    if leg.exit.kind == "walk_exit" and leg.exit.cell is not None:
        c = leg.exit.cell
        why = _open_why(c, g, rg, zones)
        seg = _segment(rg, cells[-1], c)
        if why is not None:
            problems.append(f"the exit's warp cell {list(c)}: {why}")
            seg["status"] = "closed"
        elif seg["status"] != "ok":
            problems.append(f"point {len(cells) - 1} -> the exit's warp cell {list(c)}: "
                            f"{_NOT_CONNECTED}")  # fmt: skip
        ex = {"cell": list(c), "why": why, **seg}
        walked.append(ex)
    whole = all(s["steps"] is not None for s in walked)
    return {"ok": not problems, "problems": problems, "points": points, "segments": segments,
            "exit": ex, "total_steps": sum(s["steps"] for s in walked) if whole else None,
            "total_cost": round(sum(s["cost"] for s in walked), 1) if whole else None}  # fmt: skip


def _unproven(leg: Leg) -> dict[str, Any]:
    cells = leg.cells()
    ex = None
    if leg.exit.kind == "walk_exit" and leg.exit.cell is not None:
        ex = {"cell": list(leg.exit.cell), "why": None, "status": "unproven", "steps": None,
              "cost": None}  # fmt: skip
    return {"ok": False, "problems": ["no walk grid for this map: not proven"],
            "points": [{"i": i, "cell": list(c), "status": "unproven", "why": None}
                       for i, c in enumerate(cells)],
            "segments": [{"from": i, "to": i + 1, "status": "unproven", "steps": None,
                          "cost": None} for i in range(len(cells) - 1)],
            "exit": ex, "total_steps": None, "total_cost": None}  # fmt: skip


def prove(path: WalkPath, grids: Mapping[str, Any],
          zones: Mapping[str, mz.Zones | None] | None = None) -> dict[str, Any]:  # fmt: skip
    """PURE: every leg on its map's grid (``prove_leg``). ``grids``: map name -> walkable cells;
    ``zones``: map name -> its zones (absent: none). A map with no grid is not proven (its
    statuses ``unproven``, and a problem). Returns {"ok", "problems" (each "leg K (map): ..."),
    "legs": [{"leg", "map", **prove_leg's}]}."""
    checked(path)
    zs = zones or {}
    problems: list[str] = []
    legs = []
    for k, leg in enumerate(path.legs):
        grid = grids.get(leg.map)
        rep = _unproven(leg) if grid is None else prove_leg(leg, grid, zs.get(leg.map))
        problems += [f"leg {k} ({leg.map}): {p}" for p in rep["problems"]]
        legs.append({"leg": k, "map": leg.map, **rep})
    return {"ok": not problems, "problems": problems, "legs": legs}


# --- edits (section 3 item 2) ---------------------------------------------------------------------


def _leg_at(path: WalkPath, leg: int) -> Leg:
    if not _int(leg) or not 0 <= leg < len(path.legs):
        raise PathError(f"no leg {leg!r} (the path has {len(path.legs)})")
    return path.legs[leg]


def _point_index(lg: Leg, leg: int, i: int, end_ok: bool = False) -> int:
    n = len(lg.waypoints) + (1 if end_ok else 0)
    if not _int(i) or not 0 <= i < n:
        raise PathError(f"leg {leg} ({lg.map}) has no point {i!r} (it has {len(lg.waypoints)})")
    return i


def _cell_arg(cell: Sequence[int], what: str = "the cell") -> Cell:
    if not isinstance(cell, Sequence) or len(cell) != 2:
        raise PathError(f"{what} is not (x, y)")
    c = (cell[0], cell[1])
    why = _cell_problem(c, what)
    if why is not None:
        raise PathError(why)
    return c


def _replace_leg(path: WalkPath, leg: int, new: Leg) -> WalkPath:
    legs = list(path.legs)
    legs[leg] = new
    return checked(WalkPath(path.name, tuple(legs)))


def _with_points(path: WalkPath, leg: int, wps: list[Waypoint]) -> WalkPath:
    return _replace_leg(path, leg, dataclasses.replace(path.legs[leg], waypoints=tuple(wps)))


def move_point(path: WalkPath, leg: int, i: int, cell: Sequence[int]) -> WalkPath:
    """PURE (drag): point ``i`` of leg ``leg`` moved to ``cell``; its radius and mark kept."""
    lg = _leg_at(checked(path), leg)
    i, (x, y) = _point_index(lg, leg, i), _cell_arg(cell)
    wps = list(lg.waypoints)
    wps[i] = dataclasses.replace(wps[i], x=x, y=y)
    return _with_points(path, leg, wps)


def insert_point(path: WalkPath, leg: int, i: int, cell: Sequence[int],
                 radius: int = DEFAULT_RADIUS) -> WalkPath:  # fmt: skip
    """PURE: a new point at ``cell`` that becomes point ``i`` of leg ``leg`` (0 .. its length:
    the length appends it), with ``radius``; not a mark."""
    lg = _leg_at(checked(path), leg)
    wps = list(lg.waypoints)
    x, y = _cell_arg(cell)
    wps.insert(_point_index(lg, leg, i, end_ok=True), Waypoint(x, y, radius))
    return _with_points(path, leg, wps)


def delete_point(path: WalkPath, leg: int, i: int) -> WalkPath:
    """PURE: point ``i`` of leg ``leg`` removed (a leg keeps at least one point)."""
    lg = _leg_at(checked(path), leg)
    wps = list(lg.waypoints)
    del wps[_point_index(lg, leg, i)]
    if not wps:
        raise PathError(f"leg {leg} ({lg.map}): a leg keeps at least one point")
    return _with_points(path, leg, wps)


def set_radius(path: WalkPath, leg: int, i: int, radius: int) -> WalkPath:
    """PURE: point ``i`` of leg ``leg`` with the arrival radius ``radius``."""
    lg = _leg_at(checked(path), leg)
    i = _point_index(lg, leg, i)
    wps = list(lg.waypoints)
    wps[i] = dataclasses.replace(wps[i], radius=radius)
    return _with_points(path, leg, wps)


def set_exit(path: WalkPath, leg: int, ex: Exit) -> WalkPath:
    """PURE: leg ``leg`` left by ``ex`` (the last leg's exit stays end)."""
    lg = _leg_at(checked(path), leg)
    return _replace_leg(path, leg, dataclasses.replace(lg, exit=ex))


def rename(path: WalkPath, name: str) -> WalkPath:
    """PURE: the path named ``name`` (``clean_name`` applied, then checked)."""
    checked(path)
    if not isinstance(name, str):
        raise PathError("the path's name is not text")
    return checked(dataclasses.replace(path, name=clean_name(name)))


# --- walking (Amendment 1 d) ----------------------------------------------------------------------


def leg_route(path: WalkPath, leg: int) -> mr.Route:
    """The leg as map_routes sees a route: an open PATH through its waypoints, in order."""
    lg = _leg_at(path, leg)
    return mr.Route(f"leg-{leg}", "path", lg.map, lg.cells())


def reached(path: WalkPath, leg: int, i: int, here: Cell) -> bool:
    """PURE: ``here`` is within point ``i``'s own radius (map_routes.reached)."""
    lg = _leg_at(path, leg)
    w = lg.waypoints[_point_index(lg, leg, i)]
    return mr.reached(here, w.cell, w.radius)


def ahead(path: WalkPath, leg: int, map_name: str, here: Cell, last: int | None = None
          ) -> int | None:  # fmt: skip
    """PURE: the waypoint of leg ``leg`` to walk to from ``here`` on ``map_name``. ``last``: the
    last waypoint reached or passed on this leg (None: none yet -- the walk's start, or a new map).
    None: the leg's points are all passed (next: its exit). WrongMap when ``map_name`` is not the
    leg's map. map_routes' own rules (``entry_index`` / ``resume_index``) on ``leg_route``, with
    the candidate's own radius as the reach tolerance."""
    lg = _leg_at(checked(path), leg)
    if map_name != lg.map:
        raise WrongMap(f"she is on {map_name}, the path expects {lg.map}")
    route, wps = leg_route(path, leg), lg.waypoints
    if last is None:
        # entry_index's own candidate (the nearest, the first on a tie): its radius is the tolerance
        j = min(range(len(wps)), key=lambda k: mr.cheb(here, wps[k].cell))
        return mr.entry_index(route, here, wps[j].radius)
    nxt = mr.next_index(route, _point_index(lg, leg, last))
    return None if nxt is None else mr.resume_index(route, here, last, wps[nxt].radius)
