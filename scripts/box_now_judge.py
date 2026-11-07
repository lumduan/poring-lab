#!/usr/bin/env python3
"""Pilot p8's own bars (docs/planning/rogue-xmas02.md 4N): the box targets per arm and per path,
the GPU's share outside R3's OFF windows (G1), the fresh detection's latency (G2), and E2's box
misses. E1 / E3 come from ``dungeon_judge.py row`` as before.

    box_now_judge.py SESSION_DIR [--step-log GUARDED_BUILD_LOG] [--out OUT.json]

- E2: box fights (``engage`` by box) ending as a ``box_miss`` (p7: 19 / 25, its positive case).
- G1: ``detections.jsonl`` rows that preferred the GPU, outside the step log's ``R3 pause`` ->
  ``R3 unpause`` intervals: the share the GPU served.
- G2: ``box_target`` events' ``boxes_after_ms`` (the request to the boxes), p50 by the path that
  served it.
- Per arm (assigned) and per path (served): box targets, a box found, the one hover's verdicts,
  struck, ``hover_from_grab_ms``, ``det_ms``.
Offline only; the packets are not read here.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

R3_LINE = re.compile(r"\] R3 (pause|unpause) \S+ \[(\d\d:\d\d:\d\d) ICT")


def r3_off_windows(lines: Iterable[str], day: str) -> list[tuple[float, float]]:
    """PURE: the (start, end) wall times the worker was paused, from guarded_build's R3 lines
    (ICT clock times on ``day``, YYYY-MM-DD); an unclosed pause runs to +inf."""
    out: list[tuple[float, float]] = []
    start: float | None = None
    for line in lines:
        m = R3_LINE.search(line)
        if m is None:
            continue
        t = datetime.fromisoformat(f"{day}T{m.group(2)}+07:00").timestamp()
        if m.group(1) == "pause":
            start = t
        elif start is not None:
            out.append((start, t))
            start = None
    if start is not None:
        out.append((start, float("inf")))
    return out


def paused(t: float, windows: Sequence[tuple[float, float]]) -> bool:
    return any(a <= t < b for a, b in windows)


def p50(vals: Sequence[float]) -> float | None:
    return round(statistics.median(vals), 1) if vals else None


def g1(rows: Sequence[dict[str, Any]], windows: Sequence[tuple[float, float]]) -> dict[str, Any]:
    """PURE: of the GPU-preferring detections outside the OFF windows, the GPU's share."""
    asked = [r for r in rows if r.get("prefer") == "gpu" and not paused(r["t_wall"], windows)]
    gpu = sum(1 for r in asked if r.get("path") == "gpu")
    reasons = Counter(str(r.get("reason")).split(":")[0] for r in asked if r.get("path") != "gpu")
    in_off = [r for r in rows if r.get("prefer") == "gpu" and paused(r["t_wall"], windows)]
    return {"asked_outside_off": len(asked), "gpu": gpu,
            "share": round(gpu / len(asked), 4) if asked else None,
            "not_gpu_reasons": dict(reasons), "asked_in_off": len(in_off),
            "gpu_in_off": sum(1 for r in in_off if r.get("path") == "gpu"),
            "pass": bool(asked) and gpu / len(asked) >= 0.90}  # fmt: skip


def targets(events: Sequence[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    """PURE: the box targets grouped by ``key`` ("arm" or "path")."""
    out: dict[str, dict[str, Any]] = {}
    for k in sorted({str(e.get(key)) for e in events}):
        es = [e for e in events if str(e.get(key)) == k]
        verdicts = Counter(v for e in es for v in e.get("verdicts") or [])
        hovered = sum(1 for e in es if e.get("verdicts"))
        out[k] = {
            "n": len(es), "fresh": sum(1 for e in es if e.get("fresh")),
            "box_found": sum(1 for e in es if e.get("box") is not None), "hovered": hovered,
            "verdicts": dict(verdicts), "struck": sum(1 for e in es if e.get("struck")),
            "struck_of_hovered": round(sum(1 for e in es if e.get("struck")) / hovered, 3)
            if hovered else None,
            "boxes_after_ms_p50": p50([e["boxes_after_ms"] for e in es if "boxes_after_ms" in e]),
            "det_ms_p50": p50([e["det_ms"] for e in es if e.get("det_ms") is not None]),
            "hover_from_grab_ms_p50": p50([e["hover_from_grab_ms"] for e in es
                                           if "hover_from_grab_ms" in e]),
        }  # fmt: skip
    return out


def judge(events: Sequence[dict[str, Any]], rows: Sequence[dict[str, Any]],
          windows: Sequence[tuple[float, float]]) -> dict[str, Any]:  # fmt: skip
    """PURE: the 4N bars from a session's events and detections and the step's OFF windows."""
    fights = sum(1 for e in events if e.get("kind") == "engage" and e.get("by") == "box")
    misses = sum(1 for e in events if e.get("kind") == "box_miss")
    bt = [e for e in events if e.get("kind") == "box_target"]
    by_path = targets(bt, "path")
    g_ms = by_path.get("gpu", {}).get("boxes_after_ms_p50")
    c_ms = by_path.get("cpu", {}).get("boxes_after_ms_p50")
    return {
        "e2": {"box_fights": fights, "box_misses": misses,
               "share": round(misses / fights, 4) if fights else None,
               "pass": bool(fights) and misses / fights <= 0.50},
        "g1": g1(rows, windows),
        "g2": {"gpu_p50_ms": g_ms, "cpu_p50_ms": c_ms,
               "pass": g_ms is not None and c_ms is not None and g_ms <= 100.0
               and g_ms <= 0.5 * c_ms},
        "by_arm": targets(bt, "arm"), "by_path": by_path, "off_windows": len(windows),
    }  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("session", type=Path)
    ap.add_argument("--step-log", type=Path, default=None)
    ap.add_argument("--day", default=None, help="the step log's date (default: the session's)")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    events = [json.loads(x) for x in (a.session / "events.jsonl").read_text().splitlines() if x]
    det = a.session / "detections.jsonl"
    rows = [json.loads(x) for x in det.read_text().splitlines() if x] if det.exists() else []
    day = a.day or datetime.strptime(a.session.name[:8], "%Y%m%d").strftime("%Y-%m-%d")
    windows = r3_off_windows(a.step_log.read_text().splitlines(), day) if a.step_log else []
    res = {"session": a.session.name, **judge(events, rows, windows)}
    text = json.dumps(res, indent=1)
    if a.out:
        a.out.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
