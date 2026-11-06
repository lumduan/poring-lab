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
- waypoints reached (``patrol`` reached events) and per minute;
- with the session's packets (OFFLINE ground truth, never the runner's input): the walk clicks
  that sent NO move request (no ``self_move_request`` within -0.3 .. +0.5 s of the click's log
  line), and those among the clicks STRAIGHT north (our column, >= 6 cells up: p3 sent none for
  93 of 95 at (0, +7)); the dodged targets (``dodge``, dungeon@8.7).

Usage: ``walk_judge.py <session dir or events.jsonl> ...`` -> one JSON row per session.
"""

from __future__ import annotations

import bisect
import gzip
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


COLUMN_DY_MIN = 6  # dungeon_hunt.COLUMN_DY_MIN
REQ_BEFORE_NS, REQ_AFTER_NS = 300_000_000, 500_000_000  # a click's request vs its log line


def judge(events: Iterable[Mapping[str, Any]],
          packets: Iterable[Mapping[str, Any]] | None = None) -> dict[str, Any]:  # fmt: skip
    """PURE: the walk's numbers over one run's events (run_start .. run_end); the move requests
    when ``packets`` (the session's decoded packets) are given."""
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
    clicks = [e for e in walks if e.get("clicked")]
    column = [e for e in clicks if e["to"][0] == e["from"][0]
              and e["to"][1] - e["from"][1] >= COLUMN_DY_MIN]  # fmt: skip
    moves: dict[str, Any] = {}
    if packets is not None:
        req = sorted(int(p["t_mono_ns"]) for p in packets if p.get("type") == "self_move_request")

        def sent(e: Mapping[str, Any]) -> bool:
            i = bisect.bisect_left(req, e["t_ns"] - REQ_BEFORE_NS)
            return i < len(req) and req[i] <= e["t_ns"] + REQ_AFTER_NS

        unsent = [e for e in clicks if not sent(e)]
        moves = {"unsent_clicks": len(unsent),
                 "unsent_share": round(len(unsent) / len(clicks), 3) if clicks else None,
                 "column_unsent": sum(1 for e in column if not sent(e))}  # fmt: skip
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
        "column_clicks": len(column),
        "dodges": dict(Counter(str(e["dodge"]) for e in walks if e.get("dodge"))),
        **moves,
    }


def load(p: Path) -> list[dict[str, Any]]:
    f = p / "events.jsonl" if p.is_dir() else p
    return [json.loads(line) for line in f.read_text().splitlines() if line.strip()]


def load_packets(p: Path) -> list[dict[str, Any]] | None:
    f = (p if p.is_dir() else p.parent) / "packets.jsonl.gz"
    if not f.exists():
        return None
    with gzip.open(f, "rt") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    for a in argv:
        p = Path(a)
        row = judge(load(p), load_packets(p))
        print(json.dumps({"session": (p if p.is_dir() else p.parent).name, **row}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
