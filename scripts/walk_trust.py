#!/usr/bin/env python3
"""THE TRUSTED WALK CELL (2026-10-26, docs/planning/gef10-cursor-unknown.md): a candidate fix for
dungeon_hunt's stop-and-go walk, OFF by default (``dungeon_hunt.py run --walk-trust``).

THE PROBLEM. dungeon_hunt clicks a walk target only where cursor_sword read CLEAR within
CURSOR_WAIT_S (0.35 s). On gef_fild10, 2,249 of 3,510 walk decisions (64 %; 8 runs) ended
UNKNOWN and sent no click. The study found two causes, both of TIMING, not of the cell:
- the client draws its cursor at the new point late: 93 % of the unknown reads came while the GM
  walked (42 %) or within 2 s of its server stop (51 %), when the camera scrolls and the redraw
  lags; the frames inside the 0.35-s window mostly show no arrow at the point yet;
- the WALK arrow ROTATES (cursors.act action 0, six images, one edge-on): its narrow images read
  below DRAWN_MIN against the reader's WALK subset, so a window that falls on them reads UNKNOWN.
Later frames at the same point show the arrow (a WALK cell) in most of them.

WHAT THE CURSOR READ PROTECTS ON A WALK CLICK, and what already covers it on a zoned map:
- a NO-ENTRY cell (the client will not walk): the route grid is the client GAT AND the server map
  cache (stand_grid); the ring's red still vetoes (and, here, an UNKNOWN read with the ring's red
  is a no-entry too); a click that does not move us is a stall (carved after STALL_CLICKS);
- an NPC (a TALK cursor; a click = an NPC contact, a hard bar) and a WARP (a map change): the
  delegated zones keep every route cell and every straight walk segment out of each NPC's and
  span's no-enter area (grown by 4); ``trust_why`` adds the landing cells beyond the aim (a click
  made while the GM moves lands up to ~3 cells further along the walk) and an NPC distance;
- a MONSTER under the pointer (a SWORD: the click would attack it): the read still decides when it
  decides (SWORD = engage, as now); an UNKNOWN that hid a monster becomes an attack request. On
  gef_fild10 every normal species is a target (the Orc Lord is kept off scored runs by the
  @killmonster2 schedule, rogue-gef10.md Amendment E); 23 of the 2,249 unknown targets (1.0 %) had
  a monster on (3), beside (10) or 2-3 cells in front of (10) the cell (packets, offline). A fresh
  detector box near the point (the runner's box watcher, when on) refuses the trust.

PURE functions only; the runner wires them (dungeon_hunt.run, ``--walk-trust``).
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

Cell = tuple[int, int]

TRUST_LEAD = 4  # cells beyond the aim along the walk that must also be safe (the zones note: ~3)
NPC_MIN = 6  # Chebyshev cells from every script NPC's cell (the zones grow each by 4)
BOX_NEAR_PX = 60.0  # a fresh detector box's foot this close to the point refuses the trust
ACTIONS = ("click", "engage", "carve", "refuse")


def lead_cells(here: Cell, aim: Cell, lead: int = TRUST_LEAD) -> list[Cell]:
    """PURE: the aimed cell and up to ``lead`` cells beyond it along the walk's direction (a
    Chebyshev step: each axis's sign of aim - here), where a click sent while the GM moves can
    land (frames lag the server ~0.5 s: frames-lag-server-half-second)."""
    sx = (aim[0] > here[0]) - (aim[0] < here[0])
    sy = (aim[1] > here[1]) - (aim[1] < here[1])
    out = [aim]
    if sx == 0 and sy == 0:
        return out
    for k in range(1, lead + 1):
        out.append((aim[0] + k * sx, aim[1] + k * sy))
    return out


def npc_distance(c: Cell, npcs: Iterable[Sequence[int]]) -> int | None:
    """PURE: Chebyshev cells from ``c`` to the nearest NPC cell (None when there is none)."""
    ds = [max(abs(c[0] - int(n[0])), abs(c[1] - int(n[1]))) for n in npcs]
    return min(ds) if ds else None


def trust_why(here: Cell, aim: Cell, *, route_ok: Any, carved: Any, zones: Any,
              npcs: Sequence[Sequence[int]], lead: int = TRUST_LEAD,
              npc_min: int = NPC_MIN, box_near: bool = False) -> str | None:  # fmt: skip
    """PURE: why the walk target ``aim`` (from ``here``) is NOT trusted without a cursor read, or
    None when it is. ``route_ok`` (rows y, cols x) is the runner's route grid (client GAT AND
    server map cache, warp spans and touch areas out, the zones applied), ``carved`` its carved
    cells, ``zones`` the map's map_zones.Zones, ``npcs`` every script NPC's cell (x, y).

    In order: "box" (a fresh detector box near the point), "off_grid" (a landing cell off the map,
    off the route grid or carved), "no_enter" (a straight walk from ``here`` to a landing cell
    meets a no-cross line or enters a no-enter area ``here`` is not in), "npc" (a landing cell
    within ``npc_min`` of an NPC)."""
    import map_zones as mz

    if box_near:
        return "box"
    h, w = route_ok.shape
    cells = lead_cells(here, aim, lead)
    for i, c in enumerate(cells):
        x, y = c
        if not (0 <= x < w and 0 <= y < h) or not route_ok[y, x] or carved[y, x]:
            if i == 0:
                return "off_grid"
            cells = cells[:i]  # the walk ends at a wall: it cannot land beyond the last cell
            break
    for c in cells:
        if mz.segment_violates(here, c, zones) is not None:
            return "no_enter"
    # map_zones.segment_violates passes an AXIS-ALIGNED straight walk through a no-enter area
    # (its open-interior supercover of a horizontal or vertical segment is empty; 2026-10-26, this
    # study): the trust checks the CLOSED supercover's cells instead (a touch counts)
    home = mz.polys_at(zones, here) if zones is not None and zones.no_enter else frozenset()
    if zones is not None and zones.no_enter:
        for c in mz.supercover(here, cells[-1], closed=True):
            if mz.polys_at(zones, c) - home:
                return "no_enter"
    for c in cells:
        d = npc_distance(c, npcs)
        if d is not None and d < npc_min:
            return "npc"
    return None


def decide(verdict: str, red: int, *, trusted: bool, enabled: bool,
           noentry_red: int) -> tuple[str, str]:  # fmt: skip
    """PURE: one walk decision's (action, why) from the hover's cursor verdict ("clear" / "sword" /
    "noentry" / "unknown"), the red pixels in its crop, and whether the cell is trusted.

    With ``enabled`` False it is dungeon_hunt's walk gate as it was (the default): clear -> click,
    sword -> engage, noentry -> carve, anything else -> refuse ("cursor <verdict>"). With
    ``enabled`` True only an UNKNOWN changes: with the ring's red in the crop it is a no-entry
    (carve, no click); on a trusted cell it is clicked ("trusted"); else refused."""
    if verdict == "clear":
        return "click", "clear"
    if verdict == "sword":
        return "engage", "sword"
    if verdict == "noentry":
        return "carve", "cursor noentry"
    if enabled and verdict == "unknown":
        if red >= noentry_red:
            return "carve", "cursor unknown + red"
        if trusted:
            return "click", "trusted"
    return "refuse", f"cursor {verdict}"
