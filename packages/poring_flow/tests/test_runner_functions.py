"""Live blocks stage 5c in the flow engine (docs/planning/live-blocks.md 15): the runner block
dissolved into functions in tabs -- a map node's main calls hunt_loop(), its roles are role blocks,
its tick is hunt_tick()'s step blocks. The lowering to the hunt box's hunt core, the rules (the
lint and live.problems alike), the ready-made box and its Python view."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from poring_flow import huntloop, live
from poring_flow import project as P
from poring_flow import pyproject as pp
from poring_flow import tick as tk

sys.path.insert(0, str(Path(__file__).parent))
from project_kit import FIXTURES, XMAS, act, call, fdef, lit  # noqa: E402

FUN = FIXTURES / "project_xmas_dun02_functions.json"
HUNT = FIXTURES / "project_xmas_dun02_hunt.json"


def box(edit: Any = None) -> dict[str, Any]:
    d = json.loads(FUN.read_text())
    if edit is not None:
        edit(d)
    return d


def tab(d: dict[str, Any], name: str) -> dict[str, Any]:
    return next(t for t in d["nodes"][0]["tabs"] if t["name"] == name)


def compiled(d: dict[str, Any]) -> Any:
    c = P.compile_project(P.validate(copy.deepcopy(d)))
    assert c.flow is not None
    return c


def errors(d: dict[str, Any]) -> list[tuple[str, str]]:
    p = P.validate(copy.deepcopy(d))
    return [(f.rule, f.text) for f in P.project_lint(p)[1] if f.severity == "error"]


def texts(d: dict[str, Any], rule: str, sev: str = "error") -> list[str]:
    p = P.validate(copy.deepcopy(d))
    return [f.text for f in P.project_lint(p)[1] if f.rule == rule and f.severity == sev]


def not_live(d: dict[str, Any]) -> list[str]:
    return [n.words for n in live.problems(compiled(d).flow)]


# --- the ready-made box and the lowering ----------------------------------------------------------
def test_the_functions_box_lowers_to_the_hunt_boxs_hunt_core() -> None:
    raw = FUN.read_text()
    p = P.from_json(raw)
    assert P.canonical_json(p) + "\n" == raw
    main = p.nodes[0].main
    assert [type(s).__name__ for s in main] == ["ActionStmt", "ActionStmt", "CallProc", "Stop"]
    assert P.lowered_nodes(p) == ["xmas_dun02"]
    low = P.lower_hunt_core(p)
    act_ = low.nodes[0].main[2]
    hunt_box = P.from_json(HUNT.read_text())
    runner = next(s for s in hunt_box.nodes[0].main if getattr(s, "block", "") == "dungeon_hunt")
    assert act_.block == "dungeon_hunt" and act_.params == runner.params  # the same roles
    assert act_.note == huntloop.LOWERED_NOTE
    c, ch = compiled(json.loads(raw)), compiled(json.loads(HUNT.read_text()))
    assert live.problems(c.flow) == [] and errors(json.loads(raw)) == []
    hp, hh = live.hunt_plan(c.flow, "xmas_dun02"), live.hunt_plan(ch.flow, "xmas_dun02")
    for k in ("plays", "recipes", "calls", "keys", "loop", "skill_keys", "eat_keys", "events"):
        assert getattr(hp, k) == getattr(hh, k), k
    assert hp.tick_left_out == () and P.runner_keys(p, "xmas_dun02").keys == P.runner_keys(
        hunt_box, "xmas_dun02").keys  # fmt: skip
    # the project keeps its call and its role blocks: the lowering is the compiled flow's only
    assert P.lower_hunt_core(hunt_box) is hunt_box and isinstance(p.nodes[0].main[2], type(main[2]))


def test_the_python_view_shows_the_call_the_role_blocks_and_the_tick() -> None:
    p = P.from_json(FUN.read_text())
    files = {f.path: f.text for f in pp.print_files(p)}
    assert "    hunt_loop()\n" in files["xmas_dun02/main.py"]
    assert "dungeon_hunt" not in files["xmas_dun02/main.py"]
    assert 'role_heal = "heal"\n' in files["xmas_dun02/hunt.py"]
    assert "def hunt_loop(t=False):" in files["xmas_dun02/hunt.py"]
    tick_src = files["xmas_dun02/tick.py"]
    assert "def hunt_tick():\n" + "".join(f"    {b}()\n" for b in tk.STEP_BLOCKS) in tick_src
    assert P.canonical_json(pp.parse_files(files)) == P.canonical_json(p)


def test_the_tick_table_is_one_place() -> None:
    assert len(tk.STEPS) == 20 and len(set(tk.STEP_BLOCKS)) == 20
    assert tk.OPTIONAL == ("loot", "ready", "plant")
    assert all(s.why for s in tk.STEPS if s.klass != "optional")
    assert [s.name for s in tk.STEPS[:9]] == ["begin", "sense", "hook", "vitals", "battle_log",
                                               "survive", "engage", "ui", "upkeep"]  # fmt: skip
    assert all(s.klass == "safety" for s in tk.STEPS[:9])


# --- the tick: what may be left out, and what is refused ------------------------------------------
def _tick(d: dict[str, Any], body: list[Any]) -> None:
    tab(d, "tick")["defs"][0]["body"] = body


def steps(*names: str) -> list[Any]:
    return [act(b) for b in names]


ALL = list(tk.STEP_BLOCKS)


def test_an_optional_step_may_be_left_out_and_the_plan_says_so() -> None:
    d = box(lambda d: _tick(d, steps(*[b for b in ALL if b not in ("step_loot", "step_plant")])))
    assert errors(d) == [] and not_live(d) == []
    assert live.hunt_plan(compiled(d).flow, "xmas_dun02").tick_left_out == ("loot", "plant")
    no_tick = box(lambda d: d["nodes"][0]["tabs"].remove(tab(d, "tick")))
    assert errors(no_tick) == [] and live.hunt_plan(compiled(no_tick).flow,
                                                    "xmas_dun02").tick_left_out == ()  # fmt: skip


@pytest.mark.parametrize(("why", "body", "words"), [
    ("a SAFETY step left out", [b for b in ALL if b != "step_ui"],
     "leaves out step_ui(), a SAFETY step (the UI watch; the weight; home): without it an unknown "
     "UI state would not stop the run"),
    ("a REQUIRED step left out", [b for b in ALL if b != "step_pace"],
     "leaves out step_pace(), a REQUIRED step"),
    ("a step moved", ["step_sense", "step_begin", *ALL[2:]], "step_sense() is out of its place"),
    # round 27: a step put back at the wrong place -- the words say where it goes
    ("a step dropped at the end", [*[b for b in ALL if b != "step_loot"], "step_loot"],
     "step_loot() is out of its place in hunt_tick(): it goes after step_hold() and before "
     "step_after()"),
    ("a step dropped first", ["step_survive", *[b for b in ALL if b != "step_survive"]],
     "step_survive() is out of its place in hunt_tick(): it goes after step_battle_log() and "
     "before step_engage()"),
    ("a step twice", [*ALL, "step_pace"], "step_pace() twice in hunt_tick()"),
])  # fmt: skip
def test_the_tick_refuses_each_unsafe_edit_in_words(why: str, body: list[str], words: str) -> None:
    d = box(lambda d: _tick(d, steps(*body)))
    found = texts(d, "tick_step")
    assert any(words in t for t in found), (why, found)
    assert any(words in w for w in not_live(d)), why


def test_the_tick_holds_steps_only_and_steps_stand_only_there() -> None:
    d = box(lambda d: _tick(d, [*steps(*ALL), call("heal")]))
    assert any("holds a call" in t for t in texts(d, "tick_step"))
    d2 = box(lambda d: tab(d, "keys")["defs"].append(fdef("odd", act("step_sense"))))
    assert any("step_sense() is a step of the tick: it stands only in the function hunt_tick()"
               in t for t in texts(d2, "tick_step"))  # fmt: skip
    d3 = box(lambda d: tab(d, "keys")["defs"].append(fdef("odd", call("hunt_tick"))))
    assert any("hunt_tick() is read by the hunt core, never called" in t
               for t in texts(d3, "tick_place"))  # fmt: skip
    # a tick where no hunt loop drives: the one box (the runner block, no hunt_loop)
    d4 = json.loads(XMAS.read_text())
    d4["nodes"][0]["tabs"].append({"name": "tick", "main": None, "vars": {},
                                   "defs": [fdef("hunt_tick", *steps(*ALL))]})  # fmt: skip
    assert any("is the tick of a hunt core whose hunt loop plays its steps" in t
               for t in texts(d4, "tick_place"))  # fmt: skip


# --- the hunt core's start and its roles ---------------------------------------------------------
def test_the_hunt_core_starts_only_at_one_top_level_call_in_a_map_main() -> None:
    twice = box(lambda d: d["nodes"][0]["tabs"][0]["main"].insert(2, call("hunt_loop")))
    words = "hunt_loop() starts the hunt core: a map node's main calls it once, at its top level"
    assert any(words in t for t in texts(twice, "hunt_core_call"))
    assert any(words in w for w in not_live(twice))
    nested = box(lambda d: tab(d, "keys")["defs"].append(fdef("go", call("hunt_loop"))))
    assert any(words in t for t in texts(nested, "hunt_core_call"))
    both = json.loads(HUNT.read_text())
    both["nodes"][0]["tabs"][0]["main"].insert(3, call("hunt_loop"))
    tab(both, "hunt")["defs"][0]["params"] = [{"name": "t", "default": lit(False)}]
    assert P.lowered_nodes(P.validate(both)) == []  # a node with the runner block is never lowered
    assert any(words in t for t in texts(both, "hunt_core_call"))


def test_a_missing_role_block_is_named_as_one() -> None:
    d = box(lambda d: tab(d, "hunt")["vars"].pop("role_heal"))
    got = texts(d, "hunt_roles")
    assert got and "needs its role blocks: heal (role_heal)" in got[0]
    assert not any("dungeon_hunt needs heal" in t for _, t in errors(d))  # its words, not the IR's
    assert any("needs its role blocks: heal (role_heal)" in w for w in not_live(d))
    # an optional role deleted: no role (home falls back to the item warp, as an empty field did)
    d2 = box(lambda d: tab(d, "hunt")["vars"].pop("role_eat"))
    assert texts(d2, "hunt_roles") == []
    assert "eat" not in P.lower_hunt_core(P.validate(d2)).nodes[0].main[2].params


def test_role_blocks_without_a_hunt_core_are_a_warning() -> None:
    d = json.loads(XMAS.read_text())
    d["nodes"][0]["tabs"][1]["vars"]["role_heal"] = lit("heal")
    got = texts(d, "role_block", "warning")
    assert got and "role blocks of a hunt core, but no map node's main starts one" in got[0]


def test_the_hunt_loop_may_take_a_default_now() -> None:
    d = box()
    assert texts(d, "hunt_loop_input") == []
    d2 = box(lambda d: tab(d, "hunt")["defs"][0].update(params=[]))
    assert any("def hunt_loop(t=False) when the node's main calls it" in t
               for t in texts(d2, "hunt_loop_input"))  # fmt: skip


# --- the browser's twin (services/frontend/src/lib/flow/tick.ts) ----------------------------------
TICK_TS = Path(__file__).resolve().parents[3] / "services/frontend/src/lib/flow/tick.ts"


def test_the_browsers_tick_table_is_the_engines() -> None:
    import re

    ts = TICK_TS.read_text(encoding="utf-8")
    rows = re.findall(r'^  s\("(\w+)", "(\w+)", "([^"]*)"(?:, "(\w+)")?\),$', ts, re.M)
    assert [(n, k, w, o) for n, k, w, o in rows] == [(s.name, s.klass, s.words, s.owner)
                                                     for s in tk.STEPS]  # fmt: skip

    def const(name: str) -> str:
        m = re.search(rf'^export const {name} = "([^"]*)";$', ts, re.M)
        assert m, name
        return m.group(1)

    assert const("HUNT_CALL") == huntloop.HUNT_CALL and const("ROLE_PREFIX") == huntloop.ROLE_PREFIX
    assert const("TICK_FN") == tk.TICK and const("TICK_TAB") == tk.TICK_TAB
    assert const("STEP_PREFIX") == tk.PREFIX and const("LOWERED_NOTE") == huntloop.LOWERED_NOTE
    roles = re.search(r"^export const HUNT_ROLES: readonly string\[\] = \[(.*)\];$", ts, re.M)
    req = re.search(r"^export const REQUIRED_ROLES: readonly string\[\] = \[(.*)\];$", ts, re.M)
    assert roles and req
    assert tuple(re.findall(r'"(\w+)"', roles.group(1))) == huntloop.HUNT_ROLES
    assert tuple(re.findall(r'"(\w+)"', req.group(1))) == huntloop.REQUIRED_ROLES


# --- round 26 (live-blocks.md 12.10, the reviewer's 5c review): the lint's words -----------------
def _lint(path: Path) -> list[dict[str, Any]]:
    from poring_flow.lint import default_resolver

    p = P.from_json(path.read_text())
    res = default_resolver(p.target, l3_root=Path("/nonexistent-l3"))  # no L3: the L2 bindings only
    return list(P.lint_doc(p, world=None, resolver=res)["findings"])


def test_round26_answered_bindings_in_a_learners_words_and_hunt_loop_named() -> None:
    """An answered binding: an info in a learner's words; the functions shape names hunt_loop()."""
    found = _lint(FUN)
    answered = [f for f in found if f.get("answered")]
    assert answered and all(f["severity"] == "info" for f in answered)
    for f in answered:
        for jargon in ("L2", "binding", "unsupported", "params {}", "not bound"):
            assert jargon not in f["text"] and jargon not in f["message"], f["text"]
        assert f["text"].endswith(
            "is played by the runner's own code: nothing to set up for it here"
        )
        assert f["message"] == f"{f['path']}: {f['text']}"
    by_path = {f["path"]: f["text"] for f in answered}
    assert by_path["xmas_dun02/hunt/hunt_loop.0.body.0"].startswith("find_target ")
    assert by_path["xmas_dun02/main/main.2"].startswith(f"{huntloop.HUNT_CALL}() ")
    # no block of the functions box shows the runner block: its words never name it
    assert not [f for f in found if "dungeon_hunt" in f["text"] or "dungeon_hunt" in f["message"]]
    # each finding once
    assert len({(f["path"], f["text"]) for f in found}) == len(found)
    # the old one-block shape shows the runner block: its words keep its name
    old = {f["path"]: f["text"] for f in _lint(XMAS) if f.get("answered")}
    assert old["xmas_dun02/main/main.2"].startswith("dungeon_hunt ")


# --- round 28 (live-blocks.md 12.12): which copy of a step the tick accepts -----------------------
# The SAME cases pin the browser's twin (services/frontend/src/lib/flow/tick_lock.test.ts
# PLACE_CASES, lib/flow/tick.ts tickPlaces): the editor locks only the copy the lint accepts.
_A = list(tk.STEP_BLOCKS)


def _without(b: str) -> list[str | None]:
    return [x for x in _A if x != b]


PLACE_CASES: list[tuple[str, list[str | None], list[tuple[int, str, str]]]] = [
    ("in order", list(_A), []),
    ("a second survive after pace", [*_A, "step_survive"], [(20, "extra", "")]),
    ("a second survive at the top", ["step_survive", *_A], [(0, "extra", "")]),
    ("a second survive beside it", [*_A[:6], "step_survive", *_A[6:]], [(6, "extra", "")]),
    ("loot put back at the end", [*_without("step_loot"), "step_loot"],
     [(19, "misplaced", "it goes after step_hold() and before step_after()")]),
    ("sense before begin", [_A[1], _A[0], *_A[2:]],
     [(0, "misplaced", "it goes after step_begin() and before step_hook()")]),
    ("survive only at the end", [*_without("step_survive"), "step_survive"],
     [(19, "misplaced", "it goes after step_battle_log() and before step_engage()")]),
    ("two loots, none in place", [*_without("step_loot"), "step_loot", "step_loot"],
     [(19, "misplaced", "it goes after step_hold() and before step_after()"), (20, "extra", "")]),
    ("a call in the tick", [*_A[:3], None, *_A[3:]], [(3, "other", "")]),
]  # fmt: skip


@pytest.mark.parametrize(("why", "blocks", "want"), PLACE_CASES)
def test_which_copy_the_tick_accepts(why: str, blocks: list[str | None], want: list[Any]) -> None:
    got = [(i, p.kind, p.where) for i, p in enumerate(tk.places(blocks)) if p.kind != "ok"]
    assert got == want, why


def test_a_second_safety_step_is_an_extra_copy_to_delete_and_without_it_the_tick_is_clean() -> None:
    d = box(lambda d: _tick(d, steps(*ALL, "step_survive")))
    found = texts(d, "tick_step")
    assert any("step_survive() twice in hunt_tick(): an extra copy: delete it" in t for t in found)
    assert not any("out of its place" in t for t in found)  # the original is in its place
    assert texts(box(lambda d: _tick(d, steps(*ALL))), "tick_step") == []
    # the words name the runner's order, never run(): no block shows run()
    moved = texts(box(lambda d: _tick(d, steps(*[b for b in ALL if b != "step_loot"],
                                                 "step_loot"))), "tick_step")  # fmt: skip
    assert moved and all("run()" not in t and "the runner's order" in t for t in moved)
