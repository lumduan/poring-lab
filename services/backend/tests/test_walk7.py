"""scripts/walk7.py (walk@7, demonstrations 3.12): walk@6's gate, unchanged, with the route's
decisions fixed -- patience for what moves, a substitute for a blocked goal, re-localisation on an
unconfirmed streak -- against walk@6's fake client (test_walk6.py)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parents[2] / "scripts"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mods() -> tuple[ModuleType, ModuleType]:
    sys.path.insert(0, str(SCRIPTS))
    for name in ("walk5", "walk6", "reloc2", "walk7"):
        _load(name, SCRIPTS / f"{name}.py")
    return sys.modules["walk7"], _load("fakes_walk6", HERE / "test_walk6.py")


def bubble() -> list[tuple[int, int]]:
    # over the hotspot, as the client draws it (the RDP references: 20 / 20 talk in leave-one-out)
    return [(dx, dy) for dy in range(-10, 3) for dx in range(-8, 9)
            if (dx / 8.5) ** 2 + ((dy + 4) / 6.5) ** 2 <= 1]  # fmt: skip


class World:
    """walk@6's fake client plus static NPCs (the talk bubble), monsters that LEAVE after a number
    of grabs, and cells whose chevrons are hidden (an occluder)."""

    def __init__(self, f: ModuleType, w7: ModuleType, true: tuple[int, int], *,
                 monsters: set[tuple[int, int]] = frozenset(),  # type: ignore[assignment]
                 npcs: set[tuple[int, int]] = frozenset(),  # type: ignore[assignment]
                 hidden: set[tuple[int, int]] = frozenset()) -> None:  # type: ignore[assignment]  # fmt: skip
        f.SPRITES["talk"] = [(bubble(), (240, 240, 240))]
        walk = np.ones((60, 60), dtype=bool)
        client = f.Client(w7.w6, walk, true, monsters=set(monsters))
        client.leaves: list[tuple[int, tuple[int, int]]] = []
        client.npcs, client.hidden = set(npcs), set(hidden)
        base_shape, base_grab = client.shape_at, client.grab

        def shape_at(c: tuple[int, int]) -> str:
            return "talk" if c in client.npcs else base_shape(c)

        def grab(x: int, y: int, w: int, h: int) -> tuple[int, np.ndarray]:
            for after, cell in list(client.leaves):
                if client.grabs >= after:
                    client.monsters.discard(cell)
                    client.leaves.remove((after, cell))
            fid, img = base_grab(x, y, w, h)
            c = client.cell_under(*client.cursor)
            if c in client.hidden:  # an occluder: no chevrons, the plain arrow only
                img2 = f.background(h, w, x, y)
                f.paint(img2, client.cursor[0] - x, client.cursor[1] - y, "walk")
                return fid, img2
            return fid, img

        client.shape_at, client.grab = shape_at, grab
        self.f, self.client, self.walk = f, client, walk
        refs = f.refs_for(w7.w6, ["walk", "sword", "noentry", "talk"])
        self.pr = w7.w6.Prober(client, client, refs)
        self.w = w7.w5.World(f.Cam(), f.Gat(walk), true)


@pytest.fixture
def fake(mods: tuple[ModuleType, ModuleType], monkeypatch: pytest.MonkeyPatch) -> Any:
    w7, f = mods
    for mod in (w7, w7.w6, w7.w5):
        monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(w7.r, "game_region", lambda: (f.GX, f.GY, 1280, 720))
    monkeypatch.setattr(w7.r, "ns", lambda: 0)
    return w7, f


def ticking() -> Any:
    t = [0.0]

    def clock() -> float:
        t[0] += 0.5
        return t[0]

    return clock


BAND = (100, 60, 1180, 680)


def test_a_monster_that_moves_off_is_waited_for_not_routed_around(fake: Any) -> None:
    w7, f = fake
    sim = World(f, w7, (10, 18), monsters={(12, 18)})
    sim.client.leaves.append((12, (12, 18)))  # it walks off after a few probes
    did = w7.walk_route(sim.pr, sim.w, (16, 18), BAND, 3, lambda *a: None, None,
                        clock=ticking())  # fmt: skip
    assert did.get("arrived_belief") and sim.client.true == (16, 18), did
    assert did["replans"] == 0 and did["waited_s"] > 0 and sim.client.attacked == []


def test_a_static_npc_is_routed_around_at_once_without_waiting(fake: Any) -> None:
    w7, f = fake
    sim = World(f, w7, (10, 18), npcs={(12, 18)})
    did = w7.walk_route(sim.pr, sim.w, (16, 18), BAND, 3, lambda *a: None, None,
                        clock=ticking())  # fmt: skip
    assert did.get("arrived_belief") and sim.client.true == (16, 18), did
    assert did["replans"] == 1 and did["waited_s"] == 0
    assert all(tuple(e["end"]) != (12, 18) for e in did["events"] if e.get("clicked"))


def test_a_goal_that_stays_occupied_gets_the_nearest_free_cell(fake: Any) -> None:
    w7, f = fake
    sim = World(f, w7, (10, 18), monsters={(14, 18)})  # it never leaves
    did = w7.walk_route(sim.pr, sim.w, (14, 18), BAND, 3, lambda *a: None, None,
                        clock=ticking())  # fmt: skip
    assert did.get("arrived_belief"), did
    sub = tuple(did["substitute"])
    assert max(abs(sub[0] - 14), abs(sub[1] - 18)) == 1 and sim.client.true == sub
    assert sim.client.attacked == [] and did["waited_s"] > 0  # it waited before substituting
    subs = [e for e in did["events"] if "substitute" in e]
    assert subs and subs[0]["for"] == [14, 18]


def test_two_unconfirmed_targets_from_one_belief_re_localise(fake: Any) -> None:
    """walk@6 routes 21-24: every target came back unconfirmed from one believed cell, and that
    never triggered re-localisation."""
    w7, f = fake
    sim = World(f, w7, (10, 18), hidden={(13, 18), (13, 17), (13, 19), (12, 17), (12, 19)})
    calls: list[tuple[int, int]] = []

    def reloc(agent: Any, screen: Any, w: Any, mask: Any, band: Any) -> dict[str, Any]:
        calls.append(w.position)
        return {"ok": False, "left": 3, "probes": []}

    did = w7.walk_route(sim.pr, sim.w, (16, 18), BAND, 3, lambda *a: None, None,
                        relocalise=reloc, clock=ticking())  # fmt: skip
    assert len(calls) == 1 and did["decline"] == "relocalise_failed", did
    why = [e["why"] for e in did["events"] if "relocalise" in e]
    assert why == ["unconfirmed"]


def test_the_segment_record_carries_the_click_time(fake: Any, monkeypatch: Any) -> None:
    w7, f = fake
    ticks = iter(range(1000, 10_000, 7))
    monkeypatch.setattr(w7.w6.r, "ns", lambda: next(ticks))
    sim = World(f, w7, (10, 18))
    logged: list[tuple[int, dict[str, Any]]] = []
    w7.walk_route(sim.pr, sim.w, (13, 18), BAND, 3,
                  lambda t, frm, end, step: logged.append((t, step)), None,
                  clock=ticking())  # fmt: skip
    clicked = [(t, s) for t, s in logged if s["clicked"]]
    assert clicked and all(t == s["t_click"] for t, s in clicked)
