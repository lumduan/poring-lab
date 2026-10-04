"""Read an H.264 dataset session (Batt 2026-10-04: H.264 with an IDR every 1 s is the default
dataset format; ADR-0010 note). OFFLINE ONLY, host side -- PyAV lives here and in the gamestream
image, never in vision (test_guards).

A session (scripts/record_session.py --format h264) holds what the S2 client decoded:
    stream.h264       the Annex-B access units exactly as fed to the live decoder
    stream.idx.csv    one row per access unit: au, frame_id (the bus id), frame_number,
                      frame_type, idr, pts_ms, offset, length, receive_ms, t_publish_ns
    stream.hash.csv   frame_id -> crc32+adler32 of the decoded full BGRA frame (s2spike.h264rec)
    stream.done.json  the recorder's summary, incl. the decoder "versions"
    manifest.json     incl. game_region and the freeze spans

Reading (training, QA):
  * frames are decoded by GOP: from the IDR at or before a target through the last target in that
    GOP, converting to BGRA only the frames returned (a seek costs the GOP prefix, ~1 s at H1);
  * every returned frame is checked against its recorded checksum -- the bitstream IS the dataset
    only while the decode is bit-identical. A mismatch raises DeterminismError; a decoder build
    other than the recording's raises DecoderMismatch (the checksum covers swscale too);
  * frames inside a freeze span (the last frame before a stall and the first after it) are not
    offered: a stale or recovery picture next to a moving world;
  * the returned image is the GAME_REGION crop, BGR, like the PNG shards.
"""

from __future__ import annotations

import bisect
import csv
import json
import zlib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

AV_CODEC_FLAG_LOW_DELAY = 1 << 19  # libavcodec/avcodec.h (the live decoder's flag)
LIVE_THREADS = 2  # the S2 client's default --decode-threads


class DeterminismError(RuntimeError):
    """A decoded frame differs from the one the live client decoded."""


class DecoderMismatch(RuntimeError):
    """This decoder build is not the recording's: the checksums are not comparable."""


def frame_digest(contiguous: Any) -> str:
    """crc32 + adler32 of a decoded frame's bytes, 16 hex digits. PORTED byte for byte from
    services/gamestream/s2spike/h264rec.frame_digest (a test pins the equality)."""
    return f"{zlib.crc32(contiguous):08x}{zlib.adler32(contiguous):08x}"


def decoder_versions() -> dict[str, str]:
    import av  # lazy: tests and tools that never decode do not need it

    libs = getattr(av, "library_versions", {}) or {}
    out = {"pyav": str(av.__version__)}
    for name in ("libavcodec", "libswscale", "libavutil"):
        if name in libs:
            out[name] = ".".join(str(v) for v in libs[name])
    return out


def new_decoder(threads: int = LIVE_THREADS) -> Any:
    """A decoder configured exactly like the live S2 client's (s2spike/decode.py)."""
    import av

    ctx = av.CodecContext.create("h264", "r")
    ctx.flags |= AV_CODEC_FLAG_LOW_DELAY
    ctx.thread_type = "SLICE"
    ctx.thread_count = threads
    return ctx


@dataclass(frozen=True, slots=True)
class Unit:
    au: int
    frame_id: int
    idr: bool
    offset: int
    length: int
    t_ns: int  # the live client's decode-complete time (t_publish_ns)


def read_index(path: Path) -> list[Unit]:
    """Decodable access units in stream order (gap rows and failed live decodes left out)."""
    units = []
    with path.open() as fh:
        for row in csv.DictReader(fh):
            au, fid, length = int(row["au"]), int(row["frame_id"]), int(row["length"])
            if au < 0 or fid < 0 or length <= 0:
                continue
            units.append(Unit(au, fid, row["idr"] == "1", int(row["offset"]), length,
                              int(row["t_publish_ns"])))  # fmt: skip
    return units


def read_hashes(path: Path) -> dict[int, str]:
    with path.open() as fh:
        return {int(r["frame_id"]): r["crc32_adler32"] for r in csv.DictReader(fh)}


class H264Session:
    def __init__(
        self, directory: Path, *, check_versions: bool = True, threads: int = LIVE_THREADS
    ) -> None:
        self.dir = directory
        self.threads = threads  # slice threads: Sunshine sends 4 slices, so 4 decode in parallel
        self.manifest: dict[str, Any] = json.loads((directory / "manifest.json").read_text())
        if self.manifest.get("format") != "h264":
            raise ValueError(f"{directory.name} is not an H.264 session")
        done = json.loads((directory / "stream.done.json").read_text())
        self.recorded_versions: dict[str, str] = done.get("versions", {})
        if check_versions:
            mine = decoder_versions()
            differ = {k: (v, mine.get(k)) for k, v in self.recorded_versions.items()
                      if mine.get(k) != v}  # fmt: skip
            if differ:
                raise DecoderMismatch(f"recorded vs this decoder: {differ}")
        self.units = read_index(directory / "stream.idx.csv")
        self.hashes = read_hashes(directory / "stream.hash.csv")
        self._pos = {u.frame_id: i for i, u in enumerate(self.units)}
        self._idrs = [i for i, u in enumerate(self.units) if u.idr]
        x, y, w, h = self.manifest["game_region"]
        self.region = (int(x), int(y), int(w), int(h))
        spans = (self.manifest.get("freezes") or {}).get("spans_ns") or []
        self.freeze_spans = sorted((int(a), int(b)) for a, b in spans)
        self._data: bytes | None = None

    # --- what can be read -----------------------------------------------------------------------

    @property
    def frame_ids(self) -> list[int]:
        return [u.frame_id for u in self.units]

    def in_freeze(self, t_ns: int) -> bool:
        """The frames bounding a stall ([a, b] inclusive) are not offered."""
        i = bisect.bisect_right(self.freeze_spans, (t_ns, 1 << 62)) - 1
        return i >= 0 and self.freeze_spans[i][0] <= t_ns <= self.freeze_spans[i][1]

    def usable(self) -> list[int]:
        """Frame ids that are decodable from an IDR, outside every freeze span, with a hash."""
        if not self._idrs:
            return []
        first = self._idrs[0]
        return [u.frame_id for u in self.units[first:]
                if u.frame_id in self.hashes and not self.in_freeze(u.t_ns)]  # fmt: skip

    def gop_start(self, index: int) -> int:
        """The index of the IDR at or before ``index``."""
        k = bisect.bisect_right(self._idrs, index) - 1
        if k < 0:
            raise KeyError(f"unit {index} precedes the first IDR")
        return self._idrs[k]

    def sample(self, n: int) -> list[int]:
        """``n`` usable frame ids spread evenly over the session (QA bundles, spot checks)."""
        usable = self.usable()
        if n >= len(usable):
            return usable
        step = len(usable) / n
        return [usable[int(i * step)] for i in range(n)]

    # --- decoding -------------------------------------------------------------------------------

    def _bytes(self) -> bytes:
        if self._data is None:
            self._data = (self.dir / "stream.h264").read_bytes()
        return self._data

    def frames(
        self, frame_ids: Sequence[int], *, verify: bool = True, crop: bool = True
    ) -> Iterator[tuple[dict[str, Any], npt.NDArray[np.uint8]]]:
        """The requested frames in stream order, each GOP decoded once from its IDR. Yields
        (meta, image): image is the GAME_REGION crop as BGR (crop=False: the full BGRA frame)."""
        import av

        wanted = sorted({self._pos[f] for f in frame_ids if f in self._pos})
        data = self._bytes()
        i = 0
        while i < len(wanted):
            start = self.gop_start(wanted[i])
            gop_end = len(self.units)
            nxt = bisect.bisect_right(self._idrs, start)
            if nxt < len(self._idrs):
                gop_end = self._idrs[nxt]
            targets = []
            while i < len(wanted) and wanted[i] < gop_end:
                targets.append(wanted[i])
                i += 1
            ctx = new_decoder(self.threads)
            last = targets[-1]
            pending = set(targets)
            for k in range(start, last + 1):
                u = self.units[k]
                out = list(ctx.decode(av.Packet(data[u.offset : u.offset + u.length])))
                if k not in pending:
                    continue
                if not out:
                    raise DeterminismError(f"frame {u.frame_id}: the unit decoded to nothing")
                yield self._emit(u, out[0], verify=verify, crop=crop)

    def clip(self, start_frame_id: int, n: int, **kw: Any) -> list[tuple[dict[str, Any], Any]]:
        """``n`` consecutive frames from ``start_frame_id`` (how training reads)."""
        i = self._pos[start_frame_id]
        ids = [u.frame_id for u in self.units[i : i + n]]
        return list(self.frames(ids, **kw))

    def _emit(
        self, u: Unit, frame: Any, *, verify: bool, crop: bool
    ) -> tuple[dict[str, Any], npt.NDArray[np.uint8]]:
        bgra = np.ascontiguousarray(frame.to_ndarray(format="bgra"))
        crc_ok = None
        if verify:
            want = self.hashes.get(u.frame_id)
            crc_ok = want is not None and frame_digest(bgra) == want
            if not crc_ok:
                raise DeterminismError(f"frame {u.frame_id}: checksum differs from the live decode")
        meta = {"frame_id": u.frame_id, "t_mono_ns": u.t_ns, "idr": u.idr, "crc_ok": crc_ok}
        if not crop:
            return meta, bgra
        x, y, w, h = self.region
        return meta, np.ascontiguousarray(bgra[y : y + h, x : x + w, :3])


def session_format(directory: Path) -> str:
    """'h264' or 'png' (a manifest without "format" predates recorder v4: PNG)."""
    manifest = json.loads((directory / "manifest.json").read_text())
    return str(manifest.get("format") or "png")
