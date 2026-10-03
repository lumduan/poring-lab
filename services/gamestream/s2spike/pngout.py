"""A dependency-free PNG writer for evidence frames (RGB, zlib level 1), written atomically."""

from __future__ import annotations

import os
import struct
import zlib
from pathlib import Path
from typing import Any


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def png_bytes(rgb: Any) -> bytes:
    """``rgb``: an (h, w, 3) uint8 array (numpy) or anything with .shape and .tobytes()."""
    h, w = int(rgb.shape[0]), int(rgb.shape[1])
    raw = rgb.tobytes()
    stride = w * 3
    rows = b"".join(b"\x00" + raw[y * stride : (y + 1) * stride] for y in range(h))
    header = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(rows, 1))
        + _chunk(b"IEND", b"")
    )


def write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
