"""PATROL ROUTES as the linter reads them (Batt 2026-10-22: the hunt block's `search_route` option
`patrol_route`; docs/planning/blocks-from-hunt-flow.md section 7d).

- **The file stays the source of truth:** `config/routes/<map>.yaml`, its format and its
  fail-closed loader (`scripts/map_routes.py`, config/routes/README.md). Nothing here re-reads it:
  the caller's PROVIDER loads a file with the loader (`scripts/flow_routes.py`) and hands the
  linter what it found, as the zones provider does (`poring_flow.zones`).
- **A provider** maps a map id to `RouteInfo`, to None when there is no file for that map (a
  patrol hunt there is refused: no route to walk), or raises `RoutesUnreadable` for a file that is
  there but wrong. Tests inject synthetic providers.
- The linter's rules (`poring_flow.lint.hunt`): a patrol hunt's map has a routes file
  (`patrol_route_missing`) and the loader accepts it (`patrol_route_unreadable`). The run-start
  check refuses a patrol hunt when no provider was given (`poring_flow.runstart`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

Cell = tuple[int, int]


@dataclass(frozen=True)
class RouteInfo:
    map: str
    sha256: str  # the file's sha256 (the loader's: of its bytes)
    route: str  # the id of the route a patrol hunt walks: the file's first
    kind: str  # "loop" | "path"
    waypoints: tuple[Cell, ...]  # its listed order = the walking direction
    routes: int = 1  # how many routes the file holds


class RoutesUnreadable(ValueError):
    """A routes file that is there but wrong: the loader refused it (the run must not start)."""


# map id -> its patrol route (None: no file for that map); raises RoutesUnreadable
RoutesProvider = Callable[[str], RouteInfo | None]


def none_provider(map_id: str) -> RouteInfo | None:
    """A provider for a world without routes files (every map: no file)."""
    return None
