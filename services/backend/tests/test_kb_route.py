"""scripts/kb_route.py: the workflow route's parsers (no network; rAthena-shaped fixtures)."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "kb_route.py"


@pytest.fixture(scope="module")
def kr() -> ModuleType:
    sys.path.insert(0, str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("kb_route", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_npc_blocks_menus_inputs_and_dialog_lines(kr: ModuleType) -> None:
    text = (
        "// a comment\n"
        "town_in,53,43,6\tscript\tGuide#t\t86,{\n"
        '\tmes "[Guide]";\n'
        '\tmes "Hello there.";\n'
        '\tswitch(select("Go on.:Tell me more.:" + "Bye.")) {\n'
        "\tinput .@n;\n"
        '\tmenu "Yes",L_Yes,"No",L_No;\n'
        "}\n"
        "-\tscript\tHelper\t-1,{\n"
        '\tif (select("A:B") == 1) end;\n'
        "}\n"
    )
    blocks = kr.npcs(text, "f.txt")
    assert [b["name"] for b in blocks] == ["Guide#t", "Helper"]
    g = blocks[0]
    assert (g["map"], g["x"], g["y"], g["line"]) == ("town_in", 53, 43, 2)
    assert g["menus"][0] == {
        "line": 5,
        "call": "select",
        "options": ["Go on.", "Tell me more.", "Bye."],
    }
    assert g["menus"][1]["options"] == ["Yes", "No"] and g["inputs"] == [{"line": 6, "var": ".@n"}]
    assert [m["text"] for m in g["mes"]] == ["[Guide]", "Hello there."]
    assert blocks[1]["menus"][0]["options"] == ["A", "B"]


def test_base_level_from_a_table(kr: ModuleType) -> None:
    table = [10, 20, 30]  # 1->2 needs 10, 2->3 needs 20, 3->4 needs 30
    assert kr.base_level_after(0, table) == 1
    assert kr.base_level_after(29, table) == 2
    assert kr.base_level_after(30, table) == 3
    assert kr.base_level_after(10_000, table) == 4


def test_map_table_weights_by_population(kr: ModuleType) -> None:
    mobs = {
        1: {"name": "A", "level": 1, "hp": 50, "base_exp": 2, "job_exp": 1, "aggressive": False},
        2: {"name": "B", "level": 3, "hp": 150, "base_exp": 6, "job_exp": 3, "aggressive": True},
    }
    rows = kr.map_table(
        {"m": [{"id": 1, "amount": 3, "boss": False}, {"id": 2, "amount": 1, "boss": False}]}, mobs
    )
    r = rows[0]
    assert (r["level"], r["hp"], r["job_exp"], r["aggressive_share"]) == (1.5, 75, 1.5, 0.25)
