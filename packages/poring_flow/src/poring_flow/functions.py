"""FUNCTIONS that press hotbar keys (Batt 2026-11-13; ADR-0020 Amendment C).

Batt: "Fly Wing and Butterfly Wing must not be written as fixed items. Make them FUNCTIONS whose
body says which shortcut key (F1-F9) to press; the Knife swap too; casting skills or anything else
the same way." A function is an ordinary procedure (`Flow.procedures`); its body presses a key with
the `press_key` block. Three things use them:

- an item warp by function: `Exit.proc` names the function an `item_warp` runs (the Butterfly Wing
  home). Its keys are WING KEYS: a press of one, anywhere in the flow, counts as that Butterfly
  Wing (the save-point rule, "then must be relocate or stop", a map change in a map block's main);
- the `dungeon_hunt` block: the runner (scripts/dungeon_hunt.py) as one block, whose four ROLE
  parameters each name a function of exactly one `press_key` (the runner presses one key a role);
- `call <function>` anywhere a block may run (an event's body: the world rule's
  `call butterfly_wing`).

Everything here reads the IR only (no catalogue, no linter), so the linter, the simulator and the
editor share one definition. A key is a press's LITERAL key (the linter's `param_option` refuses
any other value: a variable, a key off the hotbar).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from poring_flow import ir
from poring_flow.catalogue import registry

PRESS = "press_key"
RUNNER_BLOCK = "dungeon_hunt"
# The maps a RUNNER plays: scripts/flow_run.py FLOWS, each Flow's `map` (today one: the Rogue's
# xmas_dun02). `dungeon_hunt` runs only on a map block whose map is here (lint/functions.py);
# tests/test_flow_functions.py fails when this set and flow_run.FLOWS' maps disagree.
RUNNER_MAPS = frozenset({"xmas_dun02"})
# dungeon_hunt's ROLE parameters -> the runner's key setting each one is (scripts/flow_config.py
# FIELDS; scripts/flow_run.py FLOWS' defaults: heal_key F1, fly_key F8, knife_key F4, dagger_key F5)
ROLES = {"heal": "heal_key", "fly": "fly_key", "knife_on": "knife_key", "knife_back": "dagger_key"}
ROLE_WORDS = {
    "heal": "the heal item's key",
    "fly": "the Fly Wing's key",
    "knife_on": "the Knife's key",
    "knife_back": "the dagger's key",
}


def hotbar_keys() -> tuple[str, ...]:
    """The keys a press may name: press_key's options in blocks.yaml (L2.shortcut.hotbar's)."""
    spec = registry().blocks[PRESS]
    return tuple(next(p for p in spec.params if p.name == "key").options)


def key_of(a: ir.ActionStmt) -> str | None:
    """A press_key action's literal key ("F8"), else None (not a press, or not a literal)."""
    if a.block != PRESS:
        return None
    e = a.params.get("key")
    return e.value if isinstance(e, ir.Lit) and isinstance(e.value, str) else None


def actions(
    stmts: list[Any], flow: ir.Flow, seen: set[str] | None = None
) -> Iterator[ir.ActionStmt]:
    """Every action a body runs, through nested statements and the procedures it calls (once
    each: recursion is the linter's error, never a hang here)."""
    seen = set() if seen is None else seen
    for site in ir.walk(stmts, "x", root="x", scope="main", block=None):
        yield from ir.actions_in(site.stmt)
        if isinstance(site.stmt, ir.CallProc) and site.stmt.proc not in seen:
            seen.add(site.stmt.proc)
            yield from actions(flow.procedures.get(site.stmt.proc, []), flow, seen)


def presses(stmts: list[Any], flow: ir.Flow) -> list[ir.ActionStmt]:
    """The press_key actions of a body, through the procedures it calls."""
    return [a for a in actions(stmts, flow) if a.block == PRESS]


def item_warps(flow: ir.Flow) -> Iterator[tuple[ir.MapBlock, str, ir.Exit]]:
    """(block, node path, exit) for every item_warp a map block's main takes."""
    for b in flow.workflow.blocks if flow.workflow else []:
        for site in ir.walk(b.main, b.name, root=b.name, scope="block", block=b):
            if isinstance(site.stmt, ir.TakeExit) and site.stmt.exit.kind == "item_warp":
                yield b, site.path, site.stmt.exit


def wing_functions(flow: ir.Flow) -> list[str]:
    """The functions an item_warp runs (`Exit.proc`), in the order the flow first names them."""
    out: list[str] = []
    for _, _, x in item_warps(flow):
        if x.proc is not None and x.proc not in out:
            out.append(x.proc)
    return out


def wing_keys(flow: ir.Flow) -> dict[str, list[str]]:
    """key -> the wing functions that press it. A press of such a key, anywhere in the flow, uses
    what that slot holds: the flow said it is a Butterfly Wing (an item warp runs it)."""
    out: dict[str, list[str]] = {}
    for name in wing_functions(flow):
        if name not in flow.procedures:
            continue  # the linter names an undefined function
        for a in presses(flow.procedures[name], flow):
            k = key_of(a)
            if k is not None and name not in out.setdefault(k, []):
                out[k].append(name)
    return out


def single_press(flow: ir.Flow, name: str) -> ir.ActionStmt | None:
    """The function's press when its body is EXACTLY ONE press_key statement (a role function of
    dungeon_hunt), else None (undefined, empty, a call, two statements, another block)."""
    body = flow.procedures.get(name)
    if body is None or len(body) != 1:
        return None
    st = body[0]
    return st if isinstance(st, ir.ActionStmt) and st.block == PRESS else None


def role_functions(a: ir.ActionStmt) -> dict[str, str | None]:
    """dungeon_hunt's role -> the function name it gives (a string literal), None when absent or
    not a string literal (the linter names that)."""
    out: dict[str, str | None] = {}
    for role in ROLES:
        e = a.params.get(role)
        out[role] = e.value if isinstance(e, ir.Lit) and isinstance(e.value, str) else None
    return out
