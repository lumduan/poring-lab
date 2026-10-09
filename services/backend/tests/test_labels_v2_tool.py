"""scripts/labels_v2.py (docs/planning/labels-v2-plan.md): the banked-frame readers, the phantom
logs, the scope / budget over a synthetic KB (ids only, no rAthena data), the cut-in interface,
the aligned crops. Nothing here reads a real session, the KB or a client file."""

from __future__ import annotations

import gzip
import importlib.util
import json
import math
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]


def load() -> ModuleType:
    path = ROOT / "scripts" / "labels_v2.py"
    spec = importlib.util.spec_from_file_location("labels_v2_tool", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["labels_v2_tool"] = mod
    spec.loader.exec_module(mod)
    return mod


L = load()
from poring_dataset import labels_v2 as lv  # noqa: E402
from poring_dataset.camera import Camera  # noqa: E402
from poring_dataset.render import Scene  # noqa: E402
from poring_dataset.timeline import EntityState, FrameWorld  # noqa: E402

# --- banked frames --------------------------------------------------------------------------------


def test_banked_frames_reads_frames_and_referenced_snapshots(tmp_path: Path) -> None:
    (tmp_path / "frames").mkdir()
    for name in ("0001-500.png", "0000-200.png"):
        (tmp_path / "frames" / name).write_bytes(b"")
    recs = [{"frame": {"ref": "snapshots/000-a.png", "t_capture_ns": 300}, "frame_after": None},
            {"frame": {"ref": "snapshots/000-a.png", "t_capture_ns": 300},
             "frame_after": {"ref": "snapshots/001-b.png", "t_capture_ns": 400}},
            {"frame": {"ref": None, "t_capture_ns": None}}]  # fmt: skip
    (tmp_path / "demo.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\n")
    got = [(t, p.name if p else None) for t, p in L.banked_frames(tmp_path)]
    assert got == [(200, "0000-200.png"), (300, "000-a.png"), (400, "001-b.png"),
                   (500, "0001-500.png")]  # fmt: skip


def test_banked_frames_of_a_recorded_session_come_from_its_index(tmp_path: Path) -> None:
    rows = ["au,frame_id,idr,offset,length,t_publish_ns"]
    rows += [f"{i},{i},{int(i % 30 == 0)},{i * 10},10,{1000 + i}" for i in range(40)]
    rows.append("-1,-1,0,0,0,9999")  # a gap row: never a frame
    (tmp_path / "stream.idx.csv").write_text("\n".join(rows) + "\n")
    assert [t for t, p in L.banked_frames(tmp_path, every=15)] == [1000, 1015, 1030]


# --- the phantom logs -----------------------------------------------------------------------------


def test_detections_candidates_take_the_frame_time(tmp_path: Path) -> None:
    rows = [{"t_ns": 2_000_000_000, "ms": 250.0, "boxes": [[10, 20, 50, 60, 0.31, "monster"]]},
            {"t_ns": 3_000_000_000, "ms": 100.0, "boxes": []}]  # fmt: skip
    (tmp_path / "detections.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    (c,) = L.detections_candidates(tmp_path)
    assert (c.t_ns, c.box, c.cls, c.conf, c.source) == (1_750_000_000, (10.0, 20.0, 50.0, 60.0),
                                                        "monster", 0.31, "detections")  # fmt: skip
    assert L.detections_candidates(tmp_path / "none") == []


def test_scene_candidates_convert_the_hud_scene_to_game_px(tmp_path: Path) -> None:
    dw, dh, gx, gy = 1440.0, 900.0, 80.0, 77.0

    def rect(x: float, y: float, w: float, h: float) -> dict[str, float]:
        return {"x": (gx + x) / dw, "y": (gy + y) / dh, "w": w / dw, "h": h / dh}

    zone = {"id": 1, "kind": "zone", "anchor": "screen", "box": rect(0, 0, 1280, 720), "cls": ""}
    unit = {"id": 9, "kind": "unit", "anchor": "world", "box": rect(100, 200, 40, 30),
            "cls": "monster", "conf": 0.3}  # fmt: skip
    msgs = [
        {"type": "hud_scene", "t_mono_ns": 10, "offset": {"x": 0.0, "y": 0.0},
         "objects": [zone, unit]},
        {"type": "hud_motion", "t_mono_ns": 20, "offset": {"x": 10 / dw, "y": -5 / dh}},
        {"type": "hud_delta", "t_mono_ns": 30,
         "move": [{"id": 9, "box": rect(110, 200, 40, 30), "conf": 0.35}], "add": []},
        {"type": "hud_delta", "t_mono_ns": 99, "add": [unit], "move": []},  # after the window
    ]  # fmt: skip
    log = tmp_path / "scene.jsonl"
    log.write_text("\n".join(json.dumps({"logged_ns": m["t_mono_ns"], "msg": m}) for m in msgs)
                   + "\nnot json\n")  # fmt: skip
    got = [(c.t_ns, tuple(round(v, 6) for v in c.box), c.conf)
           for c in L.scene_candidates(log, 0, 50)]  # fmt: skip
    assert got == [
        (10, (100.0, 200.0, 140.0, 230.0), 0.3),
        (30, (120.0, 195.0, 160.0, 225.0), 0.35),
    ]
    assert L.scene_candidates(log, 15, 50)[0].t_ns == 30  # earlier messages set the state only


# --- scope and budget over a synthetic KB ---------------------------------------------------------


def kb(tmp_path: Path) -> Path:
    """iz_dun00 / iz_dun01 as training-cost.md section 5 counts them: 7 species, one static."""
    rows = {"iz_dun00": [(1161, 65), (1141, 45), (1070, 15), (1068, 15), (1066, 15), (1084, 5)],
            "iz_dun01": [(1066, 60), (1070, 50), (1068, 30), (1141, 15), (1067, 15), (1161, 10),
                         (1084, 10)],
            "pay_fild08": [(1002, 30), (1008, 20), (1083, 1)]}  # fmt: skip
    spawns = {m: [{"id": i, "amount": n, "boss": False} for i, n in r] for m, r in rows.items()}
    mobs: dict[str, Any] = {str(i): {"ai": 1, "modes": []} for r in rows.values() for i, _ in r}
    mobs["1084"]["ai"] = None
    mobs["1083"]["ai"] = None
    skills = {"1008": [{"skill": 193, "vals": ["1018", "", "", "", ""]}]}  # metamorphosis
    mobs["1018"] = {"ai": 1, "modes": []}
    for name, doc in (("spawns", spawns), ("mobs", mobs), ("mob_skills", skills)):
        (tmp_path / f"{name}.json").write_text(json.dumps(doc))
    return tmp_path


def test_difficulty_classes() -> None:
    assert L.difficulty({"ai": None, "modes": []}, False) == "static"
    assert L.difficulty({"ai": 21, "modes": ["Mvp"]}, False) == "boss_multi_form"
    assert L.difficulty({"ai": 1, "modes": []}, True) == "boss_multi_form"
    assert L.difficulty({"ai": 10, "modes": []}, False) == "normal"  # immobile, but attacks


def test_scope_carries_metamorphosis_and_the_trained_flag(tmp_path: Path) -> None:
    sc = L.scope(kb(tmp_path), ["pay_fild08", "payon"])
    rows = sc["pay_fild08"]["species"]
    assert set(rows) == {1002, 1008, 1083, 1018}
    assert rows[1002]["trained"] and rows[1018]["via"] == "metamorphosis of 1008"
    assert rows[1083]["difficulty"] == "static" and not rows[1083]["trained"]
    assert sc["payon"] == {"in_kb": False, "species": {}}  # a town: no spawns


def test_budget_reproduces_training_costs_byalan_estimate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert L.main(["--kb", str(kb(tmp_path)), "budget", "--maps", "iz_dun00"]) == 0
    out = json.loads(capsys.readouterr().out)
    (byalan,) = out["blocks"]
    assert byalan["new_maps"] == ["iz_dun00", "iz_dun01"] and byalan["sum_d"] == 6.5
    # training-cost.md section 5 (MW1's estimator): 10.4 / 8.45 / 15.42 / 24.5 night / 30.5 mix
    assert (byalan["map_prep_h"], byalan["collect_s2_h"], byalan["train_compute_h"]) == (
        10.4, 8.45, 15.42)  # fmt: skip
    assert (byalan["wall_h"]["night"], byalan["wall_h"]["mix"]) == (24.5, 30.5)


# --- the cut-in interface, crops, the session helpers ---------------------------------------------


def test_cutin_region_override_module_or_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    assert L.cutin_region("957,249,1183,720") == ((957.0, 249.0, 1183.0, 720.0), True)
    monkeypatch.setitem(sys.modules, "ui_mask", None)  # not on main: the import fails
    assert L.cutin_region(None) == (None, False)
    monkeypatch.setitem(sys.modules, "ui_mask", SimpleNamespace(CUTIN_GUIDE=(1, 2, 3, 4)))
    assert L.cutin_region(None) == ((1.0, 2.0, 3.0, 4.0), True)


def test_aligned_crop_pads_and_masks_with_nan() -> None:
    img = np.arange(100 * 120, dtype=np.float32).reshape(100, 120)
    crop = L.aligned_crop(img, (5.0, 50.0), 1.0, 10, [(0.0, 0.0, 10.0, 45.0)])
    assert crop is not None and crop.shape == (21, 21)  # x -5..15, y 40..60
    assert np.isnan(crop[:, :5]).all()  # x < 0: outside the frame
    assert np.isnan(crop[0:6, 5:16]).all() and np.isfinite(crop[6:, 5:]).all()  # the mask
    assert crop[10, 10] == img[50, 5]
    assert L.aligned_crop(img, (-1.0, 50.0), 1.0, 10, []) is None  # the anchor is off the frame
    half = L.aligned_crop(img, (60.0, 50.0), 0.5, 4, [])
    assert half is not None and half[4, 6] == img[50, 61]  # offset 2 x 0.5 = 1 px


def test_session_dialog_and_contact_lookups() -> None:
    def lab(dialog: bool, menu: bool) -> SimpleNamespace:
        return SimpleNamespace(dialog=dialog, menu=menu)

    dialog = [(0, lab(False, False)), (10, lab(True, False)), (20, lab(False, True)),
              (30, lab(False, False))]  # fmt: skip
    s = SimpleNamespace(dialog=dialog, contacts=[(5, 111), (25, 222)])
    assert [L.Session.dialog_at(s, t) for t in (5, 10, 25, 35)] == [False, True, True, False]
    assert [L.Session.contact_at(s, t) for t in (1, 5, 30)] == [None, 111, 222]


def test_warp_measure_sees_every_confirmed_portal_whatever_the_table() -> None:
    cam = Camera(0.0, math.radians(44.44), 400.0, math.radians(15.0), 640.0, 360.0)
    world = FrameWorld(0, "m.gat", 7, (100.0, 100.0),
                       (EntityState(5, 6, 45, "", 102.0, 103.0, False, 0),))  # fmt: skip
    route = {"warps": {"m": [{"x": 102, "y": 103}]}}
    every = L._AllVisible()
    assert not every and every.get("anything") == "visible"  # empty, yet not "no table"
    r = lv.warp_labels(world, Scene(cam, (100.0, 100.0)), (1280, 720), lv.l3_warps(route, "m"),
                       visibility=every, ui_rects=())  # fmt: skip
    assert len(r.labels) == 1 and r.excluded == ()


def test_packets_reader(tmp_path: Path) -> None:
    with gzip.open(tmp_path / "packets.jsonl.gz", "wt") as fh:
        fh.write(json.dumps({"t_mono_ns": 1, "type": "map_change"}) + "\n")
    assert L.load_events(tmp_path) == [{"t_mono_ns": 1, "type": "map_change"}]
