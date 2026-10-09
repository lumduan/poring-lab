"""Linter layer 2 (section 5 and 13.5): every reference exists for the target environment.

The map (its sheet), the NPC on the map the flow is on at that point, the option in that NPC's
menu, the Kafra service, the item / monster on this server; every action's bindings through
`resolve()` (an `Unsupported` is a READINESS item naming the layer and key: it blocks the run, not
the design; Batt 2026-10-09, ADR-0020 contradictions #6); the L1 preconditions that must be
assumed; exit destinations; TARGET / IGNORE lists; the workflow graph.
"""

from __future__ import annotations

import itertools
from typing import Any

from poring_flow import always_on, ir
from poring_flow.lint.common import Consts, Ctx, assigned_vars, handler_exprs

PARAM_STR = {"window": "name", "npc": "key", "option": "key", "map": "map"}


def check(ctx: Ctx) -> None:
    consts = Consts(ctx.flow, assigned_vars(ctx.flow))
    _sheets_and_ids(ctx)
    _bindings(ctx, consts)
    _npcs(ctx, consts)
    _preconditions(ctx, consts)
    if ctx.flow.workflow is not None:
        _graph(ctx)
        _exits(ctx)
        _species(ctx)


# --- maps, items, monsters ------------------------------------------------------------------------
def _all_refs(ctx: Ctx) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []

    def scan(path: str, e: Any) -> None:
        for x in ir.sub_exprs(e):
            if isinstance(x, ir.Lit):
                vals = x.value if isinstance(x.value, list) else [x.value]
                out.extend((path, v) for v in vals if isinstance(v, ir.REF_TYPES))

    for name, lit in ctx.flow.variables.items():
        scan(name, lit)
    for site in ir.sites(ctx.flow):
        for _, e in ir.stmt_exprs(site.stmt):
            scan(site.path, e)
        if isinstance(site.stmt, ir.TakeExit):
            x = site.stmt.exit
            out += [
                (site.path, r)
                for r in (x.warp, x.npc, x.item, *x.options)
                if isinstance(r, ir.REF_TYPES)
            ]
    for label, h, _, _ in ir.handler_bodies(ctx.flow):
        for _, e in handler_exprs(h):
            scan(label, e)
    for b in ctx.blocks:
        out.append((b.name, b.map))
        out += [(b.name, e.at) for e in b.entries if e.at is not None]
        out += [(b.name, m) for m in (*b.targets, *b.ignore)]
    return out


def _sheets_and_ids(ctx: Ctx) -> None:
    if ctx.world is None:
        return
    server = ctx.world.server
    for path, r in _all_refs(ctx):
        if isinstance(r, ir.MapRef | ir.CellRef) and ctx.sheet(r.map) is None:
            ctx.add(
                "map_sheet",
                "error",
                2,
                path,
                f"no map sheet for {r.map} on {server} (L3): unsupported here",
            )
        elif isinstance(r, ir.ItemRef) and ctx.world.items and r.id not in ctx.world.items:
            ctx.add("refs", "error", 2, path, f"item {r.id} is not in {server}'s item data")
        elif isinstance(r, ir.MobRef) and ctx.world.mobs and r.id not in ctx.world.mobs:
            ctx.add("refs", "error", 2, path, f"mob {r.id} is not in {server}'s monster data")


# --- bindings -----------------------------------------------------------------------------------
def _params(a: ir.ActionStmt, consts: Consts) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, e in a.params.items():
        v = consts.value(e)
        attr = PARAM_STR.get(getattr(v, "kind", ""), "id")
        if hasattr(v, attr):
            out[k] = str(getattr(v, attr))
    return out


def _bindings(ctx: Ctx, consts: Consts) -> None:
    if ctx.resolver is None:
        return
    from poring_skills.resolve import Unsupported

    # the always-on events the flow does not write run too (#15): their bindings count
    for site in itertools.chain(ir.sites(ctx.flow), always_on.sites(ctx.flow)):
        for a in ir.actions_in(site.stmt):
            if a.concept.startswith("core.") or a.block not in ctx.cat.blocks:
                continue
            try:
                ctx.resolver(a.block, a.concept, _params(a, consts))
            except Unsupported as u:
                ctx.add(
                    "bindings",
                    "readiness",  # #6: blocks the run (runstart), not the design
                    2,
                    site.path,
                    f"{a.block} is unsupported here: {u.layer} binding {u.key} ({u.reason})",
                )


# --- NPCs, menus and Kafra services --------------------------------------------------------------
def _npcs(ctx: Ctx, consts: Consts) -> None:
    flow = ctx.flow
    if flow.main is not None:
        start = None
        for a in flow.assumes:
            if (
                isinstance(a, ir.Cmp)
                and a.op == "=="
                and isinstance(a.left, ir.Sense)
                and (a.left.sensor == "current_map")
            ):
                m = consts.ref(a.right, ir.MapRef)
                start = m.map if m else None
        _walk_npcs(ctx, consts, flow.main, "main", start, fixed=False)
    for b in ctx.blocks:
        _walk_npcs(ctx, consts, b.main, b.name, b.map.map, fixed=True)
        for ev in b.events:
            if isinstance(ev, ir.Override | ir.Add):
                _walk_npcs(ctx, consts, ev.event.body, ir.event_label(ev, b), b.map.map, True)
            elif isinstance(ev, ir.Extend):
                _walk_npcs(ctx, consts, ev.steps, ir.event_label(ev, b), b.map.map, True)
        for site in ir.walk(b.main, b.name, root=b.name, scope="block", block=b):
            if isinstance(site.stmt, ir.TakeExit) and site.stmt.exit.npc is not None:
                x = site.stmt.exit
                key = site.stmt.exit.npc.key
                n = _npc_on(ctx, site.path, key, b.map.map, fixed=True)
                if n is not None:
                    for o in x.options:
                        if o.key not in n.menu:
                            ctx.add(
                                "npc_menu",
                                "error",
                                2,
                                site.path,
                                f"option {o.key} is not in npc {n.key}'s menu",
                            )


def _npc_on(ctx: Ctx, path: str, key: str, map_id: str | None, fixed: bool) -> Any:
    if map_id is None:
        return None
    sheet = ctx.sheet(map_id)
    if sheet is None:
        return None
    n = sheet.npc(key)
    if n is None:
        where = map_id if fixed else "the map the flow is on at this point"
        ctx.add("npc_menu", "error", 2, path, f"npc {key} is not on {where}")
    return n


def _walk_npcs(
    ctx: Ctx, consts: Consts, stmts: list[Any], prefix: str, map_id: str | None, fixed: bool
) -> str | None:
    """Track the current map (plain flows) and the NPC being talked to; returns the map after."""
    npc: Any = None
    for i, st in enumerate(stmts):
        path = f"{prefix}.{i}"
        for a in ir.actions_in(st):
            spec = ctx.cat.blocks[a.block].spec if a.block in ctx.cat.blocks else None
            cell = consts.ref(a.params.get("cell"), ir.CellRef) if "cell" in a.params else None
            if a.block == "walk_to" and cell is not None:
                if map_id is not None and cell.map != map_id:
                    where = map_id if fixed else f"{map_id}, where the flow is at this point"
                    ctx.add(
                        "cell_map",
                        "error",
                        2,
                        path,
                        f"cell ({cell.x}, {cell.y}) is on {cell.map}, not on {where}",
                    )
                elif not fixed:
                    map_id = cell.map
            npc_ref = consts.ref(a.params.get("npc"), ir.NpcRef) if "npc" in a.params else None
            if npc_ref is not None:
                n = _npc_on(ctx, path, npc_ref.key, map_id, fixed)
                if a.block == "talk_npc":
                    npc = n
                if n is not None and spec is not None and spec.kafra:
                    if n.kafra is None:
                        ctx.add("kafra_service", "error", 2, path, f"npc {n.key} is not a Kafra")
                    elif spec.kafra not in n.kafra.services:
                        ctx.add(
                            "kafra_service",
                            "error",
                            2,
                            path,
                            f"npc {n.key} offers no {spec.kafra} service",
                        )
            if a.block == "choose_menu" and npc is not None:
                opt = consts.ref(a.params.get("option"), ir.OptionRef)
                if opt is not None and opt.key not in npc.menu:
                    ctx.add(
                        "npc_menu",
                        "error",
                        2,
                        path,
                        f"option {opt.key} is not in npc {npc.key}'s menu",
                    )
            if a.block in ("close_dialog", "close_npc_dialog"):
                npc = None
            if not fixed and spec is not None and spec.changes_map != "never":
                to = consts.ref(a.params.get("to"), ir.MapRef) if "to" in a.params else None
                map_id = to.map if to is not None and spec.changes_map == "always" else None
        for field, body, _ in ir.child_bodies(st):
            after = _walk_npcs(ctx, consts, body, f"{path}.{field}", map_id, fixed)
            if after != map_id and not fixed:
                map_id = None
    return map_id


# --- L1 preconditions that must be assumed ------------------------------------------------------
def _assumed(ctx: Ctx, consts: Consts, sensor: str, skill: int | None, value: int) -> bool:
    for a in ctx.flow.assumes:
        if not (isinstance(a, ir.Cmp) and isinstance(a.left, ir.Sense) and a.left.sensor == sensor):
            continue
        if skill is not None:
            s = consts.ref(a.left.args.get("skill"), ir.SkillRef)
            if s is None or s.id != skill:
                continue
        v = consts.value(a.right)
        if (
            isinstance(v, int)
            and not isinstance(v, bool)
            and (
                (a.op == ">=" and v >= value)
                or (a.op == ">" and v >= value - 1)
                or (a.op == "==" and v >= value)
            )
        ):
            return True
    return False


def _preconditions(ctx: Ctx, consts: Consts) -> None:
    seen: set[str] = set()
    for site in ir.sites(ctx.flow):
        for a in ir.actions_in(site.stmt):
            spec = ctx.cat.blocks[a.block].spec if a.block in ctx.cat.blocks else None
            if spec is None or a.block in seen:
                continue
            for need in spec.assume:
                if not _assumed(ctx, consts, need.sensor, need.skill, need.value):
                    seen.add(a.block)
                    arg = f"skill({need.skill})" if need.skill is not None else ""
                    ctx.add(
                        "preconditions",
                        "warning",
                        2,
                        site.path,
                        f"{a.block} needs {need.sensor}({arg}) {need.op} {need.value} "
                        f"({need.why}): add it to the flow's assumes",
                    )


# --- the workflow graph (13.5) ------------------------------------------------------------------
def exit_edges(ctx: Ctx) -> list[tuple[str, str, ir.Exit, str]]:
    """(from block, path, exit, to block) for every take_exit."""
    out = []
    for b in ctx.blocks:
        for site in ir.walk(b.main, b.name, root=b.name, scope="block", block=b):
            if isinstance(site.stmt, ir.TakeExit):
                out.append((b.name, site.path, site.stmt.exit, site.stmt.exit.to_block))
    return out


def ends(stmts: list[Any]) -> bool:
    """Every path through these statements ends in take_exit or stop."""
    for st in stmts:
        if isinstance(st, ir.TakeExit | ir.Stop):
            return True
        if isinstance(st, ir.If) and ends(st.then) and ends(st.orelse):
            return True
        if (
            isinstance(st, ir.While)
            and isinstance(st.cond, ir.Lit)
            and st.cond.value is True
            and (st.max_iter is None and st.max_s is None and not _breaks(st.body))
        ):
            return True
    return False


def _breaks(stmts: list[Any]) -> bool:
    for st in stmts:
        if isinstance(st, ir.Break_):
            return True
        if isinstance(st, ir.If) and (_breaks(st.then) or _breaks(st.orelse)):
            return True
    return False


def _graph(ctx: Ctx) -> None:
    wf = ctx.flow.workflow
    assert wf is not None
    names = {b.name: b for b in ctx.blocks}
    start = names.get(wf.start_block)
    if start is None:
        ctx.add("graph", "error", 2, "", f"the start block {wf.start_block} does not exist")
    elif all(e.name != wf.start_entry for e in start.entries):
        ctx.add(
            "graph", "error", 2, "", f"the start block {start.name} has no entry {wf.start_entry}"
        )
    if len(names) != len(ctx.blocks):
        ctx.add("graph", "error", 2, "", "two map blocks share a name")
    adj: dict[str, set[str]] = {b.name: set() for b in ctx.blocks}
    for frm, path, x, to in exit_edges(ctx):
        tb = names.get(to)
        if tb is None:
            ctx.add("graph", "error", 2, path, f"there is no map block {to}")
            continue
        if all(e.name != x.to_entry for e in tb.entries):
            ctx.add("graph", "error", 2, path, f"{to} has no entry {x.to_entry}")
        adj[frm].add(to)
    if start is not None:
        seen = {start.name}
        todo = [start.name]
        while todo:
            for n in adj[todo.pop()]:
                if n not in seen:
                    seen.add(n)
                    todo.append(n)
        for b in ctx.blocks:
            if b.name not in seen:
                ctx.add(
                    "graph",
                    "error",
                    2,
                    b.name,
                    f"no exit reaches it from the start block {start.name}",
                )
    for b in ctx.blocks:
        if not ends(b.main):
            ctx.add(
                "graph",
                "error",
                2,
                b.name,
                "a path of its main flow ends without take_exit or stop",
            )
        for e in b.entries:
            if e.at is not None and e.at.map != b.map.map:
                ctx.add(
                    "graph",
                    "error",
                    2,
                    b.name,
                    f"entry {e.name} is on {e.at.map}, not on {b.map.map}",
                )
    by_map: dict[str, list[ir.MapBlock]] = {}
    for b in ctx.blocks:
        by_map.setdefault(b.map.map, []).append(b)
    for m, bs in by_map.items():
        if len(bs) > 1 and sum(b.resume_here for b in bs) != 1:
            names_s = ", ".join(b.name for b in bs[:-1]) + f" and {bs[-1].name}"
            ctx.add("graph", "error", 2, "", f"{m} holds {names_s}: mark one resume_here")


def in_entry(entry: ir.Entry, map_id: str, cell: tuple[int, int]) -> bool:
    if entry.at is None:
        return True
    if entry.at.map != map_id:
        return False
    return max(abs(entry.at.x - cell[0]), abs(entry.at.y - cell[1])) <= entry.radius


def arrival(
    ctx: Ctx,
    path: str,
    what: str,
    to: ir.MapBlock,
    entry_name: str,
    map_id: str,
    cell: tuple[int, int],
) -> None:
    entry = next((e for e in to.entries if e.name == entry_name), None)
    if entry is None or entry.at is None:
        return
    if map_id != to.map.map:
        return
    if not in_entry(entry, map_id, cell):
        ctx.add(
            "exit_destinations",
            "error",
            2,
            path,
            f"{what} arrives at ({cell[0]}, {cell[1]}) on {map_id}, outside {to.name}'s entry "
            f"{entry.name} (({entry.at.x}, {entry.at.y}), radius {entry.radius})",
        )


def _exits(ctx: Ctx) -> None:
    for frm, path, x, to in exit_edges(ctx):
        b = ctx.block(frm)
        tb = ctx.block(to)
        if b is None or tb is None:
            continue
        sheet = ctx.sheet(b.map.map)
        if x.kind == "walk_exit" and x.warp is not None:
            w = x.warp
            if w.map != b.map.map:
                ctx.add(
                    "exit_destinations",
                    "error",
                    2,
                    path,
                    f"cell ({w.x}, {w.y}) is on {w.map}, not on {b.map.map}",
                )
                continue
            if sheet is None:
                continue
            warp = sheet.warp_at((w.x, w.y))
            if warp is None:
                ctx.add(
                    "exit_destinations",
                    "error",
                    2,
                    path,
                    f"({w.x}, {w.y}) is not a warp on {b.map.map}",
                )
            elif warp.to_map != tb.map.map:
                ctx.add(
                    "exit_destinations",
                    "error",
                    2,
                    path,
                    f"the warp at ({w.x}, {w.y}) leads to {warp.to_map}, not to {tb.name}'s "
                    f"{tb.map.map}",
                )
            else:
                arrival(
                    ctx,
                    path,
                    f"the warp at ({w.x}, {w.y})",
                    tb,
                    x.to_entry,
                    warp.to_map,
                    (warp.to_x, warp.to_y),
                )
        elif x.kind == "npc_warp" and x.npc is not None and sheet is not None:
            n = sheet.npc(x.npc.key)
            if n is None:
                continue
            keys = [o.key for o in x.options]
            what = f"option {', '.join(keys)} of npc {n.key}"
            nw = next((w for w in n.warps if w.options == keys), None)
            if nw is None:
                ctx.add(
                    "exit_destinations",
                    "warning",
                    2,
                    path,
                    f"the warp after {what} is not known: the destination is the author's, "
                    "checked on arrival",
                )
            elif nw.to_map != tb.map.map:
                ctx.add(
                    "exit_destinations",
                    "error",
                    2,
                    path,
                    f"{what} warps to {nw.to_map}, not to {tb.name}'s {tb.map.map}",
                )
            else:
                arrival(ctx, path, what, tb, x.to_entry, nw.to_map, (nw.to_x, nw.to_y))


# --- TARGET and IGNORE lists (13.3, 13.5) ---------------------------------------------------------
def _species(ctx: Ctx) -> None:
    w = ctx.world
    for b in ctx.blocks:
        sheet = ctx.sheet(b.map.map)
        if sheet is None:
            continue
        spawned = set(sheet.spawned())
        targets = [m.id for m in b.targets]
        ignore = [m.id for m in b.ignore]
        m = b.map.map
        for mid in [*targets, *ignore]:
            if mid not in spawned:
                ctx.add(
                    "species_lists", "error", 2, b.name, f"mob {mid} is in no spawn line of {m}"
                )
        for mid in sorted(set(targets) & set(ignore)):
            ctx.add(
                "species_lists",
                "error",
                2,
                b.name,
                f"mob {mid} is on both the TARGET and the IGNORE list",
            )
        unlisted = sorted(spawned - set(targets) - set(ignore))
        for mid in unlisted:
            ctx.add(
                "species_lists",
                "info",
                2,
                b.name,
                f"mob {mid} spawns on {m} and is on neither list: treated as IGNORE",
            )
        mobs = w.mobs if w else {}
        for mid in sorted(set(ignore) | set(unlisted)):
            if mid in mobs and mobs[mid].aggressive:
                ctx.add(
                    "species_lists",
                    "warning",
                    2,
                    b.name,
                    f"mob {mid} is aggressive and ignored: it attacks, the bot never answers, "
                    "the HP events decide",
                )
        for t in targets:
            for i in sorted(set(ignore) | set(unlisted)):
                alike = (
                    t in mobs and i in mobs[t].look_alike or i in mobs and t in mobs[i].look_alike
                )
                if alike:
                    ctx.add(
                        "species_lists",
                        "warning",
                        2,
                        b.name,
                        f"mob {t} (TARGET) and mob {i} (IGNORE) look alike: their confusion "
                        "is not measured",
                    )
