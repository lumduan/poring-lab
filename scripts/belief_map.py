#!/usr/bin/env python3
"""BELIEF MAP ("Battleship", Batt 2026-10-17): a map-wide memory of monsters on the map's cell grid.

A monster seen once is "around there" even when hidden: it cannot teleport, it walks at a known
pace and only on walkable cells. A hover that shows the SWORD over a believed cell is a Battleship
HIT; a visible, unoccluded cell that shows no monster box is a MISS and lowers the belief there.

Decision-time inputs are PIXEL-ONLY (rule 1): the detector's boxes, our own cell (minimap +
odometry live; OFFLINE the packets' GM cell stands in for it), the camera / floor model and static
map data (client ∩ server walkable cells, ADR-0015: the engine's movement rules). Packets are
OFFLINE ground truth only (``eval``), never an input of the pure parts.

    belief_map.py eval SID [SID ...] [--json OUT]   # leave-one-session-out validation tables
    belief_map.py occluders SID [SID ...]           # the static occluder maps -> data/belief/

THE MODEL (pure parts, numpy only)
  GRID      anim_region.stand_grid(map) (client ∩ server walkable, warp spans and NPC touch areas
            out), 400 x 400 on prt_fild08 (89,689 cells).
  TRACKS    each monster box -> its cell (the box foot FOOT_LIFT px up, picked against the GAT's
            top surfaces with the camera centred on our fractional cell, hunt_flow.cell_of);
            greedy nearest-first association within REACH_CELLS + the kernel's 95th percentile
            for the time unseen; an unmatched box starts a track; a track unseen CAP_S is dropped.
  PREDICT   while unseen: the RING kernel. The probability mass at geodesic (8-connected, walls
            respected) distance d from the last-seen cell after t seconds unseen is K(t, d),
            spread evenly over the walkable cells of that ring. K is a table fitted OFFLINE from
            the detector's own sightings to the packets' true cell (``fit_kernel``: it holds the
            monsters' stand / walk rhythm AND the box -> cell error); a species-free mixture of
            the map's population (offline the species is unknown; with a species cue, one table
            per species: Pupa cannot move, Creamy walks 150 ms / cell, Lunatic 200, Poring /
            Drops 400). The geodesic distance is computed once per sighting in a (2 R + 1)^2
            window (R = RADIUS cells). WALK-ON (``lead``): a track whose last sightings moved
            >= 1.5 cells in 0.5-1.5 s also gets LEAD_W of its mass from the same kernel centred
            LEAD_CELLS further along that heading (rAthena's random walk ends a few cells on).
  NEGATIVE  each frame, every visible cell (feet on screen, body not under a static UI window or
            our own sprite) more than one cell from any box gets log(1 - PD x vis(c)) added to the
            track's log-miss map; the map decays with a half-life (the monster may have walked in
            since). posterior = K x exp(log-miss), renormalised; its sum before renormalising is
            the track's existence mass (all of the reachable area looked at and empty -> ~0).
  OCCLUDERS vis(c) in [0, 1], one static map per map (data/belief/<map>.occluders.npz, gitignored,
            client-derived), three routes:
            FRAME (pixels only, the one to use live): recorded frame pairs 0.4 s apart while we
              walk; each tile's floor shift by phase correlation; the residual where the frame does
              not move like the floor (canopy and roofs show parallax, the floor matches); per
              cell, the mean residual inside the body box above its feet -> 1 at the map's median,
              0 at its 97th percentile (``floor_residual``, ``cover_map``);
            BOX RATE (pixels: detector boxes): the box rate per in-view cell against the map mean
              (prt_fild08's spawns are uniform map-wide) -- data-starved: ~1e-3 boxes per in-view
              cell-frame;
            PACKET (an offline artefact, comparison only): the detector's recall of the packets'
              true monsters per cell.
  PROBES    the top-k cells of a hidden track's posterior, SPACED (each >= 2 cells from the
            others, so the 1-cell hover tolerance does not overlap); HOVER probes = the same
            restricted to the cells drawn on screen now (only those can show the SWORD).

MEASURED 2026-10-17 (``eval``, leave-one-session-out: kernel and occluders fitted on the OTHER
sessions; hunt-flow18 / 20 / 20 / 21 / 22 on prt_fild08, 53,302 detector frames; "hidden" = alive,
in the 14-cell AOI, unboxed >= 1 s; "tracked" = a track carries its gid; hit = within 1 cell):
  - box -> cell: 91-92 % of labelled boxes within 1 cell of the true cell (p50 0, p90 1).
  - spaced top-3 hit, of tracked hidden samples, pooled (kernel -> ne+lead): 1-2 s 58 -> 66 %,
    2-5 s 45 -> 54 %, 5-10 s 22 -> 26 %, > 10 s 21 -> 19 %. The WALK-ON component is the biggest
    gain (+6 / +10 / +5 points at 1-2 / 2-5 / 5-10 s); negative evidence adds +5 at 1-2 s and helps
    most for monsters that left the screen (off-screen 1-2 s 71 -> 82 %), PD 0.2 > 0.4 > 0.7.
  - on-screen hidden (the hover case), ne+lead with HOVER probes: 57 / 49 / 29 / 23 % (1-2 / 2-5 /
    5-10 / > 10 s).
  - occluders change the hit rate by -1 to +2 points: PACKET route (the offline upper bound) +1-2,
    FRAME route -1 to +1, BOX RATE -1 to +1. The frame route's covered cells are real (recall 0.51-
    0.56 at vis < 0.5 vs 0.79 at vis = 1) but few (156 of 4,540 well-observed cells): the hidden
    samples are mostly detector dropouts and off-screen walks, not static cover.
  - identity through a dropout: 66 % kept, 8 % swapped, 11 % a new track (the old one dropped).
  - cost per frame, one variant, this host at nice 15: update p50 0.26 ms (p95 2.7: the geodesic
    on a new sighting), probes for every hidden track p50 0.27 ms, the full 400 x 400 map 0.40 ms.
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import pickle
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "belief"
CACHE = Path("/dev/shm/poring-lab-tmp/belief")
MAP = "prt_fild08"
NS = 10**9
RADIUS = 20  # cells: the track window's half side (the kernel's support)
CAP_S = 30.0  # a track unseen this long is dropped
REACH_CELLS = 2.0  # association slack on top of the kernel's 95th percentile (box -> cell error)
PD = 0.2  # negative evidence: the per-frame miss weight of a visible cell (tempered: frame misses
#           are correlated -- the detector's raw per-frame recall is ~0.69, search_gap.py;
#           0.2 / 0.4 / 0.7 measured 2026-10-17: 0.2 best or equal in every time bin)
LEAD_CELLS = 2.5  # a track last seen walking: the walk-on cell this far along its heading
LEAD_W = 0.5
HALF_LIFE_S = 2.0  # the log-miss map's half-life
LM_FLOOR = -30.0
KERNEL_T = (0.33, 0.67, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0, 15.0, 20.0, 30.0)
# K(t, d) fitted 2026-10-17 (``belief_map.py occluders``, pooled): the detector's labelled sightings
# -> the packets' true cell at later frames, hunt-flow18 / 20 / 20 / 21 / 22 on prt_fild08 (each
# eval session is re-fitted WITHOUT itself). Rows = KERNEL_T, columns = d 0..RADIUS cells.
DEFAULT_MASS = (
    (0.6817, 0.2821, 0.0336, 0.0015, 0, 0, 0, 0.0012, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    (0.6048, 0.3032, 0.0701, 0.013, 0.0056, 0, 0, 0.0013, 0.002, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
     0),
    (0.531, 0.2797, 0.1364, 0.0386, 0.0104, 0.0034, 0.0005, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
     0, 0),
    (0.4608, 0.2202, 0.1658, 0.0963, 0.0365, 0.0128, 0.0046, 0.0012, 0.0008, 0.0004, 0.0004, 0,
     0, 0, 0, 0, 0, 0, 0, 0, 0),
    (0.3908, 0.1988, 0.135, 0.1213, 0.0896, 0.0435, 0.0121, 0.0075, 0.0003, 0.001, 0, 0, 0, 0, 0,
     0, 0, 0, 0, 0, 0),
    (0.2793, 0.1849, 0.133, 0.1128, 0.1053, 0.0961, 0.0571, 0.0265, 0.0042, 0.0005, 0.0003, 0, 0,
     0, 0, 0, 0, 0, 0, 0, 0),
    (0.1429, 0.1496, 0.1455, 0.1277, 0.1227, 0.1207, 0.1044, 0.0665, 0.0115, 0.0056, 0.0026,
     0.0003, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    (0.0239, 0.1067, 0.1409, 0.1557, 0.1404, 0.1379, 0.1485, 0.1011, 0.0167, 0.0143, 0.0059,
     0.0057, 0.0016, 0.0007, 0, 0, 0, 0, 0, 0, 0),
    (0.0038, 0.034, 0.0908, 0.1152, 0.1444, 0.1519, 0.2027, 0.1611, 0.0394, 0.0211, 0.0103,
     0.011, 0.0081, 0.0033, 0.0015, 0.0006, 0.0006, 0, 0, 0, 0),
    (0.0032, 0.0301, 0.0577, 0.0768, 0.1096, 0.1293, 0.154, 0.1532, 0.0911, 0.062, 0.0478,
     0.0301, 0.0289, 0.0129, 0.0057, 0.0047, 0.0009, 0.0005, 0.0009, 0.0005, 0),
    (0.0048, 0.0313, 0.051, 0.0767, 0.0833, 0.1102, 0.0885, 0.1057, 0.1034, 0.0844, 0.0747,
     0.0553, 0.0479, 0.0282, 0.0173, 0.014, 0.0103, 0.0052, 0.0036, 0.003, 0.0013),
    (0.0029, 0.0277, 0.0447, 0.0538, 0.0704, 0.0712, 0.0821, 0.1086, 0.0986, 0.0786, 0.0752,
     0.0597, 0.057, 0.0479, 0.0298, 0.0253, 0.0186, 0.0119, 0.0066, 0.0066, 0.0229),
    (0.0013, 0.0288, 0.0347, 0.0586, 0.0594, 0.0663, 0.0894, 0.0785, 0.0741, 0.0701, 0.0637,
     0.0726, 0.051, 0.0385, 0.0459, 0.0258, 0.026, 0.0237, 0.0148, 0.0074, 0.0693),
)  # fmt: skip
OCC_PRIOR = 5.0  # occluder shrinkage: pseudo-hits at the map mean rate
HIDDEN_S = 1.0
UNSEEN_BINS = ((1.0, 2.0), (2.0, 5.0), (5.0, 10.0), (10.0, 1e9))
GM_SPRITE = (620.0, 285.0, 660.0, 375.0)  # drop_blobs.GM_BOX: our own drawn sprite (client px)
# ms per cell (data/kb/mobs.json walk_speed): runtime knowledge (ADR-0015). Pupa cannot move.
WALK_MS = {"Poring": 400, "Lunatic": 200, "Drops": 400, "Pupa": None, "Creamy": 150}
Cell = tuple[int, int]
Pt = tuple[float, float]


# --- the grid -------------------------------------------------------------------------------------


def dilate8(m: Any) -> Any:
    """3 x 3 (8-connected) binary dilation."""
    a = np.asarray(m, dtype=bool)
    v = a.copy()
    v[1:, :] |= a[:-1, :]
    v[:-1, :] |= a[1:, :]
    h = v.copy()
    h[:, 1:] |= v[:, :-1]
    h[:, :-1] |= v[:, 1:]
    return h


def geodesic(ok: Any, start: Cell, rmax: int) -> Any:
    """8-connected step distance from ``start`` (x, y) over ``ok`` cells, -1 = unreachable within
    ``rmax``. The start counts even when it is not walkable (a box's cell may be a cell off)."""
    ok = np.asarray(ok, dtype=bool)
    dist = np.full(ok.shape, -1, dtype=np.int16)
    reached = np.zeros(ok.shape, dtype=bool)
    reached[start[1], start[0]] = True
    dist[start[1], start[0]] = 0
    for r in range(1, rmax + 1):
        new = dilate8(reached) & ok & ~reached
        if not new.any():
            break
        dist[new] = r
        reached |= new
    return dist


def snap(ok: Any, c: Pt, within: int = 2) -> Cell:
    """The rounded cell, or the nearest walkable one within ``within`` (Chebyshev) of it."""
    x, y = int(round(c[0])), int(round(c[1]))
    h, w = ok.shape
    if 0 <= x < w and 0 <= y < h and ok[y, x]:
        return x, y
    best: tuple[float, Cell] | None = None
    for dy in range(-within, within + 1):
        for dx in range(-within, within + 1):
            q = (x + dx, y + dy)
            if 0 <= q[0] < w and 0 <= q[1] < h and ok[q[1], q[0]]:
                d = math.hypot(q[0] - c[0], q[1] - c[1])
                if best is None or d < best[0]:
                    best = (d, q)
    return (x, y) if best is None else best[1]


# --- the kernel -----------------------------------------------------------------------------------


@dataclass
class Kernel:
    """K(t, d): the probability that a monster last seen at a cell is at ring distance d (cells)
    after t seconds unseen; rows at ``times``, linear in t between them (t = 0: all at d = 0)."""

    times: tuple[float, ...]
    mass: Any  # (len(times), RADIUS + 1), rows sum to 1

    def ring(self, t_s: float) -> Any:
        ts = self.times
        if t_s <= 0:
            out = np.zeros(self.mass.shape[1])
            out[0] = 1.0
            return out
        if t_s <= ts[0]:
            f = t_s / ts[0]
            out = f * self.mass[0]
            out[0] += 1 - f
            return out
        i = bisect.bisect_right(ts, t_s) - 1
        if i >= len(ts) - 1:
            return self.mass[-1].copy()
        f = (t_s - ts[i]) / (ts[i + 1] - ts[i])
        return (1 - f) * self.mass[i] + f * self.mass[i + 1]

    def quantile(self, t_s: float, q: float) -> int:
        c = np.cumsum(self.ring(t_s))
        return int(np.searchsorted(c, q * c[-1]))

    def to_json(self) -> dict[str, Any]:
        return {"times": list(self.times), "mass": np.round(self.mass, 5).tolist()}

    @classmethod
    def from_json(cls, d: Mapping[str, Any]) -> Kernel:
        return cls(tuple(d["times"]), np.asarray(d["mass"], dtype=float))

    @classmethod
    def default(cls) -> Kernel:
        """The pooled prt_fild08 fit (DEFAULT_MASS), rows renormalised."""
        m = np.asarray(DEFAULT_MASS, dtype=float)
        return cls(KERNEL_T, m / m.sum(axis=1, keepdims=True))


def fit_kernel(samples: Iterable[tuple[float, float]], times: Sequence[float] = KERNEL_T,
               radius: int = RADIUS, floor: float = 1e-3) -> Kernel:  # fmt: skip
    """K from (seconds unseen, Chebyshev cells from the last-seen cell) samples: each sample goes
    to its nearest time row; d is clipped to ``radius``; a ``floor`` share is spread over the
    rings within the row's 99th percentile (an unseen walk is never impossible)."""
    rows = [np.zeros(radius + 1) for _ in times]
    lt = np.log(np.asarray(times))
    for t_s, d in samples:
        if t_s <= 0:
            continue
        i = int(np.argmin(np.abs(lt - math.log(t_s))))
        rows[i][min(radius, int(round(d)))] += 1
    mass = np.zeros((len(times), radius + 1))
    for i, r in enumerate(rows):
        if r.sum() == 0:  # no data: a delta at the last cell (the next row's fit fills in)
            r = np.zeros(radius + 1)
            r[0] = 1.0
        p = r / r.sum()
        q99 = int(np.searchsorted(np.cumsum(p), 0.99)) + 1
        p[: q99 + 1] += floor / (q99 + 1)
        mass[i] = p / p.sum()
    return Kernel(tuple(times), mass)


# --- tracks and the map ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Variant:
    """One negative-evidence setting: ``pd`` = 0 is the kernel alone; ``vis`` an occluder map."""

    name: str
    pd: float = 0.0
    half_life_s: float = HALF_LIFE_S
    vis: Any = None  # full-grid float [0, 1] or None (every visible cell fully informative)
    lead: float = 0.0  # the weight of the WALK-ON component for a track last seen walking


@dataclass
class Track:
    tid: int
    cell: Pt  # last-seen (fractional) cell
    t: int  # last-seen time (ns)
    n: int = 1
    species: str | None = None
    label: int = -1  # OFFLINE only: the packets' gid of the last associated box (scoring)
    x0: int = 0
    y0: int = 0
    dist: Any = None
    ring_n: Any = None
    lm: dict[str, Any] = field(default_factory=dict)
    t_ne: int = 0  # the last negative-evidence time
    hist: list[tuple[int, Pt]] = field(default_factory=list)  # recent sightings (t, cell)
    lead_dist: Any = None  # geodesic distance from the walk-on cell (None: not seen walking)
    lead_n: Any = None


class BeliefMap:
    """The tracks and their beliefs on one map's walkable grid ``ok`` (H x W bool)."""

    def __init__(self, ok: Any, kernel: Kernel, variants: Sequence[Variant],
                 radius: int = RADIUS, cap_s: float = CAP_S,
                 reach_cells: float = REACH_CELLS) -> None:  # fmt: skip
        self.ok = np.asarray(ok, dtype=bool)
        self.kernel = kernel
        self.variants = list(variants)
        self.radius = radius
        self.cap_ns = int(cap_s * NS)
        self.reach = reach_cells
        self.tracks: dict[int, Track] = {}
        self._next = 0
        self._lead = {v.name: v.lead for v in self.variants}
        self._q95 = {round(t, 2): kernel.quantile(t, 0.95) for t in np.arange(0, cap_s + 0.5, 0.1)}

    # -- sightings --

    def _seed(self, tr: Track) -> None:
        r, (h, w) = self.radius, self.ok.shape
        c = snap(self.ok, tr.cell)
        x0, y0 = max(0, c[0] - r), max(0, c[1] - r)
        x1, y1 = min(w, c[0] + r + 1), min(h, c[1] + r + 1)
        tr.x0, tr.y0 = x0, y0
        tr.dist = geodesic(self.ok[y0:y1, x0:x1], (c[0] - x0, c[1] - y0), r)
        tr.ring_n = np.bincount(tr.dist[tr.dist >= 0].ravel(), minlength=r + 1).astype(float)
        tr.lm = {v.name: np.zeros(tr.dist.shape) for v in self.variants if v.pd > 0}
        tr.hist = [*tr.hist, (tr.t, tr.cell)][-8:]
        tr.lead_dist = tr.lead_n = None
        hd = heading(tr.hist)
        if hd is not None:
            lc = snap(self.ok, (tr.cell[0] + LEAD_CELLS * hd[0], tr.cell[1] + LEAD_CELLS * hd[1]))
            lx, ly = lc[0] - x0, lc[1] - y0
            if 0 <= lx < x1 - x0 and 0 <= ly < y1 - y0 and tr.dist[ly, lx] >= 0:
                tr.lead_dist = geodesic(self.ok[y0:y1, x0:x1], (lx, ly), r)
                tr.lead_n = np.bincount(tr.lead_dist[tr.lead_dist >= 0].ravel(),
                                        minlength=r + 1).astype(float)  # fmt: skip

    def reach_of(self, dt_s: float) -> float:
        return self.reach + self._q95.get(round(min(dt_s, self.cap_ns / NS), 1), self.radius)

    def associate(self, t: int, dets: Sequence[Pt]) -> list[tuple[int, int, bool]]:
        """Greedy nearest-first one-to-one: [(det index, track id, new track)]."""
        pairs = []
        for i, c in enumerate(dets):
            for tr in self.tracks.values():
                d = max(abs(c[0] - tr.cell[0]), abs(c[1] - tr.cell[1]))
                if d <= self.reach_of((t - tr.t) / NS):
                    pairs.append((d, -tr.t, i, tr.tid))
        pairs.sort()
        out: list[tuple[int, int, bool]] = []
        used_d: set[int] = set()
        used_t: set[int] = set()
        for _d, _nt, i, tid in pairs:
            if i in used_d or tid in used_t:
                continue
            used_d.add(i)
            used_t.add(tid)
            out.append((i, tid, False))
        for i in range(len(dets)):
            if i not in used_d:
                tid = self._next
                self._next += 1
                self.tracks[tid] = Track(tid, dets[i], t, t_ne=t)
                self._seed(self.tracks[tid])
                out.append((i, tid, True))
        for i, tid, new in out:
            if not new:
                tr = self.tracks[tid]
                tr.cell, tr.t, tr.n, tr.t_ne = dets[i], t, tr.n + 1, t
                self._seed(tr)
        return out

    def update(self, t: int, dets: Sequence[Pt],
               visible: Any = None) -> list[tuple[int, int, bool]]:  # fmt: skip
        """One frame: associate ``dets`` (fractional cells), drop stale tracks, then the
        negative evidence of ``visible`` (full-grid bool, None = no view information) on every
        track not seen in this frame."""
        for tid in [k for k, tr in self.tracks.items() if t - tr.t > self.cap_ns]:
            del self.tracks[tid]
        out = self.associate(t, dets)
        if visible is None:
            return out
        seen = {tid for _i, tid, _n in out}
        near = np.zeros(self.ok.shape, dtype=bool)
        h, w = self.ok.shape
        for c in dets:
            x, y = int(round(c[0])), int(round(c[1]))
            near[max(0, y - 1) : min(h, y + 2), max(0, x - 1) : min(w, x + 2)] = True
        info = np.asarray(visible, dtype=bool) & ~near
        for tr in self.tracks.values():
            if tr.tid in seen:
                continue
            dt = (t - tr.t_ne) / NS
            tr.t_ne = t
            ys, xs = slice(tr.y0, tr.y0 + tr.dist.shape[0]), slice(tr.x0, tr.x0 + tr.dist.shape[1])
            sub = info[ys, xs]
            for v in self.variants:
                if v.pd <= 0:
                    continue
                lm = tr.lm[v.name]
                lm *= 0.5 ** (dt / v.half_life_s)
                if sub.any():
                    pd = v.pd if v.vis is None else v.pd * v.vis[ys, xs][sub]
                    lm[sub] += np.log1p(-np.minimum(pd, 0.999))
                    np.maximum(lm, LM_FLOOR, out=lm)
        return out

    # -- beliefs --

    def posterior(self, tr: Track, t: int, variant: str) -> tuple[Any, float]:
        """(p over the track's window, normalised; existence mass in [0, 1])."""
        ring = self.kernel.ring((t - tr.t) / NS)
        prior = spread(ring, tr.dist, tr.ring_n)
        w = self._lead.get(variant, 0.0)
        if w > 0 and tr.lead_dist is not None:
            prior = (1 - w) * prior + w * spread(ring, tr.lead_dist, tr.lead_n)
        lm = tr.lm.get(variant)
        post = prior if lm is None else prior * np.exp(lm)
        m = float(post.sum())
        return (post / m if m > 0 else post), m

    def probes(self, tr: Track, t: int, variant: str, k: int = 3, spaced: bool = True
               ) -> list[Cell]:  # fmt: skip
        """The top-k cells (absolute) of the track's posterior; ``spaced``: each >= 2 cells from
        the ones before it."""
        p, _m = self.posterior(tr, t, variant)
        return top_cells(p, k, spaced, (tr.x0, tr.y0))

    def grid(self, t: int, variant: str) -> Any:
        """The map-wide belief: the expected number of monsters per cell (existence-weighted)."""
        g = np.zeros(self.ok.shape)
        for tr in self.tracks.values():
            p, m = self.posterior(tr, t, variant)
            g[tr.y0 : tr.y0 + p.shape[0], tr.x0 : tr.x0 + p.shape[1]] += m * p
        return g


def spread(ring: Any, dist: Any, ring_n: Any) -> Any:
    """Each ring's mass spread evenly over its walkable cells (a window of geodesic distances)."""
    per = np.where(ring_n > 0, ring / np.maximum(ring_n, 1), 0.0)
    return np.where(dist >= 0, per[np.maximum(dist, 0)], 0.0)


def heading(hist: Sequence[tuple[int, Pt]], span_s: tuple[float, float] = (0.5, 1.5),
            min_cells: float = 1.5) -> Pt | None:  # fmt: skip
    """The unit walking direction from the sightings (t, cell): the newest against the oldest one
    ``span_s`` before it, when it moved at least ``min_cells`` (Chebyshev); else None (standing,
    or too little history -- box -> cell noise is about a cell)."""
    if len(hist) < 2:
        return None
    t1, c1 = hist[-1]
    for t0, c0 in hist[:-1]:
        dt = (t1 - t0) / NS
        if span_s[0] <= dt <= span_s[1]:
            dx, dy = c1[0] - c0[0], c1[1] - c0[1]
            if max(abs(dx), abs(dy)) < min_cells:
                return None
            n = math.hypot(dx, dy)
            return dx / n, dy / n
    return None


def top_cells(p: Any, k: int, spaced: bool, origin: Cell = (0, 0)) -> list[Cell]:
    p = np.asarray(p, dtype=float)
    if not spaced:
        flat = np.argsort(-p, axis=None, kind="stable")[:k]
        return [(int(i % p.shape[1]) + origin[0], int(i // p.shape[1]) + origin[1])
                for i in flat if p.flat[i] > 0]  # fmt: skip
    q = p.copy()
    out: list[Cell] = []
    for _ in range(k):
        i = int(np.argmax(q))
        if q.flat[i] <= 0:
            break
        y, x = divmod(i, q.shape[1])
        out.append((x + origin[0], y + origin[1]))
        q[max(0, y - 1) : y + 2, max(0, x - 1) : x + 2] = 0.0
    return out


def box3(a: Any) -> Any:
    """3 x 3 box sum (zero padded)."""
    a = np.asarray(a, dtype=float)
    p = np.pad(a, 1)
    return sum(p[dy : dy + a.shape[0], dx : dx + a.shape[1]] for dy in range(3) for dx in range(3))


def occluder_map(n_obs: Any, n_hit: Any, prior_hits: float = OCC_PRIOR) -> Any:
    """vis(c) in [0, 1]: the hit rate per observation at each cell (3 x 3 pooled, shrunk to the
    map mean by ``prior_hits`` pseudo-hits at the mean rate) over the map mean. BOX-RATE route:
    n_obs = frames the cell was in view, n_hit = boxes on it; PACKET route: n_obs = true monsters
    in view on it, n_hit = those boxed."""
    no, nh = box3(n_obs), box3(n_hit)
    tot = float(np.asarray(n_obs).sum())
    mean = float(np.asarray(n_hit).sum()) / tot if tot > 0 else 0.0
    if mean <= 0:
        return np.ones(np.asarray(n_obs).shape)
    rate = (nh + prior_hits) / (no + prior_hits / mean)
    return np.clip(rate / mean, 0.0, 1.0)


# --- the FRAME route occluder (pixels only): where the floor does not move like the floor ---------

BODY_BOX = (-12, -44, 12, -4)  # client px around a monster's feet: the body a cover would hide
BODY_HALF = (-6, -22, 6, -2)  # the same at the residual's half resolution
FLOOR_TILES = (6, 4)  # rows x cols: one floor shift per tile (the perspective gradient)
MIN_SHIFT_PX = 10.0  # a pair says nothing about cover unless the floor moved this much
MAX_SHIFT_PX = 90


def floor_residual(a: Any, b: Any, mask: Any, tiles: tuple[int, int] = FLOOR_TILES,
                   max_shift: int = MAX_SHIFT_PX, scale: int = 2) -> tuple[Any, float]:  # fmt: skip
    """Per pixel of frame ``b`` (grey, 1 / ``scale`` resolution): how badly it matches frame ``a``
    moved by its tile's FLOOR shift (phase correlation per tile; ``mask`` = pixels to ignore,
    e.g. static UI, our own sprite): min over a 1-px slack of |diff|. The floor matches; whatever
    is drawn above it (canopy, roofs: parallax), sprites and animation do not. (residual at
    1 / scale, the median tile shift in full-resolution px)."""
    from drop_blobs import phase_shift

    ga = np.asarray(a, np.float32)[::scale, ::scale].mean(-1)
    gb = np.asarray(b, np.float32)[::scale, ::scale].mean(-1)
    keep = ~np.asarray(mask, dtype=bool)[::scale, ::scale]
    h, w = gb.shape
    res = np.zeros((h, w), dtype=np.float32)
    mags = []
    ty, tx = tiles
    for i in range(ty):
        for j in range(tx):
            y0, y1 = i * h // ty, (i + 1) * h // ty
            x0, x1 = j * w // tx, (j + 1) * w // tx
            ka = keep[y0:y1, x0:x1]
            if ka.mean() < 0.5:
                continue
            ta, tb = ga[y0:y1, x0:x1].copy(), gb[y0:y1, x0:x1].copy()
            ta[~ka], tb[~ka] = ta[ka].mean(), tb[ka].mean()
            dy, dx = phase_shift(ta, tb, max(1, max_shift // scale))  # b[y, x] ~ a[y+dy, x+dx]
            mags.append(scale * math.hypot(dy, dx))
            best = None
            for ey in (-1, 0, 1):
                for ex in (-1, 0, 1):
                    ys = np.clip(np.arange(y0, y1) + dy + ey, 0, h - 1)
                    xs = np.clip(np.arange(x0, x1) + dx + ex, 0, w - 1)
                    d = np.abs(gb[y0:y1, x0:x1] - ga[np.ix_(ys, xs)])
                    best = d if best is None else np.minimum(best, d)
            res[y0:y1, x0:x1] = best
    return res, float(np.median(mags)) if mags else 0.0


def box_means(values: Any, valid: Any, uv: Any, box: tuple[int, int, int, int] = BODY_BOX,
              min_valid: float = 0.5) -> Any:  # fmt: skip
    """Mean of ``values`` over the ``valid`` pixels of each feet point's body box (integral
    images); NaN where under ``min_valid`` of the box is valid or it leaves the image."""
    v = np.where(valid, values, 0).astype(np.float64)
    ii = np.pad(v.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    ci = np.pad(np.asarray(valid, np.float64).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    h, w = v.shape
    pts = np.atleast_2d(np.asarray(uv, dtype=float))
    x0 = np.round(pts[:, 0] + box[0]).astype(int)
    x1 = np.round(pts[:, 0] + box[2]).astype(int)
    y0 = np.round(pts[:, 1] + box[1]).astype(int)
    y1 = np.round(pts[:, 1] + box[3]).astype(int)
    inside = (x0 >= 0) & (y0 >= 0) & (x1 <= w) & (y1 <= h)
    x0, x1 = np.clip(x0, 0, w), np.clip(x1, 0, w)
    y0, y1 = np.clip(y0, 0, h), np.clip(y1, 0, h)

    def rect(t: Any) -> Any:
        return t[y1, x1] - t[y0, x1] - t[y1, x0] + t[y0, x0]

    n = rect(ci)
    area = np.maximum((x1 - x0) * (y1 - y0), 1)
    ok = inside & (n >= min_valid * area)
    out = np.full(len(pts), np.nan)
    out[ok] = rect(ii)[ok] / n[ok]
    return out


def cover_map(n_obs: Any, s_sum: Any, min_obs: float = 5.0, lo_q: float = 50.0,
              hi_q: float = 97.0) -> Any:  # fmt: skip
    """vis(c) in [0, 1] from the FRAME route's accumulated body-box residuals: 3 x 3 pooled mean;
    at or below the map's ``lo_q`` percentile = 1 (floor-like), at ``hi_q`` and above = 0;
    cells with fewer than ``min_obs`` pooled observations = 1 (unknown is not hidden)."""
    no, ss = box3(n_obs), box3(s_sum)
    m = np.where(no >= min_obs, ss / np.maximum(no, 1), np.nan)
    if not np.isfinite(m).any():
        return np.ones(np.asarray(n_obs).shape)
    lo, hi = np.nanpercentile(m, lo_q), np.nanpercentile(m, hi_q)
    vis = 1.0 - np.clip((m - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    return np.where(np.isfinite(m), vis, 1.0)


def frame_cover_counts(sid: str, prep: Mapping[str, Any], gap: int = 2, stride: int = 8,
                       refresh: bool = False) -> tuple[Any, Any, dict[str, Any]]:  # fmt: skip
    """The FRAME route's per-cell counts for one session (cached in /dev/shm): recorded frames
    (the NAS hunt-recordings, 5 Hz) k and k + ``gap``, every ``stride``-th k; our cell = the
    packets' stand-in for odometry (as everywhere offline); detector boxes near either frame and
    the static UI masked."""
    cp = CACHE / f"cover-{sid}.npz"
    if cp.exists() and not refresh:
        z = np.load(cp)
        return z["n_obs"], z["s_sum"], json.loads(str(z["info"]))
    import search_gap as sg
    from drop_blobs import Projector, load_frames, read_rgb
    from route_preview import UI_WINDOWS

    frames = load_frames(sid)
    rows = prep["rows"]
    rt = [r["t"] for r in rows]
    _d, man, events, boxf = sg.load(sid)
    bt = [f[0] for f in boxf]
    world = sg.build_world(events)
    proj = Projector(man.get("map", MAP))
    lag = int(sg.LAG_S * NS)
    shape = prep["shape"]
    n_obs = np.zeros(shape, np.float64)
    s_sum = np.zeros(shape, np.float64)
    base = np.zeros((720, 1280), dtype=bool)
    for x0, y0, x1, y1 in [*UI_WINDOWS, GM_SPRITE]:
        base[int(y0) : int(y1) + 1, int(x0) : int(x1) + 1] = True
    offs = _view_offsets()
    used = skipped = 0
    t_start = time.time()

    def boxes_near(t: int) -> list[list[Any]]:
        i = bisect.bisect_left(bt, t)
        best = [k for k in (i - 1, i) if 0 <= k < len(bt) and abs(bt[k] - t) <= NS // 4]
        return [b for k in best for b in boxf[k][1]]

    for k in range(0, len(frames) - gap, stride):
        (ta, pa), (tb, pb) = frames[k], frames[k + gap]
        here, was = world.gm.at(tb - lag), world.gm.at(ta - lag)
        if here is None or was is None or not rows or tb < rt[0] or tb > rt[-1]:
            continue
        if max(abs(here[0] - was[0]), abs(here[1] - was[1])) < 0.5:  # still: no parallax
            skipped += 1
            continue
        mask = base.copy()
        for bx in boxes_near(ta) + boxes_near(tb):
            y0_, x0_ = max(0, int(bx[1]) - 8), max(0, int(bx[0]) - 8)
            mask[y0_ : int(bx[3]) + 9, x0_ : int(bx[2]) + 9] = True
        try:
            a, b = read_rgb(pa), read_rgb(pb)
        except OSError:
            skipped += 1
            continue
        res, mag = floor_residual(a, b, mask)
        if mag < MIN_SHIFT_PX:
            skipped += 1
            continue
        r0 = (int(round(here[0])), int(round(here[1])))
        cells = offs + np.asarray(r0, dtype=float)
        px = proj.project(here, cells)
        vis = visible_px(px, [*UI_WINDOWS, GM_SPRITE])
        sc = box_means(res, ~mask[::2, ::2], px[vis] / 2, BODY_HALF)
        cc = cells[vis].astype(int)
        good = np.isfinite(sc) & (cc[:, 0] >= 0) & (cc[:, 0] < shape[1]) \
            & (cc[:, 1] >= 0) & (cc[:, 1] < shape[0])  # fmt: skip
        np.add.at(n_obs, (cc[good, 1], cc[good, 0]), 1.0)
        np.add.at(s_sum, (cc[good, 1], cc[good, 0]), sc[good])
        used += 1
    info = {"pairs": used, "skipped": skipped, "frames": len(frames),
            "wall_s": round(time.time() - t_start, 1)}  # fmt: skip
    CACHE.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cp, n_obs=n_obs, s_sum=s_sum, info=json.dumps(info))
    return n_obs, s_sum, info


# --- offline: one session prepared (packets = ground truth, scoring only) -------------------------


SCREEN = (1280, 720)
EDGE = (8.0, 24.0, 8.0, 4.0)  # search_gap.EDGE: left, top, right, bottom margins for drawn feet
BODY_UP_PX = 20.0  # search_gap.BODY_UP_PX: the body centre above the feet (the UI test)


def visible_px(px: Any, windows: Iterable[tuple[float, float, float, float]]) -> Any:
    """Vectorised search_gap.on_screen(feet) and not under_ui(body): (N, 2) px -> (N,) bool."""
    a = np.atleast_2d(np.asarray(px, dtype=float))
    if a.size == 0:
        return np.zeros(0, dtype=bool)
    u, v = a[:, 0], a[:, 1]
    ok = (u >= EDGE[0]) & (u <= SCREEN[0] - EDGE[2]) & (v >= EDGE[1]) & (v <= SCREEN[1] - EDGE[3])
    vb = v - BODY_UP_PX
    for x0, y0, x1, y1 in windows:
        ok &= ~((u >= x0) & (u <= x1) & (vb >= y0) & (vb <= y1))
    return ok


def _view_offsets(r: int = 27) -> Any:
    return np.array([(dx, dy) for dy in range(-r, r + 1) for dx in range(-r, r + 1)], dtype=float)


def prepare(sid: str, refresh: bool = False) -> dict[str, Any]:
    """Per detector frame: our GM's cell (packets: the stand-in for minimap + odometry), each box's
    cell (pixels + camera), the box's packet gid (scoring), the true monsters in the AOI, and the
    visible-cell set; per session: the occluder counts. Cached in /dev/shm."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cp = CACHE / f"prep-{sid}.pkl"
    if cp.exists() and not refresh:
        with cp.open("rb") as fh:
            out: dict[str, Any] = pickle.load(fh)
            return out
    import loot1
    import search_gap as sg
    from drop_blobs import Projector
    from route_preview import UI_WINDOWS

    from poring_dataset import picking

    d, man, events, frames = sg.load(sid)
    world = sg.build_world(events)
    proj = Projector(man.get("map", MAP))
    lag = int(sg.LAG_S * NS)
    offs = _view_offsets()
    uis = [*UI_WINDOWS, GM_SPRITE]
    shape = (proj.gat.height, proj.gat.width)
    n_view = np.zeros(shape, np.int32)
    n_box = np.zeros(shape, np.int32)
    n_true = np.zeros(shape, np.int32)
    n_thit = np.zeros(shape, np.int32)
    rows: list[dict[str, Any]] = []
    calib_du: list[float] = []
    calib_dv: list[float] = []
    for tf, boxes in frames:
        td = tf - lag
        here = world.gm.at(td)
        if here is None:
            continue
        r0 = (int(round(here[0])), int(round(here[1])))
        frac = (here[0] - r0[0], here[1] - r0[1])
        # visible cells: the feet on screen, the body not under a static window / our sprite
        cells = offs + np.asarray(r0, dtype=float)
        px = proj.project(here, cells)
        vis = visible_px(px, uis)
        vc = cells[vis].astype(int)
        vc = vc[(vc[:, 0] >= 0) & (vc[:, 0] < shape[1]) & (vc[:, 1] >= 0) & (vc[:, 1] < shape[0])]
        n_view[vc[:, 1], vc[:, 0]] += 1
        feet = [((b[0] + b[2]) / 2, float(b[3])) for b in boxes]
        bcell: list[Pt | None] = []
        if feet:
            o = picking.pick_cells(proj.camera, proj.gat, r0,
                                   np.array([[u, v - loot1.FOOT_LIFT] for u, v in feet])
                                   )  # fmt: skip
            for ox, oy in o:
                if abs(int(ox)) > 1000:
                    bcell.append(None)
                    continue
                c = (r0[0] + int(ox) + frac[0], r0[1] + int(oy) + frac[1])
                bcell.append(c)
                cx, cy = int(round(c[0])), int(round(c[1]))
                if 0 <= cx < shape[1] and 0 <= cy < shape[0]:
                    n_box[cy, cx] += 1
        truth = []
        gids = [g for g in world.mobs if world.alive_at(g, td)]
        for g in gids:
            p = world.mobs[g].at(td)
            if p is None or max(abs(p[0] - here[0]), abs(p[1] - here[1])) > sg.AOI + 0.5:
                continue
            truth.append((g, p))
        tpx = proj.project(here, [p for _g, p in truth]) if truth else np.zeros((0, 2))
        tview = [bool(x) for x in visible_px(tpx, uis)]
        for (u, v), ok_ in zip(tpx, tview, strict=True):
            if ok_:
                m = sg.greedy_match([(float(u), float(v))], feet, sg.CALIB_PX)
                if 0 in m:
                    j = m[0][0]
                    calib_du.append(feet[j][0] - float(u))
                    calib_dv.append(feet[j][1] - float(v))
        rows.append({"t": tf, "gm": here, "feet": feet, "cells": bcell, "truth": truth,
                     "tpx": tpx, "tview": tview, "vis": np.packbits(vis)})  # fmt: skip
    off = (float(np.median(calib_du)) if calib_du else 0.0,
           float(np.median(calib_dv)) if calib_dv else 0.0)  # fmt: skip
    # the box labels: the packets' projection + the measured offset, greedy within MATCH_PX
    for r_ in rows:
        r_["label"] = [-1] * len(r_["feet"])
        r_["boxed"] = set()
        ks = [k for k, ok_ in enumerate(r_["tview"]) if ok_]
        pts = [(float(r_["tpx"][k][0]) + off[0], float(r_["tpx"][k][1]) + off[1]) for k in ks]
        for i, (j, _dd) in sg.greedy_match(pts, r_["feet"], sg.MATCH_PX).items():
            g = r_["truth"][ks[i]][0]
            r_["label"][j] = g
            r_["boxed"].add(g)
        for k in ks:
            g, p = r_["truth"][k]
            cx, cy = int(round(p[0])), int(round(p[1]))
            if 0 <= cx < shape[1] and 0 <= cy < shape[0]:
                n_true[cy, cx] += 1
                n_thit[cy, cx] += g in r_["boxed"]
        del r_["tpx"]
    engaged: dict[int, list[int]] = defaultdict(list)
    for e in events:
        typ = e.get("type")
        if (typ == "attack_request" or (typ == "act" and e.get("src_gid") == sg.GM)) \
                and e.get("target_gid") is not None:  # fmt: skip
            engaged[int(e["target_gid"])].append(int(e["t_mono_ns"]))
    kills = sum(1 for e in events if e.get("type") == "entity_vanish"
                and int(e.get("reason", -1)) == 1 and int(e["gid"]) in engaged)  # fmt: skip
    modes: list[tuple[int, str]] = []
    if (d / "events.jsonl").exists():
        for line in (d / "events.jsonl").read_text().splitlines():
            x = json.loads(line)
            if x.get("kind") == "mode":
                modes.append((int(x["t_ns"]), str(x["mode"])))
    out = {"sid": sid, "rows": rows, "offset_px": off, "n_view": n_view, "n_box": n_box,
           "n_true": n_true, "n_thit": n_thit, "engaged": dict(engaged), "kills": kills,
           "modes": sorted(modes), "job": dict(world.job), "shape": shape}  # fmt: skip
    with cp.open("wb") as fh:
        pickle.dump(out, fh)
    return out


def kernel_samples(prep: Mapping[str, Any], per_box: int = 6, max_s: float = 32.0,
                   seed: int = 0) -> list[tuple[float, float]]:  # fmt: skip
    """(seconds since a labelled box, Chebyshev cells from that box's cell to the gid's true cell)
    at up to ``per_box`` random later frames while the gid stays in the AOI."""
    rng = np.random.default_rng(seed)
    rows = prep["rows"]
    ts = [r["t"] for r in rows]
    where: dict[int, dict[int, Pt]] = defaultdict(dict)  # gid -> {row index: true cell}
    for k, r in enumerate(rows):
        for g, p in r["truth"]:
            where[g][k] = p
    out = []
    for k, r in enumerate(rows):
        for c, g in zip(r["cells"], r["label"], strict=True):
            if c is None or g < 0:
                continue
            k1 = bisect.bisect_right(ts, r["t"] + int(max_s * NS))
            if k1 <= k + 1:
                continue
            for kk in rng.integers(k + 1, k1, size=per_box):
                p = where[g].get(int(kk))
                if p is not None:
                    out.append(((ts[kk] - r["t"]) / NS,
                                max(abs(p[0] - c[0]), abs(p[1] - c[1]))))  # fmt: skip
    return out


# --- offline: the validation run ------------------------------------------------------------------


def _bin(unseen_s: float) -> str:
    for a, b in UNSEEN_BINS:
        if a <= unseen_s < b:
            return f"{a:g}-{b:g}s" if b < 1e8 else f">{a:g}s"
    return "<1s"


def _mode_at(modes: Sequence[tuple[int, str]], t: int) -> str:
    i = bisect.bisect_right([m[0] for m in modes], t) - 1
    return modes[i][1] if i >= 0 else "?"


def run(prep: Mapping[str, Any], ok: Any, kernel: Kernel, variants: Sequence[Variant],
        ks: Sequence[int] = (1, 3, 5), false_every: int = 3) -> dict[str, Any]:  # fmt: skip
    """Replays one session's frames through a BeliefMap and scores it against the packets."""
    bm = BeliefMap(ok, kernel, variants)
    offs = _view_offsets().astype(int)
    shape = prep["shape"]
    names = [v.name for v in variants]
    hits: dict[tuple[str, str, int, int, bool], int] = Counter()  # (variant, bin, k, r, spaced)
    n_where: Counter[tuple[str, str]] = Counter()  # (bin, in | off screen)
    n_where_t: Counter[tuple[str, str]] = Counter()
    where3: Counter[tuple[str, str, str]] = Counter()  # spaced top-3 <= 1 cell, by where
    hover: Counter[tuple[str, str, str]] = Counter()  # the same with on-screen probes only
    n_hidden: Counter[str] = Counter()
    n_tracked: Counter[str] = Counter()
    never_seen = 0
    last_boxed: dict[int, int] = {}
    ident = Counter()
    false_mass: dict[str, list[float]] = {n: [0.0, 0.0, 0.0] for n in names}  # false, own, total
    episodes: dict[int, dict[str, Any]] = {}
    done_eps: list[dict[str, Any]] = []
    cost_ms: list[float] = []
    grid_ms: list[float] = []
    n_tracks: list[int] = []
    modes = prep["modes"]
    rows = prep["rows"]
    for fi, r in enumerate(rows):
        t = r["t"]
        here = r["gm"]
        r0 = (int(round(here[0])), int(round(here[1])))
        vis = np.unpackbits(r["vis"])[: len(offs)].astype(bool)
        vc = offs[vis] + np.asarray(r0)
        vc = vc[(vc[:, 0] >= 0) & (vc[:, 0] < shape[1]) & (vc[:, 1] >= 0) & (vc[:, 1] < shape[0])]
        visible = np.zeros(shape, dtype=bool)
        visible[vc[:, 1], vc[:, 0]] = True
        idx = [i for i, c in enumerate(r["cells"]) if c is not None]
        dets = [r["cells"][i] for i in idx]
        before = {tid: (tr.label, tr.t) for tid, tr in bm.tracks.items()}
        t0c = time.perf_counter()
        assoc = bm.update(t, dets, visible)
        cost_ms.append((time.perf_counter() - t0c) * 1e3)
        n_tracks.append(len(bm.tracks))
        # identity through dropouts (labels are OFFLINE scoring only)
        own: dict[int, list[int]] = defaultdict(list)
        for tid, (lab, _tt) in before.items():
            if lab >= 0 and tid in bm.tracks:
                own[lab].append(tid)
        for j, tid, new in assoc:
            g = r["label"][idx[j]]
            if g >= 0 and t - last_boxed.get(g, t) >= HIDDEN_S * NS:
                if not new and before[tid][0] == g:
                    ident["kept"] += 1
                elif not new and before[tid][0] >= 0:
                    ident["swapped"] += 1
                elif new and own.get(g):
                    ident["new_track_old_alive"] += 1
                elif new:
                    ident["new_track_old_dropped"] += 1
                else:
                    ident["unlabelled_track"] += 1
            if g >= 0:  # an unlabelled box (no packet monster within MATCH_PX) keeps the label
                bm.tracks[tid].label = g
        for g in r["boxed"]:
            last_boxed[g] = t
        # hidden monsters: alive, in the AOI, not boxed >= HIDDEN_S
        by_label: dict[int, Track] = {}
        for tr in bm.tracks.values():
            if tr.label >= 0 and (tr.label not in by_label or tr.t > by_label[tr.label].t):
                by_label[tr.label] = tr
        alive_now = {g for g, _p in r["truth"]}
        for g in list(episodes):
            if g not in alive_now or g in r["boxed"]:
                done_eps.append(episodes.pop(g))
        for (g, p), inview in zip(r["truth"], r["tview"], strict=True):
            if g in r["boxed"]:
                continue
            lb = last_boxed.get(g)
            if lb is None:
                never_seen += 1
                continue
            unseen = (t - lb) / NS
            if unseen < HIDDEN_S:
                continue
            b = _bin(unseen)
            wh = "in" if inview else "off"  # the true feet on screen, the body clear of the UI
            n_hidden[b] += 1
            n_where[(b, wh)] += 1
            tr = by_label.get(g)
            ep = episodes.setdefault(g, {"g": g, "t0": t, "t1": t, "hit": {}, "mode": {},
                                         "hover": {}, "hover_mode": {}})  # fmt: skip
            ep["t1"] = t
            if tr is None:
                continue
            n_tracked[b] += 1
            n_where_t[(b, wh)] += 1
            true = (int(round(p[0])), int(round(p[1])))
            ys = slice(tr.y0, tr.y0 + tr.dist.shape[0])
            xs = slice(tr.x0, tr.x0 + tr.dist.shape[1])
            for v in names:
                post, _m = bm.posterior(tr, t, v)
                # HOVER probes: the spaced top-3 among the cells drawn on screen right now
                sc = top_cells(post * visible[ys, xs], 3, True, (tr.x0, tr.y0))
                sd = min((max(abs(c[0] - true[0]), abs(c[1] - true[1])) for c in sc), default=99)
                if sd <= 1:
                    hover[(v, b, wh)] += 1
                    if v not in ep["hover"]:
                        ep["hover"][v] = t
                        ep["hover_mode"][v] = _mode_at(modes, t)
                any3 = min((max(abs(c[0] - true[0]), abs(c[1] - true[1]))
                            for c in top_cells(post, 3, True, (tr.x0, tr.y0))),
                           default=99)  # fmt: skip
                where3[(v, b, wh)] += any3 <= 1
                for spaced in (False, True):
                    cells = top_cells(post, max(ks), spaced, (tr.x0, tr.y0))
                    dd = [max(abs(c[0] - true[0]), abs(c[1] - true[1])) for c in cells]
                    for k in ks:
                        best = min(dd[:k], default=99)
                        for rr in (0, 1):
                            hits[(v, b, k, rr, spaced)] += best <= rr
                    if spaced and min(dd[:3], default=99) <= 1 and v not in ep["hit"]:
                        ep["hit"][v] = t
                        ep["mode"][v] = _mode_at(modes, t)
        # false belief: mass on cells (in the AOI) with no true monster within 1 cell
        if fi % false_every == 0 and bm.tracks:
            occ = np.zeros(shape, dtype=bool)
            for _g, p in r["truth"]:
                x, y = int(round(p[0])), int(round(p[1]))
                occ[max(0, y - 1) : y + 2, max(0, x - 1) : x + 2] = True
            aoi = np.zeros(shape, dtype=bool)
            aoi[max(0, r0[1] - 14) : r0[1] + 15, max(0, r0[0] - 14) : r0[0] + 15] = True
            truth_of = dict(r["truth"])
            for v in names:
                t0g = time.perf_counter()
                for tr in bm.tracks.values():
                    if t - tr.t < HIDDEN_S * NS:
                        continue
                    post, m = bm.posterior(tr, t, v)
                    ys = slice(tr.y0, tr.y0 + post.shape[0])
                    xs = slice(tr.x0, tr.x0 + post.shape[1])
                    w = m * post * aoi[ys, xs]
                    tot = float(w.sum())
                    false_mass[v][2] += tot
                    false_mass[v][0] += float((w * ~occ[ys, xs]).sum())
                    tp = truth_of.get(tr.label)
                    if tp is not None:
                        x, y = int(round(tp[0])) - tr.x0, int(round(tp[1])) - tr.y0
                        false_mass[v][1] += float(w[max(0, y - 1) : y + 2,
                                                    max(0, x - 1) : x + 2].sum())  # fmt: skip
                if v == names[-1]:
                    grid_ms.append((time.perf_counter() - t0g) * 1e3)
    done_eps.extend(episodes.values())
    span_s = (rows[-1]["t"] - rows[0]["t"]) / NS if rows else 0.0
    per10 = 600.0 / span_s if span_s else 0.0
    opp: dict[str, dict[str, float]] = {}
    eng = prep["engaged"]
    for v in names:
        n_all = n_never = n_search = n_hover = n_hover_search = 0
        for ep in done_eps:
            ts = eng.get(ep["g"], [])
            if any(ep["t0"] - NS <= x <= ep["t1"] + 2 * NS for x in ts):  # engaged in it
                continue
            if ep["hover"].get(v) is not None:
                n_hover += 1
                n_hover_search += ep["hover_mode"].get(v) == "search"
            if ep["hit"].get(v) is None:
                continue
            n_all += 1
            n_never += not any(x >= ep["t0"] for x in ts)
            n_search += ep["mode"].get(v) == "search"
        opp[v] = {"per10": round(n_all * per10, 1),
                  "never_engaged_per10": round(n_never * per10, 1),
                  "in_search_mode_per10": round(n_search * per10, 1),
                  "hover_per10": round(n_hover * per10, 1),
                  "hover_in_search_per10": round(n_hover_search * per10, 1)}  # fmt: skip
    return {
        "sid": prep["sid"], "span_s": round(span_s, 1), "frames": len(rows),
        "kills": prep["kills"], "offset_px": prep["offset_px"],
        "hits": {"|".join(map(str, k)): v for k, v in hits.items()},
        "n_hidden": dict(n_hidden), "n_tracked": dict(n_tracked), "never_seen": never_seen,
        "n_where": {"|".join(k): v for k, v in n_where.items()},
        "n_where_t": {"|".join(k): v for k, v in n_where_t.items()},
        "where3": {"|".join(k): v for k, v in where3.items()},
        "hover": {"|".join(k): v for k, v in hover.items()},
        "identity": dict(ident), "false": false_mass, "opportunity": opp,
        "episodes": len(done_eps),
        "cost_ms": {"update_p50": float(np.median(cost_ms)),
                    "update_p95": float(np.percentile(cost_ms, 95)),
                    "beliefs_p50": float(np.median(grid_ms)) if grid_ms else None,
                    "beliefs_p95": float(np.percentile(grid_ms, 95)) if grid_ms else None,
                    "tracks_p50": float(np.median(n_tracks)) if n_tracks else None,
                    "tracks_p95": float(np.percentile(n_tracks, 95)) if n_tracks else None},
    }  # fmt: skip


# --- offline: the CLI -----------------------------------------------------------------------------


def load_grid(map_name: str = MAP) -> Any:
    from anim_region import stand_grid

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    gat = gatmod.parse((cam.GAT_DIR / f"{map_name}.gat").read_bytes())
    return stand_grid(map_name, gat)


def occluders_of(preps: Sequence[Mapping[str, Any]]) -> tuple[Any, Any]:
    """(box-rate route, packet route) vis maps pooled over ``preps``."""
    nv = sum(p["n_view"].astype(float) for p in preps)
    nb = sum(p["n_box"].astype(float) for p in preps)
    nt = sum(p["n_true"].astype(float) for p in preps)
    nh = sum(p["n_thit"].astype(float) for p in preps)
    return occluder_map(nv, nb), occluder_map(nt, nh)


def variants_for(px: Any, pk: Any, fr: Any = None, sweep: bool = False) -> list[Variant]:
    vs = [Variant("kernel"), Variant("kernel+lead", lead=LEAD_W), Variant("ne", PD),
          Variant("ne+lead", PD, lead=LEAD_W),
          Variant("ne+lead+occ_box", PD, vis=px, lead=LEAD_W),
          Variant("ne+lead+occ_pk", PD, vis=pk, lead=LEAD_W)]  # fmt: skip
    if fr is not None:
        vs.append(Variant("ne+lead+occ_fr", PD, vis=fr, lead=LEAD_W))
    if sweep:
        vs += [Variant("ne+lead.3", PD, lead=0.3), Variant("ne+lead.7", PD, lead=0.7),
               Variant("ne.4+lead", 0.4, lead=LEAD_W)]  # fmt: skip
    return vs


def _sum(rs: Sequence[Mapping[str, Any]], key: str) -> Counter[str]:
    c: Counter[str] = Counter()
    for r in rs:
        c.update(r[key])
    return c


def tables(results: Sequence[Mapping[str, Any]], names: Sequence[str]) -> str:
    out: list[str] = []
    bins = [_bin(a + 1e-9) for a, _b in UNSEEN_BINS]
    sets = [(r["sid"].split("T", 1)[1][:6] + " " + r["sid"].rsplit("-", 1)[1], [r])
            for r in results]  # fmt: skip
    if len(results) > 1:
        sets.append(("POOLED", list(results)))
    out.append("HIDDEN SAMPLES (frame x monster: alive, in the AOI, unboxed >= 1 s; the belief has "
               "a track carrying its gid = tracked)")  # fmt: skip
    for lab, rs in sets:
        nh, nt = _sum(rs, "n_hidden"), _sum(rs, "n_tracked")
        ns = sum(r["never_seen"] for r in rs)
        cells = "  ".join(f"{b} {nt[b]}/{nh[b]}" for b in bins)
        out.append(f"  {lab:22s} {cells}  | never boxed yet: {ns}")
    for lab, rs in sets:
        out.append(f"\nHIT RATE {lab}: of TRACKED hidden samples (of ALL hidden in brackets); "
                   "raw top-k r=0 | spaced top-k r<=1")  # fmt: skip
        hits: Counter[str] = Counter()
        for r in rs:
            for key, val in r["hits"].items():
                hits[key] += val
        nh, nt = _sum(rs, "n_hidden"), _sum(rs, "n_tracked")
        hdr = "  ".join(f"{b:>27s}" for b in [*bins, "all"])
        out.append(f"  {'variant':12s} {hdr}")
        for v in names:
            row = []
            for b in [*bins, "all"]:
                bb = bins if b == "all" else [b]
                n_t = sum(nt[x] for x in bb)
                n_h = sum(nh[x] for x in bb)

                def h(k: int, rr: int, sp: bool, bb: list[str] = bb, v: str = v,
                      hits: Counter[str] = hits) -> int:  # fmt: skip
                    return sum(hits[f"{v}|{x}|{k}|{rr}|{sp}"] for x in bb)

                if not n_t:
                    row.append(f"{'-':>27s}")
                    continue
                a = "/".join(f"{100 * h(k, 0, False) / n_t:.0f}" for k in (1, 3, 5))
                c = "/".join(f"{100 * h(k, 1, True) / n_t:.0f}" for k in (1, 3, 5))
                row.append(f"{a:>9s} | {c:>8s} [{100 * h(3, 1, True) / n_h:.0f}]".rjust(27))
            out.append(f"  {v:12s} " + "  ".join(row))
    out.append("\nON SCREEN vs OFF: tracked hidden samples whose true feet are drawn (body clear "
               "of the UI) = in, else off (off screen / under a window); spaced top-3 <= 1 cell "
               "with probes anywhere | HOVER probes (on-screen cells only; in only)")  # fmt: skip
    for lab, rs in sets:
        nw: Counter[str] = Counter()
        w3: Counter[str] = Counter()
        hv: Counter[str] = Counter()
        for r in rs:
            nw.update(r["n_where_t"])
            w3.update(r["where3"])
            hv.update(r["hover"])
        cnt = "  ".join(f"{b} in {nw[f'{b}|in']} off {nw[f'{b}|off']}" for b in bins)
        out.append(f"  {lab}: tracked samples {cnt}")
        for v in names:
            row = []
            for b in bins:
                ni, no = nw[f"{b}|in"], nw[f"{b}|off"]
                i3 = 100 * w3[f"{v}|{b}|in"] / ni if ni else float("nan")
                o3 = 100 * w3[f"{v}|{b}|off"] / no if no else float("nan")
                hh = 100 * hv[f"{v}|{b}|in"] / ni if ni else float("nan")
                row.append(f"{b} in {i3:3.0f}|{hh:3.0f} off {o3:3.0f}")
            out.append(f"    {v:16s} " + "   ".join(row))
    out.append("\nIDENTITY through a dropout (a labelled box after its gid was unboxed >= 1 s)")
    for lab, rs in sets:
        c = _sum(rs, "identity")
        n = sum(c.values())
        out.append(f"  {lab:22s} n={n:5d}  " + "  ".join(f"{k} {100 * v / n:.0f} %"
                                                       for k, v in sorted(c.items())))  # fmt: skip
    out.append("\nOPPORTUNITY / 10 min: hidden episodes the spaced top-3 found within 1 cell, "
               "the bot never engaging that gid in the episode (+ never later; + found in "
               "search mode); hover = found by on-screen probes (+ in search mode)")  # fmt: skip
    for lab, rs in sets:
        row = []
        for v in names:
            a = np.mean([r["opportunity"][v]["per10"] for r in rs])
            b = np.mean([r["opportunity"][v]["never_engaged_per10"] for r in rs])
            c = np.mean([r["opportunity"][v]["in_search_mode_per10"] for r in rs])
            hv = np.mean([r["opportunity"][v]["hover_per10"] for r in rs])
            hs = np.mean([r["opportunity"][v]["hover_in_search_per10"] for r in rs])
            row.append(f"{v} {a:.1f}/{b:.1f}/{c:.1f} hover {hv:.1f}/{hs:.1f}")
        k10 = np.mean([r["kills"] * 600 / r["span_s"] for r in rs])
        out.append(f"  {lab:22s} kills/10min {k10:.1f} | " + "  ".join(row))
    out.append("\nFALSE BELIEF (hidden tracks, mass inside the AOI): on cells with no true monster "
               "within 1 cell | on the track's own gid (+-1 cell)")  # fmt: skip
    for lab, rs in sets:
        row = []
        for v in names:
            f = sum(r["false"][v][0] for r in rs)
            o = sum(r["false"][v][1] for r in rs)
            t = sum(r["false"][v][2] for r in rs)
            row.append(f"{v} {100 * f / t:.0f}|{100 * o / t:.0f} %" if t else f"{v} -")
        out.append(f"  {lab:22s} " + "  ".join(row))
    out.append("\nCOST per frame (ms, this host at nice 15): update = associate + negative "
               "evidence of every variant; beliefs = every hidden track's posterior, one "
               "variant")  # fmt: skip
    for r in results:
        c = r["cost_ms"]
        out.append(f"  {r['sid']:40s} update p50 {c['update_p50']:.2f} p95 {c['update_p95']:.2f}"
                   f"  beliefs p50 {c['beliefs_p50']:.2f} p95 {c['beliefs_p95']:.2f}"
                   f"  tracks p50 {c['tracks_p50']}")  # fmt: skip
    return "\n".join(out)


def cmd_eval(a: argparse.Namespace) -> int:
    ok = load_grid(a.map)
    preps = {sid: prepare(sid) for sid in a.sids}
    results = []
    names: list[str] = []
    for sid in a.sids:
        rest = [preps[s] for s in a.sids if s != sid] or [preps[sid]]
        kern = fit_kernel([x for p in rest for x in kernel_samples(p)])
        px, pk = occluders_of(rest)
        fr = None
        if a.frames:  # the FRAME route (pixels only), pooled over the other sessions
            cov = [frame_cover_counts(p["sid"], p) for p in rest]
            fr = cover_map(sum(c[0] for c in cov), sum(c[1] for c in cov))
        vs = variants_for(px, pk, fr, a.sweep)
        if a.only:
            vs = [v for v in vs if v.name in a.only.split(",")]
        names = [v.name for v in vs]
        t0 = time.time()
        r = run(preps[sid], ok, kern, vs)
        r["wall_s"] = round(time.time() - t0, 1)
        r["held_out"] = len(rest) < len(a.sids)
        r["kernel"] = kern.to_json()
        results.append(r)
        print(f"{sid}: {r['frames']} frames, {r['wall_s']} s", flush=True)
    print(tables(results, names))
    if a.json:
        Path(a.json).write_text(json.dumps(results, indent=1, default=str))
    return 0


def cmd_occluders(a: argparse.Namespace) -> int:
    preps = [prepare(sid) for sid in a.sids]
    px, pk = occluders_of(preps)
    cov = [frame_cover_counts(p["sid"], p) for p in preps]
    fr = cover_map(sum(c[0] for c in cov), sum(c[1] for c in cov))
    kern = fit_kernel([x for p in preps for x in kernel_samples(p)])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{a.map}.occluders.npz"
    np.savez_compressed(path, vis_frame=fr.astype(np.float32), vis_boxrate=px.astype(np.float32),
                        vis_packet=pk.astype(np.float32), sessions=np.array(a.sids))  # fmt: skip
    (OUT_DIR / f"{a.map}.kernel.json").write_text(json.dumps(kern.to_json()))
    print(f"{path}: vis < 0.5 on {int((fr < 0.5).sum())} cells (frame route), "
          f"{int((px < 0.5).sum())} (box rate), {int((pk < 0.5).sum())} (packet route, offline "
          f"artefact); kernel -> {a.map}.kernel.json")  # fmt: skip
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("eval", help="leave-one-session-out validation against packet truth")
    e.add_argument("sids", nargs="+")
    e.add_argument("--map", default=MAP)
    e.add_argument("--sweep", action="store_true", help="also the PD / lead variants")
    e.add_argument("--frames", action="store_true",
                   help="also the FRAME route occluder (reads the NAS hunt-recordings once)"
                   )  # fmt: skip
    e.add_argument("--only", help="comma-separated variant names to keep")
    e.add_argument("--json")
    e.set_defaults(func=cmd_eval)
    o = sub.add_parser("occluders", help="pooled occluder maps + kernel -> data/belief/")
    o.add_argument("sids", nargs="+")
    o.add_argument("--map", default=MAP)
    o.set_defaults(func=cmd_occluders)
    a = ap.parse_args()
    return int(a.func(a))


if __name__ == "__main__":
    raise SystemExit(main())
