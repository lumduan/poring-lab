"""2026-10-08 (loot@1 P2): floor items, the pickup request and result, the drop -- decoded from
synthetic packets built with the pinned rAthena layouts for PACKETVER 20211103 (decode.py cites
each). OFFLINE ground truth only (ADR-0007). Ids, items and cells are synthetic (no item data).
The generic checks (exact sizes, truncation to None, schema round trip, the length table, the
generator's DECODED set) run over these ids in test_interactions.py."""

import struct
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from helpers import (  # noqa: E402
    cz_enter2,
    fall_entry,
    item_entry,
    pickup_ack,
    seg,
    table,
    zc_notify_act,
)

from poring_packets.decode import MAP_CS, MAP_SC, PICKUP_RESULTS, decode
from poring_packets.events import FloorItemAppear, PickupResult
from poring_packets.sniffer import Session

AID = 2_000_002  # a synthetic account id (our block id)
FLOOR = 4_321  # a synthetic floor item block id
MOB = 110_012_345


def dec(direction: str, raw: bytes) -> dict[str, Any]:
    pid = struct.unpack_from("<H", raw)[0]
    d = decode("map", direction, pid, raw)
    assert d is not None
    return {"type": d.type, **d.fields}


def test_a_fresh_drop_reads_the_item_its_cell_and_amount() -> None:
    raw = fall_entry(FLOOR, 9001, 3, 1, 150, 201, 4, 9, 2, effect=1, mode=0)
    assert len(raw) == MAP_SC[0x0ADD].size == 24
    assert dec("sc", raw) == {
        "type": "floor_item_appear", "kind": "fall", "floor_id": FLOOR, "item_id": 9001,
        "item_type": 3, "identified": True, "x": 150, "y": 201, "sub_x": 4, "sub_y": 9,
        "amount": 2, "drop_effect": True,
    }  # fmt: skip


def test_the_item_id_is_four_bytes_at_this_packetver() -> None:
    """clif.cpp's comment still says <name id>.W; the struct is u32 at PACKETVER_RE_NUM >=
    20180704, so an id above 65535 must survive (and the fields after it stay aligned)."""
    raw = fall_entry(FLOOR, 500_123, 4, 0, 12, 34, 0, 0, 1)
    d = dec("sc", raw)
    got = (d["item_id"], d["x"], d["y"], d["amount"], d["identified"])
    assert got == (500_123, 12, 34, 1, False)
    raw2 = item_entry(FLOOR, 500_124, 1, 13, 35, 7)
    d2 = dec("sc", raw2)
    assert (d2["item_id"], d2["x"], d2["y"], d2["amount"]) == (500_124, 13, 35, 7)


def test_an_item_already_on_the_floor_coming_into_sight() -> None:
    raw = item_entry(FLOOR + 1, 9002, 1, 151, 202, 1, sub_x=12, sub_y=3)
    assert len(raw) == MAP_SC[0x009D].size == 19
    assert dec("sc", raw) == {
        "type": "floor_item_appear", "kind": "in_sight", "floor_id": FLOOR + 1, "item_id": 9002,
        "item_type": None, "identified": True, "x": 151, "y": 202, "sub_x": 12, "sub_y": 3,
        "amount": 1, "drop_effect": False,
    }  # fmt: skip


def test_the_floor_item_vanish() -> None:
    assert dec("sc", struct.pack("<HI", 0x00A1, FLOOR)) == {
        "type": "floor_item_vanish", "floor_id": FLOOR,
    }  # fmt: skip


def test_a_successful_pickup_result() -> None:
    raw = pickup_ack(7, 2, 9001, 3, 0, refine=0)
    assert len(raw) == MAP_SC[0x0B41].size == 70
    assert dec("sc", raw) == {
        "type": "pickup_result", "index": 7, "amount": 2, "item_id": 9001, "identified": True,
        "item_type": 3, "result": 0, "reason": "ok", "ok": True, "refine": 0,
    }  # fmt: skip


def test_a_refused_pickup_is_the_generic_fail_packet() -> None:
    """clif_parse_TakeItem's fail packet: clif_additem(sd, 0, 0, 6) -- everything zero but the
    client index (0 + 2) and the result."""
    raw = pickup_ack(2, 0, 0, 0, 6)
    d = dec("sc", raw)
    assert (d["ok"], d["result"], d["reason"], d["amount"], d["item_id"]) == (
        False, 6, "refused", 0, 0,
    )  # fmt: skip
    assert dec("sc", pickup_ack(2, 0, 0, 0, 2))["reason"] == "overweight"
    assert dec("sc", pickup_ack(2, 0, 0, 0, 99))["reason"] == "result99"
    assert PICKUP_RESULTS[4] == "inventory_full"


def test_the_refine_byte_sits_at_the_end() -> None:
    """refiningLevel moved behind the options at PACKETVER_RE_NUM >= 20200723 (offset 68)."""
    assert dec("sc", pickup_ack(9, 1, 9003, 5, 0, refine=7))["refine"] == 7


def test_pickup_and_drop_requests_and_the_drop_result() -> None:
    assert dec("cs", struct.pack("<HI", 0x0362, FLOOR)) == {
        "type": "pickup_request", "floor_id": FLOOR,
    }  # fmt: skip
    assert dec("cs", struct.pack("<HHH", 0x0363, 6, 1)) == {
        "type": "drop_request", "index": 6, "amount": 1,
    }  # fmt: skip
    assert dec("sc", struct.pack("<HHH", 0x00AF, 6, 1)) == {
        "type": "drop_result", "index": 6, "amount": 1, "ok": True,
    }  # fmt: skip
    assert dec("sc", struct.pack("<HHH", 0x00AF, 6, 0))["ok"] is False  # a refused drop
    assert set(MAP_CS) >= {0x0362, 0x0363}
    # the ids mean nothing the other way round (0x0362/0x0363 are cs only here)
    assert decode("map", "sc", 0x0362, struct.pack("<HI", 0x0362, FLOOR)) is None


def test_a_kill_its_drop_and_our_pickup_end_to_end() -> None:
    """The sequence the loot@1 verifier reads offline: the monster dies, its loot falls, our client
    asks for it after walking in, the server shows our pickup act, the item enters the inventory,
    the floor item vanishes, the weight rises."""
    extra = {("map", d, pid): lay.size for d, tbl in (("sc", MAP_SC), ("cs", MAP_CS))
             for pid, lay in tbl.items()}  # fmt: skip
    extra[("map", "sc", 0x08C8)] = 34
    s = Session(table(extra), "192.168.1.169", set())
    enter = cz_enter2(AID)
    s.feed(seg("cs", 5121, 0, b"", flags=0x02))
    s.feed(seg("sc", 5121, 0, b"", flags=0x12))
    s.feed(seg("cs", 5121, 1, enter))
    sc = (
        struct.pack("<HIB", 0x0080, MOB, 1)  # entity_vanish: died
        + fall_entry(FLOOR, 9001, 3, 1, 150, 201, 4, 9, 1)
        + zc_notify_act(AID, FLOOR, 0, 0, 0, 0, 1)  # our act of kind pickup on the floor item
        + pickup_ack(7, 1, 9001, 3, 0)
        + struct.pack("<HI", 0x00A1, FLOOR)
        + struct.pack("<HHi", 0x00B0, 24, 910)  # weight (tenths)
    )
    pick = s.feed(seg("cs", 5121, 1 + len(enter), struct.pack("<HI", 0x0362, FLOOR)))
    events = s.feed(seg("sc", 5121, 1, sc))
    assert [e.type for e in pick] == ["pickup_request"]
    assert [e.type for e in events] == [
        "entity_vanish", "floor_item_appear", "act", "pickup_result", "floor_item_vanish",
        "stat_change",
    ]  # fmt: skip
    drop, act, result = events[1], events[2], events[3]
    assert isinstance(drop, FloorItemAppear) and (drop.kind, drop.x, drop.y) == ("fall", 150, 201)
    assert act.type == "act" and act.kind == "pickup" and act.target_gid == drop.floor_id
    assert isinstance(result, PickupResult) and result.ok and result.item_id == drop.item_id
