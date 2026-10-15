#!/usr/bin/env python3
"""The L3 (server) bindings for the lab rAthena (Batt, 2026-10-07: layered knowledge).

    kb_bindings.py [--server lab-rathena] [--out data/kb/bindings]

Writes data/kb/bindings/<server>.json, which poring_skills.resolve reads for the L3 keys an L1
concept needs:
- map.walkability: client∩server (Batt's decision 4, 2026-10-15): a walk uses only cells walkable
  in BOTH the client's GAT (client data in /dev/shm) and the server's map cache; per map, the two
  sources' agreement counts (map_agreement.py; its cell lists stay in data/kb/map_agreement.json)
  and the maps either source lacks;
- warp.cells;
- mob.stats;
- skill.tree;
- npc.positions, npc.menus, npc.kafra;
- kafra.destinations (per town: destinations, fees, arrival cells), kafra.menus (per type);
- quiz.answers: per quiz select, the option the SCRIPT scores, with the question lines before it;
- job_change.script: which NPCs drive each job change;
- server.address: where the address really lives (the settings store, backend only).

Everything is derived from the pinned rAthena (GPL-3.0), fetched like kb_build into /dev/shm, plus
data/kb/route.json (scripts/kb_route.py). The output stays LOCAL and is NEVER committed (CLAUDE.md
rule 4). Static server data is allowed at run time (ADR-0015); packets are not.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kb_build  # noqa: E402
import kb_route  # noqa: E402
import map_agreement  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
KAFRA_FUNCS = "npc/kafras/functions_kafras.txt"
KAFRA_NPCS = ("npc/kafras/kafras.txt", "npc/pre-re/kafras/kafras.txt")
QUIZ_SCRIPTS = ("npc/jobs/2-1/blacksmith.txt",)
SCORED = re.compile(
    rf"if\s*\(\s*select\s*\(\s*(?P<args>{kb_route.STR}(?:\s*[,+]\s*{kb_route.STR})*)\s*\)\s*==\s*"
    r"(?P<n>\d+)\s*\)"
)
POINTS = re.compile(
    r"set\s+(?P<var>[.@$\w]+)\s*,\s*(?P=var)\s*\+\s*(?P<k>\d+)|(?P<v2>[.@$\w]+)\s*\+=\s*(?P<k2>\d+)"
)
MES = re.compile(r"\bmes\s+\"(?P<t>(?:[^\"\\]|\\.)*)\"")
MAP_IS = re.compile(r"\.@map\$\s*==\s*\"(?P<m>[\w-]+)\"")
SETARRAY = re.compile(r"setarray\s+(?P<var>[.@$\w]+)\[0\]\s*,\s*(?P<vals>.*?);")
KAF_TELE = re.compile(
    r"@wrpD\$\[\.@j\]\s*==\s*\"(?P<d>[^\"]+)\"\)\s*warp\s+\"(?P<m>[\w-]+)\"\s*,\s*(?P<x>\d+)\s*,\s*(?P<y>\d+)"
)
KAF_CASE = re.compile(
    r"(?:case\s+(?P<n>\d+)|default)\s*:\s*setarray\s+\.@K_Menu0\$\[0\]\s*,\s*(?P<vals>.*?);"
)


def values(text: str) -> list[str | int]:
    out: list[str | int] = []
    for tok in re.findall(r"\"((?:[^\"\\]|\\.)*)\"|(-?\d+)", text):
        out.append(tok[0] if tok[0] or not tok[1] else int(tok[1]))
    return out


def quiz_answers(text: str, file: str) -> list[dict[str, Any]]:
    """Each `if (select(...) == N) set .@v,.@v+K;`: the script scores option N with K points."""
    lines = text.splitlines()
    out = []
    question: list[str] = []
    npc = None
    for i, line in enumerate(lines):
        head = kb_route.NPC_HEAD.match(line) or kb_route.FLOAT_HEAD.match(line)
        if head:
            npc, question = head["name"].strip(), []
            continue
        for m in MES.finditer(line):
            question.append(m["t"])
        s = SCORED.search(line)
        if not s:
            if "select(" in line:
                question = []
            continue
        # A QUIZ select adds points to a score on the very next statement; a plain menu branch
        # (`if (select("go:stay") == 1)`) does not, and is not an answer.
        after = line[s.end() :] + " " + (lines[i + 1] if i + 1 < len(lines) else "")
        p = POINTS.search(after)
        if not p:
            question = []
            continue
        out.append({
            "npc": npc, "file": file, "line": i + 1,
            "options": kb_route.split_args(s["args"]), "correct": int(s["n"]),
            "points": int(p["k"] or p["k2"]),
            "question": [q for q in question if not q.startswith("[")][-4:],
        })  # fmt: skip
        question = []
    return out


def kafra(funcs: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """(per town: destinations, fees, arrival cells), (main menu per Kafra type)."""
    towns: dict[str, dict[str, Any]] = {}
    arrive = {m["d"]: [m["m"], int(m["x"]), int(m["y"])] for m in KAF_TELE.finditer(funcs)}
    in_set = False
    town = None
    for line in funcs.splitlines():
        if line.startswith("function\tscript\t"):
            in_set = "F_KafSet" in line
            continue
        if not in_set:
            continue
        m = MAP_IS.search(line)
        if m:
            town = m["m"]
            towns.setdefault(town, {})
        for sa in SETARRAY.finditer(line):
            if town is None:
                continue
            if sa["var"] == "@wrpD$":
                towns[town]["destinations"] = values(sa["vals"])
            elif sa["var"] == "@wrpP":
                towns[town]["fees"] = values(sa["vals"])
    for t in towns.values():
        t["arrive"] = {d: arrive.get(str(d)) for d in t.get("destinations", [])}
    menus = {(m["n"] or "default"): values(m["vals"]) for m in KAF_CASE.finditer(funcs)}
    return towns, menus


def leaf(**kw: Any) -> dict[str, Any]:
    return {"status": "generated", **kw}


def walkability(gat_dir: Path, mapcache_dir: Path, kb: Path) -> dict[str, Any]:
    """L3 map.walkability (decision 4): the source is client∩server, with the agreement counts of
    every map that has BOTH a GAT and a server cache entry (no cell lists here) and the maps that
    lack either (the GAT directory's and L3's maps)."""
    doc = map_agreement.build(gat_dir, mapcache_dir, kb, cells=False)
    return leaf(
        source="client∩server",
        decision=map_agreement.DECISION,
        helper="poring_dataset.walkable.both",
        counted=map_agreement.COUNTED,
        dir=str(kb_route.ROOT / "data"),
        gat_dir=str(gat_dir),
        mapcache_dir=str(mapcache_dir),
        mapcache_ref=doc["mapcache_ref"],
        by_map=doc["maps"],
        missing=doc["missing"],
        cells="data/kb/map_agreement.json (scripts/map_agreement.py build; local)",
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--server", default="lab-rathena")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "kb" / "bindings")
    ap.add_argument("--gat-dir", type=Path, default=None,
                    help="the client's GATs (default: poring_dataset.camera.GAT_DIR)")  # fmt: skip
    ap.add_argument("--mapcache-dir", type=Path, default=None,
                    help="the server map cache (default: poring_dataset _generated)")  # fmt: skip
    a = ap.parse_args()
    from poring_dataset import mapcache
    from poring_dataset.camera import GAT_DIR

    a.gat_dir = a.gat_dir or GAT_DIR
    mapcache_dir = a.mapcache_dir or mapcache.GENERATED
    ref = json.loads(kb_build.LOCK.read_text())["rathena_ref"]
    route = json.loads((ROOT / "data" / "kb" / "route.json").read_text())
    if route["ref"] != ref:
        raise SystemExit("data/kb/route.json is from another ref: run scripts/kb_route.py first")
    funcs = kb_build.fetch(ref, KAFRA_FUNCS).decode(errors="replace")
    towns, kmenus = kafra(funcs)
    kafra_npcs = []
    for f in KAFRA_NPCS:
        try:
            text = kb_build.fetch(ref, f).decode(errors="replace")
        except Exception:  # noqa: BLE001 -- absent at this ref: not part of the table
            continue
        kafra_npcs += [n for n in kb_route.npcs(text, f) if n["map"]]
    quiz = []
    for f in QUIZ_SCRIPTS:
        quiz += quiz_answers(kb_build.fetch(ref, f).decode(errors="replace"), f)
    npcs = [n for group in route["npcs"].values() for n in group if n.get("map")]
    out = {
        "server": a.server, "rathena_ref": ref, "mode": route["mode"],
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "never_commit": "GPL-derived (rAthena)",
        "server_": {},
        "map": {"walkability": walkability(a.gat_dir, mapcache_dir, ROOT / "data" / "kb")},
        "warp": {"cells": leaf(by_map=route["warps"])},
        "mob": {"stats": leaf(source="data/kb/mobs.json")},
        "skill": {"tree": leaf(by_job=route["skill_trees"])},
        "npc": {
            "positions": leaf(npcs=[{k: n.get(k) for k in ("name", "map", "x", "y", "file", "line")}
                                    for n in npcs]),
            "menus": leaf(by_npc={n["name"]: n["menus"] for n in npcs if n["menus"]}),
            "kafra": leaf(npcs=[{k: n.get(k) for k in ("name", "map", "x", "y", "file", "line")}
                                for n in kafra_npcs]),
        },
        "kafra": {"destinations": leaf(by_town=towns), "menus": leaf(by_type=kmenus)},
        "quiz": {"answers": leaf(by_select=quiz)},
        "job_change": {"script": leaf(
            merchant=[n["name"] for n in route["npcs"]["merchant"] if n.get("map")],
            blacksmith=[n["name"] for n in route["npcs"]["blacksmith"] if n.get("map")])},
    }  # fmt: skip
    del out["server_"]
    out["server"] = {"name": a.server, "address": {
        "status": "config", "source": "the user settings store (backend only)"}}  # fmt: skip
    a.out.mkdir(parents=True, exist_ok=True)
    path = a.out / f"{a.server}.json"
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    walk = out["map"]["walkability"]
    print(json.dumps({"out": str(path), "npcs": len(npcs), "kafra_npcs": len(kafra_npcs),
                      "kafra_towns": len(towns), "kafra_menu_types": len(kmenus),
                      "quiz_selects": len(quiz), "walkability_maps": len(walk["by_map"]),
                      "walkability_missing": {k: len(v) for k, v in walk["missing"].items()}}
                     ))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
