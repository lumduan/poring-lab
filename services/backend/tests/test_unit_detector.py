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


# --- the map-scoped model (Batt 2026-11-07: "use it"; xmas02-detector.md T-11) ------------------

XMAS02 = ["player", "npc", "warp", "mystcase", "cruiser", "cookie", "cookie_xmas"]
SPECIES = {s: "monster" for s in XMAS02[3:]}


def test_sixteen_threads_by_batts_decision() -> None:
    assert ud.THREADS == 16  # 2026-11-07; cpu-detector-speed.md 1 (never onnxruntime's auto)


def test_classes_renamed_to_one_name_share_one_nms_group() -> None:
    assert ud.nms_groups(XMAS02, SPECIES) == [0, 1, 2, 3, 3, 3, 3]
    assert ud.nms_groups(XMAS02, {}) == list(range(7))  # no collapse: one group per class
    assert ud.nms_groups(["a", "b", "c"], {"a": "x", "c": "x"}) == [0, 1, 0]


def test_collapse_renames_keeps_the_species_and_sends_the_groups(
    worker: Path, tmp_path: Path
) -> None:
    model = model_answering(tmp_path, [5, 6, 0, 3])
    with ud.UnitDetector(model=model, python=Path(sys.executable), names=XMAS02,
                         collapse=SPECIES) as det:  # fmt: skip
        boxes = det.detect(np.zeros((4, 6, 3), np.uint8))
        assert det.proc.args[-1] == "[0, 1, 2, 3, 3, 3, 3]"  # the worker's 6th argument
    assert [(b.cls, b.species) for b in boxes] == [
        ("monster", "cookie"),
        ("monster", "cookie_xmas"),
        ("player", None),
        ("monster", "mystcase"),
    ]
    plain = detect(model, names=XMAS02)  # no collapse: the names as they are, no groups argument
    assert [b.cls for b in plain] == ["cookie", "cookie_xmas", "player", "mystcase"]


def test_a_collapse_name_the_model_lacks_fails_closed(worker: Path, tmp_path: Path) -> None:
    with pytest.raises(ud.ClassNamesMismatch, match="not its classes"):
        detect(model_answering(tmp_path, [0]), names=XMAS02, collapse={"poring": "monster"})


def test_for_map_pins_the_file_and_falls_back_to_v1(
    worker: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "model").mkdir()
    onnx = tmp_path / "model" / "x-736x1280.onnx"
    onnx.write_text(json.dumps([6]))
    ud.sidecar(onnx).write_text(json.dumps(XMAS02))
    py = Path(sys.executable)
    monkeypatch.setitem(ud.MAP_MODELS, "test_map",
                        ud.MapModel(onnx.name, ud.file_sha256(onnx), SPECIES))  # fmt: skip
    with ud.for_map("test_map", env=tmp_path, python=py) as det:
        assert det.model == onnx
        assert [(b.cls, b.species) for b in det.detect(np.zeros((2, 2, 3), np.uint8))] == [
            ("monster", "cookie_xmas")
        ]
    onnx.write_text(json.dumps([5]))  # a different file under the pinned name
    with pytest.raises(ud.DetectorUnavailable, match="is not the deployed"):
        ud.for_map("test_map", env=tmp_path, python=py)
    with pytest.raises(ud.DetectorUnavailable, match="missing"):
        ud.for_map("xmas_dun02", env=tmp_path / "nowhere", python=py)
    v1 = model_answering(tmp_path, [1])
    with ud.for_map("prt_fild08", env=tmp_path, python=py, model=v1) as det:  # no entry: v1
        assert det.collapse == {} and [b.cls for b in det.detect(np.zeros((2, 2, 3), np.uint8))] \
            == ["monster"]  # fmt: skip
    with ud.for_map(None, env=tmp_path, python=py, model=v1) as det:
        assert det.collapse == {}


def test_the_deployed_xmas02_entry() -> None:
    spec = ud.MAP_MODELS["xmas_dun02"]
    assert spec.onnx == "xmas02-last-736x1280.onnx"
    assert spec.sha256.startswith("293dca92")  # xmas02-eval.md AMENDMENT 3's export
    assert sorted(spec.collapse) == sorted(XMAS02[3:]) and set(spec.collapse.values()) == {
        "monster"
    }


def test_the_worker_suppresses_a_group_together() -> None:
    import detector_worker as dw

    # two anchors on one sprite (cookie 0.9, cookie_xmas 0.8) + a far cruiser; 7 classes
    rows = []
    for (cx, cy), cid, sc in [((100, 100), 5, 0.9), ((102, 101), 6, 0.8), ((400, 300), 4, 0.7)]:
        scores = [0.0] * 7
        scores[cid] = sc
        rows.append([cx, cy, 40, 60, *scores])
    out = np.asarray(rows, np.float32).T[None]  # (1, 4 + nc, N)
    per_class = dw.decode(out, 1.0, 0, 0, 0.25, 0.5)
    grouped = dw.decode(out, 1.0, 0, 0, 0.25, 0.5, [0, 1, 2, 3, 3, 3, 3])
    assert sorted(int(r[5]) for r in per_class) == [4, 5, 6]  # the double box
    assert sorted(int(r[5]) for r in grouped) == [4, 5]  # one box, its own (higher) class
    assert [r for r in grouped if r[5] == 5] == [r for r in per_class if r[5] == 5]
