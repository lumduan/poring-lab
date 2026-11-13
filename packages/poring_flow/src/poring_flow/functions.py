"""FUNCTIONS that press hotbar keys (Batt 2026-11-13; ADR-0020 Amendment C).

Batt: "Fly Wing and Butterfly Wing must not be written as fixed items. Make them FUNCTIONS whose
body says which shortcut key (F1-F9) to press; the Knife swap too; casting skills or anything else
the same way." A function is an ordinary procedure (`Flow.procedures`); its body presses a key with
the `press_key` block. Three things use them:

- an item warp by function: `Exit.proc` names the function an `item_warp` runs (the Butterfly Wing
  home). Its keys are WING KEYS: a press of one, anywhere in the flow, counts as that Butterfly
  Wing (the save-point rule, "then must be relocate or stop", a map change in a map block's main);
- the `dungeon_hunt` block: the runner (scripts/dungeon_hunt.py) as one block, whose four ROLE
  parameters each name a function of exactly one `press_key` (the runner presses one key a role),
  and its optional fifth, `home` (Batt 2026-11-13, the one box: the Butterfly Wing the runner
  itself flies home on). The home role's function is a Butterfly Wing function too: its key is a
  WING KEY, as an item warp's;
- `call <function>` anywhere a block may run (an event's body: the world rule's
  `call butterfly_wing`).

Everything here reads the IR only (no catalogue, no linter), so the linter, the simulator and the
editor share one definition. A key is a press's LITERAL key (the linter's `param_option` refuses
any other value: a variable, a key off the hotbar), or (the project model, format 3) a function's
PARAMETER that every call gives a literal key (`resolve_key`; the linter's `key_argument`).
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
# The OPTIONAL fifth role (Batt 2026-11-13 ~21:4x, the one box "START > xmas_dun02"): the function
# the runner presses to fly HOME on a Butterfly Wing (the bag half full, or Stop: its settings).
# Absent: the map's item warp by function gives the home key (project.runner_keys), as before.
HOME_ROLE = "home"
HOME_FIELD = "home_key"
ALL_ROLES = {**ROLES, HOME_ROLE: HOME_FIELD}
ROLE_WORDS = {
    "heal": "the heal item's key",
    "fly": "the Fly Wing's key",
    "knife_on": "the Knife's key",
    "knife_back": "the dagger's key",
    "home": "the Butterfly Wing's key, to fly home",
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
        for proc in ir.calls_in(site.stmt):  # a call statement, and a function's value (callv)
            if proc not in seen:
                seen.add(proc)
                yield from actions(flow.procedures.get(proc, []), flow, seen)


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
    """The Butterfly Wing functions: the ones an item_warp runs (`Exit.proc`), in the order the flow
    first names them, then dungeon_hunt's `home` role (the wing the runner flies home on)."""
    out: list[str] = []
    for _, _, x in item_warps(flow):
        if x.proc is not None and x.proc not in out:
            out.append(x.proc)
    for site in ir.sites(flow):
        for a in ir.actions_in(site.stmt):
            name = role_functions(a).get(HOME_ROLE) if a.block == RUNNER_BLOCK else None
            if name is not None and name not in out:
                out.append(name)
    return out


def wing_keys(flow: ir.Flow) -> dict[str, list[str]]:
    """key -> the wing functions that press it. A press of such a key, anywhere in the flow, uses
    what that slot holds: the flow said it is a Butterfly Wing (an item warp runs it)."""
    out: dict[str, list[str]] = {}
    for name in wing_functions(flow):
        if name not in flow.procedures:
            continue  # the linter names an undefined function
        keys = [key_of(a) for a in presses(flow.procedures[name], flow)]
        keys.append(resolve_key(flow, name)[0])  # through calls with literal arguments
        for k in keys:
            if k is not None and name not in out.setdefault(k, []):
                out[k].append(name)
    return out


MAX_KEY_DEPTH = 8


def _literal(e: Any, env: dict[str, Any]) -> tuple[bool, Any]:
    """(is it known, its value): a literal, or a parameter bound to one."""
    if isinstance(e, ir.Lit):
        return True, e.value
    if isinstance(e, ir.Var) and e.name in env:
        return True, env[e.name]
    return False, None


def bind_literals(
    flow: ir.Flow, name: str, args: list[Any], kwargs: dict[str, Any]
) -> dict[str, Any] | None:
    """A call's arguments bound to the function's inputs (literal values; defaults filled), or
    None when they do not fit (the linter's call_args names how)."""
    sig = flow.signatures.get(name) or ir.Signature()
    names = [p.name for p in sig.params]
    env: dict[str, Any] = dict(zip(names, args, strict=False))
    if len(args) > len(names) and sig.varargs is None:
        return None
    for k, v in kwargs.items():
        if k not in names or k in env:
            return None
        env[k] = v
    for p in sig.params:
        if p.name not in env:
            if p.default is None:
                return None
            env[p.name] = p.default.value
    return env


def resolve_key(
    flow: ir.Flow,
    name: str,
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
    depth: int = 0,
) -> tuple[str | None, str]:
    """The ONE hotbar key a function presses (the project model, section 6: "through calls with
    literal arguments, to exactly one press_key"): its body is exactly one statement, a press_key
    whose key is a literal or the function's parameter bound to a literal, or a call -- with
    literal arguments -- of another such function. (key, "") or (None, why)."""
    body = flow.procedures.get(name)
    if body is None:
        return None, f"there is no function {name}"
    if depth > MAX_KEY_DEPTH:
        return None, "its calls go deeper than the engine follows"
    env = bind_literals(flow, name, list(args or []), dict(kwargs or {}))
    if env is None:
        return None, f"{name}() is called with arguments that do not fit its inputs"
    if len(body) != 1:
        return None, f"{name}'s body is not exactly one press_key"
    st = body[0]
    if isinstance(st, ir.ActionStmt) and st.block == PRESS:
        known, v = _literal(st.params.get("key"), env)
        if known and isinstance(v, str):
            return v, ""
        return None, f"{name}'s press_key has no literal key"
    if isinstance(st, ir.CallProc):
        vals: list[Any] = []
        for a in st.args:
            known, v = _literal(a, env)
            if not known:
                return None, f"{name} calls {st.proc} with an argument that is not a literal"
            vals.append(v)
        kw: dict[str, Any] = {}
        for k, a in st.kwargs.items():
            known, v = _literal(a, env)
            if not known:
                return None, f"{name} calls {st.proc} with an argument that is not a literal"
            kw[k] = v
        return resolve_key(flow, st.proc, vals, kw, depth + 1)
    return None, f"{name}'s body is not exactly one press_key"


def single_press(flow: ir.Flow, name: str) -> ir.ActionStmt | None:
    """The function's press when its body is EXACTLY ONE press_key statement (a role function of
    dungeon_hunt), else None (undefined, empty, a call, two statements, another block)."""
    body = flow.procedures.get(name)
    if body is None or len(body) != 1:
        return None
    st = body[0]
    return st if isinstance(st, ir.ActionStmt) and st.block == PRESS else None


def role_functions(a: ir.ActionStmt) -> dict[str, str | None]:
    """dungeon_hunt's role (the four and `home`) -> the function name it gives (a string literal),
    None when absent or not a string literal (the linter names that)."""
    out: dict[str, str | None] = {}
    for role in ALL_ROLES:
        e = a.params.get(role)
        out[role] = e.value if isinstance(e, ir.Lit) and isinstance(e.value, str) else None
    return out
