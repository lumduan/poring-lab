#!/usr/bin/env python3
"""The L3 NO-CLICK layer: static NPC cells from L3 that a walk click must never land on, independent
of the detector (walk@17 item 5; Batt 2026-10-09 ~16:15).

Why: walk@15's two town NPC contacts (docs/demonstrations.md 3.29a) passed every layer it had. The
cursor read WALK, the walk marker was drawn, and the detector envelope held 0 units: the detector
does not box town NPC sprites at all (Batt ~16:10; v0/v1 never trained on them). talk@1 already
finds NPCs from L3 (static server data, ADR-0015) + the camera model; this layer gives the walk
gate the same knowledge. The cursor and detector layers stay for moving / hidden NPCs and units.

What it refuses: a click PIXEL inside an L3 NPC's clickable FOOTPRINT, i.e. a screen box hung from
the NPC's projected feet (the camera model + the map's GAT altitude, at the rule's belief). A cell
whose every candidate point is refused is itself refused (reason ``l3_npc_noclick``).

THE FOOTPRINT IS PROVISIONAL until the targeted test (docs/planning/npc-click-test.md) measures
it. It is sized from the largest town NPC sprite in the evidence (the job-722 guild flag: about
95 x 150 px drawn in snapshot 048 of session 20261009T140625, and TALK read up to 23 px below its
feet, on its stand) plus walk@11's 12 px margin: 60 px left and right of the feet, 165 px above,
36 px below. The same box applies to every NPC. A measured per-job footprint replaces it through
``footprints``.

L3 is read at run time from data/kb (route.json's NPC groups, the bindings' NPC positions and, when
a KB extension writes it, npc_cells.json). Those files are GPL-derived (rAthena): never committed.
COVERAGE MATTERS: the KB lists only the NPC files it was built from. On 2026-10-09 it lacks
prontera's five guild flags (job 722), one of which was contact 1. ``coverage()`` says whether a
map's list is declared COMPLETE; a caller that needs safety must refuse to run on a map that is not.

    npc_noclick.py cells --map prontera [--kb data/kb]     the map's L3 NPC cells and coverage
Pixels and static data only: nothing here reads packets.

INTEGRATION (for the parent; walk17.py is NOT edited here): a function the walk gate calls,
``NoClickLayer.refuse_point(w, u, v)`` -> None or {"refused": "l3_npc_noclick", ...}, applied where
walk@12/13's zone_points filters the work zone (a refused pixel is never hovered nor clicked; a
cell left with no point is "no_safe_point" with why "l3_npc_noclick"); ``cell_refused`` gives the
cell-level answer; ``near_cells`` (the NPC cell and its 8 neighbours) is for goal / substitute /
side-cell draws. See docs/planning/npc-click-test.md, "Integration".
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
KB_DIR = ROOT / "data/kb"
REASON = "l3_npc_noclick"
Cell = tuple[int, int]
# sprite classes the client never draws (poring_dataset.labels: HIDDEN_NPC 111, HIDDEN_WARP_NPC
# 139, INVISIBLE 32767) and the portal effect (45, walk@17 B's warp areas cover it); -1 is FAKE_NPC
NOT_SPRITES = frozenset({"-1", "111", "139", "32767", "45", "FAKE_NPC", "HIDDEN_NPC",
                         "HIDDEN_WARP_NPC", "WARPNPC"})  # fmt: skip


@dataclass(frozen=True, slots=True)
class Footprint:
    """The clickable area around an NPC's projected FEET, client px: ``left`` / ``right`` of the
    feet, ``up`` above them, ``down`` below them. ``source`` says where the numbers come from."""

    left: float
    right: float
    up: float
    down: float
    source: str

    def box(self, u: float, v: float) -> tuple[float, float, float, float]:
        return (u - self.left, v - self.up, u + self.right, v + self.down)


PROVISIONAL = Footprint(
    60.0, 60.0, 165.0, 36.0,
    "PROVISIONAL: the largest town sprite seen (job-722 guild flag, ~95 x 150 px drawn, snapshot "
    "048 of 20261009T140625; its stand read TALK up to 23 px BELOW its feet) + walk@11's 12 px "
    "margin; one box for every NPC until measured",
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class StaticNpc:
    map: str
    cell: Cell
    key: str  # a stable L3 reference (file:line), never the NPC's name in committed text
    sprite: str | None  # the script's sprite field when L3 has it (route.json), else None
    source: str  # which L3 list named it


def _key(file: str | None, line: Any, cell: Cell) -> str:
    return f"{file}:{line}" if file else f"cell:{cell[0]},{cell[1]}"


def load_l3_npcs(map_name: str, kb_dir: Path = KB_DIR) -> tuple[list[StaticNpc], dict[str, Any]]:
    """Every static NPC on ``map_name`` that L3 lists (deduplicated by cell, the first source wins),
    and the coverage: {"complete": bool, "sources": [...], "counts": {...}}. A map is COMPLETE only
    when npc_cells.json (a KB extension built from every NPC file the server loads) says so."""
    out: dict[Cell, StaticNpc] = {}
    counts: dict[str, int] = {}
    complete = False
    ext = kb_dir / "npc_cells.json"
    if ext.exists():
        doc = json.loads(ext.read_text())
        block = doc.get("maps", {}).get(map_name)
        if block is not None:
            complete = bool(block.get("complete"))
            for p in block.get("npcs", []):
                c = (int(p["x"]), int(p["y"]))
                out.setdefault(c, StaticNpc(map_name, c, _key(p.get("file"), p.get("line"), c),
                                            str(p["sprite"]) if p.get("sprite") is not None
                                            else None, "npc_cells.json"))  # fmt: skip
            counts["npc_cells.json"] = len(block.get("npcs", []))
    route = kb_dir / "route.json"
    if route.exists():
        groups = json.loads(route.read_text()).get("npcs", {})
        n = 0
        for items in groups.values():
            for p in items if isinstance(items, list) else []:
                if p.get("map") != map_name:
                    continue
                c = (int(p["x"]), int(p["y"]))
                n += 1
                sprite = None if p.get("sprite") is None else str(p["sprite"])
                out.setdefault(c, StaticNpc(map_name, c, _key(p.get("file"), p.get("line"), c),
                                            sprite, "route.json"))  # fmt: skip
        counts["route.json"] = n
    bindings = kb_dir / "bindings/lab-rathena.json"
    if bindings.exists():
        pos = json.loads(bindings.read_text()).get("npc", {}).get("positions", {}).get("npcs", [])
        n = 0
        for p in pos:
            if p.get("map") != map_name:
                continue
            c = (int(p["x"]), int(p["y"]))
            n += 1
            out.setdefault(c, StaticNpc(map_name, c, _key(p.get("file"), p.get("line"), c), None,
                                        "bindings"))  # fmt: skip
        counts["bindings"] = n
    npcs = [v for v in out.values() if v.sprite is None or v.sprite not in NOT_SPRITES]
    cov = {"complete": complete, "sources": sorted(counts), "counts": counts, "npcs": len(npcs)}
    return sorted(npcs, key=lambda s: s.cell), cov


class NoClickLayer:
    """The static NPCs of ONE map and their clickable footprints (PROVISIONAL unless measured)."""

    def __init__(self, npcs: Sequence[StaticNpc], footprints: dict[str, Footprint] | None = None,
                 default: Footprint = PROVISIONAL, complete: bool = False) -> None:  # fmt: skip
        self.npcs = list(npcs)
        self.footprints = dict(footprints or {})  # by sprite (job id as text), measured
        self.default = default
        self.complete = complete

    @classmethod
    def for_map(cls, map_name: str, kb_dir: Path = KB_DIR, require_complete: bool = False,
                footprints: dict[str, Footprint] | None = None) -> NoClickLayer:  # fmt: skip
        """The layer from L3; ``require_complete``: SystemExit when the map's list is not declared
        complete (fail closed: a partial list protects only the NPCs it names)."""
        npcs, cov = load_l3_npcs(map_name, kb_dir)
        if require_complete and not cov["complete"]:
            raise SystemExit(f"L3 NPC list for {map_name} is not declared complete ({cov}): the "
                             f"no-click layer would miss NPCs (e.g. guild flags)")  # fmt: skip
        return cls(npcs, footprints, complete=bool(cov["complete"]))

    def footprint(self, npc: StaticNpc) -> Footprint:
        return self.footprints.get(npc.sprite or "", self.default)

    def boxes(self, w: Any) -> list[tuple[tuple[float, float, float, float], StaticNpc]]:
        """Each NPC's footprint box in client px at the belief ``w.position`` (``w``: a walk World:
        .camera, .gat, .position)."""
        if not self.npcs:
            return []
        pos = (int(w.position[0]), int(w.position[1]))
        rel = np.array([(n.cell[0] - pos[0], n.cell[1] - pos[1]) for n in self.npcs], dtype=float)
        alt = None if w.gat is None else w.gat.relative_altitude(pos, rel)
        feet = w.camera.project(rel, alt)
        return [(self.footprint(n).box(float(u), float(v)), n)
                for (u, v), n in zip(feet, self.npcs, strict=True)]  # fmt: skip

    def refuse_point(self, w: Any, u: float, v: float) -> dict[str, Any] | None:
        """THE PATCH POINT: None when client pixel (u, v) is outside every footprint; else the
        refusal {"refused": "l3_npc_noclick", "npc": key, "cell": [x, y], "box": [...]}."""
        for (x0, y0, x1, y1), n in self.boxes(w):
            if x0 <= u <= x1 and y0 <= v <= y1:
                box = [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)]
                return {"refused": REASON, "npc": n.key, "cell": list(n.cell), "box": box}
        return None

    def filter_points(self, w: Any, pts: Iterable[tuple[float, float]]
                      ) -> tuple[list[tuple[float, float]], list[dict[str, Any]]]:  # fmt: skip
        """(kept, refused): the candidate pixels outside every footprint, in order, and one refusal
        record per refused pixel (its "at" added)."""
        boxes = self.boxes(w)
        kept: list[tuple[float, float]] = []
        refused: list[dict[str, Any]] = []
        for u, v in pts:
            hit = next((n for (x0, y0, x1, y1), n in boxes if x0 <= u <= x1 and y0 <= v <= y1),
                       None)  # fmt: skip
            if hit is None:
                kept.append((u, v))
            else:
                refused.append({"refused": REASON, "npc": hit.key, "cell": list(hit.cell),
                                "at": [round(u, 1), round(v, 1)]})  # fmt: skip
        return kept, refused

    def cell_refused(self, w: Any, cell: Cell, points: Sequence[tuple[float, float]]) -> str | None:
        """The cell-level answer for the walk gate: ``REASON`` when ``cell`` is an L3 NPC's own
        cell, or when every one of its candidate ``points`` (the rule's own pick-safe pixels for
        it) is refused; None otherwise. No points at all is the caller's no_safe_point, not ours."""
        if any(n.cell == tuple(cell) for n in self.npcs):
            return REASON
        if not points:
            return None
        kept, _ = self.filter_points(w, points)
        return None if kept else REASON

    def near_cells(self, radius: int = 1) -> set[Cell]:
        """Each NPC's cell and the cells within Chebyshev ``radius``: never a drawn goal, an NPC
        substitute or a side cell (walking THROUGH them is fine; only clicks contact)."""
        out: set[Cell] = set()
        for n in self.npcs:
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    out.add((n.cell[0] + dx, n.cell[1] + dy))
        return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cells", help="the map's L3 NPC cells (keys, never names) and coverage")
    c.add_argument("--map", required=True)
    c.add_argument("--kb", type=Path, default=KB_DIR)
    a = ap.parse_args()
    npcs, cov = load_l3_npcs(a.map, a.kb)
    print(json.dumps({"map": a.map, "coverage": cov, "footprint": PROVISIONAL.source,
                      "npcs": [{"cell": list(n.cell), "key": n.key, "sprite": n.sprite,
                                "source": n.source} for n in npcs]}, indent=1))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
