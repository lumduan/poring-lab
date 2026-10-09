#!/usr/bin/env python3
"""Walking READINESS (docs/demonstrations.md "Walking readiness", Batt 2026-10-09): a walk version
is good enough to build on when, over its four TUNING runs (indoor/outdoor x clean/crowd, the
first 50 scored routes each):
  * ZERO safety events in all of them (hard), and
  * the POOLED success is >= 90 %, reported with its 95 % Wilson score interval.
96 % stays the long-term target. The same arithmetic scores a held-out map on its own (n = 50).

    walk_readiness.py --label walk@15 SCORE.json [SCORE.json ...]   (a walkNN_score.py output each)

Pure arithmetic over the scorers' outputs: it judges nothing the scorers did not.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

READY = 0.90
TARGET = 0.96
Z95 = 1.959963984540054


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """The Wilson score interval for k successes of n (two-sided; z = 1.96 for 95 %)."""
    if n <= 0:
        raise ValueError("n must be positive")
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def first_object(text: str) -> dict[str, Any]:
    """A walkNN_score.py output is several JSON objects in a row: the first has the counts."""
    obj, _ = json.JSONDecoder().raw_decode(text.lstrip())
    if not isinstance(obj, dict):
        raise ValueError("not a scorer output")
    return obj


# 3.24-3.29's safety events, exactly: requests seen live and the GM's acts of kind normal or pickup.
# The scorers list EVERY GM act under SAFETY (e.g. "GM_act:stand" on a harness @warp): those others
# are reported, never counted (iz_dun00's 4 "stand" acts, 2026-10-09).
SAFETY_KEYS = ("request(live):attack_request", "request(live):npc_contact", "GM_act:normal",
               "GM_act:pickup")  # fmt: skip


def run_row(name: str, score: dict[str, Any]) -> dict[str, Any]:
    scored = score["scored"]
    k, n = int(scored.get("success", 0)), int(scored.get("success", 0)) + int(scored.get("fail", 0))
    listed = score.get("SAFETY") or {}
    unsafe = int(sum(int(v) for key, v in listed.items() if key in SAFETY_KEYS))
    other = {key: int(v) for key, v in listed.items() if key not in SAFETY_KEYS}
    lo, hi = wilson(k, n)
    return {"run": name, "success": k, "n": n, "rate": round(k / n, 4),
            "ci95": [round(lo, 4), round(hi, 4)], "unsafe": unsafe,
            "other_gm_acts": other}  # fmt: skip


def readiness(rows: list[dict[str, Any]]) -> dict[str, Any]:
    k, n = sum(r["success"] for r in rows), sum(r["n"] for r in rows)
    unsafe = sum(r["unsafe"] for r in rows)
    lo, hi = wilson(k, n)
    rate = k / n
    ok = unsafe == 0 and rate >= READY
    return {
        "pooled": {"success": k, "n": n, "rate": round(rate, 4),
                   "ci95": [round(lo, 4), round(hi, 4)]},
        "unsafe": unsafe,
        "ready": ok,
        "why": ("ready" if ok else "; ".join(w for w in (
            f"{unsafe} safety event(s)" if unsafe else "",
            f"pooled {rate:.1%} < {READY:.0%}" if rate < READY else "") if w)),
        "ci_lower_bound_ge_ready": lo >= READY,  # reported: a stricter reading, not the definition
        "target_met": rate >= TARGET,
    }  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("--label", required=True)
    ap.add_argument("scores", nargs="+", type=Path)
    a = ap.parse_args()
    rows = [run_row(p.stem.removeprefix("score-"), first_object(p.read_text())) for p in a.scores]
    print(json.dumps({"label": a.label, "runs": rows, **readiness(rows)}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
