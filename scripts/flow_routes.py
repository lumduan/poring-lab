#!/usr/bin/env python3
"""The flow linter's PATROL ROUTES provider: each map's routes file through the runner's own loader
(docs/planning/blocks-from-hunt-flow.md section 7d; the twin of scripts/flow_zones.py).

    provider(root=config/routes, shapes=None)  ->  map id -> poring_flow.patrol.RouteInfo | None

The file and `scripts/map_routes.py` stay the source of truth; nothing here re-reads or re-checks
it. A map without a file gives None (no route), a file the loader refuses raises
`RoutesUnreadable` (fail closed). `shape` (h, w), when given per map, makes the loader refuse a
waypoint off the map. The RouteInfo describes the file's FIRST route: the one a patrol hunt walks.

    flow_routes.py <map> [--root DIR]    print the map's RouteInfo
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import map_routes as mr  # noqa: E402

from poring_flow.patrol import RouteInfo, RoutesUnreadable  # noqa: E402


def info(routes: mr.Routes) -> RouteInfo:
    first = routes.routes[0]
    return RouteInfo(map=routes.map, sha256=routes.sha256, route=first.id, kind=first.kind,
                     waypoints=first.waypoints, routes=len(routes.routes))  # fmt: skip


def provider(
    root: Path | str = mr.ROUTES_DIR, shapes: Mapping[str, tuple[int, int]] | None = None
) -> Callable[[str], RouteInfo | None]:
    def get(map_id: str) -> RouteInfo | None:
        try:
            r = mr.load(map_id, root, shape=(shapes or {}).get(map_id))
        except mr.RouteError as e:
            raise RoutesUnreadable(str(e)) from None
        return None if r is None else info(r)

    return get


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("map")
    ap.add_argument("--root", default=str(mr.ROUTES_DIR))
    a = ap.parse_args()
    r = provider(a.root)(a.map)
    print(json.dumps({"map": a.map, "route": None if r is None else dataclasses.asdict(r)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
