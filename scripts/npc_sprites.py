#!/usr/bin/env python3
"""N1 (labels v2, docs/planning/labels-v2-plan.md 1.2): the NPC id -> sprite FILE table for the
first workflow's NPCs ALONG THE ROUTE (Batt 2026-10-09: "NPC sprites only along the route"), plus
Batt's EXPLICIT extra set of 2026-10-13 (EXTRA, below).

    npc_sprites.py build [--kb data/kb/first_workflow.json] [--grf PATH] [--mapcache-dir DIR]
                         [--dest prontera --dest geffen_in] [--out data/kb/npc_sprites.json]
                         [--no-extra]
    npc_sprites.py summary [--table data/kb/npc_sprites.json]      ids and counts only

Which NPCs (the scope, derived from the KB, not listed by hand):
  * the training grounds: every DRAWN NPC on the training-ground maps (labels-v2-plan 7.3: 15
    sprites). The portal (the `warp` class, 1.3) and the classes the client never draws are not
    sprites here;
  * the Merchant route for the supported destinations (Batt 7.7 item 3: the two easiest first,
    prontera and geffen_in since 2026-10-15; morocc_in before): the graduation arrival in
    alberta_in, the job changer, the storehouse, the KB's `walk_kafra` legs to the destination NPC
    and back, the storehouse and the job changer again. Each map's walk between those stops is a
    shortest 8-neighbour path on the SERVER's walkability grid (10 / 14, no corner cutting). An NPC
    is "along the route" when its cell is within AREA_SIZE (14) cells, Chebyshev, of a path cell:
    the server sends a unit to the client only within that range, so an NPC farther from every path
    cell is never drawn on this route.
  * an EXPLICIT extra set beside that rule (EXTRA; the rule above is unchanged): Batt 2026-10-13,
    decision 9, "Extend N1 to prt_fild08's 909 and the church's off-route sprites", i.e. the eight
    sprites labels-v2-plan 4a's dry run over v1's NAS sessions found unsized (npc_unsized):
    prt_fild08 909; prt_church 71, 79, 741, 798, 745, 60, 755. Every drawn use of such a sprite on
    its map is listed (scope "extra"); one the KB does not list there is a problem, never a guess.

Each use keeps the SCRIPT's facing (``dir``, the npc line's fourth field) with its map and cell.

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
# Batt 2026-10-09 7.7 item 3: the two easiest first; 2026-10-15 (decision 4): morocc_in dropped
# (morocc's client/server maps disagree), geffen_in in its place (labels-v2-plan 7.7)
DESTS = ("prontera", "geffen_in")
# Batt 2026-10-13 (decision 9; labels-v2-plan 1.3 / 4a): an EXPLICIT extra set beside the route
# scope, whose rule stays as it is. map -> the sprite ids to list there (every drawn use).
EXTRA: dict[str, tuple[int, ...]] = {
    "prt_fild08": (909,),
    "prt_church": (71, 79, 741, 798, 745, 60, 755),
}
EXTRA_WHY = (
    "Batt 2026-10-13 decision 9: the sprites outside the route scope that labels-v2-plan 4a's "
    "dry run over v1's NAS sessions found unsized (npc_unsized)"
)
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
    doc: dict[str, Any],
    route: dict[str, set[Cell]],
    portal: int,
    extra: dict[str, tuple[int, ...]] | None = None,
) -> dict[int, list[dict[str, Any]]]:
    """sprite id -> its uses (map, key, cell, the script's facing, scope, distance to the route).
    ``extra`` (map -> sprite ids) adds every drawn use of those sprites on those maps, scope
    "extra", whatever the route (EXTRA: Batt's explicit set)."""
    uses: dict[int, list[dict[str, Any]]] = {}
    grounds = set(doc["scope"]["training_grounds"]["maps"])
    extra = extra or {}
    for map_name, rec in doc["maps"].items():
        for n in rec.get("npcs", []):
            if not drawable(n, portal):
                continue
            row = {"map": map_name, "key": n["key"], "cell": [n["x"], n["y"]],
                   "dir": n.get("dir"), "drawn": n["drawn"], "kind": n["kind"]}  # fmt: skip
            d = near_route(n, route[map_name]) if map_name in route else None
            if map_name in grounds:
                row["scope"] = "training_grounds"
            elif d is not None and d <= AREA_SIZE:
                row.update(scope="merchant_route", route_distance=d)
            elif int(n["sprite"]) in extra.get(map_name, ()):
                row["scope"] = "extra"
            else:
                continue
            uses.setdefault(int(n["sprite"]), []).append(row)
    return uses


def measure_extra(doc: dict[str, Any], maps: Iterable[str]) -> dict[str, tuple[int, ...]]:
    """MEASUREMENT ONLY (npc-render.md): every drawn NPC sprite on ``maps`` (the portal and the
    hidden classes excluded), so a measurement can render a whole view. Never N1's own scope."""
    portal_like = {45}
    out: dict[str, tuple[int, ...]] = {}
    for m in maps:
        npcs = doc["maps"].get(m, {}).get("npcs", [])
        out[m] = tuple(sorted({int(n["sprite"]) for n in npcs if n.get("drawn") is True
                               and n.get("sprite_class") != "hidden"
                               and int(n["sprite"]) not in portal_like}))  # fmt: skip
    return out


def in_kb_dir(path: Path) -> bool:
    """Is ``path`` inside any checkout's data/kb (the main one or a worktree's)?"""
    return any(p.name == "kb" and p.parent.name == "data" for p in path.resolve().parents)


def merge_extra(
    a: dict[str, tuple[int, ...]], b: dict[str, tuple[int, ...]]
) -> dict[str, tuple[int, ...]]:
    keys = sorted(set(a) | set(b))
    return {k: tuple(sorted(set(a.get(k, ())) | set(b.get(k, ())))) for k in keys}


def extra_problems(
    uses: dict[int, list[dict[str, Any]]], extra: dict[str, tuple[int, ...]]
) -> list[str]:
    """An extra sprite the KB does not list as a drawn NPC on its map: reported, never guessed."""
    out = []
    for map_name, ids in extra.items():
        for sid in ids:
            if not any(u["map"] == map_name for u in uses.get(sid, [])):
                out.append(f"extra {map_name}:{sid}: no drawn NPC with that sprite in the KB")
    return out


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
        row["three_sources"] = three_sources(row)  # never "agree": no single sprite file
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
        row["three_sources"] = three_sources(row)
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
    row["three_sources"] = three_sources(row)
    return row


def three_sources(row: dict[str, Any]) -> dict[str, Any]:
    """The per-sprite agreement N1 requires (ids and flags only): rAthena names a constant for the
    id; the client's npcidentity maps that constant to the same id and jobname names a sprite
    for it; the archive holds that sprite's SPR and ACT. ``agree`` only when all three hold."""
    files = row.get("files") or {}
    out = {
        "rathena_const": bool(row.get("rathena_const")),
        "client_tables": bool(row.get("client_const_agrees")) and bool(row.get("client_sprite")),
        "archive": bool(files) and all(f["present"] for f in files.values()),
        "flags": {e: f["flags"] for e, f in sorted(files.items())},
    }
    out["agree"] = out["rathena_const"] and out["client_tables"] and out["archive"]
    return out


def norm(s: str) -> str:
    return s.strip().lower()


def build(
    doc: dict[str, Any],
    arc: Archive,
    grids: Any,
    npc_hpp: str,
    dests: Iterable[str] = DESTS,
    extra: dict[str, tuple[int, ...]] | None = None,
) -> dict[str, Any]:
    """The table: the route scope (training grounds + the Merchant route) and the ``extra`` set
    (default EXTRA; ``{}`` for the route scope alone)."""
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
    extra = EXTRA if extra is None else extra
    uses = collect(doc, route, sprites.portal, extra)
    problems += extra_problems(uses, extra)
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
        "extra_scope": {
            "why": EXTRA_WHY if extra else None,
            "maps": {m: list(ids) for m, ids in extra.items()},
        },
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

    def per_map(scope: str) -> dict[str, list[int]]:
        out: dict[str, set[int]] = {}
        for r in rows:
            for u in r["uses"]:
                if u["scope"] == scope:
                    out.setdefault(u["map"], set()).add(r["id"])
        return {m: sorted(v) for m, v in sorted(out.items())}

    extra_rows = [r for r in rows if "extra" in r["scopes"]]
    return {
        "training_grounds": ids("training_grounds"),
        "merchant_route": ids("merchant_route"),
        "merchant_route_per_map": per_map("merchant_route"),
        "extra": ids("extra"),
        "extra_per_map": per_map("extra"),
        "extra_check": {
            str(r["id"]): {
                **(r.get("three_sources") or {}),
                "class": r["sprite_class"],
                "uses": sum(1 for u in r["uses"] if u["scope"] == "extra"),
                "problems": len(r["problems"]),
            }
            for r in extra_rows
        },
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
    pb.add_argument("--no-extra", action="store_true",
                    help="the route scope alone (without Batt's 2026-10-13 EXTRA set)")  # fmt: skip
    pb.add_argument("--measure-map", action="append", default=[],
                    help="MEASUREMENT ONLY (npc-render.md): also every drawn NPC sprite on this "
                         "map; refused unless --out is outside data/kb")  # fmt: skip
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
    extra = {} if a.no_extra else dict(EXTRA)
    if a.measure_map:
        if in_kb_dir(a.out):
            print("--measure-map widens N1 beyond Batt's scope: write it outside data/kb "
                  "(e.g. /dev/shm), never into the KB", file=sys.stderr)  # fmt: skip
            return 2
        extra = merge_extra(extra, measure_extra(doc, a.measure_map))
    grids = mapcache.load(a.mapcache_dir) if a.mapcache_dir else mapcache.load()
    npc_hpp = Src(SRC, doc.get("rathena_ref")).read(NPC_HPP)
    with a.grf.open("rb") as f:
        arc = Archive.open(f)
        table = build(doc, arc, grids, npc_hpp, a.dest or DESTS, extra)
    if a.measure_map:
        table["extra_scope"]["measurement_only_maps"] = list(a.measure_map)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(table, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(summary(table), indent=1))
    for p in table["problems"]:
        print(f"problem: {p}")
    print(f"table (client names, rAthena cells; never committed): {a.out}")
    return 0 if not table["problems"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
