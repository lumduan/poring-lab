"""The orcsdun01 label pipeline (docs/planning/orcsdun01-detector.md sections 3-5), on SYNTHETIC
sessions (no client pixels, no rAthena data, no NAS):
- warp_watch sessions (JPEG tar shards) read by qa_export / build_frame_cache / labels_v2, labelled
  in the RECORDED UI layout's rectangles, with the rdp offset rule;
- the committed per-species class list (ids only) and --classes species: ids, KB names, the
  fail-closed exclusions, the warp rule without a person's table;
- the camera check's pure parts (the FFT shift search = label_check's NCC, the standing filter,
  the bars) and the blind pack (its answer key in another directory, no class name in it)."""

from __future__ import annotations

import gzip
import importlib.util
import io
import json
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest
from PIL import Image

from poring_dataset import labels_v2 as lv
from poring_dataset import mapcache
from poring_dataset.timeline import ActorState, FrameWorld

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import client_layout  # noqa: E402
import label_check  # noqa: E402
import orc_camera_check as occ  # noqa: E402
import orc_label_sheets as ols  # noqa: E402
import qa_export  # noqa: E402
import warp_watch as ww  # noqa: E402

T0 = 700_000_000_000_000_000
SID = "20990101T000000-orcsdun01-syn"
ORDER = [1002, 1063, 1008, 1113, 1018, 1005, 1042, 1082, 1084, 1111, 1152, 1153]


def load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def bfc() -> ModuleType:
    return load("build_frame_cache_orc_under_test", SCRIPTS / "build_frame_cache.py")


def jpeg(rgb: tuple[int, int, int], size: tuple[int, int] = (64, 36)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, rgb).save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def ww_session(root: Path, n: int = 7, layout: str | None = "hunt",
               events: list[dict[str, Any]] | None = None,
               size: tuple[int, int] = (64, 36)) -> Path:  # fmt: skip
    """A warp_watch.py session: frames/shard-*.tar (several shards), packets, manifest."""
    s = root / SID
    # every MEMBER opens a new shard: a frame's jpg and json lie in two shards, as at the
    # recorder's 256-MB boundary
    shards = ww.JpegShards(s / "frames", max_bytes=1)
    for i in range(n):
        shards.add(i, T0 + i * 200_000_000, jpeg((20 * i, 100, 200), size))
    shards.close()
    with gzip.open(s / "packets.jsonl.gz", "wt") as fh:
        for e in events or []:
            fh.write(json.dumps(e) + "\n")
    man = {"sid": SID, "map": "orcsdun01", "t0_ns": T0, "t1_ns": T0 + n * 200_000_000,
           "backend": "rdp", "size": list(size), "rec_hz": 5.0, "quality": 80,
           "ui_layout": layout, "recorder": {"shards": shards.shards}}  # fmt: skip
    (s / "manifest.json").write_text(json.dumps(man))
    return s


# --- the warp_watch session reader --------------------------------------------------------------


def test_a_warp_watch_session_is_read_in_order_as_bgr(tmp_path: Path) -> None:
    s = ww_session(tmp_path)
    man = json.loads((s / "manifest.json").read_text())
    assert qa_export.is_warp_watch(man) and not qa_export.is_warp_watch({"session_id": "x"})
    assert qa_export.session_id(man) == SID
    refs = qa_export.jpeg_index(s, man)
    assert [r.frame_id for r in refs] == list(range(7))
    assert [r.t_mono_ns for r in refs] == [T0 + i * 200_000_000 for i in range(7)]
    assert len({r.shard for r in refs}) > 1  # across shards
    got = list(qa_export.session_frames(s, man, every=3, limit=0))
    assert [m["frame_id"] for m, _ in got] == [0, 3, 6]
    img = got[1][1]
    assert img.shape == (36, 64, 3)
    b, g, r = (int(v) for v in img[18, 32])  # BGR, like the PNG / H.264 readers
    assert abs(r - 60) <= 6 and abs(g - 100) <= 6 and abs(b - 200) <= 6
    # without the recorder's list: frames/shard-*.tar by name
    del man["recorder"]
    assert [r.frame_id for r in qa_export.jpeg_index(s, man)] == list(range(7))


def test_build_frame_cache_reads_times_without_decoding(
    bfc: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = ww_session(tmp_path)
    man = json.loads((s / "manifest.json").read_text())
    decoded = [(int(m["frame_id"]), int(m["t_mono_ns"]))
               for m, _ in bfc.session_frames(s, man, 15, 1, every_jpeg=2)]  # fmt: skip
    monkeypatch.setattr(qa_export, "read_jpeg", lambda ref: pytest.fail("decoded a JPEG"))
    assert list(bfc.recorded_times(s, man, 15, 1, every_jpeg=2)) == decoded
    assert [fid for fid, _ in decoded] == [0, 2, 4, 6]
    assert "orcsdun01" in bfc.SCENE_MAPS


def test_labels_v2_banked_frames_of_a_warp_watch_session(tmp_path: Path) -> None:
    import labels_v2 as tool

    s = ww_session(tmp_path)
    assert tool.banked_frames(s, every=3) == [(T0 + i * 200_000_000, None) for i in (0, 3, 6)]


def test_a_cut_shard_keeps_only_whole_frames(tmp_path: Path) -> None:
    s = ww_session(tmp_path, n=2)
    import tarfile

    extra = s / "frames" / "shard-000009.tar"
    with tarfile.open(extra, "w") as tar:  # a json whose jpg never landed
        body = json.dumps({"frame_id": 9, "t_mono_ns": T0}).encode()
        info = tarfile.TarInfo("000000009.json")
        info.size = len(body)
        tar.addfile(info, io.BytesIO(body))
    man = json.loads((s / "manifest.json").read_text())
    man.pop("recorder")
    assert [r.frame_id for r in qa_export.jpeg_index(s, man)] == [0, 1]


# --- the labeller on a warp_watch session ---------------------------------------------------------

pytestmark_mapcache = pytest.mark.skipif(
    not (mapcache.GENERATED / "map_cache.base.dat").exists(), reason="run scripts/gen_mapcache.py"
)


@pytest.fixture
def flat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    camera = tmp_path / "camera.json"  # a flat homography: u = 30 dx + 392, v = 330 - 30 dy
    camera.write_text(json.dumps({"h": [[30.0, 0, 392.0], [0, -30.0, 330.0], [0, 0, 1.0]]}))
    monkeypatch.setattr(qa_export, "camera_file", lambda backend: camera)
    monkeypatch.setattr(qa_export, "load_indoor_table", lambda: frozenset())
    return camera


def packets_one_monster(dx: int, dy: int) -> list[dict[str, Any]]:
    ms = 1_000_000
    return [
        {"t_mono_ns": T0 - 1000 * ms, "type": "map_change", "map": "prt_fild08", "x": 170,
         "y": 375},
        {"t_mono_ns": T0 - 900 * ms, "type": "entity_appear", "kind": "new", "gid": 7,
         "char_id": 0, "objtype": 5, "job": 1002, "speed": 400, "name": "x", "x": 170 + dx,
         "y": 375 + dy},
    ]  # fmt: skip


@pytestmark_mapcache
def test_the_labeller_uses_the_recorded_layouts_ui_rects(
    tmp_path: Path, flat: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # foot at (122, 300): the v0 box (100..144, 260..300) lies under the STANDARD Basic
    # Information window (0..222 x 0..325) but in the open on the HUNT layout (it ends at y 143)
    ev = packets_one_monster(-9, 1)
    hunt = ww_session(tmp_path / "h", events=ev, layout="hunt", size=(1280, 720))
    std = ww_session(tmp_path / "s", events=ev, layout="standard", size=(1280, 720))
    lab_h = qa_export.Labeler(hunt, "120", labels="v0")
    lab_s = qa_export.Labeler(std, "120", labels="v0")
    assert lab_h.size == (1280, 720)
    assert lab_h.ui_rects == tuple((x0, y0, x1 - x0, y1 - y0)
                                   for x0, y0, x1, y1 in client_layout.RECTS["hunt"])  # fmt: skip
    boxes = lab_h.boxes(T0)
    assert boxes is not None and [b["gid"] for b in boxes] == [7]
    assert boxes[0]["x1"] == pytest.approx(100) and boxes[0]["y2"] == pytest.approx(300)
    assert lab_s.boxes(T0) == []  # behind the standard layout's Basic Information
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(qa_export, "auto_offset_ms",
                        lambda cfg: (seen.append(cfg), (375.9, "run"))[1])  # fmt: skip
    assert qa_export.Labeler(hunt, labels="v0").offset_ms == 375.9
    assert seen == [{"backend": "rdp", "client": {"name": "xfreerdp"}}]


@pytestmark_mapcache
def test_an_unknown_layout_fails_closed(tmp_path: Path, flat: Path) -> None:
    s = ww_session(tmp_path, layout=None, size=(1280, 720))
    with pytest.raises(SystemExit, match="ui_layout"):
        qa_export.Labeler(s, "120", labels="v0")


def test_a_recorded_session_keeps_the_standard_rects() -> None:
    from poring_dataset.ui_layout import UI_RECTS

    assert qa_export.ui_rects_for({"session_id": "x", "game_region": [0, 0, 1280, 720]}) == UI_RECTS
    assert qa_export.recording_config({"config": {"backend": "console"}}) == {"backend": "console"}


# --- the per-species class list ---------------------------------------------------------------


def kb_dir(root: Path, missing: int | None = None) -> Path:
    d = root / "kb"
    d.mkdir(parents=True)
    (d / "route.json").write_text(json.dumps({"warps": {"m": [], "orcsdun01": []}}))
    rows = {str(m): {"aegis": f"MOB_{m}"} for m in ORDER if m != missing}
    (d / "classes.json").write_text(json.dumps({"m": rows}))
    return d


def test_the_committed_class_list_is_ids_only_in_the_plans_order(bfc: ModuleType) -> None:
    doc = json.loads(bfc.SPECIES_LIST.read_text())
    assert doc["fixed"] == {"player": 0, "npc": 1, "warp": 2} and doc["monsters"] == ORDER
    assert not any(isinstance(v, str) for v in doc["monsters"])  # no names committed
    c = bfc.SpeciesClasses.load(bfc.SPECIES_LIST)
    assert c.index == {m: 3 + i for i, m in enumerate(ORDER)}
    assert c.class_of(lv.V2Label("monster", 0, 0, 1, 1, job=1153, kind="opaque")) == 14
    assert c.class_of(lv.V2Label("warp", 0, 0, 1, 1)) == 2
    assert c.class_of(lv.V2Label("player", 0, 0, 1, 1, kind="self")) == 0


def test_names_come_from_the_kb_and_a_nameless_species_stops(
    bfc: ModuleType, tmp_path: Path
) -> None:
    c = bfc.SpeciesClasses.load(bfc.SPECIES_LIST)
    names = c.names(kb_dir(tmp_path / "a"))
    assert names[0] == "player" and names[1] == "npc" and names[2] == "warp"
    assert names[3] == "mob_1002" and names[14] == "mob_1153" and len(names) == 15
    with pytest.raises(SystemExit, match="1084"):
        c.names(kb_dir(tmp_path / "b", missing=1084))


def test_species_reasons_fail_closed(bfc: ModuleType, tmp_path: Path) -> None:
    c = bfc.SpeciesClasses.load(bfc.SPECIES_LIST)
    ok = [lv.V2Label("monster", 0, 0, 1, 1, job=1005, kind="opaque"),
          lv.V2Label("npc", 0, 0, 1, 1, job=92, kind="sprite_opaque")]  # fmt: skip
    assert c.reasons(ok) == []
    assert c.reasons([lv.V2Label("monster", 0, 0, 1, 1, job=1234, kind="opaque")]) == [
        "species_unlisted:1234"]  # fmt: skip
    assert c.reasons([lv.V2Label("monster", 0, 0, 1, 1, job=1153, kind="v0")]) == [
        "monster_unsized:1153"]  # fmt: skip
    assert c.reasons([lv.V2Label("monster", 0, 0, 1, 1, job=None)]) == ["monster_unknown_species"]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"fixed": {"player": 0, "npc": 1, "warp": 2},
                               "monster_first_id": 4, "monsters": [1002]}))  # fmt: skip
    with pytest.raises(SystemExit, match="gap"):
        bfc.SpeciesClasses.load(bad)


def lab(cls: str, x0: float, job: int | None = None, kind: str = "opaque") -> lv.V2Label:
    return lv.V2Label(cls, x0, 300.0, x0 + 40.0, 360.0, gid=int(x0), job=job, kind=kind)


# t -> (map, status, labels, labels_v2 exclusions)
WORLD: dict[int, tuple[str, str, tuple[lv.V2Label, ...], tuple[str, ...]]] = {
    100: ("orcsdun01.gat", "ok", (lab("player", 600.0, 0, "self"), lab("monster", 100.0, 1153),
                                  lab("monster", 200.0, 1005)), ()),
    200: ("orcsdun01.gat", "ok", (lab("monster", 100.0, 1234),), ()),  # unlisted species
    300: ("orcsdun01.gat", "ok", (lab("monster", 100.0, 1152, "v0"),), ()),  # no sprite
    400: ("orcsdun01.gat", "ok", (lab("monster", 100.0, 1082),),
          ("warp_visibility_unknown:orcsdun01:32,172",)),  # a drawn portal, no table
    500: ("orcsdun01.gat", "gm_window", (), ()),
}  # fmt: skip


class FakeSession:
    def __init__(self) -> None:
        self.labeler = SimpleNamespace(size=(1280, 720), k=0.14, sheets=None)

    def world(self, t: int) -> FrameWorld:
        return FrameWorld(t, WORLD[t][0], 7, (100.0, 100.0), ())

    def frame(self, t: int) -> tuple[str, lv.Frame | None, Any]:
        m, status, labels, excluded = WORLD[t]
        if status != "ok":
            return status, None, None
        return "ok", lv.Frame(t, m, labels, (), excluded), None


def demo(root: Path) -> None:
    s = root / "demo" / SID
    (s / "frames").mkdir(parents=True)
    (s / "manifest.json").write_text(json.dumps({"kind": "demo", "backend": "rdp"}))
    with gzip.open(s / "packets.jsonl.gz", "wt") as fh:
        fh.write("")
    for i, t in enumerate(sorted(WORLD)):
        Image.new("RGB", (1280, 720), (i * 30, 60, 90)).save(s / "frames" / f"{i:04d}-{t}.png")


def species_argv(root: Path, kb: Path, *extra: str) -> list[str]:
    return ["--labels", "v2", "--classes", "species", "--kb", str(kb), "--demo-root",
            str(root / "demo"), "--datasets", str(root / "nas"), "--out", str(root / "out"),
            "--cache-id", "c", "--train", SID, *extra]  # fmt: skip


@pytest.fixture
def species_setup(bfc: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    gat = tmp_path / "gat"
    gat.mkdir()
    (gat / "orcsdun01.gat").write_bytes(b"")
    monkeypatch.setattr(bfc.camera_mod, "GAT_DIR", gat)
    monkeypatch.setattr(bfc, "make_v2_session", lambda path, v2: FakeSession())
    demo(tmp_path)
    return kb_dir(tmp_path)


def test_species_cache_writes_species_ids_and_excludes_what_it_cannot_label(
    bfc: ModuleType, tmp_path: Path, species_setup: Path
) -> None:
    import tarfile

    assert bfc.main(species_argv(tmp_path, species_setup, "--image", "png")) == 0
    cache = tmp_path / "out" / "c"
    man = json.loads((cache / "manifest.json").read_text())
    assert man["names"]["0"] == "player" and man["names"]["14"] == "mob_1153"
    assert man["k"] == 0.14  # the v1 labels' k by default
    assert man["v2"]["classes"]["mode"] == "species" and man["v2"]["classes"]["monsters"] == ORDER
    assert man["v2"]["warp_visibility"] is None and "excludes" in man["v2"]["warp_rule"]
    row = man["sessions"][SID]
    assert (row["seen"], row["kept"], row["gm_window"], row["excluded_frames"]) == (5, 1, 1, 3)
    assert row["excluded"] == {"species_unlisted": 1, "monster_unsized": 1,
                               "warp_visibility_unknown": 1}  # fmt: skip
    with tarfile.open(cache / "shard-000000.tar") as t:
        txt = t.extractfile(f"{SID}.000000000.txt").read().decode()  # type: ignore[union-attr]
        info = json.loads(t.extractfile(f"{SID}.000000000.json").read())  # type: ignore[union-attr]
    assert [int(x.split()[0]) for x in txt.splitlines()] == [0, 14, 8]  # player, 1153, 1005
    assert info["boxes"] == [[0, 0, "self"], [14, 1153, "opaque"], [8, 1005, "opaque"]]


def test_species_dry_run_counts_the_exclusions(
    bfc: ModuleType, tmp_path: Path, species_setup: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert bfc.main(species_argv(tmp_path, species_setup, "--dry-run")) == 0
    first = json.loads(capsys.readouterr().out.split("\n", 1)[0])
    assert first["excluded_detail"] == {"species_unlisted:1234": 1, "monster_unsized:1152": 1,
                                        "warp_visibility_unknown:orcsdun01:32,172": 1}  # fmt: skip
    assert first["species_boxes"] == {"1005": 1, "1153": 1}
    assert not (tmp_path / "out").exists()


def test_plain_v2_still_needs_the_visibility_table(
    bfc: ModuleType, tmp_path: Path, species_setup: Path
) -> None:
    argv = [x for x in species_argv(tmp_path, species_setup) if x not in ("--classes", "species")]
    with pytest.raises(SystemExit, match="warp-visibility"):
        bfc.main(argv)
    with pytest.raises(SystemExit, match="builds on --labels v1"):
        bfc.main(["--labels", "v0", "--classes", "species", "--train", SID])
    # v1 + the species split exists since 3f (Batt 3b item 2: v1's rules, the species split only)
    with pytest.raises(SystemExit, match="needs --kb"):
        bfc.main(["--labels", "v1", "--classes", "species", "--train", SID])


def test_without_a_table_a_drawn_portal_excludes_the_frame() -> None:
    """labels_v2's own rule, which --classes species relies on: an EMPTY visibility table (no
    person's measurement) leaves a confirmed portal on screen unlabelled -> the frame excluded."""
    from poring_dataset.camera import Camera
    from poring_dataset.render import Scene
    from poring_dataset.timeline import EntityState

    cam = Camera(0.0, np.radians(45.0), 400.0, np.radians(15.0), 640.0, 360.0, 720)
    scene = Scene(cam, (100.0, 100.0))
    portal = EntityState(9, 6, 45, "", 101.0, 101.0, False)
    fw = FrameWorld(1, "orcsdun01.gat", 7, (100.0, 100.0), (portal,))
    res = lv.warp_labels(fw, scene, (1280, 720), (lv.WarpCell(101, 101),), visibility={})
    assert res.labels == () and res.excluded == ("warp_visibility_unknown:orcsdun01:101,101",)


# --- the camera check's pure parts --------------------------------------------------------------


def test_shift_search_finds_a_planted_offset_and_matches_label_checks_ncc() -> None:
    rng = np.random.default_rng(3)
    h, w, r = 30, 20, 16
    template = rng.uniform(0, 255, (h, w))
    mask = rng.uniform(0, 1, (h, w)) > 0.3
    observed = rng.uniform(0, 255, (h + 2 * r, w + 2 * r))
    dx, dy = 5, -3
    win = observed[r + dy : r + dy + h, r + dx : r + dx + w]
    win[mask] = 0.5 * template[mask] + 40.0  # the sprite, darker (NCC ignores gain and offset)
    grid = occ.shift_ncc(observed, template, mask, r)
    a, b = np.unravel_index(int(np.nanargmax(grid)), grid.shape)
    assert (b - r, a - r) == (dx, dy) and grid[a, b] == pytest.approx(1.0)
    for ddx, ddy in ((0, 0), (-16, 16), (7, 2)):
        ref = label_check.ncc(observed[r + ddy : r + ddy + h, r + ddx : r + ddx + w], template,
                              mask)  # fmt: skip
        assert grid[r + ddy, r + ddx] == pytest.approx(ref, abs=1e-9)
    tiny = np.zeros((h, w), bool)
    tiny[0, :5] = True
    assert np.isnan(occ.shift_ncc(observed, template, tiny, r)).all()  # < MIN_PIXELS


def st(state: str, t: int, since: int | None, x: float = 5.0) -> ActorState:
    return ActorState(1, t, state, 0, None, x, 5.0, 1005, since)  # type: ignore[arg-type]


def test_standing_means_idle_for_a_second() -> None:
    s = 1_000_000_000
    assert occ.standing(st("idle", 10 * s, 9 * s), None)
    assert not occ.standing(st("idle", 10 * s, 9 * s + 1), None)
    assert not occ.standing(st("walk", 10 * s, 5 * s), None)
    assert occ.standing(st("idle", 10 * s, None), st("idle", 9 * s, None))  # idle since appearing
    assert not occ.standing(st("idle", 10 * s, None), None)  # not seen a second ago
    assert not occ.standing(st("idle", 10 * s, None), st("idle", 9 * s, None, x=6.0))
    assert not occ.standing(None, None)


def test_isolation_and_ui_clearance() -> None:
    assert occ.isolated((500.0, 300.0), [(621.0, 300.0), (500.0, 421.0)])
    assert not occ.isolated((500.0, 300.0), [(600.0, 360.0)])  # 117 px
    hunt = qa_export.ui_rects_for({**dict.fromkeys(qa_export.WARP_WATCH_KEYS, 0),
                                   "ui_layout": "hunt"})  # fmt: skip
    assert occ.clear_box((300.0, 200.0, 340.0, 260.0), hunt, (1280, 720))
    assert not occ.clear_box((300.0, 40.0, 340.0, 100.0), hunt, (1280, 720))  # 16 px: the bar
    assert not occ.clear_box((10.0, 400.0, 50.0, 460.0), hunt, (1280, 720))  # the frame's edge


def test_hue_and_its_circular_gap() -> None:
    red = occ.hue_stats(np.array([[200, 10, 10]] * 5))
    green = occ.hue_stats(np.array([[10, 200, 10]] * 5))
    assert red["hue_deg"] == pytest.approx(0.0, abs=0.1) or red["hue_deg"] == pytest.approx(360.0)
    assert green["hue_deg"] == pytest.approx(120.0, abs=0.1)
    assert occ.hue_gap(350.0, 10.0) == 20.0 and occ.hue_gap(None, 3.0) is None
    assert occ.hue_stats(np.zeros((0, 3)))["n_px"] == 0


def row(mob: int, c1: float, why: str | None = None, dx: int = 0, dy: int = 0) -> dict[str, Any]:
    return {"mob": mob, "c1": c1, "why_low": why, "best": 0.5, "dx": dx, "dy": dy}


def test_the_bars_are_the_plans() -> None:
    rows = [row(1153, 0.5, dx=4, dy=-4) for _ in range(49)] + [row(1153, 0.01, "bad_label")]
    out = occ.summarize(rows, 0.092)
    assert out["c1"]["pooled"]["bad_label_share"] == 0.02 and out["c1"]["verdict"] == "FAIL"
    rows.append(row(1153, 0.5, dx=4, dy=4))  # 1 / 51 < 2 %
    out = occ.summarize(rows, 0.092)
    assert out["c1"]["verdict"] == "PASS" and out["c2"]["per_species"]["1153"]["verdict"] == "PASS"
    rows += [row(1005, 0.5, dx=6, dy=-6) for _ in range(19)]
    out = occ.summarize(rows, 0.092)
    assert out["c2"]["per_species"]["1005"]["verdict"] == "NO_VERDICT"  # 19 < 20
    assert out["c2"]["no_verdict"] == ["1005"] and out["verdict"]["overall"] == "PASS"
    rows.append(row(1005, 0.5, dx=6, dy=6))
    assert occ.summarize(rows, 0.092)["c2"]["per_species"]["1005"]["verdict"] == "PASS"  # 6 px
    ground_off = [row(1084, 0.5, dx=5) for _ in range(20)]
    out = occ.summarize(rows + ground_off, 0.092)
    assert out["c2"]["per_species"]["1084"]["verdict"] == "FAIL" and out["c2"]["verdict"] == "FAIL"
    assert out["verdict"]["overall"] == "FAIL"
    occl = occ.summarize([row(1152, 0.01, "occluded")] * 3, 0.092)
    assert occl["c1"]["pooled"]["bad_label"] == 0 and occl["c1"]["pooled"]["occluded"] == 3


# --- the contact sheets and the blind pack ---------------------------------------------------


def item(mob: int, fid: int, x0: float = 30.0) -> Any:
    ref = qa_export.JpegRef(fid, T0 + fid, Path("/nonexistent.tar"), 0, 0)
    return ols.Item(ref, mob, fid, (x0, 20.0, x0 + 10.0, 40.0), "opaque")


def test_crop_and_box_drawing() -> None:
    assert ols.crop_box((30.0, 20.0, 40.0, 40.0), (64, 48)) == (6, 0, 64, 48)
    img = np.zeros((40, 40, 3), np.uint8)
    out = ols.draw_box(img, (10.0, 10.0, 20.0, 20.0), (0, 0))
    assert (out[9, 9:21] == ols.BOX_RGB).all() and (out[20, 9:21] == ols.BOX_RGB).all()
    assert (out[10:20, 10:20] == 0).all()  # the box's own pixels stay visible
    assert ols.enlarge(np.zeros((50, 30, 3), np.uint8)).shape == (200, 120, 3)  # x5 capped at 4
    assert ols.enlarge(np.zeros((100, 30, 3), np.uint8)).shape == (300, 90, 3)


def test_letters_and_the_blind_sample_are_seeded() -> None:
    letters = ols.letters_for(ORDER, 0)
    assert sorted(letters.values()) == sorted(ORDER) and list(letters)[0] == "A"
    assert ols.letters_for(ORDER, 0) == letters and ols.letters_for(ORDER, 1) != letters
    items = {1005: [item(1005, i) for i in range(50)], 1082: [item(1082, i) for i in range(4)]}
    a = ols.blind_sample(items, 30, SID, 0)
    assert len(a) == 34 and sum(1 for it in a if it.mob == 1082) == 4
    assert [(it.mob, it.gid) for it in ols.blind_sample(items, 30, SID, 0)] == [
        (it.mob, it.gid) for it in a]  # fmt: skip
    assert [it.mob for it in a] != sorted(it.mob for it in a)  # one shuffled numbering


def test_the_blind_pack_hides_the_classes_and_the_key_lives_elsewhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    items = {1005: [item(1005, i) for i in range(5)], 1153: [item(1153, i, 10.0) for i in range(3)]}
    classes = SimpleNamespace(monsters=tuple(ORDER), provenance=lambda: {})
    sess = SimpleNamespace(labeler=SimpleNamespace(size=(64, 48), sheets=lambda m: None))
    summary = {"session": SID}
    monkeypatch.setattr(
        ols, "collect", lambda s, a: (summary, items, SimpleNamespace(classes=classes), sess)
    )
    monkeypatch.setattr(qa_export, "read_jpeg",
                        lambda ref: np.full((48, 64, 3), ref.frame_id * 20, np.uint8))  # fmt: skip
    monkeypatch.setattr(
        ols, "reference_sheet", lambda sheets, letters: np.zeros((8, 8, 3), np.uint8)
    )
    a = SimpleNamespace(out_root=tmp_path, per_sheet=4, per_blind=30, seed=0)
    out = ols.write_outputs(tmp_path / "unused", a)  # type: ignore[arg-type]
    pack, key_path = Path(out["blind_pack"]), Path(out["answer_key"])
    assert key_path.parent != pack and pack not in key_path.parents
    key = json.loads(key_path.read_text())
    crops = sorted(p.name for p in (pack / "crops").iterdir())
    assert crops == [f"{i:03d}.png" for i in range(1, 9)] and sorted(key["crops"]) == [
        c[:3] for c in crops]  # fmt: skip
    assert key["per_species"] == {"1005": 5, "1153": 3}
    assert sorted(key["letters"].values()) == sorted(ORDER)
    text = (pack / "pack.json").read_text()
    assert not any(str(m) in text for m in ORDER)  # no mob id, no name in the pack
    assert sorted(p.name for p in pack.iterdir()) == ["crops", "grids", "pack.json",
                                                       "reference.png"]  # fmt: skip
    assert sorted(p.name for p in (pack / "grids").iterdir()) == ["grid_01.png"]  # 8 crops
    assert (tmp_path / SID / "sheets" / "species_1005.png").exists()


def test_dwell_spans_pair_by_ref() -> None:
    ev = [{"event": "warp", "ref": 0, "t_mono_ns": 1}, {"event": "dwell_start", "ref": 0,
          "t_mono_ns": 10}, {"event": "dwell_end", "ref": 0, "t_mono_ns": 40},
          {"event": "dwell_start", "ref": 1, "t_mono_ns": 50}]  # fmt: skip
    assert occ.dwell_spans(ev) == [(10, 40)]  # an unfinished dwell is not a span


# --- a REAL positive case (memory: a scorer needs one from a real session) -------------------

COL1 = Path("/mnt/poring-lab-datasets/detector-collection/orcsdun01/20261021T103231-orcsdun01-col1")
KB = Path(os.environ.get("PORING_KB", str(ROOT / "data" / "kb")))


def test_camera_check_real_positive_case(monkeypatch: pytest.MonkeyPatch) -> None:
    """col1 (the first orcsdun01 block, 2026-10-21), frame 2320: an Orc Zombie (gid 110093469)
    standing alone; the label's sprite, at the projected anchor with k 0.14, is what the client
    drew there (C1 0.79, the best offset (0, 0)). Local data only: skipped elsewhere."""
    if not (COL1 / "manifest.json").exists() or not (KB / "classes.json").exists():
        pytest.skip("col1 or the local KB is not here")
    if not (qa_export.SPRITE_DIR / "orc_zombie.spr").exists():
        pytest.skip("the decoded orcsdun01 sprites are not in the sprite dir")
    from poring_dataset.render import Actor, MonsterAction, predict_sprite

    monkeypatch.setattr(qa_export, "KB_CLASSES", KB / "classes.json")
    monkeypatch.setattr(qa_export, "KB_SPRITE_NAMES", KB / "monster_sprite_names.json")
    lab = qa_export.Labeler(COL1, "auto", labels="v1", k=0.14)
    assert lab.ui_rects == qa_export.ui_rects_for({**dict.fromkeys(qa_export.WARP_WATCH_KEYS, 0),
                                                   "ui_layout": "hunt"})  # fmt: skip
    one = {"recorder": {"shards": ["shard-000001.tar"]}}  # frame 2320 lies in the 2nd shard
    ref = next(r for r in qa_export.jpeg_index(COL1, one) if r.frame_id == 2320)
    tw = ref.t_mono_ns - int(lab.offset_ms * 1e6)
    world = lab.timeline.frame_world(tw)
    ent = next(e for e in world.entities if e.gid == 110093469)
    assert ent.job == 1153 and world.map == "orcsdun01.gat"
    st = lab.timeline.state(ent.gid, tw)
    assert occ.standing(st, lab.timeline.state(ent.gid, tw - occ.STANDING_NS))
    assert st is not None and st.facing is not None
    scene = occ.scene_for(lab, world.map, world.self_pos)  # type: ignore[arg-type]
    sheet = lab.sheets(1153)
    pred = predict_sprite(Actor((ent.x, ent.y), st.facing, MonsterAction.IDLE), sheet, scene, 0.14)
    assert pred is not None
    assert [round(v) for v in pred.box] == [473, 379, 523, 471]
    frame = qa_export.read_jpeg(ref)
    c1 = label_check.score(frame, sheet, pred)
    assert c1 is not None and c1 > 0.7
    best = occ.best_offset(frame, sheet, pred)
    assert best is not None and best[1:3] == (0, 0) and best[0] == pytest.approx(c1, abs=1e-6)


def test_sessions_are_found_under_the_extra_roots(bfc: ModuleType, tmp_path: Path) -> None:
    """A combined cache: v1's sessions under --datasets, a warp_watch block under its own root."""
    nas, orc = tmp_path / "nas", tmp_path / "orc"
    for root, sid in ((nas, "v1sess"), (orc, SID)):
        (root / sid).mkdir(parents=True)
        (root / sid / "manifest.json").write_text("{}")
    a = SimpleNamespace(demo_root=tmp_path / "demo", datasets=nas, also_datasets=[orc])
    assert bfc.resolve_session("v1sess", a) == nas / "v1sess"
    assert bfc.resolve_session(SID, a) == orc / SID
    assert bfc.dataset_session(SID, a) == orc / SID
    with pytest.raises(SystemExit, match="no manifest"):
        bfc.resolve_session("nowhere", a)


def test_round5_multi_view_reference_shows_each_distinct_idle_pose_once(monkeypatch) -> None:
    """3l (blind round 5): round 4's labellers matched raised Familiar wings to the ONE-pose
    Lunatic tile. ``multi`` shows the idle action in directions 0/2/4/6 at frame 0 and its middle
    frame, identical images once; ``one`` stays rounds 1-4's single image."""
    from types import SimpleNamespace

    import numpy as np

    from poring_dataset import sprites

    calls = []

    def fake_compose(spr, act, ai, f):
        calls.append((ai, f))
        img = np.zeros((4, 4, 4), np.uint8)
        img[..., 3] = 255
        img[0, 0, 0] = (ai // 2) % 2 * 100 + f  # directions 0/4 draw alike, 2/6 alike
        return img, (0.0, 0.0)

    monkeypatch.setattr(sprites, "compose_frame", fake_compose)
    act = SimpleNamespace(
        action_index=lambda g, d: g * 8 + d, actions=[(1, 2, 3, 4)] * 16
    )  # 4 frames each
    sheet = SimpleNamespace(spr=object(), act=act)
    one = ols.reference_views(sheet, "one")
    assert len(one) == 1 and calls == [(0, 0)]
    calls.clear()
    multi = ols.reference_views(sheet, "multi")
    assert calls == [(0, 0), (0, 2), (2, 0), (2, 2), (4, 0), (4, 2), (6, 0), (6, 2)]
    assert len(multi) == 4  # directions 4 / 6 repeat 0 / 2's images: shown once
    sheet_img = ols.reference_sheet({1005: sheet}, {"A": 1005}, views="multi")
    assert sheet_img.ndim == 3 and sheet_img.shape[2] == 3
