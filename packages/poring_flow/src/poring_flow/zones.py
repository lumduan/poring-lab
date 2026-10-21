"""Map zones as MAP-NODE DATA: the shape the linter reads (ADR-0020 Amendment A 4, DRAFT;
docs/planning/blocks-from-hunt-flow.md section 3; Batt 2026-10-21 D6: export only for now).

- **The file stays the source of truth:** `config/map_zones/<map>.yaml`, its format and its
  fail-closed loader (`scripts/map_zones.py`, config/map_zones/README.md), unchanged. This module
  re-implements none of the geometry: the caller's PROVIDER rasterises a file with the loader's own
  functions (`scripts/flow_zones.py`) and hands the linter the closed cells.
- **A provider** maps a map id to `ZoneInfo`, to None when there is no file for that map (no zones:
  nothing changes, as in the runner), or raises `ZonesUnreadable` for a file that is there but
  wrong. Tests inject synthetic providers.
- **The map node names its file** (`ir.ZonesRef`: map + sha256), so approval binds the zones a
  person reviewed. The rules (`poring_flow.lint.zones`): the reference is the block's own map; the
  named file is there and unchanged; a file for the block's map is named; no entry inside a no-enter
  area; no walk exit closed or cut off by the zones; a warning when every spawn cell of a target is
  closed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

Cell = tuple[int, int]


@dataclass(frozen=True)
class ZoneInfo:
    map: str
    sha256: str  # the file's sha256 (the loader's: of its bytes)
    closed: frozenset[Cell]  # every cell closed to the character: both kinds (the runner's grid)
    no_enter: frozenset[Cell]  # the no-enter areas' cells (an entry there is an error)


class ZonesUnreadable(ValueError):
    """A zones file that is there but wrong: the loader refused it (the run must not start)."""


# map id -> its zones (None: no file for that map); raises ZonesUnreadable
ZonesProvider = Callable[[str], ZoneInfo | None]


def none_provider(map_id: str) -> ZoneInfo | None:
    """A provider for a world without zones files (every map: no file)."""
    return None
