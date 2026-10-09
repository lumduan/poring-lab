"""Minimal pcapng writer: SHB + one Ethernet IDB at nanosecond resolution + EPBs, and a custom block
(PEN 32473, the IANA documentation number) holding each realtime->monotonic clock sample as JSON.

CREDENTIALS (LoginScrub, Batt 2026-10-09): every client -> login-server segment has its TCP payload
zeroed BEFORE it is written. A segment that starts with a login request id keeps those 2 bytes (the
packet id); a continuation segment keeps nothing (its first bytes could be password bytes). That
covers CA_LOGIN's plaintext password (bytes 30..53) however TCP happens to segment it. The IP/TCP
checksums of those frames are then wrong; the pcap is ground truth for timing and ids, never for
login payloads. A connection is a LOGIN connection when
* its server port is one of the CONFIGURED login ports (SNIFF_LOGIN_PORTS, the sniffer's
  environment), or
* its FIRST client payload starts with a login request id (LOGIN_REQUEST_IDS), on ANY port: defense
  in depth, and the whole rule when the ports are UNKNOWN (unset or invalid: fail closed by shape).
  The decision is per connection, never per segment: a char / map stream whose segment happens to
  start with such bytes keeps its ground truth (attack / NPC requests).
"""

import json
import struct
from collections import OrderedDict
from pathlib import Path
from typing import Any, BinaryIO

LINKTYPE_ETHERNET = 1
CUSTOM_BLOCK = 0x00000BAD  # copiable custom block
PEN = 32473
LOGIN_PORT = 6900  # the lab rathena's published login port (compose.yaml): SNIFF_LOGIN_PORTS there
LOGIN_PORTS_ENV = "SNIFF_LOGIN_PORTS"
# Every client -> login-server request the pinned rAthena login server parses
# (src/login/loginclif.cpp LoginPacketDatabase; ids from src/common/packets.hpp): CA_LOGIN 0x64,
# CA_REQ_HASH 0x1db, CA_LOGIN2 0x1dd, CA_LOGIN3 0x1fa, CA_CONNECT_INFO_CHANGED 0x200,
# CA_EXE_HASHCHECK 0x204, CA_LOGIN_PCBANG 0x277, CA_LOGIN4 0x27c, CA_LOGIN_CHANNEL 0x2b0,
# CA_SSO_LOGIN_REQ 0x825, CT_AUTH 0xacf. None of them opens a char (CH_ENTER 0x65) or map stream.
LOGIN_REQUEST_IDS = frozenset(
    {0x0064, 0x01DB, 0x01DD, 0x01FA, 0x0200, 0x0204, 0x0277, 0x027C, 0x02B0, 0x0825, 0x0ACF}
)
MAX_CONNS = 4096  # connections remembered (oldest forgotten first)


def _pad(b: bytes) -> bytes:
    return b + b"\0" * (-len(b) % 4)


def _block(btype: int, body: bytes) -> bytes:
    total = 12 + len(body)
    return struct.pack("<II", btype, total) + body + struct.pack("<I", total)


def _option(code: int, value: bytes) -> bytes:
    return struct.pack("<HH", code, len(value)) + _pad(value)


def login_ports(value: str | None) -> frozenset[int] | None:
    """SNIFF_LOGIN_PORTS ("6900" or "6900,6901") -> the configured login ports. None = UNKNOWN
    (unset, empty, or any entry that is not a port 1-65535): the scrub then works by shape alone."""
    if value is None or not value.strip():
        return None
    out: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part.isdigit() or not 1 <= int(part) <= 65535:
            return None
        out.add(int(part))
    return frozenset(out)


class LoginScrub:
    """The pcap's credential scrub (see the module docstring), stateful per connection."""

    def __init__(self, ports: frozenset[int] | None) -> None:
        self.ports = ports
        self.conns: OrderedDict[tuple[str, int, str, int], bool] = OrderedDict()
        self.scrubbed = 0

    @property
    def mode(self) -> str:
        if self.ports is None:
            return "login ports UNKNOWN: scrub by shape only (fail closed)"
        return f"login ports {sorted(self.ports)} + every login-shaped connection"

    def is_login(self, seg: Any) -> bool | None:
        """The connection's verdict, decided at its first client payload; None before one."""
        return self.conns.get((seg.src, seg.sport, seg.dst, seg.dport))

    def __call__(self, seg: Any) -> bytes:
        """The frame to write for this TCP segment (seg: capture.TcpSegment-like)."""
        frame = bytes(seg.frame)
        if not seg.payload:
            return frame
        key = (seg.src, seg.sport, seg.dst, seg.dport)
        head = int.from_bytes(seg.payload[:2], "little") if len(seg.payload) >= 2 else -1
        login = self.conns.get(key)
        if login is None:
            login = head in LOGIN_REQUEST_IDS or (
                self.ports is not None and seg.dport in self.ports
            )
            self.conns[key] = login
            while len(self.conns) > MAX_CONNS:
                self.conns.popitem(last=False)
        elif self.ports is not None and seg.dport in self.ports:
            login = True
        if not login:
            return frame
        self.scrubbed += 1
        keep = int(seg.payload_offset) + (2 if head in LOGIN_REQUEST_IDS else 0)
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
