#!/usr/bin/env python3
"""The example workflow's route, Novice -> Merchant -> Blacksmith, drafted from the KB (Batt,
2026-10-07, Phase 4 UI direction): which maps, monsters, stats, skills and job-change NPCs it
needs, for the lab's PRE-RENEWAL rAthena. It also bounds Phase 3's data scope (the species the
detector must know along the route).

    kb_route.py [--out data/kb]

Static game data only, fetched at the pinned ref like scripts/kb_build.py (same cache, same ref):
mob_db (levels, HP, base/job EXP), job_exp, skill_tree, the spawn and warp tables of the cities and
fields the route can touch, the Kafra teleport lists, and the job-change NPC scripts. rAthena is
GPL-3.0: everything derived here goes to data/kb/ (gitignored) and is NEVER committed (CLAUDE.md
rule 4). That includes NPC positions, menu options and dialog lines. ADR-0015 allows static game
data at runtime; Batt (2026-10-07) applies that to NPC dialog OPTIONS read from the scripts.
Packets stay forbidden at decision time.

Warp lists (route.json "warps", read by walk@17's warp areas and labels_v2's `warp` class): the
hand list WARP_FILES below, and, for every map the first-workflow KB covers
(scripts/kb_first_workflow.py -> data/kb/first_workflow.json, built from EVERY file the server
loads), that KB's COMPLETE list instead: its `warp` lines plus the touch-triggered script NPCs
that warp (cell +- trigger span). A map with no portal gets an EMPTY list there, which says "none"
(a map missing from the dict says "unknown": walk@17 refuses it). REQUIRED_WARP_MAPS must all be
listed, else the run exits 1 (fail closed). "warps_source" says where each map's list came from.

Outputs:
    data/kb/route.json   phases, candidate leveling maps per band with EXP projections, skill trees,
                         the job NPCs with their menus (select/menu/prompt/input) and dialog lines
    data/kb/route.md     the same as a readable draft for Batt
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kb_build  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
JOB_EXP = "db/pre-re/job_exp.yml"
SKILL_TREE = "db/pre-re/skill_tree.yml"
# The fields and dungeons the route can reach from Prontera, Izlude, Alberta and Payon at Merchant
# levels (pre-re spawn files), plus the warp tables to walk between them.
SPAWN_FILES = (
    "npc/pre-re/mobs/fields/prontera.txt",
    "npc/pre-re/mobs/fields/payon.txt",
    "npc/pre-re/mobs/fields/geffen.txt",
    "npc/pre-re/mobs/fields/morocc.txt",
    "npc/pre-re/mobs/dungeons/iz_dun.txt",
    "npc/pre-re/mobs/dungeons/pay_dun.txt",
    "npc/pre-re/mobs/dungeons/orcsdun.txt",
    "npc/pre-re/mobs/dungeons/prt_sew.txt",
    "npc/pre-re/mobs/dungeons/anthell.txt",
)
WARP_FILES = (
    "npc/pre-re/warps/cities/alberta.txt",
    "npc/warps/cities/alberta.txt",
    "npc/pre-re/warps/cities/prontera.txt",
    "npc/warps/cities/prontera.txt",
    "npc/pre-re/warps/cities/izlude.txt",
    "npc/warps/cities/payon.txt",
    "npc/warps/cities/einbroch.txt",
    "npc/pre-re/warps/cities/einbroch.txt",
    "npc/pre-re/warps/fields/prontera_fild.txt",
    "npc/pre-re/warps/fields/payon_fild.txt",
    # the held-out dungeon and the visual-diversity maps (Batt 2026-10-09: walk@17 blocks warp
    # areas from this table and refuses a map it does not list)
    "npc/warps/dungeons/iz_dun.txt",
    "npc/pre-re/warps/fields/morroc_fild.txt",
    "npc/warps/cities/lutie.txt",
    "npc/warps/fields/glastheim.txt",
)
FIRST_WORKFLOW = ROOT / "data" / "kb" / "first_workflow.json"
# walk@17 refuses a map route.json does not list (Batt 2026-10-09): the first workflow's maps --
# the 20 training-ground copies and the Merchant route with its delivery towns
REQUIRED_WARP_MAPS = (
    *(f"new_{n}-{m}" for n in range(1, 6) for m in range(1, 5)),
    "alberta", "alberta_in", "prontera", "morocc", "morocc_in",
    "geffen", "geffen_in", "izlude", "izlu2dun", "payon",
)  # fmt: skip
SCRIPTS = {
    "novice": "npc/pre-re/jobs/novice/novice.txt",
    "merchant": "npc/pre-re/jobs/1-1/merchant.txt",
    "blacksmith": "npc/jobs/2-1/blacksmith.txt",
    "kafra_functions": "npc/kafras/functions_kafras.txt",
    "airport_izlude": "npc/airports/izlude.txt",
    "airships": "npc/airports/airships.txt",
    # talk@1's targets (docs/demonstrations.md 3.30, T1): prt_church's Garnet / Henson and the city
    # guide, with their menus (the scripts' own `select` lists)
    "prontera_city": "npc/cities/prontera.txt",
    "prontera_guides": "npc/pre-re/guides/guides_prontera.txt",
}
# rAthena's e_job names; its YAML spells a job as the name without JOB_, title-cased. Built at run
# time: the client's job names are locale-pack strings, never literals in this repo (ADR-0012 hook).
JOB_ENUMS = ("JOB_NOVICE", "JOB_MERCHANT", "JOB_BLACKSMITH")
NOVICE, MERCHANT, BLACKSMITH = (e.removeprefix("JOB_").title() for e in JOB_ENUMS)
JOBS = (NOVICE, MERCHANT, BLACKSMITH)
TARGET = {NOVICE: 10, MERCHANT: 40}  # job levels: the 1st job needs Novice JL10 + Basic Skill 9;
# Blacksmith needs Merchant JL40 and no unspent skill points (the scripts' own checks)
NPC_HEAD = re.compile(
    r"^(?P<map>[\w@-]+),(?P<x>\d+),(?P<y>\d+),(?P<dir>\d+)\t(?P<kind>script|duplicate\([^)]*\)|"
    r"shop|cashshop|trader)\t(?P<name>[^\t]+)\t(?P<sprite>[^,{\t]+)"
)
FLOAT_HEAD = re.compile(r"^-\t(?P<kind>script|shop)\t(?P<name>[^\t]+)\t")
FUNC_HEAD = re.compile(
    r"^function\t(script|)\t?(?P<name>\w+)\t?\{|^function\s+script\s+(?P<n2>\w+)"
)
STR = r"\"(?:[^\"\\]|\\.)*\""  # one double-quoted script string
SELECT = re.compile(rf"\b(select|prompt)\s*\(\s*(?P<args>{STR}(?:\s*[,+]\s*{STR})*)")
MENU = re.compile(r"\bmenu\s+(?P<args>\".*)")
INPUT = re.compile(r"\binput\s+(?P<var>[.@$\w]+)")
MES = re.compile(r"\bmes\s+\"(?P<text>(?:[^\"\\]|\\.)*)\"")


def load_yaml(ref: str, path: str) -> Any:
    return yaml.load(kb_build.fetch(ref, path).decode(), Loader=LOADER)  # noqa: S506


def job_tables(ref: str) -> dict[str, dict[str, list[int]]]:
    """job -> {"base": [exp to go from level i+1 to i+2 ...], "job": [...]}"""
    out: dict[str, dict[str, list[int]]] = {j: {} for j in JOBS}
    for entry in load_yaml(ref, JOB_EXP)["Body"]:
        jobs = {k for k, v in (entry.get("Jobs") or {}).items() if v}
        for key, kind in (("BaseExp", "base"), ("JobExp", "job")):
            if key in entry:
                table = [int(r["Exp"]) for r in sorted(entry[key], key=lambda r: r["Level"])]
                for j in JOBS:
                    if j in jobs:
                        out[j][kind] = table
    return out


MD_AGGRESSIVE = 0x4  # src/common/mmo.hpp e_mode at the pinned ref


def ai_modes(ref: str) -> dict[str, int]:
    """AI type ("04") -> its mode bits, from src/map/mob.hpp's MONSTER_TYPE_xx (the pinned ref)."""
    text = kb_build.fetch(ref, "src/map/mob.hpp").decode(errors="replace")
    pattern = r"MONSTER_TYPE_(\d\d)\s*=\s*(0x[0-9A-Fa-f]+|0)\b"
    return {m[1]: int(m[2], 16) for m in re.finditer(pattern, text)}


def mob_exp(ref: str) -> dict[int, dict[str, Any]]:
    doc = load_yaml(ref, kb_build.MOB_DB)
    ai = ai_modes(ref)
    out = {}
    for e in doc["Body"]:
        modes = {k for k, v in (e.get("Modes") or {}).items() if v}
        bits = ai.get(str(e.get("Ai", "06")).zfill(2), 0)
        out[int(e["Id"])] = {
            "aegis": e.get("AegisName"),
            "name": e.get("Name"),
            "level": e.get("Level", 1),
            "hp": e.get("Hp", 1),
            "base_exp": e.get("BaseExp", 0),
            "job_exp": e.get("JobExp", 0),
            "ai": str(e.get("Ai", "06")).zfill(2),
            "aggressive": bool(bits & MD_AGGRESSIVE) or "Aggressive" in modes,
            "boss": e.get("Class") == "Boss",
            "element": e.get("Element"),
            "race": e.get("Race"),
        }
    return out


def skill_trees(ref: str) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for e in load_yaml(ref, SKILL_TREE)["Body"]:
        job = e.get("Job")
        if job in JOBS:
            out[job] = [
                {
                    "skill": t["Name"],
                    "max": t.get("MaxLevel"),
                    "requires": {r["Name"]: r["Level"] for r in t.get("Requires") or []},
                    "exclude": bool(t.get("Exclude")),
                }
                for t in e.get("Tree") or []
            ]
    return out


def split_args(args: str) -> list[str]:
    """`"a:b","c"` or `"a:" + "b"` -> the options in order (joined, then split on ':')."""
    parts = re.findall(r"\"((?:[^\"\\]|\\.)*)\"", args)
    return "".join(parts).split(":")


def npcs(text: str, file: str) -> list[dict[str, Any]]:
    """Every NPC/function block of a script: its menus, inputs and dialog lines (line numbers)."""
    out: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for no, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("//"):
            continue
        m = NPC_HEAD.match(line)
        f = FLOAT_HEAD.match(line)
        fn = FUNC_HEAD.match(line)
        if m or f or fn:
            if m:
                cur = {
                    "file": file,
                    "line": no,
                    "map": m["map"],
                    "x": int(m["x"]),
                    "y": int(m["y"]),
                    "dir": int(m["dir"]),
                    "kind": m["kind"],
                    "name": m["name"].strip(),
                    "sprite": m["sprite"].strip(),
                }
            elif f:
                cur = {
                    "file": file,
                    "line": no,
                    "map": None,
                    "kind": f["kind"],
                    "name": f["name"].strip(),
                }
            else:
                cur = {
                    "file": file,
                    "line": no,
                    "map": None,
                    "kind": "function",
                    "name": (fn["name"] or fn["n2"] or "").strip(),
                }
            cur.update(menus=[], inputs=[], mes=[])
            out.append(cur)
            continue
        if cur is None:
            continue
        for s in SELECT.finditer(line):
            cur["menus"].append({"line": no, "call": s.group(1), "options": split_args(s["args"])})
        mm = MENU.search(line)
        if mm:
            opts = re.findall(r"\"((?:[^\"\\]|\\.)*)\"\s*,", mm["args"])
            cur["menus"].append({"line": no, "call": "menu", "options": opts})
        for i in INPUT.finditer(line):
            cur["inputs"].append({"line": no, "var": i["var"]})
        for t in MES.finditer(line):
            cur["mes"].append({"line": no, "text": t["text"]})
    return out


def map_table(
    spawn_lines: dict[str, list[dict[str, Any]]], mobs: dict[int, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Per map: the population-weighted level, HP, base/job EXP per kill, job EXP per 1,000 HP."""
    rows = []
    for m, lines in spawn_lines.items():
        pop = [(mobs[s["id"]], s["amount"]) for s in lines if s["id"] in mobs and not s["boss"]]
        if not pop:
            continue
        n = sum(a for _, a in pop)

        def wavg(key: str, pop: list = pop, n: int = n) -> float:
            return sum(mb[key] * a for mb, a in pop) / n

        species = sorted({mb["name"] for mb, _ in pop})
        rows.append(
            {
                "map": m,
                "monsters": n,
                "species": species,
                "level": round(wavg("level"), 1),
                "hp": round(wavg("hp")),
                "base_exp": round(wavg("base_exp"), 1),
                "job_exp": round(wavg("job_exp"), 1),
                "job_exp_per_khp": round(1000 * wavg("job_exp") / max(1.0, wavg("hp")), 2),
                "aggressive_share": round(sum(a for mb, a in pop if mb["aggressive"]) / n, 2),
                "top": [
                    f"{mb['name']} L{mb['level']} x{a}"
                    for mb, a in sorted(pop, key=lambda p: -p[1])[:5]
                ],
            }
        )
    return rows


def kb_warp_rows(rec: dict[str, Any]) -> list[dict[str, Any]]:
    """One first-workflow KB map's warp areas in route.json's row format: every `warp` line, then
    every touch-triggered script NPC whose script warps (its trigger span as the area)."""
    rows = [
        {"x": int(w["x"]), "y": int(w["y"]), "span_x": int(w.get("span_x", 0)),
         "span_y": int(w.get("span_y", 0)), "to_map": w.get("to_map"), "to_x": w.get("to_x"),
         "to_y": w.get("to_y"), "name": w.get("name"), "key": w.get("key"),
         "kind": w.get("kind", "warp"), "drawn": w.get("drawn", True)}
        for w in rec.get("warps", [])
    ]  # fmt: skip
    for n in rec.get("npcs", []):
        span = n.get("trigger_span")
        dest = (n.get("script") or {}).get("warps") or []
        if not (n.get("touch") and span and dest):
            continue
        rows.append({
            "x": int(n["x"]), "y": int(n["y"]), "span_x": int(span[0]), "span_y": int(span[1]),
            "to_map": dest[0].get("map"), "to_x": dest[0].get("x"), "to_y": dest[0].get("y"),
            "name": None, "key": n.get("key"), "kind": "touch_npc", "drawn": n.get("drawn"),
        })  # fmt: skip
    return rows


def merge_kb_warps(
    warps: dict[str, list[dict[str, Any]]], kb: dict[str, Any] | None
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str], dict[str, dict[str, int]]]:
    """(warps, source per map, the change per map that had a hand list): every map the KB covers
    takes the KB's complete list (an empty list when it has none); the rest keep the hand list."""
    out = {m: list(v) for m, v in warps.items()}
    source = {m: "WARP_FILES" for m in warps}
    changed: dict[str, dict[str, int]] = {}
    for m, rec in sorted(((kb or {}).get("maps") or {}).items()):
        if not rec.get("loaded_by_server"):
            continue
        rows = kb_warp_rows(rec)
        if m in out:
            old = {(w["x"], w["y"]) for w in out[m]}
            new = {(w["x"], w["y"]) for w in rows}
            changed[m] = {"hand": len(old), "kb": len(new), "added": len(new - old),
                          "dropped": len(old - new)}  # fmt: skip
        out[m] = rows
        source[m] = "first_workflow.json (every file the server loads)"
    return out, source, changed


def missing_required(warps: dict[str, Any], required: tuple[str, ...]) -> list[str]:
    """Required maps route.json would not list (an empty list counts as listed: "no portal")."""
    return [m for m in required if m not in warps]


def base_level_after(base_exp: float, table: list[int]) -> int:
    lvl, left = 1, base_exp
    for need in table:
        if left < need:
            break
        left -= need
        lvl += 1
    return lvl


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "kb")
    ap.add_argument("--first-workflow", type=Path, default=FIRST_WORKFLOW,
                    help="kb_first_workflow.py's KB: complete warp lists for its maps")  # fmt: skip
    a = ap.parse_args()
    ref = json.loads(kb_build.LOCK.read_text())["rathena_ref"]
    mobs = mob_exp(ref)
    tables = job_tables(ref)
    trees = skill_trees(ref)
    spawns: dict[str, list[dict[str, Any]]] = {}
    for f in SPAWN_FILES:
        for m, lines in kb_build.parse_spawns(kb_build.fetch(ref, f).decode()).items():
            spawns.setdefault(m, []).extend(lines)
    warps: dict[str, list[dict[str, Any]]] = {}
    for f in WARP_FILES:
        try:
            text = kb_build.fetch(ref, f).decode()
        except Exception:  # noqa: BLE001 -- a file absent at this ref is simply not in the table
            continue
        for m, lines in kb_build.parse_warps(text).items():
            warps.setdefault(m, []).extend(lines)
    kb = json.loads(a.first_workflow.read_text()) if a.first_workflow.exists() else None
    if kb is not None and kb.get("rathena_ref") not in (None, ref):
        print(f"kb_route: {a.first_workflow} is from {kb.get('rathena_ref')}, not {ref}: not used")
        kb = None
    warps, warps_source, warps_changed = merge_kb_warps(warps, kb)
    scripts = {
        k: npcs(kb_build.fetch(ref, p).decode(errors="replace"), p) for k, p in SCRIPTS.items()
    }
    maps = map_table(spawns, mobs)
    need = {
        NOVICE: sum(tables[NOVICE]["job"][: TARGET[NOVICE] - 1]),
        MERCHANT: sum(tables[MERCHANT]["job"][: TARGET[MERCHANT] - 1]),
    }
    for r in maps:  # kills to the job-level targets on this map alone, and the base level reached
        for job in (NOVICE, MERCHANT):
            kills = need[job] / max(0.1, r["job_exp"])
            r[f"kills_to_{job.lower()}_target"] = round(kills)
            r[f"base_level_at_{job.lower()}_target"] = base_level_after(
                kills * r["base_exp"], tables[job]["base"]
            )
    route = {
        "ref": ref,
        "mode": "pre-re",
        "targets": {
            "novice_job_level": TARGET[NOVICE],
            "merchant_job_level": TARGET[MERCHANT],
            "job_exp_needed": need,
        },
        "skill_trees": trees,
        "maps": sorted(maps, key=lambda r: r["level"]),
        "warps": warps,
        "warps_source": warps_source,
        "npcs": scripts,
    }
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "route.json").write_text(json.dumps(route, indent=1, ensure_ascii=False))
    (a.out / "route.md").write_text(render(route))
    print(
        json.dumps(
            {
                "out": str(a.out / "route.json"),
                "maps": len(maps),
                "npcs": {k: len(v) for k, v in scripts.items()},
                "job_exp_needed": need,
                "warp_maps": len(warps),
                "required_warps": {m: len(warps[m]) for m in REQUIRED_WARP_MAPS if m in warps},
                "hand_list_vs_kb": warps_changed,
            }
        )
    )
    missing = missing_required(warps, REQUIRED_WARP_MAPS)
    if missing:
        print(f"kb_route: NO warp list for {missing} (build data/kb/first_workflow.json "
              "first: kb_first_workflow.py build): walk@17 refuses these maps",
              file=sys.stderr)  # fmt: skip
        return 1
    return 0


def render(r: dict[str, Any]) -> str:
    out = [
        "# Route: Novice -> Merchant -> Blacksmith (pre-re; LOCAL, GPL-derived, never commit)",
        "",
        f"rAthena {r['ref'][:10]}, mode {r['mode']}. "
        f"Job EXP needed: {r['targets']['job_exp_needed']}.",
        "",
        "## Leveling candidates (population-weighted; kills = to the job target on this map alone)",
        "",
        "| map | lvl | hp | base/job exp | job exp/kHP | aggr | kills to Nov JL10 (base lvl) "
        "| kills to Mer JL40 (base lvl) | top species |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for m in r["maps"]:
        if m["level"] > 45:
            continue
        out.append(
            f"| {m['map']} | {m['level']} | {m['hp']} | {m['base_exp']}/{m['job_exp']} | "
            f"{m['job_exp_per_khp']} | {m['aggressive_share']} | {m['kills_to_novice_target']} "
            f"({m['base_level_at_novice_target']}) | {m['kills_to_merchant_target']} "
            f"({m['base_level_at_merchant_target']}) | {'; '.join(m['top'])} |"
        )
    out += ["", "## Skill trees", ""]
    for job, tree in r["skill_trees"].items():
        items = []
        for t in tree:
            needs = ", ".join(f"{k} {v}" for k, v in t["requires"].items())
            items.append(
                f"{t['skill']} {t['max']}"
                + (f" (needs {needs})" if needs else "")
                + (" [excluded]" if t["exclude"] else "")
            )
        out.append(f"- **{job}:** " + ", ".join(items))
    out += ["", "## Job NPCs and their menus", ""]
    for key in ("merchant", "blacksmith", "novice"):
        for n in r["npcs"][key]:
            if not n["menus"] and not n["inputs"]:
                continue
            where = f"{n['map']} {n.get('x')},{n.get('y')}" if n["map"] else n["kind"]
            out.append(f"### {n['name']} ({where}; {n['file']}:{n['line']})")
            for mnu in n["menus"]:
                out.append(
                    f"- L{mnu['line']} {mnu['call']}: "
                    + " | ".join(f"{i + 1}. {o}" for i, o in enumerate(mnu["options"]))
                )
            for i in n["inputs"]:
                out.append(f"- L{i['line']} input {i['var']}")
            out.append("")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    sys.exit(main())
