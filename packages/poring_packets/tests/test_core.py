import ctypes
import ctypes.util
import hashlib
import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from helpers import (  # noqa: E402
    ac_accept_login,
    ca_login,
    cz_enter2,
    frame,
    seg,
    table,
    var,
    wpos,
    wpos2,
)

from poring_packets import tables
from poring_packets.capture import BPF_EXPR, BPF_PROGRAM, parse_frame
from poring_packets.clock import ClockMap, Sample
from poring_packets.decode import decode, is_gm_command, pos, pos2
from poring_packets.events import json_schema
from poring_packets.framing import RoFramer, TcpReassembler
from poring_packets.pcapng import PcapngWriter, redact
from poring_packets.sniffer import Session
from poring_packets.world import Walk, path_cells

ROOT = Path(__file__).resolve().parents[3]


# --- tables ------------------------------------------------------------------------------------
def test_table_load_checks_the_lock(tmp_path: Path) -> None:
    body = json.dumps({"entries": [{"server": "map", "dir": "sc", "id": 135, "len": 12,
                                    "source": "rathena"}]}).encode()  # fmt: skip
    t, lock = tmp_path / "lengths.json", tmp_path / "lock.json"
    t.write_bytes(body)
    lock.write_text(json.dumps({"output_sha256": hashlib.sha256(body).hexdigest()}))
    assert tables.load(t, lock).length("map", "sc", 0x87) == 12
    lock.write_text(json.dumps({"output_sha256": "0" * 64}))
    with pytest.raises(tables.TableError):
        tables.load(t, lock)
    with pytest.raises(tables.TableError):
        tables.load(tmp_path / "missing.json", lock)


def test_generated_table_matches_lock_and_knows_the_first_slice() -> None:
    if not tables.DEFAULT_TABLE.exists():
        pytest.skip("generated at build time: python3 scripts/gen_packet_tables.py")
    t = tables.load()
    for key, length in {("map", "sc", 0x0087): 12, ("map", "cs", 0x0436): 23,
                        ("login", "cs", 0x0064): 55, ("map", "sc", 0x09FD): -1,
                        ("char", "cs", 0x0065): 17}.items():  # fmt: skip
        assert t.length(*key) == length


# --- framing -----------------------------------------------------------------------------------
def test_framer_handles_split_and_merged_segments() -> None:
    f = RoFramer(table(), "map", "sc")
    chat = var(0x008E, b"lab_1 : hi\0")
    move = struct.pack("<HI", 0x0087, 1234) + wpos2(10, 20, 12, 22)
    stream = chat + move + chat
    out = [p.packet_id for i in range(0, len(stream), 5) for p in f.feed(stream[i : i + 5], 0)]
    assert out == [0x008E, 0x0087, 0x008E]
    assert f.stats.packets == 3 and not f.stats.unknown_ids


def test_framer_counts_unknown_ids_and_resyncs() -> None:
    f = RoFramer(table(), "map", "sc")
    good = struct.pack("<HI", 0x007F, 99)
    stream = good + b"\xef\xbe\x01\x02\x03" + good * 4
    got = list(f.feed(stream, 0))
    assert got[0].packet_id == 0x007F and len(got) == 5
    assert (
        f.stats.unknown_ids == {0xBEEF: 1} and f.stats.desyncs == 1 and f.stats.skipped_bytes == 5
    )


def test_char_stream_skips_the_four_raw_aid_bytes() -> None:
    f = RoFramer(table(), "char", "sc", raw_prefix=4)
    got = list(f.feed(struct.pack("<I", 2000000) + var(0x082D, b"\0" * 25), 0))
    assert f.raw == struct.pack("<I", 2000000) and [p.packet_id for p in got] == [0x082D]


def test_reassembler_orders_dedups_and_waits_for_gaps() -> None:
    r = TcpReassembler()
    assert r.feed(100, b"", syn=True) == b""
    assert r.feed(101, b"abc") == b"abc"
    assert r.feed(107, b"ghi") == b""  # out of order: held
    assert r.feed(101, b"abc") == b""  # retransmit
    assert r.feed(104, b"def") == b"defghi"


# --- decoders, world, clock ---------------------------------------------------------------------
def test_position_codecs_round_trip() -> None:
    assert pos(wpos(123, 456, 5), 0) == (123, 456, 5)
    assert pos2(wpos2(1, 2, 1000, 1001), 0) == (1, 2, 1000, 1001)


def test_decode_self_move_and_thai_chat() -> None:
    d = decode("map", "sc", 0x0087, struct.pack("<HI", 0x0087, 777) + wpos2(10, 20, 13, 20))
    assert d is not None and d.fields == {
        "server_tick": 777,
        "x0": 10,
        "y0": 20,
        "x1": 13,
        "y1": 20,
    }
    thai = "สวัสดี ทดสอบ".encode("cp874")
    c = decode("map", "sc", 0x008E, var(0x008E, b"lab_1 : " + thai + b"\0"))
    assert c is not None and c.fields["speaker"] == "lab_1" and c.fields["text"] == "สวัสดี ทดสอบ"
    assert (
        c.fields["raw_hex"] == (b"lab_1 : " + thai).hex().upper()
    )  # chatlog stores the whole line
    gm = decode("map", "cs", 0x00F3, var(0x00F3, b"gm1 : @where"))
    assert gm is not None and is_gm_command(gm)


def test_walk_interpolation_uses_rathena_step_costs() -> None:
    assert path_cells(0, 0, 3, 1) == [(1, 1), (2, 1), (3, 1)]  # diagonal first, then straight
    w = Walk(0, 0, 3, 1, start_tick=1000, speed=150)
    assert w.position_at(1000) == (0.0, 0.0)
    assert w.position_at(1210) == (1.0, 1.0)  # diagonal = 150 * 14 / 10 = 210 ms
    assert w.position_at(1210 + 150 + 75) == (2.5, 1.0)
    assert w.position_at(5000) == (3.0, 1.0)


def test_clock_map_detects_steps_and_maps_by_segment() -> None:
    c = ClockMap()
    assert not c.add(Sample(mono_ns=1_000, real_ns=10_000, read_ns=50))
    assert c.add(Sample(mono_ns=2_000_000_000, real_ns=2_000_009_000 + 10_000_000, read_ns=50))
    assert c.steps == 1
    assert c.to_mono(10_500) == 1_500  # first segment's offset
    assert c.to_mono(2_000_009_000 + 10_000_000) == 2_000_000_000


# --- pcapng + credentials -----------------------------------------------------------------------
def test_login_payload_is_zeroed_before_writing(tmp_path: Path) -> None:
    payload = ca_login(b"agentuser", b"s3cretpass")
    fr = frame("192.168.1.169", 50000, "10.210.96.6", 6900, 1, payload)
    red = redact(fr, 54, 6900)
    assert b"s3cretpass" not in red and b"agentuser" not in red and red[54:56] == b"\x64\x00"
    w = PcapngWriter(tmp_path / "c.pcapng")
    w.packet(red, 1_700_000_000_123_456_789)
    w.clock_sample({"mono_ns": 1, "real_ns": 2, "read_ns": 3})
    w.close()
    data = (tmp_path / "c.pcapng").read_bytes()
    assert data[:4] == b"\x0a\x0d\x0d\x0a" and b"s3cretpass" not in data
    assert (
        redact(frame("10.210.96.6", 5121, "192.168.1.169", 50000, 1, b"\x87\x00abc"), 54, 50000)[
            54:
        ]
        == b"\x87\x00abc"
    )


def test_bpf_constant_matches_libpcap() -> None:
    lib_name = ctypes.util.find_library("pcap")
    if not lib_name:
        pytest.skip("libpcap not installed")
    lib = ctypes.CDLL(lib_name)

    class Insn(ctypes.Structure):
        _fields_ = [("code", ctypes.c_ushort), ("jt", ctypes.c_ubyte), ("jf", ctypes.c_ubyte),
                    ("k", ctypes.c_uint32)]  # fmt: skip

    class Prog(ctypes.Structure):
        _fields_ = [("bf_len", ctypes.c_uint), ("bf_insns", ctypes.POINTER(Insn))]

    prog = Prog()
    assert (
        lib.pcap_compile_nopcap(65535, 1, ctypes.byref(prog), BPF_EXPR.encode(), 1, 0xFFFFFFFF) == 0
    )
    ins = prog.bf_insns
    got = tuple((ins[i].code, ins[i].jt, ins[i].jf, ins[i].k)
                for i in range(prog.bf_len))  # fmt: skip
    assert got == BPF_PROGRAM


def test_parse_frame() -> None:
    s = parse_frame(frame("192.168.1.169", 50000, "10.210.96.6", 5121, 7, b"\x7d\x00"), 5)
    assert s is not None and (s.sport, s.dport, s.seq, s.payload) == (50000, 5121, 7, b"\x7d\x00")


# --- end to end session ------------------------------------------------------------------------
def test_session_tags_validation_accounts_and_gm_commands() -> None:
    s = Session(table(), "192.168.1.169", {"gmuser"})
    s.clock.add(Sample(mono_ns=0, real_ns=0, read_ns=1))
    s.feed(seg("cs", 6900, 0, b"", flags=0x02))
    s.feed(seg("sc", 6900, 0, b"", flags=0x12))
    s.feed(seg("cs", 6900, 1, ca_login(b"gmuser", b"pw")))
    s.feed(seg("sc", 6900, 1, ac_accept_login(2000001)))
    assert 2000001 in s.validation_aids
    s.feed(seg("cs", 5121, 0, b"", flags=0x02, cport=50002))
    s.feed(seg("sc", 5121, 0, b"", flags=0x12, cport=50002))
    s.feed(seg("cs", 5121, 1, cz_enter2(2000001), cport=50002))
    ev = s.feed(seg("cs", 5121, 24, var(0x00F3, b"gm1 : @where"), cport=50002))
    assert len(ev) == 1 and ev[0].validation_account and ev[0].gm_command
    move = struct.pack("<HI", 0x0087, 5000) + wpos2(10, 20, 12, 20)
    ev2 = s.feed(seg("sc", 5121, 1, move, cport=50002))
    assert ev2[0].type == "self_move" and ev2[0].gm_command  # inside the GM window
    assert s.stats(0).self_x is not None


def test_committed_packet_schema_matches_models() -> None:
    committed = ROOT / "packages" / "poring_packets" / "schema" / "packets.schema.json"
    assert json.loads(committed.read_text()) == json_schema(), "run scripts/gen_protocol.sh"


def test_entity_identity_is_the_block_id_not_the_char_id() -> None:
    """ZC_NOTIFY_NEWENTRY11 (0x09FE): AID @5 is the block id, GID @9 the char_id (0 for mobs)."""
    from poring_packets.decode import decode

    b = bytearray(107)
    b[0:2] = (0x09FE).to_bytes(2, "little")
    b[2:4] = (107).to_bytes(2, "little")
    b[4] = 5  # objtype: monster
    b[5:9] = (110012345).to_bytes(4, "little")  # block id
    b[9:13] = (0).to_bytes(4, "little")  # char_id: none for a monster
    b[23:25] = (1002).to_bytes(2, "little")  # job: Poring
    b[83:89] = b"Poring"
    d = decode("map", "sc", 0x09FE, bytes(b))
    assert d is not None
    assert (d.fields["gid"], d.fields["char_id"], d.fields["job"]) == (110012345, 0, 1002)
