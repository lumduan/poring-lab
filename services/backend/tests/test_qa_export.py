"""scripts/qa_export.py end to end on a synthetic recorded session (no X, no Windows, no docker)."""

import gzip
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from poring_dataset import mapcache
from poring_dataset.shards import ShardWriter, write_manifest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "qa_export.py"
T0 = 700_000_000_000_000_000

pytestmark = pytest.mark.skipif(
    not (mapcache.GENERATED / "map_cache.base.dat").exists(), reason="run scripts/gen_mapcache.py"
)


@pytest.fixture
def qa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location("qa_export", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    camera = tmp_path / "camera.json"
    h = [[30.0, 0, 392.0], [0, -30.0, 330.0], [0, 0, 1.0]]
    camera.write_text(json.dumps({"h": h}))
    monkeypatch.setattr(module, "camera_file", lambda backend: camera)
    monkeypatch.setattr(module, "BUNDLES", tmp_path / "bundles")
    # the client's indoor table is client data (/dev/shm on the lab host only): pin it here
    monkeypatch.setattr(module, "load_indoor_table", lambda: frozenset({"prt_church"}))
    return module


def session(tmp_path: Path) -> Path:
    out = tmp_path / "sess"
    writer = ShardWriter(out)
    for i in range(6):
        writer.add(i, T0 + i * 100_000_000, np.full((625, 784, 3), 40 + i, np.uint8))
    writer.close()
    ms = 1_000_000
    events = [
        {"t_mono_ns": T0 - 1000 * ms, "type": "map_change", "map": "prt_fild08", "x": 170,
         "y": 375},
        {"t_mono_ns": T0 - 900 * ms, "type": "entity_appear", "kind": "new", "gid": 7, "char_id": 0,
         "objtype": 5, "job": 1002, "speed": 400, "name": "Poring", "x": 172, "y": 375},
    ]  # fmt: skip
    with gzip.open(out / "packets.jsonl.gz", "wt") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")
    write_manifest(out, {"session_id": "s1", "backend": "rdp", "game_region": [248, 99, 784, 625],
                         "shards": writer.shards})  # fmt: skip
    return out


def test_bundle_has_frames_labels_and_index(
    qa: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sheet = tmp_path / "sheet.png"
    monkeypatch.setattr(sys, "argv", ["qa_export.py", str(session(tmp_path)), "--every", "2",
                                      "--offset-ms", "120", "--sheet", str(sheet)])  # fmt: skip
    assert qa.main() == 0
    bundle = tmp_path / "bundles" / "s1"
    labels = json.loads((bundle / "labels.json").read_text())
    assert labels["offset_ms"] == 120 and len(labels["frames"]) == 3  # every 2nd of 6
    box = labels["frames"][0]["boxes"][0]
    assert box["cls"] == "monster" and box["gid"] == 7
    assert (box["x1"] + box["x2"]) / 2 == pytest.approx(392 + 60)  # 2 cells right at 30 px/cell
    index = json.loads((tmp_path / "bundles" / "index.json").read_text())
    assert index["sessions"] == [{"id": "s1", "title": "s1 (rdp)", "frames": 3, "gold": False}]
    assert sheet.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert json.loads(capsys.readouterr().out)["with_boxes"] == 3


def run_json(path: Path, run_id: str, started: str, backend: str, client: str, paint: str | None,
             p50: float) -> None:  # fmt: skip
    cfg = {"backend": backend, "client": {"name": client, **({"paint": paint} if paint else {})}}
    path.joinpath(f"{run_id}.json").write_text(json.dumps({
        "run_id": run_id, "t_wall_start": started, "config": cfg,
        "scenes": {"outdoor": {"packet_to_frame_ms": {"p50": p50}}},
    }))  # fmt: skip


def test_auto_offset_matches_backend_client_and_paint_by_start_time(
    qa: ModuleType, tmp_path: Path
) -> None:
    """2026-10-03: the file-name sort picked V3's X-painted run for a V3b (bus) session."""
    runs = tmp_path / "runs"
    runs.mkdir()
    run_json(runs, "2026-10-03-console-5c7e-v3", "2026-10-03T13:00:00+0700", "console", "s2spike",
             "x11", 118.9)  # fmt: skip
    run_json(runs, "2026-10-03-console-26fa-v3b", "2026-10-03T17:00:00+0700", "console", "s2spike",
             "bus", 113.9)  # fmt: skip
    run_json(runs, "2026-10-03-console-0000-v3b-old", "2026-10-03T09:00:00+0700", "console",
             "s2spike", "bus", 150.0)  # fmt: skip
    run_json(runs, "2026-10-02-rdp-d16f-v2", "2026-10-02T12:00:00+0700", "rdp", "xfreerdp", None,
             375.9)  # fmt: skip
    bus = {"backend": "console", "client": {"name": "s2spike", "paint": "bus"}}
    assert qa.auto_offset_ms(bus, runs) == (113.9, "2026-10-03-console-26fa-v3b")
    x11 = {"backend": "console", "client": {"name": "s2spike", "paint": "x11"}}
    assert qa.auto_offset_ms(x11, runs) == (118.9, "2026-10-03-console-5c7e-v3")
    assert qa.auto_offset_ms({"backend": "rdp", "client": {"name": "xfreerdp"}}, runs)[0] == 375.9
    with pytest.raises(SystemExit):
        qa.auto_offset_ms({"backend": "console", "client": {"name": "moonlight-qt"}}, runs)


def test_each_backend_has_its_own_camera_file() -> None:
    from poring_dataset.projection import camera_file

    assert camera_file("rdp").name == "camera_rdp.json" and camera_file("rdp").exists()
    assert json.loads(camera_file("rdp").read_text())["backend"] == "rdp"
    assert camera_file("console").name == "camera_console.json"
    with pytest.raises(ValueError):
        camera_file("vnc")


def h264_session(tmp_path: Path) -> Path:
    """A tiny H.264 session as record_session --format h264 leaves it (Batt 2026-10-04: the
    default format): the stream, its index, the live decoder's checksums, packets, manifest."""
    import csv
    from fractions import Fraction

    av = pytest.importorskip("av")
    from poring_dataset import h264

    out = tmp_path / "h264sess"
    out.mkdir()
    enc = av.CodecContext.create("libx264", "w")
    enc.width, enc.height, enc.pix_fmt = 128, 96, "yuv420p"
    enc.time_base = Fraction(1, 30)
    enc.options = {"preset": "ultrafast", "tune": "zerolatency",
                   "x264-params": "keyint=10:min-keyint=10:repeat-headers=1:annexb=1"}  # fmt: skip
    aus = []
    for i in range(30):
        f = av.VideoFrame.from_ndarray(np.full((96, 128, 3), 40 + i * 5, np.uint8), format="rgb24")
        f.pts = i
        aus += [bytes(p) for p in enc.encode(f)]
    aus += [bytes(p) for p in enc.encode(None)]
    live = h264.new_decoder()
    with (out / "stream.idx.csv").open("w", newline="") as idx, \
            (out / "stream.hash.csv").open("w", newline="") as hsh:  # fmt: skip
        wi, wh = csv.writer(idx), csv.writer(hsh)
        wi.writerow(["au", "frame_id", "frame_number", "frame_type", "idr", "pts_ms", "offset",
                     "length", "receive_ms", "t_publish_ns"])  # fmt: skip
        wh.writerow(["frame_id", "crc32_adler32"])
        offset = 0
        for k, au in enumerate(aus):
            frame = list(live.decode(av.Packet(au)))[0]
            wi.writerow([k, 5000 + k, k, 0, int(k % 10 == 0), k * 33, offset, len(au), k,
                         T0 + k * 33_000_000])  # fmt: skip
            wh.writerow([5000 + k, h264.frame_digest(
                np.ascontiguousarray(frame.to_ndarray(format="bgra")))])  # fmt: skip
            offset += len(au)
    (out / "stream.h264").write_bytes(b"".join(aus))
    (out / "stream.done.json").write_text(json.dumps({"versions": h264.decoder_versions()}))
    with gzip.open(out / "packets.jsonl.gz", "wt") as fh:
        fh.write(json.dumps({"t_mono_ns": T0 - 1_000_000_000, "type": "map_change",
                             "map": "prt_fild08", "x": 170, "y": 375}) + "\n")  # fmt: skip
    write_manifest(out, {"session_id": "s264", "backend": "console", "format": "h264",
                         "game_region": [8, 8, 64, 48], "shards": [],
                         "freezes": {"spans_ns": []}})  # fmt: skip
    return out


def test_an_h264_session_exports_like_a_png_one(
    qa: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["qa_export.py", str(h264_session(tmp_path)), "--max", "4",
                                      "--offset-ms", "120"])  # fmt: skip
    assert qa.main() == 0
    bundle = tmp_path / "bundles" / "s264"
    labels = json.loads((bundle / "labels.json").read_text())
    ids = [f["frame_id"] for f in labels["frames"]]
    assert len(ids) == 4 and ids == sorted(ids) and all(5000 <= i < 5030 for i in ids)
    from poring_dataset.shards import decode_png

    img = decode_png((bundle / labels["frames"][0]["file"]).read_bytes())
    assert img.shape[:2] == (48, 64)  # the GAME_REGION crop, as PNG sessions export


def test_mark_gold_marks_exactly_one_exported_session(qa: ModuleType, tmp_path: Path) -> None:
    """2026-10-04 and 10-05: the B6 hand-check was twice done on the wrong session, because /qa
    opened on the newest one. The gold mark makes /qa open on the gold set."""
    index = tmp_path / "index.json"
    sessions = [{"id": "a", "title": "a", "frames": 1}, {"id": "b", "title": "b", "frames": 1}]
    index.write_text(json.dumps({"sessions": sessions}))
    qa.mark_gold(index, "a")
    got = json.loads(index.read_text())["sessions"]
    assert [(s["id"], s["gold"]) for s in got] == [("a", True), ("b", False)]
    with pytest.raises(SystemExit, match="not exported"):
        qa.mark_gold(index, "zzz")
