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


# --- warp lists: the first-workflow KB's complete lists (walk@17 refuses unlisted maps) ---


def test_required_maps_cover_the_training_grounds_and_the_merchant_route(kr: ModuleType) -> None:
    req = set(kr.REQUIRED_WARP_MAPS)
    assert {f"new_{n}-{m}" for n in range(1, 6) for m in range(1, 5)} <= req
    assert {"alberta", "alberta_in", "prontera", "morocc", "morocc_in"} <= req


def test_the_kb_list_replaces_the_hand_list_and_says_none_explicitly(kr: ModuleType) -> None:
    hand = {"town": [{"x": 1, "y": 1, "span_x": 1, "span_y": 1, "to_map": "x", "to_x": 1,
                      "to_y": 1, "name": "w"}],
            "field": [{"x": 5, "y": 5, "span_x": 2, "span_y": 2, "to_map": "town", "to_x": 1,
                       "to_y": 1, "name": "f"}]}  # fmt: skip
    kb = {"maps": {
        "town": {"loaded_by_server": True, "warps": [
            {"key": "npc/w.txt:1", "kind": "warp", "x": 1, "y": 1, "span_x": 1, "span_y": 1,
             "to_map": "x", "to_x": 1, "to_y": 1, "name": "w", "drawn": True},
            {"key": "npc/q.txt:9", "kind": "warp", "x": 7, "y": 8, "span_x": 0, "span_y": 0,
             "to_map": "y", "to_x": 2, "to_y": 2, "name": "q", "drawn": True}],
            "npcs": [{"key": "npc/t.txt:3", "x": 20, "y": 20, "touch": True,
                      "trigger_span": [2, 1], "drawn": "conditional",
                      "script": {"warps": [{"map": "z", "x": 3, "y": 4}]}},
                     {"key": "npc/d.txt:4", "x": 30, "y": 30, "touch": True,
                      "trigger_span": [3, 3], "script": {"warps": []}}]},
        "yard": {"loaded_by_server": True, "warps": [], "npcs": []},
        "ghost": {"loaded_by_server": False, "warps": [], "npcs": []},
    }}  # fmt: skip
    warps, source, changed = kr.merge_kb_warps(hand, kb)
    assert [(w["x"], w["y"], w["kind"]) for w in warps["town"]] == [
        (1, 1, "warp"), (7, 8, "warp"), (20, 20, "touch_npc")]  # fmt: skip
    touch = warps["town"][2]
    assert (touch["span_x"], touch["span_y"], touch["to_map"]) == (2, 1, "z")
    assert warps["yard"] == [] and "ghost" not in warps  # none, vs unknown
    assert warps["field"] == hand["field"] and source["field"] == "WARP_FILES"
    assert source["town"].startswith("first_workflow")
    assert changed == {"town": {"hand": 1, "kb": 3, "added": 2, "dropped": 0}}
    assert kr.missing_required(warps, ("town", "yard", "ghost")) == ["ghost"]
    assert kr.merge_kb_warps(hand, None)[0] == hand
