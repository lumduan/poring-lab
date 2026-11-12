#!/usr/bin/env python3
"""The live detector's speed in one run (rogue-xmas02.md 4T, p13's D1 / D2; committed before it).

    detect_speed.py SESSION_DIR

From the session's own logs, nothing else:
- ``detections.jsonl`` (the box watcher's every call): the count by path (gpu / cpu / fallback)
  and the GPU calls' ``ms`` (host clock, the frame to the decoded boxes) p50 / p95. Since
  dungeon@9.29c, --hud-fast's HUD-only GPU calls are logged apart (``detections_hud.jsonl``), so
  this is the decisions' calls only; s73's 93.5-ms p95 (rogue-xmas02.md 4CI) still counted both;
- ``events.jsonl``'s ``box_target`` events: ``det_ms``, ``boxes_after_ms`` (the boxes after the
  grab), ``verdict_from_grab_ms`` (the sword verdict after the grab), each p50 over the events that
  carry it, and how many were struck.
p12's figures (computed the same way): 1,811 calls, all gpu, p50 64.7 / p95 68.3 ms; 26 box
targets, boxes after the grab p50 89 ms, the verdict p50 319 ms, 19 struck.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

BOX_KEYS = ("det_ms", "boxes_after_ms", "hover_from_grab_ms", "verdict_from_grab_ms")


def pct(values: Sequence[float], q: float) -> float | None:
    """PURE: the q-quantile by the lower index (as the lab's other summaries), None if empty."""
    if not values:
        return None
    s = sorted(values)
    return float(s[min(len(s) - 1, int(q * len(s)))])


def detections(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """PURE: the calls by path and the GPU calls' ms p50 / p95."""
    rows = list(rows)
    paths = Counter(str(r.get("path")) for r in rows)
    gpu = [float(r["ms"]) for r in rows if r.get("path") == "gpu" and r.get("ms") is not None]
    n = len(rows)
    return {"calls": n, "paths": dict(paths), "gpu_share": (paths["gpu"] / n) if n else None,
            "gpu_ms_p50": statistics.median(gpu) if gpu else None,
            "gpu_ms_p95": pct(gpu, 0.95)}  # fmt: skip


def box_targets(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """PURE: the box path's timings (each key's p50 over the events carrying it), struck count."""
    bt = [e for e in events if e.get("kind") == "box_target"]
    out: dict[str, Any] = {"box_targets": len(bt), "struck": sum(bool(e.get("struck")) for e in bt)}
    for k in BOX_KEYS:
        v = [float(e[k]) for e in bt if isinstance(e.get(k), (int, float))]
        out[f"{k}_p50"] = statistics.median(v) if v else None
        out[f"{k}_n"] = len(v)
    return out


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    out = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("session", type=Path)
    a = ap.parse_args(argv)
    rep = {"session": a.session.name,
           **detections(read_jsonl(a.session / "detections.jsonl")),
           **box_targets(read_jsonl(a.session / "events.jsonl"))}  # fmt: skip
    print(json.dumps(rep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
