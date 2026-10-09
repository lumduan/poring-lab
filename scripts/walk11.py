#!/usr/bin/env python3
"""walk@11 (docs/demonstrations.md 3.18): walk@10 + the click-instant UNIT GATE (Batt 2026-10-08).

Safety, not accuracy, failed walk@10: one walk click became an attack (the client approached and
hit a unit that reached the click point after the cursor re-check: 3 hard fails), and clicks whose
cursor read WALK beside an NPC's edge contacted the NPC (the replay: walk@8/9/10). So:
1. PREDICTION on the click-decision frame (unit_gate.py): the CPU detector (unit_detector.py:
   player / monster / npc, proven on RDP frames: 97-100 % within the envelope's slack) finds the
   units; each may be anywhere within ceil(H / its fastest speed) + 1 cells at the click's arrival
   (H = the frame's age at the click + 0.36 s latency; speeds from mob_db over the map's KB spawns
   and the Poring; NPCs static) -- Batt's worst-case envelope, no tracker. The click point must
   clear every moved box by 12 px, else it is treated as a point covered by a UNIT (the next point
   on the polyline; walk@8's patience / substitute rules).
   MEMORY (Batt, after pilot 1 attacked a Poring hidden behind a pew): units seen on any park or
   decision frame are remembered 8 s at their absolute cell, their envelope growing with age;
   a refused point moves FARTHER along the polyline (FARTHER points) before patience.
2. The talk references v3 (+72 filled bubbles): an NPC at the click point reads TALK, a unit.
3. NOT included: the "cancel" walk click after a click that hit a unit. Measured 2026-10-08
   (safety_signal_check cancel-test, n=3 clicks that hit): the first hit lands 0-245 ms after the
   request and the client re-requests the attack after the cancel; hits continued in 3/3.
Everything else is walk@10's (its docstring follows).

walk@10 (docs/demonstrations.md 3.17): walk@9 + three changes from walk@9's indoor failures.

walk@9 (3.16) indoors CLEAN 39 / 50 (2026-10-08 00:22-01:02). Its logs, joined to the packets
offline (01:10-01:50):
1. 19 clicks walked ONE CELL SHORT, always to the camera's side ((-1,-1), (0,-1), (-1,0) with the
   indoor yaw), 8 of the 11 failed routes. Every time, that neighbour was a RAISED walkable block
   (a pew's kneeler: all four corners one cell = 5 units up). The character was standing (every
   click >= 6x the walk time after the last move) and the belief was right for 14 of them, so it
   was neither motion nor localisation: the client PICKS the first top surface the camera ray
   comes down through, and a kneeler's top covers the centre of the cell behind it on screen. The
   projected centre that walk@6-9 clicked (and named by the chevrons) was the kneeler.
   -> click points come from that PICKING model (poring_dataset.picking; offline it names the
   server's cell for 480 / 485 logged indoor clicks vs the centre's 467, and 383 / 383 outdoor):
   tier A = every pixel within 6 px picks the target; tier B (3 px) only where no tier-A pixel
   exists (the thin strip behind a kneeler row), and a tier-B click needs the chevrons naming it.
   A neighbour named at a pick-safe point no longer hops to the neighbour's pixel: it is doubt;
   named AGAIN right after a fix (model and marker disagree; pilot route 3 spent all 4 fixes on
   one such cell), the cell is blocked for the route and re-planned around (a goal declines).
2. Along the pew corridors the marker is hidden (~20 px) on cell after cell, so every step needed
   its own /where fix (walk@9 allows one unnamed click per fix) and the 2-fix limit ended routes
   (routes 13 and 25), although every fix was correct. -> a /where fix keeps the belief TRUSTED for
   up to TRUST_CLICKS tier-A clicks while each one visibly SHIFTS the scene; no shift or any doubt
   ends the trust at once.
3. RELOCS 2 -> 4 fixes per route (each ~10 s; 34 / 34 correct in walk@8/9).
Everything else is walk@9 unchanged (its docstring follows).

walk@9 (docs/demonstrations.md 3.16): walk@8 + four fixes from walk@8's indoor tuning failures.

walk@8 (3.14) failed indoors. From its logs (2026-10-08 ~00:30):
1. STATIC GREEN fooled the chevrons: from (112,111) two different targets were "confirmed" with the
   same 43 px of green -- scenery, not the marker -- and the clicks did not move us (two /where
   fixes said so). -> a chevron must be NEW: green already in the parked frame is not the marker.
2. A click that did not move us went unnoticed until doubt. -> after each click the scene must
   SHIFT (the camera follows the character): no shift = doubt -> /where; a click the fix shows went
   nowhere blocks that target cell for the route (it is re-planned around it).
3. The last candidate (the goal) unconfirmed under pews ended the route one cell short (the streak
   needs two targets). -> a round with every candidate unconfirmed asks /where, and then the
   unnamed-walk-cursor rule applies.
4. Animated scenery (the altar's lights) made the cursor "unknown" at every hover. -> two parked
   frames; pixels that changed between them are ignored in |A - B|.
Everything else is walk@8 unchanged (scripts/walk8.py's docstring describes it).

    walk9.py --scene indoor|outdoor|guild|town|dungeon|portal --condition clean|crowd --seed S
Pixels in, input out: the rule never reads packets.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import record_session  # noqa: E402
import reloc2  # noqa: E402
import ro_agent as r  # noqa: E402
import route_plan  # noqa: E402
import rule_run as rr  # noqa: E402
import unit_gate as ug  # noqa: E402
import walk5 as w5  # noqa: E402
import walk6 as w6  # noqa: E402
import where_fix as wf  # noqa: E402

from poring_dataset import picking  # noqa: E402
from poring_env.demo import Action, DemoLog, DemoRecord, Intended, new_session_id  # noqa: E402

WALK8_RULE = "walk@11"
# The TUNING maps (walk@1-7 were all designed on these two) and the HELD-OUT maps (Batt, ~20:00:
# never used for tuning; scored separately). Held-out spots were chosen by a FIXED rule, not by eye:
# the walkable cell nearest a named anchor with >= 60 % of its +-8 square walkable.
SCENES8 = {
    "indoor": ("prt_church", 104, 122, False),
    "outdoor": ("prt_fild08", 268, 107, False),
    "guild": ("alberta_in", 60, 40, True),  # the Merchant Guild room (L3 NPC at 53,43)
    "town": ("prontera", 156, 180, True),  # NPCs; vendors only if other players
    "dungeon": ("iz_dun00", 168, 168, True),  # its own monsters respawn
    "portal": ("prt_fild08", 170, 368, True),  # the north portal (170,378) -> prontera (156,26)
}
PORTAL = {"cell": (170, 378), "to_map": "prontera", "to": (156, 26)}  # L3 warp data
PORTAL_LOAD_S = 4.0
CURSOR_REFS_V2 = r.ROOT / "data/walk6/cursor_refs_rdp_v3.npz"  # walk@11: + 72 TALK bubbles
SEG_INDOOR, SEG_OPEN = 3, 5  # click distance along the polyline (walk@6/7's lengths, unchanged)
CLICK_ALTERNATES = 4  # other click points tried when a unit covers the chosen one
ALIGN_EVERY = 4  # clicks between belief checks (only with ALIGN on)
ALIGN_PROBES = 2
ALIGN = False  # the structure-probe alignment uses reloc2's geometry, which failed relocalise@2
#                (24 / 50 WRONG): OFF in walk@8; doubt comes from direct evidence (below) instead
UNIT_SHAPES = frozenset({"sword", "talk", "pickup"})  # shapes that ARE a unit at the click point
PATIENCE_S = 6.0  # a unit's idle pause <= 5.0 s (rAthena e985006 mob.cpp:1766) + margin
WAIT_BUDGET_S = 24.0
SUBSTITUTE_RINGS = (1, 2)
UNCONFIRMED_STREAK = 2
RELOCS = 4  # walk@10 (walk@8/9: 2)
TRUST_CLICKS = 3  # walk@10: clicks a /where fix keeps the belief trusted (each must shift)
UNITS: dict[str, Any] = {"detector": None, "ms_per_cell": 400, "memory": ug.UnitMemory()}


POR_MS_PER_CELL = 400  # Poring (mob_db 1002): the crowd condition's spawn


def map_ms_per_cell(mapname: str) -> int:
    """The FASTEST walk speed (ms per cell, smaller = faster) among the species the KB says spawn on
    this map, and the Poring (the crowd spawn). data/kb is built locally (kb_build.py)."""
    spawns = json.loads((r.ROOT / "data/kb/spawns.json").read_text()).get(mapname, [])
    mobs = json.loads((r.ROOT / "data/kb/mobs.json").read_text())
    speeds = [int(mobs[str(e["id"])]["walk_speed"]) for e in spawns if str(e["id"]) in mobs]
    return min([POR_MS_PER_CELL, *speeds])


def observe(boxes: Any, w: w5.World, t_ns: int) -> None:
    """walk@11: every detection goes into the unit memory (absolute cells, the time seen)."""
    UNITS["memory"].observe(boxes, w.camera, w.gat, w.position, t_ns, UNITS["ms_per_cell"])


def scene_has_monsters(screen: Any) -> bool:
    """The HARNESS's CLEAN check (2026-10-09): any monster box on a fresh frame (the detector)."""
    det = UNITS["detector"]
    if det is None:
        return True  # no detector: clean anyway (the old behaviour), never assume an empty scene
    frame = screen.grab(*r.game_region())[1]
    return any(b.cls == "monster" for b in det.detect(frame))


def observe_frame(frame: Any, w: w5.World, t_ns: int) -> None:
    det = UNITS["detector"]
    if det is not None:
        observe(det.detect(frame), w, t_ns)


FARTHER = 4  # walk@11: points beyond seg_max, tried only after the nearer ones are refused


def farther_candidates(w: w5.World, path: Sequence[tuple[int, int]], seg_max: int,
                       band: tuple[int, int, int, int]) -> list[tuple[int, int]]:  # fmt: skip
    """walk@11 pilot 2: four Porings spawned around us made every point within seg_max fall inside a
    unit's envelope, and three routes never clicked. Batt's walk@8 rule moves a covered point along
    the polyline; these are the next FARTHER points (in the click band), after the nearer ones.
    Each passes the same picking, naming and unit checks."""
    x0, y0, x1, y1 = band
    out: list[tuple[int, int]] = []
    for i in range(seg_max + 3, min(len(path), seg_max + 3 + FARTHER)):
        u, v = w.project([path[i]])[0]
        if x0 <= u <= x1 and y0 <= v <= y1:
            out.append(path[i])
    return out


def unit_check(pr: w6.Prober, w: w5.World, u: float, v: float) -> tuple[bool, dict[str, Any]]:
    """walk@11's click-instant gate: the decision frame NOW, the detector, the envelope."""
    det = UNITS["detector"]
    if det is None:
        return False, {"why": "no_detector"}  # fail closed
    t_frame = r.ns()
    frame = pr.screen.grab(*r.game_region())[1]
    observe(det.detect(frame), w, t_frame)
    now = r.ns()
    horizon = ug.LATENCY_S + 0.05  # the click follows at once; each unit's age is added per unit
    envs = UNITS["memory"].envelopes(w.camera, w.gat, w.position, now, horizon,
                                     UNITS["ms_per_cell"])  # fmt: skip
    ok, dist, who = ug.click_clear(u, v, envs)
    info = {"units": len(envs), "min_px": None if dist == float("inf") else round(dist, 1),
            "nearest": who, "horizon_s": round(horizon + (now - t_frame) / 1e9, 3),
            "detect_ms": det.last_ms, "remembered": len(UNITS["memory"].items),
            "radii": sorted({e.radius for e in envs})}  # fmt: skip
    return ok, info


MARGIN_PX = 6.0  # walk@10 tier A: every pixel within 6 px picks the target (the model's 5 misses in
#                  485 logged clicks lay 1-5 px from its boundary); unnamed-after-fix allowed here
MARGIN_NAMED_PX = 3.0  # tier B, only when no tier-A pixel exists (the ~8 px strip behind a raised
#                        kneeler row): the chevrons must NAME the cell; never an unnamed click
CLICK_ATTEMPTS = 30
WALK = w6.WALK
MIN_MARKER_PX8 = 30  # walk@8 names a cell from >= 30 px of chevrons (rule_run: 60): pews occlude
#                      the marker (walk@4), and the 23:19 pilot read 50-54 px on clear walk cells;
#                      >= 2 chevrons and identify_cell's corner-geometry fit are still required
STALE_RETRIES = 2  # a parked frame that never went fresh: probe the same point again
ANIM_S = 0.25  # walk@9: the second parked frame, to find animated scenery
ANIM_DIFF = 60  # summed |B1 - B2| above this = an animated pixel (ignored in the cursor mask)
MOVE_FRAC = 0.15  # walk@9: after a click, at least this share of the scene band must change
MOVE_BAND = (200, 140, 1080, 560)  # client px: the scene around us, clear of the UI panels


def waypoints(start: tuple[int, int], path: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """The polyline's corners: every cell where the step direction changes, and the goal."""
    out: list[tuple[int, int]] = []
    prev, d0 = start, None
    for i, cell in enumerate(path):
        d = (cell[0] - prev[0], cell[1] - prev[1])
        if d0 is not None and d != d0:
            out.append(prev)
        d0, prev = d, cell
        if i == len(path) - 1:
            out.append(cell)
    return out


def click_candidates(w: w5.World, path: Sequence[tuple[int, int]], seg_max: int,
                     band: tuple[int, int, int, int]) -> list[tuple[int, int]]:  # fmt: skip
    """Click points along the planned polyline, best first: the farthest cell within seg_max that
    projects into the click band, then its neighbours along the path (the same run), then the next
    cells beyond (towards the next waypoint)."""
    x0, y0, x1, y1 = band

    def in_band(c: tuple[int, int]) -> bool:
        u, v = w.project([c])[0]
        return bool(x0 <= u <= x1 and y0 <= v <= y1)

    k = min(seg_max, len(path)) - 1
    while k >= 0 and not in_band(path[k]):
        k -= 1
    if k < 0:
        return []
    order = [k, k - 1, k + 1, k - 2, k + 2, k + 3]
    seen: list[tuple[int, int]] = []
    for i in order:
        if 0 <= i < len(path) and path[i] not in seen and i <= seg_max + 2 and in_band(path[i]):
            seen.append(path[i])
    return seen[: CLICK_ALTERNATES + 1]


class Prober9(w6.Prober):
    """walk@9's prober: TWO parked frames (pixels that change between them are animated scenery and
    are ignored in |A - B|), and chevrons must be NEW (green already in the parked frame is
    scenery, not the walk marker -- the 43 px that "confirmed" two targets in walk@8, route 6)."""

    def park(self) -> bool:
        ok = super().park()
        if ok:
            first = self.background
            time.sleep(ANIM_S)
            self.background = self.screen.grab(*r.game_region())[1]
            d = np.abs(self.background[..., :3].astype(int) - first[..., :3].astype(int)).sum(-1)
            self.animated = d > ANIM_DIFF
        return ok

    def read(self, u: float, v: float) -> dict[str, Any]:
        gx, gy, _, _ = r.game_region()
        px, py = gx + round(u), gy + round(v)
        b = self._crop(self.background, u, v, 32)
        anim = self._crop(self.animated[..., None].astype(np.uint8), u, v, 32)[..., 0] > 0
        bbig = self._crop(self.background, u, v, 60)
        static_green = w6.green(bbig)
        out: dict[str, Any] = {}
        big = None
        for g in range(w6.SHAPE_GRABS):
            if g:
                time.sleep(w6.SHAPE_REGRAB_S)
            big = self.screen.grab(px - 60, py - 60, 120, 120)[1][..., :3]
            a = big[28:92, 28:92]
            b_mod = np.where(anim[..., None], a, b)  # animated pixels never count as the cursor
            out = self.refs.match(a, w6.cursor_mask(a, b_mod))
            out["grabs"] = g + 1
            if out["shape"] != "unknown":
                break
        assert big is not None
        fresh = np.where(static_green[..., None], 0, big).astype(big.dtype)  # NEW green only
        comps = rr.green_components(fresh)
        out["comps"] = [(x + px - 60 - gx, y + py - 60 - gy) for x, y, _ in comps]
        out["marker_px"] = sum(n for *_, n in comps)
        out["static_green_px"] = int(static_green.sum())
        return out


def moved(before: Any, after: Any) -> tuple[bool, float]:
    """Did the scene SHIFT? The camera follows the character, so a walk changes most of the scene
    band; a click that did not walk leaves it nearly as it was (animation, the cursor)."""
    x0, y0, x1, y1 = MOVE_BAND
    a = np.asarray(before)[y0:y1, x0:x1, :3].astype(int)
    b = np.asarray(after)[y0:y1, x0:x1, :3].astype(int)
    frac = float((np.abs(a - b).sum(-1) > 60).mean())
    return frac >= MOVE_FRAC, round(frac, 3)


def named8(w: w5.World, rel: tuple[int, int], p: dict[str, Any]) -> tuple[int, int] | None:
    """walk6.named with walk@8's marker threshold (MIN_MARKER_PX8)."""
    if p["marker_px"] < MIN_MARKER_PX8 or len(p["comps"]) < rr.MIN_CHEVRONS:
        return None
    k: tuple[int, int] | None = rr.identify_cell(w.camera, w.gat, w.position, rel, p["comps"])[0]
    return k


def pick_points(w: w5.World, end: tuple[int, int]) -> tuple[list[tuple[float, float]], str]:
    """walk@10: the click points for ``end`` from the client's PICKING (poring_dataset.picking: the
    camera ray against the GAT's top surfaces), most interior first, and their tier: "A" (6 px
    margin), "B" (3 px, named clicks only) or "none" (no pixel picks the cell from here)."""
    rel = (end[0] - w.position[0], end[1] - w.position[1])
    pts = picking.safe_points(w.camera, w.gat, w.position, rel, margin=MARGIN_PX)
    if pts:
        return pts, "A"
    pts = picking.safe_points(w.camera, w.gat, w.position, rel, margin=MARGIN_NAMED_PX, grid=1.0)
    return pts, ("B" if pts else "none")


def click_step(pr: w6.Prober, w: w5.World, end: tuple[int, int],
               expect: str = WALK, accept_unnamed: bool = False) -> dict[str, Any]:  # fmt: skip
    """Probe ONLY the click point, then click. walk@10: the points come from the picking model
    (pick_points), not the projected centre -- walk@8/9 indoors clicked a centre that a raised
    kneeler's top covers on screen and walked one cell short 25 times. A point must show the WALK
    cursor and (tier B always; tier A unless the belief was just fixed) the chevrons naming the
    cell, re-checked with no motion. A neighbour named at a pick-safe point means the belief (or
    the naming) is off: no hop to the neighbour's pixel, the next point; then doubt.
    ``expect="warp"``: the click whose intent is to TAKE a portal (portal_step)."""
    if expect == "warp":
        return portal_step(pr, w, end)
    queue, tier = pick_points(w, end)
    if not queue:
        return {"clicked": False, "outcome": "no_safe_point", "target": [], "tier": tier}
    if not pr.park():
        return {"clicked": False, "outcome": "stale_background", "target": [], "tier": tier}
    observe_frame(pr.background, w, r.ns())  # walk@11: the park frame feeds the unit memory
    rel = (end[0] - w.position[0], end[1] - w.position[1])
    target: list[dict[str, Any]] = []
    neighbour = False
    for u, v in queue[: rr.MAX_HOVERS]:
        pr.hover(u, v)
        p = pr.read(u, v)
        k = named8(w, rel, p)
        target.append({"at": [round(u, 1), round(v, 1)], "shape": p["shape"], "iou": p["iou"],
                       "cell": k, "marker_px": p["marker_px"], "tier": tier})  # fmt: skip
        if p["shape"] != WALK:  # never clicked here; another point may show the walk cursor
            continue
        if k is None and accept_unnamed and tier == "A":
            # the belief was just CONFIRMED by /where and the picking model puts every pixel
            # within 6 px in the cell: the walk cursor, re-checked with no motion, is enough --
            # unknown is still no click
            again = pr.read(u, v)
            target[-1]["recheck"] = {"shape": again["shape"], "cell": None}
            if again["shape"] != WALK:
                return {"clicked": False, "outcome": f"recheck_{again['shape']}",
                        "target": target, "tier": tier}  # fmt: skip
            ok, env = unit_check(pr, w, u, v)
            target[-1]["envelope"] = env
            if not ok:
                return {"clicked": False, "outcome": "covered_unit_envelope", "target": target,
                        "tier": tier}  # fmt: skip
            gx, gy, _, _ = r.game_region()
            t_click = r.ns()
            pr.agent.click(gx + round(u), gy + round(v))
            return {"clicked": True, "outcome": "unnamed_after_fix", "target": target,
                    "at": (u, v), "t_click": t_click, "tier": tier}  # fmt: skip
        if k == (0, 0):
            again = pr.read(u, v)  # the RE-CHECK: a fresh grab, no motion
            k2 = named8(w, rel, again)
            target[-1]["recheck"] = {"shape": again["shape"], "cell": k2}
            if again["shape"] != WALK or k2 != (0, 0):
                return {"clicked": False, "outcome": f"recheck_{again['shape']}",
                        "target": target, "tier": tier}  # fmt: skip
            ok, env = unit_check(pr, w, u, v)
            target[-1]["envelope"] = env
            if not ok:
                return {"clicked": False, "outcome": "covered_unit_envelope", "target": target,
                        "tier": tier}  # fmt: skip
            gx, gy, _, _ = r.game_region()
            t_click = r.ns()
            pr.agent.click(gx + round(u), gy + round(v))
            return {"clicked": True, "outcome": "confirmed", "target": target, "at": (u, v),
                    "t_click": t_click, "tier": tier}  # fmt: skip
        if k is not None:
            neighbour = True
    if neighbour:
        return {"clicked": False, "outcome": "neighbour", "target": target, "tier": tier}
    others = [t["shape"] for t in target if t["shape"] != WALK]
    if others and len(others) == len(target):  # no point of the cell shows the walk cursor
        first = next((x for x in others if x in UNIT_SHAPES), others[0])
        return {"clicked": False, "outcome": f"covered_{first}", "target": target, "tier": tier}
    return {"clicked": False, "outcome": "unconfirmed", "target": target, "tier": tier}


def portal_step(pr: w6.Prober, w: w5.World, end: tuple[int, int]) -> dict[str, Any]:
    """The portal click: the WARP cursor at the portal cell, re-checked with no motion; click."""
    if not pr.park():
        return {"clicked": False, "outcome": "stale_background", "target": []}
    nb = np.array([(end[0] + dx, end[1] + dy) for dx, dy in rr.NB9], dtype=float)
    target: list[dict[str, Any]] = []
    for u, v in rr.in_cell_points(w.project(nb)):
        pr.hover(u, v)
        p = pr.read(u, v)
        target.append({"at": [round(u, 1), round(v, 1)], "shape": p["shape"], "iou": p["iou"]})
        if p["shape"] != "warp":
            continue
        again = pr.read(u, v)
        target[-1]["recheck"] = {"shape": again["shape"]}
        if again["shape"] != "warp":
            return {"clicked": False, "outcome": f"recheck_{again['shape']}", "target": target}
        gx, gy, _, _ = r.game_region()
        t_click = r.ns()
        pr.agent.click(gx + round(u), gy + round(v))
        return {"clicked": True, "outcome": "portal", "target": target, "at": (u, v),
                "t_click": t_click}  # fmt: skip
    return {"clicked": False, "outcome": "no_portal_cursor", "target": target}


def align(pr: w6.Prober, w: w5.World, band: tuple[int, int, int, int],
          noentry_mask: Any) -> dict[str, Any]:  # fmt: skip
    """Check the belief against the structure: up to ALIGN_PROBES probes where the believed cell's
    prediction differs from its neighbours' (reloc2.predict), most distinctive first. A probe
    that shows something else than the belief predicts = misaligned. No informative probe in
    reach (an open field) = unchecked, not failed."""
    x0, y0, x1, y1 = band
    near = reloc2.candidates(w, w.position, 1)
    cell_px = reloc2.spacing(w)
    scored: list[tuple[int, tuple[int, int], tuple[float, float]]] = []
    for o in reloc2.OFFSETS:
        u, v = w.camera.project(np.array([o], dtype=float), None)[0]
        if not (x0 <= u <= x1 and y0 <= v <= y1):
            continue
        p = (float(u), float(v))
        mine = reloc2.signature(reloc2.predict(w, w.position, o, p))
        differ = sum(reloc2.signature(reloc2.predict(w, c, o, p)) != mine for c in near)
        if differ:
            scored.append((differ, o, p))
    scored.sort(key=lambda t: -t[0])
    checks: list[dict[str, Any]] = []
    for _, o, (u, v) in scored[:ALIGN_PROBES]:
        want = reloc2.predict(w, w.position, o, (u, v))
        got = w5.probe(pr.agent, pr.screen, u, v, noentry_mask)
        kind = w5.classify(got)
        if kind == "nothing":
            ok = None  # no information
        elif want[0] == "blocked":
            ok = kind == "noentry"
        else:
            fit = reloc2.fit_px(got["comps"], want[1][1]) / cell_px
            ok = kind == "chevrons" and fit <= rr.MAX_ANCHOR_FRAC
        checks.append({"offset": list(o), "want": want[0], "saw": kind, "ok": ok})
        if ok is False:
            return {"aligned": False, "checks": checks}
    return {"aligned": True if checks else None, "checks": checks}


def where_relocalise(templates: dict[str, Any]) -> Callable[..., dict[str, Any]]:
    """The belief fix by the client's /where (where@2, 3.15): two agreeing fresh reads, inside the
    map, walkable, within 6 cells of the dead-reckoned belief; relocalise's interface. No fix ->
    not ok (never a guess)."""

    def relocalise(agent: Any, screen: Any, w: w5.World, mask: Any, band: Any) -> dict[str, Any]:
        got = wf.fix_v2(agent, screen, templates, w.position, w.walkable)
        if got["xy"] is None:
            return {"ok": False, "left": None, "rejects": got["rejects"], "method": "where"}
        old, w.position = w.position, tuple(got["xy"])
        return {"ok": True, "from": list(old), "to": list(w.position), "method": "where",
                "rejects": got["rejects"]}  # fmt: skip

    return relocalise


# The route preview (display only): since 2026-10-08 the route goes in CELLS to the live previewer
# (route_plan.py -> route_previewd.py). The one-shot screen-pixel preview is removed: it floated off
# the character as the camera scrolled (Batt). A no-op unless the run enables publishing.
preview = route_plan.preview


def substitute_goal(w: w5.World, goal: tuple[int, int],
                    blocked: set[tuple[int, int]]) -> tuple[int, int] | None:  # fmt: skip
    """The nearest free cell around a goal a UNIT occupies: ring 1, then 2; shortest plan first."""
    for ring in SUBSTITUTE_RINGS:
        best: tuple[int, tuple[int, int]] | None = None
        for dy in range(-ring, ring + 1):
            for dx in range(-ring, ring + 1):
                c = (goal[0] + dx, goal[1] + dy)
                if max(abs(dx), abs(dy)) != ring or c in blocked:
                    continue
                if not (0 <= c[1] < w.walkable.shape[0] and 0 <= c[0] < w.walkable.shape[1]):
                    continue
                if not w.walkable[c[1], c[0]]:
                    continue
                path = w6.plan(w, c, blocked)
                if path is not None and (best is None or len(path) < best[0]):
                    best = (len(path), c)
        if best is not None:
            return best[1]
    return None


def walk_route(pr: w6.Prober, w: w5.World, goal: tuple[int, int], band: tuple[int, int, int, int],
               seg_max: int, log_seg: Any, noentry_mask: Any, read_position: Any = None,
               relocalise: Callable[..., dict[str, Any]] = reloc2.relocalise,
               label: str = "walk@8", expect_goal: str = WALK,
               clock: Callable[[], float] = time.monotonic,
               fixed_at_start: bool = False) -> dict[str, Any]:  # fmt: skip
    """walk@8, ALONE, one route: plan ONCE, probe only the click point, fix the belief only when in
    doubt. ``expect_goal="warp"``: the goal is a PORTAL (the warp cursor at the click point).
    Patience ONLY for a UNIT at the click points; a substitute ONLY when a UNIT is seen on the goal
    or a click point next to it (a monster ON the goal often reads unknown: its moving sprite merges
    into the cursor mask; the packets' judge still decides whether it was justified). walk@7 waited
    on unknown reads and substituted goals nobody had taken (7 / 8)."""
    events: list[dict[str, Any]] = []
    relocs = clicks = covered = 0
    streak, streak_from = 0, None
    target, substitute = goal, None
    waited = 0.0
    unit_since: float | None = None
    fixed = fixed_at_start  # a /where fix confirmed the belief (walk@10: for TRUST_CLICKS clicks)
    trust_left = TRUST_CLICKS if fixed_at_start else 0
    blocked: set[tuple[int, int]] = set()  # walk@9: targets a click did not walk to
    fix_fresh = fixed_at_start  # walk@10: a fix confirmed the belief, nothing clicked since
    no_move: tuple[tuple[int, int], tuple[int, int]] | None = None  # (from, end) of a dead click

    def done(**kw: Any) -> dict[str, Any]:
        return {"events": events, "relocs": relocs, "clicks": clicks, "covered": covered,
                "substitute": substitute, "waited_s": round(waited, 1), **kw}  # fmt: skip

    def plan_once() -> list[tuple[int, int]] | None:
        path = w6.plan(w, target, blocked | ({goal} if substitute else set()))
        if path is not None:
            events.append({"plan": [list(c) for c in waypoints(w.position, path)], "t": r.ns()})
        return path

    def relocate(why: str) -> str | None:
        """Fix the belief and re-plan; a decline, or None to go on."""
        nonlocal relocs, path
        if relocs >= RELOCS:
            return "relocalise_limit"
        nonlocal fixed, no_move, trust_left, fix_fresh
        rl = relocalise(pr.agent, pr.screen, w, noentry_mask, band)
        relocs += 1
        events.append({"relocalise": rl, "why": why, "t": r.ns()})
        if not rl["ok"]:
            return "relocalise_failed"
        fixed = fix_fresh = True
        if no_move is not None and w.position == no_move[0]:
            blocked.add(no_move[1])  # the fix confirms it: clicking there does not walk
            events.append({"blocked": list(no_move[1]), "t": r.ns()})
        no_move = None
        trust_left = TRUST_CLICKS
        path = plan_once()
        return None if path is not None else "no_plan"

    path = plan_once()  # static structure only: units never block movement in RO
    if path is None:
        return done(decline="no_plan")
    if ALIGN:
        chk = align(pr, w, band, noentry_mask)
        events.append({"align": chk, "t": r.ns()})
        if chk["aligned"] is False and (d := relocate("align")):
            return done(decline=d)
    pending: str | None = None
    for _ in range(CLICK_ATTEMPTS):
        if read_position is not None:
            pos = read_position()
            if pos is not None and pos != w.position:
                w.position = pos  # the minimap (outdoors) corrects the belief: re-plan from it
                path = plan_once()
                if path is None:
                    return done(decline="no_plan")
        if pending is not None:
            why, pending = pending, None
            if d := relocate(why):
                return done(decline=d)
        if w.position == target:
            preview(pr.agent, w, w.position, [target], None, label)
            return done(arrived_belief=True)
        assert path is not None
        cands = click_candidates(w, path, seg_max, band) + farther_candidates(
            w, path, seg_max, band
        )
        if not cands:
            return done(decline="out_of_band")
        clicked = replanned = False
        unit_at: list[tuple[int, int]] = []
        for end in cands:
            preview(pr.agent, w, w.position, waypoints(w.position, path), end, label)
            expect = expect_goal if end == goal else WALK
            step = click_step(pr, w, end, expect, accept_unnamed=fixed)
            for _ in range(STALE_RETRIES):  # the park never went fresh: the same point again
                if step["outcome"] != "stale_background":
                    break
                step = click_step(pr, w, end, expect, accept_unnamed=fixed)
            kept = {k: v for k, v in step.items() if k != "at"}
            events.append({"from": list(w.position), "end": list(end), "t": r.ns(), **kept})
            log_seg(step.get("t_click", r.ns()), w.position, end, step)
            if step["clicked"] and expect == "warp":
                n = max(abs(end[0] - w.position[0]), abs(end[1] - w.position[1]))
                time.sleep(n * w5.STEP_S + PORTAL_LOAD_S)  # the walk in, then the other map loads
                return done(arrived_belief=True, portal=True)
            if step["clicked"]:
                n = max(abs(end[0] - w.position[0]), abs(end[1] - w.position[1]))
                frm = w.position
                w.position = end  # dead reckoning
                path = path[path.index(end) + 1 :]  # the rest of the ONE plan
                clicks += 1
                streak, streak_from = 0, None
                unit_since = None
                trust_left -= 1
                fix_fresh = False
                fixed = trust_left > 0  # walk@10: the trust lasts TRUST_CLICKS shifted clicks
                time.sleep(n * w5.STEP_S + w5.ARRIVE_S)
                clicked = True
                did_move, frac = moved(pr.background, pr.screen.grab(*r.game_region())[1])
                events[-1]["moved"] = {"shifted": did_move, "frac": frac}
                if not did_move:  # the click did not walk: doubt (and the trust ends)
                    no_move = (frm, end)
                    pending = "no_move"
                    fixed, trust_left = False, 0
                break
            shape = step["target"][-1]["shape"] if step["target"] else None
            if shape == "noentry" and w.walkable[end[1], end[0]]:
                pending = "noentry"  # a planned (GAT-walkable) cell refused: the belief is wrong
                break
            if step["outcome"] == "no_safe_point":
                continue  # walk@10: no pixel picks this cell from here: the next point at once
            if step["outcome"].startswith(("covered_", "recheck_")):
                covered += 1  # not clickable: the next point on the polyline, at once
                if shape in UNIT_SHAPES or step["outcome"] == "covered_unit_envelope":
                    unit_at.append(end)  # walk@11: a unit's envelope covers it -- a UNIT
                continue
            if step["outcome"] == "unconfirmed":
                streak = streak + 1 if streak_from == w.position else 1
                streak_from = w.position
                if streak >= UNCONFIRMED_STREAK:
                    pending = "unconfirmed"
                    break
                continue
            if step["outcome"] == "neighbour" and fix_fresh:
                # walk@10 pilot (route 3): the marker named the SAME neighbour at every pick-safe
                # point while four fixes confirmed the belief -- the model and the marker disagree
                # about this cell. Never click it; block it for the route and re-plan around it.
                if end == target:
                    return done(decline="goal_disputed")
                blocked.add(end)
                events.append({"blocked": list(end), "why": "neighbour_after_fix", "t": r.ns()})
                path = plan_once()
                if path is None:
                    return done(decline="no_plan")
                replanned = True
                break
            if step["outcome"] == "neighbour":
                pending = "neighbour"
                break
        if clicked or replanned or pending is not None:
            continue
        outcomes = [e.get("outcome") for e in events[-len(cands) :]]
        unconfirmed = [o for o in outcomes if o != "no_safe_point"]
        if not unit_at and unconfirmed and all(o == "unconfirmed" for o in unconfirmed):
            pending = "unconfirmed_round"  # walk@9: every point shows the walk cursor, none named
            continue
        if not unit_at:
            return done(decline="no_click_point")  # nothing clickable, and no unit to wait for
        now = clock()
        unit_since = now if unit_since is None else unit_since
        if now - unit_since < PATIENCE_S and waited < WAIT_BUDGET_S:
            time.sleep(0.5)  # a UNIT covers the click points: its idle pause ends within ~5 s
            waited += clock() - now
            continue
        near_goal = [c for c in unit_at if max(abs(c[0] - target[0]), abs(c[1] - target[1])) <= 1]
        if near_goal and substitute is None and expect_goal == WALK:
            sub = substitute_goal(w, goal, {goal})
            if sub is None:
                return done(decline="goal_occupied")
            substitute, target = sub, sub
            events.append({"substitute": list(sub), "for": list(goal), "t": r.ns()})
            unit_since = None
            path = plan_once()
            if path is None:
                return done(decline="no_plan")
            continue
        return done(decline="unit_stays")
    return done(decline="click_limit")


def run(scene: str, condition: str, n: int, seed: int, label: str, crowd: int,
        fix: str = "where") -> int:  # fmt: skip
    import random

    import bench

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod
    from poring_env import selfpos

    refs = w6.CursorRefs.load(CURSOR_REFS_V2)
    import unit_detector

    UNITS["detector"] = unit_detector.UnitDetector()  # fails closed: no detector, no run
    UNITS["ms_per_cell"] = map_ms_per_cell(SCENES8[scene][0])
    noentry_mask = np.load(w5.NOENTRY_MASK)
    relocalise = (where_relocalise(wf.load_templates(wf.TEMPLATES_V2)) if fix == "where"
                  else reloc2.relocalise)  # fmt: skip
    mapname, sx0, sy0, heldout = SCENES8[scene]
    portal = scene == "portal"
    gat = gatmod.parse((cam.GAT_DIR / f"{mapname}.gat").read_bytes())
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    base = cam.camera_from_json(cj["camera"])
    indoor = mapname in cam.load_indoor_table()  # the client's own table, per map
    camera = (cam.camera_for_map(base, True, cj["indoor"]["yaw_deg"], cj["indoor"]["distance"])
              if indoor else base)  # fmt: skip
    w = w5.World(camera, gat, (sx0, sy0))
    templates = selfpos.load_digit_templates()
    band = rr.ec_band()
    seg_max = SEG_INDOOR if indoor else SEG_OPEN
    rng = random.Random(seed)
    sid = new_session_id(f"{label}-{condition}-{scene}")
    log = DemoLog(sid)
    lock = record_session.read_lock(r.ROOT / "state")
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena", rule=WALK8_RULE,
              n=n, scene=scene, map=mapname, heldout=heldout, indoor_camera=indoor,
              condition=condition, crowd=crowd if condition == "crowd" else 0, seed=seed,
              detector=str(UNITS["detector"].model), unit_ms_per_cell=UNITS["ms_per_cell"],
              latency_s=ug.LATENCY_S, margin_px=ug.MARGIN_PX,
              account="gm", seg_max=seg_max, refs=len(refs.cls), fix=fix)  # fmt: skip
    print(json.dumps({"session": sid, "rule": WALK8_RULE, "scene": scene, "map": mapname,
                      "heldout": heldout, "condition": condition}), flush=True)  # fmt: skip
    t_first = r.ns()
    with r.session(f"rule:{WALK8_RULE}") as (agent, screen):
        pr = Prober9(agent, screen, refs)
        r.gm(agent, screen, f"@warp {mapname} {sx0} {sy0}")
        time.sleep(rr.SCENE_ENTRY_S)
        bench.close_chat(agent, screen)

        def read_position() -> tuple[int, int] | None:
            """The minimap readout, on any map where the client shows it (None elsewhere)."""
            xy = selfpos.read_minimap_xy(screen.grab(*r.game_region())[1][:, :, :3], templates)
            return None if xy is None else (int(xy[0]), int(xy[1]))

        def seeded_cell(near: tuple[int, int], lo: int, hi: int,
                        target: tuple[int, int] | None = None) -> Any:  # fmt: skip
            """A walkable cell near ``near``; with ``target``, one lo..hi A* steps from it."""
            for _ in range(400):
                c = (near[0] + rng.randint(-hi, hi), near[1] + rng.randint(-hi, hi))
                if not (0 <= c[1] < w.walkable.shape[0] and 0 <= c[0] < w.walkable.shape[1]):
                    continue
                if not w.walkable[c[1], c[0]]:
                    continue
                if target is None:
                    return c
                w.position = c
                path = w6.plan(w, target, set())
                if path is not None and lo <= len(path) <= hi:
                    return c
            return None

        saw_monsters = True  # the HARNESS's CLEAN condition: the first route checks the scene
        for i in range(n):
            gm_cmd = False
            # Batt 2026-10-09: @killmonster2 only when CLEAN needs it -- a monster seen in the scene
            # now, or one the previous route saw -- never 3+ identical lines in a row (the client
            # refuses the 4th, and two held-out runs then stopped on a chat input that would not
            # open). The rule's own code is untouched.
            if condition == "clean" and (saw_monsters or scene_has_monsters(screen)):
                r.gm(agent, screen, "@killmonster2")
                gm_cmd = True
            # the HARNESS: a seeded warp (every 5th route; EVERY route of the portal scene)
            if portal or i % rr.DR_WARP_EVERY == 0:
                if condition == "crowd":
                    r.gm(agent, screen, "@killmonster2")
                start_cell = (seeded_cell(PORTAL["cell"], 8, 15, PORTAL["cell"]) if portal
                              else seeded_cell((sx0, sy0), 0, 8))  # fmt: skip
                if start_cell is None:
                    raise SystemExit("the harness found no seeded start cell")
                r.gm(agent, screen, f"@warp {mapname} {start_cell[0]} {start_cell[1]}")
                time.sleep(rr.WARP_SETTLE_S)
                if heldout:
                    r.gm(agent, screen, "@heal")  # the level-1 GM among a map's own monsters
                if condition == "crowd":
                    r.gm(agent, screen, f"@monster poring {crowd}")
                    time.sleep(1.0)
                w.position = start_cell
                UNITS["memory"].reset()  # a warp: the remembered cells belong to the old spot
                gm_cmd = True
            if gm_cmd:
                bench.close_chat(agent, screen)
            r.activate_client(agent, screen)
            pos = read_position()
            start_fix: dict[str, Any] | None = None
            if pos is not None:
                w.position = pos
            elif fix == "where":  # no minimap readout here: an absolute fix at the route's start
                start_fix = relocalise(agent, screen, w, noentry_mask, band)
            if portal:
                goal: tuple[int, int] | None = PORTAL["cell"]  # type: ignore[assignment]
            else:
                here = w.position
                goal = None
                for _ in range(400):
                    g = (here[0] + rng.randint(-12, 12), here[1] + rng.randint(-12, 12))
                    if not (0 <= g[1] < w.walkable.shape[0] and 0 <= g[0] < w.walkable.shape[1]):
                        continue
                    if not w.walkable[g[1], g[0]]:
                        continue
                    path = w6.plan(w, g, set())
                    if path is not None and 8 <= len(path) <= 20:
                        goal = g
                        break
            start, t_route = w.position, r.ns()
            pre = rr.snap(log, screen, f"{i:03d}-route-before")

            def log_seg(t_click: int, frm: tuple[int, int], end: tuple[int, int],
                        step: dict[str, Any], i: int = i) -> None:  # fmt: skip
                if not step["clicked"]:
                    return
                log.append(DemoRecord(
                    session=sid, actor=f"rule:{WALK8_RULE}", t_mono_ns=t_click, t_done_ns=r.ns(),
                    rule=f"{WALK8_RULE}/click", scene=f"{scene}:{mapname}",
                    cue="walk@8 click: only the click point probed; the record's time is the CLICK",
                    action=Action(type="walk", points=[step["at"]],
                                  intended=Intended(kind="cell", cell=end, relative=False,
                                                    note=f"route {i} believed {frm[0]},{frm[1]}")),
                    outcome={"status": "pending", "evidence": {  # type: ignore[arg-type]
                        "target": step["target"], "believed_position": list(frm),
                        "portal": step["outcome"] == "portal"}},
                ))  # fmt: skip

            if goal is None:
                did: dict[str, Any] = {"decline": "no_goal", "events": [], "relocs": 0,
                                       "clicks": 0, "covered": 0}  # fmt: skip
            else:
                did = walk_route(pr, w, goal, band, seg_max, log_seg, noentry_mask, read_position,
                                 relocalise=relocalise, label=f"walk@8 {scene} route {i}",
                                 expect_goal="warp" if portal else WALK,
                                 fixed_at_start=bool(start_fix and start_fix["ok"]))  # fmt: skip
            saw_monsters = any(it.cls == "monster" for it in UNITS["memory"].items)
            judged = PORTAL["to"] if portal else goal  # a portal route ends on the OTHER map
            extra: dict[str, Any] = (
                {"to_map": PORTAL["to_map"], "portal": list(PORTAL["cell"])} if portal else {}
            )
            if start_fix is not None:
                extra["start_fix"] = start_fix
            log.append(DemoRecord(
                session=sid, actor=f"rule:{WALK8_RULE}", t_mono_ns=t_route, t_done_ns=r.ns(),
                frame=pre, rule=WALK8_RULE, scene=f"{scene}:{mapname}",
                cue="walk@8 route: plan once, check the belief, probe only the click point",
                action=Action(type="walk", intended=Intended(
                    kind="route", cell=judged or start, relative=False,
                    note=f"route {i} from believed {start[0]},{start[1]}")),
                outcome={"status": "pending", "evidence": {  # type: ignore[arg-type]
                    "start_believed": list(start), "goal": list(judged) if judged else None,
                    "end_believed": list(w.position), **extra, **did}},
            ))  # fmt: skip
            print(json.dumps({"route": i, "start": list(start), "goal": judged,
                              "end_believed": list(w.position), "decline": did.get("decline"),
                              "clicks": did["clicks"], "covered": did["covered"],
                              "relocs": did["relocs"], "portal": did.get("portal")}),
                  flush=True)  # fmt: skip
            if portal and did.get("portal"):
                bench.close_chat(agent, screen)  # back to the field: the next route warps there
            time.sleep(0.5)
        r.gm(agent, screen, "@killmonster2")
        bench.close_chat(agent, screen)
    events, anchor = record_session.write_packets(log.dir, t_first, r.ns())
    UNITS["detector"].close()
    log.finish(packet_events=len(events), packet_anchor=anchor, routes=n)
    print(json.dumps({"session": sid, "packet_events": len(events), "routes": n}), flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--scene", choices=sorted(SCENES8), required=True)
    ap.add_argument("--condition", choices=("clean", "crowd"), required=True)
    ap.add_argument("--n", type=int, default=56)
    ap.add_argument("--seed", type=int, default=20261018)
    ap.add_argument("--label", default="walk8-alone")
    ap.add_argument("--crowd", type=int, default=4)
    ap.add_argument(
        "--fix",
        choices=("where", "v2"),
        default="where",
        help="the belief fix: /where (where@1) or re-localisation v2",
    )
    a = ap.parse_args()
    for p in (CURSOR_REFS_V2, w5.NOENTRY_MASK):
        if not p.exists():
            raise SystemExit(f"{p} missing: run the cursor calibrations (design time)")
    return run(a.scene, a.condition, a.n, a.seed, a.label, a.crowd, a.fix)


if __name__ == "__main__":
    sys.exit(main())
