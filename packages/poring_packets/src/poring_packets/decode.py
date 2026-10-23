"""Decoders for the Phase 1 first slice (docs/phase1-plan.md section 4), PACKETVER 20211103 RE.

Every offset of the first slice was printed by the compiler (`offsetof`/`sizeof` against the pinned
rAthena headers, 2026-10-01), not counted by hand. The Phase 3 M3 additions (the ZC_NOTIFY_ACT
family, ZC_CHANGE_DIRECTION) were read off the packed structs and cross-checked against OpenKore's
unpack strings and the generated table's sizes (29/33/34 and 9 bytes). Chat text is the client's
raw bytes (cp874 in this lab); servers NUL-terminate their strings, the client does not, so
trailing NULs are stripped.

The 2026-10-07 additions (NPC dialogs, shops, stat/skill points, equipment, item use and the
action request; `MAP_SC` / `MAP_CS` below) are for OFFLINE REPLAY (ADR-0007): the running sniffer
image is not rebuilt for them. Each layout was read off the pinned rAthena struct or packet_db
entry FOR PACKETVER 20211103 (an RE client by config/packets.hpp: PACKETVER_RE_NUM = 20211103,
PACKETVER_MAIN_NUM undefined), its id and size checked against the generated length table, and
cross-checked against OpenKore's RagexeRE_2021_11_03 send/receive chain. These decoders never
raise on a short or garbled packet: a fixed packet shorter than its size, or a variable one whose
u16 length disagrees with its bytes, or whose entries do not divide evenly, decodes to None.

The 2026-10-08 additions (loot@1 P2: floor items, the pickup request and result, the drop) follow
the same rules, at the same pinned ref, and are OFFLINE ground truth only as well: the item-on-floor
entries ZC_ITEM_FALL_ENTRY5 / ZC_ITEM_ENTRY, its vanish ZC_ITEM_DISAPPEAR, ZC_ITEM_PICKUP_ACK,
ZC_ITEM_THROW_ACK, and the client's CZ_ITEM_PICKUP2 / CZ_ITEM_THROW2.
"""

import struct
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, NamedTuple

from poring_packets.tables import VARIABLE

CODEPAGE = "cp874"

# rAthena map.hpp:499-502 (SP_*): the stat vars of ZC_PAR_CHANGE / ZC_LONGPAR_CHANGE we name, and
# the status ids (SP_STR..SP_LUK, 13-18) of CZ_STATUS_CHANGE / ZC_STATUS_CHANGE_ACK. The point
# pools (9, 12) arrive as ZC_PAR_CHANGE after a raise.
STAT_NAMES = {
    0: "speed", 5: "hp", 6: "max_hp", 7: "sp", 8: "max_sp", 24: "weight", 25: "max_weight",
    20: "zeny", 1: "base_exp", 2: "job_exp", 11: "base_level", 55: "job_level",
    9: "status_point", 12: "skill_point",
    13: "str", 14: "agi", 15: "vit", 16: "int", 17: "dex", 18: "luk",
}  # fmt: skip
# rAthena clif.cpp:12256-12259 (CZ_ACK_SELECT_DEALTYPE): the shop's buy/sell choice.
DEAL_KINDS = {0: "buy", 1: "sell"}
VANISH_REASONS = {0: "out_of_sight", 1: "died", 2: "logged_out", 3: "teleport", 4: "trickdead"}
# rAthena clif.hpp:691-707 (enum e_damage_type): the action type of ZC_NOTIFY_ACT. Names follow
# the enum; 5, 6, 7 and 12 are skill-side types the enum itself marks as uncertain.
ACT_KINDS = {
    0: "normal", 1: "pickup", 2: "sit", 3: "stand", 4: "endure", 5: "splash", 6: "single",
    7: "repeat", 8: "multi_hit", 9: "multi_hit_endure", 10: "critical", 11: "lucky_dodge",
    12: "touch", 13: "multi_hit_critical", 14: "splash_endure",
}  # fmt: skip


class _ActTail(NamedTuple):
    """Where the ZC_NOTIFY_ACT variants differ, after the common head."""

    num: str  # damage @22 and damage2: int16 (0x008A) or int32
    sp: int | None  # IsSPDamage, 0x08C8 only
    div: int
    action: int
    damage2: int


# The ZC_NOTIFY_ACT family (rAthena map/packets.hpp:1412-1455, one struct per PACKETVER range;
# OpenKore Receive/ServerType0.pm '008A' / '02E1' / '08C8' agree). Common head: src id @2, target id
# @6, server tick @10, src speed @14, damage motion @18, 4 bytes each. This lab (20211103) gets
# 0x08C8; the older two are decoded too, so a replay of another client's capture still reads.
ACT_LAYOUTS = {
    0x008A: _ActTail("<h", None, 24, 26, 27),  # 29 bytes
    0x02E1: _ActTail("<i", None, 26, 28, 29),  # 33 bytes
    0x08C8: _ActTail("<i", 26, 27, 29, 30),  # 34 bytes
}


@dataclass(frozen=True)
class Decoded:
    """An event type name + its fields (the sniffer adds time, stream and flags)."""

    type: str
    fields: dict[str, Any]


def text(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode(CODEPAGE, errors="replace")


def raw_text(raw: bytes) -> bytes:
    return raw.rstrip(b"\0")


def pos(b: bytes, off: int) -> tuple[int, int, int]:
    """RBUFPOS: 3 bytes -> x (10 bits), y (10 bits), dir (4 bits)  (clif.cpp:194-211)."""
    p0, p1, p2 = b[off], b[off + 1], b[off + 2]
    return (p0 << 2) | (p1 >> 6), ((p1 & 0x3F) << 4) | (p2 >> 4), p2 & 0x0F


def pos2(b: bytes, off: int) -> tuple[int, int, int, int]:
    """RBUFPOS2: 6 bytes -> x0, y0, x1, y1; byte 5 sub-cell nibbles ignored (clif.cpp:214-240)."""
    p = b[off : off + 6]
    x0 = (p[0] << 2) | (p[1] >> 6)
    y0 = ((p[1] & 0x3F) << 4) | (p[2] >> 4)
    x1 = ((p[2] & 0x0F) << 6) | (p[3] >> 2)
    y1 = ((p[3] & 0x03) << 8) | p[4]
    return x0, y0, x1, y1


def split_name(message: str) -> tuple[str | None, str]:
    """'Name : text' -> (Name, text) only when the separator is present (system text has none)."""
    name, sep, rest = message.partition(" : ")
    return (name, rest) if sep else (None, message)


def _u16(b: bytes, o: int) -> int:
    return int(struct.unpack_from("<H", b, o)[0])


def _u32(b: bytes, o: int) -> int:
    return int(struct.unpack_from("<I", b, o)[0])


def _i32(b: bytes, o: int) -> int:
    return int(struct.unpack_from("<i", b, o)[0])


def _i16(b: bytes, o: int) -> int:
    return int(struct.unpack_from("<h", b, o)[0])


def _act(lay: _ActTail, b: bytes) -> Decoded:
    """ZC_NOTIFY_ACT: `src_gid` acts on `target_gid` (rAthena clif_damage / clif_takeitem /
    clif_sitting / clif_standing, clif.cpp:5217-5360). Sit, stand and pickup leave the tick, the
    speeds and the damage at 0."""
    action = b[lay.action]
    return Decoded("act", {
        "src_gid": _u32(b, 2), "target_gid": _u32(b, 6), "server_tick": _u32(b, 10),
        "src_speed": _i32(b, 14), "dmotion": _i32(b, 18),
        "damage": int(struct.unpack_from(lay.num, b, 22)[0]),
        "damage2": int(struct.unpack_from(lay.num, b, lay.damage2)[0]),
        "div": _u16(b, lay.div), "action": action, "kind": ACT_KINDS.get(action, f"type{action}"),
        "sp_damage": None if lay.sp is None else bool(b[lay.sp]),
    })  # fmt: skip


def _chat(kind: str, raw: bytes, gid: int | None = None, speaker: str | None = None) -> Decoded:
    body = raw_text(raw)
    msg = body.decode(CODEPAGE, errors="replace")
    if speaker is None and kind not in ("broadcast",):
        speaker, msg = split_name(msg)
    return Decoded("chat", {"kind": kind, "gid": gid, "speaker": speaker, "text": msg,
                            "raw_hex": body.hex().upper()})  # fmt: skip


# --- 2026-10-07: NPC dialogs, shops, stat/skill points, equipment, items, the action request -----
class _Layout(NamedTuple):
    """A map-server packet: its fixed size, or VARIABLE (a u16 length @2) with a fixed `head`
    before its entries."""

    size: int
    fn: Callable[[bytes], Decoded | None]
    head: int = 4


def _fits(lay: _Layout, b: bytes) -> bool:
    """Complete and self-consistent: the framer hands over whole packets, so a short fixed packet or
    a length field that disagrees with the bytes means a truncated or garbled one."""
    if lay.size != VARIABLE:
        return len(b) >= lay.size
    return len(b) >= lay.head and _u16(b, 2) == len(b)


def _entries(b: bytes, head: int, size: int) -> range | None:
    """The offsets of a list's fixed-size entries after `head`; None unless they divide evenly."""
    return None if (len(b) - head) % size else range(head, len(b), size)


def _text_fields(raw: bytes) -> dict[str, str]:
    body = raw_text(raw)
    return {"text": body.decode(CODEPAGE, errors="replace"), "raw_hex": body.hex().upper()}


def _npc_id(etype: str) -> Callable[[bytes], Decoded]:
    """The dialog packets that carry only the NPC's block id (u32 @2)."""
    return lambda b: Decoded(etype, {"npc_gid": _u32(b, 2)})


def _u16_event(etype: str, field: str) -> Callable[[bytes], Decoded]:
    """The requests that carry one u16 @2."""
    return lambda b: Decoded(etype, {field: _u16(b, 2)})


def _npc_say(b: bytes) -> Decoded:
    # ZC_SAY_DIALOG (packets_struct.hpp:5486-5492): len @2, npc id @4, NUL-terminated text @8.
    # 0x0972 (ZC_SAY_DIALOG2 with a type byte) is PACKETVER_MAIN_NUM >= 20220504 only.
    return Decoded("npc_say", {"npc_gid": _u32(b, 4), **_text_fields(b[8:])})


def _npc_menu(b: bytes) -> Decoded:
    # ZC_MENU_LIST (packets.hpp:761-767): len @2, npc id @4, options @8 joined by ':' (script.cpp
    # buildin_select). Empty options are kept: CZ_CHOOSE_MENU's 1-based choice counts them.
    # cp874 is single-byte, so splitting the raw bytes on 0x3A is safe.
    body = raw_text(b[8:])
    options = [o.decode(CODEPAGE, errors="replace") for o in body.split(b":")]
    return Decoded("npc_menu", {"npc_gid": _u32(b, 4), "options": options,
                                "raw_hex": body.hex().upper()})  # fmt: skip


def _npc_contact(b: bytes) -> Decoded:
    # CZ_CONTACTNPC (packets_struct.hpp:5412-5417): block id @2, type u8 @6 (1 = click). The server
    # treats a monster's or player's id as a continuous attack (clif.cpp:12228-12232).
    return Decoded("npc_contact", {"npc_gid": _u32(b, 2), "contact_type": b[6]})


def _npc_choose(b: bytes) -> Decoded:
    # CZ_CHOOSE_MENU (packet_db 0x00B8, 7 bytes, pos 2,6): npc id @2, choice u8 @6; 1-254 is the
    # 1-based option, 255 is cancel (clif.cpp:13312-13318).
    choice = b[6]
    return Decoded("npc_choose", {"npc_gid": _u32(b, 2), "choice": choice,
                                  "cancelled": choice == 255})  # fmt: skip


def _npc_number_input(b: bytes) -> Decoded:
    # CZ_INPUT_EDITDLG (packets.hpp:1837-1842): npc id @2, value int32 @6.
    return Decoded("npc_number_input", {"npc_gid": _u32(b, 2), "value": _i32(b, 6)})


def _npc_text_input(b: bytes) -> Decoded:
    # CZ_INPUT_EDITDLGSTR (packets.hpp:1844-1850): len @2, npc id @4, text @8 (the client does not
    # NUL-terminate it at PACKETVER >= 20151001, clif.cpp:13390-13392).
    return Decoded("npc_text_input", {"npc_gid": _u32(b, 4), **_text_fields(b[8:])})


def _shop_deal_choice(b: bytes) -> Decoded:
    # CZ_ACK_SELECT_DEALTYPE (packets.hpp:1519-1524): npc id @2, type u8 @6.
    deal = b[6]
    return Decoded("shop_deal_choice", {"npc_gid": _u32(b, 2), "deal": deal,
                                        "kind": DEAL_KINDS.get(deal, f"type{deal}")})  # fmt: skip


def _shop_buy_list(b: bytes) -> Decoded | None:
    # ZC_PC_PURCHASE_ITEMLIST 0x0B77 (packets_struct.hpp:3045-3063, PACKETVER_RE_NUM >= 20211103;
    # 0x00C6 before): 19-byte entries @4 -- item id u32 @0, price u32 @4, discount price u32 @8,
    # item type u8 @12, view sprite u16 @13, location u32 @15.
    offs = _entries(b, 4, 19)
    if offs is None:
        return None
    return Decoded("shop_buy_list", {"items": [
        {"item_id": _u32(b, o), "price": _u32(b, o + 4), "discount_price": _u32(b, o + 8),
         "item_type": b[o + 12]} for o in offs]})  # fmt: skip


def _shop_buy_request(b: bytes) -> Decoded | None:
    # CZ_PC_PURCHASE_ITEMLIST 0x00C8 (packets_struct.hpp:3083-3096): 6-byte entries @4 -- amount
    # u16 @0, item id u32 @2 (u32 at PACKETVER_RE_NUM >= 20180704).
    offs = _entries(b, 4, 6)
    if offs is None:
        return None
    return Decoded("shop_buy_request", {"items": [
        {"item_id": _u32(b, o + 2), "amount": _u16(b, o)} for o in offs]})  # fmt: skip


def _shop_sell_list(b: bytes) -> Decoded | None:
    # ZC_PC_SELL_ITEMLIST 0x00C7 (packets.hpp:742-753): 10-byte entries @4 -- inventory index u16
    # @0, price u32 @2, overcharge price u32 @6.
    offs = _entries(b, 4, 10)
    if offs is None:
        return None
    return Decoded("shop_sell_list", {"items": [
        {"index": _u16(b, o), "price": _u32(b, o + 2), "overcharge": _u32(b, o + 6)}
        for o in offs]})  # fmt: skip


def _shop_sell_request(b: bytes) -> Decoded | None:
    # CZ_PC_SELL_ITEMLIST 0x00C9 (packets.hpp:301-311): 4-byte entries @4 -- inventory index u16
    # @0, amount u16 @2.
    offs = _entries(b, 4, 4)
    if offs is None:
        return None
    return Decoded("shop_sell_request", {"items": [
        {"index": _u16(b, o), "amount": _u16(b, o + 2)} for o in offs]})  # fmt: skip


def _result(etype: str) -> Callable[[bytes], Decoded]:
    """ZC_PC_PURCHASE_RESULT (packets.hpp:41-45) / ZC_PC_SELL_RESULT (clif.cpp:12329-12342): one
    result byte @2, 0 = the deal completed."""
    return lambda b: Decoded(etype, {"result": b[2], "ok": b[2] == 0})


def _stat_raise_request(b: bytes) -> Decoded:
    # CZ_STATUS_CHANGE (packet_db 0x00BB, 5 bytes, pos 2,4): status id u16 @2, amount u8 @4
    # (clif.cpp:12716-12732).
    stat = _u16(b, 2)
    return Decoded("stat_raise_request", {"stat": stat, "name": STAT_NAMES.get(stat, f"var{stat}"),
                                          "amount": b[4]})  # fmt: skip


def _stat_raise_result(b: bytes) -> Decoded:
    # ZC_STATUS_CHANGE_ACK (packets_struct.hpp:4219-4225): status id u16 @2, ok u8 @4, the new
    # value u8 @5 (capped at 255, clif.cpp:4291-4300).
    stat = _u16(b, 2)
    return Decoded("stat_raise_result", {"stat": stat, "name": STAT_NAMES.get(stat, f"var{stat}"),
                                         "ok": bool(b[4]), "value": b[5]})  # fmt: skip


def _skill_update(b: bytes) -> Decoded:
    # ZC_SKILLINFO_UPDATE (packets.hpp:489-497): skill id u16 @2, level u16 @4, sp u16 @6, range
    # u16 @8, upgradable u8 @10. pc_skillup sends it after a level-up (pc.cpp:9166-9169).
    return Decoded("skill_update", {"skill_id": _u16(b, 2), "level": _u16(b, 4), "sp": _u16(b, 6),
                                    "range": _u16(b, 8), "upgradable": bool(b[10])})  # fmt: skip


def _skill_list(b: bytes) -> Decoded | None:
    # ZC_SKILLINFO_LIST 0x0B32 (packets_struct.hpp:4238-4280, PACKETVER_RE_NUM >= 20190807; 0x010F
    # before): 15-byte SKILLDATA entries @4 -- id u16 @0, inf i32 @2, level u16 @6, sp u16 @8,
    # range u16 @10, upgradable u8 @12, level2 u16 @13.
    offs = _entries(b, 4, 15)
    if offs is None:
        return None
    return Decoded("skill_list", {"skills": [
        {"skill_id": _u16(b, o), "level": _u16(b, o + 6), "sp": _u16(b, o + 8),
         "range": _u16(b, o + 10), "upgradable": bool(b[o + 12])} for o in offs]})  # fmt: skip


def _equip_request(b: bytes) -> Decoded:
    # CZ_REQ_WEAR_EQUIP 0x0998 (packets.hpp:1502-1509, PACKETVER >= 20120925): inventory index u16
    # @2, location u32 @4.
    return Decoded("equip_request", {"index": _u16(b, 2), "location": _u32(b, 4)})


def _equip_result(b: bytes) -> Decoded:
    # ZC_REQ_WEAR_EQUIP_ACK 0x0999 (packets_struct.hpp:1268-1276, PACKETVER_RE_NUM >= 20121107):
    # index u16 @2, location u32 @4, view sprite u16 @8, result u8 @10. At this PACKETVER 0 = ok,
    # 1 = level too low, 2 = failure (clif.hpp:523-528).
    result = b[10]
    return Decoded("equip_result", {"index": _u16(b, 2), "location": _u32(b, 4),
                                    "view_sprite": _u16(b, 8), "result": result,
                                    "ok": result == 0})  # fmt: skip


def _unequip_result(b: bytes) -> Decoded:
    # ZC_REQ_TAKEOFF_EQUIP_ACK 0x099A (packets.hpp:1006-1013, PACKETVER >= 20130000): index u16
    # @2, location u32 @4, flag u8 @8 -- inverted at PACKETVER >= 20110824: 0 = ok
    # (clif.cpp:4338-4351).
    result = b[8]
    return Decoded("unequip_result", {"index": _u16(b, 2), "location": _u32(b, 4),
                                      "result": result, "ok": result == 0})  # fmt: skip


def _use_item_request(b: bytes) -> Decoded:
    # CZ_USE_ITEM2 (packet_db 0x0439, 8 bytes, pos 2,4; the client's item_use since 2008):
    # inventory index u16 @2, account id u32 @4 (clif.cpp:12076-12101).
    return Decoded("use_item_request", {"index": _u16(b, 2), "aid": _u32(b, 4)})


def _use_item_result(b: bytes) -> Decoded:
    # ZC_USE_ITEM_ACK2 0x01C8 (packets_struct.hpp:2577-2589 + useItemAckType, 311-315): index
    # i16 @2, item id u32 @4, user's id u32 @8, amount left i16 @12, ok u8 @14. A success goes to
    # the AREA, so other players' uses arrive too (clif.cpp:4468-4497).
    return Decoded("use_item_result", {"index": _i16(b, 2), "item_id": _u32(b, 4),
                                       "aid": _u32(b, 8), "amount": _i16(b, 12),
                                       "ok": bool(b[14])})  # fmt: skip


# --- 2026-10-08 (loot@1 P2): floor items, the pickup request and its result, the drop ------------
# rAthena pc.hpp:113-122 (enum e_additem_result): the result byte of ZC_ITEM_PICKUP_ACK. 6 is also
# the generic refusal clif_parse_TakeItem sends when a pickup fails before pc_additem runs (too far,
# loot priority, dead, cannot act: clif.cpp:12016-12034, "Client REQUIRES a fail packet").
PICKUP_RESULTS = {
    0: "ok", 1: "invalid", 2: "overweight", 3: "item", 4: "inventory_full", 5: "over_amount",
    6: "refused", 7: "stack_limit",
}  # fmt: skip


def _floor_item_fall(b: bytes) -> Decoded:
    # ZC_ITEM_FALL_ENTRY5 0x0ADD (packets_struct.hpp:597-618 struct packet_dropflooritem;
    # dropflooritemType = 0x0ADD at PACKETVER >= 20180418, packets_struct.hpp:130-131; sent by
    # clif_dropflooritem to the AREA, clif.cpp:861-924; 24 bytes = the OpenKore table's size):
    # floor item id u32 @2, item id u32 @6 (u32 at PACKETVER_RE_NUM >= 20180704), item type u16
    # @10, identified u8 @12, x i16 @13, y i16 @15, sub-cell x u8 @17, y u8 @18, amount i16 @19,
    # drop effect u8 @21 + mode i16 @22. clif.cpp's comment still says <name id>.W: the struct
    # wins. A FRESH drop (a kill, a player's throw, a GM's @item that overflows to the floor).
    return Decoded("floor_item_appear", {
        "kind": "fall", "floor_id": _u32(b, 2), "item_id": _u32(b, 6), "item_type": _u16(b, 10),
        "identified": bool(b[12]), "x": _i16(b, 13), "y": _i16(b, 15), "sub_x": b[17],
        "sub_y": b[18], "amount": _i16(b, 19), "drop_effect": b[21] != 0,
    })  # fmt: skip


def _floor_item_in_sight(b: bytes) -> Decoded:
    # ZC_ITEM_ENTRY 0x009D (packets_struct.hpp:2350-2364; packets.hpp:2211; 19 bytes): floor item
    # id u32 @2, item id u32 @6, identified u8 @10, x u16 @11, y u16 @13, amount u16 @15, sub-cell
    # x u8 @17, y u8 @18. An item ALREADY on the floor coming into view (map entry, a walk:
    # clif_getareachar_item, clif.cpp:5390-5410). No item type in this one.
    return Decoded("floor_item_appear", {
        "kind": "in_sight", "floor_id": _u32(b, 2), "item_id": _u32(b, 6), "item_type": None,
        "identified": bool(b[10]), "x": _u16(b, 11), "y": _u16(b, 13), "sub_x": b[17],
        "sub_y": b[18], "amount": _u16(b, 15), "drop_effect": False,
    })  # fmt: skip


def _floor_item_vanish(b: bytes) -> Decoded:
    # ZC_ITEM_DISAPPEAR 0x00A1 (packets.hpp:611-615; 6 bytes): floor item id u32 @2. Sent to the
    # AREA when the item leaves the map (picked up, or its flooritem_lifetime ran out:
    # map_clearflooritem), or to ONE client when it goes out of that client's sight
    # (clif_clearflooritem with a tsd, clif.cpp:928-941). The packet does not say which.
    return Decoded("floor_item_vanish", {"floor_id": _u32(b, 2)})


def _pickup_result(b: bytes) -> Decoded:
    # ZC_ITEM_PICKUP_ACK 0x0B41 (packets_struct.hpp:540-595 at PACKETVER_RE_NUM >= 20200723; 70
    # bytes = the generated table's size): inventory index u16 @2, amount u16 @4, item id u32 @6,
    # identified u8 @10, damaged u8 @11, 4 cards u32 @12-27, equip location u32 @28, item type u8
    # @32, result u8 @33, then hire expiry i32 @34, bind type u16 @38, 5 random options (5 bytes
    # each) @40-64, favorite u8 @65, look u16 @66, refine u8 @68, grade u8 @69. SELF only
    # (clif_additem, clif.cpp:2831-2890). NOT pickup-specific: pc_additem sends it for EVERY item
    # that enters the inventory (an @item, an NPC, a trade), so a floor pickup is this + our act of
    # kind pickup on the floor id + that id's vanish. A failure zeroes everything but the index
    # (2) and the result.
    result = b[33]
    return Decoded("pickup_result", {
        "index": _u16(b, 2), "amount": _u16(b, 4), "item_id": _u32(b, 6),
        "identified": bool(b[10]), "item_type": b[32], "result": result,
        "reason": PICKUP_RESULTS.get(result, f"result{result}"), "ok": result == 0,
        "refine": b[68],
    })  # fmt: skip


def _pickup_request(b: bytes) -> Decoded:
    # CZ_ITEM_PICKUP2 (packet_db 0x0362, 6 bytes, pos 2: the clif_shuffle.hpp:4732 block for
    # PACKETVER > 20180307 -> clif_parse_TakeItem, clif.cpp:12002-12035): floor item id u32 @2.
    return Decoded("pickup_request", {"floor_id": _u32(b, 2)})


def _drop_request(b: bytes) -> Decoded:
    # CZ_ITEM_THROW2 (packet_db 0x0363, 6 bytes, pos 2,4: clif_shuffle.hpp:4733 ->
    # clif_parse_DropItem, clif.cpp:12038-12073): the client's inventory index u16 @2, amount u16
    # @4.
    return Decoded("drop_request", {"index": _u16(b, 2), "amount": _u16(b, 4)})


def _status_change(b: bytes) -> Decoded:
    # ZC_MSG_STATE_CHANGE 0x0196 (9 bytes) and, with battle_config display_status_timers on and the
    # status starting, ZC_MSG_STATE_CHANGE2 0x0983 (29 bytes; PACKETVER >= 20120618)
    # (clif_status_change_sub, clif.cpp:6472-6532 at e985006): the status ICON id u16 @2 (rAthena
    # enum efst_type, status.hpp:1453; EFST_AUTOGUARD = 58), the block id u32 @4, the flag u8 @8
    # (1 on, 0 off); 0x0983 adds the total u32 @9 and the remaining u32 @13 (client ms) and val1-3
    # i32 @17 / 21 / 25. Sent to the block's AREA: every status of every unit in sight.
    timed = len(b) >= 29
    return Decoded("status_change", {
        "efst": _u16(b, 2), "gid": _u32(b, 4), "on": b[8] != 0,
        "total_ms": _u32(b, 9) if timed else None, "remain_ms": _u32(b, 13) if timed else None,
    })  # fmt: skip


def _drop_result(b: bytes) -> Decoded:
    # ZC_ITEM_THROW_ACK 0x00AF (clif_dropitem, clif.cpp:2893-2903; 6 bytes): the client's
    # inventory index u16 @2, amount u16 @4 -- removed from the inventory. A refused drop answers
    # with amount 0 (clif.cpp:12071-12072).
    amount = _u16(b, 4)
    return Decoded("drop_result", {"index": _u16(b, 2), "amount": amount, "ok": amount > 0})


def _attack_request(b: bytes) -> Decoded:
    # CZ_REQUEST_ACT2 (packet_db 0x0437, 7 bytes, pos 2,6: the clif_shuffle.hpp:4749 block for
    # PACKETVER > 20180307; 0x0089 is CZ_REQUEST_ACT's id only on older clients). Target id u32 @2,
    # action u8 @6: 0 = attack once, 7 = keep attacking, 2 = sit, 3 = stand (clif.cpp:11807-11831).
    action = b[6]
    return Decoded("attack_request", {"target_gid": _u32(b, 2), "action": action,
                                      "kind": ACT_KINDS.get(action, f"type{action}"),
                                      "is_attack": action in (0, 7)})  # fmt: skip


# server -> client. Ids and sizes match the generated length table (rAthena struct sizes; 0x00CB
# and 0x01C8 come from OpenKore's client table: no rAthena HEADER_ pair). The id-only dialog
# packets: ZC_WAIT_DIALOG (the 'next' button, packets_struct.hpp:5513), ZC_CLOSE_DIALOG (the
# 'close' button, packets.hpp:755), ZC_OPEN_EDITDLG / ZC_OPEN_EDITDLGSTR (number / text input
# boxes, packets.hpp:769-779) and ZC_SELECT_DEALTYPE (the shop's buy/sell box, packets.hpp:736):
# npc id u32 @2, 6 bytes.
MAP_SC: dict[int, _Layout] = {
    0x00B4: _Layout(VARIABLE, _npc_say, head=8),  # ZC_SAY_DIALOG
    0x00B5: _Layout(6, _npc_id("npc_wait")),  # ZC_WAIT_DIALOG
    0x00B6: _Layout(6, _npc_id("npc_close")),  # ZC_CLOSE_DIALOG
    0x00B7: _Layout(VARIABLE, _npc_menu, head=8),  # ZC_MENU_LIST
    0x0142: _Layout(6, _npc_id("npc_number_prompt")),  # ZC_OPEN_EDITDLG
    0x01D4: _Layout(6, _npc_id("npc_text_prompt")),  # ZC_OPEN_EDITDLGSTR
    0x00C4: _Layout(6, _npc_id("shop_deal_prompt")),  # ZC_SELECT_DEALTYPE
    0x0B77: _Layout(VARIABLE, _shop_buy_list),  # ZC_PC_PURCHASE_ITEMLIST
    0x00CA: _Layout(3, _result("shop_buy_result")),  # ZC_PC_PURCHASE_RESULT
    0x00C7: _Layout(VARIABLE, _shop_sell_list),  # ZC_PC_SELL_ITEMLIST
    0x00CB: _Layout(3, _result("shop_sell_result")),  # ZC_PC_SELL_RESULT
    0x00BC: _Layout(6, _stat_raise_result),  # ZC_STATUS_CHANGE_ACK
    0x010E: _Layout(11, _skill_update),  # ZC_SKILLINFO_UPDATE
    0x0B32: _Layout(VARIABLE, _skill_list),  # ZC_SKILLINFO_LIST
    0x0999: _Layout(11, _equip_result),  # ZC_REQ_WEAR_EQUIP_ACK (V5)
    0x099A: _Layout(9, _unequip_result),  # ZC_REQ_TAKEOFF_EQUIP_ACK (V5)
    0x01C8: _Layout(15, _use_item_result),  # ZC_USE_ITEM_ACK2
    # 2026-10-08 (loot@1 P2): floor items and the pickup result
    0x0ADD: _Layout(24, _floor_item_fall),  # ZC_ITEM_FALL_ENTRY5
    0x009D: _Layout(19, _floor_item_in_sight),  # ZC_ITEM_ENTRY
    0x00A1: _Layout(6, _floor_item_vanish),  # ZC_ITEM_DISAPPEAR
    0x0B41: _Layout(70, _pickup_result),  # ZC_ITEM_PICKUP_ACK (V7 + grade)
    0x00AF: _Layout(6, _drop_result),  # ZC_ITEM_THROW_ACK
    0x0196: _Layout(9, _status_change),  # ZC_MSG_STATE_CHANGE (2026-10-23, Batt decision 7)
    0x0983: _Layout(29, _status_change),  # ZC_MSG_STATE_CHANGE2 (with timers)
}  # fmt: skip
# client -> server: the map server's packet_db at PACKETVER 20211103 (clif_packetdb.hpp +
# clif_shuffle.hpp, last write wins), where each id maps to the clif_parse_* handler named.
# CZ_REQ_NEXT_SCRIPT / CZ_CLOSE_DIALOG (rAthena's name for CZ_REQ_CLOSE_SCRIPT, packets.hpp:1852):
# npc id u32 @2, 6 bytes (clif.cpp:13346-13421). CZ_UPGRADE_SKILLLEVEL: skill id u16 @2
# (clif.cpp:12755-12760). CZ_REQ_TAKEOFF_EQUIP: inventory index u16 @2 (clif.cpp:12164-12183).
# Inventory indexes are the client's (the server's index + 2), as on the wire.
MAP_CS: dict[int, _Layout] = {
    0x0090: _Layout(7, _npc_contact),  # CZ_CONTACTNPC -> NpcClicked
    0x00B8: _Layout(7, _npc_choose),  # CZ_CHOOSE_MENU -> NpcSelectMenu
    0x00B9: _Layout(6, _npc_id("npc_next_click")),  # CZ_REQ_NEXT_SCRIPT -> NpcNextClicked
    0x0146: _Layout(6, _npc_id("npc_close_click")),  # CZ_CLOSE_DIALOG -> NpcCloseClicked
    0x0143: _Layout(10, _npc_number_input),  # CZ_INPUT_EDITDLG -> NpcAmountInput
    0x01D5: _Layout(VARIABLE, _npc_text_input, head=8),  # CZ_INPUT_EDITDLGSTR -> NpcStringInput
    0x00C5: _Layout(7, _shop_deal_choice),  # CZ_ACK_SELECT_DEALTYPE -> NpcBuySellSelected
    0x00C8: _Layout(VARIABLE, _shop_buy_request),  # CZ_PC_PURCHASE_ITEMLIST -> NpcBuyListSend
    0x00C9: _Layout(VARIABLE, _shop_sell_request),  # CZ_PC_SELL_ITEMLIST -> NpcSellListSend
    0x00BB: _Layout(5, _stat_raise_request),  # CZ_STATUS_CHANGE -> StatusUp
    0x0112: _Layout(4, _u16_event("skill_up_request", "skill_id")),  # CZ_UPGRADE_SKILLLEVEL
    0x0998: _Layout(8, _equip_request),  # CZ_REQ_WEAR_EQUIP (V5) -> EquipItem
    0x00AB: _Layout(4, _u16_event("unequip_request", "index")),  # CZ_REQ_TAKEOFF_EQUIP
    0x0439: _Layout(8, _use_item_request),  # CZ_USE_ITEM2 -> UseItem
    0x0437: _Layout(7, _attack_request),  # CZ_REQUEST_ACT2 -> ActionRequest
    0x0362: _Layout(6, _pickup_request),  # CZ_ITEM_PICKUP2 -> TakeItem (2026-10-08)
    0x0363: _Layout(6, _drop_request),  # CZ_ITEM_THROW2 -> DropItem (2026-10-08)
}  # fmt: skip


def _decode_map(table: dict[int, _Layout], pid: int, b: bytes) -> Decoded | None:
    lay = table.get(pid)
    return lay.fn(b) if lay is not None and _fits(lay, b) else None


def decode(server: str, direction: str, pid: int, b: bytes) -> Decoded | None:
    """One RO packet -> Decoded, or None for a packet we do not decode (counted elsewhere) or, for
    the 2026-10-07 map packets, a truncated or garbled one."""
    if direction == "sc":
        if server == "login" and pid == 0x0AC4:
            return Decoded("login_accepted", {"aid": _u32(b, 8), "sex": b[46]})
        if server == "char" and pid == 0x0AC5:
            return Decoded("char_selected", {"char_id": _u32(b, 2), "map": text(b[6:22]),
                                             "map_port": _u16(b, 26)})  # fmt: skip
        if server != "map":
            return None
        if pid == 0x02EB:
            x, y, d = pos(b, 6)
            return Decoded("map_enter", {"server_tick": _u32(b, 2), "x": x, "y": y, "facing": d})
        if pid == 0x007F:
            return Decoded("time_sync", {"server_tick": _u32(b, 2)})
        if pid == 0x0087:
            x0, y0, x1, y1 = pos2(b, 6)
            return Decoded("self_move", {"server_tick": _u32(b, 2), "x0": x0, "y0": y0,
                                         "x1": x1, "y1": y1})  # fmt: skip
        if pid in (0x09FD, 0x09FE, 0x09FF):
            kind = {0x09FD: "move", 0x09FE: "new", 0x09FF: "stand"}[pid]
            name_off = {0x09FD: 90, 0x09FE: 83, 0x09FF: 84}[pid]
            # AID @5 is the block id (rAthena bl.id): the identity ZC_NOTIFY_VANISH / STOPMOVE
            # use. GID @9 is the char_id, 0 for every non-player (found live 2026-10-01: keyed
            # by GID, all monsters collapsed into one entity).
            # effectState @19 (rAthena's sc.option): an NPC sent with OPTION_INVISIBLE/HIDE/CLOAK
            # is drawn as NOTHING (found 2026-10-04: prt_church's six "Single Army" event NPCs)
            f: dict[str, Any] = {"kind": kind, "gid": _u32(b, 5), "char_id": _u32(b, 9),
                                 "objtype": b[4], "effect_state": _u32(b, 19),
                                 "speed": _u16(b, 13), "job": _u16(b, 23),
                                 "name": text(b[name_off : name_off + 24])}  # fmt: skip
            if pid == 0x09FD:
                x0, y0, x1, y1 = pos2(b, 67)
                f.update(x=x0, y=y0, x1=x1, y1=y1, move_start_tick=_u32(b, 37))
            else:
                x, y, heading = pos(b, 63)
                # RO heading 0..7 (0 = north, counter-clockwise); a 4-bit field, so guard it
                f.update(x=x, y=y, heading=heading if heading < 8 else None)
            return Decoded("entity_appear", f)
        if pid == 0x0080:
            return Decoded("entity_vanish", {"gid": _u32(b, 2), "reason": b[6]})
        if pid in ACT_LAYOUTS:
            return _act(ACT_LAYOUTS[pid], b)
        if pid == 0x009C:
            # ZC_CHANGE_DIRECTION (packets.hpp:688-694): id @2, head dir u16 @6, body dir u8 @8
            body = b[8]
            return Decoded("entity_turn", {"gid": _u32(b, 2), "head_dir": _u16(b, 6),
                                           "heading": body if body < 8 else None})  # fmt: skip
        if pid == 0x0088:
            return Decoded("entity_stop", {"gid": _u32(b, 2), "x": _u16(b, 6), "y": _u16(b, 8)})
        if pid in (0x0091, 0x0AC7):
            return Decoded("map_change", {"map": text(b[2:18]), "x": _u16(b, 18), "y": _u16(b, 20)})
        if pid in (0x0A27, 0x013D):
            # ZC_RECOVERY (packets.hpp:1209-1222; clif_heal, clif.cpp:6840): the HEAL a unit gets --
            # a potion, a skill, the regen ticks of Increase / Moving HP Recovery -- as an AMOUNT,
            # not the new absolute value. var u16 @2 (5 = hp, 7 = sp); amount i32 @4 (0x0A27,
            # PACKETVER >= 20141022: the lab client) or i16 @4 (0x013D). Without it a stat_change
            # series misses every regen tick (the Crusader's HP labels, 2026-10-21).
            var = _u16(b, 2)
            amount = _i32(b, 4) if pid == 0x0A27 else _i16(b, 4)
            return Decoded("recovery", {"var": var, "name": STAT_NAMES.get(var, f"var{var}"),
                                        "amount": amount})  # fmt: skip
        if pid in (0x00B0, 0x00B1):
            var = _u16(b, 2)
            value = _i32(b, 4) if pid == 0x00B0 else _u32(b, 4)
            return Decoded("stat_change", {"var": var, "name": STAT_NAMES.get(var, f"var{var}"),
                                           "value": value})  # fmt: skip
        if pid == 0x0ACB:
            var = _u16(b, 2)
            value = int(struct.unpack_from("<q", b, 4)[0])
            return Decoded("stat_change", {"var": var, "name": STAT_NAMES.get(var, f"var{var}"),
                                           "value": value})  # fmt: skip
        if pid == 0x008D:
            return _chat("public", b[8:], gid=_u32(b, 4))
        if pid == 0x008E:
            return _chat("self", b[4:])
        if pid == 0x0109:
            return _chat("party", b[8:], gid=_u32(b, 4))
        if pid == 0x017F:
            return _chat("guild", b[4:])
        if pid == 0x09DE:
            return _chat("whisper_in", b[33:], gid=_u32(b, 4), speaker=text(b[8:32]))
        if pid == 0x009A:
            return _chat("broadcast", b[4:])
        if pid == 0x01C3:
            return _chat("broadcast", b[16:])
        if pid == 0x02C1:
            return _chat("npc", b[12:], gid=_u32(b, 4))
        return _decode_map(MAP_SC, pid, b)
    # client -> server (map only)
    if server != "map":
        return None
    if pid == 0x035F:
        x, y, _ = pos(b, 2)
        return Decoded("self_move_request", {"x": x, "y": y})
    if pid == 0x00F3:
        return _chat("public", b[4:])
    if pid == 0x0108:
        return _chat("party", b[4:])
    if pid == 0x017E:
        return _chat("guild", b[4:])
    if pid == 0x0096:
        return _chat("whisper_out", b[28:], speaker=text(b[4:28]))
    return _decode_map(MAP_CS, pid, b)


def is_gm_command(d: Decoded) -> bool:
    """A client chat line whose text is an @command (validation GM commands are typed in chat)."""
    return d.type == "chat" and str(d.fields.get("text", "")).lstrip().startswith("@")
