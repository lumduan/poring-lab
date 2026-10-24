#!/usr/bin/env python3
"""orcsdun01 prep for a DEFEND-SCAN run (docs/planning/orcsdun01-dungeon-prep.md sections 2-3):
REST SPOTS from the warp-and-watch blocks' packets, and the zone CLICK PROOF.

    orc_dungeon_prep.py rest-spots SESSION_DIR [...] [--min-observed-s 60] [--top 5] [--out JSON]
    orc_dungeon_prep.py zone-clicks [--map orcsdun01] [--root DIR] [--samples 400] [--seed 0]

OFFLINE ONLY (ADR-0007: packets are ground truth for a measurement, never an agent input). No
frame is read, no client, no GPU. The KB (data/kb, L3), the client GAT and the server map cache
are the local run-time copies; nothing data-bearing is written to the repo.

``rest-spots``: monster PRESENCE per walkable cell. At 1 Hz inside every dwell (events.jsonl
dwell_start..dwell_end: the GM settled at its stand), outside the GM-command windows, the packets'
world (poring_dataset.timeline) gives every monster the server has sent: the units in the GM's
VIEW AREA (rAthena area_size, 14 cells Chebyshev; the data's own maximum is printed as a check).
A cell c is OBSERVED at that second when its whole R-neighbourhood lies inside the view area
(Chebyshev(c, GM) <= VIEW - R); its presence = the mean number of monsters within R cells
(Chebyshev) of c over its observed seconds = unit-seconds per observed second (x 60: per minute).
Only cells observed >= --min-observed-s count. The candidates also pass:
- the three stand-cell checks (npc_click_test.check_warps: outside the warp spans, outside the
  script-NPC touch areas, standable on the SERVER map cache);
- the main walkable component (client AND server, poring_dataset.walkable.load_both);
- outside the map zones (config/map_zones/orcsdun01.yaml), when the file is there.

``zone-clicks``: for each no-enter area of config/map_zones/<map>.yaml (--map, default orcsdun01;
--root another zones directory, e.g. a test-reviewer copy of a DRAFT in /dev/shm: 2026-10-24,
docs/planning/payf07-prep.md), --samples walk clicks from walkable cells outside it into it, and as
many onto its warp span: every one must be refused by map_zones.walk_why (the runner's gate); also
the share of outside -> outside clicks near the area it refuses (an over-reach, not a leak).
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

MAP = "orcsdun01"
VIEW = 14  # rAthena battle_config area_size (conf/battle/client.conf default; no lab override)
RADII = (9, 5)
AGGRESSIVE = (1153, 1005, 1152, 1111)  # orcsdun01-detector.md section 1
AGGRESSIVE_N = {1153: 80, 1005: 15, 1152: 10, 1111: 5}  # whole-map spawns (the same section)
ENTRANCE = (32, 166)  # the runner's @warp entrance cell (the brief); the warp's own arrival: 32,170
STEP_HZ = 1.0
NEIGHBOURS = tuple((dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy)


# --- pure parts ------------------------------------------------------------------------------


def box_count(points: Sequence[tuple[int, int]], shape: tuple[int, int], r: int) -> np.ndarray:
    """(h, w) grid: for every cell, how many ``points`` (x, y) lie within Chebyshev ``r`` of it."""
    h, w = shape
    hist = np.zeros((h + 1, w + 1), dtype=np.int64)
    for x, y in points:
        if 0 <= x < w and 0 <= y < h:
            hist[y + 1, x + 1] += 1
    cs = hist.cumsum(0).cumsum(1)
    ys, xs = np.arange(h), np.arange(w)
    y0, y1 = np.clip(ys - r, 0, h), np.clip(ys + r + 1, 0, h)
    x0, x1 = np.clip(xs - r, 0, w), np.clip(xs + r + 1, 0, w)
    out: np.ndarray = cs[y1][:, x1] - cs[y0][:, x1] - cs[y1][:, x0] + cs[y0][:, x0]
    return out


def observed_mask(gm: tuple[int, int], shape: tuple[int, int], view: int, r: int) -> np.ndarray:
    """The cells whose whole ``r``-neighbourhood lies in the GM's view area (Chebyshev view)."""
    h, w = shape
    m = np.zeros((h, w), dtype=bool)
    k = view - r
    if k < 0:
        return m
    m[max(0, gm[1] - k) : gm[1] + k + 1, max(0, gm[0] - k) : gm[0] + k + 1] = True
    return m


class Presence:
    """Accumulates, per radius: observed seconds per cell, and unit-seconds of monsters (all and
    aggressive) within the radius during those seconds."""

    def __init__(self, shape: tuple[int, int], radii: Sequence[int] = RADII, view: int = VIEW):
        self.shape, self.radii, self.view = shape, tuple(radii), view
        self.obs = {r: np.zeros(shape) for r in self.radii}
        self.all = {r: np.zeros(shape) for r in self.radii}
        self.agg = {r: np.zeros(shape) for r in self.radii}
        self.dwells = {r: np.zeros(shape, dtype=np.int64) for r in self.radii}
        self._last = {r: np.full(shape, -1, dtype=np.int64) for r in self.radii}

    def add(self, gm: tuple[int, int], monsters: Iterable[tuple[int, int, int]],
            dt: float = 1.0, dwell: int = 0) -> None:  # fmt: skip
        """One sample: the GM at ``gm``, the monsters (x, y, mob id) the server has sent, during
        the dwell numbered ``dwell`` (distinct dwells per cell are counted: the estimate's real
        sample size, since a dwell's seconds are strongly correlated)."""
        ms = list(monsters)
        pts = [(x, y) for x, y, _ in ms]
        agg = [(x, y) for x, y, j in ms if j in AGGRESSIVE]
        for r in self.radii:
            m = observed_mask(gm, self.shape, self.view, r)
            self.obs[r][m] += dt
            new = m & (self._last[r] != dwell)
            self.dwells[r][new] += 1
            self._last[r][new] = dwell
            self.all[r][m] += dt * box_count(pts, self.shape, r)[m]
            self.agg[r][m] += dt * box_count(agg, self.shape, r)[m]

    def rate(self, r: int, which: str = "agg", min_obs: float = 0.0) -> np.ndarray:
        """Mean monsters within ``r`` per observed second (NaN where observed < ``min_obs``)."""
        src = self.agg[r] if which == "agg" else self.all[r]
        with np.errstate(invalid="ignore", divide="ignore"):
            out: np.ndarray = np.where(self.obs[r] >= max(min_obs, 1e-9), src / self.obs[r],
                                       np.nan)  # fmt: skip
        return out


def bfs(ok: np.ndarray, start: tuple[int, int]) -> np.ndarray:
    """8-way steps on ``ok`` (y, x) from ``start`` (x, y), no corner cutting (rAthena's walk:
    a diagonal step needs both orthogonal cells free); -1 where unreachable."""
    h, w = ok.shape
    dist = np.full((h, w), -1, dtype=np.int64)
    if not ok[start[1], start[0]]:
        return dist
    dist[start[1], start[0]] = 0
    frontier = [start]
    d = 0
    while frontier:
        d += 1
        nxt = []
        for x, y in frontier:
            for dx, dy in NEIGHBOURS:
                nx, ny = x + dx, y + dy
                if not (0 <= nx < w and 0 <= ny < h) or not ok[ny, nx] or dist[ny, nx] >= 0:
                    continue
                if dx and dy and not (ok[y, nx] and ok[ny, x]):
                    continue
                dist[ny, nx] = d
                nxt.append((nx, ny))
        frontier = nxt
    return dist


def multi_bfs(ok: np.ndarray, starts: np.ndarray) -> np.ndarray:
    """``bfs`` from every True cell of ``starts`` (y, x) at once."""
    h, w = ok.shape
    dist = np.full((h, w), -1, dtype=np.int64)
    ys, xs = np.nonzero(starts & ok)
    dist[ys, xs] = 0
    frontier = list(zip(xs.tolist(), ys.tolist(), strict=True))
    d = 0
    while frontier:
        d += 1
        nxt = []
        for x, y in frontier:
            for dx, dy in NEIGHBOURS:
                nx, ny = x + dx, y + dy
                if not (0 <= nx < w and 0 <= ny < h) or not ok[ny, nx] or dist[ny, nx] >= 0:
                    continue
                if dx and dy and not (ok[y, nx] and ok[ny, x]):
                    continue
                dist[ny, nx] = d
                nxt.append((nx, ny))
        frontier = nxt
    return dist


def free_neighbours(ok: np.ndarray, c: tuple[int, int]) -> int:
    """Walkable 8-neighbours of ``c``: how many melee attackers can stand next to it at once."""
    h, w = ok.shape
    x, y = c
    return sum(1 for dx, dy in NEIGHBOURS
               if 0 <= x + dx < w and 0 <= y + dy < h and ok[y + dy, x + dx])  # fmt: skip


def pick_spots(score: np.ndarray, eligible: np.ndarray, top: int, min_sep: int
               ) -> list[tuple[int, int]]:  # fmt: skip
    """The ``top`` lowest-score eligible cells (x, y), each >= ``min_sep`` cells (Chebyshev) from
    those picked before it (one spot per quiet area, not five neighbours)."""
    ys, xs = np.nonzero(eligible & np.isfinite(score))
    order = np.lexsort((xs, ys, score[ys, xs]))
    out: list[tuple[int, int]] = []
    for i in order:
        c = (int(xs[i]), int(ys[i]))
        if all(max(abs(c[0] - p[0]), abs(c[1] - p[1])) >= min_sep for p in out):
            out.append(c)
            if len(out) == top:
                break
    return out


def static_reach(ok: np.ndarray, spawnable: np.ndarray, r: int = 10) -> np.ndarray:
    """For every cell c: how many ``spawnable`` cells s lie within Chebyshev ``r`` of it with a
    clear straight line s -> c (every cell the rounded line steps on, ends excluded, is ``ok``).
    A GEOMETRY prior (crusader-orcsdun01-facts.md 3d's box + line-of-sight count, without its
    path <= 10 rule, which changed its mean by ~8 %); the line is a rounded-DDA approximation of
    rAthena's path_search_long, not a port."""
    h, w = ok.shape
    out = np.zeros((h, w), dtype=np.int64)
    pad = r + 1
    okp = np.zeros((h + 2 * pad, w + 2 * pad), dtype=bool)
    okp[pad : pad + h, pad : pad + w] = ok
    spp = np.zeros_like(okp)
    spp[pad : pad + h, pad : pad + w] = spawnable
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            # s = c + (dx, dy); the line from s back to c
            clear = spp[pad + dy : pad + dy + h, pad + dx : pad + dx + w].copy()
            n = max(abs(dx), abs(dy))
            for i in range(1, n):
                ix = int(round(dx * (n - i) / n))
                iy = int(round(dy * (n - i) / n))
                clear &= okp[pad + iy : pad + iy + h, pad + ix : pad + ix + w]
            out += clear
    return out


# --- rest spots ------------------------------------------------------------------------------


Sample = tuple[int, tuple[int, int], list[tuple[int, int, int]]]


def session_samples(session: Path, step_s: float = 1.0 / STEP_HZ) -> Iterable[Sample]:
    """(dwell index, GM cell, [(x, y, mob id)]) at ``step_s`` inside the dwells, outside the GM
    windows."""
    import orc_camera_check as occ

    from poring_dataset import mapcache
    from poring_dataset.labels import gm_windows, in_windows
    from poring_dataset.timeline import Timeline

    with gzip.open(session / "packets.jsonl.gz", "rt") as fh:
        events = [json.loads(line) for line in fh]
    tl = Timeline(events, mapcache.load(prere=True))
    windows = gm_windows(events)
    dwells = occ.dwell_spans(
        json.loads(x) for x in (session / "events.jsonl").read_text().splitlines() if x
    )
    step = int(step_s * 1e9)
    for k, (a, b) in enumerate(dwells):
        for t in range(a, b, step):
            if in_windows(t, windows):
                continue
            w = tl.frame_world(t)
            if w.self_pos is None or w.map is None or not w.map.startswith(MAP):
                continue
            gm = (round(w.self_pos[0]), round(w.self_pos[1]))
            mons = [(round(e.x), round(e.y), e.job) for e in w.entities
                    if e.objtype == 5 and not e.hidden]  # fmt: skip
            yield k, gm, mons


def stand_ok(cell: tuple[int, int]) -> str | None:
    """npc_click_test.check_warps on a one-stand plan: None = passes the three checks."""
    import npc_click_test as nct

    try:
        nct.check_warps(MAP, {"npcs": [{"stands": [list(cell)]}], "clicks": []}, clicks=False)
    except SystemExit as e:
        return str(e)
    return None


def cmd_rest(a: argparse.Namespace) -> dict[str, Any]:
    import map_zones

    from poring_dataset import walkable as wk

    _gat, both_ = wk.load_both(MAP)
    both = np.asarray(both_, dtype=bool)
    shape = (int(both.shape[0]), int(both.shape[1]))
    pres = Presence(shape)
    by_session: dict[str, Presence] = {}
    max_cheb, seconds, per_session = 0, 0, Counter[str]()
    for i, s in enumerate(a.sessions):
        one = by_session.setdefault(Path(s).name[-4:], Presence(shape))
        for k, gm, mons in session_samples(Path(s)):
            for x, y, _ in mons:
                max_cheb = max(max_cheb, abs(x - gm[0]), abs(y - gm[1]))
            pres.add(gm, mons, dwell=i * 100_000 + k)
            one.add(gm, mons, dwell=k)
            seconds += 1
            per_session[Path(s).name] += 1
    zones = map_zones.load(MAP, shape=shape)
    zone = (map_zones.no_cross_mask(zones, shape) | map_zones.no_enter_mask(zones, shape)
            if zones is not None else np.zeros(shape, dtype=bool))  # fmt: skip
    ys_, xs_ = np.mgrid[0 : shape[0], 0 : shape[1]]
    spawnable = both & (xs_ >= 15) & (xs_ <= 184) & (ys_ >= 15) & (ys_ <= 184)
    reach = static_reach(both, spawnable, 10)
    e_agg = len(AGGRESSIVE_N) and sum(AGGRESSIVE_N.values()) * reach / max(1, int(spawnable.sum()))
    lab, sizes = map_zones._label8(both, True)
    main = lab == int(np.argmax(sizes))
    eligible = both & main & ~zone
    r_main, r_alt = RADII
    obs_ok = (pres.obs[r_main] >= a.min_observed_s) & (pres.obs[r_alt] >= a.min_observed_s)
    agg9 = pres.rate(r_main, "agg")
    # the hunting areas: observed cells at or above the median aggressive presence (R = 9)
    seen = obs_ok & both & main
    med = float(np.nanmedian(agg9[seen]))
    hunt = seen & (agg9 >= med)
    route_ok = map_zones.route_grid(both, zones) if zones is not None else both
    d_hunt = multi_bfs(route_ok, hunt)
    d_ent = bfs(route_ok, ENTRANCE)

    def row(c: tuple[int, int]) -> dict[str, Any]:
        x, y = c
        return {
            "cell": [x, y],
            "agg_r9_per_min": round(60 * float(pres.rate(9, "agg")[y, x]), 1),
            "all_r9_per_min": round(60 * float(pres.rate(9, "all")[y, x]), 1),
            "agg_r5_per_min": round(60 * float(pres.rate(5, "agg")[y, x]), 1),
            "all_r5_per_min": round(60 * float(pres.rate(5, "all")[y, x]), 1),
            "observed_s_r9": int(pres.obs[9][y, x]), "observed_s_r5": int(pres.obs[5][y, x]),
            "dwells_r9": int(pres.dwells[9][y, x]),
            "agg_r9_per_min_by_block": {
                b: (None if p.obs[9][y, x] < 1 else
                    [round(60 * float(p.rate(9, "agg")[y, x]), 1), int(p.obs[9][y, x])])
                for b, p in by_session.items()},
            "static_e_agg": round(float(e_agg[y, x]), 2),
            "stand_checks": stand_ok(c) or "pass", "in_zone": bool(zone[y, x]),
            "free_neighbours": free_neighbours(both, c),
            "path_to_hunting_area": int(d_hunt[y, x]), "path_from_entrance": int(d_ent[y, x]),
        }  # fmt: skip

    blocks = sum((p.obs[r_main] >= 1).astype(int) for p in by_session.values())
    elig = eligible & obs_ok & (pres.dwells[r_main] >= a.min_dwells) & (blocks >= 2)
    spots = pick_spots(agg9, elig, a.top * 4, a.min_sep)
    ranked = [r for r in (row(c) for c in spots) if r["stand_checks"] == "pass"][: a.top]
    # (a) near the entrance: the quietest eligible cell within --entrance-radius path steps
    near_ent = elig & (d_ent >= 0) & (d_ent <= a.entrance_radius)
    ent_spots = [r for r in (row(c) for c in pick_spots(agg9, near_ent, 5, 3))
                 if r["stand_checks"] == "pass"]  # fmt: skip
    vals = 60 * agg9[seen]
    return {
        "map": MAP, "sessions": dict(per_session), "seconds": seconds, "view_cells": VIEW,
        "max_monster_cheb_seen": max_cheb, "min_observed_s": a.min_observed_s,
        "cells_observed": int(seen.sum()), "walkable_main": int((both & main).sum()),
        "agg_r9_per_min_observed": {"p10": round(float(np.percentile(vals, 10)), 1),
                                    "p50": round(float(np.percentile(vals, 50)), 1),
                                    "p90": round(float(np.percentile(vals, 90)), 1)},
        "hunting_area_rule": f"observed cells with agg R9 >= the median ({60 * med:.1f}/min)",
        "hunting_area_cells": int(hunt.sum()),
        "candidate_rule": f"observed >= {a.min_observed_s:.0f} s at R 9 and R 5, >= "
                          f"{a.min_dwells} dwells and >= 2 blocks at R 9; ranked by the pooled "
                          f"aggressive R 9 presence; >= {a.min_sep} cells apart",
        "static_e_agg_walkable": {"p10": round(float(np.percentile(e_agg[both], 10)), 2),
                                  "p50": round(float(np.percentile(e_agg[both], 50)), 2),
                                  "mean": round(float(e_agg[both].mean()), 2)},
        "spawnable_cells": int(spawnable.sum()),
        "zones": None if zones is None else {"file": zones.path, "sha256": zones.sha256},
        "entrance": {"cell": list(ENTRANCE), **row(ENTRANCE)},
        "near_entrance": ent_spots[:3], "top": ranked,
    }  # fmt: skip


# --- zone click proof -------------------------------------------------------------------------


def zone_clicks(zones: Any, both: np.ndarray, warps: Sequence[dict[str, Any]], samples: int,
                seed: int) -> list[dict[str, Any]]:  # fmt: skip
    """PURE: for each no-enter area of ``zones`` on the walkable grid ``both`` ([y, x]),
    ``samples`` walk clicks from walkable cells outside every zone (within 12 cells of the area)
    INTO it and as many ONTO the span of each warp whose centre lies inside it, through
    map_zones.walk_why (the runner's gate, the client-route proxy on ``both``); plus as many
    outside -> outside clicks near it, the refused ones counted (an over-reach, not a leak). An
    area with no warp inside, or no outside cell near it, says so instead of sampling that leg.
    The draw order is the orcsdun01 proof's (its 400 / 400 numbers reproduce)."""
    import map_zones

    shape = (int(both.shape[0]), int(both.shape[1]))
    rng = np.random.default_rng(seed)
    _, masks = map_zones._masks(zones, shape)
    zone = map_zones.no_cross_mask(zones, shape) | map_zones.no_enter_mask(zones, shape)
    out = []
    for ne, pm in zip(zones.no_enter, masks, strict=True):
        inside = np.argwhere(pm & both)
        span = np.zeros(shape, dtype=bool)
        for w in warps:
            sx = slice(max(0, w["x"] - w["span_x"]), w["x"] + w["span_x"] + 1)
            sy = slice(max(0, w["y"] - w["span_y"]), w["y"] + w["span_y"] + 1)
            if pm[w["y"], w["x"]]:
                span[sy, sx] = True
        on_span = np.argwhere(span & both)
        near = np.zeros(shape, dtype=bool)
        for y, x in inside:
            near[max(0, y - 12) : y + 13, max(0, x - 12) : x + 13] = True
        outside = np.argwhere(near & both & ~zone)
        row: dict[str, Any] = {"id": ne.id, "walkable_in_area": int(len(inside)),
                               "warp_span_cells": int(len(on_span)),
                               "outside_near": int(len(outside))}  # fmt: skip
        if not len(inside) or not len(outside):
            out.append({**row, "note": "no walkable cell inside, or none outside near it"})
            continue
        why: Counter[str] = Counter()
        n_in = n_span = n_out = 0
        for _ in range(samples):
            yo, xo = outside[rng.integers(len(outside))]
            yi, xi = inside[rng.integers(len(inside))]
            w1 = map_zones.walk_why(zones, both, (int(xo), int(yo)), (int(xi), int(yi)))
            n_in += w1 is not None
            why[str(w1)] += 1
            if len(on_span):
                ys_, xs_ = on_span[rng.integers(len(on_span))]
                n_span += map_zones.walk_why(zones, both, (int(xo), int(yo)),
                                             (int(xs_), int(ys_))) is not None  # fmt: skip
            (ya, xa), (yb, xb) = (outside[rng.integers(len(outside))],
                                  outside[rng.integers(len(outside))])  # fmt: skip
            n_out += map_zones.walk_why(zones, both, (int(xa), int(ya)),
                                        (int(xb), int(yb))) is not None  # fmt: skip
        out.append({**row, "into_refused": f"{n_in}/{samples}",
                    "onto_span_refused": f"{n_span}/{samples}" if len(on_span) else None,
                    "outside_to_outside_refused": f"{n_out}/{samples}",
                    "into_reasons": dict(why)})  # fmt: skip
    return out


def cmd_zone_clicks(a: argparse.Namespace) -> dict[str, Any]:
    """``zone-clicks`` on ``a.map`` (default orcsdun01) with the zones file under ``a.root``
    (default config/map_zones; a test-reviewer COPY elsewhere proves a draft's geometry)."""
    import map_zones
    import npc_click_test as nct

    from poring_dataset import walkable as wk

    map_name = getattr(a, "map", None) or MAP
    _gat, both_ = wk.load_both(map_name)
    both = np.asarray(both_, dtype=bool)
    shape = (int(both.shape[0]), int(both.shape[1]))
    zones = map_zones.load(map_name, getattr(a, "root", None) or map_zones.ZONES_DIR, shape=shape)
    if zones is None:
        raise SystemExit(f"no zones file for {map_name}")
    warps = nct.load_warps(map_name) or []
    out = zone_clicks(zones, both, warps, a.samples, a.seed)
    return {"map": map_name, "file": zones.path, "sha256": zones.sha256, "areas": out}


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rest-spots")
    r.add_argument("sessions", nargs="+")
    r.add_argument("--min-observed-s", type=float, default=60.0)
    r.add_argument("--top", type=int, default=5)
    r.add_argument("--min-sep", type=int, default=8, help="Chebyshev cells between spots")
    r.add_argument("--min-dwells", type=int, default=3)
    r.add_argument("--entrance-radius", type=int, default=20, help="path steps from 32,166")
    r.add_argument("--out")
    z = sub.add_parser("zone-clicks")
    z.add_argument("--map", default=MAP, help="the map (default orcsdun01)")
    z.add_argument("--root", default=None, help="the zones directory (default config/map_zones)")
    z.add_argument("--samples", type=int, default=400)
    z.add_argument("--seed", type=int, default=0)
    z.add_argument("--out")
    a = ap.parse_args(argv)
    res = cmd_rest(a) if a.cmd == "rest-spots" else cmd_zone_clicks(a)
    text = json.dumps(res, indent=1)
    if a.out:
        Path(a.out).write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
