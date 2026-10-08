"""2026-10-07: NPC dialogs, shops, stat/skill points, equipment, item use and the action request,
decoded from synthetic packets built with the pinned rAthena layouts for PACKETVER 20211103
(decode.MAP_SC / MAP_CS carry the citations). Offline replay only: the sniffer image is not rebuilt.
All text and ids here are synthetic (no NPC script text, no item or skill data)."""

import importlib.util
import struct
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

sys.path.insert(0, str(Path(__file__).parent))
from helpers import cz_enter2, fall_entry, item_entry, pickup_ack, seg, table, var  # noqa: E402

from poring_packets import tables
from poring_packets.decode import MAP_CS, MAP_SC, STAT_NAMES, VARIABLE, decode
from poring_packets.events import (
    AttackRequest,
    NpcMenu,
    PacketEvent,
    ShopBuyList,
    parse_event,
)
from poring_packets.sniffer import Session

ROOT = Path(__file__).resolve().parents[3]
NPC = 110_000_123  # a synthetic NPC block id
AID = 2_000_001
THAI = "ทดสอบ หนึ่ง".encode("cp874")  # our own test words, not NPC script text
_EVENT: TypeAdapter[PacketEvent] = TypeAdapter(PacketEvent)


def npc_only(pid: int, gid: int = NPC) -> bytes:
    """The 6-byte id-only packets: ZC_WAIT_DIALOG, ZC_CLOSE_DIALOG, ZC_OPEN_EDITDLG(STR),
    ZC_SELECT_DEALTYPE, CZ_REQ_NEXT_SCRIPT, CZ_CLOSE_DIALOG."""
    return struct.pack("<HI", pid, gid)


def buy_entry(item: int, price: int, discount: int, item_type: int = 0) -> bytes:
    """ZC_PC_PURCHASE_ITEMLIST_sub at PACKETVER_RE_NUM >= 20211103: 19 bytes."""
    return struct.pack("<IIIBHI", item, price, discount, item_type, 0, 0)


def skill_entry(skill: int, level: int, sp: int = 0, rng: int = 1, up: int = 0) -> bytes:
    """SKILLDATA at PACKETVER_RE_NUM >= 20190807: 15 bytes (id, inf, level, sp, range, up, lv2)."""
    return struct.pack("<HiHHHBH", skill, 1, level, sp, rng, up, level)


# One valid sample per decoded (direction, id), in the exact wire layout.
SAMPLES: dict[tuple[str, int], bytes] = {
    # server -> client
    ("sc", 0x00B4): var(0x00B4, struct.pack("<I", NPC) + THAI + b"\0"),
    ("sc", 0x00B5): npc_only(0x00B5),
    ("sc", 0x00B6): npc_only(0x00B6),
    ("sc", 0x00B7): var(0x00B7, struct.pack("<I", NPC) + b"opt_a:opt_b::opt_d\0"),
    ("sc", 0x0142): npc_only(0x0142),
    ("sc", 0x01D4): npc_only(0x01D4),
    ("sc", 0x00C4): npc_only(0x00C4),
    ("sc", 0x0B77): var(0x0B77, buy_entry(9001, 50, 48) + buy_entry(9002, 1000, 960, 4)),
    ("sc", 0x00CA): struct.pack("<HB", 0x00CA, 0),
    ("sc", 0x00C7): var(0x00C7, struct.pack("<HII", 2, 25, 26) + struct.pack("<HII", 5, 7, 7)),
    ("sc", 0x00CB): struct.pack("<HB", 0x00CB, 1),
    ("sc", 0x00BC): struct.pack("<HHBB", 0x00BC, 13, 1, 2),
    ("sc", 0x010E): struct.pack("<HHHHHB", 0x010E, 7001, 3, 12, 1, 1),
    ("sc", 0x0B32): var(0x0B32, skill_entry(7001, 3, 12, 1, 1) + skill_entry(7002, 0)),
    ("sc", 0x0999): struct.pack("<HHIHB", 0x0999, 5, 0x0002, 4242, 0),
    ("sc", 0x099A): struct.pack("<HHIB", 0x099A, 5, 0x0002, 0),
    ("sc", 0x01C8): struct.pack("<HhIIhB", 0x01C8, 7, 9001, AID, 4, 1),
    # client -> server
    ("cs", 0x0090): struct.pack("<HIB", 0x0090, NPC, 1),
    ("cs", 0x00B8): struct.pack("<HIB", 0x00B8, NPC, 2),
    ("cs", 0x00B9): npc_only(0x00B9),
    ("cs", 0x0146): npc_only(0x0146),
    ("cs", 0x0143): struct.pack("<HIi", 0x0143, NPC, -5),
    ("cs", 0x01D5): var(0x01D5, struct.pack("<I", NPC) + THAI),  # the client sends no NUL
    ("cs", 0x00C5): struct.pack("<HIB", 0x00C5, NPC, 1),
    ("cs", 0x00C8): var(0x00C8, struct.pack("<HI", 3, 9001) + struct.pack("<HI", 1, 9002)),
    ("cs", 0x00C9): var(0x00C9, struct.pack("<HH", 2, 10)),
    ("cs", 0x00BB): struct.pack("<HHB", 0x00BB, 13, 1),
    ("cs", 0x0112): struct.pack("<HH", 0x0112, 7001),
    ("cs", 0x0998): struct.pack("<HHI", 0x0998, 5, 0x0002),
    ("cs", 0x00AB): struct.pack("<HH", 0x00AB, 5),
    ("cs", 0x0439): struct.pack("<HHI", 0x0439, 7, AID),
    ("cs", 0x0437): struct.pack("<HIB", 0x0437, 110_012_345, 7),
    # 2026-10-08 (loot@1 P2): floor items, pickups, drops (test_items.py has their semantics)
    ("sc", 0x0ADD): fall_entry(77, 9001, 3, 1, 150, 201, 4, 9, 2),
    ("sc", 0x009D): item_entry(78, 9002, 1, 151, 202, 1, 12, 3),
    ("sc", 0x00A1): struct.pack("<HI", 0x00A1, 77),
    ("sc", 0x0B41): pickup_ack(5, 2, 9001, 3, 0),
    ("sc", 0x00AF): struct.pack("<HHH", 0x00AF, 6, 1),
    ("cs", 0x0362): struct.pack("<HI", 0x0362, 77),
    ("cs", 0x0363): struct.pack("<HHH", 0x0363, 6, 1),
}
LISTS = {("sc", 0x0B77), ("sc", 0x00C7), ("sc", 0x0B32), ("cs", 0x00C8), ("cs", 0x00C9)}
LAYOUTS = {**{("sc", p): lay for p, lay in MAP_SC.items()},
           **{("cs", p): lay for p, lay in MAP_CS.items()}}  # fmt: skip


def dec(direction: str, pid: int, b: bytes | None = None) -> dict[str, Any]:
    d = decode("map", direction, pid, SAMPLES[(direction, pid)] if b is None else b)
    assert d is not None
    return {"type": d.type, **d.fields}


def test_every_decoded_id_has_a_sample_of_its_exact_size() -> None:
    assert set(SAMPLES) == set(LAYOUTS)
    for key, raw in SAMPLES.items():
        lay = LAYOUTS[key]
        if lay.size == VARIABLE:
            assert struct.unpack_from("<H", raw, 2)[0] == len(raw), key
        else:
            assert len(raw) == lay.size, key


# --- NPC dialogs ---------------------------------------------------------------------------------
def test_the_npc_dialog_chain() -> None:
    assert dec("cs", 0x0090) == {"type": "npc_contact", "npc_gid": NPC, "contact_type": 1}
    say = dec("sc", 0x00B4)
    assert say == {"type": "npc_say", "npc_gid": NPC, "text": "ทดสอบ หนึ่ง",
                   "raw_hex": THAI.hex().upper()}  # fmt: skip
    assert dec("sc", 0x00B5) == {"type": "npc_wait", "npc_gid": NPC}
    assert dec("cs", 0x00B9) == {"type": "npc_next_click", "npc_gid": NPC}
    menu = dec("sc", 0x00B7)
    assert menu["type"] == "npc_menu" and menu["npc_gid"] == NPC
    assert menu["options"] == ["opt_a", "opt_b", "", "opt_d"]  # the empty option still counts
    assert menu["raw_hex"] == b"opt_a:opt_b::opt_d".hex().upper()
    assert dec("cs", 0x00B8) == {"type": "npc_choose", "npc_gid": NPC, "choice": 2,
                                 "cancelled": False}  # fmt: skip
    cancel = dec("cs", 0x00B8, struct.pack("<HIB", 0x00B8, NPC, 255))
    assert cancel["choice"] == 255 and cancel["cancelled"]
    assert dec("sc", 0x0142) == {"type": "npc_number_prompt", "npc_gid": NPC}
    assert dec("cs", 0x0143) == {"type": "npc_number_input", "npc_gid": NPC, "value": -5}
    assert dec("sc", 0x01D4) == {"type": "npc_text_prompt", "npc_gid": NPC}
    typed = dec("cs", 0x01D5)
    assert typed == {"type": "npc_text_input", "npc_gid": NPC, "text": "ทดสอบ หนึ่ง",
                     "raw_hex": THAI.hex().upper()}  # fmt: skip
    assert dec("sc", 0x00B6) == {"type": "npc_close", "npc_gid": NPC}
    assert dec("cs", 0x0146) == {"type": "npc_close_click", "npc_gid": NPC}


def test_a_menu_with_one_option_and_a_cp874_option() -> None:
    one = dec("sc", 0x00B7, var(0x00B7, struct.pack("<I", NPC) + b"only\0"))
    assert one["options"] == ["only"]
    thai = dec("sc", 0x00B7, var(0x00B7, struct.pack("<I", NPC) + THAI + b":x\0"))
    assert thai["options"] == ["ทดสอบ หนึ่ง", "x"]


# --- shops ---------------------------------------------------------------------------------------
def test_the_shop_packets() -> None:
    assert dec("sc", 0x00C4) == {"type": "shop_deal_prompt", "npc_gid": NPC}
    assert dec("cs", 0x00C5) == {"type": "shop_deal_choice", "npc_gid": NPC, "deal": 1,
                                 "kind": "sell"}  # fmt: skip
    buy = dec("cs", 0x00C5, struct.pack("<HIB", 0x00C5, NPC, 0))
    assert buy["kind"] == "buy"
    assert dec("cs", 0x00C5, struct.pack("<HIB", 0x00C5, NPC, 9))["kind"] == "type9"
    assert dec("sc", 0x0B77)["items"] == [
        {"item_id": 9001, "price": 50, "discount_price": 48, "item_type": 0},
        {"item_id": 9002, "price": 1000, "discount_price": 960, "item_type": 4},
    ]
    assert dec("cs", 0x00C8)["items"] == [{"item_id": 9001, "amount": 3},
                                          {"item_id": 9002, "amount": 1}]  # fmt: skip
    assert dec("sc", 0x00CA) == {"type": "shop_buy_result", "result": 0, "ok": True}
    poor = dec("sc", 0x00CA, struct.pack("<HB", 0x00CA, 1))
    assert (poor["result"], poor["ok"]) == (1, False)
    assert dec("sc", 0x00C7)["items"] == [{"index": 2, "price": 25, "overcharge": 26},
                                          {"index": 5, "price": 7, "overcharge": 7}]  # fmt: skip
    assert dec("cs", 0x00C9)["items"] == [{"index": 2, "amount": 10}]
    assert dec("sc", 0x00CB) == {"type": "shop_sell_result", "result": 1, "ok": False}
    empty = dec("sc", 0x0B77, var(0x0B77, b""))
    assert empty["items"] == []  # a shop with nothing to sell is still a list


def test_zeny_is_already_a_named_stat_change() -> None:
    assert STAT_NAMES[20] == "zeny"
    d = decode("map", "sc", 0x00B1, struct.pack("<HHI", 0x00B1, 20, 12345))
    assert d is not None and d.fields == {"var": 20, "name": "zeny", "value": 12345}
    pts = decode("map", "sc", 0x00B0, struct.pack("<HHi", 0x00B0, 9, 47))
    assert pts is not None and pts.fields["name"] == "status_point"


# --- stats and skills ----------------------------------------------------------------------------
def test_stat_and_skill_points() -> None:
    assert dec("cs", 0x00BB) == {"type": "stat_raise_request", "stat": 13, "name": "str",
                                 "amount": 1}  # fmt: skip
    assert dec("sc", 0x00BC) == {"type": "stat_raise_result", "stat": 13, "name": "str",
                                 "ok": True, "value": 2}  # fmt: skip
    failed = dec("sc", 0x00BC, struct.pack("<HHBB", 0x00BC, 18, 0, 9))
    assert (failed["name"], failed["ok"], failed["value"]) == ("luk", False, 9)
    assert dec("cs", 0x0112) == {"type": "skill_up_request", "skill_id": 7001}
    assert dec("sc", 0x010E) == {"type": "skill_update", "skill_id": 7001, "level": 3, "sp": 12,
                                 "range": 1, "upgradable": True}  # fmt: skip
    assert dec("sc", 0x0B32)["skills"] == [
        {"skill_id": 7001, "level": 3, "sp": 12, "range": 1, "upgradable": True},
        {"skill_id": 7002, "level": 0, "sp": 0, "range": 1, "upgradable": False},
    ]


# --- equipment and items -------------------------------------------------------------------------
def test_equip_unequip_and_use_item() -> None:
    assert dec("cs", 0x0998) == {"type": "equip_request", "index": 5, "location": 2}
    assert dec("sc", 0x0999) == {"type": "equip_result", "index": 5, "location": 2,
                                 "view_sprite": 4242, "result": 0, "ok": True}  # fmt: skip
    low = dec("sc", 0x0999, struct.pack("<HHIHB", 0x0999, 5, 2, 0, 1))
    assert (low["result"], low["ok"]) == (1, False)  # 1 = level too low at this PACKETVER
    assert dec("cs", 0x00AB) == {"type": "unequip_request", "index": 5}
    assert dec("sc", 0x099A) == {"type": "unequip_result", "index": 5, "location": 2,
                                 "result": 0, "ok": True}  # fmt: skip
    stuck = dec("sc", 0x099A, struct.pack("<HHIB", 0x099A, 5, 2, 1))
    assert not stuck["ok"]  # the flag is inverted since 2011-08-24: 1 = failure
    assert dec("cs", 0x0439) == {"type": "use_item_request", "index": 7, "aid": AID}
    assert dec("sc", 0x01C8) == {"type": "use_item_result", "index": 7, "item_id": 9001,
                                 "aid": AID, "amount": 4, "ok": True}  # fmt: skip


# --- the action request --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("action", "kind", "is_attack"),
    [(0, "normal", True), (7, "repeat", True), (2, "sit", False), (3, "stand", False),
     (1, "pickup", False), (99, "type99", False)],
)  # fmt: skip
def test_the_action_request_tells_an_attack_from_sit_and_stand(
    action: int, kind: str, is_attack: bool
) -> None:
    raw = struct.pack("<HIB", 0x0437, 110_012_345, action)
    assert dec("cs", 0x0437, raw) == {"type": "attack_request", "target_gid": 110_012_345,
                                      "action": action, "kind": kind,
                                      "is_attack": is_attack}  # fmt: skip


def test_a_walk_click_is_still_a_move_request_not_an_attack() -> None:
    walk = decode("map", "cs", 0x035F, struct.pack("<H", 0x035F) + b"\x25\x83\x20")
    assert walk is not None and walk.type == "self_move_request"
    # the old CZ_REQUEST_ACT id is TickSend (11 bytes) at this PACKETVER: never an attack here
    assert decode("map", "cs", 0x0089, struct.pack("<HIB", 0x0089, 1, 0)) is None


# --- truncated or garbled: None, never an exception ----------------------------------------------
@pytest.mark.parametrize(("direction", "pid"), sorted(SAMPLES))
def test_truncated_or_garbled_packets_decode_to_none(direction: str, pid: int) -> None:
    raw = SAMPLES[(direction, pid)]
    lay = LAYOUTS[(direction, pid)]
    for cut in (b"", raw[:2], raw[:-1]):
        assert decode("map", direction, pid, cut) is None, cut.hex()
    if lay.size == VARIABLE:
        claims_more = raw[:2] + struct.pack("<H", len(raw) + 1) + raw[4:]
        assert decode("map", direction, pid, claims_more) is None
    if (direction, pid) in LISTS:  # a partial trailing entry, the length field consistent
        body = raw[4:] + b"\x00"
        assert decode("map", direction, pid, var(pid, body)) is None
    other = "cs" if direction == "sc" else "sc"
    if (other, pid) not in LAYOUTS:  # the id means nothing in the other direction
        assert decode("map", other, pid, raw) is None
    assert decode("char", direction, pid, raw) is None  # map-server packets only


def test_trailing_bytes_after_a_fixed_packet_are_ignored() -> None:
    """The framer hands over exactly the table's size; a longer buffer still reads the fields."""
    raw = SAMPLES[("cs", 0x0437)] + b"\xff\xff"
    assert dec("cs", 0x0437, raw)["target_gid"] == 110_012_345


# --- events: schema, round trip, the length table, the generator's guard -------------------------
@pytest.mark.parametrize(("direction", "pid"), sorted(SAMPLES))
def test_every_new_event_validates_and_round_trips(direction: str, pid: int) -> None:
    d = decode("map", direction, pid, SAMPLES[(direction, pid)])
    assert d is not None
    base = {"t_mono_ns": 5, "server": "map", "dir": direction, "packet_id": pid}
    ev = _EVENT.validate_python({"type": d.type, **d.fields, **base})
    again = parse_event(ev.model_dump_json())
    assert again == ev and again.type == d.type


def test_the_new_events_are_in_the_feed_and_the_schema() -> None:
    from poring_packets.events import json_schema, parse_feed

    menu = parse_feed(NpcMenu(t_mono_ns=1, server="map", dir="sc", packet_id=0x00B7, npc_gid=NPC,
                              options=["a", ""], raw_hex="613A").model_dump_json())  # fmt: skip
    assert isinstance(menu, NpcMenu) and menu.options == ["a", ""]
    defs = json_schema()["$defs"]
    for name in ("NpcMenu", "ShopBuyList", "ShopBuyListItem", "SkillList", "AttackRequest"):
        assert name in defs


def test_generated_table_frames_the_new_ids() -> None:
    if not tables.DEFAULT_TABLE.exists():
        pytest.skip("generated at build time: python3 scripts/gen_packet_tables.py")
    t = tables.load()
    for (direction, pid), lay in LAYOUTS.items():
        assert t.length("map", direction, pid) == lay.size, f"{direction} {pid:#06x}"


def test_the_generator_treats_the_new_ids_as_decoded() -> None:
    """scripts/gen_packet_tables.py fails on any rAthena/OpenKore disagreement for a DECODED id."""
    path = ROOT / "scripts" / "gen_packet_tables.py"
    spec = importlib.util.spec_from_file_location("gen_packet_tables", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert set(MAP_SC) | set(MAP_CS) <= mod.DECODED


# --- end to end: the offline replay --------------------------------------------------------------
EXTRA = {("map", d, pid): lay.size for (d, pid), lay in LAYOUTS.items()}


def test_the_replay_emits_the_new_events(tmp_path: Path) -> None:
    from poring_packets.pcapng import PcapngWriter
    from poring_packets.replay import replay

    path = tmp_path / "capture.pcapng"
    w = PcapngWriter(path)
    w.clock_sample({"mono_ns": 5_000_000_000, "real_ns": 1_000_000_000_000, "read_ns": 10})
    enter = cz_enter2(AID)
    cs = SAMPLES[("cs", 0x0090)] + SAMPLES[("cs", 0x00B8)] + SAMPLES[("cs", 0x0437)]
    sc = SAMPLES[("sc", 0x00B4)] + SAMPLES[("sc", 0x00B7)] + SAMPLES[("sc", 0x00CA)]
    t = 1_000_000_000_000
    for direction, seq, payload, flags in (
        ("cs", 0, b"", 0x02),
        ("sc", 0, b"", 0x12),
        ("cs", 1, enter, 0x18),
        ("cs", 1 + len(enter), cs, 0x18),
        ("sc", 1, sc, 0x18),
    ):
        w.packet(seg(direction, 5121, seq, payload, flags=flags, cport=50002).frame, t)
        t += 1_000_000
    w.close()
    s = Session(table(EXTRA), "192.168.1.169", set())
    events = [e for e in replay([path], s) if e.type not in ("unknown", "desync")]
    assert [e.type for e in events] == [
        "npc_contact", "npc_choose", "attack_request", "npc_say", "npc_menu", "shop_buy_result",
    ]  # fmt: skip
    attack = events[2]
    assert isinstance(attack, AttackRequest) and attack.packet_id == 0x0437
    assert (attack.target_gid, attack.kind, attack.is_attack) == (110_012_345, "repeat", True)
    assert events[4].packet_id == 0x00B7 and events[4].dir == "sc"
    assert all(e.t_mono_ns >= 5_000_000_000 for e in events)
    s2 = Session(table(EXTRA), "192.168.1.169", set())
    s2.feed(seg("cs", 5121, 1, enter, cport=50003))
    shop = s2.feed(seg("sc", 5121, 1, SAMPLES[("sc", 0x0B77)], cport=50003))
    assert isinstance(shop[0], ShopBuyList) and shop[0].items[1].discount_price == 960
