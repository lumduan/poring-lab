"""The lint matrix (ADR-0020 F1 / MW1 acceptance): one fixture per rule, with its EXACT message.

Workflow cases plant one fault in Batt's example (13.6.8), as 13.1 says the ADR's own messages do
("the node paths of the Python example, as if each rule's fault were present there"). A case
asserts the messages of its rule that the fault INTRODUCES (variant minus the clean example), so
the example's own findings (test_example.py) never mask or pad a case. Plain-flow cases start
from nothing. Every map, NPC, mob and item is synthetic (flow_synthetic.py).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from poring_flow import ir, pyview
from poring_flow.lint import Detector, Finding, Resolver, default_resolver, lint
from poring_flow.sheet import Kafra, MapFlags, MapSheet, Mob, Npc, NpcWarp, Warp, World
from poring_skills.resolve import Unsupported

sys.path.insert(0, str(Path(__file__).parent))
from flow_synthetic import (  # noqa: E402
    FIXTURES,
    ITEMS,
    farm_sheets,
    farm_world,
    grid,
    resolve_all,
    sheet,
)

FARM = (FIXTURES / "farm_loop.flow").read_text()
HEAD = (
    'flow(ir=2, name="t", max_runtime_s=600, target=target(client="kro-20211103-prere", '
    'server="lab-rathena", locale="en", path=S2))\n'
)
BOX = ((160, 200, 180, 200), (160, 220, 180, 220), (160, 200, 160, 220), (180, 200, 180, 220))
PLAIN_WORLD = World(
    server="lab-rathena",
    sheets={
        "field_1": sheet(
            "field_1",
            warps=[Warp(x=190, y=100, to_map="field_2", to_x=10, to_y=10)],
            npcs=[
                Npc(key="n_aa", x=20, y=20, menu=["o_1"]),
                Npc(key="n_k2", x=30, y=30, kafra=Kafra(services=["storage"])),
            ],
        ),
        "field_2": sheet("field_2", walk=grid(300, 300, BOX), npcs=[Npc(key="n_3f2a", x=50, y=50)]),
    },
    mobs={9101: Mob(id=9101, level=5)},
    items=ITEMS,
)


def farm(*subs: tuple[str, str]) -> str:
    src = FARM
    for old, new in subs:
        assert old in src, old
        src = src.replace(old, new, 1)
    return src


def world(**sheets: MapSheet) -> World:
    return farm_world(**sheets)


def with_mobs(**changes: dict[str, Any]) -> World:
    w = farm_world()
    mobs = dict(w.mobs)
    for key, upd in changes.items():
        mid = int(key.removeprefix("m"))
        mobs[mid] = mobs[mid].model_copy(update=upd) if mid in mobs else Mob(id=mid, **upd)
    return w.model_copy(update={"mobs": mobs})


def map_(name: str, **upd: Any) -> MapSheet:
    return farm_sheets()[name].model_copy(update=upd)


def raises_for(*blocks: str) -> Resolver:
    def res(block: str, concept: str, params: dict[str, str]) -> None:
        if block in blocks:
            raise Unsupported(concept, "L2", "L2.cue.pickup_cursor", "not bound for the test")

    return res


@dataclass
class Case:
    id: str
    rule: str
    source: str | Callable[[], ir.Flow]
    expected: list[str]
    world: World | None = None
    resolver: Resolver | None = field(default=resolve_all)
    farm: bool = True  # a variant of Batt's example (else a plain flow, base = nothing)
    detector: Detector | None = None


def _flow(src: str | Callable[[], ir.Flow], farm_case: bool) -> ir.Flow:
    if callable(src):
        return src()
    return pyview.parse(src if farm_case else HEAD + src)


def _run(c: Case, flow: ir.Flow, w: World | None) -> list[Finding]:
    return lint(flow, world=w, resolver=c.resolver, detector=c.detector)


def introduced(c: Case) -> list[str]:
    w = c.world if c.world is not None else (farm_world() if c.farm else PLAIN_WORLD)
    got = [f.message for f in _run(c, _flow(c.source, c.farm), w) if f.rule == c.rule]
    if not c.farm:
        return sorted(got)
    base = {f.message for f in _run(c, pyview.parse(FARM), farm_world()) if f.rule == c.rule}
    return sorted(m for m in got if m not in base)


# --- IR-only fixtures (constructs the Python view cannot write) ---------------------------------
TARGET = {"client": "kro-20211103-prere", "server": "lab-rathena", "locale": "en"}
SIT = {"kind": "action", "block": "sit", "concept": "char.sit", "timeout_s": 5}


def irflow(*main: dict[str, Any], **over: Any) -> Callable[[], ir.Flow]:
    return lambda: ir.validate(
        {"ir": 2, "name": "t", "target": TARGET, "max_runtime_s": 600, "main": list(main), **over}
    )


def nested(depth: int) -> dict[str, Any]:
    node: dict[str, Any] = SIT
    for _ in range(depth):
        node = {"kind": "if", "cond": {"kind": "lit", "value": True}, "then": [node]}
    return node


def farm_ir(edit: Callable[[dict[str, Any]], None]) -> Callable[[], ir.Flow]:
    def make() -> ir.Flow:
        import json

        data = json.loads(ir.to_json(pyview.parse(FARM)))
        edit(data)
        return ir.validate(data)

    return make


def _add_hp_low(d: dict[str, Any]) -> None:
    d["workflow"]["blocks"][1]["events"].append(
        {
            "kind": "add",
            "event": {
                "name": "hp_low",
                "when": {"kind": "lit", "value": True},
                "priority": "survival",
                "cooldown_s": 5,
                "body": [SIT],
            },
        }
    )


WALK = 'walk_to(cell("field_1", 10, 10))\n'
CASES = [
    # --- layer 1 -------------------------------------------------------------------------------
    Case(
        "repeat",
        "repeat_bounds",
        "for _ in range(0):\n    sit()\n",
        ["main.0: repeat.times must be 1..10000"],
        farm=False,
    ),
    Case(
        "depth",
        "depth",
        irflow(nested(16)),
        ["main.0" + ".then.0" * 16 + ": statements nested deeper than 16"],
        farm=False,
    ),
    Case(
        "nodes",
        "node_count",
        irflow(*[SIT] * 5001),
        ["the flow has 5001 nodes; at most 5000"],
        farm=False,
    ),
    Case(
        "unknown_block",
        "unknown_block",
        irflow(SIT | {"block": "fly_away"}),
        ["main.0: there is no block fly_away"],
        farm=False,
    ),
    Case(
        "concept",
        "block_concept",
        irflow(
            SIT
            | {
                "block": "walk_to",
                "concept": "nav.take_warp",
                "params": {
                    "cell": {
                        "kind": "lit",
                        "value": {"kind": "cell", "map": "field_1", "x": 1, "y": 1},
                    }
                },
            }
        ),
        ["main.0: walk_to runs nav.walk_to, not nav.take_warp"],
        farm=False,
    ),
    Case(
        "param_type",
        "block_params",
        "walk_to(5)\n",
        ["main.0: walk_to's cell takes a cell, not an int"],
        farm=False,
    ),
    Case(
        "param_missing",
        "block_params",
        irflow(SIT | {"block": "walk_to", "concept": "nav.walk_to"}),
        ["main.0: walk_to needs cell"],
        farm=False,
    ),
    Case(
        "sensor",
        "unknown_sensor",
        irflow({"kind": "if", "cond": {"kind": "sense", "sensor": "mana"}, "then": [SIT]}),
        ["main.0: there is no sensor mana"],
        farm=False,
    ),
    Case(
        "variables",
        "variables",
        'COUNT = 0\nCOUNT = "x"\n',
        ["main.0: COUNT holds an int: it cannot take a str"],
        farm=False,
    ),
    Case(
        "recursion",
        "procedures",
        "def a():\n    b()\n\n\ndef b():\n    a()\n\n\nsit()\n",
        ["a: recursion (a → b → a) is not allowed"],
        farm=False,
    ),
    Case(
        "escalate",
        "procedures",
        farm(
            (
                "mode=INSERT, max_per_min=6)\ndef hp_low",
                "mode=INSERT, escalate=leave, max_per_min=6)\ndef hp_low",
            )
        ),
        ["hp_low: escalate names no procedure leave"],
    ),
    Case(
        "names",
        "names",
        irflow(SIT, procedures={"walk_to": [SIT]}),
        ["walk_to is a catalogue name: a procedure cannot reuse it"],
        farm=False,
    ),
    Case(
        "exit_placement",
        "exit_placement",
        irflow(
            {
                "kind": "take_exit",
                "exit": {
                    "kind": "item_warp",
                    "item": {"kind": "item", "id": 9002},
                    "to_block": "a",
                    "to_entry": "b",
                },
            }
        ),
        ["main.0: take_exit belongs in a map block's main"],
        farm=False,
    ),
    Case(
        "map_change",
        "exit_placement",
        farm(("attack_nearest(within=12)", "use_item(WING)")),
        ["farm.0.body.0: a Butterfly Wing changes the map: a map block leaves through take_exit"],
    ),
    Case(
        "do_placement",
        "do_placement",
        "@on(sit(), priority=SURVIVAL, cooldown_s=5)\ndef h():\n    stand()\n\n\nsit()\n",
        ["h: an event condition cannot run a block"],
        farm=False,
    ),
    Case(
        "loop_control",
        "loop_control",
        irflow({"kind": "break"}),
        ["main.0: break outside a loop"],
        farm=False,
    ),
    # --- layer 2 -------------------------------------------------------------------------------
    Case(
        "map_sheet",
        "map_sheet",
        FARM,
        ["farm: no map sheet for map_3 on lab-rathena (L3): unsupported here"],
        world=World(
            server="lab-rathena",
            sheets={k: v for k, v in farm_sheets().items() if k != "map_3"},
            mobs=farm_world().mobs,
            items=ITEMS,
        ),
    ),
    Case(
        "refs",
        "refs",
        "use_item(item(7777))\nattack_nearest(mob(7778))\n",
        [
            "main.0: item 7777 is not in lab-rathena's item data",
            "main.1: mob 7778 is not in lab-rathena's monster data",
        ],
        farm=False,
    ),
    Case(
        "bindings",
        "bindings",
        WALK,
        [
            "main.0: walk_to is unsupported here: L3 binding "
            "L3.map.walkability (no L3 bindings for lab-rathena)",
            # the always-on safety events the flow does not write run too (#15): their bindings
            "dead.0: respawn is unsupported here: L2 binding L2.window.death_dialog (not bound "
            "for kro-20211103-prere/lab-rathena (params {}))",
            "hp_critical.0: escape is unsupported here: L3 binding L3.map.flags (no L3 bindings "
            "for lab-rathena)",
        ],
        resolver=default_resolver(ir.Target(**TARGET), Path("/nonexistent-l3")),
        farm=False,
    ),
    Case(
        "npc_block",
        "npc_menu",
        FARM,
        ["town.1: npc n_k1 is not on map_1", "town.2: npc n_k1 is not on map_1"],
        world=world(map_1=map_("map_1", npcs=[])),
    ),
    Case(
        "npc_plain",
        "npc_menu",
        WALK + 'talk_npc(npc("n_3f2a"))\n',
        ["main.1: npc n_3f2a is not on the map the flow is on at this point"],
        farm=False,
    ),
    Case(
        "option_exit",
        "npc_menu",
        farm(('[option("o_5d0e")]', '[option("o_x")]')),
        ["relay.0: option o_x is not in npc n_2b71's menu"],
    ),
    Case(
        "option_plain",
        "npc_menu",
        WALK + 'talk_npc(npc("n_aa"))\nchoose_menu(option("o_9"))\n',
        ["main.2: option o_9 is not in npc n_aa's menu"],
        farm=False,
    ),
    Case(
        "kafra",
        "kafra_service",
        FARM,
        ["town.1: npc n_k1 offers no save service"],
        world=world(
            map_1=map_(
                "map_1", npcs=[Npc(key="n_k1", x=146, y=90, kafra=Kafra(services=["storage"]))]
            )
        ),
    ),
    Case(
        "not_kafra",
        "kafra_service",
        WALK + 'kafra_store(npc("n_aa"), items=[item(9001)])\n',
        ["main.1: npc n_aa is not a Kafra"],
        farm=False,
    ),
    Case(
        "preconditions",
        "preconditions",
        WALK + 'kafra_store(npc("n_k2"), items=[item(9001)])\n',
        [
            "main.1: kafra_store needs skill_level(skill(1)) >= 6 (storage.deposit: Basic Skill "
            "level 6): add it to the flow's assumes"
        ],
        farm=False,
    ),
    Case(
        "npc_warp_target",
        "exit_destinations",
        FARM,
        ["relay.0: option o_5d0e of npc n_2b71 warps to map_4, not to farm's map_3"],
        world=world(
            map_2=map_(
                "map_2",
                npcs=[
                    Npc(
                        key="n_2b71",
                        x=40,
                        y=302,
                        menu=["o_5d0e"],
                        warps=[NpcWarp(options=["o_5d0e"], to_map="map_4", to_x=1, to_y=1)],
                    )
                ],
            )
        ),
    ),
    Case(
        "npc_warp_unknown",
        "exit_destinations",
        FARM,
        [
            "relay.0: the warp after option o_5d0e of npc n_2b71 is not known: the destination is "
            "the author's, checked on arrival"
        ],
        world=world(map_2=map_("map_2", npcs=[Npc(key="n_2b71", x=40, y=302, menu=["o_5d0e"])])),
    ),
    Case(
        "not_a_warp",
        "exit_destinations",
        farm(('cell("map_1", 150, 20)', 'cell("map_1", 151, 20)')),
        ["town.3: (151, 20) is not a warp on map_1"],
    ),
    Case(
        "warp_elsewhere",
        "exit_destinations",
        FARM,
        ["town.3: the warp at (150, 20) leads to map_9, not to relay's map_2"],
        world=world(map_1=map_("map_1", warps=[Warp(x=150, y=20, to_map="map_9", to_x=1, to_y=1)])),
    ),
    Case(
        "arrival",
        "exit_destinations",
        FARM,
        [
            "town.3: the warp at (150, 20) arrives at (40, 290) on map_2, outside relay's entry "
            "south "
            "((40, 300), radius 2)"
        ],
        world=world(
            map_1=map_("map_1", warps=[Warp(x=150, y=20, to_map="map_2", to_x=40, to_y=290)])
        ),
    ),
    Case(
        "noreturn",
        "exit_destinations",
        FARM,
        ["farm.1: map_3 refuses a Butterfly Wing (noreturn)"],
        world=world(map_3=map_("map_3", flags=MapFlags(noreturn=True))),
    ),
    Case(
        "not_a_wing",
        "exit_destinations",
        farm(("item_warp(WING", "item_warp(POTION")),
        ["farm.1: item 9001 is not a Butterfly Wing: an item_warp needs one"],
    ),
    Case(
        "save_cell",
        "exit_destinations",
        FARM,
        [
            "farm.1: a Butterfly Wing arrives at (150, 150) on map_1, outside town's entry A "
            "((150, 180), radius 2)"
        ],
        world=world(
            map_1=map_(
                "map_1",
                npcs=[
                    Npc(
                        key="n_k1",
                        x=146,
                        y=90,
                        kafra=Kafra(services=["save", "storage"], save_cell=(150, 150)),
                    )
                ],
            )
        ),
    ),
    Case(
        "target_spawn",
        "species_lists",
        farm(("mob(9103)]", "mob(9103), mob(9107)]")),
        ["farm: mob 9107 is in no spawn line of map_3"],
        world=with_mobs(m9107={"level": 3}),
    ),
    Case(
        "both_lists",
        "species_lists",
        farm(("mob(9103)]", "mob(9103), mob(9105)]")),
        ["farm: mob 9105 is on both the TARGET and the IGNORE list"],
    ),
    Case(
        "aggressive_ignore",
        "species_lists",
        FARM,
        [
            "farm: mob 9105 is aggressive and ignored: it attacks, the bot never answers, the HP "
            "events decide"
        ],
        world=with_mobs(m9105={"aggressive": True}),
    ),
    Case(
        "look_alike",
        "species_lists",
        FARM,
        [
            "farm: mob 9101 (TARGET) and mob 9105 (IGNORE) look alike: their confusion is not "
            "measured"
        ],
        world=with_mobs(m9101={"look_alike": [9105]}),
    ),
    Case(
        "resume_here",
        "graph",
        farm(
            ('to=entry("town", "A")))', 'to=entry("town_back", "A")))'),
            (
                "# GLOBAL events",
                '@map_block(map_id("map_1"), entries=[entry_at("A", cell("map_1", 150, '
                '180))])\ndef town_back():\n    take_exit(walk_exit(cell("map_1", 150, '
                '20), to=entry("relay", "south")))\n\n\n# GLOBAL events',
            ),
        ),
        ["map_1 holds town and town_back: mark one resume_here"],
    ),
    Case(
        "unreachable_block",
        "graph",
        farm(
            (
                "# GLOBAL events",
                '@map_block(map_id("map_2"), entries=[entry_anywhere("x")], '
                "resume_here=False)\ndef orphan():"
                '\n    stop("done")\n\n\n# GLOBAL events',
            )
        ),
        ["orphan: no exit reaches it from the start block town"],
    ),
    Case(
        "no_block",
        "graph",
        farm(('to=entry("farm", "arrival")', 'to=entry("farm2", "arrival")')),
        [
            "farm: no exit reaches it from the start block town",
            "relay.0: there is no map block farm2",
        ],
    ),
    Case(
        "no_entry",
        "graph",
        farm(('to=entry("farm", "arrival")', 'to=entry("farm", "north")')),
        ["relay.0: farm has no entry north"],
    ),
    Case(
        "path_end",
        "graph",
        farm(('    take_exit(item_warp(WING, to=entry("town", "A")))\n', "")),
        ["farm: a path of its main flow ends without take_exit or stop"],
    ),
    Case(
        "start",
        "graph",
        farm(('start=entry("town", "A")', 'start=entry("nowhere", "A")')),
        ["the start block nowhere does not exist"],
    ),
    Case(
        "entry_map",
        "graph",
        farm(('entry_at("A", cell("map_1", 150, 180))', 'entry_at("A", cell("map_2", 150, 180))')),
        ["town: entry A is on map_2, not on map_1"],
    ),
    Case(
        "death_no_block",
        "graph",
        farm(('set_save_point(npc("n_k1"))', 'assert_save_point(cell("map_9", 5, 5))')),
        [
            "a death returns to the save point on map_9, where no block is: a death then stops the "
            "run"
        ],
    ),
    Case(
        "cell_map",
        "cell_map",
        WALK + 'walk_to(cell("field_2", 5, 5))\n',
        ["main.1: cell (5, 5) is on field_2, not on field_1, where the flow is at this point"],
        farm=False,
    ),
    # --- layer 3: simulation ---------------------------------------------------------------------
    Case(
        "unreachable",
        "routes",
        WALK + 'take_warp(map_id("field_2"))\nwalk_to(cell("field_2", 170, 210))\n',
        ["main.2: cell (170, 210) is unreachable from the warp you arrive by"],
        farm=False,
    ),
    Case(
        "crosses_warp",
        "routes",
        FARM,
        [
            "town.3: the route from npc n_k1 (146, 90) to (150, 20) crosses the warp at (156, 22): "
            "it would leave map_1"
        ],
        world=world(
            map_1=map_(
                "map_1",
                warps=[
                    Warp(x=150, y=20, to_map="map_2", to_x=40, to_y=300),
                    Warp(x=156, y=22, span_x=10, to_map="map_7", to_x=1, to_y=1),
                ],
            )
        ),
    ),
    Case(
        "no_walk",
        "routes",
        FARM,
        ["town: routes on map_1 are not checked: its sheet has no walkability"],
        world=world(map_1=map_("map_1", walk=None)),
    ),
    Case(
        "entry_wall",
        "routes",
        FARM,
        ["town: entry A (150, 180) is not walkable on map_1"],
        world=world(map_1=map_("map_1", walk=grid(200, 200, ((150, 180, 150, 180),)))),
    ),
    Case(
        "attack_ignored",
        "attacks",
        farm(("attack_nearest(within=12)", "attack_nearest(mob(9105), within=12)")),
        ["farm.0.body.0: mob 9105 is on farm's IGNORE list"],
    ),
    Case(
        "attack_spawn",
        "attacks",
        farm(("attack_nearest(within=12)", "attack_nearest(mob(9107), within=12)")),
        ["farm.0.body.0: mob 9107 is in no spawn line of map_3"],
        world=with_mobs(m9107={"level": 3}),
    ),
    Case(
        "attack_no_target",
        "attacks",
        farm(("    targets=[mob(9101), mob(9102), mob(9103)],\n", "")),
        ["farm.0.body.0: attack_nearest has no target: give it a mob or the block a TARGET list"],
    ),
    Case(
        "save_point",
        "save_point",
        farm(('set_save_point(npc("n_k1"))', "sit()")),
        [
            "boss_seen: a Butterfly Wing on farm returns to the save point, and nothing sets it "
            "before "
            "farm.0. Add 'set save point' first?",
            "farm.1: a Butterfly Wing returns to the save point, not to town, and nothing sets it "
            "on "
            "map_1. Add 'set save point' at town's Kafra?",
            "farm_engagement: a Butterfly Wing on farm returns to the save point, and nothing sets "
            "it "
            "before farm.0. Add 'set save point' first?",
            "weight: a Butterfly Wing on farm returns to the save point, and nothing sets it "
            "before "
            "farm.0. Add 'set save point' first?",
            "weight: a Butterfly Wing on relay returns to the save point, and nothing sets it "
            "before "
            "relay.0. Add 'set save point' first?",
        ],
    ),
    Case(
        "save_point_elsewhere",
        "save_point",
        farm(
            ('set_save_point(npc("n_k1"))', "sit()"),
            ("def relay():\n", 'def relay():\n    set_save_point(npc("n_k2"))\n'),
        ),
        [
            "farm.1: a Butterfly Wing returns to the save point on map_2, not to town on map_1",
            "weight: a Butterfly Wing on relay returns to the save point, and nothing sets it "
            "before "
            "relay.0. Add 'set save point' first?",
        ],
        world=world(
            map_2=map_(
                "map_2",
                npcs=[
                    *farm_sheets()["map_2"].npcs,
                    Npc(
                        key="n_k2", x=45, y=300, kafra=Kafra(services=["save"], save_cell=(40, 300))
                    ),
                ],
            )
        ),
    ),
    Case(
        "assert",
        "save_point",
        farm(('set_save_point(npc("n_k1"))', 'assert_save_point(cell("map_1", 150, 180))')),
        ["town.1: the save point is asserted, not set: the assertion stays visible at approval"],
    ),
    Case(
        "respawn_unknown",
        "save_point",
        "@on(is_dead(), priority=CRITICAL, max_per_run=1, then=STOP)\ndef dead():\n    respawn()"
        "\n\n\nsit()\n",
        [
            "dead: a death at main.0 respawns at the save point, which nothing sets before it: set "
            "it "
            "first, or assert it"
        ],
        farm=False,
    ),
    Case(
        "wing_plain",
        "save_point",
        "use_item(item(9002))\n",
        [
            "main.0: a Butterfly Wing returns to the save point, and nothing sets it before "
            "main.0. "
            "Add 'set save point' first?",
            # the always-on dead (#15) respawns there too, in every flow
            "dead: a death at main.0 respawns at the save point, which nothing sets before it: "
            "set it first, or assert it",
        ],
        farm=False,
    ),
    Case(
        "weight_stall",
        "weight",
        farm(("weight_percent() < 50:", "weight_percent() < 95:")),
        [
            "farm.0: weight_percent() < 95 can change only by picking up items, and nothing in "
            "farm "
            "picks any up",
            "farm.0: weight_percent() < 95 guards an attack loop, and attacks stop at 90 %: the "
            "loop "
            "stalls before it ends",
        ],
    ),
    Case(
        "weight_loot",
        "weight",
        farm(
            (
                "        attack_nearest(within=12)\n",
                "        attack_nearest(within=12)\n        loot()\n",
            )
        ),
        [
            "farm.0: weight_percent() < 50 can change only by picking up items, and loot is "
            "unsupported here"
        ],
        resolver=raises_for("loot"),
    ),
    Case(
        "keep",
        "keep_lists",
        farm(("all_except=[WING, POTION]", "all_except=[POTION]")),
        [
            "town.2: storing everything also stores the Butterfly Wings that farm's exit, weight, "
            "boss_seen and farm_engagement use: add them to the keep list"
        ],
    ),
    Case(
        "escape_unknown",
        "escape",
        FARM,
        ["farm: hp_critical's escape on map_3 is unknown: its map flags are not extracted"],
        world=world(map_3=map_("map_3", flags=None)),
    ),
    Case(
        "escape_none",
        "escape",
        FARM,
        ["farm: hp_critical has no escape on map_3 (noteleport, noreturn): it stops the run there"],
        world=world(map_3=map_("map_3", flags=MapFlags(noteleport=True, noreturn=True))),
    ),
    Case(
        "irreversible",
        "irreversible",
        WALK + 'refine(npc("n_aa"), item(9001))\ninsert_card(item(9001), item(9002))\n'
        'sell(npc("n_aa"), keep=[])\n',
        [
            "main.1: refine can destroy the item: acknowledge it at approval",
            "main.2: insert_card is permanent: acknowledge it at approval",
            "main.3: sell with an empty keep list sells everything: acknowledge it at approval",
        ],
        farm=False,
    ),
    # --- layer 3: loops --------------------------------------------------------------------------
    Case(
        "loop_never_ends",
        "loop_ends",
        "sit()\n" * 6 + "while job_level() < 40:\n    sit()\n",
        ["main.6: this loop can never end: nothing in it changes job_level()"],
        farm=False,
    ),
    Case(
        "loop_true",
        "loop_ends",
        "while True:\n    sit()\n",
        ["main.0: this loop can never end: add a bound, a break or a stop"],
        farm=False,
    ),
    Case(
        "busy",
        "busy_loop",
        "while hp_percent() < 100:\n    pass\n",
        ["main.0: this loop has no action and no wait: a busy loop"],
        farm=False,
    ),
    Case(
        "cycle",
        "cycles",
        farm(("    run_until_stopped=True,\n", "")),
        [
            "the cycle town → relay → farm → town never ends: add a stop condition or mark the "
            "workflow run until stopped"
        ],
    ),
    # --- layer 3: events -------------------------------------------------------------------------
    Case(
        "rearm",
        "rearm",
        "@on(hp_percent() < 30, priority=SURVIVAL)\ndef drink():\n"
        "    use_item(item(9001))\n\n\nsit()\n",
        ["drink: no re-arm and no cooldown: it would fire on every tick"],
        farm=False,
    ),
    Case(
        "passive",
        "passive_only",
        "@on(item_count(item(9001)) < 3, priority=UPKEEP, cooldown_s=60)"
        "\ndef restock():\n    sit()\n\n\nsit()\n",
        ["restock: item_count() is an active sensor: never in an event condition"],
        farm=False,
    ),
    # ties (13.6.9, Batt 2026-10-09 #14): a tie needs the same class AND the same rank (#13)
    Case(  # same class, same rank (5), the same sensor overlapping: ERROR (13.6.2 step 4)
        "tie_same_sensor",
        "ties",
        farm(
            (
                "# MAP events",
                "@on(hp_percent() < 30, until=hp_percent() "
                "> 90, priority=SURVIVAL, rank=5, scope=farm)\ndef hp_panic():\n"
                "    use_item(POTION)\n\n\n# MAP events",
            )
        ),
        [
            "farm: hp_low and hp_panic are both survival at rank 5 on hp_percent() < 30",
            "farm: unintended_engagement and hp_panic are both survival: unintended_engagement "
            "runs first when both are due (rank 4 before 5)",
            "farm: hp_panic and boss_seen are both survival: hp_panic runs first when both are "
            "due (rank 5 before 50)",
        ],
    ),
    Case(  # the same overlap at DIFFERENT ranks: ordered, an INFO; two user events left at the
        # default rank (50) on different sensors: a WARNING, they queue first in, first out
        "tie_ranked",
        "ties",
        farm(
            (
                "# MAP events",
                "@on(hp_percent() < 30, until=hp_percent() "
                "> 90, priority=SURVIVAL, scope=farm)\ndef hp_panic():\n"
                "    use_item(POTION)\n\n\n# MAP events",
            )
        ),
        [
            "farm: hp_low and hp_panic are both survival on hp_percent() < 30: hp_low runs first "
            "when both are due (rank 5 before 50)",
            "farm: unintended_engagement and hp_panic are both survival: unintended_engagement "
            "runs first when both are due (rank 4 before 50)",
            "farm: hp_panic and boss_seen are both survival at rank 50 on different sensors: they "
            "queue first in, first out",
        ],
    ),
    Case(
        "retrigger",
        "retrigger",
        "@on(hp_percent() < 50, priority=SURVIVAL, cooldown_s=5)\n"
        "def fight():\n    attack_nearest(mob(9101))\n\n\nsit()\n",
        ["fight: attack_nearest lowers hp_percent(), which can re-trigger fight"],
        farm=False,
    ),
    Case(
        "failure_path",
        "failure_path",
        "@on(hp_percent() < 30, until=hp_percent() > 60, priority=SURVIVAL)\ndef drink():\n"
        "    use_item(item(9001), on_fail=CONTINUE)\n\n\nsit()\n",
        [
            "drink: use_item continues on failure and nothing reads its outcome: a failure goes "
            "unnoticed"
        ],
        farm=False,
    ),
    Case(
        "critical_long",
        "critical_long",
        farm(("    respawn()\n", '    respawn()\n    walk_to(cell("map_1", 1, 1))\n')),
        ["dead: walk_to is a long action inside a critical event"],
    ),
    Case(
        "inverted",
        "hysteresis",
        farm(("until=hp_percent() > 80", "until=hp_percent() > 40")),
        [
            "hp_low: until hp_percent() > 40 overlaps when hp_percent() < 50: the stop threshold "
            "must "
            "exceed 50"
        ],
    ),
    Case(
        "never_holds",
        "hysteresis",
        farm(("until=hp_percent() > 80", "until=hp_percent() > 100")),
        ["hp_low: until hp_percent() > 100 can never hold: hp_percent() reads 0..100"],
    ),
    Case(
        "narrow",
        "hysteresis",
        farm(("until=hp_percent() > 80", "until=hp_percent() > 50")),
        [
            "hp_low: the band between when hp_percent() < 50 and until hp_percent() > 50 is "
            "narrower "
            "than the readout's resolution (1)"
        ],
    ),
    Case(
        "same_direction",
        "same_direction",
        farm(("rearm=weight_percent() < 50", "until=weight_percent() > 95")),
        [
            "weight: until weight_percent() > 95 does not end weight_percent() >= 90: the stop "
            "must "
            "lie below 90"
        ],
    ),
    Case(
        "disable_dead",
        "safety_critical",
        farm(("disable(hp_low, scope=town)", "disable(dead, scope=town)")),
        ["town: dead is safety-critical: it can be extended, never disabled"],
    ),
    Case(
        "override_dead",
        "safety_critical",
        farm(
            (
                "# MAP events",
                "@on(is_dead(), priority=CRITICAL, "
                "max_per_run=1, then=RELOCATE, overrides=dead, "
                "scope=farm)\ndef farm_dead():\n    respawn()\n\n\n"
                "# MAP events",
            )
        ),
        ["farm: dead is safety-critical: it can be extended, never overridden"],
    ),
    Case(  # #15: no longer an error -- the compiler adds the built-in (test_always_on.py)
        "missing_is_built_in",
        "safety_critical",
        farm(
            (
                "@on(hp_percent() < 20, rearm=hp_percent() > 50, "
                "priority=CRITICAL, then=RELOCATE, max_per_min=2)\ndef "
                "hp_critical():\n    escape()  # fixed body: Fly Wing "
                "where allowed, else Butterfly Wing, else stop (13.6.8)"
                "\n",
                "",
            )
        ),
        [],
    ),
    Case(  # #15: stricter is allowed -- fires earlier, stops the run instead of relocating
        "stricter",
        "safety_critical",
        farm(
            ("@on(hp_percent() < 20, rearm", "@on(hp_percent() < 30, rearm"),
            ("max_per_run=1, then=RELOCATE)", "max_per_run=1, then=STOP)"),
        ),
        [],
    ),
    Case(
        "weakened_limit",
        "safety_critical",
        farm(
            (
                "is_dead(), priority=CRITICAL, max_per_run=1",
                "is_dead(), priority=CRITICAL, max_per_run=3",
            )
        ),
        [
            "dead: dead is safety-critical: max_per_run 3 loosens the built-in 1: it may only be "
            "tightened"
        ],
    ),
    Case(
        "weakened_trigger",
        "safety_critical",
        farm(("@on(hp_percent() < 20, rearm", "@on(hp_percent() < 10, rearm")),
        [
            "hp_critical: hp_critical is safety-critical: when hp_percent() < 10 fires later than "
            "the built-in hp_percent() < 20"
        ],
    ),
    Case(
        "weakened_then_rearm_body",
        "safety_critical",
        farm(
            (
                "@on(map_load_seen(), priority=CRITICAL, then=RELOCATE)",
                "@on(map_load_seen(), rearm=hp_percent() > 10, priority=CRITICAL, then=RESUME)",
            ),
            ("def unexpected_map():\n    read_position()", "def unexpected_map():\n    sit()"),
        ),  # fmt: skip
        [
            "unexpected_map: unexpected_map is safety-critical: then is relocate or stop, not "
            "resume",
            "unexpected_map: unexpected_map is safety-critical: its re-arm is the built-in's "
            "(none: it re-arms when its trigger clears)",
            "unexpected_map: unexpected_map's body starts with the built-in read_position(): "
            "steps may only follow it",
        ],
    ),
    Case(
        "loosen",
        "safety_critical",
        farm(
            (
                "# MAP events",
                "@extend(dead, scope=farm, max_per_run=3)"
                "\ndef farm_dead():\n    close_dialog()\n\n\n# MAP events",
            )
        ),
        ["farm: extend dead: max_per_run 3 loosens the global 1: an extension may only tighten"],
    ),
    Case(
        "class",
        "safety_critical",
        farm(("@on(is_dead(), priority=CRITICAL", "@on(is_dead(), priority=SURVIVAL")),
        ["dead: dead is safety-critical: its class is critical, not survival"],
    ),
    Case(
        "fixed_body",
        "safety_critical",
        farm(("    escape()  # fixed body", "    sit()  # fixed body")),
        ["hp_critical: hp_critical's body is fixed: escape()"],
    ),
    Case(
        "scope_extend",
        "scope",
        farm(("@extend(unexpected_map, scope=relay)", "@extend(weight_low, scope=relay)")),
        ["relay: extend weight_low: there is no global event weight_low"],
    ),
    Case(
        "scope_add",
        "scope",
        farm_ir(_add_hp_low),
        ["relay: add hp_low: hp_low is a global event: override it instead"],
    ),
    Case(
        "scope_twice",
        "scope",
        farm(
            (
                "disable(weight, scope=town)",
                "disable(weight, scope=town)\ndisable(hp_low, scope=farm)",
            )
        ),
        ["farm: two map events on hp_low: at most one per key"],
    ),
    Case(
        "class_change",
        "class_change",
        farm(
            (
                "    priority=SURVIVAL,\n    mode=INSERT,\n    "
                "max_per_min=6,\n    overrides=hp_low,",
                "    priority=UPKEEP,\n    mode=INSERT,\n    max_per_min=6,\n    overrides=hp_low,",
            )
        ),
        ["farm: hp_low moved from survival to upkeep: weight no longer waits for it"],
    ),
    Case(
        "looser",
        "looser_harder",
        farm(("    hp_percent() < 70,", "    hp_percent() < 30,")),
        [
            "farm: hp_low < 30 is looser than the global < 50, and map_3 spawns an aggressive "
            "species "
            "(mob 9105)"
        ],
        world=with_mobs(m9105={"aggressive": True}),
    ),
    Case(
        "looser_skipped",
        "looser_harder",
        farm(("    hp_percent() < 70,", "    hp_percent() < 30,")),
        [
            "farm: hp_low is looser than the global; whether map_3 is harder was judged without "
            "the "
            "level criterion: the character's base level is not in assumes"
        ],
        world=with_mobs(m9109={"aggressive": False, "boss": False}).model_copy(
            update={
                "sheets": {
                    **farm_sheets(),
                    "map_3": map_(
                        "map_3", spawns=[s for s in farm_sheets()["map_3"].spawns if s.mob != 9109]
                    ),
                }
            }
        ),
    ),
    Case(
        "insert_body",
        "insert_body",
        farm(
            (
                "def hp_low():\n    use_item(POTION)",
                'def hp_low():\n    walk_to(cell("map_1", 1, 1))',
            )
        ),
        ["hp_low: walk_to cannot be inserted: make the event pre-empt"],
    ),
    Case(
        "relocating",
        "relocating",
        farm(
            (
                "    priority=SURVIVAL,\n    then=RELOCATE,\n    scope=farm,\n)\ndef boss_seen",
                "    priority=SURVIVAL,\n    scope=farm,\n)\ndef boss_seen",
            )
        ),
        ["boss_seen: a Butterfly Wing changes the map: then must be relocate or stop"],
    ),
    Case(
        "engagement",
        "engagement_policy",
        farm(("(mob(9101), mob(9102))", "(mob(9101), mob(9102), mob(9103))")),
        ["farm: finish_target for mob 9103: it chases (L3 mob data)"],
        world=with_mobs(m9103={"chases": True}),
    ),
    Case(
        "event_species",
        "event_species",
        FARM,
        ["boss_seen: mob 9109 is in no spawn line of map_3"],
        world=world(
            map_3=map_("map_3", spawns=[s for s in farm_sheets()["map_3"].spawns if s.mob != 9109])
        ),
    ),
]


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_one_fixture_per_rule_with_its_exact_message(case: Case) -> None:
    assert introduced(case) == sorted(case.expected)


def test_every_rule_has_a_fixture() -> None:
    from poring_flow.lint import events, loops, semantics, simulate, structure

    rules = set()
    for mod in (structure, semantics, simulate, loops, events):
        import re

        text = Path(mod.__file__).read_text()  # type: ignore[arg-type]
        rules |= set(re.findall(r'ctx\.add\(\s*"([a-z_]+)"', text))
        rules |= set(re.findall(r'MergeIssue\(\s*"([a-z_]+)"', text))
    effective = (Path(events.__file__).parent.parent / "effective.py").read_text()  # type: ignore[arg-type]
    import re

    rules |= set(re.findall(r'MergeIssue\(\s*"([a-z_]+)"', effective))
    rules |= {"safety_critical", "scope"}
    covered = {c.rule for c in CASES} | {"schema"}
    assert rules - covered == set()


def test_the_schema_layer_reports_pydantic_errors_by_path() -> None:
    with pytest.raises(ir.FlowError) as e:
        irflow(SIT | {"on_fail": "retry"})()
    assert e.value.messages == ["main.0: on_fail: Input should be 'stop' or 'continue'"]
