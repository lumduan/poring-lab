"""Linter layer 1 (section 5): what the Pydantic model cannot check alone.

Bounds on counts, nesting depth and node count; every block and sensor in the catalogue with its
parameters typed; variables declared and their types consistent; the procedure call graph acyclic;
names unique and never a catalogue name; take_exit only in a map block; no block run inside a
passive condition.
"""

from __future__ import annotations

from typing import Any

from poring_flow import ir
from poring_flow.lint.common import Ctx, handler_exprs

MAX_DEPTH = 16
MAX_NODES = 5000
REPEAT_MAX = 10_000
NUMBER = ("int", "float", "percent")


def _lit_type(v: Any) -> str:
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if isinstance(v, list):
        kinds = {r.kind for r in v}
        return f"list:{kinds.pop()}" if len(kinds) == 1 else ("list" if not kinds else "list:mixed")
    return str(v.kind)


def var_types(flow: ir.Flow) -> dict[str, str]:
    return {k: _lit_type(v.value) for k, v in flow.variables.items()}


def expr_type(e: Any, ctx: Ctx, types: dict[str, str]) -> str:
    if isinstance(e, ir.Lit):
        return _lit_type(e.value)
    if isinstance(e, ir.Var):
        return types.get(e.name, "?")
    if isinstance(e, ir.OutcomeLit | ir.Do):
        return "outcome"
    if isinstance(e, ir.ListE):
        kinds = {expr_type(i, ctx, types) for i in e.items}
        return f"list:{kinds.pop()}" if len(kinds) == 1 else "list:mixed"
    if isinstance(e, ir.Sense):
        if e.sensor == "known":
            return "bool"
        s = ctx.cat.sensors.get(e.sensor)
        return s.spec.type if s else "?"
    if isinstance(e, ir.Cmp | ir.Logic | ir.Not_):
        return "bool"
    if isinstance(e, ir.Arith):
        a, b = expr_type(e.left, ctx, types), expr_type(e.right, ctx, types)
        return "int" if a == b == "int" else "float"
    return "?"


ACCEPTS = {
    "int": ("int",),
    "float": NUMBER,
    "bool": ("bool",),
    "str": ("str", "outcome"),
    "value": ("int", "str"),
    "items": ("list:item", "list"),
}


def accepts(param: str, t: str) -> bool:
    if t == "?":
        return True  # reported elsewhere (an unknown variable or sensor)
    return t in ACCEPTS.get(param, (param,))


def _article(t: str) -> str:
    shown = {"list:item": "list of items", "percent": "number", "float": "number"}.get(t, t)
    return f"an {shown}" if shown[0] in "aeiou" else f"a {shown}"


def check(ctx: Ctx) -> None:
    flow = ctx.flow
    types = var_types(flow)
    _names(ctx)
    n = ir.count_nodes(flow)
    if n > MAX_NODES:
        ctx.add("node_count", "error", 1, "", f"the flow has {n} nodes; at most {MAX_NODES}")
    for name, t in types.items():
        if t == "list:mixed":
            ctx.add("variables", "error", 1, name, "a list holds one kind of reference")
    for site in ir.sites(flow):
        st, path = site.stmt, site.path
        if site.depth > MAX_DEPTH:
            ctx.add("depth", "error", 1, path, f"statements nested deeper than {MAX_DEPTH}")
        if isinstance(st, ir.Repeat):
            v = st.times.value if isinstance(st.times, ir.Lit) else None
            if isinstance(v, bool) or (isinstance(v, int | float) and not 1 <= v <= REPEAT_MAX):
                ctx.add("repeat_bounds", "error", 1, path, f"repeat.times must be 1..{REPEAT_MAX}")
        if isinstance(st, ir.Break_ | ir.Continue_) and not site.loops:
            ctx.add("loop_control", "error", 1, path, f"{st.kind} outside a loop")
        if isinstance(st, ir.TakeExit) and site.scope != "block":
            ctx.add("exit_placement", "error", 1, path, "take_exit belongs in a map block's main")
        if isinstance(st, ir.CallProc) and st.proc not in flow.procedures:
            ctx.add("procedures", "error", 1, path, f"there is no procedure {st.proc}")
        if isinstance(st, ir.SetVar):
            _set_var(ctx, path, st.var, expr_type(st.value, ctx, types), types)
        if isinstance(st, ir.ForEach):
            _for_var(ctx, path, st, types)
        if isinstance(st, ir.WaitUntil) and st.outcome_to:
            _set_var(ctx, path, st.outcome_to, "outcome", types)
        for a in ir.actions_in(st):
            _action(ctx, path, a, types)
        for _, e in ir.stmt_exprs(st):
            _expr(ctx, path, e, types)
    for label, h, _, _ in ir.handler_bodies(flow):
        for _, e in handler_exprs(h):
            _expr(ctx, label, e, types)
            if any(isinstance(x, ir.Do) for x in ir.sub_exprs(e)):
                ctx.add("do_placement", "error", 1, label, "an event condition cannot run a block")
        if h.escalate and h.escalate not in flow.procedures:
            ctx.add("procedures", "error", 1, label, f"escalate names no procedure {h.escalate}")
    for where, e in [
        *((f"assumes.{i}", a) for i, a in enumerate(flow.assumes)),
        *((("stop_when", flow.stop_when),) if flow.stop_when else ()),
    ]:
        _expr(ctx, where, e, types)
        if any(isinstance(x, ir.Do) for x in ir.sub_exprs(e)):
            ctx.add("do_placement", "error", 1, where, "this condition cannot run a block")
    _recursion(ctx)


def _set_var(ctx: Ctx, path: str, var: str, t: str, types: dict[str, str]) -> None:
    if var not in types:
        ctx.add("variables", "error", 1, path, f"{var} is not a flow variable")
        return
    have = types[var]
    ok = (
        t == "?"
        or have == t
        or (have == "float" and t in NUMBER)
        or (have == "str" and t == "outcome")
        or (have.startswith("list") and t.startswith("list"))
    )
    if not ok:
        ctx.add(
            "variables",
            "error",
            1,
            path,
            f"{var} holds {_article(have)}: it cannot take {_article(t)}",
        )


def _for_var(ctx: Ctx, path: str, st: ir.ForEach, types: dict[str, str]) -> None:
    if isinstance(st.items, ir.Range):
        _set_var(ctx, path, st.var, "int", types)
        return
    t = expr_type(st.items, ctx, types)
    if t.startswith("list:"):
        _set_var(ctx, path, st.var, t.split(":", 1)[1], types)
    elif t != "?":
        ctx.add("variables", "error", 1, path, f"for {st.var} needs a list or a range")


def _action(ctx: Ctx, path: str, a: ir.ActionStmt, types: dict[str, str]) -> None:
    blk = ctx.cat.blocks.get(a.block)
    if blk is None:
        ctx.add("unknown_block", "error", 1, path, f"there is no block {a.block}")
        return
    spec = blk.spec
    if a.concept != spec.concept:
        ctx.add(
            "block_concept", "error", 1, path, f"{a.block} runs {spec.concept}, not {a.concept}"
        )
    params = {p.name: p for p in spec.params}
    for k, e in a.params.items():
        if k not in params:
            ctx.add("block_params", "error", 1, path, f"{a.block} has no parameter {k}")
            continue
        t = expr_type(e, ctx, types)
        if not accepts(params[k].type, t):
            ctx.add(
                "block_params",
                "error",
                1,
                path,
                f"{a.block}'s {k} takes {_article(params[k].type)}, not {_article(t)}",
            )
    for p in spec.params:
        if p.required and p.name not in a.params:
            ctx.add("block_params", "error", 1, path, f"{a.block} needs {p.name}")
    if a.outcome_to:
        _set_var(ctx, path, a.outcome_to, "outcome", types)


def _membership_ok(right: Any, types: dict[str, str]) -> bool:
    """`x in ...` / `not in` only against a LITERAL list of typed references (a list literal, or a
    list of constant variables) or a list variable: never another expression (Batt 2026-10-09,
    ADR-0020 contradictions #2: statically checkable)."""
    if isinstance(right, ir.Lit):
        return isinstance(right.value, list)
    if isinstance(right, ir.ListE):
        return all(isinstance(i, ir.Var | ir.Lit) for i in right.items)
    if isinstance(right, ir.Var):
        return types.get(right.name, "?").startswith("list") or right.name not in types
    return False


def _expr(ctx: Ctx, path: str, e: Any, types: dict[str, str]) -> None:
    for x in ir.sub_exprs(e):
        if (
            isinstance(x, ir.Cmp)
            and x.op in ("in", "not in")
            and not _membership_ok(x.right, types)
        ):
            ctx.add(
                "membership",
                "error",
                1,
                path,
                f"{x.op} needs a literal list of references or a list variable, not "
                f"{ctx.src(x.right)}",
            )
        if isinstance(x, ir.Var) and x.name not in types:
            ctx.add("variables", "error", 1, path, f"{x.name} is not a flow variable")
        elif isinstance(x, ir.Sense):
            if x.sensor == "known":
                if set(x.args) != {"value"}:
                    ctx.add("unknown_sensor", "error", 1, path, "known() takes one value")
                continue
            s = ctx.cat.sensors.get(x.sensor)
            if s is None:
                ctx.add("unknown_sensor", "error", 1, path, f"there is no sensor {x.sensor}")
                continue
            params = {p.name: p for p in s.spec.params}
            for k, v in x.args.items():
                if k not in params:
                    ctx.add(
                        "unknown_sensor", "error", 1, path, f"{x.sensor}() has no parameter {k}"
                    )
                elif not accepts(params[k].type, expr_type(v, ctx, types)):
                    ctx.add(
                        "unknown_sensor",
                        "error",
                        1,
                        path,
                        f"{x.sensor}()'s {k} takes {_article(params[k].type)}",
                    )
            for p in s.spec.params:
                if p.required and p.name not in x.args:
                    ctx.add("unknown_sensor", "error", 1, path, f"{x.sensor}() needs {p.name}")
        elif isinstance(x, ir.Do):
            _action(ctx, path, x.action, types)
            if x.action.outcome_to:
                ctx.add(
                    "block_params",
                    "error",
                    1,
                    path,
                    f"{x.action.block} used as a value has no outcome_to",
                )


def _names(ctx: Ctx) -> None:
    flow = ctx.flow
    owners: dict[str, list[str]] = {}

    def own(name: str, what: str) -> None:
        owners.setdefault(name, []).append(what)

    for v in flow.variables:
        own(v, "a variable")
    for p in flow.procedures:
        own(p, "a procedure")
    for h in flow.handlers:
        own(h.name, "a global event")
    for b in ctx.blocks:
        own(b.name, "a map block")
        for ev in b.events:
            if not isinstance(ev, ir.Disable):
                own(ir.event_label(ev, b), "a map event")
        if len({e.name for e in b.entries}) != len(b.entries):
            ctx.add("names", "error", 1, b.name, "two entries share a name")
    reserved = ctx.cat.names()
    for name, whats in owners.items():
        if name in reserved:
            ctx.add(
                "names", "error", 1, "", f"{name} is a catalogue name: {whats[0]} cannot reuse it"
            )
        if len(whats) > 1:
            ctx.add(
                "names", "error", 1, "", f"{name} names {whats[0]} and {whats[1]}: names are unique"
            )


def _recursion(ctx: Ctx) -> None:
    calls: dict[str, set[str]] = {}
    for site in ir.sites(ctx.flow):
        if site.scope == "procedure" and isinstance(site.stmt, ir.CallProc):
            calls.setdefault(site.root, set()).add(site.stmt.proc)
    reported: set[frozenset[str]] = set()

    def dfs(node: str, stack: list[str]) -> None:
        for nxt in sorted(calls.get(node, ())):
            if nxt in stack:
                cycle = [*stack[stack.index(nxt) :], nxt]
                key = frozenset(cycle)
                if key not in reported:
                    reported.add(key)
                    ctx.add(
                        "procedures",
                        "error",
                        1,
                        cycle[0],
                        f"recursion ({' → '.join(cycle)}) is not allowed",
                    )
            else:
                dfs(nxt, [*stack, nxt])

    for p in ctx.flow.procedures:
        dfs(p, [p])
