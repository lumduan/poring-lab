#!/usr/bin/env python3
"""N1 (labels v2, docs/planning/labels-v2-plan.md 1.2): the NPC id -> sprite FILE table for the
first workflow's NPCs ALONG THE ROUTE (Batt 2026-10-09: "NPC sprites only along the route").

    npc_sprites.py build [--kb data/kb/first_workflow.json] [--grf PATH] [--mapcache-dir DIR]
                         [--dest prontera --dest morocc_in] [--out data/kb/npc_sprites.json]
    npc_sprites.py summary [--table data/kb/npc_sprites.json]      ids and counts only

Which NPCs (the scope, derived from the KB, not listed by hand):
  * the training grounds: every DRAWN NPC on the training-ground maps (labels-v2-plan 7.3: 15
    sprites). The portal (the `warp` class, 1.3) and the classes the client never draws are not
    sprites here;
  * the Merchant route for the supported destinations (Batt 7.7 item 3: the two easiest first,
    prontera and morocc_in): the graduation arrival in alberta_in, the job changer, the storehouse,
    the KB's `walk_kafra` legs to the destination NPC and back, the storehouse and the job changer
    again. Each map's walk between those stops is a shortest 8-neighbour path on the SERVER's
    walkability grid (10 / 14, no corner cutting). An NPC is "along the route" when its cell is
    within AREA_SIZE (14) cells, Chebyshev, of a path cell: the server sends a unit to the client
    only within that range, so an NPC farther from every path cell is never drawn on this route.

The sprite file (three sources, all must agree or the row says why not):
  1. rAthena's constant for the id (src/map/npc.hpp `e_job_types`, the pinned ref; JT_X);
  2. the client's own tables: data\\luafiles514\\lua files\\datainfo\\npcidentity.lub (JT_X -> id)
     and jobname.lub (id -> the sprite name), read by scripts/lua51_tables.py (nothing executed);
  3. the archive: data\\sprite\\npc\\<name>.spr and .act present (flags reported).
A sprite whose id is a player job is a composite (body + head): flagged "measured extent" (1.2),
never one sprite file. A monster-class id is drawn from the monster sprite folder (the monster
catalog covers it).

rAthena is GPL and the names are the client's: the table goes to data/kb/ (gitignored) and is NEVER
committed (CLAUDE.md rule 4). `summary` prints ids and counts only.
"""

from __future__ import annotations

import argparse
import heapq
import json
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import lua51_tables  # noqa: E402
from map_identity import DEFAULT_GRF, Archive  # noqa: E402

KB = REPO / "data" / "kb" / "first_workflow.json"
OUT = REPO / "data" / "kb" / "npc_sprites.json"
AREA_SIZE = 14  # rAthena battle_config.area_size: a unit is sent to clients within this range
DESTS = ("prontera", "morocc_in")  # Batt 2026-10-09 7.7 item 3: the two easiest first
LUB_DIR = "data/luafiles514/lua files/datainfo/"
NPC_DIR = "data/sprite/npc/"
Cell = tuple[int, int]


# --- client tables ---


def client_tables(arc: Archive) -> tuple[dict[str, int], dict[int, str], list[str]]:
    """(JT name -> id, id -> sprite name, problems) from the archive's npcidentity / jobname."""
    env: dict[str, Any] = {}
    problems: list[str] = []
    for name in ("npcidentity.lub", "jobname.lub"):
        raw = arc.read(LUB_DIR + name)
        if raw is None:
            problems.append(f"{name}: {arc.errors.get(LUB_DIR + name, 'unreadable')}")
            continue
        try:
            stats = lua51_tables.run_main(lua51_tables.parse_chunk(raw), env)
        except lua51_tables.LuaFormatError as exc:
            problems.append(f"{name}: {exc}")
            continue
        odd = {k: v for k, v in stats.items() if k != "followed"}
        if odd:
            problems.append(f"{name}: instructions not followed {odd}")
    ident = env.get("jobtbl")
    names = env.get("JobNameTable")
    by_const = (
        {str(k): int(v) for k, v in ident.items.items() if isinstance(v, int)}
        if isinstance(ident, lua51_tables.Table) else {}
    )  # fmt: skip
    by_id = (
        {int(k): str(v) for k, v in names.items.items()
         if isinstance(k, int) and isinstance(v, str)}
        if isinstance(names, lua51_tables.Table) else {}
    )  # fmt: skip
    if not by_const:
        problems.append("no jobtbl table")
    if not by_id:
        problems.append("no JobNameTable table")
    return by_const, by_id, problems


# --- the route ---


def shortest_path(grid: Any, start: Cell, goals: set[Cell]) -> list[Cell] | None:
    """Dijkstra, 8 neighbours, 10 / 14, no corner cutting, on grid.nopass (rAthena's rule). The
    start cell is never re-checked (a unit stands there)."""
    if not goals:
        return None
    dist = {start: 0}
    prev: dict[Cell, Cell] = {}
    heap = [(0, start)]
    while heap:
        d, cur = heapq.heappop(heap)
        if d > dist.get(cur, 1 << 60):
            continue
        if cur in goals:
            out = [cur]
            while out[-1] != start:
                out.append(prev[out[-1]])
            return out[::-1]
        x, y = cur
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if not (dx or dy):
                    continue
                nx, ny = x + dx, y + dy
                if grid.nopass(nx, ny):
                    continue
                if dx and dy and (grid.nopass(x + dx, y) or grid.nopass(x, y + dy)):
                    continue
                nd = d + (14 if dx and dy else 10)
                if nd < dist.get((nx, ny), 1 << 60):
                    dist[(nx, ny)] = nd
                    prev[(nx, ny)] = cur
                    heapq.heappush(heap, (nd, (nx, ny)))
    return None


def goal_cells(grid: Any, cell: Sequence[int], span: Sequence[int] | None = None) -> set[Cell]:
    """Where a walk to ``cell`` ends: a portal's walkable trigger cells (cell +- span); else the
    cell when walkable; else the nearest ring of walkable cells around it (an NPC on a wall)."""
    cx, cy = int(cell[0]), int(cell[1])
    if span is not None:
        sx, sy = int(span[0]), int(span[1])
        return {(x, y) for x in range(cx - sx, cx + sx + 1) for y in range(cy - sy, cy + sy + 1)
                if not grid.nopass(x, y)}  # fmt: skip
    if not grid.nopass(cx, cy):
        return {(cx, cy)}
    for r in range(1, AREA_SIZE + 1):
        ring = {(x, y) for x in range(cx - r, cx + r + 1) for y in range(cy - r, cy + r + 1)
                if max(abs(x - cx), abs(y - cy)) == r and not grid.nopass(x, y)}  # fmt: skip
        if ring:
            return ring
    return set()


def route_stops(doc: dict[str, Any], dest: str) -> list[dict[str, Any]]:
    """The ordered stops of one Merchant round trip: ("start", map, cell), ("walk", map, cell[,
    span]) and ("jump", map, cell) after a portal or a Kafra teleport."""
    m = doc["scope"]["merchant"]
    npcs = {n["key"]: n for n in m["npcs"]}
    by_role = {(n["map"], n["role"]): n for n in m["npcs"]}
    changer = by_role[(m["home"], "job_change")]
    hub = npcs[m["hub"]]
    dest_npc = next(n for n in m["npcs"] if n["map"] == dest and n["role"] != "job_change")
    trip = m["travel"][dest]["walk_kafra"]
    if trip is None:
        raise ValueError(f"no walk_kafra trip to {dest} in the KB")
    arrival = m["graduation"][0]
    stops: list[dict[str, Any]] = [
        {"do": "start", "map": arrival["to"], "cell": arrival["to_cell"]}
    ]

    def walk(
        map_: str, cell: Sequence[int], span: Sequence[int] | None = None, why: str = ""
    ) -> None:
        stops.append({"do": "walk", "map": map_, "cell": list(cell), "span": span, "why": why})

    def jump(map_: str, cell: Sequence[int]) -> None:
        stops.append({"do": "jump", "map": map_, "cell": list(cell)})

    def leg(e: dict[str, Any]) -> None:
        if e["via"] == "portal":
            walk(e["from"], e["cell"], e.get("span", [1, 1]), "portal")
        else:
            walk(e["from"], e["npc_cell"], None, e["via"])
            if e["via"] == "kafra":  # any Kafra of the same service on the map: the nearest
                stops[-1]["alts"] = same_service(doc, e["from"], e["key"])
        jump(e["to"], e["to_cell"])

    def inside_to(npc: dict[str, Any]) -> None:
        """Reach an NPC of the home map from the arrival room (the KB's home_inside vias)."""
        for row in m.get("home_inside", []):
            if row["npc"] == npc["key"]:
                for _m0, c0, m1, c1 in row["via"]:
                    walk(_m0, c0, [1, 1], "internal portal")
                    jump(m1, c1)
        walk(npc["map"], npc["cell"], None, "npc " + npc["role"])

    walk(changer["map"], changer["cell"], None, "npc job_change")
    inside_to(hub)
    for e in trip["go"]:
        leg(e)
    walk(dest_npc["map"], dest_npc["cell"], None, "npc destination")
    for e in trip["back"]:
        leg(e)
    walk(hub["map"], hub["cell"], None, "npc " + hub["role"])
    first = trip["go"][0]  # the storehouse room's way back to the arrival room
    if first["from"] == m["home"] and first["to"] == m["home"]:
        leg(first)
    walk(changer["map"], changer["cell"], None, "npc job_change")
    return stops


def same_service(doc: dict[str, Any], map_name: str, key: str) -> list[list[int]]:
    """The cells of every NPC on the map whose script calls exactly the functions the KB's chosen
    NPC (``key``) calls: the other Kafras offering the same teleport list (one setter per map)."""
    npcs = doc["maps"].get(map_name, {}).get("npcs", [])
    chosen = next((n for n in npcs if n["key"] == key), None)
    if chosen is None:
        return []
    calls = sorted(chosen.get("script", {}).get("callfunc", []))
    return [[n["x"], n["y"]] for n in npcs
            if calls and sorted(n.get("script", {}).get("callfunc", [])) == calls]  # fmt: skip


def route_cells(stops: list[dict[str, Any]], grids: Any) -> tuple[dict[str, set[Cell]], list[str]]:
    """Per map, every cell the round trip walks through (shortest paths between the stops)."""
    cells: dict[str, set[Cell]] = {}
    problems: list[str] = []
    here: tuple[str, Cell] | None = None
    for s in stops:
        cell = (int(s["cell"][0]), int(s["cell"][1]))
        if s["do"] in ("start", "jump"):
            here = (s["map"], cell)
            cells.setdefault(s["map"], set()).add(cell)
            continue
        assert here is not None
        if here[0] != s["map"]:
            problems.append(f"walk on {s['map']} while at {here[0]}: stop order broken")
            continue
        grid = grids.get(s["map"])
        if grid is None:
            problems.append(f"{s['map']}: not in the server map cache")
            continue
        goals = goal_cells(grid, cell, s.get("span"))
        for alt in s.get("alts", []):
            goals |= goal_cells(grid, alt)
        path = shortest_path(grid, here[1], goals)
        if path is None:
            problems.append(f"{s['map']}: no path {here[1]} -> {cell} ({s['why']})")
            continue
        cells.setdefault(s["map"], set()).update(path)
        here = (s["map"], path[-1])
    return cells, problems


def near_route(npc: dict[str, Any], path: set[Cell]) -> int | None:
    """The Chebyshev distance from the NPC's cell to the nearest path cell (None: no path)."""
    if not path:
        return None
    x, y = int(npc["x"]), int(npc["y"])
    return min(max(abs(x - px), abs(y - py)) for px, py in path)


# --- the table ---


def drawable(n: dict[str, Any], portal: int) -> bool:
    return bool(n.get("drawn")) and n.get("sprite_class") != "hidden" and n["sprite"] != portal


def collect(
    doc: dict[str, Any], route: dict[str, set[Cell]], portal: int
) -> dict[int, list[dict[str, Any]]]:
    """sprite id -> its uses (map, key, cell, scope, distance to the route)."""
    uses: dict[int, list[dict[str, Any]]] = {}
    grounds = set(doc["scope"]["training_grounds"]["maps"])
    for map_name, rec in doc["maps"].items():
        for n in rec.get("npcs", []):
            if not drawable(n, portal):
                continue
            row = {"map": map_name, "key": n["key"], "cell": [n["x"], n["y"]],
                   "dir": n.get("dir"), "drawn": n["drawn"], "kind": n["kind"]}  # fmt: skip
            if map_name in grounds:
                row["scope"] = "training_grounds"
            elif map_name in route:
                d = near_route(n, route[map_name])
                if d is None or d > AREA_SIZE:
                    continue
                row.update(scope="merchant_route", route_distance=d)
            else:
                continue
            uses.setdefault(int(n["sprite"]), []).append(row)
    return uses


def sprite_row(
    sid: int,
    uses: list[dict[str, Any]],
    rathena: dict[int, list[str]],
    client_const: dict[str, int],
    client_name: dict[int, str],
    arc: Archive,
    sprite_class: str,
) -> dict[str, Any]:
    consts = rathena.get(sid, [])
    row: dict[str, Any] = {
        "id": sid, "rathena_const": consts, "sprite_class": sprite_class,
        "scopes": sorted({u["scope"] for u in uses}), "uses": uses, "problems": [],
    }  # fmt: skip
    if sprite_class == "player_job":
        row["box"] = "measured extent (composite body + head, labels-v2-plan 1.2)"
        return row
    if sprite_class == "mob":
        row["box"] = "monster sprite (the monster catalog)"
    agree = [c for c in consts if client_const.get(c) == sid]
    row["client_const_agrees"] = bool(agree)
    if consts and not agree:
        row["problems"].append(
            f"client ids for {consts}: {[client_const.get(c) for c in consts]}, rAthena {sid}"
        )
    name = client_name.get(sid)
    row["client_sprite"] = name
    if name is None:
        row["problems"].append("no client sprite name for the id")
        return row
    if consts and sprite_class == "npc" and norm(name) != norm(consts[0].removeprefix("JT_")):
        row["note"] = "client sprite name differs from the rAthena constant's"
    folder = NPC_DIR if sprite_class == "npc" else "data/sprite/몬스터/"
    files = {}
    for ext in ("spr", "act"):
        full = folder + name.lower() + "." + ext
        flags = arc.flags(full)
        files[ext] = {"name": full, "present": flags is not None,
                      "flags": None if flags is None else f"0x{flags:02x}"}  # fmt: skip
        if flags is None:
            row["problems"].append(f"{full}: not in the archive")
    row["files"] = files
    if sprite_class == "npc":
        row["box"] = "own sprite (N2: sprite_catalog --npc)"
    return row


def norm(s: str) -> str:
    return s.strip().lower()


def build(
    doc: dict[str, Any],
    arc: Archive,
    grids: Any,
    npc_hpp: str,
    dests: Iterable[str] = DESTS,
) -> dict[str, Any]:
    from kb_first_workflow import Sprites, npc_constants

    consts = npc_constants(npc_hpp)
    sprites = Sprites(consts, {})
    rathena: dict[int, list[str]] = {}
    for name, v in consts.items():
        if name.startswith("JT_"):
            rathena.setdefault(v, []).append(name)
    client_const, client_name, problems = client_tables(arc)
    route: dict[str, set[Cell]] = {}
    trips = {}
    for dest in dests:
        stops = route_stops(doc, dest)
        cells, why = route_cells(stops, grids)
        problems += [f"{dest}: {w}" for w in why]
        for m, cs in cells.items():
            route.setdefault(m, set()).update(cs)
        trips[dest] = {"stops": stops, "cells_per_map": {m: len(c) for m, c in cells.items()}}
    uses = collect(doc, route, sprites.portal)
    mob_ids = {int(n["sprite"]) for rec in doc["maps"].values() for n in rec.get("npcs", [])
               if n.get("sprite_class") == "mob"}  # fmt: skip
    rows = []
    for sid in sorted(uses):
        cls = "mob" if sid in mob_ids else sprites.sprite_class(sid)
        rows.append(sprite_row(sid, uses[sid], rathena, client_const, client_name, arc, cls))
    return {
        "generator": "scripts/npc_sprites.py",
        "kb": doc.get("built_at"),
        "rathena_ref": doc.get("rathena_ref"),
        "area_size": AREA_SIZE,
        "destinations": list(dests),
        "trips": trips,
        "client_tables": {"constants": len(client_const), "names": len(client_name)},
        "problems": problems,
        "sprites": rows,
    }


MONSTER_DIR = "data/sprite/몬스터/"


def mob_names(arc: Archive, ids: Iterable[int], aegis: dict[int, str]) -> dict[str, Any]:
    """Monster ids -> the sprite stem the CLIENT draws them with (jobname.lub), with the files'
    presence in the monster folder and whether the stem differs from rAthena's aegis name (the
    name qa_export.Sheets looks files up by)."""
    _const, by_id, problems = client_tables(arc)
    rows = {}
    for i in ids:
        name = by_id.get(int(i))
        row: dict[str, Any] = {"aegis": aegis.get(int(i)), "client_sprite": name}
        if name is None:
            problems.append(f"{i}: no client sprite name")
        else:
            stem = name.lower()
            row["stem"] = stem
            row["files_present"] = all(arc.has(MONSTER_DIR + stem + e) for e in (".spr", ".act"))
            row["differs_from_aegis"] = stem != str(aegis.get(int(i), "")).lower()
            if not row["files_present"]:
                problems.append(f"{i}: {MONSTER_DIR}{stem}.spr/.act not both in the archive")
        rows[str(i)] = row
    return {"mobs": rows, "problems": problems}


def summary(table: dict[str, Any]) -> dict[str, Any]:
    """Ids and counts only (what a committed doc may quote)."""
    rows = table["sprites"]

    def ids(scope: str) -> list[int]:
        return [r["id"] for r in rows if scope in r["scopes"]]

    per_map: dict[str, list[int]] = {}
    for r in rows:
        for u in r["uses"]:
            if u["scope"] == "merchant_route":
                per_map.setdefault(u["map"], [])
                if r["id"] not in per_map[u["map"]]:
                    per_map[u["map"]].append(r["id"])
    return {
        "training_grounds": ids("training_grounds"),
        "merchant_route": ids("merchant_route"),
        "merchant_route_per_map": {m: sorted(v) for m, v in sorted(per_map.items())},
        "union": len(rows),
        "own_sprite_files_present": sum(
            1 for r in rows if r.get("files") and all(f["present"] for f in r["files"].values())
        ),
        "client_const_agrees": sum(1 for r in rows if r.get("client_const_agrees")),
        "name_differs_from_const": [r["id"] for r in rows if r.get("note")],
        "composite": [r["id"] for r in rows if r["sprite_class"] == "player_job"],
        "monster_sprites": [r["id"] for r in rows if r["sprite_class"] == "mob"],
        "with_problems": [r["id"] for r in rows if r["problems"]],
        "route_cells": {d: t["cells_per_map"] for d, t in table["trips"].items()},
        "problems": len(table["problems"]),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pb = sub.add_parser("build")
    pb.add_argument("--kb", type=Path, default=KB)
    pb.add_argument("--grf", type=Path, default=DEFAULT_GRF)
    pb.add_argument("--mapcache-dir", type=Path)
    pb.add_argument("--dest", action="append", help=f"destinations (default {', '.join(DESTS)})")
    pb.add_argument("--out", type=Path, default=OUT)
    ps = sub.add_parser("summary")
    ps.add_argument("--table", type=Path, default=OUT)
    pm = sub.add_parser("mob-names", help="monster ids -> the client's sprite stems")
    pm.add_argument("ids", nargs="+", type=int)
    pm.add_argument("--grf", type=Path, default=DEFAULT_GRF)
    pm.add_argument("--mobs", type=Path, default=REPO / "data" / "kb" / "mobs.json")
    pm.add_argument("--out", type=Path, default=REPO / "data" / "kb" / "monster_sprite_names.json")
    a = ap.parse_args(argv)
    if a.cmd == "summary":
        print(json.dumps(summary(json.loads(a.table.read_text())), indent=1))
        return 0
    if a.cmd == "mob-names":
        mobs = json.loads(a.mobs.read_text())
        mobs = mobs.get("mobs", mobs)
        aegis = {int(k): str(v.get("aegis")) for k, v in mobs.items() if isinstance(v, dict)}
        with a.grf.open("rb") as f:
            res = mob_names(Archive.open(f), a.ids, aegis)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n")
        for i, r in res["mobs"].items():
            flag = " (differs from the aegis name)" if r.get("differs_from_aegis") else ""
            print(f"{i}: files {'present' if r.get('files_present') else 'MISSING'}{flag}")
        print(f"problems: {len(res['problems'])}; table (client names, local): {a.out}")
        return 0 if not res["problems"] else 1
    from kb_first_workflow import NPC_HPP, SRC, Src

    from poring_dataset import mapcache

    doc = json.loads(a.kb.read_text())
    grids = mapcache.load(a.mapcache_dir) if a.mapcache_dir else mapcache.load()
    npc_hpp = Src(SRC, doc.get("rathena_ref")).read(NPC_HPP)
    with a.grf.open("rb") as f:
        arc = Archive.open(f)
        table = build(doc, arc, grids, npc_hpp, a.dest or DESTS)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(table, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(summary(table), indent=1))
    for p in table["problems"]:
        print(f"problem: {p}")
    print(f"table (client names, rAthena cells; never committed): {a.out}")
    return 0 if not table["problems"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
