"""Live blocks STAGE 5b-2: THE HUNT LOOP -- the hunt core's steps as live blocks (Batt 2026-11-13:
"break the runner into blocks"; 2026-11-14: "everything in the xmas_dun02 flow, as tabs ... make
them ALL blocks"; docs/planning/live-blocks.md 13.4 and 14).

A map node whose main runs the hunt core (dungeon_hunt) may hold a function ``hunt_loop(t)`` (the
editor puts it in the tab `hunt`). Then the hunt core plays THAT loop instead of its own driver:
scripts/dungeon_hunt.py run() calls the live player's ``hook.drive(cursor)``, and the player plays
the function's statements, each block one BOUNDED call into the runner's own steps through the
TICK CURSOR (dungeon_hunt.HuntCursor: the tick and its next step; a block advances it until its
exit holds, its time box passes, or the run ends). The canonical loop

    def hunt_loop(t):
        while True:
            t = find_target()
            fight(t)               # the monsters tab's recipe for t's species (stage 4a)

plays exactly the runner's own step sequence, tick for tick (scripts/hunt_trace.py). The blocks:

- ``find_target()`` (13.4's explore(): the box's walk tab has a setting named explore, and a
  catalogue name cannot be a variable): the search (the walk, the rest, the White Plant sweep,
  the idle watchdog, the unread position's Fly Wing) until a fight begins; its value the
  monster engaged, none at its time box (its timeout_s, 120 s);
- ``choose_target()``: at once, the monster of the fight that runs (none without one);
- ``walk_to_target(t)``: the fight until its target is in reach ("in_reach" / "gone");
- ``strike(t)``: the fight until the runner's strike locked it ("struck" / "gone");
- ``wait_steal(t)``: the fight while the Knife's bare phase runs ("stolen", "not_stolen",
  "no_knife", "gone");
- ``wait_kill(t)``: the fight to its end ("killed" / "lost");
- ``loot(t)``: the fight's loot step (the loot clicks it made; 0 at once with nothing to loot);
- ``look()``: the tick's reads; ``use_skill(key)``: one press of a DECLARED role key between two
  steps -- the hunt core's heal key (dungeon_hunt.DRIVE_SKILL_ROLES), the one a start's slot check
  reads that a block may press there;
- ``fight(t)``: t's RECIPE (the species the runner locked at its strike; its own recipe where the
  box has none), played as those blocks; knife_on() / knife_back() play at the runner's moments.

Each one hands back at once on the run's end (a RUN_END, the run's time box), on a safety step's
change of mode (a Fly Wing: the target is gone) and on Stop (the tick hook). Everything here reads
the IR only (PURE): the linter (lint/huntloop.py), the live set (poring_flow.live) and the player
share one definition. Refused before any input (the backend's not_live says the same), each named:
- ``hunt_primitive``: a hunt block outside the hunt loop (strike / wait_steal / wait_kill / loot(t)
  also stand in a recipe: 4a's rule);
- ``hunt_loop_place`` / ``hunt_loop_input``: a hunt loop with no hunt core on its node, or not
  ``def hunt_loop(t)`` (one input, the target, none at the start);
- ``hunt_statement``: a statement the loop cannot play while the runner waits for it (a wait, a
  press_key, a call, a stop, an exit: the loop's blocks are the runner's, nothing else plays there);
- ``hunt_sensor``: a sensor in its conditions (the loop reads the hunt through its blocks' values;
  ``known(t)`` alone);
- ``hunt_target``: a block's target that is not a variable (find_target()'s value);
- ``hunt_spin``: a ``while`` whose first statement is not find_target(), or with no block at its top
  level that plays a fight to its end (fight, wait_kill or loot of find_target()'s value): it could
  spin without the hunt core taking a step (the cursor also ends a spin at run time);
- ``hunt_skill``: use_skill without a declared role key.
A recipe's order the cursor cannot play is 4a's (recipes.SHAPES), widened only with a trace test per
new shape; a common step cannot be left out (it has no block); a driving hook without the others is
the runner's own refusal (dungeon_hunt.drive_refused).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from poring_flow import functions as fn
from poring_flow import ir
from poring_flow import recipes as rc

VERSION = "9.55"  # scripts/dungeon_hunt.py HUNT_BLOCKS_VERSION (test_hunt_loop.py pins them)
HUNT_LOOP = rc.HUNT_LOOP
HUNT_TAB = "hunt"  # the editor's tab of the hunt loop (the Hunt category is offered there)
EXPLORE, CHOOSE, WALK = "find_target", "choose_target", "walk_to_target"
LOOK, ATTACK = "look", "fight"
NEW_BLOCKS = (EXPLORE, CHOOSE, WALK, LOOK, ATTACK)
TARGETED = (WALK, *rc.PRIMITIVES, ATTACK)  # each takes the target t (its first parameter)
BLOCKS = (*NEW_BLOCKS, *rc.PRIMITIVES, rc.SKILL)
# each plays a fight to its end: it owns the fight step and hands back only once the fight ended
# (fight through its recipe's wait_kill; loot(t) through its loot step) -- with find_target()
# first, a loop that holds one takes a step on every turn (dungeon_hunt.BLOCK_OWNS)
FIGHT_PLAYERS = (ATTACK, rc.WAIT_KILL, rc.LOOT)
STATEMENTS = ("action", "if", "while", "repeat", "for", "set", "break", "continue", "return")
SENSORS = ("known",)
SKILL_ROLES = ("heal",)  # dungeon_hunt.DRIVE_SKILL_ROLES' "potion": the heal role's key
DEFAULT_TIMEOUT = {EXPLORE: 120.0, WALK: 30.0, rc.STRIKE: 60.0, rc.WAIT_STEAL: 10.0,
                   rc.WAIT_KILL: 120.0, rc.LOOT: 30.0, ATTACK: 300.0}  # fmt: skip  # blocks.yaml
PRIMITIVE_WORDS = (
    "plays live only in the hunt core's hunt loop (a map node's function hunt_loop(t), its tab "
    "hunt; stage 5b-2)"
)
SPIN_WORDS = (
    "the hunt core plays this loop instead of its own: each turn must take a step of the hunt, so "
    "it begins with t = find_target() and holds, at its top level, a block that plays the fight "
    "to its end on t (fight(t), wait_kill(t) or loot(t)) -- else it could spin while no step runs"
)


@dataclass(frozen=True)
class LoopPlan:
    """One map block's hunt loop, as the live player plays it (decided before any input)."""

    block: str
    function: str  # its IR name
    skill_keys: tuple[str, ...] = ()  # the keys its use_skill may press (declared role keys)


def is_hunt_block(a: ir.ActionStmt) -> bool:
    """A block of the hunt loop (rc.is_primitive: loot only with its target)."""
    return a.block in NEW_BLOCKS or a.block == rc.SKILL or rc.is_primitive(a)


def loop_function(flow: ir.Flow, block: str) -> str | None:
    """The IR name of the hunt loop a map block's hunt core plays: its own copy (``<block>__
    hunt_loop``) first, else the flow's ``hunt_loop``; None: none."""
    own = f"{block}__{HUNT_LOOP}"
    if own in flow.procedures:
        return own
    return HUNT_LOOP if HUNT_LOOP in flow.procedures else None


def _skill_keys(flow: ir.Flow, b: ir.MapBlock) -> tuple[str, ...]:
    hunt = next((a for a in fn.actions(list(b.main), flow) if a.block == fn.RUNNER_BLOCK), None)
    if hunt is None:
        return ()
    roles = fn.role_functions(hunt)
    out: list[str] = []
    for r in SKILL_ROLES:
        name = roles.get(r)
        k = fn.resolve_key(flow, name)[0] if name else None
        if k is not None:
            out.append(k)
    return tuple(out)


def _target_var(a: ir.ActionStmt) -> str | None:
    t = a.params.get("target")
    return t.name if isinstance(t, ir.Var) else None


def analyse(flow: ir.Flow) -> tuple[dict[str, LoopPlan], list[rc.Issue]]:
    """PURE: every map block's hunt loop and every issue of the flow's hunt blocks (the module
    docstring). Empty when the flow has none."""
    out: list[rc.Issue] = []

    def bad(path: str, what: str, rule: str, words: str, block: str | None = None) -> None:
        out.append(rc.Issue(path, what, rule, "error", words, True, block))

    loops = {n for n in flow.procedures if n == HUNT_LOOP or n.endswith(f"__{HUNT_LOOP}")}
    uses = any(is_hunt_block(a) and a.block not in rc.PRIMITIVES
               for site in ir.sites(flow) for a in ir.actions_in(site.stmt))  # fmt: skip
    if not loops and not uses:
        return {}, []
    blocks = list(flow.workflow.blocks) if flow.workflow else []
    hunts = [b for b in blocks if rc.has_hunt_core(flow, b)]
    plans: dict[str, LoopPlan] = {}
    for b in hunts:
        name = loop_function(flow, b.name)
        if name is not None:
            plans[b.name] = LoopPlan(b.name, name, _skill_keys(flow, b))
    for name in sorted(loops):
        owner = name[: -len(f"__{HUNT_LOOP}")] if name != HUNT_LOOP else None
        mine = [p for p in plans.values() if p.function == name]
        blk = owner or (mine[0].block if len(mine) == 1 else None)
        if not mine:
            bad(name, HUNT_LOOP, "hunt_loop_place", f"{HUNT_LOOP} is a hunt core's loop: its map "
                "node's main runs dungeon_hunt (it plays this loop instead of its own)",
                blk)  # fmt: skip
        sig = flow.signatures.get(name) or ir.Signature()
        ps = list(sig.params)
        if len(ps) != 1 or ps[0].default is not None or sig.varargs or sig.kwargs:
            bad(name, HUNT_LOOP, "hunt_loop_input", f"{HUNT_LOOP} takes one input, the target its "
                f"blocks work on (none at the start): def {HUNT_LOOP}(t)", blk)  # fmt: skip
        skill = mine[0].skill_keys if mine else ()
        _body(flow, name, blk, skill, bad)
    for site in ir.sites(flow):  # the hunt blocks stand only in a hunt loop (and a recipe, 4a's)
        inside = site.scope == "procedure" and site.root in loops
        for a in ir.actions_in(site.stmt):
            if inside or not is_hunt_block(a) or a.block in rc.PRIMITIVES:
                continue  # (the recipe primitives outside both: recipes.analyse names them)
            if a.block == rc.SKILL and site.scope == "procedure" and site.root in (
                    rc.recipe_functions(flow)):  # fmt: skip
                continue  # use_skill in a recipe: 4a's rule (recipe_skill)
            bad(site.path, a.block, "hunt_primitive", f"{a.block} {PRIMITIVE_WORDS}")
    return plans, out


def _body(flow: ir.Flow, name: str, blk: str | None, skill: tuple[str, ...], bad: Any) -> None:
    """The hunt loop's statements, expressions, targets, keys and loops (the module docstring)."""
    for site in ir.walk(list(flow.procedures.get(name, [])), name, root=name, scope="procedure",
                        block=None):  # fmt: skip
        st, path = site.stmt, site.path
        if st.kind not in STATEMENTS:
            what = {"wait_until": "a wait", "call": "a call", "stop": "a stop",
                    "take_exit": "an exit"}.get(st.kind, f"a {st.kind}")  # fmt: skip
            bad(path, st.kind, "hunt_statement", f"{what} in {HUNT_LOOP}: the hunt core waits for "
                "its blocks and plays nothing else there (its blocks, if, while, repeat, for, set, "
                "break, continue, return; end the loop with break or return -- the runner's end "
                "then runs)", blk)  # fmt: skip
            continue
        for _, e in ir.stmt_exprs(st):
            for x in ir.sub_exprs(e):
                if isinstance(x, ir.Sense) and x.sensor not in SENSORS:
                    bad(path, x.sensor, "hunt_sensor", f"{x.sensor}() in {HUNT_LOOP}: the loop "
                        "reads the hunt through its blocks' values (known(t), a block's outcome); "
                        "the runner reads the sensors itself", blk)  # fmt: skip
                elif isinstance(x, ir.Do) and not is_hunt_block(x.action):
                    bad(path, x.action.block, "hunt_statement", f"{x.action.block} as a value in "
                        f"{HUNT_LOOP}: only its blocks play there", blk)  # fmt: skip
                elif isinstance(x, ir.CallV):
                    bad(path, x.proc, "hunt_statement", f"{x.proc}() as a value in {HUNT_LOOP}: "
                        "a call plays nothing of the hunt there", blk)  # fmt: skip
        for a in ir.actions_in(st):
            if not is_hunt_block(a):
                bad(path, a.block, "hunt_statement", f"{a.block} in {HUNT_LOOP}: the hunt core "
                    "presses and clicks itself there; its blocks are find_target, choose_target, "
                    "walk_to_target, strike, wait_steal, wait_kill, loot, look, fight and "
                    "use_skill (a declared key)", blk)  # fmt: skip
                continue
            if a.block in TARGETED and _target_var(a) is None:
                bad(path, a.block, "hunt_target", f"{a.block}(...) in {HUNT_LOOP}: its target is a "
                    f"variable holding find_target()'s value, e.g. {a.block}(t)", blk)  # fmt: skip
            if a.block == rc.SKILL:
                key = a.params.get("key")
                k = key.value if isinstance(key, ir.Lit) and isinstance(key.value, str) else None
                if k is None or k not in skill:
                    shown = ", ".join(skill) or "none (no heal function on the hunt core)"
                    bad(path, rc.SKILL, "hunt_skill", f"use_skill in {HUNT_LOOP} presses a "
                        "DECLARED role key the start's slot check reads, between two steps: "
                        f"dungeon_hunt's heal key ({shown}); a skill key of its own (a role the "
                        "start checks, its SP, its cast and after-cast waits) is a follow-up",
                        blk)  # fmt: skip
        if isinstance(st, ir.While):
            why = spin_problem(st)
            if why is not None:
                bad(path, "while", "hunt_spin", f"this loop in {HUNT_LOOP}: {why}", blk)


def spin_problem(st: ir.While) -> str | None:
    """PURE: why this loop of a hunt loop could spin without the hunt core taking a step (None: each
    turn takes one) -- SPIN_WORDS' shape: find_target() first, a fight player on its value at the
    top."""
    body = list(st.body)
    first = body[0] if body else None
    if not (isinstance(first, ir.ActionStmt) and first.block == EXPLORE):
        return SPIN_WORDS
    t = first.outcome_to
    if t is None:
        return SPIN_WORDS
    for x in body[1:]:
        if isinstance(x, ir.ActionStmt) and x.block in FIGHT_PLAYERS and _target_var(x) == t:
            return None
    return SPIN_WORDS


def loop_ok(flow: ir.Flow, site: ir.Site) -> bool:
    """A `while` of a hunt loop whose turns each take a step: the hunt core's time box, its end and
    Stop bound it (lint/loops.py's "this loop can never end" does not apply)."""
    st = site.stmt
    if not isinstance(st, ir.While) or site.scope != "procedure":
        return False
    is_loop = site.root == HUNT_LOOP or site.root.endswith(f"__{HUNT_LOOP}")
    return is_loop and spin_problem(st) is None
