"""scripts/build_frame_cache.py's ITEM frames (docs/planning/item-class.md 3g / 6, pre-registered
2026-10-23): the class list with the appended ``item`` class, the Route-U records read from
item_labels.py's output, their YOLO lines (our own ``player`` + every ``item``), the TRAIN-only
rule, and a written shard on a synthetic session (no client pixels: a generated JPEG)."""

from __future__ import annotations

import importlib.util
import json
import sys
import tarfile
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
ITEM_LIST = ROOT / "config" / "detector" / "classes-v2orc-item.json"
SID = "20990101T000000-demo-hunt-synthetic"


def load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def bfc() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    return load("build_frame_cache_items_under_test", SCRIPTS / "build_frame_cache.py")


def test_item_list_appends_item_after_the_15(bfc: ModuleType) -> None:
    base = bfc.SpeciesClasses.load(bfc.SPECIES_LIST)
    c = bfc.SpeciesClasses.load(ITEM_LIST)
    assert c.fixed == base.fixed and c.monsters == base.monsters and c.first == base.first
    assert c.appended == {"item": 15}
    assert base.appended == {} and "appended" not in base.provenance()
    assert c.provenance()["appended"] == {"item": 15}


def test_appended_ids_must_stay_contiguous(bfc: ModuleType, tmp_path: Path) -> None:
    doc = json.loads(ITEM_LIST.read_text())
    doc["appended"] = {"item": 16}  # a gap after the monsters' 3..14
    p = tmp_path / "gap.json"
    p.write_text(json.dumps(doc))
    with pytest.raises(SystemExit):
        bfc.SpeciesClasses.load(p)


def _rec(
    k: int, items: list[dict[str, Any]], status: str = "keep", route_u: bool = True
) -> dict[str, Any]:
    return {
        "sid": SID,
        "frame": f"{k:05d}-{1000 + k}.jpg",
        "k": k,
        "t_ns": 1000 + k,
        "status": status,
        "reasons": [],
        "route_u": route_u,
        "units": 0,
        "items": items,
        "self_box": [623.0, 266.0, 657.0, 340.0],
    }


ITEM = {"floor_id": 5, "item_id": 909, "kind": "fall", "box": [700.0, 400.0, 716.0, 412.0]}


def test_item_yolo(bfc: ModuleType) -> None:
    c = bfc.SpeciesClasses.load(ITEM_LIST)
    edge = {**ITEM, "item_id": 512, "box": [1270.0, 400.0, 1290.0, 412.0]}  # clipped at x 1280
    text, rows = bfc.item_yolo(_rec(3, [ITEM, edge]), c, 1280, 720)
    lines = text.splitlines()
    assert [ln.split()[0] for ln in lines] == ["0", "15", "15"]
    cx, cy, w, h = map(float, lines[1].split()[1:])
    assert (cx, cy) == pytest.approx((708 / 1280, 406 / 720), abs=1e-6)
    assert (w, h) == pytest.approx((16 / 1280, 12 / 720), abs=1e-6)
    assert float(lines[2].split()[3]) == pytest.approx(10 / 1280, abs=1e-6)
    assert rows == [[0, None, "self"], [15, 909, "item"], [15, 512, "item"]]
    # a negative frame: our own box only
    text, rows = bfc.item_yolo(_rec(15, []), c, 1280, 720)
    assert text.splitlines()[0].startswith("0 ") and len(rows) == 1


def _session(tmp: Path) -> tuple[Path, Path]:
    datasets, labels = tmp / "datasets", tmp / "item-r1" / "labels"
    frames = tmp / "frames"
    frames.mkdir(parents=True)
    (datasets / SID).mkdir(parents=True)
    (datasets / SID / "manifest.json").write_text(
        json.dumps(
            {"session_id": SID, "kind": "demo", "map": "prt_fild08", "frames_dir": str(frames)}
        )
    )
    recs = [
        _rec(3, [ITEM]),
        _rec(6, [ITEM], status="exclude"),
        _rec(9, [ITEM], route_u=False),
        _rec(15, []),
    ]
    rng = np.random.default_rng(1)
    for r in recs:
        Image.fromarray(rng.integers(0, 255, (720, 1280, 3), dtype=np.uint8)).save(
            frames / r["frame"], quality=80
        )
    d = labels / "prt_fild08" / "train"
    d.mkdir(parents=True)
    (d / f"{SID}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
    return datasets, labels


def test_item_records_keep_route_u_only(bfc: ModuleType, tmp_path: Path) -> None:
    _datasets, labels = _session(tmp_path)
    recs = bfc.item_records(labels, "prt_fild08.gat", SID)
    assert [r["k"] for r in recs] == [3, 15]
    with pytest.raises(SystemExit):
        bfc.item_records(labels, "orcsdun01", SID)


def test_item_session_writes_train_only(bfc: ModuleType, tmp_path: Path) -> None:
    datasets, labels = _session(tmp_path)
    c = bfc.SpeciesClasses.load(ITEM_LIST)
    a = SimpleNamespace(item_labels=labels, datasets=datasets, image="jpeg", quality=95)
    with pytest.raises(SystemExit):
        bfc.item_session(SID, "test", a, None, c)
    dry = bfc.item_session(SID, "train", a, None, c)
    assert (dry["kept"], dry["item_boxes"], dry["frames_with_items"]) == (2, 1, 1)
    out = tmp_path / "cache"
    out.mkdir()
    sink = bfc.ShardSink(out, 1 << 30)
    row = bfc.item_session(SID, "train", a, sink, c)
    sink.close()
    assert row["shards"] == ["shard-000000.tar"]
    with tarfile.open(out / "shard-000000.tar") as tar:
        names = sorted(tar.getnames())
        assert names == [f"{SID}.{k:09d}.{e}" for k in (3, 15) for e in ("jpg", "json", "txt")]
        txt = tar.extractfile(f"{SID}.000000003.txt").read().decode()  # type: ignore[union-attr]
        info = json.loads(tar.extractfile(f"{SID}.000000003.json").read())  # type: ignore[union-attr]
    assert [ln.split()[0] for ln in txt.splitlines()] == ["0", "15"]
    assert info["labels"] == "item-r1" and info["boxes"][1] == [15, 909, "item"]
