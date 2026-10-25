"""scripts/kb_build.py: the KB parsers (Phase 3 M0). Inline fixtures in rAthena's formats -- no
rAthena data is committed (GPL; generated locally)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[3]


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("kb_build", ROOT / "scripts" / "kb_build.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["kb_build"] = mod
    spec.loader.exec_module(mod)
    return mod


kb = load()

MOB_DB = """Header:
  Type: MOB_DB
  Version: 4
Body:
  - Id: 1008
    AegisName: PUPA
    Name: Pupa
    Level: 2
    Hp: 427
    WalkSpeed: 1000
    AttackDelay: 1001
    AttackMotion: 1
    DamageMotion: 1
    Ai: 01
    Modes:
      Detector: true
  - Id: 1018
    AegisName: CREAMY
    Name: Creamy
    WalkSpeed: 150
"""
SKILLS = """// MobID,Dummy value (info only),State,SkillID,SkillLv,Rate,CastTime,Delay,...
1008,Pupa@NPC_EMOTION,idle,197,1,2000,0,5000,yes,self,always,0,19,,,,,,
1008,Pupa@NPC_METAMORPHOSIS,idle,193,1,10,2000,5000,no,self,always,0,1018,,,,,,
"""
SPAWNS = """//==== a comment
prt_fild08,0,0\tmonster\tPupa\t1008,20,5000
prt_fild08,305,233,10,10\tmonster\tPupa\t1008,2,15000,0
iz_dun00,0,0\tboss_monster\tSomething\t1999,1,3600000,600000
"""
WARPS = """prt_fild08,170,378,0\twarp\tprtf08_prt\t3,2,prontera,156,22
prt_fild08,371,212,0\twarp2\tprtf08_iz\t3,3,izlude,30,78
//prt_fild08,1,1,0\twarp\told\t1,1,nowhere,1,1
"""


def test_mob_db_keeps_speeds_motions_and_modes() -> None:
    mobs = kb.parse_mob_db(MOB_DB)
    assert mobs[1008]["aegis"] == "PUPA"
    assert mobs[1008]["walk_speed"] == 1000
    assert mobs[1008]["attack_motion"] == 1
    assert mobs[1008]["modes"] == ["Detector"]
    assert mobs[1018]["level"] is None  # absent fields stay None (the server's default applies)


def test_mob_skills_and_the_metamorphosis_that_explains_creamy() -> None:
    skills = kb.parse_mob_skills(SKILLS)
    meta = [s for s in skills[1008] if s["skill"] == kb.METAMORPHOSIS]
    assert meta and meta[0]["vals"][0] == "1018" and meta[0]["cast_ms"] == 2000


def test_spawns_areas_amounts_and_boss_flag() -> None:
    spawns = kb.parse_spawns(SPAWNS)
    assert [s["amount"] for s in spawns["prt_fild08"]] == [20, 2]
    assert spawns["prt_fild08"][1]["xs"] == 10 and spawns["prt_fild08"][0]["delay1_ms"] == 5000
    assert spawns["iz_dun00"][0]["boss"] is True


def test_warps_skip_comments_and_read_the_span() -> None:
    warps = kb.parse_warps(WARPS)["prt_fild08"]
    assert [(w["x"], w["y"], w["span_x"], w["span_y"], w["to_map"]) for w in warps] == [
        (170, 378, 3, 2, "prontera"),
        (371, 212, 3, 3, "izlude"),
    ]


def test_classes_include_the_slaves_a_spawn_summons() -> None:
    """gef_fild10's Orc Lord calls Orc Archers (NPC_SUMMONSLAVE, val1): they stand on the map
    beside it, so the detector's species list holds them; a slave that also spawns keeps its
    spawn row (an Orc Baby's Orc Warrior)."""
    skills = kb.parse_mob_skills(
        "1190,Orc Lord@NPC_SUMMONSLAVE,idle,196,5,10000,0,0,yes,self,onspawn,0,1189,,,,,,\n"
        "1686,Orc Baby@NPC_SUMMONSLAVE,idle,196,2,10000,0,0,yes,self,slavele,0,1023,1273,,,,,\n"
    )
    spawns = kb.parse_spawns(
        "gef_fild10,0,0,0,0\tboss_monster\tOrc Lord\t1190,1,7200000,600000,0\n"
        "gef_fild10,0,0\tmonster\tOrc Baby\t1686,5\n"
        "gef_fild10,0,0\tmonster\tOrc Warrior\t1023,20\n"
    )
    classes = kb.classes_for(["gef_fild10"], spawns, skills, {})["gef_fild10"]
    assert classes["1189"]["via"] == "slave of 1190" and classes["1189"]["slots"] == 0
    assert classes["1273"]["via"] == "slave of 1686"
    assert classes["1023"] == {"slots": 20, "via": "spawn", "aegis": None, "name": None}
    assert list(classes)[:3] == ["1023", "1686", "1190"]  # by spawn slots


def test_the_hunt_maps_sources_are_listed_once_with_the_pre_renewal_overrides() -> None:
    """A rebuild keeps every hunt map's spawns and warps (orcsdun01 since 10-21, pay_fild07, and
    gef_fild10 since 2026-10-25: gef10-prep.md). Spawn files are the pre-renewal overrides
    (npc/pre-re/scripts_monsters.conf); a warp file is the npc/pre-re/ copy where one exists."""
    assert "npc/pre-re/mobs/fields/geffen.txt" in kb.SPAWNS
    assert "npc/pre-re/warps/fields/geffen_fild.txt" in kb.WARPS
    assert "npc/pre-re/mobs/fields/payon.txt" in kb.SPAWNS
    assert "npc/pre-re/warps/fields/payon_fild.txt" in kb.WARPS
    assert "npc/pre-re/mobs/dungeons/orcsdun.txt" in kb.SPAWNS
    assert "npc/warps/dungeons/orcsdun.txt" in kb.WARPS
    assert all(p.startswith("npc/pre-re/mobs/") for p in kb.SPAWNS)
    assert len(set(kb.SPAWNS)) == len(kb.SPAWNS) and len(set(kb.WARPS)) == len(kb.WARPS)
    assert not any(p.startswith("npc/re/") for p in (*kb.SPAWNS, *kb.WARPS))  # never Renewal's


def test_classes_include_what_a_spawn_turns_into() -> None:
    mobs = kb.parse_mob_db(MOB_DB)
    classes = kb.classes_for(
        ["prt_fild08"], kb.parse_spawns(SPAWNS), kb.parse_mob_skills(SKILLS), mobs
    )["prt_fild08"]
    assert classes["1008"]["slots"] == 22 and classes["1008"]["via"] == "spawn"
    assert classes["1018"] == {
        "slots": 0, "via": "metamorphosis of 1008", "aegis": "CREAMY", "name": "Creamy",
    }  # fmt: skip


# --- 2026-10-08 (loot@1 P4): items, drops and the server's drop config. Synthetic entries in the
# rAthena formats (no rAthena data committed).
ITEMS_ETC = """Header:
  Type: ITEM_DB
  Version: 3
Body:
  - Id: 9101
    AegisName: Test_Goo
    Name: Test Goo
    Type: Etc
    Weight: 10
  - Id: 9102
    AegisName: Test_Feather
    Name: Test Feather
    Weight: 3
  - Id: 9103
    AegisName: Test_Token
    Name: Test Token
"""
ITEMS_EQUIP = """Header:
  Type: ITEM_DB
  Version: 3
Body:
  - Id: 9201
    AegisName: Test_Blade
    Name: Test Blade
    Type: Weapon
    Weight: 400
"""
MOB_WITH_DROPS = """Header:
  Type: MOB_DB
  Version: 4
Body:
  - Id: 9001
    AegisName: TEST_BLOB
    Name: Test Blob
    Drops:
      - Item: Test_Goo
        Rate: 7000
      - Item: Test_Blade
        Rate: 100
        StealProtected: true
      - Item: Not_In_Item_Db
        Rate: 5
    MvpDrops:
      - Item: Test_Feather
        Rate: 50
  - Id: 9002
    AegisName: TEST_NODROP
    Name: Test Nodrop
"""
DROPS_CONF = """// a comment
flooritem_lifetime: 60000
item_first_get_time: 3000
item_auto_get: no
item_rate_common: 100
item_drop_common_min: 1
item_drop_common_max: 10000
item_rate_equip: 100
item_logarithmic_drops: no
drops_by_luk: 0
unrelated_setting: 7
"""


def test_item_db_weights_are_rathena_units_ten_per_shown_weight() -> None:
    items = kb.parse_item_db(ITEMS_ETC)
    items.update(kb.parse_item_db(ITEMS_EQUIP))
    assert items[9101]["weight"] == 10 and items[9101]["weight_shown"] == 1.0
    assert items[9102]["weight_shown"] == 0.3  # lighter than one shown unit
    assert items[9102]["type"] == "Etc"  # the format's default type
    assert items[9103]["weight"] == 0  # the format's default weight
    assert items[9201]["type"].lower() == "weapon" and items[9201]["weight_shown"] == 40.0


def test_battle_conf_last_write_wins_and_names_its_file() -> None:
    override = "flooritem_lifetime: 30000 // the lab would override here\n"
    server = kb.server_drop_config(
        [("conf/battle/drops.conf", DROPS_CONF), ("conf/import/battle_conf.txt", override)]
    )
    assert server["flooritem_lifetime"] == {"value": 30000, "source": "conf/import/battle_conf.txt"}
    assert server["item_first_get_time"]["value"] == 3000
    assert server["item_auto_get"]["value"] is False
    assert "unrelated_setting" not in server
    assert kb.rate_adjustment_reason(server) is None


def test_drops_join_items_by_aegis_and_keep_rates_on_a_default_server() -> None:
    items = {**kb.parse_item_db(ITEMS_ETC), **kb.parse_item_db(ITEMS_EQUIP)}
    server = kb.server_drop_config([("conf/battle/drops.conf", DROPS_CONF)])
    drops = kb.parse_drops(MOB_WITH_DROPS, items, server)
    assert 9002 not in drops  # a species without drops has no row
    rows = {d["aegis"]: d for d in drops[9001]}
    assert rows["Test_Goo"]["item_id"] == 9101 and rows["Test_Goo"]["rate"] == 7000
    assert rows["Test_Goo"]["rate_effective"] == 7000 and rows["Test_Goo"]["weight"] == 10
    assert rows["Test_Blade"]["rate_class"] == "equip" and rows["Test_Blade"]["steal_protected"]
    assert rows["Not_In_Item_Db"]["item_id"] is None  # reported, never guessed
    assert rows["Test_Feather"]["mvp"] is True
    lines = kb.drop_table(9001, drops, items)
    assert len(lines) == 4 and "70.00 %" in lines[0] and "(1 shown)" in lines[0]


def test_an_adjusting_battle_config_leaves_the_effective_rate_unknown() -> None:
    items = kb.parse_item_db(ITEMS_ETC)
    for conf, reason in (
        ("item_rate_common: 300\n", "item_rate_common = 300"),
        ("item_drop_common_min: 50\n", "item_drop_common_min = 50"),
        ("item_logarithmic_drops: yes\n", "item_logarithmic_drops on"),
        ("drops_by_luk: 100\n", "drops_by_luk = 100"),
    ):
        server = kb.server_drop_config([("a.conf", DROPS_CONF), ("b.conf", conf)])
        assert kb.rate_adjustment_reason(server) == reason
        row = kb.parse_drops(MOB_WITH_DROPS, items, server)[9001][0]
        assert row["rate_effective"] is None and row["rate_note"] == reason and row["rate"] == 7000


def test_pupa_turns_into_creamy_on_prt_fild08_and_the_species_lint_sees_it(tmp_path: Path) -> None:
    """Batt 2026-10-22 (decision 6: "Add metamorphosis (turns_into) to the KB so the species lint
    sees it"). The chain end to end, on this file's inline fixtures (rAthena's formats, no rAthena
    data): kb_build's parsers -> the KB files as kb_build writes them -> poring_flow.kbsheet's
    world (Mob.turns_into) -> lint/hunt.py's melee_ring_species. A melee-ring hunt on prt_fild08
    whose only TARGET is Pupa (1008) is refused for Creamy (1018), which is spawned nowhere: it
    reaches the lint only through the metamorphosis. Without mob_skills.json (the KB before this
    fix read it) the lint saw the spawn lines only and passed."""
    import json

    from poring_flow import kbsheet, pyview
    from poring_flow.lint import lint

    assert kbsheet.METAMORPHOSIS == kb.METAMORPHOSIS  # one skill id on both sides
    root = tmp_path / "kb"
    (root / "bindings").mkdir(parents=True)
    (root / "bindings" / "lab-rathena.json").write_text("{}")
    spawns = {m: rows for m, rows in kb.parse_spawns(SPAWNS).items() if m == "prt_fild08"}
    outputs = {
        "spawns.json": spawns,
        "mobs.json": {str(k): v for k, v in kb.parse_mob_db(MOB_DB).items()},
        "mob_skills.json": {str(k): v for k, v in kb.parse_mob_skills(SKILLS).items()},
    }
    for name, doc in outputs.items():
        (root / name).write_text(json.dumps(doc))
    world, labels = kbsheet.load_local_world("lab-rathena", ["prt_fild08"], root)
    assert world.sheets["prt_fild08"].spawned() == [1008]  # Creamy has no spawn line here
    assert world.mobs[1008].turns_into == [1018] and 1018 in world.mobs
    flow = pyview.parse(
        'flow(ir=2, name="t", max_runtime_s=600, start=entry("field", "south"), '
        'target=target(client="kro-20211103-prere", server="lab-rathena", locale="en", '
        "path=RDP))\n\n\n"
        '@map_block(map_id("prt_fild08"), entries=[entry_at("south", cell("prt_fild08", 20, 20))],'
        " targets=[mob(1008)])\n"
        "def field():\n"
        '    hunt(strike="arm_c@32", engage_on_the_way="on_the_way@19", '
        'engage_source="melee_ring", dead="exp_line@48", loot="gm_fast_scan@54", '
        'search="heading_coverage@22")\n'
    )
    found = [f.message for f in lint(flow, world=world) if f.rule == "melee_ring_species"]
    assert found == [
        "maps.field.0: hunt's engage_source melee_ring strikes EVERY monster in melee range, and "
        "mob 1018 can be on prt_fild08 without being a TARGET of field: refused on a map with a "
        "non-target species"
    ]
    (root / "mob_skills.json").unlink()  # the KB as kbsheet read it before: spawn lines only
    world, labels = kbsheet.load_local_world("lab-rathena", ["prt_fild08"], root)
    assert world.mobs[1008].turns_into == [] and 1018 not in world.mobs
    assert [f for f in lint(flow, world=world) if f.rule == "melee_ring_species"] == []
    assert any("spawn lines only" in n for n in labels.notes)
