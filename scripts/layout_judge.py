#!/usr/bin/env python3
"""v43's judge (Batt's hunting UI layout, 2026-10-19): how much more of the field the BOT SEES.
OFFLINE: packets are ground truth (ADR-0007); nothing here reaches a bot decision.

    layout_judge.py SID [SID ...] [--json]

The standard "seen / 10 min" counts monsters the SERVER sent into our view (packets): a screen
layout cannot change it. This judge measures the bot's own perception on the same ruler
(conversion_phases.analyse: every target life, its first frame on screen by the camera model, its
first detector box of the bot's own boxes.jsonl within DETECT_PX of its projected cell):
- bot_seen_10min: distinct target lives the bot's detector boxed, per back-to-back 10-min window
  of the judged run, the MEDIAN (flow_judge.sight_windowed's ruler);
- detected_share: boxed lives / lives that came on screen;
- onscreen_to_detect_s: p50 of the delay;
- uncovered_share: the share of first detections whose projected point lies in the area the
  STANDARD layout covers and the HUNTING layout does not (client_layout.RECTS): the layout's own
  contribution (0 by construction under the standard layout, apart from partly visible sprites).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

NS = 1_000_000_000
WIN_S = 600.0


def in_rects(u: float, v: float, rects: Any) -> bool:
    return any(x0 <= u < x1 and y0 <= v < y1 for x0, y0, x1, y1 in rects)


def windowed_median(times: list[int], t0: int, w1: int, win_s: float = WIN_S) -> float | None:
    """PURE: the median count per back-to-back window of ``win_s`` in [t0, w1) (the plain count
    scaled to 10 min when the run is shorter than two windows)."""
    n = int((w1 - t0) / NS // win_s)
    if n < 2:
        span = (w1 - t0) / NS
        return round(len(times) * 600 / span, 1) if span > 0 else None
    counts = sorted(sum(1 for t in times if t0 + k * win_s * NS <= t < t0 + (k + 1) * win_s * NS)
                    for k in range(n))  # fmt: skip
    mid = counts[(n - 1) // 2] if n % 2 else (counts[n // 2 - 1] + counts[n // 2]) / 2
    return round(mid * 600 / win_s, 1)


def row(sid: str) -> dict[str, Any]:
    import client_layout as cl
    import conversion_phases as cp
    import search_study as ss

    sess = ss.load_session(sid)
    res = cp.analyse(sid)
    fld = ss.Field(sess.events)
    paths = cp.Paths(fld)
    project = cp.camera_projector()
    lag = int(cp.LAG_S * NS)
    old, new = cl.RECTS["standard"], cl.RECTS["hunt"]
    det_t: list[int] = []
    delays: list[float] = []
    on = det = unc = 0
    for (g, _a), m in res.lives.items():
        if m.get("t_onscreen") is not None and sess.t0 <= m["t_onscreen"] < sess.w1:
            on += 1
        td = m.get("t_detect")
        if td is None or not sess.t0 <= td < sess.w1:
            continue
        det += 1
        det_t.append(int(td))
        if m.get("t_onscreen") is not None and td >= m["t_onscreen"]:
            delays.append((td - m["t_onscreen"]) / NS)
        off = paths.offset(int(g), int(td) - lag)
        if off is not None:
            u, v = (float(x) for x in project([off])[0])
            unc += in_rects(u, v, old) and not in_rects(u, v, new)
    delays.sort()
    return {"session": sid, "bot_seen_10min": windowed_median(det_t, sess.t0, sess.w1),
            "detected": det, "onscreen": on,
            "detected_share": round(det / on, 3) if on else None,
            "onscreen_to_detect_s": round(delays[len(delays) // 2], 2) if delays else None,
            "uncovered_share": round(unc / det, 3) if det else None}  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("sessions", nargs="+")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    rows = [row(s) for s in a.sessions]
    print(json.dumps(rows, indent=None if a.json else 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
