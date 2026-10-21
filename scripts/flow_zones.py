#!/usr/bin/env python3
"""The flow linter's MAP ZONES provider: each map's zones file through the runner's own loader
(ADR-0020 Amendment A 4, DRAFT; docs/planning/blocks-from-hunt-flow.md section 3, B1).

    provider(root=config/map_zones, shape=None)  ->  map id -> poring_flow.zones.ZoneInfo | None

The file and `scripts/map_zones.py` stay the source of truth; nothing here re-implements the
geometry. A map without a file gives None (no zones), a file the loader refuses raises
`ZonesUnreadable` (fail closed). The closed cells are the loader's own rasters: the no-cross lines'
closed supercover and the no-enter areas' cells -- what the runner takes out of its route grid
(`map_zones.route_grid`). `shape` (h, w), when given per map, bounds the rasters to the map; without
it the raster covers every point of the file (cells off the map close nothing).

    flow_zones.py <map> [--root DIR]    print the map's ZoneInfo summary (sha256, cell counts)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import map_zones as mz  # noqa: E402

from poring_flow.zones import Cell, ZoneInfo, ZonesUnreadable  # noqa: E402


def _cells(mask: np.ndarray) -> frozenset[Cell]:
    ys, xs = np.nonzero(mask)  # grids are [y, x] with y north (map_zones' docstring)
    return frozenset((int(x), int(y)) for x, y in zip(xs, ys, strict=True))


def info(zones: mz.Zones, shape: tuple[int, int] | None = None) -> ZoneInfo:
    if shape is None:
        pts = [p for z in zones.no_cross for p in z.points]
        pts += [p for z in zones.no_enter for p in z.polygon]
        shape = (max((p[1] for p in pts), default=0) + 2, max((p[0] for p in pts), default=0) + 2)
    nc, ne = mz.no_cross_mask(zones, shape), mz.no_enter_mask(zones, shape)
    return ZoneInfo(map=zones.map, sha256=zones.sha256, closed=_cells(nc | ne), no_enter=_cells(ne))


def provider(
    root: Path | str = mz.ZONES_DIR, shapes: Mapping[str, tuple[int, int]] | None = None
) -> Callable[[str], ZoneInfo | None]:
    def get(map_id: str) -> ZoneInfo | None:
        try:
            z = mz.load(map_id, root, shape=(shapes or {}).get(map_id))
        except mz.ZoneError as e:
            raise ZonesUnreadable(str(e)) from None
        return None if z is None else info(z, (shapes or {}).get(map_id))

    return get


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("map")
    ap.add_argument("--root", default=str(mz.ZONES_DIR))
    a = ap.parse_args()
    z = provider(a.root)(a.map)
    if z is None:
        print(json.dumps({"map": a.map, "zones": None}))
        return 0
    print(json.dumps({"map": z.map, "sha256": z.sha256, "closed_cells": len(z.closed),
                      "no_enter_cells": len(z.no_enter)}))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
