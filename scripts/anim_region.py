#!/usr/bin/env python3
"""anim-region@1: a map's measured ANIMATED region, in cells (Batt 2026-10-15, decision 3: "don't
read through moving scenery, AVOID it. The walk rule (and any hover/click planner) never picks a
point inside a measured per-map ANIMATED region"; docs/demonstrations.md 3.32 amendment 3).

    anim_region.py plan    --map M [--step 8]          offline: the stands, refusals, the time
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
OUT_DIR = ROOT / "data" / "kb" / "anim_regions"
Cell = tuple[int, int]


# --- pure parts (tested) ------------------------------------------------------------------------


def lattice(ok: Any, step: int = STEP, move_within: int = MOVE_WITHIN,
            origin: tuple[int, int] | None = None,
            bounds: tuple[int, int, int, int] | None = None) -> dict[str, list[Any]]:  # fmt: skip
    """Lattice points every ``step`` cells (first at step // 2, or aligned to ``origin``) inside
    ``bounds`` (x0, y0, x1, y1, exclusive ends; default the whole grid). A point on an ``ok`` cell
    is a stand; otherwise the nearest ok cell within ``move_within`` (Chebyshev; ties by y, x) is,
    and the point is listed as moved; with none it is dropped. Stands are unique, in scan order."""
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
                  move_within: int = MOVE_WITHIN) -> list[Cell]:  # fmt: skip
    """Pass 2: a lattice every ``step`` cells within ``radius`` of each stand in ``around``
    (aligned to that stand), minus the stands already measured. Unique, in order."""
    seen = set(done)
    out: list[Cell] = []
    for sx, sy in around:
        got = lattice(
            ok,
            step,
            move_within,
            origin=(sx, sy),
            bounds=(sx - radius, sy - radius, sx + radius + 1, sy + radius + 1),
        )
        for c in got["stands"]:
            if c not in seen:
                seen.add(c)
                out.append(c)
    return out


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


def plan(map_name: str, step: int) -> dict[str, Any]:
    import npc_click_score as ncs

    _, gat = ncs.load_map(map_name)
    lat = lattice(stand_grid(map_name, gat), step)
    n = len(lat["stands"])
    return {"map": map_name, "step": step, "stands": n, "moved": len(lat["moved"]),
            "dropped": len(lat["dropped"]),
            "est_minutes_pass1": round(n * 7.0 / 60, 1)}  # fmt: skip


def measure(map_name: str, step: int, refine_step: int, radius: int) -> int:
    import bench
    import cursor_anim as ca
    import npc_click_score as ncs
    import npc_click_test as t
    import record_session
    import ro_agent as r
    import rule_run as rr
    import talk1

    from poring_env import npc_dialog as nd
    from poring_env import ui_anchors as ua
    from poring_env.demo import Action, DemoLog, DemoRecord, Intended, Outcome, new_session_id

    camera, gat = ncs.load_map(map_name)
    ok = stand_grid(map_name, gat)
    lat = lattice(ok, step)
    reg = ua.default_registry()
    sizes = {n: s.size for n, s in reg.windows.items()}
    sid = new_session_id(f"anim-region-{map_name}")
    log = DemoLog(sid)
    (log.dir / "views").mkdir(exist_ok=True)
    log.start(rule=RULE, map=map_name, step=step, refine_step=refine_step, radius=radius,
              stands=len(lat["stands"]), moved=lat["moved"], dropped=lat["dropped"],
              commit=_commit(), park=list(PARK))  # fmt: skip
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
            first_pass: dict[Cell, dict[str, Any]] = {}
            for s in lat["stands"]:
                first_pass[s] = one(tuple(s), "pass1")
            confirmed = _recheck(first_pass, one, "pass1-recheck")
            keep = [s for s, m in confirmed.items() if m.any()]
            more = refine_stands(keep, ok, first_pass, refine_step, radius)
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
    views: dict[Cell, set[Cell]] = {}
    for stand, masks in by_stand.items():
        if len(masks) < 2:  # a view without animation was measured once: nothing to confirm
            continue
        both = masks[0] & masks[1]

        def pick(px: Any, s: Cell = stand) -> Any:
            return pick_cells(camera, gat, s, px)

        views[stand] = view_cells(both, pick, stand)
    region = sorted(region_of(views))
    doc = {"map": map_name, "rule": RULE, "sessions": list(sessions), "built_at":
           time.strftime("%Y-%m-%dT%H:%M:%S%z"), "commit": _commit(), "grow_cells": GROW_CELLS,
           "stands_measured": len(by_stand), "views_with_cells": len(views),
           "per_view": {f"{s[0]},{s[1]}": len(c) for s, c in sorted(views.items())},
           "dropped": dropped, "cells": [list(c) for c in region],
           "never_commit": "derived from client pixels"}  # fmt: skip
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{map_name}.json").write_text(json.dumps(doc))
    return {k: v for k, v in doc.items() if k not in ("cells", "per_view")} | {
        "region_cells": len(region)
    }


def _sizes() -> dict[str, tuple[int, int]]:
    from poring_env import ui_anchors as ua

    return {n: s.size for n, s in ua.default_registry().windows.items()}


def load_region(map_name: str, out_dir: Path = OUT_DIR) -> set[Cell] | None:
    """The map's measured region (cells), or None when it was never measured (callers fail
    closed)."""
    p = out_dir / f"{map_name}.json"
    if not p.exists():
        return None
    return {(int(c[0]), int(c[1])) for c in json.loads(p.read_text())["cells"]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("mode", choices=("plan", "measure", "build", "show"))
    ap.add_argument("--map", required=True)
    ap.add_argument("--step", type=int, default=STEP)
    ap.add_argument("--refine-step", type=int, default=REFINE_STEP)
    ap.add_argument("--radius", type=int, default=RADIUS)
    ap.add_argument("--session", action="append", default=[])
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    a = ap.parse_args()
    if a.mode == "plan":
        print(json.dumps(plan(a.map, a.step)))
        return 0
    if a.mode == "measure":
        return measure(a.map, a.step, a.refine_step, a.radius)
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
