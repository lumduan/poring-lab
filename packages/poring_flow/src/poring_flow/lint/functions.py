"""FUNCTIONS that press hotbar keys in the linter (Batt 2026-11-13; ADR-0020 Amendment C;
`poring_flow.functions`).

Layer 1:
- `exit_function`: an item_warp's function (`Exit.proc`) is a defined procedure, never a
  variable, and its body presses a key (at least one press_key, through the procedures it calls);
- `hunt_function`: each of dungeon_hunt's four ROLE parameters (heal, fly, knife_on, knife_back)
  is a string literal naming a defined procedure whose body is EXACTLY ONE press_key statement, or
  (the project model) one call, with literal arguments, of such a function (`resolve_key`: the
  runner presses one key for each role);
- `key_argument` (the project model): a function whose press_key presses its PARAMETER is given
  a literal hotbar key at every call (or the parameter's default is one);
- `hotbar_keys`: dungeon_hunt's roles press four DIFFERENT keys, and none is a key the flow's
  Butterfly Wing function presses (scripts/flow_config.py refuses two settings on one key, and a
  Fly Wing press on the wing's slot would send her home).
Layer 2:
- `runner_map`: dungeon_hunt runs in a map block's own steps, on a map that has a runner
  (`functions.RUNNER_MAPS`: scripts/flow_run.py FLOWS' maps).
Layer 3 (with simulate.py and events.py, which read `functions.wing_keys`):
- `relocating` (WARNING): an event that resumes (then is not relocate or stop) presses a key no
  Butterfly Wing function names: what that slot holds is the player's, and a wing there would
  change the map. A key a wing function presses is the wing itself: the save-point rule, then
  relocate or stop and the map-change rule treat it exactly as use_item(WING) (an ERROR each).
"""

from __future__ import annotations

from typing import Any

from poring_flow import functions as fn
from poring_flow import ir
from poring_flow.lint.common import Ctx


def _function(ctx: Ctx, name: str) -> str | None:
    """Why `name` is not a defined function (None: it is one)."""
    if name in ctx.flow.procedures:
        return None
    if name in ctx.flow.variables:
        return f"{name} is a variable, not a function"
    return f"there is no function {name}"


def check(ctx: Ctx) -> None:
    flow = ctx.flow
    wings = fn.wing_keys(flow)
    for _, path, x in fn.item_warps(flow):
        if x.proc is None:
            continue
        why = _function(ctx, x.proc)
        if why is not None:
            ctx.add("exit_function", "error", 1, path, f"item_warp's function: {why}")
        elif not fn.presses(flow.procedures[x.proc], flow):
            ctx.add(
                "exit_function",
                "error",
                1,
                path,
                f"item_warp's function {x.proc} presses no key: its body needs a press_key (the "
                "Butterfly Wing's hotbar key)",
            )
    for site in ir.sites(flow):
        for a in ir.actions_in(site.stmt):
            if a.block == fn.RUNNER_BLOCK:
                _dungeon_hunt(ctx, site, a, wings)
    _key_arguments(ctx)
    for label, h, _, _ in ir.handler_bodies(flow):
        if h.then not in ("relocate", "stop"):
            _unknown_presses(ctx, label, list(h.body), wings)
    for b in ctx.blocks:
        for ev in b.events:
            if isinstance(ev, ir.Extend):
                g = next((h for h in flow.handlers if h.name == ev.key), None)
                if g is not None and g.then not in ("relocate", "stop"):
                    _unknown_presses(ctx, ir.event_label(ev, b), list(ev.steps), wings)


def _dungeon_hunt(ctx: Ctx, site: ir.Site, a: ir.ActionStmt, wings: dict[str, list[str]]) -> None:
    flow = ctx.flow
    keys: dict[str, str] = {}  # key -> the first role that presses it
    for role, name in fn.role_functions(a).items():
        what = f"dungeon_hunt's {role} ({fn.ROLE_WORDS[role]})"
        if role not in a.params:
            continue  # block_params names a missing role (structure.py)
        if name is None:
            ctx.add(
                "hunt_function",
                "error",
                1,
                site.path,
                f"{what} takes a function's name, not {ctx.src(a.params[role])}",
            )
            continue
        why = _function(ctx, name)
        if why is not None:
            ctx.add("hunt_function", "error", 1, site.path, f"{what}: {why}")
            continue
        key, _ = fn.resolve_key(flow, name)
        if key is None:
            ctx.add(
                "hunt_function",
                "error",
                1,
                site.path,
                f"{what} names {name}, whose body is not exactly one press_key: the runner "
                "presses one key for each role",
            )
            continue
        if key not in fn.hotbar_keys():
            continue  # param_option / key_argument name a key that is not a hotbar key
        if key in keys:
            ctx.add(
                "hotbar_keys",
                "error",
                1,
                site.path,
                f"dungeon_hunt's {keys[key]} and {role} both press {key}: each role needs its "
                "own key",
            )
        else:
            keys[key] = role
        if key in wings:
            ctx.add(
                "hotbar_keys",
                "error",
                1,
                site.path,
                f"{what} presses {key}, the key {wings[key][0]} uses as the Butterfly Wing home: "
                "each role needs its own key",
            )
    b = site.block
    maps = ", ".join(sorted(fn.RUNNER_MAPS))
    if b is None or site.scope not in ("block", "map_event", "extension"):
        ctx.add(
            "runner_map",
            "error",
            2,
            site.path,
            f"dungeon_hunt runs the map's runner: it belongs in a map block's steps (a map with "
            f"a runner: {maps})",
        )
    elif b.map.map not in fn.RUNNER_MAPS:
        ctx.add(
            "runner_map",
            "error",
            2,
            site.path,
            f"dungeon_hunt runs the map's runner, and {b.map.map} has none (maps with a runner: "
            f"{maps}; scripts/flow_run.py)",
        )


def _unknown_presses(
    ctx: Ctx, label: str, body: list[ir.StmtT], wings: dict[str, list[str]]
) -> None:
    """One WARNING per event: the first press of a key no wing function names (a wing key there is
    events.py's relocating ERROR)."""
    for a in fn.presses(body, ctx.flow):
        key = fn.key_of(a)
        if key is not None and key not in wings:
            ctx.add(
                "relocating",
                "warning",
                3,
                label,
                f'press_key("{key}") uses whatever is on that hotbar slot: if it holds a '
                "Butterfly Wing, the map changes and then must be relocate or stop",
            )
            return


def key_params(flow: ir.Flow) -> dict[str, str]:
    """function -> its parameter a press_key in its own body presses (the project model)."""
    out: dict[str, str] = {}
    for name, body in flow.procedures.items():
        sig = flow.signatures.get(name)
        if sig is None:
            continue
        for site in ir.walk(body, name, root=name, scope="procedure", block=None):
            for a in ir.actions_in(site.stmt):
                k = a.params.get("key") if a.block == fn.PRESS else None
                if isinstance(k, ir.Var) and k.name in sig.names():
                    out.setdefault(name, k.name)
    return out


def _key_arguments(ctx: Ctx) -> None:
    flow = ctx.flow
    params = key_params(flow)
    if not params:
        return
    keys = fn.hotbar_keys()

    def given(proc: str, args: list[ir.ExprT], kwargs: dict[str, ir.ExprT]) -> str | None:
        """Why the call does not give the key parameter a literal hotbar key (None: it does)."""
        sig = flow.signatures.get(proc) or ir.Signature()
        k = params[proc]
        names = [p.name for p in sig.params]
        e: ir.ExprT | None = None
        if k in names and names.index(k) < len(args):
            e = args[names.index(k)]
        elif k in kwargs:
            e = kwargs[k]
        else:
            d = next((p.default for p in sig.params if p.name == k), None)
            e = d
            if e is None:
                return f"{proc}() needs {k}, the key its press_key presses"
        v = e.value if isinstance(e, ir.Lit) else None
        if isinstance(v, str) and v in keys:
            return None
        return (
            f"{proc}()'s {k} is the key its press_key presses: a literal hotbar key "
            f"({keys[0]}-{keys[-1]}), not {ctx.src(e)}"
        )

    for site in ir.sites(flow):
        st = site.stmt
        calls: list[tuple[str, list[Any], dict[str, Any]]] = []
        if isinstance(st, ir.CallProc):
            calls.append((st.proc, list(st.args), dict(st.kwargs)))
        for _, e in ir.stmt_exprs(st):
            for x in ir.sub_exprs(e):
                if isinstance(x, ir.CallV):
                    calls.append((x.proc, list(x.args), dict(x.kwargs)))
        if isinstance(st, ir.TakeExit) and st.exit.proc is not None:
            calls.append((st.exit.proc, [], {}))
        for a in ir.actions_in(st):
            if a.block == fn.RUNNER_BLOCK:
                calls += [(n, [], {}) for n in fn.role_functions(a).values() if n is not None]
        for proc, args, kwargs in calls:
            if proc in params:
                why = given(proc, args, kwargs)
                if why is not None:
                    ctx.add("key_argument", "error", 1, site.path, why)
