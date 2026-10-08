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
