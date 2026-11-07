"""scripts/gpu_parity.py: the GPU vs CPU box match (cpu-detector-speed.md section 5)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import gpu_parity as gp  # noqa: E402


def test_iou_and_the_one_to_one_match() -> None:
    a = [0.0, 0.0, 10.0, 10.0]
    assert gp.iou(a, a) == 1.0 and gp.iou(a, [20, 20, 30, 30]) == 0.0
    assert abs(gp.iou(a, [0, 0, 10, 5]) - 0.5) < 1e-9
    cpu = [[0, 0, 10, 10], [50, 50, 60, 60]]
    gpu = [[0, 0, 10, 10], [0.5, 0, 10, 10], [51, 50, 61, 60]]
    assert gp.match(cpu, gpu, 0.7) == 2  # the duplicate GPU box cannot take a second match
    assert gp.match(cpu, [[0, 0, 10, 5]], 0.7) == 0


def test_only_monster_classes_count() -> None:
    rows = [[0, 0, 1, 1, 0.9, "player"], [0, 0, 2, 2, 0.8, "cookie"], [1, 1, 3, 3, 0.7, "monster"],
            [0, 0, 4, 4, 0.6, "npc"], [0, 0, 5, 5, 0.5, "warp"]]  # fmt: skip
    assert gp.monsters(rows) == [[0.0, 0.0, 2.0, 2.0], [1.0, 1.0, 3.0, 3.0]]
