#!/usr/bin/env python3
"""How much the client's UI windows HIDE monsters (Batt 2026-10-17, decision 4 on the 21:33 report:
"measure the cover; test a compact layout; adopt it only if monsters seen per 10 min rise AND every
UI-gate check still works"). OFFLINE, packets as truth; nothing here reaches a bot.

Every second of a banked hunt-flow session, each monster the server shows us (entity_appear ..
entity_vanish, its cell along its walk: hunt_core.walk_positions) is projected into the game region
with the camera on our GM's packet cell (flow_judge.gm_track, drop_blobs.Projector). A monster
whose sprite centre (the foot pixel SPRITE_UP px up) lies inside the 1280 x 720 region is "in
view"; it is "covered" when that point lies inside one of the client's static windows
(route_preview.UI_WINDOWS). The share of in-view monster-seconds covered, per window, says what a
compact layout could at most give back.

    ui_cover.py SID [SID ...]
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import json
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

DEMO = Path("/dev/shm/poring-lab-demo")
GW, GH = 1280, 720
SPRITE_UP = 20.0  # px: a prt_fild08 monster's sprite centre above its foot pixel (~40 px tall)
TARGETS = {1002, 1063, 1113, 1008}  # farm0.TARGETS
WINDOW_NAMES = ("basic_info+menu", "shortcut_bar", "top_centre", "minimap", "chat",
                "notice_left", "notice_right")  # fmt: skip


def window_of(u: float, v: float, windows: Sequence[Sequence[float]]) -> int | None:
    """PURE: the index of the first window (x0, y0, x1, y1) containing (u, v), else None."""
    for i, (x0, y0, x1, y1) in enumerate(windows):
        if x0 <= u <= x1 and y0 <= v <= y1:
            return i
    return None


def tally(points: Iterable[tuple[float, float, bool]],
          windows: Sequence[Sequence[float]]) -> dict[str, Any]:  # fmt: skip
    """PURE: (u, v, is_target) sprite centres, one per monster-second -> in-view seconds and the
    covered share, overall / targets only / per window."""
    n = Counter[str]()
    per = Counter[int]()
    for u, v, tgt in points:
        if not (0 <= u < GW and 0 <= v < GH):
            continue
        n["in_view"] += 1
        n["in_view_targets"] += tgt
        w = window_of(u, v, windows)
        if w is not None:
            n["covered"] += 1
            n["covered_targets"] += tgt
            per[w] += 1
    iv = n["in_view"]
    return {
        "in_view_s": iv,
        "covered_s": n["covered"],
        "covered_share": round(n["covered"] / iv, 4) if iv else None,
        "targets_in_view_s": n["in_view_targets"],
        "targets_covered_share": (
            round(n["covered_targets"] / n["in_view_targets"], 4) if n["in_view_targets"] else None
        ),  # fmt: skip
        "per_window_share": {
            WINDOW_NAMES[w] if w < len(WINDOW_NAMES) else str(w): round(c / iv, 4)
            for w, c in sorted(per.items())
        },  # fmt: skip
    }


def session_points(sid: str) -> list[tuple[float, float, bool]]:
    import drop_blobs as db
    import flow_judge as fj
    import hunt_core as hc

    d = DEMO / sid
    with gzip.open(d / "packets.jsonl.gz", "rt") as fh:
        pk = sorted((json.loads(x) for x in fh), key=lambda e: int(e["t_mono_ns"]))
    ev = [json.loads(x) for x in (d / "events.jsonl").read_text().splitlines() if x]
    t0 = next(int(e["t_ns"]) for e in ev if e.get("kind") == "loop_start")
    t1 = int(ev[-1]["t_ns"])
    man = json.loads((d / "manifest.json").read_text())
    proj = db.Projector(man.get("map", db.MAP))
    gm, _mv = fj.gm_track(pk)
    gm_t = [t for t, _c in gm]
    pos = hc.walk_positions(pk)
    pos_t = {g: [t for t, _c, _j in v] for g, v in pos.items()}
    lives = fj.alive(pk)
    job = {int(e["gid"]): int(e.get("job") or 0) for e in pk
           if e.get("type") == "entity_appear" and e.get("objtype") == 5}  # fmt: skip
    out: list[tuple[float, float, bool]] = []
    for t in range(t0, t1, 1_000_000_000):
        i = bisect.bisect_right(gm_t, t) - 1
        if i < 0:
            continue
        here = gm[i][1]
        for g, ls in lives.items():
            if not any(a <= t and (b is None or t < b) for a, b, _r in ls):
                continue
            j = bisect.bisect_right(pos_t.get(g, []), t) - 1
            if j < 0:
                continue
            c = pos[g][j][1]
            if max(abs(c[0] - here[0]), abs(c[1] - here[1])) > 25:
                continue
            uv = proj.project(here, [c])[0]
            out.append((float(uv[0]), float(uv[1]) - SPRITE_UP, job.get(g, 0) in TARGETS))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("sessions", nargs="+")
    a = ap.parse_args()
    import route_preview as rp

    pooled: list[tuple[float, float, bool]] = []
    res: dict[str, Any] = {}
    for sid in a.sessions:
        pts = session_points(sid)
        pooled += pts
        res[sid] = tally(pts, rp.UI_WINDOWS)
    res["pooled"] = tally(pooled, rp.UI_WINDOWS)
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
