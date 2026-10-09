"""scripts/map_identity.py on SYNTHETIC map files and a synthetic archive built here (never a real
client asset, CLAUDE.md rule 4)."""

import importlib.util
import json
import struct
import sys
import zlib
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
SHM = Path("/dev/shm/poring-lab-tmp/test-map-identity")  # outputs: /dev/shm only (rule 7)


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mi() -> ModuleType:
    return _load("map_identity")


def _name(s: str, n: int) -> bytes:
    raw = s.encode("cp949")
    assert len(raw) < n
    return raw + b"\x00" * (n - len(raw))


def rsw_bytes(
    gnd: str, gat: str, models: list[str], minor: int = 1, tail: int = 1365 * 48
) -> bytes:
    """RSW 2.<minor>: the four names, water/light/ground blocks, then a light, a sound, an effect
    and one model per name, then the quad tree."""
    v = (2, minor)
    out = bytearray(b"GRSW" + bytes(v))
    if v >= (2, 5):
        out += struct.pack("<i", 7)
    if v >= (2, 2):
        out += b"\x00"
    out += _name("x.ini", 40) + _name(gnd, 40) + _name(gat, 40) + _name("x.src", 40)
    out += struct.pack("<fifffi", 1.0, 0, 1.0, 2.0, 3.0, 3)  # water (1.3 / 1.8 / 1.9)
    out += struct.pack("<ii6ff", 45, 45, *([1.0] * 6), 0.5)  # light (1.5 / 1.7)
    out += struct.pack("<4i", -500, 500, -500, 500)  # ground (1.6)
    objs = bytearray()
    objs += struct.pack("<i", 2) + _name("lamp", 80) + bytes(12 + 12 + 4)
    objs += struct.pack("<i", 3) + _name("snd", 80) + _name("wind.wav", 80) + bytes(12 + 16 + 4)
    objs += struct.pack("<i", 4) + _name("fx", 80) + bytes(12 + 4 + 4 + 16)
    for m in models:
        objs += struct.pack("<i", 1) + _name("obj", 40) + bytes(12)
        objs += _name(m, 80) + _name("node", 80) + bytes(36)
    out += struct.pack("<i", 3 + len(models)) + objs
    return bytes(out + bytes(tail))


def gnd_bytes(textures: list[str], w: int = 4, h: int = 4) -> bytes:
    out = bytearray(b"GRGN\x01\x07" + struct.pack("<IIfII", w, h, 10.0, len(textures), 80))
    for t in textures:
        out += _name(t, 80)
    return bytes(out + bytes(64))  # lightmaps etc. are not read


def rsm_bytes(textures: list[str]) -> bytes:
    out = bytearray(b"GRSM\x01\x04" + struct.pack("<ii", 0, 0) + b"\xff" + bytes(16))
    out += struct.pack("<i", len(textures))
    for t in textures:
        out += _name(t, 40)
    return bytes(out + bytes(32))


def gat_bytes(w: int, h: int, walls: set[tuple[int, int]]) -> bytes:
    out = bytearray(b"GRAT\x01\x02" + struct.pack("<II", w, h))
    for y in range(h):
        for x in range(w):
            out += struct.pack("<4fHH", 0.0, 0.0, 0.0, 0.0, 1 if (x, y) in walls else 0, 0)
    return bytes(out)


def build_grf(path: Path, files: dict[str, bytes]) -> None:
    """GRF 0x200 (grf_read's layout), every entry compressed and plain."""
    body = bytearray()
    table = bytearray()
    for name, payload in files.items():
        data = zlib.compress(payload)
        offset = len(body)
        aligned = (len(data) + 7) // 8 * 8
        body += data + b"\x00" * (aligned - len(data))
        raw = name.replace("/", "\\").encode("cp949")
        table += raw + b"\x00" + struct.pack("<IIIBI", len(data), aligned, len(payload), 1, offset)
    z = zlib.compress(bytes(table))
    header = b"Master of Magic\x00" + bytes(14)
    header += struct.pack("<IIII", len(body), 0, len(files) + 7, 0x200)
    path.write_bytes(header + body + struct.pack("<II", len(z), len(table)) + z)


RESNAME = """// a comment
a_1.rsw#zone_a.rsw#
a_1.gnd#zone_a.gnd#
a_1.gat#zone_a.gat#
a_2.rsw#zone_a.rsw#
a_2.gnd#zone_a.gnd#
a_2.gat#zone_a.gat#
broken line without fields
"""


def archive_files(extra: dict[str, bytes] | None = None) -> dict[str, bytes]:
    files = {
        "data/resnametable.txt": RESNAME.encode(),
        "data/indoorrswtable.txt": b"// list\r\nin_room.rsw#\r\n",
        "data/zone_a.rsw": rsw_bytes("zone_a.gnd", "zone_a.gat", ["tree.rsm", "tree.rsm"]),
        "data/zone_a.gnd": gnd_bytes(["grass.bmp"]),
        "data/zone_a.gat": gat_bytes(4, 3, {(0, 0)}),
        "data/model/tree.rsm": rsm_bytes(["leaf.bmp"]),
        "data/texture/grass.bmp": b"BMgrass",
        "data/texture/leaf.bmp": b"BMleaf",
        # b_1 / b_2: two real files, b_2 with a different ground texture
        "data/b_1.rsw": rsw_bytes("b_1.gnd", "b_1.gat", []),
        "data/b_1.gnd": gnd_bytes(["grass.bmp"]),
        "data/b_1.gat": gat_bytes(4, 3, set()),
        "data/b_2.rsw": rsw_bytes("b_2.gnd", "b_2.gat", []),
        "data/b_2.gnd": gnd_bytes(["sand.bmp"]),
        "data/b_2.gat": gat_bytes(4, 3, set()),
        "data/in_room.gat": gat_bytes(2, 2, set()),
    }
    files.update(extra or {})
    return files


# --- formats ---


def test_resnametable_aliases_and_skips(mi: ModuleType) -> None:
    t = mi.parse_resnametable(RESNAME)
    assert t["a_1.rsw"] == "zone_a.rsw" and len(t) == 6
    assert mi.resolve(t, "A_1.RSW") == ("zone_a.rsw", True)
    assert mi.resolve(t, "other.rsw") == ("other.rsw", False)


@pytest.mark.parametrize("minor", [1, 2, 5])
def test_rsw_objects_and_quadtree(mi: ModuleType, minor: int) -> None:
    r = mi.parse_rsw(rsw_bytes("g.gnd", "g.gat", ["a.rsm", "b\\c.rsm"], minor=minor))
    assert (r.gnd, r.gat) == ("g.gnd", "g.gat")
    assert r.models == ["a.rsm", "b\\c.rsm"]
    assert (r.lights, r.effects, r.sounds) == (1, 1, ["wind.wav"])


def test_rsw_fails_closed_on_a_misread(mi: ModuleType) -> None:
    with pytest.raises(mi.FormatError, match="end"):
        mi.parse_rsw(rsw_bytes("g.gnd", "g.gat", ["a.rsm"], tail=100))
    with pytest.raises(mi.FormatError, match="GRSW"):
        mi.parse_rsw(b"XXXX" + bytes(300))
    bad = bytearray(rsw_bytes("g.gnd", "g.gat", []))
    bad[4:6] = bytes((2, 6))
    with pytest.raises(mi.FormatError, match="newer"):
        mi.parse_rsw(bytes(bad))


def test_gnd_and_rsm_textures(mi: ModuleType) -> None:
    g = mi.parse_gnd(gnd_bytes(["a.bmp", "dir\\b.bmp"], 7, 9))
    assert (g.width, g.height, g.textures) == (7, 9, ["a.bmp", "dir\\b.bmp"])
    assert mi.rsm_textures(rsm_bytes(["x.bmp", "y.tga"])) == ("1.4", ["x.bmp", "y.tga"])
    assert mi.rsm_textures(b"GRSM\x02\x02" + bytes(40)) == ("2.2", None)
    with pytest.raises(mi.FormatError):
        mi.parse_gnd(b"GRGN\x01\x07" + struct.pack("<IIfII", 1, 1, 1.0, 5, 80))


# --- the verdicts ---


def test_aliased_copies_are_identical(mi: ModuleType, tmp_path: Path) -> None:
    grf = tmp_path / "a.grf"
    build_grf(grf, archive_files())
    doc = mi.check(grf, [["a_1", "a_2"]])
    g = doc["groups"][0]
    assert g["verdict"] == "IDENTICAL", g
    assert "same archive entries" in g["how"] and g["aliased"] == 6
    assert (g["ground_textures"], g["textures"], g["models"], g["model_instances"]) == (1, 2, 1, 2)
    assert g["missing_references"] == [] and g["problems"] == []


def test_copies_with_different_textures_differ(mi: ModuleType, tmp_path: Path) -> None:
    grf = tmp_path / "b.grf"
    build_grf(grf, archive_files({"data/texture/sand.bmp": b"BMsand"}))
    g = mi.check(grf, [["b_1", "b_2"]])["groups"][0]
    assert g["verdict"] == "DIFFERS"
    assert any("b_2.gnd" in d and "bytes" in d for d in g["differences"])
    assert any("textures" in d and "sand.bmp" in d for d in g["differences"])


def test_same_bytes_under_different_names_are_identical(mi: ModuleType, tmp_path: Path) -> None:
    files = archive_files()
    for ext in ("rsw", "gnd", "gat"):
        files[f"data/b_2.{ext}"] = files[f"data/b_1.{ext}"]
    # b_1's RSW names b_1.gnd: b_2's copy of it opens b_1.gnd too, a problem worth reporting
    grf = tmp_path / "c.grf"
    build_grf(grf, files)
    g = mi.check(grf, [["b_1", "b_2"]])["groups"][0]
    assert g["verdict"] == "IDENTICAL" and g["how"].startswith("different entries")
    assert any("the RSW names data/b_1.gnd" in p for p in g["problems"])


def test_missing_reference_and_missing_map(mi: ModuleType, tmp_path: Path) -> None:
    files = archive_files()
    del files["data/texture/leaf.bmp"]
    grf = tmp_path / "d.grf"
    build_grf(grf, files)
    g = mi.check(grf, [["a_1", "a_2"]])["groups"][0]
    assert g["missing_references"] == ["leaf.bmp"]
    g2 = mi.check(grf, [["a_1", "nowhere"]])["groups"][0]
    assert g2["verdict"] == "DIFFERS"
    assert any("data/nowhere.rsw: missing" in p for p in g2["problems"])


def test_server_agreement_counts_walkable_cells(mi: ModuleType) -> None:
    from poring_dataset.mapcache import MapGrid

    gat = gat_bytes(4, 3, {(0, 0)})
    same = MapGrid("m", 4, 3, bytes([1] + [0] * 11))
    assert mi.server_agreement(gat, same)["walkable_differ"] == 0
    other = MapGrid("m", 4, 3, bytes([0] * 11 + [5]))
    r = mi.server_agreement(gat, other)
    assert (r["walkable_differ"], r["type_differ"]) == (2, 2)
    assert mi.server_agreement(gat, MapGrid("m", 3, 3, bytes(9)))["size_match"] is False
    assert mi.server_agreement(None, same)["compared"] is False


def test_gat_extract_writes_server_names_and_indoor(mi: ModuleType, tmp_path: Path) -> None:
    grf = tmp_path / "e.grf"
    build_grf(grf, archive_files())
    out = SHM / "gat"
    rows = mi.extract_gats(grf, ["a_1", "a_2", "in_room", "nowhere"], out)
    by = {r["map"]: r for r in rows}
    assert by["a_1"]["alias"] and by["a_1"]["opens"] == "data/zone_a.gat"
    assert (out / "a_1.gat").read_bytes() == (out / "a_2.gat").read_bytes()
    assert by["in_room"]["indoor"] is True and by["a_1"]["indoor"] is False
    assert "written" not in by["nowhere"] and by["nowhere"]["error"] == "missing"
    assert (out / "indoorrswtable.txt").exists()


def test_gat_extract_refuses_outside_shm(mi: ModuleType, tmp_path: Path) -> None:
    grf = tmp_path / "f.grf"
    build_grf(grf, archive_files())
    if not str(tmp_path).startswith("/dev/shm"):
        with pytest.raises(mi.GrfError, match="/dev/shm"):
            mi.extract_gats(grf, ["a_1"], tmp_path / "out")
    with pytest.raises(mi.GrfError, match="repository"):
        mi.extract_gats(grf, ["a_1"], SCRIPTS.parent / "data" / "gat-test")


def test_cli_check_exit_code_and_json(mi: ModuleType, tmp_path: Path, capsys) -> None:
    grf = tmp_path / "g.grf"
    build_grf(grf, archive_files())
    out = SHM / "mi.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    rc = mi.main(["check", "--grf", str(grf), "--group", "a_1,a_2", "--out", str(out)])
    assert rc == 0 and "IDENTICAL" in capsys.readouterr().out
    assert json.loads(out.read_text())["groups"][0]["verdict"] == "IDENTICAL"
    rc = mi.main(["check", "--grf", str(grf), "--group", "b_1,b_2", "--out", str(out)])
    assert rc == 1
