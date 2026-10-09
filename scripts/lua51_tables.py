#!/usr/bin/env python3
"""Read the constant TABLES out of a compiled Lua 5.1 chunk (the client's .lub data files), without
running Lua: a symbolic walk of the main function's straight-line table-building code.

    lua51_tables.py FILE.lub [FILE.lub ...] [--global NAME] [--limit N]

Why: the client's NPC tables are compiled Lua (data\\luafiles514\\lua files\\datainfo\\
npcidentity.lub: `jobtbl.JT_X = id`; jobname.lub: `JobNameTable[jobtbl.JT_X] = "SPRITE"`). The
sprite file the client loads for an NPC id is the cross-check for rAthena's npc.hpp constants
(labels v2, N1).

What runs: NOTHING from the file. The chunk is parsed (the documented Lua 5.1 binary format: header,
function prototype, instructions, constants), and only these instructions are followed, in order,
over a register file of Python values: MOVE, LOADK, LOADBOOL, LOADNIL, GETGLOBAL, SETGLOBAL,
GETTABLE, SETTABLE, NEWTABLE, SETLIST, RETURN. Anything else (calls, arithmetic, jumps, closures)
makes its target register UNKNOWN and is counted; nothing is ever called. Globals carry over from
one chunk to the next, so a table keyed by another file's constants resolves (read npcidentity
before jobname). Our own code from the public format description (lopcodes.h / lundump.c layout as
documented in "A No-Frills Introduction to Lua 5.1 VM Instructions"); no Lua source is copied.

The tables are CLIENT data: print or write them only to /dev/shm or data/ (never committed).
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SIGNATURE = b"\x1bLua"
FIELDS_PER_FLUSH = 50  # LFIELDS_PER_FLUSH, SETLIST's batch
BITRK = 1 << 8
OPS = ("MOVE", "LOADK", "LOADBOOL", "LOADNIL", "GETUPVAL", "GETGLOBAL", "GETTABLE", "SETGLOBAL",
       "SETUPVAL", "SETTABLE", "NEWTABLE", "SELF", "ADD", "SUB", "MUL", "DIV", "MOD", "POW", "UNM",
       "NOT", "LEN", "CONCAT", "JMP", "EQ", "LT", "LE", "TEST", "TESTSET", "CALL", "TAILCALL",
       "RETURN", "FORLOOP", "FORPREP", "TFORLOOP", "SETLIST", "CLOSE", "CLOSURE",
       "VARARG")  # fmt: skip
# instructions that write no register (or only jump/compare): nothing to mark unknown
NO_TARGET = frozenset({"SETGLOBAL", "SETUPVAL", "SETTABLE", "JMP", "EQ", "LT", "LE", "TEST",
                       "SETLIST", "CLOSE", "RETURN"})  # fmt: skip


class LuaFormatError(ValueError):
    """Not a Lua 5.1 chunk this reader understands."""


class Unknown:
    """A value the walk could not know (the result of an instruction it does not follow)."""

    _inst: Unknown | None = None

    def __new__(cls) -> Unknown:
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst

    def __repr__(self) -> str:
        return "UNKNOWN"


UNKNOWN = Unknown()


@dataclass(eq=False)
class Table:
    items: dict[Any, Any] = field(default_factory=dict)


@dataclass
class Proto:
    code: list[int]
    constants: list[Any]
    protos: list[Proto]


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.d = data
        self.p = 0
        self.int_fmt = "<i"
        self.size_fmt = "<I"
        self.num_fmt = "<d"

    def take(self, n: int) -> bytes:
        if self.p + n > len(self.d):
            raise LuaFormatError("chunk truncated")
        out = self.d[self.p : self.p + n]
        self.p += n
        return out

    def u8(self) -> int:
        return self.take(1)[0]

    def i32(self) -> int:
        return int(struct.unpack(self.int_fmt, self.take(struct.calcsize(self.int_fmt)))[0])

    def size(self) -> int:
        return int(struct.unpack(self.size_fmt, self.take(struct.calcsize(self.size_fmt)))[0])

    def string(self) -> str | None:
        n = self.size()
        if n == 0:
            return None
        raw = self.take(n)
        return raw[:-1].decode("latin-1")  # the stored length counts the trailing NUL


def parse_header(r: _Reader) -> None:
    if r.take(4) != SIGNATURE:
        raise LuaFormatError("not a compiled Lua chunk")
    version, fmt, endian, s_int, s_size, s_ins, s_num, integral = r.take(8)
    if version != 0x51 or fmt != 0:
        raise LuaFormatError(f"Lua version 0x{version:02x} format {fmt}: only 5.1 official")
    if s_ins != 4 or s_num != 8 or integral != 0 or s_int not in (4, 8) or s_size not in (4, 8):
        raise LuaFormatError(f"unsupported sizes int={s_int} size_t={s_size} num={s_num}")
    e = "<" if endian == 1 else ">"
    r.int_fmt = e + ("i" if s_int == 4 else "q")
    r.size_fmt = e + ("I" if s_size == 4 else "Q")
    r.num_fmt = e + "d"


def parse_function(r: _Reader, depth: int = 0) -> Proto:
    if depth > 64:
        raise LuaFormatError("prototypes nested too deep")
    r.string()  # source
    r.i32(), r.i32()  # line defined, last line
    r.take(4)  # nups, numparams, is_vararg, maxstacksize
    n = r.i32()
    code = list(struct.unpack(f"<{n}I", r.take(4 * n))) if n else []
    consts: list[Any] = []
    for _ in range(r.i32()):
        t = r.u8()
        if t == 0:
            consts.append(None)
        elif t == 1:
            consts.append(bool(r.u8()))
        elif t == 3:
            (v,) = struct.unpack(r.num_fmt, r.take(8))
            consts.append(int(v) if float(v).is_integer() else v)
        elif t == 4:
            consts.append(r.string())
        else:
            raise LuaFormatError(f"constant type {t}")
    protos = [parse_function(r, depth + 1) for _ in range(r.i32())]
    for _ in range(r.i32()):  # line info
        r.i32()
    for _ in range(r.i32()):  # local variables
        r.string(), r.i32(), r.i32()
    for _ in range(r.i32()):  # upvalue names
        r.string()
    return Proto(code, consts, protos)


def parse_chunk(data: bytes) -> Proto:
    r = _Reader(data)
    parse_header(r)
    return parse_function(r)


def _key(v: Any) -> Any:
    return v if not isinstance(v, float) or not v.is_integer() else int(v)


def run_main(proto: Proto, env: dict[str, Any]) -> dict[str, int]:
    """Follow the main function's table-building instructions; returns counts (followed /
    unknown-making instructions by name)."""
    regs: dict[int, Any] = {}
    stats: dict[str, int] = {"followed": 0}

    def rk(x: int) -> Any:
        return proto.constants[x & 0xFF] if x & BITRK else regs.get(x, UNKNOWN)

    pc = 0
    code = proto.code
    while pc < len(code):
        i = code[pc]
        pc += 1
        op = OPS[i & 0x3F] if (i & 0x3F) < len(OPS) else "?"
        a = (i >> 6) & 0xFF
        c = (i >> 14) & 0x1FF
        b = (i >> 23) & 0x1FF
        bx = (i >> 14) & 0x3FFFF
        if op == "MOVE":
            regs[a] = regs.get(b, UNKNOWN)
        elif op == "LOADK":
            regs[a] = proto.constants[bx]
        elif op == "LOADBOOL":
            regs[a] = bool(b)
            if c:
                pc += 1
        elif op == "LOADNIL":
            for k in range(a, b + 1):
                regs[k] = None
        elif op == "GETGLOBAL":
            regs[a] = env.get(proto.constants[bx], UNKNOWN)
        elif op == "SETGLOBAL":
            env[proto.constants[bx]] = regs.get(a, UNKNOWN)
        elif op == "GETTABLE":
            t, k = regs.get(b, UNKNOWN), _key(rk(c))
            regs[a] = t.items.get(k, UNKNOWN) if isinstance(t, Table) else UNKNOWN
        elif op == "SETTABLE":
            t, k = regs.get(a, UNKNOWN), _key(rk(b))
            if isinstance(t, Table) and not isinstance(k, Unknown) and k is not None:
                t.items[k] = rk(c)
            else:
                stats["SETTABLE_unresolved"] = stats.get("SETTABLE_unresolved", 0) + 1
        elif op == "NEWTABLE":
            regs[a] = Table()
        elif op == "SETLIST":
            if c == 0:
                c = code[pc]
                pc += 1
            t = regs.get(a, UNKNOWN)
            if b == 0 or not isinstance(t, Table):
                stats["SETLIST_unresolved"] = stats.get("SETLIST_unresolved", 0) + 1
            else:
                base = (c - 1) * FIELDS_PER_FLUSH
                for k in range(1, b + 1):
                    t.items[base + k] = regs.get(a + k, UNKNOWN)
        elif op == "RETURN":
            break
        else:
            stats[op] = stats.get(op, 0) + 1
            if op not in NO_TARGET:
                regs[a] = UNKNOWN
            continue
        stats["followed"] += 1
    return stats


def load_tables(paths: list[Path], env: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run every chunk's main function in order over one global environment."""
    env = {} if env is None else env
    for p in paths:
        run_main(parse_chunk(p.read_bytes()), env)
    return env


def plain(v: Any) -> Any:
    """A JSON-able copy (tables become dicts with string keys)."""
    if isinstance(v, Table):
        return {str(k): plain(x) for k, x in v.items.items()}
    if isinstance(v, Unknown):
        return "UNKNOWN"
    return v


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--global", dest="name", help="print only this global")
    ap.add_argument("--limit", type=int, default=10, help="entries shown per table")
    a = ap.parse_args(argv)
    env: dict[str, Any] = {}
    for p in a.files:
        try:
            stats = run_main(parse_chunk(p.read_bytes()), env)
        except LuaFormatError as exc:
            print(f"lua51_tables: {p}: {exc}", file=sys.stderr)
            return 2
        print(f"{p.name}: {json.dumps(stats)}")
    for name, v in env.items():
        if a.name and name != a.name:
            continue
        if isinstance(v, Table):
            some = list(v.items.items())[: a.limit]
            print(f"{name}: table, {len(v.items)} entries; first {some}")
        else:
            print(f"{name}: {v!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
