"""scripts/walk14.py (walk@14, demonstrations 3.25): walk@13 + A (a STATIC unit keeps a small
envelope) + B (a target whose own points are refused is approached from another side).
walk@13's click step and harness are reused, and walk@13's module is untouched. The route loop is
driven by a scripted click step on a flat fake world, as in test_walk13.py."""

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
S = 1_000_000_000


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
    for name in ("walk5", "walk6", "reloc2", "where_fix", "walk7", "walk8", "walk9", "walk10",
                 "walk11", "work_zone", "walk12", "walk13", "walk14"):  # fmt: skip
        _load(name, SCRIPTS / f"{name}.py")
    return tuple(sys.modules[n] for n in ("walk14", "walk13", "walk12", "walk11"))


def names(code: types.CodeType) -> set[str]:
    out = set(code.co_names)
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            out |= names(c)
    return out


def test_walk14_reuses_walk13_and_leaves_it_untouched(mods: Any) -> None:
    w14, w13, w12, w11 = mods
    assert w14.click_step is w13.click_step  # the same click step, the same sign mask
    assert w14.run11.__code__ is w11.run.__code__ and w14.run11.__globals__ is vars(w14)
    assert w14._run12.__code__ is w12.run.__code__ and w14._run12.__globals__ is vars(w14)
    assert w13.WALK8_RULE == "walk@13" and w14.WALK8_RULE == "walk@14"
    assert inspect.unwrap(w13.walk_route).__globals__ is vars(w13)


def test_every_name_walk14s_code_uses_resolves(mods: Any) -> None:
    w14, w13, w12, w11 = mods
    pool = set(vars(w11)) | set(vars(w12)) | set(vars(w13)) | set(vars(w14))
    for fn in (w14.run11, w14._run12, w14.finish_failed, w14.finish_session, w14.run,
               inspect.unwrap(w14.walk_route), w14.side_cell, w14.points_from):  # fmt: skip
        used = {n for n in names(fn.__code__) if n in pool}
        missing = sorted(n for n in used if n not in vars(w14) and not hasattr(builtins, n))
        assert not missing, (fn.__name__, missing)


# --- A: a static unit keeps a small envelope -----------------------------------------------------
class Cam:
    """30 x 20 px per cell around (640, 384)."""

    def project(self, cells: Any, alt: Any = None) -> np.ndarray:
        c = np.asarray(cells, dtype=float)
        return np.stack([640 + 30 * c[:, 0], 384 + 20 * c[:, 1]], axis=1)


def pick(camera: Any, gat: Any, belief: Any, px: Any) -> np.ndarray:
    u, v = np.asarray(px, dtype=float)[0]
    return np.array([[round((u - 640) / 30), round((v - 384) / 20)]])


def box(cls: str, cell: tuple[int, int]) -> Any:
    u, v = 640 + 30 * cell[0], 384 + 20 * cell[1]
    return SimpleNamespace(cls=cls, foot=(u, v), x0=u - 20, y0=v - 40, x1=u + 20, y1=v)


def radius(mem: Any, t: int) -> int:
    (env,) = mem.envelopes(Cam(), None, (0, 0), t, 0.4, 400)
    return int(env.radius)


def test_a_monster_still_for_8_s_over_3_sightings_keeps_radius_1(mods: Any) -> None:
    w14 = mods[0]
    mem = w14.StaticMemory()
    for k, t in enumerate((0, 4 * S, 9 * S)):
        mem.observe(
            [box("monster", (5, 2 if k != 1 else 3))], Cam(), None, (0, 0), t, 400, pick=pick
        )  # fmt: skip  (a 1-cell box jitter in the middle)
    assert mem.items[0].n == 3 and radius(mem, 9 * S) == 1
    fresh = w14.StaticMemory()
    fresh.observe([box("monster", (5, 2))], Cam(), None, (0, 0), 0, 400, pick=pick)
    assert radius(fresh, 0) == w14.ug.radius_cells("monster", 0.4, 400) == 2  # walk@11's, fresh


def test_a_unit_that_moves_or_is_seen_twice_is_not_static(mods: Any) -> None:
    w14 = mods[0]
    moving = w14.StaticMemory()
    for t, cell in ((0, (5, 2)), (4 * S, (6, 2)), (9 * S, (7, 2))):  # 2 cells from the anchor
        moving.observe([box("monster", cell)], Cam(), None, (0, 0), t, 400, pick=pick)
    assert moving.items[0].n == 1 and radius(moving, 9 * S) > 1  # the streak began again
    twice = w14.StaticMemory()
    for t in (0, 9 * S):
        twice.observe([box("monster", (5, 2))], Cam(), None, (0, 0), t, 400, pick=pick)
    assert radius(twice, 9 * S) > 1  # 2 sightings < STATIC_SEEN
    short = w14.StaticMemory()
    for t in (0, 2 * S, 4 * S, 6 * S):
        short.observe([box("monster", (5, 2))], Cam(), None, (0, 0), t, 400, pick=pick)
    assert radius(short, 6 * S) > 1  # 4 sightings but only 6 s still


# --- B: approach the target from another side ----------------------------------------------------
class Flat:
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
    w14 = mods[0]
    monkeypatch.setattr(w14.time, "sleep", lambda s: None)
    monkeypatch.setattr(w14.r, "ns", lambda: 0)
    monkeypatch.setattr(w14.r, "game_region", lambda: (0, 0, 1280, 720))
    monkeypatch.setattr(w14, "moved", lambda a, b: (True, 1.0))
    monkeypatch.setattr(w14, "preview", lambda *a, **k: None)
    w14.UNITS["memory"].reset()
    state: dict[str, Any] = {"clicks": [], "refuse": lambda end, w: None}

    def step(pr: Any, w: Any, end: tuple[int, int], expect: str = "walk",
             accept_unnamed: bool = False) -> dict[str, Any]:  # fmt: skip
        got = state["refuse"](end, w)
        if got is not None:
            return {"clicked": False, "target": [], **got}
        state["clicks"].append((w.position, end))
        return {"clicked": True, "outcome": "confirmed", "target": [], "at": (0.0, 0.0),
                "t_click": 0}  # fmt: skip

    monkeypatch.setattr(w14, "click_step", step)
    pr = SimpleNamespace(agent=None, background=None,
                         screen=SimpleNamespace(grab=lambda *a: (0, None)))  # fmt: skip
    route = inspect.unwrap(w14.walk_route)

    def go(start: tuple[int, int], goal: tuple[int, int]) -> tuple[dict[str, Any], Flat]:
        w = Flat(start)
        did = route(pr, w, goal, BAND, 4, lambda *a: None, None, None,
                    relocalise=lambda *a: {"ok": True}, clock=Clock())  # fmt: skip
        return did, w

    return w14, state, go, monkeypatch


def test_a_goal_without_a_safe_point_from_here_is_approached_from_another_side(loop: Any) -> None:
    """walk@13 routes 19 / 41: the goal's own cell had no safe point from the last cell, and the
    route declined one cell short. walk@14 walks to a side cell from which the goal has points."""
    w14, state, go, mp = loop
    goal, side = (16, 10), (16, 12)
    mp.setattr(w14, "points_from", lambda w, c, t: 3 if c == side else 0)

    def refuse(end: tuple[int, int], w: Any) -> dict[str, Any] | None:
        if end == goal and w.position != side:
            return {"outcome": "no_safe_point"}
        return None

    state["refuse"] = refuse
    did, w = go((10, 10), goal)
    assert did.get("arrived_belief") and w.position == goal and did["sides"] == 1, did
    assert (side, goal) in state["clicks"]  # the goal was clicked FROM the side cell
    assert any(e.get("side") == list(side) for e in did["events"])


def test_sides_are_bounded_then_walk13s_decline(loop: Any) -> None:
    w14, state, go, mp = loop
    mp.setattr(w14, "points_from", lambda w, c, t: 1)  # every side looks feasible, none works
    state["refuse"] = lambda end, w: {"outcome": "no_safe_point"} if end == (16, 10) else None
    did, _ = go((10, 10), (16, 10))
    assert did["sides"] == w14.SIDES == 2 and did.get("decline") == "no_click_point", did


def test_a_unit_at_the_target_is_never_a_side_approach(loop: Any) -> None:
    w14, state, go, mp = loop
    mp.setattr(w14, "points_from", lambda w, c, t: 1)
    goal = (16, 10)
    state["refuse"] = lambda end, w: {"outcome": "covered_unit_envelope"} if end == goal else None
    did, _ = go((10, 10), goal)
    assert did["sides"] == 0 and did.get("decline") == "unit_stays", did


# --- C: an unknown read joins the route's blocked cells ----------------------------------------
def test_cells_read_unknown_are_replanned_around(loop: Any) -> None:
    """walk@13 crowd route 0: two unknown reads, no re-plan, a decline at the start. walk@14 blocks
    them for the route and plans round."""
    w14, state, go, mp = loop
    wall = {(x, 10) for x in range(11, 26)}
    state["refuse"] = lambda end, w: {"outcome": "covered_unknown"} if end in wall else None
    did, w = go((10, 10), (26, 10))
    assert did.get("arrived_belief") and w.position == (26, 10) and did["replans"] >= 1, did
    assert not wall & {end for _, end in state["clicks"]}
