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

Everything the compiled flow holds is checked (every map node's main, events and extensions,
every function, every Global event), not only what one path reaches: a relocation can land on any
map node, and a person reads one refusal list before Run, not a surprise mid-run.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any

from poring_flow import functions as fn
from poring_flow import ir
from poring_flow.catalogue import Catalogue, catalogue

STAGE = 2
# scripts/dungeon_hunt.py SURVIVAL_EVENTS_VERSION (stage 1 was 9.48, its LIVE_BLOCKS_VERSION);
# test_live_player.py pins them together
VERSION = "9.49"
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
    "respawn": "stage 2",
    "escape": "stage 2",
    "use_item": "stage 2",
    "walk_to": "stage 4",
    "walk_away": "stage 4",
    "attack_nearest": "stage 4",
    "finish_target": "stage 4",
    "loot": "stage 4",
    "use_skill": "stage 4",
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
HUNT_SENSORS = ("hp_percent", "sp_percent", "sees_boss")
# the statements its body may hold: the runner WAITS while the box plays, so no wait, no loop
HUNT_STATEMENTS = ("action", "call", "if", "set", "return")
# dungeon_hunt's roles whose key the box may press inside it (the knife, the dagger and home stay
# the runner's in stage 2), and the runner's own handler each pressed key switches off
HUNT_ROLES = ("heal", "fly")
PLAYS = ("potion", "fly_hp", "boss_fly")


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
    for block in dict.fromkeys(b for b, _ in runner_blocks(flow)):  # stage 2: inside the hunt
        for nl in hunt_plan(flow, block, cat).problems:
            if (nl.path, nl.what) not in seen:
                seen.add((nl.path, nl.what))
                out.append(nl)
    return out


# Blocks whose live binding is the player's OWN code, not an L2 binding: the hunt core is the
# runner (scripts/dungeon_hunt.py run, in-process), so a readiness item of combat.hunt's L2
# binding (L2.input.attack_click ...) is answered by it. Every other readiness item still refuses.
OWN_BINDING = (fn.RUNNER_BLOCK,)


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

    for e in merge(flow, b).active():
        if e.built_in or e.key in ir.SAFETY_CRITICAL:
            continue
        h = e.handler
        events.append(e.key)
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
    return HuntPlan(block, keys, tuple(events), frozenset(plays), tuple(out))


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
        },
        "later": later,
    }
