#!/usr/bin/env python3
"""THE HAND SCAN'S READS AGAINST THE FLOOR (3.90, Batt 2026-10-20's step 3). OFFLINE, packets as
ground truth (ADR-0007); nothing here runs during play.

Every ``hand_hover`` event (the cell the runner hovered, from its own position belief, and what
the cursor read: hand / empty / sword / unknown) is set against the floor items the server had on
that cell at that moment (``floor_item_appear`` .. ``floor_item_vanish``). Per read:
- ``item_on_cell``: a floor item lay on the hovered cell;
- ``item_within_1``: one lay within 1 cell (the belief can be a cell off the drawn camera).
So "empty" reads WITH an item on the cell are the reader's (or the aim's) misses, and "hand" reads
WITHOUT one are its false hands.

    hand_truth.py SID [SID ...]       per read kind, pooled (JSON)
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

DEMO = Path("/dev/shm/poring-lab-demo")


def floor_spans(packets: Sequence[Mapping[str, Any]]) -> list[tuple[int, int, int, int]]:
    """PURE: each floor item's (x, y, t_appear, t_vanish) -- t_vanish a large number while it is
    still on the floor at the capture's end."""
    on: dict[int, tuple[int, int, int]] = {}
    out: list[tuple[int, int, int, int]] = []
    for e in packets:
        t = int(e["t_mono_ns"])
        if e.get("type") == "floor_item_appear":
            on[int(e["floor_id"])] = (int(e["x"]), int(e["y"]), t)
        elif e.get("type") == "floor_item_vanish" and int(e["floor_id"]) in on:
            x, y, t0 = on.pop(int(e["floor_id"]))
            out.append((x, y, t0, t))
    out.extend((x, y, t0, 1 << 62) for x, y, t0 in on.values())
    return out


def truth(hovers: Sequence[Mapping[str, Any]], spans: Sequence[tuple[int, int, int, int]]
          ) -> Counter[str]:  # fmt: skip
    """PURE: per read kind, how many hovers, how many with an item on / within 1 of the cell."""
    c: Counter[str] = Counter()
    for h in hovers:
        t, (cx, cy), seen = int(h["t_ns"]), h["cell"], str(h["seen"])
        live = [(x, y) for x, y, t0, t1 in spans if t0 <= t < t1]
        on = any(x == cx and y == cy for x, y in live)
        near = any(max(abs(x - cx), abs(y - cy)) <= 1 for x, y in live)
        c[f"{seen}"] += 1
        c[f"{seen}|item_on_cell"] += on
        c[f"{seen}|item_within_1"] += near
    return c


def session(sid: str) -> Counter[str]:
    d = DEMO / sid
    ev = [json.loads(x) for x in (d / "events.jsonl").read_text().splitlines() if x]
    hovers = [e for e in ev if e.get("kind") == "hand_hover"]
    with gzip.open(d / "packets.jsonl.gz", "rt") as fh:
        pk = sorted((json.loads(x) for x in fh), key=lambda e: int(e["t_mono_ns"]))
    return truth(hovers, floor_spans(pk))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("sids", nargs="+")
    a = ap.parse_args()
    tot: Counter[str] = Counter()
    per = {}
    for s in a.sids:
        per[s] = dict(sorted(session(s).items()))
        tot.update(per[s])
    print(json.dumps({**per, "pooled": dict(sorted(tot.items()))}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
