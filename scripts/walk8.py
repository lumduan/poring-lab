#!/usr/bin/env python3
"""walk@8 (docs/demonstrations.md 3.14; Batt's insight, 2026-10-07 ~19:25).

    walk8.py --scene indoor|outdoor --condition clean|crowd [--n 56] [--seed 20261018]
             [--label walk8-alone] [--crowd 4]

walk@6/7 mixed two questions. walk@8 separates them:
1. IS THE ROUTE PASSABLE? Only static structure decides that (walls, pews: the GAT). In RO units
   do not block movement (a held drag walked through a monster without attacking it), so the
   route is planned ONCE (A* on the GAT) as a WAYPOINT polyline -- its turning points and the
   goal -- and never refused because of a unit on an intermediate cell. (walk@6's "every cell of
   the run shows the walk cursor" over-refused: 151 of its 222 indoor refusals had a unit within
   2 cells.)
2. WILL THIS CLICK WALK? Only the click pixel decides that. Per step the rule probes ONLY the
   chosen click point: the walk cursor (walk@6's two-sided classifier) + the chevrons naming the
   cell, re-checked with no motion, then the click. If a unit covers it (any other shape) the
   click MOVES to another point on the same run or the next waypoint -- no waiting. An UNKNOWN
   cursor at the click point is still no click.
The BELIEF is checked against the structure at the start and every ALIGN_EVERY clicks: probes
where the believed cell predicts a no-entry sign (a wall or pew edge) or distinctive chevrons
(reloc2's per-candidate prediction) must show it; a mismatch re-localises (v2) and re-plans. The
planned polyline and the next click are drawn for the human over the console's stream (a
RoutePreview: display only, relayed to viewers, never to the mux). The click time is logged.
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
import rule_run as rr  # noqa: E402
import walk5 as w5  # noqa: E402
import walk6 as w6  # noqa: E402
import where_fix as wf  # noqa: E402

from poring_env.demo import Action, DemoLog, DemoRecord, Intended, new_session_id  # noqa: E402

WALK8_RULE = "walk@8"
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
CURSOR_REFS_V2 = r.ROOT / "data/walk6/cursor_refs_rdp_v2.npz"  # + the pickup hand (19:13)
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
RELOCS = 2
CLICK_ATTEMPTS = 30
WALK = w6.WALK
MIN_MARKER_PX8 = 30  # walk@8 names a cell from >= 30 px of chevrons (rule_run: 60): pews occlude
#                      the marker (walk@4), and the 23:19 pilot read 50-54 px on clear walk cells;
#                      >= 2 chevrons and identify_cell's corner-geometry fit are still required
STALE_RETRIES = 2  # a parked frame that never went fresh: probe the same point again


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


def named8(w: w5.World, rel: tuple[int, int], p: dict[str, Any]) -> tuple[int, int] | None:
    """walk6.named with walk@8's marker threshold (MIN_MARKER_PX8)."""
    if p["marker_px"] < MIN_MARKER_PX8 or len(p["comps"]) < rr.MIN_CHEVRONS:
        return None
    k: tuple[int, int] | None = rr.identify_cell(w.camera, w.gat, w.position, rel, p["comps"])[0]
    return k


def click_step(pr: w6.Prober, w: w5.World, end: tuple[int, int],
               expect: str = WALK) -> dict[str, Any]:  # fmt: skip
    """Probe ONLY the click point (walk@6's target logic: WALK + the chevrons naming the cell, one
    correction for a neighbour, the in-cell alternates; the no-motion re-check), then click.
    ``expect="warp"``: the click whose intent is to TAKE a portal -- the allowed shape is the warp
    cursor instead (re-checked the same way); no chevrons are required on a portal cell."""
    if expect == "warp":
        return portal_step(pr, w, end)
    if not pr.park():
        return {"clicked": False, "outcome": "stale_background", "target": []}
    rel = (end[0] - w.position[0], end[1] - w.position[1])
    nb = np.array([(end[0] + dx, end[1] + dy) for dx, dy in rr.NB9], dtype=float)
    proj = w.project(nb)
    queue = rr.in_cell_points(proj)
    target: list[dict[str, Any]] = []
    corrected = False
    while queue and len(target) < rr.MAX_HOVERS:
        u, v = queue.pop(0)
        pr.hover(u, v)
        p = pr.read(u, v)
        k = named8(w, rel, p)
        target.append({"at": [round(u, 1), round(v, 1)], "shape": p["shape"], "iou": p["iou"],
                       "cell": k, "marker_px": p["marker_px"]})  # fmt: skip
        if p["shape"] != WALK:  # a unit (or anything unknown) covers the click point
            return {"clicked": False, "outcome": f"covered_{p['shape']}", "target": target}
        if k == (0, 0):
            again = pr.read(u, v)  # the RE-CHECK: a fresh grab, no motion
            k2 = named8(w, rel, again)
            target[-1]["recheck"] = {"shape": again["shape"], "cell": k2}
            if again["shape"] != WALK or k2 != (0, 0):
                return {"clicked": False, "outcome": f"recheck_{again['shape']}",
                        "target": target}  # fmt: skip
            gx, gy, _, _ = r.game_region()
            t_click = r.ns()
            pr.agent.click(gx + round(u), gy + round(v))
            return {"clicked": True, "outcome": "confirmed", "target": target, "at": (u, v),
                    "t_click": t_click}  # fmt: skip
        if k is not None and not corrected:
            i = rr.NB9.index(k)
            du, dv = float(proj[4][0] - proj[i][0]), float(proj[4][1] - proj[i][1])
            queue.insert(0, (u + du, v + dv))
            corrected = True
        elif k is not None:
            return {"clicked": False, "outcome": "neighbour", "target": target}
    return {"clicked": False, "outcome": "unconfirmed", "target": target}


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


def preview(agent: Any, w: w5.World, start: tuple[int, int], wps: Sequence[tuple[int, int]],
            click: tuple[int, int] | None, label: str) -> None:  # fmt: skip
    """The RoutePreview for the console (display only; poring_env.protocol.RoutePreview). Sent on
    the agent's socket with no reply expected; a viewer-side extra, never a reason to stop."""
    try:
        gx, gy, _, _ = r.game_region()
        dw, dh = r.desktop()
        cells = [start, *wps] + ([click] if click else [])
        kinds = ["start"] + ["waypoint"] * (len(wps) - 1) + ["goal"] + (["click"] if click else [])
        px = w.project(cells)
        pts = [{"x": min(max((gx + float(u)) / dw, 0.0), 1.0),
                "y": min(max((gy + float(v)) / dh, 0.0), 1.0), "kind": k}
               for (u, v), k in zip(px, kinds, strict=True)]  # fmt: skip
        msg = {"type": "route_preview", "t_mono_ns": r.ns(), "frame_id": -1, "points": pts[:64],
               "label": label[:64], "ttl_ms": 6000}  # fmt: skip
        agent.ws.send(json.dumps(msg))
    except Exception:  # noqa: BLE001 -- the preview must never break the walk
        pass


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
               clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:  # fmt: skip
    """walk@8, ALONE, one route: plan ONCE, probe only the click point, fix the belief only when in
    doubt. ``expect_goal="warp"``: the goal is a PORTAL (the warp cursor at the click point).
    Patience ONLY for a UNIT at the click point; a substitute ONLY for a UNIT on the goal
    (walk@7 waited on unknown reads and substituted goals nobody had taken: 7 / 8)."""
    events: list[dict[str, Any]] = []
    relocs = clicks = covered = 0
    streak, streak_from = 0, None
    target, substitute = goal, None
    waited = 0.0
    unit_since: float | None = None

    def done(**kw: Any) -> dict[str, Any]:
        return {"events": events, "relocs": relocs, "clicks": clicks, "covered": covered,
                "substitute": substitute, "waited_s": round(waited, 1), **kw}  # fmt: skip

    def plan_once() -> list[tuple[int, int]] | None:
        path = w6.plan(w, target, {goal} if substitute else set())
        if path is not None:
            events.append({"plan": [list(c) for c in waypoints(w.position, path)], "t": r.ns()})
        return path

    def relocate(why: str) -> str | None:
        """Fix the belief and re-plan; a decline, or None to go on."""
        nonlocal relocs, path
        if relocs >= RELOCS:
            return "relocalise_limit"
        rl = relocalise(pr.agent, pr.screen, w, noentry_mask, band)
        relocs += 1
        events.append({"relocalise": rl, "why": why, "t": r.ns()})
        if not rl["ok"]:
            return "relocalise_failed"
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
        cands = click_candidates(w, path, seg_max, band)
        if not cands:
            return done(decline="out_of_band")
        clicked = False
        unit_at: list[tuple[int, int]] = []
        for end in cands:
            preview(pr.agent, w, w.position, waypoints(w.position, path), end, label)
            expect = expect_goal if end == goal else WALK
            step = click_step(pr, w, end, expect)
            for _ in range(STALE_RETRIES):  # the park never went fresh: the same point again
                if step["outcome"] != "stale_background":
                    break
                step = click_step(pr, w, end, expect)
            kept = {k: v for k, v in step.items() if k != "at"}
            events.append({"from": list(w.position), "end": list(end), "t": r.ns(), **kept})
            log_seg(step.get("t_click", r.ns()), w.position, end, step)
            if step["clicked"] and expect == "warp":
                n = max(abs(end[0] - w.position[0]), abs(end[1] - w.position[1]))
                time.sleep(n * w5.STEP_S + PORTAL_LOAD_S)  # the walk in, then the other map loads
                return done(arrived_belief=True, portal=True)
            if step["clicked"]:
                n = max(abs(end[0] - w.position[0]), abs(end[1] - w.position[1]))
                w.position = end  # dead reckoning
                path = path[path.index(end) + 1 :]  # the rest of the ONE plan
                clicks += 1
                streak, streak_from = 0, None
                unit_since = None
                time.sleep(n * w5.STEP_S + w5.ARRIVE_S)
                clicked = True
                break
            shape = step["target"][-1]["shape"] if step["target"] else None
            if shape == "noentry" and w.walkable[end[1], end[0]]:
                pending = "noentry"  # a planned (GAT-walkable) cell refused: the belief is wrong
                break
            if step["outcome"].startswith(("covered_", "recheck_")):
                covered += 1  # not clickable: the next point on the polyline, at once
                if shape in UNIT_SHAPES:
                    unit_at.append(end)
                continue
            if step["outcome"] == "unconfirmed":
                streak = streak + 1 if streak_from == w.position else 1
                streak_from = w.position
                if streak >= UNCONFIRMED_STREAK:
                    pending = "unconfirmed"
                    break
                continue
            if step["outcome"] == "neighbour":
                pending = "neighbour"
                break
        if clicked or pending is not None:
            continue
        if not unit_at:
            return done(decline="no_click_point")  # nothing clickable, and no unit to wait for
        now = clock()
        unit_since = now if unit_since is None else unit_since
        if now - unit_since < PATIENCE_S and waited < WAIT_BUDGET_S:
            time.sleep(0.5)  # a UNIT covers the click points: its idle pause ends within ~5 s
            waited += clock() - now
            continue
        if target in unit_at and substitute is None and expect_goal == WALK:
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
              account="gm", seg_max=seg_max, refs=len(refs.cls), fix=fix)  # fmt: skip
    print(json.dumps({"session": sid, "rule": WALK8_RULE, "scene": scene, "map": mapname,
                      "heldout": heldout, "condition": condition}), flush=True)  # fmt: skip
    t_first = r.ns()
    with r.session(f"rule:{WALK8_RULE}") as (agent, screen):
        pr = w6.Prober(agent, screen, refs)
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

        for i in range(n):
            gm_cmd = False
            if condition == "clean":
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
                                 expect_goal="warp" if portal else WALK)  # fmt: skip
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
