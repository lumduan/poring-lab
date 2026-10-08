"""scripts/gen_packet_tables.py: a struct with its own length field is VARIABLE, whatever rAthena
calls the field (2026-10-08: `packetSize` was missed, so four chat-room / whisper packets were
tabled FIXED at their head size)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "gen_packet_tables.py"


@pytest.fixture(scope="module")
def gen() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gen_packet_tables", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PRE = """
const int16 HEADER_ZC_ROOM_NEWENTRY = 0xd7;
struct PACKET_ZC_ROOM_NEWENTRY { int16 packetType; uint16 packetSize; int32 owner; int32 id;
  uint16 limit; uint16 users; uint8 type; char title[]; } __attribute__((packed));
const int16 HEADER_ZC_SAY_DIALOG = 0xb4;
struct PACKET_ZC_SAY_DIALOG { int16 PacketType; int16 PacketLength; uint32 NpcID; char message[]; }
  __attribute__((packed));
const int16 HEADER_ZC_SOMETHING_LEN = 0x1234;
struct PACKET_ZC_SOMETHING_LEN { int16 packetType; int16 packetLen; char x[]; }
  __attribute__((packed));
const int16 HEADER_ZC_PERSONAL_INFOMATION = 0x97b;
struct PACKET_ZC_PERSONAL_INFOMATION { int16 packetType; int16 length; int32 total_exp;
  struct PACKET_ZC_PERSONAL_INFOMATION_SUB details[]; } __attribute__((packed));
const int16 HEADER_ZC_ITEM_DISAPPEAR = 0xa1;
struct PACKET_ZC_ITEM_DISAPPEAR { int16 packetType; uint32 itemAid; } __attribute__((packed));
"""


def test_every_length_field_name_makes_a_packet_variable(gen: ModuleType) -> None:
    pairs = gen.parse_preprocessed(PRE)
    assert pairs["ZC_ROOM_NEWENTRY"] == (0xD7, True)  # packetSize: was tabled FIXED 17
    assert pairs["ZC_SAY_DIALOG"] == (0xB4, True)  # PacketLength
    assert pairs["ZC_SOMETHING_LEN"] == (0x1234, True)  # packetLen
    assert pairs["ZC_PERSONAL_INFOMATION"] == (0x97B, True)  # `length` + a flexible array
    assert pairs["ZC_ITEM_DISAPPEAR"] == (0xA1, False)  # no length field: fixed


def test_a_fixed_dumper_line_uses_sizeof_and_a_variable_one_minus_one(gen: ModuleType) -> None:
    src = gen.dumper_source("common", gen.parse_preprocessed(PRE))
    assert '"struct ZC_ROOM_NEWENTRY %d %d\\n", (int)HEADER_ZC_ROOM_NEWENTRY, -1' in src
    assert "(int)sizeof(struct PACKET_ZC_ITEM_DISAPPEAR)" in src
