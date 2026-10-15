#!/usr/bin/env python3
"""anim-region@1: a map's measured ANIMATED region, in cells (Batt 2026-10-15, decision 3: "don't
read through moving scenery, AVOID it. The walk rule (and any hover/click planner) never picks a
point inside a measured per-map ANIMATED region"; docs/demonstrations.md 3.32 amendment 3).

    anim_region.py plan    [--map M] [--step 8]        offline: the scope's stands and the time
    anim_region.py measure --map M [--step 8]          LIVE (RDP, the GM, ASSIST): pass 1, its
                       [--refine-step 3 --radius 12]     rechecks, pass 2 around animated views
    anim_region.py build   --map M --session SID ...   offline: packets audit -> the region file
    anim_region.py show    --map M                     the saved region's counts

MEASURE (live; only `@warp` lines are typed, through the UI gate and the typing guard):
- Stands, pass 1: a lattice every STEP cells over the map's stand cells: walkable in BOTH the
  client's GAT and the server's map cache (decision 4), outside every L3 warp span and script-NPC
  touch area (npc_click_test's three checks). A lattice point that fails moves to the nearest
  passing cell within MOVE_WITHIN cells, else it is dropped (both logged).
- Per stand: @warp, the harness's settle (rule_run: 2.5 s, 7 s for the first warp onto the map), the
  cursor parked by two motions at PARK, then cursor@3's measurement unchanged (cursor_anim.measure:
  13 grabs 0.2 s apart; a pixel differing from the first grab by > 60 summed BGR in any later grab,
  grown 2 px). The view's UI windows are located on its first grab (poring_env.ui_anchors).
- A view whose EXCLUDED mask (below) keeps any animated pixel is measured AGAIN >= RECHECK_S later
  (transients: only pixels animated in BOTH count). A view more than UNSETTLED_SHARE animated is
  re-measured once after a further settle, else logged "unsettled" and not used.
- Pass 2: a lattice every REFINE_STEP cells within RADIUS cells of every pass-1 stand whose view
  kept confirmed animated pixels, measured the same way.
- Everything is saved in the session (RAM, /dev/shm/poring-lab-demo/<sid>): one demo record per
  measurement and its full-view mask (views/*.npz). Packets are never read here.

BUILD (offline):
- POSITION AUDIT from the session's packets: a measurement counts only when the GM's last position
  (map_change / own position) before it equals its stand; any other view is dropped and listed.
- Excluded pixels: the GM's own sprite box around the stand's projected feet (SELF_*), the parked
  cursor's box (PARK_HALF), every located UI window (+ UI_MARGIN), pixels that pick no map cell.
- Each counted pixel (a STRIDE grid) -> the cell the client picks there (poring_dataset.picking with
  the view's camera). The region = the UNION over views, grown by GROW_CELLS (8-neighbour).
- Written to data/kb/anim_regions/<map>.json (gitignored: derived from client pixels) with the
  sessions, the stands, per-view counts and this tool's commit.

Client pixels stay in RAM and data/ (never committed).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
RULE = "anim-region@1"
STEP = 8  # pass-1 lattice (3.32 amendment 3)
MOVE_WITHIN = 3  # a failing lattice point moves at most this far (Chebyshev), else dropped
REFINE_STEP, RADIUS = 3, 12  # pass 2 around views that kept animation
RECHECK_S = 60.0  # the second measurement of an animated view comes at least this much later
UNSETTLED_SHARE = 0.5  # more of the view animated than this = the warp has not settled
GROW_CELLS = 1
STRIDE = 2  # back-projection samples every STRIDE-th pixel (a cell is ~30 px across)
PARK = (1250, 380)  # client-area px: talk1 / walk6's rest point (right of the dialog)
PARK_HALF = 40  # the parked cursor animates too (the WALK arrow turns): its box is excluded
SELF_HALF_W, SELF_UP, SELF_DOWN = 32, 120, 16  # the GM's own sprite around its projected feet
UI_MARGIN = 4
# MEASURED 2026-10-15 on prt_church: 16.1 s per stand without the window locate (37 stands), 19.9
# s with it (session 20261015T173259, 39 stands, 18.6-20.2): the @warp line through the UI gate
# and the typing guard, the settle, the park, 13 grabs, then ~3.3 s of window template matching
SECONDS_PER_STAND = 19.9
# The GM's fixed state always shows these (gm_state): a view that locates either one NOT is a UI
# the exclusion cannot see, so the run stops for a person (fail closed; 2026-10-15, the prt_church
# session 20261015T171004 located no window at all: the registry had no templates).
ALWAYS_WINDOWS = ("basic_info", "chat")
# A window's EXCLUDED box is the window as drawn. The registry's basic_info anchor is its top
# 220 x 140; the GM's fixed state shows it with the menu expanded below (the 4 x 5 icon panel,
# measured to client x 218 / y 326 on 2026-10-15's prt_church frames), and an icon there blinks
# (the inventory bag after new items): the stopped prt_church session shows it in every view.
DRAWN_SIZE = {"basic_info": (220, 328)}
OUT_DIR = ROOT / "data" / "kb" / "anim_regions"
KB_FIRST_WORKFLOW = ROOT / "data" / "kb" / "first_workflow.json"
Cell = tuple[int, int]

# THE SCOPE (Batt 2026-10-15, amending 3.32 amendment 3 before any measurement): "scope each map to
# the FIRST WORKFLOW's areas (training grounds' 4 layouts, the route to alberta/alberta_in,
# prontera's and geffen/geffen_in's delivery paths) plus prt_church and prt_fild08's tuning areas;
# clicks outside a measured area are refused (fail closed)".
TUNING_ANCHORS: dict[str, Cell] = {"prt_church": (104, 122), "prt_fild08": (268, 107)}  # SCENES8
# walk@11's harness: a warp start within +-8 of the anchor every 5th route, the 4 routes between
# start where the last ended, each goal within +-12 of its start: 8 + 5 x 12 = 68 cells of reach.
TUNING_REACH = 68
CORRIDOR = 6  # cells around a workflow route's path cells where stands are placed
COVER_STRIDE = 8  # px: the measured-AREA sample grid of a view (a cell is ~30 px across)


# --- pure parts (tested) ------------------------------------------------------------------------


def lattice(ok: Any, step: int = STEP, move_within: int = MOVE_WITHIN,
            origin: tuple[int, int] | None = None,
            bounds: tuple[int, int, int, int] | None = None,
            where: Any = None) -> dict[str, list[Any]]:  # fmt: skip
    """Lattice points every ``step`` cells (first at step // 2, or aligned to ``origin``) inside
    ``bounds`` (x0, y0, x1, y1, exclusive ends; default the whole grid) and, when given, on
    ``where`` cells. A point on an ``ok`` cell is a stand; otherwise the nearest ok cell within
    ``move_within`` (Chebyshev; ties by y, x) is, and the point is listed as moved; with none it is
    dropped. Stands are unique, in scan order."""
    grid = np.asarray(ok, dtype=bool)
    h, w = grid.shape
    x0, y0, x1, y1 = bounds or (0, 0, w, h)
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    ox, oy = origin if origin is not None else (step // 2, step // 2)
    xs = [x for x in range(x0, x1) if (x - ox) % step == 0]
    ys = [y for y in range(y0, y1) if (y - oy) % step == 0]
    stands: list[Cell] = []
    seen: set[Cell] = set()
    moved: list[list[Cell]] = []
    dropped: list[Cell] = []
    for y in ys:
        for x in xs:
            if where is not None and not where[y, x]:
                continue
            got = _nearest_ok(grid, x, y, move_within)
            if got is None:
                dropped.append((x, y))
                continue
            if got != (x, y):
                moved.append([(x, y), got])
            if got not in seen:
                seen.add(got)
                stands.append(got)
    return {"stands": stands, "moved": moved, "dropped": dropped}


def _nearest_ok(grid: Any, x: int, y: int, within: int) -> Cell | None:
    h, w = grid.shape
    for r in range(within + 1):
        ring = [(cy, cx) for cy in range(y - r, y + r + 1) for cx in range(x - r, x + r + 1)
                if max(abs(cx - x), abs(cy - y)) == r]  # fmt: skip
        for cy, cx in sorted(ring):
            if 0 <= cx < w and 0 <= cy < h and grid[cy, cx]:
                return (cx, cy)
    return None


def refine_stands(around: Iterable[Cell], ok: Any, done: Iterable[Cell],
                  step: int = REFINE_STEP, radius: int = RADIUS,
                  move_within: int = MOVE_WITHIN,
                  origin: tuple[int, int] = (STEP // 2, STEP // 2)) -> list[Cell]:  # fmt: skip
    """Pass 2: ONE lattice every ``step`` cells, aligned to ``origin`` for the whole map, over
    the union of the squares within ``radius`` of each stand in ``around``, on ``ok`` cells (the
    caller passes the scope's), minus the stands already measured. Unique, in scan order.
    (Amendment 3c, 2026-10-15: a lattice aligned to EACH stand never merged where the squares
    overlap, so prt_church's pass 2 came to 851 stands; and it left the scope.)"""
    grid = np.asarray(ok, dtype=bool)
    h, w = grid.shape
    area = np.zeros_like(grid)
    for sx, sy in around:
        area[max(0, sy - radius) : min(h, sy + radius + 1),
             max(0, sx - radius) : min(w, sx + radius + 1)] = True  # fmt: skip
    if not area.any():
        return []
    seen = set(done)  # the squares choose the POINTS; a point moves only onto an ok cell
    got = lattice(grid, step, move_within, origin=origin, where=area)["stands"]
    return [c for c in got if c not in seen]


def exclusion(shape: tuple[int, int], feet: tuple[float, float] | None,
              windows: Mapping[str, Sequence[int]], sizes: Mapping[str, Sequence[int]],
              park: tuple[int, int] = PARK) -> Any:  # fmt: skip
    """True where a view's pixels never count: the GM's own sprite box around its projected feet,
    the parked cursor's box, and every located UI window (origin + size, + UI_MARGIN)."""
    h, w = shape
    ex = np.zeros((h, w), dtype=bool)

    def box(x0: float, y0: float, x1: float, y1: float) -> None:
        a, b = max(0, int(np.floor(x0))), max(0, int(np.floor(y0)))
        c, d = min(w, int(np.ceil(x1))), min(h, int(np.ceil(y1)))
        if a < c and b < d:
            ex[b:d, a:c] = True

    if feet is not None:
        fu, fv = feet
        box(fu - SELF_HALF_W, fv - SELF_UP, fu + SELF_HALF_W + 1, fv + SELF_DOWN + 1)
    box(park[0] - PARK_HALF, park[1] - PARK_HALF, park[0] + PARK_HALF + 1, park[1] + PARK_HALF + 1)
    for name, (ox, oy) in windows.items():
        sw, sh = sizes.get(name, (0, 0))
        box(ox - UI_MARGIN, oy - UI_MARGIN, ox + sw + UI_MARGIN, oy + sh + UI_MARGIN)
    return ex


def windows_missing(found: Mapping[str, Any], names: Iterable[str] = ALWAYS_WINDOWS) -> list[str]:
    """The always-open windows a view did not locate (or a registry has no template for);
    [] = the exclusion sees them all."""
    return [n for n in names if n not in found]


def unconfirmed(masks: Sequence[Any]) -> bool:
    """A stand measured ONCE whose view kept counted pixels: its recheck never ran, so it can
    neither confirm animation nor count as measured (build drops it; fail closed)."""
    return len(masks) == 1 and bool(np.asarray(masks[0]).any())


def counted(mask: Any, excl: Any) -> Any:
    return np.asarray(mask, dtype=bool) & ~np.asarray(excl, dtype=bool)


def view_cells(mask: Any, pick: Callable[[Any], Any], stand: Cell,
               stride: int = STRIDE) -> set[Cell]:  # fmt: skip
    """The cells the client picks under the counted pixels of one view, sampled every ``stride``
    pixels. ``pick``: client pixels (N, 2) -> cell OFFSETS from ``stand`` (N, 2), NONE for none
    (poring_dataset.picking.pick_cells with the view's camera and the map's GAT)."""
    from poring_dataset.picking import NONE

    m = np.asarray(mask, dtype=bool)
    sub = np.zeros_like(m)
    sub[::stride, ::stride] = m[::stride, ::stride]
    ys, xs = np.nonzero(sub)
    if len(xs) == 0:
        return set()
    rel = np.asarray(pick(np.c_[xs, ys].astype(float)))
    hit = rel[:, 0] != NONE
    return {(int(stand[0] + dx), int(stand[1] + dy)) for dx, dy in rel[hit]}


def coverage(pick: Callable[[Any], Any], stand: Cell, excl: Any,
             stride: int = COVER_STRIDE) -> set[Cell]:  # fmt: skip
    """The view's MEASURED cells: those the client picks anywhere in the view's counted pixels
    (every pixel not excluded), sampled every ``stride`` pixels. A click is judged only on a
    cell some measured view saw."""
    return view_cells(~np.asarray(excl, dtype=bool), pick, stand, stride)


def scope_mask(shape: tuple[int, int], *, anchors: Iterable[Cell] = (), reach: int = TUNING_REACH,
               route: Iterable[Cell] = (), corridor: int = CORRIDOR,
               whole: bool = False) -> Any:  # fmt: skip
    """The cells a map's stands are drawn in: the whole map, or the union of a box of ``reach``
    around each tuning anchor and ``corridor`` cells around each route path cell."""
    h, w = shape
    m = np.full((h, w), whole, dtype=bool)
    for ax, ay in anchors:
        m[max(0, ay - reach) : ay + reach + 1, max(0, ax - reach) : ax + reach + 1] = True
    for x, y in route:
        m[max(0, y - corridor) : y + corridor + 1, max(0, x - corridor) : x + corridor + 1] = True
    return m


def grow_cells(cells: Iterable[Cell], n: int = GROW_CELLS) -> set[Cell]:
    out = set(cells)
    for _ in range(n):
        out |= {(x + dx, y + dy) for x, y in out for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
    return out


def region_of(views: Mapping[Cell, Iterable[Cell]], grow: int = GROW_CELLS) -> set[Cell]:
    """The map's region: the union of the views' animated cells, grown by ``grow``."""
    base: set[Cell] = set()
    for cells in views.values():
        base |= set(cells)
    return grow_cells(base, grow)


def audit_positions(measures: Sequence[Mapping[str, Any]],
                    positions: Sequence[tuple[int, str, int, int]]) -> dict[int, str]:  # fmt: skip
    """{measure index: why it is dropped} for measurements whose GM position is not their stand.
    ``measures``: dicts with "t0" (ns) and "stand"; ``positions``: (t ns, map, x, y) from the
    session's packets, in time order. The position that counts is the last one before t0."""
    bad: dict[int, str] = {}
    times = [p[0] for p in positions]
    for i, m in enumerate(measures):
        k = int(np.searchsorted(times, int(m["t0"]), side="right")) - 1
        if k < 0:
            bad[i] = "no position before it"
            continue
        _, mp, x, y = positions[k]
        if (x, y) != tuple(m["stand"]) or (m.get("map") and mp.removesuffix(".gat") != m["map"]):
            bad[i] = f"GM at {mp} ({x},{y}), stand {tuple(m['stand'])}"
    return bad


# --- live -----------------------------------------------------------------------------------------


def stand_grid(map_name: str, gat: Any) -> Any:
    """The cells a stand may use: client ∩ server walkable, outside every L3 warp span and script
    NPC touch area. Fails closed when any source lacks the map."""
    import npc_click_test as t

    from poring_dataset import walkable as wk

    _, both = wk.load_both(map_name)
    ok = np.array(both, dtype=bool)
    warps = t.load_warps(map_name)
    touch = t.load_touch_areas(map_name)
    if warps is None or touch is None:
        raise SystemExit(f"L3 does not cover {map_name}'s warps / touch areas: refused")
    for a in [*warps, *touch]:
        x, y, sx, sy = int(a["x"]), int(a["y"]), int(a["span_x"]), int(a["span_y"])
        ok[max(0, y - sy) : y + sy + 1, max(0, x - sx) : x + sx + 1] = False
    return ok


class _BothGrid:
    """A ``nopass`` view of client ∩ server walkability (decision 4) for npc_sprites' paths."""

    def __init__(self, mask: Any) -> None:
        self.m = np.asarray(mask, dtype=bool)

    def nopass(self, x: int, y: int) -> bool:
        h, w = self.m.shape
        return not (0 <= x < w and 0 <= y < h and bool(self.m[y, x]))


def workflow_routes(kb: Path = KB_FIRST_WORKFLOW) -> tuple[dict[str, set[Cell]], list[str]]:
    """{map: path cells} of the first workflow's Merchant round trips to its two supported
    destinations (npc_sprites.DESTS: prontera, geffen_in): the graduation arrival in alberta_in,
    the job changer, the storehouse, the KB's walk_kafra legs (alberta, the Kafra hops) to the
    destination NPC and back. Shortest 8-neighbour paths (npc_sprites.route_cells) on client ∩
    server walkability. A map either source lacks is a problem (listed), never guessed."""
    import npc_sprites as ns

    from poring_dataset import walkable as wk

    doc = json.loads(kb.read_text())
    out: dict[str, set[Cell]] = {}
    problems: list[str] = []
    grids: dict[str, Any] = {}
    for dest in ns.DESTS:
        stops = ns.route_stops(doc, dest)
        for m in {s["map"] for s in stops}:
            if m not in grids:
                try:
                    grids[m] = _BothGrid(wk.load_both(m)[1])
                except wk.MapSourceError as exc:
                    problems.append(str(exc))
        cells, why = ns.route_cells(stops, grids)
        problems += [f"{dest}: {w}" for w in why]
        for m, c in cells.items():
            out.setdefault(m, set()).update(c)
    return out, problems


def clone_groups(kb: Path = KB_FIRST_WORKFLOW) -> dict[str, list[str]]:
    """{representative: its group's maps}: the training grounds' 4 layouts (the KB's clone groups,
    identical cells; the copies' RSW/GND/textures were checked identical in map prep, 748260d).
    The representative (the group's first map by name) is measured; its region serves the group."""
    doc = json.loads(kb.read_text())
    return {sorted(g["maps"])[0]: sorted(g["maps"]) for g in doc["clone_groups"]}


def scope_for(map_name: str, shape: tuple[int, int],
              routes: Mapping[str, set[Cell]] | None = None) -> tuple[Any, list[str]]:  # fmt: skip
    """(the map's scope mask, why): a clone-group representative is whole; a tuning map gets its
    anchors' boxes; a workflow map its route corridor. A map with none of these is OUT of scope:
    an empty mask (its clicks are all refused until a pre-registration measures it)."""
    why: list[str] = []
    whole = map_name in clone_groups()
    if whole:
        why.append("training-grounds layout (whole map)")
    anchors = [TUNING_ANCHORS[map_name]] if map_name in TUNING_ANCHORS else []
    if anchors:
        why.append(f"tuning area +-{TUNING_REACH} of {anchors[0]}")
    route = sorted((routes or {}).get(map_name, set()))
    if route:
        why.append(f"workflow route corridor +-{CORRIDOR} ({len(route)} path cells)")
    return scope_mask(shape, anchors=anchors, route=route, whole=whole), why


def scoped_maps(routes: Mapping[str, set[Cell]]) -> list[str]:
    return sorted({*clone_groups(), *TUNING_ANCHORS, *routes})


def plan(map_name: str, step: int, routes: Mapping[str, set[Cell]] | None = None) -> dict[str, Any]:
    import npc_click_score as ncs

    if routes is None:
        routes, _ = workflow_routes()
    _, gat = ncs.load_map(map_name)
    ok = stand_grid(map_name, gat)
    sc, why = scope_for(map_name, ok.shape, routes)
    lat = lattice(ok & sc, step)
    n = len(lat["stands"])
    return {"map": map_name, "scope": why, "scope_cells": int((ok & sc).sum()), "step": step,
            "stands": n, "moved": len(lat["moved"]),
            "est_minutes_pass1": round(n * SECONDS_PER_STAND / 60, 1)}  # fmt: skip


def measure(map_name: str, step: int, refine_step: int, radius: int,
            pass2_from: str | None = None, max_pass2: int | None = None) -> int:  # fmt: skip
    import bench
    import cursor_anim as ca
    import npc_click_score as ncs
    import npc_click_test as t
    import record_session
    import ro_agent as r
    import rule_run as rr
    import talk1
    import ui_gate as ug

    from poring_env import npc_dialog as nd
    from poring_env.demo import Action, DemoLog, DemoRecord, Intended, Outcome, new_session_id

    camera, gat = ncs.load_map(map_name)
    ok = stand_grid(map_name, gat)
    if any(map_name in g and map_name != rep for rep, g in clone_groups().items()):
        raise SystemExit(f"{map_name} is a clone-group copy: measure its representative")
    routes, problems = workflow_routes()
    sc, why = scope_for(map_name, ok.shape, routes)
    if not sc.any():
        raise SystemExit(f"{map_name} is outside the pre-registered scope: refused")
    lat = lattice(ok & sc, step)
    src: tuple[list[Cell], list[Cell]] | None = None
    if pass2_from is not None:  # amendment 3c: pass 2 from an earlier session's complete pass 1
        from poring_env.demo import DEMO_ROOT

        src_dir = DEMO_ROOT / pass2_from
        if json.loads((src_dir / "manifest.json").read_text()).get("map") != map_name:
            raise SystemExit(f"{pass2_from} is not a {map_name} measurement")
        src = pass1_from(src_dir)
        views = [v for v in _views(src_dir) if v["phase"] == "pass1"]
        again = {tuple(v["stand"]) for v in _views(src_dir) if v["phase"] == "pass1-recheck"}
        if missing := [v["stand"] for v in views if not v["unsettled"] and v["counted"].any()
                       and tuple(v["stand"]) not in again]:  # fmt: skip
            raise SystemExit(f"{pass2_from}'s pass 1 is incomplete (no recheck at {missing[:5]})")
    # the UI gate's template set for the lock's path (rdp / a proven s2): a registry WITHOUT
    # templates locates nothing, and the window exclusion would silently be off
    reg = ug._registry(ug._require_ready())
    if lost := windows_missing(reg.templates):
        raise SystemExit(f"no window template for {lost}: the UI exclusion cannot run")
    sizes = window_sizes(reg.windows)
    sid = new_session_id(f"anim-region-{map_name}")
    log = DemoLog(sid)
    (log.dir / "views").mkdir(exist_ok=True)
    log.start(rule=RULE, map=map_name, step=step, refine_step=refine_step, radius=radius,
              scope=why, route_problems=problems, stands=len(lat["stands"]), moved=lat["moved"],
              dropped=lat["dropped"], commit=_commit(), park=list(PARK),
              pass2_from=pass2_from, max_pass2=max_pass2)  # fmt: skip
    t_first = r.ns()
    templates = nd.load_templates(talk1.TEMPLATES)
    ended, code, k = "complete", 0, 0
    here: Cell | None = None
    first = True
    with r.session(f"rule:{RULE}") as (agent, screen):
        io = talk1.LiveIo(agent, screen, templates)
        if (why := t._ui_clear(io)) != "none":
            raise SystemExit(f"the client's UI is not clear before the run ({why}): a person first")

        def grab() -> Any:
            return screen.grab(*r.game_region())[1]

        def park() -> None:
            gx, gy, _, _ = r.game_region()
            agent.move(gx + PARK[0] - rr.HOVER_APPROACH_PX, gy + PARK[1] - rr.HOVER_APPROACH_PX)
            time.sleep(rr.HOVER_APPROACH_S)
            agent.move(gx + PARK[0], gy + PARK[1])
            time.sleep(0.8)  # the client draws its cursor ~0.4-0.8 s after the second motion

        def one(stand: Cell, phase: str) -> dict[str, Any]:
            nonlocal here, first, k
            if here != stand:
                r.gm(agent, screen, f"@warp {map_name} {stand[0]} {stand[1]}")
                time.sleep(rr.SCENE_ENTRY_S if first else rr.WARP_SETTLE_S)
                bench.close_chat(agent, screen)
                r.activate_client(agent, screen)
                here, first = stand, False
            tries = []
            for _ in range(2):
                park()
                t0 = r.ns()
                mask, frames = ca.measure(grab)
                windows = reg.locate(np.ascontiguousarray(frames[0][..., :3]))
                if lost := windows_missing(windows):
                    raise SystemExit(f"view at {stand}: {lost} not located, the UI exclusion "
                                     "would miss it: a person first")  # fmt: skip
                feet = tuple(float(v) for v in ncs.project_feet(camera, gat, stand, [stand])[0])
                cnt = counted(mask, exclusion(mask.shape, feet, windows, sizes))
                share = float(np.asarray(mask).mean())
                tries.append(round(share, 4))
                if share <= UNSETTLED_SHARE:
                    break
                time.sleep(rr.WARP_SETTLE_S)
            name = f"views/{k:05d}.npz"
            np.savez_compressed(log.dir / name, mask=np.packbits(np.asarray(mask, dtype=bool)),
                                shape=np.array(mask.shape))  # fmt: skip
            k += 1
            ev = {"stand": list(stand), "phase": phase, "view": name, "t0": t0,
                  "windows": {n: list(o) for n, o in windows.items()}, "feet": list(feet),
                  "share": tries[-1], "tries": tries, "counted_px": int(cnt.sum()),
                  "unsettled": tries[-1] > UNSETTLED_SHARE}  # fmt: skip
            log.append(DemoRecord(
                session=sid, actor=f"rule:{RULE}", t_mono_ns=t0, t_done_ns=r.ns(),
                action=Action(type="other", points=[],
                              intended=Intended(kind="cell", cell=stand, note=phase)),
                cue="anim-region: the cursor parked, 13 grabs", rule=RULE,
                scene=f"map:{map_name}", outcome=Outcome(evidence=ev)))  # fmt: skip
            return {**ev, "mask": np.asarray(mask, dtype=bool), "counted": cnt}

        try:
            if src is None:
                first_pass: dict[Cell, dict[str, Any]] = {}
                for s in lat["stands"]:
                    first_pass[s] = one(tuple(s), "pass1")
                confirmed = _recheck(first_pass, one, "pass1-recheck")
                done, keep = list(first_pass), [s for s, m in confirmed.items() if m.any()]
                views = first_pass.values()
                stats = {"pass1": len(first_pass),
                         "unsettled": sum(bool(v["unsettled"]) for v in views),
                         "rechecked": sum(not v["unsettled"] and bool(v["counted"].any())
                                          for v in views)}  # fmt: skip
            else:
                done, keep = src
                stats = {"pass1_from": pass2_from, "pass1": len(done)}
            # pass 2 stays inside the scope (amendment 3c), one lattice for the map
            more = refine_stands(keep, ok & sc, done, refine_step, radius)
            # amendment 3a: the pass-2 count is reported after pass 1, BEFORE pass 2 runs
            print(json.dumps({"map": map_name, **stats, "kept": len(keep), "pass2": len(more),
                              "est_minutes": round(len(more) * SECONDS_PER_STAND / 60, 1)}),
                  flush=True)  # fmt: skip
            if max_pass2 is not None and len(more) > max_pass2:
                ended = f"complete:pass1_only (pass 2 = {len(more)} stands > {max_pass2})"
                more = []
            second: dict[Cell, dict[str, Any]] = {}
            for s in more:
                second[s] = one(s, "pass2")
            _recheck(second, one, "pass2-recheck")
        except BaseException as exc:  # a stop inside a step (the UI gate) is never "complete"
            ended, code = f"stopped:{type(exc).__name__}: {str(exc)[:160]}", 3
            raise
        finally:
            events, anchor = record_session.write_packets(log.dir, t_first, r.ns())
            log.finish(ended=ended, packet_events=len(events), packet_anchor=anchor)
    print(json.dumps({"session": sid, "ended": ended}))
    return code


def _views(session_dir: Path) -> list[dict[str, Any]]:
    """A session's measurements (evidence + its counted pixels, recomputed exactly as live)."""
    recs = [json.loads(x) for x in (session_dir / "demo.jsonl").read_text().splitlines() if x]
    out = []
    sizes = _sizes()
    for r in recs:
        if r.get("rule") != RULE:
            continue
        m = r["outcome"]["evidence"]
        z = np.load(session_dir / m["view"])
        shape = tuple(int(v) for v in z["shape"])
        mask = np.unpackbits(z["mask"])[: shape[0] * shape[1]].reshape(shape).astype(bool)
        excl = exclusion(shape, tuple(m["feet"]), m["windows"], sizes)
        out.append({**m, "counted": counted(mask, excl), "excl": excl})
    return out


def pass1_from(session_dir: Path) -> tuple[list[Cell], list[Cell]]:
    """(the pass-1 stands, the KEPT ones) of an earlier session: a settled pass-1 view whose
    counted pixels survive its pass1-recheck (the same rule as the live run's _recheck)."""
    views = _views(session_dir)
    first = {tuple(v["stand"]): v for v in views if v["phase"] == "pass1"}
    again = {tuple(v["stand"]): v for v in views if v["phase"] == "pass1-recheck"}
    kept = [s for s, v in first.items() if not v["unsettled"] and s in again
            and bool((v["counted"] & again[s]["counted"]).any())]  # fmt: skip
    return list(first), kept


def _recheck(views: Mapping[Cell, Mapping[str, Any]], one: Callable[[Cell, str], dict[str, Any]],
             phase: str) -> dict[Cell, Any]:  # fmt: skip
    """The second measurement of every settled view that kept counted pixels, each >= RECHECK_S
    after its first; returns {stand: the pixels counted in BOTH}."""
    out: dict[Cell, Any] = {}
    for s, v in views.items():
        if v["unsettled"] or not v["counted"].any():
            out[s] = np.zeros_like(v["counted"])
            continue
        wait = RECHECK_S - (time.monotonic_ns() - int(v["t0"])) / 1e9
        if wait > 0:
            time.sleep(wait)
        again = one(s, phase)
        out[s] = v["counted"] & again["counted"]
    return out


def _commit() -> str:
    try:
        cmd = ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"]
        return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


# --- build (offline) ------------------------------------------------------------------------------


def _positions(session_dir: Path) -> list[tuple[int, str, int, int]]:
    """(t ns, map, x, y) of the GM from the session's packets: map_change and own position."""
    import gzip

    out = []
    with gzip.open(session_dir / "packets.jsonl.gz", "rt") as fh:
        for line in fh:
            e = json.loads(line)
            if e.get("type") == "map_change" and e.get("x") is not None:
                out.append((int(e["t_mono_ns"]), str(e.get("map", "")), int(e["x"]), int(e["y"])))
    return sorted(out)


def build(map_name: str, sessions: Sequence[str], out_dir: Path = OUT_DIR) -> dict[str, Any]:
    import npc_click_score as ncs

    from poring_dataset.picking import pick_cells
    from poring_env.demo import DEMO_ROOT

    camera, gat = ncs.load_map(map_name)
    by_stand: dict[Cell, list[Any]] = {}
    excls: dict[Cell, list[Any]] = {}
    where: dict[Cell, list[dict[str, str]]] = {}
    measured: set[Cell] = set()
    dropped: list[dict[str, Any]] = []
    for sid in sessions:
        d = DEMO_ROOT / sid
        recs = [json.loads(x) for x in (d / "demo.jsonl").read_text().splitlines() if x.strip()]
        meas = [
            {**r["outcome"]["evidence"], "map": map_name} for r in recs if r.get("rule") == RULE
        ]
        bad = audit_positions(meas, _positions(d))
        for i, m in enumerate(meas):
            if i in bad or m.get("unsettled"):
                dropped.append({"session": sid, "view": m["view"], "stand": m["stand"],
                                "why": bad.get(i, "unsettled")})  # fmt: skip
                continue
            z = np.load(d / m["view"])
            shape = tuple(int(v) for v in z["shape"])
            mask = np.unpackbits(z["mask"])[: shape[0] * shape[1]].reshape(shape).astype(bool)
            excl = exclusion(shape, tuple(m["feet"]), m["windows"], _sizes())
            by_stand.setdefault(tuple(m["stand"]), []).append(counted(mask, excl))
            excls.setdefault(tuple(m["stand"]), []).append(excl)
            where.setdefault(tuple(m["stand"]), []).append({"session": sid, "view": m["view"]})
    for stand, masks in by_stand.items():
        if unconfirmed(masks):  # animated once, never rechecked (a stopped run): fail closed
            dropped += [{**w, "stand": list(stand), "why": "unconfirmed"} for w in where[stand]]
            continue

        def pick_here(px: Any, s: Cell = stand) -> Any:
            return pick_cells(camera, gat, s, px)

        for excl in excls[stand]:
            measured |= coverage(pick_here, stand, excl)
    views: dict[Cell, set[Cell]] = {}
    for stand, masks in by_stand.items():
        if len(masks) < 2:  # measured once: no animation (or unconfirmed, dropped above)
            continue
        both = masks[0] & masks[1]

        def pick(px: Any, s: Cell = stand) -> Any:
            return pick_cells(camera, gat, s, px)

        views[stand] = view_cells(both, pick, stand)
    region = sorted(region_of(views))
    group = clone_groups().get(map_name, [map_name])
    doc = {"map": map_name, "rule": RULE, "sessions": list(sessions), "built_at":
           time.strftime("%Y-%m-%dT%H:%M:%S%z"), "commit": _commit(), "grow_cells": GROW_CELLS,
           "stands_measured": len(by_stand), "views_with_cells": len(views),
           "per_view": {f"{s[0]},{s[1]}": len(c) for s, c in sorted(views.items())},
           "dropped": dropped, "cells": [list(c) for c in region],
           "measured": [list(c) for c in sorted(measured)], "measured_on": map_name,
           "serves": group, "never_commit": "derived from client pixels"}  # fmt: skip
    out_dir.mkdir(parents=True, exist_ok=True)
    for m in group:  # a clone group's copies share the representative's measurement
        (out_dir / f"{m}.json").write_text(json.dumps({**doc, "map": m}))
    return {k: v for k, v in doc.items() if k not in ("cells", "per_view", "measured")} | {
        "region_cells": len(region),
        "measured_cells": len(measured),
    }


def window_sizes(specs: Mapping[str, Any]) -> dict[str, tuple[int, int]]:
    """Each window's excluded size: the registry's, or its drawn size (DRAWN_SIZE)."""
    return {n: DRAWN_SIZE.get(n, tuple(spec.size)) for n, spec in specs.items()}


def _sizes() -> dict[str, tuple[int, int]]:
    from poring_env import ui_anchors as ua

    return window_sizes(ua.default_registry().windows)  # sizes only: no templates needed


def load_region(map_name: str, out_dir: Path = OUT_DIR) -> set[Cell] | None:
    """The map's measured region (cells), or None when it was never measured (callers fail
    closed)."""
    got = load_measurement(map_name, out_dir)
    return None if got is None else got[0]


def load_measurement(map_name: str,
                     out_dir: Path = OUT_DIR) -> tuple[set[Cell], set[Cell]] | None:  # fmt: skip
    """(the region, the measured AREA) of a map, or None when it was never measured. A click is
    allowed only on a measured cell outside the region (Batt 2026-10-15: "clicks outside a
    measured area are refused (fail closed)")."""
    p = out_dir / f"{map_name}.json"
    if not p.exists():
        return None
    doc = json.loads(p.read_text())
    cells = {(int(c[0]), int(c[1])) for c in doc["cells"]}
    return cells, {(int(c[0]), int(c[1])) for c in doc.get("measured", [])}


def click_allowed(
    cell: Sequence[int], measurement: tuple[set[Cell], set[Cell]] | None
) -> str | None:
    """None when a WALK click on ``cell`` is allowed; else why not: "no_measurement" (the map was
    never measured), "not_measured" (outside every measured view), "animated_region"."""
    if measurement is None:
        return "no_measurement"
    region, measured = measurement
    c = (int(cell[0]), int(cell[1]))
    if c not in measured:
        return "not_measured"
    return "animated_region" if c in region else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("mode", choices=("plan", "measure", "build", "show"))
    ap.add_argument("--map", help="the map (plan: omit it for every map in the scope)")
    ap.add_argument("--step", type=int, default=STEP)
    ap.add_argument("--refine-step", type=int, default=REFINE_STEP)
    ap.add_argument("--pass2-from", help="measure: pass 2 only, from this session's pass 1")
    ap.add_argument("--max-pass2", type=int, help="measure: stop after pass 1 above N stands")
    ap.add_argument("--radius", type=int, default=RADIUS)
    ap.add_argument("--session", action="append", default=[])
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    a = ap.parse_args()
    if a.mode == "plan":
        routes, problems = workflow_routes()
        maps = [a.map] if a.map else [rep for rep in scoped_maps(routes)
                                      if not any(rep in g and rep != r0
                                                 for r0, g in clone_groups().items())]  # fmt: skip
        total = 0.0
        for m in maps:
            row = plan(m, a.step, routes)
            total += row["est_minutes_pass1"]
            print(json.dumps(row))
        print(json.dumps({"maps": len(maps), "est_minutes_pass1_total": round(total, 1),
                          "route_problems": problems}))  # fmt: skip
        return 0
    if not a.map:
        raise SystemExit(f"{a.mode} needs --map")
    if a.mode == "measure":
        return measure(a.map, a.step, a.refine_step, a.radius, a.pass2_from, a.max_pass2)
    if a.mode == "build":
        if not a.session:
            raise SystemExit("build needs --session (the measure run's session ids)")
        print(json.dumps(build(a.map, a.session, a.out)))
        return 0
    got = load_region(a.map, a.out)
    print(json.dumps({"map": a.map, "measured": got is not None,
                      "cells": None if got is None else len(got)}))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
