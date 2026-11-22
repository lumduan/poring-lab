#!/usr/bin/env python3
"""ROUTE TRACK -- the player's cell track from a RECORDING of her own play
(docs/planning/waypoints-npc-recording.md Amendment 8, Batt 2026-11-22: routes come from a video of
the player's own play at ~5 fps; a frame whose ``x y`` reads badly is fixed from the frames beside
it; the gap between two frames is filled with the shortest walkable path on the map's grid). This
is phase 1's CODE (Amendment 8 decision 5.1): an OFFLINE pass from a recording to her cell track,
which feeds ``path_blocks.thin`` and so the walk_to blocks of Amendments 5-7. It scores nothing:
the sessions and the bars of a score are pre-registered in a later amendment.

    route_track.py reads SESSION [--every-s 0.2] [--max-frames N] --out RAW.jsonl
    route_track.py track RAW.jsonl --map MAP [--mapcache DIR] [--t-from S] [--t-to S]
                         [--max-speed C] [--slack C] [--window N] [--max-gap-s S]
                         [--min-support N] [--gat] [--zones] --out TRACK.jsonl
    route_track.py check RAW.jsonl TRACK.jsonl SESSION [--templates NPZ] [--out REPORT.json]

THE CORE (``build_track``) is PURE: no file, no live read, no decode. Its input is ONE MAP STAY's
raw reads in time order, (t seconds, (x, y) or None, the reader's reason or None), one per sampled
frame, and the map's walkable grid (indexed [y, x], y north: map_routes' convention, no flip).
Cutting a recording into map stays is the caller's (the recording's minimap-change marks, /where;
Amendment 8 decision 1); ``track`` takes one stay by --map and an optional time range.

THE RULES (every threshold is a ``TrackSettings`` field, our value its default: Batt 2026-11-13,
everything a user would set is a setting):
- CONSISTENT: two reads (t1, c1), (t2, c2) are consistent when cheb(c1, c2) <= max_speed * |t2 -
  t1| + slack (Chebyshev cells: an 8-way step is one cell, as map_routes.cheb).
- A CANDIDATE is a read with a cell on the grid and walkable there (else dropped: ``off_map``,
  ``not_walkable``; a cell she cannot stand on is a misread). None (the reader abstained, or a map
  with no minimap) is no read at all, not a drop.
- VOTES: a candidate's neighbours are the ``window`` nearest candidates before it and the ``window``
  nearest after it, each within ``max_gap_s`` of it (a read further away is on another piece of the
  track: it vouches for nothing). It is ACCEPTED when its consistent neighbours are at least
  ``min_support`` and at least as many as its inconsistent ones; else dropped, ``outlier`` (more
  inconsistent than consistent) or ``unconfirmed`` (too few to vouch: a lone read). The votes are
  counted TWICE: first among all candidates, then against the reads the first count accepted, so
  a good read beside a burst of misreads is not outvoted by the misreads (the accepted neighbours
  are what a read is judged against). A burst of up to ``window`` mutually consistent misreads
  loses both counts; at a real jump (a Fly Wing, a GM warp) the reads on each side carry their own
  side's votes, so both sides are kept and the track splits there.
- EXCURSIONS: a piece of accepted reads entered by an inconsistent step and left by another, whose
  reads before and after are consistent with each other within ``max_gap_s`` (an out-and-back
  faster than walking), is dropped (``excursion``): a misread burst longer than the window --
  selfpos' known blind spot, another window darkening the y number's last digit(s) -- and nothing
  a player can do (a teleport lands at random, never back where it left). Not caught: a burst
  right before a REAL jump, whose returning read the jump's far side outvotes -- the burst then
  stays as a segment of its own (a dev probe on outdoor-b, 2026-11-22: 1 burst of 24).
- GAPS: frames between two consecutive accepted reads a, b (no read, or a dropped one) are FILLED
  with the shortest walkable path ``map_routes.leg_path(route_grid(grid, zones), a, b)`` (the
  runner's own router: 8-connected, octile costs, a diagonal step needs both side cells), each
  frame given the path cell at its share of the walking time between the two reads (RO's step
  costs: a diagonal is 1.4 straight steps; the nearest cell, the earlier on a tie). It stays
  UNFILLED, and the track SPLITS there (a new segment), when the gap is longer than ``max_gap_s``
  (``gap_too_long``), a and b are not consistent (``jump``), no walkable path is within reach
  (``no_path``), or the path is longer than max_speed * dt + slack (``too_far``). Two consecutive
  accepted reads with no frame between that are not consistent split it too (``jump``). Frames
  before the first accepted read and after the last are not filled (``track_start`` /
  ``track_end``; ``no_track`` when nothing was accepted).
- ``zones`` (default None) are map_zones' reviewed zones: the fill then avoids them, as the
  runners do (``map_routes.route_grid``). The CLI leaves them out unless --zones: a track records
  where she walked, and a walk_to through a zone is path_blocks.check_route's warning, not a gap.

THE OUTPUT (``Track``): one ``Frame`` per input read, in order: its final cell and its SOURCE --
``read`` (its own read, accepted), ``filled`` (a gap frame given a path cell; ``drop`` keeps why
its own read was dropped, if it had one), ``dropped`` (its read was dropped and the frame is in no
filled gap), ``unfilled`` (no read, in no filled gap); its ``gap`` (``filled`` or why not) and its
``segment`` (None without a cell). ``to_reads(map_id)``: path_blocks' raw reads (t, map, x, y,
confirmed), confirmed for ``read`` and ``filled``; the others unconfirmed with no cell (thin drops
and counts them). path_blocks.thin splits a run only at a map change: a caller that wants the
track's splits thins each ``segment`` apart. Deterministic: the same reads give the same track.

THE CLI (thin; offline only: the packets of ``check`` label, they never reach the track):
- ``reads``: a recorded session's frames (poring_dataset.h264 for an H.264 session, as
  selfpos_eval reads them; poring_dataset.frames for the PNG and video layouts), one frame at or
  after each ``--every-s`` tick, as the 1280x720 game region (a 1280x720 recording as it is; any
  other size through poring_env.clientview's virtual client: the recording's own client_view when
  its manifest has one, else the minimap anchored top-right as ro_agent.LAB_PANELS), read with
  ``poring_env.selfpos.read_minimap(..., light=True)`` exactly as the runner reads it. The runtime
  jump guard (PORING_CONFIRM_READS) is OFF here: the track's own rules judge the jumps.
- ``track``: the core on one stay, the map's grid from the server's map cache
  (``poring_dataset.mapcache``, as selfpos_calibrate loads it; pre-re; ``--gat`` intersects the
  client's GAT, ``walkable.both``, as the live planners do).
- ``check``: a DEV check, NOT a score: the raw and the track cells against the packet truth
  selfpos_calibrate / selfpos_eval build (their SessionTruth, frame_class and error, unchanged).
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import os
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, NamedTuple

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import map_routes as mr  # noqa: E402

Cell = tuple[int, int]

SOURCES = ("read", "dropped", "filled", "unfilled")
DROPS = ("off_map", "not_walkable", "outlier", "unconfirmed", "excursion")
GAPS = ("filled", "gap_too_long", "jump", "no_path", "too_far", "track_start", "track_end",
        "no_track")  # fmt: skip
SPLITS = ("jump", "gap_too_long", "no_path", "too_far")
TEMPLATES = ROOT / "data" / "ui_anchors" / "minimap_digits.npz"  # selfpos_calibrate.OUT
EVERY_S = 0.2  # Amendment 8 decision 2: 5 fps
VIRTUAL_W, VIRTUAL_H = 1280, 720  # poring_env.clientview's virtual client
# ro_agent.LAB_PANELS' minimap entry (RO keeps the minimap at the top-right corner; a test pins the
# two equal): the only panel the readout needs when a recording carries no client_view
MINIMAP_PANEL: tuple[str, tuple[int, int, int, int], Literal["tr"]] = (
    "minimap", (1130, 10, 150, 160), "tr")  # fmt: skip
DIAGONAL_COST = 1.4  # hunt_core.STEP_MS: a diagonal step's cost, for the router's node cap


class TrackError(ValueError):
    """Reads, a grid or settings that are not valid: refused, nothing is built."""


# --- the core (PURE) ------------------------------------------------------------------------------


class RawRead(NamedTuple):
    """One sampled frame's read: its time (s, any one clock), the cell or None, the reason."""

    t: float
    xy: Cell | None
    reason: str | None = None


@dataclass(frozen=True)
class TrackSettings:
    # RO's default walk is 150 ms a cell (rAthena DEFAULT_WALK_SPEED: 6.7 cells/s, the runtime's
    # own selfpos JUMP_S_PER_CELL); Increase AGI, a mount or a speed potion make it ~25-50 %
    # faster. 10 cells/s (100 ms a cell) is the default walk 1.5x faster; a faster character
    # raises it.
    max_speed: float = 10.0  # cells per second (Chebyshev: an 8-way step is one cell)
    # the readout and the frame's time can disagree by a frame or two (the client's draw, the
    # codec), and a read taken as she crosses a cell edge is one cell either way
    slack: int = 2  # cells added to every reach
    window: int = 3  # neighbours each side that vote (0.6 s at 5 fps)
    # ten frames at 5 fps; at the default walk at most ~13 cells, about one thinning step
    # (path_blocks every_cells 10): a wrong guess in a fill moves at most one kept point
    max_gap_s: float = 2.0  # a gap up to this long is filled; also the vote and excursion reach
    min_support: int = 1  # consistent neighbours a read needs (the runner's PosConfirm: two agree)


DEFAULTS = TrackSettings()


def _int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _num(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v)


def settings_problem(s: Any) -> str | None:
    """PURE: why ``s`` is not usable track settings (None: they are)."""
    if not isinstance(s, TrackSettings):
        return "not track settings"
    if not _num(s.max_speed) or s.max_speed <= 0:
        return f"max_speed {s.max_speed!r} is not a number of cells per second above 0"
    if not _num(s.max_gap_s) or s.max_gap_s <= 0:
        return f"max_gap_s {s.max_gap_s!r} is not a number of seconds above 0"
    if not _int(s.slack) or s.slack < 0:
        return f"slack {s.slack!r} is not a whole number of cells, 0 or more"
    if not _int(s.window) or s.window < 1:
        return f"window {s.window!r} is not a whole number of at least 1"
    if not _int(s.min_support) or not 0 <= s.min_support <= 2 * s.window:
        return f"min_support {s.min_support!r} is not a whole number 0 .. 2 x window"
    return None


class Frame(NamedTuple):
    """One input read's place in the track (the module docstring's OUTPUT)."""

    t: float
    raw: Cell | None  # the reader's cell (None: no read)
    reason: str | None  # the reader's own reason
    cell: Cell | None  # the track's cell
    source: str  # read | dropped | filled | unfilled
    drop: str | None  # why its read was dropped (None: not dropped, or no read)
    gap: str | None  # a frame without an accepted read: "filled", or why it was not
    segment: int | None  # the track's piece (None: no cell)


class Split(NamedTuple):
    """Where the track splits: the time of the first accepted read after it, and why."""

    t: float
    why: str


@dataclass(frozen=True)
class Track:
    frames: tuple[Frame, ...]
    splits: tuple[Split, ...]
    settings: TrackSettings

    @property
    def segments(self) -> int:
        """How many pieces the track has (0: nothing was accepted)."""
        segs = [f.segment for f in self.frames if f.segment is not None]
        return max(segs) + 1 if segs else 0

    def summary(self) -> dict[str, Any]:
        """Counts: frames, per source, per drop reason (filled-over drops included), per gap
        reason, per split reason, the segments, and the settings."""
        fr = self.frames
        return {
            "frames": len(fr),
            "raw": {"cell": sum(f.raw is not None for f in fr),
                    "none": sum(f.raw is None for f in fr)},
            "sources": {s: sum(f.source == s for f in fr) for s in SOURCES},
            "drops": {d: n for d in DROPS if (n := sum(f.drop == d for f in fr))},
            "gaps": {g: n for g in GAPS if (n := sum(f.gap == g for f in fr))},
            "splits": {w: n for w in SPLITS if (n := sum(s.why == w for s in self.splits))},
            "segments": self.segments,
            "settings": asdict(self.settings),
        }  # fmt: skip

    def to_reads(self, map_id: str, segment: int | None = None
                 ) -> list[tuple[float, str, int | None, int | None, bool]]:  # fmt: skip
        """path_blocks' raw reads (t, map, x, y, confirmed): confirmed for ``read`` and
        ``filled``; every other frame unconfirmed with no cell. ``segment``: that piece's frames
        only (then the frames without a cell are left out)."""
        if not isinstance(map_id, str) or not map_id:
            raise TrackError(f"map {map_id!r} is not a map name")
        out: list[tuple[float, str, int | None, int | None, bool]] = []
        for f in self.frames:
            if segment is not None and f.segment != segment:
                continue
            if f.cell is not None and f.source in ("read", "filled"):
                out.append((f.t, map_id, f.cell[0], f.cell[1], True))
            else:
                out.append((f.t, map_id, None, None, False))
        return out


def _cell(v: Any, k: int) -> Cell | None:
    if v is None:
        return None
    if not isinstance(v, Sequence) or isinstance(v, str) or len(v) != 2:
        raise TrackError(f"read {k}: its cell is not (x, y) or None")
    x, y = v[0], v[1]
    if not (_int(x) and _int(y)) or x < 0 or y < 0:
        raise TrackError(f"read {k}: its cell {list(v)} is not two whole numbers, 0 or more")
    return (x, y)


def _reads(reads: Iterable[Any]) -> list[RawRead]:
    out: list[RawRead] = []
    for k, r in enumerate(reads):
        if not isinstance(r, Sequence) or isinstance(r, str) or len(r) not in (2, 3):
            raise TrackError(f"read {k} is not (t, (x, y) or None, reason)")
        t = r[0]
        if not _num(t):
            raise TrackError(f"read {k}: its time {t!r} is not a finite number")
        reason = r[2] if len(r) == 3 else None
        if reason is not None and not isinstance(reason, str):
            raise TrackError(f"read {k}: its reason is not text or None")
        if out and t < out[-1].t:
            raise TrackError(f"read {k}: the reads are not in time order")
        out.append(RawRead(float(t), _cell(r[1], k), reason))
    return out


def consistent(a: Cell, ta: float, b: Cell, tb: float, s: TrackSettings = DEFAULTS) -> bool:
    """PURE: b can follow a in the time between them: cheb(a, b) <= max_speed * |dt| + slack."""
    return mr.cheb(a, b) <= s.max_speed * abs(tb - ta) + s.slack


def reach(dt: float, s: TrackSettings = DEFAULTS) -> float:
    """PURE: the most cells she can walk in ``dt`` seconds (max_speed * dt + slack)."""
    return s.max_speed * dt + s.slack


def _neighbours(i: int, pool: Sequence[int], ts: Sequence[float], s: TrackSettings) -> list[int]:
    """The up to ``window`` pool frames nearest before ``i`` and after it (``i`` left out), each
    within ``max_gap_s`` of it. ``pool``: frame indices, sorted."""
    k = bisect.bisect_left(pool, i)
    before = [j for j in pool[max(0, k - s.window) : k] if ts[i] - ts[j] <= s.max_gap_s]
    k2 = bisect.bisect_right(pool, i)
    after = [j for j in pool[k2 : k2 + s.window] if ts[j] - ts[i] <= s.max_gap_s]
    return before + after


def _judge(i: int, pool: Sequence[int], ts: Sequence[float], cells: Sequence[Cell | None],
           s: TrackSettings) -> str | None:  # fmt: skip
    """The VOTES rule: None (accepted), "outlier" or "unconfirmed"."""
    ci = cells[i]
    assert ci is not None
    sup = ag = 0
    for j in _neighbours(i, pool, ts, s):
        cj = cells[j]
        assert cj is not None
        if consistent(ci, ts[i], cj, ts[j], s):
            sup += 1
        else:
            ag += 1
    if ag > sup:
        return "outlier"
    if sup < s.min_support:
        return "unconfirmed"
    return None


def _excursions(acc: list[int], ts: Sequence[float], cells: Sequence[Cell | None],
                s: TrackSettings) -> tuple[list[int], list[int]]:  # fmt: skip
    """The EXCURSIONS rule over the accepted frames ``acc`` (sorted): (kept, dropped)."""

    def ok(i: int, j: int) -> bool:
        ci, cj = cells[i], cells[j]
        assert ci is not None and cj is not None
        return consistent(ci, ts[i], cj, ts[j], s)

    acc = list(acc)
    dropped: list[int] = []
    k = 0
    while k < len(acc) - 1:
        a = acc[k]
        if ok(a, acc[k + 1]):
            k += 1
            continue
        hit = None
        for m in range(k + 1, len(acc) - 1):
            b = acc[m + 1]
            if ts[b] - ts[a] > s.max_gap_s:
                break
            if not ok(acc[m], b) and ok(a, b):
                hit = m
                break
        if hit is None:
            k += 1
            continue
        dropped += acc[k + 1 : hit + 1]
        del acc[k + 1 : hit + 1]
    return acc, dropped


def _node_cap(r: float) -> int:
    """hunt_core.astar's node bound for a path of at most ``r`` steps: every node it expands
    before the goal costs at most the path's (<= 1.4 r), so lies within that many cells of the
    start (Chebyshev). Past the bound no path short enough exists."""
    side = 2 * math.floor(DIAGONAL_COST * max(0.0, r)) + 1
    return int(min(mr.LEG_MAX_NODES, side * side))


def path_cell(path: Sequence[Cell], frac: float) -> Cell:
    """PURE: the cell of ``path`` at ``frac`` (0 .. 1) of its walking time (a diagonal step costs
    1.4 straight ones: map_routes.path_cost): the cell whose elapsed cost is nearest, the earlier
    on a tie."""
    cum = [0.0]
    for p, q in zip(path, path[1:], strict=False):
        cum.append(cum[-1] + mr.path_cost([p, q]))
    target = min(1.0, max(0.0, frac)) * cum[-1]
    best = min(range(len(path)), key=lambda k: (abs(cum[k] - target), k))
    return path[best]


def _grid(grid: Any) -> Any:
    g = np.asarray(grid)
    if g.ndim != 2 or g.shape[0] < 1 or g.shape[1] < 1:
        raise TrackError("the grid is not a 2-D [y, x] array of walkable cells")
    return g.astype(bool)


def build_track(reads: Iterable[Any], grid: Any, zones: Any = None,
                settings: TrackSettings = DEFAULTS) -> Track:  # fmt: skip
    """PURE: one map stay's raw reads -> its cell track (the module docstring's RULES).
    ``reads``: (t, (x, y) or None[, reason]) in time order; ``grid``: the map's walkable cells,
    [y, x], y north; ``zones``: map_zones' zones for the fill (None: none). TrackError on bad
    input."""
    why = settings_problem(settings)
    if why is not None:
        raise TrackError(f"settings: {why}")
    s = settings
    rr = _reads(reads)
    g = _grid(grid)
    h, w = g.shape
    n = len(rr)
    ts = [r.t for r in rr]
    cells: list[Cell | None] = [r.xy for r in rr]
    drop: list[str | None] = [None] * n
    cand: list[int] = []
    for i, c in enumerate(cells):
        if c is None:
            continue
        if not (c[0] < w and c[1] < h):
            drop[i] = "off_map"
        elif not g[c[1], c[0]]:
            drop[i] = "not_walkable"
        else:
            cand.append(i)
    acc1 = [i for i in cand if _judge(i, cand, ts, cells, s) is None]
    acc: list[int] = []
    for i in cand:
        why_i = _judge(i, acc1, ts, cells, s)
        if why_i is None:
            acc.append(i)
        else:
            drop[i] = why_i
    acc, exc = _excursions(acc, ts, cells, s)
    for i in exc:
        drop[i] = "excursion"

    out_cell: list[Cell | None] = [None] * n
    source = ["dropped" if drop[i] is not None else "unfilled" for i in range(n)]
    gap: list[str | None] = [None] * n
    seg: list[int | None] = [None] * n
    splits: list[Split] = []
    if not acc:
        gap = ["no_track"] * n
    else:
        rg = mr.route_grid(g, zones)
        k_seg = 0
        for i in range(acc[0]):
            gap[i] = "track_start"
        for i in range(acc[-1] + 1, n):
            gap[i] = "track_end"
        for pos, a in enumerate(acc):
            if pos:
                p = acc[pos - 1]
                ca, cb = cells[p], cells[a]
                assert ca is not None and cb is not None
                inner = range(p + 1, a)
                dt = ts[a] - ts[p]
                cut: str | None = None
                path: list[Cell] | None = None
                if not inner:
                    cut = None if consistent(ca, ts[p], cb, ts[a], s) else "jump"
                elif dt > s.max_gap_s:
                    cut = "gap_too_long"
                elif not consistent(ca, ts[p], cb, ts[a], s):
                    cut = "jump"
                else:
                    r = reach(dt, s)
                    path = mr.leg_path(rg, ca, cb, max_nodes=_node_cap(r))
                    if path is None:
                        cut = "no_path"
                    elif len(path) - 1 > r:
                        cut = "too_far"
                for i in inner:
                    gap[i] = cut or "filled"
                if cut is not None:
                    splits.append(Split(ts[a], cut))
                    k_seg += 1
                elif inner:
                    assert path is not None
                    for i in inner:
                        frac = (ts[i] - ts[p]) / dt if dt > 0 else 0.0
                        out_cell[i] = path_cell(path, frac)
                        source[i] = "filled"
                        seg[i] = k_seg
            out_cell[a] = cells[a]
            source[a] = "read"
            seg[a] = k_seg
    frames = tuple(Frame(rr[i].t, rr[i].xy, rr[i].reason, out_cell[i], source[i], drop[i],
                         gap[i], seg[i]) for i in range(n))  # fmt: skip
    return Track(frames, tuple(splits), s)


# --- the frames (thin, offline) -------------------------------------------------------------------


class Picker:
    """PURE: which frames to read: the first one, then the first at or after each later tick
    t0 + k * every_s (a frame is taken once; a tick with no frame of its own is skipped)."""

    def __init__(self, every_s: float) -> None:
        if not _num(every_s) or every_s <= 0:
            raise TrackError(f"every_s {every_s!r} is not a number of seconds above 0")
        self.every_ns = max(1, round(every_s * 1e9))
        self.t0: int | None = None
        self.next_ns = 0

    def take(self, t_ns: int) -> bool:
        if self.t0 is None:
            self.t0, self.next_ns = t_ns, t_ns + self.every_ns
            return True
        if t_ns < self.next_ns:
            return False
        k = (t_ns - self.t0) // self.every_ns + 1
        self.next_ns = self.t0 + k * self.every_ns
        return True


def pick_times(times_ns: Iterable[int], every_s: float) -> list[int]:
    """PURE: the indices ``Picker`` takes from frame times in recording order."""
    p = Picker(every_s)
    return [i for i, t in enumerate(times_ns) if p.take(int(t))]


def client_view_of(manifest: Mapping[str, Any], size: tuple[int, int]) -> tuple[Any, str]:
    """PURE: the view that maps a recorded game region of ``size`` (w, h) to the virtual 1280x720
    client, and which one it is: the manifest's own ``client_view`` (record_session v8,
    rec_paths.view_record) when its rect has that size and it places the minimap; else the
    minimap anchored top-right (ro_agent.LAB_PANELS), the world scaled by h / 720."""
    from poring_env.clientview import ClientView, Panel, anchored_view

    w, h = size
    cv = manifest.get("client_view")
    if isinstance(cv, Mapping):
        try:
            rect = [int(v) for v in cv["rect"]]
            panels = []
            for p in cv.get("panels") or []:
                if p["name"] == "cursor":
                    continue
                vx, vy, vw, vh = (int(v) for v in p["virtual"])
                panels.append(Panel(str(p["name"]), (vx, vy, vw, vh),
                                    (int(p["real_xy"][0]), int(p["real_xy"][1]))))  # fmt: skip
            centre = cv.get("world_centre")
            if rect[2:] == [w, h] and any(p.name == "minimap" for p in panels):
                view = ClientView((0, 0, w, h), cv.get("mode", "window"), float(cv["world_scale"]),
                                  None if centre is None else (float(centre[0]), float(centre[1])),
                                  tuple(panels))  # fmt: skip
                return view, "the recording's client_view"
        except (KeyError, TypeError, ValueError, IndexError):
            pass
    view = anchored_view((0, 0, w, h), "fullscreen", [MINIMAP_PANEL], world_scale=h / VIRTUAL_H)
    return view, "the minimap anchored top-right"


def game_view(img: Any, manifest: Mapping[str, Any]) -> tuple[Any, str]:
    """PURE: the 1280x720 game region the reader reads, and how it was made: a 1280x720 frame as
    it is; any other size as the virtual client's picture (``client_view_of``)."""
    h, w = img.shape[:2]
    if (w, h) == (VIRTUAL_W, VIRTUAL_H):
        return img, "as recorded (1280x720)"
    view, how = client_view_of(manifest, (w, h))
    return view.virtual_frame(np.ascontiguousarray(img)), f"virtual client from {w}x{h} ({how})"


def session_frames(session: Path, manifest: Mapping[str, Any], every_s: float,
                   max_frames: int | None) -> Iterator[tuple[dict[str, Any], Any]]:  # fmt: skip
    """(meta with frame_id and t_mono_ns, BGR game region) of the frames ``Picker`` takes, in
    recording order: an H.264 session through poring_dataset.h264 (its usable frames, each GOP
    decoded once, as selfpos_eval reads them); PNG and video through poring_dataset.frames."""
    if manifest.get("format") == "h264":
        from poring_dataset.h264 import H264Session

        stream = H264Session(session)
        usable = set(stream.usable())
        units = [u for u in stream.units if u.frame_id in usable]
        ids = [units[i].frame_id for i in pick_times((u.t_ns for u in units), every_s)]
        if max_frames is not None:
            ids = ids[:max_frames]
        for meta, img in stream.frames(ids, verify=False, crop=True):
            yield {"frame_id": int(meta["frame_id"]), "t_mono_ns": int(meta["t_mono_ns"])}, img
        return
    from poring_dataset import frames as fr

    p = Picker(every_s)
    k = 0
    for meta, load in fr.iter_frames(session, dict(manifest)):
        if max_frames is not None and k >= max_frames:
            return
        t = int(meta["t_mono_ns"])
        if p.take(t):
            k += 1
            yield {"frame_id": int(meta["frame_id"]), "t_mono_ns": t}, load()


# --- the CLI --------------------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def cmd_reads(a: argparse.Namespace) -> int:
    import selfpos_calibrate as cal

    from poring_env import selfpos

    os.environ.pop(selfpos.CONFIRM_READS_ENV, None)  # the raw reads: the track judges the jumps
    session = cal.resolve_session(a.session)
    manifest = json.loads((session / "manifest.json").read_text())
    digits = selfpos.load_digit_templates(a.templates)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    reasons: Counter[str] = Counter()
    views: Counter[str] = Counter()
    n = cells = 0
    t_first: int | None = None
    t0 = time.monotonic()
    with a.out.open("w") as fh:
        for meta, img in session_frames(session, manifest, a.every_s, a.max_frames):
            region, how = game_view(img, manifest)
            views[how] += 1
            rd = selfpos.read_minimap(region, digits, light=True)
            t_ns = meta["t_mono_ns"]
            t_first = t_ns if t_first is None else t_first
            xy = rd.xy
            fh.write(json.dumps({"i": n, "frame": meta["frame_id"], "t_mono_ns": t_ns,
                                 "t": round((t_ns - t_first) / 1e9, 6),
                                 "x": None if xy is None else int(xy[0]),
                                 "y": None if xy is None else int(xy[1]),
                                 "reason": rd.reason, "mode": rd.mode}) + "\n")  # fmt: skip
            n += 1
            cells += xy is not None
            reasons[rd.reason] += 1
            if n % 1000 == 0:
                print(f"  {n} frames, {time.monotonic() - t0:.0f} s", file=sys.stderr)
    print(json.dumps({"session": session.name, "format": manifest.get("format"), "frames": n,
                      "cells": cells, "reasons": dict(reasons.most_common()),
                      "every_s": a.every_s, "max_frames": a.max_frames, "views": dict(views),
                      "templates": {"path": str(a.templates), "sha256": _sha256(a.templates)},
                      "reader": "selfpos.read_minimap(light=True), the runtime jump guard off",
                      "seconds": round(time.monotonic() - t0, 1), "out": str(a.out)}))  # fmt: skip
    return 0


def bare(map_name: str | None) -> str | None:
    """A map's name without ".gat" (packets say "prt_fild08.gat", the map cache "prt_fild08")."""
    return None if map_name is None else map_name.removesuffix(".gat")


def load_grid(map_name: str, mapcache_dir: Path, use_gat: bool = False) -> tuple[Any, str]:
    """The map's walkable grid [y, x] and its source: the server's map cache (pre-re, the lab's
    rule: poring_dataset.mapcache.load, as selfpos_calibrate loads it; walkable.server_passable);
    ``use_gat``: AND the client's GAT (walkable.both, the live planners' grid)."""
    from poring_dataset import mapcache, walkable

    name = bare(map_name)
    assert name is not None
    g = mapcache.load(mapcache_dir, prere=True).get(name)
    if g is None:
        raise TrackError(f"the map cache has no map {name!r}")
    if not use_gat:
        return walkable.server_passable(g), "server map cache (walkable.server_passable, pre-re)"
    from poring_dataset import gat as gatmod
    from poring_dataset.camera import GAT_DIR

    gat = gatmod.parse((GAT_DIR / f"{name}.gat").read_bytes())
    return walkable.both(gat, g), "client GAT and server map cache (walkable.both, pre-re)"


def _settings(a: argparse.Namespace) -> TrackSettings:
    return TrackSettings(max_speed=a.max_speed, slack=a.slack, window=a.window,
                         max_gap_s=a.max_gap_s, min_support=a.min_support)  # fmt: skip


def cmd_track(a: argparse.Namespace) -> int:
    rows = [r for r in _jsonl(a.raw)
            if (a.t_from is None or r["t"] >= a.t_from) and (a.t_to is None or r["t"] < a.t_to)
            ]  # fmt: skip
    grid, grid_src = load_grid(a.map, a.mapcache, a.gat)
    zones = None
    if a.zones:
        import map_zones as mz

        zones = mz.load(str(bare(a.map)), shape=grid.shape)
    reads = [(r["t"], None if r["x"] is None else (r["x"], r["y"]), r["reason"]) for r in rows]
    tr = build_track(reads, grid, zones, _settings(a))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    summary = {"kind": "summary", "map": bare(a.map), "raw": str(a.raw), "t_from": a.t_from,
               "t_to": a.t_to,
               "grid": {"source": grid_src, "shape": list(grid.shape),
                        "walkable": int(np.asarray(grid, bool).sum())},
               "zones": None if zones is None else {"file": zones.path, "sha256": zones.sha256},
               **tr.summary()}  # fmt: skip
    with a.out.open("w") as fh:
        for r, f in zip(rows, tr.frames, strict=True):
            fh.write(json.dumps({"kind": "frame", "i": r["i"], "frame": r["frame"],
                                 "t_mono_ns": r["t_mono_ns"], "t": f.t,
                                 "raw": None if f.raw is None else list(f.raw), "reason": f.reason,
                                 "cell": None if f.cell is None else list(f.cell),
                                 "source": f.source, "drop": f.drop, "gap": f.gap,
                                 "segment": f.segment}) + "\n")  # fmt: skip
        fh.write(json.dumps(summary) + "\n")
    print(json.dumps(summary))
    return 0


# --- the DEV check (not a score) ------------------------------------------------------------------

SCORED = ("standing", "walking")


def _rate(k: int, n: int) -> float | None:
    return round(k / n, 4) if n else None


def _acc(errs: Sequence[int | None], n: int) -> dict[str, Any]:
    """Cells given, their coverage of ``n`` frames, and how many are exact / within one cell."""
    got = [e for e in errs if e is not None]
    ex, w1 = sum(e == 0 for e in got), sum(e <= 1 for e in got)
    return {"cells": len(got), "coverage": _rate(len(got), n), "exact_n": ex,
            "exact": _rate(ex, len(got)), "within1_n": w1, "within1": _rate(w1, len(got)),
            "wrong_gt1": len(got) - w1}  # fmt: skip


def check_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """PURE: the DEV check's numbers from per-frame rows {"cls", "raw_err", "track_err",
    "source", "drop"} (an err is the Chebyshev distance to the true cell, None without a cell):
    per class (standing, walking, all scored) the raw and the track accuracy, the track per
    source, and what the dropped reads were (their raw error); every other class counted."""
    out: dict[str, Any] = {}
    groups = {c: [r for r in rows if r["cls"] == c] for c in SCORED}
    groups["all"] = [r for r in rows if r["cls"] in SCORED]
    for name, rs in groups.items():
        n = len(rs)
        by_src = {}
        for src in ("read", "filled"):
            sub = [r["track_err"] for r in rs if r["source"] == src]
            by_src[src] = _acc(sub, len(sub))
        dropped = [r["raw_err"] for r in rs if r["drop"] is not None and r["raw_err"] is not None]
        out[name] = {
            "n": n, "raw": _acc([r["raw_err"] for r in rs], n),
            "track": _acc([r["track_err"] for r in rs], n), "track_by_source": by_src,
            "sources": dict(Counter(r["source"] for r in rs)),
            "dropped_reads": {"n": len(dropped), "exact": sum(e == 0 for e in dropped),
                              "within1": sum(e <= 1 for e in dropped),
                              "wrong_gt1": sum(e > 1 for e in dropped)},
        }  # fmt: skip
    out["not_scored"] = dict(Counter(r["cls"] for r in rows if r["cls"] not in SCORED))
    return out


def _pct(v: float | None) -> str:
    return "   n/a" if v is None else f"{100 * v:6.2f}"


def check_table(s: Mapping[str, Any]) -> str:
    head = (f"{'class':<10}{'n':>7}  {'raw cov%':>8}{'exact%':>8}{'<=1%':>8}{'>1':>6}  "
            f"{'trk cov%':>8}{'exact%':>8}{'<=1%':>8}{'>1':>6}  {'filled':>7}{'f <=1%':>8}"
            f"{'drops':>6}{'d >1':>6}")  # fmt: skip
    lines = [head, "-" * len(head)]
    for name in (*SCORED, "all"):
        g = s[name]
        rw, tk, fl = g["raw"], g["track"], g["track_by_source"]["filled"]
        lines.append(f"{name:<10}{g['n']:>7}  {_pct(rw['coverage']):>8}{_pct(rw['exact']):>8}"
                     f"{_pct(rw['within1']):>8}{rw['wrong_gt1']:>6}  {_pct(tk['coverage']):>8}"
                     f"{_pct(tk['exact']):>8}{_pct(tk['within1']):>8}{tk['wrong_gt1']:>6}  "
                     f"{fl['cells']:>7}{_pct(fl['within1']):>8}{g['dropped_reads']['n']:>6}"
                     f"{g['dropped_reads']['wrong_gt1']:>6}")  # fmt: skip
    return "\n".join(lines)


def check_rows(frames: Sequence[Mapping[str, Any]], truth_at: Callable[[int], Any],
               classify: Callable[[Any], str], err: Callable[[Cell, Any], int],
               map_name: str | None) -> list[dict[str, Any]]:  # fmt: skip
    """The per-frame rows of ``check_summary``: each TRACK frame's truth (``truth_at`` its
    t_mono_ns), its class (``classify``; a scored frame on another map than the track's is
    "excluded:other_map") and the raw and track errors (``err``)."""
    rows = []
    for f in frames:
        tr = truth_at(int(f["t_mono_ns"]))
        cls = classify(tr)
        if cls in SCORED and bare(tr.map) != map_name:
            cls = "excluded:other_map"
        scored = cls in SCORED
        raw, cell = f["raw"], f["cell"]
        rows.append({"t_mono_ns": int(f["t_mono_ns"]), "cls": cls, "source": f["source"],
                     "drop": f["drop"],
                     "raw_err": err((raw[0], raw[1]), tr.pos) if scored and raw else None,
                     "track_err": err((cell[0], cell[1]), tr.pos) if scored and cell else None
                     })  # fmt: skip
    return rows


def cmd_check(a: argparse.Namespace) -> int:
    import selfpos_calibrate as cal
    import selfpos_eval as ev

    from poring_dataset import mapcache
    from poring_env import selfpos

    raw = {int(r["t_mono_ns"]): r for r in _jsonl(a.raw)}
    lines = _jsonl(a.track)
    frames = [r for r in lines if r.get("kind") == "frame"]
    summ = next((r for r in lines if r.get("kind") == "summary"), None)
    if summ is None:
        raise TrackError(f"{a.track}: no summary line (not a track file)")
    for f in frames:
        r = raw.get(int(f["t_mono_ns"]))
        xy = None if r is None or r["x"] is None else [r["x"], r["y"]]
        if r is None or xy != f["raw"]:
            raise TrackError(f"{a.track}: frame {f['frame']} is not {a.raw}'s read")
    meta = selfpos.load_digit_templates(a.templates).meta
    maps = mapcache.load(a.mapcache, prere=True)
    session = cal.resolve_session(a.session)
    truth = cal.SessionTruth(session, maps, offset_ms="auto", guard_ms=meta["guard_ms"],
                             load_ms=meta["load_ms"])  # fmt: skip
    rows = check_rows(frames, truth.at, lambda tr: ev.frame_class(tr, meta), ev.error,
                      summ["map"])  # fmt: skip
    s = check_summary(rows)
    report = {"session": session.name, "map": summ["map"], "track": str(a.track),
              "raw": str(a.raw), "t_from": summ.get("t_from"), "t_to": summ.get("t_to"),
              "truth": {"offset_ms": truth.offset_ms, "aid_source": truth.aid_source,
                        "guard_ms": meta["guard_ms"], "load_ms": meta["load_ms"]},
              "track_summary": {k: summ[k] for k in ("frames", "sources", "drops", "gaps",
                                                     "splits", "segments", "settings")},
              "check": s, "note": "DEV check on calibration sessions: not a score"}  # fmt: skip
    if a.out is not None:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(report, indent=1))
    print(check_table(s))
    print(json.dumps({"not_scored": s["not_scored"], "track": report["track_summary"]}))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    rd = sub.add_parser("reads", help="decode a session's frames and read the minimap readout")
    rd.add_argument("session")
    rd.add_argument("--every-s", type=float, default=EVERY_S)
    rd.add_argument("--max-frames", type=int, default=None)
    rd.add_argument("--templates", type=Path, default=TEMPLATES)
    rd.add_argument("--out", type=Path, required=True)
    tk = sub.add_parser("track", help="one map stay's raw reads -> its cell track")
    tk.add_argument("raw", type=Path)
    tk.add_argument("--map", required=True)
    tk.add_argument("--mapcache", type=Path, default=None)
    tk.add_argument("--gat", action="store_true", help="AND the client's GAT (walkable.both)")
    tk.add_argument("--zones", action="store_true", help="the fill avoids the map's zones")
    tk.add_argument("--t-from", type=float, default=None, help="raw t (s) from, inclusive")
    tk.add_argument("--t-to", type=float, default=None, help="raw t (s) to, exclusive")
    tk.add_argument("--max-speed", type=float, default=DEFAULTS.max_speed)
    tk.add_argument("--slack", type=int, default=DEFAULTS.slack)
    tk.add_argument("--window", type=int, default=DEFAULTS.window)
    tk.add_argument("--max-gap-s", type=float, default=DEFAULTS.max_gap_s)
    tk.add_argument("--min-support", type=int, default=DEFAULTS.min_support)
    tk.add_argument("--out", type=Path, required=True)
    ck = sub.add_parser("check", help="DEV check: raw and track cells against packet truth")
    ck.add_argument("raw", type=Path)
    ck.add_argument("track", type=Path)
    ck.add_argument("session")
    ck.add_argument("--mapcache", type=Path, default=None)
    ck.add_argument("--templates", type=Path, default=TEMPLATES)
    ck.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    if getattr(a, "mapcache", None) is None and a.cmd in ("track", "check"):
        from poring_dataset import mapcache

        a.mapcache = mapcache.GENERATED
    try:
        if a.cmd == "reads":
            return cmd_reads(a)
        if a.cmd == "track":
            return cmd_track(a)
        return cmd_check(a)
    except TrackError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
