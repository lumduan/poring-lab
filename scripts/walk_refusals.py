#!/usr/bin/env python3
"""The walk requests the server never answered in one run (rogue-xmas02.md 4AE, p23's U1 / U2;
committed before p23).

    walk_refusals.py SESSION_DIR [--lock LOCK.json]

OFFLINE ground truth only (packets, ADR-0007): nothing here reaches a runner.
- A ``self_move_request`` in the run's window (run_start .. run_end) is ANSWERED when a
  ``self_move`` (the server moving us) arrives within 0.3 s of it, else IGNORED.
- STUCK spans: runs of >= 3 consecutive ignored requests (no answered one between); each span's
  start (s into the run), length (first to last ignored request) and count; their total (U1).
- With ``--lock`` (lock_study.py's output): each box strike's class by its first walk request
  within -0.6 .. +1.0 s of the click: ignored / answered / none (U2 = class D with an ignored one).
p16-p21 by this definition (2026-11-09): stuck spans 133.9, 122.4, 110.3, 152.8, 132.9 s (p16,
p17, p19, p20, p21); class D with an ignored first request 14, 21, 15, 13, 12; p13r (before
--engage-screen) 0 s and 0.
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ANSWER_S = 0.3  # a self_move this soon after a request answers it
SPAN_MIN = 3  # consecutive ignored requests that make a stuck span
FIRST_REQ = (-0.6, 1.0)  # a strike's first walk request: this window around the click (s)


def classify(packets: Sequence[dict[str, Any]], t0: int, t1: int) -> list[tuple[int, bool]]:
    """PURE: (t_ns, answered) for every self_move_request in [t0, t1], in time order."""
    moves = sorted(int(p["t_mono_ns"]) for p in packets if p.get("type") == "self_move")
    out = []
    for p in sorted((p for p in packets if p.get("type") == "self_move_request"),
                    key=lambda p: p["t_mono_ns"]):  # fmt: skip
        t = int(p["t_mono_ns"])
        if not t0 <= t <= t1:
            continue
        i = bisect.bisect_left(moves, t)
        out.append((t, i < len(moves) and moves[i] - t <= ANSWER_S * 1e9))
    return out


def stuck_spans(reqs: Sequence[tuple[int, bool]], t0: int) -> list[dict[str, Any]]:
    """PURE: runs of >= SPAN_MIN consecutive ignored requests: start (s into the run), span, n."""
    spans: list[dict[str, Any]] = []
    cur: list[int] = []
    for t, ok in [*reqs, (0, True)]:  # a sentinel closes the last run
        if not ok:
            cur.append(t)
            continue
        if len(cur) >= SPAN_MIN:
            spans.append({"start_s": round((cur[0] - t0) / 1e9, 1),
                          "span_s": round((cur[-1] - cur[0]) / 1e9, 1), "n": len(cur)})  # fmt: skip
        cur = []
    return spans


def strike_requests(events: Sequence[dict[str, Any]], reqs: Sequence[tuple[int, bool]],
                    classes: dict[int, str]) -> dict[str, int]:  # fmt: skip
    """PURE: box strikes by (class, their first walk request: ignored / answered / none)."""
    c: Counter[str] = Counter()
    for e in events:
        if e.get("kind") != "strike" or e.get("by") != "box":
            continue
        t = int(e["t_ns"])
        first = next((ok for tr, ok in reqs
                      if t + FIRST_REQ[0] * 1e9 <= tr <= t + FIRST_REQ[1] * 1e9), None)  # fmt: skip
        state = "none" if first is None else "answered" if first else "ignored"
        c[f"{classes.get(t, '?')}:{state}"] += 1
    return dict(sorted(c.items()))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("session", type=Path)
    ap.add_argument("--lock", type=Path, default=None, help="lock_study.py's --out JSON")
    a = ap.parse_args(argv)
    events = [json.loads(x) for x in (a.session / "events.jsonl").read_text().splitlines() if x]
    t0 = next(int(e["t_ns"]) for e in events if e.get("kind") == "run_start")
    t1 = [int(e["t_ns"]) for e in events if e.get("kind") == "run_end"][-1]
    with gzip.open(a.session / "packets.jsonl.gz", "rt") as fh:
        packets = [json.loads(x) for x in fh if x.strip()]
    reqs = classify(packets, t0, t1)
    spans = stuck_spans(reqs, t0)
    out: dict[str, Any] = {"session": a.session.name, "requests": len(reqs),
                           "ignored": sum(not ok for _t, ok in reqs), "stuck_spans": spans,
                           "stuck_total_s": round(sum(s["span_s"] for s in spans), 1)}  # fmt: skip
    if a.lock is not None:
        doc = json.loads(a.lock.read_text())
        run = doc[0] if isinstance(doc, list) else doc
        classes = {int(s["t_ns"]): s["class"] for s in run["strikes"]}
        out["box_strikes"] = strike_requests(events, reqs, classes)
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
