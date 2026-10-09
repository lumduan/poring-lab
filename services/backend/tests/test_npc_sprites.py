"""scripts/lua51_tables.py and scripts/npc_sprites.py on SYNTHETIC chunks, grids and KB snippets
built here (never a client asset or rAthena data, CLAUDE.md rule 4)."""

import importlib.util
import struct
import sys
import zlib
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def _load(name: str) -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def lua() -> ModuleType:
    return _load("lua51_tables")


@pytest.fixture(scope="module")
def ns() -> ModuleType:
    return _load("npc_sprites")


# --- a hand-assembled Lua 5.1 chunk (the documented binary layout) ---

OP = {"MOVE": 0, "LOADK": 1, "GETGLOBAL": 5, "GETTABLE": 6, "SETGLOBAL": 7, "SETTABLE": 9,
      "NEWTABLE": 10, "CALL": 28, "RETURN": 30, "SETLIST": 34}  # fmt: skip
K = 256  # RK: a constant index


def abc(op: str, a: int, b: int = 0, c: int = 0) -> int:
    return OP[op] | a << 6 | c << 14 | b << 23


def abx(op: str, a: int, bx: int) -> int:
    return OP[op] | a << 6 | bx << 14


def lstr(s: str | None) -> bytes:
    if s is None:
        return struct.pack("<I", 0)
    raw = s.encode() + b"\x00"
    return struct.pack("<I", len(raw)) + raw


def chunk(code: list[int], consts: list[Any]) -> bytes:
    out = bytearray(b"\x1bLua" + bytes((0x51, 0, 1, 4, 4, 4, 8, 0)))
    out += lstr("@synthetic") + struct.pack("<ii", 0, 0) + bytes((0, 0, 2, 16))
    out += struct.pack(f"<i{len(code)}I", len(code), *code)
    out += struct.pack("<i", len(consts))
    for c in consts:
        if c is None:
            out += b"\x00"
        elif isinstance(c, bool):
            out += b"\x01" + bytes((int(c),))
        elif isinstance(c, int | float):
            out += b"\x03" + struct.pack("<d", float(c))
        else:
            out += b"\x04" + lstr(c)
    out += struct.pack("<iiii", 0, 0, 0, 0)  # protos, line info, locals, upvalues
    return bytes(out)


IDENTITY = chunk(
    [abc("NEWTABLE", 0), abc("SETTABLE", 0, K + 1, K + 2), abc("SETTABLE", 0, K + 3, K + 4),
     abx("SETGLOBAL", 0, 0), abc("RETURN", 0, 1)],
    ["jobtbl", "JT_A_NPC", 46, "JT_B_NPC", 47],
)  # fmt: skip
JOBNAME = chunk(
    [abc("NEWTABLE", 0), abx("GETGLOBAL", 1, 1), abc("GETTABLE", 2, 1, K + 2),
     abc("SETTABLE", 0, 2, K + 3), abc("GETTABLE", 2, 1, K + 4), abc("SETTABLE", 0, 2, K + 5),
     abx("SETGLOBAL", 0, 0), abx("GETGLOBAL", 3, 6), abc("CALL", 3, 1, 1),
     abc("NEWTABLE", 4), abx("LOADK", 5, 7), abc("SETLIST", 4, 1, 1), abx("SETGLOBAL", 4, 8),
     abc("RETURN", 0, 1)],
    ["JobNameTable", "jobtbl", "JT_A_NPC", "A_NPC", "JT_B_NPC", "B_SPRITE", "print", "x", "Arr"],
)  # fmt: skip


def test_lua_tables_resolve_across_chunks(lua: ModuleType) -> None:
    env: dict[str, Any] = {}
    s1 = lua.run_main(lua.parse_chunk(IDENTITY), env)
    s2 = lua.run_main(lua.parse_chunk(JOBNAME), env)
    assert s1 == {"followed": 4} and s2["CALL"] == 1
    assert env["jobtbl"].items == {"JT_A_NPC": 46, "JT_B_NPC": 47}
    assert env["JobNameTable"].items == {46: "A_NPC", 47: "B_SPRITE"}
    assert env["Arr"].items == {1: "x"}
    assert lua.plain(env["JobNameTable"]) == {"46": "A_NPC", "47": "B_SPRITE"}


def test_lua_unknown_key_is_counted_not_guessed(lua: ModuleType) -> None:
    code = [abc("NEWTABLE", 0), abx("GETGLOBAL", 1, 0), abc("GETTABLE", 2, 1, K + 1),
            abc("SETTABLE", 0, 2, K + 2), abc("RETURN", 0, 1)]  # fmt: skip
    env: dict[str, Any] = {}
    stats = lua.run_main(lua.parse_chunk(chunk(code, ["missing", "JT_X", "name"])), env)
    assert stats["SETTABLE_unresolved"] == 1


def test_lua_refuses_other_formats(lua: ModuleType) -> None:
    with pytest.raises(lua.LuaFormatError, match="not a compiled"):
        lua.parse_chunk(b"-- plain lua source\n")
    bad = bytearray(IDENTITY)
    bad[4] = 0x52
    with pytest.raises(lua.LuaFormatError, match="5.1"):
        lua.parse_chunk(bytes(bad))
    with pytest.raises(lua.LuaFormatError, match="truncated"):
        lua.parse_chunk(IDENTITY[:40])


# --- the route ---


def grid(ns: ModuleType, w: int, h: int, walls: set[tuple[int, int]]) -> Any:
    from poring_dataset.mapcache import MapGrid

    return MapGrid(
        "m", w, h, bytes(1 if (x, y) in walls else 0 for y in range(h) for x in range(w))
    )


def test_shortest_path_goes_around_a_wall(ns: ModuleType) -> None:
    g = grid(ns, 10, 10, {(4, y) for y in range(0, 8)})
    path = ns.shortest_path(g, (1, 1), {(7, 1)})
    assert path[0] == (1, 1) and path[-1] == (7, 1)
    assert all(not g.nopass(x, y) for x, y in path[1:])
    assert any(y >= 8 for _x, y in path)  # around the wall's open end
    assert ns.shortest_path(g, (1, 1), set()) is None


def test_goal_cells_for_portals_and_npcs_on_walls(ns: ModuleType) -> None:
    g = grid(ns, 10, 10, {(5, 5)})
    assert ns.goal_cells(g, (5, 5)) == {(x, y) for x in (4, 5, 6) for y in (4, 5, 6)} - {(5, 5)}
    assert ns.goal_cells(g, (2, 2), [1, 0]) == {(1, 2), (2, 2), (3, 2)}
    assert ns.goal_cells(g, (2, 2)) == {(2, 2)}


def npc(key: str, x: int, y: int, sprite: int, **kw: Any) -> dict[str, Any]:
    base = {"key": key, "x": x, "y": y, "sprite": sprite, "sprite_class": "npc", "drawn": True,
            "kind": "dialog", "dir": 4, "script": {}}  # fmt: skip
    return {**base, **kw}


def kb() -> dict[str, Any]:
    """Two maps: home h (60 x 20) and town t (60 x 20). Arrival h (2,2); the job changer at
    h (10,2); the hub at h (20,2); a portal h (40,2) -> t (2,2); the destination NPC at t (30,2);
    two same-service 'Kafras' on t: (50,2) and (8,10), the KB's pick the far one."""
    kafra_calls = {"callfunc": ["F_Set", "F_Tele"]}
    return {
        "built_at": "synthetic",
        "scope": {
            "training_grounds": {"maps": ["g"]},
            "merchant": {
                "home": "h", "hub": "h:20",
                "npcs": [{"key": "h:10", "map": "h", "cell": [10, 2], "role": "job_change"},
                         {"key": "h:20", "map": "h", "cell": [20, 2], "role": "quest"},
                         {"key": "t:30", "map": "t", "cell": [30, 2], "role": "quest"}],
                "graduation": [{"to": "h", "to_cell": [2, 2]}],
                "home_inside": [],
                "travel": {"t": {"walk_kafra": {
                    "go": [{"from": "h", "to": "t", "via": "portal", "cell": [40, 2],
                            "span": [1, 1], "to_cell": [2, 2]}],
                    "back": [{"from": "t", "to": "h", "via": "kafra", "key": "t:50",
                              "npc_cell": [50, 2], "to_cell": [3, 3]}]}}},
            },
        },
        "maps": {
            "g": {"npcs": [npc("g:1", 5, 5, 46), npc("g:2", 6, 6, 45),
                           npc("g:3", 7, 7, 111, sprite_class="hidden", drawn=False)]},
            "h": {"npcs": [npc("h:10", 10, 2, 86), npc("h:20", 20, 2, 83),
                           npc("h:far", 30, 19, 99)]},
            "t": {"npcs": [npc("t:30", 30, 2, 116), npc("t:50", 50, 2, 112, script=kafra_calls),
                           npc("t:8", 8, 10, 112, script=kafra_calls),
                           npc("t:near", 9, 16, 98), npc("t:edge", 45, 17, 97)]},
        },
    }  # fmt: skip


def test_route_walks_stops_and_takes_the_nearest_kafra(ns: ModuleType) -> None:
    doc = kb()
    stops = ns.route_stops(doc, "t")
    assert [s["do"] for s in stops][:3] == ["start", "walk", "walk"]
    grids = {"h": grid(ns, 60, 20, set()), "t": grid(ns, 60, 20, set())}
    cells, problems = ns.route_cells(stops, grids)
    assert problems == []
    assert (10, 2) in cells["h"] and (39, 2) in cells["h"] or (40, 2) in cells["h"]
    # t: (2,2) -> the destination (30,2) -> the NEAREST same-service Kafra, (8,10) is not nearer
    # than (50,2)? From (30,2): (50,2) is 20 steps, (8,10) 22 -> (50,2)
    assert (50, 2) in cells["t"] or any(abs(x - 50) <= 1 and abs(y - 2) <= 1 for x, y in cells["t"])
    uses = ns.collect(doc, cells, 45)
    assert sorted(uses) == [46, 83, 86, 98, 112, 116]  # 99 is 17 rows away from h's path
    assert all(u["scope"] == "training_grounds" for u in uses[46])
    assert 97 not in uses or uses[97][0]["route_distance"] <= ns.AREA_SIZE


def test_near_route_is_chebyshev(ns: ModuleType) -> None:
    path = {(0, 0), (1, 0)}
    assert ns.near_route({"x": 15, "y": 3}, path) == 14
    assert ns.near_route({"x": 1, "y": 15}, path) == 15
    assert ns.near_route({"x": 1, "y": 1}, set()) is None


# --- the table rows ---


def build_grf(path: Path, files: dict[str, bytes]) -> None:
    body, table = bytearray(), bytearray()
    for name, payload in files.items():
        data = zlib.compress(payload)
        aligned = (len(data) + 7) // 8 * 8
        off = len(body)
        body += data + b"\x00" * (aligned - len(data))
        raw = name.replace("/", "\\").encode("cp949")
        table += raw + b"\x00" + struct.pack("<IIIBI", len(data), aligned, len(payload), 1, off)
    z = zlib.compress(bytes(table))
    head = (
        b"Master of Magic\x00"
        + bytes(14)
        + struct.pack("<IIII", len(body), 0, len(files) + 7, 0x200)
    )
    path.write_bytes(head + body + struct.pack("<II", len(z), len(table)) + z)


def test_client_tables_and_rows(ns: ModuleType, tmp_path: Path) -> None:
    lub = "data/luafiles514/lua files/datainfo/"
    grf = tmp_path / "s.grf"
    build_grf(grf, {lub + "npcidentity.lub": IDENTITY, lub + "jobname.lub": JOBNAME,
                    "data/sprite/npc/a_npc.spr": b"SP", "data/sprite/npc/a_npc.act": b"AC",
                    "data/sprite/npc/b_sprite.spr": b"SP"})  # fmt: skip
    with grf.open("rb") as f:
        arc = ns.Archive.open(f)
        const, names, problems = ns.client_tables(arc)
        assert const == {"JT_A_NPC": 46, "JT_B_NPC": 47} and names == {46: "A_NPC", 47: "B_SPRITE"}
        assert problems == ["jobname.lub: instructions not followed {'CALL': 1}"]
        uses = [{"scope": "training_grounds"}]
        ok = ns.sprite_row(46, uses, {46: ["JT_A_NPC"]}, const, names, arc, "npc")
        assert ok["problems"] == [] and ok["client_const_agrees"] and "note" not in ok
        assert ok["files"]["spr"]["present"] and ok["files"]["act"]["flags"] == "0x01"
        odd = ns.sprite_row(47, uses, {47: ["JT_B_NPC"]}, const, names, arc, "npc")
        assert odd["note"] and odd["problems"] == [
            "data/sprite/npc/b_sprite.act: not in the archive"
        ]
        wrong = ns.sprite_row(46, uses, {46: ["JT_OTHER"]}, const, names, arc, "npc")
        assert not wrong["client_const_agrees"] and wrong["problems"]
        comp = ns.sprite_row(4001, uses, {}, const, names, arc, "player_job")
        assert comp["box"].startswith("measured extent") and "files" not in comp


def test_summary_counts(ns: ModuleType) -> None:
    table = {
        "trips": {"t": {"cells_per_map": {"h": 3}}}, "problems": [],
        "sprites": [
            {"id": 46, "scopes": ["training_grounds"], "uses": [{"scope": "training_grounds"}],
             "sprite_class": "npc", "problems": [], "client_const_agrees": True,
             "files": {"spr": {"present": True}, "act": {"present": True}}},
            {"id": 98, "scopes": ["merchant_route"], "sprite_class": "npc", "problems": ["x"],
             "uses": [{"scope": "merchant_route", "map": "t"}], "note": "differs"},
        ],
    }  # fmt: skip
    s = ns.summary(table)
    assert s["training_grounds"] == [46] and s["merchant_route"] == [98]
    assert s["merchant_route_per_map"] == {"t": [98]} and s["own_sprite_files_present"] == 1
    assert s["with_problems"] == [98] and s["name_differs_from_const"] == [98]


def test_mob_names_flag_a_client_name_that_differs(ns: ModuleType, tmp_path: Path) -> None:
    """The client draws a monster id with the sprite jobname.lub names, which need not be
    rAthena's aegis name (qa_export.Sheets looks files up by the aegis name)."""
    lub = "data/luafiles514/lua files/datainfo/"
    ident = chunk(
        [abc("NEWTABLE", 0), abc("SETTABLE", 0, K + 1, K + 2), abc("SETTABLE", 0, K + 3, K + 4),
         abx("SETGLOBAL", 0, 0), abc("RETURN", 0, 1)],
        ["jobtbl", "JT_BUG", 1051, "JT_SLIME", 1002],
    )  # fmt: skip
    names = chunk(
        [abc("NEWTABLE", 0), abx("GETGLOBAL", 1, 1), abc("GETTABLE", 2, 1, K + 2),
         abc("SETTABLE", 0, 2, K + 3), abc("GETTABLE", 2, 1, K + 4), abc("SETTABLE", 0, 2, K + 5),
         abx("SETGLOBAL", 0, 0), abc("RETURN", 0, 1)],
        ["JobNameTable", "jobtbl", "JT_BUG", "Bug_Larva", "JT_SLIME", "SLIME"],
    )  # fmt: skip
    mon = "data/sprite/몬스터/"
    grf = tmp_path / "m.grf"
    build_grf(grf, {lub + "npcidentity.lub": ident, lub + "jobname.lub": names,
                    mon + "bug_larva.spr": b"SP", mon + "bug_larva.act": b"AC",
                    mon + "slime.spr": b"SP"})  # fmt: skip
    with grf.open("rb") as f:
        res = ns.mob_names(ns.Archive.open(f), [1051, 1002, 1999], {1051: "BUG", 1002: "SLIME"})
    bug, slime, none = (res["mobs"][k] for k in ("1051", "1002", "1999"))
    assert bug == {"aegis": "BUG", "client_sprite": "Bug_Larva", "stem": "bug_larva",
                   "files_present": True, "differs_from_aegis": True}  # fmt: skip
    assert slime["files_present"] is False and slime["differs_from_aegis"] is False
    assert none["client_sprite"] is None
    assert len(res["problems"]) == 2
