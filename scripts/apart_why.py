#!/usr/bin/env python3
"""Which of OUR clicks attacked a non-target (the held-out map test, 3.76; OFFLINE: packets).

Every attack request whose target is not a hunted species is paired with the last click the bot
logged before it (clicks.jsonl: strike / strike_burst / loot / walk, with its source or why). On
prt_fild06 (2026-10-18) this named the technique that broke: 21 of the 29 non-target attack
requests came from LOOT clicks, whose unit check sees only the detector's boxes -- and the detector
has no box for a species it never learned.

    apart_why.py SID [--targets 1002,1063,1008,1113]

Packets are offline ground truth here (ADR-0007); nothing in this module runs during play.
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import json
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

DEMO = Path("/dev/shm/poring-lab-demo")
NS = 1_000_000_000
TARGETS = (1002, 1063, 1008, 1113)  # Poring, Lunatic, Pupa, Drops (farm0.TARGETS)


def classify(packets: Iterable[Mapping[str, Any]], clicks: Sequence[Mapping[str, Any]],
             targets: Iterable[int] = TARGETS) -> list[dict[str, Any]]:  # fmt: skip
    """PURE: one row per attack request on a non-target -- its job AT THE REQUEST (a Pupa that
    later turns into a Creamy keeps its block id: the last-known job miscounted 3 of them), and
    the last click before it (kind, src / why, track, age in s). ``packets`` sorted by time."""
    tg = set(targets)
    cs = sorted(clicks, key=lambda c: int(c["t"]))
    ct = [int(c["t"]) for c in cs]
    job: dict[int, int] = {}
    rows = []
    for e in packets:
        if e.get("type") == "entity_appear" and e.get("gid") is not None:
            job[int(e["gid"])] = int(e.get("job", -1))
        elif e.get("type") == "attack_request":
            j = job.get(int(e.get("target_gid") or -1))
            if j in tg:
                continue
            t = int(e["t_mono_ns"])
            i = bisect.bisect_right(ct, t) - 1
            c = cs[i] if i >= 0 else {}
            rows.append({"t": t, "job": j, "kind": c.get("kind"),
                         "via": c.get("src") or c.get("why") or c.get("gate"),
                         "track": c.get("track"),
                         "age_s": round((t - int(c["t"])) / NS, 2) if c else None})  # fmt: skip
    return rows


def summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """PURE: counts by job, by click kind, and by (job, kind)."""
    rs = list(rows)
    return {"requests": len(rs),
            "by_job": dict(Counter(str(r["job"]) for r in rs).most_common()),
            "by_kind": dict(Counter(str(r["kind"]) for r in rs).most_common()),
            "by_job_kind": {f"{j}/{k}": n for (j, k), n in
                            Counter((r["job"], r["kind"]) for r in rs).most_common()}}  # fmt: skip


def load(sid: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    d = DEMO / sid
    with gzip.open(d / "packets.jsonl.gz", "rt") as fh:
        packets = sorted((json.loads(x) for x in fh), key=lambda e: int(e["t_mono_ns"]))
    clicks = [json.loads(x) for x in (d / "clicks.jsonl").read_text().splitlines() if x]
    return packets, clicks


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("sid")
    ap.add_argument("--targets", default=",".join(str(t) for t in TARGETS))
    a = ap.parse_args()
    packets, clicks = load(a.sid)
    rows = classify(packets, clicks, [int(x) for x in a.targets.split(",") if x])
    print(json.dumps(summary(rows), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
