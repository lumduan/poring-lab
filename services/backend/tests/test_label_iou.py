"""scripts/label_iou.py (Post-S2 round Part D): scoring auto-labels against a hand-checked set."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture(scope="module")
def li() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("label_iou", SCRIPTS / "label_iou.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def b(cls: str, x1: float, y1: float, x2: float, y2: float) -> dict:
    return {"cls": cls, "x1": x1, "y1": y1, "x2": x2, "y2": y2}


def test_per_class_precision_recall_and_iou(li: ModuleType) -> None:
    hand = {"frames": [
        {"t_mono_ns": 1, "status": "edited", "boxes": [b("monster", 0, 0, 10, 10),
                                                      b("npc", 100, 100, 120, 140)]},
        {"t_mono_ns": 2, "status": "accepted", "boxes": [b("player", 50, 50, 80, 120)]},
        {"t_mono_ns": 3, "status": "accepted", "boxes": []},  # a GM window: no auto-labels
    ]}  # fmt: skip
    auto = {
        1: [b("monster", 1, 0, 11, 10),  # IoU 9/11
            b("npc", 300, 300, 320, 340),  # a false positive (a hidden NPC labelled anyway)
            b("monster", 100, 100, 120, 140)],  # right place, wrong class: FP + the npc is a FN
        2: [b("player", 50, 50, 80, 120)],
        3: None,
    }  # fmt: skip
    r = li.score(hand, lambda t: auto[t])
    assert (r["frames"], r["skipped_gm_window"]) == (2, 1)
    mon, npc, ply = (r["per_class"][c] for c in ("monster", "npc", "player"))
    assert (mon["tp"], mon["fp"], mon["fn"]) == (1, 1, 0)
    assert mon["mean_iou"] == pytest.approx(round(90 / 110, 3))
    assert (npc["tp"], npc["fp"], npc["fn"]) == (0, 1, 1) and npc["mean_iou"] is None
    assert (ply["tp"], ply["precision"], ply["recall"], ply["mean_iou"]) == (1, 1.0, 1.0, 1.0)
    assert r["overall"]["tp"] == 2 and r["overall"]["fp"] == 2 and r["overall"]["fn"] == 1
