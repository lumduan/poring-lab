"""scripts/build_frame_cache.py --labels v2 (docs/planning/labels-v2-plan.md 3.3 step 1): the v2
class names in the manifest, an excluded frame never written, the fail-closed map / NPC gates, the
dry run writes nothing and reads no image, and the v0 / v1 path is unchanged.

Synthetic sessions and a synthetic KB (map names only, no rAthena data, no client pixels). The
labels themselves are labels_v2's (tested in test_labels_v2.py / test_labels_v2_tool.py); here a
stand-in Session hands the builder ready-made ``labels_v2.Frame`` objects."""

from __future__ import annotations

import gzip
import importlib.util
import json
import os
import sys
import tarfile
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest
from PIL import Image

from poring_dataset import labels_v2 as lv
from poring_dataset.labels import CLASSES
from poring_dataset.shards import ShardWriter
from poring_dataset.timeline import FrameWorld

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
SID = "20990101T000000-demo-synthetic"
HELD = "gat_unverified"


def load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def bfc() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    return load("build_frame_cache_v2_under_test", SCRIPTS / "build_frame_cache.py")


# --- a synthetic world ------------------------------------------------------------------------


def lab(cls: str, x0: float, job: int | None = None, kind: str = "v1") -> lv.V2Label:
    return lv.V2Label(cls, x0, 300.0, x0 + 40.0, 360.0, gid=int(x0), job=job, kind=kind)


TRAINABLE = (
    lab("player", 600.0, 0, "self"),
    lab("monster", 100.0, 1002, "opaque"),
    lab("npc", 200.0, 92, "sprite_opaque"),
    lab("warp", 300.0, None, "portal"),
)

# t -> (map, Session.frame status, labels, labels_v2 exclusions)
WORLD: dict[int, tuple[str, str, tuple[lv.V2Label, ...], tuple[str, ...]]] = {
    100: ("m.gat", "ok", TRAINABLE, ()),
    200: ("m.gat", "ok", (lab("npc", 200.0, 722, "unsized"),), ("npc_unsized:722",)),
    300: ("m.gat", "gm_window", (), ()),
    400: ("elsewhere.gat", "ok", (lab("monster", 100.0, 1002),), ()),  # not in the KB
    500: ("alberta.gat", "ok", (lab("monster", 100.0, 1002),), ()),  # GAT unverified (7.6)
    600: ("m.gat", "ok", (lab("monster", -30.0, 1002), lab("npc", 900.0, 92, "sprite_opaque")), ()),
}


class FakeSession:
    """scripts/labels_v2.py Session's interface: world(t), frame(t), labeler.size / .sheets."""

    def __init__(self) -> None:
        sheets = SimpleNamespace(missing={1063: "no_name"})
        self.labeler = SimpleNamespace(size=(1280, 720), k=1.0, sheets=sheets)

    def world(self, t: int) -> FrameWorld:
        return FrameWorld(t, WORLD[t][0], 7, (100.0, 100.0), ())

    def frame(self, t: int) -> tuple[str, lv.Frame | None, Any]:
        m, status, labels, excluded = WORLD[t]
        if status != "ok":
            return status, None, None
        return "ok", lv.Frame(t, m, labels, (), excluded), None


def demo_session(root: Path, *, images: bool = True) -> Path:
    s = root / SID
    (s / "frames").mkdir(parents=True)
    (s / "manifest.json").write_text(json.dumps({"kind": "demo", "backend": "rdp"}))
    with gzip.open(s / "packets.jsonl.gz", "wt") as fh:
        fh.write("")
    for i, t in enumerate(sorted(WORLD)):
        p = s / "frames" / f"{i:04d}-{t}.png"
        if images:
            Image.new("RGB", (1280, 720), (i * 30, 60, 90)).save(p)
        else:
            p.write_bytes(b"not an image: a dry run must never open it")
    return s


def kb(root: Path) -> Path:
    d = root / "kb"
    d.mkdir()
    (d / "route.json").write_text(json.dumps({"warps": {"m": [], "alberta": []}}))
    return d


@pytest.fixture
def setup(bfc: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    gat = tmp_path / "gat"
    gat.mkdir()
    for m in ("m", "alberta"):
        (gat / f"{m}.gat").write_bytes(b"")
    monkeypatch.setattr(bfc.camera_mod, "GAT_DIR", gat)
    monkeypatch.setattr(bfc, "make_v2_session", lambda path, v2: FakeSession())
    vis = tmp_path / "warp_visibility.json"
    vis.write_text("{}")
    checked = tmp_path / "npc_checked.json"
    checked.write_text(json.dumps({"92": "fit"}))
    return {"root": tmp_path, "kb": kb(tmp_path), "vis": vis, "checked": checked,
            "demo": tmp_path / "demo", "out": tmp_path / "out"}  # fmt: skip


def v2_argv(p: dict[str, Path], *extra: str) -> list[str]:
    return ["--labels", "v2", "--kb", str(p["kb"]), "--warp-visibility", str(p["vis"]),
            "--demo-root", str(p["demo"]), "--datasets", str(p["root"] / "nas"),
            "--out", str(p["out"]), "--cache-id", "c", "--train", SID, *extra]  # fmt: skip


def members(tar_path: Path) -> dict[str, bytes]:
    with tarfile.open(tar_path) as t:
        return {m.name: t.extractfile(m).read() for m in t.getmembers()}  # type: ignore[union-attr]


# --- the build --------------------------------------------------------------------------------


def test_v2_cache_names_the_v2_classes_and_writes_only_trainable_frames(
    bfc: ModuleType, setup: dict[str, Path]
) -> None:
    demo_session(setup["demo"])
    assert bfc.main(v2_argv(setup, "--image", "png", "--npc-checked", str(setup["checked"]))) == 0
    cache = setup["out"] / "c"
    manifest = json.loads((cache / "manifest.json").read_text())
    assert manifest["labels"] == "v2"
    assert manifest["names"] == {"0": "player", "1": "monster", "2": "npc", "3": "warp"}
    assert manifest["v2"]["classes"] == lv.V2_CLASSES and manifest["v2"]["holds_lifted"] == []
    row = manifest["sessions"][SID]
    assert (row["seen"], row["kept"], row["gm_window"], row["excluded_frames"]) == (6, 2, 1, 3)
    assert row["excluded"] == {"gat_unverified": 1, "map_not_in_kb": 1, "npc_unsized": 1}
    assert row["only_npc"] == 1  # the unsized NPC frame: N2 / N3 alone would admit it
    assert row["class_boxes"] == {"monster": 2, "npc": 2, "player": 1, "warp": 1}
    assert row["species_frames"] == {"1002": 2} and row["npc_boxes"] == {"92": 2}
    assert row["sprite_lookup_missing"] == {"1063": "no_name"}
    got = members(cache / "shard-000000.tar")
    # the trainable frames are banked positions 0 (t 100) and 5 (t 600); nothing else is written
    assert sorted(got) == sorted(f"{SID}.{i:09d}.{ext}" for i in (0, 5)
                                 for ext in ("png", "txt", "json"))  # fmt: skip
    lines = got[f"{SID}.000000000.txt"].decode().splitlines()
    assert [int(x.split()[0]) for x in lines] == [0, 1, 2, 3]
    info = json.loads(got[f"{SID}.000000000.json"])
    assert info["labels"] == "v2" and info["map"] == "m" and info["ref"] == "frames/0000-100.png"
    assert info["boxes"] == [[0, 0, "self"], [1, 1002, "opaque"], [2, 92, "sprite_opaque"],
                             [3, None, "portal"]]  # fmt: skip
    clipped = got[f"{SID}.000000005.txt"].decode().splitlines()[0].split()
    assert clipped[0] == "1" and float(clipped[3]) == pytest.approx(10 / 1280, abs=1e-6)  # -30..10


def test_v2_cache_flows_into_the_vision_reader(bfc: ModuleType, setup: dict[str, Path]) -> None:
    """poring_vision.shards (the training side) reads the names and class 3 unchanged."""
    demo_session(setup["demo"])
    bfc.main(v2_argv(setup, "--image", "png", "--npc-checked", str(setup["checked"])))
    shards = load("poring_vision_shards_v2", ROOT / "services/vision/src/poring_vision/shards.py")
    samples, names = shards.load_split(setup["out"] / "c", "train")
    assert names == {0: "player", 1: "monster", 2: "npc", 3: "warp"}
    assert len(samples) == 2 and sorted(samples[0].labels[:, 0].tolist()) == [0, 1, 2, 3]


def test_npc_gate_holds_unchecked_and_rejected_sprites(
    bfc: ModuleType, setup: dict[str, Path]
) -> None:
    fr = lv.Frame(1, "m.gat", TRAINABLE, (), ())
    assert bfc.npc_reasons(fr, {}, frozenset()) == ["npc_unchecked:92"]
    assert bfc.npc_reasons(fr, {}, frozenset({"npc_unchecked"})) == []
    assert bfc.npc_reasons(fr, {"92": "fit"}, frozenset()) == []
    shifted = {"92": "fit", "m:92": "shifted"}  # a map-specific verdict wins (indoor shift, 7.6)
    assert bfc.npc_reasons(fr, shifted, frozenset({"npc_unchecked"})) == ["npc_rejected:92"]
    unsized = lv.Frame(1, "m.gat", (lab("npc", 1.0, 722, "unsized"),), (), ("npc_unsized:722",))
    assert bfc.npc_reasons(unsized, {}, frozenset()) == []  # labels_v2 already excluded it
    demo_session(setup["demo"])
    bfc.main(v2_argv(setup, "--image", "png"))  # no N3 table: every NPC sprite frame is held
    row = json.loads((setup["out"] / "c" / "manifest.json").read_text())["sessions"][SID]
    assert row["kept"] == 0 and row["excluded"]["npc_unchecked"] == 2 and row["only_npc"] == 3


def test_map_gates_fail_closed(bfc: ModuleType, setup: dict[str, Path]) -> None:
    ns = SimpleNamespace(kb=setup["kb"], warp_visibility=setup["vis"], npc_sprites=None,
                         npc_sprite_names=None, npc_extents=None, npc_checked=None,
                         cutin_rect=None, offset_ms=None, allow_hold=[], k=None)  # fmt: skip
    v2 = bfc.V2Inputs.from_args(ns)
    assert v2.maps == {"m", "alberta"}
    assert bfc.map_reasons("m.gat", v2) == []
    assert bfc.map_reasons("prt_in.gat", v2) == ["map_not_in_kb:prt_in"]
    assert bfc.map_reasons("alberta", v2) == ["gat_unverified:alberta"]
    (v2.gat_dir / "m.gat").unlink()
    assert bfc.map_reasons("m", v2) == ["gat_missing:m"]
    lifted = bfc.V2Inputs.from_args(SimpleNamespace(**{**vars(ns), "allow_hold": [HELD]}))
    assert bfc.map_reasons("alberta", lifted) == []


def test_v2_needs_the_kb_and_the_visibility_table(bfc: ModuleType, setup: dict[str, Path]) -> None:
    argv = v2_argv(setup)
    with pytest.raises(SystemExit, match="warp-visibility"):
        bfc.main([x for i, x in enumerate(argv) if i not in (4, 5)])  # no --warp-visibility
    with pytest.raises(SystemExit, match="together"):
        bfc.main([*argv, "--npc-sprites", str(setup["root"])])


# --- the dry run --------------------------------------------------------------------------------


def test_dry_run_writes_nothing_and_reads_no_image(
    bfc: ModuleType, setup: dict[str, Path], monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:  # fmt: skip
    demo_session(setup["demo"], images=False)
    monkeypatch.setattr(bfc, "read_bgr", lambda p: pytest.fail(f"read {p}"))
    monkeypatch.setattr(bfc, "ShardSink", lambda *a, **k: pytest.fail("a sink in a dry run"))
    before = sorted(p.relative_to(setup["root"]) for p in setup["root"].rglob("*"))
    assert bfc.main(v2_argv(setup, "--dry-run", "--npc-checked", str(setup["checked"]))) == 0
    assert sorted(p.relative_to(setup["root"]) for p in setup["root"].rglob("*")) == before
    assert not setup["out"].exists()
    first, rest = capsys.readouterr().out.split("\n", 1)
    row = json.loads(first)
    assert (row["session"], row["kept"], row["excluded_frames"]) == (SID, 2, 3)
    assert "shards" not in row
    out = json.loads(rest)
    assert out["dry_run"] and out["total"]["class_boxes"]["warp"] == 1
    assert out["splits"]["train"]["kept"] == 2 and out["splits"]["val"]["seen"] == 0


def test_dry_run_is_v2_only(bfc: ModuleType, setup: dict[str, Path]) -> None:
    with pytest.raises(SystemExit, match="v2"):
        bfc.main(["--labels", "v1", "--dry-run", "--train", SID])
    with pytest.raises(SystemExit, match="resume"):
        bfc.main(v2_argv(setup, "--dry-run", "--resume"))


def test_recorded_times_match_the_png_frames_without_decoding(
    bfc: ModuleType, tmp_path: Path
) -> None:
    w = ShardWriter(tmp_path, max_bytes=2000)
    for i in range(7):
        w.add(10 + i, 1000 + i, np.zeros((4, 4, 3), np.uint8))
    w.close()
    manifest = {"format": "png", "shards": w.shards}
    assert len(w.shards) > 1
    decoded = [(int(m["frame_id"]), int(m["t_mono_ns"]))
               for m, _ in bfc.session_frames(tmp_path, manifest, 15, 3)]  # fmt: skip
    assert list(bfc.recorded_times(tmp_path, manifest, 15, 3)) == decoded == [
        (10, 1000), (13, 1003), (16, 1006)]  # fmt: skip


def test_recorded_times_match_iter_every_on_an_h264_index(bfc: ModuleType, tmp_path: Path) -> None:
    """iter_every's rule: units from the first IDR, usable (hashed, outside every freeze span),
    every n-th of those."""
    rows = ["au,frame_id,idr,offset,length,t_publish_ns"]
    rows += [f"{i},{i},{int(i in (2, 12))},{i * 10},10,{1000 + i}" for i in range(20)]
    (tmp_path / "stream.idx.csv").write_text("\n".join(rows) + "\n")
    hashed = [i for i in range(20) if i != 6]
    (tmp_path / "stream.hash.csv").write_text(
        "frame_id,crc32_adler32\n" + "".join(f"{i},x\n" for i in hashed)
    )
    (tmp_path / "stream.done.json").write_text(json.dumps({"versions": {}}))
    manifest = {"format": "h264", "game_region": [0, 0, 1280, 720],
                "freezes": {"spans_ns": [[1009, 1010]]}}  # fmt: skip
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    usable = [i for i in range(2, 20) if i != 6 and i not in (9, 10)]
    assert list(bfc.recorded_times(tmp_path, manifest, 3, 1)) == [
        (i, 1000 + i) for i in usable[::3]]  # fmt: skip


# --- v0 / v1 unchanged -----------------------------------------------------------------------


class FakeLabeler:
    """qa_export.Labeler's interface for v0 / v1: a PNG-shard session on two maps."""

    def __init__(self, path: Path, labels: str = "v0", **kw: Any) -> None:
        self.size, self.offset_ms, self.labels = (64, 36), 0.0, labels
        self.timeline = SimpleNamespace(frame_world=lambda t: SimpleNamespace(
            map="prt_fild08.gat" if t < 1003 else "prontera.gat"))  # fmt: skip

    def boxes(self, t: int) -> list[dict[str, Any]] | None:
        if t == 1001:
            return None  # a GM-command window
        return [{"x1": 4.0, "y1": 4.0, "x2": 20.0, "y2": 20.0, "cls": "monster", "gid": 1}]


def test_v0_build_is_unchanged(
    bfc: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sid = "20990101T000000-console-synthetic"
    w = ShardWriter(tmp_path / "nas" / sid)
    for i in range(5):
        w.add(i, 1000 + i, np.zeros((36, 64, 3), np.uint8))
    w.close()
    (tmp_path / "nas" / sid / "manifest.json").write_text(
        json.dumps({"format": "png", "shards": w.shards})
    )
    monkeypatch.setattr(bfc.qa_export, "Labeler", FakeLabeler)
    monkeypatch.setattr(bfc, "make_v2_session", lambda *a: pytest.fail("v2 path in a v0 build"))
    assert bfc.main(["--train", sid, "--datasets", str(tmp_path / "nas"), "--out",
                     str(tmp_path / "out"), "--cache-id", "c", "--image", "png"]) == 0  # fmt: skip
    cache = tmp_path / "out" / "c"
    manifest = json.loads((cache / "manifest.json").read_text())
    assert manifest["names"] == {str(v): k for k, v in CLASSES.items()} and len(CLASSES) == 3
    assert "v2" not in manifest and "every_demo" not in manifest
    assert manifest["sessions"][sid] == {"split": "train", "format": "png", "kept": 2,
                                         "gm_window": 1, "off_scene": 2, "boxes": 2,
                                         "shards": ["shard-000000.tar"]}  # fmt: skip
    args = json.loads((cache / "progress.json").read_text())["args"]
    assert set(args) == {"labels", "k", "every", "every_png", "max_per_session", "shard_mb",
                         "image", "quality", "split"}  # fmt: skip
    got = members(cache / "shard-000000.tar")
    assert got[f"{sid}.000000000.txt"].decode().split()[0] == str(CLASSES["monster"])


def test_resume_keeps_v1_builds_and_refuses_other_v2_inputs(
    bfc: ModuleType, tmp_path: Path
) -> None:
    v1 = {"labels": "v1", "k": None, "every": 15, "every_png": 1, "max_per_session": None,
          "shard_mb": 512, "image": "jpeg", "quality": 95,
          "split": {"train": ["A"], "val": [], "test": []}}  # fmt: skip
    bfc.write_json(tmp_path, "progress.json", {"args": v1, "sessions": {}, "shards": {}})
    assert bfc.resume_state(tmp_path, dict(v1)) == ({}, {})  # an old v1 build still resumes
    v2 = {**v1, "labels": "v2", "every_demo": 1, "v2": {"warp_visibility_sha256": "a"}}
    bfc.write_json(tmp_path, "progress.json", {"args": v2, "sessions": {}, "shards": {}})
    with pytest.raises(SystemExit, match="v2"):
        bfc.resume_state(tmp_path, {**v2, "v2": {"warp_visibility_sha256": "b"}})


# --- v1 + the species split (Batt, orcsdun01-detector.md 3b item 2 / 3f) ------------------------


class SpeciesLabeler(FakeLabeler):
    """v1 boxes on prt_fild08: a player, an NPC, a Poring (1002) -- and at t 1003 a monster of a
    species outside the list (1234), at t 1004 a listed one without its sprite (v0's box)."""

    def __init__(self, path: Path, labels: str = "v1", **kw: Any) -> None:
        super().__init__(path, labels, **kw)
        ents = (SimpleNamespace(gid=1, job=1002), SimpleNamespace(gid=2, job=1234),
                SimpleNamespace(gid=3, job=1063), SimpleNamespace(gid=9, job=92))  # fmt: skip
        self.timeline = SimpleNamespace(frame_world=lambda t: SimpleNamespace(
            map="prt_fild08.gat", entities=ents))  # fmt: skip

    def boxes(self, t: int) -> list[dict[str, Any]] | None:
        if t == 1001:
            return None  # a GM-command window
        out = [{"x1": 4.0, "y1": 4.0, "x2": 20.0, "y2": 20.0, "cls": "player", "gid": 5,
                "kind": "v0"},
               {"x1": 30.0, "y1": 4.0, "x2": 40.0, "y2": 20.0, "cls": "npc", "gid": 9,
                "kind": "v0"},
               {"x1": 40.0, "y1": 10.0, "x2": 60.0, "y2": 30.0, "cls": "monster", "gid": 1,
                "kind": "opaque"}]  # fmt: skip
        if t == 1003:
            out.append({"x1": 1.0, "y1": 1.0, "x2": 9.0, "y2": 9.0, "cls": "monster", "gid": 2,
                        "kind": "opaque"})  # fmt: skip
        if t == 1004:
            out.append({"x1": 1.0, "y1": 1.0, "x2": 9.0, "y2": 9.0, "cls": "monster", "gid": 3,
                        "kind": "v0"})  # fmt: skip
        return out


def species_kb(root: Path, bfc: ModuleType) -> Path:
    d = root / "kb"
    d.mkdir()
    listed = bfc.SpeciesClasses.load(bfc.SPECIES_LIST).monsters
    rows = {str(m): {"aegis": f"MOB_{m}"} for m in listed}
    (d / "classes.json").write_text(json.dumps({"somewhere": rows}))
    return d


def test_v1_rules_with_the_species_split_only(
    bfc: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--labels v1 --classes species``: v1's frames and boxes (GM windows and off-scene frames
    skipped as v1; NO labels-v2 exclusion), the class ids of the committed species list; a frame
    with a monster the scheme cannot name (unlisted, or no sprite) is excluded, fail closed."""
    sid = "20990101T000000-console-synthetic"
    w = ShardWriter(tmp_path / "nas" / sid)
    for i in range(5):
        w.add(i, 1000 + i, np.zeros((36, 64, 3), np.uint8))
    w.close()
    (tmp_path / "nas" / sid / "manifest.json").write_text(
        json.dumps({"format": "png", "shards": w.shards})
    )
    monkeypatch.setattr(bfc.qa_export, "Labeler", SpeciesLabeler)
    monkeypatch.setattr(bfc, "make_v2_session", lambda *a: pytest.fail("v2 path in a v1 build"))
    k = species_kb(tmp_path, bfc)
    base = ["--labels", "v1", "--classes", "species", "--kb", str(k), "--train", sid,
            "--datasets", str(tmp_path / "nas"), "--out", str(tmp_path / "out"),
            "--image", "png"]  # fmt: skip
    with pytest.raises(SystemExit, match="--kb"):
        bfc.main([a for a in base if a not in ("--kb", str(k))] + ["--cache-id", "x"])
    with pytest.raises(SystemExit, match="v1"):
        bfc.main(["--labels", "v0", "--classes", "species", "--train", sid])
    assert bfc.main([*base, "--cache-id", "c"]) == 0
    cache = tmp_path / "out" / "c"
    manifest = json.loads((cache / "manifest.json").read_text())
    assert manifest["names"]["0"] == "player" and manifest["names"]["1"] == "npc"
    assert manifest["names"]["3"] == "mob_1002" and len(manifest["names"]) == 15
    row = manifest["sessions"][sid]
    assert (row["kept"], row["gm_window"], row["off_scene"]) == (2, 1, 0)
    assert row["excluded_species"] == {"species_unlisted:1234": 1, "monster_unsized:1063": 1}
    assert row["boxes_by_class_id"] == {"0": 2, "1": 2, "3": 2}
    args = json.loads((cache / "progress.json").read_text())["args"]
    assert args["classes"]["mode"] == "species" and args["k"] == 0.14
    got = members(cache / "shard-000000.tar")
    lines = got[f"{sid}.000000000.txt"].decode().splitlines()
    assert [ln.split()[0] for ln in lines] == ["0", "1", "3"]  # player, npc, Poring
    assert json.loads(got[f"{sid}.000000000.json"])["classes"] == "species"
    # the dry run: the same counts, no image read, nothing written
    monkeypatch.setattr(bfc, "session_frames", lambda *a, **kw: pytest.fail("decoded a frame"))
    monkeypatch.setattr(bfc, "recorded_times", lambda *a, **kw: iter(
        [(i, 1000 + i) for i in range(5)]))  # fmt: skip
    assert bfc.main([*base, "--dry-run"]) == 0
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["c"]


def test_yolo_lines_take_one_class_id_per_box(bfc: ModuleType) -> None:
    boxes = [{"x1": 0.0, "y1": 0.0, "x2": 10.0, "y2": 10.0, "cls": "monster"},
             {"x1": -5.0, "y1": 0.0, "x2": -1.0, "y2": 10.0, "cls": "monster"}]  # fmt: skip
    assert bfc.yolo_lines(boxes, 20, 20).split()[0] == str(CLASSES["monster"])
    assert bfc.yolo_lines(boxes, 20, 20, [7, 8]).splitlines() == [
        "7 0.250000 0.250000 0.500000 0.500000"
    ]  # the off-frame box is dropped, ids stay paired
    with pytest.raises(ValueError):
        bfc.yolo_lines(boxes, 20, 20, [7])


# --- the orcsdun01 label fix in the cache, and one build with two label modes (3f) --------------

FIT = (50.0, 290.0, 92.0, 365.0)  # a fitted box the fake fixer hands back


class FakeFixer:
    """orc_labels_fix.FixLabeler's interface: t 100 fits its Poring (pending without pixels),
    t 600 excludes its monster (1c: packets alone know it)."""

    def frame(self, t: int, img: Any) -> SimpleNamespace:
        if t == 600:
            return SimpleNamespace(applies=True, kept=[], excluded=[(70, 1002, "occluded_model")],
                                   pending=[], hidden=0)  # fmt: skip
        if img is None:
            return SimpleNamespace(applies=True, kept=[], excluded=[], hidden=0,
                                   pending=[(100, 1002, (100.0, 300.0, 140.0, 360.0))])  # fmt: skip
        return SimpleNamespace(applies=True, excluded=[], pending=[], hidden=1,
                               kept=[SimpleNamespace(gid=100, mob=1002, box=FIT)])  # fmt: skip


def test_apply_fix_is_orc_label_sheets_rule(bfc: ModuleType) -> None:
    fr = lv.Frame(1, "orcsdun01.gat", TRAINABLE, (), ())
    assert bfc.apply_fix(fr, None) == (None, ["fix_no_world"])
    assert bfc.apply_fix(fr, SimpleNamespace(applies=False)) == (fr, [])  # another map: v2's
    out, why = bfc.apply_fix(fr, SimpleNamespace(applies=True, kept=[], pending=[],
                                                 excluded=[(1, 1153, "unfit"),
                                                           (2, 1005, "next_move")]))  # fmt: skip
    assert out is None and why == ["fix_unfit:1153", "fix_next_move:1005"]
    out, why = bfc.apply_fix(fr, FakeFixer().frame(100, np.zeros(1)))
    assert why == [] and out is not None
    kinds = [(b.cls, b.kind) for b in out.labels]
    assert kinds == [("player", "self"), ("npc", "sprite_opaque"), ("warp", "portal"),
                     ("monster", "fit")]  # fmt: skip
    assert out.labels[-1].box == FIT and out.labels[-1].job == 1002
    out, _ = bfc.apply_fix(fr, FakeFixer().frame(100, None))  # a dry run: the predicted box
    assert out is not None and out.labels[-1].kind == "fit_pending"


def test_fixed_frame_checks_a_human_demos_layout_first(bfc: ModuleType) -> None:
    fr = lv.Frame(100, "orcsdun01.gat", TRAINABLE, (), ())
    img = np.zeros((720, 1280, 3), np.uint8)
    assert bfc.fixed_frame(FakeFixer(), lambda im: False, fr, 100, img)[:2] == (
        None, ["ui_layout_mismatch"])  # fmt: skip
    out, why, got = bfc.fixed_frame(FakeFixer(), lambda im: True, fr, 100, img)
    assert why == [] and out is not None and got.kept[0].box == FIT
    out, _, got = bfc.fixed_frame(FakeFixer(), lambda im: False, fr, 100, None)  # no pixels
    assert out is not None and got.pending


def params_file(root: Path) -> Path:
    p = root / "params.json"
    p.write_text(json.dumps({"labels": "v2orc-fix", "offset_ms": 120.0, "measured_on": "col3",
                             "occluders": {"rsw_sha256": "x"}}))  # fmt: skip
    return p


def v1_png_session(root: Path, sid: str) -> None:
    w = ShardWriter(root / "nas" / sid)
    for i in range(5):
        w.add(i, 1000 + i, np.zeros((36, 64, 3), np.uint8))
    w.close()
    (root / "nas" / sid / "manifest.json").write_text(
        json.dumps({"format": "png", "shards": w.shards})
    )


def test_the_test_block_and_the_mode_flags_fail_closed(
    bfc: ModuleType, setup: dict[str, Path]
) -> None:
    col2 = "20261021T122650-orcsdun01-col2"
    for argv in (["--train", col2], ["--val", col2], ["--test", col2]):
        with pytest.raises(SystemExit, match="TEST block"):
            bfc.main(["--labels", "v2", "--classes", "species", "--kb", str(setup["kb"]), *argv])
    with pytest.raises(SystemExit, match="v1-species-sessions"):
        bfc.main(["--labels", "v1", "--classes", "species", "--kb", str(setup["kb"]), "--train",
                  "A", "--v1-species-sessions", "A"])  # fmt: skip
    with pytest.raises(SystemExit, match="not in any split"):
        bfc.main(["--labels", "v2", "--classes", "species", "--kb", str(setup["kb"]), "--train",
                  "A", "--v1-species-sessions", "B"])  # fmt: skip
    with pytest.raises(SystemExit, match="--fix belongs"):
        bfc.main(["--labels", "v2", "--kb", str(setup["kb"]), "--train", "A", "--fix",
                  str(params_file(setup["root"]))])  # fmt: skip
    with pytest.raises(SystemExit, match="frozen 1d"):
        bfc.main(["--labels", "v2", "--classes", "species", "--kb", str(setup["kb"]),
                  "--train", "A", "--fix", str(params_file(setup["root"])),
                  "--offset-ms", "375.9"])  # fmt: skip


def test_one_build_two_label_modes_and_the_fix(
    bfc: ModuleType, setup: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """v1's session through ``v1 + species``, the orcsdun01 (here: synthetic) session through
    ``v2 + species + fix``: one manifest, one class list, the fitted box written, the fix's
    exclusion excluding the frame; the dry run counts both and marks the fit as pending."""
    demo_session(setup["demo"])
    v1sid = "20990101T000000-console-synthetic"
    v1_png_session(setup["root"], v1sid)
    k = setup["kb"]
    listed = bfc.SpeciesClasses.load(bfc.SPECIES_LIST).monsters
    (k / "classes.json").write_text(json.dumps({"x": {str(m): {"aegis": f"M{m}"} for m in listed}}))
    monkeypatch.setattr(bfc.qa_export, "Labeler", SpeciesLabeler)
    monkeypatch.setattr(bfc.FixInputs, "labeler", lambda self, lab: FakeFixer())
    argv = ["--labels", "v2", "--classes", "species", "--kb", str(k),
            "--npc-checked", str(setup["checked"]), "--demo-root", str(setup["demo"]),
            "--datasets", str(setup["root"] / "nas"), "--out", str(setup["out"]),
            "--image", "png", "--fix", str(params_file(setup["root"])), "--rule", "fix2",
            "--train", SID, v1sid, "--v1-species-sessions", v1sid]  # fmt: skip
    assert bfc.main([*argv, "--cache-id", "c"]) == 0
    cache = setup["out"] / "c"
    manifest = json.loads((cache / "manifest.json").read_text())
    assert manifest["labels"] == "v2" and len(manifest["names"]) == 15
    assert manifest["v1_species_sessions"] == [v1sid]
    assert manifest["fix"]["labels"] == "v2orc-fix2" and manifest["fix"]["offset_ms"] == 120.0
    assert manifest["v2"]["offset_ms"] == 120.0  # 1d replaces the benchmark's offset
    v2row, v1row = manifest["sessions"][SID], manifest["sessions"][v1sid]
    assert v2row["labels"] == "v2+v2orc-fix2" and v1row["labels"] == "v1+species"
    assert (v2row["kept"], v2row["excluded"]["fix_occluded_model"]) == (1, 1)
    assert v2row["fix"]["kept_label:1002"] == 1 and v2row["fix"]["frames_fitted"] == 2
    assert (v1row["kept"], v1row["boxes_by_class_id"]) == (2, {"0": 2, "1": 2, "3": 2})
    args = json.loads((cache / "progress.json").read_text())["args"]
    assert args["fix"]["rule"] == "fix2" and args["v1_species_sessions"] == [v1sid]
    got = members(cache / "shard-000000.tar")
    fitted = got[f"{SID}.000000000.txt"].decode().splitlines()
    cid = bfc.SpeciesClasses.load(bfc.SPECIES_LIST).index[1002]
    x0, y0, x1, y1 = FIT
    assert f"{cid} {(x0 + x1) / 2 / 1280:.6f} {(y0 + y1) / 2 / 720:.6f}" in fitted[-1]
    info = json.loads(got[f"{SID}.000000000.json"])
    assert info["fix"] == "v2orc-fix2" and info["boxes"][-1] == [cid, 1002, "fit"]
    assert f"{SID}.000000005.txt" not in got  # t 600: its monster under a model box
    v1got = members(cache / "shard-000001.tar")  # each session owns its shards
    assert json.loads(v1got[f"{v1sid}.000000000.json"])["labels"] == "v1"
    assert v1got[f"{v1sid}.000000000.txt"].decode().split()[0] == "0"  # player, the species ids
    # the dry run of the same build
    monkeypatch.setattr(bfc, "session_frames", lambda *a, **kw: pytest.fail("decoded a frame"))
    monkeypatch.setattr(bfc, "recorded_times", lambda *a, **kw: iter(
        [(i, 1000 + i) for i in range(5)]))  # fmt: skip
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        assert bfc.main([*argv, "--dry-run"]) == 0
    text = buf.getvalue()
    out = json.loads(text[text.index("{\n") :])
    assert out["fix"]["splits"]["train"]["fit_pending_frames"] == 1
    assert out["combined"]["train"]["frames_kept"] == 1 + 2
    assert out["combined"]["train"]["boxes_by_class_id"][str(cid)] == 1 + 2
    assert out["v1_species"]["train"]["kept"] == 2
    assert sorted(p.name for p in setup["out"].iterdir()) == ["c"]  # the dry run wrote nothing


# the round-3 labels' block (orc_label_sheets.py --fix --rule fix2): local / NAS data only
COL1 = Path("/mnt/poring-lab-datasets/detector-collection/orcsdun01/20261021T103231-orcsdun01-col1")
KB = Path(os.environ.get("PORING_KB", str(ROOT / "data" / "kb")))
FIX_PARAMS = Path(os.environ.get("PORING_FIX_PARAMS",
                                 "/dev/shm/poring-lab-tmp/orc-cache/params.json"))  # fmt: skip


def test_real_the_cache_fits_col1_exactly_as_orc_label_sheets() -> None:
    """col1 (3g's fix-2 labels): frame 5457 is whole (two fitted monsters), 5160 is excluded by
    2b (next_move), 5220 by the fit (unfit / ui) and 1c. The cache's path (fixed_frame) gives the
    same verdict and the same fitted boxes as orc_label_sheets._frame_fate, and without pixels
    the same packet-side exclusions, its pending labels being exactly the ones the fit judged."""
    if not (COL1 / "manifest.json").exists() or not (KB / "classes.json").exists():
        pytest.skip("col1 or the local KB is not here")
    if not FIX_PARAMS.exists():
        pytest.skip("the frozen fix parameters are not here")
    import argparse

    sys.path.insert(0, str(SCRIPTS))
    import build_frame_cache as real_bfc
    import orc_label_sheets as ols
    import orc_labels_fix as olf

    params = olf.load_params(FIX_PARAMS)
    try:
        olf.occluders_of(params)
    except SystemExit:
        pytest.skip("the frozen RSW / RSM models are not extracted here")
    ns = argparse.Namespace(kb=KB, warp_visibility=None, npc_sprites=None, npc_sprite_names=None,
                            npc_extents=None, npc_checked=None, cutin_rect=None,
                            offset_ms=float(params["offset_ms"]), allow_hold=[], k=0.14,
                            classes="species", class_list=real_bfc.SPECIES_LIST)  # fmt: skip
    v2 = real_bfc.V2Inputs.from_args(ns)
    sess = real_bfc.make_v2_session(COL1, v2)
    fix = real_bfc.FixInputs.from_args(argparse.Namespace(fix=FIX_PARAMS, rule="fix2"))
    assert fix is not None
    fixer = fix.labeler(sess.labeler)
    ols._FIX.clear()
    ols._FIX.update(sess=sess, v2=v2, layout=None, fixer=fixer)
    man = json.loads((COL1 / "manifest.json").read_text())
    refs = {r.frame_id: r for r in real_bfc.qa_export.frame_refs(COL1, man)}
    seen = {}
    for fid in (5457, 5160, 5220):
        ref = refs[fid]
        outcome, fr, _r, mk = real_bfc.decide(sess, ref.t_mono_ns, v2)
        assert outcome == "ok" and mk == "orcsdun01" and fr is not None
        img = real_bfc.qa_export.read_jpeg(ref)
        out, why, got = real_bfc.fixed_frame(fixer, None, fr, ref.t_mono_ns, img)
        _ref, _o, _rs, _w, fixed = ols._frame_fate(ref)
        assert fixed is not None and fixed[0]
        assert (out is None) == bool(fixed[2])
        if out is not None:
            mine = sorted((b.job, b.gid, b.box) for b in out.labels if b.cls == "monster")
            assert mine == sorted((m, g, box) for m, g, box in fixed[1])
        seen[fid] = why
        dry = fixer.frame(ref.t_mono_ns, None)
        side = ("occluded_model", "next_move", "ambiguous_view")
        assert sorted(dry.excluded) == sorted(x for x in got.excluded if x[2] in side)
        assert sorted(g for g, _m, _b in dry.pending) == sorted(
            [k.gid for k in got.kept] + [g for g, _m, w in got.excluded if w not in side]
        )
    assert seen[5457] == []
    assert "fix_next_move:1153" in seen[5160]
    assert {"fix_unfit:1153", "fix_ui:1153"} <= set(seen[5220])
