#!/usr/bin/env python3
"""Client GAT vs server map cache, per map: the L3 record of where the two disagree (Batt's
decision 4, 2026-10-15: "Client GAT vs server map cache: every walk rule and planner uses only
cells walkable in BOTH sources (intersection); record the mismatch per map as L2/L3 knowledge").

    map_agreement.py build [--gat-dir DIR] [--mapcache-dir DIR] [--kb DIR]
                           [--out data/kb/map_agreement.json]

The maps: every GAT in the client's GAT directory (client data in /dev/shm) and every map L3 lists
(data/kb/route.json's warp lists). For each map BOTH sources hold, poring_dataset.walkable's
`agreement` counts (the overlap, the server's last row / column excluded; that edge and anything
beyond the server's grid counted apart) and the CELL LISTS: `client_only` (client-walkable, the
server says NOPASS: a walk never uses them) and `server_only` (the server lets a character stand,
the client's GAT does not). Maps either source lacks are listed: a walk rule refuses them.

The output holds client-derived cells (and server, GPL-derived ones): it stays LOCAL under data/
(gitignored) and is NEVER committed (CLAUDE.md rule 4). kb_bindings.py puts the counts (no cells)
into L3 `map.walkability`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "kb" / "map_agreement.json"
DECISION = (
    "Batt 2026-10-15, decision 4: every walk rule and planner uses only cells walkable in BOTH "
    "the client's GAT and the server's map cache (poring_dataset.walkable.both)"
)
COUNTED = (
    "counts on the two grids' overlap EXCLUDING the server's last row and column (always NOPASS "
    "there); client-walkable cells on that edge and beyond the server's grid are counted apart "
    "(edge_client_walkable, outside_client_walkable) and are never walkable for a walk either"
)


def l3_maps(kb: Path) -> list[str]:
    """The maps L3 lists (route.json's warp lists); none when the KB is not built."""
    p = kb / "route.json"
    if not p.exists():
        return []
    return sorted(json.loads(p.read_text()).get("warps") or {})


def gat_maps(gat_dir: Path) -> list[str]:
    return sorted(p.stem for p in gat_dir.glob("*.gat")) if gat_dir.is_dir() else []


def _cells(mask: Any) -> list[list[int]]:
    ys, xs = np.nonzero(mask)
    return [[int(x), int(y)] for x, y in zip(xs.tolist(), ys.tolist(), strict=True)]


def compare(names: Iterable[str], gat_dir: Path, server: Mapping[str, Any],
            cells: bool = True) -> dict[str, Any]:  # fmt: skip
    """{"maps": {map: agreement (+ the cell lists)}, "missing": {"client_gat": [...],
    "server_cache": [...]}} for ``names``."""
    from poring_dataset import gat as gatmod
    from poring_dataset import walkable as wk

    maps: dict[str, Any] = {}
    no_gat: list[str] = []
    no_server: list[str] = []
    for name in sorted(set(names)):
        path = gat_dir / f"{name}.gat"
        grid = server.get(name)
        if not path.exists():
            no_gat.append(name)
        if grid is None:
            no_server.append(name)
        if not path.exists() or grid is None:
            continue
        gat = gatmod.parse(path.read_bytes())
        row: dict[str, Any] = dict(wk.agreement(gat, grid))
        if cells:
            client = np.asarray(gat.walkable(), dtype=bool)
            h, w = client.shape
            hi, wi = min(h, grid.ys - 1), min(w, grid.xs - 1)
            c, s = client[:hi, :wi], wk.server_passable(grid)[:hi, :wi]
            row["client_only_cells"] = _cells(c & ~s)
            row["server_only_cells"] = _cells(s & ~c)
        maps[name] = row
    return {"maps": maps, "missing": {"client_gat": no_gat, "server_cache": no_server}}


def table(doc: Mapping[str, Any]) -> str:
    """The per-map count table (plain text)."""
    head = (f"{'map':12s} {'client':>9s} {'server':>9s} {'client_w':>8s} {'server_w':>8s} "
            f"{'client_only':>11s} {'server_only':>11s} {'both':>7s} {'edge':>5s} "
            f"{'outside':>7s}")  # fmt: skip
    rows = [head]
    for name, a in doc["maps"].items():
        cs, ss = "x".join(map(str, a["client_size"])), "x".join(map(str, a["server_size"]))
        rows.append(f"{name:12s} {cs:>9s} {ss:>9s} {a['client_walkable']:8d} "
                    f"{a['server_walkable']:8d} {a['client_only']:11d} {a['server_only']:11d} "
                    f"{a['both']:7d} {a['edge_client_walkable']:5d} "
                    f"{a['outside_client_walkable']:7d}"
                    + ("  SIZE DIFFERS" if a["size_differs"] else ""))  # fmt: skip
    miss = doc["missing"]
    rows.append(f"no client GAT ({len(miss['client_gat'])}): {', '.join(miss['client_gat'])}")
    rows.append(f"no server cache entry ({len(miss['server_cache'])}): "
                f"{', '.join(miss['server_cache'])}")  # fmt: skip
    return "\n".join(rows)


def build(gat_dir: Path, mapcache_dir: Path, kb: Path, cells: bool = True) -> dict[str, Any]:
    """The whole record (the maps of the GAT directory and of L3; the lock-checked cache)."""
    from poring_dataset import mapcache

    server = mapcache.load(mapcache_dir, prere=True)
    lock = json.loads(mapcache.LOCK.read_text())
    got = compare([*gat_maps(gat_dir), *l3_maps(kb)], gat_dir, server, cells)
    return {
        "decision": DECISION, "counted": COUNTED,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "never_commit": "client-derived (GAT) and GPL-derived (rAthena map cache) cells",
        "gat_dir": str(gat_dir), "mapcache_dir": str(mapcache_dir), "prere": True,
        "mapcache_ref": lock.get("rathena_ref"),
        "mapcache_sha256": {k: v["sha256"] for k, v in lock["files"].items()},
        **got,
    }  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    from poring_dataset import mapcache
    from poring_dataset.camera import GAT_DIR

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="write the record and print the per-map table")
    b.add_argument("--gat-dir", type=Path, default=GAT_DIR)
    b.add_argument("--mapcache-dir", type=Path, default=mapcache.GENERATED)
    b.add_argument("--kb", type=Path, default=ROOT / "data" / "kb")
    b.add_argument("--out", type=Path, default=DEFAULT_OUT)
    a = ap.parse_args(argv)
    doc = build(a.gat_dir, a.mapcache_dir, a.kb)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(doc, indent=1))
    print(table(doc))
    print(json.dumps({"out": str(a.out), "maps": len(doc["maps"]),
                      "missing": {k: len(v) for k, v in doc["missing"].items()}}))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
