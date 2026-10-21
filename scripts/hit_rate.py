#!/usr/bin/env python3
"""The hit rate per species, from the packets OFFLINE (Batt 2026-10-21, the Crusader addendum: "If
the hit rate is poor (measure misses per target species from packets: our attack results vs Orc
Skeleton / Orc Zombie / Drainliar etc.), move points into DEX ... the hit rate as its primary";
docs/planning/crusader-orcsdun01.md section 4). Ground truth only: nothing here reaches the bot.

    hit_rate.py SID [SID ...] [--gm GID]     one JSON: both directions, per species, pooled

- OURS: every ZC_NOTIFY_ACT the character sends at a monster that is an attack (not pickup, sit or
  stand). A HIT carries damage (damage or damage2 non-zero; -1 = an amount hidden from us still
  hit). A MISS carries none; the target's perfect dodge (kind lucky_dodge) is a miss too.
- THEIRS: the same for a monster's act on the character: the character's measured FLEE, the
  re-spec's guard.
- The species is the target's (or the attacker's) job id at its latest appearance before the act
  (entity_appear, objtype 5); a gid never seen appearing is "unknown".
- Each rate carries its Wilson 95 % interval: a re-spec is judged on counts, never on a bare rate.
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
from flow_judge import wilson  # noqa: E402

DEMO = Path("/dev/shm/poring-lab-demo")
GM = 2000002  # the GM account's block id (a player's block id is its account id)
NOT_ATTACKS = {"pickup", "sit", "stand"}
SPECIES = {1002: "Poring", 1063: "Lunatic", 1008: "Pupa", 1113: "Drops", 1018: "Creamy",
           1153: "Orc Zombie", 1152: "Orc Skeleton", 1005: "Familiar", 1042: "Steel Chonchon",
           1111: "Drainliar", 1082: "White Plant", 1084: "Black Mushroom"}  # fmt: skip


def landed(e: Mapping[str, Any]) -> bool:
    """PURE: did this attack act carry damage (a perfect dodge never does)."""
    if e.get("kind") == "lucky_dodge":
        return False
    return int(e.get("damage") or 0) != 0 or int(e.get("damage2") or 0) != 0


def results(packets: Sequence[Mapping[str, Any]], gm: int = GM) -> dict[str, list[dict[str, Any]]]:
    """PURE: {"ours": [...], "theirs": [...]}, each row {t, gid, job, hit}: our attacks on monsters
    and monsters' attacks on us, in packet order."""
    job: dict[int, int] = {}
    out: dict[str, list[dict[str, Any]]] = {"ours": [], "theirs": []}
    for e in packets:
        typ = e.get("type")
        if typ == "entity_appear" and e.get("objtype") == 5 and e.get("gid") is not None:
            if e.get("job") is not None:
                job[int(e["gid"])] = int(e["job"])
        elif typ == "act" and e.get("kind") not in NOT_ATTACKS:
            src, dst = int(e.get("src_gid") or -1), int(e.get("target_gid") or -1)
            if src == gm and dst in job:
                side, g = "ours", dst
            elif dst == gm and src in job:
                side, g = "theirs", src
            else:
                continue
            out[side].append({"t": int(e["t_mono_ns"]), "gid": g, "job": job[g],
                              "hit": landed(e)})  # fmt: skip
    return out


def rates(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """PURE: per species (and "all"): {n, hits, misses, rate, wilson95}."""
    n: Counter[str] = Counter()
    k: Counter[str] = Counter()
    for r in rows:
        for key in (SPECIES.get(int(r["job"]), str(r["job"])), "all"):
            n[key] += 1
            k[key] += int(bool(r["hit"]))
    return {s: {"n": n[s], "hits": k[s], "misses": n[s] - k[s],
                "rate": round(k[s] / n[s], 4), "wilson95": wilson(k[s], n[s])}
            for s in sorted(n, key=lambda s_: (s_ == "all", s_))}  # fmt: skip


def load(sid: str) -> list[dict[str, Any]]:
    with gzip.open(DEMO / sid / "packets.jsonl.gz", "rt") as fh:
        return sorted((json.loads(x) for x in fh), key=lambda e: int(e["t_mono_ns"]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("sids", nargs="+")
    ap.add_argument("--gm", type=int, default=GM)
    a = ap.parse_args()
    pooled: dict[str, list[dict[str, Any]]] = {"ours": [], "theirs": []}
    per: dict[str, Any] = {}
    for sid in a.sids:
        r = results(load(sid), a.gm)
        per[sid] = {side: rates(rows) for side, rows in r.items()}
        for side, rows in r.items():
            pooled[side] += rows
    out = {"sessions": per, "pooled": {side: rates(rows) for side, rows in pooled.items()}}
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
