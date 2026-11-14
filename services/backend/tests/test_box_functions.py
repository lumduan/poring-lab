"""Live blocks stage 3 (Batt 2026-11-13: "The Knife swap (Damascus): a function: press F4,
wait 100 ms, press F5; the other way back to the Knife: the same swapped"; "make respawn a function
block, in case another server's menu differs; make everything editable in blocks, don't
hard-code"; docs/planning/live-blocks.md 3.3; dungeon@9.50): the Knife swap, the respawn, the
weight home and the way home at the end are the BOX's functions (and an event), played at the
RUNNER's moments.

Offline, no game. The REAL player's hook (flow_play.HuntHook: call, survive) plays the box's role
functions; the runner's side is its own code wherever it is pure enough to drive -- BareCtl and
opener_seq / bare_equip_seq on test_dungeon_hunt's simulated client, respawn_end and player_home_end
on fakes -- wired exactly as run() wires them (its AST is checked below), and a fake hunt loop for
the whole run."""

from __future__ import annotations

import ast
import copy
import importlib.util
import inspect
import json
import sys
import textwrap
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_hunt as dh  # noqa: E402
import flow_play as fp  # noqa: E402

from poring_flow import functions as fn  # noqa: E402
from poring_flow import live  # noqa: E402
from poring_flow import project as pj  # noqa: E402

FIX = ROOT / "services/frontend/src/lib/flow/fixtures"
# the box as stage 3 left it (stage 4a gave the ready-made one its use_model and monsters tab:
# test_box_recipes.py); stage3_ab.py's B3 arm
B3 = FIX / "project_xmas_dun02_stage3.json"
STAGE3_PLAYS = ["boss_fly", "fly_hp", "home_end", "knife", "potion", "respawn", "weight_home"]
B2 = FIX / "project_xmas_dun02_stage2.json"  # the box as stage 2 left it (the A/B's B2 arm)
STAGE2_PLAYS = ["boss_fly", "fly_hp", "potion"]


def _tdh() -> Any:
    """test_dungeon_hunt's simulated client (the swaps on SIM time), shared, not copied."""
    spec = importlib.util.spec_from_file_location("_tdh_sim", Path(__file__).with_name(
        "test_dungeon_hunt.py"))  # fmt: skip
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TDH = _tdh()


def lit(v: Any) -> dict[str, Any]:
    return {"kind": "lit", "value": v}


def press(k: str) -> dict[str, Any]:
    return {"kind": "action", "block": "press_key", "concept": "ui.press_hotkey",
            "params": {"key": lit(k)}, "timeout_s": 2.0, "on_fail": "stop", "outcome_to": None,
            "note": None}  # fmt: skip


def click(x: Any, y: Any) -> dict[str, Any]:
    return {"kind": "action", "block": "click_at", "concept": "ui.press_button",
            "params": {"x": lit(x), "y": lit(y)}, "timeout_s": 2.0, "on_fail": "stop",
            "outcome_to": None, "note": None}  # fmt: skip


def wait(s: float) -> dict[str, Any]:
    return {"kind": "wait_until", "cond": lit(False), "timeout_s": s, "outcome_to": None}


def call(p: str) -> dict[str, Any]:
    return {"kind": "call", "proc": p, "args": [], "kwargs": {}}


def box(path: Path = B3, **bodies: list[dict[str, Any]]) -> dict[str, Any]:
    """A one-box project (its time box under the run's maximum) with some defs' bodies replaced."""
    d = json.loads(path.read_text())
    d["max_runtime_s"] = 600
    for t in d["nodes"][0]["tabs"]:
        for x in t["defs"]:
            if x["name"] in bodies:
                x["body"] = bodies[x["name"]]
    return d


def tab_of(d: dict[str, Any], name: str) -> dict[str, Any]:
    return next(t for t in d["nodes"][0]["tabs"] if t["name"] == name)


def prep(tmp_path: Path, d: dict[str, Any]) -> fp.Prepared:
    got = fp.prepare(json.dumps(d), "xmas_dun02", 3600)
    assert isinstance(got, fp.Prepared), got
    return got


def refused(tmp_path: Path, d: dict[str, Any]) -> str:
    got = fp.prepare(json.dumps(d), "xmas_dun02", 3600)
    assert isinstance(got, str) and "refused before any input" in got, got
    c = pj.compile_project(pj.from_json(json.dumps(d)))
    assert c.flow is not None and live.problems(c.flow)  # the backend's not_live: the same
    return got


class FakeIO(fp.LiveIO):
    """A fake clock (``clock`` / ``sleep`` may be a simulated client's); every input recorded."""

    def __init__(self, sim: Any = None) -> None:
        self.now, self.sim = 0.0, sim
        self.map = "xmas_dun02"  # the minimap's read (geffen after the way home)
        self.out: list[tuple[Any, ...]] = []
        self.agent, self.screen = "AGENT", "SCREEN"

    def clock(self) -> float:
        return self.sim.t if self.sim is not None else self.now

    def sleep(self, s: float) -> None:
        self.out.append(("sleep", round(s, 3)))
        if self.sim is not None:
            self.sim.t += s
        else:
            self.now += s

    def ns(self) -> int:
        return int(self.clock() * 1e9)

    def senses(self) -> dict[str, Any]:
        return {"hp_percent": 100, "sp_percent": 100, "weight_percent": 10, "is_dead": False,
                "map": self.map}  # fmt: skip

    def open(self) -> None:
        self.out.append(("open",))

    def ui_clear(self) -> None:
        self.out.append(("ui_clear",))

    def tap(self, code: str) -> None:
        self.out.append(("tap", code))

    def release(self) -> None:
        self.out.append(("release",))


def player(tmp_path: Path, d: dict[str, Any], sim: Any = None
           ) -> tuple[fp.LivePlayer, fp.HuntHook, FakeIO]:  # fmt: skip
    """The REAL live player on the node, as inside its hunt core: its hook (call, survive)."""
    p = prep(tmp_path, d)
    io_ = FakeIO(sim)
    demo = tmp_path / "demo"
    demo.mkdir(exist_ok=True)
    pl = fp.LivePlayer(p, io_, fp.SessionLog(demo, "t", io_.ns), stop_file=None, hunt=None)
    pl.start_world("xmas_dun02")
    plan = p.runners["xmas_dun02"]
    pl._hunt_keys, pl._hunt_weight = frozenset(plan.events), frozenset(plan.weight_events)
    return pl, fp.HuntHook(pl, fp.HuntResult()), io_


def records(pl: fp.LivePlayer) -> list[dict[str, Any]]:
    pl.rec.fh.flush()
    return [json.loads(x) for x in (pl.rec.dir / "events.jsonl").read_text().splitlines()]


# --- the box and what it hands over ---------------------------------------------------------------
def test_the_stage3_box_plays_its_functions_and_the_stage2_box_plays_as_stage_2(
    tmp_path: Path,
) -> None:
    c, found = pj.project_lint(pj.from_json(B3.read_text()))
    assert [f.text for f in found if f.severity == "error"] == []
    assert c.flow is not None and live.problems(c.flow) == []
    plan = live.hunt_plan(c.flow, "xmas_dun02")
    assert plan.plays == frozenset({"potion", "fly_hp", "boss_fly", "knife", "respawn",
                                    "weight_home", "home_end"})  # fmt: skip
    assert plan.events == ("fly_away", "drink", "bag_full") and plan.weight_events == ("bag_full",)
    steps = {r: [s.doc() for s in st] for r, st in plan.calls.items()}
    assert steps == {
        "knife_on": [{"press": "F4"}],
        "knife_back": [{"press": "F5"}],
        "home": [{"press": "F9"}],
        "respawn": [{"click": [645, 481]}],
        "respawn_confirm": [{"click": [714, 405]}],
    }  # the runner's own defaults
    assert plan.call_names == {"knife_on": "knife_on", "knife_back": "knife_back",
                               "home": "fly_home", "respawn": "respawn_button",
                               "respawn_confirm": "respawn_ok"}  # fmt: skip
    assert plan.knife_ends == "opener"  # the strike between F4 and F5: the runner's own today
    rp = prep(tmp_path, box()).runners["xmas_dun02"]
    assert rp.box_roles() == {
        "knife_on": "opener",
        "knife_back": "armed",
        "home": "home",
        "respawn": "save_point",
        "respawn_confirm": "save_point",
    }
    # its Run keys are the same five (a body's key is its first press): the same runner argv
    keys = pj.runner_keys(pj.from_json(B3.read_text()), "xmas_dun02").keys
    keys2 = pj.runner_keys(pj.from_json(B2.read_text()), "xmas_dun02").keys
    assert keys == keys2 == {"heal_key": "F1", "fly_key": "F8", "home_key": "F9",
                             "knife_key": "F4", "dagger_key": "F5"}  # fmt: skip
    r2 = prep(tmp_path, box(B2)).runners["xmas_dun02"]
    assert r2.argv("x", None, None) == rp.argv("x", None, None)
    # the stage-2 box: no calls, no weight event -- the run() call stage 2 made, exactly
    assert (r2.calls, r2.weight_events, sorted(r2.plays)) == ({}, (), STAGE2_PLAYS)


def test_a_box_without_the_new_functions_calls_run_exactly_as_stage_2(tmp_path: Path) -> None:
    seen: list[dict[str, Any]] = []

    def run_fn(a: Any, *, hook: Any = None, session: Any = None, **kw: Any) -> int:
        seen.append(kw)
        hook.event({"kind": "run_end", "reason": "time_box"}, 0.0)
        return 0

    for path, want in ((B2, {"box_plays": STAGE2_PLAYS}),
                       (B3, {"box_plays": STAGE3_PLAYS,
                             "box_roles": {"knife_on": "opener", "knife_back": "armed",
                                           "home": "home", "respawn": "save_point",
                                           "respawn_confirm": "save_point"}})):  # fmt: skip
        d = tmp_path / path.stem
        d.mkdir()
        p = prep(d, box(path))
        io_ = FakeIO()
        fp.play(p, io_, label="k", stop_file=None, demo=d, checker=lambda _p, _i: {
            "items": [{"id": "cell", "ok": True, "words": "-"}], "ok": True},
            hunt=fp.HuntCore("k", None, run_fn=run_fn))  # fmt: skip
        assert seen[-1] == want, path.name
    # a role function that is ONE press_key stays the runner's own key: not a body
    c = pj.compile_project(pj.from_json(B2.read_text()))
    assert c.flow is not None
    assert not any(fn.is_body(c.flow, n) for n in ("knife_on", "knife_back", "butterfly_wing"))


def test_batts_other_answer_f4_wait_f5_in_one_function_is_expressible(tmp_path: Path) -> None:
    """The OPEN question (live-blocks.md 3.3): "F4, wait 100 ms, F5" -- the strike between, or
    not. The default (the box) is the runner's own: F4 before the strike, F5 after the steal. The
    other answer is one function at the opener's moment; both are written and both play."""
    d = box(knife_on=[call("wield_knife"), wait(0.1), call("wield_damascus")],
            knife_back=[call("wield_damascus"), wait(0.1), call("wield_knife"),
                        call("wield_damascus")])  # fmt: skip
    plan = prep(tmp_path, d).runners["xmas_dun02"]
    assert [s.doc() for s in plan.calls["knife_on"]] == [{"press": "F4"}, {"wait": 0.1},
                                                         {"press": "F5"}]  # fmt: skip
    assert plan.knife_ends == "armed" and plan.box_roles()["knife_on"] == "armed"
    # its Run key is still the body's first press (the start's slot check reads F4 and F5)
    assert pj.runner_keys(pj.from_json(json.dumps(d)), "xmas_dun02").keys == {
        "heal_key": "F1", "fly_key": "F8", "home_key": "F9", "knife_key": "F4",
        "dagger_key": "F5"}  # fmt: skip
    # the runner refuses that answer with --bare-ready (it waits with the Knife on between
    # targets, which that swap never leaves her): before any input
    why = dh.box_plays_refused(["knife"], _Hook(), heal_candy=False, boss_walk=False, bosses=(),
                               roles={"knife_on": "armed", "knife_back": "armed"},
                               bare_ready=True)  # fmt: skip
    assert why is not None and "--bare-ready" in why


class _Hook:
    def survive(self, view: Any, press: Any) -> str | None:
        return None

    def call(self, role: str, why: str, press: Any, click: Any = None) -> str | None:
        return None


# --- the Knife at the runner's moments (BareCtl on the simulated client) --------------------------
def knife_ctl(tmp_path: Path, d: dict[str, Any], ends: str = "opener", **kw: Any) -> tuple[
        Any, Any, dict[str, Any], list[dict[str, Any]], fp.LivePlayer, FakeIO]:  # fmt: skip
    """run()'s wiring with the box's Knife swap (bare_opener / bare_equip_press -> box_call ->
    hook_call): the player's knife_on / knife_back bodies press F4 / F5 through the runner's own
    presses (the simulated client's opener / press)."""
    sim = TDH._OpenerSim()
    pl, hook, io_ = player(tmp_path, d, sim)
    own = {"F4": sim.opener, "F5": sim.press}

    def port(code: str, why: str) -> str | None:  # run()'s box_call port (a key of the moment)
        do = own.get(code)
        if do is None:
            return None
        do(why)
        return "knife"

    def box_call(role: str, why: str) -> bool:
        return dh.hook_call(hook, role, why, port) is None

    bio = sim.io()
    bio.opener = lambda why: box_call("knife_on", why)  # bare_opener, box_knife on
    bio.press = lambda why: sim.press(why) if why == "safety" else box_call("knife_back", why)
    from collections import Counter

    counts: Counter[str] = Counter()
    evs: list[dict[str, Any]] = []
    ctl = dh.BareCtl(bio, TDH._armed_ref(), counts, evs.append, TDH._Stop,
                     opener=TDH._opener_read(), opener_ends=ends, **kw)  # fmt: skip
    return ctl, sim, counts, evs, pl, io_


def test_the_knife_bodies_play_at_the_runners_moments_opener_before_the_strike_back_after(
    tmp_path: Path,
) -> None:
    ctl, sim, counts, evs, pl, _io = knife_ctl(tmp_path, box())
    aims: list[float] = []
    assert ctl.before_strike("box", 0.9, lambda: aims.append(sim.t) is None)  # the strike next
    assert [k for k, *_ in sim.log] == ["opener"] and sim.log[0][1] == "box knife_on (box)"
    assert aims and sim.bag and not ctl.st.armed  # the Knife worn, read back, BEFORE the aim
    assert counts["bare_opener"] == 1 and evs[-1]["state"] == "opener"
    ctl.struck()
    ctl.tick(sim.t, True, True, sim.frame(), 0.9)
    assert [k for k, *_ in sim.log] == ["opener"]  # nothing back before the steal's cue
    sim.lines.append({"colour": "cyan"})  # the steal's cue: the swap back, the box's knife_back
    ctl.tick(sim.t, True, True, sim.frame(), 0.9)
    assert sim.log[-1] == ("press", "box knife_back (cyan)") and ctl.st.armed and not sim.bag
    assert counts["bare_equip_cyan"] == 1  # the runner's own read-back judged it
    calls = [(e["role"], e["function"], e["why"], e["node"]) for e in records(pl)
             if e["kind"] == "call"]  # fmt: skip
    assert calls == [
        ("knife_on", "knife_on", "box", "xmas_dun02/knife/knife_on"),
        ("knife_back", "knife_back", "cyan", "xmas_dun02/knife/knife_back"),
    ]
    assert pl.keys_sent == ["F4", "F5"]


def test_the_other_answer_f4_wait_f5_swaps_once_a_target_and_strikes_armed(tmp_path: Path) -> None:
    d = box(knife_on=[call("wield_knife"), wait(0.1), call("wield_damascus")])
    ctl, sim, counts, evs, pl, io_ = knife_ctl(tmp_path, d, ends="armed")
    aims: list[int] = []
    t0 = sim.t
    assert ctl.before_strike("box", 0.9, lambda: aims.append(1) is None)
    assert [k for k, *_ in sim.log] == ["opener", "press"]  # F4, then F5: no strike between
    assert ("sleep", 0.1) in io_.out and sim.t - t0 >= 0.1  # the wait, slept exactly
    assert ctl.st.armed and not sim.bag and aims == []  # armed: the strike goes on, no re-aim
    assert counts["bare_opener"] == 1 and counts["bare_opener_through"] == 1
    assert evs[-1]["ends"] == "armed" and evs[-1]["ok"]
    assert ctl.before_strike("box", 0.9, None)  # the same target: its one swap was taken
    assert [k for k, *_ in sim.log] == ["opener", "press"]
    ctl.struck()
    sim.lines.append({"colour": "cyan"})
    ctl.tick(sim.t, True, True, sim.frame(), 0.9)
    assert [k for k, *_ in sim.log] == ["opener", "press"]  # nothing to swap back: armed
    assert pl.keys_sent == ["F4", "F5"]


def test_the_escapes_dagger_before_a_fly_stays_the_runners_own_key(tmp_path: Path) -> None:
    ctl, sim, _counts, _evs, pl, _io = knife_ctl(tmp_path, box())
    assert ctl.before_strike("box", 0.9, None) and not ctl.st.armed
    ctl.escape()  # press("fly") calls it first: the dagger's key at once, never a body's waits
    assert sim.log[-1] == ("press", "safety")
    assert [e["role"] for e in records(pl) if e["kind"] == "call"] == ["knife_on"]


def test_a_knife_body_that_cannot_play_refuses_before_any_input(tmp_path: Path) -> None:
    cases: list[tuple[dict[str, Any], str]] = [
        # (a body's FIRST press is its role's key: [F6] alone says the Knife is on F6 -- a key the
        # start's slot check then reads; a second, other key is not one it reads)
        (box(knife_on=[press("F4"), press("F6")]), "knife_on presses F6: at that moment the hunt "
         "core hands the box only F4, F5"),
        (box(knife_on=[press("F4"), wait(0.6), press("F5"), wait(0.6), press("F4")]),
         "knife_on waits 1.2 s in all: at most 1 s"),
        (box(knife_on=[press("F4"), press("F5"), press("F4"), press("F5"), press("F4")]),
         "knife_on has 5 presses and clicks: at most 4"),
        (box(knife_back=[press("F5"), press("F4")]), "knife_back (knife_back) ends on F4: the "
         "swap back ends on the dagger's key (F5)"),
        (box(knife_on=[press("F4"), click(10, 10)]), "knife_on clicks (click_at): click_at plays "
         "live only inside dungeon_hunt's respawn functions"),
        (box(knife_on=[{"kind": "if", "cond": lit(True), "then": [press("F4")], "orelse": []}]),
         "knife_on holds a if statement"),
        (box(knife_on=[{"kind": "wait_until", "cond": {"kind": "sense", "sensor": "hp_percent",
                                                       "args": {}}, "timeout_s": 0.5,
                        "outcome_to": None}, press("F4")]),
         "knife_on holds a wait_until statement"),
    ]  # fmt: skip
    for i, (d, words) in enumerate(cases):
        (tmp_path / str(i)).mkdir()
        got = refused(tmp_path / str(i), d)
        assert words in got, (i, got)
    assert not list(tmp_path.glob("*/demo"))  # pure: no session


# --- the respawn: the death exit's two clicks -----------------------------------------------------
def death_exit(tmp_path: Path, d: dict[str, Any], *, confirm_seen: bool = True
               ) -> tuple[dict[str, Any], list[tuple[Any, ...]], fp.LivePlayer]:  # fmt: skip
    """run()'s death exit with the box's respawn (respawn_press / confirm_press -> box_call): the
    runner's OWN respawn_end (the dialog read, the confirmation read, the load wait) on fakes; the
    clicks through run()'s click port (two motions, then the click)."""
    pl, hook, _io = player(tmp_path, d)
    out: list[tuple[Any, ...]] = []
    t = [0.0]
    state = {"dead": True, "confirm": False, "info": True}

    def click_port(u: int, v: int, why: str) -> bool:  # run()'s box_call click: the death exit
        out.append(("click", u, v, why))
        if (u, v) == (645, 481) and state["dead"]:
            state["dead"], state["confirm"] = False, confirm_seen
        elif (u, v) == (714, 405) and state["confirm"]:
            state["confirm"], state["info"] = False, False
        return True

    def box_call(role: str) -> bool:
        return dh.hook_call(hook, role, "death", lambda c, w: None, click_port) is None

    def clock() -> float:
        return t[0]

    def sleep(s: float) -> None:
        t[0] += s
        if not state["info"] and t[0] > 2.0:
            state["info"] = True  # the save point's map drawn

    has_confirm = "respawn_confirm" in prep(tmp_path, d).runners["xmas_dun02"].calls
    rec = dh.respawn_end(dead=lambda: state["dead"], press=lambda: box_call("respawn") or None,
                         basic_info=lambda: state["info"],
                         confirm_reads=(lambda: state["confirm"]) if has_confirm else None,
                         confirm_press=(lambda: box_call("respawn_confirm") or None)
                         if has_confirm else None, sleep=sleep, now=clock)  # fmt: skip
    return rec, out, pl


def test_the_respawn_functions_click_in_the_death_exit_the_runners_reads_between(
    tmp_path: Path,
) -> None:
    rec, out, pl = death_exit(tmp_path, box())
    assert [o[:3] for o in out] == [("click", 645, 481), ("click", 714, 405)]
    assert out[0][3] == "box respawn_button (death)" and out[1][3] == "box respawn_ok (death)"
    assert rec["pressed"] and rec["confirm"] == "pressed" and rec["back_s"] is not None
    calls = [(e["role"], e["node"]) for e in records(pl) if e["kind"] == "call"]
    assert calls == [
        ("respawn", "xmas_dun02/exits/respawn_button"),
        ("respawn_confirm", "xmas_dun02/exits/respawn_ok"),
    ]
    # another server's menu: its own point, and no confirmation (no respawn_confirm function)
    other = box(respawn_button=[click(600, 500), wait(0.2)])
    other["nodes"][0]["tabs"][0]["main"][1]["params"].pop("respawn_confirm")
    exits = tab_of(other, "exits")  # (a click_at no respawn role names would be refused)
    exits["defs"] = [x for x in exits["defs"] if x["name"] != "respawn_ok"]
    (tmp_path / "o").mkdir()
    rec2, out2, _pl2 = death_exit(tmp_path / "o", other, confirm_seen=False)
    assert [o[:3] for o in out2] == [("click", 600, 500)] and "confirm" not in rec2


def test_click_at_plays_nowhere_but_the_death_exit(tmp_path: Path) -> None:
    def main_with(stmt: dict[str, Any]) -> dict[str, Any]:
        d = box()
        d["nodes"][0]["tabs"][0]["main"].insert(1, stmt)
        return d

    cases = [
        (main_with(click(10, 10)), "click_at plays live only inside dungeon_hunt's respawn"),
        (main_with(call("respawn_button")), "respawn_button() clicks (click_at)"),
        (box(respawn_button=[press("F1")]), "respawn_button presses F1"),
        (box(respawn_button=[click(1400, 10)]), "respawn_button clicks at 1400, 10: off the "
         "game picture"),
    ]  # fmt: skip
    for i, (d, words) in enumerate(cases):
        (tmp_path / str(i)).mkdir()
        assert words in refused(tmp_path / str(i), d), i
    d = box()
    d["nodes"][0]["tabs"][0]["main"][1]["params"].pop("respawn")
    (tmp_path / "c").mkdir()
    assert "respawn_confirm goes with respawn" in refused(tmp_path / "c", d)


# --- the weight home: an event on the runner's weight read ----------------------------------------
def test_the_weight_event_decides_only_on_the_weight_read_and_ends_the_run_normally(
    tmp_path: Path,
) -> None:
    pl, hook, io_ = player(tmp_path, box())
    port_log: list[str] = []

    def port(code: str, why: str) -> str | None:
        port_log.append(code)
        return "potion" if code == "F1" else None

    # a main tick under 30 % HP: drink plays (stage 2) -- the weight event is not evaluated there
    view = dh.HuntTick(1.0, 28, 60, False, (10, 10), "search", {}, None)
    assert hook.survive(view, port) is None and port_log == ["F1"]
    io_.now = 5.0
    # the UI watch's read: 48 % -- nothing; 50 %: the weight home (its stop), the run's normal end
    w48 = dh.HuntTick(5.0, 90, 60, False, (10, 10), "search", {}, None, weight_pct=48)
    assert hook.survive(w48, port) is None
    w50 = dh.HuntTick(6.0, 90, 60, False, (10, 10), "search", {}, None, weight_pct=50)
    why = hook.survive(w50, port)
    assert why is not None and 'stop "home"' in why and "bag_full" in why
    assert port_log == ["F1"]  # no press for it, and no potion played on the weight read
    fired = [(e["event"], e["reading"]) for e in records(pl) if e["kind"] == "event"]
    assert fired == [("drink", {"hp_percent": 28}), ("bag_full", {"weight_percent": 50})]
    # the runner's normal end then calls the way home: it plays after the box ended the run
    assert dh.hook_call(hook, "home", "end", lambda c, w: "home" if c == "F9" else None) is None
    assert pl.keys_sent == ["F1", "F9"]


def test_the_way_home_presses_once_through_the_runners_own_end(tmp_path: Path) -> None:
    pl, hook, _io = player(tmp_path, box())
    pressed: list[str] = []

    def home_press() -> None:  # run()'s home_press with the box's way home
        dh.hook_call(hook, "home", "end", lambda c, w: pressed.append(c) or "home")

    t = [0.0]
    info = iter([True, False, False, True])
    rec = dh.player_home_end("F9", "weight_home: the box: ...", True, read_count=lambda: 3,
                             press=home_press, stand=lambda: pressed.append("stand"),
                             basic_info=lambda: next(info, True),
                             sleep=lambda s: t.__setitem__(0, t[0] + s),
                             now=lambda: t[0])  # fmt: skip
    assert pressed == ["stand", "F9"] and rec["pressed"] and rec["stood"]  # stood first, once
    # a death presses no Butterfly Wing (she respawned on the save point): the runner's rule
    pressed.clear()
    rec = dh.player_home_end("F9", "death", False, read_count=lambda: 3, press=home_press,
                             stand=lambda: None, basic_info=lambda: True)  # fmt: skip
    assert pressed == [] and not rec["pressed"]
    assert [e["function"] for e in records(pl) if e["kind"] == "call"] == ["fly_home"]


def test_a_weight_event_or_home_body_that_cannot_play_refuses_before_any_input(
    tmp_path: Path,
) -> None:
    def bag(**on: Any) -> dict[str, Any]:
        d = box()
        ev = next(x for x in tab_of(d, "survival")["defs"] if x["name"] == "bag_full")
        body = on.pop("body", None)
        ev["on"].update(on)
        if body is not None:
            ev["body"] = body
        return d

    hp_or_w = {"kind": "or", "terms": [
        {"kind": "cmp", "op": "<", "left": {"kind": "sense", "sensor": "hp_percent", "args": {}},
         "right": lit(20)},
        {"kind": "cmp", "op": ">=", "left": {"kind": "sense", "sensor": "weight_percent",
                                             "args": {}}, "right": lit(50)}]}  # fmt: skip
    cases = [
        (bag(body=[call("butterfly_wing")]), "bag_full reads weight_percent() inside the hunt "
         "core: there it is the weight home, and its body is one stop"),
        (bag(when=hp_or_w), "bag_full reads hp_percent, weight_percent inside the hunt core"),
        (bag(mode="insert"), "bag_full stops the run inside the hunt core: it must be a pre-empt"),
        (box(fly_home=[call("butterfly_wing"), call("butterfly_wing")]),
         "fly_home presses 2 keys: the way home is ONE Butterfly Wing"),
        (box(fly_home=[call("butterfly_wing"), wait(1.5)]), "fly_home waits 1.5 s in all"),
    ]  # fmt: skip
    for i, (d, words) in enumerate(cases):
        (tmp_path / str(i)).mkdir()
        assert words in refused(tmp_path / str(i), d), i


# --- the whole run through the player: a fake hunt loop -------------------------------------------
class HuntLoop:
    """dungeon_hunt.run at its moments, as run() does them (each checked by its AST below): the
    survival ticks (stage 2), a fight's Knife swap (the box's or its own), the UI watch's weight
    read (the box's event or its own --weight-home), and the player end (the box's way home or
    respawn, or its own). ``weights``: the weight read per UI watch; ``dies``: a death ends it."""

    def __init__(self, io_: FakeIO, weights: list[int], dies: bool = False) -> None:
        self.io, self.weights, self.dies = io_, weights, dies
        self.kw: dict[str, Any] = {}
        self.own: list[tuple[str, str]] = []  # the runner's own presses (what, key)
        self.box: list[tuple[str, str]] = []  # the presses the box's bodies made through it
        self.reason = ""

    def __call__(self, a: Any, *, hook: Any = None, session: Any = None, **kw: Any) -> int:
        self.kw = kw
        plays, roles = frozenset(kw.get("box_plays", ())), dict(kw.get("box_roles", {}))
        keys = {"F4": "opener", "F5": "equip", "F9": "home"}

        def port(code: str, why: str) -> str | None:
            what = keys.get(code)
            if what is None:
                return None
            self.box.append((what, code))
            hook.event({"kind": "press", "what": what, "key": code, "why": why}, self.io.now)
            return what

        def at(role: str, own: tuple[str, str]) -> None:  # bare_opener / bare_equip_press / ...
            if role in roles:
                assert dh.hook_call(hook, role, "x", port) is None
            else:
                self.own.append(own)

        hook.event({"kind": "run_start", "map": "xmas_dun02"}, self.io.now)
        reason = "time_box"
        for i, w in enumerate(self.weights):
            self.io.now += 1.0
            view = dh.HuntTick(self.io.now, 90, 60, False, (10, 10), "search", {}, None)
            if (why := dh.hook_stop(hook, view)) is not None:
                reason = f"stopped: {why}"
                break
            if plays:
                assert dh.hook_survive(hook, view, port) is None
            at("knife_on", ("opener", "F4"))  # a fight: the opener before the strike ...
            at("knife_back", ("equip", "F5"))  # ... the swap back after the steal
            if self.dies and i == 1:
                reason = "death"
                break
            if "weight_home" in plays:  # the UI watch's read: the box's event decides
                wv = dh.HuntTick(self.io.now, 90, 60, False, (10, 10), "search", {}, None,
                                 weight_pct=w)  # fmt: skip
                if (why := dh.hook_survive(hook, wv, port)) is not None:
                    reason = f"weight_home: {why}"
                    break
            elif (why := dh.weight_home_due(0.50, w / 100, False)) is not None:
                reason = f"weight_home: {why}"
                break
        hook.event({"kind": "run_end", "reason": reason, "counts": {}}, self.io.now)
        respawned = home = False
        if reason == "death":
            if "respawn" in roles:
                assert dh.hook_call(hook, "respawn", "death", port,
                                    lambda u, v, w: self.box.append(("click", f"{u},{v}"))
                                    is None) is None  # fmt: skip
            else:
                self.own.append(("click", "645,481"))
            respawned = True
        else:
            at("home", ("home", "F9"))
            home = True
        self.io.map = "geffen"  # the save point (a Butterfly Wing, a respawn)
        self.reason = reason
        hook.event({"kind": "player_end", "reason": reason, "home": home, "dead": not home,
                    "respawned": respawned}, self.io.now)  # fmt: skip
        return 0


def play(tmp_path: Path, d: dict[str, Any], weights: list[int], dies: bool = False
         ) -> tuple[HuntLoop, list[dict[str, Any]]]:  # fmt: skip
    p = prep(tmp_path, d)
    io_ = FakeIO()
    loop = HuntLoop(io_, weights, dies)
    demo = tmp_path / "demo"
    demo.mkdir()
    fp.play(p, io_, label="s3", stop_file=None, demo=demo, checker=lambda _p, _i: {
        "items": [{"id": "cell", "ok": True, "words": "-"}], "ok": True},
        hunt=fp.HuntCore("s3", None, run_fn=loop))  # fmt: skip
    (s,) = list(demo.iterdir())
    return loop, [json.loads(x) for x in (s / "events.jsonl").read_text().splitlines()]


def test_the_stage3_box_hunts_swaps_goes_home_at_50_percent_and_presses_home_once(
    tmp_path: Path,
) -> None:
    loop, ev = play(tmp_path, box(), [30, 45, 52, 60])
    assert loop.own == []  # every Knife swap and the way home were the box's
    assert loop.box == [("opener", "F4"), ("equip", "F5")] * 3 + [("home", "F9")]
    assert loop.reason.startswith("weight_home: the box: the flow stopped at")
    end = ev[-1]
    assert end["kind"] == "run_end" and end["reason"] == "home"
    assert "bag_full" in end["words"] and "flew her home" in end["words"]
    fired = [(e["event"], e["reading"]) for e in ev if e["kind"] == "event"]
    assert fired == [("bag_full", {"weight_percent": 52})]  # at the first read over 50 %
    hunt_end = next(e for e in ev if e["kind"] == "hunt_end")
    assert hunt_end["calls"] == 7 and hunt_end["home"]


def test_the_stage2_box_through_the_same_loop_keeps_every_press_the_runners(
    tmp_path: Path,
) -> None:
    loop, ev = play(tmp_path, box(B2), [30, 45, 52, 60])
    assert loop.kw == {"box_plays": STAGE2_PLAYS} and loop.box == []
    assert loop.own == [("opener", "F4"), ("equip", "F5")] * 3 + [("home", "F9")]
    assert loop.reason == "weight_home: weight 0.52 > 0.50"  # the runner's own weight exit
    assert not [e for e in ev if e["kind"] == "call"]


def test_a_death_respawns_through_the_box_and_presses_no_butterfly_wing(tmp_path: Path) -> None:
    loop, ev = play(tmp_path, box(), [30, 30, 30], dies=True)
    assert loop.box[-1] == ("click", "645,481") and ("home", "F9") not in loop.box
    end = ev[-1]
    assert end["reason"] == "dead" and "the box's respawn_button() pressed her respawn" in (
        end["words"])  # fmt: skip


# --- the runner: its own presses, bypassed only where the box plays them --------------------------
def _src(f: Any) -> ast.AST:
    return ast.parse(textwrap.dedent(inspect.getsource(f)))


def _fn(name: str) -> ast.FunctionDef:
    got = [n for n in ast.walk(_src(dh.run)) if isinstance(n, ast.FunctionDef) and n.name == name]
    assert len(got) == 1, name
    return got[0]


def _first_if(f: ast.FunctionDef) -> tuple[str, str, list[str]]:
    """(its first statement's test, that branch's body, the statements after it)."""
    st = f.body[1] if isinstance(f.body[0], ast.Expr) else f.body[0]  # past the docstring
    assert isinstance(st, ast.If) and not st.orelse
    i = f.body.index(st)
    return (ast.unparse(st.test), "\n".join(ast.unparse(x) for x in st.body),
            [ast.unparse(x) for x in f.body[i + 1 :]])  # fmt: skip


def test_the_runners_own_knife_home_and_respawn_presses_are_bypassed_only_where_the_box_plays() -> (
    None
):
    cases = {
        "bare_opener": ("box_knife", "box_call('knife_on', why_)\nreturn", ["opener_press(why_)"]),
        "bare_equip_press": ("box_knife and why_ != 'safety'",
                             "box_call('knife_back', why_)\nreturn", ["press('equip', why_)"]),
        "respawn_press": ("box_respawn", "box_call('respawn', 'death')\nreturn",
                          ["two_motion_click(at_[0], at_[1])"]),
        "home_press": ("box_home", "box_call('home', 'end')\nreturn", ["press('home', 'end')"]),
    }  # fmt: skip
    for name, want in cases.items():
        assert _first_if(_fn(name)) == want, name
    cp = _fn("confirm_press")
    assert ast.unparse(cp.body[-1]) == "two_motion_click(cat_[0], cat_[1])"
    assert "box_call('respawn_confirm', 'death')" in ast.unparse(cp)

    # box_call has exactly these five callers in run()
    def calls_box(f: ast.AST) -> bool:
        return any(isinstance(c, ast.Call) and ast.unparse(c.func) == "box_call"
                   for c in ast.walk(f))  # fmt: skip

    callers = {f.name for f in ast.walk(_src(dh.run)) if isinstance(f, ast.FunctionDef)
               and f.name not in ("box_call", "run") and calls_box(f)}  # fmt: skip
    assert callers == {"bare_opener", "bare_equip_press", "respawn_press", "confirm_press",
                       "home_press"}  # fmt: skip
    # the runner's own presses are what they were: the opener's three lines, the respawn's two
    # motions then the click (dungeon@9.41's respawn_press, as a helper now)
    op = [ast.unparse(x) for x in _fn("opener_press").body[1:]]
    assert op == [
        "assert opener_key is not None",
        "agent_raw.keys(opener_key)",
        "counts['opener'] += 1",
        "ev({'kind': 'press', 'what': 'opener', 'key': opener_key, 'why': why_})",
    ]
    tm = [ast.unparse(x) for x in _fn("two_motion_click").body[1:]]
    assert tm == ["x_, y_ = (gx0 + u_, gy0 + v_)", "agent_raw.move(x_ + 4, y_ + 3)",
                  "time.sleep(0.08)", "agent_raw.move(x_, y_)", "time.sleep(0.3)",
                  "agent_raw.click(x_, y_)"]  # fmt: skip
    src = inspect.getsource(dh.run)
    assert "press=bare_equip_press," in src and "opener=bare_opener if opener_key" in src
    assert "press=home_press," in src
    # the respawn with the box: its confirm function decides whether a confirmation is pressed
    assert "cat_ = (0, 0) if 'respawn_confirm' in box_roles_ else None" in ast.unparse(_src(dh.run))


def test_the_weight_read_calls_the_box_there_and_keeps_the_runners_red_rule() -> None:
    tree = _src(dh.run)
    w = [n for n in ast.walk(tree) if isinstance(n, ast.If)
         and ast.unparse(n.test) == "box_weight"]  # fmt: skip
    assert len(w) == 1
    box_part = ast.unparse(ast.Module(body=w[0].body, type_ignores=[]))
    own = ast.unparse(ast.Module(body=w[0].orelse, type_ignores=[]))
    assert own == ("why_wh = weight_home_due(getattr(a, 'weight_home', None), hs.w_share, "
                   "hs.red_seen)")  # fmt: skip
    assert "weight_home_due(getattr(a, 'weight_home', None), None, hs.red_seen) if w_now is None" \
        in box_part  # fmt: skip
    assert "hook_survive(hook, HuntTick(" in box_part and "int(round(w_now * 100))" in box_part
    assert "reason = f'weight_home: {why_bw}'" in box_part and "break" in box_part
    # it sits in the UI watch (never mid-fight): after the weight read, inside `mode != 'fight'`
    ui = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.If)
        and ast.unparse(n.test) == "tick - hs.last_ui >= UI_EVERY_S and hs.mode != 'fight'"
    )
    assert w[0] in list(ast.walk(ui))


def test_box_plays_refused_names_each_stage3_refusal_before_any_input() -> None:
    kw: dict[str, Any] = {"heal_candy": False, "boss_walk": False, "bosses": ("Stormy Knight",)}
    roles = {"knife_on": "opener", "knife_back": "armed", "home": "home", "respawn": "save_point",
             "respawn_confirm": "save_point"}  # fmt: skip
    all_ = STAGE3_PLAYS  # stage 4a's model and recipes: test_box_recipes.py
    assert dh.box_plays_refused(all_, _Hook(), roles=roles, **kw) is None
    assert dh.box_plays_refused([], None, **kw) is None  # the CLI: nothing to check
    assert "without its functions" in str(dh.box_plays_refused(["knife"], _Hook(), **kw))
    assert "box_roles ['heal']" in str(
        dh.box_plays_refused(["knife"], _Hook(), roles={"heal": "x"}, **kw)
    )
    assert "without their play" in str(dh.box_plays_refused([], _Hook(), roles=roles, **kw))

    class NoCall:
        def survive(self, view: Any, press: Any) -> None:
            return None

    assert "hook.call" in str(dh.box_plays_refused(all_, NoCall(), roles=roles, **kw))
    assert "swaps no Knife" in str(dh.box_plays_refused(all_, _Hook(), roles=roles,
                                                        knife_swap=False, **kw))  # fmt: skip
    assert "--player-mode" in str(dh.box_plays_refused(all_, _Hook(), roles=roles, player=False,
                                                       **kw))  # fmt: skip
    assert "respawn is off" in str(dh.box_plays_refused(all_, _Hook(), roles=roles,
                                                        respawn=False, **kw))  # fmt: skip
    assert "Butterfly Wing key" in str(dh.box_plays_refused(all_, _Hook(), roles=roles,
                                                            home_key=None, **kw))  # fmt: skip
    assert "one of ['opener', 'armed']" in str(dh.box_plays_refused(
        ["knife"], _Hook(), roles={"knife_on": "x", "knife_back": "armed"}, **kw))  # fmt: skip


def test_the_cli_and_the_old_run_path_are_unchanged() -> None:
    sig = inspect.signature(dh.run)
    assert sig.parameters["box_plays"].default == () and sig.parameters["box_roles"].default is None
    assert "return run(a)" in inspect.getsource(dh.main)  # no hook, no box
    assert dh.VERSION == "dungeon@8.7" and dh.BOX_FUNCTIONS_VERSION == "9.50"
    assert dh.BOX_RECIPES_VERSION == "9.51"  # stage 4a (test_box_recipes.py)
    assert dh.BOX_EAT_VERSION == live.VERSION == "9.52"  # 2026-11-14 (test_box_eat.py)
    assert dh.BOX_PLAYS == live.PLAYS and set(STAGE3_PLAYS) < set(dh.BOX_PLAYS)
    # opener_seq's default reads exactly as before; "armed" only with the box's other answer
    assert inspect.signature(dh.opener_seq).parameters["ends"].default == "opener"
    assert inspect.signature(dh.BareCtl).parameters["opener_ends"].default == "opener"
    hook_steps = copy.deepcopy(fn.STEPS_WAIT_MAX_S)
    assert hook_steps == 1.0 and fn.STEPS_MAX == 4


@pytest.mark.parametrize("ends", ["opener", "armed"])
def test_opener_seq_reads_back_what_the_body_leaves(ends: str) -> None:
    sim = TDH._OpenerSim()
    bio = sim.io()
    presses: list[str] = []

    def body(why: str) -> None:  # the box's knife_on body on the simulated client
        presses.append("F4")
        sim.opener(why)
        if ends == "armed":
            sim.t += 0.1
            presses.append("F5")
            sim.press(why)

    bio.opener = body
    res = dh.opener_seq(bio, TDH._opener_read(), "box", ends)
    assert res["ok"] and res["presses"] == 1
    assert res["state"] == ("opener" if ends == "opener" else "armed")
    assert res["bare"] is (ends == "opener")  # the bare phase only with the Knife worn


def _unused(_c: Callable[..., Any]) -> None:  # keeps typing's Callable import honest
    return None
