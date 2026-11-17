"""Passive capture: an AF_PACKET socket with a kernel BPF filter and kernel receive timestamps.

Needs CAP_NET_RAW only (packet(7)); it never sends. Runs in rathena's network namespace, so it sees
the client <-> login/char/map TCP (Docker's DNAT keeps the client's real source address).

BPF: `host <client> and tcp and (port 6900 or port 6121 or port 5121)` for Ethernet frames,
compiled by libpcap's pcap_compile_nopcap (snaplen 65535, optimised) for the lab's game PC and
committed as constants; `tests/test_core.py` recompiles it with the host's libpcap when available.
Filtering on the client IP also excludes the inter-server traffic that shares these ports
(char->login 0x2710 on 6900, map->char 0x2af8 on 6121).

➡️ Since 2026-11-17 (Batt: "fix the sniffer to listen to the IP from WIN_HOST"; ADR-0007 note) the
client is THIS host's Windows game PC, `CLIENT_IP` from the environment (compose passes WIN_HOST):
`bpf_program(ip)` is the committed program with the address constant of its two `host` compares
swapped. libpcap compiles `host X` to the same instructions for every IPv4 X; test_core proves it
by recompiling for several addresses. And the packets only READ (ADR-0016 amendment 11-17): whatever
this filter sees or misses labels a session verified or not, never whether the bot plays.
"""

import ctypes
import ipaddress
import socket
import struct
from dataclasses import dataclass

LAB_CLIENT_IP = "192.168.1.169"  # the lab's game PC: the committed program's address
CLIENT_IP = LAB_CLIENT_IP  # the offline tools' default (replay.py); the live sniffer reads WIN_HOST
PORTS_EXPR = "tcp and (port 6900 or port 6121 or port 5121)"
BPF_EXPR = f"host {LAB_CLIENT_IP} and {PORTS_EXPR}"
BPF_PROGRAM: tuple[tuple[int, int, int, int], ...] = (
    (40, 0, 0, 12), (21, 0, 18, 2048), (32, 0, 0, 26), (21, 2, 0, 3232235945), (32, 0, 0, 30),
    (21, 0, 14, 3232235945), (48, 0, 0, 23), (21, 0, 12, 6), (40, 0, 0, 20), (69, 10, 0, 8191),
    (177, 0, 0, 14), (72, 0, 0, 14), (21, 6, 0, 6900), (21, 5, 0, 6121), (21, 4, 0, 5121),
    (72, 0, 0, 16), (21, 2, 0, 6900), (21, 1, 0, 6121), (21, 0, 1, 5121), (6, 0, 0, 65535),
    (6, 0, 0, 0),
)  # fmt: skip
PORT_SERVER = {6900: "login", 6121: "char", 5121: "map"}
# the two instructions that carry the client address: the IPv4 source and destination compares
_ADDR_INSNS = (3, 5)
_BPF_JEQ_K = 21  # BPF_JMP | BPF_JEQ | BPF_K


def client_address(client_ip: str) -> ipaddress.IPv4Address:
    """The game PC's address, or ValueError: one unicast IPv4 address (never a name, a network,
    loopback, multicast or 0.0.0.0)."""
    ip = ipaddress.IPv4Address(client_ip.strip())
    if ip.is_unspecified or ip.is_loopback or ip.is_multicast or ip.is_reserved:
        raise ValueError(f"not a game PC's address: {client_ip!r}")
    return ip


def bpf_expr(client_ip: str) -> str:
    return f"host {client_address(client_ip)} and {PORTS_EXPR}"


def bpf_program(client_ip: str) -> tuple[tuple[int, int, int, int], ...]:
    """PURE: the kernel filter for ``client_ip`` -- BPF_PROGRAM with its address constant swapped
    in exactly the two ``host`` compares (checked, so a changed template can never be patched
    silently)."""
    k = int(client_address(client_ip))
    lab = int(ipaddress.IPv4Address(LAB_CLIENT_IP))
    prog = list(BPF_PROGRAM)
    for i in _ADDR_INSNS:
        code, jt, jf, old = prog[i]
        if (code, old) != (_BPF_JEQ_K, lab):
            raise ValueError(f"BPF_PROGRAM[{i}] is not the address compare it should be")
        prog[i] = (code, jt, jf, k)
    if sum(1 for ins in prog if ins[3] == lab) != (len(_ADDR_INSNS) if k == lab else 0):
        raise ValueError("BPF_PROGRAM carries the address somewhere else too")
    return tuple(prog)


ETH_P_ALL = 0x0003
SO_ATTACH_FILTER = 26  # not exposed by Python's socket module (asm-generic/socket.h)
SO_TIMESTAMPNS = 35
SCM_TIMESTAMPNS = SO_TIMESTAMPNS


class _SockFilter(ctypes.Structure):
    _fields_ = [("code", ctypes.c_ushort), ("jt", ctypes.c_ubyte), ("jf", ctypes.c_ubyte),
                ("k", ctypes.c_uint32)]  # fmt: skip


class _SockFprog(ctypes.Structure):
    _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.POINTER(_SockFilter))]


@dataclass(frozen=True)
class TcpSegment:
    t_real_ns: int
    src: str
    sport: int
    dst: str
    dport: int
    seq: int
    flags: int
    payload: bytes
    frame: bytes  # the whole Ethernet frame (for the pcapng)
    payload_offset: int  # where the TCP payload starts inside `frame`

    @property
    def syn(self) -> bool:
        return bool(self.flags & 0x02)

    @property
    def fin_or_rst(self) -> bool:
        return bool(self.flags & 0x05)


def parse_frame(frame: bytes, t_real_ns: int) -> TcpSegment | None:
    """Ethernet + IPv4 + TCP; anything else (or truncated) -> None."""
    if len(frame) < 54 or frame[12:14] != b"\x08\x00":
        return None
    ihl = (frame[14] & 0x0F) * 4
    if frame[23] != 6 or len(frame) < 14 + ihl + 20:
        return None
    total = struct.unpack_from("!H", frame, 16)[0]
    src = socket.inet_ntoa(frame[26:30])
    dst = socket.inet_ntoa(frame[30:34])
    t = 14 + ihl
    sport, dport, seq = struct.unpack_from("!HHI", frame, t)
    doff = (frame[t + 12] >> 4) * 4
    flags = frame[t + 13]
    start = t + doff
    end = min(len(frame), 14 + total)
    return TcpSegment(t_real_ns, src, sport, dst, dport, seq, flags, bytes(frame[start:end]),
                      bytes(frame), start)  # fmt: skip


class Capture:
    """Blocking reader; `read(timeout)` returns one frame with its kernel timestamp, or None."""

    def __init__(self, iface: str, client_ip: str = CLIENT_IP) -> None:
        program = bpf_program(client_ip)  # ValueError before any socket: a bad address never runs
        self.sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ALL))
        insns = (_SockFilter * len(program))(*[_SockFilter(*i) for i in program])
        self._fprog = _SockFprog(len(program), insns)  # kept alive for the kernel copy
        self._insns = insns
        self.sock.setsockopt(socket.SOL_SOCKET, SO_ATTACH_FILTER, bytes(self._fprog))
        self.sock.setsockopt(socket.SOL_SOCKET, SO_TIMESTAMPNS, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 << 20)
        self.sock.bind((iface, 0))

    def read(self, timeout: float) -> tuple[bytes, int] | None:
        self.sock.settimeout(timeout)
        try:
            data, anc, _flags, _addr = self.sock.recvmsg(65535, socket.CMSG_SPACE(16))
        except TimeoutError:
            return None
        t_real_ns = 0
        for level, ctype, cdata in anc:
            if level == socket.SOL_SOCKET and ctype == SCM_TIMESTAMPNS and len(cdata) >= 16:
                sec, nsec = struct.unpack_from("qq", cdata)
                t_real_ns = sec * 1_000_000_000 + nsec
        return data, t_real_ns

    def close(self) -> None:
        self.sock.close()
