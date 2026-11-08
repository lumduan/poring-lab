#!/usr/bin/env python3
"""The monster SUPPLY of one run: how many monsters the server showed us (rogue-xmas02.md 5, p13's
E1 study; committed before p13r).

    sight_supply.py SESSION_DIR [--kills N]

From the session's own files, offline (packets are ground truth, ADR-0007; nothing here reaches
a runner):
- the window: ``events.jsonl``'s run_start .. run_end;
- ``packets.jsonl.gz``: every DISTINCT monster gid that appeared in our view in that window
  (``type`` entity_appear, ``objtype`` 5: the stand / move / spawn packets), by species name;
- per 10 minutes of the window; with ``--kills`` (the judge's packet kills), kills per monster seen.
p12 / p13 by this definition (2026-11-08): 50 (16.7 / 10 min) and 31 (10.3 / 10 min).
"""

from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

MONSTER_OBJTYPE = 5


def window(events: Iterable[dict[str, Any]]) -> tuple[int, int]:
    """PURE: (t0, t1) of the run: run_start .. run_end (t_ns, monotonic). ValueError if absent."""
    t0 = t1 = None
    for e in events:
        if e.get("kind") == "run_start" and t0 is None:
            t0 = int(e["t_ns"])
        elif e.get("kind") == "run_end":
            t1 = int(e["t_ns"])
    if t0 is None or t1 is None or t1 <= t0:
        raise ValueError(f"no run_start .. run_end window ({t0}, {t1})")
    return t0, t1


def sightings(packets: Iterable[dict[str, Any]], t0: int, t1: int) -> dict[int, str]:
    """PURE: gid -> species name of every monster that appeared in our view in [t0, t1]."""
    seen: dict[int, str] = {}
    for p in packets:
        if p.get("type") != "entity_appear" or p.get("objtype") != MONSTER_OBJTYPE:
            continue
        t = p.get("t_mono_ns")
        if isinstance(t, int) and t0 <= t <= t1 and isinstance(p.get("gid"), int):
            seen.setdefault(int(p["gid"]), str(p.get("name")))
    return seen


def supply(seen: dict[int, str], t0: int, t1: int, kills: int | None = None) -> dict[str, Any]:
    """PURE: the count, per 10 minutes, by species, and kills per monster seen."""
    minutes = (t1 - t0) / 6e10
    n = len(seen)
    return {"minutes": round(minutes, 2), "seen": n,
            "seen_per_10min": round(n / minutes * 10, 1) if minutes > 0 else None,
            "by_species": dict(Counter(seen.values()).most_common()),
            "kills": kills,
            "kills_per_seen": round(kills / n, 3) if kills is not None and n else None}  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("session", type=Path)
    ap.add_argument("--kills", type=int, default=None)
    a = ap.parse_args(argv)
    with (a.session / "events.jsonl").open() as fh:
        t0, t1 = window(json.loads(line) for line in fh if line.strip())
    with gzip.open(a.session / "packets.jsonl.gz", "rt") as fh:
        seen = sightings((json.loads(line) for line in fh if line.strip()), t0, t1)
    print(json.dumps({"session": a.session.name, **supply(seen, t0, t1, a.kills)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
