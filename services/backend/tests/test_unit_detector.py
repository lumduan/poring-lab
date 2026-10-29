"""scripts/unit_detector.py: the class ids map to names by an explicit list (gef10-eval.md R2-2).

v1's three names stay the default, so the live detector is unchanged; a 26-class model gets its
names from the constructor or a sidecar next to its ONNX; an id beyond the names fails closed.
The worker is a stand-in that answers with fixed class ids (no onnxruntime here).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import unit_detector as ud  # noqa: E402

FAKE_WORKER = """
import json, struct, sys
ids = json.loads(open(sys.argv[1]).read())
while True:
    head = sys.stdin.buffer.read(8)
    if len(head) < 8:
        break
    h, w, _ = struct.unpack("<HHI", head)
    sys.stdin.buffer.read(h * w * 3)
    boxes = [[1.0, 2.0, 3.0, 4.0, 0.9, c] for c in ids]
    sys.stdout.write(json.dumps({"boxes": boxes, "ms": 1.5}) + "\\n")
    sys.stdout.flush()
"""
GEF10 = ["player", "npc", "warp", *(f"species_{i}" for i in range(3, 26))]


@pytest.fixture
def worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "fake_worker.py"
    path.write_text(FAKE_WORKER)
    monkeypatch.setattr(ud, "WORKER", path)
    return path


def model_answering(tmp_path: Path, ids: list[int]) -> Path:
    """The fake worker reads the class ids to answer from the 'model' file."""
    model = tmp_path / "m-736x1280.onnx"
    model.write_text(json.dumps(ids))
    return model


def detect(model: Path, **kw: object) -> list[ud.Box]:
    with ud.UnitDetector(model=model, python=Path(sys.executable), **kw) as det:  # type: ignore[arg-type]
        return det.detect(np.zeros((4, 6, 3), np.uint8))


def test_v1_names_are_the_default_and_unchanged(worker: Path, tmp_path: Path) -> None:
    assert ud.NAMES == ("player", "monster", "npc")
    boxes = detect(model_answering(tmp_path, [1, 2, 0]))
    assert [b.cls for b in boxes] == ["monster", "npc", "player"]
    assert (boxes[0].x0, boxes[0].score) == (1.0, 0.9)


def test_an_id_beyond_the_names_fails_closed(worker: Path, tmp_path: Path) -> None:
    with pytest.raises(ud.ClassNamesMismatch, match="class id 22 is beyond its 3 names"):
        detect(model_answering(tmp_path, [1, 22]))
    assert issubclass(ud.ClassNamesMismatch, ud.DetectorUnavailable)  # rules must not click


def test_a_26_class_model_by_argument(worker: Path, tmp_path: Path) -> None:
    boxes = detect(model_answering(tmp_path, [22, 0, 25]), names=GEF10)
    assert [b.cls for b in boxes] == ["species_22", "player", "species_25"]
    with pytest.raises(ud.ClassNamesMismatch, match="class id 26"):
        detect(model_answering(tmp_path, [26]), names=GEF10)


def test_a_26_class_model_by_sidecar_list_or_manifest_names(worker: Path, tmp_path: Path) -> None:
    model = model_answering(tmp_path, [2, 21])
    side = ud.sidecar(model)
    assert side == tmp_path / "m-736x1280.names.json"
    side.write_text(json.dumps(GEF10))
    assert [b.cls for b in detect(model)] == ["warp", "species_21"]
    side.write_text(json.dumps({str(i): n for i, n in enumerate(GEF10)}))  # a manifest's names
    assert [b.cls for b in detect(model)] == ["warp", "species_21"]


def test_the_argument_wins_over_the_sidecar(tmp_path: Path) -> None:
    model = model_answering(tmp_path, [])
    ud.sidecar(model).write_text(json.dumps(GEF10))
    assert ud.names_for(model, ["a", "b", "c"]) == ("a", "b", "c")
    assert ud.names_for(model) == tuple(GEF10)
    assert ud.names_for(tmp_path / "other.onnx") == ud.NAMES


@pytest.mark.parametrize(
    "doc",
    [[], ["a", ""], ["a", "a"], {"0": "a", "2": "b"}, {"x": "a"}, {"0": "a", "00": "b"}],
)
def test_bad_names_are_refused(doc: object) -> None:
    with pytest.raises(ValueError):
        ud.parse_names(doc)  # type: ignore[arg-type]


def test_a_bad_sidecar_refuses_the_detector(worker: Path, tmp_path: Path) -> None:
    model = model_answering(tmp_path, [0])
    ud.sidecar(model).write_text(json.dumps({"0": "player", "2": "npc"}))
    with pytest.raises(ValueError, match="without a gap"):
        ud.UnitDetector(model=model, python=Path(sys.executable))
