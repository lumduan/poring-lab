#!/usr/bin/env python3
"""The Orc Lord EDGE-ENTRY watch (orclord-recognizer.md section 10, round 2; rogue-gef10.md
Amendment D): the IMMUNE Rogue meets a spawned Orc Lord coming INTO view from the screen's edge, the
case round 1 never had (its Lords spawned beside us, under spawn effects).

Per cell C of a seeded list (stand cells of the map's runner area):
  1. `@warp MAP C`, settle (Basic Info reads the Rogue again);
  2. `@monster 1190 1` (the Lord and its 5 archers appear around us), SPAWN_SETTLE_S;
  3. `@warp` to C + FAR * d (d: of the 8 directions, in a seeded order, the first whose every
     planned cell is in the area): the Lord is out of view;
  4. warp HOPS of HOP cells back toward C while the distance is > NEAR, DWELL_S at each: the Lord
     enters the view from its edge at one of them;
  5. `@killmonster2` (the spawned party dies without drops; on THIS map only).
Typed GM lines only (crusader.gm_line: the name + job check, the UI gate, chat_guard); no world
click. The recorder runs beside it (2 fps PNG), and the packets give the truth offline.

    orclord_edge_watch.py plan --map prt_fild08 --area AREA.npy --n 8 --seed S     (offline)
    orclord_edge_watch.py run  --map prt_fild08 --area AREA.npy --n 8 --seed S --label ow2 \\
                               --immune-confirmed                                (LIVE)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

VERSION = "orclord-edge@1"
DEMO = Path("/dev/shm/poring-lab-demo")
MOB = 1190  # the Orc Lord (its 5 Orc Archers come with it)
FAR, HOP, NEAR = 17, 3, 5  # cells: out of view, the hop back, where the approach ends
SPAWN_SETTLE_S, DWELL_S, READY_MAX_S = 6.0, 2.5, 20.0
DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
CHAR, JOB = "thief", "rogue"  # crusader.py's data dir and the character's job (rogue-gef10.md 3c)


def cheb(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def approach(c: tuple[int, int], d: tuple[int, int], far: int = FAR, hop: int = HOP,
             near: int = NEAR) -> list[tuple[int, int]]:  # fmt: skip
    """PURE: the far cell, then every hop back toward ``c`` while the distance is > ``near``."""
    out, k = [], far
    while k > near:
        out.append((c[0] + d[0] * k, c[1] + d[1] * k))
        k -= hop
    return out


def plan(area: np.ndarray, n: int, seed: int, near: int = NEAR,
         toggle: int | None = None) -> list[dict[str, Any]]:  # fmt: skip
    """PURE: ``n`` cells, each with a direction whose whole approach lies in ``area`` (a bool grid,
    [y, x]), spread out (>= 2 * FAR apart), in a seeded order. ``near`` ends the approach closer;
    ``toggle`` (flee fp2) adds a cell that far out on the same line, which must lie in the area too
    (the immunity is turned OFF there, beyond the party's reach). The defaults are fp1c's plan."""
    rng = np.random.default_rng(seed)
    ys, xs = np.nonzero(area)
    order = rng.permutation(len(xs))
    h, w = area.shape
    cells: list[dict[str, Any]] = []
    for i in order:
        c = (int(xs[i]), int(ys[i]))
        if any(cheb(c, tuple(p["cell"])) < 2 * FAR for p in cells):
            continue
        for j in rng.permutation(len(DIRS)):
            d = DIRS[int(j)]
            path = approach(c, d, near=near)
            extra = [] if toggle is None else [(c[0] + d[0] * toggle, c[1] + d[1] * toggle)]
            if all(0 <= x < w and 0 <= y < h and area[y, x] for x, y in [*path, *extra]):
                rec = {"cell": list(c), "dir": list(d), "path": [list(p) for p in path]}
                if extra:
                    rec["toggle"] = list(extra[0])
                cells.append(rec)
                break
        if len(cells) == n:
            break
    return cells


def _settle(screen: Any) -> float:
    import crusader as cr
    import ro_agent as r

    t0 = time.monotonic()
    time.sleep(1.5)
    while not cr.check(screen, JOB, CHAR)["ok"]:
        if time.monotonic() - t0 > READY_MAX_S:
            raise r.Stop(
                f"orclord-edge: the identity did not read within {READY_MAX_S} s of a @warp"
            )
        time.sleep(0.5)
    return round(time.monotonic() - t0, 1)


def run(a: argparse.Namespace) -> int:
    import bench
    import crusader as cr
    import npc_click_test as nct
    import ro_agent as r
    import ui_gate

    if not a.immune_confirmed:
        raise SystemExit("orclord-edge refused: --immune-confirmed (a person read the frame)")
    cells = plan(np.load(a.area), a.n, a.seed)
    stands = [list(p) for c in cells for p in [c["cell"], *c["path"]]]
    nct.check_warps(a.map, {"npcs": [{"stands": stands}], "clicks": []}, clicks=False)
    sid = f"{time.strftime('%Y%m%dT%H%M%S')}-watch-{a.map}-{a.label}"
    out = DEMO / sid
    out.mkdir(parents=True)
    evf = (out / "events.jsonl").open("a")

    def ev(rec: dict[str, Any]) -> None:
        evf.write(json.dumps({"t_ns": r.ns(), **rec}) + "\n")
        evf.flush()

    ev({"kind": "run_start", "version": VERSION, "what": "orclord-edge", "map": a.map,
        "seed": a.seed, "cells": cells, "far": FAR, "hop": HOP, "near": NEAR,
        "mob": MOB})  # fmt: skip
    reason = "done"
    with r.session("rule:orclord-edge") as (agent, screen):
        agent.wait_for_human()
        if not cr.check(screen, JOB, CHAR)["ok"]:
            raise r.Stop("not the Rogue")
        try:
            for k, c in enumerate(cells):
                x, y = c["cell"]
                cr.gm_line(agent, screen, f"@warp {a.map} {x} {y}", JOB, CHAR)
                ev({"kind": "at_cell", "i": k, "at": [x, y], "settle_s": _settle(screen)})
                cr.gm_line(agent, screen, f"@monster {MOB} 1", JOB, CHAR)
                ev({"kind": "spawn", "i": k, "mob": MOB})
                time.sleep(SPAWN_SETTLE_S)
                for j, (px, py) in enumerate(c["path"]):
                    cr.gm_line(agent, screen, f"@warp {a.map} {px} {py}", JOB, CHAR)
                    ev({"kind": "hop", "i": k, "j": j, "at": [px, py],
                        "dist": cheb((px, py), (x, y)), "settle_s": _settle(screen)})  # fmt: skip
                    bench.close_chat(agent, screen)
                    time.sleep(DWELL_S)
                cr.gm_line(agent, screen, "@killmonster2", JOB, CHAR)
                ev({"kind": "killmonster2", "i": k})
                bench.close_chat(agent, screen)
                print(f"cell {k + 1}/{len(cells)} at {x},{y} dir {c['dir']}", flush=True)
        except r.Stop as exc:
            reason = f"stop: {exc}"
        finally:
            ui_gate.ensure_clear(agent, screen, why="orclord-edge-end")
            print(r.to_png(screen.full(), r.SHOTS / f"orclord-edge-end-{a.label}.png"), flush=True)
    ev({"kind": "run_end", "reason": reason})
    evf.close()
    print(json.dumps({"sid": sid, "reason": reason, "cells": len(cells)}))
    return 0 if reason == "done" else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "run"):
        p = sub.add_parser(name)
        p.add_argument("--map", default="prt_fild08")
        p.add_argument(
            "--area", type=Path, required=True, help="the runner area, a bool .npy [y, x]"
        )
        p.add_argument("--n", type=int, default=8)
        p.add_argument("--seed", type=int, default=0)
        if name == "run":
            p.add_argument("--label", default="ow2")
            p.add_argument("--immune-confirmed", action="store_true")
    a = ap.parse_args()
    if a.cmd == "plan":
        print(json.dumps(plan(np.load(a.area), a.n, a.seed)))
        return 0
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
