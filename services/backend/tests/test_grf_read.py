"""scripts/grf_read.py on SYNTHETIC archives built here (never a real client asset)."""

import importlib.util
import json
import struct
import sys
import zlib
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "grf_read.py"


@pytest.fixture(scope="module")
def grf() -> ModuleType:
    spec = importlib.util.spec_from_file_location("grf_read", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["grf_read"] = mod
    spec.loader.exec_module(mod)
    return mod


# name (CP949 bytes), payload, compress?, flags
FILES: list[tuple[bytes, bytes, bool, int]] = [
    (b"data\\readme.txt", b"plain text, stored uncompressed\n", False, 0x01),
    (b"data\\table.txt", b"line one#\nline two#\n" * 50, True, 0x01),
    ("data\\텍스쳐\\a.txt".encode("cp949"), b"korean-named directory", True, 0x01),
    (b"data\\secret.txt", b"pretend-encrypted bytes", False, 0x01 | 0x04),
]


def build_grf_200(path: Path, files: list[tuple[bytes, bytes, bool, int]], seed: int = 3) -> None:
    body = bytearray()
    table = bytearray()
    entries = [(b"data", b"", False, 0x00)] + files  # one directory entry, like real archives
    for name, payload, compress, flags in entries:
        data = zlib.compress(payload) if compress else payload
        offset = len(body)
        body += data
        aligned = (len(data) + 7) // 8 * 8
        body += b"\x00" * (aligned - len(data))
        table += (
            name + b"\x00" + struct.pack("<IIIBI", len(data), aligned, len(payload), flags, offset)
        )
    ztable = zlib.compress(bytes(table))
    header = b"Master of Magic\x00" + bytes(range(14))
    header += struct.pack("<IIII", len(body), seed, len(entries) + seed + 7, 0x200)
    assert len(header) == 46
    path.write_bytes(header + body + struct.pack("<II", len(ztable), len(table)) + ztable)


@pytest.fixture
def archive(tmp_path: Path) -> Path:
    path = tmp_path / "synthetic.grf"
    build_grf_200(path, FILES)
    return path


def test_info_counts_files_directories_and_encryption(grf: ModuleType, archive: Path) -> None:
    info = grf.summary(archive)
    assert info["version"] == "0x200"
    assert info["entries_declared"] == 5
    assert (info["files"], info["directories"]) == (4, 1)
    assert info["encrypted"] == 1 and info["des_header_only"] == 1 and info["mixcrypt"] == 0
    assert info["encrypted_share"] == 0.25
    assert info["undecodable_names"] == 0


def test_entries_decode_cp949_names_and_keep_raw_bytes(grf: ModuleType, archive: Path) -> None:
    with archive.open("rb") as f:
        entries = list(grf.iter_entries(f, grf.read_header(f)))
    korean = [e for e in entries if "텍스쳐" in e.name]
    assert len(korean) == 1 and korean[0].raw_name == "data\\텍스쳐\\a.txt".encode("cp949")


def test_read_entry_round_trips_stored_and_compressed(grf: ModuleType, archive: Path) -> None:
    with archive.open("rb") as f:
        by_name = {e.name: e for e in grf.iter_entries(f, grf.read_header(f))}
        assert grf.read_entry(f, by_name["data\\readme.txt"]) == FILES[0][1]
        assert grf.read_entry(f, by_name["data\\table.txt"]) == FILES[1][1]
        with pytest.raises(grf.GrfError, match="encrypted: unsupported"):
            grf.read_entry(f, by_name["data\\secret.txt"])


def test_extract_writes_under_dev_shm_only(grf: ModuleType, archive: Path) -> None:
    out = Path("/dev/shm/poring-lab-tmp/test-grf-extract")
    done = grf.extract(archive, ["data/*.txt"], out, glob=True, max_bytes=1 << 20, allow_out=False)
    names = {d["name"]: d for d in done}
    assert (out / "data" / "table.txt").read_bytes() == FILES[1][1]
    assert names["data/secret.txt"] == {
        "name": "data/secret.txt",
        "skipped": "encrypted: unsupported",
    }
    for path in sorted(out.rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    out.rmdir()


def test_extract_refuses_the_repo_and_disk_paths(
    grf: ModuleType, archive: Path, tmp_path: Path
) -> None:
    repo = Path(__file__).resolve().parents[3]
    with pytest.raises(grf.GrfError, match="git repository"):
        grf.extract(archive, ["data/readme.txt"], repo / "x", glob=False, max_bytes=1 << 20,
                    allow_out=True)  # fmt: skip
    if not str(tmp_path).startswith("/dev/shm"):
        with pytest.raises(grf.GrfError, match="/dev/shm"):
            grf.extract(archive, ["data/readme.txt"], tmp_path / "out", glob=False,
                        max_bytes=1 << 20, allow_out=False)  # fmt: skip


def test_extract_honours_max_bytes(grf: ModuleType, archive: Path) -> None:
    with pytest.raises(grf.GrfError, match="max-bytes"):
        grf.extract(archive, ["data/*"], Path("/dev/shm/poring-lab-tmp/test-grf-max"), glob=True,
                    max_bytes=10, allow_out=False)  # fmt: skip


def test_unsafe_names_are_refused(grf: ModuleType) -> None:
    for bad in ("..\\..\\etc\\passwd", "c:\\windows\\x", "\\", ""):
        with pytest.raises(grf.GrfError, match="unsafe"):
            grf.safe_relpath(bad)
    assert grf.safe_relpath("data\\a\\b.txt") == Path("data/a/b.txt")


def test_unknown_magic_is_a_c8_stop(grf: ModuleType, tmp_path: Path) -> None:
    path = tmp_path / "custom.grf"
    path.write_bytes(b"Event Horizon\x00\x00\x00" + b"\x00" * 30)
    with path.open("rb") as f, pytest.raises(grf.GrfError, match="C8"):
        grf.read_header(f)


def test_version_0x300_header(grf: ModuleType, tmp_path: Path) -> None:
    """Header only: the 0x300 table layout is unverified against a real archive."""
    path = tmp_path / "big.grf"
    header = b"Master of Magic\x00" + b"\x00" * 14
    header += struct.pack("<QII", 5_000_000_000, 107, 0x300)
    path.write_bytes(header)
    with path.open("rb") as f:
        h = grf.read_header(f)
    assert (h.version, h.table_offset, h.entry_count) == (0x300, 46 + 5_000_000_000, 100)
    info = grf.summary(path)
    assert info["version"] == "0x300" and "table_error" in info


def test_cli_info_and_ls(
    grf: ModuleType, archive: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert grf.main(["info", str(archive)]) == 0
    assert json.loads(capsys.readouterr().out)["files"] == 4
    assert grf.main(["ls", str(archive), "--grep", r"secret"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1 and lines[0].startswith("E 0x05")


def test_mixcrypt_needs_the_host_local_decoder_and_never_a_repo_one(
    grf: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Batt, 2026-10-05: MIXCRYPT study only. The decoder lives OUTSIDE the repo; without it the
    reader refuses (C8), and it never loads a decoder from inside the repo or a writable dir."""
    entry = grf.Entry(b"data\\x.spr", 8, 8, 8, 0x03, 46)
    assert not grf.decodable(entry, decode_des=True)
    assert grf.decodable(entry, decode_des=True, decode_mixcrypt=True)
    missing = tmp_path / "nothing-here"
    missing.mkdir(mode=0o700)
    with pytest.raises(grf.GrfError, match="no study decoder"):
        grf.load_mixcrypt(missing)
    with pytest.raises(grf.GrfError, match="inside the repo"):
        grf.load_mixcrypt(grf.REPO / "scripts")
    loose = tmp_path / "loose"
    loose.mkdir(mode=0o700)
    (loose / grf.PRIVATE_MODULE).write_text("def decode(d, z, des):\n    return d\n")
    loose.chmod(0o777)
    with pytest.raises(grf.GrfError, match="writable"):
        grf.load_mixcrypt(loose)
    loose.chmod(0o700)
    (loose / grf.PRIVATE_MODULE).chmod(0o600)
    assert grf.load_mixcrypt(loose).decode(b"x", 1, None) == b"x"
    monkeypatch.setenv(grf.PRIVATE_ENV, str(loose))
    assert grf.private_dir() == loose.resolve()
