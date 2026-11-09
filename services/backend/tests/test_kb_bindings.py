"""scripts/kb_bindings.py: the L3 parsers on rAthena-shaped fixtures (no network, no GPL text)."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "kb_bindings.py"


@pytest.fixture(scope="module")
def kb() -> ModuleType:
    sys.path.insert(0, str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("kb_bindings", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_only_scored_selects_are_quiz_answers(kb: ModuleType) -> None:
    text = (
        "town_in,1,2,3\tscript\tTester#q\t86,{\n"
        '\tmes "[Tester]";\n'
        '\tmes "1. Which colour?";\n'
        "\tnext;\n"
        '\tif (select("Red:Blue:Green") == 2)\n'
        "\t\tset .@score,.@score+10;\n"
        '\tmes "2. Which number?";\n'
        '\tif (select("One:" + "Two") == 1) .@score += 20;\n'
        '\tif (select("Go now:Stay") == 1)\n'
        '\t\twarp "town", 1, 1;\n'
        "}\n"
    )
    got = kb.quiz_answers(text, "f.txt")
    assert [(g["correct"], g["points"], g["options"]) for g in got] == [
        (2, 10, ["Red", "Blue", "Green"]), (1, 20, ["One", "Two"])]  # fmt: skip
    assert got[0]["question"] == ["1. Which colour?"] and got[0]["npc"] == "Tester#q"


def test_kafra_towns_fees_arrivals_and_menus(kb: ModuleType) -> None:
    funcs = (
        "function\tscript\tF_Kafra\t{\n"
        '\tcase 1:\tsetarray .@K_Menu0$[0],"Save","Cancel"; break;\n'
        '\tdefault: setarray .@K_Menu0$[0],"Save","Teleport","Cancel"; break;\n'
        "}\n"
        "function\tscript\tF_KafTele\t{\n"
        '\tif (@wrpD$[.@j] == "Townb") warp "townb", 10, 20;\n'
        "}\n"
        "function\tscript\tF_KafSet\t{\n"
        '\tif (.@map$ == "towna") {\n'
        '\t\tsetarray @wrpD$[0], "Townb", "Townc";\n'
        "\t\tsetarray @wrpP[0], 600, 1200;\n"
        "\t}\n"
        "}\n"
    )
    towns, menus = kb.kafra(funcs)
    assert towns == {"towna": {"destinations": ["Townb", "Townc"], "fees": [600, 1200],
                               "arrive": {"Townb": ["townb", 10, 20], "Townc": None}}}  # fmt: skip
    assert menus == {"1": ["Save", "Cancel"], "default": ["Save", "Teleport", "Cancel"]}


def test_map_flags_lists_the_maps_of_each_flag_file(kb: ModuleType) -> None:
    """L3 map.flags (2026-11-09, nav.escape): active `<map> mapflag <flag>` lines only."""
    noteleport = (
        "//===== a header =====\n"
        "town_in01\tmapflag\tnoteleport\n"
        "//town_in02\tmapflag\tnoteleport\n"  # commented out: not a flag at this ref
        "field_9\tmapflag\tnoteleport\t// a trailing note\n"
        "field_9\tmapflag\tnoteleport\n"
        "dun_1\tmapflag\tnomemo\n"  # another flag in the file: not this one
    )
    noreturn = "//dun_2\tmapflag\tnoreturn\nship_1\tmapflag\tnoreturn\n"
    got = kb.map_flags({"noteleport": noteleport, "noreturn": noreturn})
    assert got["noteleport"] == ["field_9", "town_in01"] and got["noreturn"] == ["ship_1"]
    assert got["status"] == "generated" and "noteleport.txt" in got["source"]
    # a LEAF (lists, not a table per map): resolve hands it to escape, which takes no parameter
    assert not all(isinstance(v, dict) for v in got.values())
