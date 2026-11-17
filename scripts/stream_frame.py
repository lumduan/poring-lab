#!/usr/bin/env python3
"""Grab ONE fresh frame of the Windows session the way the bot sees it, save it as a PNG, and print
a one-line JSON report. Read-only: no input, no lock change, no container change.

    python3 scripts/stream_frame.py --out /dev/shm/poring-lab-tmp/setup/stream-test.png

It uses ro_agent's screen helper (one `python` process inside the backend, the backend's own
GrabSource rule): the S2 frame bus while the lock says console and its writer heart-beats, the RDP
ring or X otherwise. It grabs twice, --gap seconds apart, so the report shows whether frames move.

The report: path, width, height, source ("bus" | "x11"), frame_id (the bus writer's, -1 for X),
age_ms (now minus the frame's capture/decode time: the host and the backend share
CLOCK_MONOTONIC), advanced (a newer frame arrived during the gap), dark_fraction (the share of
pixels darker than 16 in every channel). The setup wizard's stream test reads it
(setup_core.judge_frame). Scratch goes to /dev/shm (rule 7); --out must be under /dev/shm.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

DARK = 16


def dark_fraction(bgra: NDArray[np.uint8]) -> float:
    return float((bgra[..., :3].max(axis=2) < DARK).mean())


Grab = tuple[int, NDArray[np.uint8], int, str]  # ro_agent.Screen.grab_meta: t, BGRA, id, source


def report(out: Path, first: Grab, last: Grab, now_ns: int) -> dict[str, Any]:
    _, img1, fid1, _ = first
    t2, img2, fid2, src2 = last
    # the bus numbers its frames; an X grab is new every time, so compare the pixels there
    advanced = fid2 > fid1 if src2 == "bus" and fid1 >= 0 else not np.array_equal(img1, img2)
    return {
        "path": str(out),
        "width": int(img2.shape[1]),
        "height": int(img2.shape[0]),
        "source": src2,
        "source_first": first[3],
        "frame_id": int(fid2),
        "age_ms": round(max(0, now_ns - t2) / 1e6, 1),
        "advanced": bool(advanced),
        "dark_fraction": round(dark_fraction(img2), 4),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--gap", type=float, default=2.0, help="seconds between the two grabs")
    a = ap.parse_args()
    out = a.out.resolve()
    if not str(out).startswith("/dev/shm/"):
        sys.exit("--out must be under /dev/shm (rule 7: scratch and evidence in RAM)")
    here = Path(__file__).resolve().parent
    sys.path.insert(0, str(here))
    import ro_agent as r

    screen = r.Screen()
    try:
        w, h = r.desktop()
        first = screen.grab_meta(0, 0, w, h)
        time.sleep(a.gap)
        last = screen.grab_meta(0, 0, w, h)
        now = time.monotonic_ns()
    finally:
        screen.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    r.to_png(last[1], out)
    print(json.dumps(report(out, first, last, now)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
