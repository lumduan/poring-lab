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
from dataclasses import dataclass
from typing import Any, Literal

from poring_flow import ir
from poring_flow.catalogue import registry

PRESS = "press_key"
RUNNER_BLOCK = "dungeon_hunt"
MODEL = "use_model"  # stage 4a: the trained data, the hunt core's model (poring_flow.recipes)
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


def literal_value(e: Any, env: dict[str, Any]) -> tuple[bool, Any]:
    """(is it known, its value): a literal, or a parameter bound to one (live.hunt_plan)."""
    return _literal(e, env)


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


def role_functions(a: ir.ActionStmt, roles: Any = None) -> dict[str, str | None]:
    """dungeon_hunt's role (the four and `home`; or ``roles``, e.g. CLICK_ROLES) -> the function
    name it gives (a string literal), None when absent or not a string literal (the linter names
    that)."""
    out: dict[str, str | None] = {}
    for role in ALL_ROLES if roles is None else roles:
        e = a.params.get(role)
        out[role] = e.value if isinstance(e, ir.Lit) and isinstance(e.value, str) else None
    return out


# --- stage 3 (Batt 2026-11-13; docs/planning/live-blocks.md 3.3, ADR-0020 Amendment G) -----------
# "The Knife swap (Damascus): a function: press F4, wait 100 ms, press F5; the other way back to the
# Knife: the same swapped" and "make respawn a function block, in case another server's menu
# differs; make everything editable in blocks, don't hard-code". A ROLE FUNCTION of the Knife swap
# or of the way home may be a BODY -- presses and waits, through calls with literal arguments --
# that the hunt core CALLS at its own moment (the live player plays it, the runner waits); the
# respawn's two roles are functions of clicks (the new block click_at) and waits. Their KEY for the
# Run settings and the start's slot check is the body's FIRST press (`role_key`): every other key a
# body presses must be one the check reads too (poring_flow.live.hunt_plan).
BODY_ROLES = ("knife_on", "knife_back", HOME_ROLE)
CLICK = "click_at"
GAME_PX = (1280, 720)  # click_at's points: game-region pixels (dungeon_hunt.GAME_PX)
# The OPTIONAL respawn roles: the death dialog's button, then this client's confirmation (absent:
# the server asks none). Their functions click; they play only in the hunt core's death exit.
CLICK_ROLES = {
    "respawn": "the death dialog's button (move to the saved location)",
    "respawn_confirm": "the confirmation's OK after it (absent: this server asks none)",
}
STEPS_MAX = 4  # presses and clicks in one role body
STEPS_WAIT_MAX_S = 1.0  # its waits in all: the runner waits while the box plays a body


@dataclass(frozen=True)
class Step:
    """One step of a role body, in order: a hotbar press, a wait, or a click (game-region px)."""

    kind: Literal["press", "wait", "click"]
    key: str | None = None
    s: float = 0.0
    x: int = 0
    y: int = 0

    def doc(self) -> dict[str, Any]:
        if self.kind == "press":
            return {"press": self.key}
        if self.kind == "wait":
            return {"wait": self.s}
        return {"click": [self.x, self.y]}


def is_wait(st: Any) -> bool:
    """The view's ``wait(s)``: a wait_until on the literal False (it only waits), no outcome."""
    return (isinstance(st, ir.WaitUntil) and isinstance(st.cond, ir.Lit) and st.cond.value is False
            and st.outcome_to is None)  # fmt: skip


def _whole(known: bool, v: Any) -> bool:
    return known and isinstance(v, int) and not isinstance(v, bool)


def body_steps(flow: ir.Flow, name: str, args: list[Any] | None = None,
               kwargs: dict[str, Any] | None = None,
               depth: int = 0) -> tuple[list[Step] | None, str]:  # fmt: skip
    """PURE: a function's body as its STEPS, in the order they play -- press_key (a literal key,
    or an input bound to one), wait(s) (a literal number of seconds), click_at(x, y) (literal
    game-region pixels), and calls of such functions with literal arguments. (steps, "") or (None,
    why): any other statement (a loop, an if, a sensor read, an exit, a stop, another block)."""
    body = flow.procedures.get(name)
    if body is None:
        return None, f"there is no function {name}"
    if depth > MAX_KEY_DEPTH:
        return None, "its calls go deeper than the engine follows"
    env = bind_literals(flow, name, list(args or []), dict(kwargs or {}))
    if env is None:
        return None, f"{name}() is called with arguments that do not fit its inputs"
    out: list[Step] = []
    for st in body:
        if isinstance(st, ir.WaitUntil) and is_wait(st):
            out.append(Step("wait", s=float(st.timeout_s)))
        elif isinstance(st, ir.ActionStmt) and st.block == PRESS:
            known, v = _literal(st.params.get("key"), env)
            if not (known and isinstance(v, str)):
                return None, f"{name}'s press_key has no literal key"
            out.append(Step("press", key=v))
        elif isinstance(st, ir.ActionStmt) and st.block == CLICK:
            (kx, x), (ky, y) = (_literal(st.params.get(k), env) for k in ("x", "y"))
            if not (_whole(kx, x) and _whole(ky, y)):
                return None, f"{name}'s click_at has no literal point (x, y: whole pixels)"
            out.append(Step("click", x=int(x), y=int(y)))
        elif isinstance(st, ir.CallProc):
            vals = [_literal(a, env) for a in st.args]
            kws = {k: _literal(a, env) for k, a in st.kwargs.items()}
            if not all(k for k, _ in [*vals, *kws.values()]):
                return None, f"{name} calls {st.proc} with an argument that is not a literal"
            inner, why = body_steps(flow, st.proc, [v for _, v in vals],
                                    {k: v for k, (_, v) in kws.items()}, depth + 1)  # fmt: skip
            if inner is None:
                return None, why
            out += inner
        else:
            what = st.block if isinstance(st, ir.ActionStmt) else f"a {st.kind} statement"
            return None, (f"{name} holds {what}: a role function is presses, waits and calls "
                          "(clicks for the respawn)")  # fmt: skip
    return out, ""


def steps_problem(steps: list[Step], name: str, role: str = "") -> str | None:
    """PURE: why a role body's steps cannot play while the runner waits (None: they fit): at least
    one press or click, at most STEPS_MAX of them, at most STEPS_WAIT_MAX_S of waits in all; the
    way home (``role`` home) presses exactly ONE key (one Butterfly Wing: the runner's rule)."""
    acts = [s for s in steps if s.kind != "wait"]
    waits = sum(s.s for s in steps if s.kind == "wait")
    if not acts:
        return f"{name} presses nothing and clicks nothing"
    n_press = sum(1 for s in steps if s.kind == "press")
    if role == HOME_ROLE and n_press != 1:
        return (f"{name} presses {n_press} keys: the way home is ONE Butterfly Wing (one "
                "press_key, waits around it)")  # fmt: skip
    if len(acts) > STEPS_MAX:
        return (f"{name} has {len(acts)} presses and clicks: at most {STEPS_MAX} in one role "
                "function")  # fmt: skip
    if waits > STEPS_WAIT_MAX_S + 1e-9:
        return (f"{name} waits {waits:g} s in all: at most {STEPS_WAIT_MAX_S:g} s in one role "
                "function (the runner waits while the box plays it)")  # fmt: skip
    return None


def is_body(flow: ir.Flow, name: str | None) -> bool:
    """A role function the BOX plays (stage 3): defined, and anything but exactly one press_key
    statement -- the stage 1-2 KEY shape, which the runner presses itself (one press_key alone is
    the same key at the same moment either way: it stays the runner's own press)."""
    return name is not None and name in flow.procedures and single_press(flow, name) is None


def role_key(flow: ir.Flow, name: str, role: str) -> tuple[str | None, str]:
    """The ONE key of a role (the Run settings, the start's slot check): `resolve_key`'s; for a
    BODY_ROLES function whose body is presses and waits (stage 3), the body's FIRST press."""
    key, why = resolve_key(flow, name)
    if key is not None or role not in BODY_ROLES or name not in flow.procedures:
        return key, why
    steps, why2 = body_steps(flow, name)
    if steps is None:
        return None, f"{name}'s body is not one press_key, nor presses and waits ({why2})"
    first = next((s.key for s in steps if s.kind == "press"), None)
    if first is None:
        return None, f"{name} presses no key"
    return first, ""
