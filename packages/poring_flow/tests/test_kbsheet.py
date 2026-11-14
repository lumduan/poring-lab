"""MW2-0 at run time (poring_flow.kbsheet): map sheets built in memory from the local KB. SYNTHETIC
files only: a made-up bindings file, spawns, mobs and a GAT built byte by byte here."""

from __future__ import annotations

import json
import struct
from pathlib import Path

from poring_flow import editor
from poring_flow.kbsheet import (
    known_maps,
    load_local_world,
    metamorphoses,
    npc_key,
    option_key,
    read_gat,
)
from poring_flow.lint import lint
from poring_flow.trace import Scenario, simulate


def gat(path: Path, rows: list[str]) -> None:
    """A GAT: header, then one 20-byte tile per cell (type 1 = wall, 0 = walkable)."""
    h, w = len(rows), len(rows[0])
    out = bytearray(struct.pack("<4sBBII", b"GRAT", 1, 2, w, h))
    for y in range(h):
        for x in range(w):
            out += struct.pack("<4fHH", 0, 0, 0, 0, 1 if rows[y][x] == "#" else 0, 0)
    path.write_bytes(bytes(out))


def kb(tmp: Path, gat_dir: Path | None) -> Path:
    root = tmp / "kb"
    (root / "bindings").mkdir(parents=True)
    l3 = {
        "map": {"walkability": {"gat_dir": str(gat_dir) if gat_dir else None}},
        "warp": {"cells": {"by_map": {"m_town": [
            {"x": 18, "y": 2, "span_x": 1, "span_y": 0, "to_map": "m_field", "to_x": 5, "to_y": 5,
             "name": "w1"}]}}},
        "npc": {
            "positions": {"npcs": [{"name": "Guide#t", "map": "m_town", "x": 3, "y": 8}]},
            "kafra": {"npcs": [{"name": "Kafra::t", "map": "m_town", "x": 10, "y": 8}]},
            "menus": {"by_npc": {"Guide#t": [{"call": "select", "options": ["Go.", "Stay."]}]}},
        },
    }  # fmt: skip
    (root / "bindings" / "srv.json").write_text(json.dumps(l3))
    (root / "spawns.json").write_text(json.dumps({"m_field": [{"id": 9301, "amount": 7}]}))
    mob = {"name": "made-up", "level": 4, "modes": ["Aggressive"], "class": None}
    (root / "mobs.json").write_text(json.dumps({"9301": mob}))
    return root


TOWN = ["....................", "....................", "....................",
        "....######..........", "....######..........", "....................",
        "....................", "....................", "....................",
        "...................."]  # fmt: skip


def test_sheets_come_from_the_kb_with_one_way_keys(tmp_path: Path) -> None:
    gd = tmp_path / "gat"
    gd.mkdir()
    gat(gd / "m_town.gat", TOWN)
    world, labels = load_local_world("srv", ["m_town", "m_field", "m_none"], kb(tmp_path, gd))
    assert sorted(world.sheets) == ["m_field", "m_town"]  # an unknown map is left out (fail closed)
    town = world.sheets["m_town"]
    assert town.walk is not None and town.walk.rows[3] == "....######.........."
    assert [(w.x, w.y, w.to_map) for w in town.warps] == [(18, 2, "m_field")]
    guide = town.npc(npc_key("m_town", "Guide#t"))
    assert guide is not None and guide.menu == [
        option_key("Guide#t", "Go."),
        option_key("Guide#t", "Stay."),
    ]
    assert labels.npcs[guide.key] == "Guide#t" and labels.options[guide.menu[0]] == "Go."
    assert guide.key.startswith("n_") and len(guide.key) == 10 and "Guide" not in guide.key
    kafra = town.npc(npc_key("m_town", "Kafra::t"))
    assert kafra is not None and kafra.kafra is not None and kafra.kafra.services == []
    assert town.flags is None  # not extracted: the linter fails closed
    field = world.sheets["m_field"]
    assert field.walk is None and [s.mob for s in field.spawns] == [9301]
    assert world.mobs[9301].aggressive and world.mobs[9301].level == 4


def test_without_the_gat_routes_are_estimates_and_the_linter_says_so(tmp_path: Path) -> None:
    world, labels = load_local_world("srv", ["m_town"], kb(tmp_path, tmp_path / "missing"))
    assert world.sheets["m_town"].walk is None
    assert any("not readable here" in n for n in labels.notes)
    findings = lint(editor.sample_flow(), world=world)
    assert any(f.rule == "map_sheet" for f in findings)  # town_1 / field_1 are not in this KB


def test_a_generated_sheet_file_wins(tmp_path: Path) -> None:
    root = kb(tmp_path, None)
    (root / "maps" / "srv").mkdir(parents=True)
    (root / "maps" / "srv" / "m_town.json").write_text(json.dumps({"map": "m_town", "town": True}))
    world, _ = load_local_world("srv", ["m_town"], root)
    assert world.sheets["m_town"].town and world.sheets["m_town"].warps == []


def test_no_bindings_no_sheets(tmp_path: Path) -> None:
    world, labels = load_local_world("other", ["m_town"], kb(tmp_path, None))
    assert world.sheets == {} and labels.notes


def test_bad_gat_files_are_refused(tmp_path: Path) -> None:
    p = tmp_path / "x.gat"
    p.write_bytes(b"NOPE" + bytes(20))
    assert read_gat(p) is None
    p.write_bytes(struct.pack("<4sBBII", b"GRAT", 1, 2, 5000, 5000))
    assert read_gat(p) is None  # too large a side
    p.write_bytes(struct.pack("<4sBBII", b"GRAT", 1, 2, 4, 4) + bytes(10))
    assert read_gat(p) is None  # truncated
    assert read_gat(tmp_path / "absent.gat") is None


def test_a_walk_on_kb_sheets_follows_the_gat(tmp_path: Path) -> None:
    gd = tmp_path / "gat"
    gd.mkdir()
    gat(gd / "m_town.gat", TOWN)
    world, _ = load_local_world("srv", ["m_town"], kb(tmp_path, gd))
    from poring_flow import pyview

    flow = pyview.parse(
        'flow(ir=2, name="t", max_runtime_s=60, target=target(client="c", server="srv", '
        'locale="en", path=S2))\n\nwalk_to(cell("m_town", 2, 4))\nwalk_to(cell("m_town", 12, 4))\n'
    )
    t = simulate(flow, world, Scenario(horizon_s=30))
    seg = next(p for p in t["paths"] if p["node"] == "main.1")
    assert not seg["estimated"]
    assert all(world.sheets["m_town"].walk.walkable((x, y)) for x, y in seg["cells"])  # type: ignore[union-attr]


def test_ids_that_could_leave_the_kb_directory_are_refused(tmp_path: Path) -> None:
    root = kb(tmp_path, None)
    (root / "maps").mkdir()
    for server in ("..", ".", "a/b", "../x"):
        world, labels = load_local_world(server, ["m_town"], root)
        assert world.sheets == {} and labels.notes, server
    world, labels = load_local_world("srv", ["..", "spawns", "m_town"], root)
    assert sorted(world.sheets) == ["m_town"]  # "spawns" is no map of the KB; ".." is refused
    assert any("cannot name local data" in n for n in labels.notes)
    (root / "maps" / "srv").mkdir()
    (root / "maps" / "srv" / "m_town.json").write_text('{"map": 1}')
    world, labels = load_local_world("srv", ["m_town"], root)
    assert any("invalid" in n for n in labels.notes)


def skill(mob: int, skill_id: int, *vals: str) -> dict[str, object]:
    """One mob-skill line as kb_build writes mob_skills.json (val1..val5 as strings)."""
    return {"skill": skill_id, "state": "idle", "vals": [*vals, *[""] * (5 - len(vals))]}


def test_metamorphosis_reaches_the_mobs_turns_into(tmp_path: Path) -> None:
    """Batt 2026-10-22 (decision 6): the KB's NPC_METAMORPHOSIS lines fill Mob.turns_into, every
    value of a line, transitively: the made-up 9301 turns into 9302, which turns into 9303 or 9304;
    each gets its Mob (it is not spawned anywhere) and the chain is complete."""
    root = kb(tmp_path, None)
    mobs = {str(i): {"name": f"made-up {i}", "level": i - 9290} for i in (9301, 9302, 9303, 9304)}
    (root / "mobs.json").write_text(json.dumps(mobs))
    skills = {
        "9301": [skill(9301, 197, "19"), skill(9301, 193, "9302")],  # an emotion, then the change
        "9302": [skill(9302, 193, "9303", "9304", "0")],  # two candidates; a 0 is no mob
        "9303": [skill(9303, 193)],  # a metamorphosis line naming nothing
    }
    (root / "mob_skills.json").write_text(json.dumps(skills))
    world, labels = load_local_world("srv", ["m_field"], root)
    assert sorted(world.mobs) == [9301, 9302, 9303, 9304]
    assert world.mobs[9301].turns_into == [9302]
    assert world.mobs[9302].turns_into == [9303, 9304]
    assert world.mobs[9303].turns_into == [] and world.mobs[9304].turns_into == []
    assert world.mobs[9302].level == 12 and not any("mob_skills" in n for n in labels.notes)
    assert metamorphoses(skills) == {9301: (9302,), 9302: (9303, 9304)}
    assert metamorphoses({"x": [], "9": "no", "8": [3, {"skill": 193, "vals": None}]}) == {}


def test_without_the_skill_file_the_species_are_the_spawn_lines_and_a_note_says_so(
    tmp_path: Path,
) -> None:
    world, labels = load_local_world("srv", ["m_field"], kb(tmp_path, None))
    assert sorted(world.mobs) == [9301] and world.mobs[9301].turns_into == []
    assert any("mob_skills.json" in n and "spawn lines only" in n for n in labels.notes)


def test_the_map_pickers_list_every_map_the_kb_names_with_its_kafra(tmp_path: Path) -> None:
    """Round 21 (live-blocks.md 12.5): the names come from the local KB at run time (synthetic
    here): the warps' both ends, the NPCs' and the Kafras' maps, the spawn lines', the sheets'."""
    root = kb(tmp_path, None)
    (root / "maps" / "srv").mkdir(parents=True)
    (root / "maps" / "srv" / "m_sheet.json").write_text(json.dumps({"map": "m_sheet"}))
    (root / "maps" / "srv" / "_server.json").write_text("{}")
    maps, notes = known_maps("srv", root)
    assert maps == [
        {"id": "m_field", "kafra": False},
        {"id": "m_sheet", "kafra": False},
        {"id": "m_town", "kafra": True},
    ]
    assert notes == []
    # nothing written: the KB directory holds what it held
    held = sorted(p.name for p in (root / "maps" / "srv").iterdir())
    assert held == ["_server.json", "m_sheet.json"]


def test_the_map_list_refuses_ids_that_could_leave_the_kb_and_says_what_is_missing(
    tmp_path: Path,
) -> None:
    root = kb(tmp_path, None)
    for server in ("..", "a/b", ""):
        maps, notes = known_maps(server, root)
        assert maps == [] and notes, server
    maps, notes = known_maps("other", root)  # no bindings for it: only the spawn lines' maps
    assert maps == [{"id": "m_field", "kafra": False}]
    assert any("no L3 bindings" in n for n in notes)
    empty = tmp_path / "empty"
    empty.mkdir()
    maps, notes = known_maps("srv", empty)
    assert maps == [] and any("names no maps" in n for n in notes)


def test_the_sample_maps_are_the_synthetic_sheets() -> None:
    assert editor.sample_maps() == [
        {"id": "field_1", "kafra": False},
        {"id": "town_1", "kafra": True},
    ]
