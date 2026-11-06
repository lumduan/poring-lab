"""scripts/build_frame_cache.py --labels map (docs/planning/payf07-detector.md 11 / 12): the
classes-v2orc-payf07 list, the "payf07-o3h-all" frame rule (whole frames only, the weak_fit floor on
labels clear of the models), the frozen-input and TEST / FIT / join-rule gates, our own ``player``
box, the written shard, the dry run's estimate, and a cache LINKED to a finished one that the
vision reader reads unchanged.

Synthetic sessions, label files and KB only (generated pictures, ids and made-up names): no client
pixels, no rAthena data. Our own box comes from a stand-in (labels_v2.self_label is tested in
packages/poring_dataset/tests/test_labels_v2.py)."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import tarfile
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest
from PIL import Image

from poring_dataset.shards import encode_png

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
PAYF07_LIST = ROOT / "config" / "detector" / "classes-v2orc-payf07.json"
SID = "20990101T000000-rdp-thief-synthetic"
OLD = "20990101T000001-console-linked"
STAGED = "20261024T170356-rdp-stage-items-b"
T2 = "20261024T131838-rdp-thief-t2"
SELF = (620.0, 290.0, 654.0, 364.0)


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
    return load("build_frame_cache_map_under_test", SCRIPTS / "build_frame_cache.py")


@pytest.fixture(scope="module")
def ml() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    import map_labels

    return map_labels


def kept(gid: int, mob: int, x0: float, ncc: float | None = 0.8, under: bool = False
         ) -> dict[str, Any]:  # fmt: skip
    return {"gid": gid, "mob": mob, "box": [x0, 300.0, x0 + 40.0, 360.0], "ncc": ncc, "dx": 0,
            "dy": 0, "motion": 0, "heading": 1, "facing_from": "fix2:after_move",
            "state": "idle", "under": under}  # fmt: skip


def frame(fid: int, k: list[dict[str, Any]], excluded: list[list[Any]] | None = None,
          excluded_frame: list[str] | None = None) -> dict[str, Any]:  # fmt: skip
    excluded, excluded_frame = excluded or [], excluded_frame or []
    return {"frame_id": fid, "t": 1_000_000_000 * fid, "shard": "shard-000000.tar", "offset": 0,
            "size": 0, "spot": None, "kept": k, "excluded": excluded, "hidden": 0,
            "excluded_frame": excluded_frame,
            "whole": not excluded and not excluded_frame}  # fmt: skip


# --- the class list ---------------------------------------------------------------------------


def test_payf07_list_appends_the_six_species_after_v2orc(bfc: ModuleType, ml: ModuleType) -> None:
    base = bfc.SpeciesClasses.load(bfc.SPECIES_LIST)
    c = bfc.SpeciesClasses.load(PAYF07_LIST)
    assert c.fixed == base.fixed and c.first == base.first and c.appended == {}
    assert c.monsters[:12] == base.monsters
    assert all(c.index[m] == base.index[m] for m in base.monsters)  # ids 0-14 unchanged
    assert {m: c.index[m] for m in c.monsters[12:]} == {1033: 15, 1010: 16, 1116: 17, 1060: 18,
                                                        1031: 19, 1080: 20}  # fmt: skip
    assert set(c.monsters[12:]) == set(ml.PAYF07.species)


# --- the frame rule ---------------------------------------------------------------------------


def test_map_frame_writes_only_whole_frames_above_the_floor(bfc: ModuleType) -> None:
    idx = bfc.SpeciesClasses.load(PAYF07_LIST).index
    ok = frame(1, [kept(1, 1033, 100.0), kept(2, 1010, 200.0, 0.30, under=True),
                   kept(3, 1116, 300.0, 0.479)])  # fmt: skip
    boxes, why = bfc.map_frame(ok, 0.479, idx)
    assert why == []  # under a model: o3h judged it; at the floor exactly: kept
    assert boxes == [(15, 1033, [100.0, 300.0, 140.0, 360.0]),
                     (16, 1010, [200.0, 300.0, 240.0, 360.0]),
                     (17, 1116, [300.0, 300.0, 340.0, 360.0])]  # fmt: skip
    assert bfc.map_frame(frame(2, [kept(1, 1033, 100.0, 0.478)]), 0.479, idx) == \
        ([], ["weak_fit:1033"])  # fmt: skip
    assert bfc.map_frame(frame(3, [kept(1, 1060, 100.0, None)]), 0.479, idx)[1] == \
        ["weak_fit:1060"]  # fmt: skip
    mixed = frame(4, [kept(1, 1033, 100.0, 0.2)], [[9, 1033, "engaged"]], ["warp_in_view"])
    assert bfc.map_frame(mixed, 0.479, idx) == \
        ([], ["engaged:1033", "warp_in_view", "weak_fit:1033"])  # fmt: skip
    assert bfc.map_frame(frame(5, [kept(1, 1099, 100.0)]), 0.479, idx)[1] == \
        ["species_unlisted:1099"]  # fmt: skip
    # 7's fallback: without a Green Plant class, a frame where one is EXCLUDED is not whole either
    v2orc = bfc.SpeciesClasses.load(bfc.SPECIES_LIST).index
    gp = frame(6, [], [[4, 1080, "occluded_model"]])
    assert bfc.map_frame(gp, 0.479, v2orc)[1] == ["occluded_model:1080",
                                                  "species_unlisted:1080"]  # fmt: skip
    assert bfc.map_frame(frame(7, []), 0.479, idx) == ([], [])  # our own box only: whole
    dropped = {"frame_id": 8, "excluded_frame": ["ui_layout_mismatch"], "whole": False}
    assert bfc.map_frame(dropped, 0.479, idx) == ([], ["ui_layout_mismatch"])
    liar = {**frame(9, [kept(1, 1033, 100.0)], [[2, 1010, "unfit"]]), "whole": True}
    with pytest.raises(SystemExit):
        bfc.map_frame(liar, 0.479, idx)


def test_shard_count_follows_the_sinks_rotation(bfc: ModuleType, tmp_path: Path) -> None:
    datas = [1500, 2500, 800, 3000, 100, 2000, 2600]
    sink = bfc.ShardSink(tmp_path, 5000)
    for i, d in enumerate(datas):
        sink.add(f"k{i:03d}", {"bin": b"x" * d})
    sink.close()
    assert bfc.shard_count([d + bfc.TAR_HEADER for d in datas], 5000) == len(sink.done) == 3
    assert bfc.shard_count([], 5000) == 0


def test_join_rule_3c(bfc: ModuleType) -> None:
    own = {"a": "ADDED", "b": "NOT_ADDED_C1"}
    assert bfc.join_verdict(STAGED, STAGED, {}) == "STAGED_FIT"
    assert [bfc.join_verdict(s, STAGED, own) for s in ("a", "b", "c")] == \
        ["ADDED", "NOT_ADDED_C1", "MISSING"]  # fmt: skip


# --- the frozen inputs ------------------------------------------------------------------------


def write(path: Path, doc: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc))
    return path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def params_file(tmp: Path, status: str = "FROZEN") -> Path:
    return write(tmp / "params" / f"params-{status}.json",
                 {"labels": "payf07-o3h", "status": status, "map": "pay_fild07",
                  "offset_ms": 120.0, "o3h_tau": 0.479, "tau": 0.092})  # fmt: skip


def label_doc(tmp: Path, params: Path, part: str, frames: list[dict[str, Any]],
              name: str | None = None) -> Path:  # fmt: skip
    sid = part.partition(":")[0]
    return write(tmp / "labels" / f"{name or sid}.json",
                 {"labels": "payf07-o3h", "map": "pay_fild07", "params_sha256": sha(params),
                  "params_status": "FROZEN", "part": part, "session": sid,
                  "frames": frames})  # fmt: skip


def check_doc(tmp: Path, params: Path, verdicts: dict[str, str]) -> Path:
    return write(tmp / "checks" / "check.json",
                 {"params_sha256": sha(params),
                  "per_part": {k: {"own_c1": v} for k, v in verdicts.items()}})  # fmt: skip


def inputs(params: Path, labels: list[Path], checks: list[Path]) -> SimpleNamespace:
    return SimpleNamespace(map_params=params, map_params_sha256=sha(params), map_labels=labels,
                           own_c1=checks)  # fmt: skip


def test_inputs_fail_closed(bfc: ModuleType, tmp_path: Path) -> None:
    p = params_file(tmp_path)
    lab = label_doc(tmp_path, p, SID, [frame(1, [])])
    chk = check_doc(tmp_path, p, {SID: "ADDED", f"{STAGED}:spots=0,1": "ADDED"})
    mli = bfc.MapLabelInputs.from_args(inputs(p, [lab], [chk]))
    assert (set(mli.docs), mli.own, mli.floor) == ({SID}, {SID: "ADDED"}, 0.479)
    assert mli.provenance["rule"] == "payf07-o3h-all"
    assert mli.provenance["params_sha256"] == sha(p)
    staged = label_doc(tmp_path, p, f"{STAGED}:spots=0-7", [frame(2, [])], "fit")
    assert set(bfc.MapLabelInputs.from_args(inputs(p, [staged], [])).docs) == {STAGED}
    bad = [
        SimpleNamespace(**{**vars(inputs(p, [lab], [])), "map_params_sha256": "0" * 64}),
        inputs(params_file(tmp_path, "PROPOSED_NOT_FROZEN"), [lab], []),
        inputs(p, [label_doc(tmp_path, params_file(tmp_path, "OTHER"), SID, [], "other")], []),
        inputs(p, [label_doc(tmp_path, p, T2, [], "t2")], []),  # TEST
        inputs(p, [label_doc(tmp_path, p, f"{STAGED}:spots=8-11", [], "s8")], []),  # TEST spots
        inputs(p, [label_doc(tmp_path, p, f"{STAGED}:spots=6-8", [], "s68")], []),
        inputs(p, [label_doc(tmp_path, p, STAGED, [], "whole-staged")], []),
        inputs(p, [lab], [check_doc(tmp_path, params_file(tmp_path, "X2"), {SID: "ADDED"})]),
        inputs(p, [], []),
    ]
    for a in bad:
        with pytest.raises(SystemExit):
            bfc.MapLabelInputs.from_args(a)
    twice = bfc.MapLabelInputs.from_args(
        inputs(p, [lab, label_doc(tmp_path, p, SID, [frame(1, [])], "again")], [])
    )
    with pytest.raises(SystemExit):
        twice.frames(SID)


# --- a synthetic recorder session -------------------------------------------------------------


def picture(i: int) -> np.ndarray:
    img = np.zeros((720, 1280, 3), np.uint8)
    img[100 + 10 * i : 200 + 10 * i, 300:500] = (25 * i, 200, 90)
    return img


def recorder_session(datasets: Path, sid: str, n: int) -> list[tuple[str, int, int]]:
    """A 1-fps PNG recorder session (3c's recording path): (shard, offset, size) per frame."""
    d = datasets / sid
    d.mkdir(parents=True)
    with tarfile.open(d / "shard-000000.tar", "w") as tar:
        for i in range(1, n + 1):
            for ext, data in (
                ("png", encode_png(picture(i))),
                ("json", json.dumps({"frame_id": i, "t_mono_ns": 1_000_000_000 * i}).encode()),
            ):
                info = tarfile.TarInfo(f"{i:09d}.{ext}")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))  # fmt: skip
    (d / "manifest.json").write_text(json.dumps({
        "session_id": sid, "backend": "rdp", "recorder_version": 5, "format": "png",
        "game_region": [80, 77, 1280, 720], "server": "lab-rathena",
        "shards": ["shard-000000.tar"]}))  # fmt: skip
    with tarfile.open(d / "shard-000000.tar") as tar:
        return [("shard-000000.tar", m.offset_data, m.size) for m in tar if m.name.endswith("png")]


def session_frames(refs: list[tuple[str, int, int]]) -> list[dict[str, Any]]:
    fs = [
        frame(1, [kept(1, 1033, 100.0), kept(2, 1010, 1260.0, 0.7)]),  # whole (one box clipped)
        frame(2, [kept(1, 1033, 100.0)], [[5, 1033, "engaged"]]),
        frame(3, [kept(1, 1060, 100.0, 0.3)]),  # weak_fit
        frame(4, []),  # our own box only
    ]
    for f, (shard, off, size) in zip(fs, refs, strict=True):
        f.update(shard=shard, offset=off, size=size)
    return fs


def fake_lab() -> Any:
    return SimpleNamespace(size=(1280, 720),
                           timeline=SimpleNamespace(events=[], inferred_aid=7))  # fmt: skip


@pytest.fixture()
def world(bfc: ModuleType, ml: ModuleType, tmp_path: Path,
          monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:  # fmt: skip
    datasets = tmp_path / "datasets"
    refs = recorder_session(datasets, SID, 4)
    p = params_file(tmp_path)
    lab = label_doc(tmp_path, p, SID, session_frames(refs))
    chk = check_doc(tmp_path, p, {SID: "ADDED"})
    kb = write(tmp_path / "kb" / "classes.json",
               {"m": {str(j): {"aegis": f"M{j}"} for j in
                      json.loads(PAYF07_LIST.read_text())["monsters"]}})  # fmt: skip
    monkeypatch.setattr(bfc, "self_box", lambda lab, spec, tw, dead: (SELF, None))
    monkeypatch.setattr(ml, "session_labeler", lambda path, spec: fake_lab())
    return {"datasets": datasets, "params": p, "labels": lab, "check": chk, "kb": kb.parent,
            "out": tmp_path / "out"}  # fmt: skip


def opts(w: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(datasets=w["datasets"], image="png", quality=95, max_per_session=None,
                           shard_mb=512)  # fmt: skip


def test_map_session_writes_whole_frames_with_our_own_box(
    bfc: ModuleType, world: dict[str, Any]
) -> None:
    classes = bfc.SpeciesClasses.load(PAYF07_LIST)
    mli = bfc.MapLabelInputs.from_args(inputs(world["params"], [world["labels"]],
                                              [world["check"]]))  # fmt: skip
    with pytest.raises(SystemExit):  # TRAIN, or VAL to monitor (T-7); never TEST
        bfc.map_session(SID, "test", opts(world), None, classes, mli)
    dry = bfc.map_session(SID, "train", opts(world), None, classes, mli)
    assert (dry["seen"], dry["kept"], dry["join_rule_3c"]) == (4, 2, "ADDED")
    assert dry["excluded"] == {"engaged": 1, "weak_fit": 1}
    assert dry["boxes_by_class_id"] == {"0": 2, "15": 1, "16": 1}
    assert dry["shards"] == [] and dry["est_shards"] == 1
    out = world["out"]
    out.mkdir()
    sink = bfc.ShardSink(out, 512 << 20)
    row = bfc.map_session(SID, "train", opts(world), sink, classes, mli)
    sink.close()
    assert {k: v for k, v in row.items() if k != "shards"} == \
        {k: v for k, v in dry.items() if k != "shards"}  # fmt: skip
    assert row["shards"] == ["shard-000000.tar"]
    with tarfile.open(out / "shard-000000.tar") as tar:
        got = {m.name: tar.extractfile(m).read() for m in tar}  # type: ignore[union-attr]
    assert sorted(got) == [f"{SID}.{k:09d}.{e}" for k in (1, 4) for e in ("json", "png", "txt")]
    lines = got[f"{SID}.000000001.txt"].decode().splitlines()
    assert [ln.split()[0] for ln in lines] == ["0", "15", "16"]
    cx, cy, w, h = map(float, lines[0].split()[1:])
    assert (cx * 1280, cy * 720, w * 1280, h * 720) == pytest.approx((637, 327, 34, 74), abs=1e-3)
    assert float(lines[2].split()[3]) * 1280 == pytest.approx(20.0, abs=1e-3)  # clipped at 1280
    assert got[f"{SID}.000000004.txt"].decode().split()[0] == "0"
    info = json.loads(got[f"{SID}.000000001.json"])
    assert info["labels"] == "payf07-o3h-all" and info["map"] == "pay_fild07"
    assert info["boxes"] == [[0, None, "self"], [15, 1033, "fit"], [16, 1010, "fit"]]
    back = np.asarray(Image.open(io.BytesIO(got[f"{SID}.000000001.png"])).convert("RGB"))
    assert np.array_equal(back[:, :, ::-1], picture(1))
    with tarfile.open(out / "shard-000000.tar") as tar:
        assert row["est_bytes"] == sum(m.size + bfc.TAR_HEADER for m in tar)


def test_self_box_fails_closed(bfc: ModuleType, ml: ModuleType) -> None:
    def lab(world: Any) -> Any:
        return SimpleNamespace(timeline=SimpleNamespace(frame_world=lambda tw: world))

    here = SimpleNamespace(self_pos=(10.0, 10.0), map="pay_fild07.gat")
    assert bfc.self_box(lab(here), ml.PAYF07, 50, [(40, 60)]) == (None, "self_dead")
    nowhere = SimpleNamespace(self_pos=None, map="pay_fild07")
    assert bfc.self_box(lab(nowhere), ml.PAYF07, 5, []) == (None, "self_unknown")
    elsewhere = SimpleNamespace(self_pos=(1.0, 1.0), map="prontera")
    assert bfc.self_box(lab(elsewhere), ml.PAYF07, 5, []) == (None, "self_unknown")


# --- the build, a linked cache, the vision reader ---------------------------------------------


def linked(bfc: ModuleType, out: Path, names: dict[int, str]) -> Path:
    d = out / "old"
    d.mkdir(parents=True)
    sink = bfc.ShardSink(d, 512 << 20)
    sink.add(f"{OLD}.000000001", {"png": encode_png(picture(9)), "txt": b"3 0.5 0.5 0.1 0.1\n",
                                  "json": json.dumps({"session": OLD}).encode()})  # fmt: skip
    sink.close()
    rows = {OLD: {"split": "train", "kept": 1, "shards": ["shard-000000.tar"],
                  "boxes_by_class_id": {"3": 1}}}  # fmt: skip
    (d / "manifest.json").write_text(json.dumps({
        "names": {str(k): v for k, v in names.items()}, "sessions": rows, "shards": sink.done,
        "split": {"train": [OLD], "val": [], "test": []}}))  # fmt: skip
    return d


def argv(w: dict[str, Any], *extra: str) -> list[str]:
    return ["--labels", "map", "--classes", "species", "--class-list", str(PAYF07_LIST),
            "--kb", str(w["kb"]), "--map-params", str(w["params"]),
            "--map-params-sha256", sha(w["params"]), "--map-labels", str(w["labels"]),
            "--datasets", str(w["datasets"]), "--out", str(w["out"]), "--image", "png",
            "--train", SID, *extra]  # fmt: skip


def test_the_build_links_a_finished_cache_for_the_vision_reader(
    bfc: ModuleType, world: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    names = bfc.SpeciesClasses.load(PAYF07_LIST).names(world["kb"])
    assert names[15] == "m1033" and len(names) == 21
    linked(bfc, world["out"], {k: v for k, v in names.items() if k < 15})
    full = argv(world, "--own-c1", str(world["check"]), "--link-cache", "old")
    assert bfc.main([*full, "--dry-run"]) == 0
    printed = capsys.readouterr().out
    dry = json.loads(printed[printed.index("\n{\n") + 1 :])
    assert dry["train_combined"] == {
        "frames": 3,
        "boxes_by_class_id": {"0": 2, "3": 1, "15": 1, "16": 1},
    }
    assert dry["would_refuse_3c"] == [] and not (world["out"] / "new").exists()
    with pytest.raises(SystemExit):  # 3c: no own C1 -> a real build refuses
        bfc.main([*argv(world, "--link-cache", "old"), "--cache-id", "new"])
    assert bfc.main([*full, "--cache-id", "new"]) == 0
    man = json.loads((world["out"] / "new" / "manifest.json").read_text())
    assert man["sessions"][OLD]["shards"] == ["../old/shard-000000.tar"]
    assert man["split"]["train"] == [SID, OLD] and len(man["names"]) == 21
    assert man["map_labels"]["rule"] == "payf07-o3h-all" and man["linked"]["cache_id"] == "old"
    shards = load("poring_vision_shards_map", ROOT / "services/vision/src/poring_vision/shards.py")
    samples, got_names = shards.load_split(world["out"] / "new", "train")
    assert got_names[20] == "m1080"
    assert sorted(s.session for s in samples) == sorted([OLD, SID, SID])
    old = next(s for s in samples if s.session == OLD)
    assert old.labels[:, 0].tolist() == [3.0] and len(shards.read_image(old)) == old.size


def test_link_and_split_gates(bfc: ModuleType, world: dict[str, Any]) -> None:
    names = bfc.SpeciesClasses.load(PAYF07_LIST).names(world["kb"])
    d = linked(bfc, world["out"], {**{k: v for k, v in names.items() if k < 15}, 3: "other"})
    base = argv(world, "--own-c1", str(world["check"]), "--dry-run")
    with pytest.raises(SystemExit):  # another class name for an id
        bfc.main([*base, "--link-cache", "old"])
    man = json.loads((d / "manifest.json").read_text())
    man["names"]["3"] = names[3]
    (d / "manifest.json").write_text(json.dumps(man))
    assert bfc.main([*base, "--link-cache", "old"]) == 0
    with (d / "shard-000000.tar").open("ab") as fh:
        fh.write(b"x")
    with pytest.raises(SystemExit):  # a linked shard changed size on the NAS
        bfc.main([*base, "--link-cache", "old"])
    for refused in ([*base, "--link-cache", "../old"], [*base, "--val", OLD],
                    [*base, "--train", OLD], [*base[:-1], "--fix", "x.json"]):  # fmt: skip
        with pytest.raises(SystemExit):
            bfc.main(refused)
    with pytest.raises(SystemExit):  # map options without --labels map
        bfc.main(["--labels", "v1", "--train", SID, "--map-labels", str(world["labels"])])


# --- T-7: a labelled VAL session, monitor only (xmas02-detector.md D13 / 8) --------------------

VAL = "20990101T000002-rdp-thief-synthetic-val"


def val_world(bfc: ModuleType, w: dict[str, Any], tmp_path: Path) -> Path:
    """A second labelled recorder session for VAL (no own C1: VAL needs none)."""
    refs = recorder_session(w["datasets"], VAL, 4)
    return label_doc(tmp_path, w["params"], VAL, session_frames(refs))


def dry(bfc: ModuleType, capsys: pytest.CaptureFixture[str], argv_: list[str]) -> dict[str, Any]:
    assert bfc.main(argv_) == 0
    printed = capsys.readouterr().out
    return dict(json.loads(printed[printed.index("\n{\n") + 1 :]))


def test_a_labelled_val_session_monitors_without_a_link(
    bfc: ModuleType, world: dict[str, Any], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """D13: the FIT watch is VAL, no linked cache. The dry run (nothing written) reads it under
    the same frame rule, marks it VAL_MONITOR (no 3c: no own C1 is asked of it), keeps it out of
    the TRAIN totals (which stay the train-only run's) and reports it beside them."""
    val_lab = val_world(bfc, world, tmp_path)
    base = argv(world, "--own-c1", str(world["check"]), "--dry-run")
    train_only = dry(bfc, capsys, base)
    assert "map_val_total" not in train_only
    i = base.index("--map-labels") + 1
    with_val = [*base[:i], str(world["labels"]), str(val_lab), *base[i + 1 :], "--val", VAL]
    out = dry(bfc, capsys, with_val)
    assert out["map_sessions"][VAL]["join_rule_3c"] == "VAL_MONITOR"
    assert out["map_sessions"][SID] == train_only["map_sessions"][SID]
    assert out["map_total"] == train_only["map_total"] and out["would_refuse_3c"] == []
    assert out["map_val_total"] == {"sessions": [VAL], "seen": 4, "kept": 2,
                                    "boxes_by_class_id": {"0": 2, "15": 1, "16": 1},
                                    "est_bytes": out["map_sessions"][VAL]["est_bytes"],
                                    "est_shards": 1}  # fmt: skip
    assert not (world["out"]).exists()  # a dry run: no directory, no shard
    classes = bfc.SpeciesClasses.load(PAYF07_LIST)
    mli = bfc.MapLabelInputs.from_args(inputs(world["params"], [val_lab], []))
    row = bfc.map_session(VAL, "val", opts(world), None, classes, mli)
    assert row["split"] == "val" and row["join_rule_3c"] == "VAL_MONITOR"


def test_val_keeps_every_refusal(bfc: ModuleType, world: dict[str, Any], tmp_path: Path) -> None:
    """Still refused: a labelled session in --test; an UNLABELLED --val session; one session in
    --train and --val; a VAL label file sharing frames with TEST (by role: T2; by spots: the
    staged session's 8-11); the gold set in VAL; map_session on the test split."""
    val_lab = val_world(bfc, world, tmp_path)
    base = argv(world, "--own-c1", str(world["check"]), "--dry-run")
    i = base.index("--map-labels") + 1

    def with_labels(*labels: Path) -> list[str]:
        return [*base[:i], *map(str, labels), *base[i + 1 :]]

    t2 = label_doc(tmp_path, world["params"], T2, [], "t2-val")
    s8 = label_doc(tmp_path, world["params"], f"{STAGED}:spots=8-11", [], "s8-val")
    gold = label_doc(tmp_path, world["params"], bfc.GOLD, [], "gold-val")
    for refused, why in (
        ([*with_labels(world["labels"], val_lab), "--test", VAL], "never TEST"),
        ([*base, "--val", VAL], "same sessions"),  # no label file for it
        ([*with_labels(world["labels"]), "--val", SID], "two splits"),  # in train and val
        ([*with_labels(world["labels"], t2), "--val", T2], "shares frames with TEST"),
        ([*with_labels(world["labels"], s8), "--val", STAGED], "shares frames with TEST"),
        ([*with_labels(world["labels"], gold), "--val", bfc.GOLD], "gold set"),
    ):
        with pytest.raises(SystemExit, match=why):
            bfc.main(refused)
    classes = bfc.SpeciesClasses.load(PAYF07_LIST)
    mli = bfc.MapLabelInputs.from_args(inputs(world["params"], [val_lab], []))
    with pytest.raises(SystemExit, match="never TEST"):
        bfc.map_session(VAL, "test", opts(world), None, classes, mli)
