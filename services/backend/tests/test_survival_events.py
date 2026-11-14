"""Live blocks stage 2 (Batt 2026-11-13: "Heal, Fly Wing, Knife swap: write every one as a
FUNCTION. Heal: press F1 (the White Potion) when HP < 30 %. Fly Wing: press F8 when a boss is seen
or HP < 25 %"; docs/planning/live-blocks.md 3.2; dungeon@9.49): the box's survival EVENTS play
inside the hunt core through its tick hook.

Offline, no game. A fake HUNT LOOP stands in for dungeon_hunt.run at its survival point: per tick
it calls the REAL player's hook (flow_play.HuntHook: tick, then survive), presses the box's keys
through a fake of the runner's own press (box_press: its record mirrored back, its paced tap), and
then runs the runner's OWN sustain() with the box's handlers off -- what run() does there. The
runner's loop itself is checked by its AST (the call, its place, the after-the-fly steps)."""

from __future__ import annotations

import ast
import copy
import inspect
import json
import sys
import textwrap
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_hunt as dh  # noqa: E402
import flow_play as fp  # noqa: E402
import flow_run as fr  # noqa: E402

from poring_flow import live  # noqa: E402
from poring_flow import project as pj  # noqa: E402

# stage 2's own box: the ready-made box as stage 2 left it (the B2 arm of stage 3's A/B; the stage-3
# box is test_box_functions.py's)
XMAS = ROOT / "services/frontend/src/lib/flow/fixtures/project_xmas_dun02_stage2.json"
TICK = 0.4  # the runner's main tick on xmas_dun02 (the 2026-11-13 runs: ~2.4 a second)
STRAT = {**dh.STRATEGIES["P2"], "max_hp": 5070}  # the Run path's strategy, the Rogue's max HP


def lit(v: Any) -> dict[str, Any]:
    return {"kind": "lit", "value": v}


def sense(n: str) -> dict[str, Any]:
    return {"kind": "sense", "sensor": n, "args": {}}


def cmp(op: str, left: Any, right: Any) -> dict[str, Any]:
    return {"kind": "cmp", "op": op, "left": left, "right": right}


def press(k: str) -> dict[str, Any]:
    return {"kind": "action", "block": "press_key", "concept": "ui.press_hotkey",
            "params": {"key": lit(k)}, "timeout_s": 2.0, "on_fail": "stop", "outcome_to": None,
            "note": None}  # fmt: skip


def box(mutate: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    """The ready-made one-box project (its time box under the run's maximum), changed by
    ``mutate(survival_tab)``; the survival tab removed when ``mutate`` deletes its defs."""
    d = json.loads(XMAS.read_text())
    d["max_runtime_s"] = 600
    if mutate is not None:
        surv = next(t for t in d["nodes"][0]["tabs"] if t["name"] == "survival")
        mutate(surv)
        if not surv["defs"]:
            d["nodes"][0]["tabs"].remove(surv)
    return d


def set_def(tab: dict[str, Any], name: str, **changes: Any) -> None:
    """Change one def of the survival tab (``on``'s fields: ``on={...}`` merges into it)."""
    d = next(x for x in tab["defs"] if x["name"] == name)
    on = changes.pop("on", None)
    d.update(changes)
    if on is not None:
        d["on"] = {**d["on"], **on}


def prep(tmp_path: Path, d: dict[str, Any]) -> fp.Prepared:
    got = fp.prepare(json.dumps(d), "xmas_dun02", 3600)
    assert isinstance(got, fp.Prepared), got
    return got


class FakeIO(fp.LiveIO):
    """A fake clock; every input recorded; her reads steady (the box reads the runner's ticks)."""

    def __init__(self) -> None:
        self.now = 0.0
        self.out: list[tuple[Any, ...]] = []
        self.agent, self.screen = "AGENT", "SCREEN"

    def clock(self) -> float:
        return self.now

    def sleep(self, s: float) -> None:
        self.now += s

    def ns(self) -> int:
        return int(self.now * 1e9)

    def senses(self) -> dict[str, Any]:
        return {"hp_percent": 100, "sp_percent": 100, "weight_percent": 10, "is_dead": False,
                "map": "xmas_dun02"}  # fmt: skip

    def open(self) -> None:
        self.out.append(("open",))

    def ui_clear(self) -> None:
        self.out.append(("ui_clear",))

    def tap(self, code: str) -> None:
        self.out.append(("tap", code))
        self.now += 0.1

    def release(self) -> None:
        self.out.append(("release",))


def ok_check(_p: Any, _io: Any) -> dict[str, Any]:
    return {"items": [{"id": "cell", "ok": True, "words": "the minimap is xmas_dun02's"}],
            "ok": True}  # fmt: skip


# A tick of the fake loop: (HP percent or None, the boss line's name or None, quick)
Tick = tuple[int | None, str | None, bool]


class HuntLoop:
    """dungeon_hunt.run(a, hook=..., session=..., box_plays=...) at its survival point (the module
    docstring): ``ticks`` one TICK apart. ``port`` is the runner's own press of a box key."""

    def __init__(self, io_: FakeIO, ticks: list[Tick]) -> None:
        self.io, self.ticks = io_, ticks
        self.kw: dict[str, Any] = {}
        self.port: list[tuple[int, str, str]] = []  # (tick index, role, why): the box's presses
        self.own: list[tuple[float, str, str]] = []  # the runner's own sustain presses
        self.reason = ""

    def __call__(self, a: Any, *, hook: Any = None, session: Any = None, **kw: Any) -> int:
        self.kw = kw
        plays = frozenset(kw.get("box_plays", ()))
        roles = {**({"F1": "potion"} if "potion" in plays else {}),
                 **({"F8": "fly"} if plays & {"fly_hp", "boss_fly"} else {})}  # fmt: skip

        def port(code: str, why: str) -> str | None:  # dungeon_hunt run's box_press
            role = roles.get(code)
            if role is None:
                return None
            self.io.out.append(("press", role, code))
            self.port.append((tick_i, role, why))
            hook.event({"kind": "press", "what": role, "key": code, "why": why}, self.io.now)
            self.io.now += 0.1  # the runner's paced tap (agent.keys)
            return role

        st, off = dh.Sustain(), plays & {"potion", "fly_hp"}
        hook.event({"kind": "run_start", "map": "xmas_dun02"}, self.io.now)
        reason = "time_box"
        tick_i = -1
        for tick_i, (hp, boss, quick) in enumerate(self.ticks):  # noqa: B007 -- port reads it
            self.io.now += TICK
            now = self.io.now
            view = dh.HuntTick(now, hp, 60, False, (10, 10), "search", {}, None, boss, quick)
            if not quick and (why := dh.hook_stop(hook, view)) is not None:
                reason = f"stopped: {why}"
                break
            n0 = len(self.port)
            why = dh.hook_survive(hook, view, port) if plays else None  # run(): `if box_on:`
            flew = any(r == "fly" for _, r, _ in self.port[n0:])
            if flew:
                st.fly = self.io.now  # the runner's after-the-fly step: its 3-s Fly Wing pace
            if why is not None:
                reason = f"stopped: {why}"
                break
            if hp is not None:  # the runner's own survival, the box's handlers off
                skip = off | ({"potion"} if flew else set())
                for what, w in dh.sustain(st, now, hp / 100, 0.6, STRAT, off=frozenset(skip)):
                    self.own.append((round(now, 2), what, w))
                    hook.event({"kind": "press", "what": what, "key": "?", "why": w}, now)
        hook.event({"kind": "run_end", "reason": reason, "counts": {}}, self.io.now)
        hook.event({"kind": "player_end", "reason": reason, "home": False, "dead": False,
                    "respawned": False}, self.io.now)  # fmt: skip
        self.reason = reason
        return 0


def play(tmp_path: Path, ticks: list[Tick], d: dict[str, Any] | None = None
         ) -> tuple[HuntLoop, FakeIO, list[dict[str, Any]]]:  # fmt: skip
    p = prep(tmp_path, d if d is not None else box())
    io_ = FakeIO()
    loop = HuntLoop(io_, ticks)
    demo = tmp_path / "demo"
    demo.mkdir()
    fp.play(p, io_, label="s2", stop_file=None, demo=demo, checker=ok_check,
            hunt=fp.HuntCore("s2", None, run_fn=loop))  # fmt: skip
    (s,) = list(demo.iterdir())
    return loop, io_, [json.loads(x) for x in (s / "events.jsonl").read_text().splitlines()]


# 28 at a fall of ~127 HP/s over 2 s (under the runner's 150 HP/s rate fly), then 24 at ~225
FALL = (33, 33, 32, 31, 30, 28, 24, 24, 24)


def roles(loop: HuntLoop) -> list[str]:
    return [r for _, r, _ in loop.port]


# --- the box and what it hands over ---------------------------------------------------------------
def test_the_box_plays_three_of_the_runners_handlers_and_prepare_passes_them(
    tmp_path: Path,
) -> None:
    p = pj.from_json(XMAS.read_text())
    c, found = pj.project_lint(p)
    assert [f.text for f in found if f.severity == "error"] == []
    assert c.flow is not None and live.problems(c.flow) == []
    plan = live.hunt_plan(c.flow, "xmas_dun02")
    assert plan.keys == {"heal": "F1", "fly": "F8"} and plan.events == ("fly_away", "drink")
    assert plan.plays == frozenset({"potion", "fly_hp", "boss_fly"})
    rp = prep(tmp_path, box()).runners["xmas_dun02"]
    assert (rp.events, rp.plays) == (plan.events, plan.plays)
    loop, _io, ev = play(tmp_path, [(100, None, False)])
    assert loop.kw == {"box_plays": ["boss_fly", "fly_hp", "potion"]}  # run(box_plays=...)
    start = next(e for e in ev if e["kind"] == "hunt_start")
    assert start["events"] == ["fly_away", "drink"]
    assert start["box_plays"] == ["boss_fly", "fly_hp", "potion"]


def test_hp_50_to_28_drinks_once_not_every_tick_and_the_runners_potion_stays_off(
    tmp_path: Path,
) -> None:
    # 50 -> 28 one point every two ticks (2 at the end): ~114 HP/s over 2 s, under the runner's
    # 150 HP/s rate fly; from 39 on every tick is under the runner's own potion line (P2: 40 %)
    hps = [v for v in range(50, 29, -1) for _ in (0, 1)] + [28, 28]
    loop, io_, ev = play(tmp_path, [(h, None, False) for h in hps])
    assert roles(loop) == ["potion"]  # once: the next tick is 0.4 s later, the pace is 0.7 s
    assert loop.port[0] == (len(hps) - 2, "potion", "box drink (hp_percent 28)")  # not at 30
    assert loop.own == []  # the runner's own potion and Fly Wing never pressed
    fired = [e for e in ev if e["kind"] == "event"]
    assert [(e["event"], e["mode"], e["in"], e["reading"]) for e in fired] == [
        ("drink", "insert", "hunt", {"hp_percent": 28})]  # fmt: skip
    assert fired[0]["node"] == "xmas_dun02/survival/drink"
    # an insert: no ReleaseAll before it (nothing was held); the one after is the run's end
    assert io_.out == [("open",), ("ui_clear",), ("press", "potion", "F1"), ("release",)]
    # held under 30 %, it drinks again at its pace (0.7 s after its last press ended)
    (tmp_path / "held").mkdir()
    loop2, _io2, _ev2 = play(tmp_path / "held", [(28, None, False)] * 4)
    assert [(i, r) for i, r, _ in loop2.port] == [(0, "potion"), (2, "potion")]  # not each tick


def test_28_to_24_flies_with_a_release_first_and_the_runner_does_not_fly_too(
    tmp_path: Path,
) -> None:
    loop, io_, ev = play(tmp_path, [(h, None, False) for h in FALL])
    assert [(i, r) for i, r, _ in loop.port] == [(5, "potion"), (6, "fly"), (7, "potion")]
    assert loop.port[1][2] == "box fly_away (hp_percent 24, sees_boss False)"
    i = io_.out.index(("press", "fly", "F8"))
    assert io_.out[i - 1] == ("release",)  # a pre-empt: ReleaseAll before its first batch
    # once per fall: the next ticks under 25 % fly no more (its condition must go false first);
    # the drink (repeating, under 30 %) goes on at its pace, not on the fly's own tick
    # the runner: 32 -> 24 in 1.8 s is ~225 HP/s under 50 %, over its rate fly's line -- but the
    # box's Fly Wing just went (its 3-s pace, as after its own), and its HP fly and potion are off
    assert loop.own == []
    fly_ev = next(e for e in ev if e["kind"] == "event" and e["event"] == "fly_away")
    assert fly_ev["mode"] == "preempt" and fly_ev["reading"] == {"hp_percent": 24,
                                                                 "sees_boss": False}  # fmt: skip


def test_the_runners_hp_rate_fly_still_fires_while_the_box_plays(tmp_path: Path) -> None:
    # 60 -> 40 in 1.2 s: ~845 HP/s under 50 %, never under the box's 30 / 25 %
    loop, _io, _ev = play(tmp_path, [(h, None, False) for h in (60, 60, 52, 44, 40, 40)])
    assert loop.port == []
    assert [w for _, w, _ in loop.own] == ["fly"] and loop.own[0][2].startswith("rate ")


def test_a_boss_line_flies_at_full_hp_once_per_sighting(tmp_path: Path) -> None:
    boss = "Stormy Knight"
    ticks: list[Tick] = [(100, None, False), (100, boss, False), (100, boss, False)]
    ticks += [(100, None, False)] * 8 + [(100, "Garm Baby", False)]  # 3.2 s later: re-armed
    loop, io_, ev = play(tmp_path, ticks)
    # the 2nd line is the same sighting (no edge); 3 s after its Fly Wing, a line-less tick
    # re-arms it; the next line flies again
    assert [(i, r) for i, r, _ in loop.port] == [(1, "fly"), (11, "fly")]
    assert loop.port[0][2] == "box fly_away (hp_percent 100, sees_boss True)"
    assert loop.own == []
    readings = [e["reading"] for e in ev if e["kind"] == "event"]
    assert readings == [{"hp_percent": 100, "sees_boss": True}] * 2
    assert io_.out.count(("release",)) >= 2  # each Fly Wing pre-empts


def test_quick_reads_inside_a_long_action_play_the_box_but_never_a_boss(tmp_path: Path) -> None:
    # guard_tick's quick read: no Battle Log there, so its boss is unknown whatever it carries
    loop, _io, ev = play(tmp_path, [(100, "Stormy Knight", True), (24, None, True)])
    assert roles(loop) == ["fly", "potion"]  # the pre-empt first, the insert at the same point
    fired = [(e["event"], e["reading"]) for e in ev if e["kind"] == "event"]
    assert fired == [("fly_away", {"hp_percent": 24, "sees_boss": None}),
                     ("drink", {"hp_percent": 24})]  # fmt: skip
    # a tick with no HP read and no boss line decides nothing (the runner's own rule)
    loop2_dir = tmp_path / "n"
    loop2_dir.mkdir()
    loop2, _io2, ev2 = play(loop2_dir, [(None, None, False), (None, None, True)])
    assert loop2.port == [] and not [e for e in ev2 if e["kind"] == "event"]


def test_a_box_without_survival_events_leaves_the_runners_handlers_on(tmp_path: Path) -> None:
    d = box(lambda t: t["defs"].clear())
    assert [t["name"] for t in d["nodes"][0]["tabs"]] == ["main", "keys"]
    rp = prep(tmp_path, d).runners["xmas_dun02"]
    assert (rp.events, rp.plays) == ((), frozenset())
    loop, _io, _ev = play(tmp_path, [(h, None, False) for h in (100, 35, 35, 15)], d)
    assert loop.kw == {}  # no box_plays: run() exactly as stage 1 (no survive call)
    assert loop.port == []
    # the runner's own (P2): a potion under 40 % (the next tick is inside its 0.7-s pace), its
    # Fly Wing under 20 %
    assert [w for _, w, _ in loop.own] == ["potion", "fly"]


def test_an_event_that_cannot_play_inside_the_hunt_core_refuses_before_any_input(
    tmp_path: Path,
) -> None:
    wait = {"kind": "wait_until", "cond": lit(False), "timeout_s": 0.5, "outcome_to": None}
    weight = cmp(">", sense("weight_percent"), lit(80))
    heal = {"kind": "call", "proc": "heal", "args": [], "kwargs": {}}
    cases: list[tuple[Callable[[dict[str, Any]], None], str]] = [
        (lambda t: set_def(t, "drink", body=[press("F4")]),
         "presses F4 inside the hunt core: there the box presses only dungeon_hunt's heal (F1) "
         "and fly (F8) keys"),
        (lambda t: set_def(t, "drink", body=[wait, heal]),
         "a wait_until statement cannot play inside the hunt core"),
        # stage 3: an event that reads the weight inside the hunt core is the weight home
        (lambda t: set_def(t, "fly_away", on={"when": weight}),
         "fly_away reads weight_percent() inside the hunt core: there it is the weight home, and "
         "its body is one stop"),
        (lambda t: set_def(t, "fly_away", on={"then": "relocate"}),
         "fly_away ends with then=relocate: inside the hunt core an event must resume"),
        (lambda t: set_def(t, "fly_away", on={"when": cmp("<", sense("sp_percent"), lit(10))}),
         "on a condition that reads neither hp_percent() nor sees_boss()"),
        (lambda t: set_def(t, "drink", body=[{"kind": "return", "value": None}]),
         "drink presses no key inside the hunt core"),
    ]  # fmt: skip
    for i, (mutate, words) in enumerate(cases):
        d = copy.deepcopy(box(mutate))
        got = fp.prepare(json.dumps(d), "xmas_dun02", 3600)
        assert isinstance(got, str) and "refused before any input" in got, (i, got)
        assert words in got, (i, got)
        c = pj.compile_project(pj.from_json(json.dumps(d)))
        assert c.flow is not None and any(words in b.words for b in live.problems(c.flow)), i
    assert not list(tmp_path.glob("*"))  # pure: no session, no input path


def test_an_events_limit_ends_the_run_through_the_runners_normal_end(tmp_path: Path) -> None:
    tight = box(lambda t: set_def(t, "drink", on={"max_fires_per_10min": 2}))
    loop, io_, ev = play(tmp_path, [(28, None, False)] * 10, tight)
    assert roles(loop) == ["potion", "potion"]  # the third fire is the runaway, not a press
    assert loop.reason.startswith("stopped: the box: an event fired more often")
    end = ev[-1]
    assert end["kind"] == "run_end" and end["reason"] == "handler_runaway"
    assert "max_fires_per_10min" in end["words"] and io_.out[-1] == ("release",)


def test_the_record_counts_potions_flies_and_fired_events_for_the_live_line(
    tmp_path: Path,
) -> None:
    _loop, _io, ev = play(tmp_path, [(h, None, False) for h in FALL])
    lv = fr.Live()
    for e in ev:
        lv.feed(e)
    s = lv.summary()
    assert (s["potions"], s["flies"], s["fired"]) == (2, 1, 3)  # one press record each, mirrored
    assert s["keys"] == 3  # the player's own key records (in the hunt core: "in": "hunt")
    assert {e.get("in") for e in ev if e["kind"] == "key"} == {"hunt"}
    hunt_end = next(e for e in ev if e["kind"] == "hunt_end")
    assert hunt_end["survive_calls"] == len(FALL) and hunt_end["ticks"] == len(FALL)


# --- the runner: its own handlers, switched off by name ------------------------------------------
def test_sustain_off_drops_the_potion_and_the_hp_fly_and_keeps_the_rate_fly() -> None:
    st = dh.Sustain()
    assert dh.sustain(st, 0.0, 0.35, 0.5, STRAT) == [("potion", "hp 0.35")]  # as before
    st = dh.Sustain()
    both = frozenset({"potion", "fly_hp"})
    assert dh.sustain(st, 0.0, 0.15, 0.5, STRAT, off=both) == []
    assert dh.sustain(st, 3.5, 0.15, 0.5, STRAT, off=both) == []  # still under fly_below: no fly
    st = dh.Sustain()
    dh.sustain(st, 0.0, 0.48, 0.5, STRAT, off=both)
    got = dh.sustain(st, 1.0, 0.40, 0.5, STRAT, off=both)  # 405 HP/s under 50 %: the rate fly
    assert got and got[0][0] == "fly" and got[0][1].startswith("rate ")
    assert [p[0] for p in dh.sustain(dh.Sustain(), 0.0, 0.15, 0.5, STRAT,
                                     off=frozenset({"potion"}))] == ["fly"]  # fmt: skip


def test_box_plays_refused_names_each_refusal_before_any_input() -> None:
    class Hook:
        def survive(self, view: Any, press: Any) -> str | None:
            return None

    kw: dict[str, Any] = {"heal_candy": False, "boss_walk": False, "bosses": ("Stormy Knight",)}
    assert dh.box_plays_refused([], None, **kw) is None  # the CLI: nothing to check
    assert dh.box_plays_refused(["potion", "fly_hp", "boss_fly"], Hook(), **kw) is None  # stage 2's
    assert "not one of" in str(dh.box_plays_refused(["stock"], Hook(), **kw))
    assert "hook.survive" in str(dh.box_plays_refused(["potion"], None, **kw))
    assert "--heal-candy" in str(dh.box_plays_refused(["potion"], Hook(),
                                                      **{**kw, "heal_candy": True}))  # fmt: skip
    assert "--boss-walk" in str(dh.box_plays_refused(["boss_fly"], Hook(),
                                                     **{**kw, "boss_walk": True}))  # fmt: skip
    assert "reads no boss" in str(dh.box_plays_refused(["boss_fly"], Hook(),
                                                       **{**kw, "bosses": ()}))  # fmt: skip
    assert dh.hook_survive(None, None, lambda c, w: None) is None  # type: ignore[arg-type]


# --- the runner's loop, by its AST ---------------------------------------------------------------
def _src(fn: Any) -> ast.AST:
    return ast.parse(textwrap.dedent(inspect.getsource(fn)))


def _loop() -> ast.While:
    loops = [n for n in ast.walk(_src(dh.run)) if isinstance(n, ast.While)
             and ast.unparse(n.test) == "time.monotonic() < t_end"]  # fmt: skip
    assert len(loops) == 1
    return loops[0]


def _assigned(node: ast.AST) -> set[str]:
    out: set[str] = set()
    for n in ast.walk(node):
        for t in n.targets if isinstance(n, ast.Assign) else []:
            for x in t.elts if isinstance(t, ast.Tuple) else [t]:
                out.add(ast.unparse(x))
    return out


def _continues(stmts: list[ast.stmt]) -> int:
    n = 0
    for st in stmts:
        if isinstance(st, ast.Continue):
            n += 1
        elif not isinstance(st, ast.For | ast.While | ast.FunctionDef):
            for f in ("body", "orelse", "finalbody"):
                n += _continues(getattr(st, f, []) or [])
            for h in getattr(st, "handlers", []) or []:
                n += _continues(h.body)
    return n


def test_the_box_plays_once_a_tick_before_the_runners_own_survival() -> None:
    body = _loop().body
    # (stage 3's weight read calls it too, inside the UI watch: test_box_functions.py)
    at = [i for i, st in enumerate(body) if "hook_survive(hook" in ast.unparse(st)
          and isinstance(st, ast.If) and ast.unparse(st.test) == "box_on"]  # fmt: skip
    assert len(at) == 1  # ONE top-level statement of the loop: every tick that gets there
    st = body[at[0]]
    assert isinstance(st, ast.If) and ast.unparse(st.test) == "box_on"
    assert "HuntTick(tick, pct, spp, bool(dead), hs.here, hs.mode, MappingProxyType(counts), " \
           "img, boss_hit)" in ast.unparse(st)  # fmt: skip
    own = next(
        i
        for i, x in enumerate(body)
        if isinstance(x, ast.If)
        and ast.unparse(x.test) == "frac is not None"
        and "sustain(" in ast.unparse(x)
    )
    assert at[0] < own and "off=off_t" in ast.unparse(body[own])
    # the boss read it carries is the Battle Log's, before the Garm Baby box sets boss_hit
    garm = next(i for i, x in enumerate(body) if "garm_now = True" in ast.unparse(x))
    assert at[0] < garm
    assert _continues(body[: at[0]]) == 0  # no tick skips it (the stop hook's rule too)


def test_a_box_fly_takes_the_runners_own_after_the_fly_steps() -> None:
    body = _loop().body
    box_if = next(st for st in body if isinstance(st, ast.If) and ast.unparse(st.test) == "box_on")
    after = next(n for n in ast.walk(box_if) if isinstance(n, ast.If)
                 and ast.unparse(n.test) == "box_fly is not None")  # fmt: skip
    own = next(
        n
        for n in ast.walk(_loop())
        if isinstance(n, ast.If) and ast.unparse(n.test) == "what == 'fly'"
    )  # the runner's own sustain fly
    want = _assigned(own) - {"hs.sitting"}  # its stand-up is box_press's (before the press)
    assert want == {"hs.fly_at", "hs.lock", "hs.goal_path", "hs.loot_list", "hs.fight_ref",
                    "hs.mode", "hs.here", "hs.last_taken"}  # fmt: skip
    assert want <= _assigned(after) and "st.fly" in _assigned(after)
    assert "time.sleep(1.0)" in ast.unparse(after) and "time.sleep(1.0)" in ast.unparse(own)
    # on a boss line the box decided, its Fly Wing ends the tick as the runner's boss fly does
    boss = next(n for n in ast.walk(_loop()) if isinstance(n, ast.If)
                and ast.unparse(n.test) == "box_line")  # fmt: skip
    assert "box_fight.clear()" in ast.unparse(boss) and "continue" in ast.unparse(boss)
    # inside a long action (guard_tick): the box too, its Fly Wing ends the action (escaped)
    gt = next(n for n in ast.walk(_src(dh.run)) if isinstance(n, ast.FunctionDef)
              and n.name == "guard_tick")  # fmt: skip
    g = ast.unparse(gt)
    assert "hook_survive(hook, HuntTick(" in g and "escaped[0] = True" in g and "off=off_q" in g
    # the press itself is the runner's own (its before-steps, count, record, stock read)
    bp = next(n for n in ast.walk(_src(dh.run)) if isinstance(n, ast.FunctionDef)
              and n.name == "box_press")  # fmt: skip
    assert "press(what_, why)" in ast.unparse(bp) and "press('stand', 'escape')" in ast.unparse(bp)


def test_the_cli_and_the_old_run_path_are_unchanged() -> None:
    sig = inspect.signature(dh.run)
    assert sig.parameters["box_plays"].default == ()
    assert "return run(a)" in inspect.getsource(dh.main)  # no hook, no box
    assert dh.VERSION == "dungeon@8.7" and dh.SURVIVAL_EVENTS_VERSION == "9.49"
    argv = fr.command(fr.FLOWS["xmas_dun02_rogue"], "x")[9:]
    assert "box_plays" not in vars(dh.args_for(argv))  # a run() argument, never a CLI flag
    assert inspect.signature(dh.sustain).parameters["off"].default == frozenset()


def test_a_press_the_mux_refuses_inside_the_hunt_core_ends_it_as_the_runners_own_stop(
    tmp_path: Path,
) -> None:
    """ro_agent.Stop from the runner's own press (the mux: the lease, the gate, the interlock)
    propagates as in the runner alone: its session ends, the hunt core fails, the run ends."""

    class Refusing(HuntLoop):
        def __call__(self, a: Any, *, hook: Any = None, session: Any = None, **kw: Any) -> int:
            def port(code: str, why: str) -> str | None:
                raise SystemExit("mux refused 1/1 (['client_not_foreground']): stopping")

            view = dh.HuntTick(1.0, 28, 60, False, (10, 10), "search", {}, None)
            dh.hook_survive(hook, view, port)
            raise AssertionError("the refusal did not reach the runner")

    p = prep(tmp_path, box())
    io_ = FakeIO()
    demo = tmp_path / "demo"
    demo.mkdir()
    fp.play(p, io_, label="r", stop_file=None, demo=demo, checker=ok_check,
            hunt=fp.HuntCore("r", None, run_fn=Refusing(io_, [])))  # fmt: skip
    (s,) = list(demo.iterdir())
    end = json.loads((s / "events.jsonl").read_text().splitlines()[-1])
    assert end["reason"] == "dungeon_hunt_failed" and "client_not_foreground" in end["words"]
    assert io_.out[-1] == ("release",)
