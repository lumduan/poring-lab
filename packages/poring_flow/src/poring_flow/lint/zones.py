"""The map node's ZONES in the linter (ADR-0020 Amendment A 4, DRAFT; blocks-from-hunt-flow.md
section 3, B1, 2026-10-21). The zones file and its loader stay the source of truth; the provider
(`poring_flow.zones`) hands the linter each map's file as the loader reads it.

Layer 1:
- `zones_map`: a map node's zones reference names the block's own map.
Layer 2, the file (skipped when no provider is given; the run-start check then refuses a flow that
names zones):
- `zones_unreadable`: the loader refuses the block's map's file (fail closed);
- `zones_missing`: the node names a zones file, the map has none (the file is gone);
- `zones_changed`: the file's sha256 is not the one the node names (approval binds the sha256);
- `zones_unreferenced`: the block's map has a zones file the node does not name.
Layer 3, on the walkable grid minus the zones (the runner's route grid):
- `zones_entry`: an entry cell inside a no-enter area;
- `zones_exit`: a walk exit's warp cell closed by the zones, or behind them: no entry reaches it
  once the zones close their cells, though one did before;
- `zones_targets` (warning): every spawn cell of a target species is closed.
"""

from __future__ import annotations

from collections import deque

from poring_flow import ir
from poring_flow.lint.common import Ctx
from poring_flow.sheet import MapSheet, Walk
from poring_flow.zones import Cell, ZoneInfo, ZonesUnreadable


def check(ctx: Ctx) -> None:
    for b in ctx.blocks:
        ref = b.zones
        if ref is not None and ref.map != b.map.map:
            ctx.add(
                "zones_map",
                "error",
                1,
                b.name,
                f"its zones name map {ref.map}; the block is on {b.map.map}",
            )
        if ctx.zones is None:
            continue
        try:
            info = ctx.zones(b.map.map)
        except ZonesUnreadable as e:
            ctx.add(
                "zones_unreadable",
                "error",
                2,
                b.name,
                f"the zones file of {b.map.map} is refused by its loader: {e}",
            )
            continue
        if info is None:
            if ref is not None:
                ctx.add(
                    "zones_missing",
                    "error",
                    2,
                    b.name,
                    f"it names zones {ref.sha256[:12]}, and {b.map.map} has no zones file",
                )
            continue
        if ref is None:
            ctx.add(
                "zones_unreferenced",
                "error",
                2,
                b.name,
                f"{b.map.map} has a zones file ({info.sha256[:12]}): the map node must name it "
                "(zones=zones(...))",
            )
            continue
        if ref.sha256 != info.sha256:
            ctx.add(
                "zones_changed",
                "error",
                2,
                b.name,
                f"it names zones {ref.sha256[:12]}; the file is now {info.sha256[:12]}: a person "
                "reviews the change and the flow is approved again",
            )
        _layer3(ctx, b, info, ctx.sheet(b.map.map))


def _reach(walk: Walk, sources: list[Cell], closed: frozenset[Cell]) -> set[Cell]:
    """Every cell reachable from the sources on the walkable grid minus `closed`, with RO's
    8-way moves (a diagonal needs both orthogonal neighbours open), as `Walk.route`."""

    def open_(c: Cell) -> bool:
        return walk.walkable(c) and c not in closed

    seen = {s for s in sources if open_(s)}
    todo = deque(seen)
    while todo:
        c = todo.popleft()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                n = (c[0] + dx, c[1] + dy)
                if n in seen or (dx == dy == 0) or not open_(n):
                    continue
                if dx and dy and not (open_((c[0] + dx, c[1])) and open_((c[0], c[1] + dy))):
                    continue
                seen.add(n)
                todo.append(n)
    return seen


def _layer3(ctx: Ctx, b: ir.MapBlock, info: ZoneInfo, sheet: MapSheet | None) -> None:
    starts: list[Cell] = []
    for e in b.entries:
        if e.at is None:
            continue
        c = (e.at.x, e.at.y)
        starts.append(c)
        if c in info.no_enter:
            ctx.add(
                "zones_entry",
                "error",
                3,
                b.name,
                f"entry {e.name} at ({c[0]}, {c[1]}) is inside a no-enter area of its zones",
            )
    walk = sheet.walk if sheet is not None else None
    reach_free: set[Cell] | None = None
    reach_zoned: set[Cell] | None = None
    for site in ir.sites(ctx.flow):
        if site.block is not b or not isinstance(site.stmt, ir.TakeExit):
            continue
        warp = site.stmt.exit.warp
        if site.stmt.exit.kind != "walk_exit" or warp is None:
            continue
        c = (warp.x, warp.y)
        if c in info.closed:
            ctx.add(
                "zones_exit",
                "error",
                3,
                site.path,
                f"the walk exit at ({c[0]}, {c[1]}) is closed by the zones",
            )
            continue
        if walk is None or not starts:
            continue
        if reach_free is None:
            reach_free = _reach(walk, starts, frozenset())
            reach_zoned = _reach(walk, starts, info.closed)
        if c in reach_free and reach_zoned is not None and c not in reach_zoned:
            ctx.add(
                "zones_exit",
                "error",
                3,
                site.path,
                f"the walk exit at ({c[0]}, {c[1]}) lies behind the zones: no entry reaches it "
                "once they close their cells",
            )
    if sheet is None:
        return
    for t in b.targets:
        lines = [s for s in sheet.spawns if s.mob == t.id]
        if not lines:
            continue  # species lists (layer 2) report a target that does not spawn here
        cells: set[Cell] = set()
        for s in lines:
            area = s.cells(walk)
            if area is None:  # anywhere on the map: closed only if the whole map is
                if walk is None:
                    cells.add((-1, -1))  # unknown map: never call it closed
                    break
                area = {
                    (x, y)
                    for y, row in enumerate(walk.rows)
                    for x, ch in enumerate(row)
                    if ch == "."
                }
            cells |= area
        if cells and cells <= info.closed:
            ctx.add(
                "zones_targets",
                "warning",
                3,
                b.name,
                f"every spawn cell of target mob {t.id} on {b.map.map} is closed by the zones: "
                "the block never reaches it",
            )
