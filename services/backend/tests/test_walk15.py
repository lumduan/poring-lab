"""scripts/walk15.py (walk@15, demonstrations 3.26): walk@14 + D (an NPC's envelope has radius 1:
no click next to a detected NPC) + E (a side cell is never one the route stood on). walk@14's route
loop and memory are reused (the same code), and walk@14's module is untouched."""

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
                 "walk11", "work_zone", "walk12", "walk13", "walk14", "walk15"):  # fmt: skip
        _load(name, SCRIPTS / f"{name}.py")
    return tuple(sys.modules[n] for n in ("walk15", "walk14", "walk13", "walk12", "walk11"))


def names(code: types.CodeType) -> set[str]:
    out = set(code.co_names)
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            out |= names(c)
    return out


def test_walk15_reuses_walk14_and_leaves_it_untouched(mods: Any) -> None:
    w15, w14, w13, w12, w11 = mods
    assert w15._route14.__code__ is inspect.unwrap(w14.walk_route).__code__
    assert w15._route14.__globals__ is vars(w15)  # its side_cell / click_step are walk@15's
    assert w15.run11.__code__ is w11.run.__code__ and w15._run12.__code__ is w12.run.__code__
    assert w14.WALK8_RULE == "walk@14" and w15.WALK8_RULE == "walk@15"
    assert inspect.unwrap(w14.walk_route).__globals__ is vars(w14)


def test_every_name_walk15s_code_uses_resolves(mods: Any) -> None:
    w15, w14, w13, w12, w11 = mods
    pool = set().union(*(vars(m) for m in mods))
    for fn in (w15._route14, w15.run11, w15._run12, w15.finish_failed, w15.finish_session,
               w15.run, w15.side_cell, w15.click_step, w15._walk_route):  # fmt: skip
        used = {n for n in names(fn.__code__) if n in pool}
        missing = sorted(n for n in used if n not in vars(w15) and not hasattr(builtins, n))
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
    return SimpleNamespace(cls=cls, foot=(u, v), x0=u - 17, y0=v - 75, x1=u + 17, y1=v)


def test_an_npc_envelope_covers_the_cells_next_to_it(mods: Any) -> None:
    """walk@14's contact: a click on the cell next to an NPC (18.9 px from its box) contacted it."""
    w15, w14 = mods[0], mods[1]
    for mem, want in ((w14.StaticMemory(), 0), (w15.NpcClearMemory(), 1)):
        mem.observe([box("npc", (3, 0))], Cam(), None, (0, 0), 0, 400, pick=pick)
        (env,) = mem.envelopes(Cam(), None, (0, 0), 0, 0.4, 400)
        assert env.radius == want
        click = (640 + 30 * 3, 384 + 20 * 1 - 4)  # the cell SOUTH of the NPC, its centre-ish
        ok, _, _ = w14.ug.click_clear(*click, mem.envelopes(Cam(), None, (0, 0), 0, 0.4, 400))
        assert ok is (want == 0)  # walk@14 let it through; walk@15 refuses it
    mon = w15.NpcClearMemory()
    mon.observe([box("monster", (3, 0))], Cam(), None, (0, 0), 0, 400, pick=pick)
    (env,) = mon.envelopes(Cam(), None, (0, 0), 0, 0.4, 400)
    assert env.radius == w14.ug.radius_cells("monster", 0.4, 400)  # monsters: walk@14's rule


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


def test_a_side_cell_is_never_where_the_route_has_stood(mods: Any,
                                                        monkeypatch: pytest.MonkeyPatch
                                                        ) -> None:  # fmt: skip
    """walk@14 route 25: the second side tried was the cell the route had come from."""
    w15, w14 = mods[0], mods[1]
    for mod in (w15, w14):
        monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(w15.r, "ns", lambda: 0)
    monkeypatch.setattr(w15.r, "game_region", lambda: (0, 0, 1280, 720))
    monkeypatch.setattr(w15, "moved", lambda a, b: (True, 1.0))
    monkeypatch.setattr(w15, "preview", lambda *a, **k: None)
    w15.UNITS["memory"].reset()
    goal = (16, 10)
    sides: list[Any] = []

    def step(pr: Any, w: Any, end: tuple[int, int], expect: str = "walk",
             accept_unnamed: bool = False) -> dict[str, Any]:  # fmt: skip
        if end == goal:
            return {"clicked": False, "target": [], "outcome": "covered_unknown"}
        return {"clicked": True, "outcome": "confirmed", "target": [], "at": (0.0, 0.0),
                "t_click": 0}  # fmt: skip

    monkeypatch.setattr(w14, "click_step", step)  # under walk@15's VISITED-noting wrapper
    real = w14.side_cell
    monkeypatch.setattr(w14, "side_cell",
                        lambda w, t, b, talk, tried: sides.append(set(tried)) or real(
                            w, t, b, talk, tried))  # fmt: skip
    monkeypatch.setattr(w14, "points_from", lambda w, c, t: 1)  # every side looks feasible
    pr = SimpleNamespace(agent=None, background=None,
                         screen=SimpleNamespace(grab=lambda *a: (0, None)))  # fmt: skip
    w = Flat((10, 10))
    did = w15._walk_route(pr, w, goal, BAND, 4, lambda *a: None, None, None,
                          relocalise=lambda *a: {"ok": True}, clock=Clock())  # fmt: skip
    assert did["sides"] == 2 and did.get("decline") == "no_click_point", did
    stood: set[tuple[int, int]] = set()
    for e in did["events"]:  # in order: a side is never a cell stood on BEFORE it was chosen
        if "from" in e:
            stood.add(tuple(e["from"]))
        if e.get("side"):
            assert tuple(e["side"]) not in stood, (e["side"], stood)
    assert all(s for s in sides)  # every side search got the cells stood on as "tried"
