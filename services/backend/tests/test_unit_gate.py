"""scripts/unit_gate.py: the worst-case envelope (Batt 2026-10-08) -- a unit may be anywhere within
ceil(H / speed) + 1 cells at the click's arrival; NPCs stay put; our own character is not a unit."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture(scope="module")
def ug() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("unit_gate", SCRIPTS / "unit_gate.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["unit_gate"] = mod  # dataclasses resolve their annotations through it
    spec.loader.exec_module(mod)
    return mod


class Cam:  # 30 px per cell east, 20 px per cell north (up the screen); our feet at (640, 360)
    def project(self, cells: Any, alt: Any = None) -> np.ndarray:
        c = np.asarray(cells, dtype=float)
        return np.stack([640 + 30 * c[:, 0], 360 - 20 * c[:, 1]], axis=1)


def pick(camera: Any, gat: Any, belief: Any, px: Any) -> np.ndarray:
    u, v = np.asarray(px, dtype=float)[0]
    return np.array([[round((u - 640) / 30), round((360 - v) / 20)]])


class B:
    def __init__(self, cls: str, cell: tuple[int, int], w: float = 40, h: float = 40) -> None:
        u, v = 640 + 30 * cell[0], 360 - 20 * cell[1]
        self.cls, self.score = cls, 0.9
        self.x0, self.x1, self.y0, self.y1 = u - w / 2, u + w / 2, v - h, v
        self.foot = (u, v)


def test_radius_is_the_horizon_over_the_speed_plus_one_step(ug: ModuleType) -> None:
    assert ug.radius_cells("npc", 0.56, 400) == 0
    assert ug.radius_cells("monster", 0.56, 400) == 3  # ceil(1.4) + 1
    assert ug.radius_cells("monster", 0.56, 200) == 4  # ceil(2.8) + 1
    assert ug.radius_cells("player", 0.56, 400) == 5  # 150 ms a cell: ceil(3.73) + 1


def test_a_monster_three_cells_from_the_click_point_refuses_it_until_the_horizon_is_short(
    ug: ModuleType,
) -> None:
    mob = B("monster", (5, 0))
    u, v = 640 + 30 * 2, 360  # the click point: two cells east of us, three from the Poring
    envs = ug.envelopes([mob], Cam(), None, (0, 0), 0.56, 400, pick=pick)
    ok, d, who = ug.click_clear(u, v, envs)
    assert not ok and who == "monster"  # radius 3 reaches the click point
    envs = ug.envelopes([mob], Cam(), None, (0, 0), 0.05, 400, pick=pick)  # radius 2
    assert envs[0].radius == 2  # its box one cell from the click point: 10 px < the margin
    assert not ug.click_clear(u, v, envs)[0]
    envs = ug.envelopes([mob], Cam(), None, (0, 0), 0.0, 400, pick=pick)  # the extra step only
    assert envs[0].radius == 1
    ok, d, _ = ug.click_clear(u, v, envs)
    assert ok and d == 40.0


def test_a_static_npc_refuses_only_points_near_its_own_box(ug: ModuleType) -> None:
    npc = B("npc", (3, 2), w=34, h=74)
    envs = ug.envelopes([npc], Cam(), None, (0, 0), 0.56, 200, pick=pick)
    assert envs[0].radius == 0 and len(envs[0].boxes) == 1
    assert not ug.click_clear(640 + 90, 360 - 40 - 30, envs)[0]  # on its body
    assert not ug.click_clear(640 + 90 + 17 + 8, 360 - 40, envs)[0]  # 8 px from its edge
    assert ug.click_clear(640 + 90 + 17 + 20, 360 - 40, envs)[0]  # 20 px clear


def test_our_own_character_is_not_a_unit_to_avoid(ug: ModuleType) -> None:
    me = B("player", (0, 0), w=34, h=74)
    assert ug.envelopes([me], Cam(), None, (0, 0), 0.56, 400, pick=pick) == []


def test_memory_keeps_a_hidden_unit_and_grows_its_envelope(ug: ModuleType) -> None:
    """walk@11's pilot: a Poring hidden behind a pew was invisible to every layer. A unit seen once
    stays forbidden ground, its radius growing with the time since it was seen."""
    mem = ug.UnitMemory()
    s = 1_000_000_000
    mem.observe([B("monster", (3, 0))], Cam(), None, (0, 0), 10 * s, 400, pick=pick)
    mem.observe([], Cam(), None, (0, 0), 12 * s, 400, pick=pick)  # hidden now
    envs = mem.envelopes(Cam(), None, (0, 0), 12 * s, 0.5, 400)
    assert len(envs) == 1 and envs[0].radius == ug.radius_cells("monster", 2.5, 400) == 8
    assert not ug.click_clear(640 + 30 * 1, 360, envs)[0]  # 2 cells from where it was seen


def test_a_re_sighting_updates_the_unit_instead_of_adding_one(ug: ModuleType) -> None:
    mem = ug.UnitMemory()
    s = 1_000_000_000
    mem.observe([B("monster", (3, 0))], Cam(), None, (0, 0), 10 * s, 400, pick=pick)
    mem.observe([B("monster", (4, 1))], Cam(), None, (0, 0), 11 * s, 400, pick=pick)  # it hopped
    assert [(i.cell, i.t_ns) for i in mem.items] == [((4, 1), 11 * s)]
    mem.observe([B("monster", (-6, 0))], Cam(), None, (0, 0), 11 * s, 400, pick=pick)  # another
    assert len(mem.items) == 2
    mem.observe([], Cam(), None, (0, 0), 20 * s, 400, pick=pick)  # past the TTL: forgotten
    assert mem.items == []


def test_memory_cells_are_absolute_so_our_own_walk_does_not_move_them(ug: ModuleType) -> None:
    mem = ug.UnitMemory()
    s = 1_000_000_000
    mem.observe([B("npc", (3, 2), w=34, h=74)], Cam(), None, (100, 100), 1 * s, 400, pick=pick)
    assert mem.items[0].cell == (103, 102)
    envs = mem.envelopes(Cam(), None, (101, 100), 2 * s, 0.5, 400)  # we walked one cell east
    assert envs[0].cell == (2, 2) and envs[0].radius == 0
