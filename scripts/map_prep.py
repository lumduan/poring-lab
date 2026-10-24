#!/usr/bin/env python3
"""MAP-AGNOSTIC offline prep for a hunt map (2026-10-24, the pay_fild07 prep:
docs/planning/payf07-prep.md; the steps orcsdun01-dungeon-prep.md ran for the dungeon, for any map).

    map_prep.py walkability MAP [MAP...]
    map_prep.py stands MAP [--root DIR] [--min-sep 20] [--min-clear 10] [--within 25]

OFFLINE ONLY: no client, no packets, no GPU, no input. Every source is the local run-time copy:
the client GAT (/dev/shm, poring_dataset.camera.GAT_DIR), the server map cache (_generated), L3
(data/kb: route.json's warps, first_workflow.json's script-NPC touch areas, warps.json). Nothing
data-bearing is written to the repo; the printed JSON holds cells and counts only.

``walkability``: per map, poring_dataset.walkable.agreement (client GAT vs server map cache: the
cells walkable on each side, the disagreement both ways) and the 8-connected components of client
AND server walkability, with rAthena's no-corner-cutting rule and without it.

``stands``: the runner's search area built exactly as scripts/dungeon_hunt.py run() builds it
(``runner_area``: anim_region.stand_grid -> hunt_core.search_area keeping the warp spans 10 cells
off -> map_zones.apply -> minus what the zones seal off -> its largest 8-connected component), then
- START = hunt_flow.area_centre(area): the anchor the runner draws its seeded start near
  (hunt.start_cell, within ``--within`` cells);
- FALLBACK = the area cell nearest START (Euclidean) that is CLEAR -- its whole
  (2 x ``--min-clear`` + 1)^2 square walkable on client AND server -- and at least ``--min-sep``
  cells (Chebyshev) from START: a second, wide-open stand somewhere else.
Each is reported with the THREE stand-cell checks (npc_click_test.check_warps: outside every warp
span, outside every script-NPC touch area, standable on the SERVER map cache), the main component,
the no-enter areas, the open 8-neighbours, its clearance, the Chebyshev distance to the nearest
warp span and the walk steps from START (8-way, no corner cutting, the zone-free route grid). Every
area cell of the seeded-start box around START is checked too (one check_warps call).
``--root``: the zones directory (default config/map_zones). A DRAFT the loader refuses is proved
from a test-reviewer COPY outside the repo (payf07-prep.md section 4); without a loadable file the
command refuses (the stands must lie outside the zones).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

Cell = tuple[int, int]
NEIGHBOURS = tuple((dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy)
SEARCH_MARGIN = 10  # dungeon_hunt.run(): hunt_core.search_area(ok, warps, margin=10)


# --- pure parts ------------------------------------------------------------------------------


def clearance(mask: Any, max_r: int = 12) -> np.ndarray:
    """PURE: per cell (y, x), the largest r <= ``max_r`` whose (2r + 1)^2 square centred on it is
    all True in ``mask`` (cells off the map count as not walkable); -1 off the mask, 0 = the cell
    alone."""
    m = np.asarray(mask, dtype=bool)
    out = np.where(m, 0, -1).astype(np.int64)
    ok = m.copy()
    for r in range(1, max_r + 1):
        pad = np.pad(m, r, constant_values=False)
        win = np.lib.stride_tricks.sliding_window_view(pad, (2 * r + 1, 2 * r + 1)).all(axis=(2, 3))
        ok &= win
        if not ok.any():
            break
        out[ok] = r
    return out


def pick_fallback(area: Any, clear: np.ndarray, start: Cell, min_sep: int,
                  min_clear: int) -> Cell | None:  # fmt: skip
    """PURE: the ``area`` cell nearest ``start`` (Euclidean; ties by y, then x) whose ``clear`` is
    >= ``min_clear`` and that lies >= ``min_sep`` cells (Chebyshev) from ``start``; None when no
    such cell exists."""
    a = np.asarray(area, dtype=bool) & (clear >= min_clear)
    ys, xs = np.nonzero(a)
    far = np.maximum(np.abs(xs - start[0]), np.abs(ys - start[1])) >= min_sep
    ys, xs = ys[far], xs[far]
    if not len(xs):
        return None
    d2 = (xs - start[0]) ** 2 + (ys - start[1]) ** 2
    i = int(np.lexsort((xs, ys, d2))[0])
    return int(xs[i]), int(ys[i])


def open_neighbours(ok: Any, c: Cell) -> int:
    """PURE: the walkable 8-neighbours of ``c`` on ``ok`` (y, x)."""
    m = np.asarray(ok, dtype=bool)
    h, w = m.shape
    x, y = c
    return sum(1 for dx, dy in NEIGHBOURS
               if 0 <= x + dx < w and 0 <= y + dy < h and m[y + dy, x + dx])  # fmt: skip


def span_distance(c: Cell, warps: Sequence[dict[str, Any]]) -> int | None:
    """PURE: the Chebyshev distance from ``c`` to the nearest warp span (centre +- span; 0 =
    inside one); None without warps."""
    out = [max(max(0, abs(c[0] - w["x"]) - w["span_x"]), max(0, abs(c[1] - w["y"]) - w["span_y"]))
           for w in warps]  # fmt: skip
    return min(out) if out else None


def runner_area(ok: Any, warps: Sequence[dict[str, Any]], zones: Any) -> tuple[Any, Any]:
    """PURE: (area, okr) as scripts/dungeon_hunt.py run() builds them from the stand grid ``ok``,
    the map's warps and its zones (None: none): the search area keeps every warp span
    ``SEARCH_MARGIN`` cells off and loses the zones and what they seal off, then its largest
    8-connected component; okr is the zone-free route grid minus the sealed-off cells."""
    import hunt_core as hc
    import hunt_flow as hf
    import map_zones as mz

    keep = [(w["x"], w["y"], w["span_x"], w["span_y"]) for w in warps]
    area = mz.apply(ok, hc.search_area(ok, keep, margin=SEARCH_MARGIN), zones)[1]
    okr = mz.route_grid(ok, zones)
    cut = mz.sealed_off(ok, okr)
    return hf.main_component(area & ~cut), okr & ~cut


def stand_check(map_name: str, cells: Sequence[Sequence[int]]) -> str | None:
    """npc_click_test.check_warps on a plan that only STANDS on ``cells`` (no clicks): None when
    every cell passes the three stand-cell checks, else the refusal's text."""
    import npc_click_test as nct

    plan = {"npcs": [{"stands": [list(c) for c in cells]}], "clicks": []}
    try:
        nct.check_warps(map_name, plan, clicks=False)
    except SystemExit as e:
        return str(e)
    return None


def components(mask: Any) -> dict[str, Any]:
    """PURE: the 8-connected components of ``mask``, without and with rAthena's corner rule:
    their count and the largest sizes."""
    import map_zones as mz

    out: dict[str, Any] = {}
    for corner in (False, True):
        _, sizes = mz._label8(mask, corner)
        s = sorted(sizes[1:], reverse=True)
        out["corner_rule" if corner else "no_corner_rule"] = {"n": len(s), "largest": s[:5]}
    return out


# --- commands --------------------------------------------------------------------------------


def cmd_walkability(maps: Sequence[str]) -> dict[str, Any]:
    from poring_dataset import walkable as wk

    out: dict[str, Any] = {}
    for m in maps:
        gat, both = wk.load_both(m)
        ag = wk.agreement(gat, wk.server_grid(m))
        b = np.asarray(both, dtype=bool)
        out[m] = {"agreement": dict(ag), "both": int(b.sum()), "components": components(b)}
    return out


def _stand(c: Cell, *, map_name: str, both: Any, main: Any, zones: Any, okr: Any,
           warps: Sequence[dict[str, Any]], clear: np.ndarray, dist: np.ndarray
           ) -> dict[str, Any]:  # fmt: skip
    import map_zones as mz

    x, y = c
    return {"cell": [x, y], "three_checks": stand_check(map_name, [c]) or "pass",
            "client_and_server": bool(both[y, x]), "main_component": bool(main[y, x]),
            "in_no_enter": mz.in_no_enter(zones, c), "open_neighbours": open_neighbours(both, c),
            "clearance": int(clear[y, x]), "warp_span_distance": span_distance(c, warps),
            "steps_from_start": int(dist[y, x])}  # fmt: skip


def cmd_stands(a: argparse.Namespace) -> dict[str, Any]:
    import hunt_flow as hf
    import map_zones as mz
    import npc_click_test as nct
    from anim_region import stand_grid

    from poring_dataset import walkable as wk

    gat, both_ = wk.load_both(a.map)
    both = np.asarray(both_, dtype=bool)
    ok = np.asarray(stand_grid(a.map, gat), dtype=bool)
    try:
        zones = mz.load(a.map, a.root or mz.ZONES_DIR, shape=ok.shape)
    except mz.ZoneError as e:
        raise SystemExit(f"stands refused: the zones file: {e}") from None
    if zones is None:
        raise SystemExit(f"stands refused: no zones file for {a.map} under {a.root}")
    warps = nct.load_warps(a.map) or []
    area, okr = runner_area(ok, warps, zones)
    lab, sizes = mz._label8(both, True)
    main = lab == int(np.argmax(sizes))
    start = hf.area_centre(area)
    clear = clearance(both, max(a.min_clear, 12))
    import orc_dungeon_prep as odp

    dist = odp.bfs(np.asarray(okr, dtype=bool), start)
    fb = pick_fallback(area, clear, start, a.min_sep, a.min_clear)
    kw = {"map_name": a.map, "both": both, "main": main, "zones": zones, "okr": okr,
          "warps": warps, "clear": clear, "dist": dist}  # fmt: skip
    box = np.zeros_like(area)
    w_ = a.within
    box[max(0, start[1] - w_) : start[1] + w_ + 1, max(0, start[0] - w_) : start[0] + w_ + 1] = True
    cells = [[int(x), int(y)] for y, x in zip(*np.nonzero(area & box), strict=True)]
    seeded = stand_check(a.map, cells) if cells else "no area cell in the box"
    return {"map": a.map, "zones": {"file": zones.path, "sha256": zones.sha256,
                                    "reviewed_by": zones.reviewed_by},
            "stand_grid": int(ok.sum()), "area": int(area.sum()), "route_grid": int(okr.sum()),
            "start": _stand(start, **kw),
            "fallback": None if fb is None else _stand(fb, **kw),
            "fallback_rule": {"min_sep": a.min_sep, "min_clear": a.min_clear},
            "seeded_start_box": {"within": w_, "area_cells": len(cells),
                                 "three_checks": seeded or "pass"}}  # fmt: skip


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("walkability")
    w.add_argument("maps", nargs="+")
    s = sub.add_parser("stands")
    s.add_argument("map")
    s.add_argument("--root", default=None, help="the zones directory (default config/map_zones)")
    s.add_argument("--min-sep", type=int, default=20, help="FALLBACK: Chebyshev cells from START")
    s.add_argument("--min-clear", type=int, default=10, help="FALLBACK: its open square's radius")
    s.add_argument("--within", type=int, default=25, help="the seeded-start box (hunt.start_cell)")
    a = ap.parse_args(argv)
    res = cmd_walkability(a.maps) if a.cmd == "walkability" else cmd_stands(a)
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
