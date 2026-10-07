"""scripts/gold_eval.py: model-vs-hand on the gold set, scored with label_iou's own scorer."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "gold_eval.py"


@pytest.fixture
def gold(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("gold_eval", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gold_eval"] = mod
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod.label_iou, "HANDCHECK", tmp_path / "hand")
    monkeypatch.setattr(mod, "OUT", tmp_path / "out")
    return mod


def test_model_vs_hand_uses_label_iou_matching(
    gold: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "hand").mkdir()
    hand = {"session": "S", "frames": [
        {"frame_id": 7, "t_mono_ns": 100, "status": "edited", "boxes": [
            {"x1": 0, "y1": 0, "x2": 10, "y2": 10, "cls": "monster"},
            {"x1": 50, "y1": 50, "x2": 60, "y2": 60, "cls": "npc"}]},
        {"frame_id": 9, "t_mono_ns": 200, "status": "accepted", "boxes": []},
    ]}  # fmt: skip
    (tmp_path / "hand" / "S.json").write_text(json.dumps(hand))
    (tmp_path / "out" / "S").mkdir(parents=True)
    (tmp_path / "out" / "S" / "index.json").write_text(json.dumps({"7": 100, "9": 200}))
    pred = {"weights": "w.pt", "imgsz": 1280, "conf": 0.25, "frames": {
        "7": [{"cls": "monster", "x1": 1, "y1": 0, "x2": 11, "y2": 10, "conf": 0.9},
              {"cls": "monster", "x1": 50, "y1": 50, "x2": 60, "y2": 60, "conf": 0.8}],
        "9": []}}  # fmt: skip
    (tmp_path / "p.json").write_text(json.dumps(pred))
    assert gold.score("S", [tmp_path / "p.json"]) == 0
    out = json.loads(capsys.readouterr().out)["w.pt"]
    assert out["frames"] == 2
    mon, npc = out["per_class"]["monster"], out["per_class"]["npc"]
    assert (mon["tp"], mon["fp"], mon["fn"]) == (1, 1, 0)  # the npc-placed monster is a FP
    assert (npc["tp"], npc["fp"], npc["fn"]) == (0, 0, 1)  # the class must match, not IoU alone
    assert out["threshold"] == 0.5


def test_model_vs_hand_by_position(
    gold: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """phase3-plan §5f / v1-vs-v0png.md: a box of the wrong SIZE still points at the monster."""
    (tmp_path / "hand").mkdir()
    hand = {"session": "S", "frames": [
        {"frame_id": 7, "t_mono_ns": 100, "status": "edited", "boxes": [
            {"x1": 0, "y1": 0, "x2": 40, "y2": 40, "cls": "monster"}]}]}  # fmt: skip
    (tmp_path / "hand" / "S.json").write_text(json.dumps(hand))
    (tmp_path / "out" / "S").mkdir(parents=True)
    (tmp_path / "out" / "S" / "index.json").write_text(json.dumps({"7": 100}))
    box = {"cls": "monster", "x1": 15, "y1": 15, "x2": 25, "y2": 25, "conf": 0.9}
    pred = {"weights": "w.pt", "imgsz": 1280, "conf": 0.25, "frames": {"7": [box]}}
    (tmp_path / "p.json").write_text(json.dumps(pred))
    assert gold.score("S", [tmp_path / "p.json"], metric="position") == 0
    out = json.loads(capsys.readouterr().out)["w.pt"]
    mon = out["per_class"]["monster"]
    assert out["metric"] == "position" and (mon["tp"], mon["fp"], mon["fn"]) == (1, 0, 0)
    assert gold.score("S", [tmp_path / "p.json"]) == 0  # IoU 0.0625: a miss by IoU
    iou = json.loads(capsys.readouterr().out)["w.pt"]["per_class"]["monster"]
    assert (iou["tp"], iou["fp"], iou["fn"]) == (0, 1, 1)
