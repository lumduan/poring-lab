#!/usr/bin/env python3
"""Offline seek benchmark for H.264 dataset sessions (Batt 2026-10-04: re-measure C3's seek on an
uncontended decoder; pre-registered in docs/benchmarks/h264-vs-png.md).

    h264_seek_bench.py SESSION [SESSION ...] [--n 200] [--clip 16] [--seed 20261004]

For each session, with the stream file held in memory and the reader training uses
(poring_dataset.h264: the live decoder's configuration, a fresh decoder per GOP, conversion of the
returned frames only, each one checked against the live checksum):
  * single: N random frames, each read alone (decode from the preceding IDR);
  * clip:   N random runs of --clip consecutive frames.
Reports p50/p95/p99 ms, ms per useful frame, the AUs decoded, and the host's load average.
Writes data/bench/h264/seek-offline-<stamp>.json (gitignored); never touches the NAS sessions.
"""

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import dataset_ship  # noqa: E402

from poring_dataset import h264  # noqa: E402

OUT = ROOT / "data" / "bench" / "h264"


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(p * len(xs)))], 1)


def bench(
    session: Path, n: int, clip: int, seed: int, threads: int, verify: bool
) -> dict[str, Any]:
    s = h264.H264Session(session, threads=threads)
    s._bytes()  # hold the file in memory: no IO inside the timings
    usable = s.usable()
    pos = {f: i for i, f in enumerate(s.frame_ids)}
    rng = random.Random(seed)
    single, single_aus = [], []
    for fid in rng.sample(usable, min(n, len(usable))):
        t0 = time.perf_counter()
        list(s.frames([fid], verify=verify))
        single.append((time.perf_counter() - t0) * 1000)
        single_aus.append(pos[fid] - s.gop_start(pos[fid]) + 1)
    starts = [f for f in usable if pos[f] + clip <= len(s.frame_ids)]
    clips, clip_aus = [], []
    for fid in rng.sample(starts, min(n, len(starts))):
        t0 = time.perf_counter()
        got = s.clip(fid, clip, verify=verify)
        clips.append((time.perf_counter() - t0) * 1000)
        clip_aus.append(pos[fid] + len(got) - s.gop_start(pos[fid]))
    idr_every = s.manifest.get("idr_every_s")
    return {
        "session": session.name, "idr_every_s": idr_every, "n": len(single),
        "threads": threads, "verify": verify,
        "single_ms": {"p50": pct(single, .5), "p95": pct(single, .95), "p99": pct(single, .99)},
        "single_aus_p50": pct([float(a) for a in single_aus], .5),
        "clip": clip,
        "clip_ms": {"p50": pct(clips, .5), "p95": pct(clips, .95), "p99": pct(clips, .99)},
        "clip_ms_per_frame_p50": round(pct(clips, .5) / clip, 1),
        "clip_aus_p50": pct([float(a) for a in clip_aus], .5),
    }  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("sessions", nargs="+")
    ap.add_argument("--datasets", type=Path, default=dataset_ship.NAS_ROOT)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--clip", type=int, default=16)
    ap.add_argument("--seed", type=int, default=20261004)
    ap.add_argument("--threads", type=int, default=h264.LIVE_THREADS)
    ap.add_argument("--no-verify", dest="verify", action="store_false")
    a = ap.parse_args(argv)
    load0 = os.getloadavg()
    t_start = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    results = [bench(Path(x) if "/" in x else a.datasets / x, a.n, a.clip, a.seed, a.threads,
                     a.verify) for x in a.sessions]  # fmt: skip
    report = {"started": t_start, "ended": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
              "loadavg_start": load0, "loadavg_end": os.getloadavg(), "nice": os.nice(0),
              "decoder": h264.decoder_versions(), "results": results}  # fmt: skip
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"seek-offline-{time.strftime('%Y%m%dT%H%M%S')}.json"
    path.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
