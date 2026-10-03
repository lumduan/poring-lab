"""scripts/msgtable_extract.py: the embedded message table of a client EXE, found by parsing bytes
(never executed). Synthetic PE32 images only -- no client bytes in the repository."""

import importlib.util
import struct
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "msgtable_extract.py"
BASE = 0x400000
RDATA_RVA, DATA_RVA = 0x1000, 0x8000
RDATA_RAW, DATA_RAW = 0x400, 0x4000


@pytest.fixture(scope="module")
def mx() -> ModuleType:
    spec = importlib.util.spec_from_file_location("msgtable_extract", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve string annotations through it
    spec.loader.exec_module(module)
    return module


def pe(strings: list[bytes], *, extra_runs: list[int] = (), anchor: bool = True,
       break_at: int | None = None) -> bytes:  # fmt: skip
    """A PE32 with .rdata (the strings) and .data (the record table, then optional decoy runs)."""
    rdata = bytearray(b"msgStringTable.txt\0" if anchor else b"something-else\0")
    vas = []
    for text in strings:
        vas.append(BASE + RDATA_RVA + len(rdata))
        rdata += text + b"\0"
    table = bytearray(b"\xcc" * 12)  # not record-aligned at the section start on purpose
    for i, va in enumerate(vas):
        if break_at is not None and i == break_at:
            table += struct.pack("<II", i, BASE + 0x7FFF0000)  # a pointer outside the image
        else:
            table += struct.pack("<II", i, va)
    for n in extra_runs:
        table += b"\xee" * 8
        table += b"".join(struct.pack("<II", i, vas[i % len(vas)]) for i in range(n))
    header = bytearray(RDATA_RAW)
    header[:2] = b"MZ"
    struct.pack_into("<I", header, 0x3C, 0x40)
    header[0x40:0x44] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", header, 0x44, 0x14C, 2, 1_635_926_200, 0, 0, 224, 0x102)
    opt = 0x58
    struct.pack_into("<H", header, opt, 0x10B)
    struct.pack_into("<I", header, opt + 28, BASE)
    sect = opt + 224
    struct.pack_into(
        "<8sIIII", header, sect, b".rdata", len(rdata), RDATA_RVA, len(rdata), RDATA_RAW
    )
    struct.pack_into(
        "<8sIIII", header, sect + 40, b".data", len(table), DATA_RVA, len(table), DATA_RAW
    )
    body = bytearray(header) + rdata
    body += b"\0" * (DATA_RAW - len(body))
    return bytes(body + table)


def texts(n: int) -> list[bytes]:
    return [f"message {i}".encode() for i in range(n)] + [b"two\r\nlines", "ข้อความ".encode("cp874")]


def test_the_table_is_found_and_written_in_warps_format(mx: ModuleType, tmp_path: Path) -> None:
    exe = tmp_path / "client.exe"
    exe.write_bytes(pe(texts(600)))
    run, report = mx.extract(exe, min_run=500)
    assert len(run.strings) == 602 and report["picked"]["section"] == ".data"
    assert report["pe_timestamp"] == 1_635_926_200
    out = mx.table_bytes(run)
    lines = out.split(b"\r\n")
    assert lines[0] == b"message 0#" and lines[600] == b"two\\r\\nlines#"  # escaped, one line
    assert lines[601] == "ข้อความ#".encode("cp874")  # the original bytes, never decoded
    assert out.endswith(b"#\r\n") and out.count(b"\r\n") == 602


def test_the_cli_writes_counts_only_and_refuses_the_repo(
    mx: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exe = tmp_path / "client.exe"
    exe.write_bytes(pe(texts(600)))
    assert mx.main([str(exe), "--out", str(tmp_path / "t.txt")]) == 0
    printed = capsys.readouterr().out
    assert '"out_lines": 602' in printed and "message 1" not in printed
    inside = SCRIPT.parents[1] / "data" / "never.txt"
    assert mx.main([str(exe), "--out", str(inside)]) == 2 and not inside.exists()


def test_a_broken_pointer_ends_the_run(mx: ModuleType, tmp_path: Path) -> None:
    exe = tmp_path / "client.exe"
    exe.write_bytes(pe(texts(600), break_at=550))
    run, _ = mx.extract(exe, min_run=500)
    assert len(run.strings) == 550


@pytest.mark.parametrize(
    ("kwargs", "why"),
    [
        ({"extra_runs": [520]}, "ambiguous"),  # a second run longer than half the first
        ({"anchor": False}, "msgStringTable.txt"),
        ({"break_at": 100}, "no record run"),  # shorter than --min-run
    ],
)
def test_it_refuses_to_guess(mx: ModuleType, tmp_path: Path, kwargs: dict, why: str) -> None:  # type: ignore[type-arg]
    exe = tmp_path / "client.exe"
    exe.write_bytes(pe(texts(600), **kwargs))
    with pytest.raises(mx.ExtractError, match=why):
        mx.extract(exe, min_run=500)
    assert mx.main([str(exe), "--out", str(tmp_path / "t.txt")]) == 3


def test_a_short_decoy_run_does_not_make_it_ambiguous(mx: ModuleType, tmp_path: Path) -> None:
    exe = tmp_path / "client.exe"
    exe.write_bytes(pe(texts(1200), extra_runs=[500]))
    run, report = mx.extract(exe, min_run=500)
    assert len(run.strings) == 1202 and len(report["runs"]) == 2


def test_not_a_pe(mx: ModuleType, tmp_path: Path) -> None:
    exe = tmp_path / "x.exe"
    exe.write_bytes(b"\x7fELF" + b"\0" * 100)
    with pytest.raises(mx.ExtractError, match="not a PE"):
        mx.extract(exe, min_run=10)
