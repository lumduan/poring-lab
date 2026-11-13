"""FUNCTIONS that press hotbar keys (Batt 2026-11-13; ADR-0020 Amendment C): the press_key block,
an item warp by function (`Exit.proc`), the runner as the dungeon_hunt block, and the xmas_dun02
flow the browser's starter makes byte for byte (services/frontend/src/lib/flow/fixtures/
xmas_dun02_flow.json)."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from poring_env.protocol import Key
from poring_flow import editor, functions, ir, lint, pyview, trace
from poring_flow.lint import Finding
from poring_flow.runtime import Sim

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "services/frontend/src/lib/flow/fixtures"
FLOW = FIXTURES / "xmas_dun02_flow.json"
RULES = FIXTURES / "starter_world_rules.json"
ZONES = REPO / "config/map_zones/xmas_dun02.yaml"
sys.path.insert(0, str(REPO / "scripts"))


def fixture() -> ir.Flow:
    return ir.from_json(FLOW.read_text(encoding="utf-8"))


def data() -> dict[str, Any]:
    return json.loads(FLOW.read_text(encoding="utf-8"))


def press(key: str) -> dict[str, Any]:
    return {
        "kind": "action",
        "block": "press_key",
        "concept": "ui.press_hotkey",
        "params": {"key": {"kind": "lit", "value": key}},
        "timeout_s": 2,
    }


def hunt(d: dict[str, Any]) -> dict[str, Any]:
    """The fixture's dungeon_hunt action (xmas_dun02's main: assert, while, take_exit)."""
    return d["workflow"]["blocks"][0]["main"][1]["body"][0]


def findings(f: ir.Flow, **kw: Any) -> list[Finding]:
    return lint.lint(f, resolver=lint.default_resolver(f.target), **kw)


def errors(f: ir.Flow, **kw: Any) -> list[str]:
    return [x.message for x in findings(f, **kw) if x.severity == "error"]


def zones_provider() -> Any:
    try:
        import flow_zones  # scripts/: the runner's own zones loader
    except ImportError:  # pragma: no cover - the dev env has it
        return None
    return flow_zones.provider()


# --- the fixture --------------------------------------------------------------------------------
def test_the_fixture_is_canonical_and_says_what_batt_asked() -> None:
    text = FLOW.read_text(encoding="utf-8")
    f = ir.from_json(text)
    assert text == ir.to_json(f) + "\n"
    assert f.name == "xmas_dun02" and f.max_runtime_s == 7200 and f.where_budget == 12
    assert f.workflow is not None and f.workflow.start_block == "xmas_dun02"
    # every key a function: the Run helper's defaults (scripts/flow_run.py FLOWS)
    keys = {n: functions.key_of(body[0]) for n, body in f.procedures.items()}  # type: ignore[arg-type]
    assert keys == {"heal": "F1", "fly_wing": "F8", "butterfly_wing": "F9", "knife_on": "F4",
                    "knife_back": "F5"}  # fmt: skip
    xmas, geffen = f.workflow.blocks
    assert [type(s).__name__ for s in xmas.main] == ["ActionStmt", "While", "TakeExit"]
    exit_ = xmas.main[2].exit  # type: ignore[union-attr]
    assert (exit_.kind, exit_.proc, exit_.item, exit_.to_block, exit_.to_entry) == (
        "item_warp", "butterfly_wing", None, "geffen", "save")  # fmt: skip
    # the one adjustment to the brief: the map node names its zones file (lint/zones.py's
    # zones_unreferenced is an ERROR wherever the zones loader runs, as in the backend)
    assert xmas.zones is not None and xmas.zones.map == "xmas_dun02"
    assert xmas.zones.sha256 == hashlib.sha256(ZONES.read_bytes()).hexdigest()
    assert geffen.main == [ir.Stop(reason="home")]


def test_the_fixture_lints_without_an_error() -> None:
    f = fixture()
    found = findings(f)
    assert [x.message for x in found if x.severity == "error"] == []
    sp = [(x.severity, x.path) for x in found if x.rule == "save_point"]
    assert sp == [("warning", "xmas_dun02.0")]  # the assertion's own (visible at approval)
    zp = zones_provider()
    if zp is not None:  # the runner's zones loader, as the backend lints with it
        assert errors(f, zones_provider=zp) == []
        d = data()
        del d["workflow"]["blocks"][0]["zones"]
        assert [x for x in errors(ir.validate(d), zones_provider=zp) if "zones" in x]


def test_the_fixture_lints_on_the_local_static_data() -> None:
    """data/kb and data/gat are local only (GPL / client data, never committed): skipped without
    them (a worktree in /dev/shm has none)."""
    kb, gat = REPO / "data" / "kb", REPO / "data" / "gat"
    if not (kb / "bindings").is_dir():
        pytest.skip("no local KB (data/kb)")
    from poring_flow.kbsheet import load_local_world

    f = fixture()
    world, _ = load_local_world(
        f.target.server, editor.maps_of(f), kb, gat if gat.is_dir() else None
    )
    res = lint.default_resolver(f.target, l3_root=kb / "bindings")
    found = lint.lint(f, world=world, resolver=res, zones_provider=zones_provider())
    assert [x.message for x in found if x.severity == "error"] == []


def test_the_python_view_round_trips_with_functions_as_names() -> None:
    f = fixture()
    src = pyview.print_flow(f)
    assert pyview.parse(src) == f
    assert pyview.print_flow(pyview.parse(src)) == src
    for line in (
        'def butterfly_wing():\n    press_key("F9")',
        "dungeon_hunt(heal=heal, fly=fly_wing, knife_on=knife_on, knife_back=knife_back)",
        'take_exit(item_warp(using=butterfly_wing, to=entry("geffen", "save")))',
    ):
        assert line in src


def test_a_function_name_is_never_read_as_a_variable() -> None:
    src = pyview.print_flow(fixture())
    # a VARIABLE where a function goes is stored as a name, and the linter refuses it
    bad = src.replace("# --- Functions", "WING = item(602)\n\n\n# --- Functions").replace(
        "heal=heal", "heal=WING"
    )
    f = pyview.parse(bad)
    assert hunt(json.loads(ir.to_json(f)))["params"]["heal"] == {"kind": "lit", "value": "WING"}
    assert any("heal (the heal item's key): WING is a variable, not a function" in m
               for m in errors(f))  # fmt: skip
    # a function where an item goes says how to write it
    with pytest.raises(pyview.ParseError, match="butterfly_wing is a function: item_warp"):
        pyview.parse(src.replace("item_warp(using=butterfly_wing,", "item_warp(butterfly_wing,"))
    with pytest.raises(pyview.ParseError, match="an item or using=<function>, not both"):
        pyview.parse(src.replace("item_warp(using=", "item_warp(item(602), using="))


# --- press_key ----------------------------------------------------------------------------------
def test_press_key_takes_one_hotbar_key_only() -> None:
    assert functions.hotbar_keys() == tuple(f"F{i}" for i in range(1, 10))
    import flow_config  # scripts/: the keys the runner reads

    assert functions.hotbar_keys() == flow_config.KEYS
    d = data()
    d["procedures"]["fly_wing"] = [press("F10")]
    found = errors(ir.validate(d))
    assert "procedures.fly_wing.0: press_key's key takes one of (F1, F2, F3, F4, F5, F6, F7, F8, " \
           "F9), not 'F10'" in found  # fmt: skip
    a = ir.ActionStmt.model_validate(press("F8"))
    assert pyview.expr_src(ir.Do(action=a)) == 'press_key("F8")'


def test_a_press_sends_its_key_down_and_up_and_a_key_off_the_hotbar_fails() -> None:
    d = data()
    d["workflow"]["blocks"][0]["main"].insert(1, press("F4"))
    sim = Sim(ir.validate(d), world={"map": "xmas_dun02", "weight_percent": 60},
              save_point=("geffen", (119, 40)))  # fmt: skip
    assert sim.run() == "home"
    pressed = [
        [(e.code, e.action) for e in em.batch.events if isinstance(e, Key)] for em in sim.out
    ]
    assert [("F4", "down"), ("F4", "up")] in pressed
    d["workflow"]["blocks"][0]["main"][1] = press("F10")
    assert Sim(ir.validate(d), world={"weight_percent": 60}).run() == "press_key_failed"


# --- the item warp by function ------------------------------------------------------------------
def test_an_item_warp_takes_an_item_or_a_function_and_walks_and_npcs_take_neither() -> None:
    def exit_errors(**exit_: Any) -> list[str]:
        d = data()
        d["workflow"]["blocks"][0]["main"][2]["exit"] = {"to_block": "geffen", "to_entry": "save",
                                                         **exit_}  # fmt: skip
        with pytest.raises(ir.FlowError) as e:
            ir.validate(d)
        return e.value.messages

    item = {"kind": "item", "id": 602}
    assert exit_errors(kind="item_warp", item=item, proc="butterfly_wing") == [
        "maps.xmas_dun02.2: exit: item_warp takes an item or a function (proc), not both"
    ]
    assert exit_errors(kind="item_warp") == [
        "maps.xmas_dun02.2: exit: item_warp takes item or proc (a function) (missing ['item'], "
        "not allowed none)"
    ]
    warp = {"kind": "cell", "map": "xmas_dun02", "x": 10, "y": 10}
    assert exit_errors(kind="walk_exit", warp=warp, proc="butterfly_wing") == [
        "maps.xmas_dun02.2: exit: walk_exit takes warp (missing none, not allowed ['proc'])"
    ]


def test_proc_is_left_out_when_none_so_every_older_flow_keeps_its_json_and_hash() -> None:
    # starter / starter_world_rules changed ON PURPOSE the same evening (Batt 2026-11-13: "a wing is
    # a function"): their wing exit is item_warp(using=butterfly_wing), so they carry a proc now
    for name in ("farm_loop", "starter_one_map", "town_warp_farm", "visit_and_choose"):
        text = (FIXTURES / f"{name}.json").read_text(encoding="utf-8")
        f = ir.from_json(text)
        assert ir.to_json(f) + "\n" == text, name  # the same bytes, so the same hash
        assert ir.flow_hash(f) == hashlib.sha256(text.rstrip("\n").encode()).hexdigest()
        assert '"proc":' not in text.replace('"kind":"call","proc":', ""), name
    assert '"proc":"butterfly_wing"' in FLOW.read_text(encoding="utf-8")


def test_an_item_warp_function_must_exist_and_press_a_key() -> None:
    d = data()
    d["workflow"]["blocks"][0]["main"][2]["exit"]["proc"] = "no_such"
    assert "maps.xmas_dun02.2: item_warp's function: there is no function no_such" in errors(
        ir.validate(d)
    )
    d = data()
    d["procedures"]["butterfly_wing"] = [{"kind": "wait_until", "cond": {"kind": "lit",
                                          "value": False}, "timeout_s": 1}]  # fmt: skip
    assert (
        "maps.xmas_dun02.2: item_warp's function butterfly_wing presses no key: its body needs a "
        "press_key (the Butterfly Wing's hotbar key)"
    ) in errors(ir.validate(d))
    d = data()  # a press through a called function counts
    d["procedures"]["home"] = [press("F9")]
    d["procedures"]["butterfly_wing"] = [{"kind": "call", "proc": "home"}]
    assert errors(ir.validate(d)) == []


def test_an_item_warp_function_before_the_save_point_is_an_error_as_an_item_one() -> None:
    """14.4: a wing before the save point is known is an ERROR (Batt 2026-10-08), by function
    too."""
    d = data()
    d["workflow"]["blocks"][0]["main"].pop(0)  # no stated save point
    found = errors(ir.validate(d))
    assert [m for m in found if "save point" in m] == [
        "maps.xmas_dun02.1: the Butterfly Wing function butterfly_wing returns to the save point, "
        "not to geffen, and nothing sets it on geffen. Add 'set save point' at geffen's Kafra?"
    ]


# --- dungeon_hunt -------------------------------------------------------------------------------
def test_each_role_names_a_function_of_exactly_one_press() -> None:
    def role_errors(change: Any) -> list[str]:
        d = data()
        change(d)
        return [m for m in errors(ir.validate(d)) if "dungeon_hunt" in m]

    at = "maps.xmas_dun02.1.body.0"

    def two(d: dict[str, Any]) -> None:
        d["procedures"]["heal"] = [press("F1"), press("F2")]

    def call(d: dict[str, Any]) -> None:
        d["procedures"]["knife_on"] = [{"kind": "call", "proc": "heal"}]

    def missing(d: dict[str, Any]) -> None:
        hunt(d)["params"]["fly"] = {"kind": "lit", "value": "fly"}

    def a_number(d: dict[str, Any]) -> None:
        hunt(d)["params"]["knife_back"] = {"kind": "lit", "value": 5}

    assert role_errors(two) == [
        f"{at}: dungeon_hunt's heal (the heal item's key) names heal, whose body is not exactly "
        "one press_key: the runner presses one key for each role"
    ]
    # ➡️ the project model (section 6: "through calls with literal arguments"): a role function
    # that calls another resolves to ITS one press_key -- here heal's F1, so the clash shows
    assert role_errors(call) == [
        f"{at}: dungeon_hunt's heal and knife_on both press F1: each role needs its own key"
    ]

    def call_a_variable(d: dict[str, Any]) -> None:
        d["variables"]["K"] = {"kind": "lit", "value": "F4"}
        d["procedures"]["press_it"] = [press("F4")]
        d["procedures"]["press_it"][0]["params"]["key"] = {"kind": "var", "name": "k"}
        d["signatures"] = {"press_it": {"params": [{"name": "k", "default": None}]}}
        d["procedures"]["knife_on"] = [{"kind": "call", "proc": "press_it",
                                        "args": [{"kind": "var", "name": "K"}]}]  # fmt: skip

    assert role_errors(call_a_variable) == [
        f"{at}: dungeon_hunt's knife_on (the Knife's key) names knife_on, whose body is not "
        "exactly one press_key: the runner presses one key for each role"
    ]
    assert role_errors(missing) == [
        f"{at}: dungeon_hunt's fly (the Fly Wing's key): there is no function fly"
    ]
    assert f"{at}: dungeon_hunt's knife_back takes a function's name, not an int" in role_errors(
        a_number
    )


def test_each_role_has_its_own_key_and_none_is_the_wings() -> None:
    d = data()
    d["procedures"]["knife_back"] = [press("F4")]
    d["procedures"]["fly_wing"] = [press("F9")]
    assert [m for m in errors(ir.validate(d)) if "hotbar" in m or "key" in m] == [
        "maps.xmas_dun02.1.body.0: dungeon_hunt's fly (the Fly Wing's key) presses F9, the key "
        "butterfly_wing uses as the Butterfly Wing home: each role needs its own key",
        "maps.xmas_dun02.1.body.0: dungeon_hunt's knife_on and knife_back both press F4: each "
        "role needs its own key",
    ]


def test_dungeon_hunt_runs_only_on_a_map_with_a_runner() -> None:
    d = data()
    block = d["workflow"]["blocks"][0]
    block["map"]["map"] = "prt_fild08"
    del block["zones"]
    assert (
        "maps.xmas_dun02.1.body.0: dungeon_hunt runs the map's runner, and prt_fild08 has none "
        "(maps with a runner: xmas_dun02; scripts/flow_run.py)"
    ) in errors(ir.validate(d))
    d = data()  # in a function: not a map block's own step
    d["procedures"]["farm"] = [hunt(d)]
    assert (
        "procedures.farm.0: dungeon_hunt runs the map's runner: it belongs in a map block's steps "
        "(a map with a runner: xmas_dun02)"
    ) in errors(ir.validate(d))


def test_the_runner_maps_and_roles_are_flow_runs() -> None:
    """One place (functions.RUNNER_MAPS) the linter and the catalogue read: scripts/flow_run.py
    FLOWS' maps. The fixture's keys are that flow's defaults, role by role."""
    import flow_run

    assert {fl.map for fl in flow_run.FLOWS.values()} == functions.RUNNER_MAPS
    defaults = flow_run.FLOWS["xmas_dun02_rogue"].defaults
    f = fixture()
    action = next(
        a for s in ir.sites(f) for a in ir.actions_in(s.stmt) if a.block == "dungeon_hunt"
    )
    roles = functions.role_functions(action)
    for role, setting in functions.ROLES.items():
        name = roles[role]
        assert name is not None
        press_ = functions.single_press(f, name)
        assert press_ is not None and functions.key_of(press_) == defaults[setting], role
    assert functions.wing_keys(f) == {defaults["home_key"]: ["butterfly_wing"]}
    doc = editor.catalogue_doc()
    assert doc["runner_maps"] == ["xmas_dun02"]
    params = doc["blocks"]["dungeon_hunt"]["spec"]["params"]
    assert [(p["name"], p["type"], p["required"]) for p in params] == [
        ("heal", "proc", True), ("fly", "proc", True), ("knife_on", "proc", True),
        ("knife_back", "proc", True)]  # fmt: skip
    spec = doc["blocks"]["dungeon_hunt"]["spec"]
    assert spec["needs_targets"] is False and spec["adds_weight"] and spec["long"]


# --- the simulators -----------------------------------------------------------------------------
def test_the_simulator_hunts_then_presses_the_wing_and_arrives_home() -> None:
    world = {"map": "xmas_dun02", "cell": (100, 100), "weight_percent": 10}
    timeline: list[tuple[float, dict[str, Any]]] = [(2.0, {"weight_percent": 55})]
    sim = Sim(fixture(), world=world, timeline=timeline, save_point=("geffen", (119, 40)))
    assert sim.run() == "home"
    assert (sim.block, sim.world["map"], sim.world["cell"]) == ("geffen", "geffen", (119, 40))
    hunts = [em for em in sim.out if em.why == "dungeon_hunt"]
    assert hunts and all(em.owner == "xmas_dun02" for em in hunts)
    wing = [em for em in sim.out if em.why == "press_key"]
    assert [[(k.code, k.action) for k in em.batch.events] for em in wing] == [
        [("F9", "down"), ("F9", "up")]
    ]
    doc = trace.simulate(fixture(), None, trace.Scenario(encounters=True))
    assert doc["end"] == "home" and doc["final"]["block"] == "geffen"
    assert doc["transitions"][0]["kind"] == "item_warp" and doc["transitions"][0]["arrived"]
    # the press IS the exit: ONE item step (the press, its proc and key), then the exit
    steps = [(s["kind"], s.get("key"), s.get("proc")) for s in doc["play"]][-2:]
    assert steps == [("item", "F9", "butterfly_wing"), ("exit", None, None)]


def test_an_item_warp_by_function_is_one_item_step_then_the_exit_in_time_order() -> None:
    """The two-map starter (field's exit item_warp(using=butterfly_wing) -> town.spawn): the
    press is the exit's item step, never an act + arrive of its own, and the play list never goes
    back in time. runtime.Sim: the press inside the exit moves nothing; the exit arrives once."""
    flow = ir.from_json((FIXTURES / "starter.json").read_text(encoding="utf-8"))
    world = editor.sample_world(editor.maps_of(flow))
    doc = trace.simulate(flow, world, trace.Scenario(horizon_s=60, encounters=True, seed=3))
    play = doc["play"]
    assert all(a["t0"] <= b["t0"] for a, b in zip(play, play[1:], strict=False))
    assert not [s for s in play if s["kind"] == "arrive" and s.get("via") == "press_key"]
    assert not [s for s in play if s.get("action") == "press_key"]
    i = next(i for i, s in enumerate(play) if s["kind"] == "item")
    item, exit_ = play[i], play[i + 1]
    assert (item["proc"], item["key"], item["map"]) == ("butterfly_wing", "F9", "field_1")
    assert item["t1"] == exit_["t0"]
    assert item["t1"] > item["t0"]
    assert (exit_["kind"], exit_["arrived"], exit_["to_map"]) == ("exit", True, "town_1")
    sim = MapChanges(flow, world={"map": "field_1", "cell": (30, 30)},
                     save_point=("town_1", (40, 40)))  # fmt: skip
    sim.block = "field"
    sim.run()
    assert sim.changes[:1] == [("exit", "town_1")]  # once, by the exit; never by the press


class MapChanges(Sim):
    """runtime.Sim recording every map change with its cause."""

    def __init__(self, *args: Any, **kw: Any) -> None:
        super().__init__(*args, **kw)
        self.changes: list[tuple[str, str]] = []

    def _set(self, changes: dict[str, Any], cause: str) -> None:
        if "map" in changes and changes["map"] != self.world.get("map"):
            self.changes.append((cause, changes["map"]))
        super()._set(changes, cause)


def test_a_wing_press_outside_an_exit_keeps_its_own_map_change() -> None:
    """call butterfly_wing in an event (the world rule's body) still lands on the save point."""
    flow = ir.from_json((FIXTURES / "starter.json").read_text(encoding="utf-8"))
    sim = Sim(flow, world={"map": "field_1"}, save_point=("town_1", (40, 40)))
    gen = sim._stmts([ir.CallProc(proc="butterfly_wing")], "unexpected_map")
    for _ in gen:
        pass
    assert (sim.world["map"], sim.world["cell"]) == ("town_1", (40, 40))


# --- the world rule's body (14.3): call butterfly_wing lints like use_item(WING) -----------------
def _rules(by_function: bool, assert_first: bool = True, then: str = "relocate") -> ir.Flow:
    """starter_world_rules.json (rules.ts's output since 2026-11-13: the wing is a FUNCTION, the
    field's home exit `item_warp(using=butterfly_wing)`, the unknown-map rule's body
    `call butterfly_wing`), or, when not by_function, the same flow with the wing as the ITEM it
    was before (`WING = item(9002)`: the exit's item, the rule's `use_item(WING)`)."""
    d = json.loads(RULES.read_text(encoding="utf-8"))
    h = d["handlers"][0]
    assert h["name"] == "unexpected_map" and h["priority"] == "critical"
    h["then"] = then
    field = d["workflow"]["blocks"][1]
    exit_ = field["main"][-1]["exit"]
    assert exit_["kind"] == "item_warp" and exit_["proc"] == "butterfly_wing"
    assert h["body"][1]["then"] == [{"kind": "call", "proc": "butterfly_wing"}]
    if not by_function:
        d["variables"]["WING"] = {"kind": "lit", "value": {"kind": "item", "id": 9002}}
        d["procedures"].pop("butterfly_wing")
        exit_["proc"] = None
        exit_["item"] = {"kind": "var", "name": "WING"}
        h["body"][1]["then"] = [{"kind": "action", "block": "use_item", "concept": "item.use",
                                 "params": {"item": {"kind": "var", "name": "WING"}},
                                 "timeout_s": 10}]  # fmt: skip
    if not assert_first:
        d["workflow"]["blocks"][0]["main"].pop(0)
    return ir.validate(d)


def _sp(f: ir.Flow) -> list[tuple[str, str, str]]:
    doc = editor.lint_doc(f, world=editor.sample_world(), resolver=lint.default_resolver(f.target))
    return sorted((x["rule"], x["severity"], x["path"]) for x in doc["findings"]
                  if x["severity"] == "error" or x["rule"] == "save_point")  # fmt: skip


def test_call_butterfly_wing_in_the_world_rule_lints_like_use_item_wing() -> None:
    for assert_first in (True, False):
        by_item, by_function = _sp(_rules(False, assert_first)), _sp(_rules(True, assert_first))
        assert by_function == by_item, assert_first
    assert _sp(_rules(True)) == [("save_point", "warning", "town.0")]  # 0 errors, stated
    assert ("save_point", "error", "unexpected_map") in _sp(_rules(True, assert_first=False))
    # an event that RESUMES after the wing: the same relocating error as with use_item(WING)
    f, g = _rules(True, then="resume"), _rules(False, then="resume")
    assert ("relocating", "error", "unexpected_map") in _sp(f)
    assert [x for x in _sp(f) if x[0] == "relocating"] == [
        x for x in _sp(g) if x[0] == "relocating"
    ]
    pyf = pyview.print_flow(_rules(True))
    assert "        butterfly_wing()" in pyf and pyview.parse(pyf) == _rules(True)


def test_a_wing_call_in_a_main_is_a_map_change_and_another_key_in_a_resuming_event_warns() -> None:
    d = data()
    d["workflow"]["blocks"][0]["main"].insert(1, {"kind": "call", "proc": "butterfly_wing"})
    assert (
        "maps.xmas_dun02.1: the Butterfly Wing on F9 (butterfly_wing) changes the map: a map "
        "block leaves through take_exit"
    ) in errors(ir.validate(d))
    d = data()
    d["handlers"] = [{"name": "hp_low", "priority": "survival", "mode": "insert",
                      "when": {"kind": "cmp", "op": "<", "left": {"kind": "sense",
                               "sensor": "hp_percent"}, "right": {"kind": "lit", "value": 50}},
                      "until": {"kind": "cmp", "op": ">=", "left": {"kind": "sense",
                                "sensor": "hp_percent"}, "right": {"kind": "lit", "value": 80}},
                      "cooldown_s": 2, "body": [{"kind": "call", "proc": "heal"}]}]  # fmt: skip
    found = findings(ir.validate(d))
    assert [x.message for x in found if x.severity == "error"] == []  # an insertable hotbar press
    assert [x.message for x in found if x.rule == "relocating"] == [
        'handlers.hp_low: press_key("F1") uses whatever is on that hotbar slot: if it holds a '
        "Butterfly Wing, the map changes and then must be relocate or stop"
    ]
