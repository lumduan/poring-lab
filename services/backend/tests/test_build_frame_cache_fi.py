"""scripts/build_frame_cache.py --labels items (docs/planning/xmas02-detector.md Amendment O.8,
ACCEPTED by O1 2026-11-10; tool T-O2): the one-class floor-item cache from scripts/fi_labels.py
label files: item frames whole + seeded negatives (1 per 3 item frames; 300 pooled from the immune
watches), FIT p31 as VAL, TRAIN by the join rule (the session's own G2, or NEGATIVE_ONLY), the
roles refused by name, the dry run's counts = the label files', and a written shard.

Synthetic sessions and label files only (generated pictures, made-up boxes): no client pixels,
no packet capture."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import tarfile
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

from poring_dataset.shards import encode_png

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
CLASSES = ROOT / "config" / "detector" / "classes-xmas02-fi.json"
P31 = "20261109T082234-rdp-hunt-xmas02-p31"
P38 = "20261109T133046-rdp-hunt-xmas02-p38"
XW2 = "20261106T151122-rdp-xmas02-xw2"
S = 1_000_000_000


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
    return load("build_frame_cache_fi_under_test", SCRIPTS / "build_frame_cache.py")


def picture(i: int) -> np.ndarray:
    img = np.zeros((720, 1280, 3), np.uint8)
    img[100 + 5 * i : 200 + 5 * i, 300:500] = (10 * i % 250, 200, 90)
    return img


def recorder_session(datasets: Path, sid: str, n: int) -> list[tuple[str, int, int]]:
    """A 1-fps PNG recorder session (3c's recording path): (shard, offset, size) per frame."""
    d = datasets / sid
    d.mkdir(parents=True)
    with tarfile.open(d / "shard-000000.tar", "w") as tar:
        for i in range(1, n + 1):
            for ext, data in (
                ("png", encode_png(picture(i))),
                ("json", json.dumps({"frame_id": i, "t_mono_ns": S * i}).encode()),
            ):
                info = tarfile.TarInfo(f"{i:09d}.{ext}")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
    (d / "manifest.json").write_text(json.dumps({
        "session_id": sid, "backend": "rdp", "recorder_version": 7, "format": "png",
        "game_region": [80, 77, 1280, 720], "server": "lab-rathena",
        "shards": ["shard-000000.tar"]}))  # fmt: skip
    with tarfile.open(d / "shard-000000.tar") as tar:
        return [("shard-000000.tar", m.offset_data, m.size) for m in tar if m.name.endswith("png")]


def item(fid: int, x0: float, dx: int = 1) -> dict[str, Any]:
    return {"floor_id": fid, "item_id": 911, "kind": "fall", "box": [x0, 400.0, x0 + 11.0, 412.0],
            "ncc": 0.9, "dx": dx, "dy": -1, "unfit": False, "under": None, "rel": [2.0, 1.0],
            "g2_clear": True}  # fmt: skip


def frames_doc(refs: list[tuple[str, int, int]], n_items: int, dx: int = 1
               ) -> list[dict[str, Any]]:  # fmt: skip
    """``n_items`` item frames (2 labels each), then item-free kept frames, one excluded."""
    out = []
    for i, (shard, off, size) in enumerate(refs, 1):
        f: dict[str, Any] = {"frame_id": i, "t": S * i, "shard": shard, "offset": off,
                             "size": size, "n_near": 0, "status": "keep", "reasons": [],
                             "items": []}  # fmt: skip
        if i <= n_items:
            f.update(n_near=2, items=[item(i % 4, 300.0, dx), item(10 + i % 4, 600.0, dx)])
        elif n_items and i == n_items + 1:
            f.update(n_near=1, status="exclude", reasons=["under_bar"],
                     items=[item(99, 640.0, dx)])  # fmt: skip
        out.append(f)
    return out


def write(path: Path, doc: Any) -> Path:
    path.write_text(json.dumps(doc))
    return path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture()
def world(tmp_path: Path) -> dict[str, Any]:
    datasets = tmp_path / "nas"
    params = write(
        tmp_path / "params.json",
        {"rule": "xmas02-fi-1", "map": "xmas_dun02", "status": "FROZEN", "anchor_px": [-4, 2]},
    )
    psha = sha(params)
    files = {}
    for sid, split, n, n_items, floors in ((P38, "train", 60, 33, 8), (P31, "val", 20, 9, 8),
                                           (XW2, "train", 30, 0, 0)):  # fmt: skip
        refs = recorder_session(datasets, sid, n)
        doc = {"rule": "xmas02-fi-1", "map": "xmas_dun02", "session": sid, "part": sid,
               "split": split, "eval_test": False, "params": str(params), "params_sha256": psha,
               "params_status": "FROZEN", "floor_items_in_packets": floors,
               "frames": frames_doc(refs, n_items)}  # fmt: skip
        files[sid] = write(tmp_path / f"{sid}.json", doc)
    return {"tmp": tmp_path, "datasets": datasets, "params": params, "sha": psha, "files": files}


def argv(w: dict[str, Any], *extra: str, files: list[str] | None = None) -> list[str]:
    fs = [str(w["files"][s]) for s in (files if files is not None else [P38, P31, XW2])]
    return [
        "--labels",
        "items",
        "--item-params",
        str(w["params"]),
        "--item-params-sha256",
        w["sha"],
        "--fi-labels",
        *fs,
        "--class-list",
        str(CLASSES),
        "--datasets",
        str(w["datasets"]),
        "--out",
        str(w["tmp"] / "cache"),
        "--image",
        "png",
        *extra,
    ]


def dry(bfc: ModuleType, capsys: pytest.CaptureFixture[str], args: list[str]) -> dict[str, Any]:
    assert bfc.main([*args, "--dry-run"]) == 0
    return json.loads(capsys.readouterr().out)  # type: ignore[no-any-return]


def test_the_class_file_is_one_floor_item_class() -> None:
    assert json.loads(CLASSES.read_text())["names"] == ["floor_item"]


def test_pure_parts(bfc: ModuleType) -> None:
    negs = [{"frame_id": i} for i in range(50)]
    a = bfc.draw_negatives(negs, 10, 7, "s")
    assert len(a) == 10 and a == bfc.draw_negatives(list(reversed(negs)), 10, 7, "s")
    assert a != bfc.draw_negatives(negs, 10, 8, "s") and a != bfc.draw_negatives(negs, 10, 7, "t")
    assert [f["frame_id"] for f in a] == sorted(f["frame_id"] for f in a)
    assert len(bfc.draw_negatives(negs, 80, 7, "s")) == 50
    f = {"items": [{"box": [0.0, 10.0, 11.0, 22.0]}, {"box": [1270.0, 700.0, 1290.0, 730.0]}]}
    lines = bfc.item_yolo_lines(f, 1280, 720).splitlines()
    assert len(lines) == 2 and all(x.startswith("0 ") for x in lines)
    bad = {"session": "s", "frames": [{"frame_id": 1, "status": "keep", "reasons": [],
                                       "items": [{"unfit": True}]}]}  # fmt: skip
    with pytest.raises(SystemExit, match="unfit"):
        bfc.item_frame_rows(bad)


def test_dry_run_counts_are_the_label_files(
    bfc: ModuleType, world: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """The positive case of T-O2: item frames / boxes = the label files' kept frames / labels;
    negatives 1 per 3 item frames (33 -> 11, 9 -> 3) and the pooled watch's (here 300 > 30: all);
    VAL is VAL_MONITOR, the watch NEGATIVE_ONLY, the hunt G2_PASS."""
    out = dry(bfc, capsys, argv(world, "--train", P38, XW2, "--val", P31, "--neg-sessions", XW2))
    rows = out["sessions"]
    p38, p31 = rows[P38], rows[P31]
    assert (p38["item_frames"], p38["item_boxes"], p38["negatives"]) == (33, 66, 11)
    assert rows[P38]["label_item_frames"] == 33 and rows[P38]["label_negatives"] == 26
    assert (p31["item_frames"], p31["item_boxes"], p31["negatives"]) == (9, 18, 3)
    assert rows[XW2]["item_frames"] == 0 and rows[XW2]["negatives"] == 30
    assert rows[P38]["join_rule"] == "G2_PASS" and rows[P31]["join_rule"] == "VAL_MONITOR"
    assert rows[XW2]["join_rule"] == "NEGATIVE_ONLY" and out["would_refuse_join"] == []
    assert out["train_total"]["item_boxes"] == 66 and out["names"] == {"0": "floor_item"}
    assert rows[P38]["excluded"] == {"under_bar": 1}
    capped = dry(bfc, capsys, argv(world, "--train", P38, XW2, "--val", P31, "--neg-sessions",
                                   XW2, "--neg-total", "5"))  # fmt: skip
    assert capped["sessions"][XW2]["negatives"] == 5


def test_the_join_rule_and_the_roles(bfc: ModuleType, world: dict[str, Any],
                                     capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    # a hunt whose clear fits sit 4 px off: G2 FAIL -> reported by the dry run, refused by a build
    doc = json.loads(world["files"][P38].read_text())
    for f in doc["frames"]:
        for it in f["items"]:
            it["dx"] = 4
    write(world["files"][P38], doc)
    out = dry(bfc, capsys, argv(world, "--train", P38, XW2, "--val", P31, "--neg-sessions", XW2))
    assert out["sessions"][P38]["join_rule"] == "G2_FAIL" and out["would_refuse_join"] == [P38]
    with pytest.raises(SystemExit, match="join rule"):
        bfc.main(argv(world, "--train", P38, XW2, "--val", P31, "--neg-sessions", XW2))
    # a hunt with too few clear fits (< 30): NOT_ENOUGH
    for f in doc["frames"]:
        for it in f["items"]:
            it["dx"], it["g2_clear"] = 1, f["frame_id"] < 10
    write(world["files"][P38], doc)
    out = dry(bfc, capsys, argv(world, "--train", P38, XW2, "--val", P31, "--neg-sessions", XW2))
    assert out["sessions"][P38]["join_rule"] == "G2_NOT_ENOUGH"
    with pytest.raises(SystemExit, match="test"):
        bfc.main(argv(world, "--train", P38, XW2, "--val", P31, "--test", "x"))
    with pytest.raises(SystemExit, match="FIT label file"):
        bfc.main(argv(world, "--train", P31, XW2, "--val", P38, "--dry-run"))
    with pytest.raises(SystemExit, match="same sessions"):
        bfc.main(argv(world, "--train", P38, "--val", P31, "--dry-run"))
    with pytest.raises(SystemExit, match="not in --train"):
        bfc.main(argv(world, "--train", P38, XW2, "--val", P31, "--neg-sessions", "other",
                      "--dry-run"))  # fmt: skip
    wrong = argv(world, "--train", P38, XW2, "--val", P31, "--dry-run")
    wrong[wrong.index(world["sha"])] = "0" * 64
    with pytest.raises(SystemExit, match="sha256"):
        bfc.main(wrong)
    held = json.loads(world["files"][P38].read_text())
    held.update(session="20261111T090000-rdp-hunt-xmas02-fiT7", eval_test=False)
    write(world["tmp"] / "fit1.json", held)
    with pytest.raises(SystemExit, match="held-out"):
        bfc.main(
            argv(world, "--train", held["session"], "--dry-run", files=[])
            + ["--fi-labels", str(world["tmp"] / "fit1.json")]
        )
    held.update(session=P38, eval_test=True)
    write(world["tmp"] / "ev.json", held)
    with pytest.raises(SystemExit, match="never cached"):
        bfc.main(
            argv(world, "--train", P38, "--dry-run", files=[])
            + ["--fi-labels", str(world["tmp"] / "ev.json")]
        )
    gw3 = {**json.loads(world["files"][XW2].read_text()), "session": "20261109T212445-rdp-gb-gw3"}
    write(world["tmp"] / "gw3.json", gw3)
    with pytest.raises(SystemExit, match="TEST"):
        bfc.main(
            argv(world, "--train", gw3["session"], "--dry-run", files=[])
            + ["--fi-labels", str(world["tmp"] / "gw3.json")]
        )
    item_rich = json.loads(world["files"][XW2].read_text())
    item_rich["floor_items_in_packets"] = 3
    write(world["files"][XW2], item_rich)
    out = dry(bfc, capsys, argv(world, "--train", P38, XW2, "--val", P31, "--neg-sessions", XW2))
    assert out["sessions"][XW2]["join_rule"] == "NOT_ITEM_FREE"


def test_the_build_writes_item_frames_and_negatives(bfc: ModuleType, world: dict[str, Any],
                                                    capsys: pytest.CaptureFixture[str]
                                                    ) -> None:  # fmt: skip
    plan = dry(bfc, capsys, argv(world, "--train", P38, XW2, "--val", P31, "--neg-sessions", XW2))
    assert bfc.main(argv(world, "--train", P38, XW2, "--val", P31, "--neg-sessions", XW2,
                         "--cache-id", "fi-test")) == 0  # fmt: skip
    capsys.readouterr()
    d = world["tmp"] / "cache" / "fi-test"
    man = json.loads((d / "manifest.json").read_text())
    assert man["labels"] == "items" and man["names"] == {"0": "floor_item"}
    assert man["split"] == {"train": [P38, XW2], "val": [P31], "test": []}
    for sid in (P38, P31, XW2):
        row = man["sessions"][sid]
        assert row["kept"] == plan["sessions"][sid]["kept"]
        assert row["item_boxes"] == plan["sessions"][sid]["item_boxes"]
    members: dict[str, bytes] = {}
    for name in man["shards"]:
        with tarfile.open(d / name) as tar:
            for m in tar:
                f = tar.extractfile(m)
                assert f is not None
                members[m.name] = f.read()
    txt = [k for k in members if k.endswith(".txt") and k.startswith(P38)]
    assert len(txt) == 33 + 11
    assert sum(bool(members[k]) for k in txt) == 33  # negatives have an empty label file
    meta = json.loads(members[f"{P38}.000000001.json"])
    assert meta["labels"] == "xmas02-fi-1" and meta["negative"] is False
    assert meta["boxes"] == [[0, 911, 1], [0, 911, 11]]
    assert all(line.startswith("0 ") for line in members[f"{P38}.000000001.txt"].decode()
               .splitlines())  # fmt: skip
    assert sum(1 for k in members if k.startswith(XW2) and k.endswith(".png")) == 30
    with pytest.raises(SystemExit, match="exists"):
        bfc.main(argv(world, "--train", P38, XW2, "--val", P31, "--neg-sessions", XW2,
                      "--cache-id", "fi-test"))  # fmt: skip


def test_o17_session_negs_raise_an_item_sessions_negatives(bfc: ModuleType) -> None:
    """O17 (round 3): --session-negs SID=N lets a pilot draw N fight negatives instead of 1 per 3
    item frames; never fewer than O.8's share; a malformed spec refuses."""
    assert bfc.session_neg_count("x-rdp-hunt-xmas02-fiT4", 24) == 8
    assert bfc.session_neg_count("x-rdp-hunt-xmas02-fiT4", 24, ["fiT4=150"]) == 150
    assert bfc.session_neg_count("x-rdp-hunt-xmas02-fiT4", 600, ["fiT4=150"]) == 200
    assert bfc.session_neg_count("x-rdp-xmas02-fs2", 92, ["fiT4=150"]) == 30
    with pytest.raises(SystemExit, match="SID=N"):
        bfc.session_neg_count("x", 3, ["fiT4"])
