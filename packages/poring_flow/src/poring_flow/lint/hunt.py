"""Block parameters that are RULE VERSIONS or OPTIONS, blocks that attack the map block's targets,
the hunt block's MELEE RING and its PATROL ROUTE (ADR-0020 Amendment A 1 + 3, DRAFT; docs/planning/
blocks-from-hunt-flow.md B1, 2026-10-21, and sections 7c and 7d, Batt 2026-10-22).

- `rule_version` (layer 1): a parameter with `choices` in the registry (the hunt block's strike,
  engage, dead, loot and search) takes one of them, as a literal. A rule version is `name@N`: its
  numbers are the ones PARAMS[N] ran (scripts/hunt_config.py); "the engine refuses an unknown rule
  version", and so does the linter, before approval.
- `param_option` (layer 1): a parameter with `options` (the hunt block's engage_source and
  search_route) takes one of them, as a literal; absent means its `default`.
- `needs_targets` (layer 2): a block that attacks the map block's TARGET species (13.3) runs in a
  map block, and that block lists its targets.
- THE MELEE RING (Batt 2026-10-22 ~13:45: "the option strikes EVERY monster in melee range, so its
  lint/readiness must refuse it on maps with an ignore list or non-target species, and on any
  server other than the lab (no kill-stealing on shared servers)"). For a hunt whose
  engage_source is `melee_ring`:
  - `melee_ring_server` (layer 1): the flow's target server is the lab's own (`LAB_SERVERS`);
  - `melee_ring_ignore` (layer 2): its map block has NO ignore list;
  - `melee_ring_species` (layer 2): every species that can be on the map is a TARGET. The data is
    the static data the linter is given (`World`): the map sheet's spawn lines (in the backend the
    local KB's: a generated sheet file, else `kbsheet`'s sheet from data/kb spawns.json) plus,
    through `Mob.turns_into`, what they turn into. No sheet for the map is a refusal (fail
    closed): nothing proves the species list then.
  The run-start check adds the ATTESTED environment (`runstart`: the server the run acts on, known
  only at run time). The NPC sprite guard and every gate of the engine stay underneath; none is a
  parameter and none is weakened here.
- THE PATROL ROUTE (Batt 2026-10-22, the Crusader's orcsdun01 demo: a fixed circuit of waypoints
  walked in ONE direction). For a hunt whose search_route is `patrol_route`, the map node's map
  must have a reviewed routes file the runner's loader accepts (`config/routes/<map>.yaml`,
  `scripts/map_routes.py`), as the routes provider reports it (`poring_flow.patrol`):
  - `patrol_route_missing` (layer 2): the map has no routes file;
  - `patrol_route_unreadable` (layer 2): the loader refuses the file (fail closed).
  Without a provider these checks are skipped, as the zones file checks are, and the run-start
  check refuses a patrol hunt (`runstart`: fail closed).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from poring_flow import ir
from poring_flow.catalogue import BlockSpec
from poring_flow.lint.common import Ctx
from poring_flow.patrol import RoutesUnreadable
from poring_flow.sheet import World

ENGAGE_SOURCE = "engage_source"
MELEE_RING = "melee_ring"
SEARCH_ROUTE = "search_route"
PATROL_ROUTE = "patrol_route"
# The lab's OWN server (ADR-0006 environment 1, config/environments.yaml `lab-rathena`): a server
# nobody else plays on, so striking every monster in melee range steals no one's kill. Deliberately
# a fixed list, not the interlock's `allowed` status: an allowed SHARED server (the community one,
# if it is ever approved) must still refuse the melee ring. lab-rathena-th (environment 1b,
# stopped, not adopted) is left out -- Batt 2026-10-23, decision 9: "not added to LAB_SERVERS";
# adding a server here is a reviewed code change.
LAB_SERVERS = frozenset({"lab-rathena"})


def option(a: ir.ActionStmt, spec: BlockSpec, name: str) -> str | None:
    """The action's OPTION parameter ``name`` as a literal (its default when absent); None when the
    block has no such parameter or the value is not a literal (param_option names that)."""
    p = next((p for p in spec.params if p.name == name), None)
    if p is None:
        return None
    e = a.params.get(name)
    if e is None:
        return p.default
    return e.value if isinstance(e, ir.Lit) and isinstance(e.value, str) else None


def engage_source(a: ir.ActionStmt, spec: BlockSpec) -> str | None:
    """The action's engage source (its default when absent; ``option``)."""
    return option(a, spec, ENGAGE_SOURCE)


def search_route(a: ir.ActionStmt, spec: BlockSpec) -> str | None:
    """The action's search route (its default, heading, when absent; ``option``)."""
    return option(a, spec, SEARCH_ROUTE)


def _paths(flow: ir.Flow, specs: Mapping[str, BlockSpec], name: str, value: str) -> list[str]:
    out = []
    for site in ir.sites(flow):
        for a in ir.actions_in(site.stmt):
            spec = specs.get(a.block)
            if spec is not None and option(a, spec, name) == value:
                out.append(site.path)
    return out


def melee_ring_paths(flow: ir.Flow, specs: Mapping[str, BlockSpec]) -> list[str]:
    """The node paths of every action that hunts with the melee ring (runstart reads them)."""
    return _paths(flow, specs, ENGAGE_SOURCE, MELEE_RING)


def patrol_route_paths(flow: ir.Flow, specs: Mapping[str, BlockSpec]) -> list[str]:
    """The node paths of every action that searches by the patrol route (runstart reads them)."""
    return _paths(flow, specs, SEARCH_ROUTE, PATROL_ROUTE)


def species_on(world: World, map_id: str) -> set[int] | None:
    """Every species that can be on a map: its spawn lines and, transitively, what they turn into
    (`Mob.turns_into`; prep.py's training scope reads it the same way). None: no sheet."""
    sheet = world.sheet(map_id)
    if sheet is None:
        return None
    seen = set(sheet.spawned())
    todo = list(seen)
    while todo:
        mob = world.mobs.get(todo.pop())
        for t in mob.turns_into if mob else []:
            if t not in seen:
                seen.add(t)
                todo.append(t)
    return seen


def _ids(ids: Iterable[int]) -> str:
    return ", ".join(f"mob {i}" for i in sorted(ids))


def _melee_ring(ctx: Ctx, site: ir.Site, a: ir.ActionStmt) -> None:
    what = f"{a.block}'s {ENGAGE_SOURCE} {MELEE_RING} strikes EVERY monster in melee range"
    server = ctx.flow.target.server
    if server not in LAB_SERVERS:
        ctx.add(
            "melee_ring_server",
            "error",
            1,
            site.path,
            f"{what}: it runs only on the lab's own server ({', '.join(sorted(LAB_SERVERS))}), "
            f"not on {server} (no kill-stealing on a shared server)",
        )
    b = site.block
    if b is None:
        return  # needs_targets names it: a hunt runs in a map block
    if b.ignore:
        ctx.add(
            "melee_ring_ignore",
            "error",
            2,
            site.path,
            f"{what}, and {b.name} has an IGNORE list ({_ids(m.id for m in b.ignore)}): "
            "refused on a map with one",
        )
    m = b.map.map
    species = species_on(ctx.world, m) if ctx.world is not None else None
    if species is None:
        ctx.add(
            "melee_ring_species",
            "error",
            2,
            site.path,
            f"{what}: no map sheet for {m} is loaded, so nothing proves every species there is "
            "a TARGET (refused, fail closed)",
        )
        return
    others = species - {t.id for t in b.targets}
    if others:
        ctx.add(
            "melee_ring_species",
            "error",
            2,
            site.path,
            f"{what}, and {_ids(others)} can be on {m} without being a TARGET of {b.name}: "
            "refused on a map with a non-target species",
        )


def check(ctx: Ctx) -> None:
    for site in ir.sites(ctx.flow):
        for a in ir.actions_in(site.stmt):
            blk = ctx.cat.blocks.get(a.block)
            if blk is None:
                continue  # unknown_block (layer 1)
            for p in blk.spec.params:
                allowed = p.choices or p.options
                if not allowed or p.name not in a.params:
                    continue
                e = a.params[p.name]
                val = e.value if isinstance(e, ir.Lit) else None
                if isinstance(val, str) and val in allowed:
                    continue
                shown = repr(val) if isinstance(val, str) else ctx.src(e)
                if p.choices:
                    ctx.add(
                        "rule_version",
                        "error",
                        1,
                        site.path,
                        f"{a.block}'s {p.name} takes a rule version ({', '.join(p.choices)}), "
                        f"not {shown}",
                    )
                else:
                    ctx.add(
                        "param_option",
                        "error",
                        1,
                        site.path,
                        f"{a.block}'s {p.name} takes one of ({', '.join(p.options)}"
                        f"{f'; absent = {p.default}' if p.default else ''}), not {shown}",
                    )
            if blk.spec.needs_targets:
                if site.block is None:
                    ctx.add(
                        "needs_targets",
                        "error",
                        2,
                        site.path,
                        f"{a.block} attacks the map block's TARGET species (13.3): it runs in a "
                        "map block",
                    )
                elif not site.block.targets:
                    ctx.add(
                        "needs_targets",
                        "error",
                        2,
                        site.path,
                        f"{a.block} attacks only the TARGET species, and {site.block.name} lists "
                        "none (13.3)",
                    )
            if engage_source(a, blk.spec) == MELEE_RING:
                _melee_ring(ctx, site, a)
            if search_route(a, blk.spec) == PATROL_ROUTE:
                _patrol_route(ctx, site, a)


def _patrol_route(ctx: Ctx, site: ir.Site, a: ir.ActionStmt) -> None:
    b = site.block
    if b is None or ctx.routes is None:
        return  # needs_targets names a hunt outside a map block; no provider: runstart refuses
    m = b.map.map
    what = f"{a.block}'s {SEARCH_ROUTE} {PATROL_ROUTE} walks {m}'s reviewed patrol route"
    try:
        info = ctx.routes(m)
    except RoutesUnreadable as e:
        ctx.add(
            "patrol_route_unreadable",
            "error",
            2,
            site.path,
            f"{what}, and the routes file of {m} is refused by its loader: {e}",
        )
        return
    if info is None:
        ctx.add(
            "patrol_route_missing",
            "error",
            2,
            site.path,
            f"{what}, and {m} has no routes file (config/routes/{m}.yaml): refused",
        )
