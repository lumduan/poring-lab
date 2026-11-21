#!/usr/bin/env python3
"""cursor-1080.md Phase 1 (pre-registered 2026-11-20, 2a0ad2dc): the PROBES of the cursor at 1080.
Why does a hover over a far monster box read no cursor at all in the runner's 0.35 s? (The older
cursor_probe.py is cursor@probe's Poring probe, cursor-robust.md; unrelated.)

    cursor_probe_1080.py hovers  --label L --mode stand|walk --n 60 --immune-confirmed  LIVE P1/P3
    cursor_probe_1080.py frames  --label L --mode stand|walk --seconds 30 --immune-confirmed  P2
    cursor_probe_1080.py analyse --label L [--json] [--stride 4] [--workers 3]       OFFLINE

LIVE steps run on the lab's Rogue (thief/rogue), IMMUNE (@monsterignore ON, judged on a frame;
--immune-confirmed says so), at xmas_dun02. MOVES ONLY over the monsters, never a click there:
the only clicks are WALK clicks (``--mode walk``), each at a point whose cursor read the WALK arrow
first (cursor_sword's CLEAR by the arrow, the pickup hand excluded), as the runner's walk clicks
do. Nothing is struck.

P1 (``hovers``): a monster box from the map's deployed detector (the GPU detect server, the CPU
behind it); its hover point is the runner's (the box centre: dungeon_hunt.box_hover_points[0]);
FAR = the point >= FAR_PX from our cell's point (dungeon_hunt.FOOT_PX), else NEAR, both within the
runner's reach (BOX_TARGET_PX); the two bands alternate. The pointer goes there in
cursor_sword.check's two motions; then for READ_S (1.0 s, not the runner's 0.35) every read keeps
- the reader's own 64 x 64 crop (cursor_sword.crop_at's box: the virtual client's pixels) and
- the REAL client's 160 x 160 pixels around the real pointer (ro_agent.real_xy's point),
with its time from the first motion and its bus frame ids; a read whose frame ids repeat the
previous read's keeps its time only (no pixels). Per hover also the real 160 x 160 around the
PREVIOUS pointer point (where the client's cursor stood) at the first read and at 0.35 s.
``--mode walk``: a walk click first, the hover WALK_LEAD_S after it (the camera scrolling).

P2 (``frames``): the bus counters, standing or walking: new frames per second (the writer's frame
ids) and the share of reads that repeat a frame, through the virtual client's box read.

P3 and the classes (``analyse``, offline): each read's recalls (cursor_sword.SwordRefs, the lab's
references), its verdict, the share of black (0) pixels in the reader's crop, its difference to
the real pixels at the point, and the cursor searched in the real 160 x 160 (the 64 x 64 window
slid by ``--stride`` px; the best SWORD / WALK / PICKUP recall and its offset from the real
point). Per hover, eye-free, over its whole window:
- sword_at_point: a read of the reader's crop is SWORD (the time of the first);
- sword_offset: none is, but the real box holds a SWORD (>= SWORD_MIN) > OFFSET_PX from the point;
- walk_at_point: the WALK arrow drawn at the point (the client says: no unit under it);
- old_place: no cursor read near the point; a cursor still drawn at the previous point;
- nothing: no cursor read anywhere in the boxes.
The runner's own decision is re-played on the reads inside 0.35 s (``runner``) beside the 1.0 s
one (``runner_at``). The reads are denser than the runner's (no recall in the loop), so the
replay is the runner's best case inside its window.

Pictures: the lab's own client only, in OUT/<label>/ (RAM), deleted after their verdict (the
plan's P1; rule 7). Nothing here is imported by a runner.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

OUT = Path("/dev/shm/poring-lab-tmp/cursor-probe")
CHAR, JOB, MAP = "thief", "rogue", "xmas_dun02"
FOOT_PX = (641, 362)  # dungeon_hunt.FOOT_PX: our cell's point in the 1280 x 720 client
REACH_PX = 220.0  # dungeon_hunt.BOX_TARGET_PX: the box targets the runner takes
FAR_PX = 120.0  # cursor-1080.md 5a: a FAR hover is >= 120 px from the centre
RUNNER_WINDOW_S = 0.35  # dungeon_hunt.CURSOR_WAIT_S
READ_S = 1.0  # the probe's window
# cursor-1080.md Amendment 5 (5a): the runner ALSO replayed at the chosen window (CURSOR_WAIT_S at
# 1080); the hover's reads cover it (READ_S >= it)
FIX_WINDOW_S = 0.75
READ_GAP_S = 0.005
HALF, REAL_HALF = 32, 80  # the reader's 64 x 64 crop; the real 160 x 160 box
APPROACH = (-3, -2)  # cursor_sword.check's first motion
OFFSET_PX = 6.0  # a cursor found further than this from the point: drawn elsewhere
WALK_LEAD_S = 0.15  # the hover after a walk click: the camera scrolling
# cursor-1080.md Amendment 4b's question (``--mode stop``): how long after she STOPS is a hover at
# 1080 safe? A walk click, the runner's own still rule (dungeon_hunt.still_now on route_preview's
# scene_shift of the virtual frames, ~60 ms apart, at most dungeon_hunt.STILL_MAX_S), then the
# hover STOP_DELAYS[i % 5] seconds later (cycled: each delay as often)
STOP_DELAYS = (0.0, 0.25, 0.5, 0.75, 1.0)
STILL_POLL_S = 0.06  # dungeon_hunt.wait_still's frame gap
WALK_RING = (170.0, 260.0)  # walk points: this far from our cell's point
WALK_CLEAR_PX = 90.0  # ... and this far from every box's hover point
WALK_TRIES = 6
MAX_STORED = 60  # reads with pixels kept per hover (new frames only)
FRAME_POLL_S = 0.004
PARK = (1250, 380)  # cursor_learn.PARK: the world's right edge


# --- pure -----------------------------------------------------------------------------------------
def hover_point(box: Sequence[float]) -> tuple[float, float]:
    """PURE: the runner's first hover point of a box (dungeon_hunt.box_hover_points[0])."""
    x0, y0, x1, y1 = (float(v) for v in box[:4])
    return ((x0 + x1) / 2, (y0 + y1) / 2)


def dist(u: float, v: float) -> float:
    """PURE: a point's distance from our cell's point."""
    return math.hypot(u - FOOT_PX[0], v - FOOT_PX[1])


def band(d: float, far_px: float = FAR_PX) -> str:
    """PURE: "far" or "near"."""
    return "far" if d >= far_px else "near"


# the runner's box targets are its detector's MONSTER boxes only (dungeon_hunt's box watcher:
# ``b.cls == "monster"``); cursor-1080.md Amendment 3 (2026-11-21): the first P1 picked HER OWN
# "player" box on 116 of 120 hovers (the client then draws the walk arrow), so it was void
TARGET_CLS = "monster"
# cursor-1080.md Amendment 4: an immune Rogue's monsters wander (they ignore her), so a hover may
# wait for one to come into reach: up to MISS_MAX looks in a row, MISS_WAIT_S apart (2 min)
MISS_MAX, MISS_WAIT_S = 120, 1.0


def pick_target(boxes: Sequence[Sequence[Any]], want: str, rng: random.Random,
                far_px: float = FAR_PX, reach_px: float = REACH_PX
                ) -> tuple[int, tuple[float, float]] | None:  # fmt: skip
    """PURE: a random MONSTER box (TARGET_CLS, the runner's) of band ``want`` within the
    runner's reach (its index and hover point); None when the band has none."""
    got = []
    for i, b in enumerate(boxes):
        if str(b[5]) != TARGET_CLS:
            continue
        u, v = hover_point(b)
        d = dist(u, v)
        if d <= reach_px and band(d, far_px) == want:
            got.append((i, (u, v)))
    return rng.choice(got) if got else None


def walk_points(boxes: Sequence[Sequence[Any]], rng: random.Random, n: int = WALK_TRIES,
                ring: tuple[float, float] = WALK_RING, clear_px: float = WALK_CLEAR_PX,
                ) -> list[tuple[float, float]]:  # fmt: skip
    """PURE: up to ``n`` walk points on the ring around our cell's point (flattened 0.7 in y, as
    the camera's ground), inside the world's middle (clear of the lab's panels: x 80..1200, y
    170..560), each >= ``clear_px`` from every box's hover point."""
    pts = [hover_point(b) for b in boxes]
    out: list[tuple[float, float]] = []
    for _ in range(200):
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(*ring)
        u, v = FOOT_PX[0] + r * math.cos(a), FOOT_PX[1] + r * math.sin(a) * 0.7
        if not (80 <= u <= 1200 and 170 <= v <= 560):
            continue
        if all(math.hypot(u - p, v - q) >= clear_px for p, q in pts):
            out.append((round(u, 1), round(v, 1)))
        if len(out) >= n:
            break
    return out


def is_walk_read(rec: Mapping[str, float]) -> bool:
    """PURE: the WALK arrow (cursor_sword's CLEAR by the arrow, never by the pickup hand)."""
    import cursor_sword as csw

    return (rec["walk"] >= csw.DRAWN_MIN and rec["sword"] < csw.CLEAR_SWORD_MAX
            and rec["pickup"] < csw.PICKUP_MIN)  # fmt: skip


def frame_stats(fids: Sequence[int], ts_ms: Sequence[float]) -> dict[str, Any]:
    """PURE: a read series' bus counters: the frames per second by the writer's ids, the new
    frames read per second, and the share of reads that repeat the previous read's frame."""
    if len(fids) < 2:
        return {"reads": len(fids), "fps": None, "new_per_s": None, "repeat_share": None}
    span_s = (ts_ms[-1] - ts_ms[0]) / 1e3
    new = sum(1 for a, b in zip(fids, fids[1:], strict=False) if b != a)
    ids = [f for f in fids if f >= 0]
    fps = (ids[-1] - ids[0]) / span_s if len(ids) >= 2 and span_s > 0 else None
    return {"reads": len(fids), "fps": round(fps, 1) if fps is not None else None,
            "new_per_s": round(new / span_s, 1) if span_s > 0 else None,
            "repeat_share": round(1 - new / (len(fids) - 1), 3)}  # fmt: skip


def runner_replay(reads: Sequence[Mapping[str, Any]], window_s: float = RUNNER_WINDOW_S) -> str:
    """PURE: the runner's decision on the reads inside its window (cursor_sword.series)."""
    import cursor_sword as csw

    return csw.series([r["verdict"] for r in reads if r["t_ms"] <= window_s * 1e3])


def classify(reads: Sequence[Mapping[str, Any]], prev: Sequence[Mapping[str, Any]],
             offset_px: float = OFFSET_PX) -> str:  # fmt: skip
    """PURE: a hover's class over its whole window (the module's list), from the analysed reads
    (each: verdict, real {class: [recall, dx, dy]}) and the previous point's boxes."""
    import cursor_sword as csw

    bars = {"sword": csw.SWORD_MIN, "walk": csw.DRAWN_MIN, "pickup": csw.PICKUP_MIN}
    if any(r["verdict"] == "sword" for r in reads):
        return "sword_at_point"
    for r in reads:
        s = (r.get("real") or {}).get("sword")
        if s and s[0] >= csw.SWORD_MIN and math.hypot(s[1], s[2]) > offset_px:
            return "sword_offset"
    if any(r["verdict"] == "clear" for r in reads):
        return "walk_at_point"
    for p in prev:
        if any((p.get(k) or [0.0])[0] >= bar for k, bar in bars.items()):
            return "old_place"
    return "nothing"


def first_ms(reads: Sequence[Mapping[str, Any]], verdict: str) -> float | None:
    """PURE: the time of the first read with that verdict."""
    return next((float(r["t_ms"]) for r in reads if r["verdict"] == verdict), None)


def pctl(xs: Sequence[float], q: float) -> float | None:
    """PURE: a nearest-rank percentile (None on no data)."""
    if not xs:
        return None
    s = sorted(xs)
    return float(s[min(len(s) - 1, max(0, math.ceil(q * len(s)) - 1))])


def stop_delay(i: int) -> float:
    """PURE (--mode stop): hover i's wait after the still scene."""
    return STOP_DELAYS[i % len(STOP_DELAYS)]


def group_key(h: Mapping[str, Any]) -> str:
    """PURE: a hover's group: mode / band, and for ``stop`` its delay after the still scene."""
    stop = h.get("stop")
    tail = f"/d{float(stop['delay_s']):.2f}" if isinstance(stop, Mapping) else ""
    return f"{h['mode']}/{h['band']}{tail}"


def summarise(hovers: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """PURE: per (mode, band[, stop delay]): the hovers, the runner's verdicts at 0.35 s and
    1.0 s, the classes over 1.0 s, the first SWORD's time (median / p90), the bus counters."""
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for h in hovers:
        groups.setdefault(group_key(h), []).append(h)
    out: dict[str, Any] = {}
    for key, hs in sorted(groups.items()):
        runner = Counter(h["runner"] for h in hs)
        runner_at = Counter(h["runner_at"] for h in hs)
        classes = Counter(h["class"] for h in hs)
        fs = [h["first_sword_ms"] for h in hs if h.get("first_sword_ms") is not None]
        fr = [h["first_read_ms"] for h in hs if h.get("first_read_ms") is not None]
        fps = [h["frames"]["fps"] for h in hs if h["frames"].get("fps") is not None]
        rep = [h["frames"]["repeat_share"] for h in hs
               if h["frames"].get("repeat_share") is not None]  # fmt: skip
        n = len(hs)
        out[key] = {
            "n": n,
            "runner": dict(runner),
            "runner_fix": dict(Counter(h.get("runner_fix") for h in hs)),
            "runner_fix_unknown_share": (
                round(sum(h.get("runner_fix") == "unknown" for h in hs) / n, 3) if n else None
            ),  # fmt: skip
            "runner_unknown_share": round(runner["unknown"] / n, 3) if n else None,
            "runner_at_1s": dict(runner_at),
            "classes": dict(classes),
            "first_sword_ms": {"median": pctl(fs, 0.5), "p90": pctl(fs, 0.9), "n": len(fs)},
            "first_read_ms_median": pctl(fr, 0.5),
            "fps_median": pctl(fps, 0.5),
            "repeat_share_median": pctl(rep, 0.5),
        }
    return out


# --- the reads (offline) ------------------------------------------------------------------------
def real_search(sw: Any, real: Any, stride: int) -> dict[str, list[float]]:
    """The best recall per class of the 64 x 64 window slid over a real box (160 x 160), with
    its hotspot's offset (dx, dy) from the box's centre: {class: [recall, dx, dy]}."""
    a = np.asarray(real)[..., :3]
    best: dict[str, list[float]] = {}
    span_y, span_x = a.shape[0] - 2 * HALF, a.shape[1] - 2 * HALF
    for oy in range(0, span_y + 1, stride):
        for ox in range(0, span_x + 1, stride):
            rec = sw.recalls(a[oy : oy + 2 * HALF, ox : ox + 2 * HALF])
            dx, dy = ox + HALF - a.shape[1] // 2, oy + HALF - a.shape[0] // 2
            for k, val in rec.items():
                if k not in best or val > best[k][0]:
                    best[k] = [round(float(val), 3), dx, dy]
    return best


def analyse_hover(stem: Path, sw: Any, stride: int) -> dict[str, Any]:
    """One stored hover (its .json and .npz): every read analysed, the hover classified."""
    import cursor_sword as csw

    meta = json.loads(stem.with_suffix(".json").read_text())
    arrs = np.load(stem.with_suffix(".npz"))
    vs, rs, ps = arrs["v"], arrs["r"], arrs["p"]
    reads: list[dict[str, Any]] = []
    k = 0
    for rd in meta["reads"]:
        if not rd.get("stored"):  # a repeated frame: the previous read's verdict
            reads.append({**rd, "verdict": reads[-1]["verdict"] if reads else "unknown"})
            continue
        v, rl = vs[k], rs[k]
        k += 1
        rec = sw.recalls(v)
        verdict = csw.verdict(rec)
        c0 = REAL_HALF - HALF
        centre = rl[c0 : c0 + 2 * HALF, c0 : c0 + 2 * HALF]
        row = {
            **rd,
            "rec": rec,
            "verdict": verdict,
            "black": round(float((np.asarray(v)[..., :3] == 0).all(-1).mean()), 3),
            "vr_diff": round(float(np.abs(v.astype(int) - centre.astype(int)).mean()), 2),
        }
        if verdict != "sword":
            row["real"] = real_search(sw, rl, stride)
        reads.append(row)
    prev = [real_search(sw, p, stride) for p in ps]
    out = {k_: meta[k_] for k_ in ("i", "mode", "band", "dist", "u", "v", "real_xy", "prev_xy",
                                   "box", "cls", "score", "det_ms", "walk", "ms", "stop")
           if k_ in meta}  # fmt: skip
    out.update(
        {
            "runner": runner_replay(reads),
            "runner_fix": runner_replay(reads, FIX_WINDOW_S),
            "runner_at": runner_replay(reads, READ_S),
            "class": classify(reads, prev),
            "first_sword_ms": first_ms(reads, "sword"),
            "first_clear_ms": first_ms(reads, "clear"),
            "first_read_ms": reads[0]["t_ms"] if reads else None,
            "frames": frame_stats([r["fid"] for r in reads], [r["t_ms"] for r in reads]),
            "black_max": max((r.get("black", 0.0) for r in reads), default=0.0),
            "vr_diff_max": max((r.get("vr_diff", 0.0) for r in reads), default=0.0),
            "reads": [
                {
                    k_: r.get(k_)
                    for k_ in ("t_ms", "fid", "verdict", "rec", "real", "black", "vr_diff")
                }
                for r in reads
            ],  # fmt: skip
            "prev": prev,
        }
    )
    return out


def _analyse_one(job: tuple[str, int]) -> dict[str, Any]:
    import cursor_sword as csw

    stem, stride = job
    return analyse_hover(Path(stem), csw.SwordRefs.load(), stride)


def analyse(label: str, stride: int = 4, workers: int = 3, root: Path = OUT) -> dict[str, Any]:
    """Every stored hover of a label, analysed (in ``workers`` processes); analysed.jsonl beside
    them; the summary returned."""
    d = root / label
    jobs = [(str(p.with_suffix("")), stride) for p in sorted(d.glob("h*.json"))]
    if workers > 1 and len(jobs) > 1:
        from multiprocessing import Pool

        with Pool(workers) as pool:
            hovers = pool.map(_analyse_one, jobs)
    else:
        hovers = [_analyse_one(j) for j in jobs]
    with (d / "analysed.jsonl").open("w") as fh:
        for h in hovers:
            fh.write(json.dumps(h) + "\n")
    return {"label": label, "hovers": len(hovers), "groups": summarise(hovers)}


# --- live -----------------------------------------------------------------------------------------
def _real_point(r: Any, u: float, v: float) -> tuple[int, int]:
    import cursor_learn as cl

    return cl.real_point(r, u, v)


def _real_box(screen: Any, xy: Sequence[int]) -> tuple[Any, int]:
    _, img, fid, _ = screen.grab_meta(int(xy[0]) - REAL_HALF, int(xy[1]) - REAL_HALF,
                                      2 * REAL_HALF, 2 * REAL_HALF)  # fmt: skip
    return np.ascontiguousarray(np.asarray(img)[..., :3]), fid


def probe_hover(agent: Any, screen: Any, r: Any, gx0: int, gy0: int, u: float, v: float,
                prev_xy: Sequence[int] | None, read_s: float = READ_S,
                ) -> tuple[dict[str, Any], dict[str, Any]]:  # fmt: skip
    """LIVE, moves only: cursor_sword.check's two motions to (u, v), then reads for ``read_s``.
    Returns (the hover's record, its arrays v / r / p)."""
    t0 = time.monotonic()
    agent.move(gx0 + round(u) + APPROACH[0], gy0 + round(v) + APPROACH[1])
    time.sleep(0.02)
    agent.move(gx0 + round(u), gy0 + round(v))
    rxy = _real_point(r, u, v)
    reads: list[dict[str, Any]] = []
    vs: list[Any] = []
    rs: list[Any] = []
    ps: list[Any] = []
    last: tuple[int, int] | None = None
    prev_due = [0.0, RUNNER_WINDOW_S] if prev_xy is not None else []
    while True:
        t_ms = (time.monotonic() - t0) * 1e3
        _, vimg, fid, _ = screen.grab_meta(gx0 + round(u) - HALF, gy0 + round(v) - HALF,
                                           2 * HALF, 2 * HALF)  # fmt: skip
        rimg, fid_r = _real_box(screen, rxy)
        if prev_due and prev_xy is not None and t_ms >= prev_due[0] * 1e3:
            prev_due.pop(0)
            ps.append(_real_box(screen, prev_xy)[0])
        stored = (fid, fid_r) != last and len(vs) < MAX_STORED
        last = (fid, fid_r)
        reads.append({"t_ms": round(t_ms, 1), "fid": fid, "fid_real": fid_r, "stored": stored})
        if stored:
            vs.append(np.ascontiguousarray(np.asarray(vimg)[..., :3]))
            rs.append(rimg)
        if t_ms >= read_s * 1e3:
            break
        time.sleep(READ_GAP_S)
    while prev_xy is not None and len(ps) < 2:
        ps.append(_real_box(screen, prev_xy)[0])
    rec = {"u": round(u, 1), "v": round(v, 1), "real_xy": list(rxy),
           "prev_xy": list(prev_xy) if prev_xy is not None else None, "reads": reads,
           "ms": round((time.monotonic() - t0) * 1e3)}  # fmt: skip
    vbox, rbox = (0, 2 * HALF, 2 * HALF, 3), (0, 2 * REAL_HALF, 2 * REAL_HALF, 3)
    arrays = {"v": np.stack(vs) if vs else np.zeros(vbox, np.uint8),
              "r": np.stack(rs) if rs else np.zeros(rbox, np.uint8),
              "p": np.stack(ps) if ps else np.zeros(rbox, np.uint8)}  # fmt: skip
    return rec, arrays


def walk_click(agent: Any, screen: Any, sw: Any, gx0: int, gy0: int,
               boxes: Sequence[Sequence[Any]], rng: random.Random) -> dict[str, Any]:  # fmt: skip
    """LIVE: a walk click at the first ring point whose cursor reads the WALK arrow TWICE: the
    hover's reads (two motions: cursor_sword.check) and one more read with no motion (the click
    census's rule: an allowed shape twice); no click when none does."""
    import cursor_sword as csw

    tried = 0
    for u, v in walk_points(boxes, rng):
        tried += 1
        res = csw.check(agent, screen, sw, gx0, gy0, u, v, wait_s=0.6)
        if res["verdict"] != "clear" or not is_walk_read(res["rec"]):
            continue
        again = sw.recalls(csw.crop_at(screen, gx0, gy0, u, v))
        if csw.verdict(again) != "clear" or not is_walk_read(again):
            continue
        agent.click(gx0 + round(u), gy0 + round(v))
        return {"clicked": [u, v], "tried": tried, "ms": res["ms"]}
    return {"clicked": None, "tried": tried}


def _detector() -> Any:
    import unit_detector as ud

    try:
        return ud.for_map_gpu(MAP)
    except ud.DetectorUnavailable:
        return ud.for_map(MAP)


def _boxes(det: Any, screen: Any, gx0: int, gy0: int) -> tuple[list[list[Any]], float]:
    t = time.monotonic()
    _, img = screen.grab(gx0, gy0, 1280, 720)
    boxes = det.detect(np.asarray(img)[..., :3])
    rows = [[b.x0, b.y0, b.x1, b.y1, b.score, b.cls] for b in boxes]
    return rows, round((time.monotonic() - t) * 1e3, 1)


def _start(label: str, immune: bool) -> Path:
    if not immune:
        raise SystemExit("cursor_probe_1080 refused: --immune-confirmed (immunity ON, judged on a "
                         "frame)")  # fmt: skip
    d = OUT / label
    d.mkdir(parents=True, exist_ok=True)
    return d


def wait_still(r: Any, screen: Any, gx0: int, gy0: int) -> tuple[bool, float]:
    """LIVE (--mode stop): the runner's still rule on the virtual frames (dungeon_hunt.wait_still:
    a frame every STILL_POLL_S, dungeon_hunt.still_now on route_preview.scene_shift, at most
    dungeon_hunt.STILL_MAX_S): (still, waited s). Reads only."""
    import dungeon_hunt as dh
    import route_preview as rp

    def frame() -> Any:
        return np.ascontiguousarray(
            np.asarray(r.grab_after_meta(screen, (gx0, gy0, 1280, 720), r.ns())[1])[..., :3]
        )

    t_w = time.monotonic()
    prev = frame()
    shifts: list[tuple[float, float]] = []
    while time.monotonic() - t_w < dh.STILL_MAX_S:
        time.sleep(STILL_POLL_S)
        cur = frame()
        shifts.append(rp.scene_shift(prev, cur))
        prev = cur
        if dh.still_now(shifts):
            break
    return dh.still_now(shifts), time.monotonic() - t_w


def cmd_hovers(a: argparse.Namespace) -> int:
    d = _start(a.label, a.immune_confirmed)  # the refusal before any import or input
    import crusader as cr
    import cursor_sword as csw
    import ro_agent as r

    rng = random.Random(a.seed)
    sw = csw.SwordRefs.load()
    det = _detector()
    done = len(list(d.glob("h*.json")))
    with r.session(f"rule:cursor-probe-1080-{a.mode}") as (agent, screen):
        agent.wait_for_human()
        if not cr.check(screen, JOB, CHAR)["ok"]:
            raise r.Stop(f"cursor_probe_1080: not the {CHAR} ({JOB})")
        gx0, gy0, gw, gh = r.game_region()
        info = {"label": a.label, "mode": a.mode, "virtual": r.virtual_active(),
                "real_region": list(r.real_game_region()), "region": [gx0, gy0, gw, gh],
                "t": time.strftime("%Y-%m-%d %H:%M:%S"), "seed": a.seed}  # fmt: skip
        (d / f"info-{a.mode}.json").write_text(json.dumps(info))
        prev_xy: Sequence[int] | None = None
        bands = ("far", "near")
        misses = 0
        i = done
        while i < done + a.n:
            walk = None
            stop: dict[str, Any] | None = None
            if a.mode in ("walk", "stop"):
                boxes, _ = _boxes(det, screen, gx0, gy0)
                walk = walk_click(agent, screen, sw, gx0, gy0, boxes, rng)
                if walk["clicked"] is None:
                    misses += 1
                    if misses > 20:
                        raise r.Stop("cursor_probe_1080: no walk point read the arrow 20 times")
                    continue
                prev_xy = _real_point(r, *walk["clicked"])
                if a.mode == "stop":
                    still, waited = wait_still(r, screen, gx0, gy0)
                    stop = {"still": still, "waited_ms": round(waited * 1e3),
                            "delay_s": stop_delay(i)}  # fmt: skip
                    time.sleep(stop["delay_s"])
                else:
                    time.sleep(WALK_LEAD_S)
            boxes, det_ms = _boxes(det, screen, gx0, gy0)
            got = pick_target(boxes, bands[i % 2], rng) or pick_target(boxes, bands[1 - i % 2],
                                                                        rng)  # fmt: skip
            if got is None:
                misses += 1
                if misses > MISS_MAX:
                    raise r.Stop(f"cursor_probe_1080: no monster box in reach {MISS_MAX} times "
                                 "in a row")  # fmt: skip
                time.sleep(MISS_WAIT_S)
                continue
            misses = 0  # CONSECUTIVE misses only (Amendment 4: 40 in all ended a sparse run)
            k, (u, v) = got
            rec, arrays = probe_hover(agent, screen, r, gx0, gy0, u, v, prev_xy, a.read_s)
            bx = boxes[k]
            rec.update(i=i, mode=a.mode, band=band(dist(u, v)), dist=round(dist(u, v), 1),
                       box=[round(float(x), 1) for x in bx[:4]], score=round(float(bx[4]), 3),
                       cls=bx[5], det_ms=det_ms, walk=walk,
                       **({"stop": stop} if stop is not None else {}))  # fmt: skip
            np.savez_compressed(d / f"h{i:03d}.npz", **arrays)
            (d / f"h{i:03d}.json").write_text(json.dumps(rec))
            prev_xy = rec["real_xy"]
            print(f"hover {i}: {rec['band']} {rec['dist']} px, {len(rec['reads'])} reads",
                  flush=True)  # fmt: skip
            i += 1
        agent.move(gx0 + PARK[0], gy0 + PARK[1])  # the pointer off the world's middle
    return 0


def cmd_frames(a: argparse.Namespace) -> int:
    d = _start(a.label, a.immune_confirmed)
    import cursor_sword as csw
    import ro_agent as r

    rng = random.Random(a.seed)
    sw = csw.SwordRefs.load()
    det = _detector() if a.mode == "walk" else None
    with r.session(f"rule:cursor-probe-1080-frames-{a.mode}") as (agent, screen):
        agent.wait_for_human()
        gx0, gy0, _, _ = r.game_region()
        fids: list[int] = []
        ts: list[float] = []
        walks = 0
        t0 = time.monotonic()
        next_walk = 0.0
        while (now := time.monotonic() - t0) < a.seconds:
            if det is not None and now >= next_walk:
                boxes, _ = _boxes(det, screen, gx0, gy0)
                got = walk_click(agent, screen, sw, gx0, gy0, boxes, rng)
                walks += got["clicked"] is not None
                next_walk = time.monotonic() - t0 + 1.2
            _, _, fid, _ = screen.grab_meta(gx0 + 600, gy0 + 300, 64, 64)
            fids.append(fid)
            ts.append((time.monotonic() - t0) * 1e3)
            time.sleep(FRAME_POLL_S)
        out = {"mode": a.mode, "seconds": a.seconds, "walk_clicks": walks,
               "virtual": r.virtual_active(), "real_region": list(r.real_game_region()),
               **frame_stats(fids, ts)}  # fmt: skip
    (d / f"frames-{a.mode}.json").write_text(json.dumps(out))
    print(json.dumps(out))
    return 0


def cmd_analyse(a: argparse.Namespace) -> int:
    got = analyse(a.label, a.stride, a.workers)
    (OUT / a.label / "summary.json").write_text(json.dumps(got, indent=1))
    print(json.dumps(got, indent=None if a.json else 1))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("hovers")
    f = sub.add_parser("frames")
    for p in (h, f):
        p.add_argument("--label", required=True)
        p.add_argument("--mode", choices=("stand", "walk", "stop"), required=True)
        p.add_argument("--immune-confirmed", action="store_true")
        p.add_argument("--seed", type=int, default=71)
    h.add_argument("--n", type=int, default=60)
    h.add_argument("--read-s", type=float, default=READ_S)
    f.add_argument("--seconds", type=float, default=30.0)
    an = sub.add_parser("analyse")
    an.add_argument("--label", required=True)
    an.add_argument("--stride", type=int, default=4)
    an.add_argument("--workers", type=int, default=3)
    an.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    cmds = {"hovers": cmd_hovers, "frames": cmd_frames, "analyse": cmd_analyse}
    return cmds[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
