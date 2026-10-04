"""scripts/sprite_catalog.py on a SYNTHETIC archive with synthetic sprites built here (never a real
client asset, CLAUDE.md rule 4)."""

import importlib.util
import json
import struct
import sys
import zlib
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "sprite_catalog.py"
MONSTER = "data\\sprite\\몬스터\\".encode("cp949")


@pytest.fixture(scope="module")
def cat() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sprite_catalog", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sprite_catalog"] = mod
    spec.loader.exec_module(mod)
    return mod


def act_bytes(minor: int, sizes: tuple[int, int] = (20, 30)) -> bytes:
    """ACT 2.<minor>: 5 groups x 8 directions, one motion of one layer standing on the anchor."""
    out = bytearray(b"AC" + bytes((minor, 2)) + struct.pack("<H", 40) + bytes(10))
    for _ in range(40):
        out += struct.pack("<I", 1) + bytes(32) + struct.pack("<I", 1)
        out += struct.pack("<iiiI", 0, -15, 0, 0) + bytes((255, 255, 255, 255))
        out += struct.pack("<ff", 1.0, 1.0) + struct.pack("<iI", 0, 0)
        if minor >= 5:
            out += struct.pack("<II", *sizes)
        out += struct.pack("<iI", -1, 0)  # event id, no attach points
    return bytes(out + struct.pack("<I", 0) + struct.pack("<40f", *([4.0] * 40)))


def spr_bytes() -> bytes:
    """SPR 2.1: one 20 x 30 palette image, opaque only in a 6 x 10 block (RLE encoded raw)."""
    ix = bytearray(20 * 30)
    for y in range(18, 28):
        ix[y * 20 + 7 : y * 20 + 13] = b"\x05" * 6
    enc = bytearray()
    for b in ix:  # every zero as its own 1-run: valid, if not compact
        enc += b"\x00\x01" if b == 0 else bytes((b,))
    pal = bytearray(1024)
    pal[20:24] = bytes((200, 10, 10, 0))
    return (b"SP\x01\x02" + struct.pack("<HH", 1, 0) + struct.pack("<HHH", 20, 30, len(enc))
            + bytes(enc) + bytes(pal))  # fmt: skip


def build_grf(path: Path, files: list[tuple[bytes, bytes, int]]) -> None:
    """GRF 0x200 (the layout scripts/grf_read.py documents); payloads stored zlib-compressed."""
    body, table = bytearray(), bytearray()
    for name, payload, flags in files:
        data = zlib.compress(payload)
        offset = len(body)
        aligned = (len(data) + 7) // 8 * 8
        body += data + b"\x00" * (aligned - len(data))
        table += (
            name + b"\x00" + struct.pack("<IIIBI", len(data), aligned, len(payload), flags, offset)
        )
    ztable = zlib.compress(bytes(table))
    header = b"Master of Magic\x00" + bytes(14)
    header += struct.pack("<IIII", len(body), 0, len(files) + 7, 0x200)
    path.write_bytes(header + body + struct.pack("<II", len(ztable), len(table)) + ztable)


@pytest.fixture
def archive(tmp_path: Path) -> Path:
    path = tmp_path / "synthetic.grf"
    build_grf(path, [
        (MONSTER + b"poring.act", act_bytes(5), 0x01),
        (MONSTER + b"poring.spr", b"pretend MIXCRYPT bytes", 0x03),  # refused, never decoded
        (MONSTER + b"lunatic.act", act_bytes(4), 0x01),  # 2.4: no layer sizes in the ACT
        (MONSTER + b"lunatic.spr", spr_bytes(), 0x01),
        (b"data\\sprite\\npc\\pupa.act", act_bytes(5), 0x01),  # not under the monster folder
    ])  # fmt: skip
    return path


def test_the_catalog_reports_refusals_and_falls_back_to_the_act(
    cat: ModuleType, archive: Path
) -> None:
    out = cat.catalog(archive, ["PORING", "LUNATIC", "PUPA"], None)
    poring, lunatic, pupa = (out["species"][n] for n in ("PORING", "LUNATIC", "PUPA"))
    assert poring["files"]["spr"]["status"].startswith("refused: MIXCRYPT")
    assert "sha256" in poring["files"]["act"] and "extracted" not in poring["files"]["act"]
    assert poring["box_kind"] == "quad" and poring["spr_version"] is None
    assert poring["idle_size"] == [20, 30] and poring["idle_box"] == [-10, -30, 10, 0]
    assert poring["actions"] == {"count": 40, "groups": 5.0}
    walk = poring["groups"][1]
    assert walk["name"] == "walk" and len(walk["directions"]) == 8
    assert walk["directions"][3]["delay_ms"] == 96.0 and walk["directions"][3]["motions"] == 1
    # the SPR is readable here: the box is its opaque pixels, not the 20 x 30 image
    assert lunatic["box_kind"] == "opaque" and lunatic["spr_version"] == "2.1"
    assert lunatic["idle_size"] == [6, 10] and lunatic["idle_box"] == [-3, -12, 3, -2]
    assert lunatic["image_count"] == {"palette": 1, "rgba": 0}
    assert "groups" not in pupa and pupa["files"]["act"]["status"] == "missing"
    assert pupa["candidates"] == ["data\\sprite\\npc\\pupa.act"]
    table = cat.summary(out)
    assert "MIXCRYPT" in table and "20x30" in table and "6x10" in table


def test_an_act_24_without_its_spr_has_no_boxes(cat: ModuleType, tmp_path: Path) -> None:
    path = tmp_path / "a.grf"
    build_grf(path, [(MONSTER + b"hydra.act", act_bytes(4), 0x01)])
    rec = cat.catalog(path, ["HYDRA"], None)["species"]["HYDRA"]
    assert rec["idle_size"] is None and rec["note"].startswith("no boxes")
    assert rec["groups"][0]["directions"][0]["motions"] == 1  # the counts are still there


def test_main_writes_the_catalog_and_exits_1_on_a_missing_species(
    cat: ModuleType, archive: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "kb" / "sprite_catalog.json"
    rc = cat.main(["--grf", str(archive), "--aegis", "PORING", "PUPA", "--no-extract",
                   "--out", str(out)])  # fmt: skip
    assert rc == 1
    assert set(json.loads(out.read_text())["species"]) == {"PORING", "PUPA"}
    printed = capsys.readouterr().out
    assert "REFUSED" in printed and "NO ACT: PUPA" in printed


def test_extraction_is_refused_outside_dev_shm(cat: ModuleType, archive: Path) -> None:
    with pytest.raises(cat.GrfError, match="dev/shm"):
        cat.catalog(archive, ["PORING"], Path("/var/tmp/sprites"))
