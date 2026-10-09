"""Linter layer 3, the /where budget (Batt 2026-10-09, ADR-0020 contradictions #10).

`position()` and `current_map()` are ACTIVE: they type the client's `/where`, as `read_position`
does. Players almost never type it, so the bot uses it as little as possible (passive sources
first: the minimap readout outdoors, dead reckoning, landmarks; `/where` only at an indoor route
start or when the position belief is in doubt). Two WARNINGs:

- `where_loop`: a /where read that repeats: inside a loop body, in a `while` or `wait_until`
  condition (evaluated on every pass / tick), or in the body of a repeating (`until`) event;
- `where_budget`: the flow's STATIC count of /where reads on its longest path is above its
  `where_budget`. The count takes every read statement once (a loop's reads once: `where_loop`
  already warns about the repetition), a procedure's reads at each call, and for a workflow the
  longest simple path of map blocks from the start. Event bodies are not on a path (they fire on
  events); the simulator counts those reads, and relocations', at run time (`runtime.Sim.where`).

Which sensors and blocks read /where comes from the catalogue: those whose L1 concept is
`nav.read_position`.
"""

from __future__ import annotations

from typing import Any

from poring_flow import ir
from poring_flow.lint.common import Ctx, sensors_in
from poring_flow.lint.semantics import exit_edges

READ_CONCEPT = "nav.read_position"
MAX_BLOCKS_EXACT = 20  # above this, the longest path is bounded by the sum of all blocks


def readers(ctx: Ctx) -> tuple[set[str], set[str]]:
    """(sensor names, block names) that type /where, from the catalogue."""
    sensors = {n for n, s in ctx.cat.sensors.items() if s.spec.concept == READ_CONCEPT}
    blocks = {n for n, b in ctx.cat.blocks.items() if b.spec.concept == READ_CONCEPT}
    return sensors, blocks


def _reads(st: Any, sensors: set[str], blocks: set[str]) -> list[str]:
    """The /where reads one statement makes itself (not its nested statements)."""
    out = [f"{a.block}()" for a in ir.actions_in(st) if a.block in blocks]
    for _, e in ir.stmt_exprs(st):
        out += [f"{s.sensor}()" for s in sensors_in(e) if s.sensor in sensors]
    return out


def _count(
    ctx: Ctx, stmts: list[Any], sensors: set[str], blocks: set[str], seen: frozenset[str]
) -> int:
    n = 0
    for site in ir.walk(stmts, "x", root="x", scope="main", block=None):
        n += len(_reads(site.stmt, sensors, blocks))
        st = site.stmt
        if isinstance(st, ir.CallProc) and st.proc not in seen:
            body = ctx.flow.procedures.get(st.proc, [])
            n += _count(ctx, body, sensors, blocks, seen | {st.proc})
    return n


def static_count(ctx: Ctx) -> int:
    """The /where reads on the flow's longest path (the module docstring says how)."""
    sensors, blocks = readers(ctx)
    flow = ctx.flow
    if flow.workflow is None:
        return _count(ctx, flow.main or [], sensors, blocks, frozenset())
    per = {b.name: _count(ctx, b.main, sensors, blocks, frozenset()) for b in ctx.blocks}
    if len(per) > MAX_BLOCKS_EXACT:
        return sum(per.values())
    nxt: dict[str, set[str]] = {n: set() for n in per}
    for frm, _, _, to in exit_edges(ctx):
        if frm in nxt and to in per:
            nxt[frm].add(to)

    def longest(b: str, visited: frozenset[str]) -> int:
        tails = [longest(t, visited | {t}) for t in nxt[b] if t not in visited]
        return per[b] + max(tails, default=0)

    start = flow.workflow.start_block
    return longest(start, frozenset({start})) if start in per else 0


def check(ctx: Ctx) -> None:
    sensors, blocks = readers(ctx)
    repeating = {label for label, h, _, _ in ir.handler_bodies(ctx.flow) if h.until is not None}
    for site in ir.sites(ctx.flow):
        st = site.stmt
        reads = _reads(st, sensors, blocks)
        if not reads:
            continue
        what = " and ".join(dict.fromkeys(reads))
        if isinstance(st, ir.While | ir.WaitUntil):
            how = (
                "its condition is read on every pass"
                if isinstance(st, ir.While)
                else ("wait_until polls its condition on every tick")
            )
        elif site.loops:
            how = "it is inside a loop"
        elif site.root in repeating:
            how = "its event repeats until its stop threshold holds"
        else:
            continue
        ctx.add(
            "where_loop",
            "warning",
            3,
            site.path,
            f"{what} types /where and {how}: read the position once, or use a passive source",
        )
    n = static_count(ctx)
    if n > ctx.flow.where_budget:
        ctx.add(
            "where_budget",
            "warning",
            3,
            "",
            f"the longest path reads the position {n} times (/where), above the flow's "
            f"where_budget {ctx.flow.where_budget}: use a passive source, or raise the budget",
        )
