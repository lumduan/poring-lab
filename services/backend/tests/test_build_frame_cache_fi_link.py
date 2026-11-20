"""scripts/build_frame_cache.py --labels items --link-cache (docs/planning/xmas02-items-1080.md
T-I3): one floor-item cache that MIXES a finished item cache's TRAIN (the 720 round 5's, linked
by reference under its own params) with new 1080 TRAIN sessions labelled under other item params.

- the rule of each params file is resolved by its map, rule and monster params' sha256 (a test
  stand-in for T-I1's 1080 rule is registered beside the 720 one);
- the one-sha rule holds per part; VAL is the new part's FIT only (the linked VAL is never linked);
- both parts' counts in the dry run equal the written ones; the trainer's reader sees both parts;
- a virtual 1080 session (1280 x 720 frames, recorder v8 with its client_view) passes the frame
  check; a 1920 x 1080 frame does not;
- the guarded cache step passes the new flags through unchanged.

Synthetic sessions and label files only (generated pictures, made-up boxes): no client pixels,
no packet capture."""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import io
import json
import shutil
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
sys.path.insert(0, str(SCRIPTS))

import fi_labels as fl  # noqa: E402
import rec_paths  # noqa: E402

CLASSES = ROOT / "config" / "detector" / "classes-xmas02-fi.json"
S = 1_000_000_000
# the 720 round 5's sessions (their names: the 720 rule's roles)
P31 = "20261109T082234-rdp-hunt-xmas02-p31"  # its FIT / VAL
P38 = "20261109T133046-rdp-hunt-xmas02-p38"
XW2 = "20261106T151122-rdp-xmas02-xw2"
# the 1080 round's (xmas02-items-1080.md section 4)
IFF = "20261120T213800-rdp-xmas02-ifF"  # its FIT / VAL
IFT1 = "20261121T010000-rdp-xmas02-ifT1"
IFT2 = "20261121T013000-rdp-xmas02-ifT2"
M1080 = "9c73278f" + "0" * 56  # a stand-in for params-1080.json's sha256
R5 = "r5"  # the linked cache's id
SHM = "/dev/shm/poring-lab-tmp"


def load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def bfc() -> ModuleType:
    return load("build_frame_cache_fi_link_under_test", SCRIPTS / "build_frame_cache.py")


@pytest.fixture()
def spec1080(monkeypatch: pytest.MonkeyPatch) -> Any:
    """A stand-in for T-I1's 1080 rule: the same map and rule name, its own monster params, FIT
    and held-outs. The registry is exactly the 720 rule + it for the test (whatever fi_labels
    registers once T-I1 lands)."""
    spec = dataclasses.replace(
        fl.XMAS02_FI,
        val_suffixes=("-rdp-xmas02-ifF",),
        eval_suffixes=("-rdp-xmas02-ifH1", "-rdp-xmas02-ifH2", "-rdp-xmas02-ifsH1"),
        monster_params_sha256=M1080,
        plan="docs/planning/xmas02-items-1080.md (test stand-in)",
    )
    monkeypatch.setattr(fl, "FI_MAPS", {"xmas_dun02": fl.XMAS02_FI, "xmas_dun02-1080": spec})
    return spec


def picture(i: int, size: tuple[int, int] = (1280, 720)) -> np.ndarray:
    img = np.zeros((size[1], size[0], 3), np.uint8)
    img[100 + 5 * i : 200 + 5 * i, 300:500] = (10 * i % 250, 200, 90)
    return img


def virtual_view() -> dict[str, Any]:
    chat = {"name": "chat", "virtual": [0, 578, 600, 142], "real_xy": [0, 938]}
    return {"rect": [0, 0, 1920, 1080], "mode": "fullscreen", "world_scale": 1.5,
            "world_centre": [960.0, 540.0], "panels": [chat]}  # fmt: skip


def recorder_session(datasets: Path, sid: str, n: int, virtual: bool = False,
                     size: tuple[int, int] = (1280, 720)
                     ) -> list[tuple[str, int, int]]:  # fmt: skip
    """A 1-fps PNG recorder session: the lab's 720 path, or (``virtual``) the 1920 x 1080 client
    recorded as its VIRTUAL 1280 x 720 picture (recorder v8 + client_view)."""
    d = datasets / sid
    d.mkdir(parents=True)
    with tarfile.open(d / "shard-000000.tar", "w") as tar:
        for i in range(1, n + 1):
            for ext, data in (
                ("png", encode_png(picture(i, size))),
                ("json", json.dumps({"frame_id": i, "t_mono_ns": S * i}).encode()),
            ):
                info = tarfile.TarInfo(f"{i:09d}.{ext}")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
    manifest: dict[str, Any] = {
        "session_id": sid, "backend": "rdp", "recorder_version": 7, "format": "png",
        "game_region": [80, 77, 1280, 720], "server": "lab-rathena",
        "shards": ["shard-000000.tar"]}  # fmt: skip
    if virtual:
        manifest.update(recorder_version=8, game_region=[rec_paths.VIRTUAL_X0, 0, 1280, 720],
                        client_view=virtual_view())  # fmt: skip
    (d / "manifest.json").write_text(json.dumps(manifest))
    with tarfile.open(d / "shard-000000.tar") as tar:
        return [("shard-000000.tar", m.offset_data, m.size) for m in tar if m.name.endswith("png")]


def item(fid: int, x0: float) -> dict[str, Any]:
    return {"floor_id": fid, "item_id": 911, "kind": "fall", "box": [x0, 400.0, x0 + 11.0, 412.0],
            "ncc": 0.9, "dx": 1, "dy": -1, "unfit": False, "under": None, "rel": [2.0, 1.0],
            "g2_clear": True}  # fmt: skip


def frames_doc(refs: list[tuple[str, int, int]], n_items: int) -> list[dict[str, Any]]:
    """``n_items`` item frames (2 labels each), then item-free kept frames, one excluded."""
    out = []
    for i, (shard, off, size) in enumerate(refs, 1):
        f: dict[str, Any] = {"frame_id": i, "t": S * i, "shard": shard, "offset": off,
                             "size": size, "n_near": 0, "status": "keep", "reasons": [],
                             "items": []}  # fmt: skip
        if i <= n_items:
            f.update(n_near=2, items=[item(i % 4, 300.0), item(10 + i % 4, 600.0)])
        elif n_items and i == n_items + 1:
            f.update(n_near=1, status="exclude", reasons=["under_bar"], items=[item(99, 640.0)])
        out.append(f)
    return out


def write(path: Path, doc: Any) -> Path:
    path.write_text(json.dumps(doc))
    return path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def label_file(tmp: Path, params: Path, sid: str, split: str, refs: list[tuple[str, int, int]],
               n_items: int, floors: int) -> Path:  # fmt: skip
    doc = {"rule": "xmas02-fi-1", "map": "xmas_dun02", "session": sid, "part": sid,
           "split": split, "eval_test": False, "params": str(params), "params_sha256": sha(params),
           "params_status": "FROZEN", "floor_items_in_packets": floors,
           "frames": frames_doc(refs, n_items)}  # fmt: skip
    return write(tmp / f"{params.stem}-{sid}.json", doc)


def items_argv(params: Path, files: list[Path], w: dict[str, Any], *extra: str) -> list[str]:
    return ["--labels", "items", "--item-params", str(params), "--item-params-sha256", sha(params),
            "--fi-labels", *[str(f) for f in files], "--class-list", str(CLASSES),
            "--datasets", str(w["datasets"]), "--out", str(w["out"]), "--image", "png",
            *extra]  # fmt: skip


@pytest.fixture()
def world(bfc: ModuleType, spec1080: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
          ) -> dict[str, Any]:  # fmt: skip
    """The 720 round's item cache ``r5`` (built by the builder: TRAIN p38 + the watch xw2, VAL
    p31) and three virtual 1080 sessions with label files under the 1080 params."""
    datasets, out = tmp_path / "nas", tmp_path / "cache"
    p720 = write(tmp_path / "params-v2.json",
                 {"rule": "xmas02-fi-1", "map": "xmas_dun02", "status": "FROZEN", "version": 2,
                  "monster_params_sha256": fl.XMAS02_FI.monster_params_sha256})  # fmt: skip
    p1080 = write(tmp_path / "items-params-1080.json",
                  {"rule": "xmas02-fi-1", "map": "xmas_dun02", "status": "FROZEN",
                   "monster_params_sha256": M1080, "anchor_px": [-6, 3]})  # fmt: skip
    w: dict[str, Any] = {"tmp": tmp_path, "datasets": datasets, "out": out, "p720": p720,
                         "p1080": p1080, "f720": {}, "f1080": {}}  # fmt: skip
    for sid, split, n, n_items, floors in ((P38, "train", 60, 33, 8), (P31, "val", 20, 9, 8),
                                           (XW2, "train", 30, 0, 0)):  # fmt: skip
        refs = recorder_session(datasets, sid, n)
        w["f720"][sid] = label_file(tmp_path, p720, sid, split, refs, n_items, floors)
    assert bfc.main(items_argv(p720, list(w["f720"].values()), w, "--train", P38, XW2, "--val",
                               P31, "--neg-sessions", XW2, "--cache-id", R5)) == 0  # fmt: skip
    capsys.readouterr()
    for sid, split, n, n_items in ((IFT1, "train", 45, 18), (IFT2, "train", 40, 16),
                                   (IFF, "val", 24, 9)):  # fmt: skip
        refs = recorder_session(datasets, sid, n, virtual=True)
        w["f1080"][sid] = label_file(tmp_path, p1080, sid, split, refs, n_items, 6)
    return w


def mixed(w: dict[str, Any], *extra: str, files: list[Path] | None = None) -> list[str]:
    fs = files if files is not None else [w["f1080"][s] for s in (IFT1, IFT2, IFF)]
    return items_argv(w["p1080"], fs, w, "--train", IFT1, IFT2, "--val", IFF,
                      "--link-cache", R5, *extra)  # fmt: skip


def dry(bfc: ModuleType, capsys: pytest.CaptureFixture[str], args: list[str]) -> dict[str, Any]:
    assert bfc.main([*args, "--dry-run"]) == 0
    return json.loads(capsys.readouterr().out)  # type: ignore[no-any-return]


# --- the rule of each params file ---------------------------------------------------------------


def test_each_params_file_finds_its_own_rule(bfc: ModuleType, world: dict[str, Any],
                                             spec1080: Any) -> None:  # fmt: skip
    """Two rules of xmas_dun02 share the rule name: the monster params' sha256 picks one; a params
    file that names neither is refused, never given the 720 rule by default."""
    head = json.loads(world["p720"].read_text())
    assert bfc.item_spec(fl, head, world["p720"]) is fl.XMAS02_FI
    assert bfc.item_spec(fl, json.loads(world["p1080"].read_text()), world["p1080"]) is spec1080
    assert bfc.item_specs(fl, "xmas_dun02") == [fl.XMAS02_FI, spec1080]
    with pytest.raises(SystemExit, match="0 floor-item rules"):
        bfc.item_spec(fl, {**head, "monster_params_sha256": "f" * 64}, world["p720"])
    with pytest.raises(SystemExit, match="has no floor-item rule"):
        bfc.item_spec(fl, {**head, "map": "prt_fild08"}, world["p720"])


def test_one_rule_alone_resolves_as_before(bfc: ModuleType, tmp_path: Path,
                                           monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    """With the 720 rule alone (before T-I1), a params file without a monster sha resolves to it,
    and a wrong rule name still reaches load_params' own refusal."""
    monkeypatch.setattr(fl, "FI_MAPS", {"xmas_dun02": fl.XMAS02_FI})
    p = tmp_path / "p.json"
    assert bfc.item_spec(fl, {"rule": "xmas02-fi-1", "map": "xmas_dun02"}, p) is fl.XMAS02_FI
    assert bfc.item_spec(fl, {"rule": "other", "map": "xmas_dun02"}, p) is fl.XMAS02_FI


# --- the mixed cache ----------------------------------------------------------------------------


def test_the_mixed_cache_dry_run_equals_the_build(
    bfc: ModuleType, world: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """The positive case of T-I3: the linked part is the 720 TRAIN (p38 + xw2) under ITS params
    (aea6f1d2's stand-in), never re-labelled; the new part the 1080 TRAIN + its FIT as VAL under
    the 1080 params; both parts' counts in the dry run equal the written ones; the linked VAL
    (p31) is left out; the trainer's reader sees both parts' frames."""
    r5 = world["out"] / R5
    before = {p.name: sha(p) for p in sorted(r5.iterdir())}
    r5_man = json.loads((r5 / "manifest.json").read_text())
    plan = dry(bfc, capsys, mixed(world))
    parts = plan["parts"]
    assert parts["new"]["params_sha256"] == sha(world["p1080"])
    assert parts["linked"]["params_sha256"] == sha(world["p720"])
    assert (parts["new"]["train"], parts["new"]["val"]) == ([IFT1, IFT2], [IFF])
    assert (parts["linked"]["train"], parts["linked"]["val"]) == ([P38, XW2], [])
    assert parts["linked"]["val_not_linked"] == [P31]
    # the new part: 18 + 16 item frames, 2 labels each, 1 negative per 3 item frames (6 + 5)
    assert parts["new"]["train_counts"] == {"sessions": 2, "frames": 45, "item_frames": 34,
                                            "labels": 68, "negatives": 11}  # fmt: skip
    assert parts["new"]["val_counts"] == {"sessions": 1, "frames": 12, "item_frames": 9,
                                          "labels": 18, "negatives": 3}  # fmt: skip
    # the linked part: r5's own rows (p38: 33 item frames + 11 negatives; xw2: 30 negatives)
    old = {"sessions": 2, "item_frames": 33, "labels": 66, "negatives": 41, "frames": 74}
    assert parts["linked"]["train_counts"] == old
    assert sum(r5_man["sessions"][s]["kept"] for s in (P38, XW2)) == 74
    assert plan["train_combined"] == {"sessions": 4, "frames": 119, "item_frames": 67,
                                      "labels": 134, "negatives": 52}  # fmt: skip
    assert plan["linked"]["manifest_sha256"] == before["manifest.json"]
    assert plan["inputs"]["params_sha256"] == sha(world["p1080"])
    assert plan["would_refuse_join"] == [] and plan["train_total"]["kept"] == 45
    assert not (world["out"] / "mix").exists()  # a dry run writes nothing

    assert bfc.main([*mixed(world), "--cache-id", "mix"]) == 0
    done = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert (done["frames"], done["frames_written"]) == (119 + 12, 45 + 12)
    man = json.loads((world["out"] / "mix" / "manifest.json").read_text())
    assert man["parts"] == plan["parts"]  # the written counts = the dry run's
    assert man["split"] == {"train": [IFT1, IFT2, P38, XW2], "val": [IFF], "test": []}
    assert json.loads((world["out"] / "mix" / "split.json").read_text()) == man["split"]
    assert P31 not in man["sessions"]
    assert man["fi_labels"]["params_sha256"] == sha(world["p1080"])
    assert man["linked"]["params_sha256"] == sha(world["p720"])
    for sid in (P38, XW2):
        row = man["sessions"][sid]
        assert row["linked_from"] == R5 and row["item_params_sha256"] == sha(world["p720"])
        assert row["shards"] == [f"../{R5}/{s}" for s in r5_man["sessions"][sid]["shards"]]
        assert row["kept"] == r5_man["sessions"][sid]["kept"]
    for sid in (IFT1, IFT2, IFF):
        row = man["sessions"][sid]
        assert "linked_from" not in row and row["item_params_sha256"] == sha(world["p1080"])
        assert row["kept"] == plan["sessions"][sid]["kept"]
        assert all(not s.startswith("../") for s in row["shards"])
    prog = json.loads((world["out"] / "mix" / "progress.json").read_text())
    assert prog["args"]["link"]["cache_id"] == R5
    # the linked cache is untouched: nothing added, nothing rewritten
    assert {p.name: sha(p) for p in sorted(r5.iterdir())} == before
    shards = load("poring_vision_shards_fi_link",
                  ROOT / "services/vision/src/poring_vision/shards.py")  # fmt: skip
    train, names = shards.load_split(world["out"] / "mix", "train")
    assert names == {0: "floor_item"} and len(train) == 119
    by: dict[str, int] = {}
    for s in train:
        by[s.session] = by.get(s.session, 0) + 1
    assert by == {IFT1: 24, IFT2: 21, P38: 44, XW2: 30}
    val, _ = shards.load_split(world["out"] / "mix", "val")
    assert {s.session for s in val} == {IFF} and len(val) == 12
    p38 = next(s for s in train if s.session == P38 and s.labels.size)
    assert p38.labels[:, 0].tolist() == [0.0, 0.0] and len(shards.read_image(p38)) == p38.size


def test_an_unlinked_build_keeps_its_keys(bfc: ModuleType, world: dict[str, Any],
                                          capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    """Without --link-cache nothing new is written (the 720 cache's manifest, rows and progress
    file keep their keys): r5 itself was built by today's path."""
    man = json.loads((world["out"] / R5 / "manifest.json").read_text())
    assert "parts" not in man and "linked" not in man
    assert all("item_params_sha256" not in r and "linked_from" not in r
               for r in man["sessions"].values())  # fmt: skip
    assert "link" not in json.loads((world["out"] / R5 / "progress.json").read_text())["args"]
    plan = dry(bfc, capsys, items_argv(world["p1080"], [world["f1080"][s] for s in (IFT1, IFF)],
                                       world, "--train", IFT1, "--val", IFF))  # fmt: skip
    assert "parts" not in plan and "train_combined" not in plan
    assert "item_params_sha256" not in plan["sessions"][IFT1]


def test_the_one_sha_rule_holds_per_part(bfc: ModuleType, world: dict[str, Any]) -> None:
    """The new part's label files are checked against --item-params only: a 720-labelled file in
    the new part is refused even though the linked part is 720 (its own params live in its
    manifest), and the 1080 params cannot claim the linked part's files."""
    w = world
    refs = recorder_session(w["datasets"], "20261121T020000-rdp-xmas02-ifT3", 40, virtual=True)
    stray = label_file(w["tmp"], w["p720"], "20261121T020000-rdp-xmas02-ifT3", "train", refs,
                       16, 6)  # fmt: skip
    files = [w["f1080"][s] for s in (IFT1, IFT2, IFF)] + [stray]
    with pytest.raises(SystemExit, match="other parameters"):
        bfc.main([*items_argv(w["p1080"], files, w, "--train", IFT1, IFT2,
                              "20261121T020000-rdp-xmas02-ifT3", "--val", IFF, "--link-cache", R5),
                  "--dry-run"])  # fmt: skip
    with pytest.raises(SystemExit, match="other parameters"):  # the 720 file under the 1080 pin
        bfc.main([*mixed(w, files=[w["f1080"][IFT1], w["f1080"][IFT2], w["f720"][P31]]),
                  "--dry-run"])  # fmt: skip


def test_val_is_the_new_parts_fit_only(bfc: ModuleType, world: dict[str, Any],
                                       capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    """--val takes the new part's FIT label file (--split val, the 1080 rule's FIT) only; the
    linked cache's VAL never joins; a new session may not be one the linked cache holds."""
    w = world
    with pytest.raises(SystemExit, match="FIT label file"):  # a TRAIN file as VAL
        bfc.main([*items_argv(w["p1080"], [w["f1080"][s] for s in (IFT1, IFT2, IFF)], w,
                              "--train", IFT2, IFF, "--val", IFT1, "--link-cache", R5),
                  "--dry-run"])  # fmt: skip
    other = "20261121T030000-rdp-xmas02-ifX"
    refs = recorder_session(w["datasets"], other, 20, virtual=True)
    bad_val = label_file(w["tmp"], w["p1080"], other, "val", refs, 9, 4)
    with pytest.raises(SystemExit, match="FIT only"):  # VAL is the 1080 rule's FIT (ifF) only
        bfc.main([*items_argv(w["p1080"], [w["f1080"][IFT1], bad_val], w, "--train", IFT1,
                              "--val", other, "--link-cache", R5), "--dry-run"])  # fmt: skip
    refs = recorder_session(w["tmp"] / "nas2", P38, 60)
    again = label_file(w["tmp"], w["p1080"], P38, "train", refs, 33, 8)
    with pytest.raises(SystemExit, match="ONE part"):  # p38 is in the linked cache already
        bfc.main([*items_argv(w["p1080"], [again, w["f1080"][IFF]], w, "--train", P38, "--val",
                              IFF, "--link-cache", R5), "--dry-run"])  # fmt: skip
    plan = dry(bfc, capsys, items_argv(w["p1080"], [w["f1080"][s] for s in (IFT1, IFT2)], w,
                                       "--train", IFT1, IFT2, "--link-cache", R5))  # fmt: skip
    assert plan["parts"]["new"]["val"] == [] and plan["parts"]["linked"]["val"] == []


def test_both_rules_keep_their_held_outs_out_of_train(bfc: ModuleType, world: dict[str, Any],
                                                      spec1080: Any) -> None:  # fmt: skip
    """Each TRAIN session of either part passes EVERY floor-item rule of the map as TRAIN by name:
    the 720 FIT (p31) named as a new 1080 TRAIN session is refused by the 720 rule, though the
    1080 rule alone would take it; a linked TRAIN row named as a 1080 held-out by the 1080 rule.
    (The 720 held-outs fiH1 / fiH2 / fsH1 are refused by both: the map's own TEST names them.)"""
    fit720 = "20261121T040000-rdp-hunt-xmas02-p31"
    assert fl.role_refusal(spec1080, fit720, "train", False) is None
    assert fl.role_refusal(spec1080, "x-rdp-hunt-xmas02-fiH2", "train", False) is not None
    specs = bfc.item_specs(fl, "xmas_dun02")
    got = bfc.train_role_refusals(fl, specs, [IFT1, P38, XW2, fit720, "x-rdp-hunt-xmas02-fiH2",
                                              "y-rdp-xmas02-ifH1", "z-rdp-xmas02-ifF"])  # fmt: skip
    assert sorted(got) == [fit720, "x-rdp-hunt-xmas02-fiH2", "y-rdp-xmas02-ifH1",
                           "z-rdp-xmas02-ifF"]  # fmt: skip
    assert got[fit720].startswith("xmas02-fi-1 (d4cc0a5d...): FIT (p31) is VAL only")
    assert got["x-rdp-hunt-xmas02-fiH2"].startswith("xmas02-fi-1 (d4cc0a5d...)")
    assert got["y-rdp-xmas02-ifH1"].startswith("xmas02-fi-1 (9c73278f...)")
    w = world
    refs = recorder_session(w["datasets"], fit720, 40, virtual=True)
    f = label_file(w["tmp"], w["p1080"], fit720, "train", refs, 16, 6)
    with pytest.raises(SystemExit, match="refused by name.*p31.*VAL only"):
        bfc.main([*items_argv(w["p1080"], [f, w["f1080"][IFF]], w, "--train", fit720, "--val",
                              IFF, "--link-cache", R5), "--dry-run"])  # fmt: skip
    r5 = w["out"] / R5
    man = json.loads((r5 / "manifest.json").read_text())
    ren = "20261121T050000-rdp-xmas02-ifH1"
    man["sessions"][ren] = man["sessions"].pop(XW2)
    man["split"]["train"] = [P38, ren]
    (r5 / "manifest.json").write_text(json.dumps(man))
    with pytest.raises(SystemExit, match="refused by name.*ifH1"):
        bfc.main([*mixed(w), "--dry-run"])


def copy_r5(w: dict[str, Any], name: str, edit: Any = None) -> str:
    """A copy of the linked cache under another id, its manifest edited by ``edit(manifest)``."""
    d = w["out"] / name
    shutil.copytree(w["out"] / R5, d)
    if edit is not None:
        man = json.loads((d / "manifest.json").read_text())
        edit(man)
        (d / "manifest.json").write_text(json.dumps(man))
    return name


def test_the_link_gates(bfc: ModuleType, world: dict[str, Any],
                        capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    """Refused: a missing or unreadable manifest, not an items cache, other class names or another
    class list, no item params sha256, another map or rule, a mixed cache, a TEST, a TRAIN row
    the join rule did not admit, a linked shard changed on the NAS, a path for an id. The
    positive case first: an unedited copy links."""
    w = world
    base = items_argv(w["p1080"], [w["f1080"][s] for s in (IFT1, IFT2, IFF)], w, "--train", IFT1,
                      IFT2, "--val", IFF, "--dry-run")  # fmt: skip
    assert bfc.main([*base, "--link-cache", copy_r5(w, "ok")]) == 0
    capsys.readouterr()

    def refused(link: str, match: str) -> None:
        with pytest.raises(SystemExit, match=match):
            bfc.main([*base, "--link-cache", link])

    refused("absent", "not found")
    (w["out"] / copy_r5(w, "garbled") / "manifest.json").write_text("{not json")
    refused("garbled", "unreadable")
    refused(copy_r5(w, "maplike", lambda m: m.update(labels="map")), "not an items cache")
    refused(copy_r5(w, "names", lambda m: m.update(names={"0": "item"})), "class names")
    refused(copy_r5(w, "names2", lambda m: m["names"].update({"1": "player"})), "class names")
    refused(copy_r5(w, "clist", lambda m: m.update(class_list_sha256="0" * 64)),
            "another class list")  # fmt: skip
    refused(copy_r5(w, "nosha", lambda m: m["fi_labels"].pop("params_sha256")), "no item params")
    refused(copy_r5(w, "nofi", lambda m: m.pop("fi_labels")), "no item params")
    refused(copy_r5(w, "othermap", lambda m: m["fi_labels"].update(map="prt_fild08")),
            "not a floor-item rule")  # fmt: skip
    refused(copy_r5(w, "otherrule", lambda m: m["fi_labels"].update(rule="xmas02-fi-0")),
            "not a floor-item rule")  # fmt: skip
    refused(copy_r5(w, "mix", lambda m: m.update(linked={"cache_id": "older"})), "mixed cache")
    refused(copy_r5(w, "mixrow", lambda m: m["sessions"][P38].update(linked_from="older")),
            "mixed cache")  # fmt: skip
    refused(copy_r5(w, "test", lambda m: m["split"].update(test=[P31])), "no TEST")
    refused(copy_r5(w, "g2fail", lambda m: m["sessions"][P38].update(join_rule="G2_FAIL")),
            "not an admitted")  # fmt: skip
    refused(copy_r5(w, "norow", lambda m: m["split"]["train"].append("x-rdp-xmas02-ghost")),
            "without a TRAIN row")  # fmt: skip
    grown = copy_r5(w, "grown")
    with (w["out"] / grown / "shard-000000.tar").open("ab") as fh:
        fh.write(b"x")
    refused(grown, "recorded")
    refused(f"../{R5}", "a cache id")
    with pytest.raises(SystemExit, match="does not belong"):  # the other label modes' flags
        bfc.main([*base, "--link-cache", R5, "--map-labels", str(w["f1080"][IFT1])])


def test_the_class_list_must_be_the_linked_caches(bfc: ModuleType, world: dict[str, Any]) -> None:
    """--class-list names floor_item but is another file than the one r5 was built with (its
    sha256): refused."""
    w = world
    other = write(w["tmp"] / "classes.json", {"names": ["floor_item"], "scheme": "other"})
    args = mixed(w, "--dry-run")
    args[args.index(str(CLASSES))] = str(other)
    with pytest.raises(SystemExit, match="another class list"):
        bfc.main(args)


# --- the frame size at 1080 ---------------------------------------------------------------------


def test_a_virtual_1080_session_passes_the_frame_check(
    bfc: ModuleType, world: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """At 1080 the recorder writes the VIRTUAL 1280 x 720 picture (recorder v8 + client_view):
    the labels' size (V2_SIZE) holds, unchanged. The positive case of the check: a session whose
    PNG frames are the real 1920 x 1080 is refused at the first frame."""
    w = world
    assert bfc.V2_SIZE == (1280, 720)
    man = json.loads((w["datasets"] / IFT1 / "manifest.json").read_text())
    assert rec_paths.path_of(man) == "virtual-1080"
    assert man["client_view"]["rect"] == [0, 0, 1920, 1080]
    assert bfc.main(items_argv(w["p1080"], [w["f1080"][s] for s in (IFT1, IFF)], w, "--train",
                               IFT1, "--val", IFF, "--cache-id", "v1080")) == 0  # fmt: skip
    capsys.readouterr()
    written = json.loads((w["out"] / "v1080" / "manifest.json").read_text())
    assert written["sessions"][IFT1]["kept"] == 24
    big = "20261121T060000-rdp-xmas02-ifT9"
    refs = recorder_session(w["datasets"], big, 40, virtual=True, size=(1920, 1080))
    f = label_file(w["tmp"], w["p1080"], big, "train", refs, 16, 6)
    with pytest.raises(SystemExit, match="1920x1080, the labels are 1280x720"):
        bfc.main(items_argv(w["p1080"], [f], w, "--train", big, "--cache-id", "big"))


# --- the guarded cache step ---------------------------------------------------------------------


def test_the_guarded_cache_step_passes_the_link(
    bfc: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """guarded_build's cache: step takes the round's arguments as plain tokens (no '=' inside
    one; absolute inputs below /dev/shm/poring-lab-tmp only) and hands them to the builder
    unchanged; the builder's parser reads --link-cache / --val / --session-negs from them."""
    gb = load("guarded_build_fi_link", SCRIPTS / "guarded_build.py")
    args = ["--labels", "items", "--item-params", f"{SHM}/i1080/items-params-1080.json",
            "--item-params-sha256", M1080, "--fi-labels", f"{SHM}/i1080/labels/{IFT1}.json",
            f"{SHM}/i1080/labels/{IFT2}.json", f"{SHM}/i1080/labels/{IFF}.json",
            "--class-list", "config/detector/classes-xmas02-fi.json", "--train", IFT1, IFT2,
            "--val", IFF, "--link-cache", "xmas02-fi-r5-20261112", "--session-negs", "ifT1",
            "ifT2", "--session-negs-n", "150", "--image", "png", "--cache-id",
            "xmas02-fi-1080-mix-20261121", "--dry-run"]  # fmt: skip
    step = gb.parse_step("cache@7200=" + " ".join(args))
    assert step.kind == "cache" and step.seconds == 7200.0
    assert gb.cache_cmd(step)[5:] == [str(gb.CACHE_PY), "scripts/build_frame_cache.py", *args]
    seen: list[Any] = []
    monkeypatch.setattr(bfc, "items_main", lambda a: seen.append(a) or 0)
    assert bfc.main(step.command) == 0
    a = seen[0]
    assert (a.link_cache, a.val, a.train) == ("xmas02-fi-r5-20261112", [IFF], [IFT1, IFT2])
    assert a.session_negs == ["ifT1", "ifT2"] and a.item_params_sha256 == M1080
    for bad in ("--item-params /home/bot/p.json", f"--fi-labels {SHM}/../../etc/x.json",
                "--link-cache r5;id"):  # fmt: skip
        with pytest.raises(ValueError):
            gb.parse_step(f"cache@7200=--labels items {bad}")
