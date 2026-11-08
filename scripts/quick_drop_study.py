#!/usr/bin/env python3
"""--quick-drop's scorer (rogue-xmas02.md 4W, pilot p15; committed before it).

    quick_drop_study.py SESSION_DIR --lock LOCK.json

From the session's events and lock_study.py's per-strike classes (packets: K / A started an
attack, D did not):
- the time held on class-D strikes (``owned_s``): count, median, total;
- every ``quick_drop`` event matched to the strike just before it (the one it gave up): its class;
  a dropped K / A is a good strike given up too early (4W's Q2);
- the quick drops by why (no_arrow / no_hit) and how many re-armed the box path.
p13r by this definition (2026-11-08): class D 7, held median 7.22 s, total 49.2 s; no quick drop
(the flag did not exist).
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def held_on_d(strikes: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """PURE: the class-D strikes' held time (owned_s)."""
    own = [float(s["owned_s"]) for s in strikes if s.get("class") == "D" and
           s.get("owned_s") is not None]  # fmt: skip
    return {"d": len(own), "held_median_s": round(statistics.median(own), 2) if own else None,
            "held_total_s": round(sum(own), 1)}  # fmt: skip


def drops(events: Sequence[dict[str, Any]], classes: dict[int, str]) -> dict[str, Any]:
    """PURE: each quick_drop matched to the latest strike before it; by why, re-armed, and the
    dropped strikes' classes."""
    strikes = sorted(int(e["t_ns"]) for e in events if e.get("kind") == "strike")
    out: Counter[str] = Counter()
    why: Counter[str] = Counter()
    rearm = 0
    for e in events:
        if e.get("kind") != "quick_drop":
            continue
        why[str(e.get("why"))] += 1
        rearm += bool(e.get("rearm"))
        before = [t for t in strikes if t <= int(e["t_ns"])]
        out[classes.get(before[-1], "?") if before else "none"] += 1
    return {"quick_drops": sum(why.values()), "by_why": dict(why), "rearmed": rearm,
            "dropped_classes": dict(out),
            "good_dropped": out.get("K", 0) + out.get("A", 0)}  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("session", type=Path)
    ap.add_argument("--lock", type=Path, required=True, help="lock_study.py's --out JSON")
    a = ap.parse_args(argv)
    events = [json.loads(x) for x in (a.session / "events.jsonl").read_text().splitlines() if x]
    doc = json.loads(a.lock.read_text())
    run = doc[0] if isinstance(doc, list) else doc
    classes = {int(s["t_ns"]): s["class"] for s in run["strikes"]}
    print(json.dumps({"session": a.session.name, **held_on_d(run["strikes"]),
                      **drops(events, classes)}))  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
