"""Walkability for a walk: the CLIENT's GAT AND the SERVER's map cache.

Batt's decision 4 (2026-10-15): "Client GAT vs server map cache: every walk rule and planner uses
only cells walkable in BOTH sources (intersection); record the mismatch per map as L2/L3
knowledge."

- The client draws and paths on its GAT (gat.Gat.walkable(): types 1 wall, 5 cliff are not).
- The server decides with its map cache (mapcache.MapGrid.nopass: rAthena's CELL_CHKNOPASS, the
  last row and column never passable). An @warp onto a server-NOPASS cell drops the GM on a random
  free cell nearby; a click there is never the server's destination.
- The two differ on some maps (2026-10-13/15: alberta, morocc, izlude -- a different map size --,
  geffen), and nearly every client GAT marks the server's last row and column walkable.

`both` is the grid every live walk rule and planner takes; `agreement` is the per-map mismatch
record (L3 map.walkability, scripts/kb_bindings.py; data/kb/map_agreement.json,
scripts/map_agreement.py). Both sources are read at run time (the GAT is client data in /dev/shm,
the map cache server data in _generated/); nothing here ships either.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

import numpy as np
import numpy.typing as npt

from poring_dataset import gat as gatmod
from poring_dataset import mapcache
from poring_dataset.camera import GAT_DIR

Mask = npt.NDArray[np.bool_]


class MapSourceError(LookupError):
    """A source lacks the map (no GAT, no server grid): walkability is unknown, fail closed."""


class Agreement(TypedDict):
    client_size: list[int]  # [width, height]
    server_size: list[int]  # [xs, ys]
    size_differs: bool
    client_walkable: int
    server_walkable: int
    client_only: int  # client-walkable, server-NOPASS
    server_only: int  # server-walkable, client-not
    both: int
    edge_client_walkable: int  # client-walkable cells ON the server's last row / column
    outside_client_walkable: int  # client-walkable cells outside the server's grid


def server_passable(grid: mapcache.MapGrid) -> Mask:
    """(ys, xs): True where ``grid.nopass(x, y)`` is False -- the cell types (1, 5 not walkable)
    and the last row and column never passable (CELL_CHKNOPASS)."""
    types = np.frombuffer(grid.cells, dtype=np.uint8).reshape(grid.ys, grid.xs)
    ok = ~np.isin(types, list(mapcache.NOT_WALKABLE))
    ok[grid.ys - 1, :] = False
    ok[:, grid.xs - 1] = False
    return np.asarray(ok, dtype=np.bool_)


def both(gat: gatmod.Gat, grid: mapcache.MapGrid | None) -> Mask:
    """(height, width) like the CLIENT grid: True only where the client GAT is walkable AND the
    server lets a character stand (``grid.nopass`` False). A client cell outside the server's grid
    is False. ``grid`` None (the server's cache lacks the map) raises: fail closed."""
    if grid is None:
        raise MapSourceError("the server's map cache lacks this map: walkability unknown")
    client = np.asarray(gat.walkable(), dtype=np.bool_)
    h, w = client.shape
    hh, ww = min(h, grid.ys), min(w, grid.xs)
    out = np.zeros((h, w), dtype=np.bool_)
    out[:hh, :ww] = client[:hh, :ww] & server_passable(grid)[:hh, :ww]
    return out


def agreement(gat: gatmod.Gat, grid: mapcache.MapGrid | None) -> Agreement:
    """The two sources' walkability compared, counted on their OVERLAP EXCLUDING the server's
    last row and column (always NOPASS on the server; the 2026-10-13 rule, as
    /dev/shm/poring-lab-tmp/mapagree/agree.py counted it). The client-walkable cells left out of
    that comparison are counted apart: ``edge_client_walkable`` (on the server's last row /
    column) and ``outside_client_walkable`` (beyond the server's grid). ``both`` equals
    ``both(gat, grid).sum()``. ``grid`` None raises (fail closed)."""
    if grid is None:
        raise MapSourceError("the server's map cache lacks this map: no agreement")
    client = np.asarray(gat.walkable(), dtype=np.bool_)
    h, w = client.shape
    server = server_passable(grid)
    hi, wi = min(h, grid.ys - 1), min(w, grid.xs - 1)  # the overlap, the server's edge excluded
    c, s = client[:hi, :wi], server[:hi, :wi]
    inside = np.zeros((h, w), dtype=np.bool_)
    inside[: min(h, grid.ys), : min(w, grid.xs)] = True
    interior = np.zeros((h, w), dtype=np.bool_)
    interior[:hi, :wi] = True
    return Agreement(
        client_size=[w, h],
        server_size=[grid.xs, grid.ys],
        size_differs=(w, h) != (grid.xs, grid.ys),
        client_walkable=int(c.sum()),
        server_walkable=int(s.sum()),
        client_only=int((c & ~s).sum()),
        server_only=int((s & ~c).sum()),
        both=int((c & s).sum()),
        edge_client_walkable=int((client & inside & ~interior).sum()),
        outside_client_walkable=int((client & ~inside).sum()),
    )


def server_grid(map_name: str, mapcache_dir: Path = mapcache.GENERATED, *,
                prere: bool = True) -> mapcache.MapGrid:  # fmt: skip
    """The server's grid for ``map_name`` (the lab's pre-renewal precedence, lock-checked);
    MapSourceError when the cache lacks the map."""
    grid = mapcache.load(mapcache_dir, prere=prere).get(map_name)
    if grid is None:
        raise MapSourceError(f"the server's map cache ({mapcache_dir}) lacks {map_name}: "
                             "walkability unknown (fail closed)")  # fmt: skip
    return grid


def load_both(map_name: str, gat_dir: Path = GAT_DIR, mapcache_dir: Path = mapcache.GENERATED,
              *, prere: bool = True) -> tuple[gatmod.Gat, Mask]:  # fmt: skip
    """(the client's Gat, ``both``'s mask) for ``map_name``; MapSourceError when either source
    lacks the map."""
    path = gat_dir / f"{map_name}.gat"
    if not path.exists():
        raise MapSourceError(f"no client GAT for {map_name} in {gat_dir}: walkability unknown "
                             "(fail closed; grf_read.py extract)")  # fmt: skip
    gat = gatmod.parse(path.read_bytes())
    return gat, both(gat, server_grid(map_name, mapcache_dir, prere=prere))
