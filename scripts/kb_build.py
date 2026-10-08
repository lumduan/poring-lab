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
    items.json     id -> aegis, name, type, weight (rAthena units: 10 = 1 shown weight) and
                   weight_shown (2026-10-08, loot@1 P4: what a pickup adds to the weight readout)
    drops.json     mob id -> its normal and MVP drops: item id + aegis, rate per 10000 as in
                   mob_db, and the EFFECTIVE rate on the lab server (None + why when the server's
                   battle config would adjust it in ways this file does not model)
    server.json    the lab server's drop config from its pinned battle conf (drops.conf, then the
                   import override, last write wins): flooritem_lifetime (ms), the loot-priority
                   times, the item_rate_* multipliers and clamps -- each with the file it came from
    kb.lock.json   the ref and the sha256 + size of every input file

    kb_build.py --show-drops 1002 [...]   also print those species' drop tables (loot@1 P4:
                                         reported, never committed)
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
# 2026-10-08 (loot@1 P4). db/item_db.yml imports db/pre-re/item_db.yml in a pre-renewal build,
# which imports these three; the lab adds no db/import item overrides (services/rathena).
ITEM_DBS = (
    "db/pre-re/item_db_usable.yml",
    "db/pre-re/item_db_equip.yml",
    "db/pre-re/item_db_etc.yml",
)
# conf/battle_athena.conf imports conf/battle/battle.conf, ..., conf/battle/drops.conf, ..., then
# conf/import/battle_conf.txt last (the lab's is the empty template: `make import`, no override in
# services/rathena/conf/import).
BATTLE_CONFS = (
    "conf/battle/battle.conf", "conf/battle/drops.conf", "conf/import-tmpl/battle_conf.txt",
)  # fmt: skip
# delay_battle_damage: a kill's drops fall 500 ms after the death when it is OFF, at once when ON
# (mob.cpp:3428); the first falls ON the death cell, then SE, W, N, SE, ... (mob.cpp:2531-2551).
DROP_KEYS = (
    "delay_battle_damage",
    "flooritem_lifetime", "item_auto_get", "item_first_get_time", "item_second_get_time",
    "item_third_get_time", "item_logarithmic_drops", "drops_by_luk", "drops_by_luk2",
    "drop_rate0item", "drop_rateincrease", "first_attack_loot_bonus",
)  # fmt: skip
# rAthena item types (db "Type", matched lower-cased) -> the drop-rate class of
# conf/battle/drops.conf. Healing items are "heal", other consumables "use", wearables "equip",
# cards "card", everything else "common". (Lower-case keys: one capitalised type name is also a
# client UI string, which the locale-pack guard refuses as a literal.)
RATE_CLASS = {
    "healing": "heal", "usable": "use", "delayconsume": "use", "cash": "use",
    "weapon": "equip", "armor": "equip", "petarmor": "equip", "shadowgear": "equip",
    "card": "card",
}  # fmt: skip
ITEM_FIELDS = {"AegisName": "aegis", "Name": "name", "Type": "type", "SubType": "subtype",
               "Weight": "weight", "Buy": "buy", "Sell": "sell", "Slots": "slots"}  # fmt: skip
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


def parse_item_db(text: str) -> dict[int, dict[str, Any]]:
    """One rAthena item_db YAML file -> id -> the fields we keep. `weight` is rAthena's unit (10 =
    1 shown weight, "Each 10 is 1 weight" in the file's own header); `weight_shown` = weight / 10,
    what the client's weight readout counts in. Absent fields take the file format's defaults
    (Type Etc, Weight 0)."""
    doc = yaml.load(text, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))  # noqa: S506
    items: dict[int, dict[str, Any]] = {}
    for entry in (doc or {}).get("Body") or []:
        item = {ours: entry.get(theirs) for theirs, ours in ITEM_FIELDS.items()}
        item["type"] = item["type"] or "Etc"
        item["weight"] = int(item["weight"] or 0)
        item["weight_shown"] = item["weight"] / 10
        items[int(entry["Id"])] = item
    return items


def parse_battle_conf(text: str) -> dict[str, str]:
    """`key: value` lines of a rAthena battle conf, comments (//) and blank lines skipped."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.split("//", 1)[0].strip()
        key, sep, value = line.partition(":")
        if sep and key.strip() and " " not in key.strip():
            out[key.strip()] = value.strip()
    return out


def _conf_value(value: str) -> int | bool | str:
    low = value.lower()
    if low in ("yes", "on", "true"):
        return True
    if low in ("no", "off", "false"):
        return False
    try:
        return int(value, 0)
    except ValueError:
        return value


def server_drop_config(confs: list[tuple[str, str]]) -> dict[str, Any]:
    """The drop / floor-item settings from the battle conf files IN LOAD ORDER (later wins), each
    with the file it came from. The item_rate_* multipliers and clamps are kept too."""
    merged: dict[str, tuple[str, str]] = {}
    for path, text in confs:
        for key, value in parse_battle_conf(text).items():
            merged[key] = (value, path)
    keep = [k for k in merged if k in DROP_KEYS or k.startswith(("item_rate_", "item_drop_"))]
    return {k: {"value": _conf_value(merged[k][0]), "source": merged[k][1]} for k in sorted(keep)}


def rate_adjustment_reason(server: dict[str, Any]) -> str | None:
    """None when the server's battle config leaves mob_db's drop rates unchanged (every
    item_rate_* 100, clamps [<= 1, >= 10000], no logarithmic or LUK-based drops, no +0.01 %);
    otherwise why the effective rate is not computed here."""

    def val(key: str, default: Any) -> Any:
        return server.get(key, {}).get("value", default)

    for key, entry in server.items():
        v = entry["value"]
        clamp = key.startswith("item_drop_") and isinstance(v, int)
        if key.startswith("item_rate_") and v != 100:
            return f"{key} = {v}"
        if clamp and key.endswith("_min") and v > 1:
            return f"{key} = {v}"
        if clamp and key.endswith("_max") and v < 10000:
            return f"{key} = {v}"
    for key in ("item_logarithmic_drops", "drop_rateincrease"):
        if val(key, False):
            return f"{key} on"
    for key in ("drops_by_luk", "drops_by_luk2"):
        if val(key, 0):
            return f"{key} = {val(key, 0)}"
    return None


def parse_drops(
    mob_text: str, items: dict[int, dict[str, Any]], server: dict[str, Any]
) -> dict[int, list[dict[str, Any]]]:
    """mob_db's Drops / MvpDrops (rate per 10000), joined with the item ids by AegisName.
    `rate_effective` is the rate on this server when its battle config leaves rates unchanged
    (rate_adjustment_reason), else None with the reason in `rate_note`. An Aegis name the item
    files do not know keeps item_id None (reported, never guessed)."""
    doc = yaml.load(mob_text, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))  # noqa: S506
    by_aegis = {str(v["aegis"]): k for k, v in items.items() if v.get("aegis")}
    reason = rate_adjustment_reason(server)
    out: dict[int, list[dict[str, Any]]] = {}
    for entry in (doc or {}).get("Body") or []:
        rows: list[dict[str, Any]] = []
        for key, mvp in (("Drops", False), ("MvpDrops", True)):
            for d in entry.get(key) or []:
                aegis = str(d.get("Item"))
                item_id = by_aegis.get(aegis)
                item = items.get(item_id) if item_id is not None else None
                rate = int(d.get("Rate", 0))
                rows.append({
                    "item_id": item_id, "aegis": aegis, "rate": rate,
                    "rate_effective": None if reason else rate,
                    "rate_note": reason or "battle config leaves mob_db rates unchanged",
                    "rate_class": (RATE_CLASS.get(str(item["type"]).lower(), "common")
                                   if item else None),
                    "weight": item["weight"] if item else None,
                    "steal_protected": bool(d.get("StealProtected", False)), "mvp": mvp,
                })  # fmt: skip
        if rows:
            out[int(entry["Id"])] = rows
    return out


def drop_table(
    mob_id: int, drops: dict[int, list[dict[str, Any]]], items: dict[int, dict[str, Any]]
) -> list[str]:
    """Human lines for one species' drops (loot@1 P4: reported, never committed)."""
    lines = []
    for d in drops.get(mob_id, []):
        item = items.get(d["item_id"]) if d["item_id"] is not None else None
        name = item["name"] if item else "?"
        rate = d["rate_effective"] if d["rate_effective"] is not None else d["rate"]
        lines.append(
            f"  {d['item_id']!s:>6} {d['aegis']:<24} {name:<24} {rate / 100:6.2f} %"
            f"  weight {d['weight']!s:>5} ({(d['weight'] or 0) / 10:g} shown)"
            + ("  MVP" if d["mvp"] else "")
        )
    return lines


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
    ap.add_argument("--show-drops", nargs="*", type=int, default=[], metavar="MOB_ID")
    a = ap.parse_args()
    ref = json.loads(LOCK.read_text())["rathena_ref"]
    raw = {p: fetch(ref, p) for p in (MOB_DB, MOB_SKILLS, *SPAWNS, *WARPS, *ITEM_DBS,
                                      *BATTLE_CONFS)}  # fmt: skip
    mobs = parse_mob_db(raw[MOB_DB].decode())
    items: dict[int, dict[str, Any]] = {}
    for p in ITEM_DBS:
        items.update(parse_item_db(raw[p].decode(errors="replace")))
    server = server_drop_config([(p, raw[p].decode(errors="replace")) for p in BATTLE_CONFS])
    drops = parse_drops(raw[MOB_DB].decode(), items, server)
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
        "items.json": {str(k): v for k, v in sorted(items.items())},
        "drops.json": {str(k): v for k, v in sorted(drops.items())},
        "server.json": {"rathena_ref": ref, "mode": "pre-re", "battle_conf": server,
                        "rate_adjustment": rate_adjustment_reason(server)},  # fmt: skip
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
               "items": len(items), "drop_mobs": len(drops),
               "flooritem_lifetime_ms": server.get("flooritem_lifetime", {}).get("value"),
               "rate_adjustment": rate_adjustment_reason(server),
               "classes": outputs["classes.json"]}  # fmt: skip
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for mob_id in a.show_drops:
        print(f"drops of {mob_id} ({(mobs.get(mob_id) or {}).get('name')}):")
        print("\n".join(drop_table(mob_id, drops, items)) or "  (none)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
