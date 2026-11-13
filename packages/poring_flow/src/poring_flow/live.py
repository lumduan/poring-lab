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
  respawn, escape, /where -- are stage 2); while the hunt core runs, the runner's own survival
  plays (stage 2 moves it into the box's events through the hunt core's tick hook).

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

STAGE = 1
VERSION = "9.48"  # scripts/dungeon_hunt.py LIVE_BLOCKS_VERSION (test_live_player.py pins both)
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
        "later": later,
    }
