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


def test_position_metric_centre_in_box_one_to_one(li: ModuleType) -> None:
    """§5f: a label counts when its CENTRE lies in a same-class hand box; one-to-one by distance;
    box size is ignored (the gold set keeps v0's 44x40 for 82 % of monsters)."""
    hand = {"frames": [
        {"t_mono_ns": 1, "boxes": [b("monster", 0, 0, 44, 40), b("monster", 100, 0, 144, 40),
                                   b("npc", 200, 0, 234, 74)]},
    ]}  # fmt: skip
    auto = {1: [
        b("monster", 15, 12, 31, 30),    # tight, centre (23, 21) inside the first: TP
        b("monster", 18, 10, 30, 28),    # also inside the first, farther: one-to-one -> FP
        b("monster", 140, 30, 200, 60),  # centre (170, 45) outside the second: FP
        b("npc", 210, 10, 220, 60),      # centre inside the npc box: TP
    ]}  # fmt: skip
    r = li.score_position(hand, auto.get)
    mon, npc = r["per_class"]["monster"], r["per_class"]["npc"]
    assert (mon["tp"], mon["fp"], mon["fn"]) == (1, 2, 1)
    assert (npc["tp"], npc["fp"], npc["fn"]) == (1, 0, 0)
    assert mon["centre_px_median"] == 1.41  # |(23, 21) - (22, 20)|
    assert r["metric"] == "position"
    # a class mismatch never matches, even with the centre inside
    tp, fp, fn, _ = li.match_position([("npc", 0, 0, 10, 10)], [("monster", 2, 2, 8, 8)])
    assert (tp, fp, fn) == (0, 1, 1)


def test_position_pairs_name_which_truth_matched_which_detection(li: ModuleType) -> None:
    """eval_q1.py needs WHICH crop matched: position_pairs is match_position's own pairing."""
    truth = [("m", 0, 0, 40, 40), ("m", 30, 0, 70, 40)]  # centres (20, 20) and (50, 20)
    pred = [("m", 40, 10, 60, 30), ("m", 10, 10, 30, 30), ("n", 0, 0, 40, 40)]  # fmt: skip
    pairs = li.position_pairs(truth, pred)
    assert [(i, j) for _d, i, j in pairs] == [(0, 1), (1, 0)]  # nearest centre first
    assert li.match_position(truth, pred) == (2, 1, 0, [0.0, 0.0])
    assert li.centre_inside(("x", 40, 40, 40, 40), ("y", 0, 0, 40, 40))  # edges included
    assert not li.centre_inside(("x", 41, 0, 41, 0), ("y", 0, 0, 40, 40))
