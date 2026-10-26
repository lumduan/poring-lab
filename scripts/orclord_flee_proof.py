#!/usr/bin/env python3
"""The Orc Lord FLEE proof (orclord-recognizer.md section 12, pre-registered): a Fly Wing on the
first aura positive, live, with immunity OFF, on spawned Orc Lords coming into view from the edge.

Per trial (a cell of orclord_edge_watch's seeded plan on prt_fild08, so gef_fild10's natural Lord
is untouched):
  1. immunity ON (verified on the client's own reply bubble), `@warp` C, `@monster 1190 1`,
     `@warp` to the far cell (17 cells out), immunity OFF (verified);
  2. hop back 3 cells at a time; at each hop the WATCHER reads fresh frames every WATCH_S:
     mvp_watch.decide(frame, model, cues=("aura",)) -- pixels only, the frozen round-1 model;
  3. on the first positive: F2 (the Fly Wing) at once; HP_FLY below as a backup (logged apart);
  4. immunity ON, `@killmonster2` (the spawned party; prt_fild08 only).
Typed GM lines only through crusader.gm_line (name + job check, UI gate, chat_guard); the only
other inputs are F2 presses. A death stops the proof (the parent recovers by the known step).

    orclord_flee_proof.py run --area AREA.npy --n 6 --seed 27 --label fp1 --model M --sha256 H
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

import orclord_edge_watch as ow  # noqa: E402

VERSION = "orclord-flee@4"
ROOT = Path(__file__).resolve().parents[1]
BUBBLES = ROOT / "data" / "mvp_watch" / "immune_bubbles.npz"  # client pixels: never committed
WATCH_S, DWELL_S, AFTER_FLY_S = 0.25, 4.0, 3.0
HP_FLY = 0.5  # the backup: HP below this share during a trial -> F2 (logged as "hp")
TEXT_LEVEL, READ_LEVEL = 200.0, 170.0  # a reference's text pixels / a frame pixel read as text
BUBBLE_WAIT_S = 3.0
SHIFT_PX = 2  # flee@2 (fp1, 03:56-04:00): the real "off" bubble drew 1 px lower than its reference
SAFE_STAND = (268, 107)  # dungeon_hunt.CLEAR_STAND's cell on prt_fild08 (open field, no aggressor)


def bubble_score(gray_box: np.ndarray, ref: np.ndarray) -> float:
    """PURE: the share of the reference's TEXT pixels (>= TEXT_LEVEL) that are text-bright in the
    frame's box too; the translucent bubble's background (the scene) is ignored."""
    mask = ref >= TEXT_LEVEL
    if not mask.any() or gray_box.shape != ref.shape:
        return 0.0
    return float((gray_box[mask] >= READ_LEVEL).mean())


def bubble_state(gray_box: np.ndarray, on: np.ndarray, off: np.ndarray) -> str | None:
    """PURE: "on" / "off" when one reference's text reads >= 0.8 and the other's < 0.6; else
    None."""
    s_on, s_off = bubble_score(gray_box, on), bubble_score(gray_box, off)
    if s_on >= 0.8 and s_off < 0.6:
        return "on"
    if s_off >= 0.8 and s_on < 0.6:
        return "off"
    return None


def read_bubble(
    gray: np.ndarray,
    box: tuple[int, int, int, int],
    on: np.ndarray,
    off: np.ndarray,
    shift: int = SHIFT_PX,
) -> str | None:
    """PURE: ``bubble_state`` on the frame's box moved by up to ``shift`` px each way, each
    reference at its own best offset (a 1-px drift between a reference and a live bubble is
    rendering, not a different text); None when neither reads, as before."""
    x, y, w, h = box
    best_on = best_off = 0.0
    for dy in range(-shift, shift + 1):
        for dx in range(-shift, shift + 1):
            y0, x0 = y + dy, x + dx
            if y0 < 0 or x0 < 0:
                continue
            g = gray[y0 : y0 + h, x0 : x0 + w]
            best_on = max(best_on, bubble_score(g, on))
            best_off = max(best_off, bubble_score(g, off))
    if best_on >= 0.8 and best_off < 0.6:
        return "on"
    if best_off >= 0.8 and best_on < 0.6:
        return "off"
    return None


def run(a: argparse.Namespace) -> int:  # noqa: PLR0915 -- one live procedure, read top to bottom
    import crusader as cr
    import gm_vitals as gv
    import hp_percent as hpp
    import mvp_watch as mw
    import npc_click_test as nct
    import ro_agent as r
    import ui_gate

    model = mw.load(a.model, sha256=a.sha256)
    zb = np.load(BUBBLES)
    ref_on, ref_off, box = zb["on"], zb["off"], tuple(int(v) for v in zb["box"])
    z = np.load(hpp.GLYPHS)
    glyphs = {("%" if k == "pct" else k[1:]): z[k] for k in z.files}
    cells = ow.plan(np.load(a.area), a.n, a.seed, near=a.near, toggle=a.toggle)
    stands = [list(p) for c in cells for p in [c["cell"], *c["path"]]]
    stands += [c["toggle"] for c in cells if "toggle" in c]  # flee@4: the OFF cells are stands too
    nct.check_warps(a.map, {"npcs": [{"stands": stands}], "clicks": []}, clicks=False)
    out = ow.DEMO / f"{time.strftime('%Y%m%dT%H%M%S')}-flee-{a.map}-{a.label}"
    out.mkdir(parents=True)
    evf = (out / "events.jsonl").open("a")

    def ev(rec: dict[str, Any]) -> None:
        evf.write(json.dumps({"t_ns": r.ns(), **rec}) + "\n")
        evf.flush()

    ev({"kind": "run_start", "version": VERSION, "map": a.map, "seed": a.seed, "cells": cells,
        "model_sha256": a.sha256, "cues": ["aura"], "watch_s": WATCH_S,
        "hp_fly": HP_FLY, "near": a.near, "toggle": a.toggle})  # fmt: skip
    reason = "done"
    with r.session("rule:orclord-flee") as (agent, screen):
        agent.wait_for_human()
        region = r.game_region()

        def frame() -> Any:
            return np.ascontiguousarray(r.grab_after(screen, region, r.ns())[..., :3])

        def gm(line: str) -> None:
            cr.gm_line(agent, screen, line, ow.JOB, ow.CHAR)

        def immune(want: str) -> None:
            gm("@monsterignore")
            end = time.monotonic() + BUBBLE_WAIT_S
            while time.monotonic() < end:
                got = read_bubble(frame().astype(np.float32).mean(axis=2), box, ref_on, ref_off)
                if got is not None:
                    ev({"kind": "immune", "want": want, "got": got})
                    if got != want:
                        raise r.Stop(f"immunity reads {got!r} after the toggle, wanted {want!r}")
                    return
                time.sleep(0.2)
            raise r.Stop(f"no immunity reply bubble read within {BUBBLE_WAIT_S} s ({want!r})")

        if not cr.check(screen, ow.JOB, ow.CHAR)["ok"]:
            raise r.Stop("not the Rogue")
        state = "off"
        spawned = False
        try:
            for k, c in enumerate(cells):
                x0, y0 = c["cell"]
                if state != "on":  # flee@3 (fp1b): the previous trial already ended ON; a 2nd
                    immune("on")  # toggle flipped it OFF (caught by the read, 04:05:07)
                    state = "on"
                gm(f"@warp {a.map} {x0} {y0}")
                ow._settle(screen)
                gm(f"@monster {ow.MOB} 1")
                spawned = True
                ev({"kind": "spawn", "i": k, "at": [x0, y0]})
                time.sleep(ow.SPAWN_SETTLE_S)
                if "toggle" in c:  # flee@4 (fp2, section 13): OFF beyond the party's reach first
                    tx, ty = c["toggle"]
                    gm(f"@warp {a.map} {tx} {ty}")
                    ow._settle(screen)
                    immune("off")
                    state = "off"
                px, py = c["path"][0]
                gm(f"@warp {a.map} {px} {py}")
                ow._settle(screen)
                if "toggle" not in c:
                    immune("off")
                    state = "off"
                fled = None
                for j, (hx, hy) in enumerate(c["path"]):
                    if j:
                        gm(f"@warp {a.map} {hx} {hy}")
                        ow._settle(screen)
                    ev({"kind": "hop", "i": k, "j": j, "at": [hx, hy],
                        "dist": ow.cheb((hx, hy), (x0, y0))})  # fmt: skip
                    end = time.monotonic() + DWELL_S
                    while time.monotonic() < end and fled is None:
                        f = frame()
                        v = mw.decide(f, model, cues=("aura",))
                        pct = hpp.read(f, glyphs)
                        low = pct is not None and pct < HP_FLY * 100
                        why = "aura" if v["seen"] else ("hp" if low else None)
                        if why is not None:
                            r.activate_client(agent, screen)
                            agent.keys("F2")
                            fled = why
                            ev({"kind": "flee", "i": k, "j": j, "why": why, "hp": pct,
                                "aura": v.get("aura"), "where": v.get("where")})  # fmt: skip
                        if r.is_state(screen, gv.DEAD_STATE):
                            raise r.Stop("dead: the death dialog is up")
                        time.sleep(WATCH_S)
                    if fled is not None:
                        break
                time.sleep(AFTER_FLY_S)
                immune("on")
                state = "on"
                gm("@killmonster2")
                spawned = False
                ev({"kind": "trial_end", "i": k, "fled": fled})
                print(f"trial {k + 1}/{len(cells)}: fled={fled}", flush=True)
        except r.Stop as exc:
            reason = f"stop: {exc}"
            if spawned and not r.is_state(screen, gv.DEAD_STATE):
                # flee@2 (fp1): a stop after a spawn left the Rogue 17 cells from the party with
                # its immunity unread -- away to the open-field stand FIRST, then clear the party
                try:
                    gm(f"@warp {a.map} {SAFE_STAND[0]} {SAFE_STAND[1]}")
                    ow._settle(screen)
                    gm("@killmonster2")
                    ev({"kind": "safe_exit", "at": list(SAFE_STAND), "killmonster2": True})
                except r.Stop as exc2:
                    ev({"kind": "safe_exit_failed", "why": str(exc2)})
                    reason += f"; safe exit failed: {exc2}"
        finally:
            ev({"kind": "immune_state_at_end", "believed": state})
            ui_gate.ensure_clear(agent, screen, why="orclord-flee-end")
            print(r.to_png(screen.full(), r.SHOTS / f"orclord-flee-end-{a.label}.png"), flush=True)
    ev({"kind": "run_end", "reason": reason})
    evf.close()
    print(json.dumps({"session": out.name, "reason": reason, "immune_believed": state}))
    return 0 if reason == "done" else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("--map", default="prt_fild08")
    p.add_argument("--area", type=Path, required=True)
    p.add_argument("--n", type=int, default=6)
    p.add_argument("--seed", type=int, default=27)
    p.add_argument("--label", default="fp1")
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--sha256", required=True)
    p.add_argument("--near", type=int, default=ow.NEAR, help="the approach ends above this")
    p.add_argument("--toggle", type=int, default=None,
                   help="flee@4 (fp2): immunity OFF this many cells out, then hop")  # fmt: skip
    a = ap.parse_args()
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
