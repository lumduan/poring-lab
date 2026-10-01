"""TCP reassembly and RO packet framing. Nothing is dropped silently: every unknown id, desync and
skipped byte is counted (`FramerStats`) and surfaced as events by the caller.

RO framing: a little-endian u16 packet id, then either a fixed length from the table or, for
VARIABLE (-1), a u16 length at offset 2 (4..32768, as rAthena's clif_parse checks).
"""

import struct
from collections.abc import Iterator
from dataclasses import dataclass, field

from poring_packets.tables import VARIABLE, LengthTable

MAX_LEN = 32768
MAX_OOO_SEGMENTS = 64  # out-of-order segments buffered per direction before giving up on a gap
RESYNC_RUN = 3  # consecutive well-framed packets that prove a resync offset


@dataclass(frozen=True)
class RoPacket:
    packet_id: int
    data: bytes  # the whole packet, header included
    t_real_ns: int  # kernel receive time of the segment that completed it


@dataclass
class FramerStats:
    packets: int = 0
    unknown_ids: dict[int, int] = field(default_factory=dict)
    desyncs: int = 0
    skipped_bytes: int = 0
    gaps: int = 0  # TCP sequence gaps we could not fill


class TcpReassembler:
    """One direction of one TCP connection: emits in-order payload bytes."""

    def __init__(self) -> None:
        self.next_seq: int | None = None
        self.pending: dict[int, bytes] = {}
        self.gaps = 0

    def feed(self, seq: int, payload: bytes, syn: bool = False) -> bytes:
        if syn:
            self.next_seq = (seq + 1) & 0xFFFFFFFF
            self.pending.clear()
            return b""
        if not payload:
            return b""
        if self.next_seq is None:  # joined mid-stream: start here (the framer resyncs)
            self.next_seq = seq
        out = bytearray()
        rel = (seq - self.next_seq) & 0xFFFFFFFF
        if rel >= 0x80000000:  # entirely or partly old data (retransmit)
            overlap = (self.next_seq - seq) & 0xFFFFFFFF
            if overlap >= len(payload):
                return b""
            payload, seq = payload[overlap:], self.next_seq
            rel = 0
        if rel > 0:
            self.pending[seq] = payload
            if len(self.pending) > MAX_OOO_SEGMENTS:  # a hole that will never fill: skip it
                base = self.next_seq
                first = min(self.pending, key=lambda s: (s - base) & 0xFFFFFFFF)
                self.gaps += 1
                self.next_seq = first
            else:
                return b""
        else:
            out += payload
            self.next_seq = (self.next_seq + len(payload)) & 0xFFFFFFFF
        while self.pending:  # drain whatever is now contiguous
            key = next((s for s in self.pending if s == self.next_seq), None)
            if key is None:
                break
            chunk = self.pending.pop(key)
            out += chunk
            self.next_seq = (self.next_seq + len(chunk)) & 0xFFFFFFFF
        return bytes(out)


class RoFramer:
    """Splits one direction's byte stream into RO packets using the length table."""

    def __init__(
        self, table: LengthTable, server: str, direction: str, *, raw_prefix: int = 0
    ) -> None:
        self.table, self.server, self.direction = table, server, direction
        self.buf = bytearray()
        self.raw_prefix = raw_prefix  # header-less bytes at stream start (char server's 4-byte AID)
        self.raw: bytes | None = None
        self.stats = FramerStats()
        self.synced = True

    def _length_at(self, offset: int) -> int | None:
        """Total length of the packet at `offset`, 0 if more bytes are needed, None if invalid."""
        if len(self.buf) - offset < 2:
            return 0
        pid = struct.unpack_from("<H", self.buf, offset)[0]
        length = self.table.length(self.server, self.direction, pid)
        if length is None:
            return None
        if length == VARIABLE:
            if len(self.buf) - offset < 4:
                return 0
            length = struct.unpack_from("<H", self.buf, offset + 2)[0]
            if not 4 <= length <= MAX_LEN:
                return None
        return length if length >= 2 else None

    def _resync(self) -> None:
        """Advance byte by byte to an offset where RESYNC_RUN packets frame cleanly."""
        for start in range(1, len(self.buf)):
            off, ok = start, 0
            while ok < RESYNC_RUN:
                n = self._length_at(off)
                if not n or off + n > len(self.buf):
                    break
                off += n
                ok += 1
            if ok >= RESYNC_RUN:
                self.stats.skipped_bytes += start
                del self.buf[:start]
                self.synced = True
                return
        # not enough data to prove an offset: keep the tail, retry with more bytes

    def feed(self, data: bytes, t_real_ns: int) -> Iterator[RoPacket]:
        self.buf += data
        if self.raw_prefix and self.raw is None:
            if len(self.buf) < self.raw_prefix:
                return
            self.raw = bytes(self.buf[: self.raw_prefix])
            del self.buf[: self.raw_prefix]
        while self.buf:
            if not self.synced:
                self._resync()
                if not self.synced:
                    return
            n = self._length_at(0)
            if n == 0:
                return
            if n is None:
                pid = struct.unpack_from("<H", self.buf, 0)[0]
                self.stats.unknown_ids[pid] = self.stats.unknown_ids.get(pid, 0) + 1
                self.stats.desyncs += 1
                self.synced = False
                continue
            if len(self.buf) < n:
                return
            packet = bytes(self.buf[:n])
            del self.buf[:n]
            self.stats.packets += 1
            yield RoPacket(struct.unpack_from("<H", packet, 0)[0], packet, t_real_ns)
