#!/usr/bin/env python3
"""walk@12 (docs/demonstrations.md 3.21): walk@11 UNCHANGED + Batt's three decisions of 2026-10-08
~11:25.

walk@11 (3.18) held against monsters: 0 attack requests and 0 GM attacks in 705 rule clicks over its
four tuning runs. What remained:
- an NPC contact in each indoor run, by the mechanism seen since walk@8: a WALK read 8 px from two
  TALK reads, all three points picking the cell (112,114) beside Sister Linus;
- one rule click on a UI window (indoor CROWD route 53: client (52.9, 295.8), the Basic Information
  icon grid), which opened the Shortcut Description window;
- that run then exited without its end time and its packets (finished offline).

The three changes, exactly:
1. CLICK POINTS EXCLUDE THE CLIENT'S UI WINDOWS (work_zone.py: route_preview.UI_WINDOWS grown by
   12 px). Every candidate pixel (tier A / B; the farther points' and the substitutes' pixels come
   from the same function; the portal's) must lie in the work zone, and a refused pixel is never
   hovered. Tier B is used only when no tier-A pixel lies in the work zone. A cell with no
   work-zone pixel is "no_safe_point" (walk@11: the next point at once). The refused pixels are
   logged as `ui_refused`.
2. A TALK READ BLOCKS THE WHOLE PICKED CELL. Within one click attempt (the points of one target
   cell), once a point reads TALK, every later point the picking model maps to the same cell is
   refused without a hover (`talk_refused`). An attempt that clicks nothing ends
   "covered_talk_cell": a unit at the click point, so walk@8's patience and substitute rules apply.
3. THE HARNESS FINISHES ITS SESSION ON ANY EXIT. A Stop (e.g. "the chat input did not open"), any
   exception, or an interrupt (SIGINT, SIGTERM) still writes the session's packets and its end
   (t1) through walk@11's finish path. The run then exits NONZERO with the reason. A rule decline
   is not a harness exit: a route declines and the run goes on, as in walk@11.
NOT included: the motion model (T1-lite) stays a proposal (3.18's walk@12 design proposal).

How walk@11 stays unchanged: walk12 does not copy walk11's code. `walk_route` and `run11` below
ARE walk@11's functions (the same code objects), re-bound to this module's names. So they call
walk12's click_step and portal_step, and log walk@12's label through walk@12's session log.
walk11.py and its module object are untouched (test_walk12.py checks both).

    walk12.py --scene indoor|outdoor|guild|town|dungeon|portal --condition clean|crowd --seed S
Pixels in, input out: the rule never reads packets.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import signal
import sys
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from types import FrameType, FunctionType
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import operator_hud  # noqa: E402
import record_session  # noqa: E402
import ro_agent as r  # noqa: E402
import route_plan  # noqa: E402
import rule_run as rr  # noqa: E402
import walk5 as w5  # noqa: E402
import walk6 as w6  # noqa: E402
import walk11 as w11  # noqa: E402
import work_zone as wz  # noqa: E402
from walk11 import (  # noqa: E402
    CURSOR_REFS_V2,
    MARGIN_NAMED_PX,
    MARGIN_PX,
    SCENES8,
    UNIT_SHAPES,
    UNITS,
    WALK,
    named8,
    observe_frame,
)

from poring_dataset import picking  # noqa: E402
from poring_env.demo import DEMO_ROOT, DemoRecord  # noqa: E402

# walk@11's names (its constants, helpers and the unit memory UNITS: the SAME objects), so its
# re-bound functions find everything they use here. The names below are walk@12's own.
OWN = frozenset({"WALK8_RULE", "pick_points", "click_step", "portal_step", "walk_route", "run",
                 "main", "DemoLog", "where_relocalise", "unit_check"})  # fmt: skip
globals().update({k: v for k, v in vars(w11).items() if not k.startswith("__") and k not in OWN})

WALK8_RULE = "walk@12"
TALK = "talk"
SEARCH_K = 20  # pick-safe points searched per tier, so a window's refusals leave alternates
POINTS_K = 5  # the points kept, as walk@11 (picking.safe_points' k; rr.MAX_HOVERS)
EXIT_STOP = 3  # a Stop / SystemExit: the harness could not go on (e.g. it cannot type)
EXIT_ERROR = 4  # any other exception
EXIT_INTERRUPTED = 130  # SIGINT / SIGTERM


def tier_points(w: w5.World, end: tuple[int, int], tier: str) -> list[tuple[float, float]]:
    """walk@11's pick-safe points of one tier for ``end`` (poring_dataset.picking), most interior
    first: "A" = every pixel within 6 px picks the cell; "B" = 3 px, named clicks only."""
    rel = (end[0] - w.position[0], end[1] - w.position[1])
    margin, grid = (MARGIN_PX, 2.0) if tier == "A" else (MARGIN_NAMED_PX, 1.0)
    return picking.safe_points(w.camera, w.gat, w.position, rel, margin=margin, grid=grid,
                               k=SEARCH_K)  # fmt: skip


def zone_points(w: w5.World, end: tuple[int, int]
                ) -> tuple[list[tuple[float, float]], str, list[Any]]:  # fmt: skip
    """Decision 1: walk@11's pick_points INSIDE THE WORK ZONE -> (points, tier, refused).
    - A pixel over a UI window does not exist for a click.
    - Tier A: its pixels in the work zone. Tier B only when there are none (named clicks only, as in
      walk@11). "none" when neither tier has one.
    - refused: the pixels walk@11 would have offered (each tier's first POINTS_K) that the work zone
      refuses.
    - With no UI window near the cell, these are exactly walk@11's points and tier."""
    refused: list[list[float]] = []
    for tier in ("A", "B"):
        pts = tier_points(w, end, tier)
        for u, v in pts[:POINTS_K]:
            p = [round(u, 1), round(v, 1)]
            if not wz.in_work_zone(u, v) and p not in refused:
                refused.append(p)
        inside = [(u, v) for u, v in pts if wz.in_work_zone(u, v)]
        if inside:
            return inside[:POINTS_K], tier, refused
    return [], "none", refused


def picked_cells(w: w5.World, pts: list[tuple[float, float]]) -> list[tuple[int, int]]:
    """The cell OFFSET the client picks under each pixel (the picking model: the camera ray against
    the GAT's top surfaces)."""
    if not pts:
        return []
    got = picking.pick_cells(w.camera, w.gat, w.position, np.asarray(pts, dtype=float))
    return [(int(a), int(b)) for a, b in got]


def click_step(pr: w6.Prober, w: w5.World, end: tuple[int, int],
               expect: str = WALK, accept_unnamed: bool = False) -> dict[str, Any]:  # fmt: skip
    """walk@11's click_step with decisions 1 and 2 (the rest is walk@11's, unchanged).
    1. The points come from zone_points: no pixel over a UI window or within 12 px of one.
    2. Once a point reads TALK, every later point the picking model maps to the SAME cell is refused
       without a hover. The attempt, if nothing is clicked, ends "covered_talk_cell" (a unit).
       In walk@11 the click after two TALK reads went to a point 8 px away in that cell, and
       contacted the NPC. A round of walk_route tries each cell once, and tier A / B points of
       different cells never pick the same cell, so this covers the whole round.
    ``expect="warp"``: the click whose intent is to TAKE a portal (portal_step)."""
    if expect == "warp":
        return portal_step(pr, w, end)
    queue, tier, ui_refused = zone_points(w, end)
    extra: dict[str, Any] = {"ui_refused": ui_refused} if ui_refused else {}
    if not queue:
        return {"clicked": False, "outcome": "no_safe_point", "target": [], "tier": tier, **extra}
    if not pr.park():
        return {"clicked": False, "outcome": "stale_background", "target": [], "tier": tier,
                **extra}  # fmt: skip
    observe_frame(pr.background, w, r.ns())  # walk@11: the park frame feeds the unit memory
    rel = (end[0] - w.position[0], end[1] - w.position[1])
    target: list[dict[str, Any]] = []
    neighbour = False
    queue = queue[: rr.MAX_HOVERS]
    picks: dict[int, tuple[int, int]] = {}  # the picked cell per queue index, once a TALK is read
    talk_cells: list[tuple[int, int]] = []
    talk_refused: list[list[float]] = []

    def out(**kw: Any) -> dict[str, Any]:
        talk = {}
        if talk_cells:
            talk = {"talk_cells": [[w.position[0] + a, w.position[1] + b] for a, b in talk_cells],
                    "talk_refused": talk_refused}  # fmt: skip
        return {**kw, "target": target, "tier": tier, **talk, **extra}

    for i, (u, v) in enumerate(queue):
        if talk_cells and picks[i] in talk_cells:
            talk_refused.append([round(u, 1), round(v, 1)])
            continue  # decision 2: never hovered, never clicked
        pr.hover(u, v)
        p = pr.read(u, v)
        k = named8(w, rel, p)
        target.append({"at": [round(u, 1), round(v, 1)], "shape": p["shape"], "iou": p["iou"],
                       "cell": k, "marker_px": p["marker_px"], "tier": tier})  # fmt: skip
        if p["shape"] == TALK:
            if not picks:  # the rest of the queue in one batch
                picks = dict(zip(range(i, len(queue)), picked_cells(w, queue[i:]), strict=True))
            if picks[i] not in talk_cells:
                talk_cells.append(picks[i])
            continue
        if p["shape"] != WALK:  # never clicked here; another point may show the walk cursor
            continue
        if k is None and accept_unnamed and tier == "A":
            # the belief was just CONFIRMED by /where and the picking model puts every pixel
            # within 6 px in the cell: the walk cursor, re-checked with no motion, is enough --
            # unknown is still no click
            again = pr.read(u, v)
            target[-1]["recheck"] = {"shape": again["shape"], "cell": None}
            if again["shape"] != WALK:
                return out(clicked=False, outcome=f"recheck_{again['shape']}")
            ok, env = unit_check(pr, w, u, v)
            target[-1]["envelope"] = env
            if not ok:
                return out(clicked=False, outcome="covered_unit_envelope")
            gx, gy, _, _ = r.game_region()
            t_click = r.ns()
            pr.agent.click(gx + round(u), gy + round(v))
            return out(clicked=True, outcome="unnamed_after_fix", at=(u, v), t_click=t_click)
        if k == (0, 0):
            again = pr.read(u, v)  # the RE-CHECK: a fresh grab, no motion
            k2 = named8(w, rel, again)
            target[-1]["recheck"] = {"shape": again["shape"], "cell": k2}
            if again["shape"] != WALK or k2 != (0, 0):
                return out(clicked=False, outcome=f"recheck_{again['shape']}")
            ok, env = unit_check(pr, w, u, v)
            target[-1]["envelope"] = env
            if not ok:
                return out(clicked=False, outcome="covered_unit_envelope")
            gx, gy, _, _ = r.game_region()
            t_click = r.ns()
            pr.agent.click(gx + round(u), gy + round(v))
            return out(clicked=True, outcome="confirmed", at=(u, v), t_click=t_click)
        if k is not None:
            neighbour = True
    if talk_cells:
        return out(clicked=False, outcome="covered_talk_cell")
    if neighbour:
        return out(clicked=False, outcome="neighbour")
    others = [t["shape"] for t in target if t["shape"] != WALK]
    if others and len(others) == len(target):  # no point of the cell shows the walk cursor
        first = next((x for x in others if x in UNIT_SHAPES), others[0])
        return out(clicked=False, outcome=f"covered_{first}")
    return out(clicked=False, outcome="unconfirmed")


def portal_step(pr: w6.Prober, w: w5.World, end: tuple[int, int]) -> dict[str, Any]:
    """walk@11's portal click (the WARP cursor at the portal cell, re-checked with no motion) on
    work-zone pixels only (decision 1)."""
    nb = np.array([(end[0] + dx, end[1] + dy) for dx, dy in rr.NB9], dtype=float)
    pts = rr.in_cell_points(w.project(nb))
    inside = [(u, v) for u, v in pts if wz.in_work_zone(u, v)]
    refused = [[round(u, 1), round(v, 1)] for u, v in pts if not wz.in_work_zone(u, v)]
    extra: dict[str, Any] = {"ui_refused": refused} if refused else {}
    if not inside:
        return {"clicked": False, "outcome": "no_safe_point", "target": [], **extra}
    if not pr.park():
        return {"clicked": False, "outcome": "stale_background", "target": [], **extra}
    target: list[dict[str, Any]] = []
    for u, v in inside:
        pr.hover(u, v)
        p = pr.read(u, v)
        target.append({"at": [round(u, 1), round(v, 1)], "shape": p["shape"], "iou": p["iou"]})
        if p["shape"] != "warp":
            continue
        again = pr.read(u, v)
        target[-1]["recheck"] = {"shape": again["shape"]}
        if again["shape"] != "warp":
            return {"clicked": False, "outcome": f"recheck_{again['shape']}", "target": target,
                    **extra}  # fmt: skip
        gx, gy, _, _ = r.game_region()
        t_click = r.ns()
        pr.agent.click(gx + round(u), gy + round(v))
        return {"clicked": True, "outcome": "portal", "target": target, "at": (u, v),
                "t_click": t_click, **extra}  # fmt: skip
    return {"clicked": False, "outcome": "no_portal_cursor", "target": target, **extra}


class SessionLog(w11.DemoLog):
    """walk@11's DemoLog, remembered so that any end of the run can finish it (decision 3). It
    counts the ROUTE records and stamps walk@12's parameters into the manifest."""

    root: Path = DEMO_ROOT  # tests point it at a temporary directory
    current: SessionLog | None = None

    def __init__(self, session: str, root: Path | None = None) -> None:
        super().__init__(session, root if root is not None else type(self).root)
        self.routes = 0
        self.finished = False
        SessionLog.current = self

    def start(self, **meta: Any) -> None:
        windows = [list(b) for b in wz.UI_WINDOWS]
        super().start(**meta, work_zone_margin_px=wz.MARGIN_PX, ui_windows=windows,
                      talk_cell_block=True)  # fmt: skip

    def append(self, rec: DemoRecord) -> DemoRecord:
        got = super().append(rec)
        if rec.rule == WALK8_RULE:  # a route's record (a click's is "walk@12/click")
            self.routes += 1
        return got

    def finish(self, **meta: Any) -> None:
        meta.setdefault("ended", "complete")
        super().finish(**meta)
        self.finished = True


DemoLog = SessionLog  # the name walk@11's run creates its session log by


def _walk11(fn: Callable[..., Any]) -> Any:
    """walk@11's function (ITS code, defaults and docstring) reading its global names from THIS
    module, so walk@12's click step, label and session log apply inside it."""
    if not isinstance(fn, FunctionType):
        raise TypeError(f"not a plain function: {fn!r}")
    g = FunctionType(fn.__code__, globals(), fn.__name__, fn.__defaults__, fn.__closure__)
    g.__kwdefaults__ = fn.__kwdefaults__
    g.__doc__, g.__qualname__ = fn.__doc__, fn.__qualname__
    g.__annotations__ = dict(fn.__annotations__)
    g.__module__ = __name__
    return g


# The LIVE route preview (Batt 2026-10-08; display only): the run publishes its plan in CELLS
# (route_plan.py) and the previewer daemon draws it. These wrappers only publish: the engine's walk
# at each click, each /where fix, the clear at each route's end. They change no argument and no
# result, and walk_route / run11 still run walk@11's code (`__wrapped__`, test_walk12.py).


def engine_path(w: w5.World, start: tuple[int, int], end: tuple[int, int]) -> Any:
    """The cells the engine walks from `start` to `end` (the GAT, nothing blocked): the preview's
    model of the walk a click starts. Display only."""
    from poring_dataset.walk import walk_path

    return walk_path(w6.Grid(w.walkable, set()), start[0], start[1], end[0], end[1],
                     max_len=w5.PLAN_MAX) or [end]  # fmt: skip


# The OPERATOR HUD (Batt 2026-10-08; display only, operator_hud.py): the gate hook only RECORDS its
# verdict (nothing between the click-instant gate and the click); the boxes, the verdicts and the
# step's outcome are published after the step returned.
unit_check = operator_hud.hook_unit_check(w11.unit_check, UNITS)
click_step = operator_hud.hook_click_step(route_plan.hook_click_step(click_step, engine_path))
where_relocalise = route_plan.hook_relocalise(w11.where_relocalise)
walk_route = operator_hud.hook_route(route_plan.hook_route_end(_walk11(w11.walk_route)))
run11 = _walk11(w11.run)  # walk@11's harness: `run` below adds decision 3 around it


def ended_by(exc: BaseException) -> tuple[str, int, str]:
    """(how the run ended, the exit code, the reason) for an exception that left the harness."""
    if isinstance(exc, KeyboardInterrupt):
        return "interrupted", EXIT_INTERRUPTED, str(exc) or "interrupt"
    if isinstance(exc, SystemExit):  # ro_agent's Stop, or the harness's own SystemExit
        return "harness_stop", EXIT_STOP, str(exc) or type(exc).__name__
    return "exception", EXIT_ERROR, f"{type(exc).__name__}: {exc}"


@contextlib.contextmanager
def signals_held() -> Iterator[None]:
    """A second Ctrl+C or a SIGTERM must not cut the finish path short (main thread only)."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    old = {s: signal.signal(s, signal.SIG_IGN) for s in (signal.SIGINT, signal.SIGTERM)}
    try:
        yield
    finally:
        for s, h in old.items():
            signal.signal(s, h)


def finish_session(log: SessionLog, ended: str, why: str, code: int) -> dict[str, Any]:
    """walk@11's finish path for a run that did not reach its end: the packets of the session's
    window (the manifest's t0 to now), then t1. A packets failure is recorded, and t1 is still
    written, so the session can be repacked offline (record_session.repack)."""
    t0 = int(json.loads((log.dir / "manifest.json").read_text())["t0_mono_ns"])
    packets: dict[str, Any]
    try:
        events, anchor = record_session.write_packets(log.dir, t0, r.ns())
        packets = {"packet_events": len(events), "packet_anchor": anchor}
    except Exception as exc:  # noqa: BLE001 -- the end time is written whatever the packets do
        packets = {"packets_error": f"{type(exc).__name__}: {exc}"[:300]}
    log.finish(routes=log.routes, ended=ended, reason=why, exit_code=code, **packets)
    return {"session": log.session, "routes": log.routes, **packets}


def finish_failed(exc: BaseException) -> int:
    """Decision 3: the run left walk@11's harness by an exception. Finish its session (if one was
    started and is not finished yet), report, and return a NONZERO exit code. No input is sent."""
    ended, code, why = ended_by(exc)
    why = why[:300]
    report: dict[str, Any] = {"rule": WALK8_RULE, "ended": ended, "reason": why, "exit_code": code}
    with signals_held():
        det = UNITS.get("detector")
        if det is not None:
            with contextlib.suppress(Exception):
                det.close()
        log = SessionLog.current
        if log is not None and log.finished:
            report["session"] = log.session  # its normal end was already written
        elif log is not None and (log.dir / "manifest.json").exists():
            report |= finish_session(log, ended, why, code)
            report["finished"] = True
    print(json.dumps(report), flush=True)
    done = "the session is finished (t1 + packets)" if report.get("finished") else "no session"
    print(f"{WALK8_RULE}: the run ENDED ({ended}): {why} -- {done}; exit {code}", file=sys.stderr,
          flush=True)  # fmt: skip
    return code


def run(scene: str, condition: str, n: int, seed: int, label: str, crowd: int,
        fix: str = "where") -> int:  # fmt: skip
    """walk@11's run (re-bound: walk@12's label, click step and session log) + decision 3."""
    SessionLog.current = None
    UNITS["detector"] = None  # walk@11's run loads its own; a failure before that has none to close
    plan = route_plan.enable(f"{WALK8_RULE}-{scene}-{condition}-{seed}", SCENES8[scene][0])
    hud = operator_hud.enable(f"{WALK8_RULE} {scene}/{condition}")
    try:
        return int(run11(scene, condition, n, seed, label, crowd, fix))
    except BaseException as exc:  # noqa: BLE001 -- decision 3: EVERY way out finishes the session
        return finish_failed(exc)
    finally:
        route_plan.disable(plan)  # the line is cleared however the run ends
        operator_hud.disable(hud)


def _terminate(signum: int, frame: FrameType | None) -> None:
    raise KeyboardInterrupt(f"signal {signal.Signals(signum).name}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--scene", choices=sorted(SCENES8), required=True)
    ap.add_argument("--condition", choices=("clean", "crowd"), required=True)
    ap.add_argument("--n", type=int, default=56)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--label", default="walk12-alone")
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
    signal.signal(signal.SIGTERM, _terminate)  # a SIGTERM ends the run like Ctrl+C (decision 3)
    return run(a.scene, a.condition, a.n, a.seed, a.label, a.crowd, a.fix)


if __name__ == "__main__":
    sys.exit(main())
