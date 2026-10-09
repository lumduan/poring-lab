"""scripts/kb_first_workflow.py: KB P1 for the first workflow. Synthetic script snippets in
rAthena's formats with synthetic names only -- no rAthena text is committed (GPL)."""

from __future__ import annotations

import gzip
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[3]


def load() -> ModuleType:
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "kb_first_workflow", ROOT / "scripts" / "kb_first_workflow.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["kb_first_workflow"] = mod
    spec.loader.exec_module(mod)
    return mod


fw = load()

NPC_HPP = """
enum e_job_types
{
	NPC_RANGE1_START = 44,
	JT_WARPNPC,
	JT_1_ALPHA,
	JT_1_BETA, // a comment
	JT_HIDDEN_NPC = 111,
	NPC_RANGE1_END,

	JT_HIDDEN_WARP_NPC = 139,

	NPC_RANGE2_START = 400,
	JT_4_GAMMA,
	NPC_RANGE2_END,
	NPC_RANGE3_START = 10000,
	JT_4_DELTA = 10005,
	NPC_RANGE3_END,
	JT_INVISIBLE = 32767,
	JT_FAKENPC = -1
};
"""
SPRITES = fw.Sprites(fw.npc_constants(NPC_HPP), {"BLOB_A": 1901, "BLOB_B": 1902})


def world(files: dict[str, str], maps: set[str] | None = None):  # type: ignore[no-untyped-def]
    recs, problems = [], []
    for name, text in files.items():
        r, p = fw.parse_file(text, name)
        recs += r
        problems += p
    server = maps or {r.map for r in recs if r.map}
    return fw.World(list(files), recs, problems, SPRITES, server)


# --- the load list -------------------------------------------------------------------------------


def test_load_list_follows_imports_like_map_reloadnpc_sub() -> None:
    confs = {
        "main.conf": "// header\nnpc: a.txt\nimport: sub.conf\n//npc: commented.txt\n"
        "npc: b.txt // trailing comment\nfrobnicate: x\n",
        "sub.conf": "npc: c.txt\nnpc: a.txt\ndelnpc: b.txt\nnpc: d.txt\n",
    }
    files, events = fw.load_list(confs.__getitem__, "main.conf")
    # b.txt is deleted by sub.conf BEFORE main.conf lists it, so it loads (load order matters)
    assert files == ["a.txt", "c.txt", "d.txt", "b.txt"]
    kinds = [e["event"] for e in events]
    assert kinds == ["listed_twice", "delnpc", "unknown_setting"]


# --- the parser ---------------------------------------------------------------------------------

SCRIPT_FILE = (
    "/* a block comment\n"
    "map_a,1,1,4\tscript\tNot Real\t46,{ }\n"
    "*/\n"
    "// map_a,2,2,4\tscript\tAlso Not\t46,{ }\n"
    "map_a,10,20,4\tscript\tTalker One::talker1\t1_ALPHA,{\n"
    '\tmes "a { brace in text";  // and } one in a comment\n'
    "\t/* } */\n"
    '\tif (qvar == 1) { savepoint "map_b",5,6,1,1; warp "map_c",7,8; }\n'
    "\tclose;\n"
    "}\n"
    "map_a,11,20,2\tduplicate(talker1)\tTalker Two\t1_BETA\n"
    "map_a,30,30,0\twarp\twarp_ab\t2,3,map_b,40,41\t/*a note*/\n"
    "map_a,0,0\tmonster\tSome Blob\t1901,7,5000,1000\n"
    "map_a\tmapflag\tnoteleport\n"
    "map_a,12,12,4\tshop\tSeller\t1_ALPHA,501:10,502:-1\n"
    "-\tscript\tFloating\t-1,{\n\tend;\n}\n"
    "function\tscript\tF_Helper\t{\n\treturn;\n}\n"
)


def test_parse_file_mirrors_npc_parsesrcfile() -> None:
    recs, problems = fw.parse_file(SCRIPT_FILE.replace("\n", "\r\n"), "f.txt")
    assert problems == []
    types = [(r.type, r.line) for r in recs]
    assert types == [
        ("script", 5),
        ("duplicate", 11),
        ("warp", 12),
        ("monster", 13),
        ("mapflag", 14),
        ("shop", 15),
        ("script", 16),
        ("function", 19),
    ]
    talker = recs[0]
    assert talker.body is not None and talker.body.startswith("{") and talker.end_line == 10
    assert recs[2].w4 == "2,3,map_b,40,41"  # the trailing block comment is not part of w4
    assert recs[6].map is None and recs[7].map is None


def test_unbalanced_script_is_reported() -> None:
    recs, problems = fw.parse_file('map_a,1,1,4\tscript\tBroken\t46,{\n\tmes "x";\n', "g.txt")
    assert [p["problem"] for p in problems] == ["script_body_unbalanced"]


def test_npc_constants_follow_c_enum_rules() -> None:
    c = fw.npc_constants(NPC_HPP)
    assert (c["JT_WARPNPC"], c["JT_1_ALPHA"], c["JT_1_BETA"]) == (45, 46, 47)
    assert (c["JT_HIDDEN_NPC"], c["NPC_RANGE1_END"], c["JT_4_GAMMA"]) == (111, 112, 401)
    assert (c["JT_4_DELTA"], c["NPC_RANGE3_END"], c["JT_FAKENPC"]) == (10005, 10006, -1)


def test_sprite_resolution_like_npc_parseview() -> None:
    assert SPRITES.resolve("86,{") == (86, None)
    assert SPRITES.resolve("1_BETA,3,3,{") == (47, None)
    assert SPRITES.resolve("BLOB_B") == (1902, None)
    sid, warn = SPRITES.resolve("NO_SUCH_THING")
    assert sid == 32767 and warn
    assert SPRITES.sprite_class(47) == "npc" and SPRITES.sprite_class(1901) == "mob"
    assert SPRITES.sprite_class(111) == "hidden" and SPRITES.sprite_class(7) == "player_job"
    assert SPRITES.portal == 45


# --- body facts and NPC entries ------------------------------------------------------------------


def test_body_facts_pair_a_savepoint_with_the_next_warp() -> None:
    body = (
        "{\n"
        '\tif (qvar == 2 && other_q == 3) { savepoint "map_b",5,6,1,1;\n'
        '\t\twarp "map_c",7,8; }\n'
        '\twarp "map_d",1,2;\n'
        "\twarp .@where$,1,2;\n"
        "\tif (Zeny < 500) end;\n"
        '\tif (getskilllv("SK_ONE") > 8) callfunc "F_Helper";\n'
        "OnInit:\n\thideonnpc strnpcinfo(0);\n\tend;\n}\n"
    )
    f = fw.body_facts(body, 100)
    assert [(w["map"], w["line"], w["savepoint"]) for w in f["warps"]] == [
        ("map_c", 102, ["map_b", 5, 6]),
        ("map_d", 103, None),
    ]
    assert f["warps_dynamic"] == [{"line": 104, "expr": ".@where$"}]
    assert f["var_tests"] == {"other_q": [3], "qvar": [2]}
    assert f["zeny_tests"] == [500] and f["skill_tests"] == [("SK_ONE", ">", 8)]
    assert f["labels"] == ["OnInit"] and f["callfunc"] == ["F_Helper"]
    assert f["state_commands"][0]["target"] == "self"


def test_npc_kinds_and_drawn() -> None:
    text = (
        'map_a,1,1,4\tscript\tPlain\t1_ALPHA,{\n\tmes "x";\n}\n'
        'map_a,2,2,0\tscript\tTrap\t111,2,2,{\nOnTouch:\n\twarp "map_b",1,1;\n}\n'
        "map_a,3,3,0\tscript\tFake\t-1,{\n\tend;\n}\n"
        'map_a,4,4,0\tscript\tRing\tWARPNPC,1,1,{\nOnTouch:\n\twarp "map_b",2,2;\n}\n'
        "map_a,5,5,4\tscript(DISABLED)\tAsleep\t1_ALPHA,{\n\tend;\n}\n"
        "map_a,6,6,4\tscript\tShy\t1_BETA,{\nOnInit:\n\tdisablenpc strnpcinfo(0);\n\tend;\n}\n"
        "map_a,7,7,4\tduplicate(Plain)\tPlain Copy\t4_GAMMA\n"
        "map_a,8,8,4\tshop\tStall\t1_ALPHA,501:10\n"
        'map_a,9,9,4\tscript\tNamed#x\t1_ALPHA,{\nOnInit:\n\thideonnpc "Named#x";\n\tend;\n}\n'
    )
    w = world({"n.txt": text})
    got = {
        n["name"]: (n["kind"], n["sprite"], n["drawn"]) for n in fw.map_entry("map_a", w)["npcs"]
    }
    assert got == {
        "Plain": ("dialog", 46, True),
        "Trap": ("invisible_trigger", 111, False),
        "Fake": ("invisible", -1, False),
        "Ring": ("warp_portal", 45, True),
        "Asleep": ("dialog", 46, False),
        "Shy": ("dialog", 47, "conditional"),
        "Plain Copy": ("dialog", 401, True),
        "Stall": ("shop", 46, True),
        "Named#x": ("dialog", 46, "conditional"),
    }
    copy = next(n for n in fw.map_entry("map_a", w)["npcs"] if n["name"] == "Plain Copy")
    assert copy["duplicate_of"] == "n.txt:1" and copy["script"]["mes_lines"] == 1


# --- the scope ----------------------------------------------------------------------------------

GROUNDS = {
    "grounds.txt": (
        "yard_1-1,10,10,0\twarp\tg1\t1,1,yard_1-2,5,5\n"
        "yard_2-1,10,10,0\twarp\tg2\t1,1,yard_2-2,5,5\n"
        "yard_1-2,20,20,4\tscript\tDesk\t1_ALPHA,{\n"
        '\tif (select("a:b") == 1) { warp "yard_1-3",1,1; end; }\n'
        '\tsavepoint "town_x",9,9,1,1;\n\twarp "town_x",9,9;\n}\n'
        "yard_2-2,20,20,4\tduplicate(Desk)\tDesk#2\t1_ALPHA\n"
        "yard_1-3,30,30,4\tscript\tExam\t1_BETA,{\n"
        '\tsavepoint "yard_1-2",3,3,1,1;\n\twarp "yard_1-3",2,2;\n'
        '\tsavepoint "town_y",8,8,1,1;\n\twarp "town_y_in",4,4;\n'
        "\twarp .@pick$,1,1;\n}\n"
    ),
}


def test_grounds_closure_exits_and_unreachable_copies() -> None:
    maps = {"yard_1-1", "yard_1-2", "yard_1-3", "yard_2-1", "yard_2-2", "yard_9-9", "town_x"}
    w = world(GROUNDS, maps)
    g = fw.grounds(w, ["yard_1-1", "yard_2-1"])
    assert g["maps"] == ["yard_1-1", "yard_2-1", "yard_1-2", "yard_2-2", "yard_1-3"]
    assert g["family"] == ["yard_1-1", "yard_1-2", "yard_1-3", "yard_2-1", "yard_2-2", "yard_9-9"]
    assert g["unreachable"] == ["yard_9-9"]
    exits = {(e["from"], e["to"]) for e in g["exits"]}
    assert exits == {
        ("yard_1-2", "town_x"),
        ("yard_2-2", "town_x"),
        ("yard_1-3", "town_y_in"),
        ("yard_1-3", None),
    }


QUEST = {
    "quest.txt": (
        "hall_in,10,10,4\tscript\tBoss\t1_ALPHA,{\n"
        '\tif (step_q == 3) { callfunc "Job_Change",Job_Tester; end; }\n'
        "\tif (Zeny >= 1000) set step_q,1;\n"
        "\tset route_q,rand(1,2);\n}\n"
        "hall_in,20,20,4\tscript\tStore\t1_BETA,{\n"
        "\tif (route_q == 1 || route_q == 2) set step_q,2;\n}\n"
        "far_in,5,5,4\tscript\tReceiver\t1_BETA,{\n\tif (route_q == 1) set step_q,3;\n}\n"
        "function\tscript\tF_QuestHook\t{\n\tif (route_q == 2) set step_q,3;\n\treturn;\n}\n"
    ),
    "other.txt": 'isle,7,7,4\tscript\tHelper\t1_ALPHA,{\n\tcallfunc "F_QuestHook";\n}\n',
}


def test_job_quest_finds_changer_file_npcs_and_function_callers() -> None:
    w = world(QUEST)
    q = fw.job_quest(w, "JOB_TESTER")
    assert q["constant"] == "Job_Tester" and q["files"] == ["quest.txt"]
    assert q["maps"] == ["far_in", "hall_in", "isle"]
    assert set(q["variables"]) == {"step_q", "route_q"}
    roles = {n["key"]: (n["role"], n["tests"]) for n in q["npcs"]}
    assert roles["quest.txt:1"] == ("job_change", {"step_q": [3]})
    assert roles["quest.txt:6"] == ("quest", {"route_q": [1, 2]})
    assert roles["quest.txt:9"] == ("quest", {"route_q": [1]})
    assert roles["other.txt:1"] == ("function_caller", {"route_q": [2]})
    req = fw.requirement_checks(w, q)
    assert req["zeny_tests"] == [1000]


KAFRA = {
    "kaf_funcs.txt": (
        "function\tscript\tF_SetList\t{\n"
        "\t.@map$ = strnpcinfo(4);\n"
        '\tif (.@map$ == "town_a") {\n'
        '\t\tsetarray @wrpD$[0], "Bee", "Cee";\n\t\tsetarray @wrpP[0], 100, 200;\n'
        '\t} else if (.@map$ == "town_b") {\n'
        '\t\tsetarray @wrpD$[0], "Aye";\n\t\tsetarray @wrpP[0], 300;\n\t}\n\treturn;\n}\n'
        "function\tscript\tF_Go\t{\n"
        "\tif (countitem(7777) > 0) delitem 7777,1;\n"
        '\tif (@wrpD$[.@j] == "Aye") warp "town_a", 1, 1;\n'
        '\telse if (@wrpD$[.@j] == "Bee") {\n'
        '\t\tif (checkre(0) == true) warp "town_b", 9, 9;\n\t\telse warp "town_b", 2, 2;\n\t}\n'
        '\telse if (@wrpD$[.@j] == "Cee") warp "town_c", 3, 3;\n\tend;\n}\n'
    ),
    "kafras.txt": (
        'town_a,5,5,4\tscript\tKiosk A\t1_ALPHA,{\n\tcallfunc "F_SetList";\n}\n'
        'town_b,5,5,4\tscript\tKiosk B\t1_ALPHA,{\n\tcallfunc "F_SetList";\n}\n'
    ),
    "warps.txt": "town_c,1,1,0\twarp\tc_to_a\t1,1,town_a,4,4\n"
    "hall_in,1,1,0\twarp\thall_out\t1,1,town_a,6,6\ntown_a,9,9,0\twarp\ta_in\t1,1,hall_in,2,2\n",
}


def test_kafra_tables_and_travel_policies() -> None:
    w = world(KAFRA)
    edges, info = fw.kafra_edges(w)
    assert info["free_ticket_item"] == 7777
    got = {(e["from"], e["to"], tuple(e["to_cell"]), e["zeny"]) for e in edges}
    assert got == {
        ("town_a", "town_b", (2, 2), 100),
        ("town_a", "town_c", (3, 3), 200),
        ("town_b", "town_a", (1, 1), 300),
    }
    trips = fw.legs(fw.all_edges(w), "hall_in", ["town_b", "town_c"])
    assert trips["town_b"]["walk"] is None
    b = trips["town_b"]["walk_kafra"]
    assert b["maps"] == ["hall_in", "town_a", "town_b"] and b["kafra_hops"] == 2
    c = trips["town_c"]["walk_kafra"]
    assert c["hops"] == 4 and c["zeny_listed"] == 200  # back from town_c on foot


# --- completeness ---------------------------------------------------------------------------------


def test_mentions_account_for_every_line_naming_a_map() -> None:
    files = {
        "a.txt": (
            "// yard_1-1 in a comment\n"
            "yard_1-1,1,1,4\tscript\tSign\t1_ALPHA,{\n"
            '\tmes "welcome to yard_1-1";\n'
            '\tif (.@m$ == "yard_1-1") end;\n'
            '\tmonster "yard_1-1",0,0,"--ja--",1901,1;\n'
            '\twarp "yard_1-1",2,2;\n'
            "}\n"
            "town_x,1,1,0\twarp\tback\t1,1,yard_1-1,3,3\n"
        )
    }
    w = world(files)
    out = fw.mentions(
        w,
        files.__getitem__,
        ["yard_1-1"],
        ["unloaded.txt"],
        read_other={"unloaded.txt": "yard_1-1\tmapflag\tnosave\n"}.__getitem__,
    )
    assert out["counts"]["yard_1-1"] == {
        "comment": 1,
        "defines_script": 1,
        "script_text": 1,
        "script_condition": 1,
        "script_monster": 1,
        "script_warp": 1,
        "warp_line_to": 1,
    }
    assert out["script_placements"] == [{"map": "yard_1-1", "at": "a.txt:5", "command": "monster"}]
    assert out["unclassified"] == []
    assert out["not_loaded_files_naming"] == {"yard_1-1": ["unloaded.txt"]}


def test_start_points_last_line_wins() -> None:
    conf = "start_point_pre: a_1,1,2:b_1,3,4\n//start_point_pre: x,1,1\nstart_point: z,1,1\n"
    assert fw.start_points(conf) == [("a_1", 1, 2), ("b_1", 3, 4)]


def test_kill_math_population_weighted() -> None:
    mobs = {
        1901: {"level": 1, "hp": 10, "base_exp": 2, "job_exp": 4, "ai": "04", "modes": []},
        1902: {"level": 3, "hp": 30, "base_exp": 6, "job_exp": 0, "ai": "01", "modes": []},
    }
    spawns = [{"id": 1901, "amount": 3}, {"id": 1902, "amount": 1}]
    km = fw.kill_math(spawns, mobs, 30, 100, {1901: 2.0}, {"04": 0x3885, "01": 0x81})
    assert km["job_exp_per_kill"] == 3.0 and km["kills_to_job_target"] == 10
    assert km["zeny_per_kill"] == 1.5 and km["kills_to_1000_zeny"] == 667
    assert km["species"]["1901"]["aggressive"] and not km["species"]["1902"]["aggressive"]


def test_check_packets_matches_cell_and_sprite(tmp_path: Path) -> None:
    doc = {
        "maps": {
            "yard_1-1": {
                "npcs": [{"x": 5, "y": 5, "sprite": 46, "key": "a.txt:1"}],
                "warps": [{"x": 9, "y": 9, "key": "a.txt:2"}],
            }
        }
    }
    rows = [
        {"type": "map_change", "map": "yard_1-1.gat"},
        {"type": "entity_appear", "objtype": 6, "x": 5, "y": 5, "job": 46, "gid": 1},
        {"type": "entity_appear", "objtype": 6, "x": 9, "y": 9, "job": 45, "gid": 2},
        {"type": "entity_appear", "objtype": 6, "x": 5, "y": 5, "job": 47, "gid": 3},
        {"type": "entity_appear", "objtype": 6, "x": 1, "y": 1, "job": 46, "gid": 4},
        {"type": "entity_appear", "objtype": 5, "x": 2, "y": 2, "job": 1901, "gid": 5},
    ]
    s = tmp_path / "sess"
    s.mkdir()
    with gzip.open(s / "packets.jsonl.gz", "wt") as f:
        f.write("\n".join(json.dumps(r) for r in rows) + "\n")
    out = fw.check_packets(doc, [s])
    assert out["matched"] == 2 and out["objects"] == 4
    assert out["mismatched"] == [{"map": "yard_1-1", "cell": [5, 5], "packet_job": 47, "kb": [46]}]
    assert out["missing_from_kb"][0]["cell"] == [1, 1]


def test_renewal_only_branches_and_fees() -> None:
    body = (
        "{\n"
        '\tswitch(select("a:b")) {\n'
        "\tcase 1:\n"
        "\t\tif (Zeny < 250) close;\n"
        "\t\tZeny = Zeny - 250;\n"
        "\t\tif (checkre(0))\n"
        '\t\t\twarp "port_a",1,1;\n'
        "\t\telse\n"
        '\t\t\twarp "port_a",2,2;\n'
        "\t\tend;\n"
        "\tcase 2:\n"
        "\t\tif (checkre(0)) {\n"
        '\t\t\twarp "port_b",3,3;\n'
        "\t\t} else {\n"
        '\t\t\twarp "port_b",4,4;\n'
        "\t\t}\n"
        "\t\tif (Zeny < .@price) end;\n"
        "\t}\n"
        "}\n"
    )
    f = fw.body_facts(body, 1)
    assert [(w["map"], w["x"], w["zeny"]) for w in f["warps"]] == [
        ("port_a", 2, 250),
        ("port_b", 4, fw.UNKNOWN_FEE),
    ]
    assert [w["x"] for w in f["warps_renewal_only"]] == [1, 3]
    assert f["warps"][1]["zeny_known"] is False


def _grid(rows: list[str]):  # type: ignore[no-untyped-def]
    """'.' walkable, '#' wall; row 0 is y = 0. One extra wall row/column, as the map edge."""
    from poring_dataset.mapcache import MapGrid

    ys, xs = len(rows) + 1, len(rows[0]) + 1
    cells = bytearray([1] * (xs * ys))
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            cells[x + y * xs] = 0 if ch == "." else 1
    return MapGrid("t", xs, ys, bytes(cells))


def test_rooms_and_room_level_trips() -> None:
    hall = _grid([".....#....", ".....#....", ".....#...."])  # two rooms split by a wall
    town = _grid(["..........", "..........", ".........."])
    rooms = fw.Rooms({"hall_in": hall, "town_a": town})
    left, right = rooms.near("hall_in", (1, 1)), rooms.near("hall_in", (8, 1))
    assert len(left) == 1 and len(right) == 1 and left != right
    assert rooms.span("hall_in", (5, 1), (1, 1)) == left | right
    edges = [
        # the hub stands in the right room; only the left room has the door to town
        {
            "from": "hall_in",
            "to": "hall_in",
            "via": "portal",
            "key": "w:1",
            "cell": [7, 0],
            "span": [0, 0],
            "to_cell": [2, 2],
        },
        {
            "from": "hall_in",
            "to": "hall_in",
            "via": "portal",
            "key": "w:2",
            "cell": [2, 0],
            "span": [0, 0],
            "to_cell": [7, 2],
        },
        {
            "from": "hall_in",
            "to": "town_a",
            "via": "portal",
            "key": "w:3",
            "cell": [0, 2],
            "span": [0, 0],
            "to_cell": [5, 1],
        },
        {
            "from": "town_a",
            "to": "hall_in",
            "via": "portal",
            "key": "w:4",
            "cell": [9, 1],
            "span": [0, 0],
            "to_cell": [1, 1],
        },
    ]
    quest = {
        "maps": ["hall_in", "town_a"],
        "npcs": [
            {"key": "q:1", "map": "hall_in", "cell": [4, 1], "role": "job_change", "tests": {}},
            {
                "key": "q:2",
                "map": "hall_in",
                "cell": [9, 1],
                "role": "quest",
                "tests": {"v": [1, 2]},
            },
            {"key": "q:3", "map": "town_a", "cell": [6, 0], "role": "quest", "tests": {"v": [1]}},
        ],
    }
    grad = [{"to": "hall_in", "to_cell": [1, 2]}]
    rt = fw.room_trips(edges, {}, quest, "hall_in", grad, {"hall_in": hall, "town_a": town})
    assert rt["hub"] == "q:2"
    trip = rt["trips"]["town_a"]["walk"]
    assert [e["key"] for e in trip["go"]] == ["w:1", "w:3"]
    assert [e["key"] for e in trip["back"]] == ["w:4", "w:2"]
    assert trip["map_changes"] == 2 and trip["hops"] == 4
    inside = {x["npc"]: (x["reachable"], len(x["via"])) for x in rt["home_inside"]}
    assert inside == {"q:1": (True, 0), "q:2": (True, 1)}


# --- npc_cells.json (npc-click-test.md 5.1 P1) ---


def _doc() -> dict:
    def n(key: str, x: int, y: int, sprite: int, drawn: object = True, **kw: object) -> dict:
        return {"key": key, "x": x, "y": y, "sprite": sprite, "sprite_class": "npc",
                "kind": "dialog", "drawn": drawn, **kw}  # fmt: skip

    return {
        "built_at": "synthetic", "rathena_ref": "abc",
        "completeness": {"counts": {"town": {}, "hall": {}}, "unclassified": [],
                         "script_placements": [{"map": "hall", "cmd": "monster"}]},
        "maps": {
            "town": {"loaded_by_server": True, "warps": [{"x": 9, "y": 9, "drawn": True}],
                     "npcs": [n("npc/a.txt:12", 10, 10, 86),
                              n("npc/a.txt:30", 11, 10, 705, "conditional"),
                              n("npc/b.txt:4", 12, 10, 111, False, sprite_class="hidden",
                                kind="invisible")]},
            "hall": {"loaded_by_server": True, "warps": [], "npcs": [n("npc/c.txt:1", 5, 5, 90)]},
            "far": {"loaded_by_server": False, "warps": [], "npcs": []},
        },
    }  # fmt: skip


def test_npc_cells_mark_drawn_and_completeness() -> None:
    cells = fw.npc_cells(_doc())["maps"]
    assert cells["town"]["complete"] is True
    assert cells["hall"]["complete"] is False  # a run-time placement names it
    assert cells["far"]["complete"] is False  # the server does not load it
    rows = {(r["x"], r["y"]): r for r in cells["town"]["npcs"]}
    assert rows[(10, 10)]["file"] == "npc/a.txt"
    assert (rows[(10, 10)]["line"], rows[(10, 10)]["probe"]) == (12, True)
    assert (rows[(11, 10)]["drawn"], rows[(11, 10)]["probe"]) == ("conditional", False)
    assert rows[(12, 10)]["probe"] is False


def test_packet_check_per_map_matches_cells_sprites_and_drawn_marks(tmp_path: Path) -> None:
    s = tmp_path / "s1"
    s.mkdir()
    rows = [
        {"type": "map_change", "map": "town.gat"},
        {"type": "entity_appear", "objtype": 6, "x": 10, "y": 10, "job": 86, "gid": 1},
        {"type": "entity_appear", "objtype": 6, "x": 11, "y": 10, "job": 705, "gid": 2,
         "effect_state": 2},
        {"type": "entity_appear", "objtype": 6, "x": 9, "y": 9, "job": 45, "gid": 3},
        {"type": "entity_appear", "objtype": 6, "x": 30, "y": 30, "job": 92, "gid": 4},
        {"type": "map_change", "map": "hall.gat"},
        {"type": "entity_appear", "objtype": 6, "x": 5, "y": 5, "job": 91, "gid": 5},
    ]  # fmt: skip
    with gzip.open(s / "packets.jsonl.gz", "wt") as f:
        f.write("\n".join(json.dumps(r) for r in rows) + "\n")
    per = fw.packet_check_per_map(_doc(), [s])
    town, hall = per["town"], per["hall"]
    assert (town["objects"], town["matched"], town["hidden_sent"]) == (4, 3, 1)
    assert town["missing"] == [[30, 30, 92]] and town["pass"] is False
    assert town["drawn_disagrees"] == []
    assert hall["wrong_sprite"] == [[5, 5, 91]] and hall["pass"] is False
    doc = _doc()
    doc["maps"]["town"]["npcs"][1]["drawn"] = True  # sent invisible, marked drawn: disagrees
    assert fw.packet_check_per_map(doc, [s])["town"]["drawn_disagrees"] == [[11, 10, 705, [2]]]
