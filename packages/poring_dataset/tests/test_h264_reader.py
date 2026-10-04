"""The H.264 dataset reader (Batt 2026-10-04: H.264 is the default dataset format): GOP decoding,
clips, freeze spans, the per-frame checksum and the decoder-build check, on a tiny synthetic
session encoded here with libx264 (the PyAV wheel bundles it)."""

import csv
import json
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

av = pytest.importorskip("av")
if "libx264" not in av.codecs_available:  # pragma: no cover -- the wheel bundles it today
    pytest.skip("no libx264 encoder", allow_module_level=True)

from poring_dataset import h264  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
W, H, N, KEYINT = 128, 96, 40, 10
REGION = [8, 8, 64, 48]
T0, DT = 1_000_000_000_000, 33_000_000
X264 = f"keyint={KEYINT}:min-keyint={KEYINT}:repeat-headers=1:annexb=1"


def encode(n: int = N) -> list[bytes]:
    enc = av.CodecContext.create("libx264", "w")
    enc.width, enc.height, enc.pix_fmt = W, H, "yuv420p"
    enc.time_base = Fraction(1, 30)
    enc.options = {"preset": "ultrafast", "tune": "zerolatency",
                   "x264-params": X264}  # fmt: skip
    aus = []
    for i in range(n):
        img = np.zeros((H, W, 3), np.uint8)
        img[:, :, 0] = (np.arange(W)[None, :] * 2 + i * 9) % 256
        img[10 + i % 40 : 30 + i % 40, 20:60] = 255
        f = av.VideoFrame.from_ndarray(img, format="rgb24")
        f.pts = i
        aus += [bytes(p) for p in enc.encode(f)]
    aus += [bytes(p) for p in enc.encode(None)]
    return aus


def make_session(tmp: Path, *, freezes: list[list[int]] | None = None,
                 versions: dict[str, str] | None = None) -> Path:  # fmt: skip
    """What record_session --format h264 leaves: the stream, its index, the live checksums."""
    d = tmp / "20261005T090000-console-synthetic"
    d.mkdir()
    aus = encode()
    live = h264.new_decoder()
    rows, hashes, offset = [], {}, 0
    for k, au in enumerate(aus):
        out = list(live.decode(av.Packet(au)))
        fid = 1000 + k
        idr = 5 in [b & 0x1F for b in _nal_heads(au)]
        rows.append([k, fid if out else -1, k, int(idr), int(idr), k * 33, offset, len(au), k,
                     T0 + k * DT])  # fmt: skip
        if out:
            hashes[fid] = h264.frame_digest(np.ascontiguousarray(out[0].to_ndarray(format="bgra")))
        offset += len(au)
    (d / "stream.h264").write_bytes(b"".join(aus))
    with (d / "stream.idx.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["au", "frame_id", "frame_number", "frame_type", "idr", "pts_ms", "offset",
                    "length", "receive_ms", "t_publish_ns"])  # fmt: skip
        w.writerows(rows)
    with (d / "stream.hash.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["frame_id", "crc32_adler32"])
        w.writerow([999, "0000000000000000"])  # decoded before the first IDR: no unit (ignored)
        w.writerows(hashes.items())
    (d / "stream.done.json").write_text(
        json.dumps({"versions": versions or h264.decoder_versions()})
    )
    (d / "manifest.json").write_text(json.dumps({
        "format": "h264", "game_region": REGION,
        "freezes": {"spans_ns": freezes or []},
    }))  # fmt: skip
    return d


def _nal_heads(au: bytes) -> list[int]:
    out, i = [], 0
    while (j := au.find(b"\x00\x00\x01", i)) >= 0 and j + 3 < len(au):
        out.append(au[j + 3])
        i = j + 3
    return out


def test_frames_decode_by_gop_crop_and_verify(tmp_path: Path) -> None:
    s = h264.H264Session(make_session(tmp_path))
    ids = s.frame_ids
    assert len(ids) == N and s.usable() == ids
    picked = [ids[3], ids[17], ids[18], ids[39]]  # three GOPs
    got = list(s.frames(picked))
    assert [m["frame_id"] for m, _ in got] == picked
    assert all(m["crc_ok"] for m, _ in got)
    _, img = got[0]
    assert img.shape == (REGION[3], REGION[2], 3) and img.dtype == np.uint8
    full = next(iter(s.frames([ids[3]], crop=False)))[1]
    assert full.shape == (H, W, 4)
    assert np.array_equal(full[8:56, 8:72, :3], img)  # the crop is the GAME_REGION


def test_a_clip_is_consecutive_frames(tmp_path: Path) -> None:
    s = h264.H264Session(make_session(tmp_path))
    clip = s.clip(s.frame_ids[7], 6)  # crosses the IDR at index 10
    assert [m["frame_id"] for m, _ in clip] == s.frame_ids[7:13]
    assert [m["idr"] for m, _ in clip] == [False, False, False, True, False, False]


def test_freeze_spans_and_sampling(tmp_path: Path) -> None:
    span = [T0 + 20 * DT, T0 + 21 * DT]  # a stall between frames 20 and 21
    s = h264.H264Session(make_session(tmp_path, freezes=[span]))
    usable = s.usable()
    assert s.frame_ids[20] not in usable and s.frame_ids[21] not in usable
    assert len(usable) == N - 2
    sample = s.sample(5)
    assert len(sample) == 5 and sample == sorted(sample) and all(f in usable for f in sample)


def test_a_changed_frame_or_another_decoder_build_is_refused(tmp_path: Path) -> None:
    d = make_session(tmp_path)
    s = h264.H264Session(d)
    s.hashes[s.frame_ids[5]] = "ffffffffffffffff"
    with pytest.raises(h264.DeterminismError, match="checksum"):
        list(s.frames([s.frame_ids[5]]))
    other = json.loads((d / "stream.done.json").read_text())
    other["versions"]["libavcodec"] = "62.0.0"
    (d / "stream.done.json").write_text(json.dumps(other))
    with pytest.raises(h264.DecoderMismatch, match="libavcodec"):
        h264.H264Session(d)
    assert h264.H264Session(d, check_versions=False).frame_ids  # an explicit opt-out


def test_the_digest_is_the_live_clients_own() -> None:
    sys.path.insert(0, str(ROOT / "services" / "gamestream"))
    from s2spike.h264rec import frame_digest as live

    data = np.arange(97, dtype=np.uint8).repeat(11)
    assert h264.frame_digest(data) == live(data)


def test_format_detection(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(json.dumps({"shards": []}))
    assert h264.session_format(tmp_path) == "png"  # recorder v3: no "format" key


def test_dataset_check_judges_a_whole_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "dataset_check", ROOT / "scripts" / "dataset_check.py"
    )
    assert spec and spec.loader
    dc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dc)
    monkeypatch.setattr(dc, "OUT", tmp_path / "out")
    d = make_session(tmp_path)
    assert dc.main([str(d)]) == 0
    report = json.loads((tmp_path / "out" / f"{d.name}.check.json").read_text())
    assert (report["compared"], report["identical"], report["mismatched"]) == (N, N, 0)
    assert report["deterministic"] and report["complete"]
    assert not (d / "stream.check.json").exists()  # never writes into the session dir
    lines = (d / "stream.hash.csv").read_text().splitlines()
    lines[5] = lines[5].split(",")[0] + ",ffffffffffffffff"
    (d / "stream.hash.csv").write_text("\n".join(lines) + "\n")
    assert dc.main([str(d)]) == 1
