#!/usr/bin/env python3
"""An OFFLINE patrol walk on a map's route (2026-10-26, before --walk-through went live): the
runner's own grid, route(), through_path() and walk_target(), with dungeon_hunt's patrol logic
mirrored (patrol_goal's reached / next, the walk tick's trim / re-route / pass, the replan when a
leg's end is near). It checks LOGIC only, not timing: does the walk finish its laps, visiting
every waypoint in order, without turning back?

It found a real bug the day it was written: a through-leg that ended near its end replanned back
to the waypoint it had run through, and the walk oscillated at gef_fild10's waypoint 64.

    patrol_sim.py [--map gef_fild10] [--laps 2] [--ticks 6000]
        prints one line per (walk-ahead, walk-through, cells per decision) case

The world model: each decision clicks walk_target(path, ahead, fits) with ``fits`` = within
VIEW_CELLS (Chebyshev) and no zone segment crossed, and our cell moves ``step`` cells along the
path toward that target (the client's walk between two decisions). Map data comes from the local
GAT and KB (never committed); nothing here reads a packet or touches the client.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

VIEW_CELLS = 14
CASES = ((7, False, 3), (7, False, 6), (7, False, 10), (12, True, 2), (12, True, 3),
         (12, True, 6), (12, True, 10), (14, True, 6))  # fmt: skip

Cell = tuple[int, int]


def cheb(a: Sequence[int], b: Sequence[int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def order_breaks(order: Sequence[int], n: int) -> int:
    """PURE: how many consecutive reached waypoints are NOT the next one on the loop."""
    return sum(1 for a, b in zip(order, order[1:], strict=False) if (b - a) % n != 1)


def simulate(env: dict[str, Any], ahead: int, through: bool, step: int, laps: int = 2,
             ticks: int = 6000) -> dict[str, Any]:  # fmt: skip
    import dungeon_hunt as dh
    import map_routes as mroutes
    import map_zones as mz

    rt, wps, okr, carved, zones = env["rt"], env["wps"], env["okr"], env["carved"], env["zones"]
    st: dict[str, Any] = {"i": None, "laps": 0, "through": None}
    order: list[int] = []

    def advance() -> None:
        order.append(st["i"])
        st["i"] = mroutes.next_index(rt, st["i"])
        if st["i"] == 0:
            st["laps"] += 1

    here: Cell = wps[0]
    goal_path: list[Cell] | None = None
    clicks = 0
    for _ in range(ticks):
        near_end = goal_path is not None and len(goal_path) >= 2 and cheb(goal_path[-1], here) <= 2
        if goal_path is None or len(goal_path) < 2 or near_end:
            if near_end and st["through"] is not None:
                advance()
                st["through"] = None
            if st["i"] is None:
                st["i"] = mroutes.entry_index(rt, here)
            for _k in range(len(wps)):
                if not mroutes.reached(here, wps[st["i"]], dh.WP_TOL):
                    break
                advance()
            goal = wps[st["i"]]
            goal_path = dh.route(okr, carved, here, goal)
            st["through"] = None
            ni = mroutes.next_index(rt, st["i"])
            if through and ni is not None and goal_path:
                ext = dh.through_path(goal_path, dh.route(okr, carved, goal, wps[ni]))
                if len(ext) > len(goal_path):
                    goal_path, st["through"] = ext, goal
        if goal_path is None:
            break
        if here in goal_path:
            goal_path = goal_path[goal_path.index(here) :]
        else:
            goal_path = dh.route(okr, carved, here, goal_path[-1])
        if st["through"] is not None and (not goal_path or st["through"] not in goal_path):
            advance()
            st["through"] = None
        if not goal_path or len(goal_path) < 2:
            continue

        def fits(c: Cell, h: Cell = here) -> bool:
            return cheb(c, h) <= VIEW_CELLS and mz.segment_violates(h, c, zones) is None

        wt = dh.walk_target(goal_path, ahead, fits)
        if wt is None:
            continue
        clicks += 1
        here = goal_path[min(wt[0], step)]
        if st["laps"] >= laps:
            break
    return {"ahead": ahead, "through": through, "step": step, "laps": st["laps"],
            "reached": len(order), "clicks": clicks,
            "order_breaks": order_breaks(order, len(wps))}  # fmt: skip


def load(map_: str) -> dict[str, Any]:
    import map_routes as mroutes
    import map_zones as mz
    import numpy as np
    from anim_region import stand_grid

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    gat = gatmod.parse((cam.GAT_DIR / f"{map_}.gat").read_bytes())
    ok = stand_grid(map_, gat)
    zones = mz.load(map_, shape=ok.shape)
    okr = mz.route_grid(ok, zones)
    okr = okr & ~mz.sealed_off(ok, okr)
    rt = mroutes.load(map_).routes[0]
    return {"rt": rt, "wps": [tuple(w) for w in rt.waypoints], "okr": okr, "zones": zones,
            "carved": np.zeros_like(okr, dtype=bool)}  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("--map", default="gef_fild10")
    ap.add_argument("--laps", type=int, default=2)
    ap.add_argument("--ticks", type=int, default=6000)
    a = ap.parse_args()
    env = load(a.map)
    bad = 0
    for ahead, through, step in CASES:
        out = simulate(env, ahead, through, step, a.laps, a.ticks)
        bad += out["laps"] < a.laps or out["order_breaks"] > 0
        print(json.dumps(out), flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
