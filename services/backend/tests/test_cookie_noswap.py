"""live-blocks 16 (Batt 2026-11-15 ~13:0x: "Test it, and make it work too"; 14.8): the NO-SWAP box
-- the one box with attack_cookie and attack_cookie_xmas `strike(t); wait_kill(t); loot(t)` -- is
the one box but those two recipes, loads and prepares as a Run does, and its recipes PLAY as
written.

Offline, no game. The REAL player's hook, prepared from the fixture, answers at the lock; the
runner's side is its own BareCtl on test_dungeon_hunt's simulated client with the Run config's
Knife (the opener on F4, --bare-ready, the popup cue), wired as run() wires it (test_box_recipes
checks that wiring's AST; here run()'s `recipe` record is checked against its source). At a lock on
the two cookies the runner presses no Knife opener and waits for no steal cue (nor the Knife's time
box); with the Knife already on (--bare-ready) it puts the dagger on first, as live-blocks 2b says;
mystcase and cruiser keep the Knife swap and its steal. The records it writes are the ones
scripts/stage6_ab.py's score counts by the species at the lock (locks_of)."""

from __future__ import annotations

import importlib.util
import inspect
import json
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_hunt as dh  # noqa: E402
import flow_play as fp  # noqa: E402
import stage6_ab as ab  # noqa: E402

from poring_flow import live  # noqa: E402
from poring_flow import project as pj  # noqa: E402
from poring_flow import recipes as rc  # noqa: E402


def _load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"_s6_{name}", Path(__file__).with_name(name))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TBF = _load("test_box_functions.py")  # stage 3's fakes (the player, the records)
TDH = TBF.TDH  # test_dungeon_hunt's simulated client
FIX = TBF.FIX
ONE = FIX / "project_xmas_dun02.json"
NOSWAP = FIX / "project_xmas_dun02_cookie_noswap.json"
FUN = FIX / "project_xmas_dun02_functions.json"  # the ready-made box (functions in tabs, 5c)
FUN_NOSWAP = FIX / "project_xmas_dun02_functions_cookie_noswap.json"  # round 29: its twin
NODE = "xmas_dun02"
KNIFE, PLAIN = list(rc.KNIFE_SHAPE), list(rc.PLAIN_SHAPE)


def _prep(path: Path) -> fp.RunnerPlan:
    got = fp.prepare(path.read_text(), NODE, 0)  # no configured maximum (Batt 2026-11-19)
    assert isinstance(got, fp.Prepared), got
    return got.runners[NODE]


# --- the box: the one box but two recipes; it loads, lints and prepares as a Run does ------------
def test_the_no_swap_box_is_the_one_box_but_its_two_cookie_recipes(tmp_path: Path) -> None:
    text = NOSWAP.read_text()
    assert text == pj.canonical_json(pj.from_json(text)) + "\n"  # a canonical fixture, as its twin
    c, found = pj.project_lint(pj.from_json(text))
    assert [f.text for f in found if f.severity == "error"] == []
    one_c, one_found = pj.project_lint(pj.from_json(ONE.read_text()))
    assert sorted(f.rule for f in found) == sorted(f.rule for f in one_found)  # the same findings
    assert c.flow is not None and live.problems(c.flow) == []  # the backend's not_live: none
    assert ab.box_difference(json.loads(ONE.read_text()), json.loads(text)) is None
    # the Run's keys (the backend's keys_refused) and the runner: the same argv, the same run()
    # arguments but box_recipes, the same settings
    assert pj.runner_keys(pj.from_json(text), NODE).keys == pj.runner_keys(
        pj.from_json(ONE.read_text()), NODE).keys  # fmt: skip
    b, n = _prep(ONE), _prep(NOSWAP)
    # under the harness's time box (stage6_ab: --max-s = minutes * 60) the two commands are one:
    # since 2026-11-19 the ready-made B holds no time limit (0), the pinned C its old 120 min
    assert n.argv("L", Path("/S"), 45.0) == b.argv("L", Path("/S"), 45.0)
    kb, kn = b.box_kwargs(), n.box_kwargs()
    assert {k: v for k, v in kn.items() if k != "box_recipes"} == {
        k: v for k, v in kb.items() if k != "box_recipes"}  # fmt: skip
    untimed = lambda v: {k: x for k, x in v.items() if k != "minutes"}  # noqa: E731
    assert (n.keys, untimed(n.vals), n.loop, n.default_species) == (
        b.keys, untimed(b.vals), None, ())  # fmt: skip
    assert (n.vals["minutes"], b.vals["minutes"]) == (120, 0)
    assert {sp: (r["steps"], r["knife"], r["priority"]) for sp, r in kn["box_recipes"].items()} == {
        "mystcase": (KNIFE, True, 1.0), "cruiser": (KNIFE, True, 1.0),
        "cookie": (PLAIN, False, 1.0), "cookie_xmas": (PLAIN, False, 1.0)}  # fmt: skip
    assert all(r["steps"] == KNIFE for r in kb["box_recipes"].values())
    # the runner takes these recipes with the Run config (before any input), as the one box's
    v = n.vals
    _pl, hook, _io = TBF.player(tmp_path, TBF.box(NOSWAP))
    for kw in (kb, kn):
        assert dh.box_plays_refused(
            kw["box_plays"], hook, heal_candy=bool(v.get("heal_candy")),
            boss_walk=False, bosses=("boss",), roles=kw["box_roles"], knife_swap=True,
            bare_ready=bool(v["bare_ready"]), respawn=True, home_key="F9",
            model=kw["box_model"], recipes=kw["box_recipes"], value_target=bool(v["value_target"]),
            eat=kw["box_eat"], keys={k: x for k, x in n.keys.items() if k != "knife_key"},
            opener=n.keys["knife_key"]) is None  # fmt: skip
    assert v["bare_ready"] is True and v["knife_swap"] is True and v["steal_cue"] == "popup"


# --- round 29 (Batt 14.12 #2 "make it work"; 16.8: an example, not the default): the twin -------
def test_the_functions_twin_is_the_ready_made_box_but_its_two_cookie_recipes_and_runs() -> None:
    """The Load lists' no-swap example in the FUNCTIONS shape: the ready-made box but the same two
    recipes (16.1's check against the functions box), no old runner block (so its Run is a real
    run, round 29), and prepared as a Run does: the functions box's argv and run() arguments but
    box_recipes for the two cookies."""
    text = FUN_NOSWAP.read_text()
    assert text == pj.canonical_json(pj.from_json(text)) + "\n"
    fun, old = json.loads(FUN.read_text()), json.loads(NOSWAP.read_text())
    twin = json.loads(text)
    assert ab.box_difference(fun, twin) is None  # the functions box but its two cookie recipes
    mon = lambda d: next(t for t in d["nodes"][0]["tabs"] if t["name"] == "monsters")  # noqa: E731
    assert mon(twin)["defs"] == mon(old)["defs"]  # 16.1's very recipes
    p = pj.from_json(text)
    assert pj.old_runner_nodes(p) == []  # no old runner block: the Run is not held
    c, found = pj.project_lint(p)
    assert [f.text for f in found if f.severity in ("error", "readiness")] == []
    _fc, fun_found = pj.project_lint(pj.from_json(FUN.read_text()))
    assert sorted(f.rule for f in found) == sorted(f.rule for f in fun_found)
    assert c.flow is not None and live.problems(c.flow) == []
    assert pj.runner_keys(p, NODE).keys == pj.runner_keys(pj.from_json(FUN.read_text()), NODE).keys
    b, n = _prep(FUN), _prep(FUN_NOSWAP)
    assert n.argv("L", Path("/S"), None) == b.argv("L", Path("/S"), None)
    kb, kn = b.box_kwargs(), n.box_kwargs()
    assert {k: v for k, v in kn.items() if k != "box_recipes"} == {
        k: v for k, v in kb.items() if k != "box_recipes"}  # fmt: skip
    assert (n.keys, n.vals) == (b.keys, b.vals)
    assert (n.loop, n.default_species) == (b.loop, b.default_species)
    assert {sp: (r["steps"], r["knife"], r["priority"]) for sp, r in kn["box_recipes"].items()} == {
        "mystcase": (KNIFE, True, 1.0), "cruiser": (KNIFE, True, 1.0),
        "cookie": (PLAIN, False, 1.0), "cookie_xmas": (PLAIN, False, 1.0)}  # fmt: skip
    # the one-box no-swap recipes and the twin's are prepared alike (the same plan per species)
    assert kn["box_recipes"] == _prep(NOSWAP).box_kwargs()["box_recipes"]


# --- the lock: the hook answers from the fixture, the runner's BareCtl plays it ------------------
class Rig:
    """run()'s wiring of the box's recipes and its Knife (strike -> bare.before_strike(..., recipe)
    -> recipe_knife -> recipe_choice(hook_recipe(...), box_recipes[species]), its `recipe` record
    into the runner's session) on the simulated client, the Run config's Knife: the opener on F4
    (the box's knife_on), the dagger on F5 (knife_back), --bare-ready, the popup cue."""

    def __init__(self, tmp_path: Path, path: Path, ready: bool = True) -> None:
        self.sim = TDH._OpenerSim()
        self.pl, self.hook, _io = TBF.player(tmp_path, TBF.box(path), self.sim)
        self.plan = self.pl.prep.runners[NODE].box_kwargs()["box_recipes"]
        own = {"F4": self.sim.opener, "F5": self.sim.press}

        def port(code: str, why: str) -> str | None:
            do = own.get(code)
            if do is None:
                return None
            do(why)
            return "knife"

        def box_call(role: str, why: str) -> bool:
            return dh.hook_call(self.hook, role, why, port) is None

        bio = self.sim.io()
        bio.opener = lambda why: box_call("knife_on", why)
        bio.press = lambda why: (self.sim.press(why) if why == "safety"
                                 else box_call("knife_back", why))  # fmt: skip
        self.counts: Counter[str] = Counter()
        self.evs: list[dict[str, Any]] = []  # the runner session's records, in order
        self.ctl = dh.BareCtl(bio, TDH._armed_ref(), self.counts, self.ev, TDH._Stop,
                              ready=ready, opener=TDH._opener_read(), cue="popup")  # fmt: skip
        self.popup = 160  # the item popup's width (test_dungeon_hunt's frames): a new one a fight

    def ev(self, rec: dict[str, Any]) -> None:
        self.evs.append({**rec, "t_ns": int(self.sim.t * 1e9)})  # run()'s ev stamps t_ns

    def recipe_knife(self, species: str | None, by: str) -> bool:
        """run()'s closure recipe_knife, its counts and its record (checked against its source)."""
        knife, fn_, odd = dh.recipe_choice(dh.hook_recipe(self.hook, species, by),
                                           self.plan.get(species or ""))  # fmt: skip
        self.counts["recipe_mismatch"] += int(odd)
        self.counts["recipe_knife" if knife else "recipe_no_knife"] += 1
        self.ev({"kind": "recipe", "species": species, "by": by, "knife": knife,
                 "function": fn_, **({"mismatch": True} if odd else {})})  # fmt: skip
        return knife

    def idle(self) -> list[tuple[Any, ...]]:
        """--bare-ready's idle moment (searching, no lock, HP over the floor): its presses."""
        n = len(self.sim.log)
        self.ctl.ready_tick(self.sim.t, True, True, 0.9)
        return self.sim.log[n:]

    def fight(self, species: str | None, cue: bool = True) -> list[tuple[Any, ...]]:
        """One target, as the runner meets it: the strike at its lock, a NEW item popup a moment
        later (a steal's, when the Knife strikes), the Knife's time box over, the kill (the lock
        goes, the fight ends). Returns the presses from the lock to the fight's end."""
        n = len(self.sim.log)
        aims: list[float] = []
        ok = self.ctl.before_strike("box", 0.9, lambda: aims.append(self.sim.t) is None,
                                    lambda: self.recipe_knife(species, "box"))  # fmt: skip
        assert ok
        self.ctl.struck()
        self.ctl.tick(self.sim.t, True, True, self.sim.frame(), 0.9)
        if cue:
            self.popup += 16  # another item's popup: a steal (the popup cue)
            self.sim.popup = self.popup
        self.ctl.tick(self.sim.t, True, True, self.sim.frame(), 0.9)
        self.sim.t += 9.0  # past the Knife's time box (BARE_MAX_S): no swap is still due
        self.ctl.tick(self.sim.t, True, True, self.sim.frame(), 0.9)
        self.ev({"kind": "kill", "by": "exp_line", "line": "base_exp"})
        self.ctl.tick(self.sim.t, False, True, self.sim.frame(), 0.9)  # the lock went
        self.ctl.tick(self.sim.t, False, False, self.sim.frame(), 0.9)  # the fight is over
        return self.sim.log[n:]


def test_run_writes_the_recipe_record_the_rig_writes() -> None:
    src = inspect.getsource(dh.run)
    assert (
        'ev({"kind": "recipe", "species": species_, "by": by_, "knife": knife_,\n'
        '                "function": fn_, **({"mismatch": True} if odd_ else {})})'
    ) in src
    assert "bare_ref, counts, ev, r.Stop, ready=bare_ready_on," in src  # BareCtl writes there too


@pytest.mark.parametrize("cookie", ["cookie", "cookie_xmas"])
def test_bare_ready_a_cookie_gets_the_dagger_first_and_no_opener_no_steal_wait(
    tmp_path: Path, cookie: str
) -> None:
    rig = Rig(tmp_path, NOSWAP)
    assert [k for k, *_ in rig.idle()] == ["opener"]  # the Run config: the Knife on while idle
    assert not rig.ctl.st.armed
    presses = rig.fight(cookie)
    # the dagger on FIRST (the box's knife_back, "recipe"), then nothing: no opener at the lock, no
    # swap back on the steal's popup, none at the Knife's time box
    assert presses == [("press", "box knife_back (recipe)")] and rig.ctl.st.armed
    assert rig.counts["bare_recipe_no_knife"] == 1 and rig.counts["bare_equip_recipe"] == 1
    assert rig.counts["bare_ready_strike"] == 0 and rig.counts["bare_opener"] == 1  # the idle one
    assert not any(k.startswith("bare_equip_") and k != "bare_equip_recipe"
                   for k in rig.counts if rig.counts[k])  # fmt: skip
    assert [k for k, *_ in rig.idle()] == ["opener"]  # the next idle: the Knife again
    # the player's record of the recipe it handed over: the fixture's own
    rec = [e for e in TBF.records(rig.pl) if e["kind"] == "recipe"]
    assert [(e["species"], e["function"], e["steps"], e["knife"]) for e in rec] == [
        (cookie, f"attack_{cookie}", PLAIN, False)]  # fmt: skip
    # the score's reader (stage6_ab.locks_of) on the runner's own records
    (lk,), before = ab.locks_of(rig.evs)
    assert before == 0 and (lk.species, lk.knife, lk.tried, lk.struck) == (cookie, False, False,
                                                                          False)  # fmt: skip
    assert (lk.plain, lk.dagger_first, lk.steals, lk.kills) == (True, True, 0, 1)


@pytest.mark.parametrize("other", ["mystcase", "cruiser"])
def test_the_other_monsters_keep_the_knife_swap_and_its_steal(tmp_path: Path, other: str) -> None:
    rig = Rig(tmp_path, NOSWAP)
    rig.idle()
    presses = rig.fight(other)
    # struck bare at once (--bare-ready's own: no press at the lock), the dagger back on the
    # steal's popup (the box's knife_back), today's technique
    assert presses == [("press", "box knife_back (popup)")]
    assert rig.counts["bare_ready_strike"] == 1 and rig.counts["bare_equip_popup"] == 1
    assert rig.counts["bare_recipe_no_knife"] == 0
    (lk,), _ = ab.locks_of(rig.evs)
    assert (lk.species, lk.knife, lk.tried, lk.struck, lk.plain) == (other, True, True, True, False)
    assert lk.steals == 1 and lk.kills == 1 and lk.kill_s is not None and lk.kill_s > 9.0


def test_one_box_strikes_a_cookie_with_the_knife_the_counter_sees_it(tmp_path: Path) -> None:
    """The positive case of the plays line: in B the same lock is a Knife strike and a steal."""
    rig = Rig(tmp_path, ONE)
    rig.idle()
    assert rig.fight("cookie") == [("press", "box knife_back (popup)")]
    (lk,), _ = ab.locks_of(rig.evs)
    assert (lk.knife, lk.tried, lk.struck, lk.plain, lk.steals) == (True, True, True, False, 1)


def test_armed_at_the_lock_a_cookie_is_struck_as_it_is_and_a_myst_case_gets_the_opener(
    tmp_path: Path,
) -> None:
    """Without the idle swap (the dagger on at the lock: after a failed idle swap, or a run
    without --bare-ready): the cookie gets no press at all, the Myst Case the opener AT its
    strike."""
    rig = Rig(tmp_path, NOSWAP, ready=False)
    assert rig.fight("cookie") == [] and rig.ctl.st.armed
    got = rig.fight("mystcase")
    assert [k for k, *_ in got] == ["opener", "press"]
    assert got[-1] == ("press", "box knife_back (popup)")
    ck, mc = ab.locks_of(rig.evs)[0]
    assert (ck.tried, ck.plain, ck.dagger_first) == (False, True, False)
    assert (mc.tried, mc.struck, mc.steals) == (True, True, 1)


def test_a_series_of_locks_through_the_real_hook_counts_by_species(tmp_path: Path) -> None:
    """A run's worth of locks in C: the score reads every cookie lock as a no-knife play, every
    other lock as a Knife strike, a strike that knew no species as the runner's own (the swap)."""
    rig = Rig(tmp_path, NOSWAP)
    order: list[str | None] = ["mystcase", "cookie", "cruiser", "cookie_xmas", None, "cookie"]
    for sp in order:
        rig.idle()
        rig.fight(sp)
    sc = ab.Score6("r", "C", 1)
    ab.score_locks(sc, rig.evs)
    assert sc.locks_sp == {"mystcase": 1, "cookie": 2, "cruiser": 1, "cookie_xmas": 1, "?": 1}
    assert sc.tries_sp == {"mystcase": 1, "cruiser": 1, "?": 1}  # no try on a cookie lock
    assert sc.plain_sp == {"cookie": 2, "cookie_xmas": 1} and sc.dagger_first == 3
    assert sc.steals_sp == {"mystcase": 1, "cruiser": 1, "?": 1} and sc.mismatch_locks == 0
    assert sc.kills_sp == {"mystcase": 1, "cookie": 2, "cruiser": 1, "cookie_xmas": 1, "?": 1}
    assert rig.counts["recipe_mismatch"] == 0 and rig.hook.res.recipes == len(order)


def test_a_hook_answer_that_is_not_the_plan_plays_the_swap_and_the_plays_line_sees_it(
    tmp_path: Path,
) -> None:
    """A negative control: if the hook's answer for a cookie were not C's plan, the runner plays
    its own recipe (the Knife) -- the reader names that lock a Knife try, which fails C's line."""
    rig = Rig(tmp_path, NOSWAP)
    real: Callable[..., Any] = rig.hook.recipe
    rig.hook.recipe = lambda sp, why: None if sp == "cookie" else real(sp, why)  # type: ignore[method-assign]
    rig.idle()
    rig.fight("cookie")
    (lk,), _ = ab.locks_of(rig.evs)
    assert lk.mismatch and lk.knife is True and lk.tried and not lk.plain
