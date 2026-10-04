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
