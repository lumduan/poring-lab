"""Minimal pcapng writer: SHB + one Ethernet IDB at nanosecond resolution + EPBs, and a custom block
(PEN 32473, the IANA documentation number) holding each realtime->monotonic clock sample as JSON.

CREDENTIALS: every client->login-server segment (dst port 6900) has its TCP payload zeroed after the
first 2 bytes (the packet id) BEFORE it is written. That covers CA_LOGIN's plaintext password (bytes
30..53) however TCP happens to segment it. The IP/TCP checksums of those frames are then wrong; the
pcap is ground truth for timing and ids, never for login payloads.
"""

import json
import struct
from pathlib import Path
from typing import BinaryIO

LINKTYPE_ETHERNET = 1
CUSTOM_BLOCK = 0x00000BAD  # copiable custom block
PEN = 32473
LOGIN_PORT = 6900


def _pad(b: bytes) -> bytes:
    return b + b"\0" * (-len(b) % 4)


def _block(btype: int, body: bytes) -> bytes:
    total = 12 + len(body)
    return struct.pack("<II", btype, total) + body + struct.pack("<I", total)


def _option(code: int, value: bytes) -> bytes:
    return struct.pack("<HH", code, len(value)) + _pad(value)


def redact(frame: bytes, payload_offset: int, dport: int) -> bytes:
    """Zero a login segment's payload after its first 2 bytes (see the module docstring)."""
    if dport != LOGIN_PORT or len(frame) <= payload_offset + 2:
        return frame
    keep = payload_offset + 2
    return frame[:keep] + b"\0" * (len(frame) - keep)


class PcapngWriter:
    def __init__(self, path: Path, app: str = "poring-lab sniffer") -> None:
        self.path = path
        self._fh: BinaryIO = path.open("wb")
        shb_opts = _option(4, app.encode()) + _option(0, b"")
        shb = struct.pack("<IHHq", 0x1A2B3C4D, 1, 0, -1) + shb_opts
        self._fh.write(_block(0x0A0D0D0A, shb))
        idb_opts = _option(9, bytes([9])) + _option(0, b"")  # if_tsresol = 10^-9
        idb = struct.pack("<HHI", LINKTYPE_ETHERNET, 0, 65535) + idb_opts
        self._fh.write(_block(1, idb))
        self.bytes = self._fh.tell()

    def packet(self, frame: bytes, t_real_ns: int) -> None:
        hi, lo = t_real_ns >> 32, t_real_ns & 0xFFFFFFFF
        body = struct.pack("<IIIII", 0, hi, lo, len(frame), len(frame)) + _pad(frame)
        blk = _block(6, body)
        self._fh.write(blk)
        self.bytes += len(blk)

    def clock_sample(self, sample: dict[str, int]) -> None:
        body = struct.pack("<I", PEN) + _pad(json.dumps(sample, sort_keys=True).encode())
        blk = _block(CUSTOM_BLOCK, body)
        self._fh.write(blk)
        self.bytes += len(blk)

    def flush(self) -> None:
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()
