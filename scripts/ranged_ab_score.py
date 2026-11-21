#!/usr/bin/env python3
"""ranged-attacker-1080.md section 3: A' (the base) vs R (`defend_box` + `defend_ranged`) at 1080,
three valid one-run series a side (rng-A1..3, rng-R1..3), scored ONCE.

  R1 kills/h      mean(R) - mean(A') > +2 SE (Welch)           (cursor_5b_score.better_line)
  R2 defend scans the seconds an hour of "defend" hover scans: mean(R) < mean(A') x 0.75
  R3 deaths R <= A'; errors none new
R joins the base when R1-R3 pass; R2 alone is "faster, not more".

Reported (decides nothing): ranged_defend picks an hour with their species and distance, what
each pick became (packets: an attack request within 6 s, walks only, nothing), Cruiser hits on her
an hour, potions / Fly Wings an hour, loot/h, z/h comes from the economy page.

    ranged_ab_score.py score [--json] [--arm A=rng-A1+rng-A2+rng-A3] [--arm R=...]
"""

from __future__ import annotations

import argparse
import gzip
import json
import statistics
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

DEFAULT = {"A": [f"rng-A{i}" for i in (1, 2, 3)], "R": [f"rng-R{i}" for i in (1, 2, 3)]}
MINUTES = 25.0
R2_SHARE = 0.75
ME = 2000002  # the lab Rogue's account id (the packets' target of a hit on her)


def defend_scan_s_h(events: Sequence[Mapping[str, Any]]) -> float | None:
    """PURE: the seconds an hour of hover scans with purpose "defend" (their own ``ms``)."""
    t = [int(e["t_ns"]) for e in events if isinstance(e.get("t_ns"), int)]
    hours = (max(t) - min(t)) / 3.6e12 if len(t) > 1 else 0.0
    if hours <= 0:
        return None
    ms = sum(float(e.get("ms") or 0) for e in events
             if e.get("kind") == "scan" and e.get("purpose") == "defend")  # fmt: skip
    return round(ms / 1000 / hours, 1)


def r2_line(a: Sequence[float], r: Sequence[float]) -> dict[str, Any]:
    """PURE: mean(R) < mean(A') x R2_SHARE; INCONCLUSIVE under 2 values an arm."""
    if len(a) < 2 or len(r) < 2:
        return {"a": a, "r": r, "verdict": "INCONCLUSIVE", "why": "fewer than 2 valid runs"}
    ma, mr = statistics.fmean(a), statistics.fmean(r)
    return {"a": round(ma, 1), "r": round(mr, 1), "max": round(ma * R2_SHARE, 1),
            "verdict": "PASS" if mr < ma * R2_SHARE else "FAIL"}  # fmt: skip


def overall(lines: Mapping[str, Mapping[str, Any]]) -> str:
    """PURE: JOINS when R1-R3 pass; WORSE on deaths / errors; FASTER NOT MORE when R2 alone."""
    st = {k: v["verdict"] for k, v in lines.items()}
    if "FAIL" in (st.get("deaths"), st.get("errors")):
        return "WORSE"
    if "INCONCLUSIVE" in st.values():
        return "INCONCLUSIVE"
    if all(v == "PASS" for v in st.values()):
        return "JOINS"
    if st.get("defend_scans") == "PASS":
        return "FASTER, NOT MORE"
    return "NOT BETTER"


def pick_fates(picks: Sequence[Mapping[str, Any]], packets: Sequence[Mapping[str, Any]],
               window_s: float = 6.0) -> Counter[str]:  # fmt: skip
    """PURE: each ranged pick's fate: an attack request within ``window_s`` ("attacked"), walk
    requests only ("walked"), or nothing ("none")."""
    att = sorted(int(p["t_mono_ns"]) for p in packets if p.get("type") == "attack_request")
    walk = sorted(int(p["t_mono_ns"]) for p in packets if p.get("type") == "self_move_request")
    out: Counter[str] = Counter()
    for e in picks:
        t = e.get("t_ns")
        if not isinstance(t, int):
            continue
        end = t + int(window_s * 1e9)
        if any(t <= x < end for x in att):
            out["attacked"] += 1
        elif any(t <= x < end for x in walk):
            out["walked"] += 1
        else:
            out["none"] += 1
    return out


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if path.is_file():
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", errors="replace") as fh:  # type: ignore[operator]
            for ln in fh:
                try:
                    e = json.loads(ln)
                except ValueError:
                    continue
                if isinstance(e, dict):
                    out.append(e)
    return out


def arm(labels: Sequence[str]) -> dict[str, Any]:
    import screen_ab as sa
    import stage2_ab as s2

    runs: list[dict[str, Any]] = []
    for lab in labels:
        if (sa.SCRATCH / lab / "series.json").is_file():
            runs += sa.score_block(lab)[1]
    scan_h: list[float] = []
    picks: Counter[str] = Counter()
    fates: Counter[str] = Counter()
    cruiser_hits = 0
    hours = 0.0
    for r in runs:
        if not sa.valid(r, MINUTES):
            continue
        for d in sorted(s2.DEMO.glob(f"*-{r['label']}-hunt*")):
            ev = read_jsonl(d / "events.jsonl")
            v = defend_scan_s_h(ev)
            if v is not None:
                scan_h.append(v)
            pk = read_jsonl(d / "packets.jsonl.gz")
            names = {p.get("gid"): p.get("name") for p in pk if p.get("type") == "entity_appear"}
            cruiser_hits += sum(1 for p in pk if p.get("type") == "act"
                                and p.get("target_gid") == ME
                                and names.get(p.get("src_gid")) == "Cruiser")  # fmt: skip
            hours += float(r.get("minutes") or 0) / 60
            for pl in sorted(s2.DEMO.glob(f"*-play-{r['label']}")):
                pe = [
                    e for e in read_jsonl(pl / "events.jsonl") if e.get("kind") == "ranged_defend"
                ]
                picks.update(str(e.get("species")) for e in pe)
                fates.update(pick_fates(pe, pk))
    return {"runs": runs, "defend_scan_s_h": scan_h, "ranged_picks": dict(picks),
            "pick_fates": dict(fates),
            "cruiser_hits_h": round(cruiser_hits / hours, 1) if hours else None}  # fmt: skip


def score(arms: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    import cursor_5b_score as c5
    import screen_ab as sa

    a, r = arm(arms["A"]), arm(arms["R"])
    j = c5.judge(a["runs"], r["runs"], sa.valid)
    lines = {"kills_h": j["lines"]["kills_h"],
             "defend_scans": r2_line(a["defend_scan_s_h"], r["defend_scan_s_h"]),
             "deaths": j["lines"]["deaths"], "errors": j["lines"]["errors"]}  # fmt: skip
    return {"verdict": overall(lines), "lines": lines, "valid": j["valid"],
            "reported": {k: {q: w for q, w in v.items() if q != "runs"} for k, v in
                         (("A", a), ("R", r))}}  # fmt: skip


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("score")
    sc.add_argument("--arm", action="append", default=[], metavar="X=L1+L2+L3")
    sc.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    arms = {k: list(v) for k, v in DEFAULT.items()}
    for it in a.arm:
        k, _, v = it.partition("=")
        if k not in arms or not v:
            ap.error(f"--arm {it!r}: A=... or R=...")
        arms[k] = v.split("+")
    got = score(arms)
    print(json.dumps(got, indent=1, default=str) if a.json else
          f"R vs A': {got['verdict']} {json.dumps(got['lines'], default=str)}")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
