#!/usr/bin/env python3
"""Walkability: rathena-th's maps (its import cache from the Thai GRF, ahead of the stock caches)
vs the current rathena's (the lock-verified stock caches built from kRO data), per map.

    mapcache_diff.py [--import data/mapcache-th/map_cache.dat] [--out data/bench/mapcache/DIFF.json]
                     [MAP ...]   (default: prt_fild08 prt_church iz_dun00 iz_dun01 prontera)

Per map: whether the Thai GRF supplied it, the size, the count of each cell type, the walkable
count (rAthena's CELL_CHKNOPASS), and how many cells changed (and how many flipped walkability).
The output is client-derived numbers only (counts), kept local (data/)."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from poring_dataset import mapcache

ROOT = Path(__file__).resolve().parents[1]
MAPS = ("prt_fild08", "prt_church", "iz_dun00", "iz_dun01", "prontera")


def walkable(g: mapcache.MapGrid) -> int:
    return sum(not g.nopass(x, y) for y in range(g.ys) for x in range(g.xs))


def compare(stock: mapcache.MapGrid | None, th: mapcache.MapGrid | None, from_thai: bool) -> dict:
    row: dict[str, object] = {"thai_cache": from_thai}
    for tag, g in (("stock", stock), ("th", th)):
        row[tag] = None if g is None else {
            "size": [g.xs, g.ys], "walkable": walkable(g),
            "types": {str(k): v for k, v in sorted(Counter(g.cells).items())},
        }  # fmt: skip
    if stock is not None and th is not None:
        if (stock.xs, stock.ys) != (th.xs, th.ys):
            row["changed"] = "size differs"
        else:
            changed = flipped = 0
            for y in range(stock.ys):
                for x in range(stock.xs):
                    if stock.gat(x, y) != th.gat(x, y):
                        changed += 1
                        flipped += stock.nopass(x, y) != th.nopass(x, y)
            row["changed_cells"], row["walkability_flips"] = changed, flipped
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("maps", nargs="*", default=list(MAPS))
    ap.add_argument("--import", dest="imp", type=Path,
                    default=ROOT / "data" / "mapcache-th" / "map_cache.dat")  # fmt: skip
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    stock = mapcache.load(prere=True)
    thai = mapcache.parse(a.imp.read_bytes())
    th = mapcache.merge([thai, stock])
    result = {m: compare(stock.get(m), th.get(m), m in thai) for m in a.maps}
    summary = {"thai_maps": len(thai), "stock_maps": len(stock)}
    text = json.dumps({"summary": summary, "maps": result}, indent=1)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
