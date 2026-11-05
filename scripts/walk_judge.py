#!/usr/bin/env python3
"""The patrol WALK's own numbers from a dungeon_hunt session's events (offline; no packets).

docs/planning/rogue-xmas02.md 4G (2026-11-06): xmas_dun02's dead ends came from the walk gate's
no-entry cue reading the orange floor as the client's red ring (dungeon@8.5): every false read
carved a 5 x 5 block out of the route grid until no waypoint routed and the runner flew. This
judge counts what the walk did:

- walk decisions (every ``walk`` event: a hover that ended in a click, a carve or a refusal);
- no-entry carves (``noentry_carve``) and their share of the walk decisions;
- the Fly Wings by reason (``escape`` events: dead_end, stuck, idle, pos_unread, ...);
- the dead ends answered by forgetting the carves (``uncarve``, dungeon@8.6);
- the ring reads (dungeon@8.6 logs ``ring`` = [on, out, dx, dy] and ``red`` on each walk):
  - ``ring_seen``: hovers the ring rule called a no-entry;
  - ``red_only_clicks``: CLICKS the old cue would have carved (red >= 25) but the ring rule did
    not -- the ring rule's live check: a ``stall`` after one (two clicks from that cell that did
    not move us) is a ring the rule may have missed;
- waypoints reached (``patrol`` reached events) and per minute.

Usage: ``walk_judge.py <session dir or events.jsonl> ...`` -> one JSON row per session.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

NOENTRY_RED = 25  # dungeon_hunt.NOENTRY_RED: the old cue (logged beside the ring since @8.6)
RING_IN_MIN, RING_OUT_MAX = 120, 20  # dungeon_hunt.RING_IN_MIN / RING_OUT_MAX


def ring_seen(ring: Any) -> bool:
    return bool(ring) and ring[0] >= RING_IN_MIN and ring[1] <= RING_OUT_MAX


def judge(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """PURE: the walk's numbers over one run's events (run_start .. run_end)."""
    evs = list(events)
    first, last = (evs[0]["t_ns"], evs[-1]["t_ns"]) if evs else (0, 0)
    t0 = next((e["t_ns"] for e in evs if e.get("kind") == "run_start"), first)
    t1 = next((e["t_ns"] for e in evs if e.get("kind") == "run_end"), last)
    minutes = max(0.0, (t1 - t0) / 60e9)
    walks = [e for e in evs if e.get("kind") == "walk"]
    flies = Counter(str(e.get("why")) for e in evs if e.get("kind") == "escape")
    carves = sum(1 for e in evs if e.get("kind") == "noentry_carve")
    reached = sum(1 for e in evs if e.get("kind") == "patrol" and e.get("event") == "reached")
    ringed = [e for e in walks if "ring" in e]
    # red-only clicks, and the stalls that follow them before we move off their cell
    red_only = 0
    red_only_stalled = 0
    pending: tuple[Any, Any] | None = None  # (from, to) of the last red-only click
    for e in evs:
        k = e.get("kind")
        if k == "walk" and e.get("clicked"):
            if pending is not None and list(e["from"]) != list(pending[0]):
                pending = None  # we moved: the click walked
            if (e.get("red") or 0) >= NOENTRY_RED and "ring" in e and not ring_seen(e["ring"]):
                red_only += 1
                pending = (e["from"], e["to"])
        elif k == "stall" and pending is not None and list(e.get("at", [])) == list(pending[0]):
            red_only_stalled += 1
            pending = None
    return {
        "minutes": round(minutes, 2),
        "walk_decisions": len(walks),
        "walk_clicks": sum(1 for e in walks if e.get("clicked")),
        "noentry_carves": carves,
        "carve_share": round(carves / len(walks), 3) if walks else None,
        "flies": dict(flies),
        "dead_end_flies": flies.get("dead_end", 0),
        "uncarves": sum(1 for e in evs if e.get("kind") == "uncarve"),
        "stalls": sum(1 for e in evs if e.get("kind") == "stall"),
        "ring_logged": len(ringed),
        "ring_seen": sum(1 for e in ringed if ring_seen(e["ring"])),
        "red_only_clicks": red_only,
        "red_only_stalled": red_only_stalled,
        "waypoints_reached": reached,
        "reached_per_min": round(reached / minutes, 2) if minutes else None,
    }


def load(p: Path) -> list[dict[str, Any]]:
    f = p / "events.jsonl" if p.is_dir() else p
    return [json.loads(line) for line in f.read_text().splitlines() if line.strip()]


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    for a in argv:
        p = Path(a)
        print(json.dumps({"session": (p if p.is_dir() else p.parent).name, **judge(load(p))}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
