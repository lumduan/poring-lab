"""scripts/walk13.py (walk@13, demonstrations 3.24): walk@12 + refusals become alternatives.
1. shorter points on the polyline; 2. a re-plan around refused cells (at most 3 per route);
3. a nearby goal when the goal sits beside an NPC; 4. "taken" = a unit's feet ON the target;
5. signboards leave the work zone. walk@12's click step and harness are REUSED (the same code),
and walk@12's module is untouched. The route loop is driven by a scripted click step on a flat
fake world (cells 30 x 20 px), so each change is tested on its own."""

from __future__ import annotations

import builtins
import importlib.util
import inspect
import sys
import types
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parents[2] / "scripts"
BAND = (100, 60, 1180, 680)


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mods() -> tuple[ModuleType, ModuleType, ModuleType]:
    sys.path.insert(0, str(SCRIPTS))
    for name in ("walk5", "walk6", "reloc2", "where_fix", "walk7", "walk8", "walk9", "walk10",
                 "walk11", "work_zone", "walk12", "walk13"):  # fmt: skip
        _load(name, SCRIPTS / f"{name}.py")
    return sys.modules["walk13"], sys.modules["walk12"], sys.modules["walk11"]


class Flat:
    """A flat open world: every cell walkable, 30 x 20 px per cell around (640, 384)."""

    def __init__(self, position: tuple[int, int], size: int = 60) -> None:
        self.walkable = np.ones((size, size), dtype=bool)
        self.position = position

    def project(self, cells: Any) -> np.ndarray:
        c = np.asarray(cells, dtype=float) - np.asarray(self.position, dtype=float)
        return np.stack([640 + 30 * c[:, 0], 384 + 20 * c[:, 1]], axis=1)


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        self.t += 1.0
        return self.t


@pytest.fixture
def loop(mods: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    """walk@13's route loop with a scripted click step: ``refuse(end, w)`` -> an outcome dict or
    None (None = clicked)."""
    w13, _, _ = mods
    monkeypatch.setattr(w13.time, "sleep", lambda s: None)
    monkeypatch.setattr(w13.r, "ns", lambda: 0)
    monkeypatch.setattr(w13.r, "game_region", lambda: (0, 0, 1280, 720))
    monkeypatch.setattr(w13, "moved", lambda a, b: (True, 1.0))
    monkeypatch.setattr(w13, "preview", lambda *a, **k: None)
    w13.UNITS["memory"].reset()
    state: dict[str, Any] = {"clicks": [], "refuse": lambda end, w: None}

    def step(pr: Any, w: Any, end: tuple[int, int], expect: str = "walk",
             accept_unnamed: bool = False) -> dict[str, Any]:  # fmt: skip
        got = state["refuse"](end, w)
        if got is not None:
            return {"clicked": False, "target": [], **got}
        state["clicks"].append(end)
        return {"clicked": True, "outcome": "confirmed", "target": [], "at": (0.0, 0.0),
                "t_click": 0}  # fmt: skip

    monkeypatch.setattr(w13, "click_step", step)
    pr = SimpleNamespace(agent=None, background=None,
                         screen=SimpleNamespace(grab=lambda *a: (0, None)))  # fmt: skip
    route = inspect.unwrap(w13.walk_route)

    def go(start: tuple[int, int], goal: tuple[int, int]) -> tuple[dict[str, Any], Flat]:
        w = Flat(start)
        did = route(pr, w, goal, BAND, 4, lambda *a: None, None, None,
                    relocalise=lambda *a: {"ok": True}, clock=Clock())  # fmt: skip
        return did, w

    return w13, state, go


# --- the code walk@13 reuses -----------------------------------------------------------------
def names(code: types.CodeType) -> set[str]:
    out = set(code.co_names)
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            out |= names(c)
    return out


def test_walk13_reuses_walk12s_click_step_and_walk11s_harness(mods: Any) -> None:
    w13, w12, w11 = mods
    assert w13._click_step12.__code__ is inspect.unwrap(w12.click_step).__code__
    assert w13._click_step12.__globals__ is vars(w13)  # its zone_points is walk@13's
    assert w13.run11.__code__ is w11.run.__code__ and w13.run11.__globals__ is vars(w13)
    assert w13.run.__code__ is w12.run.__code__ and w13.run.__globals__ is vars(w13)
    assert w13.finish_failed.__code__ is w12.finish_failed.__code__
    assert w12.WALK8_RULE == "walk@12" and w12.zone_points is not w13.zone_points  # untouched


def test_every_name_walk13s_code_uses_resolves(mods: Any) -> None:
    """Every global the reused code (and walk@13's own) reads exists in walk@13's module."""
    w13, w12, w11 = mods
    pool = set(vars(w11)) | set(vars(w12)) | set(vars(w13))
    for fn in (w13._click_step12, w13.run11, w13.run, w13.finish_failed, w13.finish_session,
               inspect.unwrap(w13.walk_route), w13.zone_points, w13._click_step,
               w13.shorter_candidates, w13.npc_substitute, w13.goal_taken):  # fmt: skip
        used = {n for n in names(fn.__code__) if n in pool}
        missing = sorted(n for n in used if n not in vars(w13) and not hasattr(builtins, n))
        assert not missing, (fn.__name__, missing)


# --- change 5: signboards leave the work zone ---------------------------------------------------
def test_a_point_under_a_sign_or_within_its_margin_is_refused(mods: Any,
                                                             monkeypatch: pytest.MonkeyPatch
                                                             ) -> None:  # fmt: skip
    w13, _, _ = mods
    pts = [(700.0, 480.0), (700.0, 497.0), (700.0, 499.0), (900.0, 300.0)]
    monkeypatch.setattr(w13, "tier_points", lambda w, end, tier: pts if tier == "A" else [])
    monkeypatch.setitem(w13.SIGNS, "boxes", [[630, 463, 758, 486]])  # the wedding NPC's bar
    queue, tier, refused = w13.zone_points(SimpleNamespace(), (0, 0))
    # inside, and 11 px below (inside the 12-px margin) are refused; 13 px below is not
    assert queue == [(700.0, 499.0), (900.0, 300.0)] and tier == "A"
    assert refused == [[700.0, 480.0], [700.0, 497.0]]
    monkeypatch.setitem(w13.SIGNS, "boxes", [])
    assert w13.zone_points(SimpleNamespace(), (0, 0))[0] == pts  # no sign: walk@12's points


def test_the_click_step_finds_signs_on_a_fresh_frame_first(mods: Any,
                                                         monkeypatch: pytest.MonkeyPatch
                                                         ) -> None:  # fmt: skip
    w13, _, _ = mods
    seen: list[Any] = []
    monkeypatch.setattr(w13, "refresh_signs", lambda screen: seen.append(screen) or [[1, 2, 3, 4]])
    monkeypatch.setattr(
        w13,
        "_click_step12",
        lambda pr, w, end, e, a: {"clicked": False, "outcome": "no_safe_point"},
    )
    step = w13._click_step(SimpleNamespace(screen="S"), None, (1, 1))
    assert seen == ["S"] and step["signs"] == [[1, 2, 3, 4]]


# --- change 1: shorter points ------------------------------------------------------------------
def test_shorter_candidates_are_nearer_cells_of_the_same_plan_nearest_last(mods: Any) -> None:
    w13, _, _ = mods
    w = Flat((10, 10))
    path = [(10 + i, 10) for i in range(1, 12)]  # 11 cells east
    have = [path[6], path[5], path[7]]
    got = w13.shorter_candidates(w, path, 7, BAND, have)
    assert got == [path[4], path[3], path[2], path[1]]  # SHORTER = 4, nearest last


# --- change 2: re-plan around refusals -----------------------------------------------------------
def test_a_round_of_refused_cells_replans_around_them_and_arrives(loop: Any) -> None:
    """A wall of unit refusals on row 10 between x 11 and 25 (every first-round candidate): walk@12
    waited and declined `unit_stays`; walk@13 blocks them for 8 s, re-plans and walks round."""
    w13, state, go = loop
    wall = {(x, 10) for x in range(11, 26)}
    state["refuse"] = lambda end, w: {"outcome": "covered_unit_envelope"} if end in wall else None
    did, w = go((10, 10), (26, 10))
    assert did.get("arrived_belief") and w.position == (26, 10), did
    assert did["replans"] >= 1 and not wall & set(state["clicks"])
    assert any("replan" in e for e in did["events"])


def test_replans_stop_at_three_then_walk12s_decline(loop: Any) -> None:
    w13, state, go = loop
    state["refuse"] = lambda end, w: {"outcome": "no_safe_point"} if end != (12, 10) else None
    did, _ = go((10, 10), (25, 10))
    assert did["replans"] == w13.REPLANS == 3 and did.get("decline") == "no_click_point", did


# --- change 3: the goal beside an NPC -----------------------------------------------------------
def test_a_goal_that_reads_talk_gets_a_nearby_goal_clear_of_the_npc(loop: Any) -> None:
    w13, state, go = loop
    goal = (16, 10)

    def refuse(end: tuple[int, int], w: Any) -> dict[str, Any] | None:
        if end == goal:
            return {"outcome": "covered_talk_cell", "talk_cells": [list(goal)]}
        return None

    state["refuse"] = refuse
    did, w = go((10, 10), goal)
    sub = did["npc_substitute"]
    assert sub is not None and did.get("arrived_belief") and w.position == tuple(sub), did
    assert max(abs(sub[0] - goal[0]), abs(sub[1] - goal[1])) == 2  # ring 1 is next to the NPC
    assert did["substitute"] is None  # not walk@8's "taken" substitute


# --- change 4: "taken" = a unit ON the target ---------------------------------------------------
def _envelope_at_goal(goal: tuple[int, int]) -> Any:
    return lambda end, w: {"outcome": "covered_unit_envelope"} if end == goal else None


def test_an_envelope_at_the_goal_with_nobody_on_it_is_never_a_substitute(loop: Any) -> None:
    """walk@12 substituted here (a unit's envelope within one cell of the goal); the server showed
    nobody on the goal in 12 of its 50 crowd routes. walk@13 waits, then declines."""
    w13, state, go = loop
    goal = (16, 10)
    state["refuse"] = _envelope_at_goal(goal)
    w13.UNITS["memory"].items = [w13.ug.Seen("monster", (17, 10), 40, 40, 0)]  # NEXT to the goal
    did, _ = go((10, 10), goal)
    assert did.get("decline") == "unit_stays" and did["substitute"] is None, did
    assert any(e.get("taken_check") == list(goal) and e["on_it"] == [] for e in did["events"])


def test_a_unit_standing_on_the_goal_is_taken(loop: Any) -> None:
    w13, state, go = loop
    goal = (16, 10)
    state["refuse"] = _envelope_at_goal(goal)
    w13.UNITS["memory"].items = [w13.ug.Seen("monster", goal, 40, 40, 0)]  # its feet ON the goal
    did, w = go((10, 10), goal)
    sub = did["substitute"]
    assert sub is not None and did.get("arrived_belief") and w.position == tuple(sub), did
    assert max(abs(sub[0] - goal[0]), abs(sub[1] - goal[1])) in (1, 2)
