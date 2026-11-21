#!/usr/bin/env python3
"""cursor-1080.md 5b (Amendments 8 and 9): the four-arm play A/B at 1080, scored ONCE.

Arms, each three valid one-run series of screen_ab.py (25 min, not immune), interleaved:
  A = the box (CURSOR_WAIT_S 0.35)            c5b-A1 c5b-A2 c5b-A3
  B = CURSOR_WAIT_S 1.0 (5a passed)           c5b-B1 ...
  C = click on sight                          c5b-C1 ...
  D = click on sight + BOX_EVERY_S 0.25       c5b-D1 ...

Judged, each of B, C, D against A (5b as registered):
  kills_h  mean(X) - mean(A) > +2 SE (Welch); fewer than 2 valid runs an arm: INCONCLUSIVE
  deaths   X <= A over the played runs
  errors   no X run ends with a code error or refuses its start unless an A run does too
  unknown  (B only) the cursor's unknown share on box targets <= 5 %
An arm is BETTER when every line passes, WORSE when deaths or errors fail, NOT BETTER when only
kills_h fails, INCONCLUSIVE otherwise.

Reported (decides nothing): loot/h, Fly Wings/h, alarm Fly Wings, the share of box targets
struck, how strikes ended, world detections a second, the box's age at each box strike and the
strike ends by that age, each arm's kills/h as a % of Batt's 228.5 (batt-benchmark-knife-swap).
The packet measures (a strike click -> an attack request, the walks after it, box -> the first
attack) are a separate committed script, reported beside this.

    cursor_5b_score.py score [--json] [--arm A=c5b-A1+c5b-A2+c5b-A3 ...]
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import statistics
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

ARMS = ("A", "B", "C", "D")
DEFAULT = {a: [f"c5b-{a}{i}" for i in (1, 2, 3)] for a in ARMS}
MINUTES = 25.0
SE_K = 2.0
UNKNOWN_MAX = 0.05
BATT_KILLS_H = 228.5  # his xmas_dun02 Rogue run (batt-benchmark-knife-swap)
AGE_BINS = ((0.0, 0.25), (0.25, 0.5), (0.5, 1.0), (1.0, 1e9))


# --- pure ----------------------------------------------------------------------------------------
def mean_se(xs: Sequence[float]) -> tuple[float | None, float | None]:
    if not xs:
        return None, None
    m = statistics.fmean(xs)
    return (m, None) if len(xs) < 2 else (m, statistics.stdev(xs) / math.sqrt(len(xs)))


def better_line(a: Sequence[float], x: Sequence[float], k: float = SE_K) -> dict[str, Any]:
    """PURE: mean(x) - mean(a) > +k SE (Welch): PASS; INCONCLUSIVE under 2 values an arm."""
    ma, sa = mean_se(a)
    mx, sx = mean_se(x)
    out: dict[str, Any] = {"a": ma, "a_se": sa, "x": mx, "x_se": sx, "n": [len(a), len(x)]}
    if ma is None or mx is None or sa is None or sx is None:
        return {**out, "verdict": "INCONCLUSIVE", "why": "fewer than 2 valid runs in an arm"}
    d, se = mx - ma, math.sqrt(sa * sa + sx * sx)
    return {**out, "diff": d, "se": se, "verdict": "PASS" if d > k * se else "FAIL"}


def judge(a_runs: Sequence[Mapping[str, Any]], x_runs: Sequence[Mapping[str, Any]],
          valid: Any, unknown: float | None = None) -> dict[str, Any]:  # fmt: skip
    """PURE: one arm's lines against A (each run: screen_ab's scored doc plus rc / short)."""
    va = [r for r in a_runs if valid(r, MINUTES)]
    vx = [r for r in x_runs if valid(r, MINUTES)]
    dead_a = sum(int(r.get("deaths") or 0) for r in a_runs if r.get("found"))
    dead_x = sum(int(r.get("deaths") or 0) for r in x_runs if r.get("found"))
    err_a = sum(1 for r in a_runs if r.get("rc") not in (0, 130, None) or r.get("short"))
    err_x = sum(1 for r in x_runs if r.get("rc") not in (0, 130, None) or r.get("short"))
    lines: dict[str, Any] = {
        "kills_h": better_line([r["kills_h"] for r in va], [r["kills_h"] for r in vx]),
        "deaths": {"a": dead_a, "x": dead_x, "verdict": "PASS" if dead_x <= dead_a else "FAIL"},
        "errors": {"a": err_a, "x": err_x,
                   "verdict": "PASS" if err_x == 0 or err_a >= err_x else "FAIL"},
    }  # fmt: skip
    if unknown is not None:
        lines["unknown"] = {"x": unknown, "max": UNKNOWN_MAX,
                            "verdict": "PASS" if unknown <= UNKNOWN_MAX else "FAIL"}  # fmt: skip
    st = {k: v["verdict"] for k, v in lines.items()}
    if "FAIL" in (st["deaths"], st["errors"]):
        overall = "WORSE"
    elif "INCONCLUSIVE" in st.values():
        overall = "INCONCLUSIVE"
    elif "FAIL" in st.values():
        overall = "NOT BETTER"
    else:
        overall = "BETTER"
    return {"verdict": overall, "lines": lines, "valid": [len(va), len(vx)]}


def box_ages(det_t: Sequence[int], strikes: Sequence[Mapping[str, Any]]) -> list[tuple[float, str]]:
    """PURE: (age s, end) of each box strike: the time since the newest world detection before
    it (the hunt core's detections.jsonl, sorted)."""
    out = []
    for e in strikes:
        t = e.get("t_ns")
        if e.get("by") != "box" or not isinstance(t, int):
            continue
        i = bisect.bisect_right(det_t, t) - 1
        if i >= 0:
            out.append(((t - det_t[i]) / 1e9, str(e.get("end"))))
    return out


def age_table(ages: Sequence[tuple[float, str]]) -> dict[str, Any]:
    """PURE: the ages' p10 / p50 / p90 and the strike ends by age bin."""
    xs = sorted(a for a, _ in ages)

    def q(p: float) -> float | None:
        return round(xs[min(len(xs) - 1, int(p * len(xs)))], 3) if xs else None

    bins = {}
    for lo, hi in AGE_BINS:
        ends = [e for a, e in ages if lo <= a < hi]
        bins[f"{lo:g}-{hi:g}" if hi < 1e8 else f">={lo:g}"] = {
            "n": len(ends), **{e: ends.count(e) for e in sorted(set(ends))}}  # fmt: skip
    return {"n": len(xs), "p10": q(0.1), "p50": q(0.5), "p90": q(0.9), "by_age": bins}


def cursor_unknown(events: Sequence[Mapping[str, Any]]) -> tuple[int, int]:
    """PURE: (unknown, all) cursor verdicts on box targets."""
    n = u = 0
    for e in events:
        if e.get("kind") == "box_target":
            for v in e.get("verdicts") or []:
                n += 1
                u += str(v) == "unknown"
    return u, n


# --- the files -----------------------------------------------------------------------------------
def read_jsonl(path: Path) -> list[dict[str, Any]]:
    out = []
    if not path.is_file():
        return out
    for ln in path.read_text(errors="replace").splitlines():
        try:
            e = json.loads(ln)
        except ValueError:
            continue
        if isinstance(e, dict):
            out.append(e)
    return out


def arm_report(labels: Sequence[str]) -> dict[str, Any]:
    import screen_ab as sa
    import stage2_ab as s2

    runs: list[dict[str, Any]] = []
    ages: list[tuple[float, str]] = []
    det_n = 0
    det_s = 0.0
    unk = allv = 0
    diags = []
    for lab in labels:
        if not (sa.SCRATCH / lab / "series.json").is_file():
            continue
        _doc, rs = sa.score_block(lab)
        runs += rs
        for r in rs:
            for d in sorted(s2.DEMO.glob(f"*-{r['label']}-hunt*")):
                ev = read_jsonl(d / "events.jsonl")
                det = sorted(int(x["t_ns"]) for x in read_jsonl(d / "detections.jsonl")
                             if isinstance(x.get("t_ns"), int))  # fmt: skip
                if len(det) > 1:
                    det_n += len(det)
                    det_s += (det[-1] - det[0]) / 1e9
                ages += box_ages(det, [e for e in ev if e.get("kind") == "strike"])
                u, n = cursor_unknown(ev)
                unk, allv = unk + u, allv + n
                diags.append(sa.diag_of(ev))
    valid = [r for r in runs if sa.valid(r, MINUTES)]

    def m(key: str) -> list[float | None]:
        mean, se = mean_se([float(r[key]) for r in valid if r.get(key) is not None])
        return [None if mean is None else round(mean, 1), None if se is None else round(se, 1)]

    kills = m("kills_h")
    return {
        "labels": list(labels), "runs": runs, "valid": len(valid),
        "kills_h": kills, "loot_h": m("loot_h"), "flies_h": m("flies_h"),
        "alarm_flies": sum(int(r.get("alarm_flies") or 0) for r in valid),
        "pct_of_batt": None if kills[0] is None else round(100 * kills[0] / BATT_KILLS_H, 1),
        "detections_s": round(det_n / det_s, 2) if det_s else None,
        "unknown_share": round(unk / allv, 3) if allv else None,
        "box_age": age_table(ages),
        "struck_share": [d.get("struck_share") for d in diags],
        "strike_end": [d.get("strike_end") for d in diags],
        "escapes_h": [d.get("escapes_h") for d in diags],
    }  # fmt: skip


def score(arms: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    import screen_ab as sa

    rep = {a: arm_report(arms[a]) for a in arms}
    out: dict[str, Any] = {"arms": rep, "verdicts": {}}
    for x in ("B", "C", "D"):
        if x in rep and "A" in rep:
            out["verdicts"][x] = judge(rep["A"]["runs"], rep[x]["runs"], sa.valid,
                                       rep[x]["unknown_share"] if x == "B" else None)  # fmt: skip
    return out


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
        if k not in ARMS or not v:
            ap.error(f"--arm {it!r}: X=L1+L2 with X one of {ARMS}")
        arms[k] = v.split("+")
    got = score(arms)
    if a.json:
        print(json.dumps(got, indent=1, default=str))
        return 0
    for x, v in got["verdicts"].items():
        print(f"{x} vs A: {v['verdict']} (valid {v['valid']})")
        for k, ln in v["lines"].items():
            rest = {q: w for q, w in ln.items() if q != "verdict"}
            print(f"  {k}: {ln['verdict']}  {json.dumps(rest, default=str)}")
    for x, r in got["arms"].items():
        print(f"{x}: kills/h {r['kills_h']} ({r['pct_of_batt']} % of Batt) loot/h {r['loot_h']} "
              f"detections/s {r['detections_s']} box age p50 {r['box_age']['p50']} "
              f"unknown {r['unknown_share']}")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
