"""Test helpers: synthetic tables, RO packets and TCP segments (inverse of rAthena WBUF macros)."""

import socket
import struct

from poring_packets.capture import TcpSegment
from poring_packets.tables import LengthTable

CLIENT = "192.168.1.169"
SERVER = "10.210.96.6"


def table(extra: dict[tuple[str, str, int], int] | None = None) -> LengthTable:
    lengths = {
        ("login", "cs", 0x0064): 55, ("login", "sc", 0x0AC4): -1,
        ("char", "cs", 0x0065): 17, ("char", "sc", 0x0AC5): 156, ("char", "sc", 0x082D): -1,
        ("map", "cs", 0x0436): 23, ("map", "cs", 0x035F): 5, ("map", "cs", 0x00F3): -1,
        ("map", "sc", 0x0087): 12, ("map", "sc", 0x02EB): 13, ("map", "sc", 0x008E): -1,
        ("map", "sc", 0x008D): -1, ("map", "sc", 0x007F): 6, ("map", "sc", 0x00B0): 8,
        ("map", "sc", 0x09FE): -1, ("map", "sc", 0x0080): 7,
    }  # fmt: skip
    lengths.update(extra or {})
    return LengthTable(lengths, {k: "test" for k in lengths})


def wpos(x: int, y: int, d: int = 0) -> bytes:
    """WBUFPOS (clif.cpp:173-180)."""
    return bytes(
        [(x >> 2) & 0xFF, ((x << 6) | ((y >> 4) & 0x3F)) & 0xFF, ((y << 4) | (d & 0xF)) & 0xFF]
    )


def wpos2(x0: int, y0: int, x1: int, y1: int, sx: int = 8, sy: int = 8) -> bytes:
    """WBUFPOS2 (clif.cpp:182-190)."""
    return bytes([
        (x0 >> 2) & 0xFF, ((x0 << 6) | ((y0 >> 4) & 0x3F)) & 0xFF,
        ((y0 << 4) | ((x1 >> 6) & 0x0F)) & 0xFF, ((x1 << 2) | ((y1 >> 8) & 0x03)) & 0xFF,
        y1 & 0xFF, ((sx << 4) | (sy & 0x0F)) & 0xFF,
    ])  # fmt: skip


def var(pid: int, body: bytes) -> bytes:
    return struct.pack("<HH", pid, 4 + len(body)) + body


def zc_notify_act(src: int, dst: int, tick: int, src_speed: int, dmotion: int, damage: int,
                  action: int, *, div: int = 1, damage2: int = 0, sp: int = 0,
                  pid: int = 0x08C8) -> bytes:  # fmt: skip
    """PACKET_ZC_NOTIFY_ACT in its three PACKETVER layouts (rAthena map/packets.hpp:1412-1455)."""
    head = struct.pack("<HIIIii", pid, src, dst, tick, src_speed, dmotion)
    if pid == 0x08C8:
        return head + struct.pack("<iBHBi", damage, sp, div, action, damage2)  # 34 bytes
    if pid == 0x02E1:
        return head + struct.pack("<iHBi", damage, div, action, damage2)  # 33 bytes
    return head + struct.pack("<hHBh", damage, div, action, damage2)  # 0x008A, 29 bytes


def zc_change_direction(gid: int, heading: int, head_dir: int = 0) -> bytes:
    """PACKET_ZC_CHANGE_DIRECTION (packets.hpp:688-694), 9 bytes."""
    return struct.pack("<HIHB", 0x009C, gid, head_dir, heading)


def ca_login(user: bytes, password: bytes) -> bytes:
    return (
        struct.pack("<HI", 0x0064, 20211103)
        + user.ljust(24, b"\0")
        + password.ljust(24, b"\0")
        + b"\x00"
    )


def ac_accept_login(aid: int) -> bytes:
    body = bytearray(60)  # 64-byte header without the server list
    struct.pack_into("<I", body, 4, aid)  # AID at offset 8 of the packet
    body[42] = 1  # sex at offset 46
    return var(0x0AC4, bytes(body))


def cz_enter2(aid: int) -> bytes:
    return struct.pack("<HIIIIB", 0x0436, aid, 150000, 0, 0, 1) + b"\0\0\0\0"


def frame(
    src: str, sport: int, dst: str, dport: int, seq: int, payload: bytes, flags: int = 0x18
) -> bytes:
    eth = b"\x02" * 6 + b"\x04" * 6 + b"\x08\x00"
    tcp = struct.pack("!HHIIBBHHH", sport, dport, seq, 0, 5 << 4, flags, 65535, 0, 0)
    ip = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + len(tcp) + len(payload), 0, 0, 64, 6, 0,
                     socket.inet_aton(src), socket.inet_aton(dst))  # fmt: skip
    return eth + ip + tcp + payload


def seg(direction: str, port: int, seq: int, payload: bytes, t_real_ns: int = 1_000_000_000_000,
        flags: int = 0x18, cport: int = 50000) -> TcpSegment:  # fmt: skip
    if direction == "cs":
        src, sport, dst, dport = CLIENT, cport, SERVER, port
    else:
        src, sport, dst, dport = SERVER, port, CLIENT, cport
    fr = frame(src, sport, dst, dport, seq, payload, flags)
    return TcpSegment(t_real_ns, src, sport, dst, dport, seq, flags, payload, fr, 54)
