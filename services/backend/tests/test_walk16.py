"""scripts/walk16.py (walk@16, demonstrations 3.27): walk@15 + F (an NPC-envelope refusal of the
GOAL, with a remembered NPC within one cell of it, triggers walk@13's NPC substitute as a TALK read
does). walk@14's route loop, walk@15's memory, side cells and visited set are reused (the same
code), and walk@15's module is untouched."""

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
def mods() -> tuple[ModuleType, ...]:
    sys.path.insert(0, str(SCRIPTS))
    for name in ("walk5", "walk6", "reloc2", "where_fix", "walk7", "walk8", "walk9", "walk10",
                 "walk11", "work_zone", "walk12", "walk13", "walk14", "walk15",
                 "walk16"):  # fmt: skip
        _load(name, SCRIPTS / f"{name}.py")
    return tuple(sys.modules[n] for n in ("walk16", "walk15", "walk14", "walk13", "walk12",
                                          "walk11"))  # fmt: skip


def names(code: types.CodeType) -> set[str]:
    out = set(code.co_names)
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            out |= names(c)
    return out


def test_walk16_reuses_walk14_15_and_leaves_them_untouched(mods: Any) -> None:
    w16, w15, w14, w13, w12, w11 = mods
    assert w16._route14.__code__ is inspect.unwrap(w14.walk_route).__code__
    assert w16._route14.__globals__ is vars(w16)  # its click_step is walk@16's
    assert w16.side_cell is w15.side_cell  # walk@15's E, unchanged
    assert w16.run11.__code__ is w11.run.__code__ and w16._run12.__code__ is w12.run.__code__
    assert w15.WALK8_RULE == "walk@15" and w16.WALK8_RULE == "walk@16"
    assert w15._route14.__globals__ is vars(w15)


def test_every_name_walk16s_code_uses_resolves(mods: Any) -> None:
    w16 = mods[0]
    pool = set().union(*(vars(m) for m in mods))
    for fn in (w16._route14, w16.run11, w16._run12, w16.finish_failed, w16.finish_session,
               w16.run, w16.click_step, w16._walk_route, w16.npc_cells_near):  # fmt: skip
        used = {n for n in names(fn.__code__) if n in pool}
        missing = sorted(n for n in used if n not in vars(w16) and not hasattr(builtins, n))
        assert not missing, (fn.__name__, missing)


class Cam:
    def project(self, cells: Any, alt: Any = None) -> np.ndarray:
        c = np.asarray(cells, dtype=float)
        return np.stack([640 + 30 * c[:, 0], 384 + 20 * c[:, 1]], axis=1)


def pick(camera: Any, gat: Any, belief: Any, px: Any) -> np.ndarray:
    u, v = np.asarray(px, dtype=float)[0]
    return np.array([[round((u - 640) / 30), round((v - 384) / 20)]])


def box(cls: str, cell: tuple[int, int]) -> Any:
    u, v = 640 + 30 * cell[0], 384 + 20 * cell[1]
    return SimpleNamespace(cls=cls, foot=(u, v), x0=u - 10, y0=v - 40, x1=u + 10, y1=v)


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


GOAL = (16, 10)


@pytest.fixture
def route(mods: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    """walk@16's route loop on a flat world; the GOAL's own points are refused by a unit's
    envelope whose nearest class is set per test; every other cell clicks."""
    w16, w15, w14 = mods[0], mods[1], mods[2]
    for mod in (w16, w15, w14):
        monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(w16.r, "ns", lambda: 0)
    monkeypatch.setattr(w16.r, "game_region", lambda: (0, 0, 1280, 720))
    monkeypatch.setattr(w16, "moved", lambda a, b: (True, 1.0))
    monkeypatch.setattr(w16, "preview", lambda *a, **k: None)
    mem = w15.NpcClearMemory()
    monkeypatch.setitem(w16.UNITS, "memory", mem)
    state: dict[str, Any] = {"nearest": "npc", "clicks": []}

    def step(pr: Any, w: Any, end: tuple[int, int], expect: str = "walk",
             accept_unnamed: bool = False) -> dict[str, Any]:  # fmt: skip
        if end == GOAL:
            return {
                "clicked": False,
                "outcome": "covered_unit_envelope",
                "target": [{"shape": "walk", "envelope": {"nearest": state["nearest"]}}],
            }
        state["clicks"].append(end)
        return {"clicked": True, "outcome": "confirmed", "target": [], "at": (0.0, 0.0),
                "t_click": 0}  # fmt: skip

    monkeypatch.setattr(w14, "click_step", step)  # under walk@15's and walk@16's wrappers
    pr = SimpleNamespace(agent=None, background=None,
                         screen=SimpleNamespace(grab=lambda *a: (0, None)))  # fmt: skip

    def go(npc_at: tuple[int, int] | None, cls: str = "npc") -> tuple[dict[str, Any], Flat]:
        if npc_at is not None:
            mem.observe([box(cls, npc_at)], Cam(), None, (0, 0), 0, 400, pick=pick)
        w = Flat((10, 10))
        did = w16._walk_route(pr, w, GOAL, BAND, 4, lambda *a: None, None, None,
                              relocalise=lambda *a: {"ok": True}, clock=Clock())  # fmt: skip
        return did, w

    return w16, state, go


def test_an_npc_envelope_refusal_beside_the_goal_takes_the_npc_substitute(route: Any) -> None:
    """walk@15 indoor clean route 44: the goal one cell from an NPC, refused by its envelope three
    times, declined unit_stays. walk@16 reads it as TALK: walk@13's substitute, ring 1."""
    w16, state, go = route
    did, w = go((17, 10))
    sub = did.get("npc_substitute")
    assert did.get("arrived_belief") and sub is not None and w.position == tuple(sub), did
    assert max(abs(sub[0] - GOAL[0]), abs(sub[1] - GOAL[1])) == 1  # ring 1 around the goal
    assert max(abs(sub[0] - 17), abs(sub[1] - 10)) >= 2  # never on or next to the NPC
    marks = [e for e in did["events"] if e.get("npc_envelope_talk")]
    assert marks and marks[0]["npc_envelope_talk"] == [[17, 10]]
    assert not w16.GOAL  # cleared when the route ends


def test_an_npc_two_cells_away_does_not_trigger_it(route: Any) -> None:
    """The verifier counts an NPC substitute only with an NPC within one cell of the goal."""
    w16, state, go = route
    did, _ = go((18, 10))
    assert did.get("npc_substitute") is None and did.get("decline") == "unit_stays", did
    assert not any(e.get("npc_envelope_talk") for e in did["events"])


def test_a_monster_envelope_is_walk15s_rule(route: Any) -> None:
    w16, state, go = route
    state["nearest"] = "monster"
    did, _ = go((17, 10), cls="monster")
    assert did.get("npc_substitute") is None and did.get("decline") == "unit_stays", did


def test_only_the_goal_is_marked(mods: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """A waypoint refused next to an NPC is walk@14's re-plan, not a substitute."""
    w16 = mods[0]
    w16.GOAL[:] = [(30, 30)]
    try:
        step = {"outcome": "covered_unit_envelope", "clicked": False,
                "target": [{"envelope": {"nearest": "npc"}}]}  # fmt: skip
        monkeypatch.setattr(mods[2], "click_step", lambda *a, **k: dict(step))
        got = w16.click_step(None, SimpleNamespace(position=(0, 0)), GOAL)
        assert "npc_envelope_talk" not in got and "talk_cells" not in got
    finally:
        w16.GOAL.clear()
