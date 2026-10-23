"""2026-10-23 (Batt's decision 7: "the 160 'no icon while remembered' cases: check the status
packets"): the status-icon packets, decoded from synthetic packets built with the pinned rAthena
layout for PACKETVER 20211103 (decode.py cites it). OFFLINE ground truth only (ADR-0007)."""

import struct
from typing import Any

from poring_packets.decode import MAP_SC, decode
from poring_packets.events import StatusChange

AID = 2_000_002  # a synthetic account id (our block id)
AUTOGUARD = 58  # rAthena enum efst_type: EFST_AUTOGUARD


def dec(raw: bytes) -> dict[str, Any]:
    pid = struct.unpack_from("<H", raw)[0]
    d = decode("map", "sc", pid, raw)
    assert d is not None
    return {"type": d.type, **d.fields}


def test_a_timed_status_start_reads_the_icon_the_block_and_the_timers() -> None:
    raw = struct.pack("<HHIBIIiii", 0x0983, AUTOGUARD, AID, 1, 300_000, 299_000, 10, 0, 0)
    assert len(raw) == 29
    got = dec(raw)
    assert got == {
        "type": "status_change", "efst": AUTOGUARD, "gid": AID, "on": True,
        "total_ms": 300_000, "remain_ms": 299_000,
    }  # fmt: skip
    StatusChange.model_validate({**got, "t_mono_ns": 1, "server": "map", "dir": "sc",
                                 "packet_id": 0x0983})  # fmt: skip


def test_a_status_end_is_the_short_packet_with_no_timers() -> None:
    raw = struct.pack("<HHIB", 0x0196, AUTOGUARD, AID, 0)
    assert len(raw) == 9
    assert dec(raw) == {
        "type": "status_change", "efst": AUTOGUARD, "gid": AID, "on": False,
        "total_ms": None, "remain_ms": None,
    }  # fmt: skip
    assert {0x0196, 0x0983} <= set(MAP_SC)
