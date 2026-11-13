"""Live blocks stage 4a in the flow engine (Batt 2026-11-13: "break the core into functions, e.g.
attack_myst_case, attack_cookie, because in the future each monster may get a different skill or
killing technique, and on some we may not swap the knife at all"; docs/planning/live-blocks.md
3.4, ADR-0020 Amendment H): use_model, one recipe per monster, the orders the runner plays, the
lint rules and the live refusals (one definition: poring_flow.recipes)."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from poring_flow import editor, lint, live, models
from poring_flow import project as P
from poring_flow import recipes as rc

sys.path.insert(0, str(Path(__file__).parent))
from project_kit import XMAS, act, call, fdef, lit, tab, var  # noqa: E402

TODAY = list(rc.KNIFE_SHAPE)


def prim(block: str, t: str = "t") -> dict[str, Any]:
    return act(block, target=var(t))


def body(*steps: str, t: str = "t") -> list[dict[str, Any]]:
    return [call(s) if s in (rc.KNIFE_ON, rc.KNIFE_BACK) else prim(s, t) for s in steps]


def recipe(species: str, *steps: str, priority: Any = 1) -> dict[str, Any]:
    params: list[Any] = [{"name": "t", "default": None}]
    if priority is not None:
        params.append({"name": "priority", "default": lit(priority)})
    return fdef(f"attack_{species}", *body(*steps), params=params)


def box(*defs: dict[str, Any], model: str | None = "xmas02") -> dict[str, Any]:
    """The one box with its monsters tab replaced (and its use_model's model, or none)."""
    d = json.loads(XMAS.read_text())
    tabs = d["nodes"][0]["tabs"]
    mon = next(t for t in tabs if t["name"] == rc.MONSTERS_TAB)
    mon["defs"] = list(defs)
    main = tabs[0]["main"]
    use = next(s for s in main if s.get("block") == rc.MODEL_BLOCK)
    if model is None:
        main.remove(use)
    else:
        use["params"]["model"] = lit(model)
    return d


def compiled(d: dict[str, Any]) -> Any:
    c = P.compile_project(P.validate(copy.deepcopy(d)))
    assert c.flow is not None
    return c


def rules(d: dict[str, Any]) -> list[tuple[str, str, str]]:
    p = P.validate(copy.deepcopy(d))
    return [(f.rule, f.severity, f.where.path) for f in P.project_lint(p)[1]
            if f.rule.startswith(("recipe", "use_model"))]  # fmt: skip


def not_live(d: dict[str, Any]) -> list[str]:
    c = compiled(d)
    return [n.words for n in live.problems(c.flow)]


# --- the one box ----------------------------------------------------------------------------------
def test_the_one_box_names_its_model_and_writes_todays_technique_for_every_monster() -> None:
    c = compiled(json.loads(XMAS.read_text()))
    plans, issues = rc.analyse(c.flow)
    assert [i for i in issues if i.severity != "info"] == [] and live.problems(c.flow) == []
    p = plans["xmas_dun02"]
    assert p.model == "xmas02" and p.default == ()
    strikes = ["mystcase", "cruiser", "cookie", "cookie_xmas"]
    assert p.model_doc() == {"id": "xmas02", "file": "xmas02gb-last-736x1280.onnx",
                             "sha256": "b22d972b714f", "maps": ["xmas_dun02"], "status": "live",
                             "kind": "detector", "strikes": strikes}  # fmt: skip
    assert {s: r.doc() for s, r in p.recipes.items()} == {
        s: {"function": f"attack_{s}", "steps": TODAY, "knife": True, "priority": 1.0}
        for s in ("cookie", "cookie_xmas", "cruiser", "mystcase")
    }
    hp = live.hunt_plan(c.flow, "xmas_dun02")
    assert {"model", "recipes"} <= hp.plays and hp.recipes == p.recipes
    assert hp.model_doc == p.model_doc() and hp.default_species == ()


def test_the_model_classes_are_the_monsters_the_runner_strikes() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
    import unit_detector as ud

    xmas = models.models().models["xmas02"]
    assert xmas.strikes == list(ud.MAP_MODELS["xmas_dun02"].collapse)  # garm_baby: not struck
    assert "garm_baby" in xmas.classes and "garm_baby" not in xmas.strikes
    assert all(not m.strikes for k, m in models.models().models.items() if k != "xmas02")
    with pytest.raises(ValueError, match="strikes name classes"):
        models.ModelSpec(kind="detector", status="live", file="a.onnx", sha256="0" * 12,
                         classes=["a", "b"], strikes=["b", "a"], why="x")  # fmt: skip


# --- the orders the runner plays ------------------------------------------------------------------
@pytest.mark.parametrize(
    ("steps", "words"),
    [
        (TODAY, None),
        (list(rc.PLAIN_SHAPE), None),
        ([*rc.KNIFE_SHAPE[:4], "use_skill", *rc.KNIFE_SHAPE[4:]], None),
        (["wait_kill", "strike", "loot"], "wait_kill(t) before strike(t)"),
        (["strike", "loot", "wait_kill"], "loot(t) before wait_kill(t)"),
        (["strike", "knife_back", "wait_kill", "loot"], "knife_back() without knife_on()"),
        (["strike", "wait_steal", "wait_kill", "loot"], "wait_steal(t) without knife_on()"),
        (
            ["knife_on", "strike", "wait_steal", "wait_kill", "loot"],
            "knife_on() without knife_back()",
        ),
        (["knife_on", "strike", "knife_back", "wait_kill", "loot"], "without wait_steal(t)"),
        (["strike", "wait_kill"], "never loots"),
        (["strike", "loot"], "never waits for the kill"),
        (["knife_on", "wait_kill", "loot"], "never strikes"),
        (["strike", "strike", "wait_kill", "loot"], "strike() twice"),
        (
            ["strike", "knife_on", "wait_steal", "knife_back", "wait_kill", "loot"],
            "knife_on() after the strike",
        ),
        (
            ["knife_on", "strike", "knife_back", "wait_steal", "wait_kill", "loot"],
            "knife_back() before wait_steal(t)",
        ),
        (
            ["knife_on", "strike", "wait_steal", "wait_kill", "knife_back", "loot"],
            "4a plays the runner's own order",
        ),
    ],
)
def test_order_problem_names_each_mistake(steps: list[str], words: str | None) -> None:
    got = rc.order_problem(steps, "attack_x")
    assert (got is None) if words is None else (got is not None and words in got), got


# --- the lint and the live refusals: one rule each ------------------------------------------------
def test_a_monster_without_a_function_is_the_runners_own_named_as_info() -> None:
    d = box(recipe("mystcase", *TODAY))
    c = compiled(d)
    plan = live.hunt_plan(c.flow, "xmas_dun02")
    assert list(plan.recipes) == ["mystcase"]
    assert plan.default_species == ("cruiser", "cookie", "cookie_xmas")
    assert [r for r in rules(d) if r[0] == "recipe_default"] == [
        ("recipe_default", "info", "xmas_dun02") for _ in range(3)]  # fmt: skip
    assert live.problems(c.flow) == []  # info only: it plays
    # the words name the runner's own recipe
    texts = [f.text for f in P.project_lint(P.validate(d))[1] if f.rule == "recipe_default"]
    assert texts[0].startswith("cruiser: no attack function (attack_cruiser); the runner's own")


def test_a_recipe_without_knife_on_is_struck_without_the_swap() -> None:
    d = box(recipe("mystcase", *TODAY), recipe("cookie", *rc.PLAIN_SHAPE, priority=None))
    c = compiled(d)
    r = live.hunt_plan(c.flow, "xmas_dun02").recipes
    assert r["mystcase"].knife and not r["cookie"].knife and r["cookie"].priority is None
    assert r["cookie"].doc() == {"function": "attack_cookie", "steps": list(rc.PLAIN_SHAPE),
                                 "knife": False, "priority": None}  # fmt: skip
    assert rules(d) == [("recipe_default", "info", "xmas_dun02")] * 2 and not_live(d) == []


def _with(d: dict[str, Any], where: str, stmt: dict[str, Any], i: int = 1) -> dict[str, Any]:
    """The one box with ``stmt`` inserted into its main (where "main") at ``i``."""
    d = copy.deepcopy(d)
    d["nodes"][0]["tabs"][0]["main"].insert(i, stmt)
    return d


CASES: list[tuple[str, Any, str, str]] = [
    (
        "a class the model lacks",
        lambda: box(recipe("dragon", *TODAY)),
        "recipe_class",
        "the model xmas02 has no class dragon",
    ),
    (
        "a class the runner never strikes",
        lambda: box(recipe("garm_baby", *TODAY)),
        "recipe_class",
        "the runner never strikes garm_baby",
    ),
    (
        "recipes without use_model",
        lambda: box(recipe("mystcase", *TODAY), model=None),
        "recipe_model",
        "it needs use_model",
    ),
    ("a model not adopted", lambda: box(model="stormy-v1"), "use_model_model", "not adopted"),
    (
        "a model that is not there",
        lambda: box(model="v9"),
        "use_model_model",
        "no trained model v9",
    ),
    (
        "a step outside the set",
        lambda: box(
            {**recipe("mystcase", *TODAY), "body": [*body(*TODAY), act("press_key", key=lit("F6"))]}
        ),
        "recipe_step",
        "holds press_key",
    ),
    (
        "a knife function that is not the hunt core's",
        lambda: box(
            {**recipe("mystcase", *TODAY), "body": [call("wield_knife"), *body(*TODAY[1:])]}
        ),
        "recipe_step",
        "holds wield_knife()",
    ),
    (
        "a target that is not its input",
        lambda: box(
            fdef("attack_mystcase", *body(*TODAY, t="u"), params=[{"name": "t", "default": None}])
        ),
        "recipe_target",
        "its target is the recipe's own",
    ),
    (
        "no input",
        lambda: box(fdef("attack_mystcase", call("knife_on"))),
        "recipe_input",
        "takes its target first",
    ),
    (
        "a priority that is no number",
        lambda: box(recipe("mystcase", *TODAY, priority="high")),
        "recipe_priority",
        "priority is a number",
    ),
    (
        "a priority of 0",
        lambda: box(recipe("mystcase", *TODAY, priority=0)),
        "recipe_priority",
        "above 0",
    ),
    (
        "an order the runner cannot play",
        lambda: box(recipe("mystcase", "strike", "loot", "wait_kill")),
        "recipe_order",
        "loot(t) before wait_kill(t)",
    ),
    (
        "a primitive outside a recipe",
        lambda: _with(
            json.loads(XMAS.read_text()),
            "main",
            act("wait_kill", target=lit({"kind": "mob", "id": 1249})),
        ),
        "recipe_primitive",
        "plays live only inside a monster's recipe",
    ),
    (
        "a recipe called from a block",
        lambda: _with(
            json.loads(XMAS.read_text()),
            "main",
            call("attack_mystcase", lit({"kind": "mob", "id": 1249})),
        ),
        "recipe_call",
        "the hunt core asks it at its lock",
    ),
    (
        "use_model after the hunt core",
        lambda: _with(box(model=None), "main", act("use_model", model=lit("xmas02")), 2),
        "use_model_place",
        "no dungeon_hunt after it",
    ),
]


@pytest.mark.parametrize(("why", "make", "rule", "words"), CASES, ids=[c[0] for c in CASES])
def test_each_mistake_is_a_lint_error_and_refused_live(why: str, make: Any, rule: str,
                                                       words: str) -> None:  # fmt: skip
    d = make()
    p = P.validate(copy.deepcopy(d))
    found = [f for f in P.project_lint(p)[1] if f.rule == rule]
    assert found and all(f.severity == "error" for f in found), (why, rules(d))
    assert any(words in f.text for f in found), [f.text for f in found]
    assert any(words in w for w in not_live(d)), not_live(d)  # the backend's not_live: the same


def test_use_skill_in_a_recipe_is_linted_and_refused_live_as_4b() -> None:
    sk = {**recipe("mystcase", *TODAY), "body": [*body(*TODAY[:4]),
          act("use_skill", key=lit("F6")), *body(*TODAY[4:])]}  # fmt: skip
    d = box(sk)
    p = P.validate(copy.deepcopy(d))
    got = [(f.rule, f.severity) for f in P.project_lint(p)[1] if f.rule == "recipe_skill"]
    assert got == [("recipe_skill", "warning")]  # expressible: not a design error
    words = not_live(d)
    assert any("use_skill cannot play live yet (stage 4b" in w for w in words), words
    # without its hotbar key it is an error (the key is what 4b presses)
    bad = box({**sk, "body": [*body(*TODAY[:4]), act("use_skill"), *body(*TODAY[4:])]})
    assert ("recipe_skill", "error", "xmas_dun02/monsters/attack_mystcase.4") in rules(bad)


def test_loot_without_a_target_is_the_old_block_and_does_not_play_live() -> None:
    d = _with(json.loads(XMAS.read_text()), "main", act("loot"))
    assert any("loot() without its target" in w for w in not_live(d))


def test_no_recipe_context_no_recipe_rules() -> None:
    """A flow with no use_model and no primitive: an attack_* function is an ordinary one."""
    d = json.loads(XMAS.read_text())
    tabs = d["nodes"][0]["tabs"]
    tabs.remove(next(t for t in tabs if t["name"] == rc.MONSTERS_TAB))
    main = tabs[0]["main"]
    main.remove(next(s for s in main if s.get("block") == rc.MODEL_BLOCK))
    tabs.append(tab("mine", fdef("attack_now", call("heal"))))
    c = compiled(d)
    assert rc.analyse(c.flow) == ({}, []) and rules(d) == [] and live.problems(c.flow) == []
    assert "model" not in live.hunt_plan(c.flow, "xmas_dun02").plays


def test_the_editor_gets_the_primitives_and_the_live_words() -> None:
    doc = editor.catalogue_doc()
    for b in (*rc.PRIMITIVES, rc.MODEL_BLOCK):
        assert doc["blocks"][b]["spec"]["live"] is True, b
    assert doc["live"]["hunt_core"]["recipes"]["shapes"] == [list(x) for x in rc.SHAPES]
    assert doc["live"]["later"]["use_skill"].startswith("stage 4b")
    assert doc["models"]["xmas02"]["strikes"] == ["mystcase", "cruiser", "cookie", "cookie_xmas"]
    assert {b: doc["blocks"][b]["status"] for b in ("use_model", "wait_steal", "wait_kill")} == {
        "use_model": "core", "wait_steal": "core", "wait_kill": "core"}  # fmt: skip


def test_the_simulator_plays_use_model_without_input() -> None:
    one = P.simulate(P.from_json(XMAS.read_text()), None, __import__(
        "poring_flow.trace", fromlist=["Scenario"]).Scenario(horizon_s=900))  # fmt: skip
    use = [s for s in one["play"] if s.get("action") == rc.MODEL_BLOCK]
    assert len(use) == 1 and use[0]["outcome"] == "ok"
    assert lint.lint(compiled(json.loads(XMAS.read_text())).flow) is not None
