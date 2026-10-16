#!/usr/bin/env python3
"""hunt-flow@N (Batt 2026-10-16): CLICK -> WALK IN -> HIT LANDS, fast, like Batt played it. Killing
does not matter; reaction does. The bar: a hit within W = 5.0 s of the first attack click, re-clicks
allowed, >= 95 % over >= 60 engagements (docs/demonstrations.md 3.41; the judge is flow_judge.py).

    hunt_flow.py run --version 1 [--minutes 30] [--seed S]   LIVE (RDP, the GM, ASSIST)

THE LOOP (3.41; parameters from Batt's 10-minute demonstration, 3.40.1)
- WALK CONTINUOUSLY: a coverage route (hunt's search area and planner). While the GM walks, a click
  every WALK_EVERY_S to the path cell ~AHEAD cells ahead (gated by the map and the detector: 3.39
  deviation (2) option B). A click from a standstill is cursor-gated (robust2 WALK). The minimap
  corrects the reckoning; hunt@8's unstick routes around clicks the client does not follow.
- TRACK every fresh detector frame (hunt@6's selection gates) into tracks of cells (predicted at
  constant velocity); a track unseen TRACK_DROP_S is dropped.
- QUEUE + STEER: the nearest track; the route is re-aimed toward a cell SHORT cells short of its
  predicted cell, every WALK_EVERY_S.
- STRIKE at the brief moment the walk ends, if the target is <= STRIKE_CELLS away: park, hover the
  target's newest box, ONE robust2 read; SWORD -> the attack click there (as hunt@6). The SWORD read
  is the only separator from an NPC drawn like a monster (the Poring War Recruiter).
- AFTER THE CLICK: dead (pixels: no target box near its last cell for DEAD_GONE_S) -> the next
  target at once; still there after RECLICK_S -> a re-click; give up at GIVE_UP_S. No looting.
- Stops (none retried): any UI state but clear (the gate's pixel check every CHECK_EVERY_S), HP
  below 75 %, Batt's takeover, the mux leaving ASSIST, an unknown own cell, no progress for STUCK_S.
Packets are never read here (rule 1): flow_judge.py reads them afterwards.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import sys
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import farm0 as f0  # noqa: E402
import farm1 as f1  # noqa: E402
import hunt_core as hc  # noqa: E402
import ro_agent as r  # noqa: E402

RULE = "hunt-flow"
MAP = "prt_fild08"
START = (268, 107)
OUT = Path("/dev/shm/poring-lab-tmp/hunt-flow")  # logs (small)
REC_ROOT = Path("/mnt/poring-lab-datasets/hunt-recordings")  # the 5 Hz frames (NAS, q80)
REC_QUALITY = 80
REC_HZ = 5.0
CHECK_EVERY_S = 30.0
WEIGHT_EVERY_S = 120.0
MINIMAP_EVERY_S = 0.3
DRIFT_CELLS = 3
STUCK_S = 60.0
MS_CELL = 150.0  # the GM's measured walk speed (hunt@5's packets)
Cell = tuple[int, int]

VERSIONS = {
    1: "HUNT-FLOW (Batt's play, 3.40.1): walk continuously (a click ~6 cells ahead every ~0.8 s); "
    "track every monster box; the nearest first; steer to 2 cells short of its predicted cell; "
    "at the brief moment the walk ends, <= 3 cells: ONE robust2 SWORD read on its newest box -> "
    "the attack click; dead from pixels -> the next target at once; no looting",
    2: "PIPELINED (Batt 2026-10-16 ~11:30): PERCEPTION (detector + tracker) and the PLANNER (a "
    "2-4 deep queue by the shortest CHAINED path, standing targets first, re-scored every "
    "frame; the next exploration waypoint always held) run in their own threads; the EXECUTOR "
    "only clicks and never waits for them. At a death it takes queue[0] (or the waypoint) at "
    "once, revalidated on the freshest frame, with the SWORD read before every attack click. "
    "A walk click goes to the farthest path point that passes the gates (v1 gave up when the "
    "one point it tried was within 60 px of a unit)",
    3: "CONTINUOUS WALKING THAT HOLDS: the walk gate while moving accepts detector frames <= 1.0 s "
    "old (was the last 2 <= 0.4 s: the detector's ~0.3 s latency made it refuse most clicks, idle "
    "~80 %) AND adds the tracked monsters' predicted positions over the next second (60 px), "
    "also before a cursor-gated walk click; legs 8 cells ahead (was 6)",
    4: "STRIKE A STANDING TARGET FROM <= 7 CELLS (Batt 12:56, from his play: every click that "
    "resolved to a monster landed, p50 4 / p90 7 cells, ~0.15 s walk-in a cell): the client walks "
    "in itself, so most steering walk clicks next to monsters go; a WALKING target keeps <= 3. "
    "Bug fix: a finished target's track and a dropped target's spot are never dispatched again",
}
PARAMS: dict[int, dict[str, Any]] = {
    1: {"walk_every_s": 0.8, "ahead": 6, "strike_cells": 3, "short": 2, "track_near": 2.0,
        "track_drop_s": 2.0, "dead_gone_s": 0.6, "dead_near_cells": 1.5, "reclick_s": 2.0,
        "give_up_s": 8.0, "dead_min_s": 1.0, "max_reads": 3, "fresh_s": 0.4, "min_box_px": 16.0,
        "unit_clear_px": 60.0, "clear_frames": 2, "drop_target_s": 15.0},
    2: {"walk_every_s": 0.8, "ahead": 6, "strike_cells": 3, "short": 2, "track_near": 2.0,
        "track_drop_s": 2.0, "dead_gone_s": 0.6, "give_up_s": 8.0, "dead_min_s": 1.0,
        "max_reads": 3, "fresh_s": 0.4, "min_box_px": 16.0, "unit_clear_px": 60.0,
        "clear_frames": 2, "drop_target_s": 15.0, "reclick_s": 2.0, "pipelined": True,
        "queue_depth": 3, "moving_penalty": 2.0, "plan_every_s": 0.1, "waypoint_every_s": 3.0,
        "dispatch_fresh_s": 1.0},
}  # fmt: skip
PARAMS[3] = {**PARAMS[2], "ahead": 8, "short": 3, "gate_frames_s": 1.0, "track_clear": True,
             "track_clear_s": 1.0, "track_clear_px": 60.0}  # fmt: skip
PARAMS[4] = {**PARAMS[3], "strike_cells_standing": 7, "dispatch_fixes": True,
             "reacquire": False, "reacquire_cells": 3.0}  # fmt: skip


# --- pure parts (tested) --------------------------------------------------------------------------


def cheb(a: Sequence[float], b: Sequence[float]) -> float:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


@dataclass
class Track:
    """One monster, by its cells over time (constant velocity), and its newest box."""

    tid: int
    seen: list[tuple[int, Cell]] = field(default_factory=list)  # (t_ns, cell)
    box: Any = None  # the newest box (client px)
    box_t: int = 0

    @property
    def t_first(self) -> int:
        return self.seen[0][0]

    @property
    def t_last(self) -> int:
        return self.seen[-1][0]

    def velocity(self) -> tuple[float, float]:
        """Cells / s from the sightings of the last ~1.5 s (0 when it stands or is new)."""
        if len(self.seen) < 2:
            return 0.0, 0.0
        t1, c1 = self.seen[-1]
        old = [s for s in self.seen if 0.4e9 <= t1 - s[0] <= 1.5e9]
        if not old:
            return 0.0, 0.0
        t0, c0 = old[0]  # the oldest in the window: a cell is +-1, so the longest baseline
        if cheb(c0, c1) <= 1:
            return 0.0, 0.0  # within a cell's noise: standing
        dt = (t1 - t0) / 1e9
        vx, vy = (c1[0] - c0[0]) / dt, (c1[1] - c0[1]) / dt
        cap = 1000.0 / 150.0  # nothing on this map walks faster than 150 ms a cell
        n = math.hypot(vx, vy)
        return (vx * cap / n, vy * cap / n) if n > cap else (vx, vy)

    def predict(self, t_ns: int) -> tuple[float, float]:
        t1, c1 = self.seen[-1]
        vx, vy = self.velocity()
        dt = min(1.0, max(0.0, (t_ns - t1) / 1e9))
        return c1[0] + vx * dt, c1[1] + vy * dt


def update_tracks(tracks: list[Track], t_ns: int, sightings: Sequence[tuple[Any, Cell]],
                  next_id: int, near: float, drop_s: float) -> tuple[list[Track], int]:  # fmt: skip
    """PURE: each sighting joins the nearest track whose prediction at ``t_ns`` is within
    ``near`` cells (one sighting per track), else starts a new track; tracks unseen ``drop_s``
    are dropped. Returns (tracks, next_id)."""
    free = list(tracks)
    for box, cell in sorted(sightings, key=lambda s: s[1]):
        best = None
        for tr in free:
            d = cheb(tr.predict(t_ns), cell)
            if d <= near and (best is None or d < best[0]):
                best = (d, tr)
        if best is None:
            tr = Track(next_id)
            next_id += 1
            tracks.append(tr)
        else:
            tr = best[1]
            free.remove(tr)
        tr.seen.append((t_ns, cell))
        tr.box, tr.box_t = box, t_ns
    keep = [tr for tr in tracks if (t_ns - tr.t_last) / 1e9 <= drop_s]
    return keep, next_id


def choose(tracks: Sequence[Track], here: Cell, t_ns: int,
           banned: Sequence[tuple[float, Cell]] = (), now_s: float = 0.0,
           ban_s: float = 15.0) -> Track | None:  # fmt: skip
    """PURE: the nearest track by its predicted cell (Batt: the nearest 52 / 54), skipping cells
    a dropped target left within ``ban_s``."""
    best = None
    for tr in tracks:
        p = tr.predict(t_ns)
        if any(now_s - tb < ban_s and cheb(p, cb) <= 2 for tb, cb in banned):
            continue
        d = cheb(p, here)
        if best is None or d < best[0]:
            best = (d, tr)
    return None if best is None else best[1]


def approach_path(grid: Any, here: Cell, target: tuple[float, float], short: int
                  ) -> list[Cell] | None:  # fmt: skip
    """The A* path toward the target's cell, ending ``short`` cells before it (never a walk click
    onto the monster: hunt@5's walk click 2 cells from it became an attack). None: no path or
    already there."""
    goal = (int(round(target[0])), int(round(target[1])))
    if not (0 <= goal[1] < grid.shape[0] and 0 <= goal[0] < grid.shape[1]):
        return None
    g = grid.copy()
    g[goal[1], goal[0]] = True
    g[here[1], here[0]] = True  # a walk-in can leave us on a cell the grid does not hold
    path = hc.astar(g, here, goal)
    if path is None or len(path) <= short + 1:
        return None
    return path[: len(path) - short]


def strike_range(tr: Track, prm: dict[str, Any]) -> int:
    """PURE (v4): STANDING targets from ``strike_cells_standing`` (Batt's p90, 7), WALKING ones
    from ``strike_cells`` (3); before v4 always ``strike_cells``."""
    vx, vy = tr.velocity()
    if prm.get("strike_cells_standing") and not (vx or vy):
        return int(prm["strike_cells_standing"])
    return int(prm["strike_cells"])


def strike_due(moving: bool, here: Cell, target: tuple[float, float], strike_cells: int) -> bool:
    """PURE: Batt's 'attack from a standing GM': the brief moment the walk has ended, the target
    within ``strike_cells``."""
    return not moving and cheb(here, target) <= strike_cells


def plan_queue(tracks: Sequence[Track], start: Sequence[float], t_ns: int, depth: int,
               banned: Sequence[tuple[float, Cell]] = (), now_s: float = 0.0,
               ban_s: float = 15.0, moving_penalty: float = 2.0) -> list[Track]:  # fmt: skip
    """PURE (v2's planner): up to ``depth`` targets by the shortest CHAINED path -- each next one
    nearest to the previous one's predicted cell, starting from ``start`` (our cell) -- with a
    walking monster costing ``moving_penalty`` cells more (standing targets first: Batt's misses
    were on walking ones). Cells a dropped target left within ``ban_s`` are skipped."""
    left = []
    for tr in tracks:
        p = tr.predict(t_ns)
        if any(now_s - tb < ban_s and cheb(p, cb) <= 2 for tb, cb in banned):
            continue
        vx, vy = tr.velocity()
        left.append((tr, p, moving_penalty if (vx or vy) else 0.0))
    out: list[Track] = []
    at = (float(start[0]), float(start[1]))
    while left and len(out) < depth:
        i = min(range(len(left)), key=lambda j: cheb(at, left[j][1]) + left[j][2])
        tr, p, _pen = left.pop(i)
        out.append(tr)
        at = p
    return out


def reacquire_target(target: Track, live: Sequence[Track], t_ns: int, within: float,
                     exclude: Sequence[int] = ()) -> Track | None:  # fmt: skip
    """PURE (v4): the target's track was dropped (the tracker started a new id for the same
    monster: the cell estimate shifts while the GM walks). The live track nearest the target's
    predicted cell within ``within`` cells carries it on, else None (lost)."""
    p = target.predict(t_ns)
    best = None
    for tr in live:
        if tr.tid == target.tid or tr.tid in exclude:
            continue
        d = cheb(tr.predict(t_ns), p)
        if d <= within and (best is None or d < best[0]):
            best = (d, tr)
    return None if best is None else best[1]


def track_clear(u: float, v: float, tracks: Sequence[Track], t_ns: int, horizon_s: float,
                px: float, project: Any) -> bool:  # fmt: skip
    """PURE (v3, the walk-click safety: hunt-flow@1 had 10 walk clicks turned attacks): the click
    point is more than ``px`` from where every TRACKED monster is predicted to be drawn over the
    next ``horizon_s`` (now, half way, the end). ``project(cell) -> (u, v)`` gives a cell's feet
    point; the monster is drawn at its newest box's offset from its feet. Tracks outlive a
    detector miss (a canopy), which the frame gate does not."""
    for tr in tracks:
        b = tr.box
        off = (0.0, 0.0)
        if b is not None:
            cx, cy = (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2
            off = (cx - (b.x0 + b.x1) / 2, cy - b.y1)
        for k in (0.0, 0.5, 1.0):
            pc = tr.predict(t_ns + int(k * horizon_s * 1e9))
            fu, fv = project(pc)
            if math.hypot(u - (fu + off[0]), v - (fv + off[1])) <= px:
                return False
    return True


def valid_at_dispatch(tr: Track, live: Sequence[Track], t_ns: int, fresh_s: float) -> bool:
    """PURE: a planned target is dispatched only if the tracker still holds it and its newest
    box is from a frame <= ``fresh_s`` old (then the SWORD read decides)."""
    return any(x.tid == tr.tid for x in live) and (t_ns - tr.box_t) / 1e9 <= fresh_s


class PositionModel:
    """Our cell, shared by the executor (it writes) and the perception thread (it reads)."""

    def __init__(self, ms_cell: float, pos: Cell) -> None:
        import threading

        self.lock = threading.Lock()
        self.reck = hc.Reckoner(ms_cell)
        self.moving = False
        self.pos = pos

    def go(self, seg: Sequence[Cell], t0: float) -> None:
        with self.lock:
            self.reck.go(seg, t0)
            self.moving = True

    def stop(self, pos: Cell) -> None:
        with self.lock:
            self.moving, self.pos = False, pos

    def at(self, t: float) -> Cell:
        with self.lock:
            if self.moving:
                return self.reck.where(t) or self.pos
            return self.pos


def _start_thread(target: Any, name: str) -> Any:
    import threading

    th = threading.Thread(target=target, name=name, daemon=True)
    th.start()
    return th


# --- the run --------------------------------------------------------------------------------------


def run(version: int, minutes: float, seed: int) -> int:  # noqa: PLR0915
    import multiprocessing as mp

    import bench
    import cursor_gate
    import gm_state
    import gm_vitals
    import hunt
    import loot1
    import operator_hud
    import record_session
    import route_demo
    import route_plan
    import rule_run as rr
    import unit_detector
    import walk5 as w5
    import walk15 as w15
    import where_fix as wf
    from anim_region import stand_grid

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod
    from poring_dataset import picking
    from poring_env import selfpos
    from poring_env.demo import DemoLog, new_session_id

    if version not in VERSIONS:
        raise SystemExit(f"unknown version {version}")
    prm = PARAMS[version]
    ok_imm, why_imm = f0.immunity_confirmed()
    if not ok_imm:
        raise f0.FarmStop(f"hunt-flow refused: the GM is not confirmed immune ({why_imm})")
    lock = record_session.read_lock(r.ROOT / "state")
    if str(lock.backend) != "rdp":
        raise f0.FarmStop(f"hunt-flow refused: RDP-only cursor references (lock {lock.backend})")
    gat = gatmod.parse((cam.GAT_DIR / f"{MAP}.gat").read_bytes())
    ok = stand_grid(MAP, gat)
    kb = r.ROOT / "data" / "kb"
    warps = json.loads((kb / "warps.json").read_text()).get(MAP, [])
    npcs = json.loads((kb / "npc_cells.json").read_text())["maps"].get(MAP, {}).get("npcs", [])
    keep = [(w["x"], w["y"], w["span_x"], w["span_y"]) for w in warps]
    keep += [(n["x"], n["y"], 1, 1) for n in npcs]
    area = hc.search_area(ok, keep, margin=10)
    start = hunt.start_cell(area, seed)
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    camera = cam.camera_from_json(cj["camera"])
    gx0, gy0, gw, gh = r.game_region()

    def in_view(u: float, v: float) -> bool:
        return 0 <= u < gw and 0 <= v < gh and not loot1.in_ui(u, v)

    offsets = hc.footprint(lambda o: camera.project(o, np.zeros(len(o))), in_view)
    sid = new_session_id(f"hunt-flow{version}")
    log = DemoLog(sid)
    out = OUT / sid
    out.mkdir(parents=True, exist_ok=True)
    frames_dir = REC_ROOT / sid / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena",
              rule=f"{RULE}@{version}", account="gm", map=MAP, minutes=minutes, seed=seed,
              start=list(start), change=VERSIONS[version], params=prm,
              area_cells=int(area.sum()), scored=True, immunity=why_imm, rec_dir=str(out),
              frames_dir=str(frames_dir), gm_profile="hunt-flow")  # fmt: skip
    print(json.dumps({"session": sid, "version": version, "start": time.strftime("%H:%M:%S")}),
          flush=True)  # fmt: skip
    events_f = (log.dir / "events.jsonl").open("a")
    clicks_f = (log.dir / "clicks.jsonl").open("a")

    def ev(rec: dict[str, Any]) -> None:
        events_f.write(json.dumps({"t_ns": r.ns(), **rec}, default=str) + "\n")
        events_f.flush()

    def click_log(rec: dict[str, Any]) -> None:
        clicks_f.write(json.dumps(rec, default=str) + "\n")
        clicks_f.flush()

    split = f0.Split(dict.fromkeys(("searching", "steering", "striking", "fighting", "stopping",
                                    "checks"), 0.0))  # fmt: skip
    engagements: list[dict[str, Any]] = []
    cov = hc.Coverage(area)
    ended, run_s, t_run0 = "time_box", 0.0, time.monotonic()
    crashed: BaseException | None = None
    t_first = r.ns()
    ctx = mp.get_context("spawn")
    stop_rec = ctx.Event()
    rec = ctx.Process(target=route_demo._record, args=(str(frames_dir), (gx0, gy0, gw, gh),
                                                       stop_rec, REC_HZ, REC_QUALITY),
                      daemon=True)  # fmt: skip
    plan_tok = route_plan.enable(f"hunt-flow{version}-{sid}", MAP,
                                 log_path=str(out / "live.jsonl"))  # fmt: skip
    sampler = None
    with r.session(f"rule:{RULE}@{version}") as (agent, screen):
        f0.stop_on_takeover(agent)
        hud_tok = operator_hud.enable(f"hunt-flow@{version}", agent=agent,
                                      log_path=str(out / "hud.jsonl"))  # fmt: skip
        det = unit_detector.UnitDetector()
        rec.start()
        try:
            import walk11 as w11

            w11.UNITS["detector"] = det
            w11.UNITS["ms_per_cell"] = MS_CELL
            w11.UNITS["memory"] = w15.NpcClearMemory()
            pr = cursor_gate.prober(agent, screen)  # robust2
            digits = selfpos.load_digit_templates()
            relocalise = w15.where_relocalise(wf.load_templates(wf.TEMPLATES_V2))
            band, noentry = rr.ec_band(), np.load(w5.NOENTRY_MASK)
            world = w5.World(camera, gat, start)
            from poring_env import weight as wt

            rig = loot1.Rig(agent, screen, pr, det, camera, gat, gat.walkable(), digits,
                            wt.load_weight_glyphs(r.ROOT / wt.DEFAULT_TEMPLATES),
                            loot1.chat_cue.load_cues(), operator_hud.sender())  # fmt: skip

            def note(line: str, boxes: Any = ()) -> None:
                loot1.hud(rig, line, boxes)

            def frame() -> Any:
                return screen.grab(gx0, gy0, gw, gh)[1]

            def read_position() -> Cell | None:
                xy = selfpos.read_minimap_xy(frame()[:, :, :3], digits)
                return None if xy is None else (int(xy[0]), int(xy[1]))

            last_fix = [0.0]
            pos_box: list[Cell] = [start]

            def settle(timeout: float = 5.0) -> Cell | None:
                """Our cell once the GM stands: two minimap reads 0.3 s apart agree; else the
                reckoned cell when a fix is under a minute old; else /where once; else stop."""
                end = time.monotonic() + timeout
                while time.monotonic() < end:
                    a = read_position()
                    time.sleep(0.3)
                    b = read_position()
                    if a is not None and a == b and ok[a[1], a[0]]:
                        last_fix[0] = time.monotonic()
                        return a
                if time.monotonic() - last_fix[0] < 60.0:
                    ev({"kind": "reckoned_fix", "cell": list(pos_box[0])})
                    return pos_box[0]
                world.position = pos_box[0]
                got = relocalise(agent, screen, world, noentry, band)
                bench.close_chat(agent, screen)
                ev({"kind": "where_fix", "ok": bool(got.get("ok")), "to": list(world.position)})
                if got.get("ok"):
                    return tuple(world.position)  # type: ignore[return-value]
                raise f0.FarmStop("our cell is unknown (minimap and /where both failed)")

            last_check = [0.0]

            def check(where: str) -> None:
                prev = split._cat
                split.to("checks", time.monotonic())
                st = f0.client_state(agent, screen)
                last_check[0] = time.monotonic()
                if st["decision"]["do"] != "clear":
                    shot = r.to_png(st["frame"], log.dir / f"stop-{len(engagements)}.png")
                    raise f0.FarmStop(f"client state at {where}: {st['decision']} (frame {shot})")
                hp = gm_vitals.hp_fraction(frame()[..., :3])
                if hp < f0.HP_STOP:
                    raise f0.FarmStop(f"HP {hp:.2f} at {where}: an immune GM lost HP")
                split.to(prev, time.monotonic())

            def cell_of(b: Any, here: Cell, w: Any = None) -> tuple[Cell | None, float]:
                w_ = world if w is None else w  # v2: the perception thread has its own World
                fu, fv = f1.foot(b)
                off = picking.pick_cells(camera, gat, here,
                                         np.array([[fu, fv - loot1.FOOT_LIFT]]))[0]  # fmt: skip
                if abs(int(off[0])) > 1000:
                    return None, 1.0
                c = (here[0] + int(off[0]), here[1] + int(off[1]))
                w_.position = here
                p = w_.project([c, (c[0] + 1, c[1])])
                p0 = w_.project([here, (here[0] + 1, here[1])])
                px0 = float(np.hypot(*(p0[1] - p0[0])))
                return c, (float(np.hypot(*(p[1] - p[0]))) / px0 if px0 > 0 else 1.0)

            def sightings_in(boxes: Any, here: Cell, w: Any = None) -> list[tuple[Any, Cell]]:
                """hunt@6's selection gates on one frame's boxes."""
                got_ = []
                for b in boxes:
                    if b.cls != "monster":
                        continue
                    c, scale = cell_of(b, here, w)
                    if c is None or not (0 <= c[0] < area.shape[1] and 0 <= c[1] < area.shape[0]):
                        continue
                    if f1.native_size(b, scale) > f1.MAX_NATIVE_PX:
                        continue  # Creamy (a metamorphosed Pupa) is no target
                    if min(b.x1 - b.x0, b.y1 - b.y0) < prm["min_box_px"]:
                        continue  # a floor item
                    if loot1.in_ui(*f1.centre(b)) or not area[c[1], c[0]]:
                        continue
                    got_.append((b, c))
                return got_

            def rp(cmd: str, *a: Any) -> None:
                pub = route_plan.publisher()
                if pub is None:
                    return
                with contextlib.suppress(Exception):
                    if cmd == "route":
                        world.position = a[0]
                        route_plan.preview(agent, world, a[0], a[1], None, f"hunt-flow@{version}")
                    elif cmd == "walk":
                        pub.walk(a[0], a[1], MS_CELL, a[2])
                    elif cmd == "snap":
                        pub.snap(a[0])
                    else:
                        pub.clear()

            def step_target(pth: list[Cell], from_i: int, at: Cell, ahead: int,
                            grid: Any = None, need_clear: bool = False
                            ) -> tuple[int | None, tuple[float, float]]:  # fmt: skip
                """The farthest path index in (from_i, from_i + ahead] whose point is in view,
                off the UI and on ``grid`` (the search area by default), seen from ``at``; with
                ``need_clear`` (v2, a click while moving) also clear of units (option B)."""
                g_ = area if grid is None else grid
                world.position = at
                hi = min(len(pth) - 1, from_i + ahead)
                for jj in range(hi, from_i, -1):
                    uu, vv = (float(c) for c in world.project([pth[jj]])[0])
                    if in_view(uu, vv) and g_[pth[jj][1], pth[jj][0]] and (
                            not need_clear or units_clear(uu, vv)):  # fmt: skip
                        return jj, (uu, vv)
                return None, (0.0, 0.0)

            def tracked_clear(u: float, v: float) -> bool:
                """v3: no tracked monster predicted within track_clear_px over track_clear_s."""
                if not prm.get("track_clear"):
                    return True
                here_ = pos_box[0]

                def project(c: Any) -> tuple[float, float]:
                    world.position = here_
                    q = world.project([c])[0]
                    return float(q[0]), float(q[1])

                return track_clear(u, v, tracks_now(), r.ns(), prm["track_clear_s"],
                                   prm["track_clear_px"], project)  # fmt: skip

            def units_clear(u: float, v: float) -> bool:
                """3.39 deviation (2) option B: no detector unit within unit_clear_px of the
                point on the last clear_frames fresh frames; v3: on every frame of the last
                gate_frames_s, and no tracked monster predicted there (tracked_clear)."""
                if prm.get("gate_frames_s"):
                    t_min = r.ns() - int(prm["gate_frames_s"] * 1e9)
                    k_ = len(sampler.frames)
                    rec_ = [f for f in sampler.since(max(0, k_ - 8)) if f[0] >= t_min]
                    return (bool(rec_) and all(
                        np.hypot(*(np.array(f1.centre(b)) - (u, v))) > prm["unit_clear_px"]
                        for _t, bs in rec_ for b in bs) and tracked_clear(u, v))  # fmt: skip
                rec_ = sampler.since(max(0, len(sampler.frames) - prm["clear_frames"]))
                return (len(rec_) >= prm["clear_frames"]
                        and (r.ns() - rec_[-1][0]) / 1e9 <= prm["fresh_s"]
                        and all(np.hypot(*(np.array(f1.centre(b)) - (u, v)))
                                > prm["unit_clear_px"] for _t, bs in rec_ for b in bs))  # fmt: skip

            # --- start --------------------------------------------------------------------------
            import chat_guard

            chat_guard.start_run(f"hunt-flow{version}-{sid}")
            before = gm_state.ensure_fixed(agent, screen, why=f"hunt-flow@{version}:before",
                                           out_dir=log.dir / "gm_state", profile="hunt-flow",
                                           loot=True)  # fmt: skip
            ev({"kind": "gm_state_before", **f0._brief(before)})
            r.gm(agent, screen, f"@warp {MAP} {start[0]} {start[1]}")
            time.sleep(rr.SCENE_ENTRY_S)
            bench.close_chat(agent, screen)
            r.activate_client(agent, screen)
            sampler = loot1.Sampler(det)
            sampler.start()
            pos = settle() or start
            if cheb(pos, start) > 3:
                raise f0.FarmStop(f"the start @warp did not land: at {pos}, not {start}")
            reck = hc.Reckoner(MS_CELL)
            posm = PositionModel(MS_CELL, pos)  # v2: shared with the perception thread
            deadline = time.monotonic() + minutes * 60
            t_run0 = time.monotonic()
            ev({"kind": "loop_start"})
            path: list[Cell] = []
            pi = 0
            moving = False
            refused = 0
            bad_tiles: list[Cell] = []
            click_from: Cell | None = None
            click_cell: Cell | None = None
            unfollowed: dict[Cell, int] = {}
            last_mm, mm_off = 0.0, 0
            last_walk = 0.0
            last_weight = time.monotonic()
            last_progress = [time.monotonic()]
            tracks: list[Track] = []
            next_id = 0
            kf = 0
            target: Track | None = None
            reads = 0
            banned: list[tuple[float, Cell]] = []
            eng: dict[str, Any] | None = None
            k = 0
            split.to("searching", time.monotonic())

            import threading

            plock = threading.Lock()
            plan: dict[str, Any] = {"queue": [], "goal_path": None, "t_goal": 0.0}
            refusals: dict[Cell, int] = {}

            def refuse(to: Cell, why: str) -> None:
                """v2 attempt 2 (Batt 11:46, the GM stuck on a ledge: "if char can't move you
                should click in available field in map"): a NO-ENTRY read blocks that spot at once,
                any other refusal after 2; the blocked cells (radius 1) leave the area and the stand
                grid, and the planner re-plans. v2 attempt 1 retried (194,128) 108 times."""
                n_ = refusals.get(to, 0) + 1
                refusals[to] = n_
                if "noentry" in why or n_ >= 2:
                    x_, y_ = to
                    area[max(0, y_ - 1) : y_ + 2, max(0, x_ - 1) : x_ + 2] = False
                    ok[max(0, y_ - 1) : y_ + 2, max(0, x_ - 1) : x_ + 2] = False
                    ev({"kind": "spot_blocked", "cell": list(to), "why": why, "refusals": n_})
                    if prm.get("pipelined"):
                        with plock:
                            plan["goal_path"] = None

            def walk_click(u: float, v: float, to: Cell, seg: list[Cell], gate: str,
                           why: str) -> bool:  # fmt: skip
                """One walk click: cursor-gated from a standstill, map+units while moving."""
                nonlocal moving, click_from, click_cell, last_walk
                t_c = r.ns()
                if gate == "cursor":
                    if prm.get("track_clear") and not tracked_clear(u, v):
                        ev({"kind": "walk_click", "gate": gate, "to": list(to), "clicked": False,
                            "why": "tracked_monster_near"})  # fmt: skip
                        return False
                    got = cursor_gate.gated_click(pr, u, v, allow=("walk",))
                    if not got["clicked"]:
                        ev({"kind": "walk_click", "gate": gate, "to": list(to), "clicked": False,
                            "why": got["why"]})  # fmt: skip
                        refuse(to, str(got["why"]))
                        return False
                    t_c = int(got["t_click"])
                    click_from, click_cell = seg[0], to
                else:
                    agent.click(gx0 + round(u), gy0 + round(v))
                click_log({"t": t_c, "u": round(u, 1), "v": round(v, 1), "kind": "walk",
                           "gate": gate, "to": list(to), "why": why})  # fmt: skip
                ev({"kind": "walk_click", "gate": gate, "to": list(to), "why": why})
                reck.go(seg, time.monotonic())
                posm.go(seg, time.monotonic())
                rp("walk", seg[0], seg, t_c)
                moving = True
                last_walk = time.monotonic()
                last_progress[0] = time.monotonic()
                return True

            def strike(tr: Track, here: Cell, again: bool) -> bool:
                """Park, hover the target's newest box, ONE robust2 read; SWORD -> the attack
                click there. True when it clicked."""
                nonlocal eng, k, reads
                prev = split._cat
                split.to("striking", time.monotonic())
                ok_park = pr.park()
                fr = sampler.since(max(0, len(sampler.frames) - 1))
                b = tr.box
                if fr and (r.ns() - fr[-1][0]) / 1e9 <= prm["fresh_s"]:
                    near_ = [x for x, c in sightings_in(fr[-1][1], here)
                             if cheb(c, tr.predict(fr[-1][0])) <= prm["track_near"]]  # fmt: skip
                    if near_:
                        b = min(near_, key=lambda x: np.hypot(*(np.array(f1.foot(x))
                                                                 - f1.foot(tr.box))))  # fmt: skip
                u, v = f1.centre(b)
                if not ok_park or loot1.in_ui(u, v):
                    split.to(prev, time.monotonic())
                    return False
                pr.hover(u, v)
                shape = pr.read(u, v)["shape"]
                pc = tr.predict(r.ns())
                hov = {"t": r.ns(), "at": [round(u, 1), round(v, 1)], "read": shape,
                       "age_ms": round((r.ns() - tr.box_t) / 1e6),
                       "pred_cell": [round(pc[0], 2), round(pc[1], 2)]}  # fmt: skip
                if shape != "sword":
                    reads += 1
                    note(f"read {shape}: no click")
                    if eng is not None:
                        eng["hovers"].append(hov)
                    split.to(prev, time.monotonic())
                    return False
                tc = r.ns()
                agent.click(gx0 + round(u), gy0 + round(v))
                hov["clicked"] = tc
                pr.park()
                click_log({"t": tc, "u": round(u, 1), "v": round(v, 1), "kind": "strike",
                           "track": tr.tid, "pred_cell": hov["pred_cell"],
                           "again": again})  # fmt: skip
                if eng is None or eng["track"] != tr.tid:
                    eng = {"k": k, "track": tr.tid, "t_seen": tr.t_first, "t_first_click": tc,
                           "here": list(here), "pred_cell": hov["pred_cell"], "hovers": [],
                           "clicks": 0, "result": None}  # fmt: skip
                    k += 1
                eng["hovers"].append(hov)
                eng["clicks"] += 1
                eng["t_last_click"] = tc
                reads = 0
                note(f"SWORD -> attack click {eng['clicks']} (track {tr.tid})", [b])
                split.to("fighting", time.monotonic())
                last_progress[0] = time.monotonic()
                return True

            done_ids: set[int] = set()  # v4: engaged tracks never dispatched again

            def end_engagement(result: str) -> None:
                nonlocal eng, target
                if eng is not None:
                    done_ids.add(int(eng["track"]))
                    eng.update(result=result, t_end=r.ns())
                    engagements.append(eng)
                    brief = {k_: eng.get(k_) for k_ in ("k", "track", "result", "clicks")}
                    ev({"kind": "engagement", **brief})
                    print(json.dumps(brief), flush=True)
                eng = None
                target = None

            # --- v2: PIPELINED (Batt ~11:30): perception + planner threads, the executor below --
            halt = threading.Event()
            pstate: dict[str, Any] = {"tracks": [], "next_id": 0}
            world_p = w5.World(camera, gat, start)  # the perception thread's own camera model

            def tracks_now() -> list[Track]:
                with plock:
                    return list(pstate["tracks"])

            def perception() -> None:
                """Every detector frame into the tracks, on the frame's own time and our cell
                then (the shared position model)."""
                kf_ = 0
                while not halt.is_set():
                    new_ = sampler.since(kf_)
                    kf_ += len(new_)
                    for t_fr, boxes in new_:
                        age = (r.ns() - t_fr) / 1e9
                        here_fr = posm.at(time.monotonic() - age)
                        sts = sightings_in(boxes, here_fr, world_p)
                        with plock:
                            pstate["tracks"], pstate["next_id"] = update_tracks(
                                pstate["tracks"], t_fr, sts, pstate["next_id"],
                                prm["track_near"], prm["track_drop_s"])  # fmt: skip
                    if not new_:
                        time.sleep(0.02)

            def planner() -> None:
                """The queue (chained, standing first) every plan_every_s, and the next exploration
                waypoint (the coverage plan's stalest tile) always held."""
                while not halt.is_set():
                    now_, t_ = time.monotonic(), r.ns()
                    here_ = posm.at(now_)
                    q = plan_queue(tracks_now(), here_, t_, prm["queue_depth"], list(banned),
                                   now_, prm["drop_target_s"], prm["moving_penalty"])  # fmt: skip
                    gp = plan["goal_path"]
                    if (gp is None or now_ - plan["t_goal"] > prm["waypoint_every_s"]
                            or cheb(here_, gp[-1]) <= 2):  # fmt: skip
                        p_ = None
                        if area[here_[1], here_[0]]:
                            goal = hc.choose_goal(cov, here_, now_, {}, list(bad_tiles))
                            p_ = None if goal is None else hc.astar(area, here_, goal)
                            if (p_ is None or len(p_) < 2) and goal is not None:
                                bad_tiles.append((goal[0] - goal[0] % hc.TILE,
                                                  goal[1] - goal[1] % hc.TILE))  # fmt: skip
                                if len(bad_tiles) > 40:
                                    bad_tiles.clear()
                        else:
                            back = hc.nearest_in(area, ok, here_)
                            p_ = None if back is None else hc.astar(ok, here_, back)
                        if p_ is not None and len(p_) >= 2:
                            gp = p_
                            with plock:
                                plan["t_goal"] = now_
                    with plock:
                        plan["queue"], plan["goal_path"] = q, gp
                    time.sleep(prm["plan_every_s"])

            def quick_fix() -> Cell:
                """Our cell at a hand-off: one minimap read near where we were (no settle wait),
                else the settle."""
                mm_ = read_position()
                if mm_ is not None and ok[mm_[1], mm_[0]] and cheb(mm_, pos) <= 4:
                    return mm_
                return settle(timeout=1.5) or pos

            def pipelined_loop() -> None:  # noqa: PLR0915
                nonlocal pos, moving, path, pi, target, reads, last_mm, mm_off, last_weight
                nonlocal click_from, click_cell
                ths = [_start_thread(perception, "perception"), _start_thread(planner, "planner")]
                gp_i = 0
                dispatched: set[tuple[int, bool]] = set()
                try:
                    while time.monotonic() < deadline:
                        now = time.monotonic()
                        if eng is None and now - last_check[0] > CHECK_EVERY_S:
                            check("v2")
                        if eng is None and not moving and now - last_weight > WEIGHT_EVERY_S:
                            last_weight = now
                            wnow = gm_state._weight(gm_state._frames(screen))
                            if gm_state.weight_action(wnow, at_restore=False) == "clear":
                                ev({"kind": "weight_clear", "weight": wnow})
                                gm_state.clear_loot(agent, screen, why="hunt-flow:mid-run",
                                                    out_dir=log.dir / "gm_state")  # fmt: skip
                        if moving and reck.remaining(now) == 0:
                            moving = False
                            pos = reck.path[-1] if reck.path else pos
                            posm.stop(pos)
                            rp("snap", pos)
                        est = reck.where(now) if moving else pos
                        if est is not None:
                            pos = est
                        if now - last_mm > MINIMAP_EVERY_S:
                            last_mm = now
                            mm = read_position()
                            if mm is not None and ok[mm[1], mm[0]]:
                                if cheb(mm, pos) <= DRIFT_CELLS:
                                    mm_off = 0
                                    last_fix[0] = time.monotonic()
                                    if not moving:
                                        pos = mm
                                        posm.stop(pos)
                                else:
                                    mm_off += 1
                                    if mm_off >= 2:
                                        ev({"kind": "drift", "reck": list(pos),
                                            "minimap": list(mm)})  # fmt: skip
                                        if (click_from is not None and click_cell is not None
                                                and cheb(mm, click_from) <= 1
                                                and eng is None):  # fmt: skip
                                            n_u = unfollowed.get(click_from, 0)
                                            unfollowed[click_from] = n_u + 1
                                            rad = 1 + min(2, n_u)
                                            cx, cy = click_cell
                                            blk = np.zeros_like(area)
                                            blk[max(0, cy - rad) : cy + rad + 1,
                                                max(0, cx - rad) : cx + rad + 1] = True  # fmt: skip
                                            fx, fy = click_from
                                            blk[max(0, fy - 1) : fy + 2,
                                                max(0, fx - 1) : fx + 2] = False  # fmt: skip
                                            area[blk] = False
                                            ev({"kind": "unfollowed_click",
                                                "from": list(click_from),
                                                "to": list(click_cell), "radius": rad})  # fmt: skip
                                            click_from = click_cell = None
                                        pos = settle() or mm
                                        posm.stop(pos)
                                        moving, path, pi = False, [], 0
                                        mm_off = 0
                        pos_box[0] = pos
                        cov.mark(pos, now, offsets)
                        t_now = r.ns()
                        live = tracks_now()
                        need_c = moving or bool(prm.get("track_clear"))  # v3: the gate everywhere
                        # the engagement in progress: dead -> HAND-OFF at once; re-click; give up
                        if eng is not None:
                            tr = next((x for x in live if x.tid == eng["track"]), None)
                            since_first = (t_now - eng["t_first_click"]) / 1e9
                            since_last = (t_now - eng["t_last_click"]) / 1e9
                            unseen = (t_now - tr.t_last) / 1e9 if tr is not None else 99.0
                            done = None
                            if since_last >= prm["dead_min_s"] and unseen >= prm["dead_gone_s"]:
                                done = "dead"
                            elif since_first > prm["give_up_s"]:
                                banned.append((now, tuple(int(x) for x in eng["pred_cell"])))
                                done = "gave_up"
                            if done is None:
                                if since_last >= prm["reclick_s"] and tr is not None and not moving:
                                    strike(tr, pos, again=True)
                                time.sleep(0.02)
                                continue
                            end_engagement(done)
                            ev({"kind": "hand_off", "after": done})
                            pos = quick_fix()
                            posm.stop(pos)
                            moving, path, pi = False, [], 0
                            live = tracks_now()
                            t_now = r.ns()
                        with plock:
                            q, gp = list(plan["queue"]), plan["goal_path"]
                        # dispatch: queue[0], revalidated on the freshest frame
                        if target is not None and not valid_at_dispatch(
                                target, live, t_now, prm["track_drop_s"]):  # fmt: skip
                            nt = None
                            if prm.get("reacquire"):  # v4: the same monster under a new id
                                nt = reacquire_target(target, live, t_now,
                                                      prm["reacquire_cells"],
                                                      list(done_ids))  # fmt: skip
                            if nt is not None:
                                ev({"kind": "target_reacquired", "track": target.tid,
                                    "as": nt.tid})  # fmt: skip
                                target = nt
                            else:
                                ev({"kind": "target_lost", "track": target.tid})
                                target = None
                        if target is None and q:
                            for rank, cand in enumerate(q):
                                if prm.get("dispatch_fixes") and (
                                        cand.tid in done_ids or any(
                                            now - tb < prm["drop_target_s"]
                                            and cheb(cand.predict(t_now), cb) <= 2
                                            for tb, cb in banned)):  # fmt: skip
                                    continue  # v4: a finished or dropped target, not again
                                ok_ = valid_at_dispatch(cand, live, t_now, prm["dispatch_fresh_s"])
                                if (cand.tid, ok_) not in dispatched:  # one record per candidate
                                    dispatched.add((cand.tid, ok_))
                                    pc_ = cand.predict(t_now)
                                    ev({"kind": "dispatch", "track": cand.tid, "rank": rank,
                                        "q_len": len(q), "valid": ok_,
                                        "cell": [round(pc_[0], 1), round(pc_[1], 1)]})  # fmt: skip
                                if ok_:
                                    target, reads = cand, 0
                                    break
                        if target is not None:
                            split.to("steering", time.monotonic())
                            tcell = target.predict(t_now)
                            s_range = strike_range(target, prm)
                            if strike_due(moving, pos, tcell, s_range):
                                if (not strike(target, pos, again=False)
                                        and reads >= prm["max_reads"]):  # fmt: skip
                                    banned.append((now, (int(round(tcell[0])),
                                                         int(round(tcell[1])))))  # fmt: skip
                                    ev({"kind": "target_dropped", "track": target.tid,
                                        "why": "no_sword", "reads": reads})  # fmt: skip
                                    target = None
                                continue
                            if cheb(pos, tcell) <= s_range:
                                time.sleep(0.02)  # walking, about to arrive: the strike is next
                                continue
                            if not moving or now - last_walk >= prm["walk_every_s"]:
                                ap = approach_path(ok, pos, tcell, prm["short"])
                                if ap is None:
                                    ev({"kind": "target_dropped", "track": target.tid,
                                        "why": "no_path"})  # fmt: skip
                                    banned.append((now, (int(round(tcell[0])),
                                                         int(round(tcell[1])))))  # fmt: skip
                                    target = None
                                    continue
                                path, pi = ap, 0
                                j, (u, v) = step_target(path, 0, pos, prm["ahead"], ok,
                                                        need_clear=need_c)  # fmt: skip
                                if j is not None:
                                    gate_ = "map+units" if moving else "cursor"
                                    walk_click(u, v, path[j], path[: j + 1], gate_, "steer")
                                    pi = j
                            time.sleep(0.02)
                            continue
                        # no target: the planner's waypoint, the GM never standing
                        split.to("searching", time.monotonic())
                        if gp is None:
                            time.sleep(0.02)
                            continue
                        if not moving or now - last_walk >= prm["walk_every_s"]:
                            cur = (reck.where(now + 0.15) or pos) if moving else pos
                            ci = gp.index(cur) if cur in gp else (gp_i if gp_i < len(gp) else 0)
                            if not moving and cur not in gp:
                                # the plan was made from another cell: walk to its nearest point
                                ci = min(range(len(gp)), key=lambda i_: cheb(gp[i_], cur))
                            j, (u, v) = step_target(gp, ci, cur, prm["ahead"],
                                                    need_clear=need_c)  # fmt: skip
                            if j is not None and j > ci:
                                seg = gp[ci : j + 1] if cur in gp else [cur, gp[j]]
                                gate_ = "map+units" if moving else "cursor"
                                if walk_click(u, v, gp[j], seg, gate_, "search"):
                                    gp_i = j
                            elif not moving:
                                with plock:
                                    plan["goal_path"] = None  # nothing clickable: re-plan
                        time.sleep(0.02)
                finally:
                    halt.set()
                    for th in ths:
                        th.join(timeout=3)

            while not prm.get("pipelined") and time.monotonic() < deadline:
                now = time.monotonic()
                if eng is None and now - last_check[0] > CHECK_EVERY_S:
                    check("searching")
                if eng is None and now - last_weight > WEIGHT_EVERY_S and not moving:
                    last_weight = now
                    fa, fb = gm_state._frames(screen)
                    wnow = gm_state._weight((fa, fb))
                    if gm_state.weight_action(wnow, at_restore=False) == "clear":
                        ev({"kind": "weight_clear", "weight": wnow})
                        gm_state.clear_loot(agent, screen, why="hunt-flow:mid-run",
                                            out_dir=log.dir / "gm_state")  # fmt: skip
                # where we are: reckoned while moving, corrected by the minimap
                if moving and reck.remaining(now) == 0:
                    moving = False
                    pos = reck.path[-1] if reck.path else pos
                    rp("snap", pos)
                est = reck.where(now) if moving else pos
                if est is not None:
                    pos = est
                if now - last_mm > MINIMAP_EVERY_S:
                    last_mm = now
                    mm = read_position()
                    if mm is not None and ok[mm[1], mm[0]]:
                        if cheb(mm, pos) <= DRIFT_CELLS:
                            mm_off = 0
                            last_fix[0] = time.monotonic()
                            if not moving:
                                pos = mm
                        else:
                            mm_off += 1
                            if mm_off >= 2:  # the reckoning drifted (or a walk-in moved us)
                                ev({"kind": "drift", "reck": list(pos), "minimap": list(mm)})
                                if (click_from is not None and click_cell is not None
                                        and cheb(mm, click_from) <= 1 and eng is None):  # fmt: skip
                                    # hunt@8's unstick: that cursor-gated click was not followed
                                    n_u = unfollowed.get(click_from, 0)
                                    unfollowed[click_from] = n_u + 1
                                    rad = 1 + min(2, n_u)
                                    cx, cy = click_cell
                                    blk = np.zeros_like(area)
                                    blk[max(0, cy - rad) : cy + rad + 1,
                                        max(0, cx - rad) : cx + rad + 1] = True  # fmt: skip
                                    fx, fy = click_from
                                    blk[max(0, fy - 1) : fy + 2, max(0, fx - 1) : fx + 2] = False
                                    area[blk] = False
                                    ev({"kind": "unfollowed_click", "from": list(click_from),
                                        "to": list(click_cell), "radius": rad})  # fmt: skip
                                    click_from = click_cell = None
                                split.to("stopping", time.monotonic())
                                pos = settle() or mm
                                moving, path, pi = False, [], 0
                                mm_off = 0
                                split.to("searching", time.monotonic())
                pos_box[0] = pos
                cov.mark(pos, now, offsets)
                # perception: every new detector frame into the tracks
                new = sampler.since(kf)
                kf += len(new)
                for t_fr, boxes in new:
                    age = (r.ns() - t_fr) / 1e9
                    here_fr = (reck.where(now - age) if moving else pos) or pos
                    tracks, next_id = update_tracks(tracks, t_fr, sightings_in(boxes, here_fr),
                                                    next_id, prm["track_near"],
                                                    prm["track_drop_s"])  # fmt: skip
                t_now = r.ns()
                # the engagement in progress: dead, a re-click, or a give-up
                if eng is not None:
                    tr = next((x for x in tracks if x.tid == eng["track"]), None)
                    since_first = (t_now - eng["t_first_click"]) / 1e9
                    since_last = (t_now - eng["t_last_click"]) / 1e9
                    unseen = (t_now - tr.t_last) / 1e9 if tr is not None else 99.0
                    # a death needs dead_min_s since the click: the client's walk-in scrolls the
                    # camera, and a walk click sent early would cancel the attack
                    if since_last >= prm["dead_min_s"] and unseen >= prm["dead_gone_s"]:
                        end_engagement("dead")
                        note("target gone: next")
                        pos = settle(timeout=1.5) or pos  # the walk-in moved us
                        moving, path, pi = False, [], 0
                        split.to("searching", time.monotonic())
                        continue
                    if since_first > prm["give_up_s"]:
                        banned.append((now, tuple(int(x) for x in eng["pred_cell"])))
                        end_engagement("gave_up")
                        pos = settle(timeout=1.5) or pos
                        moving, path, pi = False, [], 0
                        split.to("searching", time.monotonic())
                        continue
                    if since_last >= prm["reclick_s"] and tr is not None and not moving:
                        strike(tr, pos, again=True)
                    time.sleep(0.03)
                    continue
                # the queue: the nearest track
                if target is not None and target not in tracks:
                    target = None
                if target is None:
                    target = choose(tracks, pos, t_now, banned, now, prm["drop_target_s"])
                    reads = 0
                    if target is not None:
                        ev({"kind": "target", "track": target.tid,
                            "cell": [round(x, 1) for x in target.predict(t_now)]})  # fmt: skip
                if target is not None:
                    tcell = target.predict(t_now)
                    if strike_due(moving, pos, tcell, prm["strike_cells"]):
                        if not strike(target, pos, again=False) and reads >= prm["max_reads"]:
                            banned.append((now, (int(round(tcell[0])), int(round(tcell[1])))))
                            ev({"kind": "target_dropped", "track": target.tid,
                                "why": "no_sword", "reads": reads})  # fmt: skip
                            target = None
                        continue
                    if cheb(pos, tcell) <= prm["strike_cells"]:  # moving, about to arrive
                        time.sleep(0.03)
                        continue
                    if not moving or now - last_walk >= prm["walk_every_s"]:
                        split.to("steering", time.monotonic())
                        ap = approach_path(ok, pos, tcell, prm["short"])
                        if ap is not None:
                            path, pi = ap, 0
                            j, (u, v) = step_target(path, 0, pos, prm["ahead"], ok)
                            if j is not None:
                                if not moving:
                                    walk_click(u, v, path[j], path[: j + 1], "cursor", "steer")
                                elif units_clear(u, v):
                                    walk_click(u, v, path[j], path[: j + 1], "map+units",
                                               "steer")  # fmt: skip
                                pi = j
                        else:
                            ev({"kind": "target_dropped", "track": target.tid, "why": "no_path"})
                            banned.append((now, (int(round(tcell[0])), int(round(tcell[1])))))
                            target = None
                    time.sleep(0.03)
                    continue
                # no target: search, never standing
                split.to("searching", time.monotonic())
                if now - last_progress[0] > STUCK_S:
                    raise f0.FarmStop(f"no progress for {STUCK_S:.0f} s at {pos}: stopped")
                if not moving:
                    if pi >= len(path) - 1:
                        if not area[pos[1], pos[0]]:
                            back = hc.nearest_in(area, ok, pos)
                            got_path = None if back is None else hc.astar(ok, pos, back)
                            if got_path is None or len(got_path) < 2:
                                raise f0.FarmStop(f"outside the search area at {pos}, no way back")
                            path, pi = got_path, 0
                        else:
                            goal = hc.choose_goal(cov, pos, now, {}, bad_tiles)
                            got_path = None if goal is None else hc.astar(area, pos, goal)
                            if got_path is None or len(got_path) < 2:
                                if goal is not None:
                                    bad_tiles.append((goal[0] - goal[0] % hc.TILE,
                                                      goal[1] - goal[1] % hc.TILE))  # fmt: skip
                                if goal is None or len(bad_tiles) > 40:
                                    bad_tiles = []
                                pos = settle(timeout=2.0) or pos
                                continue
                            path, pi = got_path, 0
                            rp("route", pos, hc.waypoints(path))
                            ev({"kind": "route", "from": list(pos), "goal": list(goal),
                                "cells": len(path)})  # fmt: skip
                    j, (u, v) = step_target(path, pi, pos, prm["ahead"])
                    if j is None:
                        path, pi = [], 0
                        continue
                    if walk_click(u, v, path[j], path[pi : j + 1], "cursor", "search"):
                        refused = 0
                        pi = j
                    else:
                        refused += 1
                        if refused >= 3:
                            bad_tiles.append((path[-1][0] - path[-1][0] % hc.TILE,
                                              path[-1][1] - path[-1][1] % hc.TILE))  # fmt: skip
                            path, pi, refused = [], 0, 0
                elif now - last_walk >= prm["walk_every_s"] and pi < len(path) - 1:
                    cur = reck.where(now + 0.15) or pos
                    ci = path.index(cur) if cur in path else pi
                    j, (u, v) = step_target(path, ci, cur, prm["ahead"])
                    if j is not None and j > ci and units_clear(u, v):
                        walk_click(u, v, path[j], path[ci : j + 1], "map+units", "search")
                        pi = j
                time.sleep(0.03)
            if prm.get("pipelined"):
                pipelined_loop()
            if eng is not None:
                end_engagement("time_box")
            split.to(None, time.monotonic())
            run_s = time.monotonic() - t_run0
        except BaseException as exc:
            split.to(None, time.monotonic())
            ended = f"stopped:{type(exc).__name__}: {str(exc)[:200]}"
            run_s = time.monotonic() - t_run0
            if not isinstance(exc, (r.Stop, KeyboardInterrupt)):
                crashed = exc
        finally:
            stop_rec.set()
            if rec.is_alive():
                rec.join(timeout=5)
            if sampler is not None:
                sampler.stop()
                with (log.dir / "boxes.jsonl").open("w") as fh:  # the judge's first-seen
                    for t_b, bs in sampler.frames:
                        fh.write(json.dumps({"t": int(t_b), "boxes": [
                            [round(b.x0, 1), round(b.y0, 1), round(b.x1, 1), round(b.y1, 1),
                             round(b.score, 3), b.cls] for b in bs]}) + "\n")  # fmt: skip
            with contextlib.suppress(Exception):
                det.close()
            route_plan.disable(plan_tok)
            operator_hud.disable(hud_tok)
        after: dict[str, Any] = {"skipped": ended}
        if ended == "time_box":
            with contextlib.suppress(r.Stop):
                after = f0._brief(gm_state.ensure_fixed(agent, screen,
                                                        why=f"hunt-flow@{version}:after",
                                                        out_dir=log.dir / "gm_state",
                                                        profile="hunt-flow"))  # fmt: skip
                bench.close_chat(agent, screen)
        ev({"kind": "gm_state_after", **after})
    events_f.close()
    clicks_f.close()
    events, anchor = record_session.write_packets(log.dir, t_first, r.ns())
    (log.dir / "engagements.json").write_text(json.dumps(engagements, default=str))
    summary = {"run_s": round(run_s, 1), "engagements": len(engagements),
               "results": dict(Counter(e["result"] for e in engagements)),
               "split": split.ranked(), "coverage_cells": cov.first_seen,
               "det_fps": None if sampler is None or not run_s
               else round(len(sampler.frames) / run_s, 2)}  # fmt: skip
    log.finish(ended=ended, packet_events=len(events), packet_anchor=anchor, **summary)
    print(json.dumps({"session": sid, "ended": ended, **summary}, default=str), flush=True)
    if crashed is not None:
        raise crashed
    return 0 if ended == "time_box" else 3


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    rn = sub.add_parser("run")
    rn.add_argument("--version", type=int, required=True)
    rn.add_argument("--minutes", type=float, default=30.0)
    rn.add_argument("--seed", type=int, default=20261201)
    a = ap.parse_args()
    return run(a.version, a.minutes, a.seed)


if __name__ == "__main__":
    sys.exit(main())
