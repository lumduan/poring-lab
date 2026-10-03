#!/usr/bin/env python3
"""Extract the message table a Ragnarok client EXECUTABLE embeds, by parsing its bytes. Stdlib only.

NOTHING IS EXECUTED: the file is read as bytes, the PE headers are parsed, and a data structure is
located. (Batt, 2026-10-03: the exe is copied read-only and never run; WARP's ExtractMsgStrings is
only the fallback cross-check if this parse is ambiguous.)

    msgtable_extract.py EXE --out FILE [--min-run 500] [--report FILE.json]

What it finds (the layout WARP's ExtractMsgStrings walks, Neo-Mind/WARP rock_win32,
Scripts/Extensions/ExtractMsgStrings.qjs): an array of 8-byte records
    { uint32 index; uint32 va_of_a_NUL_terminated_string; }
with index = 0, 1, 2, ... in order. WARP finds the array through the code that loads
"msgStringTable.txt"; this parser scans every section for the longest run of such records whose
pointers all land on strings inside the image, and refuses to guess when that is not unique:

  * a run must be at least --min-run records long;
  * the longest run must be unique and at least twice as long as the next one;
  * the image must contain the text "msgStringTable.txt" (the WARP anchor's string; a sanity check
    that this is a client with an embedded table at all).
Otherwise it exits 3 with a report (and Batt decides on the WARP cross-check).

Output: WARP's text format -- each string in its ORIGINAL bytes (no decoding), "\\r" and "\\n"
escaped as the two characters, a "#" terminator, CRLF line ends. Line number - 1 = message id.
Write it OUTSIDE the repo (/dev/shm): client text is never committed (CLAUDE.md rule 4).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

ANCHOR = b"msgStringTable.txt"
MAX_STRING = 4096


class ExtractError(Exception):
    """Not a PE, no table, or an ambiguous one."""


@dataclass(frozen=True)
class Section:
    name: str
    va: int  # RVA
    vsize: int
    raw: int  # file offset
    rsize: int


@dataclass
class Image:
    data: bytes
    image_base: int
    sections: list[Section]
    timestamp: int

    def offset_of(self, va: int) -> int | None:
        """File offset of an absolute VA, or None when it is not backed by file bytes."""
        rva = va - self.image_base
        for s in self.sections:
            if s.va <= rva < s.va + max(s.vsize, s.rsize):
                delta = rva - s.va
                if delta < s.rsize:
                    return s.raw + delta
                return None
        return None

    def string_at(self, va: int) -> bytes | None:
        off = self.offset_of(va)
        if off is None:
            return None
        end = self.data.find(b"\0", off, off + MAX_STRING)
        if end < 0:
            return None
        return self.data[off:end]


def parse_pe(data: bytes) -> Image:
    if data[:2] != b"MZ" or len(data) < 0x40:
        raise ExtractError("not a PE file (no MZ header)")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe : pe + 4] != b"PE\0\0":
        raise ExtractError("not a PE file (no PE signature)")
    _machine, nsect, timestamp, _, _, opt_size, _chars = struct.unpack_from(
        "<HHIIIHH", data, pe + 4
    )
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    if magic != 0x10B:
        raise ExtractError(f"optional header magic 0x{magic:x}: only 32-bit (PE32) clients")
    image_base = struct.unpack_from("<I", data, opt + 28)[0]
    sections = []
    table = opt + opt_size
    for k in range(nsect):
        raw_name, vsize, va, rsize, raw = struct.unpack_from("<8sIIII", data, table + 40 * k)
        sections.append(Section(raw_name.rstrip(b"\0").decode("ascii", "replace"),
                                va, vsize, raw, rsize))  # fmt: skip
    return Image(data, image_base, sections, timestamp)


@dataclass(frozen=True)
class Run:
    offset: int  # file offset of record 0
    section: str
    strings: tuple[bytes, ...]


# Record 0 then record 1's index: every (overlapping) position, found at C speed.
_START = re.compile(rb"(?=\x00\x00\x00\x00.{4}\x01\x00\x00\x00)", re.DOTALL)


def find_runs(img: Image, min_run: int) -> list[Run]:
    """Every run of (i, va->string) records with i = 0, 1, 2, ... of at least min_run records."""
    runs: list[Run] = []
    for s in img.sections:
        start, end = s.raw, s.raw + s.rsize
        skip_to = start
        for match in _START.finditer(img.data, start, end):
            pos = match.start()
            if pos < skip_to or pos % 4:
                continue
            strings = _walk(img, pos, end)
            if len(strings) >= min_run:
                runs.append(Run(pos, s.name, tuple(strings)))
                skip_to = pos + 8 * len(strings)
    return runs


def _walk(img: Image, pos: int, end: int) -> list[bytes]:
    out: list[bytes] = []
    i = 0
    while pos + 8 <= end:
        index, va = struct.unpack_from("<II", img.data, pos)
        if index != i:
            break
        text = img.string_at(va)
        if text is None:
            break
        out.append(text)
        i += 1
        pos += 8
    return out


def pick(runs: list[Run]) -> Run:
    if not runs:
        raise ExtractError("no record run found (no embedded table, or another layout)")
    ranked = sorted(runs, key=lambda r: len(r.strings), reverse=True)
    best = ranked[0]
    if len(ranked) > 1 and len(ranked[1].strings) * 2 > len(best.strings):
        sizes = [len(r.strings) for r in ranked[:5]]
        raise ExtractError(f"ambiguous: several long runs {sizes} -- cross-check with WARP")
    return best


def escape(text: bytes) -> bytes:
    return text.replace(b"\r", b"\\r").replace(b"\n", b"\\n")


def table_bytes(run: Run) -> bytes:
    return b"".join(escape(s) + b"#\r\n" for s in run.strings)


def extract(exe: Path, min_run: int) -> tuple[Run, dict[str, object]]:
    data = exe.read_bytes()
    img = parse_pe(data)
    anchor = data.count(ANCHOR)
    runs = find_runs(img, min_run)
    report: dict[str, object] = {
        "exe_sha256": hashlib.sha256(data).hexdigest(),
        "exe_bytes": len(data),
        "pe_timestamp": img.timestamp,
        "image_base": f"0x{img.image_base:08x}",
        "sections": [s.name for s in img.sections],
        "anchor_string_count": anchor,
        "runs": [
            {"section": r.section, "file_offset": f"0x{r.offset:x}", "records": len(r.strings)}
            for r in runs
        ],  # fmt: skip
    }
    if not anchor:
        raise ExtractError(f"no {ANCHOR.decode()!r} in the image: {json.dumps(report)}")
    try:
        best = pick(runs)
    except ExtractError as exc:
        raise ExtractError(f"{exc}: {json.dumps(report)}") from None
    report["picked"] = {"section": best.section, "file_offset": f"0x{best.offset:x}",
                        "records": len(best.strings)}  # fmt: skip
    return best, report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("exe", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--min-run", type=int, default=500)
    ap.add_argument("--report", type=Path)
    a = ap.parse_args(argv)
    repo = Path(__file__).resolve().parents[1]
    for path in (a.out, a.report):
        if path is not None and repo in path.resolve().parents:
            print(f"refusing {path}: client text never goes into the repository", file=sys.stderr)
            return 2
    try:
        run, report = extract(a.exe, a.min_run)
    except ExtractError as exc:
        print(f"AMBIGUOUS/NOT FOUND: {exc}", file=sys.stderr)
        return 3
    body = table_bytes(run)
    a.out.write_bytes(body)
    report["out_lines"] = len(run.strings)
    report["out_sha256"] = hashlib.sha256(body).hexdigest()
    if a.report:
        a.report.write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))  # counts and offsets only, never table text
    return 0


if __name__ == "__main__":
    sys.exit(main())
