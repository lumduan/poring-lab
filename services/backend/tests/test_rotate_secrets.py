"""scripts/rotate_secrets.py: the .env rewrite and the generators' charset rules (no Docker)."""

import importlib.util
import re
import stat
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "rotate_secrets.py"


@pytest.fixture(scope="module")
def rs() -> ModuleType:
    spec = importlib.util.spec_from_file_location("rotate_secrets", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rotate_secrets"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_rewrite_replaces_in_place_keeps_comments_and_appends_missing(rs: ModuleType) -> None:
    text = "# DB_PASSWORD=commented\nA=1\nDB_PASSWORD=old\nB=2\nDB_PASSWORD=dup\n"
    out = rs.rewrite_env(text, {"DB_PASSWORD": "new", "C": "3"})
    assert out == "# DB_PASSWORD=commented\nA=1\nDB_PASSWORD=new\nB=2\nDB_PASSWORD=dup\nC=3\n"


@pytest.mark.parametrize(
    ("name", "pattern"),
    [
        ("DB_PASSWORD", r"[0-9a-f]{32}"),
        ("DB_ROOT_PASSWORD", r"[0-9a-f]{32}"),
        ("RATHENA_SERVER_PASSWORD", r"[0-9a-f]{23}"),  # <= 23: char/map 24-byte buffers
        ("RATHENA_TEST_PASSWORD", r"[A-Za-z0-9]{16}"),  # entrypoint: 8-32 of [A-Za-z0-9]
        ("WIN_LAB_PASSWORD", r"(?=.*[a-z])(?=.*[A-Z])(?=.*\d)[A-Za-z0-9]{20}"),
        ("DB_TH_PASSWORD", r"[0-9a-f]{32}"),
        ("RATHENA_TH_SERVER_USER", r"srv_[0-9a-f]{8}"),  # entrypoint: 4-23 characters
        ("RATHENA_TH_SERVER_PASSWORD", r"[0-9a-f]{23}"),
        ("RATHENA_TH_AGENT_USER", r"tha_[0-9a-f]{8}"),
        ("RATHENA_TH_GM_USER", r"thv_[0-9a-f]{8}"),
        ("RATHENA_TH_GM_PASSWORD", r"[A-Za-z0-9]{16}"),
    ],
)
def test_generators_match_their_consumers_rules(rs: ModuleType, name: str, pattern: str) -> None:
    for _ in range(50):
        assert re.fullmatch(pattern, rs.GENERATORS[name]())


def test_rotate_writes_env_atomically_mode_600_and_never_returns_values(
    rs: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = tmp_path / ".env"
    env.write_text("RATHENA_TEST_PASSWORD=old\nX=1\n")
    names = rs.rotate(["RATHENA_TEST_PASSWORD"], env_path=env)
    assert names == ["RATHENA_TEST_PASSWORD"]
    new = rs.parse_env(env.read_text())["RATHENA_TEST_PASSWORD"]
    assert new != "old" and re.fullmatch(r"[A-Za-z0-9]{16}", new)
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    assert new not in capsys.readouterr().out
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".env.")]  # no temp left


def test_unknown_names_are_refused(rs: ModuleType, tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("A=1\n")
    with pytest.raises(SystemExit):
        rs.rotate(["RDP_PASSWORD"], env_path=env)
    assert env.read_text() == "A=1\n"


def test_set_writes_non_secret_values_and_reads_them_back(rs: ModuleType, tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("RDP_GFX=\nX=1\n")
    assert rs.set_values(["RDP_GFX=progressive", "GAME_REGION=248,99,784,625"], env_path=env)
    back = rs.parse_env(env.read_text())
    assert (back["RDP_GFX"], back["GAME_REGION"], back["X"]) == (
        "progressive",
        "248,99,784,625",
        "1",
    )


@pytest.mark.parametrize(
    "pair", ["RDP_PASSWORD=x", "WIN_LAB_PASSWORD=x", "API_TOKEN=x", "RDP_USER=x"]
)
def test_set_refuses_secret_looking_names(rs: ModuleType, tmp_path: Path, pair: str) -> None:
    env = tmp_path / ".env"
    env.write_text("A=1\n")
    with pytest.raises(SystemExit):
        rs.set_values([pair], env_path=env)
    assert env.read_text() == "A=1\n"


def test_th_secrets_are_first_time_only(
    rs: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """db-th already initialised holds its passwords: rotating them in .env alone would break it."""
    env = tmp_path / ".env"
    env.write_text("DB_TH_PASSWORD=\n")
    monkeypatch.setattr(rs, "container_exists", lambda name: True)
    with pytest.raises(SystemExit, match="first-time only"):
        rs.rotate(["DB_TH_PASSWORD"], env)
    assert env.read_text() == "DB_TH_PASSWORD=\n"
    monkeypatch.setattr(rs, "container_exists", lambda name: False)
    assert rs.rotate(["DB_TH_PASSWORD", "RATHENA_TH_GM_USER"], env) == [
        "DB_TH_PASSWORD", "RATHENA_TH_GM_USER"]  # fmt: skip
    back = rs.parse_env(env.read_text())
    assert len(back["DB_TH_PASSWORD"]) == 32 and back["RATHENA_TH_GM_USER"].startswith("thv_")
