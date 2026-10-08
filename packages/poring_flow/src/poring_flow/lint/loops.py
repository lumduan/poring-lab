"""Linter layer 3, loops (section 5 and 13.5).

Every `while` has a bound, a sensor or variable its body can change, a break, an exit or a stop; a
body with no action and no wait is a busy loop; every cycle of the workflow graph has a stop
condition or the explicit `run_until_stopped`. `max_runtime_s` still bounds every run.
"""

from __future__ import annotations

from typing import Any

from poring_flow import ir
from poring_flow.lint.common import Ctx, body_actions, sensors_in, vars_in
from poring_flow.lint.semantics import exit_edges


def _assigned_in(stmts: list[Any], flow: ir.Flow, seen: set[str] | None = None) -> set[str]:
    seen = set() if seen is None else seen
    out: set[str] = set()
    for site in ir.walk(stmts, "x", root="x", scope="main", block=None):
        st = site.stmt
        if isinstance(st, ir.SetVar | ir.ForEach):
            out.add(st.var)
        if isinstance(st, ir.WaitUntil) and st.outcome_to:
            out.add(st.outcome_to)
        if isinstance(st, ir.CallProc) and st.proc not in seen:
            seen.add(st.proc)
            out |= _assigned_in(flow.procedures.get(st.proc, []), flow, seen)
    for a in body_actions(stmts, flow):
        if a.outcome_to:
            out.add(a.outcome_to)
    return out


def _leaves(stmts: list[Any], flow: ir.Flow) -> bool:
    """A break of this loop, an exit or a stop somewhere in the body."""
    for site in ir.walk(stmts, "x", root="x", scope="main", block=None):
        if isinstance(site.stmt, ir.TakeExit | ir.Stop):
            return True
        if isinstance(site.stmt, ir.Break_) and site.loops == 0:
            return True
    return False


def _has_work(stmts: list[Any], flow: ir.Flow) -> bool:
    if body_actions(stmts, flow):
        return True
    return any(
        isinstance(s.stmt, ir.WaitUntil | ir.TakeExit)
        for s in ir.walk(stmts, "x", root="x", scope="main", block=None)
    )


def check(ctx: Ctx) -> None:
    flow = ctx.flow
    weight_paths = {
        f.path for f in ctx.findings if f.rule == "weight" and "picking up items" in f.text
    }
    for site in ir.sites(flow):
        st = site.stmt
        if not isinstance(st, ir.While):
            continue
        if not _has_work(st.body, flow):
            ctx.add(
                "busy_loop",
                "error",
                3,
                site.path,
                "this loop has no action and no wait: a busy loop",
            )
            continue
        if st.max_iter is not None or st.max_s is not None or _leaves(st.body, flow):
            continue
        sensors = sensors_in(st.cond)
        variables = vars_in(st.cond)
        if not sensors and not variables:
            ctx.add(
                "loop_ends",
                "error",
                3,
                site.path,
                "this loop can never end: add a bound, a break or a stop",
            )
            continue
        changed = _assigned_in(st.body, flow)
        affected: set[str] = set()
        for a in body_actions(st.body, flow):
            if a.block in ctx.cat.blocks:
                affected |= set(ctx.cat.blocks[a.block].spec.affects)
        stuck: list[str] = []
        for s in sensors:
            spec = ctx.cat.sensors.get(s.sensor)
            if s.sensor == "known" or spec is None or spec.spec.drift or s.sensor in affected:
                continue
            shown = ctx.src(s)
            if shown not in stuck:
                stuck.append(shown)
        stuck += sorted(v for v in variables if v not in changed)
        any_change = any(
            (ctx.cat.sensors.get(s.sensor) and ctx.cat.sensors[s.sensor].spec.drift)
            or s.sensor in affected
            for s in sensors
        ) or bool(variables & changed)
        if any_change or not stuck:
            continue
        if site.path in weight_paths and all(x.startswith("weight_percent(") for x in stuck):
            continue  # the weight rule (13.5) already says why, more precisely
        ctx.add(
            "loop_ends",
            "error",
            3,
            site.path,
            f"this loop can never end: nothing in it changes {' or '.join(stuck)}",
        )
    _cycles(ctx)


def _cycles(ctx: Ctx) -> None:
    wf = ctx.flow.workflow
    if wf is None:
        return
    order = [b.name for b in ctx.blocks]
    adj: dict[str, list[str]] = {n: [] for n in order}
    for frm, _, _, to in exit_edges(ctx):
        if to in adj and to not in adj[frm]:
            adj[frm].append(to)
    for n in adj:
        adj[n].sort(key=order.index)
    for scc in _sccs(order, adj):
        if len(scc) == 1 and scc[0] not in adj[scc[0]]:
            continue
        if wf.run_until_stopped or ctx.flow.stop_when is not None:
            continue
        stops = any(
            isinstance(s.stmt, ir.Stop)
            for b in ctx.blocks
            if b.name in scc
            for s in ir.walk(b.main, b.name, root=b.name, scope="block", block=b)
        )
        if stops:
            continue
        cycle = _a_cycle(sorted(scc, key=order.index), adj)
        ctx.add(
            "cycles",
            "error",
            3,
            "",
            f"the cycle {' → '.join(cycle)} never ends: add a stop condition or mark the "
            "workflow run until stopped",
        )


def _sccs(order: list[str], adj: dict[str, list[str]]) -> list[list[str]]:
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on: set[str] = set()
    out: list[list[str]] = []
    counter = [0]

    def strong(v: str) -> None:
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        for w in adj[v]:
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            out.append(comp)

    for v in order:
        if v not in index:
            strong(v)
    return out


def _a_cycle(scc: list[str], adj: dict[str, list[str]]) -> list[str]:
    start = scc[0]
    members = set(scc)
    path = [start]
    seen = {start}

    def dfs(v: str) -> bool:
        for w in adj[v]:
            if w == start:
                path.append(start)
                return True
            if w in members and w not in seen:
                seen.add(w)
                path.append(w)
                if dfs(w):
                    return True
                path.pop()
        return False

    dfs(start)
    return path
