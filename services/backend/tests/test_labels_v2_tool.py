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


# --- npc-sheet (N3 preparation) ---


def test_pick_spread_keeps_first_and_last() -> None:
    assert L.pick_spread(list(range(10)), 4) == [0, 3, 6, 9]
    assert L.pick_spread([1, 2], 8) == [1, 2]
    assert L.pick_spread([], 3) == [] and L.pick_spread([1], 0) == []


def test_sighting_rows_count_below_tau_and_why() -> None:
    items = [
        {"session": "a", "map": "m", "ncc": 0.5, "why_low": None},
        {"session": "a", "map": "m", "ncc": 0.05, "why_low": "occluded"},
        {"session": "b", "map": "n", "ncc": 0.01, "why_low": "ui_covered"},
        {"session": "b", "map": "n", "ncc": None, "why_low": None},
    ]
    r = L.sighting_rows(items, 0.092)
    assert (r["sightings"], r["sessions"], r["scored"], r["below_tau"]) == (4, 2, 3, 2)
    assert (r["below_tau_occluded"], r["below_tau_ui"], r["maps"]) == (1, 1, ["m", "n"])
    assert r["ncc_median"] == 0.05


def test_draw_sheet_tiles_crops_with_the_box(tmp_path: Path) -> None:
    from PIL import Image

    img = np.zeros((100, 200, 3), np.uint8)
    img[40:80, 90:110] = 200
    path = tmp_path / "f.png"
    Image.fromarray(img).save(path)
    items = [{"image": str(path), "box": [90.0, 40.0, 110.0, 80.0], "ncc": 0.4},
             {"image": str(path), "box": [-5.0, 10.0, 15.0, 60.0], "ncc": None}]  # fmt: skip
    out = tmp_path / "sheet" / "npc_1.png"
    L.draw_sheet(items, out, cols=2)
    sheet = np.asarray(Image.open(out).convert("RGB"))
    assert sheet.shape[0] == L.TILE_H + 4
    assert ((sheet[..., 1] == 255) & (sheet[..., 0] == 0)).any()  # the green box is drawn
    L.draw_sheet([], tmp_path / "none.png")
    assert not (tmp_path / "none.png").exists()


def test_npc_sheet_needs_the_sprites(capsys: pytest.CaptureFixture[str]) -> None:
    a = SimpleNamespace(npc_sprites=None, npc_sprite_names=None)
    assert L.cmd_npc_sheet(a) == 2
    assert "--npc-sprites" in capsys.readouterr().err


def _png_bytes(value: int) -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(np.full((6, 8, 3), value, np.uint8)).save(buf, format="PNG")
    return buf.getvalue()


def recorded_png_session(root: Path, frames_per_shard: tuple[int, ...]) -> Path:
    """A synthetic recorded PNG session: tar shards of <key>.png + <key>.json (the recorder's
    member order), a manifest naming them. Frame n has t_mono_ns 1000 + n and grey level n."""
    import io
    import tarfile

    s = root / "rec"
    s.mkdir()
    shards, n = [], 0
    for i, count in enumerate(frames_per_shard):
        name = f"shard-{i:06d}.tar"
        with tarfile.open(s / name, "w") as tar:
            for _ in range(count):
                key = f"{n:09d}"
                for ext, data in (
                    ("png", _png_bytes(n)),
                    ("json", json.dumps({"frame_id": n, "t_mono_ns": 1000 + n}).encode()),
                ):
                    info = tarfile.TarInfo(f"{key}.{ext}")
                    info.size = len(data)
                    tar.addfile(info, io.BytesIO(data))
                n += 1
        shards.append(name)
    (s / "manifest.json").write_text(json.dumps({"format": "png", "shards": shards,
                                                 "game_region": [0, 0, 8, 6]}))  # fmt: skip
    return s


def test_shard_frames_read_a_recorded_png_session_without_images(tmp_path: Path) -> None:
    """Every n-th frame across shards (json-member order, as build_frame_cache's
    recorded_times counts), each a seek-and-read reference to its own PNG bytes."""
    s = recorded_png_session(tmp_path, (3, 2))
    every1 = L.shard_frames(s)
    assert [t for t, _ in every1] == [1000, 1001, 1002, 1003, 1004]
    got = L.shard_frames(s, every=2)
    assert [t for t, _ in got] == [1000, 1002, 1004]
    assert all(L.SHARD_REF.match(ref) for _, ref in got)
    assert got[2][1].startswith(str(s / "shard-000001.tar") + "@")
    for t, ref in got:
        img = np.asarray(L.open_frame(ref).convert("RGB"))
        assert img.shape == (6, 8, 3) and int(img[0, 0, 0]) == t - 1000  # the frame's own bytes
    # an H.264 session, a demo session and a bare directory have no shard frames
    (tmp_path / "h").mkdir()
    (tmp_path / "h" / "manifest.json").write_text(json.dumps({"format": "h264"}))
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "manifest.json").write_text(json.dumps({"kind": "demo", "shards": ["x"]}))
    assert L.shard_frames(tmp_path / "h") == L.shard_frames(tmp_path / "d") == []
    assert L.shard_frames(tmp_path) == []


def test_open_frame_refuses_a_short_shard_read(tmp_path: Path) -> None:
    s = recorded_png_session(tmp_path, (1,))
    _t, ref = L.shard_frames(s)[0]
    m = L.SHARD_REF.match(ref)
    assert m is not None
    big = f"{m['path']}@{m['offset']}+{10**9}"
    with pytest.raises(ValueError, match="short read"):
        L.open_frame(big)


def test_draw_sheet_takes_shard_frames(tmp_path: Path) -> None:
    from PIL import Image

    s = recorded_png_session(tmp_path, (2,))
    items = [{"image": ref, "box": [1.0, 1.0, 5.0, 4.0], "ncc": 0.3}
             for _t, ref in L.shard_frames(s)]  # fmt: skip
    out = tmp_path / "sheet.png"
    L.draw_sheet(items, out, cols=2)
    assert Image.open(out).size[1] == L.TILE_H + 4


def test_npc_sheet_lists_h264_sessions_as_without_images(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """npc-sheet never decodes video: a recorded H.264 session (index only) is reported, and no
    labeller is built for it."""
    h = tmp_path / "h264"
    h.mkdir()
    (h / "manifest.json").write_text(json.dumps({"format": "h264"}))
    (h / "stream.idx.csv").write_text("au,frame_id,idr,offset,length,t_publish_ns\n0,0,1,0,10,5\n")
    with gzip.open(h / "packets.jsonl.gz", "wt") as fh:
        fh.write("")
    a = SimpleNamespace(npc_sprites=tmp_path, npc_sprite_names=tmp_path / "n.json",
                        out_dir=tmp_path / "out", sessions=[h], every=15, tau=0.092,
                        per_sprite=8, jobs=[909], k=0.14)  # fmt: skip
    assert L.cmd_npc_sheet(a) == 0
    out = json.loads(capsys.readouterr().out.split("\nsheets")[0])
    assert out["sessions_without_images"] == ["h264"] and out["sprites"] == []
    saved = json.loads((tmp_path / "out" / "npc_sheet.json").read_text())
    assert saved["k"] == 0.14 and saved["sessions_without_images"] == ["h264"]


# --- Session: which labeller a session gets -------------------------------------------------------


def test_a_recorded_png_session_gets_its_own_recording_labeller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A recorded PNG session has no stream.idx.csv; it must not fall to the demo branch, whose
    console offset lookup has no client name (2026-10-10: the v1 PNG sessions failed there)."""
    import qa_export

    calls: list[tuple[Any, ...]] = []

    class FakeLabeler:
        def __init__(self, path: Path, labels: str = "v0", **kw: Any) -> None:
            calls.append(("recording", path.name, labels))
            self.offset_ms, self.timeline = 40.0, SimpleNamespace(inferred_aid=None)

        @classmethod
        def from_events(cls, events: Any, backend: str, size: Any, offset_ms: float,
                        labels: str = "v1") -> Any:  # fmt: skip
            calls.append(("events", backend, offset_ms))
            return SimpleNamespace(offset_ms=offset_ms, timeline=SimpleNamespace(inferred_aid=None))

    for name in ("Labeler", "KB_CLASSES", "KB_SPRITE_NAMES"):  # Session sets the KB paths
        monkeypatch.setattr(qa_export, name, getattr(qa_export, name))
    monkeypatch.setattr(qa_export, "Labeler", FakeLabeler)
    (tmp_path / "route.json").write_text(json.dumps({"warps": {}}))
    a = SimpleNamespace(kb=tmp_path, offset_ms=55.0, npc_extents=None, npc_sprites=None,
                        npc_sprite_names=None, cutin_rect="1,2,3,4",
                        warp_visibility=None)  # fmt: skip
    manifests = {"rec": {"backend": "console", "game_region": [80, 77, 1280, 720], "shards": []},
                 "demo": {"kind": "demo", "backend": "console"}}  # fmt: skip
    for name, manifest in manifests.items():
        (tmp_path / name).mkdir()
        (tmp_path / name / "manifest.json").write_text(json.dumps(manifest))
        with gzip.open(tmp_path / name / "packets.jsonl.gz", "wt") as fh:
            fh.write("")
        L.Session(tmp_path / name, a)
    assert calls == [("recording", "rec", "v1"), ("events", "console", 55.0)]
    # --k sets the labeller's sprite scale (v1's 0.14); without it the labeller's default stays
    a.k = 0.14
    assert L.Session(tmp_path / "rec", a).labeler.k == 0.14
