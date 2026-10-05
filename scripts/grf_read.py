#!/usr/bin/env python3
"""Read-only GRF archive reader (Part C of the Thai-UI task, ADR-0012). Stdlib + zlib only.

    grf_read.py info GRF                          version, entry counts, encrypted share (JSON)
    grf_read.py ls GRF [--grep REGEX] [--limit N] flags, sizes and names (CP949-decoded)
    grf_read.py extract GRF NAME [NAME...] --out DIR [--glob] [--max-bytes N] [--allow-out]
                        [--decode-des]

Rules (the data is a client asset, never committed, CLAUDE.md rule 4):
  * READ-ONLY: the archive is opened "rb" and only seek/read is used -- it is never copied. Read it
    where it lies (the NAS read-only mount); a 3.3 GB archive must not be staged on the VM's disk.
  * extract writes only under /dev/shm (rule 7) unless --allow-out, and NEVER inside this git
    repository (refused even with --allow-out). --max-bytes caps one run (default 512 MiB).
  * Nothing here loads or executes anything from the archive.

Format (GRF 0x200, the layout every RO client since ~2004 reads):
  header, 46 bytes:  magic "Master of Magic\\0" (16) | key (14) | table_offset u32 (from byte 46)
                     | seed u32 | raw_count u32 (entries = raw_count - seed - 7) | version u32
  file table at 46 + table_offset:  zsize u32 | size u32 | zlib(table)
  table entry:       name (NUL-terminated, CP949) | zsize u32 | zsize_aligned u32 | size u32
                     | flags u8 | offset u32 (from byte 46)
  flags:             0x01 FILE (else a directory), 0x02 MIXCRYPT, 0x04 DES (first 20 blocks)
GRF 0x300 (archives over 4 GiB): table_offset is u64 at 0x1E (no seed), entry offsets are u64,
and the table is preceded by an extra u32. That layout follows public tool descriptions and is
UNVERIFIED against a real archive: `info` reports the header; a failing table parse says so.

Encryption: DES/MIXCRYPT entries are listed and counted but NOT decoded ("encrypted:
unsupported"). If the files that matter are encrypted, or the magic is unknown (a custom
encryption scheme), that is the C8 stop condition: report it, do not work around it.
EXCEPT, explicitly: --decode-des (Batt, 2026-10-03, Phase 2 GAT altitude: "own decoder from the
public spec") decodes header-only DES entries (flag 0x04) with scripts/grf_des.py, our own code from
the FIPS 46-3 tables; zlib's checksum and the table's size verify every decoded entry. MIXCRYPT
(0x02) stays refused, EXCEPT with --decode-mixcrypt (Batt, 2026-10-05, option (a): STUDY ONLY): a
host-local decoder that is NEVER in this repo is loaded from $PORING_PRIVATE_DIR (default
~/poring-lab-private/grf_mixcrypt.py). This reader refuses a private dir inside the repo or one that
is group/world-writable; without the decoder it is the same C8 refusal as before. Never used with
any server: offline files only. The pre-commit hook refuses the decoder by name and fingerprint.
"""

from __future__ import annotations

import argparse
import fnmatch
import importlib.util
import json
import os
import re
import struct
import sys
import zlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import BinaryIO

MAGIC = b"Master of Magic\x00"
HEADER_SIZE = 46
FLAG_FILE, FLAG_MIXCRYPT, FLAG_DES = 0x01, 0x02, 0x04
SCRATCH_ROOT = Path("/dev/shm")
REPO = Path(__file__).resolve().parents[1]
DEFAULT_MAX_BYTES = 512 * 1024 * 1024
PRIVATE_ENV = "PORING_PRIVATE_DIR"
PRIVATE_MODULE = "grf_mixcrypt.py"


class GrfError(Exception):
    """An archive this reader cannot (or must not) handle."""


@dataclass(frozen=True, slots=True)
class Header:
    version: int
    table_offset: int  # absolute file offset of the file table
    entry_count: int
    key: bytes


@dataclass(frozen=True, slots=True)
class Entry:
    raw_name: bytes
    zsize: int
    zsize_aligned: int
    size: int
    flags: int
    offset: int  # absolute file offset of the entry's data

    @property
    def name(self) -> str:
        return decode_name(self.raw_name)

    @property
    def is_file(self) -> bool:
        return bool(self.flags & FLAG_FILE)

    @property
    def encrypted(self) -> bool:
        return bool(self.flags & (FLAG_MIXCRYPT | FLAG_DES))


def decode_name(raw: bytes) -> str:
    """Korean clients store names in CP949 (a superset of EUC-KR); undecodable bytes are kept
    visible as replacement characters, and the raw bytes stay on the Entry."""
    return raw.decode("cp949", errors="replace")


def norm_name(name: str) -> str:
    """Archive names use backslashes and any case; compare them as lower-case slash paths."""
    return name.replace("\\", "/").lower()


def read_header(f: BinaryIO) -> Header:
    f.seek(0)
    raw = f.read(HEADER_SIZE)
    if len(raw) < HEADER_SIZE:
        raise GrfError("file shorter than a GRF header")
    if raw[:16] != MAGIC:
        raise GrfError(
            f"unknown magic {raw[:16]!r}: not a standard GRF (custom encryption?) -- C8 stop"
        )
    key = raw[16:30]
    (version,) = struct.unpack_from("<I", raw, 0x2A)
    if version == 0x200:
        table_rel, seed, raw_count = struct.unpack_from("<III", raw, 0x1E)
        count = raw_count - seed - 7
    elif version == 0x300:
        (table_rel,) = struct.unpack_from("<Q", raw, 0x1E)
        (raw_count,) = struct.unpack_from("<I", raw, 0x26)
        count = raw_count - 7
    else:
        raise GrfError(f"unsupported GRF version 0x{version:x} (this reader: 0x200, 0x300)")
    if count < 0:
        raise GrfError(f"negative entry count ({count}): corrupt or custom header")
    return Header(version, HEADER_SIZE + table_rel, count, key)


def read_table(f: BinaryIO, header: Header) -> bytes:
    f.seek(header.table_offset)
    if header.version == 0x300:
        f.read(4)  # an extra u32 before the sizes (unverified layout, see the module doc)
    sizes = f.read(8)
    if len(sizes) < 8:
        raise GrfError("file table offset points past the end of the file")
    zsize, size = struct.unpack("<II", sizes)
    try:
        table = zlib.decompress(f.read(zsize))
    except zlib.error as exc:
        raise GrfError(f"file table does not inflate: {exc}") from exc
    if len(table) != size:
        raise GrfError(f"file table inflated to {len(table)} bytes, header says {size}")
    return table


def iter_entries(f: BinaryIO, header: Header) -> Iterator[Entry]:
    table = read_table(f, header)
    tail = "<IIIBQ" if header.version == 0x300 else "<IIIBI"
    tail_size = struct.calcsize(tail)
    pos = 0
    for _ in range(header.entry_count):
        end = table.find(b"\x00", pos)
        if end < 0 or end + 1 + tail_size > len(table):
            raise GrfError(f"file table truncated at byte {pos}")
        raw_name = table[pos:end]
        zsize, aligned, size, flags, offset = struct.unpack_from(tail, table, end + 1)
        pos = end + 1 + tail_size
        yield Entry(raw_name, zsize, aligned, size, flags, HEADER_SIZE + offset)


def decodable(entry: Entry, decode_des: bool, decode_mixcrypt: bool = False) -> bool:
    if entry.flags & FLAG_MIXCRYPT:
        return decode_mixcrypt
    return not entry.encrypted or bool(decode_des and entry.flags & FLAG_DES)


def private_dir() -> Path:
    return Path(os.environ.get(PRIVATE_ENV) or Path.home() / "poring-lab-private").resolve()


def load_mixcrypt(directory: Path | None = None) -> ModuleType:
    """The host-local study decoder (never in this repo), or a C8 refusal."""
    d = (directory or private_dir()).resolve()
    if d == REPO or REPO in d.parents:
        raise GrfError(f"MIXCRYPT: the private dir {d} is inside the repo: refused -- C8")
    path = d / PRIVATE_MODULE
    if not path.is_file():
        raise GrfError(f"MIXCRYPT: no study decoder at {path} (host-local, never committed) -- C8")
    for p in (d, path):
        if p.stat().st_mode & 0o022:
            raise GrfError(f"MIXCRYPT: {p} is group/world-writable: refused -- C8")
    spec = importlib.util.spec_from_file_location("grf_mixcrypt", path)
    if spec is None or spec.loader is None:
        raise GrfError(f"MIXCRYPT: cannot load {path} -- C8")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_entry(
    f: BinaryIO, entry: Entry, *, decode_des: bool = False, decode_mixcrypt: bool = False
) -> bytes:
    if not entry.is_file:
        raise GrfError(f"{entry.name}: a directory entry")
    if not decodable(entry, decode_des, decode_mixcrypt):
        raise GrfError(f"{entry.name}: encrypted: unsupported (flags 0x{entry.flags:02x}) -- C8")
    f.seek(entry.offset)
    want = entry.zsize_aligned if entry.encrypted else entry.zsize
    data = f.read(want)
    if len(data) != want:
        raise GrfError(f"{entry.name}: data runs past the end of the archive")
    if entry.flags & FLAG_MIXCRYPT:
        from grf_des import grf_block

        data = load_mixcrypt().decode(data, entry.zsize, grf_block)[: entry.zsize]
    elif entry.flags & FLAG_DES:
        from grf_des import decode_header

        data = decode_header(data)[: entry.zsize]
    try:
        out = data if entry.zsize == entry.size else zlib.decompress(data)
    except zlib.error as exc:
        raise GrfError(f"{entry.name}: does not inflate ({exc})") from None
    if len(out) != entry.size:
        raise GrfError(f"{entry.name}: inflated to {len(out)} bytes, table says {entry.size}")
    return out


def summary(path: Path) -> dict[str, object]:
    with path.open("rb") as f:
        header = read_header(f)
        out: dict[str, object] = {
            "path": str(path),
            "bytes": path.stat().st_size,
            "version": f"0x{header.version:x}",
            "entries_declared": header.entry_count,
            "key_nonzero": any(header.key),
        }
        try:
            entries = list(iter_entries(f, header))
        except GrfError as exc:
            out["table_error"] = str(exc)
            return out
    files = [e for e in entries if e.is_file]
    encrypted = [e for e in files if e.encrypted]
    out.update(
        files=len(files),
        directories=len(entries) - len(files),
        encrypted=len(encrypted),
        encrypted_share=round(len(encrypted) / len(files), 4) if files else 0.0,
        mixcrypt=sum(1 for e in files if e.flags & FLAG_MIXCRYPT),
        des_header_only=sum(1 for e in files if e.flags & FLAG_DES),
        uncompressed_bytes=sum(e.size for e in files),
        undecodable_names=sum(1 for e in entries if "�" in e.name),
    )
    return out


def safe_out_dir(out: Path, allow_out: bool) -> Path:
    """Where extracted files may go: /dev/shm by default; never this repository."""
    out = out.resolve()
    if out == REPO or REPO in out.parents:
        raise GrfError(f"refusing to extract into the git repository ({out}): client assets")
    if not allow_out and out != SCRATCH_ROOT and SCRATCH_ROOT not in out.parents:
        raise GrfError(f"refusing --out {out}: extract under /dev/shm (rule 7) or pass --allow-out")
    return out


def safe_relpath(name: str) -> Path:
    """An archive name as a relative path: no absolute paths, no `..`, no drive letters."""
    parts = [p for p in name.replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts or any(p == ".." or ":" in p for p in parts):
        raise GrfError(f"unsafe entry name {name!r}")
    return Path(*parts)


def select(entries: list[Entry], names: list[str], glob: bool) -> list[Entry]:
    wanted = [norm_name(n) for n in names]
    files = [e for e in entries if e.is_file]
    if glob:
        return [e for e in files if any(fnmatch.fnmatchcase(norm_name(e.name), w) for w in wanted)]
    by_name = {norm_name(e.name): e for e in files}
    missing = [n for n in wanted if n not in by_name]
    if missing:
        raise GrfError(f"not in the archive: {', '.join(missing)}")
    return [by_name[n] for n in wanted]


def extract(
    path: Path,
    names: list[str],
    out: Path,
    *,
    glob: bool,
    max_bytes: int,
    allow_out: bool,
    decode_des: bool = False,
    decode_mixcrypt: bool = False,
) -> list[dict[str, object]]:
    out = safe_out_dir(out, allow_out)
    done: list[dict[str, object]] = []
    with path.open("rb") as f:
        header = read_header(f)
        chosen = select(list(iter_entries(f, header)), names, glob)
        total = sum(e.size for e in chosen)
        if total > max_bytes:
            raise GrfError(f"{len(chosen)} entries = {total} bytes > --max-bytes {max_bytes}")
        for entry in chosen:
            rel = safe_relpath(entry.name)
            if not decodable(entry, decode_des, decode_mixcrypt):
                done.append({"name": str(rel), "skipped": "encrypted: unsupported"})
                continue
            data = read_entry(f, entry, decode_des=decode_des, decode_mixcrypt=decode_mixcrypt)
            dest = out / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            row: dict[str, object] = {"name": str(rel), "bytes": len(data)}
            if entry.flags & FLAG_DES:
                row["des_decoded"] = True
            if entry.flags & FLAG_MIXCRYPT:
                row["mixcrypt_decoded"] = True
            done.append(row)
    return done


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_info = sub.add_parser("info")
    p_info.add_argument("grf", type=Path)
    p_ls = sub.add_parser("ls")
    p_ls.add_argument("grf", type=Path)
    p_ls.add_argument("--grep", help="regex on the decoded, slash-normalised, lower-case name")
    p_ls.add_argument("--limit", type=int, default=0)
    p_ex = sub.add_parser("extract")
    p_ex.add_argument("grf", type=Path)
    p_ex.add_argument("names", nargs="+", help="archive names (or fnmatch patterns with --glob)")
    p_ex.add_argument("--out", type=Path, required=True)
    p_ex.add_argument("--glob", action="store_true")
    p_ex.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    p_ex.add_argument("--allow-out", action="store_true", help="--out outside /dev/shm")
    p_ex.add_argument(
        "--decode-des", action="store_true", help="decode header-only DES (0x04); never MIXCRYPT"
    )
    p_ex.add_argument(
        "--decode-mixcrypt", action="store_true",
        help="STUDY ONLY (Batt 2026-10-05): MIXCRYPT (0x02) via the host-local decoder",
    )  # fmt: skip
    a = ap.parse_args(argv)
    try:
        if a.cmd == "info":
            print(json.dumps(summary(a.grf), ensure_ascii=False, indent=1))
        elif a.cmd == "ls":
            pattern = re.compile(a.grep) if a.grep else None
            shown = 0
            with a.grf.open("rb") as f:
                for e in iter_entries(f, read_header(f)):
                    if pattern and not pattern.search(norm_name(e.name)):
                        continue
                    kind = ("E" if e.encrypted else "F") if e.is_file else "D"
                    print(f"{kind} 0x{e.flags:02x} {e.size:>10} {e.zsize:>10} {e.name}")
                    shown += 1
                    if a.limit and shown >= a.limit:
                        break
        else:
            done = extract(
                a.grf, a.names, a.out, glob=a.glob, max_bytes=a.max_bytes,
                allow_out=a.allow_out, decode_des=a.decode_des,
                decode_mixcrypt=a.decode_mixcrypt,
            )  # fmt: skip
            print(json.dumps({"out": str(a.out), "entries": done}, ensure_ascii=False, indent=1))
    except GrfError as exc:
        print(f"grf_read: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
