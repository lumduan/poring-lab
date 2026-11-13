"""Live blocks STAGE 4a: ONE FUNCTION PER MONSTER (Batt 2026-11-13: "the core of the hunt (look,
choose a target, walk up, strike, loot, explore): break it into functions, never one block, e.g.
attack_myst_case, attack_cookie, because in the future each monster may get a different skill or
killing technique, and on some we may not swap the knife at all"; docs/planning/live-blocks.md 2b
and 3.4, ADR-0020 Amendment H).

4a: the box decides WHICH technique per monster; the runner still plays every step with its own
code (the runner says WHEN, the box says WHAT). Everything here reads the IR only (PURE): the
linter (lint/recipes.py), the live set (poring_flow.live) and the editor share one definition.

- `use_model("xmas02")` (a core block in a map node's main, before its dungeon_hunt): the TRAINED
  DATA, a models.yaml entry. Its `strikes` (the classes the runner strikes: unit_detector
  MAP_MODELS' collapse) are the monsters the recipes may name; a name the model lacks is an error.
  Live, the hunt core's box detector takes that model (scripts/dungeon_hunt.py box_model_refused:
  refused before any input when it is not live, not for the map, or not the file the detector
  loads there).
- A RECIPE: a function named ``attack_<class>`` (the box's tab `monsters`), its first input the
  target ``t``, an optional ``priority=N`` (a number default), its body the primitives, in one of
  the two orders the runner plays (SHAPES):

      def attack_mystcase(t, priority=1):
          knife_on(); strike(t); wait_steal(t); knife_back(); wait_kill(t); loot(t)
      def attack_cookie(t):
          strike(t); wait_kill(t); loot(t)        # no Knife swap on this monster

  strike = the runner's strike, wait_steal = its bare-steal cue, wait_kill = its kill read,
  loot = its loot step, knife_on() / knife_back() = the hunt core's own Knife functions (stage 3).
  ``use_skill(key="F6")`` is expressible and linted; it does NOT play live in 4a (4b).
- At its lock (the target it strikes, by the detector's species before the collapse), the hunt
  core asks the box which recipe attacks that species: the plan below, decided ONCE before any
  input. A monster without a function: the runner's own recipe (DEFAULT_SHAPE, named as info).
- The primitives play NOWHERE but inside a recipe; a recipe without use_model, a step outside the
  set, an order the runner cannot play, a monster the model lacks: each refused before any input.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal

from poring_flow import functions as fn
from poring_flow import ir
from poring_flow.models import ModelCatalogue, ModelSpec, map_detector, models

VERSION = "9.51"  # scripts/dungeon_hunt.py BOX_RECIPES_VERSION (test_recipes.py pins them)
MODEL_BLOCK = fn.MODEL
STRIKE, WAIT_STEAL, WAIT_KILL, LOOT = "strike", "wait_steal", "wait_kill", "loot"
SKILL = "use_skill"
PRIMITIVES = (STRIKE, WAIT_STEAL, WAIT_KILL, LOOT)
KNIFE_ON, KNIFE_BACK = "knife_on", "knife_back"
PREFIX = "attack_"
MONSTERS_TAB = "monsters"  # the box's tab of recipes (the editor offers the primitives there)
# The two orders the runner plays (4a: its own code at its own moments): today's technique with the
# Knife swap, and the same without it (Batt: "on some we may not swap the knife at all")
KNIFE_SHAPE = (KNIFE_ON, STRIKE, WAIT_STEAL, KNIFE_BACK, WAIT_KILL, LOOT)
PLAIN_SHAPE = (STRIKE, WAIT_KILL, LOOT)
SHAPES = (KNIFE_SHAPE, PLAIN_SHAPE)
DEFAULT_SHAPE = KNIFE_SHAPE  # a monster without a function: the runner's own (its Knife swap on)
PRIORITY = "priority"
PRIORITY_MAX = 10.0
SKILL_WORDS = (
    "cannot play live yet (4b): in 4a the runner has no skill press at the strike (a declared "
    "role key the start's slot check reads, its SP, its cast and after-cast waits)"
)
PRIMITIVE_WORDS = (
    "plays live only inside a monster's recipe (a function attack_<monster>(t) the hunt core asks "
    "at its lock; stage 4a); anywhere else it is 4b's"
)
Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class Recipe:
    """One monster's recipe, as the runner plays it (decided before any input)."""

    species: str  # the model's class (the detector's species before the collapse)
    function: str  # its function's IR name
    steps: tuple[str, ...]  # SHAPES' names; "use_skill" where one stands (never live in 4a)
    priority: float | None = None  # its `priority` input's default (None: none written)
    skill: str | None = None  # use_skill's hotbar key (4b)

    @property
    def knife(self) -> bool:
        """The monster is struck with the Knife swap (knife_on ... knife_back)."""
        return KNIFE_ON in self.steps

    def doc(self) -> dict[str, Any]:
        """dungeon_hunt run(box_recipes=...)'s entry and the records' (plain JSON)."""
        out: dict[str, Any] = {"function": self.function, "steps": list(self.steps),
                               "knife": self.knife, "priority": self.priority}  # fmt: skip
        if self.skill:
            out["skill"] = self.skill
        return out


@dataclass(frozen=True)
class Issue:
    """One finding: its IR node path, what it is about (a block or a function), the rule, the
    words. ``live``: refused before any input (live.problems); False: the lint's alone (info)."""

    path: str
    what: str
    rule: str
    severity: Severity
    words: str
    live: bool = True
    block: str | None = None  # the map block it belongs to (None: the flow's)


@dataclass(frozen=True)
class BlockPlan:
    """What one map block's hunt core takes from the box (live.hunt_plan reads it)."""

    block: str
    model: str | None = None  # the use_model id
    spec: ModelSpec | None = None
    recipes: dict[str, Recipe] = field(default_factory=dict)  # species -> its recipe
    default: tuple[str, ...] = ()  # the species it strikes with no function: the runner's own

    def model_doc(self) -> dict[str, Any] | None:
        """dungeon_hunt run(box_model=...): the catalogue entry, by id."""
        if self.model is None or self.spec is None:
            return None
        s = self.spec
        return {"id": self.model, "file": s.file, "sha256": s.sha256, "maps": list(s.maps),
                "status": s.status, "kind": s.kind, "strikes": list(s.strikes)}  # fmt: skip


def is_primitive(a: ir.ActionStmt) -> bool:
    """A recipe primitive: strike, wait_steal, wait_kill, or loot WITH a target (loot() alone is
    the old block, not live)."""
    return a.block in (STRIKE, WAIT_STEAL, WAIT_KILL) or (a.block == LOOT and "target" in a.params)


def _blocks(flow: ir.Flow) -> list[ir.MapBlock]:
    return list(flow.workflow.blocks) if flow.workflow else []


def species_of(name: str, flow: ir.Flow) -> tuple[str | None, str] | None:
    """(the map block whose own copy it is, or None, the species) for a recipe function's IR name
    -- ``attack_<class>``, or a map node's own ``<node>__attack_<class>`` (the compiler's name when
    Global has one too); None: not a recipe's name."""
    owner: str | None = None
    base = name
    for b in _blocks(flow):
        if name.startswith(f"{b.name}__"):
            owner, base = b.name, name[len(b.name) + 2 :]
            break
    if not base.startswith(PREFIX) or len(base) == len(PREFIX):
        return None
    return owner, base[len(PREFIX) :]


def recipe_functions(flow: ir.Flow, block: str | None = None) -> dict[str, str]:
    """species -> the function a map block's hunt core asks for it (its own copy first), or (block
    None) every recipe function -> its species."""
    if block is None:
        return {n: got[1] for n in flow.procedures if (got := species_of(n, flow)) is not None}
    mine: dict[str, str] = {}
    shared: dict[str, str] = {}
    for n in flow.procedures:
        got = species_of(n, flow)
        if got is None:
            continue
        owner, sp = got
        if owner == block:
            mine[sp] = n
        elif owner is None:
            shared.setdefault(sp, n)
    return {**shared, **mine}


def has_hunt_core(flow: ir.Flow, block: ir.MapBlock) -> bool:
    """The map block's main runs the runner (dungeon_hunt), itself or through a function."""
    return any(a.block == fn.RUNNER_BLOCK for a in fn.actions(list(block.main), flow))


def hunt_model(
    flow: ir.Flow,
    block: ir.MapBlock,
    plans: dict[str, BlockPlan] | None = None,
    cat: ModelCatalogue | None = None,
) -> tuple[str, ModelSpec, bool] | None:
    """PURE: the model a map block's hunt core boxes its monsters with -- its main's use_model
    (True), else the map's own detector (False; models.map_detector, the runner's own box detector
    there). None: the block runs no hunt core, or no detector names what the runner strikes
    there. The runner strikes EVERY class of that model's `strikes`, whatever the recipes say: a
    recipe chooses HOW a monster is attacked (stage 4a), never WHETHER (matpilot round 17 N3)."""
    if not has_hunt_core(flow, block):
        return None
    cat = models() if cat is None else cat
    plans = analyse(flow, cat)[0] if plans is None else plans
    bp = plans.get(block.name)
    if bp is not None and bp.model is not None and bp.spec is not None:
        return bp.model, bp.spec, True
    got = map_detector(block.map.map, cat)
    return None if got is None else (got[0], got[1], False)


def has_recipes(flow: ir.Flow) -> bool:
    """The flow speaks of recipes: a use_model, or a primitive anywhere."""
    for site in ir.sites(flow):
        for a in ir.actions_in(site.stmt):
            if a.block == MODEL_BLOCK or is_primitive(a):
                return True
    return False


def order_problem(steps: list[str] | tuple[str, ...], name: str) -> str | None:
    """PURE: why the runner cannot play these steps in this order (None: one of SHAPES). Named
    for each mistake a person makes (wait_kill before strike, loot before wait_kill, knife_back
    without knife_on, wait_steal without knife_on, ...)."""
    s = [x for x in steps if x != SKILL]
    if tuple(s) in SHAPES:
        return None
    cnt = Counter(s)
    twice = next((x for x in KNIFE_SHAPE if cnt[x] > 1), None)
    if twice is not None:
        return f"{name} has {twice}() twice: one engagement a target, each step once"
    if STRIKE not in s:
        return f"{name} never strikes: a recipe strikes its target once, strike(t)"
    i = s.index
    if WAIT_KILL in s and i(WAIT_KILL) < i(STRIKE):
        return f"{name}: wait_kill(t) before strike(t) -- the kill comes after the strike"
    if LOOT in s and WAIT_KILL in s and i(LOOT) < i(WAIT_KILL):
        return f"{name}: loot(t) before wait_kill(t) -- the loot step comes after the kill"
    if LOOT in s and i(LOOT) < i(STRIKE):
        return f"{name}: loot(t) before strike(t) -- the loot step comes after the kill"
    if KNIFE_BACK in s and KNIFE_ON not in s:
        return f"{name}: knife_back() without knife_on() -- nothing to swap back"
    if WAIT_STEAL in s and KNIFE_ON not in s:
        return (f"{name}: wait_steal(t) without knife_on() -- the steal is the Knife's (without "
                "it the runner waits for the kill only)")  # fmt: skip
    if KNIFE_ON in s and KNIFE_BACK not in s:
        return (f"{name}: knife_on() without knife_back() -- the runner puts the dagger back on "
                "(the steal's cue, its time box, the HP floor)")  # fmt: skip
    if KNIFE_ON in s and WAIT_STEAL not in s:
        return (f"{name}: knife_on() without wait_steal(t) -- the dagger goes back on the "
                "steal's cue")  # fmt: skip
    if WAIT_KILL not in s:
        return f"{name} never waits for the kill: the runner reads every kill (4a): wait_kill(t)"
    if LOOT not in s:
        return (f"{name} never loots: the runner loots every kill (4a; a recipe without loot is "
                "4b's): loot(t) after wait_kill(t)")  # fmt: skip
    if i(KNIFE_ON) > i(STRIKE):
        return f"{name}: knife_on() after the strike -- the Knife goes on before the steal strike"
    if i(WAIT_STEAL) < i(STRIKE):
        return f"{name}: wait_steal(t) before strike(t) -- the steal comes from the strike"
    if i(KNIFE_BACK) < i(WAIT_STEAL):
        return (f"{name}: knife_back() before wait_steal(t) -- the dagger goes back on the "
                "steal's cue")  # fmt: skip
    return (f"{name}: 4a plays the runner's own order: {'(), '.join(KNIFE_SHAPE)}() -- or "
            f"{'(), '.join(PLAIN_SHAPE)}() without the Knife")  # fmt: skip


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def recipe_of(flow: ir.Flow, name: str, species: str, roles: dict[str, str | None],
              block: str) -> tuple[Recipe | None, list[Issue]]:  # fmt: skip
    """PURE: a recipe function's steps (the hunt core's knife roles ``roles``), or None with why."""
    out: list[Issue] = []

    def bad(path: str, rule: str, words: str, sev: Severity = "error", live: bool = True) -> None:
        out.append(Issue(path, name, rule, sev, words, live, block))

    sig = flow.signatures.get(name) or ir.Signature()
    params = list(sig.params)
    t = params[0].name if params and params[0].default is None else None
    if t is None:
        bad(name, "recipe_input", f"{name} takes its target first: def {name}(t)")
    rest = [p for p in params[1:] if p.name != PRIORITY]
    if rest or sig.varargs or sig.kwargs:
        bad(name, "recipe_input", f"{name} takes (t, priority=N) only: the runner hands it the "
            "target it locked, the priority is a number")  # fmt: skip
    priority: float | None = None
    pp = next((p for p in params[1:] if p.name == PRIORITY), None)
    if pp is not None:
        v = _num(pp.default.value) if pp.default is not None else None
        if v is None or not 0 < v <= PRIORITY_MAX:
            bad(name, "recipe_priority", f"{name}'s priority is a number above 0 and at most "
                f"{PRIORITY_MAX:g} (its default: the weight on its value a kill)")  # fmt: skip
        else:
            priority = v
    knives = {roles.get(KNIFE_ON): KNIFE_ON, roles.get(KNIFE_BACK): KNIFE_BACK}
    knives.pop(None, None)
    steps: list[str] = []
    skill: str | None = None
    ok = True
    known = True  # every statement is a step (else its order is not judged: the step is named)
    for i, st in enumerate(flow.procedures.get(name, [])):
        path = f"{name}.{i}"
        if isinstance(st, ir.ActionStmt) and (st.block in PRIMITIVES):
            tgt = st.params.get("target")
            if not (t is not None and isinstance(tgt, ir.Var) and tgt.name == t):
                ok = False
                bad(path, "recipe_target", f"{st.block}(...) in {name}: its target is the "
                    f"recipe's own input {t or 't'}, e.g. {st.block}({t or 't'})")  # fmt: skip
            steps.append(st.block)
        elif isinstance(st, ir.ActionStmt) and st.block == SKILL:
            key = st.params.get("key")
            k = key.value if isinstance(key, ir.Lit) and isinstance(key.value, str) else None
            if k is None or k not in fn.hotbar_keys():
                ok = False
                bad(path, "recipe_skill", f"use_skill in {name} names its skill's hotbar key "
                    'there: use_skill(key="F6")')  # fmt: skip
            else:
                skill = k  # expressible and linted; refused live (its `what` the block's own)
                words = f"use_skill(key={k!r}) in {name} {SKILL_WORDS}"
                out.append(Issue(path, SKILL, "recipe_skill", "warning", words, True, block))
            steps.append(SKILL)
        elif (isinstance(st, ir.CallProc) and st.proc in knives and not st.args
              and not st.kwargs):  # fmt: skip
            steps.append(knives[st.proc])
        else:
            ok = known = False
            if isinstance(st, ir.ActionStmt):
                what = st.block
            else:
                what = f"{st.proc}()" if isinstance(st, ir.CallProc) else f"a {st.kind}"
            shown = " / ".join(f"{n}()" for n in knives) or "knife_on() / knife_back()"
            bad(path, "recipe_step", f"{name} holds {what}: a recipe holds strike(t), "
                f"wait_steal(t), wait_kill(t), loot(t), the hunt core's {shown} and "
                'use_skill(key="F6") (4b), one statement each')  # fmt: skip
    why = order_problem(steps, name) if known else None
    if why is not None:
        ok = False
        bad(name, "recipe_order", why)
    if not ok or t is None:
        return None, out
    return Recipe(species, name, tuple(steps), priority, skill), out


def analyse(flow: ir.Flow, cat: ModelCatalogue | None = None
            ) -> tuple[dict[str, BlockPlan], list[Issue]]:  # fmt: skip
    """PURE: every map block's plan (the hunt cores with a use_model) and every issue of the
    flow's recipes and models (the module docstring). Empty when the flow has none."""
    if not has_recipes(flow):
        return {}, []
    cat = models() if cat is None else cat
    out: list[Issue] = []
    plans: dict[str, BlockPlan] = {}

    def bad(path: str, what: str, rule: str, words: str, block: str | None = None,
            sev: Severity = "error", live: bool = True) -> None:  # fmt: skip
        out.append(Issue(path, what, rule, sev, words, live, block))

    hunts: dict[str, tuple[int, ir.ActionStmt]] = {}  # block -> (its main's statement, the hunt)
    for b in _blocks(flow):
        for i, st in enumerate(b.main):
            got = next((a for a in fn.actions([st], flow) if a.block == fn.RUNNER_BLOCK), None)
            if got is not None:
                hunts[b.name] = (i, got)
                break
    chosen: dict[str, tuple[str, ModelSpec]] = {}
    for site in ir.sites(flow):
        for a in ir.actions_in(site.stmt):
            if a.block != MODEL_BLOCK:
                continue
            path, blk = site.path, site.block.name if site.block is not None else None
            if not (site.scope == "block" and site.depth == 1 and a is site.stmt and blk):
                bad(path, MODEL_BLOCK, "use_model_place", "use_model stands in a map node's main "
                    "(one statement of its own), before its dungeon_hunt: it sets that hunt "
                    "core's model")  # fmt: skip
                continue
            idx = int(path.rsplit(".", 1)[1])
            if blk not in hunts or hunts[blk][0] < idx:
                bad(path, MODEL_BLOCK, "use_model_place", f"use_model sets the hunt core's model: "
                    f"{blk}'s main has no dungeon_hunt after it", blk)  # fmt: skip
                continue
            m = a.params.get("model")
            mid = m.value if isinstance(m, ir.Lit) and isinstance(m.value, str) else None
            if mid is None:
                bad(path, MODEL_BLOCK, "use_model_model", 'use_model names its model as text, '
                    'e.g. use_model("xmas02"), so it can be checked', blk)  # fmt: skip
                continue
            spec = cat.models.get(mid)
            if blk in chosen:
                bad(path, MODEL_BLOCK, "use_model_place", f"{blk}'s main names a model twice: "
                    "one use_model for its hunt core", blk)  # fmt: skip
                continue
            if spec is None:
                bad(path, MODEL_BLOCK, "use_model_model", f"there is no trained model {mid} "
                    f"({', '.join(cat.models)})", blk)  # fmt: skip
                continue
            map_ = site.block.map.map if site.block is not None else ""
            why = None
            if not spec.available:
                why = f"the model {mid} is not adopted, so it is not a working sensor: {spec.why}"
            elif spec.kind != "detector":
                why = f"{mid} is a boss recognizer: the hunt core's box detector is a detector"
            elif spec.maps and map_ not in spec.maps:
                why = f"{mid} is trained for {', '.join(spec.maps)} only; {blk} is on {map_}"
            elif not spec.strikes:
                why = f"{mid} names no monster the runner strikes (models.yaml strikes)"
            if why is not None:
                bad(path, MODEL_BLOCK, "use_model_model", why, blk)
                continue
            chosen[blk] = (mid, spec)
    all_recipes = recipe_functions(flow)
    for blk, (mid, spec) in chosen.items():
        hunt = hunts[blk][1]
        roles = fn.role_functions(hunt)
        recipes: dict[str, Recipe] = {}
        for sp, name in sorted(recipe_functions(flow, blk).items()):
            if sp not in spec.classes:
                bad(name, name, "recipe_class", f"{name}: the model {mid} has no class {sp} (its "
                    f"monsters: {', '.join(spec.strikes)})", blk)  # fmt: skip
                continue
            if sp not in spec.strikes:
                bad(name, name, "recipe_class", f"{name}: the runner never strikes {sp} (its own "
                    "rule takes it, e.g. the Garm Baby's Fly Wing); a recipe attacks a monster it "
                    f"strikes: {', '.join(spec.strikes)}", blk)  # fmt: skip
                continue
            made, issues = recipe_of(flow, name, sp, roles, blk)
            out += issues
            if made is not None:
                recipes[sp] = made
        default = tuple(s for s in spec.strikes if s not in recipe_functions(flow, blk))
        for sp in default:
            bad(blk, sp, "recipe_default", f"{sp}: no attack function (attack_{sp}); the runner's "
                f"own recipe ({'(), '.join(DEFAULT_SHAPE)}())", blk, "info", False)  # fmt: skip
        plans[blk] = BlockPlan(blk, mid, spec, recipes, default)
    if all_recipes and not chosen:  # recipes without use_model (or without a working one)
        for name in all_recipes:
            bad(name, name, "recipe_model", f"{name} is a monster's recipe: it needs "
                'use_model("...") in the main of the map node whose hunt core attacks (the '
                "model's monsters are the ones a recipe names)")  # fmt: skip
    for site in ir.sites(flow):  # the hunt core asks a recipe at its lock; no block calls one
        for proc in dict.fromkeys(ir.calls_in(site.stmt)):
            if proc in all_recipes:
                bad(site.path, proc, "recipe_call", f"{proc}() is a monster's recipe: the hunt "
                    "core asks it at its lock and plays it with its own code; a block never "
                    "calls it (4b)")  # fmt: skip
    for site in ir.sites(flow):  # (a recipe without a model is named above, not its steps)
        inside = site.scope == "procedure" and site.root in all_recipes
        for a in ir.actions_in(site.stmt):
            if is_primitive(a) and not (inside and a is site.stmt and site.depth == 1):
                bad(site.path, a.block, "recipe_primitive", f"{a.block} {PRIMITIVE_WORDS}")
    return plans, out
