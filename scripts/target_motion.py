#!/usr/bin/env python3
"""Was a strike's target WALKING? (rogue-xmas02.md 4V, p14's study; committed before p14.)

    target_motion.py SESSION_DIR [--lock LOCK.json] [--by box]

OFFLINE ground truth only (packets, ADR-0007): nothing here reaches a runner.
- Every monster's cell over time from the packets: ``entity_appear`` (kind ``stand``: a cell;
  ``move``: from (x, y) to (x1, y1) at ``speed`` ms a cell, from its arrival time), ``entity_stop``
  (a cell), ``entity_vanish``. A move is interpolated along its straight line, one cell per
  ``speed`` ms (Chebyshev steps): close enough to say moving or not, and how far.
- Our cell: the last ``self_move``'s destination before the click (the strikes studied are
  clicked standing; a walking click is lock_study's ``walking``).
- For each strike: the monster nearest to our cell + the strike's ``rel`` at the click; whether
  it was moving at the GRAB (box strikes: the box_target's grab, ``verdict_from_grab_ms`` before
  that event; others: 0.3 s before the click) and at the click, and how many cells it moved
  between them. ``--lock`` adds each strike's class (lock_study.py's output, matched by t_ns).
p12 + p13 by this definition (2026-11-08): box strikes on a target walking at the grab 6, of
which 5 class D; on a standing target 25, of which 1 class D; 1 with no monster within 3 cells.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

MONSTER_OBJTYPE = 5
NEAR_CELLS = 3.0  # the nearest monster must be within this many cells of the clicked cell
GRAB_DEFAULT_S = 0.3  # non-box strikes: "the grab" this long before the click

Track = list[tuple[int, str, float, float, float | None, float | None, float]]


def tracks(packets: Iterable[dict[str, Any]]) -> dict[int, Track]:
    """PURE: gid -> [(t_ns, kind, x, y, x1, y1, ms a cell)] in arrival order (stand / move /
    gone)."""
    out: dict[int, Track] = defaultdict(list)
    for p in packets:
        t = p.get("t_mono_ns")
        if not isinstance(t, int):
            continue
        typ, gid = p.get("type"), p.get("gid")
        if typ == "entity_appear" and p.get("objtype") == MONSTER_OBJTYPE:
            sp = float(p.get("speed") or 200)
            if p.get("kind") == "move" and p.get("x1") is not None:
                out[gid].append((t, "move", p["x"], p["y"], p["x1"], p["y1"], sp))
            else:
                out[gid].append((t, "stand", p["x"], p["y"], None, None, sp))
        elif typ == "entity_stop" and gid in out:
            out[gid].append((t, "stand", p["x"], p["y"], None, None, 0.0))
        elif typ == "entity_vanish" and gid in out:
            out[gid].append((t, "gone", 0, 0, None, None, 0.0))
    return dict(out)


def position(track: Track, t: int) -> tuple[float, float, bool] | None:
    """PURE: (x, y, moving) at t from the last record at or before t; None before the first or
    after a vanish."""
    last = None
    for row in track:
        if row[0] > t:
            break
        last = row
    if last is None or last[1] == "gone":
        return None
    t0, kind, x, y, x1, y1, sp = last
    if kind == "stand" or x1 is None or y1 is None:
        return (float(x), float(y), False)
    steps = max(abs(x1 - x), abs(y1 - y))
    dur = steps * sp * 1e6
    f = min(1.0, (t - t0) / dur) if dur > 0 else 1.0
    return (x + (x1 - x) * f, y + (y1 - y) * f, f < 1.0)


def our_cell(packets: Sequence[dict[str, Any]], t: int) -> tuple[int, int] | None:
    """PURE: the destination of our last self_move at or before t."""
    cell = None
    for p in packets:
        if p.get("type") == "self_move" and isinstance(p.get("t_mono_ns"), int):
            if p["t_mono_ns"] > t:
                break
            cell = (int(p["x1"]), int(p["y1"]))
    return cell


def target_at(trs: dict[int, Track], cell: tuple[float, float], t_click: int,
              t_grab: int) -> dict[str, Any] | None:  # fmt: skip
    """PURE: the monster nearest to ``cell`` at the click (within NEAR_CELLS): its distance,
    moving at the grab / at the click, and the cells it moved between them."""
    best: dict[str, Any] | None = None
    for gid, tr in trs.items():
        pc = position(tr, t_click)
        if pc is None:
            continue
        d = math.hypot(pc[0] - cell[0], pc[1] - cell[1])
        if d > NEAR_CELLS or (best is not None and d >= best["dist"]):
            continue
        pg = position(tr, t_grab)
        moved = None if pg is None else round(math.hypot(pc[0] - pg[0], pc[1] - pg[1]), 2)
        best = {
            "gid": gid,
            "dist": round(d, 2),
            "moving_click": pc[2],
            "moving_grab": None if pg is None else pg[2],
            "moved_cells": moved,
        }
    return best


def study(events: Sequence[dict[str, Any]], packets: Sequence[dict[str, Any]],
          classes: dict[int, str] | None = None) -> list[dict[str, Any]]:  # fmt: skip
    """PURE: one row per strike (by, rel, its class if known, the target's motion)."""
    trs = tracks(packets)
    boxes = [e for e in events if e.get("kind") == "box_target" and e.get("struck")]
    rows = []
    for s in (e for e in events if e.get("kind") == "strike"):
        t_c = int(s["t_ns"])
        me = our_cell(packets, t_c)
        if me is None:
            continue
        t_g = t_c - int(GRAB_DEFAULT_S * 1e9)
        if s.get("by") == "box":
            bt = max((b for b in boxes if b["t_ns"] <= t_c and t_c - b["t_ns"] < 2e9),
                     key=lambda b: b["t_ns"], default=None)  # fmt: skip
            if bt is not None and bt.get("verdict_from_grab_ms") is not None:
                t_g = int(bt["t_ns"] - bt["verdict_from_grab_ms"] * 1e6)
        cell = (me[0] + s["rel"][0], me[1] + s["rel"][1])
        tgt = target_at(trs, cell, t_c, t_g)
        rows.append({"t_ns": t_c, "by": s.get("by"), "rel": s.get("rel"),
                     "class": (classes or {}).get(t_c), "target": tgt})  # fmt: skip
    return rows


def summary(rows: Sequence[dict[str, Any]], by: str | None = "box") -> dict[str, Any]:
    """PURE: strikes by (target walking at the grab?, class D?)."""
    c: Counter[str] = Counter()
    for r in rows:
        if by is not None and r["by"] != by:
            continue
        tgt = r["target"]
        state = "none" if tgt is None else "walking" if tgt["moving_grab"] else "standing"
        c[f"{state}:{'D' if r['class'] == 'D' else 'notD' if r['class'] else '?'}"] += 1
    return dict(sorted(c.items()))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("session", type=Path)
    ap.add_argument("--lock", type=Path, default=None, help="lock_study.py's --out JSON")
    ap.add_argument("--by", default="box", help="the strike path to summarise ('all': every)")
    a = ap.parse_args(argv)
    events = [json.loads(x) for x in (a.session / "events.jsonl").read_text().splitlines() if x]
    with gzip.open(a.session / "packets.jsonl.gz", "rt") as fh:
        packets = sorted((json.loads(x) for x in fh if x.strip()), key=lambda p: p["t_mono_ns"])
    classes = None
    if a.lock is not None:
        doc = json.loads(a.lock.read_text())
        runs = doc if isinstance(doc, list) else [doc]
        classes = {int(s["t_ns"]): s["class"] for run in runs for s in run["strikes"]}
    rows = study(events, packets, classes)
    print(json.dumps({"session": a.session.name,
                      "summary": summary(rows, None if a.by == "all" else a.by),
                      "rows": rows}))  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
