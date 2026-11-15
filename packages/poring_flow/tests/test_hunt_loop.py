"""Live blocks stage 5b-2 in the flow engine (docs/planning/live-blocks.md 13.4 and 14): the HUNT
LOOP -- a map node's hunt_loop(t), the hunt core's steps as blocks -- its lint rules, the live
refusals (the backend's not_live: live.problems, the same words), the fixture with the canonical
loop, and its Python view's round trip (one definition: poring_flow.huntloop)."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from poring_flow import editor, huntloop, live
from poring_flow import project as P
from poring_flow import pyproject as pp

sys.path.insert(0, str(Path(__file__).parent))
from project_kit import FIXTURES, XMAS, act, call, fdef, lit, press, tab, var  # noqa: E402

HUNT = FIXTURES / "project_xmas_dun02_hunt.json"


def take(block: str, out: str, **params: Any) -> dict[str, Any]:
    return {**act(block, **params), "outcome_to": out}


def loop(*body: Any, cond: Any = None) -> dict[str, Any]:
    return {"kind": "while", "cond": cond or lit(True), "body": list(body)}


CANON = [loop(take(huntloop.EXPLORE, "t"), act(huntloop.ATTACK, target=var("t")))]


def boxed(*body: Any, params: Any = ("t",), name: str = huntloop.HUNT_LOOP,
          main: list[Any] | None = None) -> dict[str, Any]:  # fmt: skip
    """The one box plus a tab hunt holding ``name(params): body``."""
    d = json.loads(XMAS.read_text())
    tabs = d["nodes"][0]["tabs"]
    if main is not None:
        tabs[0]["main"] = main
    i = [t["name"] for t in tabs].index("monsters")
    tabs.insert(i + 1, tab(huntloop.HUNT_TAB, fdef(name, *body, params=params)))
    return d


def compiled(d: dict[str, Any]) -> Any:
    c = P.compile_project(P.validate(copy.deepcopy(d)))
    assert c.flow is not None
    return c


def rules(d: dict[str, Any]) -> list[tuple[str, str, str]]:
    p = P.validate(copy.deepcopy(d))
    return [(f.rule, f.severity, f.where.path) for f in P.project_lint(p)[1]
            if f.severity == "error"]  # fmt: skip


def texts(d: dict[str, Any], rule: str) -> list[str]:
    p = P.validate(copy.deepcopy(d))
    return [f.text for f in P.project_lint(p)[1] if f.rule == rule]


def not_live(d: dict[str, Any]) -> list[str]:
    return [n.words for n in live.problems(compiled(d).flow)]


# --- the fixture: the one box plus the canonical loop ---------------------------------------------
def test_the_hunt_fixture_is_the_one_box_plus_the_hunt_tab() -> None:
    raw, one = HUNT.read_text(), json.loads(XMAS.read_text())
    p = P.from_json(raw)
    assert P.canonical_json(p) + "\n" == raw  # canonical, as every ready-made project
    d = json.loads(raw)
    tabs = d["nodes"][0]["tabs"]
    hunt = tabs.pop([t["name"] for t in tabs].index(huntloop.HUNT_TAB))
    assert d["nodes"] == one["nodes"]  # nothing else differs from the one box (but its name)
    assert {k: v for k, v in d.items() if k not in ("nodes", "name", "description")} == {
        k: v for k, v in one.items() if k not in ("nodes", "name", "description")}  # fmt: skip
    assert hunt["defs"][0]["name"] == "hunt_loop" and hunt["defs"][0]["params"] == [
        {"name": "t", "default": None}]  # fmt: skip
    c = compiled(json.loads(raw))
    assert live.problems(c.flow) == [] and rules(json.loads(raw)) == []
    plans, issues = huntloop.analyse(c.flow)
    assert issues == [] and plans["xmas_dun02"] == huntloop.LoopPlan("xmas_dun02", "hunt_loop",
                                                                     ("F1",))  # fmt: skip
    hp = live.hunt_plan(c.flow, "xmas_dun02")
    one_hp = live.hunt_plan(compiled(one).flow, "xmas_dun02")
    assert hp.loop == "hunt_loop" and hp.skill_keys == ("F1",) and one_hp.loop is None
    assert hp.plays == one_hp.plays and hp.recipes == one_hp.recipes  # the same run() arguments


def test_the_python_view_of_the_hunt_tab_and_its_round_trip() -> None:
    p = P.from_json(HUNT.read_text())
    files = {f.path: f.text for f in pp.print_files(p)}
    src = files["xmas_dun02/hunt.py"]
    # (round 26: a hunt loop block at its default time box says it in a comment, as its block does)
    assert (
        "def hunt_loop(t):\n    while True:\n        t = find_target()  # at most 120 s\n"
        "        fight_target(t)  # at most 300 s\n" in src
    )
    # the names the Python view knows the time box for are the hunt loop's blocks
    from poring_flow import pyview

    assert set(pyview.HUNT_BOX_BLOCKS) == set(huntloop.NEW_BLOCKS)
    assert P.canonical_json(pp.parse_files(files)) == P.canonical_json(p)
    # every ready-made project round-trips (the one box has no hunt tab: unchanged)
    one = P.from_json(XMAS.read_text())
    assert "xmas_dun02/hunt.py" not in {f.path for f in pp.print_files(one)}


def test_the_canonical_loop_and_variants_that_play() -> None:
    for body in (
        CANON,
        [loop(take(huntloop.EXPLORE, "t"), act("strike", target=var("t")),
              act("wait_kill", target=var("t")), act("loot", target=var("t")))],
        [loop(take(huntloop.EXPLORE, "t"), act(huntloop.WALK, target=var("t")),
              act(huntloop.ATTACK, target=var("t")), act("use_skill", key=lit("F1")))],
        [loop(take(huntloop.EXPLORE, "t"),
              {"kind": "if", "cond": {"kind": "sense", "sensor": "known",
                                      "args": {"value": var("t")}},
               "then": [take(huntloop.LOOK, "t")], "orelse": []},
              act(huntloop.ATTACK, target=var("t")), {"kind": "break"})],
        [take(huntloop.EXPLORE, "t"), act(huntloop.ATTACK, target=var("t"))],  # no loop: once
    ):  # fmt: skip
        d = boxed(*body)
        assert not_live(d) == [] and rules(d) == [], (body, rules(d), not_live(d))


# --- the refusals: each named, the lint and the live set the same ---------------------------------
@pytest.mark.parametrize(("why", "body", "rule", "words"), [
    ("a loop with no block that always advances (spin)",
     [loop(take(huntloop.EXPLORE, "t"), take(huntloop.LOOK, "x"))], "hunt_spin",
     "it could spin while no step runs"),
    ("a loop that does not begin with find_target",
     [loop(act(huntloop.ATTACK, target=var("t")), take(huntloop.EXPLORE, "t"))], "hunt_spin",
     "it begins with t = find_target()"),
    ("the fight player on another target", [loop(take(huntloop.EXPLORE, "t"),
                                                 act(huntloop.ATTACK, target=var("u")))],
     "hunt_spin", "a block that plays the fight to its end on t"),
    ("a wait in the loop", [loop(take(huntloop.EXPLORE, "t"), act(huntloop.ATTACK, target=var("t")),
                                 {"kind": "wait_until", "cond": lit(False), "timeout_s": 1})],
     "hunt_statement", "a wait in hunt_loop"),
    ("a press in the loop", [*CANON, press("F6")], "hunt_statement", "press_key in hunt_loop"),
    ("a call in the loop", [*CANON, call("heal")], "hunt_statement", "a call in hunt_loop"),
    ("a stop in the loop", [*CANON, {"kind": "stop", "reason": "home"}], "hunt_statement",
     "a stop in hunt_loop"),
    ("a sensor in a condition", [loop(take(huntloop.EXPLORE, "t"),
                                      act(huntloop.ATTACK, target=var("t")),
                                      cond={"kind": "sense", "sensor": "hp_percent", "args": {}})],
     "hunt_sensor", "hp_percent() in hunt_loop"),
    ("a target that is not a variable", [loop(take(huntloop.EXPLORE, "t"),
                                              act(huntloop.ATTACK, target=var("t")),
                                              act("strike", target=lit({"kind": "mob", "id": 1})))],
     "hunt_target", "its target is a variable"),
    ("use_skill without a declared role key", [*CANON, act("use_skill", key=lit("F6"))],
     "hunt_skill", "presses a DECLARED role key"),
])  # fmt: skip
def test_each_refusal_is_named_in_the_lint_and_before_any_input(
        why: str, body: list[Any], rule: str, words: str) -> None:  # fmt: skip
    d = boxed(*body)
    found = texts(d, rule)
    assert found and any(words in t for t in found), (why, rules(d))
    assert any(words in w for w in not_live(d)), (why, not_live(d))  # the backend's not_live


def test_the_loop_needs_its_input_and_a_hunt_core() -> None:
    d = boxed(*CANON, params=())
    assert any("def hunt_loop(t)" in t for t in texts(d, "hunt_loop_input"))
    assert any("def hunt_loop(t)" in w for w in not_live(d))
    one = json.loads(XMAS.read_text())
    main = [s for s in one["nodes"][0]["tabs"][0]["main"] if s.get("block") != "dungeon_hunt"]
    d2 = boxed(*CANON, main=main)
    assert any("its map node's main runs dungeon_hunt" in t for t in texts(d2, "hunt_loop_place"))


def test_hunt_blocks_outside_the_loop_are_refused() -> None:
    d = json.loads(XMAS.read_text())
    d["nodes"][0]["tabs"][0]["main"].insert(1, take(huntloop.EXPLORE, "x"))
    d["nodes"][0]["tabs"][0]["vars"] = {"x": lit(0)}
    assert any("find_target plays live only in the hunt core's hunt loop" in t
               for t in texts(d, "hunt_primitive"))  # fmt: skip
    assert any("find_target plays live only" in w for w in not_live(d))
    # a recipe primitive in the loop is the loop's (not 4a's recipe_primitive)
    d2 = boxed(loop(take(huntloop.EXPLORE, "t"), act("wait_kill", target=var("t"))))
    assert texts(d2, "recipe_primitive") == [] and not_live(d2) == []


def test_the_editor_and_the_live_set_name_the_loop() -> None:
    doc = editor.catalogue_doc()
    for b in huntloop.BLOCKS:
        assert doc["blocks"][b]["spec"]["live"] is True, b
    lp = doc["live"]["hunt_core"]["loop"]
    assert lp["function"] == "hunt_loop" and lp["tab"] == "hunt"
    assert set(huntloop.NEW_BLOCKS) <= set(live.OWN_BINDING)
    assert huntloop.VERSION == "9.55"
