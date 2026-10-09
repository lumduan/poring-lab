#!/usr/bin/env python3
"""collect@1: the labels-v2 data COLLECTION session driver for the Novice training grounds, every
move made by `@warp` (docs/planning/labels-v2-plan.md 7.6a: no walking until walk@17 is ready).

The M4 pattern (m4_spawns.py + scripts/runbooks/m4-rerun.sh): the GM types warp and spawn lines
while record_session.py records H.264 in an S2 clean room; every step is a JSON line in an events
timeline; the packets judge the session OFFLINE afterwards. **The GM makes NO world click at all**
(no walk, no attack, no talk). The only mouse use is the UI gate's own known steps (it parks the
cursor at a fixed rest point and closes a window by its chord) and the chat input's click.

    collect_v2.py plan --map M --seed S [--spots K] [--blocks ID ...] [--count 8]
                       [--dwell-s T] [--block-s B] [--portal-dwell-s P] [--kb DIR] [--gat-dir DIR]
        OFFLINE. K dwell spots: walkable cells (the GAT; the server's map cache too when it is on
        this host) OUTSIDE every L3 warp area (route.json; a map it does not list fails closed),
        >= NPC_MIN_CELLS from EVERY L3 NPC (npc_cells.json, drawn or not, + route.json's groups;
        a map not declared complete fails closed), >= SPOT_SPACING apart, seeded. The portal-pass
        cells (a walkable cell PORTAL_RING cells beside each warp area, outside every area). The
        spawn blocks: the map's OWN spawn species (first_workflow.json; 1184 kept as data), one
        `@monster <id> <count>` each at a spot. The planned GM lines, checked against the typing
        guard's repeat rule. The @warp check against the map's mapflags (WARP_FINDING).
    collect_v2.py preflight --map M --seed S [plan options] [--max-minutes N]
        No input, no screenshot: the plan + its line check, the UI gate's readiness on this
        capture path, the GM-state template, the immunity record of THIS GM login, the typing
        guard's state. rc 0 only if all pass (the runbook calls it before the recorder starts).
    collect_v2.py immune-on [--again] | immune-confirm --shot PNG | immune-off | immune-status
        3.33's `@monsterignore` is a TOGGLE: typed blind it can just as well turn immunity OFF.
        See IMMUNITY below.
    collect_v2.py run --map M --seed S --out EVENTS.jsonl [plan options] [--portals]
                      [--max-minutes N]                                     LIVE (the runbook)
    collect_v2.py --check-client       rc 0 only if the client's title bar is on screen (no input)
    collect_v2.py judge SESSION [--events PATH]                                         OFFLINE

THE SESSION (run), after preflight passes:
  1. a CLEAN start: the UI gate (no dialog, menu or window; closes only by known steps), a client
     screenshot (/dev/shm), the GM's fixed state (gm_state.ensure_fixed: Base / Job Lv 1, no
     notices), its vitals (an @heal if low: a start condition, not a failure);
  2. a block left alive by a crashed run is removed first (`@killmonster2 <map>`);
  3. NATURAL DWELLS: per spot `@warp M x y`, dwell T s (the natural spawns wander through a static
     view);
  4. SPAWN BLOCKS, only after every dwell: `@warp` to the block's spot, `@monster <id> <count>`
     (rAthena places them within int(sqrt(count)) + 2 cells of the GM, atcommand.cpp:2393-2397),
     hold B s, `@killmonster2`. That command kills EVERY monster on the map, the natural ones
     too (KILLMONSTER2_FINDING), so it is never typed at the session start and never before a
     dwell; on these maps the natural ones respawn >= 1 s later at random cells;
  5. PORTAL PASSES (--portals): `@warp` to each portal-pass cell, dwell P s;
  6. between steps the GM's vitals from pixels (gm_vitals): an immune GM cannot lose HP, so a heal
     or revive need (after the start) is a CONDITION FAILURE: the run recovers (@heal / @alive)
     and STOPS (rc 3).
  Every typed line passes ro_agent.gm (the UI gate, the foreground gate, the typing guard). The
  typing guard silently SKIPS a 3rd identical line in a row; the driver peeks at its state first
  and stops instead of claiming a warp that was never typed. --max-minutes and SIGTERM end the run
  cleanly (a live block is killed first).

IMMUNITY (3.33): the PCBLOCK_IMMUNE flag lives until the GM's map session ends (a logout / a
re-login); only the anti-macro captcha paths clear it otherwise (pc.cpp:15730, 15866, 15962).
`@monsterignore` flips it (atcommand.cpp:9025-9038) and answers on screen; 3.33 read the answer
from a SCREENSHOT, not by a pixel reader, and no reader exists. So:
  - `immune-on` refuses when this GM login already has a confirmed ON; else it types the toggle
    ONCE, saves a screenshot of the client's answer and records the GM's LOGIN MARKER (the rAthena
    DB: `char.last_login`, set at every character select, char.cpp:121-123, and
    `login.logincount`). The DB is read as ro_agent.gm already does (online_chars) -- an
    operational gate, never perception;
  - a PERSON (or the parent) reads the screenshot: the immune answer -> `immune-confirm --shot`;
    the normal-state answer (it was already ON) -> `immune-on --again`;
  - `run` / `preflight` refuse unless the record is CONFIRMED for the CURRENT marker. Any re-login
    changes the marker -> refused (fail closed: the flag is OFF after a re-login, and the driver
    never types the toggle itself);
  - the judge confirms it per session from the packets: ZERO acts targeting the GM.

THE FINDINGS (pinned rAthena e985006; the parent asked for file:line):
- WARP_FINDING: `@warp` (ACMD_FUNC(mapmove), atcommand.cpp:595-647) refuses only on the
  DESTINATION's `nowarpto` or the SOURCE's `nowarp` for a group without the `any_warp` permission
  (atcommand.cpp:632, 636), or when pc_job_can_entermap says no (pc.cpp:15455-15484: the job's
  noenter zone, from db/pre-re/job_noenter_map.txt, which is EMPTY at this commit: zone 0 ->
  allowed, pc.cpp:15471). The training maps carry nobranch, nomemo, nopenalty, noteleport only
  (npc/mapflag/*.txt; first_workflow.json); `noteleport` is checked by @jump (atcommand.cpp:739)
  and pc_randomwarp (pc.cpp:7216), `nomemo` by @memo (pc.cpp:7242), never by @warp. So group 20
  (groups.yml: mapmove, no any_warp) can @warp INTO and WITHIN new_N-M. A non-walkable target
  cell is replaced by a random free cell within 10 (atcommand.cpp:626-631): the plan picks
  walkable cells only, and the judge checks where each warp landed (map_change).
- KILLMONSTER2_FINDING: `@killmonster2` (ACMD_FUNC(killmonster), atcommand.cpp:2440-2464) runs
  atkillmonster_sub over EVERY BL_MOB of the map (atcommand.cpp:2422-2438, only WoE guardians
  spared): the natural spawns die too. A natural one respawns via mob_setdelayspawn after
  max(1 s, its delay) (mob.cpp:1064-1097, the floor at 1092); the training maps' spawn lines give
  no delay (0), so they come back ~1 s later at random cells (`map,0,0`). A @monster one has no
  spawn data and is freed (mob.cpp:1068-1069, 3640-3645).

Client pixels (screenshots, crops) stay in /dev/shm; nothing here reads packets at decision time
(rule 1); the KB files it reads are local and never committed (rule 4).
"""

from __future__ import annotations

import argparse
import contextlib
import gzip
import hashlib
import json
import math
import random
import signal
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

KB_DIR = ROOT / "data" / "kb"
GAT_DIRS = (Path("/dev/shm/poring-lab-tmp/gat/data"), ROOT / "data" / "gat")
STATE_DIR = Path("/dev/shm/poring-lab-tmp/collect-v2")  # RAM: a host reboot = a fresh GM login
IMMUNE = STATE_DIR / "immune.json"
LIVE_BLOCK = STATE_DIR / "live-block.json"
SHOTS = STATE_DIR / "shots"

GM_AID = 2000002
NPC_MIN_CELLS = 8  # a dwell spot's Chebyshev distance to every L3 NPC
SPOT_SPACING = 12  # between dwell spots (Chebyshev)
OPEN_RADIUS = 7  # a spot's view: the share of walkable cells in its +-7 window ...
OPEN_SHARE = 0.5  # ... at least this (no spot on a one-cell island or against a wall)
PORTAL_RING = (3, 5)  # a portal-pass cell's Chebyshev distance to the warp AREA (outside it)
PORTAL_NPC_MIN = 3
DEFAULT_COUNT = 8
REPEAT_LIMIT = 3  # chat_guard: "refuse_identical_in_a_row" (L2 chat.policy; the fallback is 3)
WARP_BLOCKING = ("nowarp", "nowarpto")  # atcommand.cpp:632, 636 (group 20 has no any_warp)
WARP_IGNORED = ("nobranch", "nomemo", "nopenalty", "noteleport")
ENTRY_SETTLE_S = 7.0  # a warp onto the map from another one (bench.enter_scene's wait)
SAME_MAP_SETTLE_S = 2.5  # a same-map warp: the map redraws around the new cell (m4 FAR_SETTLE_S)
CHUNK_S = 5.0  # dwells and holds are idled in chunks: SIGTERM and --max-minutes stop them
REQUESTS = ("attack_request", "npc_contact", "pickup_request", "self_move_request")
BAD_GM_ACTS = ("normal", "pickup")
MOB_OBJTYPE = 5  # rAthena clif: a monster's object type in ZC_NOTIFY_*ENTRY

Cell = tuple[int, int]


# --- the map's data (local KB + GAT; fail closed) ------------------------------------------------


@dataclass(frozen=True)
class MapData:
    name: str
    walkable: np.ndarray  # (height, width) bool, [y, x]
    warps: list[dict[str, Any]]  # route.json rows: x, y, span_x, span_y, to_map, ...
    npcs: list[Cell]  # EVERY L3 NPC cell (drawn, hidden, conditional)
    spawns: list[dict[str, Any]]  # first_workflow.json rows: id, amount, delay1_ms, ...
    mapflags: list[str]
    server_checked: bool = False  # the server's map cache agreed on the walkable cells


def _load(path: Path, what: str) -> Any:
    if not path.exists():
        raise SystemExit(f"collect@1: {what} missing ({path}): fail closed")
    return json.loads(path.read_text())


def load_map(name: str, kb: Path = KB_DIR, gat_dirs: Sequence[Path] = GAT_DIRS,
             mapcache_dir: Path | None = None) -> MapData:  # fmt: skip
    """Everything the plan needs for ``name``; SystemExit when any source does not cover it."""
    from poring_dataset import gat as gatmod

    route = _load(kb / "route.json", "route.json")
    if name not in (route.get("warps") or {}):
        raise SystemExit(f"collect@1: {name} has no L3 warp list in route.json: its warp areas are "
                         "unknown -- extend the KB first (kb_route.py); fail closed")  # fmt: skip
    cells = _load(kb / "npc_cells.json", "npc_cells.json")
    block = (cells.get("maps") or {}).get(name)
    if block is None or not block.get("complete"):
        raise SystemExit(f"collect@1: {name}'s L3 NPC list is missing or not declared "
                         "complete (npc_cells.json, kb_first_workflow.py npc-cells); fail "
                         "closed")  # fmt: skip
    npcs = {(int(p["x"]), int(p["y"])) for p in block.get("npcs", [])}
    for items in (route.get("npcs") or {}).values():  # route.json's groups too (union)
        for p in items if isinstance(items, list) else []:
            if p.get("map") == name and p.get("x") is not None:
                npcs.add((int(p["x"]), int(p["y"])))
    fw = _load(kb / "first_workflow.json", "first_workflow.json")
    m = (fw.get("maps") or {}).get(name)
    if m is None:
        raise SystemExit(f"collect@1: {name} is not in first_workflow.json (spawns, mapflags); "
                         "fail closed")  # fmt: skip
    gat_path = next((d / f"{name}.gat" for d in gat_dirs if (d / f"{name}.gat").exists()), None)
    if gat_path is None:
        raise SystemExit(f"collect@1: no GAT for {name} in {[str(d) for d in gat_dirs]} "
                         "(map_identity.py gat); fail closed")  # fmt: skip
    walkable = np.asarray(gatmod.parse(gat_path.read_bytes()).walkable(), dtype=bool)
    server_checked = False
    if mapcache_dir is not None and mapcache_dir.exists():
        with contextlib.suppress(Exception):  # the server cache is an extra check, when present
            from poring_dataset import mapcache

            grid = mapcache.load(mapcache_dir, prere=True).get(name)
            if grid is not None and (grid.ys, grid.xs) == walkable.shape:
                srv = server_walkable(grid.cells, grid.xs, grid.ys, mapcache.NOT_WALKABLE)
                walkable = walkable & srv
                server_checked = True
    return MapData(name=name, walkable=walkable, warps=list(route["warps"][name]),
                   npcs=sorted(npcs), spawns=list(m.get("spawns") or []),
                   mapflags=[str(f.get("flag")) for f in m.get("mapflags") or []],
                   server_checked=server_checked)  # fmt: skip


def server_walkable(cells: bytes, xs: int, ys: int, not_walkable: frozenset[int]) -> np.ndarray:
    """The SERVER's walkability (what @warp's CELL_CHKNOPASS tests, mapcache.MapGrid.nopass): the
    cell types, and the last row and column never passable."""
    t = np.frombuffer(cells, dtype=np.uint8).reshape(ys, xs)
    ok = ~np.isin(t, list(not_walkable))
    ok[-1, :] = False
    ok[:, -1] = False
    return np.asarray(ok, dtype=bool)


# --- the plan (pure) -----------------------------------------------------------------------------


def cheb(a: Sequence[int], b: Sequence[int]) -> int:
    return max(abs(int(a[0]) - int(b[0])), abs(int(a[1]) - int(b[1])))


def area_distance(cell: Sequence[int], warp: dict[str, Any]) -> int:
    """Chebyshev cells from ``cell`` to a warp's trigger AREA (its cell +- span); 0 inside."""
    dx = abs(int(cell[0]) - int(warp["x"])) - int(warp.get("span_x", 0))
    dy = abs(int(cell[1]) - int(warp["y"])) - int(warp.get("span_y", 0))
    return max(0, dx, dy)


def in_any_area(cell: Sequence[int], warps: Sequence[dict[str, Any]]) -> bool:
    return any(area_distance(cell, w) == 0 for w in warps)


def open_share(walkable: np.ndarray, cell: Cell, radius: int = OPEN_RADIUS) -> float:
    h, w = walkable.shape
    x, y = cell
    win = walkable[max(0, y - radius) : y + radius + 1, max(0, x - radius) : x + radius + 1]
    return float(win.sum()) / float((2 * radius + 1) ** 2)


def spot_candidates(md: MapData) -> list[Cell]:
    """Every cell a dwell spot may take (sorted): walkable, outside every warp area, >=
    NPC_MIN_CELLS from every L3 NPC, its +-OPEN_RADIUS window inside the map and >= OPEN_SHARE
    walkable."""
    h, w = md.walkable.shape
    ys, xs = np.nonzero(md.walkable)
    out: list[Cell] = []
    for x, y in zip(xs.tolist(), ys.tolist(), strict=True):
        c = (int(x), int(y))
        if not (OPEN_RADIUS <= x < w - OPEN_RADIUS and OPEN_RADIUS <= y < h - OPEN_RADIUS):
            continue
        if in_any_area(c, md.warps):
            continue
        if any(cheb(c, n) < NPC_MIN_CELLS for n in md.npcs):
            continue
        if open_share(md.walkable, c) < OPEN_SHARE:
            continue
        out.append(c)
    return sorted(out)


def rng_for(map_name: str, seed: int) -> random.Random:
    return random.Random(f"collect-v2:{map_name}:{seed}")  # str seeds hash with sha512: stable


def pick_spots(cands: Sequence[Cell], k: int, rng: random.Random,
               spacing: int = SPOT_SPACING) -> list[Cell]:  # fmt: skip
    """Up to ``k`` cells, seeded, pairwise >= ``spacing`` apart (greedy over a shuffled list)."""
    order = list(cands)
    rng.shuffle(order)
    chosen: list[Cell] = []
    for c in order:
        if all(cheb(c, s) >= spacing for s in chosen):
            chosen.append(c)
            if len(chosen) == k:
                break
    return chosen


def portal_cells(md: MapData, rng: random.Random) -> list[dict[str, Any]]:
    """Per L3 warp: one walkable cell PORTAL_RING cells beside its area, outside every area, >=
    PORTAL_NPC_MIN from every NPC (seeded); None when there is none."""
    h, w = md.walkable.shape
    lo, hi = PORTAL_RING
    out = []
    for wp in md.warps:
        x0, y0 = int(wp["x"]), int(wp["y"])
        sx, sy = int(wp.get("span_x", 0)), int(wp.get("span_y", 0))
        cands = []
        for y in range(max(0, y0 - sy - hi), min(h, y0 + sy + hi + 1)):
            for x in range(max(0, x0 - sx - hi), min(w, x0 + sx + hi + 1)):
                c = (x, y)
                if not md.walkable[y, x] or not lo <= area_distance(c, wp) <= hi:
                    continue
                if in_any_area(c, md.warps) or any(cheb(c, n) < PORTAL_NPC_MIN for n in md.npcs):
                    continue
                cands.append(c)
        cell = rng.choice(sorted(cands)) if cands else None
        out.append({"warp": [x0, y0], "span": [sx, sy], "to_map": wp.get("to_map"),
                    "cell": list(cell) if cell else None})  # fmt: skip
    return out


def spawn_range(count: int) -> int:
    """@monster's placement box around the GM: int(sqrt(count)) + 2 (atcommand.cpp:2393)."""
    return int(math.sqrt(count)) + 2


def block_room(md: MapData, cell: Cell, count: int) -> bool:
    """Room for ``count`` monsters around the spot: >= 2 x count walkable cells in the box."""
    r = spawn_range(count)
    x, y = cell
    win = md.walkable[max(0, y - r) : y + r + 1, max(0, x - r) : x + r + 1]
    return int(win.sum()) >= 2 * count


def species_of(md: MapData) -> list[int]:
    """The map's own spawn species in KB order (1184 kept: collection is data, not a target)."""
    out: list[int] = []
    for s in md.spawns:
        sid = int(s["id"])
        if sid not in out:
            out.append(sid)
    return out


def plan_blocks(md: MapData, spots: Sequence[Cell], count: int,
                want: Sequence[int] | None = None,
                repeats: int = 1) -> list[dict[str, Any]]:  # fmt: skip
    """The spawn blocks: each species once per round, ``repeats`` rounds, the spots in rotation
    (spawned monsters wander off: the 3.33 check's three left the GM's view within ~200 s, so
    several shorter blocks keep more of them on screen than one long one)."""
    own = species_of(md)
    species = own if want is None else [int(s) for s in want]
    foreign = [s for s in species if s not in own]
    if foreign:
        raise SystemExit(f"collect@1: {foreign} do not spawn on {md.name} (its own: {own}); "
                         "blocks take the map's own species only")  # fmt: skip
    ok = [i for i, c in enumerate(spots) if block_room(md, c, count)]
    if species and not ok:
        raise SystemExit(f"collect@1: no spot on {md.name} has room for {count} monsters")
    order = [s for _ in range(max(1, repeats)) for s in species]
    return [{"block": j, "species": s, "count": count, "spot": ok[j % len(ok)],
             "cell": list(spots[ok[j % len(ok)]])} for j, s in enumerate(order)]  # fmt: skip


def plan_lines(map_name: str, spots: Sequence[Cell], blocks: Sequence[dict[str, Any]],
               portals: Sequence[dict[str, Any]],
               with_portals: bool = True) -> list[dict[str, Any]]:  # fmt: skip
    """The ordered GM lines the run will type: dwells, then blocks, then portal passes. A warp to
    the cell the GM already stands on is omitted (no line at all)."""
    out: list[dict[str, Any]] = []
    at: Cell | None = None

    def warp(cell: Sequence[int], phase: str, ref: int) -> None:
        nonlocal at
        c = (int(cell[0]), int(cell[1]))
        if c != at:
            out.append({"phase": phase, "ref": ref, "line": f"@warp {map_name} {c[0]} {c[1]}"})
            at = c

    for i, c in enumerate(spots):
        warp(c, "dwell", i)
    for b in blocks:
        warp(b["cell"], "block", b["block"])
        out.append({"phase": "block", "ref": b["block"],
                    "line": f"@monster {b['species']} {b['count']}"})  # fmt: skip
        out.append({"phase": "block", "ref": b["block"], "line": "@killmonster2"})
    if with_portals:
        for i, p in enumerate(portals):
            if p["cell"] is not None:
                warp(p["cell"], "portal", i)
    return out


def repeat_count(last: dict[str, Any] | None, text: str) -> int:
    """The typing guard's count for ``text``: its number in a row of identical lines of its kind
    (chat_guard.before_typing; GM `@` lines are kind "chat")."""
    if last and last.get("text") == text:
        return int(last.get("count", 0)) + 1
    return 1


def check_lines(lines: Sequence[str], limit: int = REPEAT_LIMIT,
                last: dict[str, Any] | None = None) -> dict[str, Any]:  # fmt: skip
    """Simulate the guard's repeat rule over the planned lines (from ``last``, the guard's state):
    every line it would refuse (n >= limit), and the longest identical run."""
    viol, longest = [], 0
    state = dict(last) if last else None
    for i, text in enumerate(lines):
        n = repeat_count(state, text)
        longest = max(longest, n)
        if n >= limit:
            viol.append({"index": i, "line": text, "n": n})
        state = {"text": text, "count": n}
    return {"limit": limit, "max_identical_in_a_row": longest, "violations": viol}


def warp_check(mapflags: Sequence[str]) -> dict[str, Any]:
    """WARP_FINDING on this map's flags: @warp into / within it needs neither blocking flag."""
    blocking = sorted({f for f in mapflags if f in WARP_BLOCKING})
    return {"ok": not blocking, "blocking": blocking,
            "not_checked_by_warp": sorted({f for f in mapflags if f in WARP_IGNORED}),
            "other": sorted({f for f in mapflags if f not in WARP_BLOCKING + WARP_IGNORED}),
            "source": "atcommand.cpp:632 (nowarpto), :636 (nowarp); pc.cpp:15471 "
                      "(job_noenter_map empty)"}  # fmt: skip


def estimate_s(n_spots: int, n_blocks: int, n_portals: int, dwell_s: float, block_s: float,
               portal_s: float) -> float:  # fmt: skip
    per_line = 4.0  # the UI gate + typing + close_chat, measured roughly per GM line
    warps = n_spots + n_blocks + n_portals
    return (ENTRY_SETTLE_S + max(0, warps - 1) * SAME_MAP_SETTLE_S + warps * per_line
            + n_spots * dwell_s + n_blocks * (block_s + 2 * per_line)
            + n_portals * portal_s)  # fmt: skip


def make_plan(md: MapData, seed: int, k: int = 6, count: int = DEFAULT_COUNT,
              blocks: Sequence[int] | None = None, dwell_s: float = 120.0,
              block_s: float = 300.0, portal_s: float = 60.0, portals: bool = True,
              limit: int = REPEAT_LIMIT, repeats: int = 1) -> dict[str, Any]:  # fmt: skip
    rng = rng_for(md.name, seed)
    cands = spot_candidates(md)
    spots = pick_spots(cands, k, rng)
    if not spots:
        raise SystemExit(f"collect@1: no dwell spot on {md.name} satisfies the rules")
    pcs = portal_cells(md, rng)
    blk = plan_blocks(md, spots, count, blocks, repeats)
    lines = plan_lines(md.name, spots, blk, pcs, with_portals=portals)
    check = check_lines([x["line"] for x in lines], limit)
    n_portal = sum(p["cell"] is not None for p in pcs) if portals else 0
    body = {
        "map": md.name, "seed": seed,
        "rules": {"npc_min_cells": NPC_MIN_CELLS, "spot_spacing": SPOT_SPACING,
                  "open_radius": OPEN_RADIUS, "open_share": OPEN_SHARE,
                  "portal_ring": list(PORTAL_RING), "portal_npc_min": PORTAL_NPC_MIN,
                  "distance": "chebyshev", "server_walkable_checked": md.server_checked},
        "spots": [{"i": i, "cell": list(c), "npc_min": min((cheb(c, n) for n in md.npcs),
                                                            default=None),
                   "open": round(open_share(md.walkable, c), 2)} for i, c in enumerate(spots)],
        "spots_wanted": k, "spot_candidates": len(cands),
        "portal_passes": pcs, "with_portals": portals,
        "blocks": blk, "spawn_range": spawn_range(count),
        "natural_spawns": [{"id": int(s["id"]), "amount": int(s.get("amount", 0)),
                            "respawn_ms": max(1000, int(s.get("delay1_ms", 0) or 0))}
                           for s in md.spawns],
        "warp_check": warp_check(md.mapflags),
        "lines": lines, "line_check": check,
        "timing_s": {"dwell": dwell_s, "block": block_s, "portal": portal_s},
        "estimate_min": round(estimate_s(len(spots), len(blk), n_portal, dwell_s, block_s,
                                         portal_s) / 60.0, 1),
        "npcs": len(md.npcs), "warp_areas": len(md.warps),
    }  # fmt: skip
    canon = json.dumps({k_: body[k_] for k_ in ("map", "seed", "spots", "portal_passes", "blocks",
                                                 "lines")}, sort_keys=True)  # fmt: skip
    body["plan_sha"] = hashlib.sha256(canon.encode()).hexdigest()[:16]
    return body


def plan_problems(p: dict[str, Any]) -> list[str]:
    out = []
    if not p["warp_check"]["ok"]:
        out.append(f"@warp is refused on {p['map']} ({p['warp_check']['blocking']})")
    if p["line_check"]["violations"]:
        out.append(f"the typing guard would refuse {p['line_check']['violations']}")
    if len(p["spots"]) < p["spots_wanted"]:
        out.append(f"only {len(p['spots'])} of {p['spots_wanted']} spots fit the rules")
    return out


# --- immunity: the toggle's state, tied to the GM's login (pure decisions) ----------------------


def immunity_ok(record: dict[str, Any] | None, marker: dict[str, Any]) -> tuple[bool, str]:
    if record is None:
        return False, "no immune-on record: run `collect_v2.py immune-on` after the GM's login"
    if record.get("marker") != marker:
        return False, ("the GM logged in again since @monsterignore was sent (marker "
                       f"{record.get('marker')} -> {marker}): the flag is OFF after a re-login; "
                       "run immune-on again")  # fmt: skip
    if record.get("state") == "sent":
        return False, (f"@monsterignore was sent but not confirmed: read {record.get('shot')} "
                       "(the client's own answer), then immune-confirm --shot it")  # fmt: skip
    if record.get("state") != "confirmed":
        return False, f"immunity state {record.get('state')!r} for this login: not ON"
    return True, "confirmed ON for this GM login"


def immune_on_refusal(record: dict[str, Any] | None, marker: dict[str, Any],
                      again: bool) -> str | None:  # fmt: skip
    """Why `immune-on` must NOT type the toggle now (None: type it once)."""
    if record is None or record.get("marker") != marker:
        return None  # a fresh login: the flag is OFF
    state = record.get("state")
    if state == "confirmed":
        return "already confirmed ON for this login: a second toggle would turn it OFF"
    if state == "sent" and not again:
        return (f"a toggle was already sent for this login ({record.get('shot')}): if its "
                "answer is the immune one, immune-confirm; if it is the normal-state one, "
                "--again")  # fmt: skip
    return None


def gm_marker() -> dict[str, Any]:
    """The GM's current login marker from the rAthena DB (as ro_agent.online_chars reads it)."""
    import ro_agent as r

    user = r.account("gm")[0]
    rows = r.db_query(
        "SELECT c.char_id, COALESCE(UNIX_TIMESTAMP(c.last_login), 0), l.logincount FROM `char` c "
        f"JOIN login l ON l.account_id = c.account_id WHERE l.userid = {r.sql_str(user)} "
        "AND c.online = 1;"
    )
    if len(rows) != 1:
        raise r.Stop(f"collect@1: the GM must have exactly one character online "
                     f"(found {len(rows)})")  # fmt: skip
    cid, last, count = rows[0][:3]
    return {"char_id": int(cid), "last_login": int(float(last)), "logincount": int(count)}


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1) + "\n")
    tmp.replace(path)


def _shot(screen: Any, name: str) -> str:
    import ro_agent as r

    SHOTS.mkdir(parents=True, exist_ok=True)
    gx, gy, gw, gh = r.game_region()
    return str(r.to_png(screen.grab(gx, gy, gw, gh)[1], SHOTS / f"{int(time.time())}-{name}.png"))


def cmd_immune_on(a: argparse.Namespace) -> int:
    import ro_agent as r

    marker = gm_marker()
    why = immune_on_refusal(read_json(IMMUNE), marker, a.again)
    if why:
        print(json.dumps({"typed": False, "why": why}))
        return 1
    with r.session("collect-v2-immune") as (agent, screen):
        import bench

        r.gm(agent, screen, "@monsterignore")
        time.sleep(1.0)
        shot = _shot(screen, "immune-on")
        bench.close_chat(agent, screen)
    rec = {"marker": marker, "state": "sent", "shot": shot, "t_wall": time.strftime("%FT%T%z"),
           "again": bool(a.again)}  # fmt: skip
    write_json(IMMUNE, rec)
    nxt = ("READ the screenshot: the immune answer -> immune-confirm --shot; the normal-state "
           "answer -> immune-on --again")  # fmt: skip
    print(json.dumps({"typed": True, **rec, "next": nxt}))
    return 0


def cmd_immune_confirm(a: argparse.Namespace) -> int:
    rec, marker = read_json(IMMUNE), gm_marker()
    if rec is None or rec.get("marker") != marker or rec.get("state") != "sent":
        print(json.dumps({"confirmed": False, "why": "no unconfirmed toggle for this GM login"}))
        return 1
    if str(a.shot) != rec.get("shot"):
        print(json.dumps({"confirmed": False, "why": f"the shot read must be {rec.get('shot')}"}))
        return 1
    rec.update(state="confirmed", confirmed_at=time.strftime("%FT%T%z"))
    write_json(IMMUNE, rec)
    print(json.dumps({"confirmed": True, **rec}))
    return 0


def cmd_immune_off(a: argparse.Namespace) -> int:
    import ro_agent as r

    rec, marker = read_json(IMMUNE), gm_marker()
    ok, why = immunity_ok(rec, marker)
    if not ok:
        print(json.dumps({"typed": False, "why": f"not confirmed ON, so not toggled: {why}"}))
        return 1
    with r.session("collect-v2-immune") as (agent, screen):
        import bench

        r.gm(agent, screen, "@monsterignore")
        time.sleep(1.0)
        shot = _shot(screen, "immune-off")
        bench.close_chat(agent, screen)
    write_json(IMMUNE, {"marker": marker, "state": "off_sent", "shot": shot,
                        "t_wall": time.strftime("%FT%T%z")})  # fmt: skip
    print(json.dumps({"typed": True, "state": "off_sent", "shot": shot}))
    return 0


def cmd_immune_status(_a: argparse.Namespace) -> int:
    rec, marker = read_json(IMMUNE), gm_marker()
    ok, why = immunity_ok(rec, marker)
    print(json.dumps({"on": ok, "why": why, "record": rec, "marker": marker}))
    return 0 if ok else 1


# --- the live session ----------------------------------------------------------------------------


class RunStop(Exception):
    """The run ends here, cleanly (a live block is killed first)."""


class Driver:
    """The session's steps over injected effects, so the order is testable without a client:
    ``send(line) -> bool`` types one GM line (False: not typed), ``idle(s)`` waits without input,
    ``vitals() -> None | "heal" | "revive"`` reads the GM from pixels, ``note(event, **f)`` writes
    the timeline, ``stopped() -> str | None`` says why to stop now (SIGTERM, --max-minutes)."""

    def __init__(self, plan: dict[str, Any], *, send: Callable[[str], bool],
                 idle: Callable[[float], None], vitals: Callable[[], str | None],
                 note: Callable[..., None], stopped: Callable[[], str | None],
                 ns: Callable[[], int] = time.monotonic_ns,
                 clock: Callable[[], float] = time.monotonic,
                 live_block: Path | None = LIVE_BLOCK) -> None:  # fmt: skip
        self.p, self.send, self.idle, self.vitals = plan, send, idle, vitals
        self.note, self.stopped, self.ns, self.live_block = note, stopped, ns, live_block
        self.clock = clock
        self.map = str(plan["map"])
        self.at: Cell | None = None
        self.entered = False
        self.counts: Counter[str] = Counter()

    def line(self, text: str, event: str, **fields: Any) -> bool:
        t = self.ns()
        ok = self.send(text)
        self.note(event, gm_line=text, t_sent_ns=t, ok=ok, **fields)
        self.counts[f"{event}{'' if ok else '_failed'}"] += 1
        return ok

    def wait(self, seconds: float) -> None:
        end = self.clock() + seconds
        while (left := end - self.clock()) > 0:
            why = self.stopped()
            if why:
                raise RunStop(why)
            self.idle(min(CHUNK_S, left))

    def warp(self, cell: Sequence[int], phase: str, ref: int) -> None:
        c = (int(cell[0]), int(cell[1]))
        if c == self.at:
            return
        if not self.line(f"@warp {self.map} {c[0]} {c[1]}", "warp", phase=phase, ref=ref,
                         cell=list(c)):  # fmt: skip
            raise RunStop("warp_not_typed")
        self.at = c
        self.wait(SAME_MAP_SETTLE_S if self.entered else ENTRY_SETTLE_S)
        self.entered = True

    def dwell(self, seconds: float, phase: str, ref: int) -> None:
        self.note("dwell_start", phase=phase, ref=ref, cell=list(self.at or ()))
        try:
            self.wait(seconds)
        finally:
            self.note("dwell_end", phase=phase, ref=ref, cell=list(self.at or ()))
        self.check_vitals()

    def kill(self, ref: int, what: str = "@killmonster2") -> None:
        for attempt in (1, 2):
            if self.line(what, "killed", phase="block", ref=ref, attempt=attempt):
                if self.live_block is not None:
                    with contextlib.suppress(FileNotFoundError):
                        self.live_block.unlink()
                return
        raise RunStop("kill_not_typed")  # the marker stays: the next run's start removes them

    def block(self, b: dict[str, Any]) -> None:
        self.warp(b["cell"], "block", int(b["block"]))
        text = f"@monster {b['species']} {b['count']}"
        if not self.line(text, "spawned", phase="block", ref=int(b["block"]),
                         species=int(b["species"]), count=int(b["count"]),
                         cell=list(b["cell"])):  # fmt: skip
            return  # nothing spawned: no hold, no kill
        if self.live_block is not None:
            write_json(self.live_block, {"map": self.map, "block": b, "t_wall": time.time()})
        try:
            self.wait(float(self.p["timing_s"]["block"]))
        finally:
            self.kill(int(b["block"]))
        self.check_vitals()

    def check_vitals(self, start: bool = False) -> None:
        need = self.vitals()
        if need is None:
            return
        if need == "revive":
            self.line("@alive", "recover", need=need)
        self.line("@heal", "recover", need=need)
        self.note("vitals", need=need, start=start)
        if not start:  # an immune GM cannot lose HP: the CONDITION failed
            raise RunStop("immunity_condition_failed")

    def run(self, portals: bool) -> str:
        """The whole session; returns why it ended ("done" or a RunStop reason)."""
        p = self.p
        try:
            self.check_vitals(start=True)
            left = read_json(self.live_block) if self.live_block is not None else None
            if left is not None and left.get("map"):
                # a crashed run's block is still alive: removed by map name, from anywhere
                self.kill(-1, f"@killmonster2 {left['map']}")
            for s in p["spots"]:
                self.warp(s["cell"], "dwell", int(s["i"]))
                self.dwell(float(p["timing_s"]["dwell"]), "dwell", int(s["i"]))
            for b in p["blocks"]:
                self.block(b)
            if portals:
                for i, pc in enumerate(p["portal_passes"]):
                    if pc["cell"] is not None:
                        self.warp(pc["cell"], "portal", i)
                        self.dwell(float(p["timing_s"]["portal"]), "portal", i)
        except RunStop as exc:
            return str(exc)
        return "done"


def guard_state() -> dict[str, Any] | None:
    """The typing guard's last line of kind "chat" (GM lines), read only."""
    import chat_guard

    doc = read_json(chat_guard.STATE)
    last = (doc or {}).get("chat")
    return last if isinstance(last, dict) else None


def guard_limit() -> int:
    import chat_guard

    return int(chat_guard.policy().get("refuse_identical_in_a_row", REPEAT_LIMIT))


def preflight(p: dict[str, Any], max_minutes: float) -> dict[str, Any]:
    """No input, no screenshot. Every check that would otherwise stop the run mid-recording."""
    import gm_state
    import ro_agent as r
    import ui_gate

    checks: dict[str, Any] = {"plan": plan_problems(p) or "ok"}
    try:
        ui_gate._require_ready()  # the T2 templates are RDP-cut: refused on another path
        checks["ui_gate"] = "ok"
    except r.Stop as exc:
        checks["ui_gate"] = str(exc)
    checks["gm_state_template"] = "ok" if gm_state.TEMPLATE.exists() else str(gm_state.TEMPLATE)
    try:
        ok, why = immunity_ok(read_json(IMMUNE), gm_marker())
        checks["immunity"] = "ok" if ok else why
    except (r.Stop, OSError, ValueError, subprocess.SubprocessError) as exc:
        checks["immunity"] = f"unknown (fail closed): {exc}"
    first = p["lines"][0]["line"] if p["lines"] else None
    if first is not None:
        n = repeat_count(guard_state(), first)
        checks["typing_guard"] = "ok" if n < guard_limit() else f"{first!r} would be #{n}"
    est = float(p["estimate_min"])
    note = "ok" if est <= max_minutes else f"cut at {max_minutes} min (plan {est} min)"
    out = {"pass": all(v == "ok" for k, v in checks.items()), "checks": checks,
           "estimate_min": est, "max_minutes": max_minutes, "duration": note,
           "plan_sha": p["plan_sha"]}  # fmt: skip
    return out


def cmd_run(a: argparse.Namespace) -> int:
    import dataset_activity as act
    import gm_state
    import gm_vitals as gv
    import ro_agent as r
    import ui_gate

    md = load_map(a.map, a.kb, a.gat_dirs, a.mapcache_dir)
    p = make_plan(md, a.seed, a.spots, a.count, a.blocks, a.dwell_s, a.block_s, a.portal_dwell_s,
                  a.portals, guard_limit(), a.block_repeats)  # fmt: skip
    pre = preflight(p, a.max_minutes)
    if not pre["pass"]:
        print(json.dumps({"ran": False, **pre}))
        return 2
    stop = {"why": None}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(why="sigterm"))
    deadline = time.monotonic() + a.max_minutes * 60.0
    counts: dict[str, int] = {"gm_failures": 0, "gm_disabled": 0}
    limit = guard_limit()
    evidence = STATE_DIR / f"run-{time.strftime('%Y%m%dT%H%M%S')}"
    reason = "not_started"
    with a.out.open("a") as log, r.session("collect-v2") as (agent, screen):

        def note(event: str, **fields: Any) -> None:
            rec = {"t_mono_ns": r.ns(), "t_wall": time.strftime("%H:%M:%S"), "map": a.map,
                   "event": event, **fields}  # fmt: skip
            log.write(json.dumps(rec) + "\n")
            log.flush()

        def send(text: str) -> bool:
            if counts["gm_disabled"]:  # the chat input was left open: no line goes out any more
                return False
            n = repeat_count(guard_state(), text)
            if n >= limit:  # ro_agent.gm would SKIP it silently: never claim it was typed
                note("guard_would_refuse", gm_line=text, n=n)
                return False
            return bool(act.safe_gm(agent, screen, text, counts))

        def vitals() -> str | None:
            dead = r.is_state(screen, gv.DEAD_STATE)
            frame = r.grab_after(screen, r.game_region(), r.ns())
            return gv.vitals_action(gv.hp_fraction(frame), dead)

        def stopped() -> str | None:
            if stop["why"]:
                return str(stop["why"])
            if counts["gm_disabled"]:
                return "gm_disabled"
            return "max_minutes" if time.monotonic() >= deadline else None

        try:
            r.minimize_consoles(agent, screen)
            clean = ui_gate.ensure_clear(agent, screen, why="collect:start")
            shot = _shot(screen, "collect-start")
            fixed = gm_state.ensure_fixed(agent, screen, why="collect:start", out_dir=evidence)
            note("run_start", plan=p, preflight=pre, ui_gate=clean, start_shot=shot,
                 gm_state={k: v for k, v in fixed.items() if k != "frames"},
                 args={"portals": a.portals, "max_minutes": a.max_minutes})  # fmt: skip
            d = Driver(p, send=send, idle=agent.idle, vitals=vitals, note=note, stopped=stopped,
                       ns=r.ns)  # fmt: skip
            reason = d.run(a.portals)
            note("run_end", reason=reason, counts=dict(d.counts), gm=counts)
        except r.Stop as exc:
            reason = f"stop: {exc}"
            note("run_end", reason=reason, gm=counts)
    print(json.dumps({"ran": True, "reason": reason, "map": a.map, "seed": a.seed,
                      "plan_sha": p["plan_sha"], **counts}))  # fmt: skip
    return 0 if reason == "done" else (3 if reason == "immunity_condition_failed" else 1)


# --- the offline judge (pure) --------------------------------------------------------------------


def _strip_gat(m: Any) -> str:
    s = str(m or "")
    return s[:-4] if s.endswith(".gat") else s


def _i(v: Any, default: int = -1) -> int:
    """An int field of a packet event; None or a missing field gives ``default`` (real events
    carry `"gid": null`, e.g. a chat line without a speaker)."""
    try:
        return default if v is None else int(v)
    except (TypeError, ValueError):
        return default


def judge(packets: Sequence[dict[str, Any]], timeline: Sequence[dict[str, Any]],
          gm_aid: int = GM_AID) -> dict[str, Any]:  # fmt: skip
    """The session's safety (no request, no GM act of kind normal / pickup), the immunity (no act
    targets the GM, while monsters moved), the sensor's positive case (the GM's own typed lines
    seen client -> server), where each warp landed, and each spawn block's monsters."""
    ev = sorted(packets, key=lambda e: _i(e.get("t_mono_ns"), 0))
    req = {t: {"gm": 0, "other": 0} for t in REQUESTS}
    gm_acts: Counter[str] = Counter()
    on_gm, mobs = [], set()
    for e in ev:
        typ = e.get("type")
        if typ in req:
            req[typ]["gm" if e.get("validation_account") else "other"] += 1
        elif typ == "act":
            if _i(e.get("src_gid"), -1) == gm_aid:
                gm_acts[str(e.get("kind"))] += 1
            if _i(e.get("target_gid"), -1) == gm_aid:
                on_gm.append(e)
        elif typ == "entity_appear" and _i(e.get("objtype"), -1) == MOB_OBJTYPE:
            mobs.add(_i(e.get("gid")))
    moves = sum(1 for e in ev if _i(e.get("gid"), -1) in mobs
                and (e.get("type") == "entity_stop"
                     or (e.get("type") == "entity_appear"
                         and e.get("kind") == "move")))  # fmt: skip
    bad_acts = sum(gm_acts[k] for k in BAD_GM_ACTS)
    safety_ok = not any(v["gm"] or v["other"] for v in req.values()) and bad_acts == 0
    start = next((x for x in timeline if x.get("event") == "run_start"), None)
    plan = (start or {}).get("plan") or {}
    rng = int(plan.get("spawn_range", spawn_range(DEFAULT_COUNT)))
    typed = [x for x in timeline if x.get("gm_line") and x.get("ok")]
    seen = [e for e in ev if e.get("type") == "chat" and e.get("dir") == "cs"
            and str(e.get("text", "")).lstrip().startswith("@")]  # fmt: skip
    used: set[int] = set()
    matched = 0
    for x in typed:
        lo, hi = int(x["t_sent_ns"]) - 1_000_000_000, int(x["t_mono_ns"]) + 5_000_000_000
        hit = next((i for i, e in enumerate(seen) if i not in used
                    and lo <= _i(e.get("t_mono_ns")) <= hi
                    and str(e.get("text", "")).strip() == x["gm_line"]), None)  # fmt: skip
        if hit is not None:
            used.add(hit)
            matched += 1
    warps = []
    for x in typed:
        if x.get("event") != "warp":
            continue
        lo, hi = int(x["t_sent_ns"]), int(x["t_mono_ns"]) + 10_000_000_000
        mc = next((e for e in ev if e.get("type") == "map_change"
                   and lo <= _i(e.get("t_mono_ns")) <= hi), None)  # fmt: skip
        landed = None if mc is None else [_strip_gat(mc.get("map")), int(mc["x"]), int(mc["y"])]
        want = [str(x.get("map")), *[int(v) for v in x.get("cell", [])]]
        warps.append({"line": x["gm_line"], "phase": x.get("phase"), "landed": landed,
                      "ok": landed == want})  # fmt: skip
    blocks = []
    for x in typed:
        if x.get("event") != "spawned":
            continue
        lo, hi = int(x["t_sent_ns"]) - 500_000_000, int(x["t_mono_ns"]) + 5_000_000_000
        cell, sp = x.get("cell") or [0, 0], int(x["species"])
        before = {_i(e.get("gid")) for e in ev if e.get("type") == "entity_appear"
                  and _i(e.get("t_mono_ns")) < lo}  # fmt: skip
        new = {_i(e.get("gid")) for e in ev if e.get("type") == "entity_appear"
               and e.get("kind") == "new" and _i(e.get("job"), -1) == sp
               and lo <= _i(e.get("t_mono_ns")) <= hi and _i(e.get("gid")) not in before
               and cheb((e["x"], e["y"]), cell) <= rng + 1}  # fmt: skip
        kill = next((k for k in typed if k.get("event") == "killed" and k.get("ref") == x.get("ref")
                     and int(k["t_sent_ns"]) > int(x["t_sent_ns"])), None)  # fmt: skip
        died = 0
        if kill is not None:
            klo, khi = int(kill["t_sent_ns"]) - 500_000_000, int(kill["t_mono_ns"]) + 5_000_000_000
            died = len({_i(e.get("gid")) for e in ev if e.get("type") == "entity_vanish"
                        and _i(e.get("gid")) in new and _i(e.get("reason"), -1) == 1
                        and klo <= _i(e.get("t_mono_ns")) <= khi})  # fmt: skip
        blocks.append({"ref": x.get("ref"), "species": sp, "count": int(x.get("count", 0)),
                       "appeared": len(new), "killed_at_end": died,
                       "ok": len(new) >= int(x.get("count", 0))})  # fmt: skip
    dwell_seen: Counter[int] = Counter()
    spans = []
    for s in timeline:
        if s.get("event") == "dwell_start":
            end = next((e for e in timeline if e.get("event") == "dwell_end"
                        and e.get("ref") == s.get("ref") and e.get("phase") == s.get("phase")
                        and _i(e.get("t_mono_ns")) >= int(s["t_mono_ns"])), None)  # fmt: skip
            if end is not None:
                spans.append((int(s["t_mono_ns"]), int(end["t_mono_ns"])))
    for a_, b_ in spans:
        gids_by_job: dict[int, set[int]] = {}
        for e in ev:
            if (e.get("type") == "entity_appear" and _i(e.get("objtype"), -1) == MOB_OBJTYPE
                    and a_ <= _i(e.get("t_mono_ns")) <= b_):  # fmt: skip
                gids_by_job.setdefault(_i(e.get("job")), set()).add(_i(e.get("gid")))
        for job, g in gids_by_job.items():
            dwell_seen[job] += len(g)
    sensor_ok = bool(typed) and matched == len(typed)
    immune_ok = not on_gm
    end = next((x for x in reversed(timeline) if x.get("event") == "run_end"), None)
    return {
        "safety": {"requests": req, "gm_acts": dict(gm_acts), "bad_gm_acts": bad_acts,
                   "pass": safety_ok},
        "immunity": {"acts_on_gm": len(on_gm), "monster_moves": moves, "pass": immune_ok},
        "sensor": {"gm_lines_typed": len(typed), "seen_client_to_server": len(seen),
                   "matched": matched, "pass": sensor_ok},
        "warps": {"n": len(warps), "landed_as_planned": sum(w["ok"] for w in warps),
                  "off": [w for w in warps if not w["ok"]]},
        "blocks": blocks,
        "dwells": {"n": len(spans), "monster_sightings_by_job": dict(sorted(dwell_seen.items()))},
        "run_end": (end or {}).get("reason"), "plan_sha": plan.get("plan_sha"),
        "protocol_ok": all(w["ok"] for w in warps) and all(b["ok"] for b in blocks),
        "pass": safety_ok and immune_ok and sensor_ok,
    }  # fmt: skip


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    opener: Any = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def cmd_judge(a: argparse.Namespace) -> int:
    packets = read_jsonl(a.session / "packets.jsonl.gz")
    events_path = a.events or a.session / "collect-events.jsonl"
    timeline = read_jsonl(events_path)
    out = {"session": a.session.name, "events": str(events_path), **judge(packets, timeline)}
    print(json.dumps(out, indent=1))
    return 0 if out["pass"] else 1


# --- the command line ----------------------------------------------------------------------------


def plan_args(q: argparse.ArgumentParser) -> None:
    q.add_argument("--map", required=True)
    q.add_argument("--seed", type=int, required=True)
    q.add_argument("--spots", type=int, default=6)
    q.add_argument("--count", type=int, default=DEFAULT_COUNT, choices=range(1, 21),
                   metavar="1..20")  # fmt: skip
    q.add_argument("--blocks", type=int, nargs="*", default=None,
                   help="species ids (the map's own); default: all of them")  # fmt: skip
    q.add_argument("--dwell-s", type=float, default=120.0)
    q.add_argument("--block-s", type=float, default=300.0)
    q.add_argument("--block-repeats", type=int, default=1, help="rounds of the species' blocks")
    q.add_argument("--portal-dwell-s", type=float, default=60.0)
    q.add_argument("--portals", action=argparse.BooleanOptionalAction, default=True)
    q.add_argument("--max-minutes", type=float, default=55.0)
    q.add_argument("--kb", type=Path, default=KB_DIR)
    q.add_argument("--gat-dir", dest="gat_dirs", type=Path, action="append", default=None)
    q.add_argument("--mapcache-dir", type=Path, default=None,
                   help="the server map cache (default: poring_dataset _generated)")  # fmt: skip


def resolve(a: argparse.Namespace) -> argparse.Namespace:
    a.gat_dirs = a.gat_dirs or list(GAT_DIRS)
    if a.mapcache_dir is None:
        from poring_dataset import mapcache

        a.mapcache_dir = mapcache.GENERATED
    return a


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--check-client"]:
        import m4_spawns

        return int(m4_spawns.check_client())
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    plan_args(sub.add_parser("plan"))
    plan_args(sub.add_parser("preflight"))
    q = sub.add_parser("run")
    plan_args(q)
    q.add_argument("--out", type=Path, required=True)
    q = sub.add_parser("immune-on")
    q.add_argument("--again", action="store_true")
    q = sub.add_parser("immune-confirm")
    q.add_argument("--shot", required=True)
    sub.add_parser("immune-off")
    sub.add_parser("immune-status")
    q = sub.add_parser("judge")
    q.add_argument("session", type=Path)
    q.add_argument("--events", type=Path, default=None)
    a = ap.parse_args(args)
    if a.cmd in ("plan", "preflight", "run"):
        resolve(a)
    if a.cmd == "plan":
        md = load_map(a.map, a.kb, a.gat_dirs, a.mapcache_dir)
        p = make_plan(md, a.seed, a.spots, a.count, a.blocks, a.dwell_s, a.block_s,
                      a.portal_dwell_s, a.portals, REPEAT_LIMIT, a.block_repeats)  # fmt: skip
        print(json.dumps({**p, "problems": plan_problems(p)}, indent=1))
        return 0 if not plan_problems(p) else 1
    if a.cmd == "preflight":
        md = load_map(a.map, a.kb, a.gat_dirs, a.mapcache_dir)
        p = make_plan(md, a.seed, a.spots, a.count, a.blocks, a.dwell_s, a.block_s,
                      a.portal_dwell_s, a.portals, guard_limit(), a.block_repeats)  # fmt: skip
        out = preflight(p, a.max_minutes)
        print(json.dumps(out, indent=1))
        return 0 if out["pass"] else 1
    return {"run": cmd_run, "immune-on": cmd_immune_on, "immune-confirm": cmd_immune_confirm,
            "immune-off": cmd_immune_off, "immune-status": cmd_immune_status,
            "judge": cmd_judge}[a.cmd](a)  # fmt: skip


if __name__ == "__main__":
    sys.exit(main())
