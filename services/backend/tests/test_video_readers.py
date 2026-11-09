"""ADR-0024 (stage 3 of docs/planning/gpu-recording.md): the session readers on an RDP VIDEO session
(video.hevc + video.idx.csv, no shards) give the frames they give on its PNG twin -- the same frame
ids, the same capture times, the pixels within the codec's loss -- and the studies that fit pixel
cues refuse it. Synthetic twins only: the recorder's ShardWriter for PNG, a CPU stand-in of the
sidecar's stream (libx265 Main 4:4:4 10, all-intra, pc / bt709, AUDs) for the video. No NAS, no
GPU, no client."""

from __future__ import annotations

import csv
import gzip
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest

av = pytest.importorskip("av")
if "libx265" not in av.codecs_available:  # pragma: no cover -- the wheel bundles it today
    pytest.skip("no libx265 encoder", allow_module_level=True)

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from poring_dataset import frames as fr  # noqa: E402
from poring_dataset.shards import ShardWriter, write_manifest  # noqa: E402

W, H, N = 64, 48, 6
T0 = 2_635_688_478_193_796
DROPPED = (3,)  # a frame the encoder's queue could not take: in the PNG twin, not in the video


def picture(i: int) -> np.ndarray:
    img = np.zeros((H, W, 3), np.uint8)
    img[..., 0] = (np.arange(W)[None, :] * 3 + 10 * i) % 256
    img[..., 1] = (np.arange(H)[:, None] * 4) % 256
    img[..., 2] = 180
    img[8:18, (4 * i) % 50 : (4 * i) % 50 + 10] = (20, 230, 40)
    return img


def _manifest(sid: str, fmt: str, **kw: Any) -> dict[str, Any]:
    return {"session_id": sid, "format": fmt, "backend": "rdp", "recorder_version": 7,
            "game_region": [80, 77, W, H], "server": "lab-rathena", "t0_mono_ns": T0,
            "t1_mono_ns": T0 + N * 10**9, **kw}  # fmt: skip


def png_twin(root: Path) -> Path:
    d = root / "20261109T080000-rdp-png"
    w = ShardWriter(d, max_bytes=8_000)  # several shards
    for i in range(N):
        if i not in DROPPED:
            w.add(i, T0 + i * 10**9, picture(i), t_wall=f"w{i}", bus_frame_id=-1, source="x11")
    w.close()
    write_manifest(d, _manifest(d.name, "png", shards=w.shards, frames=w.frames))
    (d / "packets.jsonl.gz").write_bytes(gzip.compress(b""))
    return d


def video_session(root: Path) -> Path:
    """What record_session --format vpp-hevc444-10-q20 leaves (stage 3)."""
    d = root / "20261109T080000-rdp-video"
    d.mkdir(parents=True)
    fed = [i for i in range(N) if i not in DROPPED]
    params = "keyint=1:min-keyint=1:scenecut=0:qp=4:pools=2:frame-threads=1:log-level=error:aud=1"
    with av.open(str(d / fr.VIDEO_FILE), "w", format="hevc") as cont:
        st = cont.add_stream("libx265", rate=1, options={"x265-params": params,
                                                           "preset": "ultrafast"})  # fmt: skip
        st.width, st.height, st.pix_fmt = W, H, "yuv444p10le"
        st.codec_context.color_range, st.codec_context.colorspace = 2, 1
        for i in fed:
            vf = av.VideoFrame.from_ndarray(picture(i), format="bgr24")
            vf = vf.reformat(format="yuv444p10le", dst_colorspace="ITU709",
                             dst_color_range="JPEG")  # fmt: skip
            vf.color_range, vf.colorspace = 2, 1
            for pkt in st.encode(vf):
                cont.mux(pkt)
        for pkt in st.encode(None):
            cont.mux(pkt)
    with (d / fr.VIDEO_INDEX).open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([*fr.INDEX_FIELDS, *fr.EXTRA_FIELDS])
        k = 0
        for i in range(N):
            if i in DROPPED:
                w.writerow([i, T0 + i * 10**9, -1, "dropped_queue_full", "", "", f"w{i}", -1,
                            "x11"])  # fmt: skip
            else:
                w.writerow([i, T0 + i * 10**9, k, "fed", 1, 2, f"w{i}", -1, "x11"])
                k += 1
    (d / fr.VIDEO_LOG).write_text("stub\n")
    write_manifest(d, _manifest(d.name, fr.VIDEO_FORMAT, shards=[], frames=len(fed), kept=N,
                                video={"arm": fr.VIDEO_FORMAT, "status": "ok",
                                       "fed": len(fed)}))  # fmt: skip
    (d / "packets.jsonl.gz").write_bytes(gzip.compress(b""))
    return d


def psnr(a: np.ndarray, b: np.ndarray) -> float:
    mse = float(np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2))
    return 99.0 if mse == 0 else 10 * np.log10(255.0**2 / mse)


@pytest.fixture
def twins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    monkeypatch.delenv(fr.SOURCE_ENV, raising=False)
    return png_twin(tmp_path), video_session(tmp_path)


KEPT = [i for i in range(N) if i not in DROPPED]


def _close(img: np.ndarray, fid: int) -> bool:
    return img.shape == (H, W, 3) and psnr(img, picture(fid)) > 38


# --- the generic readers --------------------------------------------------------------------------


@dataclass(frozen=True)
class FakeBox:
    x0: float
    y0: float
    x1: float
    y1: float
    score: float
    cls: str


class FakeDetector:
    def __init__(self) -> None:
        self.last_ms = 1.0
        self.seen: list[np.ndarray] = []

    def detect(self, img: Any) -> list[FakeBox]:
        self.seen.append(np.asarray(img))
        return [FakeBox(1.0, 2.0, 3.0, 4.0, 0.9, "monster")]


def test_recorder_boxes_predicts_on_either_layout(twins: tuple[Path, Path], tmp_path: Path) -> None:
    import recorder_boxes as rb

    rows = {}
    for d in twins:
        manifest = fr.load_manifest(d)
        assert rb.is_session(d)
        det = FakeDetector()
        out = tmp_path / f"{d.name}.jsonl"
        counts = rb.predict(rb.session_frames(d, manifest), det, out)
        assert counts["new_rows"] == len(KEPT)
        rows[d.name] = [(r["t"], r["frame_id"]) for r in rb.read_rows(out)]
        assert all(_close(img, fid) for img, fid in zip(det.seen, KEPT, strict=True))
        resumed = rb.predict(rb.session_frames(d, manifest), FakeDetector(), out,
                             done={KEPT[0]})  # fmt: skip
        assert resumed["skipped_done"] == 1  # a done frame is skipped, never decoded
    png, video = (rows[d.name] for d in twins)
    assert png == video == [(T0 + i * 10**9, i) for i in KEPT]
    with pytest.raises(fr.FrameSourceError, match="no PNG shards"):
        list(rb.iter_session(twins[1], fr.load_manifest(twins[1])))


def test_qa_export_and_build_frame_cache_read_the_same_frames(twins: tuple[Path, Path]) -> None:
    import build_frame_cache as bfc
    import qa_export

    for d in twins:
        manifest = fr.load_manifest(d)
        got = list(qa_export.session_frames(d, manifest, every=2, limit=10))
        assert [m["frame_id"] for m, _ in got] == KEPT[::2]
        assert all(_close(img, m["frame_id"]) for m, img in got)
        cache = list(bfc.session_frames(d, manifest, every=15, every_png=2))
        times = list(bfc.recorded_times(d, manifest, every=15, every_png=2))
        assert [(int(m["frame_id"]), int(m["t_mono_ns"])) for m, _ in cache] == times
        assert times == [(i, T0 + i * 10**9) for i in KEPT[::2]]


def test_the_index_and_peek_readers(twins: tuple[Path, Path]) -> None:
    import detector_vs_packets as dv
    import label_quality as lq
    import labels_v2 as tool
    import m4_validate as m4
    import map_labels as ml

    for d in twins:
        manifest = fr.load_manifest(d)
        dv.check_session({**manifest, "game_region": [80, 77, 1280, 720]})
        refs = ml.png_index(d, manifest)
        assert [r.frame_id for r in refs] == KEPT
        assert all(_close(ml.read_png(r), r.frame_id) for r in refs)
        shard = tool.shard_frames(d, every=2)
        assert [t for t, _ in shard] == [T0 + i * 10**9 for i in KEPT[::2]]
        assert all(ref.split("@")[0].endswith((".tar", ".hevc")) for _t, ref in shard)
        for (t, ref), fid in zip(shard, KEPT[::2], strict=True):
            img = np.asarray(tool.open_frame(ref).convert("RGB"))[:, :, ::-1]
            assert _close(img, fid) and t == T0 + fid * 10**9
        for at, fid in ((2.9, 2), (3.2, 4)):  # 3 was dropped: the nearest kept frame
            t, rgb = lq.session_frame(d, at)
            assert t == T0 + fid * 10**9 and _close(np.ascontiguousarray(rgb[:, :, ::-1]), fid)
        s = m4.PngSession(d, manifest)
        assert s.usable() == KEPT and [u.t_ns for u in s.units] == [T0 + i * 10**9 for i in KEPT]
        ((meta, img),) = list(s.frames([5]))
        assert meta["frame_id"] == 5 and _close(img, 5)
    assert "hevc" in tool.shard_frames(twins[1])[0][1]


def test_a_stage_2_session_is_read_as_its_video_twin_when_asked(
        twins: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    """Stage 4's check: every reader run on a stage-2 session's PNG and then on its video twin
    (PORING_FRAME_SOURCE=video), the two outputs compared."""
    import qa_export

    png, video = twins
    for name in (fr.VIDEO_FILE, fr.VIDEO_INDEX):
        (png / name).write_bytes((video / name).read_bytes())
    manifest = fr.load_manifest(png)
    manifest["video"] = {"arm": fr.VIDEO_FORMAT, "status": "ok"}
    write_manifest(png, manifest)
    lossless = list(qa_export.session_frames(png, manifest, every=1, limit=10))
    monkeypatch.setenv(fr.SOURCE_ENV, "video")
    twin = list(qa_export.session_frames(png, manifest, every=1, limit=10))
    assert [m["frame_id"] for m, _ in lossless] == [m["frame_id"] for m, _ in twin] == KEPT
    for (_a, x), (_b, y) in zip(lossless, twin, strict=True):
        assert np.array_equal(x, picture(_a["frame_id"])) and psnr(x, y) > 38


# --- the studies that fit cues refuse a video recording -------------------------------------------


def test_cue_studies_refuse_a_video_recording(twins: tuple[Path, Path],
                                              monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    import cursor_unknown as cu
    import miss_cue as mc
    import mvp_watch_study as mws
    import target_items as ti

    png, video = twins
    vm = fr.load_manifest(video)
    with pytest.raises(SystemExit, match="mvp_watch_study: .*--format png"):
        mws.png_index(video, vm)
    assert [r.frame_id for r in mws.png_index(png, fr.load_manifest(png))] == KEPT
    with pytest.raises(SystemExit, match="cursor_unknown: .*PNG REQUIRED"):
        cu._frame_index(video)
    monkeypatch.setattr(ti, "DATASETS", video.parent)
    with pytest.raises(SystemExit, match="target_items: "):
        ti.build_index(video.name, out=video.parent / "out")
    monkeypatch.setattr(mc, "rec_dir", lambda sid: video)
    monkeypatch.setattr(mc, "CACHE", video.parent / "cache")
    with pytest.raises(SystemExit, match="miss_cue: "):
        mc.shard_index(video.name)


def test_media_rec_check_refuses_a_video_only_session(twins: tuple[Path, Path],
                                                      tmp_path: Path) -> None:  # fmt: skip
    import media_rec

    with pytest.raises(SystemExit, match="has none"):
        media_rec.main(["check", str(twins[1]), "--map", "m", "--out", str(tmp_path / "c.json"),
                        "--no-detector"])  # fmt: skip


def test_dataset_check_verifies_a_video_session(twins: tuple[Path, Path]) -> None:
    import dataset_check

    rep = dataset_check.check(twins[1])
    assert rep["ok"] is True and rep["decoded_alone"] == len(KEPT)
    assert rep["by_status"] == {"fed": len(KEPT), "dropped_queue_full": 1}
    assert dataset_check.verdict([rep]) == 0
    stream = twins[1] / fr.VIDEO_FILE
    last = fr.stream_access_units(stream)[-1][0]
    stream.write_bytes(stream.read_bytes()[: last + 20])  # the last unit's headers, no picture
    bad = dataset_check.check(twins[1])
    assert bad["ok"] is False and dataset_check.verdict([bad]) == 1
    assert json.loads(json.dumps(bad))  # a plain report (the results file)
