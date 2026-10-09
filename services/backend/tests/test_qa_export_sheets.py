"""qa_export.Sheets: a monster's sprite FILE STEM is the client's own name when the KB's
monster_sprite_names.json lists the species (labels-v2-plan 7.6: for 1011, 1051, 1053 and 1184 it
is not rAthena's aegis name), else the aegis name; a species with neither gets no sheet and is
reported. SYNTHETIC tables and placeholder files only (never client data, CLAUDE.md rule 4)."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "qa_export.py"


@pytest.fixture
def qa(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    sys.path.insert(0, str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("qa_export_sheets_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # the files are placeholders: the parsers and the sheet are stand-ins that record the stem
    monkeypatch.setattr(module, "parse_act", lambda b: b.decode())
    monkeypatch.setattr(module, "parse_spr", lambda b: b.decode())
    monkeypatch.setattr(module, "SpriteSheet", lambda act, spr: ("sheet", act, spr))
    return module


def files(d: Path, *stems: str) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    for s in stems:
        (d / f"{s}.act").write_text(f"act:{s}")
        (d / f"{s}.spr").write_text(f"spr:{s}")
    return d


def test_the_client_stem_wins_over_the_aegis_name(qa: ModuleType, tmp_path: Path) -> None:
    d = files(tmp_path / "spr", "client_stem_a", "aegis_b")
    sheets = qa.Sheets(d, stems={1011: "client_stem_a"}, aegis={1011: "AEGIS_A", 1002: "AEGIS_B"})
    assert sheets(1011) == ("sheet", "act:client_stem_a", "spr:client_stem_a")
    assert sheets(1002) == ("sheet", "act:aegis_b", "spr:aegis_b")  # not in the table: aegis
    assert sheets.stem(1011) == ("client_stem_a", "client_table")
    assert sheets.stem(1002) == ("aegis_b", "aegis")
    assert sheets.missing == {}


def test_a_species_with_neither_name_gets_no_sheet_and_is_reported(
    qa: ModuleType, tmp_path: Path
) -> None:
    d = files(tmp_path / "spr", "aegis_c")
    sheets = qa.Sheets(d, stems={1053: None, 1184: "stem_no_files"}, aegis={1053: "AEGIS_C"})
    assert sheets(9999) is None  # in neither table
    assert sheets(1053) is None  # listed without a client name: never falls back to a guess
    assert sheets(1184) is None  # a client stem whose files were not decoded
    assert sheets(None) is None
    assert sheets.missing == {9999: "no_name", 1053: "no_client_name",
                              1184: "no_files:client_table"}  # fmt: skip


def test_without_the_table_the_aegis_name_decides_as_before(qa: ModuleType, tmp_path: Path) -> None:
    d = files(tmp_path / "spr", "aegis_d")
    sheets = qa.Sheets(d, stems={}, aegis={1063: "AEGIS_D", 1113: "AEGIS_E"})
    assert sheets(1063) == ("sheet", "act:aegis_d", "spr:aegis_d")
    assert sheets(1113) is None
    assert sheets.missing == {1113: "no_files:aegis"}


def test_sprite_stems_reads_the_mob_names_table(qa: ModuleType, tmp_path: Path) -> None:
    table: dict[str, Any] = {"mobs": {
        "1011": {"aegis": "AEGIS_X", "client_sprite": "Client_Stem_X", "stem": "client_stem_x",
                 "differs_from_aegis": True, "files_present": True},
        "1002": {"aegis": "AEGIS_Y", "client_sprite": None},
    }, "problems": []}  # fmt: skip
    path = tmp_path / "monster_sprite_names.json"
    path.write_text(json.dumps(table))
    assert qa.sprite_stems(path) == {1011: "client_stem_x", 1002: None}
    assert qa.sprite_stems(tmp_path / "absent.json") == {}


def test_the_default_sheets_read_the_module_tables(
    qa: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    classes = tmp_path / "classes.json"
    classes.write_text(json.dumps({"some_map": {"1051": {"aegis": "AEGIS_Z"}}}))
    names = tmp_path / "monster_sprite_names.json"
    names.write_text(json.dumps({"mobs": {"1051": {"stem": "client_stem_z"}}}))
    monkeypatch.setattr(qa, "KB_CLASSES", classes)
    monkeypatch.setattr(qa, "KB_SPRITE_NAMES", names)
    d = files(tmp_path / "spr", "client_stem_z")
    assert qa.Sheets(d)(1051) == ("sheet", "act:client_stem_z", "spr:client_stem_z")
