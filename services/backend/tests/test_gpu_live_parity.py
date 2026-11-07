"""scripts/gpu_live_parity.py: boxes match one to one only within the same class and species."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import gpu_live_parity as glp  # noqa: E402


def test_the_same_box_of_another_class_or_species_is_no_match() -> None:
    a = [10.0, 10.0, 50.0, 60.0, 0.9, "monster", "cookie"]
    cpu = [a, [100.0, 10.0, 140.0, 60.0, 0.8, "player", None]]
    gpu = [[10.5, 10.0, 50.0, 60.0, 0.9, "monster", "cookie"],
           [100.0, 10.0, 140.0, 60.0, 0.8, "npc", None],
           [10.0, 10.0, 50.0, 60.0, 0.7, "monster", "cookie_xmas"]]  # fmt: skip
    m = glp.match_same_class(cpu, gpu, 0.7)
    assert [(i, j) for i, j, _ in m] == [(0, 0)]


def test_one_to_one_greedy_from_the_best_pair() -> None:
    c = [[0.0, 0.0, 10.0, 10.0, 0.9, "monster", None], [1.0, 0.0, 11.0, 10.0, 0.9, "monster", None]]
    g = [[0.0, 0.0, 10.0, 10.0, 0.9, "monster", None]]
    m = glp.match_same_class(c, g, 0.5)
    assert [(i, j) for i, j, _ in m] == [(0, 0)] and m[0][2] == 1.0
