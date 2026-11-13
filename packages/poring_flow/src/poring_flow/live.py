"""The LIVE BLOCK PLAYER's set: what a project may hold for the real game (Batt 2026-11-13,
docs/planning/live-blocks.md stage 1; ADR-0020 Amendment E). The player is scripts/flow_play.py.

ONE place says what plays live: the catalogue's `live: true` flags (blocks.yaml, per block and per
sensor) and, here, the statement kinds, exits and event endings the player's scheduler binds. Every
other block, sensor, statement or exit has NO live binding: the player refuses BEFORE ANY INPUT,
naming each one ("walk_to cannot play live yet (stage 4)"), and POST /flows/run/project refuses the
run with `not_live` and the same words. GET /flows/catalogue serves `document()` as `live`.

Stage 1 (the stages: live-blocks.md section 2):
- blocks: press_key (ro_agent's paced key tap through the mux), dungeon_hunt (the runner's play
  IN-PROCESS, the same Agent: the hunt core), assert_save_point (no input);
- sensors: hp_percent, sp_percent, weight_percent (the HP / SP percent lines, the weight readout),
  is_dead (the death dialog), current_map and map_load_seen (the map's NAME from the minimap's
  picture: minimap_id.py, no /where typed);
- statements: if, while, repeat, for, set, call (functions with inputs), return, stop, break,
  continue, wait_until (`wait(s)` is wait_until(False, s)), an action of a live block;
- exits: item_warp by a FUNCTION (its body runs, then the minimap must name the target node's
  map); walk_exit, npc_warp and an item_warp by item are not live;
- events: a def with a trigger, insert or pre-empt, evaluated on fresh sensor values each tick;
  `then` relocate relocates by the map's NAME (no /where). The always-on safety events the
  project does not write (dead, hp_critical, unexpected_map: always_on.BUILT_IN) play as the
  SAFE END in stage 1: everything held is released and the run ends, named (their bodies --
  respawn, escape, /where -- are a later stage).

Stage 2 (Batt 2026-11-13: "Heal, Fly Wing, Knife swap: write every one as a FUNCTION. Heal: press
F1 when HP < 30 %. Fly Wing: press F8 when a boss is seen or HP < 25 %"): the box's own EVENTS play
INSIDE the hunt core, through its tick hook (`hunt_plan`; scripts/flow_play.py HuntHook.survive,
scripts/dungeon_hunt.py run(box_plays=...)). On a map node with a hunt core, every user event
active there (its own, Global's) is evaluated on EVERY tick of the runner with the tick's own
values (HUNT_SENSORS: hp_percent, sp_percent and the new sensor sees_boss, the runner's boss read)
by the engine's rules, and its body is played at once through the SAME Agent while the runner
waits. Inside the hunt core such an event may press only dungeon_hunt's heal and fly keys
(HUNT_ROLES), through calls, if, set and return (HUNT_STATEMENTS), and it must resume; anything else
is refused before any input, named. The runner's own handler for each thing the box plays is
switched off for that run (PLAYS: the potion, the Fly Wing on HP, the boss fly); everything else
stays the runner's (the HP-rate fly, the Garm Baby, the stock, the dead jump, an unread position,
the NPC guard, the knife, the way home).

Stage 3 (Batt 2026-11-13: "The Knife swap (Damascus): a function: press F4, wait 100 ms, press
F5; the other way back to the Knife: the same swapped"; "make respawn a function block, in case
another server's menu differs"; live-blocks.md 3.3, ADR-0020 Amendment G): the Knife swap, the
respawn, the weight home and the way home at the end are the BOX's too. The runner keeps deciding
WHEN; at each of its moments the hunt core CALLS the role's function (`HuntPlan.calls`: its STEPS,
presses / waits / clicks, flattened through calls with literal arguments) and the live player plays
them through the runner's OWN press of that role (scripts/flow_play.py HuntHook.call). PLAYS:
- "knife": dungeon_hunt's knife_on / knife_back name a BODY (anything but one press_key statement:
  functions.is_body); both moments call the box; every key they press is one of the two knife keys;
  knife_back ends on the dagger's key; knife_on ends on the Knife's (the strike between, the
  runner's own today) or on the dagger's (no strike between: `knife_ends` "armed");
- "home_end": the home role names a BODY; it presses the home key only;
- "respawn": the new optional role `respawn` (and `respawn_confirm`) names a function of click_at
  and waits: the death exit's two presses; click_at plays NOWHERE else (refused before any input);
- "weight_home": an event that reads weight_percent() (the runner's weight read, at its UI watch,
  never mid-fight) and whose body is one stop: the run ends normally and the runner's end flies her
  home; the runner's own weight exit (--weight-home on a read weight) is off.
A role function that is exactly one press_key stays the runner's own key (the stage 1-2 shape): a
box without these plays exactly as stage 2.

Stage 4a (Batt 2026-11-13: "break the core into functions, e.g. attack_myst_case, attack_cookie,
because in the future each monster may get a different skill or killing technique, and on some we
may not swap the knife at all"; live-blocks.md 2b and 3.4, ADR-0020 Amendment H; poring_flow.recipes
holds the rules): the box decides WHICH technique per monster, the runner still plays every step.
PLAYS:
- "model": `use_model("xmas02")` in the map node's main, before its dungeon_hunt: the hunt core's
  box detector takes that models.yaml entry (the runner refuses, before any input, one that is not
  the file its detector loads there: dungeon_hunt.box_model_refused);
- "recipes": one function per monster, attack_<class>(t, priority=N), a recipe of the primitives
  strike / wait_steal / wait_kill / loot(t) and the hunt core's knife_on() / knife_back(), in one of
  the two orders the runner plays (recipes.SHAPES). At its lock the hunt core asks the box which
  recipe attacks that species (HuntPlan.recipes, decided before any input) and plays it with its own
  code: a recipe without knife_on() strikes that monster without the Knife swap; a monster without
  a function gets the runner's own recipe. The primitives play nowhere else; use_skill in a recipe
  is linted and refused live (4b).
A box without use_model and recipes plays exactly as stage 3 (run() gets no box_model, no
box_recipes).

Everything the compiled flow holds is checked (every map node's main, events and extensions,
every function, every Global event), not only what one path reaches: a relocation can land on any
map node, and a person reads one refusal list before Run, not a surprise mid-run.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any

from poring_flow import functions as fn
from poring_flow import ir
from poring_flow import recipes as rc
from poring_flow.catalogue import Catalogue, catalogue

STAGE = 4
# scripts/dungeon_hunt.py BOX_RECIPES_VERSION (stage 4a; stage 3 was 9.50, its
# BOX_FUNCTIONS_VERSION; stage 2 9.49, its SURVIVAL_EVENTS_VERSION; stage 1 9.48, its
# LIVE_BLOCKS_VERSION); test_live_player.py pins them together
VERSION = rc.VERSION
STATEMENTS = (
    "action",
    "if",
    "while",
    "wait_until",
    "repeat",
    "for",
    "set",
    "call",
    "return",
    "stop",
    "break",
    "continue",
    "take_exit",
)
EXITS = ("item_warp",)  # by a FUNCTION only (Exit.proc)
# The words of "not yet": the stage each one is planned in (live-blocks.md section 2 and 4)
LATER: dict[str, str] = {
    "respawn": "a later stage: in a hunt core, dungeon_hunt's respawn function plays it",
    "escape": "a later stage",
    "use_item": "a later stage: press_key the item's hotbar key",
    "walk_to": "stage 4",
    "walk_away": "stage 4",
    "attack_nearest": "stage 4",
    "finish_target": "stage 4",
    "use_skill": "stage 4b: a skill press of a declared role key at the strike, in a monster's "
    "recipe",
    "hunt": "stage 4",
    "sees": "stage 4",
    "count_visible": "stage 4",
    "detector_sees": "stage 4",
    "detector_count": "stage 4",
    "engagement_seen": "stage 4",
    "engaged_species": "stage 4",
    "walk_exit": "stage 4",
    "npc_warp": "a later stage",
}
LATER_DEFAULT = "a later stage"
HELPER_SENSORS = ("known",)  # `known(x)`: no read of its own (runtime.Sim._sense)
# Stage 2: what an event may read and do while the HUNT CORE plays (its tick hook, the module
# docstring). The sensors a hunt tick carries (dungeon_hunt.HuntTick: hp_pct, sp_pct, boss)
HUNT_SENSORS = ("hp_percent", "sp_percent", "sees_boss", "weight_percent")
# stage 3: weight_percent is the runner's weight read at its UI watch (HuntTick.weight_pct): only
# the WEIGHT event reads it, there (the runner's own moment, never mid-fight)
WEIGHT_SENSOR = "weight_percent"
# the statements its body may hold: the runner WAITS while the box plays, so no wait, no loop
HUNT_STATEMENTS = ("action", "call", "if", "set", "return")
# dungeon_hunt's roles whose key the box may press inside it (the knife, the dagger and home stay
# the runner's in stage 2), and the runner's own handler each pressed key switches off
HUNT_ROLES = ("heal", "fly")
# stage 3 adds the role functions the hunt core CALLS and the weight home (the module docstring)
PLAYS = ("potion", "fly_hp", "boss_fly", "knife", "respawn", "weight_home", "home_end",
         "model", "recipes")  # fmt: skip  # stage 4a: the box's model and its monsters' recipes
CALL_ROLES = ("knife_on", "knife_back", "home", "respawn", "respawn_confirm")


@dataclass(frozen=True)
class NotLive:
    """One thing the player cannot play: its IR node path, what it is, the words."""

    path: str
    what: str  # a block, a sensor, an exit kind or a statement kind
    words: str


def live_blocks(cat: Catalogue | None = None) -> list[str]:
    cat = cat or catalogue()
    return sorted(n for n, b in cat.blocks.items() if b.spec.live)


def live_sensors(cat: Catalogue | None = None) -> list[str]:
    cat = cat or catalogue()
    return sorted(n for n, s in cat.sensors.items() if s.spec.live)


def words(what: str) -> str:
    return f"{what} cannot play live yet ({LATER.get(what, LATER_DEFAULT)})"


def problems(flow: ir.Flow, cat: Catalogue | None = None) -> list[NotLive]:
    """Every block, sensor, statement and exit of the flow without a live binding, one per path
    and thing (the always-on built-ins the flow does not write are not checked: the module
    docstring). Empty: the player may play it."""
    cat = cat or catalogue()
    blocks, sensors = set(live_blocks(cat)), set(live_sensors(cat))
    out: list[NotLive] = []
    seen: set[tuple[str, str]] = set()

    def bad(path: str, what: str, text: str | None = None) -> None:
        if (path, what) not in seen:
            seen.add((path, what))
            out.append(NotLive(path, what, text or words(what)))

    def expr(path: str, e: Any) -> None:
        for x in ir.sub_exprs(e):
            if isinstance(x, ir.Sense) and x.sensor not in sensors | set(HELPER_SENSORS):
                bad(path, x.sensor)
            elif isinstance(x, ir.Do) and x.action.block not in blocks:
                bad(path, x.action.block)

    for site in ir.sites(flow):
        st = site.stmt
        if st.kind not in STATEMENTS:
            bad(site.path, st.kind)
        if isinstance(st, ir.ActionStmt) and st.block not in blocks:
            bad(site.path, st.block)
        if isinstance(st, ir.TakeExit):
            x = st.exit
            if x.kind not in EXITS:
                bad(site.path, x.kind)
            elif x.proc is None:
                bad(site.path, "item_warp", "an item warp by an ITEM cannot play live yet (a "
                    "later stage): name a function that presses the wing's key")  # fmt: skip
        for _, e in ir.stmt_exprs(st):
            expr(site.path, e)
    for label, h, _, _ in ir.handler_bodies(flow):
        for cond in (h.when, h.until, h.rearm):
            if cond is not None:
                expr(label, cond)
    if flow.stop_when is not None:
        expr("stop_when", flow.stop_when)
    for site in ir.sites(flow):  # stage 4a: loot plays only as loot(t), inside a recipe
        for a in ir.actions_in(site.stmt):
            if a.block == rc.LOOT and "target" not in a.params:
                bad(site.path, rc.LOOT, f"loot() without its target {rc.PRIMITIVE_WORDS}: "
                    "loot(t) in a monster's recipe")  # fmt: skip
    for iss in rc.analyse(flow)[1]:  # stage 4a: the model, the recipes, the primitives' places
        if iss.live:
            bad(iss.path, iss.what, iss.words)
    for nl in click_problems(flow):  # stage 3: click_at only in the death exit
        if (nl.path, nl.what) not in seen:
            seen.add((nl.path, nl.what))
            out.append(nl)
    for block in dict.fromkeys(b for b, _ in runner_blocks(flow)):  # stage 2: inside the hunt
        for nl in hunt_plan(flow, block, cat).problems:
            if (nl.path, nl.what) not in seen:
                seen.add((nl.path, nl.what))
                out.append(nl)
    return out


CLICK_WORDS = (
    "click_at plays live only inside dungeon_hunt's respawn functions, in the hunt "
    "core's death exit (stage 3); a click anywhere else in the world is stage 4's"
)


def click_problems(flow: ir.Flow) -> list[NotLive]:
    """Stage 3: every click_at, and every call of a function that clicks, outside the functions a
    hunt core's respawn roles name (and the functions they call): refused before any input."""
    clicks = {name for name, body in flow.procedures.items()
              if any(a.block == fn.CLICK for a in fn.actions(list(body), flow))}  # fmt: skip
    if not clicks:
        return []
    allowed: set[str] = set()
    for _, a in runner_blocks(flow):
        for name in fn.role_functions(a, fn.CLICK_ROLES).values():
            if name is not None and name in flow.procedures:
                allowed.add(name)
                allowed.update(x for x in flow.procedures
                               if x in _reached(flow, name))  # fmt: skip
    out: list[NotLive] = []
    for site in ir.sites(flow):
        inside = site.scope == "procedure" and site.root in allowed
        if inside:
            continue
        for a in ir.actions_in(site.stmt):
            if a.block == fn.CLICK:
                out.append(NotLive(site.path, fn.CLICK, CLICK_WORDS))
        called = list(ir.calls_in(site.stmt))
        if isinstance(site.stmt, ir.TakeExit) and site.stmt.exit.proc is not None:
            called.append(site.stmt.exit.proc)
        for proc in called:
            if proc in clicks:
                out.append(NotLive(site.path, proc, f"{proc}() clicks (click_at): {CLICK_WORDS}"))
    return out


def _reached(flow: ir.Flow, name: str) -> set[str]:
    """The functions a function calls, through calls (each once)."""
    out: set[str] = set()
    todo = [name]
    while todo:
        for site in ir.walk(list(flow.procedures.get(todo.pop(), [])), "x", root="x",
                            scope="procedure", block=None):  # fmt: skip
            for proc in ir.calls_in(site.stmt):
                if proc not in out:
                    out.add(proc)
                    todo.append(proc)
    return out


# Blocks whose live binding is the player's OWN code, not an L2 binding: the hunt core is the
# runner (scripts/dungeon_hunt.py run, in-process), so a readiness item of combat.hunt's L2
# binding (L2.input.attack_click ...) is answered by it. Every other readiness item still refuses.
OWN_BINDING = (fn.RUNNER_BLOCK, fn.CLICK, *rc.PRIMITIVES, rc.MODEL_BLOCK)
# (stage 3: click_at is the runner's own respawn press; stage 4a: a recipe's primitives are the
# runner's own strike, steal cue, kill read and loot step, and use_model its own box detector)


def own_binding_paths(c: Any) -> set[str]:
    """The project paths (`project.Compiled.where`) of every action whose live binding is the
    player's own (OWN_BINDING)."""
    out: set[str] = set()
    if c.flow is None:
        return out
    for site in ir.sites(c.flow):
        if any(a.block in OWN_BINDING for a in ir.actions_in(site.stmt)):
            out.add(c.where(site.path).path)
    return out


def verdict(c: Any, findings: list[Any], *, world: Any, resolver_given: bool,
            runtime_max_s: int | None, zones_loaded: bool, routes_loaded: bool,
            server: str | None = None) -> Any:  # fmt: skip
    """The run-start check's verdict (runstart.verdict) for the LIVE player on a compiled project
    (`project.Compiled`) and its findings (`project.PFinding`): exactly the editor's run verdict,
    but a `bindings` readiness item on a hunt core (OWN_BINDING) is answered by the runner."""
    from poring_flow.runstart import verdict as run_verdict

    own = own_binding_paths(c)
    kept = [
        f
        for f in findings
        if not (f.rule == "bindings" and f.severity == "readiness" and f.where.path in own)
    ]
    assert c.flow is not None
    return run_verdict(
        c.flow, [f.finding() for f in kept], world_loaded=world is not None,
        resolver_given=resolver_given, runtime_max_s=runtime_max_s, zones_loaded=zones_loaded,
        server=server, world_server=world.server if world is not None else None,
        routes_loaded=routes_loaded,
    )  # fmt: skip


def runner_blocks(flow: ir.Flow) -> list[tuple[str, ir.ActionStmt]]:
    """(the map block, the action) of every hunt core (dungeon_hunt) in the map nodes' mains and
    the functions they call, in order."""
    out: list[tuple[str, ir.ActionStmt]] = []
    for b in flow.workflow.blocks if flow.workflow else []:
        for a in fn.actions(list(b.main), flow):
            if a.block == fn.RUNNER_BLOCK:
                out.append((b.name, a))
    return out


# --- stage 2: the box's events INSIDE the hunt core ----------------------------------------------
@dataclass(frozen=True)
class HuntPlan:
    """What the box plays inside one map node's hunt core (the module docstring, stage 2)."""

    block: str
    keys: dict[str, str]  # the role -> its key: heal F1, fly F8 (what the box may press there)
    events: tuple[str, ...]  # the user events that play inside it (their keys), in order
    plays: frozenset[str]  # the runner's own handlers they replace (PLAYS)
    problems: tuple[NotLive, ...]  # why it cannot play (each one refuses before any input)
    # stage 3: the role functions the hunt core CALLS (role -> its steps, and its function's
    # name), the events that read the weight (played at the runner's weight read only), and where
    # knife_on's body leaves her: "opener" (the Knife worn: the strike between, the runner's own)
    # or "armed" (the dagger back already: no strike between)
    calls: dict[str, tuple[fn.Step, ...]] = field(default_factory=dict)
    call_names: dict[str, str] = field(default_factory=dict)
    weight_events: tuple[str, ...] = ()
    knife_ends: str = "opener"
    # stage 4a: the box's model (use_model: its id and catalogue entry for the runner) and its
    # monsters' recipes (species -> the recipe the hunt core plays at its lock), and the species
    # the runner strikes with no function (its own recipe)
    model: str | None = None
    model_doc: dict[str, Any] | None = None
    recipes: dict[str, rc.Recipe] = field(default_factory=dict)
    default_species: tuple[str, ...] = ()


def _sensors(e: Any) -> set[str]:
    return {x.sensor for x in ir.sub_exprs(e) if isinstance(x, ir.Sense)}


def hunt_plan(flow: ir.Flow, block: str, cat: Catalogue | None = None) -> HuntPlan:
    """PURE: the user events active on `block` (its own and Global's; the always-on safety three
    keep stage 1's rule) and what they take over from its hunt core. An event plays inside the
    hunt core when it reads only HUNT_SENSORS, presses only the heal / fly role keys (literal
    keys, through calls with literal arguments), holds only HUNT_STATEMENTS and resumes. PLAYS:
    `potion` when one presses the heal key; `fly_hp` / `boss_fly` when one presses the fly key on
    a condition (`when`) that reads hp_percent / sees_boss."""
    from poring_flow.effective import merge

    cat = cat or catalogue()
    b = next((x for x in (flow.workflow.blocks if flow.workflow else []) if x.name == block), None)
    hunt = next((a for bl, a in runner_blocks(flow) if bl == block), None)
    if b is None or hunt is None:
        return HuntPlan(block, {}, (), frozenset(), ())
    roles = fn.role_functions(hunt)
    keys: dict[str, str] = {}
    for role in HUNT_ROLES:
        name = roles.get(role)
        key = fn.resolve_key(flow, name)[0] if name else None
        if key is not None:
            keys[role] = key
    allowed = set(keys.values())
    shown = " and ".join(f"{r} ({k})" for r, k in keys.items()) or "no role key"
    readable = set(HUNT_SENSORS) | set(HELPER_SENSORS)
    out: list[NotLive] = []
    events: list[str] = []
    plays: set[str] = set()

    def bad(path: str, what: str, text: str) -> None:
        out.append(NotLive(path, what, text))

    def expr(path: str, e: Any) -> None:
        for x in ir.sub_exprs(e):
            if isinstance(x, ir.Sense) and x.sensor not in readable:
                bad(path, x.sensor, f"{x.sensor}() cannot be read inside the hunt core: there an "
                    f"event reads only {', '.join(HUNT_SENSORS)} (stage 2)")  # fmt: skip
            elif isinstance(x, ir.Do | ir.CallV):
                what = x.action.block if isinstance(x, ir.Do) else x.proc
                bad(path, what, f"{what} as a value cannot play inside the hunt core (stage 2)")

    def body(path: str, stmts: list[Any], env: dict[str, Any], depth: int,
             pressed: list[str]) -> None:  # fmt: skip
        for st in stmts:
            if st.kind not in HUNT_STATEMENTS:
                bad(
                    path,
                    st.kind,
                    f"a {st.kind} statement cannot play inside the hunt core: the "
                    "runner waits while the box plays (presses, calls, if, set, return; stage 2)",
                )
                continue
            for _, e in ir.stmt_exprs(st):
                expr(path, e)
            if isinstance(st, ir.ActionStmt):
                if st.block != fn.PRESS:
                    bad(path, st.block, f"{st.block} cannot play inside the hunt core (stage 2: "
                        "press_key only)")  # fmt: skip
                    continue
                known, v = fn.literal_value(st.params.get("key"), env)
                if not known or not isinstance(v, str):
                    bad(path, fn.PRESS, "a press_key inside the hunt core needs its key known "
                        "before the run (a literal, or an input given one)")  # fmt: skip
                elif v not in allowed:
                    bad(path, fn.PRESS, f"presses {v} inside the hunt core: there the box presses "
                        f"only dungeon_hunt's {shown} keys (the knife, the dagger and the way "
                        "home stay the runner's in stage 2)")  # fmt: skip
                else:
                    pressed.append(v)
            elif isinstance(st, ir.If):
                body(path, list(st.then), env, depth, pressed)
                body(path, list(st.orelse), env, depth, pressed)
            elif isinstance(st, ir.CallProc):
                vals = [fn.literal_value(a, env) for a in st.args]
                kws = {k: fn.literal_value(a, env) for k, a in st.kwargs.items()}
                if not all(k for k, _ in [*vals, *kws.values()]):
                    bad(
                        path,
                        st.proc,
                        f"{st.proc} is called with an argument that is not a "
                        "literal: inside the hunt core its keys must be known before the run",
                    )
                    continue
                inner = fn.bind_literals(flow, st.proc, [v for _, v in vals],
                                         {k: v for k, (_, v) in kws.items()})  # fmt: skip
                if inner is None or depth >= fn.MAX_KEY_DEPTH:
                    bad(path, st.proc, f"{st.proc}() cannot be followed inside the hunt core "
                        "(its inputs do not fit, or its calls go too deep)")  # fmt: skip
                    continue
                body(path, list(flow.procedures.get(st.proc, [])), inner, depth + 1, pressed)

    weights: list[str] = []
    for e in merge(flow, b).active():
        if e.built_in or e.key in ir.SAFETY_CRITICAL:
            continue
        h = e.handler
        events.append(e.key)
        conds = [c for c in (h.when, h.until, h.rearm) if c is not None]
        if any(WEIGHT_SENSOR in _sensors(c) for c in conds):  # stage 3: the weight home
            weights.append(e.key)
            _weight_event(e, conds, out)
            plays.add("weight_home")
            continue
        if h.then != "resume":
            bad(e.label, "then", f"{e.key} ends with then={h.then}: inside the hunt core an event "
                "must resume (the runner goes on after it; stage 2)")  # fmt: skip
        if h.escalate is not None:
            bad(e.label, "escalate", f"{e.key} escalates to {h.escalate}: not inside the hunt "
                "core (stage 2)")  # fmt: skip
        for cond in (h.when, h.until, h.rearm):
            if cond is not None:
                expr(e.label, cond)
        pressed: list[str] = []
        n_bad = len(out)
        body(e.label, [*e.extension, *h.body], {}, 0, pressed)
        if not pressed and len(out) == n_bad:
            bad(e.label, "event", f"{e.key} presses no key inside the hunt core: there an event "
                f"plays dungeon_hunt's {shown} keys (stage 2)")  # fmt: skip
        if keys.get("heal") in pressed:
            plays.add("potion")
        if keys.get("fly") in pressed:
            reads = _sensors(h.when)
            if "hp_percent" in reads:
                plays.add("fly_hp")
            if "sees_boss" in reads:
                plays.add("boss_fly")
            if not reads & {"hp_percent", "sees_boss"}:
                bad(
                    e.label,
                    "when",
                    f"{e.key} presses the Fly Wing ({keys['fly']}) inside the "
                    "hunt core on a condition that reads neither hp_percent() nor sees_boss(): "
                    "there the box's Fly Wing replaces the runner's on HP or on a boss (stage 2)",
                )
    hpath = next((s.path for s in ir.sites(flow)
                  if any(a is hunt for a in ir.actions_in(s.stmt))), block)  # fmt: skip
    calls, names, ends = _role_calls(flow, hunt, plays, out, hpath)
    rplans, issues = rc.analyse(flow)  # stage 4a: the model and the recipes of THIS hunt core
    out += [NotLive(i.path, i.what, i.words) for i in issues if i.live and i.block == block]
    rp = rplans.get(block)
    if rp is not None and rp.model is not None:
        plays.add("model")
    if rp is not None and rp.recipes:
        plays.add("recipes")
    return HuntPlan(block, keys, tuple(events), frozenset(plays), tuple(out), calls, names,
                    tuple(weights), ends, None if rp is None else rp.model,
                    None if rp is None else rp.model_doc(), {} if rp is None else dict(rp.recipes),
                    () if rp is None else rp.default)  # fmt: skip


def _weight_event(e: Any, conds: list[Any], out: list[NotLive]) -> None:
    """Stage 3: an event that reads the weight inside the hunt core is the WEIGHT HOME -- it reads
    only weight_percent() (the runner's weight read at its UI watch), it is a pre-empt (an
    inserted event's stop would count as its failure), and its body is ONE stop: the run ends
    there, normally, and the runner's end flies her home."""
    reads = set().union(*(_sensors(c) for c in conds)) - set(HELPER_SENSORS)
    if reads != {WEIGHT_SENSOR}:
        out.append(NotLive(e.label, "when", f"{e.key} reads {', '.join(sorted(reads))} inside the "
                           "hunt core: an event that reads weight_percent() there reads only it "
                           "(the runner's weight read, at its own moment; stage 3)"))  # fmt: skip
    body = [*e.extension, *e.handler.body]
    if not (len(body) == 1 and isinstance(body[0], ir.Stop)):
        out.append(NotLive(e.label, "event", f"{e.key} reads weight_percent() inside the hunt "
                           "core: there it is the weight home, and its body is one stop (the run "
                           "ends and the runner flies her home; stage 3)"))  # fmt: skip
    if e.handler.mode != "preempt":
        out.append(
            NotLive(
                e.label,
                "mode",
                f"{e.key} stops the run inside the hunt core: it must "
                "be a pre-empt (an inserted event's stop counts as its failure)",
            )
        )


def _role_calls(
    flow: ir.Flow, hunt: ir.ActionStmt, plays: set[str], out: list[NotLive], path: str
) -> tuple[dict[str, tuple[fn.Step, ...]], dict[str, str], str]:
    """Stage 3 (the module docstring): the role functions the hunt core calls, as their steps;
    `plays` gains knife / home_end / respawn; each problem refuses before any input."""
    roles = {**fn.role_functions(hunt), **fn.role_functions(hunt, fn.CLICK_ROLES)}
    keys = {r: fn.role_key(flow, n, r)[0] if n is not None and n in flow.procedures else None
            for r, n in roles.items() if r in fn.ALL_ROLES}  # fmt: skip
    calls: dict[str, tuple[fn.Step, ...]] = {}
    names: dict[str, str] = {}
    ends = "opener"

    def steps_of(role: str, allowed: set[str], clicks: bool) -> list[fn.Step] | None:
        name = roles[role]
        assert name is not None
        steps, why = fn.body_steps(flow, name)
        if steps is None:
            out.append(NotLive(path, role, f"dungeon_hunt's {role} ({name}): {why} (stage 3)"))
            return None
        bad = fn.steps_problem(steps, name, role)
        for st in steps:
            if st.kind == "press" and st.key not in allowed:
                bad = bad or (f"{name} presses {st.key}: at that moment the hunt core hands the "
                              f"box only {', '.join(sorted(k for k in allowed if k)) or 'no key'}"
                              " (keys the start's slot check reads)")  # fmt: skip
            elif st.kind == "click" and not clicks:
                bad = bad or f"{name} clicks (click_at): {CLICK_WORDS}"
            elif st.kind == "click" and not (0 <= st.x < fn.GAME_PX[0]
                                             and 0 <= st.y < fn.GAME_PX[1]):  # fmt: skip
                bad = bad or (f"{name} clicks at {st.x}, {st.y}: off the game picture "
                              f"({fn.GAME_PX[0]} x {fn.GAME_PX[1]})")  # fmt: skip
        if bad is not None:
            out.append(NotLive(path, role, f"dungeon_hunt's {role}: {bad} (stage 3)"))
            return None
        calls[role], names[role] = tuple(steps), name
        return steps

    kon, kback = roles.get("knife_on"), roles.get("knife_back")
    if fn.is_body(flow, kon) or fn.is_body(flow, kback):  # the Knife swap: both moments the box's
        plays.add("knife")
        wk = {k for k in (keys.get("knife_on"), keys.get("knife_back")) if k is not None}
        on_steps = steps_of("knife_on", wk, False) if kon in flow.procedures else None
        back_steps = steps_of("knife_back", wk, False) if kback in flow.procedures else None
        last = [s.key for s in back_steps or [] if s.kind == "press"]
        if back_steps is not None and last and last[-1] != keys.get("knife_back"):
            out.append(
                NotLive(
                    path,
                    "knife_back",
                    f"dungeon_hunt's knife_back ({kback}) ends on "
                    f"{last[-1]}: the swap back ends on the dagger's key "
                    f"({keys.get('knife_back')}), which the runner reads back worn",
                )
            )
        on_last = [s.key for s in on_steps or [] if s.kind == "press"]
        if on_last and on_last[-1] == keys.get("knife_back"):
            ends = "armed"  # "F4, wait, F5": no strike between (the open question, both written)
    home = roles.get("home")
    if fn.is_body(flow, home):
        plays.add("home_end")
        steps_of("home", {k for k in (keys.get("home"),) if k is not None}, False)
    rsp, rok = roles.get("respawn"), roles.get("respawn_confirm")
    for role, name in (("respawn", rsp), ("respawn_confirm", rok)):
        if name is not None and name not in flow.procedures:
            out.append(NotLive(path, role, f"dungeon_hunt's {role}: there is no function {name}"))
    if rok is not None and rsp is None:
        out.append(
            NotLive(
                path,
                "respawn_confirm",
                "dungeon_hunt's respawn_confirm goes with "
                "respawn: the confirmation comes after the dialog's button",
            )
        )
    elif rsp is not None and rsp in flow.procedures:
        plays.add("respawn")
        steps_of("respawn", set(), True)
        if rok is not None and rok in flow.procedures:
            steps_of("respawn_confirm", set(), True)
    return calls, names, ends


def document(cat: Catalogue | None = None) -> dict[str, Any]:
    """GET /flows/catalogue's `live`: what the live block player plays (the browser greys the rest
    and words why). Per block and sensor the same flag is `spec.live`."""
    cat = cat or catalogue()
    later = {n: LATER.get(n, LATER_DEFAULT) for n in itertools.chain(cat.blocks, cat.sensors)}
    for n in (*live_blocks(cat), *live_sensors(cat)):
        later.pop(n, None)
    return {
        "stage": STAGE,
        "version": VERSION,
        "blocks": live_blocks(cat),
        "sensors": live_sensors(cat),
        "statements": list(STATEMENTS),
        "exits": [{"kind": "item_warp", "by": "proc"}],
        "events": {
            "modes": ["insert", "preempt"],
            "relocate": "by the map's name (minimap)",
            "built_in_safety": "the safe end: release everything, end the run (stage 1)",
        },
        "hunt_core": {
            "sensors": list(HUNT_SENSORS),
            "statements": list(HUNT_STATEMENTS),
            "roles": list(HUNT_ROLES),
            "plays": list(PLAYS),
            "words": "inside a hunt core the box's events play on every runner tick; they press "
            "only its heal and fly keys, and the runner's own potion, Fly Wing on HP and boss "
            "fly are off where the box plays them (stage 2)",
            # stage 3: the role functions the hunt core calls at its own moments
            "calls": {
                "roles": list(CALL_ROLES),
                "steps": ["press_key", "wait", "click_at (respawn roles only)", "call"],
                "max_steps": fn.STEPS_MAX,
                "max_wait_s": fn.STEPS_WAIT_MAX_S,
                "weight": f"an event that reads {WEIGHT_SENSOR}() and stops: the weight home",
                "words": "a role function that is more than one press_key is played by the box "
                "at the runner's own moment (the Knife swap, the way home); the respawn functions "
                "click; one press_key alone stays the runner's own key (stage 3)",
            },
            # stage 4a: the box's model and its monsters' recipes (poring_flow.recipes)
            "recipes": {
                "model_block": rc.MODEL_BLOCK,
                "prefix": rc.PREFIX,
                "primitives": list(rc.PRIMITIVES),
                "knife": [rc.KNIFE_ON, rc.KNIFE_BACK],
                "shapes": [list(x) for x in rc.SHAPES],
                "default": list(rc.DEFAULT_SHAPE),
                "priority_max": rc.PRIORITY_MAX,
                "words": "use_model names the trained data; a function attack_<monster>(t) per "
                "monster is its recipe, which the hunt core asks at its lock and plays with its "
                "own code (no knife_on: no Knife swap on that monster); use_skill in a recipe is "
                "4b's",
            },
        },
        "later": later,
    }
