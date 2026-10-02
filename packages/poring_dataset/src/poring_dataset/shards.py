"""Recording shards (B1, ADR-0010): WebDataset-style tar files, never one file per frame.

A session directory holds:
  manifest.json            session id, backend + config hash, game region, fps cap, shards, t0/t1
  shard-000000.tar ...     per frame: <frame_id>.png (lossless, the capture path's pixels),
                           <frame_id>.json {frame_id, t_mono_ns, t_wall}; labels .txt later
  packets.jsonl.gz         the sniffer's events for [t0 - 5 s, t1 + 5 s] (names/chat pseudonymised)

PNG is written with the standard library (zlib level 1 by default: fast, lossless); no extra
dependency on the host or in the backend image.
"""

import io
import json
import struct
import tarfile
import time
import zlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt


def encode_png(img: npt.NDArray[np.uint8], level: int = 1) -> bytes:
    """BGR / BGRA / grey uint8 -> PNG bytes (RGB or RGBA or L)."""
    if img.ndim == 2:
        rgb, color = img, 0
    elif img.shape[2] == 3:
        rgb, color = img[:, :, ::-1], 2
    elif img.shape[2] == 4:
        rgb, color = img[:, :, [2, 1, 0, 3]], 6
    else:
        raise ValueError(f"unsupported shape {img.shape}")
    h, w = img.shape[:2]
    raw = np.ascontiguousarray(rgb).reshape(h, -1)
    data = b"".join(b"\x00" + raw[y].tobytes() for y in range(h))

    def chunk(kind: bytes, body: bytes) -> bytes:
        crc = struct.pack(">I", zlib.crc32(kind + body))
        return struct.pack(">I", len(body)) + kind + body + crc

    header = struct.pack(">IIBBBBB", w, h, 8, color, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(data, level)) + chunk(b"IEND", b""))  # fmt: skip


def _unfilter(raw: bytes, h: int, stride: int, bpp: int) -> npt.NDArray[np.uint8]:
    """PNG row filters 0-4 (None, Sub, Up, Average, Paeth) for 8-bit samples."""
    out = np.zeros((h, stride), dtype=np.uint8)
    prev = np.zeros(stride, dtype=np.int32)
    pos = 0
    for y in range(h):
        kind = raw[pos]
        line = np.frombuffer(raw, np.uint8, stride, pos + 1).astype(np.int32)
        pos += 1 + stride
        if kind == 0:
            cur = line
        elif kind == 2:
            cur = (line + prev) & 0xFF
        else:
            cur = line.copy()
            for x in range(stride):
                a = int(cur[x - bpp]) if x >= bpp else 0
                b = int(prev[x])
                if kind == 1:
                    pred = a
                elif kind == 3:
                    pred = (a + b) // 2
                elif kind == 4:
                    c = int(prev[x - bpp]) if x >= bpp else 0
                    pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                    pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                else:
                    raise ValueError(f"bad PNG filter type {kind}")
                cur[x] = (int(line[x]) + pred) & 0xFF
        out[y] = cur
        prev = cur
    return out


def decode_png(data: bytes) -> npt.NDArray[np.uint8]:
    """8-bit, non-interlaced PNG (grey, RGB or RGBA; any row filter) -> BGR(A) or grey."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat = 8, b""
    w = h = color = depth = interlace = 0
    while pos < len(data):
        (length,) = struct.unpack_from(">I", data, pos)
        kind = data[pos + 4 : pos + 8]
        body = data[pos + 8 : pos + 8 + length]
        if kind == b"IHDR":
            w, h, depth, color, _, _, interlace = struct.unpack_from(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat += body
        pos += 12 + length
    if depth != 8 or interlace or color not in (0, 2, 6):
        raise ValueError(f"unsupported PNG: depth {depth}, colour {color}, interlace {interlace}")
    channels = {0: 1, 2: 3, 6: 4}[color]
    px = _unfilter(zlib.decompress(idat), h, w * channels, channels)
    if channels == 1:
        return px.reshape(h, w)
    img = px.reshape(h, w, channels)
    order = [2, 1, 0] if channels == 3 else [2, 1, 0, 3]
    return np.ascontiguousarray(img[:, :, order])


class ShardWriter:
    """Appends frames to shard-NNNNNN.tar files of at most ``max_bytes`` each."""

    def __init__(self, directory: Path, max_bytes: int = 256 << 20, png_level: int = 1) -> None:
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)
        self.max_bytes, self.level = max_bytes, png_level
        self.shards: list[str] = []
        self.frames = 0
        self.bytes = 0
        self._tar: tarfile.TarFile | None = None
        self._size = 0

    def _open(self) -> tarfile.TarFile:
        if self._tar is None or self._size >= self.max_bytes:
            if self._tar is not None:
                self._tar.close()
            name = f"shard-{len(self.shards):06d}.tar"
            self.shards.append(name)
            self._tar = tarfile.open(self.dir / name, "w")  # noqa: SIM115 -- spans many add() calls; close()
            self._size = 0
        return self._tar

    def _add(self, tar: tarfile.TarFile, name: str, body: bytes) -> None:
        info = tarfile.TarInfo(name)
        info.size, info.mtime = len(body), int(time.time())
        tar.addfile(info, io.BytesIO(body))
        self._size += len(body) + 1024
        self.bytes += len(body)

    def add(self, frame_id: int, t_mono_ns: int, img: npt.NDArray[np.uint8], **meta: Any) -> None:
        tar = self._open()
        key = f"{frame_id:09d}"
        self._add(tar, f"{key}.png", encode_png(img, self.level))
        record = {"frame_id": frame_id, "t_mono_ns": t_mono_ns, **meta}
        self._add(tar, f"{key}.json", json.dumps(record, sort_keys=True).encode())
        self.frames += 1

    def close(self) -> None:
        if self._tar is not None:
            self._tar.close()
            self._tar = None


def read_shard(path: Path) -> Iterator[tuple[dict[str, Any], npt.NDArray[np.uint8]]]:
    """(meta, image) per frame, in shard order."""
    with tarfile.open(path) as tar:
        pending: dict[str, dict[str, bytes]] = {}
        for member in tar:
            key, _, ext = member.name.partition(".")
            fh = tar.extractfile(member)
            assert fh is not None
            pending.setdefault(key, {})[ext] = fh.read()
            item = pending[key]
            if "png" in item and "json" in item:
                del pending[key]
                yield json.loads(item["json"]), decode_png(item["png"])


def write_manifest(directory: Path, manifest: dict[str, Any]) -> Path:
    path = directory / "manifest.json"
    tmp = directory / ".manifest.json.tmp"
    tmp.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    tmp.replace(path)
    return path
