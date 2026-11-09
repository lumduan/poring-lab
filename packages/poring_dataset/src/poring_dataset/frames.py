"""A recorded session's frames, whichever way they were stored (ADR-0024, Batt 2026-11-09: RDP
recordings are GPU-encoded HEVC video, no longer lossless PNG). OFFLINE ONLY, host side: PyAV
lives here and in the media images, never in vision (test_guards).

Two layouts of ``scripts/record_session.py`` (``--backend rdp``) are served:

    PNG      manifest ``format: png``: ``shard-NNNNNN.tar`` with ``<frame_id>.png`` (lossless) +
             ``<frame_id>.json`` {frame_id, t_mono_ns, t_wall, bus_frame_id, source}. A stage-2
             session (gpu-recording.md 9.1) is a PNG session with a video twin beside its shards.
    VIDEO    manifest ``format: vpp-hevc444-10-q20`` (VIDEO_FORMAT), no shards:
             ``video.hevc``    the sidecar's HEVC Main 4:4:4 10 elementary stream (Annex B), CQP 20,
                               ALL-INTRA: every access unit decodes by itself;
             ``video.idx.csv`` one row per kept frame: frame_id, t_mono_ns (the grab's, the
                               packets' clock), video_index (its access unit), status ("fed" = in
                               the stream), the write's start / end, and since stage 3 the PNG
                               record's own t_wall, bus_frame_id, source;
             ``video.ffmpeg.log`` the encoder's log.

THE API (one for both layouts; readers never look at the files themselves):

* ``frame_refs(session)`` -> [FrameRef] in frame order, read from the index only (tar headers and
  the json members; the CSV and one scan of the stream for its access units): no pixel decoded.
  A FrameRef has qa_export.JpegRef's fields (frame_id, t_mono_ns, shard, offset, size): the PNG
  member's bytes in its tar, or the access unit's bytes in ``video.hevc``.
* ``read_ref(ref)`` -> the frame as BGR uint8 (GAME_REGION, H x W x 3): one seek and read, then the
  PNG decoded, or the access unit decoded ALONE by a fresh decoder (stage 2's D1: alone and in
  sequence give the same planes on every frame) and converted with the declared convention
  (BT.709, full range; stage 2's F1: every frame signals it, and a frame that does not is refused).
* ``iter_frames(session, every=N)`` -> (meta, load) per N-th frame in recording order, ``load()``
  decoding it only when called; ``iter_bgr`` decodes each. PNG: the shards are STREAMED (one read,
  front to back, a cut shard keeps the frames before its cut and is reported in ``cuts``), and
  ``meta`` is the frame's json record; VIDEO: ``meta`` is the same record from the index row.
* ``nearest_ref(refs, t_ns)``: the frame captured nearest a time.
* ``frame_source(session, manifest)``: which layout serves the frames. ``auto`` (the default) is
  the manifest's format: a stage-2 session is read from its PNG (the reference). The environment
  variable PORING_FRAME_SOURCE=png|video overrides it, so a stage-2 session can be read from its
  VIDEO twin by any reader (stage 4: each reader checked on stage 2's session against its PNG).
* ``png_required(manifest, what)``: the reason a study that fits pixel cues or templates refuses
  a video recording (ADR-0024: PNG stays REQUIRED for them until each passes its own parity on
  decoded frames; record those sessions with ``--format png``).
* ``verify_video(session)``: every access unit decoded alone, its size, convention and row checked
  (dataset_check.py's pass for video sessions).

The access units are found by the stream's own NAL syntax (``hevc_access_units``, H.265 7.4.2.4.4,
the rule libavcodec's HEVC parser applies): no decoder, no demuxer, one ``find`` per NAL unit.
"""

from __future__ import annotations

import csv
import json
import mmap
import os
import tarfile
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from poring_dataset.shards import decode_png

VIDEO_FORMAT = "vpp-hevc444-10-q20"  # scripts/media_rec.ARM (gpu_rec_bench round 3's candidate)
VIDEO_FILE = "video.hevc"
VIDEO_INDEX = "video.idx.csv"
VIDEO_LOG = "video.ffmpeg.log"
# The convention the sidecar converts BGRA into (scale_vaapi out_color_matrix=bt709, out_range=full)
# and tags (-colorspace bt709 -color_range pc): swscale's names, as gpu_rec_bench.COLOR.
VIDEO_COLOR = ("ITU709", "JPEG")
VIDEO_VUI = (2, 1)  # (AVColorRange pc, AVColorSpace bt709): what every decoded frame must signal
SOURCES = ("auto", "png", "video")
SOURCE_ENV = "PORING_FRAME_SOURCE"
# video.idx.csv's columns: stage 2's six (scripts/media_rec.INDEX_FIELDS), then the PNG record's
# own fields (stage 3; absent in stage 2's index, read as missing)
INDEX_FIELDS = ("frame_id", "t_mono_ns", "video_index", "status", "write_start_ns", "write_end_ns")
EXTRA_FIELDS = ("t_wall", "bus_frame_id", "source")
FED = "fed"
# NAL unit types that open a new access unit when they follow a picture's slices (prefix NALs:
# VPS, SPS, PPS, AUD, prefix SEI, reserved 41-44 and 48-55); the rest (suffix SEI, EOS, EOB, filler,
# reserved) stay with the picture before them.
_AU_PREFIX = frozenset((32, 33, 34, 35, 39, *range(41, 45), *range(48, 56)))
_START = b"\x00\x00\x01"

BGR = npt.NDArray[np.uint8]
Loader = Callable[[], BGR]


class FrameSourceError(ValueError):
    """The session cannot serve frames from the source asked for (or at all)."""


class ShardCut(Exception):  # noqa: N818 -- recorder_boxes' name since 2026-11-05
    """A recorder shard ended mid-member (a recording stopped by its IO guard mid-write)."""


class VideoFrameError(RuntimeError):
    """An access unit did not decode to exactly one frame of the declared convention and size."""


@dataclass(frozen=True, slots=True)
class FrameRef:
    """One recorded frame and where its encoded bytes lie: a PNG member of a tar shard, or an
    access unit of ``video.hevc``. The fields are qa_export.JpegRef's (tools that read those take
    these); ``extra`` holds a video row's PNG-record fields (t_wall, bus_frame_id, source)."""

    frame_id: int
    t_mono_ns: int
    shard: Path
    offset: int
    size: int
    extra: tuple[tuple[str, Any], ...] = field(default=(), compare=False)

    @property
    def kind(self) -> str:
        return "hevc" if self.shard.suffix == ".hevc" else "png"

    def meta(self) -> dict[str, Any]:
        """The frame's record: frame_id, t_mono_ns and, for a video frame, its index row's
        PNG-record fields (a PNG frame's full record is its json member: iter_frames)."""
        return {"frame_id": self.frame_id, "t_mono_ns": self.t_mono_ns, **dict(self.extra)}


# --- which layout ---------------------------------------------------------------------------------


def load_manifest(session: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((session / "manifest.json").read_text())
    return data


def session_format(manifest: dict[str, Any]) -> str:
    """The manifest's format: ``png`` when it has none (recorder v1-3), ``h264`` (console),
    VIDEO_FORMAT (stage 3)."""
    return str(manifest.get("format") or "png")


def is_video(manifest: dict[str, Any]) -> bool:
    """A video-only recording (ADR-0024): its frames are in video.hevc, it has no PNG shards."""
    return session_format(manifest) == VIDEO_FORMAT


def has_video(session: Path, manifest: dict[str, Any]) -> bool:
    """The session holds a video stream and its index (video-only, or stage 2's twin)."""
    return (bool(manifest.get("video")) and (session / VIDEO_FILE).is_file()
            and (session / VIDEO_INDEX).is_file())  # fmt: skip


def frame_source(session: Path, manifest: dict[str, Any], source: str | None = None) -> str:
    """``png`` or ``video``: where this session's frames are read from. ``source`` (else
    $PORING_FRAME_SOURCE, else ``auto``): auto = the manifest's format (a stage-2 session's PNG
    is the reference); ``png`` / ``video`` must exist, else FrameSourceError."""
    want = source or os.environ.get(SOURCE_ENV) or "auto"
    if want not in SOURCES:
        raise FrameSourceError(f"frame source {want!r}: one of {SOURCES} (${SOURCE_ENV})")
    fmt = session_format(manifest)
    if fmt not in ("png", VIDEO_FORMAT):
        raise FrameSourceError(f"{session.name}: format {fmt!r} is not a PNG or video recording")
    if want == "auto":
        want = "video" if fmt == VIDEO_FORMAT else "png"
    if want == "png" and fmt == VIDEO_FORMAT:
        raise FrameSourceError(f"{session.name}: a video recording ({fmt}) has no PNG frames")
    if want == "video" and not has_video(session, manifest):
        raise FrameSourceError(f"{session.name}: no video stream ({VIDEO_FILE} + {VIDEO_INDEX} "
                               "and the manifest's video block)")  # fmt: skip
    return want


def png_required(manifest: dict[str, Any], what: str) -> str | None:
    """PURE: why ``what`` (a study that fits pixel cues or templates) refuses this session, or
    None. ADR-0024: PNG stays REQUIRED for those studies until each passes its own parity on
    decoded frames, so a VIDEO recording is refused, never read as an empty session (its manifest
    lists no shards). A stage-2 session keeps its PNG: it is served (read as its video twin only
    when PORING_FRAME_SOURCE=video asks, the parity run itself)."""
    if not is_video(manifest):
        return None
    return (f"{what}: {manifest.get('session_id') or manifest.get('sid')}: format "
            f"{session_format(manifest)}: this study fits pixel cues on lossless PNG frames "
            "(ADR-0024: PNG REQUIRED until it passes its own parity on decoded frames); record "
            "it with --format png")  # fmt: skip


# --- the PNG layout -------------------------------------------------------------------------------


def iter_png_shard(path: Path) -> Iterator[tuple[dict[str, Any], bytes]]:
    """(json record, PNG bytes) per frame of ONE recorder shard, in member order, the tar STREAMED
    (mode "r|": read once, front to back, nothing extracted). A frame is yielded once both of its
    members (``NNNNNNNNN.png``, ``NNNNNNNNN.json``) were read; the json's ``frame_id`` must be the
    member key's. A CUT shard raises ShardCut AFTER the complete frames before it: a member cut
    short, a member left without its pair, or no end-of-archive marker (two zero blocks) where
    the members end -- tarfile ends a stream at a cut header silently, so the marker is read.
    (recorder_boxes.iter_shard's reader, moved here 2026-11-09.)"""
    pending: dict[str, dict[str, bytes]] = {}
    end = 0
    try:
        with tarfile.open(path, mode="r|") as tar:
            for m in tar:
                if not m.isfile():
                    continue
                key, _, ext = m.name.partition(".")
                if ext not in ("png", "json"):
                    continue
                fh = tar.extractfile(m)
                assert fh is not None
                data = fh.read()
                if len(data) != m.size:
                    raise ShardCut(f"{path.name}: {m.name} cut at {len(data)} of {m.size} bytes")
                item = pending.setdefault(key, {})
                item[ext] = data
                if "png" in item and "json" in item:
                    del pending[key]
                    meta: dict[str, Any] = json.loads(item["json"])
                    if f"{int(meta['frame_id']):09d}" != key:
                        raise ValueError(f"{path.name}: {key}.json says frame {meta['frame_id']}")
                    yield meta, item["png"]
            end = tar.offset
    except (tarfile.ReadError, EOFError) as e:
        raise ShardCut(f"{path.name}: {e}") from e
    if pending:
        raise ShardCut(f"{path.name}: {sorted(pending)} without its pair (cut)")
    with path.open("rb") as fh:
        fh.seek(end)
        marker = fh.read(1024)
    if len(marker) < 1024 or marker.strip(b"\0"):
        raise ShardCut(f"{path.name}: no end-of-archive marker at byte {end} (cut)")


def iter_png_session(session: Path, manifest: dict[str, Any], cuts: list[str] | None = None,
                     *, strict: bool = False
                     ) -> Iterator[tuple[dict[str, Any], bytes]]:  # fmt: skip
    """(json record, PNG bytes) of every frame, shard by shard in the manifest's order. A missing
    shard or a cut is noted in ``cuts`` (when given) and the next shard follows; ``strict``: it
    raises (FileNotFoundError, ShardCut) after the frames before it."""
    if is_video(manifest):
        raise FrameSourceError(f"{manifest.get('session_id')}: a video recording has no PNG "
                               "shards (frames.iter_frames reads either)")  # fmt: skip
    for name in manifest.get("shards") or []:
        shard = session / str(name)
        if not shard.exists():
            if strict:
                raise FileNotFoundError(shard)
            if cuts is not None:
                cuts.append(f"{name}: missing")
            continue
        try:
            yield from iter_png_shard(shard)
        except ShardCut as e:
            if strict:
                raise
            if cuts is not None:
                cuts.append(str(e))


def png_refs(session: Path, manifest: dict[str, Any], *, strict: bool = False,
             cuts: list[str] | None = None) -> list[FrameRef]:  # fmt: skip
    """Every PNG frame's ref (tar headers and the json members only), in frame order; a frame's
    png and json may lie in two shards. ``strict`` (map_labels.png_index's rule): a cut or missing
    shard raises. Otherwise (mvp_watch_study's): the complete members before a cut are kept, a png
    whose bytes run past its file and a frame missing a member are dropped, the cut is noted."""
    pngs: dict[str, tuple[Path, int, int]] = {}
    metas: dict[str, dict[str, Any]] = {}
    for name in manifest.get("shards") or []:
        shard = session / str(name)
        if not shard.exists():
            if strict:
                raise FileNotFoundError(shard)
            if cuts is not None:
                cuts.append(f"{name}: missing")
            continue
        size = shard.stat().st_size
        try:
            with tarfile.open(shard) as tar:
                for m in tar:
                    key, _, ext = m.name.partition(".")
                    if ext == "png" and (strict or m.offset_data + m.size <= size):
                        pngs[key] = (shard, m.offset_data, m.size)
                    elif ext == "json":
                        fh = tar.extractfile(m)
                        assert fh is not None
                        metas[key] = json.loads(fh.read())
        except (tarfile.ReadError, EOFError, json.JSONDecodeError) as e:
            if strict:
                raise
            if cuts is not None:
                cuts.append(f"{name}: {e}")
    out = [FrameRef(int(metas[k]["frame_id"]), int(metas[k]["t_mono_ns"]), *pngs[k])
           for k in set(pngs) & set(metas)]  # fmt: skip
    return sorted(out, key=lambda r: r.frame_id)


# --- the video layout -----------------------------------------------------------------------------


def hevc_access_units(buf: Any) -> list[tuple[int, int]]:
    """PURE: (offset, length) of every access unit of an Annex-B HEVC stream (``bytes`` or an
    ``mmap``), in stream order. A new unit opens at a prefix NAL (VPS, SPS, PPS, AUD, prefix SEI,
    ...) or a slice whose first_slice_segment_in_pic_flag is set, once the unit before holds a
    picture's slice (H.265 7.4.2.4.4; libavcodec's hevc_parser splits the same way). A unit begins
    at its first NAL's start code, the zero_byte before a 4-byte start code included; the first
    unit begins at 0. Emulation prevention keeps 00 00 01 out of every NAL payload."""
    n = len(buf)
    starts: list[int] = []
    vcl = False  # the open unit holds a picture's slice
    i = buf.find(_START)
    while i >= 0 and i + 5 < n:
        nal = (buf[i + 3] >> 1) & 0x3F
        begin = i - 1 if i > 0 and buf[i - 1] == 0 else i
        if not starts:
            starts.append(0)
        if nal in _AU_PREFIX:
            if vcl:
                starts.append(begin)
                vcl = False
        elif nal < 32:  # a VCL NAL: its slice segment header's first bit
            if buf[i + 5] & 0x80 and vcl:
                starts.append(begin)
            vcl = True
        i = buf.find(_START, i + 3)
    if not starts:
        return []
    ends = [*starts[1:], n]
    return [(a, b - a) for a, b in zip(starts, ends, strict=True)]


def stream_access_units(path: Path) -> list[tuple[int, int]]:
    """hevc_access_units over a file, memory-mapped (the pages come and go with the page cache:
    no whole-stream copy in the process)."""
    if path.stat().st_size == 0:
        return []
    with path.open("rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        return hevc_access_units(mm)


def read_video_index(path: Path) -> list[dict[str, Any]]:
    """video.idx.csv's rows, numbers as ints (empty write times and missing columns -> None)."""
    with path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        row: dict[str, Any] = dict(r)
        for k in ("frame_id", "t_mono_ns", "video_index"):
            row[k] = int(r[k])
        for k in ("write_start_ns", "write_end_ns", "bus_frame_id"):
            v = r.get(k)
            row[k] = int(v) if v not in (None, "") else None
        for k in ("t_wall", "source"):
            row[k] = r.get(k) or None
        out.append(row)
    return out


def video_refs(session: Path, manifest: dict[str, Any] | None = None,
               problems: list[str] | None = None, *,
               aus: list[tuple[int, int]] | None = None) -> list[FrameRef]:  # fmt: skip
    """Every frame of the session's video, in frame order: the index's ``fed`` rows, each matched
    to its access unit by ``video_index``. A fed row past the stream's end (the encoder stopped
    early) and access units past the index are left out and noted in ``problems``. ``aus``: the
    stream's access units when already found (else one scan)."""
    stream = session / VIDEO_FILE
    rows = read_video_index(session / VIDEO_INDEX)
    if aus is None:
        aus = stream_access_units(stream) if stream.exists() else []
    fed = sorted((r for r in rows if r["status"] == FED and r["video_index"] >= 0),
                 key=lambda r: int(r["video_index"]))  # fmt: skip
    if [r["video_index"] for r in fed] != list(range(len(fed))):
        raise FrameSourceError(f"{session.name}: {VIDEO_INDEX}'s fed rows are not the stream "
                               "positions 0..n-1 in order")  # fmt: skip
    out = []
    for r in fed:
        k = int(r["video_index"])
        if k >= len(aus):
            continue
        extra = tuple((f, r[f]) for f in EXTRA_FIELDS if r.get(f) is not None)
        out.append(FrameRef(int(r["frame_id"]), int(r["t_mono_ns"]), stream, *aus[k], extra))
    if problems is not None:
        if len(fed) > len(aus):
            problems.append(f"{VIDEO_FILE}: {len(fed) - len(aus)} fed frames past the stream's "
                            f"end ({len(aus)} access units)")  # fmt: skip
        if len(aus) > len(fed):
            problems.append(f"{VIDEO_FILE}: {len(aus) - len(fed)} access units past the index")
    return sorted(out, key=lambda r: r.frame_id)


def decode_hevc_au(data: bytes, *, size: tuple[int, int] | None = None,
                   threads: int = 1) -> BGR:  # fmt: skip
    """One access unit decoded ALONE (a fresh decoder, flushed) -> BGR with VIDEO_COLOR, the host
    decode path of stage 2's check (PyAV software, one thread, swscale). It must give exactly one
    frame, signal VIDEO_VUI (pc, bt709) and, with ``size`` (w, h), be that size."""
    av_frame = decode_hevc_frame(data, threads=threads)
    vui = (int(av_frame.color_range), int(av_frame.colorspace))
    if vui != VIDEO_VUI:
        raise VideoFrameError(f"the frame signals range/matrix {vui}, not {VIDEO_VUI} (pc, bt709)")
    if size is not None and (av_frame.width, av_frame.height) != tuple(size):
        raise VideoFrameError(f"the frame is {av_frame.width}x{av_frame.height}, not "
                              f"{size[0]}x{size[1]}")  # fmt: skip
    return to_bgr(av_frame)


def decode_hevc_frame(data: bytes, *, threads: int = 1) -> Any:
    """One access unit through a fresh HEVC decoder (flushed) -> its one PyAV frame."""
    import av

    ctx = av.CodecContext.create("hevc", "r")
    ctx.thread_count = threads
    try:
        got = list(ctx.decode(av.Packet(data))) + list(ctx.decode(None))
    except av.error.FFmpegError as e:
        raise VideoFrameError(f"the access unit does not decode: {e}") from e
    if len(got) != 1:
        raise VideoFrameError(f"the access unit decoded to {len(got)} frames, not 1")
    return got[0]


def to_bgr(av_frame: Any, color: tuple[str, str] = VIDEO_COLOR) -> BGR:
    """YUV -> BGR with ``color`` (gpu_rec_bench.to_bgr: swscale through PyAV)."""
    out = av_frame.reformat(format="bgr24", src_colorspace=color[0], src_color_range=color[1])
    return np.ascontiguousarray(out.to_ndarray())


# --- the API --------------------------------------------------------------------------------------


def frame_refs(session: Path, manifest: dict[str, Any] | None = None, *,
               source: str | None = None, strict: bool = False,
               cuts: list[str] | None = None) -> list[FrameRef]:  # fmt: skip
    """Every frame's ref in frame order, from the index only (see the module doc). ``strict``
    (PNG): a cut shard raises instead of keeping the frames before it."""
    manifest = manifest if manifest is not None else load_manifest(session)
    if frame_source(session, manifest, source) == "video":
        return video_refs(session, manifest, cuts)
    return png_refs(session, manifest, strict=strict, cuts=cuts)


def read_bytes(ref: FrameRef) -> bytes:
    """The ref's encoded bytes (one seek and read)."""
    with ref.shard.open("rb") as fh:
        fh.seek(ref.offset)
        data = fh.read(ref.size)
    if len(data) != ref.size:
        raise ValueError(f"{ref.shard}@{ref.offset}: short read ({len(data)} of {ref.size} bytes)")
    return data


def read_ref(ref: Any, size: tuple[int, int] | None = None) -> BGR:
    """A FrameRef (or anything with its fields: qa_export.JpegRef) as BGR uint8: the PNG member
    decoded, or the access unit decoded alone (decode_hevc_au; ``size`` (w, h) checked)."""
    data = read_bytes(ref)
    if Path(ref.shard).suffix == ".hevc":
        return decode_hevc_au(data, size=size)
    img = decode_png(data)
    if img.ndim != 3 or img.shape[2] != 3:
        raise ValueError(f"{ref.shard}@{ref.offset}: not an RGB PNG ({img.shape})")
    return img


def iter_frames(session: Path, manifest: dict[str, Any] | None = None, *, every: int = 1,
                source: str | None = None, cuts: list[str] | None = None, strict: bool = False
                ) -> Iterator[tuple[dict[str, Any], Loader]]:  # fmt: skip
    """Every ``every``-th frame in recording order as (meta, load): ``load()`` decodes it (BGR).
    PNG: the shards are streamed once (a frame not taken is never decoded; ``cuts`` / ``strict``
    as iter_png_session); ``meta`` is its json record. VIDEO: ``meta`` is its index row's record;
    each ``load`` reads and decodes its own access unit (the stream's problems go to ``cuts``; a
    stream cut short by its encoder is served up to its cut, ``strict`` or not)."""
    if every < 1:
        raise ValueError("every: 1 or more")
    manifest = manifest if manifest is not None else load_manifest(session)
    if frame_source(session, manifest, source) == "video":
        size = _region_size(manifest)
        for i, ref in enumerate(video_refs(session, manifest, cuts)):
            if not i % every:
                yield ref.meta(), _video_loader(ref, size)
        return
    for i, (meta, png) in enumerate(iter_png_session(session, manifest, cuts, strict=strict)):
        if not i % every:
            yield meta, _png_loader(png)


def iter_bgr(session: Path, manifest: dict[str, Any] | None = None, *, every: int = 1,
             source: str | None = None, cuts: list[str] | None = None, strict: bool = False
             ) -> Iterator[tuple[dict[str, Any], BGR]]:  # fmt: skip
    """iter_frames with every frame decoded: (meta, BGR)."""
    for meta, load in iter_frames(session, manifest, every=every, source=source, cuts=cuts,
                                  strict=strict):  # fmt: skip
        yield meta, load()


def nearest_ref(refs: Sequence[FrameRef], t_ns: int) -> FrameRef:
    """The ref captured nearest ``t_ns`` (the earlier one on a tie)."""
    if not refs:
        raise FrameSourceError("no frames")
    return min(refs, key=lambda r: (abs(r.t_mono_ns - t_ns), r.t_mono_ns))


def _region_size(manifest: dict[str, Any]) -> tuple[int, int] | None:
    region = manifest.get("game_region")
    return (int(region[2]), int(region[3])) if region else None


def _video_loader(ref: FrameRef, size: tuple[int, int] | None) -> Loader:
    return lambda: read_ref(ref, size)


def _png_loader(png: bytes) -> Loader:
    def load() -> BGR:
        img = decode_png(png)
        return img if img.ndim == 3 and img.shape[2] == 3 else np.ascontiguousarray(img[..., :3])

    return load


# --- verification ---------------------------------------------------------------------------------


def verify_video(session: Path, manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    """Every access unit of a session's video decoded ALONE and checked: one frame each, the
    declared convention (pc, bt709), the game region's size; every fed row of the index has its
    unit, no unit is left over. ``ok`` only when all hold (the PNG twin, if any, is not read)."""
    manifest = manifest if manifest is not None else load_manifest(session)
    if not has_video(session, manifest):
        raise FrameSourceError(f"{session.name}: no video stream to verify")
    problems: list[str] = []
    aus = stream_access_units(session / VIDEO_FILE)
    refs = video_refs(session, manifest, problems, aus=aus)
    rows = read_video_index(session / VIDEO_INDEX)
    by_status: dict[str, int] = {}
    for r in rows:
        by_status[str(r["status"])] = by_status.get(str(r["status"]), 0) + 1
    size = _region_size(manifest)
    bad: dict[str, int] = {}
    decoded = 0
    for ref in refs:
        try:
            read_ref(ref, size)
            decoded += 1
        except VideoFrameError as e:
            why = str(e).split(":")[0]
            bad[why] = bad.get(why, 0) + 1
            if sum(bad.values()) <= 5:
                problems.append(f"frame {ref.frame_id}: {e}")
    fed = by_status.get(FED, 0)
    ok = not problems and not bad and decoded == fed and decoded == len(refs)
    return {"session": manifest.get("session_id") or session.name, "format":
            session_format(manifest), "rows": len(rows), "by_status": by_status, "fed": fed,
            "access_units": len(aus),
            "decoded_alone": decoded, "bad": bad, "problems": problems,
            "manifest_frames": manifest.get("frames"), "ok": ok}  # fmt: skip
