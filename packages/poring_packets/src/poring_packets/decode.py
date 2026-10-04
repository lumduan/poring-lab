"""Decoders for the Phase 1 first slice (docs/phase1-plan.md section 4), PACKETVER 20211103 RE.

Every offset below was printed by the compiler (`offsetof`/`sizeof` against the pinned rAthena
headers, 2026-10-01), not counted by hand. Chat text is the client's raw bytes (cp874 in this
lab); servers NUL-terminate their strings, the client does not, so trailing NULs are stripped.
"""

import struct
from dataclasses import dataclass
from typing import Any

CODEPAGE = "cp874"

# rAthena map.hpp:499-502 (SP_*): the stat vars of ZC_PAR_CHANGE / ZC_LONGPAR_CHANGE we name.
STAT_NAMES = {
    0: "speed", 5: "hp", 6: "max_hp", 7: "sp", 8: "max_sp", 24: "weight", 25: "max_weight",
    20: "zeny", 1: "base_exp", 2: "job_exp", 11: "base_level", 55: "job_level",
}  # fmt: skip
VANISH_REASONS = {0: "out_of_sight", 1: "died", 2: "logged_out", 3: "teleport", 4: "trickdead"}


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


def _chat(kind: str, raw: bytes, gid: int | None = None, speaker: str | None = None) -> Decoded:
    body = raw_text(raw)
    msg = body.decode(CODEPAGE, errors="replace")
    if speaker is None and kind not in ("broadcast",):
        speaker, msg = split_name(msg)
    return Decoded("chat", {"kind": kind, "gid": gid, "speaker": speaker, "text": msg,
                            "raw_hex": body.hex().upper()})  # fmt: skip


def decode(server: str, direction: str, pid: int, b: bytes) -> Decoded | None:
    """One RO packet -> Decoded, or None for packets outside the first slice (counted elsewhere)."""
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
        if pid == 0x0088:
            return Decoded("entity_stop", {"gid": _u32(b, 2), "x": _u16(b, 6), "y": _u16(b, 8)})
        if pid in (0x0091, 0x0AC7):
            return Decoded("map_change", {"map": text(b[2:18]), "x": _u16(b, 18), "y": _u16(b, 20)})
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
        return None
    # client -> server (map only in the first slice)
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
    return None


def is_gm_command(d: Decoded) -> bool:
    """A client chat line whose text is an @command (validation GM commands are typed in chat)."""
    return d.type == "chat" and str(d.fields.get("text", "")).lstrip().startswith("@")
