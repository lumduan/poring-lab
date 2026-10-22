"""MW2-0 at RUN TIME: map sheets built in memory from the local KB (ADR-0020 13.2,
mw2-block-editor.md section 4). Nothing is written: the sheets exist only while a request lints or
simulates. Everything read here is GPL-derived (rAthena) or client data, generated LOCALLY and never
committed (CLAUDE.md rule 4); the tests use synthetic files only.

Per map, in this order:
1. `data/kb/maps/<server>/<map>.json` (MW1's sheet file), when a generator has written one: it wins;
2. else a sheet built from what `kb_build` / `kb_route` / `kb_bindings` already extracted:
   - warps: L3 `warp.cells` (bindings/<server>.json);
   - NPCs: L3 `npc.positions` and `npc.kafra` on that map, with their menu options (`npc.menus`);
   - spawns: `spawns.json`; mobs (level, boss, the Aggressive mode flag): `mobs.json`, for every
     species spawned there AND what it turns into (`Mob.turns_into`, transitively), read from the
     NPC_METAMORPHOSIS lines of `mob_skills.json` (Batt 2026-10-22, decision 6: "Add
     metamorphosis (turns_into) to the KB so the species lint sees it": prt_fild08's Pupa ->
     Creamy reaches lint/hunt.py's species check and prep.py's training scope);
   - walkability: the map's GAT in the bindings' `map.walkability.gat_dir` (client data in /dev/shm
     on the host), when it is readable; otherwise none (routes are then estimates, and the linter
     says so).
3. Left out, so the linter fails closed (13.2): map flags, the Kafra's services and save cell, the
   warp an NPC makes after an option, items. Those extractions are approved (Q27) and not built.

KEYS (~~PROVISIONAL, for Batt: ADR-0020 open question 11 and the key scheme~~ ➡️ DECIDED by Batt
2026-10-09, ADR-0020 Q11: these keys are LOCAL ONLY -- they and every filled flow holding them stay
under data/, never committed; the scheme stays as built): the IR stores keys, never text
(ADR-0012). An NPC's key is `n_` + the first 8 hex digits of sha256("<map>|<npc name>"), an
option's is `o_` + the first 8 of sha256("<npc name>|<option text>"): one-way, stable while the
server's scripts are. The names and texts are returned as LABELS for display only, never stored in
a flow.
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from poring_flow.sheet import (
    Kafra,
    MapSheet,
    Mob,
    Npc,
    Spawn,
    Walk,
    Warp,
    World,
    load_world,
)

GAT_HEADER = struct.Struct("<4sBBII")  # "GRAT", major, minor, width, height
GAT_TILE = struct.Struct("<4fHH")  # four corner altitudes, type, water
NOT_WALKABLE = frozenset(
    {1, 5}
)  # rAthena's map cache: wall, cliff (THIRD_PARTY.md, the GAT layout)
MAX_GAT_BYTES = 64 << 20
MAX_SIDE = 1024
# A server or map id names a FILE here: no path separators, no leading dot (no "..").
SAFE_NAME = re.compile(r"^[A-Za-z0-9_@][A-Za-z0-9_@.\-]{0,63}$")
# NPC_METAMORPHOSIS, a mob-skill line whose val1..val5 name the mob(s) it turns into: rAthena picks
# one of the non-zero values. Equal to scripts/kb_build.METAMORPHOSIS (test_kb_build pins it).
METAMORPHOSIS = 193


def npc_key(map_id: str, name: str) -> str:
    return "n_" + hashlib.sha256(f"{map_id}|{name}".encode()).hexdigest()[:8]


def option_key(npc_name: str, text: str) -> str:
    return "o_" + hashlib.sha256(f"{npc_name}|{text}".encode()).hexdigest()[:8]


def read_gat(path: Path) -> Walk | None:
    """A GAT's walkability ('.' walkable, '#' not), rows[y][x]; None when it cannot be read.
    Cached by the file's size and modification time (a GAT is ~3 MB and is parsed per cell)."""
    try:
        st = path.stat()
    except OSError:
        return None
    if st.st_size > MAX_GAT_BYTES:
        return None
    return _read_gat(str(path), st.st_size, st.st_mtime_ns)


@lru_cache(maxsize=8)
def _read_gat(path: str, _size: int, _mtime: int) -> Walk | None:
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if len(data) < GAT_HEADER.size:
        return None
    magic, _major, _minor, w, h = GAT_HEADER.unpack_from(data, 0)
    if magic != b"GRAT" or not (0 < w <= MAX_SIDE and 0 < h <= MAX_SIDE):
        return None
    if len(data) < GAT_HEADER.size + w * h * GAT_TILE.size:
        return None
    rows = []
    for y in range(h):
        row = []
        for x in range(w):
            off = GAT_HEADER.size + (x + y * w) * GAT_TILE.size
            t = GAT_TILE.unpack_from(data, off)[4]
            row.append("#" if t in NOT_WALKABLE else ".")
        rows.append("".join(row))
    return Walk(width=w, height=h, rows=rows)


def metamorphoses(skills: Any) -> dict[int, tuple[int, ...]]:
    """PURE: mob id -> the mobs it can turn into, from `mob_skills.json` (kb_build: mob id -> its
    mob-skill lines, each with `skill` and `vals`): every NPC_METAMORPHOSIS line's positive values,
    ALL of them, in order, once each. (kb_build's classes.json keeps val1 only; the species checks
    read every value: a superset can only refuse more.)"""
    out: dict[int, tuple[int, ...]] = {}
    for k, rows in skills.items() if isinstance(skills, dict) else []:
        if not (isinstance(k, str) and k.isdigit() and isinstance(rows, list)):
            continue
        into: list[int] = []
        for r in rows:
            if not isinstance(r, dict) or r.get("skill") != METAMORPHOSIS:
                continue
            for v in r.get("vals") or []:
                s = str(v).strip()
                if s.isdigit() and int(s) > 0 and int(s) not in into:
                    into.append(int(s))
        if into:
            out[int(k)] = tuple(into)
    return out


def read_metamorphoses(path: Path) -> dict[int, tuple[int, ...]] | None:
    """`metamorphoses` of a `mob_skills.json`; None when it cannot be read. Cached by the file's
    size and modification time (the file is ~1.6 MB, read on every lint)."""
    try:
        st = path.stat()
    except OSError:
        return None
    return _read_metamorphoses(str(path), st.st_size, st.st_mtime_ns)


@lru_cache(maxsize=4)
def _read_metamorphoses(path: str, _size: int, _mtime: int) -> dict[int, tuple[int, ...]] | None:
    raw = _json(Path(path))
    return metamorphoses(raw) if isinstance(raw, dict) else None


@dataclass
class Labels:
    """Display text for keys (local, never stored in a flow)."""

    npcs: dict[str, str] = field(default_factory=dict)
    options: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _menu(by_npc: dict[str, Any], name: str, labels: Labels) -> list[str]:
    keys: list[str] = []
    for call in by_npc.get(name) or []:
        for text in call.get("options") or []:
            if isinstance(text, str):
                k = option_key(name, text)
                labels.options.setdefault(k, text)
                if k not in keys:
                    keys.append(k)
    return keys


def build_sheet(
    map_id: str, l3: dict[str, Any], spawns: dict[str, Any], gat_dir: Path | None, labels: Labels
) -> MapSheet | None:
    """One map's sheet from the extracted KB; None when the KB does not know the map at all."""
    warps_l3 = ((l3.get("warp") or {}).get("cells") or {}).get("by_map") or {}
    npc_l3 = l3.get("npc") or {}
    positions = (npc_l3.get("positions") or {}).get("npcs") or []
    kafras = (npc_l3.get("kafra") or {}).get("npcs") or []
    by_npc = (npc_l3.get("menus") or {}).get("by_npc") or {}
    warps = [
        Warp(
            x=w["x"],
            y=w["y"],
            span_x=w.get("span_x", 0),
            span_y=w.get("span_y", 0),
            to_map=w["to_map"],
            to_x=w["to_x"],
            to_y=w["to_y"],
        )
        for w in warps_l3.get(map_id) or []
    ]
    npcs: list[Npc] = []
    seen: set[str] = set()
    for entry, kafra in [(n, False) for n in positions] + [(n, True) for n in kafras]:
        if entry.get("map") != map_id or not isinstance(entry.get("name"), str):
            continue
        key = npc_key(map_id, entry["name"])
        if key in seen:
            continue
        seen.add(key)
        labels.npcs[key] = entry["name"]
        npcs.append(
            Npc(
                key=key,
                x=int(entry["x"]),
                y=int(entry["y"]),
                menu=_menu(by_npc, entry["name"], labels),
                # services and the save cell are not extracted yet: fail closed (13.2)
                kafra=Kafra(services=[]) if kafra else None,
            )
        )
    spawn_list = [
        Spawn(mob=int(s["id"]), count=max(1, int(s.get("amount", 1))), boss=bool(s.get("boss")))
        for s in spawns.get(map_id) or []
    ]
    walk = read_gat(gat_dir / f"{map_id}.gat") if gat_dir is not None else None
    if not (warps or npcs or spawn_list or walk):
        return None
    return MapSheet(map=map_id, spawns=spawn_list, npcs=npcs, warps=warps, flags=None, walk=walk)


def load_local_world(
    server: str, maps: list[str], kb_root: Path, gat_dir: Path | None = None
) -> tuple[World, Labels]:
    """The sheets of the maps a flow names: a generated sheet file if there is one, else one built
    in memory from the extracted KB. `gat_dir` overrides the bindings' own GAT directory."""
    labels = Labels()
    if not SAFE_NAME.match(server):
        labels.notes.append(f"server id {server!r} cannot name local data")
        return World(server=server), labels
    unsafe = sorted(m for m in maps if not SAFE_NAME.match(m))
    if unsafe:
        labels.notes.append(f"map ids that cannot name local data: {', '.join(unsafe)}")
    maps = [m for m in maps if SAFE_NAME.match(m)]
    try:
        world = load_world(server, maps, root=kb_root / "maps")
    except ValueError as e:  # a generated sheet file that does not validate: fail closed
        labels.notes.append(
            f"a generated sheet under data/kb/maps/{server} is invalid: {type(e).__name__}"
        )
        world = World(server=server)
    l3 = _json(kb_root / "bindings" / f"{server}.json")
    if not isinstance(l3, dict):
        labels.notes.append(f"no L3 bindings for {server} (data/kb/bindings/{server}.json)")
        return world, labels
    spawns = _json(kb_root / "spawns.json")
    spawns = spawns if isinstance(spawns, dict) else {}
    if gat_dir is None:
        walk_cfg = (l3.get("map") or {}).get("walkability") or {}
        gd = walk_cfg.get("gat_dir")
        gat_dir = Path(gd) if isinstance(gd, str) else None
    if gat_dir is not None and not gat_dir.is_dir():
        labels.notes.append(
            f"the GAT directory {gat_dir} is not readable here: routes are estimates"
        )
        gat_dir = None
    sheets = dict(world.sheets)
    for m in sorted(set(maps) - set(sheets)):
        s = build_sheet(m, l3, spawns, gat_dir, labels)
        if s is not None:
            sheets[m] = s
    mobs = dict(world.mobs)
    if not mobs:
        raw = _json(kb_root / "mobs.json")
        wanted = {sp.mob for s in sheets.values() for sp in s.spawns}
        turns = read_metamorphoses(kb_root / "mob_skills.json")
        if turns is None and wanted:
            turns = {}
            labels.notes.append(
                "no readable data/kb/mob_skills.json: what a species turns into (metamorphosis) "
                "is unknown, so the species lists are the spawn lines only"
            )
        todo = list(wanted)
        while todo:  # what they turn into, transitively (Mob.turns_into: lint/hunt.py, prep.py)
            for t in (turns or {}).get(todo.pop(), ()):
                if t not in wanted:
                    wanted.add(t)
                    todo.append(t)
        for k, v in (raw or {}).items() if isinstance(raw, dict) else []:
            if k.isdigit() and int(k) in wanted and isinstance(v, dict):
                mobs[int(k)] = Mob(
                    id=int(k),
                    label=v.get("name"),
                    level=max(1, min(999, int(v.get("level") or 1))),
                    aggressive="Aggressive" in (v.get("modes") or []),
                    boss=v.get("class") == "Boss",
                    turns_into=list((turns or {}).get(int(k), ())),
                )
        if wanted:
            labels.notes.append(
                "aggressive: from the mob's Aggressive mode only (its AI type is not in data/kb)"
            )
    return World(server=server, sheets=sheets, mobs=mobs, items=dict(world.items)), labels
