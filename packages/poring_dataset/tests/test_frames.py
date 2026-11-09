"""poring_dataset.frames (ADR-0024): one API over a recorded session's frames, PNG shards or the
HEVC video. Synthetic sessions only: the recorder's own ShardWriter for PNG, and a CPU-encoded
stand-in of the sidecar's stream for video (libx265 Main 4:4:4 10, all-intra, tagged pc / bt709,
with and without access unit delimiters -- the GPU encoder writes them, ``-aud 1``)."""

from __future__ import annotations

import csv
import json
import tarfile
from pathlib import Path
from typing import Any

import numpy as np
import pytest

av = pytest.importorskip("av")
if "libx265" not in av.codecs_available:  # pragma: no cover -- the wheel bundles it today
    pytest.skip("no libx265 encoder", allow_module_level=True)

from poring_dataset import frames as fr  # noqa: E402
from poring_dataset.shards import ShardWriter, write_manifest  # noqa: E402

W, H = 64, 48
T0 = 2_635_688_478_193_796  # a real CLOCK_MONOTONIC magnitude
SID = "20261109T070000-rdp-frames"


def picture(i: int) -> np.ndarray:
    """A small BGR frame: a gradient, a moving block, three distinct channels."""
    img = np.zeros((H, W, 3), np.uint8)
    img[..., 0] = (np.arange(W)[None, :] * 3 + 10 * i) % 256
    img[..., 1] = (np.arange(H)[:, None] * 4) % 256
    img[..., 2] = 180
    img[8 : 8 + 10, (4 * i) % 50 : (4 * i) % 50 + 10] = (20, 230, 40)
    return img


def encode(path: Path, pics: list[np.ndarray], *, aud: bool = True, range_: int = 2,
           matrix: int = 1) -> None:  # fmt: skip
    """The sidecar's stream, on the CPU: every frame an IDR, 4:4:4 10-bit, BT.709 full range."""
    params = "keyint=1:min-keyint=1:scenecut=0:qp=4:pools=2:frame-threads=1:log-level=error"
    if aud:
        params += ":aud=1"
    with av.open(str(path), "w", format="hevc") as cont:
        st = cont.add_stream("libx265", rate=1, options={"x265-params": params,
                                                           "preset": "ultrafast"})  # fmt: skip
        st.width, st.height, st.pix_fmt = pics[0].shape[1], pics[0].shape[0], "yuv444p10le"
        st.codec_context.color_range, st.codec_context.colorspace = range_, matrix
        for img in pics:
            vf = av.VideoFrame.from_ndarray(np.ascontiguousarray(img), format="bgr24")
            vf = vf.reformat(format="yuv444p10le", dst_colorspace="ITU709",
                             dst_color_range="JPEG")  # fmt: skip
            vf.color_range, vf.colorspace = range_, matrix
            for pkt in st.encode(vf):
                cont.mux(pkt)
        for pkt in st.encode(None):
            cont.mux(pkt)


def video_session(root: Path, n: int = 6, *, dropped: tuple[int, ...] = (2,), aud: bool = True,
                  **enc: Any) -> Path:  # fmt: skip
    """What record_session --format vpp-hevc444-10-q20 leaves: the stream (the kept frames that
    were fed), its index (every kept frame, ``dropped`` ones not fed), the manifest."""
    d = root / SID
    d.mkdir(parents=True)
    fed = [i for i in range(n) if i not in dropped]
    encode(d / fr.VIDEO_FILE, [picture(i) for i in fed], aud=aud, **enc)
    with (d / fr.VIDEO_INDEX).open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([*fr.INDEX_FIELDS, *fr.EXTRA_FIELDS])
        k = 0
        for i in range(n):
            if i in dropped:
                w.writerow([i, T0 + i * 10**9, -1, "dropped_queue_full", "", "", f"w{i}", -1,
                            "x11"])  # fmt: skip
                continue
            w.writerow([i, T0 + i * 10**9, k, "fed", 5 + i, 9 + i, f"w{i}", -1, "x11"])
            k += 1
    (d / fr.VIDEO_LOG).write_text("stub\n")
    write_manifest(d, {"session_id": SID, "format": fr.VIDEO_FORMAT, "backend": "rdp",
                       "game_region": [0, 0, W, H], "shards": [], "frames": len(fed),
                       "video": {"arm": fr.VIDEO_FORMAT, "status": "ok",
                                 "fed": len(fed)}})  # fmt: skip
    return d


def png_session(root: Path, n: int = 5, max_bytes: int = 1 << 20) -> Path:
    d = root / SID.replace("frames", "png")
    w = ShardWriter(d, max_bytes=max_bytes)
    for i in range(n):
        w.add(i, T0 + i * 10**9, picture(i), t_wall=f"w{i}", bus_frame_id=-1, source="x11")
    w.close()
    write_manifest(d, {"session_id": d.name, "format": "png", "backend": "rdp",
                       "game_region": [0, 0, W, H], "shards": w.shards,
                       "frames": n})  # fmt: skip
    return d


def planes(f: Any) -> list[bytes]:
    """A decoded frame's planes, line padding dropped (2 bytes a 10-bit sample)."""
    return [bytes(np.frombuffer(memoryview(p), np.uint8).reshape(p.height, p.line_size)
                  [:, : p.width * 2]) for p in f.planes]  # fmt: skip


def psnr(a: np.ndarray, b: np.ndarray) -> float:
    mse = float(np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2))
    return 99.0 if mse == 0 else 10 * np.log10(255.0**2 / mse)


@pytest.fixture(autouse=True)
def _no_source_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(fr.SOURCE_ENV, raising=False)


# --- the stream's access units --------------------------------------------------------------------


@pytest.mark.parametrize("aud", [True, False])
def test_the_access_units_are_the_demuxers_own(tmp_path: Path, aud: bool) -> None:
    """The NAL-syntax split equals libavcodec's HEVC parser (the demuxer's packet positions), with
    the GPU encoder's AUDs and without them; every unit decodes ALONE to the frame the sequential
    decoder gives."""
    path = tmp_path / "s.hevc"
    encode(path, [picture(i) for i in range(5)], aud=aud)
    data = path.read_bytes()
    with av.open(str(path), format="hevc") as cont:
        want = [(p.pos, p.size) for p in cont.demux(cont.streams.video[0]) if p.size]
    got = fr.hevc_access_units(data)
    assert got == want and fr.stream_access_units(path) == got
    assert sum(n for _o, n in got) == len(data) and got[0][0] == 0
    seq = av.CodecContext.create("hevc", "r")
    frames = []
    for off, n in got:
        frames += seq.decode(av.Packet(data[off : off + n]))
    frames += seq.decode(None)
    assert len(frames) == 5
    for (off, n), f in zip(got, frames, strict=True):
        alone = fr.decode_hevc_frame(data[off : off + n])
        assert planes(alone) == planes(f)
    assert fr.hevc_access_units(b"") == [] and fr.hevc_access_units(b"\x00\x00\x00") == []


def test_a_cut_stream_keeps_its_whole_units(tmp_path: Path) -> None:
    path = tmp_path / "s.hevc"
    encode(path, [picture(i) for i in range(4)])
    aus = fr.stream_access_units(path)
    cut = aus[2][0] + 7  # inside the third unit's headers
    assert [a for a in fr.hevc_access_units(path.read_bytes()[:cut])][:2] == aus[:2]


# --- the video layout -----------------------------------------------------------------------------


def test_video_refs_follow_the_index_and_decode_alone(tmp_path: Path) -> None:
    d = video_session(tmp_path, 6, dropped=(2,))
    refs = fr.frame_refs(d)
    assert [r.frame_id for r in refs] == [0, 1, 3, 4, 5]  # the dropped frame is not served
    assert [r.t_mono_ns for r in refs] == [T0 + i * 10**9 for i in (0, 1, 3, 4, 5)]
    assert {r.kind for r in refs} == {"hevc"} and refs[0].offset == 0
    assert refs[1].meta() == {"frame_id": 1, "t_mono_ns": T0 + 10**9, "t_wall": "w1",
                              "bus_frame_id": -1, "source": "x11"}  # fmt: skip
    for r in refs:
        img = fr.read_ref(r, (W, H))
        assert img.shape == (H, W, 3) and img.dtype == np.uint8 and img.flags.c_contiguous
        assert psnr(img, picture(r.frame_id)) > 38  # qp 4, 4:4:4 10-bit: the frame it was fed
    assert fr.nearest_ref(refs, T0 + 2 * 10**9 + 1).frame_id == 3  # 2 was dropped: 3 is nearer
    assert fr.nearest_ref(refs, T0 + int(1.5e9)).frame_id == 1  # a tie: the earlier


def test_iter_frames_takes_every_nth_and_decodes_only_when_asked(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    d = video_session(tmp_path, 7, dropped=())
    calls = []
    real = fr.decode_hevc_au
    monkeypatch.setattr(fr, "decode_hevc_au", lambda *a, **k: calls.append(1) or real(*a, **k))
    got = list(fr.iter_frames(d, every=3))
    assert [m["frame_id"] for m, _ in got] == [0, 3, 6] and calls == []
    img = got[1][1]()
    assert calls == [1] and psnr(img, picture(3)) > 38
    assert [m["frame_id"] for m, _ in fr.iter_bgr(d)] == list(range(7))
    with pytest.raises(ValueError, match="every"):
        list(fr.iter_frames(d, every=0))


def test_a_short_stream_and_a_bad_frame_are_reported_never_served(tmp_path: Path) -> None:
    d = video_session(tmp_path, 5, dropped=())
    aus = fr.stream_access_units(d / fr.VIDEO_FILE)
    data = (d / fr.VIDEO_FILE).read_bytes()
    (d / fr.VIDEO_FILE).write_bytes(data[: aus[3][0]])  # the encoder stopped after 3 frames
    problems: list[str] = []
    refs = fr.frame_refs(d, cuts=problems)
    assert [r.frame_id for r in refs] == [0, 1, 2]
    assert problems == [f"{fr.VIDEO_FILE}: 2 fed frames past the stream's end (3 access units)"]
    rep = fr.verify_video(d)
    assert rep["ok"] is False and rep["decoded_alone"] == 3 and rep["fed"] == 5
    with pytest.raises(fr.VideoFrameError, match="does not decode|0 frames"):
        fr.decode_hevc_au(b"\x00\x00\x01\x46\x01\x50")  # an AUD alone: no picture


def test_a_frame_of_another_convention_or_size_is_refused(tmp_path: Path) -> None:
    d = video_session(tmp_path, 2, dropped=(), range_=1, matrix=6)  # tv / smpte170m
    ref = fr.frame_refs(d)[0]
    with pytest.raises(fr.VideoFrameError, match="range/matrix"):
        fr.read_ref(ref)
    d2 = video_session(tmp_path / "b", 2, dropped=())
    with pytest.raises(fr.VideoFrameError, match="not 1280x720"):
        fr.read_ref(fr.frame_refs(d2)[0], (1280, 720))
    rep = fr.verify_video(d2)
    assert rep["ok"] is True and rep["decoded_alone"] == rep["fed"] == rep["access_units"] == 2
    assert rep["by_status"] == {"fed": 2}


def test_an_index_whose_fed_rows_skip_a_position_is_refused(tmp_path: Path) -> None:
    d = video_session(tmp_path, 3, dropped=())
    rows = (d / fr.VIDEO_INDEX).read_text().splitlines()
    rows[2] = rows[2].replace(",1,fed,", ",2,fed,")
    (d / fr.VIDEO_INDEX).write_text("\n".join(rows) + "\n")
    with pytest.raises(fr.FrameSourceError, match="0..n-1"):
        fr.frame_refs(d)


# --- the PNG layout, through the same API ---------------------------------------------------------


def test_png_sessions_read_as_before(tmp_path: Path) -> None:
    d = png_session(tmp_path, 5, max_bytes=3_000)  # several shards
    manifest = fr.load_manifest(d)
    assert len(manifest["shards"]) > 1
    got = list(fr.iter_bgr(d))
    assert [m["frame_id"] for m, _ in got] == list(range(5))
    assert got[2][0] == {"frame_id": 2, "t_mono_ns": T0 + 2 * 10**9, "t_wall": "w2",
                         "bus_frame_id": -1, "source": "x11"}  # fmt: skip  # the json, whole
    for i, (_m, img) in enumerate(got):
        assert np.array_equal(img, picture(i))  # lossless
    refs = fr.frame_refs(d)
    assert [r.frame_id for r in refs] == list(range(5)) and {r.kind for r in refs} == {"png"}
    for r in refs:
        assert np.array_equal(fr.read_ref(r), picture(r.frame_id))
    assert [m["frame_id"] for m, _ in fr.iter_frames(d, every=2)] == [0, 2, 4]


def test_a_cut_png_shard_strict_or_tolerant(tmp_path: Path) -> None:
    d = png_session(tmp_path, 4)
    manifest = fr.load_manifest(d)
    shard = d / manifest["shards"][-1]
    with tarfile.open(shard) as tar:
        members = tar.getmembers()
    whole = shard.read_bytes()
    shard.write_bytes(whole[: members[4].offset_data + 10])  # frame 2's png cut
    cuts: list[str] = []
    assert [r.frame_id for r in fr.frame_refs(d, cuts=cuts)] == [0, 1]
    assert [m["frame_id"] for m, _ in fr.iter_frames(d, cuts=cuts)] == [0, 1]
    assert any("cut" in c or "unexpected" in c.lower() for c in cuts)
    with pytest.raises((tarfile.ReadError, EOFError, KeyError)):
        fr.frame_refs(d, strict=True)
    shard.write_bytes(whole)
    assert [r.frame_id for r in fr.frame_refs(d, strict=True)] == [0, 1, 2, 3]
    manifest["shards"].append("shard-000099.tar")
    cuts = []
    fr.frame_refs(d, manifest, cuts=cuts)
    assert cuts[-1] == "shard-000099.tar: missing"
    with pytest.raises(FileNotFoundError):
        fr.frame_refs(d, manifest, strict=True)


# --- which source ---------------------------------------------------------------------------------


def test_the_source_follows_the_format_and_the_override(tmp_path: Path,
                                                        monkeypatch: pytest.MonkeyPatch
                                                        ) -> None:  # fmt: skip
    v = video_session(tmp_path / "v", 3, dropped=())
    p = png_session(tmp_path / "p", 3)
    vm, pm = fr.load_manifest(v), fr.load_manifest(p)
    assert fr.frame_source(v, vm) == "video" and fr.frame_source(p, pm) == "png"
    with pytest.raises(fr.FrameSourceError, match="no PNG frames"):
        fr.frame_source(v, vm, "png")
    with pytest.raises(fr.FrameSourceError, match="no video stream"):
        fr.frame_source(p, pm, "video")
    with pytest.raises(fr.FrameSourceError, match="one of"):
        fr.frame_source(p, pm, "jpeg")
    with pytest.raises(fr.FrameSourceError, match="not a PNG or video"):
        fr.frame_source(p, {**pm, "format": "h264"})
    with pytest.raises(fr.FrameSourceError, match="has no PNG shards"):
        list(fr.iter_png_session(v, vm))
    # a stage-2 session (PNG + its video twin): PNG by default, the video when asked
    for name in (fr.VIDEO_FILE, fr.VIDEO_INDEX):
        (p / name).write_bytes((v / name).read_bytes())
    pm["video"] = {"arm": fr.VIDEO_FORMAT, "status": "ok"}
    write_manifest(p, pm)
    assert fr.frame_source(p, pm) == "png"
    monkeypatch.setenv(fr.SOURCE_ENV, "video")
    assert fr.frame_source(p, pm) == "video"
    refs = fr.frame_refs(p)
    assert {r.kind for r in refs} == {"hevc"} and len(refs) == 3


def test_cue_studies_refuse_a_video_recording(monkeypatch: pytest.MonkeyPatch) -> None:
    png = {"session_id": "a", "format": "png"}
    vid = {"session_id": "b", "format": fr.VIDEO_FORMAT}
    assert fr.png_required(png, "miss_cue") is None and fr.png_required({}, "x") is None
    why = fr.png_required(vid, "miss_cue")
    assert why is not None and "miss_cue: b" in why and "--format png" in why
    monkeypatch.setenv(fr.SOURCE_ENV, "video")  # a stage-2 session read as its twin: the parity run
    assert fr.png_required({**png, "video": {"status": "ok"}}, "miss_cue") is None
    assert fr.is_video(vid) and not fr.is_video(png) and not fr.is_video({})


def test_the_index_columns_are_the_recorders() -> None:
    import importlib.util
    import sys

    scripts = Path(__file__).resolve().parents[3] / "scripts"
    sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location("media_rec", scripts / "media_rec.py")
    assert spec and spec.loader
    mr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mr)
    assert mr.INDEX_FIELDS == fr.INDEX_FIELDS and mr.EXTRA_FIELDS == fr.EXTRA_FIELDS
    assert mr.ARM == fr.VIDEO_FORMAT
    assert json.dumps(fr.VIDEO_COLOR) == json.dumps(list(("ITU709", "JPEG")))
