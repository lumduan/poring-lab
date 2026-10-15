"""scripts/walk17.py (walk@17, demonstrations 3.32; design docs/planning/walk17.md): walk@15's
decision code, rebound (not copied), + A (the minimap first, /where once per need), B (warp areas
are not walkable for a walk), C (long walks as chained legs, no click beyond 14 server steps), D
(the harness as on main). walk@16's F is NOT carried. walk@15's module is untouched.

No test here reaches the client or the live typing guard: /where is a fake (or a guard on a
temporary state file), and the chat transport is refused outright."""

from __future__ import annotations

import builtins
import importlib.util
import inspect
import json
import sys
import time
import types
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parents[2] / "scripts"
BAND = (100, 60, 1180, 680)
CHAIN = ("walk5", "walk6", "reloc2", "where_fix", "walk7", "walk8", "walk9", "walk10", "walk11",
         "work_zone", "walk12", "walk13", "walk14", "walk15", "walk17")  # fmt: skip


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mods() -> tuple[ModuleType, ...]:
    sys.path.insert(0, str(SCRIPTS))
    for name in CHAIN:
        _load(name, SCRIPTS / f"{name}.py")
    return tuple(sys.modules[n] for n in ("walk17", "walk15", "walk14", "walk13", "walk12",
                                          "walk11"))  # fmt: skip


def names(code: types.CodeType) -> set[str]:
    out = set(code.co_names)
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            out |= names(c)
    return out


def consts(code: types.CodeType) -> set[Any]:
    out = {c for c in code.co_consts if not isinstance(c, types.CodeType)}
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            out |= consts(c)
    return out


# --- reuse ----------------------------------------------------------------------------------------


def test_walk17_reuses_walk15s_code_and_leaves_it_untouched(mods: Any) -> None:
    w17, w15, w14, w13, w12, w11 = mods
    rebound = {
        "_route14": inspect.unwrap(w14.walk_route),  # walk@14's route loop (walk@15's)
        "_leg15": w15._walk_route,  # walk@15's route: VISITED cleared, then the loop
        "run11": w11.run,  # the harness as on main (3.29a)
        "_run12": w12.run,
        "finish_session": w12.finish_session,
        "finish_failed": w12.finish_failed,
        "substitute_goal": w11.substitute_goal,  # B: they PLAN, so their planner is walk@17's
        "npc_substitute": w13.npc_substitute,
        "_side14": w14.side_cell,
    }
    for name, orig in rebound.items():
        got = getattr(w17, name)
        assert got.__code__ is orig.__code__, name  # the SAME code object: nothing copied
        assert got.__globals__ is vars(w17), name
    assert inspect.unwrap(w17.walk_route) is w17._walk_route
    assert w17.UNITS is w15.UNITS and w17.VISITED is w15.VISITED  # walk@15's E fills this set
    assert w17.WALK8_RULE == "walk@17" and w15.WALK8_RULE == "walk@15"
    # walk@15 is untouched: its own planner, route loop, click step and relocalisation
    assert w15.w6 is sys.modules["walk6"] and w17.w6 is not w15.w6
    assert w15._route14.__globals__ is vars(w15)
    assert inspect.unwrap(w15.walk_route).__globals__ is vars(w15)
    assert inspect.unwrap(w15.where_relocalise) is w11.where_relocalise
    assert w15.side_cell.__globals__ is vars(w15) and w15.click_step.__globals__ is vars(w15)


def test_walk16s_f_is_not_carried(mods: Any) -> None:
    w17 = mods[0]
    assert not hasattr(w17, "npc_cells_near") and not hasattr(w17, "NPC_SUB_NEAR")
    assert "walk16" not in {getattr(v, "__name__", "") for v in vars(w17).values()}
    assert not any(isinstance(v, ModuleType) and v.__name__ == "walk16" for v in vars(w17).values())


def test_every_name_walk17s_code_uses_resolves(mods: Any) -> None:
    w17 = mods[0]
    pool = set().union(*(vars(m) for m in mods))
    fns = (w17._route14, w17._leg15, w17.run11, w17._run12, w17.finish_failed, w17.finish_session,
           w17.run, w17.side_cell, w17._side14, w17.click_step, w17._walk_route, w17.merge_legs,
           w17.leg_ends, w17.full_path, w17.server_steps, w17.substitute_goal, w17.npc_substitute,
           w17._where_relocalise, w17.minimap_fix, w17.where_held, w17.warp_blocked,
           w17.use_map, w17.warp_areas, w17.reset_where)  # fmt: skip
    for fn in fns:
        used = {n for n in names(fn.__code__) if n in pool}
        missing = sorted(n for n in used if n not in vars(w17) and not hasattr(builtins, n))
        assert not missing, (fn.__name__, missing)


def test_where2_and_separators_are_never_used(mods: Any) -> None:
    w17 = mods[0]
    for fn in (w17._where_relocalise, w17.minimap_fix, w17.run, w17._walk_route, w17.click_step):
        assert "fix_v2" not in names(fn.__code__) and "SEPARATOR" not in names(fn.__code__)
    own = [v for v in vars(w17).values()
           if isinstance(v, types.FunctionType) and v.__module__ == "walk17"]  # fmt: skip
    assert not any("/ex" in consts(fn.__code__) for fn in own)  # no separator line, anywhere
    assert "fix_v2" not in names(w17.run11.__code__)  # the harness relocalises through walk@17's


# --- shared fakes ---------------------------------------------------------------------------------


class Flat:
    """A flat walkable world (the camera: 30 x 20 px per cell around the belief)."""

    def __init__(self, position: tuple[int, int], size: tuple[int, int] = (60, 60)) -> None:
        self.walkable = np.ones((size[1], size[0]), dtype=bool)
        self.position = position

    def project(self, cells: Any) -> np.ndarray:
        c = np.asarray(cells, dtype=float) - np.asarray(self.position, dtype=float)
        return np.stack([640 + 30 * c[:, 0], 384 + 20 * c[:, 1]], axis=1)


class Clock:
    def __init__(self, t: float = 1000.0, step: float = 1.0) -> None:
        self.t, self.step = t, step

    def __call__(self) -> float:
        self.t += self.step
        return self.t


def area(cx: int, cy: int, sx: int, sy: int) -> dict[str, Any]:
    cells = frozenset((cx + dx, cy + dy) for dx in range(-sx, sx + 1) for dy in range(-sy, sy + 1))
    return {"cell": (cx, cy), "span": (sx, sy), "to_map": "elsewhere", "cells": cells}


@pytest.fixture
def warps(mods: Any) -> Any:
    """walk@17's map state for one test (restored after)."""
    w17 = mods[0]
    saved, route = dict(w17.WARPS), dict(w17.ROUTE)

    def use(*areas: dict[str, Any], intent: str = "walk",
            nopass: frozenset[tuple[int, int]] = frozenset()) -> None:  # fmt: skip
        w17.use_map("synthetic", intent, list(areas), nopass)

    yield use
    w17.WARPS.clear()
    w17.WARPS.update(saved)
    w17.ROUTE.clear()
    w17.ROUTE.update(route)


def cost(start: tuple[int, int], path: list[tuple[int, int]]) -> int:
    """The planner's cost (a straight step 10, a diagonal 14), the cross-check test's measure."""
    total, prev = 0, start
    for c in path:
        total += 14 if (c[0] != prev[0] and c[1] != prev[1]) else 10
        prev = c
    return total


# --- A: the minimap first, /where once per need ---------------------------------------------------


class Screen:
    """Frames with a new frame_id every grab (the frame bus)."""

    def __init__(self) -> None:
        self.fid = 0

    def grab_meta(self, x: int, y: int, w: int, h: int) -> tuple[int, Any, int, str]:
        self.fid += 1
        return self.fid * 1000, np.zeros((720, 1280, 4), np.uint8), self.fid, "bus"


@pytest.fixture
def reloc(mods: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    """walk@17's relocalisation with scripted minimap reads and a fake where@3 (never typed)."""
    w17 = mods[0]
    wf = sys.modules["where_fix"]
    selfpos = w17.selfpos
    state: dict[str, Any] = {"reads": [], "where": [], "answer": (11, 10), "rejects": []}
    clock = Clock(step=0.0)

    def read_minimap(img: Any, digits: Any, rect: Any = None) -> Any:
        xy = state["reads"].pop(0) if state["reads"] else None
        return selfpos.Reading(xy, "ok" if xy else "no_glyph")

    def fix_once(agent: Any, screen: Any, templates: Any, belief: Any, walkable: Any,
                 reason: str) -> dict[str, Any]:  # fmt: skip
        state["where"].append(reason)
        xy = state["answer"]
        return {"xy": xy, "rejects": [] if xy else list(state["rejects"]), "t": 7}

    def no_typing(*a: Any, **k: Any) -> Any:
        raise AssertionError("a test must never type")

    monkeypatch.setattr(selfpos, "read_minimap", read_minimap)
    monkeypatch.setattr(wf, "fix_once", fix_once)
    monkeypatch.setattr(w17.r, "chat_line", no_typing)
    monkeypatch.setattr(w17.r, "game_region", lambda: (0, 0, 1280, 720))
    monkeypatch.setattr(w17.r, "ns", lambda: 0)
    monkeypatch.setattr(w17.time, "sleep", lambda s: None)
    monkeypatch.setattr(w17.time, "monotonic", clock)
    w17.WHERE.update(last_t=None, spent=None, retry_s=60.0, asked=0, held=0)
    fix = w17._where_relocalise({}, digits=object())
    w = Flat((10, 10))

    def go() -> dict[str, Any]:
        return dict(fix(None, Screen(), w, None, BAND))

    return w17, state, clock, w, go


def test_a_minimap_read_relocalises_with_nothing_typed(reloc: Any) -> None:
    w17, state, clock, w, go = reloc
    state["reads"] = [(12, 9), (12, 9)]
    rl = go()
    assert rl["ok"] and rl["method"] == "minimap" and rl["to"] == [12, 9] and w.position == (12, 9)
    assert state["where"] == [] and w17.WHERE["asked"] == 0


def test_a_minimap_miss_types_nothing(reloc: Any) -> None:
    """The client shows a readout here (one read has it): a miss is no fix, never a /where."""
    w17, state, clock, w, go = reloc
    cases = (([(12, 9), (13, 9)], "disagree"), ([(12, 9), None], "disagree"),
             ([(30, 30), (30, 30)], "implausible"), ([(99, 9), (99, 9)], "off_map"))  # fmt: skip
    for reads, why in cases:
        state["reads"] = list(reads)
        rl = go()
        assert not rl["ok"] and rl["rejects"] == [f"minimap:{why}"], (reads, rl)
    assert state["where"] == [] and w.position == (10, 10)


def test_a_no_readout_types_exactly_one_where(reloc: Any) -> None:
    w17, state, clock, w, go = reloc
    rl = go()  # no readout on either frame (indoors)
    assert rl["ok"] and rl["method"] == "where" and w.position == (11, 10)
    assert state["where"] == [w17.REASON_START]  # ONE where@3, the route start's reason class
    with w17._route("walk"):
        clock.t += 61.0
        go()
    assert state["where"] == [w17.REASON_START, w17.REASON_DOUBT]  # inside a route: a doubt


def test_a_second_relocalise_within_the_retry_interval_does_not_type(reloc: Any) -> None:
    w17, state, clock, w, go = reloc
    state["answer"], state["rejects"] = None, ["unparsed"]  # the one /where is not read
    first = go()
    assert not first["ok"] and first["rejects"] == ["unparsed"] and len(state["where"]) == 1
    clock.t += 30.0  # a second need, 30 s later: not even prepared
    again = go()
    assert not again["ok"] and again["rejects"] == ["held:where_retry"]
    assert len(state["where"]) == 1 and w17.WHERE["held"] == 1
    clock.t += 31.0  # past the guard's 60 s: the next need may ask once
    go()
    assert len(state["where"]) == 2


def test_a_spent_budget_is_never_asked_again(reloc: Any) -> None:
    w17, state, clock, w, go = reloc
    state["answer"], state["rejects"] = None, ["guard:where_budget"]
    assert go()["rejects"] == ["guard:where_budget"]
    clock.t += 600.0
    assert go()["rejects"] == ["held:where_budget"] and len(state["where"]) == 1


def test_a_through_the_real_guard_one_where_per_need(mods: Any, reloc: Any,
                                                     tmp_path: Path) -> None:  # fmt: skip
    """The fake where@3 asks a REAL typing guard (on a temporary state file) before 'typing', as
    where_fix.fix_once does: each need asks once, the guard logs the reason and the run. And the
    guard's repeat rule is what limits it: a 3rd /where in a row is refused (walk@17 types no
    other slash line), so walk@17 stops asking for the rest of the run (3.32: at most 2 per run)."""
    w17, state, clock, w, go = reloc
    cg = sys.modules["chat_guard"]
    wf = sys.modules["where_fix"]
    paths = {"state_path": tmp_path / "s.json", "log": tmp_path / "g.jsonl"}
    pol = {"refuse_identical_in_a_row": 3, "where_retry_s": 60, "where_budget_per_run": 12,
           "min_line_interval_s": 0.5}  # fmt: skip
    cg.start_run("20261009T150000-demo-walk17", 56, **paths)
    typed: list[str] = []

    def fix_once(agent: Any, screen: Any, templates: Any, belief: Any, walkable: Any,
                 reason: str) -> dict[str, Any]:  # fmt: skip
        try:
            cg.before_typing("/where", reason=reason, pol=pol, clock=lambda: clock.t, **paths)
        except cg.ChatRefused as exc:  # where_fix.fix_once's own handling
            return {"xy": None, "rejects": [f"guard:{exc.rule}"], "t": 0}
        typed.append(reason)
        return {"xy": None, "rejects": ["unparsed"], "t": 0}

    wf.fix_once = fix_once  # restored by the fixture's monkeypatch
    got = []
    for dt in (0.0, 5.0, 61.0, 61.0, 61.0):  # needs at 0, 5, 66, 127, 188 s
        clock.t += dt
        got.append(go()["rejects"])
    rows = [json.loads(x) for x in paths["log"].read_text().splitlines()]
    where = [x for x in rows if x.get("event") == "where"]
    assert len(typed) == 2 and len(where) == 2  # 0 s and 66 s; 5 s held by walk@17 itself
    assert got == [["unparsed"], ["held:where_retry"], ["unparsed"], ["guard:repeat"],
                   ["held:repeat"]]  # fmt: skip
    assert {x["reason"] for x in where} == {w17.REASON_START}
    assert all(x["run"] == "20261009T150000-demo-walk17" for x in where)
    assert [x["rule"] for x in rows if x.get("event") == "refused"] == ["repeat"]


def test_the_session_opens_the_runs_where_budget(mods: Any, monkeypatch: pytest.MonkeyPatch,
                                                 tmp_path: Path, warps: Any) -> None:  # fmt: skip
    w17 = mods[0]
    started: list[tuple[str, int]] = []
    monkeypatch.setattr(w17.chat_guard, "start_run", lambda rid, b: started.append((rid, b)))
    monkeypatch.setattr(w17.chat_guard, "policy", lambda: {"where_retry_s": 60})
    warps(area(5, 5, 1, 1))
    sid = "20261009T150000-demo-walk17-alone-clean-indoor"
    log = w17.SessionLog(sid, root=tmp_path)
    log.start(n=56, rule="walk@17")
    man = json.loads((tmp_path / sid / "manifest.json").read_text())
    assert started == [(sid, 56)] and man["where_budget"] == 56 and man["where_run"] == sid
    assert man["minimap_first"] and man["click_max_safe"] == 14 and man["plan_max"] == 48
    assert man["warp_areas"] == [{"cell": [5, 5], "span": [1, 1], "to_map": "elsewhere"}]
    assert w17.SessionLog.current is log and mods[1].SessionLog.current is log


# --- B: warp areas --------------------------------------------------------------------------------


def test_b_a_walk_plan_never_enters_a_warp_area(mods: Any, warps: Any) -> None:
    w17 = mods[0]
    a = area(20, 10, 1, 2)
    warps(a)
    w = Flat((10, 10))
    real = sys.modules["walk6"].plan(w, (30, 10), set())
    assert any(c in a["cells"] for c in real)  # walk@15's planner walks straight through it
    path = w17.w6.plan(w, (30, 10), set())
    assert path and path[-1] == (30, 10) and not any(c in a["cells"] for c in path)
    for c in a["cells"]:  # a goal inside: no plan (the harness's goal draw rejects it)
        assert w17.w6.plan(w, c, set()) is None


def test_b_the_portal_route_still_can(mods: Any, warps: Any) -> None:
    """Only the area holding the goal opens, and only for the portal intent."""
    w17 = mods[0]
    portal, other = area(30, 10, 1, 1), area(20, 10, 1, 2)
    warps(portal, other)
    w = Flat((10, 10))
    assert w17.w6.plan(w, (30, 10), set()) is None  # a walk: the portal is no goal
    with w17._route("warp"):
        path = w17.w6.plan(w, (30, 10), set())
    assert path and path[-1] == (30, 10)
    assert not any(c in other["cells"] for c in path)  # every OTHER warp area stays blocked


def test_b_the_harness_never_draws_a_goal_inside_a_warp_area(mods: Any, warps: Any) -> None:
    w17, w11 = mods[0], mods[5]
    assert w17.run11.__globals__["w6"] is w17.w6 and "w6" in names(w11.run.__code__)
    a = area(15, 15, 2, 2)
    warps(a)  # the harness's own intent: a walk scene
    w = Flat((10, 10))
    # the harness's goal check is "a plan exists": every cell that passes it
    drawn = [(x, y) for x in range(0, 30) for y in range(0, 30)
             if w17.w6.plan(w, (x, y), set()) is not None]  # fmt: skip
    assert drawn and not set(drawn) & a["cells"]
    warps(a, intent="warp")  # the portal scene's start search plans TO the portal
    assert w17.w6.plan(w, (15, 15), set()) is not None


def test_b_the_click_step_refuses_a_cell_inside_a_warp_area(mods: Any, warps: Any,
                                                           monkeypatch: pytest.MonkeyPatch
                                                           ) -> None:  # fmt: skip
    w17, w15, w14 = mods[0], mods[1], mods[2]
    a = area(12, 10, 0, 0)
    warps(a)
    calls: list[Any] = []
    monkeypatch.setattr(w14, "click_step", lambda *a, **k: calls.append(a) or {
        "clicked": True, "outcome": "portal", "target": []})  # fmt: skip
    w = Flat((10, 10))
    got = w17.click_step(None, w, (12, 10))
    assert got["outcome"] == "no_safe_point" and got["warp_area"] == [12, 10] and not calls
    assert (10, 10) in w15.VISITED  # walk@15's E still notes where we stand
    assert w17.click_step(None, w, (12, 10), "warp")["outcome"] == "portal"  # the portal click


def test_b_substitutes_and_sides_never_pick_a_warp_cell(mods: Any, warps: Any,
                                                       monkeypatch: pytest.MonkeyPatch
                                                       ) -> None:  # fmt: skip
    w17, w15, w14, w13, w12, w11 = mods
    a = area(22, 20, 1, 1)  # covers the goal's ring-1 cells on our side (x = 21)
    warps(a)
    w = Flat((30, 20), size=(60, 60))
    goal = (20, 20)
    assert w11.substitute_goal(w, goal, {goal}) in a["cells"]  # walk@15's: the nearest, inside
    sub = w17.substitute_goal(w, goal, {goal})
    assert sub is not None and sub not in a["cells"]
    nsub = w17.npc_substitute(w, goal, set(), {goal})
    assert nsub is not None and nsub not in a["cells"]
    monkeypatch.setattr(w17, "points_from", lambda w, c, t: 1)  # every side looks feasible
    side = w17.side_cell(w, goal, set(), set(), set())
    assert side is not None and side not in a["cells"]


def test_b_an_unlisted_map_fails_closed(mods: Any, tmp_path: Path) -> None:
    w17 = mods[0]
    kb = tmp_path / "route.json"
    warp = {"x": 5, "y": 6, "span_x": 1, "span_y": 2, "to_map": "x"}
    kb.write_text(json.dumps({"warps": {"prt_fild08": [warp]}}))
    got = w17.warp_areas("prt_fild08", kb)
    assert got[0]["cell"] == (5, 6) and len(got[0]["cells"]) == 3 * 5
    with pytest.raises(SystemExit, match="no L3 warp list"):
        w17.warp_areas("iz_dun00", kb)


def test_b_no_map_loaded_fails_closed(mods: Any, warps: Any) -> None:
    w17 = mods[0]
    w17.WARPS.update(map=None, areas=[], cells=frozenset())
    with pytest.raises(RuntimeError, match="fail closed"):
        w17.w6.plan(Flat((1, 1)), (5, 5), set())


# --- C: long walks --------------------------------------------------------------------------------


def test_c_a_long_route_becomes_legs_through_waypoints_outside_warp_areas(
    mods: Any, warps: Any
) -> None:
    w17 = mods[0]
    a = area(50, 20, 2, 2)  # astride the straight line, near the first mark (40 steps)
    warps(a)
    w = Flat((10, 20), size=(200, 40))
    goal = (130, 20)
    with w17._route("walk"):
        path = w17.full_path(w, goal)
    assert path and len(path) >= 120 and not set(path) & a["cells"]
    ends = w17.leg_ends(path, w.walkable)
    assert ends is not None and ends[-1] == len(path) - 1 and len(ends) == 3
    starts = [w.position] + [path[k] for k in ends[:-1]]
    total = 0
    for s, k in zip(starts, ends, strict=True):
        leg_len = k - (path.index(s) if s in path else -1)
        assert 1 <= leg_len <= w17.PLAN_MAX
        wp = path[k]
        assert w.walkable[wp[1], wp[0]] and w17.warp_area_of(wp) is None
        # the cross-check: each leg's own plan exists within PLAN_MAX, the same cost as the path
        leg_world = Flat(s, size=(200, 40))
        with w17._route("walk"):
            own = w17.w6.plan(leg_world, wp, set())
        assert own is not None and len(own) <= w17.PLAN_MAX
        total += cost(s, own)
    assert total == cost(w.position, path)  # chained legs cost what the whole A* costs


@pytest.fixture
def walker(mods: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    """walk@17's route on a flat world; below walk@17's and walk@15's click steps every click
    walks (recorded)."""
    w17, w14 = mods[0], mods[2]
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(w17.r, "ns", lambda: 0)
    monkeypatch.setattr(w17.r, "game_region", lambda: (0, 0, 1280, 720))
    monkeypatch.setattr(w17, "moved", lambda a, b: (True, 1.0))
    monkeypatch.setattr(w17, "preview", lambda *a, **k: None)
    w17.UNITS["memory"].reset()
    clicks: list[tuple[tuple[int, int], tuple[int, int]]] = []

    def step(pr: Any, w: Any, end: tuple[int, int], expect: str = "walk",
             accept_unnamed: bool = False) -> dict[str, Any]:  # fmt: skip
        clicks.append((tuple(w.position), tuple(end)))
        return {"clicked": True, "outcome": "confirmed", "target": [], "at": (0.0, 0.0),
                "t_click": 0}  # fmt: skip

    monkeypatch.setattr(w14, "click_step", step)
    pr = SimpleNamespace(agent=None, background=None,
                         screen=SimpleNamespace(grab=lambda *a: (0, None)))  # fmt: skip

    def go(w: Flat, goal: tuple[int, int], seg_max: int = 4) -> dict[str, Any]:
        return dict(w17._walk_route(pr, w, goal, BAND, seg_max, lambda *a: None, None, None,
                                    relocalise=lambda *a: {"ok": True}, clock=Clock()))  # fmt: skip

    return w17, clicks, go


def test_c_a_long_route_is_walked_leg_by_leg_no_click_beyond_14(walker: Any, warps: Any) -> None:
    w17, clicks, go = walker
    a = area(50, 20, 2, 2)
    warps(a)
    w = Flat((10, 20), size=(200, 40))
    did = go(w, (130, 20))
    assert did.get("arrived_belief") and w.position == (130, 20), did.get("decline")
    assert did["legs"] == 3 and did["legs_walked"] == 3 and len(did["waypoints"]) == 2
    assert [e["leg"] for e in did["events"] if "leg" in e] == [1, 2, 3]
    assert did["clicks"] == len(clicks) and did["substitute"] is None
    for frm, end in clicks:
        assert max(abs(end[0] - frm[0]), abs(end[1] - frm[1])) <= w17.CLICK_MAX_SAFE
        assert end not in a["cells"] and frm not in a["cells"]
        w.position = frm
        steps = w17.server_steps(w, end)
        assert steps is not None and steps <= w17.CLICK_MAX_SAFE


def test_c_a_short_route_is_walk15s_route_as_today(walker: Any, warps: Any) -> None:
    w17, clicks, go = walker
    warps()
    w = Flat((10, 10))
    did = go(w, (22, 10))
    assert did.get("arrived_belief") and did["legs"] == 1 and "waypoints" not in did
    assert not any("leg" in e for e in did["events"])


def test_c_a_declined_leg_ends_the_route_without_the_goals_substitutes(mods: Any) -> None:
    w17 = mods[0]
    one = {"events": [{"x": 1}], "clicks": 3, "relocs": 1, "arrived_belief": True,
           "substitute": [49, 20]}  # fmt: skip
    two = {"events": [], "clicks": 2, "decline": "unit_stays", "substitute": [89, 20],
           "npc_substitute": None}  # fmt: skip
    legs = [({"leg": 1, "to": [50, 20]}, one), ({"leg": 2, "to": [90, 20]}, two)]
    out = w17.merge_legs(legs, 3, [(50, 20), (90, 20)], 120)
    assert out["decline"] == "unit_stays" and out["leg_declined"] == 2
    # the declined leg's substitute was a WAYPOINT's, never the goal's
    assert out["substitute"] is None and out["npc_substitute"] is None
    assert out["clicks"] == 5 and out["relocs"] == 1
    assert out["legs"] == 3 and out["legs_walked"] == 2
    assert out["leg_ends"][0]["substitute"] == [49, 20]


def test_c_no_candidate_is_farther_than_14_steps(mods: Any) -> None:
    """poring-nav.md: the rules' farthest click candidate may never exceed CLICK_MAX_SAFE."""
    w17, w13 = mods[0], mods[3]
    w = Flat((0, 30), size=(80, 60))
    path = [(x, 30) for x in range(1, 60)]
    wide = (-10_000, -10_000, 10_000, 10_000)
    for seg_max in (w17.SEG_INDOOR, w17.SEG_OPEN):
        have = w17.click_candidates(w, path, seg_max, wide)
        have += w17.farther_candidates(w, path, seg_max, wide)
        have += w13.shorter_candidates(w, path, seg_max, wide, have)
        assert max(path.index(c) + 1 for c in have) <= w17.CLICK_MAX_SAFE


def test_c_the_click_step_refuses_a_cell_beyond_14_server_steps(mods: Any, warps: Any,
                                                               monkeypatch: pytest.MonkeyPatch
                                                               ) -> None:  # fmt: skip
    w17, w14 = mods[0], mods[2]
    warps()
    calls: list[Any] = []
    monkeypatch.setattr(w14, "click_step", lambda *a, **k: calls.append(a) or {
        "clicked": True, "outcome": "confirmed", "target": []})  # fmt: skip
    w = Flat((10, 10))
    far = w17.click_step(None, w, (25, 10))  # 15 steps
    assert far["outcome"] == "no_safe_point" and far["beyond_click_max"] == 14 and not calls
    assert w17.click_step(None, w, (24, 10))["clicked"] and len(calls) == 1  # 14 steps


class FlatGat:
    """A flat 30 x 30 GAT for walk5.World (walkable everywhere, no altitude)."""

    altitude = np.zeros((30, 30))

    def walkable(self) -> np.ndarray:
        return np.ones((30, 30), dtype=bool)

    def relative_altitude(self, position: Any, cells: Any) -> np.ndarray:
        return np.zeros(len(np.atleast_2d(cells)))


def test_b_the_harness_never_draws_a_start_inside_a_warp_area(mods: Any, warps: Any) -> None:
    """AMENDMENT (Batt 2026-10-13, decision 15): walk@11's start draw takes any walkable cell within
    +-8 of the scene's start. walk@17's harness sees walk5 through a proxy whose World offers no
    warp-area cell as walkable in a WALK scene; the portal scene's world is unchanged."""
    w17, w11 = mods[0], mods[5]
    assert w17.run11.__globals__["w5"] is w17.w5 and "w5" in names(w11.run.__code__)
    a = area(15, 15, 2, 2)
    warps(a)
    w = w17.w5.World(None, FlatGat(), (10, 10))
    starts = {(x, y) for x in range(30) for y in range(30) if w.walkable[y, x]}
    assert starts and not starts & a["cells"] and len(starts) == 900 - len(a["cells"])
    assert w.grid is not None  # the planner's grid is walk5's own (B blocks warp cells there)
    warps(a, intent="warp")
    assert w17.w5.World(None, FlatGat(), (10, 10)).walkable.all()
    assert w17.w5.PLAN_MAX == 48 and w17.PLAN_MAX == 48  # every other name is walk5's


# --- amendment 3 (Batt 2026-10-15, decision 4): the server's NOPASS cells -----------------------


def test_3_every_plan_avoids_a_server_nopass_cell_the_portals_too(mods: Any, warps: Any) -> None:
    w17 = mods[0]
    wall = frozenset((20, y) for y in range(5, 16))  # client-walkable, server-NOPASS
    warps(nopass=wall)
    w = Flat((10, 10))
    assert any(c in wall for c in sys.modules["walk6"].plan(w, (30, 10), set()))
    path = w17.w6.plan(w, (30, 10), set())
    assert path and path[-1] == (30, 10) and not set(path) & wall
    assert w17.w6.plan(w, (20, 10), set()) is None  # never a goal
    portal = area(30, 10, 1, 1)
    warps(portal, nopass=wall | {(30, 10)})
    with w17._route("warp"):
        assert w17.w6.plan(w, (30, 10), set()) is None  # the portal's own plan: blocked too
        path = w17.w6.plan(w, (31, 10), set())
        assert path and not set(path) & (wall | {(30, 10)})
        assert w17.full_path(w, (31, 10)) and not set(w17.full_path(w, (31, 10))) & wall


def test_3_the_harness_world_never_offers_a_server_nopass_cell(mods: Any, warps: Any) -> None:
    w17 = mods[0]
    a, off = area(15, 15, 1, 1), frozenset({(3, 4), (25, 26)})
    for intent in ("walk", "warp"):  # every scene, the portal's included
        warps(a, intent=intent, nopass=off)
        world = w17.w5.World(None, FlatGat(), (10, 10))
        assert not world.walkable[4, 3] and not world.walkable[26, 25]
        hidden = len(off) + (len(a["cells"]) if intent == "walk" else 0)
        assert int(world.walkable.sum()) == 900 - hidden
    warps(a, intent="warp")  # nothing to hide: the portal scene's world as before
    assert w17.w5.World(None, FlatGat(), (10, 10)).walkable.all()


def test_3_the_click_step_refuses_a_server_nopass_cell(mods: Any, warps: Any,
                                                      monkeypatch: pytest.MonkeyPatch
                                                      ) -> None:  # fmt: skip
    w17, w15, w14 = mods[0], mods[1], mods[2]
    warps(nopass=frozenset({(12, 10)}))
    calls: list[Any] = []
    monkeypatch.setattr(w14, "click_step", lambda *a, **k: calls.append(a) or {
        "clicked": True, "outcome": "confirmed", "target": []})  # fmt: skip
    w = Flat((10, 10))
    for expect in ("walk", "warp"):
        got = w17.click_step(None, w, (12, 10), expect)
        assert got["outcome"] == "no_safe_point" and got["server_nopass"] == [12, 10], expect
        assert "warp_area" not in got and not calls
    assert (10, 10) in w15.VISITED
    assert w17.click_step(None, w, (13, 10))["clicked"] and len(calls) == 1


def test_3_server_nopass_comes_from_both_sources_and_fails_closed(
    mods: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    w17 = mods[0]
    from poring_dataset import walkable as wk

    gat = SimpleNamespace(walkable=lambda: np.ones((4, 5), dtype=bool))
    mask = np.ones((4, 5), dtype=bool)
    mask[1, 2] = mask[3, :] = mask[:, 4] = False  # a cliff + the server's last row / column
    monkeypatch.setattr(wk, "load_both", lambda name: (gat, mask))
    got = w17.server_nopass("syn")
    assert (2, 1) in got and (0, 3) in got and (4, 0) in got and len(got) == 1 + 5 + 3

    def lacks(name: str) -> Any:
        raise wk.MapSourceError(f"the server's map cache lacks {name}")

    monkeypatch.setattr(wk, "load_both", lacks)
    with pytest.raises(SystemExit, match="lacks syn"):
        w17.server_nopass("syn")
    with pytest.raises(SystemExit, match="lacks syn"):
        w17.use_map("syn", "walk", [])  # the run refuses to start


def test_3_the_manifest_records_the_walkable_source(mods: Any, monkeypatch: pytest.MonkeyPatch,
                                                   tmp_path: Path, warps: Any) -> None:  # fmt: skip
    w17 = mods[0]
    monkeypatch.setattr(w17.chat_guard, "start_run", lambda rid, b: None)
    monkeypatch.setattr(w17.chat_guard, "policy", lambda: {"where_retry_s": 60})
    warps(nopass=frozenset({(1, 1), (2, 2)}))
    sid = "20261015T120000-demo-walk17-alone-clean-indoor"
    w17.SessionLog(sid, root=tmp_path).start(n=1, rule="walk@17")
    man = json.loads((tmp_path / sid / "manifest.json").read_text())
    assert man["walkable"] == "client∩server" and man["server_nopass_cells"] == 2
