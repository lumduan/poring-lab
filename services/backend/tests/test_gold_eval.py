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


# --- gef10-eval.md AMENDMENT R2-2: G1 --collapse-species / --gold-dir, G2 score-cache ----------


def _gold(tmp_path: Path, boxes: list[dict], pred_boxes: list[dict]) -> tuple[Path, Path, Path]:
    hand = {"session": "S", "frames": [{"frame_id": 7, "t_mono_ns": 100, "boxes": boxes}]}
    (tmp_path / "elsewhere").mkdir()
    hc = tmp_path / "elsewhere" / "hand.json"
    hc.write_text(json.dumps(hand))
    gd = tmp_path / "nas-gold" / "S"
    gd.mkdir(parents=True)
    (gd / "index.json").write_text(json.dumps({"7": 100}))
    p = tmp_path / "p.json"
    p.write_text(json.dumps({"weights": "w.pt", "imgsz": 1280, "conf": 0.25,
                             "frames": {"7": pred_boxes}}))  # fmt: skip
    return hc, gd, p


def test_collapse_keeps_player_npc_warp_and_makes_every_species_a_monster(
    gold: ModuleType,
) -> None:
    got = gold.collapse([{"cls": c, "x1": 0} for c in
                         ("player", "npc", "warp", "monster", "orc_lady", "poring")])  # fmt: skip
    assert [b["cls"] for b in got] == ["player", "npc", "warp", "monster", "monster", "monster"]
    assert got[4]["x1"] == 0


def test_score_collapse_species_and_gold_dir(
    gold: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hand_boxes = [{"x1": 0, "y1": 0, "x2": 40, "y2": 40, "cls": "monster"},
                  {"x1": 50, "y1": 50, "x2": 60, "y2": 80, "cls": "npc"}]  # fmt: skip
    pred = [{"cls": "orc_lady", "x1": 10, "y1": 10, "x2": 30, "y2": 30, "conf": 0.9},
            {"cls": "npc", "x1": 50, "y1": 50, "x2": 60, "y2": 80, "conf": 0.9},
            {"cls": "warp", "x1": 0, "y1": 0, "x2": 40, "y2": 40, "conf": 0.9}]  # fmt: skip
    hc, gd, p = _gold(tmp_path, hand_boxes, pred)
    # default: unchanged -- a species class is no label_iou class, so the monster is missed
    assert gold.score("S", [p], "position", gold_dir=gd, handcheck=hc) == 0
    plain = json.loads(capsys.readouterr().out)["w.pt"]
    assert "collapse_species" not in plain
    assert (plain["per_class"]["monster"]["tp"], plain["per_class"]["monster"]["fn"]) == (0, 1)
    assert gold.main(["score", "S", str(p), "--metric", "position", "--collapse-species",
                      "--gold-dir", str(gd), "--handcheck", str(hc)]) == 0  # fmt: skip
    out = json.loads(capsys.readouterr().out)["w.pt"]
    mon, npc = out["per_class"]["monster"], out["per_class"]["npc"]
    assert out["collapse_species"] is True and out["frames"] == 1
    assert (mon["tp"], mon["fp"], mon["fn"]) == (1, 0, 0)  # the warp box is not a monster
    assert (npc["tp"], npc["fp"], npc["fn"]) == (1, 0, 0)


def test_handcheck_falls_back_to_the_pinned_nas_copy(gold: ModuleType, tmp_path: Path) -> None:
    nas = tmp_path / "nas"
    (nas / "S").mkdir(parents=True)
    (nas / "S" / "handcheck.json").write_text("{}")
    assert gold.handcheck_path("S", nas) == nas / "S" / "handcheck.json"
    (tmp_path / "hand").mkdir()
    (tmp_path / "hand" / "S.json").write_text("{}")
    assert gold.handcheck_path("S", nas) == tmp_path / "hand" / "S.json"  # the local one first


def test_yolo_rows_become_pixel_boxes(gold: ModuleType) -> None:
    import numpy as np

    rows = np.asarray([[1, 0.5, 0.5, 0.1, 0.2], [2, 0.25, 0.75, 0.05, 0.1]], np.float32)
    got = gold.yolo_boxes(rows, {0: "player", 1: "monster", 2: "npc"}, (1280, 720))
    assert [b["cls"] for b in got] == ["monster", "npc"]
    assert [round(got[0][k], 3) for k in ("x1", "y1", "x2", "y2")] == [576, 288, 704, 432]
    assert [round(got[1][k], 3) for k in ("x1", "y1", "x2", "y2")] == [288, 504, 352, 576]
    with pytest.raises(ValueError, match="class id 3"):
        gold.yolo_boxes(np.asarray([[3, 0.5, 0.5, 0.1, 0.1]]), {0: "player"}, (1280, 720))


def test_png_size_reads_the_ihdr(gold: ModuleType) -> None:
    import numpy as np

    from poring_dataset.shards import encode_png

    assert gold.png_size(encode_png(np.zeros((72, 128, 3), np.uint8))[:24]) == (128, 72)
    with pytest.raises(ValueError, match="not a PNG"):
        gold.png_size(b"\xff\xd8\xff" + bytes(21))


def _cache(root: Path) -> Path:
    """A two-session cache in the frame-cache layout: <session>.<9 digits>.{png,txt,json}."""
    import io
    import tarfile

    import numpy as np

    from poring_dataset.shards import encode_png

    cache = root / "nas" / ".framecache" / "c1"
    cache.mkdir(parents=True)
    png = encode_png(np.zeros((72, 128, 3), np.uint8))
    rows = {("T", 1): "1 0.5 0.5 0.25 0.5\n2 0.1 0.1 0.1 0.1\n", ("T", 2): "",
            ("O", 1): "1 0.5 0.5 0.5 0.5\n"}  # fmt: skip
    with tarfile.open(cache / "shard-000000.tar", "w") as tar:
        for (sess, fid), txt in rows.items():
            k = f"{sess}.{fid:09d}"
            for ext, data in (("png", png), ("txt", txt.encode()),
                              ("json", json.dumps({"session": sess}).encode())):  # fmt: skip
                info = tarfile.TarInfo(f"{k}.{ext}")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
    (cache / "split.json").write_text(json.dumps({"train": ["O"], "val": [], "test": ["T"]}))
    (cache / "manifest.json").write_text(json.dumps({
        "cache_id": "c1", "names": {"0": "player", "1": "monster", "2": "npc"},
        "sessions": {"T": {"kept": 2, "shards": ["shard-000000.tar"]},
                     "O": {"kept": 1, "shards": ["shard-000000.tar"]}}}))  # fmt: skip
    return cache


def test_score_cache_scores_every_pred_on_the_cache_labels(
    gold: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cache = _cache(tmp_path)
    # T.1's monster: (48, 18)-(80, 54) in the 128 x 72 frame; its npc (6.4, 3.6)-(19.2, 10.8)
    hit = {"cls": "orc_lady", "x1": 50, "y1": 20, "x2": 70, "y2": 50, "conf": 0.9}
    miss = {"cls": "npc", "x1": 100, "y1": 60, "x2": 110, "y2": 70, "conf": 0.9}
    good = {"weights": "new.pt", "imgsz": 1280, "conf": 0.25,
            "frames": {"T.000000001": [hit], "T.000000002": []}}  # fmt: skip
    v1 = {"weights": "v1.pt", "imgsz": 1280, "conf": 0.25,
          "frames": {"T.000000001": [miss], "T.000000002": [miss]}}  # fmt: skip
    (tmp_path / "new.json").write_text(json.dumps(good))
    (tmp_path / "v1.json").write_text(json.dumps(v1))
    assert gold.main(["score-cache", str(tmp_path / "v1.json"), str(tmp_path / "new.json"),
                      "--cache", str(cache), "--session", "T"]) == 0  # fmt: skip
    out = json.loads(capsys.readouterr().out)
    assert (out["frames"], out["truth_boxes"], out["collapse_species"]) == (2, 2, True)
    new, old = out["runs"]["new.pt"]["per_class"], out["runs"]["v1.pt"]["per_class"]
    assert (new["monster"]["tp"], new["monster"]["fp"], new["npc"]["fn"]) == (1, 0, 1)
    assert (old["monster"]["fn"], old["npc"]["tp"], old["npc"]["fp"]) == (1, 0, 2)
    assert out["runs"]["new.pt"]["metric"] == "position"


def test_score_cache_refuses_a_missing_frame_and_a_wrong_split(
    gold: ModuleType, tmp_path: Path
) -> None:
    cache = _cache(tmp_path)
    p = tmp_path / "p.json"
    p.write_text(json.dumps({"weights": "w", "frames": {"T.000000001": []}}))
    with pytest.raises(SystemExit, match="1 of 2 frames missing"):
        gold.main(["score-cache", str(p), "--cache", str(cache), "--session", "T"])
    with pytest.raises(SystemExit, match="not in c1's test split"):
        gold.main(["score-cache", str(p), "--cache", str(cache), "--session", "O"])


def test_cache_refs_are_container_paths_to_the_frames_in_place(
    gold: ModuleType, tmp_path: Path
) -> None:
    cache = _cache(tmp_path)
    out = tmp_path / "refs.json"
    assert gold.main(["refs", "--out", str(out), "--cache", str(cache), "--session", "T",
                      "--host-root", str(tmp_path / "nas")]) == 0  # fmt: skip
    refs = json.loads(out.read_text())
    assert list(refs) == ["T.000000001", "T.000000002"]
    r = refs["T.000000001"]
    assert r["path"] == "/datasets/.framecache/c1/shard-000000.tar"
    with (cache / "shard-000000.tar").open("rb") as fh:
        fh.seek(r["offset"])
        assert gold.png_size(fh.read(24)) == (128, 72)


GOLD_SESSION = "20261004T103815-console-s2-indoor-v2"
NAS_GOLD = Path("/mnt/poring-lab-datasets/archive/train/eval/gold") / GOLD_SESSION
NAS_HAND = Path("/mnt/poring-lab-datasets") / GOLD_SESSION / "handcheck.json"


@pytest.mark.skipif(not (NAS_GOLD / "pred-v1png-20261008.json").exists() or not NAS_HAND.exists(),
                    reason="the NAS gold set is not mounted")  # fmt: skip
def test_real_g1_reproduces_v1s_recorded_gold_numbers(
    gold: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    """v1-vs-v0png.md: v1 PyTorch on the gold set, position, monsters 83 / 9 / 17 = P 0.902, R
    0.830; NPCs 52 / 1 / 2. Collapsing changes nothing for v1's own three classes."""
    pred = NAS_GOLD / "pred-v1png-20261008.json"
    for extra in ([], ["--collapse-species"]):
        assert gold.main(["score", GOLD_SESSION, str(pred), "--metric", "position",
                          "--gold-dir", str(NAS_GOLD), "--handcheck", str(NAS_HAND),
                          *extra]) == 0  # fmt: skip
        run = json.loads(capsys.readouterr().out)["/data/train/v1png-20261008/weights/last.pt"]
        mon, npc = run["per_class"]["monster"], run["per_class"]["npc"]
        assert run["frames"] == 27
        assert (mon["tp"], mon["fp"], mon["fn"], mon["precision"], mon["recall"]) == (
            83, 9, 17, 0.902, 0.83)  # fmt: skip
        assert (npc["tp"], npc["fp"], npc["fn"]) == (52, 1, 2)


V1_CACHE = Path("/mnt/poring-lab-datasets/.framecache/v1png-20261008")


@pytest.mark.skipif(not (V1_CACHE / "manifest.json").exists(), reason="the NAS cache is absent")
def test_real_g2_labels_as_predictions_score_one_and_shifted_zero(gold: ModuleType) -> None:
    """The POSITIVE CASE on v1's held-out 054429 (v1-vs-v0png.md: 1,077 frames, 4,186 boxes): its
    own labels, renamed to a species, as the detections -> monsters and NPCs P = R = 1; moved off
    the frame -> 0."""
    samples, names, manifest = gold.cache_samples(V1_CACHE, gold.G2_SESSION)
    truth = {s.key: gold.yolo_boxes(s.labels, names, gold.frame_size(s)) for s in samples}
    assert len(truth) == 1077 and sum(len(v) for v in truth.values()) == 4186
    assert manifest["sessions"][gold.G2_SESSION]["boxes"] == 4186
    perfect = {"weights": "perfect", "frames": {
        k: [{**b, "cls": "poring" if b["cls"] == "monster" else b["cls"]} for b in v]
        for k, v in truth.items()}}  # fmt: skip
    off = {"weights": "off", "frames": {
        k: [{**b, "x1": b["x1"] + 2000, "x2": b["x2"] + 2000} for b in v]
        for k, v in truth.items()}}  # fmt: skip
    res = gold.score_cache_truth(truth, [(Path("p"), perfect), (Path("o"), off)])
    for c in ("monster", "npc"):
        p = res["perfect"]["per_class"][c]
        assert (p["fp"], p["fn"], p["precision"], p["recall"]) == (0, 0, 1.0, 1.0)
        assert res["off"]["per_class"][c]["tp"] == 0
    assert res["perfect"]["per_class"]["monster"]["tp"] == 2568
    assert res["perfect"]["per_class"]["npc"]["tp"] == 1618
