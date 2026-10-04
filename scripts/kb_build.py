#!/usr/bin/env python3
"""Build the knowledge base (Phase 3 M0; ADR-0015 "The knowledge base") from rAthena, pinned ref.

    kb_build.py [--out data/kb] [--maps prt_fild08 iz_dun00 iz_dun01]

Static game data only -- monster stats and speeds, mob skills, spawn tables, warps -- for the lab's
PRE-RENEWAL server (RATHENA_PRERE=yes). rAthena is GPL-3.0: its data is fetched at the pinned ref
into /dev/shm and the derived JSON goes to data/kb/ (gitignored); NOTHING here is committed
(THIRD_PARTY.md data rule, CLAUDE.md rule 4). The ref is the one the map caches pin
(poring_dataset/mapcache.lock.json "rathena_ref").

Outputs (data/kb/):
    mobs.json      id -> stats incl. walk_speed (ms per cell), attack_delay/attack_motion/
                   damage_motion (ms), ranges, size/race/element, modes
    mob_skills.json  id -> its mob-skill lines (state, skill, rate, cast, delay, target, condition,
                   val1..val5) -- e.g. Pupa's NPC_METAMORPHOSIS into Creamy
    spawns.json    map -> spawn lines (area, species, amount, respawn delays, boss flag)
    warps.json     map -> warp lines (source cell + span -> destination map and cell)
    classes.json   the detector's species per bot map: every species spawned there, plus the
                   species they turn into (metamorphosis), with the evidence
    kb.lock.json   the ref and the sha256 + size of every input file
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "packages" / "poring_dataset" / "src" / "poring_dataset" / "mapcache.lock.json"
WORK = Path("/dev/shm/poring-lab-kb")
RAW = "https://raw.githubusercontent.com/rathena/rathena/{ref}/{path}"
MOB_DB = "db/pre-re/mob_db.yml"
MOB_SKILLS = "db/pre-re/mob_skill_db.txt"
SPAWNS = ("npc/pre-re/mobs/fields/prontera.txt", "npc/pre-re/mobs/dungeons/iz_dun.txt")
# Loaded by npc/pre-re/scripts_warps.conf (pre-renewal overrides) and npc/scripts_warps.conf
WARPS = (
    "npc/pre-re/warps/fields/prontera_fild.txt",
    "npc/pre-re/warps/cities/prontera.txt",
    "npc/pre-re/warps/cities/izlude.txt",
    "npc/warps/dungeons/iz_dun.txt",
)
DEFAULT_MAPS = ("prt_fild08", "iz_dun00", "iz_dun01")
METAMORPHOSIS = 193  # NPC_METAMORPHOSIS: val1 is the mob it turns into
MOB_FIELDS = {
    "AegisName": "aegis", "Name": "name", "Level": "level", "Hp": "hp", "WalkSpeed": "walk_speed",
    "AttackDelay": "attack_delay", "AttackMotion": "attack_motion",
    "ClientAttackMotion": "client_attack_motion", "DamageMotion": "damage_motion",
    "AttackRange": "attack_range", "SkillRange": "skill_range", "ChaseRange": "chase_range",
    "Size": "size", "Race": "race", "Element": "element", "ElementLevel": "element_level",
    "Ai": "ai", "Class": "class",
}  # fmt: skip


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(ref: str, path: str) -> bytes:
    """One pinned file, cached in /dev/shm (rule 7)."""
    dest = WORK / ref / path
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(RAW.format(ref=ref, path=path), timeout=120) as r:  # noqa: S310
            data = r.read()
        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(dest)
    return dest.read_bytes()


def parse_mob_db(text: str) -> dict[int, dict[str, Any]]:
    doc = yaml.load(text, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))  # noqa: S506
    mobs: dict[int, dict[str, Any]] = {}
    for entry in doc.get("Body") or []:
        mob = {ours: entry.get(theirs) for theirs, ours in MOB_FIELDS.items()}
        mob["modes"] = sorted(k for k, v in (entry.get("Modes") or {}).items() if v)
        mobs[int(entry["Id"])] = mob
    return mobs


def parse_mob_skills(text: str) -> dict[int, list[dict[str, Any]]]:
    """rAthena's mob_skill_db.txt: MobID,Info,State,SkillID,SkillLv,Rate,CastTime,Delay,Cancelable,
    Target,ConditionType,ConditionValue,val1,val2,val3,val4,val5,Emotion,Chat."""
    out: dict[int, list[dict[str, Any]]] = {}
    for line in text.splitlines():
        line = line.split("//", 1)[0].strip()
        if not line:
            continue
        f = [c.strip() for c in line.split(",")]
        if len(f) < 17 or not f[0].lstrip("-").isdigit():
            continue
        out.setdefault(int(f[0]), []).append({
            "info": f[1], "state": f[2], "skill": int(f[3]), "level": int(f[4]),
            "rate": int(f[5]), "cast_ms": int(f[6]), "delay_ms": int(f[7]), "target": f[9],
            "condition": f[10], "condition_value": f[11], "vals": f[12:17],
        })  # fmt: skip
    return out


def parse_spawns(text: str) -> dict[str, list[dict[str, Any]]]:
    """`map,x,y[,xs,ys]<TAB>monster|boss_monster<TAB>Name<TAB>id,amount[,delay1[,delay2[,event]]]`"""
    out: dict[str, list[dict[str, Any]]] = {}
    for line in text.splitlines():
        if line.lstrip().startswith("//"):
            continue
        cols = line.split("\t")
        if len(cols) < 4 or cols[1] not in ("monster", "boss_monster"):
            continue
        where = cols[0].split(",")
        what = cols[3].split(",")
        nums = [int(v) for v in where[1:5]] + [0] * (4 - len(where[1:5]))
        out.setdefault(where[0], []).append({
            "x": nums[0], "y": nums[1], "xs": nums[2], "ys": nums[3], "name": cols[2],
            "id": int(what[0]), "amount": int(what[1]),
            "delay1_ms": int(what[2]) if len(what) > 2 and what[2] else 0,
            "delay2_ms": int(what[3]) if len(what) > 3 and what[3] else 0,
            "boss": cols[1] == "boss_monster",
        })  # fmt: skip
    return out


def parse_warps(text: str) -> dict[str, list[dict[str, Any]]]:
    """`map,x,y,dir<TAB>warp[2]<TAB>name<TAB>spanx,spany,tomap,tox,toy`"""
    out: dict[str, list[dict[str, Any]]] = {}
    for line in text.splitlines():
        if line.lstrip().startswith("//"):
            continue
        cols = line.split("\t")
        if len(cols) < 4 or cols[1] not in ("warp", "warp2"):
            continue
        where = cols[0].split(",")
        to = cols[3].split(",")
        if len(where) < 3 or len(to) < 5:
            continue
        out.setdefault(where[0], []).append({
            "x": int(where[1]), "y": int(where[2]), "span_x": int(to[0]), "span_y": int(to[1]),
            "to_map": to[2], "to_x": int(to[3]), "to_y": int(to[4]), "name": cols[2],
        })  # fmt: skip
    return out


def classes_for(
    maps: list[str],
    spawns: dict[str, list[dict[str, Any]]],
    skills: dict[int, list[dict[str, Any]]],
    mobs: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    """Every species a bot map spawns, plus what they turn into (NPC_METAMORPHOSIS val1)."""
    out: dict[str, Any] = {}
    for m in maps:
        species: dict[int, dict[str, Any]] = {}
        for s in spawns.get(m, []):
            row = species.setdefault(s["id"], {"slots": 0, "via": "spawn"})
            row["slots"] += s["amount"]
        for mid in list(species):
            for sk in skills.get(mid, []):
                if sk["skill"] == METAMORPHOSIS and sk["vals"][0].isdigit():
                    into = int(sk["vals"][0])
                    species.setdefault(into, {"slots": 0, "via": f"metamorphosis of {mid}"})
        out[m] = {
            str(mid): {
                **row,
                "aegis": (mobs.get(mid) or {}).get("aegis"),
                "name": (mobs.get(mid) or {}).get("name"),
            }
            for mid, row in sorted(species.items(), key=lambda kv: -kv[1]["slots"])
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "kb")
    ap.add_argument("--maps", nargs="+", default=list(DEFAULT_MAPS))
    a = ap.parse_args()
    ref = json.loads(LOCK.read_text())["rathena_ref"]
    raw = {p: fetch(ref, p) for p in (MOB_DB, MOB_SKILLS, *SPAWNS, *WARPS)}
    mobs = parse_mob_db(raw[MOB_DB].decode())
    skills = parse_mob_skills(raw[MOB_SKILLS].decode(errors="replace"))
    spawns: dict[str, list[dict[str, Any]]] = {}
    for p in SPAWNS:
        for k, v in parse_spawns(raw[p].decode(errors="replace")).items():
            spawns.setdefault(k, []).extend(v)
    warps: dict[str, list[dict[str, Any]]] = {}
    for p in WARPS:
        for k, v in parse_warps(raw[p].decode(errors="replace")).items():
            warps.setdefault(k, []).extend(v)
    a.out.mkdir(parents=True, exist_ok=True)
    outputs = {
        "mobs.json": {str(k): v for k, v in sorted(mobs.items())},
        "mob_skills.json": {str(k): v for k, v in sorted(skills.items())},
        "spawns.json": spawns,
        "warps.json": warps,
        "classes.json": classes_for(a.maps, spawns, skills, mobs),
        "kb.lock.json": {
            "rathena_ref": ref, "mode": "pre-re",
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "inputs": {p: {"sha256": sha256(b), "bytes": len(b)} for p, b in raw.items()},
        },
    }  # fmt: skip
    for name, doc in outputs.items():
        tmp = a.out / f".{name}.part"
        tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
        tmp.replace(a.out / name)
        json.loads((a.out / name).read_text())  # read back
    summary = {"out": str(a.out), "mobs": len(mobs), "mob_skill_mobs": len(skills),
               "spawn_maps": len(spawns), "warp_maps": len(warps),
               "classes": outputs["classes.json"]}  # fmt: skip
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
