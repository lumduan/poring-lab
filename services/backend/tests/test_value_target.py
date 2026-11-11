"""value_target (rogue-xmas02.md 4CB, dungeon@9.28): the box worth the most wins, not the nearest.
Synthetic species and prices only (the real ones are GPL-derived, read at run time)."""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def vt() -> ModuleType:
    path = ROOT / "scripts/value_target.py"
    spec = importlib.util.spec_from_file_location("value_target", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["value_target"] = mod
    spec.loader.exec_module(mod)
    return mod


@dataclass
class B:
    x0: float
    y0: float
    x1: float
    y1: float
    species: str | None


def test_values_come_from_the_map_model_by_aegis_name(vt: ModuleType, tmp_path: Path) -> None:
    maps = {"maps": {"m1": {"mix": {"1": 3, "2": 1}, "species": {
        "1": {"aegis": "AAA", "drops": [{"p": 0.5, "sell_oc": 100}, {"p": 0.1, "sell_oc": None}]},
        "2": {"aegis": "BBB", "drops": [{"p": 0.25, "sell_oc": 400}]}}}}}  # fmt: skip
    p = tmp_path / "maps.json"
    p.write_text(json.dumps(maps))
    v = vt.species_values("m1", p)
    assert v["aaa"] == 50.0 and v["bbb"] == 100.0
    assert v["*"] == pytest.approx((50 * 3 + 100 * 1) / 4)
    assert vt.species_values("nope", p) == {}
    assert vt.species_values("m1", tmp_path / "missing.json") == {}


def test_the_better_value_wins_unless_much_farther(vt: ModuleType) -> None:
    values = {"rich": 262.0, "poor": 76.0, "*": 166.0}
    poor_near = (0.0, B(0, 0, 10, 10, "poor"))
    for d_rich, want in ((300.0, "rich"), (450.0, "poor")):
        got = vt.pick([poor_near, (d_rich, B(0, 0, 10, 10, "rich"))], values, lambda b: b.species)
        assert got is not None and got[1].species == want, d_rich
    assert vt.pick([], values, lambda b: b.species) is None


def test_unknown_species_take_the_mean_and_ties_go_to_the_nearer(vt: ModuleType) -> None:
    values = {"a": 100.0, "*": 80.0}
    assert vt.value_of(None, values) == 80.0 and vt.value_of("zzz", values) == 80.0
    a_far, a_near = (200.0, B(0, 0, 1, 1, "a")), (100.0, B(0, 0, 1, 1, "a"))
    got = vt.pick([a_far, a_near], values, lambda b: b.species)
    assert got is not None and got[0] == 100.0


def test_distances_use_the_box_foot(vt: ModuleType) -> None:
    got = vt.distances([B(0, 0, 20, 30, "a")], (10.0, 70.0))
    assert got[0][0] == pytest.approx(40.0)
