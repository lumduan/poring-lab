#!/usr/bin/env python3
"""walk@6 (docs/demonstrations.md 3.9; Batt's ALLOWLIST refinement of walk@5, 2026-10-07 ~15:55).

    walk6.py --scene indoor|outdoor [--n 56] [--seed 20261014] [--label walk6-alone]
             [--seg-indoor 3] [--seg-open 5] [--seg-crowded 3] [--obstacles 4]

walk@5 clicked a segment end when the client drew chevrons there and refused a no-entry sign: a
BLOCKLIST. Monsters, NPCs, other players' shops, floor items and warp portals stand in the way too,
and a click on one attacks, talks, opens the shop, picks up or warps. So walk@6 is an ALLOWLIST:
1. PLAN as walk@5 (A* on the GAT, straight or diagonal runs). The run length depends on the
   context: SEG_INDOOR (3) indoors, SEG_OPEN (5) in the open, SEG_CROWDED (3) for the rest of a
   route once any probe saw something other than the walk cursor.
2. PROBE EVERY CELL of the run, in order, before clicking:
   - ONE parked grab per segment (the cursor away) gives the background, B;
   - each cell is hovered (two motions), and the cursor's own mask is |A - B| minus the chevrons;
   - the mask is matched TWO-SIDED (IoU, then the colour on the overlap) against the calibrated
     reference hovers (CURSOR_REFS, RDP). Extra content, such as the no-entry ring drawn over the
     arrow, lowers the IoU, so it can never pass as the arrow;
   - every cell must be the WALK cursor. Any other shape (sword, talk, no-entry, warp, pickup,
     shop) or UNKNOWN -> no click. Up to SHAPE_GRABS grabs while unknown (the cursor animates).
3. The TARGET also needs the chevrons naming it (walk@4/5's corner anchors; one correction for a
   neighbour, then the in-cell alternates), and is RE-CHECKED right before the click: a fresh grab
   with no motion must still be WALK with the chevrons naming it. Things move.
4. A refused segment: wait WAIT_S and probe it again once; still refused -> mark the cell blocked
   for this route and re-plan (at most REPLANS). A no-entry sign on a GAT-walkable cell means the
   BELIEF is wrong: re-localise (walk@5's v1, the structure probes) and re-plan.
5. Arrival per segment: dead reckoning live (the minimap outdoors); packets offline for scoring.
Pixels in, input out: the rule never reads packets. Client pixels (the references) stay in data/
and /dev/shm, never in git.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import deque
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import record_session  # noqa: E402
import ro_agent as r  # noqa: E402
import rule_run as rr  # noqa: E402
import walk5 as w5  # noqa: E402

from poring_env.demo import Action, DemoLog, DemoRecord, Intended, new_session_id  # noqa: E402

WALK6_RULE = "walk@6"
SEG_INDOOR, SEG_OPEN, SEG_CROWDED = 3, 5, 3  # cells per click (Batt: 2-3 indoors / crowded)
CURSOR_REFS = r.ROOT / "data/walk6/cursor_refs_rdp.npz"  # client pixels: data/, never committed
MIN_IOU, MIN_COL, COL_TOL = 0.6, 0.85, 40  # leave-one-out on 564 RDP hovers (3.9)
MIN_CURSOR_PX = 12
SHAPE_GRABS, SHAPE_REGRAB_S = 3, 0.1
PARK_S, PARK_FRESH_S = 0.3, 1.5  # the parked frame must show the cursor AT the park
HOVER6_S = 0.55  # settle after the 2nd motion: the cursor is drawn ~0.41-0.82 s after it (17:47)
PARKS = ((1250, 380), (1250, 300))  # two park points: every park is a real move
PARK_CURSOR_PX = (60, 1200)  # a cursor-sized difference at the park, not a scrolling scene
WAIT_S = 1.0
REPLANS = 3
GOAL_WAITS = 3  # a refused GOAL is waited for, never blocked (blocking it leaves no plan)
WALK = "walk"


def green(c: Any) -> Any:
    """The chevrons' pale green (the calibration's filter; BGR)."""
    b, g, red = (c[..., i].astype(int) for i in range(3))
    return (g - red > 50) & (g - b > 35) & (red > 60) & (b > 60) & (g > 150)


def cursor_mask(a: Any, b: Any) -> Any:
    """The cursor's own pixels in a 64x64 crop centred on the hotspot: |A - B| > 60 summed over
    the channels, minus the chevrons, the largest component touching the hotspot (rows/cols
    28..40). A moving entity next to the cursor may merge in; that only lowers the match."""
    a3, b3 = np.asarray(a)[..., :3], np.asarray(b)[..., :3]
    diff = np.abs(a3.astype(int) - b3.astype(int)).sum(-1) > 60
    diff &= ~green(a3)
    h, w = diff.shape
    lab = np.zeros(diff.shape, dtype=np.int32)
    n, best = 0, None
    for y0, x0 in zip(*np.nonzero(diff), strict=True):
        if lab[y0, x0]:
            continue
        n += 1
        q = deque([(int(y0), int(x0))])
        lab[y0, x0] = n
        size, hot = 0, False
        while q:
            y, x = q.popleft()
            size += 1
            hot = hot or (28 <= y <= 40 and 28 <= x <= 40)
            for yy in (y - 1, y, y + 1):
                for xx in (x - 1, x, x + 1):
                    if 0 <= yy < h and 0 <= xx < w and diff[yy, xx] and not lab[yy, xx]:
                        lab[yy, xx] = n
                        q.append((yy, xx))
        if hot and (best is None or size > best[1]):
            best = (n, size)
    return lab == best[0] if best else np.zeros_like(diff)


class CursorRefs:
    """The calibrated reference hovers: crops A (N,64,64,3), masks M (N,64,64), classes."""

    def __init__(self, a: Any, m: Any, cls: Sequence[str]) -> None:
        self.a = np.asarray(a).astype(np.int16)
        self.m = np.asarray(m, dtype=bool)
        self.cls = list(cls)
        self.n = self.m.reshape(len(self.cls), -1).sum(1)

    @classmethod
    def load(cls, path: Path = CURSOR_REFS) -> CursorRefs:
        z = np.load(path)
        return cls(z["a"], z["m"], [str(c) for c in z["cls"]])

    def match(self, a: Any, mask: Any) -> dict[str, Any]:
        """Two-sided: the best IoU among the references whose colour agrees on the overlap."""
        m = np.asarray(mask, dtype=bool)
        if int(m.sum()) < MIN_CURSOR_PX:
            return {"shape": "unknown", "why": "no_cursor", "iou": 0.0, "col": 0.0}
        inter = (self.m & m).reshape(len(self.cls), -1).sum(1)
        union = (self.m | m).reshape(len(self.cls), -1).sum(1)
        iou = np.where((union > 0) & (self.n >= MIN_CURSOR_PX), inter / np.maximum(union, 1), 0.0)
        a16 = np.asarray(a)[..., :3].astype(np.int16)
        for j in np.argsort(-iou):
            if iou[j] < MIN_IOU:
                break
            ov = self.m[j] & m
            col = float((np.abs(a16 - self.a[j]).max(-1)[ov] < COL_TOL).mean())
            if col >= MIN_COL:
                return {"shape": self.cls[j], "iou": round(float(iou[j]), 3),
                        "col": round(col, 3), "ref": int(j)}  # fmt: skip
        top = float(iou.max()) if len(iou) else 0.0
        return {"shape": "unknown", "why": "no_match", "iou": round(top, 3), "col": 0.0}


def line_cells(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
    """The cells of a straight or diagonal run, start excluded, end included."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    n = max(abs(dx), abs(dy))
    if n == 0 or (dx and dy and abs(dx) != abs(dy)):
        raise ValueError(f"not a straight or diagonal run: {start} -> {end}")
    sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
    return [(start[0] + k * sx, start[1] + k * sy) for k in range(1, n + 1)]


class Grid:
    """poring_dataset.walk.Grid: the GAT plus the cells this route found blocked."""

    def __init__(self, walkable: Any, blocked: set[tuple[int, int]]) -> None:
        self.base = w5.GatGrid(walkable)
        self.xs, self.ys = self.base.xs, self.base.ys
        self.blocked = blocked

    def nopass(self, x: int, y: int) -> bool:
        return (x, y) in self.blocked or self.base.nopass(x, y)


def plan(w: w5.World, goal: tuple[int, int], blocked: set[tuple[int, int]]) -> Any:
    from poring_dataset.walk import walk_path

    return walk_path(Grid(w.walkable, blocked), w.position[0], w.position[1], goal[0], goal[1],
                     max_len=w5.PLAN_MAX)  # fmt: skip


class Prober:
    """Hover a client pixel and read the cursor's shape against the segment's parked background."""

    def __init__(self, agent: r.Agent, screen: r.Screen, refs: CursorRefs,
                 dump: Path | None = None) -> None:  # fmt: skip
        self.agent, self.screen, self.refs = agent, screen, refs
        self.background: Any = None
        self.parked = -1  # which of PARKS the cursor is at (-1: neither)
        self.stale = 0  # parks whose frame never showed the cursor at the park point
        self.park_waits: list[float] = []
        self.dump, self.dumped = dump, 0  # design time: the crops of every non-WALK read

    def park(self) -> bool:
        """Park the cursor and keep ONE background frame for the segment. The frame must be
        FRESH: the game draws its own cursor, only where a second motion leaves it, ~0.4-0.9 s
        later (the 17:36 pilot: one-motion parks left the cursor on the cells about to be
        probed, so |A - B| lost it). Fresh = the cursor has APPEARED at the park point: a
        cursor-sized difference there against a frame grabbed just before the move (a scrolling
        scene makes a bigger one). False if it never did within PARK_FRESH_S."""
        gx, gy, _, _ = r.game_region()
        self.parked = 1 if self.parked == 0 else 0
        pu, pv = PARKS[self.parked]
        before = self._crop(self.screen.grab(*r.game_region())[1], pu, pv, 32)
        t0 = time.monotonic()
        # TWO motions: the client draws its cursor only where a SECOND motion leaves it (one
        # motion never moved the drawn cursor, 2026-10-07 17:46; walk@4's marker finding)
        self.agent.move(gx + pu - rr.HOVER_APPROACH_PX, gy + pv - rr.HOVER_APPROACH_PX)
        time.sleep(rr.HOVER_APPROACH_S)
        self.agent.move(gx + pu, gy + pv)
        time.sleep(PARK_S)
        while True:
            self.background = self.screen.grab(*r.game_region())[1]
            n = int(cursor_mask(self._crop(self.background, pu, pv, 32), before).sum())
            if PARK_CURSOR_PX[0] <= n <= PARK_CURSOR_PX[1]:
                self.park_waits.append(round(time.monotonic() - t0, 3))
                return True
            if time.monotonic() - t0 > PARK_FRESH_S:
                self.stale += 1
                return False
            time.sleep(0.05)

    def _crop(self, img: Any, u: float, v: float, half: int) -> Any:
        x, y = round(u), round(v)
        pad = np.pad(np.asarray(img)[..., :3], ((half, half), (half, half), (0, 0)))
        return pad[y : y + 2 * half, x : x + 2 * half]

    def hover(self, u: float, v: float) -> None:
        self.parked = -1
        gx, gy, _, _ = r.game_region()
        px, py = gx + round(u), gy + round(v)
        self.agent.move(px - rr.HOVER_APPROACH_PX, py - rr.HOVER_APPROACH_PX)
        time.sleep(rr.HOVER_APPROACH_S)
        self.agent.move(px, py)
        time.sleep(HOVER6_S)

    def read(self, u: float, v: float) -> dict[str, Any]:
        """The shape (up to SHAPE_GRABS grabs while unknown) and the chevrons, with no motion."""
        gx, gy, _, _ = r.game_region()
        px, py = gx + round(u), gy + round(v)
        b = self._crop(self.background, u, v, 32)
        out: dict[str, Any] = {}
        for g in range(SHAPE_GRABS):
            if g:
                time.sleep(SHAPE_REGRAB_S)
            big = self.screen.grab(px - 60, py - 60, 120, 120)[1][..., :3]
            out = self.refs.match(big[28:92, 28:92], cursor_mask(big[28:92, 28:92], b))
            out["grabs"] = g + 1
            if out["shape"] != "unknown":
                break
        if self.dump is not None and out["shape"] != WALK:
            self.dump.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(self.dump / f"{self.dumped:04d}.npz", a=big, b=b)
            out["dump"] = self.dumped
            self.dumped += 1
        comps = rr.green_components(big)
        out["comps"] = [(x + px - 60 - gx, y + py - 60 - gy) for x, y, _ in comps]
        out["marker_px"] = sum(n for *_, n in comps)
        return out


def chevrons(p: dict[str, Any]) -> bool:
    return p["marker_px"] >= rr.MIN_MARKER_PX and len(p["comps"]) >= rr.MIN_CHEVRONS


def named(w: w5.World, rel: tuple[int, int], p: dict[str, Any]) -> tuple[int, int] | None:
    """The NB9 offset the chevrons name (walk@4/5's corner anchors), None without chevrons."""
    if not chevrons(p):
        return None
    k: tuple[int, int] | None = rr.identify_cell(w.camera, w.gat, w.position, rel, p["comps"])[0]
    return k


def segment_step(pr: Prober, w: w5.World, end: tuple[int, int]) -> dict[str, Any]:
    """Probe every cell of ONE run, then confirm, re-check and click its end. Returns
    {"clicked", "outcome", "line", "target", "blocker"} (blocker: the first refused cell)."""
    if not pr.park():
        return {"clicked": False, "outcome": "stale_background", "line": [], "target": [],
                "blocker": None}  # fmt: skip
    line: list[dict[str, Any]] = []
    cells = line_cells(w.position, end)
    for c in cells[:-1]:
        u, v = w.project([c])[0]
        pr.hover(float(u), float(v))
        p = pr.read(float(u), float(v))
        line.append({"cell": list(c), "shape": p["shape"], "iou": p["iou"], "grabs": p["grabs"],
                     "dump": p.get("dump")})  # fmt: skip
        if p["shape"] != WALK:
            return {"clicked": False, "outcome": f"line_{p['shape']}", "line": line,
                    "target": [], "blocker": c}  # fmt: skip
    # the target: WALK + the chevrons naming it (walk@4/5's queue: centre, a correction, alternates)
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
        k = named(w, rel, p)
        target.append({"at": [round(u, 1), round(v, 1)], "shape": p["shape"], "iou": p["iou"],
                       "cell": k, "marker_px": p["marker_px"], "dump": p.get("dump")})  # fmt: skip
        if p["shape"] != WALK:
            return {"clicked": False, "outcome": f"target_{p['shape']}", "line": line,
                    "target": target, "blocker": end}  # fmt: skip
        if k == (0, 0):
            again = pr.read(u, v)  # the RE-CHECK: a fresh grab, no motion
            k2 = named(w, rel, again)
            target[-1]["recheck"] = {"shape": again["shape"], "cell": k2}
            if again["shape"] != WALK or k2 != (0, 0):
                return {"clicked": False, "outcome": f"recheck_{again['shape']}", "line": line,
                        "target": target, "blocker": end}  # fmt: skip
            gx, gy, _, _ = r.game_region()
            pr.agent.click(gx + round(u), gy + round(v))
            return {"clicked": True, "outcome": "confirmed", "line": line, "target": target,
                    "at": (u, v), "blocker": None}  # fmt: skip
        if k is not None and not corrected:
            i = rr.NB9.index(k)
            du, dv = float(proj[4][0] - proj[i][0]), float(proj[4][1] - proj[i][1])
            queue.insert(0, (u + du, v + dv))
            corrected = True
        elif k is not None:
            return {"clicked": False, "outcome": "neighbour", "line": line, "target": target,
                    "blocker": end}  # fmt: skip
    return {"clicked": False, "outcome": "unconfirmed", "line": line, "target": target,
            "blocker": end}  # fmt: skip


def shorten_into_band(w: w5.World, path: Sequence[tuple[int, int]], end: tuple[int, int],
                      band: tuple[int, int, int, int]) -> tuple[int, int] | None:  # fmt: skip
    x0, y0, x1, y1 = band
    while True:
        u, v = w.project([end])[0]
        if x0 <= u <= x1 and y0 <= v <= y1:
            return end
        k = list(path).index(end)
        if k == 0:
            return None
        end = path[k - 1]


def walk_route(pr: Prober, w: w5.World, goal: tuple[int, int], band: tuple[int, int, int, int],
               seg_start: int, log_seg: Any, noentry_mask: Any,
               read_position: Any = None) -> dict[str, Any]:  # fmt: skip
    """walk@6, ALONE, one route: plan, then run by run through the allowlist gate."""
    events: list[dict[str, Any]] = []
    blocked: set[tuple[int, int]] = set()
    relocs = replans = 0
    seg_max = seg_start
    retried: tuple[int, int] | None = None
    goal_waits = 0
    for _ in range(16):  # at most 16 segment attempts per route
        if read_position is not None:
            pos = read_position()
            if pos is not None:
                w.position = pos
        if w.position == goal:
            return {"arrived_belief": True, "events": events, "relocs": relocs,
                    "replans": replans, "seg_max_end": seg_max}  # fmt: skip
        path = plan(w, goal, blocked)
        if path is None:
            return {"decline": "no_plan", "events": events, "relocs": relocs, "replans": replans}
        end = shorten_into_band(w, path, w5.split_segments(w.position, path, seg_max)[0], band)
        if end is None:
            return {"decline": "out_of_band", "events": events, "relocs": relocs,
                    "replans": replans}  # fmt: skip
        t0 = r.ns()
        step = segment_step(pr, w, end)
        kept = {k: v for k, v in step.items() if k not in ("at", "blocker")}
        events.append({"from": list(w.position), "end": list(end), "seg_max": seg_max, **kept})
        log_seg(t0, w.position, end, step)
        if step["clicked"]:
            n = max(abs(end[0] - w.position[0]), abs(end[1] - w.position[1]))
            w.position = end  # dead reckoning
            retried = None
            time.sleep(n * w5.STEP_S + w5.ARRIVE_S)
            continue
        shapes = [x["shape"] for x in step["line"] + step["target"]]
        if any(s not in (WALK, "noentry") for s in shapes):
            seg_max = SEG_CROWDED  # something stands around: short runs for the rest of the route
        if step["blocker"] is None:  # the background never went fresh: probe the run again
            continue
        blocker = tuple(step["blocker"])
        noentry = "noentry" in shapes or step["outcome"] == "neighbour"
        if noentry and w.walkable[blocker[1], blocker[0]]:
            if relocs >= 2:
                return {"decline": "relocalise_limit", "events": events, "relocs": relocs,
                        "replans": replans}  # fmt: skip
            rl = w5.relocalise(pr.agent, pr.screen, w, noentry_mask, band)
            relocs += 1
            events.append({"relocalise": rl})
            if not rl["ok"]:
                return {"decline": "relocalise_failed", "events": events, "relocs": relocs,
                        "replans": replans}  # fmt: skip
            continue
        if blocker == goal:  # someone stands on the goal: wait for it, never block it
            if goal_waits >= GOAL_WAITS:
                return {"decline": "goal_occupied", "events": events, "relocs": relocs,
                        "replans": replans}  # fmt: skip
            goal_waits += 1
            time.sleep(WAIT_S)
            continue
        if retried != blocker:  # things move: wait, then probe the same run once more
            retried = blocker
            time.sleep(WAIT_S)
            continue
        if replans >= REPLANS:
            return {"decline": f"segment_{step['outcome']}", "events": events, "relocs": relocs,
                    "replans": replans}  # fmt: skip
        blocked.add(blocker)  # still there: route around it
        replans += 1
        retried = None
    return {"decline": "segment_limit", "events": events, "relocs": relocs, "replans": replans}


def run(scene: str, n: int, seed: int, label: str, seg: dict[str, int], obstacles: int,
        dump: bool = False) -> int:  # fmt: skip
    import random

    import bench

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod
    from poring_env import selfpos

    refs = CursorRefs.load()
    noentry_mask = np.load(w5.NOENTRY_MASK)
    mapname, sx0, sy0 = rr.SCENES[scene]
    gat = gatmod.parse((cam.GAT_DIR / f"{mapname}.gat").read_bytes())
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    base = cam.camera_from_json(cj["camera"])
    indoor = scene == "indoor"
    camera = (cam.camera_for_map(base, True, cj["indoor"]["yaw_deg"], cj["indoor"]["distance"])
              if indoor else base)  # fmt: skip
    w = w5.World(camera, gat, (sx0, sy0))
    templates = None if indoor else selfpos.load_digit_templates()
    band = rr.ec_band()
    seg_start = seg["indoor"] if indoor else seg["open"]
    rng = random.Random(seed)
    sid = new_session_id(f"{label}-{scene}")
    log = DemoLog(sid)
    lock = record_session.read_lock(r.ROOT / "state")
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena", rule=WALK6_RULE,
              n=n, scene=scene, seed=seed, account="gm", seg=seg, obstacles=obstacles,
              refs=len(refs.cls), min_iou=MIN_IOU, min_col=MIN_COL)  # fmt: skip
    print(json.dumps({"session": sid, "rule": WALK6_RULE, "scene": scene}), flush=True)
    t_first = r.ns()
    with r.session(f"rule:{WALK6_RULE}") as (agent, screen):
        pr = Prober(agent, screen, refs, log.dir / "probes" if dump else None)
        r.gm(agent, screen, f"@warp {mapname} {sx0} {sy0}")  # the harness enters the scene once
        time.sleep(rr.SCENE_ENTRY_S)
        bench.close_chat(agent, screen)

        def read_position() -> tuple[int, int] | None:
            if indoor:
                return None
            xy = selfpos.read_minimap_xy(screen.grab(*r.game_region())[1][:, :, :3], templates)
            return None if xy is None else (int(xy[0]), int(xy[1]))

        for i in range(n):
            if i % rr.DR_WARP_EVERY == 0:  # the HARNESS: a seeded warp, the rule's known start
                if i % 10 == 0:
                    r.gm(agent, screen, "@killmonster2")
                for _ in range(200):
                    sx, sy = sx0 + rng.randint(-8, 8), sy0 + rng.randint(-8, 8)
                    if w.walkable[sy, sx]:
                        break
                r.gm(agent, screen, f"@warp {mapname} {sx} {sy}")
                time.sleep(rr.WARP_SETTLE_S)
                if i % 10 == 0 and obstacles:  # the OBSTACLES: GM-spawned monsters around us
                    r.gm(agent, screen, f"@monster poring {obstacles}")
                    time.sleep(1.0)
                bench.close_chat(agent, screen)
                w.position = (sx, sy)
            r.activate_client(agent, screen)
            if not indoor:
                pos = read_position()
                if pos is not None:
                    w.position = pos
            goal = None  # the HARNESS: a seeded goal 8-20 A* steps from the BELIEVED position
            for _ in range(400):
                g = (w.position[0] + rng.randint(-12, 12), w.position[1] + rng.randint(-12, 12))
                if not (0 <= g[1] < w.walkable.shape[0] and 0 <= g[0] < w.walkable.shape[1]):
                    continue
                if not w.walkable[g[1], g[0]]:
                    continue
                path = plan(w, g, set())
                if path is not None and 8 <= len(path) <= 20:
                    goal = g
                    break
            start, t_route = w.position, r.ns()
            pre = rr.snap(log, screen, f"{i:03d}-route-before")

            def log_seg(t0: int, frm: tuple[int, int], end: tuple[int, int],
                        step: dict[str, Any], i: int = i) -> None:  # fmt: skip
                if not step["clicked"]:
                    return  # a refused probe is route evidence, not a walk attempt
                log.append(DemoRecord(
                    session=sid, actor=f"rule:{WALK6_RULE}", t_mono_ns=t0, t_done_ns=r.ns(),
                    rule=f"{WALK6_RULE}/segment", scene=f"{scene}:{mapname}",
                    cue="walk@6 segment: every cell the walk cursor, the target's chevrons, "
                        "re-checked, then clicked",
                    action=Action(type="walk", points=[step["at"]],
                                  intended=Intended(kind="cell", cell=end, relative=False,
                                                    note=f"route {i} believed {frm[0]},{frm[1]}")),
                    outcome={"status": "pending", "evidence": {  # type: ignore[arg-type]
                        "line": step["line"], "target": step["target"],
                        "believed_position": list(frm)}},
                ))  # fmt: skip

            if goal is None:
                did: dict[str, Any] = {"decline": "no_goal", "events": [], "relocs": 0,
                                       "replans": 0}  # fmt: skip
            else:
                did = walk_route(pr, w, goal, band, seg_start, log_seg, noentry_mask,
                                 read_position if not indoor else None)  # fmt: skip
            log.append(DemoRecord(
                session=sid, actor=f"rule:{WALK6_RULE}", t_mono_ns=t_route, t_done_ns=r.ns(),
                frame=pre, rule=WALK6_RULE, scene=f"{scene}:{mapname}",
                cue="walk@6 route: A* plan, runs by context, the allowlist gate on every cell",
                action=Action(type="walk", intended=Intended(
                    kind="route", cell=goal or start, relative=False,
                    note=f"route {i} from believed {start[0]},{start[1]}")),
                outcome={"status": "pending", "evidence": {  # type: ignore[arg-type]
                    "start_believed": list(start), "goal": list(goal) if goal else None,
                    "end_believed": list(w.position), **did}},
            ))  # fmt: skip
            refused = [e for e in did["events"] if "clicked" in e and not e["clicked"]]
            print(json.dumps({"route": i, "start": list(start), "goal": goal,
                              "end_believed": list(w.position), "decline": did.get("decline"),
                              "segments": sum(1 for e in did["events"] if e.get("clicked")),
                              "refused": [e["outcome"] for e in refused],
                              "relocs": did["relocs"], "replans": did["replans"],
                              "stale_parks": pr.stale,
                              "park_wait_max": max(pr.park_waits, default=None)}),
                  flush=True)  # fmt: skip
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
    ap.add_argument("--scene", choices=sorted(rr.SCENES), required=True)
    ap.add_argument("--n", type=int, default=56)
    ap.add_argument("--seed", type=int, default=20261014)
    ap.add_argument("--label", default="walk6-alone")
    ap.add_argument("--seg-indoor", type=int, default=SEG_INDOOR)
    ap.add_argument("--seg-open", type=int, default=SEG_OPEN)
    ap.add_argument("--obstacles", type=int, default=4, help="Porings spawned every 10 routes")
    ap.add_argument("--dump", action="store_true", help="design time: save non-WALK crops")
    a = ap.parse_args()
    for p in (CURSOR_REFS, w5.NOENTRY_MASK):
        if not p.exists():
            raise SystemExit(f"{p} missing: run the walk@6 cursor calibration (design time)")
    return run(a.scene, a.n, a.seed, a.label, {"indoor": a.seg_indoor, "open": a.seg_open},
               a.obstacles, a.dump)  # fmt: skip


if __name__ == "__main__":
    sys.exit(main())
