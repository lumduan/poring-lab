"""The ALWAYS-ON safety events (Batt 2026-10-09, ADR-0020 contradictions #15).

The compiler adds `dead`, `hp_critical` and `unexpected_map` to EVERY flow, a workflow or a plain
main flow, as global events. They are on by construction: a flow cannot leave one out, and a flow
that writes one may only make it STRICTER (the linter's "not weakened" check, lint/events.py).

- The definitions are 13.6.8's global events, fixed here in code: `dead` (respawn, 1 per run,
  relocate), `hp_critical` (below 20 % the fixed escape, re-armed above 50 %, at most 2 a minute,
  relocate) and `unexpected_map` (read the position, relocate).
- They are NOT written into the IR: like the effective event set they are derived (effective.py
  adds the ones a flow does not write), so a flow's IR and its hash stay what its author wrote.
  The definitions are part of the engine's version, as the catalogue is.
- A flow that writes one of them replaces the built-in only where it is at least as strict: the same
  class (critical) and mode (pre-empt), `then` relocate or stop, a trigger that fires no later, the
  same re-arm, limits no looser, and a body that starts with the built-in's step (hp_critical's
  body is exactly the escape). Anything else is a lint ERROR.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Literal

from poring_flow import ir


def _act(block: str, concept: str, timeout_s: float) -> ir.ActionStmt:
    return ir.ActionStmt(block=block, concept=concept, timeout_s=timeout_s)


def _hp(op: Literal["<", ">"], value: int) -> ir.Cmp:
    return ir.Cmp(op=op, left=ir.Sense(sensor="hp_percent"), right=ir.Lit(value=value))


BUILT_IN: dict[str, ir.Handler] = {
    "dead": ir.Handler(
        name="dead",
        when=ir.Sense(sensor="is_dead"),
        priority="critical",
        max_per_run=1,  # 13.6.7: the second death stops the run (open question 19)
        then="relocate",
        body=[_act("respawn", "char.respawn", 30)],
    ),
    "hp_critical": ir.Handler(
        name="hp_critical",
        when=_hp("<", 20),
        rearm=_hp(">", 50),
        priority="critical",
        max_per_min=2,
        then="relocate",
        body=[_act("escape", "nav.escape", 10)],  # FIXED (13.6.8)
    ),
    "unexpected_map": ir.Handler(
        name="unexpected_map",
        when=ir.Sense(sensor="map_load_seen"),
        priority="critical",
        then="relocate",
        body=[_act("read_position", "nav.read_position", 10)],
    ),
}
assert tuple(BUILT_IN) == ir.SAFETY_CRITICAL


def added(flow: ir.Flow) -> list[ir.Handler]:
    """The built-in events a flow does not write itself (the compiler adds these)."""
    written = {h.name for h in flow.handlers}
    return [h for k, h in BUILT_IN.items() if k not in written]


def global_handlers(flow: ir.Flow) -> list[ir.Handler]:
    """The flow's global events as they run: the built-ins it does not write, then its own."""
    return [*added(flow), *flow.handlers]


def sites(flow: ir.Flow) -> Iterator[ir.Site]:
    """The statements of the built-in events a flow does not write (their node paths are the
    event's key: `dead.0`), so their bindings are checked like the flow's own."""
    for h in added(flow):
        yield from ir.walk(h.body, h.name, root=h.name, scope="handler", block=None)
