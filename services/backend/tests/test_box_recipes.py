"""Live blocks stage 4a (Batt 2026-11-13: "the core of the hunt: break it into functions, e.g.
attack_myst_case, attack_cookie, because in the future each monster may get a different skill or
killing technique, and on some we may not swap the knife at all"; docs/planning/live-blocks.md 2b
and 3.4; dungeon@9.51): the box decides WHICH technique per monster -- its use_model and one recipe
per monster -- and the runner still plays every step with its own code.

Offline, no game. The REAL player's hook (flow_play.HuntHook.recipe, call) answers at the lock;
the runner's side is its own code wherever it is pure enough to drive -- BareCtl on
test_dungeon_hunt's simulated client, recipe_choice / recipes_refused / box_model_refused /
recipe_values -- wired exactly as run() wires them (its AST is checked below), and a fake hunt
loop for the whole run."""

from __future__ import annotations

import ast
import copy
import importlib.util
import inspect
import json
import sys
import textwrap
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_hunt as dh  # noqa: E402
import flow_play as fp  # noqa: E402

from poring_flow import live  # noqa: E402
from poring_flow import project as pj  # noqa: E402
from poring_flow import recipes as rc  # noqa: E402


def _load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"_s4_{name}", Path(__file__).with_name(name))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TBF = _load("test_box_functions.py")  # stage 3's fakes (FakeIO, prep, refused, the player)
TDH = TBF.TDH  # test_dungeon_hunt's simulated client
FIX = TBF.FIX
B4 = FIX / "project_xmas_dun02.json"  # the one box (stage 4a): use_model + the monsters tab
B3 = FIX / "project_xmas_dun02_stage3.json"  # the box as stage 3 left it
B2 = FIX / "project_xmas_dun02_stage2.json"
TODAY = list(rc.KNIFE_SHAPE)
PLAIN = list(rc.PLAIN_SHAPE)
SPECIES = ["mystcase", "cruiser", "cookie", "cookie_xmas"]
STAGE3_ROLES = {"knife_on": "opener", "knife_back": "armed", "home": "home",
                "respawn": "save_point", "respawn_confirm": "save_point"}  # fmt: skip
T = {"kind": "var", "name": "t"}


def prim(block: str) -> dict[str, Any]:
    p = next(x for x in [("strike", "combat.attack_target", 60.0),
                         ("wait_steal", "core.wait_steal", 10.0),
                         ("wait_kill", "core.wait_kill", 120.0),
                         ("loot", "loot.pick_up", 30.0)] if x[0] == block)  # fmt: skip
    return {"kind": "action", "block": block, "concept": p[1], "params": {"target": T},
            "timeout_s": p[2], "on_fail": "stop", "outcome_to": None, "note": None}  # fmt: skip


def recipe(species: str, steps: list[str], priority: Any = 1) -> dict[str, Any]:
    params: list[Any] = [{"name": "t", "default": None}]
    if priority is not None:
        params.append({"name": "priority", "default": {"kind": "lit", "value": priority}})
    body = [TBF.call(s) if s in ("knife_on", "knife_back") else prim(s) for s in steps]
    return {"name": f"attack_{species}", "params": params, "varargs": None, "kwargs": None,
            "body": body, "on": None}  # fmt: skip


def box(*defs: dict[str, Any] | None) -> dict[str, Any]:
    """The one box (its time box under the run's maximum), its monsters tab's recipes replaced
    when ``defs`` are given."""
    d = TBF.box(B4)
    if defs:
        TBF.tab_of(d, rc.MONSTERS_TAB)["defs"] = [x for x in defs if x is not None]
    return d


def without_4a(d: dict[str, Any]) -> dict[str, Any]:
    """The box with its use_model and its monsters tab taken out (stage 3's shape)."""
    d = copy.deepcopy(d)
    tabs = d["nodes"][0]["tabs"]
    tabs.remove(TBF.tab_of(d, rc.MONSTERS_TAB))
    main = tabs[0]["main"]
    main.remove(next(s for s in main if s.get("block") == rc.MODEL_BLOCK))
    return d


class _Hook:
    def survive(self, view: Any, press: Any) -> str | None:
        return None

    def call(self, role: str, why: str, press: Any, click: Any = None) -> str | None:
        return None

    def recipe(self, species: str | None, why: str) -> dict[str, Any] | None:
        return None


# --- the box and what it hands over ---------------------------------------------------------------
def test_the_one_box_plays_todays_technique_through_its_recipes_and_b3_stays_stage_3(
    tmp_path: Path,
) -> None:
    c, found = pj.project_lint(pj.from_json(B4.read_text()))
    assert [f.text for f in found if f.severity == "error"] == []
    assert c.flow is not None and live.problems(c.flow) == []
    p4 = TBF.prep(tmp_path, box()).runners["xmas_dun02"]
    p3 = TBF.prep(tmp_path, TBF.box(B3)).runners["xmas_dun02"]
    assert p4.plays == p3.plays | {"model", "recipes"}
    assert p4.model_doc is not None and p4.model_doc["id"] == "xmas02"
    assert {s: r.doc() for s, r in p4.recipes.items()} == {
        s: {"function": f"attack_{s}", "steps": TODAY, "knife": True, "priority": 1.0}
        for s in SPECIES
    } and p4.default_species == ()
    # the same runner argv (the same five keys, the same config): only the box's arguments differ
    assert p4.argv("x", None, None) == p3.argv("x", None, None)
    k4, k3 = p4.box_kwargs(), p3.box_kwargs()
    assert {k: v for k, v in k4.items() if k not in ("box_model", "box_recipes")} == {
        **k3, "box_plays": sorted(p3.plays | {"model", "recipes"})}  # fmt: skip
    assert k4["box_model"] == p4.model_doc and sorted(k4["box_recipes"]) == sorted(SPECIES)
    assert (p3.model_doc, dict(p3.recipes)) == (None, {})
    assert dh.RECIPE_SHAPES == rc.SHAPES  # the runner plays exactly the engine's two orders


def test_a_box_without_use_model_or_monsters_calls_run_exactly_as_stage_3(tmp_path: Path) -> None:
    seen: list[dict[str, Any]] = []

    def run_fn(a: Any, *, hook: Any = None, session: Any = None, **kw: Any) -> int:
        seen.append(kw)
        hook.event({"kind": "run_end", "reason": "time_box"}, 0.0)
        return 0

    stage3 = {"box_plays": TBF.STAGE3_PLAYS, "box_roles": STAGE3_ROLES}
    for name, d, want in (("b2", TBF.box(B2), {"box_plays": TBF.STAGE2_PLAYS}),
                          ("b3", TBF.box(B3), stage3),
                          ("b4-less", without_4a(box()), stage3)):  # fmt: skip
        dd = tmp_path / name
        dd.mkdir()
        fp.play(TBF.prep(dd, d), TBF.FakeIO(), label="k", stop_file=None, demo=dd,
                checker=lambda _p, _i: {"items": [{"id": "cell", "ok": True, "words": "-"}],
                                        "ok": True},
                hunt=fp.HuntCore("k", None, run_fn=run_fn))  # fmt: skip
        assert seen[-1] == want, name  # byte for byte stage 3's (2's) run() call
    # the stage-3 box written in the stage-4 file is the stage-3 file itself
    assert pj.canonical_json(pj.validate(without_4a(json.loads(B4.read_text())))) == (
        pj.canonical_json(pj.from_json(B3.read_text()).model_copy(update={
            "description": json.loads(B4.read_text())["description"]})))  # fmt: skip


# --- the lock: the hook answers with the species' recipe, the runner plays it ---------------------
def recipe_ctl(tmp_path: Path, d: dict[str, Any], ready: bool = False) -> tuple[
        Any, Any, Counter[str], list[dict[str, Any]], fp.LivePlayer, Any]:  # fmt: skip
    """run()'s wiring with the box's recipes and its Knife swap (strike -> bare.before_strike(...,
    recipe) -> recipe_knife -> recipe_choice(hook_recipe(...), box_recipes[species])) on the
    simulated client; the box's knife bodies press F4 / F5 through the runner's own presses."""
    sim = TDH._OpenerSim()
    pl, hook, _io = TBF.player(tmp_path, d, sim)
    plan = pl.prep.runners["xmas_dun02"]
    box_recipes = plan.box_kwargs()["box_recipes"]
    own = {"F4": sim.opener, "F5": sim.press}

    def port(code: str, why: str) -> str | None:
        do = own.get(code)
        if do is None:
            return None
        do(why)
        return "knife"

    def box_call(role: str, why: str) -> bool:
        return dh.hook_call(hook, role, why, port) is None

    bio = sim.io()
    bio.opener = lambda why: box_call("knife_on", why)
    bio.press = lambda why: sim.press(why) if why == "safety" else box_call("knife_back", why)
    counts: Counter[str] = Counter()
    evs: list[dict[str, Any]] = []
    ctl = dh.BareCtl(bio, TDH._armed_ref(), counts, evs.append, TDH._Stop,
                     opener=TDH._opener_read(), ready=ready)  # fmt: skip

    def recipe_knife(species: str | None, by: str) -> bool:  # run()'s closure, its logic
        knife, _fn, odd = dh.recipe_choice(dh.hook_recipe(hook, species, by),
                                           box_recipes.get(species or ""))  # fmt: skip
        counts["recipe_mismatch"] += int(odd)
        return knife

    ctl.recipe_knife = recipe_knife  # type: ignore[attr-defined]  # (the test's handle)
    return ctl, sim, counts, evs, pl, hook


def strike(ctl: Any, species: str | None, aim: Any = None, by: str = "box") -> bool:
    return bool(ctl.before_strike(by, 0.9, aim, lambda: ctl.recipe_knife(species, by)))


def test_the_lock_asks_the_box_with_the_species_and_plays_todays_knife_swap(tmp_path: Path) -> None:
    ctl, sim, counts, evs, pl, hook = recipe_ctl(tmp_path, box())
    aims: list[float] = []
    assert strike(ctl, "mystcase", lambda: aims.append(sim.t) is None)
    assert [k for k, *_ in sim.log] == ["opener"] and aims and not ctl.st.armed  # as stage 3
    assert strike(ctl, "mystcase")  # struck again with no lock yet: its decision was taken
    assert hook.res.recipes == 1 and [k for k, *_ in sim.log] == ["opener"]
    ctl.struck()
    sim.lines.append({"colour": "cyan"})
    ctl.tick(sim.t, True, True, sim.frame(), 0.9)
    assert sim.log[-1] == ("press", "box knife_back (cyan)") and ctl.st.armed
    assert counts["recipe_mismatch"] == 0
    recs = [e for e in TBF.records(pl) if e["kind"] == "recipe"]
    assert recs == [{**recs[0], "kind": "recipe", "species": "mystcase", "why": "box",
                     "in": "hunt", "function": "attack_mystcase",
                     "node": "xmas_dun02/monsters/attack_mystcase", "steps": TODAY,
                     "knife": True}]  # fmt: skip
    assert [e["role"] for e in TBF.records(pl) if e["kind"] == "call"] == ["knife_on", "knife_back"]


def test_a_recipe_without_knife_on_strikes_that_monster_without_the_swap(tmp_path: Path) -> None:
    d = box(recipe("mystcase", TODAY), recipe("cookie", PLAIN))
    ctl, sim, counts, evs, pl, _hook = recipe_ctl(tmp_path, d)
    aims: list[int] = []
    assert strike(ctl, "cookie", lambda: aims.append(1) is None)
    assert sim.log == [] and ctl.st.armed and aims == []  # no press at all: struck armed
    assert counts["bare_recipe_no_knife"] == 1 and evs[-1]["what"] == "recipe"
    ctl.struck()
    sim.lines.append({"colour": "cyan"})
    ctl.tick(sim.t, True, True, sim.frame(), 0.9)
    assert sim.log == [] and ctl.st.armed  # nothing to swap back
    ctl.tick(sim.t, False, True, sim.frame(), 0.9)  # the kill: the lock went
    # the next target is a Myst Case: today's swap again
    assert strike(ctl, "mystcase")
    assert [k for k, *_ in sim.log] == ["opener"] and not ctl.st.armed
    assert pl.keys_sent == ["F4"]


def test_bare_ready_a_no_knife_monster_gets_the_dagger_first_then_the_knife_at_the_next_idle(
    tmp_path: Path,
) -> None:
    d = box(recipe("mystcase", TODAY), recipe("cookie", PLAIN))
    ctl, sim, counts, evs, pl, _hook = recipe_ctl(tmp_path, d, ready=True)
    assert ctl.ready_tick(sim.t, True, True, 0.9) == "swap"  # idle: the Knife on (F4)
    assert [k for k, *_ in sim.log] == ["opener"] and not ctl.st.armed
    aims: list[float] = []
    assert strike(ctl, "cookie", lambda: aims.append(sim.t) is None)
    assert sim.log[-1] == ("press", "box knife_back (recipe)") and ctl.st.armed
    assert aims and counts["bare_equip_recipe"] == 1  # the dagger read back, THEN the aim
    assert [e.get("swap") for e in evs if e.get("what") == "recipe"] == [True]
    ctl.struck()
    ctl.tick(sim.t, False, True, sim.frame(), 0.9)
    ctl.tick(sim.t, False, False, sim.frame(), 0.9)  # the fight over, armed
    assert ctl.ready_tick(sim.t, True, True, 0.9) == "swap"  # the next idle: the Knife again
    assert [k for k, *_ in sim.log][-1] == "opener" and not ctl.st.armed
    # a Myst Case now: struck bare at once (--bare-ready's own), as today
    n = len(sim.log)
    assert strike(ctl, "mystcase") and sim.log[n:] == [] and counts["bare_ready_strike"] == 1
    # and the aim lost after the recipe's dagger: no click
    d2 = box(recipe("cookie", PLAIN))
    (tmp_path / "b").mkdir()
    ctl2, sim2, counts2, _e2, _pl2, _h2 = recipe_ctl(tmp_path / "b", d2, ready=True)
    assert ctl2.ready_tick(sim2.t, True, True, 0.9) == "swap"
    assert not strike(ctl2, "cookie", lambda: False) and counts2["bare_aim_lost"] == 1


def test_no_function_for_a_species_or_an_unknown_one_is_the_runners_own_recipe(
    tmp_path: Path,
) -> None:
    d = box(recipe("mystcase", PLAIN))
    ctl, sim, counts, _evs, pl, hook = recipe_ctl(tmp_path, d)
    assert pl.prep.runners["xmas_dun02"].default_species == ("cruiser", "cookie", "cookie_xmas")
    assert strike(ctl, "cookie")  # no attack_cookie: the runner's own (the Knife swap)
    assert [k for k, *_ in sim.log] == ["opener"]
    ctl.tick(sim.t, False, False, sim.frame(), 0.9)
    ctl.tick(sim.t, False, False, sim.frame(), 0.9)
    n = len(sim.log)
    assert strike(ctl, None, by="scan")  # a ring scan's strike: no box, no species
    assert counts["recipe_mismatch"] == 0 and hook.res.recipes == 2
    recs = [(e["species"], e["function"], e.get("default")) for e in TBF.records(pl)
            if e["kind"] == "recipe"]  # fmt: skip
    assert recs == [("cookie", None, True), (None, None, True)]
    assert sim.log[n:] == [] or [k for k, *_ in sim.log[n:]][0] in ("press", "opener")


def test_recipe_choice_plays_only_the_plans_own_recipe() -> None:
    mc = {"function": "attack_mystcase", "steps": TODAY, "knife": True, "priority": 1.0}
    ck = {"function": "attack_cookie", "steps": PLAIN, "knife": False, "priority": None}
    assert dh.recipe_choice(mc, mc) == (True, "attack_mystcase", False)
    assert dh.recipe_choice(ck, ck) == (False, "attack_cookie", False)
    assert dh.recipe_choice(None, None) == (True, None, False)  # no function: the runner's own
    # a disagreement between the hook and the run's plan: the runner's own, counted
    assert dh.recipe_choice(None, ck) == (True, None, True)
    assert dh.recipe_choice(ck, None) == (True, None, True)
    assert dh.recipe_choice({**ck, "function": "attack_x"}, ck) == (True, None, True)
    assert dh.hook_recipe(None, "cookie", "box") is None  # the CLI: no hook, never asked


# --- the runner refuses, before any input, what it cannot play ------------------------------------
def test_recipes_refused_names_each_refusal() -> None:
    model = {
        "id": "xmas02",
        "file": "xmas02gb-last-736x1280.onnx",
        "sha256": "b22d972b714f",
        "maps": ["xmas_dun02"],
        "status": "live",
        "kind": "detector",
        "strikes": SPECIES,
    }
    mc = {"function": "attack_mystcase", "steps": TODAY, "knife": True, "priority": 1.0}
    ok = {"knife_swap": True, "value_target": True}

    def why(plays: list[str], m: Any = model, r: Any = None, hook: Any = _Hook(),
            **kw: Any) -> str | None:  # fmt: skip
        return dh.recipes_refused(plays, hook, m, r, **{**ok, **kw})

    assert why(["model", "recipes"], r={"mystcase": mc}) is None
    assert why(["model"]) is None and why([], m=None) is None  # use_model alone; nothing
    assert "goes with box_model" in str(why(["model"], m=None))
    assert "goes with box_model" in str(why([]))
    assert "goes with box_recipes" in str(why(["model", "recipes"]))
    assert "without its use_model" in str(why(["recipes"], m=None, r={"mystcase": mc}))
    assert "not monsters the runner strikes" in str(why(["model", "recipes"],
                                                        r={"garm_baby": mc}))  # fmt: skip
    skill = {**mc, "steps": [*TODAY[:4], "use_skill", *TODAY[4:]]}
    assert "use_skill is 4b" in str(why(["model", "recipes"], r={"mystcase": skill}))
    assert "knife flag" in str(why(["model", "recipes"], r={"mystcase": {**mc, "knife": False}}))
    assert "swaps no Knife" in str(why(["model", "recipes"], r={"mystcase": mc},
                                       knife_swap=False))  # fmt: skip
    plain = {**mc, "steps": PLAIN, "knife": False}
    assert "nothing for them to decide" in str(why(["model", "recipes"], r={"mystcase": plain},
                                                   knife_swap=False))  # fmt: skip
    heavy = {**mc, "priority": 3}
    assert "--value-target is off" in str(why(["model", "recipes"], r={"mystcase": heavy},
                                              value_target=False))  # fmt: skip
    assert why(["model", "recipes"], r={"mystcase": mc}, value_target=False) is None  # 1: as is
    assert "not a number in (0, 10]" in str(
        why(["model", "recipes"], r={"mystcase": {**mc, "priority": 11}})
    )
    assert "hook.recipe" in str(why(["model", "recipes"], r={"mystcase": mc},
                                    hook=TBF._Hook()))  # fmt: skip
    # box_plays_refused carries them (and stage 3's own refusals stay)
    kw: dict[str, Any] = {"heal_candy": False, "boss_walk": False, "bosses": ("Stormy Knight",)}
    assert dh.box_plays_refused([*TBF.STAGE3_PLAYS, "model", "recipes"], _Hook(),
                                roles=STAGE3_ROLES, model=model, recipes={"mystcase": mc},
                                **kw) is None  # fmt: skip
    assert "goes with box_recipes" in str(dh.box_plays_refused(["recipes"], _Hook(), **kw))


def test_box_model_refused_takes_only_the_model_the_detector_loads_on_the_map() -> None:
    import unit_detector as ud

    xmas = live.hunt_plan(
        pj.compile_project(pj.from_json(B4.read_text())).flow, "xmas_dun02"
    ).model_doc  # type: ignore[arg-type]
    assert xmas is not None
    assert dh.box_model_refused(None, "xmas_dun02") is None  # no use_model: nothing to check
    assert dh.box_model_refused(xmas, "xmas_dun02") is None  # the map's own model
    assert dh.box_model_refused(xmas, "xmas_dun02", detector="cpu") is None
    mm = ud.MAP_MODELS["xmas_dun02"]
    assert xmas["file"] == mm.onnx and mm.sha256.startswith(xmas["sha256"])
    cases = [
        ({**xmas, "status": "not_adopted"}, {}, "not a live model"),
        ({**xmas, "kind": "boss_recognizer"}, {}, "not a detector"),
        ({**xmas, "maps": ["gef_fild10"]}, {}, "trained for gef_fild10, not xmas_dun02"),
        (xmas, {"boxes": False}, "no box watcher"),
        (xmas, {"choice": "v1"}, "--box-model is v1"),
        ({**xmas, "sha256": "000000000000"}, {}, "another model than the map's own is a follow-up"),
        ({**xmas, "file": "v1png-last-736x1280.onnx"}, {}, "is not the model the runner's box"),
        ({**xmas, "sha256": "b22d"}, {}, "is not the model"),  # a prefix too short to pin
    ]
    for m, kw, words in cases:
        got = dh.box_model_refused(m, "xmas_dun02", **kw)
        assert got is not None and words in got, (words, got)
    # v1 names every map: on xmas_dun02 it is not the file the runner loads there (follow-up)
    v1 = {
        "id": "v1",
        "file": "v1png-last-736x1280.onnx",
        "sha256": "32b448a1d197",
        "maps": [],
        "status": "live",
        "kind": "detector",
        "strikes": [],
    }
    assert "follow-up" in str(dh.box_model_refused(v1, "xmas_dun02"))
    assert dh.box_model_refused(v1, "prt_fild08") is None  # a map without its own: v1 IS it


def test_priority_weighs_the_value_target_only_when_it_is_not_one() -> None:
    values = {"mystcase": 262.0, "cookie": 100.0, "*": 140.0}
    one = {"mystcase": {"priority": 1.0}, "cookie": {"priority": None}}
    assert dh.recipe_values(values, one) == values  # today's: the values as they are
    assert dh.recipe_values(values, {"cookie": {"priority": 3}}) == {**values, "cookie": 300.0}
    assert dh.recipe_values(values, {"cruiser": {"priority": 0.5}}) == {**values, "cruiser": 70.0}


# --- the whole run through the player: a fake hunt loop -------------------------------------------
class LockLoop:
    """dungeon_hunt.run at its LOCK, as run() asks (its AST is checked below): one target per
    species in ``targets`` (None: a strike that knows no species), each asking the hook once."""

    def __init__(self, targets: list[str | None]) -> None:
        self.targets = targets
        self.kw: dict[str, Any] = {}
        self.knife: list[tuple[str | None, bool]] = []

    def __call__(self, a: Any, *, hook: Any = None, session: Any = None, **kw: Any) -> int:
        self.kw = kw
        plan = dict(kw.get("box_recipes") or {})
        hook.event({"kind": "run_start", "map": "xmas_dun02"}, 0.0)
        for sp in self.targets:
            knife, _fn, odd = dh.recipe_choice(dh.hook_recipe(hook, sp, "box"),
                                               plan.get(sp or ""))  # fmt: skip
            assert not odd
            self.knife.append((sp, knife))
        hook.event({"kind": "run_end", "reason": "time_box", "counts": {}}, 1.0)
        return 0


def test_the_whole_box_through_the_player_asks_once_a_target(tmp_path: Path) -> None:
    loop = LockLoop(["mystcase", "cookie", None, "cookie_xmas"])
    d = box(recipe("mystcase", TODAY), recipe("cookie", PLAIN), recipe("cookie_xmas", TODAY))
    demo = tmp_path / "demo"
    demo.mkdir()
    fp.play(TBF.prep(tmp_path, d), TBF.FakeIO(), label="s4", stop_file=None, demo=demo,
            checker=lambda _p, _i: {"items": [{"id": "cell", "ok": True, "words": "-"}],
                                    "ok": True},
            hunt=fp.HuntCore("s4", None, run_fn=loop))  # fmt: skip
    assert loop.knife == [("mystcase", True), ("cookie", False), (None, True),
                          ("cookie_xmas", True)]  # fmt: skip
    assert loop.kw["box_model"]["id"] == "xmas02"
    assert sorted(loop.kw["box_recipes"]) == ["cookie", "cookie_xmas", "mystcase"]
    assert {"model", "recipes"} <= set(loop.kw["box_plays"])
    (s,) = list(demo.iterdir())
    ev = [json.loads(x) for x in (s / "events.jsonl").read_text().splitlines()]
    start = next(e for e in ev if e["kind"] == "hunt_start")
    assert start["box_model"] == "xmas02" and start["default_species"] == ["cruiser"]
    end = next(e for e in ev if e["kind"] == "hunt_end")
    assert end["recipes"] == 4
    assert [e["species"] for e in ev if e["kind"] == "recipe"] == ["mystcase", "cookie", None,
                                                                    "cookie_xmas"]  # fmt: skip


def test_the_player_plan_shows_the_model_and_the_recipes(tmp_path: Path) -> None:
    doc = TBF.prep(tmp_path, box()).doc()["runners"]["xmas_dun02"]
    assert doc["box_model"]["id"] == "xmas02" and sorted(doc["box_recipes"]) == sorted(SPECIES)
    assert doc["default_species"] == []
    doc3 = TBF.prep(tmp_path, TBF.box(B3)).doc()["runners"]["xmas_dun02"]
    assert "box_model" not in doc3 and "box_recipes" not in doc3


def test_use_model_plays_no_input_in_the_player(tmp_path: Path) -> None:
    seen: list[dict[str, Any]] = []

    def run_fn(a: Any, *, hook: Any = None, session: Any = None, **kw: Any) -> int:
        seen.append(kw)
        hook.event({"kind": "run_end", "reason": "time_box"}, 0.0)
        return 0

    io_ = TBF.FakeIO()
    fp.play(TBF.prep(tmp_path, box()), io_, label="k", stop_file=None, demo=tmp_path,
            checker=lambda _p, _i: {"items": [{"id": "cell", "ok": True, "words": "-"}],
                                    "ok": True},
            hunt=fp.HuntCore("k", None, run_fn=run_fn))  # fmt: skip
    assert not [o for o in io_.out if o[0] == "tap"]  # use_model, the save point: no input
    (s,) = [p for p in tmp_path.iterdir() if p.is_dir() and "play" in p.name]
    blocks = [e["what"] for e in map(json.loads, (s / "events.jsonl").read_text().splitlines())
              if e["kind"] == "block"]  # fmt: skip
    assert blocks[:3] == ["assert_save_point", "use_model", "dungeon_hunt"]


# --- the runner: its own technique, bypassed only where the box decides ---------------------------
def _src(f: Any) -> ast.AST:
    return ast.parse(textwrap.dedent(inspect.getsource(f)))


def _fn(name: str, tree: ast.AST | None = None) -> ast.FunctionDef:
    got = [n for n in ast.walk(tree or _src(dh.run)) if isinstance(n, ast.FunctionDef)
           and n.name == name]  # fmt: skip
    assert len(got) == 1, name
    return got[0]


def _calls(tree: ast.AST, name: str) -> list[ast.Call]:
    return [c for c in ast.walk(tree) if isinstance(c, ast.Call) and ast.unparse(c.func) == name]


def test_the_runner_asks_the_box_only_at_the_lock_and_only_with_its_recipes() -> None:
    tree = _src(dh.run)
    st = _fn("strike", tree)
    body = [ast.unparse(x) for x in st.body[1:]]  # past the docstring
    bare_if = next(x for x in st.body if isinstance(x, ast.If) and ast.unparse(x.test) ==
                   "bare is not None")  # fmt: skip
    got = [ast.unparse(x) for x in bare_if.body]
    assert got[1] == "rcp_ = (lambda: recipe_knife(species, by)) if box_recipe_on else None"
    assert "bare.before_strike(by, hp_b, lambda: hover(u, v)['verdict'] == 'sword', rcp_)" in got[2]
    assert body  # the rest of strike() is its own
    # recipe_knife is asked from strike's lambda alone, and asks the hook through hook_recipe
    callers = {f.name for f in ast.walk(tree) if isinstance(f, ast.FunctionDef)
               and f.name not in ("recipe_knife", "run") and _calls(f, "recipe_knife")}  # fmt: skip
    assert callers == {"strike"}
    rk = ast.unparse(_fn("recipe_knife", tree))
    assert "recipe_choice(hook_recipe(hook, species_, by_), box_recipes_.get(species_ or ''))" in rk
    # the strikes that know a species: the box path's two (box_target's box) and the queue's pick
    with_sp = sorted(ast.unparse(c) for c in _calls(tree, "strike") if len(c.args) == 5)
    assert with_sp == ["strike(u_b, v_b, rel_b, 'box', box_sp[0])",
                       "strike(u_d, v_d, rel_d, 'box', box_sp[0])",
                       "strike(u_p, v_p, rel_p, 'queue', box_species(b_))"]  # fmt: skip
    assert all(len(c.args) == 4 for c in _calls(tree, "strike") if len(c.args) != 5)
    # box_target sets the species of the box it struck, and nothing else sets it
    sets = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
            and ast.unparse(n.targets[0]) == "box_sp[0]"]  # fmt: skip
    bt = _fn("box_target", tree)
    assert len(sets) == 2 and all(s in list(ast.walk(bt)) for s in sets)
    # the priority weighs the values only with recipes, at the start
    w = [n for n in ast.walk(tree) if isinstance(n, ast.If)
         and ast.unparse(n.test) == "box_recipe_on and vt_values"]  # fmt: skip
    assert len(w) == 1 and ast.unparse(w[0].body[0]) == (
        "vt_values = recipe_values(vt_values, box_recipes_)")  # fmt: skip


def test_bare_ctl_decides_the_knife_only_through_the_recipe_at_its_own_decision_point() -> None:
    bs = _fn("before_strike", _src(dh.BareCtl))
    lines = [ast.unparse(x) for x in bs.body[1:]]
    i = lines.index("if self.tgt['phase'] or self.pending is not None:\n    return True")
    assert lines[i + 1] == ("if recipe is not None and (not recipe()):\n"
                            "    return self._no_knife(by, aim)")  # fmt: skip
    assert lines[i + 2].startswith("if self.ready and (not self.st.armed)")  # today's, unchanged
    assert inspect.signature(dh.BareCtl.before_strike).parameters["recipe"].default is None
    # _no_knife's only swap is the runner's own equip ("recipe"), read back
    nk = ast.unparse(_fn("_no_knife", _src(dh.BareCtl)))
    assert "self.equip('recipe')" in nk and "self.unequip" not in nk and "opener" not in nk


def test_boxwatch_near_names_the_species_of_the_box_it_returns() -> None:
    import time
    from types import SimpleNamespace as NS_

    w = dh.BoxWatch.__new__(dh.BoxWatch)
    w.lock = dh.threading.Lock()
    w.n_self = w.n_skip = 0
    fx, fy = dh.FOOT_PX
    near = NS_(x0=fx + 60, y0=fy - 20, x1=fx + 100, y1=fy + 40, species="cookie", cls="monster")
    far = NS_(x0=fx + 200, y0=fy - 20, x1=fx + 240, y1=fy + 40, species="mystcase", cls="monster")
    w.last = (time.monotonic(), [far, near])
    assert w.near(dh.FOOT_PX, 500, 5.0) == (near.x0, near.y0, near.x1, near.y1)
    assert w.last_species == "cookie"  # the nearest, as before
    got = w.near(dh.FOOT_PX, 500, 5.0, values={"mystcase": 262.0, "cookie": 20.0, "*": 100.0})
    assert got == (far.x0, far.y0, far.x1, far.y1) and w.last_species == "mystcase"
    w.last = (time.monotonic(), [])
    assert w.near(dh.FOOT_PX, 500, 5.0) is None and w.last_species is None


def test_the_start_refuses_before_any_input_and_records_the_box() -> None:
    src = inspect.getsource(dh.run)
    i_bm = src.index('raise SystemExit(f"dungeon@{BOX_RECIPES_VERSION} refused: {why_bm}")')
    assert i_bm < src.index("typed: list[str] = []")  # before the setup types anything
    assert src.index("model=box_model_,") < i_bm and "recipes=box_recipes_," in src
    tree = _src(dh.run)
    rec = next(n for n in ast.walk(tree) if isinstance(n, ast.Call)
               and ast.unparse(n.func) == "ev" and "'choice'" in ast.unparse(n)
               and "'box_model'" in ast.unparse(n))  # fmt: skip
    assert "'choice': a.box_model if box_model_ is None else 'box'" in ast.unparse(rec)
    assert "if box_model_ is not None and boxes.model['onnx'] != box_model_['file']" in (
        ast.unparse(tree))  # fmt: skip


def test_the_cli_and_the_old_run_path_are_unchanged_by_4a() -> None:
    sig = inspect.signature(dh.run)
    assert sig.parameters["box_model"].default is None
    assert sig.parameters["box_recipes"].default is None
    assert "return run(a)" in inspect.getsource(dh.main)  # no hook, no box
    assert dh.VERSION == "dungeon@8.7" and dh.BOX_RECIPES_VERSION == live.VERSION == "9.51"
    assert rc.VERSION == dh.BOX_RECIPES_VERSION and fp.VERSION == live.VERSION
    import runner_flow_export as rfe

    assert "BOX_RECIPES_VERSION" in rfe.NOT_FEATURES
    assert rfe.feature_version(dh) != f"dungeon@{dh.BOX_RECIPES_VERSION}"
    # the old Run path builds no box arguments at all
    plan = fp.RunnerPlan("xmas_dun02", "xmas_dun02_rogue", {}, {})
    assert plan.box_kwargs() == {}


@pytest.mark.parametrize("ends", ["opener", "armed"])
def test_a_no_knife_recipe_with_either_knife_answer_presses_nothing(ends: str) -> None:
    sim = TDH._OpenerSim()
    counts: Counter[str] = Counter()
    evs: list[dict[str, Any]] = []
    ctl = dh.BareCtl(sim.io(), TDH._armed_ref(), counts, evs.append, TDH._Stop,
                     opener=TDH._opener_read(), opener_ends=ends)  # fmt: skip
    assert ctl.before_strike("box", 0.9, None, lambda: False) and sim.log == []
    assert ctl.st.armed and counts["bare_recipe_no_knife"] == 1
