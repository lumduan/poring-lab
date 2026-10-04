#!/usr/bin/env python3
"""Evidence for the clean walk search (Post-S2 round E1, 2026-10-04): replay the walks recorded in
the NAS datasets' packets and check poring_dataset.walk against what the server actually did.

    walk_check.py [--datasets /mnt/poring-lab-datasets] [--compare-port]

Packets give each walk's start, end and start tick, never the cells in between, so the checks are:
  * found: the share of recorded walks (self_move + entities' move entries) the search finds a path
    for (the server walked them, so a path must exist);
  * timing: where the walk was CUT -- an entity_stop, or the next self_move of the same unit --
    the cell the server reports vs the cell our path + rAthena's step timing predicts for that tick
    (Chebyshev cells; 0 = exact). Arrivals (a stop at the target) are counted separately;
  * --compare-port: how often the new paths EQUAL the removed GPL port's (paths.py), as a report
    only (equal-length alternatives are legitimate). It ran once, before the deletion (2026-10-04:
    2534/2540 equal; THIRD_PARTY.md); today it needs the port checked out from git history.

Prints a JSON summary. Reads packets.jsonl.gz only (small); no frames.
"""

import argparse
import gzip
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from poring_dataset import mapcache  # noqa: E402
from poring_dataset.walk import walk_path  # noqa: E402
from poring_packets.world import MOVE_COST, MOVE_DIAGONAL_COST, TICK_MOD  # noqa: E402


def predicted(cells: list[tuple[int, int]], x0: int, y0: int, speed: int, elapsed: int) -> tuple:
    x, y = x0, y0
    for cx, cy in cells:
        step = speed * (MOVE_DIAGONAL_COST if (cx != x and cy != y) else MOVE_COST) // MOVE_COST
        if elapsed < step:
            return (x, y) if elapsed < step / 2 else (cx, cy)  # the cell the unit occupies
        elapsed -= step
        x, y = cx, cy
    return x, y


def walks(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each recorded walk with where it was cut (if it was)."""
    out: list[dict[str, Any]] = []
    current: dict[Any, dict[str, Any]] = {}
    mapname = None
    speed = 150
    aid = None
    for e in sorted(events, key=lambda e: int(e["t_mono_ns"])):
        t = e["type"]
        if t == "login_accepted":
            aid = int(e["aid"])
        elif t in ("map_change", "char_selected"):
            mapname = str(e["map"]).lower().removesuffix(".gat")
            current.clear()
        elif t == "stat_change" and e.get("name") == "speed":
            speed = int(e["value"])
        elif t == "self_move" and mapname:
            prev = current.get("self")
            if prev is not None:
                prev["cut"] = {"tick": int(e["server_tick"]), "x": int(e["x0"]), "y": int(e["y0"])}
            w = {"map": mapname, "unit": "self", "x0": int(e["x0"]), "y0": int(e["y0"]),
                 "x1": int(e["x1"]), "y1": int(e["y1"]), "tick": int(e["server_tick"]),
                 "speed": speed}  # fmt: skip
            current["self"] = w
            out.append(w)
        elif t == "entity_appear" and e.get("x1") is not None and mapname:
            w = {"map": mapname, "unit": int(e["gid"]), "x0": int(e["x"]), "y0": int(e["y"]),
                 "x1": int(e["x1"]), "y1": int(e["y1"]), "tick": int(e["move_start_tick"]),
                 "speed": int(e.get("speed") or 150)}  # fmt: skip
            current[int(e["gid"])] = w
            out.append(w)
        elif t == "entity_stop":
            gid = int(e["gid"])
            w = current.get("self" if gid == aid else gid)
            if w is not None and "cut" not in w:
                tick = int(e["t_mono_ns"]) // 1_000_000 % TICK_MOD
                w["cut"] = {"tick": tick, "x": int(e["x"]), "y": int(e["y"])}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--datasets", type=Path, default=Path("/mnt/poring-lab-datasets"))
    ap.add_argument("--compare-port", action="store_true")
    a = ap.parse_args()
    grids = mapcache.load(prere=True)
    port = None
    if a.compare_port:
        from poring_dataset.paths import path_search as port  # the GPL port, before its removal
    all_walks: list[dict[str, Any]] = []
    sessions = []
    for packets in sorted(a.datasets.glob("*/packets.jsonl.gz")):
        with gzip.open(packets, "rt") as fh:
            events = [json.loads(line) for line in fh]
        found = walks(events)
        sessions.append({"session": packets.parent.name, "walks": len(found)})
        all_walks += found
    stats = {"walks": 0, "no_map": 0, "found": 0, "not_found": [], "cut": 0, "cut_exact": 0,
             "cut_err_cells": [], "arrivals": 0, "arrival_exact": 0, "port_compared": 0,
             "port_equal": 0, "port_same_length": 0, "port_only_one_found": 0}  # fmt: skip
    for w in all_walks:
        grid = grids.get(w["map"])
        if grid is None:
            stats["no_map"] += 1
            continue
        stats["walks"] += 1
        path = walk_path(grid, w["x0"], w["y0"], w["x1"], w["y1"])
        if path is None:
            if len(stats["not_found"]) < 10:
                stats["not_found"].append({k: w[k] for k in ("map", "x0", "y0", "x1", "y1")})
            continue
        stats["found"] += 1
        if port is not None:
            old = port(grid, w["x0"], w["y0"], w["x1"], w["y1"])
            if old is None:
                stats["port_only_one_found"] += 1
            else:
                stats["port_compared"] += 1
                stats["port_equal"] += int(old == path)
                stats["port_same_length"] += int(len(old) == len(path))
        cut = w.get("cut")
        if cut is None:
            continue
        elapsed = (cut["tick"] - w["tick"]) % TICK_MOD
        if elapsed > TICK_MOD // 2:
            continue  # the stop predates the walk's start tick (clock edge)
        px, py = predicted(path, w["x0"], w["y0"], w["speed"], elapsed)
        err = max(abs(px - cut["x"]), abs(py - cut["y"]))
        if (cut["x"], cut["y"]) == (w["x1"], w["y1"]):
            stats["arrivals"] += 1
            stats["arrival_exact"] += int(err == 0)
        else:
            stats["cut"] += 1
            stats["cut_exact"] += int(err == 0)
            stats["cut_err_cells"].append(err)
    errs = sorted(stats.pop("cut_err_cells"))
    stats["cut_err_p50"] = errs[len(errs) // 2] if errs else None
    stats["cut_err_p95"] = errs[min(len(errs) - 1, int(0.95 * len(errs)))] if errs else None
    stats["cut_err_le1"] = sum(1 for e in errs if e <= 1)
    print(json.dumps({"sessions": sessions, **stats}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
