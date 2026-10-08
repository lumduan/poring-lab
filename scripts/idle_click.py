#!/usr/bin/env python3
"""idle@1 (demonstrations 3.23, pre-registered 2026-10-08 before any run): does the client drop
the FIRST world click after idle, or after chat typing? And where does a signboard's hit area end?

    idle_click.py idle [--n 30] [--seed 20261066]     the 2 x 2 (T15 / T2 / N15 / N2), interleaved
    idle_click.py sign [--n 5]                        the signboard hit-area positive case

Every trial: warp back to the start cell (a GM command, typed in EVERY trial), wait 3 s, then
the condition's extra chat line (`/where`, closed after) or none, the idle (15 or 2 s, no input),
and the click EXACTLY as walk@12 makes it: the two-motion hover, the cursor read twice (WALK), the
click at the read point. A target that does not read WALK twice is skipped (recorded, never
clicked).

The outcome is judged OFFLINE from the session's packets: a `self_move_request` within 2 s of the
click; anything else is a FAILURE. Pixels in, input out: the harness never reads a packet to decide.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench  # noqa: E402
import record_session  # noqa: E402
import ro_agent as r  # noqa: E402
import walk6 as w6  # noqa: E402
import walk10 as w10  # noqa: E402

from poring_env.demo import DemoLog, new_session_id  # noqa: E402

MAP = "prt_church"
START = (98, 118)  # all 8 cells 3 away and their paths walkable; >= 11 cells from every TALK cell
SIGN_START = (102, 106)  # walk@12 route 31's cell: the wedding NPC's signboard in view
DIRS = [(3, 0), (-3, 0), (0, 3), (0, -3), (3, 3), (3, -3), (-3, 3), (-3, -3)]
CONDITIONS = {"T15": (True, 15.0), "T2": (True, 2.0), "N15": (False, 15.0), "N2": (False, 2.0)}
SETTLE_S = 3.0  # after the warp
JUDGE_S = 2.0  # a move request within this after the click
SIGN_OFFSETS = ("inside", 2.5, 5.0, 10.0)  # px below the sign's measured bottom outline
SIGN_SEARCH = (230, 140, 1130, 530)  # x0, y0, x1, y1 (client px): the world between the UI windows
CURSOR_REFS_V3 = r.ROOT / "data/walk6/cursor_refs_rdp_v3.npz"
OUT_ROOT = Path("/dev/shm/poring-lab-tmp/idle1")


def _world() -> tuple[Any, Any]:
    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    gat = gatmod.parse((cam.GAT_DIR / f"{MAP}.gat").read_bytes())
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    camera = cam.camera_for_map(cam.camera_from_json(cj["camera"]), True,
                                cj["indoor"]["yaw_deg"], cj["indoor"]["distance"])  # fmt: skip
    return camera, gat


def sign_box(img: np.ndarray) -> tuple[int, int, int, int] | None:
    """The signboard's box (x0, y0, x1, y_bottom) in client px: its orange/gold border, then the
    last dark outline row under it. None when no sign is in view."""
    rgb = img[..., 2::-1].astype(int)  # BGR(A) -> RGB
    sx0, sy0, sx1, sy1 = SIGN_SEARCH
    rr_, gg, bb = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    orange = (rr_ > 180) & (gg > 110) & (gg < 200) & (bb < 90)
    orange[:sy0], orange[sy1:], orange[:, :sx0], orange[:, sx1:] = False, False, False, False
    ys, xs = np.nonzero(orange)
    if len(xs) < 200:
        return None
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    dark = rgb.sum(-1) < 60
    bottom = y1
    for y in range(y1 + 1, min(y1 + 6, rgb.shape[0])):
        if dark[y, x0 : x1 + 1].sum() >= 10:
            bottom = y
    return x0, y0, x1, bottom


def _record(out: str, region: tuple[int, int, int, int], stop: Any, hz: float) -> None:
    from PIL import Image

    screen = r.Screen()
    k = 0
    while not stop.is_set():
        t0 = time.monotonic()
        t, img = screen.grab(*region)
        Image.fromarray(np.ascontiguousarray(img[..., 2::-1])).save(
            Path(out) / f"{k:05d}-{t}.jpg", quality=90
        )
        k += 1
        time.sleep(max(0.0, 1.0 / hz - (time.monotonic() - t0)))


def _click_walk(agent: Any, pr: Any, u: float, v: float) -> dict[str, Any]:
    """The rule's click: two-motion hover, read twice, click at the read point if both read WALK."""
    pr.park()
    pr.hover(u, v)
    a = pr.read(u, v)
    b = pr.read(u, v)
    out: dict[str, Any] = {"at": [round(u, 1), round(v, 1)], "reads": [a["shape"], b["shape"]]}
    if a["shape"] != w6.WALK or b["shape"] != w6.WALK:
        out["clicked"] = False
        return out
    gx, gy, _, _ = r.game_region()
    out["t_click"] = r.ns()
    agent.click(gx + round(u), gy + round(v))  # the DELIBERATE walk click
    out["clicked"] = True
    return out


def judge(trials: list[dict[str, Any]], events: list[dict[str, Any]]) -> dict[str, Any]:
    reqs = sorted(e["t_mono_ns"] for e in events if e.get("type") == "self_move_request")
    per: dict[str, dict[str, int]] = {}
    for t in trials:
        c = per.setdefault(t["condition"], {"clicked": 0, "walked": 0, "failed": 0, "skipped": 0})
        if not t.get("clicked"):
            c["skipped"] += 1
            continue
        c["clicked"] += 1
        ok = any(t["t_click"] <= q <= t["t_click"] + int(JUDGE_S * 1e9) for q in reqs)
        t["walked"] = ok
        c["walked" if ok else "failed"] += 1
    return {"per_condition": per}


def _session(name: str) -> tuple[str, DemoLog, int]:
    sid = new_session_id(name)
    log = DemoLog(sid)
    lock = record_session.read_lock(r.ROOT / "state")
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena", rule=name,
              map=MAP, account="gm")  # fmt: skip
    return sid, log, r.ns()


def _finish(sid: str, log: DemoLog, t_first: int, trials: list[dict[str, Any]],
            out: Path) -> dict[str, Any]:  # fmt: skip
    events, anchor = record_session.write_packets(log.dir, t_first, r.ns())
    verdict = judge(trials, events)
    result = {"session": sid, "frames": str(out), **verdict}
    log.finish(packet_events=len(events), packet_anchor=anchor, result=result, trials=trials)
    (out / "trials.jsonl").write_text("".join(json.dumps(t) + "\n" for t in trials))
    return result


def idle(n: int, seed: int) -> int:
    import multiprocessing as mp

    from poring_dataset import picking

    camera, gat = _world()
    refs = w6.CursorRefs.load(CURSOR_REFS_V3)
    order = [c for c in CONDITIONS for _ in range(n)]
    rng = random.Random(seed)
    rng.shuffle(order)
    sid, log, t_first = _session("idle1")
    out = OUT_ROOT / sid
    (out / "frames").mkdir(parents=True, exist_ok=True)
    ctx = mp.get_context("spawn")
    stop = ctx.Event()
    rec = ctx.Process(target=_record, args=(str(out / "frames"), tuple(r.game_region()), stop, 4.0),
                      daemon=True)  # fmt: skip
    trials: list[dict[str, Any]] = []
    rec.start()
    try:
        with r.session("rule:idle1") as (agent, screen):
            pr = w10.Prober9(agent, screen, refs)
            for k, cond in enumerate(order):
                typed, idle_s = CONDITIONS[cond]
                rel = DIRS[rng.randrange(len(DIRS))]
                pts = picking.safe_points(camera, gat, START, rel, k=1)
                r.gm(agent, screen, f"@warp {MAP} {START[0]} {START[1]}")
                bench.close_chat(agent, screen)
                time.sleep(SETTLE_S)
                if typed:
                    r.chat_line(agent, screen, "/where")
                    bench.close_chat(agent, screen)
                time.sleep(idle_s)  # no input of any kind
                t: dict[str, Any] = {"k": k, "condition": cond, "rel": list(rel)}
                if not pts:
                    t.update(clicked=False, why="no safe point")
                else:
                    t.update(_click_walk(agent, pr, *pts[0]))
                trials.append(t)
                print(json.dumps(t), flush=True)
                time.sleep(JUDGE_S + 0.5)
    finally:
        stop.set()
        rec.join(timeout=5)
        result = _finish(sid, log, t_first, trials, out)
        print(json.dumps(result, indent=1), flush=True)
    return 0


def sign(n: int) -> int:
    refs = w6.CursorRefs.load(CURSOR_REFS_V3)
    sid, log, t_first = _session("idle1-sign")
    out = OUT_ROOT / sid
    out.mkdir(parents=True, exist_ok=True)
    order = [o for o in SIGN_OFFSETS for _ in range(n)]
    random.Random(20261067).shuffle(order)
    trials: list[dict[str, Any]] = []
    try:
        with r.session("rule:idle1-sign") as (agent, screen):
            pr = w10.Prober9(agent, screen, refs)
            for k, off in enumerate(order):
                r.gm(agent, screen, f"@warp {MAP} {SIGN_START[0]} {SIGN_START[1]}")
                bench.close_chat(agent, screen)
                time.sleep(SETTLE_S)
                time.sleep(2.0)  # N2's sequence: the control of idle@1
                pr.park()
                img = screen.grab(*r.game_region())[1]
                box = sign_box(img)
                t: dict[str, Any] = {"k": k, "condition": f"sign:{off}", "box": box}
                if box is None:
                    t.update(clicked=False, why="no sign in view")
                else:
                    x0, y0, x1, bottom = box
                    u = x0 + 0.66 * (x1 - x0)  # the title bar, clear of the icon square
                    v = (y0 + bottom) / 2 if off == "inside" else bottom + float(off)
                    # inside a sign the cursor is the client's plain arrow too: it reads WALK
                    t.update(_click_walk(agent, pr, u, v))
                trials.append(t)
                print(json.dumps(t), flush=True)
                time.sleep(JUDGE_S + 0.5)
    finally:
        result = _finish(sid, log, t_first, trials, out)
        print(json.dumps(result, indent=1), flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("idle")
    a.add_argument("--n", type=int, default=30)
    a.add_argument("--seed", type=int, default=20261066)
    b = sub.add_parser("sign")
    b.add_argument("--n", type=int, default=5)
    args = ap.parse_args()
    return idle(args.n, args.seed) if args.cmd == "idle" else sign(args.n)


if __name__ == "__main__":
    sys.exit(main())
