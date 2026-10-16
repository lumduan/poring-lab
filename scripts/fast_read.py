#!/usr/bin/env python3
"""The FAST cursor read (a hunt-flow candidate, 2026-10-16): robust2's classifier on a BLINK
background instead of a park.

The proven gate (`cursor_gate.prober`, walk@9's Prober9 + robust2) parks the pointer at the far
right (two motions, 0.3 s, up to 1.5 s until the drawn cursor shows there, a second frame 0.25 s
later), hovers the target (0.55 s) and reads. In hunt-flow@6 that put p50 3.56 s between "in range"
and the attack click.

Here the pointer is ALREADY on the target (hunt-flow's pointer follows it), so:
  A      = a grab with the cursor drawn on the target (the pointer still there >= SETTLE_S);
  blink  = the pointer BLINK_PX away in small moves (the client draws its cursor during continuous
           travel, ~0.15-0.2 s behind: 2026-10-16 13:24);
  B1, B2 = two grabs SETTLE_S and SETTLE_S + GAP_S after the blink (the cursor gone from the
           target; pixels changing between them are animation and never count);
  read   = robust2's match on |A - B2| minus the animated pixels, with its own floors and margins.
It is valid only when the cursor LEFT the target: a cursor-sized |A - B2| there, else "unknown".

It gates NOTHING until `check` has shown it agrees with the proven read (no false SWORD).

    fast_read.py check [--monsters 15] [--ground 10] [--npc]    no clicks
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

BLINK_PX = 90
SETTLE_S = 0.25
GAP_S = 0.12
MOVES = 4
CLEAR_PX = 70.0  # the blink point keeps this far from every unit box centre
OFFSETS = ((1, 0), (-1, 0), (0, 1), (0, -1), (0.71, 0.71), (-0.71, 0.71), (0.71, -0.71),
           (-0.71, -0.71))  # fmt: skip


def blink_point(u: float, v: float, centres: list[tuple[float, float]], in_view: Any,
                px: float = BLINK_PX) -> tuple[float, float] | None:  # fmt: skip
    """PURE: the first point ``px`` away from (u, v) that is in view (off the UI) and at least
    CLEAR_PX from every unit box centre, else None."""
    for dx, dy in OFFSETS:
        bu, bv = u + dx * px, v + dy * px
        if in_view(bu, bv) and all(np.hypot(bu - cu, bv - cv) >= CLEAR_PX for cu, cv in centres):
            return bu, bv
    return None


def glide(agent: Any, origin: tuple[int, int], a: tuple[float, float], b: tuple[float, float],
          moves: int = MOVES) -> None:  # fmt: skip
    """Small moves a -> b (client px): continuous travel, so the client draws its cursor."""
    gx0, gy0 = origin
    for i in range(1, moves + 1):
        agent.move(gx0 + round(a[0] + (b[0] - a[0]) * i / moves),
                   gy0 + round(a[1] + (b[1] - a[1]) * i / moves))  # fmt: skip
        time.sleep(0.012)


def read(pr: Any, agent: Any, screen: Any, origin: tuple[int, int], u: float, v: float,
         blink: tuple[float, float]) -> dict[str, Any]:  # fmt: skip
    """The fast read at (u, v). The caller has left the pointer on (u, v) >= SETTLE_S."""
    import walk6 as w6
    import walk10 as w10

    gx0, gy0 = origin
    px, py = gx0 + round(u), gy0 + round(v)
    t0 = time.monotonic()
    a_big = np.asarray(screen.grab(px - 60, py - 60, 120, 120)[1])[..., :3]
    glide(agent, origin, (u, v), blink)
    time.sleep(SETTLE_S)
    b1 = np.asarray(screen.grab(px - 60, py - 60, 120, 120)[1])[..., :3]
    time.sleep(GAP_S)
    b2 = np.asarray(screen.grab(px - 60, py - 60, 120, 120)[1])[..., :3]
    a, b, b1c = a_big[28:92, 28:92], b2[28:92, 28:92], b1[28:92, 28:92]
    left = int(w6.cursor_mask(a, b).sum())
    anim = np.abs(b1c.astype(int) - b.astype(int)).sum(-1) > w10.ANIM_DIFF
    b_mod = np.where(anim[..., None], a, b)
    out: dict[str, Any] = dict(pr.refs.match(a, w6.cursor_mask(a, b_mod)))
    out["left_px"] = left
    if not (w6.PARK_CURSOR_PX[0] <= left <= w6.PARK_CURSOR_PX[1]):
        out.update(shape="unknown", why="cursor_not_left")
    out["ms"] = round((time.monotonic() - t0) * 1000)
    return out


# --- the no-click check ---------------------------------------------------------------------------


def check(n_mon: int, n_ground: int, npc: bool, minutes: float,
          warp: tuple[int, int] | None = None) -> int:  # fmt: skip
    import bench
    import cursor_gate
    import farm0 as f0
    import farm1 as f1
    import loot1
    import ro_agent as r
    import unit_detector

    gx0, gy0, gw, gh = r.game_region()

    def in_view(u: float, v: float) -> bool:
        return 30 <= u < gw - 30 and 30 <= v < gh - 30 and not loot1.in_ui(u, v)

    rows: list[dict[str, Any]] = []
    out_dir = r.ROOT / "data" / "fast_read"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"check-{time.strftime('%Y%m%dT%H%M%S')}.jsonl"
    deadline = time.monotonic() + minutes * 60
    rng = np.random.default_rng(int(time.time()))
    with r.session("rule:fast-read-check@1") as (agent, screen):
        f0.stop_on_takeover(agent)
        pr = cursor_gate.prober(agent, screen)
        det = unit_detector.UnitDetector()
        if warp is not None:  # a stand cell (the caller checks it) where monsters roam
            r.gm(agent, screen, f"@warp prt_fild08 {warp[0]} {warp[1]}")
            time.sleep(2.5)
            bench.close_chat(agent, screen)  # the typed line left the chat input open (16:25)
        here = [(gw / 2, gh / 2)]

        def boxes() -> list[Any]:
            return [b for b in det.detect(screen.grab(gx0, gy0, gw, gh)[1])
                    if not loot1.in_ui(*f1.centre(b))]  # fmt: skip

        def both(kind: str, u: float, v: float, centres: list[tuple[float, float]]) -> None:
            bp = blink_point(u, v, centres, in_view)
            if bp is None:
                return
            glide(agent, (gx0, gy0), here[0], (u, v))
            time.sleep(SETTLE_S)
            fast = read(pr, agent, screen, (gx0, gy0), u, v, bp)
            t_s = time.monotonic()
            pr.park()
            pr.hover(u, v)
            std = pr.read(u, v)
            std_ms = round((time.monotonic() - t_s) * 1000)
            row = {"kind": kind, "at": [round(u, 1), round(v, 1)], "fast": fast["shape"],
                   "fast_why": fast.get("why"), "left_px": fast["left_px"],
                   "fast_ms": fast["ms"], "std": std["shape"], "std_ms": std_ms}  # fmt: skip
            if kind != "ground":  # the target still there? (a moved monster is no comparison)
                after = [f1.centre(b) for b in boxes() if b.cls == "monster" or kind == "npc"]
                row["moved"] = not any(np.hypot(cu - u, cv - v) <= 12 for cu, cv in after)
            here[0] = (u, v)
            rows.append(row)
            with out_path.open("a") as fh:
                fh.write(json.dumps(row) + "\n")
            print(json.dumps(row), flush=True)

        while time.monotonic() < deadline and (
                sum(x["kind"] == "monster" for x in rows) < n_mon
                or sum(x["kind"] == "ground" for x in rows) < n_ground):  # fmt: skip
            b1 = boxes()
            time.sleep(0.3)
            b2 = boxes()
            cs2 = [f1.centre(b) for b in b2]
            still = [b for b in b2 if b.cls == "monster" and any(
                np.hypot(*(np.array(f1.centre(x)) - f1.centre(b))) <= 6 for x in b1
                if x.cls == "monster")]  # fmt: skip
            if still and sum(x["kind"] == "monster" for x in rows) < n_mon:
                u, v = f1.centre(still[0])
                if in_view(u, v):
                    both("monster", u, v, [c for c in cs2 if c != (u, v)])
            if sum(x["kind"] == "ground" for x in rows) < n_ground:
                for _ in range(20):
                    u, v = float(rng.uniform(120, gw - 120)), float(rng.uniform(120, gh - 160))
                    if in_view(u, v) and all(np.hypot(u - cu, v - cv) > 100 for cu, cv in cs2):
                        both("ground", u, v, cs2)
                        break
        if npc:
            check_npc(agent, screen, pr, det, both, boxes, (gx0, gy0, gw, gh))
        pr.park()
    return report(rows, out_path)


def check_npc(agent: Any, screen: Any, pr: Any, det: Any, both: Any, boxes: Any,
              region: tuple[int, int, int, int]) -> None:  # fmt: skip
    """The Poring War Recruiter (prt_fild08 159,371; it looks like a Poring): @warp to a legal
    stand cell ~5 south of it (outside warp spans and touch areas), then 5 reads on its sprite."""
    import bench
    import farm1 as f1
    import ro_agent as r
    import walk5 as w5
    from anim_region import stand_grid

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod
    from poring_env import selfpos

    gat = gatmod.parse((cam.GAT_DIR / "prt_fild08.gat").read_bytes())
    ok = stand_grid("prt_fild08", gat)
    stand = next(((159 + dx, 371 - dy) for dy in (5, 6, 4, 7) for dx in (0, 1, -1, 2, -2)
                  if ok[371 - dy, 159 + dx]), None)  # fmt: skip
    if stand is None:
        print(json.dumps({"npc": "no legal stand cell near 159,371"}), flush=True)
        return
    r.gm(agent, screen, f"@warp prt_fild08 {stand[0]} {stand[1]}")
    time.sleep(2.5)
    bench.close_chat(agent, screen)
    gx0, gy0, gw, gh = region
    xy = selfpos.read_minimap_xy(np.asarray(screen.grab(gx0, gy0, gw, gh)[1])[..., :3].copy(),
                                 selfpos.load_digit_templates())  # fmt: skip
    if xy is None or (int(xy[0]), int(xy[1])) != stand:
        print(json.dumps({"npc": f"warp not confirmed: minimap {xy}, wanted {stand}"}), flush=True)
        return
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    world = w5.World(cam.camera_from_json(cj["camera"]), gat, stand)
    fu, fv = (float(c) for c in world.project([(159, 371)])[0])
    for _ in range(5):
        bs = boxes()
        near = [b for b in bs if np.hypot(*(np.array(f1.foot(b)) - (fu, fv))) <= 40]
        if not near:
            print(json.dumps({"npc": "no box on the NPC", "feet": [fu, fv]}), flush=True)
            time.sleep(0.5)
            continue
        u, v = f1.centre(near[0])
        both("npc", u, v, [f1.centre(b) for b in bs if b is not near[0]])


def report(rows: list[dict[str, Any]], path: Path) -> int:
    ok_rows = [x for x in rows if not x.get("moved")]
    false_sword = [x for x in ok_rows if x["fast"] == "sword" and x["std"] != "sword"]
    std_sword = [x for x in ok_rows if x["std"] == "sword"]
    hit = [x for x in std_sword if x["fast"] == "sword"]
    npc_sword = [x for x in ok_rows if x["kind"] == "npc" and x["fast"] == "sword"]
    fast_ms = sorted(x["fast_ms"] for x in ok_rows)
    std_ms = sorted(x["std_ms"] for x in ok_rows)
    out = {
        "rows": len(rows), "compared": len(ok_rows), "moved_excluded": len(rows) - len(ok_rows),
        "false_sword": len(false_sword), "std_sword": len(std_sword),
        "fast_sword_of_those": len(hit),
        "npc_reads": sum(x["kind"] == "npc" for x in ok_rows), "npc_fast_sword": len(npc_sword),
        "agree": sum(x["fast"] == x["std"] for x in ok_rows),
        "fast_ms_p50": fast_ms[len(fast_ms) // 2] if fast_ms else None,
        "std_ms_p50": std_ms[len(std_ms) // 2] if std_ms else None, "log": str(path),
    }  # fmt: skip
    out["passes"] = bool(
        out["false_sword"] == 0
        and out["std_sword"] >= 10
        and len(hit) >= 0.8 * len(std_sword)
        and out["npc_fast_sword"] == 0
    )
    print(json.dumps(out, indent=1), flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--monsters", type=int, default=15)
    c.add_argument("--ground", type=int, default=10)
    c.add_argument("--npc", action="store_true")
    c.add_argument("--minutes", type=float, default=10.0)
    c.add_argument("--warp", type=int, nargs=2, default=None)
    a = ap.parse_args()
    return check(a.monsters, a.ground, a.npc, a.minutes, tuple(a.warp) if a.warp else None)


if __name__ == "__main__":
    sys.exit(main())
