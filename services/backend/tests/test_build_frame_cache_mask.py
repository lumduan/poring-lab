"""scripts/build_frame_cache.py --labels map --mask-sessions (docs/planning/xmas02-detector.md
Amendment S4, 2026-11-14: the Christmas Goblin class): the MASKED rule. Excluded and weak_fit
labels become grey masks (their sprite envelope, grown, never over a written box) instead of
dropping the frame; a kept box holding a masked unit's centre, or under a mask left mostly
unpainted, is demoted; a mask on our own box drops the frame; the frame rules, the written PNG,
the frame json and the session's counts; map_labels.label_regions' plumbing.

Synthetic sessions, label files and sprites only (generated pictures, ids and made-up boxes): no
client pixels, no rAthena data."""

from __future__ import annotations

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_build_frame_cache_map import (  # noqa: E402
    PAYF07_LIST,
    SELF,
    SID,
    argv,
    check_doc,
    fake_lab,
    frame,
    inputs,
    kept,
    label_doc,
    params_file,
    picture,
    recorder_session,
    write,
)

SIZE = (1280, 720)
R = {1033: 10.0, 1010: 10.0, 1116: 10.0}  # the fit radius + MASK_PAD_PX


@pytest.fixture(scope="module")
def bfc() -> ModuleType:
    from test_build_frame_cache_map import load

    path = Path(__file__).resolve().parents[3] / "scripts" / "build_frame_cache.py"
    return load("build_frame_cache_mask_under_test", path)


@pytest.fixture(scope="module")
def ml() -> ModuleType:
    import map_labels

    return map_labels


# --- the masked frame rule --------------------------------------------------------------------


def test_masked_rule_masks_labels_and_keeps_frame_drops(bfc: ModuleType) -> None:
    idx = bfc.SpeciesClasses.load(PAYF07_LIST).index
    f = frame(1, [kept(1, 1033, 100.0), kept(2, 1010, 300.0, 0.30), kept(3, 1116, 500.0, 0.2,
                                                                          under=True)],
              [[9, 1033, "crowd"], [8, 1010, "next_move"]])  # fmt: skip
    train, masks, why = bfc.map_frame_masked(f, 0.479, idx)
    assert why == []
    assert train == [
        (15, 1033, [100.0, 300.0, 140.0, 360.0], 1),
        (17, 1116, [500.0, 300.0, 540.0, 360.0], 3),
    ]  # under a model: o3h judged it
    assert masks == [(9, 1033, "crowd", None), (8, 1010, "next_move", None),
                     (2, 1010, "weak_fit", [300.0, 300.0, 340.0, 360.0])]  # fmt: skip
    # the frame rules still drop the frame: 4g, a species without a class, the label pass's drop
    assert bfc.map_frame_masked(frame(2, [kept(1, 1033, 100.0)], None, ["warp_in_view"]),
                                0.479, idx)[2] == ["warp_in_view"]  # fmt: skip
    assert bfc.map_frame_masked(frame(3, [], [[4, 1099, "unfit"]]), 0.479, idx)[2] == \
        ["species_unlisted:1099"]  # fmt: skip
    dropped = {"frame_id": 4, "excluded_frame": ["no_scene"], "whole": False}
    assert bfc.map_frame_masked(dropped, 0.479, idx) == ([], [], ["no_scene"])
    liar = {**frame(5, [kept(1, 1033, 100.0)], [[2, 1010, "unfit"]]), "whole": True}
    with pytest.raises(SystemExit):
        bfc.map_frame_masked(liar, 0.479, idx)
    # a whole frame: no mask, the same boxes as the whole-frame rule
    whole = frame(6, [kept(1, 1033, 100.0)])
    assert bfc.map_frame_masked(whole, 0.479, idx)[:2] == \
        ([(15, 1033, [100.0, 300.0, 140.0, 360.0], 1)], [])  # fmt: skip
    assert bfc.map_frame(whole, 0.479, idx) == ([(15, 1033, [100.0, 300.0, 140.0, 360.0])], [])


def test_geometry_helpers(bfc: ModuleType) -> None:
    assert bfc.grown((10, 10, 20, 20), 5, SIZE) == (5.0, 5.0, 25.0, 25.0)
    assert bfc.grown((-30, 700, 5, 800), 2, SIZE) == (0.0, 698.0, 7.0, 720.0)
    assert bfc.grown((-30, -30, -20, -20), 2, SIZE) is None
    assert bfc.touches((0, 0, 10, 10), (5, 5, 20, 20))
    assert not bfc.touches((0, 0, 10, 10), (10, 0, 20, 10))  # an edge is not an area
    assert bfc.contains((0, 0, 10, 10), (1, 1, 9, 9)) and not bfc.contains(
        (0, 0, 10, 10), (1, 1, 11, 9)
    )
    assert bfc.contains((0, 0, 10, 10), (1, 1, 11, 9), slack=1.0)
    assert bfc.overshoot((0, 0, 10, 10), (-3, 2, 12, 9)) == 3.0
    assert bfc.overshoot((0, 0, 10, 10), (1, 1, 9, 9)) == 0.0
    assert bfc.inside((5, 5), (0, 0, 10, 10)) and not bfc.inside((10, 5), (0, 0, 10, 10))


def train_box(gid: int, mob: int, x0: float, y0: float = 300.0, w: float = 40.0,
              h: float = 60.0) -> tuple[int, int, list[float], int]:  # fmt: skip
    return (15, mob, [x0, y0, x0 + w, y0 + h], gid)


OWN = (620.0, 290.0, 654.0, 364.0)


def test_resolve_paints_around_written_boxes(bfc: ModuleType) -> None:
    """A mask next to a kept box: painted, the kept box untouched (kept), nothing demoted."""
    t = [train_box(1, 1033, 100.0)]
    masks = [(9, 1033, "crowd", None)]
    regions = {9: (150.0, 300.0, 190.0, 360.0)}  # centre (170, 330): outside the kept box
    res = bfc.resolve_masks(t, masks, regions, OWN, R, SIZE)
    assert res.why is None and res.train == t
    assert res.paint == [(1033, "crowd", (140.0, 290.0, 200.0, 370.0))]
    assert res.keep == [OWN, (100.0, 300.0, 140.0, 360.0)]
    img = np.full((720, 1280, 3), 7, np.uint8)
    out = bfc.paint_masks(img, [r for _m, _w, r in res.paint], res.keep)
    assert (out[290:370, 140:200] == bfc.MASK_FILL).all()  # the region (outside the kept box)
    assert (out[300:360, 100:140] == 7).all()  # the kept box keeps every pixel
    assert (img == 7).all()  # a copy
    assert bfc.mask_area([r for _m, _w, r in res.paint], res.keep, SIZE) == \
        pytest.approx(60 * 80 / (1280 * 720))  # fmt: skip


def test_resolve_demotes_a_box_holding_a_masked_centre(bfc: ModuleType) -> None:
    """The masked unit's centre inside a kept box: the kept box is demoted (masked too), and the
    demotion cascades by the demoted box's own centre."""
    a, b = train_box(1, 1033, 100.0), train_box(2, 1010, 110.0, w=60.0)  # b holds a's centre
    c = train_box(3, 1116, 600.0, y0=100.0)  # far away: stays
    masks = [(9, 1033, "crowd", None)]
    regions = {9: (95.0, 310.0, 125.0, 350.0)}  # centre (110, 330): inside a, on b's edge
    res = bfc.resolve_masks([a, b, c], masks, regions, OWN, R, SIZE)
    assert res.why is None and res.train == [c]
    assert [(m, w) for m, w, _r in res.paint] == [(1033, "crowd"), (1033, bfc.DEMOTED),
                                                  (1010, bfc.DEMOTED)]  # fmt: skip
    assert res.keep == [OWN, (600.0, 100.0, 640.0, 160.0)]


def test_resolve_demotes_boxes_under_a_mask_left_mostly_unpainted(bfc: ModuleType) -> None:
    """A mask whose region lies more than MAX_EXPOSED inside written boxes, its centre inside
    none of them (two boxes side by side, the centre on their shared edge): every kept box
    touching it is demoted."""
    zero = {1033: 0.0, 1010: 0.0, 1116: 0.0}
    a, b = train_box(1, 1033, 100.0, h=100.0), train_box(2, 1116, 140.0, h=100.0)
    far = train_box(3, 1033, 900.0)
    masks = [(9, 1010, "occluded_model", None)]
    regions = {9: (120.0, 290.0, 160.0, 330.0)}  # centre (140, 310): on a's / b's shared edge
    keep = [OWN, (100.0, 300.0, 140.0, 400.0), (140.0, 300.0, 180.0, 400.0)]
    assert bfc.exposure(regions[9], keep, SIZE) == pytest.approx(0.75)
    res = bfc.resolve_masks([a, b, far], masks, regions, OWN, zero, SIZE)
    assert res.why is None and res.train == [far]
    assert [(m, w) for m, w, _r in res.paint] == [(1010, "occluded_model"), (1033, bfc.DEMOTED),
                                                  (1116, bfc.DEMOTED)]  # fmt: skip
    half = {9: (120.0, 300.0, 160.0, 330.0)}  # only a (left half): exactly MAX_EXPOSED, kept
    one = bfc.resolve_masks([a, far], masks, half, OWN, zero, SIZE)
    assert one.why is None and one.train == [a, far]


def test_resolve_never_masks_our_own_box(bfc: ModuleType) -> None:
    centre_on_us = {9: (625.0, 300.0, 649.0, 350.0)}
    res = bfc.resolve_masks([], [(9, 1033, "crowd", None)], centre_on_us, OWN, R, SIZE)
    assert res.why == "mask_on_self:1033"
    beside_us = {9: (654.0, 300.0, 700.0, 350.0)}  # centre outside; the grown region overlaps us
    ok = bfc.resolve_masks([], [(9, 1033, "crowd", None)], beside_us, OWN, R, SIZE)
    assert ok.why is None and ok.keep == [OWN]
    img = bfc.paint_masks(np.zeros((720, 1280, 3), np.uint8), [ok.paint[0][2]], ok.keep)
    assert (img[290:364, 620:654] == 0).all() and (img[300:350, 660:700] == bfc.MASK_FILL).all()
    # a region mostly on our own box (its centre outside it): nothing to demote -> dropped
    mostly = {9: (612.0, 286.0, 640.0, 366.0)}  # centre (626, 326) IS inside: the centre rule
    assert bfc.resolve_masks([], [(9, 1010, "unfit", None)], mostly, OWN, R,
                             SIZE).why == "mask_on_self:1010"  # fmt: skip
    edge = {9: (600.0, 300.0, 640.0, 340.0)}  # centre (620, 320): on our left edge, not inside
    res = bfc.resolve_masks([], [(9, 1010, "unfit", None)], edge, OWN, {1010: 0.0}, SIZE)
    assert res.why is None  # half of it on us: exactly MAX_EXPOSED, not over it


def test_resolve_fails_closed_without_a_region(bfc: ModuleType) -> None:
    res = bfc.resolve_masks([train_box(1, 1033, 100.0)], [(9, 1116, "unfit", None)], {9: None},
                            OWN, R, SIZE)  # fmt: skip
    assert res.why == "mask_unknown:1116"


def test_resolve_weak_fit_uses_its_fitted_box(bfc: ModuleType) -> None:
    """A weak_fit mask: its region = envelope + fitted box, its centre the fitted box's."""
    masks = [(2, 1010, "weak_fit", [300.0, 300.0, 340.0, 360.0])]
    regions = {2: (310.0, 290.0, 330.0, 350.0)}
    res = bfc.resolve_masks([], masks, regions, OWN, R, SIZE)
    assert res.paint == [(1010, "weak_fit", (290.0, 280.0, 350.0, 370.0))]


# --- map_labels.label_regions (the plumbing; the geometry is render's, tested there) ------------


def test_label_regions_unions_headings_and_groups(
    ml: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    import poring_dataset.render as render

    ent = {
        5: SimpleNamespace(gid=5, job=1033, objtype=5, hidden=False, x=10.0, y=20.0),
        6: SimpleNamespace(gid=6, job=1033, objtype=5, hidden=True, x=0.0, y=0.0),  # hidden
        7: SimpleNamespace(gid=7, job=9999, objtype=5, hidden=False, x=0.0, y=0.0),  # no sheet
        8: SimpleNamespace(gid=8, job=1033, objtype=1, hidden=False, x=0.0, y=0.0),  # not a mob
    }
    states = [SimpleNamespace(gid=g, state="attacking" if g == 5 else "idle") for g in ent]
    world = SimpleNamespace(self_pos=(10.0, 10.0), map="xmas_dun02", entities=list(ent.values()))
    seen: list[int] = []

    def at_world(tw: int) -> tuple[Any, Any, Any, Any]:
        seen.append(tw)
        return None, world, states, {}

    lab = SimpleNamespace(timeline=SimpleNamespace(at_world=at_world),
                          sheets=lambda job: object() if job == 1033 else None)  # fmt: skip
    monkeypatch.setattr(ml.occ, "scene_for", lambda lab, m, pos: "scene")

    def predict_sprite(actor: Any, sheet: Any, scene: Any, k: float) -> Any:
        assert actor.action == 0 and scene == "scene"
        return SimpleNamespace(heading=actor.heading, anchor_px=(100.0, 200.0),
                               box=(0, 0, 1, 1))  # fmt: skip

    monkeypatch.setattr(render, "predict_sprite", predict_sprite)
    calls: list[tuple[int, int]] = []

    def envelope(sheet: Any, pred: Any, group: int) -> Any:
        calls.append((pred.heading, group))
        if group == 1 and pred.heading == 3:
            return None  # draws nothing
        x0 = 90.0 - pred.heading - (10.0 if group == 2 else 0.0)
        return SimpleNamespace(box=(x0, 150.0, 110.0 + pred.heading, 200.0 + group))

    monkeypatch.setattr(ml, "envelope", envelope)
    params = {"offset_ms": 100.0, "anchors_px": {}}
    out = ml.label_regions(lab, params, 1_000_000_000, [5, 6, 7, 8, 42])
    assert seen == [900_000_000]  # the labeller's tw = t - offset
    assert out == {5: (73.0, 150.0, 117.0, 202.0), 6: None, 7: None, 8: None, 42: None}
    assert sorted(calls) == sorted((h, g) for h in range(8) for g in (0, 1, 2))  # + its state's
    nobody = SimpleNamespace(self_pos=None, map="", entities=[])
    lab.timeline = SimpleNamespace(at_world=lambda tw: (None, nobody, [], {}))
    assert ml.label_regions(lab, params, 0, [5]) == {5: None}


# --- the session: dry run, build, frame json ----------------------------------------------------


def masked_frames(refs: list[tuple[str, int, int]]) -> list[dict[str, Any]]:
    fs = [
        frame(1, [kept(1, 1033, 100.0)], [[9, 1010, "crowd"]]),  # a mask beside a kept box
        frame(2, [kept(1, 1033, 100.0)], [[9, 1010, "crowd"]]),  # the mask on our own box
        frame(3, [kept(1, 1033, 100.0)], None, ["warp_in_view"]),  # 4g: still dropped
        frame(4, [kept(1, 1033, 100.0), kept(2, 1010, 1000.0, 0.3)]),  # weak_fit: a mask
    ]
    for f, (shard, off, size) in zip(fs, refs, strict=True):
        f.update(shard=shard, offset=off, size=size)
    return fs


REGIONS = {  # frame t -> gid -> envelope (the stand-in for label_regions)
    1_000_000_000: {1: (100.0, 300.0, 140.0, 360.0), 9: (300.0, 400.0, 340.0, 460.0)},
    2_000_000_000: {1: (100.0, 300.0, 140.0, 360.0), 9: (615.0, 300.0, 655.0, 350.0)},
    4_000_000_000: {1: (98.0, 296.0, 150.0, 362.0), 2: (995.0, 290.0, 1045.0, 365.0)},
}


@pytest.fixture()
def mworld(bfc: ModuleType, ml: ModuleType, tmp_path: Path,
           monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:  # fmt: skip
    datasets = tmp_path / "datasets"
    refs = recorder_session(datasets, SID, 4)
    p = params_file(tmp_path)
    lab = label_doc(tmp_path, p, SID, masked_frames(refs))
    chk = check_doc(tmp_path, p, {SID: "ADDED"})
    kb = write(tmp_path / "kb" / "classes.json",
               {"m": {str(j): {"aegis": f"M{j}"} for j in
                      json.loads(PAYF07_LIST.read_text())["monsters"]}})  # fmt: skip
    monkeypatch.setattr(bfc, "self_box", lambda lab, spec, tw, dead: (SELF, None))
    monkeypatch.setattr(ml, "session_labeler", lambda path, spec: fake_lab())
    monkeypatch.setattr(
        ml, "label_regions", lambda lab, params, t, gids: {g: REGIONS[t].get(g) for g in gids}
    )
    return {"datasets": datasets, "params": p, "labels": lab, "check": chk, "kb": kb.parent,
            "out": tmp_path / "out"}  # fmt: skip


def opts(w: dict[str, Any], masked: bool = True) -> SimpleNamespace:
    return SimpleNamespace(datasets=w["datasets"], image="png", quality=95, max_per_session=None,
                           shard_mb=512, mask_sessions=[SID] if masked else [])  # fmt: skip


def test_masked_session_writes_painted_frames(bfc: ModuleType, mworld: dict[str, Any]) -> None:
    classes = bfc.SpeciesClasses.load(PAYF07_LIST)
    mli = bfc.MapLabelInputs.from_args(inputs(mworld["params"], [mworld["labels"]],
                                              [mworld["check"]]))  # fmt: skip
    whole = bfc.map_session(SID, "train", opts(mworld, masked=False), None, classes, mli)
    assert (whole["kept"], whole["labels"]) == (0, "payf07-o3h-all") and "mask" not in whole
    with pytest.raises(SystemExit, match="TRAIN"):
        bfc.map_session(SID, "val", opts(mworld), None, classes, mli)
    dry = bfc.map_session(SID, "train", opts(mworld), None, classes, mli)
    assert (dry["seen"], dry["kept"], dry["labels"]) == (4, 2, "payf07-o3h-all-mask")
    assert dry["excluded"] == {"mask_on_self": 1, "warp_in_view": 1}
    assert dry["boxes_by_class_id"] == {"0": 2, "15": 2}
    m = dry["mask"]
    assert m["painted"] == {"crowd:1010": 1, "weak_fit:1010": 1} and m["frames_masked"] == 2
    # the positive case: every kept label inside its region (+ its fit radius)
    assert m["mask_check"]["checked:1033"] == 3 and m["mask_check"]["in_radius:1033"] == 3
    assert m["mask_check"]["checked:1010"] == 1 and m["mask_check"]["in_mask:1010"] == 1
    out = mworld["out"]
    out.mkdir()
    sink = bfc.ShardSink(out, 512 << 20)
    row = bfc.map_session(SID, "train", opts(mworld), sink, classes, mli)
    sink.close()
    assert {k: v for k, v in row.items() if k != "shards"} == \
        {k: v for k, v in dry.items() if k != "shards"}  # fmt: skip
    with tarfile.open(out / "shard-000000.tar") as tar:
        got = {mm.name: tar.extractfile(mm).read() for mm in tar}  # type: ignore[union-attr]
    assert sorted(got) == [f"{SID}.{k:09d}.{e}" for k in (1, 4) for e in ("json", "png", "txt")]
    info = json.loads(got[f"{SID}.000000001.json"])
    assert info["labels"] == "payf07-o3h-all-mask" and info["mask_fill"] == bfc.MASK_FILL
    assert info["masked"] == [[1010, "crowd", [290.0, 390.0, 350.0, 470.0]]]
    assert info["boxes"] == [[0, None, "self"], [15, 1033, "fit"]]
    img = np.asarray(Image.open(io.BytesIO(got[f"{SID}.000000001.png"])).convert("RGB"))
    src = np.ascontiguousarray(picture(1)[:, :, ::-1])
    assert (img[390:470, 290:350] == bfc.MASK_FILL).all()
    outside = np.ones((720, 1280), bool)
    outside[390:470, 290:350] = False
    assert np.array_equal(img[outside], src[outside])  # nothing else changed
    four = np.asarray(Image.open(io.BytesIO(got[f"{SID}.000000004.png"])).convert("RGB"))
    assert (four[280:375, 990:1050] == bfc.MASK_FILL).all()  # the weak_fit label, grown
    lines = got[f"{SID}.000000004.txt"].decode().splitlines()
    assert [ln.split()[0] for ln in lines] == ["0", "15"]


def test_mask_sessions_flag_gates(bfc: ModuleType, mworld: dict[str, Any],
                                  capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    base = argv(mworld, "--own-c1", str(mworld["check"]))
    for refused in ([*base, "--dry-run", "--mask-sessions", "other"],
                    [*base, "--dry-run", "--mask-sessions", SID, SID]):  # fmt: skip
        with pytest.raises(SystemExit, match="mask-sessions"):
            bfc.main(refused)
    with pytest.raises(SystemExit, match="belongs to --labels map"):
        bfc.main(["--labels", "v1", "--train", SID, "--mask-sessions", SID])
    assert bfc.main([*base, "--dry-run", "--mask-sessions", SID]) == 0
    printed = capsys.readouterr().out
    dry = json.loads(printed[printed.index("\n{\n") + 1 :])
    assert dry["mask"]["sessions"] == [SID] and dry["mask"]["fill"] == bfc.MASK_FILL
    assert dry["map_sessions"][SID]["labels"] == "payf07-o3h-all-mask"
    assert dry["map_sessions"][SID]["mask"]["painted_total"] == 2
    assert bfc.main([*base, "--mask-sessions", SID, "--cache-id", "new"]) == 0
    man = json.loads((mworld["out"] / "new" / "manifest.json").read_text())
    assert man["mask"]["sessions"] == [SID] and man["mask"]["max_exposed"] == bfc.MAX_EXPOSED
    assert man["sessions"][SID]["mask"]["frames_masked"] == 2
