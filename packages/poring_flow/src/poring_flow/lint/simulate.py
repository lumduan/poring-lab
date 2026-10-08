"""Linter layer 3, simulation (section 5 and 13.5): an abstract walk through the flow.

It tracks the current cell (routes on the walk grid), the SAVE POINT (it cannot be read from
pixels: unknown unless the flow sets or asserts it), what adds weight, which items later steps and
events use (keep lists), the hp_critical escape per map, attack targets and irreversible blocks.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from poring_flow import ir
from poring_flow.lint.common import Consts, Ctx, Severity, assigned_vars, body_actions
from poring_flow.lint.semantics import arrival
from poring_flow.sheet import Cell, MapSheet

SP = tuple[str, str | None, Cell | None] | None  # (set | asserted, map, cell) or unknown
States = frozenset[SP]
ATTACKS = ("attack_nearest", "finish_target", "use_skill")
ESCAPE_USER = "hp_critical's escape"


def check(ctx: Ctx) -> None:
    consts = Consts(ctx.flow, assigned_vars(ctx.flow))
    _routes(ctx, consts)
    SavePoint(ctx, consts).run()
    _weight(ctx, consts)
    _keep_lists(ctx, consts)
    _escape(ctx)
    _attacks(ctx, consts)
    _irreversible(ctx, consts)
    _map_change(ctx, consts)


# --- items ------------------------------------------------------------------------------------
def item_kind(ctx: Ctx, item_id: int | None) -> str | None:
    if item_id is None or ctx.world is None or item_id not in ctx.world.items:
        return None
    return ctx.world.items[item_id].kind


def item_name(ctx: Ctx, item_id: int, article: bool = True, plural: bool = False) -> str:
    it = ctx.world.items.get(item_id) if ctx.world else None
    label = it.label if it and it.label else None
    if label is None:
        default = {"fly_wing": "Fly Wing", "butterfly_wing": "Butterfly Wing"}
        label = default.get(it.kind) if it else None
    if label is None:
        return f"item {item_id}"
    if plural:
        return f"{label}s"
    return (f"an {label}" if label[0].lower() in "aeiou" else f"a {label}") if article else label


def escape_kind(sheet: MapSheet | None) -> str | None:
    """The escape hp_critical takes on a map: fly_wing, butterfly_wing, none, or None (unknown)."""
    if sheet is None or sheet.flags is None:
        return None
    if not sheet.flags.noteleport:
        return "fly_wing"
    return "none" if sheet.flags.noreturn else "butterfly_wing"


def _uses_wing(ctx: Ctx, consts: Consts, a: ir.ActionStmt, sheet: MapSheet | None) -> bool:
    """Does this action go to the SAVE POINT (a Butterfly Wing, or an escape that takes one)?"""
    if a.block == "use_item":
        return item_kind(ctx, consts.item(a.params.get("item"))) == "butterfly_wing"
    if a.block == "escape":
        return escape_kind(sheet) == "butterfly_wing"
    return False


# --- routes ---------------------------------------------------------------------------------------
def _routes(ctx: Ctx, consts: Consts) -> None:
    for b in ctx.blocks:
        sheet = ctx.sheet(b.map.map)
        if sheet is None:
            continue
        if sheet.walk is None:
            ctx.add(
                "routes",
                "warning",
                3,
                b.name,
                f"routes on {b.map.map} are not checked: its sheet has no walkability",
            )
            continue
        for e in b.entries:
            if e.at is None or e.at.map != b.map.map:
                continue
            if not sheet.walk.walkable((e.at.x, e.at.y)):
                ctx.add(
                    "routes",
                    "error",
                    3,
                    b.name,
                    f"entry {e.name} ({e.at.x}, {e.at.y}) is not walkable on {b.map.map}",
                )
                continue
            _route_stmts(ctx, consts, b.main, b.name, sheet, (e.at.x, e.at.y), f"entry {e.name}")
    if ctx.flow.main is not None and ctx.world is not None:
        _route_plain(ctx, consts, ctx.flow.main, "main", None, None, "")


def _leg(
    ctx: Ctx,
    path: str,
    sheet: MapSheet,
    pos: Cell | None,
    origin: str,
    to: Cell,
    allowed: set[Cell],
) -> None:
    if pos is None or sheet.walk is None:
        return
    route = sheet.walk.route(pos, to)
    if route is None:
        ctx.add("routes", "error", 3, path, f"cell ({to[0]}, {to[1]}) is unreachable from {origin}")
        return
    for c in route[1:]:
        w = sheet.warp_at(c)
        if w is not None and c not in allowed:
            ctx.add(
                "routes",
                "error",
                3,
                path,
                f"the route from {origin} to ({to[0]}, {to[1]}) crosses the warp at "
                f"({w.x}, {w.y}): it would leave {sheet.map}",
            )
            return


def _route_stmts(
    ctx: Ctx,
    consts: Consts,
    stmts: list[Any],
    prefix: str,
    sheet: MapSheet,
    pos: Cell | None,
    origin: str,
) -> tuple[Cell | None, str]:
    for i, st in enumerate(stmts):
        path = f"{prefix}.{i}"
        for a in ir.actions_in(st):
            spec = ctx.cat.blocks[a.block].spec if a.block in ctx.cat.blocks else None
            cell = consts.ref(a.params.get("cell"), ir.CellRef) if a.block == "walk_to" else None
            npc_ref = consts.ref(a.params.get("npc"), ir.NpcRef) if "npc" in a.params else None
            npc = sheet.npc(npc_ref.key) if npc_ref is not None else None
            if cell is not None and cell.map == sheet.map:
                _leg(ctx, path, sheet, pos, origin, (cell.x, cell.y), set())
                pos, origin = (cell.x, cell.y), f"({cell.x}, {cell.y})"
            elif spec is not None and spec.moves == "near" and npc is not None:
                # it walks up to the NPC: the next leg starts from the NPC's cell (approximately)
                pos, origin = (npc.x, npc.y), f"npc {npc.key} ({npc.x}, {npc.y})"
            elif spec is not None and (spec.moves != "none" or spec.changes_map != "never"):
                pos = None
        if isinstance(st, ir.TakeExit) and st.exit.warp is not None:
            w = st.exit.warp
            target = sheet.warp_at((w.x, w.y))
            if w.map == sheet.map:
                _leg(ctx, path, sheet, pos, origin, (w.x, w.y), target.cells() if target else set())
        for field, body, is_loop in ir.child_bodies(st):
            end, end_origin = _route_stmts(ctx, consts, body, f"{path}.{field}", sheet, pos, origin)
            if is_loop and end is not None and end != pos:  # the next iteration starts there
                _route_stmts(ctx, consts, body, f"{path}.{field}", sheet, end, end_origin)
            if end != pos:
                pos = None
    return pos, origin


def _route_plain(
    ctx: Ctx,
    consts: Consts,
    stmts: list[Any],
    prefix: str,
    map_id: str | None,
    pos: Cell | None,
    origin: str,
) -> tuple[str | None, Cell | None, str]:
    """A plain flow: the map comes from its cells and warps; the first position is unknown."""
    for i, st in enumerate(stmts):
        path = f"{prefix}.{i}"
        for a in ir.actions_in(st):
            spec = ctx.cat.blocks[a.block].spec if a.block in ctx.cat.blocks else None
            sheet = ctx.sheet(map_id) if map_id else None
            if a.block == "walk_to":
                cell = consts.ref(a.params.get("cell"), ir.CellRef)
                if cell is None:
                    pos = None
                    continue
                if map_id is not None and cell.map != map_id:
                    pos = None
                    continue
                map_id = cell.map
                sheet = ctx.sheet(map_id)
                if sheet is not None:
                    _leg(ctx, path, sheet, pos, origin, (cell.x, cell.y), set())
                pos, origin = (cell.x, cell.y), f"({cell.x}, {cell.y})"
            elif a.block == "take_warp":
                to = consts.ref(a.params.get("to"), ir.MapRef)
                warps = [w for w in sheet.warps if to and w.to_map == to.map] if sheet else []
                if sheet is not None and len(warps) == 1:
                    w = warps[0]
                    _leg(ctx, path, sheet, pos, origin, (w.x, w.y), w.cells())
                    map_id, pos, origin = w.to_map, (w.to_x, w.to_y), "the warp you arrive by"
                else:
                    map_id, pos = (to.map if to else None), None
            elif spec is not None and (spec.moves != "none" or spec.changes_map != "never"):
                pos = None
                if spec.changes_map != "never":
                    to = consts.ref(a.params.get("to"), ir.MapRef)
                    map_id = to.map if to and spec.changes_map == "always" else None
        for field, body, _ in ir.child_bodies(st):
            m2, p2, _o = _route_plain(ctx, consts, body, f"{path}.{field}", map_id, pos, origin)
            if (m2, p2) != (map_id, pos):
                map_id, pos = (map_id if m2 == map_id else None), None
    return map_id, pos, origin


# --- the save point (13.5; Batt 2026-10-08: an ERROR for every wing) ------------------------------
class SavePoint:
    def __init__(self, ctx: Ctx, consts: Consts) -> None:
        self.ctx, self.consts = ctx, consts
        self.entry: dict[str, set[SP]] = {b.name: set() for b in ctx.blocks}
        self.at: dict[str, list[States]] = {}  # in-state at each top-level statement
        self.report = False

    def run(self) -> None:
        ctx = self.ctx
        wf = ctx.flow.workflow
        if wf is not None:
            if wf.start_block in self.entry:
                self.entry[wf.start_block].add(None)
            for _ in range(len(ctx.blocks) * 4 + 4):  # a finite lattice: this converges
                before = {k: set(v) for k, v in self.entry.items()}
                for b in ctx.blocks:
                    if self.entry[b.name]:
                        self._block(b)
                if before == self.entry:
                    break
            self.report = True
            for b in ctx.blocks:
                if self.entry[b.name]:
                    self._block(b)
            self._events_workflow()
        elif ctx.flow.main is not None:
            self.report = True
            self.at["main"] = []
            self._stmts(ctx.flow.main, "main", frozenset({None}), None, top=self.at["main"])
            self._events_plain()

    # one block's main, from its entry states
    def _block(self, b: ir.MapBlock) -> None:
        self.at[b.name] = []
        self._stmts(b.main, b.name, frozenset(self.entry[b.name]), b, top=self.at[b.name])

    def _set(self, a: ir.ActionStmt, b: ir.MapBlock | None, state: States) -> States:
        if a.block == "set_save_point":
            map_id = b.map.map if b else None
            npc = self.consts.ref(a.params.get("npc"), ir.NpcRef)
            sheet = self.ctx.sheet(map_id) if map_id else None
            n = sheet.npc(npc.key) if sheet and npc else None
            cell = n.kafra.save_cell if n and n.kafra else None
            return frozenset({("set", map_id, cell)})
        if a.block == "assert_save_point":
            c = self.consts.ref(a.params.get("cell"), ir.CellRef)
            return frozenset({("asserted", c.map if c else None, (c.x, c.y) if c else None)})
        return state

    def _stmts(
        self,
        stmts: list[Any],
        prefix: str,
        state: States,
        b: ir.MapBlock | None,
        top: list[States] | None = None,
    ) -> States:
        ctx = self.ctx
        sheet = ctx.sheet(b.map.map) if b else None
        for i, st in enumerate(stmts):
            path = f"{prefix}.{i}"
            if top is not None:
                top.append(state)
            for a in ir.actions_in(st):
                if (
                    self.report
                    and _uses_wing(ctx, self.consts, a, sheet)
                    and not isinstance(st, ir.TakeExit)
                ):
                    self._wing(path, a, state, None)
                if self.report and a.block == "assert_save_point":
                    ctx.add(
                        "save_point",
                        "warning",
                        3,
                        path,
                        "the save point is asserted, not set: the assertion stays visible at "
                        "approval",
                        ack=True,
                    )
                state = self._set(a, b, state)
            if isinstance(st, ir.TakeExit) and b is not None:
                self._exit(path, st.exit, state, b)
            if isinstance(st, ir.If):
                state = self._stmts(st.then, f"{path}.then", state, b) | self._stmts(
                    st.orelse, f"{path}.orelse", state, b
                )
            elif isinstance(st, ir.While | ir.Repeat | ir.ForEach):
                once = self._stmts(st.body, f"{path}.body", state, b)
                state = state | once | self._stmts(st.body, f"{path}.body", state | once, b)
            elif isinstance(st, ir.CallProc):
                state = self._stmts(ctx.flow.procedures.get(st.proc, []), st.proc, state, b)
        return state

    def _wing(self, path: str, a: ir.ActionStmt, state: States, to: ir.MapBlock | None) -> None:
        what = self._what(a)
        if None in state:
            if to is not None:
                self.ctx.add(
                    "save_point",
                    "error",
                    3,
                    path,
                    f"{what} returns to the save point, not to {to.name}, and nothing sets "
                    f"it on {to.map.map}. Add 'set save point' at {to.name}'s Kafra?",
                )
            else:
                self.ctx.add(
                    "save_point",
                    "error",
                    3,
                    path,
                    f"{what} returns to the save point, and nothing sets it before "
                    f"{path}. Add 'set save point' first?",
                )
            return
        if to is not None:
            for s in sorted(state, key=repr):
                if s is not None and s[1] is not None and s[1] != to.map.map:
                    self.ctx.add(
                        "save_point",
                        "error",
                        3,
                        path,
                        f"{what} returns to the save point on {s[1]}, not to {to.name} "
                        f"on {to.map.map}",
                    )

    def _what(self, a: ir.ActionStmt) -> str:
        if a.block == "escape":
            return "the escape's Butterfly Wing"
        iid = self.consts.item(a.params.get("item"))
        return item_name(self.ctx, iid) if iid is not None else "a Butterfly Wing"

    def _exit(self, path: str, x: ir.Exit, state: States, b: ir.MapBlock) -> None:
        ctx = self.ctx
        to = ctx.block(x.to_block)
        if x.kind != "item_warp":
            if to is not None and not self.report:
                self.entry[to.name] |= set(state)
            return
        iid = x.item.id if isinstance(x.item, ir.ItemRef) else self.consts.item(x.item)
        kind = item_kind(ctx, iid)
        sheet = ctx.sheet(b.map.map)
        if not self.report:
            for s in state:
                if s is not None and s[1] is not None:
                    tb = self._resume_block(s[1])
                    if tb is not None:
                        self.entry[tb.name].add(s)
            return
        if (
            iid is not None
            and ctx.world is not None
            and ctx.world.items
            and kind != "butterfly_wing"
        ):
            ctx.add(
                "exit_destinations",
                "error",
                2,
                path,
                f"item {iid} is not a Butterfly Wing: an item_warp needs one",
            )
            return
        if sheet is not None and sheet.flags is None:
            ctx.add(
                "exit_destinations",
                "warning",
                2,
                path,
                f"{b.map.map}'s map flags are not extracted: a Butterfly Wing may be refused there",
            )
        elif sheet is not None and sheet.flags is not None and sheet.flags.noreturn:
            ctx.add(
                "exit_destinations",
                "error",
                2,
                path,
                f"{b.map.map} refuses a Butterfly Wing (noreturn)",
            )
        fake = ir.ActionStmt(
            block="use_item",
            concept="item.use",
            timeout_s=10,
            params={"item": ir.Lit(value=ir.ItemRef(id=iid))} if iid else {},
        )
        if to is None:
            return
        self._wing(path, fake, state, to)
        for s in state:
            if s is not None and s[1] == to.map.map and s[2] is not None:
                arrival(ctx, path, self._what(fake), to, x.to_entry, s[1], s[2])

    def _resume_block(self, map_id: str) -> ir.MapBlock | None:
        bs = [b for b in self.ctx.blocks if b.map.map == map_id]
        if len(bs) == 1:
            return bs[0]
        return next((b for b in bs if b.resume_here), None)

    def _first_unknown(self, name: str) -> int | None:
        return next((i for i, s in enumerate(self.at.get(name, [])) if None in s), None)

    def _events_workflow(self) -> None:
        ctx = self.ctx
        dead_reported = False
        landed: set[str] = set()
        for b in ctx.blocks:
            states = set().union(*self.at.get(b.name, [])) if self.at.get(b.name) else set()
            first = self._first_unknown(b.name)
            sheet = ctx.sheet(b.map.map)
            for e in ctx.merged(b).active():
                acts = body_actions(list(e.handler.body) + list(e.extension), ctx.flow)
                wing = next((a for a in acts if _uses_wing(ctx, self.consts, a, sheet)), None)
                if wing is not None and first is not None:
                    ctx.add(
                        "save_point",
                        "error",
                        3,
                        e.label,
                        f"{self._what(wing)} on {b.name} returns to the save point, and "
                        f"nothing sets it before {b.name}.{first}. Add 'set save point' "
                        "first?",
                    )
                respawn = any(a.block == "respawn" for a in acts)
                if respawn and first is not None and not dead_reported:
                    dead_reported = True
                    ctx.add(
                        "save_point",
                        "warning",
                        3,
                        e.label,
                        f"a death at {b.name}.{first} respawns at the save point, which "
                        "nothing sets before it: set it first, or assert it",
                    )
                if respawn or wing is not None:
                    for s in states:
                        if (
                            s is not None
                            and s[1] is not None
                            and s[1] not in landed
                            and (self._resume_block(s[1]) is None)
                        ):
                            landed.add(s[1])
                            ctx.add(
                                "graph",
                                "warning",
                                2,
                                "",
                                f"a death returns to the save point on {s[1]}, where no block "
                                "is: a death then stops the run",
                            )

    def _events_plain(self) -> None:
        ctx = self.ctx
        first = self._first_unknown("main")
        if first is None:
            return
        for e in ctx.merged(None).active():
            acts = body_actions(list(e.handler.body), ctx.flow)
            wing = next((a for a in acts if _uses_wing(ctx, self.consts, a, None)), None)
            if wing is not None:
                ctx.add(
                    "save_point",
                    "error",
                    3,
                    e.label,
                    f"{self._what(wing)} returns to the save point, and nothing sets it "
                    f"before main.{first}. Add 'set save point' first?",
                )
            if any(a.block == "respawn" for a in acts):
                ctx.add(
                    "save_point",
                    "warning",
                    3,
                    e.label,
                    f"a death at main.{first} respawns at the save point, which nothing sets "
                    "before it: set it first, or assert it",
                )


# --- weight (13.5) ------------------------------------------------------------------------------
def _weight_cmps(e: Any) -> list[ir.Cmp]:
    return [
        x
        for x in ir.sub_exprs(e)
        if isinstance(x, ir.Cmp)
        and any(isinstance(s, ir.Sense) and s.sensor == "weight_percent" for s in (x.left, x.right))
    ]


def _adds_weight(ctx: Ctx, acts: list[ir.ActionStmt]) -> tuple[bool, bool]:
    """(something adds weight, a loot block is there but unsupported here)."""
    adds = False
    loot_unsupported = False
    for a in acts:
        spec = ctx.cat.blocks[a.block].spec if a.block in ctx.cat.blocks else None
        if spec is None or not spec.adds_weight:
            continue
        if a.block == "loot" and ctx.resolver is not None:
            from poring_skills.resolve import Unsupported

            try:
                ctx.resolver(a.block, a.concept, {})
            except Unsupported:
                loot_unsupported = True
                continue
        adds = True
    return adds, loot_unsupported


def _weight(ctx: Ctx, consts: Consts) -> None:
    scopes: list[tuple[str, list[Any], ir.MapBlock | None]] = []
    if ctx.flow.main is not None:
        scopes.append(("main", ctx.flow.main, None))
    scopes += [(b.name, b.main, b) for b in ctx.blocks]
    for prefix, stmts, b in scopes:
        acts = body_actions(stmts, ctx.flow)
        for e in ctx.merged(b).active():
            acts += body_actions(list(e.handler.body) + list(e.extension), ctx.flow)
        adds, loot_unsupported = _adds_weight(ctx, acts)
        where = b.name if b else "this flow"
        for site in ir.walk(stmts, prefix, root=prefix, scope="main", block=b):
            st = site.stmt
            if not isinstance(st, ir.While | ir.If | ir.WaitUntil):
                continue
            for c in _weight_cmps(st.cond):
                src = ctx.src(c)
                if not adds:
                    tail = (
                        "loot is unsupported here"
                        if loot_unsupported
                        else (f"nothing in {where} picks any up")
                    )
                    ctx.add(
                        "weight",
                        "warning",
                        3,
                        site.path,
                        f"{src} can change only by picking up items, and {tail}",
                    )
                if not isinstance(st, ir.While):
                    continue
                left_sensor = isinstance(c.left, ir.Sense)
                op = (
                    c.op
                    if left_sensor
                    else {"<": ">", "<=": ">=", ">": "<", ">=": "<="}.get(c.op, c.op)
                )
                v = consts.value(c.right if left_sensor else c.left)
                if op not in ("<", "<=") or isinstance(v, bool) or not isinstance(v, int | float):
                    continue
                attacks = any(a.block in ATTACKS for a in body_actions(st.body, ctx.flow))
                if v >= 90 and attacks:
                    ctx.add(
                        "weight",
                        "error",
                        3,
                        site.path,
                        f"{src} guards an attack loop, and attacks stop at 90 %: the loop "
                        "stalls before it ends",
                    )
                elif 50 <= v < 90:
                    ctx.add(
                        "weight",
                        "info",
                        3,
                        site.path,
                        f"{src}: at 50 % and above, natural HP and SP regeneration has already "
                        "stopped",
                    )


# --- keep lists (13.5) --------------------------------------------------------------------------
def item_users(ctx: Ctx, consts: Consts) -> dict[int, list[str]]:
    users: dict[int, list[str]] = {}

    def use(iid: int | None, who: str) -> None:
        if iid is not None and who not in users.setdefault(iid, []):
            users[iid].append(who)

    def scan(stmts: list[Any], who: str) -> None:
        for a in body_actions(stmts, ctx.flow):
            if a.block == "use_item":
                use(consts.item(a.params.get("item")), who)

    for b in ctx.blocks:
        scan(b.main, b.name)
        for site in ir.walk(b.main, b.name, root=b.name, scope="block", block=b):
            if isinstance(site.stmt, ir.TakeExit) and site.stmt.exit.item is not None:
                x = site.stmt.exit
                use(
                    x.item.id if isinstance(x.item, ir.ItemRef) else consts.item(x.item),
                    f"{b.name}'s exit",
                )
    if ctx.flow.main is not None:
        scan(ctx.flow.main, "main")
    for label, h, _, _ in ir.handler_bodies(ctx.flow):
        scan(h.body, label)
    for b in ctx.blocks:
        for ev in b.events:
            if isinstance(ev, ir.Extend):
                scan(ev.steps, ir.event_label(ev, b))
    # the escape's wings, on every map where an escape is effective
    for b in ctx.blocks or [None]:  # type: ignore[list-item]
        for e in ctx.merged(b).active():
            if any(a.block == "escape" for a in body_actions(list(e.handler.body), ctx.flow)):
                kind = escape_kind(ctx.sheet(b.map.map)) if b else None
                for k in ("fly_wing", "butterfly_wing") if kind is None else (kind,):
                    for iid in ctx.world.items_of(k) if ctx.world else []:
                        use(iid, ESCAPE_USER)
    return users


def _keep_lists(ctx: Ctx, consts: Consts) -> None:
    users = item_users(ctx, consts)
    for site in ir.sites(ctx.flow):
        for a in ir.actions_in(site.stmt):
            if a.block == "kafra_store" and "all_except" in a.params:
                kept, verb = consts.refs(a.params["all_except"], ir.ItemRef), "storing"
            elif a.block == "sell" and "keep" in a.params:
                kept, verb = consts.refs(a.params["keep"], ir.ItemRef), "selling"
            else:
                continue
            if kept is None:
                continue
            keep_ids = {r.id for r in kept}
            for iid in sorted(set(users) - keep_ids):
                who = users[iid]
                names = ", ".join(who[:-1]) + f" and {who[-1]}" if len(who) > 1 else who[0]
                sev: Severity = "warning" if who == [ESCAPE_USER] else "error"
                past = "stores" if verb == "storing" else "sells"
                ctx.add(
                    "keep_lists",
                    sev,
                    3,
                    site.path,
                    f"{verb} everything also {past} the {item_name(ctx, iid, plural=True)} that "
                    f"{names} {'uses' if len(who) == 1 else 'use'}: add them to the keep "
                    "list",
                )


# --- the hp_critical escape per map (13.6.8, open question 30) ------------------------------------
def _escape(ctx: Ctx) -> None:
    for b in ctx.blocks:
        if not any(
            any(a.block == "escape" for a in body_actions(list(e.handler.body), ctx.flow))
            for e in ctx.merged(b).active()
        ):
            continue
        sheet = ctx.sheet(b.map.map)
        if sheet is None:
            continue
        kind = escape_kind(sheet)
        if kind is None:
            ctx.add(
                "escape",
                "warning",
                3,
                b.name,
                f"hp_critical's escape on {b.map.map} is unknown: its map flags are not extracted",
            )
        elif kind == "none":
            ctx.add(
                "escape",
                "warning",
                3,
                b.name,
                f"hp_critical has no escape on {b.map.map} (noteleport, noreturn): it stops "
                "the run there",
                ack=True,
            )


# --- attack targets (section 5: spawns on the map for attack_nearest; 13.3) ---------------------
def _attacks(ctx: Ctx, consts: Consts) -> None:
    for b in ctx.blocks:
        sheet = ctx.sheet(b.map.map)
        for site in ir.walk(b.main, b.name, root=b.name, scope="block", block=b):
            for a in ir.actions_in(site.stmt):
                if a.block != "attack_nearest":
                    continue
                mob = consts.ref(a.params.get("mob"), ir.MobRef) if "mob" in a.params else None
                if mob is None and "mob" not in a.params and not b.targets:
                    ctx.add(
                        "attacks",
                        "error",
                        3,
                        site.path,
                        "attack_nearest has no target: give it a mob or the block a TARGET list",
                    )
                if mob is not None and sheet is not None and mob.id not in sheet.spawned():
                    ctx.add(
                        "attacks",
                        "error",
                        3,
                        site.path,
                        f"mob {mob.id} is in no spawn line of {b.map.map}",
                    )
                if mob is not None and mob.id in {m.id for m in b.ignore}:
                    ctx.add(
                        "attacks",
                        "error",
                        3,
                        site.path,
                        f"mob {mob.id} is on {b.name}'s IGNORE list",
                    )
    if ctx.flow.main is not None:
        for site in ir.walk(ctx.flow.main, "main", root="main", scope="main", block=None):
            for a in ir.actions_in(site.stmt):
                if a.block == "attack_nearest" and "mob" not in a.params:
                    ctx.add(
                        "attacks",
                        "error",
                        3,
                        site.path,
                        "attack_nearest has no target: give it a mob",
                    )


# --- irreversible blocks (section 5) ------------------------------------------------------------
def _irreversible(ctx: Ctx, consts: Consts) -> None:
    for site in ir.sites(ctx.flow):
        for a in ir.actions_in(site.stmt):
            spec = ctx.cat.blocks[a.block].spec if a.block in ctx.cat.blocks else None
            if spec is None or not spec.irreversible:
                continue
            if a.block == "sell":
                keep = consts.value(a.params.get("keep")) if "keep" in a.params else None
                if keep == []:
                    ctx.add(
                        "irreversible",
                        "warning",
                        3,
                        site.path,
                        "sell with an empty keep list sells everything: acknowledge it at approval",
                        ack=True,
                    )
                continue
            ctx.add(
                "irreversible",
                "warning",
                3,
                site.path,
                f"{a.block} {spec.irreversible}: acknowledge it at approval",
                ack=True,
            )


# --- a map change inside a map block's main is an exit ------------------------------------------
def _map_change(ctx: Ctx, consts: Consts) -> None:
    for b in ctx.blocks:
        for site in ir.walk(b.main, b.name, root=b.name, scope="block", block=b):
            if isinstance(site.stmt, ir.TakeExit):
                continue
            for a in ir.actions_in(site.stmt):
                what = _changes_map(ctx, consts, a, ctx.sheet(b.map.map))
                if what:
                    ctx.add(
                        "exit_placement",
                        "error",
                        3,
                        site.path,
                        f"{what} changes the map: a map block leaves through take_exit",
                    )


def _changes_map(ctx: Ctx, consts: Consts, a: ir.ActionStmt, sheet: MapSheet | None) -> str | None:
    spec = ctx.cat.blocks[a.block].spec if a.block in ctx.cat.blocks else None
    if spec is None:
        return None
    if spec.changes_map == "always":
        return a.block
    if spec.changes_map == "by_item":
        iid = consts.item(a.params.get("item"))
        return item_name(ctx, iid) if iid and item_kind(ctx, iid) == "butterfly_wing" else None
    if spec.changes_map == "escape":
        k = escape_kind(sheet)
        return "the escape's Butterfly Wing" if k in (None, "butterfly_wing") else None
    return None


changes_map: Callable[[Ctx, Consts, ir.ActionStmt, MapSheet | None], str | None] = _changes_map
