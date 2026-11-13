"""The PROJECT model, format 3 (Batt 2026-11-13; docs/planning/project-model.md): the models and
their shape rules, canonical JSON and the hash, the compile to the engine's IR with Batt's
override rule (virtual dispatch), functions like Python in the simulator, the session blocks, the
fixtures both sides test, and Run's keys."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from poring_flow import editor, ir, lint
from poring_flow import project as P
from poring_flow.runtime import Sim
from poring_flow.trace import Scenario

sys.path.insert(0, str(Path(__file__).parent))
from project_kit import (  # noqa: E402
    REPO,
    SAMPLE,
    SAMPLE_TRACE,
    SESSION,
    XMAS,
    ZONES,
    act,
    add_tab,
    build,
    call,
    callv,
    fdef,
    hp,
    lit,
    node,
    press,
    sample,
    session,
    tab,
    var,
)

sys.path.insert(0, str(REPO / "scripts"))


def problems(d: dict[str, Any]) -> list[str]:
    with pytest.raises(P.ProjectError) as e:
        P.validate(copy.deepcopy(d))
    return e.value.messages


def findings(p: P.Project, **kw: Any) -> list[P.PFinding]:
    return P.project_lint(p, resolver=lint.default_resolver(p.target), **kw)[1]


def errors(p: P.Project, **kw: Any) -> list[str]:
    return [f.message for f in findings(p, **kw) if f.severity == "error"]


def zones_provider() -> Any:
    try:
        import flow_zones  # scripts/: the runner's own zones loader
    except ImportError:  # pragma: no cover - the dev env has it
        return None
    return flow_zones.provider()


# --- the fixtures (section 7) ---------------------------------------------------------------------
HUNT = 2  # the one box's hunt core: main.2 (stage 4a: use_model stands before it)


def test_the_xmas_dun02_fixture_is_one_box_and_says_what_batt_asked() -> None:
    """Batt 2026-11-13 ~21:4x: "START > map xmas_dun02, ONE box is enough; login and choosing the
    character come later; the user puts the character on xmas_dun02 themself"."""
    text = XMAS.read_text(encoding="utf-8")
    p = P.from_json(text)
    assert text == P.to_json(p) + "\n"
    assert (p.format, p.version, p.name, p.start, p.edges) == (
        "poring-lab.project", 3, "xmas_dun02", "xmas_dun02", [])  # fmt: skip
    (x,) = p.nodes
    assert isinstance(x, P.MapNode) and (x.id, x.map.map, (x.pos.x, x.pos.y)) == (
        "xmas_dun02", "xmas_dun02", (0, 0))  # fmt: skip
    assert x.zones is not None and x.zones.sha256 == hashlib.sha256(ZONES.read_bytes()).hexdigest()
    assert x.resume_here and (x.entries[0].name, x.entries[0].at, x.entries[0].radius) == (
        "here", None, 2)  # fmt: skip
    assert [t.name for t in x.tabs] == ["main", "keys", "survival", "knife", "exits", "monsters"]
    save, model, hunt, stop = x.main
    # stage 4a (live-blocks.md 3.4): the trained data before the hunt core
    assert isinstance(model, ir.ActionStmt) and model.block == "use_model"
    assert model.params["model"] == ir.Lit(value="xmas02") and model.concept == "core.use_model"
    assert isinstance(save, ir.ActionStmt) and save.block == "assert_save_point"
    assert save.note == "the world rule: the save point (where a Butterfly Wing and a death land)"
    assert save.params["cell"] == ir.Lit(value=ir.CellRef(map="geffen", x=119, y=40))
    assert isinstance(hunt, ir.ActionStmt) and hunt.block == "dungeon_hunt"
    assert {k: v.value for k, v in hunt.params.items()} == {  # type: ignore[union-attr]
        "heal": "heal", "fly": "fly_wing", "knife_on": "knife_on", "knife_back": "knife_back",
        "home": "fly_home", "respawn": "respawn_button",
        "respawn_confirm": "respawn_ok"}  # fmt: skip
    assert stop == ir.Stop(reason="home")
    keys = {d.name: d.body[0].params["key"].value for d in x.tabs[1].defs}  # type: ignore[union-attr]
    assert keys == {"heal": "F1", "fly_wing": "F8", "butterfly_wing": "F9", "wield_knife": "F4",
                    "wield_damascus": "F5"}  # fmt: skip
    # stage 3 (live-blocks.md 3.3): the Knife swap's two functions (each calls its key's function:
    # the strike between, the runner's own today), the way home, the respawn's two clicks
    assert [(d.name, d.body) for d in x.tabs[3].defs] == [
        ("knife_on", [ir.CallProc(proc="wield_knife")]),
        ("knife_back", [ir.CallProc(proc="wield_damascus")])]  # fmt: skip
    home, rsp, ok = x.tabs[4].defs
    assert (home.name, home.body) == ("fly_home", [ir.CallProc(proc="butterfly_wing")])
    pts = [
        (
            d.name,
            [
                (a.block, a.params["x"].value, a.params["y"].value)  # type: ignore[union-attr]
                for a in d.body
                if isinstance(a, ir.ActionStmt)
            ],
        )
        for d in (rsp, ok)
    ]
    assert pts == [
        ("respawn_button", [("click_at", 645, 481)]),
        ("respawn_ok", [("click_at", 714, 405)]),
    ]  # the runner's own defaults
    # stage 2 (Batt 2026-11-13: "Heal: press F1 when HP < 30 %. Fly Wing: press F8 when a boss is
    # seen or HP < 25 %"; live-blocks.md 3.2): two events, each calling its key's function; stage 3
    # adds the weight home (Batt: "if the weight is over 50 %, use a Butterfly Wing to go back")
    drink, fly, bag = x.tabs[2].defs
    assert (bag.name, bag.body) == ("bag_full", [ir.Stop(reason="home")])
    assert bag.on is not None and (bag.on.mode, bag.on.priority, bag.on.max_per_run) == (
        "preempt", "upkeep", 1)  # fmt: skip
    assert bag.on.when == ir.Cmp(op=">=", left=ir.Sense(sensor="weight_percent"),
                                 right=ir.Lit(value=50))  # fmt: skip
    assert (drink.name, drink.body, fly.name, fly.body) == (
        "drink", [ir.CallProc(proc="heal")],
        "fly_away", [ir.CallProc(proc="fly_wing")])  # fmt: skip
    assert drink.on is not None and fly.on is not None
    assert (drink.on.mode, drink.on.priority, drink.on.cooldown_s) == ("insert", "survival", 0.7)
    hp = ir.Sense(sensor="hp_percent")
    assert drink.on.when == ir.Cmp(op="<", left=hp, right=ir.Lit(value=30))
    assert drink.on.until == ir.Cmp(op=">=", left=hp, right=ir.Lit(value=31))
    assert (fly.on.mode, fly.on.priority, fly.on.cooldown_s, fly.on.until, fly.on.rearm) == (
        "preempt", "critical", 3.0, None, None)  # fmt: skip
    assert fly.on.when == ir.Logic(kind="or", terms=[
        ir.Sense(sensor="sees_boss"),
        ir.Cmp(op="<", left=ir.Sense(sensor="hp_percent"), right=ir.Lit(value=25))])  # fmt: skip
    assert P.session_path(p).map_start and P.start_map(p) is x
    assert "edges" in json.loads(text) and json.loads(text)["edges"] == []
    # stage 4a (Batt 2026-11-13: "break the core into functions, e.g. attack_myst_case,
    # attack_cookie"): one recipe per monster xmas02 strikes, each TODAY's technique
    t = ir.Var(name="t")
    want = [
        ir.CallProc(proc="knife_on"),
        *[
            ir.ActionStmt(block=b, concept=c, params={"target": t}, timeout_s=s)
            for b, c, s in (
                ("strike", "combat.attack_target", 60.0),
                ("wait_steal", "core.wait_steal", 10.0),
            )
        ],
        ir.CallProc(proc="knife_back"),
        *[
            ir.ActionStmt(block=b, concept=c, params={"target": t}, timeout_s=s)
            for b, c, s in (("wait_kill", "core.wait_kill", 120.0), ("loot", "loot.pick_up", 30.0))
        ],
    ]
    rec = x.tabs[5].defs
    assert [d.name for d in rec] == ["attack_mystcase", "attack_cruiser", "attack_cookie",
                                     "attack_cookie_xmas"]  # fmt: skip
    for d in rec:
        assert d.body == want and d.on is None, d.name
        assert [(q.name, q.default) for q in d.params] == [
            ("t", None),
            ("priority", ir.Lit(value=1)),
        ]


def test_the_xmas_dun02_fixture_lints_without_an_error() -> None:
    p = P.from_json(XMAS.read_text())
    assert errors(p) == []  # no static data
    zp = zones_provider()
    if zp is not None:
        assert errors(p, zones_provider=zp) == []
    sp = [(f.severity, f.where.path) for f in findings(p) if f.rule == "save_point"]
    assert sp == [("warning", "xmas_dun02/main/main.0")]  # the assertion's own, at approval
    assert [f for f in findings(p) if f.rule.startswith("session")] == []


def test_the_xmas_dun02_fixture_lints_on_the_local_static_data() -> None:
    kb, gat = REPO / "data" / "kb", REPO / "data" / "gat"
    if not (kb / "bindings").is_dir():
        pytest.skip("no local KB (data/kb)")
    from poring_flow.kbsheet import load_local_world

    for path in (XMAS, SESSION):
        p = P.from_json(path.read_text())
        c = P.compile_project(p)
        g = gat if gat.is_dir() else None
        world, _ = load_local_world(p.target.server, P.maps_of(c), kb, g)
        res = lint.default_resolver(p.target, l3_root=kb / "bindings")
        _, found = P.project_lint(p, world=world, resolver=res, zones_provider=zones_provider())
        assert [f.message for f in found if f.severity == "error"] == [], path.name


def test_the_session_fixture_is_canonical_and_lints_without_an_error() -> None:
    """The login-start project (the ready-made one before the one box): the model's tests' base."""
    text = SESSION.read_text(encoding="utf-8")
    p = P.from_json(text)
    assert text == P.to_json(p) + "\n" and p.start == "login"
    assert [(n.id, n.kind) for n in p.nodes] == [
        ("login", "login"), ("character", "character"), ("xmas_dun02", "map"),
        ("geffen", "map"), ("global", "global")]  # fmt: skip
    assert errors(p) == []
    data = json.loads(text)  # the absent fields stay out of the JSON: geffen's zones, an entry
    assert "zones" not in node(data, "geffen") and "entry" not in data["edges"][0]


def test_the_sample_fixture_lints_clean_on_the_sample_sheets_and_runs_until_stopped() -> None:
    text = SAMPLE.read_text(encoding="utf-8")
    p = P.from_json(text)
    assert text == P.to_json(p) + "\n"
    c = P.compile_project(p)
    assert c.run_until_stopped and c.flow is not None and c.flow.stop_when is None
    assert c.flow.workflow is not None and c.flow.workflow.run_until_stopped
    world = editor.sample_world(P.maps_of(c))
    assert errors(p, world=world) == []
    # without the explicit choice (stop_when false) the town <-> field cycle never ends
    d = sample()
    d["stop_when"] = None
    assert (
        "the cycle town → field → town never ends: add a stop condition or mark the workflow "
        "run until stopped" in [f.text for f in findings(build(d), world=world)]
    )


def test_the_maps_pages_trace_fixture_is_the_simulators_output() -> None:
    """lib/maps/fixtures/project_sample_trace.json: the sample project on the SYNTHETIC sheets,
    from the login. Regenerate it with this same call when the trace changes."""
    p = P.from_json(SAMPLE.read_text())
    world = editor.sample_world(P.maps_of(P.compile_project(p)))
    doc = P.simulate(p, world, Scenario(horizon_s=71, encounters=True, seed=3))
    assert json.loads(SAMPLE_TRACE.read_text()) == json.loads(json.dumps(doc))


def test_the_committed_schema_matches_the_models() -> None:
    assert (REPO / P.SCHEMA_PATH).read_text() == P.json_schema(), (
        f"regenerate: python -m poring_flow.project > {P.SCHEMA_PATH}"
    )


# --- the shape rules (section 2) -----------------------------------------------------------------
def test_canonical_json_keeps_a_call_s_arguments_and_the_hash_follows_the_text() -> None:
    p = P.from_json(SESSION.read_text())
    text = P.canonical_json(p)
    assert '"args":[],"kind":"call","kwargs":{},"proc":"heal"' in text
    assert P.project_hash(p) == hashlib.sha256(text.encode()).hexdigest()
    d = session()
    node(d, "login")["pos"]["x"] = 1
    assert P.project_hash(build(d)) != P.project_hash(p)


def test_an_ir_2_flow_and_another_version_are_refused_in_words() -> None:
    flow = json.loads((REPO / "services/frontend/src/lib/flow/fixtures/xmas_dun02_flow.json")
                      .read_text())  # fmt: skip
    assert problems(flow)[0].startswith("the flow format changed: a project (format 3)")
    assert problems({**session(), "version": 2}) == [
        "version 2 is not supported: this engine reads format 3"]  # fmt: skip
    with pytest.raises(P.ProjectError, match="at most 1048576"):
        P.from_json("x" * (1 << 20 + 1))


def test_main_tabs_and_tab_names() -> None:
    d = session()
    node(d, "geffen")["tabs"][0]["name"] = "home"
    assert "geffen/home: the first tab of geffen is its main tab (named main), not home" in (
        problems(d))  # fmt: skip
    d = session()
    node(d, "geffen")["tabs"][0]["main"] = None
    assert (
        "geffen/main: the main tab holds the node's program: main is a list (empty while "
        "drafting)" in problems(d)
    )
    d = add_tab(session(), "global", tab("main", main=[]))
    assert "global/main: Global has no main tab: its tabs hold functions, events and variables" in (
        problems(d))  # fmt: skip
    d = add_tab(session(), "geffen", tab("more", main=[]))
    assert "geffen/more: only the main tab holds a program: this tab's main is null" in problems(d)
    for bad in ("list", "global", "class"):
        d = add_tab(session(), "geffen", tab(bad))
        assert problems(d) == [
            f"geffen/{bad}: {bad} is a Python keyword or built-in name: a tab cannot take it"
        ]
    assert problems(add_tab(session(), "geffen", tab("built_in"))) == [
        "geffen/built_in: built_in is the engine's: its always-on safety events show under it"
    ]
    d = add_tab(session(), "geffen", tab("heal", fdef("heal", press("F2"))))
    assert "geffen/heal: heal is the name of a function (tab heal): a tab cannot take it" in (
        problems(d))  # fmt: skip
    d = session()
    node(d, "geffen")["tabs"] = []
    assert "geffen: geffen has no main tab: every node has one (Batt's iron rule)" in problems(d)
    d = session()
    node(d, "geffen")["tabs"][0]["name"] = "Main"
    assert problems(d) == [
        "geffen/Main: name: String should match pattern '^[a-z][a-z0-9_]{0,19}$'"
    ]


def test_one_namespace_per_node_names_both_tabs() -> None:
    d = add_tab(session(), "global", tab("more", fdef("heal", press("F2"))))
    assert problems(d) == [
        "global/more/heal: heal is defined twice on global: a function in tab keys and a "
        "function in tab more (a node's tabs are one namespace)"
    ]
    d = add_tab(session(), "global", tab("more", vars={"fly_wing": lit(1)}))
    assert problems(d) == [
        "global/more/fly_wing: fly_wing is defined twice on global: a function in tab keys and "
        "a variable in tab more (a node's tabs are one namespace)"
    ]


def test_inputs_events_returns_and_exits() -> None:
    d = add_tab(session(), "global", tab("lib", fdef("f", press("F2"), params=[
        {"name": "a", "default": lit(1)}, {"name": "b", "default": None}])))  # fmt: skip
    assert problems(d) == [
        "global/lib/f: parameter b has no default but comes after a, which has one: required "
        "parameters come first"
    ]
    on = {"when": {"kind": "sense", "sensor": "engagement_seen"}, "priority": "upkeep"}
    d = add_tab(session(), "global", tab("lib", fdef("stuck", press("F2"), params=["n"], on=on)))
    assert problems(d) == [
        "global/lib/stuck: stuck is an event (it has a trigger): an event takes no inputs, no "
        "*args and no **kwargs"
    ]
    d = session()
    node(d, "geffen")["tabs"][0]["main"].insert(0, {"kind": "return", "value": None})
    assert problems(d) == [
        "geffen/main/main.0: return belongs inside a function (a def), not in main"
    ]
    d = add_tab(
        session(),
        "global",
        tab(
            "lib",
            fdef(
                "home",
                {
                    "kind": "take_exit",
                    "exit": {
                        "kind": "item_warp",
                        "proc": "butterfly_wing",
                        "to_block": "geffen",
                        "to_entry": "save",
                    },
                },
            ),
        ),
    )
    assert problems(d) == [
        "global/lib/home.0: take_exit leaves a map: it belongs on a map node, not the global node"
    ]


def test_edges_global_and_start() -> None:
    d = session()
    d["edges"][1].pop("entry")
    assert problems(d) == ["edges.1: the edge into the map node xmas_dun02 names its entry"]
    d = session()
    d["edges"][1]["entry"] = "nowhere"
    assert problems(d) == ["edges.1: xmas_dun02 has no entry nowhere"]
    d = session()
    d["edges"].append({"from": "xmas_dun02", "to": "geffen"})
    assert problems(d) == [
        "edges.2: edges join login -> character -> map; map -> map is not one (map -> map is an "
        "exit, a take_exit statement; Global has no edges)"
    ]
    d = session()
    d["edges"].append({"from": "login", "to": "character"})
    assert "edges.2: login has two edges out (edges 0 and 2): the session path is one chain" in (
        problems(d))  # fmt: skip
    d = session()
    d["start"] = "global"
    assert problems(d) == [
        "start: start is a login node or a map node (she stands on it), not the global node global"
    ]
    d = session()
    d["start"] = "xmas_dun02"  # a map start (the one box): valid, the session nodes then unplayed
    assert build(d).start == "xmas_dun02"
    d = session()
    node(d, "global")["id"] = "shared"
    assert problems(d) == ['shared: the Global node\'s id is "global", not shared']
    d = session()
    d["nodes"].append(copy.deepcopy(node(d, "global")))
    assert "2 Global nodes: a project has at most one" in problems(d)


# --- names: imports and overrides (section 3) ---------------------------------------------------
def with_own_heal(key: str = "F2") -> dict[str, Any]:
    """xmas_dun02 overrides Global's heal (Batt's answer 2: "like a public class")."""
    return add_tab(session(), "xmas_dun02", tab("keys", fdef("heal", press(key))))


def test_global_s_event_calls_the_node_s_override_there_virtual_dispatch() -> None:
    p = build(with_own_heal())
    c = P.compile_project(p)
    assert c.dispatched == {("xmas_dun02", "hp_low")}
    flow = c.flow
    assert flow is not None and flow.workflow is not None
    xmas_b, geffen_b = flow.workflow.blocks
    (ov,) = xmas_b.events
    assert isinstance(ov, ir.Override) and ov.event.body == [ir.CallProc(proc="xmas_dun02__heal")]
    assert geffen_b.events == [] and flow.handlers[0].body == [ir.CallProc(proc="heal")]
    # the effective set shows it as Global's (inherited), run with the node's names
    eff = {e["key"]: e for e in P.effective_doc(c)["xmas_dun02"]}
    assert (eff["hp_low"]["state"], eff["hp_low"]["dispatched"], eff["hp_low"]["path"]) == (
        "inherited", True, "global/safety/hp_low")  # fmt: skip
    info = [f.text for f in findings(p) if f.rule == "dispatch"]
    assert info == ["Global's event hp_low runs on xmas_dun02 with xmas_dun02's own heal (an "
                    "override; tab safety)"]  # fmt: skip
    # in the simulator: HP drops on xmas_dun02, the insert presses xmas_dun02's F2, at its path
    doc = P.simulate(p, None, Scenario(horizon_s=40, timeline=[
        {"t": 20, "set": {"hp_percent": 25}}]))  # fmt: skip
    presses = [s for s in doc["play"] if s.get("action") == "press_key"]
    assert [(s["key"], s["node"]) for s in presses] == [("F2", "xmas_dun02/keys/heal.0")]


def test_without_an_override_global_s_function_runs() -> None:
    p = P.from_json(SESSION.read_text())
    doc = P.simulate(p, None, Scenario(horizon_s=40, timeline=[
        {"t": 20, "set": {"hp_percent": 25}}]))  # fmt: skip
    presses = [s for s in doc["play"] if s.get("action") == "press_key"]
    assert [(s["key"], s["node"]) for s in presses] == [("F1", "global/keys/heal.0")]
    assert "global/safety/hp_low.0" in doc["nodes"]


def test_a_node_s_event_replaces_global_s_there_only() -> None:
    own = fdef("hp_low", call("heal"), on={"when": hp("<", 50), "rearm": hp(">", 70),
                                           "priority": "survival", "mode": "insert"})  # fmt: skip
    c = P.compile_project(build(add_tab(session(), "xmas_dun02", tab("safety", own))))
    eff = P.effective_doc(c)
    x = next(e for e in eff["xmas_dun02"] if e["key"] == "hp_low")
    g = next(e for e in eff["geffen"] if e["key"] == "hp_low")
    assert (x["state"], x["path"]) == ("overridden", "xmas_dun02/safety/hp_low")
    assert (g["state"], g["path"]) == ("inherited", "global/safety/hp_low")


def test_a_plain_function_named_like_global_s_event_turns_it_off_there() -> None:
    p = build(add_tab(session(), "geffen", tab("quiet", fdef("hp_low", press("F7")))))
    eff = {e["key"]: e for e in P.effective_doc(P.compile_project(p))["geffen"]}
    assert eff["hp_low"]["active"] is False
    assert (
        "warning",
        "geffen/quiet/hp_low: hp_low is a plain function on geffen: Global's event "
        "hp_low does not run there",
    ) in [(f.severity, f.message) for f in findings(p)]


def test_a_node_s_safety_critical_event_is_never_weaker_than_the_built_in() -> None:
    dead = {"when": {"kind": "sense", "sensor": "is_dead"}, "priority": "critical",
            "max_per_run": 1, "then": "relocate"}  # fmt: skip
    ok = add_tab(session(), "geffen", tab("safety", fdef("dead", act("respawn"), on=dead)))
    assert errors(build(ok)) == []
    eff = {e["key"]: e for e in P.effective_doc(P.compile_project(build(ok)))["geffen"]}
    assert (eff["dead"]["state"], eff["dead"]["path"]) == ("overridden", "geffen/safety/dead")
    weak = add_tab(session(), "geffen", tab("safety", fdef("dead", act("sit"), on=dead)))
    assert errors(build(weak)) == [
        "geffen/safety/dead: dead's body starts with the built-in respawn(): steps may only "
        "follow it"
    ]
    off = add_tab(session(), "geffen", tab("safety", fdef("dead", act("respawn"))))
    assert "geffen: dead is safety-critical: it can be extended, never disabled" in errors(
        build(off)
    )


def test_global_uses_only_global_s_names() -> None:
    d = add_tab(session(), "global", tab("lib", fdef("go_home", call("only_here"))))
    d = add_tab(d, "geffen", tab("lib", fdef("only_here", press("F7"))))
    assert "global/lib/go_home.0: there is no procedure only_here" in errors(build(d))


def test_an_internal_name_never_shows_and_an_override_keeps_its_kind() -> None:
    d = add_tab(with_own_heal(), "xmas_dun02", tab("more", fdef("helper", call("heal", lit(3)))))
    assert "xmas_dun02/more/helper.0: heal() takes 0 positional arguments, not 1" in errors(
        build(d)
    )
    bad = add_tab(session(), "geffen", tab("keys", vars={"heal": lit(1)}))
    assert (
        "geffen/keys/heal: heal overrides Global's function heal (tab keys) with a variable: "
        "an override keeps its kind" in errors(build(bad))
    )


def test_a_variable_override_and_a_global_variable_assigned_from_a_node() -> None:
    lib = tab("lib", fdef("bump", {"kind": "set", "var": "COUNT", "value": {
        "kind": "arith", "op": "+", "left": var("COUNT"), "right": var("STEP")}}),
        vars={"COUNT": lit(0), "STEP": lit(1)})  # fmt: skip
    d = add_tab(session(), "global", lib)
    d = add_tab(d, "geffen", tab("cfg", vars={"STEP": lit(10)}))
    node(d, "geffen")["tabs"][0]["main"] = [
        call("bump"),
        call("bump"),
        {"kind": "stop", "reason": "home"},
    ]
    c = P.compile_project(build(d))
    assert c.flow is not None
    sim = Sim(c.flow, world={"map": "geffen", "cell": (119, 40)})
    sim.block = "geffen"
    sim.run()
    # Global's COUNT changes for everyone; geffen's STEP overrides Global's there
    assert sim.vars["COUNT"] == 20 and sim.vars["STEP"] == 1


# --- functions like Python (section 2: params, defaults, *args, **kwargs, return) --------------
def _lib() -> dict[str, Any]:
    body = [
        {"kind": "set", "var": "TOTAL", "value": {"kind": "arith", "op": "+", "left": var("a"),
                                                   "right": var("b")}},
        {"kind": "for", "var": "x", "items": var("rest"), "body": [
            {"kind": "set", "var": "TOTAL", "value": {"kind": "arith", "op": "+",
                                                      "left": var("TOTAL"), "right": var("x")}}]},
        {"kind": "if", "cond": {"kind": "cmp", "op": "in", "left": lit("boost"),
                                "right": var("opts")},
         "then": [{"kind": "return", "value": {"kind": "arith", "op": "+", "left": var("TOTAL"),
                                               "right": lit(100)}}], "orelse": []},
        {"kind": "return", "value": var("TOTAL")},
    ]  # fmt: skip
    add = fdef("add", *body, params=["a", {"name": "b", "default": lit(10)}], varargs="rest",
               kwargs="opts")  # fmt: skip
    return tab("lib", add, vars={"TOTAL": lit(0), "LAST": lit(0), "x": lit(0)})


def test_inputs_defaults_args_kwargs_and_return_in_the_simulator() -> None:
    d = add_tab(session(), "global", _lib())
    node(d, "geffen")["tabs"][0]["main"] = [
        {"kind": "set", "var": "LAST", "value": callv("add", lit(1), lit(2), lit(3), lit(4),
                                                     boost=lit(True))},
        {"kind": "if", "cond": {"kind": "cmp", "op": "==", "left": callv("add", lit(5)),
                                "right": lit(15)},
         "then": [{"kind": "stop", "reason": "fifteen"}],
         "orelse": [{"kind": "stop", "reason": "wrong"}]},
    ]  # fmt: skip
    p = build(d)
    assert [m for m in errors(p) if "geffen" in m or "lib" in m] == []
    c = P.compile_project(p)
    assert c.flow is not None
    sim = Sim(c.flow, world={"map": "geffen", "cell": (119, 40)})
    sim.block = "geffen"
    assert sim.run() == "fifteen"
    assert sim.vars["LAST"] == 110  # 1 + 2, then 3 and 4 from *rest, + 100 for **opts' boost


def test_a_call_s_arguments_are_checked_as_python_binds_them() -> None:
    d = add_tab(session(), "global", _lib())
    node(d, "geffen")["tabs"][0]["main"] = [
        call("add"), call("add", lit(1), a=lit(2)), {"kind": "stop", "reason": "home"}]  # fmt: skip
    assert [m for m in errors(build(d)) if m.startswith("geffen")] == [
        "geffen/main/main.0: add() needs a",
        "geffen/main/main.1: add() got a twice",
    ]


def test_recursion_is_refused_naming_the_cycle() -> None:
    d = add_tab(
        session(), "global", tab("lib", fdef("ping", call("pong")), fdef("pong", call("ping")))
    )
    assert "global/lib/ping: recursion (ping → pong → ping) is not allowed" in errors(build(d))
    # and the simulator bounds a run that ignores the linter
    node(d, "geffen")["tabs"][0]["main"] = [call("ping")]
    c = P.compile_project(build(d))
    assert c.flow is not None
    sim = Sim(c.flow, world={"map": "geffen"})
    sim.block = "geffen"
    assert sim.run() == "call_depth"


def test_a_pre_empting_event_never_sees_or_changes_the_locals_of_a_function_it_cuts() -> None:
    lib = tab("lib", fdef("wait_with", {"kind": "wait_until", "cond": lit(False),
                                        "timeout_s": 3, "outcome_to": None},
                          {"kind": "set", "var": "SEEN", "value": var("n")}, params=["n"]),
              fdef("other", {"kind": "set", "var": "SEEN2", "value": lit(0)}, params=["n"]),
              vars={"SEEN": lit(0), "SEEN2": lit(0)})  # fmt: skip
    d = add_tab(session(), "global", lib)
    ev = fdef("stuck", call("other", lit(99)), on={
        "when": {"kind": "sense", "sensor": "engagement_seen"}, "priority": "survival",
        "max_per_run": 1})  # fmt: skip
    d = add_tab(d, "geffen", tab("ev", ev))
    node(d, "geffen")["tabs"][0]["main"] = [
        call("wait_with", lit(7)),
        {"kind": "stop", "reason": "home"},
    ]
    c = P.compile_project(build(d))
    assert c.flow is not None
    sim = Sim(c.flow, world={"map": "geffen", "cell": (119, 40)},
              timeline=[(1.0, {"engagement_seen": True})])  # fmt: skip
    sim.block = "geffen"
    assert sim.run() == "home"
    assert sim.vars["SEEN"] == 7  # the cut function's own n


# --- the session blocks (sections 1 and 5) -------------------------------------------------------
def _login(server: str = "lab-rathena", credential: Any = "lab_gm") -> dict[str, Any]:
    d = session()
    node(d, "login")["tabs"][0]["main"] = [act("login", server=lit(server),
                                              credential=lit(credential))]  # fmt: skip
    return d


def test_the_login_names_an_environment_and_a_credential_by_name() -> None:
    assert [f for f in findings(build(_login())) if f.rule.startswith("session")] == []
    assert errors(build(_login(server="nowhere"))) == [
        "login/main/main.0: login's server nowhere is not an environment of the Settings page "
        "(lab-rathena, lab-rathena-th, official-ro-thai, official-ro-korea, community-bot-testing)"
    ]
    warn = [f.message for f in findings(build(_login(server="lab-rathena-th")))
            if f.rule == "session_server"]  # fmt: skip
    assert warn[0] == (
        "login/main/main.0: login's server lab-rathena-th (allowed) is not the lab's rAthena "
        "(lab-rathena): the simulation plays it, the bot never acts there (ADR-0006, ADR-0016)"
    )
    assert errors(build(_login(credential="lab_admin"))) == [
        "login/main/main.0: login's credential lab_admin is not one of the lab's: lab_gm, "
        "lab_player"
    ]


def test_a_secret_looking_credential_is_an_error_and_never_echoed() -> None:
    secret = "Hunter2-pass!"
    p = build(_login(credential=secret))
    msgs = [f.message for f in findings(p)]
    assert any("looks like a secret" in m for m in msgs)
    assert not any(secret in m for m in msgs)
    assert P.shown_hash(p) is None and P.has_secret(p)
    doc = P.simulate(p, None, Scenario(horizon_s=20))
    assert doc["play"][0]["credential"] is None and secret not in json.dumps(doc)


def test_session_blocks_belong_on_their_node_s_main() -> None:
    d = session()
    node(d, "geffen")["tabs"][0]["main"].insert(0, act("choose_character"))
    assert ("geffen/main/main.0: choose_character(...) belongs on a character node's main "
            "(simulated only: Run starts on a map node; the bot's real login is ro_agent's)") in (
        errors(build(d)))  # fmt: skip
    d = session()
    node(d, "login")["tabs"][0]["main"] = []
    assert (
        'login/main: a login node\'s main is one login(server="lab-rathena", '
        'credential="lab_gm") (simulated only: Run starts on a map node; the bot\'s real '
        "login is ro_agent's)"
    ) in errors(build(d))
    d = session()
    node(d, "character")["tabs"][0]["main"] = [act("choose_character", slot=lit(99))]
    assert errors(build(d)) == [
        "character/main/main.0: choose_character's slot is a number 1-15 (absent: the slot the "
        "client remembers)"
    ]
    d = session()
    d["edges"] = d["edges"][:1]
    assert (
        "edges: the session path is not complete: start (a login node) -> a character node "
        "-> a map node's entry, by edges (Simulate from login follows it); or start on a map "
        "node, where she stands" in errors(build(d))
    )


def test_the_session_plays_as_the_maps_pages_mock_then_enters_the_start_map() -> None:
    p = P.from_json(SESSION.read_text())
    doc = P.simulate(p, None, Scenario(horizon_s=30))
    login, character, first = doc["play"][:3]
    assert (login["kind"], login["t0"], login["t1"], login["node"]) == (
        "login", 0.0, 7.0, "login/main/main.0")  # fmt: skip
    assert login["phases"] == [{"what": "start", "t0": 0.0, "t1": 1.0},
                               {"what": "login", "t0": 1.0, "t1": 7.0}]  # fmt: skip
    assert (character["kind"], character["t0"], character["t1"]) == ("character", 7.0, 11.0)
    assert character["enters"] == {"block": "xmas_dun02", "entry": "here"}
    assert first["block"] == "xmas_dun02" and first["t0"] >= 11.0
    assert doc["start"]["block"] == "xmas_dun02" and doc["session"]["length_s"] == 11.0
    # Run starts on a map node: the scenario may start there, without the session
    on_map = P.simulate(p, None, Scenario(horizon_s=10, start_block="geffen"))
    assert on_map["session"] is None and on_map["start"]["block"] == "geffen"
    assert on_map["end"] == "home" and on_map["play"] == []
    with pytest.raises(ValueError, match="nowhere is no map node"):
        P.simulate(p, None, Scenario(start_block="nowhere"))


def test_login_and_character_never_reach_the_ir_that_runs() -> None:
    c = P.compile_project(P.from_json(SESSION.read_text()))
    assert c.flow is not None and c.flow.workflow is not None
    assert [b.name for b in c.flow.workflow.blocks] == ["xmas_dun02", "geffen"]
    assert P.LOGIN_BLOCK not in ir.to_json(c.flow) and "choose_character" not in ir.to_json(c.flow)
    assert (c.flow.workflow.start_block, c.flow.workflow.start_entry) == ("xmas_dun02", "here")


# --- a MAP start (Batt 2026-11-13 ~21:4x: "START > map xmas_dun02, one box is enough") ------------
def _map_start() -> dict[str, Any]:
    """The session fixture started on its map node: no login, no character, no edges."""
    d = session()
    d["start"] = "xmas_dun02"
    d["nodes"] = [n for n in d["nodes"] if n["kind"] not in ("login", "character")]
    d["edges"] = []
    return d


def test_a_map_start_validates_without_login_character_or_edges() -> None:
    p = build(_map_start())
    sp = P.session_path(p)
    assert (sp.login, sp.character, sp.entry, sp.map_start) == (None, None, "here", True)
    assert sp.map is not None and sp.map.id == "xmas_dun02"
    assert errors(p) == [] and [f for f in findings(p) if f.rule.startswith("session")] == []
    c = P.compile_project(p)
    assert c.flow is not None and c.flow.workflow is not None
    assert (c.flow.workflow.start_block, c.flow.workflow.start_entry) == ("xmas_dun02", "here")
    # the start map's FIRST entry, whichever it is
    d = _map_start()
    node(d, "xmas_dun02")["entries"].insert(0, {"name": "door", "at": None, "radius": 2})
    c2 = P.compile_project(build(d))
    assert c2.flow is not None and c2.flow.workflow is not None
    assert c2.flow.workflow.start_entry == "door"


def test_a_map_start_simulates_from_its_entry_with_no_session() -> None:
    p = build(_map_start())
    doc = P.simulate(p, None, Scenario(horizon_s=30))
    assert doc["session"] is None
    assert doc["start"]["block"] == "xmas_dun02" and doc["start"]["entry"] == "here"
    assert doc["play"] and doc["play"][0]["block"] == "xmas_dun02" and doc["play"][0]["t0"] == 0.0
    assert not [s for s in doc["play"] if s["kind"] in ("login", "character")]
    # the one-box fixture too: the save point, the runner, then the stop
    one = P.simulate(P.from_json(XMAS.read_text()), None, Scenario(horizon_s=900))
    assert one["session"] is None and one["end"] == "home"
    assert [s.get("action") for s in one["play"]][:3] == ["assert_save_point", "use_model",
                                                         "dungeon_hunt"]  # fmt: skip


def test_the_box_s_survival_events_simulate_on_scripted_sensors() -> None:
    """live-blocks.md stage 2: the simulator plays the one box's events like any other: drink on
    a scripted HP under 30 %, fly_away on a scripted sees_boss (the hunt core's boss read)."""
    p = P.from_json(XMAS.read_text())
    sc = Scenario(horizon_s=60, timeline=[{"t": 0.3, "set": {"hp_percent": 28}},
                                          {"t": 0.8, "set": {"hp_percent": 60, "sees_boss": True}},
                                          {"t": 1.0, "set": {"sees_boss": False}}])  # fmt: skip
    doc = P.simulate(p, None, sc)
    fired = [(e["t"], e["what"]) for e in doc["events"] if e["kind"] == "fire"]
    assert fired == [(0.3, "drink"), (0.8, "fly_away")] and doc["end"] == "home"
    assert [e["what"] for e in doc["events"] if e["kind"] == "until"] == ["drink"]
    # no boss scripted: sees_boss is unknown (None), HP under 25 % flies once (one-shot) and the
    # drink repeats at its pace while the scenario keeps HP there (a simulated press heals none)
    quiet = P.simulate(
        p, None, Scenario(horizon_s=60, timeline=[{"t": 0.3, "set": {"hp_percent": 24}}])
    )
    fires = [e["what"] for e in quiet["events"] if e["kind"] == "fire"]
    assert fires[:2] == ["fly_away", "drink"] and fires.count("fly_away") == 1
    assert set(fires[2:]) == {"drink"}


def test_a_map_start_with_session_nodes_warns_they_are_not_played() -> None:
    d = session()
    d["start"] = "xmas_dun02"
    p = build(d)
    assert errors(p) == []
    warn = [f.message for f in findings(p) if f.rule == "session_path"]
    assert warn == [
        "start: start is the map node xmas_dun02: the run starts where she stands there; the "
        "nodes login, character are not played (a login start plays the session)"
    ]


def test_the_python_view_s_start_line_names_the_map() -> None:
    from poring_flow import pyproject as V

    p = P.from_json(XMAS.read_text())
    files = V.print_files(p)
    by = {f.path: f.text for f in files}
    assert list(by) == ["xmas_dun02/main.py", "xmas_dun02/keys.py", "xmas_dun02/survival.py",
                        "xmas_dun02/knife.py", "xmas_dun02/exits.py",
                        "xmas_dun02/monsters.py", "project.py"]  # fmt: skip
    assert (
        "@on(sees_boss() or hp_percent() < 25, priority=CRITICAL, cooldown_s=3)\n"
        "def fly_away():\n    fly_wing()\n"
    ) in by["xmas_dun02/survival.py"]
    assert 'START = "xmas_dun02"\n' in by["project.py"] and "edge(" not in by["project.py"]
    assert V.parse_files(by) == p


# --- Run's keys (section 6) ----------------------------------------------------------------------
def test_runner_keys_from_the_fixture_and_with_an_override() -> None:
    p = P.from_json(SESSION.read_text())
    rk = P.runner_keys(p, "xmas_dun02")
    assert rk.problems == [] and rk.keys == {
        "heal_key": "F1",
        "fly_key": "F8",
        "home_key": "F9",
        "knife_key": "F4",
        "dagger_key": "F5",
    }
    assert rk.functions["home_key"] == "butterfly_wing"
    over = build(add_tab(session(), "xmas_dun02", tab("keys", fdef("fly_wing", press("F6")))))
    rk = P.runner_keys(over, "xmas_dun02")
    assert rk.keys is not None and rk.keys["fly_key"] == "F6" and rk.functions["fly_key"] == (
        "fly_wing")  # the user's name, never the internal one  # fmt: skip
    assert errors(over) == []
    assert P.runner_keys(p, "geffen").problems[0].startswith("geffen's main has no dungeon_hunt")
    assert P.runner_keys(p, "login").problems == ["login is no map node: Run belongs to a map node"]


def test_runner_keys_take_home_from_the_home_role_first() -> None:
    p = P.from_json(XMAS.read_text())  # the one box: no item warp, the runner flies home itself
    rk = P.runner_keys(p, "xmas_dun02")
    assert rk.problems == [] and rk.keys == {"heal_key": "F1", "fly_key": "F8", "home_key": "F9",
                                             "knife_key": "F4", "dagger_key": "F5"}  # fmt: skip
    assert rk.functions["home_key"] == "fly_home"  # stage 3: a body (it calls butterfly_wing)
    # the home role wins over the item warp's function (the session fixture has one: F9)
    d = session()
    xm = node(d, "xmas_dun02")
    xm["tabs"].append(tab("mine", fdef("wing_two", press("F7"))))
    xm["tabs"][0]["main"][1]["body"][0]["params"]["home"] = lit("wing_two")
    rk = P.runner_keys(build(d), "xmas_dun02")
    assert rk.keys is not None and rk.keys["home_key"] == "F7"
    assert rk.functions["home_key"] == "wing_two"
    # no home role and no item warp: refused in words
    d = copy.deepcopy(json.loads(XMAS.read_text()))
    del d["nodes"][0]["tabs"][0]["main"][HUNT]["params"]["home"]
    assert P.runner_keys(build(d), "xmas_dun02").problems == [
        "xmas_dun02 has no Butterfly Wing home: dungeon_hunt's home names no function and the "
        "map has no item warp by function"
    ]


def test_the_home_role_is_one_press_on_its_own_key_and_a_wing_key() -> None:
    from poring_flow import functions as fn

    d = json.loads(XMAS.read_text())
    keys = d["nodes"][0]["tabs"][1]["defs"]
    hunt_ = d["nodes"][0]["tabs"][0]["main"][HUNT]
    p = build(d)
    c = P.compile_project(p)
    assert c.flow is not None and fn.wing_keys(c.flow) == {"F9": ["fly_home"]}
    # two presses: not one Butterfly Wing (stage 3: a home BODY presses exactly one key)
    bad = copy.deepcopy(d)
    next(x for x in bad["nodes"][0]["tabs"][1]["defs"] if x["name"] == "butterfly_wing")["body"] = [
        press("F9"), press("F9")]  # fmt: skip
    assert errors(build(bad)) == [
        "xmas_dun02/main/main.2: dungeon_hunt's home (the Butterfly Wing's key, to fly home): "
        "fly_home presses 2 keys: the way home is ONE Butterfly Wing (one press_key, waits "
        "around it)"
    ]
    # the home key taken by another role: ONE error of the runner's, the clash -- and the box's
    # fly_away event (stage 2), which then presses the Butterfly Wing, must relocate or stop
    same = copy.deepcopy(d)
    next(x for x in same["nodes"][0]["tabs"][1]["defs"] if x["name"] == "fly_wing")["body"] = [
        press("F9")]  # fmt: skip
    assert [m for m in errors(build(same)) if "F9" in m] == [
        "xmas_dun02/main/main.2: dungeon_hunt's fly and home both press F9: each role needs its "
        "own key",
        "xmas_dun02/survival/fly_away: the Butterfly Wing on F9 (fly_home) changes the map: "
        "then must be relocate or stop",
    ]
    # an undefined function
    gone = copy.deepcopy(d)
    gone["nodes"][0]["tabs"][0]["main"][HUNT]["params"]["home"] = lit("nowhere")
    assert errors(build(gone)) == [
        "xmas_dun02/main/main.2: dungeon_hunt's home (the Butterfly Wing's key, to fly home): "
        "there is no function nowhere"
    ]
    assert keys and hunt_["block"] == "dungeon_hunt"


def test_runner_keys_resolve_through_calls_with_literal_arguments() -> None:
    lib = tab("lib", fdef("press_slot", press(var("k")), params=["k"]))
    d = add_tab(session(), "global", lib)
    keys = node(d, "global")["tabs"][0]["defs"]
    next(x for x in keys if x["name"] == "heal")["body"] = [call("press_slot", lit("F2"))]
    p = build(d)
    assert errors(p) == []
    rk = P.runner_keys(p, "xmas_dun02")
    assert rk.keys is not None and rk.keys["heal_key"] == "F2"
    doc = P.simulate(p, None, Scenario(horizon_s=40, timeline=[
        {"t": 20, "set": {"hp_percent": 25}}]))  # fmt: skip
    assert [s["key"] for s in doc["play"] if s.get("action") == "press_key"] == ["F2"]
    next(x for x in node(d, "global")["tabs"][0]["defs"] if x["name"] == "heal")["body"] = [
        call("press_slot", lit("F12"))]  # fmt: skip
    assert (
        "global/keys/heal.0: press_slot()'s k is the key its press_key presses: a literal "
        'hotbar key (F1-F9), not "F12"' in errors(build(d))
    )


# --- an event condition reads sensors and variables -----------------------------------------------
def test_an_event_condition_cannot_call_a_function() -> None:
    low = fdef("low", {"kind": "return", "value": lit(True)})
    d = add_tab(session(), "global", tab("lib", low))
    hp_low = node(d, "global")["tabs"][1]["defs"][0]
    hp_low["on"]["when"] = {"kind": "and", "terms": [hp("<", 30), callv("low")]}
    assert (
        "global/safety/hp_low: an event condition cannot call a function: it reads sensors "
        "and variables" in errors(build(d))
    )
