#!/usr/bin/env python3
"""A short MP4 of a hunt run with the HUD and the route preview drawn (route_demo's renderer).

    hunt_clip.py SESSION --start-min A --minutes M    -> .../hunt/clips/SESSION-clip-HHMMSS.mp4

The run's recorder (5 Hz game-region JPEGs) and its hud.jsonl / live.jsonl are the inputs; a window
of M minutes from A minutes after the loop start is linked into a scratch dir and rendered. The
frames are read from the manifest's `frames_dir` (the NAS since 2026-10-16), else the rec dir, else
the NAS copy of a moved run. Client pixels: the clip stays in /dev/shm or the NAS, never in git.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> int:
    import route_demo

    from poring_env.demo import DEMO_ROOT

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("session")
    ap.add_argument("--start-min", type=float, default=0.0)
    ap.add_argument("--minutes", type=float, default=3.0)
    a = ap.parse_args()
    d = DEMO_ROOT / a.session
    man = json.loads((d / "manifest.json").read_text())
    import hunt

    rec = Path(man["rec_dir"])
    nas = hunt.REC_ROOT / a.session
    cands = [Path(man["frames_dir"])] if man.get("frames_dir") else []
    cands += [rec / "frames", nas / "frames"]
    frames = next((p for p in cands if p.is_dir() and any(p.iterdir())), None)
    if frames is None:
        raise SystemExit(f"no frames for {a.session}")
    evs = [json.loads(x) for x in (d / "events.jsonl").read_text().splitlines() if x]
    t0 = next(e["t_ns"] for e in evs if e.get("kind") == "loop_start")
    lo = t0 + int(a.start_min * 60e9)
    hi = lo + int(a.minutes * 60e9)
    out = hunt.OUT / "clips" / f"{a.session}-clip-{time.strftime('%H%M%S')}"  # fresh: no deletion
    (out / "frames").mkdir(parents=True, exist_ok=True)
    k = 0
    for f in sorted(frames.glob("*.jpg")):
        t = int(f.stem.split("-")[1])
        if lo <= t <= hi:
            (out / "frames" / f"{k:05d}-{t}.jpg").symlink_to(f)
            k += 1
    for name in ("hud.jsonl", "live.jsonl"):
        src = next((p for p in (rec / name, nas / name) if p.exists()), None)
        if src is not None and not (out / name).exists():
            (out / name).symlink_to(src)
    route_demo.render(out)
    mp4 = out.parent / f"{out.name}.mp4"
    shutil.move(str(out / "route-demo.mp4"), mp4)
    print(json.dumps({"frames": k, "clip": str(mp4)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
